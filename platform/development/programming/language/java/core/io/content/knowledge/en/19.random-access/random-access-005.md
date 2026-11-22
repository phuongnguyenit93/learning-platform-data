# Designing Records with Deterministic Position and Size in Java: Random Access

## 1. Goal and problem statement

When an application needs to **read or update the Nth record directly** in a data file, reading the entire file from the beginning up to N is usually unnecessary. A *fixed-size record* design places every record into a byte region of constant size; knowing the record index immediately yields its byte position.

For example, an account file consists of a 16-byte *header* followed by multiple 64-byte records. To read the record at index 2 (0-based), the application jumps directly to the byte offset:

~~~text
offset(index) = HEADER_SIZE + index * RECORD_SIZE
offset(2)     = 16 + 2 * 64 = 144
record 2      = bytes [144, 207] (64 bytes)
~~~

This is a **byte offset** in the file; it is not a character index, a text line number, or a business key (`id`). With a fixed layout, index-based positioning cost can be O(1); actual I/O performance still depends on the operating system, storage device, cache, and fragmentation.

After this lesson, you will be able to design a *stable binary schema*, compute positions without integer overflow, read/write the exact byte count using `FileChannel`, handle variable-length string data inside a fixed storage slot, mark logical deletions, and recognize consistency/durability limits.

## 2. Conventions before writing data

A binary record format requires a **contract** so the writer and reader interpret the exact same bytes identically. This contract must specify:

1. Header size and single-record size in **bytes**, not characters.
2. Field types and positions; signedness, byte order (*endianness*), monetary representation, and status flag values.
3. String character encoding; how string length is stored and how padding to a fixed size works.
4. Offset calculation, index numbering base, and how deleted or never-written records are identified.
5. Version/schema handling when reopening the file, update strategy, error detection, and crash handling.

You cannot simply write with `DataOutputStream.writeUTF` and assume every record has a fixed length: string byte length depends on content, and `writeUTF` uses modified UTF-8 with its own length prefix. Nor can you use `String.length()` to estimate UTF-8 byte count: a single Vietnamese character can occupy multiple bytes even though it is one visible character.

### Sample schema: 16-byte header + 64-byte records

File header:

| Absolute offset | Bytes | Field | Convention |
| --- | ---: | --- | --- |
| 0–3 | 4 | `magic` | 0x46524543 corresponding to `FREC` |
| 4–7 | 4 | `version` | 32-bit integer, value 1 |
| 8–11 | 4 | `recordSize` | 32-bit integer, value 64 |
| 12–15 | 4 | `reserved` | 0 in version 1 |

Each record is indexed **relative** to the record's starting offset:

| Offset within record | Bytes | Field | Convention |
| --- | ---: | --- | --- |
| 0 | 1 | `status` | 1 = active; 2 = logically deleted |
| 1–8 | 8 | `id` | Signed `long`, business key |
| 9–16 | 8 | `balanceCents` | `long`: smallest currency unit, never `double` |
| 17–18 | 2 | `nameLength` | UTF-8 byte length, 0–40 |
| 19–58 | 40 | `nameArea` | UTF-8 bytes + zero-padded area |
| 59–63 | 5 | `reserved` | 0 in version 1 |
| **Total** | **64** | | |

All `int`/`long`/`short` values are encoded in `ByteOrder.BIG_ENDIAN`: the most significant byte comes first. The reader must use the same byte order; switching to little-endian without updating the schema causes numeric fields to be decoded incorrectly.

The `status` byte distinguishes active records from logically deleted records. Value 0 is not used for valid records; it commonly appears in uninitialized regions or holes in a *sparse file*. Never treat an all-zero region as a valid record.

A file containing three contiguous records has an exact length of `16 + 3 * 64 = 208` bytes. Record index 1 starts at byte 80 and ends at byte 143; record index 2 starts at byte 144.

## 3. Computing offsets accurately and protecting bounds

Basic formula:

~~~java
long offset = Math.addExact(
        (long) headerSize,
        Math.multiplyExact(index, (long) recordSize));
~~~

This is an **illustrative snippet**: `headerSize`, `index`, and `recordSize` must be declared appropriately. `Math.multiplyExact` and `Math.addExact` throw `ArithmeticException` on `long` overflow, avoiding the bug of multiplying `int`s before widening to `long`. Reject `index < 0` and only allow writes to valid slots per your application policy.

To read a **complete** record, verify:

~~~text
offset >= HEADER_SIZE
offset + RECORD_SIZE <= fileSize
(fileSize - HEADER_SIZE) % RECORD_SIZE == 0
~~~

These constraints apply to a contiguous file with no trailer or interleaved metadata regions. Compute `offset + RECORD_SIZE` with overflow checking (e.g., `Math.addExact`) and verify that the record lies within the allocated range. If the file was truncated mid-record, do not silently decode a partial record from unread bytes.

**Distinguish storage index from business ID.** A record with `id=102` does not necessarily reside at slot 102. For example, it might be stored at index 1. If IDs are non-contiguous, maintain an `id → slotIndex` mapping table (or an external B-tree/hash index) rather than blindly using the ID as an offset, which would create huge gaps in the file.

## 4. Complete Java 17+ example: positional read, update, and logical delete

This example uses `java.nio.channels.FileChannel` and `ByteBuffer` to place records into deterministic byte regions. It creates a **dedicated temporary file**, writes three records, closes/reopens the file, directly reads record 1, updates record 1 in place, marks record 2 as deleted, and cleans up the temporary file when finished.

Save to `FixedRecordDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FixedRecordDemo {
    private static final int HEADER_SIZE = 16;
    private static final int RECORD_SIZE = 64;
    private static final int NAME_BYTES = 40;
    private static final int MAGIC = 0x46524543; // "FREC"
    private static final int VERSION = 1;
    private static final byte ACTIVE = 1;
    private static final byte DELETED = 2;

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("fixed-record-", ".bin");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                writeHeader(channel);
                writeRecord(channel, 0, 101, 125_000, "Lan");
                writeRecord(channel, 1, 102, 230_500, "Minh");
                writeRecord(channel, 2, 103, 75_000, "An");
                channel.force(true);
            }

            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                validateHeader(channel);
                System.out.println("Offset record 1: " + offsetOf(1));
                System.out.println("Record 1: " + readRecord(channel, 1));
                writeRecord(channel, 1, 102, 240_000, "Minh");
                System.out.println("Updated record 1: " + readRecord(channel, 1));
                markDeleted(channel, 2);
                System.out.println("Record 2: " + readRecord(channel, 2));
                System.out.println("Count slots: " +
                        (channel.size() - HEADER_SIZE) / RECORD_SIZE);
                channel.force(true);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static long offsetOf(long index) {
        if (index < 0) throw new IllegalArgumentException("index must be >= 0");
        return Math.addExact((long) HEADER_SIZE,
                Math.multiplyExact(index, (long) RECORD_SIZE));
    }

    private static void writeHeader(FileChannel ch) throws IOException {
        ByteBuffer b = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN);
        b.putInt(MAGIC).putInt(VERSION).putInt(RECORD_SIZE).putInt(0);
        b.flip();
        writeFully(ch, b, 0);
    }

    private static void validateHeader(FileChannel ch) throws IOException {
        if (ch.size() < HEADER_SIZE) throw new EOFException("Missing header");
        ByteBuffer b = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN);
        readFully(ch, b, 0);
        b.flip();
        if (b.getInt() != MAGIC || b.getInt() != VERSION
                || b.getInt() != RECORD_SIZE || b.getInt() != 0) {
            throw new IOException("Unsupported header");
        }
        if ((ch.size() - HEADER_SIZE) % RECORD_SIZE != 0) {
            throw new IOException("Truncated record region");
        }
    }

    private static void writeRecord(FileChannel ch, long index,
                                    long id, long cents, String name) throws IOException {
        byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
        if (utf8.length > NAME_BYTES) {
            throw new IllegalArgumentException("name exceeds 40 UTF-8 bytes");
        }
        ByteBuffer b = ByteBuffer.allocate(RECORD_SIZE).order(ByteOrder.BIG_ENDIAN);
        b.put(ACTIVE).putLong(id).putLong(cents)
                .putShort((short) utf8.length).put(utf8);
        // allocate() initialized all remaining bytes to 0; write the full slot.
        b.position(RECORD_SIZE);
        b.flip();
        writeFully(ch, b, offsetOf(index));
    }

    private static String readRecord(FileChannel ch, long index) throws IOException {
        long at = offsetOf(index);
        if (ch.size() < Math.addExact(at, (long) RECORD_SIZE)) {
            throw new EOFException("Record out of range");
        }
        ByteBuffer b = ByteBuffer.allocate(RECORD_SIZE).order(ByteOrder.BIG_ENDIAN);
        readFully(ch, b, at);
        b.flip();
        byte state = b.get();
        if (state == DELETED) return "<deleted>";
        if (state != ACTIVE) throw new IOException("Invalid record state");
        long id = b.getLong();
        long cents = b.getLong();
        int length = Short.toUnsignedInt(b.getShort());
        if (length > NAME_BYTES) throw new IOException("Invalid name length");
        byte[] nameArea = new byte[NAME_BYTES];
        b.get(nameArea);
        String name = new String(nameArea, 0, length, StandardCharsets.UTF_8);
        return "id=" + id + ", cents=" + cents + ", name=" + name;
    }

    private static void markDeleted(FileChannel ch, long index) throws IOException {
        long at = offsetOf(index);
        if (ch.size() < Math.addExact(at, (long) RECORD_SIZE)) {
            throw new EOFException("Record out of range");
        }
        writeFully(ch, ByteBuffer.wrap(new byte[] { DELETED }), at);
    }

    private static void writeFully(FileChannel ch, ByteBuffer b, long at) throws IOException {
        while (b.hasRemaining()) {
            int count = ch.write(b, at);
            if (count <= 0) throw new IOException("Write made no progress");
            at += count;
        }
    }

    private static void readFully(FileChannel ch, ByteBuffer b, long at) throws IOException {
        while (b.hasRemaining()) {
            int count = ch.read(b, at);
            if (count < 0) throw new EOFException("Unexpected end of file");
            if (count == 0) throw new IOException("Read made no progress");
            at += count;
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac FixedRecordDemo.java
java FixedRecordDemo
~~~

Exact stdout (compiled and run on JDK 21, Java 17 compatible):

~~~text
Offset record 1: 80
Record 1: id=102, cents=230500, name=Minh
Updated record 1: id=102, cents=240000, name=Minh
Record 2: <deleted>
Count slots: 3
~~~

**Explanation of key points in the code:**

- `writeHeader` writes the magic number, version, record size, and reserved field before writing the body. `validateHeader` rejects incompatible formats, files missing a header, and bodies whose size is not divisible by 64.
- `FileChannel.write(buffer, position)` and `FileChannel.read(buffer, position)` operate at an **absolute position**; they neither use nor modify the channel's current position. This makes direct access convenient, though it does not automatically make concurrent operations thread-safe.
- A single `read`/`write` call **is not guaranteed to process all** requested bytes. `readFully`/`writeFully` update the absolute position after each read/write; `EOFException` indicates insufficient bytes. The example uses a blocking channel on a regular file; returning 0 is reported as a lack-of-progress error.
- `ByteBuffer.allocate(RECORD_SIZE)` initializes its backing byte array to zeros. After writing the actual field bytes, calling `position(RECORD_SIZE)` followed by `flip()` ensures the write sends all 64 bytes, including the padding bytes. Calling `flip()` immediately after `put(utf8)` would send only the written prefix, and the file would **not** receive a full 64-byte record.
- `writeRecord` always writes the full 64-byte slot: updating with a shorter name will not leave stale bytes from an old name in the padding area. The example writes three contiguous slots 0 through 2; this minimal helper does not enforce policies on sparse/skipped indices, so production code should validate allowed indices before calling it.
- `readRecord` decodes `status`, the `long` fields, the UTF-8 byte length, and `nameArea` according to the schema. It rejects invalid states and `nameLength > 40`; a logically deleted record returns the string `<deleted>` in this example.
- `markDeleted` updates only the status byte at the start of the slot. The file size and indices of other records stay unchanged. `Count slots` counts **physical slots**, including deleted slots; it is not the count of active records.
- Both `try-with-resources` blocks close the channel cleanly; `Files.deleteIfExists` removes the temporary file after the channels are closed. `force(true)` requests flushing file/metadata updates to the storage device per the API contract, but does not turn multiple writes into an atomic transaction.

## 5. Why must the string's byte length be stored separately?

In a fixed schema, the name region may be 40 bytes long while an actual name uses only 3, 10, or 38 bytes. When reading, you cannot reliably separate data from padding by stripping trailing zero bytes if valid values might contain NUL characters. Therefore, the example stores `nameLength` separately in two bytes and reads that exact slice.

Example:

~~~text
name = "Lan"
UTF-8 = 4C 61 6E                      (3 bytes)
nameLength = 3                        (2 bytes in schema)
nameArea = 4C 61 6E 00 00 ... 00     (40 bytes total)
~~~

If the name is `"Hà"`, `name.length()` equals 2 UTF-16 code units, yet the UTF-8 sequence occupies 3 bytes (`H`: 1, `à`: 2). The schema limit is **40 encoded bytes**, not 40 Unicode characters; you must never arbitrarily slice after byte 40, as doing so can corrupt a multi-byte UTF-8 sequence.

In production systems, when an encoder encounters an invalid Unicode surrogate or a decoder encounters a malformed UTF-8 byte sequence, use a `CharsetEncoder`/`CharsetDecoder` configured with `CodingErrorAction.REPORT` to reject the data rather than silently inserting replacement characters. `new String(bytes, UTF_8)` in the example demonstrates decoding data written by the application itself; by itself it is not a strict UTF-8 validator for arbitrary untrusted files.

The `nameLength` value has Java type `short` when written. The example decodes it with `Short.toUnsignedInt` to inspect the full 0–65535 range, then still validates the schema limit of 40 rather than trusting on-disk data.

## 6. Updating, inserting, deleting, and reusing slots

**In-place updates** work cleanly only when every record version occupies the exact same `RECORD_SIZE`. In the example, changing `balanceCents` at index 1 does not shift index 2. Names can grow or shrink as long as they still encode within the 40-byte area; the code rewrites the entire slot with zero padding.

**Sequential insertion (append)**: the next slot usually has index `(fileSize - HEADER_SIZE) / RECORD_SIZE`, after verifying a valid file size. When multiple threads/processes append concurrently, slot index allocation must be coordinated so two writers do not pick the same slot.

**Logical deletion (tombstone)**: sets status to `DELETED` while keeping the physical positions of all other records intact. To reuse deleted slots, maintain a free-slot list or an index structure with proper synchronization. Simply setting `status=DELETED` neither shrinks the file nor ensures sensitive old data is erased from the storage device.

**Physical deletion by shifting records** alters the offsets of all subsequent records, breaking any index-to-position mapping. If stable offsets are required, use tombstones or perform reorganization (*compaction*) with coordinated index/reference updates and appropriate version/generation changes.

**New records with business IDs**: if lookups by arbitrary ID are needed, build an index from ID to slot index and check for duplicate IDs on write. Never assume "ID 101 → slot 101" unless that is an explicit invariant guaranteed by the schema.

## 7. API choices and correctness of random access

| API | Characteristics | When to choose |
| --- | --- | --- |
| `RandomAccessFile` | `seek(long)` mutates the file pointer; provides `readFully`, `readInt`, `writeLong` | Single-threaded examples, working directly via a file pointer |
| `FileChannel` + `ByteBuffer` | `read/write(buffer, long position)` uses absolute offsets, supports `force` and `lock` | Binary formats, block reads/writes, explicit byte-order control |
| `SeekableByteChannel` | Provides `position(long)`, reads/writes at the current channel position | Needing a common abstraction for seekable channels |
| `MappedByteBuffer` via `FileChannel.map` | Maps file regions into memory | Memory-mapping workloads, requiring careful handling of mapping bounds, sync, and unmapping resources |

`RandomAccessFile.seek(offset)` mutates the shared file pointer, so code sharing a single instance and repeatedly calling seek/read/write without synchronization can easily read from the wrong offset. `FileChannel`'s positional I/O methods avoid relying on a shared file pointer, though you still must guard against contention when two writers modify the same bytes/record, as well as concurrent file truncation or closing.

**A `ByteBuffer` has its own cursors** `position`, `limit`, and `remaining`. Never share a mutable `ByteBuffer` across threads without proper synchronization. Always set the byte order explicitly via `order(ByteOrder.BIG_ENDIAN)` on every buffer used to read or write multi-byte fields.

## 8. Necessary limitations in real-world applications

### Writing a valid record does not mean atomic writes

A 64-byte update may correspond to multiple low-level writes or storage blocks. A power loss or crash mid-update can leave a record containing a mix of old and new bytes, or even truncate the header/file. `FileChannel.force(true)` requests synchronizing data to storage, but **does not guarantee transaction atomicity** for multi-byte or multi-record updates.

If crash recovery and stronger consistency are required, consider techniques such as: records with a `checksum` and generation number; copy-on-write to a new slot followed by an atomic pointer/manifest update; a *write-ahead log*; or using a transactional database rather than building a custom storage engine.

### Synchronization across threads/processes

- Define who is allowed to write to a given slot; use application-level locks or suitable synchronization primitives.
- `FileChannel.lock()`/`tryLock()` can coordinate file or region locks, but locking semantics depend on the platform and provider. Do not treat OS locks as a universal solution or as proof of transactional behavior.
- When readers run concurrently with writers, a record may be observed in an intermediate state. If consistent snapshots are needed, enforce a read/write protocol (e.g., locks, version/counter checks with retries, or copy-on-write).
- Never let two threads independently compute the same `fileSize` and append concurrently without atomic index allocation.

### Validating formats from untrusted files

Before parsing, verify at least `magic`, `version`, `recordSize`, total file length, valid index, status, UTF-8 byte length, and business constraints. The example checks only a few key fields to stay focused on fixed-record design; production applications should also validate `id`, `balanceCents`, reserved bytes, and integrity checksums.

For long-term durability, never "guess" a schema from file size when the header reports an unsupported version. Reject opening it or run a tested migration procedure. Changing record size from 64 to 80 bytes without updating the version/migrating renders all existing offsets invalid.

### Capacity and fragmentation

- Fixed-size records simplify slot-based access at the cost of **internal fragmentation**: the 40-byte `nameArea` is still reserved even when a name is only 3 bytes long.
- Records that are too small restrict data fields; records that are too large waste space on small updates and hurt caching.
- For fields of arbitrary length (descriptions, images, JSON), consider variable-length records plus an offset index, or fixed-size metadata records pointing to a separate data region—which introduces free-space management and consistency requirements.
- Creating a slot at a very large index can cause some file systems to produce a *sparse file* whose holes read back as zero bytes. File size alone then does not prove that every preceding slot was ever written.

## 9. Pre-implementation design checklist

A design with deterministic positions and sizes should answer the following questions:

1. **Are offsets completely deterministic?** Document header size, record size, index base, integer types, and overflow checks.
2. **Does every field have exact byte boundaries?** The sum of field byte counts equals record size; byte order and signedness are documented.
3. **Do strings specify charset and byte limits?** Encode first, then check byte count, with a length prefix or unambiguous padding rules.
4. **Do reads/writes handle partial I/O and EOF?** Never assume a single channel call drains or fills the entire buffer.
5. **Do close-and-reopen reads match?** Verify magic, version, file length, and record status.
6. **Do updates/deletes preserve offsets of remaining records?** Define tombstones, slot-reuse rules, and ID → index mappings.
7. **Are crashes and concurrency addressed?** If strong atomicity and durability are required, adopt a protocol beyond basic positional writes.

Common mistakes include calculating offsets in characters, forgetting the header in offset math, using `int` for large multiplications, forgetting to call `flip()` properly, setting `ByteBuffer.limit` smaller than a record, failing to handle partial reads/writes, reading strings by character count instead of UTF-8 byte count, and confusing slot indices with business IDs.

## 10. Self-check questions

1. Header is 24 bytes, each record is 96 bytes, 0-based indexing. What offset is record index 5 at? **504** (= 24 + 5 × 96); byte range is [504, 599].
2. Why shouldn't replacing `"Lan"` with `"Nguyễn"` shift subsequent records? Because both names fit inside the fixed `nameArea` region; compute the UTF-8 byte length and write full padding.
3. Can you use `fileSize / RECORD_SIZE` to count slots when there is a 16-byte header? **No**; you need `(fileSize - HEADER_SIZE) / RECORD_SIZE` after validating the file size.
4. Does logically deleting a slot reduce the total slot count? **No**; a tombstone keeps the physical slot intact and only changes its status.
5. Is `FileChannel.write(buffer, position)` guaranteed to write all 64 bytes in a single call? **Not guaranteed**; you must loop while the buffer still has remaining bytes.
6. Does calling `force(true)` guarantee that every 64-byte update is atomic on power loss? **No**; verification/recovery mechanisms and transactions are needed if required by the problem.

## API Reference Documentation

- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): positional read/write, `force`, `lock`, and memory mapping.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, and reading/writing binary data.
- [Java SE 17 — RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html): `seek`, `readFully`, and file pointer management.
- [Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `multiplyExact` and `addExact` to detect overflow during offset calculations.
