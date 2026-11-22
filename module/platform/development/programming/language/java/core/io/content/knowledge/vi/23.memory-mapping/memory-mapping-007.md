# Đóng FileChannel không tự kết thúc vòng đời vùng ánh xạ

Khi dùng Java NIO để ánh xạ nội dung một tệp vào bộ nhớ, lập trình viên thường viết `FileChannel.map(...)` để lấy `MappedByteBuffer`, sau đó đóng `FileChannel` bằng `try-with-resources`. **Vùng ánh xạ vẫn có thể tiếp tục tồn tại và được truy cập thông qua buffer sau khi channel đã đóng.** Điều này được quy định trong hợp đồng của `FileChannel.map`: vùng ánh xạ đã thiết lập không phụ thuộc vào channel dùng để tạo nó; đóng channel không làm ánh xạ mất hiệu lực.

Điểm này rất quan trọng với vòng đời tài nguyên, khả năng xóa/đổi tên tệp, mức sử dụng bộ nhớ native và cách bảo đảm dữ liệu sửa qua vùng ánh xạ được ghi ra thiết bị lưu trữ. Đóng channel là đúng, nhưng **đóng channel và kết thúc memory mapping là hai việc khác nhau**.

## 1. Phân biệt channel, vùng ánh xạ và mapped buffer

Cần nhận diện ba lớp tài nguyên:

1. **`FileChannel`:** Kênh I/O gắn với một lần mở tệp. Nó có `read`, `write`, `position`, `size`, `map`, `force` và `close`. Khi đóng channel, các thao tác trên chính channel không còn hợp lệ.
2. **Vùng ánh xạ bộ nhớ (memory mapping):** Mối liên hệ do hệ điều hành/provider thiết lập giữa một vùng địa chỉ ảo và một đoạn của tệp. Ánh xạ có vòng đời tài nguyên riêng. Những trang dữ liệu có thể được đưa vào RAM theo yêu cầu; không nên đồng nhất toàn bộ kích thước ánh xạ với RAM vật lý đã được cấp.
3. **`MappedByteBuffer`:** Đối tượng Java biểu diễn vùng ánh xạ và cung cấp `get`, `put`, `position`, `limit`, `force` và các thao tác buffer. Đây là phương tiện Java truy cập vùng ánh xạ sau khi `map` trả về.

Có thể hình dung:

```text
FileChannel (open)
       |
       | map(MapMode.READ_WRITE, offset, size)
       v
MappedByteBuffer -----> vùng địa chỉ ánh xạ -----> dữ liệu tệp
       ^
       | tiếp tục dùng get/put/force
FileChannel (closed)
```

Mũi tên mô tả quan hệ tài nguyên, không phải sơ đồ sở hữu đối tượng chính xác của mọi JVM.

**Đóng channel giải phóng tài nguyên của channel, không tự thu hồi vùng ánh xạ.** Trong khi còn hợp lệ, `MappedByteBuffer` vẫn có thể đọc và, nếu map cho phép, ghi dữ liệu mà không cần giữ `FileChannel` ở trạng thái mở. Ngược lại, không thể gọi `channel.force(...)` trên channel đã đóng chỉ vì một buffer từ channel đó còn tồn tại.

## 2. Tạo vùng ánh xạ bằng `FileChannel.map`

Chữ ký phổ biến:

```java
MappedByteBuffer map(FileChannel.MapMode mode,
                     long position,
                     long size) throws IOException
```

Đây là chữ ký minh họa, không phải một chương trình độc lập.

- `mode` chỉ định chế độ ánh xạ: `READ_ONLY`, `READ_WRITE` hoặc `PRIVATE`.
- `position` là offset **byte trong tệp** nơi ánh xạ bắt đầu; không phải `ByteBuffer.position()`.
- `size` là số byte được ánh xạ. Với overload trả `MappedByteBuffer`, capacity của buffer là kiểu `int` nên vùng ánh xạ cho một buffer phải nằm trong giới hạn capacity; cần chia thành các vùng nếu xử lý tệp rất lớn.
- Trên Java 17, ánh xạ cần được thiết lập qua channel còn mở với quyền phù hợp. Sau khi map thành công, channel có thể được đóng độc lập.

Các chế độ:

| `MapMode` | Cách truy cập | Tác động khi ghi qua buffer |
| --- | --- | --- |
| `READ_ONLY` | Đọc dữ liệu đã ánh xạ | `put` bị từ chối bằng `ReadOnlyBufferException` |
| `READ_WRITE` | Đọc và thay đổi dữ liệu tệp qua mapping | Thay đổi có thể được phản ánh vào tệp; dùng `MappedByteBuffer.force()` khi cần yêu cầu đẩy cập nhật theo hợp đồng API |
| `PRIVATE` | Ánh xạ copy-on-write | Các thay đổi riêng không được ghi trở lại tệp theo ngữ nghĩa private mapping |

`READ_WRITE` cần channel mở với quyền đọc và ghi. Với `READ_ONLY`, cần quyền đọc. Không nên suy ra chế độ ánh xạ từ việc channel có thể `write()` hay không; luôn chọn mode và `StandardOpenOption` phù hợp trước khi gọi `map`.

Việc `map` thành công tạo ánh xạ; thao tác này **không** có nghĩa toàn bộ byte đã được chép vào Java heap hoặc đều đã ở RAM. Hệ điều hành có thể nạp các trang theo nhu cầu truy cập, và JVM có thể sử dụng tài nguyên native ngoài Java heap.

## 3. Chương trình Java 17+ chạy được: channel đã đóng, buffer vẫn dùng được

Chương trình tạo một tệp tạm có năm byte ASCII, ánh xạ với `READ_WRITE`, đóng `FileChannel` khi thoát khối `try`, rồi **mới đọc, sửa và force qua `MappedByteBuffer`**. Nó không dựa vào tên tệp ngẫu nhiên để tạo stdout nên có kết quả rõ ràng.

Tạo tệp **`MappedLifetimeDemo.java`**:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class MappedLifetimeDemo {
    private MappedLifetimeDemo() {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-lifetime-", ".txt");
        // Yêu cầu dọn tệp tạm khi JVM kết thúc; đây là best effort.
        file.toFile().deleteOnExit();

        Files.writeString(file, "ABCDE", StandardCharsets.US_ASCII);
        MappedByteBuffer mapped;

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
            mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 5);
            System.out.println("inside: channelOpen=" + channel.isOpen());
        } // Chỉ channel được đóng tại đây.

        // Vùng ánh xạ vẫn có thể đọc, dù channel đã đóng.
        System.out.println("after close: first=" + (char) mapped.get(0));

        // Ghi thông qua mapping, không mở lại FileChannel để ghi.
        mapped.put(1, (byte) 'Z');
        System.out.println("mapped second=" + (char) mapped.get(1));

        // Yêu cầu đồng bộ thay đổi của mapping với thiết bị lưu trữ.
        mapped.force();
        System.out.println("file after force="
                + Files.readString(file, StandardCharsets.US_ASCII));
    }
}
```

Biên dịch và chạy:

```bash
javac MappedLifetimeDemo.java
java MappedLifetimeDemo
```

Kết quả khi tệp tạm được tạo và truy cập thành công:

```text
inside: channelOpen=true
after close: first=A
mapped second=Z
file after force=AZCDE
```

Tại sao kết quả hợp lý?

1. File `ABCDE` có độ dài 5 byte, nên `map(READ_WRITE, 0, 5)` ánh xạ toàn bộ tệp.
2. `MappedByteBuffer mapped` được khai báo bên ngoài `try`; sau dấu `}`, channel đóng nhưng đối tượng buffer vẫn còn được tham chiếu và vùng ánh xạ còn hợp lệ.
3. `mapped.get(0)` đọc byte `A` từ mapping đã tạo. Nếu thử `channel.read(...)` bên ngoài khối `try` (giả sử còn tham chiếu), thao tác trên channel đã đóng sẽ thất bại.
4. `mapped.put(1, 'Z')` thay byte tại offset 1. Vì đây là `READ_WRITE`, thay đổi có thể được đồng bộ về tệp. `mapped.force()` yêu cầu đẩy thay đổi của mapping, kể cả khi channel gốc đã đóng.
5. `Files.readString(...)` mở lại tệp để đọc và thấy `AZCDE`. Câu lệnh `deleteOnExit()` yêu cầu dọn tệp khi JVM kết thúc, nhưng không phải biện pháp unmap hoặc bảo đảm dọn ngay trên mọi hệ điều hành.

**Lưu ý thực hành:** Không đưa `Files.delete(file)` vào trước khi vùng ánh xạ không còn được sử dụng rồi giả định chắc chắn xóa được trên Windows. Một số hệ thống có thể giữ tài nguyên tệp vì vùng ánh xạ còn sống. Ví dụ dùng `deleteOnExit()` để tránh làm thất bại luồng minh họa bởi thời điểm unmap; lệnh dọn khi thoát cũng chỉ là nỗ lực tốt nhất.

## 4. `close()` khác với unmap như thế nào?

`FileChannel.close()` đóng kênh và giải phóng tài nguyên do lần mở channel sở hữu. Tùy nền tảng, các yêu cầu I/O còn thực hiện có thể bị ảnh hưởng. Sau khi đóng, `channel.isOpen()` trả `false` và những lời gọi yêu cầu channel mở có thể ném `ClosedChannelException`.

**Unmap** là việc chấm dứt ánh xạ, trả lại các tài nguyên liên quan như vùng địa chỉ ảo và tham chiếu tới đối tượng tệp mà hệ điều hành đang quản lý. `MappedByteBuffer` trong Java 17 **không có phương thức public `close()` hoặc `unmap()` tiêu chuẩn** để người sử dụng gọi như đóng channel.

Tài liệu `FileChannel.map` mô tả vùng ánh xạ còn hợp lệ cho đến khi chính buffer trở thành đối tượng có thể bị garbage collection. Đừng suy luận rằng chỉ một biến cục bộ ra khỏi scope, `mapped = null` hoặc một lần GC cụ thể sẽ buộc ánh xạ được tháo *ngay lập tức*. Điều kiện không còn khả năng truy cập và thời điểm thực tế thu hồi là hai chuyện khác nhau.

Các view như `slice()`, `duplicate()` hoặc `asReadOnlyBuffer()` có thể chia sẻ dữ liệu với mapping gốc. Việc giữ một view cho code khác sử dụng có thể giữ liên quan tài nguyên ánh xạ tồn tại; không nên coi bỏ tham chiếu buffer gốc là bằng chứng mọi đối tượng tham chiếu tới dữ liệu đã hết.

So sánh:

| Hành động | Channel | Mapping / buffer |
| --- | --- | --- |
| Thoát `try (FileChannel ch = ...)` | Channel tự đóng | Mapping có thể tiếp tục hoạt động |
| `ch.close()` | Không thể tiếp tục I/O qua ch | Không tự unmap vùng đã ánh xạ |
| `mapped.clear()` | Không ảnh hưởng channel | Chỉ reset position/limit, **không xóa byte và không unmap** |
| `mapped.flip()` | Không ảnh hưởng channel | Chỉ thay đổi trạng thái buffer |
| `mapped.force()` | Không cần channel gốc còn mở | Yêu cầu đồng bộ nội dung vùng ánh xạ có sửa, **không giải phóng mapping** |
| Không còn tham chiếu sử dụng mapping | Channel có thể đã đóng từ trước | Vùng ánh xạ có thể được thu hồi theo cơ chế JVM/GC về sau, thời điểm không tất định |

Trong code quản lý tài nguyên, nên coi **vòng đời FileChannel** và **vòng đời tất cả đối tượng đang dùng mapping** là hai ranh giới rõ ràng.

## 5. Đóng channel có làm dữ liệu tự ghi ra đĩa không?

Không nên đánh đồng **khả năng đọc thấy dữ liệu vừa sửa**, **thời điểm hệ điều hành chuyển dữ liệu từ trang nhớ bẩn xuống thiết bị** và **độ bền dữ liệu sau sự cố mất điện**.

Khi sửa `READ_WRITE` mapping, thay đổi được phản ánh tới nội dung tệp theo cơ chế memory mapping, nhưng JVM không hứa mọi byte đã được lưu bền vững ngay lập tức chỉ vì `put()` trả về. Đối với tệp nằm trên thiết bị lưu trữ cục bộ, `MappedByteBuffer.force()` là API để yêu cầu ghi các thay đổi của vùng mapping về thiết bị theo hợp đồng Java. Với ánh xạ trên một số loại tệp/thiết bị khác, bảo đảm có thể khác hoặc không hoàn toàn được định nghĩa.

**Đóng FileChannel không thay cho `MappedByteBuffer.force()`.** Sau khi đóng channel, buffer còn sống vẫn có thể gọi `force()`. Ngược lại, `channel.force(true)` phải được gọi khi channel còn mở và có hợp đồng liên quan các cập nhật tệp qua channel; không nhầm nó là phương thức giải phóng vùng ánh xạ.

Các mode cũng khác nhau:

- `READ_WRITE`: sửa vùng ánh xạ để tác động nội dung tệp; có thể cần `mapped.force()` theo yêu cầu durability.
- `READ_ONLY`: không sửa dữ liệu qua buffer, `put` bị cấm. Việc gọi `force` không biến nó thành writable.
- `PRIVATE`: ghi theo cơ chế copy-on-write riêng, không ghi các thay đổi của private mapping trở lại tệp. Không dùng `force()` để mong dữ liệu private mapping được persist vào file gốc.

Khi thiết kế cập nhật quan trọng, cần cả chính sách **ngăn ghi chồng**, **xử lý lỗi I/O**, **xác minh nội dung** và **durability**. `force()` không biến một loạt thay đổi byte phức tạp thành một transaction nguyên tử.

## 6. Tại sao file có thể chưa xóa/đổi tên được?

Memory mapping được hệ điều hành quản lý. Tệp có thể còn bị tham chiếu bởi một vùng ánh xạ dù ứng dụng đã đóng descriptor/channel ban đầu.

Hành vi khi `Files.delete(path)`, `Files.move(path, ...)` hoặc truncate tệp được ánh xạ **không đồng nhất trên mọi hệ thống**:

- Trên một số hệ thống kiểu Unix, tên đường dẫn có thể được unlink dù mapping vẫn còn, còn các trang dữ liệu đã ánh xạ vẫn có thể tiếp tục truy cập theo ngữ nghĩa hệ điều hành. Điều này không phải hợp đồng bảo đảm cho mọi provider Java hoặc mọi tình huống.
- Trên Windows, ánh xạ đang hoạt động có thể khiến xóa, di chuyển hoặc thay thế tệp thất bại do tài nguyên hệ điều hành vẫn tham chiếu tới tệp. Đóng channel riêng lẻ chưa bảo đảm giải phóng ràng buộc đó.
- Hệ thống tệp mạng, container, trình diệt virus, file lock và chính sách chia sẻ tệp có thể tạo ra hành vi khác nữa.

Do đó **“channel đã đóng” không đủ làm điều kiện chứng minh tệp có thể xóa ngay**. Nếu quy trình phải thay thế một file theo chu kỳ, cần thiết kế vòng đời sao cho các mapping cũ không còn được sử dụng trước bước xóa/đổi tên, đồng thời xử lý ngoại lệ thực tế từ `Files.delete/move`.

Không nên dùng cơ chế `System.gc()` và vòng đợi để “ép” unmap: `System.gc()` chỉ là yêu cầu/hint đến JVM, không phải cam kết rằng mapping được thu hồi vào thời điểm xác định. Việc gọi các API nội bộ không chuẩn như `Unsafe.invokeCleaner` để cưỡng ép giải phóng có thể phụ thuộc triển khai, phá vỡ an toàn khi mapping còn đang được dùng và không thích hợp làm giải pháp mặc định.

### Không cắt ngắn tệp khi mapping đang được sử dụng

Nếu một vùng đã ánh xạ mà tệp bên dưới bị truncate hoặc nội dung/vùng liên quan không còn truy cập được, việc `get/put` sau đó có thể thất bại với một ngoại lệ **không được Java chỉ định cụ thể**. Đây không phải một kết quả có thể dựa vào một loại exception duy nhất để xử lý mọi nền tảng.

Ứng dụng cần phối hợp lifecycle với code ghi/truncate/xóa tệp. Nếu nhiều tiến trình cùng thao tác, khóa trong Java đơn thuần không bảo vệ được trước một tiến trình khác bỏ qua khóa.

## 7. Mapping còn sống ảnh hưởng tài nguyên nào?

Một memory mapping có thể tiêu thụ **không gian địa chỉ ảo**, metadata native và các trang RAM khi được chạm tới. Không được suy ra rằng vùng ánh xạ dài 1 GiB luôn chiếm 1 GiB RAM vật lý ngay khi `map` trả về. Trên nhiều hệ thống các trang được nạp theo nhu cầu và có thể chịu cơ chế cache/thay trang của OS.

Một file lớn được chia thành hàng trăm mapping và tất cả buffer/view bị lưu trong cache có thể gây áp lực tài nguyên ngay cả khi các `FileChannel` tạo ra chúng đều đã đóng:

- Số lượng mapping/virtual memory ranges và dung lượng không gian địa chỉ có giới hạn.
- Những trang đang hoạt động có thể ảnh hưởng page faults, page cache, bộ nhớ vật lý và hành vi swap.
- Mapped buffers vẫn có các đối tượng/metadata Java; giữ tham chiếu lâu khiến việc thu hồi tài nguyên mapping khó diễn ra.
- Theo dõi riêng Java heap không cho thấy toàn bộ tài nguyên native và memory mapping. Trên JVM có hỗ trợ, `BufferPoolMXBean` với pool `mapped` cung cấp một phần chỉ số; kết hợp với bộ nhớ tiến trình/hệ điều hành mới có bức tranh đầy đủ.

Ví dụ đo chỉ số theo `BufferPoolMXBean` (đoạn minh họa, đặt trong lớp/phương thức Java):

```java
for (java.lang.management.BufferPoolMXBean pool :
        java.lang.management.ManagementFactory.getPlatformMXBeans(
                java.lang.management.BufferPoolMXBean.class)) {
    if ("mapped".equals(pool.getName())) {
        System.out.println("mapped count=" + pool.getCount());
        System.out.println("mapped capacity=" + pool.getTotalCapacity());
        System.out.println("mapped memoryUsed=" + pool.getMemoryUsed());
    }
}
```

Các chỉ số này **không đồng nghĩa** với RSS, page cache, số descriptor mở hoặc toàn bộ native memory; giá trị có thể phụ thuộc JVM. Nếu mapping tích lũy không mong muốn, hãy tìm đối tượng/view vẫn được giữ và kiểm tra chiến lược cache/pool thay vì chỉ nhìn số `FileChannel` đang mở.

## 8. Quản lý vòng đời đúng theo nghiệp vụ

Một số cách thiết kế có thể tránh lệ thuộc vào thời điểm thu hồi mapping:

### 8.1. Giữ phạm vi sử dụng rõ ràng

Tạo mapping, xử lý hoàn tất và ngừng chia sẻ buffer khi kết thúc một tác vụ. Nếu gửi `MappedByteBuffer` sang thread khác hoặc lưu trong cache, phải xem đây là phần kéo dài vòng đời vùng ánh xạ, ngay cả khi channel tạo mapping đã đóng từ lâu.

```java
// Đoạn minh họa: Path file đã có, đọc xong trong một phạm vi rõ ràng.
try (FileChannel channel = FileChannel.open(
        file, java.nio.file.StandardOpenOption.READ)) {
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
    while (mapped.hasRemaining()) {
        process(mapped.get()); // Hàm xử lý nghiệp vụ minh họa.
    }
}
// Channel đã đóng; không còn chủ động dùng mapped.
// Không có lời hứa rằng GC/unmap sẽ xảy ra đúng tại dấu }.
```

Đoạn trên **không độc lập**: cần import `MappedByteBuffer`, `FileChannel`, khai báo `file`, hàm `process` và xử lý `IOException`. Với file quá lớn cho một `MappedByteBuffer`, phải chia thành các vùng phù hợp. Với file có thể rỗng, logic xử lý cần cân nhắc cách ứng dụng muốn xử lý vùng kích thước 0.

### 8.2. Dùng `FileChannel.read/write` nếu cần đóng tài nguyên có thể dự đoán

Nếu yêu cầu là “xử lý xong thì có thể nhanh chóng đóng và thay thế/xóa file”, nhưng ứng dụng không có nhu cầu memory mapping rõ ràng, dùng đọc/ghi từng khối qua `FileChannel` với `ByteBuffer` thông thường là lựa chọn đáng cân nhắc. Một channel đóng được theo phạm vi `try-with-resources` sẽ đơn giản hơn về ownership của tài nguyên mapping.

Tuy nhiên `FileChannel` và bộ đệm thường cũng cần quản lý concurrency, ngoại lệ và trạng thái đọc/ghi. Không nên cho rằng đổi sang `read/write` sẽ tự giải quyết toàn bộ lỗi chia sẻ dữ liệu.

### 8.3. Chia vùng lớn và tránh giữ mapping thừa

Khi bắt buộc memory-map file lớn, ánh xạ theo các vùng vừa đủ để xử lý; chỉ giữ các vùng mà tác vụ thực sự đang dùng. Tránh lưu mọi mapping trong danh sách có vòng đời dài vô hạn. Nếu tái sử dụng mapping giữa các request, cần giới hạn số lượng, chủ sở hữu và cách hủy cache khi dữ liệu nền thay đổi.

### 8.4. Không áp dụng mẹo “explicit unmap” không chuẩn

Các phiên bản Java mới có những cơ chế quản lý vùng bộ nhớ khác nhau, nhưng trong phạm vi API `MappedByteBuffer` của **Java 17**, không có thao tác public `unmap()` để bảo đảm kết thúc ánh xạ đồng bộ. Không viết thư viện phụ thuộc reflection vào nội bộ JDK chỉ để giải phóng mapping đúng một thời điểm; cần lựa chọn API và kiến trúc tài nguyên phù hợp thay thế nếu vòng đời xác định là yêu cầu cứng.

## 9. Một số ngộ nhận quan trọng

| Ngộ nhận | Thực tế và cách xử lý |
| --- | --- |
| “Ra khỏi `try(FileChannel ...) `là mapping hết hiệu lực.” | Channel đã đóng, nhưng `MappedByteBuffer` vẫn có thể truy cập vùng ánh xạ; ví dụ trên minh họa trực tiếp. |
| “`MappedByteBuffer.clear()` giải phóng file mapping.” | `clear()` chỉ reset position và limit, không unmap. |
| “Đóng channel luôn làm byte sửa qua mapping bền vững trên đĩa.” | Độ bền dữ liệu là vấn đề riêng; dùng `MappedByteBuffer.force()` khi cần theo hợp đồng áp dụng. |
| “Đóng channel xong luôn xóa/đổi tên file được.” | Mapping còn sống có thể cản thao tác trên một số OS; phải kiểm tra và xử lý lỗi. |
| “Gọi `System.gc()` sẽ unmap ngay.” | Không có bảo đảm thu hồi ngay; không dựa vào GC làm giao thức đóng tài nguyên xác định. |
| “Một mapping 2 GiB đồng nghĩa đã dùng 2 GiB RAM vật lý.” | Dung lượng vùng địa chỉ ánh xạ không đồng nghĩa với RSS/page cache thực đang cư trú. |
| “`MappedByteBuffer.force()` làm mapping kết thúc.” | `force()` yêu cầu ghi dữ liệu đã sửa, không thu hồi vùng ánh xạ. |
| “Có thể truncate file dưới một mapping mà mọi byte buffer vẫn đọc được như cũ.” | Truy cập vùng không còn hợp lệ có thể thất bại bằng ngoại lệ không được chỉ định cụ thể. |
| “Private mapping lưu thay đổi vào file khi force.” | `MapMode.PRIVATE` dùng copy-on-write riêng, không có ngữ nghĩa persist thay đổi vào file gốc. |

## 10. Cách tự kiểm tra vòng đời

Có thể mở rộng chương trình `MappedLifetimeDemo` để kiểm chứng các giả định theo cách có kiểm soát:

1. In `channel.isOpen()` trong khối `try`, rồi **sau khi ra khỏi khối** đọc buffer. Quan sát channel kết thúc vòng đời trước nhưng buffer vẫn truy cập được.
2. Đổi `READ_WRITE` thành `READ_ONLY` và chỉ thực hiện `get()`; thử `put()` riêng để quan sát `ReadOnlyBufferException`.
3. Tạo một view `slice()` rồi sửa dữ liệu qua view trong phạm vi hợp lệ; chú ý view chia sẻ nội dung và có thể kéo dài vòng đời vùng ánh xạ.
4. Chạy thử thao tác xóa/đổi tên **trên tệp tạm riêng** khi mapping còn sống để quan sát hành vi hệ điều hành; xử lý `IOException` thay vì giả định kết quả giống nhau mọi nơi. Không thử trên dữ liệu đang dùng thật.
5. Theo dõi chỉ số memory pool `mapped` và OS process memory khi tạo/giải phóng tham chiếu nhiều mapping; không dùng một lần gọi GC để suy ra thời điểm unmap được bảo đảm.

**Ghi nhớ:** `FileChannel.map()` tạo một vùng ánh xạ có vòng đời độc lập với `FileChannel` dùng để tạo ra nó. `try-with-resources` đóng channel đúng cách nhưng **không tự đóng `MappedByteBuffer`**, không buộc unmap tức thì và không tự bảo đảm có thể xóa/di chuyển file hoặc ghi bền vững mọi sửa đổi. Thiết kế cần quản lý riêng thời gian sử dụng mapping, chính sách đồng bộ dữ liệu và hoạt động bảo trì tệp.