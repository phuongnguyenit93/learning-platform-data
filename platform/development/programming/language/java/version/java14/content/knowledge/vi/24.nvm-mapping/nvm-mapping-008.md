# UnsupportedOperationException khi nhà cung cấp không hỗ trợ ánh xạ NVM

## 1. Mục tiêu bài học

Khi ánh xạ một file vào bộ nhớ bằng `FileChannel.map(...)`, Java hỗ trợ các chế độ thông thường như `READ_ONLY`, `READ_WRITE` và `PRIVATE`. Từ Java 14, JDK còn cung cấp **hai chế độ dành cho ánh xạ bộ nhớ không mất dữ liệu khi mất điện (NVM/persistent memory)**:

- `ExtendedMapMode.READ_ONLY_SYNC`
- `ExtendedMapMode.READ_WRITE_SYNC`

Tuy nhiên, **có API không đồng nghĩa nền tảng nào cũng thực hiện được**. Nếu `FileChannel` implementation hoặc file-system provider **không hỗ trợ map mode được yêu cầu**, `map(...)` có thể ném **`UnsupportedOperationException`**. Một ứng dụng chạy tốt trên Linux có cấu hình persistent memory thích hợp vẫn có thể gặp lỗi trên Windows, macOS, file system không hỗ trợ, hoặc một provider Java khác.

Bài này giải thích **đúng trường hợp nhà cung cấp không hỗ trợ**:
1. `UnsupportedOperationException` xảy ra ở đâu, có nghĩa chính xác là gì?
2. Phân biệt **không hỗ trợ map mode** với **lỗi I/O**, **không đủ quyền đọc/ghi**, **tham số sai** và **thiếu module JDK**.
3. Vì sao `READ_WRITE_SYNC` khác `READ_WRITE` và không nên âm thầm thay thế trong hệ thống yêu cầu semantics của persistent memory.
4. Thiết kế chính sách **fail fast** hoặc **fallback có chủ đích**.
5. Dùng Java 17+ biên dịch/chạy một chương trình thực tế; ở môi trường không hỗ trợ NVM, quan sát lỗi, fallback và kiểm chứng dữ liệu.
6. Viết test an toàn, logs hữu ích và cấu hình triển khai tương thích.

**Giới hạn phiên bản:** `jdk.nio.mapmode.ExtendedMapMode` được bổ sung từ **Java 14** và vẫn có trong **JDK 25** theo tài liệu Oracle hiện hành. Bài học chỉ sử dụng API còn áp dụng hiện nay, không dùng API preview, thư viện pmem cũ hoặc cách triển khai legacy.

## 2. NVM là gì, và “map” không đồng nghĩa “tự động bền vững”

**NVM (*non-volatile memory*)** là bộ nhớ có khả năng giữ dữ liệu khi mất điện, khác với DRAM truyền thống. Một số cấu hình **persistent memory** có thể được hệ điều hành cung cấp thông qua **file-backed, direct-access mappings**, ví dụ trên Linux với file system hỗ trợ các cơ chế DAX thích hợp.

Các tầng liên quan:

~~~text
Code Java
   |
   | FileChannel.map(mode, position, size)
   v
FileChannel implementation / FileSystemProvider
   |
   | NIO mapping implementation
   v
Operating system memory mapping (mmap, file mappings...)
   |
   v
File system + device + memory/persistence capabilities
   |
   v
ByteBuffer / MappedByteBuffer mà Java thao tác
~~~

**Điểm quan trọng:** Sử dụng `MappedByteBuffer` không tự chứng minh file đang nằm trên **NVM**; một ánh xạ thông thường tới SSD/HDD cũng trả về `MappedByteBuffer`. Các mode `*_SYNC` chỉ có ý nghĩa khi nền tảng hỗ trợ cách ánh xạ và persist phù hợp.

Ngay cả với persistent-memory mapping thành công, việc ghi nhiều field liên quan **không tự động tạo transaction nguyên tử**. Một giao thức lưu dữ liệu bền vững còn cần xem consistency, ordering, record format, checksums, recovery và thiết kế tránh ghi dở khi crash.

### 2.1. Một số thuật ngữ

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| **File mapping** | Ánh xạ một vùng của file vào không gian địa chỉ tiến trình để truy cập bằng buffer |
| **MappedByteBuffer** | Buffer được tạo bởi `FileChannel.map`, thao tác với nội dung ánh xạ |
| **MapMode** | Chế độ ánh xạ, quyết định chỉ đọc/đọc ghi/copy-on-write/extended sync |
| **NVM / PMem** | Bộ nhớ không mất dữ liệu; một hệ thống có thể phơi bày dưới dạng file mapping phù hợp |
| **DAX** | Cơ chế cho phép truy cập dữ liệu file-backed trực tiếp theo khả năng thiết bị/file system |
| **Provider/implementation** | Thành phần Java và nền tảng thực hiện `FileChannel`/file-system mapping |
| **Fallback** | Sử dụng chế độ khác khi chế độ ưu tiên không khả dụng, **chỉ khi yêu cầu ứng dụng cho phép** |
| **Durability** | Đảm bảo dữ liệu đã ghi tồn tại sau sự cố theo phạm vi/điều kiện đã định nghĩa |

## 3. Các map mode cần phân biệt

### 3.1. Những mode tiêu chuẩn

`FileChannel.MapMode` cung cấp:

~~~java
FileChannel.MapMode.READ_ONLY
FileChannel.MapMode.READ_WRITE
FileChannel.MapMode.PRIVATE
~~~

| Mode | Cách hiểu | Tác động đến file |
| --- | --- | --- |
| `READ_ONLY` | Ánh xạ để đọc; không được viết qua buffer | Không thay đổi file từ mapped buffer |
| `READ_WRITE` | Ánh xạ cho đọc/ghi | Các thay đổi có thể được phản ánh lên file; `force()` dùng khi cần đẩy thay đổi xuống lưu trữ |
| `PRIVATE` | Ánh xạ private, copy-on-write | Thay đổi trong buffer **không được ghi ngược về file** theo hợp đồng |

**Không dùng `PRIVATE` như một “fallback an toàn” cho `READ_WRITE_SYNC`** nếu bạn cần ghi dữ liệu bền vững: copy-on-write mapping **không đáp ứng yêu cầu đó**.

### 3.2. Những mode NVM do JDK mở rộng

Class:

~~~java
import jdk.nio.mapmode.ExtendedMapMode;
~~~

cung cấp:

~~~java
ExtendedMapMode.READ_ONLY_SYNC
ExtendedMapMode.READ_WRITE_SYNC
~~~

Hai field này có **kiểu `FileChannel.MapMode`**, nên có thể truyền trực tiếp cho:

~~~java
MappedByteBuffer buffer = channel.map(mode, position, size);
~~~

Khác biệt:

- **`READ_ONLY_SYNC`**: ánh xạ read-only dành cho file backed by non-volatile RAM. Không cho phép sửa buffer và không nên dùng `force()` để giả định phát sinh ghi.
- **`READ_WRITE_SYNC`**: ánh xạ read/write cho NVM; theo ghi chú triển khai Oracle, thao tác `force()` trên buffer tạo bởi mode này có thể sử dụng **cache-line writeback** thay vì cơ chế file device flush của ánh xạ thông thường.
- **`READ_WRITE`**: mode tiêu chuẩn trên những file/môi trường hỗ trợ; **không xác lập rằng thiết bị là NVM hoặc ứng dụng đang sử dụng persistent-memory mapping với semantics của SYNC mode**.

Với Linux, tài liệu triển khai của `ExtendedMapMode` nêu `mmap` sử dụng các cờ **`MAP_SHARED_VALIDATE`** và **`MAP_SYNC`** cho hai mode SYNC. Đây là **chi tiết của triển khai Linux**, không phải quy tắc API Java yêu cầu mọi hệ điều hành đều có những cờ đó.

## 4. Tại sao `UnsupportedOperationException` xuất hiện?

Tài liệu Oracle của `ExtendedMapMode` ghi rõ ý nghĩa:

> Khi một implementation không hỗ trợ map mode SYNC được yêu cầu, phương thức map ném `UnsupportedOperationException`.

Điều kiện có thể là JVM/OS không triển khai mode đó, hoặc đối tượng `FileChannel` đến từ một provider không nhận dạng/hỗ trợ yêu cầu mapping.

Ví dụ:

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    MappedByteBuffer mapped =
            channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);
}
~~~

**Đây là snippet minh họa**, cần import tương ứng và `path` là một file hợp lệ. Trong một môi trường không hỗ trợ mode SYNC, lệnh `channel.map(...)` có thể ném `UnsupportedOperationException` ngay cả khi:
- File tồn tại.
- Mở file để đọc/ghi thành công.
- Ánh xạ cùng file bằng `FileChannel.MapMode.READ_WRITE` vẫn thành công.

**Vì thế lỗi này không mặc nhiên chứng minh file bị hỏng**; nó có thể chỉ báo chế độ ánh xạ **không được implementation hỗ trợ**.

### 4.1. Phải xác định lỗi xảy ra tại bước nào

~~~text
FileChannel.open(path, READ, WRITE)
     |
     +-- lỗi mở channel: IOException / security / unsupported options...
     |
     v
channel.map(READ_WRITE_SYNC, 0, SIZE)
     |
     +-- UnsupportedOperationException
     |      -> implementation không hỗ trợ map mode được yêu cầu
     |
     +-- IOException
     |      -> lỗi I/O hoặc điều kiện OS/file system không đáp ứng
     |
     +-- NonWritableChannelException / NonReadableChannelException
     |      -> channel không được mở với quyền phù hợp
     |
     +-- IllegalArgumentException
     |      -> position, size, overflow hoặc tiền điều kiện sai
     |
     v
MappedByteBuffer thành công
     |
     v
get/put/force...
~~~

Không nên viết một `try/catch` quá rộng rồi quy mọi exception ở `FileChannel.open`, `map` hoặc `force` thành “máy không có NVM”.

### 4.2. Vai trò của file-system provider

`FileChannel.open(path, ...)` sử dụng provider liên quan đến `Path`. Có những provider:
- Không hỗ trợ **tạo FileChannel** theo open options đã yêu cầu.
- Hỗ trợ FileChannel nhưng chỉ triển khai các **map modes thông thường**.
- Có thể hỗ trợ SYNC mode khi OS/file system cho phép.
- Có behavior khác nhau đối với yêu cầu SYNC trên từng thiết bị cụ thể.

**Vùng bắt lỗi có ý nghĩa:** Nếu bạn muốn xác định “SYNC mode bị từ chối”, hãy đặt `catch (UnsupportedOperationException)` **sát riêng lệnh `map(SYNC, ...)`**; đừng đặt catch quanh toàn bộ quá trình tạo channel rồi thông báo sai nguồn lỗi.

## 5. Phân biệt `UnsupportedOperationException` với `IOException`

Một điểm rất quan trọng trong thực tế:

**`UnsupportedOperationException`** thể hiện **map mode không được implementation hỗ trợ** theo hợp đồng API. Nhưng **không phải mọi ánh xạ NVM thất bại đều phải ném UOE**.

Ví dụ: Trên Linux có hỗ trợ map mode SYNC nhưng file nằm trên một file system **không có khả năng DAX/MAP_SYNC phù hợp**, thao tác ánh xạ có thể thất bại bằng **`IOException`** mang thông báo từ OS như “Operation not supported”.

Vì vậy cần phân biệt:

| Lỗi hoặc dấu hiệu | Giai đoạn thường gặp | Diễn giải phù hợp | Cách xử lý |
| --- | --- | --- | --- |
| `UnsupportedOperationException` trong `map(READ_WRITE_SYNC,...)` | Mapping | Implementation không hỗ trợ map mode yêu cầu | Áp dụng **chính sách strict hoặc fallback** |
| `IOException` trong `map(...)` | Mapping | Hệ điều hành/file system/device gặp lỗi hoặc không đáp ứng điều kiện mapping | Log cause và chẩn đoán file system/thiết bị; không tự coi mọi IOException là unsupported |
| `IOException` trong `FileChannel.open(...)` | Mở file | Không thể mở tệp, quyền, đường dẫn hoặc lỗi I/O | Sửa nguồn/permissions trước khi map |
| `NonWritableChannelException` | Mapping read/write với channel thiếu quyền ghi | Cách mở channel không đáp ứng mode yêu cầu | Mở channel đúng `READ + WRITE` nếu được phép |
| `NonReadableChannelException` | Mapping cần đọc với channel thiếu quyền đọc | Quyền mở channel chưa đúng | Thêm `READ` khi thích hợp |
| `IllegalArgumentException` | Mapping | Offset/size âm, tràn hoặc tiền điều kiện sai | Kiểm tra tham số; không fallback để che lỗi |
| `ReadOnlyBufferException` | Ghi vào read-only mapped buffer | Ứng dụng dùng buffer sai quyền | Sửa logic ghi hoặc mode phù hợp |
| `UncheckedIOException` tại `MappedByteBuffer.force()` | Đẩy dữ liệu xuống storage | Lỗi I/O khi force | Báo persistence failure, không giả vờ đã commit |
| `OutOfMemoryError` / giới hạn địa chỉ | Mapping hay hoạt động ứng dụng | Không đủ resource/address space hoặc giới hạn runtime | Phân tích dung lượng, không suy luận “mode unsupported” |

**Không bắt `Exception` hoặc `RuntimeException` rồi chuyển mặc định sang `READ_WRITE`.** Bạn có thể che lấp lỗi bảo mật, tham số hoặc tình trạng thiết bị, làm ứng dụng tiếp tục trong trạng thái không đảm bảo.

## 6. Hai chính sách hợp lệ: bắt buộc NVM hoặc cho phép fallback

Nhu cầu nghiệp vụ quyết định ứng xử trước lỗi.

### 6.1. Chính sách A — `require-sync`: không cho phép giảm semantics

Một database storage engine hoặc hệ thống đã thiết kế giao thức bền vững **dựa cụ thể vào SYNC mapping** có thể yêu cầu:

- Phải hỗ trợ `READ_WRITE_SYNC`.
- Không được chuyển sang normal mapping khi không có sự chấp thuận.
- Nếu mode không có, **dừng sớm với lỗi rõ ràng**.
- Ghi môi trường, provider/path không nhạy cảm và nguyên nhân, sau đó trả code lỗi triển khai.

Ví dụ:

~~~java
try {
    buffer = channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, size);
} catch (UnsupportedOperationException unsupported) {
    throw new IllegalStateException(
            "Persistent-memory mapping is required; no fallback",
            unsupported);
}
~~~

Đây là snippet bên trong một phương thức đã có `channel`, `buffer` và `size` phù hợp. Dùng `IllegalStateException` để diễn tả ứng dụng **không đáp ứng yêu cầu triển khai**; vẫn giữ exception gốc làm `cause`.

### 6.2. Chính sách B — `allow-fallback`: tính năng SYNC là tối ưu tùy chọn

Nếu sản phẩm chấp nhận semantics lưu trữ thông thường:

~~~java
MappedByteBuffer buffer;
boolean usedSync;

try {
    buffer = channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, size);
    usedSync = true;
} catch (UnsupportedOperationException unsupported) {
    buffer = channel.map(FileChannel.MapMode.READ_WRITE, 0, size);
    usedSync = false;
}
~~~

**Điều kiện** để thực hiện chính sách này:
- Đường vận hành dự phòng bằng `READ_WRITE` **được thiết kế, kiểm thử và chấp nhận**.
- Các thao tác ghi và `force()` theo hợp đồng regular mapping đủ đáp ứng yêu cầu của ứng dụng.
- Hệ thống ghi log/metrics cho biết **đã dùng fallback**, không giả mạo chế độ SYNC.
- Không coi một phép đọc lại thành công là bằng chứng dữ liệu bền vững trước mất điện.
- Nếu map tiêu chuẩn cũng lỗi, phải **cho lỗi lan ra**; đừng dùng fallback vô tận.

**Đặc biệt:** `READ_WRITE` có thể lưu được dữ liệu file theo quy định của nó, nhất là khi dùng `force()` trên local storage; nhưng **không có nghĩa hai mode có cùng cách flush, độ trễ, đường phần cứng hay hợp đồng persistent-memory**. Nếu cần chính xác SYNC/NVM, chọn **fail fast**.

### 6.3. `IOException` có nên được fallback không?

Không nên mặc định. Một `IOException` có thể là:
- File system báo **không hỗ trợ MAP_SYNC** trên một mount cụ thể.
- Permission/space/file error.
- Sự cố I/O thật có nguy cơ ảnh hưởng dữ liệu.
- Lỗi phía file/device khác.

Chính sách nâng cao có thể **phân loại một mã lỗi platform-specific đã hiểu rõ** và thử normal mapping nếu nghiệp vụ cho phép. Tuy nhiên, API `IOException` thuần Java **không cung cấp một mã lỗi nền tảng có cấu trúc, ổn định cho mọi OS** để có thể nhận diện an toàn mọi trường hợp. Không bắt mọi `IOException` và lặng lẽ chuyển mode; cần logging, test OS cụ thể và quy trình khôi phục.

## 7. Cách dò khả năng hỗ trợ chính xác

**Đừng chỉ kiểm tra tên OS hoặc file có tồn tại.** Những điều này không đủ kết luận SYNC mode được phép cho **chính file đó**.

| Kiểm tra | Giá trị | Hạn chế |
| --- | --- | --- |
| `System.getProperty("os.name")` | Biết họ OS | Không chứng minh một provider/file system hỗ trợ SYNC |
| `Files.exists(path)` | Biết đường dẫn tồn tại tại thời điểm kiểm tra | Không kiểm tra được map mode; có race giữa check và use |
| `FileChannel.open(...)` thành công | Channel có thể mở | Không chứng minh `map(READ_WRITE_SYNC)` thành công |
| `java --list-modules` có `jdk.nio.mapmode` | Module JDK khả dụng | Không chứng minh phần cứng/OS hỗ trợ NVM |
| `map(ExtendedMapMode.READ_WRITE_SYNC, ...)` thành công | **Mode được chấp nhận cho channel/file cụ thể** | Không tự chứng minh giao thức dữ liệu crash-consistent |
| Phép ghi/đọc lại trên buffer | Kiểm tra logic và data path trong môi trường test | Không phải kiểm chứng power-loss durability |

**Cách thực tế:** Thử map trên file ở **đúng thiết bị và file system dự định sử dụng** với kích thước/phạm vi nhỏ, kiểm soát tác động, bắt lỗi đúng chỗ, rồi quyết định theo policy. Không test lên file dữ liệu production đang được ghi bởi một process khác.

### 7.1. Lưu ý sự khác nhau giữa file-system provider và thiết bị

Ngay khi cả hai file đều dùng default provider:
- File A nằm trên một file system DAX phù hợp.
- File B nằm trên một disk/file system thông thường.

Kết quả `map(SYNC)` có thể khác vì **khả năng file system/device**, không chỉ vì Java class của provider. Ngược lại, một custom `FileChannel` implementation có thể không nhận mode mở rộng dù thiết bị phía dưới hỗ trợ.

### 7.2. Vì sao không thể kiểm tra support bằng `MappedByteBuffer.isLoaded()`?

`isLoaded()` chỉ đưa ra một **gợi ý** rằng nội dung buffer có khả năng đang nằm trong physical memory, **không phải API kiểm tra NVM support, durability hay mode của provider**. Không dùng nó để chứng minh mapping SYNC hợp lệ.

## 8. Chương trình Java 17+ hoàn chỉnh: mô phỏng hai chính sách

Ví dụ này:
1. Mở/tạo một file nhỏ để có đối tượng `FileChannel`.
2. Thử `READ_WRITE_SYNC` trước.
3. Nếu `map(SYNC)` bị `UnsupportedOperationException`:
   - Với `require-sync`: ném `IllegalStateException` có cause, **không fallback**.
   - Với `allow-fallback`: dùng `FileChannel.MapMode.READ_WRITE` và ghi rõ điều đó.
4. Ghi số nguyên `2026` qua `MappedByteBuffer` và gọi `force()`.
5. Mở lại file bằng `READ_ONLY` để kiểm tra **giá trị đọc lại**.

Đây là **demo kiểm tra tính đúng của code và fallback policy**, **không phải thí nghiệm mô phỏng mất điện**. Dữ liệu demo không được xem là bằng chứng crash consistency.

**Lưu vào tệp `NvmMapFallbackDemo.java`:**

~~~java
import java.io.IOException;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public final class NvmMapFallbackDemo {
    private static final long SIZE = 16L;
    private static final int VALUE = 2026;

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: NvmMapFallbackDemo <file> <require-sync|allow-fallback>");
        }

        Path path = Path.of(args[0]);
        boolean allowFallback = switch (args[1]) {
            case "require-sync" -> false;
            case "allow-fallback" -> true;
            default -> throw new IllegalArgumentException("Invalid policy");
        };
        System.out.println("Requested mode: READ_WRITE_SYNC");

        boolean usedSync;
        try (FileChannel channel = FileChannel.open(path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            if (channel.size() < SIZE) {
                channel.position(SIZE - 1);
                channel.write(java.nio.ByteBuffer.wrap(new byte[]{0}));
            }

            MappedByteBuffer buffer;
            try {
                buffer = channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, SIZE);
                usedSync = true;
            } catch (UnsupportedOperationException unsupported) {
                System.out.println("SYNC mapping unsupported");
                if (!allowFallback) {
                    throw new IllegalStateException(
                        "Persistent-memory mapping is required; no fallback",
                        unsupported);
                }
                buffer = channel.map(FileChannel.MapMode.READ_WRITE, 0, SIZE);
                usedSync = false;
                System.out.println("Fallback mode: READ_WRITE");
            }

            buffer.order(ByteOrder.BIG_ENDIAN);
            buffer.putInt(0, VALUE);
            buffer.force();
        }

        try (FileChannel channel =
                     FileChannel.open(path, StandardOpenOption.READ)) {
            MappedByteBuffer read =
                    channel.map(FileChannel.MapMode.READ_ONLY, 0, SIZE);
            read.order(ByteOrder.BIG_ENDIAN);
            int found = read.getInt(0);

            System.out.println("SYNC mode used: " + usedSync);
            System.out.println("Reopened value: " + found);
            System.out.println("Result: " + (found == VALUE ? "PASS" : "FAIL"));
        }
    }
}
~~~

### 8.1. Vì sao chương trình chuẩn bị file size trước khi map?

`FileChannel.map(mode, 0, SIZE)` yêu cầu ánh xạ một phạm vi có kích thước cụ thể. Bài lab chủ động đảm bảo file có tối thiểu **16 bytes** bằng cách viết một byte vào vị trí cuối nếu cần:

~~~java
if (channel.size() < SIZE) {
    channel.position(SIZE - 1);
    channel.write(java.nio.ByteBuffer.wrap(new byte[]{0}));
}
~~~

Đây là mã đã nằm trong chương trình đầy đủ; không dùng trực tiếp trên file đang có dữ liệu có giá trị nếu không kiểm tra kế hoạch ghi. Cách chuẩn bị tránh phụ thuộc vào chi tiết không đồng nhất khi map vượt kích thước file hiện có.

Nếu áp dụng vào sản phẩm thực, cần thêm chính sách validate **kích thước, layout, integrity và concurrency**; một ghi byte ở vị trí cuối không tự làm nội dung file trở thành một định dạng dữ liệu hợp lệ.

### 8.2. Vì sao cần `ByteOrder.BIG_ENDIAN`?

`putInt(0, VALUE)` và `getInt(0)` phải đồng ý cách mã hóa nhiều byte. Ví dụ đặt rõ `BIG_ENDIAN` trên cả write và read để tránh phụ thuộc các thao tác khác thay đổi byte order. Đây là quyết định định dạng lưu trữ; ứng dụng thật phải định nghĩa byte order nhất quán cho mọi reader và writer.

### 8.3. Vì sao catch nằm bên trong `try (FileChannel ...)`?

`UnsupportedOperationException` được bắt **riêng quanh `channel.map(ExtendedMapMode.READ_WRITE_SYNC, ...)`**. Nếu `FileChannel.open(...)` ném `IOException` hoặc standard `READ_WRITE` fallback thất bại, chương trình không gộp những lỗi đó vào “SYNC mapping unsupported”. Điều này giúp log chính xác hơn và tránh che mất lỗi lưu trữ.

### 8.4. Biên dịch và chạy

Class `ExtendedMapMode` nằm trong **module `jdk.nio.mapmode`**, không phải `java.base`. Với chương trình non-modular, chỉ rõ module khi biên dịch/chạy:

~~~bash
javac -encoding UTF-8 --release 17 --add-modules jdk.nio.mapmode NvmMapFallbackDemo.java
java --add-modules jdk.nio.mapmode NvmMapFallbackDemo mapped.bin allow-fallback
~~~

Cần một JDK **17 trở lên** cung cấp `jdk.nio.mapmode`. Đây là **module JDK-specific**, không phải API Java SE bắt buộc cho mọi triển khai Java. Với ứng dụng modular, nếu dùng trực tiếp class, `module-info.java` cần một khai báo phù hợp:

~~~java
module com.example.persistence {
    requires jdk.nio.mapmode;
}
~~~

Đây là **snippet module descriptor**, không phải một tệp chương trình độc lập có `main`. Khi phân phối runtime đã rút gọn bằng `jlink`, nhớ đưa vào các module cần thiết.

### 8.5. Stdout trên môi trường không hỗ trợ mode SYNC

Đã biên dịch và chạy chương trình trên **OpenJDK 24 / Windows**, sử dụng bytecode mục tiêu `--release 17`. Trong môi trường thử nghiệm này, lệnh `map(READ_WRITE_SYNC)` bị `UnsupportedOperationException` nên chương trình dùng policy cho phép fallback.

**Stdout chính xác:**

~~~text
Requested mode: READ_WRITE_SYNC
SYNC mapping unsupported
Fallback mode: READ_WRITE
SYNC mode used: false
Reopened value: 2026
Result: PASS
~~~

**Điều đã kiểm chứng:**
- `ExtendedMapMode.READ_WRITE_SYNC` có mặt trong JDK.
- File thông thường được mở để đọc/ghi.
- Mapping SYNC bị implementation từ chối bằng `UnsupportedOperationException`.
- Mapping chuẩn `READ_WRITE` trên cùng file thành công.
- Ghi số `2026` bằng `putInt`, gọi `force()`, đóng channel, mở lại `READ_ONLY` và đọc đúng dữ liệu.

**Điều không được khẳng định:** Demo **không chứng minh mọi Windows/JDK đều có cùng hành vi**, không chứng minh persistence khi power failure, và không benchmark đường flush NVM.

### 8.6. Khi SYNC mapping thực sự được hỗ trợ

Nếu chạy trên một môi trường có file-backed NVM mapping được hỗ trợ cho **chính file đầu vào**, chương trình có thể thành công ngay ở mode SYNC. Khi đó không có hai dòng `SYNC mapping unsupported` và `Fallback mode: READ_WRITE`. Phần kết quả sẽ có:

~~~text
Requested mode: READ_WRITE_SYNC
SYNC mode used: true
Reopened value: 2026
Result: PASS
~~~

Đây là **kết quả dự kiến từ nhánh code**, không phải stdout đã quan sát trên thiết bị NVM thực. Nó giúp hiểu sự khác nhau giữa hai đường chạy mà không giả vờ bài lab đã dùng phần cứng persistent memory.

### 8.7. Chính sách `require-sync` trên môi trường không hỗ trợ

Chạy:

~~~bash
java --add-modules jdk.nio.mapmode NvmMapFallbackDemo mapped-required.bin require-sync
~~~

Trong lần kiểm chứng trên Windows/JDK 24, chương trình in:

~~~text
Requested mode: READ_WRITE_SYNC
SYNC mapping unsupported
~~~

Sau đó process **kết thúc với exit code khác 0**, do `IllegalStateException` có message:

~~~text
Persistent-memory mapping is required; no fallback
~~~

và giữ `UnsupportedOperationException` làm cause. **Stack trace chính xác, số dòng và thông báo từ provider phụ thuộc JVM/build**, nên không nên coi một stack trace mẫu là output bắt buộc trên mọi máy.

Đây là hành vi đúng khi hợp đồng yêu cầu persistent-memory mapping: **không ghi dữ liệu theo mode yếu hơn để giả vờ đã thành công**.

## 9. `READ_ONLY_SYNC`: cũng có thể không được hỗ trợ

Ngay cả khi chỉ cần đọc, `READ_ONLY_SYNC` vẫn là một **JDK-specific sync map mode**. Nó không mặc nhiên khả dụng chỉ vì `READ_ONLY` chuẩn hoạt động.

Ví dụ kiểm tra rút gọn:

~~~java
try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ)) {
    try {
        MappedByteBuffer mapped =
                channel.map(ExtendedMapMode.READ_ONLY_SYNC, 0, 8);
        System.out.println("SYNC read supported");
    } catch (UnsupportedOperationException unsupported) {
        MappedByteBuffer normal =
                channel.map(FileChannel.MapMode.READ_ONLY, 0, 8);
        System.out.println("READ_ONLY fallback value: " + normal.get(0));
    }
}
~~~

Đoạn trên là **snippet**, yêu cầu file có ít nhất 8 bytes cùng imports và `file` phù hợp. Fallback đọc có thể hợp lý nếu ứng dụng **chỉ yêu cầu đọc file**; nhưng vẫn nên kiểm tra chính sách triển khai, bảo vệ dữ liệu và lỗi I/O.

Trong kiểm chứng bổ sung trên Windows/JDK 24, với file thử nghiệm byte đầu tiên là `1`:

~~~text
READ_ONLY_SYNC unsupported=UnsupportedOperationException
READ_ONLY value=1
~~~

Đây là stdout của một chương trình kiểm tra riêng với cách in thông báo cụ thể; không phải output nguyên xi từ snippet rút gọn phía trên. Chương trình đã xác nhận:
- `READ_ONLY_SYNC` bị từ chối bằng `UnsupportedOperationException`.
- `FileChannel.MapMode.READ_ONLY` vẫn đọc đúng byte đầu.

**Phân biệt:** Khi một ứng dụng chỉ đọc dữ liệu không yêu cầu semantics SYNC/NVM, normal `READ_ONLY` có thể hoàn toàn đủ. Khi yêu cầu phải đọc từ một vùng NVM mapping cụ thể, bạn cần áp dụng chính sách tương ứng, không tự dùng normal mode rồi khai báo sai khả năng triển khai.

## 10. Quyền mở channel quan trọng không kém mode

### 10.1. Mode read/write cần channel cho cả đọc lẫn ghi

~~~java
try (FileChannel channel =
        FileChannel.open(file, StandardOpenOption.READ)) {

    // Sai nếu cố ánh xạ RW từ channel chỉ READ:
    // channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);
}
~~~

Đây là snippet minh họa. Nếu implementation có mode nhưng channel thiếu quyền, kết quả có thể là `NonWritableChannelException` chứ **không phải** UOE. Trong example đầy đủ, `FileChannel.open` có cả `READ` và `WRITE` để tránh nhầm lỗi permission với lỗi unsupported map mode.

### 10.2. Đừng dựa vào thứ tự bắt exception để “tự nhận biết” nguyên nhân

Một implementation có thể kiểm tra map mode được hỗ trợ trước khi kiểm tra quyền, hoặc ngược lại. Nếu thấy UOE trong một trường hợp mà bạn cũng mở channel sai quyền, không có nghĩa channel permissions đã đúng. Hãy **đảm bảo tiền điều kiện** rồi thử mode.

### 10.3. Phân biệt “file không tồn tại” và “map mode unsupported”

`FileChannel.open(path, READ, WRITE)` khi file không tồn tại có thể ném `NoSuchFileException`. `CREATE` chỉ áp dụng khi sử dụng kết hợp với những open options phù hợp. Đây là lỗi **mở nguồn**, không cho biết bất cứ điều gì về SYNC support của provider.

Trong chương trình đầy đủ, `CREATE` được dùng để tạo **file lab mới**. Đối với dữ liệu production, không tự tạo file rỗng khi đầu vào đáng ra phải tồn tại và chứa dữ liệu đã được khởi tạo.

## 11. `force()`: hiểu đúng semantics sau khi mapping

`MappedByteBuffer.force()` yêu cầu đẩy các thay đổi từ mapped buffer xuống backing storage theo hợp đồng API và mode.

### 11.1. Với normal `READ_WRITE`

~~~java
MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_WRITE, 0, size);
mapped.putInt(0, 2026);
mapped.force();
~~~

Theo API `MappedByteBuffer`, đối với file nằm trên **thiết bị lưu trữ cục bộ**, `force()` cung cấp bảo đảm được mô tả trong tài liệu về các thay đổi của buffer; đối với **thiết bị không phải local**, phạm vi bảo đảm có thể khác.

Không suy ra mọi tổ hợp OS/file-system/device/hardware đều có cùng latency, ordering hoặc hành vi khi power fail từ một lần gọi `force()` đơn giản.

### 11.2. Với `READ_WRITE_SYNC`

`ExtendedMapMode.READ_WRITE_SYNC` dùng đường ánh xạ NVM mà implementation hỗ trợ. Theo ghi chú của Oracle cho Linux, `force()` trên buffer được tạo bằng mode này có thể được thực hiện bằng **cache-line writeback**, thay cho file device flush thông thường.

Điều đó **không có nghĩa**:
- Mọi lần `putInt` tự động tương đương một transaction durable.
- Có API `commit()` giao dịch tự động cho nhiều field.
- Một record nhiều field không thể bị ghi dở do crash.
- Normal mode và SYNC mode có hiệu năng/semantics giống hệt nhau.

Nếu xây storage engine, cần giao thức lưu trữ đúng: version, checksum, thứ tự persist, crash recovery và chiến lược xác thực hậu sự cố. Các chi tiết đó vượt phạm vi bài chẩn đoán UOE, nhưng là lý do **không được âm thầm fallback** khi hệ thống yêu cầu semantics NVM.

### 11.3. `force()` có thể lỗi sau khi mapping thành công

Một mapping tạo thành công **không chứng minh mọi phép ghi/force sau đó sẽ thành công**. `MappedByteBuffer.force()` có thể ném `UncheckedIOException` nếu quá trình đẩy dữ liệu thất bại.

**Xử lý đúng:** coi đó là lỗi khi lưu dữ liệu, không ghi log “commit thành công”. Một hệ thống production có thể cần đánh dấu storage unhealthy, giữ nguyên cause và triển khai recovery.

## 12. Tài nguyên, vòng đời mapping và các rủi ro I/O

### 12.1. `FileChannel.close()` không đồng nghĩa unmap ngay

Tài liệu `FileChannel.map` nêu rằng một mapping sau khi tạo **không phụ thuộc vào việc FileChannel có còn mở**, và đóng channel không làm mapping tự biến mất. `MappedByteBuffer` có vòng đời riêng; không phải `AutoCloseable` để bạn dùng trong `try-with-resources` trực tiếp.

Hệ quả:
- Đừng nghĩ `try (FileChannel channel ...)` tự giải phóng địa chỉ ánh xạ ngay khi ra khỏi block.
- Trên một số OS, file đang được map có thể không được đổi tên/xóa như mong muốn cho tới khi mapping được giải phóng.
- Không dùng các mẹo reflection gọi private cleaner APIs như giải pháp chuẩn cho JDK hiện đại.
- Khi cần quản lý vòng đời ánh xạ chủ động, xem các API hiện hành được hỗ trợ và kiến trúc ứng dụng; không truy cập internal `sun.nio.ch`.

### 12.2. Không truncate file đang được map

`MappedByteBuffer` có thể trở nên **không thể truy cập toàn bộ hoặc một phần** nếu file gốc bị cắt ngắn hoặc thao tác đồng thời không tương thích. API ghi rõ truy cập vùng mất hiệu lực có thể phát sinh exception không xác định tại thời điểm thao tác hoặc sau đó.

Với ứng dụng lưu dữ liệu quan trọng, thiết kế rõ:
- Ai là owner của file.
- Có nhiều process cùng map file hay không.
- Khi nào được resize/truncate/replace.
- Cơ chế lock/concurrency/versioning.
- Trình tự flush/force trước khi đổi metadata hoặc file.

### 12.3. Đừng test trên file production

Để phát hiện SYNC support, **tạo một file thử nghiệm riêng** trên đúng target filesystem/device theo quyền được cho phép, sau đó dọn file khi không còn mapping/process sử dụng. Tránh map rồi ghi ngẫu nhiên vào file database hay journal đang phục vụ yêu cầu thực.

## 13. Thiết kế logs và metrics khi fallback

Ứng dụng cần phân biệt trạng thái thật của storage backend. Ví dụ các sự kiện log mang tính khái niệm:

~~~text
storage.mapping.requested=READ_WRITE_SYNC
storage.mapping.actual=READ_WRITE
storage.mapping.fallback=true
storage.mapping.reason=SYNC_UNSUPPORTED
~~~

Đây là **ví dụ thông tin log**, không phải cú pháp bắt buộc của Java hay metric system. Các field nên thể hiện:
- **Mode yêu cầu** và **mode đã dùng**.
- **Chính sách**: `require-sync` hay `allow-fallback`.
- **Loại exception/cause** được thấy ở đúng mapping call.
- **OS/JDK/provider/file-system** và instance khi cần, nhưng tránh ghi đường dẫn nhạy cảm cho khách hàng cuối.
- **Kết quả xác thực dữ liệu** sau thao tác ghi/đọc; nếu chưa test power-loss, không tuyên bố durable.
- **Tỷ lệ fallback / lỗi mapping**, vì một thay đổi môi trường có thể làm cả cụm chuyển từ NVM sang normal storage.

### 13.1. Vì sao cần log rõ fallback?

Nếu không, sau khi deploy lên máy mới:
- Chương trình vẫn chạy.
- Truy cập dữ liệu qua normal mapped file vẫn đúng.
- Nhưng hệ thống không còn dùng đường NVM tối ưu dự định.
- Độ trễ và mô hình persistence có thể khác.

Một log rõ **requested vs actual mode** giúp phát hiện lỗi cấu hình trước khi trở thành sự cố hiệu năng hoặc dữ liệu.

## 14. Bảng xử lý theo tình huống

| Tình huống | Nên làm gì? | Không nên làm gì? |
| --- | --- | --- |
| Java implementation không có `jdk.nio.mapmode` | Chọn JDK hỗ trợ hoặc loại bỏ phụ thuộc module trong thiết kế | Mong `onError`/catch UOE trong `main` khắc phục lỗi module resolution |
| `map(SYNC)` ném UOE, policy strict | Dừng, báo rõ map mode unsupported, giữ cause | Lặng lẽ `READ_WRITE` và báo NVM thành công |
| `map(SYNC)` ném UOE, policy cho phép fallback | Thử normal `READ_WRITE`, ghi log mode thật, test ghi/đọc | Bắt mọi RuntimeException rồi fallback |
| Linux có mode nhưng target FS không hỗ trợ MAP_SYNC | Xem `IOException`, mount/FS/device/OS và chính sách triển khai | Kết luận đơn giản “provider Java không hỗ trợ” |
| Channel thiếu quyền WRITE | Mở channel đúng quyền nếu chính sách cho phép | Tự đè quyền hay catch UOE để che điều kiện sai |
| `force()` thất bại | Báo lưu trữ thất bại, kích hoạt xử lý lỗi/recovery | Công bố transaction thành công |
| `READ_ONLY_SYNC` không được hỗ trợ, ứng dụng chỉ cần đọc | Dùng `READ_ONLY` nếu hợp đồng cho phép | Đổi sang `PRIVATE` và giả rằng giống NVM |
| Bộ lưu trữ có yêu cầu crash consistency | Thiết kế giao thức ghi/khôi phục và test thật | Coi `reopened value == 2026` là bằng chứng vượt power failure |
| Có nhiều provider/OS | Test matrix với cấu hình thật; ghi rõ actual mode | Hard-code `os.name` như phép kiểm tra support tuyệt đối |

## 15. Các lỗi phổ biến

### Lỗi A — “Class `ExtendedMapMode` tồn tại nên NVM được hỗ trợ”

**Sai.** Class nằm trong JDK chỉ nói API có mặt. `map(...)` phải được implementation và nền tảng cho phép.

**Sửa:** kiểm tra mapping thực tế trên file phù hợp, bắt lỗi đúng nơi.

### Lỗi B — Bắt UOE quanh toàn bộ quá trình mở file

~~~java
try {
    FileChannel.open(path, StandardOpenOption.READ);
    // ...các thao tác khác...
} catch (UnsupportedOperationException e) {
    System.err.println("NVM unsupported");
}
~~~

**Sai:** UOE có thể đến từ provider không hỗ trợ **mở FileChannel** hoặc open option, không phải `map(SYNC)`.

**Sửa:** bắt ngoại lệ **trực tiếp quanh `channel.map(SYNC, ...)`**.

### Lỗi C — Mọi ánh xạ SYNC thất bại đều là `UnsupportedOperationException`

**Sai.** Trên Linux với file system không hỗ trợ mapping cụ thể, có thể là `IOException`; ngoài ra còn permission và tham số.

**Sửa:** phân loại lỗi theo stage và type, giữ cause, không giả định một subtype duy nhất.

### Lỗi D — Dùng `READ_WRITE` dự phòng nhưng vẫn ghi “SYNC/NVM=true”

**Sai:** mode thực là normal mapping và không cùng hợp đồng/hành vi flush.

**Sửa:** biến `usedSync` phải phản ánh nhánh đã chạy, log và metrics nhất quán.

### Lỗi E — Coi `MappedByteBuffer.force()` tương đương transaction

**Sai:** `force()` là thao tác đồng bộ dữ liệu của vùng ánh xạ, không tự có atomicity cho nhiều lần ghi.

**Sửa:** thiết kế persistence/recovery protocol cho dữ liệu quan trọng.

### Lỗi F — Bỏ qua `java --add-modules jdk.nio.mapmode`

Với chương trình trên classpath (unnamed module), có thể không resolve được module JDK-specific theo cách chạy mặc định.

**Sửa:** khai báo `--add-modules jdk.nio.mapmode` khi biên dịch/chạy, hoặc `requires jdk.nio.mapmode` trong ứng dụng modular.

### Lỗi G — Dùng `READ_ONLY` rồi cố `putInt`

**Sai:** read-only mapping không cho phép ghi.

**Sửa:** dùng read-only cho đọc, RW/SYNC khi quyền và hợp đồng cho phép; không bắt `ReadOnlyBufferException` để “thử tiếp” một cách mù quáng.

### Lỗi H — Chỉ kiểm tra file có tồn tại

**Sai:** `Files.exists` không chứng minh provider, file system và thiết bị hỗ trợ SYNC.

**Sửa:** làm mapping thử nghiệm hợp lệ ở file riêng và xác nhận policy.

### Lỗi I — Dùng `PRIVATE` làm đường lưu dữ liệu

**Sai:** thay đổi copy-on-write không được ghi ngược về file theo contract.

**Sửa:** nếu cần lưu xuống file và policy cho phép normal mapping, dùng `READ_WRITE` cùng cơ chế persist phù hợp.

### Lỗi J — Xem đọc lại thành công là thử nghiệm mất điện

**Sai:** OS page cache/buffer và các lớp lưu trữ có thể chưa trải qua sự cố đột ngột.

**Sửa:** test recovery trên hạ tầng phù hợp; không phá dữ liệu thật để thử.

### Lỗi K — Giả định mapping được unmap ngay khi close channel

**Sai:** mapping có vòng đời riêng; đóng channel không lập tức làm `MappedByteBuffer` hết hiệu lực.

**Sửa:** quản lý vòng đời và file operations có chủ đích, không dùng reflection vào private API.

### Lỗi L — Bắt rộng rồi xóa cause

~~~java
catch (RuntimeException e) {
    throw new IllegalStateException("NVM unavailable");
}
~~~

**Sai:** Che giấu lỗi chương trình khác và mất stack/cause gốc.

**Sửa:** chỉ bắt exception cần giải quyết tại vị trí phát sinh, giữ cause và báo trạng thái thực.

## 16. Bài tập thực hành có đáp án

### Bài 1 — Xác định exception

~~~java
MappedByteBuffer buffer =
        channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);
~~~

**Hỏi:** Channel đã mở thành công, nhưng implementation không nhận mode SYNC. Exception theo API là gì?

**Đáp án:** `UnsupportedOperationException` tại `map(...)`. Bản thân việc mở được `FileChannel` chưa chứng minh hỗ trợ SYNC mapping.

### Bài 2 — Có được fallback không?

Một công cụ phân tích file chỉ cần lưu kết quả theo semantics của regular file, không dựa vào tính năng cache-line writeback của NVM. Trên OS không hỗ trợ SYNC, code muốn dùng `READ_WRITE`.

**Đáp án:** Có thể, **nếu policy cho phép**, đường fallback được test và kết quả log phải nói chính xác mode thực. Không được tuyên bố vẫn đang sử dụng NVM-specific mapping.

### Bài 3 — Cơ sở dữ liệu yêu cầu SYNC

Một storage engine nói rõ: “Không được khởi động nếu không có persistent-memory mapping”. Nếu `map(SYNC)` ném UOE?

**Đáp án:** **Fail fast**, giữ nguyên nguyên nhân và báo không đáp ứng yêu cầu. Không tự động map `READ_WRITE`.

### Bài 4 — Phân biệt ba lỗi

1. `channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, size)` ném UOE.
2. `channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, size)` ném `IOException` từ FS.
3. `buffer.force()` ném `UncheckedIOException`.

**Đáp án:**
1. Implementation không hỗ trợ mode yêu cầu.
2. Mapping bị lỗi I/O hoặc điều kiện OS/FS không đáp ứng; cần đọc cause và kiểm tra nền tảng.
3. Mapping đã tồn tại nhưng **ghi/force thất bại**; không được coi là persistence thành công.

### Bài 5 — Chọn mode read-only

Một job chỉ cần đọc dữ liệu file đã tồn tại, không cần NVM-specific SYNC. `READ_ONLY_SYNC` không được hỗ trợ.

**Đáp án:** `FileChannel.MapMode.READ_ONLY` là fallback thích hợp nếu dữ liệu không có yêu cầu NVM-specific khác. Không cần mở quyền WRITE chỉ để đọc.

### Bài 6 — Vì sao `PRIVATE` không phù hợp?

**Hỏi:** Khi yêu cầu ghi file có khả năng tồn tại sau khi JVM kết thúc, mode `PRIVATE` có thể thay thế `READ_WRITE_SYNC` không?

**Đáp án:** **Không.** `PRIVATE` là copy-on-write, thay đổi từ mapping **không được ghi lại file** theo hợp đồng. Nếu được phép degrade, phải xem `READ_WRITE` và `force()`, không dùng `PRIVATE`.

### Bài 7 — Thiếu module

Bạn thấy lỗi module `jdk.nio.mapmode not found` trước khi method `main` được gọi.

**Đáp án:** Đây là lỗi **module availability/resolution**, không phải exception từ `FileChannel.map`. Xác minh JDK chứa module, cấu hình `--add-modules`/`module-info.java` hoặc runtime image. Một `catch (UnsupportedOperationException)` trong `main` không thể xử lý lỗi này.

### Bài 8 — Kiểm chứng dữ liệu

Demo in `Result: PASS` sau khi đọc lại `2026` từ file. Có thể báo “đã qua kiểm thử power loss” không?

**Đáp án:** **Không.** Test chỉ xác minh đường ghi/force/đọc lại trong điều kiện đang chạy. Muốn tuyên bố phục hồi sau mất điện, cần kịch bản test tương ứng, hạ tầng phù hợp và giao thức nhất quán.

### Bài 9 — Test matrix

Nêu ba trường hợp cần có trong automated/integration tests.

**Đáp án tham khảo:**
1. Environment hỗ trợ SYNC mapping thật: `require-sync` thành công, buffer force và đọc lại.
2. Environment từ chối SYNC bằng UOE: `require-sync` dừng đúng, `allow-fallback` dùng regular mapping và log mode thật.
3. File system/permissions lỗi: `IOException`/`NonWritableChannelException` được báo đúng, không bị biến thành “unsupported” hoặc fallback thành công.

## 17. Checklist triển khai an toàn

- [ ] Xác định ứng dụng **cần SYNC/NVM bắt buộc hay chỉ ưu tiên như tối ưu**.
- [ ] Chạy trên JDK có module `jdk.nio.mapmode` và resolve module đúng.
- [ ] File thử nghiệm nằm trên **đúng target device/file system**, không phải file bất kỳ.
- [ ] Channel mở với quyền đọc/ghi phù hợp mode.
- [ ] Catch `UnsupportedOperationException` **ngay quanh `map(SYNC, ...)`**.
- [ ] Phân biệt `IOException`, `IllegalArgumentException`, quyền và lỗi `force()`.
- [ ] Chỉ fallback khi **policy có chủ đích** và hệ thống xử lý đúng semantics khác biệt.
- [ ] Ghi rõ mode được yêu cầu, mode thực tế và lý do fallback.
- [ ] Không dùng `PRIVATE` cho dữ liệu yêu cầu ghi lại file.
- [ ] Không dùng `isLoaded()`, `Files.exists()` hoặc tên OS làm chứng minh support.
- [ ] Không đồng nhất `force()` với transaction/crash-consistent format.
- [ ] Quản lý concurrency và tránh truncate mapped file đang dùng.
- [ ] Test lại khi đổi JVM, provider, kernel, mount options, hardware hoặc file system.
- [ ] Test cả success, strict failure, fallback, I/O error và recovery.
- [ ] Không ghi dữ liệu thử nghiệm vào file production.

## 18. Kết luận

- `ExtendedMapMode.READ_ONLY_SYNC` và `READ_WRITE_SYNC` là **JDK-specific map modes có từ Java 14**, vẫn còn trong các JDK hiện hành.
- Khi `FileChannel.map(...)` nhận một mode mà implementation **không hỗ trợ**, nó có thể ném **`UnsupportedOperationException`**. Đây là một lỗi **khả năng hỗ trợ mapping**, không phải bằng chứng file hỏng.
- Trên một OS/file system có triển khai mode nhưng **file không phù hợp**, lỗi cũng có thể là **`IOException`**; không gộp mọi exception thành UOE.
- **Mở channel thành công ≠ map SYNC thành công**, và **map SYNC thành công ≠ mọi lần ghi/force chắc chắn thành công**.
- Nếu NVM persistence là **yêu cầu bắt buộc**, hãy **fail fast** và giữ cause. Nếu chỉ là tối ưu, có thể fallback có kiểm soát sang `READ_WRITE` hoặc `READ_ONLY` phù hợp.
- `READ_WRITE` **không phải alias của `READ_WRITE_SYNC`**; lưu ý sự khác nhau về mapping/persistence/hiệu năng.
- Bài lab Java 17+ đã kiểm chứng trên OpenJDK 24/Windows: SYNC map bị UOE, regular map hoạt động, force và đọc lại số `2026` thành công; strict policy dừng đúng.
- Hãy coi logs, policy và tests trên **hạ tầng đích** là thành phần bắt buộc của thiết kế hỗ trợ NVM, không dựa vào một phép kiểm tra OS hoặc class tồn tại.

**Nguồn chính thức, còn áp dụng:**
- [Oracle Java SE 25 — `ExtendedMapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): hai SYNC modes, `UnsupportedOperationException` khi không hỗ trợ, các ghi chú Linux.
- [Oracle Java SE 25 — `FileChannel.map`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long)): semantics mapping, các exception và vòng đời.
- [Oracle Java SE 25 — `MappedByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html): `force`, `isLoaded` và lưu ý tài nguyên.
- [Oracle Java SE 25 — `jdk.nio.mapmode` module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/module-summary.html): module chứa extended map modes.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): bối cảnh giới thiệu tính năng từ Java 14.
- [OpenJDK JDK-8207851 — Implement JEP 352](https://bugs.java.com/bugdatabase/view_bug?bug_id=8207851): phân biệt platform không hỗ trợ và trường hợp trên platform hỗ trợ với device không phù hợp.
