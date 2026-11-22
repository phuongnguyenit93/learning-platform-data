# Spring AOP, lời gọi nội bộ cùng đối tượng và nguyên nhân annotation không có hiệu lực

## 1. Bối cảnh và mục tiêu

Trong Spring Security reactive, bạn có thể gắn `@PreAuthorize("hasRole('ADMIN')")` lên một phương thức `Mono<String>`, chạy ứng dụng và thấy kiểm tra quyền hoạt động khi controller gọi phương thức đó. Tuy nhiên, chỉ cần một phương thức **khác trong cùng đối tượng** gọi nó bằng `this.adminOnly()`, việc kiểm tra quyền có thể **không xảy ra**. Đây là lỗi **self-invocation** của **Spring AOP kiểu proxy**, có thể tạo lỗ hổng phân quyền ngay cả khi annotation và biểu thức SpEL hoàn toàn đúng.

Bài này thuộc chủ đề **phân quyền phương thức trong Spring Security reactive/WebFlux**. Bạn sẽ:

1. Hiểu Spring AOP proxy và mối quan hệ của nó với `@EnableReactiveMethodSecurity`, `@PreAuthorize` và `@PostAuthorize`.
2. Giải thích được vì sao lời gọi **qua Spring proxy** kích hoạt advice bảo mật, còn lời gọi **nội bộ cùng bean qua `this`** không đi qua proxy.
3. Phân biệt lỗi self-invocation với việc chưa bật method security, bean không do Spring quản lý, method `private`/`final`, proxy sai kiểu hoặc thiếu Reactor security context.
4. Chạy một ví dụ Java 17+ Spring Boot WebFlux có đủ ba đường: **gọi trực tiếp được bảo vệ**, **gọi nội bộ bị bypass**, **gọi qua bean khác được bảo vệ**.
5. Kiểm thử user có quyền và thiếu quyền bằng `WebTestClient`, nhận biết kết quả **200/401/403** chính xác.
6. Ưu tiên sửa bằng **tách bean/thiết kế lại luồng gọi**, biết giới hạn của self-injection, `AopContext.currentProxy()` và AspectJ weaving.
7. Thiết kế test chống hồi quy để một refactor về sau không âm thầm bỏ qua chính sách authorization.

**Cảnh báo cho ví dụ:** Bài cố ý tạo một endpoint dễ bị bypass **chỉ để tái hiện lỗi trong môi trường học tập cục bộ**. Không xuất bản endpoint này lên hệ thống thật; sau khi quan sát, phải xóa hoặc thay thế bằng cách gọi qua bean được bảo vệ.

## 2. Method security của WebFlux dựa trên gì?

Đối với luồng **reactive**, Spring Security kết hợp Spring AOP với **Reactor Context**, thay vì chỉ lấy authentication từ `ThreadLocal` của Servlet.

Các thành phần:

| Thành phần | Chức năng |
| --- | --- |
| `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` | Bật các advisor/interceptor phân quyền phương thức reactive theo mô hình `AuthorizationManager` |
| `@PreAuthorize("...")` | Đánh giá quy tắc authorization **trước** khi cho thực hiện phương thức được bảo vệ |
| `@PostAuthorize("...")` | Đánh giá quy tắc khi có kết quả để quyết định có được trả kết quả đó không |
| Spring AOP proxy | Đối tượng bao bọc lời gọi bên ngoài, cho phép chạy authorization advice |
| `ReactiveSecurityContextHolder` | Đọc `SecurityContext` từ Reactor Context trong pipeline |
| `SecurityWebFilterChain` | Bảo vệ HTTP request ở tầng WebFilter, **khác** authorization trên method |
| `Mono<T>` / `Flux<T>` | Publisher trả về để reactive method security tích hợp với subscription/Context |

Ví dụ bật method security:

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {
    // ... khai báo các @Bean cần thiết ...
}
```

Đây là **đoạn trích**, class đầy đủ nằm ở phần 8. Trong Spring Security 6.x, tham số `useAuthorizationManager = true` cho biết cấu hình sử dụng hạ tầng `AuthorizationManager`; đây là hướng cấu hình khuyến nghị cho bài học này.

Ví dụ trên một Spring bean:

```java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.just("restricted-report");
    }
}
```

Nếu một đối tượng **nhận qua Spring container** gọi `reportService.adminOnly()` qua proxy, một user đã đăng nhập nhưng chỉ có `ROLE_USER` sẽ bị từ chối bởi method security. User có `ROLE_ADMIN` có thể được cho phép.

Nhưng việc **viết annotation trên source code không tự chèn kiểm tra vào mọi lời gọi Java**. Muốn hiểu tại sao, cần hiểu proxy.

## 3. Spring AOP proxy và điểm đặt advice

Spring AOP thông thường dùng **proxy runtime**. Proxy đứng giữa **caller bên ngoài** và **target object**; khi caller đi qua proxy, các interceptor/advice phù hợp mới có cơ hội hoạt động.

```text
Controller / Bean khác
       |
       v
Spring proxy của ReportService
       |
       +--> Method-security advisor (@PreAuthorize)
       |         |
       |     kiểm tra quyền
       |      /       \
       |   từ chối    cho phép
       |      |          |
       |     403         v
       |             target.adminOnly()
       |                    |
       |                    v
       |                Mono<String>
       |
       +--> Caller nhận tín hiệu reactive
```

Đây là sơ đồ khái niệm: HTTP status 403 do các filter/error handler WebFlux chuyển tín hiệu `AccessDeniedException` thành phản hồi thích hợp, không phải `@PreAuthorize` tự trả HTTP status.

### JDK dynamic proxy và class-based proxy

| Kiểu proxy | Cách tạo | Hệ quả khi thiết kế |
| --- | --- | --- |
| JDK dynamic proxy | Proxy các interface mà bean triển khai | Caller thường nên inject theo interface; những method không nằm trong interface có thể không được expose qua proxy |
| Class-based (CGLIB) proxy | Tạo subclass của class target | Không thể override `final` method; `private` method không thể được advice theo cách này |

Spring Boot có thể cấu hình class-based proxy mặc định hoặc force proxy type trong một số ngữ cảnh; không suy luận proxy luôn là JDK hay CGLIB chỉ từ việc class có interface. **Cả hai loại proxy đều có nguyên lý chung: lời gọi phải đi qua proxy.**

Không dùng `getClass()` của bean để suy đoán chắc chắn việc annotation được enforce. Test đúng phải kiểm tra **hành vi denied/allowed** của method, không chỉ nhìn tên class proxy.

### `@PreAuthorize` thuộc tầng service hay HTTP?

Bạn có thể kết hợp hai lớp:

```java
// Quy tắc HTTP: mọi URL API đều cần một user đã đăng nhập.
http.authorizeExchange(exchanges ->
        exchanges.anyExchange().authenticated());

// Quy tắc business method: chỉ ADMIN được lấy báo cáo mật.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOnly() { /* ... */ }
```

Đây là hai **đoạn minh họa** khác scope, không phải method Java hoàn chỉnh. Chúng bảo vệ hai ranh giới:

- HTTP `authenticated()`: user phải đăng nhập để gọi endpoint.
- Method `hasRole('ADMIN')`: thao tác đọc báo cáo chỉ cho ADMIN.

Một user thường đã đăng nhập có thể vượt qua lớp URL nhưng bị từ chối ở method. Nếu method bị bypass do self-invocation, lớp URL **không thay thế** rule ADMIN. Defense-in-depth tốt là cả hai lớp đều đúng.

## 4. Lỗi cốt lõi: `this` không phải proxy

Xem lớp:

```java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.just("restricted-report");
    }

    public Mono<String> unsafeInternal() {
        return this.adminOnly();
    }
}
```

Một controller gọi `reportService.adminOnly()` qua Spring proxy, advice bảo mật thấy method `adminOnly` và kiểm tra ADMIN.

Một controller khác gọi `reportService.unsafeInternal()` qua proxy. Sau khi proxy chuyển lời gọi vào target, code `unsafeInternal()` gọi `this.adminOnly()` trực tiếp trên **target**. Lời gọi nội bộ **không quay ra proxy**, do đó interceptor của `adminOnly` **không chạy**.

```text
ĐƯỜNG AN TOÀN
Controller -> [ReportService proxy] -> @PreAuthorize(adminOnly)
                                        |
                                 role ADMIN?
                                /          \
                              no           yes
                              |             |
                            deny       target.adminOnly

ĐƯỜNG BỊ BYPASS (self invocation)
Controller -> [ReportService proxy] -> target.unsafeInternal()
                                          |
                                          v
                                   this.adminOnly()
                                          |
                              KHÔNG quay qua proxy
                                          |
                                          v
                                 "restricted-report"
```

**Kết luận:** Annotation vẫn nằm trên method, bean có thể vẫn là AOP proxy, và class có thể vẫn được Spring quản lý. Lỗi xảy ra do **đường đi của lời gọi Java**. `this.adminOnly()` hoặc chỉ `adminOnly()` (không ghi `this`) đều là lời gọi self-invocation.

Một biến thể cùng bản chất:

```java
public Mono<String> unsafeInternal() {
    return adminOnly(); // this.adminOnly() ngầm định
}
```

### Vì sao đây là nguy cơ bảo mật thật?

Giả sử `/api/report/unsafe` chỉ yêu cầu `authenticated()` ở tầng URL. User `reader` có role USER, không có ADMIN:

1. HTTP Basic xác thực `reader` thành công.
2. URL-level rule `authenticated()` cho phép request đi qua.
3. Controller gọi `ReportService.unsafeInternal()`.
4. `unsafeInternal` gọi `this.adminOnly()` trực tiếp.
5. Annotation trên `adminOnly` **không được thực thi** cho lời gọi đó.
6. User không có ADMIN vẫn nhận nội dung bảo vệ.

Nếu route này mở public, hậu quả còn nghiêm trọng hơn. Vì vậy **method security bypass không nhất thiết sinh 403/500**; nó có thể trả `200 OK` và dữ liệu bí mật, khiến log trông như request bình thường.

## 5. Reactor `Mono` không tự chữa self-invocation

Đây là bài về Spring Security **reactive**, nên cần thêm một phân biệt quan trọng:

- `Mono`/`Flux` là publisher; chúng không phải AOP proxy.
- Reactor Context mang danh tính đã xác thực qua subscription; nó không tự thay thế interceptor trên method.
- `Mono.defer(...)` và `Mono.fromSupplier(...)` trì hoãn tính toán, nhưng **không khiến `this.method()` đi qua proxy**.
- `subscribeOn(...)` thay đổi scheduler, không khôi phục một authorization advice đã bị bypass.
- `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` có thể cung cấp SecurityContext cho pipeline, nhưng nếu phương thức không bị method security interceptor chặn, **context có mặt cũng không tự đánh giá `@PreAuthorize`**.

Ví dụ:

```java
public Mono<String> unsafeInternal() {
    return Mono.defer(this::adminOnly);
}
```

Đây là **đoạn minh họa trong cùng class `ReportService`**, vẫn không sửa lỗi: khi subscription thực thi supplier, nó vẫn gọi `this.adminOnly()` trên target.

Ngược lại, gọi qua một **Spring bean khác** đã được inject:

```java
@Service
public class SafeWorkflow {
    private final ReportService reportService;

    public SafeWorkflow(ReportService reportService) {
        this.reportService = reportService;
    }

    public Mono<String> run() {
        return reportService.adminOnly();
    }
}
```

`reportService` ở đây là bean do Spring cung cấp (có proxy method-security). `SafeWorkflow.run()` là một lời gọi sang **bean khác**, nên `ReportService.adminOnly()` được advice.

**Lưu ý về side effects:** Khi xây dựng reactive method, nên để công việc I/O và các side effects thực sự diễn ra trong publisher đúng cách, tránh đánh giá nguồn dữ liệu nhạy cảm một cách eager trước khi chính sách được áp dụng. Nhưng lazy execution **không thay** thiết kế ranh giới authorization.

## 6. Phân biệt các nguyên nhân annotation “không có hiệu lực”

| Triệu chứng / cấu trúc | Nguyên nhân khả dĩ | Cách xác minh và xử lý |
| --- | --- | --- |
| `this.adminOnly()` không bị chặn | Self-invocation bỏ qua AOP proxy | Tách lời gọi qua Spring bean khác |
| Gọi `new ReportService()` | Object không do Spring container quản lý | Inject Spring bean thay vì tự `new` |
| Có `@PreAuthorize` nhưng app chưa bật method security | Không đăng ký reactive advisors | Thêm `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` |
| Dùng `@EnableMethodSecurity` kiểu Servlet ở WebFlux | Sai cấu hình security stack | Dùng reactive method security và `ServerHttpSecurity` |
| Đặt annotation trên `private` method | Private method không được proxy advice | Đưa rule lên public entry point hoặc service công khai được proxied |
| Đặt annotation trên `final` method với class-based proxy | Proxy subclass không thể override | Loại `final`/mở class hoặc thiết kế qua interface phù hợp |
| Class `final` nhưng dự kiến CGLIB | Không thể tạo subclass proxy | Không dùng class final cho class-based proxy; xét kiểu proxy thật |
| Code gọi target object thay vì Spring bean | Không qua proxy | Inject bean qua constructor |
| Interface proxy nhưng caller cần method ngoài interface | Method không nằm trong hợp đồng proxy | Inject qua interface có method đó hoặc dùng class-based proxy được hỗ trợ |
| Method không trả reactive publisher phù hợp | Sai kiểu cho cơ chế reactive method authorization | Dùng `Mono`/`Flux` theo API/version; không giả định sync method được advice tương tự |
| Test gọi method trong class bằng `this` | Test vô tình bypass dù có annotation | Test gọi bean từ `ApplicationContext` |
| `onErrorResume(ex -> Mono.just(secret))` nuốt lỗi denied | Code tự thay kết quả lỗi bằng dữ liệu | Không biến `AccessDeniedException` thành success |
| `403` vì thiếu role | Method security **đã** hoạt động và deny | Kiểm tra authorities/SpEL, không coi là annotation vô hiệu |
| `401` do thiếu credential | Chưa xác thực qua filter | Kiểm tra HTTP Basic/session và SecurityContext |
| SpEL dùng tên tham số sai | Expression không truy được argument | Kiểm tra parameter metadata/annotation và error message |
| HTTP authorization rule quá rộng | URL-level policy sai, không nhất thiết method security sai | Test cả controller và service |
| `@PostAuthorize` có side effect đã xảy ra | Kiểm tra sau khi lấy kết quả quá muộn cho hành động không đảo ngược | Dùng `@PreAuthorize` cho write operation, thiết kế nghiệp vụ an toàn |

**Lời khuyên kiểm chứng:** Một 200 bất thường có nhiều nguyên nhân. Hãy kiểm tra có thực sự gọi method annotated **qua bean proxy** không trước khi thay SpEL hoặc bật DEBUG tràn lan.

### `private`, `final` và khả năng proxy

Trong cấu hình class-based proxy, proxy là subclass nên không intercept được `final` method và `private` method; `final` class không thể subclass. Với JDK dynamic proxy, proxy exposes interface methods, nhưng self-invocation **vẫn bypass**. Spring Security method annotations có thể hỗ trợ nhiều vị trí khai báo tùy mode/version, nhưng để bài học chắc chắn, chọn **public, non-final method trên Spring bean**, được gọi qua reference do Spring inject.

Với Kotlin, class/method mặc định final có thể cần plugin `kotlin-spring`/`all-open` hoặc thiết kế giao diện thích hợp; đừng copy Java example rồi kết luận proxy hoạt động trong Kotlin mà không kiểm chứng.

## 7. Cách sửa: thứ tự ưu tiên

### Cách A — Tách trách nhiệm sang hai bean (khuyến nghị)

Thay:

```java
// Một class tự gọi method nhạy cảm của chính nó:
public Mono<String> execute() {
    return this.adminOnly();
}
```

Bằng thiết kế:

```text
Controller
   |
   v
SafeWorkflow (bean)
   |
   v
ReportService (bean proxy)
   |
   v
@PreAuthorize("hasRole('ADMIN')")
   |
   v
ReportService.adminOnly()
```

Cách này làm boundary bảo mật rõ ràng, dễ test, không cần biết proxy thuộc JDK hay CGLIB để gọi đúng phương thức.

### Cách B — Bảo vệ ngay entry point được gọi từ bên ngoài

Nếu logic cần cùng bean và public API rõ ràng, có thể đặt `@PreAuthorize` lên **method public mà caller thật sự gọi qua proxy**, thay vì chỉ đặt annotation trên một helper được gọi bằng `this`.

Ví dụ:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> exportReport() {
    return internalComputeReport();
}

private Mono<String> internalComputeReport() {
    return Mono.just("restricted-report");
}
```

Đây là fragment trong một Spring bean đã bật method security. Khi **mọi con đường** vào `internalComputeReport()` đều đi qua `exportReport()`, policy được áp dụng ở public boundary. Tuy nhiên, nếu class có **nhiều public đường vào** hoặc một method khác gọi `this.exportReport()`, bạn vẫn phải rà soát self-invocation và boundary. Không xem annotation trên một public method là bao phủ mọi đường tới helper.

### Cách C — Self-injection (có thể, nhưng cần thận trọng)

Có thể inject một reference đến proxy của chính bean rồi gọi qua reference đó, thay vì `this`. Nhưng giải pháp này tạo vòng phụ thuộc, phức tạp lifecycle và dễ che giấu kiến trúc chưa tốt. Nếu bắt buộc dùng, cần thiết kế phụ thuộc qua `ObjectProvider`/lazy injection thích hợp, kiểm thử container thật, tránh tự tạo proxy hoặc giữ target object.

**Ưu tiên tách bean**, vì dễ review và ít phụ thuộc vào chi tiết Spring AOP hơn.

### Cách D — `AopContext.currentProxy()` (không khuyến khích)

Spring Framework cung cấp `AopContext.currentProxy()` trong một số cấu hình proxy có bật `exposeProxy`. Tuy nhiên, nó phụ thuộc vào hạ tầng AOP, thời điểm thực thi và việc proxy có thật sự được expose. Trong pipeline reactive có thể thay đổi thread và thời điểm subscription, càng không nên coi đây là giải pháp mặc định.

Đừng tự thêm `AopContext.currentProxy()` vào code nghiệp vụ để chữa lỗi nếu một refactor tách bean có thể giải quyết rõ ràng hơn.

### Cách E — AspectJ weaving (khác proxy AOP mặc định)

AspectJ compile-time hoặc load-time weaving có thể advice cả self-invocation vì nó thay đổi/instrument bytecode theo cơ chế khác. Nhưng `@EnableReactiveMethodSecurity` dựa trên Spring AOP proxy trong cấu hình bài này; việc “cài AspectJ dependency” **không tự** chuyển toàn bộ reactive method security sang một weaver hỗ trợ mọi annotation. Muốn dùng weaving phải có thiết kế, cấu hình, công cụ build/runtime và kiểm thử riêng. Với đa số ứng dụng WebFlux, **không cần** giải pháp này nếu chỉ muốn sửa self-invocation.

## 8. Dự án Java 17+ / Spring Boot 3.3.5 để tái hiện và sửa lỗi

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.5**, Spring Security 6.x do Boot quản lý, Gradle 8.5 hoặc wrapper tương thích. Toàn bộ request demo là GET để tập trung vào method authorization, tránh phải trộn thêm CSRF cho POST.

Mục tiêu quan sát:

- `GET /api/report/direct`: gọi method `adminOnly` **trực tiếp qua bean proxy**.
- `GET /api/report/unsafe`: gọi method `unsafeInternal` rồi nội bộ `this.adminOnly()`, **bypass** role check.
- `GET /api/report/safe`: gọi `SafeWorkflow.run()`, chuyển sang **bean `ReportService`**, role check có hiệu lực.
- `GET /health`: public; còn các route API trước hết yêu cầu đăng nhập.

Cấu trúc project:

```text
reactive-method-aop-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/methodaop/
    │   ├── MethodAopApplication.java
    │   ├── SecurityConfig.java
    │   ├── ReportService.java
    │   ├── SafeWorkflow.java
    │   └── ReportController.java
    └── test/java/dev/example/methodaop/
        └── MethodAopSecurityTests.java
```

### 8.1. Gradle files

`settings.gradle`:

```groovy
rootProject.name = 'reactive-method-aop-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

`spring-boot-starter-webflux` dùng WebFlux/Reactor. Không thêm `spring-boot-starter-web` khi muốn WebFlux thuần: có cả hai starter thường khiến Spring Boot chọn Servlet/MVC thay vì reactive web application.

### 8.2. Main application

`src/main/java/dev/example/methodaop/MethodAopApplication.java`:

```java
package dev.example.methodaop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodAopApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodAopApplication.class, args);
    }
}
```

### 8.3. WebFlux và method security configuration

`src/main/java/dev/example/methodaop/SecurityConfig.java`:

```java
package dev.example.methodaop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/health").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Điểm quan trọng:

- `@EnableWebFluxSecurity` bật cấu hình HTTP WebFlux Security; `@EnableReactiveMethodSecurity` bật **method-level authorization**. Chúng không phải một annotation duy nhất.
- `MapReactiveUserDetailsService` tạo tài khoản mẫu reader có `ROLE_USER` và admin có cả `ROLE_USER`, `ROLE_ADMIN`.
- `.anyExchange().authenticated()` yêu cầu đăng nhập ở URL; **chưa yêu cầu ADMIN**. Yêu cầu ADMIN chỉ có ở `@PreAuthorize` trên method nhạy cảm.
- `httpBasic` được bật để kiểm thử bằng curl/WebTestClient; form login tắt để các status dễ thấy.
- Password được băm BCrypt trong bộ nhớ. Hai mật khẩu demo trong source **không dùng cho production**.
- Vì mọi request trong bài là GET, CSRF mặc định không gây 403 do thiếu CSRF token; đừng suy rộng rằng API POST sẽ có hành vi giống hệt.

### 8.4. Bean có self-invocation (cố ý sai để học)

`src/main/java/dev/example/methodaop/ReportService.java`:

```java
package dev.example.methodaop;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.fromSupplier(() -> "restricted-report");
    }

    // Chỉ để tái hiện lỗi self-invocation trong demo local.
    public Mono<String> unsafeInternal() {
        return this.adminOnly();
    }
}
```

`ReportService` là public, không final, method `adminOnly` là public, non-final, và bean do Spring quản lý. Tức là các điều kiện AOP cơ bản **đều đúng**. Điểm sai chỉ nằm ở lời gọi `this.adminOnly()`. `Mono.fromSupplier` giữ giá trị lazy để người học không nhầm side effect ở thời điểm assembly; nó **không sửa** vấn đề proxy.

### 8.5. Bean workflow sửa bằng gọi qua proxy

`src/main/java/dev/example/methodaop/SafeWorkflow.java`:

```java
package dev.example.methodaop;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SafeWorkflow {

    private final ReportService reportService;

    public SafeWorkflow(ReportService reportService) {
        this.reportService = reportService;
    }

    public Mono<String> run() {
        return reportService.adminOnly();
    }
}
```

Vì `ReportService` được Spring inject vào `SafeWorkflow`, đối tượng được sử dụng là bean có proxy AOP. Khi `SafeWorkflow.run()` gọi `reportService.adminOnly()`, interceptor có cơ hội kiểm tra role trước khi kết quả được phát xuống pipeline.

### 8.6. Controller phơi bày ba đường so sánh

`src/main/java/dev/example/methodaop/ReportController.java`:

```java
package dev.example.methodaop;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    private final ReportService reportService;
    private final SafeWorkflow safeWorkflow;

    public ReportController(ReportService reportService,
                            SafeWorkflow safeWorkflow) {
        this.reportService = reportService;
        this.safeWorkflow = safeWorkflow;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/report/direct")
    public Mono<String> direct() {
        return reportService.adminOnly();
    }

    // CHỈ DÀNH CHO DEMO LOCAL, KHÔNG ĐƯỢC TRIỂN KHAI THẬT.
    @GetMapping("/api/report/unsafe")
    public Mono<String> unsafe() {
        return reportService.unsafeInternal();
    }

    @GetMapping("/api/report/safe")
    public Mono<String> safe() {
        return safeWorkflow.run();
    }
}
```

**Phân tích kết quả mong đợi:**

| Endpoint | Caller thực tế | User reader (`ROLE_USER`) | User admin (`ROLE_ADMIN`) |
| --- | --- | --- | --- |
| `GET /health` | Controller trả public | 200, `ok` | 200, `ok` |
| `GET /api/report/direct` | Controller → `ReportService` proxy → `adminOnly` | **403** | 200, `restricted-report` |
| `GET /api/report/unsafe` | Controller → `unsafeInternal` → **`this.adminOnly`** | **200, `restricted-report` (LỖ HỔNG DEMO)** | 200, `restricted-report` |
| `GET /api/report/safe` | Controller → `SafeWorkflow` → `ReportService` proxy | **403** | 200, `restricted-report` |
| `GET /api/report/unsafe` không có credential | URL `authenticated()` chặn trước | **401** | Không áp dụng |

**Giải thích 401/403/200:** reader thiếu ADMIN nhưng **đã được HTTP Basic xác thực**; direct/safe bị method security từ chối nên 403. Unsafe cho ra 200 vì method security advisor trên `adminOnly` không chạy. User chưa đăng nhập bị URL-level filter chặn 401, dù bên trong vẫn tồn tại đường self-invocation nguy hiểm.

## 9. Chạy demo và quan sát bằng curl

Ở thư mục `reactive-method-aop-demo`:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper: `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Ví dụ dùng `http://localhost:8080` để chạy local; **HTTP Basic cần HTTPS trong môi trường thật**, không truyền password qua internet bằng HTTP.

Trong terminal khác:

```bash
curl -i http://localhost:8080/health

curl -i http://localhost:8080/api/report/direct

curl -i -u reader:reader-pass http://localhost:8080/api/report/direct
curl -i -u reader:reader-pass http://localhost:8080/api/report/unsafe
curl -i -u reader:reader-pass http://localhost:8080/api/report/safe

curl -i -u admin:admin-pass http://localhost:8080/api/report/direct
curl -i -u admin:admin-pass http://localhost:8080/api/report/safe
```

Các mật khẩu ở trên là **giả và chỉ phục vụ demo local**; không đưa password thật vào command-line vì shell history/process arguments có thể ghi lại. Với dịch vụ thật, dùng HTTPS và cách nhập secret an toàn (ví dụ curl hỏi password khi chỉ cung cấp username).

Kết quả dự kiến chính:
- `/health` → 200, body `ok`.
- `/api/report/direct` không credential → 401.
- Reader gọi `/direct` → 403.
- Reader gọi `/unsafe` → **200, body `restricted-report`**, chỉ để thấy self-invocation bypass.
- Reader gọi `/safe` → 403.
- Admin gọi `/direct` hoặc `/safe` → 200, body `restricted-report`.

Đây là **kết quả dự kiến của ví dụ**, không phải log đã chạy Gradle. Một số headers/error body có thể khác theo phiên bản, nhưng khác biệt authorization quan trọng là **reader: direct=403, unsafe=200, safe=403**.

## 10. Kiểm thử tích hợp với `WebTestClient`

Test phải bắt được cả một **lỗ hổng trả 200 không mong muốn**. Nếu chỉ kiểm tra admin được 200, bạn không biết reader có thể truy cập trái phép qua đường nội bộ hay không.

Tệp `src/test/java/dev/example/methodaop/MethodAopSecurityTests.java`:

```java
package dev.example.methodaop;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MethodAopSecurityTests {

    @Autowired
    WebTestClient client;

    @Autowired
    ReportService reportService;

    @Test
    void reportServiceIsSpringAopProxy() {
        assertTrue(AopUtils.isAopProxy(reportService));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void anonymousCannotEnterApi() {
        client.get().uri("/api/report/unsafe")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerIsDeniedByDirectProxyInvocation() {
        client.get().uri("/api/report/direct")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerCanIncorrectlyAccessSelfInvocation() {
        // Bài test mô tả lỗ hổng demo, không phải hành vi mong muốn production.
        client.get().uri("/api/report/unsafe")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void readerIsDeniedWhenWorkflowCallsOtherBean() {
        client.get().uri("/api/report/safe")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallDirectMethod() {
        client.get().uri("/api/report/direct")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void adminCanCallSafeWorkflow() {
        client.get().uri("/api/report/safe")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void adminCanCallUnsafeDemoRoute() {
        client.get().uri("/api/report/unsafe")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        client.get().uri("/api/report/direct")
                .headers(h -> h.setBasicAuth("reader", "incorrect"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng:** 10 test thành công với cấu hình demo. Đây là kỳ vọng từ mã và contract, **không phải báo cáo rằng Gradle đã thực thi trên máy của bạn**.

### Vì sao kiểm tra `AopUtils.isAopProxy` chưa đủ?

Bean có thể là proxy vì một advisor khác (transaction, cache, logging...). `AopUtils.isAopProxy(bean) == true` chỉ chứng tỏ nó là Spring AOP proxy, **không chứng minh** một `@PreAuthorize` cụ thể chạy với mọi đường gọi. Những test quan trọng nhất là:

- Reader direct → 403.
- Reader unsafe → **200** (lộ đường bypass).
- Reader safe → 403.

Khi refactor xong, **xóa route unsafe** và thay test “reader can incorrectly access” bằng test **reader phải bị từ chối với tất cả business entry points nhạy cảm**. Không giữ một test chấp nhận lỗ hổng như tiêu chí production.

### Một test method-level không đi qua HTTP

Nếu không muốn dùng HTTP Basic, có thể inject `ReportService` từ Spring `ApplicationContext` và gắn authentication vào Reactor Context khi dùng `StepVerifier`:

```java
Authentication reader = UsernamePasswordAuthenticationToken.authenticated(
        "reader", null,
        java.util.List.of(
                new SimpleGrantedAuthority("ROLE_USER")));

StepVerifier.create(
        reportService.adminOnly()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(reader)))
        .expectError(AccessDeniedException.class)
        .verify();
```

**Đây là đoạn minh họa trong một JUnit test**, không phải file test độc lập. Cần imports `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `ReactiveSecurityContextHolder`, `AccessDeniedException`, `StepVerifier` và dependency `io.projectreactor:reactor-test`. Đoạn này kiểm chứng direct invocation qua proxy với Reactor Context; với `this.adminOnly()` trong target, interception vẫn bị bypass.

Ưu điểm của test HTTP là nó còn xác nhận security filter tạo Reactor Context từ request thật. Ưu điểm của test Reactor là cô lập logic method-level. Cả hai hữu ích, không thay thế nhau hoàn toàn.

## 11. Làm sao sửa bản demo trước khi chuyển sang sản phẩm?

Một bản production đơn giản nên **không có `unsafeInternal()` và không có route `/api/report/unsafe`**. Giữ:

```text
ReportController
    |
    v
SafeWorkflow.run()
    |
    v
ReportService proxy
    |
    v
@PreAuthorize("hasRole('ADMIN')")
    |
    v
ReportService.adminOnly()
```

Hoặc để controller gọi trực tiếp `ReportService.adminOnly()` từ bean được inject, nếu không cần thêm orchestration. Khi đưa ra production, cần:

1. Xóa endpoint khai thác self-invocation.
2. Kiểm tra mọi public method/entry point có thể đến nghiệp vụ nhạy cảm.
3. Giữ một nơi kiểm tra quyền có thể thực thi được, chẳng hạn service boundary qua bean proxy.
4. Viết test **non-admin bị từ chối** cho từng đường vào, không chỉ admin được phép.
5. Giữ URL-level rule phù hợp thay vì trông chờ mọi caller đều dùng method proxy.
6. Thêm authorization theo resource ownership/tenant nếu dữ liệu nhạy cảm không chỉ phụ thuộc role ADMIN.
7. Bảo đảm không có pathway gọi bean bằng `new` hoặc gọi target object từ code framework.
8. Kiểm tra transaction/async/cache annotations nếu chúng cũng dựa trên Spring AOP proxy.

Đối với thao tác ghi dữ liệu, nên dùng `@PreAuthorize` cho quyền **trước khi** thực thi thao tác. `@PostAuthorize` kiểm tra sau khi có kết quả; đừng dùng nó làm biện pháp duy nhất bảo vệ side effects không thể đảo ngược.

## 12. Một số câu hỏi chuyên sâu và tình huống biên

### 12.1. Nếu method đã public và bean có proxy, vì sao vẫn bị bypass?

Vì lời gọi `this.adminOnly()` đi **trên target**, không đi qua proxy. Public hay non-final chỉ tạo điều kiện cho proxy advice trên lời gọi bên ngoài; chúng không biến mọi lời gọi nội bộ thành lời gọi proxy.

### 12.2. Nếu thêm `Mono.defer(() -> adminOnly())` thì sao?

Vẫn bypass nếu lambda đang giữ `this`/target. Reactor defer trì hoãn thực thi, không đổi người nhận lời gọi. Chỉ khi lambda gọi một reference **đến Spring proxy khác** thì advice tương ứng mới có cơ hội chạy.

### 12.3. Nếu method protected/private thì annotation có được nhận không?

Không giả định mọi visibility đều được advice. Private method không thể override qua class-based proxy; JDK proxy cũng không expose private method. Với method security trong môi trường proxy, cách dễ bảo đảm là đặt policy ở **public bean entry point** được gọi từ bên ngoài.

### 12.4. Nếu `@PreAuthorize` đặt trên interface?

Spring Security có các cơ chế tìm annotation trên interface/class tùy cấu hình và proxy strategy. Nên tham khảo tài liệu cho version sử dụng, tránh annotation conflict; quan trọng hơn là **test hành vi qua interface bean** và không nghĩ annotation trên interface sẽ giúp `this` đi qua proxy.

### 12.5. Nếu không có `ReactiveSecurityContextHolder`?

Trong WebFlux tích hợp Spring Security, `ReactorContextWebFilter` thường chuyển security context theo pipeline. Nếu bạn gọi service trực tiếp trong unit test mà không gắn authentication vào Reactor Context, có thể nhận lỗi thiếu context hoặc deny. Điều đó **khác với self-invocation**: ở self-invocation, lời gọi annotation không đi qua advisor ngay từ đầu.

### 12.6. Nếu dùng `@Transactional` hay `@Cacheable` có tự gọi nội bộ?

Những cơ chế dùng Spring AOP **proxy mode** cũng có vấn đề tương tự: gọi từ method khác trong cùng target có thể bỏ qua transaction/cache advice. Nhưng mỗi annotation có semantics riêng; không suy luận một workaround Spring Security bảo đảm sửa mọi annotation nếu proxy topology khác.

### 12.7. Nếu sử dụng AspectJ có tự hết lỗi?

AspectJ weaving (compile-time/load-time) khác Spring AOP proxy và có thể advice self-invocation. Nhưng method security reactive mặc định dùng proxy; không thể chỉ thêm dependency AspectJ rồi giả định `@PreAuthorize` tự được woven đúng. Giải pháp tách bean thường đơn giản và an toàn hơn.

### 12.8. Nếu không có ADMIN nhưng endpoint vẫn 200?

Đừng vội kết luận SpEL `hasRole` lỗi. Kiểm tra:
- Request có đi qua target bean proxy thật không?
- Có lời gọi `this.method()` trong giữa?
- Bean được tạo bởi Spring hay tự `new`?
- `@EnableReactiveMethodSecurity` có được bật?
- Có `@PreAuthorize` trên đúng method/implementation?
- Có một `onErrorResume` nuốt `AccessDeniedException` rồi trả dữ liệu?
- Còn route/service nào khác truy cập dữ liệu mà không có rule?
- HTTP chain chỉ yêu cầu login thay vì quyền cần thiết?
- Có kiểm thử âm tính với user thiếu quyền ở **mọi đường vào** chưa?

## 13. Checklist khi review code có method security

1. **Boundary:** Annotation ở method public của Spring bean thực sự được gọi qua proxy.
2. **No self-invocation:** Không có `this.sensitiveMethod()` hoặc gọi ngầm `sensitiveMethod()` trong cùng class khi trông cậy vào advice.
3. **Enable:** Cấu hình `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` được load, không nhầm Servlet stack.
4. **Bean lifecycle:** Service đến từ dependency injection, không được tạo bằng `new`.
5. **Proxyability:** Class/method không vô tình `final`/`private` khi dùng class-based proxy; interface được inject đúng khi dùng JDK proxy.
6. **Reactive return:** Method được bảo vệ trả `Mono`/`Flux` phù hợp; không gọi `block()` trong WebFlux handler.
7. **Context:** Authentication được truyền qua Reactor Context; test trực tiếp phải tạo context phù hợp.
8. **Expression:** `hasRole("ADMIN")` tương ứng authority `ROLE_ADMIN` theo prefix mặc định; `hasAuthority` so chuỗi chính xác.
9. **Error:** Không nuốt `AccessDeniedException` hoặc biến denied thành success bằng fallback.
10. **Defense in depth:** HTTP authorization + method authorization đều được rà soát.
11. **Tests:** Reader/non-admin bị 403 ở mọi entry point nhạy cảm; admin được 200; anonymous 401 phù hợp.
12. **Deployment:** Không có endpoint demo unsafe, không có credential demo và không dùng HTTP Basic không TLS ngoài localhost.

## 14. Bảng so sánh trước và sau sửa

| Tiêu chí | Trước: self-invocation | Sau: tách bean |
| --- | --- | --- |
| Đường gọi | `this.adminOnly()` trong target | `safeWorkflow -> reportService proxy -> adminOnly()` |
| Có đi qua proxy `adminOnly`? | Không | Có |
| `@PreAuthorize` kiểm tra? | Bị bypass | Được áp dụng |
| Reader thiếu ADMIN | Có thể nhận secret 200 | Bị từ chối 403 |
| Admin | Được trả kết quả | Được trả kết quả |
| Test âm tính | Dễ bỏ sót nếu chỉ test user ADMIN | Test trực tiếp và workflow cùng thể hiện deny |
| Coupling với AOP API | Có thể không rõ nhưng sai ở đường gọi | Không cần gọi `AopContext` |
| Cách vận hành | Nguy cơ escalation | Thiết kế proxy boundary rõ ràng |

Dù đã tách bean, **mọi đường vào khác** của dữ liệu nhạy cảm vẫn cần được kiểm tra. Một method được bảo vệ đúng không làm cho database, cache hoặc endpoint khác tự động an toàn.

## 15. Câu hỏi tự kiểm tra và đáp án

**1. Spring AOP proxy có chức năng gì trong method security?**  
Cho phép Spring chặn lời gọi method từ bên ngoài để chạy authorization advice trước/sau khi gọi target.

**2. Vì sao `this.adminOnly()` bỏ qua `@PreAuthorize`?**  
Vì lời gọi ở bên trong target không quay lại Spring proxy, nên advice cho method đó không được gọi.

**3. `Mono.defer(this::adminOnly)` có sửa được không?**  
Không. Nó chỉ trì hoãn self-invocation; người nhận vẫn là target, không phải proxy.

**4. Tại sao một Spring bean đã là proxy vẫn có thể xảy ra self-invocation?**  
Proxy bảo vệ lời gọi **đi qua proxy**. Bên trong target, `this` vẫn trỏ đến target object.

**5. Phương án sửa ưu tiên nhất?**  
Tách thao tác bảo vệ sang bean riêng, inject bean đó và gọi method public qua Spring proxy. Hoặc bảo vệ đúng public entry point mà tất cả caller thực sự đi qua.

**6. Role và authority khác nhau ra sao?**  
`roles("ADMIN")` thường tạo authority `ROLE_ADMIN`; `hasRole("ADMIN")` kiểm tra authority có prefix. `hasAuthority("reports:read")` kiểm tra chuỗi authority nguyên văn.

**7. Nếu dùng `new ReportService()`, annotation có chạy không?**  
Thông thường không: object không qua Spring container/proxy method-security.

**8. Vì sao `private`/`final` method không phù hợp với class-based proxy?**  
Private method không thể override; final method không thể override. Proxy subclass không thể đặt advice theo cơ chế thông thường lên các lời gọi đó.

**9. Tại sao test admin nhận 200 là chưa đủ?**  
Vì user thiếu quyền vẫn có thể nhận 200 trên một đường self-invocation. Phải có test âm tính với reader.

**10. Kết quả dự kiến cho reader ở ba endpoint demo?**  
`/direct` → 403; `/unsafe` → 200 (lỗi demo); `/safe` → 403.

**11. Khi nào lỗi method authorization trở thành HTTP 403?**  
Khi lời gọi method bị chặn bằng tín hiệu access denied và WebFlux Security xử lý thành response Forbidden cho user đã xác thực.

**12. `@EnableWebFluxSecurity` có tự kích hoạt method security không?**  
Không nên dựa vào điều đó. Cần bật `@EnableReactiveMethodSecurity` cho annotation-based reactive method authorization.

**13. Nếu dùng Kotlin class final, cần chú ý gì?**  
Class-based proxy không subclass được final class; có thể cần mở class bằng plugin phù hợp hoặc tổ chức interface/proxy khác, rồi kiểm thử.

**14. Vì sao `AopUtils.isAopProxy` chưa chứng minh quyền được kiểm tra?**  
Vì bean có proxy không bảo đảm mọi đường gọi đi qua đúng advisor; test behavior denied mới là bằng chứng quan trọng.

### Bài tập thực hành

1. Chạy demo và xác nhận bằng `curl` hoặc `WebTestClient` rằng reader direct/safe bị 403 nhưng unsafe nhận 200. Giải thích **chính xác** chỗ proxy bị bỏ qua.
2. Xóa `unsafeInternal()`, thay endpoint `/api/report/unsafe` bằng lời gọi `safeWorkflow.run()` hoặc xóa endpoint. Sửa test để **reader luôn bị 403** ở tất cả entry point.
3. Thêm method `@PreAuthorize("hasAuthority('report:export')")` vào bean khác, tạo user có permission và kiểm thử quyền bằng `WebTestClient`.
4. Viết một method `public Mono<String> invokeIndirect() { return adminOnly(); }` trong `ReportService` rồi test. Giải thích tại sao bỏ `this` không sửa lỗi.
5. Thử đặt `@PreAuthorize` lên private helper rồi giải thích vì sao không nên tin proxy-based interception ở đó. Không vận hành phương án sai trên production.
6. Viết test `AopUtils.isAopProxy(reportService)` và một test reader denied; lý giải vì sao test thứ hai cần thiết hơn.
7. Thêm một `onErrorResume(AccessDeniedException.class, ... )` vào layer controller chỉ trong môi trường học, quan sát nguy cơ trả kết quả thành công khi exception bị nuốt; sau đó loại bỏ.
8. Vẽ lại sơ đồ workflow với hai bean và chỉ rõ controller phải nhận **Spring-managed bean** từ constructor injection, không tự `new`.

## 16. Tài liệu chính thức

- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, Reactor Context và hạ tầng method interceptor.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxy, `this` self-invocation, giới hạn `final`/`private` và các phương án thay thế.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): advice, proxy và pointcut.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): HTTP authentication/authorization và `SecurityWebFilterChain`.
- [Spring Security — Reactive Method Security tests](https://docs.spring.io/spring-security/reference/servlet/test/method.html): các ví dụ method security test; khi áp dụng cho reactive cần dùng Reactor Context đúng.
- [Project Reactor — Adding a Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context và subscription.
- [Spring Boot Gradle Plugin 3.3.5](https://docs.spring.io/spring-boot/docs/3.3.5/gradle-plugin/reference/htmlsingle/): cách chạy ứng dụng và Gradle tasks.

**Ghi nhớ:** `@PreAuthorize` hoạt động khi **lời gọi đi qua Spring AOP proxy**. `this.someMethod()` trong cùng target **không đi qua proxy**, nên annotation trên method được gọi có thể bị bypass dù đây là WebFlux và method trả `Mono`. Cách sửa bền vững là **đặt authorization ở public boundary được gọi từ bên ngoài** hoặc **tách thao tác được bảo vệ sang Spring bean khác**, đồng thời kiểm thử user thiếu quyền ở mọi đường vào.