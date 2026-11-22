# Mô phỏng timeout, mất kết nối và giới hạn tầng truyền tải

## 1. Mục tiêu của kiểm thử HTTP client

Một HTTP client không chỉ cần gửi đúng method, URL, header và body. Trong môi trường thật, request còn có thể chậm, server ngừng phản hồi, kết nối bị đóng giữa chừng hoặc client không lấy được connection từ connection pool.

Các tình huống đó thuộc những tầng khác nhau. Nếu gộp tất cả thành một khái niệm “request lỗi”, test có thể bỏ sót lỗi cấu hình timeout, retry quá mức hoặc xử lý sai một response đã bắt đầu được gửi.

Một bộ kiểm thử HTTP client thường cần xác nhận:

- Client gửi request đúng hợp đồng: method, URI, header, body và content type.
- Client xử lý đúng HTTP status như 400, 404, 429 hoặc 503.
- Client phản ứng đúng khi không có response do timeout hoặc kết nối bị ngắt.
- Client không chờ vô hạn và có giới hạn thời gian rõ ràng.
- Client hủy request và giải phóng tài nguyên khi caller timeout hoặc cancel.
- Retry chỉ xảy ra theo chính sách đã định nghĩa và không tạo tác dụng phụ trùng lặp.
- Lỗi tầng transport được chuyển thành lỗi nghiệp vụ phù hợp để service phía trên xử lý.

Điểm quan trọng là phân biệt một HTTP response lỗi với một lỗi transport. HTTP 503 vẫn là một response hợp lệ: server đã nhận request và trả status. Timeout hoặc connection reset thường không có một response hoàn chỉnh để client kiểm tra status hoặc body.

## 2. Phân biệt các loại timeout

Không có một timeout duy nhất bao phủ mọi giai đoạn của request. Một request có thể trải qua các bước:

~~~text
Lấy connection từ pool
        |
        v
DNS lookup
        |
        v
TCP connect
        |
        v
TLS handshake (nếu HTTPS)
        |
        v
Gửi request
        |
        v
Chờ response headers
        |
        v
Đọc response body
        |
        v
Deserialize / xử lý dữ liệu
~~~

Các giới hạn thường gặp:

| Loại giới hạn | Điều nó giới hạn | Ví dụ lỗi hoặc triệu chứng |
|---|---|---|
| Connection pool acquire timeout | Thời gian chờ một connection khả dụng trong pool | Pool hết connection, request nằm chờ |
| DNS timeout | Thời gian phân giải tên miền | Không tìm được địa chỉ IP kịp thời |
| Connect timeout | Thời gian thiết lập TCP connection | Server không phản hồi bắt tay TCP |
| TLS handshake timeout | Thời gian hoàn tất thương lượng TLS | Kết nối HTTPS bị treo trong handshake |
| Response/read timeout | Thời gian chờ dữ liệu từ server sau khi kết nối | Server nhận request nhưng phản hồi quá chậm |
| Overall request deadline | Tổng thời gian cho toàn bộ thao tác | Request vượt ngân sách thời gian của caller |

Tên và cách triển khai từng timeout tùy HTTP connector. Với Reactor Netty, **responseTimeout** là giới hạn giữa các lần đọc dữ liệu ở tầng mạng; nó không đồng nghĩa với tổng thời gian của toàn bộ publisher. Có thể dùng toán tử **Mono.timeout(...)** hoặc **Flux.timeout(...)** để đặt deadline cho luồng reactive.

Với client blocking, read timeout thường giới hạn thời gian chờ dữ liệu ở lần đọc tiếp theo. Nó cũng không nhất thiết là tổng thời gian từ lúc bắt đầu tới khi nhận xong body. Một response truyền từng phần đều đặn có thể kéo dài hơn giá trị read timeout mà không vi phạm khoảng chờ giữa hai lần đọc.

Cần xác định rõ yêu cầu: muốn giới hạn thời gian bắt đầu kết nối, thời gian chờ byte tiếp theo hay tổng thời gian mà nghiệp vụ cho phép chờ.

## 3. Chọn công cụ mô phỏng phù hợp

Không phải mọi công cụ giả lập HTTP đều mô phỏng được lỗi transport.

| Công cụ | Phù hợp để kiểm tra | Có socket HTTP thật không? |
|---|---|---|
| **MockRestServiceServer** | Request expectation, response status/body/header và lỗi ở tầng request factory được giả lập | Không |
| **MockWebServer** | HTTP client thật gọi server local; response delay, disconnect, response body từng phần | Có |
| **WireMock** | Stub HTTP, delay, fault, mapping và kịch bản response | Có |
| Mock object của service | Cách service phía trên phản ứng với domain exception | Không |
| Server/container staging | TLS, proxy, DNS, network policy và đặc tính hạ tầng triển khai | Có, theo môi trường đó |

**MockRestServiceServer** rất hữu ích khi kiểm tra client được tạo bằng **RestClient** hoặc **RestTemplate**. Nó kiểm tra request và response thông qua cơ chế giả lập của Spring, nên test nhanh và không phụ thuộc cổng mạng.

Khi cần kiểm tra connect timeout, read timeout, socket disconnect hoặc response bị cắt giữa body, dùng một server local như **MockWebServer** hoặc **WireMock**. Các công cụ này cho HTTP client kết nối qua socket thật và cho phép điều khiển cách server phản hồi.

Không nên dùng mock service để kết luận HTTP connector đã xử lý đúng TCP reset. Mock service chỉ có thể giả lập kết quả ở ranh giới mà test đặt ra.

## 4. Kiểm tra hợp đồng request với MockRestServiceServer

Với Spring Framework 6.1 trở lên, **MockRestServiceServer** có thể bind vào **RestClient.Builder**. Với **RestTemplate**, nó cũng có thể bind trực tiếp vào instance được kiểm thử.

Ví dụ kiểm tra request mà RestClient gửi đi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.http.HttpMethod.GET;

class CatalogClientContractTest {

    @Test
    void shouldSendTheExpectedRequest() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo("https://catalog.example/items/42"))
                .andExpect(method(GET))
                .andRespond(withSuccess(
                        "{\"id\":42,\"name\":\"Keyboard\"}",
                        MediaType.APPLICATION_JSON
                ));

        String body = client.get()
                .uri("/items/42")
                .retrieve()
                .body(String.class);

        assertThat(body).contains("Keyboard");
        server.verify();
    }
}
~~~

Cách này phù hợp để xác nhận client dùng đúng URI, method, header và cách parse response. Có thể thêm expectation cho request body, query parameter hoặc số lần gọi.

MockRestServiceServer cũng có thể giả lập một số lỗi I/O bằng response creator phát sinh exception. Điều đó hữu ích để kiểm tra cách service chuyển lỗi, nhưng không tạo ra TCP reset thực, không đo connect/read timeout của socket và không kiểm tra connection pool của connector.

## 5. Chuẩn bị MockWebServer

MockWebServer thuộc thư viện OkHttp. Thêm dependency test phù hợp với phiên bản OkHttp được dự án quản lý, sau đó khởi động server trên cổng ngẫu nhiên.

~~~java
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class CatalogHttpClientTest {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws Exception {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws Exception {
        server.shutdown();
    }
}
~~~

Dùng URL do server cấp thay vì gán cổng cố định:

~~~java
String baseUrl = server.url("/").toString();
~~~

Mỗi test có thể enqueue một response khác nhau:

~~~java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":42,\"name\":\"Keyboard\"}"));
~~~

Khi HTTP client gửi request, MockWebServer lấy response tiếp theo trong hàng đợi và ghi lại request để test có thể xác nhận method, path, header và body.

Đóng server trong **@AfterEach** hoặc **try/finally** để tránh giữ cổng và thread sau khi test kết thúc. Không chia sẻ một hàng đợi response mutable giữa các test chạy song song nếu chúng có thể lấy response của nhau.

## 6. Mô phỏng read timeout với RestClient hoặc RestTemplate

Với client blocking, cần cấu hình timeout trên **ClientHttpRequestFactory** đang được sử dụng. Ví dụ dưới đây dùng **SimpleClientHttpRequestFactory** và giá trị timeout tính bằng mili giây:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(300);
requestFactory.setReadTimeout(200);

RestClient client = RestClient.builder()
        .baseUrl(baseUrl)
        .requestFactory(requestFactory)
        .build();
~~~

Có thể dùng cùng request factory với **RestTemplate**:

~~~java
RestTemplate restTemplate = new RestTemplate(requestFactory);
~~~

Nếu ứng dụng dùng Apache HttpComponents hoặc JDK HttpClient request factory, cấu hình timeout ở factory/connector tương ứng. Không nên cho rằng một timeout cấu hình trên factory này tự động áp dụng cho factory khác.

Để mô phỏng server phản hồi chậm, enqueue response trì hoãn header:

~~~java
import java.util.concurrent.TimeUnit;

server.enqueue(new MockResponse()
        .setHeadersDelay(800, TimeUnit.MILLISECONDS)
        .setBody("{\"id\":42}"));
~~~

Với read timeout 200 ms, lời gọi blocking nên kết thúc bằng lỗi I/O thay vì chờ đủ 800 ms:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.web.client.ResourceAccessException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void shouldFailWhenResponseHeadersArriveTooLate() {
    server.enqueue(new MockResponse()
            .setHeadersDelay(800, TimeUnit.MILLISECONDS)
            .setBody("{\"id\":42}"));

    assertThatThrownBy(() ->
            client.get()
                    .uri("/items/42")
                    .retrieve()
                    .body(String.class)
    ).isInstanceOf(ResourceAccessException.class);
}
~~~

Ví dụ giả định **client** được cấu hình với read timeout ngắn hơn độ trễ header. Connector có thể bọc lỗi timeout trong **ResourceAccessException** hoặc exception I/O khác tùy request factory. Nếu test cần xác nhận nguyên nhân cụ thể, hãy kiểm tra root cause theo connector và phiên bản đang dùng.

**setHeadersDelay(...)** kiểm soát thời gian trước khi server gửi response headers. **setBodyDelay(...)** có thể dùng để trì hoãn body sau khi headers đã được gửi. Hai trường hợp này giúp phân biệt timeout lúc chờ response với timeout trong lúc đọc body.

## 7. Mô phỏng timeout với WebClient và Reactor Netty

WebClient thường dùng Reactor Netty làm HTTP connector. Có thể đặt connect timeout và response timeout khi tạo **HttpClient**:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
        .responseTimeout(Duration.ofMillis(200));

WebClient webClient = WebClient.builder()
        .baseUrl(baseUrl)
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

**CONNECT_TIMEOUT_MILLIS** giới hạn thời gian thiết lập TCP connection. **responseTimeout** cấu hình thời gian chờ dữ liệu giữa các lần đọc ở tầng mạng. Nó không phải deadline tổng cho mọi bước của request.

Nếu nghiệp vụ cần tổng thời gian chờ tối đa, áp dụng timeout trên publisher:

~~~java
Mono<String> result = webClient.get()
        .uri("/items/42")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(1));
~~~

Khi dùng cả connector timeout và publisher timeout, test nên biết timeout nào được kỳ vọng kích hoạt. Nếu publisher deadline ngắn hơn response timeout, lỗi có thể đến từ toán tử Reactor trước khi connector timeout xảy ra.

### Test response timeout

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void shouldFailWhenServerDoesNotSendHeadersInTime() {
    server.enqueue(new MockResponse()
            .setHeadersDelay(800, TimeUnit.MILLISECONDS)
            .setBody("late"));

    StepVerifier.create(webClient.get()
                    .uri("/slow")
                    .retrieve()
                    .bodyToMono(String.class))
            .expectError()
            .verify(Duration.ofSeconds(2));
}
~~~

Test có giới hạn thời gian verify để chính test không chờ vô hạn nếu cấu hình bị sai. Trong test thực tế, có thể bọc lời gọi thành method của client ứng dụng rồi kiểm tra exception domain mà method đó phát ra.

Nếu ứng dụng ánh xạ lỗi connector thành **CatalogUnavailableException**, hãy kiểm tra exception đó ở ranh giới service. Đừng buộc mọi test phải phụ thuộc một class exception nội bộ của Netty nếu chi tiết đó không phải hợp đồng mà ứng dụng muốn công bố.

### Test overall deadline

Response timeout và overall deadline là hai hành vi khác nhau. Có thể mô phỏng server gửi body chậm theo từng phần để response timeout không nhất thiết kích hoạt, nhưng tổng thời gian vẫn vượt deadline nghiệp vụ.

~~~java
Mono<String> operation = webClient.get()
        .uri("/slow-stream")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofMillis(500));
~~~

Test cho deadline tổng nên xác nhận publisher kết thúc trong khoảng thời gian cho phép và tác vụ bị cancel. Không dùng **Thread.sleep()** để suy đoán thời điểm timeout; dùng **StepVerifier.verify(Duration)** hoặc công cụ điều khiển thời gian của Reactor khi test logic dựa vào scheduler.

## 8. Mô phỏng server ngắt kết nối

Server có thể đóng socket sau khi nhận request nhưng trước khi gửi một response hoàn chỉnh. MockWebServer hỗ trợ điều khiển hành vi socket qua **SocketPolicy**.

Ví dụ đóng kết nối ngay sau khi nhận request:

~~~java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.SocketPolicy;

server.enqueue(new MockResponse()
        .setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST));
~~~

WebClient không nhận được status hoặc body hoàn chỉnh. Lời gọi thường kết thúc bằng lỗi transport; class exception cụ thể tùy connector và thời điểm socket bị đóng.

~~~java
StepVerifier.create(webClient.get()
                .uri("/items/42")
                .retrieve()
                .bodyToMono(String.class))
        .expectError()
        .verify(Duration.ofSeconds(2));
~~~

Với RestClient hoặc RestTemplate, test có thể xác nhận lỗi I/O được bọc bởi exception của Spring, ví dụ **ResourceAccessException**. Điều quan trọng là không coi tình huống này như một HTTP 500: server đã không gửi một response HTTP hoàn chỉnh.

### Phân biệt connection refused và connect timeout

Hai tình huống này không giống nhau:

- **Connection refused:** địa chỉ có thể truy cập nhưng không có process lắng nghe trên port, hoặc hệ điều hành từ chối kết nối. Lỗi thường xuất hiện nhanh.
- **Connect timeout:** client gửi yêu cầu thiết lập kết nối nhưng không nhận được phản hồi TCP kịp thời, ví dụ gói SYN bị firewall drop. Client chờ tới hết connect timeout.

Tắt MockWebServer rồi kết nối vào port vừa đóng thường tạo ra connection refused, không phải connect timeout. Muốn kiểm tra connect timeout thật cần một môi trường mạng có thể cố ý bỏ qua gói tin hoặc một proxy/network fault injector được kiểm soát. Không nên dùng một IP public ngẫu nhiên vì kết quả phụ thuộc mạng ngoài và làm test không ổn định.

## 9. Mô phỏng response body bị ngắt giữa chừng

Một server có thể gửi headers và một phần body rồi đóng kết nối. Tình huống này khác với việc server không trả lời từ đầu.

MockWebServer có policy ngắt trong lúc gửi body:

~~~java
server.enqueue(new MockResponse()
        .setBody("partial response")
        .setSocketPolicy(SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY));
~~~

Client có thể đã đọc được một phần dữ liệu trước khi nhận lỗi. Với JSON response, deserializer có thể báo body không hoàn chỉnh hoặc lỗi parse. Với stream lớn, ứng dụng có thể đã xử lý một số chunk trước khi kết nối bị đóng.

Test nên xác nhận hành vi ở cấp ứng dụng:

- Kết quả không được coi là thành công nếu body bắt buộc phải hoàn chỉnh.
- Tài nguyên hoặc buffer tạm phải được giải phóng.
- Không công bố một object domain nửa chừng nếu ứng dụng yêu cầu dữ liệu nguyên vẹn.
- Retry chỉ được thực hiện khi semantics của request cho phép.
- Nếu ứng dụng ghi file theo streaming, cần xóa file tạm hoặc đánh dấu file chưa hoàn chỉnh.

Một lỗi body bị cắt có thể xuất hiện sau khi headers và một phần byte đã tới client. Do đó, status có thể là 200 nhưng thao tác đọc body vẫn thất bại. Không được xem việc nhận status 200 là bằng chứng toàn bộ response đã được đọc thành công.

## 10. Retry và nguy cơ thực hiện thao tác hai lần

Khi request timeout hoặc mất kết nối, client không phải lúc nào cũng biết server đã xử lý request tới đâu.

Ví dụ:

~~~text
Client gửi POST /payments
          |
          v
Server nhận request và tạo payment
          |
          v
Server gửi response 201
          |
          X  Kết nối bị đứt trước khi client nhận response
          |
          v
Client thấy timeout, không biết payment đã được tạo hay chưa
~~~

Nếu client tự động retry POST, server có thể tạo payment thứ hai. Đây là tình huống **kết quả không xác định đối với client**: request có thể đã được thực hiện nhưng response bị mất.

Retry thường phù hợp hơn với thao tác idempotent như GET, hoặc với thao tác ghi có idempotency key được server hỗ trợ. Không chỉ dựa vào HTTP method; cần hiểu semantics của endpoint và bảo đảm server xử lý khóa idempotency một cách nguyên tử.

Một test retry nên xác nhận:

- Số lần request thực sự được gửi.
- Khoảng backoff và số lần retry tối đa.
- Những loại lỗi được retry, chẳng hạn một số lỗi kết nối hoặc status tạm thời.
- Những lỗi không được retry, như validation 400.
- POST có idempotency key không tạo tài nguyên trùng lặp.
- Cancellation hoặc deadline tổng có dừng retry tiếp theo hay không.

Ví dụ với WebClient và Reactor Retry:

~~~java
Mono<String> result = webClient.get()
        .uri("/catalog/items/42")
        .retrieve()
        .bodyToMono(String.class)
        .retryWhen(
                reactor.util.retry.Retry.backoff(
                        2,
                        Duration.ofMillis(100)
                )
        );
~~~

Cấu hình này cho tối đa hai lần retry sau lần gọi đầu, với backoff tăng dần. Trong ứng dụng thật, nên lọc loại exception được retry bằng **filter(...)** và đặt deadline tổng để retry không kéo dài quá ngân sách thời gian của caller.

Có thể xác nhận số request bằng **MockWebServer.takeRequest()** hoặc request count sau khi exchange kết thúc. Đối với test thời gian, tránh phụ thuộc vào một khoảng sleep cố định; dùng scheduler ảo của Reactor khi kiểm tra logic backoff độc lập với socket, và dùng server local khi cần xác nhận tương tác HTTP.

## 11. Connection pool và giới hạn tài nguyên

HTTP client thường tái sử dụng connection để giảm chi phí thiết lập TCP/TLS. Connection pool có giới hạn số connection đang hoạt động và có thể có hàng đợi chờ connection.

Nếu mọi connection đang bận, request mới có thể chờ trong pool. Đây là **pending acquire timeout**, khác với connect timeout: client chưa bắt đầu kết nối mới vì chưa lấy được connection từ pool.

Với Reactor Netty, có thể cấu hình pool:

~~~java
import java.time.Duration;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

ConnectionProvider provider = ConnectionProvider.builder("catalog-test")
        .maxConnections(1)
        .pendingAcquireTimeout(Duration.ofMillis(200))
        .build();

HttpClient httpClient = HttpClient.create(provider);
~~~

Để kiểm tra pool timeout, test cần giữ connection duy nhất đang được sử dụng, sau đó gửi một request thứ hai và xác nhận nó hết thời gian chờ acquire. Đây là test concurrency; cần điều khiển rõ khi request thứ nhất bắt đầu và khi nó được phép hoàn tất. Không dùng sleep để hy vọng hai request chồng lấp đúng lúc.

Khi test tạo connection provider riêng, hãy dispose provider sau khi test kết thúc để giải phóng pool và tài nguyên event loop liên quan:

~~~java
provider.dispose();
~~~

Cũng cần xác định các giới hạn khác như số connection tối đa, số request đồng thời, kích thước response body, số byte buffer và thời gian giữ connection nhàn rỗi. Test tải hoặc test concurrency có thể giúp phát hiện pool cạn, nhưng cần chạy với cấu hình gần môi trường thực tế.

## 12. HTTP status lỗi không phải lỗi kết nối

Một HTTP client có thể nhận response 429, 500 hoặc 503 hoàn chỉnh. Đây là kết quả ở tầng HTTP; client đã kết nối được tới server và đọc được status line cùng headers.

Với WebClient, **retrieve()** mặc định chuyển status 4xx/5xx thành **WebClientResponseException** nếu không tùy chỉnh status handling. Có thể kiểm tra status và body lỗi:

~~~java
StepVerifier.create(webClient.get()
                .uri("/unavailable")
                .retrieve()
                .bodyToMono(String.class))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(
                            org.springframework.web.reactive.function.client
                                    .WebClientResponseException.class
                    );
        })
        .verify();
~~~

Nếu ứng dụng dùng **onStatus(...)** để ánh xạ response lỗi thành exception domain, test cần xác nhận mapping đó. Đừng dùng một test chỉ kiểm tra **expectError()** cho cả HTTP 503 và TCP disconnect rồi kết luận hai tình huống được xử lý giống nhau; retry policy và cách hiển thị lỗi cho người dùng có thể khác.

Với RestClient, response status 4xx/5xx mặc định được xử lý qua status handler. Có thể cấu hình handler riêng để chuyển response thành exception domain. Lỗi I/O xảy ra trước khi nhận response thường được ném dưới dạng exception tài nguyên/kết nối của Spring hoặc connector.

## 13. Giới hạn của mô phỏng ở tầng transport

MockWebServer và WireMock chạy qua socket local nên phù hợp để kiểm tra nhiều hành vi HTTP thực. Nhưng chúng vẫn không đại diện đầy đủ cho mạng production.

| Điều cần xác nhận | Mô phỏng local có phù hợp? | Khi nào cần môi trường thật? |
|---|---|---|
| Server trì hoãn headers hoặc body | Có | Thường không cần |
| Server đóng socket trước response | Có | Thường không cần |
| Body bị cắt giữa chừng | Có | Cần nếu hành vi phụ thuộc proxy/connector triển khai |
| HTTP status 429/500/503 | Có | Cần khi xác nhận server/gateway production tạo status đó |
| Connect timeout do SYN bị drop | Không ổn định nếu chỉ dùng MockWebServer | Cần firewall hoặc network fault injector được kiểm soát |
| DNS timeout hoặc DNS record thay đổi | Không | Cần DNS test environment |
| TLS certificate hết hạn, sai hostname hoặc trust chain | Có thể dựng local TLS server, nhưng cần chứng chỉ test | Cần khi xác nhận trust store, proxy hoặc certificate của môi trường |
| Proxy buffering, rewrite header, idle timeout | Không nếu request đi thẳng vào local mock server | Cần test qua proxy tương ứng |
| Packet loss, jitter và băng thông giới hạn | Không mô phỏng đầy đủ | Cần network emulator hoặc môi trường kiểm thử mạng |
| HTTP/2, ALPN và TLS negotiation của deployment | Phụ thuộc server và connector test | Cần môi trường cấu hình tương đương production |

Không nên dùng internet công cộng để mô phỏng lỗi mạng. Một endpoint bên ngoài có thể thay đổi, giới hạn lưu lượng hoặc không phản hồi đúng thời điểm mong muốn. Test sẽ khó tái lập và không xác định được lỗi đến từ client, server bên ngoài hay mạng.

Với lỗi mạng cấp thấp, dùng một môi trường cô lập: local proxy, container network, firewall rule tạm thời hoặc công cụ network fault injection. Đặt giới hạn thời gian cho test và luôn dọn rule/container sau khi hoàn tất.

## 14. Cancellation và giải phóng tài nguyên

Với client reactive, caller có thể hủy subscription trước khi response hoàn tất. Client nên truyền cancellation xuống HTTP exchange, ngừng đọc body và giải phóng connection hoặc trả connection về pool theo đúng trạng thái connector cho phép.

Có thể kiểm tra cancellation bằng một server giữ response mở, tạo subscription, rồi cancel subscription từ test. Test cần quan sát server hoặc client-side hook để xác nhận request bị hủy; chỉ kiểm tra rằng subscriber không nhận thêm item chưa chứng minh socket đã được giải phóng.

Với client blocking, thread có thể bị interrupt hoặc caller timeout ở tầng bao ngoài. Cần hiểu request factory có hỗ trợ interruption/cancellation tới mức nào. Không phải mọi blocking HTTP implementation đều dừng I/O ngay lập tức khi thread bị interrupt.

Đối với streaming response, phải đóng stream hoặc response body sau khi đọc. Không đọc hết hoặc không đóng body có thể giữ connection trong trạng thái không thể tái sử dụng và làm pool cạn dần.

Test nên xác nhận:

- Subscription bị cancel khi deadline tổng hết hạn.
- Response body/stream được đóng sau khi xử lý.
- Connection pool không tăng số connection bị giữ qua nhiều lần chạy.
- Retry không tiếp tục sau cancellation.
- Tác vụ nền không tiếp tục ghi vào resource đã bị hủy.

## 15. Thiết kế test ổn định và dễ chẩn đoán

Timeout test dễ chập chờn nếu dùng thời gian quá ngắn hoặc phụ thuộc tải máy. Một vài nguyên tắc giúp kết quả đáng tin cậy:

- Dùng MockWebServer/WireMock local, không gọi dịch vụ công cộng.
- Đặt timeout đủ lớn để CI có thể chạy ổn định nhưng vẫn nhỏ hơn độ trễ cố ý của server.
- Dùng **StepVerifier.verify(Duration)** hoặc timeout của test framework để giới hạn thời gian chờ tổng.
- Dùng latch, barrier hoặc publisher có điều khiển để đồng bộ request và response.
- Không dùng **Thread.sleep()** để đoán lúc server đã nhận request hoặc lúc timeout sẽ xảy ra.
- Phân biệt lỗi HTTP status, lỗi kết nối, timeout, deserialize lỗi và cancellation.
- Kiểm tra số lần request và nội dung request khi test retry.
- Đóng MockWebServer, WireMock, connection provider và response stream sau test.
- Không chia sẻ queue response hoặc mutable request recorder giữa các test chạy song song.

Khi test thất bại, hãy ghi lại request đã nhận, response đã gửi, thời gian hoàn tất và exception root cause. Những dữ liệu đó giúp phân biệt lỗi ở tầng ứng dụng với lỗi do connector hoặc transport.

## 16. Ma trận chọn công cụ và loại lỗi

| Mục tiêu | Công cụ nên dùng |
|---|---|
| Kiểm tra URI, method, headers, body và HTTP status giả lập | MockRestServiceServer |
| Kiểm tra service ánh xạ lỗi I/O thành domain exception | MockRestServiceServer hoặc mock connector ở ranh giới phù hợp |
| Kiểm tra read/response timeout qua socket | MockWebServer hoặc WireMock |
| Kiểm tra server đóng kết nối sau request | MockWebServer với SocketPolicy |
| Kiểm tra response body bị cắt | MockWebServer/WireMock và HTTP client thật |
| Kiểm tra Reactor overall deadline và cancellation | StepVerifier, Reactor virtual time và server có điều khiển |
| Kiểm tra connection pool acquire timeout | Reactor Netty ConnectionProvider và test concurrency có đồng bộ |
| Kiểm tra DNS, TLS, proxy, packet loss hoặc network policy | Môi trường mạng kiểm thử tương ứng |

Không có một mock duy nhất mô phỏng được mọi tầng. Hãy dùng MockRestServiceServer để xác nhận hợp đồng request/response của Spring client; dùng MockWebServer hoặc WireMock để kiểm tra HTTP connector và lỗi socket có thể tái lập; dùng môi trường mạng thật khi cần xác nhận DNS, TLS, proxy hoặc hành vi hạ tầng.

Một HTTP client đáng tin cậy cần giới hạn thời gian rõ ràng, phân biệt response lỗi với lỗi transport, xử lý disconnect và cancellation, đồng thời retry có kiểm soát. Các test ở đúng tầng sẽ chứng minh từng hành vi đó mà không phụ thuộc vào sự cố ngẫu nhiên ngoài mạng.

