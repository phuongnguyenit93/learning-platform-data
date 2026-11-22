# Đọc hoặc ghi một phần trong Java NIO; phân biệt 0 với kết thúc luồng

## 1. Bối cảnh và mục tiêu

Trong Java NIO, một lời gọi `SocketChannel.read(ByteBuffer)` hoặc `SocketChannel.write(ByteBuffer)` không đồng nghĩa với việc đã xử lý trọn **thông điệp ứng dụng**. TCP cung cấp **luồng byte có thứ tự**; nó không giữ ranh giới giữa các lần gọi `write()`, không tự biết header/payload và không hứa một lần `read()` trả đúng số byte được gửi trong một lần `write()`.

Bài này tập trung vào hai quy tắc sống còn:

1. **Đọc có thể chỉ được một phần.** Với `ReadableByteChannel.read(ByteBuffer)`, kết quả **dương** là số byte đã chuyển, **`0`** là chưa chuyển byte nào trong lần gọi, còn **`-1`** mới là **EOF** (kết thúc luồng đầu vào).
2. **Ghi có thể chỉ được một phần.** Với `WritableByteChannel.write(ByteBuffer)`, kết quả là **số byte thực sự ghi**, có thể bằng `0` nếu chưa thể ghi. Phần chưa ghi vẫn nằm trong `ByteBuffer`; đầu ghi **không dùng `-1` để báo EOF**.

Sau khi học, bạn sẽ biết cách đọc/ghi qua `SocketChannel`, sử dụng `ByteBuffer.position/limit/flip/compact`, xử lý một frame bị chia làm nhiều chunk, phân biệt stream I/O truyền thống với NIO, dùng `Selector` thay cho busy-spin và xử lý kết nối đóng giữa một frame. Ví dụ Java 17+ dùng `Pipe` để tạo các trường hợp 0, partial transfer và EOF **có thể kiểm chứng lặp lại được**, không phải trông vào lịch mạng may rủi.

## 2. Ba kiểu kết quả đọc: dương, 0, -1

`ReadableByteChannel.read(ByteBuffer dst)` và `SocketChannel.read(dst)` trả kiểu `int`. Ý nghĩa:

| Giá trị | Chuyện gì đã xảy ra? | Hành động |
| --- | --- | --- |
| `n > 0` | Đã đọc đúng **n byte** vào buffer; `position` tăng n | Parse byte vừa có hoặc đọc thêm nếu frame chưa đủ |
| `n == 0` | Không chuyển byte nào **trong lần gọi này** | Kiểm tra buffer còn chỗ; với non-blocking thì chờ readiness |
| `n == -1` | Nguồn đã tới **end-of-stream** | Kiểm tra frame dở, đóng/half-close theo protocol |

Khi kênh ở **non-blocking mode**, `0` thường có nghĩa dữ liệu **chưa sẵn sàng ngay lúc đó**. Một nguyên nhân khác: `dst.remaining() == 0` (buffer đã đầy), nên lời gọi không thể nhận thêm byte cho dù socket có dữ liệu. Do vậy `0` **không chứng minh peer đã hết dữ liệu**, cũng không chứng minh mạng không có lưu lượng.

Một đầu TCP có thể gửi 5 byte rồi kết thúc chiều gửi. Đầu nhận có thể thấy:

~~~text
Dữ liệu gửi: 11 22 33 44 55

Cách nhận hợp lệ 1:
read -> 5 byte
read -> -1

Cách nhận hợp lệ 2:
read -> 2 byte
read -> 0 byte (non-blocking, chưa có byte mới)
read -> 3 byte
read -> -1

Cách nhận hợp lệ 3:
read -> 1 byte
read -> 1 byte
read -> 3 byte
read -> -1
~~~

**`-1` chỉ xuất hiện sau khi các byte đã nhận được trong luồng được tiêu thụ hết** và nguồn đã đóng chiều gửi. Nếu có TCP reset/lỗi kết nối, Java có thể ném `IOException` thay vì trả `-1`. Nếu buffer đích không còn chỗ, ngay cả sau khi peer đã gửi FIN, lần đọc vào buffer đầy có thể trả `0`; phải giải phóng chỗ trước khi kiểm tra EOF.

### 2.1. 0 byte đã chuyển khác byte có giá trị 0

Không được nhầm **số lượng byte** với **giá trị byte dữ liệu**:

~~~text
Trên dây có một byte 00 (giá trị số 0).
SocketChannel.read(dst) -> 1  (đã đưa 1 byte vào dst)
dst.get()               -> 0  (byte dữ liệu vừa nhận)

Không có dữ liệu sẵn ngay bây giờ:
SocketChannel.read(dst) -> 0  (không chuyển byte nào)

Kết thúc đầu vào:
SocketChannel.read(dst) -> -1
~~~

Giá trị 0 của dữ liệu là hoàn toàn hợp lệ trong protocol nhị phân. Không dừng nhận chỉ vì một byte trong buffer là `0x00`.

### 2.2. Blocking channel có thể đọc một phần không?

Có. Ở chế độ blocking, `SocketChannel.read(dst)` thường đợi cho tới khi có **ít nhất một byte** nếu buffer còn chỗ, hoặc EOF/lỗi; không có cam kết nó sẽ đợi **đủ toàn bộ buffer**. Ví dụ cần 4 byte header, read có thể trả `1`, `2` hoặc `4`. Vì vậy ngay cả với blocking mode, ứng dụng cần vòng lặp đọc cho đủ khi giao thức yêu cầu N byte.

Ở non-blocking mode, `0` là điều thường gặp ngay cả khi buffer còn chỗ. Hãy kiểm tra `channel.isBlocking()` khi lựa chọn cơ chế vòng lặp và timeout. Không dùng một vòng lặp quay liên tục để đợi `read()>0` trên non-blocking channel.

## 3. Phân biệt InputStream với Channel

Trong Java networking, code cũ có thể dùng `Socket.getInputStream()`, còn NIO dùng `SocketChannel`. Hai API có **hợp đồng trả về khác nhau ở overload**.

| API | Trả về | Trường hợp 0 | EOF |
| --- | --- | --- | --- |
| `InputStream.read()` | **Giá trị byte** 0..255 | **Một byte `0x00` hợp lệ** | `-1` |
| `InputStream.read(byte[],off,len)` | **Số byte đã đọc** | Với `len==0` trả 0; với `len>0`, stream blocking chuẩn thường đợi dữ liệu/EOF/lỗi | `-1` |
| `ReadableByteChannel.read(ByteBuffer)` | **Số byte đã đọc** | Không chuyển byte; có thể do non-blocking hoặc buffer đầy | `-1` |
| `SocketChannel.read(ByteBuffer)` | **Số byte đã đọc** | Không có tiến độ lần đó | `-1` |
| `WritableByteChannel.write(ByteBuffer)` | **Số byte đã ghi** | Chưa ghi được byte nào | Không có sentinel `-1` cho ghi |
| `OutputStream.write(byte[])` | `void` | Không có số lượng trả về | Thành công hoặc ném exception |

Sai lầm điển hình:

~~~java
// SAI với InputStream.read() không tham số:
int value = input.read();
if (value == 0) {
    return; // Sẽ bỏ cuộc khi gặp byte 0x00 hợp lệ!
}

// ĐÚNG:
int value2 = input.read();
if (value2 == -1) {
    // EOF.
} else {
    // Byte thực có giá trị 0..255, kể cả 0.
}
~~~

Hai đoạn là minh họa trong phương thức có biến `input` là `InputStream` và khai báo/handle `IOException`. Khi xử lý stream nhị phân, tránh trộn các loại API rồi suy luận “`0` luôn là EOF”.

Ngoài ra, `InputStream.available() == 0` **không chứng minh EOF** và không cho biết tổng kích thước thông điệp. Nó chỉ báo số byte ước lượng có thể đọc ngay mà không bị chặn theo hợp đồng của loại stream. Với protocol TCP, phải dùng **framing** hoặc EOF thực sự, không sử dụng `available()` để quyết định “message đã đủ”.

## 4. Ghi một phần: write trả số byte đã tiêu thụ

`SocketChannel.write(ByteBuffer src)` có thể ghi **ít hơn** `src.remaining()`. Nó cập nhật `position` của `src` theo số byte đã lấy ra, để lần gọi kế tiếp bắt đầu từ đúng phần **chưa gửi**.

~~~text
ByteBuffer nguồn:
position=0, limit=1000, remaining=1000

Lần write 1 -> 300:
position=300, remaining=700

Lần write 2 -> 0 (non-blocking, send buffer chưa nhận thêm):
position=300, remaining=700

Sau sự kiện writable:
Lần write 3 -> 700:
position=1000, remaining=0
~~~

Đừng gọi `src.flip()` lại sau mỗi lần ghi một phần: nó đưa `position` về 0 và có thể khiến bạn **gửi lặp byte đã gửi**. Đừng gọi `src.clear()` khi `hasRemaining()==true`, vì sẽ đánh mất trạng thái offset chưa gửi. Chỉ khi buffer hết remaining hoặc đã được copy để giữ phần dư, bạn mới được tái sử dụng có chủ đích.

### 4.1. Mẫu vòng ghi đủ cho blocking SocketChannel

~~~java
// Hàm tiện ích minh họa, không phải file độc lập.
// Cần import java.io.*, java.nio.*, java.nio.channels.*.
static void writeAllBlocking(SocketChannel channel, ByteBuffer source)
        throws IOException {

    if (!channel.isBlocking()) {
        throw new IllegalArgumentException(
                "Non-blocking channel requires readiness handling");
    }

    while (source.hasRemaining()) {
        int written = channel.write(source);
        if (written == 0) {
            // Với blocking socket và buffer còn dữ liệu,
            // không được lặp vô hạn trong tình huống bất thường.
            throw new IOException("Write made no progress");
        }
    }
}
~~~

Với blocking `SocketChannel` có buffer chưa hết, `write` thường đợi có thể ghi ít nhất một phần; vòng lặp trên xử lý trường hợp trả số byte dương nhưng chưa hết. Một lần ghi trả số dương chỉ nói dữ liệu đã được channel nhận để gửi xuống network stack, **không** chứng minh server bên kia đã đọc hay xử lý.

Với **non-blocking** channel, `write()==0` là tình huống bình thường. Thay vì ném lỗi hoặc spin, **giữ buffer trong outbound queue, đăng ký `OP_WRITE` khi có dữ liệu, và thử tiếp khi channel writable**.

### 4.2. `write()` không trả -1 như read

Đóng kênh, đầu ra bị lỗi hoặc kết nối chưa hình thành thường được báo bằng **exception** phù hợp như `ClosedChannelException`, `NotYetConnectedException` hay `IOException`. Không bao giờ viết `if (channel.write(buf) == -1) ...` rồi chờ nó báo EOF. Hợp đồng ghi không có `-1` sentinel.

Một peer có thể đã đóng chiều nhận mà bên gửi chưa biết ngay; thành công của một lần `write` không bảo đảm phía kia nhận hết. Khi hệ thống phát hiện lỗi, lời gọi sau có thể ném exception. Giao thức ứng dụng cần ACK/response để xác nhận xử lý, không dựa vào count từ `write`.

## 5. ByteBuffer: position, limit và trạng thái còn lại

`ByteBuffer` là bộ nhớ byte **có trạng thái**. Những thông số cần nắm:

- `capacity()`: tổng dung lượng byte buffer có thể chứa.
- `position()`: chỉ số byte tiếp theo cho thao tác `put/get` hoặc channel `read/write`.
- `limit()`: giới hạn hiện hành, không cho thao tác vượt qua.
- `remaining() == limit - position`: số byte còn lại trong vùng làm việc.
- `hasRemaining()`: kiểm tra còn chỗ (khi nhận byte) hoặc còn dữ liệu (khi gửi byte), tùy **pha**.

Hai pha quan trọng:

1. **Filling/putting:** đưa byte từ network vào buffer hoặc `put` dữ liệu, `position` tiến về cuối.
2. **Draining/getting:** sau `flip()`, buffer sẵn sàng cho parser hoặc cho `channel.write()` tiêu thụ.

### 5.1. Flip đúng lúc

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[]{10, 20, 30, 40, 50});
// position = 5, limit = 8; đang ở pha ghi vào buffer.

buffer.flip();
// position = 0, limit = 5; đang ở pha đọc 5 byte.

byte first = buffer.get(); // first == 10
// position = 1, remaining = 4.
~~~

`flip()` **không xóa byte**, chỉ đặt `limit` thành position cũ rồi đưa position về 0. Để gửi phần 5 byte này qua `SocketChannel`, hãy gọi `write(buffer)` và giữ nguyên buffer giữa những lần ghi dở.

### 5.2. Compact giữ lại phần frame chưa đọc

Khi nhận dữ liệu:

~~~text
buffer sau read từ channel:
[ header frame A ][ payload A ][ 2 byte đầu frame B ][ chỗ trống ]

buffer.flip()
  parser tiêu thụ frame A, còn 2 byte đầu frame B.

buffer.compact()
  dời 2 byte dở về đầu, position=2, limit=capacity.
  Lần read tiếp nhận thêm byte sau hai byte đó.
~~~

`compact()` rất cần thiết khi một `read` chứa nhiều frame nhưng frame cuối mới tới một phần. Nếu bạn gọi `clear()` ngay sau khi parse frame A, hai byte đã nhận của frame B sẽ bị xem như dữ liệu không cần giữ, làm lệch giao thức. `clear()` chỉ reset pointers, không xóa nội dung vật lý, nhưng làm mất ý nghĩa các byte cũ.

### 5.3. Buffer đầy và read trả 0

Nếu `position==limit` của buffer đích, `read(dst)` không có nơi chứa byte và có thể trả `0` ngay cả khi socket đã có byte hoặc peer đã gửi FIN. Đó là **lý do đọc 0 do phía ứng dụng**, không phải bằng chứng endpoint chưa phát gì.

Khi thấy `read()==0`, luôn cân nhắc:

- Buffer còn `remaining()>0` hay không?
- Channel đang blocking hay non-blocking?
- Có đang chờ readiness đúng cách không?
- Parser có tiêu thụ dữ liệu và `compact()` để dành chỗ chưa?
- Frame có lớn hơn giới hạn cấp phát/buffer hay không?

Không phải cứ buffer đầy là tăng bộ nhớ vô hạn; hãy đặt **max frame size** và loại bỏ đầu vào bất hợp lệ.

## 6. Một ví dụ Java 17+ có kết quả ổn định: 0, partial, -1

Trên TCP, không thể giả định rằng hai lần `write` của sender sẽ được server đọc bằng đúng hai lần `read`. Để kiểm tra độc lập số lượng byte và EOF, chương trình sau dùng `java.nio.channels.Pipe`: source non-blocking, sink blocking. Ta **chủ động giới hạn ByteBuffer.limit()** để có hai lần ghi 2+3 byte, hai lần đọc 2+3 byte, sau đó thử đọc khi chưa EOF và sau khi đóng đầu ghi.

`Pipe` là byte stream một chiều nội bộ, không phải TCP socket; tuy nhiên return values và ByteBuffer position thuộc cùng họ API NIO, rất thích hợp để **minh họa chính xác** cách phân biệt read 0 với -1.

Tạo file **PartialChannelDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.util.Arrays;

public class PartialChannelDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            source.configureBlocking(false);

            ByteBuffer received = ByteBuffer.allocate(8);
            System.out.println(
                    "read(empty) = " + source.read(received));

            ByteBuffer sending = ByteBuffer.wrap(
                    new byte[]{10, 20, 30, 40, 50});

            sending.limit(2);
            int sent1 = sink.write(sending);
            sending.limit(5);
            int sent2 = sink.write(sending);
            System.out.println(
                    "sent = " + sent1 + " + " + sent2);

            received.limit(2);
            int first = source.read(received);
            received.limit(5);
            int second = source.read(received);
            System.out.println(
                    "read = " + first + " + " + second);

            received.limit(received.capacity());
            System.out.println(
                    "read(no new data) = " + source.read(received));

            sink.close();
            System.out.println(
                    "read(EOF) = " + source.read(received));

            received.flip();
            byte[] bytes = new byte[received.remaining()];
            received.get(bytes);
            System.out.println(
                    "bytes = " + Arrays.toString(bytes));
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PartialChannelDemo.java
java PartialChannelDemo
~~~

Stdout chính xác khi chạy thành công:

~~~text
read(empty) = 0
sent = 2 + 3
read = 2 + 3
read(no new data) = 0
read(EOF) = -1
bytes = [10, 20, 30, 40, 50]
~~~

**Đọc kết quả từng bước:**

1. Source non-blocking chưa có dữ liệu, `source.read(received)` trả **0**. Sink vẫn mở; không hề có EOF.
2. Ghi có giới hạn 2 byte, sau đó mở giới hạn lên 5 byte. `sending.position` tự tăng theo số byte đã viết; kết quả 2+3.
3. Nhận có giới hạn 2 byte, rồi mở lên 5. Tương ứng đọc 2+3; đây là chia nhỏ **có chủ đích** bằng limit để tạo bài thử, không phải thuộc tính “TCP chia mỗi lần 2 và 3”.
4. Mở limit của received ra hết capacity để **còn chỗ đọc**. Sink vẫn mở nhưng không có byte mới; kết quả **0**.
5. Đóng sink sau khi mọi byte gửi đã được đọc; `source.read` nhận **-1**, EOF thật.
6. `received.flip()` chuẩn bị lấy lại 5 byte đã đọc, in mảng `[10, 20, 30, 40, 50]`.

Thử bỏ `sink.close()`: lần đọc cuối không có byte sẽ thường trả 0, không có EOF. Thử bỏ bước `received.limit(received.capacity())`: buffer có thể đã đầy theo limit hiện hành và `read` trả 0 **do không còn chỗ**. Bỏ `received.flip()` trước `get` sẽ làm parser đọc sai vùng dữ liệu hợp lệ.

Chương trình không cần Internet hay port mạng để kiểm tra semantics của channel. Trên một TCP connection thực tế, cấu trúc return value vẫn tương tự, nhưng số byte trong từng lần đọc/ghi là do mạng, OS, channel mode và tiến độ peer quyết định.

## 7. TCP framing: chưa đủ byte không phải message đã hoàn tất

Một giao thức nhị phân phổ biến đặt trước payload một số nguyên 4 byte mô tả độ dài:

~~~text
+---------------------------+--------------------------+
| length (int32 big-endian) | payload: length byte     |
| 4 byte cố định            | 0 <= length <= 65,536    |
+---------------------------+--------------------------+

Gửi chuỗi ASCII "ABC":
00 00 00 03 | 41 42 43
header      | payload
~~~

Header 4 byte có thể được TCP đưa tới theo dạng 1+3, 2+2, hoặc 4 byte một lần. Payload cũng vậy. **Không gọi `ByteBuffer.getInt()` trước khi có đủ bốn byte hợp lệ**; nếu chỉ có hai byte, có thể nhận `BufferUnderflowException`.

### 7.1. Blocking SocketChannel: đọc đủ N byte

Hàm minh họa dành riêng cho **blocking `SocketChannel`**:

~~~java
// Cần import java.io.*, java.nio.*, java.nio.channels.*.
static void readFullyBlocking(SocketChannel channel, ByteBuffer target)
        throws IOException {
    if (!channel.isBlocking()) {
        throw new IllegalArgumentException(
                "Use a Selector/readiness loop for non-blocking mode");
    }

    while (target.hasRemaining()) {
        int n = channel.read(target);
        if (n == -1) {
            throw new EOFException("Peer ended stream mid-frame");
        }
        if (n == 0) {
            // Guard: không spin vô hạn với buffer còn chỗ.
            throw new IOException("Read made no progress");
        }
    }
}
~~~

Đây là **phương thức bổ sung**, không phải `main` độc lập. Với channel blocking và buffer còn chỗ, read thông thường sẽ chờ byte/EOF/lỗi; vòng lặp xử lý trường hợp lần đầu chỉ nhận 1–3 byte. Không dùng hàm này với non-blocking: `0` ở nonblocking là tín hiệu đợi readiness, không phải lỗi tự động.

Sử dụng helper để đọc frame:

~~~java
// Đặt cùng lớp với readFullyBlocking; đoạn minh họa.
static ByteBuffer readFrameBlocking(SocketChannel channel)
        throws IOException {
    ByteBuffer header = ByteBuffer.allocate(4)
            .order(ByteOrder.BIG_ENDIAN);

    readFullyBlocking(channel, header);
    header.flip();
    int length = header.getInt();

    if (length < 0 || length > 65_536) {
        throw new IOException("Invalid frame length: " + length);
    }

    ByteBuffer payload = ByteBuffer.allocate(length);
    readFullyBlocking(channel, payload);
    payload.flip();
    return payload;
}
~~~

**Length 0** có thể là **frame rỗng hợp lệ** nếu protocol cho phép. Điều đó chỉ được biết từ **bốn byte header hợp lệ**, không phải từ một lần `read()==0`. Nếu peer gửi 3/4 byte header rồi EOF, đây là **truncated header**. Nếu gửi đủ header nhưng thiếu payload rồi EOF, là **truncated payload**.

Tinh tế: helper `readFullyBlocking` hiện coi EOF khi đang yêu cầu 4 byte mới là một `EOFException`. Trong server nhận **nhiều frame trên cùng kết nối**, EOF **ngay tại ranh giới trước frame mới** có thể là kết thúc bình thường; phân biệt điều này bằng parser có trạng thái, không báo lỗi dữ liệu cho mọi EOF tại ranh giới.

### 7.2. Blocking SocketChannel: gửi đủ header và payload

~~~java
static void writeFrameBlocking(SocketChannel channel, ByteBuffer payload)
        throws IOException {
    int length = payload.remaining();
    if (length > 65_536) {
        throw new IllegalArgumentException("Payload too large");
    }

    ByteBuffer header = ByteBuffer.allocate(4)
            .order(ByteOrder.BIG_ENDIAN);
    header.putInt(length).flip();

    writeAllBlocking(channel, header);
    writeAllBlocking(channel, payload);
}
~~~

Đoạn trên dùng helper `writeAllBlocking` ở mục 4 và là **mã minh họa thêm**, không phải chương trình riêng. `payload` phải ở pha đọc/sẵn sàng ghi ra network. `writeAllBlocking` sẽ khiến position tăng tới limit; nếu muốn giữ buffer cho tác vụ khác, dùng `duplicate()` hoặc copy có chủ đích.

Nếu write lỗi khi mới gửi được một phần payload, peer có thể đang giữ header và nửa frame. Đừng tự gửi lại **cả frame từ đầu** trên cùng TCP stream: nó có thể khiến parser bên kia nhầm byte của bản gửi lại thành phần đuôi của bản cũ. Cần quy ước retry/ACK ở tầng ứng dụng hoặc đóng và tạo phiên mới.

## 8. Non-blocking SocketChannel và Selector: xử lý kết quả 0

### 8.1. Không busy-spin khi không có tiến độ

Đây là ví dụ **sai**:

~~~java
// SAI: non-blocking read có thể trả 0 mãi, gây CPU 100%.
while (target.hasRemaining()) {
    channel.read(target);
}
~~~

Vòng lặp không kiểm tra `-1`; với EOF và buffer chưa đầy, nó cũng có thể chạy mãi. Ngay cả khi thêm `if (n == 0) continue`, vẫn bị busy-spin. Non-blocking I/O hoạt động đúng nhất khi gắn với **readiness/event loop**.

Mô hình thích hợp:

1. `channel.configureBlocking(false)`.
2. `channel.register(selector, SelectionKey.OP_READ, connectionState)`.
3. `selector.select(...)` chờ có sự kiện, không tự quay vòng liên tục.
4. `key.isReadable()`: gọi read; nếu n>0 thì parse; nếu n==0 thì giữ state; nếu n==-1 thì xử lý EOF.
5. Khi có outbound queue, thêm `SelectionKey.OP_WRITE` vào `interestOps`.
6. `key.isWritable()`: gọi write cho đến khi hết buffer hoặc `n==0`, rồi trả điều khiển cho event loop.
7. Khi hết outbound data, **tắt OP_WRITE** để tránh loop sẵn sàng liên tục.

### 8.2. Pseudocode event handler đúng cơ chế

~~~java
// PSEUDOCODE Java: không phải chương trình độc lập.
// in/out là ByteBuffer riêng của connection;
// closeConnection() và parseCompleteFrames() do ứng dụng tự viết.
if (key.isReadable()) {
    if (!in.hasRemaining()) {
        throw new IOException("Inbound buffer full");
    }

    int n = channel.read(in);
    if (n == -1) {
        closeConnection();  // Hoặc half-close theo giao thức.
    } else if (n > 0) {
        in.flip();
        parseCompleteFrames(in);
        in.compact();
    } else {
        // n == 0: không EOF, không reset buffer.
        // Trở lại Selector và chờ sự kiện kế.
    }
}

if (key.isValid() && key.isWritable()) {
    while (out.hasRemaining()) {
        int n = channel.write(out);
        if (n == 0) {
            break; // Không spin; chờ OP_WRITE kế tiếp.
        }
    }

    if (!out.hasRemaining()) {
        key.interestOps(
                key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
~~~

Đây chỉ là **logic minh họa**; `parseCompleteFrames`, `closeConnection`, lifecycle của key, queue nhiều frame và các lỗi của event loop cần triển khai riêng. Điểm cần học là **giữ trạng thái khi có kết quả 0**, và cập nhật OP_WRITE theo dữ liệu thực tế cần gửi.

**Tại sao phải tắt OP_WRITE khi không còn dữ liệu?** Socket thường writable gần như mọi lúc nếu send buffer chưa đầy. Đăng ký OP_WRITE liên tục có thể làm `select()` thức dậy liên tục và tiêu CPU trong khi không có gì để gửi. Khi outbound queue có thêm byte, bật lại OP_WRITE và gọi `selector.wakeup()` nếu thread khác đã sửa interest set hoặc phát sinh dữ liệu mới.

Readiness không bảo đảm mỗi lời gọi sau đó có n>0, vì trạng thái có thể thay đổi hoặc buffer đã hết chỗ. Trả 0 không nhất thiết là lỗi; hãy trở về vòng select, theo dõi deadline và metrics.

### 8.3. Đừng đánh đồng timeout với read 0

Một `SocketChannel` non-blocking trả 0 **ngay lúc đó** khi chưa có byte: không có nghĩa đã đợi tới timeout. `Selector.select(timeoutMs)` có thể chờ có giới hạn, nhưng một lần select timeout cũng **chưa phải** deadline tổng cho message nếu code lặp nhiều sự kiện. Ứng dụng phải dùng deadline riêng, ví dụ từ `System.nanoTime()`, và kiểm tra thời gian còn lại.

`Socket.setSoTimeout()` thường dùng để giới hạn blocking `InputStream.read` trên socket truyền thống; không được giả định đặt SO_TIMEOUT sẽ biến `SocketChannel.read(ByteBuffer)` non-blocking thành đọc chờ trong N mili giây. Cơ chế của NIO là readiness + deadline do ứng dụng quản lý.

## 9. Parser trạng thái khi frame bị chia thành nhiều chunk

Với giao thức length-prefix, một máy trạng thái đơn giản:

~~~text
WAIT_HEADER:
  giữ byte đã nhận cho đến khi đủ 4 byte
  decode length; kiểm tra 0 <= length <= MAX_FRAME
  nếu length == 0: hoàn tất empty frame
  nếu length > 0: chuyển WAIT_PAYLOAD

WAIT_PAYLOAD:
  tích lũy đúng length byte payload
  khi đủ: xử lý frame, quay lại WAIT_HEADER

on read(n > 0):
  thêm n byte rồi parse nhiều frame nếu có thể

on read(n == 0):
  giữ state và bytes chưa hoàn chỉnh, chờ readiness

on read(n == -1):
  nếu ở ranh giới frame: EOF hợp lệ theo protocol
  nếu đang giữ header/payload dở: truncated frame
~~~

Đọc một lần có thể nhận **nhiều frame nối nhau** hoặc chỉ một nửa frame. Parser phải tiêu thụ trọn các frame có thể, rồi giữ phần byte đầu của frame cuối để xử lý khi có thêm. Với ByteBuffer inbound, chu trình phổ biến:

~~~text
channel.read(in)        -> nhận byte vào cuối buffer [write mode]
in.flip()               -> giới hạn vùng byte hợp lệ [read mode]
parseCompleteFrames(in) -> tiêu thụ các frame hoàn chỉnh
in.compact()            -> giữ byte chưa parse và mở chỗ cho read mới
~~~

Cẩn thận `compact` giữ lại phần dữ liệu chưa đọc. Nếu parser không thể xử lý vì buffer đầy mà còn thiếu frame lớn, phải **giới hạn/kiểm tra length và phân bổ buffer có kiểm soát**, không tiếp tục gọi read vào buffer đầy khiến return 0 vô hạn.

### 9.1. Vì sao EOF giữa frame không được nuốt?

Giả sử đã đọc header length=100 và chỉ nhận 70 byte payload, sau đó peer đóng chiều gửi. Nếu lần tiếp theo `read()==-1`, frame đó **đã bị cắt cụt**. Một server đúng phải báo protocol error hoặc đóng phiên, không bàn giao 70 byte như payload hoàn chỉnh. Nếu đã đọc đủ 100 byte rồi mới nhận EOF ở ranh giới frame mới, có thể kết thúc phiên bình thường.

Tương tự nếu header có 4 byte mà peer gửi 2 byte rồi EOF, không gọi `getInt()` và không diễn giải 2 byte thiếu là length 0.

### 9.2. Half-close và EOF

Ở TCP, peer có thể gọi `shutdownOutput()`, kết thúc **chiều gửi** mà chưa đóng chiều còn lại. Phía nhận đọc hết byte đệm rồi gặp `-1`, nhưng tùy protocol vẫn có thể gửi response trên chiều ghi của mình. `-1` ở `read` nghĩa là **EOF đầu vào**, không phải chỉ “chưa có dữ liệu”; cũng không nhất thiết đồng nghĩa mọi thao tác ghi đều lập tức không hợp lệ.

Nếu kết nối bị reset hoặc có lỗi I/O bất thường, Java có thể ném `IOException` thay vì trả -1. Đừng nuốt lỗi thành EOF bình thường: chúng có khác biệt quan trọng khi retry, chẩn đoán và đối soát dữ liệu.

## 10. Backpressure và bộ nhớ khi ghi bị kẹt

Một peer đọc dữ liệu rất chậm có thể khiến nonblocking `write()==0` vì OS send buffer chưa nhận thêm. Trong khi đó ứng dụng vẫn sinh frame mới. Nếu cứ đưa frame vào queue không giới hạn, bộ nhớ có thể tăng cho tới khi cạn heap.

Thiết kế an toàn nên có:

- **Outbound queue theo từng connection**, lưu `ByteBuffer` và offset còn lại.
- **Giới hạn tổng số byte chưa gửi** và số frame queued; từ chối hoặc giảm tốc producer nếu vượt ngưỡng.
- `OP_WRITE` chỉ bật khi queue không rỗng và chỉ tắt khi không còn byte chờ.
- **Timeout tiến độ ghi**: nếu channel không writable hoặc peer không đọc quá lâu, đóng phiên theo chính sách.
- **Không để nhiều threads cùng ghi trộn frame.** Một writer/event loop sở hữu socket là cấu trúc dễ kiểm soát.
- **Metrics**: pending bytes, số lần write 0, thời gian chờ writable, số phiên bị đóng vì quá tải.

Tương tự, nếu inbound buffer đầy và parser không tiêu thụ kịp, bạn cần dừng tạm `OP_READ` hoặc giới hạn frame/phiên theo khả năng ứng dụng, không lặp vô hạn `read` rồi chấp nhận `0`.

Một lần `write` trả số dương nghĩa là byte đã được chấp nhận vào tầng channel/OS, **không** xác nhận remote application xử lý chúng. Với message có side effect, application-level acknowledgment và idempotency quan trọng hơn việc writer đếm được bao nhiêu byte.

## 11. Bảng lỗi thường gặp

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Nghĩ `SocketChannel.read()==0` là EOF | 0 là không chuyển byte; có thể nonblocking/no room | Giữ connection, dùng readiness, xử lý buffer |
| Nghĩ `InputStream.read()==0` là không có byte | 0 là byte `0x00` hợp lệ | `-1` mới là EOF với InputStream.read() |
| Gọi `read` một lần rồi cho là đủ frame | TCP không giữ message boundaries | Tích lũy đủ header/payload |
| Đọc 2 byte rồi `ByteBuffer.getInt()` | Chưa đủ 4 byte hợp lệ | Kiểm tra `remaining()>=4` |
| Lặp `while(read()==0)` | Busy-spin làm CPU tăng | Selector + readiness/deadline |
| `write` partial rồi `flip` lại source | Có thể gửi lặp byte | Giữ position và remaining |
| `write()==0` rồi xóa buffer | Mất payload chưa gửi | Giữ queue, đợi OP_WRITE |
| Luôn đăng ký OP_WRITE | Socket thường writable nên loop thức liên tục | Tắt khi outbound queue rỗng |
| Buffer đích đầy mà cứ read | Return 0 do hết chỗ | Parse/compact/tăng có giới hạn hoặc reject |
| Gọi `clear()` khi còn partial frame | Mất byte dở | `flip`, parse, `compact` |
| Trộn 0-length frame với read 0 | Một bên là giá trị protocol, một bên là I/O count | Chỉ chốt length sau đủ header |
| EOF giữa frame mà vẫn xử lý payload | Frame bị truncate | Báo lỗi và đóng/xử lý đúng protocol |
| Dùng `available()==0` để nhận biết EOF | Không phải chỉ báo hết luồng | Đọc và xét `-1` |
| Hiểu write trả -1 là đóng output | Không có -1 ở write API | Bắt IOException/closed-channel |
| Retry gửi từ đầu sau partial write | Peer có thể đã nhận phần đầu | Tiếp tục từ offset hoặc reset theo protocol |
| Chỉ đo số byte mà không đặt timeout | Peer có thể ngưng gửi và giữ phiên | Deadline, read/write progress timeout |

## 12. Bài tập tự kiểm tra

### Bài 1: 0, 5, -1

Một nonblocking `SocketChannel` trả `0` rồi `5` rồi `-1` trong ba lần `read`. Nghĩa là gì?

**Đáp án:** lần đầu chưa có tiến độ; lần hai nhận đúng 5 byte; lần ba đã tới EOF đầu vào. Không được đóng ở lần đầu chỉ vì nhận 0. Trước khi đóng ở lần cuối, parser phải kiểm tra 5 byte đã đủ frame hay chưa.

### Bài 2: Buffer có 100 byte, write trả 60 rồi 0

**Đáp án:** đã gửi cho channel 60 byte; `position` tăng 60, còn 40 byte. Lần `write==0` không gửi thêm byte và không chứng minh peer đóng. Giữ nguyên buffer, chờ readiness, ghi nốt 40 byte từ offset cũ.

### Bài 3: InputStream nhận byte 0 rồi 255

`input.read()` trả `0`, sau đó `255`, sau đó `-1`.

**Đáp án:** hai byte hợp lệ là `0x00` và `0xFF`; giá trị `-1` mới là EOF. Không so sánh với 0 để quyết định kết thúc InputStream.

### Bài 4: Header 00 00 00 00

Một parser nhận đủ bốn byte header `00 00 00 00`, tức length 0, nhưng trước đó một lần `read` trả 0. 

**Đáp án:** length 0 là **giá trị dữ liệu của giao thức**, có thể là frame payload rỗng hợp lệ; read 0 chỉ cho biết một lần không chuyển byte. Không kết luận frame length=0 từ return value của channel.

### Bài 5: EOF giữa header

Đã nhận 3/4 byte header, lần gọi tiếp theo trả -1.

**Đáp án:** truncated frame. Không decode thiếu byte, không tiếp tục chờ trên luồng đã EOF. Truyền lỗi có ngữ cảnh, cleanup socket.

### Bài 6: Buffer đầy

`dst.position()==dst.limit()==dst.capacity()` nhưng read trả 0.

**Đáp án:** nguyên nhân trực tiếp có thể là buffer không còn chỗ. Cần parse/flip/compact, hoặc kiểm tra giới hạn frame. Không suy ra socket đã hết dữ liệu.

### Bài 7: OP_WRITE làm CPU cao

Event loop luôn đăng ký `OP_WRITE` kể cả khi không có frame queued.

**Đáp án:** socket thường writable nên selector thức liên tục. Bật OP_WRITE chỉ khi có pending bytes, và tắt ngay khi gửi hết.

### Bài 8: Gửi hai lần, nhận một lần

Sender gọi write với buffer 2 byte và buffer 3 byte; receiver đọc một lượt đủ 5 byte.

**Đáp án:** hoàn toàn bình thường. TCP chỉ bảo toàn thứ tự byte, không bảo toàn số lần gọi write. Phải dùng framing thay vì đếm các chunk từ network.

## 13. Checklist khi triển khai SocketChannel

- [ ] Phân biệt API trả **giá trị byte** và API trả **số byte**?
- [ ] Đọc `-1` là EOF, đọc `0` không tự động coi là EOF?
- [ ] Ghi `0` không xóa buffer chưa gửi và không gây busy-spin?
- [ ] Khi n>0, giữ đúng `ByteBuffer.position` đã được channel cập nhật?
- [ ] Không `flip/clear` sau mỗi partial write?
- [ ] Với inbound, dùng `flip -> parse -> compact` để giữ phần dữ liệu dở?
- [ ] Mọi frame có header/payload định nghĩa rõ, length tối đa và giới hạn memory?
- [ ] EOF giữa frame bị coi là truncated; EOF tại ranh giới xử lý theo protocol?
- [ ] Blocking channel đọc/ghi đủ khi cần; nonblocking dùng `Selector` và readiness?
- [ ] OP_WRITE chỉ bật khi outbound queue còn byte, có giới hạn queue và timeout?
- [ ] Buffer đầy được xử lý, không liên tục read để nhận 0?
- [ ] Test cả trường hợp 1+3, 2+2, all-at-once, read 0, write 0, EOF giữa header và payload?

**Kết luận:** `0` ở phép đọc/ghi số lượng byte của NIO chỉ nghĩa là **lần gọi chưa chuyển được byte nào**; `-1` ở phép đọc mới là **hết luồng**. Đọc/ghi một phần là hoạt động bình thường của buffer/channel, đặc biệt với TCP và non-blocking I/O. Muốn chương trình đúng, phải **giữ trạng thái buffer**, **đợi readiness thay vì busy-spin**, và **chỉ xử lý message khi đã có đủ byte theo framing**.