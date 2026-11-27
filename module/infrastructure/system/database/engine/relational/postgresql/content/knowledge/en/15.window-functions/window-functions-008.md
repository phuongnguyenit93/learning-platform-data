# ntile, percent_rank, cume_dist, and Data Distribution in PostgreSQL

A report showing only `AVG(score)` or `MAX(score)` is often insufficient to understand **data distribution**. Two customer cohorts can share the exact same average spend yet look completely different: the first consists mostly of customers with similar spend levels, while the second has a handful of very high spenders and many low spenders. To see that difference, you typically need to rank rows, bucket them by position, and locate where an observation sits in the distribution.

PostgreSQL provides window functions especially suited for this task:

- **`NTILE(n)`:** splits ordered rows within a partition into up to `n` buckets of roughly equal **row count**.
- **`PERCENT_RANK()`:** measures relative rank position from 0 to 1, derived from `RANK()` and total row count.
- **`CUME_DIST()`:** calculates the cumulative fraction of rows standing before or at the current value in the chosen order, accounting for the entire peer group (*peers*).

All three look percentage-related at first glance, yet **they do not return the same concept**. `NTILE(4)` does not compute "25%, 50%, 75% quantile cutoffs"; `PERCENT_RANK()` is not the fraction of rows less than or equal to the current value; and `CUME_DIST()` does not split data into four equal-sized groups.

This lesson uses data containing tied scores, multiple segments, and a single-observation segment to highlight their differences. By the end, you will be able to apply them to customer tiering, exam scoring, revenue analysis, and boundary verification when ties exist.

## 1. Prerequisites: window functions and OVER

Unlike standard `GROUP BY`, window functions generally **preserve each source row** and append computed columns based on related rows.

General syntax example:

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score ASC, measure_id ASC
    ) AS bucket
FROM distribution_lab.measurements;
```

Meaning:

| Component | Role |
| --- | --- |
| `NTILE(4)` | Requests splitting into up to 4 ordered buckets. |
| `OVER (...)` | Defines the window for the function. |
| `PARTITION BY segment` | Evaluates **independently within each segment**; restarts in the next segment. |
| `ORDER BY score ASC` | Lower scores come before higher scores. |
| `measure_id ASC` | Secondary tie-breaker for stable ordering when scores match. |
| `AS bucket` | Names the output column without creating a physical table column. |

`PARTITION BY` is optional. If omitted, all input rows form one partition for the window function. The window's `ORDER BY` also has its own semantics and must be designed intentionally.

### 1.1. PARTITION differs from GROUP BY

With:

```sql
SELECT segment, AVG(score) AS average_score
FROM distribution_lab.measurements
GROUP BY segment;
```

each `segment` collapses to a single output row.

With:

```sql
SELECT
    measure_id,
    segment,
    score,
    AVG(score) OVER (PARTITION BY segment) AS segment_average
FROM distribution_lab.measurements;
```

each observation keeps its own row; the segment average repeats across rows of that segment.

`NTILE`, `PERCENT_RANK`, and `CUME_DIST` belong to the window function family, so their goal is **attaching position/distribution metrics to each row**, not collapsing all rows into one summary row.

### 1.2. ORDER BY inside OVER vs. ORDER BY on the result

```sql
SELECT
    measure_id,
    score,
    PERCENT_RANK() OVER (ORDER BY score) AS relative_rank
FROM distribution_lab.measurements
ORDER BY measure_id DESC;
```

`ORDER BY score` inside `OVER` determines how ranks are calculated. `ORDER BY measure_id DESC` at the end determines the **display order of rows after evaluation**. Do not treat these two clauses as the same thing.

If a SQL query omits the final `ORDER BY`, PostgreSQL makes no guarantee about returned row order, even if the window includes `ORDER BY`.

## 2. Practice data: tied scores and a tiny segment

We create a score table where each row represents one observation of an entity at a point in time. Examples are strictly for statistical illustration and do not reflect any real HR or customer grading scale.

### 2.1. Creating the schema and table

Run in a practice database:

```sql
CREATE SCHEMA IF NOT EXISTS distribution_lab;

CREATE TABLE distribution_lab.measurements (
    measure_id bigint PRIMARY KEY,
    segment text NOT NULL,
    score numeric(10, 2),
    observed_on date NOT NULL
);
```

Insert 14 observations:

```sql
INSERT INTO distribution_lab.measurements
    (measure_id, segment, score, observed_on)
VALUES
    (101, 'north',  50.00, DATE '2026-10-01'),
    (102, 'north',  50.00, DATE '2026-10-02'),
    (103, 'north',  70.00, DATE '2026-10-03'),
    (104, 'north',  90.00, DATE '2026-10-04'),
    (105, 'north',  90.00, DATE '2026-10-05'),
    (106, 'north',  90.00, DATE '2026-10-06'),
    (107, 'north', 110.00, DATE '2026-10-07'),
    (108, 'north', 140.00, DATE '2026-10-08'),

    (201, 'south',  30.00, DATE '2026-10-01'),
    (202, 'south',  30.00, DATE '2026-10-02'),
    (203, 'south',  40.00, DATE '2026-10-03'),
    (204, 'south',  80.00, DATE '2026-10-04'),
    (205, 'south', 100.00, DATE '2026-10-05'),

    (301, 'pilot',  95.00, DATE '2026-10-01');
```

Read the data:

```sql
SELECT measure_id, segment, score
FROM distribution_lab.measurements
ORDER BY segment, score, measure_id;
```

Scores in ascending order:

| Segment | Row count | Score values in ascending order |
| --- | ---: | --- |
| north | 8 | 50, 50, 70, 90, 90, 90, 110, 140 |
| south | 5 | 30, 30, 40, 80, 100 |
| pilot | 1 | 95 |

Notable points:

- `north` has two 50s and three 90s; these form **peer groups** when sorted solely by `score`.
- `south` has two 30s.
- `pilot` has just one observation; some ranking formulas must handle a zero denominator.

Re-running the full `INSERT` will trigger a duplicate primary key error in PostgreSQL. To practice again, use a fresh lab schema or clean up data in a controlled manner; never drop a production schema.

## 3. Peer groups: rows tied under the window's ORDER BY

For ranking functions, **peers** are rows indistinguishable across **all `ORDER BY` expressions of the window**.

Consider north:

```text
ID       Score
101       50  ┐
102       50  ┘ same peer group under ORDER BY score
103       70
104       90  ┐
105       90  ├ same peer group
106       90  ┘
107      110
108      140
```

If you use:

```sql
PERCENT_RANK() OVER (PARTITION BY segment ORDER BY score)
```

then all rows with score 90 in north receive the **exact same `percent_rank`**.

Yet if you use:

```sql
PERCENT_RANK() OVER (
    PARTITION BY segment
    ORDER BY score, measure_id
)
```

then the 90-point rows are no longer peers because `measure_id` differs. Every row now has a unique ordering position and the percentile outputs change.

**Important warning:** adding a primary key to `ORDER BY` inside `PERCENT_RANK` or `CUME_DIST` does not merely stabilize display; it **alters the peer groups and the statistical formula itself**. You may add a secondary key to `NTILE` to decide which row lands in a boundary bucket, while keeping `ORDER BY score` alone for metrics where tied scores must share the exact same standing.

## 4. NTILE(n): dividing rows into roughly equal buckets

`NTILE(n)` assigns each row a bucket number from 1 to `n` based on the sort order inside the partition.

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (
        ORDER BY score ASC, measure_id ASC
    ) AS quartile_bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Result:

| measure_id | score | quartile_bucket |
| ---: | ---: | ---: |
| 101 | 50 | 1 |
| 102 | 50 | 1 |
| 103 | 70 | 2 |
| 104 | 90 | 2 |
| 105 | 90 | 3 |
| 106 | 90 | 3 |
| 107 | 110 | 4 |
| 108 | 140 | 4 |

Eight rows are split into four buckets of two rows each. Because sorting is `ASC`, **bucket 1 holds low-score rows**, and bucket 4 holds high-score rows.

### 4.1. Bucket sizing rules

Given `N` rows and `B` requested buckets:

- Each created bucket has size approximately `N/B`.
- Row counts across buckets never differ by more than one row.
- If there is a remainder, earlier buckets receive one extra row.
- If `N < B`, at most `N` buckets contain rows; trailing bucket numbers do not appear in the output.

Examples:

| Row count N | `NTILE(B)` | Populated bucket sizes |
| ---: | --- | --- |
| 8 | `NTILE(4)` | 2, 2, 2, 2 |
| 8 | `NTILE(3)` | 3, 3, 2 |
| 5 | `NTILE(4)` | 2, 1, 1, 1 |
| 5 | `NTILE(2)` | 3, 2 |
| 3 | `NTILE(5)` | 1, 1, 1; buckets 4 and 5 are empty |
| 1 | `NTILE(4)` | 1; only bucket 1 appears |

`n` must be a valid bucket count greater than 0. `NTILE(0)` or negative bucket counts make no sense and are rejected by PostgreSQL.

### 4.2. Splitting into three groups

```sql
SELECT
    measure_id,
    score,
    NTILE(3) OVER (ORDER BY score, measure_id) AS tercile
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

With 8 rows, buckets hold 3, 3, and 2 rows respectively:

```text
bucket 1: 50, 50, 70
bucket 2: 90, 90, 90
bucket 3: 110, 140
```

You can use `NTILE(10)` for deciles or `NTILE(100)` for row-count percentile buckets, provided the dataset is large enough for those buckets to be statistically meaningful.

### 4.3. NTILE can split tied values

In the `NTILE(4)` output, the three rows scoring 90 do not stay in one bucket: ID 104 lands in bucket 2, while IDs 105 and 106 land in bucket 3.

That is **not a bug**. `NTILE` prioritizes balanced row counts across buckets; it never promises to keep tied values together in a single bucket.

If business rules require "equal scores always belong to the same tier", you cannot blindly run row-level `NTILE` and call the result fair. Later sections show how to bucket by **distinct score values** or use peer-aware thresholds.

### 4.4. NTILE is not equal-width value intervals

In north, bucket 1 spans 50–50, bucket 2 spans 70–90, bucket 3 spans 90–90, and bucket 4 spans 110–140. The score widths of each bucket vary widely.

`NTILE` splits by **observation count**, not by value interval width. To split the scale `[0, 160)` into equal-width bins, use `width_bucket` or boundary `CASE` expressions—that is a different problem.

## 5. PERCENT_RANK(): relative rank position

`PERCENT_RANK()` reflects a row's rank **relative to the number of rows in the partition**, by the formula:

\[
\operatorname{percent\_rank}(x)=
\begin{cases}
0, & N=1 \\\\
\dfrac{\operatorname{rank}(x)-1}{N-1}, & N>1
\end{cases}
\]

Here:

- `N`: number of rows in the partition.
- `RANK()`: 1-based rank of the row under `ORDER BY`.
- Rows tied under `ORDER BY` are **peers**, sharing identical `RANK()` and `PERCENT_RANK()`.

### 5.1. Manual calculation on north

Ascending scores: `50, 50, 70, 90, 90, 90, 110, 140`. There are 8 rows so the denominator is 7.

| Score | Rows with this score | RANK | PERCENT_RANK by formula |
| ---: | ---: | ---: | ---: |
| 50 | 2 | 1 | `(1-1)/7 = 0` |
| 70 | 1 | 3 | `(3-1)/7 ≈ 0.285714` |
| 90 | 3 | 4 | `(4-1)/7 ≈ 0.428571` |
| 110 | 1 | 7 | `(7-1)/7 ≈ 0.857143` |
| 140 | 1 | 8 | `(8-1)/7 = 1` |

Because 50 appears twice, the next rank for 70 is **3**, not 2. Because 90 appears three times, the next rank for 110 is **7**, not 5.

### 5.2. PERCENT_RANK query

```sql
SELECT
    measure_id,
    score,
    RANK() OVER (ORDER BY score) AS score_rank,
    ROUND(
        (PERCENT_RANK() OVER (ORDER BY score))::numeric,
        6
    ) AS percent_rank_value
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Expected result:

| measure_id | score | score_rank | percent_rank_value |
| ---: | ---: | ---: | ---: |
| 101 | 50 | 1 | 0.000000 |
| 102 | 50 | 1 | 0.000000 |
| 103 | 70 | 3 | 0.285714 |
| 104 | 90 | 4 | 0.428571 |
| 105 | 90 | 4 | 0.428571 |
| 106 | 90 | 4 | 0.428571 |
| 107 | 110 | 7 | 0.857143 |
| 108 | 140 | 8 | 1.000000 |

The function returns `double precision`; the example casts to `numeric` to call `ROUND(..., 6)` for display. Interpret decimal places in light of floating-point precision and formatting.

### 5.3. PERCENT_RANK does not necessarily reach 1

Test three rows:

```sql
WITH sample(score) AS (
    VALUES (10), (20), (20)
)
SELECT
    score,
    RANK() OVER (ORDER BY score) AS rnk,
    PERCENT_RANK() OVER (ORDER BY score) AS pr
FROM sample
ORDER BY score;
```

Result:

```text
score  rank  percent_rank
10      1        0.0
20      2        0.5
20      2        0.5
```

The highest score is 20, yet `PERCENT_RANK` is only 0.5, not 1, because the top score group has **two peers**, starting at rank 2 out of three rows.

Therefore, never assert "the highest score must have `percent_rank = 1`". Only when the final rank equals `N` (i.e., the highest score is unique) does the formula yield 1.

### 5.4. Single-row partition

When `N=1`, the general formula would divide by 0. PostgreSQL defines `PERCENT_RANK() = 0` for a one-row partition.

```sql
SELECT
    segment,
    score,
    PERCENT_RANK() OVER (PARTITION BY segment ORDER BY score) AS pr
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Result `pr = 0`. Do not interpret this as "bottom 0%"; it is simply a **single observation with no meaningful relative rank**.

## 6. CUME_DIST(): cumulative distribution

`CUME_DIST()` stands for *cumulative distribution*. In ascending score order, it returns the **fraction of rows with scores less than or equal to the current score**, across the entire partition.

For an arbitrary sort order, the exact phrasing is the **number of rows preceding or belonging to the current peer group in that order**, divided by total rows.

Within a tied group, all peers receive the same result and all are included in the numerator:

\[
\operatorname{cume\_dist}(x)
= \frac{\text{rows preceding or in the peer group of }x}{N}
\]

### 6.1. Manual calculation on north

| Score | Rows less than or equal to this score | CUME_DIST |
| ---: | ---: | ---: |
| 50 | 2 / 8 | 0.250 |
| 70 | 3 / 8 | 0.375 |
| 90 | 6 / 8 | 0.750 |
| 110 | 7 / 8 | 0.875 |
| 140 | 8 / 8 | 1.000 |

All three rows scoring 90 receive **0.75**, because 6 out of 8 rows have a score less than or equal to 90.

### 6.2. Query

```sql
SELECT
    measure_id,
    score,
    ROUND(
        (CUME_DIST() OVER (ORDER BY score))::numeric,
        4
    ) AS cumulative_share
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Result:

| measure_id | score | cumulative_share |
| ---: | ---: | ---: |
| 101 | 50 | 0.2500 |
| 102 | 50 | 0.2500 |
| 103 | 70 | 0.3750 |
| 104 | 90 | 0.7500 |
| 105 | 90 | 0.7500 |
| 106 | 90 | 0.7500 |
| 107 | 110 | 0.8750 |
| 108 | 140 | 1.0000 |

### 6.3. Value range

For a partition of `N` rows, `CUME_DIST()` is always strictly greater than 0 and at most 1. The minimum value is at least `1/N`; if the first score tier has multiple peers, the initial value is larger.

Unlike `PERCENT_RANK()`, the **final peer group always has `CUME_DIST() = 1`**, because every row stands before or within the final group.

### 6.4. Single-row partition

```sql
SELECT
    segment,
    score,
    CUME_DIST() OVER (PARTITION BY segment ORDER BY score) AS cd
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

The result is **1**, because that single row accounts for the entire partition. This contrasts with `PERCENT_RANK() = 0` in the same situation.

## 7. Placing all three functions side by side on the same data

This is the core summary query of the lesson:

```sql
SELECT
    measure_id,
    score,
    RANK() OVER (ORDER BY score) AS rnk,
    NTILE(4) OVER (
        ORDER BY score, measure_id
    ) AS ntile_4,
    ROUND(
        (PERCENT_RANK() OVER (ORDER BY score))::numeric,
        4
    ) AS percent_rank,
    ROUND(
        (CUME_DIST() OVER (ORDER BY score))::numeric,
        4
    ) AS cume_dist
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

| measure_id | score | rnk | ntile_4 | percent_rank | cume_dist |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 50 | 1 | 1 | 0.0000 | 0.2500 |
| 102 | 50 | 1 | 1 | 0.0000 | 0.2500 |
| 103 | 70 | 3 | 2 | 0.2857 | 0.3750 |
| 104 | 90 | 4 | 2 | 0.4286 | 0.7500 |
| 105 | 90 | 4 | 3 | 0.4286 | 0.7500 |
| 106 | 90 | 4 | 3 | 0.4286 | 0.7500 |
| 107 | 110 | 7 | 4 | 0.8571 | 0.8750 |
| 108 | 140 | 8 | 4 | 1.0000 | 1.0000 |

Three key conclusions:

1. **NTILE:** aims for roughly equal row counts per bucket, so 90-point rows can be split apart.
2. **PERCENT_RANK:** uses the **start** position of the tied group via `RANK`, so all three 90s get 0.4286.
3. **CUME_DIST:** uses the **end** position of the tied group, so all three 90s get 0.75.

### 7.1. Intuition diagram

```text
North, ascending score order:

Position:     1    2    3    4    5    6    7    8
Score:       50   50   70   90   90   90  110  140
NTILE(4):     1    1    2    2    3    3    4    4

The 90 group occupies positions 4,5,6:
  RANK starts at position 4.
  PERCENT_RANK = (4 - 1) / (8 - 1) = 3/7
  CUME_DIST    = 6 / 8 = 0.75
```

This diagram is handy when explaining outputs to a product owner or data analyst: identical scores landing in different `NTILE` buckets is not a PostgreSQL bug—it stems from **different metric definitions**.

## 8. Verifying formulas using RANK, COUNT, and peer count

We can reconstruct `PERCENT_RANK` and `CUME_DIST` from formulas to see how they work:

```sql
WITH positions AS (
    SELECT
        measure_id,
        segment,
        score,
        RANK() OVER (
            PARTITION BY segment ORDER BY score
        ) AS rank_position,
        COUNT(*) OVER (
            PARTITION BY segment
        ) AS n,
        COUNT(*) OVER (
            PARTITION BY segment, score
        ) AS peer_count
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT
    measure_id,
    segment,
    score,
    rank_position,
    n,
    peer_count,
    CASE
        WHEN n = 1 THEN 0::numeric
        ELSE (rank_position - 1)::numeric / (n - 1)
    END AS manual_percent_rank,
    (rank_position + peer_count - 1)::numeric / n
        AS manual_cume_dist
FROM positions
ORDER BY segment, score, measure_id;
```

Explanation:

- `rank_position - 1` is the count of positions before the peer group starts.
- `rank_position + peer_count - 1` is the ending row position of the peer group.
- `n` is the number of observations compared within the segment.
- `CASE WHEN n = 1 THEN 0` handles single-observation partitions without division by zero.

For north, the 90-point peer group has `rank_position=4`, `peer_count=3`, `n=8`. Thus:

```text
manual_percent_rank = (4 - 1) / (8 - 1) = 3/7
manual_cume_dist    = (4 + 3 - 1) / 8 = 6/8
```

Remember that `COUNT(*) OVER (PARTITION BY segment, score)` accurately matches the peer group only because the ranking function here also sorts **solely by `score`** within each segment. If the ranking `ORDER BY` changes, the peer-count expression must change too.

## 9. PARTITION BY: computing distributions per group

When you want to evaluate a score **against peers in the same region** rather than the whole company, use `PARTITION BY segment`.

```sql
SELECT
    measure_id,
    segment,
    score,
    COUNT(*) OVER (
        PARTITION BY segment
    ) AS segment_size,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score ASC, measure_id ASC
    ) AS score_bucket,
    ROUND(
        (PERCENT_RANK() OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ))::numeric,
        4
    ) AS relative_position,
    ROUND(
        (CUME_DIST() OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ))::numeric,
        4
    ) AS cumulative_share
FROM distribution_lab.measurements
ORDER BY segment, score, measure_id;
```

Each `segment` is evaluated independently. Specifically:

- **north (8 rows):** `NTILE(4)` creates four buckets of two rows each.
- **south (5 rows):** buckets have sizes 2, 1, 1, 1.
- **pilot (1 row):** `score_bucket=1`, `relative_position=0`, `cumulative_share=1`.

### 9.1. Manual calculation for south

South has scores `30, 30, 40, 80, 100`:

| measure_id | score | ntile_4 | percent_rank | cume_dist |
| ---: | ---: | ---: | ---: | ---: |
| 201 | 30 | 1 | 0.0000 | 0.4000 |
| 202 | 30 | 1 | 0.0000 | 0.4000 |
| 203 | 40 | 2 | 0.5000 | 0.6000 |
| 204 | 80 | 3 | 0.7500 | 0.8000 |
| 205 | 100 | 4 | 1.0000 | 1.0000 |

Score 40 has `rank=3`, so `percent_rank=(3-1)/(5-1)=0.5`; three out of five observations do not exceed 40, so `cume_dist=3/5=0.6`.

### 9.2. Group-level comparison vs. global comparison

A score of 95 in pilot beats most people in north/south. Yet because pilot has only one row, its `PERCENT_RANK() OVER (PARTITION BY segment)` equals 0.

This is not a contradiction: one metric measures standing **within pilot**, whereas global comparison is a separate query. Whenever publishing percentiles, always state the **reference population**.

### 9.3. PARTITION BY does not require a physically partitioned table

Window `PARTITION BY` only divides rows **logically for evaluation**. It is not PostgreSQL table partitioning, nor does it create subtables or indexes.

Never confuse "grouping calculation by segment" with partitioned tables used for storage management and partition pruning.

## 10. ORDER BY ASC and DESC: sort direction reverses meaning

With `ORDER BY score ASC`:

- Lower scores come first.
- `NTILE(4)=1` is the lowest-scoring group.
- `PERCENT_RANK=0` attaches to the lowest score group.
- `CUME_DIST` equals the fraction of scores less than or equal to the current score.

With `ORDER BY score DESC`:

- Higher scores come first.
- `NTILE(4)=1` is the highest-scoring group.
- `PERCENT_RANK=0` attaches to the **highest score group**.
- `CUME_DIST` equals the fraction of rows standing before or tied in descending order—i.e., scores **greater than or equal to** the current score.

Example:

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (
        ORDER BY score DESC, measure_id
    ) AS high_first_bucket,
    ROUND(
        (PERCENT_RANK() OVER (ORDER BY score DESC))::numeric,
        4
    ) AS high_first_percent_rank,
    ROUND(
        (CUME_DIST() OVER (ORDER BY score DESC))::numeric,
        4
    ) AS high_first_cume_dist
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score DESC, measure_id;
```

In north, score 140 leads: `high_first_bucket=1`, `high_first_percent_rank=0`, and `high_first_cume_dist=1/8=0.125`.

**Do not slap a generic label "higher percentile is better" onto a query ordered DESC.** Always state direction explicitly: relative position measured from the bottom up or from the top down.

## 11. When scores tie: NTILE and bucketing fairness

Suppose a bonus policy states:

> People with the exact same score must belong to the same reward tier.

If you run:

```sql
NTILE(4) OVER (ORDER BY score DESC, measure_id)
```

then whenever the 90-point group crosses a bucket boundary, people with equal scores land in different tiers. Adding `measure_id` makes the **split deterministic**, yet fails the requirement that **equal scores share the same tier**.

### 11.1. Option A: NTILE over DISTINCT score values

You can bucket **distinct score tiers** into four buckets and join back to each row:

```sql
WITH distinct_scores AS (
    SELECT DISTINCT segment, score
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
),
score_buckets AS (
    SELECT
        segment,
        score,
        NTILE(4) OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ) AS bucket_by_distinct_score
    FROM distinct_scores
)
SELECT
    m.measure_id,
    m.segment,
    m.score,
    b.bucket_by_distinct_score
FROM distribution_lab.measurements AS m
JOIN score_buckets AS b
    ON b.segment = m.segment
   AND b.score = m.score
ORDER BY m.segment, m.score, m.measure_id;
```

Now **every row with the same score in a segment gets the same bucket**. In trade-off, headcount per bucket can **vary widely**, because `NTILE` balances the count of **distinct score levels**, not people.

North has distinct levels `50, 70, 90, 110, 140`. Four buckets over distinct levels give:

```text
bucket 1: levels 50, 70  -> 3 people
bucket 2: level 90       -> 3 people
bucket 3: level 110      -> 1 person
bucket 4: level 140      -> 1 person
```

This satisfies peer preservation, though it is not the only valid rule. Choose bucketing policy per business needs.

### 11.2. Option B: percentile thresholds accepting uneven group sizes

If the rule is "everyone scoring at or above a threshold qualifies together", compute the threshold first and compare on **score**, instead of row-bucketing with `NTILE`.

For example, selecting everyone with `score >= 110`:

```sql
SELECT measure_id, score
FROM distribution_lab.measurements
WHERE segment = 'north'
  AND score >= 110
ORDER BY score DESC, measure_id;
```

Returns IDs 107 and 108. If multiple people score 110, all qualify together, even if the selected count exceeds a target quota.

With thresholds computed via `percentile_cont` or `percentile_disc`, also state clearly whether comparison is `>` or `>=`, and document that ties can exceed quota.

### 11.3. Option C: strict quota despite ties

If policy **mandates strictly K rows**, publish an explicit secondary tie-breaker: completion timestamp, secondary evaluation metric, or transparent lottery. Then `ROW_NUMBER()` or `NTILE` with full `ORDER BY` makes selection deterministic.

Acknowledge, however, that this introduces an **additional ranking rule** rather than "purely by score". Silently using a technical ID to break ties in HR or financial payouts can be unfair.

## 12. Are PERCENT_RANK and CUME_DIST "percentage of maximum score achieved"?

No. `0.8571` returned by `PERCENT_RANK()` **does not mean scoring 85.71% of the maximum scale**.

For north:

- Score 110: `PERCENT_RANK ≈ 0.8571`.
- Score 110: `CUME_DIST = 0.875`.

Both numbers reflect **the observation's position within the 8-row set**, not ratios like `110/140`, `110/100`, or any maximum score scale.

If `score` represents absolute revenue, these metrics describe **rank standing in the revenue distribution**, not share of total revenue. For "what percentage of total revenue does a customer contribute?", use `SUM(score)` over the group total and divide appropriately.

### 12.1. CUME_DIST vs. empirical CDF

With `ORDER BY score ASC` and no `NULL`s in `score`, `CUME_DIST(score)` matches the empirical cumulative distribution function at that score:

\[
\widehat F(s) = \frac{\#\{x_i \le s\}}{N}
\]

At score 90, `F(90) = 6/8 = 0.75`. This is useful when asking: **"What fraction of observations score no higher than this level?"**

`PERCENT_RANK` instead uses the **starting RANK of the peer group**, yielding ~0.4286 at 90. It does not return `F(90)` when tied values exist.

### 12.2. Boundary values

`PERCENT_RANK` of the first group is always 0. `CUME_DIST` of the last group is always 1. With many peers at the minimum score, `CUME_DIST` at the minimum can be quite large; that simply indicates **many observations share the minimum level**.

For example, south has two 30s out of 5 rows, so `CUME_DIST(30) = 2/5 = 0.4`, not 0.2.

## 13. Filtering by percent_rank or cume_dist

Window functions cannot appear directly in same-level `WHERE` such as:

```sql
-- Invalid:
-- SELECT measure_id, score
-- FROM distribution_lab.measurements
-- WHERE PERCENT_RANK() OVER (ORDER BY score) >= 0.75;
```

Reason: same-level `WHERE` is evaluated before window functions under SQL semantics. To **compute the group distribution first and then filter results**, use a CTE or subquery.

### 13.1. Selecting observations at the high end

```sql
WITH ranked AS (
    SELECT
        measure_id,
        segment,
        score,
        PERCENT_RANK() OVER (
            PARTITION BY segment
            ORDER BY score ASC
        ) AS pr
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT measure_id, segment, score, pr
FROM ranked
WHERE segment = 'north'
  AND pr >= 0.75
ORDER BY score DESC, measure_id;
```

North returns IDs 107 (110) and 108 (140). Yet **this is not a contract to "always return strictly 25% of rows"**. With ties or small segments, the count passing the threshold varies.

### 13.2. Picking the top group from NTILE

```sql
WITH bucketed AS (
    SELECT
        measure_id,
        segment,
        score,
        NTILE(4) OVER (
            PARTITION BY segment
            ORDER BY score DESC, measure_id ASC
        ) AS high_to_low_bucket
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT measure_id, segment, score
FROM bucketed
WHERE segment = 'north'
  AND high_to_low_bucket = 1
ORDER BY score DESC, measure_id;
```

For north with 8 rows, the top bucket holds the two highest scores 140 and 110. For south with 5 rows, bucket 1 of `NTILE(4)` holds **two rows**—40%, not strictly 25%.

### 13.3. Selecting by cumulative share

```sql
WITH ranked AS (
    SELECT
        measure_id,
        segment,
        score,
        CUME_DIST() OVER (
            PARTITION BY segment
            ORDER BY score DESC
        ) AS top_cumulative_share
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
)
SELECT measure_id, segment, score, top_cumulative_share
FROM ranked
WHERE segment = 'north'
  AND top_cumulative_share <= 0.25
ORDER BY score DESC, measure_id;
```

This selects **peer groups whose cumulative share does not exceed 25%** counting from highest score downward. In north, that yields 140 and 110.

If a large peer group pushes the cumulative share from below 25% to above 25%, the entire group is **excluded** by `<= 0.25`. Thus the result may return **fewer** rows than a target quota, unlike `NTILE`'s ~25%.

## 14. Filtering before vs. after window functions

When applying `WHERE` **in the same `SELECT` as a window function**, PostgreSQL computes the window over **rows surviving the filter**.

Example:

```sql
SELECT
    measure_id,
    score,
    PERCENT_RANK() OVER (ORDER BY score) AS pr_among_high_scores
FROM distribution_lab.measurements
WHERE segment = 'north'
  AND score >= 90
ORDER BY score, measure_id;
```

Here the distribution has only **five rows**: 90, 90, 90, 110, 140. The 90 group gets `pr=0` because it is the lowest group in the filtered set.

Different query:

```sql
WITH ranked_north AS (
    SELECT
        measure_id,
        score,
        PERCENT_RANK() OVER (ORDER BY score) AS pr_in_full_north
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT measure_id, score, pr_in_full_north
FROM ranked_north
WHERE score >= 90
ORDER BY score, measure_id;
```

Here the 90 group still gets `pr ≈ 0.428571` because `percent_rank` was computed **across all eight north rows before filtering for display**.

Both queries return the exact same `score >= 90` rows, yet **different `percent_rank` values**. When writing reports, always state the reference cohort clearly: all customers, active customers only, paid transactions only, or records within a date window?

### 14.1. Data can be multiplied by a JOIN before the window

If you join each customer to three orders and run `PERCENT_RANK()` on the joined rows, frequent buyers appear multiple times and **skew the distribution**.

To compare **one row per customer** by total spend, aggregate revenue to one row per customer first, then run the window. Never slap `DISTINCT` onto a broken-grain query as an ad-hoc fix.

## 15. How do NULLs affect distributions?

In the lab table, `score` allows `NULL` though sample rows all have scores. This lets us examine a common scenario in incomplete datasets.

### 15.1. PostgreSQL still sorts NULLs

PostgreSQL defaults:

- `ORDER BY score ASC`: `NULL` sits **last** (default `NULLS LAST`).
- `ORDER BY score DESC`: `NULL` sits **first** (default `NULLS FIRST`).

You can write explicitly:

```sql
SELECT measure_id, segment, score
FROM distribution_lab.measurements
ORDER BY score DESC NULLS LAST, measure_id;
```

If `NULL` means "not yet scored" rather than a very high score, specify `NULLS LAST` or exclude ungraded rows before computing distributions per business rules.

### 15.2. Ranking functions do not skip NULLs automatically

Test on temporary data:

```sql
WITH sample(id, score) AS (
    VALUES
        (1, 10::numeric),
        (2, NULL::numeric),
        (3, NULL::numeric)
)
SELECT
    id,
    score,
    RANK() OVER (
        ORDER BY score ASC NULLS LAST
    ) AS rnk,
    PERCENT_RANK() OVER (
        ORDER BY score ASC NULLS LAST
    ) AS pr,
    CUME_DIST() OVER (
        ORDER BY score ASC NULLS LAST
    ) AS cd
FROM sample
ORDER BY score ASC NULLS LAST, id;
```

In this order:

| id | score | rnk | pr | cd |
| ---: | --- | ---: | ---: | ---: |
| 1 | 10 | 1 | 0 | 1/3 |
| 2 | NULL | 2 | 0.5 | 1 |
| 3 | NULL | 2 | 0.5 | 1 |

Both `NULL`s are peers at the end because the window's `ORDER BY` treats them as equal sort keys. That **does not mean both entities had the same actual score**; both merely lack data.

### 15.3. Recommendations for handling missing data

If percentiles are meaningful only for known scores:

```sql
SELECT
    measure_id,
    segment,
    score,
    PERCENT_RANK() OVER (
        PARTITION BY segment ORDER BY score
    ) AS pr
FROM distribution_lab.measurements
WHERE score IS NOT NULL;
```

If ungraded entities must remain visible in the report, compute distributions over scored rows and `LEFT JOIN` results back to the full roster; missing entities get SQL `NULL` or a distinct status for percentile, **never 0**.

Only treat `NULL` as score 0 if that is genuinely the business definition. Never mechanically apply `COALESCE` to turn `NULL` into 0 before ranking.

## 16. Comparison with ROW_NUMBER, RANK, and DENSE_RANK

Other functions in the ranking family often studied together:

| Function | Meaning | Handles ties identically? |
| --- | --- | --- |
| `ROW_NUMBER()` | Assigns sequential numbers 1, 2, 3,... per row. | Distinct number per row; needs clear `ORDER BY` for stability on ties. |
| `RANK()` | Equal scores share rank; subsequent ranks **skip numbers**. | Yes. |
| `DENSE_RANK()` | Equal scores share rank; subsequent ranks **do not skip numbers**. | Yes. |
| `NTILE(n)` | Splits rows into roughly equal-count buckets. | Can split equal-score rows across buckets. |
| `PERCENT_RANK()` | Relative position derived from `RANK`. | Peers share the same value. |
| `CUME_DIST()` | Cumulative row fraction up to end of peer group. | Peers share the same value. |

Example:

```sql
SELECT
    measure_id,
    score,
    ROW_NUMBER() OVER (
        ORDER BY score, measure_id
    ) AS row_no,
    RANK() OVER (
        ORDER BY score
    ) AS rank_no,
    DENSE_RANK() OVER (
        ORDER BY score
    ) AS dense_rank_no
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

For north's score 90:

- Rows get `ROW_NUMBER` 4, 5, 6.
- All get `RANK=4`.
- All get `DENSE_RANK=3` because 90 is the third distinct score level.

Score 110 gets `RANK=7` yet `DENSE_RANK=4`.

### 16.1. Why is PERCENT_RANK based on RANK rather than DENSE_RANK?

`PERCENT_RANK` measures a **row's** position among all rows, not the index of a distinct value tier. Ties create gaps in `RANK`, which makes `(rank - 1)/(N - 1)` reflect the starting position of each peer group within all observations.

If business logic requires grading against **distinct score levels**, build a separate model—such as ranking distinct scores first and joining back to observations.

## 17. Difference between NTILE and true quantile thresholds

The word "quartile" is sometimes used ambiguously for:

1. **Four groups of people/rows with roughly equal counts**.
2. **Three threshold values Q1, Q2, Q3** dividing the value scale by distribution.

`NTILE(4)` solves the first problem. PostgreSQL provides ordered-set aggregates such as `percentile_cont` and `percentile_disc` for the second.

### 17.1. percentile_cont: interpolated percentile

```sql
SELECT
    percentile_cont(0.25)
        WITHIN GROUP (ORDER BY score::double precision) AS p25,
    percentile_cont(0.50)
        WITHIN GROUP (ORDER BY score::double precision) AS median,
    percentile_cont(0.75)
        WITHIN GROUP (ORDER BY score::double precision) AS p75
FROM distribution_lab.measurements
WHERE segment = 'north';
```

On north with ascending scores `50,50,70,90,90,90,110,140`:

- Interpolated median `p50 = 90`.
- `p75` interpolates between position 6 (90) and 7 (110), giving **95** under PostgreSQL's `percentile_cont` rules.

`percentile_cont` returns a **single threshold value** (or array of values if given an array of fractions), not one row per person like `PERCENT_RANK`.

Understand data types and interpolation methods. This example casts to `double precision` to match the common ordered-set aggregate overload; for exact decimal currency outputs, verify system representation and rounding rules.

### 17.2. percentile_disc: discrete percentile

```sql
SELECT
    percentile_disc(0.25)
        WITHIN GROUP (ORDER BY score) AS p25_discrete,
    percentile_disc(0.50)
        WITHIN GROUP (ORDER BY score) AS median_discrete,
    percentile_disc(0.75)
        WITHIN GROUP (ORDER BY score) AS p75_discrete
FROM distribution_lab.measurements
WHERE segment = 'north';
```

`percentile_disc` picks an **actual value present in the data** at the cumulative threshold. For north:

```text
p25_discrete = 50
median_discrete = 90
p75_discrete = 90
```

Compared to `percentile_cont(0.75)=95`, `percentile_disc(0.75)=90`. Both answers differ yet both are right under **two distinct quantile definitions**.

### 17.3. Aggregating per segment

```sql
SELECT
    segment,
    COUNT(score) AS scored_rows,
    percentile_disc(0.5)
        WITHIN GROUP (ORDER BY score) AS median_score
FROM distribution_lab.measurements
GROUP BY segment
ORDER BY segment;
```

Result on sample data:

| segment | scored_rows | median_score |
| --- | ---: | ---: |
| north | 8 | 90 |
| pilot | 1 | 95 |
| south | 5 | 40 |

Never equate `median_score` with a row's `PERCENT_RANK=0.5`. One is a **score value at a quantile**, while the other is a **score's relative position**.

### 17.4. Why do percentile_cont and percentile_disc not use OVER like NTILE?

In PostgreSQL, `percentile_cont` and `percentile_disc` are ordered-set aggregates written with `WITHIN GROUP (ORDER BY ...)` to compute thresholds over an aggregated set. Their standard usage **differs from ranking window functions** `NTILE`, `PERCENT_RANK`, and `CUME_DIST`.

To attach a per-segment quantile threshold onto each observation, compute the threshold in an aggregate CTE and `JOIN` it back:

```sql
WITH limits AS (
    SELECT
        segment,
        percentile_disc(0.75)
            WITHIN GROUP (ORDER BY score) AS p75_score
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
    GROUP BY segment
)
SELECT
    m.measure_id,
    m.segment,
    m.score,
    l.p75_score,
    m.score >= l.p75_score AS meets_p75_threshold
FROM distribution_lab.measurements AS m
JOIN limits AS l
    ON l.segment = m.segment
WHERE m.score IS NOT NULL
ORDER BY m.segment, m.score, m.measure_id;
```

With `>= p75_score`, ties right at the threshold can qualify more than 25% of rows—a natural consequence of **keeping tied scores together**.

## 18. NTILE vs. WIDTH_BUCKET and histograms

A histogram uses fixed **value** intervals, whereas `NTILE` uses buckets by **row position**.

For example, splitting `[0,160)` into four bins of width 40:

```sql
SELECT
    measure_id,
    score,
    width_bucket(score, 0::numeric, 160::numeric, 4)
        AS fixed_width_bucket,
    NTILE(4) OVER (
        ORDER BY score, measure_id
    ) AS equal_count_bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Fixed intervals:

```text
width_bucket = 1: [  0,  40)
width_bucket = 2: [ 40,  80)
width_bucket = 3: [ 80, 120)
width_bucket = 4: [120, 160)
```

For north:

- Fixed-width bucket 1: 0 rows.
- Fixed-width bucket 2: 3 rows (50, 50, 70).
- Fixed-width bucket 3: 4 rows (90, 90, 90, 110).
- Fixed-width bucket 4: 1 row (140).

Meanwhile `NTILE(4)` produces 2–2–2–2 rows. The two approaches solve different statistical tasks.

### 18.1. width_bucket with out-of-range values

With `width_bucket(value, lower, upper, count)` and `lower < upper`, PostgreSQL returns bucket **0** when value is below the lower bound and **count + 1** when greater than or equal to the upper bound.

Try:

```sql
SELECT
    width_bucket(-1::numeric, 0::numeric, 160::numeric, 4) AS below,
    width_bucket(50::numeric, 0::numeric, 160::numeric, 4) AS inside,
    width_bucket(160::numeric, 0::numeric, 160::numeric, 4) AS at_upper;
```

Results are `0`, `2`, and `5` respectively. When building a histogram, decide whether to filter out-of-range values, create overflow buckets, or display them separately.

### 18.2. Counting observations per fixed bin

```sql
WITH histogram AS (
    SELECT
        width_bucket(score, 0::numeric, 160::numeric, 4) AS bucket,
        COUNT(*) AS observations
    FROM distribution_lab.measurements
    WHERE segment = 'north'
      AND score >= 0
      AND score < 160
    GROUP BY 1
)
SELECT
    b.bucket,
    COALESCE(h.observations, 0) AS observations
FROM generate_series(1, 4) AS b(bucket)
LEFT JOIN histogram AS h
    ON h.bucket = b.bucket
ORDER BY b.bucket;
```

Result: `0, 3, 4, 1` observations across the four bins. `generate_series` ensures empty bins still appear, which is convenient for reporting.

## 19. Tiering customers by total spend

A popular use of `NTILE` is segmenting customers by **lifetime spending** or periodic revenue:

```text
orders -----------+
                  |
              SUM(amount)
                  |
                  v
           customer_spending
                  |
                  v
             NTILE(4)
                  |
                  v
        low -> high value groups
```

Crucially, the input must have **one row per customer**. Running `NTILE` directly on `orders` makes multi-order customers appear multiple times and distorts the **customer** distribution.

### 19.1. Self-contained simulated dataset

Without creating new tables, use a `VALUES` CTE:

```sql
WITH customer_spending(customer_id, segment, total_spent) AS (
    VALUES
        (1, 'retail',  120::numeric),
        (2, 'retail',  450::numeric),
        (3, 'retail',  450::numeric),
        (4, 'retail',  900::numeric),
        (5, 'retail', 1100::numeric),
        (6, 'retail', 1400::numeric),
        (7, 'retail', 1900::numeric),
        (8, 'retail', 2500::numeric)
),
segmented AS (
    SELECT
        customer_id,
        segment,
        total_spent,
        NTILE(4) OVER (
            PARTITION BY segment
            ORDER BY total_spent DESC, customer_id
        ) AS spending_tier,
        CUME_DIST() OVER (
            PARTITION BY segment
            ORDER BY total_spent DESC
        ) AS top_share
    FROM customer_spending
)
SELECT
    customer_id,
    total_spent,
    spending_tier,
    top_share
FROM segmented
ORDER BY spending_tier, total_spent DESC, customer_id;
```

With eight customers:

- Tier 1: highest spenders, customers with 2500 and 1900.
- Tier 2: next two customers with 1400 and 1100.
- Tier 3: 900 and one of the two 450 customers, per the declared tie-breaker.
- Tier 4: the remaining 450 customer and customer 120.

Because of `ORDER BY total_spent DESC, customer_id`, between two customers spending 450, `customer_id=2` precedes customer 3. That is a **technical tie-breaker**, not necessarily fair if tiers grant privileges.

### 19.2. When customers have no orders yet

Clarify whether "customers with zero orders" count as 0 spend or are excluded from the cohort. Example pattern:

```sql
WITH customers(customer_id) AS (
    VALUES (1), (2), (3), (4)
),
orders(order_id, customer_id, amount) AS (
    VALUES
        (11, 1, 100::numeric),
        (12, 1, 200::numeric),
        (13, 3,  50::numeric)
),
spending AS (
    SELECT
        c.customer_id,
        COALESCE(SUM(o.amount), 0) AS total_spent
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
    GROUP BY c.customer_id
)
SELECT
    customer_id,
    total_spent,
    NTILE(4) OVER (
        ORDER BY total_spent DESC, customer_id
    ) AS tier
FROM spending
ORDER BY tier;
```

This keeps customers 2 and 4 (with no orders) at `total_spent=0`. Using an `INNER JOIN` before aggregating would drop them from the segmentation cohort.

### 19.3. Customers with multiple transaction types

In real systems, specify clearly:

- Are pending orders included?
- How do refunds and cancellations reduce totals?
- Is total spend pre-tax or post-tax?
- Is tiering evaluated monthly, quarterly, or lifetime?
- Do multiple currencies require conversion to a single unit?
- Are multi-account customers merged?

`NTILE` only processes the **order and row count of its input metric**. If the input metric lacks accurate business semantics, tiers cannot fix it.

## 20. Evaluations, exam scores, and SLAs

### 20.1. Higher score is better

When high scores indicate strong performance:

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (
        ORDER BY score DESC, measure_id
    ) AS performance_tier
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY performance_tier, score DESC, measure_id;
```

Tier 1 is the top-performing group. If you want "fraction of exams scoring at or below X", use `CUME_DIST() OVER (ORDER BY score ASC)`.

### 20.2. Lower latency is better

If `score` represents latency in milliseconds, **lower is better**. On the same metric:

```sql
SELECT
    measure_id,
    score AS latency_ms,
    NTILE(4) OVER (
        ORDER BY score ASC, measure_id
    ) AS best_latency_tier,
    CUME_DIST() OVER (
        ORDER BY score ASC
    ) AS latency_cdf
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY latency_ms, measure_id;
```

Tier 1 is now the lowest-latency group. `latency_cdf` gives the fraction of observations with latency no higher than the current value. When defining a p95 latency SLO, teams usually need the **95th-percentile latency threshold**, computed via `percentile_cont(0.95)` or histogram metrics—not finding `PERCENT_RANK()=0.95` and treating it as milliseconds.

### 20.3. Small populations yield hard-to-interpret numbers

A single-person segment always receives `PERCENT_RANK=0` and `CUME_DIST=1`, yet this provides **no reliable relative performance signal**. Two-row segments exhibit huge step jumps.

When building dashboards, display `COUNT(*) OVER (PARTITION BY segment)` alongside percentiles and enforce a minimum sample-size threshold before publishing comparative rankings.

## 21. Naming a WINDOW when repeating the same definition

PostgreSQL supports the `WINDOW` clause to name a frequently reused window:

```sql
SELECT
    measure_id,
    segment,
    score,
    RANK() OVER w AS rnk,
    PERCENT_RANK() OVER w AS pr,
    CUME_DIST() OVER w AS cd
FROM distribution_lab.measurements
WHERE score IS NOT NULL
WINDOW w AS (
    PARTITION BY segment
    ORDER BY score ASC
)
ORDER BY segment, score, measure_id;
```

Benefits:

- Eliminates repeating `PARTITION BY segment ORDER BY score ASC`.
- Guarantees `RANK`, `PERCENT_RANK`, and `CUME_DIST` share the **exact same peer groups**.
- Improves readability when multiple metrics share population and order.

However, if `NTILE` needs secondary key `measure_id` to break ties while `PERCENT_RANK` must preserve peers on `score`, declare **two distinct windows**:

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER w_bucket AS bucket,
    PERCENT_RANK() OVER w_peers AS pr,
    CUME_DIST() OVER w_peers AS cd
FROM distribution_lab.measurements
WHERE score IS NOT NULL
WINDOW
    w_bucket AS (
        PARTITION BY segment
        ORDER BY score, measure_id
    ),
    w_peers AS (
        PARTITION BY segment
        ORDER BY score
    )
ORDER BY segment, score, measure_id;
```

**Different window names reflect two distinct intents**, not wasteful duplication.

## 22. Do window frames affect these three functions?

An `OVER` clause can also specify a *window frame*, such as `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Frames are crucial for functions like `SUM(...) OVER (...)`, `FIRST_VALUE`, or `LAST_VALUE`.

However, `NTILE`, `PERCENT_RANK`, and `CUME_DIST` inherently evaluate over the **entire partition and `ORDER BY` peer groups**, not a shrinking frame like a rolling sum.

Test two different metrics in the same query:

```sql
SELECT
    measure_id,
    score,
    SUM(score) OVER (
        ORDER BY score, measure_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum,
    CUME_DIST() OVER (
        ORDER BY score
    ) AS cumulative_row_fraction
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

`running_sum` adds **score values** from the start up to the current row according to the frame. `cumulative_row_fraction` counts the **fraction of rows** up to the end of the peer group. Even though both are labeled "cumulative" in reports, their units and semantics are completely different.

### 22.1. Default frames and ties

For many window aggregates when `ORDER BY` is present without an explicit frame, PostgreSQL uses the default frame including peers up to the current row per SQL rules. Consequently `SUM(score) OVER (ORDER BY score)` jumps across the entire 90-point group rather than incrementing row by row in ID order.

For a per-row running sum, specify `ROWS ...` with a tie-broken `ORDER BY`. Never use a frame-affected running sum as evidence that `CUME_DIST` is miscalculating.

## 23. Reading EXPLAIN and optimizing distribution queries

Window functions generally require sorting rows by partition and order keys, so costs can be substantial on millions of rows.

```sql
EXPLAIN
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score, measure_id
    ) AS bucket
FROM distribution_lab.measurements
WHERE score IS NOT NULL;
```

The plan may show `WindowAgg`, `Sort`, index scans, or other nodes depending on data and PostgreSQL version.

### 23.1. Indexes aligned with partition/order

An index that can help workloads frequently computing distributions by segment and score:

```sql
CREATE INDEX idx_measurements_segment_score_id
ON distribution_lab.measurements (
    segment,
    score,
    measure_id
);
```

A matching index can supply rows in a helpful order or reduce sort work. However, **there is no guarantee every window query will use the index**, especially when filters match most of the table, data is small, or multiple windows use different sort orders.

To evaluate empirically:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score, measure_id
    ) AS bucket
FROM distribution_lab.measurements
WHERE score IS NOT NULL;
```

`EXPLAIN ANALYZE` actually executes the `SELECT`, so weigh table size and production load before running it. A 14-row lab table does not reflect performance on 100 million rows.

### 23.2. Factors that commonly affect performance

1. **Population size:** input row count after `WHERE`, `JOIN`, and `GROUP BY`.
2. **Partition count:** many tiny partitions behave differently from one massive partition.
3. **Window orderings:** multiple windows with distinct `ORDER BY` clauses can increase sort steps.
4. **Indexes and statistics:** actual data layout and planner statistics drive plan choices.
5. **work_mem and spills:** `Sort`/`WindowAgg` consume memory; large workloads can spill to temporary files.
6. **Returned row count:** avoid shipping entire tables over the network when only top tiers are needed.
7. **Pre-window JOIN cost:** a fan-out join both corrupts metrics and inflates cost.

### 23.3. Outer LIMIT does not shrink the partition

```sql
SELECT
    measure_id,
    score,
    PERCENT_RANK() OVER (ORDER BY score) AS pr
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score
LIMIT 3;
```

To compute a row's percent rank, PostgreSQL semantically evaluates the **entire partition in the specified order**, not just the three displayed rows. `LIMIT 3` at the end does not alter the window function's denominator `N`.

If you only want the three lowest-scoring individuals **without needing percentiles**, drop the window function and use plain `ORDER BY ... LIMIT 3`, which can be dramatically lighter.

## 24. Data quality checks before analyzing distributions

Before trusting percentile metrics, check:

| Question | Consequence if ignored |
| --- | --- |
| What does one row represent? | Transaction distribution gets mistaken for customer distribution. |
| Are there duplicate records? | Duplicated entities exert multiple weights on the distribution. |
| What does `NULL` mean? | `NULL`s may sort first/last as if they were real values. |
| Are scores on the same scale? | Comparing 100 USD with 100 VND or mismatched latency types is wrong. |
| Is the cohort large enough? | Percentiles swing wildly and invite over-interpretation. |
| How should ties be handled? | `NTILE` may split equal scores across buckets. |
| Does the metric have outliers? | Equal-count buckets and value thresholds can diverge sharply. |
| Over which period is it partitioned? | Monthly rank may not represent annual rank. |
| Are there cancellation/refund policies? | Input revenue or scores may be business-inaccurate. |

Example checking row counts and distinct score levels:

```sql
SELECT
    segment,
    COUNT(*) AS total_rows,
    COUNT(score) AS nonnull_scores,
    COUNT(DISTINCT score) AS distinct_score_levels,
    MIN(score) AS min_score,
    MAX(score) AS max_score
FROM distribution_lab.measurements
GROUP BY segment
ORDER BY segment;
```

North has 8 rows yet only **5 distinct score levels**. That signals the need to check tie-handling policies when tiering rewards.

### 24.1. Diagnosing tied score groups

```sql
SELECT segment, score, COUNT(*) AS peer_size
FROM distribution_lab.measurements
WHERE score IS NOT NULL
GROUP BY segment, score
HAVING COUNT(*) > 1
ORDER BY segment, score;
```

Results show north 50 (2), north 90 (3), south 30 (2). This explains why `CUME_DIST` exhibits large jumps and why `NTILE` can split peers at boundaries.

## 25. Reading results from a Java application

In JDBC, window columns have SQL types:

- `NTILE(n)`: bucket number, best read as an integer.
- `PERCENT_RANK()` and `CUME_DIST()`: `double precision`, mappable to `double`/`Double` as needed.

Example SQL for a repository:

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score DESC, measure_id
    ) AS performance_bucket,
    PERCENT_RANK() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS relative_rank,
    CUME_DIST() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS cumulative_share
FROM distribution_lab.measurements
WHERE score IS NOT NULL
ORDER BY segment, performance_bucket, score DESC, measure_id;
```

If an API returns percentages, standardize scaling by 100 and rounding:

```sql
SELECT
    measure_id,
    ROUND(
        (
            100 * PERCENT_RANK() OVER (
                ORDER BY score
            )
        )::numeric,
        2
    ) AS percent_rank_percent
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

The value `85.71` here is a **relative rank expressed as a percentage per `percent_rank`**, not "achieved 85.71% of the business target".

### 25.1. Naming API fields to match exact semantics

Use explicit field names like:

- `score_quartile_bucket` for `NTILE(4)`.
- `score_percent_rank` for `PERCENT_RANK()`.
- `score_cumulative_fraction` for `CUME_DIST()`.
- `sample_size` for partition observation count.

Avoid an ambiguous `percentile` field without documenting formula, sort direction, cohort, `NULL` policy, and tie policy.

## 26. Common mistakes and fixes

### Mistake 1. Treating NTILE(4) as four equal-width score intervals

Wrong: each `NTILE` bucket has equal score range width. Right: `NTILE` balances **row counts**, not value widths. Use `width_bucket`/histograms for fixed score bins.

### Mistake 2. Assuming NTILE never splits tied scores

Wrong: all three 90-point rows in north stay in one bucket. In reality `NTILE(4)` puts one in bucket 2 and two in bucket 3 under deterministic ordering. If equal scores must stay in one tier, use score thresholds or bucket over distinct scores.

### Mistake 3. Omitting secondary keys from NTILE and expecting stable per-ID output

`NTILE(4) OVER (ORDER BY score)` leaves relative order among equal scores undefined. When peers cross a bucket boundary, a specific ID can shift buckets across plans or runs. Add a meaningful secondary criterion for reproducibility.

### Mistake 4. Adding ID to PERCENT_RANK to "fix ties"

Doing so turns every row into its own peer and **alters the statistic**. If business logic treats equal scores identically, keep only `ORDER BY score` in `PERCENT_RANK`.

### Mistake 5. Interpreting PERCENT_RANK as fraction of rows <= score

That is `CUME_DIST` in ascending order, not `PERCENT_RANK`. On north score 90, the two values are ~0.4286 and 0.75.

### Mistake 6. Assuming the highest score always gets PERCENT_RANK = 1

If the highest score has multiple peers, its value is less than 1. The function uses the peer group's starting rank, not the final row position.

### Mistake 7. Thinking CUME_DIST can equal 0

In any non-empty partition, `CUME_DIST` is strictly positive; even the first group contains at least one row.

### Mistake 8. Forgetting single-row partitions

When `N=1`, `PERCENT_RANK=0` and `CUME_DIST=1`. Never treat this as absolute performance evidence over a tiny sample.

### Mistake 9. Sorting DESC yet labeling output "percentage of people scoring lower"

`CUME_DIST() OVER (ORDER BY score DESC)` accumulates from highest score downward, not lowest upward. Always state direction.

### Mistake 10. Filtering before the window and calling it the overall distribution

`WHERE score >= 90` in the window query alters `N` and all ranks. To compute over the full cohort and filter output display, use a CTE/subquery.

### Mistake 11. Ranking on a table with multiple transactions per customer

To rank customers, aggregate to one row per customer first. Ranking per order ranks **orders**, not **customers**.

### Mistake 12. Forgetting NULLS FIRST/LAST

In PostgreSQL, default `DESC` places `NULL`s first. If `NULL` means unknown score, it should not silently top the leaderboard; filter out or specify explicit `NULL` semantics.

### Mistake 13. Confusing percentile_cont with percent_rank

`percentile_cont(0.75)` returns a **value threshold at a quantile**. `PERCENT_RANK()` returns **each row's relative rank position**. Their units are completely different.

### Mistake 14. Assuming percent_rank >= 0.75 always selects 25% of people

With ties, small samples, or peer boundaries, the row count qualifying can differ sharply from 25%. For a strict quota, pick rows with an explicit, fair tie-breaker.

### Mistake 15. Using DISTINCT before a window without clarity

`SELECT DISTINCT score` shifts the population from **observations** to **distinct score tiers**. Percentiles over distinct levels are no longer percentiles over all individuals.

### Mistake 16. Assuming ORDER BY inside OVER guarantees output order

The window's `ORDER BY` governs evaluation order; guaranteed output order requires an outer query `ORDER BY`.

### Mistake 17. Confusing frames with partitions

`NTILE`, `PERCENT_RANK`, and `CUME_DIST` do not use frames like a running `SUM`. Changing the frame clause will not make `percent_rank`'s denominator equal the "last 5 rows".

### Mistake 18. Reading metrics without specifying the cohort

North's `PERCENT_RANK` differs from company-wide `PERCENT_RANK`. A decimal without population and period context is meaningless.

### Mistake 19. Treating percent_rank decimals as absolute business precision

With small sample sizes or skewed data, ranks jump sharply. Never treat a two-decimal rank as high-precision evidence without sample-size context.

### Mistake 20. Creating indexes without measuring on real data

Indexes can assist `PARTITION BY/ORDER BY`, yet the optimizer still weighs scans, sorts, memory, and table size. Measure with `EXPLAIN (ANALYZE, BUFFERS)` on realistic workloads.

## 27. Practice exercises

The exercises below use `distribution_lab.measurements` from Section 2. A few use `VALUES` and run standalone. Compare manual calculations against PostgreSQL results; all examples are read-only and do not alter tables.

### Exercise 1. Basic NTILE

Write a query selecting only `north`, returning `measure_id`, `score`, and `NTILE(4)` ordered by score ascending, breaking ties by ID ascending. Predict the buckets of 104, 105, and 106.

### Exercise 2. NTILE with non-divisible row count

Test `NTILE(3)` on north's eight rows. What are the sizes of the three buckets in order?

### Exercise 3. NTILE with more buckets than rows

Test `NTILE(4)` on the single-observation `pilot` partition. Which bucket numbers appear?

### Exercise 4. Manual PERCENT_RANK

For north, calculate `PERCENT_RANK` of scores 70 and 110 using `RANK` and `N`.

### Exercise 5. Manual CUME_DIST

For north, calculate `CUME_DIST` of scores 50, 90, and 140. Explain why score 90 jumps from 0.375 to 0.75.

### Exercise 6. Single-row partition

Write a query computing `NTILE(4)`, `PERCENT_RANK`, and `CUME_DIST` on `pilot`. Predict all three values.

### Exercise 7. PARTITION BY

Write a query computing all three metrics per segment, ordered by `segment, score, measure_id`. Predict south's score 40.

### Exercise 8. Descending order

On north, use `ORDER BY score DESC`. What are `PERCENT_RANK` and `CUME_DIST` for the highest score 140?

### Exercise 9. Reasoning about ties

Why can `NTILE(4)` place north's three 90s into two buckets? Should ID be used as a tie-breaker if buckets decide bonuses?

### Exercise 10. Keeping tied scores together

Write a CTE selecting `DISTINCT segment, score`, run `NTILE(4)` over the distinct score levels, then `JOIN` back to `measurements`. Do all three rows with score 90 in north receive the same bucket?

### Exercise 11. Post-window filtering

Compute `PERCENT_RANK` across all of north, then show only rows with `score >= 90`. Compare with placing `score >= 90` in `WHERE` before window evaluation.

### Exercise 12. CUME_DIST and fraction <= threshold

Write a query returning the cumulative share at score 90 in north. Explain why it equals 6/8.

### Exercise 13. NULLS LAST

Use a `VALUES` CTE with scores `10, NULL, NULL` to compare `PERCENT_RANK` and `CUME_DIST` under `ORDER BY score ASC NULLS LAST`. If scores are missing, what should you do before publishing rankings?

### Exercise 14. 75th percentile

Compute `percentile_cont(0.75)` and `percentile_disc(0.75)` for north. Explain why the two numbers differ.

### Exercise 15. Comparison with WIDTH_BUCKET

Split north scores into four bins `[0,40)`, `[40,80)`, `[80,120)`, `[120,160)`. Count rows per bin; compare against `NTILE(4)` bucket sizes.

### Exercise 16. Top 25% in different ways

On north, compare:

- `NTILE(4) OVER (ORDER BY score DESC, measure_id) = 1`.
- `CUME_DIST() OVER (ORDER BY score DESC) <= 0.25`.

In the sample data, which rows does each select? If a huge 90-point group sits at the boundary, are both guaranteed to match?

### Exercise 17. RANK and DENSE_RANK

For north, compute `RANK` and `DENSE_RANK` for scores 90 and 110. Why do the two functions give different numbers?

### Exercise 18. Checking sample size

Write a query returning each row alongside `COUNT(*) OVER (PARTITION BY segment)`. Why should sample size be shown next to percentiles?

### Exercise 19. Customer-grain metric

An orders table has multiple orders per customer. Sketch SQL using `GROUP BY customer_id` to compute `SUM(amount)` and then `NTILE(4)` by total spend. Why not put `NTILE` directly on `orders`?

### Exercise 20. Unified dashboard query

Return `measure_id`, `segment`, `score`, `bucket` ordered by descending score and ID, `percent_rank` by descending score **without ID**, `cume_dist` by descending score, and `segment_size`. Include only non-NULL scores.

## 28. Solution hints

### Solution 1

```sql
SELECT
    measure_id,
    score,
    NTILE(4) OVER (ORDER BY score, measure_id) AS bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

ID 104 gets bucket 2; IDs 105 and 106 get bucket 3.

### Solution 2

```sql
SELECT
    measure_id,
    score,
    NTILE(3) OVER (ORDER BY score, measure_id) AS bucket
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score, measure_id;
```

Eight rows split into three buckets of sizes **3, 3, 2**.

### Solution 3

```sql
SELECT
    measure_id,
    NTILE(4) OVER (ORDER BY score, measure_id) AS bucket
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Only bucket **1** appears.

### Solution 4

`score=70` has rank 3 so `(3-1)/(8-1)=2/7 ≈ 0.285714`. `score=110` has rank 7 so `(7-1)/7=6/7 ≈ 0.857143`.

### Solution 5

By row count <= current score: score 50 gives `2/8=0.25`; score 90 gives `6/8=0.75`; score 140 gives `8/8=1`. The jump from 0.375 to 0.75 comes from having **three rows** tied at score 90.

### Solution 6

```sql
SELECT
    measure_id,
    NTILE(4) OVER (ORDER BY score) AS bucket,
    PERCENT_RANK() OVER (ORDER BY score) AS pr,
    CUME_DIST() OVER (ORDER BY score) AS cd
FROM distribution_lab.measurements
WHERE segment = 'pilot';
```

Result: `bucket=1`, `pr=0`, `cd=1`.

### Solution 7

```sql
SELECT
    measure_id,
    segment,
    score,
    NTILE(4) OVER (
        PARTITION BY segment ORDER BY score, measure_id
    ) AS bucket,
    PERCENT_RANK() OVER (
        PARTITION BY segment ORDER BY score
    ) AS pr,
    CUME_DIST() OVER (
        PARTITION BY segment ORDER BY score
    ) AS cd
FROM distribution_lab.measurements
ORDER BY segment, score, measure_id;
```

For south score 40 (ID 203): `bucket=2`, `pr=0.5`, `cd=0.6`.

### Solution 8

`score=140` leads under `DESC` order, so `PERCENT_RANK=0` and `CUME_DIST=1/8=0.125`. That position is measured **from the highest score downward**.

### Solution 9

`NTILE` balances row counts and therefore splits peers across boundaries. When buckets decide bonuses, never use an arbitrary technical ID without a published tie-breaker rule. Alternatively, adopt a score-tie-preserving policy accepting uneven group sizes.

### Solution 10

```sql
WITH distinct_scores AS (
    SELECT DISTINCT segment, score
    FROM distribution_lab.measurements
    WHERE score IS NOT NULL
),
buckets AS (
    SELECT
        segment, score,
        NTILE(4) OVER (
            PARTITION BY segment ORDER BY score
        ) AS bucket
    FROM distinct_scores
)
SELECT m.measure_id, m.segment, m.score, b.bucket
FROM distribution_lab.measurements AS m
JOIN buckets AS b
    ON b.segment = m.segment
   AND b.score = m.score
ORDER BY m.segment, m.score, m.measure_id;
```

All rows scoring 90 in north fall into **the same bucket 2** under distinct-score bucketing.

### Solution 11

```sql
WITH ranked AS (
    SELECT
        measure_id,
        score,
        PERCENT_RANK() OVER (ORDER BY score) AS pr
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT measure_id, score, pr
FROM ranked
WHERE score >= 90
ORDER BY score, measure_id;
```

Across all of north, score 90 has `pr=3/7`. If `score >= 90` filters **inside the window query**, 90 becomes the first group of the five-row set so `pr=0`.

### Solution 12

```sql
WITH ranked AS (
    SELECT
        score,
        CUME_DIST() OVER (ORDER BY score) AS cd
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT DISTINCT score, cd
FROM ranked
WHERE score = 90;
```

Result `0.75`, because six out of eight rows have score <= 90.

### Solution 13

```sql
WITH sample(id, score) AS (
    VALUES
        (1, 10::numeric),
        (2, NULL::numeric),
        (3, NULL::numeric)
)
SELECT
    id, score,
    PERCENT_RANK() OVER (
        ORDER BY score NULLS LAST
    ) AS pr,
    CUME_DIST() OVER (
        ORDER BY score NULLS LAST
    ) AS cd
FROM sample
ORDER BY score NULLS LAST, id;
```

`NULL`s form the final group, getting `pr=0.5` and `cd=1`. If ungraded records are ineligible for ranking, exclude `score IS NULL` before computing and display an "ungraded" status separately.

### Solution 14

```sql
SELECT
    percentile_cont(0.75)
        WITHIN GROUP (ORDER BY score::double precision)
        AS continuous_p75,
    percentile_disc(0.75)
        WITHIN GROUP (ORDER BY score)
        AS discrete_p75
FROM distribution_lab.measurements
WHERE segment = 'north';
```

Results **95** and **90**. `percentile_cont` interpolates between positions, whereas `percentile_disc` picks an actual existing value at the cumulative threshold.

### Solution 15

```sql
WITH counts AS (
    SELECT
        width_bucket(score, 0::numeric, 160::numeric, 4) AS bucket,
        COUNT(*) AS n
    FROM distribution_lab.measurements
    WHERE segment = 'north'
      AND score >= 0
      AND score < 160
    GROUP BY 1
)
SELECT b.bucket, COALESCE(c.n, 0) AS n
FROM generate_series(1, 4) AS b(bucket)
LEFT JOIN counts AS c ON c.bucket = b.bucket
ORDER BY b.bucket;
```

Fixed-width histogram counts are `0,3,4,1`; row-count `NTILE(4)` sizes are `2,2,2,2`.

### Solution 16

```sql
WITH ranked AS (
    SELECT
        measure_id,
        score,
        NTILE(4) OVER (
            ORDER BY score DESC, measure_id
        ) AS tile,
        CUME_DIST() OVER (
            ORDER BY score DESC
        ) AS cd
    FROM distribution_lab.measurements
    WHERE segment = 'north'
)
SELECT measure_id, score, tile, cd
FROM ranked
WHERE tile = 1 OR cd <= 0.25
ORDER BY score DESC, measure_id;
```

In north, both pick IDs 108 and 107. Yet when a peer group straddles the boundary, `NTILE` can split the group to approximate the quota, whereas `CUME_DIST` evaluates the entire peer group and may drop the whole group under `<=`.

### Solution 17

```sql
SELECT
    score,
    RANK() OVER (ORDER BY score) AS rnk,
    DENSE_RANK() OVER (ORDER BY score) AS dense_rnk
FROM distribution_lab.measurements
WHERE segment = 'north'
ORDER BY score;
```

Score 90 gets `RANK=4` and `DENSE_RANK=3`. Score 110 gets `RANK=7`, `DENSE_RANK=4`. `RANK` skips positions occupied by peers; `DENSE_RANK` counts only distinct score tiers.

### Solution 18

```sql
SELECT
    measure_id,
    segment,
    score,
    COUNT(*) OVER (
        PARTITION BY segment
    ) AS sample_size
FROM distribution_lab.measurements
ORDER BY segment, measure_id;
```

Percentiles on pilot `N=1` have no discriminatory power; on south `N=5` step sizes are also huge. Sample size helps readers interpret values responsibly.

### Solution 19

```sql
WITH spending AS (
    SELECT
        customer_id,
        SUM(amount) AS total_spent
    FROM some_orders
    WHERE status = 'completed'
    GROUP BY customer_id
)
SELECT
    customer_id,
    total_spent,
    NTILE(4) OVER (
        ORDER BY total_spent DESC, customer_id
    ) AS spending_tier
FROM spending;
```

`some_orders` here is a **hypothetical placeholder name to replace with a real table having matching columns**, not a table created in the lab. The `spending` CTE ensures one row per customer with completed orders before tiering.

### Solution 20

```sql
SELECT
    measure_id,
    segment,
    score,
    COUNT(*) OVER (
        PARTITION BY segment
    ) AS segment_size,
    NTILE(4) OVER (
        PARTITION BY segment
        ORDER BY score DESC, measure_id
    ) AS bucket,
    PERCENT_RANK() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS percent_rank,
    CUME_DIST() OVER (
        PARTITION BY segment
        ORDER BY score DESC
    ) AS cume_dist
FROM distribution_lab.measurements
WHERE score IS NOT NULL
ORDER BY segment, bucket, score DESC, measure_id;
```

`bucket` includes a secondary key for stable splits when scores tie; `percent_rank` and `cume_dist` order solely by `score` to preserve peers.

## 29. Checklist for picking the right function

Before shipping distribution metrics to a dashboard or decision logic:

1. **Clarify the question:** roughly equal-count buckets, relative rank position, or cumulative row fraction?
2. **Define the population:** whole company, per region, per period, or per role?
3. **Define the grain:** per person, per order, per transaction, or per measurement?
4. **Determine good/bad direction:** is high score better or low latency better?
5. **Specify tie policy:** can equal scores be split across tiers, or must they stay together?
6. **Specify NULL handling:** exclude, mark ineligible, or assign a value per business rules?
7. **Check partition sizes:** `N=1` and tiny `N` rarely produce meaningful quantiles.
8. **Check threshold vs. bucket:** score thresholds (`percentile_cont/disc`) differ from row-count buckets (`NTILE`).
9. **Filter at the right level:** compute ranks over the target population first, then filter display output if needed.
10. **Keep output ordered:** window `ORDER BY` and outer `ORDER BY` serve separate purposes.
11. **Measure performance:** on large tables, inspect `WindowAgg`, sorts, indexes, input row counts, and `JOIN` costs.
12. **Name metrics transparently:** document formula, population, period, direction, and tie policy.

## 30. Summary

`NTILE`, `PERCENT_RANK`, and `CUME_DIST` all support distribution analysis in PostgreSQL, yet **differ in purpose and calculation**:

- **`NTILE(n)`** divides rows in each partition into up to `n` roughly equal-sized buckets; with ties at a boundary, identical scores can be split across different buckets.
- **`PERCENT_RANK()`** returns relative position from `RANK` via `(rank-1)/(N-1)`, returning 0 when `N=1`. It uses the **starting position of the peer group**.
- **`CUME_DIST()`** returns the cumulative fraction of rows preceding or within the current peer group, divided by `N`. It uses the **ending position of the peer group**; the final group always gets 1.
- **`PARTITION BY`** defines independent comparison populations; **`ORDER BY`** determines ranking direction and peers. Adding an ID to `ORDER BY` stabilizes `NTILE`, yet alters `PERCENT_RANK`/`CUME_DIST` if they share the same window.
- **`percentile_cont` and `percentile_disc`** compute **quantile value thresholds**, unlike row-level positional metrics. **`width_bucket`** bins by fixed value width rather than equal observation counts.
- **`NULL`s, ties, sample size, grain, and `WHERE`** govern whether results are statistically and business-valid.

Concise selection rule: **to split a list into roughly equal-sized groups of rows, use `NTILE`; to find relative standing based on `RANK`, use `PERCENT_RANK`; to find the fraction of observations up to a score level, use `CUME_DIST`.** If the question is "what is the 75th-percentile score?", switch to `percentile_cont` or `percentile_disc` instead of looking for a row whose `percent_rank` is near 0.75 and treating it as the official threshold.
