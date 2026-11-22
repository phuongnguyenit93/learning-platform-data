# SocketException, SocketTimeoutException và lỗi mạng trong Java

Lập trình socket trong Java buộc chương trình đối mặt với nhiều trạng thái không hoàn toàn nằm trong quyền kiểm soát của mã ứng dụng: địa chỉ không phân giải được, server chưa lắng nghe, kết nối bị đóng, kết nối bị reset, không có dữ liệu đến trong khoảng thời gian cho phép, mạng không có đường đi, hoặc thao tác gửi đã được thực hiện nhưng phản hồi không tới. **`SocketException` và `SocketTimeoutException` là hai tên quan trọng, nhưng chúng không cùng một nhánh kế thừa trực tiếp**.

Những điểm cần nhớ ngay:

- **`java.net.SocketException`** kế thừa **`java.io.IOException`**; nó thường biểu diễn lỗi khi tạo, truy cập hoặc dùng socket. Các lớp con đáng biết gồm `ConnectException`, `BindException`, `NoRouteToHostException` và `PortUnreachableException`.
- **`java.net.SocketTimeoutException`** kế thừa **`java.io.InterruptedIOException`**, rồi mới tới **`IOException`**. Nó **không** kế thừa `SocketException`. Nó báo một thao tác socket đã vượt **thời hạn chờ** do API hỗ trợ, chẳng hạn kết nối, đọc dữ liệu, `ServerSocket.accept()` hoặc `DatagramSocket.receive()`.
- Cả hai là **checked exceptions** theo nghĩa Java: chúng nằm trong `IOException`, không thuộc `RuntimeException`. Phương thức gọi phải xử lý hoặc khai báo một loại checked exception đủ bao phủ chúng.
- **Timeout không đồng nghĩa với lỗi kết nối vĩnh viễn**, **EOF không đồng nghĩa với timeout**, **DNS failure không đồng nghĩa với connection refused**, và **socket closed không đồng nghĩa với mạng bị mất**.
- Cần phân biệt **lỗi kỹ thuật**, **mức retry có thể chấp nhận**, **idempotency của thao tác**, **trạng thái giao dịch** và **cách bảo toàn cause/stack trace**. Chỉ dựa vào message như `"Connection reset"` để quyết định retry là rất dễ sai.

Bài giải thích hợp đồng API, phân cấp, những tình huống thực tế, ví dụ Java 17 tự chạy bằng loopback không cần Internet, mẫu xử lý lỗi, giới hạn của timeout, kiểm thử và checklist khắc phục.

## 1. Sơ đồ kế thừa: phân biệt trước khi viết catch

Sơ đồ rút gọn các loại checked exception liên quan:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException
        ├── java.net.SocketException
        │   ├── java.net.BindException
        │   ├── java.net.ConnectException
        │   ├── java.net.NoRouteToHostException
        │   └── java.net.PortUnreachableException
        ├── java.io.InterruptedIOException
        │   └── java.net.SocketTimeoutException
        ├── java.net.UnknownHostException
        ├── java.io.EOFException
        └── ... các lớp IOException khác
```

**Điểm thường bị nhầm nhất:** `SocketTimeoutException` không nằm dưới `SocketException`. Hai loại có thể đều phát sinh trong thao tác socket, nhưng thuộc **hai nhánh khác nhau** của `IOException`.

Hệ quả khi viết handler:

```java
try {
    communicate();
} catch (SocketTimeoutException e) {
    // Chính sách timeout.
} catch (SocketException e) {
    // Các lỗi socket khác.
} catch (IOException e) {
    // Các lỗi I/O còn lại.
}
```

Đây là **khối minh họa**, với method `communicate() throws IOException` trong phạm vi và các import `java.net`/`java.io` phù hợp. Cấu trúc này hợp lệ vì `IOException` đứng cuối, còn hai loại trước đều là nhánh con của nó.

Nếu chỉ viết `catch (SocketException e)` thì **không** bắt được `SocketTimeoutException`. Nếu dùng `catch (IOException e)` ở đầu, các handler subtype sau nó sẽ **không thể tới được** và compiler từ chối.

## 2. Ví dụ Java 17: kiểm chứng quan hệ kiểu bằng mã

Lưu **`SocketExceptionHierarchyDemo.java`**:

```java
import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

public class SocketExceptionHierarchyDemo {
    public static void main(String[] args) {
        System.out.println("SocketException <: IOException: "
                + IOException.class.isAssignableFrom(
                        SocketException.class));

        System.out.println("Timeout <: IOException: "
                + IOException.class.isAssignableFrom(
                        SocketTimeoutException.class));

        System.out.println("Timeout <: InterruptedIOException: "
                + InterruptedIOException.class.isAssignableFrom(
                        SocketTimeoutException.class));

        System.out.println("Timeout <: SocketException: "
                + SocketException.class.isAssignableFrom(
                        SocketTimeoutException.class));

        System.out.println("ConnectException <: SocketException: "
                + SocketException.class.isAssignableFrom(
                        ConnectException.class));

        System.out.println("UnknownHostException <: SocketException: "
                + SocketException.class.isAssignableFrom(
                        UnknownHostException.class));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SocketExceptionHierarchyDemo.java
java SocketExceptionHierarchyDemo
```

**Stdout chính xác:**

```text
SocketException <: IOException: true
Timeout <: IOException: true
Timeout <: InterruptedIOException: true
Timeout <: SocketException: false
ConnectException <: SocketException: true
UnknownHostException <: SocketException: false
```

`Class.isAssignableFrom` kiểm tra quan hệ gán kiểu. Kết quả khẳng định một lỗi timeout có thể được bắt bằng `IOException` hoặc `InterruptedIOException` nhưng **không** bằng `SocketException`.

Nếu không muốn bắt nhiều loại riêng, `catch (IOException e)` là tầng dự phòng chung. Tuy nhiên, **bắt quá rộng không có nghĩa mọi lỗi I/O có cùng chính sách retry hoặc phục hồi**.

## 3. `SocketException` mô tả những dạng thất bại nào?

`SocketException` là checked exception được sử dụng trong các thao tác socket để phản ánh tình trạng I/O hoặc sử dụng socket không thành công. Những ví dụ ngoài thực tế có thể là:

- Socket đã đóng trong khi chương trình cố dùng nó.
- Một đầu TCP kết nối bị reset theo hành vi của hệ thống mạng.
- Có sự cố ở tầng socket khiến thao tác đọc/ghi/kết nối thất bại.
- Hệ điều hành hoặc stack mạng từ chối một thao tác liên quan đến socket.
- Một subclass báo tình huống cụ thể như **`ConnectException`** (kết nối bị từ chối hoặc không thiết lập được theo cơ chế phù hợp) hay **`BindException`** (không thể bind endpoint).

Nhưng **không nên áp dụng suy luận quá mạnh**:

- `SocketException` không luôn có nghĩa máy chủ đã tắt.
- `SocketException` không luôn có nghĩa phần cứng mạng hỏng.
- `SocketException` không cho biết chắc thao tác gửi ở phía server đã thực hiện hay chưa.
- Cùng một nguyên nhân vật lý có thể xuất hiện dưới loại hoặc message khác nhau tùy JVM, hệ điều hành, giao thức và bước đang thực hiện.
- Message như `"Connection reset"`, `"Broken pipe"` hay `"Socket closed"` là dấu hiệu hỗ trợ chẩn đoán, **không phải mã lỗi Java được tiêu chuẩn hóa trên mọi nền tảng**.

Cần quan sát **loại exception, thao tác đang thực hiện, socket lifecycle, địa chỉ, timeout cấu hình, thời điểm và kết quả nghiệp vụ**, chứ không chỉ đọc một đoạn message.

## 4. `SocketTimeoutException` mang nghĩa gì?

`SocketTimeoutException` được ném khi một thao tác socket có **thời hạn chờ** và thời hạn đó bị vượt trước khi thao tác đạt điều kiện hoàn tất do API xác định.

Các ngữ cảnh tiêu biểu:

1. **Kết nối:** `Socket.connect(endpoint, timeout)` chưa thiết lập kết nối kịp trong giới hạn.
2. **Đọc TCP:** `Socket.setSoTimeout(milliseconds)` đặt read timeout cho những thao tác đọc blocking thích hợp trên `SocketInputStream`.
3. **Chờ client:** `ServerSocket.setSoTimeout(milliseconds)` giới hạn thời gian `ServerSocket.accept()` chờ một kết nối mới.
4. **Nhận datagram:** `DatagramSocket.setSoTimeout(milliseconds)` giới hạn thời gian `receive(...)` chờ gói phù hợp.

Không nên nói “timeout = 2 giây thì toàn bộ request phải hoàn tất trong 2 giây” nếu chỉ đặt **read timeout**: đây là thời hạn của thao tác đọc chờ dữ liệu, không tự tạo một **deadline tổng** cho một quy trình gồm nhiều lần đọc, retry, parse và xử lý.

Khi timeout xảy ra, API trả exception; **không đồng nghĩa tài nguyên chắc chắn đã hỏng vĩnh viễn**. Với blocking socket read bị `SO_TIMEOUT`, tài liệu `Socket` nói socket vẫn hợp lệ sau `SocketTimeoutException`, nhưng tầng ứng dụng phải xác định còn có thể tiếp tục đọc không, message framing có nhất quán không và có rủi ro dữ liệu dở dang không.

## 5. Checked exception và nghĩa vụ catch-or-declare

Cả `SocketException` và `SocketTimeoutException` là lớp con của `IOException`, do đó thuộc nhóm **checked**. Ví dụ:

```java
static int receiveOneByte(Socket socket) throws IOException {
    return socket.getInputStream().read();
}
```

Đây là **phương thức minh họa**; cần import `java.net.Socket` và `java.io.IOException`. Vì `getInputStream` và `read` có thể ném checked `IOException`, method công bố `throws IOException` là một cách hợp lệ để cho caller chịu trách nhiệm.

Một caller có thể:

- `catch (SocketTimeoutException e)` để áp chính sách timeout.
- `catch (SocketException e)` cho lỗi socket cụ thể.
- `catch (IOException e)` cho lỗi I/O khác.
- Hoặc công bố `throws IOException` để đẩy lên tầng có trách nhiệm xử lý.

Không có `throws SocketTimeoutException` trong chữ ký không có nghĩa nó không thể xảy ra: một method có `throws IOException` vẫn cho phép các lớp con thích hợp. Ngược lại, viết `throws SocketException` **không bao phủ** `SocketTimeoutException` do chúng khác nhánh.

## 6. Các loại lỗi mạng cần phân biệt

| Loại hoặc tín hiệu | Tình huống thường gặp | Điều không nên kết luận |
| --- | --- | --- |
| `UnknownHostException` | Không phân giải được tên host theo cơ chế DNS/địa chỉ | Không phải `SocketException`; không đồng nghĩa server đã từ chối kết nối |
| `ConnectException` | Kết nối TCP không thiết lập được, thường gặp khi endpoint từ chối | Không có bằng chứng request nghiệp vụ đã được thực thi |
| `NoRouteToHostException` | Không tìm được đường mạng tới host hoặc lý do phù hợp ở tầng IP | Không giống timeout ứng dụng |
| `BindException` | Không bind được địa chỉ/cổng cục bộ | Không phải lỗi đọc dữ liệu của kết nối đã mở |
| `SocketTimeoutException` | Thao tác socket chờ quá giới hạn | Không tự chứng minh remote server đã chết |
| `SocketException` | Lỗi socket tổng quát hoặc trạng thái socket không dùng được | Không có một chính sách retry chung cho mọi message |
| `EOF` từ `InputStream.read() == -1` | Đầu gửi đóng output sạch sẽ và không còn byte để đọc | Không phải exception timeout |
| `EOFException` | Một API đọc dữ liệu có cấu trúc kỳ vọng thêm byte nhưng gặp EOF | Khác với giá trị `-1` của `InputStream.read()` |
| `SSLException` | Vấn đề thuộc tầng TLS/SSL khi dùng API tương ứng | Không phải mọi TLS failure đều là `SocketException` |
| `HttpTimeoutException` | Timeout theo hợp đồng `java.net.http.HttpClient` | Không phải subclass của `SocketTimeoutException` |

Tên exception là **tín hiệu bước đầu**. Muốn xử lý chính xác phải biết gọi API nào, thất bại ở bước nào và điều gì có thể đã xảy ra phía đối tác.

## 7. Timeout kết nối: `Socket.connect(endpoint, timeout)`

Một cách đặt timeout kết nối tường minh:

```java
try (Socket socket = new Socket()) {
    socket.connect(
            new InetSocketAddress(host, port),
            1500);
    // Đã kết nối thì mới sử dụng input/output stream.
}
```

Đây là **mã minh họa**, cần import `java.net.Socket` và `java.net.InetSocketAddress`, cùng `host`, `port` trong phạm vi. Phương thức chứa phải bắt hoặc khai báo `IOException` tương ứng.

Giá trị `1500` là **1.500 milliseconds**, tức 1,5 giây về mặt tham số. Nó là thời hạn chờ ở thao tác `connect`, không phải một cam kết tổng thời gian method không bao giờ vượt quá 1,5 giây trong mọi cấu hình DNS, scheduler và mạng.

Các kết quả có thể xảy ra:

- Kết nối thành công: `connect` trả bình thường.
- Timeout: có thể ném `SocketTimeoutException`.
- Endpoint từ chối: thường có thể ném `ConnectException`.
- Không có đường mạng: có thể ném `NoRouteToHostException`.
- Vấn đề socket hoặc I/O khác: có thể ném `SocketException` hoặc `IOException` phù hợp.

**Lưu ý về resolution:** tạo `InetSocketAddress(host, port)`, tra DNS và thực hiện kết nối là các khâu cần quan sát riêng; API socket này không nên được nhầm với một “deadline toàn ứng dụng bao gồm DNS, TLS, request và response”.

## 8. Ví dụ Java 17: mã phân loại lỗi kết nối không phụ thuộc Internet

Để có output xác định khi dạy về **nhánh catch**, ví dụ sau *mô phỏng* từng loại exception bằng cách khởi tạo chúng; nó **không tạo lỗi mạng thật**.

Lưu **`NetworkExceptionClassificationDemo.java`**:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

public class NetworkExceptionClassificationDemo {
    static void classify(IOException error) {
        try {
            throw error;
        } catch (SocketTimeoutException e) {
            System.out.println("TIMEOUT");
        } catch (ConnectException e) {
            System.out.println("CONNECT_REFUSED");
        } catch (NoRouteToHostException e) {
            System.out.println("NO_ROUTE");
        } catch (SocketException e) {
            System.out.println("SOCKET_IO");
        } catch (UnknownHostException e) {
            System.out.println("DNS");
        } catch (IOException e) {
            System.out.println("OTHER_IO");
        }
    }

    public static void main(String[] args) {
        classify(new SocketTimeoutException("simulated"));
        classify(new ConnectException("simulated"));
        classify(new NoRouteToHostException("simulated"));
        classify(new SocketException("simulated"));
        classify(new UnknownHostException("simulated"));
        classify(new IOException("simulated"));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 NetworkExceptionClassificationDemo.java
java NetworkExceptionClassificationDemo
```

**Stdout chính xác:**

```text
TIMEOUT
CONNECT_REFUSED
NO_ROUTE
SOCKET_IO
DNS
OTHER_IO
```

Điểm học tập:

- `ConnectException` và `NoRouteToHostException` là lớp con của `SocketException` nên handler cụ thể **phải đứng trước** `catch (SocketException)`.
- `SocketTimeoutException` và `UnknownHostException` **không** thuộc nhánh `SocketException`.
- `IOException` cuối cùng xử lý các trường hợp còn lại.
- Có thể đổi thứ tự giữa các sibling catch nếu không gây che phủ kế thừa; quan trọng nhất là **subclass trước superclass**.

Không dựa vào `error.getMessage()` để phân loại. Khi ứng dụng cần mã lỗi có cấu trúc, nên ánh xạ dựa trên loại và **ngữ cảnh thao tác**, không chỉ subtype.

## 9. `Socket.setSoTimeout(...)` dùng cho **đọc**, không phải kết nối

Với `java.net.Socket`, `setSoTimeout(int timeout)` cấu hình giới hạn chờ đọc trên socket blocking. Ví dụ:

```java
socket.setSoTimeout(500);
int next = socket.getInputStream().read();
```

Đây là **mã minh họa**. Nếu không có dữ liệu hay EOF phù hợp trước giới hạn chờ, thao tác đọc có thể ném `SocketTimeoutException`.

Những lưu ý:

- Giá trị tính bằng **milliseconds**.
- `0` có ý nghĩa **timeout vô hạn** cho thao tác chờ liên quan (không chủ động giới hạn thời gian bằng SO_TIMEOUT).
- Giá trị âm không hợp lệ và `setSoTimeout` ném `IllegalArgumentException`.
- `setSoTimeout` phải được áp trước thao tác blocking cần giới hạn.
- `setSoTimeout` **không thay thế** `Socket.connect(endpoint, connectTimeout)`.
- Nó không tạo một deadline cho toàn bộ vòng đời socket hoặc mọi lần đọc nối tiếp.
- Với một lần `read()` bị timeout, socket thông thường vẫn hợp lệ, nhưng **không có bảo đảm giao thức ứng dụng đang ở trạng thái sạch** sau khi một request đã gửi nhưng chưa nhận đủ phản hồi.

Không dùng `InputStream.available() == 0` để khẳng định remote đã đóng hoặc không còn dữ liệu; `available()` chỉ là một ước lượng số byte có thể đọc **không blocking**, không phải tín hiệu EOF hay tình trạng kết nối.

## 10. Ví dụ tự chạy: read timeout thực sự trên loopback

Ví dụ này dùng **loopback** (`127.0.0.1` hoặc địa chỉ loopback tương đương của hệ thống), không cần server bên ngoài hay Internet. Nó chủ động kết nối hai đầu socket trong **cùng một tiến trình**, giữ đầu server không gửi byte trong lần đọc đầu, rồi gửi một byte để kiểm chứng client có thể đọc tiếp sau timeout.

Lưu **`SocketReadTimeoutDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class SocketReadTimeoutDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server =
                     new ServerSocket(0, 50, loopback);
             Socket client =
                     new Socket(loopback, server.getLocalPort());
             Socket accepted = server.accept()) {

            client.setSoTimeout(150);
            InputStream input = client.getInputStream();

            try {
                input.read();
                throw new AssertionError("Mong đợi read timeout");
            } catch (SocketTimeoutException e) {
                System.out.println("Read timed out");
            }

            accepted.getOutputStream().write(65);
            accepted.getOutputStream().flush();

            System.out.println("Byte sau timeout: " + input.read());
            System.out.println("Client vẫn mở: " + !client.isClosed());
        }
    }
}
```

Biên dịch/chạy với Java 17:

```bash
javac -encoding UTF-8 --release 17 SocketReadTimeoutDemo.java
java SocketReadTimeoutDemo
```

**Stdout mong đợi trên hệ thống cho phép TCP loopback**, khi không có can thiệp mạng ngoài vào cổng ngẫu nhiên:

```text
Read timed out
Byte sau timeout: 65
Client vẫn mở: true
```

Giải thích:

1. `new ServerSocket(0, 50, loopback)` mở cổng **ephemeral** do hệ điều hành chọn, bind riêng vào loopback.
2. `client` kết nối cổng đó; `server.accept()` trả socket phía server.
3. `client.setSoTimeout(150)` giới hạn mỗi thao tác đọc blocking tương ứng.
4. Vì `accepted` chưa gửi dữ liệu và chưa đóng output, lần `input.read()` đầu hết thời gian chờ rồi ném `SocketTimeoutException`.
5. Sau đó phía server gửi **giá trị byte 65**; lần `read()` tiếp theo trả `65`.
6. Timeout đọc **không tự động `close()` socket** trong ví dụ này.

**Đây là minh họa hành vi socket thật**, không phải output cứng đảm bảo trên môi trường chặn loopback hoặc JVM/hệ điều hành có lỗi. Không nên assert số milliseconds thực tế; scheduler và tải máy có thể ảnh hưởng thời điểm exception xuất hiện. Cổng được chọn động để tránh hard-code cổng.

## 11. Timeout đọc không có nghĩa EOF

Với một `InputStream` lấy từ TCP socket, một lời gọi đọc một byte thường có ba nhóm kết quả:

1. **Một byte được đọc thành công:** `read()` trả số `0..255`.
2. **Luồng kết thúc sạch và không còn dữ liệu:** `read()` trả `-1`.
3. **Thất bại I/O hoặc chờ quá giới hạn:** ném một `IOException` thích hợp, có thể là `SocketTimeoutException`.

Nếu đọc một byte mà nhận `-1`, đó **không phải `SocketTimeoutException`** và không nên retry cùng logic như timeout. Nó biểu thị đã nhận EOF từ luồng; với TCP thường liên quan peer đóng phía gửi output một cách có trật tự.

Đối với `read(byte[])`, kết quả còn phụ thuộc độ dài bộ đệm (yêu cầu đọc 0 byte có thể trả 0 ngay). Khi thiết kế giao thức, phải đọc đúng số byte theo framing và phân biệt đoạn thiếu dữ liệu với EOF.

Một exception như `EOFException` có thể xuất hiện trong các API đọc cấu trúc như `DataInputStream.readFully(...)` khi yêu cầu số byte cụ thể nhưng luồng kết thúc sớm. **Giá trị -1 của InputStream.read() không phải object `EOFException`.**

## 12. Ví dụ Java 17: EOF sạch không ném timeout

Lưu **`SocketEndOfStreamDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class SocketEndOfStreamDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server =
                     new ServerSocket(0, 50, loopback);
             Socket client =
                     new Socket(loopback, server.getLocalPort());
             Socket accepted = server.accept()) {

            client.setSoTimeout(1000);

            accepted.shutdownOutput();
            InputStream input = client.getInputStream();

            System.out.println("read sau shutdownOutput: "
                    + input.read());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SocketEndOfStreamDemo.java
java SocketEndOfStreamDemo
```

**Stdout mong đợi khi loopback hoạt động bình thường:**

```text
read sau shutdownOutput: -1
```

`accepted.shutdownOutput()` thực hiện half-close hướng **gửi** từ phía server. Khi phía client đọc và không có dữ liệu còn chờ, nó nhận EOF (`-1`). Đây là **kết thúc có thứ tự** thay vì chờ tới timeout.

Trong giao thức thực tế, EOF có thể là **kết thúc bình thường** hoặc **phản hồi thiếu dữ liệu** tùy framing. Ví dụ giao thức yêu cầu 100 byte mà peer đóng sau 20 byte thì đó là lỗi dữ liệu không đầy đủ ở tầng ứng dụng, dù dấu hiệu cấp stream là EOF.

## 13. `ServerSocket.accept()` cũng có thể timeout

`ServerSocket` là đầu socket lắng nghe kết nối TCP. Nếu cần server không đứng chờ mãi trong `accept()`, dùng:

```java
serverSocket.setSoTimeout(500);
Socket peer = serverSocket.accept();
```

Đây là **mã khung minh họa**. Timeout của `ServerSocket` áp vào **thao tác chờ kết nối mới**; nó **không** tự quy định read timeout trên `Socket` mà `accept()` trả về.

Khi `accept()` vượt thời gian chờ, nó ném `SocketTimeoutException`. Theo contract `ServerSocket`, **ServerSocket vẫn hợp lệ** sau timeout; chương trình có thể tiếp tục chờ lần khác, ngừng phục vụ hoặc kiểm tra cờ dừng.

**Phải tự đóng socket phía client được accept** khi công việc với client kết thúc, thường bằng try-with-resources hoặc cơ chế quản lý kết nối tương ứng. Timeout của listener và timeout của kết nối đã accept là hai chính sách tách biệt.

## 14. Ví dụ Java 17: listener hết thời gian chờ nhưng vẫn mở

Lưu **`ServerAcceptTimeoutDemo.java`**:

```java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class ServerAcceptTimeoutDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {

            server.setSoTimeout(120);

            try (Socket ignored = server.accept()) {
                System.out.println("Có kết nối bất ngờ");
            } catch (SocketTimeoutException e) {
                System.out.println("Accept timed out");
            }

            System.out.println("Server vẫn mở: "
                    + !server.isClosed());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ServerAcceptTimeoutDemo.java
java ServerAcceptTimeoutDemo
```

**Stdout mong đợi trong môi trường không có client kết nối tới cổng loopback vừa cấp:**

```text
Accept timed out
Server vẫn mở: true
```

Lỗi xảy ra tại `server.accept()`, không phải vì ServerSocket đã bị đóng. Hệ thống có thể tiếp tục gọi `accept()` nếu đó là chính sách vận hành.

Ví dụ dùng cổng ephemeral, không khởi tạo thread hay client, nên rất thích hợp để kiểm chứng hành vi chờ. Một môi trường không cho phép mở listener cục bộ có thể ném lỗi bind/quyền khác ngay trước bước timeout; đó không phải kết quả mong đợi của ví dụ.

## 15. `DatagramSocket.receive()` và UDP timeout

UDP khác TCP: không có kết nối TCP đảm bảo giao hàng và thứ tự byte stream theo cùng cách. `DatagramSocket.receive(packet)` chờ datagram tới socket; có thể cấu hình:

```java
datagramSocket.setSoTimeout(500);
datagramSocket.receive(packet);
```

Đây là **mã minh họa**; cần các biến `DatagramSocket` và `DatagramPacket`. Nếu không có datagram phù hợp trước thời hạn, có thể ném `SocketTimeoutException`.

Cần lưu ý:

- **UDP timeout không chứng minh gói đã bị mất ở đâu**: có thể sender không gửi, packet bị rớt, định tuyến có vấn đề hoặc thời hạn chờ quá ngắn.
- `DatagramSocket` có thể được kết nối logic đến một peer nhưng UDP vẫn **không** có phiên TCP như `Socket`.
- `PortUnreachableException` là một subclass của `SocketException`; trên UDP có thể liên quan ICMP port unreachable nhưng **không được đảm bảo xuất hiện ở mọi OS, mọi trường hợp**.
- Không suy rằng `send` UDP thành công đồng nghĩa peer đã nhận/xử lý dữ liệu.
- Muốn độ tin cậy, thứ tự và retry, giao thức ứng dụng phải chủ động thiết kế.

`DatagramSocket.setSoTimeout` chỉ điều chỉnh thao tác nhận chờ dữ liệu; nó không là một **deadline trọn vẹn** cho cơ chế retransmission tự xây.

## 16. Ví dụ Java 17: UDP receive timeout trên loopback

Lưu **`DatagramTimeoutDemo.java`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;

public class DatagramTimeoutDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramSocket receiver =
                new DatagramSocket(0, InetAddress.getLoopbackAddress())) {

            receiver.setSoTimeout(120);

            byte[] data = new byte[32];
            DatagramPacket packet = new DatagramPacket(data, data.length);

            try {
                receiver.receive(packet);
                System.out.println("Có gói dữ liệu");
            } catch (SocketTimeoutException e) {
                System.out.println("UDP receive timed out");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 DatagramTimeoutDemo.java
java DatagramTimeoutDemo
```

**Stdout mong đợi** khi không có tác nhân nào gửi datagram đến cổng mới được cấp:

```text
UDP receive timed out
```

Không có code gửi UDP trong chương trình, do đó `receive` chờ rồi timeout. Nếu môi trường cấm bind loopback hoặc có gói bất ngờ tới cổng đó, nhánh kết quả có thể khác; test thực tế cần điều kiện mạng ổn định.

Điểm chính là **cùng loại `SocketTimeoutException` có thể xuất hiện ở TCP read, ServerSocket accept và UDP receive**, nhưng mỗi nơi có ý nghĩa thao tác khác nhau.

## 17. `ConnectException`: kết nối thất bại, thường gặp connection refused

`ConnectException extends SocketException` và thường gặp khi client cố thiết lập kết nối đến cổng không có dịch vụ lắng nghe hoặc endpoint từ chối kết nối theo cơ chế OS.

Ví dụ code khung:

```java
try (Socket socket = new Socket()) {
    socket.connect(
            new InetSocketAddress("127.0.0.1", 65000),
            500);
} catch (ConnectException e) {
    // Không thiết lập được kết nối, thường do endpoint từ chối.
}
```

Đây là **mã minh họa**, **không có stdout cố định** và **không phải test xác định**: cổng 65000 vẫn có thể được sử dụng trên một máy cụ thể. Cần import `Socket`, `InetSocketAddress`, `ConnectException`; còn các `IOException` khác cũng cần xử lý hoặc khai báo.

Đừng chỉ nhìn message kiểu `"Connection refused"` rồi chắc chắn nguyên nhân là server process chưa chạy. Còn cần xét địa chỉ IP/port, listener bind trên giao diện nào, firewall, container/VM network namespace và chính sách bảo mật mạng.

Nếu muốn test thật việc từ chối kết nối, phải kiểm soát được endpoint và không dựa vào một port “chắc chắn trống” bằng suy đoán.

## 18. `BindException`: không gắn được endpoint cục bộ

Một server phải bind vào địa chỉ/cổng địa phương trước khi chấp nhận kết nối. Nếu cổng đã có listener khác hoặc địa chỉ bind không khả dụng, `new ServerSocket(port)` hay thao tác bind có thể ném **`BindException`**, một subclass của `SocketException`.

Các điểm dễ nhầm:

- **Bind failure** xảy ra khi chuẩn bị endpoint của **phía local**, không phải khi client đọc phản hồi.
- `BindException` có thể do cổng đã bị chiếm, địa chỉ không có trên host, quyền hệ thống hoặc chính sách mạng.
- Không nên giải thích mọi `BindException` bằng câu “server bên kia đã chết”.
- Khi server bind port `0`, OS chọn một cổng sẵn có; có thể đọc `serverSocket.getLocalPort()` sau khi bind thành công.

Trong ví dụ dùng loopback của bài, chọn port `0` để **hạn chế va chạm cổng** và tránh tự hứa rằng một port cố định không bị chiếm trên máy học viên.

## 19. `UnknownHostException`: lỗi phân giải tên, không phải kết nối đã bị từ chối

`UnknownHostException extends IOException`, **không thuộc `SocketException`**. Nó thường báo host name không phân giải được thành địa chỉ phù hợp theo cơ chế đang dùng.

Ví dụ:

```java
InetAddress resolved = InetAddress.getByName(hostName);
```

Đây là **mã minh họa** với `hostName` trong phạm vi và import `java.net.InetAddress`. Nếu resolution không thực hiện được, API có thể ném `UnknownHostException`.

Cần phân biệt các giai đoạn:

1. **DNS/name resolution**: xác định địa chỉ từ tên.
2. **Connect**: cố thiết lập kết nối tới địa chỉ/cổng.
3. **I/O**: gửi và nhận dữ liệu qua kết nối.
4. **Protocol/application**: nhận phản hồi đúng cú pháp và ý nghĩa.

Một lỗi ở bước 1 không chứng minh host đã nhận và từ chối kết nối ở bước 2. Một kết nối thành công ở bước 2 không chứng minh response nghiệp vụ sẽ tới ở bước 4.

**Đừng dựa vào hostname giả để tạo test DNS lỗi có stdout cố định**: DNS có cấu hình nội bộ, search domain, resolver hoặc môi trường mạng khác nhau. Nếu cần test logic phân loại, hãy tạo một `UnknownHostException` nhân tạo trong unit test như ở `NetworkExceptionClassificationDemo`.

## 20. Socket closed, reset và broken pipe

Những thông điệp thường gặp khi nghiên cứu lỗi socket:

- `Socket closed`: ứng dụng cố thao tác trên một socket đã bị đóng, hoặc tài nguyên đã được đóng trong khi thao tác đang chờ, tùy API/cách thực thi.
- `Connection reset`: kết nối TCP bị reset, có thể xảy ra do peer hoặc thành phần mạng.
- `Broken pipe`: thường liên quan thao tác ghi khi đầu bên kia không còn tiếp nhận theo tình trạng hệ điều hành.

Chú ý:

- **Thông điệp không phải enum/contract Java độc lập.** Wording có thể khác theo OS/JDK và bước thao tác.
- Một socket đã được đóng bởi chính code ứng dụng **không phải bằng chứng có lỗi hạ tầng mạng**.
- Việc `Socket.isClosed()` là `false` không cam kết peer còn sống hay lần I/O tiếp theo sẽ thành công.
- `Socket.isConnected()` phản ánh socket **đã từng kết nối thành công**, không phải một health check liên tục xác nhận peer đang trực tuyến.
- Một lời gọi `write` thành công ở phía client không tự chứng minh server đã xử lý yêu cầu ở tầng ứng dụng.
- Khi có reset/broken pipe, phải đánh giá **thao tác có thể đã được thực hiện một phần không**, trước khi retry.

Không nên thay thế mọi message lỗi bằng `SocketTimeoutException` hoặc tự ép chúng thành một trạng thái “timeout” duy nhất.

## 21. Timeout khác thế nào với server phản hồi chậm?

Nếu thao tác `read()` không nhận được dữ liệu trong thời hạn `SO_TIMEOUT`, Java có thể ném `SocketTimeoutException`. Nhưng nhiều nguyên nhân có thể dẫn tới cùng tín hiệu:

- Server đang thực hiện truy vấn chậm.
- Server đã nhận request nhưng chờ một phụ thuộc khác.
- Server không gửi response vì đang chờ bạn gửi thêm dữ liệu theo giao thức.
- Gói tin bị trì hoãn hoặc mất trên đường mạng.
- Peer đã gặp lỗi nhưng TCP chưa có tín hiệu đóng/reset mà bên nhận quan sát được.
- Timeout cấu hình quá ngắn so với độ trễ bình thường.

Vì vậy câu “SocketTimeoutException chứng minh server không xử lý request” là **sai**. Timeout chỉ xác nhận **điều kiện chờ của bên gọi bị vượt**. Trạng thái xử lý ở peer có thể **chưa được biết**.

Đối với thao tác có side effect như đặt hàng hoặc chuyển tiền, timeout chờ response không cho phép bạn kết luận thao tác chưa thực hiện. Phải có ID yêu cầu, idempotency, tra cứu trạng thái hoặc cơ chế bù trừ theo thiết kế.

## 22. Retry không đồng nghĩa với giải pháp cho mọi IOException

Khi có `SocketTimeoutException`, `ConnectException` hoặc `SocketException`, một thiết kế retry tốt phải trả lời:

1. **Lỗi xảy ra ở bước nào?** Trước khi gửi request, trong khi gửi, sau khi gửi, hay khi đọc response?
2. **Thao tác có idempotent không?** Đọc dữ liệu, PUT cập nhật trạng thái đã thiết kế, hay POST tạo giao dịch mới?
3. **Kết quả phía server có thể đã được commit chưa?**
4. **Có thời gian tối đa cho toàn bộ retry không?**
5. **Có giới hạn số lần thử và backoff/jitter không?**
6. **Có token/idempotency key để xử lý yêu cầu lặp lại không?**
7. **Có nguy cơ tạo retry storm làm hệ thống đang quá tải càng quá tải?**
8. **Có chính sách phân biệt lỗi DNS cấu hình sai, địa chỉ sai với lỗi tạm thời?**

Ví dụ an toàn hơn:

- Một request **đọc trạng thái** có thể thử lại có giới hạn trong chính sách đã thiết kế.
- Một lệnh **tạo giao dịch** có thể cần idempotency key và kiểm tra trạng thái giao dịch trước khi thử lại.
- `UnknownHostException` do tên miền cấu hình sai có thể không được khắc phục bằng retry liên tục.
- `BindException` vì server trùng port thường cần sửa cấu hình hoặc giải phóng port, không phải gửi cùng request đi nhiều lần.

Không dùng mã giả `catch (IOException e) { retryForever(); }` làm chiến lược mặc định.

## 23. Read timeout không phải deadline toàn request

Giả sử một ứng dụng đọc một response dài theo nhiều lần `read()`, mỗi lần đều có `SO_TIMEOUT = 2 giây`. Nếu peer gửi một lượng nhỏ dữ liệu trước mỗi khoảng hai giây, ứng dụng có thể tiếp tục hoạt động **lâu hơn hai giây tổng cộng**.

Do đó cần phân biệt:

- **Connect timeout**: giới hạn thời gian thiết lập kết nối trong API kết nối.
- **Read timeout / SO_TIMEOUT**: giới hạn chờ của một lần đọc blocking phù hợp.
- **Accept timeout**: giới hạn chờ kết nối mới cho listener.
- **Request deadline**: giới hạn tổng thời gian thực hiện tác vụ, do tầng ứng dụng/framework thiết kế.
- **Idle timeout**: giới hạn thời gian không có hoạt động, có thể được triển khai ở tầng server/proxy/framework.
- **TCP keepalive**: cơ chế phát hiện peer chết sau những khoảng thời gian lớn tùy cấu hình; **không phải** request timeout ngắn.

Đặt `setSoTimeout(2000)` **không** thay thế deadline tổng. Nếu có yêu cầu “response phải hoàn tất trong 5 giây”, hệ thống cần chính sách deadline theo đồng hồ đơn điệu, ngân sách cho các bước và cơ chế hủy/đóng khi hết hạn tương ứng.

## 24. `SocketTimeoutException` và `InterruptedIOException` không giống `InterruptedException`

Một nhầm lẫn tinh tế: `SocketTimeoutException extends InterruptedIOException`, nhưng điều đó **không** có nghĩa mỗi timeout là do thread bị interrupt.

- `InterruptedException` là checked exception thường liên quan tác vụ chờ bị tín hiệu interrupt, chẳng hạn `Thread.sleep()`.
- `InterruptedIOException` biểu thị thao tác I/O bị gián đoạn, có field `bytesTransferred` cho một số ngữ cảnh.
- `SocketTimeoutException` là một subclass của `InterruptedIOException` dùng để báo thao tác socket **hết thời hạn chờ**.
- **Không tự gọi `Thread.currentThread().interrupt()` chỉ vì bắt `SocketTimeoutException`.** Timeout không tự chứng minh thread đã nhận yêu cầu hủy.

Trong một số API I/O và channel khác, thread interruption có thể dẫn tới những exception chuyên biệt, chẳng hạn `java.nio.channels.ClosedByInterruptException`. Đừng ép tất cả thành `SocketTimeoutException`; hãy xử lý theo contract của API dùng thực tế.

Field `InterruptedIOException.bytesTransferred` không nên được coi là “tổng byte của toàn request đã được gửi thành công tới server” trong mọi tình huống. Nếu giao thức cần xác nhận chính xác, dùng cơ chế acknowledgment và state ở tầng ứng dụng.

## 25. Khung client TCP có timeout và đóng tài nguyên

Đây là một **phương thức minh họa**, đủ cú pháp Java nhưng không kèm server/`main`, nên không gắn stdout cố định. Nó minh họa cách cấu hình **connect timeout** riêng với **read timeout**, và quản lý socket bằng try-with-resources:

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

class SimpleTcpClient {
    static int readOneByte(String host, int port) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(
                    new InetSocketAddress(host, port),
                    1500);
            socket.setSoTimeout(2000);
            return socket.getInputStream().read();
        }
    }
}
```

Ý nghĩa:

1. `new Socket()` tạo socket chưa kết nối.
2. `connect(..., 1500)` áp thời hạn chờ riêng cho thiết lập TCP.
3. `setSoTimeout(2000)` giới hạn chờ lần đọc blocking sau đó.
4. `read()` trả byte hoặc `-1` khi EOF, hoặc ném lỗi I/O/timeout.
5. `try-with-resources` tự gọi `close()` khi thoát bình thường hoặc do exception.

**Không dùng nó như client giao thức hoàn chỉnh**: nó không tạo request, không xác nhận framing, không đọc response dài, không có deadline toàn tác vụ và chưa có retry policy.

Nếu phương thức thực tế cần trả về “không có dữ liệu”, trả `-1` có thể giữ nguyên hợp đồng InputStream; tầng caller phải hiểu `-1` khác với timeout.

## 26. Xử lý exception theo loại tại ranh giới có trách nhiệm

Một pattern phục vụ kiểm soát lỗi có thể là:

```java
try {
    performNetworkOperation();
} catch (SocketTimeoutException e) {
    handleTimeout(e);
} catch (UnknownHostException e) {
    handleNameResolutionFailure(e);
} catch (ConnectException e) {
    handleConnectFailure(e);
} catch (SocketException e) {
    handleOtherSocketFailure(e);
} catch (IOException e) {
    handleOtherIoFailure(e);
}
```

Đây là **mã khung minh họa** với các method xử lý cần được định nghĩa, import `java.io.*` và `java.net.*` tương ứng. Thứ tự quan trọng:

- `ConnectException` phải đứng trước `SocketException`.
- `SocketTimeoutException` và `UnknownHostException` không nằm dưới `SocketException`.
- `IOException` đứng cuối do là lớp cha chung.

Nhưng **không phải mọi tầng đều nên catch đủ sáu nhánh**. Nếu tầng repository không có cách phục hồi, nó có thể khai báo `throws IOException`; tầng API/job có thông tin request, policy và khả năng phản hồi sẽ xử lý.

Handler phải phân biệt **đã phục hồi thật sự** và **đang chuyển lỗi thành phản hồi thất bại**. Catch để ghi log rồi trả dữ liệu giả là một bug nếu caller nghĩ thao tác thành công.

## 27. Log có cấu trúc: lưu ngoại lệ chứ không chỉ message

Với lỗi mạng, chỉ in `e.getMessage()` thường không đủ vì:

- Message có thể khác theo JVM/OS.
- Nó không cho biết loại exception chính xác.
- Nó không luôn cho biết cause hoặc suppressed exceptions.
- Không có stack trace khi chỉ lưu một `String`.
- Không có ngữ cảnh thao tác: connect, read, write, accept hay DNS.
- Không có request ID và thông tin thời hạn chờ đang dùng.

Một log hữu ích nên bao gồm **địa chỉ/endpoint ở mức đã được phép lưu, tên thao tác, timeout cấu hình, attempt number, request correlation ID, loại exception và Throwable gốc**.

Pseudocode dành cho thư viện logging có overload nhận Throwable:

```java
// Pseudocode; chữ ký phụ thuộc logging framework đang dùng:
logger.error("Network operation failed: requestId={}, phase={}",
             requestId, phase, exception);
```

Đây **không** phải code Java chuẩn tự biên dịch nếu chưa có logger và các biến. Mục đích là nhấn mạnh: truyền **object exception** khi framework hỗ trợ, để giữ stack trace/cause/suppressed.

Không đưa access token, cookie, password, chuỗi truy vấn nhạy cảm hoặc payload cá nhân vào log chỉ để có thêm ngữ cảnh.

## 28. Bọc lỗi bằng cause khi đổi abstraction

Có thể một API nghiệp vụ không muốn phơi trực tiếp `IOException` mà dùng một custom exception:

```java
class NetworkOperationException extends RuntimeException {
    NetworkOperationException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Ví dụ gọi:

```java
try {
    sendRequest();
} catch (IOException e) {
    throw new NetworkOperationException(
            "Không thực hiện được yêu cầu", e);
}
```

Cả hai là **đoạn minh họa**, `sendRequest()` và `IOException` cần có trong phạm vi, không gắn stdout.

Khi bọc:

- Exception wrapper mang **loại và thông điệp của tầng mới**.
- `wrapper.getCause()` giữ object `IOException`, kể cả `SocketTimeoutException` hay `ConnectException`.
- Stack trace của wrapper được ghi tại nơi tạo wrapper; cause giữ trace của nó.
- Mọi suppressed exceptions đang nằm trên cause **không tự chuyển** lên `wrapper.getSuppressed()`.
- API caller giờ thấy unchecked `NetworkOperationException`, khác với checked `IOException`.

**Không bọc chỉ bằng `new RuntimeException(e.getMessage())` nếu cần giữ nguyên nhân**. Lựa chọn checked hay unchecked cho wrapper phải là quyết định hợp đồng, không chỉ để tránh compiler bắt viết `throws`.

## 29. Ví dụ Java 17: bảo toàn cause từ timeout

Ví dụ này **mô phỏng timeout** để đầu ra không phụ thuộc môi trường mạng; nó tập trung vào wrapping/cause.

Lưu **`NetworkCauseDemo.java`**:

```java
import java.io.IOException;
import java.net.SocketTimeoutException;

public class NetworkCauseDemo {
    static class ServiceNetworkException extends RuntimeException {
        ServiceNetworkException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void lowLevelRead() throws IOException {
        throw new SocketTimeoutException("read timed out");
    }

    static void fetch() {
        try {
            lowLevelRead();
        } catch (IOException e) {
            throw new ServiceNetworkException("Fetch thất bại", e);
        }
    }

    public static void main(String[] args) {
        try {
            fetch();
        } catch (ServiceNetworkException e) {
            System.out.println("Wrapper: " + e.getMessage());
            System.out.println("Cause class: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
            System.out.println("Cause là IOException: "
                    + (e.getCause() instanceof IOException));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 NetworkCauseDemo.java
java NetworkCauseDemo
```

**Stdout chính xác:**

```text
Wrapper: Fetch thất bại
Cause class: SocketTimeoutException
Cause message: read timed out
Cause là IOException: true
```

`ServiceNetworkException` là một loại exception ứng dụng mới. `getCause()` vẫn giữ `SocketTimeoutException` và thông điệp gốc. Trong hệ thống thực, việc quyết định có retry hay không cần **ngữ cảnh**, không chỉ kiểm tra cause có `SocketTimeoutException`.

Nếu một lỗi network đã được bọc nhiều lần, tầng xử lý có thể cần duyệt cause chain cẩn thận (tránh vòng lặp do cấu trúc lỗi tùy chỉnh không chuẩn).

## 30. Try-with-resources và lỗi khi đóng socket

Cả `Socket` và `ServerSocket` đều hỗ trợ `AutoCloseable`, nên có thể dùng:

```java
try (Socket socket = new Socket()) {
    // connect, read, write...
}
```

Đây là **mã khung minh họa**. Khi rời scope, Java cố đóng socket. Nếu thao tác chính đã ném exception và `close()` cũng ném exception, Java có thể ghi lỗi đóng vào **suppressed exceptions** của lỗi chính, theo cơ chế try-with-resources.

Hệ quả:

- Khi chẩn đoán, có thể cần xem `primary.getSuppressed()` để biết cleanup cũng thất bại.
- `getCause()` và `getSuppressed()` không đồng nghĩa.
- Không tự nuốt lỗi cleanup chỉ để log trông sạch hơn.
- Khi socket hết khả năng sử dụng, đóng tài nguyên và tạo kết nối mới theo hợp đồng có thể đúng hơn cố giữ object cũ.
- `SocketTimeoutException` do **read SO_TIMEOUT** không tự bảo đảm socket đã hỏng hoặc đã đóng, nhưng tầng ứng dụng vẫn phải quản lý các điều kiện từ giao thức.

Không suy rằng chỉ vì socket được đặt trong try-with-resources thì mọi dữ liệu ứng dụng đã được server xác nhận hoặc mọi side effect đã rollback.

## 31. Những điều không thể suy từ trạng thái `Socket`

Một số method có tên dễ khiến người đọc lầm tưởng là kiểm tra “sức khỏe kết nối”:

- `socket.isConnected()`: cho biết socket đã từng kết nối thành công, **không** là probe liên tục xác nhận peer còn sống.
- `socket.isClosed()`: kiểm tra đối tượng socket đã bị đóng ở phía local hay chưa.
- `socket.isInputShutdown()` / `isOutputShutdown()`: trạng thái shutdown các hướng local.
- `input.available()`: ước lượng byte có thể đọc không blocking, **không** dùng để xác định EOF hoặc remote đã gửi xong.
- `socket.getSoTimeout()`: đọc cấu hình read timeout, **không** cho biết deadline tổng hoặc thời gian còn lại của một request.

Nếu cần **health check**, nên có cơ chế ở tầng protocol: ping/pong phù hợp, request kiểm tra sức khỏe, heartbeat, hoặc xác thực kết quả I/O thực tế; vẫn phải chấp nhận mạng có độ trễ và lỗi.

Không có API đồng bộ nào có thể cam kết trạng thái peer **sẽ vẫn đúng** tại thời điểm thao tác tiếp theo trong một hệ thống phân tán.

## 32. Phân biệt với Java NIO và Java HTTP Client

### 32.1. Java NIO channels

`java.nio.channels.SocketChannel` và các channel khác có API I/O riêng; tùy tình huống có thể xuất hiện những loại exception như:

- `ClosedChannelException`,
- `AsynchronousCloseException`,
- `ClosedByInterruptException`,
- các `IOException` thích hợp.

**Đừng mặc định rằng `Socket.setSoTimeout` điều khiển mọi thao tác NIO non-blocking hoặc selector**. Trong thiết kế NIO, timeout thường được quản lý thông qua selector, deadline hoặc API tầng cao phù hợp. Xem hợp đồng cụ thể của channel và chế độ blocking/non-blocking.

### 32.2. `java.net.http.HttpClient`

Java 11+ có HTTP Client chuẩn `java.net.http.HttpClient`. Timeout theo API này có exception chuyên biệt:

- `java.net.http.HttpTimeoutException`: thuộc nhánh `IOException`.
- `java.net.http.HttpConnectTimeoutException`: là lớp con của `HttpTimeoutException`, dùng trong ngữ cảnh connect timeout của HTTP Client.

Các loại này **không phải `SocketTimeoutException`**. Nếu đang dùng `HttpClient`, phải dựa vào **API và loại exception của HTTP Client**, không áp mã catch dành riêng cho classic `Socket` lên tất cả lời gọi HTTP.

Một số thư viện HTTP khác có cơ chế wrapper, retry, async exception riêng; tài liệu của thư viện luôn quan trọng hơn suy luận từ các lớp socket thô.

## 33. Lỗi TLS/SSL là một lớp khác

Khi dùng `SSLSocket` hoặc HTTPS, có thêm bước **TLS handshake**, xác minh chứng chỉ và giao thức mã hóa. Những lỗi có thể xuất hiện bao gồm `javax.net.ssl.SSLException` và các lớp con, cùng một số lỗi socket/I/O thấp hơn.

Không được kết luận:

- Có `SSLException` nghĩa là DNS sai.
- Có `SocketTimeoutException` nghĩa là chứng chỉ TLS không hợp lệ.
- TCP connect thành công là TLS handshake chắc chắn thành công.
- Timeout TCP read tương đương timeout toàn bộ handshake và HTTP response trong mọi API.

Trong hệ thống thật, mỗi tầng cần ghi ngữ cảnh: **resolve → connect → TLS handshake → write request → read response → parse**. Điều này giúp phân biệt lỗi cấu hình, lỗi mạng và lỗi protocol.

Nếu mục tiêu chỉ là hiểu `SocketException`/`SocketTimeoutException` ở Java core, hãy coi TLS/HTTP là **tầng bổ sung**, không nhầm các exception của chúng với toàn bộ các dạng socket errors.

## 34. Không cố dựa vào message hệ điều hành để viết test

Một test kiểu:

```java
assertEquals("Connection refused", exception.getMessage());
```

là **đoạn minh họa phản ví dụ** (giả định framework assert). Message có thể khác giữa Linux, Windows, JDK và ngữ cảnh. Những kiểm tra ổn định hơn:

- Loại exception hoặc superclass phù hợp.
- Mã lỗi ở **tầng domain** nếu ứng dụng tự định nghĩa.
- Cause của wrapper khi chuyển abstraction.
- Số lần retry hay chính sách fallback được thực hiện.
- Trạng thái tài nguyên sau failure.
- Giới hạn timeout ở mức hợp đồng, tránh assert con số thời gian chính xác tuyệt đối.

Khi muốn test phân loại lỗi, có thể **tạo exception nhân tạo** như `new ConnectException("simulated")`. Khi cần integration test socket, dùng **loopback và cổng ephemeral** để giảm phụ thuộc mạng, nhưng vẫn phải đánh dấu những giả định môi trường.

## 35. Test timeout và tránh flaky test

Timeout test dễ không ổn định nếu phụ thuộc scheduler hoặc tải máy. Những cách giảm rủi ro:

1. Tách **unit test logic** khỏi **integration test thực sự tạo socket**.
2. Unit test bằng exception nhân tạo nếu đang kiểm tra chính sách phân loại/retry.
3. Với socket thật, dùng **loopback** và `ServerSocket(0)` thay vì dịch vụ Internet hoặc port cố định.
4. Không kiểm tra `elapsedMillis == configuredTimeout`; thời gian thực có overhead.
5. Không ngủ mù quáng để chờ một thread chưa chắc đã bắt đầu; dùng `CountDownLatch` hoặc cơ chế đồng bộ khi cần threads.
6. Không biến một timeout test thành deadlock vì client/server cùng chờ nhau theo giao thức sai.
7. Đảm bảo đóng resource trong `try-with-resources`, kể cả khi test thất bại.
8. Tránh “port chắc chắn không ai dùng”; các port luôn chịu race và cấu hình môi trường.
9. Nếu cần kiểm thử retry, dùng server giả có điều khiển request ID và hành vi phản hồi, không phụ thuộc lỗi Internet ngẫu nhiên.
10. Dành thời hạn hợp lý cho CI và ghi rõ test cần khả năng bind/connect loopback.

**Test socket thực phản ánh runtime/network behavior; unit test nhân tạo phản ánh code phân loại.** Cả hai có giá trị nhưng không nên thay thế khái niệm của nhau.

## 36. Những sai lầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`SocketTimeoutException extends SocketException`.” | Sai. Nó extends `InterruptedIOException`, còn `SocketException` extends `IOException` trực tiếp. |
| “Bắt `SocketException` sẽ bắt mọi timeout.” | Sai. Cần bắt `SocketTimeoutException` hoặc `IOException` phù hợp. |
| “`ConnectException` là nhánh riêng ngoài SocketException.” | Sai. `ConnectException` là subclass của `SocketException`. |
| “`UnknownHostException` là subclass SocketException.” | Sai. Nó thuộc `IOException`, không nằm dưới SocketException. |
| “Timeout nghĩa là server chắc chắn không xử lý request.” | Sai. Thao tác có thể đã được xử lý nhưng phản hồi chưa tới. |
| “Read timeout là deadline cho toàn bộ request.” | Sai. SO_TIMEOUT liên quan thao tác đọc blocking, không tự giới hạn toàn workflow. |
| “`setSoTimeout` đặt timeout của `connect`.” | Sai. Dùng `connect(endpoint, timeout)` cho kết nối. |
| “`SocketTimeoutException` luôn khiến socket đóng.” | Sai. Read timeout trên socket blocking không tự đóng socket. |
| “`Socket.isConnected() == true` nghĩa là peer đang online.” | Không. Nó không phải health check realtime. |
| “`available() == 0` nghĩa là đã EOF.” | Sai. Nó không chứng minh peer đóng hay stream kết thúc. |
| “`read() == -1` nghĩa là timeout.” | Sai. `-1` là EOF, khác exception timeout. |
| “Socket reset và socket closed đều là lỗi DNS.” | Sai. Phải xem thời điểm, loại lỗi và thao tác. |
| “UDP send thành công bảo đảm dữ liệu đã nhận.” | Sai. UDP không có đảm bảo ấy theo mặc định. |
| “Mọi timeout nên retry ngay mãi mãi.” | Sai. Cần giới hạn, backoff, idempotency và deadline tổng. |
| “Read timeout có nghĩa phải gọi `Thread.interrupt()`.” | Sai. Timeout không phải InterruptedException của thread. |
| “Message `Connection reset` có thể dùng làm mã lỗi ổn định.” | Không. Message phụ thuộc runtime/hệ điều hành và tình huống. |
| “Java HTTP Client timeout luôn ném SocketTimeoutException.” | Không. `java.net.http` có `HttpTimeoutException`/`HttpConnectTimeoutException`. |
| “Chỉ log message đã đủ để điều tra socket error.” | Thường không; cần Throwable, cause và ngữ cảnh. |
| “Catch IOException rồi trả thành công giúp ứng dụng bền hơn.” | Sai nếu chưa phục hồi đúng; đó có thể là thành công giả. |
| “Có try-with-resources là server đã xử lý giao dịch an toàn.” | Không. Nó quản lý đóng resource, không xác nhận side effect ở peer. |

## 37. Câu hỏi tự kiểm tra

**1.** `SocketException` có checked không?  
**Đáp án:** Có, vì kế thừa `IOException`.

**2.** `SocketTimeoutException` có phải subclass của `SocketException`?  
**Đáp án:** Không. Nó là subclass của `InterruptedIOException`, cũng thuộc `IOException`.

**3.** Catch `SocketException` có bắt được `ConnectException` không?  
**Đáp án:** Có, vì `ConnectException extends SocketException`.

**4.** Catch `SocketException` có bắt được `UnknownHostException` không?  
**Đáp án:** Không. `UnknownHostException` nằm dưới `IOException` theo nhánh khác.

**5.** Dùng API nào để đặt timeout kết nối classic `Socket`?  
**Đáp án:** `socket.connect(endpoint, timeoutMillis)`.

**6.** Dùng API nào để giới hạn thời gian chờ `Socket.getInputStream().read()`?  
**Đáp án:** `socket.setSoTimeout(timeoutMillis)` trước thao tác đọc blocking phù hợp.

**7.** `ServerSocket.setSoTimeout` ảnh hưởng thao tác nào?  
**Đáp án:** Thời gian `ServerSocket.accept()` chờ kết nối mới.

**8.** `DatagramSocket.setSoTimeout` được dùng với thao tác nào?  
**Đáp án:** `DatagramSocket.receive(...)`.

**9.** Sau một read timeout, socket có chắc đã bị đóng không?  
**Đáp án:** Không. Timeout đọc không tự buộc đóng socket; ứng dụng phải quyết định tiếp tục hay đóng theo protocol.

**10.** `InputStream.read()` trả `-1` khác gì `SocketTimeoutException`?  
**Đáp án:** `-1` là EOF; timeout là exception do hết thời gian chờ thích hợp.

**11.** `ConnectException` thường gắn với giai đoạn nào?  
**Đáp án:** Thiết lập kết nối, thường gặp khi endpoint từ chối hoặc không thể thiết lập kết nối theo cơ chế OS.

**12.** `BindException` xảy ra ở bên client đọc dữ liệu hay lúc chuẩn bị endpoint local?  
**Đáp án:** Chủ yếu ở thao tác bind endpoint local.

**13.** DNS/name resolution failure có nhất thiết là `SocketException`?  
**Đáp án:** Không. `UnknownHostException` là một subclass riêng của `IOException`.

**14.** `setSoTimeout(0)` có nghĩa “ngay lập tức timeout” không?  
**Đáp án:** Không. `0` có nghĩa không đặt giới hạn chờ SO_TIMEOUT cho thao tác liên quan.

**15.** Nếu server đã xử lý một lệnh tạo giao dịch nhưng client timeout khi chờ response, có thể retry vô điều kiện không?  
**Đáp án:** Không. Cần idempotency key, kiểm tra trạng thái và chính sách retry có giới hạn.

**16.** `Socket.isConnected()` có là health check peer hiện tại không?  
**Đáp án:** Không. Nó phản ánh trạng thái đã từng kết nối, không xác nhận peer còn phục vụ.

**17.** Tại sao không dùng `InputStream.available() == 0` để kết luận EOF?  
**Đáp án:** Nó chỉ báo số byte có thể đọc không blocking theo một ước lượng; có thể chưa có dữ liệu nhưng stream chưa kết thúc.

**18.** `SocketTimeoutException` kế thừa `InterruptedIOException` có nghĩa thread phải bị interrupt không?  
**Đáp án:** Không. Timeout là điều kiện chờ, không tự chứng minh thread đã nhận tín hiệu interrupt.

**19.** Khi Java HTTP Client có timeout, những loại nào có thể liên quan?  
**Đáp án:** `HttpTimeoutException` và `HttpConnectTimeoutException` theo hợp đồng `java.net.http`, không mặc định là SocketTimeoutException.

**20.** Vì sao cần dùng `getCause()` khi bọc lỗi network thành domain exception?  
**Đáp án:** Để giữ ngoại lệ gốc, loại lỗi và trace, tránh mất thông tin khi đổi abstraction.

**21.** Hai lần gọi `read()` lần lượt nhận dữ liệu trước mỗi read timeout, nhưng tổng thời gian vượt deadline nghiệp vụ. SO_TIMEOUT có tự dừng request không?  
**Đáp án:** Không nhất thiết. Cần deadline tổng ở tầng ứng dụng.

**22.** Khi debug lỗi mạng, chỉ biết message `"Broken pipe"` đã đủ chưa?  
**Đáp án:** Không. Cần thao tác đang gọi, trạng thái connection, cause, OS/JDK và kết quả nghiệp vụ.

**23.** Vì sao test kết nối tới port “chắc chắn trống” không đáng tin?  
**Đáp án:** Một tiến trình khác có thể sử dụng port, tạo race và sự khác biệt giữa các môi trường.

**24.** Có thể dùng loopback để tự học timeout mà không cần Internet không?  
**Đáp án:** Có, với `ServerSocket(0)` và `Socket` cùng tiến trình, nếu hệ thống cho phép TCP loopback.

## 38. Checklist xử lý lỗi mạng

Trước khi thiết kế hoặc review một lời gọi Java networking:

1. **Xác định API đang dùng:** classic `Socket`, `ServerSocket`, `DatagramSocket`, NIO hay HTTP Client.
2. **Nắm phân cấp exception:** `SocketTimeoutException` không nằm trong `SocketException`.
3. **Ghi rõ giai đoạn:** resolve, bind, connect, TLS, write, read, accept hay receive.
4. **Phân biệt timeout và EOF:** `read() == -1` không phải SocketTimeoutException.
5. **Đặt connect timeout nếu cần:** qua `connect(endpoint, timeout)`.
6. **Đặt read timeout riêng:** qua `Socket.setSoTimeout` khi dùng classic blocking socket.
7. **Đặt accept timeout riêng cho listener:** qua `ServerSocket.setSoTimeout` khi phù hợp.
8. **Nhớ timeout không tự là deadline tổng:** thiết kế request budget/deadline nếu cần.
9. **Không dùng `isConnected()` hay `available()` như health check đáng tin tuyệt đối.**
10. **Đánh giá idempotency trước retry:** request có thể đã được thực thi bên server.
11. **Giới hạn retry và dùng backoff/jitter hợp lý.**
12. **Giữ request ID/correlation ID và trạng thái server** để phân biệt kết quả chưa rõ.
13. **Không nuốt exception rồi trả thành công giả.**
14. **Khi wrapping, truyền cause:** `new XxxException(message, cause)`.
15. **Sử dụng try-with-resources** để đóng socket đúng vòng đời.
16. **Quan sát suppressed exception** nếu thao tác chính và cleanup cùng thất bại.
17. **Không phân loại chỉ bằng message OS/JDK.**
18. **Tránh log credential, token, query/payload nhạy cảm.**
19. **Phân biệt UDP với TCP:** không giả định UDP có xác nhận giao hàng.
20. **Xử lý thread interruption riêng** với timeout socket.
21. **Viết unit test loại lỗi không phụ thuộc mạng**, integration test loopback riêng.
22. **Không khẳng định thời gian chờ chính xác tuyệt đối trong test.**
23. **Nếu dùng HttpClient/NIO, đọc contract riêng**, không áp quy tắc Socket cũ máy móc.
24. **Rà tình huống đồng thời:** socket có thể bị đóng bởi thread khác; kiểm tra trạng thái không loại bỏ race.
25. **Công bố thất bại ở đúng ranh giới**: API cần xử lý hoặc khai báo checked exception theo trách nhiệm của từng tầng.

## 39. Kết luận

`SocketException` và `SocketTimeoutException` cùng thuộc họ checked `IOException` nhưng **khác nhánh và khác ý nghĩa**. `SocketException` biểu thị một nhóm lỗi socket nói chung và có những subclass như `ConnectException`, `BindException`, `NoRouteToHostException`. `SocketTimeoutException` kế thừa `InterruptedIOException` và báo một thao tác socket chờ quá giới hạn thời gian cấu hình; **`catch (SocketException)` không bắt được nó**.

Khi lập trình TCP/UDP thực tế, hãy đặt timeout đúng tầng: **connect timeout** cho kết nối, **SO_TIMEOUT** cho đọc hoặc nhận/accept thích hợp; phân biệt **EOF (`-1`)** với timeout và không coi message hệ điều hành là mã lỗi ổn định. Đọc/ghi socket còn phụ thuộc vào giao thức, trạng thái tài nguyên và khả năng request đã có side effect phía server.

Thiết kế xử lý tốt không dừng ở việc catch đúng loại: cần **deadline tổng, idempotency, retry có giới hạn, logging đủ ngữ cảnh, bảo toàn cause, quản lý resource và kiểm thử tách biệt logic lỗi khỏi môi trường mạng**. Đây là nền tảng để dùng Java networking an toàn và chẩn đoán sự cố đáng tin.
