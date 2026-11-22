# Vì sao một lần write không tương ứng với một lần read?

## 1. Vấn đề cốt lõi: TCP truyền luồng byte, không truyền “lần gọi hàm”

Hãy tưởng tượng client Java ghi một thông điệp:

~~~java
byte[] data = "HELLO".getBytes(StandardCharsets.UTF_8);
socket.getOutputStream().write(data); // Một lần gọi write(...)
~~~

Bên server có thể nhận bằng **một lần read() đủ 5 byte**, nhưng cũng có thể cần **nhiều lần read()** mới nhận đủ. Ngược lại, hai lần write(...) liên tiếp ở client có thể được server lấy ra trong **một lần read()** nếu buffer và thời điểm đọc cho phép.

Đây là hành vi **bình thường, đúng chuẩn TCP**, không phải TCP làm thất lạc hoặc nhân đôi thông điệp.

**Nguyên tắc phải nhớ: TCP là một byte stream có thứ tự. TCP không lưu và không truyền ranh giới giữa các lần gọi write() của ứng dụng.**

~~~text
Client Java                                      Server Java

write("ABC") --\
                \                              /--> read(...) = "AB"
write("DEF") ---->  DÒNG BYTE: A B C D E F  --<
                                               \--> read(...) = "CDEF"

Một cách phân chia khác cũng hợp lệ:

write("ABC") --\
                \                              /--> read(...) = "ABCDEF"
write("DEF") ---->  DÒNG BYTE: A B C D E F  --<
~~~

Hai sơ đồ mô tả **các kết quả có thể xảy ra**, không phải lịch chạy có thể ép TCP tái hiện bằng cách sleep vài mili-giây. Nếu ứng dụng cần nhận các thông điệp “ABC” và “DEF” riêng biệt, **chính giao thức ứng dụng phải đánh dấu ranh giới thông điệp**.

Câu nói chính xác hơn là:

> Một lần write() biểu diễn một thao tác gửi byte ở phía ứng dụng. Một lần read() biểu diễn một thao tác lấy một số byte hiện có (hoặc chờ byte) ở phía nhận. Không tồn tại cam kết một-một giữa hai thao tác đó.

## 2. Tách ba loại ranh giới thường bị nhầm

Có ít nhất ba loại ranh giới khác nhau:

| Ranh giới | Ai xác định? | Bên nhận có được bảo toàn không? |
| --- | --- | --- |
| **Lần gọi write(...)** của ứng dụng | Code sender | **Không**: TCP không chuyển nó thành “record” |
| **TCP segment / IP packet** | Ngăn xếp TCP/IP, mạng và thiết bị | **Không**: read() không phải API đọc từng segment |
| **Thông điệp ứng dụng (application message)** | Giao thức do ứng dụng hoặc chuẩn như HTTP quy định | **Chỉ có** nếu ứng dụng có cách đóng khung và giải mã |

Một thông điệp có thể bị chia qua nhiều segment. Nhiều đoạn dữ liệu ghi gần nhau có thể được TCP đưa vào những segment theo cách không trùng số lần ghi. Khi bên nhận đã có byte trong receive buffer, một lần read có thể lấy dữ liệu xuất phát từ nhiều lần write trước đó.

Ngay cả khi dùng Wireshark thấy “một TCP segment chứa một message” trong vài lần chạy, đó **không phải hợp đồng API**. Những lần chạy khác có thể có segmentation, offload, buffer size và thời điểm scheduling khác.

**TCP bảo đảm những gì khi kết nối còn hoạt động?**

- Các byte được giao cho phía nhận **theo đúng thứ tự của luồng**, không tự hoán đổi ranh giới do ứng dụng tạo.
- TCP có kiểm tra, xác nhận và cơ chế truyền lại để duy trì tính toàn vẹn và truyền byte khi còn có thể.
- TCP không tự biết “đây là một đơn hàng”, “đây là một JSON” hoặc “đây là kết thúc message”.
- Khi kết nối lỗi, ứng dụng vẫn có thể không biết yêu cầu đã được phía kia xử lý đến đâu. Một write() trả về thành công **không phải biên nhận nghiệp vụ**.

TCP cung cấp nền tảng luồng byte đáng tin cậy theo khả năng của giao thức; nó **không cung cấp transaction, exactly-once business processing hay application acknowledgment**.

## 3. Vì sao một write() có thể cần nhiều read()?

### 3.1. Buffer của người nhận có kích thước giới hạn

Ví dụ client ghi 16 byte bằng một lần write:

~~~text
Client: write("HELLO_TCP_STREAM")    // 16 byte UTF-8

Server: byte[] buffer = new byte[4];

read(buffer) <= 4 byte trong mỗi lần gọi
~~~

Dù cả 16 byte đã ở receive buffer, server **không thể** lấy hơn 4 byte trong một lần read(buffer) với buffer 4 byte. Nó phải đọc ít nhất **4 lần có kết quả dương** mới có đủ 16 byte. Nếu dữ liệu đến rời rạc hơn, có thể cần **nhiều hơn 4 lần**.

Đây là cách chứng minh có thể lặp lại mà không phụ thuộc vào việc cố tình làm mạng chậm: **giới hạn buffer do chương trình đặt** đủ để khiến một write bị tiêu thụ bởi nhiều read.

### 3.2. Byte có thể đến không đồng thời

Ngay cả khi buffer của server lớn, lệnh read có thể chạy khi mới có một phần byte. Với socket blocking, **InputStream.read(byte[], off, len)** chờ cho đến khi có dữ liệu, EOF hoặc lỗi; khi dữ liệu đã có, nó **được phép trả ít hơn len**. Không có điều kiện “đợi đến khi đủ toàn bộ message của sender” vì TCP không biết message đó dài bao nhiêu.

Ví dụ client muốn gửi 10.000 byte, server read vào buffer 16 KiB. Bất kỳ kết quả dương nào **không quá 10.000** đều có thể là số byte được đọc, tùy thời điểm dữ liệu có sẵn. Server không được tự kết luận một lần read < 10.000 nghĩa là sender gửi thiếu.

### 3.3. Mạng và hệ điều hành xử lý riêng các byte

Những yếu tố có thể thay đổi số byte từng lần read:

- Phân mảnh luồng thành các TCP segment phù hợp với MSS/MTU và chính sách TCP.
- Bộ đệm gửi/nhận của hệ điều hành, congestion control và flow control.
- Lịch chạy thread, số byte hiện có lúc read được gọi.
- BufferedInputStream, BufferedReader, TLS hoặc lớp framing bên trên có bộ đệm riêng.
- Cách code chọn kích thước buffer hoặc thời gian đọc.

**Không phải tìm một “kích thước gói TCP chuẩn” rồi dùng làm kích thước message.** Segment size và message size phục vụ hai tầng khác nhau.

## 4. Vì sao nhiều write() có thể được một read() đọc chung?

Giả sử sender viết hai lần:

~~~java
OutputStream out = socket.getOutputStream();
out.write("HELLO".getBytes(StandardCharsets.UTF_8));
out.write("WORLD".getBytes(StandardCharsets.UTF_8));
~~~

Receiver có buffer 64 byte và thực hiện read() sau khi các byte đã đến; nó có thể nhận **HELLOWORLD** trong một lần. Nó cũng có thể nhận **HEL**, rồi **LOWORLD**, hoặc cách chia khác vẫn giữ nguyên thứ tự.

Điểm thường gây hiểu nhầm:

- **flush()** trên một BufferedOutputStream/BufferedWriter đẩy dữ liệu đang đệm xuống output stream bên dưới; nó **không tạo ranh giới message trong TCP** và không xác nhận server đã xử lý.
- **Socket.setTcpNoDelay(true)** ảnh hưởng tới thuật toán Nagle; nó không thay đổi TCP thành giao thức có record boundaries.
- **Thread.sleep(...)** giữa hai write có thể làm một lần thử cho kết quả khác nhưng không biến khoảng ngừng thành delimiter đáng tin cậy.
- **Một TCP segment không bắt buộc tương ứng một lần read()**. Có thể đọc một segment qua nhiều read nhỏ hoặc đọc dữ liệu nhiều segment qua một read lớn.

Đối với ứng dụng, câu hỏi “sender đã gọi write bao nhiêu lần?” không phải cách xác định số thông điệp.

## 5. Hợp đồng chính xác của các API đọc/ghi Java

### 5.1. InputStream.read

Với socket blocking:

~~~java
byte[] buf = new byte[1024];
int n = socket.getInputStream().read(buf);
~~~

Kết quả có ý nghĩa:

| n | Ý nghĩa |
| --- | --- |
| **n > 0** | Đã đọc được đúng n byte vào buffer, tối đa 1024; n không phải kích thước message |
| **n == -1** | Đã gặp **end-of-stream** sau khi hết byte có thể đọc; thường do peer đóng nửa gửi/đóng kết nối một cách bình thường |
| **n == 0** | Không phải trạng thái thông thường của một lần đọc blocking với buffer có độ dài dương; đặc biệt có thể xuất hiện khi yêu cầu đọc **0 byte** |

Một read(...) blocking với độ dài dương thường đợi ít nhất một byte, EOF hoặc ngoại lệ. Nó **không tự đọc đủ** độ dài được yêu cầu. Nếu một message cần đúng 4096 byte thì phải lặp hoặc dùng API đọc đủ byte.

**Không làm thế này:**

~~~java
// Minh họa sai: giả định một read là một message.
byte[] buffer = new byte[4096];
int n = in.read(buffer);
String message = new String(buffer, 0, n, StandardCharsets.UTF_8);
process(message);
~~~

Đoạn minh họa còn bỏ qua **n == -1** và có thể giải mã sai khi một ký tự UTF-8 bị cắt giữa hai lần read. Ngay cả khi n dương, dữ liệu có thể chỉ là một phần message hoặc nhiều message đã dính nhau.

### 5.2. readFully và readNBytes

Trong Java 17, có những API hữu ích khi **giao thức đã biết trước số byte phải đọc**:

- **DataInputStream.readFully(byte[])**: cố đọc đủ số byte của mảng; nếu gặp EOF trước khi đủ thì ném **EOFException**.
- **InputStream.readNBytes(int len)**: đọc tối đa len byte, cố lấy đủ khi còn dữ liệu; nếu gặp EOF sớm có thể trả mảng **ngắn hơn len**. Code cần kiểm tra độ dài nếu yêu cầu đúng len.
- **InputStream.readNBytes(byte[], off, len)**: trả số byte thực sự đọc được, có thể nhỏ hơn len nếu đã EOF.
- **InputStream.readAllBytes()**: đọc đến **EOF**; không dùng như “đọc xong một message” khi kết nối giữ mở để trao đổi nhiều message.

API “đọc đủ N byte” là bước thực hiện framing, **không có tác dụng đoán N byte từ TCP**. Ứng dụng phải biết N từ hợp đồng (kích thước cố định, header length, v.v.).

### 5.3. OutputStream.write và SocketChannel.write

Một lần **OutputStream.write(byte[])** trên socket blocking cố chuyển các byte qua luồng output và có thể chặn/lỗi trong lúc thao tác. Khi write() trả về, không được suy ra peer đã đọc, đã parse hay đã xử lý message. Nếu kết nối bị lỗi giữa chừng, ứng dụng có thể không biết phía kia nhận được bao nhiêu.

Với **java.nio.channels.SocketChannel**, phương thức **write(ByteBuffer)** trả về **số byte thực tế đã viết**. Đặc biệt trong chế độ **non-blocking**, có thể viết **ít hơn số byte còn lại**, thậm chí **0**. Vì thế cần kiểm tra **buffer.hasRemaining()**, giữ lại phần chưa gửi và đăng ký chờ khả năng ghi bằng **Selector.OP_WRITE** thay vì busy-spin khi không thể ghi thêm.

Tương tự, **SocketChannel.read(ByteBuffer)** trong non-blocking mode có thể trả **0** nếu lúc đó chưa có byte, trả **-1** khi EOF, hoặc số byte dương; đây vẫn là byte stream không có message boundaries.

## 6. Ví dụ Java 17+ chạy được: một write, nhiều read

Chương trình sau mở hai tiến trình Java trên loopback TCP cổng **5051**. Client ghi payload **HELLO_TCP_STREAM** (16 byte ASCII/UTF-8) bằng **một lần gọi out.write(payload)**. Server chủ động đọc payload vào mảng có kích thước **4 byte**, vì vậy phải gọi read nhiều lần. Mọi kích thước message được gửi qua **length-prefix 4 byte**, tránh phải đoán khi nào đủ.

**Giao thức demo:**

~~~text
Request client -> server:
+----------------------------+------------------------+
| length: 4 byte signed int  | payload: length byte   |
| big-endian (writeInt)      | UTF-8                  |
+----------------------------+------------------------+

Reply server -> client:
+----------------------------+------------------------+
| length: 4 byte signed int  | payload: length byte   |
+----------------------------+------------------------+
~~~

Length-prefix là một phần của **giao thức ứng dụng**; TCP không tự thêm nó. Mốc tối đa 1024 byte cho request và 64 byte cho response chỉ là **giới hạn tự đặt** trong ví dụ này.

### Tệp ChunkedReadServer.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class ChunkedReadServer {
    public static void main(String[] args) throws IOException {
        try (ServerSocket listener = new ServerSocket(
                5051, 50, InetAddress.getLoopbackAddress())) {
            System.out.println("Server ready");

            try (Socket client = listener.accept()) {
                client.setSoTimeout(5000);

                DataInputStream in =
                        new DataInputStream(client.getInputStream());
                DataOutputStream out =
                        new DataOutputStream(client.getOutputStream());

                int length = in.readInt();
                if (length < 0 || length > 1024) {
                    throw new IOException("Invalid frame length: " + length);
                }

                ByteArrayOutputStream assembled =
                        new ByteArrayOutputStream();
                byte[] part = new byte[4];
                int calls = 0;

                while (assembled.size() < length) {
                    int requested = Math.min(
                            part.length, length - assembled.size());
                    int n = in.read(part, 0, requested);

                    if (n == -1) {
                        throw new EOFException("Truncated frame");
                    }
                    if (n == 0) {
                        continue;
                    }

                    assembled.write(part, 0, n);
                    calls++;
                }

                String message =
                        assembled.toString(StandardCharsets.UTF_8);
                System.out.println("Server received: " + message);
                System.out.println("Multiple reads: " + (calls > 1));

                byte[] reply = "ACK".getBytes(StandardCharsets.UTF_8);
                out.writeInt(reply.length);
                out.write(reply);
                out.flush();
            }
        }
    }
}
~~~

### Tệp SingleWriteClient.java

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SingleWriteClient {
    public static void main(String[] args) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 5051), 3000);
            socket.setSoTimeout(5000);

            DataOutputStream out =
                    new DataOutputStream(socket.getOutputStream());
            DataInputStream in =
                    new DataInputStream(socket.getInputStream());

            byte[] payload = "HELLO_TCP_STREAM"
                    .getBytes(StandardCharsets.UTF_8);

            out.writeInt(payload.length); // Header 4 byte
            out.write(payload);            // Đúng một write cho payload
            out.flush();
            System.out.println("Client sent: HELLO_TCP_STREAM");

            int length = in.readInt();
            if (length < 0 || length > 64) {
                throw new IOException("Invalid reply length");
            }
            byte[] response = new byte[length];
            in.readFully(response);        // Đọc đúng length byte

            System.out.println("Client received: " +
                    new String(response, StandardCharsets.UTF_8));
        }
    }
}
~~~

### Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**. Đặt hai tệp trong cùng một thư mục, biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 ChunkedReadServer.java SingleWriteClient.java
~~~

Terminal thứ nhất:

~~~bash
java ChunkedReadServer
~~~

Chờ server in **Server ready**, rồi chạy ở terminal thứ hai:

~~~bash
java SingleWriteClient
~~~

**Stdout mong đợi của server:**

~~~text
Server ready
Server received: HELLO_TCP_STREAM
Multiple reads: true
~~~

**Stdout mong đợi của client:**

~~~text
Client sent: HELLO_TCP_STREAM
Client received: ACK
~~~

Đã kiểm tra logic chương trình bằng Java runtime: kết quả nhận được đúng hai nhóm stdout ở trên.

**Vì sao kết quả Multiple reads: true là xác định?** Chuỗi có đúng **16 byte UTF-8**. Server đọc tối đa **4 byte** cho mỗi lần read payload. Dù mạng gửi liền 16 byte, cần ít nhất **4 lần read trả số dương**. Nếu hệ điều hành phân phối byte thành nhiều phần nhỏ hơn, có thể cần hơn 4 lần; chương trình cố tình chỉ in boolean, không in một số lần read giả định.

**Mục đích của hai thao tác đầu client:**

~~~java
out.writeInt(payload.length); // 4 byte header length
out.write(payload);            // payload gửi trong một write
~~~

Client ghi header và payload là hai thao tác ghi khác nhau, nhưng **payload chỉ có một lời gọi write**. Server đọc header bằng **readInt()**, rồi đọc payload bằng những lần **read(...)** có buffer 4 byte. Cả hai bên biết chính xác ranh giới payload là **16 byte do header công bố**, không dựa vào số lần write hay read.

Server chỉ nhận một kết nối để bài học dễ theo dõi và bind vào **loopback** để chạy trên cùng máy. Nếu gặp **BindException**, cổng 5051 có thể đang được dùng: thay cùng số port trong cả hai chương trình. Nếu client chạy trước server, connect có thể bị từ chối. **setSoTimeout(5000)** giới hạn thời gian chờ đọc socket, không biến thành deadline cho toàn bộ nghiệp vụ.

## 7. Cách giải bài toán thực tế: framing thông điệp

Muốn truyền **nhiều message** trên một TCP connection, hai bên phải thống nhất **cách xác định điểm bắt đầu/kết thúc** của mỗi message. Có bốn cách phổ biến.

| Cách | Quy tắc | Phù hợp với | Điều dễ sai |
| --- | --- | --- | --- |
| **Kích thước cố định** | Mỗi message đúng N byte | Binary record đơn giản, cấu trúc cố định | Phải thống nhất N và layout |
| **Delimiter** | Message kết thúc bằng ký tự/chuỗi phân cách, ví dụ LF | Lệnh văn bản, giao thức theo dòng | Payload chứa delimiter phải escape; cần giới hạn dòng |
| **Length-prefix** | Header ghi kích thước phần body | Binary, JSON, nhiều message cùng kết nối | Phải giới hạn length để tránh cấp phát khổng lồ |
| **Giao thức chuẩn** | Dùng framing của HTTP, WebSocket, gRPC... | API, ứng dụng phân tán | Tuân thủ đúng framing và version của từng chuẩn |

**TCP không cung cấp framing**, vì vậy không có lựa chọn nào tự xuất hiện khi tạo socket.

### 7.1. Delimiter bằng dòng văn bản

Nếu giao thức định nghĩa mỗi thông điệp là **một dòng UTF-8 kết thúc bằng LF**, sender có thể dùng BufferedWriter.write(...), newLine(), flush(); receiver dùng BufferedReader.readLine().

~~~java
// Minh họa API nằm trong một phiên TCP đang mở.
out.write("PING");
out.newLine();
out.flush();

String command = in.readLine();
~~~

**readLine()** có thể gọi những lần đọc byte bên dưới nhiều lần; nó trả chuỗi logic một dòng, không phải một TCP packet. Nếu stream kết thúc trước khi có ký tự mới, readLine() trả null; nếu EOF đến sau một số ký tự nhưng chưa có delimiter, API có thể trả phần ký tự đã đọc thành dòng cuối. Vì thế giao thức yêu cầu **newline bắt buộc** phải kiểm tra riêng tình huống EOF/truncated message nếu cần.

Chỉ dùng ví dụ khi payload **không chứa LF chưa escape**. Một JSON có nhiều dòng không thể mặc định nhận hết bằng một readLine().

### 7.2. Length-prefix

Ví dụ lớp trợ giúp (đoạn minh họa **không phải chương trình Java độc lập**, đặt bên trong một class đã import java.io.*):

~~~java
static byte[] readFrame(DataInputStream in) throws IOException {
    int n = in.readInt(); // 4 byte, big-endian
    if (n < 0 || n > 1_048_576) {
        throw new IOException("Invalid frame length");
    }
    byte[] payload = new byte[n];
    in.readFully(payload);    // Lặp nội bộ đến đủ n byte hoặc EOFException
    return payload;
}

static void writeFrame(DataOutputStream out, byte[] payload)
        throws IOException {
    if (payload.length > 1_048_576) {
        throw new IOException("Frame too large");
    }
    out.writeInt(payload.length);
    out.write(payload);
    out.flush();
}
~~~

Với nhiều message trên cùng socket, gọi **readFrame(...) cho từng message**. Bên nhận phải đọc đủ header trước khi quyết định body dài bao nhiêu, rồi đọc **đúng** số byte body. Byte đầu tiên sau body là điểm bắt đầu header tiếp theo. Không lấy n từ số byte read() trả về.

Thao tác **readFully()** có thể phải đọc từ socket nhiều lần, nhưng sau khi thành công, ứng dụng có một message đúng kích thước. Nếu EOF đến sớm, **EOFException** báo frame bị cắt. Một **SocketTimeoutException** không mang ý nghĩa “kết thúc message”; nó cho biết lần đọc vượt thời gian chờ.

**Không giải mã UTF-8 ở giữa message nếu có thể cắt rời ký tự nhiều byte.** Với payload đã lắp đủ, dùng **new String(bytes, StandardCharsets.UTF_8)** hoặc bộ giải mã phù hợp chính sách validation. Nếu phải stream-decode theo chunk, dùng **CharsetDecoder** có trạng thái để xử lý ký tự trải qua nhiều chunk.

### 7.3. Kết thúc bằng EOF

Một số giao thức đơn giản gửi toàn bộ dữ liệu rồi **shutdownOutput()** hoặc đóng phía gửi, để đầu nhận đọc đến EOF. Cách này hợp lý **chỉ khi chính EOF được định nghĩa là điểm kết thúc message**, ví dụ một luồng một chiều. Nó không phù hợp để đánh dấu nhiều message liên tiếp trên một kết nối cần giữ mở, và dễ gây deadlock nếu cả hai bên đều chờ đối phương đóng.

**InputStream.readAllBytes()** và vòng lặp đọc đến -1 hoạt động theo nguyên tắc này: chúng hoàn tất khi EOF xuất hiện, **không** khi sender gọi xong một lần write.

## 8. Cần hiểu đúng EOF, timeout, close và flush

### Khi nào read() trả -1?

Với TCP socket input, -1 thường xuất hiện sau khi peer đã hoàn tất đóng chiều gửi và byte còn lại đã được tiêu thụ. Điều này cho biết **stream kết thúc**, không cho biết **một thông điệp ứng dụng bất kỳ** đã đủ.

Ví dụ server nhận request dài 100 byte theo header nhưng chỉ đọc được 70 byte rồi EOF: message **không hoàn chỉnh**, phải báo lỗi; không được xử lý 70 byte như một request hợp lệ.

### Nếu peer không đóng thì sao?

Một server đọc “cho đến -1” có thể **chờ mãi** khi client cố ý giữ socket mở để đợi response. Cả hai phía cùng chờ sẽ gây deadlock ở tầng ứng dụng. Hãy dùng **delimiter, length-prefix hoặc giao thức chuẩn** thay vì phụ thuộc việc kết thúc kết nối.

### Timeout có phải delimiter không?

**Không.** Socket.setSoTimeout(n) đặt giới hạn thời gian chặn của mỗi thao tác đọc; khi hết thời gian có thể ném SocketTimeoutException. Dữ liệu đến chậm vẫn có thể là cùng một message hợp lệ; và một peer độc hại có thể gửi từng phần nhỏ để mỗi lần đọc không timeout. Ứng dụng cần thêm **giới hạn tổng thời gian cho toàn bộ frame** khi phù hợp.

### flush() có nghĩa đầu kia đã đọc xong không?

**Không.** Với writer/buffered stream, flush đẩy dữ liệu từ bộ đệm của lớp đó xuống stream tiếp theo. Nó không đợi đến khi phía nhận thực hiện read, không chứng minh ứng dụng đã giải mã hoặc commit giao dịch. Muốn biết request được xử lý, xây **acknowledgment ở tầng ứng dụng** và quy tắc chống xử lý trùng.

### close() có thể thay cho framing không?

Không trong trường hợp cần nhiều request/response trên cùng kết nối. Close/shutdown chỉ phục vụ vòng đời luồng. Nếu thiết kế giao thức dùng EOF làm delimiter thì phải quy định tường minh; cách đó không thể tái dùng cùng chiều gửi cho các message sau.

## 9. Những lỗi code phổ biến

### Lỗi A: đọc một lần rồi parse ngay

~~~java
int count = input.read(buffer);
parseRequest(buffer, count); // Sai nếu chưa xác định đủ frame
~~~

Có thể chỉ mới nhận một phần request hoặc gộp nhiều request. Cách sửa: bộ giải mã framing xử lý **header/body/delimiter** và giữ lại byte dư để parse message kế tiếp.

### Lỗi B: lấy buffer.length làm số byte đã đọc

~~~java
byte[] buffer = new byte[1024];
int count = input.read(buffer);
System.out.println(new String(buffer, StandardCharsets.UTF_8));
~~~

Đoạn này có thể in thêm byte cũ hoặc ký tự NUL vì **buffer.length = dung lượng** chứ không phải số byte mới nhận. Nếu đúng mục tiêu hiển thị chunk đã đọc thì dùng khoảng **[0, count)** sau khi kiểm tra count > 0. Tuy nhiên, hiển thị chunk vẫn không giải quyết framing.

### Lỗi C: dùng available() để tính độ dài message

~~~java
int size = input.available(); // Không phải tổng chiều dài message!
~~~

**available()** là ước lượng byte có thể đọc ngay mà không block trong ngữ cảnh stream, không hứa rằng sender đã gửi xong hoặc byte đang trên mạng đã đến. size == 0 không khẳng định message kết thúc.

### Lỗi D: sleep hoặc TCP_NODELAY để ép read khớp write

Delay nhân tạo và socket option chỉ ảnh hưởng timing/packing, không tạo ranh giới. Bài học đúng là **thiết kế protocol**, không cố “đồng bộ hóa” các lời gọi read/write bằng may rủi.

### Lỗi E: nhận theo chuỗi UTF-8 từng chunk tùy ý

Một ký tự tiếng Việt có thể trải qua hai read. Nếu mỗi chunk được giải mã riêng bằng new String(chunk, UTF_8), bộ giải mã có thể sinh ký tự thay thế, làm hỏng văn bản. Cách sửa là gom đúng frame byte trước khi decode hoặc dùng bộ giải mã streaming có trạng thái.

### Lỗi F: tin tưởng length từ mạng

Nếu peer gửi header yêu cầu cấp phát hàng gigabyte, tạo mảng ngay từ giá trị đó có thể cạn bộ nhớ. Hãy **giới hạn size, số frame, timeout, tốc độ, tổng dữ liệu** trước khi cấp phát. Nếu đọc thiếu thì hủy frame/kết nối theo hợp đồng.

### Lỗi G: parse frame xong nhưng vứt phần byte dư

Một lần read có thể chứa cuối frame A và đầu frame B. Nếu tự viết parser theo buffer, phải **giữ byte chưa tiêu thụ** để parse frame B. Dùng DataInputStream.readFully với length-prefix giúp giảm nguy cơ đọc quá biên của một frame.

### Lỗi H: coi write thành công là “đơn hàng đã tạo”

Nếu kết nối đứt sau khi write nhưng trước response, client có thể không biết server đã xử lý hay chưa. Dùng **request ID/idempotency key**, acknowledgment và cơ chế đối soát theo tính chất nghiệp vụ. TCP không bảo đảm exactly-once processing cho business operation.

## 10. Một ví dụ trước–sau trong ứng dụng thực

Giả sử client cần gửi hai request tạo tác vụ trên **một TCP connection**:

~~~text
Request A = {"task":"A"}
Request B = {"task":"B"}
~~~

**Cách sai:** thực hiện write(A), write(B); server đọc một lần cho A, rồi đọc một lần cho B. Nếu TCP gộp hai nội dung hoặc cắt giữa JSON, parse sai hoặc block. Việc cả hai request cùng là JSON **không giải quyết ranh giới**: ký tự đóng dấu ngoặc không đủ cho parser đơn giản nếu có chuỗi chứa escape, JSON lồng nhau, hoặc dữ liệu kế tiếp.

**Cách đúng:** chọn một framing, ví dụ 4-byte length-prefix + UTF-8 JSON cho mỗi request:

~~~text
[4-byte length][12 byte JSON A][4-byte length][12 byte JSON B]
    frame A hoàn chỉnh           frame B hoàn chỉnh
~~~

Header là **4 byte big-endian** do `DataOutputStream.writeInt(...)` ghi, còn mỗi payload JSON ASCII trong ví dụ dài **12 byte UTF-8**. Trong hệ thống thật hãy tính độ dài bằng `payload.getBytes(StandardCharsets.UTF_8).length`, không dùng `String.length()` hoặc hard-code chiều dài.

Server đọc header A, đọc đủ body A, parse; sau đó đọc header B, đọc đủ body B, parse. TCP có thể phân phối hai frame qua bất kỳ số lần read nào, nhưng **ranh giới được khôi phục bằng length-prefix**. Nếu client/server dùng HTTP hoặc WebSocket, nên dùng framing của giao thức chuẩn thay cho một giao thức tự chế.

## 11. Phân biệt thêm với UDP, NIO và TLS

**UDP:** DatagramSocket.receive(...) nhận theo **datagram**, không phải byte stream. UDP giữ ranh giới datagram nếu datagram tới nơi, nhưng không bảo đảm giao hàng, thứ tự hay không trùng. Nếu mảng nhận quá ngắn, phần vượt quá có thể bị cắt bỏ theo API. Không lấy tính chất UDP để suy ngược cho TCP.

**Java NIO:** SocketChannel ở chế độ non-blocking có thể read 0 hoặc write 0; ứng dụng phải quản lý ByteBuffer.position/limit và parser incremental. Parser có thể nhận một phần header trong lần đọc đầu tiên, phần body trong lần sau, hoặc nhiều frame cùng lúc. Trong thực tế cần state machine như **READ_HEADER → READ_BODY → EMIT_FRAME → READ_HEADER** và giữ phần byte chưa được tiêu thụ.

**TLS:** SSLSocket hoặc tầng TLS thêm mã hóa/bộ đệm/record bên dưới, nhưng InputStream của ứng dụng vẫn không tự biến mỗi write thành một message ở tầng nghiệp vụ. TLS record boundaries không phải định nghĩa thông điệp của API mà bạn tự thiết kế. Hãy chọn framing thích hợp ở tầng ứng dụng.

## 12. Các câu hỏi kiểm tra hiểu biết

**Câu 1.** Client write() 100 byte một lần, server có buffer 1024 byte. Server có chắc đọc được đúng 100 byte trong lần read đầu tiên không?  
**Đáp án:** Không. Có thể đọc ít hơn 100 byte; read phụ thuộc byte đã sẵn có và trạng thái stream. Phải biết kích thước message và đọc đủ.

**Câu 2.** Client write() hai lần, mỗi lần 50 byte; server có thể nhận một lần read 100 byte không?  
**Đáp án:** Có, nếu 100 byte đã sẵn có và buffer đủ. Hai write không tương ứng bắt buộc với hai read.

**Câu 3.** Vì sao server của ví dụ chắc chắn in Multiple reads: true?  
**Đáp án:** Payload dài 16 byte nhưng mỗi lần read payload đọc tối đa 4 byte. Do đó cần ít nhất 4 lần read dương. Điều này do kích thước buffer ứng dụng, không phụ thuộc ta đoán TCP chia segment thế nào.

**Câu 4.** read(...) trả -1 có phải kết thúc một JSON không?  
**Đáp án:** -1 nghĩa là EOF của stream sau byte còn lại. Chỉ coi nó là điểm kết thúc message nếu giao thức **chủ động dùng EOF làm delimiter** và xác minh message đầy đủ.

**Câu 5.** Đặt TCP_NODELAY có làm mỗi write thành một message không?  
**Đáp án:** Không. TCP_NODELAY không thay đổi byte-stream semantics.

**Câu 6.** Nếu length-prefix nói 400 byte mà server nhận được 250 byte rồi EOF, có thể parse 250 byte không?  
**Đáp án:** Không. Đây là frame thiếu; báo EOFException/protocol error, không xử lý như thông điệp hoàn chỉnh.

**Câu 7.** Vì sao không dùng String.length() làm length-prefix của một văn bản UTF-8?  
**Đáp án:** Length-prefix biểu diễn **số byte**; ký tự Unicode có thể chiếm nhiều byte trong UTF-8. Dùng **getBytes(UTF_8).length**.

**Câu 8.** Khi nào InputStream.readAllBytes() có thể là lựa chọn đúng?  
**Đáp án:** Khi hợp đồng truyền xác định rõ **toàn bộ stream kết thúc bằng EOF** và có giới hạn tài nguyên phù hợp, chẳng hạn một luồng dữ liệu một chiều có độ dài hợp lý. Nó không tự nhận biết ranh giới của nhiều message trên kết nối giữ mở.

## Kết luận

Lý do **một write không tương ứng một read** nằm ở chính hợp đồng của **TCP byte stream**: TCP bảo toàn thứ tự byte trong luồng, nhưng không bảo toàn những ranh giới do các lời gọi write(...) tạo ra. Một read(...) chỉ lấy một lượng byte phù hợp với buffer và trạng thái nhận, nên có thể đọc một phần của một write hoặc dữ liệu đến từ nhiều write.

Muốn chương trình hoạt động đúng, hãy **thiết kế framing** (fixed-size, delimiter, length-prefix hoặc giao thức chuẩn), **đọc đủ byte**, **giới hạn tài nguyên**, **xử lý EOF/timeout**, và chỉ **giải mã/xử lý khi một thông điệp đã hoàn chỉnh**. Đây là nền tảng để xây TCP server/client đúng, kể cả khi dùng Java blocking I/O, NIO hoặc TLS.

### Tài liệu tham khảo

- [RFC 9293 — Transmission Control Protocol, mục Segmentation](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.7): TCP không bảo đảm quan hệ một-một giữa segment, read/write buffer và thông điệp ứng dụng.
- [Java 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): read(), readNBytes() và các điều kiện EOF.
- [Java 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): readInt() và readFully().
- [Java 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): write() và flush().
- [Java 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): TCP socket và thời gian chờ đọc.
- [Java 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): read/write với ByteBuffer và non-blocking I/O.
