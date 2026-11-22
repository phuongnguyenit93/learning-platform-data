# Giới hạn mạng, DNS và kiểm thử với dịch vụ cục bộ trong Java 17

Khi một ứng dụng Java gọi dịch vụ HTTP, sự cố có thể xảy ra ở nhiều giai đoạn: phân giải tên miền, thiết lập kết nối TCP, trao đổi HTTP, chờ phản hồi hoặc đọc nội dung. Nếu chỉ đặt một timeout mà không hiểu nó giới hạn giai đoạn nào, ứng dụng vẫn có thể chờ lâu hoặc báo lỗi khó phân biệt.

Trong Java 17, `java.net.http.HttpClient` cung cấp cấu hình timeout cho việc thiết lập kết nối và cho từng request. `java.net.InetAddress` hỗ trợ phân giải tên máy thành địa chỉ IP. Để kiểm thử mà không phụ thuộc Internet, có thể chạy một HTTP service chỉ lắng nghe trên loopback và dùng cổng động.

Bài này tập trung vào các API còn dùng được trong Java 17: timeout, DNS, địa chỉ loopback, kiểm thử dịch vụ HTTP cục bộ và cách nhận diện lỗi mạng.

## 1. Một request mạng đi qua những giai đoạn nào?

Khi ứng dụng gọi URL như `https://api.example.test/orders`, có thể hình dung luồng xử lý như sau:

~~~text
Ứng dụng Java
    |
    v
Phân tích URI / hostname
    |
    v
DNS: hostname -> một hoặc nhiều địa chỉ IP
    |
    v
Thiết lập kết nối TCP (và TLS nếu dùng HTTPS)
    |
    v
Gửi HTTP request
    |
    v
Chờ HTTP response
    |
    v
Đọc và xử lý response body
~~~

Mỗi giai đoạn có kiểu lỗi và cách giới hạn khác nhau:

| Giai đoạn | Ví dụ vấn đề | Khái niệm/API liên quan |
|---|---|---|
| Phân giải tên | DNS không tìm thấy hostname hoặc resolver chậm | `InetAddress`, `UnknownHostException` |
| Kết nối | Máy đích từ chối kết nối, firewall chặn hoặc mạng không phản hồi | TCP, `connectTimeout` |
| TLS | Chứng thư không hợp lệ hoặc handshake thất bại | TLS, `SSLHandshakeException` |
| HTTP | Server trả về 404, 429 hoặc 500 | `HttpResponse.statusCode()` |
| Chờ phản hồi | Server xử lý quá lâu | `HttpRequest.timeout` |
| Đọc nội dung | Body lớn hoặc truyền chậm | `BodyHandler`, giới hạn ứng dụng |

**Timeout không đồng nghĩa với việc mọi lỗi mạng được xử lý giống nhau.** Ví dụ HTTP 404 là một phản hồi HTTP hợp lệ, không phải lỗi kết nối; ngược lại, `ConnectException` xảy ra trước khi ứng dụng nhận được một HTTP response.

## 2. Giới hạn thời gian thiết lập kết nối bằng connectTimeout

`HttpClient.Builder.connectTimeout(Duration)` đặt giới hạn thời gian cho việc thiết lập kết nối khi client cần mở một kết nối mới.

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

Trong ví dụ này, client được cấu hình timeout kết nối là 3 giây. Nếu không thể thiết lập kết nối trong thời gian quy định, thao tác có thể thất bại với `HttpConnectTimeoutException`.

Các điểm cần nhớ:

- Timeout được cấu hình trên `HttpClient`, không phải trên từng `HttpRequest`.
- Nó có ý nghĩa khi cần thiết lập một kết nối mới.
- Nếu client tái sử dụng kết nối đã có, không có một lần kết nối mới để áp dụng connect timeout.
- Thời gian phải dương; giá trị không hợp lệ có thể làm builder ném `IllegalArgumentException`.
- Không đặt timeout quá nhỏ một cách tùy tiện; mạng chậm hoặc TLS handshake có thể cần thêm thời gian.

`HttpClient` sau khi được build là immutable và có thể được dùng cho nhiều request. Thực tế nên tái sử dụng client thay vì tạo một client mới cho mỗi lần gọi, để tận dụng quản lý kết nối và giảm chi phí khởi tạo.

### 2.1. connectTimeout không phải timeout tổng của request

Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
~~~

Đoạn này chỉ cấu hình thời gian thiết lập kết nối. Một khi kết nối đã được thiết lập, server vẫn có thể mất nhiều thời gian để xử lý request hoặc trả dữ liệu.

Để giới hạn thời gian chờ phản hồi cho một request cụ thể, cấu hình `HttpRequest.timeout` ở phần tiếp theo.

### 2.2. Không dùng một địa chỉ IP “không phản hồi” làm bài test timeout tùy tiện

Một địa chỉ không thể truy cập có thể trả về lỗi rất nhanh, bị firewall từ chối ngay, hoặc bị hệ điều hành xử lý theo cách khác nhau. Vì vậy, một bài test kết nối đến địa chỉ IP tùy chọn không phải lúc nào cũng tái lập được tình huống timeout.

Khi cần kiểm thử timeout kết nối thật, hãy dùng môi trường mạng kiểm thử có thể kiểm soát firewall, route hoặc proxy. Với bài tập thông thường, kiểm thử request timeout bằng một local server phản hồi chậm thường ổn định và dễ lặp lại hơn.

## 3. Giới hạn thời gian của từng request bằng HttpRequest.timeout

`HttpRequest.Builder.timeout(Duration)` đặt thời gian chờ cho một request:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

Request có timeout 5 giây. Nếu response không được nhận trong thời gian đó, việc gửi request có thể kết thúc bằng `HttpTimeoutException`.

### 3.1. Kết hợp timeout client và request

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

Hai timeout có vai trò khác nhau:

| Cấu hình | Phạm vi | Ví dụ |
|---|---|---|
| `HttpClient.Builder.connectTimeout` | Thiết lập kết nối mới | Tối đa 2 giây |
| `HttpRequest.Builder.timeout` | Chờ response của request | Tối đa 5 giây |

Đừng cộng hai con số rồi coi đó là giới hạn chính xác cho mọi trường hợp. Kết nối có thể được tái sử dụng, DNS có thể có cache, và hành vi chi tiết còn phụ thuộc giai đoạn request đang thực hiện.

### 3.2. Request không có timeout tường minh

Nếu không gọi `timeout` trên request, API không tự áp dụng một giới hạn request hữu hạn do ứng dụng chỉ định. Khi làm việc với dịch vụ bên ngoài, hãy quyết định timeout dựa trên SLA, loại thao tác và ngân sách thời gian của luồng gọi.

Không nên chọn một con số duy nhất cho tất cả endpoint. Một endpoint health check có thể cần timeout ngắn; một thao tác báo cáo nặng có thể cần ngân sách lớn hơn.

### 3.3. Gửi đồng bộ và bất đồng bộ

Gửi đồng bộ:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

Luồng gọi chờ kết quả hoặc ngoại lệ.

Gửi bất đồng bộ:

~~~java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
);

future.thenAccept(response ->
        System.out.println(response.statusCode())
);
~~~

`sendAsync` trả về `CompletableFuture`. Request timeout vẫn được đặt trên `HttpRequest`. Nếu ứng dụng tự gọi `future.get(timeout, unit)`, timeout của `get` là giới hạn chờ của thao tác lấy kết quả ở phía caller; nó không giống cấu hình timeout của request và không tự động thay thế timeout của request.

Khi hủy một future hoặc request, hãy xử lý trạng thái hủy và tài nguyên liên quan đúng cách. Không giả định việc caller ngừng chờ đồng nghĩa server đã dừng xử lý.

## 4. DNS và InetAddress

DNS (Domain Name System) ánh xạ hostname như `example.com` sang địa chỉ IP. Trong Java, `InetAddress` đại diện địa chỉ IP và cung cấp API phân giải tên.

~~~java
import java.net.InetAddress;

InetAddress address = InetAddress.getByName("localhost");

System.out.println(address.getHostName());
System.out.println(address.getHostAddress());
~~~

`getByName` có thể trả về địa chỉ IPv4 hoặc IPv6 tùy cấu hình máy và kết quả phân giải. Không nên giả định `localhost` luôn chỉ ánh xạ tới `127.0.0.1`.

### 4.1. Lấy tất cả địa chỉ được phân giải

~~~java
InetAddress[] addresses = InetAddress.getAllByName("localhost");

for (InetAddress address : addresses) {
    System.out.println(address.getHostAddress());
}
~~~

Một hostname có thể có nhiều địa chỉ. Ứng dụng và hệ điều hành có thể lựa chọn địa chỉ phù hợp trong quá trình kết nối; thứ tự trả về không nên được dùng như một hợp đồng cố định cho mọi môi trường.

### 4.2. Lấy địa chỉ loopback mà không hard-code IPv4

~~~java
InetAddress loopback = InetAddress.getLoopbackAddress();
System.out.println(loopback.getHostAddress());
~~~

Loopback là địa chỉ quay về chính máy đang chạy chương trình. Nó thường được dùng cho service cục bộ, test tích hợp và giao tiếp giữa các tiến trình trên cùng máy.

Nếu muốn kiểm thử riêng IPv4, có thể chỉ định `127.0.0.1`. Nếu muốn kiểm thử IPv6, dùng địa chỉ loopback IPv6 `::1` và bảo đảm môi trường hỗ trợ. Không trộn giả định IPv4/IPv6 trong test mà không xác định rõ địa chỉ bind và địa chỉ client sử dụng.

### 4.3. Phân biệt hostname, địa chỉ IP và URI

| Giá trị | Ý nghĩa |
|---|---|
| `localhost` | Hostname thường được phân giải về loopback |
| `127.0.0.1` | Địa chỉ loopback IPv4 |
| `::1` | Địa chỉ loopback IPv6 |
| `http://localhost:8080/health` | URI chứa scheme, hostname, port và path |
| `InetAddress` | Đối tượng biểu diễn địa chỉ IP đã phân giải |

DNS chỉ liên quan tới hostname. Nếu URI dùng địa chỉ IP literal, không cần tra cứu DNS cho hostname đó. Tuy nhiên, kết nối TCP và các bước HTTP/TLS vẫn có thể thất bại.

## 5. DNS cache và giới hạn kiểm soát trong Java 17

Kết quả phân giải tên có thể được cache để tránh truy vấn DNS lặp lại. Java có chính sách cache cho kết quả thành công và kết quả không phân giải được.

Hai security property thường gặp:

- `networkaddress.cache.ttl`: thời gian cache kết quả phân giải thành công.
- `networkaddress.cache.negative.ttl`: thời gian cache kết quả phân giải thất bại.

Đây là **security properties** được quản lý theo cấu hình bảo mật của Java. Không nhầm chúng với các system property thông thường mà luôn có thể thay đổi bằng `System.setProperty`.

Các giá trị TTL và chính sách cụ thể nên được cấu hình theo yêu cầu vận hành, nền tảng và chính sách bảo mật của ứng dụng. Không nên thay đổi cache DNS toàn JVM chỉ để làm một bài test chạy nhanh hơn.

### 5.1. Vì sao DNS có thể khiến test khó lặp lại?

Giả sử test gọi một hostname lần đầu và DNS phân giải thành công. Lần gọi sau có thể nhận kết quả từ cache thay vì truy vấn resolver. Ngược lại, một hostname từng phân giải thất bại có thể tiếp tục bị ghi nhận thất bại trong thời gian negative cache.

Vì thế, kết quả test có thể phụ thuộc:

- Máy đang chạy test.
- File hosts và DNS resolver cấu hình trên máy.
- Kết quả DNS đã được cache trước đó.
- Mạng đang kết nối và chính sách DNS của môi trường.

Để test logic HTTP không phụ thuộc DNS công cộng, ưu tiên loopback hoặc địa chỉ IP cục bộ. Nếu mục tiêu của test chính là DNS, hãy dùng resolver hoặc môi trường test được kiểm soát.

### 5.2. InetAddress không cung cấp timeout DNS riêng cho từng lần gọi

`InetAddress.getByName` và `getAllByName` là API phân giải tên đồng bộ. Java 17 không cung cấp một tham số `Duration` cho từng lời gọi để đặt DNS timeout riêng.

`HttpClient.connectTimeout` là timeout thiết lập kết nối; không nên coi nó là một API cấu hình DNS timeout độc lập. Chi tiết DNS được thực hiện qua cơ chế phân giải tên của runtime và hệ điều hành.

Nếu ứng dụng có yêu cầu đặc biệt về DNS timeout, resolver tùy biến, failover hoặc kiểm soát cache, cần thiết kế ở tầng resolver/network phù hợp với môi trường. Không dựa vào các lớp nội bộ như `sun.net.*`; chúng không phải API công khai ổn định để ứng dụng phụ thuộc.

### 5.3. Xử lý hostname không phân giải được

`InetAddress.getByName` có thể ném `UnknownHostException`:

~~~java
try {
    InetAddress address = InetAddress.getByName("host-that-does-not-exist.invalid");
    System.out.println(address.getHostAddress());
} catch (UnknownHostException e) {
    System.err.println("Không phân giải được hostname: " + e.getMessage());
}
~~~

Tên miền dùng hậu tố `.invalid` được dành riêng cho mục đích kiểm thử/tài liệu, nhưng truy vấn DNS thực tế vẫn có thể phụ thuộc resolver và thời gian chờ môi trường. Không nên dùng ví dụ này làm test timeout có thời gian chạy cố định.

Trong test đơn vị, có thể mock tầng phân giải hoặc truyền một địa chỉ đã biết vào component cần kiểm thử. Trong test tích hợp DNS, hãy chạy trong môi trường có resolver được quản lý.

## 6. Phân biệt các loại timeout và lỗi mạng

Các ngoại lệ thường gặp:

| Ngoại lệ | Ý nghĩa thường gặp |
|---|---|
| `UnknownHostException` | Không phân giải được hostname |
| `HttpConnectTimeoutException` | Không thiết lập được kết nối trong thời gian connect timeout |
| `HttpTimeoutException` | Request không nhận được response trong request timeout |
| `ConnectException` | Kết nối bị từ chối hoặc không thể thiết lập |
| `SocketException` | Lỗi ở tầng socket hoặc hệ thống mạng |
| `SSLHandshakeException` | TLS handshake thất bại |
| `IOException` | Nhóm lỗi I/O tổng quát |

Một số ngoại lệ là lớp con của `IOException`; khi xử lý, có thể bắt loại cụ thể trước rồi mới bắt `IOException` tổng quát.

Ví dụ:

~~~java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    System.out.println("HTTP status: " + response.statusCode());
} catch (HttpConnectTimeoutException e) {
    System.err.println("Hết thời gian thiết lập kết nối");
} catch (HttpTimeoutException e) {
    System.err.println("Request chờ response quá lâu");
} catch (UnknownHostException e) {
    System.err.println("Không phân giải được hostname");
} catch (IOException e) {
    System.err.println("Lỗi I/O mạng: " + e.getMessage());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    System.err.println("Luồng bị gián đoạn");
}
~~~

Lưu ý: trong một số trường hợp, lỗi phân giải hostname phát sinh khi HttpClient kết nối có thể xuất hiện như nguyên nhân gốc bên trong một ngoại lệ I/O. Nếu cần phân loại chi tiết, hãy xem cause chain thay vì chỉ đọc message.

### 6.1. HTTP status không phải ngoại lệ kết nối

Nếu server trả về status 404 hoặc 500, request vẫn đã nhận được một HTTP response:

~~~java
int status = response.statusCode();

if (status >= 200 && status < 300) {
    System.out.println("Thành công");
} else {
    System.out.println("Dịch vụ trả về HTTP " + status);
}
~~~

`HttpClient.send` không tự ném ngoại lệ chỉ vì status là 404 hoặc 500. Ứng dụng phải tự xác định status nào được xem là thành công.

## 7. Kiểm thử với dịch vụ cục bộ: nguyên tắc

Một bài test mạng đáng tin cậy nên hạn chế phụ thuộc vào:

- Internet công cộng.
- DNS bên ngoài.
- Dịch vụ của bên thứ ba.
- Cổng cố định có thể đang được tiến trình khác sử dụng.
- Dữ liệu hoặc trạng thái thay đổi theo thời gian.

Với test HTTP, có thể chạy một service cục bộ chỉ bind vào loopback:

1. Bind server vào `127.0.0.1`.
2. Chọn port `0` để hệ điều hành cấp một cổng trống.
3. Đăng ký endpoint đơn giản như `/health`.
4. Start server trong test.
5. Lấy port thực tế từ `server.getAddress().getPort()`.
6. Gửi request bằng `HttpClient` tới loopback và port đó.
7. Dừng server trong khối `finally`.

Port `0` là cách yêu cầu hệ điều hành chọn cổng khả dụng tại thời điểm bind. Không hard-code `8080` cho test vì cổng đó có thể đã bị tiến trình khác chiếm.

## 8. Dựng HTTP service cục bộ bằng HttpServer

JDK 17 cung cấp `com.sun.net.httpserver.HttpServer` trong module `jdk.httpserver`. Đây là HTTP server nhẹ hữu ích cho test và công cụ phát triển. Nó không phải lựa chọn mặc định để xây dựng một web server production lớn; ứng dụng production thường dùng server/framework được thiết kế cho yêu cầu vận hành tương ứng.

Tạo file **`LocalHttpTest.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class LocalHttpTest {
    public static void main(String[] args) throws Exception {
        // Chỉ lắng nghe trên IPv4 loopback; port 0 để OS cấp cổng trống.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );

        server.createContext("/health", exchange -> {
            byte[] body = "OK".getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/plain; charset=UTF-8"
            );
            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();

        try {
            int port = server.getAddress().getPort();
            URI uri = URI.create(
                    "http://127.0.0.1:" + port + "/health"
            );

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(uri)
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8
                    )
            );

            System.out.println("Status: " + response.statusCode());
            System.out.println("Body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 --add-modules jdk.httpserver LocalHttpTest.java
java --add-modules jdk.httpserver LocalHttpTest
~~~

Kết quả:

~~~text
Status: 200
Body: OK
~~~

### 8.1. Vì sao ví dụ này ổn định hơn khi test?

- Server chỉ bind loopback, không mở endpoint ra địa chỉ mạng bên ngoài.
- Port động tránh xung đột với cổng cố định.
- Test không cần truy vấn DNS công cộng hoặc gọi dịch vụ bên thứ ba.
- Client có connect timeout và request timeout tường minh.
- Server được dừng trong `finally` kể cả khi request lỗi.

Ví dụ dùng IPv4 loopback `127.0.0.1` cho cả bind và request để tránh khác biệt giữa thứ tự phân giải IPv4/IPv6 của hostname `localhost` trên các máy.

### 8.2. Module jdk.httpserver

`HttpServer` nằm trong module `jdk.httpserver`. Với chương trình classpath đơn giản, lệnh biên dịch/chạy ở trên thêm module bằng `--add-modules jdk.httpserver`.

Nếu dự án dùng named module, khai báo phụ thuộc:

~~~java
module local.http.test {
    requires java.net.http;
    requires jdk.httpserver;
}
~~~

`java.net.http` là module chứa `HttpClient`; `jdk.httpserver` cung cấp `HttpServer`. Với bài tập một file Java trên classpath, không cần tạo `module-info.java`.

## 9. Kiểm thử request timeout bằng endpoint phản hồi chậm

Có thể thêm endpoint `/slow` để mô phỏng server xử lý lâu:

~~~java
server.createContext("/slow", exchange -> {
    try {
        Thread.sleep(1_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }

    byte[] body = "finished".getBytes(StandardCharsets.UTF_8);
    exchange.sendResponseHeaders(200, body.length);

    try (OutputStream output = exchange.getResponseBody()) {
        output.write(body);
    }
});
~~~

Tạo request có timeout ngắn hơn thời gian chờ của server:

~~~java
HttpRequest slowRequest = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:" + port + "/slow"))
        .timeout(Duration.ofMillis(200))
        .GET()
        .build();

try {
    client.send(
            slowRequest,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
    );
} catch (HttpTimeoutException e) {
    System.out.println("Request timeout như dự kiến");
}
~~~

Trong ví dụ, handler chờ khoảng một giây trong khi request đặt timeout 200 ms. Client có thể kết thúc chờ với `HttpTimeoutException`.

Một số lưu ý:

- Timeout xảy ra ở client không đảm bảo code handler phía server đã ngừng chạy ngay lập tức.
- Server có thể vẫn hoàn tất công việc sau khi client đã bỏ chờ.
- Trong test thực tế, cần dừng server và dọn executor/tài nguyên đúng cách.
- Không dùng thời gian ngủ cố định để kiểm tra hiệu năng chính xác; đây chỉ là ví dụ minh họa timeout.

## 10. Kiểm thử DNS và hostname cục bộ

Có thể kiểm tra phân giải hostname loopback bằng:

~~~java
import java.net.InetAddress;

for (InetAddress address : InetAddress.getAllByName("localhost")) {
    System.out.println(address.getHostAddress());
}
~~~

Kết quả phụ thuộc cấu hình máy; có thể thấy IPv4, IPv6 hoặc cả hai. Không nên viết assertion yêu cầu luôn chỉ có một địa chỉ cố định.

Nếu mục tiêu là kiểm thử HTTP server, dùng IP loopback tường minh như ví dụ trước giúp test không phụ thuộc vào kết quả phân giải hostname. Nếu mục tiêu là kiểm thử DNS, tách test đó thành một test riêng và xác định resolver, hostname, cache policy cùng kỳ vọng của môi trường.

### 10.1. Không dựa vào DNS công cộng trong unit test

Một unit test gọi hostname bên ngoài có thể thất bại do:

- Mạng của máy chạy CI không có Internet.
- DNS resolver tạm thời lỗi.
- Rate limit hoặc chính sách mạng của tổ chức.
- DNS cache giữ kết quả cũ.
- Dịch vụ đích đổi địa chỉ hoặc ngừng hoạt động.

Unit test nên kiểm tra logic xử lý với dependency được giả lập. Test tích hợp DNS/HTTP nên chạy riêng trong môi trường đã kiểm soát và có timeout hữu hạn.

### 10.2. Hostname và Host header

Khi gọi một dịch vụ bằng hostname, hostname còn có thể được dùng trong HTTP authority/Host và TLS server name. Thay hostname bằng IP literal không phải lúc nào cũng tương đương, đặc biệt với HTTPS và chứng thư TLS.

Vì vậy:

- Dùng IP loopback cho test HTTP thuần cục bộ đơn giản.
- Nếu test virtual host hoặc TLS, dùng hostname test và cấu hình resolver/certificate tương ứng.
- Không tắt kiểm tra chứng thư TLS trong test chỉ để làm request chạy được; hãy tạo chứng thư test phù hợp và cấu hình trust riêng.

## 11. Timeout, retry và giới hạn tài nguyên

Timeout là một phần của khả năng chịu lỗi, nhưng không thay thế chính sách retry hoặc giới hạn tài nguyên.

### 11.1. Chỉ retry khi thao tác phù hợp

Một request GET đọc dữ liệu thường có thể retry nếu lỗi tạm thời và ngân sách thời gian còn đủ. Với POST tạo đơn hàng hoặc thanh toán, retry mù có thể tạo tác dụng phụ trùng lặp nếu server đã xử lý nhưng response bị mất.

Trước khi retry, hãy xác định:

- Request có idempotent không?
- Có idempotency key hay cơ chế chống xử lý trùng không?
- Lỗi có khả năng tạm thời không?
- Còn bao nhiêu thời gian trong deadline tổng?
- Số lần retry tối đa và backoff là bao nhiêu?

Không retry vô hạn. Một vòng retry phải có giới hạn và quan sát được qua log/metrics.

### 11.2. Phân biệt timeout mỗi request với deadline tổng

Nếu một luồng công việc gọi ba dịch vụ tuần tự, đặt timeout 5 giây cho từng request có thể khiến tổng thời gian vượt xa 5 giây. Ứng dụng cần một deadline tổng cho cả công việc và tính ngân sách còn lại trước từng lần gọi.

Ví dụ khái niệm:

~~~text
Deadline tổng: 8 giây
    |
    +-- Dịch vụ A: tối đa 2 giây
    |
    +-- Dịch vụ B: dùng phần thời gian còn lại
    |
    +-- Dịch vụ C: chỉ gọi nếu deadline chưa hết
~~~

Deadline tổng là chính sách ở tầng ứng dụng. `HttpRequest.timeout` không tự phối hợp ngân sách giữa nhiều request độc lập.

### 11.3. Giới hạn body và concurrency

Một request có timeout vẫn có thể nhận body rất lớn. Với response không tin cậy, cân nhắc:

- Dùng `BodyHandlers.ofInputStream()` và tự giới hạn số byte đọc.
- Giới hạn số request đồng thời ở tầng ứng dụng.
- Đóng stream body khi đã đọc xong hoặc khi dừng sớm.
- Tránh tạo quá nhiều thread chỉ để chờ I/O.
- Theo dõi số kết nối, độ trễ và tỷ lệ lỗi.

`BodyHandlers.ofString()` thuận tiện cho response nhỏ; nó đọc body thành chuỗi trong bộ nhớ. Với body lớn hoặc không biết trước kích thước, cần cân nhắc cách đọc streaming và giới hạn dữ liệu.

## 12. Ví dụ hoàn chỉnh: kiểm thử timeout cục bộ

Tạo file **`LocalTimeoutTest.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class LocalTimeoutTest {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );

        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            byte[] body = "done".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();

        try {
            int port = server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(
                            "http://127.0.0.1:" + port + "/slow"
                    ))
                    .timeout(Duration.ofMillis(200))
                    .GET()
                    .build();

            try {
                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                );

                System.out.println("HTTP " + response.statusCode());
                System.out.println(response.body());
            } catch (HttpTimeoutException e) {
                System.out.println("Đã bắt được request timeout");
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 --add-modules jdk.httpserver LocalTimeoutTest.java
java --add-modules jdk.httpserver LocalTimeoutTest
~~~

Kết quả dự kiến trong môi trường chạy bình thường:

~~~text
Đã bắt được request timeout
~~~

Đây là test request timeout. Nó không phải test connect timeout hoặc DNS timeout: server đã bind thành công trên loopback, client có địa chỉ IP trực tiếp và timeout được đặt trên request.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request chờ rất lâu | Không đặt request timeout | Đặt `HttpRequest.timeout` phù hợp |
| Kết nối mới chờ lâu | Không cấu hình connect timeout | Đặt `HttpClient.Builder.connectTimeout` |
| Nhầm DNS timeout với connect timeout | Java 17 không có tham số DNS timeout riêng trên `InetAddress` | Kiểm soát resolver/môi trường DNS ở tầng phù hợp |
| `UnknownHostException` | Hostname không phân giải được | Kiểm tra hostname, DNS resolver và hosts |
| `ConnectException` | Không có service lắng nghe hoặc kết nối bị từ chối | Kiểm tra host, port, bind address và firewall |
| `HttpTimeoutException` | Request không nhận response trong timeout | Kiểm tra độ trễ server, network và timeout |
| HTTP 500 nhưng không có IOException | Server đã trả một HTTP response hợp lệ | Kiểm tra `statusCode()` |
| Local test không kết nối được | Server bind IPv4 nhưng client dùng IPv6 hoặc ngược lại | Dùng cùng địa chỉ loopback rõ ràng |
| Test báo port đang dùng | Dùng cổng cố định bị tiến trình khác chiếm | Bind port `0` rồi đọc port thực tế |
| Test phụ thuộc Internet | Gọi hostname/dịch vụ công cộng | Dùng loopback hoặc mock/service test riêng |
| Client timeout nhưng server vẫn xử lý | Timeout phía client không đảm bảo hủy logic server ngay | Thiết kế cancellation và giới hạn công việc ở server |

## 14. Bài tập thực hành

### Bài 1: Đặt hai loại timeout

Tạo `HttpClient` với connect timeout 2 giây và `HttpRequest` với request timeout 4 giây.

**Đáp án gợi ý:**

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(4))
        .GET()
        .build();
~~~

### Bài 2: Phân giải loopback

Viết chương trình in tất cả địa chỉ được trả về bởi `InetAddress.getAllByName("localhost")`.

**Đáp án:**

~~~java
for (InetAddress address : InetAddress.getAllByName("localhost")) {
    System.out.println(address.getHostAddress());
}
~~~

Không cố định assertion rằng chỉ có một địa chỉ.

### Bài 3: Vì sao không dùng port 8080 trong test?

**Đáp án:** Port 8080 có thể đang được ứng dụng khác sử dụng. Bind server vào port 0 để hệ điều hành cấp cổng trống, sau đó lấy port thực tế từ `server.getAddress().getPort()`.

### Bài 4: Phân biệt lỗi

Ghép lỗi với giai đoạn:

- `UnknownHostException`.
- `HttpConnectTimeoutException`.
- `HttpTimeoutException`.
- HTTP status 503.

**Đáp án:**

- `UnknownHostException`: phân giải hostname thất bại.
- `HttpConnectTimeoutException`: không thiết lập được kết nối trong thời gian cho phép.
- `HttpTimeoutException`: request không nhận được response trong timeout.
- HTTP 503: server đã trả response HTTP; ứng dụng cần xử lý status.

### Bài 5: Kiểm thử request timeout cục bộ

Dựng `HttpServer` trên loopback, đăng ký endpoint ngủ 1 giây rồi trả response. Gửi request có timeout 200 ms và bắt `HttpTimeoutException`.

**Gợi ý:** Dùng `InetSocketAddress("127.0.0.1", 0)`, lấy port động, gọi `server.stop(0)` trong `finally`.

### Bài 6: Có thể đặt DNS timeout bằng connectTimeout không?

**Đáp án:** Không nên coi đây là DNS timeout riêng. `connectTimeout` giới hạn việc thiết lập kết nối mới; `InetAddress` không cung cấp tham số timeout riêng cho từng lần phân giải tên trong Java 17. Nếu cần kiểm soát DNS chuyên sâu, phải thiết kế resolver hoặc môi trường mạng phù hợp.

## 15. Ghi nhớ

Khi xử lý kết nối mạng trong Java 17:

1. Dùng `HttpClient` và tái sử dụng client cho nhiều request.
2. Đặt `connectTimeout` để giới hạn việc thiết lập kết nối mới.
3. Đặt `HttpRequest.timeout` để giới hạn thời gian chờ response cho từng request.
4. Dùng `InetAddress` để phân giải hostname và làm việc với địa chỉ loopback.
5. Nhớ rằng DNS có cache và Java 17 không cung cấp timeout DNS riêng trên `InetAddress`.
6. Phân biệt lỗi DNS, lỗi kết nối, timeout request và HTTP status.
7. Kiểm thử HTTP bằng local server trên loopback và port động.
8. Dừng server và đóng tài nguyên trong mọi đường chạy.
9. Giới hạn retry, thời gian tổng và kích thước response theo yêu cầu ứng dụng.

Một test mạng tốt phải có đầu vào và môi trường kiểm soát được. Local service giúp kiểm tra HTTP, status, body và request timeout mà không phụ thuộc Internet; DNS và connect timeout nên có test riêng với môi trường được kiểm soát phù hợp.

## 16. Tài liệu tham khảo

- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): cấu hình client, connect timeout, gửi đồng bộ và bất đồng bộ.
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout và builder.
- [Oracle Java SE 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): timeout khi chờ HTTP response.
- [Oracle Java SE 17 — HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): timeout thiết lập kết nối.
- [Oracle Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): phân giải hostname, địa chỉ IP và chính sách DNS cache.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server nhẹ trong module `jdk.httpserver`.
- [Oracle Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): một số tùy chọn socket ở tầng kết nối.
- [OpenJDK JEP 321 — HTTP Client](https://openjdk.org/jeps/321): HTTP Client API được chuẩn hóa trong Java 11.

