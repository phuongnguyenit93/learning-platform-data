# Reading and Writing CLOB/BLOB Using DBMS_LOB

Oracle Database provides LOB (*Large Object*) data types to store large content such as long text, documents, images, audio, or binary data. Two commonly used types are **CLOB** (*Character Large Object*) for character data and **BLOB** (*Binary Large Object*) for binary data. In PL/SQL, the `DBMS_LOB` package provides procedures and functions to read, write, append, copy, truncate, and inspect LOB contents through a locator.

When working with LOBs, you must distinguish the locator from the actual content. A locator is a reference Oracle uses to access a LOB value. A program can retrieve a locator from a column and pass it to `DBMS_LOB.READ`, `WRITE`, `WRITEAPPEND`, or other operations. For large LOBs, this approach enables processing in chunks rather than loading the entire content into a single PL/SQL variable.

## 1. How Do CLOB and BLOB Differ?

| Characteristic | CLOB | BLOB |
|---|---|---|
| Content | Text and character data | Arbitrary binary data |
| Unit for length, offset, and amount in DBMS_LOB | Characters | Bytes |
| Typical PL/SQL buffer | VARCHAR2 | RAW |
| Examples | JSON, XML, article bodies, long text | Images, PDFs, compressed files, encrypted data |
| Character conversion | According to CLOB and buffer character sets | Content is not interpreted as text |

Oracle also has NCLOB for storing character data in the national character set. This section focuses on CLOB and BLOB; processing principles are similar, though an appropriate buffer type must be used for NCLOB.

Do not store arbitrary binary data in a CLOB just because it can be represented as a string. Conversely, if storing text in a BLOB, the application must agree on the encoding when converting between bytes and characters. For images, PDFs, or binary files, use BLOB to preserve exact bytes.

## 2. LOB Locators, NULL, and Empty LOBs

A LOB column can have a NULL value or contain an empty LOB. These two cases differ:

- **NULL:** the column does not yet have a valid locator to access content.
- **Empty LOB:** has a valid locator, but its length is 0.

In SQL, Oracle provides `EMPTY_CLOB()` and `EMPTY_BLOB()` to initialize an empty LOB. This is a common pattern when inserting a row and retrieving the locator using the `RETURNING` clause.

Example creating a table to store documents:

~~~sql
CREATE TABLE document_store (
  document_id    NUMBER PRIMARY KEY,
  title          VARCHAR2(200) NOT NULL,
  text_content   CLOB,
  binary_content BLOB,
  created_at     TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Inserting a row with two empty LOBs:

~~~sql
INSERT INTO document_store (
  document_id,
  title,
  text_content,
  binary_content
)
VALUES (
  1,
  'Sample document',
  EMPTY_CLOB(),
  EMPTY_BLOB()
);

COMMIT;
~~~

If a LOB column is NULL, initialize it with `EMPTY_CLOB()` or `EMPTY_BLOB()` before calling write operations. Write procedures require a valid, writable locator.

## 3. Commonly Used DBMS_LOB Operations

| API | Purpose |
|---|---|
| `GETLENGTH` | Retrieve LOB length |
| `SUBSTR` | Extract a portion of content as VARCHAR2 or RAW |
| `READ` | Read data into a PL/SQL buffer |
| `WRITE` | Write data at a specified offset |
| `WRITEAPPEND` | Append data to the end of a LOB |
| `APPEND` | Append the entire content of a source LOB to a destination LOB |
| `COPY` | Copy a portion from a source LOB to a destination LOB |
| `TRIM` | Truncate a LOB to a new length |
| `INSTR` | Find the position of a pattern in a LOB |
| `COMPARE` | Compare the contents of two LOBs or two LOB ranges |
| `CREATETEMPORARY` | Create a temporary LOB in memory/temporary tablespace |
| `FREETEMPORARY` | Free a temporary LOB |
| `OPEN`, `CLOSE` | Open and close a LOB when managing a sequence of operations |

APIs have overloads for multiple LOB types. Pass the matching locator and buffer types: CLOB typically pairs with VARCHAR2, BLOB with RAW.

## 4. Getting Length and Reading a Slice with SUBSTR

`DBMS_LOB.GETLENGTH` returns the length of a LOB. For CLOB, length is measured in characters; for BLOB, length is measured in bytes.

~~~sql
DECLARE
  l_clob CLOB;
  l_blob BLOB;
  l_text VARCHAR2(32767);
  l_raw  RAW(32767);
  l_clob_length NUMBER;
  l_blob_length NUMBER;
BEGIN
  SELECT text_content, binary_content
    INTO l_clob, l_blob
    FROM document_store
   WHERE document_id = 1;

  IF l_clob IS NOT NULL THEN
    l_clob_length := DBMS_LOB.GETLENGTH(l_clob);
    DBMS_OUTPUT.PUT_LINE('CLOB characters: ' || l_clob_length);

    IF l_clob_length > 0 THEN
      l_text := DBMS_LOB.SUBSTR(l_clob, 4000, 1);
      DBMS_OUTPUT.PUT_LINE('CLOB prefix: ' || l_text);
    END IF;
  END IF;

  IF l_blob IS NOT NULL THEN
    l_blob_length := DBMS_LOB.GETLENGTH(l_blob);
    DBMS_OUTPUT.PUT_LINE('BLOB bytes: ' || l_blob_length);

    IF l_blob_length > 0 THEN
      l_raw := DBMS_LOB.SUBSTR(l_blob, 100, 1);
      DBMS_OUTPUT.PUT_LINE('BLOB prefix (hex): ' || RAWTOHEX(l_raw));
    END IF;
  END IF;
END;
/
~~~

The second parameter of `SUBSTR` is the number of characters for CLOB and the number of bytes for BLOB. The third parameter is the starting offset, 1-based. The return value is constrained by VARCHAR2 or RAW buffer limits; therefore, `SUBSTR` is suitable for retrieving a small slice, not for loading an entire large LOB into a single variable.

## 5. Reading LOBs in Chunks with READ

When content exceeds PL/SQL buffer limits, read in chunks. `DBMS_LOB.READ` takes the locator, the amount to read, the offset, and the output buffer. The `amount` parameter is IN OUT: pass the desired amount to read, and after the call it contains the actual amount read. The next offset must advance by this actual amount.

### Reading CLOB

~~~sql
DECLARE
  l_clob   CLOB;
  l_buffer VARCHAR2(32767);
  l_length NUMBER;
  l_offset NUMBER := 1;
  l_amount BINARY_INTEGER;
  c_chunk_chars CONSTANT PLS_INTEGER := 8000;
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1;

  IF l_clob IS NULL THEN
    RETURN;
  END IF;

  l_length := DBMS_LOB.GETLENGTH(l_clob);

  WHILE l_offset <= l_length LOOP
    l_amount := LEAST(c_chunk_chars, l_length - l_offset + 1);

    DBMS_LOB.READ(
      lob_loc => l_clob,
      amount  => l_amount,
      offset  => l_offset,
      buffer  => l_buffer
    );

    -- Process l_buffer here, e.g., pass to a text parser.
    DBMS_OUTPUT.PUT_LINE('Read characters: ' || l_amount);

    l_offset := l_offset + l_amount;
  END LOOP;
END;
/
~~~

### Reading BLOB

~~~sql
DECLARE
  l_blob   BLOB;
  l_buffer RAW(32767);
  l_length NUMBER;
  l_offset NUMBER := 1;
  l_amount BINARY_INTEGER;
  c_chunk_bytes CONSTANT PLS_INTEGER := 32767;
BEGIN
  SELECT binary_content
    INTO l_blob
    FROM document_store
   WHERE document_id = 1;

  IF l_blob IS NULL THEN
    RETURN;
  END IF;

  l_length := DBMS_LOB.GETLENGTH(l_blob);

  WHILE l_offset <= l_length LOOP
    l_amount := LEAST(c_chunk_bytes, l_length - l_offset + 1);

    DBMS_LOB.READ(
      lob_loc => l_blob,
      amount  => l_amount,
      offset  => l_offset,
      buffer  => l_buffer
    );

    -- Process l_buffer here, e.g., write to an application byte stream.
    DBMS_OUTPUT.PUT_LINE('Read bytes: ' || l_amount);

    l_offset := l_offset + l_amount;
  END LOOP;
END;
/
~~~

In the CLOB example, the chunk size is set to 8,000 characters so the VARCHAR2 buffer has enough room for multibyte character sets like AL32UTF8. In the BLOB example, RAW is read up to 32,767 bytes per call. Choose a size suited to buffer limits and how the application processes data.

Do not advance the offset by a fixed requested chunk size. Oracle may return fewer units than requested, for instance due to buffer limits or character conversion. Use the `l_amount` value returned after `READ` to update the offset. When looping based on `GETLENGTH`, avoid attempting to read past the end of the LOB.

## 6. Writing New CLOB and BLOB Data with WRITEAPPEND

To write a new LOB, you can INSERT a row with `EMPTY_CLOB()` and `EMPTY_BLOB()`, obtain the locators with `RETURNING`, and then write the content. Example:

~~~sql
DECLARE
  l_clob CLOB;
  l_blob BLOB;

  l_text VARCHAR2(1000) := 'Document text content.';
  l_bytes RAW(32767) := UTL_RAW.CAST_TO_RAW('Sample PDF or bytes');
BEGIN
  INSERT INTO document_store (
    document_id,
    title,
    text_content,
    binary_content
  )
  VALUES (
    2,
    'New document',
    EMPTY_CLOB(),
    EMPTY_BLOB()
  )
  RETURNING text_content, binary_content
       INTO l_clob, l_blob;

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_blob,
    amount  => UTL_RAW.LENGTH(l_bytes),
    buffer  => l_bytes
  );

  COMMIT;
END;
/
~~~

In this example:

- `RETURNING` retrieves the locators of the two newly initialized LOBs.
- For CLOB, `LENGTH(l_text)` counts the number of characters to write.
- For BLOB, `UTL_RAW.LENGTH(l_bytes)` counts the number of bytes to write.
- `UTL_RAW.CAST_TO_RAW` converts text in the database character set into bytes. This is only to illustrate a byte sequence; when storing real files, the application must provide the original file bytes rather than converting file content into a string.

Changes to LOBs stored in a table belong to the current transaction. `COMMIT` confirms the changes; `ROLLBACK` discards uncommitted changes according to Oracle's standard transaction rules.

## 7. Writing or Overwriting at an Offset with WRITE

`DBMS_LOB.WRITE` writes a buffer starting at a specified offset. It overwrites existing data in that region; the operation does not insert extra bytes or characters to shift subsequent content forward.

Example replacing a leading portion of a CLOB:

~~~sql
DECLARE
  l_clob CLOB;
  l_text VARCHAR2(100) := 'HEADER';
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  IF l_clob IS NULL THEN
    RAISE_APPLICATION_ERROR(-20001, 'CLOB is NULL');
  END IF;

  DBMS_LOB.WRITE(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    offset  => 1,
    buffer  => l_text
  );

  COMMIT;
END;
/
~~~

For CLOB, `amount` and `offset` are measured in characters. For BLOB, these two parameters are measured in bytes. When writing to an existing LOB, you must lock the row containing the LOB with `SELECT ... FOR UPDATE` within the transaction before modifying the locator.

If you write a string shorter than the old content, the old tail remains. For example, writing `ABC` at offset 1 of CLOB `ABCDEFGHIJ` produces `ABCDEFGHIJ`, because the first three characters are overwritten with their same values. Writing `XYZ` produces `XYZDEFGHIJ`, not `XYZ`. To replace the entire content, trim the LOB to 0 first and then write the new content, or use an appropriate UPDATE statement.

## 8. Appending Content: WRITEAPPEND and APPEND

Both APIs serve similar purposes but accept different inputs:

- `WRITEAPPEND(dest_lob, amount, buffer)`: appends a VARCHAR2 or RAW buffer to the end of a LOB.
- `APPEND(dest_lob, src_lob)`: appends the entire content from a compatible source LOB to a destination LOB.

Example appending a text snippet:

~~~sql
DECLARE
  l_clob CLOB;
  l_text VARCHAR2(200) := CHR(10) || 'Appended section.';
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  COMMIT;
END;
/
~~~

Example appending a source CLOB to a destination CLOB:

~~~sql
DECLARE
  l_destination CLOB;
  l_source      CLOB;
BEGIN
  SELECT text_content
    INTO l_destination
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  SELECT text_content
    INTO l_source
    FROM document_store
   WHERE document_id = 2;

  DBMS_LOB.APPEND(l_destination, l_source);

  COMMIT;
END;
/
~~~

The destination must be a writable locator. Source and destination must have compatible LOB types. To append binary data, use BLOB with a RAW buffer or a source BLOB.

## 9. Copying a Range with COPY

`DBMS_LOB.COPY` copies a specified number of bytes or characters from a source LOB to a destination LOB. You can specify the starting position in the source and the write position in the destination.

~~~sql
DECLARE
  l_destination CLOB;
  l_source      CLOB;
  l_amount      NUMBER;
BEGIN
  SELECT text_content
    INTO l_destination
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  SELECT text_content
    INTO l_source
    FROM document_store
   WHERE document_id = 2;

  l_amount := LEAST(100, DBMS_LOB.GETLENGTH(l_source));

  IF l_amount > 0 THEN
    DBMS_LOB.COPY(
      dest_lob    => l_destination,
      src_lob     => l_source,
      amount      => l_amount,
      dest_offset => DBMS_LOB.GETLENGTH(l_destination) + 1,
      src_offset  => 1
    );
  END IF;

  COMMIT;
END;
/
~~~

The example above appends up to the first 100 characters of the source CLOB to the end of the destination CLOB. For BLOB, `amount`, `dest_offset`, and `src_offset` are measured in bytes. If the goal is to replace the entire destination content, call `TRIM(dest_lob, 0)` before COPY; COPY does not automatically remove the old tail if the new data is shorter.

## 10. Truncating a LOB with TRIM

`DBMS_LOB.TRIM` changes a LOB's length to the specified number of bytes or characters. It is commonly used to remove trailing data or prepare a LOB before rewriting its entire content.

~~~sql
DECLARE
  l_clob CLOB;
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  DBMS_LOB.TRIM(l_clob, 0);

  COMMIT;
END;
/
~~~

After `TRIM(l_clob, 0)`, the CLOB remains an empty LOB with a locator; it does not become NULL. For BLOB, the passed length is in bytes. Do not confuse `TRIM` with `ERASE`: TRIM removes everything past the new length at the end, whereas ERASE clears content within a range without necessarily shortening the LOB.

## 11. Creating and Freeing Temporary LOBs

Temporary LOBs (*temporary LOB*) are useful when constructing or transforming intermediate content before writing it to a table LOB column. Use `DBMS_LOB.CREATETEMPORARY` to create a locator and `DBMS_LOB.FREETEMPORARY` to free it when no longer needed.

~~~sql
DECLARE
  l_temp_clob CLOB;
  l_text      VARCHAR2(100) := 'Temporary content';
BEGIN
  DBMS_LOB.CREATETEMPORARY(
    lob_loc => l_temp_clob,
    cache   => TRUE,
    dur     => DBMS_LOB.SESSION
  );

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_temp_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  DBMS_OUTPUT.PUT_LINE(
    'Temporary CLOB length: ' || DBMS_LOB.GETLENGTH(l_temp_clob)
  );

  IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_temp_clob);
  END IF;
EXCEPTION
  WHEN OTHERS THEN
    IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
      DBMS_LOB.FREETEMPORARY(l_temp_clob);
    END IF;
    RAISE;
END;
/
~~~

The `dur` parameter determines the lifetime of the temporary LOB: `DBMS_LOB.SESSION` keeps it for the session, while `DBMS_LOB.CALL` limits it to the call. When the application no longer needs the locator, free the temporary LOB to avoid holding resources longer than necessary. In production code, ensure the cleanup branch executes even when exceptions occur.

Temporary LOBs differ from persistent LOBs in tables. Persistent LOBs are managed along with rows and transactions; temporary LOBs are created specifically for intermediate work and have an application-managed lifecycle.

## 12. OPEN and CLOSE

`DBMS_LOB.OPEN` and `DBMS_LOB.CLOSE` allow opening a LOB in read-only or read-write mode when performing multiple operations. Opening does not replace the row-locking requirement for persistent LOBs being modified.

~~~sql
DECLARE
  l_clob CLOB;
  l_text VARCHAR2(100) := 'Additional text';
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  DBMS_LOB.OPEN(l_clob, DBMS_LOB.LOB_READWRITE);

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  DBMS_LOB.CLOSE(l_clob);
  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    IF l_clob IS NOT NULL AND DBMS_LOB.ISOPEN(l_clob) = 1 THEN
      DBMS_LOB.CLOSE(l_clob);
    END IF;
    RAISE;
END;
/
~~~

OPEN/CLOSE is optional for many routine LOB operations. Once you open a LOB, close it before ending the transaction. If an exception occurs, close the LOB in the error handler and re-raise the error. For a single simple write, you can call WRITE or WRITEAPPEND directly on a locked locator without OPEN/CLOSE.

## 13. Searching and Comparing Content

In addition to reading and writing, DBMS_LOB provides search and comparison functions:

- `INSTR(lob_loc, pattern, offset, nth)` finds the `nth` occurrence of a pattern starting from the specified offset. For CLOB, positions are in characters; for BLOB, the pattern and positions are in bytes.
- `COMPARE(lob_1, lob_2, amount, offset_1, offset_2)` compares the contents of two LOBs or two LOB ranges. A return value of 0 indicates the compared ranges are equal; a non-zero value indicates they differ.

Example searching for a string in a CLOB:

~~~sql
DECLARE
  l_clob CLOB;
  l_pos  INTEGER;
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1;

  l_pos := DBMS_LOB.INSTR(l_clob, 'Oracle', 1, 1);

  IF l_pos = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Text not found');
  ELSE
    DBMS_OUTPUT.PUT_LINE('Text found at character ' || l_pos);
  END IF;
END;
/
~~~

If the LOB is large, consider the number of searches and data range sizes. `INSTR` scans the LOB for the supplied pattern; it does not replace an indexed full-text search engine with linguistic analysis.

## 14. Rules for Offset, Amount, and Buffer Size

This is the most error-prone area when working with LOBs:

| LOB Type | Offset | Amount | Common Buffer |
|---|---|---|---|
| CLOB | Characters, 1-based | Characters | VARCHAR2 |
| BLOB | Bytes, 1-based | Bytes | RAW |

Key principles to remember:

1. Offsets in DBMS_LOB start at 1, not 0.
2. CLOB measures offset and amount in characters; BLOB measures them in bytes.
3. PL/SQL buffer sizes are bounded. VARCHAR2 and RAW in PL/SQL have a maximum limit of 32,767 bytes.
4. For CLOBs using multibyte character sets, a given number of characters can occupy more bytes in the buffer. Therefore, the character chunk size must be chosen small enough.
5. With READ, advance the offset by the actual amount returned after each read.
6. Do not load an entire large LOB into VARCHAR2 or RAW just for processing; use a chunk loop or pass the locator to an application layer capable of streaming.

In addition, do not use `LENGTHB` to compute amount for a CLOB. `LENGTHB` counts bytes of a string while the CLOB API requires character units. Similarly, do not use `LENGTH` instead of byte count when writing a BLOB; for RAW, use `UTL_RAW.LENGTH`.

## 15. Common Errors and How to Avoid Them

**NULL locator:** calling READ or WRITE on a NULL locator is not equivalent to operating on an empty LOB. Check for NULL and initialize the LOB with EMPTY_CLOB/EMPTY_BLOB or an appropriate INSERT/UPDATE.

**Not locking the row when modifying a persistent LOB:** when modifying a locator retrieved from a column, lock the row with `SELECT ... FOR UPDATE` inside a transaction. This prevents uncontrolled concurrent updates.

**Confusing characters with bytes:** using LENGTHB for CLOB or LENGTH for RAW can produce incorrect amounts. Always choose units matching the LOB type.

**Buffer too large:** requesting too much data in a single READ or SUBSTR call can exceed VARCHAR2/RAW limits. Split data into chunks and advance the offset after each read.

**Overwriting when intending to insert:** WRITE replaces data at the offset without shifting subsequent data. To append, use WRITEAPPEND or APPEND.

**Forgetting old trailing data:** writing a shorter piece at the beginning of a LOB does not delete the remaining portion. To replace everything, TRIM to 0 before writing or replace the locator with a new LOB per appropriate design.

**Not freeing temporary LOBs:** call FREETEMPORARY when processing finishes and also in exception branches.

**Treating binary data as text:** a BLOB can contain bytes that are invalid in a character set. Do not cast RAW to VARCHAR2 for processing without knowing the encoding.

**Printing entire LOBs with DBMS_OUTPUT:** DBMS_OUTPUT has line and buffer size limits; it is not a transport mechanism for large content. Only print lengths, short debugging snippets, or transfer data to the application layer.

## 16. Transactions and LOB Storage

Persistent LOBs reside in table rows and are governed by transactions. If you use `SELECT ... FOR UPDATE` to obtain a locator and then call WRITE, WRITEAPPEND, TRIM, or COPY, changes are committed or rolled back together with the transaction holding that row.

Do not commit midway just to free memory while constructing a persistent LOB if doing so breaks business transaction boundaries. Let the calling layer decide the appropriate commit timing.

Oracle supports storing LOBs using SecureFiles and BasicFiles depending on version, configuration, and tablespace. SecureFiles is the modern choice for many systems because it supports advanced LOB storage features. Choosing storage format, compression, deduplication, encryption, and caching should be based on data characteristics, Oracle version, and operational policy; it does not change the principles of using locators and DBMS_LOB APIs in PL/SQL.

## 17. General Processing Pattern

When you need to read or write CLOB/BLOB data, you can follow this sequence:

1. Obtain the locator from the LOB column or create an empty/temporary LOB.
2. Check whether the locator is NULL.
3. For persistent LOBs being modified, lock the row containing the LOB within the transaction.
4. Confirm the exact LOB type to choose the buffer type and offset/amount units.
5. Read in chunks with READ, or write with WRITE/WRITEAPPEND.
6. If copying or appending two LOBs is needed, use COPY or APPEND.
7. Close the LOB if OPEN was called; free temporary LOBs if created.
8. Commit or roll back at the appropriate transaction boundary.

For example, an application uploading a PDF file can receive bytes from an HTTP request, create a document row with EMPTY_BLOB, obtain the locator via RETURNING, write each RAW chunk to the BLOB with WRITEAPPEND, and commit once the entire file has been written successfully. When downloading, the application reads the BLOB in chunks and streams each byte slice back to the client. For long descriptions or large JSON payloads, the same workflow applies to CLOB, except the buffer is VARCHAR2 and offset/amount are measured in characters.

## 18. Conclusion

`DBMS_LOB` is the primary PL/SQL API for controlled manipulation of CLOBs and BLOBs. CLOB stores text and uses character units; BLOB stores binary bytes and uses byte units. Locators enable reading and writing directly on a LOB without loading all data into a single PL/SQL variable.

Use GETLENGTH and SUBSTR for small slices, READ to read in chunks, WRITE to write at an offset, WRITEAPPEND or APPEND to append, COPY to copy, TRIM to truncate, and CREATETEMPORARY/FREETEMPORARY to manage intermediate data. When modifying persistent LOBs, lock rows appropriately and manage transactions; when using temporary LOBs, release resources. Accurately distinguishing characters from bytes and choosing the right buffer type will prevent offset, amount, and memory-limit errors when handling large data.
