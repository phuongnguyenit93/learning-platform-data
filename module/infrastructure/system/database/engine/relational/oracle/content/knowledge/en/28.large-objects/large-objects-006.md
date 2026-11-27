# CLOB/BLOB Conversion, Charsets, and Vietnamese Text Handling

When storing and exchanging Vietnamese text in Oracle, three data layers must be distinguished: the Unicode characters the user sees, the bytes used to encode those characters, and the LOB type used to store large content. A CLOB stores text in the database character set; an NCLOB stores text in the national character set; a BLOB stores binary bytes and carries no intrinsic charset meaning.

Many Vietnamese text issues—such as characters turning into question marks, mojibake like “Tiáº¿ng Viá»‡t”, missing diacritics, or errors when importing/exporting files—stem from interpreting bytes with the wrong charset, converting to a charset that cannot represent the characters, or comparing two Unicode strings that have different normalization forms.

This lesson covers:

- Oracle's database character set and national character set.
- Differences among CHAR/VARCHAR2, NCHAR/NVARCHAR2, CLOB/NCLOB, BLOB, and BFILE.
- LOB locators, temporary LOBs, and DBMS_LOB operations.
- Converting CLOB to BLOB and BLOB to CLOB with the right charset.
- Reading/writing large files, streaming, and buffer limits.
- Vietnamese Unicode, precomposed forms, and combining diacritic forms.
- NLS, client encoding, JDBC, SQL*Loader, and diagnosing mojibake errors.

Examples use Oracle Database 19c. Before converting production data, test on a copy, identify source and target charsets, check for unconvertible characters, and verify results using Vietnamese sample data.

## 1. Characters, Charsets, and Bytes Are Three Different Concepts

A displayed string like “Tiếng Việt” is a sequence of characters. When stored or transmitted over a file or network, the character sequence is encoded into bytes using a specific character set/encoding.

Example:

~~~text
Character:   ế
Unicode:     U+1EBF
UTF-8 bytes: E1 BA BF
~~~

The bytes E1 BA BF represent the character ế only when decoded as UTF-8. If the same bytes are interpreted using another charset, the result may be garbled characters or mojibake.

### 1.1. Character Set Is Not Collation

- A character set defines how characters and bytes are represented.
- A collation defines how strings are compared/sorted under linguistic or binary rules.
- Unicode normalization defines equivalent representations of a character as a code point sequence.

These three concepts are related but do not substitute for one another. Changing NLS_SORT does not fix bytes that were decoded incorrectly. Changing a charset does not normalize a string. Unicode normalization cannot recover characters that were already replaced with question marks during a lossy conversion.

### 1.2. AL32UTF8 and UTF8 in Oracle

Oracle generally recommends AL32UTF8 as the database character set for new Unicode applications. AL32UTF8 is Oracle's name for standard UTF-8, supporting full Unicode including characters outside the Basic Multilingual Plane.

The name UTF8 in Oracle is a legacy charset based on CESU-8, which is not identical to standard UTF-8 across all of Unicode. Do not choose UTF8 merely because its name resembles UTF-8. When Vietnamese and modern Unicode support are required, AL32UTF8 is usually the right choice.

## 2. Database Character Set and National Character Set

Oracle has two separate character sets:

1. Database character set: used for CHAR, VARCHAR2, CLOB, and most regular literals/identifiers.
2. National character set: used for NCHAR, NVARCHAR2, and NCLOB.

In Oracle 19c, the national character set is usually AL16UTF16 or legacy UTF8. The database character set and national character set are defined at database creation; changing them should not be treated as a minor configuration tweak.

### 2.1. Checking Database Charsets

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
~~~

NLS_CHARACTERSET reports the charset for CHAR/VARCHAR2/CLOB data. NLS_NCHAR_CHARACTERSET reports the charset for NCHAR/NVARCHAR2/NCLOB.

### 2.2. Checking Charset Name and ID

~~~sql
SELECT
    NLS_CHARSET_ID('AL32UTF8') AS al32utf8_id,
    NLS_CHARSET_NAME(NLS_CHARSET_ID('AL32UTF8')) AS charset_name
FROM dual;
~~~

NLS_CHARSET_ID returns the charset ID; NLS_CHARSET_NAME converts an ID to its name. These functions are useful when passing a charset ID to DBMS_LOB conversion APIs.

### 2.3. Checking Session NLS

~~~sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
~~~

NLS_SESSION_PARAMETERS reflects session NLS settings such as date format, numeric characters, sort, and comparison. It does not replace NLS_DATABASE_PARAMETERS when determining the database character set.

### 2.4. NLS_LANG Is Not the Database Charset

NLS_LANG is a client-side setting in OCI environments consisting of language, territory, and client character set. The charset component describes the encoding the client uses when exchanging data with Oracle over OCI.

Example format:

~~~text
NLS_LANG=VIETNAMESE_VIETNAM.AL32UTF8
~~~

The exact value must match the client environment and the actual encoding of the application/terminal. An incorrect declaration can cause the client to send bytes that get misinterpreted before Oracle stores them.

JDBC Thin uses Java's Unicode mechanism and does not rely on NLS_LANG like OCI does. Do not tweak NLS_LANG to fix a JDBC Thin application if the root cause lies in how the application reads files or handles strings.

## 3. Choosing the Right Character and LOB Data Types

| Type | Content | Character Set / Meaning |
| --- | --- | --- |
| CHAR | Fixed-length character string | Database character set |
| VARCHAR2 | Variable-length character string | Database character set |
| NCHAR | Fixed-length string | National character set |
| NVARCHAR2 | Variable-length string | National character set |
| CLOB | Character large object | Database character set |
| NCLOB | National character large object | National character set |
| BLOB | Binary large object | Raw bytes, no intrinsic charset |
| BFILE | Binary file outside database | OS file bytes, read-only from PL/SQL |

### 3.1. CLOB

CLOB stores large text in the database character set. If the database uses AL32UTF8, CLOB can store Unicode Vietnamese text in that charset.

CLOB operations normally measure offsets in characters, not bytes. Use DBMS_LOB.GETLENGTH to get LOB length in the unit of that LOB type.

### 3.2. NCLOB

NCLOB stores large text in the national character set. It is useful when an application needs NCHAR/NVARCHAR2/NCLOB to maintain national character set semantics independent of the database character set.

If the database already uses AL32UTF8, CLOB is usually sufficient for Unicode Vietnamese data. Do not choose NCLOB merely because the content contains diacritics. Decide based on data contracts, legacy systems, and national character set requirements.

### 3.3. BLOB

BLOB stores bytes. Oracle does not know whether those bytes are UTF-8, JPEG, PDF, ZIP, or another binary format. When converting a BLOB to a CLOB, the application must supply the exact charset of the source bytes.

Do not cast a BLOB to a string just to "see if Vietnamese comes out." Determine encoding from file/API metadata or integration contracts.

### 3.4. BFILE

BFILE is a locator pointing to a file outside the database via a DIRECTORY object. The file is read from the OS and cannot have its content updated through DBMS_LOB; modifying the file requires external tools.

BFILE is suitable when referencing large files on the filesystem. It differs from a BLOB stored in a database segment and has separate DIRECTORY/filesystem permission requirements.

## 4. Character Length and Byte Length

In a multibyte charset such as AL32UTF8, a single character can occupy from one to four bytes. Therefore, character count and byte count are not the same.

### 4.1. LENGTH and LENGTHB

~~~sql
SELECT
    LENGTH('Tiếng Việt') AS char_length,
    LENGTHB('Tiếng Việt') AS byte_length
FROM dual;
~~~

LENGTH returns length in characters; LENGTHB returns the number of bytes in the representation of the charset applied to the expression. Under AL32UTF8, accented letters typically use more bytes than ASCII letters.

### 4.2. LENGTHC, LENGTH2, and LENGTH4

Oracle also provides LENGTHC, LENGTH2, and LENGTH4 counting rules based on Unicode complete characters, UCS2 code units, and UCS4 code points respectively. They can yield different results for supplementary characters or strings with combining marks.

For typical Vietnamese data, LENGTH is the familiar choice. When handling emojis or characters outside the BMP, understand the exact counting unit used by both the application and Oracle APIs.

### 4.3. CLOB and DBMS_LOB.GETLENGTH

~~~sql
SELECT
    DBMS_LOB.GETLENGTH(document_text) AS character_count
FROM documents;
~~~

For CLOB/NCLOB, GETLENGTH returns length in characters. For BLOB, GETLENGTH returns byte count. Do not apply the same interpretation across all LOB types.

### 4.4. BYTE and CHAR Length Semantics

Column declarations:

~~~sql
CREATE TABLE customer_names (
    name_bytes VARCHAR2(100 BYTE),
    name_chars VARCHAR2(100 CHAR)
);
~~~

BYTE semantics limit by bytes; CHAR semantics limit by character units of the database character set. A VARCHAR2(100 CHAR) column is still subject to the datatype's and database version's maximum byte limit.

NLS_LENGTH_SEMANTICS affects the default semantics when creating CHAR/VARCHAR2 columns without specifying BYTE or CHAR. It does not change the database character set and does not convert stored data. For important schemas, declare BYTE/CHAR explicitly to avoid depending on the session creating the table.

## 5. Vietnamese Unicode and Combining Diacritics

Vietnamese uses many accented characters. A displayed character can be represented by a single precomposed code point or by a code point sequence consisting of a base letter and combining marks.

Example for the letter “ế”:

~~~text
Precomposed form:        U+1EBF
Canonical decomposed:    U+0065 U+0302 U+0301
                         e       circumflex acute
~~~

Two strings can look identical visually yet have different code point sequences. Byte comparison, length, and searching can differ if the system does not normalize consistently.

### 5.1. Oracle Does Not Automatically Normalize All Strings to One Form

Storing Unicode strings in AL32UTF8 does not mean Oracle automatically converts every string to NFC or NFD. Two canonically equivalent strings can still be stored as two different code point sequences.

If the application requires consistent comparisons, choose a normalization form—usually NFC for exchanged text—and normalize at input boundaries. Apply the same rule to existing data, new data, searches, and comparison keys.

### 5.2. UNISTR to Construct Unicode Characters

~~~sql
SELECT UNISTR('\1EBF') AS vietnamese_char
FROM dual;
~~~

UNISTR lets you build strings from Unicode code points using escape syntax. It is useful for creating test data independent of the SQL file or terminal encoding.

### 5.3. COMPOSE and DECOMPOSE

Oracle provides COMPOSE and DECOMPOSE to work with Unicode composition/decomposition forms:

~~~sql
SELECT
    COMPOSE(
        UNISTR('\0065') ||
        UNISTR('\0302') ||
        UNISTR('\0301')
    ) AS composed_form,
    DECOMPOSE(UNISTR('\1EBF')) AS decomposed_form
FROM dual;
~~~

COMPOSE produces the precomposed form where possible; DECOMPOSE produces the canonically decomposed form. Test against your database character set and actual system data. Applications can also use their programming language's standard Unicode library to normalize to NFC/NFD.

### 5.4. Normalization Does Not Fix Mojibake

If UTF-8 bytes were decoded into the wrong characters and stored in the database, COMPOSE or NFC cannot know what the original content was. You must go back to the source bytes or a valid backup and re-decode with the original charset.

Do not run bulk conversions on production data merely because Vietnamese diacritics look wrong. First determine whether the error occurred during encoding, decoding, client transmission, or database storage.

## 6. Diagnosing Vietnamese Data

### 6.1. Inspecting ASCII Escape Representation

~~~sql
SELECT
    customer_name,
    ASCIISTR(customer_name) AS escaped_name
FROM customers;
~~~

ASCIISTR represents non-ASCII characters using Unicode escapes, which is useful for distinguishing the actual stored characters. It is not a way to export UTF-8 files.

### 6.2. Inspecting Internal Bytes

~~~sql
SELECT
    customer_name,
    DUMP(customer_name, 1016) AS internal_bytes
FROM customers
WHERE customer_id = 1;
~~~

DUMP displays datatype information, charset, and internal byte representation. Format 1016 requests hex representation along with charset info. This is a diagnostic tool; displayed bytes must be interpreted according to the actual charset.

### 6.3. Comparing Characters and Bytes

~~~sql
SELECT
    'ế' AS sample_text,
    LENGTH('ế') AS char_count,
    LENGTHB('ế') AS byte_count,
    ASCIISTR('ế') AS unicode_escape
FROM dual;
~~~

In AL32UTF8, the precomposed character ế takes three UTF-8 bytes. If byte results differ from expectations, check the database charset, literal source encoding, and client.

### 6.4. Pinpointing Where the Error Happened

A corrupted string may come from:

- A source file created with an encoding other than UTF-8.
- A client declaring a charset that does not match the actual byte encoding.
- An application decoding bytes incorrectly before binding.
- A database character set that cannot represent the source characters.
- Converting CLOB/BLOB with the wrong charset ID.
- Export/import using an incorrectly declared charset.
- Two systems using different normalization forms.

Keep a sample of source bytes, the expected Unicode string, and the read-back result. Looking only at the UI display makes it hard to tell whether the issue is in the database or the font/client.

## 7. LOB Locators and DBMS_LOB

A LOB column does not behave like a small VARCHAR2. PL/SQL normally works with a locator, which is a reference to the LOB value stored in the database or in temporary LOB storage.

DBMS_LOB provides APIs to read, write, compare, truncate, convert, and manage LOBs.

### 7.1. Persistent LOBs and Temporary LOBs

- A persistent LOB is stored in a table column and persists with transactions/the database.
- A temporary LOB is created in temporary LOB storage for intermediate processing; the application must free it when no longer needed.

### 7.2. Creating a Temporary CLOB

~~~sql
DECLARE
    l_text CLOB;
    l_value VARCHAR2(100) := 'Xin chào, tiếng Việt!';
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_text,
        cache => TRUE,
        dur => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_text,
        amount => LENGTH(l_value),
        buffer => l_value
    );

    DBMS_OUTPUT.PUT_LINE(
        'Characters=' || DBMS_LOB.GETLENGTH(l_text)
    );

    DBMS_LOB.FREETEMPORARY(l_text);
END;
/
~~~

For CLOB, amount in WRITEAPPEND is the number of characters written. For BLOB, amount is the number of bytes. Use LENGTH for text buffers and LENGTHB or appropriate RAW length for byte buffers.

### 7.3. Freeing Temporary LOBs on Errors

~~~sql
DECLARE
    l_text CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(l_text, TRUE, DBMS_LOB.CALL);

    -- Process l_text.

    DBMS_LOB.FREETEMPORARY(l_text);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_text) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_text);
        END IF;
        RAISE;
END;
/
~~~

In production applications, ensure temporary LOBs are freed even when errors occur. Do not retain a temporary LOB locator beyond its needed lifecycle.

### 7.4. Obtaining a Persistent CLOB Locator

~~~sql
CREATE TABLE lab_documents (
    document_id NUMBER PRIMARY KEY,
    body CLOB
);
~~~

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(100) := 'Nội dung tiếng Việt';
BEGIN
    INSERT INTO lab_documents(document_id, body)
    VALUES (1, EMPTY_CLOB())
    RETURNING body INTO l_body;

    DBMS_LOB.WRITEAPPEND(
        l_body,
        LENGTH(l_text),
        l_text
    );

    COMMIT;
END;
/
~~~

EMPTY_CLOB() creates an empty LOB with a locator to operate on. INSERT/UPDATE with RETURNING retrieves the locator allowing DBMS_LOB to write content.

## 8. Offsets and Buffers When Reading LOBs

Offset units depend on the LOB type:

| LOB | Offset/Length Unit |
| --- | --- |
| CLOB | Characters |
| NCLOB | Characters |
| BLOB | Bytes |
| BFILE | Bytes |

### 8.1. Reading a CLOB Piecewise

~~~sql
DECLARE
    l_body CLOB;
    l_buffer VARCHAR2(32767);
    l_offset INTEGER := 1;
    l_amount INTEGER;
BEGIN
    SELECT body
    INTO l_body
    FROM lab_documents
    WHERE document_id = 1;

    WHILE l_offset <= DBMS_LOB.GETLENGTH(l_body) LOOP
        l_amount := 1000;

        DBMS_LOB.READ(
            lob_loc => l_body,
            amount => l_amount,
            offset => l_offset,
            buffer => l_buffer
        );

        DBMS_OUTPUT.PUT_LINE(l_buffer);
        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

READ returns the actual number of characters read into amount. CLOB offsets are character positions. A VARCHAR2 buffer in PL/SQL has a byte limit, so the slice size must be small enough for multibyte charsets; do not assume 32,767 characters will always fit in the buffer.

### 8.2. DBMS_LOB.SUBSTR

~~~sql
SELECT DBMS_LOB.SUBSTR(body, 2000, 1)
FROM lab_documents
WHERE document_id = 1;
~~~

SUBSTR extracts a portion of a LOB. For CLOB, amount/offset are measured in characters; for BLOB, in bytes. Returned PL/SQL/SQL buffers have size limits, so SUBSTR is not a way to load an entire large LOB into a single VARCHAR2/RAW variable.

### 8.3. Do Not Split Mid-Multibyte Sequence

Do not perform byte operations on UTF-8 as if every character occupied one byte. Splitting a BLOB in the middle of a UTF-8 sequence can leave an isolated byte slice ending mid-code-unit sequence and unable to decode. For text, read by CLOB character offsets after converting with the right charset; if a byte stream must be split, use a stateful decoder across chunks.

## 9. Converting BLOB to CLOB

A BLOB is just bytes. To turn a BLOB holding a text file into a CLOB, you must know the source charset of those bytes. For example, if a CSV/JSON file is UTF-8 encoded, the source charset ID must be AL32UTF8.

### 9.1. Preparing BLOB and CLOB

~~~sql
CREATE TABLE lab_files (
    file_id NUMBER PRIMARY KEY,
    raw_content BLOB,
    text_content CLOB
);
~~~

### 9.2. CONVERTTOCLOB

~~~sql
DECLARE
    l_source_blob BLOB;
    l_target_clob CLOB;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
    l_lang_context INTEGER := DBMS_LOB.DEFAULT_LANG_CTX;
    l_warning INTEGER;
BEGIN
    SELECT raw_content
    INTO l_source_blob
    FROM lab_files
    WHERE file_id = 1
    FOR UPDATE;

    DBMS_LOB.CREATETEMPORARY(l_target_clob, TRUE, DBMS_LOB.CALL);

    DBMS_LOB.CONVERTTOCLOB(
        dest_lob => l_target_clob,
        src_blob => l_source_blob,
        amount => DBMS_LOB.LOBMAXSIZE,
        dest_offset => l_dest_offset,
        src_offset => l_src_offset,
        blob_csid => NLS_CHARSET_ID('AL32UTF8'),
        lang_context => l_lang_context,
        warning => l_warning
    );

    IF l_warning = DBMS_LOB.WARN_INCONVERTIBLE_CHAR THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Source contains characters that cannot be converted'
        );
    END IF;

    UPDATE lab_files
    SET text_content = l_target_clob
    WHERE file_id = 1;

    COMMIT;
    DBMS_LOB.FREETEMPORARY(l_target_clob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_target_clob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_target_clob);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Key points to understand:

- blob_csid is the charset used to interpret the source bytes in the BLOB.
- src_offset is in bytes; dest_offset is in characters.
- lang_context preserves conversion state, especially when processing across multiple chunks.
- warning reports incomplete conversion conditions, such as unconvertible characters.
- LOBMAXSIZE requests converting all remaining processable content.

This example assumes raw_content actually contains UTF-8. If the source file is Windows-1258, Shift-JIS, or another encoding, you must pass the correct charset ID. Passing AL32UTF8 for Windows-1258 bytes does not turn them into UTF-8; it simply causes Oracle to decode them wrongly.

### 9.3. Checking Warnings

Never ignore DBMS_LOB conversion warnings. If WARN_INCONVERTIBLE_CHAR is returned, content may have had characters substituted or lost. For data requiring fidelity, treat warnings as errors to handle and do not commit unverified conversions.

## 10. Converting CLOB to BLOB

When exporting text to a file or an API expecting UTF-8 bytes, convert the CLOB to a BLOB with the specified target charset.

### 10.1. CONVERTTOBLOB

~~~sql
DECLARE
    l_source_clob CLOB;
    l_target_blob BLOB;
    l_dest_offset INTEGER := 1;
    l_src_offset INTEGER := 1;
    l_lang_context INTEGER := DBMS_LOB.DEFAULT_LANG_CTX;
    l_warning INTEGER;
BEGIN
    SELECT body
    INTO l_source_clob
    FROM lab_documents
    WHERE document_id = 1;

    DBMS_LOB.CREATETEMPORARY(l_target_blob, TRUE, DBMS_LOB.CALL);

    DBMS_LOB.CONVERTTOBLOB(
        dest_lob => l_target_blob,
        src_clob => l_source_clob,
        amount => DBMS_LOB.LOBMAXSIZE,
        dest_offset => l_dest_offset,
        src_offset => l_src_offset,
        blob_csid => NLS_CHARSET_ID('AL32UTF8'),
        lang_context => l_lang_context,
        warning => l_warning
    );

    IF l_warning = DBMS_LOB.WARN_INCONVERTIBLE_CHAR THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Text cannot be represented in target charset'
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'UTF-8 bytes=' || DBMS_LOB.GETLENGTH(l_target_blob)
    );

    DBMS_LOB.FREETEMPORARY(l_target_blob);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_target_blob) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_target_blob);
        END IF;
        RAISE;
END;
/
~~~

Here blob_csid is the target charset used to encode text into bytes. With AL32UTF8, the result is UTF-8 bytes. The converted BLOB can then be written to a file or sent over a binary stream.

### 10.2. Do Not Use CAST_TO_RAW Instead of Charset Conversion

UTL_RAW.CAST_TO_RAW and UTL_RAW.CAST_TO_VARCHAR2 are buffer cast/reinterpretation operations per Oracle rules, not general-purpose Unicode transcoding APIs. Do not use them to turn a database-charset string into UTF-8 bytes without verifying the exact byte representation.

When encoding/decoding to a specific charset is needed, use DBMS_LOB conversion for LOBs or the application language's standard encoding APIs.

## 11. CONVERT for Small Strings and Its Limitations

Oracle provides the CONVERT function for character expressions:

~~~sql
SELECT CONVERT(
    'Vietnamese text',
    'AL32UTF8',
    'WE8MSWIN1252'
)
FROM dual;
~~~

The signature is CONVERT(char, dest_char_set, source_char_set). It fits character strings within return-type limits, not as a streaming tool for large CLOBs/BLOBs. When working with LOBs, use DBMS_LOB.CONVERTTOCLOB or DBMS_LOB.CONVERTTOBLOB.

CONVERT cannot recover data if source_char_set is misdeclared or source bytes were already misinterpreted earlier. When a character does not exist in the target charset, the result may contain replacement characters. Verify representability before using legacy charsets.

### 11.1. Conversion Is Not Transliteration

Character-set conversion maps characters to their representations in another charset. Transliteration replaces characters with visually or phonetically similar forms, such as stripping Vietnamese diacritics. These are two different operations.

Do not degrade Vietnamese into ASCII by switching charsets when the business requirement is to preserve content. If an unaccented version is needed for search, generate a separate field/search key using explicit transliteration rules.

## 12. Reading External Files with BFILE

BFILE lets PL/SQL reference files in a DIRECTORY object. The file remains on the database server's filesystem.

### 12.1. DIRECTORY Object

DBA creates the directory:

~~~sql
CREATE OR REPLACE DIRECTORY import_dir AS '/data/import';
GRANT READ ON DIRECTORY import_dir TO app_user;
~~~

The path is an example on the database server, not a client machine path. The Oracle database process needs appropriate filesystem permissions.

### 12.2. Creating a BFILE Locator

~~~sql
DECLARE
    l_file BFILE;
    l_length INTEGER;
BEGIN
    l_file := BFILENAME('IMPORT_DIR', 'customers_utf8.txt');

    DBMS_LOB.FILEOPEN(l_file, DBMS_LOB.FILE_READONLY);
    l_length := DBMS_LOB.GETLENGTH(l_file);
    DBMS_OUTPUT.PUT_LINE('File bytes=' || l_length);
    DBMS_LOB.FILECLOSE(l_file);
END;
/
~~~

A BFILE locator does not store file content inside the database. It references the file by DIRECTORY object and filename.

### 12.3. Loading Files into LOBs

Oracle provides DBMS_LOB.LOADFROMFILE, LOADBLOBFROMFILE, and LOADCLOBFROMFILE for corresponding scenarios. When loading text into a CLOB, specify the source charset and use a procedure that performs appropriate charset conversion. When loading binary bytes into a BLOB, do not interpret bytes as text.

For UTF-8 text files, verify the file is genuinely UTF-8 and supply the AL32UTF8 charset ID to the read/conversion API. Files with a BOM must be handled according to the file contract: determine whether the BOM is leading metadata to strip or content to preserve.

### 12.4. Privileges and Security

- Grant READ only on required DIRECTORY objects.
- Control filesystem permissions of the Oracle service account.
- Do not allow users to pass arbitrary filesystem paths.
- Validate filenames and file types.
- Limit file sizes and inspect file contents.
- Close BFILEs with FILECLOSE when finished.

## 13. Working with Large LOBs via Streaming

Do not load an entire large CLOB/BLOB into a single VARCHAR2/RAW variable. PL/SQL buffers have limits; read and write in chunks.

### 13.1. Streaming CLOB

Pattern:

1. Obtain the CLOB locator.
2. Initialize offset to 1.
3. Read a chunk using DBMS_LOB.READ or SUBSTR.
4. Process the chunk.
5. Advance offset by the actual number of characters read.
6. Loop up to GETLENGTH.

When using READ, Oracle updates amount to the actual number of units read. Use that value to advance the offset rather than always adding the requested chunk size.

### 13.2. Streaming BLOB

For BLOB, offset and amount are measured in bytes. The buffer is RAW, up to 32,767 bytes in PL/SQL. If the byte stream is UTF-8, do not slice arbitrarily mid-multibyte-sequence and decode each chunk independently. Use a stateful decoder or convert to CLOB first.

### 13.3. Chunk Size and LOB Chunk

DBMS_LOB.GETCHUNKSIZE returns the LOB's storage chunk size. You can consider chunk size when tuning I/O, though application buffers do not always need to match this exact value. Measure with realistic workloads and storage.

### 13.4. Temporary LOBs and Memory

Temporary LOBs consume temporary LOB storage. Creating many LOBs without freeing them can drive up session TEMP usage. Call FREETEMPORARY on both success and exception paths; avoid unnecessary LOB copies.

## 14. Handling Vietnamese on the Client

A database with the right charset can still display Vietnamese improperly if the client sends or reads data with the wrong encoding.

### 14.1. JDBC Thin

Java Strings store text as Unicode. JDBC Thin handles conversion between Java Unicode and the Oracle database character set. For VARCHAR2/CLOB, use character APIs; for BLOB, use byte APIs.

Example writing a CLOB using a character stream:

~~~java
String sql = "insert into lab_documents(document_id, body) values (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql);
     Reader reader = new StringReader("Xin chào, tiếng Việt!")) {
    ps.setLong(1, 10L);
    ps.setCharacterStream(2, reader);
    ps.executeUpdate();
}
~~~

Example reading a CLOB:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "select body from lab_documents where document_id = ?")) {
    ps.setLong(1, 10L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (Reader reader = rs.getCharacterStream("BODY")) {
                char[] buffer = new char[4096];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    String part = new String(buffer, 0, count);
                    System.out.print(part);
                }
            }
        }
    }
}
~~~

For BLOBs, use setBinaryStream/getBinaryStream. Do not use Reader for binary bytes or InputStream for text unless an explicit charset decoder is specified.

### 14.2. NCHAR/NVARCHAR2 and JDBC National Character Methods

If a column is NVARCHAR2 or NCHAR, JDBC provides methods such as setNString/getNString and setNCharacterStream/getNCharacterStream. For VARCHAR2/CLOB, use the standard character methods.

Not every application needs national character types. If the database character set is AL32UTF8, VARCHAR2/CLOB already supports Vietnamese Unicode.

### 14.3. BLOB in JDBC

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "insert into lab_files(file_id, raw_content) values (?, ?)")) {
    ps.setLong(1, 1L);
    try (InputStream in = Files.newInputStream(path)) {
        ps.setBinaryStream(2, in);
        ps.executeUpdate();
    }
}
~~~

This is a byte stream. Even if the file is UTF-8 text, Oracle stores only bytes; the charset must be recorded in metadata or known from a file contract so the BLOB can later be converted to a CLOB.

### 14.4. OCI and SQL*Plus

For OCI clients, NLS_LANG must reflect the charset the client actually uses. Terminal, shell, script files, and applications may each have different encodings; check every boundary.

JDBC Thin does not need NLS_LANG to encode Java Strings. Do not apply an OCI fix to JDBC Thin or vice versa.

## 15. Import/Export and Charsets

### 15.1. SQL*Loader

SQL*Loader can specify the source charset via the CHARACTERSET parameter in the control file or command line. The charset must match the actual encoding of the input file.

Example control file:

~~~text
LOAD DATA
CHARACTERSET AL32UTF8
INFILE 'customers.csv'
INTO TABLE customers
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
  customer_id,
  customer_name
)
~~~

If the file is Windows-1258, do not declare AL32UTF8. Before loading the full file, run a test sample containing Vietnamese letters, tone marks, đ/Đ characters, quotes, and delimiters.

### 15.2. Data Pump

Data Pump export/import can perform charset conversion between source and target databases based on metadata and character representability. If the target charset does not support all source characters, data can be lost or substituted.

Before migration:

- Check NLS_CHARACTERSET and NLS_NCHAR_CHARACTERSET on both databases.
- Check data for characters outside the target charset's repertoire.
- Use Database Migration Assistant for Unicode (DMU) when assessing/migrating a database to Unicode.
- Inspect import/export logs and sample data after import.
- Compare row counts, lengths, byte/character diagnostics, and checksums under appropriate rules.

Do not use ALTER DATABASE CHARACTER SET as a quick way to change charsets on a database already containing data. Changing the database character set requires an Oracle-supported migration process and prior data assessment.

### 15.3. CSV Files and BOM

A UTF-8 BOM is typically the three bytes EF BB BF at the beginning of a file. Some tools accept the BOM, while others treat it as the first character of the first field. Define a BOM policy for each pipeline:

- Whether a BOM is present.
- If present, whether the parser strips the BOM or retains it as content.
- Whether the charset is declared in metadata or merely guessed.
- Whether line endings are LF or CRLF.
- Whether CSV escaping and quoting are handled properly.

Do not blindly strip the first three bytes of every file; only strip them once confirmed to be a BOM.

## 16. Workflow for Troubleshooting Corrupted Vietnamese Strings

When encountering strings like “Tiáº¿ng Viá»‡t”, do not repeatedly convert by guesswork. Trace the bytes and charsets:

1. Obtain a sample of the corrupted data and the original source if available.
2. Identify the encoding of the initial file/request.
3. Identify the client API and how it decodes bytes into strings.
4. Check the database character set and national character set.
5. Use ASCIISTR and DUMP to inspect the stored string.
6. Determine whether the error occurred before binding, during conversion, or on display.
7. Select explicit source and target charsets.
8. Test conversion on a copy or small subset.
9. Verify warnings, replacement characters, byte lengths, and read-back content.
10. Migrate only after results are confirmed by users/business stakeholders.

### 16.1. Two Distinct Failure Modes

**Wrong encoding on decode:** UTF-8 bytes were read as Windows-1252. Recoverable if the source bytes are still intact.

**Lossy encoding to an unsupported charset:** characters were replaced with question marks or replacement characters. If the original bytes were overwritten and no backup exists, you cannot recover them merely by changing charsets again.

### 16.2. Do Not Double-Convert

If the driver already converted Java Unicode to the database charset, do not run CONVERT again as if the data were still raw source bytes. Double conversion can introduce new mojibake.

Document data boundaries:

~~~text
File bytes --decode using source encoding--> Application Unicode String
Application String --driver conversion--> Oracle character data
Oracle CLOB --DBMS_LOB.CONVERTTOBLOB--> UTF-8 bytes
UTF-8 bytes --decode as UTF-8--> Application Unicode String
~~~

Each arrow should perform only one conversion matching the source/target encodings.

## 17. Integrated Example: Storing Vietnamese Text and UTF-8 Files

### 17.1. Create Table

~~~sql
CREATE TABLE lab_vietnamese_docs (
    doc_id NUMBER PRIMARY KEY,
    title VARCHAR2(200 CHAR),
    body CLOB,
    original_file BLOB,
    source_charset VARCHAR2(30)
);
~~~

### 17.2. Store Unicode Text via SQL Literals

~~~sql
INSERT INTO lab_vietnamese_docs (
    doc_id,
    title,
    body,
    source_charset
)
VALUES (
    1,
    UNISTR('Tài liệu tiếng Việt'),
    TO_CLOB(UNISTR('Xin chào! Đây là nội dung tiếng Việt có dấu: ă â ê ô ơ ư đ.')),
    'AL32UTF8'
);
~~~

This example assumes the database character set supports the corresponding literal/Unicode characters. When authoring scripts with external tools, save the script in the right encoding or use UNISTR escapes to avoid errors at the file-reading layer.

### 17.3. Verify

~~~sql
SELECT
    doc_id,
    title,
    LENGTH(title) AS title_chars,
    LENGTHB(title) AS title_bytes,
    DBMS_LOB.GETLENGTH(body) AS body_chars,
    ASCIISTR(title) AS title_escaped
FROM lab_vietnamese_docs
WHERE doc_id = 1;
~~~

### 17.4. Store Original File Bytes

When uploading files, use BLOB to preserve the original bytes and record the source charset in SOURCE_CHARSET if the file is text. For PDFs, images, or ZIPs, SOURCE_CHARSET has no textual meaning; metadata should describe media type/format.

### 17.5. Convert a Text File to CLOB

Read the BLOB from ORIGINAL_FILE and use DBMS_LOB.CONVERTTOCLOB with a charset ID looked up from a validated SOURCE_CHARSET. Never take an arbitrary charset name from a request and concatenate it straight into dynamic SQL. Validate the charset name against a supported allowlist and NLS_CHARSET_ID.

## 18. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Vietnamese turns into question marks | Target charset cannot represent characters or data was already replaced | Identify source/target charsets and restore from bytes/backup |
| String becomes mojibake | Bytes decoded with the wrong charset | Re-decode from original bytes using the right encoding |
| CLOB displays incorrectly | Wrong database charset or client conversion | Check NLS_CHARACTERSET and client encoding |
| BLOB converts to garbage text | Wrong charset ID used for source bytes | Determine the actual encoding of the file |
| Still broken when using NCHAR | Client sent wrong bytes before Oracle received them | Check driver/client encoding; NCHAR does not fix bad input bytes |
| LENGTH differs from LENGTHB | Multibyte characters in AL32UTF8 | Distinguish character units from byte units |
| Exceeds VARCHAR2 limit when reading CLOB | Loading large LOB into a small buffer | Read in chunks with DBMS_LOB |
| UTF-8 chunk breaks at boundary | Splitting bytes mid-multibyte-sequence | Use CLOB offsets or a streaming decoder |
| Temporary LOB grows TEMP | FREETEMPORARY not called | Free on both success and exception paths |
| Conversion loses characters | Ignoring warnings or target charset lacks repertoire | Check warnings and use an appropriate Unicode charset |
| Two identical-looking strings compare differently | Different Unicode composed/decomposed forms | Normalize consistently, e.g., to NFC |
| SQL*Loader corrupts Vietnamese | CHARACTERSET does not match file | Declare the exact source charset |
| Changing NLS_LANG affects JDBC expectations | Confusing OCI settings with JDBC Thin | Check the actual API/driver in use |
| Using CAST_TO_RAW to encode UTF-8 | Confusing byte casting with charset conversion | Use DBMS_LOB conversion or standard encoders |
| Slicing BLOB like CLOB | Confusing byte and character offsets | Use the right API and units for each LOB type |

## 19. Design and Migration Checklist

Before designing columns or pipelines:

- Choose a database character set with full Unicode support, typically AL32UTF8.
- Determine whether NCHAR/NCLOB are truly needed or if CLOB/VARCHAR2 suffice.
- Separate textual data from binary byte data.
- Record the source charset of every text file in metadata.
- Use DBMS_LOB conversion for LOBs and inspect warnings.
- Define a normalization form for Vietnamese data.
- Specify BYTE/CHAR semantics for columns.
- Verify client drivers and file/script encodings.
- Define policies for BOM, line endings, and CSV quoting.
- Prepare backups and rollback plans for charset migrations.
- Test samples with all diacritics, đ/Đ, combining characters, and supplementary characters.
- Never use CONVERT or CAST_RAW as a blind fix for mojibake of unknown origin.

## 20. Practice Exercises

Use LAB_DOCUMENTS, LAB_FILES, and LAB_VIETNAMESE_DOCS from this lesson.

### Exercise 1 — Charset Metadata

Query NLS_DATABASE_PARAMETERS to identify the database and national character sets. Record the results and explain which charset VARCHAR2/CLOB columns use and which charset NVARCHAR2/NCLOB columns use.

### Exercise 2 — Character Length and Byte Length

Compare LENGTH and LENGTHB for the strings “A”, “ế”, “Đặng Thị Ánh”, and an emoji. Explain the differences in AL32UTF8.

### Exercise 3 — Unicode Normalization

Create two strings displaying the same character using precomposed form and combining marks. Compare LENGTH, LENGTHB, and the outputs of COMPOSE/DECOMPOSE. Propose a normalization rule for the application.

### Exercise 4 — Temporary CLOB

Create a temporary CLOB, write multiple Vietnamese segments using WRITEAPPEND, read in chunks, and free it even when an exception occurs.

### Exercise 5 — BLOB to CLOB

Create a BLOB containing UTF-8 bytes from a sample file. Use CONVERTTOCLOB with AL32UTF8. Try declaring the wrong charset on a copy and compare the results.

### Exercise 6 — CLOB to BLOB

Convert a Vietnamese CLOB to a UTF-8 BLOB using CONVERTTOBLOB. Export bytes to a file, read back as UTF-8, and compare contents.

### Exercise 7 — Diagnosing Mojibake

Use ASCIISTR and DUMP to inspect a valid string and an incorrectly decoded string. Identify the step where recovery is possible if source bytes remain.

### Exercise 8 — Import Pipeline

Create UTF-8 CSV files with and without a BOM. Write a SQL*Loader control file with an appropriate CHARACTERSET, test importing, and document the tool's BOM handling behavior.

## 21. Lab Data Cleanup

Run only in the lab schema you created, after finishing the exercises:

~~~sql
DROP TABLE lab_vietnamese_docs PURGE;
DROP TABLE lab_documents PURGE;
DROP TABLE lab_files PURGE;
~~~

If you created additional DIRECTORY objects, tables, or lab files, delete only the resources belonging to your practice environment. Do not drop shared database DIRECTORY objects or files.

## Summary

CLOB and NCLOB store characters in the database character set and national character set; BLOB stores bytes with no intrinsic charset; BFILE references an external file and is read-only. AL32UTF8 is the full-Unicode choice generally suited for new databases. NCHAR/NCLOB do not automatically repair data already decoded wrongly by a client.

When converting BLOB to CLOB, you must know the source bytes' charset and call CONVERTTOCLOB with the right charset ID. When converting CLOB to BLOB, specify the target charset with CONVERTTOBLOB. CLOB offsets are measured in characters and BLOB offsets in bytes; read large LOBs in chunks and free temporary LOBs. Vietnamese can exist in precomposed or combining-diacritic Unicode forms; normalize consistently at application boundaries if stable comparisons are required. When investigating mojibake, trace bytes and encodings at every boundary, check warnings, and never apply repeated guesswork conversions.

## Oracle Reference Documentation

- [Oracle Database Globalization Support Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/) — database/national character sets, Unicode, and globalization.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_LOB (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_LOB.html) — LOB read/write, conversion, temporary LOBs, and BFILEs.
- [Oracle Database SQL Language Reference — Character Datatypes (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html) — CHAR, VARCHAR2, NCHAR, NVARCHAR2, and LOBs.
- [Oracle Database SQL Language Reference — CONVERT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CONVERT.html) — charset conversion for character expressions.
- [Oracle Database SQL Language Reference — Unicode Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Single-Row-Functions.html) — UNISTR, COMPOSE, DECOMPOSE, and string functions.
- [Oracle Database Utilities — SQL*Loader (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/) — data loading and declaring source character sets.
- [Oracle Database Migration Assistant for Unicode](https://docs.oracle.com/en/database/oracle/oracle-database/19/dmuag/) — assessing and migrating databases to Unicode.
- [Oracle JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — exchanging character and LOB data via JDBC.

When deploying on an Oracle release other than 19c, cross-check the Globalization Support Guide, PL/SQL Packages Reference, and driver documentation for your exact version—especially charset IDs, LOB conversion warnings, national character sets, streaming, and Unicode normalization.
