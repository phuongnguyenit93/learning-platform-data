# Interest set, ready set và các cờ OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE trong Java NIO Selector

## Mục tiêu bài học

`java.nio.channels.Selector` là thành phần quan trọng của Java NIO giúp một thread theo dõi **nhiều channel có khả năng chọn (selectable channel)**, thay vì tạo một thread chặn ở mỗi socket. Trong chương trình mạng thực tế, phần dễ nhầm nhất không phải câu lệnh `select()` mà là hai tập thao tác của `SelectionKey`:

- **Interest set:** những thao tác **ứng dụng muốn nhận thông báo khả dụng** trong các lần chọn tiếp theo.
- **Ready set:** những thao tác mà **selector đã ghi nhận là sẵn sàng** trong quá trình lựa chọn gần đây.

Các cờ `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE` là các **bit mask**, không phải bốn trạng thái loại trừ lẫn nhau. Một key có thể quan tâm nhiều thao tác, và readiness chỉ báo **có thể thử I/O**, không bảo đảm toàn bộ thao tác sẽ thành công hoặc xử lý hết dữ liệu ngay lập tức.

Sau bài này, bạn có thể giải thích, dùng và debug chính xác `interestOps()`, `readyOps()`, `validOps()`, bốn cờ trên; xây event loop `select() → selectedKeys() → xử lý → remove()`; quản lý `OP_WRITE` để tránh CPU spin; và chuyển `OP_CONNECT` sang `OP_READ/OP_WRITE` sau `finishConnect()`.

Ví dụ sử dụng **Java 17+** và TCP loopback. Những điểm liên quan đến `DatagramChannel` được chỉ rõ ở phần đối chiếu; không nhầm `OP_ACCEPT` của TCP server với nhận UDP datagram.

## 1. Tư duy đúng về Selector và SelectionKey

Trong mô hình Java NIO:

```text
                      Selector
              ┌─────────────────────┐
              │ registered keys     │
              │ selected keys       │
              └──────────▲──────────┘
                         │ select()
             ready state │
                         │
       ┌─────────────────┴─────────────────┐
       │                                   │
ServerSocketChannel                  SocketChannel #1
interest: OP_ACCEPT                  interest: OP_READ
ready:    OP_ACCEPT (khi có peer)    ready:    OP_READ (khi có dữ liệu/EOF)

                                         SocketChannel #2
                                         interest: OP_CONNECT
                                         ready:    OP_CONNECT (kết nối hoàn tất/có lỗi)

                                         SocketChannel #3
                                         interest: OP_READ | OP_WRITE
                                         ready:    OP_WRITE (thường xuyên!)
```

Một `SelectableChannel` đăng ký với `Selector` tạo một `SelectionKey` đại diện cho **mối đăng ký giữa đúng channel và đúng selector**. Một channel có thể được đăng ký với các selector khác nhau, nhưng với **một selector cụ thể** chỉ có một key cho channel đó. Gọi `register(selector, ops, attachment)` khi channel đã đăng ký và key còn hợp lệ sẽ cập nhật interest operations/attachment của đăng ký ấy, không sinh một key thứ hai cho cùng cặp.

Ba tập/khái niệm khác nhau cần phân biệt:

| Khái niệm | API | Nội dung | Ai làm thay đổi |
|---|---|---|---|
| Registered-key set | `selector.keys()` | Các key đang đăng ký với selector, trừ khi bị hủy/dọn | Register, cancel/close và tiến trình dọn key |
| Selected-key set | `selector.selectedKeys()` | Những key đã được selector phát hiện có readiness và chưa bị ứng dụng loại khỏi tập selected | Selector thêm/cập nhật; **ứng dụng phải remove/clear sau xử lý** |
| Interest set của một key | `key.interestOps()` | Bit mask thao tác ứng dụng muốn theo dõi | Ứng dụng qua `interestOps(...)`/các phương thức tương ứng |
| Ready set của một key | `key.readyOps()` | Bit mask readiness selector ghi nhận | Selector khi xử lý select, không phải `interestOps(...)` |

**Ví dụ:** một `SocketChannel` kết nối xong có `interestOps() == OP_READ` nhưng `readyOps() == 0` cho tới khi selector quan sát thấy dữ liệu có thể đọc, EOF hoặc trạng thái liên quan. Ngược lại, sau khi một key đã nằm trong selected set, thay đổi interest set **không tự xóa ready set cũ**.

**Điểm quan trọng:** `readyOps()` là **snapshot trạng thái chọn**, không phải một hàng đợi các sự kiện bất biến kiểu “mỗi lần có 1 byte thì thêm một event”. Nếu bạn không đọc hết dữ liệu hoặc không remove key khỏi selected-key set, xử lý tiếp rất dễ sai hoặc lặp lại trạng thái cũ.

### Selector không biến I/O thành bất đồng bộ hoàn toàn

Event loop chuẩn dùng channel **non-blocking**. `select()` có thể chặn để **đợi readiness**, còn I/O như `read()` hoặc `write()` trên non-blocking channel phải tự xử lý kết quả tạm thời (`0`, partial read/write). Selector không tự tạo buffer vô hạn, không parse protocol, không quản lý thời hạn request và không quyết định khi nào đóng kết nối.

## 2. Bốn hằng số thao tác: giá trị bit và channel hợp lệ

Trong `java.nio.channels.SelectionKey`, bốn hằng số có giá trị được định nghĩa:

| Hằng số | Giá trị số | Bit mask (minh họa) | Ý nghĩa readiness |
|---|---:|---|---|
| `OP_READ` | `1` | `0001` | Có thể thử đọc; cũng có thể là EOF/đóng/error |
| `OP_WRITE` | `4` | `0100` | Có thể thử ghi vào buffer tầng vận chuyển |
| `OP_CONNECT` | `8` | `1000` | Non-blocking connect có thể hoàn tất hoặc báo lỗi khi finish |
| `OP_ACCEPT` | `16` | `1 0000` | Listening TCP channel có kết nối chờ accept |

**Không đoán thứ tự bit từ thứ tự tên**: `OP_WRITE` là 4, `OP_CONNECT` là 8, `OP_ACCEPT` là 16. Hãy dùng trực tiếp hằng số thay vì hard-code số.

### 2.1. Kiểu channel nào chấp nhận cờ nào?

| Channel | Thao tác có thể đăng ký | Ví dụ sử dụng |
|---|---|---|
| `ServerSocketChannel` | **`OP_ACCEPT`** | Chờ một TCP client mới |
| `SocketChannel` | **`OP_CONNECT | OP_READ | OP_WRITE`** | Mở kết nối TCP non-blocking, đọc và ghi |
| `DatagramChannel` | **`OP_READ | OP_WRITE`** | Nhận/gửi UDP datagram |
| `Pipe.SourceChannel` | **`OP_READ`** | Đọc từ pipe |
| `Pipe.SinkChannel` | **`OP_WRITE`** | Ghi vào pipe |

`ServerSocketChannel` **không** dùng `OP_READ` để nhận request bytes; nó chỉ nhận connection bằng `accept()`. Sau khi accept, bạn đăng ký **`SocketChannel` được trả về** với `OP_READ` hoặc `OP_WRITE`.

UDP không có TCP handshake hay `accept()`. Với `DatagramChannel`, `OP_READ` báo datagram có thể nhận; không đăng ký `OP_ACCEPT` hay `OP_CONNECT` cho UDP. Nếu chương trình gọi `register(selector, SelectionKey.OP_ACCEPT)` với `SocketChannel`, bộ bit không nằm trong `validOps()` và Java có thể ném `IllegalArgumentException`.

### 2.2. Kết hợp cờ bằng bitwise OR

```java
// Đoạn minh họa, giả định key còn hợp lệ và channel hỗ trợ các cờ.
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

`|` là phép OR trên từng bit. Kết quả `1 | 4 == 5` nghĩa là theo dõi **cả đọc và ghi**; không phải cộng hai trạng thái nghiệp vụ hoặc “chuyển từ đọc sang ghi”.

Kiểm tra bit:

```java
int interests = key.interestOps();
boolean wantsRead = (interests & SelectionKey.OP_READ) != 0;
boolean wantsWrite = (interests & SelectionKey.OP_WRITE) != 0;
```

Với `&`, chỉ bit chung mới được giữ lại. Không viết `interests == OP_READ` để hỏi “có quan tâm đọc không”, vì nếu interest mask là `OP_READ | OP_WRITE` thì phép so sánh bằng `OP_READ` trả `false`, dù bit read đang bật.

### 2.3. `validOps()` là hợp đồng khả năng của channel

`SelectableChannel.validOps()` trả tập bit mà channel cho phép. Trước khi xây register/interest mask động, có thể kiểm tra:

```java
// Trích đoạn minh họa: channel là SelectableChannel.
int requested = SelectionKey.OP_READ;
if ((requested & ~channel.validOps()) != 0) {
    throw new IllegalArgumentException("Unsupported operation for channel");
}
```

Mã này chỉ là đoạn minh họa, chưa có biến `channel` độc lập. Nó hữu ích khi ứng dụng có nhiều kiểu channel chung trong một event loop; đừng nhầm cờ hợp lệ với readiness đã xảy ra.

## 3. Java 17+: kiểm tra các bit và `validOps()` bằng chương trình chạy được

Tạo file **`SelectorOpsMatrix.java`**:

```java
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class SelectorOpsMatrix {
    public static void main(String[] args) throws Exception {
        System.out.println("OP_READ=" + SelectionKey.OP_READ);
        System.out.println("OP_WRITE=" + SelectionKey.OP_WRITE);
        System.out.println("OP_CONNECT=" + SelectionKey.OP_CONNECT);
        System.out.println("OP_ACCEPT=" + SelectionKey.OP_ACCEPT);
        try (ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel tcp = SocketChannel.open();
             DatagramChannel udp = DatagramChannel.open()) {
            System.out.println("Server accepts: "
                    + ((server.validOps() & SelectionKey.OP_ACCEPT) != 0));
            System.out.println("TCP supports connect: "
                    + ((tcp.validOps() & SelectionKey.OP_CONNECT) != 0));
            System.out.println("UDP supports accept: "
                    + ((udp.validOps() & SelectionKey.OP_ACCEPT) != 0));
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 SelectorOpsMatrix.java
java SelectorOpsMatrix
```

**Stdout đã được biên dịch và chạy kiểm chứng:**

```text
OP_READ=1
OP_WRITE=4
OP_CONNECT=8
OP_ACCEPT=16
Server accepts: true
TCP supports connect: true
UDP supports accept: false
```

Đây không phải giá trị được đo ngẫu nhiên từ giao diện mạng: bốn giá trị bit thuộc hợp đồng `SelectionKey`; `validOps()` phản ánh loại channel được mở, không cần server từ xa. Chương trình chưa gọi `register` hay `select`; nó chỉ xác thực **phép toán bit mask và phạm vi cờ hợp lệ**.

## 4. Interest set: chương trình muốn được thông báo về điều gì?

**Interest set** trả lời câu hỏi: “Trong vòng select tới, tôi muốn quan tâm những loại readiness nào trên channel này?”

Truy cập:

```java
int current = key.interestOps();   // Đọc bit mask hiện tại.
key.interestOps(SelectionKey.OP_READ); // Đổi toàn bộ interest mask.
key.interestOps(0);                // Tạm thời không quan tâm thao tác nào.
```

Đây là **đoạn minh họa** giả định key hợp lệ. `interestOps(0)` **không đóng socket và không hủy key**; nó chỉ ngừng đăng ký interest vào các thao tác I/O cho đến khi bật lại.

Các trường hợp thường gặp:

- `ServerSocketChannel` vừa bind/listen: đăng ký `OP_ACCEPT`.
- `SocketChannel` đang kết nối theo non-blocking mode: đăng ký `OP_CONNECT` nếu `connect(...)` trả `false`.
- TCP socket đã kết nối và đang chờ request: đăng ký `OP_READ`.
- Đã có dữ liệu outbound **đang chờ ghi**: bật thêm hoặc chuyển sang `OP_WRITE` cho đến khi buffer được đẩy đi.
- Chưa có gì cần gửi: **tắt `OP_WRITE`**, tránh tự đánh thức CPU liên tục vì socket thường có chỗ trống để ghi.

### 4.1. Thay interest set là quyết định của ứng dụng, không phải readiness mới

Giả sử một socket đã ready for read; bạn gọi:

```java
key.interestOps(SelectionKey.OP_WRITE);
```

Lệnh này **không tức khắc chuyển `readyOps()` thành `OP_WRITE`**. Ready set chỉ được cập nhật theo hoạt động select; bit read đã phát hiện có thể vẫn tồn tại trong snapshot cũ. Phải phân biệt **ý định chọn cho tương lai** và **trạng thái đã quan sát**.

Từ Java 11 có `interestOpsOr(int)` và `interestOpsAnd(int)` để thay đổi bit theo cách **atomic** mà không tự đọc–sửa–ghi mask thủ công. Với Java 17:

```java
// Minh họa: thêm OP_WRITE mà giữ nguyên các bit khác.
key.interestOpsOr(SelectionKey.OP_WRITE);

// Minh họa: gỡ riêng OP_WRITE nhưng không xóa OP_READ.
key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

Các phương thức vẫn yêu cầu key còn hợp lệ và chỉ dùng bit mà channel hỗ trợ. Lưu ý `~OP_WRITE` là bitwise NOT, thường kết hợp với AND để xóa đúng bit write. Các cập nhật atomic giúp tránh mất bit do hai thread cùng sửa `interestOps()` qua mẫu read-modify-write, nhưng **không thay thế quy tắc ownership thread của event loop**.

### 4.2. Vì sao không đăng ký `OP_WRITE` mọi lúc?

Đối với TCP socket đã kết nối, buffer gửi thường có thể nhận thêm một lượng byte nhỏ ngay cả khi bạn **chưa có dữ liệu cần gửi**. Khi `OP_WRITE` luôn ở interest set, selector có thể liên tục báo writable:

```text
select() -> OP_WRITE
ứng dụng chẳng có dữ liệu gửi -> return
select() -> OP_WRITE
ứng dụng chẳng có dữ liệu gửi -> return
... lặp lại liên tục, CPU tăng cao
```

Đây là **busy loop** do thiết kế event loop, không phải minh chứng network traffic nhiều. Quy tắc thực tế: chỉ bật `OP_WRITE` khi queue/buffer có bytes còn pending, sau khi `write()` làm buffer trống thì **tắt bit write** ngay.

## 5. Ready set: readiness là tín hiệu cho một phép thử I/O

Sau khi gọi một trong các phương thức chọn, ứng dụng có thể xem:

```java
int ready = key.readyOps();
boolean readable = (ready & SelectionKey.OP_READ) != 0;
boolean writable = key.isWritable();
boolean acceptable = key.isAcceptable();
boolean connectable = key.isConnectable();
```

Bốn convenience method kiểm tra bit readiness tương ứng trên một key còn hợp lệ. Chúng **không gửi/nhận dữ liệu** và không chứng minh rằng thao tác tiếp theo xử lý xong toàn bộ công việc.

### 5.1. Ready set không nhất thiết giống interest set

Có thể có:

```text
interestOps = OP_READ | OP_WRITE     (ứng dụng muốn cả hai)
readyOps    = OP_WRITE               (selector chỉ thấy có khả năng ghi)

hoặc:
interestOps = OP_READ                (hiện tại chỉ hỏi đọc)
readyOps    = OP_READ                (đã thấy đọc được/EOF)

sau đó ứng dụng đổi interestOps = 0
readyOps có thể vẫn giữ OP_READ trong snapshot đã chọn.
```

Không nên kỳ vọng `interestOps()==readyOps()`. Thậm chí sau khi cập nhật interest ops trong lúc selector đang chọn, thay đổi có thể **không tác động tới vòng chọn đang diễn ra**, tùy thời điểm. Đây là lý do khi một thread khác thêm outbound data thì event loop phải có phương thức **wakeup/queue công việc** phù hợp, thay vì tin rằng bất kỳ thay đổi interest mask nào cũng được quan sát ngay lập tức.

### 5.2. Những chữ “ready” dễ bị đọc sai

**`OP_ACCEPT`:** có khả năng chấp nhận kết nối mới, nhưng khi dùng `ServerSocketChannel` non-blocking, `accept()` vẫn có thể trả `null` nếu không còn connection chờ tại thời điểm gọi. Xử lý `null` bình thường; server tải cao thường accept trong vòng lặp cho đến `null`.

**`OP_CONNECT`:** non-blocking TCP connect có thể hoàn tất hoặc phát sinh lỗi. Bạn phải gọi `SocketChannel.finishConnect()` để hoàn tất quy trình/quan sát lỗi. `key.isConnectable()` **không** tự có nghĩa connection đã thành công.

**`OP_READ`:** có thể có bytes đọc được, hoặc kết thúc stream/lỗi. Trên TCP, `channel.read(buffer)` trả `>0` nếu có byte, `0` nếu hiện chưa đọc được byte nào trong non-blocking mode, hoặc `-1` khi peer kết thúc chiều gửi sau khi dữ liệu trước đó đã được đọc hết. EOF là lúc phải xử lý lifecycle, không được coi như payload rỗng và tiếp tục cố đọc vô hạn.

**`OP_WRITE`:** có thể ghi ít nhất một phần dữ liệu nếu hệ thống cho phép. `channel.write(buffer)` vẫn có thể trả `0`; nó có thể chỉ đẩy một phần `ByteBuffer.remaining()`. Không được `clear()` hoặc giải phóng buffer khi còn byte pending.

### 5.3. Selected-key set khác ready set

`selector.selectedKeys()` là tập các **key**; `key.readyOps()` là tập **bit readiness của một key**. Một key có thể sẵn sàng cho **nhiều thao tác cùng lúc**, chứ không xuất hiện hai phần tử trong selected set.

`select()` không tự động xóa toàn bộ selected-key set sau khi bạn xử lý. Cách phổ biến:

```java
// Đoạn minh họa; selector đã tạo và được dùng bởi event loop.
selector.select();

java.util.Iterator<java.nio.channels.SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    java.nio.channels.SelectionKey key = it.next();
    it.remove(); // Xóa khỏi selected set, không hủy đăng ký channel.
    if (!key.isValid()) {
        continue;
    }
    // Kiểm tra isAcceptable/isConnectable/isReadable/isWritable...
}
```

`it.remove()` chỉ **xóa selected-key entry đã xử lý**, không có nghĩa `key.cancel()`. `cancel()` mới là thao tác hủy đăng ký, và việc selector loại hẳn key khỏi các tập có thể diễn ra trong một lần selection/dọn key tiếp theo.

## 6. Java 17+: chứng minh đổi interest set không xóa ready set cũ

Ví dụ tiếp theo mở listening TCP socket trên loopback, đăng ký `OP_ACCEPT`, tạo một client kết nối vào, sau đó `select` để quan sát readiness. Khi đã nhận ready bit `OP_ACCEPT`, chương trình đặt `interestOps(0)` rồi đọc lại ready set.

**Tệp `InterestReadySnapshotDemo.java`:**

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class InterestReadySnapshotDemo {
    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {
            server.configureBlocking(false);
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
            System.out.println("Interest ACCEPT: "
                    + ((key.interestOps() & SelectionKey.OP_ACCEPT) != 0));

            client.connect(server.getLocalAddress());
            long deadline = System.nanoTime() + 3_000_000_000L;
            while (selector.selectedKeys().isEmpty() && System.nanoTime() < deadline) {
                selector.select(200);
            }
            if (selector.selectedKeys().isEmpty() || !key.isAcceptable()) {
                throw new IllegalStateException("No accept readiness");
            }
            System.out.println("Ready ACCEPT: "
                    + ((key.readyOps() & SelectionKey.OP_ACCEPT) != 0));

            key.interestOps(0);
            System.out.println("Interest is zero: " + (key.interestOps() == 0));
            System.out.println("Previous ready ACCEPT retained: "
                    + ((key.readyOps() & SelectionKey.OP_ACCEPT) != 0));

            selector.selectedKeys().remove(key);
            try (SocketChannel accepted = server.accept()) {
                System.out.println("Accepted channel: " + (accepted != null));
            }
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InterestReadySnapshotDemo.java
java InterestReadySnapshotDemo
```

**Stdout đã được biên dịch/chạy xác minh trong môi trường hỗ trợ TCP loopback:**

```text
Interest ACCEPT: true
Ready ACCEPT: true
Interest is zero: true
Previous ready ACCEPT retained: true
Accepted channel: true
```

Điều ví dụ chứng minh:

1. `key.interestOps()` ban đầu chứa `OP_ACCEPT`: đó là **interest do ứng dụng yêu cầu**.
2. Client mở TCP kết nối loopback; server channel trở nên acceptable; `select` làm key xuất hiện trong selected set và `readyOps()` có bit `OP_ACCEPT`.
3. `key.interestOps(0)` xóa **interest bit hiện tại**; nó **không sửa ngay ready bit đã quan sát**. Vì vậy bit ACCEPT trong snapshot vẫn true.
4. `selector.selectedKeys().remove(key)` xóa key khỏi **selected set**, không hủy server channel.
5. `server.accept()` lấy một TCP connection đang chờ. Vì đây là thí nghiệm cục bộ có một client và điều kiện đã quan sát, ví dụ mong đợi non-null; nếu môi trường bất thường không báo readiness đúng hạn, nó ném exception thay vì in kết quả giả.

Lưu ý: đây là một thí nghiệm có **ready set đã có trước khi đổi interest**; không nên dùng kết quả để suy ra rằng mỗi `select()` sau đó vẫn phải báo `OP_ACCEPT` khi interest set bằng `0`.

## 7. Bốn thao tác trong vòng đời một TCP server non-blocking

Một server TCP dùng Selector thường chuyển các channel qua những trạng thái:

```text
ServerSocketChannel
    bind + register(OP_ACCEPT)
             │
             ▼
      isAcceptable()
             │
          accept()
             │
             ▼
  Accepted SocketChannel ──► configureBlocking(false)
             │
             ▼
      register(OP_READ)
             │
          isReadable()
             │
        read(ByteBuffer)
             │
     đã đủ request theo framing?
            /  \
          chưa  rồi
          │      │
      giữ READ   có response cần gửi
                 │
                 ▼
            bật OP_WRITE
                 │
             isWritable()
                 │
          write(pendingBuffer)
                 │
            còn bytes?
             /    \
           còn     hết
           │        │
        giữ WRITE   tắt WRITE, giữ READ hoặc close
```

Phía **client non-blocking** có bước thêm ở đầu:

```text
SocketChannel.configureBlocking(false)
              │
     boolean connected = connect(remote)
              │
         ┌────┴────┐
       true       false
         │          │
      đã kết      register(OP_CONNECT)
      nối ngay      │
         │       isConnectable()
         │          │
         │       finishConnect()
         │          │
         └────┬─────┘
              ▼
   register/interest OP_READ
      hoặc OP_WRITE nếu đã có buffer cần gửi
```

### 7.1. `OP_ACCEPT`: chỉ dành cho listener

Chương trình server thường:

```java
// Minh họa, giả định selector và localAddress đã được tạo.
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(localAddress);
server.register(selector, SelectionKey.OP_ACCEPT);
```

Đây là **đoạn minh họa chưa độc lập** vì `selector`/`localAddress` phải được khởi tạo và giải phóng đúng cách.

Khi `key.isAcceptable()`, gọi `((ServerSocketChannel) key.channel()).accept()`. Kênh trả về đại diện **một TCP connection đã chấp nhận**; chuyển nó sang non-blocking trước khi register. Không đọc application bytes trực tiếp từ `ServerSocketChannel`.

### 7.2. `OP_CONNECT`: hoàn tất non-blocking TCP connect

Gọi `SocketChannel.connect(remote)` trên channel ở non-blocking mode có thể trả:

- `true`: TCP connection đã hoàn tất ngay; thường đăng ký `OP_READ` và/hoặc `OP_WRITE` theo nhu cầu.
- `false`: đang kết nối; đăng ký `OP_CONNECT` và đợi readiness. Khi key connectable, gọi `finishConnect()`; nếu hoàn tất, chuyển interest khỏi `OP_CONNECT` sang thao tác I/O cần thiết. `finishConnect()` cũng có thể ném `IOException` như `ConnectException`.

Không đăng ký `OP_CONNECT` cho một `SocketChannel` đã được accept từ server để “kích hoạt” connection; nó đã kết nối. Cũng không coi một key `isConnectable()` là thành công khi chưa xử lý `finishConnect()`.

### 7.3. `OP_READ`: đọc cho tới khi hết khả năng đọc hoặc đủ message

Khi `isReadable()`, bạn có thể gọi:

```java
int n = socketChannel.read(buffer);
if (n > 0) {
    // Nhận được n byte; buffer đã tiến position tương ứng.
} else if (n == 0) {
    // Non-blocking socket tạm thời chưa cho thêm byte.
} else {
    // n == -1: remote output đã kết thúc (EOF).
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Một lần readable **không nhất thiết là một message**. Ứng dụng phải dùng delimiter, length prefix hoặc parser để xác định request hoàn chỉnh. Nếu một request đến thành hai phần, hãy giữ inbound buffer hoặc parser state trong attachment.

Nếu đọc `0`, **không** chạy `while(true){read()}` vô hạn để mong có thêm dữ liệu; quay lại Selector. Nếu đọc `-1`, đóng/hủy channel theo protocol, hoặc nếu ứng dụng hỗ trợ half-close, xử lý trạng thái chiều nhận hợp lý.

### 7.4. `OP_WRITE`: chỉ bật khi có buffer pending

`ByteBuffer` duy trì `position` và `limit`. Với buffer chứa outbound data:

```java
int n = socketChannel.write(pending);
if (pending.hasRemaining()) {
    key.interestOpsOr(SelectionKey.OP_WRITE);
} else {
    key.interestOpsAnd(~SelectionKey.OP_WRITE);
}
```

Đoạn trên giả định `socketChannel`, `pending` và `key` thuộc **cùng connection** và do event loop quản lý. Một lần `write` có thể ghi một phần hoặc trả 0. Không gán lại `pending = null` khi `hasRemaining()` vẫn true, nếu không bạn làm mất phần message chưa được chuyển tới socket buffer.

Khi ghi xong, giữ `OP_READ` nếu tiếp tục chờ request. Nếu protocol quy định đóng kết nối sau response, có thể đóng channel **sau khi đã chuyển hết outbound buffer vào socket**, nhưng phải hiểu: write hoàn thành không chứng minh peer đã đọc/xử lý bytes. Để bảo đảm ứng dụng bên kia xử lý, cần ACK ở tầng ứng dụng.

## 8. Java 17+: một Selector điều phối ACCEPT, CONNECT, READ và WRITE

Ví dụ đầy đủ dưới đây chạy **một process Java** trên loopback. Nó tạo một listening `ServerSocketChannel` và một client `SocketChannel`, đều được điều phối qua **một `Selector`**. Quy tắc ứng dụng rất nhỏ:

- Client gửi chuỗi UTF-8 `PING\n`.
- Server tích lũy byte đến dấu newline, trả `PONG\n`.
- Client nhận đến newline, rồi chương trình in nội dung.

**Tất cả bốn readiness flag** đều có vai trò. Với một số hệ điều hành, `connect()` của client có thể hoàn thành ngay (`true`); khi đó không cần đợi sự kiện `OP_CONNECT`. Chương trình xử lý **cả hai trường hợp**, không ép nhận một sự kiện CONNECT không chắc xảy ra.

**Tệp `SelectorLoopbackDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class SelectorLoopbackDemo {
    private static final class State {
        final boolean client;
        final ByteArrayOutputStream received = new ByteArrayOutputStream();
        ByteBuffer pending;
        String line;

        State(boolean client) {
            this.client = client;
            if (client) pending = StandardCharsets.UTF_8.encode("PING\n");
        }
    }

    private static void onRead(SelectionKey key, State state)
            throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        ByteBuffer buffer = ByteBuffer.allocate(128);
        int count = channel.read(buffer);
        if (count < 0) throw new EOFException("EOF before complete line");
        if (count == 0) return;
        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            if (state.received.size() >= 128)
                throw new IOException("Line too long");
            state.received.write(value);
            if (value == '\n') {
                state.line = state.received.toString(StandardCharsets.UTF_8)
                        .stripTrailing();
                if (state.client) {
                    key.cancel();
                    channel.close();
                } else {
                    state.pending = StandardCharsets.UTF_8.encode("PONG\n");
                    key.interestOps(SelectionKey.OP_WRITE);
                }
                return;
            }
        }
    }

    private static void onWrite(SelectionKey key, State state)
            throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        channel.write(state.pending);
        if (!state.pending.hasRemaining()) {
            if (state.client) {
                key.interestOps(SelectionKey.OP_READ);
            } else {
                key.cancel();
                channel.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {
            InetAddress local = InetAddress.getLoopbackAddress();
            server.configureBlocking(false);
            server.bind(new InetSocketAddress(local, 0));
            server.register(selector, SelectionKey.OP_ACCEPT);

            client.configureBlocking(false);
            boolean connected = client.connect(server.getLocalAddress());
            State clientState = new State(true);
            client.register(selector,
                    connected ? SelectionKey.OP_WRITE : SelectionKey.OP_CONNECT,
                    clientState);

            State serverState = null;
            SocketChannel accepted = null;
            try {
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (clientState.line == null && System.nanoTime() < deadline) {
                    selector.select(500);
                    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) continue;
                        if (key.isAcceptable()) {
                            accepted = ((ServerSocketChannel) key.channel()).accept();
                            if (accepted != null) {
                                accepted.configureBlocking(false);
                                serverState = new State(false);
                                accepted.register(selector, SelectionKey.OP_READ,
                                        serverState);
                            }
                            continue;
                        }
                        State state = (State) key.attachment();
                        if (key.isConnectable()) {
                            SocketChannel ch = (SocketChannel) key.channel();
                            if (ch.finishConnect()) key.interestOps(SelectionKey.OP_WRITE);
                        } else if (key.isReadable()) {
                            onRead(key, state);
                        } else if (key.isWritable()) {
                            onWrite(key, state);
                        }
                    }
                }
                if (clientState.line == null || serverState == null
                        || serverState.line == null)
                    throw new IllegalStateException("Exchange incomplete");
                System.out.println("Server received: " + serverState.line);
                System.out.println("Client received: " + clientState.line);
            } finally {
                if (accepted != null) accepted.close();
            }
        }
    }
}
```

**Biên dịch và chạy với JDK 17+:**

```bash
javac --release 17 -encoding UTF-8 SelectorLoopbackDemo.java
java SelectorLoopbackDemo
```

**Stdout đã được biên dịch và thực thi kiểm chứng trên TCP loopback:**

```text
Server received: PING
Client received: PONG
```

Phân tích từng giai đoạn:

1. `Selector.open()` tạo selector. `server.configureBlocking(false)` cho phép register; `server.bind(..., 0)` dùng local loopback và port động nên không phải chọn port cố định.
2. `server.register(selector, OP_ACCEPT)` theo dõi listener. Khi acceptable, `accept()` trả client-side peer channel của server; server peer được chuyển sang non-blocking rồi đăng ký `OP_READ`.
3. Client gọi `connect()` ở non-blocking mode. Nếu hoàn thành ngay, client được đăng ký `OP_WRITE` để gửi PING; nếu chưa, nó chờ `OP_CONNECT`, gọi `finishConnect()` rồi đổi sang `OP_WRITE`.
4. Trong `onWrite`, `SocketChannel.write(ByteBuffer)` có thể ghi **không hết**. `state.pending.hasRemaining()` quyết định có cần giữ `OP_WRITE`. Khi client viết xong, interest được đổi sang `OP_READ` để chờ response; **không giữ `OP_WRITE` vô ích**.
5. Server nhận `PING\n`; dù lần read có thể trả từng byte, `State.received` tích lũy theo connection đến newline. Server đổi interest sang `OP_WRITE` để gửi `PONG\n`.
6. Server đóng accepted socket **sau khi đã ghi hết pending buffer**. Client đọc response đến newline rồi đóng connection. Trong bài này, server chủ động xử lý **một request và một response**; đây không phải production event loop có nhiều request trên connection.
7. Mỗi key trong selected set được `it.remove()` trước khi xử lý. `key.isValid()` giúp bỏ qua key bị hủy/đóng.
8. Giới hạn `128` byte cho mỗi dòng là **giới hạn cố ý của giao thức demo** để không tích lũy dữ liệu tùy ý; deadline 5 giây giúp demo không chờ vô hạn.

**Tại sao output không in từng sự kiện SELECT?** Thứ tự `ACCEPT` và `CONNECT` readiness, số lượt `READ/WRITE` và số byte trong mỗi lần gọi khác nhau theo OS/timing. In chuỗi sự kiện cụ thể rồi khẳng định stdout luôn giống sẽ sai. Hai dòng kết quả cuối đã được kiểm chứng là deterministic **khi exchange hoàn thành thành công**.

**Giới hạn của ví dụ:** chỉ một client, chỉ một request dạng dòng, trả response cố định, xử lý lỗi bằng exception, không có backpressure queue, accept burst hoặc TLS. Thực tế cần quản lý per-connection read buffer, response queue, partial write, backpressure, timeout từng connection và cleanup toàn diện.

## 9. Quản lý `OP_WRITE`, backpressure và bộ đệm đúng cách

### 9.1. Vòng đọc/ghi không phải “một event = một message”

Thường ứng dụng phải giữ trạng thái trên `SelectionKey.attachment()`, ví dụ:

```text
ConnectionState
  inboundBuffer
  parserProgress
  outboundQueue<ByteBuffer>
  currentWriteBuffer
  lastActivityTimestamp
  closingAfterWrite
```

Đây là **sơ đồ cấu trúc**, không phải code Java độc lập. Một readiness có thể phục vụ nhiều message; một message cũng có thể cần nhiều lần readiness. `OP_READ`/`OP_WRITE` báo khả năng thử I/O, còn **parser và queue của ứng dụng** quyết định xử lý logic.

### 9.2. Mẫu ghi không blocking

Khi có một response mới:

1. Encode response thành `ByteBuffer` với delimiter/length prefix theo protocol.
2. Thêm buffer vào queue của **đúng connection**.
3. Bật `OP_WRITE` nếu queue không rỗng.
4. Khi writable, ghi lần lượt từ đầu queue. Nếu `write(buffer)` trả `0` hoặc `buffer.hasRemaining()` vẫn true, giữ buffer đó và quay lại Selector.
5. Khi buffer hoàn tất, bỏ nó khỏi queue; tiếp tục buffer tiếp theo trong giới hạn công bằng theo connection.
6. Khi queue rỗng, **tắt `OP_WRITE`** để tránh spin.

Pseudocode:

```text
onResponseQueued(connection, buffer):
    queue.add(buffer)
    key.interestOpsOr(OP_WRITE)

onWritable(key):
    while queue not empty:
        current = queue.peek()
        channel.write(current)
        if current.hasRemaining():
            break
        queue.remove()

    if queue empty:
        key.interestOpsAnd(~OP_WRITE)
```

Pseudocode này nêu thuật toán **bỏ qua xử lý exception, giới hạn số byte mỗi vòng, đóng channel và đồng bộ thread**. Một server production còn phải tránh cho một connection ghi quá nhiều trong một lượt khiến các connection khác bị đói (*fairness*).

### 9.3. Backpressure

Nếu client chậm đọc, `write` có thể ghi ít hoặc 0. Khi đó **outbound queue tăng** nếu ứng dụng tiếp tục tạo response không giới hạn. Selector không tự làm queue an toàn. Hãy quy định:

- Dung lượng tối đa theo connection và tổng server.
- Ngưỡng tạm dừng đọc (`OP_READ`) khi outbound queue quá đầy, nếu giao thức cho phép.
- Cơ chế timeout, từ chối hoặc đóng peer quá chậm.
- Giới hạn tổng bytes được ghi trong mỗi lượt để không chiếm toàn bộ event-loop thread.

**Đừng xóa OP_READ một cách mù quáng** nếu còn phải nhận tín hiệu protocol/control hoặc giải phóng tài nguyên. Hành vi backpressure phải theo hợp đồng ứng dụng.

### 9.4. Ghi từ thread khác và `selector.wakeup()`

Trong server có worker thread tạo response, cách dễ kiểm soát là worker **đưa một tác vụ vào concurrent queue**, gọi `selector.wakeup()`, rồi để **thread event loop** duy nhất sửa attachment, queue và interest set:

```text
Worker thread:
    completedResponses.add(taskForConnection)
    selector.wakeup()

Selector thread:
    select()
    drain completedResponses
    enqueue outbound buffers
    enable OP_WRITE for relevant keys
    process selected keys
```

`Selector.wakeup()` khiến một thao tác chọn đang chờ trả về sớm (hoặc ảnh hưởng lần select tiếp theo theo hợp đồng API), **không tự làm channel readable/writable**. Cần drain work queue thực tế và xử lý readiness bình thường. Không dùng `wakeup()` để tạo fake `OP_READ` event.

## 10. Những lỗi sử dụng Selector thường gặp

### Lỗi 1: hiểu sai interest set và ready set

`interestOps()` là **bit mask đặt yêu cầu theo dõi**. `readyOps()` là **readiness selector đã thấy**. Thay interest mask không đồng nghĩa ready set đổi ngay. Dùng `key.isReadable()` hoặc bitwise `readyOps & OP_READ` sau khi xử lý select, không dùng `key.interestOps() & OP_READ` làm bằng chứng socket có byte.

### Lỗi 2: đăng ký cờ không hợp lệ

`ServerSocketChannel` chỉ hỗ trợ `OP_ACCEPT`; `SocketChannel` hỗ trợ `OP_CONNECT/READ/WRITE`; `DatagramChannel` hỗ trợ `OP_READ/WRITE`. Kiểm tra `channel.validOps()` nếu code chọn cờ động. Invalid interest mask gây `IllegalArgumentException`, không phải network timeout.

### Lỗi 3: quên chuyển channel về non-blocking

Trước `channel.register(selector, ops)`, channel phải ở **non-blocking mode**. Nếu còn blocking, `register` có thể ném `IllegalBlockingModeException`. Channel đã đăng ký với selector cũng không thể tự ý đổi sang blocking mode khi đăng ký còn hiệu lực. Cần thiết kế rõ I/O lifecycle.

### Lỗi 4: `OP_CONNECT` đã ready nhưng không gọi `finishConnect()`

Phát hiện `key.isConnectable()` không đủ. Với TCP socket đang connecting, gọi `finishConnect()` và xử lý `IOException`. Khi connection hoàn tất, bỏ `OP_CONNECT` và bật `OP_READ/OP_WRITE` theo nhu cầu; nếu không, ứng dụng có thể giữ state sai hoặc thử đọc/ghi khi connect chưa xong.

### Lỗi 5: giữ `OP_WRITE` khi chẳng có gì cần ghi

Nếu không có outbound data nhưng vẫn luôn đăng ký `OP_WRITE`, selector có thể liên tục thấy socket writable, gây **CPU spin**. Chỉ bật write interest khi pending buffer/queue không trống, và tắt ngay khi hết.

### Lỗi 6: nhầm `OP_READ` với “có sẵn nguyên message”

TCP là **byte stream**; read có thể trả 0, một phần message, nhiều message dính nhau hoặc -1 khi EOF. Không được lấy độ dài của một lần `read` làm ranh giới message. Thiết kế framing (newline, length prefix hoặc parser), giới hạn kích thước và xử lý read 0/EOF riêng.

### Lỗi 7: quên remove selected key sau xử lý

`selector.selectedKeys()` không được hệ thống tự clear như một “fresh event list” sau mỗi lượt. Dùng `Iterator.remove()` để loại key đã xử lý, rồi đợi chọn readiness mới. `selectedKeys().clear()` cũng có thể dùng khi thích hợp, nhưng phải tránh xóa key trước khi công việc cần thiết đã xử lý.

### Lỗi 8: quên xử lý key bị cancel

Key có thể mất hiệu lực khi channel đóng, selector đóng hoặc gọi `key.cancel()`. Kiểm tra `key.isValid()` trước khi truy cập state và bắt/handle `CancelledKeyException` ở ranh giới phù hợp. Cancellation được xử lý theo lifecycle của selector; không giả định mọi tập key lập tức trống ngay trong cùng dòng code.

### Lỗi 9: lầm tưởng `select()` trả số key đang chờ xử lý

Giá trị return của `selector.select()` mô tả các key mà ready operation set được cập nhật trong selection operation, **không phải kích thước cố định của `selectedKeys()` sau mọi lần gọi**. Với selected keys tồn tại từ lượt trước, số trả về và kích thước tập selected có thể khác. Đọc `selectedKeys()` và remove đúng cách.

### Lỗi 10: `select(0)` được hiểu là “không chờ”

Trong `Selector.select(long timeout)`, **timeout 0** có nghĩa đợi **không giới hạn** cho đến khi có selected readiness, wakeup hoặc yếu tố làm nó trở về theo API; không phải polling ngay. Nếu cần **không block**, dùng `selectNow()`. Đặt timeout dương để có điểm kiểm tra deadline/tác vụ khác theo ứng dụng.

### Lỗi 11: quên fairness và timeout nghiệp vụ

Một connection có thể liên tục writable hoặc readable; event loop xử lý vô hạn một key sẽ khiến các channel khác chờ. Giới hạn bytes/số message xử lý mỗi lượt; cập nhật last-activity/deadline, chia nhỏ công việc nặng ra worker pool và tránh blocking DB/HTTP call ngay trên selector thread.

### Lỗi 12: đóng socket như đóng một “sự kiện” đã xử lý

`it.remove()` chỉ xóa key khỏi selected set. `key.cancel()` hủy đăng ký. `channel.close()` đóng channel (và làm key không còn sử dụng được). Không thay ba thao tác này cho nhau. Khi đóng connection, phải giải phóng buffer, bỏ task pending và xử lý các callback đang chờ theo chính sách.

## 11. Quy trình chẩn đoán khi event loop không hoạt động

### 11.1. Ghi log đủ ngữ cảnh, không spam từng lượt chọn

Mỗi sự kiện quan trọng nên log:

```text
timestamp | channelId | remoteAddress | interestOps | readyOps
          | event=ACCEPT/CONNECT/READ/WRITE/CLOSE/ERROR
          | bytesRead | bytesWritten | queueBytes | reason
```

Vì `OP_WRITE` có thể xảy ra rất thường xuyên, không log chi tiết mọi lần writable trong production; tổng hợp metrics hoặc log có điều kiện để tránh làm hệ thống chậm hơn. Khi debug, cho phép bật log chi tiết trong khoảng thời gian có kiểm soát.

### 11.2. Ma trận quan sát

| Hiện tượng | Khả năng thường gặp | Bước kiểm tra |
|---|---|---|
| `register` báo `IllegalBlockingModeException` | Chưa `configureBlocking(false)` | Kiểm tra thứ tự open → non-blocking → register |
| `register` báo `IllegalArgumentException` | Dùng OP không thuộc `validOps()` | In `validOps`, loại channel và mask |
| Server không accept dù có client | Listener không bind/register đúng hoặc chưa xử lý selected keys | Xem `OP_ACCEPT`, `isAcceptable`, `accept()==null`, bind port |
| Client luôn ở trạng thái connecting | Bỏ quên `finishConnect()` hoặc connect thực sự gặp lỗi | Kiểm tra `OP_CONNECT`, kết quả `finishConnect` và exception |
| CPU gần 100%, traffic ít | Giữ `OP_WRITE` liên tục, hoặc polling `selectNow` không nghỉ | In interest mask, queue pending và số lượt select |
| `isReadable()==true` nhưng `read()==-1` | Remote đã đóng chiều gửi | Xử lý EOF, không tạo message rỗng giả |
| `isWritable()==true` nhưng write được một phần | Buffer/hệ thống có giới hạn tức thời | Giữ position và `OP_WRITE` cho phần còn lại |
| Client đã gửi nhưng handler không chạy | Đọc chưa đủ message/framing, chưa parse, hoặc key chưa remove | Theo dõi bytes, parser state, selected set |
| Đã đổi `interestOps` nhưng selector thread không phản hồi sớm | Thay đổi trong lúc `select` đang chờ | Dùng công việc queue + `selector.wakeup()` |
| Cả server chậm vì một client | Handler blocking hoặc vòng xử lý không công bằng | Đo thời gian event loop, tách công việc nặng |
| `CancelledKeyException` bất thường | Truy cập key sau close/cancel hoặc race | Quản lý lifecycle và ownership |
| Chỉ một client hoạt động | Dùng state/buffer chung cho nhiều channel | Mỗi key cần attachment/queue riêng |

### 11.3. Phân biệt lỗi application với lỗi mạng

`OP_CONNECT` có thể ready ngay cả khi `finishConnect()` cho biết kết nối lỗi; đây là tín hiệu tầng TCP, không phải “Selector hỏng”. `OP_READ` có thể ready khi remote đóng output; kiểm tra `read()==-1` trước khi kết luận parser có vấn đề. Nếu có dữ liệu đọc được nhưng application không xử lý, hãy kiểm tra **framing, buffer position/limit, thread state và exception path** trước khi quy lỗi cho firewall.

Selector không giải quyết tất cả lỗi connection: DNS có thể sai, TCP port có thể bị chặn, server có thể đứt hoặc ứng dụng có thể không xử lý response. Tách rõ **readiness**, **I/O result**, và **business result**.

### 11.4. Một checklist review nhanh

- [ ] Channel đã non-blocking trước register.
- [ ] `validOps()` có chứa những bit interest được yêu cầu.
- [ ] Server listener dùng `OP_ACCEPT`; accepted channel dùng `OP_READ/WRITE`.
- [ ] Non-blocking client xử lý cả `connect()==true` và `connect()==false` + `finishConnect()`.
- [ ] Sau `select`, duyệt `selectedKeys()` bằng iterator và remove từng key.
- [ ] Kiểm tra `key.isValid()` và cleanup khi close/cancel/error.
- [ ] `read` có xử lý `>0`, `0`, `-1` và framing.
- [ ] `write` giữ nguyên buffer position/remaining khi ghi một phần.
- [ ] `OP_WRITE` chỉ bật lúc có pending data; tắt khi queue rỗng.
- [ ] Event loop có timeout/deadline, không làm blocking công việc nặng.
- [ ] Nếu cross-thread thay interest/queue, có cơ chế đồng bộ + `selector.wakeup()`.
- [ ] Có test gửi một request bị chia nhỏ/response dài để phát hiện lỗi framing và partial I/O.

## 12. Tự kiểm tra

**Câu 1.** `interestOps()==OP_READ`, `readyOps()==0`. Có thể kết luận “có dữ liệu để đọc” không?

**Đáp án:** Không. Ứng dụng **muốn** theo dõi đọc, nhưng selector chưa ghi nhận readiness trong ready set đang xem.

**Câu 2.** Sau khi `key.isAcceptable()`, bạn gọi `accept()` và nhận `SocketChannel`. Đăng ký `OP_ACCEPT` cho channel vừa accept có đúng không?

**Đáp án:** Không. `OP_ACCEPT` thuộc `ServerSocketChannel`, còn accepted `SocketChannel` hỗ trợ `OP_READ/WRITE`; cần `configureBlocking(false)` rồi đăng ký phù hợp.

**Câu 3.** `SocketChannel.connect(remote)` trả `false`. Nên chuyển ngay sang `OP_READ` hay đăng ký `OP_CONNECT`?

**Đáp án:** Đăng ký `OP_CONNECT` và đợi connectable; gọi `finishConnect()`, chỉ chuyển sang read/write khi connect thực sự hoàn tất.

**Câu 4.** `key.isWritable()==true` có nghĩa toàn bộ response 2 MB sẽ được ghi trong một lần không?

**Đáp án:** Không. Non-blocking `write` có thể ghi một phần hoặc 0; giữ `ByteBuffer.position` và bật `OP_WRITE` cho đến khi gửi xong.

**Câu 5.** Tại sao CPU tăng khi chỉ có 5 client nhàn rỗi nhưng `OP_WRITE` được bật cho mọi channel?

**Đáp án:** Socket thường writable ngay cả khi không có bytes cần gửi. Selector liên tục thông báo writable, tạo busy loop. Tắt `OP_WRITE` khi outbound queue rỗng.

**Câu 6.** `key.interestOps(0)` rồi `key.readyOps()` vẫn còn bit `OP_ACCEPT`. Có phải Java lỗi?

**Đáp án:** Không. Interest set mới không tự xóa ready set đã được ghi nhận trước đó.

**Câu 7.** Sau khi xử lý key, `it.remove()` có đóng socket không?

**Đáp án:** Không. Nó chỉ loại key khỏi **selected-key set**; không cancel registration hay close channel.

**Câu 8.** `selector.select(0)` có phải cách poll ngay giống `selectNow()` không?

**Đáp án:** Không. Timeout 0 trong `select(long)` là yêu cầu chờ không giới hạn theo hợp đồng; dùng `selectNow()` để chọn không block.

**Câu 9.** `key.isReadable()` nhưng `read(buffer)==-1`. Tình trạng gì?

**Đáp án:** TCP input đã tới EOF (remote kết thúc chiều gửi sau dữ liệu trước đó). Đây không phải message rỗng; phải xử lý lifecycle/protocol.

**Câu 10.** Tại sao `selectedKeys().size()` không được mặc định bằng return value `select()`?

**Đáp án:** Selected-key set có thể giữ key từ các vòng trước; giá trị trả về của select mô tả những key được cập nhật ready-operation set trong lần chọn đó, không phải số lượng key còn tồn trong tập selected.

**Câu 11.** `OP_READ | OP_WRITE` có giá trị bao nhiêu? Nếu muốn chỉ kiểm tra có bật read thì dùng phép toán nào?

**Đáp án:** `1 | 4 = 5`; dùng `(ops & SelectionKey.OP_READ) != 0`.

**Câu 12.** Một worker thread thêm response vào outbound queue trong khi selector thread đang đợi. Cách phối hợp nào phù hợp?

**Đáp án:** Dùng concurrent work queue, `selector.wakeup()`, rồi event-loop thread lấy task, thêm buffer và bật `OP_WRITE`. `wakeup` không tự cung cấp readiness giả.

## 13. Kết luận

- **Interest set (`interestOps`)** = ứng dụng muốn theo dõi thao tác nào; **ready set (`readyOps`)** = selector đã thấy thao tác nào có thể thử làm I/O. Chúng không phải một.
- **`OP_ACCEPT`** cho TCP listener; **`OP_CONNECT`** cho TCP client non-blocking đang kết nối; **`OP_READ`** cho channel có thể thử đọc; **`OP_WRITE`** cho channel có thể thử ghi.
- `SelectionKey` là **bit mask**; dùng `|` để kết hợp, `&` để kiểm tra, `validOps` để biết channel hỗ trợ gì.
- Một event loop là chu trình **select → lấy selected keys → remove từng key → xử lý I/O → cập nhật interest mask**.
- Readiness không bảo đảm hoàn tất: `accept()` có thể trả null; `finishConnect()` có thể lỗi; `read()` có thể trả 0 hoặc -1; `write()` có thể ghi một phần.
- **Chỉ theo dõi `OP_WRITE` khi thực sự có pending bytes**, nếu không event loop dễ dùng CPU cao vô ích.
- Với ứng dụng thực, phải quản lý connection state, framing, read/write buffers, timeout, backpressure, thread ownership và cleanup; Selector chỉ hỗ trợ phát hiện I/O readiness.

### Tài liệu tham khảo chính thức (Java 17)

- [`SelectionKey` — interest set, ready set, valid operations, OP flags](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [`Selector` — registered keys, selected keys, select(), selectNow(), wakeup()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [`SelectableChannel` — configureBlocking(), register(), validOps()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [`ServerSocketChannel` — non-blocking accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [`SocketChannel` — non-blocking connect/finishConnect/read/write](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [`DatagramChannel` — supported operations for UDP](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
