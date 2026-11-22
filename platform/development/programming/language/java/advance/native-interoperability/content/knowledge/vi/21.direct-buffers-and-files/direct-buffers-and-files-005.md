# Ánh xạ tệp thành MemorySegment với FileChannel và Arena trong Java FFM

**Memory-mapped file** là kỹ thuật để hệ điều hành ánh xạ một vùng byte của tệp vào không gian địa chỉ của tiến trình. Thay vì gọi `FileChannel.read(...)` và copy từng khối vào `ByteBuffer`, chương trình có thể **truy cập bytes của tệp thông qua bộ nhớ ánh xạ**; hệ điều hành điều phối trang nhớ (pages), page cache, page faults và quá trình ghi dữ liệu về storage. Từ **JDK 22**, Java cung cấp overload `FileChannel.map(FileChannel.MapMode mode, long offset, long size, Arena arena)` trả về **`java.lang.foreign.MemorySegment`**, kết hợp lợi ích của mapping với **spatial bounds và lifetime do `Arena` quản lý**.

Điểm cần hiểu đúng: **`FileChannel` và `Arena` có vòng đời khác nhau**. Đóng `FileChannel` sau khi mapping thành công **không tự khiến mapped segment mất hiệu lực**; còn khi đóng một `Arena` closeable chứa mapping, JVM có thể thu hồi/unmap vùng ánh xạ và những lần truy cập tiếp theo bị từ chối. `MemorySegment.force()` có ý nghĩa đồng bộ thay đổi cho mapping **`READ_WRITE`**, nhưng **không biến file I/O thành giao dịch nguyên tử**. Nếu tệp bị tiến trình khác truncate hoặc đổi nội dung khi đang mapped, dù segment vẫn có size/scope đúng, vùng memory có thể trở nên không truy cập được.

Bài thuộc nhóm **Bộ đệm và tệp** trong module Java Advance — native-interoperability. Ta làm rõ API, ba `MapMode`, offset/size theo byte, mapped segment methods, vai trò `Arena`, cách xử lý lỗi và an toàn khi nhiều thread/process. Có một chương trình **Java 22+ hoàn chỉnh** tạo một file tạm, map `READ_WRITE`, sửa dữ liệu sau khi đóng channel, `force()`, thử `READ_ONLY`/`PRIVATE`, kiểm tra lỗi sau `arena.close()`, cùng lệnh `javac`/`java` và stdout xác định.

> **Phạm vi phiên bản:** `java.lang.foreign` thành API chuẩn từ **Java 22** (JEP 454). Java 17 có FFM incubator, Java 21 vẫn dùng FFM preview khác bản final. Không compile nguyên ví dụ này bằng Java 17/21. Chỉ dùng `FileChannel.map(..., Arena)` và `MemorySegment.get/set/force` **không tự đòi `--enable-native-access`** như các restricted operations dùng để gọi hàm C qua `Linker`. Nếu bạn thêm `Linker.downcallHandle`, `SymbolLookup.libraryLookup` hoặc `reinterpret` thì phải kiểm tra/cấp quyền native access tương ứng.

## 1. Bản chất của memory mapping: bytes, không phải Java objects

Trong I/O truyền thống:

~~~text
File trên storage -> kernel/page cache -> read(...) -> ByteBuffer/byte[]
                                                      -> Java xử lý
~~~

Khi dùng mapping:

~~~text
File trên storage
      |
      | hệ điều hành ánh xạ vùng [offset, offset+size)
      v
Virtual memory trong tiến trình <---- page cache / page faults
      |
      | FileChannel.map(mode, offset, size, arena)
      v
MemorySegment: virtual address + byteSize + scope + access rules
      |
      +-- get(ValueLayout.JAVA_BYTE, byteOffset)
      +-- set(ValueLayout.JAVA_BYTE, byteOffset, value)
      +-- asSlice(...) / asByteBuffer()
      +-- force() / load() / isLoaded() / unload()
      |
      v
Arena.close() -> invalidates mapped segment; unmaps vùng nhớ
~~~

`FileChannel.map(...)` không biến dữ liệu tệp thành đối tượng Java `String`, `int[]`, `struct` hoặc một bộ sưu tập tự decode. File chỉ có **chuỗi byte**. Cách bạn nhóm và diễn giải bytes là trách nhiệm của ứng dụng:

- Binary record có 4-byte integer: dùng `ValueLayout.JAVA_INT` hoặc layout với `ByteOrder` phù hợp **định dạng tệp**, không mặc định đúng native order.
- Text UTF-8: đọc thành một byte sequence và decode bằng charset/decoder, không coi mỗi byte là một Java `char`.
- Header chứa magic/version/length: xác thực rồi mới đọc phần dữ liệu theo offsets có kiểm tra overflow.
- File chứa record với padding/alignment: cần mô tả field layout đúng; offset trong tệp có thể không aligned theo `JAVA_INT`, khi đó dùng unaligned layout **chỉ nếu format thực sự cho phép**.

Mapping thường có lợi khi truy cập ngẫu nhiên, lặp lại trên một tệp lớn; nó không có nghĩa tệp đã nằm toàn bộ trong RAM. Page faults có thể kéo theo I/O bất kỳ lúc nào, và mapped bytes cũng có thể được cache hoặc đẩy ra tùy chính sách OS.

## 2. API then chốt của JDK 22: `FileChannel.map(..., Arena)`

Chữ ký:

~~~java
// Chữ ký API minh họa, không phải một chương trình Java độc lập:
MemorySegment FileChannel.map(
        FileChannel.MapMode mode, long offset, long size, Arena arena)
        throws IOException;
~~~

Cách dùng cơ bản:

~~~java
// Mảnh Java minh họa: file tồn tại, kênh đọc hợp lệ,
// segment/arena chỉ được dùng trong scope còn sống.
try (Arena arena = Arena.ofConfined();
     FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    long size = channel.size();
    MemorySegment mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, size, arena);
    // Đọc bytes trong [0, size), không ghi mapping READ_ONLY.
}
~~~

Bốn đối số có ý nghĩa riêng:

| Đối số | Đơn vị/contract | Điều cần kiểm tra |
| --- | --- | --- |
| `mode` | `READ_ONLY`, `READ_WRITE`, `PRIVATE` | Phải tương thích quyền mở channel |
| `offset` | `long` byte offset trong **tệp** | Không âm, tính toán không overflow; không tự hiểu là record index |
| `size` | `long` số **byte mapping** | Không âm; `offset + size` không overflow; vùng tệp được chứng minh phù hợp |
| `arena` | Owner của scope mapping | Còn alive, quyền thread hợp lệ; giải phóng khi closeable arena đóng |

Trả về:

- Một **mapped native `MemorySegment`** với `mapped.isMapped()==true` và `mapped.byteSize()==size`.
- Segment có bounds: `get/set` theo byte offsets tương đối với **đầu vùng mapping**, không tương đối với đầu toàn bộ tệp.
- Khi `mode==READ_ONLY`, `mapped.isReadOnly()==true` và Java `set` bị từ chối.
- Lifetime của mapping gắn với arena, không gắn trực tiếp với lần gọi `FileChannel.close()` sau khi mapping.
- `FileChannel.map` này khác overload **ba tham số** `map(MapMode,long,long)` có kết quả là **`MappedByteBuffer`**.

Không lẫn `offset` với vị trí tương đối của channel. `map` nhận **vị trí tuyệt đối** trong tệp; không nên giả định nó tăng `channel.position()` như một lệnh `read(ByteBuffer)` theo vị trí hiện tại.

### 2.1. Mốc byte của mapping và mốc byte của segment

Giả sử file dài 1.024 byte. Bạn gọi:

~~~java
// Mảnh minh họa: file>=1024 byte; arena còn sống.
MemorySegment window = channel.map(
        FileChannel.MapMode.READ_ONLY, 100, 40, arena);
~~~

Khi đó:

~~~text
File:     byte 0 ................... byte 100 ........ byte 139 ... byte 1023
                                       |                 |
                                       +--- 40 bytes ---+
                                               |
Segment: byte 0 ............................. byte 39
~~~

`window.get(JAVA_BYTE, 0)` đọc **file byte 100**; `window.get(JAVA_BYTE,39)` đọc **file byte 139**. `window.get(JAVA_BYTE,40)` nằm ngoài segment và không được đọc. Nếu muốn map record thứ 5, phải tính **byte offset** từ format: `recordIndex * recordStride` kèm kiểm tra overflow rồi mới truyền vào `map`.

Với mapping 0 byte, bạn có một view rỗng; không được cố đọc phần tử 0. Để code portable, thường xử lý tệp rỗng bằng nhánh riêng thay vì tự yêu cầu OS map 0 byte và giả định tính năng mapping đó có hành vi giống nhau trên mọi provider.

### 2.2. Khác biệt với `MappedByteBuffer`

| Đặc tính | `MappedByteBuffer` cổ điển | `MemorySegment` mapping JDK 22+ |
| --- | --- | --- |
| Tạo bằng | `channel.map(mode,position,size)` | `channel.map(mode,offset,size,arena)` |
| Kết quả | `MappedByteBuffer` | `MemorySegment` |
| Phạm vi dữ liệu mỗi object | Buffer capacity bị ràng buộc bởi `int` | Mapping `size` dùng `long`; vẫn phụ thuộc tài nguyên OS/VM |
| Dọn mapping | Thường phụ thuộc GC/Cleaner hoặc runtime mechanism | **`Arena.close()`** với closeable arena |
| Phương thức access | `buffer.get/put(...)` và buffer position/limit | `segment.get/set(ValueLayout, byteOffset)` |
| Lifetime check | Buffer còn reachable không đảm bảo close deterministic | Scope của `Arena` kiểm tra thời hạn truy cập |
| Chia vùng | `slice/duplicate` theo ByteBuffer | `asSlice(...)` theo long byte offsets |
| Ép ra ByteBuffer | Không cần | `segment.asByteBuffer()` với giới hạn ByteBuffer tương ứng |

**`MemorySegment` có thể đại diện vùng lớn hơn giới hạn index của một `ByteBuffer`**, nhưng không vì thế tệp lớn được map thành công trên mọi OS hay mọi JVM. Giới hạn virtual address space, file system, mapped region và quota OS vẫn áp dụng. Nếu đổi mapped segment rất lớn thành `ByteBuffer`, hãy xét giới hạn capacity kiểu `int` và chia nhỏ theo chunk.

## 3. Ba `FileChannel.MapMode` và ảnh hưởng tới file

| MapMode | Quyền cần có trên FileChannel | Java được ghi qua segment? | Ghi có phản ánh về tệp? |
| --- | --- | --- | --- |
| **`READ_ONLY`** | Mở `READ` | **Không** | Không có sửa đổi từ mapping này |
| **`READ_WRITE`** | Mở **`READ` và `WRITE`** | Có | Thay đổi cuối cùng được truyền về file; gọi `mapped.force()` khi cần cam kết flush |
| **`PRIVATE`** | Mở **`READ` và `WRITE`** | Có (bản copy-on-write riêng) | **Không** truyền các thay đổi private mapping về tệp |

### 3.1. `READ_ONLY`

~~~java
// Mảnh Java minh họa:
try (Arena arena = Arena.ofConfined();
     FileChannel channel = FileChannel.open(file, StandardOpenOption.READ)) {
    MemorySegment segment = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, channel.size(), arena);
    System.out.println(segment.isReadOnly()); // true
    // segment.set(ValueLayout.JAVA_BYTE, 0, (byte)7) bị từ chối.
}
~~~

Với `MemorySegment.set(...)` trên một segment read-only, API có thể ném `IllegalArgumentException`. Đừng diễn giải `READ_ONLY` là “đọc được từ bất cứ thread nào”: nếu arena là confined, chỉ thread owner của arena được truy cập. Read-only là **quyền sửa bytes**, còn thread confinement là **ràng buộc lifetime/ownership** khác.

### 3.2. `READ_WRITE`

~~~java
// Mảnh Java minh họa:
try (Arena arena = Arena.ofConfined();
     FileChannel channel = FileChannel.open(
             file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    MemorySegment segment = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, channel.size(), arena);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte)42);
    segment.force(); // Yêu cầu đồng bộ thay đổi mapping về storage.
}
~~~

`segment.force()` trên mapped `READ_WRITE` có semantics flush; theo tài liệu JDK 22, với descriptor trên **local storage**, khi return thành công, thay đổi trong mapped segment đã được ghi về thiết bị lưu trữ theo hợp đồng. Với network/remote device, tài liệu **không bảo đảm** cùng điều đó. Việc gọi `force` **không làm nhiều write trở thành một transaction** hoặc bảo đảm tính nhất quán đồng thời khi ứng dụng khác đang thay đổi cùng file.

### 3.3. `PRIVATE`: copy-on-write

`PRIVATE` cho phép bạn thử sửa bytes trong view riêng. Thay đổi **không** được đẩy về tệp và không nên trở thành cơ chế cập nhật dữ liệu chung. `mapped.force()` không có hiệu quả đối với mapping private theo đặc tả. Chú ý: copy-on-write **không đồng nghĩa snapshot version ổn định** khi những tiến trình khác đang sửa file; tính nhất quán quan sát còn phụ thuộc OS.

Ví dụ phần thực hành sẽ ghi byte 77 vào PRIVATE mapping tại offset0, đọc trong chính mapping được 77, nhưng byte0 trên tệp sau khi đóng vẫn là 10.

## 4. Vòng đời: đóng channel khác với đóng arena

Hai resource độc lập:

~~~text
FileChannel [OPEN] ------ map(...) --------> MemorySegment [ALIVE]
    |                                           |
    | FileChannel.close()                       | vẫn có thể get/set/force
    v                                           |
  [CLOSED]                                      |
                                                | Arena.close()
                                                v
                                          [SCOPE DEAD/UNMAPPED]
                                                |
                                                +-> get/set bị từ chối
~~~

`FileChannel` điều khiển I/O API và handle tệp. Sau khi mapping hoàn tất, tệp đã được map qua OS vào memory; tài liệu `FileChannel.map(...,Arena)` định nghĩa lifetime của **mapped segment** bằng arena. Vì thế **không lấy channel.close làm lệnh unmap**. Ngược lại, **arena.close** không buộc đóng một FileChannel bạn vẫn giữ mở: hãy đóng cả hai theo đúng ownership.

### 4.1. `Arena.ofConfined()`

- Một thread sở hữu arena và những mapped segments liên quan.
- Hợp cho một quy trình map/đọc/sửa/flush/đóng có lifecycle rõ ràng.
- Dùng `try-with-resources` để `close()` chạy cả khi có Java exception.
- Truy cập confined segment từ thread khác có thể ném `WrongThreadException`.
- Khi arena đóng, `MemorySegment.get/set` vào segment đó thường ném `IllegalStateException`.
- Tránh cho segment hoặc slice thoát ra khỏi method nếu owner arena đã bị đóng.

### 4.2. `Arena.ofShared()`

- Cho phép access từ nhiều threads khi ứng dụng thực sự cần chia việc.
- **Không** tự đồng bộ concurrent writes; caller cần locking/atomic strategy hợp lệ.
- `Arena.close()` có thể cần chờ các accesses đang chạy để hoàn tất theo protocol scope; nên ngừng nhận việc, đợi in-flight work rồi mới đóng.
- File mapping giữa tiến trình và threads có hệ quả page-cache/coherence phức tạp. File locks và Java thread locks phục vụ các vấn đề khác nhau, không thay thế lẫn nhau.

### 4.3. `Arena.ofAuto()` và `Arena.global()`

- `Arena.ofAuto()` có lifetime do GC quản lý; thời điểm cleanup không xác định, khó sử dụng cho những file cần unmap đúng hạn.
- `Arena.global()` là scope sống đến khi JVM kết thúc, không đóng; tránh dùng cho mapping tạm hoặc nhiều mapping lớn cần giải phóng.
- **Khuyến nghị:** mapping ngắn/trung hạn với lifecycle ứng dụng rõ ràng dùng closeable arena, đặc biệt khi cần xóa/đổi tên file trên hệ điều hành có ràng buộc đối với file vẫn mapped.

### 4.4. `asSlice` không tách khỏi owner

~~~java
// Mảnh Java minh họa: mapped size >= 64 byte, arena sống.
MemorySegment header = mapped.asSlice(0, 16);
MemorySegment payload = mapped.asSlice(16, 48);
~~~

`header` và `payload` cùng chia sẻ backing mapping/scope. `asSlice` chỉ siết spatial bounds; **không tạo bản copy tách riêng** và không sở hữu mapping mới. Khi parent arena đóng, các slices cũng hết hiệu lực. Không dùng `asSlice` để “giữ sống mapping” sau khi owner đóng.

## 5. Đọc/ghi bằng ValueLayout: byte order, alignment và phạm vi

`MemorySegment.get(ValueLayout, offset)` nhận **byte offset** từ đầu segment. Đây không phải index của int array. Với binary files, layout nên bám **format**:

~~~java
// Mảnh minh họa cho format big-endian:
// file có ít nhất 8 byte và region hợp lệ.
ValueLayout.OfInt bigEndianInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
int magic = mapped.get(bigEndianInt, 0);
int length = mapped.get(bigEndianInt, 4);
~~~

Nếu số nguyên nằm ở byte offset1 của file, `JAVA_INT` có constraint alignment theo native 4 byte và có thể bị từ chối. Nếu format cố ý packed, dùng `JAVA_INT_UNALIGNED.withOrder(...)`, **sau khi** chứng minh vùng bytes 1..4 thật sự là int của format và còn trong bounds.

~~~java
// File chứa int32 big-endian ở byte offset1, không aligned4.
ValueLayout.OfInt packedInt =
        ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN);
int number = mapped.get(packedInt, 1);
~~~

Lưu ý:

1. `byteSize()` của layout là kích thước **một giá trị**. `JAVA_INT.byteSize() == 4`; đọc offset7 trong segment size8 vượt biên.
2. `getAtIndex(JAVA_INT,i)` dùng **element index** (scale theo size), khác `get(JAVA_INT,byteOffset)`.
3. `MemorySegment` bảo vệ các truy cập Java đối với bounds/scope/threads, nhưng nếu backing file bị truncate **mà segment chưa đóng**, OS có thể khiến một phần mapping không truy cập được; không thể dùng Java bounds checker để chứng minh tệp ngoài process chưa thay đổi.
4. `ByteOrder.nativeOrder()` thích hợp cho một số native ABI, nhưng file format dùng BIG/LITTLE cố định phải được decode đúng theo tài liệu, bất kể CPU.
5. Khi đọc metadata length từ file, phải kiểm tra số âm, maximum, overflow và offset trước khi đọc payload; không sử dụng bất kỳ length từ file không tin cậy để tạo slice khi chưa xác minh.

## 6. Ví dụ Java 22+ hoàn chỉnh, không cần JNI/C compiler

Ví dụ tạo một **tệp tạm**, viết trước tám bytes, map `READ_WRITE`, đóng channel **trước** khi thao tác tiếp trên mapping, sửa byte và `force`. Sau đó mở lại `READ_ONLY` và `PRIVATE` để kiểm chứng quyền truy cập/semantics copy-on-write. Cuối cùng đóng arena và chứng minh segment không còn được truy cập.

Tệp nguồn tên **`FileMappingDemo.java`**, không có `package`. Chương trình dùng `Files.createTempFile` và xóa file trong `finally`, không ghi đè một file làm việc của bạn. Các thao tác kiểm chứng dùng byte nên stdout không phụ thuộc endianness hay alignment của host.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileMappingDemo {
    private FileMappingDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("ffm-mapped-", ".bin");

        try {
            Files.write(file, new byte[] {
                    10, 20, 30, 40, 50, 60, 70, 80
            });

            // Để ngoài try để minh họa truy cập bị từ chối sau close.
            MemorySegment mapped;

            try (Arena arena = Arena.ofConfined()) {
                try (FileChannel channel = FileChannel.open(
                        file,
                        StandardOpenOption.READ,
                        StandardOpenOption.WRITE)) {

                    mapped = channel.map(
                            FileChannel.MapMode.READ_WRITE,
                            0, channel.size(), arena);

                    System.out.println("mapped=" + mapped.isMapped());
                    System.out.println("size=" + mapped.byteSize());
                    System.out.println("readOnly=" + mapped.isReadOnly());
                    System.out.println("initialByte1=" +
                            (mapped.get(ValueLayout.JAVA_BYTE, 1) & 0xFF));
                } // Chỉ FileChannel đã đóng; arena vẫn mở.

                System.out.println("afterChannelClose=" +
                        (mapped.get(ValueLayout.JAVA_BYTE, 1) & 0xFF));

                mapped.set(ValueLayout.JAVA_BYTE, 1, (byte) 99);

                // Segment con từ file byte2..byte4: 30+40+50.
                MemorySegment slice = mapped.asSlice(2, 3);
                long sum = 0;
                for (long i = 0; i < slice.byteSize(); ++i) {
                    sum += slice.get(ValueLayout.JAVA_BYTE, i) & 0xFF;
                }
                System.out.println("sliceSum=" + sum);

                mapped.force();
                System.out.println("updatedByte1=" +
                        (mapped.get(ValueLayout.JAVA_BYTE, 1) & 0xFF));
            } // Arena đóng: mapping không còn hợp lệ.

            try {
                mapped.get(ValueLayout.JAVA_BYTE, 0);
                System.out.println("closedRejected=false");
            } catch (IllegalStateException expected) {
                System.out.println("closedRejected=true");
            }

            System.out.println("fileByte1=" +
                    (Files.readAllBytes(file)[1] & 0xFF));

            // READ_ONLY: Java không được ghi qua segment.
            try (Arena arena = Arena.ofConfined();
                 FileChannel channel = FileChannel.open(
                         file, StandardOpenOption.READ)) {

                MemorySegment readOnly = channel.map(
                        FileChannel.MapMode.READ_ONLY,
                        0, channel.size(), arena);

                System.out.println("readonly=" + readOnly.isReadOnly());

                try {
                    readOnly.set(
                            ValueLayout.JAVA_BYTE, 0, (byte) 1);
                    System.out.println("readonlyWriteRejected=false");
                } catch (IllegalArgumentException expected) {
                    System.out.println("readonlyWriteRejected=true");
                }
            }

            // PRIVATE: thay đổi nằm trong copy-on-write view,
            // KHÔNG được ghi vào file.
            try (Arena arena = Arena.ofConfined();
                 FileChannel channel = FileChannel.open(
                         file,
                         StandardOpenOption.READ,
                         StandardOpenOption.WRITE)) {

                MemorySegment privateMap = channel.map(
                        FileChannel.MapMode.PRIVATE,
                        0, channel.size(), arena);

                privateMap.set(
                        ValueLayout.JAVA_BYTE, 0, (byte) 77);
                System.out.println("privateValue=" +
                        (privateMap.get(ValueLayout.JAVA_BYTE, 0) & 0xFF));
                privateMap.force(); // Không persist PRIVATE changes.
            }

            System.out.println("fileByte0=" +
                    (Files.readAllBytes(file)[0] & 0xFF));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

### 6.1. Biên dịch và chạy

Từ thư mục chứa `FileMappingDemo.java`, cần JDK 22+:

~~~sh
java -version
javac -version
javac FileMappingDemo.java
java FileMappingDemo
~~~

Windows Command Prompt hoặc PowerShell cũng dùng lệnh `javac FileMappingDemo.java` và `java FileMappingDemo`. **Không cần `javac -h`, `jni.h`, compiler C, native library hoặc `--enable-preview`**. Chương trình không dùng `Linker.downcallHandle` và không gọi restricted FFM native-function API; do đó không yêu cầu `--enable-native-access=ALL-UNNAMED` chỉ để map file vào `MemorySegment`.

### 6.2. Stdout dự kiến

~~~text
mapped=true
size=8
readOnly=false
initialByte1=20
afterChannelClose=20
sliceSum=120
updatedByte1=99
closedRejected=true
fileByte1=99
readonly=true
readonlyWriteRejected=true
privateValue=77
fileByte0=10
~~~

Kiểm toán từng bước:

- File tạm ban đầu gồm bytes `10,20,30,40,50,60,70,80` (8 byte). `map(READ_WRITE,0,8,arena)` trả mapped segment có size8.
- Byte index1 ban đầu =20; đóng `FileChannel` không hủy mapping vì arena vẫn alive, nên đọc sau channel.close còn 20.
- Ghi byte index1 =99; slice bắt đầu ở index2 dài 3 nên tổng 30+40+50=120.
- `mapped.force()` đồng bộ thay đổi; sau đóng arena, đọc lại file được byte index1=99.
- Truy cập qua `mapped` sau khi đóng arena ném `IllegalStateException`, được Java bắt và in true.
- Mapping `READ_ONLY` có `isReadOnly()==true`; thử `set` ném `IllegalArgumentException`.
- Mapping `PRIVATE` ghi byte0 thành77 **trong view riêng**, nhưng file byte0 vẫn là10 sau scope.
- Tệp tạm bị xóa ở `finally` khi các mapping/channel đã đóng, không cần biết tên file tạm.

Đây là kết quả theo logic source và các hợp đồng API trên JDK 22+ khi file system/map mode được hỗ trợ. Chưa phải kết quả được xác thực bằng việc chạy trên một OS/JDK thực tế; nếu file system không hỗ trợ mapping hoặc có lỗi I/O, chương trình có thể throw thay vì in đầy đủ. Ví dụ tránh in `isLoaded()` vì đó là gợi ý phụ thuộc hệ điều hành, không phải giá trị true/false xác định.

### 6.3. Vì sao ví dụ không dùng `FileChannel.force(true)`?

`FileChannel.force(boolean metaData)` là API flush của **channel**; `MemorySegment.force()` là API liên quan **mapped segment**. Cả hai đều có mục đích thúc đẩy ghi xuống storage trong tình huống phù hợp, nhưng khác đối tượng nhận lệnh và chi tiết hợp đồng. Sau khi FileChannel đã đóng, muốn flush những bytes vừa thay qua mapping `READ_WRITE` vẫn có thể gọi `mapped.force()` khi arena còn sống. Đừng hiểu `FileChannel.close()` là thao tác đồng bộ dữ liệu mapped tương đương `mapped.force()`.

## 7. Các phương thức chuyên biệt của mapped MemorySegment

| Method | Vai trò | Giới hạn |
| --- | --- | --- |
| `isMapped()` | Phân biệt segment mapped với segment native thông thường | Boolean mô tả loại segment, không chứng minh file vẫn không bị truncate |
| `isNative()` | Xác nhận segment được backing ngoài Java heap | Mapped segment là native segment, nhưng không phải mọi native segment là mapped |
| `isReadOnly()` | Kiểm tra view không cho Java ghi | Chỉ nói về quyền viết Java access qua view |
| `byteSize()` | Số byte trong region mapping | Không có nghĩa dữ liệu hiện đang resident trong RAM |
| `get/set(...)` | Đọc/ghi từng giá trị theo layout | Bounds, scope, thread, alignment; file có thể bị chỉnh từ bên ngoài |
| `asSlice(offset,size)` | Chia view theo byte offsets | Vẫn cùng backing mapping/arena |
| `asByteBuffer()` | Tạo ByteBuffer view để dùng NIO API cũ | Giới hạn capacity dạng int; cùng lifetime và readonly semantics tương ứng |
| `force()` | Ghi thay đổi của mapped `READ_WRITE` ra storage | Không có hiệu quả với `READ_ONLY`/`PRIVATE`; remote FS không có cùng bảo đảm |
| `load()` | Best-effort đưa mapped pages vào physical memory | Có thể gây page faults/I/O; không khóa pages vĩnh viễn |
| `isLoaded()` | Gợi ý mức độ resident của mapped pages | true/false không là cam kết dài hạn |
| `unload()` | Best-effort gợi ý OS đẩy contents khỏi physical memory | **Không** hủy mapping, không làm segment hết hiệu lực |

`load()`, `isLoaded()` và `unload()` chỉ hoạt động với mapped segments; với segment không mapped, chúng có thể ném `UnsupportedOperationException`. `unload()` không đồng nghĩa `Arena.close()`: sau `unload` bạn vẫn có một mapped segment hợp lệ và lần đọc tiếp có thể page fault nạp lại dữ liệu. **Chỉ scope/arena close mới xác định hết lifetime theo protocol của ví dụ.**

### 7.1. `force()` không phải transaction/lock

Giả sử bạn cập nhật 100 bytes ở hai vị trí khác nhau rồi gọi `force`. Nếu một reader khác đồng thời đọc file, nó không tự động nhìn thấy cả hai cập nhật trong một snapshot nguyên tử. `force` cũng không giải quyết sự cố tệp bị truncate hoặc các tiến trình khác ghi vào vùng mapping. Nếu ứng dụng cần tính nguyên tử của một record update, phải thiết kế protocol: journal/WAL, versioned record, checksums, file locks/coordination, hoặc write-rename strategy phù hợp filesystem.

### 7.2. `isLoaded()` không phải thước đo RAM chính xác

Một giá trị `true` nói rằng phần lớn nội dung có khả năng đã resident ở thời điểm hỏi; OS có thể page out ngay sau đó. `false` không chứng minh lần đọc tiếp chắc chắn phải I/O; hệ thống có nhiều tầng cache. Không nên viết unit test `assert(isLoaded())` sau `load()` hoặc dùng nó làm tiêu chí “mapping thành công”.

## 8. Kiểm tra offset, size, file length và overflow

`map` nhận `offset` và `size` là `long`. Hợp đồng JDK 22 yêu cầu:

~~~text
offset >= 0
size   >= 0
offset + size không overflow long
channel có quyền tương thích với MapMode
arena còn sống và thread được phép dùng
~~~

Ngoài các điều kiện API, ứng dụng nên yêu cầu **vùng map nằm trong size hiện tại của file** khi chỉ định đọc một tệp không được chỉnh sửa:

~~~java
// Mảnh minh họa kiểm tra một vùng [offset,offset+size)
// với fileSize từ channel.size().
static void checkRegion(long fileSize, long offset, long size) {
    if (offset < 0 || size < 0 ||
            offset > fileSize || size > fileSize - offset) {
        throw new IllegalArgumentException("invalid file region");
    }
}
~~~

Cách `size > fileSize - offset` tránh cộng `offset+size` trước khi kiểm tra, nên không gây overflow. Vùng rỗng `offset==fileSize,size==0` hợp lệ về logic slice; với file rỗng hãy xử lý không đọc phần tử và kiểm tra khả năng provider/OS tạo 0-byte mapping nếu thật sự gọi API.

### 8.1. Lỗi thường gặp: map vượt EOF rồi dựa vào auto-extension

Overload map có một số chi tiết phụ thuộc OS/file provider; tài liệu cảnh báo hành vi khi vùng được map không hoàn toàn nằm trong file không có contract portable mong muốn. Không map đến một vị trí lớn hơn file size rồi trông chờ file sẽ luôn tự mở rộng “đúng và an toàn”. Nếu muốn tạo tệp có kích thước mong muốn, **chủ động tạo/đặt size bằng I/O hợp lệ**, xác minh kích thước rồi mới map. Đừng tự gọi `FileChannel.truncate(newLargerSize)` để mở rộng: `truncate` theo contract không tăng kích thước file nếu tham số lớn hơn size hiện tại.

Một cách chuẩn tạo tệp dữ liệu cố định là ghi đủ bytes theo format, dùng `FileChannel.write(...)` ở vị trí thích hợp (kiểm tra số bytes thật sự ghi), hoặc thao tác resize được file provider hỗ trợ; kiểm tra `channel.size()` rồi mới map. Trong demo, `Files.write` tạo chính xác tám bytes, vì vậy ta không dựa vào semantics mở rộng ngoài EOF.

### 8.2. Chia tệp lớn thành các cửa sổ mapping

Với tệp nhiều GB, tạo một mapping lớn có thể hợp lý trên JVM 64-bit nhưng cũng có thể thất bại vì giới hạn address space hoặc resource mapping. Cách quản lý đơn giản là map từng cửa sổ:

~~~java
// Mảnh Java minh họa, không phải chương trình độc lập:
long fileSize = channel.size();
long windowSize = 64L * 1024L * 1024L; // 64 MiB
for (long offset = 0; offset < fileSize; ) {
    long n = Math.min(windowSize, fileSize - offset);
    try (Arena windowArena = Arena.ofConfined()) {
        MemorySegment window = channel.map(
                FileChannel.MapMode.READ_ONLY, offset, n, windowArena);
        // Xử lý [offset, offset+n) rồi thôi dùng window.
    }
    offset += n; // n>0 khi offset<fileSize và windowSize>0.
}
~~~

Trong binary format có record chạy qua ranh giới hai cửa sổ, phải giữ lại phần overlap/partial record theo thiết kế. Đừng giả định có thể tăng offset bằng mọi số mà không tính record alignment, encoding UTF-8 split-point hoặc checksum region. Với processing đồng thời, không chia sẻ confined `windowArena` cho thread khác; dùng riêng arena mỗi thread hoặc shared arena với synchronization.

## 9. Tệp bị sửa, truncate, thay thế hoặc xóa khi còn mapped

Đây là phần nguy hiểm nhất của memory mapping. Một mapped segment có `byteSize()==N` và scope alive **chỉ chứng minh Java access nằm trong vùng được mô tả**. Nó không chứng minh tệp backing trên storage còn đủ N bytes hoặc OS vẫn cho phép truy cập toàn bộ mapping.

Tài liệu `FileChannel.map(...,Arena)` JDK 22 nêu rõ:

- Content của mapped segment **có thể thay đổi bất cứ lúc nào** nếu file tương ứng bị chương trình khác sửa; khi nào nhìn thấy thay đổi là **phụ thuộc OS**, không có promise nhất quán cross-process.
- Tất cả hoặc một phần vùng mapped **có thể trở nên không truy cập được** nếu file backing bị truncate.
- Khi truy cập vùng bị mất hiệu lực, có thể xảy ra **unspecified exception** tại thời điểm access hoặc sau đó. Không thể dựa vào một loại Java exception cố định để recovery.
- Do vậy nên có protocol tránh thao tác thay đổi kích thước/file backing bởi chương trình khác trong thời gian mapping được dùng.

Trên Unix-like OS, file truncation có thể khiến truy cập page không tồn tại dẫn tới tín hiệu như `SIGBUS`, nhưng **không** tuyên bố mọi JVM/OS sẽ luôn xảy ra cùng một tín hiệu. Một lỗi OS-level mapping có thể nghiêm trọng hơn Java `IndexOutOfBoundsException`, nên không chủ động viết test dereference vùng đã truncate để “xem lỗi gì”.

### 9.1. Chiến lược an toàn cho concurrent file ownership

- Dùng file immutable trong suốt thời gian reader map; tạo file mới và chuyển con trỏ/tên một cách có protocol nếu cần cập nhật version.
- Với mutable file, quy định writer/reader coordination, tránh truncate trong lúc mapped readers active.
- Nếu cần lock cross-process, nghiên cứu `FileChannel.lock`/`tryLock` và filesystem/platform semantics, nhưng nhớ **file locks thường thuộc JVM/process**, không tự bảo vệ accesses giữa các threads Java trong cùng JVM.
- Một thứ tự đóng tốt: ngừng tạo readers/writers mới → chờ in-flight memory accesses → flush nếu `READ_WRITE` → đóng arena/unmap → đóng channel (nếu còn mở) → rename/truncate/delete theo quy trình.
- Kiểm tra lỗi I/O và bảo đảm lock release cả khi exception. Từng file system có đặc điểm riêng; mapped file trên network share có rủi ro consistency cao hơn local disk.

### 9.2. Xóa tệp trên Windows và Unix khác nhau

Mapped regions có thể giữ OS handles/section objects ngay cả khi `FileChannel` đã đóng. Một số file systems/OS (đặc biệt Windows) hạn chế xóa/rename tệp khi mapping còn tồn tại, trong khi Unix có thể cho unlink tên file mà mapping vẫn truy cập backing object. Không thiết kế một API giả định mọi platform cho phép xóa mapped file ngay lập tức. **Đóng Arena một cách xác định** trước khi xóa file tạm là lựa chọn portable hơn so với chờ GC của `MappedByteBuffer`.

## 10. Memory mapping và performance: khi nào có lợi?

Memory mapping không phải lời giải mặc định cho mọi tệp.

| Workload | Mapping thường hữu ích? | Lý do/cân nhắc |
| --- | --- | --- |
| Tệp lớn, random reads lặp lại | Thường có | OS page cache và address-based access |
| Chỉ đọc một header vài KB | Có thể không | Overhead tạo mapping/page faults có thể nhiều hơn `Files.readAllBytes` |
| Xử lý sequential một lần | Tùy workload | `FileChannel.read` với buffer lớn có thể đơn giản/nhanh tương đương |
| Nhiều records cần view theo byte offsets | Có | `MemorySegment.asSlice` và layout-based access |
| Dữ liệu multi-GB > ByteBuffer capacity | Có thể có | `MemorySegment` dùng long; vẫn phụ thuộc virtual memory/OS |
| File thường xuyên truncate/rewrite | Rủi ro cao | Segments có thể mất backing/cross-process coherence |
| Ánh xạ private để thử sửa tạm | Có | `PRIVATE` copy-on-write, không persist |
| Cần transaction/power-loss atomicity | Không đủ | `force` không thay WAL/transaction protocol |
| Nhiều threads cùng sửa record | Cần thiết kế thêm | Arena/shared access ≠ lock/atomicity |

Thời gian truy cập có thể bị chi phối bởi page faults, storage latency, paging pressure, block size và access pattern hơn là overhead gọi `get`. Trên một số OS, tạo mapping cho tệp rất nhỏ có thể tốn hơn `read`. Hãy đo **benchmark thực tế** với representative file sizes, cache nóng/lạnh, random/sequential patterns, concurrent access, flush cost và cleanup/unmap.

`load()` có thể giúp giảm faults trong một số tình huống nhưng cũng có thể lãng phí RAM hoặc chặn vì I/O; `isLoaded()` chỉ cho hint. Không in/load trước toàn bộ nhiều GB nếu ứng dụng chỉ cần một vài records.

## 11. Các dạng lỗi phổ biến và chẩn đoán

| Anti-pattern | Vấn đề | Cách sửa |
| --- | --- | --- |
| Dùng `FileChannel.map(mode,pos,size)` ba tham số rồi chờ nhận `MemorySegment` | Overload cũ trả `MappedByteBuffer` | Dùng overload **bốn** tham số có `Arena` (JDK22+) |
| Chạy `java.lang.foreign` code trên JDK17 | Java 17 chỉ có API incubator khác | Dùng JDK22+ cho source final |
| Dùng `READ_WRITE` nhưng channel chỉ mở `READ` | Không có quyền ghi tương ứng | Mở `READ` + `WRITE`, có thể nhận `NonWritableChannelException` |
| Dùng `READ_ONLY` rồi gọi `set` | Segment read-only | Chỉ đọc hoặc map `READ_WRITE` nếu có quyền |
| Dùng `PRIVATE` mong tệp được cập nhật | Copy-on-write không persist | Dùng `READ_WRITE` và `force` |
| Tưởng `channel.close()` tự làm `mapped` invalid | Mapping sống theo arena | Dừng users và `arena.close()` |
| Tưởng `arena.close()` sẽ tự gọi `FileChannel.close()` | Hai resource owners riêng | Đóng cả channel và arena |
| Đọc sau `arena.close()` | Segment scope đã đóng | Trả bản copy ra ngoài scope nếu cần dữ liệu sau đó |
| Dùng `Arena.ofConfined()` qua thread khác | Wrong-thread access | Owner thread hoặc `Arena.ofShared()` và đồng bộ |
| Gọi `unload()` để giải phóng mapping | `unload` chỉ best-effort pages | Dùng `arena.close()` để unmap |
| Coi `isLoaded()==true` là toàn bộ tệp “pinned” | OS có thể page out bất kỳ lúc nào | Chỉ xem là hint |
| Gọi `force` rồi nghĩ có transaction | Flush ≠ atomicity/locking | Thêm journal/version/checksum protocol |
| Map vượt EOF và trông chờ file tự giãn ra | Hành vi phụ thuộc OS/provider | Ghi/resize file trước, xác minh size |
| Gọi `truncate(larger)` để tăng file size | truncate không tự mở rộng | Dùng write/resize được provider hỗ trợ |
| Truncate file khi thread khác còn đọc mapping | Vùng mapped trở nên inaccessible | Freeze size hoặc stop/unmap trước |
| Đọc `JAVA_INT` ở byte offset1 | Misalignment nếu format packed | Dùng `JAVA_INT_UNALIGNED` đúng format |
| Đọc file network-order bằng native-order | Sai byte order | `withOrder(BIG_ENDIAN)`/format layout |
| Sai đơn vị: offset record thay vì byte | Mapping hoặc access sai vị trí | `recordIndex*stride` kèm overflow checks |
| `asSlice` rồi giữ sau scope | Slice chia lifetime với parent | Copy bytes nếu cần sống lâu hơn |
| Cho rằng mapped segment chỉ có 2 GB max | Nhầm với ByteBuffer overload | Segment API size là long; vẫn xem OS limits |
| Cho rằng mapping luôn nhanh hơn file read | Overhead/IO pattern khác nhau | Benchmark workload thực |
| Xóa mapped temp file trước close Arena trên Windows | OS file handle/mapping còn giữ | Unmap trước rồi xóa |

### 11.1. Nhóm exception thường gặp

- `IllegalArgumentException`: `offset`/`size` không hợp lệ hoặc cộng overflow khi tạo mapping; hoặc ghi vào read-only segment; hoặc layout không tương thích alignment.
- `IndexOutOfBoundsException`: `get/set` vào offset vượt `mapped.byteSize()`.
- `IllegalStateException`: dùng segment có arena đã đóng hoặc map với arena không alive.
- `WrongThreadException`: dùng confined arena/segment từ thread không sở hữu.
- `NonReadableChannelException`/`NonWritableChannelException`: channel không có quyền phù hợp `MapMode`.
- `UnsupportedOperationException`: provider không hỗ trợ mapping/mode; `force/load` trên một segment không mapped cũng có thể bị từ chối.
- `IOException`/`UncheckedIOException`: lỗi I/O ở giai đoạn map hoặc force/flush.
- **Mapped backing inaccessible** do file bị truncate: đặc tả cho phép lỗi **không xác định** khi truy cập, không hứa một exception có thể bắt và hồi phục dễ dàng.

Phân biệt lỗi Java bounds/scope với lỗi backing file: dù bạn chứng minh mọi offset hợp lệ, external file mutation vẫn có thể phá vỡ khả năng truy cập ở OS layer.

## 12. Thiết kế wrapper sở hữu mapping đúng cách

Một ứng dụng production nên có đối tượng owner:

~~~text
MappedFile (AutoCloseable)
  |
  +-- FileChannel channel (được mở theo mode)
  +-- Arena arena = Arena.ofConfined()/ofShared()
  +-- MemorySegment region = channel.map(...,arena)
  +-- fixed file size/version contract
  +-- active-access counter/lock nếu đa thread
  |
  +-- read/write methods kiểm tra owner state
  +-- flush() gọi region.force() khi READ_WRITE
  +-- close():
        stop accepting new readers/writers
        wait for in-flight accesses
        flush if durability required
        arena.close() (unmap)
        channel.close()
~~~

Đây là **sơ đồ API**, không phải full Java source. Nếu wrapper phục vụ đa thread, `Arena.ofConfined()` không phù hợp nếu threads khác trực tiếp truy cập. Với `Arena.ofShared()`, bản thân việc tạo shared scope không làm accesses atomic; dùng synchronization hoặc immutable design và đảm bảo close không race với một access đang diễn ra.

Quy tắc `AutoCloseable`:

- Chỉ một owner có quyền đóng arena mapping; tránh double-close.
- Không đưa raw `MemorySegment` ra ngoài trừ khi caller đồng ý với scope và kiểm soát lifetime.
- `close()` nên idempotent ở wrapper, nhưng không đồng nghĩa `Arena.close()` được gọi tùy ý nhiều lần.
- Nếu flush thất bại, cần báo lỗi cho caller, đồng thời vẫn xử lý cleanup resource trong `finally`. Đừng âm thầm bỏ lỗi vì thao tác ghi dữ liệu có thể chưa durable.
- Nếu muốn copy dữ liệu cho caller giữ sau close, copy sang `byte[]` hoặc một segment có scope khác **trước** khi đóng owner.
- Xác định rõ tương tác với file locks, locks nội bộ JVM và shared memory giữa processes; không dùng `force()` làm primitive đồng bộ.

## 13. Bài tập có đáp án ngắn

1. `FileChannel.map(READ_ONLY,100,20,arena)` trả segment size bao nhiêu? **20 bytes**. `segment.get(JAVA_BYTE,0)` đọc file byte nào? **byte100**.
2. Đóng channel nhưng không đóng arena: mapped segment còn dùng được không? **Có**, nếu backing file vẫn hợp lệ, scope alive và caller đúng thread.
3. Đóng `Arena.ofConfined()` rồi dùng `get`: exception nào thường có? **IllegalStateException**.
4. Có thể dùng `Arena.ofConfined()` từ worker thread khác không? **Không**, trừ khi access được thực hiện trên owner thread; nếu cần multi-thread, thiết kế `Arena.ofShared()`/locking.
5. Mapping `READ_ONLY` với channel `READ` rồi gọi `set` có hợp lệ? **Không**; segment read-only.
6. Mapping `READ_WRITE` cần mở channel theo options nào? **READ + WRITE**.
7. Mapping `PRIVATE` ghi byte99 rồi `force`: file byte có thay đổi không? **Không** từ private writes theo contract copy-on-write.
8. `mapped.isLoaded()==true` có bảo đảm không page fault ở lần đọc sau không? **Không**, chỉ là hint.
9. `mapped.unload()` có phải unmap và làm `get` bị từ chối? **Không**; chỉ best-effort OS resident pages.
10. File dài 100 byte, map `offset=90,size=20` có phải một yêu cầu đọc đúng trong file không? **Không**: vượt EOF. Application nên từ chối dù provider có thể hành xử khác.
11. File dài 100 byte, `offset=100,size=0` là slice hợp lệ theo số học? **Có**; nhưng không truy cập phần tử nào và cần xét hỗ trợ map rỗng.
12. `offset=Long.MAX_VALUE-3,size=8` có được phép? **Không** vì cộng overflow; kiểm tra `size > fileSize-offset` khi đã biết bounds.
13. Tại sao `mapped.get(JAVA_INT,1)` có thể lỗi dù file còn 100 byte? **Alignment** hoặc format packed; chọn layout đúng.
14. Nếu hai processes cùng sửa file backing, `MemorySegment` có bảo đảm snapshot nhất quán không? **Không**, timing/coherence phụ thuộc OS.
15. Cần xóa temp file trên Windows, nên đóng gì trước? **Arena/unmap và FileChannel**.
16. Tệp 6 GB có thể dùng một `MappedByteBuffer` với capacity 6 GB không? **Không** theo overload ByteBuffer truyền thống; dùng MemorySegment long size nếu platform hỗ trợ, hoặc nhiều windows.

## 14. Checklist triển khai ánh xạ tệp thành MemorySegment

- [ ] **JDK:** Build/run dùng Java 22+ để có `FileChannel.map(MapMode,long,long,Arena)` final?
- [ ] **Đúng overload:** Bốn tham số với `Arena` trả `MemorySegment`, không nhầm với `MappedByteBuffer`?
- [ ] **Mode:** `READ_ONLY/READ_WRITE/PRIVATE` phù hợp quyền của channel, đúng semantics cần persist?
- [ ] **Region:** `offset`/`size` tính theo **byte**, không âm, không overflow; region không vượt file size theo contract ứng dụng?
- [ ] **Empty:** Nếu file/slice rỗng, đã xử lý riêng không dereference phần tử 0?
- [ ] **Owner:** Có đóng cả `FileChannel` và `Arena`; không trông vào GC hoặc `channel.close()` để unmap?
- [ ] **Scope:** Mọi views/slices/ByteBuffers không bị dùng sau `Arena.close()`?
- [ ] **Threads:** Confined/shared arena phù hợp và không có close-while-access races?
- [ ] **Formats:** Đọc/ghi ValueLayout đúng size, alignment, byte order và file version; không tự coi file bytes là Java objects?
- [ ] **Durability:** Với `READ_WRITE` có `force()` khi cần flush; hiểu giới hạn remote FS, transaction và crash consistency?
- [ ] **Private:** Không dựa vào `PRIVATE` để persist; biết nó là copy-on-write?
- [ ] **Resident:** `load/isLoaded/unload` chỉ là best-effort/hint, không phải lock pages hay unmap?
- [ ] **Backing file:** Có protocol tránh external truncate/rename/delete trong thời gian mapping đang hoạt động?
- [ ] **Large files:** Có xét virtual address space, OS quota, windowing, record split và ByteBuffer int limits?
- [ ] **Error handling:** Bắt đúng nhóm `IOException`, permission/mode, scope, thread, bounds và unsupported provider; không trông vào exception cố định khi file bị truncate?
- [ ] **Verification:** Đã chạy integration tests trên OS/filesystem thực tế, bao gồm READ_ONLY, READ_WRITE+force, PRIVATE, channel.close-before-arena.close, scope-after-close và file cleanup?

**Kết luận:** Với JDK 22+, `FileChannel.map(MapMode,offset,size,Arena)` nối **tệp** với **MemorySegment** theo một scope do ứng dụng kiểm soát. `FileChannel` cho quyền I/O; `MapMode` xác định đọc/ghi/copy-on-write; `MemorySegment` mang spatial bounds và access API; `Arena` quyết định thời hạn mapping. Thiết kế đúng cần kết hợp cả bốn, dùng `force` khi có yêu cầu durability, và không để external file mutation hoặc concurrency phá vỡ vùng backing.

### Tài liệu tham khảo chính thức

- Oracle, [Java 22 FileChannel](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): overload `map(MapMode,long,long,Arena)` từ JDK22, quyền mode, lifecycle, backing file modifications và errors.
- Oracle, [Java 22 FileChannel.MapMode](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): `READ_ONLY`, `READ_WRITE`, `PRIVATE`.
- Oracle, [Java 22 MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `isMapped`, `force`, `load`, `isLoaded`, `unload`, `get/set`, `asSlice` và scope checks.
- Oracle, [Java 22 Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared/auto/global arenas, scope lifetime.
- Oracle, [Java 22 ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): byte size, alignment, byte order khi đọc/ghi binary.
- OpenJDK, [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM final từ JDK22 và mô hình memory segments.
- Oracle, [Java 22 StandardOpenOption](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/file/StandardOpenOption.html): `READ`/`WRITE`, tạo/mở tệp.