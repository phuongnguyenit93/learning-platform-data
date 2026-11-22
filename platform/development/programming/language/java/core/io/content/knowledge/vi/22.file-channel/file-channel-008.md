# Quan hệ giữa FileChannel với FileInputStream, FileOutputStream và RandomAccessFile

## 1. Một tệp, hai cách sử dụng API

Trong Java I/O, ba lớp `java.io.FileInputStream`, `java.io.FileOutputStream` và `java.io.RandomAccessFile` đã có từ trước Java NIO. NIO bổ sung `java.nio.channels.FileChannel`, cho phép thao tác với tệp thông qua `ByteBuffer`, vị trí byte, chuyển dữ liệu giữa channel, ánh xạ tệp và nhiều khả năng khác.

Ba lớp I/O truyền thống đều có phương thức **`getChannel()`**. Phương thức này trả về **`FileChannel` gắn với chính đối tượng đã mở tệp**, vì vậy bạn có thể làm việc với cùng một tệp và trạng thái liên quan bằng API cũ lẫn API channel.

~~~text
FileInputStream  ── getChannel() ──> FileChannel (READ)
FileOutputStream ── getChannel() ──> FileChannel (WRITE)
RandomAccessFile ── getChannel() ──> FileChannel (READ hoặc READ+WRITE)
       │
       └── Cùng tài nguyên, vị trí tệp và vòng đời đóng
~~~

**Điểm cốt lõi:** channel lấy qua `getChannel()` có quan hệ chặt với đối tượng nguồn. Di chuyển vị trí bên channel ảnh hưởng vị trí đọc/ghi của stream hoặc `RandomAccessFile` và ngược lại. Nội dung và độ dài của tệp cũng là cùng một tài nguyên. Đóng một bên làm bên còn lại không thể tiếp tục sử dụng.

Bài này phân biệt chính xác các quyền đọc/ghi, vị trí chia sẻ, quản lý vòng đời, ảnh hưởng của append/buffering và trường hợp nên dùng trực tiếp `FileChannel.open(...)`.

## 2. Bảng so sánh nhanh

| Đối tượng gốc | Cách lấy channel | Quyền channel nhận được | Phương thức I/O quen thuộc |
| --- | --- | --- | --- |
| `FileInputStream` | `input.getChannel()` | Đọc | `read()`, `read(byte[])` |
| `FileOutputStream` | `output.getChannel()` | Ghi | `write(int)`, `write(byte[])` |
| `RandomAccessFile(file, "r")` | `raf.getChannel()` | Đọc | `read(...)`, `seek(...)`, `getFilePointer()` |
| `RandomAccessFile(file, "rw")` | `raf.getChannel()` | Đọc và ghi | `read(...)`, `write(...)`, `seek(...)`, `setLength(...)` |

Với `RandomAccessFile`, các mode `"rws"` và `"rwd"` cũng cho phép đọc/ghi và yêu cầu đồng bộ cập nhật theo hợp đồng của mode; có sự khác biệt về metadata giữa hai mode. Việc đồng bộ thực tế còn phụ thuộc hệ thống lưu trữ.

`getChannel()` trả về đối tượng channel riêng được liên kết với **đối tượng stream/RAF đó**. Các lần gọi `getChannel()` trên cùng đối tượng trả về cùng channel đã liên kết; gọi lại không tạo thêm một descriptor hay một con trỏ độc lập.

Ví dụ:

~~~java
FileInputStream in = new FileInputStream("data.bin");
FileChannel first = in.getChannel();
FileChannel second = in.getChannel();
System.out.println(first == second); // true
in.close();
~~~

Đây là **đoạn code minh họa**, chỉ chạy khi `data.bin` tồn tại; cần import `java.io.FileInputStream` và `java.nio.channels.FileChannel`. Trong ứng dụng thật, ưu tiên `try-with-resources` như ví dụ hoàn chỉnh phía dưới.

**Đừng hiểu kiểu `FileChannel` tự động cấp mọi quyền.** Phương thức `write(...)` trên channel nhận từ `FileInputStream` không hợp lệ vì channel đó chỉ mở để đọc; tương tự `read(...)` trên channel của `FileOutputStream` không hợp lệ khi channel chỉ mở để ghi. Các lỗi điển hình lần lượt là `NonWritableChannelException` và `NonReadableChannelException`.

## 3. FileInputStream và FileChannel: chia sẻ vị trí đọc

`FileInputStream` cung cấp cách đọc từng byte hoặc mảng byte. `FileChannel` cùng tệp cho phép đọc vào `ByteBuffer`, thay đổi vị trí và sử dụng các khả năng NIO khác.

~~~java
try (FileInputStream input = new FileInputStream(path.toFile())) {
    FileChannel channel = input.getChannel();
    // ...
}
~~~

Đây là mảnh code minh họa: `path` phải là một `Path` hợp lệ; nhập các kiểu từ `java.io`, `java.nio.file` và `java.nio.channels`.

Khi stream đọc `n` byte thành công, vị trí của channel tăng theo `n`. Nếu đổi `channel.position(offset)`, lần `input.read()` tiếp theo sẽ bắt đầu tại vị trí đã đặt.

~~~text
File content: A B C D E
Offsets:      0 1 2 3 4

input.read()       → trả 'A', channel.position() = 1
channel.position(3)
input.read()       → trả 'D', channel.position() = 4
~~~

Phương thức `channel.position()` thể hiện con trỏ byte của tệp, không phải offset ký tự của văn bản. `input.read()` trả một byte dưới dạng số nguyên 0–255, hoặc `-1` ở EOF. Chuyển về `char` như `(char) input.read()` chỉ có ý nghĩa trực tiếp cho dữ liệu ASCII đơn byte.

### FileInputStream đọc, FileChannel có thể seek nhưng không ghi

`FileInputStream.getChannel()` trả về channel mở **READ**. Một số thao tác cho phép:

~~~java
FileChannel channel = input.getChannel();
long fileSize = channel.size();
channel.position(0);
ByteBuffer dst = ByteBuffer.allocate(16);
int read = channel.read(dst);
~~~

Đây cũng là mảnh code minh họa; nó sử dụng `input` đang mở và cần import `java.nio.ByteBuffer`. Sau `channel.read(dst)`, nếu cần lấy dữ liệu từ buffer phải gọi `dst.flip()`.

Các lời gọi ghi như `channel.write(src)`, `truncate(...)` hoặc `map(FileChannel.MapMode.READ_WRITE, ...)` không được phép chỉ vì bạn đã có `FileChannel`. Muốn ghi phải mở tệp bằng nguồn cho phép ghi.

### Có thể dùng `FileChannel.read(dst, offset)` không?

Có. `FileChannel` có overload `read(ByteBuffer dst, long position)` đọc tại **offset riêng** mà không thay đổi `channel.position()` chung. Vì channel và `FileInputStream` chia sẻ vị trí chung, cách đọc định vị này cũng không dịch con trỏ logic của `input`.

Tuy nhiên, `dst.position()` vẫn tăng theo số byte nhận. Đừng nhầm việc position của channel không đổi với việc ByteBuffer không thay đổi.

## 4. FileOutputStream và FileChannel: chia sẻ vị trí ghi

`FileOutputStream` ghi byte ra tệp. Channel của nó mở **WRITE**, và vị trí của stream/channel liên kết:

~~~java
try (FileOutputStream output = new FileOutputStream(path.toFile())) {
    FileChannel channel = output.getChannel();
    output.write(new byte[] {'A', 'B', 'C'});
    System.out.println(channel.position()); // 3
}
~~~

Đây là mảnh code minh họa; constructor `new FileOutputStream(file)` **cắt/ghi lại file cũ ngay lúc mở** nếu file đã tồn tại. Vì vậy, phải chọn đúng file và chế độ trước khi thực thi.

Khi đã có channel của output stream, có thể sử dụng `channel.position(index)` rồi gọi `output.write(...)` để ghi đè tại index được đặt:

~~~text
Ban đầu: A B C D E
Offset:  0 1 2 3 4

channel.position(2)
output.write('X')

Kết quả: A B X D E
          position = 3
~~~

**Ghi đè không phải chèn:** `C` được thay bằng `X`, các byte D, E không tự dịch sang phải.

Channel lấy từ `FileOutputStream` **không mở để đọc**, nên nếu muốn đọc ngược dữ liệu vừa ghi, không thể gọi `channel.read(dst)` một cách mặc nhiên. Hãy dùng `RandomAccessFile("rw")`, `FileChannel.open(path, READ, WRITE)` hoặc một kênh đầu vào độc lập với quy tắc phối hợp phù hợp.

### Chế độ append là ngoại lệ rất quan trọng

Có thể tạo stream ghi nối:

~~~java
FileOutputStream output = new FileOutputStream(file, true);
~~~

Đối số `true` nghĩa là append. Khi đó, vị trí khởi đầu của channel liên kết phản ánh **kích thước file**, và các lần ghi qua stream hướng đến cuối tệp. Tương tác giữa seek thủ công trên channel và hành vi append của provider/nền tảng có những ràng buộc; không dựa vào `channel.position(0)` để cố ghi đè đầu tệp khi stream được mở để append.

Nếu bài toán yêu cầu truy cập ngẫu nhiên và ghi đè offset bất kỳ, hãy **mở không ở chế độ append**. Nếu bài toán chỉ cần append log, sử dụng mode phù hợp và đồng bộ khi có nhiều writer. `append` không đồng nghĩa một chuỗi thao tác đọc-size → seek → ghi được bảo đảm nguyên tử.

## 5. RandomAccessFile và FileChannel: hai bộ API cho cùng con trỏ

`RandomAccessFile` khác input/output stream đơn hướng vì bản thân nó đã hỗ trợ **đọc, ghi, nhảy vị trí và đổi độ dài**. Đây là cầu nối dễ thấy nhất giữa API I/O truyền thống và `FileChannel`.

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    FileChannel channel = raf.getChannel();
    raf.seek(10);
    System.out.println(channel.position()); // 10

    channel.position(3);
    System.out.println(raf.getFilePointer()); // 3
}
~~~

Đây là mảnh code minh họa; `file` phải là `java.io.File` hợp lệ và tệp được mở `"rw"`. `raf.seek(long)` và `channel.position(long)` điều khiển cùng vị trí tệp. `raf.getFilePointer()` và `channel.position()` phản ánh cùng offset logic.

Các tương ứng chính:

| RandomAccessFile | FileChannel | Quan hệ |
| --- | --- | --- |
| `raf.seek(pos)` | `channel.position(pos)` | Đặt con trỏ byte dùng chung |
| `raf.getFilePointer()` | `channel.position()` | Hỏi vị trí hiện tại |
| `raf.length()` | `channel.size()` | Hỏi độ dài logic của cùng tệp |
| `raf.read(...)` | `channel.read(buffer)` | Đọc tại vị trí hiện tại, làm con trỏ tiến |
| `raf.write(...)` | `channel.write(buffer)` | Ghi tại vị trí hiện tại, làm con trỏ tiến |
| `raf.setLength(n)` | `channel.truncate(n)` | Cùng liên quan tới độ dài, nhưng khác nhau khi **n lớn hơn size cũ** |

### Khác biệt lớn: `setLength` có thể mở rộng, `truncate` thì không

Đây là ranh giới dễ nhầm lẫn nhất.

- `RandomAccessFile.setLength(n)`: nếu `n` nhỏ hơn size cũ thì cắt; nếu `n` lớn hơn thì **mở rộng** tệp. Byte trong phần mới mở rộng **không được xác định** chung bởi API.
- `FileChannel.truncate(n)`: nếu `n` nhỏ hơn size cũ thì cắt; nếu `n` lớn hơn hoặc bằng size cũ thì **không** mở rộng tệp.

~~~text
Current size = 5

raf.setLength(8)       → new size = 8
channel.size()         → 8
bytes at offsets 5..7 → không được API định nghĩa

channel.truncate(4)    → new size = 4
raf.length()           → 4
~~~

Khi cắt tệp ngắn đi, con trỏ lớn hơn giới hạn mới bị điều chỉnh xuống. `setLength` cũng có thể điều chỉnh file pointer theo hợp đồng của phương thức. Các thao tác này thay đổi **cùng tệp**, vì thế `raf.length()` và `channel.size()` quan sát cùng độ dài sau cập nhật thành công.

Đừng dùng phần vừa mở rộng chưa được ghi giá trị như dữ liệu có ý nghĩa. Muốn định dạng file có padding xác định, hãy ghi byte padding rõ ràng.

## 6. Chương trình Java 17+ hoàn chỉnh: ba đối tượng cùng cách chia sẻ trạng thái

Chương trình sau sử dụng một tệp tạm và mở ba đối tượng gốc **lần lượt**, không mở đồng thời. Nhờ đó, ta có thể quan sát đầy đủ hành vi chia sẻ con trỏ mà không lẫn với các vấn đề cạnh tranh I/O.

Lưu thành `FileChannelLegacyBridgeDemo.java`:

~~~java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileChannelLegacyBridgeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("channel-bridge-", ".bin");

        try {
            FileChannel outputChannel;

            try (FileOutputStream out =
                         new FileOutputStream(file.toFile())) {
                outputChannel = out.getChannel();

                out.write("ABCDE".getBytes(StandardCharsets.US_ASCII));
                System.out.println("output position after write="
                        + outputChannel.position());

                outputChannel.position(2);
                out.write('X');
                System.out.println("output position after seek/write="
                        + outputChannel.position());
            }

            System.out.println("output channel open after close="
                    + outputChannel.isOpen());

            try (FileInputStream in =
                         new FileInputStream(file.toFile())) {
                FileChannel inputChannel = in.getChannel();

                System.out.println("input first=" + (char) in.read());
                System.out.println("input channel position="
                        + inputChannel.position());

                inputChannel.position(3);
                System.out.println("input after channel seek="
                        + (char) in.read());
                System.out.println("input position after read="
                        + inputChannel.position());
            }

            try (RandomAccessFile raf =
                         new RandomAccessFile(file.toFile(), "rw")) {
                FileChannel randomChannel = raf.getChannel();

                raf.seek(1);
                System.out.println("raf.seek channel position="
                        + randomChannel.position());

                randomChannel.position(4);
                System.out.println("channel.position raf pointer="
                        + raf.getFilePointer());

                raf.writeByte('Z');
                System.out.println("raf write channel position="
                        + randomChannel.position());

                raf.setLength(7);
                System.out.println("after setLength: raf.length="
                        + raf.length() + ", channel.size="
                        + randomChannel.size());

                randomChannel.truncate(4);
                System.out.println("after truncate: raf.length="
                        + raf.length() + ", raf pointer="
                        + raf.getFilePointer());
            }

            System.out.println("final="
                    + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac FileChannelLegacyBridgeDemo.java
java FileChannelLegacyBridgeDemo
~~~

Stdout mong đợi trên hệ thống tệp mặc định thông dụng:

~~~text
output position after write=5
output position after seek/write=3
output channel open after close=false
input first=A
input channel position=1
input after channel seek=D
input position after read=4
raf.seek channel position=1
channel.position raf pointer=4
raf write channel position=5
after setLength: raf.length=7, channel.size=7
after truncate: raf.length=4, raf pointer=4
final=ABXD
~~~

Giải thích từng bước:

1. `FileOutputStream` ghi `ABCDE`, position của channel thành 5. Di chuyển channel về offset 2 rồi gọi `out.write('X')` thay byte C bằng X, nhận `ABXDE`. Position chung thành 3.
2. Ra khỏi `try (out)`, stream được đóng; channel liên kết cũng đã đóng. `outputChannel.isOpen()` vì vậy trả `false`.
3. `FileInputStream` mở lại tệp từ đầu, đọc `A` ở offset 0 nên channel position = 1. `inputChannel.position(3)` làm lần `in.read()` sau đọc byte D, rồi position thành 4.
4. `RandomAccessFile("rw")` mở tệp và cho phép cả đọc lẫn ghi. `raf.seek(1)` phản ánh thành position 1 ở channel. `randomChannel.position(4)` phản ánh thành file pointer 4 ở RAF.
5. `raf.writeByte('Z')` thay E bằng Z, tệp thành `ABXDZ` và position thành 5.
6. `raf.setLength(7)` mở rộng tệp từ 5 lên 7 byte. `randomChannel.size()` lập tức phản ánh 7; ví dụ **không đọc** hai byte mới vì chúng không có giá trị được API bảo đảm.
7. `randomChannel.truncate(4)` cắt tệp từ 7 về 4 byte, làm file pointer đang ở 5 bị kéo về 4. Tệp cuối cùng chỉ còn `ABXD`.
8. `Files.readString` đọc sau khi RAF đã được đóng, để kiểm tra kết quả cuối; `finally` xóa tệp tạm.

Các chữ `A`, `D` được cast từ byte sang `char` an toàn trong ví dụ vì dữ liệu chỉ gồm ASCII. Với văn bản UTF-8 nhiều byte, hãy dùng charset decoder phù hợp thay vì cast từng byte.

## 7. Đóng stream hay đóng channel: một quan hệ vòng đời

Một channel lấy qua `getChannel()` **không phải handle độc lập cần được quản lý như một file thứ hai**.

- `input.close()` đóng channel liên kết với `FileInputStream`; `output.close()` và `raf.close()` cũng đóng channel tương ứng.
- Theo hợp đồng `FileChannel`, **đóng channel liên kết cũng đóng đối tượng stream hoặc RAF gốc**.
- Sau khi đã đóng, thao tác I/O tiếp trên channel sẽ thất bại, thường với `ClosedChannelException`; thao tác trên stream/RAF đã đóng cũng không thể dùng tiếp.
- Phương thức `getChannel()` nhiều lần trên cùng một đối tượng không phải lệnh mở lại sau khi đóng.

Mẫu ưu tiên:

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    FileChannel channel = raf.getChannel();
    // Dùng cả raf và channel trong cùng phạm vi sở hữu.
}
~~~

Đây là mảnh code minh họa, với `file` kiểu `File` hợp lệ. Chỉ khai báo **nguồn sở hữu tài nguyên** trong `try-with-resources` là đủ cho vòng đời thông thường. Nếu code cố đóng `channel` giữa chừng rồi tiếp tục dùng `raf`, thiết kế sẽ lỗi do tài nguyên đã đóng.

Nếu chuyển channel từ một hàm nội bộ ra ngoài, phải thống nhất **ai có quyền đóng**. Ví dụ một hàm tiện ích nhận `FileChannel` của caller thường không nên tự đóng nó nếu caller còn sử dụng `FileInputStream` liên kết.

## 8. Hai cách mở FileChannel không có cùng quan hệ sở hữu

Có hai con đường:

**A. Lấy channel từ đối tượng Java I/O đã mở**

~~~java
FileChannel channel = stream.getChannel();
~~~

Khi dùng kiểu này, channel gắn với chính `FileInputStream`/`FileOutputStream`/`RandomAccessFile` được truyền vào, chia sẻ position và vòng đời.

**B. Mở trực tiếp từ Path**

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        java.nio.file.StandardOpenOption.READ,
        java.nio.file.StandardOpenOption.WRITE)) {
    // Channel này được quản lý độc lập.
}
~~~

Khi mở trực tiếp, bạn không có một `FileInputStream`/`FileOutputStream`/`RandomAccessFile` nguồn để chia sẻ pointer theo `getChannel()`. Nếu một stream khác cũng mở cùng tệp, chúng có thể **cùng thấy nội dung file**, nhưng không phải cùng cặp liên kết stream–channel nói trên. Trên filesystem thông thường, các lần mở độc lập có con trỏ độc lập; đừng suy luận rằng vì hai đường dẫn giống nhau nên `channel.position(...)` tự điều khiển pointer của mọi stream khác đang mở file đó.

Nếu muốn đơn thuần đọc và ghi bằng `ByteBuffer`, `FileChannel.open(path, options)` thường rõ ràng. Nếu đã có stream hoặc RAF và cần phối hợp API mới, `getChannel()` giúp tránh mở thêm một tài nguyên không cần thiết.

## 9. ByteBuffer và mảng byte: chuyển đổi cách tư duy khi kết hợp API

Stream truyền thống nhận hoặc trả từng byte/mảng byte:

~~~java
int value = in.read();
out.write(new byte[] {'A', 'B'});
~~~

FileChannel chủ yếu làm việc với `ByteBuffer`:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int n = channel.read(buffer);
buffer.flip(); // Chuẩn bị tiêu thụ n byte vừa đọc.
~~~

Các mảnh code ở trên dùng biến `in`, `out`, `channel` đã được khởi tạo theo chế độ thích hợp; chúng không phải chương trình độc lập.

Phân biệt hai nhóm con trỏ:

- **Con trỏ file** của stream/RAF/channel liên kết: byte tiếp theo trên tài nguyên đang mở.
- **`position`/`limit` của ByteBuffer**: byte tiếp theo trong vùng nhớ đệm.

Khi `channel.read(buffer)` đọc được `n` byte, file position và buffer position đều tăng `n`. Lúc đó `buffer.flip()` chỉ đặt lại giới hạn để đọc từ buffer; nó không đưa file position quay về đầu.

Khi `channel.write(buffer)` ghi ra file, buffer position và file position tiến theo số byte đã ghi. Nếu `write` chỉ chuyển được một phần, không được `buffer.clear()` rồi bỏ qua phần chưa ghi.

**Thận trọng khi mix stream + channel với bộ đệm cấp cao.** Nếu bạn bọc `FileInputStream` bằng `BufferedInputStream` hoặc `InputStreamReader`, wrapper có thể đọc trước nhiều byte vào vùng nhớ nội bộ. Lúc đó file position vật lý đã vượt quá số byte ứng dụng nhìn thấy. Thay đổi vị trí bằng channel trong khi wrapper còn giữ dữ liệu đệm có thể khiến dữ liệu quan sát bị lặp, bỏ qua hoặc không như ý. Với `BufferedOutputStream`, byte đang chờ flush có thể được ghi sau khi code đã seek bằng channel, dẫn đến nội dung không mong đợi.

Khi cần truy cập ngẫu nhiên, hãy ưu tiên một đường I/O nhất quán; nếu bắt buộc phối hợp wrapper, quản lý `flush`/trạng thái buffer và vị trí tệp một cách tường minh, tránh giả định chúng tự đồng bộ.

## 10. FileChannel bổ sung điều gì so với ba lớp nguồn?

`getChannel()` đặc biệt hữu ích vì `FileChannel` có API mà ba lớp Java I/O không cung cấp cùng hình thức:

- `read(ByteBuffer, long)` và `write(ByteBuffer, long)`: đọc/ghi tại offset chỉ định mà không thay đổi position chung của channel.
- `transferTo(...)`, `transferFrom(...)`: truyền dữ liệu giữa các channel tương thích với khả năng tối ưu của provider.
- `map(...)`: ánh xạ vùng file vào bộ nhớ.
- `lock(...)`/`tryLock(...)`: khóa vùng file với các giới hạn nền tảng và việc hợp tác của ứng dụng.
- `force(boolean)`: yêu cầu đẩy các cập nhật xuống thiết bị lưu trữ theo hợp đồng API.
- `size()`, `truncate(long)` và `position(long)`: quan sát/điều chỉnh độ dài và vị trí byte qua API NIO.

Nếu chỉ cần `read()` tuần tự từng byte, `FileInputStream` có thể đủ. Nếu chỉ ghi một mảng byte, `FileOutputStream` đơn giản hơn. Nếu cần đọc và ghi record theo offset kết hợp các kiểu dữ liệu nguyên thủy, `RandomAccessFile` cung cấp `readInt`, `writeLong`, `seek`, v.v. Khi cần ByteBuffer, positional I/O hoặc chuyển dữ liệu giữa channel, `FileChannel` phù hợp hơn.

**Không thể xem `getChannel()` là một phép nâng quyền.** Channel của FileInputStream vẫn chỉ đọc; channel của FileOutputStream vẫn chỉ ghi. Mọi thao tác đặc biệt còn phụ thuộc quyền tệp và hỗ trợ của hệ điều hành/provider.

## 11. Đồng thời: chia sẻ pointer có thể tạo race condition

Quan hệ chia sẻ vị trí thuận tiện trong chương trình một luồng, nhưng cần rất cẩn thận nếu nhiều thread dùng chung stream/channel:

~~~text
Thread A: input.getChannel().position(100)
Thread B: input.read()              // Đọc byte ở vị trí 100
Thread A: input.read()              // Không chắc còn ở vị trí 100
~~~

Trong ví dụ, dòng thứ hai có thể làm con trỏ tiến trước khi thread A đọc. `position(offset)` rồi `read()` là **hai thao tác**, không mặc nhiên nguyên tử khi trộn API giữa thread.

Để hạn chế xung đột:

1. Giao một stream/channel liên kết cho một thành phần chịu trách nhiệm quản lý position.
2. Nếu cần chia sẻ, đồng bộ một chuỗi thao tác seek + read/write ở mức ứng dụng.
3. Cân nhắc overload `FileChannel.read(dst, offset)`/`write(src, offset)` để thao tác với offset riêng mà không làm đổi position chung, nếu quyền truy cập cho phép.
4. Phân biệt xung đột **con trỏ** với xung đột **nội dung file**: positional I/O giúp hạn chế việc giẫm lên shared position, nhưng không tự loại bỏ việc nhiều writer ghi lên cùng vùng dữ liệu.

Đóng channel từ thread này trong khi thread khác đang sử dụng stream có thể làm thao tác của thread kia thất bại. Thiết kế ownership đóng cũng quan trọng không kém ownership con trỏ.

## 12. Lỗi phổ biến

### Sai 1. Nghĩ `getChannel()` tạo file/channel mới độc lập

Nó trả channel gắn với nguồn đang mở. Cùng một con trỏ và vòng đời; seek bên channel ảnh hưởng stream/RAF. Mở tệp mới độc lập bằng `FileChannel.open(path, ...)` là tình huống khác.

### Sai 2. Lấy channel từ input rồi gọi write

`FileInputStream.getChannel()` tạo channel chỉ đọc. `write` trên channel đó sẽ ném `NonWritableChannelException`. Muốn đọc/ghi, chọn `RandomAccessFile("rw")` hoặc mở trực tiếp `FileChannel` với quyền thích hợp.

### Sai 3. Lấy channel từ output rồi gọi read

`FileOutputStream.getChannel()` là channel chỉ ghi. Nó không tự có quyền đọc vì đang có kiểu `FileChannel`; `read` sẽ thất bại với `NonReadableChannelException`.

### Sai 4. Đóng channel rồi vẫn dùng stream hoặc RAF

Vì hai đối tượng gắn với cùng vòng đời, đóng channel sẽ làm nguồn không thể tiếp tục thao tác. Dùng một `try-with-resources` rõ quyền sở hữu; không đóng tài nguyên do caller quản lý khi trả về từ utility.

### Sai 5. Tưởng RandomAccessFile và FileChannel có hai con trỏ

`raf.seek(offset)` làm `channel.position()` thay đổi; `channel.position(offset)` làm `raf.getFilePointer()` thay đổi. Nếu dùng cả hai, phải ghi nhận rằng chúng điều khiển một vị trí.

### Sai 6. Dùng `truncate` để làm tệp dài ra

`FileChannel.truncate(newSize)` chỉ thu nhỏ khi cần; ngược lại `RandomAccessFile.setLength(newSize)` có thể mở rộng file. Phần mở rộng không bảo đảm các byte có giá trị xác định.

### Sai 7. Cố ghi đè đầu tệp từ stream append

`new FileOutputStream(file, true)` dành cho nối cuối. Không thiết kế logic seek/overwrite dựa vào giả định append sẽ tôn trọng một con trỏ thủ công theo cách bạn mong muốn.

### Sai 8. Trộn buffered wrapper với channel và tưởng con trỏ ứng dụng khớp con trỏ tệp

Wrapper có thể đọc trước, giữ byte chưa flush hoặc giải mã thành ký tự. Chỉ số byte đã tiêu thụ ở wrapper khác vị trí channel. Cần chủ động quản lý buffer hoặc dùng một API truy cập nhất quán.

### Sai 9. Không để ý quyền và lỗi I/O

Các ngoại lệ quan trọng bao gồm `NonReadableChannelException`, `NonWritableChannelException`, `ClosedChannelException`, `IOException`. Ngoài ra còn vấn đề file không tồn tại, permission, bộ nhớ đệm, lock và filesystem không hỗ trợ. Chọn nguồn và mode đúng ngay từ lúc mở.

## 13. Câu hỏi tự kiểm tra

1. `FileInputStream.getChannel()` có thể ghi dữ liệu không? **Không**, channel được mở đọc.
2. Stream đã đọc 3 byte; `input.getChannel().position()` thường là bao nhiêu? **3**, nếu chưa có thao tác khác thay đổi vị trí.
3. Vì sao `channel.position(10)` có thể đổi byte kế tiếp của `in.read()`? Vì chúng chia sẻ vị trí trên cùng đối tượng nguồn.
4. `FileOutputStream.getChannel()` có thể đọc dữ liệu vừa ghi không? **Không**, channel được mở ghi.
5. `RandomAccessFile("rw")` gọi `raf.seek(7)`. `raf.getChannel().position()` bằng bao nhiêu? **7**.
6. Channel của RAF gọi `position(2)`; `raf.getFilePointer()` thay đổi không? **Có, về 2**.
7. Tệp dài 5 byte; `raf.setLength(8)` rồi `raf.getChannel().size()` bằng bao nhiêu? **8**. Nội dung ba byte thêm vào có xác định không? **Không**.
8. Tệp dài 5 byte; `raf.getChannel().truncate(8)` có làm size thành 8 không? **Không, vẫn 5**.
9. Sau khi đóng `FileOutputStream`, có thể tiếp tục gọi `out.getChannel().write(...)` không? **Không**, tài nguyên liên kết đã đóng.
10. Vì sao không nên để hai thread tự do gọi `raf.seek(...)` và `channel.read(...)` trên cùng RAF? Vì vị trí đọc được chia sẻ, thứ tự thực thi có thể làm thao tác đọc sai offset.
11. Khi dùng `FileChannel.read(dst, 100)`, vị trí channel/RAF có đổi không? **Không do lời gọi định vị riêng này**, nhưng `dst.position()` tăng theo số byte thực đọc.
12. Khi chỉ cần FileChannel độc lập từ `Path`, dùng API nào? **`FileChannel.open(path, options)`**, quản lý vòng đời channel bằng `try-with-resources`.

**Ghi nhớ:** `getChannel()` là cầu nối trực tiếp từ `FileInputStream`, `FileOutputStream` và `RandomAccessFile` tới NIO. Nó **giữ quyền I/O của nguồn**, đồng thời **chia sẻ vị trí, dữ liệu, độ dài và vòng đời đóng** với nguồn đó. `RandomAccessFile.setLength` có thể tăng kích thước trong khi `FileChannel.truncate` chỉ cắt ngắn; tách bạch hai hành vi này khi thiết kế truy cập tệp ngẫu nhiên.
