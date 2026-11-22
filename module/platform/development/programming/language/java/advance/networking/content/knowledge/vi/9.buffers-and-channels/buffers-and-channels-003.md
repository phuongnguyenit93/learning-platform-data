# Giữ dữ liệu chưa xử lý khi thông điệp đi qua nhiều lần đọc

## 1. Mục tiêu và tình huống cần giải quyết

Một ứng dụng Java dùng `SocketChannel` để nhận dữ liệu TCP. Đầu gửi đóng gói hai thông điệp theo thứ tự. Đầu nhận gọi `read(ByteBuffer)` nhưng có thể nhận **một nửa header**, **một phần payload** hoặc **hai thông điệp và một phần thông điệp tiếp theo** trong cùng một lần đọc. Nếu bộ giải mã chỉ cố parse phần mới vừa nhận rồi gọi `clear()`, byte chưa đủ tạo thành message sẽ biến mất khỏi trạng thái xử lý.

Bài học này hướng dẫn giữ **những byte đã nhận nhưng chưa tiêu thụ thành thông điệp hoàn chỉnh** qua nhiều lượt đọc trong Java NIO. Trọng tâm là `ByteBuffer`, `SocketChannel`, state của parser và cơ chế framing. Đây là bài thuộc nhóm **Buffer và channel**; không cần tìm hiểu toàn bộ thiết kế selector hoặc giao thức nghiệp vụ khác để hiểu và triển khai đúng nguyên lý.

Sau bài học, bạn phải:
- Phân biệt **một lần `read`** với **một thông điệp ứng dụng**, đặc biệt trên luồng TCP.
- Hiểu `position`, `limit`, `capacity` và biết dùng `flip()` → parse → `compact()` để giữ byte còn dư.
- Xử lý **header chưa đủ**, **payload chưa đủ**, **nhiều frame trong một buffer**, **frame lớn hơn dung lượng ban đầu**, **EOF giữa frame** và **`read() == 0`**.
- Tự viết decoder có giới hạn bộ nhớ và trạng thái riêng cho mỗi kết nối; không làm mất, lặp, đảo byte khi đọc từng mảnh.
- Kiểm chứng code Java 17+ bằng các chunk cố tình cắt ngang ranh giới, rồi áp dụng cùng cơ chế vào `SocketChannel` thực.

## 2. Vì sao một thông điệp có thể đi qua nhiều lần đọc?

TCP cung cấp **luồng byte có thứ tự**. Nó không hứa rằng một lần `write` bên gửi sẽ tương ứng một lần `read` bên nhận. TCP segment, socket buffer, thời điểm scheduler chạy, tải hệ thống và kích thước `ByteBuffer` có thể khiến dữ liệu đến parser theo bất kỳ cách phân mảnh hợp lệ nào. Một lần `read` thậm chí chứa nhiều message ứng dụng.

Ví dụ ứng dụng tự định nghĩa message bằng bốn byte độ dài (big-endian) rồi đến payload UTF-8:

```text
Thông điệp A = "CAT":
  00 00 00 03  43 41 54
  [length=3]   [CAT]

Thông điệp B = "DOG":
  00 00 00 03  44 4F 47
  [length=3]   [DOG]

Byte stream trên kết nối TCP:
  00 00 00 03 43 41 54 00 00 00 03 44 4F 47
```

Các lần `SocketChannel.read` hoàn toàn có thể cắt stream như sau:

```text
read #1: 00 00
read #2: 00 03 43
read #3: 41 54 00 00 00 03 44
read #4: 4F 47
```

Sau `read #1`, parser chưa có đủ 4 byte header. Sau `read #2`, parser đã có header hoàn chỉnh nhưng mới thấy 1 byte payload; chưa thể công bố `CAT`. Sang `read #3`, parser mới có 2 byte còn lại của A và một phần header/payload B. Sang `read #4`, parser mới có đủ B.

**Nếu mất các byte còn dư ở một lần đọc, không có cách lấy lại byte đó bằng lần đọc tiếp theo.** TCP coi chúng đã được giao cho ứng dụng khi `read` trả về số byte dương.

Một lưu ý về phạm vi: ví dụ là **TCP stream**. UDP giữ ranh giới từng datagram và buffer nhỏ có thể làm **truncate** datagram; UDP không sử dụng cùng chiến lược giữ “phần dư một datagram” để nhận tiếp như TCP. Dù vậy, bản thân một thông điệp nghiệp vụ được chia qua nhiều datagram UDP vẫn cần cơ chế ghép mảnh riêng do ứng dụng định nghĩa.

## 3. Cần tách ba cấp độ trạng thái

Để thiết kế parser đúng, cần phân biệt:

1. **Transport input:** các byte đã đến socket và được `SocketChannel.read` chép vào buffer. Lượt read có thể trả `n > 0`, `n == 0` hoặc `-1` (EOF).
2. **Byte accumulator:** byte đã đến ứng dụng nhưng **chưa đủ để tạo thành một frame** hoặc chưa được parser tiêu thụ. Đây là phần cần được giữ giữa các lần đọc.
3. **Message parser/consumer:** thông điệp hoàn chỉnh đã được kiểm tra độ dài và lấy khỏi accumulator. Từ đây message thuộc về logic ứng dụng, hàng đợi công việc hoặc một cấu trúc dữ liệu khác.

```text
TCP socket
   │
   ▼  channel.read(...), nhận 0..N byte
ByteBuffer ở write mode: [byte cũ chưa đủ][byte mới]
   │
   ▼  flip()
ByteBuffer ở read mode:  [frame hoàn chỉnh][frame hoàn chỉnh][byte còn thiếu]
   │
   ├── dispatch frame hoàn chỉnh sang xử lý nghiệp vụ
   │
   ▼  compact()
ByteBuffer ở write mode: [byte còn thiếu][vùng trống để nhận tiếp]
   │
   └── lần read tiếp theo nối thêm sau các byte còn thiếu
```

**Bất biến cốt lõi:** Byte chưa đủ để hoàn thành frame phải luôn còn trong accumulator, đúng thứ tự, cho tới khi đủ dữ liệu hoặc kết nối bị đóng/lỗi. Sau khi dispatch một frame, byte của frame đó không được dispatch lại.

## 4. ByteBuffer: position, limit, capacity và mode

`ByteBuffer` sở hữu ba số quan trọng:

- `capacity`: dung lượng buffer, không đổi trong vòng đời đối tượng.
- `position`: chỉ số vị trí đọc/ghi tiếp theo.
- `limit`: ranh giới không được vượt khi đọc/ghi.
- `remaining()` = `limit - position`; `hasRemaining()` kiểm tra còn phần nằm giữa position và limit hay không.

Mọi lúc có bất biến `0 <= position <= limit <= capacity`.

Khi buffer mới tạo:

```java
ByteBuffer buffer = ByteBuffer.allocate(12);
```

Trạng thái là `position=0, limit=12, capacity=12`; ta thường gọi đây là **write mode** vì đang chuẩn bị chèn byte vào buffer.

Giả sử channel hoặc `put(...)` vừa ghi 7 byte, trạng thái là `position=7, limit=12`. Gọi `flip()` chuyển sang **read mode**: `position=0, limit=7`. Khi parser đã tiêu thụ 5 byte, `position=5, limit=7`, còn đúng 2 byte chưa xử lý. Lúc này:

```text
Sau flip và parse: capacity = 12, limit = 7, position = 5

index:   0   1   2   3   4   5   6   7  ... 11
         [  frame đã xử lý ][X ][Y ][không còn trong read limit]
                               ▲
                            position=5
         ^                               ^
        0                              capacity=12

compact() chép hai byte X,Y về đầu:
index:   0   1   2   3   4  ... 11
         [X ][Y ][    vùng có thể ghi    ]
                  ▲
              position=2, limit=12
```

Các thao tác chủ yếu:

| API | Tác dụng | Có giữ byte chưa đọc? |
| --- | --- | --- |
| `flip()` | `limit = position; position = 0`, chuẩn bị đọc những byte vừa ghi | Có, chỉ đổi con trỏ |
| `compact()` | Dồn byte trong `[position, limit)` về đầu, `position = số byte giữ lại`, `limit = capacity` | **Có**, đây là lựa chọn mặc định khi còn frame dở |
| `clear()` | `position = 0; limit = capacity`, chuẩn bị ghi lại từ đầu | **Không bảo toàn trạng thái byte dở**; có thể ghi đè chúng |
| `rewind()` | `position = 0`, giữ limit, đọc lại từ đầu | Có thể khiến frame đã xử lý bị xử lý **lặp** |
| `mark()/reset()` | Nhớ/khôi phục position tạm thời khi parse | Hữu ích để hoàn tác việc đọc header chưa đủ payload |
| `remaining()` | Số byte còn có thể đọc/ghi trong mode hiện tại | Chỉ là phép tính, không tự kiểm tra frame |

`compact()` **không xóa bộ nhớ**; nó chỉ chuyển byte còn lại và đổi position/limit. `clear()` cũng không zero-fill buffer; tên “clear” chỉ liên quan trạng thái con trỏ. Vì vậy không coi byte cũ trong vùng ngoài `[position, limit)` là dữ liệu hợp lệ.

## 5. Trường hợp quan trọng: header đủ nhưng payload chưa đủ

Giao thức minh họa quy định mỗi frame có:

```text
+---------------------+-------------------------------+
| 4-byte signed int   | length byte payload UTF-8     |
| big-endian length   | có thể 0..MAX_PAYLOAD byte    |
+---------------------+-------------------------------+
```

Phía gửi phải ghi **đúng byte length**, không phải `String.length()`. Phía nhận phải kiểm tra `0 <= length <= MAX_PAYLOAD` *trước khi* cấp phát hoặc giữ payload.

Giả sử buffer đang có:

```text
00 00 00 05  48 45
[length=5]  "HE" (thiếu "LLO")
```

Sau `flip()`, parser thấy đủ 4 byte header nên gọi `getInt()`. Nhưng `remaining() == 2 < 5`, nghĩa là chưa đủ payload. Nếu lúc này đơn giản `break` rồi `compact()`, **header đã bị tiêu thụ**, hai byte `HE` bị dồn về đầu và lần sau parser có thể đọc `HE...` như một header mới: giao thức mất đồng bộ.

Cách làm đúng:
1. Trước khi đọc length, gọi `mark()` ở đầu frame.
2. Đọc `length` và validate.
3. Nếu payload chưa đủ, gọi `reset()` để position quay **về đầu header**.
4. Thoát vòng parse; gọi `compact()` để giữ **cả header và payload một phần**.
5. Lần đọc tiếp theo nối thêm sau byte đã giữ; thử parse lại từ đầu frame.

Ví dụ logic trong read mode:

```java
while (buffer.remaining() >= Integer.BYTES) {
    buffer.mark();
    int length = buffer.getInt();
    if (length < 0 || length > MAX_PAYLOAD) {
        throw new IOException("Invalid frame length");
    }
    if (buffer.remaining() < length) {
        buffer.reset(); // cả header lẫn payload dở vẫn là pending
        break;
    }
    byte[] payload = new byte[length];
    buffer.get(payload);
    handleFrame(payload);
}
buffer.compact();
```

Đây là **mảnh code minh họa**, cần `ByteBuffer buffer`, hằng `MAX_PAYLOAD`, `handleFrame` và `java.io.IOException` đã tồn tại. Điều kiện vòng lặp bảo vệ `getInt()` khỏi đọc khi chưa có đủ 4 byte; nếu bỏ kiểm tra đó, có thể gặp `BufferUnderflowException`.

### Tại sao phải dùng vòng `while` mà không dùng `if`?

Một lần `read` có thể chứa **nhiều frame hoàn chỉnh**, chẳng hạn `[len=1]["A"][len=1]["B"][len=2]["OK"]`. Vòng `while` xử lý hết các frame đã đủ, rồi mới giữ lại phần dở. Nếu chỉ xử lý một frame trên mỗi callback và không tiếp tục parse phần đã nằm trong buffer, chương trình có thể **kẹt message** dù byte đã đến đủ, vì không có read event mới để đánh thức parser.

## 6. Thiết kế accumulator tồn tại qua nhiều lần feed

Có hai cách phổ biến:

- **Một ByteBuffer trạng thái riêng cho từng kết nối:** channel đọc trực tiếp vào buffer, parser `flip/compact` chính buffer đó. Dễ tối ưu, nhưng cần capacity đủ cho frame lớn nhất hoặc cơ chế growth.
- **Một buffer đọc I/O và một accumulator parser:** channel đọc vào buffer I/O, sau đó chuyển byte sang decoder giữ state qua các callback. Rõ ràng về ownership; có thể phát sinh một lần copy, hữu ích cho bài kiểm thử deterministic.

Ví dụ ở mục 7 dùng hướng thứ hai ở mức mô phỏng các chunk read, tránh phụ thuộc việc hệ điều hành thực sự chia TCP stream ra sao. Ví dụ ở mục 9 dùng hướng thứ nhất trên `SocketChannel` thực.

**Không được tạo một accumulator mới trong mỗi lần đọc.** Nếu mỗi callback thực hiện `ByteBuffer.allocate(...)` rồi parse và bỏ buffer, mọi header/payload chưa đủ sẽ mất ngay khi callback kết thúc. Với server nhiều kết nối, mỗi connection cần trạng thái độc lập; không dùng một `ByteBuffer` mutable chung cho mọi peer.

## 7. Java 17+ chạy được: parser vẫn đúng với các chunk cố tình cắt giữa frame

Chương trình dưới đây tự tạo wire bytes bằng `DataOutputStream.writeInt`, sau đó đưa các byte ấy vào `FrameDecoder` qua 7 chunk có kích thước khác nhau. Nó thực hành đầy đủ:
- Header 4 byte có thể chia qua nhiều chunk.
- Payload có thể chia qua nhiều chunk.
- Một chunk có thể chứa phần cuối frame trước và phần đầu frame tiếp theo.
- `compact()` giữ toàn bộ byte chưa tiêu thụ.
- Buffer ban đầu chỉ 8 byte, có thể **grow** có kiểm soát khi frame hợp lệ chưa đủ chỗ.

Lưu đúng tên file `FrameAcrossReadsDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class FrameAcrossReadsDemo {
    private static final int MAX_PAYLOAD = 64;

    static final class FrameDecoder {
        private ByteBuffer pending = ByteBuffer.allocate(8); // write mode

        void accept(byte[] chunk) {
            int offset = 0;
            while (offset < chunk.length) {
                if (!pending.hasRemaining()) grow();
                int count = Math.min(pending.remaining(), chunk.length - offset);
                pending.put(chunk, offset, count);
                offset += count;
                parseAvailable();
            }
        }

        private void parseAvailable() {
            pending.flip(); // write mode -> read mode
            while (pending.remaining() >= Integer.BYTES) {
                pending.mark(); // remember where this frame starts
                int length = pending.getInt();
                if (length < 0 || length > MAX_PAYLOAD) {
                    throw new IllegalArgumentException("invalid frame length");
                }
                if (pending.remaining() < length) {
                    pending.reset(); // restore header for next read
                    break;
                }
                byte[] payload = new byte[length];
                pending.get(payload);
                System.out.println("FRAME " + new String(payload, StandardCharsets.UTF_8));
            }
            pending.compact(); // keep unconsumed bytes, return to write mode
        }

        private void grow() {
            int maximum = MAX_PAYLOAD + Integer.BYTES;
            if (pending.capacity() >= maximum) {
                throw new IllegalStateException("frame exceeds buffer policy");
            }
            ByteBuffer larger = ByteBuffer.allocate(
                    Math.min(pending.capacity() * 2, maximum));
            pending.flip();
            larger.put(pending);
            pending = larger;
        }

        int retainedBytes() { return pending.position(); }

        void endOfStream() {
            pending.flip();
            if (pending.hasRemaining()) {
                throw new IllegalStateException("truncated frame at EOF");
            }
            System.out.println("EOF complete");
        }
    }

    private static void writeFrame(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            writeFrame(out, "A");
            writeFrame(out, "HELLO");
            writeFrame(out, "OK");
        }
        byte[] wire = bytes.toByteArray(); // 5 + 9 + 6 = 20 bytes
        int[] chunkSizes = {2, 1, 4, 2, 5, 1, 5};
        FrameDecoder decoder = new FrameDecoder();
        int offset = 0;
        for (int size : chunkSizes) {
            byte[] chunk = Arrays.copyOfRange(wire, offset, offset + size);
            decoder.accept(chunk);
            offset += size;
            System.out.println("chunk=" + size
                    + " retained=" + decoder.retainedBytes());
        }
        if (offset != wire.length) throw new AssertionError("bad test chunks");
        decoder.endOfStream();
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac FrameAcrossReadsDemo.java
java FrameAcrossReadsDemo
```

Stdout đã kiểm chứng:

```text
chunk=2 retained=2
chunk=1 retained=3
FRAME A
chunk=4 retained=2
chunk=2 retained=4
FRAME HELLO
chunk=5 retained=0
chunk=1 retained=1
FRAME OK
chunk=5 retained=0
EOF complete
```

### Diễn giải output

Wire format có 3 frame: `A` chiếm 4+1=5 byte, `HELLO` chiếm 4+5=9 byte, `OK` chiếm 4+2=6 byte, tổng **20 byte**.

- **Chunk 2 byte, rồi 1 byte:** parser chỉ có 2 rồi 3 byte, không đọc header chưa đủ. `retained=3`.
- **Chunk 4 byte:** tổng có 7 byte; parser lấy frame `A` (5 byte), còn 2 byte thuộc header `HELLO`. `compact()` giữ đúng 2 byte đó.
- **Chunk 2 byte:** header `HELLO` đủ 4 byte nhưng payload 5 byte vẫn thiếu; parser `reset()` về đầu header. `retained=4`.
- **Chunk 5 byte:** chương trình cần mở rộng buffer từ 8 lên 16 byte khi header+payload dở không vừa; sau đó nhận đủ 9 byte và phát `FRAME HELLO`. Không có byte bị mất.
- **Chunk 1 byte:** giữ 1 byte đầu header `OK`.
- **Chunk 5 byte:** đủ frame `OK`, phát thông điệp và buffer hết byte chờ.
- **EOF:** không còn header/payload đang chờ → `EOF complete`.

Đặc điểm quan trọng của decoder: sau mỗi `accept`, `pending` luôn trở về **write mode**; `position()` khi đó biểu thị **số byte chưa tiêu thụ đang được giữ**, không phải tổng byte đã nhận từ đầu kết nối.

### Giới hạn của ví dụ

Đây là chương trình mô phỏng việc chia read thành chunk, nên kết quả deterministic. Nó **không** tự mở kết nối TCP; mục 9 minh họa áp dụng tương tự lên kênh socket. Demo dùng ASCII để stdout ổn định, còn quy tắc wire length vẫn là **số byte UTF-8**. Phần `endOfStream()` là thao tác cuối vòng đời decoder; sau khi lật buffer để kiểm tra EOF, không gọi `accept` thêm vào chính decoder đó.

## 8. Khi một frame lớn hơn buffer ban đầu: grow có giới hạn

Một buffer dung lượng 8 byte không thể chứa cùng lúc header 4 byte và payload `HELLO` 5 byte. Nếu parser chỉ làm `compact()`, thấy `position == capacity` rồi gọi `channel.read(buffer)` tiếp, buffer **không còn chỗ ghi**. Với blocking channel, `read` khi buffer không có remaining có thể trả 0, làm ứng dụng tưởng “mạng không gửi nữa” dù bản thân parser đang giữ một frame dở.

Có ba chiến lược hợp lệ:

1. **Cấp buffer đủ lớn cho frame tối đa**: nếu `MAX_PAYLOAD = 64`, buffer ít nhất `4 + 64 = 68` byte. Đơn giản nhưng tốn bộ nhớ cho nhiều kết nối nếu max cao.
2. **Grow buffer tới giới hạn cấu hình**: như `FrameDecoder.grow()`; chuyển byte đang giữ sang buffer mới bằng `flip()` rồi `put(...)`. Không tăng vô hạn và không đọc length ngoài protocol.
3. **Parser theo trạng thái header/payload riêng**: đọc đủ header, validate length, cấp một payload buffer bounded; khi chưa đủ payload, tiếp tục fill phần còn thiếu, hoàn tất mới dispatch. Cách này phù hợp khi muốn xử lý frame lớn mà không buộc một accumulator liên tục chứa cả header+payload.

Trong mọi chiến lược, **giới hạn frame là yêu cầu bắt buộc**, đặc biệt khi source không tin cậy. Một header ghi `2_000_000_000` không được khiến server lập tức cấp phát mảng 2 GB hoặc tích lũy vô hạn. Hãy reject sớm khi length âm, quá max, không hợp phiên bản protocol hoặc vượt quota của connection.

Tránh tính toán `length + 4` trước khi validate nếu `length` do mạng cung cấp; integer overflow có thể biến số dương rất lớn thành số sai. Kiểm tra `0 <= length <= MAX_PAYLOAD` rồi mới cộng phần header.

## 9. Java 17+ chạy được: đọc từ SocketChannel thật

Chương trình độc lập dưới đây tạo TCP listener trên `127.0.0.1` và cho client cùng tiến trình gửi hai frame. Parser dùng **một `ByteBuffer` tồn tại xuyên suốt vòng `read`**, không giải mã từng lượt read riêng lẻ. Vì ví dụ đặt `MAX_FRAME = 60` và buffer `MAX_FRAME + 4`, một frame hợp lệ luôn có thể được tích lũy đầy đủ.

Lưu đúng tên file `SocketChannelFrameDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class SocketChannelFrameDemo {
    private static final int MAX_FRAME = 60;

    private static byte[] encode(String... messages) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            for (String message : messages) {
                byte[] payload = message.getBytes(StandardCharsets.UTF_8);
                out.writeInt(payload.length);
                out.write(payload);
            }
        }
        return bytes.toByteArray();
    }

    private static void parse(ByteBuffer buffer) throws IOException {
        buffer.flip();
        while (buffer.remaining() >= Integer.BYTES) {
            buffer.mark();
            int length = buffer.getInt();
            if (length < 0 || length > MAX_FRAME) {
                throw new IOException("Invalid frame length: " + length);
            }
            if (buffer.remaining() < length) {
                buffer.reset();
                break;
            }
            byte[] payload = new byte[length];
            buffer.get(payload);
            System.out.println("message=" +
                    new String(payload, StandardCharsets.UTF_8));
        }
        buffer.compact();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            try (SocketChannel sender = SocketChannel.open(
                         new InetSocketAddress(loopback,
                                 ((InetSocketAddress) listener.getLocalAddress()).getPort()));
                 SocketChannel receiver = listener.accept()) {

                ByteBuffer outgoing = ByteBuffer.wrap(encode("cat", "elephant"));
                while (outgoing.hasRemaining()) sender.write(outgoing);
                sender.shutdownOutput();

                ByteBuffer incoming = ByteBuffer.allocate(MAX_FRAME + Integer.BYTES);
                for (;;) {
                    int n = receiver.read(incoming);
                    if (n == -1) break;
                    if (n == 0) continue; // relevant for nonblocking channels
                    parse(incoming); // retains incomplete header/body
                }
                incoming.flip();
                if (incoming.hasRemaining()) {
                    throw new IOException("Truncated frame at EOF");
                }
                System.out.println("EOF complete");
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SocketChannelFrameDemo.java
java SocketChannelFrameDemo
```

Stdout thông thường trên loopback, khi quá trình gửi/nhận thành công:

```text
message=cat
message=elephant
EOF complete
```

**Vì sao code chạy đúng với nhiều cách phân mảnh TCP?** Một lần `read` có thể lấy trọn hai frame, hoặc chỉ lấy vài byte, nhưng cả hai trường hợp đều đi qua `parse(incoming)`. Sau `parse`, `compact()` dồn header/payload dở về đầu và giữ vị trí ghi cho lần nhận kế tiếp. Sau khi bên gửi gọi `shutdownOutput()`, phía nhận tiếp tục đọc cho tới `-1` rồi kiểm tra không còn phần frame dở. Nếu mạng/socket bị lỗi, code sẽ ném `IOException`; TCP không bảo đảm ứng dụng luôn hoàn tất mọi frame khi kết nối bị cắt.

Với mã production, cần thời hạn chờ hợp lý, quản lý thread, timeout, giới hạn số kết nối, xử lý payload lỗi và timeout giữ frame dở. Ví dụ chỉ dùng loopback để kiểm chứng nguyên lý.

### Vì sao dùng `sender.shutdownOutput()` thay cho việc chờ “không còn byte”?

`shutdownOutput()` thông báo kết thúc **chiều gửi** của TCP, cho phép receiver quan sát EOF sau khi nhận hết byte đang được giao. Chỉ vì `read` tạm thời chưa có dữ liệu **không** chứng minh bên gửi đã xong message; receiver phải dựa vào **length-prefix** để biết message hoàn chỉnh, và chỉ dùng EOF để biết luồng gửi đã kết thúc.

## 10. Cách xử lý `read()`, EOF và non-blocking NIO

`SocketChannel.read(ByteBuffer)` có thể trả:

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| `n > 0` | Đã đưa `n` byte mới vào buffer, tăng `position` | `flip()`, parse hết frame hoàn chỉnh, `compact()` giữ phần dư |
| `n == 0` | Không có byte nào được đưa vào buffer; thường xảy ra với non-blocking channel | Không parse ra message mới chỉ vì 0; chờ readiness tiếp hoặc xử lý tình trạng buffer đầy |
| `n == -1` | Đầu đọc đã đến EOF | Xử lý frame hoàn chỉnh còn lại, sau đó kiểm tra **còn byte dở hay không**; đóng/cleanup |

Trong blocking mode và có chỗ ghi trong `ByteBuffer`, `SocketChannel.read` thường block cho tới khi có ít nhất 1 byte hoặc EOF/lỗi. Với non-blocking mode, `read` có thể trả `0` ngay khi chưa có byte. Một `SelectionKey` báo `OP_READ` có thể do dữ liệu, EOF hoặc lỗi, nên **readiness chỉ là tín hiệu kiểm tra**, không phải lời bảo đảm nhận được một frame đầy đủ.

### EOF sạch và EOF giữa frame

Nếu sau cùng buffer không còn byte chưa xử lý, kết thúc stream là **sạch ở mức framing**. Nếu chỉ còn 1–3 byte header, hoặc một header đầy đủ và payload chưa đủ, đó là **truncated frame**. Không nên lặng lẽ drop rồi báo thành công. Có thể báo `IOException("Truncated frame at EOF")` và kết thúc connection.

Nếu protocol cho phép zero-length frame, header `00 00 00 00` vẫn là một **frame đầy đủ**. Đừng nhầm frame độ dài 0 với EOF: EOF là trạng thái channel, không phải frame. Trong ứng dụng cụ thể, có thể quy định length phải lớn hơn 0 rồi reject frame rỗng; đây là lựa chọn nghiệp vụ.

### Non-blocking và Selector

Trong server nhiều kết nối:

```text
key A -> SocketChannel A + FrameDecoder A
key B -> SocketChannel B + FrameDecoder B
key C -> SocketChannel C + FrameDecoder C
```

Mỗi kết nối có `SelectionKey.attachment()` hoặc map state riêng; khi key readable, đọc đến khi channel trả 0, EOF hoặc đến giới hạn công việc của vòng event loop. Không tạo decoder mới ở mỗi event. Không copy byte của kết nối A vào accumulator của B.

**Không viết busy loop** `while (channel.read(buffer) == 0) { }` vì nó đốt CPU. Dựa vào `selector.select()` để chờ và chỉ giữ `OP_READ` khi còn khả năng tiếp nhận/parse; nếu công việc xử lý downstream quá tải, điều chỉnh read interest/backpressure có chủ đích.

## 11. Khi dùng buffer riêng cho I/O và accumulator

Một số kiến trúc muốn channel đọc vào buffer I/O nhỏ, rồi chuyển byte sang decoder có lifetime dài. Luồng đúng:

```text
channel.read(ioBuffer) → ioBuffer.flip()
→ decoder.accept(các byte đọc được)
→ ioBuffer.clear() cho lần đọc tiếp theo

decoder.accept:
  ghép vào pending buffer của CHÍNH kết nối đó
  parse các frame đầy đủ
  compact giữ phần còn thiếu
```

Dùng buffer I/O tạm thời thì `clear()` sau khi đã chuyển byte vào decoder là hợp lệ, vì **decoder đang sở hữu byte chưa xử lý**. Ngược lại, nếu buffer I/O **đồng thời** là accumulator thì phải dùng `compact()` sau parse, không được `clear()` khi còn phần dư. Hai thiết kế đều đúng nếu ownership và lifetime được xác định rõ.

Một mảnh phương thức minh họa việc chuyển byte sang decoder `FrameAcrossReadsDemo.FrameDecoder` ở mục 7:

```java
static void receive(SocketChannel channel,
                    FrameAcrossReadsDemo.FrameDecoder decoder)
        throws IOException {
    ByteBuffer io = ByteBuffer.allocate(1024);
    for (;;) {
        int n = channel.read(io);
        if (n == -1) {
            decoder.endOfStream();
            return;
        }
        if (n == 0) continue;
        io.flip();
        byte[] bytes = new byte[io.remaining()];
        io.get(bytes);
        decoder.accept(bytes);
        io.clear(); // byte dở đã chuyển sang decoder
    }
}
```

Đây là **mảnh code**, cần import `java.nio.ByteBuffer`, `java.nio.channels.SocketChannel`, `java.io.IOException` và class decoder ở mục 7. Không nên chạy vòng `n == 0` liên tục trong non-blocking mode; mảnh code này phù hợp cách gọi blocking và dùng làm giải thích ownership. Nếu sử dụng selector thật, chỉ đọc khi được báo readiness và trả điều khiển cho event loop khi chưa có dữ liệu.

## 12. Vòng đời ByteBuffer và các lỗi gây mất dữ liệu

### Lỗi A: gọi `clear()` trước khi frame hoàn tất

```java
int n = channel.read(buffer);
if (n > 0) {
    buffer.flip();
    parseWhateverIsAvailable(buffer);
    buffer.clear(); // SAI nếu parser vẫn còn byte chưa xử lý
}
```

Nếu parser chỉ tiêu thụ một frame rồi còn header của frame tiếp theo, `clear()` khiến lần `read` sau ghi đè từ index 0. Cần `compact()`, hoặc chuyển byte còn dở sang một accumulator riêng trước `clear()`.

### Lỗi B: đọc header rồi không phục hồi khi payload thiếu

Nếu parser gọi `getInt()` rồi thấy thiếu payload mà không `reset()`/giữ state length, sau `compact` chỉ còn payload dở, khiến lần sau nó được diễn giải là header mới. Phải **mark/reset** hoặc dùng parser state machine lưu riêng `expectedLength`.

### Lỗi C: chỉ parse một frame cho mỗi read

`if (buffer.remaining() >= frameSize) parseOne()` không đủ khi buffer chứa nhiều frame. Dùng vòng parse đến khi không còn một frame hoàn chỉnh. Không được giả định sẽ có sự kiện read mới để xử lý byte đã được lưu trong buffer.

### Lỗi D: gọi `flip()` hai lần hoặc `compact()` sai mode

`flip()` liên tiếp khi position đang 0 có thể khiến limit trở thành 0, làm “trống” vùng có dữ liệu theo góc nhìn parser. `compact()` trên buffer chưa được đặt read mode cũng có thể giữ/di chuyển sai vùng. Quy ước nhất quán:

```text
write mode:   channel.read(buffer) hoặc buffer.put(...)
read mode:    buffer.flip() -> parse
write mode:   buffer.compact() (giữ byte dở)
lặp lại
```

### Lỗi E: chia sẻ ByteBuffer mutable qua nhiều callback/thread

`ByteBuffer` có position/limit mutable và dữ liệu backing mutable; nó **không tự an toàn để nhiều thread đồng thời thay đổi**. Nếu một worker xử lý `slice`/`duplicate` trỏ tới cùng dữ liệu trong khi event loop compact/đọc tiếp, worker có thể thấy payload bị ghi đè. Cần copy sang buffer owned riêng, reference counting có quy tắc nghiêm ngặt hoặc bảo đảm không dùng lại memory trước khi consumer hoàn thành.

### Lỗi F: tạo buffer mới trong từng callback

Tạo `ByteBuffer.allocate(4096)` và bỏ đi sau mỗi `OP_READ` event khiến frame dở không có nơi tồn tại giữa events. Gắn state vào connection hoặc protocol session và chỉ giải phóng khi connection đóng/decoder bị reset có chủ đích.

### Lỗi G: dùng `capacity()` như số byte hợp lệ

Khi ở read mode, dữ liệu hợp lệ từ `position` đến `limit`. `capacity` chỉ là dung lượng; không phải frame length, không phải số byte vừa nhận. Hãy dùng `remaining()` và length đã được protocol xác thực.

## 13. Hai chiến lược giữ state: tích lũy nguyên frame và state machine

### 13.1. Cumulative buffer + mark/reset

Phù hợp với frame nhỏ/vừa và giới hạn biết trước:
- Giữ header và payload dở trong cùng `ByteBuffer`.
- Mỗi lần parse thử đọc length, nếu chưa đủ thì reset về đầu frame.
- Sau xử lý nhiều frame, compact byte còn lại.
- Cần đủ capacity cho frame lớn nhất hoặc cơ chế tăng bounded.

Ưu điểm: code gọn, dễ kiểm chứng. Nhược điểm: có thể copy byte dở nhiều lần khi compact/grow; bộ nhớ tối đa thường bằng kích thước frame lớn nhất nhân số kết nối.

### 13.2. Incremental state machine

Có thể thiết kế:

```text
READ_HEADER (cần 4 byte)
   │ đủ header, kiểm tra length <= MAX
   ▼
READ_BODY (cần chính xác length byte)
   │ đủ body
   ▼
DISPATCH_FRAME
   │
   └── trở về READ_HEADER cho frame kế tiếp
```

State là `headerBuffer`, `expectedLength`, `bodyBuffer`, `bytesReceived`. Lần `read` có thể chỉ bổ sung 2 byte header, hoặc 10 byte body; khi đủ thì chuyển state. Mã dài hơn nhưng phù hợp với streaming parser, tối ưu copy và kiểm soát memory. **Không** coi một lượt read là một state transition bắt buộc: một lượt read có thể làm đầy header, body và nhiều frame tiếp theo.

### So sánh

| Tiêu chí | Cumulative buffer | Incremental state machine |
| --- | --- | --- |
| Dễ triển khai | Cao cho length-prefix đơn giản | Cần nhiều trạng thái |
| Header/payload dở | Dùng `mark/reset` và `compact` | Lưu state/expected byte count |
| Một buffer chứa nhiều frame | Vòng `while` parse liên tiếp | Vòng state transition |
| Payload lớn | Cần buffer grow hoặc đủ capacity | Có thể fill payload buffer riêng |
| Tối ưu copy | `compact` có thể di chuyển byte | Có thể giảm copy nhưng tăng độ phức tạp |
| Kiểm tra EOF | `pending.hasRemaining()` | Kiểm tra state và số byte còn thiếu |

Cả hai đều có cùng bất biến: **byte đã nhận và chưa hoàn thành frame phải được bảo toàn chính xác**.

## 14. UTF-8, byte order và protocol framing

### 14.1. Length-prefix phải đo byte

Nếu sender gửi `"Xin chào"` bằng UTF-8, `String.length()` trả số UTF-16 code unit, **không** phải số byte trên wire. Sender phải encode trước:

```java
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
out.writeInt(bytes.length);
out.write(bytes);
```

Receiver đọc đủ số byte đó rồi mới decode. Nếu decode từng chunk nhận được như string riêng, một code point UTF-8 nhiều byte có thể bị cắt giữa hai lần read và thành ký tự lỗi. Với parser streaming thật, dùng `CharsetDecoder` và giữ trạng thái decode giữa các chunk, không giải mã bằng `new String(chunk)` độc lập rồi nối nếu chưa bảo đảm ranh giới ký tự.

### 14.2. Endianness phải thống nhất

`ByteBuffer` mới mặc định `BIG_ENDIAN`. `DataOutputStream.writeInt` cũng ghi 4 byte theo thứ tự **big-endian**. Nếu bên gửi thiết kế little-endian còn bên nhận gọi `getInt()` mặc định, frame length sẽ sai. Hãy ghi rõ format wire:

```text
4 byte big-endian signed int, valid range 0..MAX_PAYLOAD
then exactly length bytes of UTF-8
repeat until EOF
```

Nếu protocol cần little-endian, đặt `buffer.order(ByteOrder.LITTLE_ENDIAN)` trước khi parse và bảo đảm encoder dùng cùng quy ước. Với nhiều ngôn ngữ, không dựa vào byte order mặc định của CPU.

### 14.3. Không phải protocol nào cũng dùng length-prefix

Các cách framing khác:
- **Delimiter:** một dòng kết thúc bằng `\n`. Phải giữ byte sau delimiter và giữ dòng chưa đủ qua nhiều lần đọc, áp dụng max line length và quy tắc escape.
- **Fixed-size record:** đợi đủ N byte; dễ tính nhưng có thể phải padding.
- **Varint length:** header dài biến đổi; header **cũng có thể bị chia** qua nhiều read, cần state máy đọc varint và chặn overflow.
- **HTTP, WebSocket, TLS/application protocol:** có framing/record riêng; không tự dùng ví dụ 4-byte length-prefix nếu protocol không quy định như vậy.

Đừng sử dụng “đợi một khoảng im lặng” hoặc “một `read` là một message” làm framing; timing mạng không phải ranh giới giao thức.

## 15. EOF, timeout và khôi phục sau lỗi

Tình huống cần phân biệt:

| Tình huống | Trạng thái | Kết luận |
| --- | --- | --- |
| Có đủ frame, sau đó EOF, không còn pending | Hoàn chỉnh | Có thể đóng connection sạch về mặt framing |
| EOF chỉ sau 2/4 byte header | Header dở | Truncated protocol frame; báo lỗi |
| EOF sau length=100 nhưng mới có 70 byte | Payload dở | Truncated protocol frame; không dispatch 70 byte như message đầy đủ |
| `read` trả `0` ở non-blocking | Không có byte mới ngay lúc đó | Giữ state, chờ event tiếp |
| Đọc đủ frame nhưng handler chưa xử lý xong | Parser hoàn chỉnh, business xử lý dở | Đảm bảo ownership/queue/backpressure; không đọc lại frame |
| Peer gửi length âm hoặc vượt MAX | Header không hợp lệ | Reject, thường đóng connection |
| Timeout giữa frame | Không thể suy ra peer không còn gửi | Áp dụng timeout/quota; kết thúc connection hoặc protocol-specific retry |

Việc TCP bảo đảm thứ tự byte khi kết nối còn hoạt động **không** đồng nghĩa mọi yêu cầu nghiệp vụ luôn thực hiện đúng một lần. Nếu client gửi request nhưng không biết server đã xử lý trước khi mất kết nối, retry cần request ID/idempotency theo giao thức; không giải quyết bằng `compact()`.

Đừng tiếp tục parse những byte còn lại bằng cách bỏ qua một header lỗi rồi tìm “frame tiếp theo” nếu protocol không có cơ chế resynchronization. Với length-prefix không có magic marker/checksum, mất đồng bộ có thể khiến toàn bộ dữ liệu sau đó bị giải thích sai.

## 16. Bộ nhớ, ownership và backpressure trong server nhiều kết nối

Với `N` kết nối đồng thời, nếu mỗi kết nối giữ một buffer tối đa `M` byte, chi phí buffer thô có thể xấp xỉ `N × M`, chưa tính object overhead, TLS và work queue. Ví dụ một buffer tối đa 1 MiB cho 10.000 kết nối là lượng memory rất lớn; không chọn max frame tùy tiện.

Thực hành cần:
- **Giới hạn độ dài frame** từ protocol và chặn trước allocation, kể cả integer overflow.
- **Giới hạn pending bytes và thời gian sống** của frame dở. Peer gửi 1 byte mỗi phút có thể giữ connection và memory quá lâu (slowloris-like behavior).
- **Giới hạn số frame và bytes xử lý mỗi vòng event loop** để một kết nối không chiếm hết thời gian CPU.
- **Backpressure:** khi handler/queue chưa tiêu thụ kịp, hạn chế đọc thêm hoặc điều chỉnh `OP_READ`; tránh queue tăng vô hạn dù parser luôn đúng.
- **Ownership:** handler nhận payload đã copy hoặc một vùng memory có lifetime được quản lý, không tham chiếu buffer sẽ bị `compact` hoặc `read` ghi đè.
- **Log không rò rỉ dữ liệu:** ghi số byte/connection ID/error code có giới hạn; không tự in payload nhạy cảm vào log.
- **Thời gian chờ đọc/ghi:** với non-blocking dùng deadline/selector scheduling; với blocking có thể cấu hình timeout qua socket khi phù hợp.

`ByteBuffer.allocateDirect` có thể hữu ích với I/O tải cao, nhưng direct buffer chi phí allocation/deallocation cao hơn và thường có bộ nhớ ngoài heap. Chỉ chọn theo benchmark/lifetime thực tế. `compact()` và `flip()` giữ cùng logic dù heap hay direct; không được giả định direct buffer luôn có mảng truy cập được qua `array()`. Ví dụ bài học dùng heap buffer để dễ kiểm chứng.

Một chi tiết thường gặp: nếu parser trả `ByteBuffer.slice()` cho worker, slice vẫn **dùng chung dữ liệu nền**. `slice()` không mặc nhiên sao chép payload. Hãy copy hoặc giữ ownership trước khi tái sử dụng vùng nhớ cho lượt read sau.

## 17. Kiểm thử parser: cắt ở mọi vị trí, ghép nhiều frame và EOF

Một bài kiểm tra tốt nên dựa trên **wire bytes chuẩn** và thay đổi cách chia chunk độc lập với nội dung message. Với cùng một chuỗi wire bytes, decoder phải phát đúng cùng danh sách frame dù cắt ở bất kỳ vị trí nào.

| Test | Dữ liệu đưa vào | Kết quả phải đạt |
| --- | --- | --- |
| Header 4 byte trong 4 lần read | `[00] [00] [00] [03] [CAT]` | Chưa dispatch khi header chưa đủ |
| Header đủ, payload thiếu | `[len=5][HE]` rồi `[LLO]` | Chỉ dispatch `HELLO` khi đủ 5 byte |
| Hai frame trong một chunk | `[len=1][A][len=2][OK]` | Dispatch hai frame liên tiếp |
| Một frame kết thúc giữa chunk | `[frame A][2 byte header B]` | Dispatch A, giữ 2 byte header B |
| Buffer ban đầu quá nhỏ | Frame hợp lệ dài hơn capacity hiện tại | Grow có giới hạn hoặc dùng state payload riêng, không spin |
| Length âm/giá trị quá max | `[FF FF FF FF]` hoặc length > MAX | Reject trước allocation |
| EOF giữa header | Chỉ 1–3 byte header rồi EOF | Báo truncated frame |
| EOF giữa body | Length=6, body mới có 3 byte rồi EOF | Báo truncated frame |
| EOF sau frame hoàn chỉnh | Không còn pending | Kết thúc sạch |
| Frame rỗng | Length=0 | Dispatch frame rỗng hoặc reject theo policy; không nhầm EOF |
| UTF-8 split giữa hai read | Một code point nhiều byte bị cắt | Decode đúng sau khi có đủ payload |
| Một connection chậm, một connection nhanh | Hai channel/state riêng | Không trộn dữ liệu hoặc khiến connection nhanh bị mất state |

Với unit test, có thể tạo một `byte[] wire` chuẩn rồi lặp mọi cut position `i` trong khoảng 0..wire.length, feed `wire[0:i]` và `wire[i:end]`, so sánh danh sách frame với kết quả kỳ vọng. Với nhiều frame, thử mọi phân đoạn ngẫu nhiên nhưng **giữ nguyên thứ tự byte**. Chỉ dùng test dựa trên thời gian/loopback là không đủ vì hệ điều hành có thể vô tình gom tất cả dữ liệu trong một lần read và che lấp bug.

Ở mức tích hợp, kiểm thử riêng lifecycle: close giữa frame, timeout, multiple connections, đầy buffer, queue downstream quá tải, payload độc hại và thay đổi quyền sở hữu buffer.

## 18. Quy trình xử lý một lần read trong thực tế

Khi nhận một event đọc từ `SocketChannel`, có thể áp dụng trình tự:

1. Lấy **connection state** đang giữ accumulator/parser và bộ đếm giới hạn.
2. Đọc vào vùng buffer đang ở **write mode** và còn `remaining() > 0`; nếu không còn chỗ, xử lý frame hoặc grow bounded **trước khi đọc**.
3. Nếu `n > 0`, chuyển sang **read mode** bằng `flip()`; parse toàn bộ frame đã đủ.
4. Với header chưa đủ, không đọc `getInt`; với payload chưa đủ, **khôi phục position về đầu frame** hoặc lưu state riêng.
5. Dispatch payload hoàn chỉnh, quản lý ownership để buffer gốc có thể tái sử dụng an toàn.
6. Gọi `compact()`, giữ byte chưa xử lý; lần read tiếp theo chèn sau byte đó.
7. Nếu `n == 0` trong non-blocking, ngừng vòng đọc khi phù hợp và chờ selector; nếu `n == -1`, kiểm tra phần pending/EOF và cleanup.
8. Giới hạn pending, max payload, thời gian chờ, tốc độ xử lý và queue để chống hao tài nguyên.

**Tiêu chuẩn đúng:** Với cùng một chuỗi byte stream, parser xuất cùng các message hoàn chỉnh **bất kể chia thành bao nhiêu lượt read**, và không phát message chưa đầy đủ.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** ByteBuffer sau `flip()` có `position=6` và `limit=9`. Parser đã đọc xong đến index 5, còn 3 byte thuộc frame tiếp theo. Nếu gọi `compact()`, trạng thái mới là gì?  
**Đáp án:** Giữ 3 byte `[6,9)` dồn về đầu, `position=3` và `limit=capacity` (write mode).

**Câu 2.** Vì sao `clear()` dễ làm mất message khi parser chỉ có 2 byte đầu header?  
**Đáp án:** `clear()` reset position về 0 để lần ghi tiếp theo ghi đè phần header dở; cần `compact()` hoặc copy sang accumulator khác.

**Câu 3.** Buffer có header length=5 và payload mới 2 byte. Parser đã gọi `getInt()`. Nếu không `reset()` trước `compact()`, lỗi gì xảy ra?  
**Đáp án:** Header 4 byte bị coi là đã tiêu thụ, còn 2 byte payload thành đầu buffer mới; lần parse sau hiểu sai protocol. Phải giữ cả header+payload dở hoặc chuyển sang state PAYLOAD với length đã lưu.

**Câu 4.** Nếu một lần read mang đủ ba frame, parser dùng `if` chỉ đọc frame đầu có thể hỏng ở đâu?  
**Đáp án:** Hai frame còn lại đã nằm trong ứng dụng nhưng có thể không được xử lý nếu callback kế tiếp không đến; phải dùng vòng parse tới khi chỉ còn frame dở.

**Câu 5.** `read() == 0` trong SocketChannel non-blocking có nghĩa là EOF không?  
**Đáp án:** Không. EOF trả `-1`; `0` nghĩa là lúc đó không thêm byte vào buffer, hoặc không có chỗ nhận. Không xoá trạng thái pending.

**Câu 6.** Tại sao `String.length()` không dùng làm length-prefix UTF-8?  
**Đáp án:** Nó đếm UTF-16 code unit, không đếm số byte UTF-8 trên wire. Phải encode rồi dùng `bytes.length`.

**Câu 7.** Một frame dài 100 byte, buffer capacity 32 byte. Parser phải làm gì?  
**Đáp án:** Nếu length <= giới hạn cho phép, grow bounded hoặc lưu state và thu payload vào buffer riêng; tuyệt đối không spin đọc vào buffer đã đầy hoặc truncate âm thầm.

**Câu 8.** Vì sao trả `ByteBuffer.slice()` sang worker rồi lập tức `compact()`/ghi lại có thể gây lỗi?  
**Đáp án:** Slice chia sẻ vùng nhớ với buffer gốc; worker có thể đọc dữ liệu đã bị ghi đè. Cần copy hoặc ownership/lifetime an toàn.

**Câu 9.** Nếu EOF tới sau khi hai frame hoàn chỉnh đã được dispatch và còn 1 byte đầu header frame thứ ba, có thể báo kết thúc sạch không?  
**Đáp án:** Không. Có 1 byte header dở nên phải báo truncated frame và xử lý kết nối theo protocol.

**Câu 10.** Tại sao parser đúng khi được feed từng byte là thử nghiệm quan trọng?  
**Đáp án:** Nó chứng minh parser không lệ thuộc kích thước chunk và biết giữ state khi header/payload phân mảnh. Đồng thời cần test nhiều frame trong một chunk để chứng minh xử lý được coalescing.

## 20. Tài liệu đối chiếu

- Java SE 17 `ByteBuffer` — `flip()`, `compact()`, `mark()`, `reset()`, byte order và direct buffer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `Buffer` — quy tắc position, limit, capacity, remaining: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
- Java SE 17 `SocketChannel` — `read` có thể trả số byte bất kỳ tới giới hạn, `0` hoặc `-1`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 17 `SelectionKey` — `OP_READ`, attachment theo kết nối: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- Java SE 17 `DataOutputStream` — `writeInt` 4 byte big-endian: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html
- RFC 9293, Transmission Control Protocol — byte stream và ranh giới segment không ánh xạ trực tiếp tới ứng dụng: https://www.rfc-editor.org/rfc/rfc9293
