# Quản lý vòng đời kênh, vùng ánh xạ và giới hạn tài nguyên khi ánh xạ NVM trong Java

## 1. Vì sao phải quản lý vòng đời của vùng ánh xạ?

**Memory-mapped file** cho phép Java truy cập một vùng tệp như một vùng nhớ thay vì thực hiện từng lần đọc/ghi qua `FileChannel.read/write`. Đây là cơ chế nền tảng của Java NIO và cũng được dùng trong bài toán **NVM (non-volatile memory)** khi hệ điều hành, hệ thống tệp và thiết bị hỗ trợ ánh xạ phù hợp.

Khi dùng ánh xạ bộ nhớ, lập trình viên cần phân biệt ít nhất ba tài nguyên:

1. **Kênh tệp (`FileChannel`):** đại diện cho một kênh I/O; có thể đóng bằng `close()` và nên đặt trong `try-with-resources`.
2. **Vùng ánh xạ (mapped region):** một vùng địa chỉ bộ nhớ ảo liên kết với vùng của file. Nó có thể tiếp tục tồn tại **sau khi kênh được đóng**.
3. **Dữ liệu lưu trữ và vòng đời bền vững:** những thay đổi trên mapping có thể cần `force()`; đóng channel hoặc giải phóng mapping không phải thay thế tự động cho quy trình đảm bảo dữ liệu đã được ghi xuống thiết bị.

Từ Java 22, có thêm cách quản lý rõ ràng thông qua **`MemorySegment` và `Arena`**, cho phép tạo mapped segment với vòng đời gắn với một arena có thể đóng. Đây là hướng hiện đại cho ứng dụng mới cần kiểm soát unmap chính xác; `MappedByteBuffer` vẫn là API chuẩn, được hỗ trợ và rất phù hợp khi phải chạy trên Java 17/21.

**Kết luận cần nhớ:** `channel.close()` **không tương đương** với “mapping đã được unmap”; `mapped.force()` **không tương đương** với “mapping đã được giải phóng”; `arena.close()` **không nên được xem là lời gọi flush dữ liệu thay cho `force()`**.

## 2. Bối cảnh NVM của Java 14 và những API còn phù hợp hiện nay

### 2.1. MappedByteBuffer: cơ chế ánh xạ chuẩn

Java có thể tạo một vùng ánh xạ bằng:

~~~java
MappedByteBuffer buffer = channel.map(
        FileChannel.MapMode.READ_WRITE, offset, length);
~~~

Overload `FileChannel.map(MapMode, long, long)` trả về `MappedByteBuffer`, thuộc API `java.nio` có từ lâu và **vẫn được hỗ trợ trong Java 17, 21, 25/26**.

Các chế độ cơ bản:

| Chế độ | Quyền truy cập | Tác động lên file |
| --- | --- | --- |
| `READ_ONLY` | Chỉ đọc | Không cho ghi qua vùng ánh xạ |
| `READ_WRITE` | Đọc/ghi | Các thay đổi có thể lan tới file; dùng `force()` khi cần flush |
| `PRIVATE` | Copy-on-write | Các thay đổi riêng không được lan ngược về file |

Muốn ánh xạ kiểu `READ_WRITE` hoặc `PRIVATE`, kênh thường cần được mở với **cả quyền đọc lẫn ghi**. Muốn `READ_ONLY`, kênh cần quyền đọc.

### 2.2. Tính năng NVM mở rộng từ Java 14

JEP 352 (*Non-Volatile Mapped Byte Buffers*) giới thiệu module `jdk.nio.mapmode` với `ExtendedMapMode`:

~~~java
import jdk.nio.mapmode.ExtendedMapMode;

MappedByteBuffer mapped = channel.map(
        ExtendedMapMode.READ_WRITE_SYNC, offset, length);
~~~

Đây là **mảnh code cho môi trường NVM có hỗ trợ**, không phải ví dụ chạy được trên mọi máy. Các map modes mở rộng:

- `READ_ONLY_SYNC`: ánh xạ chỉ đọc dành cho file trên non-volatile RAM.
- `READ_WRITE_SYNC`: ánh xạ đọc/ghi dành cho NVM; `force()` có thể dùng cơ chế cache-line writeback theo triển khai và nền tảng.

Theo tài liệu Oracle cho JDK hiện đại, các mode này là **JDK-specific**, được định nghĩa trong module `jdk.nio.mapmode`. Trên Linux, cơ chế có thể dùng `MAP_SYNC` và `MAP_SHARED_VALIDATE`. Nó **đòi hỏi filesystem/mount/thiết bị/NVM support phù hợp**; truyền `READ_WRITE_SYNC` vào file tạm trên SSD thông thường hoặc Windows rồi mong luôn thành công là không đúng.

Khi mode không được hỗ trợ, `FileChannel.map` có thể ném `UnsupportedOperationException`. Không mặc định âm thầm đổi từ `READ_WRITE_SYNC` sang `READ_WRITE` trong phần dữ liệu cần bảo đảm đúng cơ chế bền vững của NVM; cần chính sách fallback được đánh giá rõ.

**Ví dụ chạy độc lập trong bài sử dụng `READ_WRITE` chuẩn** để không yêu cầu thiết bị NVM. Mục tiêu là học **vòng đời và giới hạn tài nguyên**; trên hệ thống NVM thật, cùng các nguyên tắc sở hữu/lifetime vẫn cần được áp dụng.

### 2.3. API MemorySegment hiện đại từ Java 22

Từ **Java 22 (JEP 454)**, Foreign Function & Memory API trở thành tính năng chính thức. `FileChannel` có overload:

~~~java
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        offset, length, arena);
~~~

Trong đó `arena` là `java.lang.foreign.Arena`. **Lifetime của mapped segment được kiểm soát bởi arena**: đóng một closeable arena thành công sẽ làm segment không còn truy cập hợp lệ và unmap vùng bộ nhớ.

Hai hướng API hiện được hỗ trợ:

| API | JDK phù hợp | Vòng đời |
| --- | --- | --- |
| `FileChannel.map(mode, offset, size)` → `MappedByteBuffer` | Java 17+ và các bản hiện đại | Mapping còn hợp lệ cho tới khi buffer được GC; không có `close()` công khai trên buffer |
| `FileChannel.map(mode, offset, size, arena)` → `MemorySegment` | **Java 22+** | Mapping bị unmap khi closeable arena được đóng |
| `ExtendedMapMode.READ_WRITE_SYNC` | JDK có module `jdk.nio.mapmode` và platform hỗ trợ | Chế độ NVM cụ thể; **không tự giải quyết vòng đời** |

Không sao chép code `java.lang.foreign.Arena` sang bản build target Java 17/21 rồi kỳ vọng biên dịch được: API chính thức của overload dùng arena có **`Since: 22`**. Không cần dùng API incubator/preview cũ cho ứng dụng mới chạy Java 22+.

## 3. Sơ đồ vòng đời chính xác

~~~text
Mở FileChannel
    |
    +-- map(mode, offset, length) --> MappedByteBuffer
    |       |
    |       +-- Đọc/ghi qua mapped bytes
    |       +-- force() nếu cần flush dữ liệu
    |       |
    |       +-- Đóng FileChannel KHÔNG hủy mapping
    |       +-- Mapping tồn tại tới khi buffer được GC
    |           (không được lập lịch theo ý muốn)
    |
    +-- map(mode, offset, length, arena) --> MemorySegment
            |
            +-- Đọc/ghi khi arena còn sống
            +-- force() nếu cần flush dữ liệu
            +-- Đóng FileChannel KHÔNG hủy mapping
            |
            +-- Đóng closeable Arena -> unmap segment
            +-- Truy cập segment sau đó -> IllegalStateException
~~~

Đây là sơ đồ **quan hệ tài nguyên**, không có nghĩa JVM luôn thực hiện flush đúng thứ tự vật lý như các mũi tên. Việc ghi dữ liệu bền vững còn phụ thuộc chế độ map, filesystem, thiết bị và lời gọi `force`.

### Lớp FileChannel

`FileChannel` triển khai `AutoCloseable`, nên:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    // Tạo và sử dụng mapping.
}
~~~

Đây là **mảnh code**, cần khai báo `Path path`/imports. Khi thoát block, channel được đóng kể cả khi có exception. Việc này giải phóng resource của **kênh** nhưng **không hủy vùng memory mapping đã tạo**.

### Lớp vùng ánh xạ

Theo `FileChannel.map`, **một mapping đã tạo không phụ thuộc vào FileChannel dùng để tạo nó**. Vì thế không nên coi biến `MappedByteBuffer` là invalid chỉ vì channel đã close; nhưng cũng không được quên mapping đang giữ tài nguyên OS.

### Lớp dữ liệu bền vững

Với `READ_WRITE`, viết bytes vào mapping rồi gọi `mapped.force()` (hoặc `MemorySegment.force()`) khi cần đẩy thay đổi ra thiết bị. Đừng tự thay bằng `channel.force(true)` rồi cho rằng mọi sửa đổi qua mapping đều được bảo đảm: Javadoc `FileChannel.force` chỉ cam kết cho các thay đổi qua những API kênh tương ứng, **có thể không cam kết cho sửa đổi qua mapped buffer**.

## 4. Java 17+: MappedByteBuffer sau khi đóng channel

Đây là chương trình **chạy độc lập**, đã được biên dịch/chạy bằng JDK 24 với `--release 17`, thể hiện sự tách biệt của channel và vùng ánh xạ.

Tạo file **`MappedBufferLifecycleDemo.java`**:

~~~java
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import static java.nio.file.StandardOpenOption.READ;
import static java.nio.file.StandardOpenOption.WRITE;

public class MappedBufferLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("mapping-17-", ".bin");
        path.toFile().deleteOnExit(); // Chỉ dọn khi JVM thoát, best effort.
        Files.write(path, new byte[8]);

        MappedByteBuffer mapped;
        FileChannel channel = FileChannel.open(path, READ, WRITE);
        try (channel) {
            mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 8);
            mapped.order(ByteOrder.BIG_ENDIAN);
            mapped.putInt(0, 0x01020304);
            mapped.force();

            System.out.println(
                    "channel-inside=" + channel.isOpen());
        }

        System.out.println(
                "channel-after-close=" + channel.isOpen());
        System.out.println(
                "mapping-after-close="
                    + String.format("%08x", mapped.getInt(0)));

        byte[] bytes = Files.readAllBytes(path);
        System.out.println("file-prefix="
                + String.format("%02x%02x%02x%02x",
                        bytes[0], bytes[1], bytes[2], bytes[3]));
        System.out.println(
                "mapping-capacity=" + mapped.capacity());
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 MappedBufferLifecycleDemo.java
java MappedBufferLifecycleDemo
~~~

**Đầu ra đã kiểm chứng trên OpenJDK 24:**

~~~text
channel-inside=true
channel-after-close=false
mapping-after-close=01020304
file-prefix=01020304
mapping-capacity=8
~~~

**Giải thích:**

1. `Files.write(path, new byte[8])` tạo file thử gồm 8 byte 0, tránh truy cập một vùng không có backing data hoặc tùy thuộc hành vi mở rộng file của từng OS.
2. `FileChannel.open(path, READ, WRITE)` có đủ quyền cho `MapMode.READ_WRITE`.
3. `map(...,0,8)` trả về buffer có capacity 8. `putInt(0, 0x01020304)` ghi 4 byte theo `BIG_ENDIAN`.
4. `mapped.force()` yêu cầu flush thay đổi của mapping về file. Sau đó `channel.close()` tự động qua try-with-resources.
5. `channel.isOpen()` bằng false sau block, nhưng **`mapped.getInt(0)` vẫn dùng được** và cho `0x01020304`. Đây chính là bằng chứng channel và mapping có lifetime tách nhau.
6. Đọc lại bốn byte đầu của tệp cho `01 02 03 04`; capacity vẫn là 8.
7. `deleteOnExit()` dùng trong lab vì Java 17 không có API `MappedByteBuffer.close()` công khai để unmap đúng thời điểm. Việc xóa file khi mapping vẫn còn sống **khác nhau giữa OS**, nhất là Windows; không dùng mẫu này để khẳng định tệp tạm luôn được xóa ngay.

**Lưu ý bảo toàn tài nguyên:** ví dụ Java 17 trên minh họa cơ chế, **không cung cấp cách unmap xác định thời điểm**. Nếu cần tạo hàng nghìn mapping ngắn hạn rồi xóa file ngay trong một process, `MappedByteBuffer` không phải lựa chọn thuận tiện nhất. Từ Java 22+, dùng arena-scoped memory mapping sẽ dễ quản lý lifetime hơn.

## 5. Vì sao MappedByteBuffer không có close()?

`MappedByteBuffer` là một dạng `ByteBuffer` direct, không triển khai `AutoCloseable`. Mapping của nó tiếp tục hợp lệ đến khi buffer được garbage collected. Nghĩa là:

- **Không thể dựa vào `try (MappedByteBuffer mapped = ...)`**: không có contract close phù hợp.
- **Không nên gọi `System.gc()` để “unmap ngay”**. GC có thể không chạy, có thể bị vô hiệu hóa và không cung cấp thời điểm xác định để release OS mapping.
- **Không nên dùng reflection, `sun.misc.Unsafe.invokeCleaner` hay API nội bộ để ép unmap** trong code mới. Những kỹ thuật này không phải hợp đồng Java SE, có nguy cơ tương thích, phân quyền và truy cập bộ nhớ sai.
- **Không giữ mapping trong cache vô hạn** nếu không có ngân sách tài nguyên. Việc giữ một `MappedByteBuffer` còn tham chiếu có thể kéo dài sự tồn tại của vùng memory-mapped.
- Các **slice/duplicate/view** chia sẻ dữ liệu backing và có thể khiến vùng mapping tiếp tục cần được giữ. Không được dùng chúng sau khi một cơ chế unmap ngoài hợp đồng đã ép giải phóng vùng bộ nhớ.
- **Không coi đối tượng buffer là file descriptor**. Đóng FileChannel giải phóng channel; vùng mapping là resource khác, có thể giữ file backing và vùng địa chỉ ảo.

Nếu cần kiểm soát chính xác thời điểm file được unmap, hãy chọn `MemorySegment + Arena` khi dùng Java 22+, hoặc đổi thiết kế đọc/ghi khi ứng dụng phải chạy trên Java 17/21.

## 6. Java 22+: quản lý vùng ánh xạ bằng Arena

Từ Java 22, dùng overload `FileChannel.map(MapMode, offset, size, Arena)`. Arena có thể được đóng rõ ràng, giúp **unmap mapping khi ra khỏi scope**.

Các dạng arena phổ biến:

| Arena | Có đóng chủ động được? | Thread access | Khi nên dùng |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Có | Chỉ owner thread | Xử lý một mapping trong một luồng |
| `Arena.ofShared()` | Có | Nhiều threads | Nhiều worker cần truy cập cùng vùng, có shutdown coordination |
| `Arena.ofAuto()` | Không đóng chủ động | Nhiều threads | Lifetime do GC quản lý; không phù hợp nếu cần unmap đúng thời điểm |
| `Arena.global()` | Không đóng | Nhiều threads | Vòng đời gắn với JVM, thường không phù hợp với mapping tạm |

**Ưu tiên `try (Arena arena = Arena.ofConfined())`** khi một thread sở hữu vòng đời mapping. Khi thoát try, arena đóng; truy cập segment sau đó không còn hợp lệ.

Nếu dùng `Arena.ofShared()`, phải ngừng hoặc đồng bộ các worker trước khi close. Một số truy cập đang hoạt động có thể khiến việc đóng arena cần đợi hoặc thất bại theo quy tắc concurrency. Không đóng từ một thread bất kỳ giữa lúc thread khác đang đọc/ghi.

## 7. Chương trình Java 22+ hoàn chỉnh: close channel, close arena, rồi xóa file

Mã sau đã được **biên dịch với `javac --release 22` và chạy trên OpenJDK 24**, không cần preview flag. Nó chứng minh:

- Mapping vẫn dùng được sau khi channel đã đóng, nếu arena còn sống.
- `segment.force()` flush thay đổi từ mapping.
- Sau khi arena đóng, segment không còn truy cập được và một lần thử `get` ném `IllegalStateException`.
- Sau khi arena đóng, file tạm có thể được dọn bằng `Files.deleteIfExists` trong môi trường đã kiểm thử.

Tạo file **`ArenaMappingLifecycleDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import static java.nio.file.StandardOpenOption.READ;
import static java.nio.file.StandardOpenOption.WRITE;

public class ArenaMappingLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("mapping-22-", ".bin");
        try {
            Files.write(path, new byte[8]);
            ValueLayout.OfInt layout =
                ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN);

            MemorySegment segment;
            try (Arena arena = Arena.ofConfined()) {
                try (FileChannel channel =
                        FileChannel.open(path, READ, WRITE)) {
                    segment = channel.map(
                        FileChannel.MapMode.READ_WRITE, 0, 8, arena);
                }

                // FileChannel đã đóng nhưng arena vẫn còn sống.
                segment.set(layout, 0, 0x01020304);
                segment.force();
                System.out.println("segment-inside="
                    + String.format("%08x", segment.get(layout, 0)));
            }

            boolean inaccessible = false;
            try {
                segment.get(layout, 0);
            } catch (IllegalStateException expected) {
                inaccessible = true;
            }

            System.out.println(
                "segment-after-arena-close-inaccessible=" + inaccessible);

            byte[] bytes = Files.readAllBytes(path);
            System.out.println("file-prefix="
                + String.format("%02x%02x%02x%02x",
                    bytes[0], bytes[1], bytes[2], bytes[3]));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 22 -encoding UTF-8 ArenaMappingLifecycleDemo.java
java ArenaMappingLifecycleDemo
~~~

**Đầu ra đã kiểm chứng trên OpenJDK 24:**

~~~text
segment-inside=01020304
segment-after-arena-close-inaccessible=true
file-prefix=01020304
~~~

**Các điểm quan trọng:**

- `FileChannel.map(..., arena)` là API có từ Java 22. Chạy file class target 22 trên JVM Java 17 sẽ không tương thích.
- `FileChannel` được đóng ở cuối try bên trong. `segment.set(...)` diễn ra **sau khi channel đã đóng** nhưng **trước khi arena đóng**, nên mapping vẫn hoạt động.
- `ValueLayout.JAVA_INT_UNALIGNED.withOrder(BIG_ENDIAN)` đảm bảo cùng cách mã hóa bốn byte bất kể native endianness của máy.
- `segment.force()` được gọi **khi segment còn hợp lệ**. Không gọi `force()` sau khi arena đóng.
- `Arena.ofConfined()` giữ lifetime trong thread hiện tại; sau `arena.close()`, truy cập segment bị chặn bằng `IllegalStateException`.
- Khác cách dùng buffer dựa vào GC, arena cho phép giải phóng mapping ở **thời điểm xác định**, rất hữu ích khi tạo/xóa tệp tạm hoặc lặp lại nhiều mappings.
- `Files.deleteIfExists` là cleanup thật. Nó vẫn có thể thất bại bởi quyền, antivirus, tiến trình khác giữ tệp hoặc lý do filesystem; ví dụ này không khẳng định mọi OS đều xóa thành công trong mọi tình huống.
- Ví dụ kiểm chứng **lifecycle**, không phải thử nghiệm trên NVM/DAX. Nếu chạy trên non-volatile memory, người vận hành vẫn phải chọn map mode phù hợp và kiểm thử đường ghi bền vững.

## 8. force(), close() và tính bền vững không hoán đổi được

Đây là ba hành động độc lập:

| Hành động | Tác dụng chính | Không nên suy ra |
| --- | --- | --- |
| `MappedByteBuffer.force()` | Yêu cầu ghi các thay đổi của mapped buffer ra storage | Không unmap mapping; không đóng FileChannel |
| `MappedByteBuffer.force(index,length)` | Force một đoạn trong buffer | Không có nghĩa phần còn lại được flush; có thể ghi cả khối rộng hơn vì granularity OS |
| `MemorySegment.force()` | Force các thay đổi của mapped segment | Không thay cho đóng Arena |
| `FileChannel.force(metaData)` | Force các thay đổi qua channel API, tùy flag metadata | Không được đảm bảo flush mọi sửa đổi qua mapping |
| `FileChannel.close()` | Đóng channel | Không tự unmap buffer/segment |
| `Arena.close()` (closeable arena) | Vô hiệu scope, unmap mapping gắn với arena | Không coi là bước flush thay cho explicit force |
| `Files.deleteIfExists(path)` | Yêu cầu xóa file | Có thể thất bại nếu file còn được ánh xạ hoặc bị giữ bởi OS/process khác |

Tài liệu `MappedByteBuffer.force` bảo đảm đối với **file nằm trên thiết bị lưu trữ local** rằng các thay đổi của vùng buffer được force theo phạm vi mô tả; trên **non-local device** không có cùng bảo đảm đó. `force` có thể gây I/O và ném lỗi; ứng dụng cần xử lý.

**Không coi `force()` là một transaction đa trường**: nếu ghi nhiều cấu trúc dữ liệu rồi bị mất điện giữa các bước, file có thể chứa trạng thái chỉ được cập nhật một phần. Với hệ thống NVM quan trọng, hãy thiết kế record format, checksum, version/sequence, commit marker hoặc journal phù hợp, kiểm tra thứ tự ghi và cơ chế khôi phục.

### Quy tắc chính xác cho force

- Với mapping **`READ_WRITE`**, `mapped.force()` hoặc `segment.force()` là API phù hợp cho **nội dung thay đổi qua mapping**.
- Với `READ_ONLY` và `PRIVATE`, force thường không có tác dụng ghi lại thay đổi về file gốc.
- Với `ExtendedMapMode.READ_WRITE_SYNC` trên NVM được hỗ trợ, force có thể dùng cache-line writeback thay vì flush qua thiết bị file truyền thống, theo tài liệu `jdk.nio.mapmode`; **không** suy ra mọi hệ thống file trên SSD có cùng đảm bảo.
- Khi thay đổi **kích thước hoặc metadata** qua kênh, xem thêm `FileChannel.force(true/false)` và hợp đồng durability của hệ thống file. Nó không thay thế lực flush cho các thay đổi mapped bytes.
- Không bỏ qua `UncheckedIOException` từ `MappedByteBuffer.force()` khi hệ thống báo lỗi I/O.

## 9. Vùng địa chỉ ảo, bộ nhớ ngoài heap và tài nguyên OS

Một file mapping không đơn giản là mảng `byte[]` trên heap Java.

**Những tài nguyên có thể bị chiếm dụng:**

1. **Virtual address space** dành cho vùng ánh xạ.
2. **Page tables và VM mapping metadata** của OS; số lượng mappings lớn có thể tạo overhead quản lý.
3. **Page cache / physical pages** khi các trang được truy cập hoặc `load()`.
4. **Disk I/O / storage bandwidth** khi xảy ra page faults hoặc khi force/dump.
5. **File-backed object/OS handles** theo cách hệ điều hành triển khai, kể cả sau khi FileChannel đã đóng.
6. **Giới hạn kernel/process** như số lượng mappings, hạn mức memory address space, giới hạn file descriptors cho các channel đang mở.
7. **Thời gian của GC hoặc Arena cleanup** tùy chiến lược lifecycle.

Đừng chỉ theo dõi **`Runtime.maxMemory()` hoặc `-Xmx`** rồi kết luận còn đủ không gian cho tất cả mappings. Nhiều mapping dùng **off-heap/virtual memory**, ảnh hưởng tới process RSS, page cache và giới hạn OS/container theo cách khác với Java heap.

### `load()` và `isLoaded()` không bảo đảm pin toàn bộ dữ liệu

`MappedByteBuffer.load()` yêu cầu OS **cố gắng nạp các trang vào RAM**, có thể tạo page faults và I/O. `isLoaded()` chỉ là **hint** về khả năng các trang đang resident; không phải bảo đảm lâu dài.

`MemorySegment` mapped cũng có `load()`/`isLoaded()` tương ứng. Không gọi `load()` trên hàng chục GB dữ liệu theo thói quen: có thể gây memory pressure, I/O burst và ảnh hưởng các workload khác.

**Giám sát tốt hơn:** RSS, virtual memory, page faults, tốc độ mapping/unmapping, disk I/O, p95/p99 latency, số lượng file/channels và thời gian shutdown/cleanup.

## 10. Kích thước và giới hạn vùng ánh xạ

### 10.1. Giới hạn MappedByteBuffer: Integer.MAX_VALUE

Overload trả về `MappedByteBuffer` nhận `long position` và `long size`, nhưng tài liệu quy định `size <= Integer.MAX_VALUE` vì `ByteBuffer` có capacity/position dạng `int`.

~~~java
// Mảnh minh họa: đừng map một buffer lớn hơn int max.
long regionSize = 3L * 1024 * 1024 * 1024;
// channel.map(MapMode.READ_ONLY, 0, regionSize); // Không hợp lệ.
~~~

`FileChannel.map(..., Arena)` trả về `MemorySegment` có kích thước tính theo `long`, nên API này thích hợp hơn khi cần một vùng ánh xạ lớn, **trong giới hạn OS/địa chỉ ảo/file/nguồn lực thực**. Không suy rằng mọi hệ điều hành/máy đủ khả năng map một vùng bất kỳ chỉ vì tham số là `long`.

### 10.2. Cách xử lý file lớn trên Java 17

Khi chỉ có `MappedByteBuffer`, chia file thành **nhiều cửa sổ ánh xạ có kích thước giới hạn**. Ví dụ:

~~~java
static void scanFile(FileChannel channel, long fileSize)
        throws java.io.IOException {
    final long chunkSize = 256L * 1024 * 1024;
    for (long offset = 0; offset < fileSize; ) {
        long size = Math.min(chunkSize, fileSize - offset);
        MappedByteBuffer part = channel.map(
            FileChannel.MapMode.READ_ONLY, offset, size);
        // Xử lý part và không giữ tham chiếu lâu nếu không cần.
        offset += size;
    }
}
~~~

Đây là **mảnh phương thức minh họa**, không phải code xử lý thật. Khi dùng `MappedByteBuffer` liên tiếp, từng mapping vẫn có lifetime theo GC, vì vậy **chỉ chia nhỏ file chưa bảo đảm OS mappings được giải phóng ngay**. Nếu workload tạo hàng nghìn cửa sổ, cân nhắc tái dùng mapping, giảm số vùng đang sống hoặc dùng `MemorySegment + Arena` trên JDK 22+.

Ngoài ra, hãy kiểm tra phép tính `offset + size` có overflow không trước khi map. Với file lớn, luôn dùng `long` cho file offsets và file size; không ép cả file length sang `int`.

### 10.3. Offset và ranh giới backing file

Các điều kiện cần kiểm tra:

- `offset >= 0`, `size >= 0`.
- Offset và size **không overflow**.
- Với read-only mapping, chỉ map các byte thực sự nằm trong file nếu muốn hành vi dễ dự đoán.
- Với read/write mapping, file đủ kích thước chưa? Các quy tắc mở rộng file khác nhau theo mode/OS. Không dựa vào việc map vượt cuối file rồi hy vọng dữ liệu được khởi tạo rõ ràng.
- Nếu muốn dữ liệu đã tồn tại được bảo toàn, **không tự `TRUNCATE_EXISTING`** khi mở file.

Đối với một file bền vững, logic tốt nhất là **xác định định dạng và kích thước file trước**, rồi mới map một vùng có độ dài đã được xác minh.

## 11. Không thay đổi kích thước file khi mapping đang được sử dụng

Một rủi ro nghiêm trọng: tiến trình khác hoặc code của chính mình **truncate** file trong khi vẫn có một mapping tới vùng cũ.

Theo Javadoc:

- Một phần hoặc toàn bộ mapping có thể trở nên **không thể truy cập** nếu backing file bị thu nhỏ.
- Cố đọc/ghi vùng không còn hợp lệ có thể dẫn tới **exception không được chỉ rõ** ở lúc truy cập hoặc sau đó.
- Việc thay đổi kích thước/nội dung file qua các cơ chế khác và mức độ hiển thị cho mapping phụ thuộc OS.

**Không nên viết test dựa vào “luôn ném đúng IndexOutOfBoundsException”** khi ai đó truncate backing file. Đây không phải một cơ chế kiểm soát file size an toàn.

### Quy trình thiết kế an toàn hơn

1. Có chủ sở hữu rõ của backing file trong suốt thời gian mapping sống.
2. Cấm hoặc phối hợp mọi thao tác truncate, replace hoặc xóa file đang được map.
3. Nếu cần thay thế file, tạo một **file mới** với định dạng hợp lệ rồi áp dụng cơ chế chuyển đổi phiên bản/đường dẫn, và chỉ bỏ bản cũ sau khi không còn người đọc.
4. Với nhiều processes, xây dựng một **giao thức đồng bộ hóa ở mức ứng dụng**; không dựa duy nhất vào mapped memory.
5. Nếu dùng file locks, tìm hiểu cơ chế và giới hạn của `FileLock` trên OS/filesystem: lock không phải bảo đảm tuyệt đối mọi tác nhân đều tôn trọng.
6. Xem xét checksum/version để phát hiện dữ liệu đang cập nhật hoặc bị hỏng.

### Cảnh báo concurrent modifications

Mapped bytes có thể thay đổi khi thread/process khác viết vào cùng backing file. Khi nào thay đổi hiện ra, và cách hai tiến trình nhìn thấy bộ nhớ mapped cùng file, có phần **OS-dependent/unspecified**.

Nếu nhiều thread ghi cùng vùng, cần kiểm soát data races, thứ tự ghi, quy tắc atomicity và visibility theo hợp đồng thực tế. Chỉ vì cùng một mapping được chia sẻ **không có nghĩa mọi write là atomic hoặc transactional**.

## 12. Đóng file, rename, delete: nhất là trên Windows

Trong Java 17:

~~~java
MappedByteBuffer mapped;
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ)) {
    mapped = channel.map(
        FileChannel.MapMode.READ_ONLY, 0, channel.size());
}
// channel đã đóng; mapped vẫn có thể còn sống.
~~~

Đây là **mảnh code**. Nếu chương trình ngay lập tức thử:

~~~java
Files.delete(path);
~~~

thì kết quả **phụ thuộc OS/điều kiện filesystem và trạng thái mapping**. Trên Windows, vùng map còn sống thường khiến việc xóa/đổi tên thay file thất bại. Trên các hệ điều hành khác, unlink file có thể thành công trong khi mapping cũ tiếp tục gắn với nội dung backing cũ.

Do vậy:

- Không hứa xóa file thành công ngay khi channel.close() trả về.
- Không dựa vào `path.toFile().deleteOnExit()` để quản lý vòng đời dữ liệu chính; đó chỉ là cleanup best-effort khi JVM kết thúc.
- Không gọi `System.gc()` trong logic dọn tệp ở production.
- Java 22+ nên dùng **closeable `Arena`** rồi mới thao tác xóa/đổi tên nếu cần release mapping ở thời điểm có kiểm soát.
- Cần quản lý các **view/slice/consumer threads** để không ai còn sử dụng vùng mapping khi arena sắp đóng.

**Đừng thử truncate/delete một tệp có dữ liệu thật chỉ để “xem có unmap không”**. Ví dụ trong bài đều dùng file tạm do chương trình tự tạo.

## 13. Chiến lược đồng thời: Arena, channel và multi-thread

### MappedByteBuffer

`FileChannel` có quy tắc đồng thời riêng (một số thao tác được serialize). Tuy nhiên **các chỉ số `position/limit/mark` của ByteBuffer là trạng thái có thể thay đổi** và không nên được chỉnh sửa bừa bãi từ nhiều threads. Nếu nhiều thread dùng cùng backing bytes:

- Dùng các view riêng để tránh va chạm cursor, ví dụ `duplicate()`, `slice()`, hoặc absolute `get(index)/put(index,value)`.
- Vẫn cần đồng bộ hóa **dữ liệu chung** khi đọc/ghi, vì có view riêng không tự làm dữ liệu trở thành thread-safe.
- Đừng giữ duplicate trong cache vô hạn nếu chủ mapping cần unmap/xóa file.

### MemorySegment + Arena

Với `Arena.ofConfined()`:

- Segment chỉ truy cập hợp lệ từ **owner thread**.
- Nếu dùng ở thread khác có thể ném `WrongThreadException`.
- Vòng đời chỉ do owner quản lý; phù hợp xử lý một luồng, tránh race khi shutdown.

Với `Arena.ofShared()`:

- Có thể cho nhiều thread truy cập segment.
- Phải có **ownership protocol**: dừng nhận yêu cầu mới, đợi các worker kết thúc vùng truy cập, rồi mới đóng arena.
- Không close giữa lúc worker khác đang thực hiện đọc/ghi; quản lý đồng thời là trách nhiệm ứng dụng.

Không chuyển sang `Arena.global()` chỉ để né lỗi `WrongThreadException`. Global arena có lifetime không đóng, khiến tài nguyên map sống tới hết tiến trình — không phù hợp nếu cần kiểm soát số lượng mapping và xóa file tạm.

## 14. Thiết kế Resource Owner cho ứng dụng thực

Khi một vùng ánh xạ phục vụ nhiều hàm, nên tạo **một lớp quản lý lifetime duy nhất**, thay vì để từng hàm tự mở kênh và tạo mapping rồi quên.

Quy trình khái niệm:

~~~text
open file / kiểm tra size
    -> tạo Arena + ánh xạ
        -> tạo view theo range
            -> đọc/ghi có đồng bộ
            -> force khi cần durability
        -> chặn truy cập mới
        -> đợi các thao tác đang chạy xong
    -> Arena.close() để unmap
    -> FileChannel.close() nếu chưa đóng
    -> delete/rename/rotate file nếu cần và được phép
~~~

Chú ý: thứ tự đóng FileChannel và Arena không phải lúc nào phải giống hệt sơ đồ; **mapping độc lập với channel**. Quy tắc cốt lõi là:

1. Không cho phép consumer truy cập segment **sau khi arena đóng**.
2. Không truncate backing file trong lúc mapping còn được dùng.
3. Nếu cần durability, flush **trước** khi mapping bị giải phóng.
4. Đóng tất cả `FileChannel` bằng try-with-resources.
5. Giới hạn tổng số mapping đang sống và điều kiện dừng.

### Định nghĩa policy budget

Một service có thể đặt budget (các con số phải dựa vào workload thật, không có ngưỡng chung của Java):

- Tổng kích thước **virtual mapped regions**.
- Số mapping/arenas đồng thời.
- Số file channels/handles đang mở.
- Số thao tác đồng thời đang truy cập mapping.
- Dung lượng page cache/physical memory và I/O budget.
- Thời gian chờ cleanup hoặc shutdown.
- Số file backing đang được giữ cho các bản snapshot/phiên bản cũ.

Nếu vượt budget, nên **từ chối/đợi tạo mapping mới theo chính sách**, thay vì luôn gọi map cho tới khi JVM hoặc OS báo lỗi tài nguyên.

## 15. Kiểm thử vòng đời và khả năng phục hồi

### 15.1. Các test đơn vị hữu ích

1. Mở một file tạm 8 byte, map READ_WRITE và ghi giá trị cố định.
2. Đóng FileChannel và xác nhận mapping vẫn còn truy cập hợp lệ **nếu dùng MappedByteBuffer**.
3. Dùng `force()`, đọc lại bytes và so sánh giá trị.
4. Với Java 22+, đóng `Arena` rồi xác nhận truy cập `MemorySegment` ném `IllegalStateException`.
5. Thử đóng kênh hoặc arena sau khi exception từ code nghiệp vụ để chứng minh `try-with-resources` vẫn dọn.
6. Kiểm tra file tạm có thể xóa sau khi mapping đã được arena unmap, trên các OS mục tiêu.
7. Kiểm tra ứng dụng từ chối map khi `offset/size` không hợp lệ hoặc vượt budget.
8. Xem lại log lỗi I/O: `force` có thể lỗi, không được coi một thao tác thất bại là commit thành công.

### 15.2. Test hiệu năng và tài nguyên

Đo với khối lượng dữ liệu và số threads đại diện:

| Chỉ số | Cần phát hiện |
| --- | --- |
| Virtual memory / mapped regions count | Nhiều mapping sống lâu gây cạn không gian hoặc giới hạn OS |
| RSS / page faults / page cache | Working set quá lớn, truy cập ngẫu nhiên gây pressure |
| File descriptors / handles | Rò rỉ FileChannel hoặc handles từ các resource khác |
| Throughput, p95/p99 latency | `load()` hoặc `force()` tạo burst I/O |
| Thời gian shutdown / rotate | Có chờ workers và unmap đúng thứ tự không |
| Lỗi xóa/rename trên Windows | Mapping chưa được giải phóng hoặc file bị giữ |
| Tần suất GC và thời gian mapping cleanup | Thiết kế Java 17 phụ thuộc GC quá nhiều? |

Không đo overhead của mmap chỉ bằng dung lượng heap. Và **không khẳng định map luôn nhanh hơn read/write**: Javadoc `FileChannel.map` lưu ý map thường chỉ đáng giá cho những file tương đối lớn, còn mapping nhiều vùng rất nhỏ có thể tốn hơn I/O thông thường.

### 15.3. Test lỗi có kiểm soát

Không thực hiện thao tác phá hỏng file backing production hoặc NVM thật để thử lỗi. Dùng file tạm và quy trình test trên môi trường cách ly. Những tình huống thao tác với file bị truncate có thể cho exception **không được chỉ rõ** theo tài liệu; tránh biến test thành yêu cầu cứng về một loại exception cố định.

## 16. Xử lý lỗi: phân biệt tài nguyên nào đang gặp vấn đề

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Đã `channel.close()` nhưng file vẫn không xóa được | Mapping vẫn sống; tiến trình khác giữ file; OS/file permissions | Kiểm tra mapping lifetime, file handles, OS và Java version |
| `MappedByteBuffer` còn đọc được sau channel.close | Đúng đặc tả, không phải leak của channel | Quản lý riêng vùng mapping |
| Đọc segment sau arena.close ném `IllegalStateException` | Vùng đã hết lifetime | Không escape segment khỏi scope hoặc thiết kế API rõ owner |
| Truy cập segment từ thread khác ném `WrongThreadException` | Dùng confined arena sai thread | Dùng owner thread hoặc shared arena có lifecycle an toàn |
| `map` trả `UnsupportedOperationException` với `READ_WRITE_SYNC` | OS/filesystem/NVM không hỗ trợ synchronous mapping | Kiểm tra NVM/DAX support, không fallback âm thầm |
| Lỗi `IllegalArgumentException` khi map buffer quá lớn | Kích thước > `Integer.MAX_VALUE` hoặc offset/size không hợp lệ | Chia window hoặc dùng MemorySegment 22+ |
| `force()` lỗi | Lỗi ghi dữ liệu, quyền, storage hoặc filesystem | Xử lý lỗi, không coi dữ liệu đã durable |
| Process có heap trống nhưng map thất bại | Cạn virtual space, kernel mapping limit hoặc resource OS | Kiểm tra VM mappings, RSS, OS limits, chứ không chỉ `-Xmx` |
| App bị chậm sau `load()` | Page faults, disk I/O, RAM pressure | Dùng load có mục đích; đo profiling trên workload |
| Mapping không còn truy cập sau truncate | File backing thay đổi kích thước | Ngăn thay đổi file khi mapping đang dùng |
| File có dữ liệu mới nhưng reader khác chưa thấy | OS caching/concurrency/flush semantics | Kiểm tra giao thức đồng bộ và snapshot, không suy rằng force giải quyết mọi visibility |
| Không thể map file NVM trên Linux | Sai mount, không có DAX/MAP_SYNC, quyền hoặc module config | Xác minh NVM-capable FS và ExtendedMapMode support |

## 17. Lỗi thiết kế thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “FileChannel.close() sẽ unmap mọi vùng đã tạo.” | Mapping độc lập với channel sau khi tạo. |
| “MappedByteBuffer có close() như FileChannel.” | Không có close công khai; lifetime phụ thuộc GC. |
| “MappedByteBuffer không còn dùng được khi channel đóng.” | Nó có thể tiếp tục hợp lệ và đọc/ghi bình thường. |
| “Chỉ cần System.gc() là mapping được giải phóng ngay.” | Không có đảm bảo thời điểm GC/unmap. |
| “Dùng Unsafe/cleaner nội bộ là cách chuẩn.” | Không được khuyến nghị; không phải API Java SE. |
| “Arena.close() tương đương flush() xuống NVM.” | Arena kiểm soát lifetime; force kiểm soát flush. |
| “force(channel) luôn flush cả mọi mapped writes.” | `FileChannel.force` không bảo đảm mọi sửa đổi qua mapped buffer. |
| “NVM READ_WRITE_SYNC chạy được trên mọi máy.” | Cần filesystem/OS/thiết bị phù hợp; có thể unsupported. |
| “Một ByteBuffer map được hàng chục GB.” | `MappedByteBuffer` bị giới hạn size theo `int`. |
| “MemorySegment long size không bị giới hạn bởi tài nguyên.” | Vẫn phụ thuộc OS/địa chỉ ảo, file và nguồn lực. |
| “Có nhiều heap memory thì mmap không thể OOM.” | Mmap còn dùng virtual memory, page cache và OS limits. |
| “Thay file trong lúc đang map là an toàn.” | Truncate/replace có thể khiến mapping mất hiệu lực hoặc thấy dữ liệu OS-dependent. |
| “force() có nghĩa nhiều trường ghi atomically.” | Force không thay thế transaction, format và recovery protocol. |
| “load() sẽ giữ toàn bộ mapping trong RAM mãi mãi.” | Chỉ best-effort hint, OS có thể page out. |
| “MappedByteBuffer nên bị loại bỏ vì legacy.” | Đây vẫn là API chuẩn được hỗ trợ; chọn Arena khi cần deterministic lifetime và có Java 22+. |

## 18. Checklist trước khi dùng file mapping trong ứng dụng thật

1. **JDK mục tiêu:** app chỉ chạy Java 17/21 hay cho phép Java 22+ dùng Arena?
2. **Mục tiêu:** mapping file thường hay NVM/DAX với `READ_WRITE_SYNC`? Đã kiểm tra platform support?
3. **Sở hữu:** ai là owner của FileChannel, mapping, Arena và backing file?
4. **Lifecycle:** có đóng FileChannel qua try-with-resources không? Mapping được giải phóng khi nào?
5. **Durability:** với read/write mapping, đã `force()` trước khi unmap/hoàn tất commit chưa?
6. **Size:** offset/length hợp lệ, không overflow, không vượt `Integer.MAX_VALUE` cho MappedByteBuffer?
7. **Backing file:** đã kiểm tra hoặc chuẩn bị file size chưa? Có ai có thể truncate/replace khi mapping đang sống?
8. **Concurrency:** shared segment và threads có quy tắc shutdown/đồng bộ không?
9. **OS:** Windows có yêu cầu giải phóng mapping trước khi xóa/rename file không?
10. **Resource limits:** có budget cho virtual mappings, page cache, file handles và I/O không?
11. **Performance:** benchmark map với read/write trên workload thật, đã thử nhiều sizes và độ song song chưa?
12. **Recovery:** nếu power loss xảy ra giữa ghi, định dạng dữ liệu và khôi phục có an toàn không?
13. **Observability:** có metrics về số mapping, mapped bytes, page faults, force latency và cleanup failures không?
14. **Bảo mật:** file backing chứa dữ liệu nhạy cảm có quyền truy cập, mã hóa và retention phù hợp không?

## 19. Bài tập thực hành có đáp án

### Bài 1 — Channel đã đóng, mapping còn hiệu lực?

~~~java
MappedByteBuffer mapped;
try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {
    mapped = channel.map(FileChannel.MapMode.READ_ONLY, 0, 16);
}
// Có được đọc mapped.get(0) không?
~~~

**Đáp án:** theo đặc tả, mapping vẫn có thể hợp lệ **sau khi channel đóng**, miễn là backing file/vùng ánh xạ không bị thay đổi theo cách gây mất hiệu lực. Không coi channel.close là unmap. Ví dụ chỉ hợp lệ nếu file có ít nhất 16 byte và có quyền đọc.

### Bài 2 — Dọn mapping ngay trên Java 17

Một dịch vụ Java 17 tạo vài nghìn `MappedByteBuffer`, gọi `System.gc()` sau mỗi file để xóa.

**Đáp án:** không nên. GC không bảo đảm unmap tức thời và có thể gây pause lớn. Giới hạn mapping đồng thời, tái sử dụng mapping hoặc thiết kế đọc/ghi khác nếu không thể dùng Java 22+. Với Java 22+, cân nhắc `FileChannel.map(..., Arena)`.

### Bài 3 — Đóng Arena và truy cập segment

~~~java
MemorySegment segment;
try (Arena arena = Arena.ofConfined()) {
    segment = channel.map(FileChannel.MapMode.READ_ONLY, 0, 8, arena);
}
segment.get(ValueLayout.JAVA_BYTE, 0);
~~~

**Đáp án:** truy cập sau close sẽ ném `IllegalStateException`. Cần giữ tất cả thao tác trong lifetime của arena. Đây là mảnh mã Java **22+**, không phải cú pháp chạy được trên Java 17.

### Bài 4 — Ghi mapped bytes và durability

Bạn gọi `channel.force(true)` sau khi sửa nội dung qua `mapped.putInt(...)` mà không gọi `mapped.force()`. Đã bảo đảm flush nội dung mapped chưa?

**Đáp án:** không theo cam kết của `FileChannel.force()`. Dùng `mapped.force()` hoặc `MemorySegment.force()` cho thay đổi qua mapping; nếu cần metadata, cân nhắc force channel riêng và filesystem contract.

### Bài 5 — File lớn hơn 2 GiB

Một file 5 GiB, chương trình cố `channel.map(READ_ONLY,0,5L*1024*1024*1024)` thành `MappedByteBuffer`.

**Đáp án:** kích thước vượt `Integer.MAX_VALUE`, không hợp lệ cho overload trả buffer. Chia thành nhiều vùng có size nhỏ hoặc dùng overload mapped `MemorySegment` trên Java 22+ và kiểm soát Arena/OS resources.

### Bài 6 — NVM mode không được hỗ trợ

Một chương trình gọi `map(ExtendedMapMode.READ_WRITE_SYNC,...)` trên hệ thống file không hỗ trợ MAP_SYNC và gặp `UnsupportedOperationException`.

**Đáp án:** đó là tình huống cần dự liệu; kiểm tra nền tảng và NVM/DAX support. Chỉ fallback sang `READ_WRITE` nếu hợp đồng độ bền và kiến trúc cho phép, không tự chuyển chế độ trong ứng dụng cần nhất quán dữ liệu trên NVM.

### Bài 7 — Truncate file trong khi worker đọc mapping

Một thread giữ mapping tới 1 MiB, thread khác gọi `channel.truncate(4096)` trên file đó.

**Đáp án:** thao tác có thể khiến một phần mapping không còn truy cập. Không dựa vào một exception cụ thể để kiểm soát. Cần phối hợp ownership và ngăn truncate/replace trong lúc vẫn có consumer.

### Bài 8 — Chạy hai chương trình kiểm chứng

Chạy `MappedBufferLifecycleDemo.java` với JDK 17+ và `ArenaMappingLifecycleDemo.java` với JDK 22+. Quan sát hai khác biệt:

- Chương trình đầu: `channel-after-close=false` nhưng `mapping-after-close=01020304`.
- Chương trình hai: `segment-after-arena-close-inaccessible=true` và file được dọn sau khi arena đóng.

Giải thích tại sao sự khác biệt này quan trọng khi ứng dụng cần rotate snapshot hoặc xóa file trên Windows.

## 20. Tài liệu chính thức hiện còn áp dụng

- [Oracle JDK 25 — FileChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): map trả `MappedByteBuffer`, map trả `MemorySegment`, channel independence, giới hạn size và semantics của `force`.
- [Oracle JDK 25 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html): vòng đời phụ thuộc GC, `force`, `load`/`isLoaded`, khả năng backing file bị truncate.
- [Oracle JDK 26 — FileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html): các overload và hợp đồng tiếp tục được hỗ trợ.
- [Oracle JDK 25 — ExtendedMapMode](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_ONLY_SYNC`, `READ_WRITE_SYNC` và điều kiện nền tảng hỗ trợ NVM.
- [Oracle JDK 26 — Arena](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared/auto/global, lifetime và khả năng truy cập giữa threads.
- [Oracle JDK 25 — Backing a Memory Segment with a File](https://docs.oracle.com/en/java/javase/25/core/backing-memory-segment-memory-region-inside-file.html): ánh xạ bằng `FileChannel.map(..., Arena)` và các ví dụ chuẩn.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): lý do hỗ trợ ánh xạ đồng bộ trên NVM từ JDK 14.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): nền tảng API MemorySegment/Arena chính thức từ Java 22.
