# Chọn WebFlux theo mô hình I/O và hệ sinh thái phụ thuộc

Một REST API tổng hợp dữ liệu từ PostgreSQL, tồn kho và dịch vụ định giá. Khi concurrency tăng, nhóm cân nhắc **Spring WebFlux** thay MVC. Nhưng nếu dependency vẫn dùng JDBC/JPA hay SDK đồng bộ, đổi controller thành **Mono** không biến I/O thành non-blocking. WebFlux có giá trị khi nhiều request đang chờ I/O thực sự bất đồng bộ.

Bài thuộc chương **Spring WebFlux** của **INTEGRATION_API_REST**, kết hợp hợp đồng HTTP, Java/Spring, bảo mật và kiểm thử. Trọng tâm là **quyết định chọn stack**, không phải đổi cú pháp.

## 1. Mục tiêu và nguyên tắc chọn công nghệ

Sau bài này, bạn có thể:

1. Phân biệt **mô hình thread-per-request** thường gặp ở Spring MVC với **event-loop/non-blocking I/O** của WebFlux.
2. Nhận diện workload **I/O-bound**, **CPU-bound**, streaming và những giới hạn từ connection pool, downstream.
3. Kiểm tra sự phù hợp của **JDBC/JPA, R2DBC, WebClient, SDK và message broker** trước khi quyết định stack.
4. Dùng **Mono, Flux, flatMap, zipWhen, boundedElastic** đúng ngữ cảnh; tránh chặn event loop và fan-out không giới hạn.
5. Thiết kế HTTP API reactive với authentication, tenant isolation, error mapping, timeout, backpressure và idempotency.
6. Đo và kiểm thử concurrency, cancellation, dữ liệu, quyền và hành vi khi dependency lỗi bằng **WebTestClient/StepVerifier**.

**Chọn WebFlux khi phần lớn thời gian chờ là I/O non-blocking, có nhu cầu concurrency/streaming và dependency phù hợp**. Với JPA/JDBC đồng bộ, **MVC vẫn hợp lý**.

## 2. Một HTTP request tiêu tốn tài nguyên thế nào?

### 2.1. MVC và WebFlux khác nhau ở cách chờ I/O

Spring MVC đồng bộ dùng **Servlet worker thread**: khi gọi JDBC/HTTP blocking, thread chờ response. Servlet cũng có async API, nhưng mô hình này thường giữ một worker cho mỗi request đang chạy.

WebFlux dựa trên **Reactive Streams**, chạy được trên **Reactor Netty** hoặc Servlet non-blocking. Event loop tiếp tục request khi I/O phát tín hiệu, thay vì giữ thread đợi mạng.

~~~mermaid
flowchart TB
    subgraph MVC["Spring MVC + blocking dependencies"]
        A["Request A"] --> TA["Worker A chờ JDBC"]
        B["Request B"] --> TB["Worker B chờ HTTP"]
        C["Request C"] --> TC["Worker C chờ HTTP"]
    end
    subgraph WEBFLUX["WebFlux + non-blocking dependencies"]
        R1["Request A/B/C"] --> E["Event loop"]
        E --> IO["R2DBC / WebClient async I/O"]
        IO --> E
    end
~~~

Sơ đồ chỉ minh họa. **WebFlux không tăng vô hạn throughput**: pool DB, rate limit, CPU, bộ nhớ và mạng vẫn là giới hạn.

### 2.2. Concurrency cao không đồng nghĩa CPU phải cao

Ở **1.000 request/giây**, thời gian trung bình **0,4 giây** tương ứng khoảng **400 request đồng thời** trong trạng thái ổn định (định luật Little). Non-blocking giúp khi chúng chủ yếu chờ I/O; nếu chủ yếu tính toán, **CPU vẫn là giới hạn**.

Đo **p95/p99, throughput, threads, CPU, GC, heap, pool và downstream throttling**; đừng benchmark “hello world”.

### 2.3. Reactive Streams và backpressure

**Mono<T>** phát tối đa một phần tử, **Flux<T>** phát 0..N. Subscriber truyền **demand** để publisher điều tiết tốc độ, giảm nguy cơ buffer không kiểm soát.

**Backpressure Reactor không tự lan end-to-end** qua mọi SDK/HTTP/broker. Response 100 MB hoặc nguồn không hỗ trợ demand vẫn cần giới hạn size, buffer và tốc độ.

## 3. Bảng quyết định: khi nào WebFlux có giá trị?

| Tình huống | Spring MVC | Spring WebFlux | Hướng chọn |
|---|---|---|---|
| CRUD nhỏ, JDBC/JPA đã ổn định | Rất phù hợp | Dễ thành reactive facade quanh DB blocking | **MVC** thường đơn giản hơn |
| Tổng hợp nhiều remote API có client non-blocking | Có thể dùng async nhưng quản lý phức tạp | Tốt cho composition/timeout/cancellation | **Cân nhắc WebFlux** |
| Hàng nghìn kết nối SSE/stream lâu sống | Có hỗ trợ streaming/async | Reactor pipeline và non-blocking thuận tiện | **WebFlux đáng thử** |
| CPU-bound: PDF render, nén, mã hóa | Cần executor riêng | Vẫn cần executor/worker riêng | Đừng chọn chỉ vì reactive |
| JPA entity graph, transaction imperative phức tạp | Thư viện hỗ trợ rộng | Trộn JPA vào event loop là sai | **MVC** hoặc tách service |
| Phần lớn SDK đối tác chỉ có blocking API | Dùng trực tiếp hợp lý | Phải isolate sang scheduler/pool | Phân tích chi phí chuyển đổi |
| Load thấp, team quen imperative | Dễ đọc/debug | Nhiều abstraction không cần thiết | **MVC** |
| Có R2DBC, WebClient và reactive security/data phù hợp | Vẫn có thể dùng client reactive | Reactive end-to-end khả thi | **WebFlux** là ứng viên mạnh |

**Không có công thức “X request/giây phải dùng WebFlux”**. Ngưỡng phụ thuộc thời gian chờ, cấu hình thread, tính chất dependency, memory budget và SLO. Quyết định dựa trên **benchmark giống production và toàn bộ dependency graph**, không chỉ controller.

### 3.1. Đừng bỏ qua MVC với virtual threads

Trên **Java 21+**, Spring Boot phiên bản tương thích có thể cấu hình virtual threads cho ứng dụng Servlet, giúp mã blocking dễ đọc mà giảm chi phí giữ platform thread khi chờ. Ví dụ cấu hình ở phiên bản hỗ trợ:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Virtual threads không làm JDBC/SDK thành non-blocking, không tăng DB connections hoặc xóa rate limit; chú ý pinning. So **MVC thường, MVC virtual threads và WebFlux** dưới cùng tải.

## 4. Audit hệ sinh thái phụ thuộc trước khi chuyển stack

**Câu hỏi đầu tiên không phải “controller trả Mono chưa?” mà là “mọi chặng I/O có chặn thread không?”**

| Thành phần | Hướng non-blocking/reactive | Điểm cần kiểm tra |
|---|---|---|
| HTTP client | **WebClient** / Reactor Netty hoặc connector async | Timeout, connection pool, TLS, circuit breaker |
| SQL | **Spring Data R2DBC** + driver R2DBC | DB/driver support, truy vấn/transaction, mapping khác JPA |
| SQL hiện hữu | **JDBC/JPA/Hibernate ORM** | **Blocking**; @Repository không làm thành reactive |
| MongoDB | Spring Data Reactive MongoDB khi dùng reactive driver | Không nhầm với synchronous MongoTemplate |
| Redis | ReactiveRedisTemplate với driver thích hợp | Các operation/pipeline dùng thật có non-blocking không |
| Messaging | Reactive connector được kiểm chứng hoặc adapter async | Consumer ack, demand và backpressure không tự tương đương |
| Cloud/payment SDK | Kiểm tra API client async thật | Nhiều API bọc CompletableFuture hoặc blocking; đo behavior |
| Cache / filesystem | Xem client API và driver cụ thể | Disk/file scan/serialization có thể vẫn blocking/CPU-heavy |
| Authentication | Spring Security WebFlux | Reactor Context, tenant và security propagation |
| Metrics/tracing | Micrometer Observation / Reactor integration | Context propagation và cardinality |

**R2DBC không phải JPA reactive**: khác persistence context, lazy-loading và transaction. Chuyển codebase JPA có chi phí đáng kể.

**WebClient dùng được trong MVC**. Khi có cả **spring-boot-starter-webflux** và **spring-boot-starter-web**, Boot thường chọn **MVC** mặc định; cần kiểm chứng application type. Import Mono không xác định runtime.

### 4.1. Audit theo đường đi thật của request

~~~text
GET /v1/products/{id}
  -> JWT verify                     CPU nhỏ
  -> PostgreSQL product lookup       JDBC blocking? hay R2DBC async?
  -> Inventory HTTP                  RestTemplate blocking? hay WebClient?
  -> Promotion rules                 CPU / cache / remote?
  -> JSON response                   serialize CPU
~~~

Ghi từng dependency: **blocking?**, latency p95/p99, connection giới hạn, khả năng cancellation, timeout, retry/idempotency, observability, thư viện thay thế và chi phí sửa. Một route có **một chặng JDBC blocking dài** vẫn có thể cần thread từ boundedElastic dù mọi đoạn còn lại trả Mono; throughput toàn hệ thống lúc đó tiếp tục phụ thuộc thread/connection của chặng blocking.

## 5. Tư duy lập trình Reactor: composition thay vì chờ kết quả

Trong WebFlux, handler thường **trả Publisher mô tả công việc**. Framework subscribe vào publisher để tạo response HTTP; code không cần tự gọi subscribe trong controller.

~~~java
// Reactive: mô tả pipeline, không chặn thread để lấy kết quả.
Mono<ProductView> result = products.findByIdAndTenantId(id, tenantId)
        .flatMap(product -> stockClient.load(tenantId, product.id())
                .map(stock -> new ProductView(
                        product.id(), product.name(), product.priceMinor(),
                        product.currency(), stock.available())));
return result;
~~~

Chọn operator theo ý nghĩa:

| Operator | Dùng khi | Rủi ro thường gặp |
|---|---|---|
| **map** | Biến đổi đồng bộ, ngắn, không trả publisher | Gọi JDBC, Thread.sleep hay API đồng bộ bên trong |
| **flatMap** | Hàm tạo Mono/Flux mới, I/O bất đồng bộ | Fan-out quá nhiều request nếu không giới hạn |
| **concatMap** | Cần xử lý tuần tự và giữ thứ tự trong một Flux | Throughput thấp hơn parallel nếu nghiệp vụ không cần thứ tự |
| **zip / zipWhen** | Kết hợp kết quả từ nhiều nguồn | Mono rỗng có thể làm zip không phát giá trị |
| **onErrorResume** | Phục hồi có chính sách khi lỗi | Che lỗi thành dữ liệu “thành công” sai lệch |
| **timeout** | Giới hạn thời gian chờ của một đoạn pipeline | Cancellation không bảo đảm external side effect rollback |
| **retryWhen** | Retry có giới hạn với lỗi đã phân loại | Lặp POST không idempotent, khuếch đại tải |
| **doOnNext/doOnError** | Ghi quan sát/log an toàn | Nhầm với nơi tạo side effect phải exactly-once |

Publisher “cold” thường chạy I/O khi subscribe; subscribe lại có thể gọi DB/HTTP lần nữa. Side effect ghi cần operation ID/idempotency.

### 5.1. Vì sao block() nguy hiểm ở event loop?

~~~java
// Anti-pattern bên trong WebFlux request pipeline:
ProductRow row = productRepository.findById(id).block();
~~~

**block()** chặn thread cho tới khi Mono kết thúc; trên thread non-blocking do Reactor quản lý, nó thường bị phát hiện và ném lỗi kiểu **IllegalStateException**. Dù một cấu hình cho phép chạy, nó loại bỏ lợi ích của event loop và có thể gây tắc nghẽn hoặc deadlock khi các tác vụ phụ thuộc vào cùng executor.

Cũng tránh **Thread.sleep**, JDBC/JPA, thư viện HTTP đồng bộ, đọc/ghi file lớn hoặc xử lý CPU nặng trực tiếp trong **map** của pipeline chạy trên event loop. Đừng nghĩ gắn **Mono.just(blockingCall())** là reactive: lời gọi blocking đã xảy ra **trước** khi Mono được tạo.

### 5.2. Nếu bắt buộc gọi thư viện blocking

Trong giai đoạn chuyển tiếp, có thể cô lập blocking I/O lên scheduler dành cho nó:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<LegacyRecord> record = Mono.fromCallable(
            () -> legacyJdbcClient.loadById(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

**fromCallable** trì hoãn lời gọi; **subscribeOn(boundedElastic)** chuyển việc chặn sang worker pool được giới hạn. Đây là giải pháp **bridge có chi phí**, không biến JDBC thành non-blocking. BoundedElastic có giới hạn threads/hàng đợi; nếu quá nhiều blocking call tích tụ, latency và memory vẫn tăng. Cần đo riêng saturation của scheduler và connection pool; với một route phần lớn blocking, có thể **giữ MVC** sẽ đơn giản, đáng tin hơn.

**publishOn** đổi scheduler của các tín hiệu từ chỗ đặt nó trở xuống; **subscribeOn** ảnh hưởng vị trí subscription của nguồn upstream. Không thêm scheduler ngẫu nhiên sau mọi map: context switching làm tăng chi phí và khó quan sát.

### 5.3. Giới hạn fan-out và dữ liệu trong bộ nhớ

~~~java
Flux<ProductView> views = Flux.fromIterable(productIds)
        .flatMap(id -> catalog.findVisible(tenantId, id), 8);
~~~

Thông số **8** ở đây giới hạn số publisher inner được subscribe đồng thời tại flatMap. Không đủ để thay **connection pool, HTTP rate limit và global concurrency limit**, nhưng là lớp kiểm soát ở pipeline. Nếu cần giữ thứ tự kết quả, dùng **flatMapSequential** hoặc **concatMap** theo yêu cầu. Tránh **collectList()** trên Flux không giới hạn số phần tử: nó giữ tất cả trong RAM, triệt tiêu lợi ích streaming.

## 6. Ví dụ REST API Spring WebFlux với phụ thuộc non-blocking

Tình huống: **GET /v1/products/{id}** đọc sản phẩm theo tenant từ PostgreSQL qua **R2DBC**, sau đó gọi tồn kho qua **WebClient**. Chỉ đọc dữ liệu của principal đã xác thực; resource ngoài tenant có thể được che bằng **404**. Ví dụ dùng Spring Boot 3, Java 17, Spring Data R2DBC và Spring Security reactive; code là các mảnh ghép phải tích hợp với schema/database/identity thực tế.

~~~http
GET /v1/products/41ea9158-1338-4868-ac5d-ac04b2c6c7c0 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "41ea9158-1338-4868-ac5d-ac04b2c6c7c0",
  "name": "Camera A",
  "priceMinor": 3590000,
  "currency": "VND",
  "available": 12
}
~~~

### 6.1. Reactive repository

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

@Table("products")
record ProductRow(
        @Id UUID id, UUID tenantId, String name,
        long priceMinor, String currency) {}

interface ProductRepository
        extends ReactiveCrudRepository<ProductRow, UUID> {
    Mono<ProductRow> findByIdAndTenantId(UUID id, UUID tenantId);
}

record StockView(long available) {}
record ProductView(
        UUID id, String name, long priceMinor,
        String currency, long available) {}
~~~

R2DBC driver phải hỗ trợ database và Spring Data mapping đã chọn. **ReactiveCrudRepository** trả Publisher, nhưng truy vấn phải được thiết kế để có index cho **tenant_id + id** và giới hạn connection pool; tên phương thức reactive **không** tự bảo đảm isolation hoặc authorization.

### 6.2. WebClient và service composition

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
class CatalogService {
    private final ProductRepository products;
    private final WebClient inventory;

    CatalogService(ProductRepository products,
            @Qualifier("inventoryWebClient") WebClient inventory) {
        this.products = products;
        this.inventory = inventory;
    }

    Mono<ProductView> findVisible(UUID tenant, UUID id) {
        return products.findByIdAndTenantId(id, tenant)
                .flatMap(row ->
                    inventory.get()
                        .uri("/v1/tenants/{tenant}/stock/{id}",
                                tenant, row.id())
                        .retrieve()
                        .bodyToMono(StockView.class)
                        .timeout(Duration.ofSeconds(2))
                        .map(stock -> new ProductView(
                                row.id(), row.name(),
                                row.priceMinor(), row.currency(),
                                stock.available())));
    }
}
~~~

Bean **inventoryWebClient** phải được cấu hình với **base URL đáng tin, TLS, giới hạn connection, timeout mạng, credential service-to-service**. Downstream phải xác minh tenant/resource tương ứng; một path có tenantId không tự bảo vệ dữ liệu. Timeout 2 giây ở đây là **giới hạn operator**, không thay connect/read timeout production.

### 6.3. Controller và security principal

~~~java
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/v1/products")
class CatalogController {
    private final CatalogService catalog;
    private final TenantResolver tenants;

    CatalogController(CatalogService catalog, TenantResolver tenants) {
        this.catalog = catalog;
        this.tenants = tenants;
    }

    @GetMapping("/{id}")
    Mono<ProductView> get(
            @PathVariable UUID id,
            @AuthenticationPrincipal Jwt jwt) {
        UUID tenant = tenants.resolveValidatedTenant(jwt);
        return catalog.findVisible(tenant, id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}

interface TenantResolver {
    UUID resolveValidatedTenant(Jwt jwt);
}
~~~

TenantResolver phải xác định tenant từ **JWT đã xác thực, có kiểm tra issuer/audience/claims**, không từ query/body client. Khi sản phẩm không thuộc tenant, lookup trả Mono.empty và API che resource bằng **404**; khi tồn kho downstream lỗi, **không** được tự biến lỗi đó thành 404 sản phẩm không tồn tại. Cần chuyển lỗi phụ thuộc sang HTTP **502/503/504** theo hop và loại lỗi, kèm Problem Details an toàn.

### 6.4. Cấu hình security reactive

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveApiSecurity {
    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET, "/v1/products/**")
                        .hasAuthority("SCOPE_catalog:read")
                    .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Code giả định OAuth2 resource server JWT và không cấu hình các chi tiết như CORS, CSRF policy, validation issuer/audience, rate limit và error handlers. Nếu dùng **cookie/session cho thao tác ghi**, vẫn cần đánh giá CSRF; không tắt CSRF bừa chỉ vì API dùng WebFlux. Scope ở route và **row-level tenant check** trong service bảo vệ **hai lớp khác nhau**.

## 7. Resilience và hợp đồng lỗi HTTP trong pipeline

**Non-blocking** không đồng nghĩa **không bao giờ timeout**. Client phải đặt **connect/response timeout** cho WebClient connector, service deadline tổng, connection pool và giới hạn retry. Operator **timeout(Duration)** bảo vệ một đoạn publisher; không thay cấu hình socket, chính sách tải hoặc hủy tác động ngoài hệ thống.

Ví dụ chuyển timeout đã biết thành lỗi có chủ đích:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<StockView> loadStock(Mono<StockView> remote) {
    return remote.timeout(Duration.ofSeconds(2))
            .onErrorMap(TimeoutException.class,
                    ex -> new InventoryTimeoutException());
}

class InventoryTimeoutException extends RuntimeException {}
~~~

Response theo **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/inventory-unavailable",
  "title": "Inventory is temporarily unavailable",
  "status": 503,
  "code": "INVENTORY_TIMEOUT"
}
~~~

**503** là lựa chọn có thể phù hợp nếu inventory tạm không phục vụ; tại gateway, upstream phản hồi lỗi không hợp lệ hoặc timeout còn có thể dẫn đến **502/504**. Đừng trả **404 PRODUCT_NOT_FOUND** khi DB tìm thấy product nhưng inventory bị timeout. Đừng gửi stack trace, URL nội bộ hoặc credentials trong ProblemDetail.

### 7.1. Retry phải phân loại request

~~~java
import reactor.util.retry.Retry;
import java.time.Duration;

Mono<StockView> retried = inventoryCall()
        .retryWhen(Retry.backoff(2, Duration.ofMillis(150))
                .jitter(0.5)
                .filter(this::isRetryableTransportOrUpstreamError));
~~~

Ví dụ giả định **inventoryCall()** và predicate **isRetryableTransportOrUpstreamError** được triển khai riêng; tối đa hai retry **sau lần gọi đầu**. Cần thêm **overall deadline** và retry budget, đồng thời tránh client/gateway/backend cùng retry làm nhân số attempt. GET thường idempotent nhưng vẫn không nên retry 400/401/403, hoặc gây retry storm khi upstream quá tải.

Với POST tạo đơn/hoàn tiền, **retryWhen** sẽ **subscribe lại**, có thể lặp side effect nếu server không có Idempotency-Key + unique operation record. Với GET dữ liệu có thể thay đổi giữa các attempt, kết quả cuối cũng không bảo đảm giống nhau. Không dùng **onErrorResume** để trả stock=0 giả tạo khi lỗi hạ tầng vì nó làm sai nghĩa nghiệp vụ.

### 7.2. Reactor Context và tracing

Trong reactive pipeline, xử lý có thể chuyển giữa các thread. **ThreadLocal** tự quản lý không còn là nơi an toàn để mặc định lấy principal, tenant hay trace ID; Spring Security reactive sử dụng **Reactor Context** cho SecurityContext. Dùng **@AuthenticationPrincipal**, **ReactiveSecurityContextHolder** hoặc cơ chế context propagation được framework hỗ trợ, không lấy authentication từ một ThreadLocal ngẫu nhiên trong map.

Mọi outbound call cần metadata tracing và service auth theo policy, nhưng **không log JWT, API key hoặc payload cá nhân**. Đặt metric theo route template, method và status, tránh label là raw productId/userId.

## 8. Database transaction reactive và tính nhất quán

Với **R2DBC**, transaction có thể được điều phối bằng **ReactiveTransactionManager** và **TransactionalOperator**. Khác với transaction imperative dựa trên thread-bound resource, transaction reactive gắn với **Reactor Context** của subscription.

~~~java
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

class StockReservation {
    private final DatabaseClient db;
    private final TransactionalOperator tx;

    StockReservation(DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    Mono<Long> reserve(UUID tenant, UUID product, long qty) {
        if (qty <= 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid quantity"));
        }
        return db.sql("""
                UPDATE inventory
                   SET available = available - :qty
                 WHERE tenant_id = :tenant
                   AND product_id = :product
                   AND available >= :qty
                """)
                .bind("qty", qty)
                .bind("tenant", tenant)
                .bind("product", product)
                .fetch().rowsUpdated()
                .flatMap(count -> count == 1
                    ? Mono.just(count)
                    : Mono.error(new ResponseStatusException(
                            HttpStatus.CONFLICT, "Insufficient stock")))
                .as(tx::transactional);
    }
}
~~~

Chỉ có một UPDATE trong ví dụ nên transaction ở đây nhằm minh họa reactive boundary; với nhiều thao tác liên quan, **tất cả phải nằm trong cùng pipeline/connection được quản lý**. Không trộn lời gọi JPA/JDBC và nghĩ nó tự tham gia R2DBC transaction. Spring có thể hỗ trợ **@Transactional** trên method trả reactive type khi cấu hình reactive transaction manager thích hợp; vẫn phải kiểm tra ranh giới subscription.

**Cạnh tranh phải được chặn tại DB** bằng conditional update, unique constraint hoặc optimistic locking. **Cancellation khi client ngắt kết nối không bảo đảm transaction hoặc tác động ngoài hệ thống chưa commit**. Với thao tác ghi, tiếp tục cần **operation identity/idempotency, outbox và đối soát** theo yêu cầu nghiệp vụ.

## 9. Streaming: khi Flux có lợi thế rõ hơn

Một endpoint **Server-Sent Events (SSE)** gửi các thay đổi trạng thái lâu dài:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

record EventView(String id, String type, String message) {}

interface AuthorizedEventFeed {
    Flux<EventView> streamForCurrentUser();
}

@RestController
class EventController {
    private final AuthorizedEventFeed feed;
    EventController(AuthorizedEventFeed feed) { this.feed = feed; }

    @GetMapping(value = "/v1/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<EventView>> events() {
        return feed.streamForCurrentUser()
                .map(item -> ServerSentEvent.<EventView>builder()
                        .id(item.id())
                        .event(item.type())
                        .data(item)
                        .build());
    }
}
~~~

**feed** phải áp dụng quyền của subscriber trong reactive security context và giới hạn dữ liệu theo tenant. Cần kiểm tra proxy có buffer SSE không, timeout/heartbeat, số kết nối đồng thời, memory, tốc độ client chậm và cơ chế replay **Last-Event-ID** nếu hợp đồng yêu cầu. Khi client ngắt, subscription thường bị cancel, nhưng nguồn message hoặc công việc đã chạy ở hệ thống khác có thể vẫn tiếp diễn.

Với danh sách REST thông thường, **Flux không thay pagination**. API collection lớn vẫn nên dùng **limit/cursor, Link next, max page size** và cache/ETag khi thích hợp. Streaming một tập dữ liệu vô hạn dưới một GET JSON bình thường thường gây khó cho client, gateway và observability; chọn SSE/NDJSON/streaming media type khi contract thực sự cần.

## 10. Kiểm thử, benchmark và quyết định triển khai

| Kiểm thử | Cách thực hiện | Bằng chứng |
|---|---|---|
| HTTP/auth | WebTestClient GET thiếu token, token sai scope | 401/403, không rò dữ liệu |
| Tenant isolation | ID sản phẩm thuộc tenant khác | 404, không gọi stock cho dữ liệu không được phép |
| Reactive composition | Mock R2DBC + HTTP downstream | StepVerifier xác nhận value, completion và error |
| Timeout | Giữ inventory không phản hồi | 503/Problem Details theo policy, không trả stock giả |
| Blocking detection | Tải cao và công cụ phát hiện blocking | Không JDBC/Thread.sleep trên event loop |
| Retry | Downstream 503/timeout, nhiều request đồng thời | Attempt/deadline có giới hạn, không retry storm |
| Slow client/stream | SSE client nhận chậm rồi disconnect | Memory ổn định, subscription/cancellation được quan sát |
| Load thực | So MVC, MVC virtual threads và WebFlux | Cùng SLO, dataset, pool và giới hạn downstream |

**WebTestClient** kiểm tra HTTP contract; **StepVerifier** kiểm tra hành vi Publisher. Ví dụ rút gọn, giả định các fixture, mock bean và security test context đã được cấu hình:

~~~java
@Test
void missingTokenIsRejected() {
    webTestClient.get().uri("/v1/products/{id}", productId)
            .exchange()
            .expectStatus().isUnauthorized();
}

@Test
void productPipelineCompletes() {
    StepVerifier.create(catalog.findVisible(tenantId, productId))
            .assertNext(p -> assertEquals("Camera A", p.name()))
            .verifyComplete();
}
~~~

Khi test **time/Retry.backoff**, dùng **virtual time** nếu phù hợp để không chờ thời gian thật; test cancellation và race cũng cần kiểm chứng tác động ở DB/downstream. Code trên là **đoạn test minh họa**, không phải test chạy độc lập. Benchmark phải đo thêm p95/p99, pool saturation, boundedElastic queue, heap/GC và CPU, không chỉ RPS.

## 11. Bài tập tình huống

Một API có **800 request/giây**, mỗi request đọc từ PostgreSQL, gọi hai HTTP service và trả JSON. 85% thời gian là chờ mạng; đội ngũ đang dùng **JPA, RestTemplate và SDK thanh toán blocking**. Dự kiến thêm SSE cho trạng thái đơn.

Hãy: **(1)** lập bản đồ dependency blocking/non-blocking; **(2)** đề xuất giữ MVC, MVC virtual threads hoặc chuyển WebFlux, kèm điều kiện; **(3)** nếu chuyển, chỉ ra chặng cần WebClient/R2DBC và chặng phải isolate; **(4)** mô tả bảo vệ tenant, timeout/retry POST và ít nhất năm test; **(5)** chọn metric go/no-go.

**Gợi ý:** WebFlux có triển vọng ở phần fan-out HTTP và SSE, nhưng **không có lợi thế end-to-end** nếu JPA/SDK blocking còn chiếm phần chính. Có thể giữ MVC cho checkout/PSP, tách SSE/aggregator thành service reactive sau benchmark, hoặc thử virtual threads trước khi thay persistence. Chỉ rollout khi latency, độ ổn định, security và chi phí vận hành đạt tiêu chí.

## 12. Checklist và tài liệu tham khảo

- [ ] Đã đo phần thời gian **chờ I/O** và kiểm kê mọi SDK/repository blocking.
- [ ] Đã so MVC, virtual threads và WebFlux trong điều kiện tải/giới hạn tương đương.
- [ ] Không gọi **block(), JDBC, Thread.sleep** trên event loop; boundedElastic có giới hạn.
- [ ] Có timeout, retry budget, cancellation policy, concurrency limit và resource pool.
- [ ] Reactive security giữ **tenant isolation** và context qua các operator.
- [ ] Ghi dữ liệu dùng reactive transaction phù hợp; POST có idempotency/đối soát.
- [ ] WebTestClient, StepVerifier, load test, lỗi downstream và slow client đều được kiểm chứng.

Tham khảo: **Spring WebFlux**, https://docs.spring.io/spring-framework/reference/web/webflux.html; **Spring Data R2DBC**, https://docs.spring.io/spring-data/relational/reference/r2dbc.html; **Project Reactor Reference**, https://projectreactor.io/docs/core/release/reference/; **Spring Security Reactive**, https://docs.spring.io/spring-security/reference/reactive/index.html; **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html.

**Kết luận:** WebFlux phù hợp khi **I/O thật sự non-blocking, concurrency/streaming đủ quan trọng và các dependency hỗ trợ**. Nếu phần lớn công việc vẫn chặn trên JDBC/JPA/SDK, chuyển controller sang Mono chỉ tăng độ phức tạp. Hãy chọn bằng **dependency audit, benchmark, security và kiểm thử sự cố**, không bằng tên framework.
