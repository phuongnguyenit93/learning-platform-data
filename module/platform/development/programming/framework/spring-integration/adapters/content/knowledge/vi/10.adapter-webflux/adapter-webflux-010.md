# Xử lý lỗi không chặn luồng trong Spring Integration WebFlux

## 1. Bài toán: khi dịch vụ ngoài lỗi, luồng vẫn phải vận hành ổn định

Một ứng dụng nhận sự kiện từ Kafka hoặc JMS, kiểm tra tồn kho qua HTTP, sau đó cập nhật đơn hàng trong database. Nếu HTTP server trả `503 Service Unavailable`, mạng đứt hoặc payload JSON không giải mã được, luồng cần phát hiện lỗi, phân loại, ghi nhận và lựa chọn xử lý tiếp theo. Cách xử lý sai thường là gọi `block()` để đợi WebClient, bắt ngoại lệ bằng `try/catch`, sau đó `Thread.sleep` để retry. Cách này có thể chiếm dụng thread (đặc biệt nguy hiểm trên Reactor Netty event loop) và che giấu hợp đồng lỗi bất đồng bộ.

**Xử lý lỗi không chặn luồng** là dùng tín hiệu lỗi của Reactive Streams và các toán tử Reactor như `doOnError`, `onErrorMap`, `onErrorResume`, `retryWhen`, `timeout`, phối hợp với error flow của Spring Integration. Mục tiêu không phải “nuốt mọi lỗi để chương trình chạy tiếp”, mà là **lỗi được truyền, xử lý hoặc chuyển thành kết quả nghiệp vụ một cách có kiểm soát**, trong khi không khóa thread chờ I/O.

Chủ đề thuộc chương **Adapter WebFlux** trong module **SPRING_INTEGRATION_ADAPTERS**, nơi các inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối HTTP, file, SFTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Khi đi qua các ranh giới đó, cần phân biệt rõ: lỗi của HTTP request, lỗi trong Reactor pipeline, lỗi dispatch message, lỗi của poller/broker và lỗi của nghiệp vụ.

~~~mermaid
flowchart LR
    A["Kafka / JMS / File / HTTP"] --> B["Spring Integration Message"]
    B --> C["MessageChannel"]
    C --> D["WebFlux outbound gateway / WebClient"]
    D -->|"HTTP request"| E["API tồn kho"]
    E -->|"HTTP response / network error"| D
    D --> F{"Kết quả"}
    F -->|"Thành công"| G["Reply Message<InventoryReply>"]
    F -->|"Lỗi có thể retry"| H["Retry có giới hạn"]
    F -->|"Lỗi nghiệp vụ"| I["Kết quả lỗi có cấu trúc"]
    F -->|"Lỗi chưa khôi phục"| J["Error flow / DLQ / cảnh báo"]
    H --> D
~~~

Trong sơ đồ, đường retry chỉ là logic khi policy cho phép, không ngụ ý Spring Integration tự retry mọi lỗi. Với message nguồn cần đảm bảo xử lý, các bước ACK/commit, outbox và idempotency phải được thiết kế riêng.

## 2. Hợp đồng lỗi của Mono và Flux

Reactive Streams có ba loại tín hiệu kết quả quan trọng: `onNext(T)` phát dữ liệu, `onComplete()` báo hoàn tất và `onError(Throwable)` báo lỗi. `Mono<T>` phát tối đa một phần tử; `Flux<T>` có thể phát nhiều phần tử. Sau khi phát `onError` hoặc `onComplete`, subscription đó **kết thúc** và không phát thêm `onNext` hợp lệ.

~~~mermaid
sequenceDiagram
    participant Source as Publisher
    participant Op as Reactive operators
    participant Sub as Subscriber
    Sub->>Source: subscribe + request(n)
    Source-->>Op: onNext(item 1)
    Op-->>Sub: onNext(item 1)
    Source-->>Op: onError(timeout)
    alt Có onErrorResume
        Op->>Op: Chọn fallback publisher
        Op-->>Sub: onNext(fallback) hoặc empty
        Op-->>Sub: onComplete
    else Không có error handler
        Op-->>Sub: onError(timeout)
    end
~~~

| Tình huống | Ý nghĩa | Cách xử lý phù hợp |
|---|---|---|
| `Mono.just(value)` | Một giá trị rồi complete | Chuyển kết quả thành reply hoặc lưu dữ liệu |
| `Mono.empty()` | Hoàn tất không có phần tử | Quy định “không tìm thấy” hay “không cần trả body” |
| `Mono.error(ex)` | Lỗi làm kết thúc chuỗi | Phân loại, map, retry hoặc chuyển error flow |
| `Flux` lỗi sau 3 phần tử | Ba phần tử trước đã phát; subscription kết thúc lỗi | Giữ cursor, tránh phát trùng khi retry |
| `cancel()` | Consumer không muốn nhận tiếp | Dọn tài nguyên; không đồng nghĩa rollback việc đã làm |

**Quan trọng:** `Mono.empty()` không phải `Mono.error(...)`. Một request tìm tồn kho trả “không có bản ghi” nên được ánh xạ thành 404 hoặc domain outcome phù hợp, không nên tự quy tất cả thành lỗi mạng. Reactive Streams cũng không cho phép `onNext(null)`; nếu không có dữ liệu hãy dùng `Mono.empty()` hoặc một object kết quả rõ ràng.

## 3. Các toán tử xử lý lỗi: quan sát, biến đổi, phục hồi

| Toán tử Reactor | Mục đích | Điểm cần tránh |
|---|---|---|
| `doOnError(consumer)` | Ghi log, metrics hoặc tracing khi thấy lỗi | Không thay thế lỗi và không làm recovery |
| `onErrorMap(mapper)` | Chuyển exception tầng thấp thành exception domain | Không làm mất cause/context hữu ích |
| `onErrorResume(ex -> publisher)` | Chọn một publisher thay thế tùy lỗi | Không nuốt lỗi ngoài dự kiến |
| `onErrorReturn(value)` | Trả giá trị dự phòng có sẵn | Không tạo kết quả “thành công giả” cho giao dịch quan trọng |
| `onErrorComplete(...)` | Hoàn tất không phát lỗi với điều kiện | Không dùng để giấu lỗi thanh toán, lưu DB hoặc chuyển broker |
| `retryWhen(Retry...)` | Subscribe lại upstream khi lỗi phù hợp | Không retry vô hạn hoặc POST không idempotent |
| `timeout(Duration)` | Phát lỗi khi chờ quá hạn | Không chứng minh remote đã hủy/rollback |
| `doFinally(signal)` | Cleanup/metrics cho complete, error hoặc cancel | Không giả định chỉ gọi khi thành công |

Ví dụ rất nhỏ minh họa các tầng:

~~~java
Mono<InventoryReply> guarded = inventoryApi.find("SKU-001")
    .doOnError(error -> log.warn("Inventory lookup failed", error))
    .onErrorMap(
        java.util.concurrent.TimeoutException.class,
        error -> new InventoryDependencyException(
            "Inventory timeout", error))
    .onErrorResume(
        InventoryDependencyException.class,
        error -> Mono.just(InventoryReply.unknown("SKU-001")));
~~~

Đoạn trên là **mảnh code minh họa**, các type `inventoryApi`, `log`, `InventoryDependencyException` và `InventoryReply` thuộc ứng dụng. Fallback `unknown` chỉ hợp lệ nếu nghiệp vụ **cho phép trạng thái chưa xác định**. Nếu hệ thống phải đảm bảo không bán hàng vượt tồn kho, không được gán ngầm “còn hàng” khi dependency thất bại.

## 4. Những lỗi có thể xuất hiện ở đâu trong Spring Integration WebFlux?

| Ranh giới | Ví dụ lỗi | Tín hiệu thường quan sát | Phản ứng cần thiết |
|---|---|---|---|
| Inbound WebFlux route | Path, HTTP method, `Content-Type` không hợp lệ | HTTP 404/405/415 theo trường hợp | Trả lỗi client an toàn, chưa đưa message vào flow |
| Inbound decode/validation | JSON hỏng, field sai, thiếu quyền | WebFlux exception hoặc validation result | HTTP 400/401/403/422 theo hợp đồng |
| `MessageChannel` | Không có consumer, executor/queue đầy | Send failure, dispatch exception | Giới hạn tải, error handling ở messaging |
| Handler reactive | `Mono.error`/`Flux.error` | `onError` trong publisher | Recovery, retry hoặc error flow |
| WebClient HTTP | Remote trả 404/429/503 | HTTP status được map thành lỗi/giá trị | Phân loại status trước khi retry |
| Reactor Netty | DNS, TLS, TCP, response timeout | Transport exception/cause | Network policy, timeout, retry có điều kiện |
| Reply trong gateway | Không có reply đúng hạn | `replyTimeout` / timeout error | Trả lỗi phù hợp, không giữ HTTP request mãi |
| Adapter Kafka/JMS/DB poller | Redelivery, transaction, ACK/commit failure | Lỗi theo adapter/broker/DB | DLQ, outbox, đảm bảo xử lý trùng |
| HTTP streaming SSE | Lỗi sau khi gửi một số event | `onError`/connection close | Không thể đổi status đã commit |

**Không đồng nhất hai lớp lỗi:** `onErrorResume` hoạt động **trong publisher mà nó được gắn vào**; `errorChannel` của Spring Integration xử lý `ErrorMessage` khi framework/endpoint chuyển lỗi sang hệ thống messaging. Lỗi phát sinh từ một publisher không nhất thiết được chuyển thành `ErrorMessage` trừ khi endpoint tiêu thụ lỗi và có cấu hình phù hợp. Việc gọi `send()` thành công cũng không chứng minh hoạt động HTTP bất đồng bộ đã hoàn tất.

## 5. Ví dụ WebClient: phân loại HTTP status trước khi trả lỗi domain

Để luồng không phụ thuộc chi tiết `WebClientResponseException`, nên ánh xạ status/transport error sang các lỗi domain có ý nghĩa. Ví dụ một HTTP inventory service trả `200` kèm JSON, `404` khi SKU không tồn tại và `503` nếu dependency tạm ngừng.

### 5.1. DTO và exception

~~~java
package com.example.integration;

public record InventoryReply(String sku, int available) {
    public static InventoryReply unknown(String sku) {
        return new InventoryReply(sku, -1); // -1 là trạng thái UNKNOWN theo ví dụ.
    }
}
~~~

~~~java
package com.example.integration;

public class InventoryNotFoundException extends RuntimeException {
    public InventoryNotFoundException(String sku) {
        super("Inventory not found for " + sku);
    }
}
~~~

~~~java
package com.example.integration;

public class InventoryDependencyException extends RuntimeException {
    public InventoryDependencyException(String message) {
        super(message);
    }
    public InventoryDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Giá trị `-1` của `available` chỉ là ví dụ biểu diễn UNKNOWN; trong production nên ưu tiên domain model phân biệt `FOUND`, `NOT_FOUND`, `UNKNOWN` để tránh diễn giải sai số tồn âm như số tồn thật.

### 5.2. Dùng WebClient với onStatus, timeout và retry có lọc

~~~java
package com.example.integration;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class InventoryClient {

    private final WebClient client;

    public InventoryClient(@Qualifier("inventoryWebClient") WebClient client) {
        this.client = client;
    }

    public Mono<InventoryReply> find(String sku) {
        // defer giúp mỗi subscription/attempt tạo một HTTP request mới.
        return Mono.defer(() -> client.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .onStatus(status -> status.value() == 404,
                    response -> Mono.just(
                        new InventoryNotFoundException(sku)))
                .onStatus(HttpStatusCode::is5xxServerError,
                    response -> Mono.just(
                        new InventoryDependencyException(
                            "Inventory HTTP " + response.statusCode().value())))
                .bodyToMono(InventoryReply.class))
            .timeout(Duration.ofSeconds(2))
            .retryWhen(Retry
                .backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(this::retryable))
            .timeout(Duration.ofSeconds(6));
    }

    private boolean retryable(Throwable error) {
        return error instanceof InventoryDependencyException
            || error instanceof TimeoutException
            || error instanceof WebClientRequestException;
    }
}
~~~

Với Spring Boot, tạo client dùng chung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryClientConfiguration {
    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder.baseUrl("http://localhost:9090").build();
    }
}
~~~

**Đọc chính xác ví dụ:**

1. `retrieve()` cùng `onStatus(...)` biến HTTP status thành **error signal**; `404` là lỗi không tìm thấy theo domain, `5xx` là lỗi dependency.
2. Với `429 Too Many Requests` hoặc các 4xx khác, hành vi mặc định của `retrieve()` có thể phát `WebClientResponseException`; ví dụ chưa retry các mã này. Nếu muốn retry `429`, cần ánh xạ/filter riêng và xem xét header `Retry-After`.
3. `bodyToMono(InventoryReply.class)` giải mã JSON body khi response được xử lý như thành công. **Chưa có** validation `sku`, quyền truy cập hoặc schema kinh doanh; cần triển khai riêng.
4. `timeout(2s)` trước `retryWhen` áp dụng cho **mỗi attempt**. `timeout(6s)` sau retry giới hạn **toàn bộ chuỗi** gồm backoff.
5. `Retry.backoff(2, ...)` có tối đa hai lần retry sau lần thử đầu. Nó chỉ chạy với lỗi khớp `retryable`.
6. Retry `WebClientRequestException` trong ví dụ này giả định **GET chỉ đọc**. Trong production, phải phân loại cause: lỗi chứng chỉ/TLS trust hoặc tên miền sai không nên retry liên tục.
7. Không có `block()` hay `Thread.sleep`. Lỗi được phát bất đồng bộ cho subscriber/endpoint; không vì vậy mà có bảo đảm tiến trình không có thao tác blocking khác ở downstream.

Đây là mã minh họa có chủ đích; việc sử dụng trong production phải bổ sung connect/response timeout ở transport, circuit breaker, giới hạn concurrency và điều kiện fallback theo nghiệp vụ.

## 6. Fallback: khi nào được trả kết quả thay vì phát lỗi?

Fallback có giá trị khi hệ thống vẫn có thể tiếp tục **mà không làm sai kết quả**. Ví dụ dashboard có thể hiện trạng thái `UNKNOWN` khi API tồn kho không sẵn sàng, nhưng nghiệp vụ thu tiền không được giả định hết lỗi là thành công.

~~~java
Mono<InventoryReply> displayInventory(String sku) {
    return inventoryClient.find(sku)
        .onErrorResume(
            InventoryNotFoundException.class,
            error -> Mono.just(new InventoryReply(sku, 0)))
        .onErrorResume(
            InventoryDependencyException.class,
            error -> Mono.just(InventoryReply.unknown(sku)));
}
~~~

Đây là **policy dành riêng cho hiển thị**: SKU không tồn tại được biểu diễn “0”, còn dependency lỗi được biểu diễn “UNKNOWN”. Phải **phân biệt rõ** hai trường hợp trong giao diện và logging. Các lỗi khác, ví dụ authentication, serialization hoặc cấu hình hỏng, vẫn truyền về downstream.

Nếu một tác vụ cần tính toán chính xác tồn kho để giữ tiền hoặc chốt đơn, nên **fail closed** hoặc chuyển sang trạng thái `PENDING` và xử lý lại sau; không dùng `onErrorReturn(new InventoryReply(sku, 9999))`.

### 6.1. Đừng vô tình nuốt lỗi bằng onErrorComplete

~~~java
// NGUY HIỂM nếu ghi đơn hàng quan trọng:
Mono<Void> ignored = saveOrder(order)
    .onErrorComplete();

// Tốt hơn: cho lỗi truyền đi hoặc biến thành outcome nghiệp vụ rõ ràng.
Mono<OrderOutcome> handled = saveOrder(order)
    .thenReturn(OrderOutcome.saved(order.id()))
    .onErrorResume(TemporaryDatabaseException.class,
        error -> Mono.just(OrderOutcome.pending(order.id())));
~~~

Các type `saveOrder`, `OrderOutcome`, `TemporaryDatabaseException` là thành phần ứng dụng trong snippet. `pending` chỉ được phép dùng nếu thực sự có nơi lưu và cơ chế xử lý lại tác vụ, không chỉ đổi trạng thái trong bộ nhớ.

## 7. Không để một phần tử lỗi làm ngừng toàn bộ Flux khi không cần thiết

Một stream nhận nhiều yêu cầu tra tồn kho. Nếu gọi `flatMap(inventoryClient::find)` trực tiếp, lỗi ở một SKU có thể kết thúc **toàn bộ** `Flux`. Trong một số nghiệp vụ, ta muốn kết quả của từng SKU độc lập, đồng thời những SKU lỗi trở thành outcome rõ ràng.

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public record LookupOutcome(
    String sku, InventoryReply reply, String errorCode) {

    public static LookupOutcome success(String sku, InventoryReply reply) {
        return new LookupOutcome(sku, reply, null);
    }

    public static LookupOutcome unavailable(String sku) {
        return new LookupOutcome(sku, null, "DEPENDENCY_UNAVAILABLE");
    }
}

Flux<LookupOutcome> results = Flux.fromIterable(skus)
    .flatMap(sku ->
        inventoryClient.find(sku)
            .map(reply -> LookupOutcome.success(sku, reply))
            .onErrorResume(
                InventoryDependencyException.class,
                error -> Mono.just(LookupOutcome.unavailable(sku))),
        8);
~~~

Trong đoạn này, `skus` là danh sách/`Iterable<String>` đầu vào. Mỗi `inner Mono` xử lý lỗi dependency của **chính SKU đó**, nên lỗi tạm thời đã được biết trước không làm dừng stream của tất cả SKU. Những lỗi **khác** vẫn có thể làm `Flux` tổng thể kết thúc; đây là chủ ý.

Nếu cần map `InventoryNotFoundException` thành `LookupOutcome.notFound`, thêm một nhánh xử lý riêng; đừng biến “không tìm thấy” thành dependency unavailable. `flatMap(..., 8)` giới hạn số inner publishers active, nhưng không bảo đảm kết quả giữ đúng thứ tự đầu vào; dùng `concatMap` hoặc cơ chế tuần tự hóa khi yêu cầu ordering.

**Chú ý về null:** `LookupOutcome` là object không null (hợp lệ với Reactive Streams). Field `reply` có thể null để biểu diễn outcome thất bại trong ví dụ, nhưng production nên dùng sealed result types hoặc DTO có trạng thái rõ ràng để tránh gọi `reply.available()` trên null.

### 7.1. Vì sao onErrorContinue thường không phải lựa chọn tốt?

`onErrorContinue` có semantics phụ thuộc operator, có thể ảnh hưởng upstream và khiến lỗi bị bỏ qua không như dự đoán. Với luồng tích hợp nghiệp vụ, cách dễ kiểm soát hơn là **bao từng phần tử trong `flatMap`/`concatMap` và xử lý lỗi ngay tại inner publisher**, giống ví dụ ở trên. Đừng dùng `onErrorContinue` như cơ chế mặc định để “stream không bao giờ dừng”.

## 8. Retry không chặn luồng nhưng vẫn có thể làm quá tải

`retryWhen(Retry.backoff(...))` lên lịch thử lại trong Reactor thay vì dùng `Thread.sleep`. Tuy nhiên, nhiều nguồn message đồng thời retry sẽ làm tăng số request vào hệ thống đang lỗi.

~~~java
Mono<InventoryReply> retried = inventoryClient.find("SKU-001")
    .doOnError(error -> log.warn("Final inventory error", error));
~~~

Ví dụ `InventoryClient.find(...)` đã có retry riêng. **Không** thêm một `retryWhen` ngoài cùng một cách máy móc: mỗi lớp retry lại có thể nhân số attempts. Nếu tầng service, IntegrationFlow và Kafka listener cùng retry, một event có thể tạo rất nhiều HTTP calls.

| Loại lỗi | Retry? | Lý do |
|---|---|---|
| HTTP 400/401/403 | Thường không | Dữ liệu hoặc quyền truy cập không được sửa bằng retry |
| HTTP 404 | Theo hợp đồng | Có thể là kết quả nghiệp vụ hợp lệ |
| HTTP 429 | Có điều kiện | Backoff, xem `Retry-After`, giảm tải |
| HTTP 502/503/504 | Có điều kiện | Thường transient, cần deadline và giới hạn |
| Timeout khi POST tạo đơn | Chỉ nếu idempotent | Remote có thể đã thực hiện side effect |
| JSON decode/schema lỗi | Thường không | Lỗi hợp đồng dữ liệu cần sửa |
| Network reset | Theo hợp đồng thao tác | Có thể đã gửi request; cần idempotency |

Một POST tạo vận đơn nếu timeout có thể đã được server ghi nhận. Khi retry, phải dùng cùng **idempotency key** và phía đối tác **thực thi** việc khử trùng lặp. Chỉ gắn một UUID vào header mà remote bỏ qua không tạo ra bảo đảm nào.

### 8.1. Timeout và retry là hai vòng đồng hồ

~~~java
// Timeout từng attempt, có thể trigger retry.
Mono<InventoryReply> perAttempt = callOnce()
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)));

// Timeout toàn operation, gồm attempts và backoff.
Mono<InventoryReply> overall = callOnce()
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200)))
    .timeout(Duration.ofSeconds(6));
~~~

`callOnce()` là publisher **cold/repeatable** do ứng dụng cung cấp. Các đoạn là lựa chọn thay thế nhau. Đặt `timeout` **trước** retry giới hạn từng attempt; đặt **sau** retry giới hạn thời gian của toàn chuỗi. Nếu cần cả hai ràng buộc, có thể kết hợp hai `timeout` theo thứ tự tương ứng, đồng thời tránh cấu hình xung đột với timeout của Reactor Netty.

## 9. Ánh xạ lỗi với Spring Integration WebFlux outbound gateway

Trong Spring Integration, `WebFlux.outboundGateway(...)` gọi remote service bằng WebClient và tạo **reply message** khi exchange thành công. Ví dụ đơn giản:

~~~java
package com.example.integration;

import org.springframework.beans.factory.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class InventoryGatewayFlow {

    public record InventoryRequest(String sku) {}

    @Bean
    IntegrationFlow outboundInventory(WebClient inventoryWebClient) {
        return IntegrationFlow.from("inventoryRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:9090/api/inventory/query",
                    inventoryWebClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(InventoryReply.class))
            .channel("inventoryReplies")
            .get();
    }
}
~~~

**Điểm cần phân biệt:** `InventoryClient.find(...)` ở mục 5 là một Java service có policy `onStatus`, `timeout`, `retryWhen`. Cấu hình `WebFlux.outboundGateway(...)` ở đây dùng WebClient trực tiếp, **không tự chạy policy bên trong `InventoryClient.find(...)`**. Nếu muốn lỗi được phân loại và retry theo cơ chế Spring Integration endpoint, cần thiết kế advice/error flow tương thích với cách xử lý bất đồng bộ của phiên bản đang chạy, rồi kiểm thử.

Tại một outbound gateway, khi remote trả 4xx/5xx, lỗi HTTP/network/decode có thể phát sinh **sau** khi `MessageChannel.send(...)` đã trả về. Không coi `send() == true` là thành công của HTTP request. Cần chọn nơi quan sát kết quả và nơi ghi nhận error outcome theo correlation ID của message nguồn.

Nếu chỉ cần gửi HTTP một chiều, sử dụng `WebFlux.outboundChannelAdapter(...)`; nó không tạo reply message nghiệp vụ. Tuy nhiên, HTTP status và lỗi mạng vẫn phải được quản lý.

## 10. ReactiveMessageHandler và cách giữ lỗi trong pipeline

Spring Integration hỗ trợ `ReactiveMessageHandler`, với phương thức xử lý trả `Mono<Void>`. Java DSL từ Spring Integration 6.1 có `handleReactive(...)` để tích hợp side effect bất đồng bộ mà không cần tự `block()`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import reactor.core.publisher.Mono;

@Bean
IntegrationFlow checkInventoryCommands(InventoryClient client) {
    return IntegrationFlow.from("inventoryCommands")
        .handleReactive(message -> {
            String sku = (String) message.getPayload();
            return client.find(sku)
                .doOnNext(reply -> System.out.println(
                    "Received inventory: " + reply))
                .then();
        })
        .get();
}
~~~

Ví dụ này là một nhánh **side effect một chiều**, không tạo reply `InventoryReply` cho downstream. `then()` chỉ phát tín hiệu hoàn tất hoặc lỗi của công việc, giúp endpoint/reactive consumer theo dõi kết quả. Thao tác in log chỉ để minh họa: production cần persist/publish qua API async/reactive phù hợp, không biến một log entry thành chứng nhận commit.

Trong handler reactive, `try/catch` bên ngoài đoạn trả `Mono` thường chỉ bắt được lỗi **ngay lúc xây dựng publisher**. Lỗi HTTP xuất hiện **khi subscription chạy** thì phải xử lý bằng các operator hoặc error handling của endpoint:

~~~java
// Sai mô hình kỳ vọng: catch không đón được mọi lỗi phát sau subscription.
try {
    Mono<InventoryReply> publisher = client.find("SKU-001");
    // Chưa có nghĩa HTTP request đã hoàn tất.
} catch (Exception error) {
    // Không phải đường xử lý mọi reactive onError.
}

// Đúng hướng: gắn error policy lên publisher.
Mono<InventoryReply> publisher = client.find("SKU-001")
    .doOnError(error -> log.warn("Reactive operation failed", error));
~~~

Khi `MessageHandler` không có đường reply nhưng một inbound gateway đang chờ kết quả HTTP, gateway có thể timeout; đừng nhầm `Mono<Void>` completion với reply DTO tự động. Muốn hợp đồng request-reply, chọn gateway/handler trả reply có correlation rõ ràng.

## 11. Spring Integration errorChannel và lỗi ngoài Reactor

Spring Integration cung cấp `ErrorMessage` và `errorChannel` để xử lý lỗi messaging. Tùy endpoint và channel, lỗi có thể được ném ra đồng bộ, chuyển qua error channel hoặc tồn tại dưới dạng `onError` của publisher. Vì vậy, **không có một quy tắc đơn giản “mọi lỗi đều vào errorChannel”**.

| Đường đi | Ví dụ | Cách xử lý |
|---|---|---|
| Dispatch đồng bộ | `DirectChannel` consumer ném exception ngay trong `send` | Caller hoặc flow/advice xử lý exception |
| Executor/poller | Worker thread chạy handler và bị lỗi | Error handler/error channel phù hợp của endpoint |
| Reactive pipeline | WebClient `Mono` phát `onError` sau subscription | Reactor operators hoặc reactive endpoint error handling |
| Inbound gateway | Handler không trả reply trước deadline | `replyTimeout`, timeout/error mapping |
| Broker source | Kafka/JMS listener ném lỗi hoặc redelivery | Ack/retry/DLQ theo adapter và broker |

Ví dụ một **error flow dùng để ghi nhận ErrorMessage** (phải bảo đảm lỗi từ endpoint thực sự được định tuyến đến channel tương ứng):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessagingException;

@Bean
IntegrationFlow integrationErrors() {
    return IntegrationFlow.from("errorChannel")
        .handle(message -> {
            Throwable error = (Throwable) message.getPayload();
            System.err.println("Integration error: " + error.getClass());
            if (error instanceof MessagingException me
                    && me.getFailedMessage() != null) {
                System.err.println("Failed message available for correlation");
            }
        })
        .get();
}
~~~

Đây là **cấu hình minh họa đường nhận lỗi**, không chứng minh mọi publisher error tự đến đây. `errorChannel` mặc định có thể đã được Spring Integration đăng ký; hãy kiểm tra cấu hình endpoint, error header, advice và cách định tuyến của hệ thống. Không ghi nguyên failed message payload hoặc credential vào log. Với những lỗi không có thể xử lý phục hồi tại chỗ, lưu trạng thái thất bại và chuyển tới dead-letter/reconciliation workflow.

**Bảo toàn correlation:** error message cần đủ message ID, business event ID và thông tin source để đối soát. Một lỗi HTTP phát sau `send` không nhất thiết có stack trace trên caller thread; observability và context propagation cần được thiết kế.

## 12. Inbound WebFlux gateway: trả lỗi HTTP mà không chặn thread

Một inbound gateway nhận HTTP request, tạo Spring Integration message rồi chờ reply. Với request-reply, phải phân biệt:

- **Lỗi trước flow:** sai method, path, media type, JSON invalid hoặc authentication failure do WebFlux xử lý.
- **Lỗi trong flow:** validation, không đủ quyền nghiệp vụ, database failure, downstream `Mono.error` hoặc gateway `replyTimeout`.
- **Lỗi khi ghi response:** client đã rời, body serialization fail hoặc stream phát lỗi sau khi response đã commit.

Nếu nghiệp vụ yêu cầu `404` cho SKU không tồn tại và `503` khi dependency không sẵn sàng, hãy có **quy tắc ánh xạ exception/domain outcome sang HTTP status**. `onErrorResume` có thể biến lỗi thành một DTO phù hợp, nhưng **không tự đặt HTTP status** theo ý nghĩa nghiệp vụ nếu endpoint không được cấu hình.

~~~mermaid
flowchart TD
    A["HTTP request đến inbound gateway"] --> B{"Request/codec hợp lệ?"}
    B -->|"Không"| C["HTTP 4xx từ route/validation mapping"]
    B -->|"Có"| D["Spring Integration request message"]
    D --> E{"Downstream result"}
    E -->|"Success reply"| F["HTTP 200 + DTO"]
    E -->|"Domain not found"| G["HTTP 404 theo hợp đồng"]
    E -->|"Dependency unavailable"| H["HTTP 503 theo hợp đồng"]
    E -->|"Không có reply"| I["Timeout/error flow được cấu hình"]
~~~

`replyTimeout` là giới hạn **chờ reply message** theo hợp đồng Spring Integration. Nó không đồng nghĩa với `responseTimeout` của WebClient outbound và không nhất thiết giới hạn toàn bộ thời gian phát của một `Flux` SSE đã được trả làm payload reply. Không tự giả định một lỗi ở downstream luôn được trả cho HTTP caller dưới dạng status `503`; phải kiểm chứng bằng integration test.

### 12.1. Trước và sau khi HTTP response được commit

| Lỗi xuất hiện | HTTP server có thể làm gì? |
|---|---|
| Trước khi status/headers được gửi | Có thể chọn status `4xx/5xx` và body lỗi đã lọc |
| Sau khi SSE đã phát vài events | Không thể đổi `200 OK` thành `500` trong cùng response |
| Khi browser ngắt kết nối | Có thể cancel HTTP subscription, cleanup resource |
| Khi nguồn nóng vẫn phát sau cancel | Các subscriber khác có thể tiếp tục; cần giới hạn nguồn và buffer |

Nếu SSE đang gửi thì phát sinh lỗi, có thể cho stream kết thúc, hoặc phát một **SSE event loại `error`** theo hợp đồng nếu vẫn ghi được. Event `error` không thay thế HTTP status và không đảm bảo client nhận được nếu kết nối đã đứt.

## 13. Xử lý lỗi theo từng phần tử của HTTP stream

Với `Flux` từ SSE hoặc NDJSON, nên quyết định một lỗi thuộc **toàn kết nối** hay **một record**. Nếu record đơn lẻ bị lỗi validation, có thể biến nó thành outcome dữ liệu có trạng thái; nếu nguồn mất kết nối, phải quyết định reconnect/resume ở cấp subscription.

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<LookupOutcome> stream = incomingSkus
    .flatMap(sku ->
        inventoryClient.find(sku)
            .map(reply -> LookupOutcome.success(sku, reply))
            .onErrorResume(InventoryDependencyException.class,
                error -> Mono.just(LookupOutcome.unavailable(sku))),
        4);
~~~

`incomingSkus` là `Flux<String>` hoặc publisher tương thích, `LookupOutcome` đã định nghĩa ở mục 7. Cách này xử lý lỗi **bên trong từng inner publisher** để một dependency failure có thể được biểu diễn thành kết quả cho một SKU mà không dừng stream còn lại.

Ngược lại, nếu nguồn HTTP itself bị `onError`, stream phía ngoài vẫn có thể kết thúc. `retryWhen` ở toàn Flux có thể subscribe lại từ đầu, làm phát trùng các events đã nhận; dùng cursor/event ID, de-duplication hoặc thiết kế resume rõ ràng khi dữ liệu phải được nhận đủ.

Đừng gọi `collectList()` trên stream vô hạn chỉ để “đợi dữ liệu xử lý xong”: nó sẽ không bao giờ hoàn thành hoặc làm tăng bộ nhớ. Với stream lớn, quản lý concurrency, size giới hạn, backpressure và cancellation.

## 14. Logging, metrics, tracing và không làm chậm event loop

`doOnError` phù hợp để gắn logging/metrics, nhưng callback cũng chạy trong ngữ cảnh thực thi của publisher; một thao tác blocking nặng bên trong `doOnError` vẫn có thể ảnh hưởng event loop.

~~~java
Mono<InventoryReply> observed = inventoryClient.find("SKU-001")
    .doOnError(error -> metrics.counter(
        "inventory.lookup.failed",
        "exception", error.getClass().getSimpleName()).increment())
    .doFinally(signal -> metrics.counter(
        "inventory.lookup.terminated",
        "signal", signal.name()).increment());
~~~

`metrics` là một `MeterRegistry` phù hợp trong ứng dụng thực. Chỉ sử dụng tags cardinality thấp như tên dependency, loại lỗi và nhóm status; không dùng token, request ID riêng từng request hoặc toàn URL query làm metric tags.

Những chỉ số nên đo:

1. **Error rate theo loại:** 4xx/5xx, network, TLS, codec, timeout, validation và xử lý nội bộ.
2. **Latency từng giai đoạn:** chờ connection pool, TCP/TLS, HTTP response, retry/backoff và thời gian xử lý end-to-end.
3. **Retry outcomes:** số attempt, retry exhausted, fallback được kích hoạt, kết quả `UNKNOWN`.
4. **Channel/adapter:** queue depth, in-flight messages, poller lag, broker consumer lag và dead-letter count.
5. **Streaming:** active subscriptions, cancellation, event lag, dropped events và sự kiện lỗi sau commit.

Với Reactor Context, trace/correlation data cần được propagate đúng qua reactive scheduler và message boundaries. Không dựa hoàn toàn vào `ThreadLocal`/MDC trên một thread khi chuỗi chuyển scheduler. Nếu công việc chạm tới logs/metrics không đồng bộ bên ngoài, thiết kế thêm giới hạn queue và quy tắc chống overload.

## 15. Kiểm thử lỗi không chặn luồng

### 15.1. Test onErrorResume: fallback chỉ cho lỗi đã biết

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorFallbackTest {

    @Test
    void knownErrorUsesFallback() {
        Mono<String> result =
            Mono.<String>error(new InventoryDependencyException("down"))
                .onErrorResume(InventoryDependencyException.class,
                    error -> Mono.just("UNKNOWN"));

        StepVerifier.create(result)
            .expectNext("UNKNOWN")
            .verifyComplete();
    }

    @Test
    void unexpectedErrorStillPropagates() {
        Mono<String> result =
            Mono.<String>error(new IllegalArgumentException("bad input"))
                .onErrorResume(InventoryDependencyException.class,
                    error -> Mono.just("UNKNOWN"));

        StepVerifier.create(result)
            .expectError(IllegalArgumentException.class)
            .verify();
    }
}
~~~

Test thứ hai chứng minh một lỗi không nằm trong policy **không bị nuốt**. Cần quy định rõ expected errors cho từng nhánh để không trả dữ liệu sai khi hệ thống phụ thuộc gặp sự cố.

### 15.2. Test timeout bằng virtual time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorTimeoutTest {

    @Test
    void slowPublisherFailsWithoutBlockingThread() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }
}
~~~

`StepVerifier.withVirtualTime` kiểm tra deadline **của Reactor operator**, không tự chứng minh connect timeout của Reactor Netty hoặc đường `errorChannel` Spring Integration đã hoạt động. Để kiểm chứng transport/gateway, cần integration tests với mock HTTP server điều khiển response status, delay, broken connection và body không hợp lệ.

### 15.3. Ma trận test end-to-end

| Tình huống | Điều cần xác nhận |
|---|---|
| Remote 200 JSON hợp lệ | Reply DTO đúng, không phát error |
| Remote 404 | Domain not found, không retry ngoài chính sách |
| Remote 429 hoặc 503 | Backoff có giới hạn, quan sát attempts; không retry storm |
| Remote liên tục lỗi | Error propagated/error flow sau khi retry exhausted |
| Response JSON sai schema | Codec/decode error không bị biến thành success |
| Network refused/TLS lỗi | Phân loại nguyên nhân, không retry trust error vô hạn |
| Một SKU lỗi trong Flux nhiều SKU | Chỉ SKU tương ứng thành outcome lỗi; các item khác vẫn xử lý |
| HTTP caller hủy SSE giữa stream | Subscription/cleanup và backlog được xử lý |
| Inbound gateway không có reply | Timeout, HTTP error mapping và error channel đúng cấu hình |
| Kafka/JMS redelivery sau HTTP timeout | Idempotency tránh side effect trùng |
| Handler gọi `Thread.sleep` trên event loop | Phát hiện block bằng BlockHound/test hoặc metrics ở môi trường thích hợp |

Nếu dùng `BlockHound` trong test, cần tích hợp phiên bản tương thích Reactor/JDK và hiểu false positives; đây là công cụ kiểm tra blocking operation, không thay thế code review, kiểm thử tải hay metrics.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Có `onErrorResume` thì mọi lỗi đều đã xử lý an toàn” | Phải phân loại lỗi và bảo đảm fallback không phá hợp đồng nghiệp vụ |
| “`doOnError` đã bắt và loại bỏ exception” | Chỉ quan sát; `onError` vẫn đi tiếp |
| “`try/catch` quanh `Mono` bắt được mọi lỗi HTTP” | Lỗi HTTP có thể xuất hiện sau subscription |
| “`onErrorContinue` luôn giữ được các record còn lại” | Semantics phụ thuộc operator; nên cô lập lỗi từng inner publisher |
| “`retryWhen` không chặn nên retry bao nhiêu lần cũng được” | Vẫn tốn network, pool, memory và có thể tạo retry storm |
| “`send() == true` chứng minh remote đã xử lý thành công” | Chỉ xác nhận hành vi gửi vào channel theo hợp đồng |
| “Lỗi trong publisher luôn vào Spring Integration `errorChannel`” | Phụ thuộc endpoint/subscription/error handling và cấu hình |
| “`Mono.empty()` giống `Mono.error()`” | Completion rỗng khác error signal |
| “Đã timeout thì remote chưa commit” | Remote có thể đã xử lý; cần idempotency/reconciliation |
| “Lỗi SSE sau khi gửi hai event sẽ đổi status thành 500” | Status đã commit không thể đổi giữa response |
| “`block()` giúp đơn giản hóa xử lý lỗi trong WebFlux” | Có thể chặn event loop; dùng reactive operators và async boundary |

## 17. Bài thực hành

1. Viết `Mono.error(new InventoryDependencyException(...))`, nối `doOnError` và `onErrorResume`. Quan sát thứ tự log và kết quả downstream.
2. Viết test `StepVerifier` cho `Mono.empty()` và `Mono.error()` để phân biệt completion rỗng với exception.
3. Thêm `onStatus` cho mock WebClient xử lý 404 thành `InventoryNotFoundException` và 503 thành `InventoryDependencyException`. Kiểm tra không nhầm status 404 với timeout.
4. Cho mock trả hai lần 503 rồi 200. Giới hạn retry bằng `Retry.backoff`; đo số attempts, latency và error outcome.
5. Dùng nhiều SKU trong `Flux.flatMap`; mô phỏng một SKU lỗi. Thực hiện xử lý lỗi ở inner `Mono` và kiểm tra các SKU còn lại vẫn có kết quả.
6. Cố tình dùng `onErrorComplete()` sau thao tác lưu đơn; giải thích vì sao flow có thể báo hoàn tất dù database failed, rồi thay bằng outcome `PENDING` có lưu bền vững.
7. Kết nối `WebFlux.outboundGateway` vào mock API, trả 503 và kiểm tra error flow. Chứng minh rằng retry policy đặt trên một service khác không tự áp dụng cho gateway.
8. Viết `handleReactive(...)` gọi `InventoryClient`; bảo đảm không có `block()`/`subscribe()` thủ công trong handler.
9. Tạo inbound gateway HTTP request-reply và cho downstream không trả reply; quan sát `replyTimeout` và thiết kế response 503 hoặc 504 có cấu hình rõ.
10. Tạo SSE phát hai events rồi lỗi. So sánh lỗi trước và sau khi headers đã commit; không kỳ vọng sửa HTTP status giữa response.
11. Gắn correlation ID vào message và logs, theo dõi một lỗi WebClient qua scheduler; xác minh không để lộ token và payload nhạy cảm.
12. Đưa nguồn Kafka/JMS vào flow, mô phỏng HTTP timeout sau khi remote đã xử lý. Thiết kế idempotency key, outbox/DLQ, ACK/commit và reconciliation.

**Câu hỏi tình huống:** hệ thống nhận lệnh thanh toán qua HTTP inbound gateway, gửi thông báo tới đối tác qua WebClient, ghi trạng thái database và publish Kafka. Phía đối tác đã ghi nhận nhưng response bị mất; WebClient timeout, message có thể được redeliver. Bạn sẽ xử lý lỗi không chặn như thế nào mà không biến khoản thanh toán thành success giả, không tạo giao dịch trùng và vẫn cho client biết trạng thái `PENDING`/`UNKNOWN` một cách nhất quán?

## 18. Tài liệu tham khảo

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): WebFlux inbound/outbound adapter, gateway, WebClient và reply/error semantics.
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveStreamsConsumer` và `handleReactive`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, message endpoint error handling và advice.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply timeout, error channel và correlation.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient, error handling, `retrieve` và `onStatus`.
- [Project Reactor Reference — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `doOnError`, `onErrorResume`, `onErrorMap`, `onErrorContinue` và retry.
- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time và kiểm tra error signals.
- [Reactive Streams Specification](https://www.reactive-streams.org/): `Publisher`, `Subscriber`, `Subscription`, `onError` và cancellation.

> **Ghi nhớ:** xử lý lỗi **không chặn luồng** không có nghĩa che giấu lỗi. Hãy để `Mono`/`Flux` truyền `onError` đúng cách, phân loại HTTP/transport/domain errors, chọn retry/fallback có giới hạn, cô lập lỗi từng phần tử nếu phù hợp và tích hợp với `errorChannel` theo semantics endpoint. Với Spring Integration WebFlux, kết quả đáng tin cậy còn phụ thuộc message correlation, timeout, idempotency, ACK/commit và khả năng quan sát toàn bộ luồng.
