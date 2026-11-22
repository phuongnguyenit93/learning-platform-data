# @PreAuthorize và kiểm tra quyền trước khi thực thi nghiệp vụ

## Mục tiêu học tập

Bài học thuộc **Phân quyền phương thức** trong **Spring Security reactive (Spring WebFlux)**. Sau bài này, bạn có thể:

- Giải thích `@PreAuthorize` là **kiểm tra authorization trước khi phương thức nghiệp vụ được phép chạy**, khác với authentication và khác rule URL trong `authorizeExchange(...)`.
- Bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` và hiểu cách Spring AOP, `AuthorizationManagerBeforeReactiveMethodInterceptor`, `ReactiveSecurityContextHolder` và Reactor `Context` phối hợp.
- Viết expression SpEL như `hasRole('ADMIN')`, `hasAuthority('SCOPE_reports.read')`, `isAuthenticated()`, so sánh tham số `#p0` với `authentication.name` và gọi bean kiểm tra quyền.
- Hiểu vì sao method reactive được bảo vệ nên trả `Mono<T>` hoặc `Flux<T>`, và vì sao phải giữ side effect trong pipeline để có thể xác minh **không thực thi nghiệp vụ khi bị từ chối**.
- Phân biệt `AccessDeniedException` nội bộ với status HTTP 401/403, và trường hợp `@PreAuthorize` không hoạt động do self-invocation hoặc thiếu Spring proxy.
- Chạy ví dụ **Java 17 + Spring WebFlux**, kiểm thử method security bằng Reactor `StepVerifier` và test HTTP với credentials hợp lệ/không đủ quyền.

> **Phạm vi:** Spring Security **reactive** với `@EnableReactiveMethodSecurity`. Không trộn với `@EnableMethodSecurity`/`SecurityContextHolder` kiểu ThreadLocal của Servlet. Bài này tập trung vào **before-method authorization**; một số API như `@PostAuthorize` được nhắc tới chỉ để phân biệt.

## 1. Vì sao phải kiểm tra quyền ở tầng phương thức?

Một hệ thống WebFlux thường có nhiều đường gọi đến cùng một service:

~~~text
HTTP Controller ---------+
                         |
Message Consumer --------+--> ReportService.readConfidentialReport()
                         |
Scheduled Job -----------+
                         |
Một service khác --------+
~~~

Nếu chỉ phân quyền ở HTTP URL, bạn đang bảo vệ những lời gọi **đi qua controller**. Những lời gọi khác, hoặc một route mới vô tình gọi service, có thể không được ràng buộc bởi cùng rule. Method security thêm một **ranh giới bảo vệ gần nơi thực hiện nghiệp vụ**.

Ví dụ yêu cầu: *Chỉ user có role ADMIN mới được đọc báo cáo nội bộ*.

HTTP-level rule:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated());
~~~

Đây là **mảnh cấu hình `ServerHttpSecurity`**, không phải chương trình Java độc lập. Nó bảo vệ URL `/api/admin/**`, nhưng giả sử controller ở `/api/reports/secret` hoặc một job gọi thẳng service thì rule trên không trực tiếp bao phủ lời gọi ấy.

Bổ sung bảo vệ ở service:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readConfidentialReport() {
        return Mono.just("internal-report");
    }
}
~~~

Đoạn trên là class minh họa; các import là `@Service`, `@PreAuthorize` và `Mono`. Khi bật reactive method security, một lời gọi qua Spring proxy sẽ được quyết định authorization **trước khi method body được phép thực thi**. Người không đủ quyền nhận lỗi và không nhận dữ liệu bảo mật.

**Defense in depth:** Nên có cả HTTP authorization (ai được gọi route) và method authorization (ai được thực hiện nghiệp vụ). Hai lớp có thể dùng rule khác nhau. `permitAll()` ở URL **không ghi đè** `@PreAuthorize` ở service.

## 2. Authentication và authorization khác nhau

- **Authentication (xác thực):** Người gửi request có danh tính nào? Ví dụ `Authentication.getName() == "reader"`, authorities chứa `ROLE_USER`.
- **Authorization (phân quyền):** Danh tính đó có được thực hiện hành động cụ thể trên tài nguyên cụ thể không?
- **HTTP authorization:** `ServerHttpSecurity.authorizeExchange(...)` đánh giá request/matcher ở WebFilter chain.
- **Method authorization:** `@PreAuthorize(...)` đánh giá một **method invocation**, có thể dùng principal, role, authority và tham số của method.

| Tình huống | Quyết định ở phương thức | Ý nghĩa |
|---|---|---|
| Anonymous gọi method yêu cầu `hasRole('ADMIN')` | Từ chối | Chưa có Authentication đáp ứng rule. |
| User `reader` đã đăng nhập, chỉ có `ROLE_USER` | Từ chối | Authenticated nhưng thiếu role ADMIN. |
| User `admin` có `ROLE_ADMIN` | Cho phép | Method body được phép được gọi. |
| User authenticated gọi method chỉ cho phép đọc bản ghi của mình | Tùy identity + ownership | Role chung chưa đủ; cần policy theo tài nguyên. |
| URL công khai `permitAll()` gọi method yêu cầu ADMIN | Vẫn có thể bị từ chối | HTTP-level permit và method-level permit là hai quyết định độc lập. |

Không suy luận rằng user đã authenticated thì được xem mọi dữ liệu. Cũng không coi một header `X-Role: ADMIN` do client gửi là GrantedAuthority đã xác minh.

## 3. Bật Reactive Method Security đúng cách

Với Spring Security 6.x, cách khai báo được tài liệu khuyến nghị:

~~~java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfig {
}
~~~

Cần import `org.springframework.context.annotation.Configuration` và `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`. Annotation có thể đặt trên class cấu hình Spring khác; ví dụ bài thực hành đặt trực tiếp cùng `@SpringBootApplication`.

Các điều kiện thiết yếu:

1. Đưa dependency Spring Security phù hợp vào ứng dụng WebFlux.
2. Bật **`@EnableReactiveMethodSecurity`** — chỉ bật `@EnableWebFluxSecurity` hoặc `http.authorizeExchange(...)` chưa đủ để tự kích hoạt `@PreAuthorize` trên service.
3. Method nằm trên **bean do Spring quản lý**, được gọi **qua Spring AOP proxy** (không phải `new ReportService()` hoặc `this.method()` tự gọi trong cùng class).
4. Method được bảo vệ trả reactive `Publisher` như `Mono` hoặc `Flux` để Spring có thể tích hợp với **Reactor Context**. Với các phiên bản hỗ trợ Kotlin coroutines có cơ chế riêng.
5. Có Authentication được thiết lập vào context theo reactive subscription, chẳng hạn WebFlux security filter chain tạo nó từ HTTP Basic/Bearer/form login.

### 3.1. AuthorizationManager và Spring AOP làm gì?

Với `useAuthorizationManager=true`, Spring Security tạo các method interceptor dựa trên `AuthorizationManager`. Đối với `@PreAuthorize`, cơ chế before-method dùng `AuthorizationManagerBeforeReactiveMethodInterceptor` để đánh giá expression và đưa ra quyết định.

~~~text
Caller (Controller / service khác)
    |
    v
Spring AOP proxy của ReportService
    |
    v
@PreAuthorize expression
    |
    +-- tìm Authentication từ Reactor Context
    +-- lấy method arguments (nếu expression cần)
    +-- đánh giá hasRole / hasAuthority / bean policy
    |
    +-- DENY --> AccessDeniedException (Mono/Flux error)
    |               Method body/điều khiển nghiệp vụ không chạy
    |
    +-- GRANT --> gọi method đích và tiếp tục Publisher
                    |
                    v
                 DB/API/logic nghiệp vụ
~~~

Sơ đồ giải thích điều cần đạt. Ở môi trường reactive, cần **subscribe vào publisher** để tín hiệu và kiểm tra authorization diễn ra. Đừng gọi `block()` trong service WebFlux hoặc `subscribe()` thủ công để tự thoát khỏi vòng đời security.

### 3.2. Reactor Context chứ không phải ThreadLocal

Spring Security reactive truy cập context thông qua `ReactiveSecurityContextHolder` và Reactor `Context`. Điều này quan trọng khi pipeline chuyển scheduler/thread; một `ThreadLocal` kiểu Servlet không bảo đảm mang Authentication qua các operator reactive.

Ví dụ thuần Reactor — **mảnh code trong method Java** có Authentication đã tạo hợp lệ:

~~~java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(securityContext -> securityContext.getAuthentication())
        .map(authentication -> authentication.getName());

Mono<String> withUser = currentUser.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication));
~~~

Biến `authentication` ở đây là một `Authentication` đã được server xác thực; đoạn này không phải cách chuyển dữ liệu từ header chưa kiểm chứng thành logged-in user. Trong WebFlux request được filter bảo mật xử lý, context thường do framework thiết lập tự động.

**Nếu không có security context**, expression `hasRole('ADMIN')` không tự cho phép. Trong một số cách test gọi method trực tiếp, `AccessDeniedException` đi ra dưới dạng reactive error thay vì tự biến thành HTTP status.

## 4. Viết biểu thức @PreAuthorize

`@PreAuthorize` nhận một biểu thức SpEL, kết quả là quyết định có cho phép method được gọi hay không.

| Biểu thức | Ý nghĩa | Điều cần nhớ |
|---|---|---|
| `@PreAuthorize("hasRole('ADMIN')")` | Cần `ROLE_ADMIN` theo prefix mặc định. | `hasRole` thêm `ROLE_`; không viết `hasRole('ROLE_ADMIN')` theo thói quen. |
| `@PreAuthorize("hasAnyRole('USER','ADMIN')")` | Có ít nhất một role được chỉ định. | Roles vẫn được ánh xạ thành authorities có prefix. |
| `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` | Cần đúng authority `SCOPE_reports.read`. | Hữu ích với scope từ OAuth2/JWT khi converter cấp authority đó. |
| `@PreAuthorize("isAuthenticated()")` | Cần Authentication hợp lệ theo policy. | Không đồng nghĩa được thực hiện mọi nghiệp vụ. |
| `@PreAuthorize("#p0 == authentication.name")` | Tham số method đầu tiên phải bằng tên principal. | Chỉ là ví dụ ownership đơn giản; cần xác minh owner thật từ database. |
| `@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")` | Chủ sở hữu hoặc admin. | `#p0` tránh phụ thuộc tên tham số đã được giữ ở bytecode. |
| `@PreAuthorize("@documentAcl.canRead(#p0, authentication)")` | Gọi bean policy `documentAcl`. | Dùng cho quyết định phức tạp, có thể trả `Mono<Boolean>` với cấu hình AuthorizationManager. |
| `@PreAuthorize("denyAll()")` | Luôn từ chối. | Có ích khi đóng tạm chức năng nhưng cần kiểm tra method security thật sự bật. |

### 4.1. hasRole và hasAuthority

Khi dùng:

~~~java
User.withUsername("reader")
    .password("{noop}demo-pass")
    .roles("USER")
    .build();
~~~

`roles("USER")` tạo `ROLE_USER`; expression `hasRole('USER')` kiểm tra đúng authority này. Trong khi đó `hasAuthority('USER')` sẽ tìm authority **tên chính xác** là `USER` và không mặc nhiên tương đương `ROLE_USER`. Vì vậy nếu API cấp scope `SCOPE_reports.read`, dùng `hasAuthority('SCOPE_reports.read')` hoặc converter/mapping phù hợp.

Cả role và authority chỉ đáng tin khi có nguồn Authentication đã được xác minh (ví dụ security manager hoặc token validator); không tạo role từ query/header do người dùng chọn.

### 4.2. Đọc method arguments trong SpEL

Với method:

~~~java
@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
public Mono<String> readForOwner(String owner) {
    return Mono.just("owner=" + owner);
}
~~~

Biểu thức so sánh **tham số thứ nhất** với `Authentication.getName()`, hoặc cho ADMIN vượt qua. Dùng `#p0` (hoặc `#a0`) khi muốn tránh phụ thuộc metadata tên tham số. Nếu dùng `#owner`, cần đảm bảo tên tham số được giữ cho Spring SpEL thông qua compiler metadata (thường là flag `-parameters` hoặc annotation hỗ trợ).

**Lỗ hổng cần tránh:** Nếu `owner` đến từ URL do client tự nhập, so sánh nó với username chỉ chứng minh **client khai đúng tên mình**; không chứng minh record được truy cập thực sự do user đó sở hữu. Trong nghiệp vụ thật cần kiểm tra quyền dựa trên **ID/owner trong database đáng tin**, quan hệ tenant, scope và trạng thái tài nguyên.

### 4.3. Gọi bean authorization — có thể asynchronous

Một policy theo bản ghi thường cần tra database. Theo tài liệu Spring Security 6.x với `AuthorizationManager`, expression có thể gọi bean trả `Boolean` **hoặc** `Mono<Boolean>`:

~~~java
@PreAuthorize("@documentAcl.canRead(#p0, authentication)")
public Mono<Document> readDocument(Long documentId) {
    return repository.findById(documentId);
}
~~~

Mảnh này là method minh họa; `Document` và `repository` là domain của ứng dụng. Một bean policy có thể có chữ ký:

~~~java
@Component("documentAcl")
public class DocumentAcl {

    private final DocumentRepository repository;

    public DocumentAcl(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(
        Long id, Authentication authentication) {

        return repository.findById(id)
            .map(doc ->
                authentication != null &&
                (doc.ownerUsername().equals(authentication.getName())
                 || authentication.getAuthorities().stream()
                       .anyMatch(a ->
                           a.getAuthority().equals("ROLE_ADMIN"))))
            .defaultIfEmpty(false);
    }
}
~~~

**Đây là class minh họa chưa biên dịch độc lập** vì `Document`, `DocumentRepository` và mapping ownership thuộc dự án thực tế. Import thêm `org.springframework.stereotype.Component`, `org.springframework.security.core.Authentication` và `reactor.core.publisher.Mono`. `defaultIfEmpty(false)` bảo đảm không có record thì quyết định **deny** thay vì để publisher rỗng có thể được hiểu như abstain. Thực tế nên định nghĩa policy “không thấy bản ghi” có status 404 hay 403 sao cho không lộ sự tồn tại tài nguyên.

Phần authorization bean phải tránh thao tác blocking trên event loop; dùng repository reactive hoặc cách offload có giới hạn. Không gọi `block()` trong biểu thức SpEL để truy vấn quyền.

## 5. Trước khi thực thi nghiệp vụ: bảo vệ side effect

Đề bài đặt trọng tâm vào **kiểm tra quyền trước khi thực thi nghiệp vụ**, đặc biệt nguy hiểm nếu method thực hiện ghi tiền, phát hành báo cáo, thay trạng thái đơn hàng hay gửi thông báo.

Ví dụ **không nên làm**:

~~~java
// Phần thân method minh họa: tác vụ chạy ngay khi method được gọi.
// Có thể làm khó việc kiểm soát vòng đời reactive và kiểm thử.
public Mono<Void> publishReport(Long id) {
    auditClient.sendImmediately(id); // side effect eager đồng bộ!
    return reportRepository.publish(id);
}
~~~

Ngay cả khi Spring AOP có thể chặn method đích trước khi được gọi, **side effect eager** ở các publisher chưa được bảo vệ khác hoặc khi gọi bỏ qua proxy làm hệ thống khó kiểm soát hơn. Reactive side effect nên nằm trong publisher để được quản lý theo subscription, error và cancellation.

Cách viết phù hợp với reactive:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> publishReport(Long id) {
    return Mono.defer(() ->
        reportRepository.publish(id));
}
~~~

Đây là **mảnh service method**; `reportRepository` là dependency reactive của ứng dụng. Khi caller đi qua proxy và authorization bị từ chối, pipeline không gọi phần nghiệp vụ của method. Với user được phép, công việc được thực hiện khi publisher được subscribe. `Mono.defer` giúp tránh tạo side effect trước subscription và tạo ra một lượt thực thi rõ ràng cho từng subscription.

**Đừng nhầm trước khi method chạy với bảo đảm giao dịch.** Sau khi authorization cho phép, dữ liệu/quyền vẫn có thể thay đổi (TOCTOU: time-of-check/time-of-use). Với thao tác nhạy cảm, cần ràng buộc tenant/owner ngay trong truy vấn cập nhật hoặc transaction, dùng optimistic locking/constraint phù hợp. Method security là một lớp; không thay thế kiểm tra nhất quán trong database.

### 5.1. Tại sao gọi subscribe() để “vượt lỗi” là sai?

~~~java
// SAI trong controller/service WebFlux:
protectedService.publishReport(id).subscribe();
return Mono.empty();
~~~

Đây là mảnh code sai để nhận diện lỗi. `subscribe()` tự tạo subscription riêng, làm lỗi, cancellation và Reactor Context khó điều phối; có thể mất authentication context hoặc trả HTTP success trước khi công việc thất bại. Cách đúng thường là:

~~~java
// Trả publisher và để framework subscribe.
return protectedService.publishReport(id);
~~~

Với `Mono`, không gọi `block()` trên Netty event loop. Ở unit test mới dùng `StepVerifier` để chủ động subscribe và kiểm tra tín hiệu.

## 6. HTTP authorization và method authorization: thứ tự và status

Cấu hình HTTP thường đặt luật URL rõ ràng:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public").permitAll()
    .anyExchange().authenticated());
~~~

Nếu request chưa có credentials truy cập endpoint bảo vệ, HTTP layer thường phản hồi **401** khi bật HTTP Basic. Nếu request đã authenticated nhưng thiếu quyền do `@PreAuthorize`, service phát `AccessDeniedException`, security exception handling của WebFlux thường chuyển nó thành **403 Forbidden**.

| Request | HTTP layer | Method layer | HTTP thường gặp |
|---|---|---|---|
| Không Basic tới protected `/api/docs/secret` | `authenticated()` từ chối | Có thể chưa gọi | **401** (Basic challenge) |
| Basic `reader` đúng tới protected secret | Cho qua vì authenticated | `hasRole('ADMIN')` từ chối | **403** |
| Basic `admin` đúng tới protected secret | Cho qua | Method cho phép | **200** |
| Basic `reader` đúng tới owner record của `reader` | Cho qua | Owner expression cho phép | **200** |
| Basic `reader` đúng tới owner record của `alice` | Cho qua | Owner expression từ chối | **403** |
| Basic `admin` đúng tới owner record bất kỳ | Cho qua | Admin override cho phép | **200** |

HTTP status ở bảng là kỳ vọng với config demo dưới đây. **`AccessDeniedException` không phải một HTTP response tự thân**: khi gọi service trực tiếp trong test hoặc background job, nó là tín hiệu lỗi reactive và không có status 401/403 nếu không có HTTP adapter. Với custom exception handlers/filter chain khác, mapping status có thể thay đổi.

Đừng để controller bắt `AccessDeniedException` rồi trả mặc định 200 hay log chứa dữ liệu bảo mật. Để security infrastructure chuyển lỗi theo chính sách, hoặc tùy biến denial handling minh thị và test kỹ.

## 7. Ví dụ Java 17+ chạy độc lập: bảo vệ ReportService bằng @PreAuthorize

Dự án dùng **Java 17**, **Spring Boot 3.5.16** và các thư viện WebFlux/Spring Security 6.5 do Boot quản lý. Spring Boot 3.5.16 đã phát hành nhưng là bản cuối của dòng 3.5 OSS; dự án production nên dùng dòng còn hỗ trợ/bản vá phù hợp. Trong bài thực hành, version được cố định để sinh viên có thể dựng ví dụ thống nhất.

Tính năng:

- User `reader:demo-pass` có `ROLE_USER`.
- User `admin:admin-pass` có `ROLE_ADMIN`.
- Endpoint `GET /api/docs/secret` cần login ở HTTP và cần role ADMIN ở service.
- Endpoint `GET /api/docs/owner/{owner}` cần login ở HTTP; method chỉ cho phép `owner == Authentication.name` hoặc ADMIN.
- `DocumentService.secretReadCount()` là bộ đếm **chỉ phục vụ test**, dùng chứng minh lời gọi bị từ chối không đọc dữ liệu nghiệp vụ. Bộ đếm tăng **bên trong `Mono.defer(...)`**, không tăng khi bị deny.
- Endpoint `/api/public` là public nhưng không chứa dữ liệu bí mật.

### 7.1. Cấu trúc thư mục

~~~text
reactive-preauthorize-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/ReactivePreAuthorizeDemo.java
    └── test/java/example/DocumentServiceSecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-preauthorize-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17+ và Gradle/Gradle Wrapper phiên bản tương thích Spring Boot. Dùng wrapper nếu dự án có sẵn để build nhất quán. Mục 7.2 có tất cả class chính trong **một file**; mục 8 có test class riêng.

### 7.2. Ứng dụng đầy đủ

Tệp `src/main/java/example/ReactivePreAuthorizeDemo.java`:

~~~java
package example;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactivePreAuthorizeDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactivePreAuthorizeDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Chỉ cho localhost: {noop} và password hardcoded không an toàn.
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Service
    public static class DocumentService {

        private final AtomicInteger secretReads = new AtomicInteger();

        // Tầng HTTP chỉ yêu cầu authenticated;
        // tầng service yêu cầu ROLE_ADMIN.
        @PreAuthorize("hasRole('ADMIN')")
        public Mono<Map<String, Object>> readSecret() {
            return Mono.defer(() -> {
                int count = secretReads.incrementAndGet();
                return Mono.just(Map.of(
                    "classification", "ADMIN_ONLY",
                    "readCount", count));
            });
        }

        // #p0 là tham số thứ nhất, không phụ thuộc tên trong bytecode.
        @PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
        public Mono<Map<String, String>> readOwned(String owner) {
            return Mono.defer(() -> Mono.just(Map.of(
                "owner", owner,
                "content", "demo-only")));
        }

        // Method này chỉ để test, không có business side effect.
        public int secretReadCount() {
            return secretReads.get();
        }
    }

    @RestController
    static class DocumentController {

        private final DocumentService service;

        DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/docs/secret")
        Mono<Map<String, Object>> secret() {
            return service.readSecret();
        }

        @GetMapping("/api/docs/owner/{owner}")
        Mono<Map<String, String>> owned(@PathVariable String owner) {
            return service.readOwned(owner);
        }
    }
}
~~~

**Giải thích về thứ tự và cấu trúc:**

1. `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` kích hoạt interceptor reactive. Nếu bỏ dòng này, service annotation có thể chỉ còn là metadata và mất bảo vệ.
2. `DocumentService` là Spring bean `@Service`, controller nhận qua constructor injection. Đây là lời gọi qua bean proxy, không phải `this.readSecret()` nội bộ trong cùng class.
3. HTTP `anyExchange().authenticated()` cho reader/admin qua nếu có Basic credential hợp lệ. Rule riêng trên service quyết định ai được đọc báo cáo bí mật.
4. `.roles("ADMIN")` tạo authority `ROLE_ADMIN`, phù hợp `hasRole('ADMIN')`.
5. `readSecret()` tạo Mono bằng `defer`; `secretReads.incrementAndGet()` chỉ xảy ra nếu publisher business được subscribe sau khi authorization cho phép.
6. `readOwned(String owner)` minh họa SpEL theo argument + identity. **Không dùng mô hình path-owner này làm ACL production:** bản ghi thật phải được liên kết owner/tenant từ database, không chỉ từ tham số do client kiểm soát.
7. Controller không tự kiểm tra `Authentication`, cũng không tự `subscribe()`; nó trả publisher để WebFlux và security filters điều phối.
8. Các API đều là **GET** để bài thực hành tập trung vào method authorization, không gây nhầm với CSRF đối với POST. Khi thêm write endpoint, vẫn phải xử lý CSRF/session/token theo threat model.

### 7.3. Chạy thử qua HTTP

Trong thư mục `reactive-preauthorize-demo`, với JDK 17 và Gradle tương thích:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Ở terminal khác:

~~~bash
# 1. Không credential -> HTTP layer yêu cầu login.
curl -i http://localhost:8080/api/docs/secret

# 2. Đúng password nhưng không đủ role ADMIN.
curl -i -u reader:demo-pass http://localhost:8080/api/docs/secret

# 3. ADMIN được phép đọc.
curl -i -u admin:admin-pass http://localhost:8080/api/docs/secret

# 4. Reader đọc dữ liệu gắn với tên mình.
curl -i -u reader:demo-pass http://localhost:8080/api/docs/owner/reader

# 5. Reader thử tên người khác.
curl -i -u reader:demo-pass http://localhost:8080/api/docs/owner/alice

# 6. ADMIN được truy cập owner bất kỳ trong demo.
curl -i -u admin:admin-pass http://localhost:8080/api/docs/owner/alice

# 7. Endpoint public.
curl -i http://localhost:8080/api/public
~~~

Với PowerShell, nếu `curl` là alias không mong muốn, dùng `curl.exe`. `-i` hiển thị HTTP status/header; `-u` gửi Basic credentials. Chỉ sử dụng password giả ở localhost, không đặt secret thật trong lệnh shell trên máy dùng chung.

| Request | Status kỳ vọng | Giải thích |
|---|---|---|
| Không Basic tới `/api/docs/secret` | **401** | HTTP security `authenticated()` đòi login, Basic challenge. |
| Reader tới `/api/docs/secret` | **403** | HTTP qua, method `@PreAuthorize("hasRole('ADMIN')")` từ chối. |
| Admin tới `/api/docs/secret` | **200** | JSON có `classification=ADMIN_ONLY`, `readCount` tăng. |
| Reader tới `/api/docs/owner/reader` | **200** | `#p0 == authentication.name` cho phép. |
| Reader tới `/api/docs/owner/alice` | **403** | Không phải owner, cũng không phải ADMIN. |
| Admin tới `/api/docs/owner/alice` | **200** | Vế `hasRole('ADMIN')` cho phép. |
| Anonymous tới `/api/public` | **200** | Endpoint không yêu cầu login ở HTTP; không gọi service bảo vệ. |

Đây là **HTTP response** chứ không phải stdout Java. Ví dụ body thành công có thể là `{"classification":"ADMIN_ONLY","readCount":1}` cho lượt admin đầu tiên; số đếm và thứ tự key JSON không cố định giữa các lần chạy hoặc nhiều request. Test nên so sánh status và field có nghĩa, không so sánh nguyên raw response.

### 7.4. Tác dụng “trước nghiệp vụ” được kiểm tra bằng cách nào?

Từ HTTP, ta thấy reader nhận 403. Nhưng chỉ status 403 chưa đủ chứng minh một side effect không xảy ra, vì controller có thể ghi dữ liệu trước khi exception. Mục 8 test trực tiếp method và so sánh `secretReadCount()` **trước và sau** denied call để chứng minh publisher nghiệp vụ không chạy. Production cần kết hợp test với DB transaction, audit side effect hoặc mock dependency thích hợp.

## 8. Kiểm thử @PreAuthorize trực tiếp bằng StepVerifier

Dự án đã khai báo `spring-security-test` và `reactor-test`. Tại tầng method, `@WithMockUser` giúp tạo Authentication của test mà không cần gọi HTTP Basic. `StepVerifier` subscribe vào Mono để kiểm tra success/error.

Tệp `src/test/java/example/DocumentServiceSecurityTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    ReactivePreAuthorizeDemo.DocumentService service;

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerDeniedBeforeSecretRead() {
        int before = service.secretReadCount();

        StepVerifier.create(service.readSecret())
            .expectError(AccessDeniedException.class)
            .verify();

        // Side effect trong Mono.defer không được thực thi.
        assertEquals(before, service.secretReadCount());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadSecret() {
        int before = service.secretReadCount();

        StepVerifier.create(service.readSecret())
            .expectNextMatches(record ->
                "ADMIN_ONLY".equals(record.get("classification")))
            .verifyComplete();

        assertEquals(before + 1, service.secretReadCount());
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerCanReadOwnRecord() {
        StepVerifier.create(service.readOwned("reader"))
            .expectNextMatches(record ->
                "reader".equals(record.get("owner")))
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerCannotReadOtherOwner() {
        StepVerifier.create(service.readOwned("alice"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadOtherOwner() {
        StepVerifier.create(service.readOwned("alice"))
            .expectNextMatches(record ->
                "alice".equals(record.get("owner")))
            .verifyComplete();
    }

    @Test
    void anonymousCannotReadSecret() {
        StepVerifier.create(service.readSecret())
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Nếu đã có wrapper: `./gradlew test` hoặc `gradlew.bat test`. Các test được viết cho cấu hình minh họa; chúng cần được chạy thực tế trên môi trường build để xác nhận dependency và kết quả. Với setup hợp lệ, mong đợi sáu test pass. Test không có `@WithMockUser` xác minh method bị từ chối khi không có Authentication phù hợp.

**Vì sao @WithMockUser có tác dụng trong reactive test?** Spring Security Test thiết lập context phù hợp cho method security; `StepVerifier` subscribe vào publisher được proxy trả về. Đây không phải việc tự tạo ThreadLocal rồi mong nó tự truyền qua mọi reactive scheduler. Tài liệu Spring Security có ví dụ `@WithMockUser` + `StepVerifier.expectError(AccessDeniedException.class)` cho reactive method.

### 8.1. Nên có thêm HTTP integration test

Method test kiểm tra rule và trước-nghiệp-vụ; HTTP test kiểm tra đường đi của WebFilter và mapping lỗi ra 401/403. Với `WebTestClient`, tối thiểu nên có:

- `GET /api/docs/secret` không Basic → 401 và `WWW-Authenticate` theo Basic config.
- Reader có Basic hợp lệ → 403.
- Admin có Basic hợp lệ → 200, response JSON chỉ chứa field được phép.
- Reader tự đọc `owner/reader` → 200; đọc `owner/alice` → 403.
- Endpoint public → 200.
- Khi thêm endpoint ghi dữ liệu, test CSRF và role/method policy riêng.

Có thể dùng `WebTestClient` bind vào `ApplicationContext` và `SecurityMockServerConfigurers.springSecurity()`, hoặc dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client thực để kiểm chứng security chain.

### 8.2. Kiểm thử bền trước thay đổi quyền

Đừng chỉ test user có `ROLE_ADMIN`. Với policy theo owner/tenant, test ít nhất:

1. User thuộc cùng tenant + được phép → thành công.
2. User khác tenant nhưng biết ID hợp lệ → từ chối.
3. ID không tồn tại → từ chối/404 đúng policy, không lộ thông tin.
4. User chuyển role hoặc bị disabled → kiểm tra theo cơ chế refresh/revocation thực tế.
5. Concurrent update/thay đổi ownership → kiểm tra ở database/transaction chứ không chỉ annotation.

## 9. Những chỗ @PreAuthorize dễ bị bỏ qua

### 9.1. Self-invocation trong cùng bean

~~~java
@Service
public class ReportService {

    public Mono<String> outerCall() {
        return innerProtected(); // Gọi nội bộ, có thể bỏ qua proxy.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> innerProtected() {
        return Mono.just("secret");
    }
}
~~~

Đây là **ví dụ lỗi thiết kế**, không phải class cần đưa nguyên vào demo. Spring AOP proxy thường chỉ can thiệp khi một caller gọi **qua proxy**. `this.innerProtected()` hoặc gọi nội bộ từ `outerCall()` không đi qua proxy, có thể **không kích hoạt** check. Sửa bằng cách tách method được bảo vệ sang một Spring bean riêng rồi inject bean đó, hoặc thay kiến trúc để tránh self-invocation.

### 9.2. Tạo service bằng new

~~~java
// SAI khi mong Spring AOP method security hoạt động:
ReportService raw = new ReportService();
raw.innerProtected();
~~~

Tạo object trực tiếp bỏ qua Spring container/proxy; `@PreAuthorize` không tự “chạy” chỉ vì annotation tồn tại trong bytecode. Các method `private`, `final` hoặc class không thể proxy theo cơ chế AOP cũng cần đặc biệt thận trọng. Sử dụng Spring bean và public method phù hợp.

### 9.3. Annotation trên controller nhưng service không được bảo vệ

Đặt `@PreAuthorize` chỉ ở controller có thể bảo vệ route ấy, nhưng không bảo vệ các caller khác của service. Khi rule gắn với nghiệp vụ, nên đặt ở service boundary (và vẫn có HTTP authorization). Tránh copy cùng một expression ở nhiều controller khiến rules không đồng bộ.

### 9.4. Trả String/void trong reactive method bảo vệ

Tài liệu Spring Security nhấn mạnh reactive method security cần method trả `org.reactivestreams.Publisher` như `Mono`/`Flux` để tích hợp Reactor Context (hoặc cơ chế coroutine được hỗ trợ). Đừng copy demo Java Servlet với method blocking trả `String` rồi mong nó có cùng behavior trong reactive method security.

### 9.5. Dùng ThreadLocal để lấy principal

`SecurityContextHolder.getContext()` theo mô hình ThreadLocal có thể không chứa Authentication đúng khi reactive pipeline chuyển thread. Dùng `ReactiveSecurityContextHolder.getContext()`, injection principal từ framework hoặc SpEL `authentication` trong interceptor reactive.

### 9.6. Bỏ annotation enable

Không có `@EnableReactiveMethodSecurity`, các annotation trên service có thể không được enforce. Đây là lý do **test reader-denied** rất quan trọng: nếu bật cấu hình sai, test sẽ thất bại thay vì giữ lỗ hổng im lặng.

### 9.7. Đọc authorization từ body/header tự khai

Ví dụ `@PreAuthorize("#role == 'ADMIN'")`, nơi `role` là tham số request do client gửi, là lỗi nghiêm trọng. Policy phải dựa vào `Authentication` đã xác minh và dữ liệu server có thẩm quyền. Dữ liệu client dùng làm **định danh tài nguyên để truy vấn** hoặc đề xuất hành động, không làm nguồn chân lý về quyền.

### 9.8. Sai scope/role prefix

`hasRole('ADMIN')` kiểm tra `ROLE_ADMIN` theo prefix mặc định. `hasAuthority('SCOPE_admin')` kiểm tra exact string. Nếu JWT converter cung cấp `SCOPE_reports.read` mà expression kiểm tra `ROLE_ADMIN`, kết quả deny là hợp lý; phải thiết kế mapping theo chính sách, không ép cho qua bằng `permitAll`.

### 9.9. Dùng @PostAuthorize thay @PreAuthorize cho tác vụ ghi

`@PostAuthorize` kiểm tra **sau khi method được thực thi**/khi giá trị được trả về theo pipeline. Nếu method đã thực hiện side effect, từ chối trả kết quả không nhất thiết hoàn tác thay đổi trong database hoặc external API. Với thao tác có tác dụng phụ, ưu tiên check **trước** bằng `@PreAuthorize` và ràng buộc authorization tại transaction/repository, thay vì cho phép ghi rồi cố che response.

### 9.10. Chuyển AccessDeniedException thành Mono.empty()

~~~java
// Không làm điều này trong service nếu mục đích là bảo vệ dữ liệu:
return protectedService.readSecret()
    .onErrorResume(AccessDeniedException.class, ex -> Mono.empty());
~~~

Đoạn code chỉ minh họa. Nuốt lỗi authorization có thể khiến caller hiểu rằng không có bản ghi thay vì bị cấm; ở một số luồng có thể vô tình trả success status. Xử lý lỗi theo policy rõ ràng ở boundary, không “im lặng cho qua”.

## 10. Một số điểm nâng cao đáng nhớ

### 10.1. @PreAuthorize với Mono<Boolean> từ authorization bean

Khi việc kiểm tra quyền phải tra DB không blocking, một bean có thể trả `Mono<Boolean>`. Với `@EnableReactiveMethodSecurity(useAuthorizationManager=true)`, tài liệu Spring Security 6.5 có ví dụ bean function reactive trong expression. Tuy nhiên cần đảm bảo:

- Bean policy đúng Spring bean name trong SpEL.
- Dữ liệu quyền đến từ nguồn trusted, không chỉ từ request.
- `Mono.empty()` có ngữ nghĩa khác `Mono.just(false)` ở một số quy tắc authorization; nên **fail closed** bằng `defaultIfEmpty(false)` khi không có tài nguyên.
- Truy vấn DB đúng reactive, có timeout và logging an toàn; không gọi `block()`.
- Quyền thay đổi trong khi xử lý: cân nhắc database constraint hoặc optimistic locking.

### 10.2. Annotation ở interface và method

Spring hỗ trợ đọc method security annotation trên method, class hoặc interface trong các tình huống phù hợp với Spring AOP. Với nhiều interface/annotation có rule xung đột, Spring Security 6.x có cơ chế phát hiện cấu hình mơ hồ. Quy tắc tốt là đặt policy nhất quán tại service contract hoặc implementation và test khi có kế thừa/override, không copy nhiều expression mâu thuẫn.

### 10.3. @PreAuthorize trên các sự kiện không có HTTP

Một message consumer hoặc scheduled task không tự có security context của request; nếu gọi service protected, phải có cơ chế gán Authentication **được hệ thống tin cậy** cho subscriber, hoặc tách xử lý system-task theo policy service account rõ ràng. Không bỏ annotation chỉ vì background task bị deny. Đặc biệt không tạo `ROLE_ADMIN` từ header message hoặc metadata do bên ngoài chưa xác minh.

### 10.4. Cache, session và JWT thay đổi quyền

Method security đọc Authentication/authorities đang ở security context. Nếu admin vừa thu hồi role nhưng token JWT hoặc session cũ vẫn mang role, rule có thể tiếp tục cho phép tới khi token/phiên được revalidate/revoke. Với quyền nhạy cảm cần xác định TTL, session invalidation, token introspection hoặc lookup authoritative theo từng thao tác.

### 10.5. Kết hợp với tenant isolation

`hasRole('ADMIN')` không mặc nhiên có nghĩa admin được đọc mọi tenant. Một policy đúng có thể là “tenant trùng + role phù hợp”, dựa trên **tenant của record trong DB** và tenant đã được ràng buộc với Authentication. Tránh bypass toàn hệ thống chỉ vì có role ADMIN trong một tenant.

## 11. Checklist code review và kiểm thử

Trước khi chấp nhận một method `@PreAuthorize`, hãy kiểm tra:

1. **Enable:** Ứng dụng đã bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`?
2. **Proxy:** Method có nằm trên Spring bean và được caller gọi qua bean proxy, không self-invocation?
3. **Return type:** Method có trả `Mono`/`Flux` tương thích reactive security?
4. **Authentication:** Identity/authorities lấy từ Reactor SecurityContext đúng subscription, không từ raw client header?
5. **SpEL:** Expression đúng syntax, role prefix và tên tham số (`#p0`/metadata)?
6. **Policy:** Cần role, scope, ownership, tenant, trạng thái tài nguyên hay kết hợp?
7. **Source of truth:** Nếu theo tài nguyên, owner/tenant được xác minh từ DB, không lấy từ tham số tự khai?
8. **No side effects on deny:** Test denied call không thực thi DB write, external call hoặc publisher business?
9. **Reactive discipline:** Không `block()`/`subscribe()` thủ công trong filter/service/policy.
10. **Error semantics:** Direct service test thấy `AccessDeniedException`; HTTP test đúng 401/403 theo security chain.
11. **Method vs HTTP:** Có cả policy URL lẫn policy service? `permitAll` ở URL không bỏ method-level check?
12. **AOP pitfalls:** Không private/final/self-invoked method, không tự `new` object protected?
13. **Time-of-check:** Side effects nhạy cảm có transaction, optimistic lock hoặc enforcement ở DB?
14. **Role changes:** Session/token caches có TTL/revocation phù hợp nếu cần thu hồi quyền nhanh?
15. **Data leakage:** Error body không tiết lộ hồ sơ/tên tài nguyên nhạy cảm; không log credentials/token.
16. **Testing:** Có test anonymous, role thiếu, role đủ, owner đúng/sai, tenant khác, và trường hợp policy bean tra DB không có record?

## 12. Câu hỏi tự đánh giá

**1.** `@PreAuthorize("hasRole('ADMIN')")` khác `pathMatchers("/admin/**").hasRole("ADMIN")` ở đâu?

**Đáp án:** Annotation bảo vệ **method invocation** qua Spring AOP, dù caller đến từ controller hay service khác đi qua proxy. URL matcher bảo vệ các HTTP request khớp path trong chain. Nên dùng cả hai.

**2.** `hasRole('ADMIN')` tìm authority gì theo mặc định?

**Đáp án:** `ROLE_ADMIN`, khác với `hasAuthority('ADMIN')` vốn tìm exact string.

**3.** Vì sao method trả Mono/Flux quan trọng?

**Đáp án:** Reactive method security tích hợp với Reactor Context gắn theo subscriber để lấy Authentication. Publisher cũng giúp kiểm soát việc thực thi khi subscription, cancellation và reactive errors.

**4.** Reader có Basic hợp lệ nhưng gọi secret method đòi ADMIN. Client thường nhận gì?

**Đáp án:** `403 Forbidden` trong WebFlux HTTP chain thông thường; ở test gọi service trực tiếp, nhận reactive `AccessDeniedException`.

**5.** Nếu một controller dùng `this.protectedMethod()` trên cùng bean, annotation có chắc hoạt động không?

**Đáp án:** Không. Self-invocation có thể bypass Spring AOP proxy. Tách protected method sang Spring bean và gọi qua injected proxy.

**6.** Viết `@PreAuthorize("#p0 == authentication.name")` cho endpoint đọc record theo owner là đủ cho production chưa?

**Đáp án:** Chưa. Tham số client có thể tự khai. Cần đối chiếu owner thật của record trong database và tenant/role theo nguồn tin cậy.

**7.** Một method đã ghi database rồi mới dùng `@PostAuthorize` deny có hoàn tác ghi không?

**Đáp án:** Không tự động. `@PostAuthorize` từ chối trả kết quả không bảo đảm rollback side effect. Với nghiệp vụ ghi dùng pre-check + enforcement transaction/DB.

**8.** Tại sao kiểm thử denied call bằng bộ đếm trong `Mono.defer(...)` có ý nghĩa?

**Đáp án:** Nó chứng minh authorization đã ngăn publisher nghiệp vụ được thực thi; status 403 một mình không chứng minh không có side effect.

**9.** Có thể gọi bean trả `Mono<Boolean>` từ SpEL không?

**Đáp án:** Có trong cơ chế reactive AuthorizationManager được tài liệu Spring Security 6.5 hỗ trợ; policy cần xử lý dữ liệu không tồn tại theo kiểu deny và không blocking.

**10.** Một JWT còn mang role ADMIN cũ nhưng người dùng đã bị hạ quyền. `@PreAuthorize` có tự tra database để biết ngay không?

**Đáp án:** Không mặc định. Expression đọc Authentication hiện hành; cần chiến lược revoke/revalidate hoặc policy authoritative theo nghiệp vụ.

## Tài liệu chính thức

- Spring Security 6.5 — Enable Reactive Method Security (`@EnableReactiveMethodSecurity`, `@PreAuthorize`, `Mono<Boolean>`): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Testing Reactive Method Security (`@WithMockUser` + `StepVerifier`): https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html
- Spring Security 6.5 — Testing Reactive Authentication with WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — PreAuthorize annotation: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.5.16 release note / end of 3.5 OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
