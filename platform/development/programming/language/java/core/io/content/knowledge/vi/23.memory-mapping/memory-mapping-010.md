# Khi nào memory mapping có ích và khi nào gây bất lợi trong Java NIO.2

## 1. Memory mapping là gì?

**Memory mapping (ánh xạ tệp vào bộ nhớ)** cho phép chương trình làm việc với một vùng nội dung tệp thông qua các thao tác đọc/ghi trên bộ đệm được ánh xạ vào **không gian địa chỉ ảo** của tiến trình. Hệ điều hành liên kết các trang bộ nhớ ảo với dữ liệu tệp và đưa những trang cần thiết vào RAM theo cơ chế quản lý bộ nhớ của nó.

Trong Java NIO.2, cách sử dụng phổ biến là gọi `FileChannel.map(...)` để nhận `MappedByteBuffer`:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
    byte firstByte = mapped.get(0);
}
~~~

Đây là **đoạn minh họa**, cần các import `java.nio.MappedByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Path` và `java.nio.file.StandardOpenOption`, với `path` là một tệp có ít nhất một byte.

`MappedByteBuffer` kế thừa `ByteBuffer`, nên có thể dùng các phép đọc/ghi theo vị trí tương đối hoặc tuyệt đối, chẳng hạn `get()`, `get(int)` và `put(int, byte)` (nếu mapping cho phép ghi).

**Memory mapping không có nghĩa là tải toàn bộ tệp vào Java heap**. Vùng mapping thuộc địa chỉ ảo và do hệ điều hành quản lý; những trang được truy cập có thể được nạp vào bộ nhớ vật lý khi cần. Java heap vẫn chứa đối tượng quản lý bộ đệm và các đối tượng khác của chương trình. Vì thế, một ứng dụng có thể dùng ít heap nhưng vẫn gây áp lực RAM, page cache và không gian địa chỉ.

Mục tiêu của bài: biết **trường hợp nào mapping có lợi**, **chi phí và rủi ro nào khiến mapping bất lợi**, và **cách chọn đúng công cụ I/O** dựa trên kiểu truy cập.

## 2. Cơ chế hoạt động ở mức cần biết

Khi gọi:

~~~java
MappedByteBuffer buffer = channel.map(
        FileChannel.MapMode.READ_ONLY, startOffset, length);
~~~

ứng dụng yêu cầu một vùng ánh xạ tệp bắt đầu tại offset `startOffset`, dài `length` byte. Việc tạo mapping không đồng nghĩa mọi byte trong vùng đã nằm sẵn trong RAM.

Một chuỗi sự kiện thường gặp:

1. Chương trình tạo mapping giữa vùng địa chỉ ảo và vùng tệp.
2. Khi chạm tới trang chưa có sẵn trong bộ nhớ, CPU/hệ điều hành có thể phát sinh **page fault** để thiết lập ánh xạ trang hoặc đưa dữ liệu từ thiết bị lưu trữ vào bộ nhớ.
3. Khi trang đã sẵn sàng, chương trình đọc/ghi qua buffer mà không cần gọi `FileChannel.read(...)`/`write(...)` ở từng thao tác.
4. Với mapping có quyền ghi, các trang bị sửa có thể trở thành **dirty pages** và được hệ điều hành ghi trở lại thiết bị theo chính sách của nó; ứng dụng có thể yêu cầu đồng bộ bằng `MappedByteBuffer.force()`.

Page fault **không phải lúc nào cũng là đọc từ đĩa**: có thể chỉ cần ánh xạ tới một trang đã nằm trong page cache (minor fault). Nếu phải chờ I/O lưu trữ, độ trễ có thể lớn hơn đáng kể (major fault). Mapping chỉ thay đổi con đường truy cập dữ liệu; nó không loại bỏ chi phí I/O hoặc bảo đảm độ trễ thấp.

### Ba chế độ `FileChannel.MapMode`

| Chế độ | Đọc/ghi trong mapping | Ý nghĩa |
| --- | --- | --- |
| `READ_ONLY` | Đọc; cố ghi sẽ gặp `ReadOnlyBufferException` | Phù hợp khi chỉ tra cứu/duyệt dữ liệu không cần cập nhật |
| `READ_WRITE` | Đọc và ghi | Thay đổi buffer được ánh xạ vào vùng tệp; cân nhắc `force()` khi cần yêu cầu ghi xuống thiết bị |
| `PRIVATE` | Có thể đọc và sửa trong vùng nhìn thấy của mapping | Cơ chế copy-on-write: thay đổi không được ghi vào tệp nguồn qua mapping này; không dùng để lưu cập nhật bền vững |

`MapMode.PRIVATE` **không đồng nghĩa đã sao chép toàn bộ tệp ngay khi map**. Các trang cần thay đổi được xử lý theo cơ chế copy-on-write của nền tảng; hành vi nhìn thấy các sửa đổi khác của tệp sau thời điểm mapping không nên được giả định là nhất quán.

## 3. Khi nào memory mapping thường có ích?

### 3.1. Truy cập ngẫu nhiên nhiều lần vào những vùng dữ liệu lớn

Ví dụ: tệp chỉ mục nhị phân có bản ghi cố định, mỗi bản ghi dài 32 byte, và chương trình cần đọc hàng nghìn bản ghi ở các offset khác nhau.

Với `FileChannel.read(dst, position)`, ứng dụng thường phải chuẩn bị `ByteBuffer`, gọi đọc và kiểm tra số byte nhận được. Với mapping, sau khi tạo vùng ánh xạ, có thể truy cập byte ở offset cần thiết trực tiếp qua `get(int)` (trong giới hạn của buffer).

~~~java
// Minh họa với mapping đang mở, recordSize = 32.
int recordSize = 32;
int recordIndex = 7;
int offset = Math.multiplyExact(recordIndex, recordSize);
byte type = mapped.get(offset);
~~~

Đoạn này minh họa truy cập có vị trí; cần chắc chắn `offset` còn nằm trong vùng mapping và `mapped` có ít nhất `offset + 1` byte. Với tệp lớn phải tính offset toàn cục bằng `long` rồi xác định cửa sổ mapping phù hợp trước khi đổi thành chỉ số `int`.

**Lợi ích tiềm năng:** giảm công việc sao chép sang bộ đệm trung gian và số lời gọi đọc có chủ đích ở cấp ứng dụng; thuận tiện với các cấu trúc được thiết kế để đọc trực tiếp từ một vùng byte.

**Điều kiện:** mô hình truy cập, kích thước tập dữ liệu, page cache, CPU và hệ thống tệp thực sự phù hợp. Truy cập ngẫu nhiên trên thiết bị chậm có thể vẫn chịu nhiều page fault và nhanh chóng trở thành nút thắt.

### 3.2. Tệp chỉ đọc được truy cập lặp đi lặp lại

Một bộ tra cứu từ điển, bảng mã, bảng chỉ mục hoặc dữ liệu nhị phân lớn nhưng tương đối ổn định có thể được ánh xạ một lần rồi truy vấn nhiều lần. Khi những trang được dùng thường xuyên đã có sẵn, các lần đọc tiếp theo có khả năng tận dụng cache của hệ điều hành.

Cách dùng phổ biến:

- Tạo mapping `READ_ONLY` trong vòng đời thành phần truy vấn.
- Xác định định dạng tệp, byte order, offset, kích thước bản ghi và xử lý dữ liệu lỗi.
- Không tạo/hủy mapping ở từng yêu cầu nhỏ; cân nhắc tái sử dụng mapping khi vòng đời dữ liệu cho phép.

Đây là **mẫu ứng dụng có thể có lợi**, không phải cam kết tốc độ vượt mọi phương án khác: `FileChannel` và buffered I/O cũng tận dụng page cache.

### 3.3. Chia sẻ dữ liệu đọc với các tiến trình trên cùng máy

Nếu nhiều tiến trình ánh xạ cùng một vùng tệp, hệ điều hành có thể chia sẻ các trang dữ liệu vật lý/page cache tương ứng. Với tập dữ liệu chỉ đọc hoặc mô hình chia sẻ được thiết kế cẩn thận, cách này có thể giảm nhu cầu duy trì các bản sao dữ liệu độc lập trong heap của từng tiến trình.

Tuy nhiên, **memory mapping không thay thế giao thức đồng bộ giữa các tiến trình**. Đối với cập nhật đồng thời, phải xác định rõ tính nhất quán, thứ tự công bố dữ liệu, khóa và giới hạn của nền tảng. `MappedByteBuffer` không tự cung cấp transaction, snapshot nhất quán hoặc cơ chế thông báo sự kiện.

### 3.4. Xử lý cấu trúc nhị phân theo vùng

Các tệp chứa header, record cố định hoặc các bảng offset thường phù hợp hơn với mapping so với dữ liệu văn bản phải phân tích tuần tự phức tạp. Chẳng hạn, một file chứa 1 triệu record có header định nghĩa chiều dài từng record: ứng dụng ánh xạ một cửa sổ cần thiết rồi dùng `getInt(...)`, `getLong(...)`, `slice()` và `order(ByteOrder...)` để giải mã các trường.

Trong ứng dụng thực tế phải kiểm tra:

- Endianness (thứ tự byte) được định nghĩa rõ: mặc định `ByteBuffer` dùng big-endian nếu chưa đặt khác.
- Mọi offset và kích thước đều nằm trong phạm vi hợp lệ trước khi đọc.
- Bộ đệm không được dùng ngoài vòng đời dữ liệu mà hệ thống tệp có thể thay đổi nguy hiểm.
- Việc ánh xạ theo cửa sổ để xử lý tệp vượt giới hạn kích thước một `ByteBuffer`.

## 4. Những trường hợp mapping có thể gây bất lợi

### 4.1. Tệp nhỏ, chỉ đọc/ghi một lần

Nếu một chương trình chỉ đọc tệp cấu hình vài kilobyte, `Files.readString(path)` hoặc `Files.readAllBytes(path)` thường đơn giản và ít ràng buộc hơn. Memory mapping có chi phí tạo/quản lý vùng ánh xạ, xử lý page fault và vòng đời tài nguyên; chi phí này có thể lớn hơn lợi ích với dữ liệu nhỏ hoặc sử dụng một lần.

Tương tự, khi cần **sao chép tuần tự** từ một tệp sang tệp khác, `Files.copy`, `InputStream`/`OutputStream`, `FileChannel.transferTo` hoặc bộ đệm tuần tự thường dễ hiểu hơn. Việc ánh xạ không tự động là đường sao chép tệp nhanh nhất.

### 4.2. Truy cập ngẫu nhiên vào tập dữ liệu lớn hơn RAM, thiếu tính cục bộ

Memory mapping có thể tiện khi mô hình truy cập ngẫu nhiên, nhưng nếu mỗi lần đọc chạm tới một trang mới và tập dữ liệu lớn vượt xa RAM, số lần thiếu trang và I/O tăng. Kết quả có thể là độ trễ tăng mạnh, tranh chấp page cache và làm chậm các ứng dụng khác trên máy.

Một buffer được ánh xạ không có nghĩa dữ liệu đã được “cache toàn bộ”. Nếu ứng dụng thường xuyên đọc vùng mới trên ổ chậm, hãy cân nhắc index nhỏ hơn, caching theo tầng, batch đọc hoặc bố trí dữ liệu theo thứ tự truy cập.

### 4.3. Hệ thống yêu cầu độ trễ ổn định, dự đoán được

Truy cập mapped memory có thể kích hoạt page fault **ngay ở biểu thức `get(...)` hoặc `put(...)`**, khiến độ trễ xảy ra ở vị trí ít hiển nhiên trong mã. Điều này khó kiểm soát khi ứng dụng có yêu cầu tail latency nghiêm ngặt.

`MappedByteBuffer.load()` có thể yêu cầu hệ thống cố gắng nạp các trang, nhưng **không phải cam kết mọi trang sẽ luôn cư trú trong RAM**, cũng không loại bỏ khả năng các trang bị thu hồi sau đó. `isLoaded()` chỉ cung cấp thông tin gần đúng/tạm thời; không dùng làm chứng nhận thời gian đọc sẽ ổn định.

Nếu cần kiểm soát lịch đọc, batching, backpressure và timeout rõ ràng, đọc tường minh qua `FileChannel`/buffer có thể dễ quản trị hơn.

### 4.4. Tệp thường xuyên đổi kích thước, bị xóa/đổi tên hoặc ghi lại

Mapping có vòng đời độc lập phần nào với `FileChannel`. Đóng channel **không lập tức hủy vùng ánh xạ**; buffer có thể còn tham chiếu tới vùng mapped memory.

Nếu tệp bị truncate khi buffer vẫn có thể truy cập vùng cũ, hành vi truy cập phần không còn hợp lệ có thể dẫn tới lỗi không dự đoán được theo triển khai. API không bảo đảm một cơ chế tự động làm mới mapping an toàn sau mọi thay đổi tệp.

Một số hệ điều hành, đặc biệt Windows, có thể hạn chế đổi tên/xóa/resize tệp khi mapping còn tồn tại. Do đó, các quy trình thường xuyên thay file bằng cách rename hoặc truncate có thể gặp vấn đề vòng đời và cleanup.

**Quy tắc thực hành:** Khi dữ liệu cần thay thế thường xuyên, hãy cân nhắc mô hình tạo tệp phiên bản mới, chuyển tham chiếu theo giao thức ứng dụng, chờ người dùng của mapping cũ kết thúc rồi mới dọn tệp. Tránh vừa sử dụng mapping vừa sửa/truncate file một cách không điều phối.

### 4.5. Tạo rất nhiều mapping ngắn hạn

Mỗi mapping sử dụng tài nguyên bộ nhớ ảo và tài nguyên quản lý của hệ điều hành/JVM. Tạo hàng nghìn mapping cho các tệp nhỏ hoặc tạo mapping mới cho từng request có thể tăng áp lực quản lý trang và tài nguyên native.

`MappedByteBuffer` ở Java 17 **không cung cấp phương thức `close()` hoặc `unmap()` công khai chuẩn**. Vùng ánh xạ tồn tại cho đến khi bộ đệm đủ điều kiện được thu gom và triển khai giải phóng tài nguyên. Dựa vào GC để giải phóng ngay lập tức là không an toàn; ép `System.gc()` cũng không phải hợp đồng thu hồi mapping đáng tin.

Nếu cần vòng đời ánh xạ chặt chẽ, hãy xem xét lựa chọn API phù hợp phiên bản JDK hoặc chuyển sang FileChannel I/O thông thường. Đừng dựa vào API nội bộ của JDK để “unmap ngay” trong chương trình portable.

### 4.6. Dữ liệu cần giải mã, giải nén hoặc biến đổi lớn

Nếu dữ liệu nằm trong tệp nén/mã hóa và cần giải nén/giải mã trước khi sử dụng, byte thô được map vào không tự biến thành dữ liệu đã xử lý. Ứng dụng vẫn cần chuỗi xử lý riêng, buffer phù hợp và kiểm soát bảo mật.

Mapping có thể giúp truy cập tệp chứa dữ liệu mã hóa theo block, nhưng lợi ích phụ thuộc định dạng, tính cục bộ và thiết kế truy cập. Với xử lý theo luồng (streaming transform), `InputStream`, `ReadableByteChannel` và buffer tường minh thường hợp lý hơn.

## 5. Ví dụ chạy độc lập với Java 17+: đọc, cập nhật, đồng bộ

Ví dụ sau tạo tệp ASCII dài 10 byte, ánh xạ bằng `READ_WRITE`, đọc/sửa byte đầu ở vị trí tuyệt đối, gọi `force()` rồi đọc lại qua API tệp để kiểm tra.

Lưu thành **`MemoryMappingDecisionDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MemoryMappingDecisionDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("memory-mapping-", ".dat");

        try {
            Files.write(file,
                    "ABCDE12345".getBytes(StandardCharsets.US_ASCII));

            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                MappedByteBuffer mapped = channel.map(
                        FileChannel.MapMode.READ_WRITE, 0, channel.size());

                System.out.println("File size: " + channel.size());
                System.out.println("First before: " + (char) mapped.get(0));

                mapped.put(0, (byte) 'Z');
                mapped.force();

                System.out.println("First after: " + (char) mapped.get(0));
                System.out.println("Channel position: " + channel.position());
            }

            System.out.println("File content: "
                    + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            // Trên một số nền tảng, file còn có thể bị giữ bởi mapping.
            // Dọn tạm theo best effort để demo vẫn kết thúc rõ ràng.
            try {
                Files.deleteIfExists(file);
            } catch (IOException cleanupFailure) {
                file.toFile().deleteOnExit();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MemoryMappingDecisionDemo.java
java MemoryMappingDecisionDemo
~~~

Trong trường hợp I/O bình thường, stdout:

~~~text
File size: 10
First before: A
First after: Z
Channel position: 0
File content: ZBCDE12345
~~~

**Giải thích:**

1. Tệp được ghi sẵn 10 byte trước khi map; vùng mapping hợp lệ và không phụ thuộc hành vi nền tảng khi ánh xạ qua cuối tệp.
2. `channel.map(READ_WRITE, 0, channel.size())` ánh xạ toàn bộ vùng dữ liệu đã tồn tại. Việc map không tự đổi `channel.position()`.
3. `mapped.get(0)` và `mapped.put(0, ...)` là thao tác **absolute access** trên `ByteBuffer`, không tăng vị trí nội bộ của buffer; nội dung vị trí 0 đổi từ `A` thành `Z`.
4. `mapped.force()` yêu cầu ghi các thay đổi trong mapping xuống thiết bị lưu trữ theo hợp đồng API cho mapping ghi. Đây không phải transaction, không chứng minh mọi metadata đã được đồng bộ hoặc bảo đảm khả năng khôi phục bất chấp sự cố mọi loại thiết bị/hệ thống tệp.
5. `Files.readString(...)` kiểm tra nội dung sau khi cập nhật, còn `channel.position() == 0` minh họa rằng thao tác mapping không tác động vị trí I/O tường minh của channel.
6. `try-with-resources` đóng `FileChannel`; tuy nhiên mapping **không có cùng vòng đời với channel**. Cleanup có thể bị trì hoãn trên một số hệ điều hành, nên ví dụ sử dụng dọn tạm theo best effort. `deleteOnExit()` chỉ là giải pháp phụ cho tệp tạm trong demo, không phải cơ chế quản lý mapping đáng tin trong dịch vụ chạy lâu dài.

### Vì sao ví dụ dùng ASCII?

Vị trí `get(0)` và `put(0)` xử lý **byte**, không phải ký tự Unicode. Với UTF-8, một ký tự có thể cần nhiều byte và việc sửa một byte ngẫu nhiên có thể phá hỏng chuỗi. Memory mapping phù hợp với cấu trúc nhị phân đã có schema/encoding rõ ràng hơn là chỉnh văn bản Unicode tại offset ngẫu nhiên.

## 6. Các giới hạn kỹ thuật quan trọng

### 6.1. Mỗi `MappedByteBuffer` dùng chỉ số `int`

Dù `FileChannel.map(...)` nhận `long position` và `long size`, đối tượng trả về là một `MappedByteBuffer` với `capacity()` kiểu `int`. Trong Java 17, độ dài của **một mapping** không vượt `Integer.MAX_VALUE` byte.

Vì vậy, không map một lần toàn bộ tệp 10 GiB. Hãy chia thành các **cửa sổ (windows)**:

~~~java
long fileSize = channel.size();
long offset = 0;
final long windowBytes = 64L * 1024 * 1024;

while (offset < fileSize) {
    int size = (int) Math.min(windowBytes, fileSize - offset);

    MappedByteBuffer window = channel.map(
            FileChannel.MapMode.READ_ONLY, offset, size);

    // Đọc/giải mã dữ liệu trong window (size byte).
    // Dữ liệu record giao giữa hai cửa sổ phải được xử lý riêng.

    offset += size;
}
~~~

Đây là **đoạn minh họa**, cần `channel` mở ở chế độ đọc, import `FileChannel` và `MappedByteBuffer`. Để tránh giữ nhiều mapping cũ cùng lúc, hãy thiết kế bộ quản lý cửa sổ và mức đồng thời phù hợp; việc thay biến `window` không bảo đảm mapping cũ được giải phóng ngay.

Nếu một bản ghi nằm vắt qua hai cửa sổ, xử lý phần dư giữa các cửa sổ hoặc thiết kế cửa sổ chồng lấn có kiểm soát. Không âm thầm làm rơi phần cuối của bản ghi.

### 6.2. Bộ nhớ ảo khác heap và RAM vật lý

Khi đánh giá memory mapping, theo dõi **nhiều chỉ số cùng lúc**:

- **Java heap:** nơi đặt các đối tượng Java, không phản ánh trực tiếp toàn bộ mapped pages.
- **Virtual address space:** vùng địa chỉ được giữ để ánh xạ, có thể lớn hơn nhiều so với lượng RAM đang sử dụng.
- **Resident memory / page cache:** trang thực sự hiện diện trong RAM; tăng khi truy cập mapping và có thể bị hệ điều hành thu hồi.
- **Page faults, disk I/O, CPU và latency:** cho thấy đường đi của bộ nhớ có thực sự giúp hiệu năng hay không.

Một heap nhỏ **không chứng minh ứng dụng dùng ít tài nguyên hệ thống**. Giới hạn container, bộ nhớ native, địa chỉ ảo và các tiến trình khác đều có thể ảnh hưởng.

### 6.3. Mapping không đồng nghĩa dữ liệu luôn sẵn trong RAM

~~~java
mapped.load();           // Gợi ý cố gắng nạp trang.
boolean loaded = mapped.isLoaded();
~~~

Đây là API minh họa sử dụng trên một `MappedByteBuffer` đã tạo. `load()` có thể tốn thời gian đáng kể và không bảo đảm trang không bị thu hồi sau đó. `isLoaded()` không thay thế phép đo page faults hoặc kiểm soát cache của hệ điều hành.

### 6.4. Tính nhất quán khi tệp thay đổi

Mapping đang hoạt động trong lúc bên khác sửa, truncate hoặc thay file là trường hợp cần **giao thức ứng dụng rõ ràng**. Không suy ra rằng mọi thay đổi ngoài mapping sẽ xuất hiện tức thì và nhất quán trong từng thao tác đọc. Không dùng mapping làm snapshot giao dịch khi không có cơ chế snapshot thật.

Với dữ liệu cấu hình/chỉ mục thay phiên bản, có thể dùng các tệp chỉ đọc bất biến cho từng phiên bản và chuyển sang phiên bản mới ở mức đối tượng quản lý; chỉ giải phóng mapping cũ khi không còn độc giả. Đây là **hướng thiết kế**, không phải tính năng được `MappedByteBuffer` tự cung cấp.

## 7. So sánh với các cách I/O khác

| Nhu cầu | Memory mapping | Lựa chọn khác thường phù hợp |
| --- | --- | --- |
| Truy vấn vị trí ngẫu nhiên nhiều lần trong file nhị phân ổn định | **Đáng thử**: truy cập theo offset trực tiếp, tận dụng cache | `FileChannel.read(buffer, position)` nếu muốn kiểm soát I/O tường minh |
| Cùng tập dữ liệu chỉ đọc được dùng lâu dài | **Đáng thử**, nếu quản lý vòng đời mapping tốt | FileChannel với cache ứng dụng |
| Sao chép file nguyên vẹn một lần | Không phải lựa chọn mặc định | `Files.copy` hoặc `FileChannel.transferTo/transferFrom` |
| Đọc văn bản nhỏ một lần | Thường thêm độ phức tạp | `Files.readString`, `BufferedReader` |
| Truyền dữ liệu mạng trực tiếp | Mapping không tự giải quyết backpressure và network | `SocketChannel`, luồng/buffer; `transferTo` khi thích hợp |
| Tệp thay thế/truncate liên tục | Rủi ro mapping cũ và tài nguyên bị giữ | I/O tường minh, versioned immutable files |
| Tệp lớn hơn 2 GiB | Phải tổ chức mapping theo cửa sổ | `FileChannel` với buffer có kích thước cố định |
| Phải kiểm soát latency, cancellation, timeout | Page fault có thể khó dự đoán | Đọc/ghi theo lô tường minh, kiến trúc async phù hợp |
| Cần giải mã/giải nén theo luồng | Chỉ có ích nếu định dạng hỗ trợ random access rõ ràng | Stream hoặc pipeline ByteBuffer |
| Ghi cập nhật đòi hỏi giao dịch/durability | Cần thêm giao thức đồng bộ, xác nhận tính toàn vẹn | Cơ sở dữ liệu hoặc log giao dịch phù hợp |

**Không có một phương pháp nhanh nhất cho mọi máy và mọi workload.** Ưu điểm của mapping phụ thuộc phân bố offset đọc, tỷ lệ đọc/ghi, kích thước tệp, cache, thiết bị lưu trữ và vòng đời dữ liệu.

## 8. Cách quyết định trong dự án thực tế

Thay vì chọn công nghệ theo tên gọi “zero-copy”, hãy kiểm tra lần lượt các câu hỏi sau:

1. **Truy cập kiểu gì?** Nếu chỉ đọc/ghi tuần tự một lần, dùng buffered/FileChannel thông thường làm baseline. Nếu nhiều random access lặp lại trong một file ổn định, mapping là ứng viên tốt.
2. **Tệp thay đổi thế nào?** Tệp bất biến/read-only dễ quản lý mapping. File thường bị truncate, resize hoặc thay tên cần phương án vòng đời cẩn thận.
3. **Kích thước và phạm vi đọc?** Nếu file vượt 2 GiB, lập kế hoạch window. Nếu phần dùng thường xuyên rất nhỏ, có thể chỉ map/đọc phần nóng.
4. **Độ trễ quan trọng tới đâu?** Nếu phục vụ request nhạy với page fault, cần đo P95/P99 chứ không chỉ throughput trung bình.
5. **Giới hạn tài nguyên là gì?** Kiểm tra heap, RSS, page cache, địa chỉ ảo, số mapping, giới hạn container và quyền truy cập file.
6. **Có cần cập nhật bền vững không?** Với `READ_WRITE`, xác định điểm gọi `force()`, giao thức khôi phục và kiểm tra tính toàn vẹn. Không xem `force()` là giao dịch đa bước.
7. **Đo đạc ra sao?** So sánh ít nhất memory mapping với `FileChannel.read/write` hoặc streaming I/O trên cùng workload, cùng kích thước file và điều kiện máy; đo cold cache/warm cache riêng, page faults, throughput, CPU, RSS và tail latency.

### Ví dụ tình huống

**Tình huống A — bộ từ điển nhị phân chỉ đọc 3 GiB, truy vấn ngẫu nhiên liên tục:** Mapping theo cửa sổ hoặc kiến trúc hỗ trợ mapping phân đoạn là phương án có cơ sở để benchmark. Thời gian truy vấn có thể giảm khi trang nóng được cache. Cần giải quyết kích thước window, cấu trúc bản ghi và vòng đời mapping.

**Tình huống B — dịch vụ nhận file upload rồi sao chép sang thư mục khác:** Không cần map chỉ để sao chép tuần tự. `Files.copy` hoặc các API channel/stream có cơ chế kiểm soát lỗi và backpressure rõ ràng thường đơn giản hơn.

**Tình huống C — file cấu hình vài KiB thay mới liên tục bằng rename:** `Files.readString` và giữ cấu hình đã parse trong bộ nhớ có thể phù hợp hơn. Mapping tạo thêm rủi ro giữ file cũ và sự phức tạp khi thay phiên bản.

**Tình huống D — hệ thống ghi record trực tiếp trong file với yêu cầu crash recovery:** Mapping `READ_WRITE` có thể hữu ích nhưng không giải quyết atomicity, journal, thứ tự flush, kiểm tra dữ liệu hay phục hồi. Cần thiết kế giao thức lưu trữ hoặc dùng hệ quản trị dữ liệu thích hợp.

## 9. Sai lầm thường gặp

**Sai lầm 1 — “Map xong là toàn bộ file đã vào RAM.”** Không. Mapping là địa chỉ ảo và thường đưa trang vào bộ nhớ theo nhu cầu. `load()` không phải cơ chế pin RAM vĩnh viễn.

**Sai lầm 2 — “Không dùng heap nên không tốn bộ nhớ.”** Không. Mapping dùng địa chỉ ảo, RAM/page cache và tài nguyên native; chỉ riêng biểu đồ heap không phản ánh đủ.

**Sai lầm 3 — “MappedByteBuffer cho phép map một file lớn tùy ý thành một buffer.”** Không trong API `MappedByteBuffer` Java 17: giới hạn `int` của capacity khiến cần nhiều cửa sổ nếu file đủ lớn.

**Sai lầm 4 — “Đóng FileChannel sẽ unmap ngay.”** Không. Mapping có vòng đời riêng và không có `close()` công khai chuẩn trên `MappedByteBuffer`.

**Sai lầm 5 — “Map luôn nhanh hơn read/write.”** Không. Page fault, layout dữ liệu, CPU/cache, workload, và overhead khởi tạo có thể làm mapping chậm hơn.

**Sai lầm 6 — “MappedByteBuffer.force() bảo đảm toàn bộ transaction thành công.”** Không. API không thực hiện transaction, không tự phối hợp các file và không tự làm cho bản ghi cập nhật nguyên tử.

**Sai lầm 7 — “Có thể truncate file trong khi các thread vẫn đọc mapping.”** Nguy hiểm. Truy cập vùng không còn hợp lệ có thể dẫn tới lỗi phụ thuộc triển khai; cần điều phối vòng đời dữ liệu.

**Sai lầm 8 — “Byte offset cũng là ký tự offset.”** Không, đặc biệt với UTF-8/UTF-16; việc giải mã phải theo encoding và ranh giới ký tự hoặc schema nhị phân.

**Sai lầm 9 — “PRIVATE mapping sẽ ghi thay đổi trở lại file khi force.”** Không. `PRIVATE` dùng semantics copy-on-write, không phù hợp để lưu thay đổi vào tệp nguồn.

**Sai lầm 10 — “Dùng mmap là tự động zero-copy cho cả truyền mạng.”** Không. Tối ưu truyền dữ liệu tới socket là vấn đề khác, với API và phụ thuộc nền tảng riêng như `FileChannel.transferTo`; mapping không thay thế lựa chọn đó.

## 10. Câu hỏi tự kiểm tra

1. **Bạn cần tìm ngẫu nhiên hàng triệu bản ghi nhị phân trong file chỉ đọc, truy vấn liên tục. Có nên thử mapping không?** Có. Đây là ứng viên hợp lý, nhưng vẫn cần benchmark với `FileChannel.read(position)` và đánh giá page faults, cache và latency.
2. **Một file 6 GiB có thể được map thành một `MappedByteBuffer` duy nhất trong Java 17 không?** Không. `MappedByteBuffer` có capacity kiểu `int`; cần chia thành những cửa sổ hợp lệ.
3. **Đã gọi `FileChannel.close()` thì có thể xóa mapped file ngay trên mọi hệ điều hành?** Không bảo đảm. Mapping có thể tồn tại sau khi channel đóng, và một số hệ điều hành hạn chế xóa/đổi tên tệp đang được map.
4. **`mapped.load()` bảo đảm sẽ không có page fault trong các lần truy vấn tiếp theo?** Không. Trạng thái trang có thể thay đổi; `load()` chỉ cố gắng nạp các trang.
5. **Bạn cần cập nhật file theo nhiều bước với rollback khi mất điện. Chỉ sử dụng `READ_WRITE` và `force()` đã đủ chưa?** Chưa. Cần thiết kế atomicity, thứ tự ghi, khôi phục và kiểm tra tính toàn vẹn riêng.
6. **Khi nào I/O tuần tự có thể hợp lý hơn?** Khi đọc một lần, xử lý streaming, dữ liệu nhỏ, cần quản lý timeout/cancellation rõ ràng hoặc tệp bị thay đổi thường xuyên.

## 11. Ghi nhớ

**Memory mapping đáng cân nhắc** khi làm việc với dữ liệu nhị phân ổn định, truy cập theo offset nhiều lần hoặc đọc lặp lại tập dữ liệu lớn mà hệ điều hành có thể cache hiệu quả. Nó giúp lập trình truy cập dữ liệu theo bộ nhớ và có thể giảm overhead ở đường đọc phù hợp.

**Memory mapping bất lợi** khi công việc quá nhỏ/đơn giản, chỉ streaming một lần, tập dữ liệu truy cập thiếu tính cục bộ, rất nhạy với page fault hoặc tệp thường xuyên bị thay/resize. Cần tính cả chi phí địa chỉ ảo, RAM/page cache, vòng đời mapping và tính nhất quán.

**Tiêu chí cuối cùng là đo trên workload thật**: so sánh throughput, độ trễ (đặc biệt P95/P99), page faults, CPU, sử dụng bộ nhớ và độ phức tạp vận hành. Chọn mapping khi những số liệu và yêu cầu ứng dụng ủng hộ nó.
