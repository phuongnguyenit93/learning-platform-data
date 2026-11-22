# ExchangeFilterFunction và chuỗi filter phía khách trong Spring WebFlux

## 1. Vai trò của ExchangeFilterFunction

`WebClient` là HTTP client reactive của Spring WebFlux. Ứng dụng thường cần áp dụng cùng một số xử lý cho nhiều request: gắn access token, thêm correlation ID, ghi log, đo latency, chuẩn hóa header, ánh xạ lỗi hoặc làm mới token.

`ExchangeFilterFunction` cho phép đóng gói các xử lý đó thành filter rồi đăng ký trên `WebClient.Builder`. Filter nằm giữa code gọi WebClient và `ExchangeFunction` thực hiện HTTP exchange.

~~~text
Service / Repository
       |
       v
WebClient fluent API
       |
       v
Filter A -> Filter B -> Filter C
       |
       v
ExchangeFunction
       |
       v
ClientHttpConnector
       |
       v
HTTP client / Network
       |
       v
ClientResponse
       |
       v
Filter C -> Filter B -> Filter A
       |
       v
retrieve() / exchangeToMono()
       |
       v
Mono<T> / Flux<T>
~~~

Filter can thiệp ở tầng logical request/response. Connection pool, TLS, proxy, socket timeout và HTTP transport vẫn thuộc client connector.

## 2. Hợp đồng của filter

### 2.1. Functional interface

`ExchangeFilterFunction` nằm trong package:

~~~java
org.springframework.web.reactive.function.client.ExchangeFilterFunction
~~~

Phương thức chính:

~~~java
Mono<ClientResponse> filter(
    ClientRequest request,
    ExchangeFunction next
);
~~~

- `request` là request hiện tại, gồm method, URL, headers, attributes và body inserter.
- `next` là bước tiếp theo trong chuỗi; ở cuối chuỗi, nó thực hiện HTTP exchange qua connector.
- Giá trị trả về là Publisher chứa `ClientResponse` hoặc phát error signal.
- Filter chỉ chạy khi Publisher được subscribe.

Filter pass-through:

~~~java
ExchangeFilterFunction passThrough =
    (request, next) -> next.exchange(request);
~~~

### 2.2. Những việc filter có thể làm

1. Thay đổi request rồi gọi `next.exchange(modifiedRequest)`.
2. Quan sát request trước khi gửi.
3. Quan sát response bằng `doOnNext` hoặc `flatMap`.
4. Trả response khác nếu hợp đồng ứng dụng cho phép.
5. Phát lỗi mà không gửi request.
6. Đọc, tiêu thụ hoặc release response body.
7. Gửi lại request theo chính sách retry/refresh có giới hạn.

Filter phù hợp cho concern dùng chung ở biên HTTP client. Business rule của use case nên nằm trong service/domain layer.

## 3. Thứ tự trong filter chain

### 3.1. Đăng ký filter

~~~java
WebClient client = WebClient.builder()
    .filter(filterA)
    .filter(filterB)
    .filter(filterC)
    .build();
~~~

`WebClient.Builder.filter` thêm filter vào cuối danh sách. Nếu thứ tự đăng ký là A, B, C:

- Request đi: A → B → C → connector.
- Response quay về: connector → C → B → A.

Filter A là lớp ngoài cùng. Nó gọi B qua `next`; B gọi C; C gọi connector. Khi response trở về, mỗi filter có thể xử lý response trước khi trả cho lớp bao ngoài.

### 3.2. Quan sát thứ tự bằng code

~~~java
ExchangeFilterFunction first = (request, next) -> {
    log.info("A: request");
    return next.exchange(request)
        .doOnNext(response -> log.info("A: response"));
};

ExchangeFilterFunction second = (request, next) -> {
    log.info("B: request");
    return next.exchange(request)
        .doOnNext(response -> log.info("B: response"));
};

WebClient client = WebClient.builder()
    .filter(first)
    .filter(second)
    .build();
~~~

Log theo thứ tự:

~~~text
A: request
B: request
B: response
A: response
~~~

### 3.3. andThen, chèn và xóa filter

`ExchangeFilterFunction.andThen` tạo filter kết hợp, trong đó filter hiện tại được áp dụng trước filter được truyền vào:

~~~java
ExchangeFilterFunction combined = filterA.andThen(filterB);
~~~

Có thể thay đổi thứ tự danh sách bằng `filters`:

~~~java
WebClient client = WebClient.builder()
    .filter(loggingFilter)
    .filter(metricsFilter)
    .filters(filters -> filters.add(0, requestIdFilter))
    .build();
~~~

`add(0, ...)` đặt filter ở đầu chuỗi. Hãy cấu hình danh sách trước khi build client.

## 4. Thay đổi ClientRequest

### 4.1. Request là immutable

Không sửa trực tiếp request. Tạo bản sao bằng `ClientRequest.from(request)`:

~~~java
ExchangeFilterFunction addHeader = (request, next) -> {
    ClientRequest updated = ClientRequest.from(request)
        .headers(headers ->
            headers.set("X-Client-Name", "catalog-service"))
        .build();

    return next.exchange(updated);
};
~~~

`headers.set` thay giá trị hiện tại. Phương thức `header(name, value)` có thể thêm giá trị mới vào header đã tồn tại. Request mới giữ method, URL, body inserter và attributes nếu không thay đổi chúng.

### 4.2. ofRequestProcessor

~~~java
ExchangeFilterFunction userAgentFilter =
    ExchangeFilterFunction.ofRequestProcessor(request -> {
        ClientRequest updated = ClientRequest.from(request)
            .headers(headers ->
                headers.set(HttpHeaders.USER_AGENT, "orders-client/1.0"))
            .build();

        return Mono.just(updated);
    });
~~~

`ofRequestProcessor` biến một hàm xử lý `ClientRequest` thành filter chỉ tập trung vào request.

### 4.3. Áp dụng có điều kiện

~~~java
ExchangeFilterFunction conditionalHeader = (request, next) -> {
    if (request.url().getPath().startsWith("/internal/")) {
        ClientRequest updated = ClientRequest.from(request)
            .headers(headers ->
                headers.set("X-Internal-Client", "true"))
            .build();

        return next.exchange(updated);
    }

    return next.exchange(request);
};
~~~

Với quy tắc theo use case, request attribute thường rõ ràng hơn việc kiểm tra URL bằng chuỗi quá rộng.

## 5. Request attributes và Reactor Context

### 5.1. Attribute không phải HTTP header

`ClientRequest` có attributes để truyền metadata nội bộ giữa caller và filter. Attribute không tự trở thành HTTP header và không được gửi qua network.

Caller gắn request ID và operation name:

~~~java
client.get()
    .uri("/products/{id}", id)
    .attribute("requestId", requestId)
    .attribute("operationName", "product.lookup")
    .retrieve()
    .bodyToMono(Product.class);
~~~

Filter đọc attribute rồi chuyển request ID thành header:

~~~java
ExchangeFilterFunction requestIdFilter = (request, next) -> {
    String requestId = request.attribute("requestId")
        .map(String::valueOf)
        .orElseGet(() -> UUID.randomUUID().toString());

    ClientRequest updated = ClientRequest.from(request)
        .headers(headers -> headers.set("X-Request-Id", requestId))
        .build();

    return next.exchange(updated);
};
~~~

Đây là cách truyền metadata theo từng request mà không lưu request ID trong field mutable của singleton filter.

### 5.2. Khi nào dùng Reactor Context?

Reactor Context phù hợp khi metadata cần truyền xuyên qua nhiều Publisher và được đọc ở nhiều điểm trong reactive chain. Request attribute phù hợp khi filter cần đọc metadata từ chính ClientRequest.

Không dùng ThreadLocal để truyền request ID trong ứng dụng reactive: callback có thể chạy trên thread khác và nhiều request có thể xen kẽ trên cùng thread.

## 6. Xử lý ClientResponse

### 6.1. ofResponseProcessor

~~~java
ExchangeFilterFunction responseStatusFilter =
    ExchangeFilterFunction.ofResponseProcessor(response -> {
        log.info("Downstream returned {}", response.statusCode());
        return Mono.just(response);
    });
~~~

Filter chỉ quan sát status và trả nguyên response cho WebClient xử lý tiếp. Nó không đọc body nên caller vẫn có thể decode body.

### 6.2. Đo latency

~~~java
ExchangeFilterFunction timingFilter = (request, next) -> {
    long started = System.nanoTime();

    return next.exchange(request)
        .doOnNext(response -> {
            long elapsedMs =
                (System.nanoTime() - started) / 1_000_000;

            log.info("HTTP {} completed with {} in {} ms",
                request.method(), response.statusCode(), elapsedMs);
        });
};
~~~

`doOnNext` chỉ quan sát response. Body vẫn được chuyển xuống caller, nơi `retrieve()` hoặc `exchangeToMono()` quyết định cách decode.

### 6.3. Status 4xx/5xx

Khi filter trả response nguyên vẹn, `retrieve()` áp dụng status handler của nó; mặc định status 4xx/5xx được chuyển thành `WebClientResponseException`.

Nếu dùng `exchangeToMono` hoặc `exchangeToFlux`, caller trực tiếp kiểm tra status và chọn cách decode hoặc phát lỗi.

Spring có tiện ích `ExchangeFilterFunctions.statusError`:

~~~java
ExchangeFilterFunction serverErrorFilter =
    ExchangeFilterFunctions.statusError(
        HttpStatusCode::is5xxServerError,
        response -> new DownstreamServiceException(
            "Downstream service returned a server error")
    );
~~~

`DownstreamServiceException` là exception do ứng dụng định nghĩa. Chỉ dùng filter này khi muốn áp dụng chính sách lỗi chung cho mọi request của client. Nếu từng endpoint cần diễn giải status khác nhau, xử lý ở service sẽ linh hoạt hơn.

## 7. Response body ownership

### 7.1. Filter phải tiêu thụ hoặc chuyển tiếp body

`ClientResponse` có body stream. Khi filter xử lý response, nó phải:

- Tiêu thụ body hoàn toàn nếu filter chịu trách nhiệm đọc body.
- Release body nếu không cần nội dung.
- Hoặc trả nguyên response để code downstream tiếp tục tiêu thụ.

Không được đọc body trong filter rồi trả nguyên response như thể body vẫn còn nguyên. Body là stream có thể chỉ tiêu thụ một lần.

### 7.2. Đọc body để log rồi trả response là sai

Ví dụ sai:

~~~java
return next.exchange(request)
    .flatMap(response ->
        response.bodyToMono(String.class)
            .doOnNext(body -> log.info("body={}", body))
            .thenReturn(response)
    );
~~~

Filter đã tiêu thụ body thành String. Khi caller tiếp tục gọi `bodyToMono` để decode DTO, body không còn để đọc; có thể gặp body rỗng hoặc lỗi.

Log toàn bộ response body còn có thể làm lộ token, dữ liệu cá nhân hoặc payload lớn. Hãy ưu tiên log status, latency, request ID và error code đã chuẩn hóa.

### 7.3. Bỏ body thì phải release

Nếu filter quyết định bỏ response và không chuyển cho caller:

~~~java
return next.exchange(request)
    .flatMap(response -> {
        if (response.statusCode().is3xxRedirection()) {
            return response.releaseBody()
                .then(Mono.error(
                    new IllegalStateException("Redirect is not allowed")));
        }

        return Mono.just(response);
    });
~~~

`releaseBody` tiêu thụ/giải phóng body để connection và buffer có thể được tái sử dụng đúng cách.

### 7.4. Đọc body rồi tạo response mới

Nếu thật sự cần kiểm tra body và vẫn muốn downstream đọc lại, phải đọc một lần rồi xây response mới:

~~~java
return next.exchange(request)
    .flatMap(response ->
        response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> ClientResponse.from(response)
                .body(body)
                .build())
    );
~~~

Đây là ví dụ cho body nhỏ. Nó aggregate toàn bộ response thành String, làm tăng memory usage và có thể thay đổi cách xử lý charset/streaming. Không dùng cho file lớn, NDJSON vô hạn hoặc response streaming.

### 7.5. exchangeToMono và exchangeToFlux

~~~java
Mono<Product> product = client.get()
    .uri("/products/{id}", id)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Product.class);
        }

        return response.createError();
    });
~~~

Sau khi Publisher được trả về từ callback kết thúc, Spring kiểm tra body response. Nếu body chưa được tiêu thụ, framework release nó để tránh memory/connection leak. Vì vậy không thể giữ response rồi cố decode body ở bước downstream sau khi callback đã kết thúc.

## 8. Authentication và token refresh

### 8.1. Gắn Bearer token

Một token provider có thể trả token bất đồng bộ:

~~~java
public interface TokenProvider {
    Mono<String> currentAccessToken();
}
~~~

Filter gắn Bearer token:

~~~java
ExchangeFilterFunction bearerTokenFilter(TokenProvider tokens) {
    return (request, next) ->
        tokens.currentAccessToken()
            .map(token -> ClientRequest.from(request)
                .headers(headers -> headers.setBearerAuth(token))
                .build())
            .flatMap(next::exchange);
}
~~~

Token được lấy trong reactive pipeline, không cần block chờ. Nếu request đã có Authorization header đặc biệt, hãy xác định rõ filter có được phép ghi đè hay không. Không log token.

### 8.2. Basic authentication

~~~java
WebClient client = WebClient.builder()
    .filter(ExchangeFilterFunctions.basicAuthentication(
        "service-user", "service-password"))
    .build();
~~~

Thông tin đăng nhập phải lấy từ secret manager hoặc cấu hình bảo mật. Không hardcode credential trong source code hoặc log.

### 8.3. Refresh token khi gặp 401

Mẫu dưới đây release response body 401, lấy token mới, rồi gửi lại request một lần qua các filter phía sau:

~~~java
ExchangeFilterFunction refreshOnUnauthorized(
    TokenProvider tokens
) {
    return (request, next) -> next.exchange(request)
        .flatMap(response -> {
            if (response.statusCode().value()
                    != HttpStatus.UNAUTHORIZED.value()) {
                return Mono.just(response);
            }

            return response.releaseBody()
                .then(tokens.refreshAccessToken())
                .flatMap(token -> {
                    ClientRequest retryRequest =
                        ClientRequest.from(request)
                            .headers(headers ->
                                headers.setBearerAuth(token))
                            .build();

                    return next.exchange(retryRequest);
                });
        });
}
~~~

Interface provider:

~~~java
public interface TokenProvider {
    Mono<String> currentAccessToken();
    Mono<String> refreshAccessToken();
}
~~~

Khi đưa vào production, cần bổ sung:

- Chỉ refresh cho request có cơ chế authentication phù hợp.
- Không lặp refresh vô hạn nếu lần gửi lại vẫn nhận 401.
- Đồng bộ refresh khi nhiều request cùng hết hạn token.
- Dùng client riêng cho token endpoint để tránh filter refresh tự gọi lại chính nó.
- Xử lý refresh token hết hạn và lỗi xác thực.
- Không gửi lại request body dạng stream một lần nếu body không thể replay.
- Chỉ retry thao tác ghi khi có idempotency key hoặc cơ chế chống thực hiện trùng.

`next` bên trong filter đại diện cho phần chuỗi nằm phía sau filter hiện tại. Gọi `next.exchange(retryRequest)` không chạy lại chính filter hiện tại, nhưng vẫn đi qua các filter phía sau nó.

## 9. Logging, tracing và observability

### 9.1. Log metadata thay vì body

Một filter logging nên tập trung vào HTTP method, tên operation/route template, request ID, response status, thời gian xử lý và loại exception nếu exchange thất bại.

~~~java
ExchangeFilterFunction safeLoggingFilter() {
    return (request, next) -> {
        String operation = request.attribute("operationName")
            .map(String::valueOf)
            .orElse("outbound-http");

        String requestId = request.headers()
            .getFirst("X-Request-Id");

        long started = System.nanoTime();

        log.debug("Outbound {} operation={} requestId={}",
            request.method(), operation, requestId);

        return next.exchange(request)
            .doOnNext(response -> {
                long elapsed =
                    (System.nanoTime() - started) / 1_000_000;

                log.info("Outbound operation={} status={} elapsedMs={}",
                    operation, response.statusCode(), elapsed);
            })
            .doOnError(error ->
                log.warn("Outbound operation={} failed with {}",
                    operation, error.getClass().getSimpleName()));
    };
}
~~~

Không log query string, request body, response body, cookie hoặc Authorization header theo mặc định. URL có thể chứa email, token hoặc mã tài khoản; dùng operation name/route template để tránh đưa dữ liệu nhạy cảm vào log.

### 9.2. Micrometer Observation

Spring hỗ trợ observation cho WebClient thông qua `ObservationRegistry`. Khi đã dùng Micrometer Observation và tracing phù hợp, ưu tiên cơ chế chuẩn để thu thập metric/span thay vì tự tạo hệ thống log/trace riêng trong mọi filter.

Tránh metric tag có cardinality cao như user ID, order ID, full URL hoặc exception message.

### 9.3. Không dùng ThreadLocal

Filter là singleton dùng chung giữa nhiều request. Không đặt request ID, user hoặc token hiện tại vào field mutable. Hãy lấy dữ liệu từ request attribute, Reactor Context hoặc provider thread-safe.

## 10. Error handling, timeout và retry

### 10.1. Filter có thể short-circuit

Nếu filter không gọi `next.exchange`, HTTP request sẽ không được gửi:

~~~java
ExchangeFilterFunction blockDisallowedHost = (request, next) -> {
    if (request.url().getHost().equals("blocked.example")) {
        return Mono.error(
            new IllegalArgumentException("Host is not allowed"));
    }

    return next.exchange(request);
};
~~~

Đây là cơ chế có thể dùng để chặn host theo policy. Trong ứng dụng thực tế, hãy chuẩn hóa hostname và xem xét redirect, DNS rebinding cùng cấu hình proxy khi policy bảo mật yêu cầu.

### 10.2. Retry chỉ cho lỗi có thể phục hồi

Không retry mọi exception. Một số lỗi DNS tạm thời hoặc connection reset có thể phục hồi; 400, 401 chưa refresh, 404 nghiệp vụ hoặc validation failure thường không có ích khi gửi lại nguyên request.

~~~java
return client.get()
    .uri("/catalog/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransientFailure)
    );
~~~

Hàm `isTransientFailure` phải được ứng dụng định nghĩa dựa trên exception/status thực tế. Hai lần retry có nghĩa tối đa ba lần thực hiện gồm lần đầu.

Đặt retry ở service/use case thường dễ đánh giá tính idempotent và deadline hơn. Nếu retry nằm trong filter, policy có thể vô tình áp dụng cho cả request đăng nhập, upload, payment và các thao tác ghi khác.

### 10.3. Request body không replayable

Request body có thể là Publisher được tạo một lần, file stream hoặc dữ liệu từ nguồn không thể đọc lại. Gửi lại request không đồng nghĩa body có thể phát lại.

Trước khi retry, xác minh body có thể được tạo lại, server chưa thực hiện side effect, thao tác ghi có idempotency key, retry có giới hạn và caller vẫn còn chờ response.

### 10.4. Timeout thuộc nhiều tầng

| Loại timeout | Nơi cấu hình thường gặp |
| --- | --- |
| DNS/connect timeout | HTTP client connector |
| Response/read timeout | Reactor Netty hoặc connector tương ứng |
| Timeout toàn Publisher | Reactor `timeout` |
| Deadline nghiệp vụ | Service/use case |
| Idle timeout của proxy | Reverse proxy/API gateway |

Filter có thể thêm timeout vào Publisher, nhưng timeout kết nối và TLS handshake cần cấu hình ở connector. Không dùng một timeout duy nhất để thay thế mọi giới hạn.

## 11. WebClient immutable, Builder và mutate

### 11.1. WebClient sau khi build là immutable

Sau khi gọi `build()`, WebClient có cấu hình bất biến và có thể dùng chung trong singleton service. Không tạo client mới cho từng request nếu không có lý do đặc biệt vì có thể làm mất lợi ích tái sử dụng connection pool và cấu hình chung.

### 11.2. Tạo client dẫn xuất bằng mutate

~~~java
WebClient baseClient = WebClient.builder()
    .filter(requestIdFilter)
    .filter(loggingFilter)
    .build();

WebClient authenticatedClient = baseClient.mutate()
    .filter(bearerTokenFilter)
    .build();
~~~

`authenticatedClient` kế thừa cấu hình của `baseClient` và thêm filter. Client gốc không bị thay đổi.

Có thể chèn filter ở vị trí cụ thể:

~~~java
WebClient clientWithAuthFirst = baseClient.mutate()
    .filters(filters -> filters.add(0, bearerTokenFilter))
    .build();
~~~

Vị trí filter ảnh hưởng thứ tự request và response; hãy kiểm thử khi thay đổi chuỗi.

### 11.3. Khi nào tạo nhiều WebClient?

Có thể tạo client riêng theo dependency hoặc security boundary:

- Catalog API: base URL, token và timeout riêng.
- Payment API: credential, retry và idempotency policy riêng.
- Public API: không mang credential nội bộ.
- Token endpoint: client riêng để tránh refresh filter tự gọi vòng lặp.

Các client có thể dùng chung connector hoặc connection provider nếu cấu hình phù hợp, nhưng không nên dùng chung header/credential giữa các trust boundary khác nhau.

## 12. Filter và các điểm mở rộng khác của WebClient

| Cơ chế | Dùng khi nào? |
| --- | --- |
| `ExchangeFilterFunction` | Xử lý cross-cutting concern ở logical request/response |
| `defaultHeader` / `defaultRequest` | Header hoặc request customization mặc định đơn giản |
| `retrieve().onStatus(...)` | Ánh xạ status thành exception ở một request |
| `exchangeToMono` / `exchangeToFlux` | Cần kiểm soát decode theo status/header |
| `ClientHttpConnector` | Cấu hình HTTP engine, TLS, proxy và transport |
| `ExchangeStrategies` / codec config | Điều chỉnh encode/decode và memory limit |
| `Micrometer Observation` | Metric, trace và observation chuẩn |

Đừng dùng filter để giải quyết việc mà connector hoặc codec đã có extension point phù hợp. Ví dụ, thay đổi trust store TLS nên cấu hình HTTP client connector; filter chỉ nhìn thấy request/response ở tầng cao hơn.

## 13. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Ứng dụng dưới đây có hai endpoint:

- `GET /internal/greetings/{name}`: endpoint mô phỏng dịch vụ downstream.
- `GET /api/greetings/{name}`: gọi endpoint nội bộ qua WebClient có request ID filter và logging filter.

Một integration test dùng MockWebServer xác minh thứ tự filter và request attribute.

### 13.1. Cấu trúc project

~~~text
webclient-filter-demo/
├── pom.xml
├── src/main/resources/
│   └── application.properties
├── src/main/java/example/webclient/
│   ├── WebClientFilterApplication.java
│   ├── WebClientConfiguration.java
│   ├── ClientFilters.java
│   ├── GreetingService.java
│   ├── GreetingController.java
│   └── GreetingResponse.java
└── src/test/java/example/webclient/
    └── ExchangeFilterFunctionTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-filter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. application.properties

~~~properties
server.port=8080
logging.level.example.webclient=INFO
~~~

Khi triển khai nhiều service, thay base URL localhost bằng URL của downstream service thực tế. Giá trị localhost chỉ phục vụ demo chạy một process.

### 13.4. WebClientFilterApplication.java

~~~java
package example.webclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebClientFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebClientFilterApplication.class, args);
    }
}
~~~

### 13.5. GreetingResponse.java

~~~java
package example.webclient;

public record GreetingResponse(
    String message,
    String requestId
) {}
~~~

### 13.6. ClientFilters.java

~~~java
package example.webclient;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;

public final class ClientFilters {

    private static final Logger log =
        LoggerFactory.getLogger(ClientFilters.class);

    private ClientFilters() {
    }

    public static ExchangeFilterFunction requestId() {
        return (request, next) -> {
            String requestId = request.attribute("requestId")
                .map(String::valueOf)
                .orElseGet(() -> UUID.randomUUID().toString());

            ClientRequest updated = ClientRequest.from(request)
                .headers(headers ->
                    headers.set("X-Request-Id", requestId))
                .build();

            return next.exchange(updated);
        };
    }

    public static ExchangeFilterFunction safeLogging() {
        return (request, next) -> {
            String operation = request.attribute("operationName")
                .map(String::valueOf)
                .orElse("outbound-http");

            String requestId = request.headers()
                .getFirst("X-Request-Id");

            long started = System.nanoTime();

            log.debug("Outbound {} operation={} requestId={}",
                request.method(), operation, requestId);

            return next.exchange(request)
                .doOnNext(response -> {
                    long elapsedMs =
                        (System.nanoTime() - started) / 1_000_000;

                    log.info(
                        "Outbound operation={} status={} elapsedMs={}",
                        operation, response.statusCode(), elapsedMs);
                })
                .doOnError(error ->
                    log.warn(
                        "Outbound operation={} failed with {}",
                        operation,
                        error.getClass().getSimpleName()));
        };
    }
}
~~~

Filter `requestId()` tạo hoặc lấy request ID từ attribute, sau đó đặt header bằng `headers.set` để tránh nhân đôi giá trị. Filter `safeLogging()` ghi method, operation, status và latency; nó không đọc body hoặc log credential.

### 13.7. WebClientConfiguration.java

~~~java
package example.webclient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    WebClient greetingWebClient(
        WebClient.Builder builder,
        @Value("${demo.remote-base-url:http://localhost:8080}") String baseUrl
    ) {
        return builder
            .baseUrl(baseUrl)
            .filter(ClientFilters.requestId())
            .filter(ClientFilters.safeLogging())
            .build();
    }
}
~~~

Spring Boot cung cấp `WebClient.Builder` được cấu hình theo application context. Mỗi lần `filter` được gọi, filter được thêm vào cuối chuỗi. Client sau khi build được inject và tái sử dụng.

### 13.8. GreetingService.java

~~~java
package example.webclient;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    private final WebClient client;

    public GreetingService(WebClient greetingWebClient) {
        this.client = greetingWebClient;
    }

    public Mono<GreetingResponse> greet(String name) {
        String requestId = UUID.randomUUID().toString();

        return client.get()
            .uri("/internal/greetings/{name}", name)
            .attribute("requestId", requestId)
            .attribute("operationName", "greeting.lookup")
            .retrieve()
            .bodyToMono(GreetingResponse.class);
    }
}
~~~

Service không tự thêm header `X-Request-Id`. Nó truyền metadata bằng request attribute; filter chịu trách nhiệm chuyển attribute thành HTTP header.

### 13.9. GreetingController.java

~~~java
package example.webclient;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/internal/greetings/{name}")
    public GreetingResponse internal(
        @PathVariable String name,
        @RequestHeader(
            value = "X-Request-Id",
            required = false
        ) String requestId
    ) {
        return new GreetingResponse(
            "Hello, " + name,
            requestId
        );
    }

    @GetMapping("/api/greetings/{name}")
    public Mono<GreetingResponse> greeting(
        @PathVariable String name
    ) {
        return service.greet(name);
    }
}
~~~

Khi gọi `/api/greetings/Linh`, controller gọi WebClient tới `/internal/greetings/Linh`. Request ID được filter gắn vào header và endpoint downstream trả lại ID đó trong response.

### 13.10. ExchangeFilterFunctionTest.java

~~~java
package example.webclient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

class ExchangeFilterFunctionTest {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws IOException {
        server.shutdown();
    }

    @Test
    void filtersRunInRegistrationOrder() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("ok"));

        List<String> events = new CopyOnWriteArrayList<>();

        ExchangeFilterFunction first = (request, next) -> {
            events.add("first:request");

            ClientRequest updated = ClientRequest.from(request)
                .headers(headers -> headers.set("X-First", "yes"))
                .build();

            return next.exchange(updated)
                .doOnNext(response -> events.add("first:response"));
        };

        ExchangeFilterFunction second = (request, next) -> {
            events.add("second:request");

            return next.exchange(request)
                .doOnNext(response -> events.add("second:response"));
        };

        WebClient client = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .filter(first)
            .filter(second)
            .build();

        String body = client.get()
            .uri("/probe")
            .attribute("requestId", "req-123")
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(3));

        RecordedRequest recorded =
            server.takeRequest(3, TimeUnit.SECONDS);

        assertEquals("ok", body);
        assertNotNull(recorded);
        assertEquals("yes", recorded.getHeader("X-First"));

        assertEquals(
            List.of(
                "first:request",
                "second:request",
                "second:response",
                "first:response"
            ),
            events
        );
    }

    @Test
    void requestIdFilterAddsAttributeAsHeader() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("accepted"));

        WebClient client = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .filter(ClientFilters.requestId())
            .build();

        String body = client.get()
            .uri("/probe")
            .attribute("requestId", "trace-456")
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(3));

        RecordedRequest recorded =
            server.takeRequest(3, TimeUnit.SECONDS);

        assertEquals("accepted", body);
        assertNotNull(recorded);
        assertEquals("trace-456",
            recorded.getHeader("X-Request-Id"));
    }
}
~~~

Test thứ nhất xác minh filter đầu tiên chạy trước filter thứ hai ở chiều request; response quay về theo thứ tự ngược lại; header do filter thêm đã tới HTTP server giả lập; caller vẫn decode được body.

Test thứ hai xác minh request attribute được chuyển thành header thực tế. MockWebServer giúp kiểm tra HTTP request mà không cần phụ thuộc vào dịch vụ ngoài.

### 13.11. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/api/greetings/Linh
~~~

Body dự kiến:

~~~json
{
  "message": "Hello, Linh",
  "requestId": "một-uuid-thay-đổi-theo-lần-gọi"
}
~~~

Request ID thực tế là UUID được tạo khi service chạy; giá trị sẽ khác nhau mỗi lần gọi. Trong log ứng dụng, filter ghi operation, status và thời gian xử lý.

Chạy test:

~~~bash
mvn test
~~~

Hai test filter dùng MockWebServer và không cần chạy ứng dụng Spring Boot. Có thể bổ sung test ứng dụng riêng để xác minh endpoint `/api/greetings` gọi endpoint `/internal/greetings` đúng cấu hình.

## 14. Lỗi phổ biến khi viết ExchangeFilterFunction

**Lỗi 1 — Quên gọi `next.exchange(request)`.** Request không tới connector. Nếu cố ý short-circuit, phải trả một response/error hợp lệ.

**Lỗi 2 — Gọi `next.exchange` nhiều lần ngoài ý muốn.** Có thể gửi duplicate request. Chỉ gọi lại khi có chính sách retry/refresh rõ ràng.

**Lỗi 3 — Sửa ClientRequest trực tiếp.** Request là immutable; dùng `ClientRequest.from(request).build()`.

**Lỗi 4 — Đọc response body để log rồi trả response gốc.** Downstream không còn body để decode. Chỉ log metadata hoặc xây response mới sau khi đã đọc body có giới hạn.

**Lỗi 5 — Bỏ response body mà không release.** Có thể làm connection/buffer không được tái sử dụng đúng cách. Gọi `response.releaseBody()` nếu filter bỏ response.

**Lỗi 6 — Log Authorization hoặc Cookie.** Có thể làm lộ credential trong log. Redact hoặc không ghi các header nhạy cảm.

**Lỗi 7 — Dùng ThreadLocal cho request ID.** Reactive chain có thể đổi thread. Dùng request attribute hoặc Reactor Context.

**Lỗi 8 — Lưu token/request ID vào field mutable của filter singleton.** Nhiều request chạy đồng thời sẽ ghi đè dữ liệu của nhau. Lấy dữ liệu theo từng request hoặc từ provider thread-safe.

**Lỗi 9 — Retry mọi status và exception.** Có thể retry 400/401/404 hoặc lặp side effect. Chỉ retry lỗi transient theo policy.

**Lỗi 10 — Refresh token nhưng không release response 401.** Body cũ có thể giữ connection/buffer. Release body trước khi gửi request mới.

**Lỗi 11 — Refresh token không giới hạn.** Token mới vẫn có thể bị từ chối và tạo vòng lặp. Chỉ thử refresh/replay một lần cho một request.

**Lỗi 12 — Gửi lại body không replayable.** Publisher/file stream có thể đã bị tiêu thụ. Chỉ replay khi body có thể được tạo lại và thao tác an toàn.

**Lỗi 13 — Dùng cùng refresh filter cho token endpoint.** Request lấy token có thể kích hoạt chính filter đó, tạo recursion. Dùng WebClient riêng cho authentication endpoint.

**Lỗi 14 — Nhầm thứ tự request và response.** Filter đầu tiên chạy trước khi gửi, nhưng response quay về theo thứ tự ngược. Kiểm thử chain bằng event log.

**Lỗi 15 — Sửa danh sách filter sau khi build.** WebClient đã build là immutable. Dùng `mutate()` để tạo client dẫn xuất.

**Lỗi 16 — Đưa business rule vào filter.** Filter trở thành lớp khó kiểm thử và khó hiểu. Giữ filter cho concern HTTP dùng chung.

**Lỗi 17 — Dùng filter thay cho connector timeout/TLS.** Filter không cấu hình socket hoặc TLS handshake. Dùng ClientHttpConnector/HTTP client tương ứng.

**Lỗi 18 — Gọi `block()` hoặc `subscribe()` trong filter.** Có thể phá reactive composition, gây deadlock hoặc mất error propagation. Trả Publisher và để caller quản lý subscription.

## 15. Checklist thiết kế chuỗi filter

Trước khi đưa filter vào production, kiểm tra:

1. Filter này phục vụ concern dùng chung nào?
2. Nó cần sửa request, quan sát response hay cả hai?
3. Filter có luôn gọi `next.exchange` khi không short-circuit không?
4. Thứ tự đăng ký có đúng với authentication, logging, metrics và retry không?
5. Request mutation có giữ lại method, URL, body và attributes không?
6. Metadata theo request có dùng attribute/Context thay vì field mutable không?
7. Response body có được chuyển tiếp, tiêu thụ hoặc release đúng cách không?
8. Có log body, token, cookie hoặc query string nhạy cảm không?
9. Retry có lọc lỗi transient, giới hạn lần và tôn trọng idempotency không?
10. Token refresh có release body 401 và giới hạn một lần thử lại không?
11. Request body có replayable không?
12. Token endpoint có dùng client riêng nếu cần tránh recursion không?
13. Timeout có được cấu hình đúng tầng connector và service deadline không?
14. Filter có test thứ tự request/response bằng MockWebServer hoặc ExchangeFunction giả không?
15. Có metric/tracing chuẩn để tránh tự tạo hệ thống observability trùng lặp không?

## 16. Bài tập tự kiểm tra

1. `ExchangeFilterFunction` nằm ở đâu trong WebClient? **Giữa API gọi WebClient và ExchangeFunction thực hiện HTTP exchange.**
2. Phương thức chính của filter có tham số nào? **ClientRequest và ExchangeFunction next.**
3. `next.exchange(request)` có ý nghĩa gì? **Chuyển request sang filter tiếp theo hoặc connector ở cuối chuỗi.**
4. Nếu đăng ký A rồi B, request đi theo thứ tự nào? **A → B → connector.**
5. Response quay về theo thứ tự nào? **Connector → B → A.**
6. ClientRequest có thể sửa trực tiếp không? **Không; tạo bản sao bằng ClientRequest.from.**
7. `ofRequestProcessor` dùng cho việc gì? **Tạo filter từ hàm xử lý ClientRequest.**
8. `ofResponseProcessor` dùng cho việc gì? **Tạo filter từ hàm xử lý ClientResponse.**
9. Request attribute có tự trở thành HTTP header không? **Không; filter phải chủ động chuyển thành header nếu cần gửi qua network.**
10. Filter có được đọc response body rồi trả response cũ không? **Không; body đã bị tiêu thụ.**
11. Nếu filter bỏ response, cần làm gì với body? **Release body bằng response.releaseBody().**
12. `retrieve()` xử lý 4xx/5xx mặc định ra sao? **Chuyển thành WebClientResponseException nếu không có status handler tùy chỉnh.**
13. `exchangeToMono` phù hợp khi nào? **Khi cần kiểm tra status/header rồi chọn cách decode response.**
14. `mutate()` có sửa WebClient gốc không? **Không; tạo builder cho client dẫn xuất.**
15. Có nên log Authorization header không? **Không; cần bảo vệ hoặc redaction credential.**
16. Có nên retry mọi POST không? **Không; cần hiểu idempotency và khả năng replay body.**
17. Vì sao token refresh phải release body 401? **Để không giữ response body/connection trước khi gửi request mới.**
18. Filter có thay thế cấu hình TLS/connection pool không? **Không; các phần đó thuộc ClientHttpConnector và HTTP client.**

## 17. Ghi nhớ và tài liệu tham khảo

- **`ExchangeFilterFunction`** là functional interface để can thiệp vào logical HTTP exchange của WebClient.
- Filter đầu tiên đăng ký chạy đầu tiên ở chiều request; response quay về theo thứ tự ngược lại.
- Dùng `ClientRequest.from` để tạo request mới; dùng request attributes cho metadata theo từng request.
- `ofRequestProcessor` và `ofResponseProcessor` phù hợp cho filter đơn nhiệm vụ.
- Filter xử lý response phải tiêu thụ, release hoặc chuyển tiếp body. Không đọc body để log rồi trả response cũ.
- `response.releaseBody()` cần thiết khi filter bỏ response body; token refresh phải release 401 trước khi retry.
- `retrieve()` và `exchangeToMono/Flux` có cơ chế xử lý status/body khác nhau.
- WebClient immutable sau khi build; dùng `mutate()` để tạo client dẫn xuất.
- Retry phải có điều kiện, giới hạn, deadline, idempotency và khả năng replay body.
- Không log credential/body nhạy cảm; dùng request ID, metric và tracing phù hợp.
- Filter xử lý concern HTTP; connector xử lý transport, TLS, proxy và connection pool.

Tài liệu chính thức:

1. [Spring Framework 6.2 Reference — WebClient Filters](https://docs.spring.io/spring/reference/6.2/web/webflux-webclient/client-filter.html): đăng ký filter, request mutation, mutate, response body ownership và token refresh.
2. [Spring Framework 6.2 Reference — WebClient Exchange](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html): exchangeToMono, exchangeToFlux và tự động release response body chưa tiêu thụ.
3. [Spring Framework 6.2 Reference — WebClient Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html): Builder, connector, codec, filter chain và client immutability.
4. [Spring Framework Javadoc — ExchangeFilterFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html): filter, andThen, ofRequestProcessor và ofResponseProcessor.
5. [Spring Framework Javadoc — WebClient.Builder](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html): filter, filters, clientConnector và các cấu hình builder.
6. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): request/response workflow, codecs, testing và observability.
