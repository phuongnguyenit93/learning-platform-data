# SeekableByteChannel và khả năng thay đổi vị trí trong Java NIO

## 1. Vấn đề: đọc/ghi tuần tự chưa đủ

Khi đọc một luồng dữ liệu thông thường, chương trình tiêu thụ dữ liệu theo thứ tự và không nhất thiết có cách quay lại byte đã đọc. Với tệp, nhiều bài toán cần khả năng truy cập ngẫu nhiên (random access): đọc header ở đầu, nhảy tới một bản ghi ở cuối, sửa một trường nằm giữa tệp hoặc cắt bỏ phần cuối.

Trong Java NIO, **`SeekableByteChannel`** (`java.nio.channels.SeekableByteChannel`) cung cấp cơ chế đó: nó là một channel có thể đọc/ghi byte, **biết kích thước tài nguyên** và **cho phép thay đổi vị trí hiện tại**.

~~~text
Tệp:     a  b  c  d  e  f
Offset:  0  1  2  3  4  5
                               EOF tại offset 6

position = 2
            ↑
lệnh read tiếp theo bắt đầu từ byte 'c'
lệnh write tiếp theo bắt đầu ghi đè từ byte 'c'
~~~

**`position` không phải nội dung tệp.** Đó là con trỏ logic chỉ nơi thao tác đọc/ghi tương đối tiếp theo sẽ bắt đầu. Di chuyển con trỏ không tự thêm, xóa hoặc sao chép byte.

Phạm vi của bài học: hiểu hợp đồng `SeekableByteChannel`, quan hệ giữa `position` và `size`, cách đọc/ghi ở vị trí tùy ý, `truncate` và các tình huống dễ sai khi dùng API này.

## 2. Vai trò và các phương thức chính

`SeekableByteChannel` mở rộng `ByteChannel`, tức là thừa hưởng cả `ReadableByteChannel` và `WritableByteChannel`. Nó cũng là `Channel`, hỗ trợ đóng tài nguyên bằng `close()` và kiểm tra `isOpen()`. Tuy nhiên **chế độ mở** có thể cho phép chỉ đọc, chỉ ghi hoặc cả hai; việc một object có kiểu `SeekableByteChannel` không mặc nhiên có quyền thực hiện cả hai hướng.

Các phương thức thiết yếu:

| Phương thức | Tác dụng | Điều cần nhớ |
| --- | --- | --- |
| `long position()` | Lấy vị trí hiện tại | Đơn vị byte, offset bắt đầu từ 0 |
| `SeekableByteChannel position(long newPosition)` | Di chuyển vị trí đọc/ghi kế tiếp | `newPosition < 0` là không hợp lệ; có thể đặt vượt EOF |
| `long size()` | Lấy kích thước hiện tại của tài nguyên | Không phải vị trí; có thể thay đổi khi ghi/truncate |
| `SeekableByteChannel truncate(long size)` | Nếu kích thước mới nhỏ hơn kích thước hiện tại, cắt phần cuối | Không dùng để mở rộng tệp |
| `int read(ByteBuffer dst)` | Đọc byte từ vị trí hiện tại sang buffer | Trả số byte đọc, hoặc `-1` ở EOF |
| `int write(ByteBuffer src)` | Ghi byte từ buffer tại vị trí hiện tại | Có thể ghi đè byte cũ hoặc mở rộng tệp |
| `close()` | Đóng channel | Nên dùng `try-with-resources` |

Thông thường một `SeekableByteChannel` gắn với tệp, nhưng giao diện không hứa mọi implementation là một file trên ổ đĩa. `FileChannel` cũng triển khai `SeekableByteChannel` và bổ sung các tính năng riêng như thao tác định vị có chỉ số độc lập, memory mapping, file lock và `force`.

### Ba đại lượng dễ nhầm lẫn

Giả sử tệp có 6 byte:

~~~text
Nội dung: abcdef
size() = 6
position() = 2
ByteBuffer.remaining() = 4 (giả sử buffer có 4 chỗ đọc)
~~~

- `channel.size()`: kích thước dữ liệu trong **tệp/tài nguyên**.
- `channel.position()`: con trỏ hiện tại của **channel**.
- `buffer.position()`, `buffer.limit()`, `buffer.remaining()`: trạng thái của **buffer trong bộ nhớ**.

Mỗi lần `channel.read(buffer)` thành công với `n` byte, vị trí channel tăng `n` và vị trí buffer tăng `n`. Mỗi lần `channel.write(buffer)` thành công với `n` byte, hai vị trí cũng thường tăng `n` tương ứng. **Không nhầm vị trí của channel với vị trí của buffer.**

## 3. Tạo `SeekableByteChannel` và xác định quyền truy cập

Cách thông dụng với API `Files`:

~~~java
Path path = Path.of("data.bin");

// Chỉ đọc. Khi không truyền options, Files.newByteChannel mặc định là READ.
try (SeekableByteChannel channel = Files.newByteChannel(path)) {
    System.out.println(channel.size());
}
~~~

Đây là đoạn minh họa cần import `java.nio.file.*` và `java.nio.channels.SeekableByteChannel`; tệp `data.bin` phải tồn tại nếu muốn chạy trực tiếp.

Để vừa đọc vừa ghi một tệp đã có:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    // Thao tác với channel trong khối try.
}
~~~

Một số `StandardOpenOption` cần phân biệt:

- **`READ`**: cho phép đọc dữ liệu.
- **`WRITE`**: cho phép ghi dữ liệu.
- **`CREATE`**: tạo tệp nếu chưa có khi dùng cùng tùy chọn ghi phù hợp.
- **`CREATE_NEW`**: chỉ tạo tệp mới; thất bại nếu mục tiêu đã tồn tại.
- **`TRUNCATE_EXISTING`**: khi mở để ghi, cắt tệp đã tồn tại về kích thước 0 ngay lúc mở; không sử dụng khi cần giữ dữ liệu để seek và sửa.
- **`APPEND`**: ghi nối vào cuối theo ngữ nghĩa provider; không thích hợp nếu mục tiêu là điều khiển vị trí ghi tùy ý.

Ví dụ: `Files.newByteChannel(path, READ, WRITE)` không tạo tệp nếu tệp chưa tồn tại. Có thể dùng `WRITE, CREATE` khi cần tạo mới hoặc tiếp tục ghi tùy nhu cầu.

**Lưu ý về `APPEND`:** trong chế độ append, trước mỗi thao tác ghi, channel có thể bị chuyển về cuối để nối thêm; việc kết hợp `APPEND` với `READ` hoặc `TRUNCATE_EXISTING` có thể không được provider hỗ trợ. Một số kết hợp được JDK mặc định từ chối. Không dùng `position(0)` để kỳ vọng ghi đè đầu tệp khi channel mở `APPEND`.

API dựa trên `Path` nên hệ thống tệp và provider của `path` quyết định cách mở channel, tính năng hỗ trợ và ngoại lệ thực tế.

## 4. `position(long)`: di chuyển con trỏ trước khi đọc/ghi

Ví dụ có tệp chứa `abcdef`:

~~~text
Offset     0  1  2  3  4  5
Byte       a  b  c  d  e  f
Size       6
Position   0
~~~

Đặt:

~~~java
channel.position(2);
~~~

Sau đó `channel.read(dst)` bắt đầu tại offset 2, tức là byte `c`. Nếu đọc được 3 byte, channel có `position() == 5`. Lệnh `channel.write(src)` cũng bắt đầu ghi tại vị trí hiện tại (nếu channel cho phép ghi).

Với tệp thông thường:

- `position(0)` quay về đầu tệp.
- `position(channel.size())` đặt con trỏ tại EOF để có thể ghi nối từ đó nếu mở ghi.
- `position(2)` cho phép đọc/ghi từ byte thứ ba.
- `position(-1)` ném `IllegalArgumentException`.
- `position(newPosition)` không thay đổi kích thước tệp chỉ vì vị trí lớn hơn `size()`.

### Đặt con trỏ vượt EOF có hợp lệ không?

Có. Ví dụ size = 6 và:

~~~java
channel.position(100);
~~~

`position()` lúc này có thể là 100 trong khi `size()` vẫn bằng 6. Với tệp có nội dung hữu hạn, một lời gọi `read` khi vị trí ở hoặc sau EOF thường trả `-1` mà không tự kéo dài tệp.

Nếu **ghi dữ liệu** tại offset 100, tệp có thể được mở rộng để chứa dữ liệu mới và khoảng trống giữa EOF cũ với vị trí ghi. Theo hợp đồng của `SeekableByteChannel`, **giá trị byte trong khoảng trống đó không được xác định chung cho mọi implementation**. Đừng tự giả định luôn được điền bằng byte `0`. Nếu định dạng tệp yêu cầu giá trị cụ thể, ứng dụng cần ghi/khởi tạo rõ ràng.

Lưu ý: vị trí dùng kiểu `long` để biểu diễn offset lớn; đừng ép về `int` khi làm việc với tệp dung lượng lớn.

## 5. Ghi tại vị trí tùy ý: ghi đè và mở rộng

Một channel mở `WRITE` dùng vị trí hiện tại để xác định nơi viết byte. Nếu vị trí nằm trong dữ liệu đã có, ghi sẽ **thay thế các byte nằm ở vùng đó**, không tự chèn byte làm các byte phía sau dịch sang phải.

~~~text
Tệp ban đầu:
Offset 0 1 2 3 4 5
       a b c d e f
size = 6

position(2)
write("XY")

Tệp sau ghi:
Offset 0 1 2 3 4 5
       a b X Y e f
size = 6
position = 4
~~~

Đây là **overwrite**, không phải thao tác chèn chuỗi tại index 2. Hai byte `c` và `d` đã bị thay bằng `X`, `Y`; các byte `e`, `f` còn nguyên.

Nếu ghi dài tới sau cuối tệp, kích thước tăng tới mức chứa byte cuối cùng được ghi. Nếu ghi trong phạm vi tệp và không có thay đổi đồng thời, `size()` có thể giữ nguyên.

### Tại sao không giả định một `write` ghi hết buffer?

Phương thức `int write(ByteBuffer src)` trả số byte đã ghi. Số đó có thể ít hơn `src.remaining()` trước lời gọi, tùy implementation và tình trạng I/O. Vì vậy, khi cần ghi toàn bộ payload, phải lặp tới khi `src.hasRemaining()` là `false` hoặc xử lý tình huống không có tiến triển.

~~~java
while (src.hasRemaining()) {
    int written = channel.write(src);
    if (written == 0) {
        // Tùy loại channel, đợi khả năng ghi rồi thử tiếp.
    }
}
~~~

Đây là mã minh họa cấu trúc vòng lặp: trong chương trình thực tế, cần cơ chế đợi/cancel/timeout phù hợp; vòng lặp gọi `write` mãi khi liên tục trả 0 sẽ tốn CPU.

Đối với channel tệp chặn thông thường và buffer hợp lệ, thao tác hay có tiến triển, nhưng vẫn nên lập trình theo số byte thực tế thay vì cho rằng một lần ghi luôn hoàn thành.

## 6. Đọc ở vị trí tùy ý và xử lý EOF

Với `read(ByteBuffer dst)`:

1. Byte được lấy từ vị trí hiện tại của channel.
2. Các byte chuyển vào buffer bắt đầu tại `dst.position()`.
3. `channel.position()` và `dst.position()` tăng theo số byte đọc thực sự.
4. Khi đến EOF trước khi đọc được byte nào, `read` trả `-1`; buffer không nhận byte.
5. `read` cũng có thể trả `0` trong hoàn cảnh không đọc được byte, ví dụ `dst` hết chỗ hoặc implementation không chặn chưa có dữ liệu.

Đọc lại từ đầu:

~~~java
channel.position(0);

ByteBuffer dst = ByteBuffer.allocate(16);
int count = channel.read(dst);
dst.flip();

// Lúc này dst chứa các byte đã đọc được từ channel,
// không nhất thiết đủ 16 byte.
~~~

Đây là mảnh minh họa sử dụng biến `channel` đã được mở phù hợp. `channel.position(0)` **không** tương đương `dst.clear()`: một bên di chuyển con trỏ của tài nguyên, bên kia đặt lại trạng thái buffer trong RAM.

Để đọc chính xác một lượng byte xác định, cần lặp và kiểm tra `-1`, `0` hoặc phần còn lại của buffer. Đặc biệt tránh gọi `new String(dst.array())` khi buffer chưa được điền đầy: việc đó có thể kèm byte chưa đọc từ tệp. Hãy `flip()` rồi giải mã đúng vùng dữ liệu hợp lệ, ví dụ `StandardCharsets.UTF_8.decode(dst)` nếu dữ liệu là UTF-8 hoàn chỉnh.

## 7. `size()` và `truncate(long)`

`size()` báo kích thước hiện tại của tệp/tài nguyên, độc lập với việc con trỏ đang ở đâu:

~~~text
size = 6; position = 2
size vẫn = 6 sau position(100)
~~~

`truncate(newSize)` có quy tắc quan trọng:

- Nếu `newSize < size()`, tệp bị cắt còn `newSize` byte, mất phần đuôi.
- Nếu `newSize >= size()`, kích thước **không tăng** chỉ nhờ `truncate`.
- Nếu vị trí hiện tại lớn hơn kích thước còn lại sau truncate, vị trí được đưa về kích thước mới; nếu vị trí đang nằm trong phạm vi giữ lại, nó được bảo toàn.
- `newSize < 0` là không hợp lệ và có thể ném `IllegalArgumentException`.
- Channel phải mở với quyền ghi phù hợp; nếu không, `NonWritableChannelException` có thể phát sinh.

Ví dụ:

~~~text
Ban đầu: "abcdef"
size = 6
position = 100

truncate(4)

Còn lại: "abcd"
size = 4
position = 4
~~~

**`truncate(100)` trên tệp 4 byte không kéo dài tệp thành 100 byte**. Nếu yêu cầu định dạng tệp cố định kích thước, ứng dụng phải ghi thêm dữ liệu (và xử lý mọi khoảng trống) theo quy tắc của mình.

Cần cẩn trọng với `TRUNCATE_EXISTING` khi mở channel: tùy chọn đó xóa nội dung ngay khi mở, khác với phương thức `truncate(...)` được gọi tại thời điểm do chương trình lựa chọn.

## 8. Ví dụ Java 17+ chạy độc lập: seek, overwrite, EOF và truncate

Chương trình sử dụng tệp tạm trên filesystem mặc định, vì thế chạy độc lập, không phụ thuộc đường dẫn cụ thể trên máy. Các chuỗi mẫu là ASCII để việc đếm offset theo byte hoàn toàn rõ ràng. Lưu thành `SeekableByteChannelDemo.java`:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class SeekableByteChannelDemo {

    private static void writeFully(SeekableByteChannel channel, String data)
            throws IOException {
        ByteBuffer src = ByteBuffer.wrap(
                data.getBytes(StandardCharsets.US_ASCII));
        while (src.hasRemaining()) {
            int n = channel.write(src);
            if (n == 0) {
                throw new IOException("No write progress");
            }
        }
    }

    private static String readFully(SeekableByteChannel channel, int length)
            throws IOException {
        ByteBuffer dst = ByteBuffer.allocate(length);
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n == -1) {
                break;
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
        }
        dst.flip();
        return StandardCharsets.US_ASCII.decode(dst).toString();
    }

    public static void main(String[] args) throws IOException {
        Path temp = Files.createTempFile("seekable-demo-", ".bin");

        try {
            try (SeekableByteChannel channel = Files.newByteChannel(
                    temp,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                System.out.println("initial: position=" + channel.position()
                        + ", size=" + channel.size());

                writeFully(channel, "abcdef");
                System.out.println("after write: position=" + channel.position()
                        + ", size=" + channel.size());

                channel.position(2);
                writeFully(channel, "XY");
                System.out.println("after overwrite: position=" + channel.position()
                        + ", size=" + channel.size());

                channel.position(0);
                System.out.println("content=" + readFully(channel, 6));
                System.out.println("after read: position=" + channel.position());

                channel.position(100);
                int result = channel.read(ByteBuffer.allocate(1));
                System.out.println("read beyond EOF=" + result);
                System.out.println("position after EOF=" + channel.position());

                channel.truncate(4);
                System.out.println("after truncate: position=" + channel.position()
                        + ", size=" + channel.size());

                channel.position(0);
                System.out.println("truncated content=" + readFully(channel, 4));

                channel.position(10);
                System.out.println("seek beyond EOF: position=" + channel.position()
                        + ", size=" + channel.size());
                writeFully(channel, "!");
                System.out.println("after extension: position=" + channel.position()
                        + ", size=" + channel.size());
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SeekableByteChannelDemo.java
java SeekableByteChannelDemo
~~~

Stdout khi chạy với provider tệp mặc định thông dụng hỗ trợ các thao tác trên:

~~~text
initial: position=0, size=0
after write: position=6, size=6
after overwrite: position=4, size=6
content=abXYef
after read: position=6
read beyond EOF=-1
position after EOF=100
after truncate: position=4, size=4
truncated content=abXY
seek beyond EOF: position=10, size=4
after extension: position=11, size=11
~~~

Cách đọc kết quả:

1. Tệp tạm mới có kích thước 0. `writeFully("abcdef")` ghi 6 byte và đưa `position` về 6.
2. `position(2)` rồi ghi `XY` đè đúng hai byte ở offset 2 và 3. Tệp vẫn dài 6 byte; sau ghi `position=4`.
3. Đưa `position` về 0 rồi đọc 6 byte để xác nhận nội dung `abXYef`. Hàm `readFully` chỉ giải mã vùng buffer đã thực sự nhận dữ liệu.
4. Đặt `position=100` dù tệp có 6 byte. Đọc thêm 1 byte trả `-1` vì EOF; vị trí vẫn là 100.
5. `truncate(4)` cắt bớt đuôi, đồng thời kéo `position` từ 100 về 4. Đọc từ đầu xác nhận phần còn lại là `abXY`.
6. `position(10)` không đổi `size=4`; ghi một dấu `!` tại offset 10 mới tăng `size` thành 11, `position` thành 11. Ví dụ **không đọc hay đoán** giá trị các byte ở offset 4–9 vì giá trị gap không được API bảo đảm trên mọi provider.
7. `try-with-resources` đóng channel, còn `finally` xóa tệp tạm.

Hai hàm trợ giúp ở ví dụ có chủ ý ném `IOException` nếu channel không tiến triển. Cách này phù hợp để tránh vòng lặp vô tận trong ví dụ tệp cục bộ; với channel có khả năng không chặn và hoạt động bất đồng bộ, cần cơ chế điều phối riêng thay vì mặc định 0 nghĩa là lỗi.

## 9. `SeekableByteChannel` và `FileChannel`: dùng cái nào?

`FileChannel` triển khai `SeekableByteChannel`, vì vậy cũng hỗ trợ `position()`, `position(long)`, `size()`, `truncate(long)`, `read(ByteBuffer)` và `write(ByteBuffer)`.

`FileChannel` bổ sung các API hữu ích:

- `read(ByteBuffer dst, long position)`: đọc bắt đầu từ offset được cung cấp mà **không thay đổi vị trí hiện tại của channel**.
- `write(ByteBuffer src, long position)`: ghi tại offset được cung cấp mà **không thay đổi vị trí hiện tại của channel**.
- `map(...)`: ánh xạ một vùng tệp vào bộ nhớ.
- `transferTo(...)`/`transferFrom(...)`: truyền dữ liệu giữa channel thích hợp.
- `lock(...)`/`tryLock(...)`: khóa vùng tệp với ngữ nghĩa phụ thuộc hệ thống.
- `force(boolean metaData)`: yêu cầu đẩy cập nhật ra thiết bị lưu trữ theo hợp đồng của API.

**Chọn `SeekableByteChannel`** khi chỉ cần tập thao tác chung, muốn code làm việc với nhiều implementation/provider. **Chọn `FileChannel`** khi thực sự cần một khả năng mở rộng của `FileChannel`.

Ví dụ minh họa một phương thức đọc theo offset mà không sửa vị trí toàn cục, khi đã có `FileChannel channel` đang mở và quyền đọc phù hợp:

~~~java
ByteBuffer dst = ByteBuffer.allocate(4);
int n = channel.read(dst, 128); // Không làm đổi channel.position().
dst.flip();
~~~

Đây là mảnh code minh họa, cần import `java.nio.ByteBuffer`, và không giả định tệp có đủ 4 byte tại offset 128. `dst.position()` vẫn tăng theo số byte được đọc; chỉ **vị trí của FileChannel** là không đổi do lệnh đọc có offset.

Với `SeekableByteChannel` nói chung, bạn không có overload `read(dst, offset)`; phải thao tác `position(offset)` rồi `read(dst)`. Nếu nhiều tác vụ cùng chia sẻ một channel, hai lệnh riêng có thể bị xen kẽ, gây đọc/ghi sai offset. Cần quản lý đồng bộ/ownership của channel hoặc cân nhắc API định vị độc lập của `FileChannel`.

## 10. Vấn đề đồng thời, sửa kích thước và tính nhất quán

Các thao tác seek và I/O có thể tạo race condition khi cùng sử dụng một channel:

~~~text
Thread A: position(100)
Thread B: position(0)
Thread A: read(buffer)   → có thể đọc từ vị trí không mong muốn
~~~

Vì vậy, không nên tách `position(offset)` và `read/write` trên một channel chia sẻ rồi mặc định đó là một thao tác nguyên tử. Hãy quản lý truy cập của các thread hoặc sử dụng API đọc/ghi theo offset của `FileChannel` khi phù hợp. Đặc tính đồng thời chi tiết tùy loại channel/provider và môi trường.

Tương tự, `size()` là thông tin về kích thước **tại thời điểm gọi**. Một tiến trình khác có thể sửa tệp ngay sau đó; logic `if (position < size()) ...` không phải bảo đảm rằng byte sẽ còn tồn tại đến lúc đọc. Nếu ứng dụng cần nhất quán giữa nhiều tiến trình, phải thiết kế cơ chế phối hợp tệp thích hợp.

`truncate` có thể làm mất dữ liệu không thể khôi phục nếu chưa có bản sao hoặc thông tin phục hồi. Trong ứng dụng thực tế, xác minh đúng tệp, đúng kích thước cắt và chiến lược backup trước khi dùng trên tài liệu quan trọng.

Một số provider có thể là read-only hoặc không hỗ trợ đủ chế độ mở/thao tác, và có thể báo `UnsupportedOperationException`, `NonWritableChannelException`, `IOException` hoặc các ngoại lệ riêng. Không suy luận toàn bộ tính năng từ tên tệp hay scheme URI; sử dụng API và xử lý lỗi đúng ngữ cảnh.

## 11. Lỗi phổ biến

### Nhầm `position` với `size`

**Sai:** cho rằng đặt `position(100)` sẽ tự tạo tệp dài 100 byte.

**Đúng:** chỉ đặt con trỏ; size chỉ tăng khi thực sự ghi dữ liệu vượt EOF (hoặc có cơ chế khác tác động).

### Quên `ByteBuffer.flip()`

Sau `read(buffer)`, buffer vẫn có `position` ở cuối vùng đã điền. Muốn đọc dữ liệu từ buffer phải `flip()` để đặt `limit=position cũ`, `position=0`. `channel.position(0)` chỉ thay vị trí **channel**, không tự flip buffer.

### Muốn chèn byte nhưng lại overwrite

Ghi `XY` tại offset 2 của `abcdef` tạo `abXYef`. Nếu cần chèn thêm byte làm dữ liệu phía sau dịch chuyển, phải xây giải thuật dịch phần đuôi hoặc tạo tệp mới; `write` không có ngữ nghĩa insert.

### Giả định `truncate` có thể mở rộng tệp

`truncate(100)` không làm tệp 6 byte thành 100 byte. Để mở rộng cần ghi hoặc cơ chế hỗ trợ cụ thể và xác định chính sách byte điền.

### Mở nhầm chế độ `TRUNCATE_EXISTING`

Trước khi seek/overwrite một file hiện hữu, không được thêm `TRUNCATE_EXISTING` theo thói quen; option này làm mất dữ liệu **ngay lúc mở**.

### Bỏ qua số byte thực tế đã đọc/ghi

Đọc/ghi với ByteBuffer có thể chuyển ít byte hơn `remaining()`. Luôn xem giá trị trả về và trạng thái buffer. Nếu mong đủ `n` byte, phải lặp, xử lý EOF hoặc điều kiện không tiến triển.

### Dùng `APPEND` rồi mong `position(long)` điều khiển vị trí ghi

`APPEND` được thiết kế cho ghi nối vào cuối; không dùng khi cần ghi đè offset bất kỳ. Hãy mở quyền `WRITE` phù hợp và bỏ `APPEND`.

### Đếm offset theo ký tự Unicode

`position` tính **byte**, không tính ký tự Java hay Unicode code point. Với UTF-8, chuỗi “Việt” chứa nhiều byte hơn số ký tự trông thấy. Khi seek theo record text, cần định dạng có byte offset được lưu/đánh chỉ mục rõ ràng, hoặc giải mã tuần tự; không lấy chỉ số ký tự làm offset byte một cách máy móc.

## 12. Bài tập tự kiểm tra

1. Tệp `0123456789` có size 10. Đặt `position(3)` rồi ghi 2 byte `AB`. Kết quả? **`012AB56789`, size 10, position 5**.
2. Tệp size 10 và position 4; gọi `truncate(7)`. Kết quả? **size 7, position 4**. Nếu position là 9 trước khi truncate thì sau đó position thành 7.
3. Tệp size 10; gọi `truncate(20)`. Kết quả? **size vẫn 10**.
4. Tệp size 5; gọi `position(12)` rồi đọc. Điều gì xảy ra? Với tệp thông thường, **`read` trả -1**, size không đổi. Vị trí không tự quay lại EOF.
5. Tệp `abcdef`, con trỏ ở 0 và buffer vừa `read` 4 byte. `position` của channel là bao nhiêu nếu đủ 4 byte? **4**. Sau đó `dst.flip()` có làm channel quay về 0 không? **Không**.
6. Vì sao `FileChannel.read(dst, 100)` giúp giảm rủi ro khi nhiều người đọc các offset khác nhau? Vì nó dùng **offset riêng cho lần đọc** mà không thay đổi vị trí chung của channel. Các yếu tố đồng thời khác vẫn cần được quản lý.
7. Muốn sửa metadata ở offset cố định của tệp nhị phân lớn mà giữ nguyên phần còn lại, bạn sẽ mở channel bằng mode nào và thực hiện những bước gì? **Mở READ/WRITE phù hợp, định vị offset byte chính xác, ghi byte đúng độ dài, kiểm tra kết quả và đóng channel**; không dùng `TRUNCATE_EXISTING` hoặc `APPEND`.

**Ghi nhớ:** `SeekableByteChannel` cho phép **đọc/ghi ở vị trí tùy ý** nhờ `position(long)`, quan sát kích thước với `size()` và cắt đuôi bằng `truncate(long)`. Di chuyển vị trí không đổi nội dung; đọc/ghi mới làm vị trí tiến lên. Luôn tách trạng thái **channel** khỏi trạng thái **ByteBuffer**, hiểu quyền mở và kiểm tra số byte I/O thực tế.
