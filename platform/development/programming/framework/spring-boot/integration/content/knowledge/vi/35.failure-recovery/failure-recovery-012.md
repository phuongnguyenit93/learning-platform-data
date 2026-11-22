# Kiểm thử phục hồi khi kết nối khôi phục hoặc hệ thống bị quá tải

Một luồng tích hợp Spring Boot có thể vượt qua mọi bài test khi HTTP API, cơ sở dữ liệu và broker đều ổn định, nhưng vẫn đánh mất dữ liệu khi kết nối chập chờn hoặc khi hệ thống phục hồi sau vài phút gián đoạn. Ví dụ: người dùng đặt hàng, ứng dụng ghi đơn vào database và gửi sự kiện sang broker; broker ngắt kết nối, các lần gửi bị retry; khi broker hoạt động lại, hàng nghìn ứng dụng cùng gửi lại, gây quá tải. Dù log đã xuất hiện dòng **connection established**, một số sự kiện vẫn bị mất, xử lý trùng hoặc mắc kẹt trong hàng chờ.

Bài học thuộc chương **Phục hồi khi lỗi** của mô-đun **SPRING_BOOT_INTEGRATION**. Mô-đun tổ chức tích hợp HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration, tập trung vào cấu hình, hợp đồng dữ liệu, giao dịch, xử lý lỗi, trùng lặp, kiểm thử và quan sát. Vì vậy, **kiểm thử phục hồi** phải chứng minh không chỉ kết nối được thiết lập lại, mà cả tiến độ nghiệp vụ, tính toàn vẹn dữ liệu và khả năng chịu tải sau khi hệ thống ổn định.

## 1. Hiểu đúng hai tình huống phải kiểm thử

**Khôi phục kết nối** là quá trình ứng dụng nhận biết kết nối hoặc dịch vụ phụ thuộc đã trở lại và có thể thực hiện yêu cầu mới. Nó bao gồm việc tái tạo connection, lấy connection hợp lệ từ pool, refresh metadata hoặc session, và xác định công việc nào cần tiếp tục.

**Phục hồi nghiệp vụ** là việc các yêu cầu đã được chấp nhận trước/during outage được hoàn tất, đưa vào trạng thái lỗi cuối cùng minh bạch, hoặc chuyển đến hàng chờ để xử lý tiếp theo chính sách. Đây là yêu cầu mạnh hơn việc chỉ “ping thành công”.

**Quá tải (overload)** xuất hiện khi lưu lượng vào vượt năng lực xử lý tại một ranh giới: thread pool, connection pool, API đối tác, DB, consumer, broker hoặc bộ nhớ hàng đợi. Quá tải có thể xảy ra khi hệ thống bình thường hoặc **ngay sau khi kết nối phục hồi**, do backlog tích tụ và hàng loạt retry đồng thời.

Phân biệt các dạng lỗi:

| Trạng thái | Ví dụ | Điều phải chứng minh khi test |
| --- | --- | --- |
| **Mất kết nối hoàn toàn** | DNS sai, TCP reset, broker không truy cập được | Lỗi được nhận diện, timeout hữu hạn, không treo vô thời hạn |
| **Kết nối chập chờn** | 10 yêu cầu có 3 lần mất kết nối | Retry có giới hạn, không gây side effect nhân đôi |
| **Kết nối phục hồi** | HTTP đối tác trả lại 200 hoặc broker lên lại | Request mới và backlog được xử lý đúng; không cần restart thủ công nếu thiết kế yêu cầu tự phục hồi |
| **Quá tải phía đối tác** | HTTP 429/503, response chậm, giới hạn concurrency | Backoff, `Retry-After` (nếu có), rate limit/circuit breaker phù hợp |
| **Quá tải phía ứng dụng** | Queue đầy, pool cạn, CPU tăng, executor reject | Backpressure/load shedding có kiểm soát, không dùng queue vô hạn |
| **Phục hồi đồng loạt** | Nhiều replica cùng reconnect/retry | Không có retry storm, số tác vụ hoàn tất tăng ổn định |
| **Thành công không rõ ràng** | Client timeout sau khi phía đối tác đã ghi xong | Có idempotency key hoặc bước đối chiếu để tránh thao tác trùng |

**Một HTTP 200 sau outage chưa đủ để đánh giá PASS.** Bài test cần đối soát công việc đã nhận, số việc hoàn tất, việc thất bại cuối cùng, bản ghi còn đợi và tác động được tạo ở hệ thống đích.

## 2. Mô hình vòng đời phục hồi

~~~mermaid
stateDiagram-v2
    [*] --> Healthy
    Healthy --> Degraded: Timeout, lỗi kết nối, 429/503, latency tăng
    Degraded --> Protected: Circuit mở / queue đạt giới hạn
    Protected --> Recovering: Downstream bắt đầu đáp ứng / probe thành công
    Degraded --> Recovering: Sự cố ngắn kết thúc
    Recovering --> Healthy: Health ổn + backlog thu hẹp + SLO đáp ứng
    Recovering --> Degraded: Thất bại lại / tải tăng
    Protected --> Protected: Shed load / delay retry trong giới hạn
~~~

Tại mỗi pha, bài test nên quan sát **dấu hiệu tiến triển**, không suy đoán từ thời gian chờ cố định:

| Pha | Kỳ vọng hệ thống | Tín hiệu quan sát |
| --- | --- | --- |
| **Healthy** | Xử lý trong SLA khi phụ thuộc ổn định | Success rate, p95/p99 latency, backlog thấp |
| **Degraded** | Lỗi được báo đúng loại; không giữ thread vô hạn | Timeout/error count, retry attempt, pool occupancy |
| **Protected** | Giữ ổn định bằng giới hạn tải và cơ chế từ chối có kiểm soát | Circuit breaker state, pending queue, rejected requests |
| **Recovering** | Thử lại có điều tiết; connection/pool mới hoạt động; backlog giảm | Successful probe, throughput, queue age, retry counts |
| **Healthy lần nữa** | Tất cả công việc đã chấp nhận được đối soát đúng | End-to-end completion, duplicate side effects, SLA sau phục hồi |

Hai lỗi phổ biến trong thiết kế test:

1. Thấy dependency trả 200 là đánh dấu **phục hồi xong**, dù outbox còn hàng nghìn message `PENDING`.
2. Thấy retry kết thúc thành công là đánh dấu **không mất dữ liệu**, dù cùng một lệnh thanh toán đã được gửi hai lần.

Đối với thao tác có side effect, cần tách ba mốc: **đã chấp nhận yêu cầu**, **đã ghi nhận bền vững ý định xử lý**, và **đã hoàn tất ở hệ thống đích**.

## 3. Xác định bất biến và tiêu chí nghiệm thu trước khi gây lỗi

Bộ test đáng tin cậy phải có **bất biến (invariants)** để xác minh trong và sau sự cố. Ví dụ một luồng nhận `OrderCreated`, ghi outbox rồi đồng bộ đơn đến API kho:

- **Không mất ý định đã chấp nhận**: mọi `eventId` được xác nhận nhận vào phải có trạng thái bền vững có thể đối soát.
- **Không tạo tác động trùng ngoài chính sách**: xử lý lại một `eventId` không tạo hai lần trừ kho, hai đơn hoặc hai thông báo.
- **Lỗi hữu hạn**: một yêu cầu bị lỗi phải có timeout và tổng ngân sách retry, không chiếm thread/connection mãi.
- **Backlog có giới hạn**: queue nội bộ phải có capacity rõ; khi đầy, hệ thống từ chối hoặc làm chậm producer theo chính sách.
- **Phục hồi có thể quan sát**: khi dependency ổn định, backlog giảm và các trạng thái lỗi còn lại có nguyên nhân rõ.
- **Đúng thứ tự khi hợp đồng yêu cầu**: với cùng `orderId`, sự kiện cập nhật sau không được ghi đè trạng thái mới bằng dữ liệu cũ.
- **Lỗi cuối cùng có nơi nhận**: record không thể xử lý được đưa vào DLT, quarantine hoặc trạng thái thất bại để xử lý thủ công, không biến mất âm thầm.

Một cách đối soát minh họa:

~~~text
accepted_count
  = succeeded_count
  + terminal_failure_count
  + outstanding_count
~~~

Phương trình này chỉ có giá trị khi mỗi **ID nghiệp vụ duy nhất** được tính đúng một trạng thái, thay vì cộng số lần thử xử lý. Những trạng thái đang xử lý phải thuộc `outstanding_count`; các thao tác đã chạy ở đối tác nhưng chưa được xác nhận cần bước reconciliation.

Các chỉ số để đặt điều kiện PASS/FAIL nên lấy từ SLA thực tế:

| Chỉ tiêu | Ví dụ tiêu chí thử nghiệm | Ý nghĩa |
| --- | --- | --- |
| **Time to detect** | Nhận biết dependency lỗi trong vài giây theo timeout cấu hình | Không treo vô thời hạn |
| **Time to resume** | Từ khi dependency sẵn sàng đến request mới thành công trong giới hạn đã thỏa thuận | Đo khôi phục kết nối |
| **Time to drain** | Backlog có thể xử lý hết trong ngưỡng SLO sau khi nguồn ổn định | Đo khôi phục nghiệp vụ |
| **Duplicate side effects** | Bằng **0** theo khóa idempotency được kiểm thử | Bảo vệ tính đúng dữ liệu |
| **Accepted but unaccounted** | Bằng **0** | Không mất trạng thái công việc |
| **Max queue / active threads / connections** | Không vượt capacity cấu hình ngoài biên sai số đo | Không tự làm cạn tài nguyên |
| **Latency và error rate khi phục hồi** | Trở về phạm vi SLO, không oscillate giữa hồi phục/quá tải | Đánh giá ổn định |

Các ngưỡng “vài giây”, “vài phút” trong ví dụ chỉ minh họa; phải thay bằng **SLO/SLI của hệ thống**. Với thao tác không hỗ trợ idempotency từ xa, không thể khẳng định “exactly once” chỉ dựa trên retry ở client.

## 4. Chọn công cụ và lớp kiểm thử

Không một loại mock nào bao phủ mọi lỗi khôi phục. Ghép các lớp theo mục tiêu kiểm thử:

| Lớp | Công cụ phù hợp | Kiểm tra được | Giới hạn |
| --- | --- | --- | --- |
| **Unit test retry/policy** | JUnit, Mockito, đồng hồ có thể điều khiển | Backoff, số lần thử, phân loại exception, trạng thái | Không chứng minh TCP thật, connection pool hay side effect |
| **HTTP contract / adapter** | WireMock, OkHttp MockWebServer | 429/503, timeout, header, response đúng/sai, request count | Không tự mô phỏng sự cố mạng phức tạp |
| **Network fault integration** | Testcontainers + Toxiproxy | Mất và nối lại mạng, latency, bandwidth, timeout, kết nối cũ | Cần container/network và tài nguyên kiểm thử |
| **DB/broker integration** | Testcontainers PostgreSQL, Kafka/RabbitMQ, Redis | Recovery của driver/pool, transaction, ack, outbox, redelivery | Chậm hơn unit test; cần cleanup và cô lập |
| **System/load test** | k6, Gatling hoặc công cụ tải đã chọn | Saturation, retry storm, queue growth, resource exhaustion | Phải chọn workload và môi trường gần thực tế |
| **Chaos/staging** | Network shaping/failure injection có giới hạn | Tương tác nhiều replica, autoscaling, failover | Cần kịch bản an toàn và rollback rõ |

Để test có thể lặp lại, ghi rõ:

1. **Trạng thái ban đầu**: số event/record, group offset, dữ liệu DB, queue rỗng hay đang có backlog.
2. **Fault được tiêm**: kết nối bị cắt ở client/server, response 503 hay 429, độ trễ, tỉ lệ lỗi, thời gian kéo dài.
3. **Tải đầu vào**: records/giây, concurrency, kích thước payload, phân bố key và độ dài queue.
4. **Điều kiện phục hồi**: lúc proxy mở lại, server trả 200, DB sẵn sàng, broker ack được.
5. **Assertions**: thời gian, số lần thử, trạng thái cuối cùng theo ID, queue, resource, logs/metrics.
6. **Cleanup**: xóa dữ liệu test theo ID, trả lại network rule, dừng containers, tránh để group hoặc bảng tồn dư gây nhiễu.

Nếu test thuộc nhiều lớp, viết riêng kiểm thử HTTP retry nhanh trong pull request và kiểm thử mạng/tải nặng theo pipeline phù hợp. Không dùng thời gian `Thread.sleep` cố định để suy rằng recovery đã xảy ra; nên đợi **điều kiện quan sát được** với deadline.

## 5. Ma trận kịch bản phục hồi kết nối

| Kịch bản | Cách gây lỗi | Tiêu chí PASS |
| --- | --- | --- |
| **Mất TCP trước khi gửi** | Chặn kết nối tới HTTP/DB/broker | Timeout hữu hạn, lỗi được phân loại; không báo thành công giả |
| **Kết nối bị cắt trong request** | Reset connection khi đang gửi/đọc | Có thể retry an toàn hoặc đối chiếu trạng thái; không tạo side effect trùng |
| **Connection pool chứa kết nối cũ** | Cắt mạng, phục hồi rồi thực hiện request kế | Pool không tiếp tục trả connection hỏng vô hạn; có kết nối mới hoạt động |
| **HTTP 503 vài lần rồi 200** | Mock 503, 503, 200 | Retry có giới hạn, cuối cùng thành công; request count bằng số dự kiến |
| **HTTP 400/422 từ hợp đồng sai** | Mock lỗi dữ liệu vĩnh viễn | Không retry mù; lỗi giữ ngữ cảnh để sửa payload |
| **HTTP 429 có Retry-After** | Mock throttling rồi hồi phục | Tuân thủ chính sách wait/rate limit; không tăng áp lực lên đối tác |
| **DB failover** | Ngắt kết nối giữa transaction | Transaction hiện tại rollback hoặc kết quả được đối soát; transaction mới có thể chạy sau recovery |
| **Broker tạm ngừng** | Block publish/consume, sau đó mở lại | Message được bảo toàn theo cơ chế durable/ack đã chọn; redelivery có idempotency |
| **DNS/TLS/certificate đổi** | Đổi endpoint/credential theo cấu hình môi trường thử | Client nhận cấu hình hợp lệ theo cơ chế triển khai; lỗi auth/cert không bị retry vô hạn |
| **Nhiều lần flap** | Up–down–up liên tục | Backoff/circuit breaker không dao động tạo retry storm |
| **Restart ứng dụng khi backlog còn** | Kill container sau khi nhận việc | Công việc bền vững được đọc lại, commit/ack đúng, không mất ID |
| **Khôi phục trong lúc tải cao** | Nạp backlog rồi cho dependency hoạt động lại | Thoát overload có kiểm soát; queue giảm, SLO trở lại, không mất/nhân bản |

Đối với request **ghi** như tạo thanh toán, gửi đơn hàng hoặc trừ kho, lỗi timeout có thể xảy ra *sau khi đối tác đã ghi thành công*. Test cần dựng tình huống “server đã xử lý, client chỉ mất response” và xác nhận yêu cầu lặp được nhận diện bằng **idempotency key** hoặc đọc trạng thái từ hệ thống đối tác.

## 6. Ví dụ JUnit: từ HTTP 503 trở về 200

Bắt đầu với tình huống dễ xác định: **lấy tồn kho bằng HTTP GET**, một thao tác đọc không tạo side effect. Ứng dụng dùng `RestClient` (Spring Framework 6.1+, thường có trong Spring Boot 3.2+) và `Resilience4j Retry`. Test dùng **MockWebServer** đưa 503 rồi 200 để xác minh retry có giới hạn.

Gradle minh họa; chọn phiên bản tương thích với Spring Boot/JDK của dự án:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'io.github.resilience4j:resilience4j-retry:2.3.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

### 6.1. Adapter có timeout và chính sách retry

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;

import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

record Stock(String sku, int available) {}

final class StockGateway {
    private final RestClient http;
    private final Retry retry;

    StockGateway(String baseUrl) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(300))
                .build();

        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(client);
        requestFactory.setReadTimeout(Duration.ofSeconds(1));

        this.http = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .build();

        RetryConfig config = RetryConfig.custom()
                .maxAttempts(3)  // Tính cả lần gọi đầu tiên
                .waitDuration(Duration.ofMillis(20))
                .retryOnException(error ->
                        error instanceof HttpServerErrorException
                        || error instanceof ResourceAccessException)
                .build();

        this.retry = Retry.of("stock-lookup", config);
    }

    Stock get(String sku) {
        return retry.executeSupplier(() ->
                http.get()
                    .uri("/stocks/{sku}", sku)
                    .retrieve()
                    .body(Stock.class));
    }
}
~~~

**Phạm vi của ví dụ:** chỉ retry với lỗi máy chủ HTTP 5xx và lỗi truy cập tài nguyên, tối đa ba lần gọi GET. **HTTP 400/422** không được retry. **HTTP 429** cũng không nằm trong predicate: nếu muốn hỗ trợ throttling, phải thiết kế riêng theo hợp đồng, `Retry-After`, ngân sách thời gian và giới hạn tải. Không sao chép cơ chế retry GET này sang HTTP POST có side effect nếu đối tác không hỗ trợ idempotency.

`maxAttempts=3` gồm lần đầu và tối đa **hai lần thử lại**. `20 ms` chỉ làm test nhanh; production nên dùng backoff tăng dần, jitter, budget retry và giới hạn concurrency phù hợp. `RestClient`, cấu hình timeout và hành vi exception tùy loại request factory/phiên bản được chọn.

### 6.2. Test khôi phục và không retry vô hạn

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;

class StockGatewayTest {

    @Test
    void succeedsAfterDependencyRecovers() throws IOException {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(json(503, "{\"error\":\"busy\"}"));
            server.enqueue(json(200, "{\"sku\":\"SKU-1\",\"available\":7}"));
            server.start();

            Stock result = new StockGateway(server.url("/").toString())
                    .get("SKU-1");

            assertEquals("SKU-1", result.sku());
            assertEquals(7, result.available());
            assertEquals(2, server.getRequestCount());
        }
    }

    @Test
    void givesUpWhenDependencyKeepsFailing() throws IOException {
        try (MockWebServer server = new MockWebServer()) {
            for (int i = 0; i < 3; i++) {
                server.enqueue(json(503, "{\"error\":\"busy\"}"));
            }
            server.start();

            StockGateway gateway =
                    new StockGateway(server.url("/").toString());

            assertThrows(HttpServerErrorException.class,
                    () -> gateway.get("SKU-1"));
            assertEquals(3, server.getRequestCount());
        }
    }

    @Test
    void doesNotRetryPermanentClientError() throws IOException {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(json(400, "{\"error\":\"bad sku\"}"));
            server.start();

            StockGateway gateway =
                    new StockGateway(server.url("/").toString());

            assertThrows(HttpClientErrorException.class,
                    () -> gateway.get("BAD"));
            assertEquals(1, server.getRequestCount());
        }
    }

    private static MockResponse json(int status, String body) {
        return new MockResponse()
                .setResponseCode(status)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
~~~

**Ba assertions khác nhau:** phục hồi đúng (503 → 200), retry dừng đúng ngưỡng (503 mãi), và lỗi không thể tự sửa bị loại khỏi retry (400). Bài test này xác minh **chính sách HTTP**, chưa chứng minh kết nối TCP/pool tự phục hồi hay backlog được xử lý hết. Cần các test tích hợp ở những phần sau.

Khi code production ghi metrics, assert thêm **retry attempts**, last exception, trạng thái circuit breaker và correlation ID. Với test thời gian, dùng đồng hồ có thể điều khiển nếu thư viện hỗ trợ, hoặc timeout condition rõ; không yêu cầu chính xác từng mili giây trên CI.

## 7. Test mạng thật: ngắt kết nối, mở lại và kiểm tra pool

Mock 503 là lỗi ứng dụng; lỗi “đã ngắt rồi nối lại mạng” đòi hỏi test ở lớp transport. Dùng container của dependency và một proxy kiểm soát kết nối, chẳng hạn **Toxiproxy**:

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> P["Toxiproxy"]
    P --> D["PostgreSQL / Redis / Kafka / HTTP test server"]
    C["JUnit test controller"] -. "cắt / mở lại / thêm latency" .-> P
    A --> M["Actuator / Micrometer"]
    M --> C
~~~

Kịch bản mẫu:

1. Khởi động dependency thật (ví dụ PostgreSQL) và proxy trong mạng test. Trỏ URL JDBC qua **proxy**, tránh đi thẳng tới database.
2. Kiểm tra truy vấn + transaction đọc/ghi thành công khi kết nối khỏe. Ghi snapshot `accepted/succeeded/outstanding`.
3. Tiêm lỗi **cắt cả kết nối đang mở và kết nối mới**. Thực hiện vài thao tác; xác nhận timeout hữu hạn, lỗi được phân loại, giao dịch không thành công không báo commit giả.
4. Khôi phục proxy; với giới hạn thời gian rõ, đợi `SELECT 1` và một **transaction nghiệp vụ mới** thành công, không cần restart ứng dụng nếu chính sách yêu cầu tự phục hồi.
5. Đọc lại dữ liệu đã ghi, outbox và trạng thái idempotency để bảo đảm lỗi không khiến công việc biến mất hay được áp dụng hai lần.
6. Theo dõi kết nối đang hoạt động/chờ của HikariCP, số lần lấy connection thất bại, thời gian chờ và log khôi phục.

Đối với **database connection pool**, cần hiểu một transaction đã lỗi trong lúc mất kết nối thường **không tự sống lại** sau khi mạng trở lại. Mỗi đơn vị xử lý phải bắt đầu **transaction mới**; không lặp từng câu SQL riêng lẻ nếu transaction cũ đã rollback. Khi retry logic ở tầng service, tạo transaction mới cho mỗi attempt với boundary rõ, tránh giữ transaction hoặc Connection đã hỏng xuyên suốt vòng retry.

Đối với test HTTP/TCP, cũng cần cả hai kiểu lỗi:

- **Ngắt trước khi request đến server**: client chắc chắn chưa gửi được nghiệp vụ, nhưng vẫn cần kiểm tra timeout và retry.
- **Ngắt sau khi server hoàn tất nghiệp vụ, trước khi client nhận response**: kết quả không chắc chắn; retry chỉ an toàn khi có idempotency hoặc đối chiếu.

Khi thiết kế fault injection, lựa chọn **reset**, **timeout**, **latency**, **bandwidth throttling** và **connection refuse** khác nhau vì mỗi loại có thể kích hoạt một nhánh xử lý lỗi riêng. Chỉ test một loại “mất mạng” là chưa đủ cho connector dùng connection pool hoặc client long-lived.

## 8. Test quá tải: backpressure, bulkhead và retry storm

Sau khi phục hồi, giả sử hệ thống có **20.000 sự kiện tồn đọng**, đối tác chỉ xử lý ổn định **100 yêu cầu/giây**, còn 10 replica cùng retry 50 yêu cầu/giây. Tổng đầu vào 500 yêu cầu/giây có thể khiến đối tác quá tải lần nữa, ngay cả khi kết nối đã phục hồi.

~~~text
Backlog(t + Δt) ≈ backlog(t)
                   + accepted_in(Δt)
                   - completed_out(Δt)
                   - terminally_resolved(Δt)

Nếu tốc độ công việc mới + replay
  > năng lực xử lý thực tế,
thì backlog tiếp tục tăng hoặc chuyển thành quá tải.
~~~

Trong công thức, `terminally_resolved` chỉ được trừ nếu công việc được kết thúc hợp lệ theo chính sách (ví dụ vào DLT với trạng thái được đối soát), không phải bỏ qua âm thầm. Phải đo theo **ID công việc duy nhất**, không dùng số lượt gọi HTTP vì retry làm tăng số lượt gọi.

### Bảo vệ từng tài nguyên

| Cơ chế | Ngăn điều gì? | Test cần khẳng định |
| --- | --- | --- |
| **Timeout** | Thread/connection chờ vô hạn | Mỗi attempt kết thúc trong deadline; lỗi rõ nguyên nhân |
| **Retry budget + backoff + jitter** | Bão retry và tác động không kiểm soát | Số attempts và tốc độ thử lại có giới hạn |
| **Circuit breaker** | Liên tục gọi dependency đang lỗi | OPEN từ chối nhanh, HALF_OPEN thử có giới hạn, CLOSED khi đủ tín hiệu thành công |
| **Bulkhead / concurrency limit** | Một downstream làm cạn mọi worker | Pool/thread của luồng khác còn phục vụ được |
| **Rate limiter** | Vượt quota/throttling phía đối tác | Tổng tốc độ outbound không vượt ngưỡng, kể cả khi nhiều replica |
| **Bounded queue / backpressure** | Tích trữ vô hạn gây OOM và latency mất kiểm soát | Queue có capacity; từ chối/delay producer theo chính sách |
| **Load shedding** | Dùng hết tài nguyên cho các request khó có thể phục vụ | Trả 429/503 có ý nghĩa; giữ đường xử lý ưu tiên |
| **Gradual ramp-up** | Đồng loạt giải phóng toàn bộ backlog khi reconnect | Tăng concurrency/tốc độ có kiểm soát, không oscillate |

**Lưu ý circuit breaker:** chuyển sang `HALF_OPEN` sau thời gian chờ hoặc khi được kích hoạt theo cấu hình không chứng minh downstream đã khỏe. Cần kiểm tra số probe cho phép và tiêu chí đóng/mở lại. **Jitter** giúp tránh nhiều instance cùng retry trên một nhịp; exponential backoff không có jitter vẫn có thể đồng bộ lượt thử.

### Kịch bản kiểm thử tải có điều khiển

Một ví dụ workload cho môi trường staging được cô lập:

- Mức ổn định ban đầu: 50 request/giây trong giới hạn downstream đã biết.
- Gây lỗi downstream và tiếp tục nạp dữ liệu đầu vào trong một cửa sổ thử nghiệm.
- Khi backlog hình thành, cho downstream phục hồi nhưng giới hạn đầu ra 100 request/giây.
- Mở dần lưu lượng replay theo concurrency/rate limit đã cấu hình.
- Theo dõi `accepted`, `rejected`, `retried`, `succeeded`, queue depth, oldest message age, p95/p99, CPU, heap, DB pool và connection errors.

Test PASS khi hệ thống **không cạn tài nguyên**, các request bị từ chối nhận phản hồi đúng hợp đồng, các công việc đã chấp nhận được giải quyết theo trạng thái bền vững và backlog giảm theo năng lực còn lại. Con số 50/100 chỉ là ví dụ; đo capacity thực tế trước khi đặt ngưỡng.

**Chú ý phân biệt**: `rejected_count` ở HTTP gateway là số yêu cầu bị từ chối **trước khi được chấp nhận bền vững**; không nên đưa chúng vào `accepted_count`. Nếu đầu vào đã được chấp nhận rồi mới thất bại, bắt buộc giữ trạng thái xử lý lại hoặc lỗi cuối cùng.

## 9. Các ranh giới của Spring Boot cần test khi khôi phục

### 9.1. HTTP client và đối tác bên ngoài

- Kiểm tra `connect timeout`, `read/response timeout`, tổng deadline (bao gồm tất cả retry) và số connection tối đa.
- Với **HTTP 429**, xem `Retry-After` nếu đối tác công bố; với **HTTP 503**, retry có giới hạn và có jitter nếu phù hợp.
- Với POST/PUT/PATCH có side effect, dùng **idempotency key**, query trạng thái hoặc giao thức nghiệp vụ được thiết kế cho replay. Một timeout không khẳng định phía đích đã rollback.
- Nếu dùng OAuth/TLS, tách lỗi **401/403/certificate invalid** khỏi lỗi tạm thời; không retry mãi để chờ lỗi cấu hình tự biến mất.
- Ghi correlation ID, attempt, endpoint alias và duration; không log token hoặc payload nhạy cảm.

### 9.2. Database và connection pool

- Kiểm tra pool stale connection sau failover, connection acquisition timeout và transaction rollback.
- Retry **đúng đơn vị nghiệp vụ**, không chỉ retry một câu SQL sau khi transaction đã lỗi.
- Tránh retry mọi loại `DataAccessException`: unique constraint violation thường là lỗi vĩnh viễn hoặc dấu hiệu bản ghi đã có, cần reconciliation.
- Khi DB vừa phục hồi, pool reconnect đồng loạt có thể gây **connection storm**; giới hạn pool và concurrent recovery.
- Nếu ghi database rồi gửi message, test crash window giữa hai thao tác; cân nhắc **transactional outbox**.

### 9.3. Cache

- Redis/cache mất kết nối có thể làm toàn bộ request rơi xuống database, gây **cache stampede** khi phục hồi.
- Test quy tắc degrade: dữ liệu nào có thể đọc stale, dữ liệu nào bắt buộc fail closed, TTL và cache refresh.
- Dùng giới hạn concurrency/single-flight cho key nóng nếu phù hợp; không biến cache miss thành hàng nghìn query DB.
- Cache không được coi là nguồn bảo đảm idempotency bền vững nếu dữ liệu dedup có thể bị mất do TTL/eviction mà nghiệp vụ vẫn cần bảo vệ dài hơn.

### 9.4. Kafka, RabbitMQ và broker thông điệp

**Kafka**:

- Khi producer lỗi mạng, kiểm tra chính sách `acks`, retry, `delivery.timeout.ms`, idempotent producer và trường hợp kết quả publish không chắc chắn.
- Với consumer, kiểm tra committed offsets, partition reassignment, `max.poll.interval.ms`, `poll()` sau khi broker trở lại, trạng thái handler và duplicate processing.
- Không commit offset trước khi công việc bền vững/được xử lý đúng chính sách. Record đã xử lý nhưng chưa commit có thể được đọc lại.
- Khi backlog lớn, tăng `concurrency` bị giới hạn bởi số partition và năng lực downstream; queue nội bộ vô hạn không phải giải pháp.

**RabbitMQ / AMQP**:

- Kiểm tra channel/connection recovery, publisher confirms/returns và **manual ack** theo đường đi thực tế.
- Nếu consumer chết trước ack, message có thể redeliver. Side effect phải idempotent.
- Kiểm tra prefetch/concurrency để không kéo quá nhiều message chưa ack làm cạn bộ nhớ hoặc downstream.
- Test dead lettering và TTL theo cấu hình; message bị reject/requeue liên tục có thể tạo vòng lỗi nóng.

**Spring Integration**:

- Với `DirectChannel`, handler thường chạy đồng bộ trên thread của người gửi; lỗi/timeout phía downstream có thể dội ngược về caller.
- Với `ExecutorChannel` hoặc `QueueChannel`, cần kiểm tra executor/queue capacity, rejection policy và đường đi `errorChannel`. `QueueChannel` in-memory không mặc định là lưu trữ bền vững.
- Với inbound/outbound adapter hoặc poller, phải biết **ack/commit thực sự diễn ra ở đâu** và lỗi được đưa về đâu. Việc message “đã vào channel” không nhất thiết nghĩa là đã được xử lý xong.
- Nếu dùng `IdempotentReceiverInterceptor` hoặc metadata store, test vòng đời dữ liệu dedup sau restart, expiry và lỗi giữa lưu khóa dedup với side effect.

## 10. Kiểm thử xử lý trùng, outbox và các cửa sổ crash

Độ tin cậy của phục hồi thường nằm ở ranh giới giữa **transaction** và **ack/commit**. Xét luồng:

~~~mermaid
sequenceDiagram
    participant I as Inbound adapter
    participant DB as Business DB
    participant O as Outbox dispatcher
    participant P as Partner API
    I->>DB: Ghi order + outbox trong 1 transaction
    DB-->>I: Commit
    I-->>I: Ack inbound theo hợp đồng
    O->>DB: Lấy outbox PENDING
    O->>P: Gửi request với idempotency key
    P-->>O: Timeout sau khi có thể đã xử lý
    Note over O,P: Kết quả từ xa chưa chắc chắn
    O->>P: Truy vấn trạng thái hoặc retry cùng key
    P-->>O: Xác nhận kết quả duy nhất
    O->>DB: Đánh dấu outbox PROCESSED
~~~

Các cửa sổ lỗi cần dựng trong integration test:

| Cửa sổ | Rủi ro | Assertion chính |
| --- | --- | --- |
| Crash **trước** business DB commit | Yêu cầu không được ghi bền vững | Có thể nhận lại/retry; không tạo trạng thái nửa vời |
| Crash **sau** DB commit nhưng **trước** ack đầu vào | Event bị giao lại | Event ID được khử trùng, chỉ có một order/outbox |
| Broker/downstream mất ngay **trước publish** | Công việc vẫn `PENDING` | Dispatcher retry khi kết nối trở lại |
| Publish thành công nhưng không nhận ack/HTTP response | Client không biết thành công hay chưa | Retry cùng idempotency key hoặc reconciliation; không nhân đôi |
| Outbox gửi thành công nhưng **trước update status** xảy ra crash | Hàng `PENDING` được xử lý lại | Tác động phía đích không lặp nhờ khóa idempotency |
| Hệ thống hồi phục nhưng một record luôn lỗi schema | Backlog đứng ở một offset | Record được quarantine/DLT, các record khác theo chính sách vẫn tiến |
| Nhiều dispatcher cùng tranh một hàng outbox | Gửi trùng đồng thời | Lease/locking/unique business key bảo vệ |

**Transactional outbox** giải quyết vấn đề lưu ý định gửi cùng transaction với business data; nó **không tự đảm bảo exactly-once** đối với API ngoài hoặc giữa DB và broker. Cần outbox relay có retry, trạng thái, unique key, idempotency ở đích và reconciliation.

Với xử lý theo thứ tự, chỉ commit/ack tiến độ cao hơn khi mọi công việc đứng trước trong partition/key đã có kết quả phù hợp. Nếu một record cũ còn xử lý bất đồng bộ mà đã commit offset của record mới, crash có thể bỏ qua record cũ.

## 11. Viết test phục hồi có điều kiện, tránh flaky

Test có ý nghĩa khi kết quả không phụ thuộc tốc độ máy CI một cách ngẫu nhiên. Với các sự kiện bất đồng bộ, nên dùng **assert eventually** với deadline rõ:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

// Mã minh họa trong integration test: các biến được tạo bởi fixture test.
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        assertEquals(expectedCount, outboxRepository.countProcessed());
        assertEquals(0, outboxRepository.countPending());
        assertEquals(expectedCount, partnerStub.distinctBusinessKeys());
    });
~~~

Đoạn này là **mẫu assertion** để chèn vào test fixture có `outboxRepository` và `partnerStub`; không phải một class Java đầy đủ có thể chạy độc lập. Dùng `distinctBusinessKeys` để kiểm tra side effect theo **khóa nghiệp vụ duy nhất**, và thêm assert số lần side effect thực tế nếu đối tác giả lập cho phép.

Để giảm flaky test:

- Sử dụng **latch/barrier** hoặc điểm tiêm lỗi có thể điều khiển để chặn đúng trước/sau commit, thay vì `Thread.sleep(2000)` rồi hy vọng rơi vào cửa sổ cần test.
- Dùng clock có thể thay thế cho logic backoff, TTL hoặc circuit-breaker nếu thư viện cho phép; không yêu cầu trễ đúng đến mili giây.
- Gắn một `testRunId` vào event, idempotency key và bảng tạm; tránh trạng thái còn sót từ test khác.
- Đợi dấu hiệu dependency **thực sự healthy** rồi mới mở proxy, khởi chạy recovery và bắt đầu đo.
- Có deadline cho mỗi phase, không để test chờ vô hạn khi lệnh ack/commit lỗi.
- So sánh snapshot dữ liệu trước và sau phục hồi; tránh chỉ nhìn exception hoặc `isConnected=true`.
- Test retry/overload với **concurrency xác định** và tải có giới hạn; ngưỡng SLO phải phù hợp khả năng CI/staging.

Một false-positive thường thấy là `await().until(() -> httpPing() == 200)`: điều này chỉ kiểm tra khả dụng của dependency, không chứng minh outbox đã gửi xong hoặc số tiền chưa bị thu hai lần.

## 12. Quan sát, cảnh báo và điều kiện tuyên bố phục hồi

Khi kiểm thử và trong vận hành, cần có cùng bộ tín hiệu để kết luận hệ thống thực sự thoát sự cố:

| Nhóm | Chỉ số và ngữ cảnh |
| --- | --- |
| **Kết nối** | Connection error rate, timeout, pool active/idle/pending, reconnect attempts |
| **Retry/circuit** | Attempts per logical request, retry exhausted, open/half-open/closed state, rejected calls |
| **Tải và chờ** | Queue depth, oldest queued age, worker saturation, active threads, heap, CPU, request rate |
| **Độ trễ** | p95/p99 mỗi outbound call, end-to-end time từ accepted đến completed |
| **Tiến độ** | Accepted vs completed vs terminal failure vs outstanding, outbox pending age, broker consumer lag |
| **Dữ liệu** | Duplicate business effects, idempotency conflicts, outbox reconciliation failures |
| **Lỗi hợp đồng** | HTTP status, serialization/deserialization exception, DLQ/DLT, correlation ID |
| **Chất lượng phục hồi** | Time to resume, time to drain, recovery error rate, số lần quay lại degraded |

Với Spring Boot, **Actuator/Micrometer** có thể thu thập nhiều metric có sẵn như HTTP, thread pool, JDBC/HikariCP; retry, queue, outbox và idempotency thường cần metric tùy chỉnh. Tên và nhãn metric phụ thuộc phiên bản thư viện và exporter: khi tạo dashboard phải đối chiếu **định nghĩa thực** thay vì tự suy từ tên.

Nên gắn `traceId`/`correlationId`, `messageId`, `idempotencyKey` đã được che đúng cách, loại adapter, downstream alias, mã lỗi và retry attempt để lần theo một công việc. Không log mật khẩu, API key, token, nội dung thanh toán hay payload nhạy cảm nguyên vẹn.

**Tiêu chí tuyên bố hệ thống đã phục hồi** nên gồm đủ:

1. Dependency mới đã có thể phục vụ request.
2. Tỷ lệ lỗi và độ trễ quay về trong SLO ở mức tải được xác định.
3. Queue/backlog có xu hướng giảm và có thời hạn giải phóng hợp lý.
4. Mọi công việc được chấp nhận đã có trạng thái đối soát, không có ID “mất tích”.
5. Không có side effect lặp ngoài chính sách idempotency.
6. Không xuất hiện vòng lặp kết nối → retry storm → circuit mở → kết nối lại.

## 13. Bài thực hành hoàn chỉnh

Xây một ứng dụng Spring Boot mô phỏng luồng **tạo đơn hàng → outbox → HTTP kho** hoặc **tạo đơn hàng → outbox → broker → consumer**. Chuẩn bị số `eventId` duy nhất có thể đối chiếu và một endpoint trả về trạng thái theo idempotency key.

### Kịch bản A: kết nối khôi phục

1. Gửi một nhóm đơn hàng hợp lệ; xác nhận business DB và outbox commit thành công.
2. Cắt kết nối outbound qua proxy, để dispatcher gặp lỗi timeout; đo số attempts và thời gian đợi.
3. Khôi phục kết nối; xác minh request mới thành công **và** các hàng `PENDING` được xử lý lại.
4. Kiểm tra mọi ID: không mất, không duplicate side effect, outbox được chuyển trạng thái đúng.
5. Làm lại với crash ngay sau khi phía kho đã xử lý nhưng trước khi dispatcher đánh dấu `PROCESSED`.

### Kịch bản B: khôi phục trong khi quá tải

1. Dùng nhiều producer/replica tạo backlog đủ lớn để quan sát nhưng trong giới hạn staging.
2. Giữ downstream trả 429/503 hoặc áp hạn mức request/giây.
3. Quan sát retry, queue capacity, lượng request bị từ chối, circuit breaker và latency.
4. Cho downstream phục hồi ở capacity hữu hạn; xác nhận replay được **điều tiết**, không dồn mọi attempt đồng thời.
5. Đợi backlog giảm theo điều kiện deadline. So số ID đã nhận, đã xử lý, lỗi cuối cùng và còn tồn.
6. Kiểm tra CPU, heap, thread/connection pool và end-to-end latency quay về vùng cho phép.

### Kịch bản C: lỗi liên tiếp

1. Cho downstream hoạt động 10 giây, ngừng vài giây, hồi phục ngắn, lại ngừng, rồi ổn định.
2. Xác minh circuit breaker và backoff không tạo vòng lặp nóng.
3. Kiểm tra outbox/queue không vượt capacity, các tác vụ đến hạn vẫn có trạng thái rõ.
4. Khi downstream ổn định, xác nhận backlog được xử lý xong và không có record bị kẹt mãi ở trạng thái trung gian.

**Điều kiện đạt bài thực hành:** test chỉ PASS khi chứng minh được khả năng tái lập lỗi, thời gian phục hồi được đo, ngân sách retry/timeout được giữ, công việc đã chấp nhận được đối soát, side effect không trùng và hệ thống thoát overload bền vững.

## 14. Checklist đưa kiểm thử vào pipeline

- [ ] Có test phân biệt lỗi kết nối thật, HTTP 5xx, HTTP 429, lỗi hợp đồng 4xx và timeout kết quả không chắc chắn.
- [ ] Có timeout cho từng attempt và ngân sách tổng của retry; lỗi vĩnh viễn không retry mù.
- [ ] Có test khi dependency trở lại: request mới thành công, backlog giảm, công việc cũ được giải quyết.
- [ ] Có fault injection khi connection đang mở và khi server đã xử lý nhưng client chưa nhận response.
- [ ] Có giới hạn queue, concurrency, thread/connection pools và chính sách load shedding/backpressure.
- [ ] Có test retry storm sau khi nhiều replica cùng phục hồi, bao gồm backoff/jitter hoặc ramp-up.
- [ ] Có idempotency, reconciliation và test cửa sổ crash/ack/commit.
- [ ] Có kiểm thử side effect ngoài database/broker, không chỉ kiểm tra số message đã nhận.
- [ ] Có phép đo thời gian resume, drain backlog, event age, tỷ lệ lỗi, resource usage theo SLO.
- [ ] Có dữ liệu test cô lập, timeout điều kiện, cleanup và công cụ khôi phục trạng thái ban đầu.

**Kết luận:** Khôi phục kết nối là bước đầu; phục hồi thực sự cần chứng minh **dữ liệu không mất, tác động không trùng, tác vụ còn chờ được hoàn tất và hệ thống không tái quá tải**. Với Spring Boot, bộ kiểm thử mạnh phải theo dõi từ HTTP/DB/cache/broker đến transaction, ack/commit, outbox và các adapter Spring Integration, đồng thời kết hợp fault injection, tải có kiểm soát, idempotency và chỉ số nghiệp vụ có thể đối soát.
