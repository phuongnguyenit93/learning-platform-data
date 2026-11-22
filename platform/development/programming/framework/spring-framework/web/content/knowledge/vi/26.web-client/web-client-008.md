# WebClient: Tiêu thụ hoặc giải phóng response body để tái sử dụng kết nối

## 1. Vì sao response body quyết định vòng đời kết nối?

Khi dùng Spring `WebClient` để gọi HTTP, việc nhận được status và headers **chưa có nghĩa là đã đọc xong phản hồi**. Response body là một luồng dữ liệu có thể chưa được nhận, giải mã hoặc bỏ đi. Nếu ứng dụng chỉ nhìn status rồi bỏ qua body, một kết nối HTTP/1.1 có thể vẫn còn dữ liệu phản hồi chưa xử lý; không thể an toàn dùng kết nối đó cho request kế tiếp.

Với connector dùng connection pool (ví dụ Reactor Netty), vòng đời thông thường của một phản hồi hữu hạn là:

1. Lấy một kết nối từ pool hoặc mở kết nối mới; gửi request.
2. Nhận response status, headers và luồng body.
3. **Đọc hết body** nếu cần nội dung, hoặc **giải phóng/discard body bằng API thích hợp** nếu không cần.
4. Hoàn tất hoặc hủy response theo quy tắc của HTTP client; nếu giao thức và server cho phép, kết nối có thể được đưa về pool để tái sử dụng.

Phải phân biệt ba khái niệm:

- **Consume:** subscribe và xử lý luồng body đến khi hoàn tất, chẳng hạn `bodyToMono(String.class)` hoặc `bodyToFlux(Item.class)`.
- **Release/discard:** xử lý/giải phóng phần body không cần dùng qua API như `ClientResponse.releaseBody()` hoặc `toBodilessEntity()`. Đây là cách đóng vòng đời phản hồi khi ứng dụng chỉ cần status/headers.
- **Reuse:** kết nối vật lý thực sự được dùng lại. Consume/release đúng là điều kiện quan trọng, **không phải cam kết** reuse: server có thể gửi `Connection: close`, kết nối có thể lỗi/hết hạn, request có thể bị cancel giữa chừng, pool có thể loại bỏ connection; HTTP/2 lại có đặc điểm multiplexing khác HTTP/1.1.

`Mono` và `Flux` là mô tả xử lý bất đồng bộ: thông thường request chưa chạy chỉ vì bạn gọi `retrieve()` hoặc tạo pipeline. Phải có subscription (ví dụ framework WebFlux subscribe khi trả publisher từ handler, hoặc `block()` trong demo ở ngoài event-loop).

## 2. Chọn API đúng để quản lý body

| Nhu cầu | Cách viết khuyến nghị | Điều cần hiểu |
| --- | --- | --- |
| Cần đối tượng hoặc văn bản của body | `retrieve().bodyToMono(T.class)` | Đọc và decode body để tạo giá trị; `Mono` hoàn tất sau quá trình nhận/giải mã theo codec. |
| Cần toàn bộ các phần tử của response dạng luồng hữu hạn | `retrieve().bodyToFlux(T.class)` và tiêu thụ đến hết | Dùng stream đúng mục đích; tránh cắt ngang tùy tiện nếu ưu tiên tái sử dụng HTTP/1.1 connection. |
| Chỉ cần status/headers, bỏ body | `retrieve().toBodilessEntity()` | Trả `ResponseEntity<Void>`; phù hợp khi không cần payload. Nhánh mặc định `retrieve()` coi 4xx/5xx là lỗi. |
| Cần tự phân nhánh theo HTTP status | `exchangeToMono(response -> ...)` hoặc `exchangeToFlux(response -> ...)` | Quyết định xử lý body bên trong callback. Spring kiểm tra và giải phóng body chưa dùng sau khi publisher callback trả về hoàn tất. |
| Trong callback đã có `ClientResponse` và chủ động bỏ body | `response.releaseBody()` | Trả `Mono<Void>`; phải **chain** vào publisher trả về, không chỉ gọi hàm rồi bỏ qua. |
| Cần status/headers và body dạng `Flux` | `retrieve().toEntityFlux(T.class)` | `ResponseEntity` chứa `Flux`: **phải subscribe/tiêu thụ Flux bên trong**, nếu không tài nguyên liên quan không được giải phóng đúng. |

API cũ `exchange()` bị deprecated từ Spring 5.3 do dễ bỏ sót bước consume/release response. Với code hiện đại, ưu tiên `retrieve()` hoặc `exchangeToMono`/`exchangeToFlux`.

Lưu ý: `bodyToMono(Void.class)` có thể dùng khi thực sự **không kỳ vọng body**. Nếu server bất ngờ gửi bytes, dùng `Void` để “bỏ qua” không đồng nghĩa với chủ động đọc hết dữ liệu để tái sử dụng HTTP/1.1 connection; connector có thể đóng kết nối. Khi response **có thể có body nhưng bạn không cần body**, `toBodilessEntity()` hoặc `releaseBody()` diễn đạt ý định rõ hơn.

## 3. Cách viết khi cần và không cần nội dung

### 3.1. Cần dữ liệu: decode body như bình thường

~~~java
WebClient client = WebClient.create("https://api.example.com");

// Mono<String> sẽ đọc/giải mã nội dung khi được subscribe.
Mono<String> payload = client.get()
        .uri("/orders/42")
        .retrieve()
        .bodyToMono(String.class);

// Ở ứng dụng WebFlux, trả payload qua reactive chain cho framework xử lý.
// Tránh gọi subscribe() thủ công trong service chỉ để "kích hoạt" request.
~~~

`retrieve()` mặc định chuyển trạng thái 4xx/5xx thành `WebClientResponseException` khi subscriber yêu cầu đọc response. Nếu cần mã lỗi và body lỗi, có thể dùng các API lỗi được cung cấp, thay vì đọc response hai lần.

### 3.2. Không cần payload: trả về response không có body

~~~java
Mono<ResponseEntity<Void>> response = client.delete()
        .uri("/orders/42")
        .retrieve()
        .toBodilessEntity();
~~~

Dù caller chỉ quan tâm mã HTTP, publisher vẫn phải được subscribe để request và cleanup thực sự diễn ra. Ở Spring WebFlux, nên trả publisher lên controller thay vì gọi `.block()` trên event-loop.

### 3.3. Muốn tự xử lý status: consume hoặc release trong callback

~~~java
Mono<String> result = client.get()
        .uri("/orders/42")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(String.class);
            }
            return response.createError();
        });
~~~

Trong ví dụ, nhánh thành công đọc body; nhánh lỗi tạo reactive error từ response. Với `exchangeToMono`/`exchangeToFlux`, nếu callback trả về publisher hoàn tất mà body chưa tiêu thụ, Spring giải phóng phần chưa dùng để tránh giữ tài nguyên. **Không đưa chính `ClientResponse` ra khỏi callback** rồi mới cố đọc body ở downstream: body không còn bảo đảm truy cập được sau khi publisher callback kết thúc.

Nếu chỉ lấy status và không cần body:

~~~java
Mono<Integer> status = client.get()
        .uri("/health")
        .exchangeToMono(response ->
                response.releaseBody()
                        .thenReturn(response.statusCode().value()));
~~~

`releaseBody()` chỉ trả về `Mono<Void>`, vì vậy mẫu sai là gọi `response.releaseBody();` rồi ngay sau đó `return Mono.just(status);`: publisher cleanup vừa tạo chưa được subscribe/chain. `thenReturn(...)` buộc công việc release trở thành một phần của chuỗi kết quả.

Nếu muốn nhánh khác nhau theo lỗi, phải chú ý khác biệt: `retrieve()` tự báo lỗi cho 4xx/5xx; `exchangeToMono()` đưa quyền quyết định cho callback. Chọn rõ policy từng nhánh.

### 3.4. Filter tự chặn response phải giải phóng nó

~~~java
ExchangeFilterFunction rejectBusy = (request, next) ->
        next.exchange(request).flatMap(response -> {
            if (response.statusCode().value() == 429) {
                return response.releaseBody()
                        .then(Mono.error(
                                new IllegalStateException("Upstream too busy")));
            }
            return Mono.just(response);
        });
~~~

Đây là đoạn mã minh họa cho filter: filter **thay response bằng lỗi** nên phải cleanup body trước khi phát lỗi. Ở nhánh `Mono.just(response)`, filter chuyển response cho các tầng phía sau tiếp tục xử lý body; không release sớm vì downstream vẫn cần nó.

## 4. Demo chạy được với Java 17 và Spring WebFlux

Ví dụ dưới tạo HTTP server nội bộ trả body có độ dài xác định. Nó minh họa ba cách khép vòng đời phản hồi, không tuyên bố đo được việc tái sử dụng kết nối.

**Điều kiện:** JDK 17+, một dự án Maven/Gradle có dependency `spring-boot-starter-webflux` (Spring Boot 3.x) hoặc đầy đủ `spring-webflux` cùng HTTP connector, rồi chạy lớp `ResponseBodyLifecycleDemo` từ IDE. Đây là một chương trình Java hoàn chỉnh trong ngữ cảnh project đã khai báo dependency; `javac` trần không đủ classpath cho Spring/Reactor.

Lưu tệp `src/main/java/ResponseBodyLifecycleDemo.java`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;

public class ResponseBodyLifecycleDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/data", exchange -> {
            byte[] body = "payload-ready".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });

        server.start();
        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            WebClient client = WebClient.create(baseUrl);

            String body = client.get()
                    .uri("/data")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5));
            System.out.println("body = " + body);

            Integer bodilessStatus = client.get()
                    .uri("/data")
                    .retrieve()
                    .toBodilessEntity()
                    .map(entity -> entity.getStatusCode().value())
                    .block(Duration.ofSeconds(5));
            System.out.println("bodiless status = " + bodilessStatus);

            Integer releasedStatus = client.get()
                    .uri("/data")
                    .exchangeToMono(response ->
                            response.releaseBody().thenReturn(
                                    response.statusCode().value()))
                    .block(Duration.ofSeconds(5));
            System.out.println("released status = " + releasedStatus);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Output kỳ vọng khi ba request đều thành công:

~~~text
body = payload-ready
bodiless status = 200
released status = 200
~~~

Giải thích:

- Request 1 cần body nên `bodyToMono(String.class)` đọc và decode `payload-ready`.
- Request 2 không cần body nên `toBodilessEntity()` trả status và headers mà không cấp payload cho caller.
- Request 3 dùng `exchangeToMono` để lấy status và chain `releaseBody()`.
- `block(Duration...)` chỉ phục vụ `main` đồng bộ trong demo; không dùng `block()` trong controller/service đang chạy trên Reactor event-loop.
- Server đặt cổng `0` để hệ điều hành chọn cổng trống. Kết quả kiểm tra **cách xử lý response**, chưa chứng minh một TCP socket được reuse; muốn khẳng định reuse phải quan sát pool và connection/channel identifiers.

## 5. Tình huống dễ sai và hậu quả

### Chỉ đọc headers/status rồi bỏ response

Code cũ có thể gọi `exchange()`, kiểm tra status và return một giá trị khác mà không động tới body. Khi đó stream phản hồi chưa được xử lý có thể giữ tài nguyên và gây pool exhaustion dưới tải. Đổi sang `exchangeToMono(...)`, dùng `retrieve().toBodilessEntity()` hoặc chain `releaseBody()` trong nhánh chủ động bỏ payload.

### Trả `Flux` nhưng không ai subscribe

Với `toEntityFlux(...)`, response entity chứa một `Flux` chưa chắc đã được đọc. Nếu chỉ lấy status từ `ResponseEntity` rồi lãng quên Flux, tài nguyên liên quan có thể chưa được giải phóng. Hãy tiêu thụ Flux hoặc chọn `toBodilessEntity()` nếu thực sự không cần nội dung.

### Dừng giữa stream bằng `take(1)`, `next()`, timeout hoặc cancellation

Một chuỗi body bị cancel trước khi đọc hết không giống trường hợp consume thành công đến EOF. Framework/connector cần cleanup tài nguyên; với HTTP/1.1, nó có thể phải hủy/đóng connection thay vì đưa connection còn bytes về pool. **Cancel không đồng nghĩa memory leak**, nhưng cũng không nên kỳ vọng socket được reuse. Với stream vô hạn (SSE), kết nối có thể bị giữ cho đến khi người dùng ngắt và cleanup theo đường hủy.

### Chạm tới `DataBuffer` thấp tầng mà không release

`bodyToFlux(DataBuffer.class)` trao buffer cho code của bạn. Với pooled buffer, nếu giữ hoặc loại bỏ buffer sai cách sẽ có nguy cơ leak bộ nhớ native, **khác** với khái niệm kết nối TCP chưa trở về pool. Khi tự xử lý buffer, hãy đọc xong rồi `DataBufferUtils.release(buffer)` trong `finally`, và xem xét `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` nếu operator có thể loại bỏ buffer do filter, error hoặc cancel. Với codec chuẩn chuyển thẳng sang POJO/String, framework thường quản lý buffer giúp bạn; đừng release lại buffer đã được framework sở hữu/giải phóng.

### Nhầm lỗi 4xx/5xx với body không cần xử lý

`retrieve()` có xử lý lỗi mặc định, còn `exchangeToMono()` yêu cầu bạn tự phân nhánh. Khi dùng `onStatus` hay filter để đọc thông báo lỗi, không được lấy body hai lần; muốn đưa thông tin lỗi vào exception thì tiêu thụ body trong đường xử lý lỗi. Không tạo một publisher release rồi bỏ quên nó.

## 6. Quan sát thực tế khi connection pool có vấn đề

Khi thấy nhiều request chờ acquire connection, timeout bất thường hoặc số kết nối active tăng mà không giảm:

1. Kiểm tra mọi code path: thành công, 4xx/5xx, retry, timeout, cancel, filter, nhánh chỉ đọc headers. Hỏi rõ: body đã được tiêu thụ đến hết hoặc được release theo API chưa?
2. Phân biệt stream dài hợp lệ với connection bị mắc kẹt. SSE và response streaming có thể chiếm connection trong thời gian dài.
3. Đọc metrics của Reactor Netty connection provider (active/idle/pending, nếu đã bật metrics), log thời điểm request bắt đầu/kết thúc và log debug có kiểm soát. Dựa vào **channel/connection id** thực tế nếu cần xác nhận reuse.
4. Dùng một server test HTTP/1.1 giữ kết nối sống để thử tải tuần tự và đồng thời; so sánh phản hồi có body hữu hạn được đọc hết với trường hợp hủy sớm. Không suy ra kết luận chỉ từ ba status 200.
5. Rà soát nguyên nhân khác: pool quá nhỏ, timeout, server `Connection: close`, proxy, lỗi mạng hoặc server chậm. Tăng pool size không chữa được luồng body bị bỏ quên.

**Quy tắc ra quyết định:** cần payload thì decode và tiêu thụ; không cần payload thì dùng `toBodilessEntity()` hoặc chain `releaseBody()`; khi tùy biến status, giữ toàn bộ xử lý body trong callback `exchangeToMono`/`exchangeToFlux`. Hoàn tất vòng đời response giúp pool hoạt động đúng, còn reuse thực tế tùy transport và server.

## 7. Tài liệu gốc

- Spring Framework, WebClient — Exchange: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework, WebClient — retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework, Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework, ClientResponse JavaDoc (releaseBody, toBodilessEntity): https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/reactive/function/client/support/ClientResponseWrapper.html
- Spring Framework, ResponseSpec JavaDoc (toEntityFlux): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html
