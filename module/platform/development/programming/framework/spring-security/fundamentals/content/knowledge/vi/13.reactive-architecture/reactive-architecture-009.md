# Lựa chọn Servlet hay reactive theo toàn bộ kiến trúc ứng dụng

> **Bối cảnh:** Spring Security fundamentals → Kiến trúc reactive. Bài này giúp quyết định kiến trúc cho một ứng dụng Spring có bảo mật, từ HTTP đầu vào đến dữ liệu, dịch vụ bên ngoài, transaction, vận hành và kiểm thử.

## 1. Câu hỏi cần trả lời trước khi chọn công nghệ

Servlet (thường là **Spring MVC**) và reactive (thường là **Spring WebFlux**) đều có thể xây dựng ứng dụng web an toàn. Khác biệt chính là **mô hình xử lý I/O, quản lý đồng thời và cách truyền ngữ cảnh thực thi**; lựa chọn HTTP framework còn ảnh hưởng đến Security, persistence, transaction, client HTTP, thư viện tích hợp, giám sát và năng lực nhóm.

Không nên quyết định chỉ từ một controller có trả về `Mono`/`Flux` hay không, cũng không nên mặc định “reactive nhanh hơn”. Hãy trả lời ba câu hỏi:

1. **Đường đi của request có thực sự non-blocking từ đầu đến cuối?** Nếu phần lớn nghiệp vụ gọi JPA/JDBC hoặc SDK chỉ có API chặn luồng, WebFlux không tự biến các lời gọi đó thành non-blocking.
2. **Tải thực tế có hưởng lợi từ việc phục vụ nhiều request đang chờ I/O với ít luồng hệ điều hành hơn?** Cần phân biệt lưu lượng, độ đồng thời, tỷ lệ chờ I/O, chi phí CPU, p95/p99 latency và giới hạn downstream.
3. **Toàn bộ hệ sinh thái đã phù hợp chưa?** Bao gồm cơ chế Spring Security, transaction, context, kiểm thử, tích hợp thư viện, tracing, giới hạn tài nguyên và khả năng debug.

**Nguyên tắc xuất phát:** Với ứng dụng hiện hữu vận hành tốt bằng MVC + JPA/JDBC, thường nên giữ Servlet; chỉ chuyển sang WebFlux khi có bằng chứng và lộ trình chuyển toàn bộ đường xử lý quan trọng. Với một dịch vụ mới chủ yếu thực hiện I/O non-blocking như streaming hay fan-out nhiều lời gọi HTTP, reactive đáng cân nhắc từ đầu.

## 2. Hai mô hình thực thi thực sự khác nhau ở đâu?

### 2.1. Servlet / Spring MVC

Luồng đơn giản hóa:

```text
HTTP request
  → Servlet container (ví dụ Tomcat)
  → Servlet Filter / Spring Security FilterChainProxy
  → DispatcherServlet → Controller → Service
  → JDBC/JPA hoặc API khác → HTTP response
```

Trong xử lý đồng bộ điển hình, một luồng xử lý request có thể **chờ** khi gọi database hay dịch vụ mạng. Container dùng pool luồng để quản lý nhiều request; kỹ thuật Servlet async cũng tồn tại và Spring MVC có thể xử lý một số kiểu bất đồng bộ, nên “Servlet = chỉ làm được đồng bộ” là sai. Ưu điểm chính của đường imperative là dòng lệnh dễ đọc, dùng trực tiếp hệ sinh thái blocking rất lớn, transaction theo luồng và công cụ debug quen thuộc.

### 2.2. Reactive / Spring WebFlux

Luồng đơn giản hóa:

```text
HTTP request
  → WebFilter / SecurityWebFilterChain
  → DispatcherHandler → Controller/Handler
  → Mono/Flux pipeline → non-blocking HTTP/DB client
  → tín hiệu dữ liệu / lỗi / hoàn tất → HTTP response
```

Thay vì giữ một luồng chờ mỗi I/O, mã phản ứng khai báo pipeline; khi I/O chưa sẵn sàng, luồng có thể phục vụ công việc khác. WebFlux thường chạy với event-loop và số luồng tương đối nhỏ; do đó **không được chặn event-loop** bằng `Thread.sleep`, `Future.get`, `block()`, JDBC hoặc thao tác mạng blocking.

`Mono<T>` biểu thị tối đa một giá trị hoặc kết thúc/lỗi, `Flux<T>` biểu thị chuỗi 0..N giá trị. Pipeline chỉ chạy khi được subscribe; trong WebFlux, framework thường đảm nhận subscribe cho giá trị trả về controller. Reactor hỗ trợ backpressure giữa các thành phần tuân thủ Reactive Streams, nhưng điều này **không tự động bảo đảm** mọi database, queue, HTTP client hay người dùng cuối đều có cơ chế kiểm soát tải phù hợp.

**Phân biệt:** Reactive không đồng nghĩa với Netty. WebFlux chạy được trên server hỗ trợ tương thích khác; Netty là lựa chọn thường thấy của starter WebFlux. Ngược lại, dùng `WebClient` hoặc trả `Mono` từ controller MVC **không tự động biến toàn ứng dụng thành WebFlux**.

### 2.3. Độ trễ, thông lượng và tài nguyên

Non-blocking thường có lợi khi rất nhiều thao tác **chờ I/O** (API chậm, streaming, kết nối dài). Nó không tự làm SQL chạy nhanh hơn, không xóa giới hạn connection pool và có thể thêm chi phí lập trình, scheduler, bộ nhớ hoặc xử lý tín hiệu. Nghiệp vụ nặng CPU vẫn phải phân phối CPU hữu hạn; gọi reactive cho phép tính toán CPU-bound không khiến phép tính song song hơn.

Có thể ước lượng mức đồng thời bằng **định luật Little**: số request đang ở hệ thống xấp xỉ tốc độ đến nhân thời gian xử lý trung bình, `L ≈ λ × W`. Ví dụ 200 request/giây và 250 ms trung bình tương ứng khoảng 50 request đồng thời khi hệ thống ổn định. Con số này là **request in-flight**, không phải số luồng WebFlux cần và cũng không phải số kết nối JDBC cần. Mục đích là đặt câu hỏi đo đạc, không dùng phép nhân này để tuyên bố kiến trúc thắng.

## 3. Kiểm tra *toàn bộ* đường đi của dữ liệu

Một hệ thống được hưởng lợi từ reactive khi các đoạn có nhiều thời gian chờ đều hỗ trợ non-blocking, trong khi các đoạn blocking được cô lập, đo đạc và có giới hạn. Dùng bảng kiểm dưới đây để kiểm tra từng request quan trọng:

| Thành phần | Servlet/MVC điển hình | WebFlux/reactive điển hình | Điểm phải xác minh |
|---|---|---|---|
| HTTP server/controller | `DispatcherServlet`, `@RestController` | `DispatcherHandler`, `Mono`/`Flux` hoặc functional routes | Framework thực sự được Boot khởi động là gì? |
| Client gọi REST | `RestClient`, `RestTemplate` hoặc `WebClient` | `WebClient` non-blocking | Có `block()`, SDK đồng bộ, retry gây bão tải? |
| Truy cập SQL | JPA/Hibernate, JDBC, `JdbcTemplate` | R2DBC khi driver và use case hỗ trợ | Có driver, ORM, transaction và tính năng SQL cần thiết? |
| Transaction | `PlatformTransactionManager`, thường thread-bound | `ReactiveTransactionManager`, Reactor Context | Đường nào sở hữu transaction, có trộn thread/context? |
| Security HTTP | `SecurityFilterChain` + `HttpSecurity` | `SecurityWebFilterChain` + `ServerHttpSecurity` | Có cấu hình đúng loại stack và đủ rule? |
| Security context | `SecurityContextHolder` phổ biến theo luồng | `ReactiveSecurityContextHolder` qua Reactor Context | Danh tính có đi qua async/scheduler/pipeline? |
| Filter / exchange | Servlet `Filter`, `HttpServletRequest` | `WebFilter`, `ServerWebExchange` | Có thư viện cần Servlet API? |
| Session, CSRF, login | Servlet session / CSRF filter | Web session / reactive CSRF filter | Dùng cookie/browser hay bearer token? |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Kiểu trả về và context có tương thích? |
| Kiểm thử HTTP | `MockMvc`, Servlet test | `WebTestClient`, reactive security test | Test cả 401, 403, CSRF, context propagation? |
| Vận hành | Thread pool, JDBC pool, servlet metrics | Event-loop, scheduler, connection pool, backpressure | Có đo được queue, timeout, memory, p95/p99? |

**Điểm nghẽn yếu nhất quyết định hiệu quả:** Nếu một request WebFlux đi qua ba lớp non-blocking nhưng cuối cùng chờ JDBC trên event-loop, request đó có thể kéo nghẽn nhiều request khác. Nếu một dịch vụ MVC dùng `WebClient` để gọi song song hai downstream độc lập và trả kết quả bất đồng bộ thích hợp, dịch vụ đó vẫn có thể giảm thời gian chờ mà không phải đổi web stack.

### 3.1. Phân loại phụ thuộc trước khi thiết kế

- **Blocking bắt buộc:** JPA, JDBC, driver/SDK đồng bộ, thao tác file blocking, gọi thư viện không có API async. Chúng thường phù hợp với MVC, hoặc cần cầu nối được quản lý chặt trong reactive.
- **Non-blocking thực tế:** `WebClient` sử dụng đúng cách, R2DBC/driver reactive tương thích, một số messaging driver/stream API có giao thức backpressure.
- **CPU-bound:** Mã hóa, nén, xử lý ảnh, tính toán lớn, một số xác thực chữ ký. Dù stack nào cũng cần giới hạn CPU và concurrency.
- **Tài nguyên chia sẻ:** DB pool, upstream rate limit, cache, message broker, API quota, thread/scheduler. Một pipeline non-blocking vẫn có thể làm quá tải chúng nếu không giới hạn fan-out.

Không chỉ hỏi “có reactive repository không?”. Hỏi thêm “hệ thống có bắt buộc cần JPA entity lifecycle, lazy loading, quan hệ phức tạp, transaction hiện có hay driver đặc thù không?”. Chuyển JPA sang R2DBC không phải thay import tương đương: persistence model và bảo đảm transaction cần được thiết kế, kiểm thử lại.

## 4. Spring Security phải khớp web stack

Dù chọn mô hình nào, yêu cầu bảo mật vẫn giống nhau: xác thực danh tính, phân quyền, nguyên tắc từ chối mặc định ở đường cần bảo vệ, xử lý 401/403, chống CSRF khi có nguy cơ từ cookie, bảo vệ session/token, mã hóa, ghi log an toàn và test âm tính. **API thực thi của Spring Security mới là phần khác nhau.**

### 4.1. Servlet security

Trong MVC, Spring Security tích hợp qua Servlet filter chain. Cấu hình dùng `HttpSecurity` để tạo bean `SecurityFilterChain`; request được xác thực/phân quyền qua các filter trước khi vào controller. `SecurityContextHolder` là cách truy cập context theo luồng phổ biến trong xử lý đồng bộ, nhưng khi tự chuyển sang executor/thread khác phải dùng cách truyền context được hỗ trợ thay vì giả định `ThreadLocal` tự đi theo.

### 4.2. Reactive security

Trong WebFlux, Spring Security tích hợp bằng `WebFilter` và `SecurityWebFilterChain`; cấu hình dùng `ServerHttpSecurity`, ví dụ `authorizeExchange` và `pathMatchers`. Authentication/security context đi qua **Reactor Context** gắn với subscription/pipeline, không thể xem `SecurityContextHolder.getContext()` trên một event-loop bất kỳ là cách lấy đúng user.

Một đoạn minh họa **đặt bên trong phương thức trả về `Mono<String>`** của thành phần reactive đã được Spring Security tích hợp:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Imports tương ứng: `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.core.context.SecurityContext` và `org.springframework.security.core.Authentication`. Đoạn trên không phải một Java class độc lập; trong endpoint đã yêu cầu authenticated, nó cung cấp tên principal hiện tại.

Khi tự `subscribe()`, `block()` hoặc tạo luồng bên ngoài chuỗi Reactor mà không kiểm soát, dễ làm mất semantics của context, error, cancellation, transaction và quan sát. Giữ **một pipeline được framework subscribe**, dùng operator hợp lệ; kiểm tra bằng test có danh tính thật.

### 4.3. CSRF, session và token

- Với ứng dụng web dùng **session cookie để tự động gửi credential**, cần phân tích CSRF và thường giữ bảo vệ CSRF cho thao tác thay đổi trạng thái. Không tắt chỉ để test `POST` dễ hơn.
- Với REST API dùng bearer token trong header và không dựa vào cookie credential tự động, có thể có lý do cấu hình CSRF khác; phải phân tích **cơ chế xác thực thực tế**. “Dùng JWT” không đủ để kết luận mọi endpoint đều miễn CSRF nếu vẫn có cookie/session.
- Một ứng dụng có thể cần form login, OAuth2 login/OIDC, resource server JWT hoặc opaque token trên cả hai stack, nhưng bean, bộ lọc, entry point, persistence context và integration phải chọn theo stack tương ứng.
- Authentication/authorization policy có thể giữ **ý nghĩa tương đương** khi chuyển stack; không thể sao chép nguyên xi `HttpSecurity` sang `ServerHttpSecurity`.
- Phân biệt **401** (chưa xác thực hoặc credential không hợp lệ), **403** (đã xác thực nhưng không đủ quyền, hoặc bị kiểm soát khác như CSRF). Entry point thực tế có thể trả redirect cho form login; test theo cấu hình cụ thể.

### 4.4. Method-level security, transaction và lỗi

`@EnableMethodSecurity` dành cho phương thức imperative; với pipeline reactive dùng `@EnableReactiveMethodSecurity` và phương thức/kiểu trả về phù hợp. Kiểm tra cả quyền ở controller và ở service nhạy cảm để tránh lỗ hổng khi một service được gọi từ đường khác.

Transaction imperative được quản lý bởi `PlatformTransactionManager` và thường gắn theo luồng; transaction reactive do `ReactiveTransactionManager` quản lý dựa trên Reactor Context. Vì vậy gọi service `@Transactional` kiểu JPA qua một luồng/scheduler tùy ý không thể được xem là đã chuyển transaction sang reactive. Các nhánh retry/cancel/error của publisher cũng cần được xét khi bảo đảm rollback và tính idempotent.

## 5. Hai ví dụ tối thiểu có thể chạy để nhìn thấy khác biệt

Hai ví dụ dưới đây là **hai ứng dụng Spring Boot độc lập**, không đặt chung một project. Tạo project Spring Boot 3.x + Java 17+ từ Spring Initializr (hoặc project Boot đã cấu hình Gradle plugin/BOM), chọn đúng các starter tương ứng. `build.gradle` minh họa chỉ là phần `dependencies` của project Boot hiện có; không phải build file đầy đủ. Cả hai có cùng chính sách: `/public/**` công khai, mọi URL khác cần xác thực HTTP Basic. User demo `learner / demo123` sử dụng `{noop}` **chỉ để học cục bộ**; production dùng kho danh tính và password encoder an toàn.

### 5.1. Phương án Servlet/MVC

Trong project thứ nhất, thêm các dependency vào `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Đặt tệp `src/main/java/example/mvc/MvcApplication.java`:

```java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "mvc public";
    }

    @GetMapping("/api/ping")
    public String privatePing() {
        return "mvc protected";
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
```

Code sử dụng Servlet/MVC + `SecurityFilterChain`, không tạo publisher để hoàn thành endpoint. Chạy `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows, từ đúng project. Mặc định HTTP port 8080 nếu chưa cấu hình khác.

### 5.2. Phương án WebFlux/reactive

Trong **project thứ hai**, dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Đặt tệp `src/main/java/example/reactive/ReactiveApplication.java`:

```java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> publicPing() {
        return Mono.just("reactive public");
    }

    @GetMapping("/api/ping")
    public Mono<String> privatePing() {
        return Mono.just("reactive protected");
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(ex -> ex
                    .pathMatchers("/public/**").permitAll()
                    .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
```

Ở đây luồng HTTP đi qua `SecurityWebFilterChain` và endpoint trả publisher. `Mono.just` trong demo chỉ minh họa **kiểu trả về và security integration**, chưa có I/O non-blocking nên không phải bằng chứng hiệu năng WebFlux cao hơn.

### 5.3. Chạy và quan sát

Chỉ chạy **một trong hai ứng dụng tại port 8080** mỗi lần. Với project đã tạo, dùng các lệnh sau:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/ping
curl -i -u learner:demo123 http://localhost:8080/api/ping
```

| Request | Trạng thái dự kiến | Body điển hình |
|---|---:|---|
| GET `/public/ping` không credential | 200 | `mvc public` hoặc `reactive public` |
| GET `/api/ping` không credential | 401 | Không dựa vào body lỗi cố định |
| GET `/api/ping` với credential hợp lệ | 200 | `mvc protected` hoặc `reactive protected` |

Header phụ thuộc server/Spring Security/config; không nên so sánh nguyên văn toàn bộ output `curl -i`. Thử thêm credential sai → 401. Vì hai demo chỉ có GET, chúng chưa kiểm thử CSRF đối với POST, và cũng chưa minh họa role ADMIN, session, database hay transaction.

**Cạm bẫy lúc chọn starter:** Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng ở classpath, mặc định Spring Boot chọn auto-configuration **MVC**, vì ứng dụng MVC thường thêm WebFlux để dùng `WebClient`. Đừng suy luận web stack đang chạy chỉ dựa vào việc thấy `spring-webflux` trong dependency tree. Xác minh `WebApplicationType`, log startup, context/bean hiện diện và endpoint/integration test thực tế. Không tự ép `REACTIVE` trên ứng dụng MVC cũ khi chưa kiểm tra các dependency và security beans.

## 6. Bridging: vẫn còn API blocking thì phải xử lý thế nào?

Đôi khi phải gọi thư viện blocking từ WebFlux trong giai đoạn chuyển tiếp. Một **đoạn service minh họa, không phải chương trình độc lập**, có thể chuyển thao tác blocking ra bounded scheduler:

```java
public Mono<Customer> findCustomer(String id) {
    return Mono.fromCallable(() -> legacyRepository.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Giả định `legacyRepository.findById` là method blocking trả về `Customer` hoặc `null`; `Mono.fromCallable` hoàn tất rỗng khi callable trả `null`. Các tên `Customer` và `legacyRepository` do project cung cấp; cần import `Mono` và `Schedulers` từ Reactor. Cầu nối này **không biến repository thành non-blocking**; nó sử dụng luồng khác để không chặn event-loop. Vẫn phải theo dõi số task chờ, số luồng, connection pool, timeout, giới hạn concurrency và context/transaction. Nếu toàn bộ đường đi phải bọc JDBC bằng `boundedElastic`, rất có thể MVC là lựa chọn đơn giản và dễ vận hành hơn.

Các thao tác nên tránh trong pipeline WebFlux:

```java
// Ví dụ sai khi chạy trên event-loop:
User user = userClient.getUser(id).block();
Thread.sleep(500);
```

Đây là ví dụ chống mẫu, **không phải class runnable**. `block()` khiến thread chờ kết quả và trong nhiều đường Reactor non-blocking có thể gây lỗi tại runtime; `Thread.sleep` giữ event-loop không làm việc. Với CPU-bound dài, cũng cần cân nhắc executor/scheduler chuyên dụng hoặc tách tác vụ ra worker, không mặc định đưa tất cả lên `boundedElastic`.

Mặt khác, nếu dùng Servlet MVC và cần gọi nhiều HTTP endpoint, có thể dùng `WebClient` không chặn trong mô hình async đã được MVC hỗ trợ. Tránh gọi `.block()` vô tội vạ trong controller rồi kết luận “WebClient không giúp ích”; lựa chọn này vẫn cần đo hiệu quả và giữ nhất quán cách xử lý lỗi, timeout.

## 7. Các tình huống quyết định thường gặp

### Tình huống A — Ứng dụng nghiệp vụ CRUD với JPA

Hệ thống quản trị có nhiều bảng quan hệ, JPA/Hibernate, giao dịch imperative, vài API ngoài đồng bộ và tải vừa phải. **Đề xuất khởi đầu: Servlet/MVC + Spring Security Servlet.** Đường data và transaction đang blocking; chi phí chuyển đổi sang WebFlux/R2DBC có thể vượt lợi ích. Tập trung tối ưu SQL/index, JDBC pool, cache, thời gian gọi downstream, timeout, pagination và phân quyền.

### Tình huống B — API aggregation/gateway gọi nhiều dịch vụ HTTP

Một endpoint cần truy vấn song song nhiều downstream với latency cao, không có transaction JPA và đã dùng client non-blocking. **WebFlux + Security reactive có thể phù hợp**, nhất là khi nhiều request đang chờ I/O. Nhưng cần giới hạn fan-out, kết nối, retry, timeout, backpressure ở từng khâu; không coi gateway bất kỳ là minh chứng tự động nên dùng WebFlux. Một MVC service đã ổn cũng có thể thử `WebClient` trước.

### Tình huống C — SSE/streaming và kết nối lâu

Ứng dụng truyền event liên tục hoặc nhiều kết nối dài, upstream hỗ trợ luồng dữ liệu non-blocking. **WebFlux là lựa chọn đáng thử** khi cần biểu diễn stream, cancellation và kiểm soát tài nguyên theo pipeline. Servlet cũng có streaming/async; quyết định dựa trên concurrency, cơ chế gửi sự kiện, cân bằng tải, reconnect và hạ tầng triển khai. Security vẫn phải xử lý đăng nhập/token, thời điểm hết hạn, quyền nhận stream, ngắt kết nối và giới hạn tốc độ.

### Tình huống D — Tác vụ nặng CPU hoặc SDK blocking bắt buộc

Phân tích ảnh, ký số khối lượng lớn, xử lý file qua thư viện chặn luồng. **Reactive không tự giải quyết nút thắt CPU/SDK**. Cân nhắc Servlet + luồng ảo trên Java 21+, pool phù hợp, task queue, background workers, tách service. Đánh giá riêng giới hạn JVM, pinning của virtual threads và áp lực downstream.

### Tình huống E — Nhiều microservice khác nhu cầu

Không bắt buộc tất cả service dùng cùng web stack. Chẳng hạn service quản trị JPA dùng MVC, dịch vụ streaming dùng WebFlux, hệ thống giao tiếp bằng HTTP/events hợp đồng ổn định. Mỗi service cấu hình **Security đúng stack của nó**; vẫn cần cùng chuẩn identity, issuer/audience, authorization semantics, truyền trace context, timeout và quản trị khóa. Tuy nhiên việc pha trộn tăng chi phí kỹ năng, thư viện và vận hành: chỉ dùng khi lợi ích cụ thể chứng minh được.

## 8. Quy trình quyết định có thể áp dụng cho dự án thật

### Bước 1: Vẽ đường request và khoanh giới hạn cứng

Với từng luồng nghiệp vụ chính, vẽ từ ingress → security filters → controller → service → database/cache/upstream/message broker → response. Ghi rõ driver/SDK **blocking** hay **non-blocking**, kiểu transaction, authentication, session, timeout, retry. Một thư viện quan trọng chỉ có Servlet API hoặc JPA có thể là ràng buộc cứng.

### Bước 2: Phân loại workload

Đo RPS, concurrent requests, thời gian chờ database/API, p50/p95/p99, request size, streaming duration, CPU, memory, connection/thread pool, số lỗi. Xác định điểm nghẽn do **chờ I/O**, CPU, database, contention, limit từ upstream hay thuật toán. Một dịch vụ có 10.000 concurrent kết nối chờ sự kiện khác hẳn 10.000 phép tính CPU cùng lúc.

### Bước 3: Chọn ứng viên tối giản

- Nếu phần lớn stack hiện có blocking, JPA transaction là cốt lõi, Security Servlet ổn định: ưu tiên MVC. Với Java 21+, có thể thử virtual threads có giám sát nếu phù hợp, nhưng vẫn phải đo pinning và pool downstream.
- Nếu luồng quan trọng thực sự dùng non-blocking end-to-end, streaming/fan-out nhiều I/O, đội ngũ làm chủ Reactor và có test/security reactive: thử WebFlux.
- Nếu chưa có bằng chứng: giữ kiến trúc ổn, làm một thử nghiệm nhỏ với tải thực tế. Đừng chuyển chỉ vì “công nghệ mới”.

### Bước 4: Dựng thử nghiệm đúng điều kiện

Giữ cùng nghiệp vụ, auth, DB và dữ liệu, SLO, payload, tỷ lệ GET/POST, độ trễ downstream, phần cứng và giới hạn concurrency. Ghi rõ cấu hình thread/event-loop, pool kết nối, client timeout, retry, heap, GC và số request đang đợi. Đo cả **trạng thái ổn định lẫn khi upstream chậm/lỗi**; một benchmark chỉ “Hello World” chủ yếu đo framework overhead, không quyết định kiến trúc doanh nghiệp.

### Bước 5: Đánh giá cả tính đúng đắn bảo mật và transaction

Có đủ 401/403 cho tất cả endpoint? Session/cookie có CSRF? User/role trong chain có đúng khi dùng async/scheduler? `@PreAuthorize` có hoạt động theo Reactor Context? Transaction, rollback, cancellation, retry và idempotency có tương ứng? Audit, trace và log có gắn đúng request/user mà không lộ secret/token? Hiệu năng đạt SLO nhưng security/transaction không đúng **không phải** một lựa chọn đạt yêu cầu.

### Bước 6: Ra quyết định và ghi lại lý do

Ghi một ADR (Architecture Decision Record) ngắn:

```text
Decision: MVC / WebFlux cho service X
Workload: RPS, độ đồng thời, p95/p99, tỷ lệ chờ I/O
Constraints: JPA/JDBC/SDK, security, transaction, team, operations
Alternatives: MVC hiện tại, MVC + WebClient, MVC + virtual threads,
              WebFlux non-blocking end-to-end, tách service
Evidence: kết quả load test, lỗi, CPU/heap, pool, failure modes
Security: chain/context/method security, CSRF/session/token, test 401/403
Trade-offs: migration cost, debugging, library support, observability
Revisit when: workload/driver/critical dependency thay đổi
```

Một quyết định tốt có điều kiện **xem xét lại** khi workload hoặc thư viện thay đổi, thay vì biến stack thành quy tắc cứng áp cho mọi module.

## 9. Kế hoạch chuyển đổi an toàn nếu chọn reactive

Chuyển từ MVC/JPA sang WebFlux không chỉ là đổi `@RestController` trả về `Mono`:

1. **Xác định phạm vi service và SLO:** chọn đường request có lợi ích I/O rõ ràng, không di cư toàn bộ chỉ vì một endpoint.
2. **Kiểm kê dependency:** JPA/JDBC, transaction, thư viện Servlet, filter, auth provider, SDK, HTTP client, cache, metrics, test.
3. **Tách business logic khỏi API framework:** xác định interface/domain không phụ thuộc `HttpServletRequest`/`ServerWebExchange` nếu có thể.
4. **Định nghĩa persistence:** driver R2DBC hỗ trợ nghiệp vụ không, có cần thiết kế lại truy vấn/transaction/lazy loading?
5. **Đổi security đúng semantics:** từ `SecurityFilterChain`/`HttpSecurity` sang `SecurityWebFilterChain`/`ServerHttpSecurity`; kiểm tra rule, session/CSRF, OAuth2, context và method security.
6. **Thay các client I/O:** xây pipeline thực sự non-blocking, quản lý retry có backoff, timeout, concurrency và propagation.
7. **Cô lập phần blocking còn lại:** có số lượng hữu hạn, scheduler hợp lý, giám sát queue/pool; tránh giấu blocking bằng tên method “async”.
8. **Kiểm thử trạng thái biên:** anonymous, forbidden, invalid/expired token, race/cancel, retry, timeout, rollback, overload, mất client, shutdown.
9. **Rollout có quan sát:** canary hoặc chia lưu lượng theo service khi thích hợp; so sánh SLO, GC, tài nguyên, errors, bảo mật.
10. **Có kế hoạch quay lui:** cấu hình và đường dữ liệu cho phép trở về bản ổn nếu phát hiện vấn đề; không đổi schema/protocol đồng loạt nếu chưa cần.

Nếu mục tiêu chỉ là tăng concurrency cho một vài tích hợp blocking, cân nhắc tối ưu kiến trúc MVC trước hoặc tách phần streaming thành dịch vụ chuyên biệt; không biến quá trình chuyển stack thành một dự án refactor toàn hệ thống thiếu chỉ tiêu đo.

## 10. Kiểm thử security và hiệu năng để tránh chọn sai

### 10.1. Kiểm thử chức năng và phân quyền

Trong MVC, dùng `MockMvc`/Spring Security test tùy cấp test; trong WebFlux, dùng `WebTestClient` và công cụ reactive security test. Dù framework nào, cần kiểm tra:

- Endpoint public truy cập được; endpoint private khi anonymous nhận phản hồi phù hợp; credential sai bị từ chối.
- Người dùng có role thiếu quyền nhận 403; rule cụ thể không bị `anyRequest` hay filter chain khác vô tình mở rộng.
- Browser session/cookie và POST/PUT/DELETE xử lý CSRF đúng thiết kế; token-based API có chính sách chính xác.
- Security context và method authorization giữ đúng identity qua pipeline/async, thread switching hợp lệ và outbound calls.
- Log/trace không lộ password, access token, cookie, header nhạy cảm; audit ghi user ID tin cậy.
- Timeout, cancellation, retry hoặc client disconnect không biến request lỗi thành bypass authorization hay phát lại tác vụ có side effect.

### 10.2. Tải và khả năng chống chịu

Chạy kịch bản có thời gian warm-up, đủ thời gian ổn định và **độ trễ downstream giống thực tế**. Đo throughput thành công, p50/p95/p99, error/timeout rate, CPU, RSS/heap/GC, thời gian đợi pool và chi phí mỗi request. Với MVC quan sát thread pool/connection pool; với WebFlux thêm event-loop/scheduler saturation, pending tasks, Reactor Netty connections và khả năng backpressure. Khi upstream chậm hoặc DB pool hết kết nối, yêu cầu hệ thống suy giảm có kiểm soát thay vì tăng queue vô hạn.

Đừng xem số luồng thấp là KPI duy nhất: một WebFlux app có 8 event-loop nhưng nghẽn JDBC trên boundedElastic vẫn có thể tốn nhiều luồng và không đạt SLA. Ngược lại, một MVC app với virtual threads và pool database được giới hạn tốt có thể đáp ứng mục tiêu. **Kết quả ở tải thực mới quyết định.**

## 11. Các hiểu nhầm và lỗi thiết kế hay gặp

| Nhận định / cách làm | Vấn đề | Cách sửa |
|---|---|---|
| “WebFlux luôn nhanh hơn MVC.” | Non-blocking tối ưu hiệu quả sử dụng tài nguyên ở bài toán phù hợp, không bảo đảm giảm mọi latency. | Đo workload và giới hạn thực. |
| “Trả `Mono` là toàn hệ thống reactive.” | Publisher có thể bọc API blocking; MVC cũng hỗ trợ một số reactive return types. | Xem runtime web type và từng driver/client. |
| “Thêm starter WebFlux vào MVC tự đổi server.” | Spring Boot mặc định ưu tiên MVC khi cả hai starter hiện diện. | Xác minh auto-configuration và dependency tree. |
| “Dùng JDBC trực tiếp trên event-loop vẫn ổn.” | Có thể chặn ít event-loop, kéo theo request khác. | Giữ MVC, chuyển sang driver phù hợp, hoặc dùng scheduler làm cầu nối có giới hạn. |
| “`.block()` giúp code reactive dễ đọc hơn.” | Phá lợi ích non-blocking, có thể lỗi trên event-loop. | Giữ pipeline reactive hoặc dùng imperative stack rõ ràng. |
| “SecurityContextHolder lấy đúng user ở mọi luồng.” | Reactor context khác ThreadLocal; tự đổi thread/subscribe dễ mất context. | Dùng API security/context đúng stack và test propagation. |
| “Copy SecurityFilterChain từ MVC sang WebFlux.” | Các filter, request matcher và DSL khác nhau. | Viết `SecurityWebFilterChain` tương ứng, kiểm tra semantic rule. |
| “Đã dùng JWT thì luôn tắt CSRF.” | Phụ thuộc cookie credential, cách client gửi token và threat model. | Phân tích authentication thực tế từng endpoint. |
| “Reactive transaction dùng chung với JPA @Transactional.” | Manager và context propagation có contract khác nhau. | Chọn đúng transaction manager cho I/O model. |
| “Unlimited `flatMap`/retry cho nhanh.” | Có thể dồn áp lực lên upstream/DB, làm khuếch đại sự cố. | Giới hạn concurrency, connection, timeout, backoff và retry budget. |
| “Có SSE thì bắt buộc dùng WebFlux.” | Servlet cũng có async/streaming, trade-off phụ thuộc tải. | Đo số connection dài và cách vận hành. |
| “Virtual threads thay thế toàn bộ reactive.” | Virtual threads giúp mô hình blocking concurrency, không biến thư viện thành non-blocking hay tạo backpressure. | So sánh theo benchmark và yêu cầu semantics. |

## 12. Checklist chốt lựa chọn

Trước khi phê duyệt kiến trúc, người review cần có câu trả lời cụ thể cho các mục sau:

- [ ] Luồng request và những phụ thuộc blocking/non-blocking quan trọng đã được kiểm kê.
- [ ] Khối lượng I/O waiting, CPU, concurrent connections và mục tiêu p95/p99 đã được đo.
- [ ] Driver database, transaction semantics và thư viện ngoài phù hợp lựa chọn.
- [ ] Stack security thực tế được xác nhận; cấu hình HTTP/method security dùng đúng API.
- [ ] Session, cookie, CSRF, authentication, authorization, 401/403 đã có negative tests.
- [ ] Identity/trace/transaction context đã được kiểm tra qua async hoặc Reactor pipeline.
- [ ] Scheduler, event-loop, database connection pool, rate limit và retry có giới hạn.
- [ ] Có load test với upstream chậm, timeout, cancellation, shutdown và lỗi phục hồi.
- [ ] Chi phí di cư, vận hành, học tập và rollback đã được ghi trong ADR.
- [ ] Quyết định dựa trên kết quả của service cụ thể, không áp một nhãn cho mọi service.

**Kết luận thực hành:** Chọn **Servlet/MVC** khi phần lớn luồng nghiệp vụ là imperative/blocking, nhất là JPA/JDBC và transaction hiện hữu, hoặc khi tính đơn giản và vận hành tốt quan trọng hơn lợi ích non-blocking chưa chứng minh. Chọn **WebFlux/reactive** khi tải I/O đồng thời lớn, có đường đi non-blocking đáng kể, streaming/fan-out phù hợp và team có thể kiểm soát Reactor, Spring Security reactive, transaction và observability. Hai loại service có thể cùng tồn tại trong một kiến trúc phân tán; hợp đồng bảo mật và chất lượng vận hành phải nhất quán.

## 13. Tài liệu chính thức để đào sâu

- Spring Framework — [WebFlux Overview / MVC or WebFlux?](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): cơ sở chọn stack, sự khác biệt mô hình I/O, concurrency và tác động từ thư viện blocking.
- Spring Boot — [Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): starter và quy tắc mặc định khi có cả Web MVC/WebFlux.
- Spring Security — [Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): Servlet request authorization.
- Spring Security — [Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context và bảo mật ở tầng method.
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): phân biệt transaction theo thread với Reactor Context.
- Spring Boot — [Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads): lựa chọn bổ sung trên Java 21+, giới hạn và vận hành.

Các tài liệu chính thức có thể phát triển theo từng release; khi áp dụng cho dự án, luôn đối chiếu đúng phiên bản Spring Boot / Spring Security đang chạy và thay thế cấu hình mẫu bằng chính sách bảo mật của hệ thống.
