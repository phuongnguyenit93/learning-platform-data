# Đọc đủ số byte cần thiết và giữ lại phần dữ liệu của thông điệp tiếp theo

## Mục tiêu

Trong TCP, một lần `read` **không tương ứng** một thông điệp ứng dụng. Sau bài này, bạn có thể:

- Giải thích vì sao TCP đưa tới ứng dụng **luồng byte liên tục**, nên thông điệp có thể bị chia thành nhiều lần đọc hoặc nhiều thông điệp cùng nằm trong một lần đọc.
- Thiết kế cách xác định **ranh giới thông điệp** (framing), đặc biệt với giao thức có **4 byte độ dài + payload**.
- Đọc **đúng số byte cần** bằng `DataInputStream.readFully` hoặc vòng lặp `InputStream.read`, kiểm tra EOF và không tiêu thụ quá phạm vi thông điệp.
- Giữ lại byte chưa thuộc thông điệp hoàn chỉnh bằng bộ đệm tích lũy (cumulation buffer) với `ByteBuffer.flip()`, `mark()`, `reset()`, `compact()`.
- Phân biệt tình trạng **thiếu byte**, **đủ một frame** và **có thêm phần của frame kế tiếp**; tránh nhầm `available()`, `readAllBytes()` hoặc một lần `read` là ranh giới thông điệp.
- Viết và kiểm tra ví dụ Java 17+ có cả cách đọc tuần tự và bộ giải mã xử lý những chunk bị tách/gộp.

**Phạm vi:** ứng dụng dùng TCP theo giao thức do hai đầu thống nhất. Các ví dụ mã hóa payload văn bản bằng UTF-8, nhưng **độ dài trong header là số byte**, không phải số ký tự Java.

## 1. TCP không lưu ranh giới thông điệp cho ứng dụng

TCP đảm bảo luồng byte được chuyển theo thứ tự trên một kết nối khi không phát sinh lỗi; TCP **không** lưu lại việc phía gửi đã gọi `write` bao nhiêu lần để phía nhận khôi phục từng “tin nhắn” ứng dụng.

Giả sử phía gửi lần lượt gọi:

~~~java
output.write(frameA);
output.write(frameB);
~~~

Phía nhận có thể quan sát:

~~~text
Sender:   [frame A][frame B]       (hai lần write)
Receiver: [A phần 1] [A phần 2 + B]      hoặc
          [A + B]                         hoặc
          [A][B phần 1][B phần 2]         ...
~~~

Hình thức chia chunk phụ thuộc buffer, TCP segmentation, lịch chạy và thời điểm đọc. Không có bảo đảm “mỗi `write` tạo đúng một `read`”, dù trong thử nghiệm localhost tình cờ thấy chúng bằng nhau.

Ba tình huống cần phân biệt:

| Tình huống | Byte thu được trong một lần đọc | Kết luận |
|---|---|---|
| **Fragmented** | Chỉ một phần của frame hiện tại | **Chưa** xử lý; giữ trạng thái, đọc tiếp. |
| **Exact** | Vừa đủ hết frame hiện tại | Xử lý frame, chuẩn bị đọc frame kế tiếp. |
| **Coalesced / dư** | Hết frame hiện tại và một phần hoặc toàn bộ frame tiếp theo | Xử lý frame đã đủ, **giữ lại** byte dư để phân tích tiếp; không bỏ đi. |

Cả ba đều là hành vi hợp lệ. Số byte nhận được phải được diễn giải bằng **quy tắc framing của giao thức ứng dụng**.

## 2. Hợp đồng framing: 4 byte độ dài và payload

Một cách thông dụng là *length-prefix framing*. Trong bài này quy ước cụ thể:

~~~text
Frame = [4 byte unsigned-like length in network byte order][payload bytes]

Header: 4 byte big-endian, đọc bằng Java DataInputStream.readInt()
Length: số byte payload; trong giao thức mẫu giới hạn 0..1024
Payload: byte UTF-8; có thể là thông điệp rỗng nếu length=0
~~~

`readInt()` đọc số nguyên **signed** 32-bit big-endian. Dù người gửi coi header như một độ dài không âm, phải từ chối số âm và số lớn hơn giới hạn thỏa thuận **trước khi cấp phát mảng**.

Ví dụ hai thông điệp liên tục:

~~~text
Frame 1 "HELLO": 00 00 00 05  48 45 4C 4C 4F
Frame 2 "BYE":   00 00 00 03  42 59 45

Luồng TCP: 00 00 00 05 48 45 4C 4C 4F 00 00 00 03 42 59 45
            |--header--| |--HELLO--| |--header--| |--BYE--|
~~~

Có **16 byte** trên luồng: 9 byte của frame `HELLO` và 7 byte của frame `BYE`. Một `read` có thể trả cả 16 byte, 1 byte, hoặc một số lượng khác. Để hoàn tất frame đầu, parser chỉ được tiêu thụ **4 + 5 = 9 byte**. Bảy byte còn lại phải dùng cho frame thứ hai.

**Chú ý Unicode:** độ dài trên wire phải tính bằng `payload.getBytes(StandardCharsets.UTF_8).length`. Ví dụ `"Việt".length()` là **4 đơn vị UTF-16**, nhưng UTF-8 của chuỗi ấy là **6 byte** (chữ `ệ` chiếm 3 byte). Dùng `String.length()` để gửi header sẽ khiến bên nhận cắt sai payload và lệch toàn bộ những frame theo sau.

### Bất biến của một parser đúng

Ở mỗi thời điểm, parser có **vị trí đọc** trong dãy byte đã nhận:

1. Nếu chưa đủ **4 byte header**, không được cố đọc độ dài; giữ byte header còn thiếu.
2. Khi đã có header, kiểm tra độ dài thuộc `0..MAX_FRAME`.
3. Nếu chưa đủ `length` byte payload, **đừng xử lý thông điệp chưa hoàn chỉnh**; giữ nguyên phần cần thiết và chờ thêm.
4. Khi đủ, tiêu thụ **chính xác** `4 + length` byte của frame vừa hoàn tất, phát thông điệp.
5. Mọi byte **nằm sau** vị trí đó thuộc phần chưa phân tích của một hay nhiều frame sau. Không xóa, không decode sớm, không đọc quá rồi bỏ.

~~~text
[đã parse xong][frame đầy đủ][header/payload chưa đủ của frame kế tiếp]
               ^---------- tiêu thụ ----------^
                                                     ^-- giữ lại
~~~

Từ một chunk có thể hoàn tất **0, 1 hoặc nhiều frame**. Parser phải có vòng lặp xử lý các frame đầy đủ, rồi giữ phần còn lại.

## 3. Cách đơn giản với blocking stream: yêu cầu đúng số byte

Với `Socket.getInputStream()` ở chế độ blocking, `InputStream.read(byte[])` chỉ hứa đọc **tối đa** số byte được yêu cầu; trả về ít hơn là bình thường. Trong nhiều trường hợp, cách dễ đúng nhất là dùng `DataInputStream`:

~~~java
static String readFrame(DataInputStream in) throws IOException {
    int length = in.readInt(); // Đọc đủ 4 byte header, big-endian.

    if (length < 0 || length > 1024) {
        throw new IOException("Invalid frame length: " + length);
    }

    byte[] payload = new byte[length];
    in.readFully(payload);    // Chỉ trở về khi đủ length byte.
    return new String(payload, StandardCharsets.UTF_8);
}
~~~

**Đoạn mã minh họa phương thức**, đặt trong lớp đã import `java.io.DataInputStream`, `java.io.IOException` và `java.nio.charset.StandardCharsets`. Một lần `readFrame` tiêu thụ **đúng** 4 byte header và đúng `length` byte payload:
- `readInt()` sẽ đợi đủ header hoặc ném `EOFException` nếu EOF xảy ra trước khi đủ.
- `readFully(payload)` đọc lặp đến đủ byte, hoặc ném `EOFException` nếu luồng kết thúc trước.
- Nếu đã có dữ liệu frame tiếp theo trong luồng, nó **chưa bị lấy ra khỏi wrapper stream**. Lần `readFrame` kế tiếp đọc tiếp tại đúng vị trí còn lại.

Khi bọc `BufferedInputStream`, tầng buffer nội bộ có thể **đọc trước** dữ liệu từ socket. Điều đó vẫn đúng vì byte đọc trước được **giữ bên trong chính buffer còn sống**. Cần giữ **một đối tượng stream wrapper xuyên suốt kết nối**, không tạo một `BufferedInputStream` mới sau mỗi frame và bỏ wrapper cũ (hành động đó có thể làm mất các byte đã prefetch).

Ví dụ sử dụng với socket đang mở (mã minh họa, không phải chương trình tự chạy):

~~~java
socket.setSoTimeout(5_000); // Timeout cho mỗi thao tác đọc blocking.
DataInputStream input = new DataInputStream(
    new BufferedInputStream(socket.getInputStream())
);

String first = readFrame(input);
String second = readFrame(input); // Đọc tiếp đúng nơi first dừng.
~~~

Cần import `java.net.Socket`, `java.io.BufferedInputStream`, `java.io.DataInputStream`; code trên giả định biến `socket` đã được khởi tạo và phương thức `readFrame` ở cùng lớp. Chỉ **một luồng đọc** nên sở hữu input stream của một kết nối để tránh hai reader tranh nhau byte. Khi đóng socket, đóng stream và socket đúng vòng đời của kết nối; ví dụ trên không trình bày trọn vòng đời tài nguyên.

**Ưu điểm:** không cần buffer ứng dụng tự quản lý nếu chỉ đọc tuần tự bằng blocking I/O và API không đọc vượt số byte cần. **Giới hạn:** nếu framework/event loop đã trao bạn **cả chunk chứa byte dư**, bạn phải tự quản lý byte dư như phần tiếp theo.

## 4. Vì sao một vòng lặp `read` vẫn cần thiết?

Nếu không dùng `DataInputStream.readFully`, cách tương đương là tích lũy cho đủ **một vùng byte đã biết độ dài**:

~~~java
static void readExactly(InputStream input, byte[] target)
        throws IOException {
    int position = 0;
    while (position < target.length) {
        int n = input.read(
            target, position, target.length - position
        );

        if (n == -1) {
            throw new EOFException(
                "Truncated frame: read " + position
                + " of " + target.length + " bytes"
            );
        }
        if (n == 0) {
            // Với InputStream chuẩn và len > 0 không nên xảy ra;
            // tránh vòng lặp vô hạn với implementation bất thường.
            throw new IOException("InputStream made no progress");
        }
        position += n;
    }
}
~~~

Đây là **đoạn phương thức** cần import `java.io.InputStream`, `java.io.IOException` và `java.io.EOFException`. Bất biến vòng lặp: `position` là số byte đã có; lần tiếp theo chỉ yêu cầu `target.length - position` byte, nên không vượt ranh giới mục tiêu.

Đối chiếu các API Java 17+:

| API | Hành vi |
|---|---|
| `InputStream.read(b, off, len)` | Trả về tối đa `len` byte, có thể ít hơn; `-1` khi EOF. |
| `DataInputStream.readFully(b)` | Đọc đủ `b.length` byte hoặc ném `EOFException`/`IOException`. |
| `InputStream.readNBytes(len)` | Cố đọc tới `len` byte; nếu EOF sớm, có thể trả mảng ngắn hơn. **Phải kiểm tra `result.length`**. |
| `InputStream.readAllBytes()` | Đọc cho tới **EOF**, không phù hợp với TCP connection tồn tại lâu để chứa nhiều thông điệp. |
| `InputStream.available()` | Ước lượng byte có thể đọc **không cần block**; **không phải** tổng độ dài frame hay độ dài thông điệp. |

Khi làm việc với `SocketChannel` nonblocking, `read` có thể trả **0** do hiện không có byte sẵn. Đó là semantics khác: giữ trạng thái decoder và chờ tín hiệu khả đọc (ví dụ `Selector`), **không spin liên tục**. Không áp máy móc `DataInputStream.readFully` blocking vào NIO nonblocking.

## 5. Trường hợp đọc trước: giữ lại dữ liệu của frame tiếp theo

Khi chương trình nhận các khối byte từ một event loop hoặc đọc socket vào `byte[4096]`, một khối có thể kết thúc giữa header của frame kế tiếp. Không thể bỏ byte còn dư vì chúng đã bị lấy ra khỏi stream; cũng không thể “đặt lại” byte vào socket một cách tùy tiện.

Ví dụ với hai frame ở trên, chia luồng thành ba chunk:

| Chunk | Byte nhận trong lần đó | Parser sau khi nhận |
|---|---|---|
| `1` (7 byte) | `00 00 00 05 48 45 4C` | Có header 5 byte payload nhưng mới nhận `HEL`; chưa phát frame. **Giữ 7 byte**. |
| `2` (4 byte) | `4C 4F 00 00` | Đủ `HELLO` nên phát frame 1; `00 00` là **2 byte đầu header frame 2**, **giữ 2 byte**. |
| `3` (5 byte) | `00 03 42 59 45` | Ghép với 2 byte cũ thành header `00 00 00 03` và `BYE`; phát frame 2; còn 0 byte. |

Một decoder nhận chunk phải có **bộ nhớ qua nhiều lời gọi**. Tại cùng một thời điểm, nó cần biết byte nào đã phân tích xong và byte nào còn dở. Chẳng hạn:
- `ByteBuffer` ban đầu ở **write mode**: `position` chỉ vị trí sẽ ghi byte mới; `limit` là dung lượng.
- Sau `put(...)`, gọi `flip()` để chuyển sang **read mode**: `position = 0`, `limit` là số byte hiện có.
- Khi đủ header, gọi `mark()` để đánh dấu vị trí bắt đầu header, đọc `length`. Nếu payload chưa đủ, `reset()` để quay lại **đầu header**, giữ toàn bộ frame chưa đủ.
- Sau khi xử lý hết các frame đầy đủ, `compact()` đưa **mọi byte còn lại** sang đầu buffer, chuyển về write mode để nhận chunk kế.

**Quan trọng:** `compact()` giữ byte từ `position` tới `limit`, không phải xóa sạch buffer. Dù byte còn lại chỉ là 1 byte của header, nó vẫn được bảo toàn cho lần `offer` sau.

## 6. Ví dụ chạy được: đọc đủ và giữ byte dư

File **`TcpFramingDemo.java`** dưới đây minh họa hai đường:
- `readFrame` dùng `readInt` + `readFully` trên luồng bị giới hạn tối đa 2 byte mỗi `read(byte[])`.
- `FrameDecoder.offer` nhận những chunk bất kỳ, phát các frame hoàn chỉnh và dùng `compact()` giữ phần của frame sau.

Ví dụ chạy **trong bộ nhớ**, không mở socket nên stdout xác định. Tại mạng thật, byte đầu vào sẽ đến từ socket hoặc I/O callback thay vì `ByteArrayInputStream`.

~~~java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class TcpFramingDemo {
    private static final int MAX_FRAME = 1024;

    static byte[] wire(String... messages) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        for (String message : messages) {
            byte[] payload = message.getBytes(StandardCharsets.UTF_8);
            out.writeInt(payload.length);
            out.write(payload);
        }
        return bytes.toByteArray();
    }

    static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_FRAME) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    static final class FrameDecoder {
        private ByteBuffer pending = ByteBuffer.allocate(8);

        List<String> offer(byte[] chunk, int from, int to)
                throws IOException {
            int count = to - from;
            if (from < 0 || count < 0 || to > chunk.length) {
                throw new IndexOutOfBoundsException();
            }

            ensureSpace(count);
            pending.put(chunk, from, count);
            pending.flip();

            List<String> messages = new ArrayList<>();
            while (pending.remaining() >= Integer.BYTES) {
                pending.mark(); // Đầu header của frame kế.
                int length = pending.getInt();
                if (length < 0 || length > MAX_FRAME) {
                    throw new IOException(
                        "Invalid frame length: " + length);
                }
                if (pending.remaining() < length) {
                    pending.reset(); // Payload chưa đủ.
                    break;
                }

                byte[] payload = new byte[length];
                pending.get(payload);
                messages.add(new String(
                    payload, StandardCharsets.UTF_8));
            }
            pending.compact(); // Giữ byte của frame kế tiếp.
            return messages;
        }

        int retainedBytes() {
            return pending.position(); // Trong write mode.
        }

        private void ensureSpace(int additional) {
            if (pending.remaining() >= additional) {
                return;
            }
            int required = pending.position() + additional;
            ByteBuffer larger = ByteBuffer.allocate(
                Math.max(required, pending.capacity() * 2));
            pending.flip();
            larger.put(pending);
            pending = larger;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = wire("HELLO", "BYE");

        InputStream fragmented = new FilterInputStream(
                new ByteArrayInputStream(bytes)) {
            @Override
            public int read(byte[] b, int off, int len)
                    throws IOException {
                return super.read(b, off, Math.min(len, 2));
            }
        };
        DataInputStream in = new DataInputStream(fragmented);
        System.out.println("readFully 1: " + readFrame(in));
        System.out.println("readFully 2: " + readFrame(in));

        FrameDecoder decoder = new FrameDecoder();
        System.out.println("chunk 1: "
            + decoder.offer(bytes, 0, 7)
            + " | retained=" + decoder.retainedBytes());
        System.out.println("chunk 2: "
            + decoder.offer(bytes, 7, 11)
            + " | retained=" + decoder.retainedBytes());
        System.out.println("chunk 3: "
            + decoder.offer(bytes, 11, bytes.length)
            + " | retained=" + decoder.retainedBytes());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TcpFramingDemo.java
java TcpFramingDemo
~~~

Stdout chính xác:

~~~text
readFully 1: HELLO
readFully 2: BYE
chunk 1: [] | retained=7
chunk 2: [HELLO] | retained=2
chunk 3: [BYE] | retained=0
~~~

### Giải thích code

1. `wire("HELLO", "BYE")` dùng `DataOutputStream.writeInt` gửi độ dài 4 byte big-endian, rồi `write` payload UTF-8; giao thức của sender và receiver hoàn toàn khớp.
2. `fragmented` buộc `read(byte[], off, len)` chỉ trả tối đa 2 byte mỗi lần, nhưng `DataInputStream.readFully` vẫn nhận được cả `HELLO` và `BYE` đúng thứ tự. Đây là kiểm thử **short read**, không giả lập độ trễ mạng.
3. `FrameDecoder.offer(bytes, 0, 7)` nhận 7 byte đầu, chưa đủ payload 5 byte; `pending.reset()` đưa con trỏ về đầu header và `compact()` giữ 7 byte.
4. Lần hai bổ sung 4 byte: parser đủ 9 byte frame `HELLO`, còn 2 byte đầu header `BYE` trong `pending`. `compact()` giữ chính **2 byte đó**.
5. Lần ba bổ sung 5 byte, đủ 4 byte header và 3 byte payload `BYE`. Parser phát `BYE`, còn 0 byte.
6. Vòng `while` có thể xuất **nhiều** frame trong một lần `offer` nếu chunk chứa nhiều frame hoàn chỉnh; nếu phần cuối chưa đủ thì giữ lại. Không có nhánh nào làm mất byte của frame sau.

Ví dụ minh họa cách cấp phát buffer tăng kích thước theo chunk và chưa triển khai giới hạn tổng bộ nhớ cho input bất thường. Trong hệ thống thật, phải **giới hạn kích thước chunk, lượng byte đang chờ, độ dài frame, tốc độ/timeout** hoặc dùng state machine xử lý dòng với buffer cố định. `MAX_FRAME` ngăn payload quá lớn nhưng **không tự ngăn** một lời gọi `offer` đưa vào một chunk cực lớn; không coi code demo là decoder sẵn sàng đưa lên Internet mà không thêm giới hạn.

## 7. Ba lỗi thường khó phát hiện

### Lỗi A: xem `read` là một thông điệp

~~~java
byte[] buf = new byte[4096];
int n = input.read(buf);
String message = new String(buf, 0, n, StandardCharsets.UTF_8);
~~~

Đoạn trên chỉ tạo text từ **chunk vừa nhận**, không chứng minh chunk là một frame. Nếu byte UTF-8 nhiều byte bị chia ở ranh giới lần đọc, decode từng chunk còn có thể làm hỏng ký tự (replacement character). Chỉ decode **payload đã đủ** sau khi framing.

### Lỗi B: đọc nhiều hơn cần rồi bỏ phần dư

~~~java
int n = input.read(buf);
processOnlyFirstFrame(buf, n);
// Quên lưu buf từ cuối frame đầu tới n.
~~~

Nếu `n` bao gồm byte đầu của frame kế tiếp, parser đã **tiêu thụ** chúng từ socket mà lại loại bỏ khỏi bộ nhớ. Lần đọc sau bắt đầu giữa frame, header sẽ sai và toàn bộ stream mất đồng bộ. Phải giữ vùng `[endOfFirstFrame, n)` hoặc dùng decoder với cursor/`compact`.

### Lỗi C: cho rằng EOF, timeout và short read giống nhau

- `n > 0` nhưng ít hơn mong muốn: **short read hợp lệ**, tiếp tục tích lũy.
- `n == -1`: **EOF** — đầu bên kia đã kết thúc chiều truyền; nếu đang giữa header/payload thì là **truncated frame**.
- `SocketTimeoutException`: thao tác đọc blocking chờ quá `SO_TIMEOUT`, **không** có nghĩa frame kết thúc. Tùy chính sách, tiếp tục với state đã giữ hoặc đóng kết nối; không tự coi byte thiếu là thông điệp hoàn chỉnh.
- `SocketChannel.read` nonblocking trả `0`: chưa có byte; đợi readiness, không coi là EOF.

`readInt()` khi EOF trước hoặc trong header thường ném `EOFException`; nếu muốn phân biệt **đóng sạch ở ranh giới giữa hai frame** với **header bị cắt dở**, phải viết phép đọc header có thể nhận biết `-1` trước byte đầu tiên. Đừng coi `EOFException` luôn là một thông điệp hợp lệ đã hoàn tất.

## 8. Giới hạn, hiệu năng và vòng đời kết nối

**Kiểm tra length trước cấp phát.** Header đến từ mạng là dữ liệu không đáng tin. Đặt `MAX_FRAME` theo giao thức và quota; từ chối length âm, quá giới hạn, hoặc định dạng không hợp lệ. Nếu chuyển `long` sang `int` hoặc tính `header + payload`, kiểm tra tràn số. Với payload lớn, cân nhắc xử lý streaming theo từng phần vào sink có giới hạn thay vì tạo mảng khổng lồ.

**Timeout và slow sender.** `socket.setSoTimeout(5_000)` áp dụng cho thao tác đọc blocking trên socket; nó **không đồng nghĩa** với deadline 5 giây cho toàn frame. Bên gửi có thể nhỏ giọt dữ liệu và kéo dài tổng thời gian. Sản phẩm thật cần tổng deadline, giới hạn thời gian chờ giữa các byte, quota và chính sách ngắt kết nối.

**Chỉ một parser sở hữu byte stream.** Nhiều thread cùng đọc một `InputStream` có thể lấy mất header/payload của nhau. Cách ổn định là một reader/decoder chịu trách nhiệm framing, sau đó dispatch **thông điệp đã hoàn chỉnh** sang các worker xử lý nghiệp vụ.

**Đồng bộ giao thức hai đầu.** Hai phía phải thống nhất bề rộng/endianness header, số byte length có bao gồm header không, charset payload, giới hạn kích thước và thứ tự frame. `DataInputStream.readUTF()`/`DataOutputStream.writeUTF()` dùng định dạng **modified UTF-8** kèm cơ chế length riêng; chúng **không** tự tương thích với giao thức mẫu 4-byte length + UTF-8 thông thường trong bài.

**Buffer qua nhiều frame.** Nếu bọc input bằng `BufferedInputStream`, giữ wrapper suốt vòng đời stream; nếu dùng `FrameDecoder`, giữ cùng instance qua các chunk. Không tự xóa `pending` khi chưa xử lý hết frame và không cố đọc lại từ socket những byte đã được callback trao cho ứng dụng.

**Lỗi là trạng thái của kết nối.** Nếu gặp header sai hoặc payload bị cắt, cân nhắc đóng kết nối và tái tạo parser từ đầu trên kết nối mới; cố “đoán vị trí” frame tiếp theo trong byte stream không có marker đồng bộ thường không đáng tin cậy.

## 9. Những kiểu framing khác và giới hạn của từng kiểu

| Cách phân khung | Nguyên tắc | Điểm cần lưu ý |
|---|---|---|
| **Fixed-size** | Mọi thông điệp có đúng N byte | Chỉ phù hợp khi kích thước luôn cố định; cần đọc đủ N. |
| **Length-prefix** | Header báo độ dài payload | Kiểm tra độ dài; đọc đủ; giữ phần sau frame. |
| **Delimiter-based** | Ký tự/byte đặc biệt ngăn thông điệp, như LF | Payload cần escape delimiter hoặc quy tắc encoding; delimiter có thể nằm ở nhiều chunk. |
| **EOF-delimited** | EOF đánh dấu kết thúc | Chỉ phù hợp khi một chiều kết nối kết thúc sau nội dung; không phù hợp với nhiều message trên kết nối lâu dài nếu không thêm cấu trúc. |

Với delimiter-based, không thể chỉ tìm `'\n'` trong **mỗi chunk riêng** rồi bỏ phần trước/sau: cần giữ các byte chưa hoàn chỉnh qua các lần đọc. Với length-prefix, ranh giới do số byte quy định nên payload hoàn toàn có thể chứa byte giống delimiter mà không gây nhầm lẫn.

## 10. Checklist kiểm thử decoder

Khi kiểm thử giao thức thực, cần tạo những dữ liệu đầu vào có thể tái lập:

1. **Header bị chia nhỏ:** 4 byte length đến lần lượt `1 + 1 + 2`; decoder không được đọc length sớm hoặc phát thông điệp giả.
2. **Payload bị chia nhỏ:** header đã đủ nhưng payload đến nhiều chunk; chỉ phát sau byte cuối.
3. **Hai frame cùng một chunk:** phát cả hai theo thứ tự.
4. **Một frame và header kế tiếp chưa đủ:** phát frame đầu, giữ đúng byte của header sau.
5. **Frame rỗng:** length 0 hợp lệ nếu giao thức cho phép.
6. **Truncated EOF:** thiếu một byte header/payload thì báo lỗi thích hợp; không phát thông điệp dở.
7. **Length âm hoặc quá `MAX_FRAME`:** từ chối trước khi cấp phát hoặc tăng buffer vượt quota.
8. **Payload đa byte UTF-8:** độ dài header là `byte[].length`; không decode từng phần ngay giữa một ký tự.
9. **Chunk nhận kích thước ngẫu nhiên:** chia cùng một chuỗi wire thành nhiều phân hoạch, rồi so sánh danh sách frame và trạng thái byte dư với kết quả chuẩn.
10. **Giới hạn tài nguyên:** người gửi kéo dài, gửi length rất lớn, gửi dữ liệu rác hoặc duy trì nhiều kết nối song song không được làm hệ thống cấp phát vô hạn.

Điều nên assert là **danh sách frame được phát và phần byte chưa đọc**, không phải số `read` mà hệ điều hành chọn trả về.

## 11. Bài tập tự luyện

1. Tại sao hai lời gọi `socket.getOutputStream().write(...)` ở sender không bảo đảm receiver sẽ có đúng hai lời gọi `read(...)`?
2. Với luồng gồm `00 00 00 05 HELLO 00 00 00 03 BYE`, parser nhận 11 byte đầu thì phải phát những gì và giữ bao nhiêu byte?
3. Sửa `FrameDecoder` để khi `offer` nhận chunk chứa **cả hai** frame, kết quả trả ra có hai thông điệp và `retainedBytes() == 0`. Cần sửa vòng `while` không?
4. Thử payload `"Việt"`. Vì sao header dùng `"Việt".length()` làm giá trị sẽ sai? Hãy kiểm chứng length UTF-8.
5. Thiết kế test cho trường hợp chỉ nhận 3/4 byte header rồi phía gửi đóng kết nối.
6. Nêu điều gì có thể xảy ra nếu mỗi lần đọc một frame lại khởi tạo `new BufferedInputStream(socket.getInputStream())` và bỏ wrapper cũ.
7. Nếu dùng `InputStream.readNBytes(100)` nhưng chỉ nhận 73 byte do EOF, điều kiện nào quyết định đó là frame hợp lệ hay bị cắt dở?
8. Tại sao không nên dùng `input.available() == expectedLength` để xác định đã nhận đủ frame?

**Đáp án cốt lõi:** (1) TCP chỉ giữ thứ tự byte; (2) phát `HELLO`, giữ **2 byte đầu header frame `BYE`**; (3) không cần sửa nếu vòng lặp `while` đã parse tới khi thiếu byte, lúc đó trả cả hai; (4) UTF-8 cần **6 byte**, khác 4 đơn vị UTF-16; (5) phát hiện truncated header và không phát frame; (6) mất byte prefetch; (7) chỉ hợp lệ nếu framing thật sự yêu cầu 73 byte, còn mong đợi 100 thì truncated; (8) `available` không phản ánh tổng byte của message hay byte sẽ đến sau.

## 12. Ghi nhớ

- **TCP là byte stream, không có message boundary.** Framing thuộc giao thức ứng dụng.
- **Đọc đủ**: dùng `readFully` hoặc vòng lặp tích lũy chính xác `remaining` byte, xử lý EOF và timeout riêng.
- **Không đọc dư rồi bỏ.** Nếu đã đọc được chunk chứa byte của frame tiếp theo, giữ phần chưa parse với cursor/buffer; `compact()` là một cách thực hiện.
- **Parse theo byte.** Header length của UTF-8 payload phải đo bằng số **byte**; chỉ decode thành `String` sau khi đủ payload.
- **Một parser cho một stream**, có giới hạn length/buffer, timeout và test với mọi kiểu chia/gộp chunk.

### Tài liệu tham khảo

- [Oracle Java SE 21 — InputStream: read, readNBytes, available](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
- [Oracle Java SE 21 — DataInputStream và readFully](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html)
- [Oracle Java SE 21 — ByteBuffer: flip, compact, mark, reset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
- [Oracle Java SE 21 — Socket: setSoTimeout, getInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293.html)
