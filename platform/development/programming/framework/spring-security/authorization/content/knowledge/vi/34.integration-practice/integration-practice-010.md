# Triển khai cùng chính sách trong WebFlux và kiểm chứng Reactor Context

> **Chủ đề:** Spring Security — authorization, nhóm **Thực hành tích hợp**. Mục tiêu là dùng **một chính sách phân quyền** cho cả tầng HTTP của Spring WebFlux và tầng service được bảo vệ bằng reactive method security, đồng thời kiểm chứng rằng `Authentication` đi theo **Reactor Context của từng subscriber**, kể cả khi luồng đổi scheduler. Bài thực hành dùng Java 17, Spring Boot 3.x, Spring Security 6.x, Project Reactor, WebTestClient, StepVerifier.

## 1. Đầu ra mong đợi

Sau bài này, bạn có thể:

1. Phân biệt authentication ở `SecurityWebFilterChain`, authorization theo URL, và `@PreAuthorize` trên phương thức trả về `Mono`/`Flux`.
2. Triển khai **một nguồn luật duy nhất**: một user cần authority `report:read` **và** phải sở hữu báo cáo, trừ trường hợp được cấp `report:read:any`.
3. Tái sử dụng `ReportPolicy.canRead(authentication, id)` ở cả HTTP authorization và method authorization, tránh hai rule drift với nhau.
4. Đọc `ReactiveSecurityContextHolder.getContext()` trong một reactive chain, không đọc `SecurityContextHolder` ThreadLocal của ứng dụng Servlet để tìm principal.
5. Test cả request HTTP bằng `WebTestClient` và gọi service trực tiếp bằng `StepVerifier`, bao gồm anonymous, thiếu quyền, sai owner, đổi scheduler và hai subscriber đồng thời.
6. Chẩn đoán lỗi mất Reactor Context do `subscribe()` thủ công, `block()`/ThreadLocal, callback ngoài Reactor, self-invocation hoặc test chỉ đi qua controller.

**Contract thử nghiệm:** báo cáo 101 thuộc user `an`; báo cáo 102 thuộc user `binh`. `an` chỉ có `report:read` được xem 101 nhưng không xem 102. `reviewer` có `report:read` và `report:read:any` được xem 102. User chỉ có `report:write` bị từ chối cả hai.

## 2. Bức tranh tổng thể về authorization trong WebFlux

Ở ứng dụng Spring WebFlux, chuỗi request đi qua reactive security filters. Sau khi xác thực, Spring Security có thể lưu `SecurityContext` của request vào **Reactor Context** để những operator phía sau, bao gồm reactive method security, nhìn thấy authentication của subscriber hiện hành.

~~~text
Request HTTP GET /api/reports/101
  |
  v
SecurityWebFilterChain
  |-- Authentication (user an)
  |-- ReactiveAuthorizationManager cho URL + reportId
  |          \-- ReportPolicy.canRead(an, 101)
  |
  v
ReportController.view(101) -> Mono<ReportView>
  |
  v
ReportService.read(101)
  |-- @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
  |          \-- CÙNG ReportPolicy.canRead(an, 101)
  |-- repository lookup
  |-- publishOn(...)
  |-- ReactiveSecurityContextHolder.getContext()
  |
  v
HTTP 200 + dữ liệu; hoặc 401/403 nếu không được phép
~~~

Điều cần nhớ:

- **Authentication**: “ai đang gửi request?”, ví dụ `Authentication.getName() == "an"`.
- **Function authorization**: “có `report:read` không?”.
- **Object authorization**: “có được đọc đúng báo cáo `reportId` này không?”.
- **Reactor Context**: dữ liệu theo **subscription**, không phải biến toàn cục hay ThreadLocal gắn cứng với một thread.
- **Reactive method security**: `@EnableReactiveMethodSecurity` kích hoạt `@PreAuthorize` cho Spring-managed beans có kiểu trả về reactive thích hợp; check thường xảy ra trong luồng subscribe.
- **Defense in depth**: kiểm ở HTTP để từ chối sớm và ở service để tránh endpoint mới hoặc caller nội bộ bỏ qua nghiệp vụ.

Chính sách phải lấy principal từ Spring Security (đã được xác thực) và dữ liệu tài nguyên trên server. Không chấp nhận một biến `isAdmin` hay `owner` do client gửi như bằng chứng quyền.

## 3. Reactor Context khác gì ThreadLocal?

Một reactive pipeline có thể chạy trên nhiều thread, nhất là khi có `publishOn`, `subscribeOn`, I/O bất đồng bộ hoặc hợp nhất nhiều `Mono`. `SecurityContextHolder.getContext()` kiểu ThreadLocal trong Servlet không bảo đảm lấy được authentication của subscriber hiện tại ở WebFlux.

~~~java
// KHÔNG dùng như cách chuẩn để lấy principal trong chuỗi WebFlux:
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Cách sử dụng thích hợp:

~~~java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

Khi không chạy qua HTTP filters (ví dụ test service), tự đặt context **trên publisher được subscribe**:

~~~java
Mono<String> withUser = currentUsername.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));
~~~

`contextWrite(...)` áp dụng vào subscription; nó **không phải** lệnh thay đổi ThreadLocal toàn cục. Mỗi subscription có thể có một `Authentication` khác. Việc tạo `Mono` trước rồi thêm `contextWrite` lúc subscribe vẫn hoạt động nếu tất cả operator sử dụng Context đúng cách.

Một lỗi tinh vi là tạo `Mono` rồi gọi `subscribe()` trong method và trả một `Mono` khác: bạn đã tạo subscription rời rạc, làm mất quản lý lỗi, transaction hoặc security context, khiến test “trong một luồng” không còn đúng. Trong code server, hãy **return publisher**, để WebFlux subscriber điều khiển việc thực thi.

## 4. Khởi tạo project Spring Boot + WebFlux

Ví dụ dùng **Spring Boot 3.x / Spring Security 6.x** và Java 17. Không thêm đồng thời `spring-boot-starter-web` vào ứng dụng này: starter đó có thể làm Spring Boot chọn MVC thay vì WebFlux. Khi nâng Boot 4/Security 7, dùng BOM và migration notes đúng phiên bản rồi chạy lại toàn bộ test.

### 4.1. Dependencies

Trong một Maven project đã có Spring Boot parent/BOM, bổ sung:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Sơ đồ mã ví dụ:

~~~text
src/main/java/com/example/reactiveauth/
    ReactiveAuthApplication.java
    Report.java
    ReportView.java
    ReportRepository.java
    ReportPolicy.java
    ReportService.java
    ReportController.java
    WebFluxSecurityConfig.java
src/test/java/com/example/reactiveauth/
    ReportHttpSecurityTest.java
    ReportReactorContextTest.java
~~~

Mỗi file Java trong ví dụ có cùng `package com.example.reactiveauth`. Chọn Spring Boot 3.x hỗ trợ Java 17 và Spring Security 6.x qua BOM; không trộn ngẫu nhiên Spring Framework/Security phiên bản khác nhau.

### 4.2. Ứng dụng chính

File `src/main/java/com/example/reactiveauth/ReactiveAuthApplication.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
~~~

Lệnh chạy từ project dùng Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trong Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Kết quả lúc khởi động phụ thuộc version, port và môi trường; mặc định ứng dụng Boot WebFlux thường lắng nghe port 8080 nếu không thay `server.port`. Không dự đoán stdout framework cố định.

## 5. Một nguồn dữ liệu và một chính sách phân quyền duy nhất

### 5.1. Domain model

File `src/main/java/com/example/reactiveauth/Report.java`:

~~~java
package com.example.reactiveauth;

public record Report(long id, String owner, String title) {
}
~~~

File `src/main/java/com/example/reactiveauth/ReportView.java`:

~~~java
package com.example.reactiveauth;

public record ReportView(
        long id,
        String owner,
        String title,
        String seenBy) {
}
~~~

`seenBy` là một trường chỉ có trong **bài demo** để chứng minh principal thực sự đi qua Reactor Context sau khi `publishOn`; không bắt buộc đưa thông tin subscriber vào JSON production.

### 5.2. Repository giữ dữ liệu minh họa

File `src/main/java/com/example/reactiveauth/ReportRepository.java`:

~~~java
package com.example.reactiveauth;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class ReportRepository {

    private final Map<Long, Report> reports = Map.of(
            101L, new Report(101L, "an", "Bao cao cua An"),
            102L, new Report(102L, "binh", "Bao cao cua Binh")
    );

    public Optional<Report> findById(long id) {
        return Optional.ofNullable(reports.get(id));
    }
}
~~~

Repository in-memory trả `Optional` đồng bộ và không gây I/O; phù hợp để minh họa policy **không blocking**. Trong ứng dụng thật, **không đưa JDBC hoặc I/O blocking** vào expression `@PreAuthorize` trên event-loop WebFlux. Với R2DBC/remote PDP, thiết kế policy phản ứng bất đồng bộ bằng reactive authorization manager/service pipeline phù hợp; không gọi `block()` để ép kết quả.

### 5.3. Định nghĩa quyền dùng chung

File `src/main/java/com/example/reactiveauth/ReportPolicy.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {

    private final ReportRepository repository;

    public ReportPolicy(ReportRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long reportId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        boolean hasReadPermission = authentication.getAuthorities().stream()
                .anyMatch(a -> "report:read".equals(a.getAuthority()));

        if (!hasReadPermission) {
            return false;
        }

        return repository.findById(reportId)
                .map(report -> {
                    boolean owner = report.owner().equals(
                            authentication.getName());

                    boolean allowedAcrossOwners =
                            authentication.getAuthorities().stream()
                                    .anyMatch(a ->
                                            "report:read:any".equals(
                                                    a.getAuthority()));

                    return owner || allowedAcrossOwners;
                })
                .orElse(false);
    }
}
~~~

Policy trả `false` nếu chưa xác thực, thiếu `report:read` hoặc báo cáo không tồn tại. Có `report:read:any` **không thay** quyền cơ sở `report:read`. Chỉ khi có cả hai, reviewer mới được đọc cross-owner. Không suy ra authority từ biến role ở frontend.

Chính sách này không dựa vào Reactor API: đó là một hàm Java thuần nhận `Authentication` đã xác minh và ID. Ưu điểm là **cả HTTP reactive authorization manager và annotation trên reactive method dùng lại đúng một quyết định**. Vì repository ở memory, hàm `canRead` không blocking. Với database tenant, cần lọc/kiểm tra theo tenant/owner thật chứ không chỉ role chung.

## 6. Cấu hình WebFlux: HTTP cũng gọi cùng ReportPolicy

File `src/main/java/com/example/reactiveauth/WebFluxSecurityConfig.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http, ReportPolicy reportPolicy) {

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(
                                HttpMethod.GET, "/api/reports/{id}")
                        .access((authentication, context) -> {
                            long id;
                            try {
                                Object rawId =
                                        context.getVariables().get("id");
                                id = Long.parseLong(String.valueOf(rawId));
                            } catch (NumberFormatException error) {
                                return Mono.just(
                                        new AuthorizationDecision(false));
                            }

                            long reportId = id;
                            return authentication
                                    .map(auth -> new AuthorizationDecision(
                                            reportPolicy.canRead(
                                                    auth, reportId)))
                                    .defaultIfEmpty(
                                            new AuthorizationDecision(false));
                        })
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // DỮ LIỆU DEMO: mật khẩu {noop} tuyệt đối không dùng production.
        UserDetails an = User.withUsername("an")
                .password("{noop}demo-only")
                .authorities("report:read")
                .build();

        UserDetails binh = User.withUsername("binh")
                .password("{noop}demo-only")
                .authorities("report:read")
                .build();

        UserDetails reviewer = User.withUsername("reviewer")
                .password("{noop}demo-only")
                .authorities("report:read", "report:read:any")
                .build();

        return new MapReactiveUserDetailsService(
                an, binh, reviewer);
    }
}
~~~

Giải thích:

- `@EnableWebFluxSecurity` kích hoạt WebFlux security filters; `@EnableReactiveMethodSecurity` kích hoạt reactive method security. Chỉ thêm starter không có nghĩa method annotation tự bật.
- `pathMatchers(HttpMethod.GET, "/api/reports/{id}")` cho match đúng route; `AuthorizationContext.getVariables().get("id")` lấy path variable đã match, không tin body `owner` do client gửi.
- Không parse được ID: **DENY** thay vì thử giá trị mặc định nới quyền. Trình duyệt có thể nhận 403; ở hệ thống thật có thể để routing/input validation trả 400 nhưng vẫn không được trả dữ liệu.
- `authentication` ở callback `access` là `Mono<Authentication>`; `map` tạo `AuthorizationDecision` từ **cùng** `ReportPolicy` và `defaultIfEmpty(false)` chặn khi không có identity. Không gọi `block()`.
- `anyExchange().denyAll()` từ chối các API/method khác theo mặc định.
- `httpBasic` chỉ để demo kiểm thử trạng thái 401. Khi triển khai OAuth2 Resource Server/JWT hoặc session, thay bộ xác thực phù hợp **nhưng giữ nguyên luật ReportPolicy**.
- CSRF giữ mặc định; demo chỉ GET. Đối với POST/PUT/DELETE, cần quy tắc CSRF và authorization riêng, không tắt CSRF theo phản xạ.

**Về cùng chính sách:** hai điểm chặn HTTP và service cùng gọi `ReportPolicy.canRead`, không phải hai bản sao `owner.equals(...)` dễ drift. Trong production, tránh thực hiện truy vấn DB hai lần; có thể cấp quyền chức năng ở HTTP và quyền đối tượng ở service, hoặc dùng evaluator/caching phù hợp để áp dụng cùng policy logic mà không thừa I/O.

## 7. Service: method security và truy xuất principal sau publishOn

File `src/main/java/com/example/reactiveauth/ReportService.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
    public Mono<ReportView> read(long reportId) {
        return Mono.defer(() -> Mono.justOrEmpty(
                        repository.findById(reportId)))
                // Đổi scheduler để chứng minh subscriber context
                // đi theo reactive chain chứ không phụ thuộc thread.
                .publishOn(Schedulers.parallel())
                .flatMap(report ->
                        ReactiveSecurityContextHolder.getContext()
                                .map(SecurityContext::getAuthentication)
                                .map(authentication ->
                                        new ReportView(
                                                report.id(),
                                                report.owner(),
                                                report.title(),
                                                authentication.getName())))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Report not found")));
    }
}
~~~

Vì `ReportService` là Spring bean và method trả `Mono<ReportView>`, `@PreAuthorize` chạy theo cơ chế reactive khi subscribe. `#p0` là tham số thứ nhất (`reportId`), không phụ thuộc compiler có lưu tên tham số.

`ReactiveSecurityContextHolder.getContext()` được đọc **sau khi chuyển scheduler**. Nếu chạy thành công, trường `seenBy` vẫn đúng user. Đây là kiểm thử hữu ích chống phụ thuộc vào ThreadLocal. Trong WebFlux bình thường, security filter đặt context vào reactive subscription; khi test service không thông qua HTTP phải tự đặt `contextWrite`.

**Giới hạn demo:** `publishOn(Schedulers.parallel())` ở đây chỉ để minh họa Context, không phải lời khuyên luôn chuyển scheduler khi đọc memory. Không dùng `Schedulers.parallel()` để chạy JDBC blocking. Mẫu này sử dụng `Mono.defer` để tránh thực thi repository lookup trước subscription và `switchIfEmpty` khi báo cáo không tồn tại.

## 8. Controller WebFlux không tự quyết định quyền

File `src/main/java/com/example/reactiveauth/ReportController.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ReportView> view(@PathVariable long id) {
        return service.read(id);
    }
}
~~~

Controller chỉ trả publisher từ Spring service bean. Nó không gọi `subscribe()` và không dùng `block()`. Nếu thêm endpoint khác gọi cùng `service.read(id)`, method security vẫn bảo vệ nghiệp vụ. Test **service trực tiếp** ở mục 10 là bằng chứng rule không chỉ nằm ở HTTP filter.

### 8.1. Kiểm thử nhanh bằng HTTP Basic demo

Sau khi chạy ứng dụng:

~~~bash
curl -i http://localhost:8080/api/reports/101
curl -i -u an:demo-only http://localhost:8080/api/reports/101
curl -i -u an:demo-only http://localhost:8080/api/reports/102
curl -i -u reviewer:demo-only http://localhost:8080/api/reports/102
~~~

Kỳ vọng về status (HTTP headers/chi tiết error body phụ thuộc version):

| Request | HTTP | Vì sao |
| --- | --- | --- |
| Chưa đăng nhập, đọc 101 | 401 | HTTP Basic yêu cầu danh tính |
| `an`, đọc 101 | 200 | `report:read` và đúng owner |
| `an`, đọc 102 | 403 | Đúng authority nhưng sai owner |
| `reviewer`, đọc 102 | 200 | Có `report:read` và `report:read:any` |
| `an`, gọi `DELETE /api/reports/101` | Bị từ chối | `anyExchange().denyAll()` và có thể có CSRF enforcement |

Hai response thành công có JSON từ `ReportView`, ví dụ của `an`:

~~~json
{
  "id": 101,
  "owner": "an",
  "title": "Bao cao cua An",
  "seenBy": "an"
}
~~~

`seenBy = "an"` chỉ là bằng chứng Reactor Context được truyền đến chain. Trong thực tế tránh trả trường này nếu không có nhu cầu nghiệp vụ.

## 9. Test tích hợp HTTP: WebTestClient + springSecurity()

Để kiểm tra HTTP authorization thật (không phải nhấp nút UI), dùng Spring Test và Security WebTestClient configurer. Client gắn vào Spring `ApplicationContext` đã khởi động, áp dụng `springSecurity()` rồi thêm identity test bằng `mockUser`.

File `src/test/java/com/example/reactiveauth/ReportHttpSecurityTest.java`:

~~~java
package com.example.reactiveauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReportHttpSecurityTest {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousGets401() {
        client.get().uri("/api/reports/101")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void missingReadAuthorityGets403() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:write")))
                .get().uri("/api/reports/101")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void ownerSeesOwnReportAndItsReactorPrincipal() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:read")))
                .get().uri("/api/reports/101")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("an")
                .jsonPath("$.seenBy").isEqualTo("an");
    }

    @Test
    void changingIdCannotReadOtherOwnersReport() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:read")))
                .get().uri("/api/reports/102")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void reviewerWithBothPermissionsCanReadCrossOwner() {
        client.mutateWith(mockUser("reviewer").authorities(
                        new SimpleGrantedAuthority("report:read"),
                        new SimpleGrantedAuthority("report:read:any")))
                .get().uri("/api/reports/102")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("binh")
                .jsonPath("$.seenBy").isEqualTo("reviewer");
    }

    @Test
    void elevatedObjectPermissionAloneDoesNotGrantRead() {
        client.mutateWith(mockUser("reviewer").authorities(
                        new SimpleGrantedAuthority("report:read:any")))
                .get().uri("/api/reports/102")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void invalidReportIdIsNotGrantedAccess() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:read")))
                .get().uri("/api/reports/not-a-number")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Lưu ý cú pháp Java:** trong ví dụ trên hai câu import static bị tách thành hai dòng trước dấu chấm (`...server` rồi `.SecurityMockServerConfigurers...`). Java cho phép line break tại vị trí này, nhưng khi copy vào IDE có thể viết gọn thành:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
~~~

Không chèn cả hai kiểu import cùng lúc vào một file; chọn cách viết một dòng để dễ đọc. `mockUser` chỉ giả lập identity **cho test authorization**, không kiểm xác minh password/JWT thật.

**Kết quả mong đợi:** bảy test HTTP PASS khi chạy đúng Spring Boot 3.x + Security 6.x và filter/method bean theo ví dụ. Không có stdout cố định do test/framework; các HTTP status và JSON path đã được assert. Nếu ứng dụng không bật Spring WebFlux đúng, test sẽ báo lỗi context setup thay vì âm thầm xác nhận đúng policy.

## 10. Test Reactor Context ở service bằng StepVerifier

Đây là phần quan trọng nhất: **gọi thẳng service** mà không có HTTP filter. Gắn `Authentication` vào Reactor Context bằng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`; kiểm tra `@PreAuthorize` và `seenBy` sau `publishOn`.

File `src/test/java/com/example/reactiveauth/ReportReactorContextTest.java`:

~~~java
package com.example.reactiveauth;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReportReactorContextTest {

    @Autowired
    ReportService service;

    private static Authentication user(
            String name, String... authorities) {
        var grants = java.util.Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toList();
        return new UsernamePasswordAuthenticationToken(
                name, "n/a", grants);
    }

    @Test
    void anCanReadHisReportAfterPublishOn() {
        Authentication an = user("an", "report:read");

        Mono<ReportView> publisher = service.read(101L)
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(an));

        StepVerifier.create(publisher)
                .expectNextMatches(view ->
                        view.id() == 101L
                        && "an".equals(view.owner())
                        && "an".equals(view.seenBy()))
                .verifyComplete();
    }

    @Test
    void sameUserIsDeniedForAnotherOwner() {
        Authentication an = user("an", "report:read");

        StepVerifier.create(
                        service.read(102L)
                                .contextWrite(
                                        ReactiveSecurityContextHolder
                                                .withAuthentication(an)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void authorityWithoutFunctionPermissionIsDenied() {
        Authentication reviewer = user(
                "reviewer", "report:read:any");

        StepVerifier.create(
                        service.read(102L)
                                .contextWrite(
                                        ReactiveSecurityContextHolder
                                                .withAuthentication(
                                                        reviewer)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void approvedReviewerMayReadCrossOwner() {
        Authentication reviewer = user(
                "reviewer", "report:read", "report:read:any");

        StepVerifier.create(
                        service.read(102L)
                                .contextWrite(
                                        ReactiveSecurityContextHolder
                                                .withAuthentication(
                                                        reviewer)))
                .expectNextMatches(view ->
                        view.id() == 102L
                        && "binh".equals(view.owner())
                        && "reviewer".equals(view.seenBy()))
                .verifyComplete();
    }

    @Test
    void concurrentSubscribersRemainIsolated() {
        Authentication an = user("an", "report:read");
        Authentication binh = user("binh", "report:read");

        Mono<ReportView> first = service.read(101L)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(an));
        Mono<ReportView> second = service.read(102L)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(binh));

        StepVerifier.create(Mono.zip(first, second))
                .expectNextMatches(pair ->
                        "an".equals(pair.getT1().seenBy())
                        && "binh".equals(pair.getT2().seenBy())
                        && pair.getT1().id() == 101L
                        && pair.getT2().id() == 102L)
                .verifyComplete();
    }

    @Test
    void publisherCanBeBuiltBeforeContextIsWritten() {
        Mono<ReportView> waitingForSubscriber = service.read(101L);
        Authentication an = user("an", "report:read");

        StepVerifier.create(waitingForSubscriber.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(an)))
                .expectNextMatches(view ->
                        "an".equals(view.seenBy()))
                .verifyComplete();
    }
}
~~~

Ghi chú: `java.util.List` import trong file test không cần thiết (chỉ dùng `Arrays`). Trình biên dịch Java cho phép import thừa; có thể xóa để giữ code gọn. Tên test cố ý giải thích đúng ý nghĩa: `concurrentSubscribersRemainIsolated` tạo hai publisher có context riêng và dùng `Mono.zip` để subscribe cả hai; không dựa vào ThreadLocal shared state. Trong ứng dụng chạy nhiều request, còn cần test context không rò qua connection pool, cache và callback tích hợp bên ngoài Reactor.

Chạy bằng Maven Wrapper:

~~~bash
./mvnw -Dtest=ReportHttpSecurityTest,ReportReactorContextTest test
~~~

Windows:

~~~powershell
.\mvnw.cmd "-Dtest=ReportHttpSecurityTest,ReportReactorContextTest" test
~~~

**Kỳ vọng:** 7 test HTTP và 6 test service PASS; `publisherCanBeBuiltBeforeContextIsWritten` chứng minh publisher xây trước, context được cấp khi subscribe. Nếu một test `AccessDeniedException` khác do lỗi configuration/context, cần xem root cause, không đổi assertion thành chấp nhận bất kỳ exception.

## 11. Ma trận kiểm chứng cùng policy giữa HTTP và service

| Tình huống | HTTP WebTestClient | Service StepVerifier | Quyết định |
| --- | --- | --- | --- |
| Không xác thực | `401` | Cần deny khi không có Reactor Authentication | DENY |
| Có `report:write`, thiếu `report:read` | `403` | `AccessDeniedException` | DENY |
| `an` đọc báo cáo 101 | `200` + `seenBy=an` | Mono phát đúng `ReportView` | ALLOW |
| `an` đọc báo cáo 102 | `403` | `AccessDeniedException` | DENY |
| Reviewer chỉ có `report:read:any` | `403` | `AccessDeniedException` | DENY |
| Reviewer có cả hai authority, đọc 102 | `200` + `seenBy=reviewer` | Mono phát đúng dữ liệu | ALLOW |
| Path ID không phải số | `403` ở HTTP matcher demo | Không gọi service `long` | DENY |
| Hai subscription khác identity | Nên thêm test song song HTTP nếu cần | `Mono.zip` độc lập | Không rò context |

Kiểm cùng chính sách nghĩa là **cùng input principal + action + resource + context -> cùng quyền**. HTTP có thể trả 401 cho anonymous vì authentication entry point; method publisher có thể phát error security thay vì HTTP status. Đừng so sánh text exception với HTTP status; so sánh semantics ALLOW/DENY và dữ liệu quan sát.

Khi có nhiều tenant, policy phải bổ sung `tenantId` từ identity đã kiểm chứng và dữ liệu server. Chỉ check authority rồi trả mọi `reportId` sẽ mắc BOLA/IDOR, dù Reactor Context đã truyền đúng.

## 12. Cách kiểm thử Reactor Context nghiêm ngặt hơn

### 12.1. Đổi scheduler không có nghĩa context mất

`publishOn` và `subscribeOn` trong Reactor operators thông thường truyền **Reactor Context cùng subscription**. Lỗi thường là dùng API tạo execution ngoài Reactor mà không giữ Context.

~~~java
// Đúng: publisher vẫn trong cùng reactive chain.
return source.publishOn(Schedulers.parallel())
        .flatMap(value ->
                ReactiveSecurityContextHolder.getContext()
                        .map(ctx -> value + ":" +
                                ctx.getAuthentication().getName()));
~~~

Đoạn này là **snippet**, giả sử `source` là `Mono<String>`; không phải file độc lập. Đừng dùng `new Thread(...)` rồi gọi `SecurityContextHolder.getContext()` và kỳ vọng principal của WebFlux. Với callback ngoại vi hoặc `CompletableFuture`, phải tích hợp truyền context một cách chủ đích theo bridge phù hợp, không tự viết global static holder.

### 12.2. Không tự subscribe trong service

~~~java
// SAI: subscription nội bộ tách khỏi luồng HTTP,
// lỗi, cancellation và context caller không còn được quản lý.
Mono<ReportView> result = service.read(101L);
result.subscribe(view -> saveAudit(view));
return Mono.empty();
~~~

Cách phù hợp là **compose** một chain và trả publisher; nếu cần audit, dùng `doOnNext`/`flatMap` kết nối một reactive audit publisher để chờ hoàn thành đúng cách. `doOnNext` nên dành cho side effect ngắn, không blocking.

~~~java
// Snippet: ghi audit bất đồng bộ và chỉ trả khi ghi xong.
return service.read(101L)
        .flatMap(view -> auditRepository.saveEvent(view.id())
                .thenReturn(view));
~~~

`auditRepository.saveEvent` ở đây là interface giả định trả `Mono<?>`, cần được triển khai thực; không phải một method có sẵn của Spring Security.

### 12.3. Không block event loop để lấy SecurityContext

~~~java
// SAI trong WebFlux: block có thể gây deadlock,
// lỗi event-loop hoặc mất ngữ cảnh đã gắn theo subscription.
Authentication auth = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .block();
~~~

Không dùng `block()` trong production reactive chain, nhất là ở thread event loop. Nếu truy cập DB blocking, hãy chuyển sang reactive driver hoặc tách blocking adapter đúng cách, không ép lấy `Authentication` từ context rồi gắn vào ThreadLocal thủ công.

### 12.4. Phân biệt context của subscriber với global state

Một publisher có thể được subscribe hai lần với hai `Authentication` khác nhau. Nếu code lưu `Authentication` vào biến static/field singleton rồi reuse cho request sau, đã tạo **cross-request data leak**. Đảm bảo mọi quyết định lấy context mới theo subscription và không cache kết quả ALLOW mà thiếu principal/resource/tenant/policy version.

## 13. Lưu ý về tính tương thích Spring Security 6.x và 7.x

Spring Security cho reactive method authorization dùng `@EnableReactiveMethodSecurity`. Tài liệu và annotation options thay đổi theo phiên bản. Trong nhiều hướng dẫn Spring Security 6.x có ví dụ `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`; những phiên bản mới có thể mặc định dùng AuthorizationManager. Không bê nguyên cờ hoặc custom interceptor từ một bài viết cũ mà không kiểm tra dependency hiện hành.

Với Spring Security 7.x, các interface/kiểu trả về của custom authorization manager có thể thay đổi so với 6.x. **Đừng trộn một class triển khai `ReactiveAuthorizationManager` theo chữ ký API 7.x với ứng dụng 6.x.** Ví dụ ở mục 6 tránh định nghĩa custom manager class; nó dùng lambda `access` và `AuthorizationDecision` phổ biến trong 6.x, còn khi nâng version cần xem migration guide và compile/test lại.

Có hai điểm không được bỏ qua:

1. Spring Security Servlet dùng `SecurityFilterChain`, `HttpSecurity`, `@EnableMethodSecurity`. WebFlux dùng **`SecurityWebFilterChain`, `ServerHttpSecurity`, `@EnableReactiveMethodSecurity`**. Chúng không hoán đổi trực tiếp cho nhau.
2. Reactive `@PreAuthorize` bảo vệ publisher trong luồng subscribe. Nếu method trả giá trị đồng bộ hoặc chính bạn gọi `block()` rồi trả object đã tính, cơ chế authorization và context propagation có thể không còn đúng. Dùng `Mono`/`Flux`/Publisher và kiểm thử thật trên Spring bean.

Chốt version trong CI, kiểm thử dependency compatibility và audit mọi thay đổi ALLOW/DENY khi nâng cấp. Đừng dùng chỉ một test `200` để suy luận tất cả quyền vẫn đúng.

## 14. Những lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `403` cho user đúng owner | Thiếu `report:read`, quyền mapping sai, policy kết quả sai | Kiểm raw authorities và owner trong server data |
| User đúng authority đọc được report khác owner | Chỉ kiểm function permission, thiếu object policy | Dùng chung `ReportPolicy.canRead` ở HTTP + service |
| HTTP hoạt động nhưng gọi service trực tiếp bỏ qua policy | Chưa bật `@EnableReactiveMethodSecurity`, không gọi Spring proxy | Test `StepVerifier` gọi bean injected |
| Service cho 404 thay vì 403 khi ID lạ | Policy/model khác về đối tượng không tồn tại | Quy định 403/404 nhất quán, không lộ data |
| Test reactive method security mất principal | Không đặt `contextWrite` trên publisher được subscribe | Gắn `ReactiveSecurityContextHolder.withAuthentication(auth)` |
| Lúc dùng `publishOn` thấy principal null | Truy cập Servlet ThreadLocal, chạy callback ngoài Reactor | Dùng `ReactiveSecurityContextHolder` và compose chain |
| Hai request rò danh tính | Lưu auth trong static field / singleton | Không chia sẻ Authentication; test zip/concurrent subscription |
| `WebTestClient` mockUser không tác dụng | Chưa `apply(springSecurity())` hoặc bind sai context | Dùng đúng test configurer |
| Gọi `subscribe()` thủ công | Tách reactive chain khỏi subscriber gốc | Return publisher, nối operator |
| Dùng JDBC trong `canRead` | Blocking event loop, tăng latency | R2DBC, reactive authorization manager, tránh `block()` |
| Dùng `SecurityContextHolder` trong WebFlux | ThreadLocal không phản ánh subscriber context | Dùng `ReactiveSecurityContextHolder` |
| Chỉ test HTTP, không test service | Endpoint mới có thể bypass policy | Kiểm trực tiếp `service.read` |
| Chỉ test service, không test HTTP | Filter/matcher hoặc status sai | Test `WebTestClient` cả 401/403/200 |
| Dùng `@WithMockUser(roles="USER")` khi policy đòi `report:read` | `roles` tạo `ROLE_USER`, không tự tạo `report:read` | Dùng `authorities="report:read"` |
| Browser có CSRF token nhưng action sai quyền vẫn chạy | CSRF không phải object authorization | Rule quyền riêng cho mỗi action |
| Parse ID bằng cách lấy substring URL tùy ý | Route khác/malformed path có thể bypass | Dùng variables từ matcher chính xác và test đường biên |

## 15. Checklist hoàn thành bài thực hành

- [ ] Project chỉ dùng WebFlux starter cho ví dụ reactive (không vô tình chạy Spring MVC).
- [ ] `@EnableWebFluxSecurity` và `@EnableReactiveMethodSecurity` đều bật.
- [ ] `ReportPolicy` là nguồn logic duy nhất dùng ở HTTP và method security.
- [ ] Policy kiểm cả `report:read` và owner/authority cross-owner; default deny.
- [ ] Không tin owner/tenant/role do browser gửi.
- [ ] Mọi service bảo vệ là Spring bean trả về publisher reactive.
- [ ] Không `block()`/`subscribe()` thủ công trong controller/service.
- [ ] Context được lấy từ `ReactiveSecurityContextHolder` trong chain.
- [ ] `WebTestClient` test anonymous, thiếu quyền, đúng owner, sai owner, reviewer và ID lỗi.
- [ ] `StepVerifier` test truy cập service trực tiếp, đổi scheduler, và hai subscription có identity khác nhau.
- [ ] Có negative tests phát hiện 403/AccessDeniedException, không chỉ test 200.
- [ ] Khi thay in-memory repository bằng DB, giữ nonblocking và kiểm tenant theo object.
- [ ] Không coi CSRF/CORS/ẩn nút là thay thế authorization server.
- [ ] Khi nâng Spring Security, chạy lại matrix trên version thật.

## 16. Bài tập tự luyện

**Bài 1 — Mở rộng action:** thêm `DELETE /api/reports/{id}` với authority `report:delete` và chỉ owner được xóa. Viết policy `canDelete(authentication, id)` dùng chung HTTP/service; kiểm DELETE bởi guest, owner, người khác owner, reviewer, người dùng thiếu quyền. Khi dùng HTTP Basic/session trong trình duyệt, cần xử lý CSRF phù hợp; không vô hiệu hóa chỉ để test qua.

**Bài 2 — Thêm tenant:** model `Report` có `tenantId`. Quyền `report:read:any` chỉ có tác dụng **trong tenant đã xác thực**, không trên tất cả tenant. Viết test cross-tenant bị DENY dù user là reviewer. Không lấy tenantId từ request tùy ý.

**Bài 3 — Context isolation:** tạo 100 subscription độc lập với hai user, kết hợp `flatMap` và `publishOn`, khẳng định mọi `seenBy` đúng owner. Không được lưu principal vào biến static; nếu tăng concurrency mà thấy lẫn user, cần tìm đoạn tạo subscription/callback tách ngoài chain.

**Bài 4 — Reactive DB policy:** thay `ReportRepository` in-memory bằng repository R2DBC và một reactive authorization manager thực sự. Giải thích vì sao không nên gọi blocking DB trong `@PreAuthorize` và cách giữ nguyên semantics “có quyền chức năng + đúng object” với một nơi định nghĩa rule.

## 17. Tài liệu tham khảo

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebFlux Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Reactive Method Security Testing](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

**Kết luận:** “Cùng chính sách” không có nghĩa lặp hai đoạn if-else; đó là một policy duy nhất được gọi tại nhiều boundary và được kiểm bằng cùng ma trận quyền. Với WebFlux, principal cần đi theo **Reactor Context của subscriber**; muốn tin tưởng cơ chế này phải kiểm nghiệm bằng request HTTP, StepVerifier, đổi scheduler và nhiều subscriber song song.