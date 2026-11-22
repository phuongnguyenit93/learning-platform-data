# Scattering read, gathering write và gom phần đầu với nội dung

## 1. Bài toán: gửi phần đầu (header) và nội dung (payload) trên một channel

Trong Java NIO, một thông điệp TCP thường gồm **header** (chẳng hạn độ dài, loại bản tin) và **payload** (nội dung thực tế). Có hai cách tạo dữ liệu gửi:

- **Gộp vật lý:** cấp phát một `ByteBuffer` lớn, `put` header và payload vào đó rồi gọi `channel.write(buffer)`.
- **Gathering write:** giữ header và payload trong **những `ByteBuffer` riêng**, truyền mảng `ByteBuffer[]` cho `channel.write(...)` để channel tiêu thụ byte của chúng **theo đúng thứ tự**.

Ở chiều nhận, **scattering read** cho phép `channel.read(ByteBuffer[])` phân phối các byte từ channel vào nhiều vùng đích **theo thứ tự**: buffer đầu trước, rồi các buffer tiếp theo. Mỗi `ByteBuffer` có `position` và `limit` riêng.

Ví dụ một frame nhị phân:

```text
Giao thức: [4-byte length L][1-byte type][L-1 byte payload UTF-8]

Ví dụ gửi "HELLO", type=1:
    length = 6    (1 byte type + 5 byte text)
    header = 00 00 00 06
    type   = 01
    text   = 48 45 4C 4C 4F

   ByteBuffer header       ByteBuffer type       ByteBuffer payload
   +------------------+    +--------------+      +--------------------+
   | 00 00 00 06      |    | 01           |      | H E L L O          |
   +--------+---------+    +------+-------+      +--------+-----------+
            |                     |                       |
            +---------------------+-----------------------+
                                  |
                                  v
                channel.write(new ByteBuffer[] {
                    header, typeBuffer, payload
                })
                                  |
                                  v
                 TCP byte stream: 00 00 00 06 01 H E L L O
                                  |
                                  v
                  read header trước để biết L
                                  |
                                  v
                  read(new ByteBuffer[] {
                      typeBuffer, payloadBuffer
                  })
```

**Điểm cần phân biệt:** gathering/scattering là kỹ thuật **I/O vectored** giúp ứng dụng không phải tự ghép/tách mọi byte vào một mảng trung gian. Nó **không** biến TCP thành giao thức có ranh giới thông điệp, không bảo đảm một `write` thành một gói mạng, và không bảo đảm một `read` trả đủ frame.

## 2. Hai giao diện cốt lõi của Java NIO

Các API liên quan:

| API | Ý nghĩa |
| --- | --- |
| `GatheringByteChannel.write(ByteBuffer[] srcs)` | Ghi dữ liệu còn lại trong nhiều buffer nguồn lên channel theo thứ tự trong mảng |
| `GatheringByteChannel.write(ByteBuffer[] srcs, int offset, int length)` | Chỉ xét đoạn **`length` phần tử** trong mảng buffer, bắt đầu tại phần tử `offset` |
| `ScatteringByteChannel.read(ByteBuffer[] dsts)` | Đọc vào nhiều buffer đích theo thứ tự trong mảng |
| `ScatteringByteChannel.read(ByteBuffer[] dsts, int offset, int length)` | Chỉ xét đoạn con của **mảng các buffer**, không phải offset byte của một buffer |
| `SocketChannel` | Channel TCP có thể thực hiện cả scattering read và gathering write |
| `FileChannel` | Channel tệp cũng hỗ trợ kiểu đọc/ghi qua nhiều buffer; không phải kỹ thuật chỉ có ở network |

Với các overload nhận **mảng `ByteBuffer[]`**, số byte đọc/ghi trả về là `long` (khác với overload một `ByteBuffer` thường trả `int`).

**Quy tắc thứ tự:**

- Scattering read: byte được ghi vào buffer thứ nhất **cho tới khi vùng `remaining()` của nó hết**, rồi mới tới buffer thứ hai, v.v. Nếu hoạt động đọc trả sớm, một số buffer phía sau có thể chưa có byte nào.
- Gathering write: byte được lấy từ vùng `remaining()` của buffer thứ nhất, rồi tới các buffer sau. Nếu một lần write chỉ ghi một phần, `position` của các buffer cho thấy phần còn lại.
- Cả hai chỉ xử lý các byte trong phạm vi `position .. limit` của từng buffer; `capacity` không tự quyết định số byte truyền.

Tài liệu API không hứa "đọc hết tất cả buffer trong một lệnh". Nếu cần frame hoàn chỉnh, ứng dụng **phải lặp** và quan sát `hasRemaining()`.

## 3. `ByteBuffer` quyết định byte nào được gửi và còn chỗ nào để nhận

Một `ByteBuffer` có ba mốc quan trọng:

- `capacity`: dung lượng cố định của buffer.
- `position`: chỉ vị trí **đọc/ghi kế tiếp**.
- `limit`: ranh giới vùng có thể dùng trong trạng thái hiện tại; chỉ số từ `limit` trở đi không được truy cập qua thao tác tương đối.

Số byte có thể sử dụng tiếp = **`remaining() = limit - position`**.

### 3.1. Header trước khi gửi

```java
ByteBuffer header = ByteBuffer.allocate(4);
header.putInt(6);   // position: 0 -> 4; limit=4
header.flip();      // position=0, limit=4; sẵn sàng để write
```

`ByteBuffer` mặc định dùng **big-endian**, phù hợp với quy ước network byte order trong frame này. Có thể ghi rõ `header.order(ByteOrder.BIG_ENDIAN)` để làm đặc tả tường minh. Nếu hai đầu không thống nhất thứ tự byte, độ dài header có thể bị đọc thành số rất lớn.

### 3.2. Payload trước khi gửi

```java
byte[] encoded = "HELLO".getBytes(StandardCharsets.UTF_8);
ByteBuffer payload = ByteBuffer.wrap(encoded);
// position=0, limit=5, remaining=5
```

`ByteBuffer.wrap(...)` không sao chép mảng `encoded`: buffer dùng chung storage với mảng đó. Không được sửa mảng hoặc tái sử dụng buffer quá sớm trong khi một lần ghi chưa tiêu thụ hết dữ liệu.

### 3.3. Buffer bên nhận

```java
ByteBuffer typeBuffer = ByteBuffer.allocate(1);
ByteBuffer bodyBuffer = ByteBuffer.allocate(5);
// Cả hai ở chế độ ghi: position=0, limit=capacity.

// Sau khi channel đọc đủ:
typeBuffer.flip();
bodyBuffer.flip();
// Cả hai chuyển sang chế độ đọc dữ liệu vừa nhận.
```

Đặt `flip()` **sau khi đã ghi/nhận xong** để đọc. Nếu quên `flip()` header sau `putInt`, `remaining()==0` và gathering write có thể không gửi bốn byte header. Nếu gọi `flip()` quá sớm khi server chưa nhận đủ, phần còn lại của frame có thể bị đọc/giải mã sai.

## 4. Chương trình hoàn chỉnh Java 17+: TCP loopback, header và payload riêng

Chương trình này tạo TCP server/client trên loopback trong một JVM. Protocol quy định:

- Bốn byte đầu là số nguyên signed 32-bit **big-endian** `L`, biểu thị **tổng số byte phía sau header**, gồm một byte `type` và byte UTF-8 của `text`.
- `1 <= L <= 1024`; frame có một byte loại message.
- Client gửi `type=1`, text `HELLO`. Server phản hồi `type=2`, text `OK`.
- Khi **gửi**, mỗi phía dùng **một gathering write với mảng gồm header, type, payload** (lặp khi chưa ghi hết).
- Khi **nhận**, mỗi phía đọc **4-byte header trước**, kiểm tra độ dài, rồi dùng **scattering read vào hai buffer type và payload** đã được cấp phát đúng kích thước. Không đoán độ dài payload trước khi đọc header.
- Code dùng **blocking `SocketChannel`**; nếu có lỗi hoặc EOF giữa frame, hàm nhận báo lỗi chứ không coi đó là frame hợp lệ.

**Tệp `ScatterGatherFrameDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.GatheringByteChannel;
import java.nio.channels.ScatteringByteChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ScatterGatherFrameDemo {
    private static final int MAX_FRAME_BYTES = 1024;

    record Frame(int type, String text) {}

    private static boolean hasRemaining(ByteBuffer[] buffers) {
        for (ByteBuffer b : buffers) {
            if (b.hasRemaining()) return true;
        }
        return false;
    }

    private static void writeFully(GatheringByteChannel channel,
            ByteBuffer... buffers) throws IOException {
        while (hasRemaining(buffers)) {
            long written = channel.write(buffers);
            if (written <= 0) {
                throw new IOException("No write progress on blocking channel");
            }
        }
    }

    private static void readFully(ScatteringByteChannel channel,
            ByteBuffer... buffers) throws IOException {
        while (hasRemaining(buffers)) {
            long count = channel.read(buffers);
            if (count == -1) {
                throw new EOFException("Peer closed during a frame");
            }
            if (count == 0) {
                throw new IOException("No read progress on blocking channel");
            }
        }
    }

    private static void sendFrame(GatheringByteChannel channel,
            int type, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (type < 0 || type > 255 ||
                bytes.length + 1 > MAX_FRAME_BYTES) {
            throw new IllegalArgumentException("Invalid outgoing frame");
        }
        ByteBuffer header = ByteBuffer.allocate(4);
        header.putInt(1 + bytes.length);
        header.flip();
        ByteBuffer typePart = ByteBuffer.wrap(new byte[] {(byte) type});
        ByteBuffer payload = ByteBuffer.wrap(bytes);
        writeFully(channel, header, typePart, payload);
    }

    private static Frame receiveFrame(ScatteringByteChannel channel)
            throws IOException {
        ByteBuffer header = ByteBuffer.allocate(4);
        readFully(channel, header);
        header.flip();
        int bytesAfterHeader = header.getInt();
        if (bytesAfterHeader < 1 || bytesAfterHeader > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length");
        }

        ByteBuffer typePart = ByteBuffer.allocate(1);
        ByteBuffer payload = ByteBuffer.allocate(bytesAfterHeader - 1);
        readFully(channel, typePart, payload);
        typePart.flip();
        payload.flip();
        return new Frame(Byte.toUnsignedInt(typePart.get()),
                StandardCharsets.UTF_8.decode(payload).toString());
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Frame> server = executor.submit(() -> {
                    try (SocketChannel peer = listener.accept()) {
                        Frame request = receiveFrame(peer);
                        sendFrame(peer, 2, "OK");
                        return request;
                    }
                });

                try (SocketChannel client =
                             SocketChannel.open(listener.getLocalAddress())) {
                    sendFrame(client, 1, "HELLO");
                    Frame reply = receiveFrame(client);
                    Frame request = server.get(5, TimeUnit.SECONDS);
                    System.out.println("server: type=" + request.type()
                            + ", text=" + request.text());
                    System.out.println("client: type=" + reply.type()
                            + ", text=" + reply.text());
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

Lệnh chạy (Java 17+):

```bash
javac --release 17 ScatterGatherFrameDemo.java
java ScatterGatherFrameDemo
```

Stdout trong lần chạy thành công:

```text
server: type=1, text=HELLO
client: type=2, text=OK
```

**Giải nghĩa kết quả:** server nhận đúng frame `type=1`, payload `HELLO`; client nhận frame phản hồi `type=2`, payload `OK`. Đây là bản tin ở **tầng ứng dụng**, không phải dấu hiệu một lời gọi gathering write tự tạo một TCP packet hoặc TCP ACK.

Code được viết cho **blocking channel** và demo nhỏ trên loopback. Nó ném `IOException` khi một thao tác không tiến triển (trả 0) để tránh chạy vòng vô hạn trong ngữ cảnh này; **không bê nguyên nhánh này sang non-blocking mode** vì 0 là kết quả bình thường của một thao tác I/O chưa sẵn sàng. Demo cũng chưa đặt deadline cho mọi thao tác socket; production cần chính sách timeout, hủy yêu cầu và xử lý lỗi phù hợp.

## 5. Gộp header với body theo nghĩa logic, không copy sang buffer lớn

Với giao thức trong ví dụ, khi gửi text `HELLO`:

```java
// Mảnh code (header/type/body được tạo như hàm sendFrame).
ByteBuffer[] parts = { header, typePart, payload };
long written = channel.write(parts);
```

Các buffer riêng có thể mang dữ liệu từ những nguồn khác nhau:

- Header có thể do `ByteBuffer.allocate(4)` tạo trong hàm encode.
- Type có thể là buffer 1 byte hoặc là một phần của header cố định.
- Payload có thể là `ByteBuffer.wrap(bytes)` từ byte array, `slice()` từ vùng backing khác, hoặc direct buffer.
- Mảng `parts` chỉ chứa **tham chiếu các buffer** và thứ tự; nó không nối các mảng byte lại thành một mảng mới.

Trong cấu trúc header/body đơn giản hơn (không có `type`), có thể ghi:

```java
ByteBuffer header = ByteBuffer.allocate(4);
header.putInt(payload.remaining()); // độ dài số BYTE còn lại
header.flip();

ByteBuffer[] parts = { header, payload };
while (header.hasRemaining() || payload.hasRemaining()) {
    long n = channel.write(parts);
    if (n <= 0) {
        throw new IOException("No write progress on blocking channel");
    }
}
```

*Đây là mảnh code bên trong hàm có `channel`, `payload` và xử lý `IOException`, với channel ở **blocking mode**.* Nếu `payload` đã bị đọc/ghi làm `position` thay đổi, `payload.remaining()` chỉ là số byte **chưa được sử dụng** từ vị trí hiện hành. Khi tính kích thước frame, phải bảo đảm đang chỉ đúng vùng muốn gửi.

**Gathering không đồng nghĩa "zero-copy từ ứng dụng đến card mạng".** Nó giúp tránh bước copy **thủ công để ghép header/body trong JVM**, còn JVM, hệ điều hành và TCP có thể sao chép hoặc xử lý buffer theo cách triển khai. Cũng không có lời hứa tạo **chính xác một** system call hoặc một TCP segment cho mọi mảng `ByteBuffer[]`.

## 6. Scattering read: đọc vào nhiều buffer theo đúng thứ tự

Trong code demo, receiver phải biết kích thước body **sau khi đọc header**:

```text
Bước A:
  channel.read([header: capacity 4])
  lặp đến khi header đủ 4 byte
  header.flip()
  L = header.getInt()
  kiểm tra 1 <= L <= 1024

Bước B:
  typePart = ByteBuffer.allocate(1)
  payload  = ByteBuffer.allocate(L - 1)
  channel.read([typePart, payload])
  lặp đến khi cả hai buffer đã đủ byte
  typePart.flip(), payload.flip()
  decode frame
```

Nếu client gửi 3 byte header rồi chậm lại, một lần `channel.read(header)` có thể trả 3 và `header.hasRemaining()` vẫn là `true`. Nếu phần còn lại không bao giờ tới, read có thể tiếp tục chờ trong blocking mode, hoặc báo EOF/lỗi nếu kết nối đóng/hỏng.

**Sai lầm nguy hiểm:** cấp trước `ByteBuffer payload = ByteBuffer.allocate(MAX_BODY)`, gọi `read(new ByteBuffer[]{header, payload})` rồi mới xem `L`. Trên kết nối TCP giữ lâu, nếu payload thật ngắn hơn `MAX_BODY`, phần dư của buffer có thể **nuốt byte thuộc frame tiếp theo**. Khi đó decoder nhầm ranh giới hai message.

Có thể scattering read header và body trong cùng một lần **khi kích thước các phần đã biết trước**, ví dụ một bản ghi cố định 4-byte header + 32-byte body. Nhưng với **độ dài động do header quy định**, thông thường cần **đọc header trước, validate, rồi mới cấp các buffer body phù hợp**. Đó vẫn là ứng dụng thực sự của scattering read cho các phần body/type sau header.

Một trường hợp cụ thể khác: protocol quy định frame cố định `[4 byte sequence][8 byte data]`. Có thể tạo:

```java
ByteBuffer sequence = ByteBuffer.allocate(4);
ByteBuffer data = ByteBuffer.allocate(8);
ByteBuffer[] dsts = { sequence, data };

while (sequence.hasRemaining() || data.hasRemaining()) {
    long n = channel.read(dsts);
    if (n < 0) throw new EOFException("Incomplete fixed record");
    if (n == 0) throw new IOException(
            "No read progress on blocking channel");
}
sequence.flip();
data.flip();
```

*Đây là mảnh code cho blocking `ScatteringByteChannel` có trong biến `channel`; payload cố định 8 byte là ràng buộc **đã thỏa thuận từ đầu**, không phải buffer lớn tùy tiện.* Cần có `import java.io.EOFException;`, `IOException` và `ByteBuffer`.

## 7. Một `write(ByteBuffer[])` có thể ghi chưa hết

Đối với gathering write, giá trị trả về là **tổng byte thực sự đã được ghi trong lời gọi đó**, không phải tổng `capacity` hay `remaining()` ban đầu. Nếu channel chỉ nhận được một phần, các buffer đã được cập nhật `position` tương ứng. Ví dụ:

```text
Trước lần write:
  header: 4 byte remaining
  payload: 10 byte remaining

Giả sử write(...) trả 6:
  header: 0 byte remaining    (4 byte đã ghi)
  payload: 8 byte remaining   (2 byte đã ghi)

Lần write tiếp theo phải tiếp tục đúng từ position hiện tại.
Không reset header/payload về position 0.
```

Ví dụ trên chỉ là **minh họa phép tính**: không có cam kết write sẽ luôn trả 6. Thực tế phụ thuộc channel, trạng thái socket, OS, tải và blocking/non-blocking mode.

Chú ý các nguyên tắc:

1. Dùng `while (hasRemaining(buffers))` để lặp cho tới khi tất cả source buffers đã hết, nếu protocol cần gửi đủ frame.
2. Không gọi `clear()` hay `rewind()` giữa các lần write còn dang dở; làm vậy có thể **gửi lại header hoặc body từ đầu**.
3. Không tạo lại header bằng cách `putInt(...)` liên tục cho mỗi lần ghi khi đang gửi dở; tạo frame **một lần** rồi giữ trạng thái.
4. Không coi `write(...)` trả về dương nghĩa là peer application đã xử lý dữ liệu; nó phản ánh việc ghi xuống tầng channel của tiến trình hiện tại.
5. Khi channel dùng **non-blocking mode**, 0 là bình thường khi chưa ghi thêm được; không busy-loop vô hạn mà dùng `Selector`/`OP_WRITE` và lưu nguyên các buffer chưa ghi xong.
6. Không ghi nhiều frame vào cùng channel từ nhiều thread mà không serialize việc ghi: header của frame A có thể xen với payload frame B nếu các writer tự chia lượt ghi.

Khi ghi nhiều frame nối tiếp trên TCP, receiver phải đọc theo framing riêng từng frame, ngay cả khi một gathering write đã "gom" phần header với body ở phía gửi.

## 8. Một `read(ByteBuffer[])` cũng có thể chỉ nhận một phần

Return value của scattering read được diễn giải như sau:

| Kết quả | Ý nghĩa |
| --- | --- |
| `n > 0` | Đã đặt `n` byte vào một hoặc nhiều đích; vẫn cần kiểm tra buffer nào chưa đầy |
| `n == 0` | Không có byte mới trong lời gọi này; thường gặp ở non-blocking mode hoặc khi không còn vùng để nhận |
| `n == -1` | Đã chạm **end-of-stream** của channel đọc; nếu một frame đang dang dở, đó là **frame bị thiếu** |
| Ngoại lệ `IOException` | Có lỗi I/O; có thể đã nhận một phần frame trước khi lỗi được báo |

Với blocking `SocketChannel` và có ít nhất một buffer còn `remaining()>0`, `read` thông thường đợi cho tới khi có dữ liệu, EOF hoặc lỗi; không được giả định một lần đọc hoàn thành toàn bộ header + body. Loop trong chương trình demo kiểm tra các buffer và ném `EOFException` nếu peer đóng trước khi frame hoàn tất.

**TCP là byte stream:** một `write(new ByteBuffer[]{header,body})` bên gửi có thể được phía nhận thấy qua nhiều lần `read`, hoặc nhiều frame có thể nằm nối tiếp trong cùng luồng. Gathering write **không tạo datagram** và scattering read **không tự phân định frame**.

Ngược lại, trên một channel tệp như `FileChannel`, kết quả đọc/ghi một phần cũng phải được xử lý qua `position/remaining`; ý nghĩa EOF là cuối tệp, không phải peer TCP đã đóng.

## 9. Với non-blocking `SocketChannel` cần state machine và `Selector`

Helpers `readFully`/`writeFully` của demo chỉ dành cho **blocking channel**: chúng lặp trực tiếp cho tới khi buffer hoàn thành và coi `n==0` là không tiến triển. Trong non-blocking mode, **không được đợi kiểu đó**, bởi:

- `read(ByteBuffer[])` có thể trả `0` khi chưa có dữ liệu.
- `write(ByteBuffer[])` có thể trả `0` khi socket send buffer chưa nhận thêm.
- Nếu cứ gọi liên tục khi trả 0, thread có thể dùng CPU vô ích (busy spin).

Một state machine nhận frame động nên có các trạng thái:

```text
READ_LENGTH (4 byte)
       |
       | đủ 4 byte; flip + getInt(); validate 1..MAX
       v
READ_TYPE_AND_BODY (1 byte + L-1 byte)
       |
       | cả type và body đều đủ; flip + decode
       v
FRAME_COMPLETE
       |
       +----> xử lý; tạo response; trở lại READ_LENGTH
```

Ở nhánh ghi:

```text
ENQUEUE_FRAME
    |
    | tạo header + type + payload, giữ ByteBuffer positions
    v
WRITE_PENDING
    |
    | channel.write(parts), có thể partial hoặc trả 0
    | còn remaining -> giữ buffers cho lần OP_WRITE tiếp theo
    | hết remaining -> bỏ yêu cầu OP_WRITE nếu queue trống
    v
FRAME_QUEUED_TO_CHANNEL
```

Hãy đăng ký `OP_READ` để tiếp tục nhận khi channel readable; chỉ quan tâm `OP_WRITE` khi **thật sự có dữ liệu chờ ghi**, để tránh vòng lặp selector báo writable liên tục khi socket vốn đã sẵn sàng. Trên một kết nối có nhiều request, cần queue frame gửi và cơ chế backpressure, không cấp vô hạn buffer.

Lưu ý về `ByteBuffer.compact()`: dùng khi muốn giữ các byte **chưa xử lý** trong một buffer, dồn chúng về đầu rồi đọc thêm. Nếu đang dùng **các buffer cố định cho từng phần frame** theo state machine, có thể tiếp tục trực tiếp với `position` của từng buffer mà không cần compact. `clear()` và `flip()` không xóa dữ liệu vật lý; chúng chỉ thay vị trí và giới hạn.

## 10. `offset/length` của mảng buffer và số byte truyền

Có overload:

```java
long n = channel.write(parts, startIndex, count);
long m = channel.read(destinations, startIndex, count);
```

*Đây là những mảnh code trong các phương thức có `channel`, `parts`, `destinations`, `startIndex`, `count` cùng interface tương ứng.* Hai tham số `startIndex` và `count` chọn **bao nhiêu phần tử ByteBuffer trong mảng**; không phải offset và độ dài của vùng byte bên trong mỗi buffer.

Ví dụ mảng có ba phần tử:

```text
parts[0] = header
parts[1] = type
parts[2] = payload

channel.write(parts, 1, 2)
  -> chỉ ghi type rồi payload
  -> bỏ qua header
```

Khi cần "bỏ header đã gửi" trong lần gửi tiếp theo, đa phần cứ truyền **cả mảng**: vì `header.remaining()==0`, channel sẽ tự đi tới buffer kế. Không cần tính thủ công chỉ số phần tử sau mỗi partial write trừ khi tối ưu có chủ đích.

Nếu slice từ một buffer lớn, quan tâm thêm `ByteBuffer.slice()`: slice có `position=0`, `limit=remaining` tại thời điểm tạo, nhưng **chia sẻ vùng dữ liệu** với buffer gốc; di chuyển vị trí của slice không đồng nghĩa di chuyển vị trí buffer gốc. `duplicate()` cũng tạo đối tượng có position/limit riêng nhưng dùng chung nội dung. Khi dùng pooled/direct buffer, phải quản lý vòng đời và không tái sử dụng backing memory trước khi I/O hoàn tất.

## 11. Header định nghĩa độ dài theo **byte**, không phải số ký tự

Đối với UTF-8, số byte có thể khác số lượng ký tự:

```java
byte[] payload = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
int byteCount = payload.length;  // dùng byteCount để viết header
```

Không dùng `text.length()` để tính số byte UTF-8, vì `String.length()` đếm UTF-16 code units chứ không phải byte UTF-8. Nếu sender viết header bằng số ký tự nhưng receiver cấp phát/đọc theo byte, frame dễ bị thiếu dữ liệu, làm lệch ranh giới các message kế tiếp.

Trong ví dụ hoàn chỉnh, giá trị `L` gồm **1 byte type + số byte payload UTF-8**, không gồm bốn byte header. Receiver đọc đúng số byte được công bố sau khi kiểm tra `L`. Hai đầu phải dùng cùng quy ước này; không được một đầu tính độ dài body không gồm type còn đầu kia hiểu bao gồm type.

Với thông điệp không đáng tin, nên thêm:

- Giới hạn độ dài trước khi `ByteBuffer.allocate(L - 1)`; tránh cấp phát vô hạn, số âm và frame quá lớn.
- Kiểm tra `type` thuộc danh sách cho phép. `Byte.toUnsignedInt(typePart.get())` cho giá trị 0..255; không nhầm kiểu `byte` signed với loại message 128..255.
- Kiểm tra UTF-8 hợp lệ, ví dụ decoder với `CodingErrorAction.REPORT` nếu protocol không chấp nhận byte hỏng; `StandardCharsets.UTF_8.decode(...)` theo cấu hình mặc định có thể dùng ký tự thay thế.
- Giới hạn số frame/connection, timeout, tốc độ gửi, số pending response và tổng bộ nhớ.
- Với request có side effect, dùng ID để ghép response đúng request và thiết kế retry/idempotency phù hợp. Một `write` thành công không bảo đảm server đã xử lý.

## 12. Bao giờ nên dùng scattering/gathering thay vì một buffer duy nhất?

| Tình huống | Gợi ý |
| --- | --- |
| Header nhỏ, payload đã là một `ByteBuffer` sẵn có | **Gathering write** giúp gửi cả hai theo thứ tự mà không tự tạo mảng byte mới |
| Protocol có type + metadata + payload trong những vùng khác nhau | Gom nhiều buffer bằng `write(ByteBuffer[])`; hạn chế số buffer và đo hiệu năng |
| Đọc bản ghi có các phần **kích thước cố định đã biết** | **Scattering read** vào nhiều buffer giúp tách vùng nhận |
| Đọc frame có độ dài **động nằm trong header** | Đọc/validate header trước, sau đó scattering read các phần body đã biết kích thước |
| Một payload nhỏ đã có sẵn trong một buffer | `channel.write(singleBuffer)` có thể đơn giản hơn; không ép gathering bằng mọi giá |
| Số lượng buffer rất nhiều, kích thước rất nhỏ | Cân nhắc overhead/giới hạn vectored I/O của nền tảng; benchmark trước khi tối ưu |
| Gửi file ra socket | Xem thêm `FileChannel.transferTo(...)` trong trường hợp phù hợp; đó là API khác, không phải gathering write mặc định |
| Non-blocking server | Giữ trạng thái buffer giữa các sự kiện `Selector` và quản lý backpressure |

Không có lợi ích chung tuyệt đối về tốc độ. Lợi ích tùy kích thước thông điệp, mô hình cấp phát, số buffer, TLS/SSLEngine nếu có, CPU và OS. Đặc biệt khi dùng TLS, các bản ghi mã hóa, header bảo mật và buffer bên trong có thể làm việc truyền dữ liệu thực tế khác với một frame TCP thô. Trước khi đổi kiến trúc vì hiệu suất, hãy đo throughput/latency và số allocation của chính workload.

## 13. Những lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Tạo header bằng `putInt` nhưng không `flip()` | `remaining()==0`, không gửi header | `flip` trước khi đưa vào mảng nguồn |
| Cho rằng một lần `write(ByteBuffer[])` gửi đủ mọi byte | Trên socket có thể ghi một phần | Lặp tới khi mọi source buffer hết `remaining` |
| Lặp write nhưng gọi `rewind()` giữa chừng | Header/body có thể bị gửi lại | Giữ nguyên `position` sau partial write |
| Cho rằng một lần `read(ByteBuffer[])` điền đủ các buffer | Decoder đọc frame chưa hoàn chỉnh | Theo dõi `hasRemaining` và EOF |
| `read` trả `-1` giữa frame nhưng vẫn parse | Frame bị cắt | Báo lỗi/đóng theo protocol |
| Mở buffer body lớn trước khi xem header | Có thể đọc lấn sang frame kế tiếp | Đọc 4-byte header, validate L, rồi mới đọc đúng L byte |
| Dùng `String.length()` làm byte length UTF-8 | Frame lệch độ dài khi có Unicode | Tính trên `getBytes(UTF_8).length` |
| Dùng `capacity` thay vì `remaining` khi gửi | Kích thước thực tế không đúng | Theo dõi `position` và `limit` |
| Quên `flip()` đích sau receive | Parser đọc sai vị trí | `flip` khi phần dữ liệu yêu cầu đã nhận đủ |
| Coi `read/write==0` là EOF trong non-blocking mode | Đóng nhầm connection | 0 nghĩa là chưa tiến triển; đợi Selector |
| Busy-loop khi write non-blocking trả 0 | Tốn CPU | Chờ `OP_WRITE`, giữ buffer ở hàng đợi |
| Nhiều thread cùng ghi header/body trên socket | Byte của nhiều frame bị xen kẽ | Serialize writer/queue và bảo toàn từng frame |
| Coi gathering là một TCP packet/atomic message | Hiểu sai TCP framing | Parser phải dựa vào header length, không dựa ranh giới write |
| Không giới hạn header L từ phía mạng | Cấp phát quá lớn/âm hoặc DoS | Check `1 <= L <= MAX_FRAME_BYTES` trước allocate |
| Nhầm `write(parts, 1, 2)` là offset byte | Bỏ qua sai phần header/type | Hiểu offset/length ở cấp **mảng buffer** |

## 14. Bài tập áp dụng

**Bài 1 — Gửi hai phần không copy:** Có `ByteBuffer header` chứa 4-byte length và `ByteBuffer payload` chứa dữ liệu. Viết vòng lặp gathering write bảo đảm truyền hết hai phần ở blocking mode. Khi nào phải `flip()`?

**Bài 2 — Ghi dở:** Header còn 4 byte, body còn 10 byte. `channel.write(new ByteBuffer[]{header, body})` trả `6`. Giả sử ghi theo thứ tự chuẩn, còn bao nhiêu byte ở mỗi buffer? Lần tiếp nên dùng lại buffer ra sao?

**Bài 3 — Đọc frame động:** Header công bố `L=100` (bao gồm type). Receiver muốn scattering vào `type` và `payload`. Nó cần cấp phát lần lượt bao nhiêu byte? Có nên cấp `payload=ByteBuffer.allocate(1024)` rồi đọc đến đầy không?

**Bài 4 — Đọc hai buffer:** `ByteBuffer a=allocate(4)` và `b=allocate(8)`. Một scattering read trả 5 byte. Trong tình huống các buffer đều trống lúc đầu, `remaining()` của từng buffer sau lần đọc là bao nhiêu?

**Bài 5 — Non-blocking:** Một lần `write(ByteBuffer[])` trả `0`, các buffer vẫn còn data. Nên làm gì thay vì gọi `write` liên tục trong `while(true)`?

**Bài 6 — Sai độ dài:** Client gửi text UTF-8 có ký tự tiếng Việt nhưng header ghi `String.length()`. Hệ quả là gì? Cần thay bằng phép tính nào?

**Đáp án gợi ý:**

1. `header.flip()` sau `putInt`; payload phải ở trạng thái đọc. Gọi `write(new ByteBuffer[]{header,payload})` lặp tới khi cả hai `hasRemaining()==false`, không rewind giữa chừng.
2. Header còn `0`, body còn `8`; tiếp tục ghi cùng các buffer với vị trí hiện tại.
3. Buffer type `1` byte, payload `99` byte; không đọc tùy tiện 1024 vì có thể nuốt frame tiếp theo.
4. `a.remaining()==0`, `b.remaining()==7` (4 byte vào a, 1 byte vào b).
5. Lưu trạng thái các buffer pending, đăng ký `OP_WRITE` và viết tiếp khi writable; giới hạn queue/backpressure.
6. `String.length()` đếm UTF-16 code units, không phải byte UTF-8. Dùng `text.getBytes(StandardCharsets.UTF_8).length` trước khi ghi header.

## Tài liệu tham khảo Java chính thức

- [Java SE 17 — ScatteringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ScatteringByteChannel.html): `read(ByteBuffer[])`, thứ tự buffer, kết quả `long`.
- [Java SE 17 — GatheringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/GatheringByteChannel.html): `write(ByteBuffer[])`, partial progress.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): TCP channel, blocking/non-blocking và các overload read/write.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `slice`, `duplicate`, `order`.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): xử lý readiness cho channel non-blocking.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): scattering/gathering trên channel tệp.
