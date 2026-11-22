# Đường đi của yêu cầu qua WebFilter, WebFilterChainProxy và SecurityWebFilterChain

## Mục tiêu và ngữ cảnh

Bài học nằm trong phần **Kiến trúc WebFilter** của **Spring Security - reactive**. Sau khi học, bạn cần giải thích được:

1. Một yêu cầu HTTP đi từ Spring WebFlux vào chuỗi `WebFilter` toàn cục như thế nào.
2. Vì sao `WebFilterChainProxy` là một `WebFilter` nhưng `SecurityWebFilterChain` không phải chính `WebFilter` đó.
3. Spring Security chọn **một** `SecurityWebFilterChain` theo `securityMatcher` và thứ tự ưu tiên ra sao.
4. Các filter xác thực, ủy quyền chạy trước handler như thế nào; khi nào pipeline dừng sớm.
5. Cách cấu hình, quan sát và kiểm thử đường đi với **nhiều security chain** mà không bỏ hở URL.

Đây là kiến trúc **Spring WebFlux** sử dụng Reactor (`Mono`/`Flux`). Các lớp `jakarta.servlet.Filter`, `FilterChainProxy` và `SecurityFilterChain` thuộc Servlet có khái niệm tương tự, nhưng **không được dùng thay cho** `WebFilter`, `WebFilterChainProxy` và `SecurityWebFilterChain` của WebFlux.

## 1. Phân biệt bốn thành phần cốt lõi

| Thành phần | Thuộc tầng nào? | Hợp đồng chính | Trách nhiệm |
| --- | --- | --- | --- |
| `WebFilter` | Spring WebFlux | `Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)` | Chặn trước/sau xử lý HTTP; có thể gọi tiếp chain, trả response hoặc phát lỗi |
| `WebFilterChain` | Spring WebFlux | `Mono<Void> filter(ServerWebExchange exchange)` | Đại diện **phần còn lại** của chuỗi filter và cuối cùng là `WebHandler` |
| `WebFilterChainProxy` | Spring Security reactive | Bản thân **triển khai `WebFilter`** | Nhận exchange, xử lý firewall, tìm security chain phù hợp và cho các security filter tham gia pipeline |
| `SecurityWebFilterChain` | Spring Security reactive | `Mono<Boolean> matches(ServerWebExchange)` và `Flux<WebFilter> getWebFilters()` | Mô tả **điều kiện chọn chain** cùng **danh sách security WebFilter** tương ứng |

Các ý nghĩa thường bị đánh đồng:

- `WebFilterChain` là một **đường thực thi tiếp**; nó được truyền qua từng lời gọi `filter(...)`.
- `SecurityWebFilterChain` là một **cấu hình được chọn cho request**, gồm matcher và danh sách filter; nó **không** tự có phương thức `filter(exchange, chain)` như một `WebFilter`.
- `WebFilterChainProxy` là **điểm nối** giữa hai thế giới: một filter trong chuỗi WebFlux toàn cục và nhiều tập security filter có điều kiện lựa chọn.
- `ServerHttpSecurity` là DSL dùng để cấu hình và `build()` thành `SecurityWebFilterChain`; nó không đại diện cho một request đang chạy.

Ví dụ, một `SecurityWebFilterChain` có thể bảo vệ `/api/**` bằng HTTP Basic, còn chain khác bảo vệ đường dẫn còn lại bằng cơ chế khác. Proxy xem từng request và chọn chain thích hợp; không phải cứ có hai bean là cả hai tập filter được chạy liên tiếp.

## 2. Sơ đồ đường đi của yêu cầu

```text
Client gửi HTTP request
    |
    v
HTTP server/reactive adapter (ví dụ Reactor Netty)
    |
    v
HttpWebHandlerAdapter / WebHandler pipeline của Spring WebFlux
    |
    v
FilteringWebHandler
    |
    +--> WebFilter toàn cục A (nếu được đăng ký)
    |       |
    |       +--> WebFilterChainProxy  <-- cũng là một WebFilter
    |                  |
    |                  +--> ServerWebExchangeFirewall kiểm tra exchange
    |                  |
    |                  +--> duyệt các SecurityWebFilterChain theo ưu tiên
    |                          |
    |                          +--> matches(exchange): Mono<Boolean>
    |                          +--> chọn CHAIN ĐẦU TIÊN khớp
    |                                  |
    |                                  v
    |                             danh sách WebFilter của chain đó
    |                             (context, authentication, authorization,
    |                              exception handling, headers... tùy cấu hình)
    |                                  |
    |                                  v
    |                             WebFilterChain gốc tiếp tục
    |       |                          |
    |       +--------------------------+
    |       |
    +--> WebFilter toàn cục B (nếu còn trong chain)
    |
    v
WebHandler / DispatcherHandler / RouterFunction handler
    |
    v
Kết quả được ghi vào ServerHttpResponse
    |
    v
Reactive pipeline hoàn tất hoặc kết thúc vì lỗi/cancellation
```

Sơ đồ mang tính **khái niệm**; vị trí chính xác của A, B và các security filter tùy thứ tự đăng ký và cấu hình. Phần **WebFilter toàn cục** bao gồm cả security proxy, còn **security WebFilter bên trong** chỉ được nối vào khi proxy chọn được `SecurityWebFilterChain`.

Đường phản hồi không phải một chuỗi filter chạy “ngược” tự động theo kiểu hàm đồng bộ. Những thao tác `doOnSuccess`, `doOnError`, `doFinally` hoặc `then` mà filter gắn lên `Mono<Void>` có thể chạy khi luồng ở phía dưới kết thúc, lỗi hoặc bị hủy. Mọi thứ được thực thi theo hợp đồng reactive khi publisher được subscribe.

## 3. Giai đoạn khởi tạo và giai đoạn xử lý request

### 3.1. Khởi tạo ứng dụng

Khi bật Spring Security reactive, chẳng hạn với `@EnableWebFluxSecurity` hoặc auto-configuration thích hợp, ứng dụng có thể tạo một hay nhiều bean `SecurityWebFilterChain` bằng `ServerHttpSecurity`:

```java
// Mảnh cấu hình, chưa phải ứng dụng độc lập.
@Bean
SecurityWebFilterChain defaultSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Trong quá trình wiring, Spring Security cung cấp `WebFilterChainProxy` để sử dụng các security chain đó. WebFlux nhìn proxy như một `WebFilter` trong dãy filter toàn cục. Trong Spring Boot WebFlux, các bean `WebFilter` được nhận diện và sắp theo `Ordered`/`@Order`; mặc định Spring Boot đặt security `WebFilterChainProxy` tại order **-100**. Con số này là thứ tự **giữa các WebFilter toàn cục** trong cấu hình Boot tương ứng, không phải thứ tự bên trong từng security chain.

Đối với mỗi `SecurityWebFilterChain`, `ServerHttpSecurity.build()` tập hợp những security filter cần thiết theo cấu hình (security context, xác thực, CSRF, authorization, v.v.). Danh sách thực tế khác nhau theo `httpBasic`, `formLogin`, JWT, CSRF, headers và phiên bản framework; **không giả định mọi ứng dụng đều có cùng filter hoặc cùng số lượng filter**.

### 3.2. Khi request đến

1. HTTP server chuyển request vào WebFlux; framework tạo `ServerWebExchange`, chứa request, response và các thuộc tính exchange.
2. Chuỗi `WebFilter` toàn cục được gọi theo thứ tự; mỗi filter nhận một `WebFilterChain` để có thể đi tiếp.
3. Đến lượt `WebFilterChainProxy`, proxy áp dụng `ServerWebExchangeFirewall`. Exchange không hợp lệ có thể bị từ chối ngay trước bước xác thực/ủy quyền.
4. Proxy duyệt những `SecurityWebFilterChain` đã được sắp theo thứ tự: gọi `matches(exchange)` cho từng chain cho đến chain **đầu tiên** trả `true`.
5. Proxy lấy `getWebFilters()` của chain đã chọn, ghép chúng với `WebFilterChain` gốc để giữ khả năng đi tiếp tới các WebFilter còn lại và handler.
6. Các security filter trong chain thực hiện logic theo cấu hình; filter có thể tiếp tục, challenge người dùng, từ chối hoặc trả lỗi.
7. Khi các bước đều cho phép, luồng tiếp tục đến `DispatcherHandler`/functional handler để chạy endpoint và ghi response.

Về mặt triển khai, lựa chọn chain có thể hình dung là `Flux.fromIterable(chains).filterWhen(chain -> chain.matches(exchange)).next()`: `filterWhen` đánh giá matcher phản ứng; `next()` lấy **phần tử khớp đầu tiên**. Đây là mô tả ý tưởng của cơ chế lựa chọn, **không phải API ứng dụng cần tự gọi**.

Nếu **không chain nào khớp**, proxy tiếp tục đường WebFlux gốc **mà không chèn security filters của một SecurityWebFilterChain**. Đây là chỗ dễ để lộ endpoint nếu ứng dụng chỉ tạo chain có matcher `/api/**` mà quên bảo vệ URL khác. Đừng hiểu “không khớp” là “mặc định bị cấm”: phải đặt một chain bao phủ các request còn lại hoặc có lớp bảo vệ khác được kiểm chứng.

## 4. Hai tầng thứ tự và một tầng quy tắc ủy quyền

Ba cơ chế sau có thể cùng xuất hiện trong một ứng dụng nhưng không thay thế cho nhau:

| Vị trí thiết lập | Dùng để sắp thứ tự gì? | Ví dụ |
| --- | --- | --- |
| `@Order` trên bean `WebFilter` toàn cục | Vị trí filter trong pipeline WebFlux (trước/sau proxy) | Filter quan sát ở order `-200` chạy trước security proxy mặc định của Boot (`-100`) |
| `@Order` trên bean `SecurityWebFilterChain` | Thứ tự **đánh giá chain nào khớp trước** | `@Order(1)` cho `/api/**`; `@Order(2)` cho chain dự phòng |
| `SecurityWebFiltersOrder`, `addFilterBefore/After/At` | Vị trí một filter **bên trong** security chain đã chọn | Chèn custom security `WebFilter` trước `AUTHORIZATION` |

Còn `authorizeExchange(exchanges -> exchanges.pathMatchers(...).permitAll() ...)` là **quy tắc bên trong chain**, không quyết định việc chọn chain. Phân biệt hai câu hỏi:

- **Chain nào xử lý request?** Do `securityMatcher(...)` của từng chain và `@Order` quyết định.
- **Request có được phép trong chain đã chọn?** Do `authorizeExchange(...)`, authentication và các security filter tương ứng quyết định.

Ví dụ, nếu cả chain `/api/**` và chain mặc định đều khớp `GET /api/hello`, chỉ chain `/api/**` có ưu tiên cao hơn được dùng. Quy tắc `permitAll()` hay `denyAll()` đặt trong chain mặc định **không cộng dồn** lên request đó.

**Không tự ý gắn `@Order(-200)` cho một `WebFilter` dùng để cho qua request mà không gọi `chain.filter(exchange)`**. Nếu nó kết thúc response sớm, security proxy có thể chưa được gọi; các trường hợp bypass phải được thiết kế và kiểm thử như một phần của kiến trúc bảo mật.

## 5. Ví dụ chạy được với Java 17+ và hai security chain

Ví dụ tối thiểu dùng Spring Boot 3.3.13, Java 17+, WebFlux và Spring Security tương thích do BOM quản lý. App có ba GET endpoint:

- `GET /api/hello`: chain API, chỉ người dùng đăng nhập mới được truy cập.
- `GET /public/ping`: chain dự phòng, cho phép public.
- `GET /internal/secret`: chain dự phòng, từ chối tất cả, kể cả người dùng đã đăng nhập.

Tạo `settings.gradle`:

```groovy
rootProject.name = 'webfilter-flow-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/main/java/example/WebFilterFlowApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class WebFilterFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFilterFlowApplication.class, args);
    }

    @GetMapping("/api/hello")
    public String apiHello() {
        return "api-ok";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/internal/secret")
    public String secret() {
        return "secret";
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        http
            // Không có securityMatcher: áp dụng cho mọi path còn lại.
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().denyAll())
            .httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    @Order(-200)
    WebFilter traceOutsideSecurity() {
        return (exchange, chain) -> Mono.defer(() -> {
            String path = exchange.getRequest().getPath().value();
            System.out.println("OUTER enter: " + path);
            return chain.filter(exchange)
                .doFinally(signal ->
                    System.out.println("OUTER finish: " + path + " / " + signal));
        });
    }
}
```

**Giải thích từng phần:**

- `apiChain` dùng `securityMatcher("/api/**")` và `@Order(1)`; nó được xét trước. `authenticated()` là quy tắc **trong chain API**.
- `fallbackChain` dùng matcher mặc định khớp mọi request và `@Order(2)`; các URL không vào chain API vẫn có chính sách rõ ràng. `/public/**` được phép, tất cả path còn lại bị từ chối.
- `MapReactiveUserDetailsService` có người dùng `alice` để thử HTTP Basic. `{noop}` chỉ phù hợp **demo cục bộ**; ứng dụng thật cần mật khẩu mã hóa và cơ chế quản lý secret thích hợp.
- `traceOutsideSecurity` là **WebFilter toàn cục**: order `-200` khiến nó chạy trước proxy security mặc định order `-100` trong Spring Boot WebFlux. `Mono.defer` giúp lệnh in xuất hiện khi luồng được subscribe; `doFinally` chạy khi pipeline kết thúc, lỗi hoặc bị hủy. Nó không được dùng làm cơ chế quyết định ủy quyền.
- Hai security chain không được tự nối bằng `chain.filter(...)` trong method bean. Proxy tự chọn chain và sắp security filters tương ứng.

Chạy với Gradle 8.5+ và JDK 17+:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Khi ứng dụng sẵn sàng trên cổng 8080, thử:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/hello
curl -i -u alice:demo http://localhost:8080/api/hello
curl -i -u alice:demo http://localhost:8080/internal/secret
```

Các kết quả cần quan sát (mã trạng thái với cấu hình trên, không yêu cầu header/định dạng log giống hệt từng phiên bản):

| Request | Chain được chọn | Kết quả mong đợi |
| --- | --- | --- |
| `GET /public/ping` không credentials | `fallbackChain` | `200`, body `pong` |
| `GET /api/hello` không credentials | `apiChain` | `401`, HTTP Basic challenge |
| `GET /api/hello` với `alice:demo` | `apiChain` | `200`, body `api-ok` |
| `GET /internal/secret` với `alice:demo` | `fallbackChain` | `403`; handler `secret()` không được gọi |

Không suy ra một request chưa xác thực bị `denyAll` sẽ luôn 403: khi chưa xác thực, entry point có thể trả 401 hoặc chuyển hướng tùy cấu hình. Trong ví dụ trên dùng **credentials hợp lệ** cho ca kiểm tra 403 để tách biệt rõ authorization với authentication.

Log tùy thời điểm request hoàn tất nhưng có dạng:

```text
OUTER enter: /api/hello
OUTER finish: /api/hello / onComplete
```

Đường đi thực tế vẫn còn các filter security bên trong proxy giữa hai mốc. Tín hiệu `onComplete` có thể xảy ra cả khi request bị từ chối **đã được framework xử lý thành response**, vì `Mono<Void>` hoàn tất sau khi ghi response; bản thân log hoàn tất **không chứng minh** handler đã chạy hay authorization đã thành công.

## 6. Đi sâu vào WebFilterChainProxy và lựa chọn chain

Pseudo-code sau mô tả trách nhiệm, **không phải mã nguồn có thể copy vào ứng dụng**:

```java
// PSEUDOCODE: diễn giải ý tưởng; không phải API implementation.
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain original) {
    return firewall.check(exchange)
        .flatMap(safeExchange ->
            firstMatchingChain(safeExchange)
                .flatMap(chosen -> {
                    List<WebFilter> filters = chosen.getWebFilters();
                    WebFilterChain secured = decorate(original, filters);
                    return secured.filter(safeExchange);
                })
                .switchIfEmpty(Mono.defer(
                    () -> original.filter(safeExchange))));
}
```

Các thực tế cần phân biệt:

**(1) Matcher trả tín hiệu bất đồng bộ.** `SecurityWebFilterChain.matches(...)` có kiểu `Mono<Boolean>`, không phải một `boolean` đồng bộ. Framework đánh giá theo thứ tự chain cho đến khi có match; không được dùng `block()` trong request WebFlux để bắt kết quả.

**(2) Chỉ chain đầu tiên khớp được dùng.** Với danh sách `apiChain` rồi `fallbackChain`, request `/api/hello` thỏa cả matcher `/api/**` và matcher mặc định, nhưng danh sách filter của `fallbackChain` không chạy vì proxy đã chọn `apiChain`. Không áp dụng cơ chế “OR” hay “AND” mặc định giữa các chain khác nhau.

**(3) Có match không có nghĩa là cho phép.** Matcher chỉ xét request thuộc cấu hình chain nào; quyết định `permitAll`, `authenticated`, `hasRole` hay `denyAll` được đánh giá sau đó bởi các security filter tương ứng.

**(4) Không có match là một trường hợp nguy hiểm.** Proxy vẫn có thể chuyển request xuống ứng dụng nhưng không có bảo vệ từ các security WebFilter. Vì thế, thường tạo một chain mặc định khớp phần còn lại và dùng `anyExchange().denyAll()` hoặc policy được phê duyệt.

**(5) Firewall không phải authorization rule.** Firewall xử lý điều kiện hợp lệ của exchange, chẳng hạn path đáng ngờ, trước hoặc bên cạnh các bước bảo mật khác. Từ chối bởi firewall không có cùng nguyên nhân với 401 thiếu xác thực hay 403 thiếu quyền.

**(6) SecurityWebFilterChain không phải global WebFilterChain.** `getWebFilters()` trả `Flux<WebFilter>`; proxy mới ghép các filter được chọn với `WebFilterChain` gốc. Các security filter nằm trong chain đã chọn vẫn là những đối tượng `WebFilter`, nhưng chúng được quản lý theo cấu hình security tương ứng.

## 7. Điều gì xảy ra bên trong security filters?

Với chuỗi có authentication và authorization, luồng thông thường gồm những trách nhiệm sau; thứ tự cụ thể cùng thành phần thực tế do `ServerHttpSecurity` xây dựng:

1. **Security context:** khôi phục hoặc truyền `SecurityContext` / `Authentication` qua Reactor Context và các thành phần của Spring Security. Không giả định có thể luôn đọc người dùng từ `ThreadLocal` giống code Servlet.
2. **Xác thực (authentication):** các filter phù hợp với HTTP Basic, bearer token, form login hoặc cơ chế khác lấy credentials, chuyển thành `Authentication` và xác thực; nếu thất bại, handler/entry point được cấu hình có thể tạo 401 hoặc redirect.
3. **Xử lý exception bảo mật:** filter tương ứng xử lý các lỗi security như authentication/access denied theo cơ chế của framework. Nó có thể quyết định challenge, denied response, hoặc truyền lỗi lên trên.
4. **Ủy quyền (authorization):** `AuthorizationWebFilter` áp dụng `ReactiveAuthorizationManager` cho request; quyết định không đủ quyền có thể ngăn không cho đến handler.
5. **Đi tiếp:** nếu không bị chặn, security filters gọi phần `WebFilterChain` còn lại. WebFlux chạy route handler và ghi body.

Tên một số filter có thể gặp khi đọc mã nguồn hoặc TRACE: `ReactorContextWebFilter`, `AuthenticationWebFilter`, `ExceptionTranslationWebFilter`, `AuthorizationWebFilter`, `HeaderWriterWebFilter`, `CsrfWebFilter`. Chúng không được đảm bảo xuất hiện đầy đủ trong mỗi cấu hình. Có trường hợp những filter quản lý security context hoặc xử lý lỗi nằm trước/sau nhau theo thứ tự framework quy định, nên **không suy ra thứ tự runtime bằng thứ tự các dòng DSL trong `ServerHttpSecurity`**.

Hãy tách ba khái niệm:

- **Authentication:** ai đang truy cập? Chưa có credentials hoặc credentials sai thường kích hoạt luồng challenge.
- **Authorization:** người đó có quyền vào endpoint không? Một người hợp lệ vẫn có thể nhận 403.
- **Request handling:** controller/functional handler chạy sau khi security cho phép pipeline tiếp tục. Nếu chain dừng hoặc kết thúc với exception, handler không chạy.

Việc lấy `ReactiveSecurityContextHolder.getContext()` phải diễn ra theo API reactive; security context thường nằm trong Reactor Context của subscriber, không nên coi `SecurityContextHolder.getContext()` dựa trên ThreadLocal là nguồn chân lý cho luồng WebFlux.

## 8. Dừng chuỗi sớm, tín hiệu Mono và response

Một `WebFilter` phải trả `Mono<Void>`. Cách đi tiếp phổ biến là:

```java
// Mảnh ví dụ độc lập với routing, giả sử đã ở trong method WebFilter.filter.
return chain.filter(exchange);
```

Nếu muốn gắn logic trước/sau:

```java
return Mono.defer(() -> {
    log.debug("before");
    return chain.filter(exchange)
        .doOnError(error -> log.warn("failed", error))
        .doFinally(signal -> log.debug("finished: {}", signal));
});
```

Mảnh trên chỉ minh họa nội bộ hàm; `log` là logger do ứng dụng cung cấp. `doFinally` còn chạy khi `CANCEL`, và thứ tự in giữa các filter lồng nhau có thể bị ảnh hưởng bởi toán tử reactive. Không dùng `block()` hoặc I/O blocking trong `WebFilter` vì nó có thể chiếm thread event loop.

Một filter có thể trả `exchange.getResponse().setComplete()` mà **không** gọi `chain.filter(exchange)` để chủ động kết thúc response. Đây là hành vi hợp lệ cho các trường hợp đã thiết kế (chẳng hạn một kiểm tra protocol đặc biệt), nhưng nếu filter toàn cục chạy trước proxy và bỏ qua việc gọi chain, request đó **chưa đi qua Spring Security**. Việc trả `Mono.empty()` trực tiếp cũng không tự tạo quyết định bảo mật hoặc mã HTTP phù hợp; phải chịu trách nhiệm thiết lập response đúng.

**Phân biệt tình huống:**

| Điều xảy ra | Security/handler có tiếp tục không? |
| --- | --- |
| Global WebFilter gọi `chain.filter(exchange)` | Đến filter kế tiếp, có thể đến security proxy |
| Global WebFilter trả response trước khi gọi chain | Filter phía sau (kể cả proxy nếu đứng sau) và handler không chạy |
| Proxy không tìm thấy `SecurityWebFilterChain` khớp | Không áp dụng các security filters từ chain; WebFlux gốc vẫn đi tiếp |
| Authentication thành công | Có thể đến authorization; **chưa chắc được phép** |
| Authorization từ chối | Handler bị chặn; framework xử lý AccessDenied/authentication response |
| Security cho phép và các filter đi tiếp | Handler xử lý; response có thể hoàn tất, lỗi hoặc bị client hủy |

Đừng xử lý lỗi bằng cách vô điều kiện `onErrorResume(error -> chain.filter(exchange))` ở bên ngoài security proxy: nó có nguy cơ gọi lại luồng và đi vòng qua bước từ chối/lỗi bảo mật. Lỗi phải được xử lý ở đúng layer với hợp đồng rõ ràng; không thử chạy lại phần còn lại của chain vì đã bắt được exception.

## 9. Quan sát đúng hai lớp filter

Để hiểu đường đi khi debug, quan sát đồng thời:

**Lớp WebFlux:** các bean `WebFilter` toàn cục, `@Order`, request path, việc có gọi `chain.filter(exchange)` hay không. Với Spring Boot, `WebFilterChainProxy` thông thường ở order -100; một filter ở -200 có thể quan sát trước proxy, còn filter ở order 0 thường nằm sau proxy. Tuy nhiên, nếu security chặn request sớm thì filter chạy **sau proxy** có thể không được gọi.

**Lớp Spring Security:** các bean `SecurityWebFilterChain`, `@Order`, `securityMatcher`, danh sách filter nhận được từ `ServerHttpSecurity.build()` và authentication/authorization result. Bật TRACE ở môi trường phát triển khi cần, ví dụ trong `application.yml`:

```yaml
logging:
  level:
    org.springframework.security: TRACE
```

TRACE có thể hiển thị nhiều thông tin về request và security flow; chỉ bật khi debug có kiểm soát, tránh giữ log nhạy cảm ở môi trường thực. Với nhiều chain, hãy ghi lại path, chain được dự kiến khớp và phản hồi cuối cùng bằng test rõ ràng; không kết luận chain được chọn chỉ từ dòng log của một global WebFilter.

**Chèn filter đúng tầng:** Nếu muốn ghi nhận mọi request, dùng bean `WebFilter` toàn cục. Nếu muốn kiểm tra/bổ sung một bước **trong** cấu hình bảo mật đã chọn, thêm `WebFilter` qua `ServerHttpSecurity.addFilterBefore(...)`, `addFilterAfter(...)` hoặc `addFilterAt(...)` với mốc `SecurityWebFiltersOrder` thích hợp. Ví dụ mảnh cấu hình:

```java
// Mảnh code trong method cấu hình ServerHttpSecurity:
WebFilter traceBeforeAuthorization = (exchange, chain) -> {
    System.out.println("before security authorization");
    return chain.filter(exchange);
};
http.addFilterBefore(
    traceBeforeAuthorization,
    SecurityWebFiltersOrder.AUTHORIZATION
);
```

Cần import `org.springframework.security.config.web.server.SecurityWebFiltersOrder`. Filter bổ sung ở ví dụ này chỉ tham gia **security chain nơi bạn cấu hình nó**. Không coi vị trí đó là một authorization policy; muốn áp dụng kiểm tra quyền, dùng DSL/manager bảo mật tương ứng.

## 10. Kịch bản kiểm thử có ý nghĩa

Để chứng minh hiểu kiến trúc, kiểm tra các trường hợp sau thay vì chỉ kiểm tra endpoint thành công:

| Kịch bản | Chain dự kiến | Bằng chứng nên kiểm tra |
| --- | --- | --- |
| `/api/hello` thiếu credentials | API | Challenge/401; handler không trả `api-ok` |
| `/api/hello` có credentials hợp lệ | API | 200; handler trả `api-ok` |
| `/public/ping` không credentials | Fallback | 200; handler trả `pong` |
| `/internal/secret` có credentials hợp lệ | Fallback | 403; handler không trả `secret` |
| Chain `/api/**` đặt sau matcher mặc định khớp mọi path | Fallback có thể thắng | Test sẽ lộ cấu hình sai thứ tự |
| Chỉ khai báo chain `/api/**`, không có fallback | Không chain khớp `/internal/secret` | Security proxy không có security filters cho path này: phải bổ sung bảo vệ |
| Global WebFilter trước proxy tự kết thúc | Chưa vào proxy | Không thấy security check; phải giải thích rõ lý do dừng sớm |
| Matcher/filter phát lỗi | Không phải một quyết định ALLOW | Kiểm tra error handling, metric và response; không bỏ qua lỗi |

Trong test tích hợp, `WebTestClient` có thể gửi request vào WebFlux application với security chain thật. Nếu sử dụng mock authentication, cần nhớ mock không nhất thiết kiểm chứng được luồng HTTP Basic hay JWT thực. Vì vậy tách test **cơ chế xác thực** và test **quy tắc authorization**; đối với rủi ro bypass do chain matcher, bắt buộc có ca cho URL ngoài matcher ưu tiên.

## 11. Lỗi phổ biến và cách sửa

**Lỗi 1 — nhầm Servlet và WebFlux.** Dùng `FilterChainProxy`/`SecurityFilterChain` (Servlet) khi triển khai WebFlux làm lệch API và cơ chế thực thi. Dùng `WebFilterChainProxy` và `SecurityWebFilterChain` đúng package `org.springframework.security.web.server`.

**Lỗi 2 — tưởng có nhiều chain thì tất cả được chạy.** Proxy lấy **match đầu tiên**; chain kế tiếp không được chạy khi đã có chain khớp. Đặt matcher cụ thể trước và matcher tổng quát cuối.

**Lỗi 3 — nhầm `securityMatcher` với `pathMatchers`.** Cái đầu chọn chain, cái sau chọn quyền **trong chain đó**. Nếu chỉ cấu hình pathMatchers của chain chưa bao giờ được chọn, rule sẽ không áp dụng.

**Lỗi 4 — không có chain dự phòng.** Đường dẫn ngoài matcher có thể đến handler mà không qua các security filter của Spring Security. Dùng chain bắt tất cả và chính sách mặc định từ chối hoặc một thiết kế bao phủ rõ ràng.

**Lỗi 5 — thêm global WebFilter rồi tưởng là security filter nội bộ.** `@Order` của bean toàn cục điều khiển vị trí quanh proxy; `SecurityWebFiltersOrder` định vị filter bên trong chain được chọn. Chọn đúng API.

**Lỗi 6 — global filter dừng trước proxy.** Trả `setComplete()` mà không gọi `chain.filter(exchange)` có thể là bypass. Khi đây là chủ ý, kiểm thử rõ endpoint/response và bảo vệ thích hợp.

**Lỗi 7 — dùng `block()` trong filter.** Reactor/WebFlux được thiết kế không chặn luồng; thay bằng `flatMap`, `then` hoặc operator reactive khác.

**Lỗi 8 — kết luận sai từ status hoặc log.** `401`, `403`, `400` của firewall, lỗi `5xx` và `Mono<Void>` hoàn tất là các sự kiện khác nhau. Một response hoàn tất không chứng minh request đã chạy qua handler hay được authorization cấp quyền.

**Lỗi 9 — log toàn bộ credentials/token khi debug.** Chỉ log metadata đủ để kiểm tra chain/path và dùng TRACE bảo mật khi cần có kiểm soát.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một request `/api/orders/1` khớp cả `apiChain` và `fallbackChain`. Có bao nhiêu `SecurityWebFilterChain` được chạy? **Một**: chain đầu tiên khớp theo thứ tự ưu tiên.

**Câu 2.** Dùng `.pathMatchers("/public/**").permitAll()` trong `fallbackChain` có làm `apiChain` bỏ qua security cho `/public/**` không? **Không**. `pathMatchers` quy định authorization trong chain đã được chọn; `securityMatcher` mới quyết định request vào chain nào.

**Câu 3.** Khi `WebFilterChainProxy` không tìm ra chain nào khớp, mặc định có tự ném 403 không? **Không**. Nó có thể tiếp tục `WebFilterChain` gốc mà không cài thêm security filter cho request; đây là rủi ro cấu hình cần kiểm thử.

**Câu 4.** `@Order(-200)` của global WebFilter và `@Order(1)` của security chain có cùng ý nghĩa không? **Không**. Một cái điều khiển thứ tự WebFilter trong WebFlux; cái còn lại điều khiển thứ tự xét matcher của các security chain.

**Câu 5.** Vì sao không được dùng `Mono.empty()` từ một custom WebFilter như cách trả 403? Vì nó chỉ phát tín hiệu hoàn tất rỗng, không tự mang quyết định từ chối hoặc status 403. Muốn dừng, phải thực hiện response/error handling rõ ràng và đặt filter đúng tầng.

**Ghi nhớ:** Request đi qua **chuỗi WebFilter của WebFlux**; `WebFilterChainProxy` là **một WebFilter** nằm trong chuỗi đó; proxy chọn **SecurityWebFilterChain đầu tiên khớp** rồi gắn **security WebFilter** của chain được chọn vào phần thực thi tiếp theo. Matcher quyết định *chain nào*, authorization quyết định *có quyền hay không*, còn WebFlux handler chỉ chạy khi pipeline cho phép đi tới nó.

## Tài liệu tham khảo

- [Spring Framework — WebFlux Reactive Core, Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — contract `WebFilter` và cách đăng ký `WebFilter`.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html) — tự động nhận bean `WebFilter` và thứ tự mặc định của proxy trong Boot.
- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `securityMatcher`, `@Order`, `ServerHttpSecurity`.
- [Spring Security — SecurityWebFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html) — `matches` và `getWebFilters`.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — `addFilterBefore`, `addFilterAfter`, `addFilterAt`.
- [Spring Security — WebFilterChainProxy source](https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/server/WebFilterChainProxy.java) — kiểm chứng cách proxy chọn chain đầu tiên và nối bộ lọc.
