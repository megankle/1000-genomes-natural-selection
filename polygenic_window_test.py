#!/usr/bin/env python3
import math
import random
import numpy as np
import copy
import sys
import glob


# first argument: trait ID
TRAIT = sys.argv[1]

# second argument: population
population = ["EN", "BA", "H"][int(sys.argv[2])]

# third argument: p-value threshold when choosing associated SNPs
P_EXP = int(sys.argv[3])
P_CUTOFF = np.float_power(10, -1 * P_EXP)

# fourth argument: which biobank/dataset to use
DATASET = sys.argv[4]

# True to use magnitude of beta when calculating polarized statistic; False to just use the sign of beta
USE_EFFECT_SIZE = False

INVALID = 9999999999999999

if DATASET == "UKB":
	gwas_path = "/scratch/07754/meganle/GWAS_stats/hum0197.v3.EUR." + TRAIT + ".v1/*.auto.txt"
	#print("/scratch1/07754/meganle/GWAS_stats/hum0197.v3.EUR." + TRAIT + ".v1/*.auto.txt")
	gwas_file = open(glob.glob(gwas_path)[0], 'r')
elif DATASET == "BBJ":
	gwas_path = "/scratch1/07754/meganle/GWAS_stats/hum0197.v3.BBJ." + TRAIT + ".v1/*.auto.txt"
	gwas_file = open(glob.glob(gwas_path)[0], 'r')
elif DATASET == "body-proportions":
	gwas_path = "/scratch1/07754/meganle/bolt_lmm_2021_11_14/" + TRAIT + "_lmm_combo.tab"
	gwas_file = open(gwas_path, "r")
else:
	assert 0

# quantiles computed from LD score file
LD_CUTOFFS = [1.42309722e-19, 1.33096160e-06, 7.99490360e-04, 1.00316488e-02, 5.29890833e-02, 1.98940513e-01, 8.59677415e-01, INVALID]

ld_file = open("/work/07754/meganle/lonestar/shared/polygenic_scan/deCodeMap_sorted.txt")
	
scan_file = open("/work2/07754/meganle/lonestar/shared/admixture_scans/v4.5_results_sorted/sorted_" + population + "_scan_results_v5_recorrect.txt")
b_file = open("/work/07754/meganle/lonestar/shared/polygenic_scan/v21.0.snp.annot_v2")

NUM_BINS = 8
NUM_TRIALS = 10000

# BBJ headers
COL_HEADERS = [["CHR", "POS", "p.value", "Allele1", "Allele2", "BETA", "AF_Allele2_UKB", "Allele2"], ["CHR", "BP", "P_BOLT_LMM_INF", "ALLELE0", "ALLELE1", "BETA", "A1FREQ", "ALLELE1"], ["CHR", "POS", "p.value", "Allele1", "Allele2", "BETA", "AF_Allele2", "Allele2"]]

COL_CHR = 0
COL_POS = 1
COL_P = 2
COL_REF = 3
COL_ALT = 4
COL_BETA = 5
COL_FREQ = 6
COL_FREQA = 7

print("Population:", population)
print("GWAS Path:", gwas_path)
print("Threshold:", P_CUTOFF)
print("Number of trials:", NUM_TRIALS)
print("Number of bins:", NUM_BINS)

WINDOW_SIZE = 100000
invalid_count = 0

# returns p_val, ref allele, alt alele, beta from the GWAS file given the chromosome and position
def get_gwas_line(find_chr, find_loc):
	global invalid_count
	global gwas_line
	while(gwas_line):
		g_split = gwas_line.split()
		g_chr = g_split[COL_INDICES[COL_CHR]]
		g_loc = int(float(g_split[COL_INDICES[COL_POS]]))

		if g_chr == "X" or g_chr == "Y":
			return INVALID, INVALID, INVALID, INVALID, INVALID, INVALID

		# check for match
		if g_chr == find_chr and find_loc == g_loc:
			try:
				test = float(g_split[COL_INDICES[COL_FREQ]])
			except:
				gwas_line = gwas_file.readline()
				return INVALID, INVALID, INVALID, INVALID, INVALID, INVALID
			return float(g_split[COL_INDICES[COL_P]]), g_split[COL_INDICES[COL_REF]], g_split[COL_INDICES[COL_ALT]], float(g_split[COL_INDICES[COL_BETA]]), float(g_split[COL_INDICES[COL_FREQ]]), g_split[COL_INDICES[COL_FREQA]]

		# check if we've gone too far
		if int(g_chr) > int(find_chr) or (g_chr == find_chr and g_loc > find_loc):
			return INVALID, INVALID, INVALID, INVALID, INVALID, INVALID

		# keep searching 
		gwas_line = gwas_file.readline()
	
	# already reached end of file
	return INVALID, INVALID, INVALID, INVALID, INVALID, INVALID

# returns recombination rate given the chromosome and position
def get_ld(find_chr, find_loc):
	global ld_line
	while(ld_line):
		ld_split = ld_line.split()
		ld_chr = ld_split[0]
		ld_begin = int(ld_split[1])
		ld_end = int(ld_split[2])

		if ld_chr == "X":
			return INVALID

		if ld_chr == find_chr and find_loc >= ld_begin and find_loc < ld_end:
			return float(ld_split[3])

		if int(ld_chr) > int(find_chr) or (ld_chr == find_chr and ld_begin > find_loc):
			return INVALID

		ld_line = ld_file.readline()
	return INVALID

# returns B statistic given the chromosome and position
def get_bscore(find_chr, find_loc):
	global b_line	
	while(b_line):
		b_split = b_line.split()
		b_chr = b_split[1]
		b_loc = int(b_split[3])

		b_ref = b_split[4]
		b_alt = b_split[5]

		anc_der = b_split[12]

		b_anc = INVALID
		b_der = INVALID

		if anc_der != "." and anc_der != ".,.":
			ref_code = int(anc_der.split(",")[0])
			alt_code = int(anc_der.split(",")[1])
			if ref_code == 1 and alt_code == 0:
				b_anc = b_alt
				b_der = b_ref
			elif ref_code == 0 and alt_code == 1:
				b_anc = b_ref
				b_der = b_alt
			else:
				assert 0

		if b_chr == "23":
			return INVALID, b_anc, b_der

		# check for match
		if b_chr == find_chr and find_loc == b_loc:
			if b_split[6] == "." or b_split[6][-1:] == "-":
				return INVALID, b_anc, b_der
			return int(b_split[6][-1:]), b_anc, b_der

		# check if we've gone too far
		if int(b_chr) > int(find_chr) or (b_chr == find_chr and b_loc > find_loc):
			return INVALID, b_anc, b_der

		# keep searching
		b_line = b_file.readline()

# returns column indices for values in GWAS files (so that different GWAS file formats can be submitted in the same batch of jobs)
def get_column_indices(header):
	h_split = header.split()
	indices = np.zeros(len(COL_HEADERS[0]), dtype=int)

	found = False
	for head_type in COL_HEADERS:
		try:
			j = 0
			for col in head_type:
				indices[j] = h_split.index(col)
				j += 1
			found = True
		except:
			continue
	assert found
	print("Column indices:", indices)
	return indices

# use global files/lines so we only have to pass through the files once
global gwas_line
global ld_line
global b_line
global scan_line

scan_line = scan_file.readline()
header = scan_line.split()

# column indices in the admixture scan result file
COL_SCAN_CHR = header.index("CHROM")
COL_SCAN_POS = header.index("POSITION")
COL_SCAN_REF = header.index("REF")
COL_SCAN_ALT = header.index("ALT")
COL_SCAN_T_FREQ = header.index("TARGET_FREQ")
COL_SCAN_T_EXP = header.index("EXPECTED")
COL_SCAN_STAT = header.index("correctedStat")

scan_line = scan_file.readline()

gwas_line = gwas_file.readline()
COL_INDICES = get_column_indices(gwas_line)
gwas_line = gwas_file.readline()


ld_line = ld_file.readline()
ld_line = ld_file.readline()

b_line = b_file.readline()
# manually inserted "***" into B statistic file to mark when the data begins
while (b_line.strip() != "***"):
	b_line = b_file.readline()
b_line = b_file.readline()

# initialize data structures and window variables
LOWEST_P = INVALID
LOWEST_STAT = INVALID
LOWEST_DAF_BIN = INVALID
LOWEST_B_VALUE = INVALID
LOWEST_LD_BIN = INVALID

bin_counts = np.zeros(shape=(NUM_BINS, 10, NUM_BINS))
other_variants = []
for i in range(NUM_BINS):
	other_variants.append([])

	for j in range(10):
		other_variants[i].append([])

		for k in range(NUM_BINS):
			other_variants[i][j].append([])

num_lowest = 0
lowest_sum = 0

start = 1
cur_chr = "1"

while(scan_line):
	split_line = scan_line.split()
	
        # parse admixture scan results file line
	chrom = split_line[COL_SCAN_CHR]
	loc = int(split_line[COL_SCAN_POS])
	ref = split_line[COL_SCAN_REF]
	alt = split_line[COL_SCAN_ALT]
	
        # get GWAS data for this chromosome and position, if it exists
	p_val, g_ref, g_alt, beta, freq, freq_allele = get_gwas_line(chrom, loc)

	# check that this position overlaps with GWAS
	if p_val != INVALID and (split_line[COL_SCAN_STAT] != "NA") and ((ref == g_ref and alt == g_alt) or (ref == g_alt and alt == g_ref)) and not math.isinf(beta):

		stat = float(split_line[COL_SCAN_STAT])
		t_freq = float(split_line[COL_SCAN_T_FREQ])
		t_exp = float(split_line[COL_SCAN_T_EXP])

                # get B statistic for this chromosome and position, if it exists
		b_score, anc, der = get_bscore(chrom, loc)

                # get LD score for this chromosome and position, if it exists
		ld_score = get_ld(chrom, loc)

                # verify overlap between scan file, B statistic file, and LD score file
		if ld_score == INVALID or b_score == INVALID or anc == INVALID:
			scan_line = scan_file.readline()
			continue

		# check B score file alleles against scan alleles
		if not((anc == ref and der == alt) or (anc == alt and der == ref)):
			scan_line = scan_file.readline()
			continue

                # assign the derived allele frequency
		if der == freq_allele:
			daf = freq
		elif anc == freq_allele:
			daf = 1 - freq
		else:
			assert 0
				
                # calculate the derived allele frequency bin
		daf_bin = (NUM_BINS - 1) if daf == 1 else int(daf // (1 / NUM_BINS))

                # assign the direction of selection from scan results
		if t_freq > t_exp:
			direction = 1
		elif t_freq < t_exp:
			direction = -1
		else:
			direction = 0

		# get trait-decreasing allele from effect size
		inc_allele = g_ref if beta < 0 else g_alt

                # if the alternate allele is the trait-increasing allele, reverse the sign of polarized statistic
		if alt == inc_allele:
			direction *= -1
		else:
			assert ref == inc_allele

		if USE_EFFECT_SIZE:
                        # compute the polarized statistic using magnitude of beta
			polarized = abs(stat) * direction * abs(beta)
		else:
                        # compute the polarized statistic only using hte direction of beta
			if beta == 0:
				polarized = 0
			else:
				polarized = abs(stat) * direction
			
                # iterate to find correct LD bin
		ld_bin = 0
		while ld_score > LD_CUTOFFS[ld_bin]:
			ld_bin += 1

		# check if we're in a new window
		if (cur_chr != chrom or (cur_chr == chrom and loc >= start + WINDOW_SIZE)):
			# save current lowest variant information and reset 
			if LOWEST_P != INVALID:
				bin_counts[LOWEST_DAF_BIN][LOWEST_B_VALUE][LOWEST_LD_BIN] += 1
				lowest_sum += LOWEST_STAT
				num_lowest += 1
				
				# reset the lowest variant information
				LOWEST_P = INVALID
				LOWEST_STAT = INVALID
				LOWEST_DAF_BIN = INVALID
				LOWEST_B_VALUE = INVALID
				LOWEST_LD_BIN = INVALID
				LOWEST_CHR = INVALID
				LOWEST_POS = INVALID

			# jump to the next chromosome if necessary
			if cur_chr != chrom:
				cur_chr = chrom	
				start = 1
			# move the window forward until the current variant's location is inside the window
			while(loc >= start + WINDOW_SIZE):
				start += WINDOW_SIZE

		assert (cur_chr == chrom and loc < start + WINDOW_SIZE)

		# check if the current variant is lower than current lowest and the p value is lower than the threshold in this window
		if p_val < LOWEST_P and p_val <= P_CUTOFF:
			if LOWEST_P != INVALID:
				# bin the current lowest, since it's no longer the lowest in this window
				other_variants[LOWEST_DAF_BIN][LOWEST_B_VALUE][LOWEST_LD_BIN].append(LOWEST_STAT) 

			# save the current variant as the current lowest in this window
			LOWEST_P = p_val
			LOWEST_STAT = polarized
			LOWEST_DAF_BIN = daf_bin
			LOWEST_B_VALUE = b_score
			LOWEST_LD_BIN = ld_bin
			LOWEST_CHR = chrom
			LOWEST_POS = loc
		else:
			# this variant is not lower than the current lowest, so bin it
			other_variants[daf_bin][b_score][ld_bin].append(polarized)

	scan_line = scan_file.readline()

# check the last current lowest statistic
if LOWEST_P != INVALID:
	lowest_sum += LOWEST_STAT
	bin_counts[LOWEST_DAF_BIN][LOWEST_B_VALUE][LOWEST_LD_BIN] += 1
	num_lowest += 1

if num_lowest != 0:
	lowest_avg = lowest_sum / num_lowest 
	print("Number of lowest variants:", num_lowest)
	print("Lowest average:", lowest_avg)

	lower_count = 0
	higher_count = 0
	equal_count = 0

	for n in range(NUM_TRIALS):
		trial_sum = 0
		trial_valid = 0
		for i in range(NUM_BINS):
			for j in range(10):
				for k in range(NUM_BINS):
                                        # get the number of lowest variants in this bin
					num_sample = int(bin_counts[i][j][k])
					if num_sample != 0:
                                                # sample the number of lowest variants in this bin from the list of non-lowest variants in this bin
						sampled = random.sample(other_variants[i][j][k], num_sample)
						assert num_sample == len(sampled)
						trial_sum += np.sum(sampled)
						trial_valid += num_sample
		assert trial_valid == num_lowest

                # calculate average polarized statistic for this trial
		trial_avg = trial_sum / trial_valid
		if trial_avg < lowest_avg:
			lower_count += 1
		elif trial_avg > lowest_avg:
			higher_count += 1
		else:
			equal_count += 1

	print("Number of trials lower:", lower_count)		
	print("Number of trials higher:", higher_count)		
	print("Number of trials equal:", equal_count)		
	
        # save the results to a .npy file to be auto compiled into a spreadsheet
	if USE_EFFECT_SIZE:
		np.save("./" + DATASET + "_effect_size/results/" + TRAIT + "_" + str(P_EXP) + "_" + population + ".npy", [num_lowest, lower_count, higher_count])
	else:
		np.save("./" + DATASET + "_no_effect_size/results/" + TRAIT + "_" + str(P_EXP) + "_" + population + ".npy", [num_lowest, lower_count, higher_count])
		

ld_file.close()
scan_file.close()
b_file.close()
gwas_file.close()
