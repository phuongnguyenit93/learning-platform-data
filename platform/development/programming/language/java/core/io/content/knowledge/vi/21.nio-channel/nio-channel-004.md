# Đọc hoặc ghi không đủ toàn bộ buffer trong Java NIO Channel

## 1. Vấn đề: một lần read/write không đồng nghĩa hoàn tất

Các API channel của Java NIO truyền byte qua `ByteBuffer`. Một lời gọi `read(buffer)` hoặc `write(buffer)` có thể xử lý **ít byte hơn số byte còn lại trong buffer**, ngay cả khi không có lỗi. Hiện tượng này thường được gọi là **partial read** hoặc **partial write** (đọc/ghi một phần).

Ví dụ: buffer có 8 byte cần gửi nhưng `channel.write(buffer)` chỉ chấp nhận 3 byte trong lần gọi đầu. Phương thức trả về `3`, còn 5 byte chưa gửi. Nếu bỏ buffer đi hoặc gọi `clear()` ngay, ứng dụng sẽ mất dữ liệu.

~~~text
ByteBuffer trước lần write:
       position=0                    limit=8
            v                            v
         [ A B C D E F G H ]   remaining=8

channel.write(buffer) trả 3:
               position=3             limit=8
                    v                    v
         [ A B C D E F G H ]   remaining=5
           đã gửi ^ ^ ^
                 Các byte D..H vẫn đang chờ gửi.
~~~

Điểm cốt lõi là: **giá trị trả về** cho biết số byte thực sự chuyển trong lần gọi; **`position`** của buffer tiến tương ứng. Chương trình cần tiếp tục từ vị trí còn lại cho đến khi đạt điều kiện hoàn tất hoặc sự kiện cần xử lý như EOF, tạm thời chưa sẵn sàng, timeout, hủy thao tác hay lỗi I/O.

Chủ đề này nằm trong nhóm **NIO Channel**, không giới hạn ở đọc tệp: quan trọng nhất với `SocketChannel` ở chế độ không chặn, nhưng cũng phải tôn trọng hợp đồng API khi làm việc với `FileChannel`, `ReadableByteChannel`, `WritableByteChannel` và các channel tùy biến.

## 2. Hợp đồng read và write

### 2.1. Đọc từ ReadableByteChannel vào ByteBuffer

Với `int n = channel.read(dst)`:

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `n > 0` | Chính xác `n` byte đã được chép vào `dst`; `position` tăng `n`. | Xử lý lượng đã nhận; đọc tiếp nếu còn thiếu thông điệp. |
| `n == 0` | Không byte nào được chuyển trong lượt gọi này. | Không suy ra EOF; với non-blocking channel, đợi tín hiệu sẵn sàng hoặc có cơ chế lập lịch lại. |
| `n == -1` | Channel báo **end-of-stream (EOF)**: không còn byte tiếp theo. | Nếu đang yêu cầu một thông điệp cố định chưa đủ byte, báo thiếu/truncated; nếu là luồng đọc đến EOF, kết thúc đúng lúc. |
| Ném `IOException` | Có lỗi I/O. | Xử lý/đóng tài nguyên theo hợp đồng ứng dụng. |

`read(dst)` có thể đọc tối đa `dst.remaining()` byte. Với `dst.remaining() == 0`, lời gọi không có chỗ để nhận byte và không nên dùng nó để dò trạng thái dữ liệu. Khi buffer có chỗ, vẫn **không có bảo đảm** lần đọc sẽ điền hết chỗ trống.

Với `SocketChannel` ở **blocking mode**, nếu còn chỗ trong buffer, phương thức thường chờ cho đến khi đọc được ít nhất một byte, gặp EOF hoặc lỗi, nhưng không có nghĩa chờ đủ toàn bộ buffer. Ở **non-blocking mode**, `read` có thể trả `0` khi socket hiện chưa có dữ liệu.

### 2.2. Ghi từ ByteBuffer ra WritableByteChannel

Với `int n = channel.write(src)`:

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `n > 0` | Chính xác `n` byte đã được tiêu thụ từ `src`; `position` tăng `n`. | Nếu `src.hasRemaining()`, tiếp tục gửi. |
| `n == 0` | Lần này chưa ghi được byte nào. | Nếu non-blocking, đợi channel sẵn sàng ghi; tránh vòng lặp chạy liên tục không tiến triển. |
| Ném `IOException` | Lỗi truyền hoặc ghi dữ liệu. | Chọn retry có kiểm soát, xử lý thất bại hay đóng kết nối theo nghiệp vụ. |

**Không có giá trị `-1` thông thường cho `write` để biểu thị EOF.** Cách dùng `-1` là đặc trưng của các thao tác đọc. Ngay cả `write` trả số dương, điều đó có nghĩa byte đã được channel tiếp nhận theo hợp đồng của nó; không tự suy ra dữ liệu đã được lưu bền vững trên đĩa hoặc peer từ xa đã nhận/xử lý toàn bộ thông điệp.

Ví dụ, `WritableByteChannel.write` cũng được phép ghi ít hơn `src.remaining()` byte. Ở socket, lượng byte đi được còn phụ thuộc trạng thái bộ đệm mạng. Ở tệp, số byte ghi có thể thay đổi theo provider, môi trường hoặc lỗi I/O. **Không viết mã giả định mọi channel.write luôn ghi hết.**

## 3. ByteBuffer liên kết với tiến độ I/O như thế nào?

Các thao tác tương đối trên buffer dựa vào ba giá trị:

~~~text
0 <= position <= limit <= capacity
remaining() == limit - position
hasRemaining() == (remaining() > 0)
~~~

- Với `read(dst)`, channel **đưa dữ liệu vào buffer** ở vị trí hiện tại rồi tăng `position` theo số byte nhận.
- Với `write(src)`, channel **lấy dữ liệu từ buffer** bắt đầu ở vị trí hiện tại rồi tăng `position` theo số byte đã lấy.
- `limit` là ranh giới exclusive; `capacity` là sức chứa vật lý/logic của buffer. Một channel không tự hiểu đâu là số byte “hợp lệ” do ứng dụng vừa ghi trừ khi ứng dụng đặt trạng thái đúng.

Quy trình thường gặp:

~~~text
Đọc từ channel vào buffer:
  clear hoặc compact  -> read(...) -> flip() -> xử lý -> clear/compact

Ghi dữ liệu đã có ra channel:
  put(...) -> flip() -> write(...) -> nếu remaining > 0 thì giữ để ghi tiếp
~~~

**`flip()`** chuyển buffer từ trạng thái vừa được ghi vào sang trạng thái đọc: đặt `limit` bằng `position` cũ, sau đó đặt `position=0`. **`clear()`** đặt `position=0, limit=capacity` để chuẩn bị ghi đè dữ liệu mới; nó không xóa byte thật. **`compact()`** đưa phần byte chưa đọc về đầu rồi chuẩn bị cho lần ghi tiếp, nên hữu ích khi thông điệp chưa đủ hoặc ghi socket mới tiêu thụ một phần.

Không dùng `flip()` lặp đi lặp lại trên buffer **đang chờ write nốt**: sau partial write, buffer đã ở trạng thái đọc và `position` trỏ đúng byte tiếp theo. Nếu gọi `flip()` thêm lần nữa, vùng đọc bị thay đổi, dễ khiến dữ liệu bị lặp hoặc mất.

## 4. Đọc đầy đủ một lượng byte cố định

Giả sử giao thức quy định mỗi header dài chính xác 4 byte. **Một lần `read(header)` là chưa đủ**, vì có thể chỉ nhận được 1, 2 hoặc 3 byte. Với channel blocking mà ứng dụng kỳ vọng mỗi lần đọc có thể tiến triển, ta có thể lặp theo `hasRemaining()`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ReadableByteChannel;

static void readFullyBlocking(ReadableByteChannel channel, ByteBuffer dst)
        throws IOException {
    while (dst.hasRemaining()) {
        int count = channel.read(dst);

        if (count == -1) {
            throw new EOFException("Đã hết luồng trước khi nhận đủ byte");
        }
        if (count == 0) {
            throw new IOException("Không có tiến triển; kiểm tra mode/channel");
        }
    }
}
~~~

Đây là **một phương thức tiện ích**, không phải chương trình Java chạy độc lập. Phương thức được viết cho những trường hợp **blocking có kỳ vọng tiến triển**, không dùng nguyên xi làm vòng lặp non-blocking hoặc cho các provider có thể trả `0` hợp lệ nhiều lần.

Ví dụ sử dụng khi `channel` và byte order đã được xác định:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
readFullyBlocking(channel, header);

header.flip();
int payloadLength = header.getInt();
~~~

Nếu `readFullyBlocking` không báo lỗi, `header` đã chứa đủ 4 byte. Lệnh `flip` đặt limit đúng vùng nhận trước khi `getInt`. Số `payloadLength` chỉ là một số đọc từ dữ liệu: **cần xác thực nó** (không âm, không vượt kích thước tối đa, không gây tràn hoặc cấp phát quá lớn) trước khi dùng làm kích thước buffer tiếp theo.

### 4.1. Đọc đúng N byte khác với đọc cho đến EOF

Có hai mục tiêu khác nhau:

- **Đọc đúng N byte:** kết thúc khi đã nhận N byte; gặp `-1` trước đó là thông điệp bị thiếu.
- **Đọc cả luồng cho đến EOF:** nhận từng chunk tùy ý; `-1` có thể là kết thúc hoàn toàn hợp lệ.

Nếu đọc tệp chỉ để tính tổng số byte hoặc lưu vào một đích, không cần biết trước kích thước, dùng buffer theo từng chunk đến khi EOF. Nếu dữ liệu có framing (length-prefixed, delimiter, fixed-size record), phải thực hiện thêm bước ghép/giải mã khung; ranh giới giữa các lời gọi `read` **không** phải ranh giới thông điệp.

### 4.2. Đọc file theo từng buffer

Một dạng vòng lặp có thể dùng với `FileChannel`:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);

    while (true) {
        int n = channel.read(buffer);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            continue; // Phù hợp với ngữ cảnh file blocking ví dụ này.
        }

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte b = buffer.get();
            // Xử lý byte b, ví dụ cập nhật checksum.
        }
        buffer.clear();
    }
}
~~~

Đây là **mảnh minh họa**, cần `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Path`, `java.nio.file.StandardOpenOption` và xử lý `IOException`. Cách này giả định xử lý hết mọi byte của buffer ở mỗi vòng; khi cần giữ một phần frame đang dang dở, phải dùng `compact()` hoặc bộ tích lũy dữ liệu phù hợp.

Vòng `continue` khi `n==0` được nêu trong ngữ cảnh ví dụ **FileChannel kiểu blocking**; không sao chép vào non-blocking `SocketChannel` vì có thể gây busy-spin.

## 5. Ghi hết dữ liệu trong buffer

Với một channel **blocking** dự kiến ghi tiến triển, mẫu căn bản là:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.WritableByteChannel;

static void writeFullyBlocking(WritableByteChannel channel, ByteBuffer src)
        throws IOException {
    while (src.hasRemaining()) {
        int count = channel.write(src);

        if (count == 0) {
            throw new IOException("Không có tiến triển; kiểm tra mode/channel");
        }
    }
}
~~~

Giả sử trước khi gọi đã đặt buffer vào trạng thái đọc (ví dụ `flip()` sau `put`):

~~~java
ByteBuffer outgoing = ByteBuffer.wrap(
        "PING".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
writeFullyBlocking(channel, outgoing);
~~~

**Vì sao không gọi `clear` giữa các lần write?** Sau lần ghi thứ nhất, `src.position()` đã tự tăng đúng số byte được channel tiêu thụ. `src.hasRemaining()` cho biết còn gì phải gửi; lặp `write(src)` sẽ tiếp tục đúng từ phần chưa hoàn tất.

Nếu ứng dụng muốn sử dụng lại một buffer sau khi ghi **hết**, khi đó mới `clear()` để thêm dữ liệu mới. Nếu socket chỉ nhận được một phần và ứng dụng cần nối dữ liệu bổ sung ở cuối, `compact()` có thể giữ phần chưa gửi và chuyển sang trạng thái ghi để append tiếp; cần kiểm soát thứ tự byte khi làm việc này.

### 5.1. FileChannel và file output

`FileChannel.write(buffer)` cập nhật position của buffer theo số byte ghi. Mẫu lặp `while (buffer.hasRemaining())` vẫn là cách diễn đạt đúng khi cần chuyển **toàn bộ vùng dữ liệu còn lại** sang tệp.

Chú ý có sự khác nhau giữa:

1. Dữ liệu đã được `write` chấp nhận qua API.
2. Dữ liệu đã được hệ điều hành đưa xuống phương tiện lưu trữ.

Nếu có yêu cầu durability, hãy xem hợp đồng `FileChannel.force(boolean metaData)`. Lệnh này liên quan đến đồng bộ dữ liệu, **không** thay thế vòng lặp xử lý partial write, và không nên giả định mọi provider/phần cứng đều có cùng bảo đảm.

## 6. Non-blocking SocketChannel: 0 có thể là trạng thái bình thường

Khi `SocketChannel.configureBlocking(false)`, lời gọi `read` hoặc `write` có thể trả `0` dù kết nối chưa đóng và buffer vẫn còn chỗ/dữ liệu. Lý do thường là socket **chưa sẵn sàng ngay lúc đó**. Một vòng lặp liên tục gọi lại mà không chờ sẽ tốn CPU:

~~~java
// Không nên làm với non-blocking channel.
while (out.hasRemaining()) {
    socket.write(out); // Có thể liên tục trả 0 -> busy-spin.
}
~~~

Với NIO selector, cách tiếp cận là **giữ trạng thái buffer và đợi sự kiện phù hợp**:

- Khi có `OP_READ`, đọc những gì sẵn có, xử lý số byte trả về; nếu `read == 0` thì dừng lượt xử lý read hiện tại.
- Khi có dữ liệu đang chờ ghi, đăng ký `OP_WRITE`, thử ghi những byte còn lại. Nếu `write == 0`, giữ `position/limit` và đợi lượt `OP_WRITE` tiếp theo.
- Khi buffer ghi đã hết `remaining()`, bỏ quan tâm `OP_WRITE` cho đến khi lại có dữ liệu chờ; nếu giữ `OP_WRITE` liên tục, socket thường xuyên sẵn sàng ghi có thể khiến event loop thức dậy không cần thiết.
- Khi `read == -1`, peer đã báo kết thúc hướng đọc; xử lý phần dữ liệu còn tồn và trạng thái đóng kết nối theo giao thức (đối với TCP, cũng có khái niệm half-close).

Pseudocode ngắn minh họa xử lý một lần socket sẵn sàng ghi:

~~~java
// out đã ở trạng thái đọc, chứa dữ liệu cần gửi.
// key, socket là các biến thuộc event loop của ứng dụng.
if (key.isWritable()) {
    socket.write(out); // Có thể gửi 0, một phần hoặc toàn bộ.
    if (!out.hasRemaining()) {
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
        out.clear(); // Chỉ tái sử dụng khi không còn byte chờ gửi.
    }
}
~~~

Đây là **pseudocode tích hợp vào event loop**, không phải chương trình chạy độc lập; cần quản lý buffer hàng đợi, khóa/chủ sở hữu và hủy đăng ký phù hợp. Trong ứng dụng có nhiều thông điệp xếp hàng, thường phải lưu **một hoặc nhiều buffer chưa gửi hết** thay vì chỉ một buffer chung.

**Readiness không bảo đảm số byte:** tín hiệu `OP_READ` không có nghĩa có đủ cả frame; `OP_WRITE` không có nghĩa gửi được hết mọi byte. Selector chỉ thông báo điều kiện có thể thử thao tác, số byte thực chuyển vẫn đến từ `read`/`write`.

## 7. Ví dụ chạy được trên Java 17+: cố ý giới hạn mỗi lần read và write

Để kiểm chứng partial I/O chắc chắn, ví dụ này **không dựa vào may rủi của ổ đĩa hoặc mạng**. Nó cài hai channel nhỏ dựa trên các interface chuẩn:

- `ChunkedReadableChannel` cố ý cấp **tối đa 2 byte** cho mỗi lần `read`.
- `ChunkedWritableChannel` cố ý nhận **tối đa 3 byte** cho mỗi lần `write`.

Dữ liệu nguồn là chuỗi ASCII `HELLO-NIO`, có 9 byte. Do đó cần đúng **5 lần đọc có dữ liệu** (2+2+2+2+1) và **3 lần ghi** (3+3+3).

Lưu file `PartialChannelDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;

public class PartialChannelDemo {

    static final class ChunkedReadableChannel implements ReadableByteChannel {
        private final ByteBuffer source;
        private boolean open = true;
        private int calls;

        ChunkedReadableChannel(byte[] bytes) {
            this.source = ByteBuffer.wrap(bytes);
        }

        @Override
        public int read(ByteBuffer dst) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            if (!dst.hasRemaining()) {
                return 0;
            }
            if (!source.hasRemaining()) {
                return -1;
            }

            int n = Math.min(2, Math.min(dst.remaining(), source.remaining()));
            for (int i = 0; i < n; i++) {
                dst.put(source.get());
            }
            calls++;
            return n;
        }

        int calls() {
            return calls;
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

    static final class ChunkedWritableChannel implements WritableByteChannel {
        private final ByteArrayOutputStream output = new ByteArrayOutputStream();
        private boolean open = true;
        private int calls;

        @Override
        public int write(ByteBuffer src) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            if (!src.hasRemaining()) {
                return 0;
            }

            int n = Math.min(3, src.remaining());
            byte[] batch = new byte[n];
            src.get(batch);
            output.write(batch);
            calls++;
            return n;
        }

        int calls() {
            return calls;
        }

        String text() {
            return output.toString(StandardCharsets.UTF_8);
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

    public static void main(String[] args) throws IOException {
        byte[] payload = "HELLO-NIO".getBytes(StandardCharsets.US_ASCII);
        ByteBuffer buffer = ByteBuffer.allocate(payload.length);

        try (ChunkedReadableChannel reader = new ChunkedReadableChannel(payload);
             ChunkedWritableChannel writer = new ChunkedWritableChannel()) {

            // Đọc đủ 9 byte: mỗi read chỉ trả tối đa 2 byte.
            while (buffer.hasRemaining()) {
                int n = reader.read(buffer);
                if (n == -1) {
                    throw new EOFException("Payload bị thiếu");
                }
                if (n == 0) {
                    throw new IOException("Read không tiến triển");
                }
            }

            System.out.println("readCalls=" + reader.calls());
            System.out.println("readPosition=" + buffer.position());

            buffer.flip();
            System.out.println("writeRemainingBefore=" + buffer.remaining());

            // Ghi đủ 9 byte: mỗi write chỉ nhận tối đa 3 byte.
            while (buffer.hasRemaining()) {
                int n = writer.write(buffer);
                if (n == 0) {
                    throw new IOException("Write không tiến triển");
                }
            }

            System.out.println("writeCalls=" + writer.calls());
            System.out.println("writeRemainingAfter=" + buffer.remaining());
            System.out.println("output=" + writer.text());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PartialChannelDemo.java
java PartialChannelDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
readCalls=5
readPosition=9
writeRemainingBefore=9
writeCalls=3
writeRemainingAfter=0
output=HELLO-NIO
~~~

Giải thích kết quả:

1. Buffer ban đầu có `capacity=9`, `position=0` và `limit=9`.
2. Reader chỉ giao 2 byte mỗi lượt (lượt cuối 1 byte), nên cần đúng 5 lượt để `position=9`.
3. `flip()` chuyển buffer sang chế độ đọc: `position=0`, `limit=9`, `remaining=9`.
4. Writer tiêu thụ 3 byte mỗi lượt; sau 3 lần ghi, `position=9` và `remaining=0`.
5. `output=HELLO-NIO` chứng minh không mất, không lặp byte mặc dù mỗi lần I/O đều chỉ chuyển một phần payload.

Hai channel tùy biến chỉ dùng để **minh họa hợp đồng một cách tái lập được**. Chúng luôn tiến triển khi còn dữ liệu và không mô phỏng mạng non-blocking, selector, timeout hay lỗi từ xa. Các nhánh kiểm tra `n==0` cố ý coi đó là bất thường trong ví dụ blocking mang tính kiểm chứng này.

## 8. Khi frame chưa đủ: giữ byte đang dang dở

Dữ liệu mạng là một **dòng byte**, nên một thông điệp có thể được chia ra nhiều lần `read`; ngược lại một lần `read` có thể nhận nhiều thông điệp liên tiếp. Nếu protocol dùng **frame có độ dài cố định**, bộ giải mã cần giữ số byte còn thiếu đến lượt tiếp theo.

Ví dụ frame bắt đầu bằng 4 byte length big-endian rồi đến `length` byte payload:

~~~text
Trên wire:
[ 00 00 00 05 ][ H E L L O ]
   length=5       payload

Lượt read #1: [ 00 00 00 ]                -> header chưa đủ
Lượt read #2: [ 05 H E ]                   -> đủ header, payload chưa đủ
Lượt read #3: [ L L O ]                    -> hoàn tất payload
~~~

Nếu parser bỏ qua ba byte header nhận ở lượt đầu hoặc decode payload ngay khi chưa đủ, kết quả sẽ sai. Có hai chiến lược điển hình:

1. **State machine + buffer đọc:** giữ trạng thái “đang đọc header” hoặc “đang đọc payload”, chỉ chuyển trạng thái khi phần tương ứng đã đầy đủ. Với blocking channel có thể dùng `readFullyBlocking`; với non-blocking channel giữ trạng thái giữa các sự kiện sẵn sàng đọc.
2. **Một buffer tích lũy và `compact()`:** sau `flip()`, parser tiêu thụ những frame hoàn chỉnh, để lại phần cuối chưa đủ byte; `compact()` giữ chúng lại để lượt `read` tiếp theo ghi nối vào.

Phác thảo vòng lặp non-blocking cho hướng đọc:

~~~java
int n = socket.read(input);  // input đang ở chế độ ghi.
if (n == -1) {
    handleEndOfStream();    // Phân biệt EOF sạch và frame bị cắt.
} else if (n > 0) {
    input.flip();
    parseAllCompleteFrames(input); // Chỉ lấy frame hoàn chỉnh.
    input.compact();               // Giữ phần byte còn lại.
}
~~~

Các hàm `handleEndOfStream` và `parseAllCompleteFrames` là **hàm ứng dụng tự xây dựng**, không phải API Java; đoạn mã cũng phải xử lý buffer đầy mà không giải mã được frame nào (ví dụ yêu cầu cấp buffer lớn hơn trong giới hạn cho phép hoặc từ chối frame quá lớn).

### Lỗi nguy hiểm: cấp phát theo length không kiểm tra

Khi nhận length từ mạng, phải kiểm tra hợp lệ trước khi cấp phát hoặc định vị buffer. Bốn byte length có thể biểu diễn số âm hoặc số quá lớn theo giải mã `getInt()`. Hạn chế kích thước frame, quản lý backpressure, timeout và số kết nối đang giữ buffer là một phần của thiết kế I/O đúng đắn.

## 9. Scattering/Gathering và các API khác vẫn có partial I/O

Một số channel cung cấp thao tác đọc/ghi nhiều buffer:

~~~java
long n = scatteringChannel.read(new ByteBuffer[] {header, body});
long m = gatheringChannel.write(new ByteBuffer[] {prefix, payload});
~~~

Đây là **đoạn minh họa**: `scatteringChannel` thuộc loại hỗ trợ `ScatteringByteChannel`, `gatheringChannel` hỗ trợ `GatheringByteChannel`, và các buffer đã được chuẩn bị trạng thái đúng. `n` và `m` là **tổng số byte được chuyển**, không phải số buffer đã xử lý. Channel có thể chỉ điền một phần trong buffer đầu tiên hoặc chỉ ghi một phần payload; vẫn cần kiểm tra `position/remaining` của từng buffer.

Tương tự, các API như `FileChannel.transferTo(...)` và `transferFrom(...)` trả về **số byte thực chuyển**; không giả định một lần gọi sẽ chuyển hết `count` yêu cầu. Với `AsynchronousByteChannel`, giá trị kết quả hoàn tất của `Future` hoặc `CompletionHandler` cũng cần được diễn giải theo số byte, không tự suy ra rằng đã xong toàn bộ thông điệp.

Một thông điệp gửi thành công qua I/O có thể đòi hỏi *application-level acknowledgment* nếu ứng dụng cần chứng minh peer đã nhận và xử lý, vượt ngoài ý nghĩa của `write()`.

## 10. Phân biệt các điều kiện kết thúc

Để điều khiển vòng lặp an toàn, trước tiên phải xác định **điều kiện hoàn tất thực sự**.

| Mục tiêu | Điều kiện thành công | Điều kiện cần xử lý |
| --- | --- | --- |
| Đọc chính xác `N` byte | `dst` chứa đủ `N` byte; `remaining()==0`. | `read==-1` trước khi đủ ⇒ EOF/truncated. |
| Đọc tất cả byte đến EOF | Đã xử lý các chunk nhận được; sau đó `read==-1`. | `read==0` không phải EOF. |
| Ghi hết một `ByteBuffer` | `src.hasRemaining()==false`. | `write==0` cần cơ chế chờ/tiếp tục phù hợp mode. |
| Ghi frame gồm nhiều buffer | Mọi buffer đã hết `remaining()`, đúng thứ tự. | Partial write ở một buffer bất kỳ. |
| Non-blocking socket | Hoàn tất theo trạng thái ứng dụng và event loop. | `0`/readiness, backpressure, timeout, đóng kết nối. |

Trong production, đừng để yêu cầu “đọc cho đủ” vô thời hạn trên dữ liệu không tin cậy. Cần giới hạn kích thước, deadline hoặc timeout theo giao thức; việc dùng `SocketChannel` và `Selector` không tự cung cấp mọi chính sách timeout/cancel ở cấp ứng dụng.

## 11. Các lỗi thường gặp và cách sửa

### Quên lặp sau write

~~~java
out.flip();
socket.write(out);  // Có thể chỉ ghi một phần.
out.clear();         // SAI nếu vẫn còn byte chưa gửi!
~~~

Cách đúng với blocking channel có khả năng tiến triển là gửi tiếp tới khi `!out.hasRemaining()`. Với non-blocking socket, giữ `out` trong hàng đợi ghi và đăng ký `OP_WRITE` để gửi phần còn lại khi sẵn sàng.

### Dùng `remaining()` trước và sau không đúng thời điểm

Nếu buffer vừa được channel **đọc vào** và position đang nằm cuối dữ liệu, `remaining()` lúc đó chỉ cho biết **sức chứa còn trống để ghi thêm**, không phải số byte dữ liệu mới đọc. Sau `flip()`, `remaining()` mới biểu thị số byte trong vùng đã nhận đang sẵn sàng để ứng dụng đọc ra.

### Dùng `clear()` trên buffer còn dữ liệu

`clear()` thay đổi trạng thái logic, có thể khiến dữ liệu chưa tiêu thụ bị ghi đè trong lượt đọc tiếp. Nếu chỉ một phần frame đã được parser xử lý, dùng `compact()` để giữ phần còn lại.

### Gọi `flip()` hai lần trong chuỗi gửi

Gọi `flip()` giữa hai lần `write` sau partial write khiến `limit` đổi thành vị trí sau lần gửi đầu và `position` về 0, nên có nguy cơ gửi lại phần đã gửi. Sau partial write, giữ nguyên trạng thái buffer và viết tiếp.

### Lầm `0` là kết thúc stream

Một non-blocking socket trả `0` thường chỉ có nghĩa *lúc này chưa tiến triển*, không phải ngắt kết nối. Điều kiện EOF của `read` là `-1`. Ngược lại, vòng lặp liên tục gọi lại khi trả `0` có thể chiếm CPU vô ích.

### Giả định một TCP read là một thông điệp

TCP không giữ ranh giới của mỗi `write` phía người gửi. Một thông điệp có thể đến nhiều mảnh; nhiều thông điệp cũng có thể gộp trong cùng lần `read`. Cần giao thức framing (độ dài, delimiter, cấu trúc cố định...) và parser xử lý dữ liệu còn dang dở.

### Bỏ qua character encoding

Một ký tự UTF-8 có thể gồm nhiều byte và bị chia giữa hai lần đọc. Không gọi `new String(chunk, UTF_8)` riêng cho mỗi chunk tùy ý nếu mục tiêu là xử lý **một stream văn bản liên tục**: ký tự ở ranh giới chunk có thể bị giải mã sai. Dùng `CharsetDecoder` theo trạng thái với buffer byte còn dư, hoặc tích lũy đủ một đơn vị văn bản/frame trước khi decode.

### Nhầm tiến độ channel với thành công nghiệp vụ

`write` trả số dương chỉ báo lượng byte được channel chấp nhận; khi giao tiếp mạng, đó không phải ACK ở tầng ứng dụng. Nếu yêu cầu “đơn hàng đã được xử lý” hoặc “thông điệp đã lưu bền vững”, cần xác nhận riêng ở đúng tầng.

## 12. Thực hành kiểm tra

1. Buffer có `position=3` và `limit=12`. `remaining()` bằng bao nhiêu? **9 byte** nếu đó là `ByteBuffer`. Một lần `write` có thể nhận ít hơn 9 byte.
2. `write(buffer)` trả `4` khi trước đó `position=3`. Position mới là bao nhiêu? **7**, nếu không có thao tác buffer khác xen vào.
3. Non-blocking `read(buffer)` trả `0`. Có kết luận peer đã đóng kết nối được không? **Không.** Cần đợi readiness hoặc điều kiện tiếp theo; `-1` mới báo EOF.
4. Đang đọc header 4 byte, lần đầu chỉ đọc được 2 byte. Làm gì? **Giữ 2 byte trong buffer, đọc tiếp** cho đến khi đủ 4 byte hoặc gặp EOF/lỗi.
5. Khi đang gửi 10 byte, lần đầu write thành công 6 byte, lệnh tiếp theo là `flip()` hay `write(buffer)`? **`write(buffer)` tiếp**, với buffer giữ nguyên trạng thái và `remaining()==4`.
6. Sau khi parser tiêu thụ 7 byte trong tổng 10 byte đã nhận, muốn nhận thêm vào cùng buffer thì dùng gì? **`compact()`**, để giữ lại 3 byte chưa xử lý.
7. Tại sao cùng một payload có thể cần 1 lần read trên máy này nhưng 5 lần read trên máy khác? **API chỉ trả số byte thực chuyển mỗi lần**, phụ thuộc provider, tốc độ đến của dữ liệu, bộ đệm và điều kiện thời điểm.
8. Lệnh `write` đã gửi toàn bộ buffer có chứng minh peer xử lý xong không? **Không.** Nếu cần xác nhận xử lý, giao thức phải có acknowledgment ứng dụng riêng.
9. `ScatteringByteChannel.read(buffers)` trả `long n`. Có phải `n` là số buffer đã được điền? **Không.** Đó là tổng số byte được đọc.
10. Cần ngăn chương trình đọc vô hạn từ client ác ý bằng cách nào? **Quy định giới hạn frame, deadline/timeout, kiểm soát dung lượng bộ đệm và cơ chế hủy/đóng kết nối** theo giao thức.

**Ghi nhớ:** Java NIO Channel cung cấp **số byte thực chuyển trong mỗi lần gọi**; buffer giữ tiến độ qua `position`. Để không mất hay lặp dữ liệu, đọc/ghi theo `remaining()`, giữ trạng thái sau partial I/O, phân biệt `0` với `-1`, và kết hợp cơ chế chờ sự kiện phù hợp với blocking hay non-blocking mode.
