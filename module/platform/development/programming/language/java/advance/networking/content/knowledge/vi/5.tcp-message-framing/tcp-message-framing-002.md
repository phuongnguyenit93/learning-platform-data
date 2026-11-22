# Xác định ranh giới thông điệp trên TCP: độ dài cố định, ký tự phân cách và tiền tố độ dài

**TCP truyền một luồng byte có thứ tự và đáng tin cậy, không truyền các “thông điệp” có ranh giới sẵn.** Nếu ứng dụng cần gửi lần lượt các bản tin `PING`, `PONG` hoặc các đối tượng JSON, hai đầu kết nối phải thống nhất một **giao thức đóng khung (message framing)** để biết byte nào thuộc bản tin nào. Ba cách phổ biến là **độ dài cố định**, **ký tự phân cách** và **tiền tố độ dài**.

Bài học tập trung vào cách thiết kế, mã hóa và đọc ba loại frame trên TCP bằng Java 17+, gồm kiểm soát đọc thiếu byte, UTF-8, EOF, giới hạn kích thước, timeout và các trường hợp gây lệch giao thức. Ví dụ chạy trên bộ nhớ lẫn loopback TCP, giúp bạn thấy cùng quy tắc framing áp dụng được cho mọi `InputStream`/`OutputStream`.

Sau bài này, bạn có thể:

- Giải thích vì sao một lần `write()` của sender không tương ứng một lần `read()` ở receiver.
- Chọn một trong ba giao thức framing theo đặc tính dữ liệu.
- Viết reader có khả năng ghép byte nhận từng đợt, đọc nhiều frame liên tiếp và phát hiện frame dở dang.
- Xử lý độ dài theo **số byte** và tránh lỗi khi chuỗi chứa ký tự Unicode nhiều byte.
- Dùng `DataInputStream.readFully()`, `DataOutputStream.writeInt()` và chính sách kích thước/timeout thích hợp.

## 1. Bản chất TCP: luồng byte, không có dấu kết thúc bản tin

Giả sử sender tạo hai bản tin:

~~~text
Ứng dụng gửi:  "HELLO"        "WORLD"
send/write:    [ H E L L O ]  [ W O R L D ]

Luồng byte TCP nhìn từ receiver:
               H E L L O W O R L D
~~~

Receiver có thể nhận theo nhiều cách, đều hợp lệ:

~~~text
Lần read 1:   HELLOWORLD
hoặc
Lần read 1:   HE
Lần read 2:   LLOW
Lần read 3:   ORLD
hoặc
Lần read 1:   H
Lần read 2:   E
...
~~~

**Không có lời hứa rằng một lần `InputStream.read(byte[])` trả toàn bộ frame, hoặc chỉ trả đúng một frame.** Lời gọi có thể trả ít hơn số byte mong muốn; lần đọc có thể thấy phần đuôi frame trước và phần đầu frame sau. Ở tầng truyền tải, TCP đảm bảo thứ tự byte và truyền lại dữ liệu khi có thể; ở tầng ứng dụng, **bạn phải tự xác định cấu trúc thông điệp**.

Không thể dùng kích cỡ gói IP, MTU, TCP segment, cờ PSH hay số lần `flush()` để suy ra ranh giới thông điệp. `flush()` chỉ đẩy dữ liệu đang được buffer bởi wrapper (nếu có) xuống tầng dưới, **không tạo dấu phân cách** trên luồng TCP.

### Hành vi của Java I/O cần nhớ

| API | Điều thực sự được đảm bảo | Không nên giả định |
| --- | --- | --- |
| `InputStream.read()` | Trả một byte 0–255 hoặc `-1` nếu EOF | `-1` có nghĩa kết thúc **frame**; thực ra nó là EOF của stream |
| `InputStream.read(byte[])` | Trả số byte đã đọc, có thể nhỏ hơn độ dài buffer; `-1` khi EOF | Một lần đọc luôn đủ dữ liệu ứng dụng cần |
| `DataInputStream.readFully(byte[])` | Lặp đọc tới khi đủ số byte yêu cầu hoặc ném `EOFException` | Nó biết kích thước bản tin; kích thước phải do protocol cung cấp |
| `DataInputStream.readInt()` | Đọc đúng bốn byte và diễn giải thành số nguyên có dấu big-endian | Đọc được prefix nghĩa là payload chắc chắn đã đến |
| `InputStream.available()` | Ước lượng byte có thể đọc ngay mà không bị block | Tổng kích thước frame hoặc toàn bộ dữ liệu sẽ đến |
| `InputStream.readAllBytes()` | Đọc đến EOF | Phù hợp cho một bản tin trên kết nối TCP duy trì lâu |
| `Socket.setSoTimeout(ms)` | Giới hạn thời gian chặn của các thao tác đọc socket; hết hạn ném `SocketTimeoutException` | Chỉ cần timeout là xác định được ranh giới frame |

**Ví dụ gây lỗi:** sender gọi `out.write(bytesOfA)` rồi `out.write(bytesOfB)`; receiver gọi `in.read(buffer)` một lần rồi tự cho buffer chứa đúng thông điệp A. Chương trình có thể “chạy được trên localhost” nhưng hỏng khi dữ liệu đến rời rạc hoặc nhiều thông điệp được gộp.

## 2. Framing là hợp đồng của protocol

Trước khi lập trình, hai phía cần thống nhất:

1. **Frame bắt đầu và kết thúc thế nào?** Cố định 4 byte, kết thúc bằng LF, hay có 4 byte đầu chỉ độ dài?
2. **Độ dài tính theo gì?** Với TCP luôn quy định cụ thể số byte trên wire, không mơ hồ là số ký tự Java.
3. **Dữ liệu mã hóa thế nào?** ASCII, UTF-8, binary, JSON? Có cho phép delimiter nằm trong payload không?
4. **Giới hạn tối đa là bao nhiêu?** Hạn chế bộ nhớ/CPU khi peer gửi độ dài hoặc chuỗi quá lớn.
5. **Đọc hết socket xử lý ra sao?** EOF ở giữa frame thường là lỗi/truncation; EOF đúng ranh giới frame có thể là đóng kết nối bình thường.
6. **Nhiều frame liên tiếp thì sao?** Phải tiếp tục đọc từ đúng byte sau frame trước, không làm rơi byte dư hoặc đọc nhầm sang frame khác.
7. **Lỗi protocol có được khôi phục không?** Với TCP, nếu parser bị lệch ranh giới và không thể đồng bộ lại an toàn, thường phải đóng kết nối.

Ba chiến lược nhìn trên wire:

~~~text
A. Độ dài cố định, N = 4 byte:
    [P I N G][P O N G]
     frame 1  frame 2

B. Dấu phân cách LF (byte 0A):
    [H E L L O 0A][W O R L D 0A]
     frame 1       frame 2

C. Tiền tố độ dài, header 4 byte big-endian:
    [00 00 00 05][H E L L O][00 00 00 05][W O R L D]
     length = 5   payload    length = 5   payload
~~~

Mỗi frame trong ví dụ được gửi liên tục trên cùng một TCP connection. Receiver phải đọc đúng theo format đã quy ước; TCP không thông báo “đã hoàn thành frame” cho ứng dụng.

## 3. Phương án 1: độ dài cố định (fixed-length framing)

Nếu mọi bản tin dài **chính xác N byte**, receiver chỉ việc đọc đủ N byte cho một frame rồi lặp lại:

~~~text
Protocol: mỗi thông điệp đúng 4 byte ASCII

Wire:   P I N G P O N G
        |-------|-------|
         frame 1  frame 2

READ_4_BYTES -> EMIT -> READ_4_BYTES -> EMIT -> ...
~~~

Trong Java, `DataInputStream.readFully(byte[])` là lựa chọn dễ hiểu cho giao thức này:

~~~java
// Snippet: dùng trong phương thức có quyền xử lý IOException.
DataInputStream input = new DataInputStream(socket.getInputStream());
byte[] frame = new byte[4];
input.readFully(frame); // Đọc đủ 4 byte hoặc ném EOFException.
~~~

**Điều kiện:** tất cả sender đều phải ghi đúng 4 byte cho mỗi frame; receiver đọc theo chính xác cùng N. Nếu sender gửi thiếu 1 byte rồi bắt đầu frame tiếp theo, receiver có thể lấy một byte đầu của frame kế tiếp để bù và mọi ranh giới về sau bị lệch.

Với bản tin có các trường cố định như `type(1 byte) + requestId(4 byte) + status(1 byte)`, một frame 6 byte có thể hợp lý. Nhưng nếu nội dung thực tế thay đổi độ dài, bạn phải định nghĩa rõ cách xử lý **padding**, byte đệm và quy tắc cắt phần đệm; việc cắt ngắn payload một cách tùy tiện gây mất dữ liệu.

### Ký tự không đồng nghĩa byte

Trong Java, `String.length()` đếm UTF-16 code units; không phải độ dài byte UTF-8. Ví dụ:

~~~java
String s = "cà";
System.out.println(s.length()); // 2 UTF-16 code units
System.out.println(s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
// 3 byte UTF-8: 'c' = 1 byte, 'à' = 2 byte
~~~

Vì vậy, giao thức **“4 byte”** không đồng nghĩa với **“4 ký tự”**. Nếu frame cố định chứa text UTF-8, chỉ cắt theo ranh giới byte hợp lệ và quy định padding rõ ràng; với dữ liệu text biến đổi độ dài thường nên ưu tiên delimiter hoặc length prefix.

**Ưu điểm:** parser đơn giản, overhead gần như bằng 0; thích hợp bản ghi binary có kích cỡ biết trước.  
**Nhược điểm:** lãng phí padding nếu bản tin ngắn; không linh hoạt với payload lớn/biến đổi; mất đồng bộ nếu các phía bất đồng N.

## 4. Phương án 2: ký tự hoặc chuỗi phân cách (delimiter framing)

Sender ghi payload rồi thêm **một delimiter được quy ước**, ví dụ newline LF `\n` (byte `0A`):

~~~text
Protocol: UTF-8 text, kết thúc mỗi frame bằng LF (0x0A)

Wire:   x i n ... 0A o k 0A
        |---------|------|
          frame 1  frame 2
~~~

Reader đọc từng byte hoặc dùng buffer giữ trạng thái, dừng khi gặp delimiter. Chỉ sau khi có một frame hoàn chỉnh mới chuyển byte payload sang chuỗi UTF-8. Nếu tự giải mã từng chunk trước khi ghép, một ký tự Unicode bị chia giữa hai lần đọc có thể thành dữ liệu lỗi.

Một ứng dụng line-based có thể dùng `BufferedReader.readLine()` nếu protocol thực sự là text và quy ước CR/LF/CRLF của Java phù hợp. Tuy nhiên `readLine()` loại bỏ ký tự kết thúc dòng; nó chấp nhận nhiều loại xuống dòng chứ không chỉ một byte LF, và `BufferedReader` có thể đọc trước qua ranh giới. **Không trộn trực tiếp `BufferedReader` với binary reader khác trên cùng một `Socket.getInputStream()`** nếu các buffer không được quản lý thống nhất.

### Khi delimiter xuất hiện trong payload

Giả sử protocol dùng LF để kết thúc, nhưng người dùng gửi:

~~~text
Dòng 1
Dòng 2
~~~

Nếu gửi thẳng chuỗi này với `\n`, receiver sẽ hiểu thành **hai frame**. Phải thống nhất một trong các cách:

- **Cấm delimiter** trong payload và validate khi gửi; ví dụ text command mỗi dòng.
- **Escape delimiter** theo ngữ pháp rõ ràng, chẳng hạn `\n` bên trong payload được chuyển thành hai ký tự literal `\` và `n`; reader phải unescape sau khi tìm ranh giới và xử lý cả ký tự escape.
- **Đóng gói payload** sao cho không chứa delimiter (ví dụ base64), chấp nhận overhead.
- **Đổi sang length-prefix** nếu payload là binary/JSON nhiều dòng hoặc có thể chứa mọi byte.

Không chỉ dùng `String.split("\n")` trên các chunk riêng lẻ nhận từ `read()`: delimiter có thể nằm ở ranh giới chunk; cần giữ phần dư giữa những lần đọc.

### Giới hạn và EOF

Reader nên đếm **byte payload** kể từ delimiter trước, đặt giới hạn, chẳng hạn tối đa 1 KiB. Nếu chưa thấy LF mà quá giới hạn, báo lỗi và thường đóng kết nối; không chờ vô hạn để buffer tăng mãi.

Phải định nghĩa rõ trường hợp:

| Dữ liệu nhận | Quy ước LF-only minh họa |
| --- | --- |
| `hello\n` | Một frame có payload `hello` |
| `\n` | Một frame rỗng (hợp lệ nếu protocol cho phép) |
| `hello\nok\n` | Hai frame liên tiếp |
| `hello` rồi TCP EOF | Frame dở dang; **lỗi protocol** |
| TCP EOF ngay sau `\n` hoặc khi chưa nhận byte nào | EOF tại ranh giới; có thể coi là kết thúc stream bình thường |

Với CRLF, delimiter phải là **hai byte** `0D 0A` và reader phải kiểm tra/loại bỏ theo đúng hợp đồng; đừng để byte `\r` lọt vào payload một cách tình cờ nếu protocol đòi CRLF.

**Ưu điểm:** dễ kiểm tra bằng telnet/netcat/log, linh hoạt với văn bản theo dòng, overhead nhỏ.  
**Nhược điểm:** yêu cầu escaping hoặc hạn chế payload; reader phải tìm delimiter và giới hạn kích thước; không lý tưởng cho binary không bị hạn chế ký tự.

## 5. Phương án 3: tiền tố độ dài (length-prefixed framing)

Trước mỗi payload, sender ghi header mang **số byte của payload**, rồi ghi đúng số byte đó. Ví dụ protocol dùng 4 byte độ dài **signed int big-endian** và payload UTF-8:

~~~text
Text:       "xin chào"
UTF-8:       9 byte

Frame:
    00 00 00 09 | 78 69 6E 20 63 68 C3 A0 6F
    -----------   --------------------------
    length = 9           UTF-8 payload
~~~

**Luồng nhận:**

1. Đọc **đủ 4 byte header**.
2. Diễn giải số nguyên 32-bit big-endian.
3. Kiểm tra `0 <= length <= MAX_FRAME_BYTES` **trước khi cấp phát** buffer.
4. Đọc **đủ `length` byte** bằng `readFully` hoặc vòng lặp tương đương.
5. Giải mã payload theo encoding đã thỏa thuận rồi xử lý message; tiếp tục đọc frame sau.

Trạng thái parser:

~~~text
[READ_HEADER_4]
      |
      v
[VALIDATE_LENGTH] -- lỗi (<0 hoặc >MAX) --> [REJECT/CLOSE]
      |
      v
[READ_EXACT_BODY_N] -- EOF giữa body --> [TRUNCATED/CLOSE]
      |
      v
[EMIT_MESSAGE]
      |
      +------------------------------> [READ_HEADER_4]
~~~

Java hỗ trợ sẵn network byte order của ví dụ này:

~~~java
// Snippet: dùng trong phương thức có throws/catch IOException.
byte[] body = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
DataOutputStream out = new DataOutputStream(socket.getOutputStream());
out.writeInt(body.length); // 4 byte big-endian.
out.write(body);

DataInputStream in = new DataInputStream(socket.getInputStream());
int length = in.readInt(); // Chỉ header: 4 byte.
if (length < 0 || length > 1024 * 1024) {
    throw new IOException("Invalid frame length");
}
byte[] received = new byte[length];
in.readFully(received); // Payload đủ byte, bất kể TCP chia thành bao nhiêu lượt.
~~~

Đây là **snippet minh họa hai đầu**: `out` và `in` trên cùng socket không có nghĩa chương trình đã thiết lập hai bên server/client hay giao thức request-response; các phần phải đặt vào logic mỗi phía theo đúng thứ tự. Mức 1 MiB chỉ là ví dụ, phải chọn theo hệ thống.

**Đếm độ dài sau khi encode:** `"xin chào"` có 8 ký tự Unicode nhìn thấy nhưng **9 byte UTF-8**. Header phải là `9` vì receiver đọc byte. Không dùng `String.length()` làm độ dài.

**Endianness và signedness:** `DataOutputStream.writeInt` và `DataInputStream.readInt` cùng dùng big-endian, nhưng các ngôn ngữ khác phải cấu hình giống hệt. Java `int` có dấu; nếu nhận giá trị âm hoặc lớn hơn giới hạn cho phép, từ chối ngay. Prefix có thể là `uint16`/`uint32`, varint hoặc kích thước khác, nhưng khi đó hai phía phải cùng đặc tả; không tự thay một đầu bằng định dạng khác.

**Ưu điểm:** phù hợp binary, JSON nhiều dòng, UTF-8 có delimiter nội bộ; biết chính xác lượng byte cần đọc, dễ truyền nhiều frame liên tiếp.  
**Nhược điểm:** có overhead prefix; phải validate độ dài trước khi allocate, xử lý header/body bị cắt và bảo vệ khỏi gửi kích thước không thực tế.

## 6. So sánh ba lựa chọn

| Tiêu chí | Độ dài cố định | Ký tự phân cách | Tiền tố độ dài |
| --- | --- | --- | --- |
| Cách nhận biết ranh giới | Đếm đúng `N` byte | Tìm byte/chuỗi delimiter | Đọc header rồi đúng số byte |
| Overhead | Không có (nhưng có thể phải padding) | Chi phí delimiter/escape | Kích cỡ header, ví dụ 4 byte |
| Payload độ dài biến đổi | Không thuận tiện | Có | Có |
| Chứa delimiter trong payload | Không thành vấn đề vì biết N | Phải escape/cấm/encode | Có thể chứa mọi byte |
| Dữ liệu binary | Tốt khi bản ghi cố định | Khó nếu delimiter có thể xuất hiện | Thích hợp |
| Text theo dòng | Hơi bất tiện | Rất tự nhiên | Thích hợp |
| Rủi ro nổi bật | Lệch ranh giới do sai N | Frame vô hạn nếu thiếu delimiter | Prefix giả rất lớn, cấp phát bộ nhớ |
| Parser cần giữ trạng thái | Còn bao nhiêu byte của N | Byte đang chờ delimiter + escaping | Header còn thiếu, length, body còn thiếu |

Gợi ý theo tình huống: lệnh nhỏ với đúng 4 byte dùng fixed; giao thức text gồm một lệnh/một dòng với LF và quy tắc escaping rõ ràng dùng delimiter; payload biến đổi hoặc binary hỗn hợp thường chọn length-prefix. Không có lựa chọn nào thay thế timeout và giới hạn tài nguyên.

## 7. Chương trình Java 17+: cùng một luồng nhưng đọc đúng ba kiểu framing

Ví dụ sau tạo nhiều frame liên tiếp bằng `ByteArrayOutputStream`, rồi đọc qua một `InputStream` giả lập **mỗi lần `read(byte[])` chỉ trả tối đa 1 byte**. Kỹ thuật này không tự tạo TCP thật, nhưng cho thấy parser vẫn hoạt động khi dữ liệu bị chia nhỏ như trường hợp TCP.

Tạo file **`FramingDemo.java`** (UTF-8):

~~~java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;

public class FramingDemo {
    private static final int FIXED_BYTES = 4;
    private static final int MAX_PAYLOAD = 1024;

    private static String strictUtf8(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    // Mỗi bản tin cố định đúng 4 byte.
    private static void writeFixed(OutputStream out, byte[] payload)
            throws IOException {
        if (payload.length != FIXED_BYTES) {
            throw new IllegalArgumentException("expected 4 bytes");
        }
        out.write(payload);
    }

    private static byte[] readFixed(DataInputStream in) throws IOException {
        byte[] payload = new byte[FIXED_BYTES];
        in.readFully(payload);
        return payload;
    }

    // Protocol LF-only; sender cấm CR/LF trong payload.
    private static void writeDelimited(OutputStream out, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        if (text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0
                || data.length > MAX_PAYLOAD) {
            throw new IllegalArgumentException("invalid LF record");
        }
        out.write(data);
        out.write('\n');
    }

    // null nghĩa là EOF đúng ranh giới, khi chưa có byte payload.
    private static String readDelimited(InputStream in) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();

        while (true) {
            int b = in.read();
            if (b < 0) {
                if (body.size() == 0) {
                    return null;
                }
                throw new EOFException("partial LF record");
            }
            if (b == '\n') {
                return strictUtf8(body.toByteArray());
            }
            if (body.size() >= MAX_PAYLOAD) {
                throw new IOException("record too large");
            }
            body.write(b);
        }
    }

    // Header 4 byte big-endian, chứa số byte UTF-8 của body.
    private static void writePrefixed(DataOutputStream out, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_PAYLOAD) {
            throw new IllegalArgumentException("message too large");
        }
        out.writeInt(data.length);
        out.write(data);
    }

    private static String readPrefixed(DataInputStream in)
            throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("invalid length");
        }
        byte[] body = new byte[length];
        in.readFully(body);
        return strictUtf8(body);
    }

    // Giả lập read(byte[]) chỉ trả nhiều nhất 1 byte.
    private static InputStream oneByteAtATime(byte[] bytes) {
        return new FilterInputStream(new ByteArrayInputStream(bytes)) {
            @Override
            public int read(byte[] b, int off, int len)
                    throws IOException {
                if (len == 0) {
                    return 0;
                }
                return super.read(b, off, Math.min(len, 1));
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream fixed = new ByteArrayOutputStream();
        writeFixed(fixed, "PING".getBytes(StandardCharsets.US_ASCII));
        writeFixed(fixed, "PONG".getBytes(StandardCharsets.US_ASCII));
        try (DataInputStream in = new DataInputStream(
                oneByteAtATime(fixed.toByteArray()))) {
            System.out.println("Fixed: "
                    + new String(readFixed(in), StandardCharsets.US_ASCII)
                    + " | "
                    + new String(readFixed(in), StandardCharsets.US_ASCII));
        }

        ByteArrayOutputStream delimited = new ByteArrayOutputStream();
        writeDelimited(delimited, "xin chào");
        writeDelimited(delimited, "ok");
        try (InputStream in = oneByteAtATime(
                delimited.toByteArray())) {
            System.out.println("Delimiter: "
                    + readDelimited(in) + " | " + readDelimited(in));
        }

        ByteArrayOutputStream prefixed = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(prefixed)) {
            writePrefixed(out, "xin chào");
            writePrefixed(out, "hi");
        }
        try (DataInputStream in = new DataInputStream(
                oneByteAtATime(prefixed.toByteArray()))) {
            System.out.println("Length-prefixed: "
                    + readPrefixed(in) + " | " + readPrefixed(in));
        }

        // Header khai báo 5 byte, nhưng payload chỉ có 2 byte.
        ByteArrayOutputStream cut = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(cut)) {
            out.writeInt(5);
            out.write(new byte[] {1, 2});
        }
        try (DataInputStream in = new DataInputStream(
                oneByteAtATime(cut.toByteArray()))) {
            readPrefixed(in);
        } catch (EOFException e) {
            System.out.println("Truncated: EOFException");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FramingDemo.java
java FramingDemo
~~~

Kết quả (terminal hỗ trợ UTF-8):

~~~text
Fixed: PING | PONG
Delimiter: xin chào | ok
Length-prefixed: xin chào | hi
Truncated: EOFException
~~~

**Điểm cần quan sát:**

- `writeFixed` yêu cầu chính xác 4 byte cho mỗi bản tin. `readFully` nhận đủ 4 byte dù `read(byte[])` bên dưới bị giới hạn về 1 byte.
- `writeDelimited` thêm LF, `readDelimited` dừng đúng LF và giữ các frame tiếp theo. Nó trả `null` khi EOF xảy ra giữa hai frame; EOF sau một phần payload ném `EOFException`.
- `writePrefixed` ghi **byte length** trước body; `readPrefixed` kiểm tra length rồi `readFully`. Bản tin UTF-8 có thể chứa ký tự nhiều byte.
- `strictUtf8` dùng decoder báo lỗi thay vì lặng lẽ thay các byte UTF-8 sai bằng ký tự `�`. Nó được áp dụng **sau khi** ghép đủ một frame.
- Dòng cuối chứng minh khi header nói 5 nhưng chỉ có 2 byte payload, reader **không được coi 2 byte đó là một message hợp lệ**.

Đây là phép thử **đọc stream bị chia nhỏ**, không mô phỏng toàn bộ hành vi của mạng (mất kết nối, latency, timeout, TLS, flow control). Nó kiểm tra được nguyên tắc quan trọng: parser không phụ thuộc kích thước mỗi lượt `read`.

## 8. Chạy length-prefix qua TCP loopback thật

Ví dụ sau dựng một `ServerSocket` trên loopback và một client kết nối đến đúng port được cấp tự động. Chúng sử dụng **cùng format 4-byte length prefix** rồi trao đổi một request và một response. Thread của server chỉ phục vụ một kết nối để minh họa. Không cần truy cập Internet.

Tạo file **`LengthPrefixTcpExample.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class LengthPrefixTcpExample {
    private static final int MAX_FRAME = 4096;

    private static void send(DataOutputStream out, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        if (body.length > MAX_FRAME) {
            throw new IllegalArgumentException("too large");
        }
        out.writeInt(body.length);
        out.write(body);
        out.flush();
    }

    private static String receive(DataInputStream in) throws IOException {
        int n = in.readInt();
        if (n < 0 || n > MAX_FRAME) {
            throw new IOException("invalid length");
        }
        byte[] body = new byte[n];
        in.readFully(body);
        return new String(body, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> handled = pool.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(3000);
                        DataInputStream in =
                                new DataInputStream(peer.getInputStream());
                        DataOutputStream out =
                                new DataOutputStream(peer.getOutputStream());
                        String request = receive(in);
                        send(out, "ACK: " + request);
                        return request;
                    }
                });

                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    client.setSoTimeout(3000);
                    DataOutputStream out =
                            new DataOutputStream(client.getOutputStream());
                    DataInputStream in =
                            new DataInputStream(client.getInputStream());
                    send(out, "xin chào");
                    System.out.println("Client got: " + receive(in));
                }

                System.out.println("Server got: " + handled.get());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LengthPrefixTcpExample.java
java LengthPrefixTcpExample
~~~

Output khi trao đổi trên loopback thành công:

~~~text
Client got: ACK: xin chào
Server got: xin chào
~~~

Hai chiều dùng **cùng format nhưng trên hai luồng ngược nhau**: client ghi request vào output của client; server đọc từ input của peer. Server sau đó ghi response; client đọc response. `flush()` giúp dữ liệu trong wrapper được đẩy xuống, nhưng không tạo frame; frame có ranh giới là `writeInt(length)` và `length` byte tiếp theo.

Trong code mẫu, `new String(body, UTF_8)` đủ để hiển thị payload hợp lệ đã gửi. Với đầu vào không tin cậy, nên tái dùng **strict decoder** từ `FramingDemo` hoặc cơ chế kiểm tra format/schema riêng. `setSoTimeout(3000)` ở đây đặt hạn chờ đọc 3 giây để demo tránh bị treo lâu; sản phẩm phải chọn timeout phù hợp latency và tải thực tế, xử lý `SocketTimeoutException`, đóng socket và dọn tài nguyên.

**Giới hạn của demo:** đây là request-response một lần, không phải server production có nhiều client, xác thực, TLS, thread pool giới hạn hay hệ thống retry. Các phần đó không thay đổi quy tắc framing: cả hai phía phải phân tích đúng cùng cấu trúc byte.

## 9. EOF, đọc thiếu và lỗi protocol

Trong một stream TCP có nhiều bản tin, **EOF là trạng thái của kết nối/chiều đọc**, không tự nhiên là dấu kết thúc bản tin. Quy tắc xử lý phải tùy vị trí đọc:

| Trạng thái đang đọc | Nhận EOF | Hành động thường đúng |
| --- | --- | --- |
| Chưa bắt đầu frame mới, đã xử lý xong mọi frame cũ | Kết nối được đóng có trật tự | Có thể kết thúc vòng đọc bình thường |
| Đang đợi đủ N byte fixed-length, mới nhận k byte với k < N | Frame bị cắt | Báo lỗi và ngừng xử lý |
| Đang đọc delimiter frame có một phần payload nhưng chưa thấy delimiter | Frame bị cắt | Báo lỗi |
| Mới nhận 1–3 trong 4 byte prefix | Header bị cắt | Báo lỗi |
| Đã đọc đủ prefix nhưng body ít hơn khai báo | Payload bị cắt | Báo lỗi |

`DataInputStream.readInt()` ném `EOFException` cả khi vừa bắt đầu đọc header mà peer đã đóng và khi header đang dở dang. Nếu ứng dụng cần phân biệt “EOF sạch giữa hai frame” với “header bị cắt”, có thể đọc byte đầu header riêng: `-1` ngay tại byte đầu là EOF sạch; nếu byte đầu tồn tại, yêu cầu **đủ phần header còn lại** bằng `readFully`. Hoặc protocol có thể quy định đóng kết nối bất ngờ ở mọi vị trí là lỗi.

`InputStream.readNBytes(length)` cũng có thể trả mảng ngắn hơn `length` khi chạm EOF; nếu dùng API này phải tự kiểm tra `result.length == length`. Đừng coi “đã đọc một ít” là thành công. Với socket duy trì mở, `readAllBytes()` thường chặn đến EOF, nên không dùng thay thế reader dựa trên frame.

### Timeout không tự xác định frame

`Socket.setSoTimeout(3000)` ngăn một số thao tác đọc socket chặn quá lâu (báo `SocketTimeoutException`), nhưng nó **không** có nghĩa “sau 3 giây là hết frame”. Nếu peer còn có thể gửi tiếp, kết luận framing phải đến từ fixed count, delimiter hoặc length. Timeout là cơ chế bảo vệ tài nguyên, thường đi kèm deadline tổng cho một frame, tốc độ tối thiểu (slow sender) và chính sách đóng kết nối.

Sau khi phát hiện prefix âm/khổng lồ, UTF-8 sai, delimiter bị thiếu hoặc payload không đúng schema, tránh cố đoán nơi frame sau bắt đầu. Khi stream mất đồng bộ, thường nên đóng kết nối và ghi log lỗi ở mức phù hợp; đừng đưa byte thừa vào parser khác một cách tùy tiện.

## 10. Kiểm soát bộ nhớ, hiệu năng và an toàn

### Giới hạn kích thước là bắt buộc

Một peer không tin cậy có thể gửi prefix `0x7fffffff` (2.147.483.647 byte) rồi không gửi payload. Nếu ứng dụng lập tức tạo `new byte[length]` mà không kiểm tra, nó có thể làm cạn bộ nhớ. Hãy:

- Kiểm tra `length >= 0`, `length <= MAX_FRAME_BYTES` trước khi cấp phát.
- Giới hạn **byte trước khi tìm delimiter**; không dùng `readLine()` trên nguồn không giới hạn kích thước mà thiếu cơ chế kiểm soát.
- Với payload lớn được cho phép, cân nhắc xử lý theo chunk lên stream/file thay vì giữ toàn bộ trong RAM, nhưng vẫn phải đếm đúng số byte để tách frame.
- Duy trì giới hạn số kết nối đồng thời, bộ nhớ tổng, queue và lượng công việc mỗi message.
- Đặt timeout và khả năng hủy đọc khi sender ngừng tiến triển.

### Chuyển text sang byte phải thống nhất

Dùng `StandardCharsets.UTF_8`, không phụ thuộc charset mặc định của máy. Chuyển text sang byte trước khi tính length prefix. Dữ liệu UTF-8 sai trên wire nên được xử lý theo policy rõ (từ chối hay thay thế), không âm thầm đổi ý nghĩa bản tin. Nếu có schema JSON/Protobuf khác, validation của schema diễn ra **sau khi** đã đọc chính xác payload.

### Đọc và ghi cùng socket có trạng thái

- Một TCP connection có **hai chiều byte stream** (input và output). Mỗi chiều có thể dùng framing riêng, nhưng hai bên phải biết protocol áp dụng.
- **Một reader sở hữu input stream** hoặc có một bộ điều phối phân phối byte. Hai thread cùng đọc `socket.getInputStream()` có thể lấy mất byte của nhau, làm hỏng frame.
- Nếu dùng `BufferedInputStream` hay `BufferedReader`, phải hiểu chúng **đọc trước**: không chuyển qua lại giữa parser khác nhau trên cùng nguồn mà không quản lý cùng một buffer.
- Khi nhiều thread cùng ghi lên một stream, chúng phải đồng bộ ở **cấp frame** để header A không bị chen vào body B. Chỉ `writeInt` và `write` riêng lẻ không làm cả frame thành thao tác atomic xuyên thread.
- `flush()` không phải message boundary và không bảo đảm peer đã xử lý. Chỉ protocol acknowledgement mới cho biết ứng dụng bên kia xác nhận đã nhận/xử lý đến bước nào.

### Khi nào cần thêm version, type hoặc checksum?

Trong protocol thực tế, header có thể gồm:

~~~text
[magic: 2 B][version: 1 B][type: 1 B][length: 4 B][payload: N B]
~~~

Đây vẫn là length-prefix, chỉ có header phong phú hơn. `magic` giúp nhận diện protocol, `version` hỗ trợ thay đổi format, `type` giúp phân loại message. Checksum ở tầng ứng dụng có thể kiểm tra payload theo nhu cầu riêng nhưng **không thay thế TLS** cho bảo mật và xác thực. Khi receiver không biết version/type, phải có quy tắc từ chối rõ ràng; không cố parse payload theo định dạng đoán chừng.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “Mỗi `write` là một message” | Receiver dính/gãy message khi TCP chia/gộp | Thiết kế framing trên luồng byte |
| Gọi `read(buffer)` một lần và không kiểm tra số byte trả về | Đọc thiếu hoặc lẫn message tiếp theo | Lặp đọc đến đủ frame hoặc delimiter |
| Dùng `available()` làm độ dài bản tin | Đọc dữ liệu tùy thời điểm, sai frame | Lấy độ dài từ protocol |
| Dùng `readAllBytes()` để đọc một message khi socket còn mở | Chờ EOF vô hạn | Đọc đến ranh giới frame |
| Ghi prefix bằng `String.length()` | Sai với Unicode UTF-8 nhiều byte | `getBytes(UTF_8).length` |
| Sender little-endian, receiver `readInt()` big-endian | Decode length sai | Quy định byte order nhất quán |
| Cấp phát `new byte[length]` trước khi kiểm tra | Dễ hết bộ nhớ với prefix độc hại | Kiểm tra 0 ≤ length ≤ max trước |
| Dùng LF delimiter nhưng payload có LF | Một message bị tách thành nhiều | Escape/cấm delimiter hoặc đổi protocol |
| Quên kiểm tra EOF giữa header/body | Coi frame dở dang là bản tin hoàn chỉnh | `readFully` và xử lý `EOFException` |
| Decode UTF-8 theo từng TCP chunk | Ký tự multibyte bị chia và lỗi | Ghép đủ frame rồi decode, hoặc dùng stateful decoder |
| Trộn `BufferedReader` và `DataInputStream` trên cùng input | Buffer đọc trước làm mất byte của parser kia | Một parser sở hữu stream và buffer |
| Nhiều writer ghi xen kẽ header/body | Byte của frame khác chen vào | Serialize/synchronize ở cấp frame |
| Nghĩ `flush` tương ứng packet/message hoàn chỉnh | Giao thức phụ thuộc chi tiết TCP | Tách frame bằng quy tắc ở application |
| Không giới hạn line/length | Bị giữ bộ nhớ hoặc chặn đọc lâu | Max frame, timeout, quota/backpressure |

## 12. Bài tập tự kiểm tra và đáp án

**Bài 1.** Sender gọi `write("HELLO")` rồi `write("WORLD")`. Receiver gọi `read(1024)` một lần. Có chắc nhận `HELLO` không?

**Đáp án:** Không. Receiver có thể nhận một phần, đúng 5 byte, cả 10 byte, hoặc số lượng byte khác tùy thời điểm và buffer. Phải dùng protocol framing để biết ranh giới.

**Bài 2.** Một fixed frame có N = 4 byte, receiver mới nhận `AB` rồi TCP EOF. Có nên trả về message `AB` không?

**Đáp án:** Không. Frame cần đúng 4 byte; EOF sau 2 byte là truncated frame.

**Bài 3.** Protocol LF-delimited nhận `one\ntwo\n` theo thứ tự nhưng qua 3 lần đọc `"on"`, `"e\nt"`, `"wo\n"`. Có bao nhiêu message?

**Đáp án:** Hai: `one` và `two`. Parser phải giữ phần payload giữa những lần đọc, không dùng số lần `read` để đếm message.

**Bài 4.** Payload UTF-8 là `xin chào` (8 ký tự người đọc nhìn thấy). Prefix 4-byte big-endian cần ghi giá trị nào?

**Đáp án:** `9`, vì payload có 9 **byte UTF-8**; tiền tố là `00 00 00 09`.

**Bài 5.** Nhận prefix khai báo 2 GiB trong khi giới hạn của hệ thống là 1 MiB. Reader nên làm gì?

**Đáp án:** Từ chối ngay sau khi kiểm tra header và đóng/xử lý lỗi theo protocol; tuyệt đối không cấp phát 2 GiB để chờ body.

**Bài 6.** Khi nào EOF có thể là bình thường với LF-delimited framing?

**Đáp án:** Khi EOF xảy ra **ngay giữa hai frame**, tức byte cuối của frame trước đã là LF và không còn payload dở dang. Nếu payload đã có nhưng chưa có LF thì đó là lỗi incomplete frame.

**Bài 7.** Có thể dựa vào `out.flush()` để biết receiver đã thấy một message hoàn chỉnh không?

**Đáp án:** Không. `flush` không truyền ranh giới ứng dụng hay acknowledgement. Receiver chỉ biết frame hoàn chỉnh khi parser đã thấy N byte, delimiter hoặc đủ header+body.

**Bài 8.** Khi một socket có hai worker cùng gọi `read` từ cùng `InputStream`, điều gì có thể xảy ra?

**Đáp án:** Mỗi worker có thể lấy một phần byte của frame mà worker kia đang parse, gây mất đồng bộ. Nên có một reader/dispatcher quản lý stream hoặc một cơ chế đồng bộ đủ chặt trên toàn bộ quá trình đọc frame.

## Tài liệu tham khảo

- [Java SE 21 — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): hợp đồng của `read`, `readNBytes`, `available` và `readAllBytes`.
- [Java SE 21 — `DataInputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html): `readFully`, `readInt`, EOF.
- [Java SE 21 — `DataOutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataOutputStream.html): `writeInt`, format big-endian.
- [Java SE 21 — `Socket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html) và [`ServerSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html): byte stream TCP, timeout và lifecycle.
- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293): TCP cung cấp dịch vụ luồng byte, không mang message boundary của ứng dụng.
