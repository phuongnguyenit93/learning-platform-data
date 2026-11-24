# Timeout và retry trong reactive flow của Spring Integration WebFlux

## 1. Vì sao timeout và retry phải được thiết kế cùng nhau?

Một hệ thống xử lý đơn hàng nhận message từ Kafka, gửi HTTP request qua WebFlux tới API định giá, nhận kết quả rồi ghi database. Khi API phản hồi chậm hoặc tạm ngừng hoạt động, luồng tích hợp phải trả lời được ba câu hỏi:

1. **Chờ đến khi nào?** Kết nối TCP, chờ pool, nhận HTTP response và xử lý toàn bộ nghiệp vụ có những thời hạn khác nhau.
2. **Thử lại khi nào?** Có lỗi tạm thời nên retry, nhưng một yêu cầu sai dữ liệu hoặc không đủ quyền thường phải dừng.
3. **Thử lại có an toàn không?** HTTP client timeout không chứng minh server chưa xử lý request. Đối với thao tác có side effect, retry có thể tạo dữ liệu trùng.

Trong chương **Adapter WebFlux** thuộc module **SPRING_INTEGRATION_ADAPTERS**, chúng ta dùng inbound/outbound adapter, gateway, poller và `MessageChannel` để kết nối các hệ thống HTTP, file, SFTP, JMS, AMQP, Kafka và database. Timeout/retry nằm ở **nhiều ranh giới**: từ lúc nhận source message, vào channel, gọi WebClient, nhận reply đến khi ACK/commit ở hệ thống nguồn.

**Mục tiêu bài học:** phân biệt timeout ở từng tầng; xây dựng `Mono`/`Flux` có retry đúng vị trí; kết nối chính sách đó với WebFlux outbound gateway, inbound request-reply, error channel và idempotency; kiểm thử hành vi bằng Reactor `StepVerifier`.

~~~mermaid
flowchart LR
    A["Kafka / JMS / DB / Service"] --> B["Spring Integration Message"]
    B --> C["MessageChannel"]
    C --> D["WebFlux outbound gateway / WebClient"]
    D -->|"HTTP request"| E["API đối tác"]
    E -->|"HTTP response hoặc timeout"| D
    D -->|"Reply / Error"| F["Business handler / error flow"]
    F --> G["ACK / persist / DLQ"]
    D -.->|"retry khi an toàn"| E
~~~

**Điểm nền tảng:** *reactive* không có nghĩa “không bao giờ timeout” hay “retry miễn phí”. Reactor biểu diễn tín hiệu kết quả/lỗi/cancellation theo publisher; Spring Integration và hệ thống nguồn quyết định đường đi của message, transaction và ACK.

## 2. Bản đồ timeout: không có một đồng hồ duy nhất

| Loại timeout/giới hạn | Nơi áp dụng | Giải quyết vấn đề gì? | Không tự bảo đảm |
|---|---|---|---|
| `pendingAcquireTimeout` | Reactor Netty `ConnectionProvider` | Chờ một connection còn khả dụng trong pool | Kết nối TCP, HTTP response |
| `CONNECT_TIMEOUT_MILLIS` | Reactor Netty `HttpClient` | TCP connection establishment | Toàn bộ DNS/TLS, pool, server processing |
| TLS handshake timeout | SSL/TLS transport | Thời gian bắt tay bảo mật | Chờ response body hoặc nghiệp vụ |
| `responseTimeout` | Reactor Netty HTTP client | Thời gian chờ dữ liệu phản hồi ở transport | Tổng deadline gồm queue + retry + downstream |
| `timeout(Duration)` | Reactor `Mono` / `Flux` | Giới hạn thời gian chờ tín hiệu trong publisher | Tự rollback side effect ở remote |
| `requestTimeout` | Messaging gateway / channel | Chờ gửi request message vào channel phù hợp | Thời gian remote HTTP xử lý |
| `replyTimeout` | Spring Integration request-reply gateway | Chờ reply message của flow | Timeout TCP/HTTP hoặc toàn bộ thời gian stream `Flux` |
| Deadline nghiệp vụ | Toàn bộ workflow | Tổng thời gian còn chấp nhận được | Tự tồn tại nếu chưa được lập trình |
| Consumer/poller timeout | Kafka/JMS/AMQP/DB và scheduler | Hợp đồng riêng của adapter/consumer | Đồng bộ tự động với WebClient timeout |

Một request có thể phải đi qua các giai đoạn **đợi pool → DNS → TCP/TLS → gửi body → chờ response → decode → ghi database → ACK message nguồn**. Vì vậy, đặt `responseTimeout(5s)` không có nghĩa toàn bộ workflow chắc chắn xong trong 5 giây.

~~~mermaid
sequenceDiagram
    participant Flow as IntegrationFlow
    participant Pool as Connection pool
    participant Net as HTTP transport
    participant Remote as Remote API
    Flow->>Pool: Acquire
    Note over Flow,Pool: pendingAcquireTimeout
    Pool->>Net: Connection
    Note over Net: connect/TLS timeout khi tạo mới
    Net->>Remote: HTTP request
    Note over Net,Remote: responseTimeout + Reactor timeout
    alt Response hợp lệ
        Remote-->>Net: HTTP 200 JSON
        Net-->>Flow: Reply
    else Lỗi tạm thời
        Net-->>Flow: Error signal
        Note over Flow: Retry policy kiểm tra lỗi & budget
    end
~~~

**Ngân sách deadline:** nếu SLA người dùng là 8 giây, không nên cho phép ba lần gọi, mỗi lần có `responseTimeout(8s)` rồi thêm backoff không giới hạn. Cần phân biệt **timeout từng attempt** với **deadline toàn bộ thao tác**, kể cả khi retry.

## 3. Cách `timeout` vận hành trên Mono và Flux

### 3.1. Mono: chờ một kết quả hoặc kết thúc

`Mono<T>` phát tối đa một giá trị rồi hoàn tất, hoặc hoàn tất rỗng, hoặc phát lỗi. Toán tử `timeout(Duration)` phát lỗi `TimeoutException` nếu publisher không có tín hiệu phù hợp trước thời hạn.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<String> lookup = remoteLookup()
    .timeout(Duration.ofSeconds(2));
~~~

`remoteLookup()` là hàm trả publisher do ứng dụng cung cấp. Khi timeout, Reactor **cancel upstream subscription** và phát `onError` về downstream. Cancellation không chứng minh remote HTTP server hay database đã hủy/rollback công việc đang thực hiện.

Nếu upstream trả `Mono.empty()` và hoàn tất trước timeout, đó là **completion rỗng**, không phải timeout. Cần định nghĩa riêng trường hợp “không tìm thấy”:

~~~java
Mono<String> lookup = remoteLookup()
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No matching result")))
    .timeout(Duration.ofSeconds(2));
~~~

Không biến mọi `Mono.empty()` thành lỗi nếu một kết quả rỗng là hợp lệ theo hợp đồng.

### 3.2. Flux: deadline giữa những lần phát tín hiệu

`Flux<T>` có thể phát nhiều phần tử. `timeout(Duration)` dạng đơn giản của Flux kiểm soát thời gian chờ **phần tử đầu** và **khoảng thời gian giữa các phần tử tiếp theo**, chứ không mặc định là deadline tổng cho một stream dài:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<String> updates = remoteUpdates()
    .timeout(Duration.ofSeconds(10));
~~~

Nếu mỗi cập nhật đến sau 5 giây, stream có thể tiếp tục nhiều phút mà không timeout. Nếu muốn một stream **chỉ được sống tối đa 60 giây**, cần đặt thêm deadline phù hợp ở mức subscription/lifecycle, không chỉ dựa vào inactivity timeout.

Với SSE, các khoảng im lặng có thể hợp lệ; một timeout quá ngắn có thể cắt kết nối dù dịch vụ khỏe. Xem xét heartbeat, thời gian đến event đầu, inactivity timeout và giới hạn tuổi stream như bốn khái niệm khác nhau.

### 3.3. Toán tử timeout không phải time travel

Khi timeout xảy ra, nó có thể ngừng đợi hoặc hủy subscription, nhưng không:

- Hoàn tác một POST đã được remote server thực hiện.
- Thu hồi message đã gửi tới Kafka/JMS.
- Rollback giao dịch database đã commit.
- Chắc chắn ngắt được một tác vụ blocking đang chạy trong executor.

Đó là lý do retry phải đi kèm **idempotency, trạng thái delivery và quan sát lỗi**, không chỉ một toán tử Reactor.

## 4. Retry trong Reactor: resubscribe, không phải “gọi tiếp từ chỗ hỏng”

`retryWhen(...)` lắng nghe lỗi rồi **subscribe lại upstream** theo `Retry` spec. Với HTTP request, điều này có thể kích hoạt lại một HTTP exchange mới. Với `Flux` đang phát dở, những phần tử đã phát trước lỗi có thể được phát lại khi resubscribe, tùy loại publisher.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<String> result = remoteLookup()
    .retryWhen(Retry
        .backoff(2, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5));
~~~

Ở đây `backoff(2, ...)` nghĩa là tối đa **hai lần thử lại sau attempt ban đầu** (tối đa ba lượt), **không** phải tổng cộng hai lượt. `jitter` làm lệch thời điểm retry để nhiều client không đồng loạt đánh vào server sau khi dịch vụ khôi phục.

### 4.1. Chỉ retry lỗi phù hợp

| Tình huống | Retry mặc định? | Lý do |
|---|---|---|
| HTTP `400` (request sai) | **Không** | Gửi lại cùng dữ liệu thường vẫn sai |
| HTTP `401`/`403` | **Không** | Cần sửa xác thực/phân quyền, không lặp vô hạn |
| HTTP `404` | Thường **không** | Có thể là kết quả nghiệp vụ hợp lệ hoặc sai URL |
| HTTP `409` | Theo hợp đồng | Có thể là conflict có thể giải quyết, cũng có thể là lỗi vĩnh viễn |
| HTTP `429` | **Có điều kiện** | Phải tôn trọng rate limit, có thể dựa trên `Retry-After` |
| HTTP `502`/`503`/`504` | **Có điều kiện** | Thường tạm thời, nhưng vẫn phải có budget và backoff |
| Connection reset / transient network | **Có điều kiện** | Retry khi request idempotent; phân biệt TLS/certificate lỗi vĩnh viễn |
| Timeout khi POST đã gửi | **Chỉ khi an toàn** | Remote có thể đã thực thi side effect |
| JSON decode/schema lỗi | Thường **không** | Retry không sửa được dữ liệu/schema sai |

`Retry.filter(...)` giúp quy định tập lỗi được retry. Không dùng `retry()` không giới hạn ở production, và không retry mọi `Throwable` — các lỗi cấu hình, validation, TLS trust hay decoding có thể không hồi phục bằng việc lặp lại request.

### 4.2. Retry khi Flux đã phát một phần dữ liệu

Giả sử remote stream đã phát `event-1`, `event-2`, sau đó mất kết nối. Nếu dùng `retryWhen` cho toàn bộ `Flux`, subscription mới có thể phát lại `event-1` và `event-2`. Subscriber nhận trùng:

~~~text
Attempt #1: event-1 → event-2 → network error
Retry #1:   event-1 → event-2 → event-3 → complete
Subscriber: event-1, event-2, event-1, event-2, event-3
~~~

Để stream nghiệp vụ có thể resume, cần **event ID/cursor, lưu lịch sử, khử trùng lặp** và hợp đồng định vị lại vị trí đọc (ví dụ `Last-Event-ID` với SSE). `retryWhen` chỉ lặp subscription, không tự suy ra vị trí resume.

## 5. Vị trí của timeout và retry quyết định kết quả

Đây là phần dễ gây lỗi nhất khi code reactive resilience. **Thứ tự các toán tử thay đổi phạm vi timeout.**

~~~java
// A: timeout cho TỪNG ATTEMPT; mỗi retry được phép chờ lại 3 giây.
Mono<QuoteResponse> perAttempt = requestOnce()
    .timeout(Duration.ofSeconds(3))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));

// B: timeout cho TOÀN BỘ chuỗi, gồm cả attempts và backoff.
Mono<QuoteResponse> overall = requestOnce()
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)))
    .timeout(Duration.ofSeconds(8));

// C: hai lớp timeout: 3 giây/attempt và tối đa 8 giây tổng.
Mono<QuoteResponse> bounded = requestOnce()
    .timeout(Duration.ofSeconds(3))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)))
    .timeout(Duration.ofSeconds(8));
~~~

`requestOnce()` là ví dụ về một **publisher cold/repeatable** được tạo từ HTTP call. Ba đoạn mã là các **biến thể thay thế nhau**, không phải biến cần khai báo đồng thời trong cùng scope. Khi dùng lại cùng một publisher, phải chắc chắn **subscription mới thực sự kích hoạt request mới** và body có thể gửi lại; request body streaming một lần đọc có thể không repeatable.

| Đặt toán tử | Hệ quả |
|---|---|
| `timeout` **trước** `retryWhen` | Timeout có thể kích hoạt retry; mỗi attempt có đồng hồ riêng |
| `timeout` **sau** `retryWhen` | Một deadline tổng áp dụng cả chuỗi retries/backoff; hết giờ sẽ phát lỗi tới downstream |
| Kết hợp cả hai | Giới hạn từng lượt và toàn bộ thời gian; phù hợp nhiều outbound HTTP operations |
| `onErrorResume` đặt trước retry và nuốt lỗi | Retry có thể không chạy vì upstream đã thành completion/fallback |
| `onErrorResume` sau retry | Chỉ fallback khi policy retry đã hoàn tất hoặc gặp lỗi không retryable |

**Lưu ý về retry và deadline tổng:** khi `timeout(8s)` ở cuối phát lỗi, nó hủy subscription của chuỗi trước đó. Không có nghĩa server đối tác chắc chắn dừng xử lý nếu HTTP request đang chạy. Nếu API có side effect, vẫn phải lưu idempotency key và reconcile kết quả.

## 6. WebClient: phân biệt HTTP status lỗi với lỗi network

Với `WebClient.retrieve().bodyToMono(...)`, HTTP 4xx/5xx thông thường tạo `WebClientResponseException`, giúp xét status code. Lỗi kết nối/transport thường xuất hiện qua `WebClientRequestException` với nguyên nhân nằm trong cause; timeout do Reactor `timeout` phát `TimeoutException`.

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;
import java.util.concurrent.TimeoutException;

boolean shouldRetry(Throwable error) {
    if (error instanceof TimeoutException) {
        return true; // Chỉ an toàn nếu thao tác idempotent.
    }
    if (error instanceof WebClientResponseException ex) {
        int status = ex.getStatusCode().value();
        return status == 429 || status == 502
            || status == 503 || status == 504;
    }
    return false;
}
~~~

Chính sách trên **chưa** retry các lỗi network `WebClientRequestException`. Đây là lựa chọn có chủ ý cho ví dụ: trong production cần phân loại cause (`ConnectException`, reset, DNS, certificate, TLS...) và áp dụng theo hợp đồng. Đừng thêm `error instanceof WebClientRequestException` một cách mù quáng vì lỗi truststore/TLS hostname không được sửa bằng retry.

Khi cần xử lý status đặc biệt (ví dụ 404 là “không có dữ liệu” thay vì lỗi), dùng `onStatus(...)` hoặc `exchangeToMono(...)` của WebClient để ánh xạ status thành kết quả domain. **Không** trả `QuoteResponse` giả giống thành công cho mọi lỗi 5xx, vì downstream có thể ghi sai dữ liệu.

## 7. Cấu hình HTTP transport và connection pool

Lớp Reactor Netty giúp kiểm soát TCP connect, chờ response và pool acquisition. Các timeout này bổ sung cho Reactor `timeout`, không thay thế nó.

~~~java
package com.example.integration;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class ResilientWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider quoteConnectionPool() {
        return ConnectionProvider.builder("quote-http-pool")
            .maxConnections(20)
            .pendingAcquireMaxCount(40)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .maxIdleTime(Duration.ofSeconds(30))
            .build();
    }

    @Bean("quoteWebClient")
    WebClient quoteWebClient(
            WebClient.Builder builder,
            @Qualifier("quoteConnectionPool") ConnectionProvider pool) {
        HttpClient transport = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1500)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .clientConnector(new ReactorClientHttpConnector(transport))
            .build();
    }
}
~~~

Đọc cấu hình theo đúng lớp:

1. `maxConnections` giới hạn connection, **không phải request/giây**.
2. `pendingAcquireTimeout` là thời gian chờ pool cấp connection; request có thể thất bại trước khi có TCP connection.
3. `CONNECT_TIMEOUT_MILLIS` giới hạn TCP connect, không bao gồm mọi thời gian chờ ở upstream queue hoặc sau HTTP exchange.
4. `responseTimeout` điều khiển việc chờ HTTP response ở tầng transport; không phải tổng deadline có retries.
5. Pool riêng được đóng khi Spring context dừng qua `destroyMethod = "dispose"`; event loops dùng chung có vòng đời riêng.

Các thông số là **giá trị học tập**. Nếu API đối tác giới hạn 10 request đồng thời, chỉ tăng `maxConnections` lên 100 sẽ tạo quá tải. Cần theo dõi active/pending connections, độ trễ remote, response rate và số request đang thực thi.

## 8. Ví dụ hoàn chỉnh: WebClient reactive với hai lớp deadline và retry có lọc

Ví dụ này gọi API báo giá `POST /api/quotes`. Nó giả định **đối tác hỗ trợ `Idempotency-Key`** và trả cùng kết quả nếu nhận lại cùng khóa. Nếu API không hỗ trợ quy tắc đó, không được coi retry POST trong ví dụ là an toàn.

~~~java
package com.example.integration;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class PartnerQuoteClient {

    public record QuoteRequest(
        String eventId, String orderId, int weightKg) { }

    public record QuoteResponse(
        String orderId, long amountVnd, String currency) { }

    private final WebClient client;

    public PartnerQuoteClient(
            @Qualifier("quoteWebClient") WebClient client) {
        this.client = client;
    }

    public Mono<QuoteResponse> quote(QuoteRequest request) {
        // Mono.defer làm rõ một subscription mới có thể tạo HTTP exchange mới.
        return Mono.defer(() -> client.post()
                .uri("https://partner.example/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", request.eventId())
                .bodyValue(request)
                .retrieve()
                .bodyToMono(QuoteResponse.class))
            // Mỗi attempt không chờ quá 3s ở mức publisher.
            .timeout(Duration.ofSeconds(3))
            .retryWhen(Retry
                .backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(this::retryable)
                .onRetryExhaustedThrow(
                    (spec, signal) -> signal.failure()))
            // Deadline tổng tính cả attempts và backoff.
            .timeout(Duration.ofSeconds(8));
    }

    private boolean retryable(Throwable error) {
        if (error instanceof TimeoutException) {
            return true;
        }
        if (error instanceof WebClientResponseException ex) {
            int status = ex.getStatusCode().value();
            return status == 429 || status == 502
                || status == 503 || status == 504;
        }
        return false;
    }
}
~~~

**Điều nên hiểu trước khi dùng:**

- URL `https://partner.example/api/quotes` là **địa chỉ giả lập**, cần thay bằng endpoint qua cấu hình bảo vệ; không có server thực cho URL ví dụ này.
- `eventId` phải ổn định qua các attempt và lần khởi động lại; không tạo UUID mới bên trong mỗi retry.
- `Mono.defer` giữ đoạn tạo request trong ngữ cảnh subscription. Request body dạng DTO bất biến ở đây có thể gửi lại; một `Flux<DataBuffer>` đọc một lần chưa chắc repeatable.
- `timeout(3s)` ở trước retry giới hạn từng attempt; `timeout(8s)` cuối cùng là deadline tổng. `responseTimeout(3s)` của transport là một giới hạn khác, nên cần tránh cấu hình mâu thuẫn với kết quả kỳ vọng.
- `Retry.backoff(2, ...)` cho tối đa ba attempt. Sau khi hết retry, `onRetryExhaustedThrow` phát lại lỗi gốc cuối cùng để downstream dễ phân loại; không tự chuyển lỗi thành success.
- Bộ lọc không retry `400`, `401`, `403` hay lỗi decode; khi remote trả `429`, production cần xét `Retry-After` và ngân sách tổng chứ không chỉ dựa trên backoff cố định.
- `.timeout(8s)` hủy publisher khi quá hạn nhưng không bảo đảm remote đã rollback. Cần đối soát theo `eventId`.

**Hai kiểu timeout có thể cùng phát sinh:** lỗi timeout do tầng HTTP transport có thể có kiểu exception/cause khác với `java.util.concurrent.TimeoutException` của Reactor operator. Bộ lọc `retryable` phía trên chỉ là chính sách minh họa; trong thực tế phải phân loại đầy đủ lỗi transport qua log/tests trên phiên bản Reactor Netty đang dùng.

## 9. Đặt chính sách trong Spring Integration flow ở đâu?

Có **hai cách tổ chức**, không nên xem chúng là một cấu hình mặc định có thể thay thế nhau.

### 9.1. Dùng WebFlux outbound gateway

Nếu flow cần **reply message** chứa kết quả HTTP để tiếp tục xử lý, sử dụng `WebFlux.outboundGateway(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class QuoteOutboundFlow {

    public record QuoteRequest(String eventId, String orderId) { }
    public record QuoteResponse(String orderId, long feeVnd) { }

    @Bean
    IntegrationFlow quoteGateway(WebClient quoteWebClient) {
        return IntegrationFlow.from("quoteRequests")
            .handle(WebFlux.outboundGateway(
                    "https://partner.example/api/quotes",
                    quoteWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class))
            .channel("quoteResults")
            .get();
    }
}
~~~

Ở đây WebClient đã cấu hình **transport timeout** có tác dụng. Tuy nhiên, `Retry.backoff` trong `PartnerQuoteClient.quote(...)` ở mục 8 **không tự được áp dụng** cho outbound gateway này: gateway gọi WebClient trực tiếp theo cấu hình endpoint. Nếu muốn retry ở tầng Spring Integration, cần thiết kế **advice/error flow/retry phù hợp với hành vi bất đồng bộ của endpoint**, xác định loại lỗi và kiểm thử thực tế; không giả định mọi retry advice dành cho synchronous handler sẽ tự nhìn thấy lỗi phát ra sau này từ publisher.

Khi API cần reply để ghi DB hoặc route, hãy giữ hợp đồng request-reply thay vì chuyển thành fire-and-forget. Nếu phải retry bền vững qua application restart, kết hợp outbox/broker và cơ chế điều phối retry, không chỉ giữ request trong bộ nhớ.

### 9.2. Dùng reactive client như một bước xử lý không trả reply nghiệp vụ

Với nhánh chỉ cần phát lệnh, ghi trạng thái hoặc thực thi side effect có quản lý lỗi, có thể đưa `PartnerQuoteClient` vào một `ReactiveMessageHandler`. Java DSL Spring Integration 6.1+ hỗ trợ `handleReactive(...)` nhận handler trả `Mono<Void>`:

~~~java
@Bean
IntegrationFlow triggerRemoteQuotes(PartnerQuoteClient client) {
    return IntegrationFlow.from("quoteCommands")
        .handleReactive(message -> {
            PartnerQuoteClient.QuoteRequest request =
                (PartnerQuoteClient.QuoteRequest) message.getPayload();
            return client.quote(request)
                .doOnNext(response -> System.out.println(
                    "Quote received: " + response))
                .then();
        })
        .get();
}
~~~

Đây là **phương án một chiều có side effect**, không tạo reply `QuoteResponse` cho downstream. Đoạn ví dụ minh họa cách **giữ Mono trong pipeline**, không gọi `block()` hay `subscribe()` thủ công. Trong ứng dụng thực, thay log bằng thao tác persist/publish reactive có xử lý lỗi; không kết luận thao tác đã bền vững chỉ vì đã in log.

Nếu yêu cầu handler tạo **reply** để một inbound gateway trả HTTP response, chọn một endpoint/flow có hợp đồng request-reply, hoặc xây dựng cầu nối publisher/reply channel có correlation rõ ràng; không tự giả định `handleReactive(...).then()` sẽ trả payload nghiệp vụ.

## 10. Error channel, replyTimeout và bất đồng bộ

Spring Integration có thể xử lý lỗi qua `ErrorMessage`/`errorChannel`, advice hoặc nhánh lỗi của flow. Cần phân biệt **lỗi xảy ra lúc dispatch message** và **lỗi phát sinh về sau khi HTTP publisher chạy**.

| Trường hợp | Điều có thể xảy ra | Cần kiểm tra |
|---|---|---|
| Channel không chấp nhận message | `send` thất bại hoặc ném exception | Capacity, dispatcher, consumer, send timeout |
| WebClient tạo HTTP request nhưng connection refused | Reactive error sau khi publisher được subscribe | Error flow của endpoint, correlation với message nguồn |
| Remote trả `503` | HTTP status thành error signal khi dùng cơ chế đọc response mặc định | Retry policy, circuit breaker, dead-letter |
| Inbound gateway không có reply | Gateway chờ đến `replyTimeout` | ErrorOnTimeout, error channel, HTTP response mapping |
| HTTP client đóng kết nối | Cancellation có thể truyền vào reactive pipeline | Đoạn nào đã thực thi và có thể còn chạy |

**`replyTimeout`** ở inbound request-reply gateway là timeout **đợi reply message**, không thay thế HTTP transport timeout ở outbound WebClient. Nếu downstream trả một reply chứa `Flux<T>` sớm, thời gian phát của `Flux` có thể vượt reply timeout mà không có nghĩa gateway đã vi phạm thời hạn chờ reply ban đầu.

Không mặc định mọi lỗi WebClient sẽ được ném ngay tại `MessageChannel.send(...)`: đường chạy bất đồng bộ có thể phát lỗi sau khi `send` đã trả về. Cần **integration test** về lỗi network, HTTP status và vị trí error channel trên phiên bản Spring Integration thực tế.

Nếu client gọi inbound gateway cần nhận lỗi `504 Gateway Timeout`, `503 Service Unavailable` hoặc một schema lỗi riêng, phải thiết kế **HTTP error mapping** tương ứng. Một ngoại lệ `TimeoutException` trong flow không bảo đảm framework tự trả status theo cách doanh nghiệp mong muốn.

## 11. Retry, idempotency và ACK/commit nguồn message

Khi request đến từ Kafka/JMS/AMQP/file/SFTP/DB poller, việc retry HTTP ảnh hưởng đến bảo đảm delivery của **message nguồn**. Ví dụ:

~~~mermaid
sequenceDiagram
    participant Source as Kafka/JMS source
    participant App as IntegrationFlow
    participant API as Partner API
    Source->>App: order.created (eventId=e-101)
    App->>API: POST Idempotency-Key=e-101
    API->>API: Persist result
    API--xApp: Response bị mất / timeout
    Note over App: Không biết remote đã commit chưa
    App->>API: Retry POST cùng key e-101
    API-->>App: Trả kết quả đã lưu cho key e-101
    App->>Source: ACK theo hợp đồng nguồn
~~~

**Idempotency** là khả năng xử lý lại cùng thao tác mà không nhân đôi side effect. Nó cần hỗ trợ từ **bên nhận hoặc tầng nghiệp vụ**. Chỉ gắn header `Idempotency-Key` không tự tạo cơ chế khử trùng lặp nếu server đối tác không kiểm tra và lưu khóa.

Thiết kế vận hành nên xác định:

1. **Khóa ổn định:** `eventId`/`commandId` duy nhất cho một tác vụ; giữ nguyên qua HTTP retry và retry từ broker.
2. **Outcome store:** lưu request, trạng thái gửi, response hoặc reconciliation token; biết được task nào đang `PENDING`, `SUCCEEDED`, `FAILED` hay `UNKNOWN`.
3. **ACK nguồn:** nếu ACK Kafka/JMS trước khi xác nhận đủ điều kiện, có thể mất việc khi ứng dụng restart. Nếu ACK muộn, có thể xử lý trùng sau redelivery.
4. **Retry bền vững:** outbox/broker với backoff và dead-letter để xử lý cả lỗi sau crash. Reactor `retryWhen` trong RAM không tự sống qua restart.
5. **Số lần retry cộng dồn:** nếu WebClient thử 3 lần và broker redelivery 5 lần, một event có thể gây nhiều HTTP requests hơn dự tính.
6. **Manual reconciliation:** với outcome không chắc chắn, tra cứu trạng thái bên nhận theo idempotency key thay vì tiếp tục POST vô hạn.

Một số tác vụ `GET` thực sự không có side effect có thể retry đơn giản hơn, nhưng vẫn cần rate limit, timeout, request budget và tránh làm quá tải server.

## 12. Giới hạn đồng thời, backpressure và circuit breaker

Retry làm tăng số request gửi vào hệ thống đang bị lỗi. Khi 1.000 messages cùng timeout, mọi message tự retry có thể tạo **retry storm** và làm dịch vụ đối tác khó phục hồi.

| Cơ chế | Giải quyết | Không tự bảo đảm |
|---|---|---|
| `retryWhen` + backoff/jitter | Thử lại có kiểm soát sau lỗi phù hợp | Không có delivery bền vững qua restart |
| `timeout` và deadline | Giới hạn thời gian mỗi attempt hoặc toàn operation | Remote tự rollback side effect |
| `flatMap(..., concurrency)` | Giới hạn số inner publishers đang được subscribe | Không thay thế rate limit/request-per-second |
| `limitRate` / Reactive Streams demand | Điều tiết yêu cầu trong reactive chain | Broker/JDBC bên ngoài tự hiểu demand |
| Bounded queue | Giới hạn backlog ở một ranh giới | Không làm tăng năng lực xử lý remote |
| Connection pool | Giới hạn socket và thời gian acquire | Không phải throughput limit mỗi giây |
| Circuit breaker | Ngừng gọi tạm thời khi dependency lỗi liên tiếp | Không thay thế reconciliation/idempotency |
| Rate limiter | Khống chế request theo chính sách | Không tự phân loại lỗi có thể retry |

Ví dụ Reactor giới hạn độ đồng thời của các HTTP requests:

~~~java
import reactor.core.publisher.Flux;

Flux<PartnerQuoteClient.QuoteResponse> quotes =
    Flux.fromIterable(requests)
        .flatMap(client::quote, 8);
~~~

Ở đây `requests` là `Iterable<PartnerQuoteClient.QuoteRequest>`, `client` là `PartnerQuoteClient`. Tham số `8` giới hạn số inner publishers đang xử lý đồng thời; **không** đồng nghĩa 8 HTTP requests mỗi giây. Với dữ liệu cần đúng thứ tự, dùng `concatMap` hoặc ranh giới đảm bảo ordering phù hợp.

**Lưu ý:** giới hạn concurrency của từng flow không bảo đảm giới hạn **toàn ứng dụng** nếu có nhiều instances/partitions. Có thể cần rate limiter dùng chung hoặc quota từ đối tác. Retry budget và circuit breaker phải được thống nhất giữa các replicas.

## 13. Timeout/retry đối với stream Flux và SSE

Stream có thể tồn tại lâu; khái niệm “thành công” và “kết thúc” khác với JSON response đơn:

- Với `Mono<QuoteResponse>`, thành công thường là nhận một object và complete.
- Với `Flux<ShipmentEvent>`, mỗi event được phát khi đến; có thể complete sau N phần tử, lỗi giữa stream hoặc tiếp tục vô hạn.
- Với `text/event-stream`, kết nối HTTP có thể mở lâu; proxy và browser có idle timeout/reconnect riêng.
- Với `Flux` đã phát hai event rồi lỗi, `retryWhen` có thể phát lại event từ đầu. Cần event ID, cursor và khử trùng lặp.
- Nếu client ngắt SSE, cancellation có thể đến upstream; nhưng message đã ghi vào broker/DB không tự được thu hồi.

Ví dụ phân biệt idle timeout của stream:

~~~java
Flux<ShipmentEvent> liveUpdates = remoteEventStream()
    // Không nhận event nào trong 15s thì báo timeout.
    .timeout(Duration.ofSeconds(15))
    .doOnCancel(() -> log.info("Client no longer consumes stream"));
~~~

`remoteEventStream()`, `ShipmentEvent` và `log` thuộc ứng dụng thực. `timeout(15s)` ở đây không phải **tổng tuổi stream tối đa 15 giây**. Nếu stream có thể im lặng hợp lệ lâu hơn, cần heartbeat hoặc sửa chính sách. Trước khi retry một stream, hãy xác định có cách resume từ offset/event ID hay không.

## 14. Quan sát, bảo mật và vòng đời

Những chỉ số nên đo theo **từng attempt** và **từng tác vụ nghiệp vụ**, tránh đếm mọi attempt là một giao dịch hoàn tất:

- **Latency:** thời gian chờ acquire, TCP connect, TLS, response, tổng thời gian gồm retries, p50/p95/p99.
- **Retry:** số attempts, số retries, retry exhausted, thời gian backoff, lỗi cuối cùng, response `429/5xx`.
- **Pool:** active/idle/pending connections, acquire failures và connection lifetime.
- **Flow:** in-flight messages, queue length, consumer lag, ACK/commit, dead-letter, messages outcome `UNKNOWN`.
- **Stream:** số subscription, cancellation, idle timeout, reconnect, duplicate event và event lag.

Không gắn `orderId`, token hoặc toàn bộ URL có query nhạy cảm thành metric tags có cardinality lớn. Dùng trace/correlation ID cho logs có lọc thông tin và đảm bảo không lộ `Authorization` hoặc dữ liệu cá nhân.

Về bảo mật, retry không được vô tình chuyển credentials tới host khác: kiểm soát endpoint allowlist, TLS hostname verification, redirect và token refresh. Không tắt kiểm tra chứng chỉ để biến lỗi TLS thành “thành công”, và không retry một lỗi `401` liên tục thay cho quy trình refresh credential an toàn.

Về lifecycle, WebClient/connection pool nên được tái sử dụng và đóng theo Spring context. Khi shutdown, ngừng nhận công việc mới theo chính sách, ghi nhận trạng thái tác vụ chưa hoàn tất, để broker/outbox có thể tiếp tục xử lý khi restart. Đừng dựa vào một `Mono.retryWhen` đang nằm trong bộ nhớ để đảm bảo task được gửi sau restart.

## 15. Kiểm thử với StepVerifier và virtual time

Kiểm thử retry bằng đồng hồ thật vừa chậm vừa dễ flake. `reactor-test` cho phép dùng `StepVerifier.withVirtualTime(...)` để điều khiển scheduler thời gian trong pipeline reactive.

~~~groovy
// build.gradle - dependency test
testImplementation 'io.projectreactor:reactor-test'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

### 15.1. Retry hai lần rồi thành công

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryVirtualTimeTest {

    @Test
    void retriesTwiceThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> remote = Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(
                    new IllegalStateException("temporary"));
            }
            return Mono.just("ok");
        });

        StepVerifier.withVirtualTime(() ->
                remote.retryWhen(Retry
                    .backoff(2, Duration.ofSeconds(1))
                    .jitter(0.0)
                    .filter(e -> e instanceof IllegalStateException)))
            .thenAwait(Duration.ofSeconds(4))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
~~~

Với `jitter(0.0)`, backoff minh họa là khoảng 1 giây và 2 giây. Test cấp 4 giây virtual để vượt cả hai đợt. Việc `Retry.backoff(2,...)` tạo **hai retries, ba attempts** được kiểm chứng bằng `attempts.get() == 3`.

### 15.2. Timeout phát lỗi, không phải completion rỗng

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutVirtualTimeTest {

    @Test
    void timesOutBeforeSlowResponse() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }
}
~~~

Test này kiểm tra Reactor operator với publisher mô phỏng, **không** khẳng định TCP connect/HTTP response của WebClient đã được test. Để kiểm tra timeout transport và HTTP retry thực, dùng mock HTTP server điều khiển `503`, `429`, response delay, connection reset và body không hợp lệ.

### 15.3. Ma trận test tối thiểu với mock HTTP server

| Điều kiện mô phỏng | Kỳ vọng |
|---|---|
| Remote `200` trong deadline | Một success result, không retry |
| Remote `400` | Không retry, lỗi được phân loại |
| Remote `401`/`403` | Không retry vô hạn hoặc làm lộ token |
| Remote `429` rồi `200` | Retry theo budget/rate limit; cùng idempotency key |
| Remote `503` hai lần rồi `200` | Tổng ba attempts và một kết quả |
| Remote liên tục `503` | Hết retries, lỗi về error flow |
| Remote nhận POST rồi làm mất response | Retry cùng key, remote không tạo side effect trùng |
| Pool đầy/chờ acquire quá lâu | Phân biệt lỗi acquire với HTTP server timeout |
| Source message bị redelivery | Không nhân đôi nghiệp vụ dù client đã retry nội bộ |
| Flux lỗi sau hai events | Quan sát phần tử bị lặp khi resubscribe |
| Client ngắt SSE | Cleanup subscription, không suy rằng DB/broker rollback |

## 16. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`timeout(3s)` có nghĩa remote chắc chắn không xử lý nữa” | Timeout chỉ kết thúc/hủy phía subscription; side effect từ xa có thể đã diễn ra |
| “`retryWhen(Retry.backoff(2))` chỉ gửi hai lượt tổng cộng” | Một lượt ban đầu cộng tối đa hai retries |
| “Đặt `timeout` ở đâu cũng như nhau” | Trước retry là từng attempt; sau retry là deadline toàn chuỗi |
| “`Flux.timeout(10s)` cắt stream sau đúng 10 giây” | Thường giới hạn thời gian chờ phần tử đầu/tiếp theo, không phải tuổi stream |
| “HTTP `429` retry ngay sẽ nhanh hơn” | Cần backoff, có thể dùng Retry-After và rate limit |
| “`400` hay JSON decode lỗi cứ retry rồi sẽ hết” | Thường là lỗi dữ liệu/hợp đồng, phải sửa gốc |
| “`send() == true` nghĩa WebClient đã gọi thành công” | Kết quả send theo hợp đồng channel, không đồng nghĩa HTTP exchange hoàn tất |
| “WebFlux outbound gateway tự dùng chính sách retry của một service WebClient khác” | Chỉ dùng chính sách gắn đúng vào request/publisher/endpoint đang chạy |
| “Retry một POST luôn vô hại nếu request có UUID” | Phía server phải **thực thi** idempotency theo key |
| “Retry trong Reactor bảo đảm xử lý khi ứng dụng restart” | Cần outbox/broker/persistence và cơ chế tiếp tục sau restart |
| “Reactive backpressure tự đi ngược sang mọi Kafka/JMS/DB” | Mỗi adapter/broker có giới hạn, prefetch, ACK và semantics riêng |

## 17. Bài thực hành

1. Dùng `StepVerifier.withVirtualTime` kiểm tra `timeout` trên `Mono.delay`, thay 2 giây thành 5 giây và giải thích khác biệt khi remote hoàn thành sau deadline.
2. Cho publisher lỗi hai lần rồi thành công; kiểm tra `Retry.backoff(2,...)` và `attempts == 3`. Đổi thành `backoff(1,...)` để quan sát retry exhausted.
3. Di chuyển `timeout` trước/sau `retryWhen` và dùng virtual time đo khác biệt giữa deadline từng attempt và deadline tổng.
4. Tạo mock API trả lần lượt `503, 503, 200`; quan sát HTTP status mapping, số lần gọi thực tế và backoff.
5. Cho mock trả `400`, `401` và `429`, kiểm tra chỉ những lỗi hợp đồng cho phép mới retry.
6. Mô phỏng API nhận `POST` và ghi dữ liệu thành công nhưng mất response; triển khai idempotency theo `eventId` ở mock và chứng minh chỉ một side effect được ghi.
7. Đưa `PartnerQuoteClient` vào một reactive handler để gọi ra ngoài; thử xử lý lỗi không nuốt thông tin, không dùng `block()` trên WebFlux event loop.
8. So sánh cấu hình dùng trực tiếp `WebFlux.outboundGateway` với `PartnerQuoteClient.quote(...)`; nêu rõ nơi nào thực sự có retry operator và nơi nào chỉ có transport timeout.
9. Đưa nguồn Kafka/JMS vào flow; cố tình restart ứng dụng giữa các retries, thiết kế outbox/retry bền vững và ACK hợp lý.
10. Dùng SSE/Flux phát ba events rồi lỗi, bật `retryWhen` và quan sát dữ liệu bị lặp. Đề xuất cursor/replay/deduplication để không bỏ lỡ cũng không nhân đôi event.
11. Làm đầy connection pool của mock client và phân biệt pending-acquire timeout với response timeout qua logs/metrics.
12. Lập bảng ngân sách SLA 8 giây gồm queue, remote HTTP, backoff, downstream persist; xác định ranh giới ngừng retry và cách trả kết quả cho inbound HTTP client.

**Tình huống tổng hợp:** một `POST /api/orders` tạo đơn, ghi DB, gửi sự kiện Kafka rồi gọi đối tác giao vận qua WebClient. Đối tác đã tạo vận đơn nhưng response bị mất; client HTTP phía ngoài vẫn đang chờ và Kafka message có thể bị redelivery. Hãy chọn timeout cho từng lớp, deadline tổng, retry policy, idempotency key, ranh giới transaction và điều kiện trả `201 Created` hoặc `202 Accepted`. Vì sao chỉ thêm `retryWhen(3)` vào một Mono chưa đủ?

## 18. Tài liệu tham khảo

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): WebFlux outbound gateway/adapter và cơ chế HTTP reactive.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): hợp đồng request-reply, request/reply timeout và error channel.
- [Spring Integration Reference — Reactive Streams](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveStreamsConsumer` và reactive message handlers.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): request/response handling và lỗi HTTP.
- [Spring Framework Reference — WebClient Retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): cách `retrieve()` xử lý HTTP 4xx/5xx và tùy biến status.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): transport/connect/response timeout và connection pool.
- [Project Reactor Reference — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): `retryWhen`, retry signals, backoff và giới hạn số lần thử.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time và kiểm thử asynchronous publishers.

> **Ghi nhớ:** timeout giới hạn **thời gian chờ của một lớp**, còn retry **lặp subscription hoặc một request** khi được phép. Trên Spring Integration WebFlux, phải phân biệt timeout pool/TCP/response với `Mono.timeout`, `Flux.timeout`, `replyTimeout` và deadline nghiệp vụ; đặt đúng thứ tự retry operators, dùng idempotency cho tác vụ có side effect và thiết kế ACK/outbox/error flow để bảo đảm tính nhất quán khi có lỗi hoặc restart.
