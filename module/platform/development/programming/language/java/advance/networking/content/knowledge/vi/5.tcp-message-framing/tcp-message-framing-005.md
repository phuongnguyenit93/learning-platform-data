# Mã hóa UTF-8 và xử lý ký tự bị chia giữa nhiều lần đọc trên TCP (Java 17+)

Một kết nối TCP chuyển **luồng byte**, không chuyển các ký tự Unicode hay “mỗi lần `write()` là một thông điệp”. UTF-8 lại biểu diễn một ký tự Unicode bằng **1–4 byte**. Vì vậy một lần `InputStream.read()` có thể kết thúc ngay ở giữa biểu diễn UTF-8 của ký tự; lần đọc kế tiếp mới chứa các byte còn lại. Nếu chuyển từng khối nhận được thành `String` độc lập, ứng dụng có thể biến dữ liệu hợp lệ thành ký tự thay thế `�`, làm sai JSON, chữ tiếng Việt hoặc nội dung nhắn tin.

Bài này giải thích hai ranh giới phải xử lý độc lập:

- **Ranh giới byte của TCP:** nơi các lời gọi `read()` tình cờ trả về; không bảo đảm trùng với lần `write()`, ký tự hay thông điệp.
- **Ranh giới Unicode và thông điệp ứng dụng:** decoder phải giữ trạng thái qua các khối byte, còn giao thức phải xác định đầy đủ một message trước khi xác nhận nó hợp lệ.

Ngữ cảnh thuộc **Thông điệp trên TCP**. Các ví dụ dùng `Socket`/`ServerSocket` Java 17+ trên loopback, không cần Internet hay thư viện ngoài.

## 1. UTF-8 biểu diễn ký tự thành byte như thế nào?

Unicode định danh ký tự bằng **code point**; Java `String` lưu dữ liệu bằng các **UTF-16 code unit** (`char`). UTF-8 chuyển mỗi Unicode scalar value thành dãy từ 1 đến 4 byte. Ba khái niệm không hoán đổi cho nhau:

| Khái niệm | Đơn vị | Ví dụ |
| --- | --- | --- |
| `String.length()` | Số code unit UTF-16 | Emoji ngoài BMP thường chiếm **2** `char` |
| `String.codePointCount(0, s.length())` | Số Unicode code point trong chuỗi Java | Một emoji như `😀` là **1** code point |
| `s.getBytes(UTF_8).length` | Số byte UTF-8 sau mã hóa | `😀` chiếm **4** byte |
| `InputStream.read(...)` | Số **byte** đã đọc | Không có khái niệm “đủ ký tự” |
| `Reader.read(...)` | Số **UTF-16 char** đã đọc | Có thể kết thúc giữa **cặp surrogate** của một code point ngoài BMP |

Với chuỗi `A€😀B`:

```text
Ký tự hiển thị:       A       €            😀                  B
Code point:          U+0041  U+20AC       U+1F600             U+0042
Byte UTF-8 (hex):    41      E2 82 AC     F0 9F 98 80        42

UTF-8 tổng cộng: 9 byte
Java String.length(): 5 char (A=1, €=1, 😀=2, B=1)
Số code point: 4
```

Các byte `E2 82 AC` cùng biểu diễn ký tự `€`. Các byte `F0 9F 98 80` cùng biểu diễn emoji `😀`. Ranh giới một lượt đọc TCP hoàn toàn có thể nằm ở bất kỳ vị trí nào trong những dãy này.

**Cảnh báo:** code point chưa chắc tương đương một *grapheme cluster* (ký tự người dùng nhìn thấy). Một chữ có dấu có thể được biểu diễn bằng code point đã tổng hợp hoặc bằng chữ cái + combining mark. UTF-8 stream decoding đúng vẫn không tự động làm Unicode normalization (NFC/NFD) hay tách cụm chữ để hiển thị.

## 2. Tại sao ký tự có thể bị cắt giữa hai lần `read()`?

TCP giữ **thứ tự byte** trong một chiều kết nối, nhưng không giữ ranh giới giữa các `write()`. Hai lần ghi có thể được gộp khi nhận; một lần ghi có thể được tách thành nhiều lần đọc; một lần đọc có thể trả về ít byte hơn kích thước buffer.

Giả sử phía gửi đã mã hóa chính xác `A€😀B` thành 9 byte. Phía nhận tình cờ đọc thành ba khối:

```text
Lần đọc 1: 41 E2              ("A" và byte đầu của "€")
Lần đọc 2: 82 AC F0 9F        (2 byte cuối "€", 2 byte đầu "😀")
Lần đọc 3: 98 80 42           (2 byte cuối "😀", "B")
Ghép byte:  41 E2 82 AC F0 9F 98 80 42
Đúng:       A  €        😀          B
```

Không khối nào của ví dụ bị TCP “gửi sai”: dãy byte ghép lại vẫn nguyên vẹn, đúng thứ tự. **Sai sót xảy ra ở tầng ứng dụng** nếu mỗi khối được giả định là một chuỗi UTF-8 hoàn chỉnh.

Đừng suy ra số byte đọc bằng số byte đã `write`, số byte của UTF-8 bằng `String.length()`, hay ngưỡng kết thúc ký tự từ `InputStream.available()`.

## 3. Lỗi phổ biến: `new String(chunk, UTF_8)` ở mỗi vòng đọc

Đoạn sau là **mã minh họa chưa hoàn chỉnh** (giả định `in` là một `InputStream` đang kết nối):

```java
byte[] buffer = new byte[4096];
int count;
StringBuilder text = new StringBuilder();

while ((count = in.read(buffer)) != -1) {
    // SAI khi byte UTF-8 của một ký tự bị chia giữa hai lần read():
    text.append(new String(
            buffer, 0, count, StandardCharsets.UTF_8));
}
```

Mỗi lần gọi `new String(byte[], off, len, charset)` diễn giải **một tập byte như một đơn vị giải mã hoàn chỉnh**. Nếu khối kết thúc với tiền tố của ký tự UTF-8 còn thiếu byte, bộ giải mã lần đó không giữ phần còn dang dở cho lần sau. Với nhiều API String decoding thông thường, dữ liệu malformed được **thay bằng ký tự thay thế U+FFFD**; vì vậy thông điệp cuối bị hỏng dù các byte TCP có đủ.

```text
Khối 1: 41 E2         -> "A�"       (E2 thiếu 82 AC)
Khối 2: 82 AC F0 9F   -> "��..."    (bắt đầu bằng continuation bytes)
Khối 3: 98 80 42      -> "��B"
Nối các chuỗi này không thể khôi phục lại "A€😀B".
```

Số lượng ký tự `�` cụ thể có thể phụ thuộc decoder và cách dữ liệu bị phân chia. Điều cần khẳng định là **giải mã độc lập từng chunk không bảo toàn ký tự bị cắt giữa chunk**.

Ngay cả khi thấy text đúng ở môi trường thử nghiệm, đó có thể chỉ là vì thời điểm nhận vô tình trùng ranh giới UTF-8. Thay đổi buffer, tải mạng, proxy hoặc lịch CPU có thể khiến lỗi xuất hiện.

## 4. Cách 1: dùng `InputStreamReader` để giải mã liên tục

`InputStreamReader` nối byte stream với character stream. Nó sử dụng decoder liên tục trên các lượt đọc; các byte UTF-8 chưa tạo thành ký tự hoàn chỉnh có thể được giữ lại để ghép với byte nhận tiếp theo. Đây là lựa chọn thuận tiện khi **toàn bộ luồng** là văn bản UTF-8 và bạn có quy tắc xác định kết thúc luồng/message.

```java
// Đoạn minh họa (in là InputStream, không phải class độc lập).
try (Reader reader =
             new InputStreamReader(in, StandardCharsets.UTF_8)) {
    char[] chars = new char[2048];
    int n;
    while ((n = reader.read(chars)) != -1) {
        // Chỉ dùng chars[0..n), có thể chứa một phần cặp surrogate.
        processChars(chars, n);
    }
}
```

`processChars` trong đoạn này là hàm do ứng dụng định nghĩa, không phải API Java có sẵn. **Đừng lập tức xử lý từng lượt `Reader.read` như một message hoàn chỉnh.** `Reader` giải quyết biên giữa các byte UTF-8, nhưng một lượt đọc `char[]` vẫn có thể tách một *surrogate pair* thành hai đoạn `char`: nếu yêu cầu xử lý theo code point, bạn phải giữ surrogate còn dang dở hoặc ghép đủ chuỗi rồi duyệt bằng `codePoints()`.

Ví dụ minh họa sử dụng `try-with-resources` vì đầu vào được xem là **stream hoàn chỉnh kết thúc bằng EOF**. Trên kết nối TCP giữ mở để trao đổi nhiều message, không nên dùng EOF làm điều kiện kết thúc từng message; bạn cần framing của giao thức ở phần sau. Cũng không nên đóng `Reader` nếu vẫn cần dùng tiếp socket: đóng reader sở hữu stream có thể đóng stream/socket nền.

## 5. Ví dụ Java 17+ chạy được: nhận UTF-8 bị chia ở giữa ký tự

Tệp **`Utf8SplitTcp.java`** tạo một cặp socket loopback. Phía gửi viết 9 byte thành ba phần, đúng tại vị trí làm vỡ `€` và `😀`. Phía nhận dùng một wrapper cố ý giới hạn mỗi thao tác `InputStream.read(byte[], off, len)` xuống tối đa **1 byte**, khiến decoder thường xuyên phải chờ byte tiếp theo.

```java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class Utf8SplitTcp {
    public static void main(String[] args) throws Exception {
        String expected = "A\u20AC\uD83D\uDE00B";
        byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);

        String broken =
                new String(utf8, 0, 2, StandardCharsets.UTF_8)
                + new String(utf8, 2, 4, StandardCharsets.UTF_8)
                + new String(utf8, 6, 3, StandardCharsets.UTF_8);

        try (ServerSocket listener = new ServerSocket(
                     0, 1, InetAddress.getLoopbackAddress());
             Socket sender = new Socket(
                     InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket receiver = listener.accept()) {

            OutputStream output = sender.getOutputStream();
            output.write(utf8, 0, 2);
            output.write(utf8, 2, 4);
            output.write(utf8, 6, 3);
            sender.shutdownOutput();

            InputStream oneBytePerRead =
                    new FilterInputStream(receiver.getInputStream()) {
                        @Override
                        public int read(byte[] b, int off, int len)
                                throws IOException {
                            return super.read(b, off, Math.min(len, 1));
                        }
                    };

            InputStreamReader decoder = new InputStreamReader(
                    oneBytePerRead, StandardCharsets.UTF_8);
            StringBuilder decoded = new StringBuilder();
            char[] chars = new char[2];
            int n;
            while ((n = decoder.read(chars)) != -1) {
                decoded.append(chars, 0, n);
            }

            System.out.println("UTF-8 bytes: " + utf8.length);
            System.out.println("Java char units: " + expected.length());
            System.out.println("Unicode code points: "
                    + expected.codePointCount(0, expected.length()));
            System.out.println("Decode each chunk correct: "
                    + expected.equals(broken));
            System.out.println("Streaming decode correct: "
                    + expected.contentEquals(decoded));
        }
    }
}
```

Chạy với JDK 17+:

```sh
javac -encoding UTF-8 Utf8SplitTcp.java
java Utf8SplitTcp
```

Stdout xác định:

```text
UTF-8 bytes: 9
Java char units: 5
Unicode code points: 4
Decode each chunk correct: false
Streaming decode correct: true
```

Giải thích:

1. `broken` giải mã ba `byte[]` slice **độc lập** nên không thể tái lập chuỗi gốc.
2. `InputStreamReader` duy trì trạng thái qua các lần lấy byte; code dùng một decoder cho cả stream, rồi nối các `char` đã giải mã theo thứ tự.
3. Chương trình in **đúng sai bằng Boolean** thay vì phụ thuộc terminal hỗ trợ hiển thị emoji và tiếng Việt.
4. Các lần gọi `write` không cam kết cùng ranh giới `read`. Wrapper một-byte-per-read là phép thử cố ý để kiểm tra tình huống khắc nghiệt, **không có nghĩa TCP thực tế luôn giao 1 byte/lần**.

Ví dụ chỉ gửi một nội dung, sau đó `shutdownOutput()` để bên nhận có thể đọc tới EOF. Cách này thích hợp cho demo nhưng **không đủ làm giao thức nhiều message** khi hai phía phải giữ socket mở.

## 6. Cách 2: có ranh giới message thì ghép **đúng byte** trước khi giải mã

Nếu ứng dụng truyền các message độc lập trên cùng kết nối, cần giao thức phân khung (**framing**) như **length-prefix** hoặc delimiter có escaping/giới hạn. Với length-prefix:

```text
+-------------------------+-----------------------------------+
| Header: 4 byte length N | Body: chính xác N byte UTF-8       |
+-------------------------+-----------------------------------+
  readInt()                readFully(byte[N]) -> UTF-8 decode once
```

Quy trình nhận an toàn:

1. Đọc đủ header theo đúng định dạng: `DataInputStream.readInt()` nhận số nguyên 32-bit big-endian, giống `DataOutputStream.writeInt()`.
2. Kiểm tra `0 <= N <= MAX_FRAME_BYTES` theo chính sách của ứng dụng **trước khi cấp phát**.
3. `readFully(payload)` lấy **đúng N byte** qua bao nhiêu lần đọc TCP cũng được, hoặc báo `EOFException` nếu stream kết thúc khi frame còn thiếu.
4. Chỉ khi body hoàn chỉnh, thực hiện giải mã `UTF-8`. Với dữ liệu không đáng tin, dùng `CharsetDecoder` ở chế độ `REPORT` để bác bỏ byte UTF-8 malformed thay vì âm thầm thay bằng `�`.
5. Lặp lại cho frame kế tiếp. Framing giải quyết **ranh giới thông điệp**, decoder giải quyết **ranh giới Unicode**.

**Độ dài header phải là số byte UTF-8**, không phải `String.length()` hay số code point. Ví dụ `"Xin chào"` có 8 UTF-16 code unit nhưng 9 byte UTF-8, do `à` chiếm 2 byte.

Hai chiều giao thức phải đồng thuận kiểu integer, byte order, kích thước tối đa, số frame và cách xử lý EOF. TCP không cung cấp các quy ước đó hộ ứng dụng.

## 7. Ví dụ Java 17+ chạy được: 2 frame UTF-8 và kiểm tra byte malformed

Tệp **`Utf8FramedMessages.java`** gửi hai message trên một kết nối TCP loopback, cùng kiểu 4-byte length-prefix. Bên nhận giới hạn body 1024 byte, đọc toàn bộ frame và dùng `CharsetDecoder` strict. Sau hai frame, sender half-close chiều gửi; client nhận xác nhận EOF. Chương trình còn chủ động thử một dãy UTF-8 bị cắt mất byte cuối để kiểm tra decoder strict báo lỗi.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class Utf8FramedMessages {
    private static final int MAX_FRAME_BYTES = 1024;

    private static void writeFrame(DataOutputStream out, String message)
            throws IOException {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame too large");
        }
        out.writeInt(payload.length);
        out.write(payload);
    }

    private static String strictDecode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return strictDecode(payload);
    }

    public static void main(String[] args) throws Exception {
        String first = "Xin chào";
        String second = "\uD83D\uDE00: OK";

        try (ServerSocket listener = new ServerSocket(
                     0, 1, InetAddress.getLoopbackAddress());
             Socket sender = new Socket(
                     InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket receiver = listener.accept()) {

            sender.setSoTimeout(5000);
            receiver.setSoTimeout(5000);

            DataOutputStream out =
                    new DataOutputStream(sender.getOutputStream());
            writeFrame(out, first);
            writeFrame(out, second);
            out.flush();
            sender.shutdownOutput();

            DataInputStream in =
                    new DataInputStream(receiver.getInputStream());
            String received1 = readFrame(in);
            String received2 = readFrame(in);

            System.out.println("Frames: 2");
            System.out.println("First UTF-8 bytes: "
                    + first.getBytes(StandardCharsets.UTF_8).length);
            System.out.println("Payloads match: "
                    + (first.equals(received1) && second.equals(received2)));
            System.out.println("EOF after frames: " + (in.read() == -1));
        }

        byte[] truncated = {(byte) 0xE2, (byte) 0x82};
        try {
            strictDecode(truncated);
            System.out.println("Truncated rejected: false");
        } catch (CharacterCodingException expected) {
            System.out.println("Truncated rejected: true");
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 Utf8FramedMessages.java
java Utf8FramedMessages
```

Stdout xác định trên một lần chạy bình thường:

```text
Frames: 2
First UTF-8 bytes: 9
Payloads match: true
EOF after frames: true
Truncated rejected: true
```

Chú ý:

- `writeFrame` gửi **4 byte header rồi toàn bộ body**. Không có yêu cầu TCP phải trả từng frame bằng một lượt đọc.
- `readFully` xử lý trường hợp body bị chia thành nhiều lượt nhận. Nếu kết nối kết thúc giữa frame, exception được ném thay vì trả về message bị cắt.
- `strictDecode` dùng `CodingErrorAction.REPORT`; dãy hai byte `E2 82` thiếu byte kết thúc của ký tự ba byte, nên **bị từ chối** khi coi đó là toàn bộ message.
- `setSoTimeout(5000)` đặt timeout cho một thao tác đọc socket blocking, không bảo đảm tổng thời gian end-to-end của nhiều lần đọc bằng 5 giây.
- `shutdownOutput()` đóng chiều gửi sau các frame; nó **không phải** dấu kết thúc message của mọi giao thức và không mang ngữ nghĩa “nghiệp vụ đã xử lý thành công”.

Ví dụ gửi các chuỗi Java `String` hợp lệ. Nếu nguồn ký tự có **surrogate không ghép cặp** (UTF-16 malformed), `String.getBytes(UTF_8)` thông thường có thể thay thế dữ liệu đầu vào; muốn **từ chối đầu vào lỗi ngay ở chiều gửi**, dùng `CharsetEncoder` với `onMalformedInput(REPORT)` và xử lý `CharacterCodingException` trước khi gửi. Việc decode strict ở chiều nhận **không khôi phục được** ký tự đã bị thay ở phía gửi.

## 8. Giải mã tăng dần bằng `CharsetDecoder` khi cần xử lý stream phức tạp

`InputStreamReader` đã phù hợp cho đa số text stream. Khi dùng NIO/`SocketChannel`, muốn kiểm soát buffer, trạng thái lỗi, non-blocking I/O hoặc giải mã dần các mảnh byte từ một parser riêng, sử dụng **một** `CharsetDecoder` xuyên suốt luồng logic.

Một decoder có trạng thái có thể gặp ba kết quả:

| `CoderResult` | Ý nghĩa | Phản ứng phù hợp |
| --- | --- | --- |
| `UNDERFLOW` | Đã dùng hết byte hiện có **hoặc** còn tiền tố UTF-8 chờ byte mới | Giữ byte chưa tiêu thụ; lấy thêm byte, không reset decoder |
| `OVERFLOW` | `CharBuffer` đầu ra đã đầy | Lấy/xử lý ký tự đã giải mã và cấp chỗ trống rồi decode tiếp |
| Error (`malformed`/`unmappable`) | Dữ liệu không hợp lệ theo `CodingErrorAction.REPORT` | Từ chối frame/stream theo chính sách giao thức |

Quy tắc buffer trong một vòng decoder liên tục:

```text
1. Nạp byte mới vào ByteBuffer ở WRITE mode.
2. flip(): chuyển sang READ mode.
3. decoder.decode(input, output, endOfInput=false).
4. Xử lý output chars và OVERFLOW nếu có.
5. input.compact(): giữ phần byte CHƯA ĐƯỢC decoder tiêu thụ.
6. Chờ byte tiếp theo, lặp lại.
7. Chỉ khi stream/frame thật sự kết thúc: decode(..., true), rồi flush(output).
```

**`compact()` rất quan trọng:** nó dồn phần byte chưa tiêu thụ về đầu buffer, không vứt byte UTF-8 dở dang. Nếu bạn `clear()` khi decoder chưa ăn hết byte, ký tự bị mất. Nếu bạn gọi `decode(..., true)` ở cuối **mỗi** lần `Socket.read()`, decoder sẽ coi một tiền tố UTF-8 đang chờ là *kết thúc stream* và có thể báo malformed không đúng lúc.

Với message length-prefix đã có **đầy đủ byte**, giải mã một lần với `CharsetDecoder.decode(ByteBuffer.wrap(payload))` thường đơn giản và an toàn hơn tự viết vòng buffering. Đừng thêm state machine khi `InputStreamReader` hoặc `readFully` đáp ứng giao thức.

## 9. Encoding và framing nên đặt theo thứ tự nào?

**Chiều gửi:** xây dựng message logic → xác định/chuẩn hóa nội dung theo quy ước → mã hóa UTF-8 thành byte → tính `payload.length` → gửi header → gửi body.

**Chiều nhận:** đọc frame header ở cấp byte → đọc đúng body ở cấp byte → giải mã UTF-8 (strict nếu cần) → parse dữ liệu text/JSON → xác thực nội dung → xử lý nghiệp vụ.

Sơ đồ:

```text
Sender:
String ──UTF-8 encode──> byte[] ──length prefix──> TCP byte stream

Receiver:
TCP byte stream ──read length──> N bytes ──UTF-8 decode──> String
                                      └── EOF sớm? -> frame lỗi
                                      └── UTF-8 lỗi? -> reject frame
```

Một lỗi thực tế là lấy một `InputStreamReader`/`BufferedReader` để đọc header text, rồi quay sang `Socket.getInputStream()` để đọc body nhị phân trên cùng kết nối. Reader có thể **đọc trước (read-ahead)** nhiều byte từ stream gốc để đệm/giải mã, khiến byte của body đã nằm trong buffer reader, không còn ở chỗ raw input code mong đợi. Vì vậy cần **một parser nhất quán** cho toàn bộ wire format, hoặc một tầng buffering được thiết kế để chia sẻ hợp lệ.

Nếu giao thức thực sự **text-delimited** như các dòng kết thúc bằng LF, có thể dùng `BufferedReader.readLine()` sau `InputStreamReader` UTF-8. Nhưng phải giới hạn độ dài dòng, định nghĩa escape/delimiter và cách xử lý line kết thúc không có LF; `readLine()` không tự có giới hạn độ dài, có thể đợi vô hạn khi peer không gửi newline.

## 10. Kết thúc stream, frame dở dang và lỗi UTF-8: phân biệt ba tình huống

**Tình huống A: TCP chia ký tự nhưng còn gửi tiếp.** Byte UTF-8 chưa hoàn chỉnh ở cuối một lần `read` là **bình thường**. Stateful decoder đợi byte kế; không gắn lỗi cho phần tiền tố này.

**Tình huống B: frame được khai báo N byte, nhưng chỉ nhận dưới N byte rồi EOF.** Đây là **frame bị cắt**. `readFully` ném `EOFException`. Không nên diễn giải dữ liệu thiếu là message hợp lệ, ngay cả khi phần đã đọc có thể giải mã thành một chuỗi.

**Tình huống C: frame có đủ N byte nhưng body UTF-8 bị malformed hoặc kết thúc bằng prefix dở dang.** Đây là **lỗi encoding của message**. Strict decoder báo lỗi; replacement decoder có thể tạo `�` và che mất việc dữ liệu đầu vào không hợp lệ.

EOF của `InputStream.read()` là `-1` **sau khi đã đọc hết dữ liệu** và chiều gửi đã kết thúc theo trạng thái bình thường. Khi peer reset hoặc kết nối lỗi, bạn có thể nhận `IOException` thay vì EOF. **Timeout không phải EOF**: `SocketTimeoutException` nói không có tiến triển trong khoảng chờ của thao tác đọc; không chứng minh message hoàn chỉnh hay peer đã hủy nó.

Thực tế production cần quy định rõ khi nào đóng kết nối sau frame malformed, có trả mã lỗi ứng dụng hay không, và có cho phép thử lại message đó không.

## 11. Unicode ngoài BMP, cặp surrogate và chữ có dấu

UTF-8 biểu diễn một Unicode scalar value với 1–4 byte; Java `char` là đơn vị 16 bit của UTF-16. Ví dụ emoji `😀`:

```text
Unicode code point: U+1F600
UTF-8:  F0 9F 98 80          (4 byte)
UTF-16: D83D DE00            (2 Java char / surrogate pair)
```

Sau giải mã UTF-8 đúng, `Reader.read(char[])` vẫn có thể trả về một đoạn `char` chứa **high surrogate** mà low surrogate xuất hiện ở lần đọc sau. Nếu bạn nối các `char` theo thứ tự rồi dùng toàn bộ `String`, cặp surrogate có thể được ghép đúng. Nhưng nếu ứng dụng chuyển **mỗi mảnh `char[]`** sang JSON, kiểm tra “mỗi char là ký tự” hoặc đếm emoji bằng `String.length()`, vẫn mắc lỗi ranh giới.

Để duyệt code point khi đã có message trọn vẹn:

```java
// Minh họa, không phải chương trình độc lập.
String message = "A\u20AC\uD83D\uDE00B";
long count = message.codePoints().count(); // 4 code point
message.codePoints().forEach(cp -> {
    // Mỗi cp biểu diễn một Unicode code point (int).
});
```

`String.codePoints()` xử lý cặp surrogate hợp lệ trong chuỗi; việc một văn bản trông giống nhau nhưng có code point khác nhau (NFC/NFD) vẫn là vấn đề Unicode normalization riêng, **không phải lỗi TCP split read**. Nếu giao thức cần chuẩn hóa để so sánh định danh, phải thống nhất chính sách và bảo mật của việc chuẩn hóa.

## 12. Chọn cơ chế xử lý theo loại ứng dụng

| Giao thức / yêu cầu | Cách xử lý nên ưu tiên | Lưu ý |
| --- | --- | --- |
| Một text stream UTF-8 kết thúc khi peer half-close | Một `InputStreamReader` xuyên suốt stream | Đọc đến EOF; giới hạn tổng độ dài/duration |
| Nhiều message trên một TCP connection | Framing length-prefix/delimiter trước | Không dùng số lần `read` để đo message |
| Length-prefix chứa body UTF-8 | `DataInputStream.readFully` + `CharsetDecoder` cho **từng frame đã đầy đủ** | Giới hạn byte length, strict decoding nếu cần |
| NIO, stream không đồng bộ, parser binary/text phức tạp | `CharsetDecoder` stateful với `ByteBuffer.compact` | Không reset/`endOfInput=true` giữa chunk |
| Dòng UTF-8 phân tách LF | `BufferedReader` + giới hạn dòng tại protocol/parser | `readLine` có thể read-ahead và không giới hạn độ dài |
| Dữ liệu UTF-8 có thể chứa byte malformed | `CodingErrorAction.REPORT` | Xác định cách thông báo lỗi và chính sách drop |
| Giao thức tương tác giữ socket mở | Framing có điểm kết thúc độc lập EOF | Timeouts và backpressure theo message |

Một giao thức chỉ cần “đọc tới EOF rồi mới giải mã” chỉ đúng khi **EOF chính là mốc kết thúc dữ liệu đã được định nghĩa**; nếu peer giữ socket mở chờ phản hồi, bên đọc đợi EOF có thể tạo deadlock nghiệp vụ.

## 13. Sai lầm dễ gặp khi debug lỗi tiếng Việt qua TCP

1. **“TCP làm mất nửa ký tự tiếng Việt.”** Nếu tất cả byte cuối cùng đến đủ, TCP không làm mất ký tự: ứng dụng đang giải mã mỗi chunk riêng hoặc bỏ phần byte còn dang dở.
2. **“`read(buffer)` một lần phải đủ message.”** Sai; `read` trả những byte hiện có, có thể rất ít. Hãy làm framing trước khi parse.
3. **“`new String(buffer, UTF_8)` xử lý toàn bộ buffer.”** Nó có thể đọc cả **byte cũ** trong vùng không được overwrite ở lần đọc này. Luôn dùng đúng `buffer, 0, n`; tuy nhiên ngay cả khi dùng `n` vẫn **sai** nếu decoding từng chunk độc lập.
4. **“Gửi length bằng `String.length()`.”** Sai nếu header mô tả byte length UTF-8; có dấu/emoji thì số byte khác số `char`.
5. **“`new String` không ném lỗi nên byte hợp lệ.”** Sai: decoder mặc định có thể dùng ký tự thay thế U+FFFD. Dùng strict decoder nếu dữ liệu malformed phải bị từ chối.
6. **“EOF giữa ký tự giống EOF sau message.”** Sai: EOF giữa một frame hoặc giữa UTF-8 sequence có thể nghĩa là thông điệp hỏng; tách lỗi EOF/framing/charset.
7. **“`Reader` luôn trả cả code point.”** Sai: API đọc `char`, có thể chia một surrogate pair; ứng dụng xử lý theo code point phải giữ cặp.
8. **“UTF-8 trên cả hai phía là đủ.”** Chưa: hai phía còn phải thống nhất **framing, cấu trúc payload, byte order của header, giới hạn kích thước và quy tắc lỗi**.
9. **“`available() == 0` là kết thúc message.”** Sai; đó không phải message boundary và không báo peer sẽ không gửi tiếp.
10. **“Sau khi đọc header bằng Reader có thể dùng raw InputStream để lấy body ngay.”** Có thể sai vì reader đã read-ahead. Thiết kế một parser xuyên suốt.

## 14. Quy trình tự kiểm chứng một lỗi cắt byte trong thực tế

Khi server nhận JSON, tiếng Việt hay emoji bị chuyển thành `�`, hãy kiểm tra tuần tự:

1. **Chụp bytes ở cả hai đầu** (ví dụ hex trong môi trường test, tránh log dữ liệu nhạy cảm). So sánh byte mà sender tạo ra với byte receiver ghép lại *trước decoding*.
2. Nếu bytes hai phía bằng nhau, vấn đề thường ở **decoder, charset hoặc framing**. Kiểm tra có `new String` ở mỗi `read` hay không và có dùng đúng số byte `n` không.
3. Cố ý thử nhiều biên read: 1 byte mỗi lượt; cắt trong 2-byte (`C3 A9`), 3-byte (`E2 82 AC`), 4-byte (`F0 9F 98 80`) sequence; ghép lại phải giữ nguyên text.
4. Kiểm tra ứng dụng tính header theo `payload.length`, giới hạn payload trước cấp phát và dùng `readFully`/vòng lặp đọc đủ N byte.
5. Thử **truncated frame**, **invalid continuation byte**, **overlong encoding**, **lone surrogate ở input Java**, EOF và timeout; quan sát các lỗi phải được phân loại rõ.
6. Kiểm tra kích thước `String` bằng `length()` và số code point bằng `codePointCount` để phân biệt bug UTF-16 với bug network.
7. Đo lại với buffer nhỏ/lớn và socket đọc nhiều lượt; kết quả **nội dung** phải bất biến, chỉ số lượt đọc/timing có thể đổi.

Với test tự động, so sánh **dữ liệu cuối cùng** và số frame, tránh assert “mỗi `read` trả đúng X byte”. Đó là kiểm tra hành vi thật sự của giao thức.

## 15. Ghi nhớ cốt lõi

- **TCP bảo toàn thứ tự của byte stream, không bảo toàn ranh giới UTF-8 hay message.**
- **UTF-8 1–4 byte mỗi code point; Java `char` là UTF-16 16-bit.** Đếm byte để tạo length-prefix; đếm code point nếu muốn đếm code point.
- **Không giải mã mỗi chunk TCP thành `String` độc lập** nếu chunk có thể cắt giữa ký tự. Dùng `InputStreamReader`/decoder stateful hoặc ghép đủ byte của một frame rồi decode.
- **EOF/timeout/malformed là ba tình huống riêng.** Không bỏ qua dữ liệu thiếu hoặc thay thế ký tự lỗi một cách vô thức.
- **Luôn tách framing khỏi decoding.** Một parser biết “đã nhận đủ message” mới có cơ sở trả dữ liệu text hợp lệ cho logic ứng dụng.

Tài liệu API để tra cứu: [Java SE 17 `InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html), [`DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [RFC 3629 — UTF-8](https://www.rfc-editor.org/rfc/rfc3629).