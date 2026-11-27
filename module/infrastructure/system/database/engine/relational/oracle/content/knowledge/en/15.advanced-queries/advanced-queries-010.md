# MATCH_RECOGNIZE and Event Sequence Pattern Matching in Oracle Database

## 1. When a SQL Question Is Not Just "Which Rows to Filter?"

Many data problems require recognizing **an ordered sequence of events**, rather than merely finding individual rows that satisfy independent conditions. For example:

- An account starts a session, performs several payments, and then closes.
- A stock price rises consecutively over several sessions, then declines.
- A sensor exceeds a threshold three times before returning to normal range.
- An order transitions through states CREATED → PAID → SHIPPED.
- Detecting a sequence of failed logins followed by a successful login.
- Finding activity sessions consisting of a start event and an end event.

Some cases can be solved using self joins, analytic functions, correlated subqueries, or PL/SQL. However, when the rule is naturally expressed as **a pattern over a sequence of rows**, SQL written that way can become lengthy and hard to read.

Oracle provides the **`MATCH_RECOGNIZE`** clause for row pattern matching. You declare:

1. Which rows belong to the same sequence via `PARTITION BY`.
2. Event order via `ORDER BY`.
3. The pattern to match via `PATTERN`.
4. Conditions for assigning a row to a pattern variable via `DEFINE`.
5. Values to output via `MEASURES`.
6. Where to continue searching for the next match via `AFTER MATCH SKIP`.

`MATCH_RECOGNIZE` was introduced in Oracle Database 12c and is available in Oracle Database 19c. This lesson uses 19c syntax.

## 2. Core Idea: Viewing Data as a Sequence

Suppose a transactions table contains:

| ACCOUNT_ID | EVENT_TIME | EVENT_TYPE | AMOUNT |
| ---: | --- | --- | ---: |
| 10 | 09:00 | START | NULL |
| 10 | 09:10 | PAYMENT | 100 |
| 10 | 09:20 | PAYMENT | 50 |
| 10 | 09:30 | CLOSE | NULL |
| 10 | 10:00 | START | NULL |
| 10 | 10:05 | PAYMENT | 30 |
| 10 | 10:15 | CLOSE | NULL |

The goal is to find each session matching the structure:

~~~text
START → PAYMENT (zero or more) → CLOSE
~~~

We can name the row roles in the pattern:

- `S`: session start row.
- `P`: payment row.
- `C`: session close row.

The pattern is written as:

~~~sql
PATTERN (S P* C)
~~~

Here `P*` means **zero or more** `P` rows. A session may have multiple payments or no payments at all.

Diagram:

~~~text
Time-ordered row sequence:

START  PAYMENT  PAYMENT  CLOSE  START  PAYMENT  CLOSE
  S       P        P       C      S       P       C
  └──────────── MATCH 1 ────────┘  └── MATCH 2 ───┘
~~~

The difference from ordinary `WHERE` filtering is that a row is evaluated within **the context of its position in the pattern**, and the pattern is matched across multiple ordered rows. This is an event-sequence analysis tool, not merely an independent per-row filter.

## 3. MATCH_RECOGNIZE Syntax Framework

General structure:

~~~sql
SELECT ...
FROM source_table
MATCH_RECOGNIZE (
    [PARTITION BY partition_column [, ...]]
    [ORDER BY sort_column [ASC | DESC] [NULLS FIRST | NULLS LAST] [, ...]]
    [MEASURES measure_expression AS alias [, ...]]
    [ONE ROW PER MATCH | ALL ROWS PER MATCH]
    [AFTER MATCH SKIP ...]
    PATTERN (pattern_expression)
    [SUBSET ...]
    [DEFINE variable_condition [, ...]]
) pattern_result
~~~

Each clause has a specific role:

| Clause | Question answered |
| --- | --- |
| `PARTITION BY` | Which rows belong to the same independent sequence? |
| `ORDER BY` | What is the order of events within the sequence? |
| `PATTERN` | What sequence structure are we looking for? |
| `DEFINE` | What condition makes the current row match a pattern variable? |
| `MEASURES` | Once a pattern is matched, what values should be computed and output? |
| `ONE ROW PER MATCH` / `ALL ROWS PER MATCH` | Should each match emit one summary row or return every participating row? |
| `AFTER MATCH SKIP` | From which position should searching for the next match resume? |
| `SUBSET` | Groups multiple pattern variables into one logical name for measures/conditions? |

`PARTITION BY`, `ORDER BY`, `MEASURES`, `PATTERN`, and `DEFINE` are the most common components. For event sequences, always declare `ORDER BY` explicitly; physical table order is not event order.

## 4. First Example: Finding START, PAYMENT, CLOSE Sessions

### 4.1. Source data in a CTE

The self-contained example below requires no table creation:

~~~sql
WITH event_log AS (
    SELECT 10 AS account_id,
           101 AS event_id,
           TIMESTAMP '2026-11-14 09:00:00' AS event_time,
           'START' AS event_type,
           CAST(NULL AS NUMBER) AS amount
    FROM dual
    UNION ALL
    SELECT 10, 102, TIMESTAMP '2026-11-14 09:10:00',
           'PAYMENT', 100 FROM dual
    UNION ALL
    SELECT 10, 103, TIMESTAMP '2026-11-14 09:20:00',
           'PAYMENT', 50 FROM dual
    UNION ALL
    SELECT 10, 104, TIMESTAMP '2026-11-14 09:30:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 105, TIMESTAMP '2026-11-14 10:00:00',
           'START', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 106, TIMESTAMP '2026-11-14 10:05:00',
           'PAYMENT', 30 FROM dual
    UNION ALL
    SELECT 10, 107, TIMESTAMP '2026-11-14 10:15:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
)
SELECT *
FROM event_log
ORDER BY account_id, event_time, event_id;
~~~

This dataset has two sessions for account 10. `EVENT_ID` is the unique tie-breaker if two events share the same timestamp.

### 4.2. The MATCH_RECOGNIZE query

~~~sql
WITH event_log AS (
    SELECT 10 account_id, 101 event_id,
           TIMESTAMP '2026-11-14 09:00:00' event_time,
           'START' event_type, CAST(NULL AS NUMBER) amount
    FROM dual
    UNION ALL
    SELECT 10, 102, TIMESTAMP '2026-11-14 09:10:00',
           'PAYMENT', 100 FROM dual
    UNION ALL
    SELECT 10, 103, TIMESTAMP '2026-11-14 09:20:00',
           'PAYMENT', 50 FROM dual
    UNION ALL
    SELECT 10, 104, TIMESTAMP '2026-11-14 09:30:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 105, TIMESTAMP '2026-11-14 10:00:00',
           'START', CAST(NULL AS NUMBER) FROM dual
    UNION ALL
    SELECT 10, 106, TIMESTAMP '2026-11-14 10:05:00',
           'PAYMENT', 30 FROM dual
    UNION ALL
    SELECT 10, 107, TIMESTAMP '2026-11-14 10:15:00',
           'CLOSE', CAST(NULL AS NUMBER) FROM dual
)
SELECT account_id,
       match_no,
       started_at,
       closed_at,
       payment_count,
       total_paid
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(S.event_time) AS started_at,
        LAST(C.event_time) AS closed_at,
        COUNT(P.event_id) AS payment_count,
        NVL(SUM(P.amount), 0) AS total_paid
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
) mr
ORDER BY account_id, match_no;
~~~

Logical output:

| ACCOUNT_ID | MATCH_NO | STARTED_AT | CLOSED_AT | PAYMENT_COUNT | TOTAL_PAID |
| ---: | ---: | --- | --- | ---: | ---: |
| 10 | 1 | 09:00 | 09:30 | 2 | 150 |
| 10 | 2 | 10:00 | 10:15 | 1 | 30 |

### 4.3. Reading each part

- `PARTITION BY account_id`: each account forms an independent sequence. Matches never cross from one account to another.
- `ORDER BY event_time, event_id`: processes events chronologically; ID breaks ties on matching timestamps.
- `PATTERN (S P* C)`: one START row, zero or more PAYMENT rows, then one CLOSE row.
- `DEFINE`: defines which row types can match `S`, `P`, and `C`.
- `MEASURES`: outputs match number, start/end timestamps, payment count, and total amount.
- `ONE ROW PER MATCH`: each session is summarized into one output row.
- `AFTER MATCH SKIP PAST LAST ROW`: after finding a session, resume searching after the last row of that matched session.

`FIRST(S.event_time)` takes the timestamp of the first row bound to variable `S` in the match. `LAST(C.event_time)` takes the timestamp of the last row bound to `C`. `COUNT(P.event_id)` counts payment rows; `SUM(P.amount)` totals amounts across `P` rows.

### 4.4. Why does P* allow a session with no payments?

`*` means **zero or more**. If data has:

~~~text
START → CLOSE
~~~

it still matches `S P* C` with `P*` matching zero rows. In that case `COUNT(P.event_id)` is 0; `SUM(P.amount)` is NULL under aggregate semantics, so the example uses `NVL(..., 0)` to display a total of 0.

If business rules require at least one payment, change `P*` to `P+`:

~~~sql
PATTERN (S P+ C)
~~~

`+` requires one or more `P` rows.

## 5. PARTITION BY and ORDER BY Define the Event Sequence

### 5.1. PARTITION BY

`PARTITION BY` divides the data source into independent groups. Each partition is processed as a separate sequence.

Example:

~~~sql
PARTITION BY account_id
ORDER BY event_time, event_id
~~~

means:

- Sort events within each account.
- A pattern cannot start in account 10 and finish in account 20.
- `MATCH_NUMBER()` is numbered within each partition.

To match per device and day, you can partition by both:

~~~sql
PARTITION BY device_id, TRUNC(event_time)
ORDER BY event_time, event_id
~~~

Consider the data type and time zone of `event_time` before splitting by day. `TRUNC` on a timestamp and session-level date rules may not reflect the intended business day if data carries time zones. In multi-timezone systems, clarify whether days follow UTC or the customer's local time zone.

### 5.2. ORDER BY

Pattern matching requires a meaningful order. If you only write:

~~~sql
ORDER BY event_time
~~~

and two rows share the same `EVENT_TIME`, their relative order is not guaranteed. Whenever same-timestamp ordering affects pattern matching, add a unique key:

~~~sql
ORDER BY event_time, event_id
~~~

If business rules define a priority order for simultaneous events, use a dedicated tie-breaker expression:

~~~sql
ORDER BY event_time,
         CASE event_type
           WHEN 'START' THEN 1
           WHEN 'PAYMENT' THEN 2
           WHEN 'CLOSE' THEN 3
           ELSE 9
         END,
         event_id
~~~

Use such an ordering only when it reflects genuine business rules. Never arbitrarily force START before CLOSE solely to make a query match a pattern.

### 5.3. ORDER BY inside MATCH_RECOGNIZE does not replace the outer ORDER BY

`ORDER BY` inside `MATCH_RECOGNIZE` defines the order used for **pattern recognition**. If the application requires a guaranteed display order for the output, also declare `ORDER BY` on the outer query:

~~~sql
SELECT account_id, match_no, started_at, closed_at
FROM event_log
MATCH_RECOGNIZE (...)
ORDER BY account_id, match_no;
~~~

Never assume output is automatically ordered just because inputs were ordered inside the row pattern clause.

## 6. PATTERN: A Language for Describing Sequence Structure

`PATTERN` uses pattern variables and operators to describe sequences. Variable names are usually uppercase for readability, such as `A`, `B`, `START_EVT`, `PAYMENT_EVT`.

### 6.1. Concatenation

~~~sql
PATTERN (A B C)
~~~

Requires a row matching `A`, immediately followed by a row matching `B`, then a row matching `C`.

Order status example:

~~~text
CREATED → PAID → SHIPPED
~~~

### 6.2. Quantifiers: occurrence counts

| Symbol | Meaning | Example |
| --- | --- | --- |
| `?` | Zero or one time | `A?` |
| `*` | Zero or more times | `A*` |
| `+` | One or more times | `A+` |
| `{m}` | Exactly m times | `A{3}` |
| `{m,}` | At least m times | `A{2,}` |
| `{m,n}` | Between m and n times | `A{2,5}` |

Examples:

~~~sql
PATTERN (S P{2,4} C)
~~~

One START, two to four PAYMENTs, then CLOSE.

~~~sql
PATTERN (A B? C)
~~~

One A, optionally one B, then C.

### 6.3. Alternation: one of multiple branches

~~~sql
PATTERN (START (PAYMENT | REFUND)+ END)
~~~

After START, one or more PAYMENT or REFUND rows, then END.

`|` is the alternation operator. Use parentheses to clarify scope:

~~~sql
PATTERN ((A B) | (C D))
~~~

This pattern accepts either A followed by B, or C followed by D.

### 6.4. Grouping

Grouping parentheses allow applying quantifiers to an entire subsequence:

~~~sql
PATTERN (START (ITEM PAYMENT)+ CLOSE)
~~~

After START, one or more pairs of ITEM followed by PAYMENT, ending with CLOSE.

### 6.5. Greedy quantifiers

Standard quantifiers are **greedy**: they try to match as many times as possible while still allowing the rest of the pattern to succeed.

Example:

~~~sql
PATTERN (A B* C)
~~~

`B*` tries to consume as many consecutive B rows as possible before matching C. In complex patterns with multiple branches or quantifiers, greediness and backtracking affect how rows are assigned to variables.

When business rules require stopping at a specific event, write explicit `DEFINE` conditions. Do not rely on a quantifier "guessing" session boundaries.

### 6.6. Partition start and end anchors

Two anchors:

- `^`: start of partition.
- `$`: end of partition.

Example:

~~~sql
PATTERN (^ A+ $)
~~~

Requires the entire partition to consist of one or more rows matching A. It will not match a sub-segment sitting in the middle of a partition.

Anchors are useful when the rule states "the sequence must begin at the first event" or "the sequence must end at the last event". Omit anchors when searching for matching subsequences anywhere inside a stream.

## 7. DEFINE: Conditions for Matching a Row to a Pattern Variable

`DEFINE` assigns a predicate to each pattern variable:

~~~sql
PATTERN (A B+ C)
DEFINE
    A AS A.event_type = 'START',
    B AS B.event_type = 'PAYMENT',
    C AS C.event_type = 'CLOSE'
~~~

A row is mapped to a variable when that variable's condition evaluates to TRUE. Conditions can inspect:

- Column values of the current row.
- Values of preceding/following rows via navigation functions.
- Relationships between the current value and rows already accepted into the match.
- Supported SQL arithmetic, comparisons, and expressions.

If a pattern variable is omitted from `DEFINE`, its default condition is TRUE. In real queries, explicitly define any variable with business meaning so readers understand the pattern.

### 7.1. Conditions based solely on the current row

~~~sql
PATTERN (S P+ C)
DEFINE
    S AS S.event_type = 'START',
    P AS P.event_type = 'PAYMENT' AND P.amount > 0,
    C AS C.event_type = 'CLOSE'
~~~

Only payments with positive amounts are accepted into the sequence. If a payment with amount 0 or negative appears between START and CLOSE, this pattern does not automatically skip it; it can only match the declared structure. To allow intervening events, model them explicitly in the pattern.

### 7.2. Comparing with the previous row using PREV

Example recognizing consecutive price increases:

~~~sql
PATTERN (A B+)
DEFINE
    B AS B.price > PREV(B.price)
~~~

`PREV` accesses the value in the preceding row of the partition relative to the row being evaluated. When `B` follows `A`, B's condition compares the current price with the prior row's price. As `B+` repeats, each subsequent B is compared against the row immediately before it.

Using this in a complete query:

~~~sql
SELECT symbol,
       match_no,
       first_price,
       last_price,
       rise_count,
       start_time,
       end_time
FROM stock_ticks
MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY tick_time, tick_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(A.price) AS first_price,
        LAST(B.price) AS last_price,
        COUNT(B.tick_id) AS rise_count,
        FIRST(A.tick_time) AS start_time,
        LAST(B.tick_time) AS end_time
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A B+)
    DEFINE
        B AS B.price > PREV(B.price)
) mr
ORDER BY symbol, start_time;
~~~

Pattern variable A has no explicit condition, so it matches a row as the starting anchor. Each B must have a higher price than the immediately preceding row. `A B+` captures an anchor plus at least one upward step.

This is an illustrative template; with real price data, decide how to handle NULLs, time gaps without ticks, simultaneous trades, and whether flat/non-increasing rows are allowed inside the run.

### 7.3. PREV and NEXT are not the same as FIRST and LAST

| Function | Role |
| --- | --- |
| `PREV(expr [, offset])` | Retrieves the expression at a preceding row in the partition by offset |
| `NEXT(expr [, offset])` | Retrieves the expression at a following row in the partition by offset |
| `FIRST(expr [, offset])` | Accesses the value at the first position in the match/pattern-variable context |
| `LAST(expr [, offset])` | Accesses the value at the last position in the match/pattern-variable context |
| `CLASSIFIER()` | Name of the pattern variable assigned to the current row in the match |
| `MATCH_NUMBER()` | Sequential match number within the partition |

`PREV`/`NEXT` navigate by row position in the partition; `FIRST`/`LAST` operate in the context of the match and pattern variable. For complex calculations, carefully verify expression scope and test on small sequences with known expected results.

### 7.4. NULLs in DEFINE

A predicate evaluating to UNKNOWN due to NULL does not count as TRUE for binding a row to a pattern variable. Example:

~~~sql
DEFINE
    P AS P.amount > 0
~~~

If `P.amount` is NULL, the condition is not TRUE, so the row does not match variable P. If business logic treats NULL as 0, write it explicitly:

~~~sql
DEFINE
    P AS NVL(P.amount, 0) > 0
~~~

Use `NVL` only when that interpretation accurately reflects data semantics.

## 8. MEASURES: Producing Output from a Match

`MEASURES` defines expressions included in the output. Common functions:

- `MATCH_NUMBER()` — sequential match number in the partition.
- `CLASSIFIER()` — name of the pattern variable assigned to a row in the match.
- `FIRST(expr)` / `LAST(expr)` — first/last value in the match context.
- Aggregates such as `COUNT`, `SUM`, `MIN`, `MAX`, and `AVG` over pattern variables.

Example:

~~~sql
MEASURES
    MATCH_NUMBER() AS match_no,
    FIRST(S.event_time) AS session_start,
    LAST(C.event_time) AS session_end,
    COUNT(P.event_id) AS payment_count,
    SUM(P.amount) AS payment_total
~~~

The pattern variable name restricts which rows participate in the measure. `SUM(P.amount)` sums only rows mapped to P within the match.

### 8.1. ONE ROW PER MATCH

`ONE ROW PER MATCH` emits one row per match. This fits session summaries, alert sequences, start/end intervals, or pattern-level aggregated metrics.

~~~sql
SELECT account_id, match_no, session_start, session_end
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(S.event_time) AS session_start,
        LAST(C.event_time) AS session_end
    ONE ROW PER MATCH
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
);
~~~

### 8.2. ALL ROWS PER MATCH

`ALL ROWS PER MATCH` returns every row belonging to a match. This is useful when you want to see which row was classified as START, PAYMENT, or CLOSE.

~~~sql
SELECT account_id,
       event_id,
       event_type,
       event_time,
       classifier_name,
       match_no
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES
        CLASSIFIER() AS classifier_name,
        MATCH_NUMBER() AS match_no
    ALL ROWS PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
)
ORDER BY account_id, event_time, event_id;
~~~

The result can emit multiple rows for a single match:

| EVENT_ID | EVENT_TYPE | CLASSIFIER_NAME | MATCH_NO |
| ---: | --- | --- | ---: |
| 101 | START | S | 1 |
| 102 | PAYMENT | P | 1 |
| 103 | PAYMENT | P | 1 |
| 104 | CLOSE | C | 1 |
| 105 | START | S | 2 |
| 106 | PAYMENT | P | 2 |
| 107 | CLOSE | C | 2 |

`CLASSIFIER()` is especially helpful when explaining why a row belongs to a match: from one event source, each row takes on a distinct role.

### 8.3. RUNNING and FINAL in measures

Under `ALL ROWS PER MATCH`, measure results can be evaluated as running values or final post-match values. Oracle supports `RUNNING` and `FINAL` measure semantics in the corresponding contexts:

- **RUNNING:** value as of the current row during pattern evaluation.
- **FINAL:** value once the complete match is finalized.

This matters when displaying a running total versus repeating the match's final total on every row of the match. Under `ONE ROW PER MATCH`, typically only the final match value is needed. When writing `ALL ROWS PER MATCH`, specify semantics explicitly depending on whether output depends on in-progress state or final state.

## 9. AFTER MATCH SKIP: Where Searching for the Next Match Resumes

Once a pattern is matched, Oracle needs to know which row to start searching from for the next pattern. `AFTER MATCH SKIP` governs this behavior.

### 9.1. PAST LAST ROW

~~~sql
AFTER MATCH SKIP PAST LAST ROW
~~~

After a match completes, skip past the last row of that match. This is the usual choice when sessions must not overlap.

~~~text
S P P C S P C
└─ match 1 ─┘ └ match 2 ┘
              resume after C
~~~

### 9.2. TO NEXT ROW

~~~sql
AFTER MATCH SKIP TO NEXT ROW
~~~

Continue searching from the row immediately following the starting row of the previous match. This allows overlapping matches, because rows from an earlier match can participate in a subsequent match.

For example, a pattern looking for two consecutive increases can have overlapping windows sharing some rows. With `PAST LAST ROW`, trailing windows get skipped; `TO NEXT ROW` re-evaluates starting from an earlier position.

### 9.3. TO FIRST variable and TO LAST variable

Oracle supports skipping to the first or last occurrence of a pattern variable inside the match:

~~~sql
AFTER MATCH SKIP TO FIRST B
~~~

or:

~~~sql
AFTER MATCH SKIP TO LAST B
~~~

These options are useful when a pattern has multiple occurrences of a variable and you want the next match search to begin at a specific point inside the previous match. The target variable must fit the pattern and be present in the match; misusing it can yield an invalid query or fail to meet the goal.

### 9.4. Skip policy changes results, not just performance

Two queries with the exact same `PATTERN` but different `AFTER MATCH SKIP` clauses can produce **different sets of matches**. Treat the skip policy as part of the business definition:

| Goal | Skip policy to consider |
| --- | --- |
| Sequential, non-overlapping sessions | `PAST LAST ROW` |
| Finding overlapping windows | `TO NEXT ROW` |
| Resuming from a landmark event inside a match | `TO FIRST variable` / `TO LAST variable` |

Never choose a skip policy merely because a query returns more or fewer rows than expected. Sketch the input sequence and mark the start/end of each match to verify.

## 10. SUBSET: Grouping Multiple Pattern Variables

`SUBSET` lets you define a union variable representing a group of pattern variables.

Example:

~~~sql
PATTERN (S (P | R)+ C)
SUBSET MONEY_EVENT = (P, R)
~~~

Here P may be PAYMENT and R may be REFUND. `MONEY_EVENT` groups both types for use in measures or conditions.

~~~sql
MEASURES
    COUNT(MONEY_EVENT.event_id) AS money_event_count
~~~

This keeps expressions concise when multiple pattern variables play the same role in calculations. `SUBSET` does not change the pattern; it only defines a variable group for referencing.

## 11. Example: Recognizing Consecutive Price Increases

Problem: for each stock ticker, find segments with at least two consecutive increases (i.e., at least three price observations where each price exceeds the immediately preceding price).

Suppose `STOCK_TICKS` contains:

| SYMBOL | TICK_ID | TICK_TIME | PRICE |
| --- | ---: | --- | ---: |
| ABC | 1 | 09:00 | 100 |
| ABC | 2 | 09:01 | 102 |
| ABC | 3 | 09:02 | 105 |
| ABC | 4 | 09:03 | 103 |
| ABC | 5 | 09:04 | 107 |
| ABC | 6 | 09:05 | 109 |

SQL:

~~~sql
SELECT symbol,
       match_no,
       first_price,
       last_price,
       observations,
       start_time,
       end_time
FROM stock_ticks
MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY tick_time, tick_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(A.price) AS first_price,
        LAST(B.price) AS last_price,
        COUNT(B.tick_id) + 1 AS observations,
        FIRST(A.tick_time) AS start_time,
        LAST(B.tick_time) AS end_time
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO NEXT ROW
    PATTERN (A B+)
    DEFINE
        B AS B.price > PREV(B.price)
) mr
ORDER BY symbol, start_time;
~~~

Explanation:

- A is the starting anchor price.
- B is an observation higher than the immediately preceding row.
- `B+` requires at least one upward step.
- `AFTER MATCH SKIP TO NEXT ROW` allows finding potentially overlapping runs.
- `observations` counts A plus the B rows.

In the sample data, `100 → 102 → 105` is one rising run; `103 → 107 → 109` is the next rising run. If you want maximal non-overlapping rising runs, consider `PAST LAST ROW`. If you want all potentially overlapping rising windows, `TO NEXT ROW` is usually appropriate.

Note: test patterns and skip policies on real data, especially since greedy quantifiers can extend matches. `PREV` compares against the immediately preceding row in the partition; if data contains NULLs or time gaps, the rise condition must reflect how to handle them.

## 12. Example: Detecting Anomalous Transaction Sequences

An account may generate multiple consecutive high-value transactions. Suppose an alert rule is:

- At least three consecutive transactions.
- Each transaction has amount greater than 1,000.
- All belong to the same account.
- The streak breaks when a transaction is less than or equal to 1,000.

Pattern:

~~~sql
SELECT account_id,
       match_no,
       first_event,
       last_event,
       event_count,
       total_amount
FROM transactions
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY transaction_time, transaction_id
    MEASURES
        MATCH_NUMBER() AS match_no,
        FIRST(H.transaction_time) AS first_event,
        LAST(H.transaction_time) AS last_event,
        COUNT(H.transaction_id) AS event_count,
        SUM(H.amount) AS total_amount
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (H{3,})
    DEFINE
        H AS H.amount > 1000
) mr
ORDER BY account_id, first_event;
~~~

`H{3,}` requires at least three consecutive rows satisfying H. A row failing H ends the ability to extend the current streak; Oracle resumes searching at the next position per the skip policy.

**Business limitation:** this example matches consecutive rows in sequence order; it does not prove the transactions share the same actor, same device, are invalid, or involve fraud. Real fraud detection requires additional features, context, and verification workflows.

## 13. Example: Order Status Transitions

Suppose a valid order status progression is:

~~~text
CREATED → PAID → (PACKED) → SHIPPED
~~~

where `PACKED` is optional:

~~~sql
SELECT order_id,
       created_at,
       paid_at,
       shipped_at
FROM order_status_history
MATCH_RECOGNIZE (
    PARTITION BY order_id
    ORDER BY status_time, status_event_id
    MEASURES
        FIRST(C.status_time) AS created_at,
        FIRST(P.status_time) AS paid_at,
        LAST(S.status_time) AS shipped_at
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (C P K? S)
    DEFINE
        C AS C.status = 'CREATED',
        P AS P.status = 'PAID',
        K AS K.status = 'PACKED',
        S AS S.status = 'SHIPPED'
) mr
ORDER BY order_id, created_at;
~~~

`K?` allows one PACKED row or none. This pattern matches only the exact declared order; if the system also records `CANCELLED`, `RETURNED`, or `ON_HOLD`, decide whether they should be ignored, break the sequence, or form an alternate pattern branch.

Do not blindly add `.*` to "skip over any unexpected statuses" without determining whether those statuses alter the order lifecycle semantics.

## 14. Unmatched Rows and Gaps in the Sequence

Not every row in a partition must belong to a match. `MATCH_RECOGNIZE` finds segments matching the pattern; rows outside matches may not appear in the output depending on the row-per-match option and query structure.

If you need to inspect both matched and unmatched rows:

- Use `ALL ROWS PER MATCH` to inspect every row belonging to matches.
- Check support and semantics of `WITH UNMATCHED ROWS` in your Oracle release's syntax if you want unmatched rows emitted in the output.
- You can compare the source against matched rows using a unique key and an anti-join / `NOT EXISTS`.

Illustrative comparison pattern:

~~~sql
WITH matched_events AS (
    SELECT account_id, event_id
    FROM event_log
    MATCH_RECOGNIZE (
        PARTITION BY account_id
        ORDER BY event_time, event_id
        MEASURES
            CLASSIFIER() AS classifier_name
        ALL ROWS PER MATCH
        PATTERN (S P* C)
        DEFINE
            S AS S.event_type = 'START',
            P AS P.event_type = 'PAYMENT',
            C AS C.event_type = 'CLOSE'
    )
)
SELECT e.*
FROM   event_log e
WHERE  NOT EXISTS (
    SELECT 1
    FROM matched_events m
    WHERE m.account_id = e.account_id
      AND m.event_id = e.event_id
);
~~~

This is an illustrative framework; when applying it, check the output columns of `MATCH_RECOGNIZE` for the chosen row-per-match mode and preserve sufficiently unique keys. An anti-join helps find events outside any match, though it does not replace the row pattern clause's built-in unmatched-row classification rules.

## 15. AFTER MATCH SKIP and Overlapping Matches

Consider the sequence:

~~~text
Price: 10 → 12 → 14 → 16
ID:     1    2    3    4
~~~

Pattern `A B+` with `B.price > PREV(B.price)` matches the rising run starting at ID 1. With `PAST LAST ROW`, after the match ends at ID 4, Oracle resumes after ID 4, so no windows starting at ID 2 or 3 are produced.

With `TO NEXT ROW`, the search resumes at the row right after the previous match's start; subsequent rows can be reused in later matches. This creates overlapping matches, shaped by greedy quantifiers and DEFINE rules.

~~~text
Input:  10 → 12 → 14 → 16

Possible overlapping matches:
        [10 → 12 → 14]
              [12 → 14 → 16]

PAST LAST ROW:
        [10 → 12 → 14 → 16]
        resumes after last ID
~~~

When reporting match counts, clearly state whether matches can overlap. If non-overlapping, matched rows never belong to multiple matches (though total matched rows need not equal source rows); if overlapping, a single row can participate in multiple matches.

## 16. Handling Duplicate Timestamps, NULLs, and Time Intervals

### 16.1. Duplicate timestamps

Always add a unique tie-breaker when relative order among same-timestamp events matters:

~~~sql
ORDER BY event_time, event_id
~~~

Without a tie-breaker, two simultaneous events can be processed in non-deterministic order. A pattern like `A B C` may match differently if those two rows swap places.

### 16.2. NULL values in condition columns

Condition:

~~~sql
DEFINE
    H AS H.amount > 1000
~~~

does not accept a row with NULL amount into H because the comparison returns UNKNOWN, not TRUE. If NULL represents "unknown amount", decide explicitly:

- Should that row be excluded from the pattern?
- Should that row break the sequence?
- Should that row be treated as 0?
- Should that row have its own pattern variable?

Express that rule explicitly rather than letting NULL semantics decide implicitly.

### 16.3. Time interval between two events

You can add time-gap conditions in `DEFINE`, such as requiring the current event to occur within 10 minutes of the prior row. For timestamps, subtraction produces an INTERVAL:

~~~sql
DEFINE
    B AS B.event_time - PREV(B.event_time)
         <= INTERVAL '10' MINUTE
~~~

The actual expression must match the column data type and timestamp arithmetic result type. If rows can intervene or if you need elapsed time from anchor A rather than the immediately preceding row, use the appropriate navigation function and test on small sequences.

## 17. Common Design and Query Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No match found despite seeing START and CLOSE | Intervening row disallowed by pattern; DEFINE not TRUE | Inspect the full sequence in ORDER BY order; define a variable for intervening events if allowed |
| Match traverses out of order | ORDER BY lacks tie-breaker or sort key does not reflect business order | Add a unique key / priority rule |
| One session splits into multiple matches | Wrong skip policy or pattern boundary | Sketch the sequence; inspect quantifiers and AFTER MATCH SKIP |
| Matches overlap unexpectedly | Using TO NEXT ROW or skipping to an earlier position | Choose PAST LAST ROW for sequential non-overlapping matches |
| Missing overlapping matches | Using PAST LAST ROW | Consider TO NEXT ROW or an appropriate skip target |
| Pattern matches too many rows | Overly broad DEFINE or greedy quantifier | Tighten conditions and define clear stop boundaries |
| No payments yet total is NULL | SUM over an empty set returns NULL | Use NVL(SUM(...), 0) if business logic expects 0 |
| PREV returns NULL at start of partition | No prior row or prior value is NULL | Handle boundaries/NULLs explicitly |
| Matches change across runs on identical data | Non-deterministic row order on tied sort keys | Add a unique tie-breaker |
| More output rows than expected | Using ALL ROWS PER MATCH, or overlapping matches | Check row-per-match mode and skip policy |
| Only summary returned when source rows are needed | Using ONE ROW PER MATCH | Switch to ALL ROWS PER MATCH or a separate detail query |
| Measure column uses wrong scope | Wrong pattern variable in aggregate/FIRST/LAST | Qualify measures with the proper variable |
| Unmatched row disappears | Emitting only matched rows | Reconcile unmatched rows via supported options or anti-join |

## 18. Performance and Inspecting the Execution Plan

`MATCH_RECOGNIZE` is a sequence-analysis operation that may require sorting and maintaining state during recognition. Cost depends on:

- Rows per partition.
- Number of partitions and size distribution.
- Pattern complexity.
- Looping quantifiers and number of alternation branches.
- Expressions in DEFINE/MEASURES.
- Ability to leverage ordering/indexes and pre-matching filters.

### 18.1. Reduce input data properly

If analyzing only a specific time window, filter the source first:

~~~sql
SELECT ...
FROM (
    SELECT *
    FROM event_log
    WHERE event_time >= TIMESTAMP '2026-11-01 00:00:00'
      AND event_time <  TIMESTAMP '2026-12-01 00:00:00'
) src
MATCH_RECOGNIZE (...);
~~~

Filter conditions must still retain enough context to recognize patterns. For example, if a session started before Nov 1 and closed during Nov, filtering out START breaks the pattern. You may need to widen the read window, carry prior state, or define boundary rules.

### 18.2. Partition keys and ordering

An index on `(account_id, event_time, event_id)` can help workloads that frequently analyze by account and time. However, the optimizer will not necessarily use that index; sorts, joins, filters, and cardinality also shape the plan.

Do not create an index solely because a query uses `PARTITION BY`/`ORDER BY`. Inspect the execution plan, write overhead, storage, and overall workload.

### 18.3. Complex patterns

Patterns with many looping quantifiers, alternations, and navigation conditions can be harder to control and more resource-intensive. Be sure to:

- Keep the pattern minimal to express the business rule.
- Scope partitions cleanly where possible without breaking logic.
- Avoid overly broad DEFINE conditions where multiple branches match the same row.
- Verify output on small sequences with known expected matches.
- Benchmark on realistic data distributions, not just a few rows.

### 18.4. Viewing the plan

~~~sql
EXPLAIN PLAN FOR
SELECT account_id, match_no
FROM event_log
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY event_time, event_id
    MEASURES MATCH_NUMBER() AS match_no
    ONE ROW PER MATCH
    PATTERN (S P* C)
    DEFINE
        S AS S.event_type = 'START',
        P AS P.event_type = 'PAYMENT',
        C AS C.event_type = 'CLOSE'
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows the estimated plan. If runtime metrics are needed, a DBA can use `DBMS_XPLAN.DISPLAY_CURSOR` with the appropriate cursor and statistics. Do not grant administrative privileges just to run a lesson exercise; use the privileges provided in your lab environment.

## 19. Limitations and Notes When Using MATCH_RECOGNIZE

1. **Event ordering is required:** row pattern matching cannot infer business order from storage order.
2. **Cannot cross partitions:** a match never spans across partition boundaries.
3. **A match need not cover every row:** only rows participating in a pattern are considered matched.
4. **Skip policy controls overlap:** `AFTER MATCH SKIP` is part of the core semantics.
5. **Not every sequential query needs MATCH_RECOGNIZE:** if you only need `LAG`, `LEAD`, `ROW_NUMBER`, or simple aggregates, analytic functions may be clearer and lighter.
6. **Historical reads need sufficient context:** cutting off timestamps too early can drop the opening event of a pattern.
7. **Patterns do not validate business intent by themselves:** the query recognizes sequences matching your conditions, but does not prove fraud, bad orders, or faulty hardware.
8. **Verify data types:** timestamps, intervals, NULLs, collation, and DEFINE/MEASURES expressions must align with the data.
9. **Never assume output order:** add an outer ORDER BY when the client expects ordered results.
10. **Syntax varies by release:** verify against the SQL Language Reference for your exact Oracle version, especially row-per-match options and navigation.

## 20. When to Use MATCH_RECOGNIZE vs. Analytic Functions or Self Joins?

| Problem | Typically suited tool | Reason |
| --- | --- | --- |
| Access previous/next row value | `LAG`, `LEAD` | Simple single-offset relationship |
| Number and rank rows | `ROW_NUMBER`, `RANK`, `DENSE_RANK` | Ordered ranking |
| Compute running totals | Analytic aggregate | Cumulative sum without pattern matching |
| Detect structured event sequences | `MATCH_RECOGNIZE` | Expresses variables, quantifiers, order, and skip rules |
| List parent-child or all row pairs | JOIN/self join | Row-to-row relationships |
| Check only whether related rows exist | `EXISTS` | No sequence recognition needed |
| Multi-step control logic with side effects | PL/SQL/procedures/workflows | Requires actions or persisted business state |

For example, `LAG` can detect a single price increase:

~~~sql
SELECT symbol,
       tick_time,
       price,
       LAG(price) OVER (
           PARTITION BY symbol
           ORDER BY tick_time, tick_id
       ) AS previous_price
FROM stock_ticks;
~~~

Then `WHERE price > previous_price` filters rising rows. However, if the requirement is finding **a sequence with at least three increases followed by a decrease, allowing optional branches and computing match-level measures**, `MATCH_RECOGNIZE` expresses the structure far more clearly.

Do not pick a tool solely for novelty. Choose based on problem shape and result verifiability.

## 21. Self-Contained Practice Lab

> You can run these SELECT queries in an Oracle 19c environment. Table names `EVENT_LOG`, `STOCK_TICKS`, `TRANSACTIONS`, and `ORDER_STATUS_HISTORY` in some examples are illustrative; substitute lab tables or CTEs in your granted schema. Never run DML on production.

### Exercise A — Recognize non-overlapping sessions

Use the CTE from section 4 and `PATTERN (S P* C)`.

Requirements:

1. Return one row per session.
2. Count the number of payments.
3. Sum the payment amounts.
4. Display start and close timestamps.
5. Try adding a `START → CLOSE` session with no payments.

Expect the zero-payment session to still be recognized, with count 0 and total NULL handled as required.

### Exercise B — Require at least two payments

Change the pattern:

~~~sql
PATTERN (S P{2,} C)
~~~

Create data with one 1-payment session and one 2-payment session. Explain why only the session with two or more payments matches.

### Exercise C — Return each row in the match

Change `ONE ROW PER MATCH` to:

~~~sql
ALL ROWS PER MATCH
~~~

Add measures:

~~~sql
CLASSIFIER() AS event_role,
MATCH_NUMBER() AS match_no
~~~

Check each `EVENT_ID` and explain why a single partition can have multiple match numbers.

### Exercise D — Compare skip policies

Create a rising sequence:

~~~text
100, 102, 105, 103, 107, 109
~~~

Run the pattern:

~~~sql
PATTERN (A B+)
DEFINE
    B AS B.price > PREV(B.price)
~~~

Compare `AFTER MATCH SKIP PAST LAST ROW` with `AFTER MATCH SKIP TO NEXT ROW`. Sketch the start/end positions of each match and note which rows are reused.

### Exercise E — Duplicate timestamps

Create two events with identical `EVENT_TIME` but different `EVENT_ID` values. Run the query before and after adding `EVENT_ID` to `ORDER BY`. Explain why tie ordering can change pattern recognition.

### Exercise F — NULLs in DEFINE

Create a row with `AMOUNT = NULL`, then compare:

~~~sql
DEFINE
    P AS P.amount > 0
~~~

with:

~~~sql
DEFINE
    P AS NVL(P.amount, 0) > 0
~~~

Conclude whether the NULL row is accepted into variable P and why.

### Exercise G — Maximum time gap

For an event sequence with TIMESTAMP `EVENT_TIME`, add a condition requiring at most 10 minutes between consecutive rows in the pattern. Test intervals of 8 minutes, 10 minutes, and 11 minutes to verify boundaries.

### Exercise H — Reconcile unmatched rows

Use `ALL ROWS PER MATCH` to extract the keys of recognized rows, then use `NOT EXISTS` to list remaining events. Explain the difference between "unmatched by pattern" and "invalid data".

## 22. Review Questions

**Question 1.** What class of problems does `MATCH_RECOGNIZE` solve?

**Question 2.** Why is `PARTITION BY` needed when matching sequences per account?

**Question 3.** Is `ORDER BY event_time` sufficient to define order if two events share the same timestamp?

**Question 4.** How does `PATTERN (S P* C)` differ from `PATTERN (S P+ C)`?

**Question 5.** What is the role of `DEFINE`?

**Question 6.** If a pattern variable is not defined in DEFINE, what is its default condition?

**Question 7.** How does `ONE ROW PER MATCH` differ from `ALL ROWS PER MATCH`?

**Question 8.** What information do `CLASSIFIER()` and `MATCH_NUMBER()` provide?

**Question 9.** How do `AFTER MATCH SKIP PAST LAST ROW` and `TO NEXT ROW` differ?

**Question 10.** How does `PREV` differ from `FIRST`?

**Question 11.** Why can `SUM(P.amount)` be NULL when a pattern allows zero payments?

**Question 12.** When should you use LAG/LEAD instead of MATCH_RECOGNIZE?

<details>
<summary>Suggested answers</summary>

1. Recognizing ordered row sequences matching a structural pattern, such as START, multiple PAYMENTs, and CLOSE.
2. So each account forms an independent sequence and matches never span across two accounts.
3. No. A unique tie-breaker key or business priority rule is required.
4. `P*` allows zero or more P rows; `P+` requires at least one P row.
5. Defines the predicate that assigns the current row to a pattern variable.
6. TRUE, meaning the variable can match any row when allowed by the pattern position.
7. ONE emits one summary row per match; ALL emits every row participating in the match.
8. CLASSIFIER gives the row's assigned pattern variable name; MATCH_NUMBER numbers matches within the partition.
9. PAST LAST ROW resumes after the end of the match; TO NEXT ROW resumes from the row after the match's start, allowing overlap.
10. PREV accesses a prior row in the partition; FIRST accesses the first value in the match/pattern-variable context.
11. SUM over a set with no non-NULL values returns NULL; use NVL if business logic wants 0.
12. When only a single-row lookback/lookahead relationship or simple sequential comparison is needed; analytic functions are easier to read.

</details>

## 23. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — SELECT / MATCH_RECOGNIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): row pattern matching syntax, partition, order, measures, pattern, define, row-per-match, and skip.
2. [Oracle Database 19c Data Warehousing Guide — SQL Pattern Matching](https://docs.oracle.com/en/database/oracle/oracle-database/19/dwhsg/sql-pattern-matching-data-warehouses.html): concepts, sequence modeling, pattern matching examples, and analytical applications.
3. [Oracle Database 19c SQL Language Reference — Pattern Matching Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Pattern-matching-functions.html): navigation and functions used in row pattern matching.
4. [Oracle Database 19c SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): analytic function evaluation order and comparison with sequence analysis.
5. [Oracle Database 19c SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plans, optimizer, and query cost evaluation.

**Core principle to remember:** `MATCH_RECOGNIZE` turns a partitioned, ordered sequence of rows into a pattern-description language. `PATTERN` states the structure, `DEFINE` states per-variable conditions, `MEASURES` produces outputs, row-per-match governs output granularity, and `AFTER MATCH SKIP` governs where searching resumes. When designing, explicitly define event ordering, NULL handling, intervening events, quantifiers, and whether overlapping matches are permitted.
