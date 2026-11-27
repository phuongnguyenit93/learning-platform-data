# Oracle Text: Text Indexes, Lexers, and Index Synchronization

Oracle Text is the text search technology inside Oracle Database. Instead of merely comparing values with standard SQL operators, Oracle Text parses content into tokens, builds an inverted index, and provides a query language to search for words, phrases, proximity relationships, word variants, and sections within documents.

A typical Oracle Text query uses the CONTAINS function:

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE CONTAINS(content, 'oracle AND database', 1) > 0
ORDER BY relevance DESC;
~~~

To operate Oracle Text properly, you must understand all three parts:

- **Index architecture**: where the datastore retrieves content from, which formats filters convert, how the lexer splits tokens, how wordlists and stoplists adjust search, and which document regions section groups describe.
- **Query behavior**: CONTAINS, SCORE, search operators, structured filtering, and how results are ranked.
- **Index synchronization**: how DML changes enter the pending queue, when SYNC_INDEX is needed, index optimization, and monitoring indexing errors.

Oracle Text suits document search, CLOB content, product descriptions, contracts, records, and text repositories requiring keyword search. It does not automatically replace every dedicated search system; the choice depends on ranking requirements, update latency, linguistic analysis, storage, and application integration.

## 1. How Does Oracle Text Work?

Oracle Text builds an inverted index. Instead of scanning a list of words across the entire table on every search, the indexing process maps tokens to the documents/rows containing those tokens.

Consider three documents:

| Document | Content |
| --- | --- |
| 101 | Oracle Database supports text search |
| 102 | Oracle Text creates a text index |
| 103 | Database administration and backup |

After tokenization, the conceptual inverted index might be:

| Token | Document IDs |
| --- | --- |
| oracle | 101, 102 |
| database | 101, 103 |
| text | 102 |
| index | 102 |
| backup | 103 |

When searching `oracle AND database`, Oracle Text intersects the posting lists of the two tokens to identify document 101.

This is a conceptual model. Oracle Text's actual storage structure is more complex, with internal index tables, token metadata, posting lists, and data supporting scoring/optimization.

### 1.1. Indexing Flow

~~~text
Application table
     |
     v
Datastore
     |
     v
Filter (if content is a binary document)
     |
     v
Lexer
     |
     +--> tokenization
     +--> case/accent handling
     +--> language rules
     |
     v
Stoplist / Wordlist / Section Group
     |
     v
Oracle Text inverted index
     |
     v
CONTAINS / CATSEARCH / MATCHES
~~~

Each component plays a distinct role:
- Datastore defines how content is retrieved.
- Filter extracts text from formats such as PDF, Word, or HTML when configured.
- Lexer analyzes text into tokens and applies language rules.
- Stoplist excludes words that do not need indexing/searching per policy.
- Wordlist controls fuzzy, stemming, prefix, and substring behavior.
- Section group defines title, heading, body, or XML/HTML regions.
- Storage preference controls certain index storage characteristics.

### 1.2. Inverted Indexes vs. B-Tree Indexes

B-tree indexes suit equality/range lookups on structured values, such as customer_id or created_at. Oracle Text indexes suit searching tokens and relationships between words.

A query can combine both:

~~~sql
SELECT document_id, SCORE(1)
FROM documents
WHERE status = 'PUBLISHED'
  AND CONTAINS(content, 'oracle AND recovery', 1) > 0;
~~~

The status predicate can use a standard B-tree index; CONTAINS uses the Oracle Text index. The optimizer chooses access paths based on statistics and cost.

### 1.3. Main Index Types

Oracle Text has several common index types:

| Index Type | Typical Purpose | Notes |
| --- | --- | --- |
| CONTEXT | Full-text search on documents/large text | Has index synchronization lifecycle; suits document search |
| CTXCAT | Catalog search combining text with structured attributes | Has an index set and separate update semantics |
| CTXRULE | Stores rules/queries to classify incoming text | Uses MATCHES to find matching rules |

Choose the index type based on workload. Do not replace CONTEXT with CTXCAT simply because the name sounds right for a catalog; check data type limits, query interfaces, update behavior, and release documentation.

## 2. Preparing Schema and Data

Example document table with a CLOB column:

~~~sql
CREATE TABLE documents (
    document_id NUMBER
        CONSTRAINT documents_pk PRIMARY KEY,
    title       VARCHAR2(500),
    content     CLOB,
    status      VARCHAR2(20),
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

CLOB content can be plain text, HTML, or text extracted from another system. Oracle Text needs to know how to interpret the content.

### 2.1. Checking Data Types

Oracle Text is commonly used with VARCHAR2, CLOB, and supported document data types via datastores/filters. Exact support depends on index type, datastore, and release.

Check metadata:

~~~sql
SELECT column_name,
       data_type,
       data_length,
       nullable
FROM user_tab_columns
WHERE table_name = 'DOCUMENTS'
ORDER BY column_id;
~~~

If source data resides in a BLOB, identify the document format and how the filter extracts text. Do not assume BLOB bytes are directly indexable UTF-8 text.

### 2.2. Loading Sample Data

~~~sql
INSERT INTO documents(document_id, title, content, status)
VALUES (
    101,
    'Oracle database overview',
    'Oracle Database provides indexing and text search capabilities.',
    'PUBLISHED'
);

INSERT INTO documents(document_id, title, content, status)
VALUES (
    102,
    'Text indexing guide',
    'Oracle Text uses a lexer to identify tokens in documents.',
    'PUBLISHED'
);

COMMIT;
~~~

Commit data before syncing a CONTEXT index manually. If configured with SYNC ON COMMIT, Oracle Text can sync according to the chosen commit semantics.

## 3. Creating a Basic CONTEXT Index

CONTEXT is the common choice for full-text search over CLOBs or document content.

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT;
~~~

After creating the index, inspect it:

~~~sql
SELECT index_name,
       index_type,
       status
FROM user_indexes
WHERE table_name = 'DOCUMENTS';
~~~

Search:

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE CONTAINS(content, 'oracle', 1) > 0
ORDER BY relevance DESC;
~~~

CONTAINS returns a positive value when a document matches the query expression; 0 indicates no match in the query condition. SCORE(label) retrieves the relevance score matching the label passed to CONTAINS. The label is an integer linking CONTAINS and SCORE in the same SQL statement.

### 3.1. Multiple CONTAINS in One Query

~~~sql
SELECT document_id,
       SCORE(1) AS title_score,
       SCORE(2) AS content_score
FROM documents
WHERE CONTAINS(title, 'oracle', 1) > 0
   OR CONTAINS(content, 'recovery', 2) > 0;
~~~

Each CONTAINS uses a separate label if corresponding SCOREs are needed. Labels must match between CONTAINS and SCORE.

### 3.2. Searching with Structured Predicates

~~~sql
SELECT document_id,
       title,
       SCORE(1) AS relevance
FROM documents
WHERE status = 'PUBLISHED'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND CONTAINS(content, 'oracle AND text', 1) > 0
ORDER BY relevance DESC;
~~~

Structured predicates narrow the result set by status and timestamp. Oracle can use B-tree indexes for those columns depending on the plan.

### 3.3. Do Not Use LIKE as a Full Replacement

~~~sql
SELECT *
FROM documents
WHERE content LIKE '%oracle%';
~~~

LIKE can fit simple patterns, yet usually lacks tokenizers, stemming, fuzzy matching, section search, or relevance ranking like Oracle Text. On large CLOBs, leading-wildcard LIKE also typically lacks an efficient access path compared to Oracle Text.

## 4. Lexer — The Component Controlling Tokenization

The lexer splits content into indexable tokens. Lexer rules directly affect search results.

Example string:

~~~text
Oracle-Database, text_search; version 26ai.
~~~

The lexer must decide:
- Does a hyphen split two tokens?
- Is an underscore preserved inside a token?
- Is case distinguished?
- Are Vietnamese diacritics normalized?
- How are digits and letters handled?
- Which punctuation marks are treated as separators vs. join characters?

If the lexer changes, the token set in the index can change. Therefore, changing lexer preferences usually requires evaluating an index rebuild or re-creation per Oracle Text procedures.

### 4.1. BASIC_LEXER

BASIC_LEXER is a common lexer for Latin-based languages and basic rules.

Create preference:

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE(
        'DOCS_LEXER',
        'BASIC_LEXER'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_LEXER',
        'MIXED_CASE',
        'NO'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_LEXER',
        'BASE_LETTER',
        'YES'
    );
END;
/
~~~

Meaning:
- MIXED_CASE=NO generally makes search case-insensitive.
- BASE_LETTER=YES normalizes certain accented characters to base letters per lexer rules.

BASE_LETTER can help with accent-insensitive search, yet requires language testing. In Vietnamese, diacritics distinguish words and meanings. Stripping diacritics increases recall but can also increase false positives. Choose according to product requirements rather than enabling it simply because data contains accents.

### 4.2. PRINTJOINS and SKIPJOINS

BASIC_LEXER has attributes controlling word-joining characters. For example, a hyphen can be treated as:
- A join character kept inside the token.
- A separator creating two tokens.
- A character skipped during tokenization.

Configuration must be based on actual data such as:
- Product codes.
- Emails.
- Filenames.
- Contract numbers.
- Hyphenated compound words.
- Identifiers containing underscores.

Do not change PRINTJOINS/SKIPJOINS without running query regression tests, because this change can cause existing queries to gain or lose matches.

### 4.3. MULTI_LEXER

MULTI_LEXER is used when a dataset contains multiple languages and each document can declare a language. It selects a lexer based on the configured language column value.

Conceptual model:
- A lang column holds language codes.
- A MULTI_LEXER preference maps language codes to lexer preferences.
- Documents are tokenized with the corresponding lexer.

Exact configuration details depend on Oracle-supported language mappings and how language codes are stored. Check language names and attributes for your running release; do not assume every ISO code automatically maps to a lexer.

### 4.4. AUTO_LEXER and WORLD_LEXER

Automatic/broad-language lexers can help when data sources are multilingual or lack reliable language metadata. They carry their own overhead and behavior.

Before choosing:
- Check supported languages.
- Measure tokenization quality.
- Test stemming/fuzzy behavior.
- Evaluate CPU and indexing time.
- Compare results against BASIC_LEXER or MULTI_LEXER.
- Check whether multiple languages are mixed within the same document.

### 4.5. Testing the Lexer

Build a test suite with:
- Uppercase/lowercase.
- Vietnamese diacritics.
- Proper names.
- Hyphenated words.
- Emails/URLs.
- Product codes.
- Numbers with periods/commas.
- Compound words and Unicode characters.
- HTML/XML content.
- Different languages.

Use CTX_DOC or appropriate Oracle Text queries to inspect tokenization if needed. Compare results against business expectations, not just whether preference creation succeeded.

## 5. Stoplist — Excluding Unindexed Words

A stoplist contains words Oracle Text ignores during indexing or querying per configuration. For example, English often has function words like "the", "and", "of". However, stopwords can matter in certain domains or phrases.

### 5.1. Creating a BASIC_STOPLIST

~~~sql
BEGIN
    CTX_DDL.CREATE_STOPLIST(
        'DOCS_STOPLIST',
        'BASIC_STOPLIST'
    );

    CTX_DDL.ADD_STOPWORD(
        'DOCS_STOPLIST',
        'the'
    );

    CTX_DDL.ADD_STOPWORD(
        'DOCS_STOPLIST',
        'and'
    );
END;
/
~~~

Attach the stoplist to a CONTEXT index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'STOPLIST DOCS_STOPLIST'
);
~~~

If the index already exists, do not create a second index with the same name. Plan preference configurations before creating/recreating.

### 5.2. Stopwords Affect Search Semantics

If "and" is excluded by the stoplist, AND in a query acts as a logical operator in the query grammar rather than a text word. Function words in documents may not be stored as normal tokens.

Do not add stopwords merely to shrink index size. Removing words can prevent certain phrases or exact queries from working as expected.

### 5.3. Language-Specific Stoplists

Multilingual data needs matching stoplists. Do not apply an English stoplist to Vietnamese documents and expect good search quality. Check how the lexer recognizes words and which words must be kept in your domain.

## 6. Wordlist — Fuzzy, Stemming, Prefix, and Substring

The wordlist controls query expansion features.

### 6.1. BASIC_WORDLIST

Example:

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE(
        'DOCS_WORDLIST',
        'BASIC_WORDLIST'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_WORDLIST',
        'PREFIX_INDEX',
        'YES'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_WORDLIST',
        'PREFIX_MIN_LENGTH',
        '2'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_WORDLIST',
        'PREFIX_MAX_LENGTH',
        '5'
    );
END;
/
~~~

Attach to the index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'WORDLIST DOCS_WORDLIST'
);
~~~

This example is solely for the wordlist; when using multiple preferences, combine them in one PARAMETERS string.

### 6.2. Prefix Indexing

A prefix index accelerates searches for words starting with a string. For example, a prefix query can match database, databases, or database-related tokens using supported Oracle Text wildcard syntax.

Prefix indexes increase index size and indexing time. Choose min/max prefix lengths based on actual query patterns.

### 6.3. Substring Indexing

A substring index supports certain searches for substrings in the middle of tokens. It can help with product codes or terms requiring partial matching, yet significantly increases storage and maintenance costs.

Do not enable substring indexing for every large corpus if workloads only need full-word search.

### 6.4. Stemming

Stemming finds morphological variants of a word by language, such as singular/plural forms or verb variants in English.

Stemming depends on language support. Do not assume English stemming behaves similarly for Vietnamese. Check Oracle Text documentation for your release and test on domain vocabulary.

### 6.5. Fuzzy Matching

Fuzzy matching finds similarly spelled words to tolerate typos or minor variations. It helps with proper names or free-form user queries, yet can yield many irrelevant results.

Fuzzy behavior can be controlled via wordlist preferences and query operators. Tune thresholds based on data quality; do not assume fuzzy equals synonym search.

## 7. Datastores and Filters

The datastore tells Oracle Text where to fetch content for indexing. Filters extract text from certain document formats.

### 7.1. DIRECT_DATASTORE

DIRECT_DATASTORE is commonly used when text already resides in a table column, such as CLOB/VARCHAR2. It is the default choice for tables storing content directly.

### 7.2. MULTI_COLUMN_DATASTORE

MULTI_COLUMN_DATASTORE combines content from multiple columns into one document for indexing.

For example, a document has:
- title
- abstract
- body

You can create a preference combining columns into one document, then use a section group to search within title/body regions when configured properly.

Benefits:
- One index serves multiple text fields.
- Enables full-document search.
- Can preserve field/section semantics for queries.

Define how NULLs, delimiters, and section boundaries are handled. Never concatenate values without boundaries because a token at the end of one column may merge with a token at the start of the next in some cases.

### 7.3. FILE_DATASTORE

FILE_DATASTORE is used when the table stores references to external files, typically via a directory object and filename. Oracle Text reads files from the filesystem per configuration.

Requirements:
- Oracle DIRECTORY object.
- Appropriate READ privileges.
- File exists and is accessible by the database server process.
- Controlled file paths.
- Security policies and size limits.
- Handling for deleted or moved files.

Paths on the application machine are not automatically paths on the database server.

### 7.4. USER_DATASTORE

USER_DATASTORE lets applications supply content via a user-defined procedure. It suits composite data sources or custom retrieval logic.

The procedure must:
- Return content matching Oracle Text's contract.
- Handle exceptions cleanly.
- Have privileges to read source data.
- Avoid unintended side effects.
- Perform adequately when indexing many rows.

### 7.5. AUTO_FILTER

AUTO_FILTER converts certain document formats to text for Oracle Text indexing. Depending on version and installation, office/PDF/HTML formats may be supported.

If using a BLOB storing files:
- Store MIME/content type or format metadata.
- Choose an appropriate filter.
- Verify the filter supports that file.
- Check for encrypted/password-protected files.
- Check for corrupt or invalid documents.
- Control size and processing time.

Do not assume every PDF/Office document extracts identically. Test real files, especially embedded fonts, scanned images, OCR, passwords, and multilingual documents.

### 7.6. Filters Are Not OCR

Filters generally extract existing text from documents. Scanned PDFs containing only images may lack a text layer. To search text inside scanned images, run a separate OCR pipeline and store the recognized text in an indexed column or datastore.

## 8. Section Groups — Searching by Document Region

Section groups describe internal document structure so queries can restrict searches to specific regions.

HTML example:

~~~html
<html>
  <head><title>Oracle Text Guide</title></head>
  <body>
    <h1>Index synchronization</h1>
    <p>Use CTX_DDL.SYNC_INDEX.</p>
  </body>
</html>
~~~

You may want to find the word Oracle in title, or find SYNC_INDEX in body.

### 8.1. Types of Section Groups

Common types include:
- NULL_SECTION_GROUP: no sections declared.
- BASIC_SECTION_GROUP: manually configured sections.
- HTML_SECTION_GROUP: recognizes sections in HTML.
- AUTO_SECTION_GROUP: automatically detects certain HTML/XML regions.
- XML_SECTION_GROUP: handles XML sections.
- PATH_SECTION_GROUP: supports XML path querying in suitable cases.
- NEWS_SECTION_GROUP: section group for structured news/document formats per release capabilities.

Verify exact names and capabilities against documentation for your running release.

### 8.2. Creating a Section Group for HTML

Example:

~~~sql
BEGIN
    CTX_DDL.CREATE_SECTION_GROUP(
        'DOCS_HTML_SECTIONS',
        'HTML_SECTION_GROUP'
    );
END;
/
~~~

Then attach to the CONTEXT index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'SECTION GROUP DOCS_HTML_SECTIONS'
);
~~~

With filtered HTML or HTML stored in a CLOB, Oracle Text can recognize tags per the section group. Check documentation on tag handling, field sections, and visibility.

### 8.3. Searching Within a Section

If the section group declares a title section, you can query by section name:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(
        content,
        'oracle WITHIN title',
        1
      ) > 0;
~~~

The section name must match the name defined in the section group. Do not use section queries if the index lacks a corresponding section group.

### 8.4. Field Sections and Zone Sections

Field sections typically represent structurally bounded regions like title/meta fields; zone sections represent regions that can contain multiple elements/content. Exact semantics depend on section group type and configuration.

Sections improve precision: matching a keyword in title can carry different weight/meaning than matching in body.

## 9. Combining Preferences in One CONTEXT Index

You can create preferences first and attach them in PARAMETERS.

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE('DOCS_LEXER', 'BASIC_LEXER');
    CTX_DDL.SET_ATTRIBUTE('DOCS_LEXER', 'MIXED_CASE', 'NO');
    CTX_DDL.SET_ATTRIBUTE('DOCS_LEXER', 'BASE_LETTER', 'YES');

    CTX_DDL.CREATE_PREFERENCE('DOCS_WORDLIST', 'BASIC_WORDLIST');
    CTX_DDL.SET_ATTRIBUTE('DOCS_WORDLIST', 'PREFIX_INDEX', 'YES');
    CTX_DDL.SET_ATTRIBUTE('DOCS_WORDLIST', 'PREFIX_MIN_LENGTH', '2');
    CTX_DDL.SET_ATTRIBUTE('DOCS_WORDLIST', 'PREFIX_MAX_LENGTH', '5');

    CTX_DDL.CREATE_STOPLIST('DOCS_STOPLIST', 'BASIC_STOPLIST');
    CTX_DDL.ADD_STOPWORD('DOCS_STOPLIST', 'the');

    CTX_DDL.CREATE_SECTION_GROUP(
        'DOCS_HTML_SECTIONS',
        'HTML_SECTION_GROUP'
    );
END;
/
~~~

Create index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'LEXER DOCS_LEXER
     WORDLIST DOCS_WORDLIST
     STOPLIST DOCS_STOPLIST
     SECTION GROUP DOCS_HTML_SECTIONS
     SYNC (MANUAL)'
);
~~~

Notes:
- Preference names are referenced in index parameters.
- Preferences must exist and the user must have privileges to use them.
- Use clear preference names per schema/application.
- Modifying a preference after the index exists does not always automatically re-index existing content; check rebuild/recreate requirements by attribute and release.
- Keep preference creation scripts alongside migrations/schema deployments.

## 10. Synchronizing a CONTEXT Index

An important operational aspect of CONTEXT indexes is that DML on the source table does not necessarily appear immediately in the text index. Oracle Text uses a pending queue and index synchronization mechanism.

### 10.1. Manual Sync

With manual configuration, after INSERT/UPDATE/DELETE and COMMIT, changes are recorded for later synchronization.

Run:

~~~sql
BEGIN
    CTX_DDL.SYNC_INDEX('DOCUMENTS_TEXT_IDX');
END;
/
~~~

After syncing, Oracle Text queries can find new content reflecting the updated index state.

The passed index name must match the exact index name. Usually invoked in the schema owning the index or with appropriate privileges.

### 10.2. SYNC ON COMMIT

Index synchronization can be configured on commit:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'SYNC (ON COMMIT)'
);
~~~

Sync work is then tied to DML commit per Oracle Text semantics. Measure costs carefully because commit latency can rise, especially when a transaction updates many documents or large documents.

SYNC ON COMMIT is not always suitable for write-heavy workloads. If search delay is acceptable, manual or periodic sync reduces pressure on the transaction path.

### 10.3. Periodic Sync

You can use DBMS_SCHEDULER to run SYNC_INDEX on a schedule:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'SYNC_DOCUMENTS_TEXT',
        job_type        => 'PLSQL_BLOCK',
        job_action      =>
            'BEGIN CTX_DDL.SYNC_INDEX(''DOCUMENTS_TEXT_IDX''); END;',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=MINUTELY;INTERVAL=5',
        enabled         => TRUE
    );
END;
/
~~~

Running every 5 minutes is only an illustrative schedule. Choose intervals based on freshness requirements, DML volume, document sizes, and processing capacity. Monitor job owner, privileges, run failures, and execution duration.

### 10.4. SYNC with Memory

SYNC_INDEX can accept a memory parameter to control resources for synchronization per release syntax. Example:

~~~sql
BEGIN
    CTX_DDL.SYNC_INDEX(
        'DOCUMENTS_TEXT_IDX',
        '64M'
    );
END;
/
~~~

More memory can improve throughput in some workloads, though bigger is not always better. Measure duration, PGA, CPU, I/O, and contention before changing it.

### 10.5. Pending Queue

Oracle Text holds rows awaiting sync in a pending queue. Inspect:

~~~sql
SELECT *
FROM ctx_user_pending;
~~~

This view shows changes waiting to be indexed. Exact columns vary by release; check the dictionary description for detailed queries.

If the pending queue grows continuously:
- The sync job may not be running.
- Sync may be failing.
- DML rate exceeds sync capacity.
- Documents are large or filters are slow.
- Some failing rows are preventing indexing from completing as expected.

### 10.6. Deletes and Updates

When rows are deleted or content changes, Oracle Text must sync to update the inverted index. With manual sync, search results may not reflect the latest state immediately after commit.

Define clear freshness SLAs: e.g., new documents must be searchable within 2 minutes, or hourly batch updates suffice. Do not call SYNC_INDEX after every single row in write-heavy workloads without measuring cost.

## 11. Optimizing a CONTEXT Index

Over time, repeated syncs create multiple index fragments needing merging/optimization. Oracle Text provides CTX_DDL.OPTIMIZE_INDEX.

### 11.1. Optimize FULL

~~~sql
BEGIN
    CTX_DDL.OPTIMIZE_INDEX(
        'DOCUMENTS_TEXT_IDX',
        'FULL'
    );
END;
/
~~~

FULL optimizes/merges the index per Oracle Text semantics. It can consume substantial CPU, I/O, and time. Schedule off-peak and monitor workload impact.

### 11.2. Optimize FAST

~~~sql
BEGIN
    CTX_DDL.OPTIMIZE_INDEX(
        'DOCUMENTS_TEXT_IDX',
        'FAST'
    );
END;
/
~~~

FAST focuses on merging necessary parts per Oracle Text behavior. Effectiveness depends on index fragmentation and release.

### 11.3. Optimize TOKEN

Some releases support optimizing a specific token with a token parameter. Use when targeting a specific token and release syntax is understood. Do not use TOKEN as a general substitute for FULL.

### 11.4. Optimization Schedule

Separate jobs can be scheduled:
- SYNC frequently per freshness SLA.
- OPTIMIZE based on pending/fragmentation volume and workload.
- Track duration, CPU, I/O, and locks.
- Avoid running multiple concurrent optimizations on the same index.
- Check impact on search queries.

There is no need to run FULL after every SYNC. Measure benefits and costs before scheduling.

## 12. Oracle Text Query Language

CONTAINS takes a query expression in Oracle Text syntax. The query string is not a normal SQL predicate; it has its own operators.

### 12.1. AND, OR, NOT

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'oracle AND database', 1) > 0;
~~~

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'oracle OR database', 1) > 0;
~~~

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'oracle NOT backup', 1) > 0;
~~~

Use parentheses to express logical precedence clearly in complex expressions.

### 12.2. Phrase Search

Searching for a phrase:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, '"oracle database"', 1) > 0;
~~~

Phrase syntax follows Oracle Text query grammar; check escaping/quoting when applications build queries from user input.

### 12.3. NEAR

NEAR finds words appearing close together within configured distance and ordering:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(
        content,
        'NEAR((oracle,database), 5, TRUE)',
        1
      ) > 0;
~~~

NEAR parameters and syntax must match Oracle Text query syntax for your release. Use NEAR when word proximity matters; it is not the same as a simple AND.

### 12.4. ABOUT

ABOUT searches by theme/topic when the index is configured to support theme indexing:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'ABOUT(backup recovery)', 1) > 0;
~~~

ABOUT is not mere literal string matching. Theme quality depends on the language knowledge base and configuration; verify availability and language support.

### 12.5. STEM and FUZZY

Some Oracle Text operators expand searches by word stem or similar spelling. For instance, queries can use STEM or FUZZY per supported grammar.

Before enabling:
- Confirm the wordlist has required settings.
- Check language support.
- Check false positives.
- Measure query cost.
- Limit query complexity when input comes from users.

### 12.6. Wildcard and Prefix

Prefix search finds tokens starting with a string when the wordlist supports a prefix index. Example:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'datab%', 1) > 0;
~~~

Exact wildcard syntax and performance depend on the wordlist. Short prefix queries can match huge result sets; enforce length limits and structured filters.

## 13. Ranking and SCORE

Oracle Text can rank documents by relevance based on the query and indexed content.

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE CONTAINS(content, 'oracle AND text', 1) > 0
ORDER BY relevance DESC;
~~~

SCORE returns the score for the matching label. Scores are internal ranking values, not probabilities of correctness or relevance percentages.

### 13.1. Combining Score with Business Sorting

Example prioritizing relevance, then creation date:

~~~sql
SELECT document_id,
       title,
       created_at,
       SCORE(1) AS relevance
FROM documents
WHERE status = 'PUBLISHED'
  AND CONTAINS(content, 'oracle text', 1) > 0
ORDER BY relevance DESC,
         created_at DESC;
~~~

If using pagination, ensure deterministic ordering. Add a tie-breaker key such as document_id to prevent nondeterministic ordering when scores tie.

### 13.2. Score Does Not Replace Relevance Evaluation

Evaluate search quality with a test query set and expected results:
- Precision: are returned results relevant?
- Recall: are relevant documents missed?
- Ranking quality: do good documents appear near the top?
- Latency: how long do queries take?
- Freshness: how soon does new content become searchable?

Do not set arbitrary SCORE thresholds without measuring on a real corpus.

## 14. CTXCAT for Catalog Search

CTXCAT suits certain catalog applications needing text search combined with structured attributes such as category, price, date, or status. It uses an index set to define structured columns accompanying the text index.

### 14.1. Creating an Index Set

Example:

~~~sql
BEGIN
    CTX_DDL.CREATE_INDEX_SET('PRODUCT_CATALOG_SET');

    CTX_DDL.ADD_INDEX(
        'PRODUCT_CATALOG_SET',
        'CATEGORY_ID'
    );

    CTX_DDL.ADD_INDEX(
        'PRODUCT_CATALOG_SET',
        'PRICE'
    );
END;
/
~~~

Create CTXCAT index:

~~~sql
CREATE INDEX product_catalog_text_idx
ON products(description)
INDEXTYPE IS CTXSYS.CTXCAT
PARAMETERS (
    'INDEX SET PRODUCT_CATALOG_SET'
);
~~~

Verify index set syntax and supported structured index types for your release. Only add columns actually participating in catalog searches.

### 14.2. CATSEARCH

CTXCAT is typically queried with CATSEARCH:

~~~sql
SELECT product_id,
       price
FROM products
WHERE CATSEARCH(
        description,
        'wireless headphones',
        'category_id = 10 AND price < 200'
      ) > 0;
~~~

The structured clause of CATSEARCH has its own grammar; do not pass arbitrary full SQL fragments. Verify supported data types and syntax.

### 14.3. When to Choose CONTEXT vs. CTXCAT?

- CONTEXT: general document/full-text search, rich preferences, and sync lifecycle.
- CTXCAT: catalog-style queries combining text and structured attributes via an index set.
- If workloads need flexible SQL queries with many structured predicates, evaluate plans and overall index design; do not assume CTXCAT is always faster.

## 15. CTXRULE for Text Classification

CTXRULE stores queries/rules to apply against incoming text. Instead of users searching documents, the system checks which rules a new document matches.

Example use cases:
- Classifying support tickets by keywords.
- Tagging emails by topic.
- Identifying records belonging to a business category.
- Routing documents to handling teams.

Model:
1. Store each rule as a query expression.
2. Create a CTXRULE index on the rule column.
3. Use MATCHES to find rules matching document text.
4. Store classification results.

CTXRULE has its own query/index semantics. Check rule index creation and MATCHES in release documentation; do not substitute CONTAINS for classification rule lookups.

## 16. Index Synchronization and Result Consistency

An essential operational question: after INSERT/UPDATE/DELETE, when does CONTAINS see the changes?

### 16.1. CONTEXT with Manual Sync

With manual sync:
- DML updates the source table.
- Transaction commits.
- Changes wait in the Oracle Text pending queue.
- SYNC_INDEX processes the changes.
- CONTAINS queries after sync see the newly indexed content.

If an application needs immediate search-after-write, scheduled manual sync may miss SLAs.

### 16.2. SYNC ON COMMIT

SYNC ON COMMIT places synchronization work in the commit path. This reduces stale-search delay at the cost of higher commit overhead and potential throughput impact.

Test:
- Transaction writing a single small document.
- Transaction writing many documents.
- Large documents.
- Concurrent writers.
- Commit latency and rollback behavior.
- Searching immediately after commit.
- Errors when filtering/indexing fails.

### 16.3. Commit and Rollback

Only committed data represents the durable state of the source table. Oracle Text sync processes changes per the index's transaction/indexing semantics. Never assume calling SYNC_INDEX makes uncommitted data searchable.

### 16.4. Separating Write Paths and Search Freshness

If the application has high write throughput:
- Commit DML quickly.
- Sync via a short schedule or worker.
- Monitor pending backlog.
- Inform the UI that the search index has latency if needed.
- Use direct SQL primary-key lookups immediately after writes before the search index syncs.

Never use the Oracle Text index as a source of truth in place of relational tables.

## 17. Monitoring Oracle Text

Oracle Text provides dictionary views to track indexes, preferences, pending work, and errors.

### 17.1. Indexes

~~~sql
SELECT *
FROM ctx_user_indexes;
~~~

DBAs can inspect DBA_CTX_* or ALL_CTX_* views depending on privileges and release. Check dictionary descriptions for column names.

### 17.2. Pending Queue

~~~sql
SELECT *
FROM ctx_user_pending;
~~~

A persistently growing pending queue can indicate sync is not running or cannot keep up.

### 17.3. Index Errors

~~~sql
SELECT *
FROM ctx_user_index_errors;
~~~

This view aids investigating errors raised during indexing. Check rowid, error code/message, and timestamp if those columns exist in your running release.

### 17.4. Index Objects

~~~sql
SELECT *
FROM ctx_user_index_objects;
~~~

This view lets you inspect Oracle Text objects associated with an index. Never modify or delete internal Oracle Text tables directly.

### 17.5. Job Monitoring

If SYNC/OPTIMIZE runs via DBMS_SCHEDULER, check:

~~~sql
SELECT job_name,
       status,
       actual_start_date,
       run_duration,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'SYNC_DOCUMENTS_TEXT'
ORDER BY log_date DESC;
~~~

Column names can differ by release/view. Inspect scheduler run details, job logs, and the alert log if sync fails.

## 18. Troubleshooting Oracle Text Errors

### 18.1. CONTAINS Does Not Find New Documents

Check:
1. Was DML committed?
2. Does the index type require sync?
3. Did SYNC_INDEX succeed?
4. Does the row appear in CTX_USER_PENDING?
5. Are there index errors in CTX_USER_INDEX_ERRORS?
6. Is the document empty or composed solely of stopwords?
7. Did the lexer tokenize as expected?
8. Is the query grammar correct?

### 18.2. ORA-20000 or DRG-... Errors

Oracle Text typically raises DRG- errors, which may be wrapped in ORA-20000. Read the full error stack; the DRG portion usually pinpoints the preference, lexer, filter, query parser, or index operation at fault.

Never resolve errors by directly deleting internal indexes or DR$ tables.

### 18.3. Document Fails to Index

Causes:
- Filter does not support the format.
- Corrupt or password-protected BLOB/file.
- Datastore cannot find the file.
- Missing DIRECTORY privilege.
- User-defined procedure error.
- Invalid character set/encoding.
- Oversized document or timeout.
- Misnamed preference or invalid attribute.

Check CTX_USER_INDEX_ERRORS, the alert log, filter configuration, and source access privileges.

### 18.4. Wrong Search Results

Investigate:
- Lexer case/accent/joins.
- Stoplist.
- Wordlist and stemming/fuzzy settings.
- Section group.
- Document source/filter.
- Whether the index was synced.
- Query expression and escaping.
- Structured predicates and data types.

Create a small reproducible document set and verify tokenization and query semantics before modifying preferences on a production index.

### 18.5. Slow SYNC_INDEX

Check:
- Pending queue growth.
- Number of DML rows.
- Document sizes.
- Filter time.
- CPU/PGA/I/O.
- Concurrent syncs.
- Index fragmentation and optimize schedule.
- Storage placement and tablespaces.

Do not increase memory or run parallel SYNCs without first measuring the bottleneck.

### 18.6. Invalid Index or Index Creation Failure

Read the full error and check:
- CTXSYS component/installation status.
- EXECUTE privilege on CTX_DDL package.
- Tablespace/storage.
- Preference names and attributes.
- Column datatype.
- Filter availability.
- Index errors and database alert log.

Do not broadly grant CTXAPP/CTX_DDL to every user. Grant the minimum privileges required.

## 19. Security and Query Safety

Oracle Text query expressions have their own grammar. If an application directly concatenates user input into a query string, users can craft unintended complex expressions.

### 19.1. Input Control

- Limit query length.
- Validate permitted operators.
- Escape or quote literals per Oracle Text query grammar.
- Never concatenate input into SQL text.
- Use bind variables for the CONTAINS parameter.
- Restrict expensive wildcards/fuzzy/expansions.
- Enforce timeouts/rate limits per use case.
- Prevent users from querying outside their tenant/authorization scope.

Bind variables prevent SQL injection at the SQL layer, yet do not automatically neutralize all operators inside Oracle Text query grammar. Sanitize the query language separately.

### 19.2. Row-Level Authorization

CONTAINS does not automatically guarantee users only see documents they are permitted to read. Combine authorization/tenant predicates:

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE tenant_id = :tenant_id
  AND status = 'PUBLISHED'
  AND CONTAINS(content, :text_query, 1) > 0
ORDER BY relevance DESC;
~~~

Authorization must be enforced server-side. Never rely on filters sent by the browser.

### 19.3. File Datastore

If using FILE_DATASTORE:
- Restrict DIRECTORY objects.
- Never let users pass arbitrary paths.
- Check for symlinks/path traversal at the ingestion layer.
- Restrict file types and sizes.
- Scan for malware per policy.
- Never let database processes read arbitrary host directories.

## 20. Operations and Capacity Design

Oracle Text indexes have dedicated storage and maintenance costs. Forecast:
- Document count.
- Total text volume after filtering.
- Unique token count.
- DML frequency.
- Update/delete ratio.
- Sync frequency.
- Fuzzy/prefix/substring requirements.
- Number of languages.
- Filter CPU.
- Query concurrency.

### 20.1. Index Growth

An inverted index can be larger or smaller than the raw text depending on token distribution, metadata, wordlists, and storage structures. Never use a fixed multiplier to forecast every corpus.

Benchmark with a representative sample and measure:
- Segment size.
- Pending queue.
- Sync throughput.
- Optimize duration.
- Query latency.
- DML commit latency.

### 20.2. Backup and Recovery

Oracle Text indexes are database objects protected by database backups. After restore/recovery, verify components, index status, preferences, source data, and query functionality. If index rebuilds are needed, estimate time and resources.

Never back up internal DR$ tables separately via application scripts and treat that as a supported restore strategy.

### 20.3. Partitioning

Some architectures can use local/domain indexes or appropriate partitioning strategies. Oracle Text partitioned index support varies by index type and release. Check version documentation and partition restrictions before designing; do not assume every CONTEXT index partitions the same way as a B-tree.

## 21. Controlled Preference/Index Rollout Process

An Oracle Text migration should follow these steps:

1. Check CTXSYS component and privileges.
2. Check datatypes and content sources.
3. Create preferences with versioned names.
4. Test lexer/stoplist/wordlist/section group on sample data.
5. Create the index in a test environment.
6. Run query regression tests.
7. Measure index build, sync, optimize, and query times.
8. Test DML and search freshness.
9. Deploy the production index during a maintenance window if needed.
10. Set up SYNC jobs and monitoring.
11. Save rollback/drop index scripts.
12. Monitor pending/errors after cutover.

### 21.1. Changing Preferences

When changing lexers/wordlists/stoplists/section groups, determine whether the change requires rebuilding/recreating the index. Do not assume modifying a preference object automatically re-tokenizes all already-indexed data.

Use versioned preference names, such as DOCS_LEXER_V2, to test new settings and compare against the old configuration on a clone.

### 21.2. Dropping an Index

~~~sql
DROP INDEX documents_text_idx;
~~~

Dropping the index removes the search index, not the documents table. Before dropping:
- Confirm the application no longer depends on the query.
- Have a recreation plan.
- Estimate build time.
- Save preference definitions.
- Confirm storage and maintenance window.

Never drop internal DR$ tables directly.

## 22. Complete Example: Document Search

Create table:

~~~sql
CREATE TABLE knowledge_documents (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(300),
    body        CLOB,
    category    VARCHAR2(40),
    status      VARCHAR2(20),
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Create lexer and wordlist:

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE('KNOWLEDGE_LEXER', 'BASIC_LEXER');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_LEXER', 'MIXED_CASE', 'NO');

    CTX_DDL.CREATE_PREFERENCE('KNOWLEDGE_WORDLIST', 'BASIC_WORDLIST');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_WORDLIST', 'PREFIX_INDEX', 'YES');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_WORDLIST', 'PREFIX_MIN_LENGTH', '2');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_WORDLIST', 'PREFIX_MAX_LENGTH', '5');
END;
/
~~~

Create CONTEXT index:

~~~sql
CREATE INDEX knowledge_body_text_idx
ON knowledge_documents(body)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'LEXER KNOWLEDGE_LEXER
     WORDLIST KNOWLEDGE_WORDLIST
     SYNC (MANUAL)'
);
~~~

Insert document:

~~~sql
INSERT INTO knowledge_documents(
    document_id, title, body, category, status
)
VALUES (
    1,
    'Oracle Text operations',
    'Oracle Text indexes documents using a lexer and inverted index.',
    'DATABASE',
    'PUBLISHED'
);

COMMIT;
~~~

Sync:

~~~sql
BEGIN
    CTX_DDL.SYNC_INDEX('KNOWLEDGE_BODY_TEXT_IDX');
END;
/
~~~

Search:

~~~sql
SELECT document_id,
       title,
       SCORE(1) AS relevance
FROM knowledge_documents
WHERE category = 'DATABASE'
  AND status = 'PUBLISHED'
  AND CONTAINS(body, 'oracle AND lexer', 1) > 0
ORDER BY relevance DESC,
         document_id;
~~~

Check pending/errors:

~~~sql
SELECT * FROM ctx_user_pending;

SELECT *
FROM ctx_user_index_errors
WHERE err_index_name = 'KNOWLEDGE_BODY_TEXT_IDX';
~~~

Column names in error views can vary between releases; if querying specific columns fails, inspect the view's dictionary description before adjusting.

## 23. Oracle Text Operations Checklist

- [ ] Confirm the appropriate index type: CONTEXT, CTXCAT, or CTXRULE.
- [ ] Confirm correct column and datastore.
- [ ] Confirm filter supports source formats.
- [ ] Confirm lexer and language mappings.
- [ ] Test case/accent/joins on real data.
- [ ] Confirm stoplist does not exclude searchable business terms.
- [ ] Configure wordlist for fuzzy/stem/prefix/substring needs.
- [ ] Configure section group if field/zone search is required.
- [ ] Save preference and index creation scripts.
- [ ] Choose manual, periodic, or ON COMMIT sync.
- [ ] Measure commit latency and search freshness.
- [ ] Monitor CTX_USER_PENDING.
- [ ] Monitor CTX_USER_INDEX_ERRORS.
- [ ] Schedule optimizations based on workload.
- [ ] Verify query plans and SCORE behavior.
- [ ] Sanitize query grammar from user input.
- [ ] Combine tenant/authorization predicates.
- [ ] Verify backup/recovery and rebuild feasibility.
- [ ] Establish capacity estimates and maintenance windows.
- [ ] Retest after changing preferences or Oracle RUs.

## 24. Self-Practice Exercises

1. What types of search workloads does Oracle Text solve?
2. How does an inverted index differ from a B-tree index?
3. Diagram the flow of datastore, filter, lexer, wordlist, and inverted index.
4. Distinguish CONTEXT, CTXCAT, and CTXRULE.
5. Write the statement to create a CONTEXT index on a CLOB.
6. How are CONTAINS and SCORE linked together?
7. Why is SCORE not a relevance probability?
8. What is the role of the lexer?
9. How do MIXED_CASE and BASE_LETTER affect search?
10. Why can BASE_LETTER increase false positives with Vietnamese text?
11. How do PRINTJOINS and SKIPJOINS affect tokenization?
12. When should MULTI_LEXER be used?
13. How can a stoplist alter search results?
14. What features does a wordlist support?
15. What costs does prefix indexing increase?
16. How does stemming differ from fuzzy matching?
17. Distinguish DIRECT_DATASTORE and FILE_DATASTORE.
18. Does AUTO_FILTER replace OCR?
19. What is a section group used for?
20. Write a query searching for a token within a title section.
21. How does manual sync work?
22. How does SYNC ON COMMIT affect commit latency?
23. Write the CTX_DDL.SYNC_INDEX command.
24. What are CTX_USER_PENDING and CTX_USER_INDEX_ERRORS used for?
25. When is OPTIMIZE_INDEX needed?
26. Distinguish a CONTEXT query from CATSEARCH.
27. What problem does CTXRULE/MATCHES solve?
28. Why don't SQL binds automatically prevent query operator injection in Oracle Text grammar?
29. Design a sync/optimize schedule for a document repository with heavy DML.
30. Build a test plan for changing a lexer from MIXED_CASE=YES to NO and BASE_LETTER=YES.

**Oracle Text converts content into an inverted index through datastores, filters, and lexers; wordlists, stoplists, and section groups govern how tokens are stored and searched.** With CONTEXT indexes, clearly design the freshness contract and choose manual, periodic, or ON COMMIT sync based on workload; monitor the pending queue, indexing errors, and optimization costs. When changing lexers or preferences, test tokenization and query regressions before applying changes to production indexes.
