# Thiết kế framing bằng độ dài hoặc dấu phân cách trong Java NIO mạng

## 1. Vì sao TCP cần framing?

`SocketChannel` trong Java NIO truyền và nhận **luồng byte** TCP. TCP không bảo toàn ranh giới thông điệp của ứng dụng: một lần `write()` có thể được đọc thành nhiều lần `read()`, và một lần `read()` có thể chứa byte của nhiều lần `write()`.

Giả sử ứng dụng gửi hai thông điệp `"HELLO"` và `"WORLD"`. Receiver có thể nhận các chunk `"HEL"`, `"LOWOR"`, `"LD"`, hoặc nhận toàn bộ `"HELLOWORLD"` trong một lần. Không cách phân chia nào sai theo hợp đồng TCP. Vì thế chương trình **không thể** dựa vào mỗi lần `read()` để xác định một thông điệp.

**Message framing** là một định dạng ở tầng ứng dụng giúp phân định từng thông điệp (frame) trên luồng byte. Hai cách phổ biến là:

- **Length-prefix**: đặt thông tin độ dài ở header, sau đó gửi đúng số byte payload.
- **Delimiter-based**: kết thúc từng payload bằng một chuỗi byte đặc biệt, ví dụ LF (`0x0A`) hoặc CRLF (`0x0D 0x0A`).

Bài học thuộc Java Core I/O → **NIO mạng**, giải thích thiết kế wire format, state machine xử lý `ByteBuffer`, partial read/write, EOF, giới hạn bộ nhớ, kiểm thử và cách chọn kỹ thuật.

## 2. Phân biệt các tầng khi truyền dữ liệu

| Thuật ngữ | Vai trò |
| --- | --- |
| Payload | Nội dung ứng dụng như chuỗi UTF-8, JSON, byte nhị phân |
| Frame | Payload và thông tin xác định ranh giới (header độ dài hoặc delimiter) |
| TCP stream | Chuỗi byte được chuyển theo thứ tự, không có ranh giới message |
| `SocketChannel.read(ByteBuffer)` | Chuyển một lượng byte từ socket vào buffer tại lần gọi này |
| `ByteBuffer` | Bộ nhớ và con trỏ `position`, `limit`, `capacity` |
| TCP segment | Đơn vị đóng gói của tầng mạng, không đồng nhất với frame ứng dụng |

Ngay cả khi thử nghiệm trên localhost cho cảm giác “một write bằng một read”, ứng dụng phải xử lý chia nhỏ, ghép lại và thay đổi thời điểm nhận dữ liệu. Giải pháp là **decoder giữ trạng thái giữa các lần nhận byte**.

## 3. Framing bằng header độ dài

Một giao thức đơn giản dùng **4 byte đầu là số nguyên có dấu, big-endian** chứa độ dài tính bằng **byte của payload**, theo sau là đúng lượng byte đó:

```text
+------------------------------+-----------------------+
| length: 4 bytes (big-endian) | payload: length bytes |
+------------------------------+-----------------------+

"CAT" (3 byte UTF-8):
  00 00 00 03 | 43 41 54

"HI" (2 byte UTF-8):
  00 00 00 02 | 48 49
```

Các đặc điểm cần ghi rõ trong tài liệu giao thức:

1. Header có kích thước bao nhiêu byte; ví dụ này là 4.
2. Header đếm **chỉ payload** hay cả header; ví dụ này chỉ đếm payload.
3. Endianness; ví dụ dùng `ByteOrder.BIG_ENDIAN`.
4. Số âm hoặc length vượt giới hạn bị từ chối; `length=0` có thể đại diện frame rỗng.
5. Payload mã hóa UTF-8, byte nhị phân hay một schema khác.
6. Chính sách EOF giữa header hoặc giữa payload, timeout, compression và giới hạn tổng tài nguyên.

Với UTF-8, **độ dài ký tự Java khác số byte trên wire**: `String.length()` không phải giá trị để điền vào header. Luôn mã hóa trước rồi dùng `payload.getBytes(UTF_8).length`.

### 3.1. Encoder (đoạn mã trong một lớp Java)

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

static ByteBuffer encode(String message) {
    byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
    if (bytes.length > 1024) {
        throw new IllegalArgumentException("Payload too large");
    }
    ByteBuffer frame = ByteBuffer.allocate(4 + bytes.length);
    frame.order(ByteOrder.BIG_ENDIAN);
    frame.putInt(bytes.length);
    frame.put(bytes);
    frame.flip();
    return frame;
}
```

Code này là **phương thức minh họa**, cần đặt trong một class. Sau `flip()`, `position=0`, `limit=4+bytes.length` để `SocketChannel.write(frame)` bắt đầu chuyển byte từ header. Nếu quên `flip()`, channel có thể không gửi byte mới nào.

Độ dài 4 byte là một `int` có dấu ở Java. Nếu muốn hỗ trợ unsigned length hoặc varint, phải đặc tả rõ cách giải mã và kiểm tra tràn. Không ngầm coi mọi tổ hợp 4 byte đều là độ dài được cấp phát hợp lệ.

## 4. Decoder độ dài là máy trạng thái

Với length-prefix, decoder có hai pha:

```text
WAIT_HEADER (tích lũy đủ 4 byte)
             |
             v
     kiểm tra 0 <= N <= MAX
             |
             +-- N = 0 ------> emit frame rỗng ----+
             |                                     |
             v                                     |
WAIT_BODY (tích lũy đúng N byte)                   |
             |                                     |
             +---- emit payload --------------------+
             |
             v
         WAIT_HEADER tiếp
```

Không được giả định header 4 byte đến trong một `read()`. Ví dụ kết quả một lần `read` có thể mới chứa 1 byte header, lần kế có 3 byte, rồi lần tiếp theo mới chứa payload. Nếu đọc `getInt()` khi chưa đủ 4 byte, có thể ném `BufferUnderflowException`. Tương tự, một lần `read` không bảo đảm nhận được toàn bộ `N` byte payload.

Sau khi emit một frame, decoder phải **tiếp tục xử lý các byte còn lại trong cùng chunk**: một `read()` có thể chứa nhiều frame hoàn chỉnh và một phần frame kế tiếp.

Ví dụ hai frame nối tiếp:

```text
Frame "Hi":  00 00 00 02  48 69
Frame "NIO": 00 00 00 03  4E 49 4F

Luồng: [00 00 00 02 48 69 00 00 00 03 4E 49 4F]

Chunk A [00 00 00]            -> thiếu header 1 byte
Chunk B [02 48 69 00 00]      -> emit "Hi", giữ 2 byte đầu header thứ hai
Chunk C [00 03 4E 49 4F]      -> emit "NIO"
```

Decoder phải có trạng thái bền theo **từng kết nối TCP**: số byte header đã nhận, độ dài đã validate, số byte payload còn thiếu. Nếu dùng chung một state giữa hai socket độc lập, byte của hai kết nối có thể bị nối sai thành một thông điệp.

### 4.1. Giới hạn kích thước trước khi cấp phát

```java
int length = header.getInt(); // header đã có đủ 4 byte
if (length < 0 || length > MAX_PAYLOAD_BYTES) {
    throw new IllegalArgumentException("Invalid length: " + length);
}
```

Đây là code minh họa, cần một `header` và `MAX_PAYLOAD_BYTES` phù hợp. Đầu vào từ mạng **không đáng tin để cấp phát trực tiếp**. Không được `new byte[length]` trước khi xác minh length; một peer có thể gửi số rất lớn để gây cạn RAM. Với dữ liệu nén, phải giới hạn cả dung lượng sau giải nén. Ngoài per-frame limit, ứng dụng cần giới hạn tổng số buffer, số kết nối, request đang chờ và timeout.

## 5. Framing bằng dấu phân cách

Với giao thức văn bản, có thể chọn **byte LF = `0x0A`** làm dấu kết thúc:

```text
Dữ liệu gửi: red LF blue LF

Byte trên wire:
  72 65 64 0A 62 6C 75 65 0A
  [ red   ]LF [  blue  ] LF
```

Decoder tích lũy byte cho đến LF, emit phần trước LF thành một frame, bỏ delimiter rồi tiếp tục. Một chunk có thể chứa nhiều LF (nhiều frame); LF có thể đến ở cuối hoặc đầu chunk bất kỳ.

**Ưu điểm:** dễ xem bằng công cụ dòng lệnh, phù hợp protocol theo dòng, log và lệnh text; không cần đo trước độ dài payload.

**Giới hạn:** delimiter **không được xuất hiện không escape trong payload**. Nếu payload chứa LF, phải có escaping, quoting hoặc encoding được đặc tả (ví dụ JSON Lines với newline trong JSON string biểu diễn bằng escape), hoặc dùng length-prefix. Không được tự động coi mọi CRLF và LF là tương đương nếu protocol chưa quy định.

### 5.1. CRLF và delimiter nhiều byte

Một delimiter `CRLF` có hai byte: `0x0D 0x0A`. Nếu một chunk kết thúc ở CR và chunk kế bắt đầu ở LF, thuật toán tìm CRLF trong **từng chunk riêng** sẽ bỏ sót biên thông điệp. Parser cần giữ byte CR đang chờ hoặc dùng matcher streaming theo delimiter. Với delimiter dài hơn, có thể dùng một state machine/KMP giữ số byte khớp tiền tố.

### 5.2. Giới hạn độ dài dòng

Nếu bên gửi không bao giờ gửi LF, decoder không thể phát frame và dữ liệu tích lũy tăng vô hạn. Cần `MAX_LINE_BYTES`, kiểm tra trước khi thêm byte mới, timeout và chính sách từ chối kết nối khi vượt giới hạn. Hai LF liên tiếp có thể là frame rỗng; chấp nhận hoặc từ chối tùy hợp đồng giao thức.

## 6. So sánh length-prefix và delimiter

| Tiêu chí | Length-prefix | Delimiter |
| --- | --- | --- |
| Xác định ranh giới | Header + đúng N byte payload | Tìm chuỗi delimiter |
| Payload nhị phân bất kỳ | Dễ hỗ trợ | Phải escape khi chứa delimiter |
| Văn bản đọc trực tiếp | Header nhị phân không tiện nhìn | Dễ theo dõi bằng terminal |
| Payload dài bao nhiêu | Phải biết hoặc dùng chiến lược streaming/chunked | Không cần biết trước |
| Decoder | Tích lũy header rồi body | Matcher delimiter qua các chunk |
| Rủi ro lớn | Header giả, length âm/quá lớn, sai endian | Quên escaping, không có delimiter, line quá dài |
| Frame qua nhiều lần read | Cần giữ trạng thái | Cần giữ trạng thái |
| Nhiều frame cùng một lần read | Lặp parse để lấy hết | Lặp scan để lấy hết |
| EOF giữa frame | Header/body thiếu là lỗi theo strict protocol | Dòng chưa có delimiter: tùy policy |
| Ứng dụng điển hình | RPC, Protobuf, binary protocol | Line protocol, command text, JSON Lines |

Có thể dùng kết hợp: header length/type rồi payload chứa text có newline. Lựa chọn phải bám vào dữ liệu và định dạng hợp đồng; không có một kỹ thuật mặc định tốt nhất cho mọi hệ thống.

## 7. Ví dụ Java 17+ chạy độc lập: giải mã được dữ liệu bị chia hoặc gộp

Chương trình sau **mô phỏng kết quả socket read** bằng cách chia một luồng byte thành những chunk tùy ý. Decoder length-prefix quản lý 4 byte header và payload, decoder delimiter dùng LF; cả hai giữ trạng thái qua các lần gọi. Đây là bài test xác định, không phụ thuộc thời điểm mạng.

Tạo tệp `FramingDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FramingDemo {
    static final int MAX_BYTES = 1024;

    static byte[] encodeLengthFrame(String text) {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_BYTES) {
            throw new IllegalArgumentException("Too long");
        }
        ByteBuffer frame = ByteBuffer.allocate(4 + data.length);
        frame.order(ByteOrder.BIG_ENDIAN);
        frame.putInt(data.length);
        frame.put(data);
        return frame.array();
    }

    static class LengthDecoder {
        private final ByteBuffer header =
                ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN);
        private byte[] body;
        private int used;

        List<String> accept(byte[] chunk) {
            List<String> messages = new ArrayList<>();

            for (byte b : chunk) {
                if (body == null) {
                    header.put(b);
                    if (!header.hasRemaining()) {
                        header.flip();
                        int length = header.getInt();
                        header.clear();

                        if (length < 0 || length > MAX_BYTES) {
                            throw new IllegalArgumentException("Bad length");
                        }
                        if (length == 0) {
                            messages.add("");
                        } else {
                            body = new byte[length];
                            used = 0;
                        }
                    }
                } else {
                    body[used++] = b;
                    if (used == body.length) {
                        messages.add(new String(
                                body, StandardCharsets.UTF_8));
                        body = null;
                        used = 0;
                    }
                }
            }
            return messages;
        }

        void endOfInput() throws EOFException {
            if (header.position() != 0 || body != null) {
                throw new EOFException("Incomplete length frame");
            }
        }
    }

    static class LineDecoder {
        private final ByteArrayOutputStream pending =
                new ByteArrayOutputStream();

        List<String> accept(byte[] chunk) {
            List<String> messages = new ArrayList<>();
            for (byte b : chunk) {
                if (b == 10) { // LF
                    messages.add(new String(
                            pending.toByteArray(), StandardCharsets.UTF_8));
                    pending.reset();
                } else {
                    if (pending.size() >= MAX_BYTES) {
                        throw new IllegalArgumentException("Line too long");
                    }
                    pending.write(b);
                }
            }
            return messages;
        }

        void endOfInput() throws EOFException {
            if (pending.size() != 0) {
                throw new EOFException("Missing final LF");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        stream.writeBytes(encodeLengthFrame("Hi"));
        stream.writeBytes(encodeLengthFrame("NIO"));
        byte[] wire = stream.toByteArray();

        LengthDecoder length = new LengthDecoder();
        System.out.println("length 1: " +
                length.accept(Arrays.copyOfRange(wire, 0, 3)));
        System.out.println("length 2: " +
                length.accept(Arrays.copyOfRange(wire, 3, 8)));
        System.out.println("length 3: " +
                length.accept(Arrays.copyOfRange(wire, 8, wire.length)));
        length.endOfInput();

        byte[] lines = ("red" + (char) 10 + "blue" + (char) 10)
                .getBytes(StandardCharsets.UTF_8);
        LineDecoder line = new LineDecoder();
        System.out.println("line 1: " +
                line.accept(Arrays.copyOfRange(lines, 0, 2)));
        System.out.println("line 2: " +
                line.accept(Arrays.copyOfRange(lines, 2, 6)));
        System.out.println("line 3: " +
                line.accept(Arrays.copyOfRange(lines, 6, lines.length)));
        line.endOfInput();
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac FramingDemo.java
java FramingDemo
```

Kết quả:

```text
length 1: []
length 2: [Hi]
length 3: [NIO]
line 1: []
line 2: [red]
line 3: [blue]
```

**Giải thích:**

1. Chunk đầu của length-prefix mới có 3 byte header, chưa thể emit.
2. Chunk hai chứa byte header thứ tư, payload `Hi` và 2 byte đầu của header kế tiếp. Decoder emit `Hi`, giữ trạng thái header dang dở.
3. Chunk cuối hoàn tất header thứ hai và ba byte `NIO`, emit `NIO`.
4. Với delimiter, hai byte đầu là `re`. Chunk kế là `d`, LF, `bl`; decoder emit `red`, giữ `bl`. Chunk cuối là `ue`, LF, nên emit `blue`.
5. `endOfInput()` bảo đảm EOF ở ranh giới frame. Nếu header/body hoặc line còn dở, ví dụ này ném `EOFException`.

Decoder demo dùng `new String(bytes, UTF_8)`, có thể thay thế byte UTF-8 không hợp lệ. Nếu protocol yêu cầu *bắt buộc* UTF-8 hợp lệ, hãy dùng `CharsetDecoder` với `CodingErrorAction.REPORT`. Với performance cao, có thể thay vòng lặp từng byte bằng parser đọc trực tiếp `ByteBuffer`, nhưng phải giữ các bất biến về framing như trên.

## 8. Tích hợp với `SocketChannel` và `ByteBuffer`

Phần code Java NIO thực tế phải phân biệt ba giá trị từ `read()`:

- `n > 0`: có `n` byte mới; đưa **đúng đoạn này** vào decoder.
- `n == 0`: chưa có byte mới tại lần gọi, thường gặp khi socket non-blocking chưa sẵn sàng; không emit và không coi là EOF.
- `n == -1`: input stream kết thúc; gọi `decoder.endOfInput()` để kiểm tra frame dở dang rồi kết thúc phần đọc theo chính sách.
- `IOException`: lỗi I/O cần xử lý riêng, không đổi thành frame rỗng.

Ví dụ khung xử lý **trong một handler ứng dụng**; các biến `socket`, `buffer`, `decoder` và `handleMessage` phải được định nghĩa ngoài đoạn:

```java
int n = socket.read(buffer);

if (n > 0) {
    buffer.flip();
    byte[] chunk = new byte[buffer.remaining()];
    buffer.get(chunk);

    for (String message : decoder.accept(chunk)) {
        handleMessage(message);
    }
    buffer.clear();
} else if (n == 0) {
    // Non-blocking: trở về Selector/event loop để chờ tiếp.
} else {
    decoder.endOfInput();
    // Kết thúc nhận, đóng hoặc half-close theo giao thức.
}
```

Ví dụ này giả định `buffer` được chuẩn bị nhận dữ liệu từ lần đọc trước. Ở một ứng dụng thực tế cần xử lý lỗi callback, giới hạn số byte và trạng thái đóng tài nguyên.

**Hai mẫu quản lý buffer khác nhau:**

- **Decoder tự sở hữu pending bytes**, như `LengthDecoder` trong ví dụ: sau khi chuyển toàn bộ byte mới vào decoder có thể `buffer.clear()`. `clear()` chỉ reset `position/limit` và không có tác dụng xóa byte.
- **Decoder giữ phần chưa đủ trong chính read buffer**: khi chuyển sang chế độ đọc bằng `flip()`, parser tiêu thụ frame hoàn chỉnh, sau đó dùng `compact()` để giữ byte còn thiếu; không `clear()` nếu còn partial frame.

Không trộn lẫn hai cách để tránh mất dữ liệu hoặc đọc lại byte cũ. Mỗi kết nối giữ decoder và read buffer riêng.

### 8.1. Selector không quyết định ranh giới message

`SelectionKey.isReadable()` chỉ cho biết có khả năng đọc; nó **không hứa** rằng `read()` nhận đủ một frame, hoặc mỗi thông báo ready chứa một message. Trong event loop:

```text
Selector chọn key readable
           |
       channel.read(buffer)
         /      |       \
       n>0     n=0     n=-1
        |       |        |
    feed      chờ       EOF -> finalize decoder
   decoder   sự kiện    và đóng theo chính sách
        |
   emit 0..N frame
```

Nếu `read` trả `0`, đừng gọi liên tục trong vòng `while` không có cơ chế chờ: gây busy loop và tốn CPU. Trả điều khiển về selector/event loop và giữ state pending đến lượt sau.

## 9. Chiều ghi cần xử lý partial write

Cũng như `read()`, `SocketChannel.write(ByteBuffer)` có thể xử lý **ít byte hơn số byte còn lại**, đặc biệt trong non-blocking mode. Điều này không được phép làm thay đổi thứ tự frame:

```java
ByteBuffer frame = encode("Hello");
int written = socket.write(frame);
// Nếu frame.hasRemaining(), frame chưa được gửi xong.
```

Đây là snippet trong một phương thức có `socket` và `encode`. Khi còn byte trong frame, phải giữ chính buffer đó với `position` hiện tại để ghi tiếp. Nếu gọi `clear()` hoặc gửi frame tiếp theo ngay, có thể gây xen kẽ header/payload hoặc làm mất byte.

Một thiết kế phổ biến là **outbound queue** chứa `Deque<ByteBuffer>`; mỗi phần tử là một frame đã `flip()`. Khi có `OP_WRITE`, ghi phần tử đầu tiên cho đến khi hết byte hoặc socket tạm không nhận thêm:

```java
while (!outbound.isEmpty()) {
    ByteBuffer head = outbound.peek();
    int written = socket.write(head);

    if (head.hasRemaining()) {
        // Còn byte; giữ nguyên head ở đầu queue và chờ OP_WRITE.
        break;
    }
    outbound.remove();

    if (written == 0) {
        break;
    }
}
```

Đây là đoạn minh họa trong handler có sẵn `SocketChannel socket` và `Deque<ByteBuffer> outbound`. Trong event loop, chỉ đăng ký `OP_WRITE` khi có byte còn chờ và hủy interest này khi queue rỗng để tránh selector báo writable liên tục. Cần giới hạn tổng outbound bytes để xử lý client nhận chậm (backpressure).

**`write()==0` không phải EOF.** Nó nói lượt ghi này không chuyển byte; với non-blocking socket cần chờ một sự kiện phù hợp.

## 10. EOF, timeout và thông điệp bị cắt

Khi `read()` trả `-1`, protocol phải quyết định liệu buffer hiện có là frame hợp lệ hay còn thiếu dữ liệu.

| Trạng thái khi EOF | Cách diễn giải với protocol strict |
| --- | --- |
| Length decoder đang chờ header mới, không có byte dư | Kết thúc bình thường |
| Header mới nhận 1–3/4 byte | Truncated header |
| Đã nhận header length N, payload mới có K byte với K nhỏ hơn N | Truncated payload |
| Delimiter decoder không có pending bytes | Kết thúc bình thường |
| Delimiter decoder có pending bytes nhưng không có delimiter | Thiếu delimiter, nếu protocol đòi LF kết thúc |
| Delimiter protocol cho phép final line không có LF | Có thể emit dòng cuối, nhưng phải ghi rõ ngoại lệ này |

Không phải protocol nào cũng cho phép EOF thay thế delimiter. Nếu sử dụng mô hình line theo Unix, có thể chấp nhận dòng cuối không có LF; nếu framing yêu cầu LF bắt buộc, phải báo lỗi. **Hai bên phải thống nhất**.

Ngoài EOF còn có các chính sách timeout: client có thể gửi header rồi giữ kết nối mở mãi mà không gửi payload; decoder cần deadline cho frame, giới hạn số kết nối và cơ chế hủy thao tác chậm. TCP half-close có nghĩa phía gửi kết thúc output không nhất thiết đồng nghĩa phía nhận cũng đã đóng; ứng dụng nên phân biệt chiều dữ liệu.

## 11. Dữ liệu UTF-8 và delimiter

Nếu gửi `"Tiếng Việt"` theo length-prefix, header chứa số **byte UTF-8**, không chứa số ký tự Java. Một ký tự nhiều byte có thể bị chia giữa hai lần socket read; decoder nên đợi đủ payload rồi decode, hoặc dùng `CharsetDecoder` ở chế độ streaming.

Với delimiter LF `0x0A`, việc quét byte trước rồi decode cả frame là cách đơn giản nếu protocol chọn UTF-8 và không cho phép LF bên trong payload. Đối với JSON Lines, newline trong trường string phải được escape thành nội dung văn bản hợp lệ (ví dụ ký tự backslash+n) thay vì chèn LF thô.

Nếu delimiter là chuỗi dài như CRLF, một phần delimiter có thể nằm cuối read buffer và phần còn lại nằm đầu buffer sau. Khi scan trong từng chunk riêng, cần matcher có state hoặc giữ đoạn cuối đủ dài để nối với chunk sau.

Nếu dữ liệu nhị phân có thể chứa bất kỳ giá trị byte nào, **length-prefix thường đơn giản hơn** giải pháp delimiter phải escape tất cả lần xuất hiện của dấu phân cách.

## 12. Xử lý an toàn và giới hạn tài nguyên

**Với length-prefix:**

- Kiểm tra length âm/vượt `MAX_FRAME_BYTES` trước khi allocate.
- Giới hạn tổng số frame chờ xử lý, thời gian nhận frame và tổng byte trong queue.
- Nếu có compression, giới hạn kích thước sau giải nén.
- Nếu có schema có cấu trúc, validate version, type, payload format trước khi sử dụng.
- Đảm bảo không tính nhầm số char hoặc count ký tự Java thành byte count.

**Với delimiter:**

- Chỉ tích lũy tối đa `MAX_LINE_BYTES` trước delimiter, kể cả peer không bao giờ gửi delimiter.
- Nếu delimiter có thể xuất hiện trong payload, phải escape/quote theo định dạng hoặc chọn phương thức khác.
- Xác định CRLF và LF có được phép cùng tồn tại không.
- Xác định empty frame, trailing delimiter và EOF không có delimiter.

**Với cả hai:**

- Decoder độc lập cho mỗi kết nối.
- Có timeout, idle timeout, chính sách close, exception logging phù hợp.
- Không busy-loop khi read hoặc write trả 0.
- Quản lý inbound/outbound backpressure.
- Không tin dữ liệu đầu vào mạng chỉ vì đã xác định được ranh giới frame: framing **không** xác thực danh tính, không mã hóa và không bảo đảm dữ liệu an toàn.

## 13. Kiểm thử ở mọi điểm chia chunk

Vì ranh giới của TCP read tùy ý, nên tạo test đưa **cùng một luồng byte hợp lệ** vào decoder theo nhiều cách chia:

1. Từng byte một.
2. Toàn bộ byte trong một chunk.
3. Cắt giữa từng byte của header length.
4. Cắt giữa header và payload.
5. Cắt giữa byte UTF-8 nhiều byte.
6. Chunk có nhiều frame hoàn chỉnh và một phần frame sau.
7. Cắt giữa CR và LF của delimiter CRLF.
8. EOF khi header hoặc payload chưa hoàn chỉnh.
9. Header âm, header quá lớn, delimiter thiếu, dòng quá dài.

Bất biến mong muốn:

```text
decode(allBytes as one chunk)
  == decode(same bytes split into arbitrary chunks)
```

Ở đây `decode` so sánh danh sách frame **cùng nội dung và thứ tự**, giả định luồng byte hợp lệ và cùng trạng thái ban đầu. Đối với luồng không hợp lệ, cần kiểm tra cả loại lỗi và không emit frame thiếu dữ liệu.

Property-based testing/fuzzing rất hữu ích: sinh các chuỗi frame ngẫu nhiên theo encoder, nối thành stream, chia ngẫu nhiên thành các chunk, rồi kiểm tra decoder tạo đúng tập frame ban đầu. Những test này phát hiện bug mà các bài thử “một write, một read” thường bỏ sót.

## 14. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cho rằng một `write` bằng một `read` | Frame bị chia/gộp sai | Parser streaming với state |
| Đọc một lần rồi `getInt()` ngay | Thiếu byte header | Đợi đủ 4 byte |
| Header dùng `String.length()` | Sai độ dài UTF-8 | Đếm byte sau encoding |
| Encoder/decoder khác endian | Độ dài bị hiểu sai | Chọn BIG_ENDIAN và test wire bytes |
| Dùng length mạng để allocate không giới hạn | OutOfMemory/DoS | Validate trước allocation |
| Chỉ emit một frame mỗi chunk | Bỏ frame tiếp | Lặp xử lý hết chunk |
| Không giữ state frame dở | Mất header/payload giữa các lần read | `compact()` hoặc decoder độc lập |
| Delimiter xuất hiện trong payload | Tách sớm | Escape/encoding/length-prefix |
| Không giới hạn byte khi chờ delimiter | Bộ nhớ phình to | MAX_LINE_BYTES và deadline |
| Chỉ tìm CRLF bên trong từng chunk | Bỏ delimiter bị chia | Streaming delimiter matcher |
| `read()==0` xem là EOF | Ngắt kết nối sai | Chỉ `-1` là EOF |
| `write()==0` thì lặp liên tục | Busy CPU | `OP_WRITE`, queue và backpressure |
| `clear()` buffer trước khi giữ byte dư | Mất frame dở | `compact()` hoặc state machine |
| EOF khi frame dở vẫn emit | Dữ liệu thiếu | Báo truncated frame theo strict protocol |

## 15. Tự kiểm tra

**1.** Client gọi `write` hai lần cho hai message, server nhận một `read` chứa cả hai. TCP có lỗi không?  
**Đáp án:** Không. Framing tầng ứng dụng phải tách hai message.

**2.** Length header là 4 byte, một lượt read mới nhận 2 byte. Decoder có thể đọc `getInt()` không?  
**Đáp án:** Không. Phải đợi đủ 4 byte rồi đọc length.

**3.** Payload dài 5 byte, lần đầu chỉ nhận 3. Có nên emit luôn?  
**Đáp án:** Không. Giữ 3 byte và đợi 2 byte tiếp, hoặc báo truncated nếu EOF.

**4.** Một chunk chứa frame A, frame B và hai byte đầu của frame C. Decoder làm gì?  
**Đáp án:** Emit A và B, giữ hai byte đầu của C.

**5.** Line protocol dùng LF, nhưng dữ liệu người dùng chứa newline. Có thể gửi thẳng không?  
**Đáp án:** Không, nếu không có escape/quote; có thể chuyển sang length-prefix.

**6.** CRLF chia thành hai chunk ở CR và LF. Parser cần gì?  
**Đáp án:** Giữ trạng thái delimiter chưa hoàn chỉnh qua các chunk.

**7.** Peer gửi header length 2.000.000.000 byte. Có nên allocate ngay?  
**Đáp án:** Không. Validate giới hạn và reject nếu vượt.

**8.** `SocketChannel.write` trả 0 nhưng frame còn byte. Có thể gửi frame tiếp theo trước không?  
**Đáp án:** Không. Giữ frame đầu trong queue và chờ có khả năng ghi.

**9.** EOF đến khi length decoder đang giữ header mới chỉ có 3 byte. Có thể coi là message rỗng không?  
**Đáp án:** Không. Trong strict framing đây là truncated header.

## 16. Checklist triển khai

- Chốt wire format: byte order, header length, length semantics, charset/delimiter, maximum, frame rỗng, version.
- Decoder duy trì state giữa các `read` và xử lý 0..N frame cho mỗi chunk.
- Producer xử lý partial `write` bằng `ByteBuffer.position()` và queue.
- NIO event loop phân biệt `read>0`, `read==0`, `read==-1`.
- Quy định EOF/timeout khi frame chưa hoàn chỉnh.
- Giới hạn kích thước frame/dòng, tổng queue, số kết nối và thời gian chờ.
- Test chia/gộp frame ở mọi ranh giới và thử dữ liệu không hợp lệ.
- Chỉ giải mã UTF-8 khi đủ byte, hoặc dùng decoder streaming; dùng strict validation khi cần.
- Đo hiệu năng và backpressure dưới tải, không dựa vào hành vi localhost.

## Tham khảo API chính thức

- Java SE 21 — `SocketChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 21 — `ReadableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 21 — `WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html
- Java SE 21 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21 — `Selector`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 21 — `CharsetDecoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
