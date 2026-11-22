# Chia một thông điệp qua nhiều lần ghi và ghép nhiều thông điệp trong một lần ghi

## Mục tiêu của thực nghiệm

TCP mang một **luồng byte có thứ tự**, chứ không truyền một danh sách các “message” mà ứng dụng có thể tự động nhận đúng ranh giới. Vì vậy:

- Một message của ứng dụng có thể được người gửi **chia thành nhiều lần gọi `OutputStream.write(...)`**.
- Nhiều messages có thể được người gửi **ghép thành một mảng byte rồi gửi bằng một lần `write(...)`**.
- Ở đầu nhận, một lần `InputStream.read(buffer)` có thể nhận **ít hơn một message, đúng một message, nhiều messages hoặc một đoạn bất kỳ của chúng**; chương trình **không được dựa vào số byte/một lần read để nhận biết ranh giới message**.
- TCP giữ thứ tự byte trên một connection khi truyền thành công; **không** hứa các lần gọi `write` ứng với các lần gọi `read`, cũng không có cơ chế “giữ nguyên message boundaries” của ứng dụng.

Đây là bài **Thực nghiệm mạng bằng Java 17+**. Ta chủ động làm thay đổi **hình dạng các lần ghi ở phía gửi** nhưng vẫn buộc bên nhận khôi phục **cùng những thông điệp logic**. Cách đúng là tạo giao thức đóng khung (*framing*) ở tầng ứng dụng, ví dụ **4 byte độ dài + payload**, **dấu xuống dòng**, hoặc kích thước cố định khi contract thích hợp.

Bài gồm bốn chương trình **độc lập, đã biên dịch và chạy kiểm chứng trên JDK tương thích Java 17**:

1. `TcpWriteShapeLab.java`: một frame chia **3 lần write**, hai frames khác ghép **1 lần write**, server nhận đúng `[ALPHA, RED, BLUE]` trên loopback.
2. `IncrementalFrameDecoderDemo.java`: cho decoder nhận các **chunks tùy ý**: một header bị chia, payload bị chia, rồi hai frames trong cùng chunk.
3. `TruncatedFrameDefenseDemo.java`: phân biệt EOF ở ranh giới frame hợp lệ với header/body bị cắt, giới hạn length để chặn dữ liệu quá lớn.
4. `LineFramingLab.java`: thí nghiệm tương tự với **dấu `\n`** và `BufferedReader.readLine()`, làm rõ ưu/nhược điểm delimiter framing.

Các ví dụ dùng `127.0.0.1` và port động, không cần Internet; các lời gọi `Socket` có timeout hợp lý. **Không lấy số lần `read` hoặc TCP segments quan sát được trên một máy làm một cam kết trên mọi hệ điều hành/JDK.** Điểm được khẳng định là khả năng giải mã chính xác bất kể chunking.

## 1. Phân biệt message, frame, write call, read call và TCP segment

Có năm khái niệm dễ bị trộn lẫn:

| Khái niệm | Nằm ở tầng nào? | Có giữ ranh giới của message ứng dụng? |
|---|---|---|
| **Logical message** — “ALPHA”, một JSON command, một yêu cầu RPC | Ứng dụng | Có, do **ứng dụng định nghĩa** |
| **Application frame** — ví dụ length-prefix + payload | Giao thức ứng dụng | Có, **nếu coder/decoder cùng hiểu contract** |
| **`OutputStream.write` call** — một lần ghi vào stream | Java API | Không tự tạo message boundary trên TCP |
| **`InputStream.read` call** — một lần đọc số bytes sẵn có | Java API | Không; trả số bytes thực đọc, có thể nhỏ hơn buffer |
| **TCP segment** — đơn vị phân đoạn khi TCP gửi đi | Transport/network | Không bảo toàn write/message boundaries cho ứng dụng |

**RFC 9293 `3.7** mô tả segmentation của TCP và nói rõ không có tương quan được đảm bảo giữa **TCP segment boundaries** với **application read/write buffer boundaries**. Một lần `write` lớn có thể tạo nhiều segments; nhiều lần `write` nhỏ có thể được network stack xử lý/ghép thành những segment khác nhau. Đầu nhận lại gọi `read` với kích thước buffer, scheduling và trạng thái socket của riêng mình.

### So sánh với UDP

Với `DatagramSocket`/UDP, đơn vị gửi và nhận là **datagram**, có ranh giới riêng; datagram quá dài có thể bị cắt theo buffer API và mạng có thể mất/đảo thứ tự. Với **TCP `Socket`**, phía nhận chỉ thấy stream; muốn có đơn vị message, ứng dụng phải tự đóng khung hoặc dùng một protocol thư viện đã đóng khung hộ.

**Không đồng nghĩa TCP “có thể làm mất giữa hai message” một cách bình thường**: TCP đảm bảo thứ tự và giao hàng đáng tin cậy hoặc báo failure ở transport. Vấn đề của bài là **không biết ranh giới message** từ read calls, không phải TCP tùy ý xáo trộn bytes.

## 2. Một message có thể được gửi bằng ba lần `write`

Hãy định nghĩa một message `ALPHA` có payload UTF-8 5 bytes. Ta chọn giao thức:

```text
[4 bytes signed int length, big-endian][payload UTF-8]
```

Do đó frame ứng với `ALPHA` dài **9 bytes**:

```text
Offset: 00 01 02 03 | 04 05 06 07 08
Hex:    00 00 00 05 | 41 4C 50 48 41
        └── length 5 ┘   └── "ALPHA" ─┘
```

Người gửi **cố ý** chia cùng một frame thành ba lần gọi API:

```java
// Trích đoạn minh họa; "out" là OutputStream của một socket đã kết nối.
byte[] firstFrame = frame("ALPHA"); // Hàm frame do chương trình định nghĩa.
out.write(firstFrame, 0, 2);                       // 00 00
out.write(firstFrame, 2, 3);                       // 00 05 41
out.write(firstFrame, 5, firstFrame.length - 5);   // 4C 50 48 41
```

Ba lần `write` **không** tạo ba logical messages. Đó vẫn là **một frame** với header length 5 và payload ALPHA. Đầu nhận có thể nhận:

```text
Read #1: 00 00
Read #2: 00 05 41
Read #3: 4C 50 48 41
```

nhưng cũng có thể nhận:

```text
Read #1: 00 00 00 05 41 4C 50 48 41
```

hoặc bất kỳ cách chia thành những đoạn liên tục khác. **Cả hai ví dụ read trên chỉ là các cách nhận có thể xảy ra**, không được mặc định một máy sẽ chạy theo số lần/mảnh như vậy.

### Vấn đề khi tự coi một `read` là một message

Code sai thường có dạng:

```java
// ANTI-PATTERN: không runnable độc lập; giả định sai ranh giới.
byte[] buf = new byte[1024];
int n = socket.getInputStream().read(buf);
String message = new String(buf, 0, n, StandardCharsets.UTF_8);
handle(message); // Sai nếu chỉ có một phần frame hoặc nhiều frames.
```

Ở đây `handle` và `socket` là biến/hàm minh họa, không có khai báo độc lập. Nếu `n=2`, code sẽ xử lý hai bytes length header như nội dung text; nếu `n=15`, có thể chứa hơn một frame. Tăng buffer lên 65.536 bytes **không giải quyết**: một lần read vẫn được phép trả ít bytes hơn yêu cầu hoặc chứa nhiều messages hơn tưởng tượng.

## 3. Hai messages được ghép vào **một** lần `write`

Với cùng contract length-prefix:

```text
Frame "RED":
  00 00 00 03 52 45 44           (4 + 3 = 7 bytes)

Frame "BLUE":
  00 00 00 04 42 4C 55 45        (4 + 4 = 8 bytes)

Gộp thành một byte[] dài 15 bytes:
  00 00 00 03 52 45 44 00 00 00 04 42 4C 55 45
      frame #2                   frame #3
```

Một lần gửi:

```java
// Trích đoạn minh họa, không độc lập; out và frame(...) do app cung cấp.
ByteArrayOutputStream joined = new ByteArrayOutputStream();
joined.write(frame("RED"));
joined.write(frame("BLUE"));
out.write(joined.toByteArray()); // Một write call chứa HAI frames.
```

**Một lần `write` không có nghĩa một message**. Nếu server chỉ parse một frame rồi bỏ bytes dư trong buffer, nó sẽ mất `BLUE`. Decoder đúng phải **lặp đến khi không còn frame hoàn chỉnh** trong vùng dữ liệu đang giữ, và phải bảo toàn mọi fragment còn thiếu cho lần read sau.

### Không cần đồng bộ thời điểm giữa hai đầu

Nếu server đang `read` với buffer 8 bytes, nó có thể đọc phần đầu frame RED, hoặc cả RED và một byte header BLUE, hoặc các phần khác. Người gửi không có quyền chỉ định cách JVM bên nhận gọi `read` tương ứng. **Message boundaries do protocol framing, không do scheduling.**

## 4. Quy tắc đóng khung bằng length-prefix

Một contract tối thiểu, đủ cho thí nghiệm:

1. Mỗi frame bắt đầu bằng **4 bytes** biểu diễn số **bytes payload UTF-8**, theo **big-endian**.
2. Tiếp theo là đúng `length` bytes payload.
3. Giá trị length hợp lệ là `0..1024` trong các chương trình minh họa; production chọn giới hạn hợp lý theo nghiệp vụ.
4. Sau khi giải mã frame thứ nhất, bắt đầu lại từ **byte ngay sau payload** cho frame thứ hai, bất kể số lần `read` trước đó.
5. Nếu EOF xảy ra **ngay khi đang chờ frame mới**, có thể kết thúc stream bình thường; nếu EOF xảy ra **giữa header hoặc body**, phải xem đó là truncated frame.
6. Phải từ chối độ dài âm, quá lớn hoặc tràn số **trước khi cấp phát mảng**.
7. Charset dùng `UTF-8` **mã hóa bytes trước**, sau đó mới lấy độ dài; không lấy `String.length()` (UTF-16 units) làm byte length.

### Vì sao chọn 4 bytes big-endian?

`java.nio.ByteBuffer` mặc định **big-endian**, còn `DataInputStream.readInt()` đọc bốn bytes theo thứ tự high byte trước, nên chúng tương thích với nhau trong ví dụ. Đây là **quy ước của protocol tự định nghĩa**, không phải TCP bắt buộc mọi ứng dụng dùng 4-byte header hay big-endian. Hai phía cần **thống nhất contract**; nếu client gửi little-endian còn server đọc big-endian sẽ thấy length sai.

### Giới hạn max frame rất cần thiết

Một client không tin cậy có thể gửi header:

```text
7F FF FF FF → length = 2,147,483,647 bytes
```

Nếu server cứ `new byte[length]` theo dữ liệu từ network, nó có thể cạn RAM. Hãy validate `0 <= length <= MAX_FRAME_BYTES` trước khi cấp phát. Trong hệ thống thật còn phải giới hạn **số kết nối đồng thời**, thời gian chờ header/body, buffered bytes, decode CPU, số messages/giây và authentication.

### Zero-length frame có hợp lệ không?

Trong contract của bài, length 0 là frame rỗng hợp lệ, **khác với EOF**. Nếu ứng dụng muốn cấm message rỗng, phải nói rõ trong contract. Đừng dùng `length == 0` làm tín hiệu “connection đã đóng” khi protocol còn dùng rỗng như dữ liệu.

## 5. Java 17+: chương trình TCP thật — 3 lần ghi cho 1 frame, 1 lần ghi cho 2 frames

Server mở một `ServerSocket` ở `127.0.0.1`, nhận **một** connection, đọc **ba** length-prefixed frames qua `DataInputStream.readInt()` và `readFully(...)`. Client tạo `frame("ALPHA")` rồi chia thành ba `write`; sau đó ghép `frame("RED")` và `frame("BLUE")` thành một `byte[]` và gửi bằng một `write`.

Chương trình chủ động gọi `Socket.shutdownOutput()` sau khi gửi, để server có thể thấy EOF **sau khi** giải mã ba frames; đó là half-close phía gửi, **không phải phương pháp duy nhất để phân tách các frames**. Server đọc đủ ba frames nhờ **length-prefix**, không nhờ EOF.

**Tệp `TcpWriteShapeLab.java`:**

```java
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class TcpWriteShapeLab {
    record Result(List<String> messages, boolean sawCleanEof) {}

    static byte[] frame(String message) {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + payload.length)
                .putInt(payload.length).put(payload).array();
    }

    static String readFrame(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 0 || length > 1024) throw new IOException("Invalid length");
        byte[] payload = new byte[length];
        input.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<Result> server = pool.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(4000);
                    DataInputStream input = new DataInputStream(peer.getInputStream());
                    List<String> messages = new ArrayList<>();
                    for (int i = 0; i < 3; i++) messages.add(readFrame(input));
                    boolean cleanEof = input.read() == -1;
                    return new Result(messages, cleanEof);
                }
            });
            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress("127.0.0.1",
                        listener.getLocalPort()), 2000);
                OutputStream output = client.getOutputStream();

                byte[] first = frame("ALPHA");
                output.write(first, 0, 2);
                output.write(first, 2, 3);
                output.write(first, 5, first.length - 5);

                byte[] second = frame("RED");
                byte[] third = frame("BLUE");
                ByteArrayOutputStream joined = new ByteArrayOutputStream();
                joined.write(second);
                joined.write(third);
                output.write(joined.toByteArray());
                output.flush();
                client.shutdownOutput();

                Result result = server.get(3, TimeUnit.SECONDS);
                System.out.println("First frame write calls: 3");
                System.out.println("Other two frames write calls: 1");
                System.out.println("Server decoded: " + result.messages());
                System.out.println("Clean EOF after frames: " + result.sawCleanEof());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy từ thư mục chứa file với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 TcpWriteShapeLab.java
java TcpWriteShapeLab
```

**Stdout đã kiểm chứng trên loopback:**

```text
First frame write calls: 3
Other two frames write calls: 1
Server decoded: [ALPHA, RED, BLUE]
Clean EOF after frames: true
```

### Chứng minh điều gì — và không chứng minh điều gì?

**Có bằng chứng trực tiếp rằng:**

- Client đã **gọi ba `write`** cho bytes thuộc đúng một frame ALPHA, và **một `write`** cho hai frames RED/BLUE liên tiếp.
- Server đã giải mã đúng **ba messages logic**, theo đúng thứ tự, bất kể receiver có bao nhiêu lần đọc ở tầng dưới.
- `DataInputStream.readInt()` lấy đúng 4-byte header; `readFully(payload)` không dừng chỉ vì một lần raw read nhận một phần dữ liệu. Đây là lý do API này phù hợp với **length đã biết và hợp lệ**.
- `shutdownOutput()` làm peer nhận EOF khi không còn bytes đang gửi, nên lệnh `input.read()` sau ba frames có thể trả `-1` ở đường kiểm thử normal.

**Không chứng minh:**

- “Một lần `write` là một TCP packet.” Chương trình **không đếm packets**.
- “Ba lần `write` chắc chắn tạo đúng ba `read`.” Chương trình không có giả định này và server vẫn đúng nếu số lần raw read khác.
- “Mọi client nhận đúng ba messages tự động khi dùng TCP.” Chỉ đúng vì cả hai bên đồng ý **framing contract**.
- “TCP bảo đảm ứng dụng bên kia xử lý thành công nghiệp vụ.” Đây là chứng cứ decode; nếu cần ACK nghiệp vụ, phải định nghĩa thêm.
- “Một server production được phép đọc vô hạn và nhận mọi length”. Code có max 1024, timeout nhưng chỉ xử lý một connection để học.

### Chi tiết về `DataInputStream.readFully`

`readFully(byte[])` cố đọc **đủ bytes đã được yêu cầu** từ stream (có thể dùng nhiều lần đọc bên dưới). Nếu EOF đến trước khi đủ, nó ném `EOFException`. `readInt()` cũng cần đủ 4 bytes và ném EOF khi thiếu. Điều này giải quyết **partial read đối với một frame hợp lệ** khi độ dài đã xác định, nhưng không thay server-side resource limits hoặc protocol versioning.

Với một connection lâu dài, sau ba frames server **không cần chờ EOF mới biết frame thứ ba đã xong**: length-prefix đã nói rõ. EOF chỉ dùng để chấm dứt session trong chương trình thử nghiệm.

## 6. Vì sao cần decoder stateful khi dùng `SocketChannel` hoặc `read(buffer)`?

`DataInputStream` thuận tiện trong **blocking I/O** khi có thể đợi đủ 4 bytes header và đủ payload. Nhưng với:

- `SocketChannel` dùng nonblocking mode,
- Selector event loop,
- asynchronous I/O,
- byte buffers do framework callback,
- hoặc dữ liệu từ một parser/transport layer phân chia thành arbitrary chunks,

bạn thường chỉ nhận **một đoạn bytes mới**. Không được gọi `ByteBuffer.getInt()` khi mới có 2 bytes header; cũng không được bỏ phần buffer dư sau frame hoàn chỉnh.

Decoder đúng phải có trạng thái qua nhiều lần `feed(chunk)`:

```text
[CHỜ HEADER 4 BYTES]
    │ thiếu → giữ lại, đợi chunk sau
    │ đủ → đọc length, kiểm tra 0..MAX
    ▼
[CHỜ PAYLOAD length BYTES]
    │ thiếu → giữ lại, đợi chunk sau
    │ đủ → decode 1 message, consume frame
    ▼
[ĐẾN FRAME TIẾP THEO]
    ├─ buffer còn đủ một frame → decode tiếp trong cùng feed
    ├─ buffer còn fragment → giữ lại
    └─ buffer trống → đợi feed tiếp
```

**Cả hai điều kiện đều bắt buộc**: (a) lưu fragment còn thiếu; (b) parse **nhiều frames** nếu một chunk chứa nhiều.

### Tránh bẫy “mỗi onRead là một message”

Một Selector thường báo **readiness**, không báo “có một message hoàn chỉnh”. Callback `onRead` có thể nhận rất ít hoặc nhiều bytes. Parser phải tích lũy theo framing. Readiness của `OP_READ` không đồng nghĩa length-prefix header/body đã đủ.

## 7. Java 17+: decoder nhận arbitrary chunks — thí nghiệm quyết định

Chương trình thứ hai không dùng socket. Đó là **thử nghiệm ở tầng byte-stream parser** với các chunk sizes **chủ động kiểm soát**, để bảo đảm việc kiểm tra không phụ thuộc lịch TCP thật.

Nó đưa frame `ONE` vào decoder theo ba mảnh: 2 bytes đầu header, tiếp 2 bytes header và 2 bytes payload, cuối cùng 1 byte payload. Decoder **không** phát message cho hai mảnh đầu vì chưa đủ. Sau đó nó đưa **hai frames TWO và THREE trong một chunk**, decoder phải phát **hai messages**, không bỏ phần dư.

Decoder dùng buffer pending cố định 4096 bytes và từ chối length vượt 1024. Đây vẫn là demo, không phải parser production cho mọi tải/số lượng frame; trong production cần xử lý chunk lớn hơn/bounded queues mà không làm mất bytes.

**Tệp `IncrementalFrameDecoderDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.util.*;

public class IncrementalFrameDecoderDemo {
    static final class Decoder {
        private final byte[] pending = new byte[4096];
        private int count;

        List<String> feed(byte[] part) throws IOException {
            if (part.length > pending.length - count)
                throw new IOException("Pending buffer full");
            System.arraycopy(part, 0, pending, count, part.length);
            count += part.length;
            List<String> decoded = new ArrayList<>();
            while (count >= 4) {
                int size = ByteBuffer.wrap(pending, 0, 4).getInt();
                if (size < 0 || size > 1024)
                    throw new IOException("Frame length rejected: " + size);
                if (count < size + 4) break;
                try {
                    String text = StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(pending, 4, size)).toString();
                    decoded.add(text);
                } catch (CharacterCodingException badUtf8) {
                    throw new IOException("Invalid UTF-8", badUtf8);
                }
                int remaining = count - size - 4;
                System.arraycopy(pending, 4 + size, pending, 0, remaining);
                count = remaining;
            }
            return decoded;
        }

        int pendingBytes() { return count; }

        void finish() throws IOException {
            if (count != 0) throw new IOException("Incomplete final frame");
        }
    }

    static byte[] frame(String message) {
        byte[] data = message.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + data.length)
                .putInt(data.length).put(data).array();
    }

    static byte[] concat(byte[] a, byte[] b) {
        byte[] combined = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, combined, a.length, b.length);
        return combined;
    }

    public static void main(String[] args) throws Exception {
        Decoder decoder = new Decoder();
        byte[] one = frame("ONE");
        System.out.println("Partial header: "
                + decoder.feed(Arrays.copyOfRange(one, 0, 2)));
        System.out.println("Header plus partial payload: "
                + decoder.feed(Arrays.copyOfRange(one, 2, 6)));
        System.out.println("Remaining payload: "
                + decoder.feed(Arrays.copyOfRange(one, 6, one.length)));
        System.out.println("Two frames in one chunk: "
                + decoder.feed(concat(frame("TWO"), frame("THREE"))));
        decoder.finish();
        System.out.println("Pending after decode: " + decoder.pendingBytes());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 IncrementalFrameDecoderDemo.java
java IncrementalFrameDecoderDemo
```

**Stdout đã kiểm chứng:**

```text
Partial header: []
Header plus partial payload: []
Remaining payload: [ONE]
Two frames in one chunk: [TWO, THREE]
Pending after decode: 0
```

### Phân tích bytes thật

`frame("ONE")` dài 7 bytes:

```text
00 00 00 03 4F 4E 45
└ length 3 ┘ └ ONE ┘
```

Các lần feed:

| Feed | Bytes mới | Pending trước khi decode | Messages hoàn chỉnh | Pending còn lại |
|---|---|---:|---|---:|
| `one[0:2]` | `00 00` | 2 | Không | 2 |
| `one[2:6]` | `00 03 4F 4E` | 6 | Không (cần thêm 1 payload byte) | 6 |
| `one[6:7]` | `45` | 7 | ONE | 0 |
| `frame("TWO")+frame("THREE")` | 7+9 = 16 bytes | 16 | TWO, THREE | 0 |

**Không có sự kiện TCP nào được dùng để dựng bảng này**: phân đoạn được chọn cố ý ở tầng test. Điều này quan trọng vì kiểm thử parser phải **deterministic**, trong khi việc một `Socket.read` nhận 2 hay 9 bytes phụ thuộc timing, OS buffers và network stack.

### Vì sao `while (count >= 4)` mà không phải `if`?

Vì **một chunk có thể chứa nhiều frames**. Khi đã decode TWO, còn nguyên frame THREE trong `pending`; vòng `while` tiếp tục xử lý. Nếu chỉ dùng `if` một lần rồi bỏ buffer dư, frame THREE có thể bị mất hoặc bị giữ mãi đến khi có thêm dữ liệu mới.

### Vì sao phải buffer một phần header?

Nếu nhận chỉ 2 bytes `00 00` và cố gọi `ByteBuffer.getInt`, decoder sẽ gặp underflow hoặc đọc bytes không hợp lệ. Quy tắc phải là **đủ 4 bytes mới đọc length**. Tương tự, đủ header rồi nhưng payload chưa đủ thì giữ lại.

### Vì sao strict UTF-8 decode sau khi đủ bytes?

Một ký tự Unicode có thể trải qua nhiều bytes UTF-8, và một chunk có thể cắt ngay giữa chuỗi bytes của ký tự. `new String(part, UTF_8)` trên **từng chunk** có thể tạo ký tự thay thế do mảnh byte chưa hoàn chỉnh. Decoder nên chỉ giải mã text **sau khi gom đủ một frame**, hoặc dùng một `CharsetDecoder` stateful theo đúng streaming contract.

Trong ví dụ này, `CharsetDecoder.onMalformedInput(REPORT)`/`onUnmappableCharacter(REPORT)` giúp **từ chối UTF-8 sai** thay vì thay bằng kí tự `�` không nhận biết. Với protocol binary, không decode UTF-8 mà chuyển raw bytes lên lớp nghiệp vụ.

### Hạn chế của decoder minh họa

`Decoder.feed` giới hạn **một chunk đầu vào cộng pending <= 4096 bytes**. Nếu caller gửi một chunk rất lớn, nó từ chối thay vì tự chia nhỏ. Đây là lựa chọn an toàn có chủ đích cho demo, **không phải parser đầy đủ**. Một decoder production có thể dùng buffer mở rộng có quota, ring buffer, xử lý chunk bằng offsets, pooling và backpressure để tránh cấp phát không giới hạn.

## 8. EOF không giống “đã nhận xong một message”

Đừng nhầm:

- `InputStream.read() == -1`: **EOF**, peer đã đóng chiều gửi hoặc stream kết thúc.
- `length-prefix payload đã đủ`: **message hoàn tất**, bất kể connection còn mở.
- `BufferedReader.readLine()` thấy newline: một **line-delimited message hoàn tất** theo protocol quy định.
- `ByteBuffer.remaining() == 0` sau một lần `read`: hết bytes trong buffer hiện tại, **không** có nghĩa hết frame, message hay connection.
- `Socket.isConnected()==true`: đã từng kết nối, **không phải** socket đang online hay peer còn gửi dữ liệu.

Với protocol **nhiều messages trên connection lâu dài**, nếu server cứ gọi `input.readAllBytes()` trên raw `Socket.getInputStream()`, nó có thể **chờ mãi** vì TCP peer không đóng stream sau mỗi message. Đây là bẫy phổ biến khi học Java Networking.

### EOF ở ba thời điểm

```text
A. [frame đầy đủ][EOF]
   → Kết thúc connection hợp lệ nếu protocol cho phép close tại boundary.

B. [1..3 bytes header][EOF]
   → Header chưa đủ 4 bytes, phải báo truncated header.

C. [4 bytes length = 5][2 bytes payload][EOF]
   → Payload thiếu 3 bytes, phải báo truncated frame.
```

Nếu program chỉ đọc đến EOF rồi coi mọi bytes đã nhận là “thành công”, trường hợp B/C sẽ bị coi nhầm dữ liệu hợp lệ. Với RPC/financial protocol, đó có thể là lỗi nghiêm trọng: parser nhận message bị cắt mà vẫn tạo side effect.

### Vì sao `DataInputStream.readFully` đáng dùng?

Nó thực hiện việc chờ đủ `N` bytes hoặc báo `EOFException` (và có thể IOException do network). Nhưng phải **biết N hợp lệ trước**, đọc đúng N bằng một contract framing, và đặt socket timeout/cancellation policy tránh đợi vô hạn khi peer không gửi đủ. `readFully` không tự làm validation hay timeout.

## 9. Java 17+: từ chối header thiếu, body thiếu và length quá lớn

Ví dụ thứ ba dùng `ByteArrayInputStream` để kiểm thử parser **không có network timing**. Nó đọc byte đầu của header để phân biệt **clean EOF trước frame** với **EOF giữa header**, rồi dùng `DataInputStream.readFully` để lấy ba header bytes còn lại và payload.

Các cases:

1. Stream rỗng ngay khi chờ frame mới → trả `null` như tín hiệu clean boundary EOF của **protocol demo**.
2. Chỉ có 2 bytes header → ném `EOFException`.
3. Header length 5 nhưng chỉ có 2 payload bytes → ném `EOFException`.
4. Length 999999 > MAX 1024 → ném `IOException` trước khi cấp phát payload.
5. Length 0 → trả chuỗi rỗng `""` như một **frame hợp lệ**.

**Tệp `TruncatedFrameDefenseDemo.java`:**

```java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class TruncatedFrameDefenseDemo {
    static String readFrame(DataInputStream input) throws IOException {
        int first = input.read();
        if (first == -1) return null;
        byte[] header = new byte[4];
        header[0] = (byte) first;
        input.readFully(header, 1, 3);
        int length = ByteBuffer.wrap(header).getInt();
        if (length < 0 || length > 1024)
            throw new IOException("Rejected length: " + length);
        byte[] payload = new byte[length];
        input.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    static String outcome(byte[] bytes) {
        try {
            readFrame(new DataInputStream(new ByteArrayInputStream(bytes)));
            return "ACCEPTED";
        } catch (EOFException incomplete) {
            return "EOFException";
        } catch (IOException invalid) {
            return "IOException";
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Clean boundary EOF: "
                + (readFrame(new DataInputStream(
                    new ByteArrayInputStream(new byte[0]))) == null));
        System.out.println("Partial header: "
                + outcome(new byte[] {0, 0}));
        System.out.println("Truncated payload: "
                + outcome(new byte[] {0, 0, 0, 5, 'A', 'B'}));
        System.out.println("Oversized length: "
                + outcome(ByteBuffer.allocate(4).putInt(999999).array()));
        System.out.println("Valid zero-length frame: "
                + ("".equals(readFrame(new DataInputStream(
                    new ByteArrayInputStream(new byte[] {0, 0, 0, 0}))))));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TruncatedFrameDefenseDemo.java
java TruncatedFrameDefenseDemo
```

**Stdout đã kiểm chứng:**

```text
Clean boundary EOF: true
Partial header: EOFException
Truncated payload: EOFException
Oversized length: IOException
Valid zero-length frame: true
```

### Phân loại lỗi chính xác

- **Clean boundary EOF** không có 4-byte header nào đang đọc dở, do đó là tín hiệu kết thúc stream **theo contract demo**. Một protocol production có thể còn yêu cầu close reason, sequence number hoặc expected message count trước khi chấp nhận EOF.
- **Partial header**: phát hiện đã có byte đầu nhưng còn thiếu 3 bytes header. `EOFException` là hợp lý, thay vì âm thầm bỏ qua bytes dư.
- **Truncated payload**: header hợp lệ nói phải có 5 bytes, nhưng stream chỉ cung cấp 2. Trả message “AB” như thành công là sai.
- **Oversized length**: validation thực hiện **trước cấp phát**, giúp chặn ý định dùng header để chiếm RAM. Runtime không bị bắt buộc allocate 999999 bytes.
- **Zero-length frame**: hợp lệ theo contract. Không nhầm với clean EOF vì header `00 00 00 00` vẫn tồn tại đầy đủ.

**Một chỗ cần mở rộng cho production:** trả `null` khi clean EOF có thể xung đột nếu type message cho phép `null`. Có thể dùng `Optional<Message>` hoặc một result enum/record để phân biệt trạng thái. Demo dùng String để dễ học nhưng đã diễn giải contract rõ ràng.

## 10. Cách đóng khung khác: delimiter `\n` và `BufferedReader.readLine`

Không phải mọi protocol cần length-prefix. Giao thức **mỗi message trên một dòng** có thể dùng một delimiter nhất quán như LF `\n`. Khi đầu nhận dùng `BufferedReader.readLine()`, nó sẽ **tích lũy cho tới khi có line terminator hoặc EOF** theo contract API, bất kể người gửi chia bytes thành mấy lần `write`.

Ví dụ stream:

```text
"FIRST\nSECOND\nTHIRD\n"
```

Client có thể gửi:

```text
write #1: "FI"
write #2: "RST\n"
write #3: "SECOND\nTHIRD\n"
```

Server gọi `readLine` ba lần và nhận `FIRST`, `SECOND`, `THIRD`. Ở đây delimiter `\n` là **message boundary do application protocol**, chứ không phải TCP tự sinh ranh giới.

### Ưu điểm và giới hạn

| Tiêu chí | Dấu xuống dòng | Length-prefix |
|---|---|---|
| Dễ nhìn bằng telnet/netcat/log? | Có, với UTF-8 text và LF | Ít dễ nhìn bằng mắt vì binary header |
| Hỗ trợ newline trong payload? | Cần escape/encode hoặc cấm | Có, newline là payload bình thường |
| Hỗ trợ binary tùy ý? | Phải có escaping/Base64 | Có thể giữ bytes nguyên |
| Biết trước kích thước frame? | Không, chỉ biết khi gặp LF | Có sau khi đọc đủ header |
| Giới hạn kích thước | Cần đếm bytes/chars đến delimiter | Kiểm tra length trước allocate, vẫn giới hạn |
| EOF giữa một dòng | `readLine` có thể trả dòng cuối **không có LF** | Header/body thiếu được phát hiện rõ |
| Unicode/UTF-8 | Reader phải decode đúng across byte chunks | Decode payload sau khi đủ frame |
| Parser streaming | `BufferedReader.readLine`/scanner có thể dùng | Custom state machine/`readFully` |

**Lưu ý quan trọng:** `BufferedReader.readLine()` theo Java API chấp nhận LF, CR hoặc CRLF, và nếu EOF đến sau các chars chưa có terminator, nó vẫn có thể trả **dòng cuối**. Nếu protocol **bắt buộc mỗi message phải kết thúc bằng LF**, dùng `readLine` đơn thuần **không chứng minh** line cuối có terminator. Một parser nghiêm ngặt cần bảo toàn/kiểm tra dấu kết thúc, giới hạn line length và xử lý EOF không có LF như incomplete message nếu contract yêu cầu.

## 11. Java 17+: gửi một dòng qua hai lần ghi, hai dòng qua một lần ghi

Server `BufferedReader` đọc tới EOF, lưu các lines. Client gửi FIRST chia đôi, rồi ghép SECOND và THIRD. Chương trình **không cho rằng một `readLine` tương ứng với một `write`**; nó tận dụng **delimiter**.

**Tệp `LineFramingLab.java`:**

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class LineFramingLab {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<List<String>> decoded = workers.submit(() -> {
                try (Socket peer = listener.accept();
                     BufferedReader in = new BufferedReader(new InputStreamReader(
                             peer.getInputStream(), StandardCharsets.UTF_8))) {
                    peer.setSoTimeout(4000);
                    List<String> lines = new ArrayList<>();
                    String line;
                    while ((line = in.readLine()) != null) {
                        lines.add(line);
                        if (lines.size() > 3)
                            throw new IOException("Unexpected extra message");
                    }
                    return lines;
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress("127.0.0.1",
                        listener.getLocalPort()), 2000);
                OutputStream out = client.getOutputStream();
                byte[] first = "FIRST\n".getBytes(StandardCharsets.UTF_8);
                out.write(first, 0, 2);
                out.write(first, 2, first.length - 2);
                out.write("SECOND\nTHIRD\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                client.shutdownOutput();

                System.out.println("First line write calls: 2");
                System.out.println("Next two lines write calls: 1");
                System.out.println("Server readLine messages: "
                        + decoded.get(3, TimeUnit.SECONDS));
            }
        } finally {
            workers.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 LineFramingLab.java
java LineFramingLab
```

**Stdout đã kiểm chứng:**

```text
First line write calls: 2
Next two lines write calls: 1
Server readLine messages: [FIRST, SECOND, THIRD]
```

### Vì sao ví dụ này thành công?

- `FIRST\n` là **một message** theo contract delimiter dù được gửi bằng **hai lần write**.
- `SECOND\nTHIRD\n` là **hai messages** dù được gửi bằng **một lần write**.
- `BufferedReader` xử lý charset across stream và `readLine` nhìn vào **dấu kết thúc dòng**, không dựa vào số lần TCP segments/read.
- Server dùng `shutdownOutput()` ở client để `readLine` có thể trả `null` sau ba dòng. Delimiter vẫn xác định message boundaries trước EOF.
- Chương trình không xử lý escaped newlines, maliciously long lines hay message IDs; khi xây production protocol, phải thêm giới hạn line length, escaping và validation.

### Khi nào không dùng delimiter?

Không phù hợp nếu payload là binary tùy ý chứa `\n`, nếu cần nhận binary frames rất lớn không escape, hoặc nếu protocol không đảm bảo line terminator. Có thể dùng JSON Lines khi mỗi JSON document đúng **một dòng** và newline bên trong string được encode thành `\\n` trong JSON representation. Không thể gửi “pretty JSON” có nhiều dòng bằng delimiter LF đơn giản rồi coi một JSON object là một message.

## 12. UTF-8: độ dài ký tự không phải độ dài bytes

Một String Java dùng UTF-16 representation, nên `String.length()` không phải số bytes UTF-8 sẽ gửi trên TCP. Ví dụ:

```text
Text: "é"
Java String.length(): 1 UTF-16 code unit
UTF-8 payload bytes: C3 A9 (2 bytes)

Text: "🌍"
Java String.length(): 2 UTF-16 code units (surrogate pair)
UTF-8 payload bytes: F0 9F 8C 8D (4 bytes)
```

Nếu header ghi `payload.length()` rồi phía gửi thực sự viết `payload.getBytes(UTF_8)`, server có thể đọc **thiếu bytes** ở frame đầu và xem phần dư thành header của frame tiếp theo. Đây là lỗi framing thường chỉ xảy ra với Unicode.

**Luôn tính:**

```java
// Snippet minh họa; DataOutputStream và message do ứng dụng định nghĩa.
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
out.writeInt(bytes.length); // Số BYTES, không phải String.length().
out.write(bytes);
```

Đoạn này là snippet không độc lập; `out` là `DataOutputStream`, và server phải đọc `readInt`/`readFully` theo cùng contract.

### Split ngay giữa một UTF-8 code point có sao không?

TCP có thể trả byte chunks cắt giữa `C3` và `A9`. **Điều này hoàn toàn hợp lệ với byte-stream**. Nếu parser tích lũy bytes rồi giải mã sau khi đủ một frame, nhận lại `é` bình thường. Nếu parser gọi `new String(chunk, UTF8)` trên từng chunk độc lập, nó có thể tạo replacement characters. Sử dụng `CharsetDecoder` stateful hoặc decode **sau khi frame complete**.

Trong `IncrementalFrameDecoderDemo`, payload được decode sau khi có đủ bytes; vì vậy việc chia header/body qua nhiều `feed` không làm thay đổi thông điệp.

## 13. `flush()`, `TCP_NODELAY`, Nagle, PSH không tạo message boundary

Bốn khái niệm bị dùng sai:

### `OutputStream.flush()`

`flush()` là thao tác theo contract của OutputStream/BufferedOutputStream để đẩy dữ liệu **đang được buffer ở tầng Java stream** xuống tầng dưới. Khi viết qua `BufferedOutputStream`, cần flush nếu muốn dữ liệu không nằm mãi trong buffer Java. Nhưng **flush không tạo một delimiter frame** cho peer; bên nhận vẫn có thể đọc một phần hoặc nhiều frames trong cùng một `read`.

Nếu dùng raw `Socket.getOutputStream()` không có Java buffered layer thêm, `flush()` có thể không làm gì đáng kể; đừng xem đó là “send packet now” hoặc “receiver read exactly one message”.

### `Socket.setTcpNoDelay(true)`

Tùy chọn này điều khiển TCP_NODELAY, thường được giải thích là tắt Nagle algorithm để giảm một loại trì hoãn của small writes. **Nó không làm TCP trở thành message transport**. Dù Nagle bật hay tắt, TCP vẫn là stream và read boundaries không được bảo đảm.

### Nagle, delayed ACK và scheduler

Small writes có thể bị TCP stack gom/tạm giữ tùy network conditions, Nagle, congestion window, delayed ACK, MSS/MTU và scheduling. Bật/tắt `TCP_NODELAY` có thể thay latency/packet patterns nhưng **không thay nhiệm vụ của parser**.

### PSH flag không phải End-of-Message

PSH trong TCP không phải cơ chế bảo đảm “dữ liệu tới trước PSH thuộc đúng một application message”. Không dùng PSH hoặc TCP segment boundary làm dấu kết thúc bản tin. Cần protocol framing ở tầng ứng dụng.

**Nguyên tắc:** nếu thay `TCP_NODELAY` làm bug “biến mất” thì thường parser vẫn sai; bug chỉ bị che bởi timing. Kiểm thử tốt phải chủ động thay chunk sizes mà parser **vẫn cho cùng kết quả**.

## 14. `SocketChannel` nonblocking: đọc/ghi một phần và ByteBuffer

Với Java NIO `SocketChannel` ở nonblocking mode, một lần `read(ByteBuffer)` có thể trả số bytes dương nhỏ, **0** nếu hiện không có dữ liệu sẵn sàng, hoặc **-1** khi stream kết thúc. Không đồng nhất “read 0” với EOF; cũng không cố parse 4-byte header khi chỉ có 2 bytes trong buffer.

Một lần `write(ByteBuffer)` nonblocking có thể ghi **ít bytes hơn `remaining()`** (kể cả 0) vì send buffer/flow control. Muốn gửi một frame, phải **giữ lại ByteBuffer còn dư** và tiếp tục ghi khi channel sẵn sàng. Không ném phần payload chưa gửi đi.

```java
// Snippet minh họa, không phải một chương trình độc lập.
ByteBuffer outbound = ByteBuffer.wrap(frameBytes);
while (outbound.hasRemaining()) {
    int n = channel.write(outbound);
    if (n == 0) {
        // Không busy-spin trong nonblocking I/O:
        // đăng ký OP_WRITE và tiếp tục khi Selector báo writable.
        break;
    }
}
// Giữ outbound có position hiện tại để ghi tiếp ở event loop.
// Chỉ coi frame bytes đã được đẩy hết khỏi buffer khi !hasRemaining().
```

Trong đó `channel` là một `SocketChannel` đã connect, `frameBytes` chứa frame theo contract. Một production event loop phải có queue gửi có giới hạn, quản lý `OP_WRITE` theo nhu cầu, không để OP_WRITE luôn bật gây busy spin.

### `ByteBuffer.flip()` và `compact()`

Receive buffer trong NIO thường theo pattern:

```java
// Snippet minh họa: inputBuffer và channel do app sở hữu.
int count = channel.read(inputBuffer); // Buffer ở write mode.
if (count > 0) {
    inputBuffer.flip();                // Đọc bytes mới có trong buffer.
    decodeCompleteFrames(inputBuffer); // Không đọc vượt limit.
    inputBuffer.compact();             // Giữ bytes thừa, về write mode.
}
```

Đây là snippet không độc lập: `decodeCompleteFrames` phải giữ đúng state và xử lý incomplete header/payload. `compact()` giữ bytes chưa consume, không tự parse protocol cho bạn. Nếu một lần read chứa hai frames, decoder phải xử lý **cả hai** trong vòng lặp trước khi compact.

### Không interleave bytes của hai frames từ nhiều threads

TCP bảo toàn thứ tự bytes đã chấp nhận vào stream nhưng **không tự bảo đảm nguyên tử cho “một frame gồm nhiều `write`”** nếu nhiều threads cùng chia sẻ `OutputStream` và gửi xen kẽ.

```text
Thread A: header A
Thread B: header B + payload B
Thread A: payload A

Wire stream có thể thành:
  [header A][header B][payload B][payload A]
```

Decoder thấy header A rồi coi header B là **payload A**, dẫn tới sai toàn bộ framing. Hãy serialize **trọn frame** qua một writer thread/queue hoặc dùng lock bao quanh **toàn quá trình gửi frame**, không chỉ bảo vệ mỗi lời gọi `write` riêng lẻ. Việc một frame thường được gửi bằng một `write` không tự giải quyết backpressure/partial writes của NIO.

## 15. Bảo vệ decoder trước dữ liệu lỗi và tấn công

Framing là điều kiện **cần** để tái dựng messages nhưng **không đủ** để bảo vệ production server.

| Rủi ro | Ví dụ | Biện pháp |
|---|---|---|
| Length âm hoặc cực lớn | Header `FF FF FF FF` = -1 hay `7F FF FF FF` rất lớn | Validate length range trước allocate |
| Header chỉ gửi 1–3 bytes rồi đứng | Slowloris theo protocol custom | Timeout, per-connection quotas, connection limit |
| Payload thiếu bytes | Header báo 500, peer chỉ gửi 10 rồi EOF | Báo truncated frame, cleanup; không xử lý partial |
| Unicode malformed | Bytes không phải UTF-8 hợp lệ | CharsetDecoder `REPORT` nếu protocol yêu cầu strict |
| Một chunk chứa hàng nghìn tiny frames | Message flood | Limit frames per tick, CPU budget, queue và rate |
| Fragmentation làm buffer lớn dần | Partial frames kéo dài | Max pending bytes, max frame bytes, deadline |
| Một client không đọc response | Send queue tăng vô hạn | Bounded queue, backpressure, timeout/close policy |
| Reader chặn mãi dù peer còn sống | Peer giữ TCP open không gửi đủ | `setSoTimeout`, application deadline hoặc async timeout |
| Hai threads xen bytes của frames | Corrupt header/payload | Single writer / serialized send queue / frame-level lock |
| Empty frame bị nhầm EOF | Header length 0 | Phân biệt clean EOF và zero-byte payload |
| Receiver xử lý trùng khi retry | Timeout sau server xử lý | Application message ID, idempotency, ACK protocol |

**Đừng dùng `InputStream.available()` để quyết định message đã hoàn tất.** Nó chỉ ước tính bytes có thể đọc không block tại thời điểm đó, không biết frame length của ứng dụng. `available()==0` không nghĩa peer đã gửi xong message; `available()>0` cũng không đảm bảo đủ header/body.

### Giới hạn tổng RAM chứ không chỉ max frame

Nếu mỗi connection cho phép buffer tới 1 MiB, thì 10.000 connections có thể chiếm khoảng 10 GiB **chỉ cho pending buffers**. Cần hạn mức đồng thời, pooled buffers/quota, kịch bản khi client chậm và lifetime. Nếu API hỗ trợ compressed frames, phải kiểm soát decompressed size; length-prefix của compressed bytes không tự giới hạn memory sau giải nén.

### Không giải mã trước khi hoàn tất framing

Nếu thông điệp là JSON, hãy đưa **đúng payload bytes của một frame** cho JSON parser sau khi có đủ; nếu receiver decode khi còn thiếu bytes, parser sẽ báo lỗi giả hoặc lưu trạng thái nửa chừng. JSON streaming parser có thể xử lý incremental, nhưng vẫn cần contract rõ ràng về message boundaries khi nhiều documents nằm trên một connection.

## 16. Gỡ lỗi bằng packet capture: đo gì và không đoán gì?

Trong một thực nghiệm thực tế, bạn có thể bật packet capture trên **loopback interface** khi có quyền và dùng Wireshark/tcpdump hoặc công cụ hệ điều hành tương ứng. Tuy nhiên:

- **TCP segment count** không bằng `write` call count; offload/coalescing của OS/adapter và capture layer có thể thay hình dạng packet.
- Một TCP segment có thể chứa **nhiều application frames**; một application frame cũng có thể đi qua nhiều TCP segments.
- **Receive `read(buffer)` count** lại là số lần ứng dụng gọi API, phụ thuộc buffer size và thời điểm được scheduled, không phải số packets.
- `tcpdump` có thể thấy retransmissions, duplicated ACKs, congestion; những thứ này không biến cùng bytes thành các logical messages mới ở tầng Java khi TCP cung cấp stream bình thường.
- Nếu dùng TLS, packet capture không đọc được plaintext payload nếu không có giải mã hợp lệ; người học vẫn kiểm chứng framing ở tầng ứng dụng qua structured logs/byte arrays mà không phải mở secrets.

### Log đúng để so sánh

```text
txLogicalMessageId    = 123
txPayloadUtf8Bytes    = 5
txFrameBytes          = 9
txWriteCalls          = 3
rxSocketReadCalls     = (measurement only, may vary)
rxFramesDecoded       = 1
rxMessage             = "ALPHA"
rxBytesBuffered       = ...
rxIncompleteFrame     = false
```

Đừng thiết kế assertion `rxSocketReadCalls == 3`; nó có thể đúng một lần rồi sai lần sau mà **không có bug**. Assertion đúng là **rx decoded message count/order/payload == expected**, cộng trạng thái parser cuối cùng và error behavior.

### Vì sao các ví dụ không dùng `Thread.sleep(...)` để ép read boundaries?

Thêm `Thread.sleep(50)` giữa writes **không đảm bảo** kernel/receiver sẽ đọc thành ba chunks. Thời gian scheduler, Nagle, TCP buffers, CPU load khác nhau khiến test flaky. Vì vậy bài dùng hai dạng thí nghiệm có mục tiêu khác nhau: socket thật **đo kết quả decode**, và parser unit test **feed bytes theo chunks cố định** để kiểm chứng partial/coalesced inputs một cách quyết định.

## 17. Ma trận kiểm thử bắt buộc cho một protocol TCP tự xây dựng

Bất kỳ parser length-prefixed nào cũng nên vượt qua ít nhất:

| Case | Dữ liệu đưa vào decoder | Kết quả mong đợi |
|---|---|---|
| Frame vừa đủ | `[header][payload]` | Đúng một message |
| Header chia 1+3 | `[1 byte]` rồi `[3 header bytes+body]` | Không decode sớm; cuối cùng đúng một |
| Header chia 2+2 | `[2 bytes]` rồi `[2 bytes+body]` | Không underflow |
| Payload chia nhiều mảnh | `[header+1 byte]` rồi phần còn lại | Chờ đủ mới decode |
| Một chunk chứa hai frames | `[f1][f2]` | Trả cả f1 và f2 |
| Chunk chứa f1 và đầu f2 | `[f1][header f2 chưa đủ]` | Trả f1, giữ partial f2 |
| Nhiều frames chia bất kỳ | N chunks ngẫu nhiên giữ thứ tự bytes | Message sequence khớp y nguyên |
| EOF ở frame boundary | Stream rỗng khi chờ header mới | Clean close nếu protocol cho phép |
| EOF giữa header | Chỉ 1–3 header bytes | Truncated header |
| EOF giữa payload | Length=N, nhận ít hơn N | Truncated payload |
| Length âm | Header high bit bật thành số âm | Từ chối trước allocate |
| Length vượt limit | Header lớn hơn MAX | Từ chối trước allocate |
| Length 0 | Header bằng 0 | Frame rỗng, nếu contract cho phép |
| UTF-8 nhiều bytes | Ký tự được split giữa chunks | Text khôi phục đúng sau đủ frame |
| Malformed UTF-8 | Byte sequence không hợp lệ | Từ chối hoặc xử lý theo documented policy |
| Một connection nhiều request | Frames nối nhau trong cùng stream | Không đòi EOF giữa messages |
| NIO partial write | Write trả ít hơn remaining | Chưa drop bytes còn pending |
| Hai sender threads cùng socket | Frames interleaved nếu không bảo vệ | Dùng serialization, không coi raw writes atomic |
| Peer không gửi tiếp | Header/body dở rồi đứng | Deadline/timeout, cleanup |
| Peer gửi quá nhanh | Nhiều frames trong một read | Bounded parsing, backpressure, giữ ordering |

### Property-based test cho decoder

Lý tưởng là tạo một chuỗi bytes `frame(m1)+frame(m2)+...` rồi **chia ngẫu nhiên thành chunks** theo nhiều seeds, feed tuần tự vào decoder, so danh sách decoded messages với messages ban đầu. Property phải giữ với mọi cách chia giữ nguyên thứ tự, kể cả chunk size 1, chunk lớn chứa nhiều frames và split giữa bytes UTF-8.

Không cần gây mất packets thật để kiểm chứng decoder partial/coalesced. Unit test với deterministic byte slices **tốt hơn** để kiểm tra parser; integration test qua socket bổ sung chứng cứ hoạt động end-to-end.

## 18. Bài tập thực hành nâng cao

### Bài tập A — chia một frame thành từng byte

Trong `TcpWriteShapeLab`, thay ba lần `write` của frame ALPHA bằng:

```java
// Trích đoạn thay thế, không độc lập.
for (byte b : first) {
    output.write(b & 0xff);
}
```

Một frame 9 bytes sẽ được gửi bằng **9 write calls**. Giữ nguyên server code. **Expected decoded messages vẫn là `[ALPHA, RED, BLUE]`.** Không đặt kỳ vọng `server.read` phải chạy 9 lần.

### Bài tập B — ghép 100 frames trong một write

Tạo `ByteArrayOutputStream`, trong vòng lặp append 100 frames theo contract rồi gửi **một lần `write`**. Server thay số expected frames từ 3 sang 100 và kiểm tra thứ tự/CRC của payload. Giới hạn tổng bytes để tránh test gây memory spike. **Không thay frame limit 1024** nếu mỗi payload nhỏ hơn giới hạn.

### Bài tập C — decoder random-split

Tạo frames `M0..M99`, nối thành `byte[] all` rồi chọn chunk lengths bằng `Random(seed)`. Bảo đảm tổng chunks khớp `all.length`, feed sequential và so danh sách messages. Chạy nhiều seeds; khi fail, log seed và raw hex ngắn để reproduce. Mục tiêu là chứng minh **không phụ thuộc chunking**.

### Bài tập D — Unicode

Thay message ALPHA bằng `"Xin chào 🌍"`, dùng `message.getBytes(UTF_8).length` trong header. Kiểm tra server khôi phục đúng Unicode dù cắt network chunks ở bất kỳ điểm nào. Cẩn thận terminal encoding khi in tiếng Việt trên Windows, vì lỗi console encoding **không đồng nghĩa lỗi TCP framing**.

### Bài tập E — lỗi thiếu payload

Gửi header length 100 nhưng chỉ gửi 10 bytes rồi gọi `shutdownOutput()`. Server phải báo `EOFException`/protocol error thay vì chấp nhận message 10 bytes. Có thể dùng `TruncatedFrameDefenseDemo` để unit-test trước khi integration-test.

### Bài tập F — cố tình gây bug bằng `read(buffer)`

Viết server sai: mỗi lần `read` thì tạo một message. Sau đó áp dụng sender chia/ghép và thay buffer size từ 1, 2, 3, 8, 4096. Ghi các trường hợp decode sai. Cuối cùng thay server bằng length-prefix parser và chạy cùng ma trận để thấy decode ổn định. **Đừng cố thêm sleep để sửa bug parser.**

### Bài tập G — framing bằng delimiter

Dùng `LineFramingLab`, đổi payload thành `"HELLO\nWORLD"` theo ý định là **một** logical message. Quan sát `readLine` sẽ trả **hai messages** nếu không có escaping. Thiết kế escaping hoặc đổi sang length-prefix, sau đó kiểm thử lại.

### Bài tập H — concurrency

Cho hai threads cùng gửi frames trên một `Socket.getOutputStream()`, mỗi frame gồm header và payload ghi riêng. Với mỗi thread chỉ khóa từng write, có thể xen byte giữa frames. Tạo **một outbound writer queue** và verify decoder không bị corrupt. Lưu ý đây là thí nghiệm concurrency: kết quả lỗi có thể phụ thuộc scheduling; assertion chủ yếu là sau khi serialize, mọi messages đúng.

## 19. Câu hỏi kiểm tra kiến thức

**Câu 1.** Một client gọi `write` ba lần cho một message. Server có chắc gọi `read` ba lần tương ứng không?  
**Đáp án:** Không. TCP chỉ cung cấp byte stream có thứ tự; read/write/segment boundaries không được tương ứng 1:1.

**Câu 2.** Một lần `write` có thể chứa hai application messages không?  
**Đáp án:** Có. Nếu người gửi ghép hai frames và viết một `byte[]`, server phải decode **hai** messages dựa trên framing.

**Câu 3.** Vì sao một lần `read(buffer)` đủ 4 KB không chứng minh đã nhận một message?  
**Đáp án:** Buffer capacity không tạo boundary. Read có thể trả 1 byte, n bytes hoặc nhiều frames tùy dữ liệu đang có.

**Câu 4.** TCP có bảo toàn message boundary của Java `OutputStream.write` không?  
**Đáp án:** Không. TCP là ordered byte stream, không phải datagram/message transport.

**Câu 5.** Length-prefix 4 bytes thường được giải mã lúc nào?  
**Đáp án:** Khi đã có đủ **4 bytes header**; phải validate length trước khi cấp phát/đọc body.

**Câu 6.** Frame header length 5 nhưng chỉ có hai bytes payload rồi EOF. Chấp nhận payload hai bytes được không?  
**Đáp án:** Không. Đây là truncated frame, nên báo lỗi protocol/EOFException.

**Câu 7.** Header length 0 có đồng nghĩa stream EOF không?  
**Đáp án:** Không. Trong contract bài, đó là frame rỗng hợp lệ; EOF chỉ khi read trả -1 ở boundary.

**Câu 8.** Vì sao `String.length()` không phù hợp làm length header cho UTF-8?  
**Đáp án:** Vì String.length đo UTF-16 code units, còn header phải chứa số **UTF-8 bytes** được gửi.

**Câu 9.** `DataInputStream.readFully` có thể dùng nhiều lần raw read bên dưới không?  
**Đáp án:** Có. Nó chờ đủ N bytes hoặc báo EOF/IOException, không dựa vào một lần read.

**Câu 10.** Một chunk chứa `frame("TWO")+frame("THREE")`. Decoder trả mấy messages?  
**Đáp án:** Hai, theo đúng thứ tự; dùng vòng lặp xử lý mọi frames hoàn chỉnh.

**Câu 11.** Khi feed chỉ 2 bytes header, decoder nên xử lý sao?  
**Đáp án:** Giữ pending bytes và đợi chunk kế, không gọi getInt hoặc parse payload.

**Câu 12.** `ByteBuffer.compact()` có tự parse message không?  
**Đáp án:** Không. Nó di chuyển bytes chưa consume và chuyển buffer sang write mode; decoder vẫn phải thực hiện framing.

**Câu 13.** `SocketChannel.write` nonblocking trả 0 nhưng còn bytes pending; nên busy-loop không?  
**Đáp án:** Không. Đăng ký OP_WRITE/chờ readiness, giữ buffer còn dư và queue giới hạn.

**Câu 14.** `flush()` có đảm bảo receiver sẽ có một `read` tương ứng không?  
**Đáp án:** Không. Flush không định nghĩa message boundary TCP.

**Câu 15.** `setTcpNoDelay(true)` có sửa được parser đang coi một `read` là một message?  
**Đáp án:** Không. Nó thay Nagle behavior, không biến TCP thành message-based transport.

**Câu 16.** Bật TCP PSH có phải dấu End-of-Message không?  
**Đáp án:** Không. TCP segment flags không thay application framing.

**Câu 17.** `InputStream.available()==0` có nghĩa message hoàn tất chưa?  
**Đáp án:** Không. Nó chỉ ước lượng bytes hiện có thể đọc mà không block.

**Câu 18.** Delimiter LF có tốt cho payload chứa newline không?  
**Đáp án:** Không nếu không có escaping/encoding; newline trong payload bị hiểu là separator.

**Câu 19.** `BufferedReader.readLine` trả dòng cuối khi EOF thiếu LF có hợp lệ trong protocol bắt buộc newline cuối không?  
**Đáp án:** Không. API có thể trả text trước EOF nhưng protocol nghiêm ngặt phải tự nhận biết terminator và xử lý thiếu delimiter.

**Câu 20.** Nếu header chứa length 2 tỷ bytes, có nên `new byte[length]` không?  
**Đáp án:** Không. Validate max frame trước allocation để tránh OOM/DoS.

**Câu 21.** Two threads gửi header/payload xen kẽ cùng socket, TCP có tự sửa frame boundaries không?  
**Đáp án:** Không. Cần serialize toàn frame hoặc dùng một writer queue.

**Câu 22.** Vì sao nên kiểm thử parser với các chunk sizes cố định trước khi thay network packet sizes?  
**Đáp án:** Vì unit test deterministic; TCP packetization/scheduling không ổn định và không quyết định ứng dụng có framing đúng.

**Câu 23.** Nếu receiver đọc được đúng ALPHA/RED/BLUE thì có chứng minh ACK nghiệp vụ đã hoàn tất?  
**Đáp án:** Chỉ chứng minh decoder server đã nhận/giải mã trong demo; ACK/commit nghiệp vụ cần protocol riêng.

**Câu 24.** Khi socket bị reset sau khi client gửi một command, có chắc server chưa xử lý command không?  
**Đáp án:** Không. Server có thể đã nhận/commit trước reset; retry cần idempotency/status query theo contract.

## 20. Checklist áp dụng và tài liệu chuẩn

### Checklist triển khai

- [ ] Phân biệt **application message**, **application frame**, **write call**, **read call**, **TCP segment**.
- [ ] Không bao giờ dựa vào `read(buffer)` là đúng một message hoặc `write` tạo một TCP packet.
- [ ] Định nghĩa framing contract rõ: length-prefix, delimiter, fixed-size hoặc close-delimited tùy loại giao thức.
- [ ] Với length-prefix, thống nhất header size, endianness, số **bytes** payload, charset và max frame.
- [ ] Decoder phải **giữ incomplete header/payload** qua nhiều receive chunks.
- [ ] Decoder phải **xử lý nhiều frames trong một chunk** và không bỏ bytes dư.
- [ ] Trước khi cấp phát, **validate length** để tránh memory exhaustion, tràn số và malformed frames.
- [ ] Phân biệt EOF ngay boundary với EOF giữa header/payload.
- [ ] Không dùng `InputStream.available()` để đo đã đủ message.
- [ ] Với text, decode UTF-8 **sau khi đủ message bytes** hoặc dùng CharsetDecoder streaming đúng cách.
- [ ] Với delimiter, quy định escaping/line length và xử lý EOF thiếu terminator.
- [ ] Với `SocketChannel` nonblocking, giữ partial writes và xử lý `read()==0` khác EOF.
- [ ] Serialize outbound frames khi nhiều threads dùng một connection.
- [ ] Có read timeout, overall deadline, quota per connection, concurrency limit và backpressure.
- [ ] Không dựa vào `flush()`, TCP_NODELAY, Nagle, PSH/MSS để khôi phục message boundaries.
- [ ] Unit-test decoder qua mọi chunk sizes/ngẫu nhiên seeds, rồi mới integration-test bằng TCP.
- [ ] Log số bytes/message IDs, không bắt buộc một số read/segment cụ thể.
- [ ] Với lệnh có side effect, thiết kế ACK, dedup và retry idempotent ở tầng ứng dụng.

**Ghi nhớ then chốt:** **Gửi một message qua nhiều lần `write` vẫn là một message** nếu framing nói vậy. **Gửi nhiều messages trong một `write` vẫn là nhiều messages** nếu framing nói vậy. TCP giữ thứ tự của **bytes**, còn **message boundaries là trách nhiệm của protocol ứng dụng và decoder**, không phải kết quả của số lần gọi `read`/`write`.

### Tài liệu tham khảo

- [RFC 9293 — Transmission Control Protocol, `2.2 và `3.7](https://www.rfc-editor.org/rfc/rfc9293.html): TCP byte-stream service và segmentation không bảo đảm ánh xạ tới application reads/writes.
- [Java 17 `InputStream.read`, `readNBytes`, `available`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): số bytes thực đọc, EOF, readNBytes, available không phải framing.
- [Java 17 `DataInputStream.readInt` và `readFully`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): đọc length-prefix và báo EOF khi payload thiếu.
- [Java 17 `Socket` — `setSoTimeout`, `shutdownOutput`, `setTcpNoDelay`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html).
- [Java 17 `SocketChannel` — nonblocking reads/writes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java 17 `ByteBuffer` — flip, compact, endian](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html).
- [Java 17 `BufferedReader.readLine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html).
