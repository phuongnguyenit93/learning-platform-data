# LOAD CSV: Reading Headers, Type Conversion, and Missing Value Handling

## 1. The problem: from a CSV table to a property graph

In the **DATABASE_ENGINE_GRAPH_NEO4J** module, Neo4j stores data using **nodes**, **relationships**, and their **properties**. Many systems start with data in CSV format exported from relational databases, CRM systems, ERPs, or data warehouses. Before creating nodes and links, you need to read the right columns, convert strings to appropriate data types, handle missing fields, and prevent invalid data from entering the graph.

Cypher's **LOAD CSV** command reads CSV records one by one and turns each line into a variable that can be used in clauses such as **WITH**, **WHERE**, **MERGE**, **CREATE**, and **SET**. This lesson focuses on three skills:

1. **Reading CSVs with or without headers**, extracting the right fields by name or position.
2. **Converting types** of CSV data—which is primarily read as strings—into numbers, booleans, and dates.
3. **Handling missing values** according to business rules: skipping the row, substituting a default, keeping existing data, or omitting the property.

Examples use the **ImportCustomer** label to separate practice data from real application data. Data-creating statements should only be run against a **test** database.

## 2. Preparing the CSV file and determining its path

Create a UTF-8 file named **customers.csv**:

~~~csv
customer_id,full_name,age,active,email,joined_on,credit_limit
C001,"Nguyen, Van An",29,true,an@example.com,2024-06-01,2500.50
C002,Tran Binh,,false,,,
C003,Pham Chi,34,true,chi@example.com,2024-02-29,0
~~~

Column meanings:

| Column | Example value | Expected type in Neo4j | Rule |
|---|---|---|---|
| **customer_id** | C001 | STRING | Required, unique identifier; preserve letters and leading zeros |
| **full_name** | Nguyen, Van An | STRING | May be missing; do not overwrite existing name when CSV cell is empty |
| **age** | 29 | INTEGER | If empty, omit or keep property; input value must be non-negative |
| **active** | true / false | BOOLEAN | Distinguish **false** from missing data |
| **email** | an@example.com | STRING | Optional; normalize whitespace |
| **joined_on** | 2024-06-01 | DATE | Valid ISO date string; leave blank if unknown |
| **credit_limit** | 2500.50 | FLOAT in example | Numeric value; for money, consider storing smallest currency units as INTEGER |

In row C002, the **age**, **email**, **joined_on**, and **credit_limit** cells have no value. In row C003, **credit_limit = 0** is a valid value, **not** missing data. The double quotes around **"Nguyen, Van An"** keep the comma inside the name instead of splitting the name into two columns.

### 2.1. The file:/// path and where the CSV is actually read

For self-managed Neo4j, place the file in the **Neo4j server's import directory**. Then you can run:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN row
LIMIT 3;
~~~

The path **file:///customers.csv** is resolved by Neo4j on the **database server**, not in the current working directory of Neo4j Browser, the Java Driver, or the user's web browser. By default, that location corresponds to the **import** directory configured by **server.directories.import**. Local file reading also depends on the **dbms.security.allow_csv_import_from_file_urls** setting and source read permissions.

With **Neo4j Aura**, do not use **file:///...** to read files on your local machine. Host the CSV at an **HTTPS source accessible from the Aura environment** with proper permissions, and substitute that URL into the query. Illustrative example:

~~~cypher
LOAD CSV WITH HEADERS
FROM 'https://example.org/data/customers.csv' AS row
RETURN row.customer_id
LIMIT 3;
~~~

The example URL above is an **illustrative address**, not a real file to execute. For real sources, use trusted HTTPS, appropriate read permissions, and avoid putting sensitive credentials in URLs or source code.

**File format:** Neo4j requires CSVs to be **UTF-8**; the default delimiter is a comma, and line endings may be LF or CRLF. Inspect the file in a UTF-8-capable editor and avoid headers with spaces, duplicate names, or invisible characters from export tools.

## 3. WITH HEADERS: accessing columns by name

Basic syntax:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN
  row.customer_id AS id,
  row.full_name AS name,
  row.age AS rawAge,
  row.active AS rawActive
LIMIT 3;
~~~

When using **WITH HEADERS**, the first row provides column names and is **not treated as a data record**. Each subsequent row is read as a **map**; for example, row C001 corresponds semantically to:

~~~text
{
  customer_id: "C001",
  full_name: "Nguyen, Van An",
  age: "29",
  active: "true",
  email: "an@example.com",
  joined_on: "2024-06-01",
  credit_limit: "2500.50"
}
~~~

**Note:** the values **"29"**, **"true"**, and **"2500.50"** at the CSV-reading stage are **strings**, not INTEGER, BOOLEAN, or FLOAT. Cypher does not automatically cast property types just because a column is named **age** or **active**.

### 3.1. Checking headers before importing

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN
  keys(row) AS columnNames,
  row.customer_id AS sampleId,
  row.full_name AS sampleName,
  row.age AS sampleAge
LIMIT 3;
~~~

**keys(row)** shows the keys present in the CSV row map. If the actual header is **CustomerId** while the query uses **row.customer_id**, Neo4j will not guess that they match. Check spelling, letter casing, and spaces right at this step.

### 3.2. CSV without headers

If **customers-no-header.csv** contains:

~~~csv
C001,Nguyen An,29
C002,Tran Binh,
~~~

read it **without WITH HEADERS**:

~~~cypher
LOAD CSV FROM 'file:///customers-no-header.csv' AS row
RETURN row[0] AS customerId,
       row[1] AS fullName,
       row[2] AS rawAge;
~~~

In this mode, each row is a **list** and columns are indexed from **0**. If you forget **WITH HEADERS** on a file that has headers, the header row will be read as data and may cause type-conversion errors or create junk nodes.

### 3.3. Semicolon-delimited files

For CSVs using **;** (common in some export tools):

~~~csv
customer_id;full_name;age
C001;"Nguyen, Van An";29
~~~

you can declare:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers-semicolon.csv'
AS row FIELDTERMINATOR ';'
RETURN row.customer_id, row.full_name, row.age;
~~~

**FIELDTERMINATOR** specifies the field delimiter; it does not change how headers are accessed and does not fix files with inconsistent delimiters.

## 4. Converting CSV strings to meaningful data types

In a Neo4j property graph, proper typing ensures arithmetic, comparisons, filtering, and indexes behave with expected semantics. Do not store ages **"100"** and **"20"** as strings and expect comparisons to behave like integers.

| Raw data | Cypher expression | Expected result | Notes |
|---|---|---|---|
| "29" | **toInteger("29")** | INTEGER 29 | Does not preserve leading zeros; IDs should be STRING |
| "2500.50" | **toFloat("2500.50")** | FLOAT 2500.5 | Standard decimal separator is a dot |
| "true" | **toBoolean("true")** | BOOLEAN true | Do not confuse non-empty strings with true |
| "false" | **toBoolean("false")** | BOOLEAN false | False is valid data |
| "2024-02-29" | **date("2024-02-29")** | DATE 2024-02-29 | String must be a valid calendar date |
| String with outer spaces | **trim(value)** | Normalized string | Preserves meaningful internal spaces |

### 4.1. Using the type conversion functions

~~~cypher
RETURN
  toInteger('29') AS age,
  toFloat('2500.50') AS creditLimit,
  toBoolean('false') AS active,
  date('2024-02-29') AS joinedOn;
~~~

The results have types **INTEGER**, **FLOAT**, **BOOLEAN**, and **DATE** respectively. **date()** accepts a valid date in a supported format; **date('2025-02-30')** is not a real date and can cause the query to fail. Never convert arbitrary date strings to DATE without verifying the source format.

### 4.2. OrNull functions are useful when validating data

~~~cypher
RETURN
  toIntegerOrNull('29') AS validAge,
  toIntegerOrNull('abc') AS invalidAge,
  toFloatOrNull('2500.50') AS validCredit,
  toBooleanOrNull('false') AS validActive,
  toBooleanOrNull('yes') AS invalidActive;
~~~

Expected results: **29**, **null**, **2500.5**, **false**, **null**. The functions **toIntegerOrNull**, **toFloatOrNull**, and **toBooleanOrNull** return **null** if conversion fails. They help identify malformed values, but they do **not** prove the original string was empty; **"abc"** and a blank cell both become null after conversion.

Therefore, you must distinguish **missing data** from **invalid data** before writing. If you silently replace every bad value with null, the import may report success while quietly losing information.

### 4.3. Do not mechanically cast identifiers to INTEGER

The value **"00042"** becomes **42** if passed to **toInteger()**. For customer codes, postal codes, external identifiers, or order codes, leading characters can be significant. Only convert to INTEGER when the field is genuinely a number used for calculation.

For monetary amounts, **FLOAT** has binary rounding errors in certain calculations. In financial applications, you should generally store **the smallest currency unit as an INTEGER** or a dedicated exact representation designed for the domain, rather than defaulting to FLOAT.

## 5. Missing values: null, empty strings, and defaults

Neo4j **does not store properties with a null value**. Setting a property to null causes that property to **no longer exist** on the node or relationship. In CSVs, a blank cell may be represented by the reader as an empty string or null depending on context; normalize both.

### 5.1. Normalizing blank cells and whitespace

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row,
     trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.age, '')) AS ageText,
     trim(coalesce(row.email, '')) AS emailText
RETURN customerId, ageText, emailText;
~~~

Explanation:

- **coalesce(value, '')** replaces null with an empty string so string functions can be applied.
- **trim(...)** removes whitespace from the **start and end** of the string.
- After normalization, **ageText = ''** means no usable value; **ageText = '0'** is a distinct value and is not treated as empty.

Do not use truthiness-only checks for booleans: **false** must be preserved as false rather than replaced with a default.

### 5.2. Four policies for missing fields

| Policy | When to use | Example |
|---|---|---|
| **Skip row** | Required business key is missing | Do not import a Customer with an empty **customer_id** |
| **Assign default** | Clear domain rule exists | Missing status defaults to **pending**, if valid |
| **Omit property** | Value is genuinely unknown | Do not create **email** when blank |
| **Keep old value** | Supplemental import from an incomplete file | Blank **email** in CSV does not erase an existing email |

The last two policies differ when using **MERGE** to re-import: "an empty field clears existing data" and "an empty field leaves existing data unchanged" are two distinct business contracts that must be chosen explicitly.

### 5.3. CASE and coalesce do not mean the same thing

**Assigning a default when missing:**

~~~cypher
RETURN coalesce(null, 'unknown') AS value;
~~~

**Parsing a number only when the cell is non-empty:**

~~~cypher
WITH ' 29 ' AS rawValue
WITH trim(coalesce(rawValue, '')) AS ageText
RETURN CASE
         WHEN ageText = '' THEN null
         ELSE toIntegerOrNull(ageText)
       END AS age;
~~~

When importing into an existing node, avoid **SET c.email = null** if the intent is to preserve the previous email. Use **CASE WHEN emailText = '' THEN c.email ELSE emailText END** to preserve the old property when the CSV provides no value.

## 6. Validating source data before writing

A good import pipeline should have a **preview** step, an **invalid-row detection** step, and only then **write the data**. The queries below use **customers.csv** from Section 2.

### 6.1. Previewing row counts and values

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN
  linenumber() AS csvLine,
  row.customer_id AS id,
  row.full_name AS name,
  row.age AS rawAge,
  row.active AS rawActive,
  row.joined_on AS rawDate
LIMIT 20;
~~~

**linenumber()** returns the CSV line number currently being read within **LOAD CSV**, which is convenient for cross-referencing the source file. Running **RETURN** to inspect data first creates no nodes.

### 6.2. Detecting missing required keys and invalid numeric/boolean fields

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH linenumber() AS csvLine,
     trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.age, '')) AS ageText,
     trim(coalesce(row.active, '')) AS activeText,
     trim(coalesce(row.credit_limit, '')) AS creditText
WITH csvLine,
     [msg IN [
       CASE WHEN customerId = '' THEN 'Missing customer_id' END,
       CASE WHEN ageText <> ''
                   AND toIntegerOrNull(ageText) IS NULL
            THEN 'age is not an integer' END,
       CASE WHEN ageText <> ''
                   AND toIntegerOrNull(ageText) < 0
            THEN 'age is negative' END,
       CASE WHEN activeText <> ''
                   AND toBooleanOrNull(toLower(activeText)) IS NULL
            THEN 'active is not true/false' END,
       CASE WHEN creditText <> ''
                   AND toFloatOrNull(creditText) IS NULL
            THEN 'credit_limit is not a number' END
     ] WHERE msg IS NOT NULL] AS errors
WHERE size(errors) > 0
RETURN csvLine, errors
ORDER BY csvLine;
~~~

With the three valid sample rows, the query above returns **0 rows**. If you add a row with **age = abc** or **active = yes**, the query reports errors on that line. Because **toIntegerOrNull('abc')** returns null, you must specifically check the case **ageText <> ''**.

**Limitation of this step:** the illustrative query checks keys, numbers, and booleans; it does **not** yet validate whether a calendar date actually exists, email format, duplicate identifier rows, or business limits on monetary amounts. For example, **2025-02-30** can still pass these conditions and cause **date()** to fail during the import step. Validate ISO dates, duplicate IDs, and other domain rules during source cleaning or an additional pre-write check.

## 7. Complete import with MERGE and missing-field handling

### 7.1. Creating a constraint on the business key

Run once on the test database:

~~~cypher
CREATE CONSTRAINT import_customer_id_unique IF NOT EXISTS
FOR (c:ImportCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

The constraint prevents multiple **ImportCustomer** nodes from having the same non-null **customerId**. It also creates an index supporting node lookup for **MERGE**. However, a uniqueness constraint **does not automatically require every node to have the customerId property**; if existence is also required, choose a constraint type supported by your edition and version, and guard inputs in your queries.

### 7.2. Writing data while keeping old properties when CSV cells are blank

Assuming the file has already been validated as in Section 6, and in particular all non-empty **joined_on** values are valid ISO dates:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH
  trim(coalesce(row.customer_id, '')) AS customerId,
  trim(coalesce(row.full_name, '')) AS fullName,
  trim(coalesce(row.age, '')) AS ageText,
  trim(coalesce(row.active, '')) AS activeText,
  trim(coalesce(row.email, '')) AS emailText,
  trim(coalesce(row.joined_on, '')) AS joinedText,
  trim(coalesce(row.credit_limit, '')) AS creditText
WHERE customerId <> ''
  AND (ageText = '' OR toIntegerOrNull(ageText) IS NOT NULL)
  AND (activeText = '' OR toBooleanOrNull(toLower(activeText)) IS NOT NULL)
  AND (creditText = '' OR toFloatOrNull(creditText) IS NOT NULL)
MERGE (c:ImportCustomer {customerId: customerId})
SET
  c.fullName = CASE WHEN fullName = ''
                    THEN c.fullName ELSE fullName END,
  c.age = CASE WHEN ageText = ''
               THEN c.age ELSE toIntegerOrNull(ageText) END,
  c.active = CASE WHEN activeText = ''
                  THEN c.active
                  ELSE toBooleanOrNull(toLower(activeText)) END,
  c.email = CASE WHEN emailText = ''
                 THEN c.email ELSE emailText END,
  c.joinedOn = CASE WHEN joinedText = ''
                    THEN c.joinedOn ELSE date(joinedText) END,
  c.creditLimit = CASE WHEN creditText = ''
                       THEN c.creditLimit ELSE toFloatOrNull(creditText) END;
~~~

Processing flow:

1. **LOAD CSV WITH HEADERS** reads each row into **row**.
2. **WITH** normalizes null/empty cells and trims leading and trailing spaces.
3. **WHERE** filters out rows missing **customerId** or failing numeric/boolean conversion. This is **defensive filtering**, not a substitute for reporting and storing rejected records.
4. **MERGE** finds or creates the node using **only customerId**. Do not include **fullName** or **email** in the MERGE key, since those values can change over time.
5. **SET + CASE** converts available values and **keeps existing properties when the file cell is empty**.

If the database initially had none of the three customers, the expected result is three nodes:

| customerId | age | active | joinedOn | creditLimit |
|---|---:|---|---|---:|
| C001 | 29 | true | 2024-06-01 | 2500.5 |
| C002 | *no property* | false | *no property* | *no property* |
| C003 | 34 | true | 2024-02-29 | 0.0 |

Verify afterward:

~~~cypher
MATCH (c:ImportCustomer)
RETURN c.customerId AS customerId,
       c.fullName AS fullName,
       c.age AS age,
       c.active AS active,
       c.email AS email,
       c.joinedOn AS joinedOn,
       c.creditLimit AS creditLimit
ORDER BY customerId;
~~~

**Understand the limitations of this import query:** the WHERE clause drops certain invalid rows without logging rejections automatically; therefore, you must **run the validation query in Section 6** or an upstream validation pipeline and reconcile record counts. It also does not block every business-invalid value (such as an unreasonably large age) or invalid calendar date strings. In production, **reject bad files before importing** or maintain a dedicated rejected-rows table/log in the ingestion pipeline.

### 7.3. If a blank cell means delete the property

Another business rule might require the file to be a **full snapshot**, where an empty email means the email was removed in the source. In that case, you can use:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.email, '')) AS emailText
WHERE customerId <> ''
MATCH (c:ImportCustomer {customerId: customerId})
SET c.email = CASE
                WHEN emailText = '' THEN null
                ELSE emailText
              END;
~~~

**SET c.email = null** causes the **email** property to **disappear** from the node rather than storing a null value. This is a different policy from the query in Section 7.2. Agree on the policy with the data owner before deploying.

### 7.4. If a missing field needs a default value

For example, when creating a new node, a blank **active** source value may be defined as **false**:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.active, '')) AS activeText
WHERE customerId <> ''
MERGE (c:ImportCustomer {customerId: customerId})
ON CREATE SET
  c.active = CASE
               WHEN activeText = '' THEN false
               ELSE toBooleanOrNull(toLower(activeText))
             END;
~~~

**ON CREATE SET** runs only when **MERGE creates a new node**. In the example, if the node already exists, this clause does not alter active. Defaulting missing data to **false** is a **business decision**, not an automatic rule of LOAD CSV. In addition, validation is needed so strings like **yes/no** or **unknown** are not silently converted to null.

## 8. LOAD CSV on large datasets: batching, idempotency, and performance

### 8.1. Why split transactions?

Importing hundreds of thousands or millions of rows in **one** transaction holds a large number of uncommitted changes, increasing memory pressure, lock duration, and rollback cost if an error occurs. Neo4j supports **CALL { ... } IN TRANSACTIONS** to split input rows into smaller transaction batches.

The example below uses a **variable scope clause** of the form **CALL (row, customerId)**, supported starting in **Neo4j 5.23**. This snippet updates only the name to illustrate the batch structure; if all properties are needed, apply the normalization/type conversions from Section 7 inside the subquery.

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row, trim(coalesce(row.customer_id, '')) AS customerId
WHERE customerId <> ''
CALL (row, customerId) {
  MERGE (c:ImportCustomer {customerId: customerId})
  SET c.fullName = CASE
    WHEN trim(coalesce(row.full_name, '')) = ''
    THEN c.fullName
    ELSE trim(row.full_name)
  END
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Important when executing:** **CALL { ... } IN TRANSACTIONS** must be executed in an **implicit transaction**. In Neo4j Browser, prefix the query with **:auto**; in the Java Driver, run it with **session.run(...)** and consume the result—do not wrap it inside an **executeWrite(...)** callback or a manually opened transaction. In applications using Spring Data Neo4j, do not nest this style of import query inside an open **@Transactional** transaction.

For older Cypher versions that do not yet support **CALL (row, customerId)**, you can use the importing **WITH** syntax inside the subquery:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row, trim(coalesce(row.customer_id, '')) AS customerId
WHERE customerId <> ''
CALL {
  WITH row, customerId
  MERGE (c:ImportCustomer {customerId: customerId})
  ON CREATE SET c.fullName = row.full_name
} IN TRANSACTIONS OF 1000 ROWS;
~~~

The **CALL { WITH ... } IN TRANSACTIONS** syntax was used in versions supporting batching prior to the variable scope clause; some older forms emit deprecation warnings on newer servers. Check your actual Neo4j/Cypher version and upgrade plan before choosing a syntax.

### 8.2. Batches can commit partially

If the first batch of 1,000 rows has **committed** and the second batch hits a date error, Neo4j **does not automatically roll back** the first batch. Therefore:

- **MERGE on a constrained identifying key** lets you rerun the import without creating duplicate nodes per ID.
- **SET** fields must follow consistent overwrite/preserve rules. If two CSV rows share the same ID with different values, resolve conflicts at the source.
- Log counts of read, valid, rejected, created, updated, and failed records in the ingestion system.
- Choose batch size based on measurement—for instance testing **500**, **1,000**, and **5,000** rows while observing memory, latency, and throughput; there is no single optimal batch size for every graph.

**USING PERIODIC COMMIT** is legacy import syntax. In modern Neo4j, use **CALL { ... } IN TRANSACTIONS** when batching is required.

### 8.3. Relationships and multiple CSV files

When importing a graph from relational tables, there are typically two passes: (1) import nodes and business keys; (2) read link CSVs, **MATCH** target nodes, and **MERGE/CREATE** the appropriate relationships. Avoid **MERGE**ing an entire complex node–relationship pattern before ensuring endpoints have clear identifiers.

For example, if Customer nodes already exist and a **customer_follows.csv** file contains columns **from_id,to_id**, an illustrative Cypher statement is:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customer_follows.csv' AS row
WITH trim(coalesce(row.from_id, '')) AS fromId,
     trim(coalesce(row.to_id, '')) AS toId
WHERE fromId <> '' AND toId <> ''
MATCH (a:ImportCustomer {customerId: fromId})
MATCH (b:ImportCustomer {customerId: toId})
MERGE (a)-[:IMPORT_FOLLOWS]->(b);
~~~

If either endpoint does not exist, **MATCH** yields no row for it; you must reconcile skipped links. The type name **IMPORT_FOLLOWS** in the example is for practice purposes only.

## 9. Common errors and diagnostics

| Symptom | Common cause | How to check |
|---|---|---|
| **Couldn't load external resource** | File is not in the import dir, URL is unreachable, or permissions are missing | Check server-side file:///, load config, HTTPS connectivity, and permissions |
| **row.customer_id** returns null | Misspelled header, wrong case, trailing spaces, or headerless file | RETURN **keys(row)** and sample rows |
| Import creates a node named **"customer_id"** | Forgot **WITH HEADERS** | Switch to WITH HEADERS and clean up junk data |
| Age or credit limit stored as STRING | Used **row.age** or **row.credit_limit** directly in SET | Use **toIntegerOrNull**, **toFloatOrNull** after validation |
| Boolean **false** disappears as missing data | Overly broad null or default logic | Handle **activeText = ''** separately from **'false'** |
| Missing key causes MERGE error | Passing null into identifying property of MERGE pattern | Filter **customerId <> ''** and report rejected row |
| Value **abc** turns into null | OrNull function converts invalid value to null | Separately check non-empty values that fail conversion |
| Query aborts on **date()** | String is not a valid calendar date or format | Normalize to ISO and validate calendar dates before writing |
| Re-import creates duplicate nodes | Used CREATE or MERGE with mutable properties, or lacked constraint | MERGE on stable key and create uniqueness constraint |
| Batch fails yet some nodes already appear | Earlier batches committed | Inspect batches, reconcile counts, and perform safe rerun |
| CSV uses **;** but columns collapse into one | Wrong delimiter | Use **FIELDTERMINATOR ';'** |

### 9.1. Pre-production checklist

1. Confirm **UTF-8** encoding, delimiter, quoting, and column count matching headers.
2. Preview samples with **LOAD CSV ... RETURN**; check **keys(row)** and row counts.
3. Identify **required** columns, target types, and policies for null/empty strings.
4. Run validation to catch numeric, boolean, date, duplicate-ID, and out-of-range errors.
5. Prepare indexes/constraints for MERGE keys; explicitly define update, clear, or preserve policies for missing properties.
6. Choose an appropriate transaction batch size; test on representative data and verify resumability after failure.
7. Reconcile source row counts, valid row counts, node/relationship counts, and key values after import.

## 10. Practice exercises

**Exercise 1 — Reading headers.** Given a CSV with columns **customer_id,full_name,age**, write a query using **WITH HEADERS** to return columns by name, then rewrite the query to read the data properly when the file **has no headers**.

**Exercise 2 — Preserving boolean values.** Given the three strings **"true"**, **"false"**, and **""**, convert them to boolean or null. Explain why false must not be treated as equivalent to missing data.

**Exercise 3 — Detecting invalid data.** Add rows with **age = abc**, **active = yes**, and an **empty customer_id** to a test source file. Run the error-detection query from Section 6.2 and explain why you should not simply use **toIntegerOrNull** and write immediately.

**Exercise 4 — Snapshot vs. partial update.** Node C001 already has an email, and a new import file leaves email blank. Write two queries corresponding to the policies **keep old email** and **remove email**. Explain the behavior of **SET property = null**.

**Exercise 5 — Repeated imports.** Re-run the MERGE query from Section 7 on an unchanged file. Predict the number of **ImportCustomer** nodes. Then change one customer's name and re-run; explain the difference between **MERGE by ID** and **MERGE by ID + fullName**.

**Exercise 6 — Mid-batch failure.** The first batch committed 1,000 rows, and the second batch encountered an invalid date. Propose a way to locate the offending row, fix the source, and safely rerun without creating duplicate nodes.

## 11. Key takeaways

**LOAD CSV WITH HEADERS** accesses fields by **column name**, whereas the headerless syntax uses **column index**. CSV values must be **normalized**, **validated**, and **intentionally cast** before entering a property graph. Always distinguish **null**, **empty strings**, **0**, **false**, and **invalid values**, because each case can lead to different business outcomes.

For large datasets, use **constrained identifying keys**, **MERGE** on stable keys, **batched transactions**, and reconciliation checks. A correct import is not merely a query that runs without error, but one that produces the **exact entity counts, exact property types, and exact missing-data policy**.

### Official documentation

- [Neo4j Cypher Manual – LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Getting Started – Import CSV data using LOAD CSV](https://neo4j.com/docs/getting-started/data-import/csv-import/)
- [Neo4j Getting Started – Working with CSV files](https://neo4j.com/docs/getting-started/data-import/csv-files/)
- [Neo4j Cypher Manual – Scalar functions and type conversion](https://neo4j.com/docs/cypher-manual/current/functions/scalar/)
- [Neo4j Cypher Manual – CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Cypher Manual – Constraint syntax](https://neo4j.com/docs/cypher-manual/current/constraints/syntax/)
