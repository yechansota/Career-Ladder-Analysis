# Which Doors Open for Outsiders?
### Vacancy Access in the U.S. Federal Internal Labor Market

A personal data project measuring **which grade levels are reachable depending on how you enter an organisation**, using ten years of U.S. federal personnel records.

---

## 1. Project Motivation

**There is an argument that recurs in every organisation.**

> **Do people hired from outside get treated better, or do people who stay inside have the advantage?**

You hear both versions at once — that experienced hires are paid above internal staff at the same seniority, and that the people who stay long enough end up holding the posts. **Neither has ever been checked.**

No organisation publishes *"here is what we pay experienced hires, and here is what we pay internal promotions."* So the argument always ends in anecdote.

I wanted to know whether this is specific to particular organisations or **structural to organisations as such** — and if structural, whether **changing jobs repeatedly is actually the answer.** Many people act on that belief and it has never been tested.

### Why the U.S. federal government

Private-employer data cannot answer this, so I used the government that publishes its personnel records monthly. It carries one decisive property.

> **Grade placement is not negotiable.** Every position carries a grade fixed in law, and individuals cannot negotiate it.

> **If a gap by entry path appears even where grade cannot be negotiated, the gap is structural rather than a matter of bargaining power.**
> Conversely, **if it disappears there**, the experienced-hire premium is something the **negotiation channel** creates.

Either way there is an answer.

*Precisely: **step** within a grade is negotiable to a limited degree under Superior Qualifications authority. But step 1 to step 10 spans roughly 30% of pay while GS-9 to GS-13 spans roughly double, and what this project measures is door height, not pay. (No step column exists in the data — see §12.)*

---

## 2. Research question and the three comparisons

### Why three comparisons rather than one

The original question contains **two roles that must be assigned precisely** before anything can be measured.

| In the question | The group in this data |
|---|---|
| Someone **hired in from outside** with a career behind them | **New hires** — a 45-year-old first-time entrant already carries twenty years of career |
| An **internal employee** at the same seniority | **Incumbents of the same age or tenure** |

**The "transfers" in this data are not outside hires.** They were already inside the federal system, moving between agencies. That makes them a third group, and each pairing answers a different sub-question.

| # | Comparison | What it isolates | Why it is needed |
|---|---|---|---|
| **A** | **New hires vs same-age incumbents** | Whether arriving from outside beats staying inside | **This is the original question.** It is the only pairing that maps onto "external hire vs internal employee at the same seniority" |
| **B** | **Transfers vs new hires** | The value of **prior system experience**, holding the entry point constant | Both are outsiders *to the hiring agency*, so agency-level differences cancel. This isolates experience itself, which A cannot do because incumbents differ from entrants in many ways at once |
| **C** | **Transfers vs same-age incumbents** | Whether **moving** carries a premium over **staying** | Answers the second half of the question — *"is changing jobs the answer?"* — which neither A nor B can address |

Reading only one of the three produces the wrong conclusion. **A** without **B** cannot tell whether the penalty attaches to *being new* or to *lacking experience*. **B** without **C** invites reading the transfer advantage as a mobility premium, which **C** shows it is not.

### The answer

**Comparison A — the hypothesis is disconfirmed.**

| Age band | External hire vs same-age incumbent | Share below incumbent |
|---|---:|---:|
| 30-34 | **−2 steps** | 66.7% |
| 40-44 | **−2 steps** | 63.3% |
| 50-54 | **−1 step** | 58.7% |

> **Where grade placement cannot be negotiated, someone hired in from outside starts one to two steps below an internal employee of the same age.** That is the reverse of the starting hypothesis.
<img width="1790" height="1417" alt="01_doorway" src="https://github.com/user-attachments/assets/7d58030b-486d-4ded-ad24-03e7dae69653" />

**Comparisons B and C.**

| Comparison | Result |
|---|---|
| **B** Prior experience vs none | **Decisive advantage** — 12 more per 100 reach GS-13+ |
| **C** Movers vs same-tenure, same-age incumbents | **No systematic tilt** — same median grade, symmetric distribution |

> **Experience is priced. "Moving" by itself is not.**

### What this project does not answer

The starting question also contained **"do they get favoured?"** That part **cannot be answered from public data.**

| | Comparison | Answerable? |
|---|---|---|
| (A) | Entrants with prior experience vs entrants without | **Yes** |
| (B) | Outside entrants vs people who built the same seniority inside | **Partly** |

**(B) is the core of "favouritism," so this project does not demonstrate favouritism.** The favouritism argument is about *who should have got the position*. This project answers the prior question — **which heights of position get filled through which channel in the first place.**

---

## 3. Data Source

| | |
|---|---|
| Source | **OPM Federal Workforce Data** (`data.opm.gov`) |
| Access | **Public API, no authentication.** Parquet download |
| Datasets | `accessions`, `separations`, `employment` (September stock snapshots) |
| Window | **FY2015–FY2024** (2014-10 to 2024-09, 120 months) |
| Reproducibility | **Every file's API version is recorded and pinned in a manifest**, because OPM was observed revising past files retroactively |

**FedScope was replaced by FWD in January 2026.** Code and tutorials written against FedScope have broken paths; this project targets FWD.

**Schema audit:** the September files for 2015, 2018, 2021 and 2024 carry identical column structures (64/68/69 columns), and all files were reissued under one schema, so **pooling ten years is safe**.

---

## 4. Data Cleaning and Processing

### Sample reduction cascade

**Generated automatically** (`analyze_extensions.py`, Stage B) so hand-written numbers cannot drift from the code.

| Step | Count | % of raw |
|---|---:|---:|
| FWD accessions, raw | **2,730,385** | 100.0% |
| + FY2015–2024 window | 2,729,696 | 100.0% |
| + pay plan = GS | 1,768,921 | 64.8% |
| + grade 01–15 | 1,768,835 | 64.8% |
| + competitive service | 1,161,161 | 42.5% |
| + full-time | 1,042,394 | 38.2% |
| + exclude named-foreign, accession AA/AC → **main sample** | **1,003,763** | 36.8% |
| + drop rehire-suspect → **estimation sample** | **842,522** | 30.9% |

**Main-sample strata**

| Stratum | Count | Share |
|---|---:|---:|
| AC — pure new hires | 701,134 | 69.9% |
| AC_REHIRE_SUSPECT — separate stratum | 161,241 | 16.1% |
| AA — transfers | 141,388 | 14.1% |

**Rehire-suspects** are recorded as new hires but show prior federal service. **The OPM codes have no rehire category**, so they are pulled out of the main analysis and handled separately.

### Data quality defects

All documented in `docs/SCHEMA_AUDIT.md`.

| Defect | Measured | Response |
|---|---|---|
| **Pay withheld, non-randomly** | 51.1% | Pay dropped as an outcome; **grade used instead** |
| **Duty station withheld** | **48.2%; three columns at 48.16 / 48.16 / 48.21%** | **Suppression is per record, not per column**, so switching columns does not help. Regional analysis closed |
| **No step column** | — | **Step negotiation cannot be measured.** Declared as a limitation, not ruled out |
| SCD sentinel (`1900-01-01`) | 3.4% of accessions | Derived LOS set to null; **rows kept** |
| LOS confounded with military credit | 99.5% of LOS>0 are veterans | **LOS not used** as a proxy for prior experience |
| Education missingness asymmetric | 1.97% vs 0.12% (**16.2×**) | Sensitivity re-estimation moves the result 0.159 pp; stated as a limitation |

---

## 5. Four rules that favour insiders — written, not customary

The federal system uses **position classification**: **grades attach to positions, not people.** "Budget analyst post = GS-13" is decided in advance, and whoever sits in it gets GS-13.

So the question becomes **which doors, at which heights, open for whom** — vacancy access.

**And four rules give insiders an advantage.** These are hard to know without having worked in government, so each is spelled out with a private-sector analogue.

| # | Rule | Content | Analogue |
|---|---|---|---|
| **1** | **Merit promotion (internal-only) announcements** | Only current or former federal career employees may apply ("status candidate"). **Outsiders cannot see the posting** | A role filled only through internal posting — except this is **statutory procedure, not custom** |
| **2** | **Time-in-grade** | **52 weeks** at the next lower grade is required to move up. **That grade history accrues only inside the federal system** | "A year as senior manager before director" — **where that service only counts if it happened here** |
| **3** | **Differential qualification thresholds** | Inservice applicants may qualify on experience **two grades below**; outside applicants need **one grade below** | Same post, different threshold for insiders and outsiders |
| **4** | **RIF retention order** (5 CFR 351) | Release order runs tenure group → veterans' preference → **length of service** → performance. **Service precedes performance** | Seniority written into the order of layoffs |

**Rule 3 was found only after the analysis**, while verifying the qualification standards. So part of the gap measured here is **the direct product of written regulation**, not informal preference.

---

## 6. Methodology

### The two groups

| | Definition | n |
|---|---|---:|
| **Transfers (AA)** | Already federal employees, moving to another agency | 141,388 |
| **New hires (AC)** | Entering federal service for the first time | 701,134 |

**Both are outsiders to the hiring agency.** The difference is prior federal experience.

**Group validity:** transfers hold career tenure at **83.2%** and show prior federal service at **62.1%**; new hires at **5.0%** and **10.2%**.

### Controls

Agency, occupational group, education band, age band, veteran status, fiscal year, plus an **occupational-group × year interaction** to absorb the time-varying expansion of direct-hire authority in IT and cyber.

### Model choices

| Choice | What | Why |
|---|---|---|
| **Threshold ladder** | P(grade ≥ 9 / 11 / 13 / 14) estimated **separately** | Ordered logit assumes an identical effect at every threshold. This project **expects that assumption to fail**, so it was checked rather than imposed |
| **Grouped binomial GLM** | Collapse to cell-level successes and trials | 842k rows × ~300 dummies needs a 3.6 GB design matrix. All covariates are categorical, so collapsing is **mathematically identical** |
| **Cluster-robust SE** | Department × occupational group (936 clusters) | Entries within a cluster are correlated. Treating 842k observations as independent would understate standard errors |
| **Empirical Bayes shrinkage** | Department × occupation cells | Without it, ranking tables are topped and tailed by small cells |

### Percentage points, not odds ratios, as the headline

**Odds ratios split sharply by group**, which is why they are reported only as a supplement.

| Group | Odds ratio |
|---|---:|
| Non-veterans | **5.14×** |
| Veterans | **1.97×** |
| Pooled | 3.06× |

**The pooled 3.06 is an average of two structurally different groups** and cannot serve as a headline. **Percentage points are stable**: the strata-weighted mean (12.03 pp) matches the pooled estimate (11.81 pp).

**How to read an odds ratio.** An odds ratio of 3.06 does **not** mean "three times as many people get in." It multiplies the *odds*.

> If 11 of 100 new hires reach GS-13 or above, the odds are 11/89 = 0.124.
> Multiplied by 3.06 that becomes 0.379, which converts back to **27.5%**.
> So **11% → 27.5%** is what "an odds ratio of 3.06" actually means.

Odds ratios remain useful because they are **comparable across different base rates**, which percentage points are not.

---

## 7. Key Findings

### Finding 1 — the gap exists at every grade threshold

| Threshold | Matched on age (direct) | Not matched (total) | Odds ratio |
|---|---:|---:|---:|
| ≥ GS-9 | **+18.14 pp** | — | 3.66 |
| ≥ GS-11 | **+19.25 pp** | **+26.58 pp** | 3.61 |
| ≥ GS-13 | **+11.81 pp** | **+15.79 pp** | 3.06 |
| ≥ GS-14 | **+5.23 pp** | — | 2.99 |
| Supervisory | **+5.72 pp** | **+7.58 pp** | 2.69 |

All estimates p < 0.0001, 936 clusters.
<img width="1909" height="1172" alt="04_year_trend" src="https://github.com/user-attachments/assets/cc77828f-cdbd-446b-a840-0d9adb22ca7d" />
<img width="1713" height="1749" alt="03_threshold_ladder" src="https://github.com/user-attachments/assets/0e980cf6-a267-46ce-ae66-d0da5c55fd87" />

**Evidence** — the pre-registered prediction was "the gap widens at higher grades" (a glass ceiling). **It was wrong.** Percentage points peak at GS-11 and fall, but **odds ratios run 3.66 → 2.99, nearly flat.** The decline in percentage points is an **arithmetic consequence of falling base rates**.

**Year stability:** 3 measures × 10 years = **30 estimates, all the same sign**, coefficient of variation **0.11**. The pattern holds through two changes of administration and a pandemic.

> **⚠ For seniority-based organisations, use the total effect.**
>
> The headline 11.81 pp is **matched on age**. But in a seniority-based system — the Korean and Japanese pattern — **seniority itself is the mechanism.** Matching it away deletes precisely what you wanted to observe.
>
> → In that context the reference figure is the **total effect: 15.79 pp** (26.58 pp at GS-11). The age-matched 11.81 pp is *"the path effect that survives after seniority is removed."*

**Practical interpretation** — a gap present at every height means **the two groups are on different ladders from the ground up**, not blocked at one rung. But **high doors are few**, so a constant relative disadvantage becomes near-complete absence at the top in absolute terms. **What an individual experiences is a ceiling; the cause is different.**

<img width="1790" height="1417" alt="02_vacancy_pyramid" src="https://github.com/user-attachments/assets/8f6f3094-09b3-4e62-b486-6a571e28b93f" />

---

### Finding 2 — movement carries no systematic tilt; first entry does

Compared against incumbents of the same age (813,000 matched, 96.6%), **with spread**:

| | Median diff | IQR | Below | Equal | Above |
|---|---:|---|---:|---:|---:|
| **Transfers** (40-44) | **0.0** | −2 to +1 | 38.2% | 25.9% | 35.9% |
| **Transfers** (55-59) | **0.0** | −1 to +1 | 34.7% | 26.2% | 39.1% |
| New hires (30-34) | **−2.0** | −4 to 0 | **66.7%** | 16.6% | 16.7% |
| New hires (50-54) | **−1.0** | −4 to 0 | **58.7%** | 19.0% | 22.3% |

**Evidence** — among transfers, as many land below (38%) as above (36%): the distribution is **symmetric**. Two independent matching axes — service length and age — gave the same answer.

**Only about one in four land at exactly the same grade**, so the accurate statement is **"no systematic tilt," not "exactly neutral."**

**⚠ This is not age discrimination.** The comparison group is **incumbents of the same age**; it does not set older against younger. The disadvantage attaches to **being newly arrived, not to being older.** And it gets **smaller with age**, not larger — someone entering in their fifties arrives around GS-11, within one step of a same-age incumbent at GS-12. Age discrimination would produce the opposite pattern.

**Practical interpretation** — the disadvantage attaches not to *moving* but to **entering without prior experience**.

---

### Finding 3 — HR and procurement are the most closed; IT the most open

**Reading the gap alone inverts the conclusion**, so absolute rates on both sides are shown.

| Occupation | Transfers ≥13 | New hires ≥13 | Gap |
|---|---:|---:|---:|
| Mathematics & Statistics | 78.5% | 23.7% | **+54.8 pp** |
| **Human Resources** | 40.7% | **6.8%** | +33.9 pp |
| **Business & Procurement** | 40.5% | 11.2% | +29.3 pp |
| Accounting & Budget | 40.0% | 10.7% | +29.3 pp |
| **Information Technology** | **55.4%** | **37.9%** | **+17.5 pp** |
| Medical | 14.7% | 8.4% | +6.3 pp |
| Transportation | 12.5% | 12.0% | +0.5 pp |

Pre-registered contrast (IT − federal-specific): **−11.09 pp**.

<img width="1711" height="1580" alt="05_occupation_scatter" src="https://github.com/user-attachments/assets/de0b9dd3-e6a2-406d-9d6e-61a2b77595f0" />

**Evidence** — **37.9% of IT new hires enter at GS-13 or above against 6.8% in HR**, a 5.6× difference. IT's transfers (55.4%) also exceed HR's transfers (40.7%). **IT's narrow gap comes from new hires being pulled up, not transfers being held down** — consistent with direct-hire authority bypassing competitive procedure.

**⚠ No gap is not the same as an open door.** Legal shows a small gap (+2.9 pp) because **both sides are extremely low** (3.7% and 0.8%).

**⚠ That "Legal" is not attorneys.** Federal attorneys (series 0905) sit in the **excepted service**, and this project samples the **competitive service only**, so Department of Justice attorneys are absent from the data entirely. What appears is **legal support** — paralegals, legal assistants. Many physicians, judges and intelligence personnel are likewise excepted and absent.

**Security clearance is not the cause.** Tested separately with Investigation as an occupation and Defense / Homeland Security / Justice as departments: at department level the direction **reversed** (10.2 pp inside versus 13.6 pp outside). HR is not clearance-intensive to begin with. **What remains is internal knowledge succession** — and procurement additionally has a **written education requirement** that experience cannot substitute for above GS-13.

**Practical interpretation** — the constraint type determines the lever, and the two are opposite.

| Constraint | Symptom | Lever that works |
|---|---|---|
| **Process** (IT-type) | Outsiders do enter high, just slowly | Speed, **delegated grade-setting authority** |
| **Knowledge** (HR/procurement-type) | Outsiders **cannot** enter high at all | Process fixes are inert. Design **knowledge transfer** |

---

### Finding 4 — smaller organisations are more closed, and people inside them do not rise either

| Department | Gap (GS-13+) | n(AA) |
|---|---:|---:|
| Justice | **+18.60 pp** | 3,699 |
| General Services Administration | +17.56 pp | 3,086 |
| Health & Human Services | +15.60 pp | 6,996 |
| Homeland Security | +12.89 pp | 9,906 |
| Veterans Affairs | +9.86 pp | 12,785 |
| Interior | +9.16 pp | 7,843 |
| Agriculture | +8.64 pp | 7,669 |
| **Defense** | **+8.41 pp** | 62,177 |

Size (log) × transfer interaction: supervisory **−0.272 (p = 0.0001)**.

**Evidence** — the prediction ("large organisations fill from within, so bigger gaps") was **wrong; the reverse holds.** The incumbent age-grade slope, by department:

| Organisation size | Tenure → grade conversion (per-department slope) |
|---|---|
| **Large** (above median) | **Works** — 0.0989 |
| **Small** (at or below median) | **Barely** — 0.0635 |

Slopes come from a median split of 59 departments. **The per-department gaps above (Justice 18.60 to Defense 8.41) are individual estimates, not group means**, so they are kept out of this table.

**⚠ Reading size correctly.** Justice, with the largest gap, is **not a small department by headcount.** But this sample covers the **competitive service only** — much of FBI, Bureau of Prisons and DEA is excepted or law-enforcement — so Justice's competitive-service GS population is smaller than its total. **Size here means size within this sample.**

**It holds with Defense excluded** (0.0985 vs 0.0619, 58 departments), so it is not one department's artefact.

<img width="1790" height="1417" alt="07_size_seniority" src="https://github.com/user-attachments/assets/474714f3-86df-43d7-914d-314718597a4b" />

**⚠ The moderator is size.** Entered jointly, size survives (−0.201, p = .011) while **closedness does not** (+0.111, p = .143), and the closedness effect also shrinks once the seniority slope is unweighted. **Closedness is therefore not reported as an independent moderator.**

**Practical interpretation** — **in small organisations neither path works.** The binding constraint is not culture but **the count of senior posts**. The intuition *"we're small and nimble, so we're open"* runs against the data.

**Defense holds 44% of all transfers (62,177/141,388) while showing the smallest gap**, so the headline estimate is effectively Defense-weighted (excluding it: 11.81 → 14.25 pp).

---

### Finding 5 — veterans' preference cuts the insider premium nearly in half

| | GS-13+ gap | Supervisory gap |
|---|---:|---:|
| Non-veterans (preference does not apply) | **15.00 pp** | 6.48 pp |
| Veterans (preference applies) | **8.03 pp** | 4.74 pp |
| Reduction | **−46%** | −27% |

**Evidence** — veterans' preference **applies to competitive appointment by law and does not apply to inter-agency transfer.** Decomposed by path:

| Outcome | Competitive path | Interaction | Transfer path |
|---|---:|---:|---:|
| ≥GS-11 | +0.474 | −0.655 | −0.181 |
| ≥GS-13 | +0.406 | −0.824 | −0.418 |
| Supervisory | +0.862 | −0.942 | **−0.080** |

**For supervisory entry the advantage vanishes almost exactly on the transfer path.** The effect appears where the law reaches and only there, which makes it **the rule <img width="1750" height="1213" alt="06_veteran_paths" src="https://github.com/user-attachments/assets/bf61b2e9-1fd9-4519-bc44-6ec3128d4931" /><img width="1750" height="1213" alt="06_veteran_paths" src="https://github.com/user-attachments/assets/9a81dbd8-670c-465e-99db-e7fc0a6fad33" />
 veterans.**

**Practical interpretation** — **policy works only on the channel it is attached to.** A diversity target or experienced-hire policy attached to open competition, in an organisation where most senior roles are filled by internal movement, will **run exactly as designed and change nothing.**

*Caveat: veterans and non-veterans may differ in unobserved ways. This project does not evaluate whether the preference is good policy — only that it has a measurable, channel-bounded effect.*

---

### Finding 6 — a quarter of the gap travels through the age/tenure channel

| | Matched | Not matched | Share travelling through |
|---|---:|---:|---:|
| GS-11+ | 19.37 | 26.58 | **27.1%** |
| GS-13+ | 11.73 | 15.79 | **25.7%** |
| Supervisory | 5.71 | 7.58 | **24.7%** |

**Evidence** — the main specification enters age as an **additive control**, treating it as a confounder. But in the chain *prior experience → older → higher grade*, age is a **mediator**, and controlling a mediator understates the total effect.

**⚠ Naming constraint (measured).** Age-band rank correlates with mean federal tenure at **+0.992 for transfers and +0.959 for new hires.** The two cannot be separated, so this is reported only as the **"age/tenure channel"** and never as an age effect.

**⚠ Method limitation.** In a nonlinear model, coefficients shift when covariates are added even with no confounding (noncollapsibility). Percentage points behave far better than log-odds, but this remains **a descriptive decomposition, not a causal mediation estimate.**

**Practical interpretation** — **both values are reported**: the gap people experience is **15.79 pp**, the age-conditional gap is **11.81 pp**.

**And the gap forms in the thirties, then locks in.**

| Age band | GS-13+ gap |
|---|---:|
| 20-24 | **−0.05** (p = 0.69, not significant) |
| 30-34 | +12.47 |
| **35-39** | **+15.85** (peak) |
| 55-59 | +14.19 |
| 65+ | +10.75 |

**In the early twenties there is no gap.** *(That cell has only 644 transfers, so power is low.)*
<img width="1909" height="1213" alt="09_age_gap_curve" src="https://github.com/user-attachments/assets/f113dc06-5b62-4d9e-bfdc-5a344d1e2778" />

---

### Finding 7 — a degree opens the door but does not carry you up
<img width="1750" height="1213" alt="06_veteran_paths" src="https://github.com/user-attachments/assets/cbccafb4-b49b-4525-b5c1-890e1d5c15e2" />

Share of new hires entering at GS-13 or above:

| Education | New hires | Transfers |
|---|---:|---:|
| **Doctorate** | **41.5%** | 71.7% |
| Master's / professional | 23.4% | 52.6% |
| Bachelor's | 9.1% | 33.9% |
| High school or less | 8.9% | 23.3% |

**Evidence** — the education-driven spread falls **41%** from GS-9 to GS-13 (indexing GS-9 at 100, GS-13 comes in at 59).

**Institutional boundary, verified against OPM standards:** education substitutes for experience **only up to GS-11** (master's for GS-9, doctorate for GS-11). **From GS-12 up, specialized experience is required and a degree cannot supply it** (GS-12 research positions excepted).

**Two observations:**
1. **A new hire with a doctorate (41.5%) beats a transfer with a bachelor's (33.9%)** — a credential can beat insider status, but it takes a doctorate
2. **Bachelor's and high school are effectively identical** (9.1% vs 8.9%) — **the threshold sits at master's level**
<img width="1750" height="1213" alt="08_education_ladder" src="https://github.com/user-attachments/assets/e10896da-6697-4b58-96e0-b9ddc7ab6eaa" />

**A degree opens the door in two different ways** (pre-registered predictions P-C1 and P-C2, both held).

| | Rule | Scope |
|---|---|---|
| **Rule A** | Education substitutes for experience (master's → GS-9, doctorate → GS-11, nothing above GS-12) | **All occupations** |
| **Rule B** | **Positive education requirement** — without the degree you are not qualified, and experience cannot substitute | **Occupation-specific** |

Education spread, new hires only, after controls:

| Threshold | Credentialed occupations | Non-credentialed | Ratio |
|---|---:|---:|---:|
| ≥GS-9 | 5.82 | 3.25 | **1.79** |
| ≥GS-11 | 5.29 | 2.50 | **2.12** |
| ≥GS-13 | 3.80 | 2.19 | **1.73** |

**P-C1 held** — roughly twice the education effect where a positive requirement exists. **P-C2 held** — both groups attenuate from GS-9 to GS-13, confirming Rule A is general.

**⚠ This does not appear before controlling.** Raw, the master's-over-bachelor's step is +13.6% versus +12.9% — **no difference.** **⚠ The occupational classification is imprecise** — two-digit groups cannot track a regulatory boundary (Accounting & Budget holds both accountants, coursework required, and budget analysts, no requirement). **The twofold difference appeared despite that**; refining to four-digit series is backlog.

**⚠ Education-control asymmetry — verified.** Education is missing for **1.97%** of new hires against **0.12%** of transfers (**16.2×**). Dropping all missing-education records moves the estimate by at most **0.159 pp** (pre-registered threshold 0.5 pp), so **the conclusion does not depend on how missingness is handled.**

The missingness **means different things in the two groups**: new hires with education missing average **GS-4.8** (1.5% reach GS-13+), transfers average **GS-11.2** (34.3%). The former looks like "no degree to record," the latter like a plain record gap.

**Removing the education control entirely makes the gap +1.18 pp larger**, so without it education's effect would be misattributed to the entry path. **Keeping it was correct.**

**Practical interpretation** — **a degree moves your starting line forward; it does not replace the ladder.** The same shape as veterans' preference: opening the hiring door without opening the promotion door.

---

## 8. Robustness
<img width="1869" height="1027" alt="10_robustness" src="https://github.com/user-attachments/assets/0cd72302-e4ad-4de4-ac34-3bfc38e4193d" />

| Specification | GS-13+ | Reading |
|---|---:|---|
| Main | 11.81 pp | — |
| Same-specification reference (no interaction) | 11.73 pp | **Specification effect −0.08 ≈ 0** |
| **Entry grade ≥ 11 (career-ladder correction)** | **13.22 pp** | **Sample effect +1.49 pp** |
| Excluding FY2015 (mixed file versions v2/v3) | 11.91 pp | Unchanged |
| Excluding artefact departments | 11.58 pp | Unchanged |
| Excluding Defense | 14.25 pp | Rises |
| Excluding missing-education records | 11.87 pp | Unchanged |

**The career-ladder alternative is rejected.** The strongest objection was that *new hires cluster at GS-5/7/9 ladder entry points and structurally cannot reach GS-13.* Removing the ladder range **does not shrink the gap; it grows.** Specification change and sample restriction were separated to confirm this.

**FY2015 files carried mixed versions (v2/v3)**, but excluding them does not move the result, so the analysis window is kept.

---

## 9. Figures

`pipeline/make_dashboard.py` reads the actual CSV and DuckDB outputs and emits a **single self-contained HTML file** with no hardcoded numbers.

| Chart | Finding |
|---|---|
| **Two Doors** — entry-grade distributions mirrored across a GS-1..15 ladder | 1 |
| **Vacancy pyramid** — post counts by grade, each tier coloured by filling path | 1 |
| **Dual axis** — percentage points as bars, odds ratios as a line | Methodology |
| **Occupation scatter** — X new hires, Y transfers, 45° line | 3 |
| **Size × seniority quadrant** | 4 |
| Year trends, veteran path decomposition, sensitivity bars, Parity Index table, annotation chips | 1, 5, 8 |

**Suppressed cells render as `—`, never as 0, and are excluded from the payload.**

**⚠ Not yet run.** The generator has been verified against stand-in data only and has not been executed on the real data, so **no rendered HTML is included in this repository.**

---

## 10. Repository Structure

```
README.md                    This document
README_KO.md                 Korean version
PUBLISHING.md                GitHub publishing guide: file-by-file decisions, commit order, safety checks
requirements.txt  .gitignore

docs/
  EXPLAINER.md               Plain-language explainer (Korean), 16 sections
  EXPLAINER_EN.md            Plain-language explainer (English), 16 sections
  RESEARCH_DESIGN.md         Pre-registration, full results, verification history (v2.1)
  SCHEMA_AUDIT.md            Data dictionary, quality audit, linkage diagnostics (v1.3)
  LINKEDIN_POST.md           Publication draft (KO/EN)

pipeline/
  config.py                  Single source for window, filters, codes, thresholds
  ingest.py                  Version-pinned download with manifest
  build_analysis.py          DuckDB analysis tables
  aggregate.py               Empirical Bayes shrinkage, cell suppression, Parity Index
  estimate.py                Threshold-ladder GLM with cluster-robust SE (H1-H5, Ancillary A)
  analyze_extensions.py      Integrity audit, sample cascade, occupation levels, agency axes, veteran strata
  analyze_age.py             Age/tenure channel, seniority slope, education ceiling
  analyze_credentials.py     Two education rules, geography suppression audit, step-channel check
  verify_02.py               Spread, education asymmetry, seniority slope re-estimation, collinearity
  verify_03.py               Education-missingness sensitivity
  make_annotations.py        Chart annotation layer for institutional changes and data limits
  make_dashboard.py          Self-contained HTML dashboard generator (--lang ko|en)
  README.md                  Run order and interpretation rules

archive/                     Diagnostic and patch history, kept rather than discarded
  README.md                  What each patch fixed and why
  linkage_diagnostic.py      v1 initial linkage diagnostic
  linkage_diagnostic_v2.py   v2, stages F/B/C/D/E/G/H
  diagnose_02.py             Root-cause trace for a TypeError
  patch_estimate_01..07.py   Seven sequential patches after the first real-data run
  PATCH_extensions_01.md     Cascade and SQL three-valued-logic fixes (applied; script retired)
```

---

## 11. Reproducing the Analysis

```bash
pip install -r requirements.txt
cd pipeline

python ingest.py --scope main        # FY2015-2024, about 700 MB, one time
python make_annotations.py
python build_analysis.py             # builds the DuckDB tables
python aggregate.py
python estimate.py                   # H1-H5 and Ancillary A
python analyze_extensions.py         # integrity audit and extensions
python analyze_age.py                # age/tenure and education axes
python analyze_credentials.py        # credential rules, geography, step channel
python verify_02.py
python verify_03.py
python make_dashboard.py             # -> docs/dashboard.html
python make_dashboard.py --lang en   # -> docs/dashboard_en.html
```

**Run order follows dependencies.** `build_analysis.py` needs `fwd_cache/*.parquet`; the analysis and verification scripts need `fwd.duckdb`; `make_dashboard.py` needs the CSV outputs of everything before it.

**Optional — linkage diagnostics.** To reproduce the evidence that rejected the individual-tracking design:

```bash
python archive/linkage_diagnostic_v2.py --stage all
```

### What reproduction needs, and does not

| | |
|---|---|
| **Not needed** | API key, authentication, application process — FWD is fully public |
| **Needed** | About 1 GB of disk (700 MB cache plus DuckDB), Python 3.11+ |
| **Caution** | **OPM revises past monthly files retroactively.** Do not compare results across files downloaded at different times. `ingest.py` records versions in a manifest |
| **Not in the repository** | Raw data (700 MB), the DuckDB file, record-level outputs — blocked by `.gitignore` |

---

## 12. Limitations

### What this project does not claim

**It does not demonstrate favouritism.** Whether a position was open to internal candidates — internal posting, the internal applicant pool, merit promotion outcomes — is not in the public data.

### Stated limitations

| Limitation | Measured basis |
|---|---|
| **Individual promotion cannot be tracked** | No person identifier; quasi-identifier linkage doubly rejected (§14) |
| **AA is restricted to competitive-to-competitive moves** | 99.5% of transfers |
| **The control group contains rehires** | 16.1% of the AC family (161,241 records) |
| **Pay cannot be analysed** | 51.1% non-random suppression; grade used instead |
| **Regional analysis is closed** | Duty station 48.2% suppressed, three columns identical (per-record suppression) |
| **Step negotiation unverified** | No `step` column. Grade non-negotiability is confirmed; step is not measured |
| **Education control is asymmetric** | 16.2×; sensitivity moves the estimate 0.159 pp |
| **Age and tenure cannot be separated** | Correlation +0.992 / +0.959 |
| **Performance, bargaining power and job capability unobserved** | — |
| **Multiple comparisons** | Roughly 40 tests. Headline results (p<0.0001) survive any correction; **marginal ones (size p=.055, closedness p=.042) and department rankings do not** |
| **Federal-specific features** | Grades attach to positions, separation is difficult, agencies are mission organisations. **Federal transfers map better onto inter-affiliate movement in a corporate group than onto private lateral hires** |

**Every gap is therefore called "a conditional gap associated with entry path," and discrimination is not claimed.**

### Verification status

**Passed:** integrity audit **20/20**. Estimates of the same specification obtained by two independent routes agree (11.728 vs 11.73). Service-length and age-based comparisons agree independently.

**Two statements were narrowed by verification:**

| Item | Final statement |
|---|---|
| Mobility neutrality | "No systematic tilt" (IQR ±2 steps, 25% exactly equal) |
| Organisational moderator | **Size only.** Closedness is entangled with size and cannot be separated |

**Backlog with no bearing on conclusions:** four-digit series refinement of the credential classification, dashboard execution on real data.

---

## 13. Why public-sector data is useful to a private employer

The most predictable objection, answered directly.

### Numbers do not transfer. Mechanisms and diagnostics do.

| | Claim | This project |
|---|---|---|
| **Transferring the number** | "Private firms will show 11.8 pp too" | **Not done** |
| **Transferring the mechanism** | "Where firm-specific knowledge is large, outside experience is discounted more" | **The core** |
| **Transferring the diagnostic** | "Measure this in your own organisation" | **Highest practical value** |

### The federal government is not the average — it is the extreme, which makes it a floor

No negotiation on grade, grades fixed in law, procedure maximised, discretion minimised.

> **A gap by entry path appeared even where discretion barely exists.**
> → It **cannot be explained by discretion, negotiation or favouritism.**
> → Where discretion is far greater, there is **at least this much, with discretionary effects on top.**

So the federal figure is **not an estimate of the private sector but a floor.**

*Counter-condition: an employer could show less if it is small, has standardised jobs and almost no internal mobility — an early-stage startup. The floor argument applies to **organisations with hierarchy and an internal labour market.***

### The strongest use: as a control case

> **Federal (grade not negotiable):** at equal age and tenure, moving in yields the same grade. Mobility premium **absent**.
> **Private (negotiable):** internal employees at the same seniority reportedly cannot reach an external hire's pay. Mobility premium **present**.
>
> → The difference is the **negotiation channel.** The experienced-hire premium exists **not because outsiders are worth more, but because their price is set in the market.**
> → So the lever is not "pay experienced hires less" but **"index internal pay to the market."**

### What transfers and what does not

| Finding | Private analogue | Transferability |
|---|---|---|
| Occupational knowledge lock (HR/procurement vs IT) | In-house systems and process knowledge | **High** |
| Policy works only on its own channel | Referrals, intern conversion, internal postings | **High** |
| Seniority channel (a quarter of the gap) | Same | **High** |
| Credential ceiling (a degree only opens the door) | Degree recognition by job level | **Medium-high** |
| Smaller organisations are more closed | Same | **Medium-high** |
| Uniform gap at every grade | Only where job levels exist | **Medium** |
| Neutrality of moving | Negotiation exists | **Low — it is the control case** |
| Promotion = relocation, 11.5× | Varies | **Low** |
| The 11.8 pp figure itself | None | **Not transferable** |

### From a private employer's point of view

**For executives** — the experienced-hire premium is a **pricing problem, not a talent-value problem.** The narrative that external talent is better and therefore costs more is not supported. Repricing internal talent to market may be cheaper and more reliable, since they already hold the firm-specific knowledge.

**For compensation leads** — this reframes as an **attrition-cost problem.** The wider the internal-external pricing gap, the stronger the incentive to realise it by leaving, and replacement costs more than the gap.

**For HR leaders** — **HR was the most closed occupation in this data.** HR designs the organisation's mobility policy while being the function that admits the least outside perspective, and those leaders then write mobility policy for everyone else. The structure is self-reinforcing.

**A misreading to avoid** — "so stop hiring externally" does not follow. What follows is that **external sourcing is structurally hard in certain jobs**, so **Make/Buy should be decided job by job.**

### Eight things to measure in your own organisation

All feasible in an ordinary HRIS.

| # | Measure | How | Reading |
|---|---|---|---|
| 1 | **Knowledge-lock index** | Share of senior fills sourced externally, by job family, last 3 years | Near zero → Make; high → Buy |
| 2 | **Channel audit** | Which channel fills senior roles vs which channel your policy attaches to | Mismatch → the policy runs and nothing changes |
| 3 | **Dual pricing check** | Median internal pay vs median external-hire pay, same job and seniority | Large gap → a pricing problem, not an evaluation problem |
| 4 | **Senior vacancy density** | Count of senior positions; annual senior vacancies | Fewer → external access structurally blocked |
| 5 | **Promotion-mobility coupling** | Share of promotions that also changed team or location | High → people who cannot move are squeezed out |
| 6 | **Seniority gradient** | Average job level by tenure band, incumbents only | Steeper → tenure converts into level more strongly |
| 7 | **Credential ceiling** | Degree's contribution to level, by level band | Disappears at senior levels → opens the door, does not carry up |
| 8 | **Gap formation age** | Internal vs external level distribution by age band | Where the gap opens is where to intervene |

---

## 14. Diagnostic record — more failed than succeeded

The original design was to track individuals over ten years. **The data rejected it.**

| Finding | Content |
|---|---|
| **Individual tracking impossible** | No person identifier. Quasi-identifier linkage **doubly rejected** — differential selection **19.65 pp** (threshold 10) and key instability **107.64%** (threshold 13.74) |
| **The linked sample was biased** | New hires arrive in cohorts (same date, office, occupation); transfers arrive individually → transfers **over-sampled 1.6×** |
| **Promotion = relocation** | People who changed duty station were promoted at **11.5×** the rate of those who did not |
| **Geographic mobility** | **0.41%** monthly — far lower than expected |
| **FedScope retired** | Replaced by FWD in 2026-01; OPM reissued twenty years under one schema |
| **Retroactive revision observed** | The same monthly file changed between runs (sentinels 846 → 84). Version pinning is mandatory |

**The 11.5× promotion-relocation coupling** was a by-product of failure but is a finding in itself — *promotion means moving house, so people who cannot relocate are structurally squeezed out.*

### Five bugs found and fixed in my own code

| Bug | Content |
|---|---|
| Missing values in the cluster key | Under pandas 3.0, `NaN.astype(str)` does not become a string — **every estimate failed** |
| Memory accumulation | GLM objects not released — **three out-of-memory kills** |
| Separation undetected | A diverging coefficient was reported as a result (odds ratio 8.6 × 10¹²) |
| Non-monotonic sample cascade | An `OR` condition printed a step where the sample **grew** |
| SQL three-valued logic | `NULL IN (...)` returns NULL, dropping **2.38%** of transfers from both comparison groups |

All recorded in `archive/` with their evidence. **Two of my diagnoses were wrong** (a department-level merge was not the cause) and **one patch shipped dead code.**

---

## 15. Pre-registration record — 5 right, 5 wrong

| Prediction | Outcome |
|---|---|
| IT would be more open | **Right** |
| Closed organisations would show bigger gaps | **Right** (but entangled with size; not separable) |
| Part of the gap would travel through age/tenure | **Right** (25–27%) |
| The education effect would weaken at senior grades | **Right** (41% reduction) |
| The gap would widen at higher grades | **Wrong** — present throughout |
| The interaction signature in the veterans analysis | **Wrong** — I mis-specified the statistical reading |
| Larger organisations would show bigger gaps | **Wrong** — the reverse |
| Incumbents would outrank movers | **Wrong** — no systematic tilt |
| Small organisations would show steeper seniority slopes | **Wrong** — the reverse |
| The gap would keep widening with age | **Partly** — peaks at 35-39, then flat |

**All five failures are left uncorrected.** No pre-registered threshold was relaxed after seeing results. **And one failed prediction produced the strongest result** — the neutrality of movement.

---

## 16. Practitioner summary

| Question | What the data says |
|---|---|
| **What grade for an experienced hire?** | **12 more per 100** matched people reach GS-13+ (16 without matching on age). Raw medians differ by 5 steps (GS-12 vs GS-7) |
| **Which occupation is most closed?** | HR (new hires reach GS-13+ at **6.8%**), Investigation (5.4%), Legal support (0.8%). IT is 37.9% |
| **The most striking comparison** | **A first-time entrant into IT (37.9%) matches a transfer into HR (40.7%)** |
| **Is my organisation open?** | **Smaller means more closed.** The reverse of the "small and nimble" intuition |
| **Does a degree help?** | It opens the door but does not carry you up. **The threshold is master's level** |
| **How should policy be designed?** | Policy works **only on its own channel.** Veterans' preference cuts the gap 46% where it applies and has zero effect where it does not |
| **What about individuals?** | Moving is **neither an advantage nor a disadvantage.** What pays is **holding prior experience**, and it gets priced in the thirties |

Full discussion: [Plain-Language Explainer](docs/EXPLAINER_EN.md)

---

## 17. Ethics and reproducibility

- Aggregate outputs only; **cells of 10 or fewer suppressed** (adopting OPM's own standard)
- Record-level outputs blocked by `.gitignore`
- Every file's API version recorded and pinned. **Results from files of different versions are never compared**
- Pre-registered predictions and thresholds were not revised after seeing results
- The record-linkage design was rejected, and the rejection evidence is fully documented in `docs/SCHEMA_AUDIT.md`

---

## 18. Relation to prior work

Bidwell, M. (2011). Paying More to Get Less: The Effects of External Hiring versus Internal Mobility. *Administrative Science Quarterly*, 56(3), 369–407.

Bidwell found that external hires receive roughly an **18% pay premium** and hold stronger credentials, are promoted faster, yet score lower on performance in their first two years and leave at higher rates.

**None of those four results can be reproduced from public federal data.**

| Bidwell result | Reproducible here? | Why not |
|---|---|---|
| 18% pay premium | **No** | Pay 51% suppressed, and pay is a function of grade |
| Lower early performance | **No** | No performance-appraisal data |
| Faster promotion | **No** | Individual tracking impossible (§14) |
| Higher exit rates | **Partly** | Only an LOS-based approximation |

**This project is therefore not a replication of Bidwell, and does not present itself as one.**

**What it is instead: a boundary-condition test.** Bidwell measured a premium in a system where pay is negotiated. This project examines a system where **grade placement cannot be negotiated** and finds **no mobility premium there** — movers hold the same grade as same-age, same-tenure incumbents, while the disadvantage falls on first-time entrants.

That supports a specific reading of Bidwell's result: **the premium comes from the pricing channel, not from outsiders being more valuable.** Where the channel is closed, the premium is absent; the structural sorting of who reaches which position remains.

---

*A personal project. It does not represent the views of OPM or any institution.*
