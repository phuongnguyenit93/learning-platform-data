# Kiểm chứng độ bền của ánh xạ NVM theo mô hình lỗi của môi trường đích

## 1. Bài toán: “đã ghi vào bộ nhớ” không đồng nghĩa “sẽ sống sót sau mọi lỗi”

Khi dùng **NVM / persistent memory** (*non-volatile memory*, bộ nhớ không mất dữ liệu trong một số điều kiện mất nguồn điện), một chương trình Java có thể truy cập dữ liệu được ánh xạ vào không gian địa chỉ bằng `FileChannel.map(...)` và `MappedByteBuffer`. Từ **Java 14**, **JEP 352 — Non-Volatile Mapped Byte Buffers** bổ sung các chế độ mapping riêng của JDK để hỗ trợ **file nằm trên nền tảng NVM có khả năng persistent mapping**.

Câu hỏi quan trọng không phải chỉ là “gọi `force()` có thành công không?” mà là:

> Sau đúng **loại sự cố** mà sản phẩm cam kết chịu được, trên **hardware + OS + filesystem + JDK + storage** thật, dữ liệu nào phải còn? Dữ liệu nào có thể mất? Dữ liệu nào tuyệt đối không được xuất hiện ở trạng thái nửa vời?

**Mục tiêu bài học:** thiết kế và thực hiện kiểm chứng **durability** (độ bền lưu trữ) dựa trên *fault model* của **môi trường đích**, thay vì suy luận từ một lần chạy thử trong cùng JVM hoặc từ tên API.

Ví dụ contract giả định:

- Sau khi hệ thống báo **“đã commit thành công”**, bản ghi tương ứng phải còn hợp lệ sau sự cố nằm trong mô hình được hỗ trợ.
- Nếu lỗi xảy ra **trước commit**, recovery có thể nhìn thấy bản cũ hoặc bản mới **nếu chính sách cho phép**, nhưng không được chấp nhận bản ghi hỏng.
- **Atomicity / crash consistency** phải được thiết kế riêng; chỉ `MappedByteBuffer.force()` không tạo transaction nhiều trường.
- Các lỗi nằm **ngoài mô hình** (thiết bị hỏng vĩnh viễn, lỗi phần mềm ác ý, nhiều vùng lưu cùng mất, sai firmware) cần được xử lý bằng backup/replication hoặc contract khác, không thể mặc định có bảo đảm từ JEP 352.

**Special Note — chỉ kiến thức còn hiệu lực:** `jdk.nio.mapmode.ExtendedMapMode.READ_WRITE_SYNC` và `READ_ONLY_SYNC` được công bố từ Java 14 và **vẫn tồn tại trong JDK 17, 25 và các tài liệu JDK hiện đại**. Đây là API **JDK-specific thuộc module `jdk.nio.mapmode`**, không phải kiểu mapping Java SE bảo đảm chạy được trên mọi OS/filesystem. Bài sử dụng Java 17+ và các API hiện hành, không dựa vào preview/incubator đã lỗi thời.

## 2. Lập mô hình lỗi **trước** khi viết kiểm thử

Một “bài test restart” có thể chứng minh rất ít: máy còn nguồn, kernel còn chạy, filesystem cache còn dữ liệu. Cần tách các tình huống khác nhau:

| Lỗi / sự kiện | Trạng thái phần cứng | Rủi ro dữ liệu | Phép thử phù hợp |
| --- | --- | --- | --- |
| **Dừng bình thường** | JVM, OS và điện vẫn ổn | Chưa chứng minh gì về crash | Đóng chương trình, mở lại bằng process mới |
| **Process kill / crash** | Kernel, page cache, thiết bị vẫn chạy | Ghi dở ở mức ứng dụng | Kill **process test** tại failpoint rồi mở process mới |
| **JVM crash** | OS còn hoạt động | Callback/flush chưa hoàn tất | Inject failure trước/sau từng bước commit |
| **OS crash / kernel panic** | OS dừng đột ngột | Dữ liệu trong caches/metadata có thể chưa ổn định | Lab VM hoặc máy test có điều khiển, phục hồi qua boot mới |
| **Power loss toàn máy** | Cache/controller/thiết bị mất nguồn theo thiết kế | Mất write chưa vào persistence domain; torn writes | Thiết bị test có cơ chế ngắt nguồn **được phê duyệt**, reboot và verify |
| **Storage reset / controller fault** | Một phần đường ghi có thể hỏng | Báo thành công sai, lỗi I/O, stale/torn block | Fault injection storage được kiểm soát |
| **Corruption / torn write** | Có thể còn nguồn | Header, payload, checksum hoặc marker lệch nhau | Sửa byte có chủ đích trên **file test**, kiểm tra recovery |
| **Hai writer đồng thời** | Không nhất thiết có crash | Ghi đè/chồng lấp gây data race | Concurrent write test và single-writer/locking policy |
| **Filesystem/directory metadata mất** | Dữ liệu file có thể tồn tại | File mới/rename không còn đường dẫn ổn định | Test create/rename/metadata sync sau crash |
| **Device/media mất vĩnh viễn** | Một thiết bị không còn đọc được | Không thể phục hồi chỉ bằng force | Backup/replication/restore drill |

**Tránh khẳng định “power-loss safe” sau khi chỉ thử `kill -9`.** Kill process **không xóa Linux page cache hoặc mô phỏng capacitor/ADR/eADR của phần cứng**. Tương tự, chép file ra SSD thông thường rồi restart không phải phép kiểm chứng đặc thù của persistent memory DAX.

### 2.1. Xác định **persistence domain**

Một phép ghi của CPU có thể đi qua:

```text
Java put(...) vào MappedByteBuffer
             |
             v
CPU stores / cache lines
             |
             v
Memory controller / pending write queues
             |
             v
NVM media hoặc storage device
             |
             v
Sau sự cố: boot + read + validate
```

**Persistence domain** là phạm vi các dữ liệu được phần cứng **bảo toàn** trước kiểu mất nguồn đã định. Ví dụ:

- **ADR** (*Asynchronous DRAM Refresh* trong thuật ngữ phần cứng PMem): một số hệ thống bảo toàn phần dữ liệu đã tới hàng đợi của memory controller, **không mặc nhiên bảo toàn CPU caches**.
- **eADR** (*extended ADR*): trên nền tảng hỗ trợ, miền được bảo toàn còn bao gồm CPU caches.
- **Storage thông thường** có controller caches, volatile RAM hoặc pin bảo vệ riêng; hành vi phụ thuộc lệnh flush, firmware, thiết bị và cấu hình.

Không nên nói “mọi NVM đều cần đúng một lệnh flush” hoặc “cứ dùng eADR là transaction atomic”. **Durability của một dải bytes và atomicity của nhiều thao tác là hai tính chất khác nhau.** Thực tế cần tài liệu CPU/BIOS/NVDIMM, kernel, filesystem và phạm vi bảo vệ nguồn của **nền tảng triển khai cụ thể**.

### 2.2. Thiết lập **acknowledgement point**

Một contract tốt cần trả lời:

**Khi nào ứng dụng được trả kết quả “commit thành công”?**

Ví dụ protocol hai bản ghi trong bài:

```text
1. Ghi "không hợp lệ" cho slot chuẩn bị, force marker.
2. Ghi header/payload/checksum, force phần thân.
3. Ghi commit marker, force marker.
4. Chỉ sau khi bước 3 hoàn tất mới gửi ACK.
```

Với mô hình **local storage thực thi đúng guarantee của force** và assumptions phần cứng/OS đã xác minh, bước 4 là điểm ứng dụng coi là committed. Nếu process hoặc nguồn điện chết **trước** ACK, operation chưa được xác nhận; recovery phải chọn bản hợp lệ và tuân theo quy tắc old/new đã thỏa thuận. Nếu chết **sau** ACK, bản đã ACK phải tồn tại theo mô hình lỗi được hỗ trợ.

Cần phân biệt:

- **Persistence ordering:** dữ liệu của các pha đã được force đúng thứ tự.
- **Atomic commit:** recovery không chấp nhận một record dở dang.
- **Durable ACK:** record sau khi xác nhận phải còn tồn tại.
- **Idempotency:** gửi lại yêu cầu sau timeout không áp dụng hai lần.
- **Replication:** một máy còn dữ liệu nhưng máy khác không đồng nghĩa cụm hệ thống đã đạt durability.

Không thể suy ra tất cả tính chất trên chỉ từ `force()`.

## 3. API ánh xạ NVM hiện hành: `ExtendedMapMode`

### 3.1. Các mode cần phân biệt

Java SE cung cấp `FileChannel.MapMode.READ_ONLY`, `READ_WRITE` và `PRIVATE`. JEP 352 bổ sung trong module **`jdk.nio.mapmode`**:

```java
import jdk.nio.mapmode.ExtendedMapMode;

FileChannel.MapMode mode = ExtendedMapMode.READ_WRITE_SYNC;
```

| Mapping mode | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| `FileChannel.MapMode.READ_ONLY` | Đọc mapping thông thường | Không được viết |
| `FileChannel.MapMode.READ_WRITE` | Đọc/ghi file mapping thông thường | `force()` dùng đường flush phù hợp OS/storage |
| `FileChannel.MapMode.PRIVATE` | Copy-on-write, thay đổi không đưa trở lại file gốc theo hợp đồng mode | Không dùng làm durable shared data |
| `ExtendedMapMode.READ_ONLY_SYNC` | Read-only mapping dành cho file NVM | Nền tảng cần hỗ trợ synchronous NVM mapping |
| `ExtendedMapMode.READ_WRITE_SYNC` | Read/write mapping dành cho file NVM | Với implementation hỗ trợ, `force()` dùng cache-line writeback |

Trên Linux, Javadoc của `ExtendedMapMode` nêu implementation dùng cờ `MAP_SHARED_VALIDATE` và `MAP_SYNC` khi gọi `mmap`. Mapping chế độ `READ_WRITE_SYNC` có `force()` được triển khai bằng **cache-line writeback** thay vì file-device flush truyền thống.

Đây là **phân biệt quan trọng về cơ chế**, không phải lời hứa Java có quyền bật persistent memory trên **mọi file**, kể cả SSD, NTFS hay network drive.

### 3.2. Unsupported không phải “NVM đã bật”

Javadoc cho biết `FileChannel.map(READ_WRITE_SYNC, ...)` có thể ném `UnsupportedOperationException` nếu implementation/nền tảng không hỗ trợ. Các lỗi `IOException` khác có thể phản ánh file, filesystem hoặc quyền truy cập.

**Hành vi đúng:** khi sản phẩm **bắt buộc** semantics của DAX/NVM, phát hiện thiếu hỗ trợ và **fail closed**: từ chối khởi chạy hoặc chuyển sang chế độ bảo toàn dữ liệu khác **được thiết kế và kiểm thử độc lập**. Không âm thầm thay `READ_WRITE_SYNC` bằng `READ_WRITE` rồi báo người dùng rằng dữ liệu vẫn có guarantee NVM như cũ.

### 3.3. Biên dịch Java 17 với module JDK

Do `ExtendedMapMode` thuộc module JDK-specific, ví dụ độc lập dùng:

```bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 NvmDurabilityLab.java
java --add-modules jdk.nio.mapmode NvmDurabilityLab ...
```

Cú pháp này đã được biên dịch với JDK 24 ở chế độ `--release 17`. Với ứng dụng modular thật, khai báo phụ thuộc module phù hợp và đóng gói module `jdk.nio.mapmode` trong runtime image. **Không** coi nó là API Java SE portable sang mọi nhà triển khai JDK.

### 3.4. `MappedByteBuffer.force()` có ý nghĩa gì?

`MappedByteBuffer.force()` hoặc `force(int index, int length)` buộc những thay đổi của phần mapped buffer được ghi tới storage device chứa file, **với bảo đảm được Javadoc nêu cho local storage device**. Với `READ_WRITE_SYNC` trên NVM được hỗ trợ, đường writeback có thể dùng cache-line operations. Với `READ_WRITE` thông thường, cơ chế OS/file flush khác.

Trong mã:

```java
mapped.put(20, (byte) 0x7F);
mapped.force(20, 1);
```

`force(20,1)` yêu cầu flush dải tính **từ index của mapping**, không phải offset tuyệt đối của file. Implementation có thể flush rộng hơn một byte do page/cache-line granularity. Dù force thành công, vẫn **không thể** suy ra bản ghi gồm nhiều field được commit nguyên tử.

**Không nhầm với `load()` hoặc `isLoaded()`:** hai phương thức đó liên quan tới dữ liệu có hiện diện trong bộ nhớ vật lý hay không, **không phải phép xác nhận đã bền trước mất điện**.

### 3.5. `FileChannel.force(true)` và mapping là hai đường khác nhau

`FileChannel.force(true)` được dùng để buộc những thay đổi của file **qua các phương thức channel** và phần metadata liên quan, tùy storage/OS. Oracle Javadoc nói rõ `FileChannel.force(...)` **không nhất thiết** đẩy các byte đã sửa **thông qua mapped buffer**. Muốn force những thay đổi do `mapped.put(...)`, hãy gọi **`mapped.force(...)`**.

```java
// Sau thao tác ghi qua FileChannel:
channel.force(true);

// Sau thao tác ghi qua MappedByteBuffer:
mapped.force();
```

Các đoạn trên chỉ minh họa nguyên tắc; `channel` và `mapped` là biến đã được tạo. `channel.force(true)` cũng **không tự bảo đảm** directory entry của file mới hoặc tên sau rename đã bền; phần filesystem metadata có contract khác và được xét ở mục 8.

### 3.6. Những giới hạn Java NIO cần nhớ

- `MappedByteBuffer` sống cho tới khi buffer không còn được tham chiếu và được GC xử lý; đóng `FileChannel` **không ngay lập tức unmap** vùng mapped cũ.
- Tránh sửa/truncate file đang mapped từ process khác; Javadoc cảnh báo mapping có thể trở nên không truy cập được, với ngoại lệ không xác định.
- Mapping `FileChannel.map(MapMode,long,long)` dạng `MappedByteBuffer` có giới hạn kích thước một mapping không lớn hơn `Integer.MAX_VALUE`. Với file lớn, chia thành windows/regions; đừng cố mapping cả file lớn hơn giới hạn trong một buffer.
- Mapping file trên **network storage** hoặc remote filesystem không có các bảo đảm local-device trong Javadoc.
- `force()` có thể ném `UncheckedIOException` nếu lỗi ghi buffer ra thiết bị; chương trình không được trả ACK như thể commit thành công khi flush thất bại.
- Một mapping `READ_ONLY_SYNC` không tự chuyển thành writable; chế độ `PRIVATE` không phải đường ghi durable xuống file gốc.

## 4. Phân biệt **durability, atomicity, consistency và recovery**

| Tính chất | Câu hỏi cần trả lời | `force()` tự cung cấp? |
| --- | --- | --- |
| **Durability** | Sau ACK rồi gặp lỗi trong phạm vi cam kết, dữ liệu còn không? | Hỗ trợ ghi tới storage, còn phụ thuộc nền tảng và contract |
| **Atomicity** | Nếu chết giữa ghi N field, có nhận một nửa transaction không? | **Không** |
| **Ordering** | Field body phải bền trước marker, có thiết lập quan hệ bền không? | Cần tổ chức nhiều pha force và xác minh |
| **Consistency** | Recovery chỉ trả record đúng schema/checksum/version không? | Phải do ứng dụng kiểm tra |
| **Isolation** | Hai process ghi cùng mapping có xung đột không? | Không tự cung cấp transaction/lock |
| **Availability** | Khi storage hỏng, ứng dụng có tiếp tục phục vụ không? | Không, cần thiết kế failover |
| **Replication** | Bản sao trên máy khác có bền và đồng bộ không? | Không |
| **Discoverability** | File sau CREATE/RENAME còn tên được mở sau power loss không? | Cần xét metadata/directory sync riêng |

**Độ bền không bằng toàn vẹn.** Việc bảo đảm tất cả bytes đã được flush tới một persistence domain không thể phát hiện một record bị ghi sai logic hoặc đồng thời bị ghi đè. Hãy gắn invariants của ứng dụng với phiên bản layout, checksum và quy trình phục hồi.

### 4.1. Torn write và partial write

Một record có thể gồm `generation`, `length`, `payload`, `checksum` và `commit marker`. Nếu chết khi đang ghi, một số trường có thể là giá trị mới và một số còn của bản cũ. Nếu code chỉ kiểm tra `marker==COMMITTED`, nó có thể tin nhầm dữ liệu bị xé (*torn record*).

Cần ít nhất:

1. Có **hai slot** hoặc cấu trúc copy-on-write tránh phá bản đã commit gần nhất.
2. **Vô hiệu hóa slot sẽ ghi** trước khi đè nội dung; force trạng thái không hợp lệ.
3. Ghi body, checksum, version/generation; force body.
4. Chỉ sau đó mới ghi marker và force marker.
5. Recovery kiểm tra magic/version, kích thước, checksum, marker, generation trước khi trả giá trị.

Đây là **mẫu đơn giản để học**, **không phải một transactional NVM engine hoàn chỉnh**. CRC32C có thể có collision, không phải chữ ký mật mã; marker 32 bit cũng **không được Java bảo đảm có ghi atomic trước power loss trên mọi thiết bị**. Thiết kế production cần đánh giá atomic write granularity, cache-line boundaries, persist ordering, fault injection và chọn journal/WAL/transaction engine đã được kiểm định khi contract nghiêm ngặt.

### 4.2. Không tự động gán atomicity cho `ByteBuffer.putLong`

`mapped.putLong(...)` ghi tám byte từ góc nhìn Java API. Nó **không tự hứa** tám byte được ghi bền nguyên tử trên mọi persistent memory sau power cut. Độ nguyên tử thực tế có thể phụ thuộc alignment, CPU, cache line, filesystem, firmware và cách crash xảy ra.

Với nhiều writer, các thao tác trên mapped buffer còn phải được **đồng bộ** theo concurrency protocol. `force()` không thay thế locks, transaction isolation hay memory-ordering discipline của ứng dụng.

## 5. Ví dụ chạy được Java 17+: hai bản ghi, hai pha commit và phục hồi

Ví dụ dùng file **128 byte** chia thành **hai slot 64 byte**, mỗi slot chứa:

| Offset trong slot | Độ dài | Ý nghĩa |
| --- | ---: | --- |
| 0 | 4 | `MAGIC` — nhận diện định dạng |
| 4 | 8 | `generation` — số phiên bản tăng |
| 12 | 4 | Độ dài payload UTF-8 |
| 16 | 4 | CRC32C trên magic/generation/length/payload |
| 20 | 32 | Vùng bytes payload |
| 52 | 4 | Dự phòng |
| 56 | 4 | `COMMIT` marker |
| 60 | 4 | Dự phòng |

**File test chỉ có một writer.** Slot A giữ bản `generation=1, alpha`. Chuẩn bị slot B với `generation=2, beta`, nhưng marker chưa commit. Nếu recovery thấy B chưa commit, vẫn trả A. Sau khi commit B và force marker, recovery chọn B. Nếu cố ý làm hỏng B thì checksum loại B, recovery trở về A.

Mục tiêu là minh họa **invariants và failpoints có thể kiểm chứng**, không phải cam kết đủ mọi loại mất điện.

**Tệp `NvmDurabilityLab.java` — Java 17+:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.CRC32C;
import jdk.nio.mapmode.ExtendedMapMode;

public class NvmDurabilityLab {
    static final int SLOT_SIZE = 64;
    static final int FILE_SIZE = 2 * SLOT_SIZE;
    static final int MAGIC = 0x4E564D31; // NVM1
    static final int COMMIT = 0x434F4D54; // COMT
    static final int DATA_OFFSET = 20;
    static final int DATA_SIZE = 32;
    static final int MARKER_OFFSET = 56;

    record Record(long generation, String text) {}

    static int checksum(long generation, int size, byte[] content) {
        ByteBuffer data = ByteBuffer.allocate(4 + 8 + 4 + size)
                .order(ByteOrder.BIG_ENDIAN);
        data.putInt(MAGIC).putLong(generation).putInt(size)
                .put(content, 0, size);
        CRC32C crc = new CRC32C();
        crc.update(data.array(), 0, data.position());
        return (int) crc.getValue();
    }

    static Record read(MappedByteBuffer map, int slot, boolean needsCommit) {
        int base = slot * SLOT_SIZE;
        if (needsCommit && map.getInt(base + MARKER_OFFSET) != COMMIT) {
            return null;
        }
        if (map.getInt(base) != MAGIC) {
            return null;
        }
        long generation = map.getLong(base + 4);
        int size = map.getInt(base + 12);
        if (generation <= 0 || size < 0 || size > DATA_SIZE) {
            return null;
        }
        byte[] text = new byte[size];
        for (int i = 0; i < size; i++) {
            text[i] = map.get(base + DATA_OFFSET + i);
        }
        if (map.getInt(base + 16) != checksum(generation, size, text)) {
            return null;
        }
        return new Record(generation, new String(text, StandardCharsets.UTF_8));
    }

    static void stage(MappedByteBuffer map, int slot, long generation, String text) {
        byte[] raw = text.getBytes(StandardCharsets.UTF_8);
        if (raw.length > DATA_SIZE) {
            throw new IllegalArgumentException("payload too long");
        }
        int base = slot * SLOT_SIZE;

        // Invalidate the older slot first and persist that invalidation.
        map.putInt(base + MARKER_OFFSET, 0);
        map.force(base + MARKER_OFFSET, Integer.BYTES);

        // Write body, then persist it before publishing COMMIT.
        map.putInt(base, MAGIC);
        map.putLong(base + 4, generation);
        map.putInt(base + 12, raw.length);
        map.putInt(base + 16, checksum(generation, raw.length, raw));
        for (int i = 0; i < DATA_SIZE; i++) {
            map.put(base + DATA_OFFSET + i, i < raw.length ? raw[i] : (byte) 0);
        }
        map.force(base, DATA_OFFSET + DATA_SIZE);
    }

    static void commit(MappedByteBuffer map, int slot) {
        int index = slot * SLOT_SIZE + MARKER_OFFSET;
        map.putInt(index, COMMIT);
        map.force(index, Integer.BYTES);
    }

    static Record latest(MappedByteBuffer map) {
        Record a = read(map, 0, true);
        Record b = read(map, 1, true);
        if (a == null) return b;
        if (b == null) return a;
        return a.generation() >= b.generation() ? a : b;
    }

    public static void main(String[] args) throws IOException {
        if (args.length < 2 || args.length > 3 ||
                (args.length == 3 && !args[2].equals("sync"))) {
            throw new IllegalArgumentException(
                    "usage: <init|stage|commit|inspect|corrupt> <path> [sync]");
        }
        String action = args[0];
        Path path = Path.of(args[1]);
        boolean sync = args.length == 3;
        FileChannel.MapMode mode = sync
                ? ExtendedMapMode.READ_WRITE_SYNC
                : FileChannel.MapMode.READ_WRITE;

        if (action.equals("init")) {
            try (FileChannel ch = FileChannel.open(path,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {
                ch.position(FILE_SIZE - 1);
                ch.write(ByteBuffer.wrap(new byte[] {0}));
                ch.force(true);
                MappedByteBuffer map = ch.map(mode, 0, FILE_SIZE);
                map.order(ByteOrder.BIG_ENDIAN);
                stage(map, 0, 1L, "alpha");
                commit(map, 0);
                System.out.println("initialized=alpha");
            }
            return;
        }

        try (FileChannel ch = FileChannel.open(path, StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
            if (ch.size() != FILE_SIZE) {
                throw new IOException("unexpected file size");
            }
            MappedByteBuffer map = ch.map(mode, 0, FILE_SIZE);
            map.order(ByteOrder.BIG_ENDIAN);
            switch (action) {
                case "stage" -> {
                    if (read(map, 0, true) == null) {
                        throw new IllegalStateException("baseline invalid");
                    }
                    stage(map, 1, 2L, "beta");
                    System.out.println("staged=beta");
                }
                case "commit" -> {
                    Record staged = read(map, 1, false);
                    if (staged == null || staged.generation() != 2L
                            || !staged.text().equals("beta")) {
                        throw new IllegalStateException("staged record invalid");
                    }
                    commit(map, 1);
                    System.out.println("committed=beta");
                }
                case "inspect" -> {
                    Record valid = latest(map);
                    System.out.println(valid == null
                            ? "latest=NONE"
                            : "latest=" + valid.generation() + ":" + valid.text());
                }
                case "corrupt" -> {
                    int index = SLOT_SIZE + DATA_OFFSET;
                    map.put(index, (byte) '?');
                    map.force(index, 1);
                    System.out.println("corruptedSlot=1");
                }
                default -> throw new IllegalArgumentException("unknown action");
            }
        }
    }
}
```

### 5.1. Biên dịch và chạy demo **không cần NVM**

Với Windows hoặc filesystem thông thường, dùng mặc định `READ_WRITE` (không thêm tham số cuối `sync`). Đây là phép thử **thuật toán recovery** và các API `MappedByteBuffer`, **không chứng minh NVM/power-loss durability**.

```bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 NvmDurabilityLab.java

java --add-modules jdk.nio.mapmode NvmDurabilityLab init nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab inspect nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab stage nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab inspect nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab commit nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab inspect nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab corrupt nvm-lab.dat
java --add-modules jdk.nio.mapmode NvmDurabilityLab inspect nvm-lab.dat
```

**Stdout chính xác đã kiểm chứng** (tám lệnh `java` chạy riêng, mỗi lệnh in một dòng):

```text
initialized=alpha
latest=1:alpha
staged=beta
latest=1:alpha
committed=beta
latest=2:beta
corruptedSlot=1
latest=1:alpha
```

Giải thích:

1. `init` tạo file mới **128 byte** bằng `CREATE_NEW`, tránh đè file dữ liệu tồn tại; thiết lập một slot A hợp lệ `gen=1,alpha`.
2. `inspect` là **process mới**, đọc file từ storage/mapping. Lúc này recovery thấy `alpha`.
3. `stage` chuẩn bị slot B: trước tiên vô hiệu hóa commit marker và force, rồi ghi body/checksum và force. **Chưa** viết marker cuối.
4. `inspect` tiếp theo không thấy B đã commit nên vẫn trả `alpha`. Đây là hành vi mong muốn nếu sự cố xảy ra khi mới chuẩn bị.
5. `commit` kiểm tra nội dung B rồi đặt marker, gọi `force(index,4)`. Lần `inspect` sau chọn `gen=2,beta`.
6. `corrupt` cố tình sửa một byte trong payload B và force. Recovery phát hiện checksum không khớp, loại B và quay về A là bản `alpha` còn hợp lệ.

**Điểm quan trọng:** toàn bộ phép thử có OS và nguồn điện hoạt động, chỉ thay process; nó **không** chứng minh gì về khả năng chịu **OS crash/power cut**. Bước `corrupt` là lỗi dữ liệu có chủ đích, không phải simulation đầy đủ cho torn write, controller cache hoặc mất điện.

**Cảnh báo về thao tác:** chương trình ghi file thật. Chỉ chạy với một **tệp test mới** trong thư mục thử nghiệm. `init` sẽ từ chối file đã tồn tại; nếu muốn chạy lại, tạo path test mới và chỉ xóa file cũ sau khi xác nhận không chứa dữ liệu cần giữ. Không chạy `corrupt` trên file sản xuất.

### 5.2. Thử mode NVM trên **nền tảng DAX được hỗ trợ**

Chỉ trên một môi trường **đã xác nhận có NVM + filesystem DAX + mapping `MAP_SYNC` được hỗ trợ**, thử thêm `sync`:

```bash
java --add-modules jdk.nio.mapmode NvmDurabilityLab init /mnt/pmem-lab/nvm-lab.dat sync
java --add-modules jdk.nio.mapmode NvmDurabilityLab inspect /mnt/pmem-lab/nvm-lab.dat sync
```

**Đường dẫn chỉ là ví dụ**; `/mnt/pmem-lab` phải được đội vận hành cấu hình bằng thiết bị và filesystem thực sự có persistent mapping. Lệnh không tự tạo DAX device hoặc bật `MAP_SYNC` trên ổ đĩa bất kỳ.

Nếu `map(ExtendedMapMode.READ_WRITE_SYNC,...)` ném `UnsupportedOperationException`, `IOException` hoặc lỗi mapping, **không được coi là bài kiểm chứng durability đã đạt**. Hãy ghi rõ môi trường không hỗ trợ hoặc chưa cấu hình đúng và khắc phục hạ tầng trước khi làm fault injection.

### 5.3. Kết quả kiểm chứng về tính khả dụng

Trong thử nghiệm với Windows và OpenJDK/HotSpot 24.0.2:

- Biên dịch bằng `javac --release 17 --add-modules jdk.nio.mapmode`: **thành công**.
- Mapping thường `FileChannel.MapMode.READ_WRITE`: **thành công**, tám lệnh khôi phục có stdout đúng như trên.
- Yêu cầu `READ_WRITE_SYNC` trên file thử Windows: **`UnsupportedOperationException`** trong môi trường đó.

Đây là bằng chứng **API và lựa chọn mode được kiểm tra theo platform**, chứ **không** phải dấu hiệu Java 24 bỏ hỗ trợ JEP 352. `READ_WRITE_SYNC` vẫn có trong Oracle Javadoc mới; thiếu hỗ trợ mapping thực tế là tình huống **môi trường đích không đáp ứng điều kiện**.

## 6. Những giới hạn có chủ đích của demo

Bài thực hành dùng **CRC32C + commit marker** để minh họa recovery; không dùng nó như cơ sở dữ liệu NVM hoàn thiện.

1. **Không bảo đảm marker ghi nguyên tử:** đặt `int COMMIT` không tự bảo đảm atomic persistent store trên mọi phần cứng. Kiểm tra cả checksum, generation, length và bản sao giúp tăng khả năng phát hiện nhưng không loại mọi tình huống.
2. **CRC32C không phải mật mã:** có xác suất collision, không bảo vệ trước sửa đổi có chủ ý. Với threat model cần integrity chống giả mạo, phải dùng cơ chế xác thực phù hợp và quản lý khóa.
3. **Không kiểm tra dữ liệu của nhiều writer:** code chỉ dành cho **single writer**; hai JVM cùng ghi có thể làm hỏng state. Cần file locking/serialization hoặc transactional engine đúng yêu cầu.
4. **Không xử lý generation overflow:** bản production cần policy cho wrap-around và version/migration.
5. **Không đảm bảo atomic rename/metadata:** `init` tạo file, `channel.force(true)` không tự đảm bảo parent directory entry bền. Chuẩn bị file/data path và metadata trước khi test power-loss.
6. **Không đảm bảo hardware persistence domain:** `force()` trên local device có contract theo Java API, nhưng power loss ở tầng thiết bị/firmware/nguồn cần được xác thực với hạ tầng thật.
7. **Không có external ACK oracle:** khi crash xảy ra sát thời điểm response, cần cơ chế phân biệt transaction đã ACK hay chưa, có thể phải ghi nhận độc lập hoặc dùng request ID/idempotency key.
8. **Không có benchmark throughput:** tám bước chỉ kiểm tra logic trạng thái, không đo write latency/durability rate hoặc overhead của `force`.
9. **Không khẳng định OS restart bằng process restart:** chương trình mở file lại sau process kết thúc, Linux page cache vẫn có thể còn nếu chỉ kill process.
10. **Không giải quyết device failure:** một file và hai slot trên cùng thiết bị không thay thế backup/replica.

**Nếu ứng dụng thực sự cần ACID transactions, nhiều writer, failover hoặc bảo vệ lỗi phần cứng cấp cao, ưu tiên một storage engine đã được kiểm định** (database có WAL/snapshot/replication theo SLA), rồi test trên hạ tầng đích. Mẫu này dành cho việc *hiểu thứ tự ghi bền và xây bài kiểm thử*, không khuyến nghị xây database mới trong mọi sản phẩm.

## 7. Kiểm thử fault injection: ma trận checkpoint

Để kiểm chứng durability, cần biết **lỗi xảy ra ở khoảng giữa hai thao tác nào**. Với hai slot A/B và `alpha` đã commit ban đầu:

| Điểm chèn lỗi | Trạng thái lý thuyết trước lỗi | Recovery chấp nhận | Recovery không chấp nhận |
| --- | --- | --- | --- |
| Trước khi bắt đầu ghi B | A đã commit | `alpha` | Trống/hỏng nếu A còn tốt |
| Sau khi marker B = invalid, trước khi force marker | A vẫn nguyên | `alpha` | Trả B chưa commit |
| Sau force marker invalid, trước khi ghi body B | B invalid | `alpha` | Trả payload cũ B |
| Đang ghi header/payload B | B chưa commit | `alpha` | Trả body nửa cũ nửa mới như hợp lệ |
| Sau `force(body)`, trước marker commit | B đã có body nhưng invalid | `alpha` | Trả `beta` như đã ACK |
| Đang ghi marker B, trước `force(marker)` trả về | B có thể chưa bền hoàn toàn | `alpha` hoặc `beta` hợp lệ, theo contract chưa ACK | Giá trị hỏng/torn được chấp nhận |
| Sau `force(marker)` hoàn tất, **trước ACK** | B được yêu cầu persist nhưng client chưa biết | `beta` nếu guarantee đáp ứng, cần idempotency khi retry | Nhận record hỏng |
| **Sau ACK** đã gửi thành công | B đã commit theo protocol | **`beta` hợp lệ** | Mất `beta` hoặc chỉ còn `alpha` trong fault model được cam kết |
| Sau khi B bị corrupt có chủ đích | CRC của B không hợp lệ | `alpha` từ slot A | Trả dữ liệu B hỏng |

**Lưu ý:** bảng thể hiện **quy tắc mong muốn và assumptions**, không phải một theorem được chứng minh cho mọi tổ hợp CPU/OS/filesystem. Trong trường hợp crash giữa ghi marker, phải xét khả năng torn marker, reordering và checksum collision. Thiết kế production có thể cần journal, sequence metadata, double checksum, atomic commit field phù hợp cache-line/alignment, hoặc transactional storage chuyên dụng.

### 7.1. Tạo failpoints trong process test

Thực hiện trên process thí nghiệm, **không** trên ứng dụng phục vụ người dùng. Ví dụ:

- Thêm một tùy chọn kiểm thử để **dừng có chủ đích ngay sau từng lệnh force**.
- Với một lần chạy khác, dừng **trước** lệnh force tiếp theo.
- Chạy process mới thực hiện recovery và xuất `generation`, `payload`, `checksumValid`.
- Lặp lại **nhiều lần** và với những vùng ghi khác nhau.

Việc gọi `System.exit(...)` hoặc tắt tiến trình ở failpoint chỉ tạo ra **process-level crash model**. Trên Linux, dùng cơ chế dừng process test do harness quản lý; **không** suy ra kết quả tương đương kernel panic/power cut.

Trong demo, các lệnh `init`, `stage` và `commit` cố ý là **process riêng**, giúp thấy recovery không dựa vào state của một process. Với thử nghiệm nghiêm ngặt, bổ sung checkpoints nằm **giữa từng store**, không chỉ cuối pha.

### 7.2. Kiểm thử kernel/power failure trong **lab được phép**

Với hợp đồng yêu cầu chịu được mất điện, cần môi trường chuyên dụng:

1. **Snapshot/backup dữ liệu thử và baseline của thiết bị**; bảo đảm không ảnh hưởng dịch vụ thật.
2. Xác nhận hardware persistence domain (ADR/eADR hoặc thiết bị tương đương), firmware, OS kernel, driver, DAX filesystem, mount config và bản JDK.
3. Chạy workload tạo nhiều generations, mỗi generation có ID và checksum.
4. Ghi **oracle của các ACK** qua kênh quan sát độc lập có tính bền phù hợp, tránh dùng chính file đang thử làm nguồn chân lý duy nhất.
5. Tại một failpoint hoặc thời điểm có kiểm soát, mô phỏng **OS crash** hoặc **ngắt nguồn thiết bị thử** bằng hạ tầng được phê duyệt; không tự áp dụng thao tác phá hủy lên máy production.
6. Khởi động lại **OS/máy**, không chỉ Java process; chạy recovery bằng ứng dụng độc lập.
7. Đối chiếu generations đã ACK và invariants: không có record rách, không mất ACK được cam kết, không chấp nhận sequence sai, metadata/file path còn tồn tại.
8. Thu thập log lỗi I/O, trạng thái file system recovery, các cảnh báo unsafe shutdown/counter hardware và các mẫu torn write.
9. Lặp lại trên nhiều điểm lỗi, payload sizes, áp lực ghi và thay đổi tải.
10. Ghi kết quả theo từng lớp fault model; nếu chỉ kiểm thử process kill, đánh dấu **“process crash verified”**, không ghi **“power loss verified”**.

**An toàn vận hành:** chỉ đội có quyền quản trị lab mới nên thực hiện ngắt nguồn hoặc kernel fault injection trên thiết bị test đã được phê duyệt. Đừng đặt lệnh gây crash kernel hoặc tắt nguồn cưỡng bức trong tài liệu có thể bị copy sang production.

### 7.3. Expected outcome cần dựa trên **ACK thật**

Một vấn đề thường bị bỏ qua: client mất mạng đúng lúc server commit; client không biết request đã thành công. Trong thử nghiệm, đừng giả định “không nhận ACK” nghĩa là operation chắc chắn chưa commit. Đặc tả phải cho phép **ambiguous result before ACK** và định nghĩa quy tắc retry/idempotency.

Với những operation đã ACK (server đã gửi thành công và client/harness xác nhận đã nhận), sau crash trong fault model hỗ trợ phải tồn tại bản tương ứng hoặc trạng thái mới hơn hợp lệ. Nếu không, đó là **durability failure**.

Việc ghi nhận ACK độc lập cũng có fault model riêng; oracle mất dữ liệu có thể làm bạn kết luận sai về thiết bị được thử. Chọn kênh oracle và cách đối chiếu có độ tin cậy phù hợp.

## 8. Metadata, tạo file và đổi tên: một nguồn lỗi khác

Một mapped buffer chỉ bao gồm **nội dung vùng ánh xạ**. File được truy cập qua **directory entry và metadata của filesystem**. Để nói “sau power cut tôi vẫn tìm thấy file X chứa data Y”, phải kiểm tra **cả hai tầng**.

### 8.1. `force` buffer không đồng nghĩa tên file đã bền

`mapped.force()` nhắm tới nội dung mapping. `FileChannel.force(true)` có thể yêu cầu dữ liệu và metadata của file qua channel, nhưng **không bảo đảm parent directory entry** khi mới tạo hoặc rename. Linux `fsync(2)` manual nói muốn bảo đảm entry trong directory đã tới disk cần **fsync trên file descriptor của directory**.

Standard Java 17 API **không có một phương thức portable đảm bảo fsync mọi directory trên mọi OS**. Với sản phẩm yêu cầu crash-safe file creation/rename, cần dùng cơ chế native/platform-specific được hỗ trợ, kiểm chứng từng filesystem và kiểm thử bằng power-loss fault injection.

### 8.2. Atomic rename không bằng durable rename

`Files.move(..., StandardCopyOption.ATOMIC_MOVE)` yêu cầu rename/move nguyên tử **nếu filesystem hỗ trợ**, nhưng đó không đồng nghĩa tên mới đã được persist qua power cut. Khi tạo file tạm, ghi, force, đổi tên, vẫn cần xem xét **fsync directory** cùng storage and filesystem semantics.

Không suy ra một quy trình “temp → rename” trên overlayfs, network mount hay cross-filesystem move luôn chịu lỗi giống ext4/xfs local.

### 8.3. Chuẩn bị file và metadata trước khi đo persistence

Ví dụ `NvmDurabilityLab.init`:

- Tạo file mới `CREATE_NEW`; đảm bảo không ghi đè file có sẵn.
- Ghi byte cuối để file có kích thước 128 rồi `channel.force(true)`.
- Map và viết bản khởi tạo đã commit bằng `mapped.force`.
- Không có bước portable fsync parent directory trong demo.

Vì vậy, **không sử dụng `init` như một phép thử bảo đảm file mới vẫn có tên sau mất điện**. Trong test endurance, có thể chuẩn bị file và metadata **trước** pha fault injection; vẫn phải xác minh OS/filesystem đã đảm bảo các bước chuẩn bị theo policy.

## 9. Xác minh môi trường Linux DAX / NVM

### 9.1. NVM không đồng nghĩa SSD, và DAX không tự bật

**NVM** là tính chất của phần cứng/đường lưu. **DAX** (*Direct Access*) là khả năng filesystem ánh xạ dữ liệu từ thiết bị memory-like trực tiếp vào user-space, tránh thêm một lớp page cache thông thường. Linux kernel documentation mô tả `S_DAX` là trạng thái DAX **đang có hiệu lực** của inode và `FS_XFLAG_DAX` là cờ cấu hình/hưởng thừa cho file.

Đừng suy luận một file là DAX chỉ vì:

- Đường dẫn nằm trong `/mnt/pmem`.
- Tên thiết bị chứa `pmem` hoặc `nvdimm`.
- Filesystem được mount với một option bạn từng nhớ là DAX.
- `MappedByteBuffer` có `isLoaded()==true`.
- Java program chạy được với mapping thường.

Với Linux hiện hành, hãy đối chiếu tài liệu kernel cho **filesystem và phiên bản kernel** đang dùng, kiểm tra `S_DAX` qua công cụ `statx`/kernel interface thích hợp, đồng thời xác nhận `READ_WRITE_SYNC` mapping thực sự thành công.

### 9.2. Checklist hạ tầng phải ghi kèm test result

| Thành phần | Cần ghi nhận |
| --- | --- |
| CPU/hardware | Model, cache-line behavior, persistence domain ADR/eADR, thông tin nguồn điện dự phòng |
| NVM/storage | Loại thiết bị, firmware, DAX namespace/config, tình trạng sức khỏe |
| Kernel/OS | OS/version/kernel, memory-management và DAX driver |
| Filesystem | ext4/xfs/loại khác, `S_DAX` thực tế, mount options, journaling/policy |
| JDK | Vendor, build đầy đủ, module `jdk.nio.mapmode`, GC/JVM options có ảnh hưởng workload |
| Mapping | `READ_WRITE_SYNC` hay `READ_WRITE`, offset/size, alignment, exception |
| Data layout | Format version, marker, checksum, slot size, generation/epoch |
| Fault model | Process kill, OS crash, power loss, device fault và điểm fault injection |
| Quan sát | Log flush errors, ACK oracle, recovery result, raw file hash nếu hữu ích |
| Điều kiện | Số lượt thử, tải nền, kích thước dữ liệu, tỷ lệ lỗi được đo |

Nếu thiếu phần mô tả **lỗi đã được inject**, kết quả “PASS” không có nghĩa rõ ràng. Hãy ghi **“PASS cho process kill”** hoặc **“PASS cho power cut với cấu hình X”** thay vì PASS chung cho mọi sự cố.

### 9.3. Network filesystem và virtualization

Javadoc của `MappedByteBuffer.force` bảo đảm local-storage semantics theo phạm vi nó quy định, **không hứa cùng điều đó cho remote filesystems**. Với NFS, overlay, distributed filesystem hoặc virtual disk có cache write-back, guarantee phụ thuộc nhiều tầng khác: client cache, server ACK, storage backend, replication và hypervisor.

Một VM restart **không mặc định** tương đương **physical power cut**. Nếu VM/hypervisor còn giữ cache trong host, phép thử sẽ không chạm persistence boundary của thiết bị. Cần mô tả chính xác tầng nào thực sự bị crash.

## 10. Thiết kế benchmark hiệu năng **không làm yếu durability**

`READ_WRITE_SYNC` với cache-line writeback có mục tiêu giảm overhead so với đường flush file truyền thống trên NVM được hỗ trợ, nhưng **không có số phần trăm tăng tốc cố định**. Trước khi tối ưu:

1. Chọn **durability contract** và fault model rõ ràng.
2. Chạy correctness/recovery tests qua các failpoints đã liệt kê.
3. Giữ cùng hardware, OS, filesystem, JDK, dataset, layout và payload sizes khi so sánh.
4. Đo latency của từng `force(range)`, throughput, tail latency (p95/p99), CPU, cache flushes/OS faults.
5. Theo dõi CPU cache line writeback và tình trạng storage saturation khi có công cụ phù hợp.
6. Đo tỷ lệ failed recoveries sau fault injection, không chỉ số transaction/s.
7. Tăng batching/cắt giảm `force()` **chỉ khi** điều đó vẫn đáp ứng điểm ACK và mất dữ liệu được phép theo contract.
8. Không tối ưu bằng cách “bỏ force và kiểm tra thấy dữ liệu vẫn còn sau restart” — đó là lỗi phương pháp.

**Một thiết kế có thể nhanh hơn nhưng kém bền hơn** nếu trả ACK trước khi force phù hợp. Khi benchmark, phải giữ **mức bảo đảm giống nhau**, nếu không kết quả throughput không so sánh được.

### 10.1. Batching và nhóm commit

Thay vì force sau mỗi bản ghi, một hệ thống có thể gom nhiều bản ghi rồi persist cả batch, nhưng phải rõ:

- ACK chỉ gửi **sau** khi batch đã bền theo fault model.
- Một crash trước force batch có thể làm mất cả nhóm **chưa ACK**.
- Recovery phân biệt trạng thái batch đã xác nhận và đang chuẩn bị.
- Không cho phép callback khác phát ACK sớm vì thấy bytes đã được viết vào virtual memory.
- Giới hạn bộ nhớ/độ trễ và ghi lại group-commit size trong test report.

Đây là kỹ thuật transaction-level, **không được xây dựng sẵn bởi `ExtendedMapMode`**.

## 11. Các lỗi thường gặp

### Lỗi 1 — “`MappedByteBuffer.put(...)` thành công nghĩa là dữ liệu đã bền”

Sai: `put` thay đổi vùng mapped; durable persistence phải tuân theo `force`/hợp đồng storage và fault model. **Sửa:** định nghĩa điểm force + ACK, kiểm chứng sau crash thực.

### Lỗi 2 — “Đã gọi `force()`, vậy transaction gồm 10 field là atomic”

Sai: `force` không tạo transaction. **Sửa:** version/marker/checksum và recovery protocol hoặc storage engine đã kiểm định.

### Lỗi 3 — “`FileChannel.force(true)` luôn thay `MappedByteBuffer.force()`”

Sai: Javadoc không bảo đảm channel force flush mọi thay đổi qua mapping. **Sửa:** force đúng đối tượng và dải đã sửa.

### Lỗi 4 — “`READ_WRITE_SYNC` chạy được trên mọi OS/file”

Sai: đây là **JDK-specific mapping** cần nền tảng hỗ trợ. **Sửa:** kiểm tra `UnsupportedOperationException`, DAX và mapping thực sự.

### Lỗi 5 — “Test restart một process là đã test mất điện”

Sai: OS/device còn cache. **Sửa:** lab power loss/OS crash theo phạm vi có quyền; phân loại PASS theo từng fault class.

### Lỗi 6 — “Mọi SSD đều là direct-mapped NVM”

Sai: SSD persistent storage và NVM byte-addressable DAX có semantics khác nhau. **Sửa:** xác minh hardware + filesystem + `MAP_SYNC`.

### Lỗi 7 — “`READ_WRITE` và `READ_WRITE_SYNC` có cùng persistence guarantee”

Không được giả định. `READ_WRITE_SYNC` trên NVM được hỗ trợ có đường cache-line writeback và mapping contract riêng. **Sửa:** phân biệt hai mode và không silently downgrade.

### Lỗi 8 — “`isLoaded()==true` chứng minh dữ liệu đã xuống thiết bị”

Sai: đó là chỉ báo residency, không phải persistence. **Sửa:** dùng `force`/fault tests.

### Lỗi 9 — “Một CRC32C bảo vệ mọi lỗi và mọi kẻ tấn công”

Sai: CRC có collision và không xác thực mật mã. **Sửa:** dùng nó để phát hiện corrupt vô ý trong bài học; threat model chống giả mạo cần giải pháp khác.

### Lỗi 10 — “ACK rồi nhưng dữ liệu biến mất là bình thường”

Không bình thường **nếu** loss nằm trong fault model đã cam kết. **Sửa:** test failure sau ACK, ngừng release khi thiếu durable guarantee.

### Lỗi 11 — “Không nhận ACK nghĩa là chắc chắn không commit”

Sai: có thể commit đã persist, response bị mất. **Sửa:** idempotency/retry protocol và đối chiếu transaction ID.

### Lỗi 12 — “Đã force file rồi thì tên sau rename cũng tồn tại”

Không chắc. Directory metadata cần sync riêng theo semantics OS. **Sửa:** dùng chiến lược create/rename được kiểm thử crash-safe.

### Lỗi 13 — “Cứ dùng `Files.move(ATOMIC_MOVE)` là durable”

Atomic move không tự tương đương durable rename. **Sửa:** phân biệt atomic namespace change với persistence của directory entry.

### Lỗi 14 — “Hai writer cùng sửa mapped bytes sẽ được force serialize”

Không. Cần concurrency control rõ ràng; force không cung cấp isolation. **Sửa:** single writer, file lock hoặc transaction protocol.

### Lỗi 15 — “`MappedByteBuffer.force(index,len)` chỉ flush đúng một byte”

Không bảo đảm; implementation có thể flush nhiều hơn do hardware granularity. **Sửa:** chỉ dựa vào guarantee vùng được chọn, không dựa chi phí byte tuyệt đối.

### Lỗi 16 — “Process recovery đọc được dữ liệu nghĩa là power-loss safe”

Sai: nếu OS không crash, buffers và cache vẫn sống. **Sửa:** kiểm thử đúng tầng lỗi, ghi rõ kernel/host/power bị tác động.

### Lỗi 17 — “Truy cập file đang mapped rồi truncate ở process khác là an toàn”

Sai: mapping có thể trở nên không truy cập được/raise unspecified exception. **Sửa:** cấm thay đổi backing file khi mapping đang dùng, có lock và lifecycle.

### Lỗi 18 — “Bỏ qua lỗi `force()` rồi vẫn ACK”

Sai: `UncheckedIOException` hoặc I/O failure cần đưa operation vào trạng thái lỗi/unknown và xử lý. **Sửa:** không trả ACK thành công khi chưa hoàn thành pha durability.

### Lỗi 19 — “Chỉ benchmark latency, không đo phục hồi”

Một thiết kế bỏ force có thể nhanh hơn nhưng đánh đổi durability. **Sửa:** kiểm chứng invariants trước, so sánh hiệu năng chỉ giữa các cấu hình có guarantee tương đương.

## 12. Checklist kiểm chứng trước khi phát hành

- [ ] Đã liệt kê fault model theo từng loại: process crash, OS crash, power loss, device fault, corruption, concurrent writers.
- [ ] Đã định nghĩa ACK point và “durable” nghĩa chính xác những gì trên môi trường đích.
- [ ] Đã xác minh phần cứng NVM và persistence domain ADR/eADR hoặc tương đương.
- [ ] Đã xác minh filesystem thực sự ở trạng thái DAX nếu dùng `READ_WRITE_SYNC`.
- [ ] Có JDK vendor/version hỗ trợ module `jdk.nio.mapmode` và kiểm tra map mode thật.
- [ ] Không âm thầm fallback từ `READ_WRITE_SYNC` sang `READ_WRITE` khi contract đòi NVM.
- [ ] Mọi vùng mapped được `force` đúng thứ tự trước ACK.
- [ ] Có phục hồi old/new record với version, checksum, marker và xử lý dữ liệu corrupt.
- [ ] Đã kiểm chứng trường hợp chết trong lúc viết body và trong lúc viết commit marker.
- [ ] Đã kiểm chứng trường hợp chết **sau khi force và ACK**.
- [ ] Đã xác định hành vi khi `force` lỗi; không giả định dữ liệu đã bền.
- [ ] Có chính sách single-writer hoặc khóa/transactions phù hợp.
- [ ] Đã xét file/directory metadata, đặc biệt CREATE/RENAME.
- [ ] Đã kiểm tra trên OS/file system/JDK/firmware **thật**, không chỉ VM/process restart.
- [ ] Có ACK oracle và log kết quả để chứng minh commit đã được client công nhận.
- [ ] Có backup/replication khi fault model vượt khả năng một thiết bị.
- [ ] Có môi trường fault-injection biệt lập, quyền và quy trình an toàn.
- [ ] Report nêu rõ những fault classes **chưa được kiểm chứng**.
- [ ] Có giới hạn tập tin/log chứa dữ liệu thật và mã hóa/kiểm soát quyền nếu cần.
- [ ] Benchmark latency/throughput chỉ sau khi correctness và durability đạt.

## 13. Bài tập và cách tự đánh giá

1. **Phân loại lỗi:** một process Java bị kill nhưng OS vẫn chạy có giống mất điện rack không? Hãy nêu khác biệt.
2. **API:** viết import và mode `ExtendedMapMode.READ_WRITE_SYNC`, giải thích tại sao phải có module `jdk.nio.mapmode`.
3. **Platform:** trên máy thường `map(READ_WRITE_SYNC,...)` ném `UnsupportedOperationException`; có được tự chuyển sang `READ_WRITE` mà vẫn tuyên bố NVM persistence không?
4. **Force:** phân biệt `channel.force(true)` và `mapped.force(0,64)` khi bytes được sửa qua mapped buffer.
5. **Atomicity:** một record có 5 trường, crash giữa lần ghi thứ ba. `force()` cuối cùng có tự biến tất cả thành transaction không?
6. **Quy trình:** vì sao cần force marker “invalid” trước khi đè slot cũ?
7. **Failpoint:** chạy `init → inspect → stage → inspect`, giải thích tại sao vẫn chọn `alpha`.
8. **Commit:** chạy tiếp `commit → inspect`, giải thích tại sao giờ chọn `beta`.
9. **Corruption:** chạy `corrupt → inspect`, giải thích cách CRC khiến phục hồi về `alpha`.
10. **Checksum:** CRC32C có phải chữ ký mật mã và luôn phát hiện tất cả corruption không?
11. **Directory metadata:** một file vừa `CREATE_NEW`, đã `mapped.force`, nhưng chưa sync directory; sau kernel crash có thể mất điều gì?
12. **ACK:** client timeout trước khi nhận response; server đã force commit. Theo contract client có chắc transaction chưa commit không?
13. **Power failure:** thiết kế một đợt test trên lab với ADR/eADR, DAX active state và các failpoint.
14. **Virtual machine:** VM reboot nhưng host vẫn chạy có đủ để tuyên bố chịu mất nguồn điện vật lý không?
15. **Read-only mapping:** vì sao `READ_ONLY_SYNC` không là đường để commit dữ liệu?
16. **Large file:** nếu file lớn hơn `Integer.MAX_VALUE` bytes, có thể map nó thành một `MappedByteBuffer` duy nhất không?
17. **Production:** lập bảng kết quả `PASS/FAIL/NOT TESTED` theo từng fault class, có JDK build, filesystem, firmware và data invariants.

**Gợi ý đáp án:** (1) OS/device caches vẫn tồn tại khi chỉ kill process; (2) module API JDK-specific; (3) không, cần fail closed hoặc giải pháp khác đã test; (4) channel force không bảo đảm mapped writes; (5) không; (6) tránh hồi sinh slot cũ có marker commit; (7) B chưa commit; (8) B có marker/CRC hợp lệ và generation lớn; (9) checksum B lệch, A còn tốt; (10) CRC có collision; (11) tên file/directory entry có thể chưa bền; (12) không, cần idempotency; (13) môi trường được phê duyệt, so old/new và các ACK; (14) không; (15) read-only; (16) phải chia mapping/windows; (17) chỉ tuyên bố những fault classes đã kiểm chứng.

## 14. Tài liệu tham khảo chính thức và có giá trị hiện hành

- **OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers (Java 14):** mục tiêu và cơ chế mapping NVM, tham khảo thiết kế: https://openjdk.org/jeps/352
- **Oracle Java SE 17 `ExtendedMapMode`:** `READ_ONLY_SYNC`, `READ_WRITE_SYNC`, `MAP_SYNC`, khả năng ném `UnsupportedOperationException`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html
- **Oracle Java SE 25 `ExtendedMapMode`:** xác nhận API JDK-specific vẫn có trong JDK hiện đại: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html
- **Oracle Java SE 17 `MappedByteBuffer`:** `force()`/`force(index,length)`, bảo đảm local storage và giới hạn mapping: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html
- **Oracle Java SE 25 `FileChannel`:** `force(boolean)`, `map(...)` và quan hệ với mapped buffer: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html
- **Oracle JDK 14 Migration Guide:** xác nhận JEP 352 bổ sung file mapping modes cho NVM từ Java 14: https://docs.oracle.com/en/java/javase/14/migrate/index.html
- **Linux kernel — Direct Access for Files:** `S_DAX` so với `FS_XFLAG_DAX` và điều kiện filesystem: https://www.kernel.org/doc/html/latest/filesystems/dax.html
- **Linux `fsync(2)`:** dữ liệu, metadata và yêu cầu sync directory entry: https://man7.org/linux/man-pages/man2/fsync.2.html
- **Linux `msync(2)`:** đồng bộ các thay đổi từ memory-mapped files theo OS: https://man7.org/linux/man-pages/man2/msync.2.html
- **Persistent Memory Glossary, ADR/eADR:** phân biệt các persistence domains: https://pmem.io/glossary/

**Ghi nhớ:** Độ bền của một file ánh xạ NVM không được chứng minh bằng `put`, `force` đơn lẻ, hoặc chỉ chạy lại chương trình. Hãy **định nghĩa lỗi cần chịu**, thiết kế thứ tự **body → force → commit marker → force → ACK**, xác minh **khả năng mapping và persistence domain** của nền tảng đích, rồi **inject đúng loại sự cố và phục hồi bằng process/OS mới** để so với các ACK và invariants. `ExtendedMapMode.READ_WRITE_SYNC` vẫn là API có ý nghĩa từ Java 14 đến hiện nay, nhưng **không tạo atomic transactions, durable filenames hoặc bảo đảm chịu mọi lỗi phần cứng chỉ bằng tên mode**.