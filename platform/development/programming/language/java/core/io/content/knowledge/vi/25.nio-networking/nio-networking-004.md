# TCP là luồng byte, không bảo toàn ranh giới bản tin — Java NIO mạng

## 1. Mục tiêu bài học

Khi hai ứng dụng trao đổi dữ liệu bằng TCP, phía gửi có thể gọi `write()` nhiều lần, nhưng phía nhận **không có bảo đảm rằng mỗi lần `read()` ứng với một lần `write()`**. TCP cung cấp **một luồng byte có thứ tự**, không cung cấp sẵn khái niệm “một bản tin” ở cấp ứng dụng.

Đây là điểm nền tảng khi lập trình `SocketChannel`, `ServerSocketChannel` và `ByteBuffer` trong Java NIO. Nếu bỏ qua, ứng dụng dễ gặp các lỗi: JSON nhận thiếu, hai lệnh dính liền, giải mã UTF-8 sai hoặc giao thức bị treo vì không biết một bản tin đã kết thúc hay chưa.

Sau bài này, bạn có thể:

- Giải thích chính xác vì sao một lần ghi không tương đương một lần đọc TCP.
- Phân biệt **TCP segment**, **byte stream**, **application message** và **frame**.
- Thiết kế giao thức xác định ranh giới bản tin bằng độ dài, delimiter hoặc kích thước cố định.
- Đọc/ghi đủ byte với `SocketChannel`, xử lý giá trị trả về nhỏ hơn dự kiến, `0` và `-1`.
- Dùng `ByteBuffer` đúng cách, đặc biệt với `flip()`, `clear()`, `compact()`.
- Phòng các lỗi về kích thước frame, UTF-8, blocking/non-blocking và dữ liệu đến từng phần.

## 2. TCP cung cấp gì và không cung cấp gì?

TCP là giao thức **hướng kết nối**, truyền một dãy byte có thứ tự. Khi kết nối còn hoạt động và dữ liệu được nhận thành công, TCP sắp xếp lại dữ liệu theo thứ tự byte của luồng; các cơ chế sequence number, retransmission, kiểm soát luồng và tắc nghẽn hoạt động bên dưới ứng dụng.

Tuy nhiên, **TCP không định nghĩa ranh giới bản tin của ứng dụng**. Ví dụ phía gửi thực hiện:

~~~text
write("ABC")
write("DEF")
write("GHI")
~~~

Phía nhận có thể quan sát các kết quả đọc như:

~~~text
Lần đọc 1: "ABCDEFGHI"
~~~

hoặc:

~~~text
Lần đọc 1: "A"
Lần đọc 2: "BCDE"
Lần đọc 3: "FGHI"
~~~

hoặc những cách chia khác, miễn thứ tự các byte được giữ nguyên. Đây là **những khả năng minh họa**, không phải quy luật cố định của TCP hay của một JVM.

Điều này cũng đúng khi người gửi gom tất cả byte vào **một** lần `write()`: một lần `read()` có thể trả về ít byte hơn. Ngược lại, nếu gửi bằng nhiều lần `write()`, một lần `read()` có thể trả về byte từ nhiều lời gọi ghi.

### Phân biệt các lớp

| Khái niệm | Ai xác định? | Có phải ranh giới bản tin ứng dụng không? |
| --- | --- | --- |
| TCP segment | TCP stack / đường truyền | **Không** |
| Các lần gọi `SocketChannel.write(...)` | Mã phía gửi | **Không** |
| Các lần gọi `SocketChannel.read(...)` | Mã phía nhận, dữ liệu sẵn có và trạng thái channel | **Không** |
| Frame của giao thức ứng dụng | Thiết kế giao thức của bạn (hoặc HTTP, WebSocket, v.v.) | **Có**, nếu giao thức định nghĩa đúng |
| Message nghiệp vụ | Ứng dụng | Có thể nằm trong một frame hoặc được ghép từ nhiều frame theo giao thức |

Không nên suy luận “mỗi TCP packet là một message”. Ứng dụng Java thông thường nhận **byte trên socket**, không nhận trực tiếp một danh sách các TCP segment để ghép theo packet.

> **Quy tắc:** Bên nhận phải tự xác định bản tin kết thúc ở đâu. Hãy áp dụng **message framing**, đừng đoán từ số lần `read()`.

## 3. Tại sao dữ liệu có thể bị chia nhỏ hoặc gộp lại?

Giả sử client gửi hai lệnh:

~~~text
LOGIN alice
PING
~~~

Nếu không có dấu kết thúc lệnh hay trường độ dài, bên nhận chỉ thấy chuỗi byte `LOGIN alicePING` và **không có cách tổng quát nào biết phải tách ở đâu**.

Ngay cả khi client gọi `write()` tách biệt hai lần, TCP và hệ điều hành vẫn có thể chia/gộp dữ liệu theo nhiều yếu tố:

1. **Kích thước buffer của ứng dụng:** nếu buffer nhận chỉ còn 4 byte, `read()` không thể đặt 10 byte vào đó.
2. **Thời điểm đọc:** dữ liệu từ nhiều lần ghi có thể đã đến trước một lần đọc.
3. **Phân đoạn/truyền lại TCP:** cách dữ liệu được đưa qua mạng không phải giao diện bản tin cho ứng dụng.
4. **Socket không chặn (non-blocking):** lần đọc hiện tại có thể chỉ nhận một phần, hoặc chưa có byte nào.
5. **Áp lực luồng (backpressure):** phía nhận/đích chậm khiến số byte chấp nhận trong một lần ghi nhỏ hơn yêu cầu.

Tên gọi hay gặp là “sticky packets” hoặc “packet fragmentation” ở tầng ứng dụng; cách hiểu chính xác hơn là **ứng dụng chưa thiết kế hoặc chưa xử lý framing trên một byte stream**.

TCP không làm thất lạc **ranh giới** mà nó từng hứa giữ: ngay từ đầu TCP **không hứa giữ ranh giới thông điệp**.

## 4. Đọc và ghi với `SocketChannel`: phải kiểm tra số byte thực tế

Trong Java NIO:

~~~java
int readBytes = socketChannel.read(readBuffer);
int writtenBytes = socketChannel.write(writeBuffer);
~~~

Hai lời gọi trả về số byte **thực tế** được đọc/ghi trong lần thực hiện, không nhất thiết bằng `ByteBuffer.remaining()` trước đó.

### Với `read(ByteBuffer)`

- Giá trị **dương**: đã đọc được số byte tương ứng, buffer tiến `position` đúng số byte.
- Giá trị **0**: lần này không đọc byte nào. Với channel **non-blocking**, thông thường là chưa có dữ liệu đọc được ngay; cũng có thể xảy ra khi buffer không có chỗ trống.
- Giá trị **-1**: đã gặp **end-of-stream (EOF)**, tức phía bên kia đã kết thúc chiều gửi dữ liệu và các byte còn được xếp hàng đã được tiêu thụ.
- Phát sinh `IOException`: lỗi I/O, đóng channel, reset kết nối hoặc điều kiện khác; không đồng nhất mọi lỗi với EOF bình thường.

Trong chế độ **blocking**, nếu buffer còn chỗ, lệnh đọc thường đợi đến khi có ít nhất một byte, EOF hoặc lỗi; **nó không đợi cho đủ cả bản tin ứng dụng**. Một lời gọi đọc thành công có thể chỉ trả về 1 byte.

### Với `write(ByteBuffer)`

- Giá trị **dương**: một phần hoặc toàn bộ số byte còn lại trong buffer đã được chấp nhận vào channel; `position` buffer tiến tương ứng.
- Giá trị **0**: lần gọi không ghi được byte nào, đặc biệt có thể gặp trong non-blocking. Không suy ra rằng peer đã nhận xong dữ liệu.
- Lần gọi `write()` trả về thành công **không bảo đảm phía đối tác đã đọc/xử lý** byte đó ở tầng ứng dụng.

Ví dụ vòng lặp cơ bản trong chế độ blocking:

~~~java
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n == 0) {
        throw new IOException("Socket ghi không tiến triển");
    }
}
~~~

Đoạn này chỉ minh họa, cần `channel` là `SocketChannel` **blocking**, `buffer` đã `flip()` để sẵn sàng đọc ra và import `java.io.IOException`. Trong non-blocking, nếu `write()` trả 0 thì **đăng ký chờ khả năng ghi** bằng `Selector` hoặc thiết kế sự kiện tương ứng, không quay vòng liên tục trên CPU.

## 5. Ba cách thiết kế ranh giới bản tin

### 5.1. Length-prefix framing: đặt độ dài ở đầu

Mỗi frame chứa độ dài payload trước, sau đó là đúng số byte payload. Ví dụ dùng một số nguyên 32-bit (4 byte) **big-endian**, không dấu ở cấp ý nghĩa giao thức nhưng khi đọc bằng Java `int` phải xác thực miền hợp lệ:

~~~text
[ 00 00 00 05 ][ H E L L O ][ 00 00 00 04 ][ J A V A ]
      4 byte        5 byte          4 byte       4 byte
      length=5                      length=4
~~~

Bên nhận làm theo các bước:

1. Đọc **đủ 4 byte** header, dù cần nhiều lần `read()`.
2. Giải mã độ dài theo endian đã thỏa thuận; từ chối số âm, quá lớn hoặc vượt giới hạn giao thức.
3. Đọc **đủ đúng số byte payload** đã công bố.
4. Chỉ khi đủ byte mới giải mã payload và xử lý một message.
5. Lặp lại bước 1 cho frame tiếp theo, kể cả khi các byte frame tiếp theo đã nằm sẵn trong buffer nhận.

**Ưu điểm:** payload có thể chứa byte bất kỳ, kể cả newline hoặc byte `0`; dễ kiểm tra tính đầy đủ. **Hạn chế:** cần quản lý trạng thái header/payload khi dữ liệu đến từng phần, phải giới hạn độ dài trước khi cấp phát bộ nhớ.

Một giao thức production nên chỉ rõ độ rộng header, endian, kích thước tối đa, encoding payload, phiên bản, xử lý frame lỗi và chính sách timeout.

### 5.2. Delimiter framing: dấu phân cách

Ví dụ lệnh văn bản kết thúc bằng LF (`\n`):

~~~text
PING\n
LOGIN alice\n
~~~

Phía nhận tích lũy byte đến dấu LF rồi tách message. Đây là lựa chọn đơn giản cho các giao thức line-oriented.

**Cẩn trọng:**

- Dấu phân cách có thể nằm trong payload; phải định nghĩa escaping/quoting hoặc cấm nó trong nội dung.
- Khi dùng UTF-8, phải bảo đảm giải mã đúng cả khi một ký tự nhiều byte bị chia qua các lần đọc; thường nên tách/ghép **byte** trước, rồi giải mã trọn message hoặc dùng `CharsetDecoder` có trạng thái.
- Phải giới hạn chiều dài dòng. Nếu peer gửi vô hạn mà không gửi `\n`, server không được tích lũy buffer vô hạn.
- Quy định rõ `\n` hay `\r\n`, cũng như cách xử lý dòng cuối kết thúc bằng EOF.

### 5.3. Fixed-size framing: mỗi frame có kích thước cố định

Nếu mọi bản ghi đều dài đúng 32 byte, bên nhận cứ tích đủ 32 byte rồi xử lý. Cách này phù hợp với giao thức nhị phân có schema cố định.

Nhược điểm: dữ liệu biến độ dài cần padding hoặc trường xác định chiều dài; không thể tự suy đoán bản ghi ngắn hơn. **Vẫn phải lặp đọc** đến khi đủ 32 byte, vì mỗi `read()` có thể trả về ít hơn.

### Phương án nào nên chọn?

| Giao thức | Ưu điểm | Điểm cần chú ý |
| --- | --- | --- |
| Length-prefix | Rõ kích thước; hỗ trợ payload nhị phân tùy ý | Kiểm tra giới hạn, endian, trạng thái header/body |
| Delimiter | Dễ đọc/debug với văn bản | Escaping, giới hạn chiều dài, encoding |
| Fixed-size | Đơn giản với record đồng nhất | Lãng phí padding, khó biểu diễn payload dài biến đổi |
| Kết thúc bởi EOF | Có thể phù hợp cho **một payload cuối cùng** trên kết nối | Không dùng để phân biệt nhiều message trên kết nối tiếp tục mở |

Tránh dùng **thời gian chờ**, `available()`, kích thước buffer hoặc số lần `read()` để đoán message đã hoàn tất. Những dữ kiện đó không xác định ranh giới giao thức.

## 6. Ví dụ Java 17+ hoàn chỉnh: hai bản tin trong một luồng TCP

Ví dụ sau tạo một TCP server trên loopback với cổng do hệ điều hành cấp, một client gửi liên tiếp hai frame, rồi server đọc đúng hai message theo length-prefix.

Để người học thấy rõ một message có thể cần **nhiều lần đọc**, hàm `readExactly` cố ý giới hạn mỗi lần đọc tối đa **3 byte** bằng `ByteBuffer.slice()`. Đây là giới hạn **do ví dụ chủ động đặt ra**, không phải hành vi phân đoạn mạng được TCP bảo đảm.

Lưu tệp **`TcpMessageFramingDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.FutureTask;

public class TcpMessageFramingDemo {
    private static final int MAX_FRAME_BYTES = 1024;
    private static final int READ_CHUNK = 3;

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(
                    new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));

            FutureTask<List<String>> received = new FutureTask<>(() -> {
                try (SocketChannel peer = listener.accept()) {
                    return List.of(readFrame(peer), readFrame(peer));
                }
            });
            Thread serverThread = new Thread(received, "tcp-frame-reader");
            serverThread.start();

            try (SocketChannel client = SocketChannel.open()) {
                client.connect((InetSocketAddress) listener.getLocalAddress());

                byte[] first = "HELLO".getBytes(StandardCharsets.UTF_8);
                byte[] second = "JAVA".getBytes(StandardCharsets.UTF_8);

                // Hai frame liên tiếp trong MỘT ByteBuffer của ứng dụng.
                ByteBuffer outgoing = ByteBuffer.allocate(
                        Integer.BYTES + first.length
                                + Integer.BYTES + second.length);
                outgoing.putInt(first.length).put(first);
                outgoing.putInt(second.length).put(second);
                outgoing.flip();

                // Một lời gọi write không được giả định sẽ ghi hết buffer.
                while (outgoing.hasRemaining()) {
                    int written = client.write(outgoing);
                    if (written == 0) {
                        throw new IOException("Blocking write không tiến triển");
                    }
                }
            }

            List<String> messages = received.get();
            System.out.println("Message 1: " + messages.get(0));
            System.out.println("Message 2: " + messages.get(1));
            System.out.println("Frame count: " + messages.size());
        }
    }

    private static String readFrame(SocketChannel channel)
            throws IOException {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
        readExactly(channel, header);
        header.flip();

        int byteLength = header.getInt();
        if (byteLength < 0 || byteLength > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + byteLength);
        }

        ByteBuffer payload = ByteBuffer.allocate(byteLength);
        readExactly(channel, payload);
        payload.flip();
        return StandardCharsets.UTF_8.decode(payload).toString();
    }

    private static void readExactly(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            ByteBuffer step = dst.slice();
            step.limit(Math.min(step.remaining(), READ_CHUNK));

            int n = channel.read(step);
            if (n == -1) {
                throw new EOFException(
                        "EOF giữa frame, còn thiếu "
                                + dst.remaining() + " byte");
            }
            if (n == 0) {
                // Demo dùng SocketChannel blocking và buffer còn chỗ.
                // Non-blocking cần Selector hoặc cơ chế chờ tương ứng.
                throw new IOException("Blocking read không tiến triển");
            }

            // Vì đọc qua slice, tự cập nhật vị trí của buffer gốc.
            dst.position(dst.position() + n);
        }
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 TcpMessageFramingDemo.java
java TcpMessageFramingDemo
~~~

**Stdout** khi kết nối loopback hoạt động bình thường:

~~~text
Message 1: HELLO
Message 2: JAVA
Frame count: 2
~~~

### Giải thích từng điểm quan trọng

1. `listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))` chỉ lắng nghe loopback, cổng `0` yêu cầu hệ điều hành chọn cổng sẵn có. Chương trình lấy chính địa chỉ vừa bind, nên stdout không phụ thuộc số cổng.
2. Server và client dùng `SocketChannel` **blocking mặc định**. Thread server đợi `accept()` rồi đọc hai frame. Thread chính gửi đủ hai frame và đợi kết quả bằng `FutureTask.get()`.
3. `outgoing.putInt(first.length)` đặt header 4 byte với byte order mặc định **big-endian**, sau đó đặt payload. Tương tự cho frame thứ hai. Hai frame nằm sát nhau trong 17 byte dữ liệu của ứng dụng.
4. `outgoing.flip()` chuyển buffer từ chế độ **ghi byte vào buffer** sang chế độ **đọc byte từ buffer để gửi ra socket**. Vòng `while (outgoing.hasRemaining())` xử lý ghi từng phần.
5. `readFrame` phải thu đủ 4 byte trước khi gọi `getInt()`, rồi thu đúng `byteLength` byte payload. Không suy đoán rằng vì client đã gửi hai frame liền nhau thì server sẽ nhận cả hai trong một lần `read()`.
6. `readExactly` đặt `step.limit(...)` tối đa 3 byte. Vì vậy header 4 byte và payload 5 byte chắc chắn cần **nhiều lần gọi `read()`** ngay cả nếu mạng đã cung cấp sẵn tất cả dữ liệu. `step` là một `slice` dùng chung nội dung bộ nhớ với `dst` nhưng có vị trí độc lập, nên phải cập nhật `dst.position()` sau mỗi lần đọc.
7. Nếu peer đóng kết nối trước khi gửi đủ header hoặc payload, `readExactly` nhận `-1` và ném `EOFException`; phần message bị thiếu **không** được xử lý như message hoàn chỉnh.
8. Giới hạn `MAX_FRAME_BYTES` được kiểm tra **trước khi cấp phát** buffer payload; điều này ngăn header giả mạo yêu cầu cấp phát tùy ý lớn.
9. `UTF_8.decode(...)` chỉ chạy sau khi đã có đủ payload. Ví dụ dùng dữ liệu ASCII trong UTF-8 nên không gặp ký tự bị chia giữa các lần đọc.

**Ý nghĩa của ví dụ:** Hai message được gửi liền nhau trên **một luồng TCP**, trong khi việc phân chia thành hai message ở bên nhận chỉ dựa trên **header độ dài**. Kích thước các lần đọc không quyết định số message.

## 7. Mẫu tích lũy dữ liệu với `ByteBuffer` trong ứng dụng non-blocking

Ở chế độ non-blocking (`channel.configureBlocking(false)`), `read()` có thể trả về 0 do hiện không có dữ liệu. Không được áp dụng nguyên xi `readExactly` dạng blocking phía trên để **ngồi chờ** một frame; thay vào đó cần giữ trạng thái parse giữa các sự kiện đọc.

Vòng xử lý thường có ý tưởng:

1. Khi `Selector` báo kênh có khả năng đọc, gọi `channel.read(buffer)`; kết quả có thể dương, 0 hoặc -1.
2. Chuyển buffer sang trạng thái đọc bằng `flip()`.
3. Trích xuất **những frame hoàn chỉnh** hiện đã tích đủ. Nếu chưa đủ 4 byte header hoặc chưa đủ payload, giữ lại phần chưa xử lý.
4. Gọi `compact()` để dồn các byte chưa đọc về đầu buffer, tạo chỗ nhận thêm dữ liệu. Khi đã tiêu thụ toàn bộ, `clear()` cũng có thể phù hợp.
5. Chờ sự kiện đọc tiếp theo. Nếu `read() == -1` khi còn frame dang dở, báo lỗi giao thức kết thúc sớm.

Ví dụ vòng đời ByteBuffer:

~~~text
Mới tạo/clear:     position=0, limit=capacity   (chuẩn bị ghi dữ liệu vào)
Đọc socket:        channel.read(buffer)          (position tăng theo byte nhận)
flip:              limit=position, position=0    (chuẩn bị parse)
Parse một phần:    position tăng theo byte đã tiêu thụ
compact:           giữ lại byte chưa parse       (chuẩn bị đọc socket tiếp)
~~~

**Không nhầm `clear()` với xóa dữ liệu bộ nhớ:** `clear()` chỉ đặt lại chỉ số vị trí và giới hạn; nếu còn byte chưa xử lý thì gọi `clear()` có thể khiến chúng bị ghi đè. `compact()` mới phù hợp khi cần giữ lại dữ liệu chưa parse.

### Một lần đọc có thể tạo 0, 1 hoặc nhiều frame

Parser đúng phải xử lý cả ba tình huống:

- **0 frame đầy đủ:** chỉ nhận một phần header hoặc một phần payload; chờ thêm byte.
- **1 frame đầy đủ:** phát ra đúng một message, giữ phần dư nếu có.
- **Nhiều frame đầy đủ:** tiếp tục parse trong buffer hiện có đến khi thiếu dữ liệu cho frame tiếp theo.

Ví dụ, buffer hiện có thể chứa:

~~~text
[length=3][CAT][length=3][DOG][length=5][HE...
~~~

Parser phát ra `CAT` và `DOG`, đồng thời **giữ lại header của frame thứ ba và hai byte `HE`**. Lần đọc tiếp theo bổ sung `LLO` mới cho phép xử lý message `HELLO`.

Khi frame có thể lớn hơn buffer đọc socket, parser phải có trạng thái độc lập: đọc header, xác thực chiều dài, cấp phát/thu thập payload có giới hạn, rồi xử lý. Không giả định một buffer socket cố định phải đủ chứa mọi frame.

### Gửi non-blocking cũng có trạng thái dở dang

Nếu `channel.write(outgoing)` chỉ ghi 7 trong 20 byte, **giữ nguyên buffer với 13 byte còn lại**. Khi khả năng ghi sẵn sàng, tiếp tục từ `position` hiện tại. Nếu trả 0, đăng ký quan tâm `SelectionKey.OP_WRITE` khi còn dữ liệu chờ, và vô hiệu hóa quan tâm ghi khi hàng đợi đã hết để tránh vòng lặp sự kiện ghi không cần thiết.

Phải định nghĩa chính sách **backpressure**: giới hạn hàng đợi gửi, tạm ngừng đọc thêm đầu vào hoặc từ chối yêu cầu khi peer đọc quá chậm. TCP không tự quyết định giới hạn bộ nhớ cho queue thông điệp của ứng dụng.

## 8. UTF-8 và ranh giới bản tin không phải ranh giới ký tự

Một ký tự UTF-8 có thể chiếm 1–4 byte. Giả sử ký tự `Đ` được mã hóa thành nhiều byte; nếu một lần `read()` nhận byte đầu, lần sau nhận byte còn lại, giải mã từng chunk độc lập có thể tạo ký tự lỗi hoặc ký tự thay thế.

**Quy trình an toàn cho giao thức length-prefix:**

1. Đếm độ dài payload theo **byte UTF-8** (`text.getBytes(StandardCharsets.UTF_8).length`), không theo `String.length()`.
2. Gửi header là số **byte**, sau đó gửi đúng byte của payload.
3. Bên nhận thu đủ byte trước khi giải mã toàn bộ payload, hoặc dùng `CharsetDecoder` giữ trạng thái qua nhiều chunk.
4. Chỉ xử lý message sau khi nội dung hợp lệ theo schema.

Ví dụ chuỗi `"Xin chào"` có số byte UTF-8 **lớn hơn** số ký tự mà người đọc đếm. Nếu header lấy `text.length()` thay vì `encoded.length`, phía nhận sẽ cắt ngang payload, làm hỏng framing cho cả các message tiếp theo.

`ByteBuffer.order(ByteOrder.BIG_ENDIAN)` hoặc mặc định big-endian ảnh hưởng cách đọc số nguyên header. Endian của header **khác** với encoding UTF-8 của body; cần định nghĩa rõ cả hai.

Khi dữ liệu đến từ bên không tin cậy, `StandardCharsets.UTF_8.decode` có thể thay thế chuỗi byte UTF-8 sai định dạng theo chính sách mặc định. Nếu yêu cầu từ chối dữ liệu sai, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` và bắt lỗi giải mã, không âm thầm nhận thông điệp bị lỗi.

## 9. EOF, half-close, đóng kết nối và timeout

### `read() == -1` nghĩa là gì?

`-1` báo rằng **đầu vào từ phía peer đã kết thúc** và không còn byte dữ liệu để nhận tiếp trên chiều đó. Đối với giao thức length-prefix:

- Nếu đã đọc đủ một frame rồi sau đó nhận `-1` đúng ở vị trí bắt đầu frame mới, có thể coi đây là kết thúc luồng hợp lệ **nếu giao thức cho phép đóng tại ranh giới frame**.
- Nếu mới đọc 2/4 byte header hoặc 7/10 byte payload, `-1` là **frame bị cắt cụt**, phải báo lỗi.
- Nếu giao thức yêu cầu các frame bắt buộc hoặc số lượng frame cụ thể, đóng ở ranh giới vẫn có thể là lỗi nghiệp vụ.

TCP còn hỗ trợ **half-close**: phía gửi có thể kết thúc chiều gửi bằng `SocketChannel.shutdownOutput()` nhưng vẫn đọc phản hồi theo chiều ngược lại. Vì vậy, EOF của chiều nhận không nhất thiết có nghĩa cả hai phía đã đóng hoàn toàn cùng lúc.

### Không dùng khoảng im lặng để kết luận hết message

Nếu server chưa nhận thêm byte trong 50 ms, điều đó **không chứng minh** frame đã kết thúc. Độ trễ mạng, scheduling, congestion hoặc tải của peer đều có thể khiến dữ liệu đến sau.

**Timeout** là công cụ xử lý kết nối chậm/bị treo theo chính sách vận hành; nó **không phải message delimiter**. Nếu hết timeout giữa frame, quyết định hủy frame/kết nối hoặc retry theo giao thức cụ thể.

### Một lần `write()` thành công không phải xác nhận xử lý

Việc Java trả về đã ghi N byte thường chỉ có nghĩa channel đã chấp nhận N byte ở phía gửi. Nếu cần biết peer đã **xử lý nghiệp vụ thành công**, giao thức phải có ACK/response với định danh request. TCP cũng không tự bảo đảm “exactly once” cho thông điệp qua các lần ngắt và kết nối lại; nếu client retry, server cần logic idempotency/deduplication khi nghiệp vụ yêu cầu.

## 10. Các kiểm tra bảo mật và độ bền của frame

Giao thức framing triển khai không đúng dễ thành điểm yếu của server:

| Nguy cơ | Ví dụ | Cách kiểm soát |
| --- | --- | --- |
| Header độ dài giả mạo | Peer gửi length `2_000_000_000` | Giới hạn `MAX_FRAME_BYTES` trước khi cấp phát |
| Header số âm | `getInt()` trả về `-1` | Từ chối giá trị âm và trường hợp vượt giới hạn |
| Gửi dở frame rồi giữ kết nối | Mới có 1/4 byte header | Timeout, quota kết nối, giới hạn thời gian nhận |
| Dòng delimiter dài vô tận | Peer không gửi `\n` | Giới hạn độ dài message và cắt kết nối vi phạm |
| Giải mã sớm | Chunk chứa nửa ký tự UTF-8 | Ghép đủ byte hoặc dùng decoder có trạng thái |
| Tích lũy không giới hạn | Nhiều frame đến nhanh hơn tốc độ xử lý | Backpressure, queue bounded, giới hạn frame đang chờ |
| Nhiều request trên một kết nối | Payload nối liên tiếp | Parser xử lý nhiều frame và lưu phần dư |
| Peer ngắt giữa frame | `read() == -1` khi còn thiếu payload | Phát hiện truncated frame, không xử lý dữ liệu thiếu |
| Client gửi mãi mà không nhận | `write()` trả 0 liên tục trong non-blocking | Chờ `OP_WRITE`, quản lý timeout và queue |
| Tin rằng đã ghi là peer hoàn tất | Mất kết nối sau `write` | Xác nhận tầng ứng dụng, request ID/idempotency khi cần |

### Giới hạn kích thước trước khi tạo đối tượng

Nếu header là `int`, kiểm tra ngay:

~~~java
int length = header.getInt();
if (length < 0 || length > MAX_FRAME_BYTES) {
    throw new IOException("Invalid length: " + length);
}
ByteBuffer payload = ByteBuffer.allocate(length);
~~~

Đây là **đoạn minh họa**, cần `header` đã đủ 4 byte và đang ở chế độ đọc, `MAX_FRAME_BYTES` là giới hạn cấu hình hợp lệ, import `ByteBuffer` và `IOException`. Trên đường đọc nhiều frame, cũng cần giới hạn **tổng** bộ nhớ và số lượng kết nối, không chỉ từng frame riêng lẻ.

## 11. Các lỗi phổ biến khi lập trình Java NIO mạng

**Lỗi 1 — Một lần đọc là một message.**

~~~java
int n = channel.read(buffer);
// Sai: xử lý ngay n byte như một message hoàn chỉnh.
~~~

`n` là số byte nhận trong lần đọc, không phải độ dài bản tin. Hãy parser theo giao thức framing.

**Lỗi 2 — Một lần ghi chắc chắn gửi hết.**

~~~java
channel.write(buffer);
// Sai: bỏ qua buffer.hasRemaining() và phần chưa ghi.
~~~

Phải giữ buffer và ghi tiếp; với non-blocking, đợi khi writable.

**Lỗi 3 — Không giữ header/payload dở dang.** Chỉ đọc được 2 byte trong header 4 byte rồi bỏ đi sẽ khiến 2 byte tiếp theo bị diễn giải thành đầu một header mới sai lệch.

**Lỗi 4 — Chỉ parse một frame khi buffer chứa nhiều frame.** Dẫn đến độ trễ không cần thiết hoặc mất byte thừa nếu buffer bị `clear()` trước khi xử lý phần dư.

**Lỗi 5 — Dùng `read() == 0` làm EOF.** `0` là không có byte trong lần đọc; `-1` mới là EOF. Đối với non-blocking, cách xử lý `0` là chờ sự kiện thích hợp.

**Lỗi 6 — Dùng `String.length()` làm số byte UTF-8.** Dễ cắt ngang ký tự nhiều byte và làm lệch cả luồng frame kế tiếp.

**Lỗi 7 — Bỏ qua giới hạn frame.** Peer có thể gửi header yêu cầu cấp phát khổng lồ, gây quá tải hoặc hết bộ nhớ.

**Lỗi 8 — Gọi `clear()` khi vẫn còn byte chưa parse.** Buffer mất thông tin về phần dư; `compact()` phù hợp hơn nếu còn dữ liệu phải giữ lại.

**Lỗi 9 — Dựa vào TCP_NODELAY hoặc quy mô packet để tạo ranh giới.** `TCP_NODELAY` ảnh hưởng một số hành vi gom byte/latenсy, **không biến TCP thành message-oriented transport**. Framing vẫn bắt buộc.

**Lỗi 10 — Cho rằng EOF luôn là kết thúc hợp lệ của frame.** Nếu header đã hứa 100 byte mà mới nhận 60, đây là truncated message và cần báo lỗi.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Client gọi `write("HELLO")` rồi `write("JAVA")`. Server gọi `read()` một lần nhận được `"HELLOJAVA"` có đúng không?

**Đáp án:** Có. TCP là byte stream; hai lần ghi có thể xuất hiện chung trong một lần đọc.

**Câu 2.** Một `read()` trả về 3 byte của header dài 4 byte. Bên nhận nên làm gì?

**Đáp án:** Giữ 3 byte đã nhận, đọc thêm 1 byte để đủ header, rồi mới giải mã length. Không xử lý 3 byte đó thành một message.

**Câu 3.** Header yêu cầu payload 30 byte, nhưng lần đọc đầu chỉ nhận 8 byte. Có phải dữ liệu bị lỗi?

**Đáp án:** Chưa. Đây là tình huống đọc từng phần bình thường; tiếp tục tích lũy 22 byte còn lại. Nếu peer đóng trước khi đủ thì mới kết luận frame bị cắt cụt.

**Câu 4.** `read()` trả về 0 trên `SocketChannel` non-blocking. Có được đóng kết nối vì EOF không?

**Đáp án:** Không. `0` chỉ có nghĩa lần gọi chưa đọc được byte; thường cần đợi `Selector` báo sẵn sàng đọc.

**Câu 5.** `write()` của buffer 1.024 byte trả về 600. Cần gửi bao nhiêu byte tiếp theo?

**Đáp án:** Còn 424 byte chưa ghi. `ByteBuffer.position()` đã tăng theo lượng ghi, nên tiếp tục `write` với **chính buffer đó** khi channel cho phép.

**Câu 6.** Có thể gửi UTF-8 `"Xin chào"` với header bằng `String.length()` không?

**Đáp án:** Không nếu header là số byte payload; phải mã hóa UTF-8 rồi dùng `encoded.length`.

**Câu 7.** Khi đã nhận đủ 2 frame và còn 2 byte đầu header frame thứ ba trong buffer, có thể gọi `clear()` không?

**Đáp án:** Không nên vì sẽ bỏ mất dữ liệu header còn dở. Giữ phần dư bằng `compact()` hoặc cơ chế buffer tương đương.

**Câu 8.** Nếu ứng dụng cần phân biệt các lệnh ngay trong một kết nối TCP lâu dài, có thể dùng EOF để ngăn cách chúng không?

**Đáp án:** Không. EOF chỉ báo kết thúc chiều gửi; dùng length-prefix, delimiter có quy tắc, hoặc fixed-size framing để phân biệt nhiều lệnh.

## 13. Ghi nhớ

- **TCP = byte stream có thứ tự**, **không có ranh giới message do TCP bảo toàn**.
- **`write()` không tương ứng 1:1 với `read()`**. Một message có thể đi qua nhiều lần đọc; một lần đọc có thể chứa nhiều message.
- **Framing là trách nhiệm của giao thức ứng dụng**: length-prefix, delimiter hoặc fixed-size; không đoán bằng packet, buffer hay thời gian.
- Đọc/ghi Java NIO phải xét **số byte thực tế**; `read() == -1` là EOF, `0` không phải EOF; non-blocking phải giữ trạng thái và đợi readiness.
- Dùng `flip()`/`compact()` đúng, giữ phần dữ liệu dở dang, kiểm tra độ dài trước khi cấp phát, và chỉ giải mã UTF-8 sau khi đã xử lý đúng ranh giới byte.
