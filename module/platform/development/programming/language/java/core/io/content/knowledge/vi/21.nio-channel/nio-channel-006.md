# NIO Channel: vòng lặp đọc ghi dựa trên position và remaining

Trong Java NIO, một lời gọi `ReadableByteChannel.read(ByteBuffer)` hoặc `WritableByteChannel.write(ByteBuffer)` **không có nghĩa là toàn bộ dữ liệu đã được đọc hoặc ghi**. Channel chuyển một số byte, rồi cập nhật `position` của `ByteBuffer`. Vì vậy, chương trình cần lặp dựa trên **`position()`, `limit()`, `remaining()` và giá trị trả về của read/write**.

Đây là nền tảng để sao chép file chính xác, truyền thông điệp qua socket, xử lý bản ghi có kích thước cố định, và thiết kế chương trình không bị mất byte khi I/O trả về ít hơn yêu cầu.

## 1. Ba quy tắc quan trọng nhất

**Quy tắc 1: `read(buffer)` ghi vào buffer ở vị trí hiện tại.** Phương thức trả về số byte đã đọc `n`; nếu `n > 0` thì `position` tăng đúng `n`. Không được giả định mỗi lần `read` sẽ làm đầy buffer.

**Quy tắc 2: `write(buffer)` lấy byte từ vị trí hiện tại đến trước `limit`.** Phương thức trả về số byte đã ghi `n`; nếu `n > 0` thì `position` tăng đúng `n`. Không được bỏ những byte còn lại nếu một lời gọi ghi chưa tiêu thụ hết buffer.

**Quy tắc 3: Chuyển pha đúng cách.** Sau khi channel đọc **vào** buffer, gọi `flip()` để bắt đầu tiêu thụ dữ liệu. Sau khi tiêu thụ xong, gọi `clear()` để nhận đợt mới; hoặc `compact()` nếu còn dữ liệu chưa thể xử lý.

Phạm vi bài này là các channel đồng bộ trong `java.nio.channels`, đặc biệt `FileChannel` và `SocketChannel`. Với non-blocking channel, còn cần phối hợp `Selector` khi một lời gọi trả về 0.

## 2. Mô hình position, limit, capacity, remaining

Mỗi `Buffer` theo dõi:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity()` | Dung lượng tối đa tính theo **phần tử buffer**; với `ByteBuffer` là byte. |
| `limit()` | Ranh giới *không bao gồm* phần tử được phép đọc/ghi kế tiếp. |
| `position()` | Vị trí kế tiếp cho thao tác tương đối, được channel cập nhật khi chuyển byte. |
| `remaining()` | Số phần tử trong vùng có thể xử lý: `limit() - position()`. |
| `hasRemaining()` | `true` khi `remaining() > 0`. |

Bất biến bắt buộc:

```text
0 <= position <= limit <= capacity
remaining = limit - position
```

Một `ByteBuffer.allocate(8)` có trạng thái ban đầu:

```text
capacity = 8, limit = 8, position = 0, remaining = 8
[ .  .  .  .  .  .  .  . ]
  ^
  byte kế tiếp do channel.read(buffer) ghi vào
```

Giả sử `read` trả về 3, ba byte được đặt vào buffer, `position = 3`. Sau `flip()`, trạng thái thành `position = 0, limit = 3, remaining = 3`. Nếu `write` tiêu thụ 2 byte, `position = 2, remaining = 1`: **byte cuối vẫn cần được ghi**.

```text
Sau read trả về 3:              Sau flip:                    Sau write trả về 2:
position=3, limit=8             position=0, limit=3          position=2, limit=3
[A  B  C  .  .  .  .  .]       [A  B  C | .  .  .  .  .]     [A  B | C  .  .  .  .  .]
         ^                      ^                                  ^
                              3 byte chờ ghi                  1 byte còn lại
```

Điều kiện đúng để ghi phần còn lại là `while (buffer.hasRemaining())`, **không** kiểm tra `buffer.position() < buffer.capacity()`: capacity có thể lớn hơn limit sau `flip()`.

## 3. Hiểu giá trị trả về của read và write

Với `ReadableByteChannel.read(ByteBuffer dst)`:

- **`n > 0`**: đọc được `n` byte, tăng `dst.position()` đúng `n`.
- **`n == 0`**: chưa chuyển byte trong lần gọi này. Trên non-blocking `SocketChannel`, điều này rất bình thường khi chưa có dữ liệu; cần chờ readiness, không chạy vòng lặp bận vô hạn.
- **`n == -1`**: kết thúc luồng đầu vào (EOF). Không có thêm byte để đọc. Với một file channel, EOF là điểm dừng thông thường; với protocol có framing, EOF trước khi đủ khung có thể là lỗi dữ liệu thiếu.

Đối với `WritableByteChannel.write(ByteBuffer src)`:

- **`n > 0`**: đã ghi `n` byte và tăng `src.position()` theo số byte đó.
- **`n == 0`**: chưa chuyển byte. Trường hợp này có thể xuất hiện khi channel non-blocking chưa sẵn sàng để ghi. Việc retry liên tục ngay lập tức sẽ đốt CPU.
- `write` không có giá trị trả về `-1` để báo EOF như `read`. Lỗi ghi được biểu đạt qua `IOException` hoặc trạng thái channel, tùy loại.

Nếu buffer không còn byte có thể ghi (`!src.hasRemaining()`) thì thường không cần gọi `write`. Nếu đích của `read` đã đầy (`!dst.hasRemaining()`), hãy tiêu thụ hoặc chuyển pha trước, thay vì tiếp tục đọc vào một buffer không còn chỗ.

**Blocking không đồng nghĩa mỗi lệnh làm xong cả buffer.** Một blocking channel có thể chỉ đọc một phần, hoặc ghi một phần; việc gọi blocking chỉ mô tả cơ chế chờ nhất định của channel, không hứa một lời gọi chuyển đúng `remaining()` byte. Ngược lại, non-blocking channel thường trả về 0 khi chưa sẵn sàng.

## 4. Mẫu vòng lặp ghi đúng cho blocking channel

Sau khi buffer đã ở **pha đọc** (thường sau `flip()`), mẫu cơ bản:

```java
// Snippet: channel là WritableByteChannel đang mở;
// buffer chứa byte cần gửi trong [position, limit).
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n == 0) {
        throw new IOException("Không có tiến triển khi ghi");
    }
}
```

Đoạn trên là snippet với `channel`, `buffer` được khai báo bên ngoài và `IOException` được xử lý. Nó **cố ý fail fast** nếu không có tiến triển, phù hợp với một tác vụ I/O blocking mà ứng dụng lựa chọn báo lỗi thay vì chờ. Nó **không phải thuật toán chung cho non-blocking channel**, nơi 0 có thể hợp lệ; ở phần non-blocking bên dưới sẽ chờ sự kiện `OP_WRITE`.

Vì sao cần vòng `while`? Giả sử `buffer.remaining() == 10`, lần `write` đầu trả 4. Channel đã tự tăng `position` thêm 4; còn 6 byte chưa gửi. Gọi `write` tiếp trên **chính buffer đó** sẽ bắt đầu ở byte thứ năm. Nếu chương trình gọi `clear()` ngay sau lần ghi thứ nhất, sáu byte còn lại sẽ bị mất khỏi luồng đầu ra của ứng dụng.

**Không tự cộng position theo n** sau `write(buffer)`: channel đã làm việc đó. Cộng lần nữa khiến ứng dụng bỏ qua byte. Không dùng `buffer.array()` để gửi thay cho `buffer` nếu muốn tôn trọng position, limit và hỗ trợ direct buffer.

## 5. Mẫu vòng lặp đọc đúng cho FileChannel

Với `FileChannel` đọc một file thông thường và dữ liệu được xử lý ngay:

```java
// Snippet: channel là FileChannel mở READ;
// consume nhận dữ liệu đang ở pha đọc [position, limit).
ByteBuffer buffer = ByteBuffer.allocate(8192);
while (true) {
    int n = channel.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        throw new IOException("Đọc file không có tiến triển");
    }

    buffer.flip();
    consume(buffer);
    buffer.clear();
}
```

Đây là **mã minh họa**, không phải chương trình độc lập; nó giả sử hàm `consume` xử lý **hết mọi byte** trong buffer. Nếu `consume` chỉ tiêu thụ một phần vì chưa đủ một frame, thay `clear()` bằng `compact()` và quản lý state như phần 8. Khi xử lý file tĩnh thông thường, mỗi `read` có thể trả về số byte nhỏ hơn capacity, đặc biệt ở cuối file.

Cách viết tổng quát cho việc đọc **đủ N byte** là lưu số còn thiếu và tiếp tục gọi `read`. Không được dùng một lần `read` rồi kết luận dữ liệu đầu vào đã đủ N byte. Với NIO, `ByteBuffer.position()` là chỉ báo trực tiếp về số byte đã được thêm tính từ khi đặt position ban đầu.

## 6. Ví dụ Java 17+ đầy đủ: sao chép file và xác minh toàn bộ byte

Ví dụ dưới đây tạo hai file tạm, ghi `Hello NIO!` vào file nguồn, sao chép bằng `FileChannel` qua buffer chỉ **4 byte**, kiểm tra kết quả rồi dọn file. Dung lượng nhỏ làm lộ rõ việc phải lặp nhiều lần; mã vẫn xử lý đúng khi một lần `write` chỉ ghi được một phần dữ liệu.

Lưu thành **`ChannelLoopDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ChannelLoopDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("channel-source-", ".bin");
        Path target = Files.createTempFile("channel-target-", ".bin");

        try {
            Files.writeString(source, "Hello NIO!", StandardCharsets.UTF_8);

            long totalRead = 0;
            long totalWritten = 0;
            ByteBuffer buffer = ByteBuffer.allocate(4);

            try (FileChannel in = FileChannel.open(
                         source, StandardOpenOption.READ);
                 FileChannel out = FileChannel.open(
                         target, StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {

                while (true) {
                    int n = in.read(buffer);
                    if (n == -1) {
                        break;
                    }
                    if (n == 0) {
                        throw new IOException("Không có tiến triển khi đọc");
                    }

                    totalRead += n;
                    buffer.flip(); // position=0, limit=số byte vừa đọc

                    while (buffer.hasRemaining()) {
                        int written = out.write(buffer);
                        if (written == 0) {
                            throw new IOException("Không có tiến triển khi ghi");
                        }
                        totalWritten += written;
                    }

                    buffer.clear(); // đã chuyển hết byte; sẵn sàng đọc đợt sau
                }
            }

            System.out.println("read=" + totalRead
                    + " written=" + totalWritten);
            System.out.println("result="
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("identical="
                    + (Files.mismatch(source, target) == -1));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

Chạy:

```bash
javac ChannelLoopDemo.java
java ChannelLoopDemo
```

Stdout:

```text
read=10 written=10
result=Hello NIO!
identical=true
```

**Giải thích trình tự:**

1. `Files.writeString` tạo payload ASCII dài 10 byte; ứng dụng mở `FileChannel` đầu vào để đọc và đầu ra để ghi.
2. `in.read(buffer)` thêm từ 1 đến tối đa 4 byte vào vị trí hiện tại; `totalRead` cộng đúng số thực tế. Không dùng `buffer.capacity()` thay cho `n`.
3. `buffer.flip()` chuyển sang pha ghi **ra channel**: limit được đặt bằng position cũ (số byte vừa đọc), position về 0.
4. `out.write(buffer)` lấy byte từ position đến limit; một lần có thể chưa hết, nên `while (buffer.hasRemaining())` ghi đến khi buffer trống.
5. Chỉ khi **mọi byte đã được ghi**, `buffer.clear()` mới an toàn: nó reset state thành position 0, limit capacity để nhận block mới.
6. Khi `read` trả về `-1`, vòng lặp dừng; hai channel được đóng. `Files.mismatch(source, target) == -1` xác nhận hai file có nội dung byte giống nhau, không chỉ là chuỗi in ra giống nhau.

Trong ví dụ file blocking này, nếu read/write trả về 0 bất ngờ, chương trình báo lỗi rõ ràng để tránh busy loop. Với ứng dụng thực tế, chính sách no-progress phụ thuộc loại channel, deadline và nhu cầu chờ I/O; không nên suy diễn một vòng `while` spin là an toàn với mọi channel.

## 7. Sai lầm điển hình: một lần write là đủ

Mã sai sau có thể làm mất dữ liệu khi output channel chỉ nhận một phần:

```java
int n = in.read(buffer);
if (n > 0) {
    buffer.flip();
    out.write(buffer); // SAI: không bảo đảm ghi hết remaining()
    buffer.clear();    // Các byte chưa ghi có thể bị bỏ qua.
}
```

Sửa thành:

```java
int n = in.read(buffer);
if (n > 0) {
    buffer.flip();
    while (buffer.hasRemaining()) {
        int written = out.write(buffer);
        if (written == 0) {
            throw new IOException("Ghi không có tiến triển");
        }
    }
    buffer.clear();
}
```

Hai đoạn là **snippet có biến `in`, `out`, `buffer` trong ngữ cảnh**, không phải chương trình chạy độc lập; nếu không chạy blocking, điều chỉnh nhánh trả về 0 theo readiness thay vì ném lỗi. Khi `read` trả `-1`, cần thoát khỏi vòng đọc ở cấp trên.

Lỗi tương tự xảy ra khi đọc đúng một lần vào buffer rồi mặc định số byte đó là **một thông điệp hoàn chỉnh**. Trong giao thức trên TCP, một `read` có thể trả về một phần khung, nhiều khung hoặc không byte; TCP là luồng byte, không bảo toàn ranh giới thông điệp của các lệnh `write`.

## 8. compact khi chưa tiêu thụ hết một khung dữ liệu

Nếu buffer chứa dữ liệu dở dang, `clear()` sẽ bỏ qua các byte chưa xử lý về mặt logic. Dùng `compact()` để giữ phần `[position, limit)`, chuyển chúng về đầu buffer rồi chuẩn bị ghi thêm byte.

Ví dụ đầu vào là các bản ghi cố định **4 byte**:

```java
// Snippet: buffer là ByteBuffer ở pha ghi.
// Tùy channel và ứng dụng, cần xử lý n == 0/-1 bên ngoài.
buffer.flip();

while (buffer.remaining() >= Integer.BYTES) {
    int value = buffer.getInt(); // Tiêu thụ 4 byte.
    handle(value);
}

buffer.compact(); // Giữ 0..3 byte chưa tạo thành một int hoàn chỉnh.
```

Khi `compact()` kết thúc, phần dữ liệu chưa đọc nằm ở đầu buffer; `position` bằng số byte giữ lại và `limit` về capacity. Lần `read(buffer)` tiếp theo nối dữ liệu mới **sau phần còn giữ**, nên parser không làm mất bản ghi bị chia giữa hai lần đọc.

Một vòng lặp đầy đủ cho record cố định cần kiểm tra thêm:

- Trong pha đọc, chỉ gọi `getInt()` khi `remaining() >= 4`, tránh `BufferUnderflowException`.
- Nếu EOF mà vẫn còn 1–3 byte chưa ghép thành bản ghi, file/protocol bị cắt giữa chừng; quyết định rõ sẽ báo lỗi hay chấp nhận phần dư.
- Với parser khung có length-prefix, phải xác minh độ dài không âm, nằm trong quota và có đủ byte trước khi cấp phát/giải mã.
- Dung lượng buffer phải đủ để chứa tối thiểu một đơn vị header cần phân tích, hoặc parser cần hỗ trợ state để thu thập header dần. Nếu buffer không còn chỗ mà không xử lý được bản ghi quá lớn, phải mở rộng/stream payload theo chính sách.

**`compact()` khác `clear()`:** compact sao chép phần chưa đọc về đầu và thay position; clear chỉ reset state, không xóa byte nhưng sẽ cho phép lần đọc kế tiếp ghi đè vùng dữ liệu cũ.

## 9. Ví dụ về EOF khi đang tích lũy frame

Giả sử protocol định nghĩa mỗi frame gồm **4 byte độ dài + N byte payload**. Nếu `read` trả `-1` trước khi có đủ 4 byte header hoặc trước khi đủ N byte payload, đó là **frame chưa hoàn chỉnh**, không phải kết thúc hợp lệ của một frame.

Không thể xử lý bằng cách đọc `channel.read(headerBuffer)` một lần duy nhất. Mã phác thảo blocking channel:

```java
// Snippet: channel là ReadableByteChannel đồng bộ;
// header là ByteBuffer.allocate(4).
while (header.hasRemaining()) {
    int n = channel.read(header);
    if (n == -1) {
        throw new EOFException("Thiếu dữ liệu header");
    }
    if (n == 0) {
        throw new IOException("Đọc header không có tiến triển");
    }
}
header.flip();
int payloadSize = header.getInt();
if (payloadSize < 0 || payloadSize > 1_048_576) {
    throw new IOException("Payload size không hợp lệ");
}
```

Đây là **snippet** yêu cầu import `java.io.EOFException`, `java.io.IOException` và các biến được khởi tạo trước. Nếu EOF xảy ra **trước khi bắt đầu bất kỳ header mới nào**, một protocol có thể coi là kết thúc sạch; còn EOF giữa header/payload phải được báo là truncate. Phân biệt hai trường hợp bằng state của parser hoặc số byte đã thu thập cho frame.

Việc kiểm tra `payloadSize` ngăn cấp phát theo độ dài độc hại. Với payload lớn, thiết kế streaming theo chunk để giới hạn memory, không ép mọi thông điệp vào một buffer khổng lồ.

## 10. SocketChannel non-blocking: không quay vòng khi trả về 0

Sau `SocketChannel.configureBlocking(false)`:

- `read(buffer) == 0` nghĩa là hiện chưa có byte để đọc; quay lại làm việc khác hoặc đợi `SelectionKey.OP_READ` qua `Selector`.
- `write(buffer) == 0` nghĩa là hiện chưa gửi được byte; giữ nguyên buffer cùng vị trí, đợi khả năng ghi với `OP_WRITE`.
- `read(buffer) == -1` là đầu vào đã kết thúc; xử lý EOF/half-close và trạng thái protocol theo thiết kế.
- Sau khi đọc/ghi `n > 0`, cả hai API đã tự tăng `position`. Trước khi đọc lần nữa, parser phải xử lý dữ liệu vừa nhận, `compact()` hoặc `clear()` cho phù hợp.

Ví dụ phác thảo cho **một buffer outbound**:

```java
// Snippet: socket là SocketChannel không blocking,
// pending là ByteBuffer đã flip, dùng để gửi.
// Chạy khi Selector thông báo có thể ghi.
while (pending.hasRemaining()) {
    int n = socket.write(pending);
    if (n == 0) {
        break; // Giữ nguyên pending; chờ OP_WRITE lần tiếp theo.
    }
}
if (!pending.hasRemaining()) {
    // Bỏ quan tâm OP_WRITE nếu không còn dữ liệu chờ gửi.
}
```

Đây là **mã minh họa**, không bao gồm cấu hình Selector/SelectionKey và quản lý hàng đợi message. Một ứng dụng thực tế cần giữ `pending` qua các vòng event loop, không tạo mới nó khi write chưa xong; cập nhật interest ops theo backlog để tránh CPU bận vì `OP_WRITE` luôn sẵn sàng khi socket còn khả năng ghi.

**Tuyệt đối không dùng `while (socket.write(pending) == 0) { }`**: việc chờ readiness hay timeout là trách nhiệm của event loop. Với NIO, tránh busy spin là một phần của tính đúng đắn về vận hành.

## 11. FileChannel: vị trí file khác vị trí buffer

Cả `FileChannel` và `ByteBuffer` đều có khái niệm `position`, nhưng đó là **hai con trỏ khác nhau**:

| Con trỏ | Quản lý cái gì? | API ví dụ |
| --- | --- | --- |
| `buffer.position()` | Index byte tiếp theo trong buffer. | `buffer.position()`, `flip()`, `clear()` |
| `channel.position()` | Byte offset hiện tại trong file. | `FileChannel.position()`, `position(long)` |

Khi gọi `channel.read(buffer)` dạng không truyền offset, `FileChannel` thường cập nhật cả vị trí file theo số byte đọc được và vị trí buffer theo cùng số byte. Ngược lại, các lệnh positional:

```java
int n = channel.read(buffer, 100L);
int m = channel.write(buffer, 200L);
```

là **snippet** áp dụng với `FileChannel` đã mở có quyền phù hợp. Chúng sử dụng vị trí file **được chỉ định** và không thay đổi `channel.position()` hiện tại, nhưng **vẫn cập nhật `buffer.position()`** theo số byte thực tế. Không nhầm việc không dịch file position với việc không dịch buffer position.

`FileChannel.transferTo`/`transferFrom` có thể hỗ trợ truyền dữ liệu hiệu quả nhưng cũng **có thể chuyển ít byte hơn yêu cầu**; chương trình vẫn cần lặp, kiểm tra số đã chuyển và xử lý tình trạng 0 phù hợp. Không bỏ quy tắc kiểm soát partial I/O chỉ vì dùng một API ở mức cao hơn.

## 12. Điều kiện dừng, tiến triển và tổng số byte

Một vòng lặp I/O đáng tin cần có:

1. **Mục tiêu rõ ràng:** Đọc đến EOF, thu đủ N byte, gửi toàn bộ `remaining()`, hay xử lý đến khi parser không còn frame hoàn chỉnh.
2. **Điều kiện dừng hợp lệ:** `read == -1` với file, buffer hết dữ liệu cần ghi, payload length đã thỏa, hoặc kết thúc theo protocol.
3. **Điều kiện chờ:** `read/write == 0` thì không có tiến triển; non-blocking phải chờ readiness, blocking có chính sách timeout/fail-fast thích hợp.
4. **Xử lý ngoại lệ:** `IOException`, channel bị đóng và các lỗi payload bất thường; giải phóng resource qua `try-with-resources`.
5. **Giới hạn nguồn lực:** quota kích thước, thời gian, số frame, và tổng byte nếu xử lý đầu vào không tin cậy.

Nếu phải đọc đúng N byte, dùng bộ đếm `long` hoặc buffer có limit đã đặt phù hợp. Đừng dựa hoàn toàn vào việc một `read` trả số byte bằng `buffer.capacity()`; lần đọc cuối có thể trả ít hơn, và buffer còn chứa dữ liệu cũ ở vùng chưa được ghi đợt này.

Trong mạng thực tế, deadline/timeout cần áp dụng lên **toàn bộ thao tác** chứ không chỉ từng lần đọc/ghi; điều này tránh peer chậm gửi từng byte để kéo dài kết nối vô hạn. Với file lớn, ghi bộ đếm `long` để tránh tràn khi tổng số byte vượt `Integer.MAX_VALUE`.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| File đích ngắn hơn nguồn | Chỉ gọi `write(buffer)` một lần trước `clear()`. | Lặp `while (hasRemaining())` để ghi hết buffer. |
| File đích chứa byte 0 hoặc byte cũ | Không `flip()` sau `read`, hoặc dùng capacity làm số byte hợp lệ. | `flip()` để giới hạn đúng vùng dữ liệu vừa nhận. |
| Lặp vô hạn, CPU tăng | Channel trả 0 liên tục, vòng loop không có wait/failfast. | Blocking có chính sách no-progress; non-blocking đợi Selector. |
| Parser mất một phần message | Gọi `clear()` khi vẫn còn byte chưa đọc. | Dùng `compact()` và parser tích lũy phần thiếu. |
| `BufferUnderflowException` | `getInt()` dù chưa đủ 4 byte. | Kiểm tra `remaining() >= Integer.BYTES`. |
| `BufferOverflowException` | Đọc vào buffer hết chỗ/ghi vượt limit. | Quản lý pha buffer và quota payload. |
| EOF bị xem là 0 | Không phân biệt `-1` và `0`. | `-1` kết thúc input; 0 là chưa chuyển byte. |
| Socket nhận thiếu thông điệp | Mặc định một `read` bằng một thông điệp. | Dùng frame: fixed-size, delimiter, hoặc length-prefix. |
| Byte bị lặp/mất | Tự cộng `buffer.position()` sau `channel.write/read`. | Để channel dịch position; chỉ đặt lại khi chuyển pha có chủ đích. |
| Đọc cùng byte nhiều lần ngoài ý muốn | `flip()` hoặc `rewind()` sai thời điểm. | Ghi rõ state machine và kiểm tra position/limit trước/sau. |

Một điều nên kiểm tra trong code review là: **mỗi lệnh chuyển pha buffer có dựa trên thực tế đã xử lý hết dữ liệu của pha trước chưa?** Đặc biệt, đặt `clear()` ngay sau một `write` không có vòng `remaining` là dấu hiệu dễ mất dữ liệu.

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài tập 1 — Mô phỏng partial write.** Buffer chứa 10 byte, `position=0, limit=10`. Channel lần lượt ghi được 4, 3, 3 byte. Hãy ghi `position/remaining` sau mỗi lần: `(4,6)` → `(7,3)` → `(10,0)`. Giải thích vì sao `while (hasRemaining())` dừng đúng lúc.

**Bài tập 2 — Sao chép file bất kỳ.** Đổi ví dụ thành buffer dung lượng 7 hoặc 8192 và file nguồn chứa nhiều dòng Unicode. Xác minh bằng `Files.mismatch` rằng số byte bằng nhau. Vì sao không thể suy số byte UTF-8 chỉ từ `String.length()`?

**Bài tập 3 — Parser `int` với compact.** Chuyển một stream byte chứa ba số `int` big-endian bằng các lượt đọc trả lần lượt 3, 2, 4, 3 byte. Viết vòng `flip()` → `while (remaining() >= 4) getInt()` → `compact()`, theo dõi số byte còn lại sau mỗi đợt.

**Bài tập 4 — EOF giữa frame.** Thiết kế hàm `readExactly(channel, buffer)` cho blocking channel đã có header 4 byte, phân biệt EOF sạch trước khung mới và EOF bất ngờ khi mới thu 1–3 byte. Bổ sung kiểm tra no-progress.

**Bài tập 5 — Non-blocking send.** Giả sử socket chỉ gửi 2 byte, sau đó trả 0 rồi có sự kiện `OP_WRITE` mới. Hãy mô tả trạng thái buffer phải giữ lại giữa các event; vì sao tạo buffer từ đầu ở mỗi event làm gửi trùng dữ liệu?

**Câu hỏi kiểm tra nhanh:**

- Sau `read(buffer)` nhận 5 byte, vì sao phải `flip()` trước khi ghi các byte đó ra channel?
- `remaining()` khác `capacity()` ở điểm nào sau `flip()`?
- Khi `write` trả 2 trong lúc `remaining = 8`, chương trình còn bao nhiêu byte chưa gửi?
- Khi `read == 0`, có thể kết luận EOF không?
- Nếu parser chỉ xử lý 4 trên tổng 7 byte, nên `clear()` hay `compact()`?
- Vì sao `FileChannel.read(buffer, offset)` có thể không thay `channel.position()` nhưng vẫn thay `buffer.position()`?

**Ghi nhớ:** `position` và `remaining` cho biết **bao nhiêu byte còn cần xử lý**; giá trị trả về của `read/write` cho biết **bao nhiêu byte thực tế đã chuyển trong lượt này**. Ghép hai thông tin đó với `flip/clear/compact` và chính sách cho `-1`/`0` là nền tảng của mọi vòng đọc ghi NIO Channel đúng đắn.
