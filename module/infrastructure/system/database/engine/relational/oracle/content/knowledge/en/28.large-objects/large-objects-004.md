# Temporary LOBs: Creation, Freeing, and Space Control

In Oracle Database, a **temporary LOB** is a temporary LOB object created to hold intermediate data during processing. Temporary LOBs are commonly used when PL/SQL concatenates large CLOB strings, transforms BLOB content, produces results from a LOB operation, or builds a document before writing it to a persistent LOB column.

A temporary LOB has a locator just like other LOBs, but its lifecycle is managed by CALL or SESSION duration. Temporary LOB data uses temporary tablespace resources and may use the buffer cache depending on options chosen at creation time. Creating many temporary LOBs or keeping them longer than necessary can cause a session to consume significant TEMP space and increase pressure on the system.

The primary management operations are in the DBMS_LOB package:

- **CREATETEMPORARY**: creates a temporary BLOB/CLOB/NCLOB.
- **ISTEMPORARY**: checks whether a locator points to a temporary LOB.
- **FREETEMPORARY**: frees a temporary LOB when no longer needed.
- **GETLENGTH, WRITE, WRITEAPPEND, APPEND, COPY, READ, TRIM**: manipulates LOB data.
- **DBMS_LOB.CALL and DBMS_LOB.SESSION**: selects the lifecycle of the temporary LOB.

It is critical to distinguish a temporary LOB from a persistent LOB in a table. A locator retrieved from a table's CLOB/BLOB column normally points to persistent data; you must not call FREETEMPORARY on that locator. Temporary LOBs must be freed promptly, especially in long-running sessions or multi-batch processing.

## 1. LOB Locators and Temporary LOBs

LOB (Large Object) is a data type used to store large content:

- **BLOB**: binary data, such as images, PDF files, audio, or encrypted content.
- **CLOB**: character data in the database character set.
- **NCLOB**: character data in the national character set.
- **BFILE**: a locator to a binary file outside the database; BFILE is read-only from Oracle's perspective and is not a temporary LOB created with CREATETEMPORARY.

A CLOB/BLOB variable in PL/SQL holds a **LOB locator**. A locator is a reference allowing PL/SQL/SQL to operate on a LOB value. Do not confuse a locator with the entire LOB content copied into a VARCHAR2 or RAW variable.

### 1.1. Persistent LOB

A persistent LOB is a LOB stored in a table column or another persistent LOB storage object.

~~~sql
CREATE TABLE document_store (
    document_id NUMBER PRIMARY KEY,
    body        CLOB
);
~~~

When reading:

~~~sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT body
    INTO l_body
    FROM document_store
    WHERE document_id = 10;
END;
/
~~~

L_BODY receives a locator to the CLOB value in the DOCUMENT_STORE row. This locator does not turn persistent data into a temporary LOB. Do not call DBMS_LOB.FREETEMPORARY(l_body) merely because the locator sits in a PL/SQL variable.

If you need to update a persistent LOB, you must follow row DML/locking and transaction rules. Changes to a persistent LOB can be COMMITted or ROLLBACKed with the transaction.

### 1.2. Temporary LOB

A temporary LOB is created to hold intermediate data, not a persistent LOB value in a table column. Example:

~~~sql
DECLARE
    l_work CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_work,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_work,
        amount  => LENGTH('Temporary content'),
        buffer  => 'Temporary content'
    );

    DBMS_OUTPUT.PUT_LINE(
        'Length=' || DBMS_LOB.GETLENGTH(l_work)
    );

    DBMS_LOB.FREETEMPORARY(l_work);
END;
/
~~~

Temporary LOBs are commonly used for:
- Combining multiple pieces of content into a single large CLOB.
- Building a binary file before saving it to a table.
- Receiving intermediate results from LOB operations.
- Transforming or normalizing large content.
- Constructing payloads before sending them to the application layer.

### 1.3. Quick Comparison

| Characteristic | Persistent LOB | Temporary LOB |
| --- | --- | --- |
| Where value is stored | LOB column / persistent storage object | Temporary LOB storage, using TEMP resources |
| Lifecycle | Tied to row/transaction and storage rules | CALL or SESSION |
| COMMIT/ROLLBACK | Applies to persistent data changes | Not a mechanism to free temporary LOBs |
| Created by | INSERT/UPDATE or LOB column operations | CREATETEMPORARY or certain operations creating implicit temporary LOBs |
| Freed by | DML/DDL and object management | FREETEMPORARY or end of duration |
| ISTEMPORARY | Returns 0 | Returns 1 |
| Can call FREETEMPORARY | No | Yes |

## 2. Creating a Temporary LOB with CREATETEMPORARY

Common syntax:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    lob_loc IN OUT NOCOPY CLOB,
    cache   IN BOOLEAN,
    dur     IN PLS_INTEGER DEFAULT DBMS_LOB.SESSION
);
~~~

There is a corresponding overload for BLOB. NCLOB is also supported with the matching datatype.

Parameters:

- **lob_loc**: locator variable receiving the new temporary LOB.
- **cache**: TRUE if temporary LOB data should be cached in the buffer cache; FALSE to skip caching per this option.
- **dur**: lifetime duration, typically DBMS_LOB.CALL or DBMS_LOB.SESSION.

If dur is omitted, the default is session duration. For code creating a temporary LOB to process within a single PL/SQL call, consider passing DBMS_LOB.CALL explicitly to bound its lifecycle.

### 2.1. Creating a CLOB

~~~sql
DECLARE
    l_clob CLOB;
    l_text VARCHAR2(100) := 'Oracle temporary CLOB';
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_clob,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_clob,
        amount  => LENGTH(l_text),
        buffer  => l_text
    );

    DBMS_OUTPUT.PUT_LINE(
        DBMS_LOB.GETLENGTH(l_clob)
    );

    DBMS_LOB.FREETEMPORARY(l_clob);
END;
/
~~~

For CLOB, amount in WRITEAPPEND is measured in characters. LENGTH(l_text) returns the character count; do not mechanically replace it with LENGTHB.

### 2.2. Creating a BLOB

BLOB holds bytes. Example creating a temporary BLOB from an ASCII string converted to RAW:

~~~sql
DECLARE
    l_blob BLOB;
    l_raw  RAW(32767);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_blob,
        cache   => FALSE,
        dur     => DBMS_LOB.CALL
    );

    l_raw := UTL_RAW.CAST_TO_RAW('Binary payload');

    DBMS_LOB.WRITEAPPEND(
        lob_loc => l_blob,
        amount  => UTL_RAW.LENGTH(l_raw),
        buffer  => l_raw
    );

    DBMS_OUTPUT.PUT_LINE(
        'Bytes=' || DBMS_LOB.GETLENGTH(l_blob)
    );

    DBMS_LOB.FREETEMPORARY(l_blob);
END;
/
~~~

For BLOB, amount is measured in bytes. UTL_RAW.LENGTH returns the number of bytes in the RAW buffer.

### 2.3. CACHE TRUE and FALSE

The CACHE parameter affects how Oracle handles buffer caching for temporary LOB data:

- **TRUE**: allows LOB data to be cached in the buffer cache.
- **FALSE**: creates the LOB without caching under this option.

No single option is optimal for all cases. CACHE TRUE can help if the same data is read repeatedly; CACHE FALSE can suit large intermediate data that is rarely re-read. Measure on real workloads because cache choice also affects memory pressure and system I/O.

CACHE does not determine whether a LOB is temporary, nor does it control lifetime. Lifetime is governed by dur.

### 2.4. Verifying That a Locator Was Created Successfully

After CREATETEMPORARY, you can check:

~~~sql
IF l_clob IS NOT NULL
   AND DBMS_LOB.ISTEMPORARY(l_clob) = 1
THEN
    DBMS_OUTPUT.PUT_LINE('Temporary CLOB is ready');
END IF;
~~~

ISTEMPORARY returns 1 if the locator points to a temporary LOB and 0 otherwise. This check is useful in shared helpers or cleanup code that may receive various kinds of locators.

## 3. CALL Duration and SESSION Duration

A temporary LOB has a lifecycle selected at creation time.

### 3.1. DBMS_LOB.CALL

DBMS_LOB.CALL limits the temporary LOB to the duration of the corresponding PL/SQL call. When the call ends, Oracle frees the temporary LOB per that duration.

~~~sql
CREATE OR REPLACE PROCEDURE build_message AS
    l_message CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_message,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_message,
        LENGTH('Generated inside this call'),
        'Generated inside this call'
    );

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_message));
    -- Temporary LOB with CALL duration is freed when the call ends.
END build_message;
/
~~~

If the locator is not needed after the procedure ends, CALL duration is usually the sensible choice. It is still good practice to free early once processing finishes inside long calls to reduce held resources.

### 3.2. DBMS_LOB.SESSION

DBMS_LOB.SESSION keeps the temporary LOB throughout the session, or until explicitly freed:

~~~sql
DECLARE
    l_buffer CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_buffer,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_buffer,
        LENGTH('Keep for later calls'),
        'Keep for later calls'
    );

    -- Can pass locator to other routines in the same session.
    -- Must call FREETEMPORARY when no longer needed.
END;
/
~~~

Session duration is useful when a LOB must survive across multiple PL/SQL calls in the same session. On the flip side, forgetting to free it can leave the LOB holding TEMP resources for a long time.

### 3.3. COMMIT Does Not Replace FREETEMPORARY

Temporary LOBs have CALL/SESSION durations, not transaction lifetimes. COMMIT or ROLLBACK is not a command to free a session-duration temporary LOB.

For example, a session creates a temporary LOB with DBMS_LOB.SESSION and then runs COMMIT; the locator can still remain usable until FREETEMPORARY is called or the session terminates.

Do not rely on COMMIT as a way to clean up temporary LOBs.

### 3.4. Choosing Duration Based on Locator Ownership

| Requirement | Duration to Consider |
| --- | --- |
| Create content, process, and discard within one call | DBMS_LOB.CALL |
| Need to keep locator across multiple procedure calls in the same session | DBMS_LOB.SESSION |
| Function/procedure returns locator for caller to continue using | Define lifetime clearly; usually needs session duration and caller is responsible for freeing |
| Session pool reuses sessions for other requests | Prefer CALL if sufficient; free all SESSION LOBs before returning connection to pool |

Especially with connection pools, sessions do not close after each request. Forgotten SESSION LOBs can persist when the connection is reused for the next user/request.

## 4. FREETEMPORARY and ISTEMPORARY

These two routines form the foundation of cleanup.

### 4.1. Checking ISTEMPORARY

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_clob) = 1 THEN
    DBMS_OUTPUT.PUT_LINE('This locator refers to a temporary LOB');
ELSE
    DBMS_OUTPUT.PUT_LINE('This is not a temporary LOB');
END IF;
~~~

ISTEMPORARY helps distinguish a temporary LOB from a persistent LOB locator. When a locator has not been initialized, check IS NOT NULL before invoking other LOB operations.

### 4.2. Freeing with FREETEMPORARY

~~~sql
DBMS_LOB.FREETEMPORARY(l_clob);
~~~

After freeing, do not continue reading/writing through that locator. You can reset the variable to NULL to make clear that the code no longer owns the locator:

~~~sql
DBMS_LOB.FREETEMPORARY(l_clob);
l_clob := NULL;
~~~

Only call FREETEMPORARY on a temporary LOB locator. Do not use it to free a persistent LOB retrieved from a table.

### 4.3. Cleanup on Both Success and Error Paths

PL/SQL has no FINALLY block like some other languages. You can place cleanup in both the normal path and the exception handler:

~~~sql
DECLARE
    l_clob CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_clob,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.WRITEAPPEND(
        l_clob,
        LENGTH('Work data'),
        'Work data'
    );

    -- Perform work with L_CLOB.

    IF l_clob IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_clob) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_clob);
    END IF;

    l_clob := NULL;

EXCEPTION
    WHEN OTHERS THEN
        IF l_clob IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_clob) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_clob);
        END IF;

        l_clob := NULL;
        RAISE;
END;
/
~~~

In production systems, cleanup can be encapsulated into a helper. If cleanup itself raises an error, establish a clear policy so it does not accidentally mask the original exception; log the cleanup error if possible.

### 4.4. Free as Early as Possible

Do not hold a temporary LOB until the end of a long procedure if processing finished early. Free it right after its last use. This is especially important when:
- A procedure processes many documents sequentially.
- Each row creates a temporary CLOB.
- A batch creates many temporary BLOBs.
- Sessions are kept alive long-term in an application server.
- Multiple workers/sessions share TEMP.

## 5. Implicitly Created Temporary LOBs

Not all temporary LOBs are created directly with CREATETEMPORARY. Certain LOB operations or SQL/PLSQL expressions can create an **implicit temporary LOB** as an intermediate result.

Example concatenating CLOBs:

~~~sql
DECLARE
    l_clob CLOB;
BEGIN
    l_clob := TO_CLOB('Part A') || TO_CLOB('Part B');

    DBMS_OUTPUT.PUT_LINE(
        'Is temporary=' || DBMS_LOB.ISTEMPORARY(l_clob)
    );
END;
/
~~~

The result of an expression can be a temporary CLOB. Use ISTEMPORARY to determine whether a locator is temporary and manage it according to the expression semantics and Oracle version in use.

### 5.1. Repeated LOB Concatenation Can Create Many Intermediate Copies

The following pattern can be expensive when content is very large:

~~~sql
l_document := l_document || p_piece;
~~~

When repeated thousands of times, concatenation can allocate/copy intermediate values. This increases CPU, memory, and temporary LOB activity.

Instead, create one temporary CLOB and append to the same locator:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    l_document,
    TRUE,
    DBMS_LOB.CALL
);

DBMS_LOB.WRITEAPPEND(
    l_document,
    LENGTH(p_piece),
    p_piece
);
~~~

Inside a loop, call WRITEAPPEND for each piece. This approach typically controls intermediate data creation much better.

### 5.2. Not Every LOB Result Is Temporary

A function can return a locator to a persistent LOB, or return a new temporary LOB. Do not infer the locator kind solely from the CLOB/BLOB datatype.

When deciding on cleanup, check ISTEMPORARY. For a persistent locator, the caller must not free it with FREETEMPORARY.

### 5.3. Implicit Temporary LOBs Still Need Management

Implicitly created temporary LOBs may be managed by Oracle for the duration of the operation/call, but in long-running or heavily looped code, avoid creating unnecessary intermediate values. When receiving a temporary locator with clear ownership, free it once finished.

## 6. EMPTY_CLOB/EMPTY_BLOB Are Not CREATETEMPORARY

A common misconception is treating EMPTY_CLOB() or EMPTY_BLOB() as ways to create a temporary LOB. Those two functions are normally used to initialize an empty value for a persistent LOB column in INSERT/UPDATE.

~~~sql
INSERT INTO document_store(document_id, body)
VALUES (10, EMPTY_CLOB());
~~~

Afterward, you can retrieve the newly created row's locator with RETURNING:

~~~sql
DECLARE
    l_body CLOB;
    l_text VARCHAR2(100) := 'Persistent document content';
BEGIN
    INSERT INTO document_store(document_id, body)
    VALUES (11, EMPTY_CLOB())
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

Here L_BODY points to the new row's persistent LOB. Do not call FREETEMPORARY on this locator.

| Creation Method | Purpose | Is It a Temporary LOB? |
| --- | --- | --- |
| DBMS_LOB.CREATETEMPORARY | Create an intermediate LOB | Yes |
| EMPTY_CLOB() in INSERT/UPDATE | Initialize an empty persistent CLOB column | No |
| EMPTY_BLOB() in INSERT/UPDATE | Initialize an empty persistent BLOB column | No |
| SELECT lob_column INTO l_lob | Retrieve a locator to a stored LOB | Usually persistent, not temporary |

## 7. Manipulating Temporary LOB Data

DBMS_LOB provides many routines to write, read, append, and copy data.

### 7.1. WRITEAPPEND

WRITEAPPEND adds a buffer to the end of a LOB:

~~~sql
DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
);
~~~

For CLOB/NCLOB, amount is measured in characters. For BLOB, amount is measured in bytes.

### 7.2. APPEND

APPEND appends content from a source LOB to a destination LOB:

~~~sql
DBMS_LOB.APPEND(
    dest_lob => l_target,
    src_lob  => l_source
);
~~~

The two locators must have compatible LOB types. APPEND takes a source LOB locator, whereas WRITEAPPEND takes a scalar buffer such as VARCHAR2 or RAW.

### 7.3. WRITE

WRITE writes a buffer at a specified offset:

~~~sql
DBMS_LOB.WRITE(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    offset  => 1,
    buffer  => l_text
);
~~~

Offsets for CLOB/NCLOB are measured in characters; offsets for BLOB are measured in bytes. Writing into the middle of a LOB can overwrite existing data; do not confuse WRITE with WRITEAPPEND.

### 7.4. READ and SUBSTR

Read a portion of a LOB without loading the entire content into a variable:

~~~sql
DECLARE
    l_clob  CLOB;
    l_piece VARCHAR2(4000);
BEGIN
    -- Assume L_CLOB is already initialized and contains data.
    l_piece := DBMS_LOB.SUBSTR(
        lob_loc => l_clob,
        amount  => 4000,
        offset  => 1
    );
END;
/
~~~

DBMS_LOB.SUBSTR returns VARCHAR2 on CLOB and RAW on BLOB. PL/SQL buffers have size limits, so read in chunks when handling large LOBs. With multibyte characters, the number of characters returned may be fewer than the requested amount to fit the buffer's byte limit.

### 7.5. COPY Creates an Independent Data Copy

Locator assignment:

~~~sql
l_alias := l_source;
~~~

usually only copies the locator/reference; it does not create an independent copy of the LOB data. Two variables may reference the same LOB. If you need a separate copy, create a destination LOB and use DBMS_LOB.COPY:

~~~sql
DECLARE
    l_source CLOB;
    l_copy   CLOB;
BEGIN
    -- Assume L_SOURCE already points to a populated CLOB.
    DBMS_LOB.CREATETEMPORARY(
        l_copy,
        TRUE,
        DBMS_LOB.CALL
    );

    DBMS_LOB.COPY(
        dest_lob    => l_copy,
        src_lob     => l_source,
        amount      => DBMS_LOB.GETLENGTH(l_source),
        dest_offset => 1,
        src_offset  => 1
    );

    -- L_COPY is an independent temporary LOB and can be processed separately.

    DBMS_LOB.FREETEMPORARY(l_copy);
END;
/
~~~

For CLOB, amount/offset are measured in characters; for BLOB, in bytes. Only perform COPY when a true copy is required because copying a large LOB consumes additional TEMP and I/O.

### 7.6. TRIM

TRIM truncates a LOB to the desired length:

~~~sql
DBMS_LOB.TRIM(l_clob, 1000);
~~~

For CLOB, length is measured in characters; for BLOB, in bytes. Do not use TRIM to free a temporary LOB; TRIM only alters content/length, whereas FREETEMPORARY releases temporary LOB resources.

## 8. Processing Large LOBs in Chunks

Do not convert an entire large CLOB/BLOB into VARCHAR2/RAW if its size could exceed PL/SQL buffer limits. Reading in chunks bounds memory usage and enables streaming processing.

### 8.1. Reading a CLOB in Chunks

~~~sql
DECLARE
    l_clob   CLOB;
    l_piece  VARCHAR2(4000);
    l_offset PLS_INTEGER := 1;
BEGIN
    -- Assume L_CLOB already contains data.
    LOOP
        l_piece := DBMS_LOB.SUBSTR(
            l_clob,
            4000,
            l_offset
        );

        EXIT WHEN l_piece IS NULL;

        -- Process the current chunk.
        DBMS_OUTPUT.PUT_LINE(
            'Chunk characters=' || LENGTH(l_piece)
        );

        l_offset := l_offset + LENGTH(l_piece);
    END LOOP;
END;
/
~~~

Offset increases by the number of characters read. For multibyte CLOBs, do not use LENGTHB to advance the offset because CLOB offsets are in character units.

In real applications, you do not necessarily call DBMS_OUTPUT for each chunk; you can pass the chunk to a parser, writer, or downstream processing layer.

### 8.2. Reading a BLOB in Chunks

~~~sql
DECLARE
    l_blob   BLOB;
    l_buffer RAW(32767);
    l_amount PLS_INTEGER;
    l_offset PLS_INTEGER := 1;
    l_length PLS_INTEGER;
BEGIN
    -- Assume L_BLOB already contains data.
    l_length := DBMS_LOB.GETLENGTH(l_blob);

    WHILE l_offset <= l_length LOOP
        l_amount := LEAST(32767, l_length - l_offset + 1);

        DBMS_LOB.READ(
            lob_loc => l_blob,
            amount  => l_amount,
            offset  => l_offset,
            buffer  => l_buffer
        );

        -- Process L_BUFFER.

        l_offset := l_offset + l_amount;
    END LOOP;
END;
/
~~~

BLOB offset and amount are measured in bytes. A RAW buffer has a 32,767-byte limit in PL/SQL; do not request a single READ larger than the buffer capacity.

### 8.3. Writing a CLOB Piecewise

~~~sql
DECLARE
    l_clob CLOB;
    l_part VARCHAR2(4000);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_clob,
        TRUE,
        DBMS_LOB.CALL
    );

    l_part := 'Header';
    DBMS_LOB.WRITEAPPEND(l_clob, LENGTH(l_part), l_part);

    l_part := ' - Detail';
    DBMS_LOB.WRITEAPPEND(l_clob, LENGTH(l_part), l_part);

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_clob));

    DBMS_LOB.FREETEMPORARY(l_clob);
END;
/
~~~

This pattern avoids allocating a new CLOB string via concatenation at each step.

## 9. Locator Management and Ownership

A locator is a reference to a LOB value. Clear locator management helps prevent accidental freeing or using an expired locator.

### 9.1. Assigning a Locator Does Not Copy Data

~~~sql
l_second := l_first;
~~~

Assigning a LOB locator should not be treated as a deep copy. Both variables can reference the same LOB value. If independent data is required, use DBMS_LOB.COPY into a newly created destination LOB.

### 9.2. Only One Place Should Be Responsible for Freeing

If multiple variables hold locators referencing the same temporary LOB, clearly define where ownership and freeing belong. Once a temporary LOB has been freed, do not continue using any locator that still references that value.

A maintainable convention:
- The routine that creates the temporary LOB is responsible for freeing it.
- A routine receiving a locator only uses it and does not free it unless the API contract transfers ownership.
- If returning a locator to the caller, document the duration and responsibility for freeing.
- If an independent copy is needed, use COPY and manage the new locator separately.

### 9.3. Do Not Free a Persistent Locator

Example reading a persistent CLOB:

~~~sql
DECLARE
    l_body CLOB;
BEGIN
    SELECT body
    INTO l_body
    FROM document_store
    WHERE document_id = 11;

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_body));

    -- Do not call FREETEMPORARY on L_BODY if it is a persistent LOB.
END;
/
~~~

You can check:

~~~sql
IF DBMS_LOB.ISTEMPORARY(l_body) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_body);
END IF;
~~~

With a persistent locator, the result is 0 and there is no temporary LOB to free.

### 9.4. Locators Must Not Be Used After CALL Duration Ends

If a temporary LOB has CALL duration, resources are released when the call ends per that duration. Do not store the locator in a package variable and expect to use it after the call completes.

If data must live across multiple calls, consider SESSION duration and make clear which caller will free it.

## 10. Temporary LOBs and Session Pools

Application servers typically use connection/session pools. A connection is returned to the pool after a request, while the underlying database session may remain alive.

If every request creates a SESSION-duration temporary LOB without freeing it:
- The temporary LOB stays alive after the request ends.
- Subsequent requests may reuse the session with old temporary LOBs attached.
- TEMP usage grows steadily over time.
- Errors only appear after many requests or under higher concurrent load.

### 10.1. Prefer CALL Duration for Request-Local Data

If the LOB is only needed within a single stored procedure call, use:

~~~sql
DBMS_LOB.CREATETEMPORARY(
    l_work,
    TRUE,
    DBMS_LOB.CALL
);
~~~

If SESSION duration must be used, guarantee cleanup before returning the connection to the pool.

### 10.2. Cleanup at Request Boundaries

Applications should follow a discipline:
1. The routine creating a LOB tracks its locator/ownership.
2. When processing completes, call FREETEMPORARY.
3. Exception paths also clean up.
4. Never hold locators in package globals across different requests.
5. Before returning a connection to the pool, no unnecessary session LOBs remain.

### 10.3. Do Not Rely on Connection Pool Closure as Routine Cleanup

Sessions can outlive individual requests. Closing a logical connection merely returns the session to the pool and does not necessarily terminate the database session. Therefore, session termination cannot be relied upon as routine cleanup for temporary LOBs.

## 11. Temporary LOBs and the Temporary Tablespace

Temporary LOBs consume temporary storage resources. Large intermediate data or many sessions creating LOBs concurrently can drive up TEMP tablespace usage.

Distinguish among:
- **Temporary LOB**: a temporary LOB value.
- **Temporary table**: a temporary table with its own transaction/session semantics.
- **Temporary tablespace**: the tablespace holding temporary segments.
- **Buffer cache**: a data caching area, not what defines temporary LOB lifetime.

A temporary LOB is not a global temporary table. Having "temporary" in the name does not mean the two objects share the same storage or cleanup mechanism.

### 11.1. Monitoring Temporary LOB Counts by Session

The V$TEMPORARY_LOBS view provides per-session temporary LOB statistics, typically including:
- SID.
- CACHE_LOBS.
- NOCACHE_LOBS.
- ABSTRACT_LOBS.

Example inspecting the current session:

~~~sql
SELECT sid,
       cache_lobs,
       nocache_lobs,
       abstract_lobs
FROM v$temporary_lobs
WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'));
~~~

These columns report counts of temporary LOBs grouped by cache/nocache/abstract; they are counts, not direct byte sizes. Appropriate privileges on dynamic performance views are required.

### 11.2. Monitoring Temporary Segments

You can use V$TEMPSEG_USAGE to observe temporary segments by session:

~~~sql
SELECT username,
       tablespace,
       segtype,
       blocks,
       sql_id
FROM v$tempseg_usage
WHERE session_addr = (
    SELECT saddr
    FROM v$session
    WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
);
~~~

This view reports temporary segments currently used by sessions. Segment types and display details can depend on workload/version. To convert blocks to bytes, you need the tablespace block size.

### 11.3. Viewing Overall TEMP Tablespace Space

A DBA can inspect TEMP space:

~~~sql
SELECT tablespace_name,
       tablespace_size,
       allocated_space,
       free_space
FROM dba_temp_free_space;
~~~

Access privileges and views may vary by version/schema privileges. In RAC environments, inspect the corresponding GV$ views and distinguish INST_ID/SID so sessions across different instances are not conflated.

### 11.4. Measuring Before and After an Operation

When investigating a suspected temporary LOB leak:
1. Record the session's temporary LOB counts and temporary segments.
2. Run a representative batch.
3. Free all explicitly created locators.
4. Measure again.
5. Repeat across multiple batches to see whether usage grows.
6. Compare against session termination or call completion per duration.

An elevated TEMP reading at a single moment does not automatically prove a leak. Oracle may retain/reclaim extents under temporary segment management; examine trends and session state.

## 12. Controlling Space and Performance

Managing temporary LOBs is not just about calling FREETEMPORARY. You also need to reduce the number of LOBs created, the size of copies, and locator retention time.

### 12.1. Choose the Shortest Duration That Meets Requirements

- Use CALL if data is only needed within one call.
- Use SESSION when it genuinely must survive across multiple calls.
- Free early right after the last use.
- Do not default to SESSION merely because it is the default value of CREATETEMPORARY.

### 12.2. Limit Concatenations That Create Intermediate Copies

Avoid repeating:

~~~sql
l_clob := l_clob || p_piece;
~~~

on large content. Creating one temporary CLOB and calling WRITEAPPEND piecewise usually gives better control over intermediate allocations.

### 12.3. Do Not Copy the Entire LOB If Only a Slice Is Needed

Use DBMS_LOB.SUBSTR or DBMS_LOB.READ in chunks if you only need to process parts. Copying an entire large LOB into another temporary LOB can nearly double temporary space usage.

### 12.4. Choose CACHE Based on Workload

- Repeatedly reading a small LOB may benefit from caching.
- Large, read-once data may suit NOCACHE.
- Measure I/O, buffer cache pressure, and throughput under representative load.

Do not pick CACHE TRUE just to be fast; nor pick FALSE for every large LOB without measuring.

### 12.5. Limit Concurrent LOBs

When processing many documents:
- Use small batches.
- Free each document's LOB before moving to the next if retention is unnecessary.
- Avoid holding a list of locators when only one LOB is needed at a time.
- Avoid creating unnecessary parallel copies.

### 12.6. Prevent Session-Duration Leaks

In long-running sessions:
- Monitor V$TEMPORARY_LOBS.
- Check exception branches.
- Audit routines returning locators.
- Audit package variables holding locators.
- Ensure cleanup before returning a session to the pool.

### 12.7. Do Not Use COMMIT to Free TEMP

COMMIT resolves transactions, not FREETEMPORARY. If a session holds a session-duration LOB, COMMIT does not make the locator disappear.

## 13. Safe Temporary CLOB Management Code Pattern

A procedure can create, write, process, and free a temporary CLOB as follows:

~~~sql
CREATE OR REPLACE PROCEDURE build_document_preview (
    p_header IN VARCHAR2,
    p_detail IN VARCHAR2
) AS
    l_document CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        lob_loc => l_document,
        cache   => TRUE,
        dur     => DBMS_LOB.CALL
    );

    IF p_header IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_document,
            LENGTH(p_header),
            p_header
        );
    END IF;

    IF p_detail IS NOT NULL THEN
        DBMS_LOB.WRITEAPPEND(
            l_document,
            LENGTH(p_detail),
            p_detail
        );
    END IF;

    -- Process or pass L_DOCUMENT to a routine accepting a LOB.
    DBMS_OUTPUT.PUT_LINE(
        'Preview length=' || DBMS_LOB.GETLENGTH(l_document)
    );

    IF DBMS_LOB.ISTEMPORARY(l_document) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_document);
    END IF;

    l_document := NULL;

EXCEPTION
    WHEN OTHERS THEN
        IF l_document IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_document) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_document);
        END IF;

        l_document := NULL;
        RAISE;
END build_document_preview;
/
~~~

The procedure uses CALL duration because the LOB is only needed during the call. The exception handler frees it if an error occurs after LOB creation. In production code, if cleanup could raise an exception, design it so the original error is not masked and cleanup errors are logged.

## 14. Pattern for Creating and Saving a Persistent CLOB from a Temporary CLOB

You can assemble temporary content first and then write it to a persistent column. Keep source and destination locators distinct.

~~~sql
CREATE TABLE report_store (
    report_id NUMBER PRIMARY KEY,
    report_body CLOB
);
~~~

Example:

~~~sql
DECLARE
    l_temp   CLOB;
    l_target CLOB;
    l_part   VARCHAR2(100);
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_temp,
        TRUE,
        DBMS_LOB.CALL
    );

    l_part := 'Report header' || CHR(10);
    DBMS_LOB.WRITEAPPEND(l_temp, LENGTH(l_part), l_part);

    l_part := 'Report detail' || CHR(10);
    DBMS_LOB.WRITEAPPEND(l_temp, LENGTH(l_part), l_part);

    INSERT INTO report_store(report_id, report_body)
    VALUES (1, EMPTY_CLOB())
    RETURNING report_body INTO l_target;

    DBMS_LOB.COPY(
        dest_lob    => l_target,
        src_lob     => l_temp,
        amount      => DBMS_LOB.GETLENGTH(l_temp),
        dest_offset => 1,
        src_offset  => 1
    );

    COMMIT;

    IF DBMS_LOB.ISTEMPORARY(l_temp) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_temp);
    END IF;

    -- L_TARGET is a persistent locator; do not call FREETEMPORARY.
EXCEPTION
    WHEN OTHERS THEN
        IF l_temp IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_temp) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_temp);
        END IF;

        ROLLBACK;
        RAISE;
END;
/
~~~

L_TEMP is a temporary CLOB; L_TARGET is a locator to REPORT_STORE.REPORT_BODY. COMMIT persists the changes; FREETEMPORARY frees L_TEMP. Do not call FREETEMPORARY on L_TARGET.

In real applications, place cleanup and transaction boundaries according to the API that owns the LOB; if COMMIT succeeds and cleanup afterward fails, persistent data is already committed and can no longer be rolled back by the handler.

## 15. Temporary LOBs in Functions and Locator-Returning APIs

A function can return a CLOB/BLOB. If a function creates a temporary LOB and returns its locator to the caller, the duration must be long enough for the caller to use it.

Conceptual example:

~~~sql
CREATE OR REPLACE FUNCTION make_text_lob (
    p_text IN VARCHAR2
) RETURN CLOB
IS
    l_result CLOB;
BEGIN
    DBMS_LOB.CREATETEMPORARY(
        l_result,
        TRUE,
        DBMS_LOB.SESSION
    );

    DBMS_LOB.WRITEAPPEND(
        l_result,
        LENGTH(p_text),
        p_text
    );

    RETURN l_result;
END make_text_lob;
/
~~~

The caller receives the locator and must manage freeing it:

~~~sql
DECLARE
    l_value CLOB;
BEGIN
    l_value := make_text_lob('Returned temporary value');

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_value));

    IF DBMS_LOB.ISTEMPORARY(l_value) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_value);
    END IF;
END;
/
~~~

This example uses SESSION duration so the locator remains valid after the function returns. It must be documented that the caller owns the responsibility to free it. If using CALL duration, understand the exact call boundary in the actual invocation; never return a locator that the caller intends to retain after its duration expires.

### 15.1. Ownership Contracts Must Be Explicit

When an API returns a LOB locator, document:
- Whether the locator points to a persistent or temporary LOB.
- Whether a temporary LOB uses CALL or SESSION duration.
- Whether the caller is allowed to write/modify it.
- Who is responsible for calling FREETEMPORARY.
- Whether the locator may be shared across multiple variables/routines.
- Whether COPY is required if the caller wants independent data.

Never leave both callee and caller assuming the other will free it; nor let both free the same locator without an ownership contract.

## 16. Common Errors When Managing Temporary LOBs

| Error/Situation | Cause | Resolution |
| --- | --- | --- |
| ORA-22275 | Invalid or improperly initialized locator | Create a temporary LOB or obtain a valid persistent locator before operating |
| ORA-22289 | Invalid operation on locator/LOB in current context | Check datatype, locator, and routine used |
| ORA-22922 | Locator points to a LOB value that is no longer valid | Check locator lifecycle and source object |
| TEMP growing steadily per session | SESSION temporary LOBs not freed | Use CALL when suitable, clean up explicitly, and monitor sessions |
| LOB becomes invalid after routine returns | CALL-duration locator expired | Choose an appropriate duration or process the LOB within the same call |
| Calling FREETEMPORARY on a persistent LOB | Mistaking a table column locator for temporary | Check ISTEMPORARY and only free when it returns 1 |
| CLOB truncated/wrong offset | Using LENGTHB or byte offsets for CLOB | Use character units for CLOB/NCLOB |
| BLOB truncated/wrong offset | Using character units instead of bytes | Use byte counts such as UTL_RAW.LENGTH |
| Memory/TEMP spikes during string concatenation | Many implicit temporary LOBs/intermediate copies | Create one LOB and WRITEAPPEND piecewise |
| Excessive LOB copying | Unnecessary full assignment/copying | Use locators, chunk reads, or COPY only what is needed |
| Locator alias used after freeing | Multiple variables referencing the same temporary LOB | Define owner; never use aliases after FREETEMPORARY |
| COMMIT does not reduce TEMP | COMMIT does not free SESSION LOBs | Call FREETEMPORARY or terminate the session |
| Session pool retains TEMP | Logical connection returned to pool while session stays alive | Clean up before returning connection |
| Calling DBMS_LOB on NULL locator | Uninitialized LOB variable | Check NULL and create/read a valid locator |

Specific error codes depend on the operation, locator state, and Oracle version. When investigating, record SQLCODE, SQLERRM, error stack, and backtrace; also inspect sessions holding temporary LOBs.

## 17. Workflow for Diagnosing Temporary LOB Usage

When TEMP tablespace grows abnormally or a session holds many temporary LOBs:

1. Identify the SID/serial number and SQL_ID of the suspect session.
2. Check CACHE_LOBS, NOCACHE_LOBS, and ABSTRACT_LOBS in V$TEMPORARY_LOBS.
3. Check the session's temporary segments in V$TEMPSEG_USAGE.
4. Identify the running procedure/package and branches creating LOBs.
5. Look for CREATETEMPORARY with SESSION duration.
6. Look for implicit LOB expressions inside loops, especially repeated CLOB concatenation.
7. Verify that every exception branch performs cleanup.
8. Audit functions/procedures returning locators and their ownership contracts.
9. Re-measure after freeing LOBs or ending the call.
10. Observe trends across multiple batches/requests rather than a single snapshot.
11. Evaluate batch size, cache mode, and concurrent LOB count.
12. Check overall TEMP tablespace usage and load from other sessions.

Do not conclude a leak from a single glance at TEMP usage. Distinguish temporary segments retained by Oracle for reuse from LOB locators actually still alive in a session.

## 18. Common Misconceptions

**A temporary LOB is a temporary table.** False. A temporary LOB is an intermediate LOB value; a temporary table is a table object with its own temporary data rules.

**Every CLOB variable is a temporary LOB.** False. A variable may hold a locator to a persistent LOB, a temporary LOB, or be uninitialized.

**Selecting a CLOB from a table and calling FREETEMPORARY is proper cleanup.** False. That locator usually points to a persistent LOB; do not free it with FREETEMPORARY.

**EMPTY_CLOB() creates a temporary CLOB.** False. EMPTY_CLOB is typically used to initialize an empty persistent CLOB column; use CREATETEMPORARY for temporary LOBs.

**COMMIT frees temporary LOBs.** False. CALL/SESSION duration is not a transaction lifetime.

**SESSION duration is always better than CALL.** False. SESSION keeps the locator longer and easily causes leaks in session pools if not freed.

**CALL duration means ending a BEGIN/END block automatically frees it.** Do not reason by nested blocks; CALL is tied to call duration per Oracle semantics. Call FREETEMPORARY when finished inside long calls.

**CACHE TRUE is always faster than CACHE FALSE.** False. It depends on read patterns, size, buffer cache pressure, and workload.

**Assigning L_B := L_A creates an independent copy.** Do not treat locator assignment as a deep copy. Use DBMS_LOB.COPY when independent data is required.

**TRIM frees a temporary LOB.** False. TRIM only truncates length; FREETEMPORARY is what frees temporary LOBs.

**Concatenating CLOBs in a loop is always cheap.** False. It can allocate many intermediate values; WRITEAPPEND is usually easier to control.

**CLOB amount and offset are measured in bytes.** False. CLOB/NCLOB use character units; BLOB uses bytes.

**V$TEMPORARY_LOBS reports exact TEMP bytes.** False. This view reports counts by temporary LOB category; also inspect temporary segment views for space usage.

**Returning a connection to a session pool ends the database session.** False. The logical connection may be returned to the pool while the database session remains alive.

**FREETEMPORARY works on any locator.** False. Only free temporary LOB locators.

## 19. Practice Exercises

1. Create a temporary CLOB using CREATETEMPORARY with CALL duration.
2. Write a string into a CLOB with WRITEAPPEND and compute amount accurately.
3. Create a temporary BLOB and append a RAW buffer.
4. Why does CLOB use LENGTH while BLOB uses UTL_RAW.LENGTH?
5. Check a locator using ISTEMPORARY.
6. Free a temporary LOB using FREETEMPORARY.
7. Write an exception handler ensuring cleanup when a LOB operation fails.
8. Compare CALL and SESSION durations.
9. Why does COMMIT not replace FREETEMPORARY?
10. Create a SESSION-duration temporary LOB in a session and free it in a subsequent call.
11. Explain the risk of SESSION LOBs in connection pools.
12. Distinguish a persistent LOB locator from a temporary LOB locator.
13. Use EMPTY_CLOB in an INSERT and write persistent data using RETURNING.
14. Why must you not call FREETEMPORARY on a locator retrieved from a CLOB column?
15. Create a CLOB via concatenation and check ISTEMPORARY.
16. Replace repeated concatenation with WRITEAPPEND.
17. Compare APPEND and WRITEAPPEND.
18. Use COPY to create an independent temporary CLOB from a source CLOB.
19. Explain why assigning a locator does not equal a deep copy.
20. Read a CLOB in 4000-character chunks and advance the offset properly.
21. Read a BLOB in chunks up to 32767 bytes.
22. Why is LENGTHB unsuitable for advancing a CLOB offset?
23. Use TRIM to shorten a CLOB and distinguish it from FREETEMPORARY.
24. Create a function returning a temporary CLOB and document ownership for the caller.
25. State the risk of returning a CALL-duration locator outside a routine.
26. Write a query to inspect V$TEMPORARY_LOBS for the current session.
27. Write a query to inspect the session's temporary segments in V$TEMPSEG_USAGE.
28. Distinguish temporary LOB count from temporary segment size.
29. Build a procedure to detect SESSION LOB leaks in a session pool.
30. Design a large-file processing API: chunk reading, creating a temporary LOB, saving a persistent LOB, and cleanup on both success and failure.

**Temporary LOBs are intermediate data with CALL or SESSION lifecycles; create them with CREATETEMPORARY, check with ISTEMPORARY, and free with FREETEMPORARY.** Distinguish temporary locators from persistent locators, use character units for CLOBs and bytes for BLOBs, avoid creating unnecessary copies, and monitor TEMP usage at the session level. Clear duration and ownership management prevents temporary LOB leaks, especially in connection-pooled applications.
