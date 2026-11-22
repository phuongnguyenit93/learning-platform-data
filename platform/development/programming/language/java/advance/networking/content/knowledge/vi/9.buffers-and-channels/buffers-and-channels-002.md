# Chu kỳ put → flip → write và read → flip → xử lý → compact

## 1. Vì sao phải hiểu hai chu kỳ này?

Trong Java NIO, **ByteBuffer** là vùng nhớ có các chỉ số **position**, **limit** và **capacity**, còn **Channel** thực hiện thao tác I/O với byte trong buffer. Khi dùng **SocketChannel** cho TCP, chương trình:

- Chuẩn bị byte cần gửi bằng put(...), chuyển buffer sang trạng thái lấy byte bằng flip(), rồi cho channel tiêu thụ các byte bằng write(...).
- Nhận byte qua channel.read(buffer), chuyển buffer sang trạng thái xử lý bằng flip(), chỉ giải mã những thông điệp hoàn chỉnh và dùng compact() để bảo toàn phần dở dang.

Hai chu kỳ:

~~~text
GỬI:  put(byte[]) → flip() → channel.write(buffer)
                                 |
                      còn remaining? → giữ buffer, write tiếp
                                 |
                      gửi hết? → clear() để put mẻ mới

NHẬN: channel.read(buffer) → flip() → parse complete frames
                                     |
                             còn byte chưa xử lý
                                     |
                                compact()
                                     |
                         channel.read(buffer) lần sau
~~~

**Quan trọng:** TCP là **luồng byte**, không bảo toàn ranh giới giữa các lần ứng dụng gọi write(). Một lần channel.read(...) có thể lấy được một phần message hoặc nhiều message ghép lại; một lần channel.write(...) cũng có thể chỉ ghi một phần dữ liệu. Vì vậy trạng thái ByteBuffer là nền tảng để không mất những byte còn dang dở.

Tên **write mode** hay **read mode** trong bài này nói về **thao tác trên buffer**. Khi channel.read(buffer), channel đang đọc từ socket nhưng đồng thời **ghi vào buffer**, nên buffer phải ở write mode. Khi channel.write(buffer), channel đang ghi ra socket nhưng **đọc byte từ buffer**, nên buffer phải ở read mode.

## 2. Position, limit và capacity hoạt động thế nào?

Mỗi ByteBuffer luôn có bất biến:

~~~text
0 <= position <= limit <= capacity

remaining()    = limit - position
hasRemaining() = position < limit
~~~

- **capacity:** tổng số byte có thể chứa; không đổi suốt vòng đời của một ByteBuffer.
- **position:** chỉ số của byte sẽ được put/get tiếp theo. Khi put hoặc get tương đối, position tiến lên.
- **limit:** chỉ số exclusive của vùng hiện cho phép put/get.
- **mark:** vị trí ghi nhớ tùy chọn để reset() quay về; nhiều thao tác chuyển trạng thái sẽ hủy mark.

Các phép chuyển đổi quan trọng:

| Phương thức | Position sau gọi | Limit sau gọi | Ý nghĩa |
| --- | --- | --- | --- |
| **put(b)** | Tăng theo số byte vừa put | Giữ nguyên | Đưa byte vào buffer |
| **get(...)** | Tăng theo số byte vừa get | Giữ nguyên | Lấy byte từ buffer |
| **flip()** | 0 | Position cũ | Chuẩn bị đọc những byte đã put/read từ channel vào |
| **clear()** | 0 | Capacity | Chuẩn bị ghi đè/tái sử dụng toàn buffer |
| **rewind()** | 0 | Giữ nguyên limit cũ | Đọc lại vùng dữ liệu hiện hữu |
| **compact()** | Số byte chưa xử lý trước compact | Capacity | Dồn byte từ [position,limit) về đầu rồi chuẩn bị put/read thêm |
| **mark()/reset()** | reset đặt về mark cũ | Không đổi | Quay lại một vị trí trong cùng giai đoạn đọc |

**clear() không xóa dữ liệu vật lý trong RAM.** Nó chỉ thiết lập lại position/limit và hủy mark. Do đó không nên dùng clear() như phương pháp xóa dữ liệu nhạy cảm.

**flip(), clear(), rewind(), compact() đều hủy mark.** Nếu parser đã đặt mark trước header nhưng phát hiện body thiếu, phải reset() **trước khi compact()**, nếu không mark sẽ mất hiệu lực.

Ví dụ với ByteBuffer.allocate(8):

~~~text
Khởi tạo:          [ . . . . . . . . ]  position=0, limit=8, capacity=8
put("HELLO"):      [ H E L L O . . . ]  position=5, limit=8, capacity=8
flip():            [ H E L L O . . . ]  position=0, limit=5, capacity=8
get 2 byte:        [ H E L L O . . . ]  position=2, limit=5, capacity=8
compact():         [ L L O . . . . . ]  position=3, limit=8, capacity=8
~~~

Dòng compact trên chỉ mô tả vùng byte có ý nghĩa; những vị trí được ghi bằng dấu chấm không có cam kết đã bị xóa. Sau compact, ba byte chưa đọc là **LLO** nằm ở [0,3), và byte mới có thể được put từ vị trí 3 trở đi.

## 3. Chu kỳ outbound: put → flip → write

Giả sử gửi chuỗi **HELLO** (5 byte UTF-8 vì toàn ký tự ASCII) qua một WritableByteChannel.

### 3.1. Put vào buffer đang ở write mode

~~~java
ByteBuffer send = ByteBuffer.allocate(8);
send.put("HELLO".getBytes(StandardCharsets.UTF_8));
~~~

Sau put:

~~~text
[H E L L O . . .]
           ^ position=5
limit=8, capacity=8
~~~

Nếu ngay lúc này gọi channel.write(send) thì channel sẽ đọc từ vị trí 5 tới trước limit 8, không phải vùng HELLO đã put. Vì thế phải flip.

### 3.2. Flip để giới hạn đúng vùng đã có dữ liệu

~~~java
send.flip();
~~~

Sau flip: **position=0, limit=5, capacity=8**. Chỉ vùng [0,5) là dữ liệu dành cho channel. flip **không gửi byte qua mạng**, nó chỉ chuyển trạng thái buffer.

### 3.3. Write có thể chỉ tiêu thụ một phần byte

~~~java
// Minh họa cho WritableByteChannel luôn có khả năng tiến triển.
while (send.hasRemaining()) {
    channel.write(send);
}
~~~

Mỗi lần channel.write(send) trả về số byte đã tiêu thụ và tăng position đúng số byte đó. Ví dụ một channel chỉ nhận tối đa hai byte mỗi lần:

| Lượt | Byte channel nhận | Position | Limit | Remaining |
| --- | --- | ---: | ---: | ---: |
| Trước write | Chưa có | 0 | 5 | 5 |
| write #1 | HE | 2 | 5 | 3 |
| write #2 | LL | 4 | 5 | 1 |
| write #3 | O | 5 | 5 | 0 |

Ở cuối, position=limit=5. Khi **hasRemaining()==false**, có thể gọi clear() để tái sử dụng buffer cho lần put mới.

**Lỗi mất dữ liệu:** gọi clear() khi position còn nhỏ hơn limit sẽ bỏ đi dấu vết các byte chưa được channel nhận. Hãy giữ buffer ở read mode cho tới khi channel tiêu thụ hết.

### 3.4. Nếu muốn append thêm byte khi vẫn còn dữ liệu chưa gửi

Có hai chiến lược:

1. **Không append:** giữ nguyên position/limit và write tiếp khi channel sẵn sàng.
2. **Append có kiểm soát:** compact() để dồn byte chưa gửi về đầu, put thêm byte nếu còn capacity, rồi flip() trước khi write.

~~~java
// Minh họa, send đang trong read mode và còn byte chưa gửi.
send.compact();       // Giữ remaining bytes, chuyển về write mode.
send.put(moreBytes);  // Chỉ khi có đủ khoảng trống.
send.flip();          // Chuyển lại read mode để write tiếp.
~~~

compact() **không tự gửi dữ liệu**. Nó di chuyển các byte còn lại để tiếp tục xây outbound buffer. Nếu moreBytes quá lớn, cần queue các buffer khác hoặc backpressure; không ghi vượt dung lượng.

### 3.5. Riêng SocketChannel non-blocking: không quay vòng khi write trả 0

~~~java
// Minh họa trong callback ghi; pending đã flip để gửi.
while (pending.hasRemaining()) {
    int n = socketChannel.write(pending);
    if (n == 0) {
        // Giữ position/limit; bật interest OP_WRITE và rời callback.
        break;
    }
}
if (!pending.hasRemaining()) {
    // Không còn pending output: bỏ interest OP_WRITE
    // nếu không cần gửi thêm buffer nào.
}
~~~

SocketChannel ở chế độ non-blocking có thể trả **0** nếu lúc đó không thể ghi tiếp. Một vòng lặp write liên tục trong trường hợp này sẽ gây **busy-spin** và tăng CPU. Selector.OP_WRITE chỉ nên được theo dõi khi có dữ liệu chờ gửi, và được bỏ sau khi queue rỗng.

**Đừng flip lần thứ hai** một buffer đang ở read mode, position=2, limit=5: flip lần nữa sẽ đặt limit=2 và position=0, làm sai vùng byte còn phải gửi.

## 4. Chu kỳ inbound: read → flip → xử lý → compact

ByteBuffer phía nhận ban đầu ở write mode (position=0, limit=capacity). Channel.read(buffer) sẽ đưa byte mới vào buffer kể từ position và tăng position theo số byte thực sự nhận.

~~~java
ByteBuffer inbound = ByteBuffer.allocate(1024);
int n = socketChannel.read(inbound);
~~~

Khi n dương, chuyển sang read mode:

~~~java
inbound.flip();
parseCompleteFrames(inbound);
inbound.compact();
~~~

Đây là minh họa API; **parseCompleteFrames** là phương thức parser của ứng dụng, không phải API Java có sẵn.

- **flip()** thiết lập limit bằng số byte hiện có, position về 0, để parser không đọc những byte chưa nhận.
- **parseCompleteFrames(...)** chỉ tiêu thụ những frame có đầy đủ header/body, giữ position ở đầu phần chưa thể xử lý.
- **compact()** dồn các byte chưa xử lý về đầu buffer, đặt position sau phần còn lại, limit=capacity để lần read tiếp theo có chỗ đưa byte mới vào.

### 4.1. Vì sao phải compact thay vì clear?

Giả sử protocol có header dài 4 byte, lần read hiện tại mới nhận **2 byte header**.

~~~text
Sau read:  [H0 H1 . . . . . .]  position=2, limit=capacity
flip:      [H0 H1 . . . . . .]  position=0, limit=2
Parser:    remaining=2 < 4 nên chưa thể đọc header.
compact:   [H0 H1 . . . . . .]  position=2, limit=capacity
Read sau:  [H0 H1 H2 H3 B0 B1 ...]  (byte mới nối sau H1)
~~~

Nếu gọi clear() khi chưa xử lý H0/H1, lần read tiếp có thể ghi đè hai byte đó và làm hỏng header. compact() bảo toàn dữ liệu dang dở. Nếu parser đã tiêu thụ toàn bộ byte hợp lệ, compact() để position=0, tương đương vùng ghi mới bắt đầu từ đầu.

### 4.2. Nếu đọc được nhiều frame cùng lúc?

Một lần read có thể đưa nhiều message vào buffer. Parser phải giải mã **liên tục từng frame hoàn chỉnh** cho tới khi không đủ dữ liệu cho frame tiếp theo. Khi ngừng, phần còn lại được giữ bằng compact. Đừng mặc định “một read tương ứng một message TCP”.

### 4.3. Nếu header đủ nhưng payload chưa đủ?

Nếu parser tiêu thụ header trước rồi phát hiện body thiếu, cần **quay lại đầu header** trước khi compact (nếu không lưu trạng thái header riêng).

~~~java
// Minh họa parser, buffer đã flip() và ở read mode.
while (true) {
    if (buffer.remaining() < Integer.BYTES) {
        break; // Thiếu header.
    }

    buffer.mark();                 // Ghi nhớ đầu header.
    int size = buffer.getInt();    // Đọc 4 byte, position tăng 4.
    if (size < 0 || size > MAX_FRAME_BYTES) {
        throw new IOException("Invalid frame length");
    }

    if (buffer.remaining() < size) {
        buffer.reset(); // Giữ lại header lẫn body dang dở.
        break;
    }

    byte[] body = new byte[size];
    buffer.get(body);
    processFrame(body); // Chỉ xử lý thông điệp hoàn chỉnh.
}
buffer.compact();
~~~

Đây là snippet có các định danh **buffer**, **MAX_FRAME_BYTES**, **processFrame(...)** thuộc code ứng dụng; nó chưa phải một file có thể chạy riêng. Ví dụ đầy đủ ở phần tiếp theo có khai báo tất cả thành phần.

**Giới hạn thiết kế:** parser giữ trọn frame trong ByteBuffer phải có capacity **ít nhất 4 + MAX_FRAME_BYTES**. Nếu frame lớn hơn capacity, buffer có thể đầy mà parser chưa thể tiêu thụ được gì; cần từ chối frame hoặc thiết kế state machine đọc body theo từng phần. Với mạng không tin cậy, luôn giới hạn length trước khi cấp phát.

## 5. Ví dụ protocol để hiểu chính xác vị trí byte

Giả sử hai thông điệp được gửi theo định dạng **4-byte length (big-endian) + payload UTF-8**:

~~~text
Frame A, nội dung "A":
  00 00 00 01 41                       = 4-byte header + 1 byte body = 5 byte

Frame B, nội dung "WORLD":
  00 00 00 05 57 4F 52 4C 44           = 4-byte header + 5 byte body = 9 byte

Hai frame nối tiếp nhau: 5 + 9 = 14 byte.
~~~

**ByteBuffer mặc định byte order BIG_ENDIAN**, nên putInt() và getInt() ở hai phía tương thích nếu không đổi thứ tự byte. Trên hệ thống thật phải thống nhất byte order và kiểu length trong protocol; length ở đây là **số byte body**, không phải số ký tự Java String.

Nhận 14 byte bằng ByteBuffer capacity=12 **hoàn toàn khả thi** vì parser tiêu thụ từng frame 5 hoặc 9 byte rồi compact. Không cần đủ chỗ cho cả hai message cùng một lúc. Điều kiện là **mỗi frame hoàn chỉnh** phải vừa trong buffer của mô hình này.

Một kế hoạch kiểm tra dễ tái hiện là tạo một ReadableByteChannel giả lập trả tối đa **3 byte một lần**: parser phải bảo toàn phần header/body thiếu cho tới lúc đủ frame. Một WritableByteChannel giả lập trả tối đa **2 byte một lần** sẽ giúp kiểm chứng outbound.

## 6. Ví dụ Java 17+ độc lập, kiểm tra được kết quả

Chương trình sau kiểm tra cả hai chu kỳ mà không phụ thuộc thời điểm gói TCP đến. **LimitedWriter** tiêu thụ tối đa 2 byte/lần; **LimitedReader** trả tối đa 3 byte/lần. Đây là **channel mô phỏng**, không có socket TCP hay phỏng đoán segmentation thật.

**Tệp BufferCycleDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class BufferCycleDemo {
    static class LimitedWriter implements WritableByteChannel {
        private final ByteArrayOutputStream bytes =
                new ByteArrayOutputStream();
        private boolean open = true;
        int calls;

        @Override
        public int write(ByteBuffer src) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            int n = Math.min(2, src.remaining());
            byte[] part = new byte[n];
            src.get(part);
            bytes.write(part);
            calls++;
            return n;
        }

        String text() {
            return bytes.toString(StandardCharsets.UTF_8);
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }
    }

    static class LimitedReader implements ReadableByteChannel {
        final byte[] wire;
        private int offset;
        private boolean open = true;
        int calls;

        LimitedReader(byte[] wire) {
            this.wire = wire;
        }

        @Override
        public int read(ByteBuffer dst) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            if (offset == wire.length) {
                return -1;
            }

            int n = Math.min(
                    3, Math.min(dst.remaining(), wire.length - offset));
            dst.put(wire, offset, n);
            offset += n;
            if (n > 0) {
                calls++;
            }
            return n;
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }
    }

    static byte[] frame(String text) {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + body.length)
                         .putInt(body.length)
                         .put(body).array();
    }

    public static void main(String[] args) throws Exception {
        // Outbound: put -> flip -> write -> clear.
        ByteBuffer send = ByteBuffer.allocate(8);
        send.put("HELLO".getBytes(StandardCharsets.UTF_8));
        send.flip();

        LimitedWriter writer = new LimitedWriter();
        while (send.hasRemaining()) {
            writer.write(send);
        }
        System.out.println("Sent: " + writer.text());
        System.out.println("Write calls: " + writer.calls);

        send.clear();
        System.out.println("Ready for next put: " +
                (send.position() == 0 && send.limit() == 8));
        writer.close();

        // Inbound: hai frame, tổng cộng 14 byte.
        byte[] first = frame("A");
        byte[] second = frame("WORLD");
        byte[] wire = new byte[first.length + second.length];
        System.arraycopy(first, 0, wire, 0, first.length);
        System.arraycopy(second, 0, wire, first.length, second.length);

        LimitedReader reader = new LimitedReader(wire);
        ByteBuffer receive = ByteBuffer.allocate(12);
        List<String> messages = new ArrayList<>();
        int incomplete = 0;
        int n;

        // read -> flip -> parse -> compact.
        while ((n = reader.read(receive)) != -1) {
            if (n == 0) {
                throw new IllegalStateException("Receive buffer full");
            }

            receive.flip();
            while (true) {
                if (receive.remaining() < 4) {
                    if (receive.hasRemaining()) {
                        incomplete++;
                    }
                    break;
                }

                receive.mark();
                int length = receive.getInt();
                if (length < 0 || length > 8) {
                    throw new IOException("Invalid message length");
                }
                if (receive.remaining() < length) {
                    receive.reset();
                    incomplete++;
                    break;
                }

                byte[] body = new byte[length];
                receive.get(body);
                messages.add(
                        new String(body, StandardCharsets.UTF_8));
            }
            receive.compact();
        }

        if (receive.position() != 0) {
            throw new IOException("Truncated message at EOF");
        }
        reader.close();

        System.out.println("Read calls: " + reader.calls);
        System.out.println("Incomplete-frame waits: " + incomplete);
        System.out.println(
                "Decoded messages: " + String.join("|", messages));
        System.out.println(
                "Pending bytes after compact: " + receive.position());
    }
}
~~~

### Cách biên dịch và chạy

Lưu file đúng tên **BufferCycleDemo.java**, dùng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 BufferCycleDemo.java
java BufferCycleDemo
~~~

**Stdout chính xác của chương trình khi thành công:**

~~~text
Sent: HELLO
Write calls: 3
Ready for next put: true
Read calls: 5
Incomplete-frame waits: 4
Decoded messages: A|WORLD
Pending bytes after compact: 0
~~~

Logic chương trình đã được chạy kiểm tra trong Java runtime. Các con số là kết quả **do channel mô phỏng giới hạn n=2/n=3**, không phải hành vi cố định của SocketChannel TCP thật.

### Vì sao ghi HELLO cần đúng ba lần write?

HELLO dài 5 byte. LimitedWriter chỉ nhận tối đa 2 byte/lần: lần 1 nhận HE, lần 2 nhận LL, lần 3 nhận O. **ByteBuffer.position** tăng theo số byte thực nhận, nên không có byte bị gửi hai lần hay bỏ sót. Sau khi gửi hết, clear() đặt position=0, limit=8, in **Ready for next put: true**.

### Vì sao nhận hai frame cần năm lượt read?

Cả hai frame dài 14 byte. LimitedReader đưa tối đa ba byte/lần: bốn lượt đầu đưa 12 byte, lượt cuối đưa 2 byte. Parser phải giữ những phần header/body chưa đủ và chỉ consume frame hoàn chỉnh.

| Lượt read | Byte mới | Byte đang có sau read | Xử lý | Position sau compact |
| --- | ---: | ---: | --- | ---: |
| 1 | 3 | 3 | Thiếu header 4 byte | 3 |
| 2 | 3 | 6 | Giải mã frame "A" (5 byte), giữ 1 byte đầu frame B | 1 |
| 3 | 3 | 4 | Đủ header B nhưng chưa có body; reset về đầu header | 4 |
| 4 | 3 | 7 | Header B + 3/5 byte body; reset giữ đủ 7 byte | 7 |
| 5 | 2 | 9 | Đủ frame "WORLD" (9 byte); giải mã | 0 |

Các lượt 1–4 đều kết thúc ở một **frame chưa hoàn chỉnh**, vì vậy in **Incomplete-frame waits: 4**. Sau lượt 5, hai frame được giải mã thành **A|WORLD** và buffer không còn byte dang dở.

**Một chi tiết về frame(...):** Hàm helper cấp đúng 4+N byte heap buffer, điền header/body rồi truy cập backing array. Vì helper lấy mảng byte trực tiếp và không gọi channel.write trên ByteBuffer đó, nó không cần flip trước khi đọc mảng. Khi gửi ByteBuffer qua Channel, vẫn phải tuân thủ put → flip → write.

## 7. Đưa mô hình vào SocketChannel thật

### Phía gửi

Một SocketChannel non-blocking phải giữ outbound buffer qua nhiều callback nếu còn byte chưa gửi.

~~~java
// Đoạn minh họa trong handler OP_WRITE: pending đã flip.
while (pending.hasRemaining()) {
    int written = socketChannel.write(pending);
    if (written == 0) {
        // Không thể viết tiếp ngay: giữ pending, đợi OP_WRITE.
        break;
    }
}
if (!pending.hasRemaining()) {
    // Bỏ OP_WRITE nếu toàn bộ output queue đã trống.
}
~~~

Không clear buffer khi còn remaining. Không flip lần nữa một buffer đã đọc/sent được một phần. Nếu có nhiều message chờ gửi, cần queue hoặc quản lý buffer cụ thể, giữ thứ tự và giới hạn lượng dữ liệu backlog. Peer đọc chậm sẽ cần **backpressure**, không nên tích lũy vô hạn byte trong RAM.

### Phía nhận

~~~java
// Đoạn minh họa: inbound duy trì write mode giữa các callback.
int count = socketChannel.read(inbound);
if (count > 0) {
    inbound.flip();
    parseCompleteFrames(inbound);
    inbound.compact();
} else if (count == 0) {
    // Non-blocking: chưa có byte mới; đợi sự kiện OP_READ.
} else {
    // count == -1: EOF; kiểm tra có frame dở dang không.
    // Sau đó kết thúc/đóng connection theo giao thức.
}
~~~

**Đây là snippet, không phải file Java độc lập**: biến socketChannel, inbound, phương thức parseCompleteFrames(...) và cơ chế selector phải được khai báo trong server. Việc giữ ByteBuffer ở **write mode sau compact()** là điều kiện để lần đọc tiếp theo nối dữ liệu mới vào phần trống.

Chú ý: nếu parser không thể xử lý byte nào vì frame dài hơn capacity, compact sẽ để buffer không còn remaining; lần read tiếp theo không thể tiến triển. Hãy giới hạn frame, chọn buffer đủ lớn hoặc thiết kế streaming parser. Với EOF, nếu buffer còn dữ liệu chưa thành frame hoàn chỉnh, đó là **truncated frame**, không được tự bỏ qua.

## 8. Những tình huống biên và lỗi phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Put xong quên flip trước write | Channel có thể lấy vùng byte chưa chuẩn bị | flip đúng lúc chuyển sang lấy byte |
| Channel.read xong quên flip | Parser thấy position/limit không đúng vùng byte đã nhận | flip trước parse |
| Write trả ít hơn remaining rồi clear | Bỏ byte chưa gửi | Giữ read mode, chờ ghi tiếp |
| Read mới có nửa header/body rồi clear | Mất byte của frame | compact để giữ byte dở dang |
| GetInt header, body thiếu, compact không reset | Bỏ mất header | mark/reset hoặc parser state độc lập |
| Read 0 coi là EOF | Đóng kết nối non-blocking quá sớm | 0 khác -1; đợi OP_READ |
| Write 0 rồi chạy while vô hạn | CPU cao, không làm peer nhận nhanh hơn | Dừng vòng lặp, chờ OP_WRITE |
| Bật OP_WRITE mãi khi không có dữ liệu chờ | Selector thức liên tục | Chỉ quan tâm OP_WRITE khi pending output |
| Gọi flip hai lần liên tiếp | flip thứ hai có thể đặt limit=0 | Chỉ flip khi chuyển write mode → read mode |
| Dùng rewind thay clear để ghi dữ liệu mới | Limit không thành capacity, dễ overflow | clear khi không cần giữ byte |
| Giả định clear xóa sạch RAM | Byte cũ vẫn có thể ở backing storage | Dùng biện pháp xóa dữ liệu phù hợp nếu yêu cầu bảo mật |
| Tách một ký tự UTF-8 ra hai read rồi decode riêng | Ký tự Unicode có thể bị lỗi | Ghép byte theo frame rồi decode hoặc CharsetDecoder stateful |
| Nhận length tùy ý từ mạng rồi cấp phát | Có thể cạn RAM | Kiểm tra length/giới hạn payload |
| Dùng .array() trên direct buffer | Có thể ném UnsupportedOperationException | Dùng get/put hoặc channel API |
| Dùng chung mutable ByteBuffer giữa nhiều thread | Race ở position/limit và dữ liệu | Định rõ ownership hoặc đồng bộ hóa |

### read(...) trả -1 và timeout

- **-1** là EOF của channel, không phải thông điệp ứng dụng tự động hoàn chỉnh.
- **0** trong non-blocking mode thường biểu thị chưa có byte mới; không có nghĩa peer đã đóng.
- **Read timeout** hoặc deadline của ứng dụng là cơ chế riêng; không dùng thời gian ngừng nhận byte làm delimiter đáng tin.
- Khi peer đóng giữa header/body, báo **truncated frame** hoặc lỗi giao thức; đừng xử lý payload nửa chừng như hoàn chỉnh.

### Heap buffer, direct buffer và nhiều connection

- **ByteBuffer.allocate(...)** cấp heap buffer.
- **ByteBuffer.allocateDirect(...)** cấp direct buffer, không mặc định có accessible backing array; chọn theo nhu cầu I/O và chi phí cấp phát.
- **slice()/duplicate()** có chỉ số position/limit độc lập nhưng có thể chia sẻ vùng byte nền; đừng sửa payload trong khi channel khác đang gửi cùng vùng.
- **ByteBuffer không thread-safe**. Mỗi connection nên có inbound/outbound state riêng hoặc cơ chế đồng bộ hóa và sở hữu rõ ràng.

## 9. Các bài toán tự kiểm tra

**1.** Buffer capacity=12, sau put 5 byte thì position/limit bằng bao nhiêu? Sau flip?  
**Trả lời:** Sau put: position=5, limit=12. Sau flip: position=0, limit=5.

**2.** Buffer gửi có position=2, limit=9; channel.write trả 3. Còn bao nhiêu byte?  
**Trả lời:** Position trở thành 5, remaining=9-5=4 byte. Không clear trước khi gửi 4 byte đó.

**3.** Buffer nhận ở read mode có position=3, limit=8; compact sẽ làm gì?  
**Trả lời:** Dồn 5 byte chưa đọc [3,8) về [0,5), position=5, limit=capacity, rồi có thể nhận thêm byte.

**4.** Vì sao channel.read dùng buffer đang ở write mode?  
**Trả lời:** Channel đọc từ nguồn nhưng **ghi byte vào buffer**; position chỉ nơi đặt byte tiếp theo.

**5.** Header có 4 byte và body mới đến 2/10 byte, nên xử lý request không?  
**Trả lời:** Chưa. Giữ header/body, nhận thêm tới khi đủ length; không xóa byte dở dang.

**6.** Vì sao compact mà không reset sau khi getInt có thể gây lỗi?  
**Trả lời:** Position đã vượt qua header; compact chỉ giữ byte từ position trở đi, khiến header bị mất nếu parser chưa lưu length vào state riêng.

**7.** Hai frame dài tổng cộng 14 byte, buffer capacity=12 có thể xử lý không?  
**Trả lời:** Có, khi từng frame tối đa 12 byte và parser xử lý frame hoàn chỉnh rồi compact. Ví dụ A (5 byte) và WORLD (9 byte) cho kết quả đúng.

**8.** Sau clear, byte cũ có biến mất khỏi RAM không?  
**Trả lời:** Không, clear chỉ reset position/limit/mark.

**9.** Tại sao SocketChannel non-blocking write có thể cần nhiều callback?  
**Trả lời:** Socket có thể chỉ nhận một phần byte, thậm chí trả 0; phải giữ buffer và chờ khả năng ghi thêm.

**10.** Khi nào nên dùng compact thay clear?  
**Trả lời:** Khi còn byte **chưa gửi** hoặc **chưa xử lý** cần giữ lại để nối với dữ liệu mới. Nếu đã xử lý/gửi hết và muốn bắt đầu mẻ mới, clear đơn giản hơn.

## 10. Checklist triển khai Java NIO

1. Xác định rõ lúc nào buffer ở write mode và read mode; không trộn hai ý nghĩa.
2. Gửi: put → flip → write tới khi không còn remaining; với non-blocking phải chờ OP_WRITE thay vì spin.
3. Nhận: read → flip → parse hoàn chỉnh → compact, giữ dữ liệu dang dở.
4. Parser phải có quy ước framing, kiểm tra length/UTF-8, EOF và giới hạn kích thước.
5. Không giả định một read = một message hay một write được tiêu thụ hết.
6. Nếu buffer đầy mà vẫn không đủ frame, reject hoặc chuyển sang state machine/streaming.
7. Quản lý interest OP_WRITE đúng lúc và backpressure cho output queue.
8. Tránh dùng chung ByteBuffer giữa nhiều thread hoặc connection mà không rõ ownership.
9. Test các trường hợp header/body phân mảnh, nhiều frame liền nhau, partial writes, read/write trả 0 và EOF giữa frame.
10. Luôn quan sát position, limit, remaining khi debug thay vì chỉ in dung lượng buffer.

## Kết luận

**put → flip → write** chuyển byte từ giai đoạn **đưa dữ liệu vào ByteBuffer** sang giai đoạn **channel tiêu thụ byte**. **read → flip → xử lý → compact** chuyển byte từ giai đoạn **channel nhận dữ liệu** sang giai đoạn **parser đọc thông điệp hoàn chỉnh**, đồng thời giữ byte còn dang dở cho lần tiếp theo.

Nắm vững **position/limit/capacity**, flip đúng lúc, compact khi cần bảo toàn byte và xử lý partial read/write là nền tảng để viết Java NIO networking ổn định.

### Tài liệu tham khảo

- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer và put/get, heap/direct, byte order.
- [Java SE 17 — Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): position, limit, capacity, flip, clear, compact/rewind, mark/reset.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): đọc/ghi và non-blocking.
- [Java SE 17 — WritableByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritableByteChannel.html): write(ByteBuffer).
- [Java SE 17 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): read(ByteBuffer).
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): OP_READ và OP_WRITE.
