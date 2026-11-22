# Giới hạn giải phóng memory mapping theo phiên bản API và JVM

## 1. Vấn đề thực tế: đóng tệp rồi, mapping đã được giải phóng chưa?

Khi dùng **memory-mapped file**, Java ánh xạ một vùng nội dung của tệp vào vùng địa chỉ bộ nhớ ảo của tiến trình. Chương trình có thể truy cập vùng đó thông qua `MappedByteBuffer` hoặc, trên JDK mới, `MemorySegment`. Cơ chế này thường tránh phải tự sao chép dữ liệu bằng vòng lặp `FileChannel.read/write` ở tầng ứng dụng, nhưng kéo theo câu hỏi về **vòng đời của tài nguyên native**: khi nào hệ điều hành thôi giữ vùng ánh xạ?

Một nhầm lẫn phổ biến:

```java
MappedByteBuffer mapped = channel.map(
    FileChannel.MapMode.READ_WRITE, 0, length);
channel.close();
// Không thể suy ra vùng mapping đã được unmap.
```

Đây là đoạn minh họa, giả sử `channel` và `length` đã được khai báo. `close()` giải phóng tài nguyên của **channel**, còn mapping đã tạo có vòng đời riêng. Với API truyền thống trả về `MappedByteBuffer`, **đóng channel không hủy mapping**. Mapping có thể tiếp tục hợp lệ khi buffer vẫn còn được dùng.

Hợp đồng API Java SE 17 nói mapping của một `MappedByteBuffer` còn hợp lệ cho đến khi buffer được garbage-collected. Nhưng **GC xảy ra lúc nào không được bảo đảm**; Java SE 17 cũng không công bố phương thức `unmap()`/`close()` chuẩn trên `MappedByteBuffer`. Đây là giới hạn trọng tâm cần hiểu khi thiết kế chương trình cần giải phóng hoặc thay thế tệp ngay lập tức.

## 2. Phân biệt bốn thao tác thường bị nhầm

| Thao tác | Điều nó thực sự làm | Có bảo đảm unmap không? |
| --- | --- | --- |
| `FileChannel.close()` | Đóng kênh và tài nguyên gắn với channel | **Không** đối với mapping `MappedByteBuffer` đã tạo |
| `mapped.force()` | Yêu cầu đồng bộ thay đổi ở mapping đọc/ghi tới thiết bị lưu trữ theo hợp đồng API | **Không** |
| `mapped.clear()` | Đặt lại `position=0`, `limit=capacity`, xóa mark | **Không**; không xóa byte |
| Đối tượng mapping không còn reachable và GC thu gom | Có thể dẫn đến giải phóng tài nguyên mapping của buffer cũ | **Không có thời điểm xác định** |

Cần tách các khái niệm:

- **Flush/persistence**: dữ liệu thay đổi được đẩy xuống thiết bị lưu trữ hay chưa.
- **Unmap/release**: vùng ánh xạ bộ nhớ không còn được tiến trình sử dụng.
- **Close channel**: tài nguyên kênh được đóng.
- **Delete/rename/truncate**: thao tác hệ thống tệp; hành vi với vùng mapping đang sống phụ thuộc nền tảng.

`force()` phục vụ độ bền dữ liệu, **không phải giải phóng vùng ánh xạ**. `load()` chỉ cố gắng nạp trang vào RAM; `isLoaded()` chỉ gợi ý mức resident; chúng cũng không phải API unmap. `System.gc()` chỉ yêu cầu JVM cân nhắc chạy GC, không tạo cam kết giải phóng ngay.

## 3. API truyền thống: `FileChannel.map(mode, position, size)`

Từ những phiên bản Java cũ và vẫn tồn tại trong Java 17/21/22+, `FileChannel` có phương thức:

```java
MappedByteBuffer map(
        FileChannel.MapMode mode,
        long position,
        long size) throws IOException;
```

Kết quả là `java.nio.MappedByteBuffer`, một loại `ByteBuffer` trực tiếp đại diện cho vùng ánh xạ tệp.

**Các điểm thuộc hợp đồng quan trọng:**

1. Mapping có thể vẫn truy cập được **sau khi `FileChannel` đã đóng**.
2. Thời gian mapping được giải phóng gắn với việc buffer trở thành đối tượng có thể được GC thu gom; ứng dụng **không điều khiển chính xác thời điểm GC**.
3. `MappedByteBuffer` không triển khai `AutoCloseable` và không có phương thức `close()` hay `unmap()` chuẩn công khai.
4. Các view như `slice()` hoặc `duplicate()` có thể cùng chia sẻ vùng nội dung. Không giả định gán `mapped = null` là đủ nếu còn view hoặc tham chiếu liên quan đang sống.
5. Tài nguyên native và địa chỉ ảo có thể tiếp tục được giữ dù lượng bộ nhớ heap nhìn thấy không lớn. Dựa riêng vào `Runtime.freeMemory()` để suy đoán mapping đã được tháo là sai.

Theo API, kích thước của mapping trả về `MappedByteBuffer` bị giới hạn bởi hệ số chỉ số `int` của buffer (vùng map không được lớn hơn `Integer.MAX_VALUE` byte). Tệp lớn hơn có thể được chia thành nhiều mapping nhỏ theo thiết kế; mỗi mapping lại cần quản lý vòng đời. **Giảm số lượng map hoặc chuyển sang I/O đọc/ghi thông thường** có thể hữu ích khi khối lượng tạo/hủy mapping liên tục gây khó quản lý.

## 4. Ví dụ Java 17+: mapping vẫn dùng được sau khi channel đóng

Chương trình này tạo một tệp tạm 4 byte, ánh xạ với chế độ `READ_WRITE`, đóng channel rồi tiếp tục đọc và sửa qua `MappedByteBuffer`. Tệp được đăng ký xóa khi JVM kết thúc; đây là **dọn dẹp tệp ở lúc thoát chương trình**, không phải thao tác unmap.

**Tệp `LegacyMappingDemo.java`:**

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LegacyMappingDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("legacy-map-", ".bin");
        path.toFile().deleteOnExit();
        Files.write(path, new byte[] {10, 20, 30, 40});

        MappedByteBuffer mapped;
        try (FileChannel channel = FileChannel.open(
                path,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
            mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 4);
            System.out.println("Trong khoi mo: " + mapped.get(0));
        }

        // FileChannel đã đóng, mapping vẫn có thể được truy cập.
        System.out.println("Sau close channel: " + mapped.get(1));
        mapped.put(2, (byte) 99);
        mapped.force();

        System.out.println("Byte vua sua: " + mapped.get(2));
        System.out.println("Size: " + Files.size(path));
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac LegacyMappingDemo.java
java LegacyMappingDemo
```

**Stdout trong điều kiện I/O thành công:**

```text
Trong khoi mo: 10
Sau close channel: 20
Byte vua sua: 99
Size: 4
```

Ví dụ chứng minh **việc đóng channel không làm `mapped` mất hiệu lực**. Nó **không đo thời điểm unmap** và không dùng `System.gc()` để khẳng định tài nguyên được thu hồi tức thì. `deleteOnExit()` chỉ đăng ký một lần xóa khi kết thúc JVM, nên thành công thực tế còn phụ thuộc hệ thống tệp và trạng thái tài nguyên; không sử dụng mẹo này làm chính sách dọn dẹp dài hạn cho dịch vụ chạy liên tục.

Với Windows, một mapping đang tồn tại có thể cản trở xóa/đổi tên tệp trong những tình huống nhất định; một số hệ thống Unix có thể cho phép unlink tên tệp trong khi mapping còn sống. Không viết code phụ thuộc giả định “xóa được trên máy phát triển thì luôn xóa được trên mọi OS”.

## 5. Theo phiên bản Java: khi nào có quyền kiểm soát vòng đời rõ ràng?

Bảng dưới đây phân biệt **API chuẩn hiện có**, không đồng nhất mọi JDK vendor và mọi provider:

| Phiên bản | Cách tạo mapping chuẩn chính | Kiểm soát thời điểm giải phóng |
| --- | --- | --- |
| Java 8, 11, 17, 21 | `FileChannel.map(MapMode, long, long)` → `MappedByteBuffer` | Theo khả năng tiếp cận/GC; không có `MappedByteBuffer.close()` chuẩn |
| Java 22 trở đi | Vẫn có overload trả `MappedByteBuffer` | Mapping kiểu cũ **vẫn** có giới hạn vòng đời GC |
| Java 22 trở đi | Thêm `FileChannel.map(MapMode, long, long, Arena)` → `MemorySegment` | Có thể gắn vào **arena đóng được**; đóng arena giải phóng mapping của segment theo hợp đồng |

**Mốc Java 22** quan trọng vì Foreign Function & Memory API (FFM API, `java.lang.foreign`) được chuẩn hóa cùng overload `FileChannel.map(..., Arena)`. Điều này **không biến mọi `MappedByteBuffer` cũ thành đối tượng có `close()`**. Muốn dùng vòng đời arena, chương trình phải chủ động chọn API trả về `MemorySegment` và triển khai trên runtime/provider hỗ trợ nó.

Đặc tả của overload mới ghi rằng **triển khai mặc định có thể ném `UnsupportedOperationException`**. Trên JDK thông dụng cung cấp triển khai thực tế, tính năng mapping qua arena được hỗ trợ, nhưng nếu ứng dụng dùng một nhà cung cấp `FileChannel` tùy chỉnh, vẫn cần xét khả năng không hỗ trợ.

Không nên khẳng định rằng “mọi Java 22+ đều hỗ trợ cách gọi đó trên mọi file provider” hoặc “nâng version tự động sửa việc unmap của code cũ”.

## 6. API từ Java 22: `MemorySegment` và `Arena`

Overload mới:

```java
MemorySegment map(
        FileChannel.MapMode mode,
        long offset,
        long size,
        Arena arena) throws IOException;
```

- `MemorySegment` đại diện một vùng bộ nhớ có ranh giới rõ ràng.
- `Arena` xác định vòng đời và quy tắc truy cập của các segment gắn với nó.
- Với một **arena đóng được**, mapping được unmap khi arena đó được **đóng thành công** theo hợp đồng `FileChannel.map`.
- Các thao tác truy cập segment sau khi arena đóng bị từ chối, thường bằng `IllegalStateException`; đây là một cơ chế kiểm soát *temporal safety*.
- Với `Arena.ofConfined()`, chỉ luồng sở hữu được sử dụng/đóng vùng đó; truy cập sai luồng có thể gây `WrongThreadException`.
- `Arena.ofShared()` phù hợp khi nhiều luồng cần truy cập nhưng vẫn có vòng đời đóng tường minh.

Các arena có khác biệt quan trọng:

| Arena | Đóng tường minh? | Có thể sử dụng từ nhiều luồng? | Vòng đời |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Có | Không | Kết thúc khi đóng bởi luồng sở hữu |
| `Arena.ofShared()` | Có | Có | Kết thúc khi đóng, cần phối hợp tác vụ |
| `Arena.ofAuto()` | Không | Có | Tự động thu hồi khi JVM xác định arena/segment không còn sống; không có thời điểm chắc chắn |
| `Arena.global()` | Không | Có | Vòng đời toàn cục; không dùng để lập lịch unmap tường minh |

**Muốn có thời điểm giải phóng do mã ứng dụng quản lý, hãy chọn arena có thể đóng.** Dùng `Arena.ofAuto()` vẫn chịu tính không xác định của quản lý bộ nhớ tự động; dùng `Arena.global()` lại càng không phù hợp nếu cần giải phóng mapping theo từng request.

`Arena.close()` không idempotent: đóng hai lần có thể gây `IllegalStateException`. Cơ chế `try-with-resources` giúp tránh việc gọi đóng lặp và bảo đảm đóng khi rời scope, kể cả lúc có ngoại lệ, miễn hoạt động đóng diễn ra thành công.

## 7. Ví dụ Java 22+: giải phóng mapping bằng cách đóng arena

Chương trình sau sử dụng API chính thức của Java 22 trở lên. Tệp được ánh xạ vào một `MemorySegment` thuộc `Arena.ofConfined()`. Sau khi kết thúc `try-with-resources`, arena đóng, mapping được giải phóng theo hợp đồng API và truy cập lại segment bị từ chối.

**Tệp `ArenaMappingDemo.java`:**

```java
import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ArenaMappingDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("arena-map-", ".bin");
        Files.write(path, new byte[] {1, 2, 3, 4});

        MemorySegment segment;
        try (Arena arena = Arena.ofConfined();
             FileChannel channel = FileChannel.open(
                     path,
                     StandardOpenOption.READ,
                     StandardOpenOption.WRITE)) {

            segment = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 4, arena);

            System.out.println(
                    "Truoc close: " + segment.get(ValueLayout.JAVA_BYTE, 0));
            segment.set(ValueLayout.JAVA_BYTE, 1, (byte) 42);
            segment.force();
        } // Đóng channel, sau đó đóng arena => mapping được unmap.

        try {
            segment.get(ValueLayout.JAVA_BYTE, 0);
            System.out.println("Truy cap van thanh cong");
        } catch (IllegalStateException ex) {
            System.out.println("Segment khong con hieu luc");
        }

        byte[] contents = Files.readAllBytes(path);
        System.out.println("Byte tai 1: " + contents[1]);
        Files.delete(path);
    }
}
```

Dùng **JDK 22 trở lên có hỗ trợ overload mapping trên file provider đang dùng**:

```bash
javac ArenaMappingDemo.java
java ArenaMappingDemo
```

**Stdout khi I/O và giải phóng mapping thành công:**

```text
Truoc close: 1
Segment khong con hieu luc
Byte tai 1: 42
```

**Vì sao kết quả này khác ví dụ Java 17?**

1. `segment` được tạo bằng overload `map(..., arena)`, không phải overload trả `MappedByteBuffer`.
2. Trong scope của `arena`, segment hợp lệ và cho phép đọc/ghi byte.
3. `segment.force()` được dùng để đồng bộ thay đổi trên mapping `READ_WRITE`; nó **không** thay `arena.close()`.
4. Khi thoát `try`, `channel.close()` diễn ra trước `arena.close()` do thứ tự khai báo tài nguyên đảo ngược khi đóng.
5. Đóng arena thành công kết thúc vòng đời segment; `segment.get` sau đó phát sinh `IllegalStateException`, được bắt để in thông báo.
6. Tệp còn tồn tại và chứa byte 42 đã ghi; việc giải phóng mapping không đồng nghĩa tự xóa tệp. Chương trình tự xóa tệp ở cuối.

**Giới hạn:** nếu file provider không hỗ trợ overload, có thể gặp `UnsupportedOperationException`. Nếu có lỗi quyền, không gian đĩa, I/O hoặc đóng arena thất bại, chương trình có thể không in toàn bộ stdout ví dụ. Đây là ví dụ dùng một mapping trong một luồng; với code nhiều luồng hãy lựa chọn arena và thiết kế bàn giao/truy cập đúng quy tắc.

## 8. MappedByteBuffer và MemorySegment: hai mô hình quản lý tài nguyên

| Khía cạnh | Legacy `MappedByteBuffer` | `MemorySegment` với arena đóng được |
| --- | --- | --- |
| API tạo | `map(mode, offset, size)` | `map(mode, offset, size, arena)` |
| Phiên bản chính thức | Có từ lâu, dùng được Java 17 | Java 22+ |
| Điều khiển vòng đời | GC của buffer | `arena.close()` |
| Có `close()` chuẩn trực tiếp trên kết quả map? | Không | Không đóng trực tiếp segment; đóng **arena** |
| Khi đóng `FileChannel` | Mapping vẫn hợp lệ | Không thay thế thao tác đóng arena |
| Khi muốn giải phóng đúng lúc | Không có API public chuẩn trực tiếp | Gói mapping trong `try (Arena arena = ...)` |
| Truy cập sau khi tài nguyên đã giải phóng | Phụ thuộc trạng thái mapping/GC, không thiết kế để tự unmap | Segment bị từ chối sau khi arena đóng |
| Hỗ trợ nhiều mapping lớn | Bị giới hạn bởi `ByteBuffer` có chỉ số `int` | `MemorySegment` dùng kích thước `long`, tùy giới hạn thực tế |

Lưu ý `MemorySegment.asByteBuffer()` chỉ tạo view ByteBuffer khi độ dài nằm trong giới hạn `int`. View này **không thoát khỏi vòng đời của arena**: truy cập buffer-view sau khi arena đóng cũng không được phép. Điều đó khác với kết luận sai rằng “bọc segment thành ByteBuffer sẽ tự kéo dài tuổi thọ mapping”.

Mô hình mới cung cấp cách quản lý tài nguyên dễ dự đoán hơn, nhưng vẫn phải tuân theo quyền truy cập, tính nhất quán dữ liệu và giới hạn hệ điều hành. Không áp dụng mặc định rằng một mapped segment có thể dùng tự do xuyên thread nếu đang ở confined arena.

## 9. Những giới hạn vẫn tồn tại trên mọi phiên bản

### 9.1. File có thể bị sửa, rút ngắn hoặc thay thế từ nơi khác

Java không bảo đảm hành vi nhất quán nếu file bị **truncate** hoặc thay đổi kích thước trong khi mapping đang được dùng. Theo tài liệu `MappedByteBuffer` và `MemorySegment`, toàn bộ hoặc một phần vùng ánh xạ có thể trở nên không truy cập được; lỗi được ném khi truy cập có thể **không được chỉ rõ chính xác** theo hệ điều hành.

Vì vậy, đừng sử dụng việc đóng/mở arena để suy ra ứng dụng có thể tùy ý truncate một file đang được người khác map. Cần phối hợp các writer/reader hoặc thiết kế snapshot/versioning, tránh thao tác rút ngắn file khi đang còn các mapping sống.

### 9.2. Không đồng nhất giải phóng mapping với bảo đảm ghi bền vững

Khi mapping `READ_WRITE`, thay đổi có thể được đồng bộ ra file theo cơ chế hệ điều hành. Nếu nghiệp vụ cần đẩy thay đổi tới thiết bị lưu trữ trước khi xác nhận thành công, dùng `MappedByteBuffer.force()` hoặc `MemorySegment.force()` khi phù hợp.

- `force()` là thao tác liên quan **persistence**.
- `close()` trên arena là thao tác liên quan **vòng đời mapping**.
- `FileChannel.force(boolean)` liên quan dữ liệu/metadata của **channel**, không có vai trò là nút unmap.

Độ bền dữ liệu trên thiết bị từ xa hoặc file system đặc biệt còn có giới hạn theo đặc tả. Không mặc định việc unmap tương đương với giao dịch ghi dữ liệu nguyên tử.

### 9.3. Xóa/đổi tên file khi đang map khác nhau giữa OS

Một số OS cho phép đổi tên hoặc unlink file khi tiến trình còn giữ mapping; nơi khác có thể trả về lỗi “file in use” hoặc chặn xóa trong suốt thời gian mapping tồn tại. Java NIO **không cung cấp bảo đảm đồng nhất** cho mọi nền tảng trong tình huống này.

Nếu ứng dụng xử lý file tạm, file segment hoặc log xoay vòng và cần xóa ngay, hãy lựa chọn API với vòng đời rõ ràng (JDK 22+), hoặc nếu phải dùng Java 17, cân nhắc cách tổ chức **không phụ thuộc unmap ngay lập tức**, như đọc/ghi qua `FileChannel` thông thường, chia vòng đời tác vụ, hoặc trì hoãn cleanup dựa trên chính sách phù hợp.

### 9.4. Off-heap, địa chỉ ảo và giới hạn ánh xạ

Mapping không giống như cấp phát một `byte[]` lớn trên Java heap. Một lượng dữ liệu map lớn có thể tiêu thụ **không gian địa chỉ ảo** và các tài nguyên quản lý trang mà metric heap không phản ánh đầy đủ. Không kết luận mapping đã được giải phóng chỉ vì heap sử dụng ít.

Giới hạn còn phụ thuộc kiến trúc 32/64 bit, file descriptor, số vùng mmap, giới hạn địa chỉ, tình trạng tệp và khả năng của filesystem. Khi ứng dụng tạo mapping liên tục, theo dõi số mapping/vòng đời, quan sát tài nguyên tiến trình bằng công cụ phù hợp và đo đạc trên hệ điều hành triển khai thực tế.

### 9.5. Đóng arena cũng cần xử lý tác vụ đang chạy

Với `Arena.ofShared()`, nhiều thread có thể cùng truy cập vùng nhớ được map. Việc một thread cố đóng arena trong khi thread khác đang sử dụng có thể dẫn tới ngoại lệ khi đóng hoặc khi truy cập theo hợp đồng FFM. Phải hoàn tất/hủy tác vụ sử dụng và điều phối vòng đời trước khi đóng.

Với `Arena.ofConfined()`, chỉ thread sở hữu được phép truy cập/đóng. Đưa segment sang thread khác rồi gọi trực tiếp `get` hoặc `set` vi phạm giới hạn thread confinement. Nếu API yêu cầu giao dữ liệu giữa các thread, dùng shared arena hoặc sao chép dữ liệu sang cấu trúc riêng theo thiết kế.

## 10. Những “mẹo unmap” cần xem xét cẩn thận

### 10.1. Dùng `System.gc()` để buộc unmap

```java
mapped = null;
System.gc();
```

Đây **không phải giải pháp xác định**. `mapped = null` chỉ bỏ một tham chiếu cụ thể; còn các view hoặc tham chiếu khác có thể giữ tài nguyên sống. `System.gc()` chỉ là yêu cầu, có thể bị JVM bỏ qua hoặc thực thi vào lúc khác. Không thể chứng minh mapping đã unmap chỉ từ việc lời gọi `System.gc()` kết thúc.

### 10.2. Dùng `sun.misc.Unsafe.invokeCleaner` hoặc reflection nội bộ

Một số mã cũ sử dụng API nội bộ để kích hoạt cleaner trên direct buffer. Cách này **không phải giải pháp portable theo Java SE**: phụ thuộc implementation, module encapsulation, quyền truy cập, công cụ build và trạng thái buffer/view; có thể hỏng khi nâng JDK. Việc cố tình bỏ qua kiểm soát của JVM còn có nguy cơ use-after-unmap nếu tài nguyên vẫn đang được dùng.

Không nên đưa thủ thuật này thành hướng dẫn mặc định cho thư viện dùng trên nhiều vendor/JVM. Khi buộc phải duy trì hệ thống cũ, cần thẩm định riêng cho runtime cụ thể, quản lý quyền sở hữu và kiểm thử đầy đủ; ưu tiên API chuẩn có vòng đời rõ ràng khi có thể nâng cấp.

### 10.3. Nghĩ đóng channel hay gọi `clear` đủ để xóa file ngay

`close()` của channel không giải phóng mapping legacy; `clear()` của buffer chỉ chỉnh `position/limit`; `force()` đồng bộ dữ liệu. Ba thao tác phục vụ ba mục đích khác nhau. Lỗi thiết kế thường xuất hiện khi ứng dụng map file, đóng channel rồi lập tức gọi `Files.delete(path)` và cho rằng thao tác phải thành công trên mọi OS.

## 11. Chọn giải pháp cho ứng dụng thực tế

| Nhu cầu | Hướng triển khai |
| --- | --- |
| Dùng Java 17 và map file lớn, đọc nhiều lần | Giới hạn số mapping sống, kiểm soát scope tham chiếu; chấp nhận việc giải phóng theo GC hoặc chọn I/O không map |
| Java 17 cần xóa/đổi tên file temp ngay sau request | Tránh phụ thuộc vào thời điểm GC; cân nhắc `FileChannel.read/write` với `ByteBuffer` nếu phù hợp |
| Java 22+ cần unmap theo cuối phạm vi xử lý | `FileChannel.map(..., Arena.ofConfined())` với `try-with-resources`, nếu chỉ một thread sử dụng |
| Java 22+ chia mapping giữa nhiều thread | `Arena.ofShared()` và phối hợp đóng sau khi mọi tác vụ hoàn tất |
| Không cần giải phóng tường minh, chấp nhận vòng đời tự động | `Arena.ofAuto()` có thể phù hợp; không có thời điểm unmap được bảo đảm |
| Cần bảo đảm thay đổi xuống thiết bị lưu trữ | Dùng `force()` phù hợp trước khi tuyên bố hoàn tất |
| Cần tương thích nhiều phiên bản JDK | Chọn baseline build/runtime rõ ràng, kiểm tra overload JDK 22 và provider, thử nghiệm trên OS thật |

Nếu mục tiêu chỉ đọc tuần tự một file không quá lớn, mapping không nhất thiết tối ưu hơn mọi giải pháp còn lại. Thiết kế cần cân nhắc độ lớn tệp, tần suất tái sử dụng, yêu cầu thay thế/xóa file, giới hạn native resource và vòng đời dịch vụ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Java 17: đã gọi `FileChannel.close()` sau khi map. Có thể lập tức `Files.delete(path)` và tin chắc thành công trên mọi OS không?

**Không.** Mapping `MappedByteBuffer` vẫn có thể sống sau khi channel đóng, và hành vi delete/rename với file đang được map phụ thuộc OS.

**Câu 2.** Gọi `mapped.force()` có làm memory mapping bị tháo không?

**Không.** `force()` là yêu cầu đồng bộ dữ liệu xuống thiết bị lưu trữ, không phải unmap.

**Câu 3.** Java 22+: có `FileChannel.map(..., Arena)`, vậy mọi chương trình `MappedByteBuffer` cũ đều được unmap khi đóng channel?

**Không.** API cũ vẫn tạo mapping có vòng đời gắn với GC. Chỉ phương thức map trả `MemorySegment` gắn vào **arena đóng được** mới có hợp đồng đóng arena để unmap theo scope.

**Câu 4.** Dùng `Arena.ofAuto()` có thể gọi `close()` để buộc unmap ngay khi request hoàn tất không?

**Không.** Arena automatic không đóng tường minh được theo mô hình API. Chọn confined/shared arena nếu cần chính sách đóng đúng thời điểm.

**Câu 5.** Sau khi đóng `Arena.ofConfined()`, có nên giữ `MemorySegment` rồi tiếp tục `get` nó không?

**Không.** Scope không còn sống; thao tác truy cập bị từ chối bằng ngoại lệ, thường `IllegalStateException`. Đóng arena thể hiện **kết thúc quyền truy cập** vùng mapping.

## 13. Ghi nhớ và tài liệu chuẩn

- `MappedByteBuffer` từ `FileChannel.map(mode, position, size)` **không có unmap/close chuẩn công khai**; vòng đời mapping gắn với GC và không có thời điểm giải phóng chắc chắn.
- `FileChannel.close()`, `MappedByteBuffer.clear()` và `force()` **không phải thao tác unmap**.
- **Java 22+** có overload `FileChannel.map(mode, offset, size, arena)` trả `MemorySegment`. Với arena đóng được, **đóng arena thành công sẽ unmap** vùng gắn với nó.
- Chọn `Arena.ofConfined()` cho một thread, `Arena.ofShared()` khi cần nhiều thread; `ofAuto()`/`global()` không cung cấp lịch unmap tường minh.
- Tính khả dụng sau truncate, thời điểm ghi xuống thiết bị, hành vi xóa/đổi tên và khả năng đồng thời đều có yếu tố phụ thuộc hệ điều hành/JVM/provider.

**Tài liệu chính thức để đối chiếu phiên bản:**

1. [MappedByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html).
2. [FileChannel — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html), đặc biệt overload `map(..., Arena)` và phần `Since: 22`.
3. [Arena — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html), các loại arena và quy tắc đóng scope.
4. [MemorySegment — Java SE 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html), truy cập mapping, `force()` và vòng đời segment.
