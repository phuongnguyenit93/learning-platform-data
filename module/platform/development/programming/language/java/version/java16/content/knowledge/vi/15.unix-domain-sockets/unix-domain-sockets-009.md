# Đọc ghi byte stream và thiết kế ranh giới thông điệp

## 1. Unix-domain socket cung cấp byte stream

Unix-domain socket cho phép các tiến trình trên cùng một máy giao tiếp qua socket gắn với địa chỉ trong hệ thống tệp. Từ Java 16, Java NIO cung cấp API chuẩn để tạo địa chỉ và mở socket theo giao thức UNIX thông qua JEP 380.

Các lớp thường dùng:

- `UnixDomainSocketAddress` biểu diễn địa chỉ socket từ một `Path`.
- `ServerSocketChannel` lắng nghe kết nối đến.
- `SocketChannel` đại diện kết nối hai chiều để đọc và ghi dữ liệu.
- `StandardProtocolFamily.UNIX` chọn họ giao thức Unix-domain.

Ví dụ tạo địa chỉ:

~~~java
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));
~~~

Khi kết nối đã được thiết lập, `SocketChannel` cung cấp luồng byte hai chiều. Ứng dụng có thể đọc và ghi byte bằng `ByteBuffer` tương tự cách làm với socket stream khác.

Điểm quan trọng: byte stream không giữ ranh giới message. Nếu sender gọi write một lần để gửi một message, receiver có thể nhận dữ liệu qua nhiều lần read; ngược lại, một lần read có thể nhận dữ liệu thuộc nhiều lần write. Vì vậy, ứng dụng phải tự định nghĩa cách nhận biết điểm kết thúc của từng message.

Mục tiêu bài học:

- Mở và sử dụng Unix-domain socket bằng Java NIO.
- Hiểu sự khác nhau giữa byte stream và message.
- Nhận biết partial read và partial write.
- Thiết kế framing để phân tách các message.
- Dùng length-prefix, delimiter hoặc fixed-size message đúng trường hợp.
- Xử lý EOF, message bị cắt cụt và kích thước không hợp lệ.
- Xây dựng giao thức đọc ghi có giới hạn kích thước và xử lý trạng thái buffer chính xác.

## 2. Mở kết nối Unix-domain socket

Server tạo `ServerSocketChannel` với họ giao thức UNIX, bind vào một địa chỉ rồi chờ client:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

class UnixServer {
    public static void main(String[] args) throws IOException {
        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));

        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(address);

            try (SocketChannel client = server.accept()) {
                // Đọc và ghi dữ liệu với client.
            }
        }
    }
}
~~~

Client mở `SocketChannel` cùng họ giao thức và kết nối đến địa chỉ:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

class UnixClient {
    public static void main(String[] args) throws IOException {
        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(Path.of("/tmp/orders.sock"));

        try (SocketChannel channel =
                 SocketChannel.open(StandardProtocolFamily.UNIX)) {
            channel.connect(address);

            // Gửi request và đọc response.
        }
    }
}
~~~

Một số lưu ý khi triển khai:

- Đường dẫn socket phải phù hợp với hệ điều hành và quyền truy cập của tiến trình.
- Họ giao thức UNIX chỉ hoạt động trên nền tảng hỗ trợ Unix-domain socket; nếu không được hỗ trợ, thao tác mở hoặc bind có thể thất bại.
- Đường dẫn socket có thể còn lại sau khi server dừng bất thường. Chỉ xóa file socket cũ khi đã xác nhận không còn server đang sử dụng nó.
- Unix-domain socket giao tiếp giữa các tiến trình trên cùng máy; nó không dùng địa chỉ IP hoặc port TCP.
- Ví dụ mặc định dùng channel ở chế độ blocking. Nếu chuyển sang non-blocking, logic đọc ghi phải xử lý trường hợp thao tác trả về `0` và cần chờ readiness qua `Selector`.

## 3. Vì sao byte stream không có ranh giới message?

Giả sử client gửi hai message liên tiếp:

~~~text
WRITE A: HELLO
WRITE B: WORLD
~~~

Server có thể nhận dữ liệu theo nhiều cách:

~~~text
READ 1: HEL
READ 2: LOWO
READ 3: RLD
~~~

Hoặc:

~~~text
READ 1: HELLOWORLD
~~~

Cả hai cách đều hợp lệ với byte stream. Lệnh `write()` của sender không tương ứng một-một với lệnh `read()` của receiver.

Do đó, không được viết code giả định:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
channel.read(buffer);

// Sai về mặt giao thức nếu coi một lần read là một message hoàn chỉnh.
processMessage(buffer);
~~~

Lần read có thể nhận ít hơn message, nhận đúng một message hoặc nhận nhiều message ghép lại. Ứng dụng cần một quy tắc framing để xác định:

- Message bắt đầu ở đâu.
- Message kết thúc ở đâu.
- Message có kích thước bao nhiêu.
- Dữ liệu hiện có đã đủ để xử lý hay cần đọc tiếp.

Framing là một phần của giao thức ứng dụng, không tự được cung cấp bởi Unix-domain stream socket.

## 4. Ba cách thiết kế ranh giới thông điệp

Có ba cách phổ biến để phân tách message trong byte stream:

| Cách framing | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Fixed-size | Mọi message có kích thước cố định đã biết trước. | Bản ghi nhị phân có cấu trúc cố định. |
| Delimiter-based | Dùng byte hoặc chuỗi ký tự đánh dấu kết thúc. | Dòng văn bản, giao thức line-oriented. |
| Length-prefixed | Gửi trường độ dài trước payload. | Message nhị phân hoặc văn bản có kích thước thay đổi. |

### Fixed-size message

Nếu mỗi bản tin luôn có đúng 32 byte, receiver chỉ cần tích lũy đủ 32 byte rồi xử lý. Cách này đơn giản nhưng kém linh hoạt khi dữ liệu có độ dài thay đổi.

### Delimiter-based message

Một giao thức dòng lệnh có thể kết thúc mỗi message bằng byte newline (`\n`). Receiver tích lũy byte cho đến khi tìm thấy delimiter. Nếu payload có thể chứa delimiter, giao thức cần escaping hoặc một encoding bảo đảm delimiter không xuất hiện như dữ liệu thông thường.

### Length-prefixed message

Sender gửi độ dài payload trước, sau đó gửi đúng số byte đã khai báo:

~~~text
+----------------------+----------------------+
| Payload length (N)   | Payload (N bytes)    |
+----------------------+----------------------+
~~~

Receiver đọc đủ header, giải mã độ dài, kiểm tra giới hạn, rồi đọc đủ payload. Đây là cách phù hợp cho ví dụ trong bài vì ranh giới message rõ ràng và payload có thể chứa bất kỳ byte nào.

## 5. Thiết kế length-prefix an toàn

Một giao thức đơn giản có thể dùng header 4 byte chứa số byte payload dưới dạng signed `int`, theo byte order big-endian mặc định của `ByteBuffer`.

~~~text
Header: 4 bytes, integer N
Body:   N bytes
~~~

Ví dụ message văn bản `"Xin chao"` được mã hóa UTF-8:

1. Chuyển chuỗi thành byte bằng `StandardCharsets.UTF_8`.
2. Tính độ dài từ `byte[].length`, không dùng `String.length()`.
3. Gửi header chứa độ dài byte.
4. Gửi payload.
5. Receiver đọc header, xác thực `0 <= N <= MAX_MESSAGE_BYTES`.
6. Receiver đọc chính xác N byte rồi mới giải mã hoặc xử lý.

Giới hạn kích thước là bắt buộc khi độ dài đến từ peer. Không cấp phát buffer theo một giá trị chưa xác thực, vì peer có thể gửi một số rất lớn nhằm làm ứng dụng cấp phát quá nhiều bộ nhớ.

Ví dụ chọn giới hạn 1 MiB:

~~~java
private static final int MAX_MESSAGE_BYTES = 1024 * 1024;
~~~

Đây là chính sách của giao thức mẫu, không phải giới hạn cố định của Java hoặc Unix-domain socket. Ứng dụng nên chọn giới hạn phù hợp với dữ liệu và ngân sách bộ nhớ.

## 6. Đọc đủ byte: xử lý partial read

`SocketChannel.read(ByteBuffer)` đọc tối đa số byte còn có thể ghi vào buffer. Một lần gọi có thể đọc ít hơn số byte được yêu cầu.

Với channel ở chế độ blocking, có thể lặp đến khi buffer đầy:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;

static void readFully(SocketChannel channel, ByteBuffer target)
        throws IOException {
    while (target.hasRemaining()) {
        int count = channel.read(target);

        if (count < 0) {
            throw new EOFException("Peer closed before frame was complete");
        }
    }
}
~~~

Ý nghĩa:

- `target.hasRemaining()` cho biết vẫn còn byte cần nhận.
- Mỗi lần `read()` cập nhật position của buffer.
- Khi position đạt limit, buffer đã nhận đủ số byte yêu cầu.
- Giá trị `-1` báo peer đã đóng đầu ra; nếu frame chưa đủ, đó là dữ liệu bị cắt cụt.

Helper này giả định channel ở chế độ blocking. Với non-blocking channel, `read()` có thể trả về `0`; khi đó không được lặp bận liên tục mà cần chờ sự kiện đọc bằng `Selector` rồi tiếp tục.

### Đọc header và payload là hai giai đoạn riêng

Header luôn có 4 byte. Sau khi đọc đủ header, cần gọi `flip()` để chuyển buffer sang chế độ đọc:

~~~java
ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
readFully(channel, header);

header.flip();
int payloadLength = header.getInt();
~~~

Sau khi lấy độ dài, kiểm tra nó trước khi cấp phát payload:

~~~java
if (payloadLength < 0 || payloadLength > MAX_MESSAGE_BYTES) {
    throw new IOException("Invalid frame length: " + payloadLength);
}

ByteBuffer payload = ByteBuffer.allocate(payloadLength);
readFully(channel, payload);
payload.flip();
~~~

`payload.flip()` đặt limit về số byte đã đọc và position về 0, để code sau có thể đọc payload.

## 7. Ghi đủ byte: xử lý partial write

Tương tự read, `SocketChannel.write(ByteBuffer)` có thể ghi ít byte hơn số byte còn lại trong buffer. Không giả định một lần write gửi hết payload.

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;

static void writeFully(SocketChannel channel, ByteBuffer source)
        throws IOException {
    while (source.hasRemaining()) {
        channel.write(source);
    }
}
~~~

Mỗi lần write thành công cập nhật position của `source`. Vòng lặp kết thúc khi toàn bộ byte đã được ghi.

Helper này cũng giả định channel ở chế độ blocking. Với non-blocking channel, khi write trả về `0`, cần giữ nguyên buffer còn dữ liệu và chờ channel sẵn sàng ghi trước khi thử lại.

## 8. Cài đặt helper gửi và nhận một frame

Ghép header và payload thành một buffer duy nhất để gửi:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;

static final int MAX_MESSAGE_BYTES = 1024 * 1024;

static void writeFrame(SocketChannel channel, byte[] payload)
        throws IOException {
    if (payload.length > MAX_MESSAGE_BYTES) {
        throw new IllegalArgumentException("Message is too large");
    }

    ByteBuffer frame = ByteBuffer.allocate(
        Integer.BYTES + payload.length
    );

    frame.putInt(payload.length);
    frame.put(payload);
    frame.flip();

    writeFully(channel, frame);
}

static byte[] readFrame(SocketChannel channel) throws IOException {
    ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
    readFully(channel, header);

    header.flip();
    int length = header.getInt();

    if (length < 0 || length > MAX_MESSAGE_BYTES) {
        throw new IOException("Invalid frame length: " + length);
    }

    ByteBuffer payload = ByteBuffer.allocate(length);
    readFully(channel, payload);

    return payload.array();
}
~~~

Một số điểm cần hiểu:

- `Integer.BYTES` là 4.
- `putInt()` và `getInt()` dùng byte order big-endian mặc định của `ByteBuffer`.
- `writeFully()` bảo đảm toàn bộ frame được gửi trong chế độ blocking.
- `readFully()` bảo đảm đủ header và payload trước khi trả về.
- `readFrame()` từ chối độ dài âm hoặc lớn hơn giới hạn.
- Payload có độ dài 0 vẫn là một frame hợp lệ nếu giao thức cho phép message rỗng.

Nếu giao thức được dùng bởi nhiều ngôn ngữ hoặc nhiều hệ thống, hãy tài liệu hóa byte order, độ dài header, giới hạn payload, encoding và ý nghĩa của từng message type.

## 9. Ví dụ client/server trao đổi message UTF-8

Sau khi có `readFrame`, `writeFrame`, `readFully` và `writeFully`, có thể trao đổi message văn bản. Mã hóa chuỗi thành byte trước khi đóng khung:

~~~java
byte[] request = "Xin chao server".getBytes(StandardCharsets.UTF_8);
writeFrame(channel, request);

byte[] response = readFrame(channel);
String text = new String(response, StandardCharsets.UTF_8);
System.out.println(text);
~~~

Ví dụ server xử lý một request rồi trả response:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

class EchoServer {
    public static void main(String[] args) throws IOException {
        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(Path.of("/tmp/echo.sock"));

        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(address);

            try (SocketChannel client = server.accept()) {
                byte[] request = readFrame(client);
                String message =
                    new String(request, StandardCharsets.UTF_8);

                byte[] response =
                    ("Echo: " + message).getBytes(StandardCharsets.UTF_8);

                writeFrame(client, response);
            }
        }
    }

    // Đặt các helper readFrame, writeFrame, readFully, writeFully
    // trong class hoặc một utility class dùng chung.
}
~~~

Client:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

class EchoClient {
    public static void main(String[] args) throws IOException {
        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(Path.of("/tmp/echo.sock"));

        try (SocketChannel channel =
                 SocketChannel.open(StandardProtocolFamily.UNIX)) {
            channel.connect(address);

            byte[] request =
                "Xin chao server".getBytes(StandardCharsets.UTF_8);

            writeFrame(channel, request);

            byte[] response = readFrame(channel);
            System.out.println(
                new String(response, StandardCharsets.UTF_8)
            );
        }
    }

    // Dùng cùng định nghĩa helper framing với server.
}
~~~

Hai đoạn trên minh họa phần xử lý kết nối và giao thức. Để chạy thành chương trình độc lập, đặt các helper framing vào một class dùng chung và import hoặc khai báo chúng trong từng class.

Lưu ý: `String.length()` đếm đơn vị UTF-16 code unit, không phải số byte UTF-8. Header phải ghi `payload.length` sau khi mã hóa, không ghi số ký tự của chuỗi.

## 10. Một luồng có thể chứa nhiều frame liên tiếp

Sau khi đọc xong một frame, channel vẫn có thể còn dữ liệu của frame tiếp theo. Vì vậy, server có thể tiếp tục đọc trong vòng lặp cho đến khi peer đóng kết nối:

~~~java
while (true) {
    byte[] request = readFrameOrNull(client);
    if (request == null) {
        break; // EOF ngay tại ranh giới frame: peer đóng kết nối bình thường.
    }

    byte[] response = handle(request);
    writeFrame(client, response);
}
~~~

Trong ví dụ này, `readFrameOrNull` trả về `null` chỉ khi peer đóng kết nối trước khi gửi byte đầu tiên của frame kế tiếp. Nếu peer đóng sau khi đã gửi một phần header hoặc payload, helper ném `EOFException` để báo frame bị cắt cụt. Helper giả định channel ở chế độ blocking, giống các helper đọc ghi phía trên.

Triển khai helper phân biệt EOF sạch với frame chưa hoàn chỉnh:

~~~java
static byte[] readFrameOrNull(SocketChannel channel) throws IOException {
    ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);

    // Đọc byte đầu tiên riêng để phân biệt EOF sạch với header bị cắt cụt.
    int first;
    do {
        first = channel.read(header);
    } while (first == 0);

    if (first < 0) {
        return null; // Chưa nhận byte nào của frame mới.
    }

    // Nếu peer đóng sau byte đầu tiên, readFully ném EOFException.
    readFully(channel, header);
    header.flip();

    int length = header.getInt();
    if (length < 0 || length > MAX_MESSAGE_BYTES) {
        throw new IOException("Invalid frame length: " + length);
    }

    ByteBuffer payload = ByteBuffer.allocate(length);
    readFully(channel, payload);
    return payload.array();
}
~~~

Không được bỏ qua phần dữ liệu còn lại của frame rồi tiếp tục parse byte tiếp theo như thể đó là đầu frame mới; điều đó làm mất đồng bộ giao thức.

## 11. Thiết kế protocol: loại message, version và giới hạn

Length-prefix chỉ xác định độ dài, chưa xác định ý nghĩa của payload. Một giao thức ứng dụng thường cần thêm cấu trúc, chẳng hạn:

~~~text
+---------+---------+------------------+----------------+
| Version | Type    | Payload length   | Payload        |
+---------+---------+------------------+----------------+
| 1 byte  | 1 byte  | 4 bytes          | N bytes        |
+---------+---------+------------------+----------------+
~~~

Các trường có thể mang ý nghĩa:

- `Version`: phiên bản giao thức để hai bên biết cách diễn giải frame.
- `Type`: loại message như request, response, error hoặc event.
- `Payload length`: số byte payload.
- `Payload`: dữ liệu theo schema của message type.

Khi thiết kế, cần quyết định:

1. Byte order của trường số.
2. Kích thước tối đa của header và payload.
3. Encoding văn bản, thường là UTF-8.
4. Hành vi khi nhận version hoặc message type không hỗ trợ.
5. Cách báo lỗi và kết thúc phiên khi frame không hợp lệ.
6. Timeout hoặc chính sách hủy nếu peer gửi header rồi dừng lâu.
7. Có cho phép nhiều request đồng thời trên cùng connection hay phải tuần tự.
8. Cách serialize việc ghi nếu nhiều thread cùng gửi message.

Giới hạn payload bảo vệ bộ nhớ. Timeout và giới hạn tốc độ giúp tránh giữ connection vô thời hạn khi peer gửi dữ liệu quá chậm. Với nhiều writer, cần khóa hoặc một hàng đợi ghi để header và payload của hai frame không bị xen kẽ byte.

## 12. Buffer state khi đọc ghi stream

`ByteBuffer` dùng ba thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity` | Dung lượng được cấp phát, không đổi sau khi tạo. |
| `limit` | Biên mà thao tác đọc/ghi hiện tại không vượt qua. |
| `position` | Vị trí thao tác tiếp theo. |

Các thao tác thường gặp:

- `put(...)` ghi byte và tăng position.
- `get(...)` đọc byte và tăng position.
- `flip()` chuyển từ ghi sang đọc: limit nhận position cũ, position về 0.
- `clear()` đặt position về 0 và limit về capacity; không xóa byte cũ.
- `compact()` giữ phần byte chưa đọc, dồn chúng về đầu buffer rồi chuyển về chế độ ghi tiếp.

Khi đọc stream theo từng đợt vào một buffer dùng lại, `compact()` hữu ích nếu cuối buffer còn một phần header hoặc payload chưa đủ. Các byte chưa xử lý được giữ lại để ghép với dữ liệu nhận ở lần read sau.

Ví dụ mô hình tích lũy:

~~~java
ByteBuffer input = ByteBuffer.allocate(8192);

while (channel.read(input) >= 0) {
    input.flip();

    // parseAvailable(input) chỉ tiêu thụ những frame đã đủ.
    parseAvailable(input);

    // Giữ lại các byte chưa đủ thành frame.
    input.compact();
}
~~~

`parseAvailable()` phải cập nhật position đúng bằng số byte đã tiêu thụ. Nếu chưa đủ header hoặc payload, nó phải dừng mà không bỏ các byte còn thiếu. Ví dụ trên là mô hình cho parser tăng dần; cần xử lý riêng EOF và trường hợp buffer đầy nhưng parser vẫn không thể tiến triển, ví dụ frame lớn hơn dung lượng buffer.

Với giao thức có payload lớn hơn buffer làm việc, nên đọc header trước, xác thực length rồi xử lý payload theo từng chunk hoặc cấp phát buffer có giới hạn phù hợp. Không để một frame tùy ý làm buffer tăng vô hạn.

## 13. Lỗi thường gặp và cách khắc phục

1. **Coi một lần `read()` là một message:** stream không giữ ranh giới message; phải dùng framing.
2. **Coi một lần `write()` gửi toàn bộ byte:** write có thể ghi một phần; lặp khi buffer còn dữ liệu.
3. **Không xử lý EOF:** peer có thể đóng giữa header hoặc payload; xem đó là frame bị cắt cụt.
4. **Cấp phát theo length chưa xác thực:** kiểm tra length âm và giới hạn tối đa trước khi allocate.
5. **Dùng `String.length()` làm số byte:** mã hóa UTF-8 trước rồi lấy `byte[].length`.
6. **Quên `flip()` trước khi đọc header hoặc payload:** sau khi ghi vào buffer, phải chuyển sang chế độ đọc.
7. **Nhầm `clear()` với xóa nội dung:** clear chỉ đặt lại position và limit, không ghi zero vào buffer.
8. **Không đồng bộ nhiều writer:** frame có thể bị xen kẽ; serialize toàn bộ header và payload của mỗi frame.
9. **Dùng helper blocking cho channel non-blocking:** phải xử lý `read()`/`write()` trả về 0 và tích hợp Selector.
10. **Bỏ qua phần frame còn thiếu:** parser phải giữ lại byte chưa tiêu thụ để tiếp tục khi có dữ liệu mới.
11. **Không quản lý file socket:** đường dẫn cũ có thể khiến bind thất bại; chỉ dọn file đã xác định là stale.
12. **Cho rằng Unix-domain socket là TCP trên localhost:** đây là họ địa chỉ và cơ chế IPC riêng, không dùng IP/port.

## 14. Bài tập thực hành

1. Tạo một Unix-domain server và client bằng `ServerSocketChannel` và `SocketChannel` với `StandardProtocolFamily.UNIX`.
2. Gửi chuỗi UTF-8 qua socket. Tính header bằng số byte sau mã hóa và giải thích vì sao không dùng `String.length()`.
3. Viết `readFully()` để đọc đủ 4 byte header dù dữ liệu đến thành nhiều lần read.
4. Viết `writeFully()` để xử lý trường hợp write chưa tiêu thụ hết buffer.
5. Cài đặt length-prefix 4 byte big-endian và giới hạn payload tối đa 1 MiB.
6. Gửi hai frame liên tiếp trong cùng connection. Chứng minh receiver không phụ thuộc vào ranh giới giữa các lần read.
7. Thử đóng client giữa header hoặc payload và xử lý frame bị cắt cụt.
8. Tạo buffer parser dùng `compact()` để giữ byte chưa đủ thành một frame.
9. Mở hai writer trên cùng connection và thiết kế cơ chế serialize frame để tránh byte bị xen kẽ.
10. So sánh fixed-size, delimiter-based và length-prefixed framing cho một giao thức nội bộ.

## Ghi nhớ

Unix-domain socket trong Java NIO cung cấp kết nối byte stream giữa các tiến trình trên cùng máy. Stream không bảo toàn ranh giới của các lần write, nên receiver không được coi một lần read là một message. Giao thức phải tự định nghĩa framing, chẳng hạn fixed-size, delimiter hoặc length-prefix. Với length-prefix, hãy đọc đủ header, xác thực độ dài và giới hạn payload trước khi cấp phát, rồi đọc đủ body. Cả read và write đều có thể xử lý ít byte hơn yêu cầu; dùng vòng lặp cho blocking channel và dùng Selector/state machine cho non-blocking channel. Quản lý đúng `position`, `limit`, `flip()` và `compact()` để không làm mất byte chưa xử lý. Những nguyên tắc này áp dụng cho Unix-domain socket và các byte stream khác trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [JEP 380 – Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [Java 16 API – UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [Java 16 API – SocketChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java 16 API – ServerSocketChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java 16 API – ByteBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 16 API – StandardProtocolFamily](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/StandardProtocolFamily.html)
