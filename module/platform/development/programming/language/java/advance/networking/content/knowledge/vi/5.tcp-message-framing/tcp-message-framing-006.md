# Byte order và truyền số nguyên bằng DataInputStream hoặc ByteBuffer trong thông điệp TCP

## 1. Mục tiêu và vấn đề cần giải quyết

TCP chỉ truyền **một dãy byte có thứ tự**, chứ không tự hiểu “đây là một số nguyên”, “đây là header” hoặc “đây là một thông điệp”. Khi Java gửi số nguyên nhiều byte, hai phía cần thống nhất **độ rộng số**, **byte order** (thứ tự byte), **kiểu có dấu hay không dấu** và **cách xác định ranh giới thông điệp**. Nếu thiếu một trong các quy ước này, hai chương trình có thể kết nối TCP thành công nhưng diễn giải sai dữ liệu.

Hãy xét số nguyên 32-bit `0x01020304`. Cùng một số, hai cách ghi 4 byte phổ biến là:

~~~text
Giá trị logic: 0x01020304

Big-endian:     01 02 03 04   (byte có trọng số lớn nhất đi trước)
Little-endian:  04 03 02 01   (byte có trọng số nhỏ nhất đi trước)
~~~

Một đầu gửi `01 02 03 04`, đầu kia đọc nó theo little-endian sẽ thu được `0x04030201`, một giá trị **khác hẳn**, dù không mất hay đảo thứ tự byte nào trên đường truyền.

Sau bài này, bạn cần:

- Giải thích được big-endian/little-endian, “network byte order” và phạm vi trách nhiệm của TCP.
- Biết `DataOutputStream.writeInt()` / `DataInputStream.readInt()` luôn dùng big-endian; biết `ByteBuffer.order(...)` mặc định và cách chọn little-endian.
- Mã hóa, giải mã số `short`, `int`, `long` theo kích thước cố định; phân biệt byte có dấu/không dấu.
- Kết hợp số nguyên với **length-prefix framing**, đọc đủ byte kể cả khi TCP chia dữ liệu thành nhiều lần đọc.
- Phát hiện lỗi sai byte order, thiếu byte, chiều dài không hợp lệ, đọc nhầm trạng thái buffer và giới hạn tài nguyên.

Bài tập trung vào truyền **số nguyên nhị phân** trong các thông điệp TCP; đây là nền tảng trước khi học các giao thức ứng dụng phức tạp.

## 2. Byte order là gì và vì sao cần quy định?

### 2.1. Byte không tự mang kiểu dữ liệu

Mỗi byte có 8 bit và giá trị thô 0–255. Một `int` của Java có **32 bit = 4 byte**; `short` có 16 bit = 2 byte; `long` có 64 bit = 8 byte. Khi truyền qua `OutputStream` hoặc socket, các bit của giá trị phải được biểu diễn dưới dạng một dãy byte.

Với giá trị `0x01020304`, bốn byte theo thứ tự trọng số là:

| Byte | Hex | Trọng số trong số nguyên 32-bit |
| --- | --- | --- |
| B3 (cao nhất) | `01` | `0x01 × 2^24` |
| B2 | `02` | `0x02 × 2^16` |
| B1 | `03` | `0x03 × 2^8` |
| B0 (thấp nhất) | `04` | `0x04 × 2^0` |

Trong **big-endian**, byte B3 đi trước: `01 02 03 04`. Trong **little-endian**, B0 đi trước: `04 03 02 01`. Thứ tự này áp dụng cho **byte của trường nhiều byte**, không nói về việc bit bên trong từng byte chạy ngược nhau. Đối với **một byte**, không có khác biệt endian.

### 2.2. Network byte order có phải tính năng của TCP?

Trong nhiều giao thức mạng chuẩn, “**network byte order**” nghĩa là **big-endian** đối với các trường số nguyên nhiều byte. Ví dụ, những trường nhị phân theo đặc tả Internet có thể quy định gửi byte trọng số lớn nhất trước.

Tuy nhiên, cần phân biệt:

- **TCP** chỉ cung cấp byte stream; nó giữ thứ tự của các byte được gửi, **không tự chuyển byte order** trong payload ứng dụng.
- **Giao thức ứng dụng** mới quyết định header length 4 byte dùng big-endian, payload số dùng little-endian hay ngược lại.
- **CPU của máy gửi/nhận** có thể có native byte order khác nhau; đừng dùng native order làm quy ước wire format nếu muốn các client tương tác ổn định.

Giao thức không sai chỉ vì chọn little-endian. Sai ở chỗ **không công bố hoặc không thống nhất** cách giải mã. Ví dụ một giao thức tự thiết kế hoàn toàn có thể quy định length là big-endian và dữ liệu đo đạc là little-endian; hai phía phải làm đúng từng trường.

### 2.3. Hình dung sự khác biệt trên cùng 4 byte

~~~text
Wire bytes:     01 02 03 04
                │  │  │  │
Giải mã BE:     └───────────→ 0x01020304 = 16909060
Giải mã LE:     └───────────→ 0x04030201 = 67305985

Wire bytes:     04 03 02 01
Giải mã LE:                  → 0x01020304 = 16909060
Giải mã BE:                  → 0x04030201 = 67305985
~~~

Đây là khác biệt **biểu diễn**. Khi đã giải mã về một `int` Java, giá trị logic được sử dụng bình thường; byte order lại quan trọng lúc mã hóa giá trị trở về byte.

## 3. DataOutputStream và DataInputStream: số nguyên theo big-endian

### 3.1. Quy tắc của `writeInt()` và `readInt()`

`DataOutputStream` bọc một `OutputStream` và có các phương thức ghi kiểu nguyên thủy Java. `writeInt(int v)` ghi **đúng 4 byte**, byte cao trước, tức **big-endian**. `DataInputStream.readInt()` đọc **đủ 4 byte** và ghép theo cùng quy ước big-endian thành `int` có dấu.

Ví dụ minh họa:

~~~java
// Đoạn code minh họa; cần import java.io.*
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
try (DataOutputStream out = new DataOutputStream(bytes)) {
    out.writeInt(0x01020304);
}

byte[] encoded = bytes.toByteArray(); // [0x01, 0x02, 0x03, 0x04]
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(encoded))) {
    int decoded = in.readInt();        // 0x01020304
}
~~~

Đoạn trên là mã minh họa trong phương thức có thể ném `IOException`, không phải chương trình độc lập. Nó dùng bộ nhớ để thấy chính xác byte trước khi áp dụng với TCP.

Những phương thức thường dùng:

| Phương thức | Độ rộng | Byte order / cách hiểu |
| --- | --- | --- |
| `DataOutputStream.writeByte(int)` | 1 byte thấp | Không có khác biệt endian |
| `writeShort(int)` / `readShort()` | 2 byte | Big-endian, khi đọc trả `short` có dấu |
| `writeInt(int)` / `readInt()` | 4 byte | Big-endian, khi đọc trả `int` có dấu |
| `writeLong(long)` / `readLong()` | 8 byte | Big-endian, khi đọc trả `long` có dấu |
| `DataInputStream.readUnsignedByte()` | 1 byte | Trả `int` trong khoảng 0–255 |
| `DataInputStream.readUnsignedShort()` | 2 byte | Big-endian, trả `int` trong khoảng 0–65535 |
| `DataInputStream.readFully(byte[])` | Theo độ dài mảng | Đọc đủ số byte, hoặc ném `EOFException` nếu hết luồng sớm |

`DataInputStream` và `DataOutputStream` **không có tùy chọn đổi sang little-endian** cho `readInt()`/`writeInt()`. Nếu giao thức yêu cầu little-endian, dùng `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` hoặc tự mã hóa rõ từng byte; đừng nghĩ `ByteOrder.nativeOrder()` sẽ đổi được `DataOutputStream`.

### 3.2. Điều gì xảy ra nếu chưa nhận đủ 4 byte?

`readInt()` sẽ chờ đến khi đọc đủ 4 byte, gặp EOF hoặc lỗi I/O theo chính sách timeout của luồng/socket. Nếu EOF đến sau 1, 2 hay 3 byte, `readInt()` ném `EOFException`. Nó **không** trả một số nguyên “một phần”. Đó là lý do `readInt()` thích hợp cho header 4 byte trên TCP.

Quan trọng: `InputStream.read(byte[4])` đơn lẻ **không** có bảo đảm đọc được cả 4 byte trong một lần. Trái lại, `DataInputStream.readFully(byte[])` lặp đọc cho đủ mảng và ném lỗi nếu EOF quá sớm. Với một frame, nên dùng `readInt()` cho prefix và `readFully(payload)` cho phần dữ liệu có độ dài đã xác thực.

Nếu đã có `DataInputStream` bọc socket, không tạo thêm một `BufferedReader` hay stream đọc độc lập cùng socket để xử lý frame khác: tầng buffering có thể đọc trước, khiến các wrapper tranh byte của nhau.

### 3.3. Ghi số vào socket và `flush()`

~~~java
// socket đã connect; ví dụ minh họa, không phải chương trình độc lập.
DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(socket.getOutputStream()));
out.writeInt(0x01020304);
out.flush();
~~~

`writeInt()` chuyển giá trị thành 4 byte big-endian. `flush()` bảo đảm buffer ở tầng Java chuyển dữ liệu xuống luồng dưới, vì `BufferedOutputStream` có thể giữ byte chưa gửi. Nó **không** xác nhận peer đã nhận hay xử lý số; muốn điều đó cần phản hồi ở tầng ứng dụng.

Lưu ý `DataOutputStream.writeUTF()` dùng biến thể **modified UTF-8** và prefix độ dài riêng; không liên quan đến quy tắc 4 byte cố định của `writeInt()` và không tự động là wire format UTF-8 chung cho nhiều ngôn ngữ.

## 4. ByteBuffer: chủ động chọn BIG_ENDIAN hoặc LITTLE_ENDIAN

### 4.1. Tạo và sử dụng ByteBuffer

`java.nio.ByteBuffer` lưu các byte có thứ tự đọc/ghi, đồng thời có các phương thức `putInt()`/`getInt()`, `putShort()`/`getShort()`, `putLong()`/`getLong()`. **Byte order mặc định của một ByteBuffer mới là BIG_ENDIAN.** Để thay đổi, gọi `order(ByteOrder.LITTLE_ENDIAN)`.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

int value = 0x01020304;

ByteBuffer big = ByteBuffer.allocate(Integer.BYTES);
big.putInt(value); // Mặc định BIG_ENDIAN: 01 02 03 04

ByteBuffer little = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.LITTLE_ENDIAN);
little.putInt(value); // LITTLE_ENDIAN: 04 03 02 01
~~~

Đây là hai đoạn ghi độc lập vào buffer **4 byte**. Với buffer kiểu heap được tạo từ `allocate(...)`, `array()` có thể dùng để truy cập mảng byte nền; với direct buffer do `allocateDirect(...)` tạo, không nên giả định `array()` được hỗ trợ. Nếu cần gửi byte tổng quát, có thể lấy byte qua `get(byte[])` sau khi `flip()`.

Khi nhận 4 byte từ mạng, đặt order **trước khi đọc số**:

~~~java
byte[] raw = {4, 3, 2, 1};
int decoded = ByteBuffer.wrap(raw)
        .order(ByteOrder.LITTLE_ENDIAN)
        .getInt();
// decoded == 0x01020304
~~~

`ByteBuffer.order(ByteOrder.BIG_ENDIAN)` dùng khi giao thức ghi high byte trước; `ByteBuffer.nativeOrder()` mô tả thứ tự byte bản địa của nền tảng, nhưng **không phải mặc định giao thức**. Hãy khai báo byte order của wire format bằng hằng rõ ràng, không lệ thuộc phần cứng.

### 4.2. Position, limit, flip và BufferUnderflowException

`ByteBuffer` có ba khái niệm:

- **capacity:** tổng số byte có thể chứa.
- **position:** vị trí thao tác tiếp theo.
- **limit:** giới hạn cho phép của những byte đang đọc/ghi.

Sau `putInt()`, position tăng 4. Nếu muốn đọc lại từ **cùng buffer**, phải chuyển từ pha ghi sang pha đọc bằng `flip()`:

~~~java
ByteBuffer buf = ByteBuffer.allocate(4)
        .order(ByteOrder.LITTLE_ENDIAN);

buf.putInt(0x01020304);      // position = 4, limit = 4
buf.flip();                  // position = 0, limit = 4
int number = buf.getInt();   // number == 0x01020304
~~~

Nếu quên `flip()`, `getInt()` có thể ném `BufferUnderflowException` vì không còn 4 byte đọc được từ position hiện tại. Ngược lại, `putInt()` vào buffer không đủ chỗ ném `BufferOverflowException`. Những lỗi buffer này khác với `EOFException` và `SocketTimeoutException` của luồng mạng.

`clear()` chỉ đặt lại chỉ số, **không xóa byte thực**; `compact()` giữ lại phần byte chưa đọc cho lần ghi tiếp theo. Trong NIO non-blocking, `SocketChannel.read(ByteBuffer)` có thể đọc ít byte hơn yêu cầu hoặc trả 0; `SocketChannel.write(ByteBuffer)` cũng có thể ghi được ít byte hơn số còn lại. Phải duy trì trạng thái `position`, `limit` và `hasRemaining()` qua nhiều lượt xử lý, dùng `Selector` để đợi khi chưa sẵn sàng thay vì quay vòng bận CPU.

### 4.3. DataInputStream và ByteBuffer tương đương khi cùng order

Với cùng 4 byte `01 02 03 04`:

~~~text
new DataInputStream(...).readInt()              -> 0x01020304
ByteBuffer.wrap(bytes).getInt()                 -> 0x01020304
ByteBuffer.wrap(bytes).order(BIG_ENDIAN)
                      .getInt()                 -> 0x01020304

ByteBuffer.wrap(bytes).order(LITTLE_ENDIAN)
                      .getInt()                 -> 0x04030201
~~~

Sự tương đương chỉ đến từ **cùng quy ước byte order**, không phải hai API có cùng cách đọc từ TCP. `DataInputStream` trực tiếp đọc đủ byte từ luồng; `ByteBuffer.getInt()` chỉ đọc **các byte đã có trong buffer**, và ném underflow nếu chưa đủ. Khi dùng `ByteBuffer` trên socket, việc gom đủ byte là trách nhiệm của lớp đọc mạng/state machine.

## 5. Truyền số nguyên trong một thông điệp TCP: framing + endian

### 5.1. Vì sao phải có ranh giới thông điệp?

TCP bảo đảm byte stream có thứ tự trong kết nối, nhưng không bảo tồn ranh giới mỗi lần `write()`. Nếu gửi hai số `int` liên tiếp, bên nhận không thể giả định hai lần `read(byte[])` sẽ tương ứng với hai số. Có thể xảy ra:

~~~text
Bên gửi gọi write() chứa 8 byte:  01 02 03 04 05 06 07 08

Bên nhận có thể đọc:
  Lần 1: 01 02
  Lần 2: 03 04 05
  Lần 3: 06 07 08

Hoặc:
  Lần 1: 01 02 03 04 05 06 07 08
~~~

Với một chuỗi số nguyên có cấu trúc cố định, phía nhận có thể đọc **đúng 4 byte cho từng số** theo protocol. Với thông điệp có độ dài biến đổi, thường dùng **length prefix**, ví dụ 4 byte length theo big-endian, sau đó là payload dài `length` byte. Khi payload chứa một số little-endian, giao thức có thể quy định **header BE, payload LE** một cách tường minh.

### 5.2. Một protocol demo cụ thể

Trong demo ở phần tiếp theo, request có định dạng:

~~~text
┌─────────────────────────┬──────────────────────────┐
│ Header: length (4 byte) │ Payload: integer (4 byte)│
│ Big-endian              │ Little-endian            │
└─────────────────────────┴──────────────────────────┘

Gửi số 0x01020304:
    header length = 4             payload integer = 0x01020304
        00 00 00 04                    04 03 02 01

Toàn bộ wire bytes:
        00 00 00 04 | 04 03 02 01
~~~

Server đọc lần lượt:

1. Dùng `DataInputStream.readInt()` đọc **4 byte header** theo big-endian để lấy độ dài payload.
2. Kiểm tra length hợp lệ (**chính xác 4 byte** trong demo) trước khi cấp phát mảng.
3. Gọi `readFully(payload)` để gom đủ 4 byte payload, bất kể TCP chia dữ liệu ra sao.
4. Dùng `ByteBuffer.wrap(payload).order(LITTLE_ENDIAN).getInt()` để giải mã số.
5. Gửi ACK bằng `DataOutputStream.writeInt(value)`, nghĩa là **ACK 4 byte big-endian**.

Số trên dây của ACK là `01 02 03 04`. Đây là một giao thức tự định nghĩa để học sự khác biệt của hai API; không phải định dạng TCP mặc định hay một tiêu chuẩn chung.

Định dạng giả định mọi message request chứa đúng một số nguyên 32-bit. Với giao thức lớn hơn, cần tài liệu hóa version, message type, maximum frame size, signedness, thứ tự byte từng trường, cách báo lỗi và phản hồi.

## 6. Ví dụ Java 17+ hoàn chỉnh: TCP gửi int little-endian, header và ACK big-endian

Demo chạy **hoàn toàn trên loopback**, không dùng server ngoài. Nó tạo server TCP ở cổng tự chọn, chạy một worker, mở client local, gửi frame có length prefix rồi nhận ACK. Code dùng cả `DataOutputStream`/`DataInputStream` và `ByteBuffer` để thấy rõ byte order.

Tạo file **ByteOrderTcpDemo.java** và lưu mã với UTF-8:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ByteOrderTcpDemo {
    private static void serve(ServerSocket listener) throws IOException {
        try (Socket peer = listener.accept();
             DataInputStream in = new DataInputStream(
                     new BufferedInputStream(peer.getInputStream()));
             DataOutputStream out = new DataOutputStream(
                     new BufferedOutputStream(peer.getOutputStream()))) {

            peer.setSoTimeout(3_000);

            // Header 4 byte: luôn big-endian qua DataInputStream.
            int length = in.readInt();
            if (length != Integer.BYTES) {
                throw new IOException("Invalid payload length: " + length);
            }

            // Không giả định TCP sẽ trả 4 byte trong một read().
            byte[] payload = new byte[length];
            in.readFully(payload);

            // Payload 4 byte: little-endian theo thỏa thuận protocol.
            int value = ByteBuffer.wrap(payload)
                    .order(ByteOrder.LITTLE_ENDIAN)
                    .getInt();

            // ACK cố định 4 byte big-endian.
            out.writeInt(value);
            out.flush();
        }
    }

    public static void main(String[] args) throws Exception {
        int number = 0x01020304;

        // Xem byte do DataOutputStream.writeInt() tạo ra.
        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(memory)) {
            out.writeInt(number);
        }
        System.out.println("DataOutputStream BE: "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(memory.toByteArray()));

        // Xem byte do ByteBuffer little-endian tạo ra.
        ByteBuffer little = ByteBuffer.allocate(Integer.BYTES)
                .order(ByteOrder.LITTLE_ENDIAN);
        little.putInt(number);
        byte[] payload = little.array();
        System.out.println("ByteBuffer LE:       "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(payload));

        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {

            ExecutorService workers = Executors.newSingleThreadExecutor();
            try {
                Future<?> serverTask = workers.submit(() -> {
                    try {
                        serve(listener);
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                });

                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            InetAddress.getLoopbackAddress(),
                            listener.getLocalPort()), 2_000);
                    client.setSoTimeout(3_000);

                    try (DataOutputStream out = new DataOutputStream(
                                 new BufferedOutputStream(
                                         client.getOutputStream()));
                         DataInputStream in = new DataInputStream(
                                 new BufferedInputStream(
                                         client.getInputStream()))) {

                        // Prefix length BIG_ENDIAN.
                        out.writeInt(payload.length);
                        // Payload số nguyên LITTLE_ENDIAN.
                        out.write(payload);
                        out.flush();

                        // ACK BIG_ENDIAN.
                        int ack = in.readInt();
                        System.out.printf("ACK BE:              0x%08X%n", ack);
                    }
                }

                // Nhận được exception của worker nếu xử lý server lỗi.
                serverTask.get(5, TimeUnit.SECONDS);
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ByteOrderTcpDemo.java
java ByteOrderTcpDemo
~~~

Stdout khi chạy thành công:

~~~text
DataOutputStream BE: 01 02 03 04
ByteBuffer LE:       04 03 02 01
ACK BE:              0x01020304
~~~

**Đọc luồng xử lý:**

1. `DataOutputStream.writeInt(number)` tạo byte `01 02 03 04` trong memory stream. `ByteBuffer.order(LITTLE_ENDIAN).putInt(number)` tạo `04 03 02 01` trong mảng payload.
2. `ServerSocket(0, ..., loopback)` chọn cổng còn trống; worker chỉ phục vụ một kết nối để demo nhỏ, không phải server production.
3. Client gọi `writeInt(payload.length)` ghi header `00 00 00 04`, rồi `write(payload)` ghi `04 03 02 01`; `flush()` đẩy dữ liệu đã buffer xuống output stream.
4. Server `readInt()` lấy length=4, kiểm tra hợp lệ, `readFully()` lấy đúng 4 byte rồi `ByteBuffer` little-endian giải mã lại `0x01020304`.
5. Server `writeInt(value)` gửi ACK big-endian; client `readInt()` nhận đúng 4 byte và in ra mã hex.
6. Socket và stream đóng bằng `try-with-resources`. Timeout đọc giúp demo không chờ vô hạn nếu một đầu ngừng gửi; `Future.get()` truyền lỗi worker ra luồng main.

Phần server không in ra console nên thứ tự stdout ổn định. Trong môi trường chạy bị giới hạn mở loopback socket, chương trình có thể không khởi động được, nhưng điều đó không làm thay đổi quy tắc byte order.

## 7. Số nguyên có dấu, không dấu và chuyển đổi byte

### 7.1. Java `byte` là signed

Trong Java, `byte` có miền `-128..127`; giá trị byte nhị phân `0xFF` khi đọc vào `byte` sẽ là `-1` ở cấp ngôn ngữ, dù 8 bit trên dây vẫn là `11111111`.

~~~java
byte b = (byte) 0xFF;
System.out.println(b);                     // -1
System.out.println(Byte.toUnsignedInt(b)); // 255
System.out.println(b & 0xFF);              // 255
~~~

Đây là đoạn code minh họa độc lập về cách diễn giải byte, có thể đặt trong `main`. Khi tự ghép nhiều byte bằng bit shifting, phải mask từng byte trước khi dịch để tránh **sign extension**:

~~~java
// Minh họa big-endian cho byte[4].
int value = ((bytes[0] & 0xFF) << 24)
          | ((bytes[1] & 0xFF) << 16)
          | ((bytes[2] & 0xFF) << 8)
          |  (bytes[3] & 0xFF);
~~~

`bytes` là biến `byte[]` có **ít nhất 4 byte**; đoạn code không tự kiểm tra độ dài. Để giảm lỗi thủ công, ưu tiên `readInt()` hoặc `ByteBuffer.getInt()` khi protocol phù hợp.

### 7.2. 32-bit trên dây không tự quy định signedness

`DataInputStream.readInt()` và `ByteBuffer.getInt()` trả `int` **có dấu** theo biểu diễn two's complement. Nếu protocol xác định trường 32-bit là **unsigned**, có thể lấy bit pattern bằng `int` rồi chuyển sang `long`:

~~~java
int bits = 0xFFFFFFFF;                      // -1 theo int có dấu
long unsigned32 = Integer.toUnsignedLong(bits);
System.out.println(unsigned32);             // 4294967295
~~~

Byte order chỉ quyết định vị trí byte, còn **signedness** quyết định cách giải thích bit cao nhất. Vì vậy cần ghi rõ cả hai. `DataInputStream.readUnsignedShort()` đọc 2 byte big-endian và trả 0..65535, nhưng không có `readUnsignedInt()` trực tiếp; dùng `Integer.toUnsignedLong(in.readInt())` nếu muốn đủ miền unsigned 32-bit.

Khi truyền số nguyên 64-bit, dùng `writeLong()/readLong()` hoặc `putLong()/getLong()` với **8 byte** và cùng byte order. Tránh đổi từ 32 sang 64 bit ở một phía mà không đổi protocol: số byte tiêu thụ sẽ sai, kéo lệch tất cả trường tiếp theo.

### 7.3. Không nhầm integer, float và chuỗi ký tự

- Số nguyên nhị phân `123` trong frame 4 byte khác chuỗi ASCII/UTF-8 `"123"` dài 3 byte.
- `writeInt(123)` ghi `00 00 00 7B`; `"123".getBytes(UTF_8)` ghi `31 32 33`.
- Endian ảnh hưởng cách sắp xếp **các byte của số nhiều byte**; charset là quy ước khác dùng để mã hóa text. Nếu payload chứa cả số và text, phải định nghĩa riêng field length, endian và charset.

Không dùng `new String(integerBytes)` để giải mã số nhị phân; cũng không dùng `Integer.parseInt(...)` trên 4 byte mà chưa có định dạng text được thỏa thuận.

## 8. Xử lý TCP partial read, EOF và giới hạn frame

### 8.1. DataInputStream đọc đủ, ByteBuffer cần bảo đảm đủ trước khi getInt

Với stream blocking:

~~~java
// Minh họa server nhận frame gồm 4-byte length + payload.
int length = in.readInt();        // 4 byte big-endian
if (length < 0 || length > MAX_BYTES) {
    throw new IOException("Invalid frame length");
}
byte[] payload = new byte[length];
in.readFully(payload);            // đọc đủ length hoặc EOFException
~~~

Đây là đoạn minh họa yêu cầu `in` là `DataInputStream` và `MAX_BYTES` được cấu hình dương. Tránh `new byte[length]` trước khi xác minh giới hạn: peer có thể gửi số lớn hoặc âm, gây cấp phát quá mức, `NegativeArraySizeException` hoặc thiếu bộ nhớ. Trong demo, vì payload chỉ gồm một số nguyên, việc kiểm tra `length == Integer.BYTES` là giới hạn chặt nhất.

`readFully()` ném `EOFException` nếu peer đóng chiều gửi trước khi đủ byte. Nó có thể đã tiêu thụ **một phần payload** trước khi lỗi; ứng dụng không được giả định có thể đọc lại frame từ đầu trên cùng socket. Nếu `SO_TIMEOUT` được đặt, việc đọc chờ có thể ném `SocketTimeoutException`; đó là tình trạng **khác EOF**, và socket không nhất thiết tự đóng. Việc retry/resume cần dựa trên trạng thái parser và giao thức.

Với `ByteBuffer` nhận từ NIO, chỉ gọi `getInt()` khi có **ít nhất 4 byte hợp lệ** trong phần có thể đọc. Khi sử dụng `SocketChannel` ở chế độ non-blocking, một lần `read(buffer)` có thể trả 0 hoặc 1–3 byte; bạn phải tích lũy đủ 4 byte qua nhiều sự kiện trước khi `flip()` rồi giải mã. Không busy-loop liên tục khi `read() == 0`; dùng cơ chế readiness như `Selector` để tránh tiêu tốn CPU.

### 8.2. Một lỗi endian có thể biến length thành giá trị nguy hiểm

Giả sử wire header hợp lệ theo big-endian là `00 00 00 04`, nghĩa là payload dài 4 byte. Nếu bên nhận nhầm little-endian, nó sẽ hiểu thành `0x04000000` = **67.108.864 byte**. Một header bé có thể bị biến thành yêu cầu cấp phát hàng chục MiB hoặc hơn.

Do đó parser phải:

1. Đọc **đủ số byte của header**.
2. Giải mã bằng **byte order được protocol định nghĩa**.
3. Kiểm tra `0 <= length <= MAX_FRAME_SIZE` và các điều kiện tối thiểu/version.
4. Chỉ sau đó mới cấp phát buffer hoặc tiếp tục nhận payload.
5. Giới hạn thời gian đọc, số lượng kết nối và bộ nhớ; xử lý frame lỗi bằng cách đóng/báo lỗi rõ ràng theo protocol.

Kiểm tra byte order, framing và giới hạn kích thước là một nhóm trách nhiệm chung: sai byte order ở header thường có hậu quả nghiêm trọng hơn chỉ đọc sai một giá trị nghiệp vụ.

## 9. Bảng lỗi phổ biến và cách khắc phục

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Sender ghi little-endian, receiver dùng `readInt()` | Giá trị bị đảo byte | Thống nhất BE hoặc receiver đọc qua `ByteBuffer.order(LITTLE_ENDIAN)` |
| Dùng `ByteOrder.nativeOrder()` làm wire format ngầm định | Phụ thuộc máy/kiến trúc | Chọn `BIG_ENDIAN`/`LITTLE_ENDIAN` tường minh |
| Nghĩ TCP tự có network byte order cho payload | Giải mã sai hoặc protocol mơ hồ | Ghi rõ endian cho từng trường |
| Gọi `in.read(bytes)` một lần rồi `getInt()` | Có thể thiếu 4 byte do partial read | Dùng `readFully()` hoặc vòng lặp đọc đủ |
| Gọi `putInt()` rồi `getInt()` ngay mà không `flip()` | `BufferUnderflowException` | `flip()` trước khi chuyển sang pha đọc |
| Dùng `ByteBuffer.array()` trên direct buffer | Có thể ném `UnsupportedOperationException` | `flip()` và `get(byte[])` hoặc dùng heap buffer đúng mục đích |
| Nhầm 32-bit unsigned với Java `int` signed | Giá trị từ `0x80000000` trở lên thành âm | Diễn giải qua `Integer.toUnsignedLong()` khi cần |
| Tự dịch byte âm mà quên `& 0xFF` | Sign extension, ghép số sai | Mask trước dịch hoặc dùng API chuẩn |
| Đọc length sai endian, không kiểm tra length | Có thể cấp phát bộ nhớ quá lớn | Decode đúng endian rồi giới hạn trước cấp phát |
| Quên `flush()` với `BufferedOutputStream` | Peer có thể chờ frame đang nằm trong buffer | Flush tại ranh giới frame phù hợp |
| Để nhiều thread ghi cùng một socket không đồng bộ | Header/payload các frame có thể xen kẽ | Một writer/queue hoặc lock bao toàn bộ frame |
| Retry từ đầu sau EOF/timeout giữa frame | Parser có thể mất đồng bộ với stream | Giữ trạng thái đã đọc hoặc đóng kết nối theo protocol |

## 10. Bài thực hành tự kiểm chứng

### Bài A: Xác định byte order từ 4 byte

Wire bytes là `78 56 34 12`. Kết quả:

- **Big-endian:** `0x78563412`.
- **Little-endian:** `0x12345678`.

Nếu receiver dùng `DataInputStream.readInt()`, nó luôn hiểu theo cách big-endian. Nếu dùng `ByteBuffer.wrap(bytes).order(LITTLE_ENDIAN).getInt()`, nó hiểu theo little-endian.

### Bài B: Giải mã 2 byte không dấu

Wire bytes `FF FE`, giao thức quy định unsigned 16-bit big-endian. Giá trị là `65534`. Nếu dùng `readShort()`, Java trả `-2`; nếu dùng `readUnsignedShort()`, Java trả `65534`. Byte order **không thay thế** quy tắc signedness.

### Bài C: Header big-endian, payload little-endian

Cho dãy trên dây:

~~~text
00 00 00 04 | 78 56 34 12
  length 4   | int payload LE
~~~

`DataInputStream.readInt()` trả length=4. Đọc đúng 4 byte tiếp theo rồi `ByteBuffer.order(LITTLE_ENDIAN).getInt()` trả `0x12345678`. Nếu decode nhầm payload bằng `readInt()`, nhận `0x78563412`.

### Bài D: Đọc số nguyên từ TCP thành nhiều chunk

Client gửi bốn byte `01 02 03 04`, server `read(bytes)` lần đầu chỉ nhận `01 02`. Chưa đủ 4 byte, nên **không được gọi `getInt()` trên buffer 2 byte**. Tiếp tục đọc đủ 2 byte còn lại; hoặc dùng `DataInputStream.readInt()`, vốn yêu cầu đủ 4 byte trước khi trả số.

### Bài E: Thử đổi wire format trong demo

Đổi phần encode payload của client thành `ByteOrder.BIG_ENDIAN` nhưng giữ server `LITTLE_ENDIAN`. Không còn tương thích: server sẽ hiểu `0x04030201` và ACK khác số gốc. Muốn sửa, đổi cả hai phía cùng một order hoặc đổi protocol rõ ràng để dùng BE trên payload.

## 11. Checklist khi thiết kế định dạng số nguyên trên TCP

- [ ] Mỗi trường số có độ rộng cụ thể (**8/16/32/64 bit**) và signedness rõ ràng?
- [ ] Byte order của **từng trường nhiều byte** được định nghĩa tường minh; không dùng native order ngầm định?
- [ ] Hai phía dùng cùng quy tắc `DataInputStream` (BE) hoặc `ByteBuffer.order(...)`?
- [ ] Giao thức có ranh giới thông điệp; header length có kích thước, endian và giới hạn tối đa?
- [ ] Luôn đọc đủ byte bằng `readInt()/readFully()` hoặc parser buffer có trạng thái, không coi một lần `read()` là đủ?
- [ ] Với `ByteBuffer`, position/limit/flip/compact được xử lý đúng?
- [ ] Đã kiểm tra length trước cấp phát và phân biệt EOF, timeout, malformed frame?
- [ ] Khi dùng output có buffer, đã flush **sau frame** khi cần phản hồi nhanh?
- [ ] Có test byte pattern dễ kiểm tra như `0x01020304`, các giá trị âm, unsigned lớn, partial reads và endian mismatch?
- [ ] Nếu nhiều tác vụ dùng chung socket, đã serialize **trọn frame** để các byte không xen kẽ?

**Ghi nhớ:** TCP giữ nguyên thứ tự byte, còn **ý nghĩa của bốn byte là do giao thức định nghĩa**. `DataInputStream`/`DataOutputStream` cho bạn số nguyên big-endian nhất quán; `ByteBuffer` cho phép chọn big-endian hoặc little-endian rõ ràng. Kết hợp lựa chọn endian với framing, đọc đủ byte và kiểm tra độ dài là nền tảng để truyền số nguyên qua TCP chính xác và an toàn.