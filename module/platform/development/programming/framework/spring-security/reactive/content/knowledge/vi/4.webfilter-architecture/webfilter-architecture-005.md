# Vai trò của ReactorContextWebFilter và SecurityContextServerWebExchangeWebFilter

## 1. Vì sao cần hai WebFilter liên quan đến SecurityContext?

Trong Spring Security Reactive, một HTTP request của Spring WebFlux đi qua nhiều `WebFilter` trước khi đến handler. Framework không thể giả định mọi giai đoạn xử lý đều chạy trên một thread. Vì vậy, thông tin bảo mật của request được truyền qua **Reactor Context** trong subscription đang thực thi, thay vì dựa vào `ThreadLocal` như nhiều ví dụ Spring MVC/Servlet.

Hai filter có tên dễ nhầm lẫn nhưng thực hiện **hai nhiệm vụ riêng**:

1. **`ReactorContextWebFilter`** lấy `SecurityContext` từ một `ServerSecurityContextRepository` và cung cấp nó cho `ReactiveSecurityContextHolder` trong Reactor Context của chuỗi xử lý request.
2. **`SecurityContextServerWebExchangeWebFilter`** trang trí (`decorate`) `ServerWebExchange` để lời gọi `exchange.getPrincipal()` tra cứu principal từ `ReactiveSecurityContextHolder`.

Nói cách khác, một filter tạo cầu nối **repository → Reactor Context**, filter còn lại tạo cầu nối **Reactor Context → API `ServerWebExchange.getPrincipal()`**.

Đây không phải hai filter đăng nhập độc lập. Chúng không tự giải mã mật khẩu, không tự xác thực JWT, không tự quyết định quyền truy cập và không thay thế `AuthenticationWebFilter` hoặc các thành phần authorization.

Sau bài học, bạn sẽ:
- Chỉ rõ đầu vào, đầu ra và trách nhiệm của từng filter.
- Phân biệt `SecurityContext`, `Authentication`, `Principal`, `ServerSecurityContextRepository`, Reactor Context và `ServerWebExchange`.
- Mô tả các tình huống context đến từ phiên đăng nhập đã lưu hoặc từ authentication mới trong request hiện tại.
- Dùng cả `ReactiveSecurityContextHolder.getContext()` và `ServerWebExchange.getPrincipal()` trong một API WebFlux thực sự chạy được.
- Chẩn đoán các lỗi mất context, nhầm lẫn stateless/session, tự subscribe, block và thay đổi filter order.

## 2. Các đối tượng tham gia: đừng đồng nhất chúng

| Thành phần | Bản chất | Vai trò |
| --- | --- | --- |
| `Authentication` | Interface thuộc Spring Security, đồng thời có tính chất `Principal` | Giữ danh tính, trạng thái xác thực và authorities của người gọi |
| `SecurityContext` | Đối tượng chứa `Authentication` | Cung cấp thông tin bảo mật cho một chuỗi xử lý |
| `ReactiveSecurityContextHolder` | API truy cập `SecurityContext` từ Reactor Context | `getContext()` trả về `Mono<SecurityContext>` |
| Reactor `Context` | Ngữ cảnh gắn với subscription Reactor | Truyền dữ liệu theo chuỗi reactive kể cả khi chuyển thread |
| `ServerWebExchange` | Abstraction cho HTTP request/response của WebFlux | Cung cấp request, response, attributes, `getPrincipal()`, v.v. |
| `ServerSecurityContextRepository` | Strategy `load(exchange)` / `save(exchange, context)` | Lưu và/hoặc tải context tùy cơ chế session/stateless |
| `ReactorContextWebFilter` | WebFilter trong security chain | Khởi tạo quyền truy cập context từ repository trong Reactor |
| `SecurityContextServerWebExchangeWebFilter` | WebFilter trong security chain | Làm cho `exchange.getPrincipal()` đọc principal từ reactive security context |

**`SecurityContext` khác `Authentication`:** `SecurityContext` là lớp bao; `context.getAuthentication()` mới lấy đối tượng có danh tính và authorities. Không phải mọi `Authentication` đều là bằng chứng người dùng thực sự đã đăng nhập: hệ thống còn có thể dùng anonymous authentication và các authentication token chưa xác thực tùy đường xử lý. Việc cho phép truy cập phải dựa vào bộ phận authorization, không phải chỉ vì một object không null.

**`ServerWebExchange` khác Reactor Context:** `ServerWebExchange` mô tả tương tác HTTP của request. Reactor Context là dữ liệu ngữ cảnh của subscription. Spring Security kết nối hai thế giới này bằng các filter và API holder; chúng không tự động là một object duy nhất.

## 3. Vai trò chính xác của `ReactorContextWebFilter`

API của Spring Security mô tả `ReactorContextWebFilter` là một `WebFilter` dùng `ServerSecurityContextRepository` để cung cấp `SecurityContext` phục vụ khởi tạo `ReactiveSecurityContextHolder`.

Các bước khái niệm:

1. Filter nhận `ServerWebExchange` và `WebFilterChain`.
2. Nó có một `ServerSecurityContextRepository` được cấu hình.
3. Repository có thể tải `Mono<SecurityContext>` tương ứng với exchange.
4. Filter khiến publisher context đó có thể được truy cập trong Reactor Context của chuỗi phía sau, thông qua cơ chế của `ReactiveSecurityContextHolder`.
5. Các thành phần downstream có thể gọi `ReactiveSecurityContextHolder.getContext()` để đọc context khi subscription thực sự chạy.

Sơ đồ:

~~~text
HTTP request
    |
    v
ServerWebExchange
    |
    v
ReactorContextWebFilter
    |
    |  ServerSecurityContextRepository.load(exchange)
    |                 |
    |          Mono<SecurityContext>
    |                 |
    +--> Reactor Context của subscription
                   |
                   v
         ReactiveSecurityContextHolder.getContext()
                   |
                   v
          Authentication / principal
~~~

**Đây là cơ chế nạp/cung cấp context, không phải thao tác xác thực thông tin đăng nhập.** Nếu repository trả `Mono.empty()`, không thể kết luận filter đã “đánh rớt” request; authentication filter khác vẫn có thể nhận credentials hiện tại và tạo authentication mới.

### 3.1. Repository có nghĩa gì?

`ServerSecurityContextRepository` có hai phương thức cốt lõi:

~~~java
Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
Mono<SecurityContext> load(ServerWebExchange exchange);
~~~

Đây là **chữ ký API minh họa**, không phải một chương trình Java độc lập. `load` trả về `Mono.empty()` khi không tìm thấy context; nó không trả `null`.

Hai implementation quan trọng:
- `WebSessionServerSecurityContextRepository`: lưu `SecurityContext` trong `WebSession`; thích hợp với cơ chế dựa trên phiên khi authentication được lưu đúng cách.
- `NoOpServerSecurityContextRepository`: không lưu context và không tải lại context đã lưu. Phù hợp khi không cần persistence qua request, chẳng hạn nhiều cấu hình Bearer token stateless.

Lưu ý: **repository được dùng để nạp context không tự động bảo đảm authentication mới được lưu.** Việc xác thực thành công có được lưu hay không còn phụ thuộc cơ chế authentication và repository mà authentication filter sử dụng. Không chỉ nhìn thấy bean `WebSessionServerSecurityContextRepository` mà kết luận mọi login đều được ghi vào session.

### 3.2. `ReactiveSecurityContextHolder` đọc ở đâu?

Lệnh:

~~~java
Mono<SecurityContext> contextMono =
        ReactiveSecurityContextHolder.getContext();
~~~

không truy vấn trực tiếp database, không lấy một biến toàn cục theo thread và không gọi HTTP API. Nó lấy context bảo mật từ **Reactor Context đang gắn với subscription**; context đó có thể đã được `ReactorContextWebFilter` làm sẵn từ repository hoặc được thành phần authentication đưa vào pipeline của request.

Để xử lý danh tính:

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

Đoạn trên là ví dụ cú pháp, cần các import tương ứng khi đặt trong class. `Mono` có thể trống nếu không có SecurityContext trong ngữ cảnh đang đọc. Với endpoint yêu cầu authentication, hãy để security chain từ chối người chưa xác thực trước khi đến handler.

### 3.3. Reactor Context không phải `ThreadLocal`

Một pipeline có thể chuyển scheduler mà vẫn mang theo Reactor Context vì context đi theo subscription:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .map(name -> "Hello " + name);
~~~

Cần import `reactor.core.scheduler.Schedulers` nếu dùng đoạn minh họa này. `publishOn` trong cùng chain **không mặc nhiên làm mất Reactor Context**. Ngược lại, gọi `subscribe()` ở một đoạn code khác tạo subscription mới; tự mở `Thread` hoặc `CompletableFuture.runAsync` cũng không tự mang theo ngữ cảnh của HTTP request.

## 4. Vai trò chính xác của `SecurityContextServerWebExchangeWebFilter`

API chính thức mô tả filter thứ hai: nó thay cách `ServerWebExchange.getPrincipal()` hoạt động để principal được tra cứu bằng `ReactiveSecurityContextHolder`.

Trong WebFlux, code downstream có thể hỏi:

~~~java
Mono<? extends Principal> principal = exchange.getPrincipal();
~~~

Nhờ `SecurityContextServerWebExchangeWebFilter`, exchange được chuyển xuống handler thông qua một wrapper có thể tính `getPrincipal()` từ security context reactive. Thành phần liên quan là **`SecurityContextServerWebExchange`**, một `ServerWebExchangeDecorator`.

Sơ đồ:

~~~text
Reactor Context đang chứa Mono<SecurityContext>
                         |
                         v
             ReactiveSecurityContextHolder
                         |
                         v
SecurityContextServerWebExchangeWebFilter
                         |
                         v
           SecurityContextServerWebExchange
                         |
                         v
             exchange.getPrincipal()
                         |
                         v
                  Mono<Principal>
~~~

Điểm then chốt:
- Filter này **không** tự gọi repository để nạp context; đó là nhiệm vụ của filter/ngữ cảnh trước nó.
- Filter này **không** xác thực username/password/JWT.
- Filter này **không** cấp hoặc thay đổi roles/authorities.
- Nó cung cấp một cách đọc principal nhất quán cho code dùng API chuẩn `ServerWebExchange.getPrincipal()`.
- Việc decorate exchange dành cho các thành phần **downstream**. Một WebFilter chạy ở vị trí sớm hơn, giữ bản exchange ban đầu, không nên giả định đã nhận được wrapper của filter chạy sau.

### 4.1. Tại sao cần `getPrincipal()` trong khi đã có holder?

Nhiều thành phần WebFlux được thiết kế để làm việc với giao diện HTTP chung `ServerWebExchange`, `Principal` hoặc các handler argument như `Principal`/`Mono<Principal>`. Chúng không nhất thiết phụ thuộc trực tiếp vào API nội bộ của Spring Security.

Khi `getPrincipal()` lấy dữ liệu từ holder, handler có thể thấy danh tính do chính security chain đã xác thực mà không tự tra cứu session, parse token hoặc tham chiếu `ThreadLocal`. Đồng thời, các thành phần cần authorities, thông tin credential type hoặc `Authentication` đầy đủ vẫn có thể truy cập `ReactiveSecurityContextHolder`.

### 4.2. Đừng nhầm chiều của cầu nối

`ReactorContextWebFilter` làm cho security context từ repository trở nên có thể truy cập trong Reactor Context.

`SecurityContextServerWebExchangeWebFilter` làm cho `exchange.getPrincipal()` có thể truy cập principal **từ** Reactor Context.

Vì thế, không nên mặc định rằng việc tự thay `ServerWebExchange.getPrincipal()` là đủ để sửa `ReactiveSecurityContextHolder`, hay việc gán một attribute tùy ý vào exchange sẽ tự trở thành authentication được tin cậy.

## 5. Hai filter đứng ở đâu trong SecurityWebFilterChain?

Cấu hình Spring Security WebFlux thường tạo một bean `SecurityWebFilterChain` bằng `ServerHttpSecurity`. Khi request phù hợp matcher, security filters được sắp xếp theo các vị trí do `SecurityWebFiltersOrder` mô tả. Hai vị trí có tên chính thức:

- `SecurityWebFiltersOrder.REACTOR_CONTEXT`: dành cho `ReactorContextWebFilter`.
- `SecurityWebFiltersOrder.SECURITY_CONTEXT_SERVER_WEB_EXCHANGE`: dành cho `SecurityContextServerWebExchangeWebFilter`.

Trong chuỗi mặc định của dòng Spring Security 6.x, bước Reactor Context được bố trí trước các vị trí authentication HTTP phổ biến; bước trang trí exchange được đặt sau những vị trí authentication đó và trước nhiều bước downstream như authorization. Cấu hình thực tế có thể bao gồm hoặc bỏ các filter khác tùy HTTP Basic, form login, OAuth2/JWT, CSRF, CORS, anonymous authentication và matcher của các chain.

Hình dung tổng thể:

~~~text
Request
  |
  v
WebFilterChainProxy / SecurityWebFilterChain phù hợp
  |
  +--> ReactorContextWebFilter
  |     nạp SecurityContext từ repository vào Reactor Context
  |
  +--> Authentication filter(s) phù hợp
  |     xác minh credential/token khi request có thông tin xác thực
  |     đưa Authentication đã tạo vào security context của request
  |
  +--> SecurityContextServerWebExchangeWebFilter
  |     cho getPrincipal() đọc từ ReactiveSecurityContextHolder
  |
  +--> Authorization / các filter bảo vệ khác
  |     kiểm tra quyền hoặc áp dụng chính sách liên quan
  |
  v
WebFlux handler / controller / reactive service
~~~

**Sơ đồ mang tính khái niệm:** không cố tái hiện đầy đủ từng filter, thứ tự chi tiết hoặc nhánh logic theo mọi phiên bản Spring Security. Những filter như CORS, CSRF, login, logout, exception translation, anonymous authentication có vị trí và điều kiện kích hoạt riêng. Khi cấu hình custom filter, dùng `SecurityWebFiltersOrder` thay vì dựa vào trực giác về thứ tự xuất hiện trong file Java.

Lưu ý sự khác biệt với Servlet:
- Reactive: `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebFilter`, `ReactiveSecurityContextHolder`, `ServerSecurityContextRepository`.
- Servlet: `HttpSecurity`, `SecurityFilterChain`, Servlet `Filter`, các cơ chế `SecurityContextHolder`/repository tương ứng.

Không sử dụng API Servlet chỉ vì tên filter gần giống.

## 6. Hai luồng cụ thể: session và Bearer token

### 6.1. Luồng có session/context đã lưu

Giả sử ứng dụng dùng `WebSessionServerSecurityContextRepository` và trước đó một cơ chế login **đã lưu thành công** `SecurityContext` vào session:

1. Browser gửi cookie session.
2. `ReactorContextWebFilter` có thể nạp context gắn với `ServerWebExchange` từ repository.
3. Downstream `ReactiveSecurityContextHolder.getContext()` đọc được authentication đã lưu.
4. `SecurityContextServerWebExchangeWebFilter` giúp `exchange.getPrincipal()` trả về principal tương ứng.
5. Authorization kiểm tra quyền, rồi handler được gọi nếu đủ điều kiện.

Điều kiện “đã lưu thành công” là quan trọng. Chỉ có cookie hoặc một `WebSession` không đồng nghĩa tồn tại authenticated `SecurityContext`.

### 6.2. Luồng stateless với JWT

Giả sử API dùng OAuth2 Resource Server, client gửi Bearer token trên **từng request** và không cần lưu authentication vào session:

1. Repository có thể là no-op, nên `ReactorContextWebFilter` không tải được context của request trước.
2. Authentication filter phù hợp kiểm tra Bearer token (chữ ký, thời hạn, issuer/audience theo cấu hình), tạo `Authentication` cho request hiện tại.
3. Spring Security đưa authentication hiện tại vào reactive security context của pipeline.
4. Filter trang trí exchange giúp `getPrincipal()` phản ánh authentication của request.
5. Authorization kiểm tra scopes/roles/authorities được ánh xạ, còn quyền sở hữu dữ liệu vẫn phải kiểm tra theo nghiệp vụ.

**Không có mâu thuẫn** khi repository no-op nhưng handler vẫn đọc được principal. Repository kiểm soát cách tải/lưu **giữa các request**, còn security context trong **request hiện tại** có thể được tạo từ credentials/token vừa kiểm tra.

Điều quan trọng là không trình bày `ReactorContextWebFilter` như “filter giải mã JWT” hoặc `SecurityContextServerWebExchangeWebFilter` như “filter đăng nhập”. Authentication thuộc một bước khác trong chain.

## 7. Ví dụ WebFlux chạy được: đọc cùng danh tính theo hai đường

Ví dụ dùng Java 17, Spring Boot 3.3.13 và Gradle. Đây là bản học tập để quan sát tên principal; tài khoản/password và HTTP Basic được cấu hình tối giản cho môi trường local.

Cấu trúc:

~~~text
reactive-context-filter-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── SecurityConfig.java
    └── WhoAmIController.java
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactive-context-filter-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**`src/main/java/demo/DemoApplication.java`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/demo/SecurityConfig.java`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(learner);
    }
}
~~~

**`src/main/java/demo/WhoAmIController.java`**

~~~java
package demo;

import java.security.Principal;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/whoami")
    public Mono<Map<String, String>> whoAmI(ServerWebExchange exchange) {
        Mono<String> fromContext = ReactiveSecurityContextHolder
                .getContext()
                .map(context -> context.getAuthentication())
                .map(Authentication::getName);

        Mono<String> fromExchange = exchange
                .<Principal>getPrincipal()
                .map(Principal::getName);

        return Mono.zip(fromContext, fromExchange)
                .map(names -> Map.of(
                        "reactorContext", names.getT1(),
                        "exchangePrincipal", names.getT2()));
    }
}
~~~

Giải thích:
- `fromContext` sử dụng API reactive bảo mật, phù hợp khi cần cả `Authentication`, authorities, v.v.
- `fromExchange` chỉ lấy `Principal` qua API WebFlux. Filter trang trí exchange là cầu nối giúp API này dùng cùng security context.
- `Mono.zip` chờ cả hai publisher phát giá trị. Vì `/whoami` yêu cầu xác thực hợp lệ, ví dụ mong đợi cả hai đều có tên `learner`. Nếu một trong hai `Mono` rỗng, `zip` có thể hoàn thành rỗng; đó là hành vi Reactor, không phải lỗi do JSON serializer.
- Controller không tự `block()` hoặc `subscribe()`; WebFlux là thành phần subscribe vào publisher trả về.
- Cấu hình này **không tự triển khai** hai filter, vì Spring Security đã gắn chúng vào security chain khi phù hợp. Không nên tạo thêm filter trùng lặp để “bật” chức năng.

### Chạy thử

Từ thư mục chứa `build.gradle`, chạy:

~~~bash
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun`. Khi server đang chạy trên cổng mặc định 8080, mở terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/whoami
curl -i -u learner:localpass http://localhost:8080/whoami
curl -i -u learner:wrong http://localhost:8080/whoami
~~~

Kết quả mong đợi:

| Request | HTTP status | Kết quả có ý nghĩa |
| --- | --- | --- |
| `GET /public`, không credentials | **200 OK** | Body `public` |
| `GET /whoami`, không credentials | **401 Unauthorized** | Route yêu cầu đăng nhập; HTTP Basic có thể trả header `WWW-Authenticate` |
| `GET /whoami`, đúng `learner:localpass` | **200 OK** | JSON có `reactorContext = learner` và `exchangePrincipal = learner` |
| `GET /whoami`, sai password | **401 Unauthorized** | Không tạo authenticated principal hợp lệ |

JSON response thành công biểu diễn các giá trị:

~~~json
{
  "reactorContext": "learner",
  "exchangePrincipal": "learner"
}
~~~

**Thứ tự các key JSON không được bảo đảm**, vì ví dụ dùng `Map.of`. Body lỗi, thông điệp và headers cũng có thể thay đổi theo phiên bản/cấu hình của Spring Security.

**Lưu ý an toàn:** `{noop}` nghĩa là password không hash, chỉ phục vụ demo local. Không dùng username/password hard-code hoặc HTTP Basic qua kết nối không mã hóa trong môi trường sản xuất; bảo vệ credentials bằng HTTPS và dùng password encoder mạnh/kho secrets phù hợp. Spring Boot 3.3.13 ở đây là phiên bản minh họa để chạy bài; dự án thực tế phải dùng nhánh đang được hỗ trợ và cập nhật bảo mật.

### Thí nghiệm để hiểu “repository không phải authentication”

Trong demo, mỗi lệnh `curl -u` gửi HTTP Basic credentials trực tiếp trên request. Dù cơ chế persistence giữa các request được thay đổi, một request có credentials hợp lệ vẫn có thể được `AuthenticationWebFilter` xác thực và đặt principal vào pipeline. Đừng dùng kết quả `/whoami` với HTTP Basic để kết luận chắc chắn rằng user đã được lưu vào session.

Nếu muốn chứng minh session persistence, cần một ví dụ riêng có cơ chế login thực sự **save** context vào `WebSessionServerSecurityContextRepository` và một request sau đó dùng lại session mà không gửi credentials. Đây là ca kiểm thử khác với ví dụ HTTP Basic hiện tại.

## 8. Tự kiểm tra bằng một phép thử có kiểm soát

Ví dụ dưới đây minh họa cách **tự đưa** một Authentication vào Reactor Context ở ngoài HTTP request để quan sát `ReactiveSecurityContextHolder`. Nó không tạo `ServerWebExchange`, nên không trực tiếp kiểm thử filter trang trí exchange.

~~~java
// Đoạn minh họa trong code đã có các dependency Spring Security + Reactor.
Authentication auth = new UsernamePasswordAuthenticationToken(
        "test-user", "N/A",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
~~~

Nếu subscribe `name` trong một bài test với `StepVerifier` hoặc dùng `block()` **ngoài** event-loop tại biên console, kết quả là `test-user`. Cần import `Authentication`, `UsernamePasswordAuthenticationToken`, `AuthorityUtils` và `Mono` khi đặt code trong class.

Ví dụ này chứng minh holder đọc dữ liệu từ Reactor Context; **không chứng minh** `ReactorContextWebFilter` đã tải context từ repository. Hai filter chỉ hoạt động đầy đủ khi một `SecurityWebFilterChain` có request/exchange đang chạy.

## 9. Những lỗi hay gặp khi đọc context và principal

### Lỗi 1 — Nghĩ `ReactorContextWebFilter` tự xác thực token

**Sai:** “Có ReactorContextWebFilter thì JWT tự hợp lệ.”

**Đúng:** Nó làm cho security context đã được repository cung cấp có mặt trong reactive pipeline. Resource Server authentication phải dùng cấu hình OAuth2/JWT và kiểm tra token riêng. Khi JWT hợp lệ, authentication filter đưa kết quả vào context request; còn `SecurityContextServerWebExchangeWebFilter` phản ánh principal đó qua exchange.

### Lỗi 2 — Nghĩ filter trang trí exchange là nơi lưu session

**Sai:** “`SecurityContextServerWebExchangeWebFilter` ghi principal vào WebSession.”

**Đúng:** Vai trò được tài liệu mô tả là thay `ServerWebExchange.getPrincipal()` bằng cơ chế tra cứu từ `ReactiveSecurityContextHolder`. Persistence thuộc `ServerSecurityContextRepository` và cơ chế save của authentication flow.

### Lỗi 3 — Context không tồn tại sau khi tự `subscribe()`

~~~java
// SAI: tách subscription khỏi publisher của HTTP request.
auditService.writeEvent(event).subscribe();
return Mono.just("ok");
~~~

Một publisher được subscribe riêng không được bảo đảm có Reactor Context đã gắn với request. Lỗi của audit cũng có thể xảy ra sau khi trả response, không đi vào luồng lỗi của request.

Khi audit là điều kiện hoàn thành request, ghép nó vào một chain:

~~~java
return auditService.writeEvent(event)
        .thenReturn("ok");
~~~

Nếu audit thực sự cần chạy lâu hơn HTTP response, hãy dùng job/queue/outbox có vòng đời riêng và truyền actor ID đã xác thực dưới dạng dữ liệu rõ ràng.

### Lỗi 4 — Gọi `block()` để lấy SecurityContext

~~~java
// SAI bên trong handler/service reactive.
Authentication auth = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .block();
~~~

`block()` tạo subscription mới và chặn thread; trên event-loop có thể phát sinh lỗi blocking, đồng thời context request không được bảo đảm truyền sang subscription mới.

Đúng hơn:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .flatMap(auth -> orderService.findOrdersFor(auth.getName()));
~~~

Đoạn trên là mã tích hợp minh họa; cần service và imports tương ứng để chạy.

### Lỗi 5 — Đọc `SecurityContextHolder` ThreadLocal theo phong cách Servlet

Một request WebFlux có thể chuyển thread khi đi qua các bước Reactor. Vì vậy, không nên coi `SecurityContextHolder.getContext()` kiểu `ThreadLocal` là nguồn danh tính mặc định của request. Dùng `ReactiveSecurityContextHolder`, hoặc `exchange.getPrincipal()` trong handler nhận exchange đã được filter xử lý.

### Lỗi 6 — Gọi `exchange.getPrincipal()` quá sớm trong custom WebFilter

Một custom filter chạy **trước** `SecurityContextServerWebExchangeWebFilter` có thể nhận exchange chưa được trang trí. Nếu cần dùng principal do Spring Security tạo, hãy chọn vị trí tương thích trong chain; không tự chỉnh order của các filter nội bộ hoặc giả định wrapper đã tồn tại từ đầu request.

### Lỗi 7 — Không có principal nhưng chỉ kiểm tra xem repository có bean không

Xác minh theo thứ tự:
1. Request có đi qua đúng `SecurityWebFilterChain` và security matcher không?
2. Có cơ chế xác thực phù hợp với Basic/Bearer/session và credentials hợp lệ không?
3. `ServerSecurityContextRepository.load(exchange)` có được mong đợi tìm thấy context đã lưu không?
4. Nếu là stateless, authentication mới có được đưa vào Reactor Context của **request hiện tại** không?
5. Code downstream có ở trong cùng reactive chain hay đã tách subscription?
6. Với `getPrincipal()`, exchange đã đi qua filter trang trí chưa?
7. Route có được cho phép đối với anonymous hay không, và authentication có tồn tại như kỳ vọng không?

Không log toàn bộ `SecurityContext`, password, Authorization header hoặc JWT để debug. Chỉ log thông tin phi nhạy cảm cần thiết và correlation ID phù hợp.

## 10. Kiểm thử đúng trách nhiệm từng lớp

Không nên chỉ kiểm thử controller trả 200. Một ma trận tối thiểu:

| Kịch bản | Điều cần kiểm chứng |
| --- | --- |
| Public request, chưa đăng nhập | Route công khai hoạt động, nhưng đừng mặc định `getPrincipal()` rỗng nếu anonymous authentication được bật |
| Protected request, không credentials | Bị từ chối theo entry point phù hợp, ví dụ Basic thường là 401 |
| Protected request, credentials hợp lệ | `ReactiveSecurityContextHolder` và `exchange.getPrincipal()` phản ánh cùng tên người gọi |
| Credentials sai | Không có authentication hợp lệ và route bảo vệ bị từ chối |
| Authentication hợp lệ nhưng thiếu authority | Authorization từ chối (thường 403), dù principal đã hiện diện |
| Stateful login có lưu session | Request tiếp theo dùng session có thể tải lại security context |
| Stateless Bearer token | Mỗi request phải tự cung cấp token; `NoOpServerSecurityContextRepository` không duy trì login qua request |
| Custom operator đổi scheduler trong cùng chain | Reactor Context vẫn truy cập được khi không tạo subscription độc lập |
| Tác vụ tự subscribe ngoài chain | Phát hiện và tránh phụ thuộc vào request context hoặc request cancellation |

Khi dùng `WebTestClient` và các công cụ Spring Security Test, kiểm tra quyền theo URL lẫn method, đồng thời kiểm tra quyền sở hữu dữ liệu ở service nếu ứng dụng có multi-user resources. `getPrincipal()` có tên đúng **không tự chứng minh** người gọi có quyền với mọi tài nguyên.

Một cách quan sát thực tế: trong endpoint `/whoami`, so sánh hai trường JSON sau khi gọi bằng cùng tài khoản. Nếu chúng không khớp hoặc publisher bị rỗng dù request đã xác thực, xem lại việc compose pipeline, custom filters, principal mapping và security chain matcher trước khi đoán lỗi do Reactor chuyển thread.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Filter nào dùng `ServerSecurityContextRepository` để làm SecurityContext khả dụng trong Reactor Context?

> `ReactorContextWebFilter`.

**Câu 2.** Filter nào giúp `ServerWebExchange.getPrincipal()` đọc danh tính từ `ReactiveSecurityContextHolder`?

> `SecurityContextServerWebExchangeWebFilter`, thông qua exchange được trang trí.

**Câu 3.** Nếu dùng `NoOpServerSecurityContextRepository`, một request Bearer token hợp lệ có thể có principal không?

> Có. Authentication trong request hiện tại có thể được authentication filter tạo và gắn vào Reactor Context; no-op repository chỉ không cung cấp persistence qua các request.

**Câu 4.** Sau khi login dùng WebSession, vì sao request sau vẫn không có context dù repository được cấu hình?

> Cần kiểm tra authentication flow có thực sự lưu `SecurityContext` vào repository không, cookie/session có được gửi lại không và request có đi qua đúng security chain không.

**Câu 5.** `exchange.getPrincipal()` và `ReactiveSecurityContextHolder.getContext()` có cùng kiểu dữ liệu trả về không?

> Không. `getPrincipal()` trả `Mono` của `Principal`; holder trả `Mono<SecurityContext>`, từ đó có thể đọc `Authentication`.

**Câu 6.** Vì sao không đọc security context bằng `block()` trong controller WebFlux?

> Vì nó chặn thread và tạo subscription mới, có thể phá vỡ kết nối với Reactor Context của request.

**Câu 7.** Hai filter này có thay `AuthenticationWebFilter` hoặc `AuthorizationWebFilter` không?

> Không. Chúng nối các cách biểu diễn và truy cập context/principal; xác thực credentials và quyết định quyền vẫn do các thành phần khác thực thi.

## 12. Tổng kết

Trong kiến trúc WebFilter của Spring Security Reactive, **`ReactorContextWebFilter` bảo đảm context có thể được nạp từ repository vào luồng Reactor**, còn **`SecurityContextServerWebExchangeWebFilter` làm cho API `ServerWebExchange.getPrincipal()` phản ánh security context của luồng đó**. Hai filter hỗ trợ các thành phần xác thực và phân quyền, nhưng không trực tiếp thay thế chúng.

Điều cần nhớ nhất khi áp dụng:
- Phân biệt rõ **persistence giữa request** với **security context của request hiện tại**.
- Đọc danh tính trong pipeline bằng `ReactiveSecurityContextHolder` hoặc `exchange.getPrincipal()` tại đúng vị trí của security chain.
- Giữ công việc cần authorization trong cùng reactive chain; không tự subscribe hoặc block trong WebFlux handler.
- Xác minh riêng authentication, authorization, context propagation và hành vi session/stateless khi gặp lỗi.

### Tài liệu chính thức

- Spring Security Javadoc — `ReactorContextWebFilter`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/ReactorContextWebFilter.html
- Spring Security Javadoc — `SecurityContextServerWebExchangeWebFilter`: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html
- Spring Security Javadoc — `ServerSecurityContextRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- Spring Security Javadoc — `SecurityWebFiltersOrder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security Reference — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Reactor Reference — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html