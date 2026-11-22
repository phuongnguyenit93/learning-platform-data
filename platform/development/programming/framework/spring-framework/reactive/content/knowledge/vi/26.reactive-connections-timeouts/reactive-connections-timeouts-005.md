# Phân biệt timeout tầng mạng với toán tử timeout toàn chuỗi trong WebClient

## 1. Vì sao cần phân biệt hai loại timeout?

Khi dùng `WebClient`, một request có thể mất thời gian ở nhiều giai đoạn: chờ connection pool, phân giải DNS, mở TCP connection, TLS handshake, gửi request, chờ response và đọc body. Có hai lớp timeout thường bị nhầm:

- **Timeout tầng transport/network** do HTTP connector quản lý. Với Reactor Netty, ví dụ quan trọng là `responseTimeout`: giới hạn khoảng im lặng giữa hai lần đọc dữ liệu ở tầng mạng khi đang nhận response.
- **Timeout của Reactor sequence** như `Mono.timeout(Duration)` hoặc `Flux.timeout(Duration)`: giới hạn thời gian chờ tín hiệu của Publisher theo semantics của từng kiểu sequence.

Hai lớp này bảo vệ hai điều khác nhau. Một response stream có thể kéo dài vài phút nhưng vẫn hợp lệ nếu liên tục gửi dữ liệu trước khi network read timeout hết hạn. Ngược lại, một `Mono` có thể bị timeout dù server vẫn gửi các chunk đều đặn, vì `bodyToMono` chỉ phát kết quả sau khi đã đọc và giải mã xong toàn bộ body.

**Điểm cần nhớ:** `responseTimeout` kiểm soát khoảng trống giữa các lần đọc mạng; `Mono.timeout` kiểm soát thời gian chờ kết quả `Mono` phát ra.

## 2. Vòng đời một request và vị trí các timeout

~~~text
Subscribe WebClient Publisher
          |
          v
  Chờ connection pool
          |
          v
  DNS resolve
          |
          v
  TCP connect
          |
          v
  TLS handshake (HTTPS)
          |
          v
  Gửi HTTP request
          |
          v
  Chờ / đọc response bytes  <--- responseTimeout
          |
          v
  Decode body thành DTO       <--- vẫn nằm trong bodyToMono
          |
          v
  Mono phát kết quả           <--- Mono.timeout
          |
          v
  Complete
~~~

Một số timeout được cấu hình ở connector cho từng giai đoạn. Toán tử Reactor được đặt trên Publisher và theo dõi tín hiệu của chuỗi mà nó bọc.

Ví dụ:

~~~java
Mono<Product> product = webClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(4));
~~~

Với request trên, `Mono.timeout` bắt đầu khi Publisher được subscribe. `bodyToMono(Product.class)` phát một Product sau khi body đã được đọc và giải mã; do đó deadline bao phủ việc chờ request/response và decode trước khi Product xuất hiện.

Không phải cứ đặt timeout ở cuối code là nó tự động giới hạn mọi công việc trong ứng dụng. Nó chỉ theo dõi Publisher nằm upstream của chính toán tử đó. Nếu một tác vụ blocking hoặc một side effect được thực hiện ngoài Publisher, timeout này không tự quản lý tác vụ đó.

## 3. responseTimeout của Reactor Netty là gì?

`HttpClient.responseTimeout(Duration)` cấu hình khoảng thời gian tối đa giữa các lần đọc dữ liệu ở tầng mạng khi đang đọc một response.

Theo JavaDoc Reactor Netty, cơ chế này:

1. Thêm `ReadTimeoutHandler` vào channel pipeline sau khi request được gửi.
2. Theo dõi khoảng thời gian giữa các network-level read operations trong lúc nhận response.
3. Gỡ handler khi response đã được nhận đầy đủ.
4. Có thể được ghi đè bằng cấu hình timeout ở cấp request.

Nó là **read-inactivity timeout**. Nó không đặt giới hạn tổng thời gian từ lúc bắt đầu request đến lúc response kết thúc.

Ví dụ, server gửi một chunk mỗi 500 ms và client đặt `responseTimeout(Duration.ofSeconds(2))`. Nếu các lần đọc mạng vẫn xảy ra trong khoảng dưới 2 giây, response có thể tiếp tục chạy trong nhiều phút mà không bị timeout này chặn.

### 3.1. Cấu hình responseTimeout cho mọi request

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Cấu hình này áp dụng cho mọi request đi qua connector Reactor Netty đã cung cấp.

### 3.2. Cấu hình responseTimeout cho một request

Khi chỉ một endpoint cần chính sách riêng:

~~~java
Mono<String> response = webClient.get()
        .uri("/reports/export")
        .httpRequest(request -> {
            HttpClientRequest nativeRequest =
                    request.getNativeRequest();

            nativeRequest.responseTimeout(
                    Duration.ofSeconds(10));
        })
        .retrieve()
        .bodyToMono(String.class);
~~~

Cần import `reactor.netty.http.client.HttpClientRequest`. Ví dụ này dùng API native của Reactor Netty; nếu WebClient đang dùng JDK HttpClient, Jetty hoặc connector khác thì không có cùng native request API.

### 3.3. responseTimeout không phải connect timeout

`responseTimeout` chỉ xử lý khoảng im lặng khi đọc response. Nó không thay thế:

- Timeout chờ connection từ pool.
- Timeout thiết lập TCP connection.
- Timeout DNS.
- Timeout TLS handshake.
- Deadline tổng của nghiệp vụ.

Nếu server chưa nhận được kết nối, response read timeout không phải lớp phù hợp để chẩn đoán lỗi connect.

## 4. Mono.timeout(Duration) giới hạn thời gian chờ kết quả Mono

`Mono` phát tối đa một giá trị. `Mono.timeout(Duration)` phát `TimeoutException` nếu không có `onNext` trước khi thời gian quy định hết hạn.

~~~java
Mono<Product> product = webClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(4));
~~~

Với `bodyToMono`, decoder thường chỉ phát DTO sau khi body đã được đọc xong. Vì vậy, nếu response body mất 7 giây mới hoàn tất thì deadline 4 giây có thể hết hạn, ngay cả khi server gửi từng chunk đều đặn mỗi 200 ms.

Một vài chi tiết:

- Bộ đếm bắt đầu khi subscribe, không phải lúc lắp ráp Publisher.
- Khi hết hạn trước `onNext`, Reactor phát `TimeoutException` hoặc subscribe fallback nếu đã cấu hình.
- Nếu Mono hoàn tất rỗng trước deadline, nó vẫn là một kết quả empty bình thường; không có timeout.
- Khi timeout thắng, Reactor cancel upstream subscription. Request WebClient vì vậy được hủy ở phía client.
- Timeout không chứng minh server chưa xử lý request. Server có thể đã nhận và xử lý POST trước khi client hủy chờ response.

Có thể dùng fallback:

~~~java
Mono<Product> product = webClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(
                Duration.ofSeconds(4),
                Mono.error(new PartnerDeadlineExceeded()));
~~~

`PartnerDeadlineExceeded` là exception do ứng dụng định nghĩa. Fallback phải có kiểu tương thích với Mono kết quả.

## 5. Flux.timeout(Duration) không phải deadline tổng của cả stream

`Flux` có thể phát nhiều phần tử. Với `Flux.timeout(Duration)`, timeout được tính:

- Từ lúc subscribe tới phần tử đầu tiên.
- Sau đó được đặt lại sau mỗi phần tử.
- Nếu không có phần tử mới trong khoảng thời gian cho phép, sequence timeout.

Ví dụ:

~~~java
Flux<ServerEvent> events = webClient.get()
        .uri("/events")
        .retrieve()
        .bodyToFlux(ServerEvent.class)
        .timeout(Duration.ofSeconds(15));
~~~

Nếu server phát một event mỗi 5 giây, Flux có thể tiếp tục chạy nhiều giờ. Mỗi khoảng chờ đều nhỏ hơn 15 giây nên không có timeout.

| Publisher | Ý nghĩa của `timeout(Duration)` |
| --- | --- |
| `Mono<T>` | Chờ một giá trị đầu tiên trong khoảng thời gian quy định |
| `Flux<T>` | Chờ phần tử đầu tiên, rồi giới hạn khoảng im lặng giữa các phần tử |
| `bodyToMono(String.class)` | Thường phát một String sau khi body được đọc và decode xong |
| `bodyToFlux(DataBuffer.class)` | Có thể phát nhiều buffer trong lúc body đang streaming |

Nếu cần giới hạn tổng thời gian của một Flux hữu hạn và kích thước dữ liệu cho phép aggregate, có thể dùng:

~~~java
Mono<List<ServerEvent>> allEvents = webClient.get()
        .uri("/events/batch")
        .retrieve()
        .bodyToFlux(ServerEvent.class)
        .collectList()
        .timeout(Duration.ofSeconds(10));
~~~

Cách này tích lũy toàn bộ event trong memory. Không dùng `collectList()` cho stream vô hạn hoặc body lớn.

Với stream lớn cần deadline tuyệt đối, phải thiết kế timer/deadline độc lập và hủy subscription khi hết thời gian. Không nhầm `Flux.timeout(Duration)` với giới hạn tuổi thọ tổng của stream.

## 6. Bảng so sánh: timeout tầng mạng và timeout Reactor

| Tiêu chí | Reactor Netty responseTimeout | Mono.timeout | Flux.timeout |
| --- | --- | --- | --- |
| Tầng hoạt động | HTTP connector / Netty channel | Reactor sequence | Reactor sequence |
| Theo dõi | Khoảng giữa các network read operations | Thời gian chờ `onNext` của Mono | Khoảng giữa các `onNext` |
| Bắt đầu | Sau khi request được gửi và response đang được đọc | Khi subscribe Publisher | Khi subscribe; đặt lại sau mỗi item |
| Phạm vi | Đọc response bytes | Chờ giá trị Mono | Chờ item tiếp theo |
| Stream dài nhưng có dữ liệu đều | Có thể chạy lâu nếu read gap luôn dưới ngưỡng | `bodyToMono` có thể timeout trước khi body hoàn tất | Không timeout nếu gap giữa item đủ ngắn |
| Ngoại lệ điển hình | Netty `ReadTimeoutException` được bọc theo connector | `TimeoutException` | `TimeoutException` |
| Dùng để | Phát hiện server/network ngừng gửi dữ liệu | Deadline cho request trả một kết quả | Giới hạn thời gian im lặng giữa các event |

Không có một con số timeout duy nhất thay thế được các lớp này. Chọn lớp theo failure mode cần kiểm soát.

## 7. Các timeout khác trong Reactor Netty

Ngoài response read timeout, Reactor Netty có các cấu hình riêng cho từng giai đoạn.

| Giai đoạn | API | Ý nghĩa |
| --- | --- | --- |
| Connection pool | `pendingAcquireTimeout` | Thời gian tối đa chờ lấy connection từ pool |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` | Thời gian tối đa thiết lập kết nối tới remote peer |
| TLS | `handshakeTimeout` | Thời gian tối đa hoàn tất TLS handshake |
| DNS | `queryTimeout` | Thời gian tối đa cho một DNS query |
| Response read | `responseTimeout` | Khoảng tối đa giữa các lần đọc response ở tầng mạng |
| Reactive operation | `Mono.timeout` / `Flux.timeout` | Deadline hoặc khoảng chờ tín hiệu theo semantics Publisher |

Tài liệu Reactor Netty release hiện hành ghi các mặc định tham khảo:

- Pool pending acquire: 45 giây.
- TCP connect: 30 giây.
- TLS handshake: 10 giây.
- DNS query: 5 giây.
- `responseTimeout`: không được đặt mặc định.

Các giá trị này thuộc Reactor Netty và có thể thay đổi theo phiên bản, cấu hình hoặc connector. WebClient cũng hỗ trợ JDK HttpClient, Jetty và Apache HttpComponents; các connector đó có API và default riêng. Hãy kiểm tra dependency thực tế của ứng dụng trước khi dựa vào một giá trị mặc định.

### 7.1. Cấu hình nhiều timeout cùng lúc

~~~java
ConnectionProvider pool =
        ConnectionProvider.builder("partner-api")
                .maxConnections(40)
                .pendingAcquireTimeout(Duration.ofMillis(400))
                .build();

HttpClient transport = HttpClient.create(pool)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2))
        .secure(ssl -> ssl.handshakeTimeout(
                Duration.ofSeconds(3)))
        .resolver(spec -> spec.queryTimeout(
                Duration.ofSeconds(1)));

WebClient partnerClient = WebClient.builder()
        .baseUrl("https://partner.example.test")
        .clientConnector(
                new ReactorClientHttpConnector(transport))
        .build();
~~~

Ví dụ cần các import Reactor Netty, Netty và Spring WebFlux tương ứng. `secure(...)` cấu hình TLS cho HTTPS; nó không cần thiết cho endpoint HTTP thuần.

Cấu hình trên kiểm soát:

- Chờ pool tối đa 400 ms.
- TCP connect tối đa 1 giây.
- Khoảng im lặng khi đọc response tối đa 2 giây.
- TLS handshake tối đa 3 giây.
- Mỗi DNS query tối đa 1 giây.

Đây vẫn chưa phải deadline tổng. Một response stream có thể kéo dài hơn 2 giây nếu liên tục có network read. Nếu nghiệp vụ cần giới hạn tổng thời gian của request, đặt thêm timeout ở Publisher thích hợp.

## 8. Kết hợp timeout theo ngân sách thời gian

Giả sử một API đối tác có SLA 4 giây. Có thể chia ngân sách minh họa như sau:

| Thành phần | Ngưỡng ví dụ |
| --- | ---: |
| Chờ connection pool | 300 ms |
| TCP connect | 800 ms |
| TLS handshake | 1.000 ms |
| Response read gap | 1.200 ms |
| Tổng thời gian cho Mono request | 4.000 ms |

Các ngưỡng phase không cộng đơn giản thành deadline tổng. Chúng giới hạn từng giai đoạn hoặc khoảng chờ riêng; timeout tổng là lớp chặn cuối để giữ SLA.

Ví dụ đặt deadline cho kết quả:

~~~java
Mono<PartnerResponse> response = partnerClient.get()
        .uri("/v1/data")
        .retrieve()
        .bodyToMono(PartnerResponse.class)
        .timeout(Duration.ofSeconds(4));
~~~

Đặt timeout tổng lớn hơn các phase timeout một cách hợp lý để có chỗ cho các giai đoạn nối tiếp. Nếu timeout tổng nhỏ hơn một timeout phase, deadline tổng có thể kết thúc trước và che mất lỗi phase mà bạn muốn quan sát.

Không chọn timeout chỉ dựa trên giá trị thấp nhất có thể. Hãy dựa vào latency percentile, SLA, thời gian xử lý server, kích thước body và mức độ chấp nhận của người gọi.

## 9. Vị trí toán tử timeout khi có retry

Vị trí của `timeout` so với `retryWhen` làm thay đổi phạm vi deadline.

### 9.1. Timeout bao trùm toàn bộ retry

~~~java
Mono<Product> result = Mono.defer(this::callOnce)
        .retryWhen(Retry.backoff(
                2, Duration.ofMillis(150)))
        .timeout(Duration.ofSeconds(4));
~~~

Timeout nằm sau `retryWhen` nên bao trùm các lần thử và thời gian backoff. Tổng thời gian của chuỗi retry không thể vượt quá deadline Publisher này mà không phát timeout.

### 9.2. Timeout riêng cho mỗi lần thử

~~~java
Mono<Product> result = Mono.defer(this::callOnce)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(
                2, Duration.ofMillis(150)));
~~~

Ở đây mỗi lần subscribe lại có timeout 2 giây. Tổng thời gian gồm nhiều lần thử và backoff có thể vượt 2 giây.

Hai cách không tương đương. Nếu có SLA cho toàn bộ thao tác, đặt một deadline bao ngoài cả retry chain. Vẫn có thể giữ timeout ngắn hơn bên trong cho từng attempt nếu cần.

### 9.3. Không retry mù quáng sau timeout

Khi client timeout, server có thể đã nhận và xử lý request nhưng response chưa tới. Retry một POST tạo đơn hàng hoặc thanh toán có thể tạo tác dụng phụ trùng lặp.

Chỉ retry thao tác có thể lặp an toàn hoặc dùng idempotency key và contract tương ứng. Dùng số lần retry nhỏ, backoff, jitter và tổng deadline rõ ràng.

## 10. Timeout và cancellation

Khi `Mono.timeout` hoặc `Flux.timeout` phát timeout, Reactor cancel subscription upstream. Với WebClient, việc hủy có thể khiến client ngừng đọc body, đóng hoặc loại connection tùy trạng thái giao thức và connector.

Cancellation không phải lệnh đảm bảo server dừng xử lý. Ví dụ:

1. Client gửi POST tạo báo cáo.
2. Server nhận request và bắt đầu ghi dữ liệu.
3. Client hết deadline trước khi nhận response.
4. Client hủy subscription.
5. Server vẫn có thể hoàn tất thao tác và ghi dữ liệu.

Vì vậy:

- Không suy luận rằng server chưa xử lý chỉ từ timeout phía client.
- Với thao tác ghi, dùng idempotency key hoặc cơ chế kiểm tra trạng thái.
- Không retry tự động khi chưa xác định semantics của operation.
- Theo dõi request ID để tra cứu kết quả sau timeout.
- Đảm bảo tài nguyên phía client được cleanup khi cancellation.

## 11. Chẩn đoán timeout qua exception và metrics

Tên exception giúp xác định tầng phát sinh, nhưng connector có thể bọc exception trong lớp Spring.

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| `PoolAcquireTimeoutException` | Pool đầy, pending queue dài, connection không được release kịp |
| Connect timeout | DNS đã có địa chỉ nhưng TCP connect không hoàn tất kịp |
| `ReadTimeoutException` | Không có network read trong khoảng responseTimeout |
| `TimeoutException` từ Reactor | Publisher không phát tín hiệu theo deadline |
| TLS handshake timeout | Certificate, handshake, network hoặc TLS server chậm |
| DNS query timeout | DNS resolver hoặc nameserver phản hồi chậm |

Có thể tìm cause chain:

~~~java
static boolean hasCauseNamed(
        Throwable error, String simpleName) {

    for (Throwable current = error;
         current != null;
         current = current.getCause()) {

        if (current.getClass().getSimpleName()
                .equals(simpleName)) {
            return true;
        }
    }

    return false;
}
~~~

Đây là helper chẩn đoán minh họa. Trong code production, nên phân loại theo exception type cụ thể của connector và giữ nguyên cause gốc khi chuyển thành domain exception.

Các metric hữu ích của Reactor Netty gồm:

- Thời gian DNS resolve.
- Thời gian connect.
- Thời gian TLS handshake.
- Thời gian response.
- Connection pool active, idle và pending.
- Số request lỗi.
- Dữ liệu gửi/nhận.

Tách metric theo service và route template. Không gắn raw URL chứa ID hoặc query nhạy cảm làm metric tag vì có thể tạo cardinality rất lớn.

## 12. Chương trình Java 17+ chạy được: so sánh read-gap timeout và Mono deadline

Chương trình này tạo HTTP server local bằng `ServerSocket` của JDK và gọi server bằng WebClient/Reactor Netty.

Server có hai endpoint:

- `/pause`: chờ 450 ms rồi mới gửi response. Client đặt response read timeout 150 ms, nên network read gap timeout xảy ra.
- `/stream`: gửi 6 chunk, mỗi chunk cách nhau 60 ms. Tổng body mất khoảng 360 ms, nhưng mỗi khoảng trống giữa các lần gửi nhỏ hơn 150 ms.

Cùng một client có `responseTimeout` 150 ms. Request stream vẫn có thể hoàn tất với deadline Mono 2 giây, nhưng bị timeout nếu đặt `Mono.timeout` 250 ms.

### 12.1. Cấu trúc dự án

~~~text
webclient-timeout-layers/
  pom.xml
  src/main/java/example/timeout/TimeoutLayersDemo.java
~~~

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Boot BOM quản lý Spring Framework, Reactor và Reactor Netty tương thích.

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webclient-timeout-layers</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.3. TimeoutLayersDemo.java

~~~java
package example.timeout;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

public final class TimeoutLayersDemo {

    private static void writeAscii(
            OutputStream output, String value) throws IOException {

        output.write(value.getBytes(StandardCharsets.US_ASCII));
    }

    private static void writeFixedResponse(
            OutputStream output) throws IOException {

        byte[] body = "late".getBytes(StandardCharsets.UTF_8);

        writeAscii(output,
                "HTTP/1.1 200 OK\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Connection: close\r\n\r\n");

        output.write(body);
        output.flush();
    }

    private static void writeChunkedResponse(
            OutputStream output)
            throws IOException, InterruptedException {

        writeAscii(output,
                "HTTP/1.1 200 OK\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n"
                + "Transfer-Encoding: chunked\r\n"
                + "Connection: close\r\n\r\n");

        output.flush();

        byte[] body = "ABCDEF".getBytes(StandardCharsets.UTF_8);

        for (byte value : body) {
            writeAscii(output, "1\r\n");
            output.write(value);
            writeAscii(output, "\r\n");
            output.flush();
            Thread.sleep(60);
        }

        writeAscii(output, "0\r\n\r\n");
        output.flush();
    }

    private static void handle(Socket socket) {
        try (Socket client = socket) {
            client.setSoTimeout(3_000);

            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));

            String requestLine = reader.readLine();
            if (requestLine == null) {
                return;
            }

            String[] requestParts = requestLine.split(" ");
            String path = requestParts.length > 1
                    ? requestParts[1]
                    : "/";

            String header;
            while ((header = reader.readLine()) != null
                    && !header.isEmpty()) {
                // Đọc hết request headers trước khi gửi response.
            }

            OutputStream output = client.getOutputStream();

            if ("/pause".equals(path)) {
                Thread.sleep(450);
                writeFixedResponse(output);
            }
            else if ("/stream".equals(path)) {
                writeChunkedResponse(output);
            }
            else {
                writeAscii(output,
                        "HTTP/1.1 404 Not Found\r\n"
                        + "Content-Length: 0\r\n"
                        + "Connection: close\r\n\r\n");
                output.flush();
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
        catch (IOException ignored) {
            // Client có thể đã hủy request vì timeout.
        }
    }

    private static boolean hasCauseNamed(
            Throwable error, String simpleName) {

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current.getClass().getSimpleName()
                    .equals(simpleName)) {
                return true;
            }
        }

        return false;
    }

    private static void expectTimeout(
            String label,
            Mono<?> publisher,
            String expectedCause) {

        try {
            publisher.block(Duration.ofSeconds(3));
            throw new AssertionError(
                    label + " should have timed out");
        }
        catch (RuntimeException error) {
            if (!hasCauseNamed(error, expectedCause)) {
                throw new AssertionError(
                        label + " did not contain " + expectedCause,
                        error);
            }

            System.out.println(label + "=TIMEOUT");
        }
    }

    public static void main(String[] args) throws Exception {
        ServerSocket serverSocket = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"));

        ExecutorService workers = Executors.newCachedThreadPool(
                task -> {
                    Thread thread = new Thread(task);
                    thread.setDaemon(true);
                    return thread;
                });

        Thread acceptor = new Thread(() -> {
            while (!serverSocket.isClosed()) {
                try {
                    Socket socket = serverSocket.accept();
                    workers.execute(() -> handle(socket));
                }
                catch (IOException error) {
                    if (!serverSocket.isClosed()) {
                        throw new IllegalStateException(error);
                    }
                }
            }
        }, "timeout-demo-acceptor");

        acceptor.setDaemon(true);
        acceptor.start();

        try {
            String baseUrl = "http://127.0.0.1:"
                    + serverSocket.getLocalPort();

            HttpClient transport = HttpClient.create()
                    .responseTimeout(Duration.ofMillis(150));

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .clientConnector(
                            new ReactorClientHttpConnector(transport))
                    .build();

            expectTimeout(
                    "network-read-gap",
                    client.get()
                            .uri("/pause")
                            .retrieve()
                            .bodyToMono(String.class),
                    "ReadTimeoutException");

            Mono<String> streamWithShortDeadline = client.get()
                    .uri("/stream")
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(250));

            expectTimeout(
                    "mono-total-deadline",
                    streamWithShortDeadline,
                    "TimeoutException");

            String stream = client.get()
                    .uri("/stream")
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofSeconds(2))
                    .block(Duration.ofSeconds(3));

            if (!"ABCDEF".equals(stream)) {
                throw new AssertionError(
                        "Unexpected body: " + stream);
            }

            System.out.println(
                    "stream-over-read-gap=OK:" + stream);
        }
        finally {
            serverSocket.close();
            workers.shutdownNow();
            acceptor.join(1_000);
        }
    }
}
~~~

### 12.4. Chạy chương trình

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.timeout.TimeoutLayersDemo
~~~

**Stdout dự kiến:**

~~~text
network-read-gap=TIMEOUT
mono-total-deadline=TIMEOUT
stream-over-read-gap=OK:ABCDEF
~~~

Diễn giải:

- `/pause` không gửi byte nào trong 450 ms. `responseTimeout` 150 ms phát network read timeout trước khi server trả headers/body.
- `/stream` gửi chunk mỗi 60 ms. Khoảng im lặng luôn nhỏ hơn 150 ms nên response read timeout không kích hoạt.
- Tổng thời gian stream khoảng 360 ms. `Mono.timeout(250 ms)` hết hạn vì `bodyToMono(String.class)` chỉ phát String sau khi body hoàn tất.
- Cùng stream đó thành công với deadline Mono 2 giây dù tổng thời gian lớn hơn response read timeout 150 ms.

Chương trình dùng socket local, không gọi internet. Thời gian thực tế có thể dao động nhẹ theo scheduler và hệ điều hành; các ngưỡng được đặt đủ khoảng cách để thể hiện khác biệt.

## 13. Kiểm thử timeout bằng StepVerifier

Với logic Reactor thuần, có thể dùng virtual time để test mà không phải chờ đồng hồ thật:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
                .timeout(Duration.ofSeconds(2)))
        .thenAwait(Duration.ofSeconds(2))
        .expectError(TimeoutException.class)
        .verify();
~~~

Cần dependency `reactor-test` ở scope test. Virtual time phù hợp cho toán tử Reactor; nó không mô phỏng DNS, TCP connect, TLS hoặc network read timeout của socket thật.

Đối với timeout tầng mạng, nên có integration test với connector đang dùng và server có khả năng:

- Trì hoãn byte đầu tiên.
- Gửi chunk đều đặn.
- Dừng gửi giữa chừng.
- Đóng connection đột ngột.
- Gửi body dài hơn deadline Mono.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi responseTimeout là tổng thời gian response | Stream liên tục vẫn có thể chạy rất lâu | Thêm deadline Publisher nếu cần giới hạn tổng |
| Coi Mono.timeout là read inactivity timeout | Không phân biệt được phase mạng với thời gian toàn request | Dùng responseTimeout cho read gap và Mono timeout cho kết quả |
| Dùng Flux.timeout để giới hạn tuổi thọ stream | Stream phát event đều có thể chạy vô hạn | Dùng deadline tuyệt đối riêng |
| Chỉ đặt connect timeout | Server có thể kết nối được nhưng ngừng gửi response | Cấu hình responseTimeout |
| Chỉ đặt responseTimeout | Pool, DNS, connect hoặc TLS vẫn có thể chờ theo timeout riêng | Đặt timeout theo từng giai đoạn |
| Cấu hình timeout nhưng không kiểm tra connector | API Reactor Netty không áp dụng cho connector khác | Xác định ClientHttpConnector thực tế |
| Timeout tổng nhỏ hơn mọi phase timeout | Deadline tổng kết thúc trước và che phase timeout | Thiết kế ngân sách thời gian có thứ tự |
| Đặt timeout trước retry rồi nghĩ nó bao trùm toàn bộ retry | Mỗi attempt có thể có timer riêng; tổng thời gian dài hơn dự kiến | Đặt deadline sau retry chain nếu cần giới hạn tổng |
| Retry mọi timeout | Có thể tăng tải và lặp side effect | Retry có điều kiện và có idempotency |
| Nghĩ cancel đồng nghĩa server dừng xử lý | Server có thể đã hoàn thành thao tác | Dùng idempotency key và tra cứu request ID |
| Dùng một timeout cho mọi API | Endpoint streaming và endpoint RPC có đặc tính khác nhau | Cấu hình theo service và loại operation |
| Không quan sát pool metrics | Pool bão hòa bị hiểu nhầm là server chậm | Theo dõi pending acquire và active connections |
| Đặt timeout quá ngắn | Tăng false timeout khi có jitter hoặc GC pause | Chọn ngưỡng theo latency percentile và SLA |

## 15. Checklist thiết kế timeout production

- [ ] Xác định connector đang dùng: Reactor Netty, JDK HttpClient, Jetty hay Apache.
- [ ] Có timeout chờ connection pool phù hợp với concurrency.
- [ ] Có connect timeout.
- [ ] Có DNS/TLS timeout khi cần kiểm soát các phase đó.
- [ ] Cấu hình responseTimeout cho network read inactivity.
- [ ] Đặt Mono deadline cho request trả một kết quả khi nghiệp vụ có SLA tổng.
- [ ] Với Flux streaming, phân biệt inter-item timeout và deadline tổng.
- [ ] Đặt timeout quanh retry chain nếu SLA áp dụng cho toàn bộ lần thử và backoff.
- [ ] Giữ cause gốc để phân loại timeout theo phase.
- [ ] Theo dõi pool pending, connect time, response time và request errors.
- [ ] Không retry write operation khi chưa có idempotency strategy.
- [ ] Kiểm thử byte đầu tiên chậm, stream đều, stream bị ngắt và tổng body quá hạn.
- [ ] Không log URL/header chứa token hoặc dữ liệu nhạy cảm.

## 16. Tự kiểm tra

**Câu 1.** `responseTimeout` của Reactor Netty đo gì?

Khoảng thời gian tối đa giữa các lần network-level read operation khi đang đọc một response.

**Câu 2.** Response stream có thể chạy lâu hơn responseTimeout không?

Có. Nếu dữ liệu tiếp tục được đọc và mỗi khoảng im lặng đều nhỏ hơn timeout, stream có thể kéo dài lâu hơn tổng giá trị timeout.

**Câu 3.** `Mono.timeout(Duration)` phát timeout khi nào?

Khi Mono không phát `onNext` trong khoảng thời gian đã đặt, tính từ lúc subscribe.

**Câu 4.** Vì sao `bodyToMono(String.class).timeout(2s)` có thể giới hạn toàn bộ response body?

Mono String chỉ phát sau khi body được đọc và decode thành công; timer vẫn đang chờ kết quả trong quá trình đó.

**Câu 5.** `Flux.timeout(Duration)` có phải tổng deadline không?

Không. Nó giới hạn khoảng chờ giữa các item, bắt đầu từ subscribe cho item đầu tiên.

**Câu 6.** Vì sao một Flux SSE có thể chạy hàng giờ dù timeout là 15 giây?

Vì mỗi event đến trước khi khoảng im lặng 15 giây hết hạn, timer được đặt lại.

**Câu 7.** `CONNECT_TIMEOUT_MILLIS` khác `responseTimeout` thế nào?

Connect timeout giới hạn việc thiết lập TCP connection; responseTimeout giới hạn khoảng im lặng khi đọc response.

**Câu 8.** `pendingAcquireTimeout` kiểm soát giai đoạn nào?

Thời gian chờ lấy connection từ pool khi chưa có connection sẵn sàng.

**Câu 9.** Đặt `timeout` trước hay sau `retryWhen` nếu cần deadline tổng?

Đặt timeout bao ngoài sau retryWhen để nó bao gồm các lần thử và backoff.

**Câu 10.** Client timeout có chứng minh server chưa thực hiện POST không?

Không. Server có thể đã nhận và xử lý request trước khi client hủy chờ response.

**Câu 11.** Có thể dùng `responseTimeout` với mọi connector WebClient không?

Không. Đây là API của Reactor Netty; connector JDK, Jetty hoặc Apache có cấu hình riêng.

**Câu 12.** Nên test timeout bằng cách nào?

Dùng virtual time cho toán tử Reactor và integration test với connector/server thật cho DNS, connect, network read gap và streaming.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình ClientHttpConnector, Reactor Netty, connect timeout và response timeout.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient reactive API và các connector được hỗ trợ.
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration): pool acquire, response, connect, TLS và DNS timeout.
- [Reactor Netty — HttpClientRequest JavaDoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClientRequest.html): semantics chính xác của `responseTimeout(Duration)` và giới hạn giữa các network-level read operations.
- [Reactor Netty — HttpClient JavaDoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html): cấu hình response timeout cho HttpClient.
- [Reactor Core — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `Mono.timeout` và semantics chờ onNext.
- [Reactor Core — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `Flux.timeout` và semantics khoảng giữa các phần tử.

**Ghi nhớ:** Timeout tầng mạng của Reactor Netty phát hiện khoảng im lặng khi đọc response; `Mono.timeout` giới hạn thời gian chờ một kết quả Mono; `Flux.timeout` giới hạn khoảng im lặng giữa các event. Kết hợp timeout theo phase với deadline nghiệp vụ, đặt deadline bao ngoài retry chain khi cần SLA tổng, và nhớ rằng client cancellation không đảm bảo server đã dừng xử lý.