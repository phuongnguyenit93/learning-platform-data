# Thiết lập connect timeout, read timeout và deadline nghiệp vụ

Trong Java 21, timeout giúp giới hạn thời gian một thao tác I/O chờ kết quả. Tuy nhiên, **connect timeout**, **read timeout** và **deadline nghiệp vụ** giải quyết ba phạm vi khác nhau. Connect timeout giới hạn thời gian thiết lập kết nối; read timeout giới hạn thời gian chờ dữ liệu trong một lần đọc; deadline giới hạn tổng thời gian mà một công việc được phép sử dụng qua nhiều bước.

Nếu chỉ đặt read timeout cho từng lần đọc, một đối tác mạng có thể gửi dữ liệu nhỏ đều đặn để kéo dài toàn bộ giao dịch lâu hơn mong muốn. Khi nghiệp vụ yêu cầu tổng thời gian tối đa, hãy dùng một deadline tuyệt đối dựa trên đồng hồ monotonic và tính thời gian còn lại trước mỗi thao tác có thể chặn.

## 1. Phân biệt ba loại giới hạn thời gian

| Loại giới hạn | Phạm vi | Ví dụ API | Điều nó không bảo đảm |
| --- | --- | --- | --- |
| Connect timeout | Thời gian thiết lập kết nối mạng. | `Socket.connect(address, timeout)`, `HttpClient.Builder.connectTimeout(...)` | Không giới hạn toàn bộ thời gian xử lý request; DNS có thể nằm ngoài timeout của `Socket.connect`. |
| Read timeout | Thời gian chờ dữ liệu trong một thao tác đọc hoặc chờ chấp nhận kết nối, tùy API. | `Socket.setSoTimeout(...)`, `URLConnection.setReadTimeout(...)`, `ServerSocket.setSoTimeout(...)` | Không giới hạn tổng thời gian đọc nhiều lần hoặc thời gian xử lý nghiệp vụ. |
| Request timeout / deadline | Tổng thời gian chờ cho một request hoặc một công việc gồm nhiều bước. | `HttpRequest.Builder.timeout(...)`, deadline tự quản lý bằng `System.nanoTime()` | Không tự hủy mọi công việc CPU hoặc mọi thao tác I/O nếu API không hỗ trợ timeout/cancellation tương ứng. |

Timeout thường được biểu diễn bằng mili giây hoặc `Duration`. Với các API nhận `int` mili giây, giá trị `0` thường có nghĩa là chờ vô hạn; với API nhận `Duration`, quy tắc khác nhau theo phương thức và thường yêu cầu duration dương. Luôn kiểm tra hợp đồng của API cụ thể.

## 2. Thiết lập connect timeout với `Socket`

`Socket.connect(SocketAddress endpoint, int timeout)` giới hạn thời gian chờ thiết lập kết nối TCP. Timeout tính bằng mili giây; `0` nghĩa là chờ vô hạn. Nếu hết thời gian, phương thức ném `SocketTimeoutException`.

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class ConnectTimeoutExample {
    public static void main(String[] args) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("127.0.0.1", 8080), 2_000);
            System.out.println("Connected: " + socket.getRemoteSocketAddress());
        } catch (SocketTimeoutException e) {
            System.out.println("Connection timed out");
        } catch (IOException e) {
            System.out.println("Connection failed: " + e.getMessage());
        }
    }
}
```

Tạo `Socket` rỗng rồi gọi `connect(endpoint, timeout)` giúp chỉ rõ giới hạn thời gian. Nếu dùng constructor như `new Socket(host, port)`, không có tham số timeout để ứng dụng đặt giới hạn connect trực tiếp.

Timeout âm gây `IllegalArgumentException`. Không nên truyền `0` nếu nghiệp vụ yêu cầu giới hạn; `0` có nghĩa là không giới hạn thời gian chờ. `Socket.connect` chỉ giới hạn giai đoạn kết nối sau khi endpoint đã được xác định. Nếu tạo `InetSocketAddress` từ hostname, bước phân giải DNS có thể xảy ra trước khi `connect()` bắt đầu và không được giới hạn bởi tham số timeout này. Khi cần quản lý cả DNS, phải thiết kế riêng bước phân giải tên hoặc dùng resolver có chính sách timeout phù hợp.

## 3. Thiết lập read timeout với `Socket.setSoTimeout()`

Sau khi kết nối, có thể đặt read timeout bằng `Socket.setSoTimeout(int timeout)`. Giá trị là mili giây; `0` nghĩa là chờ vô hạn. Khi thao tác đọc từ `InputStream` chờ quá thời gian, nó ném `SocketTimeoutException`. Socket vẫn còn hợp lệ sau read timeout và có thể tiếp tục được sử dụng nếu giao thức cho phép.

```java
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class ReadTimeoutExample {
    public static void main(String[] args) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("127.0.0.1", 8080), 2_000);
            socket.setSoTimeout(3_000);

            InputStream input = socket.getInputStream();
            int firstByte = input.read();

            System.out.println("Received: " + firstByte);
        } catch (SocketTimeoutException e) {
            System.out.println("No data arrived within the read timeout");
        } catch (java.io.IOException e) {
            System.out.println("Socket error: " + e.getMessage());
        }
    }
}
```

`setSoTimeout()` chỉ tác động đến thao tác đọc trên socket; nó không đặt connect timeout và cũng không đặt write timeout. Giá trị âm gây `IllegalArgumentException`. Nếu timeout xảy ra, exception được ném tại lần đọc bị hết hạn; socket không tự đóng chỉ vì read timeout.

### Read timeout không phải deadline cho toàn bộ response

Read timeout được áp dụng cho mỗi lần đọc có thể chặn. Nếu một lần đọc nhận được dữ liệu trước khi timeout, lần đọc kế tiếp lại có thể chờ thêm tối đa khoảng timeout đó. Vì vậy, nhiều lần đọc có thể kéo dài tổng thời gian vượt xa giá trị `SO_TIMEOUT`.

Ví dụ, một server gửi một byte mỗi hai giây có thể khiến client tiếp tục đọc mãi nếu read timeout được đặt là ba giây. Mỗi lần `read()` đều nhận dữ liệu trước khi hết hạn, dù toàn bộ response có thể mất nhiều phút.

Nếu nghiệp vụ cần tổng thời gian tối đa, phải cập nhật timeout theo thời gian còn lại của deadline trước mỗi lần đọc; xem phần deadline bên dưới.

## 4. Thiết lập timeout cho `ServerSocket.accept()`

`ServerSocket.setSoTimeout(int timeout)` giới hạn thời gian chờ một kết nối đến tại `accept()`. Giá trị tính bằng mili giây; `0` nghĩa là chờ vô hạn. Khi hết thời gian, `accept()` ném `SocketTimeoutException`, nhưng `ServerSocket` vẫn mở để có thể tiếp tục chờ ở lần sau.

```java
import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class AcceptTimeoutExample {
    public static void main(String[] args) {
        try (ServerSocket server = new ServerSocket(8080)) {
            server.setSoTimeout(5_000);

            try (Socket client = server.accept()) {
                System.out.println("Accepted: " + client.getRemoteSocketAddress());
            } catch (SocketTimeoutException e) {
                System.out.println("No client connected within five seconds");
            }
        } catch (IOException e) {
            System.out.println("Server socket error: " + e.getMessage());
        }
    }
}
```

Đây là timeout cho thao tác chấp nhận kết nối, không phải read timeout của socket client được trả về từ `accept()`. Nếu cần giới hạn đọc dữ liệu từ client, đặt `setSoTimeout()` trên chính socket client sau khi chấp nhận.

## 5. Thiết lập timeout với `URLConnection`

`URLConnection` cung cấp hai cấu hình riêng:

- `setConnectTimeout(int timeout)`: thời gian tối đa chờ mở communications link.
- `setReadTimeout(int timeout)`: thời gian tối đa chờ dữ liệu khi đọc từ input stream.

Hai giá trị đều tính bằng mili giây; `0` nghĩa là vô hạn. Giá trị âm gây `IllegalArgumentException`. Một số protocol handler có thể không triển khai đầy đủ các timeout này, vì vậy cần kiểm tra tài liệu của protocol đang sử dụng.

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URLConnection;

public class UrlConnectionTimeoutExample {
    public static void main(String[] args) throws IOException {
        var url = URI.create("https://example.com/").toURL();
        URLConnection connection = url.openConnection();
        connection.setConnectTimeout(2_000);
        connection.setReadTimeout(4_000);

        try (InputStream input = connection.getInputStream()) {
            byte[] buffer = input.readNBytes(4_096);
            System.out.println("Read " + buffer.length + " bytes");
        }
    }
}
```

Phải đặt timeout trước khi thao tác làm kết nối được thiết lập, chẳng hạn trước `connect()`, `getInputStream()` hoặc `getOutputStream()`. `URLConnection` vẫn là API chuẩn trong Java 21 cho các protocol handler tương ứng. Với ứng dụng HTTP mới, `java.net.http.HttpClient` thường là lựa chọn rõ ràng hơn vì hỗ trợ `Duration`, HTTP/2 và API bất đồng bộ.

## 6. Timeout với `java.net.http.HttpClient`

Java 21 có HTTP Client API chuẩn trong module `java.net.http`. Có thể cấu hình connect timeout ở client và request timeout ở từng request:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpClientTimeoutExample {
    public static void main(String[] args) throws java.io.IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/status"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println(response.statusCode());
        System.out.println(response.body());
    }
}
```

`HttpClient.Builder.connectTimeout(Duration)` giới hạn thời gian thiết lập kết nối mới. Timeout này có thể không được áp dụng nếu request sử dụng một connection đã được thiết lập và tái sử dụng. Nếu không cấu hình, connect timeout mặc định là không giới hạn.

`HttpRequest.Builder.timeout(Duration)` đặt thời gian chờ cho request. Nếu không nhận được response trong thời gian quy định, API ném `HttpTimeoutException`. Nếu không cấu hình request timeout, thời gian chờ mặc định là không giới hạn. Duration phải dương; giá trị bằng không hoặc âm không hợp lệ.

`HttpConnectTimeoutException` là một dạng `HttpTimeoutException` dành cho timeout khi kết nối. Với `client.send(...)`, các timeout được báo qua exception (ngoài `InterruptedException` và các lỗi I/O khác). Với `sendAsync(...)`, future hoàn tất bất thường với nguyên nhân tương ứng.

### Request timeout và streaming response body

Với `BodyHandlers.ofString()` hoặc handler thu thập body hoàn chỉnh, `send()` trả về sau khi body được xử lý xong theo handler đó. Với `BodyHandlers.ofInputStream()`, response có thể được trả về cùng một `InputStream` để ứng dụng đọc body sau đó. Khi đọc body streaming, cần quản lý deadline đọc riêng và đóng stream khi không còn sử dụng; không xem request timeout như một read timeout socket có thể đặt lại cho từng lần đọc stream.

## 7. Deadline nghiệp vụ: giới hạn tổng thời gian qua nhiều bước

Deadline là một thời điểm kết thúc tuyệt đối. Mỗi thao tác lấy thời gian còn lại bằng cách trừ thời điểm hiện tại khỏi deadline. Khi thời gian còn lại bằng hoặc nhỏ hơn không, công việc đã hết ngân sách thời gian.

Nên dùng `System.nanoTime()` để đo khoảng thời gian. Đây là đồng hồ monotonic phù hợp cho timeout và deadline; không dùng `System.currentTimeMillis()` vì đồng hồ hệ thống có thể được điều chỉnh bởi đồng bộ thời gian hoặc thao tác quản trị.

```java
long budgetNanos = TimeUnit.SECONDS.toNanos(5);
long deadline = System.nanoTime() + budgetNanos;

long remainingNanos = deadline - System.nanoTime();
if (remainingNanos <= 0) {
    throw new SocketTimeoutException("Business deadline exceeded");
}
```

Phép trừ `deadline - System.nanoTime()` là cách tính khoảng thời gian còn lại theo `nanoTime`. Giữ ngân sách nhỏ hơn khoảng nửa miền `long` nano giây (khoảng 292 năm) để phép tính chênh lệch vẫn có ý nghĩa khi bộ đếm cuộn vòng. Trong ứng dụng thực tế, deadline thường ngắn hơn rất nhiều.

### Chuyển thời gian còn lại sang mili giây an toàn

Các API `Socket.connect()` và `Socket.setSoTimeout()` nhận `int` mili giây. Nếu thời gian còn lại dương nhưng nhỏ hơn một mili giây, không được làm tròn xuống `0`, vì `0` có nghĩa là vô hạn. Hãy làm tròn lên ít nhất một mili giây và giới hạn giá trị ở `Integer.MAX_VALUE`:

```java
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeUnit;

static int remainingMillis(long deadlineNanos) throws SocketTimeoutException {
    long remaining = deadlineNanos - System.nanoTime();
    if (remaining <= 0) {
        throw new SocketTimeoutException("Deadline exceeded");
    }

    long millis = TimeUnit.NANOSECONDS.toMillis(remaining);
    if (remaining % 1_000_000L != 0) {
        millis++;
    }

    return (int) Math.min(Integer.MAX_VALUE, Math.max(1L, millis));
}
```

Làm tròn lên có thể khiến một thao tác vượt deadline một lượng nhỏ, tối đa gần một mili giây ở bước chuyển đổi này. Vì vậy, hãy kiểm tra deadline lại sau khi thao tác trả về nếu yêu cầu nghiệp vụ cần từ chối kết quả đến muộn.

### Áp dụng một deadline cho connect và nhiều lần read

Ví dụ sau dùng cùng một ngân sách thời gian cho giai đoạn kết nối và toàn bộ các lần đọc đến EOF. `InetSocketAddress` được truyền vào đã được phân giải trước; DNS không nằm trong ngân sách mà `Socket.connect()` có thể áp dụng trong ví dụ này.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeUnit;

public class DeadlineSocketExample {
    static byte[] connectAndReadUntilEof(
            InetSocketAddress remote,
            long budgetNanos
    ) throws IOException {
        if (budgetNanos <= 0) {
            throw new IllegalArgumentException("budgetNanos must be positive");
        }

        long deadline = System.nanoTime() + budgetNanos;

        try (Socket socket = new Socket()) {
            socket.connect(remote, remainingMillis(deadline));

            InputStream input = socket.getInputStream();
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[8_192];

            while (true) {
                socket.setSoTimeout(remainingMillis(deadline));
                int count = input.read(buffer);
                if (count == -1) {
                    break;
                }
                output.write(buffer, 0, count);
            }

            if (deadline - System.nanoTime() <= 0) {
                throw new SocketTimeoutException("Business deadline exceeded");
            }

            return output.toByteArray();
        }
    }

    static int remainingMillis(long deadlineNanos) throws SocketTimeoutException {
        long remaining = deadlineNanos - System.nanoTime();
        if (remaining <= 0) {
            throw new SocketTimeoutException("Business deadline exceeded");
        }

        long millis = TimeUnit.NANOSECONDS.toMillis(remaining);
        if (remaining % 1_000_000L != 0) {
            millis++;
        }
        return (int) Math.min(Integer.MAX_VALUE, Math.max(1L, millis));
    }
}
```

Mỗi lần đọc đều đặt `SO_TIMEOUT` theo ngân sách còn lại, vì vậy một peer gửi dữ liệu nhỏ liên tục không thể kéo dài các lần đọc vượt quá deadline một cách vô hạn. Vòng lặp cũng kiểm tra lại thời gian sau khi EOF được nhận để tránh trả kết quả đã đến muộn.

Đây là ví dụ đọc đến EOF; giao thức thực tế có thể kết thúc response bằng độ dài đã khai báo, delimiter hoặc frame. Trong trường hợp đó, thay điều kiện EOF bằng điều kiện hoàn tất giao thức nhưng vẫn cập nhật timeout trước mỗi lần đọc. Nếu cần deadline bao gồm cả DNS, ghi request hoặc xử lý CPU, phải quản lý riêng các bước đó; `SO_TIMEOUT` không bao phủ chúng.

## 8. Write timeout và giới hạn của blocking `Socket`

API `Socket` không có phương thức `setWriteTimeout()`. `setSoTimeout()` chỉ điều chỉnh thao tác đọc. Một lần `OutputStream.write()` trên socket blocking có thể chờ khi bộ đệm gửi đầy hoặc mạng không tiến triển; connect timeout và read timeout không giới hạn thời gian chờ ghi.

Nếu nghiệp vụ yêu cầu deadline cho ghi dữ liệu, cân nhắc:

- Dùng `SocketChannel` ở non-blocking mode kết hợp `Selector`, đăng ký `OP_WRITE` và tính thời gian còn lại trước mỗi lần `select()`.
- Dùng `AsynchronousSocketChannel` với overload đọc/ghi có timeout và xử lý `InterruptedByTimeoutException` theo hợp đồng API.
- Dùng HTTP Client hoặc thư viện giao thức cấp cao có request timeout/cancellation phù hợp với workload.

Đóng socket từ một thread khác có thể làm thao tác I/O đang chặn kết thúc, nhưng đó là hành động hủy kết nối, không phải một write timeout có thể cấu hình độc lập. Chỉ dùng khi chính sách nghiệp vụ chấp nhận đóng kết nối và xử lý lại request nếu phù hợp.

## 9. Kết hợp timeout với retry và deadline

Retry phải dùng chung deadline nghiệp vụ. Không cấp lại toàn bộ timeout ban đầu cho từng lần thử, nếu không tổng thời gian có thể tăng theo số lần retry.

Ví dụ về cách tính ngân sách còn lại trước mỗi lần thử:

```java
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeUnit;

static void retryWithinDeadline() throws SocketTimeoutException {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);

    for (int attempt = 1; attempt <= 3; attempt++) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            throw new SocketTimeoutException("Request deadline exceeded");
        }

        long remainingMillis = TimeUnit.NANOSECONDS.toMillis(remaining);
        if (remaining % 1_000_000L != 0) {
            remainingMillis++;
        }
        int attemptTimeoutMillis = (int) Math.min(
                2_000L,
                Math.max(1L, remainingMillis)
        );

        // Thực hiện một lần gọi I/O với attemptTimeoutMillis.
        // Nếu cần sleep/backoff, chỉ ngủ khi vẫn còn ngân sách.
    }
}
```

Ví dụ trên giới hạn mỗi lần thử bởi giá trị nhỏ hơn giữa hai giây và ngân sách còn lại, đồng thời làm tròn lên khi chuyển nano giây sang mili giây để tránh vô tình dùng `0` (vô hạn). Trong code thực tế, kiểm tra deadline sau mỗi lần thử và trước/sau backoff. Chỉ retry các lỗi có thể thử lại an toàn; không retry mù quáng các thao tác ghi hoặc giao dịch có thể đã được server thực hiện.

Timeout và retry cũng phải tính đến idempotency. Với thao tác tạo đơn hàng hoặc trừ tiền, client có thể timeout sau khi server đã hoàn thành nhưng trước khi response quay về. Gửi lại request mà không có idempotency key hoặc cơ chế đối soát có thể thực hiện nghiệp vụ hai lần.

## 10. Lựa chọn timeout theo loại công việc

| Công việc | Cấu hình phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| TCP client kết nối server | `Socket.connect(endpoint, connectTimeout)` | Phân giải DNS có thể xảy ra trước khi connect timeout bắt đầu. |
| TCP client đọc dữ liệu | `Socket.setSoTimeout(readTimeout)` | Timeout áp dụng cho từng lần đọc; đặt lại theo deadline nếu cần giới hạn tổng. |
| TCP server chờ client | `ServerSocket.setSoTimeout(acceptTimeout)` | Timeout không đóng server socket. |
| HTTP request mới | `HttpClient.connectTimeout` và `HttpRequest.timeout` | Connection đã tái sử dụng có thể không cần connect mới; streaming body cần quản lý riêng. |
| Protocol hỗ trợ qua URLConnection | `setConnectTimeout` và `setReadTimeout` | Một số protocol handler có thể bỏ qua cấu hình timeout. |
| Nhiều bước I/O hoặc retry | Deadline tuyệt đối với `System.nanoTime()` | Mỗi bước phải dùng ngân sách còn lại, không reset toàn bộ timeout. |
| Ghi socket blocking | API không có write timeout riêng | Dùng non-blocking selector hoặc asynchronous I/O nếu cần deadline ghi. |

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết nối vẫn chờ lâu dù đã đặt read timeout | Read timeout không áp dụng cho bước connect. | Đặt connect timeout riêng. |
| `Socket.connect()` vẫn mất thời gian trước khi kết nối | DNS có thể được phân giải trước lời gọi connect. | Quản lý bước phân giải tên riêng hoặc dùng địa chỉ đã phân giải. |
| Response kéo dài vượt read timeout | Mỗi lần đọc nhận được dữ liệu trước khi hết hạn nên timeout được tính lại. | Dùng deadline tuyệt đối và đặt read timeout theo thời gian còn lại. |
| Timeout bằng `0` khiến chương trình chờ mãi | Với Socket/URLConnection, `0` nghĩa là vô hạn. | Dùng giá trị dương và xác thực cấu hình đầu vào. |
| `SocketTimeoutException` bị coi là socket đã đóng | Read timeout không tự đóng socket. | Quyết định tiếp tục đọc hay đóng socket theo trạng thái giao thức. |
| Dùng `SO_TIMEOUT` để giới hạn ghi | `SO_TIMEOUT` chỉ áp dụng cho đọc. | Chọn non-blocking hoặc asynchronous I/O nếu cần write deadline. |
| Retry làm tổng thời gian vượt SLA | Mỗi lần retry được cấp lại timeout đầy đủ. | Chia sẻ một deadline và tính lại ngân sách trước từng lần thử. |
| Dùng `currentTimeMillis()` để đo deadline | Đồng hồ hệ thống có thể nhảy khi được điều chỉnh. | Dùng `System.nanoTime()` để đo khoảng thời gian. |
| HTTP request timeout bị hiểu là timeout cho mọi lần đọc stream | Handler streaming có thể trả InputStream trước khi ứng dụng tiêu thụ hết body. | Đặt deadline riêng cho giai đoạn đọc stream và đóng body khi hết hạn. |

## 12. Tài liệu tham khảo chính thức

- [Java SE 21 API — `Socket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html): `connect`, `setSoTimeout` và hành vi timeout của socket.
- [Java SE 21 API — `ServerSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html): timeout của `accept()`.
- [Java SE 21 API — `URLConnection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLConnection.html): connect timeout và read timeout.
- [Java SE 21 API — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cấu hình connect timeout.
- [Java SE 21 API — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout bằng `Duration`.
- [Java SE 21 API — `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): timeout khi chờ HTTP response.
- [Java SE 21 API — `AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): thao tác đọc/ghi bất đồng bộ có timeout.
- [Java SE 21 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()): đồng hồ monotonic để đo khoảng thời gian.
