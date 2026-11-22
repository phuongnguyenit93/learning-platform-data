# ServerWebExchange trong luồng xử lý yêu cầu

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `ServerWebExchange` là gì, nó được tạo ở đâu và đi qua những thành phần nào của Spring WebFlux.
2. Phân biệt request/response, exchange attributes, `WebSession`, `Principal` và Reactor `Context`.
3. Hiểu cách Spring Security áp dụng xác thực và phân quyền trên cùng một luồng xử lý reactive.
4. Viết `WebFilter` và controller dùng `ServerWebExchange` mà không chặn event loop hoặc làm mất chuỗi reactive.
5. Quan sát được yêu cầu được cho phép, yêu cầu bị từ chối và dữ liệu đi xuyên suốt filter → handler → response.

**Phạm vi:** Spring WebFlux (reactive stack) và tích hợp Spring Security WebFlux. Các khái niệm `HttpServletRequest`, `HttpServletResponse` và `FilterChain` của Servlet/MVC thuộc một stack khác; không dùng chúng để giải thích API `ServerWebExchange`.

## 2. ServerWebExchange là gì?

`org.springframework.web.server.ServerWebExchange` là **ngữ cảnh của một lần trao đổi HTTP** trên phía server WebFlux. Nó tập hợp các đối tượng và tiện ích mà nhiều lớp xử lý trong *cùng một request* cần dùng:

- `ServerHttpRequest`: HTTP method, URI, path, headers, cookies và body của request.
- `ServerHttpResponse`: status, headers, cookies và cách ghi body của response.
- `Map<String, Object>` attributes: dữ liệu tạm, gắn với exchange hiện tại để các thành phần trong chuỗi xử lý phối hợp.
- `Mono<WebSession>`, `Mono<Principal>`: truy cập session và principal theo giao diện reactive.
- Các tiện ích như `getFormData()`, `getMultipartData()`, `getLocaleContext()`, `getLogPrefix()` và `mutate()`.

Hiểu theo mô hình: **request và response là hai phần của cuộc trao đổi; exchange là đối tượng bao quát chúng cùng thông tin ngữ cảnh trong quá trình xử lý.** Không nên xem exchange là một request body, một “global context”, hay kho lưu trữ xuyên nhiều request.

`ServerWebExchange` tồn tại ở lớp `WebHandler` của Spring WebFlux, phía trên `HttpHandler` (lớp thích ứng với HTTP server như Reactor Netty). Cả mô hình controller annotation lẫn functional routing đều vận hành trên nền xử lý WebFlux này; controller annotation có thể nhận trực tiếp `ServerWebExchange` làm tham số.

## 3. Vị trí trong luồng xử lý HTTP

Sơ đồ khái quát:

```text
Client
  │ HTTP request
  ▼
HTTP server + HttpHandler adapter
  │ tạo / đưa request, response vào tầng WebHandler
  ▼
WebExceptionHandler (bao quanh luồng để xử lý lỗi)
  ▼
WebFilter #1 → WebFilter #2 → ... → WebHandler
                          │
                          ├─ Spring Security: WebFilterChainProxy
                          │    └─ chọn SecurityWebFilterChain phù hợp
                          │       → xác thực / security context / phân quyền
                          │
                          └─ DispatcherHandler (với annotated controllers)
                               → HandlerMapping
                               → HandlerAdapter / Controller
                               → ghi kết quả vào ServerHttpResponse
  ▼
HTTP response về client
```

Sơ đồ cho thấy quan hệ logic; **thứ tự chính xác giữa các `WebFilter` phụ thuộc vào cấu hình và thứ tự filter**. Spring Security cũng là một phần của chuỗi `WebFilter`, không phải một bước bắt buộc xảy ra đúng tại vị trí cố định trong mọi cấu hình. `WebExceptionHandler` có thể can thiệp khi lỗi phát sinh; nếu filter kết thúc sớm, controller sẽ không được gọi.

Một request GET thông thường đi qua các mốc:

1. HTTP server nhận dữ liệu và adapter tạo các abstraction của Spring; `ServerWebExchange` đại diện cho cuộc trao đổi đó.
2. Các `WebFilter` có thể đọc method/path/headers, gắn attributes, thêm header response, kiểm tra điều kiện, hoặc gọi tiếp `chain.filter(exchange)`.
3. Khi Spring Security được cấu hình, `WebFilterChainProxy` chọn `SecurityWebFilterChain` thích hợp theo `ServerWebExchangeMatcher`. Các security filter thực hiện công việc như tải `SecurityContext`, xác thực credentials và đánh giá quy tắc truy cập.
4. Nếu được tiếp tục, `DispatcherHandler` tìm handler phù hợp; controller đọc exchange hoặc các tham số đã được Spring resolve.
5. Handler trả về `Mono`/`Flux` hay một giá trị được chuyển thành response; WebFlux xử lý bất đồng bộ, gửi headers/body và hoàn tất exchange.
6. Nếu xác thực/phân quyền không đạt, security filter có thể tạo 401 hoặc 403 mà **không cần đi vào controller**.

**Chú ý:** “Non-blocking” không có nghĩa là mọi thành phần đều chạy cùng một thread hoặc request được xử lý tức thời. Công việc bắt đầu/kết thúc theo subscription và tín hiệu reactive; dữ liệu xác thực không nên được lưu trong một `ThreadLocal` do ứng dụng tự quản.

## 4. Các API quan trọng của exchange

| API | Ý nghĩa | Cách dùng đúng |
| --- | --- | --- |
| `getRequest()` | Lấy `ServerHttpRequest` | Đọc method, path, query, headers, cookies; body là một luồng dữ liệu |
| `getResponse()` | Lấy `ServerHttpResponse` | Gán status/header trước khi response được commit; ghi body theo reactive API |
| `getAttributes()`, `getAttribute(...)` | Lấy dữ liệu request-scoped | Truyền correlation id / kết quả trung gian giữa filter và handler |
| `getSession()` | `Mono<WebSession>` | Truy cập session bất đồng bộ; gọi API này **không tự động bắt đầu một session mới** |
| `getPrincipal()` | `Mono<T extends Principal>` | Lấy principal nếu đã có; có thể là `Mono.empty()` |
| `getFormData()` | `Mono<MultiValueMap<String, String>>` | Truy cập dữ liệu form đã parse khi phù hợp content type |
| `getMultipartData()` | `Mono<MultiValueMap<String, Part>>` | Truy cập các phần multipart; chú ý tài nguyên và kích thước upload |
| `getLocaleContext()` | Thông tin locale | Phục vụ xử lý đa ngôn ngữ theo resolver hiện hành |
| `getLogPrefix()` | Prefix hỗ trợ log theo exchange | Dùng khi cần nối các dòng log cùng request |
| `mutate()` | Builder tạo exchange wrapper | Thay request/response/principal biểu kiến cho các bước tiếp theo |

Ví dụ *đọc thông tin không tiêu thụ body* trong một controller:

```java
@GetMapping("/request-info")
Mono<Map<String, String>> requestInfo(ServerWebExchange exchange) {
    ServerHttpRequest request = exchange.getRequest();
    return Mono.just(Map.of(
        "method", request.getMethod().name(),
        "path", request.getPath().value(),
        "requestId", request.getId()
    ));
}
```

Đoạn này là **method minh họa**, cần nằm trong một `@RestController` với import tương ứng. `requestId` do runtime sinh ra nên không thể dự đoán cố định. Không dùng path, request ID hay bất kỳ exchange attribute nào như bằng chứng người dùng đã xác thực.

### Exchange attributes, session và Reactor Context khác nhau thế nào?

| Nơi chứa | Phạm vi | Đặc điểm điển hình |
| --- | --- | --- |
| `exchange.getAttributes()` | Một exchange HTTP | `Map` có thể thay đổi; chia sẻ giữa các bước thấy cùng exchange; không tự tồn tại ở request kế tiếp |
| `WebSession` | Session của client | Có thể tồn tại qua nhiều request nếu cơ chế session được sử dụng; lưu lượng nhỏ và có chủ đích |
| Reactor `Context` | Chuỗi subscription/reactive | Truyền metadata qua các bước reactive kể cả khi đổi thread; đọc/ghi qua Reactor API |
| `SecurityContext` | Ngữ cảnh bảo mật cho reactive execution | Chứa `Authentication`; Spring Security kết nối nó với Reactor `Context` và cơ chế security context repository theo cấu hình |

*Không đánh đồng:* đặt một key `"user"` trong `getAttributes()` **không xác thực** người dùng. Muốn kiểm tra danh tính hoặc quyền phải dựa trên cơ chế Spring Security (`Authentication`/`AuthorizationManager` và `SecurityContext`), không tin vào header hay attribute do client có thể ảnh hưởng.

### Request body không phải một String có sẵn

`exchange.getRequest().getBody()` cung cấp `Flux<DataBuffer>`. Body thường được tiêu thụ trong quá trình decode/bind. Một filter đọc hết body rồi yêu cầu controller đọc lại có thể gây thiếu dữ liệu; nếu cần đọc lại, phải dùng cơ chế cache/decorate phù hợp và quản lý bộ nhớ `DataBuffer` cẩn thận. Với nghiệp vụ thông thường, ưu tiên `@RequestBody Mono<MyDto>` hoặc `ServerRequest.bodyToMono(...)` thay vì tự gom body trong filter.

## 5. ServerWebExchange và Spring Security reactive

Ở WebFlux, cấu hình security web dùng `ServerHttpSecurity` và tạo một hoặc nhiều `SecurityWebFilterChain`. `WebFilterChainProxy` sẽ áp dụng chuỗi phù hợp với exchange. Một số thành phần nội bộ có thể hoạt động ở các thời điểm khác nhau:

- Bộ lọc liên quan tới `ServerSecurityContextRepository` nạp/lưu thông tin security context theo chiến lược cấu hình.
- Bộ lọc xác thực xử lý HTTP Basic, form login, bearer token… khi cơ chế đó được bật.
- Bộ lọc phân quyền xem path, method và trạng thái xác thực để cho phép hay từ chối.
- `SecurityContextServerWebExchangeWebFilter` làm cho `exchange.getPrincipal()` có thể lấy principal từ `ReactiveSecurityContextHolder` trong ngữ cảnh security phù hợp.

Ví dụ quy tắc `pathMatchers("/public/**").permitAll()` chỉ nói rằng đường dẫn được phép truy cập mà không cần đăng nhập. Điều đó **không đảm bảo** `exchange.getPrincipal()` sẽ có giá trị. Tương tự, `authenticated()` yêu cầu có xác thực hợp lệ; API của exchange không tự thực hiện đăng nhập.

Trong xử lý reactive, khi cần chính `Authentication` (roles/authorities, metadata xác thực), dùng:

```java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Đây là **fragment** đặt trong đoạn code đã có Spring Security context; các import tương ứng là `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.core.context.SecurityContext` và `org.springframework.security.core.Authentication`. Nó có thể hoàn thành rỗng nếu không có context; hãy thiết kế trường hợp anonymous/unauthenticated rõ ràng. Không lấy `Authentication` từ `SecurityContextHolder.getContext()` kiểu Servlet rồi giả định nó theo bạn qua mọi bước reactive.

## 6. Ví dụ runnable: filter → exchange → security → controller

Ví dụ dùng **Java 17+, Spring Boot 3.5.12 và Spring WebFlux/Spring Security 6.x**. Ta tạo hai endpoint GET:

- `GET /public/exchange`: công khai, trả về method/path và ID mà `WebFilter` đặt trong attributes.
- `GET /me`: yêu cầu HTTP Basic; trả tên người dùng từ `exchange.getPrincipal()`.

`WebFilter` đặt cùng một correlation ID vào exchange attributes và header response **trước khi** gọi tiếp chuỗi. Nó không tự xác thực hay thay thế security filter.

### Cấu trúc dự án

```text
exchange-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/exchange/
    ├── ExchangeDemoApplication.java
    ├── SecurityConfiguration.java
    ├── TraceWebFilter.java
    └── ExchangeController.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'exchange-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

**`src/main/java/com/example/exchange/ExchangeDemoApplication.java`**

```java
package com.example.exchange;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExchangeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExchangeDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/exchange/SecurityConfiguration.java`**

```java
package com.example.exchange;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo123")
            .roles("LEARNER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
```

`{noop}` chỉ phù hợp **demo cục bộ** để quan sát request flow; trong ứng dụng thật, dùng password encoder an toàn, secret management và cơ chế xác thực phù hợp. Không đưa tài khoản demo lên production. Ví dụ giữ mặc định CSRF protection; các request kiểm chứng đều dùng GET, nên không cần tắt CSRF.

**`src/main/java/com/example/exchange/TraceWebFilter.java`**

```java
package com.example.exchange;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String traceId = exchange.getRequest().getId();
        exchange.getAttributes().put("demo.traceId", traceId);
        exchange.getResponse().getHeaders().set("X-Trace-Id", traceId);
        return chain.filter(exchange);
    }
}
```

`@Order(Ordered.HIGHEST_PRECEDENCE)` đặt filter ví dụ ở ưu tiên cao, cho phép nó gắn ID trước khi các bước phía sau xử lý. Nó không đọc principal bởi ở thời điểm sớm này security context có thể **chưa** được thiết lập. `return chain.filter(exchange)` là chi tiết thiết yếu: tiếp nối publisher của cả chuỗi, đồng thời để framework kiểm soát subscription và kết thúc response.

**`src/main/java/com/example/exchange/ExchangeController.java`**

```java
package com.example.exchange;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ExchangeController {
    @GetMapping("/public/exchange")
    public Mono<Map<String, String>> inspect(ServerWebExchange exchange) {
        ServerHttpRequest request = exchange.getRequest();
        String traceId = exchange.getAttributeOrDefault("demo.traceId", "unavailable");

        return Mono.just(Map.of(
            "method", request.getMethod().name(),
            "path", request.getPath().value(),
            "traceId", traceId
        ));
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.<Principal>getPrincipal()
            .map(principal -> Map.of(
                "user", principal.getName(),
                "path", exchange.getRequest().getPath().value()
            ));
    }
}
```

Ở `inspect`, controller đọc đúng attribute mà filter đã ghi **trong cùng exchange**. Ở `me`, `getPrincipal()` là nguồn danh tính do tích hợp Spring Security cung cấp sau khi chuỗi security cho phép request đến controller. Không có `block()`, `subscribe()` hay truy cập session không cần thiết.

### Chạy và đối chiếu

Cần JDK 17+ và Gradle tương thích với Spring Boot 3.5 (hoặc dùng Gradle Wrapper được tạo cho dự án). Trong thư mục `exchange-demo`:

```bash
gradle bootRun
```

Nếu dự án có wrapper, trên Linux/macOS dùng `./gradlew bootRun`, trên Windows dùng `gradlew.bat bootRun`. Lệnh `javac`/`java` đơn thuần không đủ ở đây vì ví dụ cần các thư viện Spring và dependency graph; Gradle giải quyết classpath và chạy main class.

Mở terminal khác:

```bash
curl -i http://localhost:8080/public/exchange
curl -i http://localhost:8080/me
curl -i -u learner:demo123 http://localhost:8080/me
```

Kỳ vọng:

| Request | Trạng thái | Quan sát |
| --- | --- | --- |
| GET `/public/exchange` không credentials | `200 OK` | JSON có `method=GET`, `path=/public/exchange`, `traceId`; header `X-Trace-Id` cùng giá trị |
| GET `/me` không credentials | `401 Unauthorized` | Security từ chối trước khi controller `me` chạy; HTTP Basic có thể trả `WWW-Authenticate` |
| GET `/me` với HTTP Basic `learner:demo123` | `200 OK` | JSON có `user=learner` và `path=/me` |

JSON mẫu cho request cuối (thứ tự field có thể khác):

```json
{"user":"learner","path":"/me"}
```

Giá trị `traceId` **thay đổi theo request**; không ghi một output cố định giả. Nếu một client/browser tự gửi credentials hoặc thay đổi `Accept` header, hành vi challenge/response có thể khác chi tiết, nhưng các quy tắc cho phép hoặc yêu cầu xác thực trong cấu hình trên vẫn giữ nguyên.

### Phân tích từng bước của ví dụ

1. Client gửi `GET /me`. `TraceWebFilter` nhận `ServerWebExchange`, đọc `ServerHttpRequest.getId()`, ghi attribute và response header.
2. Spring Security áp dụng `SecurityWebFilterChain` và quy tắc `anyExchange().authenticated()`.
3. Nếu thiếu credentials, security tạo challenge 401; `ExchangeController.me` không được gọi. Header trace có thể được gửi vì filter gắn trước security.
4. Nếu HTTP Basic đúng, Spring Security có `Authentication` hợp lệ trong ngữ cảnh reactive. Security cho chuỗi xử lý đi tiếp.
5. `DispatcherHandler` định tuyến tới `me`, tham số exchange được inject, `getPrincipal()` phát ra principal, `map(...)` tạo dữ liệu JSON.
6. WebFlux serialize kết quả và hoàn tất response; các filter bao quanh có thể quan sát tín hiệu hoàn thành/lỗi theo thứ tự đã cấu hình.

## 7. Khi nào dùng exchange.mutate()?

Không nên cố sửa trực tiếp mọi trường của request, vì các abstraction WebFlux thường dùng wrapper/decorator để biểu diễn thay đổi. Ví dụ một `WebFilter` cần thêm header **nội bộ** cho các bước phía sau:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    var newRequest = exchange.getRequest().mutate()
        .header("X-Internal-Lesson", "exchange")
        .build();

    ServerWebExchange updated = exchange.mutate()
        .request(newRequest)
        .build();

    return chain.filter(updated);
}
```

Đây là **fragment minh họa** của một `WebFilter`, không phải ứng dụng độc lập. `updated` vẫn là exchange cho cùng một HTTP request, được bọc để lớp phía sau nhìn thấy request đã thay đổi. Không dùng việc tự thêm header như một cách cấp quyền hay mạo danh principal; headers từ client cần được kiểm soát tại ranh giới tin cậy.

Khi muốn kết thúc sớm (ví dụ một filter chủ động trả status), cần trả publisher hoàn tất response thay vì gọi tiếp `chain.filter`. Nhưng chính sách xác thực/phân quyền nên để Spring Security quản lý; tùy tiện tự trả 403 trong filter dễ làm sai lệch trình tự security.

## 8. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách làm |
| --- | --- | --- |
| Gọi `chain.filter(exchange).subscribe()` trong filter rồi trả `Mono.empty()` | Tự tạo subscription ngoài vòng đời request, làm sai thứ tự và xử lý lỗi | `return chain.filter(exchange)`, ghép bằng reactive operators khi cần |
| Gọi `block()` trong controller/filter trên event loop | Chặn thread xử lý non-blocking, gây giảm throughput hoặc deadlock trong một số tình huống | Giữ `Mono`/`Flux`; dùng API reactive; cô lập thư viện blocking trên scheduler phù hợp khi bắt buộc |
| Đọc `getPrincipal()` trong filter chạy trước Spring Security và cho rằng luôn có user | Security context có thể chưa tồn tại; endpoint public cũng có thể không có principal | Xem thứ tự filter; dùng đúng security context sau khi authentication hoàn tất |
| Tự lưu `Authentication` trong `ThreadLocal` | Reactive execution có thể thay thread | Dùng `ReactiveSecurityContextHolder` / Reactor `Context` |
| Tin vào `exchange.getAttributes().get("role")` để phân quyền | Attribute không phải kết quả xác thực đáng tin cậy | Dùng security authorization và authorities thực tế |
| Đọc `getBody()` toàn bộ trong filter rồi controller đọc lại | Body stream có thể đã bị tiêu thụ; giữ `DataBuffer` sai gây rò bộ nhớ | Để framework decode hoặc decorate/cache body có kiểm soát |
| Ghi header sau khi response đã commit | Status/headers không còn thay đổi được | Ghi trước khi chain commit hoặc dùng hook phù hợp của response |
| Lạm dụng `getSession()`/attributes cho dữ liệu lớn | Tốn bộ nhớ, tạo coupling và có thể giữ trạng thái ngoài ý muốn | Chỉ giữ metadata nhỏ, đúng vòng đời |
| Giả định `permitAll()` luôn có principal | `permitAll()` là quyết định truy cập, không phải lệnh xác thực | Xử lý `Mono.empty()` nếu endpoint cho phép anonymous |
| Dùng DSL Servlet `HttpSecurity` cho WebFlux | Không khớp reactive security stack | Dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `WebFilter` |

### Chẩn đoán request không vào controller

Trước tiên kiểm tra: HTTP method/path có khớp mapping không; `WebFilter` nào dừng sớm; security matcher nào được chọn; rule nào từ chối; request có credentials hợp lệ không; có lỗi trước lúc handler được gọi không. Phân biệt 401 (chưa được xác thực hợp lệ) với 403 (đã xác thực nhưng không đủ quyền) trong bối cảnh cấu hình cụ thể. Correlation ID từ exchange giúp ghép log, nhưng không nên log password, Authorization header, cookie phiên hay toàn bộ body nhạy cảm.

## 9. Tự kiểm tra

1. **`ServerWebExchange` khác `ServerHttpRequest` ở đâu?** Exchange bao cả request, response và ngữ cảnh xử lý; request chỉ mô tả phía yêu cầu.
2. **Vì sao `getPrincipal()` trả `Mono`?** Vì việc lấy principal tuân theo mô hình reactive và có thể chưa có/không có giá trị; không được giả định `Principal` sẵn sàng đồng bộ.
3. **`getAttributes()` có thay thế session được không?** Không. Attribute sống theo exchange hiện tại; session có thể được quản lý qua nhiều request.
4. **Nếu `/me` trả 401, controller `me` có chạy không?** Theo cấu hình ví dụ, không. Security chặn trước khi vào controller.
5. **Muốn chuyển một giá trị từ filter sang controller trong cùng request thì làm sao?** Ghi `exchange.getAttributes().put(key, value)` trong filter, đọc `getAttribute(...)` trong controller, đồng thời tiếp tục `chain.filter(exchange)`.
6. **Muốn lấy roles/authorities để kiểm tra quyền thì dùng gì?** Cơ chế phân quyền Spring Security hoặc `Authentication` từ reactive security context; không tự tin vào query/header/attribute.

## 10. Ghi nhớ

- `ServerWebExchange` là **đối tượng trung tâm của một HTTP exchange** trong WebFlux; các `WebFilter` và handler có thể cùng tiếp cận nó.
- Spring Security trong WebFlux triển khai qua **reactive `WebFilter` chain**, trong đó `ServerWebExchange` là đầu vào cho logic match, xác thực và phân quyền.
- Exchange attributes chia sẻ dữ liệu **cùng request**; WebSession, Reactor Context và SecurityContext có phạm vi và ngữ nghĩa khác.
- Luồng reactive phải được **trả về và compose**, không tự `subscribe()` hoặc chặn bằng `block()` trong handler/filter.
- Trạng thái cuối cùng quan sát được là **response HTTP**; 401/403 có thể xuất hiện trước controller.

### Tài liệu tham khảo chính thức

- Spring Framework, Reactive Core / WebHandler và WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework, tham số của annotated controller: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework, API `ServerWebExchange`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Security, cấu hình WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security, authorize HTTP requests (reactive): https://docs.spring.io/spring-security/reference/7.2/reactive/authorization/authorize-http-requests.html
- Spring Security, `SecurityContextServerWebExchangeWebFilter` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html
