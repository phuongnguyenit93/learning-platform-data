# Gửi UDP với buffer nhỏ: quan sát cắt dữ liệu và ranh giới datagram trong Java 17

## 1. Bài toán thực nghiệm: gửi 12 byte, tại sao chỉ nhận được 5 byte?

Giả sử chương trình gửi một UDP datagram có nội dung ASCII:

```text
ABCDEFGHIJKL
```

Phía nhận dùng `byte[]` dài **5 byte**. Kết quả điển hình khi chạy trên loopback là:

```text
Gửi:        ABCDEFGHIJKL  (12 byte trong một UDP datagram)
Nhận #1:    ABCDE         (5 byte được chép vào buffer)
Phần dư:         FGHIJKL   (7 byte bị loại bỏ, KHÔNG chờ lần nhận sau)

Gửi tiếp:   xyz           (một UDP datagram khác)
Nhận #2:    xyz           (3 byte của datagram thứ hai)
```

**UDP giữ ranh giới thông điệp (*message/datagram boundary*)**: mỗi lần nhận thành công qua `DatagramSocket.receive(DatagramPacket)` hoặc `DatagramChannel.receive(ByteBuffer)` lấy **một datagram**, không phải lấy một số byte tùy ý từ một luồng dài. Nếu vùng đích không chứa nổi datagram, phần không chép được **bị bỏ**, không được nối vào lần gọi `receive` tiếp theo.

Điểm này trái với cách tư duy về TCP `InputStream.read()`: TCP cung cấp **luồng byte**, một lần `read` có thể đọc một phần của application message và các lần đọc sau lấy phần tiếp theo từ cùng stream; UDP cung cấp **các datagram riêng biệt**, mỗi datagram mang payload có ranh giới của chính nó.

**Kết luận ngắn:** UDP `send` một datagram lớn hơn buffer nhận → có thể quan sát **một datagram bị cắt**, không phải datagram tự chia thành nhiều lần `receive`. Gọi `receive` lần nữa không phục hồi phần đã mất. Muốn nhận đủ, thiết kế kích thước datagram/buffer hoặc protocol ứng dụng phù hợp.

Trong bài thực nghiệm này, ta chủ động gửi payload ngắn qua `127.0.0.1`, kiểm tra bytes thật, thử cả `DatagramSocket` và `DatagramChannel`, và phân biệt ba khái niệm thường bị trộn: **độ dài datagram gửi**, **khả năng chứa của buffer nhận**, **kích thước bộ đệm hệ điều hành của socket**.

## 2. UDP là gì và vì sao ranh giới datagram quan trọng?

Một UDP datagram có thể hình dung gồm:

```text
┌───────────────────────────────────────────┐
│ UDP header (8 byte)                       │
├───────────────────────────────────────────┤
│ Application payload: A B C D E F ... L    │
└───────────────────────────────────────────┘
             1 datagram
```

UDP định danh peer bằng IP và cổng nguồn/đích, vận chuyển các datagram độc lập. Một lần gửi bằng `DatagramSocket.send(packet)` thường tương ứng **một UDP datagram** với phần dữ liệu được mô tả bởi `DatagramPacket`. Trong NIO, `DatagramChannel.send(buffer, target)` gửi dữ liệu còn lại của source buffer thành **một datagram** khi thao tác gửi thực hiện thành công.

Các đặc tính cần ghi nhớ:

- **Có ranh giới:** Datagram 1 và datagram 2 không bị ghép làm một “byte stream” duy nhất ở API UDP nhận.
- **Không đảm bảo giao hàng:** Datagram có thể mất do mạng, hàng đợi đầy, lỗi routing, filter hoặc các nguyên nhân khác.
- **Không đảm bảo thứ tự:** Nếu gửi A trước B, không có bảo đảm chung B không tới trước A.
- **Không đảm bảo không trùng:** Với các tầng giao thức/triển khai khác nhau, application cần tự xác định xử lý duplicates, retries và idempotency.
- **Không có reliability/retransmission kiểu TCP:** Nếu datagram bị mất hoặc bị cắt tại buffer ứng dụng, lần `receive` sau không phải thao tác lấy lại byte thiếu.
- **Có giới hạn payload thực tế:** IP/UDP headers, MTU, fragmentation và platform limits ảnh hưởng kích thước nên gửi.
- **Cắt do buffer nhận là vấn đề tại phía nhận:** Ngay cả khi mạng đã chuyển đầy đủ datagram tới máy, application với buffer quá nhỏ vẫn chỉ quan sát được phần đầu.

Ví dụ này **không** thử độ tin cậy qua Internet. Loopback giúp giảm biến số mạng để dễ quan sát tính chất API, nhưng một bài test chạy đúng không biến UDP thành giao thức giao hàng đảm bảo.

### Sơ đồ vòng nhận

```text
Application sender
    send("ABCDEFGHIJKL")  ──────▶  UDP datagram #1, length = 12
                                      │
                                      v
                                 Kernel UDP receive
                                      │
                                      v
                             application receive cap=5
                                      │
                                      ├── copied bytes = "ABCDE"
                                      └── excess bytes = "FGHIJKL" DISCARDED

    send("xyz")           ──────▶  UDP datagram #2, length = 3
                                      │
                                      v
                             next application receive
                                      └── copied bytes = "xyz"
```

**Không có “nửa datagram còn lại” trong UDP receive queue** sau lần nhận đầu. Điều này khác cơ chế partial read của TCP.

## 3. Phân biệt bốn kích thước và ba loại buffer

| Tên | Nằm ở đâu? | Ý nghĩa thực tế |
|---|---|---|
| **UDP payload length** | Datagram mà sender tạo | Số byte ứng dụng gửi trong một datagram |
| **`DatagramPacket` receive length** | Đối tượng Java phía nhận | Số byte tối đa sẵn sàng nhận vào packet; sau `receive`, `getLength()` trả lượng dữ liệu đã nhận |
| **`byte[]` backing storage** | Bộ nhớ heap của ứng dụng | Dung lượng mảng; vùng được phép dùng còn phụ thuộc offset và packet receive length |
| **`ByteBuffer.remaining()`** | Buffer NIO khi gọi `DatagramChannel.receive` | Số byte còn trống từ `position` tới `limit` cho datagram hiện tại |
| **`SO_RCVBUF` / receive buffer size** | Hàng đợi/buffer nhận ở tầng socket OS | Khả năng đệm các datagram trước khi application lấy; không phải kích thước mảng nhận Java |
| **`SO_SNDBUF` / send buffer size** | Socket/OS | Khả năng đệm dữ liệu gửi; không quy định receiver sẽ có `byte[]` dài bao nhiêu |
| **Path MTU** | Đường mạng/IP | Kích thước gói IP có thể đi mà không cần fragmentation ở đường đi thích hợp |

Thực nghiệm “buffer nhỏ” ở đây chủ yếu nói tới **application receive buffer**: `new byte[5]` hoặc `ByteBuffer.allocate(4)`. Đừng tăng `setReceiveBufferSize(1_000_000)` rồi tưởng rằng một `DatagramPacket` chỉ có 5 byte sẽ tự chứa được 12 byte. Hai loại buffer khác nhau về vai trò.

### Java nhận payload như một đơn vị

Với `DatagramSocket`:

```java
byte[] bytes = new byte[5];
DatagramPacket received = new DatagramPacket(bytes, bytes.length);
socket.receive(received);
int copied = received.getLength(); // số byte được copy vào packet
```

Với `DatagramChannel`:

```java
ByteBuffer bytes = ByteBuffer.allocate(4);
SocketAddress remote = channel.receive(bytes);
int copied = bytes.position(); // giả định position ban đầu = 0
bytes.flip();                  // chuẩn bị đọc các byte vừa nhận
```

Hai đoạn trên là **minh họa API**, chưa phải chương trình độc lập (các biến `socket`, `channel` và import phải được cung cấp). Chương trình runnable hoàn chỉnh nằm ở phần 6.

## 4. `DatagramPacket`: buffer, offset, length và tái sử dụng an toàn

Các API chính trong `java.net.DatagramPacket`:

| Phương thức | Ý nghĩa |
|---|---|
| `getData()` | Trả về **mảng backing**; không phải một bản sao vừa đúng số byte nhận |
| `getOffset()` | Vị trí bắt đầu dữ liệu hợp lệ trong backing array |
| `getLength()` | Độ dài dữ liệu gửi hoặc số byte đã nhận sau `receive` |
| `setLength(int)` | Đặt giới hạn số byte của packet cho lần gửi/nhận tương ứng, không vượt dung lượng backing |
| `setData(byte[], offset, length)` | Thay mảng/offset/length theo ý định |
| `getAddress()`, `getPort()` | Địa chỉ IP và cổng nguồn của datagram vừa nhận (trong trường hợp nhận) |

### Chỉ đọc vùng dữ liệu hợp lệ

**Sai:**

```java
// Mã cố ý sai khi sử dụng packet vừa receive:
String value = new String(packet.getData(), StandardCharsets.UTF_8);
```

Mảng có thể chứa byte rác/cũ ở ngoài khoảng vừa nhận, hoặc packet sử dụng `offset > 0`. Với text đã biết UTF-8 và đã nhận đủ bytes, hãy giới hạn đúng vùng:

```java
String value = new String(
        packet.getData(),
        packet.getOffset(),
        packet.getLength(),
        StandardCharsets.UTF_8);
```

Ngay cả câu lệnh này **không chứng minh data đầy đủ**: nếu UDP datagram lớn hơn vùng nhận, text có thể bị cắt, thậm chí cắt giữa một code point UTF-8. Protocol layer cần kiểm tra độ dài/format trước khi tin dữ liệu.

### Có nên gọi lại `setLength` khi reuse?

Khi sử dụng lại một `DatagramPacket` nhận, nên đặt **receive limit mong muốn** trước mỗi `receive`:

```java
packet.setLength(packet.getData().length - packet.getOffset());
socket.receive(packet);
```

Dòng này diễn đạt rõ “lần tới tôi cho phép nhận tối đa phần còn lại của mảng”, tránh vô tình giữ một cap nhỏ do chính code đặt trước đó. Khi có `getOffset()`, không dùng `setLength(array.length)` nếu offset dương vì offset + length sẽ vượt mảng.

**Chi tiết quan trọng:** không kết luận máy móc rằng “một lần nhận datagram 3 byte khiến mọi lần nhận sau tự bị giới hạn 3 byte chỉ vì `getLength()==3`”. Cách hiện thực giữ capacity nội bộ có thể khác cách bạn suy đoán từ thuộc tính đã nhận. Trong bài chạy thật, **ta gọi tường minh `setLength(3)`** để thu hẹp giới hạn ở lượt #3 và #5; vì thế việc cắt ở những lượt đó là có chủ đích, kiểm chứng được, không dựa vào một giả định về reuse.

Nếu muốn đơn giản tuyệt đối, có thể tạo **packet mới trên mỗi lần nhận**, chấp nhận chi phí cấp phát; với luồng datagram nhanh, reuse buffer/packet giúp giảm cấp phát nhưng phải xử lý ownership, concurrency và metadata đúng.

### Không chia một DatagramPacket thành hai lượt receive

Sau `receive`, `getLength()` chỉ cho biết **số byte đã chép vào packet**. Khi bằng capacity, nó **không tự xác nhận đã đầy đủ**. Nó cũng **không cung cấp cờ “truncated” kiểu OS-specific `MSG_TRUNC`** trong API high-level này. Nhận tiếp sẽ lấy datagram mới nếu có, không lấy dư của datagram cũ.

## 5. Thiết kế thực nghiệm không phụ thuộc Internet

Chúng ta dùng:

- **IPv4 loopback `127.0.0.1`**, không cần DNS hay host bên ngoài.
- Receiver `DatagramSocket` bind vào cổng **0** để OS cấp một ephemeral UDP port còn trống; sender lấy `receiver.getLocalPort()` làm đích.
- Sender và receiver tạo trước, mỗi lần **gửi đúng một datagram rồi nhận**. Điều này khiến việc quan sát các datagram theo thứ tự của chương trình không phụ thuộc vào phát nhiều datagram cùng một lúc.
- `receiver.setSoTimeout(2000)` ngăn `receive` chờ vô hạn nếu packet bị mất/OS ngăn UDP; test sẽ thất bại rõ thay vì treo.
- Một backing byte array 5 byte cùng một `DatagramPacket` để thử nhiều receive capacities.
- Sau đó dùng cặp `DatagramChannel` riêng với `ByteBuffer.allocate(4)`.
- Với dữ liệu ASCII, số ký tự bằng số byte nên kết quả dễ đọc; với Unicode, in **hex bytes** để không che lỗi cắt UTF-8 bằng decoder thay thế ký tự lỗi.
- Mỗi kết quả được kiểm chứng bằng `AssertionError` nếu khác mong đợi; không có “PASS giả” chỉ vì code in một chuỗi.

Các lượt:

| Lượt | Datagram gửi | Độ dài gửi | Receive cap | Kết quả dự kiến |
|---|---|---:|---:|---|
| UDP #1 | `ABCDEFGHIJKL` | 12 | 5 | `ABCDE`; 7 byte cuối bị bỏ |
| UDP #2 | `xyz` | 3 | 5 | `xyz` — một datagram **mới**, không phải `FGHIJKL` |
| UDP #3 | `12345` | 5 | **3 được đặt tường minh** | `123` |
| UDP #4 | `HELLO` | 5 | **5 được khôi phục** | `HELLO` |
| UDP #5 | `A🙂B` (UTF-8) | 6 | **3** | Hex `41 F0 9F`, Unicode bị cắt giữa code point |
| UDP #6 | `abcde` | 5 | 5 | `abcde`, chính xác bằng capacity |
| NIO #1 | `NETWORK` | 7 | 4 | `NETW`, 3 byte cuối bị bỏ |
| NIO #2 | `ok` | 2 | 4 | `ok` — datagram mới, không phải `ORK` |

Không có yêu cầu chứng minh UDP Internet delivery: nếu firewall hoặc environment chặn loopback UDP, code sẽ báo lỗi/timeout. **Một lần chạy thành công trên loopback minh họa semantics khi datagram đã được giao**, không phải lời hứa mạng thật không mất/đảo thứ tự.

## 6. Chương trình Java 17 hoàn chỉnh — DatagramSocket và DatagramChannel

Tạo file **`UdpSmallBufferDemo.java`** với toàn bộ mã dưới đây. Chương trình chỉ dùng Java SE 17:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public class UdpSmallBufferDemo {
    private static void require(boolean pass, String message) {
        if (!pass) {
            throw new AssertionError(message);
        }
    }

    private static void send(
            DatagramSocket sender, InetAddress host,
            int port, byte[] data) throws Exception {
        sender.send(new DatagramPacket(data, data.length, host, port));
    }

    private static void sendText(
            DatagramSocket sender, InetAddress host,
            int port, String text) throws Exception {
        send(sender, host, port,
                text.getBytes(StandardCharsets.US_ASCII));
    }

    private static String text(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.US_ASCII);
    }

    private static String hex(DatagramPacket packet) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < packet.getLength(); i++) {
            int value = packet.getData()[packet.getOffset() + i] & 0xff;
            if (i != 0) {
                result.append(' ');
            }
            result.append(Character.forDigit(value >>> 4, 16));
            result.append(Character.forDigit(value & 15, 16));
        }
        return result.toString().toUpperCase(java.util.Locale.ROOT);
    }

    private static String receiveNio(
            DatagramChannel receiver, ByteBuffer buffer)
            throws Exception {
        buffer.clear();
        SocketAddress source = receiver.receive(buffer);
        require(source != null, "No UDP datagram");
        buffer.flip();
        byte[] data = new byte[buffer.remaining()];
        buffer.get(data);
        return new String(data, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        try (DatagramSocket receiver = new DatagramSocket(
                    new InetSocketAddress(loopback, 0));
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(2000);
            int port = receiver.getLocalPort();
            byte[] storage = new byte[5];
            DatagramPacket packet = new DatagramPacket(
                    storage, storage.length);

            sendText(sender, loopback, port, "ABCDEFGHIJKL");
            receiver.receive(packet);
            require(packet.getLength() == 5
                    && "ABCDE".equals(text(packet)), "First receive");
            System.out.println("UDP #1: " + text(packet)
                    + " (copied=" + packet.getLength() + " of 12)");

            packet.setLength(storage.length);
            sendText(sender, loopback, port, "xyz");
            receiver.receive(packet);
            require(packet.getLength() == 3
                    && "xyz".equals(text(packet)), "Second receive");
            System.out.println("UDP #2: " + text(packet)
                    + " (copied=" + packet.getLength() + ")");

            // Explicitly narrow the receive limit to three bytes.
            packet.setLength(3);
            sendText(sender, loopback, port, "12345");
            receiver.receive(packet);
            require(packet.getLength() == 3
                    && "123".equals(text(packet)), "Narrowed receive");
            System.out.println("UDP #3 with cap 3: "
                    + text(packet) + " (copied=" + packet.getLength() + ")");

            packet.setLength(storage.length);
            sendText(sender, loopback, port, "HELLO");
            receiver.receive(packet);
            require(packet.getLength() == 5
                    && "HELLO".equals(text(packet)), "Reset length");
            System.out.println("UDP #4 with cap 5: " + text(packet));

            byte[] unicode = "A\uD83D\uDE42B".getBytes(
                    StandardCharsets.UTF_8);
            require(unicode.length == 6, "UTF-8 payload length");
            packet.setLength(3);
            send(sender, loopback, port, unicode);
            receiver.receive(packet);
            require(packet.getLength() == 3
                    && "41 F0 9F".equals(hex(packet)), "UTF8 bytes");
            System.out.println("UDP #5 UTF-8 cut: "
                    + hex(packet) + " (sent=6, copied=3)");

            packet.setLength(storage.length);
            sendText(sender, loopback, port, "abcde");
            receiver.receive(packet);
            require("abcde".equals(text(packet)), "Exact-sized message");
            System.out.println("UDP #6 exact fit: "
                    + text(packet) + " (copied=" + packet.getLength() + ")");
            System.out.println("Length == capacity is ambiguous: "
                    + (packet.getLength() == storage.length));
        }

        try (DatagramChannel receiver = DatagramChannel.open(
                     StandardProtocolFamily.INET);
             DatagramChannel sender = DatagramChannel.open(
                     StandardProtocolFamily.INET)) {
            receiver.bind(new InetSocketAddress(loopback, 0));
            InetSocketAddress dest =
                    (InetSocketAddress) receiver.getLocalAddress();
            ByteBuffer small = ByteBuffer.allocate(4);

            int firstSent = sender.send(ByteBuffer.wrap(
                    "NETWORK".getBytes(StandardCharsets.US_ASCII)), dest);
            String first = receiveNio(receiver, small);
            require(firstSent == 7 && "NETW".equals(first), "NIO #1");
            System.out.println("NIO #1: " + first
                    + " (sent=7, copied=" + first.length() + ")");

            int nextSent = sender.send(ByteBuffer.wrap(
                    "ok".getBytes(StandardCharsets.US_ASCII)), dest);
            String second = receiveNio(receiver, small);
            require(nextSent == 2 && "ok".equals(second), "NIO #2");
            System.out.println("NIO #2: " + second
                    + " (copied=" + second.length() + ")");
        }
    }
}
```

### Biên dịch và chạy

Trên máy có **JDK 17+** và cho phép UDP loopback:

```bash
javac --release 17 -encoding UTF-8 UdpSmallBufferDemo.java
java UdpSmallBufferDemo
```

**Stdout chính xác của một lần thực nghiệm thành công:**

```text
UDP #1: ABCDE (copied=5 of 12)
UDP #2: xyz (copied=3)
UDP #3 with cap 3: 123 (copied=3)
UDP #4 with cap 5: HELLO
UDP #5 UTF-8 cut: 41 F0 9F (sent=6, copied=3)
UDP #6 exact fit: abcde (copied=5)
Length == capacity is ambiguous: true
NIO #1: NETW (sent=7, copied=4)
NIO #2: ok (copied=2)
```

Không có port cố định trong output vì OS chọn ephemeral port và chương trình không in port. Mỗi run có thể dùng cổng khác nhưng vẫn giữ các chuỗi kết quả trên nếu tất cả local UDP datagrams được giao thành công và đúng thứ tự các thao tác gửi/nhận của demo.

**Cảnh báo phạm vi:** `DatagramChannel.receive` ở ví dụ dùng **blocking mode**, nên không có `setSoTimeout` riêng như DatagramSocket. Các lệnh `send` được gọi trước `receive` trong cùng JVM để giảm nguy cơ block, nhưng môi trường cực đoan có thể vẫn làm mất datagram. Với ứng dụng thật, dùng `Selector`/nonblocking mode và deadline/cancellation thích hợp để không treo vô hạn.

## 7. Đọc kết quả: ranh giới datagram được bảo toàn thế nào?

### UDP #1 — Datagram lớn bị cắt

Sender gửi một `DatagramPacket` 12 byte, receiver cho phép chứa tối đa 5 byte. `receive` chỉ chép `ABCDE`, `getLength()==5`. Các byte `FGHIJKL` đã bị bỏ đối với **lượt nhận này**.

Sự kiện quan trọng không phải “5 byte bằng đúng buffer” mà là **ta biết payload gửi dài 12 byte trong điều kiện test**, còn receiver chỉ có 5 byte. Không giả định mọi khi thấy buffer đầy đều là do truncation.

### UDP #2 — Không nhận lại phần dư của UDP #1

Sender gửi **datagram thứ hai** chứa `xyz`. Lần `receive` tiếp theo nhận `xyz`, không nhận `FGHIJKL`. Điều này chứng tỏ một DatagramSocket không hoạt động như TCP stream reader: **ranh giới datagram là đơn vị lấy dữ liệu**.

### UDP #3 và #4 — `DatagramPacket.setLength` làm thay đổi giới hạn nhận

Backing array vẫn là `new byte[5]`. Trước #3, chương trình đặt `packet.setLength(3)`. Khi gửi `12345`, packet chỉ cho phép chép 3 byte nên nhận `123`.

Trước #4, đặt lại `packet.setLength(storage.length)` thành 5. Gửi `HELLO` thì nhận đủ 5 byte. Điểm này cho thấy **dung lượng mảng không đồng nghĩa một giới hạn nhận đã được cấu hình trong packet**, và `setLength` là cách diễn đạt chủ động bao nhiêu byte được nhận ở lần gọi tiếp theo.

Không diễn giải #3 là lỗi do tự động reuse `getLength()` sau #2: trong #3 ta **chủ động thu nhỏ** cap. Nếu không đọc source/Javadoc và không kiểm thử, suy đoán về cách reuse giữa các JDK/platform có thể dẫn đến giải thích sai.

### UDP #5 — Cắt giữa một ký tự UTF-8

Sender mã hóa text `A🙂B` bằng UTF-8:

```text
41          : "A"       (1 byte)
F0 9F 99 82 : "🙂"      (4 byte)
42          : "B"       (1 byte)
Tổng        : 6 byte
```

Receiver nhận tối đa 3 byte:

```text
41 F0 9F
```

Đây **không phải chuỗi UTF-8 hoàn chỉnh**: đã có byte đầu và byte thứ hai của emoji nhưng thiếu phần tiếp. Nếu giải mã bằng decoder có chính sách thay thế, bạn có thể thấy ký tự `�` hoặc nội dung sai; nếu decoder được đặt báo lỗi, nó sẽ từ chối malformed input. **Byte-level length và content validation phải diễn ra trước khi parse text/JSON**, vì Java `String.length()` không phải số byte UTF-8.

Đừng tin việc `new String(received, UTF_8)` không ném exception nghĩa là message đầy đủ. Overload này thường thay thế malformed sequences theo chính sách decoder. Khi yêu cầu strict, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` và xử lý `CharacterCodingException`.

### UDP #6 — Buffer đầy không chứng minh bị cắt

Đã gửi **đúng 5 byte** `abcde`, nhận buffer 5 byte, `getLength()==5` — **không cắt**. So với #1 cũng `getLength()==5` nhưng **cắt**:

| Trường hợp | Sender payload | Receiver cap | `getLength()` | Có cắt không? |
|---|---:|---:|---:|---|
| #1 | 12 | 5 | 5 | **Có** (biết từ thí nghiệm phía gửi) |
| #6 | 5 | 5 | 5 | **Không** |
| Chỉ nhìn receiver `length == cap` | **Không biết** | 5 | 5 | **Không thể quyết định** |

Một API nhận high-level như `DatagramSocket.receive` không trả kèm “original payload length” hoặc cờ truncation độc lập. Vì vậy **`received.getLength()==buffer.length` là tín hiệu cần thận trọng, không phải bằng chứng cắt**. Nếu cần biết datagram nguyên vẹn, hãy thiết kế framing/expected-length trong payload, dùng buffer đủ cho payload tối đa hợp đồng và validate toàn bộ record.

### NIO #1 và #2 — ByteBuffer cũng giữ ranh giới datagram

`DatagramChannel.receive(ByteBuffer)` đặt byte nhận vào vùng còn trống (`remaining()`) của một `ByteBuffer`. Với buffer 4 byte và `NETWORK` dài 7 byte, nhận `NETW`; 3 byte `ORK` bị bỏ.

Lần sau, sau `buffer.clear()`, sender gửi datagram khác `ok` và receiver nhận `ok`. Không có byte `ORK` nào chờ lấy tiếp. `clear()` chỉ reset vị trí/giới hạn của **buffer ứng dụng**, **không** khôi phục dữ liệu UDP đã mất.

## 8. `DatagramChannel`, ByteBuffer và vấn đề position/limit

`DatagramChannel` trong NIO hỗ trợ gửi/nhận UDP với `ByteBuffer` thay vì `DatagramPacket`. Một số điểm khác cần biết:

- `DatagramChannel.receive(dst)` trả `SocketAddress` của datagram vừa nhận; khi cấu hình nonblocking và chưa có datagram, có thể trả `null`.
- Nó chép dữ liệu vào `dst` từ **current position**; số byte chứa được là `dst.remaining()`, **không phải chỉ `dst.capacity()`**.
- Sau nhận, `position` tăng theo số bytes được chép, `limit` không đổi. Gọi `flip()` để chuyển sang đọc những bytes vừa nhận.
- Trước lượt nhận mới, gọi `clear()` để đặt position=0 và limit=capacity; nếu muốn chỉ cấp một phần, có thể thay `limit` một cách có chủ ý.
- Nếu buffer không đủ, phần dữ liệu còn lại của datagram **bị loại bỏ im lặng**. API không báo con số original datagram length.
- Nếu `dst` là read-only, `receive` có thể ném `IllegalArgumentException`; cần writable buffer.
- Trường hợp channel **connected**, `read(ByteBuffer)` đọc **một datagram từ peer đã connect**, vẫn không biến nó thành TCP stream.

### Minh họa "capacity lớn nhưng remaining nhỏ"

```java
// Mã minh họa, channel là DatagramChannel đang mở.
ByteBuffer buffer = ByteBuffer.allocate(1024);
buffer.position(1020);  // còn 4 byte từ position tới limit

SocketAddress peer = channel.receive(buffer);
// Nếu datagram 100 byte được giao, chỉ có 4 byte còn chỗ;
// các byte dư bị bỏ, dù capacity() bằng 1024.
```

Không đoán kích thước nhận bằng `capacity()` khi position không bằng 0. Trong demo, helper `receiveNio` luôn `clear()` trước nhận và `flip()` sau nhận, vì thế số byte hữu ích đọc được chính xác bằng vùng đã nhận.

### `ByteBuffer.flip` và `clear` không gọi xuống mạng

Hai method này thay đổi metadata về vùng đọc/ghi của buffer, không gửi `ACK`, không làm UDP resend và không thay bộ đệm kernel. `clear()` cũng không zero toàn bộ mảng bytes; nó chỉ cho phép ghi đè. Nếu đang lưu dữ liệu nhạy cảm, phải áp dụng security/zeroization policy riêng.

### Nonblocking cần selector/deadline

Với `channel.configureBlocking(false)`, `receive` có thể trả `null` ngay khi chưa có data. Một ứng dụng production có thể dùng `Selector` với `SelectionKey.OP_READ`, kiểm tra timeout và hủy; không nên viết vòng `while (receive()==null) {}` bận CPU. Với blocking channel, phải có lifecycle/close/cancellation thích hợp khi peer im lặng.

## 9. Phân biệt cắt do application buffer với mất do hệ điều hành và mạng

Có ba loại tình huống khác nhau:

### A. Datagram đã đến, buffer ứng dụng quá nhỏ

- Receiver gọi `receive` thành công.
- `DatagramPacket` hoặc `ByteBuffer` nhận được phần đầu trong giới hạn.
- Phần dư của **datagram ấy** bị bỏ ở bước receive.
- Không có cơ chế tự gửi lại hay lấy phần dư bằng `receive` tiếp.

Đây là điều **thực nghiệm chính** kiểm chứng trên loopback.

### B. Hàng đợi socket/OS bị đầy

Nếu receiver không đọc đủ nhanh, receive queue có thể đầy và các datagrams mới bị drop trước khi application thấy. `SO_RCVBUF` / `DatagramSocket.setReceiveBufferSize` ảnh hưởng mức buffer/queue kernel theo cơ chế/hạn chế OS; nó **không sửa lỗi packet 5 byte nhận datagram 12 byte**.

Trên Linux, có thể xem số liệu UDP errors/drop qua công cụ hệ điều hành phù hợp; tên counter và công cụ khác nhau giữa Linux, Windows, macOS. Không gán một packet không xuất hiện trong application cho "bị cắt" khi nó có thể đã **bị drop ở socket queue**.

### C. IP fragmentation, MTU hoặc mất datagram trên đường truyền

Datagram UDP vượt path MTU có thể cần IP fragmentation hoặc bị từ chối, tùy IP version, DF/PMTU và network stack. Nếu một mảnh IP mất, **toàn bộ UDP datagram có thể không được giao cho socket** sau reassembly. Đây là network-layer issue khác với **application receive buffer truncation**.

Một sender gọi `send` thành công chỉ xác nhận hoạt động gửi ở tầng socket/API theo contract; không chứng minh receiver đã nhận đủ hay application đã xử lý thành công. Không có UDP ACK chuẩn tự động như một business protocol.

## 10. MTU, độ dài datagram và cách chọn kích thước

UDP header có **8 byte**. Với IPv4 không có options, IP header thường **20 byte**; vì vậy payload UDP phải tính cả IP/UDP overhead trong kích thước gói IP. Giới hạn lý thuyết cho UDP payload trong IPv4 cơ bản là **65.507 byte** (65.535 − 20 − 8), nhưng **không nên dùng gần mức tối đa đó cho Internet**. IPv6, extension headers, đường truyền, tunnels, VPN và firewall còn đặt giới hạn khác.

Ví dụ ở đường mạng có MTU **1.500 byte** với IPv4 header 20 byte và UDP header 8 byte, một datagram không phân mảnh về mặt đơn giản cần payload không quá khoảng **1.472 byte**. Đây **không phải một số bảo đảm xuyên Internet**: VPN/tunnel có overhead, IP options và PMTU thực có thể khác. Thiết kế thực tế nên dựa trên yêu cầu và đo path/PMTU hoặc chọn size bảo thủ đã kiểm chứng với môi trường triển khai.

**Đừng nhầm hai thứ:**

- **MTU/fragmentation:** datagram có được chuyển nguyên vẹn tới socket qua network không?
- **Application receive buffer:** datagram đã tới thì `receive` có đủ chỗ để copy **toàn bộ payload** không?

Ngay cả một datagram chỉ 64 byte, không vướng MTU, vẫn **bị cắt ở API** nếu bạn nhận vào buffer dài 5 byte.

### Khi payload lớn, nên làm gì?

- Giảm kích thước **mỗi datagram** hoặc chia thông tin thành nhiều **logical messages/datagrams theo protocol của chính bạn**.
- Nếu cần phân mảnh ở tầng ứng dụng, mỗi fragment phải có **message ID, sequence/part index, total count/total bytes, checksum/integrity, deadline** và cơ chế reassembly bounded.
- Đặt giới hạn số fragments, tổng bytes, số messages dang dở, timeout, duplicate policy, authentication và chống resource exhaustion.
- Với dữ liệu dài cần truyền **đầy đủ, đúng thứ tự, reliable**, xem xét TCP/TLS hoặc một protocol đáng tin cậy phù hợp; UDP raw không tự cung cấp các bảo đảm này.
- Không chọn `SO_RCVBUF` rất lớn để che lấp design gửi datagram lớn vô hạn.

### Ảnh hưởng của checksum

UDP/IP có checksum/kiểm tra lỗi ở các mức phù hợp, nhưng checksum chỉ giúp phát hiện một số kiểu hư hại trên đường truyền; **không bảo đảm datagram được giao, không chống replay/injection, không nói buffer của ứng dụng đủ chỗ**, và không thay authentication của protocol.

## 11. Muốn biết bị cắt, phải xác định "đủ dữ liệu" theo protocol

Một datagram nhận đúng bằng buffer cap có **hai khả năng**:

1. Datagram dài chính xác cap, đã nhận đủ.
2. Datagram dài hơn cap, bị cắt.

`DatagramPacket.getLength()` không tự phân biệt hai trường hợp. Vì thế cần có **application-level record format** và validation.

Ví dụ một message tự định nghĩa:

```text
+------------+----------+----------+-------------------------+
| version(1) | type(1)  | len(2)   | payload(len bytes)      |
+------------+----------+----------+-------------------------+
              network byte order for length
```

Khi nhận, hãy:

1. Kiểm tra buffer có ít nhất **4 byte header**; nếu không, từ chối.
2. Parse `len` như unsigned 16-bit theo thứ tự byte đã quy định.
3. So sánh `len` với **maxAllowedPayload** và tổng datagram length dự kiến.
4. Kiểm tra `actualReceivedBytes == 4 + len` (nếu protocol yêu cầu một record duy nhất).
5. Decode/parse payload chỉ sau khi kiểm tra framing và các field bắt buộc.
6. Nếu thiếu byte hoặc quá size, **drop record và ghi metric**; không ghép một datagram tiếp theo vào record hiện tại nếu protocol không có fragmentation design.
7. Xác thực nội dung và nguồn gửi theo threat model; trường `len` do sender khai báo vẫn là **dữ liệu không tin cậy**, có thể sai hoặc bị giả mạo.

Đây là **minh họa giao thức**, không phải một format chuẩn được Java cung cấp. Nếu sender độc hại khai báo độ dài đúng với phần đã cắt, một check đơn lẻ vẫn có thể không phát hiện mọi thao túng; cần message authentication hoặc checksum/sequence tùy mục đích.

### Một mẫu validate length bên application

```java
// Minh họa; header dài 4 byte, n là bytes nhận thực tế.
// Chỉ tiếp tục nếu toàn bộ datagram được xác thực và schema hợp lệ.
if (n < 4) {
    throw new IllegalArgumentException("Datagram header too short");
}

int payloadLength =
        ((data[offset + 2] & 0xff) << 8)
        | (data[offset + 3] & 0xff);

if (payloadLength > maxPayload
        || n != 4 + payloadLength) {
    throw new IllegalArgumentException("Truncated/invalid datagram");
}
```

Khi thiết kế protocol thật còn phải kiểm tra offset bounds, version/type, authentication, checksum, source identity và tổng quota. `n` phải là **số byte thực sự nhận**, không phải `array.length`. Không cấp phát một mảng 65 KiB (hoặc nhiều hơn ở tầng reassembly) chỉ vì nhận được một field `length` chưa kiểm chứng.

## 12. UTF-8, String và bytes: không được dùng số ký tự làm receive capacity

UDP gửi **byte arrays**, không gửi Java Strings nguyên thủy. Một chuỗi Unicode có thể dài ít code units nhưng nhiều bytes:

```text
Java String: "A🙂B"
UTF-16 code units = 4   // A=1, emoji=2, B=1
UTF-8 bytes       = 6   // 41 F0 9F 99 82 42
```

Do đó **`String.length()` không phải size cần gửi/nhận trên UDP**. Đúng:

```java
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
DatagramPacket outbound = new DatagramPacket(
        payload, payload.length, receiverAddress, receiverPort);
sender.send(outbound);
```

Nếu nhận vào buffer nhỏ hơn `payload.length`, bạn có thể mất phần cuối của một code point. Gọi `new String(received, UTF_8)` có thể thay thế byte hỏng và tạo text nhìn như “gần đúng”; điều này nguy hiểm cho JSON, signatures, hashes và protocol framing.

**Khuyến nghị:**
- Với protocol text, decode UTF-8 **sau khi** xác minh datagram đủ và đúng structure.
- Nếu cần strict decoding, dùng `CharsetDecoder` với `onMalformedInput(CodingErrorAction.REPORT)` và `onUnmappableCharacter(CodingErrorAction.REPORT)`.
- Với protocol binary, giữ `byte[]`/`ByteBuffer`, không đổi thành String rồi đổi về bytes.
- Không nhầm UTF-8 split trong **hai UDP datagrams** với UTF-8 streaming của TCP: nếu ứng dụng chủ động chia message vào nhiều datagrams thì phải có reassembly theo sequence/order, xử lý mất/đảo thứ tự/trùng lặp trước khi decode.

## 13. Timeout, đóng tài nguyên và độ ổn định của thực nghiệm

### `DatagramSocket.setSoTimeout`

Receiver trong demo gọi:

```java
receiver.setSoTimeout(2000);
```

Điều này giới hạn thời gian chờ một `DatagramSocket.receive` khi không có datagram. Nếu quá hạn, method ném `SocketTimeoutException`; **nó không chứng minh sender chưa gửi** hoặc datagram không có trên mạng, chỉ cho biết receive không nhận datagram đúng hạn theo API.

Một socket timeout không phải tín hiệu “đã hết phần dư datagram #1”, bởi UDP không có cơ chế để request tiếp phần dư. Nếu peer không gửi datagram mới, lần receive tiếp có thể đợi tới timeout.

### `DatagramChannel` cần timeout strategy riêng

Trong ví dụ NIO, `DatagramChannel` mặc định blocking; dùng `try-with-resources` và gửi trước nhận trên loopback. Với service lâu dài, dùng nonblocking + `Selector` với deadline, hoặc cơ chế hủy/đóng channel. Đừng gán `setSoTimeout` cho một DatagramChannel rồi mong mọi blocking channel reads có cùng semantics; tích hợp với channel/selector khác Socket API truyền thống.

### Cleanup

`DatagramSocket` và `DatagramChannel` đều là closeable, nên dùng `try-with-resources`:

```java
try (DatagramSocket socket = new DatagramSocket()) {
    // send/receive UDP
}
```

Không dùng `Thread.sleep` để tạo sự đồng bộ giả trong các test. Chương trình trên gửi từng packet rồi nhận và có assertion; điều này đơn giản hóa test nhưng không ngăn mọi vấn đề scheduling/OS drop. Trong CI thường nên kiểm tra environment cho phép UDP loopback, đặt deadline phù hợp và xử lý timeout theo thông điệp lỗi dễ hiểu.

### Cách quan sát bằng packet capture

Trong môi trường test có quyền dùng Wireshark/tcpdump và phép ghi packet capture được phê duyệt:

1. Lọc traffic UDP trên loopback và ephemeral port thực tế.
2. Quan sát **payload length trên wire** của datagram #1 là 12.
3. So sánh với số byte ứng dụng báo nhận **5**.
4. Quan sát datagram #2 là `xyz`; không có datagram mới mang phần dư `FGHIJKL`.
5. Từ đó phân biệt **mạng đã nhận đầy đủ datagram**, còn **bộ đệm ứng dụng bị cắt**.
6. Nếu capture không thấy datagram hoặc thấy phân mảnh ở mạng thật, phân loại lại thành delivery/fragmentation/OS queue issue.

Đừng dùng một bản capture chứa dữ liệu thật/credentials mà không có policy retention và quyền xem phù hợp.

## 14. Sai lầm phổ biến khi gửi và nhận UDP với buffer nhỏ

| Sai lầm | Vì sao sai? | Cách làm đúng |
|---|---|---|
| “Receive 5 byte rồi receive tiếp sẽ lấy 7 byte còn lại” | UDP có ranh giới datagram; phần dư bị bỏ | Gửi datagram phù hợp cap; dùng protocol reassembly nếu cố tình chia |
| Coi UDP như TCP stream | TCP không giữ application message boundaries; UDP có | Parse một datagram như một unit, không tự nối ngẫu nhiên |
| `new String(packet.getData())` | Đọc toàn backing array, gồm bytes cũ/không thuộc packet | Dùng `offset` và `getLength()` |
| Đếm String.length để đặt byte buffer | UTF-8 có độ dài bytes khác UTF-16 chars | Tính `getBytes(UTF_8).length` hoặc protocol max |
| Nghĩ `getLength()==cap` chắc chắn có cắt | Datagram có thể vừa đúng cap | Kiểm tra expected payload/schema length |
| Nghĩ `getLength()<cap` chứng minh mọi thứ hợp lệ | Packet vẫn có thể sai schema, thiếu logical chunks | Validate protocol message |
| Hiểu `SO_RCVBUF` như `DatagramPacket` cap | Kernel receive queue khác mảng Java | Phân biệt OS queue và application buffer |
| Tăng `SO_RCVBUF` sẽ trả byte bị cắt | Dữ liệu dư của datagram đã nhận không thể lấy lại | Sửa application receive cap/protocol |
| Coi ByteBuffer.capacity là số byte sẽ nhận | `remaining = limit - position` mới là chỗ trống | `clear()`/đặt limit đúng trước nhận |
| Quên `flip()` trước đọc ByteBuffer vừa nhận | Position đang cuối vùng ghi; decode rỗng/sai | `flip()` rồi đọc `remaining` |
| Gọi `clear()` để khôi phục byte UDP đã mất | `clear()` chỉ reset metadata buffer | Gửi lại ở app protocol nếu cần |
| Coi payload > MTU luôn tới đủ | Fragmentation/drop/firewall/PMTU | Kiểm soát kích thước datagram và mạng |
| Nghĩ `send()` thành công là receiver xử lý thành công | UDP không có application ACK | Dùng ACK/sequence/checksum/retry theo protocol |
| Bỏ timeout khi receive | App có thể chờ vô hạn nếu datagram mất | `setSoTimeout`/Selector/deadline |
| Dựa vào loopback test để kết luận Internet reliable | Loopback giảm biến số network | Test loss/reorder/duplicate/MTU ngoài lab |
| Tự ghép JSON hai UDP packets bất kỳ | Không có ordering/length guarantee | Message ID, fragments, reassembly, validation |
| Decode UTF-8 ngay khi buffer đầy | Có thể cắt giữa code point | Validate bytes, strict decoder khi cần |
| Tin độ dài trong payload chưa xác thực | Có thể dẫn đến alloc/parse sai hoặc DoS | Quota, bounds và authentication |
| Lưu shared buffer qua nhiều receive async mà không copy | Data có thể bị ghi đè bởi packet sau | Ownership rõ, copy trước khi xử lý async |
| Dùng DatagramPacket đồng thời từ nhiều threads | State mutable của packet gây race | State per operation hoặc synchronization có thiết kế |
| Kết luận có byte dư vì nhận “ngắn” | Datagram gửi có thể ngắn thật hoặc đã mất ở tầng khác | Đối chiếu sender/test fixture/capture/protocol |

## 15. Bài tập mở rộng sau khi chạy demo

### Bài tập A — Thay đổi receive cap

Giữ sender gửi `ABCDEFGHIJKL`, sửa backing buffer từ 5 thành 8 byte và dự đoán:

- Datagram #1 nhận được gì?
- `getLength()` bằng bao nhiêu?
- Lần receive tiếp theo có phải phần dư `IJKL` không?
- Nếu gửi datagram dài đúng 8 byte thì `getLength()==8` có giúp phân biệt “đủ” với “bị cắt” không?

**Kỳ vọng:** nhận 8 byte đầu `ABCDEFGH`, phần dư bị bỏ; lần receive sau vẫn là datagram khác. `getLength()==8` vẫn mơ hồ nếu không biết sender payload.

### Bài tập B — Hai datagram ngắn độc lập

Gửi lần lượt `AA` và `BBB` vào receiver có buffer 100 byte. Hãy đọc hai lần `receive` và đếm số bytes mỗi lần. Vì sao không nhận một chuỗi `AABBB` như TCP stream?

**Kỳ vọng:** hai receive calls, mỗi cái một datagram có độ dài 2 và 3 byte (khi chúng được giao), không tự hợp thành 5 byte trong một callback.

### Bài tập C — NIO position

Thay `ByteBuffer.allocate(4)` thành `ByteBuffer.allocate(8)` và đặt `position(6)` ngay trước `receive`. Gửi `NETWORK`. Chỗ trống là bao nhiêu?

**Kỳ vọng:** `remaining()=2`, có thể chép `NE` rồi bỏ `TWORK`. Để nhận đủ 7 byte cần vùng trống ít nhất 7 và gọi `flip()` trước khi đọc. Khi làm lại thực nghiệm, nhớ kiểm soát position/limit trước nhận.

### Bài tập D — UTF-8 boundary

Giữ payload `A🙂B`, cho cap lần lượt 1, 2, 3, 5, 6 byte. In hex và dùng decoder strict. Ở cap nào datagram vừa đủ toàn bộ payload?

**Kỳ vọng:** cần 6 byte; cap 2/3 cắt giữa emoji, cap 5 chứa A+emoji nhưng thiếu B. “Decode được một chuỗi hợp lệ” không đồng nghĩa nhận đủ payload theo business protocol.

### Bài tập E — Nhận với payload length header

Tạo một datagram gồm 2 byte big-endian độ dài payload + payload text. Receiver luôn đọc tối đa size contract và validate `actualLength == 2 + declaredLength`. Gửi payload đủ, quá cap và field length giả.

**Kỳ vọng:** những datagrams không thỏa schema bị từ chối **trước khi parse business data**. Đừng tin declaredLength để cấp phát không giới hạn.

### Bài tập F — Mất và đảo thứ tự

Phát triển sender gửi datagrams với `sequenceNumber`, rồi cố ý drop hoặc đổi thứ tự gửi trong test harness. Receiver cần detect missing/duplicate/out-of-order, không giả định datagram boundaries bảo đảm ordering/reliability.

**Kỳ vọng:** thiết kế riêng application protocol, timeout/reassembly và phần đo error; đừng hứa UDP tự resend.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Gửi một UDP datagram 100 byte, `DatagramPacket` receive cap 10 byte. Sau receive, gọi receive tiếp có nhận 90 byte còn lại không?

**Đáp án:** Không. Khi datagram đã được nhận với cap 10, phần dư bị loại bỏ. Lần receive sau chờ datagram khác.

**Câu 2.** Vì sao UDP khác TCP về việc chia dữ liệu giữa các lần đọc?

**Đáp án:** UDP là datagram/message-oriented, giữ ranh giới datagram ở API nhận; TCP là byte stream, không giữ application message boundaries.

**Câu 3.** `DatagramPacket.getLength()==buffer.length` có chứng minh datagram bị cắt không?

**Đáp án:** Không. Nó cũng có thể là datagram dài vừa đúng buffer. Cần biết sender size hoặc validate application framing.

**Câu 4.** Vì sao `new String(packet.getData(), UTF_8)` có thể sai?

**Đáp án:** Vì nó đọc toàn backing array thay vì đúng `offset` và số byte nhận. Còn có thể decode sai nếu UTF-8 bị cắt giữa code point.

**Câu 5.** `setReceiveBufferSize(65535)` có làm mảng `new byte[5]` nhận đủ 12 byte không?

**Đáp án:** Không. `SO_RCVBUF` là socket/kernel receive queue hint; mảng/packet receive length ở application vẫn chỉ 5 byte.

**Câu 6.** Gửi `"A🙂B"` thì cần bao nhiêu byte UTF-8?

**Đáp án:** 6 byte: `41 F0 9F 99 82 42`. Java `String.length()` là 4 UTF-16 code units, không phải 6 bytes.

**Câu 7.** Với `ByteBuffer.allocate(10)` nhưng `position=8, limit=10`, nhận được tối đa mấy byte?

**Đáp án:** 2 byte. `remaining()=2`; size thật phụ thuộc remaining, không phải capacity.

**Câu 8.** `ByteBuffer.clear()` có khôi phục phần datagram đã bị cắt không?

**Đáp án:** Không. Nó chỉ reset metadata buffer cho lần đọc/ghi mới.

**Câu 9.** Khi `DatagramChannel.configureBlocking(false)`, `receive` trả `null` có nghĩa datagram trước bị cắt không?

**Đáp án:** Không. Nó báo không có datagram sẵn tại thời điểm gọi; không liên quan phần dư của datagram trước.

**Câu 10.** `DatagramSocket.setSoTimeout(2000)` bảo đảm sender sẽ gửi trong 2 giây không?

**Đáp án:** Không. Nó giới hạn thời gian blocking receive, hết hạn có thể ném `SocketTimeoutException`.

**Câu 11.** Đã nhìn thấy datagram 12 byte trong packet capture nhưng Java chỉ nhận 5. Những tầng nào cần kiểm tra?

**Đáp án:** Đặc biệt là application receive buffer cap/offset/DatagramPacket length hoặc ByteBuffer remaining. Tách khỏi kernel queue drop và IP fragmentation trước đó.

**Câu 12.** Khi gửi datagram lớn hơn path MTU, chắc chắn receiver nhận hai datagrams ứng dụng khác nhau không?

**Đáp án:** Không. IP fragmentation/reassembly không biến một UDP datagram thành hai UDP application datagrams. Nếu fragment mất, cả UDP datagram có thể không được giao.

**Câu 13.** Muốn gửi tài liệu lớn và yêu cầu nhận đủ, đúng thứ tự qua UDP cần gì?

**Đáp án:** Application-level segmentation, sequence/ID, bounded reassembly, integrity, timeout, retransmission/ACK và security; hoặc chọn reliable protocol đã có.

**Câu 14.** Gọi `receive` rồi chỉ thấy 3 byte `xyz` dù buffer có 100 byte có phải bị mất 97 byte?

**Đáp án:** Không. Datagram đó có thể chỉ dài 3 byte. Buffer là **sức chứa tối đa**, không phải số bytes bắt buộc phải nhận.

**Câu 15.** Khi reuse một packet sau một receive ngắn, có nên tự giả định receive cap lần sau luôn bằng `getLength()` trước đó không?

**Đáp án:** Không. Hãy đặt `setLength` rõ ràng theo dung lượng dự kiến hoặc tạo packet mới, dựa vào API và kiểm thử, không suy diễn implementation từ số bytes nhận trước.

## 17. Checklist áp dụng sau thực nghiệm

Trước khi triển khai UDP networking trong Java 17:

1. **Xác định max payload per datagram** theo protocol, network và MTU/PMTU cần hỗ trợ.
2. **Cấp receive buffer đủ lớn** cho datagram tối đa hợp lệ, không chỉ đủ cho text thường gặp.
3. **Phân biệt receive cap với `SO_RCVBUF`**; tăng OS queue không chữa packet/ByteBuffer nhỏ.
4. **Dùng đúng `DatagramPacket.getOffset()`, `getLength()`**; không parse toàn backing array.
5. **Nếu reuse packet**, chủ động `setLength` theo vùng trống được cho phép, tránh cap không mong muốn.
6. **Nếu dùng NIO**, kiểm tra `remaining()`, gọi `clear()` trước nhận và `flip()` trước đọc.
7. **Không kỳ vọng receive lần 2 lấy dư lần 1**; một call chỉ tiêu thụ một datagram.
8. **Không dùng `length==capacity` làm bằng chứng chắc chắn cắt**; thiết kế framing/length/checksum/schema.
9. **Đếm size bằng bytes**; với Unicode UTF-8 cần kiểm tra tính toàn vẹn trước decode.
10. **Có timeout/deadline**, tránh read block vô hạn khi packet mất; đừng nhầm timeout với EOF hay truncation.
11. **Xử lý UDP loss/reorder/duplicates** nếu nghiệp vụ yêu cầu, không coi send thành công là deliver.
12. **Giới hạn reassembly/quota** nếu chia message lớn thành nhiều datagrams, tránh DoS/memory exhaustion.
13. **Dùng try-with-resources**, không dùng chung mutable receive buffer bất cẩn giữa threads.
14. **Test trên loopback và mạng thật**, phân biệt application truncation, socket drops, MTU fragmentation và firewall.
15. **Thêm metrics/logs đúng tầng**: bytesCopied, expectedLength, datagramCount, malformedPackets, timeout, drop/reorder if observable.

**Ghi nhớ:** UDP được nhận theo **từng datagram**. Nếu datagram lớn hơn receive buffer, phần dư **bị bỏ**, không được gửi tiếp cho lần `receive` sau. `DatagramPacket.getLength()` và `ByteBuffer.remaining()` cho biết các giới hạn và số bytes quan sát ở Java, nhưng **không tự cung cấp chứng cứ datagram nguyên vẹn khi buffer đầy**. Thực nghiệm với buffer nhỏ cho thấy vì sao cần sizing, framing, byte-level validation và protocol thiết kế phù hợp.

### Tài liệu tham khảo chính thức

- [Java SE 17 — DatagramSocket: receive, send, setSoTimeout, SO_RCVBUF](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html)
- [Java SE 17 — DatagramPacket: getLength, getOffset, setLength](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html)
- [Java SE 17 — DatagramChannel: receive(ByteBuffer) và remainder discarded](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Java SE 17 — ByteBuffer: position, limit, remaining, flip, clear](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — CharsetDecoder và CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768)
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085)