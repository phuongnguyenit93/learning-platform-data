# Bộ nhớ không mất dữ liệu và tệp được ánh xạ (NVM / Memory-Mapped Files) trong Java

## Mục tiêu

**Bộ nhớ không mất dữ liệu** (non-volatile memory, NVM) giữ dữ liệu khi không còn nguồn điện. **Memory-mapped file** là kỹ thuật ánh xạ một vùng của **tệp** vào không gian địa chỉ của tiến trình để chương trình đọc/ghi qua buffer như một vùng bộ nhớ, thay vì phải gọi `read()` hoặc `write()` cho từng thao tác.

Hai khái niệm liên quan nhưng **không đồng nhất**: Java có thể ánh xạ một file thường trên SSD/HDD mà **không sử dụng NVM dạng byte-addressable**. Chỉ trên phần cứng, hệ điều hành và filesystem tương thích, ánh xạ file mới tận dụng được đường truy cập persistent memory chuyên biệt.

Nền tảng Java NIO hiện hành là `FileChannel.map(...)` và `MappedByteBuffer`. Điểm gắn với **Java 14** là **JEP 352 — Non-Volatile Mapped Byte Buffers**, bổ sung `jdk.nio.mapmode.ExtendedMapMode.READ_ONLY_SYNC` và `READ_WRITE_SYNC` cho việc ánh xạ file được backing bởi non-volatile RAM.

Sau bài học, bạn có thể:

- Phân biệt **RAM dễ mất dữ liệu**, **NVM/persistent memory**, **SSD/NVMe/HDD** và **tệp được ánh xạ vào bộ nhớ**.
- Hiểu cơ chế `FileChannel.map` và `MappedByteBuffer`, byte offset, size, endianness và ba chế độ `READ_ONLY`/`READ_WRITE`/`PRIVATE`.
- Ghi/đọc dữ liệu nhị phân bằng `putInt`, `putLong`, `getInt`, `getLong`, chọn `ByteOrder` và biết lúc nào cần `force()`.
- Giải thích ranh giới giữa **flush/persistence** và **atomicity/crash consistency**.
- Phân biệt mapping bình thường với `ExtendedMapMode.READ_WRITE_SYNC`/`READ_ONLY_SYNC` và điều kiện DAX/persistent memory.
- Hiểu giới hạn một `MappedByteBuffer`, vòng đời mapping, đồng bộ nhiều thread/process và nguy cơ file bị truncate.
- Biên dịch/chạy ví dụ **Java 17+** trên tệp thông thường, rồi biết cách chuyển ý tưởng sang môi trường NVM thật.

**Phạm vi còn áp dụng:** `FileChannel` và `MappedByteBuffer` là các API hiện hành. `ExtendedMapMode` có từ **Java 14** và vẫn hiện diện trong tài liệu **JDK 25/26**. Đây là module **JDK-specific**, không bảo đảm mọi JVM/OS/filesystem đều hỗ trợ mode đồng bộ. Ví dụ Java dùng JDK 17+, không yêu cầu preview hoặc thư viện PMEM cũ.

## 1. Ba tầng cần phân biệt: bộ nhớ, tệp, persistent storage

### 1.1. RAM, NVM và SSD

| Thành phần | Cách hoạt động chính | Không được suy ra |
|---|---|---|
| **DRAM/RAM thông thường** | Byte-addressable, truy cập nhanh, nội dung mất khi mất điện | Ghi vào RAM là đã lưu bền vững |
| **NVM / persistent memory** | Có thể giữ dữ liệu qua mất điện; một số nền tảng cho truy cập dạng byte thông qua DAX | Mọi thiết bị “non-volatile” đều có cùng cơ chế mapping |
| **SSD/NVMe/HDD** | Thiết bị lưu trữ theo khối hoặc giao thức lưu trữ; nội dung thường được bảo toàn | NVMe SSD chính là NVM byte-addressable của JEP 352 |
| **Memory-mapped file** | Không gian địa chỉ ảo của tiến trình gắn với một vùng backing file | Chỉ cần gọi `map` là đã dùng đường truyền NVM SYNC |

Ví dụ trên một máy Windows có SSD, bạn thường vẫn có thể gọi `FileChannel.map(MapMode.READ_WRITE, ...)` để sửa file. Nhưng điều này **không chứng minh** máy có NVM/DAX phù hợp cho `ExtendedMapMode.READ_WRITE_SYNC`.

### 1.2. Khi nào memory mapping hữu ích?

Một vùng mapping có thể giúp:

1. Thao tác với dữ liệu tại byte offset theo cách gần với truy cập bộ nhớ.
2. Hạn chế các lệnh I/O nhỏ lặp lại cho file lớn và truy cập ngẫu nhiên.
3. Dựa vào quản lý trang bộ nhớ và caching của OS.
4. Chỉ map từng cửa sổ cần thiết của file lớn.
5. Với NVM thực sự, tận dụng cơ chế flush cache lines hiệu quả hơn đường đi qua block-device flush thông thường.

**Không phải mapping luôn nhanh hơn:** với file nhỏ, chỉ đọc một lần hoặc truy cập rất tuần tự, `FileChannel.read`, `InputStream` hay `Files.readAllBytes` có thể đơn giản và hiệu quả hơn. Cần đo trên workload và storage thực tế, tính cả page faults và chi phí setup/flush.

## 2. FileChannel.map tạo vùng MappedByteBuffer

Các lớp phổ biến:

~~~java
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
~~~

Lời gọi minh họa:

~~~java
// channel đã mở với cả quyền READ và WRITE.
MappedByteBuffer buffer =
        channel.map(FileChannel.MapMode.READ_WRITE, 0, 4096);
~~~

Tham số:

- `MapMode.READ_WRITE`: ánh xạ đọc/ghi.
- `0`: **file offset** bắt đầu, tính bằng byte.
- `4096`: kích thước vùng được ánh xạ, tính bằng byte.

`MappedByteBuffer` là một `ByteBuffer` trực tiếp ánh xạ vào file, cho phép truy cập dữ liệu tại các offset mà không cần gọi `FileChannel.write(...)` cho mỗi trường.

### 2.1. Chỉ số là tương đối với cửa sổ map

~~~java
// Đoạn minh họa: file lớn hơn 12 KiB và channel mở để đọc.
MappedByteBuffer window =
        channel.map(FileChannel.MapMode.READ_ONLY, 8192, 4096);
byte first = window.get(0);
~~~

`window.get(0)` tương ứng với byte của **file tại offset 8192**. Nếu dùng `window.getInt(4)`, vị trí bắt đầu trong file là `8192 + 4`, không phải offset 4 của toàn bộ file.

### 2.2. position, limit, capacity và byte order

Một buffer mới được map với `position=0`, `limit=size`, `capacity=size`. Hai cách thao tác:

- `buffer.putInt(4, 123)`: **absolute write** tại index 4, không thay position.
- `buffer.putInt(123)`: **relative write** từ position, tăng position.
- `flip()`: chuyển giới hạn sang position hiện tại và đặt position về 0, hữu ích khi vừa ghi tương đối rồi đọc tương đối.
- `clear()`: đặt lại position/limit, **không xóa dữ liệu trong file**.

Các số nhiều byte cần quy ước **endianness**:

~~~java
// Buffer đã được ánh xạ thành công.
buffer.order(ByteOrder.LITTLE_ENDIAN);
buffer.putInt(0, 1234);
int sameValue = buffer.getInt(0);
~~~

Khi định nghĩa định dạng bền vững, phải ghi rõ byte order, kích thước trường, offsets, magic header, version và encoding. Nếu viết little-endian nhưng đọc big-endian, giá trị có thể sai dù backing file không bị hỏng.

## 3. Ba MapMode chuẩn

| Chế độ | Đọc | Ghi qua mapping | Thay đổi ghi về file gốc? |
|---|---|---|---|
| `READ_ONLY` | Có | **Không** — `ReadOnlyBufferException` khi gọi `put` | Không |
| `READ_WRITE` | Có | Có | **Có**, với việc lan truyền dữ liệu do OS quản lý; dùng `force()` khi cần flush có kiểm soát |
| `PRIVATE` | Có | Có, trong private copy-on-write mapping | **Không**, dữ liệu sửa không được propagate về backing file |

Để map `READ_ONLY`, channel phải mở cho **READ**; để map `READ_WRITE` hay `PRIVATE`, channel phải có cả **READ và WRITE**.

**`PRIVATE` không phải một chế độ lưu dữ liệu bền vững.** Đây là bản đồ copy-on-write: buffer có thể cho thấy nội dung đã sửa nhưng backing file không đổi. Không dùng `PRIVATE` để implement persistence.

## 4. force(): ghi thay đổi tới thiết bị lưu trữ

Khi bạn sửa dữ liệu trong `READ_WRITE` mapping:

~~~java
// Đoạn minh họa: mapped buffer có ít nhất 8 byte.
buffer.putLong(0, 123456789L);
~~~

nội dung vùng mapped được cập nhật, nhưng thời điểm OS thực sự đưa thay đổi xuống storage không nhất thiết trùng với lệnh `putLong`.

`MappedByteBuffer` cung cấp:

~~~java
// Flush toàn vùng hoặc một vùng con của mapped buffer.
buffer.force();
buffer.force(0, Long.BYTES);
~~~

- `force()` flush thay đổi của vùng tương ứng với cả buffer.
- `force(index, length)` flush vùng con, tính index/length theo byte trong buffer.
- Triển khai có thể ghi thêm byte ngoài vùng yêu cầu để phù hợp granularity của storage.
- Lỗi flush có thể xuất hiện dưới dạng `UncheckedIOException`.

Theo Javadoc, với một **file nằm trên thiết bị lưu trữ cục bộ** và buffer được mapped `READ_WRITE`, khi `force()` trả thành công, các thay đổi của buffer tương ứng được bảo đảm ghi tới thiết bị. Với file trên **thiết bị không cục bộ**, Javadoc **không đưa ra** bảo đảm tương đương.

### 4.1. FileChannel.force và MappedByteBuffer.force là hai API khác

~~~java
// Minh họa: channel và buffer đã tồn tại.
channel.force(true);
buffer.force();
~~~

`FileChannel.force(boolean metaData)` áp dụng cho các thay đổi theo hợp đồng thao tác I/O của channel; nó **có thể hoặc không** flush được thay đổi được tạo bằng cách sửa mapped buffer. Để flush **dữ liệu đã sửa qua mapping**, dùng `MappedByteBuffer.force()`.

Nếu còn cần đảm bảo metadata của file như kích thước, tên hay quyền, phải xem quy tắc của filesystem và các operations tương ứng. `force` của vùng mapped không tự có transaction cho toàn bộ metadata.

### 4.2. force không phải một giao dịch nguyên tử

Giả sử record lưu:

~~~text
[magic: 4 bytes][id: 4 bytes][amount: 8 bytes]
~~~

Một chương trình ghi `id`, sau đó ghi `amount`. Nếu crash giữa hai bước, file có thể phản ánh **trạng thái trung gian**. `force` không tự bảo đảm nhiều field cùng commit atomically, không thay cho:

- Versioning/commit marker.
- Checksum và kiểm tra torn writes.
- Write-ahead log hoặc shadow copy/double buffering.
- Transaction isolation khi nhiều writers hoạt động.
- Kiểm tra recovery sau mất điện hoặc process crash.

Phải phân biệt **durability/persistence** (“byte đã tới thiết bị theo hợp đồng”) với **crash consistency** (“định dạng dữ liệu còn hợp lệ sau khi dừng bất thường”). Dùng database/storage engine đã kiểm chứng nếu yêu cầu giao dịch phức tạp.

## 5. Phần mới từ Java 14: JEP 352 và ExtendedMapMode

### 5.1. Các chế độ NVM

JEP 352 bổ sung lớp `jdk.nio.mapmode.ExtendedMapMode` trong module `jdk.nio.mapmode`:

~~~java
import jdk.nio.mapmode.ExtendedMapMode;
~~~

| Mode | Mục đích |
|---|---|
| `ExtendedMapMode.READ_ONLY_SYNC` | Mapping **chỉ đọc** một file backing bởi non-volatile RAM |
| `ExtendedMapMode.READ_WRITE_SYNC` | Mapping **đọc/ghi** file backing bởi non-volatile RAM, dùng đường flush chuyên biệt khi thực hiện `force()` |

Hai hằng số có kiểu `FileChannel.MapMode` nên được truyền cho `FileChannel.map(...)` hiện hành, không cần đổi toàn bộ API truy xuất buffer.

Với `READ_WRITE_SYNC`, tài liệu JDK mô tả flush sử dụng **cache-line writeback** thay vì flush qua block device theo cách mapping thông thường. Đây là cơ chế tối ưu cho persistent memory trên nền tảng hỗ trợ, **không phải một cờ để tự động biến file trên SSD thành NVM**.

### 5.2. Điều kiện hệ thống

Muốn `READ_WRITE_SYNC` thật sự hoạt động, cần đồng thời xem xét:

1. Bản JDK có module `jdk.nio.mapmode` và implementation hỗ trợ mode đồng bộ.
2. OS/kernel hỗ trợ cơ chế memory mapping đồng bộ.
3. Filesystem và backing device hỗ trợ **DAX (Direct Access)** hoặc mô hình tương đương.
4. File thực sự nằm trên filesystem/thiết bị đó, có quyền phù hợp và đủ kích thước.
5. CPU/hardware có khả năng thực hiện flush đường cache line theo triển khai.

Ghi chú implementation của Oracle cho Linux nhắc hai flags `MAP_SYNC` và `MAP_SHARED_VALIDATE` của `mmap`.

**Không kết luận một máy có SSD/NVMe thì hỗ trợ NVM SYNC.** Có thể biên dịch được `ExtendedMapMode` nhưng mapping trên file bình thường vẫn thất bại.

Javadoc nêu `UnsupportedOperationException` khi implementation không hỗ trợ mode. Trên filesystem không phù hợp cũng có thể gặp `IOException` khi thử map. Code phải phát hiện lỗi thật và không tự báo “NVM enabled” nếu đã fallback.

### 5.3. Ví dụ NVM dành riêng cho hệ thống có DAX

Tạo tệp **`NvmModeProbe.java`**:

~~~java
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public final class NvmModeProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Supply an existing DAX-backed file");
        }

        Path file = Path.of(args[0]);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            MappedByteBuffer mapped =
                    channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 16);

            mapped.putInt(0, 42);
            mapped.force(0, Integer.BYTES);

            System.out.println("syncMappingCommitted=true");
        }
    }
}
~~~

**Điều kiện chạy:** File **đã tồn tại**, dài ít nhất 16 byte và được hệ thống xác nhận nằm trên một filesystem NVM/DAX tương thích. Chương trình **sửa bốn byte đầu file**, vì vậy chỉ chạy với dữ liệu thử nghiệm bạn có quyền ghi.

Biên dịch:

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode \
  -encoding UTF-8 NvmModeProbe.java
~~~

Chạy trên host hỗ trợ:

~~~bash
java --add-modules jdk.nio.mapmode \
  NvmModeProbe /path/to/validated-dax-file
~~~

**Ranh giới kiểm chứng:** Cú pháp Java ở trên đã được **biên dịch thành công** với `javac --release 17 --add-modules jdk.nio.mapmode`. Không chạy `READ_WRITE_SYNC` vì máy thử không có cấu hình DAX/NVM được xác nhận. `syncMappingCommitted=true` chỉ là **stdout dự kiến sau một lần map/force thành công trên thiết bị phù hợp**, không phải kết quả đã đo trên thiết bị NVM.

`READ_ONLY_SYNC` dùng cho file NVM chỉ đọc và channel đọc tương ứng. Mã đã khai báo `requires jdk.nio.mapmode;` nếu đưa vào một ứng dụng JPMS có `module-info.java`; các classpath examples thường cần `--add-modules jdk.nio.mapmode` khi compile/run.

**Fallback có chủ đích:** Nếu mode đồng bộ bị từ chối, bạn có thể dừng app để bảo vệ một SLA yêu cầu NVM, hoặc chuyển sang `READ_WRITE` thông thường **chỉ khi** thiết kế cho phép, tài liệu đã phân biệt behavior, có test và telemetry chỉ rõ chế độ thực tế. Không được âm thầm đổi mode rồi vẫn tuyên bố kết quả là NVM SYNC.

## 6. Chương trình Java 17+ hoàn chỉnh: memory-mapped file bình thường

Ví dụ thực hành dưới đây **không cần persistent-memory hardware**; nó minh họa mapping file tiêu chuẩn trên filesystem thông thường. Chương trình tạo một record 16 byte, flush, mở lại file để đọc, thử `READ_ONLY` và `PRIVATE`.

Định dạng record:

| Offset | Độ dài | Giá trị |
|---|---:|---|
| 0 | 4 byte | Magic number `0x4D415031` |
| 4 | 4 byte | Record ID `7` |
| 8 | 8 byte | Amount `123456789` |
| **Tổng** | **16 byte** | Số viết theo little-endian |

### 6.1. Mã tệp MappedFileNvmIntro.java

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.nio.file.StandardOpenOption.*;

public final class MappedFileNvmIntro {
    private static final int SIZE = 16;

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Supply a fresh data file path");
        }

        Path file = Path.of(args[0]);

        try (FileChannel ch = FileChannel.open(
                file, CREATE_NEW, READ, WRITE)) {

            // Tạo backing file dài 16 byte trước khi map.
            ch.write(ByteBuffer.wrap(new byte[]{0}), SIZE - 1L);

            MappedByteBuffer data =
                    ch.map(FileChannel.MapMode.READ_WRITE, 0, SIZE);
            data.order(ByteOrder.LITTLE_ENDIAN);

            data.putInt(0, 0x4D415031);
            data.putInt(4, 7);
            data.putLong(8, 123456789L);

            data.force(0, SIZE);
            System.out.println("writtenRecord=7,123456789");
        }

        try (FileChannel ch = FileChannel.open(file, READ)) {
            MappedByteBuffer data =
                    ch.map(FileChannel.MapMode.READ_ONLY, 0, SIZE);
            data.order(ByteOrder.LITTLE_ENDIAN);

            System.out.println("reopenRecord="
                    + data.getInt(4) + "," + data.getLong(8));

            try {
                data.putInt(4, 99);
                System.out.println("readOnlyRejected=false");
            } catch (ReadOnlyBufferException ex) {
                System.out.println("readOnlyRejected=true");
            }
        }

        try (FileChannel ch =
                FileChannel.open(file, READ, WRITE)) {
            MappedByteBuffer copy =
                    ch.map(FileChannel.MapMode.PRIVATE, 0, SIZE);
            copy.order(ByteOrder.LITTLE_ENDIAN);
            copy.putInt(4, 99);
            System.out.println("privateValue=" + copy.getInt(4));
        }

        try (FileChannel ch = FileChannel.open(file, READ)) {
            MappedByteBuffer original =
                    ch.map(FileChannel.MapMode.READ_ONLY, 0, SIZE);
            original.order(ByteOrder.LITTLE_ENDIAN);
            System.out.println("fileValueAfterPrivate="
                    + original.getInt(4));
        }

        System.out.println("fileSize=" + Files.size(file));
    }
}
~~~

### 6.2. Lệnh chạy

Biên dịch bằng **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 MappedFileNvmIntro.java
java MappedFileNvmIntro mapped.bin
~~~

**Lưu ý:** Đường dẫn `mapped.bin` phải **chưa tồn tại** vì ví dụ dùng `CREATE_NEW`. Muốn thử lại, chọn tên file thử khác hoặc xóa file thử an toàn khi không còn mapping nào sử dụng nó; không xóa/ghi đè dữ liệu quan trọng.

**Stdout đã được kiểm chứng bằng biên dịch và chạy Java:**

~~~text
writtenRecord=7,123456789
reopenRecord=7,123456789
readOnlyRejected=true
privateValue=99
fileValueAfterPrivate=7
fileSize=16
~~~

### 6.3. Giải thích kết quả

- `writtenRecord`: ghi ID và amount bằng `READ_WRITE` mapping, gọi `force(0, SIZE)`.
- `reopenRecord`: mở channel mới và map `READ_ONLY`, đọc lại đúng giá trị. Điều này chỉ chứng minh **đọc lại thành công**, **không phải mô phỏng mất điện để xác nhận crash durability**.
- `readOnlyRejected=true`: `putInt` trên read-only buffer ném `ReadOnlyBufferException`.
- `privateValue=99`: `PRIVATE` cho phép thay đổi dữ liệu **trong private view**.
- `fileValueAfterPrivate=7`: backing file vẫn giữ ID `7` do private mapping không propagate thay đổi vào file.
- `fileSize=16`: file được tạo đủ 16 byte trước khi map.

**Vì sao mở rộng file trước?** Theo `FileChannel.map`, chi tiết của việc map vùng vượt quá EOF phụ thuộc OS. Ví dụ ghi một byte ở offset `SIZE - 1` để tạo file đúng size rồi mới map, tránh dựa vào hành vi không được bảo đảm ngoài phạm vi file.

**Vì sao dùng LITTLE_ENDIAN?** Một định dạng binary phải chọn endianness có chủ đích. Người đọc khác process/ngôn ngữ/JDK phải biết layout và byte order để giải mã đúng.

**Vì sao dùng putInt(offset,value)?** Truy cập tuyệt đối không tự sửa position của buffer; điều này giúp ví dụ thao tác trường ở fixed offsets dễ hiểu. Nó **không tự giải quyết data races** nếu nhiều threads đồng thời ghi.

## 7. Vòng đời mapping và việc unmap

Một số điểm quan trọng của API:

- `FileChannel.close()` đóng channel nhưng **không làm mapping vô hiệu ngay lập tức**.
- Vùng mapped tồn tại độc lập với channel sau khi tạo và gắn với vòng đời của buffer/mapping; với `MappedByteBuffer`, việc giải phóng mapping liên quan đến garbage collection.
- Không nên mặc định file có thể được xóa/đổi tên ngay sau khi đóng channel. Trên một số OS, đặc biệt Windows, file có thể vẫn còn tài nguyên mapping đang giữ.
- Tránh dùng internal cleaner/reflection vào private JDK APIs để cưỡng ép unmap như một thiết kế portable.

Ứng dụng nên dừng mọi tác vụ đang dùng buffer trước khi thay file, quản lý phạm vi giữ tham chiếu và kiểm thử lifecycle theo OS.

### 7.1. Không truncate file trong khi còn mapped readers

Theo `MappedByteBuffer` Javadoc, mapping có thể không còn truy cập được nếu backing file bị truncate hoặc thay đổi bởi process khác. Lỗi có thể biểu hiện ở thời điểm đọc/ghi và phụ thuộc OS.

Nếu nhiều process cùng truy cập một file, cần quy trình phối hợp: file lock khi phù hợp, versioning, tránh truncate khi còn readers, rename/swap theo quy tắc OS và kiểm tra recovery.

### 7.2. Mapping không tự có thread safety cho mọi thao tác

- `position`, `limit`, `mark` là trạng thái mutable của buffer.
- `duplicate()` tạo view có vị trí riêng nhưng vẫn dùng **cùng backing content**.
- Nhiều thread/process sửa một vùng cần đồng bộ phù hợp.
- Mapping không tự cung cấp semantic của `volatile`, atomic multi-field commit hoặc transaction isolation.

Với NVM, dữ liệu **tồn tại sau restart** nhưng có thể chứa một record dở dang nếu mất điện giữa các thao tác. Độ bền và tính nhất quán vẫn phải được thiết kế riêng.

## 8. Giới hạn size, load/isLoaded và các lựa chọn API hiện hành

### 8.1. Một MappedByteBuffer bị giới hạn bởi int

`FileChannel.map(MapMode,long,long)` trả về buffer có capacity kiểu `int`; size của một vùng mapped buffer theo overload này không thể vượt `Integer.MAX_VALUE` byte.

File lớn hơn vẫn có thể được xử lý bằng **nhiều mapping windows**, mỗi cửa sổ có offset và size phù hợp. Đừng chia file vài chục GB thành một buffer duy nhất.

Trên **JDK 22+**, API `FileChannel.map(..., Arena)` với mapped `MemorySegment` là một lựa chọn hiện hành khác cho trường hợp cần vòng đời gắn với `Arena`, vùng lớn và thao tác có scope. Đây là API riêng có yêu cầu JDK mới hơn; không dùng nó như mã Java 17 trong ví dụ chính.

### 8.2. load/isLoaded không phải flush

- `MappedByteBuffer.load()` cố gắng đưa pages của mapping vào physical memory, **best effort**.
- `isLoaded()` trả về **hint** về các pages có khả năng resident, không phải một bảo đảm.
- `force()` là cơ chế flush các thay đổi của mapped buffer.

Do đó, `isLoaded()==true` **không chứng minh** các byte đã persist, không cho biết backing là DAX và không bảo đảm crash recovery.

### 8.3. Khi nào mapping không phải giải pháp phù hợp?

Không ép dùng mapping nếu:

- File nhỏ hoặc chỉ đọc một lần, stream/channel đơn giản dễ bảo trì hơn.
- File liên tục rotate/truncate và không thể quản lý lifetime.
- Hệ thống đòi transaction, rollback, locking và recovery phức tạp; một database/storage engine phù hợp hơn.
- Không thể kiểm soát OS/filesystem/hardware nhưng yêu cầu `READ_WRITE_SYNC` ở mọi môi trường.
- Không có kiểm thử và đo đạc để chứng minh mapping cải thiện throughput/latency.

Khi benchmark, đo **page faults, cache behavior, file size, thời gian `force`, chi phí mapping/unmapping, workload ngẫu nhiên/tuần tự** và tác động nhiều process đồng thời.

## 9. Các lỗi thường gặp và cách sửa

| Hiện tượng hoặc nhầm lẫn | Vì sao xảy ra | Hướng xử lý |
|---|---|---|
| Tưởng SSD NVMe là NVM SYNC | NVMe SSD là storage theo block, không mặc định DAX | Kiểm tra backing file/FS/hardware và `ExtendedMapMode` |
| `NonReadableChannelException` | Mode cần READ nhưng channel không có quyền | Mở channel với `READ` |
| `NonWritableChannelException` | `READ_WRITE`/`PRIVATE` cần quyền WRITE | Mở cả `READ` và `WRITE` |
| `ReadOnlyBufferException` | Ghi vào `READ_ONLY` buffer | Chọn writable mapping nếu hợp đồng và quyền cho phép |
| `IllegalArgumentException` khi map | Offset/size âm, size vượt giới hạn hoặc args sai | Validate bounds trước khi gọi |
| Map vượt EOF | Tùy OS, có thể lỗi hoặc hành vi không mong muốn | Chủ động tạo file đủ kích thước |
| `UnsupportedOperationException` khi SYNC | Runtime/OS không hỗ trợ extended map mode | Xác minh platform; fallback tường minh hoặc fail |
| `IOException` khi SYNC trên file thường | Backing FS không hỗ trợ MAP_SYNC/DAX hoặc lỗi I/O | Kiểm tra filesystem, quyền và cấu hình thực |
| `BufferOverflowException` / `IndexOutOfBoundsException` | Đọc/ghi vượt capacity/limit | Tính layout và offsets chính xác |
| `PRIVATE` put thành công nhưng file không đổi | Copy-on-write không cập nhật backing file | Dùng `READ_WRITE` nếu muốn persist |
| Đóng channel nhưng file vẫn bị khóa | Mapping còn sống | Quản lý lifetime; đừng giả định channel close unmap |
| Truncate file trong khi process khác đang map | Mapping có thể mất khả năng truy cập | Đồng bộ lifecycle và tránh thao tác rủi ro |
| Dùng `channel.force(true)` thay cho `buffer.force()` | Channel force không bảo đảm flush mọi mapped changes | Dùng force của mapped buffer |
| Đọc được dữ liệu sau reopen nên khẳng định crash safe | Reopen không kiểm thử mất điện; record có thể thiếu transaction | Test crash consistency, checksums/version |
| `isLoaded()` được coi là persist | Chỉ là hint về pages resident | Dùng force và đánh giá contract storage |
| Tưởng nhiều writers tự đồng bộ vì cùng map file | Cùng backing content không tự có atomicity/isolation | Định nghĩa locking/commit protocol |
| Silent fallback từ SYNC sang READ_WRITE | Thay đổi storage path mà báo sai trạng thái | Ghi nhận mode và chỉ fallback có chủ đích |

## 10. Quy trình đưa mapping/NVM vào ứng dụng

1. **Đặt mục tiêu:** cần hiệu năng random file access, hay cần NVM byte-addressable thật?
2. **Kiểm tra file backing:** loại storage, filesystem, DAX, quyền, kích thước và cấu hình của host.
3. **Chọn JDK:** Java 17+ cho ví dụ chuẩn; nếu dùng `ExtendedMapMode` phải có `jdk.nio.mapmode` và runtime phù hợp.
4. **Thiết kế layout:** offsets, byte order, magic/version, alignment, checksum và expected endianness.
5. **Chọn mode:** `READ_ONLY`, `READ_WRITE`, `PRIVATE` cho file thường; SYNC modes chỉ trên NVM hỗ trợ.
6. **Kiểm thử errors:** thiếu quyền, file chưa đủ size, mode không hỗ trợ, IOException, truncate và concurrent access.
7. **Xác định flush policy:** lúc nào `force`, commit marker và cách phục hồi nếu crash giữa nhiều thao tác.
8. **Đồng bộ:** phối hợp read/write từ threads hoặc processes, tránh race với file lifecycle.
9. **Benchmark:** không giả định mapping luôn nhanh hơn stream/channel I/O.
10. **Bảo vệ dữ liệu:** không bỏ quên quyền file, backup, encryption và secrets trong vùng memory-mapped.
11. **Giải phóng tài nguyên đúng:** đóng channel, ngừng dùng mapped buffers, không truncate/xóa khi còn active.
12. **Quan sát lỗi thực tế:** log loại mode đang dùng, lỗi map/force, thời gian flush và kết quả recovery.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `FileChannel.map(READ_WRITE, ...)` trên SSD thông thường có nghĩa ứng dụng đang dùng NVM SYNC từ Java 14?

**Đáp án:** Không. Đó là memory-mapped file thông thường. NVM SYNC dùng extended modes và chỉ hoạt động khi có backing DAX/non-volatile RAM phù hợp.

**Câu 2.** `READ_WRITE_SYNC` khác `READ_WRITE` ở đâu?

**Đáp án:** Đây là mode mở rộng trong `jdk.nio.mapmode` cho vùng file backed by NVM; `force` có đường cache-line writeback khi được triển khai hỗ trợ, chứ không phải một tối ưu luôn sẵn có trên mọi filesystem.

**Câu 3.** `force()` đã trả về có nghĩa một record nhiều trường được commit nguyên tử?

**Đáp án:** Không. Flush và transaction atomicity khác nhau; vẫn cần thiết kế version/checksum/commit protocol khi yêu cầu crash consistency.

**Câu 4.** Đóng `FileChannel` có tự unmap buffer ngay không?

**Đáp án:** Không. Vùng mapping không phụ thuộc vào channel sau khi tạo, và `MappedByteBuffer` tồn tại gắn với vòng đời buffer/GC.

**Câu 5.** `MapMode.PRIVATE` có phù hợp để ghi thay đổi vào file gốc không?

**Đáp án:** Không. Các sửa đổi thuộc private copy-on-write mapping, không propagate về backing file.

**Câu 6.** `MappedByteBuffer.isLoaded()` trả `true` có nghĩa dữ liệu đã được flush vào NVM?

**Đáp án:** Không. Kết quả chỉ là hint về pages được load, không phải persistence guarantee.

**Câu 7.** Vì sao ví dụ ghi một byte ở `SIZE-1` trước khi map một file mới?

**Đáp án:** Để file có đủ 16 byte trước khi ánh xạ, tránh phụ thuộc hành vi khi map vùng vượt EOF mà tài liệu để ngỏ theo OS.

**Câu 8.** Khi SYNC mode không được hỗ trợ, có nên âm thầm đổi sang `READ_WRITE` và giữ nhãn “NVM enabled”?

**Đáp án:** Không. Chỉ fallback khi được cho phép về storage contract, có test và telemetry thể hiện đúng mode thực tế. Nếu yêu cầu NVM, báo lỗi và dừng hợp lý.

**Câu 9.** Muốn xử lý một file 20 GB, có thể tạo một `MappedByteBuffer` duy nhất qua `map(MapMode,long,long)`?

**Đáp án:** Không. Giới hạn kích thước một buffer theo `int`; map nhiều windows hoặc dùng API mapped `MemorySegment` ở JDK mới phù hợp.

## Tài liệu chính thức

- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): động cơ và thiết kế NVM mapping từ Java 14.
- [JDK 25 — `ExtendedMapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_ONLY_SYNC`, `READ_WRITE_SYNC`, giới hạn support và `MAP_SYNC`.
- [JDK 25 — `FileChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): `map`, `force(boolean)`, các MapMode và lifecycle.
- [JDK 25 — `MappedByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `force(index,length)`, `load`, `isLoaded` và truncation hazards.
- [JDK 17 — `MappedByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): API baseline của ví dụ đã chạy.
- [JDK 25 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): truy cập theo byte offset, primitive encoding, byte order.
- [JDK 25 — `FileChannel.map(...,Arena)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): mapped MemorySegment trên JDK mới.
- [Linux Kernel — Direct Access for Files](https://docs.kernel.org/filesystems/dax.html): điều kiện và trạng thái DAX trên Linux.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): cơ sở của API `MemorySegment`/`Arena` từ Java 22.

**Ghi nhớ:** **Mapped file thường** và **NVM SYNC mapped file** đều có thể truy cập qua `MappedByteBuffer`, nhưng chúng khác storage backing, mapping mode và cơ chế flush. `force` không tự tạo transaction; đóng channel không unmap tức thời; thay đổi trên `PRIVATE` không ghi vào file; và `READ_WRITE_SYNC` chỉ áp dụng trên hệ thống có hạ tầng persistent memory hỗ trợ. Hãy kiểm chứng mode, backing file và storage contract trước khi đưa vào sản phẩm.