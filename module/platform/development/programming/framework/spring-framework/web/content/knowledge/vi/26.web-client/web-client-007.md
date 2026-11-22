# WebClient: Xử lý lỗi, retry có giới hạn và tránh lặp thao tác có tác dụng phụ

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt lỗi HTTP với lỗi kết nối khi gọi dịch vụ bằng Spring WebClient; quyết định lỗi nào được thử lại; cấu hình số lần retry, backoff, jitter và timeout có giới hạn; đồng thời tránh tạo đơn hàng, thu tiền hoặc ghi dữ liệu hai lần khi một request được gửi lại. Trọng tâm là **độ an toàn của hành vi nghiệp vụ**, không chỉ là làm cho một HTTP call cuối cùng trả về thành công.

WebClient là HTTP client theo mô hình reactive, trả về Mono hoặc Flux. Pipeline chỉ thực sự chạy khi có subscriber (hoặc khi block trong ứng dụng console). **retryWhen đăng ký lại (resubscribe) upstream khi có tín hiệu lỗi**: nếu upstream chứa thao tác HTTP, request có thể được gửi lại. Vì vậy, retry là một quyết định nghiệp vụ có tác động đến hệ thống bên ngoài.

## 1. Hiểu đúng các nhóm lỗi

Với cách gọi phổ biến **retrieve().bodyToMono(...)**, Spring mặc định biến HTTP 4xx/5xx thành WebClientResponseException, có thông tin status, headers và response body. Lỗi khi chưa nhận được một HTTP response đầy đủ, chẳng hạn từ kết nối, DNS hoặc TLS, thường được biểu diễn qua WebClientRequestException. Lỗi parse JSON, xử lý dữ liệu hoặc lỗi do code ứng dụng ném ra là những nhóm lỗi khác; không nên tự động retry chỉ vì chúng cũng đi theo nhánh onError.

| Trường hợp | Ý nghĩa điển hình | Cách xử lý đề xuất |
| --- | --- | --- |
| 200/201/204 | Thành công; 204 thường không có body | Đọc body đúng kiểu; xử lý Mono.empty nếu phù hợp |
| 400/422 | Dữ liệu request sai hoặc không hợp lệ | Sửa input, trả lỗi nghiệp vụ; thường không retry |
| 401/403 | Thiếu xác thực hoặc không có quyền | Xử lý auth/quyền theo hợp đồng; không retry vô điều kiện |
| 404 | Không tìm thấy tài nguyên | Chuyển thành lỗi nghiệp vụ hoặc giá trị rỗng theo yêu cầu |
| 409/412 | Xung đột phiên bản/trạng thái | Giải quyết xung đột, kiểm tra điều kiện ghi; không retry mù |
| 408/429 | Request timeout tại server hoặc bị giới hạn tốc độ | Có thể retry khi request an toàn; tôn trọng Retry-After nếu server cung cấp |
| 500/502/503/504 | Lỗi phía server/gateway; một số lỗi tạm thời | Chỉ retry những mã đã cho phép và khi thao tác có thể lặp an toàn |
| Mất kết nối, timeout phía client | Không biết chắc server có xử lý xong hay chưa | Đặc biệt nguy hiểm với thao tác ghi; cần hợp đồng chống trùng |

Không đánh đồng “HTTP trả 5xx” với “chắc chắn server chưa ghi gì”. Ví dụ server đã lưu đơn hàng, nhưng lỗi xảy ra lúc tạo response; client nhìn thấy 500 hoặc timeout dù tác dụng phụ đã xảy ra.

## 2. Bắt và chuyển đổi lỗi tại WebClient

**retrieve()** tiện khi chủ yếu cần response body. Nếu không tùy biến, 4xx/5xx được phát thành WebClientResponseException. Dùng **onStatus** khi cần tạo lỗi nghiệp vụ cụ thể; handler nhận ClientResponse và phải trả về Mono chứa Throwable hoặc Mono phát lỗi. Ví dụ sau là **đoạn mã tích hợp vào service**, không phải một chương trình độc lập:

~~~java
Mono<Product> findProduct(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.just(new ProductNotFoundException(id))
        )
        .bodyToMono(Product.class);
}
~~~

Trong đoạn trên, Product và ProductNotFoundException là kiểu của ứng dụng; webClient là WebClient đã cấu hình baseUrl. Khi status là 404, lỗi được chuyển thành loại riêng để caller xử lý có chủ đích. Không nên chuyển mọi lỗi thành Mono.empty vì sẽ xóa mất khác biệt giữa “không có dữ liệu” và “dịch vụ bị lỗi”.

Nếu cần đọc status/headers và lựa chọn cách giải mã body theo nhiều nhánh, dùng **exchangeToMono** hoặc **exchangeToFlux**; ví dụ:

~~~java
Mono<String> result = webClient.get()
    .uri("/health/details")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        return response.createException()
            .flatMap(Mono::error);
    });
~~~

Ở đây response lỗi được chuyển thành exception mang status/body. Việc tiêu thụ body cần được thực hiện trong hàm xử lý ClientResponse; không giữ ClientResponse để dùng sau khi publisher từ exchangeToMono hoàn tất.

Phân biệt các operator sau:
- **doOnError**: quan sát/ghi log; không nuốt hoặc phục hồi lỗi.
- **onErrorMap**: chuyển đổi lỗi; giữ nguyên nguyên nhân (cause) khi bọc exception.
- **onErrorResume**: chủ động phục hồi bằng publisher khác, chỉ nên dùng khi có fallback hợp lệ về nghiệp vụ.
- **retryWhen**: đăng ký lại upstream, có thể gửi HTTP request thêm lần nữa.
- **onErrorReturn**: thay lỗi bằng một giá trị; nguy hiểm nếu trả dữ liệu giả để che mất sự cố.

Vị trí operator cũng có ý nghĩa: doOnError đặt **trước** retryWhen thấy từng lần thử thất bại; đặt **sau** retryWhen thường chỉ thấy lỗi cuối cùng khi chính sách retry không cứu được request.

## 3. Retry có giới hạn: điều kiện, số lần và khoảng chờ

Một retry policy đủ an toàn phải trả lời bốn câu hỏi: **lỗi nào**, **phương thức/nghiệp vụ nào**, **tối đa bao nhiêu lần**, và **đợi bao lâu**. Không đặt retryWhen(Retry.indefinitely()) cho outbound HTTP trong luồng xử lý request người dùng.

Project Reactor cung cấp **Retry.backoff(maxRetries, minBackoff)**. Ví dụ maxRetries = 2 nghĩa là **một lần gọi đầu tiên + tối đa hai lần thử lại = tối đa ba HTTP request**. Backoff tăng dần giảm áp lực khi dịch vụ đang lỗi; maxBackoff chặn khoảng chờ quá lớn; jitter làm nhiều client không đồng loạt retry đúng cùng thời điểm. Trong ví dụ bên dưới jitter = 0 chỉ để kết quả dễ lặp lại; trong production thường nên dùng jitter khác 0.

Ví dụ logic quyết định lỗi có thể retry cho một request **GET chỉ đọc**:

~~~java
static boolean isTransientHttpFailure(Throwable error) {
    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();
        return status == 408 || status == 429 ||
               status == 502 || status == 503 || status == 504;
    }
    return error instanceof WebClientRequestException;
}
~~~

Đây là **chính sách minh họa**, không phải danh sách retry mặc định cho mọi API. Có API trả 500 cho lỗi tạm thời, API khác có 500 sau khi ghi thành công; việc có đưa 500 vào filter phải dựa vào hợp đồng của dịch vụ. Với 429/503 kèm Retry-After, retry backoff cơ bản **không tự động làm đúng theo header này**; cần logic đọc header và điều chỉnh lịch thử lại theo chính sách server nếu API yêu cầu.

Mẫu áp dụng:

~~~java
Retry policy = Retry.backoff(2, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(MyClient::isTransientHttpFailure)
    .doBeforeRetry(signal ->
        logger.warn("Retry #{} do {}",
            signal.totalRetries() + 1,
            signal.failure().toString()))
    .onRetryExhaustedThrow((spec, signal) -> signal.failure());

Mono<String> body = webClient.get()
    .uri("/catalog/{id}", id)
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(policy);
~~~

Đây cũng là đoạn tích hợp: MyClient, logger, webClient và id thuộc lớp ứng dụng. **onRetryExhaustedThrow** ở đây trả lỗi HTTP/cuối cùng thay vì lớp lỗi “retry exhausted”, giúp tầng trên phân loại lỗi gốc. Chỉ log số lần thử, loại lỗi, request/correlation ID và thời gian; tránh log token, mật khẩu, dữ liệu cá nhân hoặc toàn bộ body nhạy cảm. Retry.backoff không giới hạn tổng thời gian nghiệp vụ nếu không kết hợp timeout/budget ở tầng phù hợp.

### Timeout và tổng ngân sách

- **Timeout từng lần thử**: dùng timeout ở HTTP connector (ví dụ Reactor Netty HttpClient.responseTimeout) hoặc một timeout operator được đặt trước retryWhen, có đánh giá rõ về loại lỗi phát ra.
- **Timeout toàn chuỗi**: đặt timeout sau retryWhen để giới hạn tổng thời gian bao gồm các lần thử và backoff.
- **TimeoutException** từ Mono.timeout không tự động khớp filter chỉ nhận WebClientRequestException/WebClientResponseException; muốn retry nó phải quyết định bổ sung một cách tường minh.
- Dù client timeout, request trước đó **có thể vẫn chạy ở server**. Timeout không phải lệnh rollback.
- Cấu hình phải thỏa ngân sách của caller: một API cần phản hồi trong 2 giây không nên có ba lần timeout 2 giây cộng nhiều giây backoff.

## 4. Ví dụ đầy đủ: GET lỗi 503 hai lần rồi thành công

Ví dụ Java 17+ sau khởi động một HTTP server nhỏ trong cùng JVM để chủ động trả 503 cho hai request đầu tiên, rồi trả 200. WebClient gọi GET và dùng retry có giới hạn. Server JDK này chỉ phục vụ demo; không có thao tác ghi. Ví dụ dùng Spring WebFlux và Reactor Netty do dependency spring-boot-starter-webflux cung cấp.

Đặt các tệp trong thư mục:

~~~text
webclient-retry-demo/
├── pom.xml
└── src/main/java/demo/WebClientRetryDemo.java
~~~

Tệp **pom.xml** (bản Spring Boot 3.3.13 được ghim để có thể tái hiện ví dụ; khi làm dự án thật hãy chọn nhánh còn được hỗ trợ):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webclient-retry-demo</artifactId>
    <version>1.0.0</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/demo/WebClientRetryDemo.java**:

~~~java
package demo;

import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.util.retry.Retry;

public final class WebClientRetryDemo {
    private WebClientRetryDemo() {}

    public static void main(String[] args) throws Exception {
        AtomicInteger hits = new AtomicInteger();
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/items/42", exchange -> {
            int attempt = hits.incrementAndGet();
            int status = attempt <= 2 ? 503 : 200;
            String response = status == 503 ? "temporarily unavailable" : "item-42";
            byte[] bytes = response.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream stream = exchange.getResponseBody()) {
                stream.write(bytes);
            }
        });
        server.start();

        try {
            int port = server.getAddress().getPort();
            WebClient client = WebClient.builder()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

            Retry boundedRetry = Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(300))
                .jitter(0.0) // Chỉ để demo có thời gian chờ xác định.
                .filter(WebClientRetryDemo::canRetryGet)
                .onRetryExhaustedThrow((spec, signal) -> signal.failure());

            String item = client.get()
                .uri("/items/42")
                .retrieve()
                .bodyToMono(String.class)
                .retryWhen(boundedRetry)
                .block(Duration.ofSeconds(5)); // Chỉ dùng ở demo console.

            System.out.println("Kết quả: " + item);
            System.out.println("Số request: " + hits.get());
        } finally {
            server.stop(0);
        }
    }

    private static boolean canRetryGet(Throwable error) {
        if (error instanceof WebClientResponseException response) {
            int code = response.getStatusCode().value();
            return code == 429 || code == 502 ||
                   code == 503 || code == 504;
        }
        return error instanceof WebClientRequestException;
    }
}
~~~

Cài JDK 17+ và Maven, sau đó đứng trong thư mục webclient-retry-demo chạy:

~~~bash
mvn -q compile
mvn -q exec:java -Dexec.mainClass=demo.WebClientRetryDemo
~~~

Hai dòng do chương trình chủ động in ra là:

~~~text
Kết quả: item-42
Số request: 3
~~~

Maven hoặc thư viện có thể in thêm log tùy môi trường. Server trả 503 ở lượt 1 và 2, hai lỗi này nằm trong filter nên Reactor resubscribe hai lần; request thứ 3 nhận 200. **Không có lượt thứ 4** vì maxRetries = 2. Đổi điều kiện server thành attempt <= 3 để thử nhánh hết retry: lỗi 503 cuối cùng sẽ đi ra ngoài, code không in hai dòng thành công. Đổi status thành 400 để thấy filter từ chối retry ngay lần đầu.

Trong ứng dụng Spring WebFlux, **không gọi block() trên luồng xử lý reactive/event loop**. Service/controller nên trả Mono/Flux để framework subscribe. block() ở đây chỉ nhằm quan sát kết quả đồng bộ từ hàm main.

## 5. Tránh lặp thao tác có tác dụng phụ

### 5.1. HTTP method và tính idempotent

**Idempotent** có nghĩa là gửi cùng một thao tác nhiều lần có **tác động cuối cùng mong muốn lên trạng thái server tương đương gửi một lần**. Nó không đồng nghĩa “chỉ có một HTTP request”, “không ghi log nhiều lần”, hoặc “response lần nào cũng giống nhau”.

| Method | Tính chất theo ý nghĩa HTTP | Quyết định retry |
| --- | --- | --- |
| GET/HEAD | An toàn (read-only) và idempotent theo hợp đồng HTTP | Thường phù hợp retry lỗi tạm thời nếu hệ thống thực hiện đúng |
| PUT | Idempotent nếu cùng URI và cùng trạng thái đích | Có thể retry khi API thực sự giữ hợp đồng đó |
| DELETE | Idempotent về hiệu ứng xóa; lượt sau có thể trả 404 | Cần coi 404/204 theo hợp đồng để tránh báo lỗi giả |
| POST | Không mặc nhiên idempotent | Không tự động retry thao tác ghi nếu chưa có cơ chế chống trùng |
| PATCH | Không mặc nhiên idempotent | Phụ thuộc ý nghĩa patch và điều kiện cập nhật |

Ngay cả GET cũng không “an toàn” trong một hệ thống viết sai hợp đồng (ví dụ GET lại thu tiền); hãy xác nhận contract thực tế. PUT như “đặt số lượng về 5” khác POST như “tăng số lượng thêm 5”. Cùng một request POST gửi ba lần có thể tạo ba đơn hàng.

### 5.2. Cửa sổ lỗi nguy hiểm

Ví dụ client gửi **POST /orders** tạo đơn:
1. Server nhận POST, lưu đơn #123 và commit transaction.
2. Mạng đứt trước khi response 201 về tới client.
3. WebClient nhìn thấy request exception/timeout, không biết server đã commit.
4. retryWhen gửi lại POST. Nếu server thiếu cơ chế chống trùng, có thể tạo thêm đơn #124.

Việc bắt WebClientRequestException và retry không giải quyết được tính không chắc chắn ở bước 3. **Không thể kết luận “request chưa tới server” chỉ từ lỗi client**.

### 5.3. Idempotency-Key phải được server thực thi

Một cách thường dùng cho POST tạo tài nguyên/thanh toán là sinh **một key duy nhất cho một thao tác nghiệp vụ** và tái sử dụng **chính key đó qua mọi lần retry**. Ví dụ phần client (mã minh họa tích hợp):

~~~java
String operationKey = /* ID ổn định của một yêu cầu tạo đơn */;
Mono<OrderResponse> request = webClient.post()
    .uri("/orders")
    .header("Idempotency-Key", operationKey)
    .bodyValue(command)
    .retrieve()
    .bodyToMono(OrderResponse.class);

// Chỉ cấu hình retry khi server đã cam kết xử lý idempotency key
// và các lỗi được phân loại là tạm thời.
~~~

OrderResponse, command và operationKey là các giá trị thuộc ứng dụng; snippet không phải chương trình độc lập. Không sinh UUID mới **bên trong** Mono.defer hoặc ngay tại từng lần retry; làm thế các lần gửi có key khác nhau, phá hỏng cơ chế chống trùng. Ngược lại, key cũng không nên dùng lại cho **hai thao tác nghiệp vụ độc lập**.

Một phía server thực thi idempotency đúng cần đảm bảo:
- Lưu khóa theo phạm vi phù hợp, thường là tenant/user + endpoint/operation + key, cùng dấu vân tay (fingerprint) của request; cùng key nhưng khác nội dung phải báo xung đột, không âm thầm thực hiện thao tác mới.
- **Kiểm tra/giành quyền xử lý key và ghi kết quả nghiệp vụ một cách atomic** (ví dụ transaction/unique constraint hoặc cơ chế tương đương). Chỉ kiểm tra “key chưa tồn tại” rồi mới insert mà không khóa có thể race giữa hai request đồng thời.
- Nếu cùng key và cùng payload được gửi lại sau khi thao tác hoàn tất, trả về kết quả đã lưu hoặc trạng thái phù hợp theo contract, thay vì chạy tác dụng phụ lần nữa.
- Xác định xử lý request đang chạy, kết quả thất bại, TTL/lưu trữ, quyền truy cập và hồi phục sau crash. TTL hết hạn có thể cho phép thực hiện lại, nên vòng đời key phải khớp yêu cầu nghiệp vụ.
- Với hệ thống phát sự kiện hoặc gọi dịch vụ khác, transaction database một mình không đủ để ngăn gửi message hai lần; cân nhắc transactional outbox, unique operation ID và consumer idempotent.

Idempotency-Key **không tự có hiệu lực chỉ vì client gắn header**; server phải hỗ trợ và tài liệu hóa hợp đồng. Nếu server không hỗ trợ, cách an toàn có thể là **không retry thao tác ghi**; thay vào đó hỏi trạng thái bằng operation ID hoặc dùng API truy vấn kết quả trước khi quyết định gửi tiếp. Với thanh toán, xử lý unknown outcome theo chính sách của nhà cung cấp.

## 6. Retry ở đúng vị trí và kiểm soát tải

**Một publisher có thể được subscribe nhiều lần.** retryWhen sẽ đăng ký lại toàn bộ đoạn upstream bên trái nó, bao gồm các thao tác phát sinh khi subscribe. Tránh đặt thao tác phụ như gửi email, ghi DB hoặc phát event bên trong phần sẽ retry nếu thao tác đó không có khóa chống trùng.

~~~java
// Nguy hiểm nếu savePayment có tác dụng phụ và thiếu chống trùng:
savePayment(command)
    .then(webClient.get().uri("/receipt").retrieve().bodyToMono(String.class))
    .retryWhen(retryPolicy); // Có thể gọi lại savePayment.

// Chỉ retry phần đọc HTTP khi phù hợp:
savePayment(command)
    .then(
        webClient.get().uri("/receipt")
            .retrieve()
            .bodyToMono(String.class)
            .retryWhen(retryPolicy)
    );
~~~

Snippet chỉ diễn giải **phạm vi resubscribe**; savePayment, command, webClient và retryPolicy là thành phần giả định của ứng dụng. Việc tách phạm vi không bảo vệ thao tác savePayment nếu caller bên ngoài retry toàn bộ flow; hệ thống vẫn cần đánh giá idempotency ở mọi tầng.

Trong hệ thống thật, nhiều lớp (HTTP client, service, message consumer, gateway, job) cùng retry có thể nhân số request: ba tầng, mỗi tầng tối đa ba lượt, có thể tạo đến **27 lượt cố gắng** cho một thao tác. Thiết kế retry ở số ít tầng có chủ đích và đặt **retry budget**, giới hạn đồng thời, rate limit/circuit breaker khi cần. Backoff có jitter giúp giảm “retry storm”, nhưng không thay thế giới hạn công suất. Retry chỉ nên áp dụng lỗi **có khả năng hồi phục trong thời gian ngắn**; lỗi input hoặc bug logic cần sửa nguyên nhân.

Về quan sát vận hành, đo số attempt thực tế, tỉ lệ thành công sau retry, mã status, timeout, latency toàn chuỗi, thời gian chờ backoff và số request bị từ chối do budget. Phân biệt “người dùng thực hiện một thao tác” với “client phát ba HTTP request”. Cảnh báo nếu retry làm tải tăng trong khi tỷ lệ thành công không cải thiện.

## 7. Các lỗi triển khai thường gặp

1. **Retry tất cả exception**: WebClientResponseException 400/401/404 và lỗi parse dữ liệu tiếp tục được thử lại dù request không thay đổi. Hãy dùng filter theo status và nhóm lỗi.
2. **Nhầm số lần**: Retry.backoff(3, ...) cho tối đa ba lần retry **sau** lần đầu, tức tối đa bốn attempt, chứ không phải tổng cộng ba.
3. **Retry mọi POST**: response mất không chứng minh server chưa ghi. Cần Idempotency-Key có hợp đồng server, điều kiện ghi, hoặc cơ chế truy vấn trạng thái.
4. **Tạo key mới mỗi attempt**: mỗi retry bị xem là một nghiệp vụ mới. Key phải ổn định theo operation.
5. **Không có timeout/budget**: nhiều lần timeout + backoff vượt SLA của caller, tăng số request đang treo.
6. **Bỏ qua Retry-After**: client ồ ạt gọi lại API đang rate limit; cần điều chỉnh chiến lược theo giao thức dịch vụ.
7. **Nuốt lỗi bằng fallback giả**: onErrorResume trả “thành công rỗng” cho thao tác thanh toán khiến downstream hiểu sai. Fallback phải có ý nghĩa nghiệp vụ rõ ràng.
8. **Đặt retry quá rộng**: retry cả chuỗi có DB write/event emit gây lặp thao tác; thu hẹp vùng được resubscribe.
9. **Lẫn lộn request timeout với rollback**: client dừng chờ nhưng server có thể vẫn đang xử lý.
10. **Dùng block() trong reactive handler**: chặn event-loop, làm giảm thông lượng và có thể gây lỗi runtime; trả Mono/Flux thay vì block.
11. **Chỉ test đường thành công**: thiếu test status 400, 404, 429, 503, request exception, hết retry, key trùng, key khác payload và request đồng thời.

## 8. Quy trình quyết định trước khi bật retry

Hãy lần lượt xác định: (1) đây là GET chỉ đọc hay thao tác có thể đổi trạng thái; (2) nếu server xử lý thành công nhưng response mất, lần gửi thứ hai có an toàn không; (3) có idempotency key/conditional write hay contract server hỗ trợ không; (4) lỗi được phân loại cụ thể và có khả năng phục hồi không; (5) tổng số attempt, backoff, jitter và timeout có nằm trong ngân sách không; (6) có metric/log và phép thử đối với request trùng hay chưa.

**Nguyên tắc cần nhớ:** retry giúp tăng khả năng hoàn thành request trước sự cố tạm thời, nhưng **không tự tạo ra tính exactly-once cho tác dụng phụ**. Với thao tác ghi, độ an toàn phải đến từ giao thức và trạng thái server (idempotency, unique constraint, transaction/outbox/consumer deduplication), sau đó client mới quyết định retry.

## Tài liệu tham khảo

- Spring Framework Reference — WebClient retrieve và onStatus: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework Reference — exchangeToMono/exchangeToFlux: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Project Reactor API — RetryBackoffSpec, filter, jitter, maxBackoff và onRetryExhaustedThrow: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html
- HTTP Semantics — safe/idempotent methods và Retry-After: https://www.rfc-editor.org/rfc/rfc9110
