# Kết hợp nhiều điều kiện phân quyền theo chính sách nghiệp vụ trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm kiến thức:** Phân quyền HTTP  
> **Đề bài:** Kết hợp nhiều điều kiện phân quyền theo chính sách nghiệp vụ.  
> **Đích học tập:** Thiết kế và kiểm thử một chính sách có điều kiện AND, OR và kiểm tra tài nguyên, thay vì gán một vai trò cố định cho mọi request. Mã ví dụ dùng Java 17+, Spring Boot WebFlux, Spring Security và WebTestClient.

## 1. Vấn đề: chỉ authenticated hoặc một role thường chưa đủ

Giả sử hệ thống quản lý đơn hàng đa tenant cần bảo vệ `GET /api/orders/{id}`. Nghiệp vụ quy định:

1. Người gọi phải **được xác thực**.
2. Người gọi cần quyền kỹ thuật `SCOPE_orders.read`.
3. Người gọi phải thuộc **ít nhất một** nhóm `ROLE_MEMBER` hoặc `ROLE_AUDITOR`.
4. Đơn hàng phải thuộc **tenant mà người gọi được cấp quyền**.
5. Đơn hàng phải ở trạng thái `OPEN`.
6. Trong tenant đó, người gọi chỉ được đọc đơn của **chính mình**, **hoặc** auditor có quyền đọc các đơn OPEN của tenant.

Nếu chỉ dùng `.authenticated()` thì Bob đã đăng nhập có thể truy cập đơn của Alice. Nếu chỉ dùng `.hasRole("AUDITOR")` thì thành viên bình thường không đọc được đơn của chính họ. Nếu viết sai vị trí dấu ngoặc, auditor có thể vô tình vượt qua điều kiện tenant hoặc scope.

Chính sách đúng là một biểu thức logic có thể kiểm thử:

~~~text
ALLOW =
    authenticated
    AND has("SCOPE_orders.read")
    AND (has("ROLE_MEMBER") OR has("ROLE_AUDITOR"))
    AND sameTenant
    AND orderStatus == OPEN
    AND (isOwner OR has("ROLE_AUDITOR"))
~~~

**Quan trọng:** hai nhóm điều kiện này nằm ở **hai lớp phù hợp**. Các quyền tổng quát trên request (authenticated, scope, role) có thể kiểm tra sớm ở **HTTP authorization**. Những điều kiện phụ thuộc dữ liệu thực (tenant của đơn, chủ sở hữu, trạng thái) nên kiểm tra ở **service/domain authorization**, nơi đã truy xuất tài nguyên bằng repository đáng tin cậy. Đặt rule HTTP không biến business rule thành mặc định đúng cho mọi luồng gọi service.

## 2. Các khái niệm: Authentication, Authorization, quyền và thuộc tính

- **Authentication:** xác minh danh tính người gọi; Spring Security đặt một `Authentication` vào `SecurityContext`. Một Authentication không nhất thiết có đủ quyền đọc đơn.
- **Authorization:** quyết định thao tác cụ thể có được phép với tài nguyên cụ thể hay không.
- **Role / RBAC:** nhóm quyền theo vai trò, ví dụ `ROLE_MEMBER`, `ROLE_AUDITOR`, `ROLE_ADMIN`.
- **Authority / Scope:** quyền cụ thể, ví dụ `SCOPE_orders.read` hoặc `SCOPE_orders.approve`. Trong Resource Server JWT, Spring Security thường ánh xạ scope thành authority có prefix `SCOPE_` theo cấu hình mặc định.
- **ABAC (attribute-based access control):** quyết định dựa vào thuộc tính người gọi, tài nguyên hoặc môi trường, ví dụ tenant, owner, bộ phận, thời điểm, trạng thái giao dịch.
- **ReBAC (relationship-based access control):** quyết định dựa vào quan hệ, ví dụ user là owner, collaborator hoặc được chia sẻ qua một nhóm có quyền.
- **Policy decision:** trả kết quả cho phép hoặc từ chối; với nghiệp vụ còn có thể cần lý do nội bộ để audit, nhưng **không** nên tiết lộ dữ liệu nhạy cảm trong thông báo lỗi công khai.

Một route URL có thể có quy tắc HTTP tổng quát, nhưng một bản ghi đơn hàng cần **quyền trên object cụ thể**. Không nhầm một `ROLE_ADMIN` hoặc scope toàn cục với quyền đọc mọi tenant: đó là một lựa chọn đặc quyền phải được định nghĩa và giám sát riêng.

## 3. AND, OR, NOT và thứ tự đánh giá

| Cách diễn đạt nghiệp vụ | Biểu thức | Ý nghĩa |
| --- | --- | --- |
| Có cả hai quyền | `A && B` | Thiếu một điều kiện thì từ chối |
| Có một trong hai vai trò | `A || B` | Ít nhất một điều kiện đúng |
| Không trong trạng thái bị khóa | `!locked` | Phủ định một điều kiện |
| Có scope và (owner hoặc auditor) | `scope && (owner || auditor)` | Scope áp dụng cho **cả hai nhánh** |
| Owner hoặc (auditor có scope) | `owner || (auditor && scope)` | **Sai** nếu owner cũng phải có scope |
| Đúng tenant và (owner hoặc auditor) | `tenant && (owner || auditor)` | Auditor **không** vượt ranh giới tenant |

Ví dụ sai phổ biến:

~~~java
boolean allowed =
    isOwner || (isAuditor && hasReadScope && sameTenant);
~~~

Ở biểu thức này, nếu `isOwner` true thì các điều kiện scope và tenant không cần đúng. Nếu nghiệp vụ quy định mọi nhánh đều cần scope và đúng tenant, phải đặt những điều kiện đó bên ngoài ngoặc:

~~~java
boolean allowed =
    hasReadScope && sameTenant && (isOwner || isAuditor);
~~~

**Deny by default:** nếu thiếu user, thiếu role, không tìm được đơn, tenant chưa xác định, trạng thái chưa hỗ trợ hoặc kết quả policy không rõ ràng, **không cấp quyền**. Trong ứng dụng sản xuất, lỗi từ policy service cũng không được âm thầm chuyển thành allow.

## 4. Hai cấp phân quyền: route trước, object sau

~~~mermaid
flowchart TD
    R["GET /api/orders/{id}"] --> C["SecurityWebFilterChain"]
    C --> A{"Có Authentication?"}
    A -->|"Không"| U["401: chưa xác thực"]
    A -->|"Có"| S{"Scope orders.read?"}
    S -->|"Không"| F["403: không có quyền HTTP"]
    S -->|"Có"| T{"ROLE_MEMBER OR ROLE_AUDITOR?"}
    T -->|"Không"| F
    T -->|"Có"| D["Controller → OrderService → OrderStore"]
    D --> E{"Đơn có tồn tại?"}
    E -->|"Không"| N["404: không thấy tài nguyên"]
    E -->|"Có"| G{"Tenant của đơn được cấp?"}
    G -->|"Không"| N
    G -->|"Có"| H{"Trạng thái OPEN?"}
    H -->|"Không"| N
    H -->|"Có"| O{"Owner OR Auditor?"}
    O -->|"Không"| N
    O -->|"Có"| P["200: trả dữ liệu được phép"]
~~~

**Tầng HTTP** giúp chặn sớm request thiếu quyền tổng quát, giảm việc chạy logic nặng và cho ra 401/403 hợp lý. **Tầng nghiệp vụ** quyết định quyền truy cập **một đối tượng thực**; nếu URL có `{id}` thì chỉ dựa vào id do client gửi là không đủ để quyết định quyền.

Lợi ích của việc tách lớp:

1. Không phải truy vấn DB cho mọi request chưa có quyền đọc.
2. Logic kiểm tra tenant/owner/state nằm gần use case và có thể tái sử dụng ở nhiều adapter: HTTP, message consumer, job nội bộ, GraphQL.
3. Policy có thể được kiểm thử độc lập với HTTP layer.
4. Quy tắc lỗi 404 che tài nguyên thuộc người khác có thể được áp dụng thống nhất trong service.
5. Nếu cần phân quyền thêm theo “bản ghi được khóa”, “yêu cầu duyệt hai người” hoặc “hạn mức giao dịch”, logic ở tầng domain phù hợp hơn một expression HTTP đơn giản.

Tuy nhiên, **bảo vệ mỗi HTTP endpoint vẫn cần thiết**. Service-level policy không thay thế cấu hình URL, và URL policy không thay kiểm tra đối tượng.

## 5. Cách Spring Security Reactive chọn rule trong authorizeExchange

Spring Security Reactive dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Các `pathMatchers` trong `authorizeExchange` được xét theo **thứ tự khai báo**. Khi một matcher phù hợp, **authorization manager tương ứng** quyết định; Spring không cộng tất cả các rule cùng khớp URL để tự tạo AND.

**Ví dụ sai — hai rule giống nhau không phải phép AND:**

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/api/orders/**").hasRole("MEMBER")
    .pathMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
    .anyExchange().denyAll()
)
~~~

Rule role khớp trước đã xử lý URL; rule scope sau **không** làm thành điều kiện thứ hai của cùng request. Nếu MEMBER không có scope mà chỉ rule đầu được áp dụng, rủi ro cấp quyền quá rộng.

**Ví dụ đúng — một matcher, một policy tổng hợp:**

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/orders/{id}")
        .access(orderReadRoutePolicy)
    .anyExchange().denyAll()
)
~~~

`orderReadRoutePolicy` là một `ReactiveAuthorizationManager<AuthorizationContext>` triển khai kết hợp điều kiện rõ ràng. Có thể dùng các manager sẵn có như `AuthorityReactiveAuthorizationManager.hasRole(...)` và `hasAuthority(...)` rồi phối hợp kết quả, hoặc viết policy Java thuần dễ kiểm thử như ví dụ bên dưới.

**Phân biệt thêm:** `securityMatcher` chọn **SecurityWebFilterChain** khi có nhiều chain; `pathMatchers` chọn rule **bên trong chain đã được chọn**. Một chain ưu tiên cao có matcher rộng có thể che chain khác. Bài này dùng **một chain** để tập trung vào policy composition, không pha trộn lỗi chain ordering.

## 6. Thiết kế chính sách mẫu và dữ liệu thử

Ứng dụng mẫu quản lý đơn đọc được bằng HTTP GET. Có 4 đơn hàng:

| Order ID | Tenant | Owner | Status |
| --- | --- | --- | --- |
| `ord-100` | `acme` | `alice` | OPEN |
| `ord-101` | `acme` | `charlie` | OPEN |
| `ord-200` | `beta` | `bob` | OPEN |
| `ord-300` | `acme` | `alice` | SEALED |

Dữ liệu xác thực mẫu (mật khẩu chỉ dành cho localhost):

| User | Authorities | Ý nghĩa |
| --- | --- | --- |
| `alice` | `ROLE_MEMBER`, `SCOPE_orders.read`, `TENANT_acme` | Chủ ord-100 và ord-300 |
| `charlie` | `ROLE_MEMBER`, `SCOPE_orders.read`, `TENANT_acme` | Chủ ord-101 |
| `bob` | `ROLE_MEMBER`, `SCOPE_orders.read`, `TENANT_beta` | Chủ ord-200 |
| `auditor` | `ROLE_AUDITOR`, `SCOPE_orders.read`, `TENANT_acme` | Đọc đơn OPEN trong acme |
| `observer` | `ROLE_MEMBER`, `TENANT_acme` | Thiếu scope đọc |
| `external` | `ROLE_GUEST`, `SCOPE_orders.read`, `TENANT_acme` | Có scope nhưng thiếu cả MEMBER/AUDITOR |

**Điều kiện route:** authenticated AND scope read AND (MEMBER OR AUDITOR). **Điều kiện service:** tenant của đơn nằm trong tenant được cấp cho principal AND trạng thái OPEN AND (principal là owner OR principal có role AUDITOR).

Trong lab, `TENANT_acme` là authority được server tạo từ user store. Trong thực tế, tenant phải xuất phát từ hệ thống danh tính/claim đã xác minh và được ánh xạ, hoặc được kiểm chứng với membership trong DB; **không tin header `X-Tenant` hoặc query parameter do client tự đặt như bằng chứng được cấp tenant**.

## 7. Cấu trúc project runnable

Yêu cầu **Java 17+**, Maven, cổng 8080 chưa sử dụng. Bài dùng Spring Boot **3.3.13** và API Spring Security 6.x làm bản lab có tính ổn định trong hướng dẫn; nhánh 3.3 đã kết thúc hỗ trợ OSS nên khi tạo hệ thống mới phải chọn bản Spring Boot/Spring Security còn được hỗ trợ, cập nhật mã và kiểm thử trên version sử dụng.

~~~text
reactive-business-authz/
├── pom.xml
└── src/
    ├── main/java/example/authz/
    │   ├── AuthzApplication.java
    │   ├── SecurityConfig.java
    │   ├── OrderReadRoutePolicy.java
    │   ├── OrderService.java
    │   └── OrderController.java
    └── test/java/example/authz/
        └── OrderAuthorizationTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactive-business-authz</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

`spring-boot-starter-webflux` cung cấp WebFlux/Project Reactor; `spring-boot-starter-security` cung cấp reactive security; `spring-boot-starter-test` cung cấp JUnit 5 và WebTestClient. **Không thêm `spring-boot-starter-web`** trong ví dụ vì lab dùng WebFlux, không trộn Servlet MVC.

### 7.2. Điểm khởi động

File `src/main/java/example/authz/AuthzApplication.java`:

~~~java
package example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzApplication.class, args);
    }
}
~~~

`@SpringBootApplication` tự động cấu hình và quét các bean cùng package. Không cần database thực; đơn hàng và users nằm trong bộ nhớ để người học tập trung vào logic chính sách. Production cần repository có bảo vệ tenant và hệ thống identity đáng tin cậy.

## 8. SecurityConfig: định nghĩa user mẫu và HTTP authorization

File `src/main/java/example/authz/SecurityConfig.java`:

~~~java
package example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    private UserDetails user(
            PasswordEncoder encoder,
            String name,
            String password,
            String... authorities) {

        return User.withUsername(name)
            .password(encoder.encode(password))
            .authorities(authorities)
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            user(encoder, "alice", "alice-pass",
                "ROLE_MEMBER", "SCOPE_orders.read", "TENANT_acme"),
            user(encoder, "charlie", "charlie-pass",
                "ROLE_MEMBER", "SCOPE_orders.read", "TENANT_acme"),
            user(encoder, "bob", "bob-pass",
                "ROLE_MEMBER", "SCOPE_orders.read", "TENANT_beta"),
            user(encoder, "auditor", "auditor-pass",
                "ROLE_AUDITOR", "SCOPE_orders.read", "TENANT_acme"),
            user(encoder, "observer", "observer-pass",
                "ROLE_MEMBER", "TENANT_acme"),
            user(encoder, "external", "external-pass",
                "ROLE_GUEST", "SCOPE_orders.read", "TENANT_acme")
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            OrderReadRoutePolicy readPolicy) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/{id}")
                    .access(readPolicy)
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
~~~

**Điều gì được kiểm tra ở đây?**

- Rule cụ thể cho GET `/api/public` cho phép anonymous.
- Chỉ GET `/api/orders/{id}` mới vào `readPolicy`. Việc có id trong URL không chứng minh người gọi được phép xem id đó.
- `anyExchange().denyAll()` từ chối các đường dẫn/method không khai báo. Không mở `/api/**` rộng quá mức.
- HTTP Basic được dùng để mô phỏng xác thực từng request đơn giản; raw password tồn tại trong source demo nên **chỉ dùng cho localhost**. Ngoài môi trường local, HTTP Basic bắt buộc qua HTTPS và nên có cơ chế identity/token phù hợp với kiến trúc.
- User store tạo authorities có prefix `ROLE_`, `SCOPE_` và `TENANT_` một cách tường minh; chúng **không được client tự chọn** khi gọi endpoint.
- `formLogin` bị tắt trong lab API để chưa đăng nhập nhận HTTP Basic challenge thay vì redirect tới trang login HTML.
- CSRF mặc định không bị tắt. Bài chỉ thực hiện **GET đọc dữ liệu**, nên không cần CSRF token cho các yêu cầu thử nghiệm. Nếu mở POST/PUT/DELETE, phải đánh giá CSRF dựa trên cách client mang credentials, không tắt CSRF vô điều kiện.

**Khi dùng JWT Resource Server:** thay HTTP Basic và user store bằng `oauth2ResourceServer(...jwt(...))`, cấu hình issuer, signature/audience/expiry và claim-to-authorities mapping. Logic AND/OR vẫn phù hợp, nhưng chỉ có giá trị khi authorities đến từ **token đã được xác thực và cấp đúng audience**; không sao chép role trực tiếp từ request body.

## 9. Custom ReactiveAuthorizationManager kết hợp AND/OR

File `src/main/java/example/authz/OrderReadRoutePolicy.java`:

~~~java
package example.authz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class OrderReadRoutePolicy
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        return authentication
            .map(auth -> {
                boolean loggedIn = auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken);

                boolean mayRead = has(auth, "SCOPE_orders.read");

                boolean actorType = has(auth, "ROLE_MEMBER")
                    || has(auth, "ROLE_AUDITOR");

                return new AuthorizationDecision(
                    loggedIn && mayRead && actorType);
            })
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private static boolean has(Authentication auth, String authority) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority::equals);
    }
}
~~~

### 9.1. Đọc biểu thức này thế nào?

~~~text
loggedIn && mayRead && (isMember || isAuditor)
~~~

- `loggedIn`: Authentication đã xác thực và không thuộc AnonymousAuthenticationToken.
- `mayRead`: có authority chính xác `SCOPE_orders.read`.
- `actorType`: có `ROLE_MEMBER` **hoặc** `ROLE_AUDITOR`.
- Thiếu bất kỳ điều kiện bắt buộc nào → `new AuthorizationDecision(false)`. Nếu thiếu Authentication, `defaultIfEmpty(...)` cũng từ chối.
- Chính sách không truy xuất tài nguyên hoặc tin URL id để phán đoán owner. Các thuộc tính động thuộc OrderService.
- Tham số `AuthorizationContext` được interface truyền vào và có thể cung cấp đường dẫn/path variables, nhưng trong bài này chúng **không là bằng chứng ownership**.

Vì đây là API Spring Security 6.x, `ReactiveAuthorizationManager.check(Mono<Authentication>, T)` trả `Mono<AuthorizationDecision>` và được `access(...)` chấp nhận. Các phiên bản Spring Security mới hơn còn có API `authorize(...)/AuthorizationResult`; khi nâng phiên bản, đối chiếu tài liệu API phù hợp thay vì trộn ví dụ từ nhiều major versions.

### 9.2. Tại sao không dùng expression URL dài?

Một policy có thể được viết bằng biểu thức, nhưng khi có nhiều điều kiện, policy Java riêng có lợi thế: type checking, unit tests, dễ thêm audit và không nhầm thứ tự operator. Đối với rule chỉ một điều kiện, vẫn ưu tiên DSL sẵn có:

~~~java
.pathMatchers("/admin/**").hasRole("ADMIN")
.pathMatchers("/public/**").permitAll()
~~~

**Không cần viết custom manager cho mọi URL.** Hãy tạo policy riêng khi cần kết hợp nhiều điều kiện hoặc khi logic được tái sử dụng/test độc lập. Tránh chuyển mọi rule thành các boolean if rải rác trong controller.

## 10. OrderService: kiểm tra quyền trên bản ghi thật

File `src/main/java/example/authz/OrderService.java`:

~~~java
package example.authz;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

record OrderRecord(
    String id,
    String tenant,
    String owner,
    String status
) {}

@Service
public class OrderService {

    private final Map<String, OrderRecord> orders = Map.of(
        "ord-100", new OrderRecord(
            "ord-100", "acme", "alice", "OPEN"),
        "ord-101", new OrderRecord(
            "ord-101", "acme", "charlie", "OPEN"),
        "ord-200", new OrderRecord(
            "ord-200", "beta", "bob", "OPEN"),
        "ord-300", new OrderRecord(
            "ord-300", "acme", "alice", "SEALED")
    );

    public Mono<OrderRecord> findReadable(
            String id,
            Authentication authentication) {

        return Mono.justOrEmpty(orders.get(id))
            .switchIfEmpty(Mono.error(hidden()))
            .flatMap(order -> {
                boolean sameTenant = has(authentication,
                    "TENANT_" + order.tenant());

                boolean isOwner = order.owner()
                    .equals(authentication.getName());

                boolean auditor = has(authentication, "ROLE_AUDITOR");

                boolean open = "OPEN".equals(order.status());

                boolean allowed = sameTenant
                    && open
                    && (isOwner || auditor);

                return allowed
                    ? Mono.just(order)
                    : Mono.error(hidden());
            });
    }

    private static boolean has(Authentication auth, String authority) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority::equals);
    }

    private static ResponseStatusException hidden() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
}
~~~

### 10.1. Vì sao service cần tự phân quyền nữa?

Route policy đã chứng minh `SCOPE_orders.read` và vai trò. Nhưng chỉ đến khi tra `OrderRecord` mới biết đơn thuộc tenant nào, ai là owner và trạng thái OPEN hay SEALED. Nếu service bỏ ba kiểm tra đó, người biết `ord-200` có thể thử đọc dữ liệu của tenant beta dù chỉ có quyền acme: đây là một dạng **Broken Object Level Authorization (BOLA/IDOR)**.

OrderService làm **một tổ hợp**:

~~~text
sameTenant
AND isOpen
AND (isOwner OR isAuditor)
~~~

- Alice có thể xem `ord-100` vì đúng tenant, đúng owner, OPEN.
- Charlie **không** xem `ord-100` dù cùng tenant và có scope, vì không là owner và không là auditor.
- Auditor của acme có thể xem `ord-100` và `ord-101`, nhưng không xem `ord-200` của beta.
- Alice **không** xem `ord-300` của mình vì trạng thái SEALED. Điều kiện trạng thái áp dụng cho cả member và auditor.
- Nếu không tìm thấy order hoặc không có quyền xem, bài lab trả **cùng 404** để không trực tiếp xác nhận sự tồn tại của order thuộc người khác.

**Chọn 404 hay 403 là quyết định API/threat model.** 403 biểu thị đã xác thực nhưng không có quyền; 404 có thể che sự tồn tại của tài nguyên khi định danh nhạy cảm. Trong ví dụ, **route-level denial** trả 403 khi thiếu scope/role, còn **object-level denial** trả 404. Nếu production dùng 404 để che object, cần giữ nhất quán response body, timing, log và cache behavior để không tạo oracle mới.

### 10.2. Không dùng tenant do client tự khai làm căn cứ

Đây là lỗi nguy hiểm:

~~~java
boolean allowed = request.headers().getFirst("X-Tenant")
    .equals(order.tenant());
~~~

Header `X-Tenant` có thể bị client giả. Trong lab, membership nằm trong authorities do server tạo. Trong production, nên lấy tenant membership từ identity đã xác minh/DB/permission service và kiểm tra lại trên record. Nếu user được cấp nhiều tenant, phải giải quyết policy chọn tenant hiện tại, giới hạn dữ liệu theo tenant đó và bảo vệ các request cập nhật trạng thái tenant.

### 10.3. Policy phải đi cùng truy vấn dữ liệu khi cần

Với database thật, truy vấn danh sách nên **lọc tenant, trạng thái và quyền trước khi phân trang**. Đừng lấy 100 bản ghi thuộc nhiều tenant rồi lọc trong Java sau đó trả danh sách; như vậy pagination/count/caching có thể lộ dữ liệu hoặc tạo tải không cần thiết.

Với thao tác thay đổi trạng thái (ví dụ phê duyệt đơn), cần kiểm tra điều kiện **tại thời điểm ghi** trong một transaction hoặc conditional update, tránh TOCTOU: trạng thái đơn có thể thay đổi giữa lúc check và update. Không cho request vượt qua rule chỉ vì GET trước đó đã được cho phép.

## 11. Controller chỉ điều phối, không tự suy đoán quyền

File `src/main/java/example/authz/OrderController.java`:

~~~java
package example.authz;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/orders/{id}")
    public Mono<Map<String, String>> order(@PathVariable String id) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .flatMap(auth -> orders.findReadable(id, auth))
            .map(record -> Map.of(
                "id", record.id(),
                "tenant", record.tenant(),
                "owner", record.owner(),
                "status", record.status()
            ));
    }
}
~~~

`ReactiveSecurityContextHolder.getContext()` lấy SecurityContext từ **Reactor Context** trong request WebFlux. Nó khác việc dùng Servlet `SecurityContextHolder.getContext()` dựa trên ThreadLocal. Code trả `Mono`, không gọi `block()`, không tự `subscribe()` và không phân tích Basic header bằng tay.

**Vì sao không check tenant trong controller?** Controller có nhiệm vụ mapping HTTP và trả dữ liệu; việc kiểm tra domain object được đặt trong service để các luồng khác có thể dùng lại. Khi thêm GraphQL, event consumer hoặc scheduled job, phải bảo đảm caller luôn đi qua use case có kiểm soát quyền, không truy cập thẳng repository và bỏ qua service policy.

## 12. Ma trận truy cập mong đợi

| Request tới `/api/orders/{id}` | Route checks | Object checks | Kết quả |
| --- | --- | --- | --- |
| Anonymous đọc ord-100 | Không authenticated | Không chạy | **401** |
| Alice đọc ord-100 | Scope + MEMBER pass | Tenant acme, owner Alice, OPEN | **200** |
| Charlie đọc ord-100 | Scope + MEMBER pass | Cùng tenant nhưng khác owner | **404** |
| Auditor acme đọc ord-100 | Scope + AUDITOR pass | Cùng tenant, auditor, OPEN | **200** |
| Auditor acme đọc ord-200 | Scope + AUDITOR pass | Sai tenant beta | **404** |
| Bob beta đọc ord-100 | Scope + MEMBER pass | Sai tenant acme | **404** |
| Bob beta đọc ord-200 | Scope + MEMBER pass | Đúng tenant và owner | **200** |
| Alice đọc ord-300 | Scope + MEMBER pass | Đơn trạng thái SEALED | **404** |
| Observer đọc ord-100 | Thiếu `SCOPE_orders.read` | Không chạy | **403** |
| External đọc ord-100 | Có scope, thiếu MEMBER/AUDITOR | Không chạy | **403** |
| Alice đọc id không tồn tại | Route pass | Không có object | **404** |
| GET /api/public anonymous | `permitAll()` | Không áp dụng | **200** |

**HTTP status khác nhau theo tầng:** khi chưa xác thực với HTTP Basic thường 401; đã xác thực nhưng thiếu scope/role tại HTTP thường 403; service chủ động trả 404 khi không thấy object hoặc muốn che nó. Khi đổi cơ chế xác thực sang form login hay Bearer JWT, entry point và error body có thể khác. Bảo đảm quyền bằng negative tests, không dựa duy nhất vào một status dự đoán.

## 13. Kiểm thử WebTestClient với dữ liệu thật của lab

File `src/test/java/example/authz/OrderAuthorizationTest.java`:

~~~java
package example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderAuthorizationTest {

    @Autowired
    WebTestClient client;

    private WebTestClient.ResponseSpec getAs(
            String uri, String user, String password) {
        return client.get()
            .uri(uri)
            .headers(headers -> headers.setBasicAuth(user, password))
            .exchange();
    }

    @Test
    void publicEndpointIsAccessibleWithoutLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void anonymousCannotReadOrders() {
        client.get().uri("/api/orders/ord-100")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void memberCanReadOwnOpenOrder() {
        getAs("/api/orders/ord-100", "alice", "alice-pass")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void anotherMemberInSameTenantCannotReadOrder() {
        getAs("/api/orders/ord-100", "charlie", "charlie-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void auditorMayReadOpenOrderInsideOwnTenant() {
        getAs("/api/orders/ord-101", "auditor", "auditor-pass")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("charlie");
    }

    @Test
    void auditorMustNotCrossTenantBoundary() {
        getAs("/api/orders/ord-200", "auditor", "auditor-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void memberMustNotCrossTenantBoundary() {
        getAs("/api/orders/ord-100", "bob", "bob-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void memberCanReadOwnOrderInBetaTenant() {
        getAs("/api/orders/ord-200", "bob", "bob-pass")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("beta");
    }

    @Test
    void sealedOrderIsNotReadableEvenByOwner() {
        getAs("/api/orders/ord-300", "alice", "alice-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void memberWithoutReadScopeIsForbiddenAtHttpLayer() {
        getAs("/api/orders/ord-100", "observer", "observer-pass")
            .expectStatus().isForbidden();
    }

    @Test
    void readScopeWithoutAllowedRoleIsForbidden() {
        getAs("/api/orders/ord-100", "external", "external-pass")
            .expectStatus().isForbidden();
    }

    @Test
    void unknownOrderUsesSameStatusAsHiddenOrder() {
        getAs("/api/orders/missing", "alice", "alice-pass")
            .expectStatus().isNotFound();

        getAs("/api/orders/ord-101", "alice", "alice-pass")
            .expectStatus().isNotFound();
    }

    @Test
    void unexpectedRouteIsDenied() {
        getAs("/api/admin/debug", "alice", "alice-pass")
            .expectStatus().isForbidden();
    }
}
~~~

Chạy:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Maven sẽ thực hiện unit/integration web tests. Các method có tên thể hiện **điều kiện cụ thể** cần chứng minh: không chỉ “Alice nhận 200” mà còn **Charlie bị chặn với cùng tenant**, **auditor không vượt tenant**, **user thiếu scope bị chặn tại HTTP** và **đơn SEALED bị chặn ngay cả khi là owner**.

**Chưa xem `mvn test` là một bằng chứng production security:** đây là test lab với user/order cố định. Trong hệ thống thật cần test với token đã được ký và kiểm chứng, cơ sở dữ liệu, transaction, nhiều tenant thực, proxy/gateway, cache và các đường gọi use case khác.

## 14. Kiểm thử thủ công bằng curl

Chạy app, sau đó dùng terminal khác. Với PowerShell có alias `curl`, dùng `curl.exe` nếu cần.

~~~bash
# API công khai
curl -i http://localhost:8080/api/public

# Không credentials → 401
curl -i http://localhost:8080/api/orders/ord-100

# Alice đọc đơn của mình; curl hỏi mật khẩu alice-pass
curl -i -u alice http://localhost:8080/api/orders/ord-100

# Charlie thử đọc đơn Alice; hỏi charlie-pass, kỳ vọng 404
curl -i -u charlie http://localhost:8080/api/orders/ord-100

# Auditor xem đơn acme; hỏi auditor-pass, kỳ vọng 200
curl -i -u auditor http://localhost:8080/api/orders/ord-101

# Auditor thử đơn beta; kỳ vọng 404
curl -i -u auditor http://localhost:8080/api/orders/ord-200
~~~

`curl -u username` không viết password trực tiếp vào shell history; sau khi chạy, nhập password demo khi được hỏi. Không đưa password thật hay Bearer token vào log và tài liệu chia sẻ. HTTP Basic ở `http://localhost:8080` chỉ hợp lý cho môi trường thực hành cục bộ; ngoài mạng thật phải dùng **HTTPS**.

Khi gọi hợp lệ, ví dụ JSON response từ `GET /api/orders/ord-100` dưới Alice:

~~~json
{
  "id": "ord-100",
  "tenant": "acme",
  "owner": "alice",
  "status": "OPEN"
}
~~~

Thứ tự field trong JSON không phải hợp đồng bảo mật; test dùng JSONPath để không phụ thuộc thứ tự của `Map.of(...)`.

## 15. Tại sao không chuyển điều kiện owner vào URL rule đơn giản?

Một URL có `/api/orders/{id}` chỉ cung cấp ID từ client. `id` không mang thông tin chắc chắn về tenant/owner. Nếu controller nhận thêm `?tenant=acme&owner=alice` hoặc header `X-User: alice`, client có thể sửa giá trị. Không thể kết luận quyền trên object bằng so sánh hai dữ liệu đều do client điều khiển.

Trường hợp có thể đặt tất cả tại HTTP: một policy manager tùy chỉnh có thể lấy path variable và **truy vấn repository đáng tin cậy** trong `ReactiveAuthorizationManager<AuthorizationContext>`. Tuy nhiên cần cân nhắc:

- Manager có thể phải truy vấn DB trước khi chọn controller, gây truy vấn trùng nếu controller đọc lại object.
- Cần giữ consistency giữa object được kiểm tra và object thực sự được sửa, đặc biệt với write.
- Phải hạn chế lỗi/timeout từ policy store và không biến lỗi thành allow.
- Quyết định cần được tái sử dụng ở use case ngoài HTTP; nếu toàn bộ policy chỉ nằm ở HTTP, một adapter khác có thể bỏ qua.
- Với danh sách, phân quyền từng item sau khi tải toàn bộ có thể làm lộ count và phân trang sai.

Vì vậy kiến trúc mẫu đặt **coarse authorization tại HTTP** và **fine-grained authorization gần dữ liệu**. Với hệ thống lớn, nên chuẩn hóa quyết định qua policy service/gate/permission evaluator tập trung, nhưng vẫn kiểm tra tại các use cases quan trọng.

## 16. Mở rộng chính sách: duyệt đơn với nhiều ràng buộc

Giả sử sau này có `POST /api/orders/{id}/approve`. Nghiệp vụ:

- User authenticated, có `SCOPE_orders.approve`.
- Có `ROLE_MANAGER` hoặc `ROLE_ADMIN`.
- Đúng tenant và đơn đang `PENDING_APPROVAL`.
- Người duyệt **không phải người tạo đơn** (four-eyes / separation of duties).
- Số tiền nằm trong hạn mức phê duyệt của user; đơn giá trị lớn cần cấp duyệt bổ sung.
- Request có idempotency key/transaction semantics phù hợp và CSRF nếu dùng auto-sent browser credentials.

Biểu thức đúng:

~~~text
ALLOW_APPROVE =
    authenticated
    AND has(SCOPE_orders.approve)
    AND (ROLE_MANAGER OR ROLE_ADMIN)
    AND sameTenant
    AND status == PENDING_APPROVAL
    AND (actorUserId != creatorUserId)
    AND withinApprovalLimit
    AND approvalWindowOpen
~~~

**Các điều kiện này phải áp dụng đồng thời.** Một lỗi dấu ngoặc kiểu `ROLE_ADMIN || (ROLE_MANAGER && withinApprovalLimit)` có thể vô tình bỏ giới hạn với admin, nếu chính sách yêu cầu giới hạn áp dụng cho cả hai. Nếu admin được miễn giới hạn thì phải ghi rõ **đó là ngoại lệ nghiệp vụ được phê duyệt**, kèm audit và test riêng.

**Chú ý TOCTOU:** với endpoint mutate, không làm: đọc state → kiểm tra state → cập nhật sau một khoảng thời gian mà không bảo vệ race. Sử dụng transaction/optimistic locking, conditional update với version/state và kiểm tra permission nhất quán tại thời điểm commit. Hai người duyệt đồng thời không được làm vượt giới hạn hoặc ghi đè trạng thái sai.

Bài mẫu chỉ triển khai GET để không che khuất bài học bởi CSRF và transaction; đoạn biểu thức duyệt đơn là **mô hình chính sách**, không phải một route đã được cài trong project.

## 17. Nên dùng hasRole, hasAuthority, hasAnyRole hay custom manager?

| Nhu cầu | Phương án thích hợp | Ví dụ |
| --- | --- | --- |
| Chỉ cần đã đăng nhập | `authenticated()` | User profile |
| Chỉ một role | `hasRole("ADMIN")` | Admin console |
| Một trong vài role | `hasAnyRole("MANAGER", "ADMIN")` | Trang báo cáo nội bộ |
| Một scope cụ thể | `hasAuthority("SCOPE_orders.read")` | API đọc đơn |
| Scope **và** role-group | `access(customReactiveAuthorizationManager)` | API cần scope + (member/auditor) |
| Quyền tùy record/tenant | Service/domain policy sau khi nạp object | Owner, tenant, status |
| Kiểm tra ở method service | `@PreAuthorize` + `@EnableReactiveMethodSecurity` | Bảo vệ các method `Mono`/`Flux` |
| Quy tắc rất phức tạp/nhiều service | Policy component/engine có contract rõ | Approval threshold, SoD, tenant delegation |

**Role và scope là các khái niệm có thể trùng ý nghĩa trong hệ thống nhỏ, nhưng nên quy định phân biệt rõ.** Ví dụ role mô tả nhóm nhiệm vụ, scope mô tả API capability. Trong JWT Resource Server, scope mapping phụ thuộc issuer/claim converter; không giả định role tự xuất hiện dưới dạng `ROLE_` nếu chưa cấu hình.

**Không nhầm `hasRole("MEMBER")` với `hasAuthority("ROLE_MEMBER")`:** Spring Security thường thêm prefix `ROLE_` cho `hasRole`; còn `hasAuthority` kiểm tra exact string. Lab dùng `"ROLE_MEMBER"` và `"SCOPE_orders.read"` trực tiếp trong Java để thể hiện các kiểm tra rõ ràng.

## 18. Method security: lớp bảo vệ bổ sung

Nếu nhiều entrypoints có thể gọi một use case (HTTP, GraphQL, scheduled tasks, message consumers), chỉ chặn ở URL chưa đủ. Spring Security Reactive hỗ trợ method security với Reactor Context.

Cấu hình phương thức bổ sung (đoạn trích cần đặt trong một Spring `@Configuration`):

~~~java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfig {
}
~~~

Ví dụ thêm điều kiện **coarse role/scope** lên một method service trả `Mono`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "(hasRole('MEMBER') or hasRole('AUDITOR'))")
public Mono<OrderRecord> findReadableForCurrentUser(String id) {
    // Nghiệp vụ phải nạp order, lấy Authentication từ Reactor Context,
    // rồi kiểm tra tenant, owner và status như OrderService.
    return Mono.empty(); // Chỉ minh họa vị trí annotation, không phải method chạy thật.
}
~~~

**Đây là đoạn minh họa cú pháp annotation, không thay thế OrderService ở mục 10.** Với method security thực tế phải thực thi logic, không trả `Mono.empty()` như phần phác thảo. Spring Security Reactive áp dụng method authorization với các publisher `Mono` / `Flux` và security context của Reactor. Tự gọi method của chính bean (self-invocation) có thể bỏ qua proxy AOP, do đó nếu policy chỉ đặt trên annotation phải thiết kế cách gọi qua bean proxy và kiểm thử trường hợp đó.

**Dù có `@PreAuthorize`, vẫn phải kiểm tra quyền trên object**. Annotation không tự suy ra tenant hoặc owner từ ID. Có thể dùng một bean policy được gọi trong SpEL, nhưng với async DB access và phức tạp nghiệp vụ, code policy Java riêng thường dễ test, audit và xử lý timeout hơn.

## 19. Authorization và authentication không thay thế nhau

Khi dùng HTTP Basic, mỗi request thành công có Authentication với user/authorities do server kiểm tra password. Nếu chuyển sang JWT:

- Resource Server phải xác minh chữ ký JWT hoặc introspection, issuer, hạn dùng, audience và token type theo hợp đồng.
- Scope/role/tenant phải đến từ claims đã được xác thực hoặc từ nguồn membership tin cậy và được ánh xạ nhất quán.
- Nếu quyền của user thay đổi giữa vòng đời token, claim cũ có thể lạc hậu; xác định SLA cho revocation, TTL, introspection/versioning hoặc tra cứu quyền động.
- Tenant active của request không được quyết định chỉ bằng header `X-Tenant` nếu user có thể giả; phải xác minh membership và phạm vi tài nguyên.
- Authentication valid **không** suy ra policy allow, kể cả token có role ADMIN.

Ở luồng reactive, đừng gọi `SecurityContextHolder.getContext()` như một `ThreadLocal` Servlet rồi giả định luôn có principal chính xác. Dùng `ReactiveSecurityContextHolder` trong publisher, hoặc truyền một principal **đã xác thực** vào service theo ranh giới rõ ràng.

## 20. 401, 403, 404 và cách trả lỗi an toàn

**401 Unauthorized:** thiếu hoặc sai thông tin xác thực. Với HTTP Basic, server thường gửi `WWW-Authenticate` challenge.

**403 Forbidden:** user đã xác thực nhưng thiếu scope/role cần cho route, hoặc bị một policy authorization từ chối. Trong một số phương thức HTTP, thiếu CSRF token có thể cũng gây 403; phân biệt qua logs an toàn và test.

**404 Not Found:** tài nguyên không tồn tại hoặc chủ động che sự tồn tại của object user không có quyền xem, theo API contract. Không tự kết luận rằng 404 nghĩa object chưa từng được tạo; nó có thể là chính sách tránh BOLA enumeration.

Nếu chọn 404 cho object denial, tránh có thông báo khác biệt giữa “not found” và “not authorized”, tránh lộ qua count/list/caching và cần kiểm tra timing khi thực sự có rủi ro. Trong log nội bộ, có thể lưu lý do từ chối với correlation ID, nhưng phải bảo vệ dữ liệu nhạy cảm, không đưa object/customer PII vào response.

**Không lộ nội dung đơn trước khi cấp quyền.** Ví dụ tệ:

~~~java
return repository.findById(id)
    .doOnNext(order -> log.info("Order payload: {}", order))
    .flatMap(order -> checkAuthorization(order, auth));
~~~

Logging raw order trước khi quyết định quyền có thể làm lộ dữ liệu nhạy cảm. Ở service thật, chỉ ghi metadata tối thiểu, tránh log token/header Authorization, và áp dụng policy gần truy vấn.

## 21. Các lỗi phổ biến khi ghép chính sách

1. **Nhiều pathMatchers cùng URL được hiểu là AND.** Thực tế rule phù hợp đầu tiên chi phối; dùng một `.access(policy)` để gộp.
2. **Đặt URL public quá rộng trước rule riêng tư.** `/api/**.permitAll()` có thể che route cần xác thực.
3. **Nhầm AND/OR và ngoặc.** `owner || auditor && tenant` khác `tenant && (owner || auditor)`; hãy viết test cho từng nhánh.
4. **Cho auditor vượt tất cả điều kiện.** Nếu tenant/scope/status vẫn bắt buộc, đừng viết `auditor || (scope && tenant && owner)`.
5. **Dùng request parameter làm bằng chứng tenant/owner.** Attacker có thể thay URL, body, query và header.
6. **Chỉ kiểm tra role ở HTTP, bỏ IDOR ở service.** Người dùng đăng nhập có thể truy cập ID của người khác.
7. **Chỉ kiểm tra bản ghi khi đọc, không bảo vệ update.** Trạng thái thay đổi gây race/TOCTOU.
8. **Lấy toàn bộ danh sách rồi lọc quyền sau phân trang.** Có thể lộ count, gây kết quả sai và mất dữ liệu tenant.
9. **Tin scope JWT mà không xác minh issuer/audience/signature.** Claim chưa xác thực không phải authority đáng tin.
10. **Cho phép khi policy service lỗi/timeout.** Authorization phải fail closed; xử lý 5xx/503 phù hợp thay vì tự allow.
11. **Cache quyết định quyền quá lâu.** Role/tenant/status thay đổi khiến kết quả cache cũ dễ tạo quyền dư.
12. **Dùng ThreadLocal trong WebFlux.** Bỏ hoặc đọc nhầm SecurityContext khi chuyển scheduler.
13. **Tắt CSRF để thử POST với browser cookie/Basic.** Phải hiểu credential transport và threat model trước.
14. **Chỉ test người có quyền, thiếu negative tests.** Không biết policy có vượt tenant hoặc vượt scope hay không.
15. **Dựa vào chính sách ở controller duy nhất.** Job, GraphQL hoặc adapter khác có thể gọi service bỏ qua.
16. **Dùng role ADMIN làm ngoại lệ mặc định.** Nếu có break-glass, cần điều kiện, audit và quyền tối thiểu được quy định riêng.

## 22. Bài tập vận dụng

### Bài A — viết truth table

Tạo bảng ít nhất 12 tổ hợp `authenticated`, `SCOPE_orders.read`, `ROLE_MEMBER`, `ROLE_AUDITOR`. Điền ALLOW/DENY cho rule HTTP. Chứng minh nếu thiếu scope thì **cả member và auditor** đều bị từ chối.

### Bài B — sửa lỗi operator precedence

Giả sử code cũ viết:

~~~java
boolean allowed = isOwner || isAuditor && sameTenant && isOpen;
~~~

Hãy chỉ ra ít nhất hai request được cho phép sai; sửa thành biểu thức với dấu ngoặc rõ ràng. Sau đó thêm test riêng cho auditor khác tenant, owner của SEALED order và member có sai tenant.

### Bài C — thêm một điều kiện policy HTTP

Nghiệp vụ cho phép đọc order chỉ khi feature flag `orders.read.enabled` đang bật, **kể cả với auditor**. Dựng một `ReadPolicySettings` bean hoặc policy service tin cậy, kết hợp thành `authenticated && scope && roleGroup && featureEnabled`. Viết negative test khi flag tắt. Không lấy feature flag trực tiếp từ header do client gửi.

### Bài D — thêm phân quyền collection

Tạo `GET /api/orders`, đọc nhiều order. Yêu cầu chỉ trả các đơn OPEN cùng tenant mà người dùng là owner hoặc auditor được phép xem. Thực hiện filter trong repository/database **trước khi phân trang**; kiểm tra total count/caching không lộ số đơn tenant khác.

### Bài E — mở luồng phê duyệt

Thiết kế chính sách cho `POST /api/orders/{id}/approve` với scope approve, role manager/admin, đúng tenant, trạng thái chờ duyệt, creator khác approver và hạn mức. Viết test cho concurrent approvals và deny khi thiếu CSRF token trong mô hình cookie/session phù hợp.

### Bài F — phân quyền theo giờ và môi trường

Thêm điều kiện thời điểm làm việc với `Clock` được inject để test deterministic. Nếu policy gọi hệ thống bên ngoài để biết “đang trong ca”, cần timeout rõ ràng và fail closed. Không phụ thuộc `LocalDateTime.now()` trực tiếp trong test dẫn đến flaky.

### Bài G — BOLA/IDOR test

Dùng user Charlie thử đọc đơn Alice bằng thay `id` trong URL. Chứng minh cùng tenant + cùng role + cùng scope vẫn **không** đủ, vì owner khác. Thêm một auditor acme đọc hợp lệ rồi thử auditor đó với đơn beta; tenant phải là hàng rào bắt buộc cho cả hai nhánh.

### Checklist tự đánh giá

- [ ] Định nghĩa rõ toàn bộ điều kiện `ALLOW` bằng AND/OR/NOT và dấu ngoặc.
- [ ] Phân biệt authenticated, authority/scope, role, tenant, owner và trạng thái tài nguyên.
- [ ] Hiểu `authorizeExchange` chọn một rule theo thứ tự; không cộng hai pathMatchers thành AND.
- [ ] Dùng `ReactiveAuthorizationManager<AuthorizationContext>` để gộp scope + role tại HTTP.
- [ ] Kiểm tra ownership/tenant/status ở service với object thực.
- [ ] Không tin ID/tenant/owner do client tự khai nếu chưa xác minh.
- [ ] Dùng deny-by-default cho route ngoài danh sách và không allow khi policy không chắc.
- [ ] Có test 401, 403, 404 che object và 200 hợp lệ cho các nhánh quyền.
- [ ] Auditor không vượt tenant, owner không vượt trạng thái, member không vượt scope.
- [ ] Không lộ dữ liệu thông qua listing, count, cache hoặc log trước authorization.
- [ ] Nhận biết race/TOCTOU khi quyền phụ thuộc vào trạng thái đang thay đổi.
- [ ] Có cách áp dụng cùng domain policy khi service bị gọi ngoài controller HTTP.

## 23. Câu hỏi tự kiểm tra

1. Hai dòng `pathMatchers("/api/**").hasRole("MEMBER")` và `pathMatchers("/api/**").hasAuthority("SCOPE_orders.read")` có tạo điều kiện AND không? Vì sao?
2. Vì sao route policy thường chỉ nên quyết định role/scope, còn kiểm tra owner/tenant nên nằm gần database/use case?
3. Biểu thức nào đúng khi auditor vẫn cần scope và cùng tenant: `auditor || (scope && tenant)` hay `scope && tenant && (owner || auditor)`?
4. Nếu user có `SCOPE_orders.read` nhưng không có ROLE_MEMBER/ROLE_AUDITOR, HTTP layer trả gì?
5. Nếu Alice có role MEMBER/scope và đơn SEALED thuộc Alice, có được trả dữ liệu không?
6. Vì sao chỉ có `ROLE_ADMIN` không tự chứng minh quyền trên mọi tenant?
7. Khác biệt giữa 401, 403 và 404 “che object” là gì?
8. Khi chuyển từ HTTP Basic demo sang JWT, authority và tenant membership phải được xác minh như thế nào?
9. Nếu object được check là OPEN rồi một request khác chuyển nó sang SEALED trước khi update, đây là loại vấn đề gì?
10. Tại sao query danh sách cần lọc quyền **trước khi** phân trang và cache?
11. Nếu policy engine bên ngoài không phản hồi, nên allow theo mặc định hay fail closed?
12. Test nào chứng minh mạnh nhất rằng auditor có quyền đọc trong tenant **không** mặc nhiên được đọc tenant khác?

## 24. Tài liệu chính thức và hướng dẫn an toàn

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): thứ tự rule `authorizeExchange` và custom `ReactiveAuthorizationManager` với `.access(...)`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize` và Reactor Context.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `ServerHttpSecurity` và chain selection.
- [Spring Security — ReactiveAuthorizationManager API (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): giao diện `check` và `authorize` khi chuyển phiên bản.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): encoder cho tài khoản demo và production.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): rủi ro khi chỉ kiểm tra route mà không kiểm tra object ID.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny-by-default, validate every request và phân quyền trên dữ liệu.
- [OWASP — Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html): kiểm soát quyền theo đối tượng và quản trị policy.

**Kết luận:** Quyền truy cập thực tế thường là **tổ hợp** của danh tính, scope, vai trò, tenant, quan hệ owner và trạng thái tài nguyên. Với Spring Security Reactive, đưa **một chính sách tổng hợp** vào `.access(ReactiveAuthorizationManager)` ở HTTP thay vì hy vọng nhiều `pathMatchers` được cộng lại; sau đó kiểm tra các điều kiện **phụ thuộc bản ghi thật** trong domain service. Viết biểu thức có dấu ngoặc, từ chối theo mặc định, kiểm thử cả nhánh được phép lẫn bị chặn, và không để ngoại lệ role vô tình vượt ranh giới tenant/owner.