# CharsetDecoder và CharsetEncoder khi chuyển đổi dữ liệu tăng dần trong Java NIO

**Chủ đề:** Java Advance - networking  
**Nhóm:** Buffer và channel

Trong mạng TCP, một lần **SocketChannel.read(...)** hoặc **InputStream.read(...)** chỉ nhận **một phần byte đang có**, không bảo đảm đúng một ký tự hoặc một thông điệp. Nếu mã hóa là UTF-8, ký tự **€** chiếm 3 byte; emoji **😄** chiếm 4 byte. Một lần đọc có thể dừng ngay sau byte đầu tiên của ký tự. Tương tự, Java lưu văn bản trong **UTF-16 code units**: một emoji thường gồm **hai char** (surrogate pair), và hai phần có thể nằm ở hai lượt cung cấp dữ liệu khác nhau cho bộ mã hóa.

**java.nio.charset.CharsetDecoder** chuyển dần **byte → char**; **CharsetEncoder** chuyển dần **char → byte**. Khác với việc gọi **new String(chunk, UTF_8)** hay **text.getBytes(UTF_8)** cho từng mảnh độc lập, hai bộ chuyển đổi này lưu **trạng thái của một phiên chuyển đổi**, báo **UNDERFLOW / OVERFLOW / MALFORMED / UNMAPPABLE** và cho phép điều khiển chính xác thời điểm kết thúc.

Bài học tập trung vào **ByteBuffer**, **CharBuffer**, vòng lặp **decode/encode**, xử lý ký tự bị chia mảnh, **flush**, hành vi lỗi và tích hợp với channel. **Không nhầm** chuyển đổi charset với định ranh giới message, TCP framing hay xác nhận bên nhận đã xử lý dữ liệu.

## 1. Vấn đề: ranh giới byte không phải ranh giới ký tự

Ví dụ chuỗi Java:

~~~text
Văn bản: A€😄Z
Code point: U+0041, U+20AC, U+1F604, U+005A
UTF-16 char units: [0041] [20AC] [D83D DE04] [005A] (5 char units)
UTF-8 bytes: 41 E2 82 AC F0 9F 98 84 5A (9 byte)
~~~

Với stream TCP, các lần nhận có thể tách tùy ý:

~~~text
Lượt đọc #1: 41 E2
Lượt đọc #2: 82
Lượt đọc #3: AC F0 9F
Lượt đọc #4: 98 84 5A
~~~

Ở cuối lượt #1, **E2** chưa đủ 3 byte để tạo **€**. Ở lượt #3, **F0 9F** chưa đủ 4 byte để tạo **😄**. Nếu tạo **new String(byteChunk, UTF_8)** trên từng mảnh, Java có thể thay chuỗi byte thiếu hoặc sai bằng **U+FFFD (�)**; nối các chuỗi đã giải mã sai lại sẽ **không** tái tạo văn bản gốc.

Đối với chiều mã hóa, một phần **CharBuffer** có thể kết thúc tại **high surrogate U+D83D**; **low surrogate U+DE04** đến trong phần kế tiếp. Không được biến high surrogate đơn lẻ thành dấu **?**, hoặc tự xem nó là một ký tự Unicode hoàn chỉnh.

**Cách giải quyết:** duy trì một **CharsetDecoder/CharsetEncoder** xuyên suốt các mảnh của **cùng một luồng mã hóa**, giữ lại dữ liệu đầu vào chưa tiêu thụ, và chỉ đánh dấu kết thúc khi thật sự đến cuối luồng/đơn vị văn bản được định nghĩa là độc lập.

## 2. Bốn API chính và quan hệ giữa các buffer

~~~text
Chiều nhận (decode):
socket/channel → [ByteBuffer, write mode]
                  flip()
              → CharsetDecoder.decode(inputBytes, outputChars, endOfInput)
              → [CharBuffer, write mode]
                  flip() → đọc char đã giải mã → clear()
                  compact() ByteBuffer để giữ các byte chưa tiêu thụ

Chiều gửi (encode):
chuỗi/char stream → [CharBuffer, write mode]
                     flip()
                 → CharsetEncoder.encode(inputChars, outputBytes, endOfInput)
                 → [ByteBuffer, write mode]
                     flip() → gửi/ghi hết byte → clear()/compact()
                     compact() CharBuffer để giữ char còn lại

Cuối phiên: decode(..., true) hoặc encode(..., true) → flush(output)
~~~

| Đối tượng/API | Đầu vào | Đầu ra | Vai trò |
| --- | --- | --- | --- |
| **Charset** | Tên charset / hằng số **StandardCharsets.UTF_8** | Decoder hoặc encoder | Định nghĩa cách ánh xạ byte ↔ ký tự |
| **CharsetDecoder** | **ByteBuffer** | **CharBuffer** | Giải mã tăng dần, quản lý trạng thái giải mã |
| **CharsetEncoder** | **CharBuffer** | **ByteBuffer** | Mã hóa tăng dần, quản lý trạng thái mã hóa |
| **CoderResult** | Kết quả từ decode/encode/flush | Trạng thái hoặc lỗi | Quyết định đọc thêm, xả đầu ra, báo lỗi |
| **CodingErrorAction** | REPORT / REPLACE / IGNORE | Chính sách gặp dữ liệu lỗi | Xử lý byte không hợp lệ / ký tự không biểu diễn được |

Tạo bộ chuyển đổi:

~~~java
import java.nio.charset.*;

CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Đây là **snippet** cấu hình, chưa thực hiện I/O. Sử dụng **newDecoder() / newEncoder()** riêng cho mỗi phiên độc lập; các đối tượng encoder/decoder **có trạng thái và không an toàn để nhiều thread đồng thời dùng chung**. **StandardCharsets.UTF_8** là đối tượng Charset có thể chia sẻ; không áp dụng điều đó cho encoder/decoder.

## 3. Nắm chắc position, limit, flip, compact và clear

Một **ByteBuffer/CharBuffer** có **capacity**, **position**, **limit**. Bộ chuyển đổi đọc từ **input.position()** đến **input.limit()** và ghi vào **output.position()** đến **output.limit()**. Sau lệnh, position của hai buffer có thể đã thay đổi; **đừng giả định nó tiêu thụ hết input**.

| Thao tác | Ý nghĩa |
| --- | --- |
| **flip()** | Sau khi ghi dữ liệu vào buffer, chuyển sang đọc: limit ← position, position ← 0 |
| **compact()** | Di chuyển phần **chưa đọc** về đầu, position sau dữ liệu còn lại, limit ← capacity; chuẩn bị ghi thêm |
| **clear()** | position ← 0, limit ← capacity; **không xóa nội dung vật lý**, chỉ chuẩn bị tái sử dụng và coi nội dung cũ là không cần giữ |
| **hasRemaining()** | Còn phần tử giữa position và limit |
| **remaining()** | Số phần tử còn lại trong vùng hiện tại |
| **rewind()** | Đưa position về 0 nhưng giữ limit; thường **không** thay thế compact khi phải giữ phần đầu vào chưa dùng |

Vòng lặp quan trọng ở phía decoder:

~~~text
(1) ByteBuffer đang WRITE MODE, chứa byte mới và byte thừa cũ
(2) input.flip()                   → READ MODE
(3) decoder.decode(input, output, endOfInput)
(4) output.flip() → tiêu thụ char → output.clear()
(5) OVERFLOW: quay lại (3), sau khi đã giải phóng đầu ra
    UNDERFLOW: cần thêm byte hoặc đã hết input
    ERROR: xử lý lỗi theo chính sách
(6) input.compact()                → giữ byte chưa tiêu thụ, chuyển WRITE MODE
(7) nhận thêm byte rồi lặp
~~~

**Lỗi kinh điển:** khi **decode** trả **UNDERFLOW** vì ở cuối buffer còn byte chưa tạo đủ một ký tự, gọi **input.clear()** sẽ bỏ chính những byte phải giữ. Phải dùng **input.compact()**. Mặt khác, **output** đã được đọc hết thì có thể **clear()** để lấy chỗ ghi mới.

**Không được luôn gọi compact sau khi encode vào ByteBuffer mà kênh chưa ghi hết:** byte output chưa gửi phải được giữ lại. Khi **channel.write(output)** trả **0** hoặc ghi chưa hết, buffer output phải giữ trong **read mode** để ghi tiếp ở lần kênh sẵn sàng, thay vì xóa dữ liệu chưa gửi.

## 4. CoderResult: UNDERFLOW, OVERFLOW, lỗi mã hóa

Lời gọi:

~~~java
CoderResult status = decoder.decode(inputBytes, outputChars, endOfInput);
~~~

có thể trả:

| Kết quả | Ý nghĩa | Xử lý đúng |
| --- | --- | --- |
| **UNDERFLOW** | Bộ chuyển đổi chưa thể/không còn tiếp tục với input hiện có; có thể còn một phần ký tự chưa đủ byte/char | Giữ phần còn lại qua **compact()**; nhận input mới, hoặc hoàn tất nếu đã end-of-input |
| **OVERFLOW** | Output buffer không còn đủ chỗ để tạo tiếp kết quả | **flip → consume/drain output → clear/compact → retry** cùng input còn lại |
| **MALFORMED** | Chuỗi byte/UTF-16 code units **không hợp lệ** đối với charset | REPORT lỗi, hoặc REPLACE/IGNORE có chủ đích |
| **UNMAPPABLE** | Ký tự hợp lệ nhưng charset đích **không biểu diễn được** (điển hình US-ASCII gặp **€**) | REPORT hoặc REPLACE/IGNORE theo protocol |

Trong Java:

~~~java
if (status.isOverflow()) {
    // Xả output; sau đó gọi decode/encode tiếp.
} else if (status.isUnderflow()) {
    // Giữ input chưa tiêu thụ và chờ thêm, hoặc bước kết thúc.
} else if (status.isError()) {
    status.throwException(); // CharacterCodingException subtype.
}
~~~

Đây là **snippet logic**, không phải chương trình độc lập. Khi **CodingErrorAction.REPORT**, các lỗi như **MALFORMED[1]** hay **UNMAPPABLE[1]** được trả dưới dạng **CoderResult**; **throwException()** ném **MalformedInputException** hoặc **UnmappableCharacterException** (các dạng **CharacterCodingException**).

**UNDERFLOW không nhất thiết nghĩa input.position() == input.limit().** Bộ giải mã có thể dừng tại một chuỗi byte chưa đủ; nếu endOfInput=false, nó chưa thể biết đó là dữ liệu lỗi hay một ký tự sẽ được hoàn thiện ở lượt sau. **OVERFLOW** không phải lỗi dữ liệu; nó là tín hiệu phải xả đầu ra.

**Chống vòng lặp vô hạn:** nếu output buffer quá nhỏ để chứa **một đơn vị đầu ra tối thiểu** (chẳng hạn CharBuffer có capacity=1 nhưng decoder cần ghi **hai UTF-16 char** cho một code point bổ sung), có thể cứ nhận **OVERFLOW** ngay cả khi buffer rỗng. Hãy chọn kích thước output đủ lớn, hoặc mở rộng buffer khi không có tiến triển. Với demo UTF-8, **CharBuffer capacity 2** và **ByteBuffer output capacity 4** đủ cho một code point tối đa 4 UTF-8 byte và hai UTF-16 code units.

## 5. decode(...) theo mảnh: giữ chuỗi byte chưa hoàn chỉnh

**CharsetDecoder.decode(ByteBuffer in, CharBuffer out, boolean endOfInput)** chuyển đổi phần input có sẵn, có thể tiêu thụ **ít hơn số byte đang có**.

Ví dụ khi giải mã **E2 82 AC** (ký tự **€**) theo từng byte:

~~~text
decode([E2], endOfInput=false)          → UNDERFLOW; giữ E2
decode([E2 82], endOfInput=false)       → UNDERFLOW; giữ E2 82
decode([E2 82 AC], endOfInput=false)    → sinh '€'; trạng thái thường UNDERFLOW
~~~

Một cách xây pipeline:

1. Dùng **ByteBuffer** đầu vào ở write mode; dữ liệu dư của lượt trước đã được compact về đầu.
2. Nhận thêm byte từ **SocketChannel.read(buffer)** hoặc producer tương tự.
3. Gọi **flip()** để chuyển sang read mode.
4. Gọi **decoder.decode(...)** trong vòng lặp; mỗi lần cần **xả CharBuffer** mà decoder đã ghi.
5. Khi **OVERFLOW**, xả output rồi decode tiếp ngay; khi **UNDERFLOW**, compact input để giữ phần byte còn sót.
6. Khi **read() == -1**, đánh dấu **endOfInput=true** ở lần decode cuối, sau đó gọi **flush(...)**.
7. Nếu giao thức đóng một **văn bản độc lập** trong frame thay vì kết thúc socket, có thể coi **hết frame** là end-of-input của phiên charset riêng đó, miễn protocol thật sự bảo đảm mỗi frame có chuỗi byte được mã hóa độc lập và đầy đủ.

### Sắc thái với non-blocking channel

**read() == 0** nghĩa là lúc đó chưa có byte; **không** tương đương EOF. Chỉ **read() == -1** biểu thị end-of-stream đối với **SocketChannel**. Không gọi **decode(..., true)** chỉ vì một lượt đọc trả 0 hoặc tạm thời không nhận thêm packet. Với NIO non-blocking, nên giữ input buffer + decoder ở trạng thái của **từng connection**, đợi **OP_READ** hoặc sự kiện tiếp theo để bổ sung byte.

Sau **UNDERFLOW** phải kiểm tra buffer đầu vào còn đủ chỗ để nhận thêm. Nếu nó đầy mà không thể tiêu thụ dữ liệu, dùng buffer lớn hơn hoặc báo lỗi giới hạn tài nguyên. Không thể giải mã vô hạn vào một buffer cố định quá nhỏ mà không có chiến lược tăng capacity hoặc áp dụng protocol limit.

## 6. encode(...) theo mảnh: chú ý surrogate pair và partial write

**CharsetEncoder.encode(CharBuffer in, ByteBuffer out, boolean endOfInput)** mã hóa phần char hiện có thành byte. Java **char** là một **UTF-16 code unit**, không đồng nghĩa với một Unicode code point. Emoji **😄** là hai char:

~~~text
U+1F604 (😄)
High surrogate: U+D83D
Low surrogate:  U+DE04
UTF-8 output:   F0 9F 98 84
~~~

Nếu input fragment kết thúc tại **U+D83D** và **endOfInput=false**, encoder có thể trả **UNDERFLOW** để đợi **U+DE04**. Sau **CharBuffer.compact()**, high surrogate được giữ lại; lần đưa low surrogate kế tiếp giúp encoder tạo byte hợp lệ.

**Không** thực hiện mã hóa riêng cho mỗi mảnh char bằng cách tạo encoder mới hoặc **new String(chunk).getBytes(UTF_8)**. Một surrogate lẻ bị coi là malformed hoặc bị thay thế, khiến byte stream sai.

Ở chiều output, khi encoder sinh byte vào **ByteBuffer** và chương trình dùng **SocketChannel.write(ByteBuffer)**:

- Gọi **output.flip()** rồi ghi **trong khi output.hasRemaining()**.
- Nếu channel non-blocking trả **0** hoặc ghi chỉ một phần, phải giữ byte chưa gửi; đăng ký **OP_WRITE** (khi cần) và ghi tiếp ở thời điểm thích hợp.
- Chỉ **clear()** output khi **đã gửi hoặc sao chép hết toàn bộ byte trong đó**.
- **OVERFLOW** từ encoder nghĩa là phải tiêu thụ output rồi tiếp tục encode input chưa dùng, không phải nên bỏ byte.
- Giữa các mảnh input, dùng **CharBuffer.compact()** để giữ high surrogate hay code unit khác chưa được tiêu thụ.

Một **StringBuilder**/CharBuffer ở tầng ứng dụng cũng cần giới hạn. Nếu producer nhanh hơn đường truyền, phải thực hiện **backpressure**, không tạo queue byte vô hạn.

## 7. endOfInput và flush(): kết thúc đúng một phiên

Thứ tự đúng ở cuối một luồng charset:

~~~text
Các mảnh chưa cuối:
    decode(in, out, false) hoặc encode(in, out, false)
    + xả output + compact input để nhận thêm

Mảnh cuối cùng:
    decode(in, out, true) hoặc encode(in, out, true)
    + xử lý OVERFLOW bằng cách xả output và thử lại với endOfInput=true
    + nếu lỗi: xử lý REPORT/REPLACE/IGNORE
    + khi UNDERFLOW: phần chuyển đổi chính đã kết thúc

Sau đó:
    decoder.flush(out) hoặc encoder.flush(out)
    + xử lý OVERFLOW cho tới khi UNDERFLOW
    + xả phần output còn lại

Để xử lý một văn bản độc lập mới:
    reset() hoặc tạo encoder/decoder mới
~~~

**endOfInput=true** là lời khẳng định rằng sẽ không có byte/char tiếp theo trong **phiên charset đang xử lý**, **không phải** “đây là mảnh cuối của một lần read hiện tại” hay “tạm thời hết byte trong TCP receive queue”.

Nếu byte cuối là một tiền tố UTF-8 chưa đầy đủ, ví dụ **C3** mà không có byte continuation, decoder có thể trả:

~~~text
decode([C3], endOfInput=false) → UNDERFLOW
decode([C3], endOfInput=true)  → MALFORMED[1] (với REPORT)
~~~

Tại EOF, **không được bỏ qua input còn thừa**. Nếu đã đánh dấu endOfInput=true mà phát hiện dữ liệu malformed, hãy áp dụng chính sách lỗi đã định (thường fail fast trong protocol). **flush(...)** chỉ hợp lệ sau khi đã đi qua lệnh decode/encode cuối với **endOfInput=true** và đạt **UNDERFLOW**; gọi flush quá sớm có thể gây **IllegalStateException** do trạng thái bộ chuyển đổi chưa đúng.

Với input rỗng hoàn toàn, vẫn cần chuyển bộ chuyển đổi từ trạng thái ban đầu qua bước **decode/encode(empty, out, true)** trước khi **flush**, thay vì chỉ gọi flush ngay. Đối với một số charset có trạng thái (ví dụ những encoding dùng shift sequences), flush có thể sinh thêm output, vì vậy không được bỏ qua. Với UTF-8 thông thường, flush thường không sinh thêm byte/char, nhưng cách tổ chức vòng lặp vẫn phải đúng.

Một khi đã kết thúc phiên, **không** tiếp tục gọi decode(...,false)/encode(...,false) trên cùng bộ chuyển đổi trước khi **reset()**.

## 8. Chương trình Java 17+ hoàn chỉnh: giải mã và mã hóa từng code unit

Demo tự kiểm chứng **không cần mạng**: mô phỏng một nguồn cung cấp byte UTF-8 **mỗi lần đúng một byte**, rồi mô phỏng nguồn cấp **mỗi lần một UTF-16 char**. Đây là điều kiện rất bất lợi để kiểm thử việc giữ lại **UTF-8 multibyte prefix** và **UTF-16 high surrogate** giữa các lượt.

Đặc điểm code:

- Decoder dùng **ByteBuffer capacity 8** và **CharBuffer capacity 2**.
- Encoder dùng **CharBuffer capacity 4** và **ByteBuffer capacity 4**.
- Sau mỗi lần decode/encode, output được **flip → drain → clear**; input được **compact** để giữ phần chưa tiêu thụ.
- Mảnh cuối mới dùng **endOfInput=true**, sau đó lặp **flush**.
- Cấu hình **REPORT**, tức lỗi charset không bị thay âm thầm.
- Kết quả được so với byte UTF-8 ban đầu bằng **Arrays.equals**.

Tạo tệp **StreamingCharsetDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.*;
import java.util.Arrays;
import java.util.HexFormat;

public class StreamingCharsetDemo {
    private static void drainChars(CharBuffer buffer, StringBuilder result) {
        buffer.flip();
        result.append(buffer);
        buffer.clear();
    }

    private static void drainBytes(ByteBuffer buffer, ByteArrayOutputStream result) {
        buffer.flip();
        while (buffer.hasRemaining()) {
            result.write(buffer.get());
        }
        buffer.clear();
    }

    static String decodeFragments(byte[] bytes) throws CharacterCodingException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(2);
        StringBuilder text = new StringBuilder();

        for (int i = 0; i < bytes.length; i++) {
            input.put(bytes[i]);
            input.flip();
            boolean lastFragment = (i == bytes.length - 1);

            while (true) {
                CoderResult status = decoder.decode(input, output, lastFragment);
                drainChars(output, text);
                if (status.isError()) {
                    status.throwException();
                }
                if (status.isOverflow()) {
                    continue;
                }
                if (status.isUnderflow()) {
                    break;
                }
            }
            input.compact();
        }
        while (true) {
            CoderResult status = decoder.flush(output);
            drainChars(output, text);
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                break;
            }
        }
        return text.toString();
    }

    static byte[] encodeFragments(String text) throws CharacterCodingException {
        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        CharBuffer input = CharBuffer.allocate(4);
        ByteBuffer output = ByteBuffer.allocate(4);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        char[] units = text.toCharArray();

        for (int i = 0; i < units.length; i++) {
            input.put(units[i]);
            input.flip();
            boolean lastFragment = (i == units.length - 1);

            while (true) {
                CoderResult status = encoder.encode(input, output, lastFragment);
                drainBytes(output, bytes);
                if (status.isError()) {
                    status.throwException();
                }
                if (status.isOverflow()) {
                    continue;
                }
                if (status.isUnderflow()) {
                    break;
                }
            }
            input.compact();
        }
        while (true) {
            CoderResult status = encoder.flush(output);
            drainBytes(output, bytes);
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                break;
            }
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        String input = "A€😄Z";
        byte[] raw = input.getBytes(StandardCharsets.UTF_8);
        String decoded = decodeFragments(raw);
        byte[] encoded = encodeFragments(input);

        System.out.println("inputHex=" + HexFormat.of().formatHex(raw));
        System.out.println("decoded=" + decoded);
        System.out.println("utf16Units=" + input.length());
        System.out.println("encodedHex=" + HexFormat.of().formatHex(encoded));
        System.out.println("sameBytes=" + Arrays.equals(raw, encoded));

        CharsetDecoder incomplete = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);
        ByteBuffer oneByte = ByteBuffer.wrap(new byte[] {(byte) 0xC3});
        CharBuffer chars = CharBuffer.allocate(4);
        System.out.println("beforeEOF=" + incomplete.decode(oneByte, chars, false));
        System.out.println("atEOF=" + incomplete.decode(oneByte, chars, true));

        CharsetEncoder ascii = StandardCharsets.US_ASCII.newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        System.out.println("asciiEuro=" +
                ascii.encode(CharBuffer.wrap("€"), ByteBuffer.allocate(8), true));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ ở thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 StreamingCharsetDemo.java
java StreamingCharsetDemo
~~~

**Stdout trong một lượt chạy thành công** (đã kiểm chứng với JDK 24, biên dịch mục tiêu Java 17):

~~~text
inputHex=41e282acf09f98845a
decoded=A€😄Z
utf16Units=5
encodedHex=41e282acf09f98845a
sameBytes=true
beforeEOF=UNDERFLOW
atEOF=MALFORMED[1]
asciiEuro=UNMAPPABLE[1]
~~~

### Phân tích từng phần

**Decoder:**

1. Lấy từng byte trong mảng **raw**, gọi **input.put(...)** khi ByteBuffer ở write mode.
2. **flip()** giúp decoder đọc byte mới cộng các byte UTF-8 prefix còn giữ lại từ trước.
3. **decode(..., false)** đối với các mảnh chưa cuối có thể để lại byte chưa đủ tạo ký tự. **compact()** giữ byte đó; lần sau mới nối thêm.
4. **CharBuffer capacity 2** đủ để chứa một supplementary Unicode code point dưới dạng surrogate pair.
5. Khi đã nhận byte cuối, **decode(..., true)** kết thúc luồng; tiếp đến **flush**.
6. Kết quả là **A€😄Z** mà không làm biến mất các code point bị chia byte.

**Encoder:**

1. **text.toCharArray()** tạo 5 UTF-16 code units: **A**, **€**, high surrogate, low surrogate, **Z**.
2. Mỗi lần cung cấp **một char**, **encode(..., false)** có thể cần chờ low surrogate. **CharBuffer.compact()** giữ high surrogate còn lại giữa hai lần gọi.
3. Output **ByteBuffer capacity 4** đủ ghi một UTF-8 code point tối đa 4 byte; vòng lặp vẫn có xử lý **OVERFLOW** và **flush** đúng cấu trúc.
4. **sameBytes=true** nghĩa là demo tái tạo đúng mảng byte gốc trên dữ liệu đầu vào đã chọn, không phải cam kết mọi charset hay input đều round-trip khi có lỗi hoặc chuẩn hóa.

**Lỗi minh họa:**

- **beforeEOF=UNDERFLOW**: byte **C3** là phần đầu của một UTF-8 sequence có thể cần thêm byte.
- **atEOF=MALFORMED[1]**: nếu luồng thật sự kết thúc tại byte **C3**, byte đó trở thành dữ liệu UTF-8 không đầy đủ.
- **asciiEuro=UNMAPPABLE[1]**: **€** là ký tự Unicode hợp lệ, nhưng charset **US-ASCII** không thể mã hóa nó.

**Giới hạn của demo:** các hàm **decodeFragments/encodeFragments** nhận chuỗi/mảng **không rỗng** để đơn giản hóa vòng lặp. Khi triển khai tổng quát, phải xử lý **input rỗng** bằng lệnh decode/encode cuối **endOfInput=true** trước flush. Trong ứng dụng mạng thật, đọc byte từ channel, quản lý buffer output còn chưa ghi hết và giới hạn tài nguyên; không tạo ByteArrayOutputStream/StringBuilder không giới hạn đối với dữ liệu không tin cậy.

## 9. REPORT, REPLACE hay IGNORE: chọn chính sách lỗi có chủ đích

Có hai loại lỗi quan trọng:

- **Malformed input**: byte sequence hoặc UTF-16 code units **bất hợp lệ** đối với mã hóa. Ví dụ UTF-8 kết thúc bằng byte **C3**, hoặc input encoder chứa một high surrogate đơn lẻ.
- **Unmappable character**: đầu vào hợp lệ nhưng **charset đích không có biểu diễn**. Ví dụ **€** với **US_ASCII CharsetEncoder**.

Cấu hình:

~~~java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetDecoder tolerant = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith("\uFFFD");

CharsetEncoder ascii = StandardCharsets.US_ASCII.newEncoder()
        .onUnmappableCharacter(CodingErrorAction.REPLACE);
// Có thể cấu hình replacement byte[] hợp lệ bằng ascii.replaceWith(...).
~~~

Đoạn trên là **snippet cấu hình**. Chính sách:

| Action | Hành vi | Rủi ro/cách dùng |
| --- | --- | --- |
| **REPORT** | Trả CoderResult lỗi; caller quyết định ném exception, ngắt frame hoặc connection | Thích hợp cho giao thức cần tính toàn vẹn |
| **REPLACE** | Thay dữ liệu lỗi bằng replacement có cấu hình | Hữu ích với hiển thị “best effort”, nhưng có thể mất thông tin |
| **IGNORE** | Bỏ dữ liệu lỗi rồi tiếp tục | Có thể xóa im lặng byte/char quan trọng; thường không phù hợp với dữ liệu có ý nghĩa bảo mật |

**CharsetDecoder** thường dùng ký tự thay thế **U+FFFD**, còn **CharsetEncoder** dùng replacement **byte[]** hợp lệ cho charset đích. Đừng đồng nhất hành vi của **new String(byte[], charset)** hoặc **String.getBytes(charset)** (các API tiện ích có chính sách thay thế khi dữ liệu lỗi) với một encoder/decoder đang cấu hình **REPORT**. Luôn xác định quy tắc protocol.

Tình huống bảo mật: nếu một tầng **REPLACE/IGNORE** để hợp thức hóa dữ liệu không hợp lệ, còn tầng khác giải thích byte thô theo cách khác, các lớp có thể **không đồng ý về nội dung thông điệp**. Với protocol yêu cầu cú pháp nghiêm ngặt, dùng charset cố định (thường UTF-8), **REPORT**, giới hạn kích thước và validate nội dung sau decode.

## 10. Kết hợp với SocketChannel: ranh giới byte, text và message

Một pipeline networking đúng cần chia ít nhất ba vấn đề:

~~~text
TCP byte stream
    ↓ SocketChannel.read()
ByteBuffer tích lũy byte (có thể chứa nửa ký tự)
    ↓ CharsetDecoder stateful
CharBuffer / chuỗi ký tự Unicode
    ↓ parser theo protocol
Thông điệp hoàn chỉnh (delimiter, length-prefix, JSON stream, ...)
    ↓ validation và xử lý nghiệp vụ
~~~

**CharsetDecoder chỉ giải quyết việc ghép byte thành ký tự**, không cho biết “đã đọc đủ một HTTP request”, “đã gặp hết dòng” hay “đã nhận một JSON document”. Muốn parse message cần **framing**: độ dài byte, delimiter phù hợp, hoặc parser streaming. Với giao thức length-prefixed UTF-8, cần đọc đủ số **byte** trước (hoặc decode streaming đúng giới hạn frame); không nhầm **byte length** với **String.length()**, vì String.length() đếm UTF-16 code units.

### Phác thảo vòng lặp nhận trên channel

~~~java
// Pseudocode minh họa, không phải chương trình độc lập:
// channel là SocketChannel, decoder và các buffer thuộc riêng connection.
int n = channel.read(inputBytes); // Input ByteBuffer đang ở write mode.
if (n == -1) {
    inputBytes.flip();
    // Gọi decoder.decode(..., true) trong vòng lặp,
    // xử lý CoderResult, xả CharBuffer và gọi decoder.flush(...).
} else if (n > 0) {
    inputBytes.flip();
    // Gọi decoder.decode(..., false), xử lý OVERFLOW / ERROR.
    // Sau UNDERFLOW: inputBytes.compact() để giữ byte còn thiếu.
} else {
    // n == 0: không phải EOF; đợi lần đọc tiếp theo.
}
~~~

Đoạn này trình bày **cấu trúc trạng thái**, chưa triển khai vòng lặp decode, output draining, error handling và selector; đừng copy như một server chạy được. Chương trình **StreamingCharsetDemo** ở phần 8 là ví dụ chạy được và kiểm chứng được cho core algorithm.

### Phác thảo vòng lặp gửi trên non-blocking channel

~~~java
// Pseudocode, không chạy độc lập:
// outputBytes đã được encoder ghi vào ở write mode.
outputBytes.flip();
while (outputBytes.hasRemaining()) {
    int n = channel.write(outputBytes);
    if (n == 0) {
        // Không clear outputBytes!
        // Ghi nhớ byte còn lại, đợi OP_WRITE rồi tiếp tục.
        break;
    }
}
// Sau khi toàn bộ byte đã thực sự rời buffer mới clear() hoặc tái sử dụng.
// Nếu còn byte, giữ read mode cho lần write sau.
~~~

Dữ liệu trả về từ **encoder** chưa đồng nghĩa với dữ liệu đã gửi đến peer: **SocketChannel.write** có thể ghi một phần. Ngay cả khi write tiêu thụ hết ByteBuffer, tầng TCP mới nhận byte để vận chuyển; chỉ response của protocol mới cho biết phía kia đã xử lý yêu cầu.

### Khi nào reset encoder/decoder?

Một **connection** có thể có nhiều message. Có hai thiết kế khác nhau:

- **Luồng text mã hóa liên tục**: giữ cùng decoder qua tất cả read và message, chỉ endOfInput=true khi thực sự hết luồng; parser độc lập rút message khỏi char stream.
- **Các frame độc lập, mỗi frame là một text encoding hoàn chỉnh**: có thể tạo decoder mới (hoặc reset sau flush) cho **từng frame**; bắt buộc bảo đảm frame kết thúc tại ranh giới byte hợp lệ và không chứa nửa ký tự của frame sau.

Đối với charset có trạng thái, tạo/reset decoder tại ranh giới sai có thể làm mất trạng thái shift/escape. Với UTF-8, việc khởi tạo lại ở mỗi read vẫn sai nếu một code point bị chia; chỉ thiết lập phiên theo ranh giới text được protocol xác nhận.

## 11. Buffer sizing, hiệu năng và dữ liệu thực tế

**ByteBuffer.allocateDirect(...)** có thể hữu ích trong một số đường đi I/O lớn, nhưng không phải “bật direct là nhanh hơn” cho mọi bài toán. Buffer trực tiếp có chi phí quản lý, và cần benchmark thực tế. CharsetDecoder/Encoder làm việc với **ByteBuffer/CharBuffer**; chọn heap/direct dựa trên workflow và khả năng giữ/reuse buffer.

**Kích thước đầu ra có thể khác kích thước đầu vào**:

- UTF-8 → UTF-16 có thể chuyển một code point 4 byte thành **2 char**.
- UTF-16 → UTF-8 có thể chuyển một char thành 1–3 byte hoặc một surrogate pair thành 4 byte.
- Không lấy **bytes.length == text.length()** làm công thức bộ nhớ; **String.length()** tính code units UTF-16, không tính Unicode code points và cũng không phải số ký tự hiển thị (grapheme clusters).
- **CharsetDecoder.averageCharsPerByte() / maxCharsPerByte()** và **CharsetEncoder.averageBytesPerChar() / maxBytesPerChar()** chỉ giúp định cỡ/gợi ý; xử lý overflow vẫn cần vì charset, trạng thái và replacement có thể làm số phần tử thực tế thay đổi.

### Bốn nguyên tắc hiệu năng

1. **Tái sử dụng** buffer và decoder/encoder trong **một phiên** thay vì cấp phát mới ở mỗi packet. **Không** chia sẻ một instance có state đồng thời giữa các connection/thread.
2. **Tách protocol limit với buffer capacity**: một ByteBuffer 8 KiB không có nghĩa message tối đa 8 KiB. Cần quản lý tổng bytes/chars đã xử lý, chống memory exhaustion và message quá lớn.
3. **Đo backpressure**: nếu downstream parser xử lý chậm hoặc non-blocking channel chưa ghi hết, đừng đẩy vô hạn dữ liệu vào queue; ngừng đọc hoặc điều tiết producer hợp lý.
4. **Chọn charset tường minh**: **StandardCharsets.UTF_8** cho giao thức UTF-8; không dựa vào platform default charset. Với charset stateful như ISO-2022-JP, việc giữ state và gọi **flush** đúng thời điểm càng quan trọng.

### BOM, normalization và ranh giới Unicode

Một luồng UTF-8 có thể bắt đầu với byte BOM **EF BB BF**. Việc bộ giải mã hay tầng ứng dụng xử lý **U+FEFF** như thế nào cần theo quy định của protocol/format; đừng tự xóa mọi U+FEFF trong nội dung. CharsetDecoder **không** tự thực hiện Unicode normalization (NFC/NFD), không kiểm tra semantic validity của toàn bộ JSON/XML/HTTP message và không đảm bảo văn bản đã hợp lệ cho một trường nghiệp vụ. Nếu cần giới hạn ký tự hoặc xử lý Unicode confusables, validation ở tầng sau phải được thiết kế riêng.

## 12. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Ký tự **�** xuất hiện khi byte UTF-8 bị chia ở ranh giới read | Tạo String từ từng byte chunk hoặc bật REPLACE mà không giữ byte dư | Giữ **CharsetDecoder** xuyên các mảnh, **ByteBuffer.compact()** |
| Emoji bị mất hoặc thành **?** khi encode theo từng char | Tách surrogate pair và mã hóa độc lập | Giữ high surrogate bằng **CharBuffer.compact()**, encode theo stream |
| CPU chạy 100% trong vòng lặp decode | Nhận OVERFLOW nhưng chưa xả output; hoặc output quá nhỏ để tiến triển | Drain output; đủ capacity và kiểm tra tiến triển |
| Exception sau khi gọi flush | Chưa gọi decode/encode với **endOfInput=true** và đạt UNDERFLOW | Tuân thủ state machine |
| Đọc data rồi thiếu ký tự cuối | Kết thúc mà không decode(..., true) / flush; hoặc bỏ byte còn dư | Xử lý EOF đúng, REPORT truncated sequence |
| Có byte còn lại trong input nhưng lần sau thành chữ sai | Dùng **clear()** thay vì **compact()** cho input chưa tiêu thụ | Giữ remaining prefix đúng cách |
| Mất byte gửi trên SocketChannel non-blocking | Clear output khi **write()** mới ghi một phần hoặc trả **0** | Giữ ByteBuffer còn remaining, đợi writable và ghi tiếp |
| Decoder báo MalformedInputException | Dữ liệu có byte không hợp lệ/charset sai hoặc bị cắt ở EOF | Kiểm tra wire bytes, khai báo charset, framing và error policy |
| ASCII encoder báo Unmappable | Chuỗi chứa ký tự ngoài tập ASCII | Chọn UTF-8 hoặc xử lý REPORT/REPLACE theo hợp đồng |
| Mỗi read trả một “message” bị dính hoặc thiếu | Nhầm TCP read boundary với message boundary | Thêm framing/parser độc lập sau decode |
| Chạy lại decoder cho frame khác bị IllegalStateException | Instance còn ở FLUSHED hoặc trạng thái kết thúc | **reset()** sau flush hoặc tạo mới |
| Buffer nhỏ và underflow lặp, không có chỗ đọc thêm | Buffer không đủ giữ một sequence hoặc đã chạm resource limit | Mở rộng có giới hạn / điều chỉnh buffer sizing |

### Checklist tự kiểm tra khi viết pipeline tăng dần

- [ ] Charset được chỉ định rõ ràng và nhất quán giữa hai phía?
- [ ] Có **một encoder/decoder theo mỗi luồng mã hóa độc lập**, không tạo lại theo packet?
- [ ] Sau **UNDERFLOW**, input **compact()** giữ byte/char chưa tiêu thụ?
- [ ] Sau **OVERFLOW**, output được drain trước khi thử lại, kể cả khi buffer quá nhỏ?
- [ ] Có phân biệt **read()==0** với **read()==-1**?
- [ ] Chỉ **endOfInput=true** khi luồng charset thực sự hoàn tất?
- [ ] Sau final decode/encode, có **flush** tới UNDERFLOW?
- [ ] Có chính sách **REPORT/REPLACE/IGNORE** minh bạch và xử lý malformed/unmappable?
- [ ] Khi channel.write() chưa ghi hết, byte output vẫn được giữ?
- [ ] Có message framing, giới hạn payload và xử lý backpressure?
- [ ] Có test UTF-8 ký tự nhiều byte và surrogate pair bị cắt ở mọi vị trí?
- [ ] Có reset/tạo mới decoder khi bắt đầu **một phiên độc lập mới**?

## 13. Bài tập thực hành

1. Dùng chuỗi **"Việt Nam 😄"** và thử mọi cách chia byte UTF-8 thành các mảnh độ dài 1 đến 5. Đối chiếu kết quả từ **CharsetDecoder** với chuỗi gốc; giải thích vì sao giải mã mỗi mảnh bằng **new String(...)** có thể sai.
2. Thay **CharBuffer.allocate(2)** trong demo thành **allocate(1)**. Quan sát vấn đề khi gặp emoji và sửa vòng lặp bằng cách tăng capacity đủ cho surrogate pair; không busy-loop vĩnh viễn.
3. Cung cấp **E2 82** rồi kết thúc stream. So sánh **decode(false)**, **decode(true)** với REPORT và REPLACE. Tại sao kết quả ở hai thời điểm khác nhau?
4. Đưa **"A€B"** vào **US_ASCII.newEncoder()**. So sánh REPORT, REPLACE và IGNORE, đánh giá nguy cơ mất dữ liệu khi protocol đòi exact content.
5. Viết một TCP client/server dùng **SocketChannel**: server decode UTF-8 tăng dần, parser nhận message theo length-prefix tính bằng **byte**, rồi encode UTF-8 response. Giả lập read trả chỉ 1–2 byte; thêm kiểm thử EOF giữa một UTF-8 sequence.
6. Với channel non-blocking, giả lập **write(ByteBuffer)** trả 0 hoặc ghi từng phần. Thiết kế state giữ output ByteBuffer chưa gửi và tránh queue không giới hạn.

**Tóm tắt:** **CharsetDecoder** chuyển **byte → char** và **CharsetEncoder** chuyển **char → byte** theo **một phiên có trạng thái**. **UNDERFLOW** yêu cầu giữ input chưa hoàn thành; **OVERFLOW** yêu cầu xả output; **MALFORMED / UNMAPPABLE** đòi chính sách lỗi. Dùng **flip → decode/encode → drain output → compact input**, chỉ đặt **endOfInput=true** khi thực sự hết luồng, rồi **flush** và **reset** nếu bắt đầu luồng mới. Bản thân charset conversion không thay thế TCP framing, I/O timeout hoặc application protocol.

**Tài liệu chính thức:** [CharsetDecoder (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html), [CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html), [CoderResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CoderResult.html), [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html).