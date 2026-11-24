# Viết bộ lọc tùy biến có kiểm thử và không chặn event loop

Trong bài thực hành thuộc chương **Thực hành tổng hợp**, bạn sẽ tạo một bộ lọc toàn cục cho **Spring Cloud Gateway Server WebFlux**. Bộ lọc nhận diện hoặc tạo `X-Request-Id`, gắn ID vào request gửi tới dịch vụ phía sau và response trả về client. Sau đó, bạn viết kiểm thử để xác nhận filter chain tiếp tục chạy, header được truyền đúng và mã filter không thực hiện thao tác chặn trên Reactor non-blocking scheduler.

Gateway là cổng vào của microservices: route predicate chọn dịch vụ đích, filter chain xử lý request/response, còn các cơ chế như service discovery, xác thực, rate limiting, circuit breaker, retry, TLS và observability hỗ trợ vận hành. Một custom filter chạy trên mọi request phải đặc biệt nhẹ. Nếu gọi `.block()`, truy cập file đồng bộ, dùng JDBC hoặc chờ một HTTP call đồng bộ trên event loop, một request chậm có thể chiếm thread xử lý nhiều request khác.

## Mục tiêu và kết quả mong đợi

Sau khi hoàn thành, bạn có thể:

- Tạo `GlobalFilter` và đặt thứ tự thực thi bằng `Ordered`.
- Thay đổi request bất biến bằng `ServerHttpRequest.mutate()` và `ServerWebExchange.mutate()`.
- Truyền correlation ID qua Gateway tới upstream và trả lại ID trong response.
- Viết unit test cho filter bằng `MockServerWebExchange`, `StepVerifier` và JUnit.
- Dùng BlockHound để phát hiện một số lời gọi blocking trên Reactor non-blocking thread.
- Chuyển công việc blocking bắt buộc sang `Schedulers.boundedElastic()` hoặc thay bằng API reactive.

Kết quả cuối cùng là request `GET /api/orders/42` đi qua Gateway có header `X-Request-Id` hợp lệ ở cả request upstream và response gửi client. Bộ lọc không tự gọi I/O và luôn trả về `Mono<Void>` của filter chain.

## 1. Chuẩn bị project

Thực hành này dùng WebFlux vì mục tiêu là làm việc đúng với Reactor event loop. Ví dụ dùng Spring Cloud 2025.0 trở lên, trong đó starter và namespace đã phân biệt rõ Gateway Server WebFlux. Hãy chọn Spring Cloud BOM tương thích với phiên bản Spring Boot của project; không tự gắn một phiên bản Gateway riêng lẻ.

Thêm dependency vào Maven `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor.tools</groupId>
        <artifactId>blockhound</artifactId>
        <version>${blockhound.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Khai báo `blockhound.version` bằng phiên bản BlockHound tương thích với JDK và Reactor của project. Spring Boot BOM quản lý các dependency Spring Boot và Reactor phổ biến; BlockHound cần được quản lý phiên bản riêng nếu BOM đang dùng không quản lý nó.

Nếu project dùng release train cũ, tên starter và prefix cấu hình có thể khác. Đối chiếu tài liệu của đúng release train trước khi sao chép ví dụ.

## 2. Khai báo route thử nghiệm

Tạo route chuyển request đến một dịch vụ orders đang chạy ở cổng `9081`. Trong `application.yml`:

```yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:9081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
```

Với route này, request `GET /api/orders/42` được chuyển tới `http://localhost:9081/orders/42`. `StripPrefix=1` loại bỏ segment `/api`. `GlobalFilter` ở phần tiếp theo được áp dụng cho mọi route đang chạy trong Gateway, không cần khai báo tên filter trong route YAML.

Đảm bảo dịch vụ thử nghiệm có endpoint `GET /orders/42` và có thể trả về response đơn giản. Nếu chưa có service thật, có thể thay URI bằng một HTTP stub trong môi trường phát triển.

## 3. Viết RequestIdGlobalFilter

Tạo file `RequestIdGlobalFilter.java` trong package ứng dụng:

```java
package com.example.gateway.filter;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public final class RequestIdGlobalFilter implements GlobalFilter, Ordered {

    public static final String HEADER_NAME = "X-Request-Id";

    private static final Pattern SAFE_REQUEST_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String requestId = resolveRequestId(
                exchange.getRequest().getHeaders().getFirst(HEADER_NAME));

        ServerHttpRequest request = exchange.getRequest().mutate()
                .headers(headers -> headers.set(HEADER_NAME, requestId))
                .build();

        ServerWebExchange updatedExchange = exchange.mutate()
                .request(request)
                .build();

        // Response header được đặt trước khi response commit.
        updatedExchange.getResponse().getHeaders().set(HEADER_NAME, requestId);

        // Luôn trả về publisher của filter chain; không chờ kết quả đồng bộ.
        return chain.filter(updatedExchange);
    }

    private String resolveRequestId(String incomingId) {
        if (incomingId != null && SAFE_REQUEST_ID.matcher(incomingId).matches()) {
            return incomingId;
        }
        return UUID.randomUUID().toString();
    }

    @Override
    public int getOrder() {
        // Giá trị nhỏ hơn được thực thi sớm hơn trong pha request.
        return -100;
    }
}
```

Điểm cần chú ý:

- `GlobalFilter` chạy trên các route của Gateway. Nếu chỉ muốn áp dụng logic cho một số route, cân nhắc tạo `GatewayFilterFactory` thay vì một global filter.
- Request trong WebFlux là immutable. Dùng `mutate().build()` để tạo request mới rồi gắn request đó vào exchange mới.
- Header đầu vào chỉ được giữ nếu khớp tập ký tự an toàn và có độ dài tối đa 64 ký tự. Giá trị không hợp lệ được thay bằng UUID mới để tránh đưa chuỗi tùy ý vào log hoặc hệ thống quan sát.
- Response header được đặt trước khi response commit để client có thể đối chiếu request với log/trace downstream.
- Request ID chỉ phục vụ tương quan request. Không dùng header này làm danh tính người dùng, bằng chứng xác thực hoặc khóa phân quyền.
- `getOrder()` trả về `-100` để filter chạy sớm. Khi có nhiều filter, cần kiểm tra thứ tự tổng thể; pha response được xử lý theo chiều ngược lại đối với các filter có logic sau chain.

Filter chỉ thực hiện kiểm tra chuỗi, tạo UUID và biến đổi object request. Nó không gọi mạng, đọc file, truy cập database hay chờ thread khác.

## 4. Viết unit test cho filter

Tạo `RequestIdGlobalFilterTest.java` trong `src/test/java`:

```java
package com.example.gateway.filter;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import reactor.blockhound.BlockHound;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class RequestIdGlobalFilterTest {

    private final RequestIdGlobalFilter filter = new RequestIdGlobalFilter();

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }

    @Test
    void createsIdAndPassesMutatedExchangeToNextFilter() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42").build());
        var forwardedExchange = new AtomicReference<ServerWebExchange>();

        GatewayFilterChain chain = nextExchange -> {
            forwardedExchange.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain))
                .verifyComplete();

        assertThat(forwardedExchange.get()).isNotNull();
        String requestId = forwardedExchange.get().getRequest()
                .getHeaders().getFirst(RequestIdGlobalFilter.HEADER_NAME);

        assertThat(requestId).isNotBlank();
        assertThatCodeCanParseUuid(requestId);
        assertThat(forwardedExchange.get().getResponse().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME)).isEqualTo(requestId);

        // Exchange gốc không bị sửa trực tiếp.
        assertThat(exchange.getRequest().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME)).isNull();
    }

    @Test
    void preservesSafeIncomingId() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42")
                        .header(RequestIdGlobalFilter.HEADER_NAME, "req-42_A.b")
                        .build());
        var forwardedExchange = new AtomicReference<ServerWebExchange>();

        GatewayFilterChain chain = nextExchange -> {
            forwardedExchange.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain)).verifyComplete();

        assertThat(forwardedExchange.get().getRequest().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME)).isEqualTo("req-42_A.b");
    }

    @Test
    void replacesInvalidIncomingId() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42")
                        .header(RequestIdGlobalFilter.HEADER_NAME, "invalid request id")
                        .build());
        var forwardedExchange = new AtomicReference<ServerWebExchange>();

        GatewayFilterChain chain = nextExchange -> {
            forwardedExchange.set(nextExchange);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, chain)).verifyComplete();

        String requestId = forwardedExchange.get().getRequest().getHeaders()
                .getFirst(RequestIdGlobalFilter.HEADER_NAME);
        assertThat(requestId).isNotEqualTo("invalid request id");
        assertThatCodeCanParseUuid(requestId);
    }

    @Test
    void runsOnReactorNonBlockingScheduler() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/orders/42").build());
        var ranOnNonBlockingThread = new AtomicBoolean(false);

        GatewayFilterChain chain = nextExchange -> {
            ranOnNonBlockingThread.set(Schedulers.isInNonBlockingThread());
            return Mono.empty();
        };

        StepVerifier.create(Mono.defer(() -> filter.filter(exchange, chain))
                        .subscribeOn(Schedulers.parallel()))
                .verifyComplete();

        assertThat(ranOnNonBlockingThread).isTrue();
    }

    private static void assertThatCodeCanParseUuid(String value) {
        assertThat(UUID.fromString(value)).isNotNull();
    }
}
```

Các test dùng `StepVerifier` để subscribe và xác nhận publisher hoàn tất. Test cuối chạy filter trên `Schedulers.parallel()`, nơi Reactor đánh dấu thread là non-blocking; khi BlockHound đã cài đặt, các lời gọi blocking mà BlockHound nhận diện được trên thread này sẽ làm test thất bại. Test không thay thế kiểm thử tích hợp hoặc kiểm thử tải, nhưng giúp bắt sớm lỗi như `Thread.sleep`, một số thao tác file/socket đồng bộ và các API blocking phổ biến.

Nếu BlockHound không cài đặt được trong JVM kiểm thử, kiểm tra hướng dẫn tương thích instrumentation của phiên bản BlockHound/JDK đang dùng. Không bỏ qua lỗi instrumentation rồi coi test là đã xác nhận không blocking.

## 5. Chạy và quan sát thực hành

Khởi động dịch vụ orders trên `localhost:9081`, sau đó chạy Gateway. Gửi request không có request ID:

```bash
curl -i http://localhost:8080/api/orders/42
```

Response phải có header `X-Request-Id` chứa UUID. Kiểm tra log hoặc trace ở dịch vụ orders để xác nhận upstream cũng nhận được cùng header.

Gửi request với ID hợp lệ:

```bash
curl -i -H "X-Request-Id: lab-2026-42" \
  http://localhost:8080/api/orders/42
```

Gateway giữ `lab-2026-42` ở request upstream và response. Gửi một giá trị có khoảng trắng để xác nhận filter thay bằng UUID mới:

```bash
curl -i -H "X-Request-Id: invalid request id" \
  http://localhost:8080/api/orders/42
```

Chạy unit test bằng Maven:

```bash
mvn -Dtest=RequestIdGlobalFilterTest test
```

Nếu muốn xác nhận BlockHound thật sự bắt được blocking call, có thể tạo một test thử nghiệm riêng chạy `Thread.sleep(...)` trên `Schedulers.parallel()` và xác nhận publisher phát lỗi `BlockingOperationError`. Xóa test thử nghiệm hoặc giữ nó như test kiểm tra instrumentation có chủ đích; tuyệt đối không đưa lời gọi blocking đó vào filter production.

## 6. Những cách viết làm chặn event loop

Không viết các đoạn sau bên trong `GlobalFilter` hoặc callback đang chạy trên event loop:

```java
// Sai: chờ publisher hoàn tất ngay trên thread hiện tại.
String body = webClient.get()
        .uri("http://orders-service/health")
        .retrieve()
        .bodyToMono(String.class)
        .block();

// Sai: chặn thread trong lúc xử lý request.
Thread.sleep(100);

// Sai: chờ Future đồng bộ.
String result = future.get();
```

Thay vào đó, nối publisher vào chuỗi reactive:

```java
return webClient.get()
        .uri("http://orders-service/metadata")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(metadata -> {
            ServerHttpRequest request = exchange.getRequest().mutate()
                    .headers(headers -> headers.set("X-Service-Metadata", metadata))
                    .build();
            return chain.filter(exchange.mutate().request(request).build());
        });
```

Nếu bắt buộc gọi thư viện blocking cũ, bọc lời gọi trong publisher deferred và chuyển source sang `boundedElastic`:

```java
return Mono.fromCallable(() -> legacyClient.lookupMetadata(serviceId))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(metadata -> {
            ServerHttpRequest request = exchange.getRequest().mutate()
                    .headers(headers -> headers.set("X-Service-Metadata", metadata))
                    .build();
            return chain.filter(exchange.mutate().request(request).build());
        });
```

`Mono.fromCallable` trì hoãn lời gọi cho đến khi subscribe; `subscribeOn(Schedulers.boundedElastic())` đưa source blocking sang scheduler dành cho tác vụ blocking. Đừng gọi `legacyClient.lookupMetadata(...)` trước khi tạo `Mono`, vì khi đó lời gọi đã chạy ngay trên thread hiện tại. Cũng không dùng `publishOn` như cách sửa chung cho mọi blocking call: nó chuyển việc xử lý tín hiệu phía sau điểm đặt, nhưng không tự di chuyển một lời gọi đã thực thi trước khi publisher được tạo.

Ưu tiên thay JDBC hoặc HTTP client đồng bộ bằng R2DBC, `WebClient` hoặc API reactive tương ứng khi kiến trúc cho phép. `boundedElastic` là vùng cách ly cho legacy blocking, không phải lý do để biến toàn bộ Gateway thành chuỗi tác vụ chờ đồng bộ. Đặt timeout, giới hạn concurrency và theo dõi queue của scheduler để tránh làm cạn tài nguyên khi upstream chậm.

## 7. Checklist hoàn tất

- [ ] Gateway dùng đúng starter WebFlux và Spring Cloud BOM tương thích.
- [ ] Route `/api/orders/**` chuyển request tới đúng upstream và rewrite path chính xác.
- [ ] `X-Request-Id` được tạo khi thiếu hoặc sai định dạng; ID hợp lệ được giữ nguyên.
- [ ] Request upstream và response client có cùng request ID.
- [ ] Unit test xác nhận exchange được mutate, chain được gọi và publisher hoàn tất.
- [ ] BlockHound được cài đặt thành công và test chạy trên Reactor non-blocking scheduler.
- [ ] Không có `.block()`, `Future.get()`, `Thread.sleep`, JDBC hoặc I/O đồng bộ trong đường xử lý event loop.
- [ ] Tác vụ blocking bắt buộc được cô lập bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và có giới hạn phù hợp.
- [ ] Header correlation không được dùng thay cho xác thực hoặc phân quyền.

## Tài liệu tham khảo

- [Spring Cloud Gateway — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): vòng đời, thứ tự và cách kết hợp global filter với filter theo route.
- [Spring Cloud Gateway — Writing Custom Route Predicate Factories and GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/writing-custom-route-predicate-factories-and-gatewayfilter-factories.html): cách mở rộng filter theo route.
- [Project Reactor — Blocking Can Be Caught](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): hướng dẫn cô lập lời gọi blocking bằng `fromCallable` và `boundedElastic`.
- [BlockHound](https://github.com/reactor/BlockHound): công cụ phát hiện blocking call trên thread không cho phép blocking.

Bộ lọc tùy biến tốt giữ phần xử lý trên event loop ngắn, không chờ I/O đồng bộ và trả lại publisher của Gateway filter chain. Hãy dùng unit test để khóa hành vi của header và exchange, dùng BlockHound để phát hiện blocking phổ biến, rồi kiểm thử tích hợp với upstream để xác nhận request thực tế đi qua Gateway đúng như thiết kế.
