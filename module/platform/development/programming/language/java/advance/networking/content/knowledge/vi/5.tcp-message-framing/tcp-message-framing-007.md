# Giới hạn kích thước thông điệp trước khi cấp phát bộ nhớ

## 1. Vấn đề: TCP là luồng byte, còn kích thước message có thể do peer cung cấp

TCP cung cấp một **luồng byte có thứ tự**. Nó không mang khái niệm “một lần `write` là một thông điệp”: một `read` có thể nhận một phần, nhiều phần hoặc dữ liệu từ nhiều lần ghi. Để phân biệt ranh giới, ứng dụng cần **quy tắc đóng khung (framing)**, ví dụ gửi bốn byte thông báo độ dài trước mỗi phần dữ liệu.

Điểm nguy hiểm xuất hiện khi dùng độ dài chưa kiểm chứng từ mạng để cấp phát bộ nhớ:

~~~java
DataInputStream in = new DataInputStream(socket.getInputStream());
int length = in.readInt();
byte[] payload = new byte[length]; // Sai: dữ liệu của client quyết định cấp phát.
in.readFully(payload);
~~~

*Đoạn mã trên minh họa **cách không được làm**, không phải chương trình độc lập.*

Chỉ cần gửi bốn byte header mô tả độ dài rất lớn, một peer không đáng tin có thể khiến chương trình xin mảng khổng lồ. Khi đó server có thể gặp `OutOfMemoryError`, áp lực GC, độ trễ lớn hoặc từ chối phục vụ các kết nối khác. Peer thậm chí **không cần gửi một byte payload nào**. Header âm có thể làm `new byte[length]` ném `NegativeArraySizeException`.

**Nguyên tắc:** kiểm tra giá trị length và ngân sách tài nguyên **trước mọi phép cấp phát hoặc phép tính kích thước dựa vào length**. Sau khi hợp lệ, mới bắt đầu đọc đầy đủ frame và giải mã nội dung.

## 2. Phải định nghĩa giới hạn dựa trên định dạng dữ liệu trên dây

Ví dụ này dùng một giao thức TCP tự định nghĩa:

~~~text
       4 byte header            length byte payload
+------------------------+------------------------------+
| Signed 32-bit length   | Nội dung message             |
+------------------------+------------------------------+

Frame của "HELLO":
00 00 00 05  48 45 4C 4C 4F
[4 byte=5]   [5 byte payload]
~~~

`DataOutputStream.writeInt` ghi `int` 4 byte theo thứ tự byte lớn trước (big-endian); `DataInputStream.readInt` đọc đúng bốn byte đó thành `int` có dấu. **Đây là quy ước framing của ứng dụng**, không phải tính năng tự có của TCP.

Quy ước ví dụ: giá trị length chỉ tính **payload**, không bao gồm bốn byte header. Vì thế một frame payload 1024 byte có tổng kích thước truyền trên dây là 1028 byte.

Một chính sách rõ ràng có thể là:

| Thành phần | Quy tắc |
| --- | --- |
| Header | 4 byte signed `int`, big-endian |
| Kích thước payload tối đa | `MAX_PAYLOAD_BYTES = 1_048_576` (1 MiB), chỉ làm ví dụ |
| Header âm | Từ chối ngay |
| Header bằng 0 | Chấp nhận nếu giao thức cho phép message rỗng |
| Header từ 1 đến `MAX_PAYLOAD_BYTES` | Hợp lệ về mặt kích thước, bắt đầu đọc chính xác payload |
| Header lớn hơn `MAX_PAYLOAD_BYTES` | Từ chối trước khi tạo mảng hay buffer |

Mốc 1 MiB **không phải giới hạn mặc định hay giá trị an toàn cho mọi hệ thống**. Một lệnh điều khiển có thể giới hạn vài KiB; một luồng truyền tệp cần thiết kế đọc theo khối. Trong hai bài chạy minh họa phía dưới, hạn mức được cố ý chọn là 1024 và 16 byte để nhìn thấy lỗi rõ ràng.

Đừng nhầm **số byte** với **số ký tự**. Một chuỗi UTF-8, nhất là tiếng Việt, có thể tốn nhiều byte hơn số ký tự hiển thị; `String.length()` đếm đơn vị UTF-16. Nếu giao thức tuyên bố “tối đa 1024 byte”, hãy chặn theo **số byte nhận từ mạng trước khi chuyển sang String**.

## 3. Quy trình chuẩn: read header → validate → allocate → readFully

Với length-prefix 4 byte:

1. Đọc **đúng bốn byte** bằng `DataInputStream.readInt()`. Nếu header chưa đủ, phương thức ném `EOFException`; không được tự đoán độ dài.
2. Kiểm tra hai đầu miền giá trị: `length < 0` hoặc `length > MAX_PAYLOAD_BYTES` đều là lỗi. Nếu message rỗng bị cấm, kiểm tra cả `length == 0`.
3. Chỉ **sau khi hợp lệ**, cấp phát `new byte[length]`.
4. Dùng `readFully(payload)` để nhận đủ số byte được khai báo. TCP có thể chia một payload qua nhiều lần đọc, vì vậy **không** giả định `read(payload)` một lần sẽ đủ.
5. Nếu EOF, timeout hoặc mất kết nối trước khi đủ payload, **không xử lý frame chưa hoàn chỉnh**. Đóng/loại bỏ connection theo chính sách, tránh giải mã dữ liệu dở.
6. Khi đã đủ payload, kiểm tra tiếp định dạng, charset, xác thực, nén hoặc nội dung nghiệp vụ; header hợp lệ chỉ chứng minh **độ dài được khai báo nằm trong hạn mức**, chưa chứng minh payload hợp lệ.

Mẫu thuật toán cốt lõi:

~~~java
static final int MAX_PAYLOAD_BYTES = 1024;

static byte[] readFrame(InputStream source) throws IOException {
    DataInputStream in = new DataInputStream(source);
    int length = in.readInt();
    if (length < 0 || length > MAX_PAYLOAD_BYTES) {
        throw new IOException("invalid length: " + length);
    }
    byte[] payload = new byte[length]; // Chỉ được thực hiện sau kiểm tra.
    in.readFully(payload);
    return payload;
}
~~~

*Đây là phương thức minh họa cần đặt trong một class đã import `java.io.*`. Chương trình hoàn chỉnh ở phần 5.*

`readFully` tiếp tục đọc cho tới khi đủ độ dài yêu cầu, gặp cuối luồng (`EOFException`) hoặc gặp lỗi I/O. Mảng có độ dài 0 được xử lý ngay mà không cần chờ thêm payload.

Một hệ thống production thường giữ một bộ đọc trên connection và đọc liên tiếp từng frame. Với một frame có header vượt hạn mức, cách đơn giản, dễ tránh mất đồng bộ là **từ chối frame và đóng connection**, thay vì thử đọc bỏ số byte khổng lồ theo đúng header độc hại.

## 4. Các cách viết thiếu an toàn và cách sửa

| Cách viết | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| `new byte[in.readInt()]` | Dùng length chưa kiểm chứng để cấp phát ngay | Đọc ra biến, so sánh min/max trước |
| `if (length <= MAX)` | Chưa loại length âm | Dùng `length >= 0 && length <= MAX` |
| `byte[] p = new byte[length]; if (length > MAX)...` | Check sau allocation | Đưa check trước allocation |
| `int total = length + 4; if (total <= MAX)...` | Cộng trước check có thể overflow `int` | Validate length trước; dùng `long` hoặc `Math.addExact` |
| `if (in.available() >= length) ...` | `available()` không phản ánh số byte sẽ đến hay độ dài message | Đọc đúng framing bằng `readFully` và timeout |
| `in.readAllBytes()` trên socket mở lâu | Có thể gom dữ liệu không giới hạn hoặc đợi EOF mãi | Giới hạn frame và đọc có kiểm soát |
| `in.readNBytes(length)` trước kiểm tra | Có thể cấp phát theo length độc hại | Chỉ dùng sau khi kiểm tra giới hạn |
| So sánh `String.length()` với byte limit | Số đơn vị UTF-16 khác số byte UTF-8 | Giới hạn trên dữ liệu byte trước khi decode |
| Chỉ giới hạn dữ liệu nén | Payload nhỏ có thể nở rất lớn | Giới hạn cả kích thước sau giải nén |
| Tự cấp phát 1 MiB trên hàng nghìn connection | Mỗi frame đạt hạn mức, tổng bộ nhớ vẫn quá lớn | Quota tổng RAM, số connection và backpressure |

Khi muốn tính **tổng số byte của frame**, hãy nhớ độ dài prefix của giao thức: chẳng hạn `4L + length` đối với header 4 byte. Dùng `long` để tránh tràn `int` trước khi so sánh. Không cấp phát mảng “tổng frame” trước khi kiểm tra.

Nếu định dạng length thực sự là **unsigned 32-bit**, đừng dùng `readInt()` rồi ép số âm thành size của mảng. Có thể chuyển `int raw = in.readInt()` thành `long unsignedLength = Integer.toUnsignedLong(raw)`, sau đó kiểm tra `unsignedLength <= MAX_PAYLOAD_BYTES` ở kiểu `long` **trước khi ép về `int`**. Hai phía gửi/nhận phải thống nhất signed/unsigned, không được tự thay đổi quy ước ở một phía.

## 5. Ví dụ Java 17+: chứng minh chặn độ dài trước khi cấp phát

Ví dụ chạy trên luồng byte trong bộ nhớ, không phụ thuộc máy chủ hoặc Internet. Hàm `frame(...)` cố ý nhận header tùy ý để **mô phỏng peer gửi dữ liệu sai**. Writer production phải kiểm tra độ dài trước khi gửi, nhưng reader không được tin rằng mọi peer đều là writer đúng.

Lưu tệp `FrameBoundsDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class FrameBoundsDemo {
    private static final int MAX_PAYLOAD_BYTES = 1024;

    static byte[] readFrame(InputStream source) throws IOException {
        DataInputStream in = new DataInputStream(source);
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD_BYTES) {
            throw new IOException("invalid length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return payload;
    }

    static byte[] frame(int announcedLength, byte[] actualPayload)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(announcedLength);
        out.write(actualPayload);
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] hello = "HELLO".getBytes(StandardCharsets.UTF_8);
        System.out.println("valid payload: " +
                new String(readFrame(new ByteArrayInputStream(
                        frame(hello.length, hello))), StandardCharsets.UTF_8));

        System.out.println("empty payload bytes: " +
                readFrame(new ByteArrayInputStream(frame(0, new byte[0]))).length);

        try {
            readFrame(new ByteArrayInputStream(frame(-1, new byte[0])));
        } catch (IOException e) {
            System.out.println("negative rejected: " + e.getMessage());
        }

        try {
            readFrame(new ByteArrayInputStream(frame(1025, new byte[0])));
        } catch (IOException e) {
            System.out.println("oversize rejected: " + e.getMessage());
        }

        try {
            readFrame(new ByteArrayInputStream(frame(5, new byte[] { 65, 66 })));
        } catch (EOFException e) {
            System.out.println("truncated rejected: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FrameBoundsDemo.java
java FrameBoundsDemo
~~~

Kết quả:

~~~text
valid payload: HELLO
empty payload bytes: 0
negative rejected: invalid length: -1
oversize rejected: invalid length: 1025
truncated rejected: EOFException
~~~

Các trường hợp minh chứng:

- Header `5` kèm đủ năm byte `HELLO` thành công.
- Header `0` hợp lệ theo chính sách hiện tại, trả một mảng rỗng.
- Header `-1` hoặc `1025` bị từ chối **ngay sau đọc header** khi `MAX_PAYLOAD_BYTES == 1024`, không cần peer gửi payload.
- Header `5` nhưng chỉ có hai byte `AB` làm `readFully` ném `EOFException`; reader không được chuyển `AB` thành message thành công.

`readInt()` cũng có thể ném `EOFException` nếu stream hết trước khi đọc đủ 4 byte header. Khi nhận nhiều frame trên cùng một TCP connection, giao thức nên phân biệt **EOF đúng ranh giới frame** (client đóng bình thường) với **EOF khi đã bắt đầu header/payload** (frame thiếu). Chỉ gọi `readInt()` không cho biết nó đã nhận 0 hay 1–3 byte trước EOF; nếu cần phân biệt, phải tự đọc/count header theo số byte nhận được.

## 6. Ví dụ Java 17+: giới hạn frame trên TCP loopback thật

Bây giờ sử dụng `ServerSocket` và `Socket` trên cùng máy. Server đặt `MAX_PAYLOAD_BYTES = 16`. Kết nối đầu gửi `"OK"`; kết nối thứ hai chỉ gửi header `17` và **không gửi payload**. Reader phải từ chối ngay vì 17 vượt 16, thay vì chờ payload hay tạo mảng.

Lưu tệp `TcpFrameLimitDemo.java`:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpFrameLimitDemo {
    private static final int MAX_PAYLOAD_BYTES = 16;

    static byte[] readFrame(InputStream source) throws IOException {
        DataInputStream in = new DataInputStream(source);
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD_BYTES) {
            throw new IOException("invalid length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return payload;
    }

    public static void main(String[] args) throws IOException {
        try (ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(2_000);

            try (Socket sender = new Socket(
                    listener.getInetAddress(), listener.getLocalPort());
                 Socket receiver = listener.accept()) {
                receiver.setSoTimeout(2_000);
                DataOutputStream out = new DataOutputStream(sender.getOutputStream());
                byte[] message = "OK".getBytes(StandardCharsets.UTF_8);
                out.writeInt(message.length);
                out.write(message);
                out.flush();

                byte[] received = readFrame(receiver.getInputStream());
                System.out.println("accepted: " +
                        new String(received, StandardCharsets.UTF_8));
            }

            try (Socket sender = new Socket(
                    listener.getInetAddress(), listener.getLocalPort());
                 Socket receiver = listener.accept()) {
                receiver.setSoTimeout(2_000);
                DataOutputStream out = new DataOutputStream(sender.getOutputStream());
                out.writeInt(MAX_PAYLOAD_BYTES + 1);
                out.flush();

                try {
                    readFrame(receiver.getInputStream());
                } catch (IOException e) {
                    System.out.println("oversize rejected: " + e.getMessage());
                }
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac TcpFrameLimitDemo.java
java TcpFrameLimitDemo
~~~

Kết quả khi môi trường cho phép kết nối TCP loopback:

~~~text
accepted: OK
oversize rejected: invalid length: 17
~~~

Vì sao ví dụ này có giá trị:

1. `new ServerSocket(0, 8, InetAddress.getLoopbackAddress())` lắng nghe trên loopback và nhờ hệ điều hành cấp cổng server, tránh phụ thuộc số cổng cố định.
2. `DataOutputStream.writeInt` tương thích với `DataInputStream.readInt`: một phía khai báo độ dài byte, phía còn lại đọc đúng format.
3. `receiver.setSoTimeout(2_000)` giới hạn thời gian của một thao tác đọc đang chặn; bảo vệ nếu peer khai báo độ dài hợp lệ nhưng không gửi tiếp payload. Hạn chờ này **không phải deadline tổng cho cả frame**.
4. Trong lần kết nối thứ hai, chương trình kiểm tra `length > MAX_PAYLOAD_BYTES` trước `new byte[length]`; không phát sinh allocation phụ thuộc `17` và cũng không gọi `readFully`.
5. `try-with-resources` đóng các socket. Trong dịch vụ thật, cần phân biệt loại lỗi vi phạm giao thức và xử lý/log đúng mức; đoạn demo dùng `IOException` chung để tập trung vào thứ tự kiểm tra.

## 7. Giới hạn theo message chưa phải giới hạn bộ nhớ toàn hệ thống

Giả sử mỗi frame hợp lệ tối đa **1 MiB**. Nếu 200 kết nối đồng thời đều khiến server giữ mảng gần 1 MiB, **riêng các mảng payload** đã chiếm gần **200 MiB**, chưa tính bộ đệm TCP, đối tượng Java, thread, dữ liệu parse và các bản sao.

Vì thế một hệ thống chịu tải cần hai lớp bảo vệ:

- **Hạn mức từng frame:** kiểm tra `0 <= length <= MAX_PAYLOAD_BYTES` trước allocation, không phụ thuộc điều client khai báo muốn bao nhiêu.
- **Hạn mức tổng:** giới hạn số kết nối, lượng byte đang chờ xử lý, số frame đang giải mã và hàng đợi tác vụ. Khi hết ngân sách, áp **backpressure**, từ chối hoặc tạm ngưng nhận thêm theo thiết kế.

Thêm vào đó, một frame nhỏ không bảo đảm xử lý rẻ:

| Dữ liệu đến | Rủi ro còn lại | Biện pháp |
| --- | --- | --- |
| Nhiều frame rất nhỏ | Tổng số request hoặc byte/giây quá lớn | Rate limit, quota tổng, hàng đợi có giới hạn |
| Payload nén nhỏ | Giải nén thành dữ liệu khổng lồ (decompression bomb) | Giới hạn byte sau giải nén và chi phí |
| JSON/XML lồng sâu | Parser tiêu thụ nhiều RAM hoặc CPU | Giới hạn độ sâu, số node, kích thước chuỗi |
| Payload chỉ có header rồi dừng | Buffer/connection tồn tại lâu, tốn tài nguyên | Timeout, deadline tổng, read-rate |
| Nhiều frame chờ nghiệp vụ | Dữ liệu backlog tích tụ | Bounded queue, semaphore, xử lý theo luồng |

Không nên coi `OutOfMemoryError` là ngoại lệ bình thường dùng để từ chối payload. Khi đến đó JVM có thể đã mất khả năng phục vụ ổn định.

## 8. Streaming: đọc payload theo từng khối khi không cần giữ toàn bộ trong RAM

Với bài toán cần chuyển/lưu dữ liệu dài, thay vì cấp phát `byte[length]` sau khi kiểm tra, có thể **kiểm tra length rồi đọc từng khối cố định**. Ví dụ helper dưới đây dùng buffer 8 KiB và không đọc vượt số byte còn lại của frame:

~~~java
static void copyLimitedFrame(InputStream input, OutputStream output, int length)
        throws IOException {
    final int maxFrameBytes = 1024 * 1024;
    if (length < 0 || length > maxFrameBytes) {
        throw new IOException("invalid length: " + length);
    }

    byte[] chunk = new byte[8192];
    int remaining = length;
    while (remaining > 0) {
        int count = input.read(chunk, 0, Math.min(chunk.length, remaining));
        if (count < 0) {
            throw new EOFException("truncated payload");
        }
        if (count == 0) {
            continue;
        }
        output.write(chunk, 0, count);
        remaining -= count;
    }
}
~~~

*Phương thức minh họa, cần class có `import java.io.*`. Caller đọc header trước và chuyển length hợp lệ, quản lý stream, timeout và đích nhận. Đây không phải chương trình độc lập.*

`remaining` giảm theo số byte **thực sự đọc** chứ không giảm theo số byte yêu cầu. Điều này vừa xử lý read ngắn, vừa tránh nuốt byte thuộc frame kế tiếp. Buffer cố định `8192` byte giúp hạn chế RAM trên một luồng.

Tuy nhiên, nếu `output` là `ByteArrayOutputStream` thì nó **vẫn** có thể giữ toàn bộ dữ liệu trong bộ nhớ. Muốn streaming thật sự, cần đích tiêu thụ có hạn mức, ví dụ ghi tệp tạm hoặc xử lý chunk liên tục. Không công bố một tệp/đối tượng “hoàn chỉnh” khi chưa nhận đủ dữ liệu, kiểm tra tính toàn vẹn và xác thực cần thiết. Tệp tạm/đĩa cũng cần quota để tránh chuyển bài toán DoS từ RAM sang lưu trữ.

## 9. Tránh lỗi số nguyên và đổi kiểu khi đọc độ dài

Một lỗi nguy hiểm là tính tổng kích thước bằng `int` **trước khi** validate:

~~~java
int total = length + 4; // Có thể tràn số nguyên.
if (total <= MAX_FRAME_BYTES) {
    byte[] frame = new byte[total];
}
~~~

*Đây là ví dụ sai về thứ tự kiểm tra, không dùng làm mã production.*

Nếu length gần `Integer.MAX_VALUE`, phép cộng 4 có thể trở thành số âm. Quy trình đúng là kiểm tra khoảng **không âm và không quá max** trước, sau đó tính `long total = 4L + length` hoặc `Math.addExact(4, length)` rồi so sánh với hạn mức tổng frame.

Với header 8 byte, `DataInputStream.readLong()` có thể đọc số lớn hơn rất nhiều kích thước mảng Java: phải so sánh ở kiểu `long` rồi **mới** ép kiểu. Với header unsigned 32-bit, đọc raw `int` rồi chuyển `Integer.toUnsignedLong(raw)`, kiểm tra giá trị `long` trước khi cast sang `int`; không được để số unsigned lớn biến thành signed âm rồi đi vào cấp phát.

Không tự diễn giải byte order: `DataInputStream.readInt` là big-endian. Nếu giao thức bên ngoài là little-endian, phải giải mã tương ứng; hai phía lệch thứ tự byte có thể biến một header nhỏ thành độ dài khổng lồ.

## 10. EOF, timeout và xử lý frame lỗi

- `DataInputStream.readInt()` đọc bốn byte header. Nếu không đủ, `EOFException` báo stream kết thúc sớm; không cố đoán length.
- `DataInputStream.readFully(byte[])` chỉ trả về khi đủ toàn bộ payload; nếu EOF giữa chừng, ném `EOFException`. Không xử lý mảng mới chỉ được ghi một phần như message hoàn chỉnh.
- `Socket.setSoTimeout(milliseconds)` là hạn chờ cho **mỗi thao tác đọc chặn** trên socket, có thể gây `SocketTimeoutException`. Nó không phải deadline tổng của toàn bộ frame: một peer gửi từng byte chậm có thể kéo dài tổng thời gian. Cần deadline tổng hoặc yêu cầu tốc độ tối thiểu khi hệ thống có yêu cầu chống slow client.
- Nếu header vượt giới hạn, từ chối ngay và đóng connection; không đọc bỏ số byte khổng lồ theo một trường length không đáng tin, trừ khi giao thức có cơ chế phục hồi có hạn mức riêng.
- Nếu read timeout sau khi nhận một phần payload, để bảo toàn framing thường nên đóng connection; tiếp tục như thể frame chưa từng bắt đầu dễ làm lệch ranh giới.
- Dùng `try-with-resources` cho `Socket`/`ServerSocket` và xử lý `IOException`. Không log toàn bộ payload không tin cậy hoặc đưa dữ liệu/stack trace nhạy cảm vào phản hồi peer.
- Hạn chế số kết nối và số byte đang giữ cùng lúc, kể cả khi **mỗi** message tuân thủ max. Mảng có chiều dài hợp lệ vẫn có thể cấp phát thất bại nếu hết ngân sách tổng.

Độ dài hợp lệ chỉ là **điều kiện cần**. Payload vẫn có thể sai charset, sai JSON/XML, sai checksum/chữ ký hoặc chứa nội dung làm thuật toán xử lý tốn tài nguyên. Các lớp giải mã sau cần giới hạn tiếp số phần tử, độ sâu, byte sau giải nén và số bản ghi sinh ra.

## 11. Các câu hỏi cần quyết định khi thiết kế giao thức

| Câu hỏi | Cần thống nhất trước triển khai |
| --- | --- |
| Ranh giới frame xác định bằng gì? | Prefix 4/8 byte, delimiter hoặc framing khác |
| Length bao gồm phần nào? | Chỉ payload hay tổng header + payload |
| Kiểu và endianness là gì? | Signed/unsigned, big-endian/little-endian |
| Message rỗng có hợp lệ? | `length == 0` được phép hay không |
| Max frame và max payload? | Giá trị cấu hình do **server kiểm soát**, có ngân sách |
| Kiểm tra nằm ở đâu? | Trước mọi allocation và phép tính dễ overflow |
| EOF giữa frame? | Hủy frame dở, không xử lý dữ liệu thiếu |
| Lỗi header quá lớn? | Đóng connection hoặc cơ chế phục hồi giới hạn rõ |
| Tổng byte/connection đồng thời? | Quota RAM, thời gian, hàng đợi, disk |
| Có nén/parse cấu trúc lồng nhau? | Giới hạn byte sau giải nén/độ sâu/đối tượng |
| Có cần giữ cả payload trong RAM? | Nếu không, dùng buffer cố định và đích tiêu thụ có quota |

Một bất biến có ích cho review code: **trên mọi đường thực thi, không có dữ liệu length do peer điều khiển nào đi vào allocation hoặc tính toán kích thước nguy hiểm trước khi được ràng buộc về miền giá trị hợp lệ**.

## 12. Câu hỏi và bài thực hành

**Câu 1.** Client gửi prefix `2_000_000_000` rồi ngắt ngay. Vì sao `new byte[in.readInt()]` nguy hiểm dù không có payload?

Đáp án: JVM cố cấp phát gần 2 tỷ byte ngay khi nhận header; thiếu bộ nhớ có thể xảy ra trước bước đọc payload.

**Câu 2.** Giao thức cho phép `0 <= length <= 1024`. Các length `-1`, `0`, `1024` và `1025` xử lý thế nào?

Đáp án: từ chối `-1` và `1025`; cho phép `0` và `1024`. Nếu giao thức cấm message rỗng, phải thêm điều kiện cấm `0`.

**Câu 3.** Header báo 6 byte, nhưng một lần `read()` chỉ trả 2 byte. Có phải peer vi phạm không?

Đáp án: **chưa**. TCP được phép giao dữ liệu từng phần. Tiếp tục đọc tới đủ 6 byte, EOF hoặc timeout theo chính sách.

**Câu 4.** Frame tối đa 1 MiB đã bảo vệ JVM khỏi mọi trường hợp hết RAM chưa?

Đáp án: chưa. Nhiều connection giữ frame cùng lúc và bản sao sau parse/giải nén vẫn có thể tiêu thụ nhiều bộ nhớ; phải giới hạn tổng.

**Câu 5.** Header ghi 100 KiB nén thành dữ liệu giải nén 500 MiB. Kiểm tra MAX payload 1 MiB có đủ?

Đáp án: không. Cần giới hạn **byte sau giải nén**, số node/độ sâu parser và tổng tài nguyên.

**Thực hành:** giảm `MAX_PAYLOAD_BYTES` của `FrameBoundsDemo` xuống `4`. Đổi payload `"HELLO"` (5 byte) thành `"JAVA"` (4 byte) để xác minh giá trị sát trần hợp lệ. Tiếp tục thử khai báo `4` nhưng chỉ gửi 2 byte, rồi xác minh `EOFException`. Trong `TcpFrameLimitDemo`, thử khai báo chiều dài hợp lệ nhưng chậm gửi payload để quan sát timeout; không tăng timeout vô hạn chỉ để bài chạy.

## Tài liệu API (Java SE 21)

- [`DataInputStream`, `readInt` và `readFully`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html)
- [`DataOutputStream` và `writeInt`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataOutputStream.html)
- [`DataInput` và hành vi `readFully` khi EOF](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInput.html)
- [`Socket` và `setSoTimeout`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [`InputStream` và `readNBytes`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
