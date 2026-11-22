# Biểu thức SpEL với authentication, principal và tham số phương thức

> **Chủ đề:** Spring Security – reactive  
> **Nhóm:** Phân quyền phương thức  
> **Mục tiêu:** Sử dụng Spring Expression Language (SpEL) trong `@PreAuthorize` để ràng buộc danh tính đã xác thực với tham số method; phân biệt `authentication`, `principal`, `#owner`, `#p0`, bean policy; thực hành bằng Spring WebFlux Java 17+, `WebTestClient` và `StepVerifier`.

## 1. Tình huống thực tế và kết quả cần đạt

Giả sử user `alice` đăng nhập thành công, gọi `GET /api/invoice/bob/inv-42`. Một HTTP rule chỉ yêu cầu `authenticated()` sẽ cho request đi tiếp vì Alice có mật khẩu đúng. Nhưng business policy còn phải xác định Alice **có quyền xem hóa đơn của Bob hay không**. Đây là lý do đặt authorization ở tầng service/method thay vì chỉ dừng ở phân quyền URL.

Một rule đơn giản:

```java
@PreAuthorize("hasAuthority('invoice:read') and #owner == authentication.name")
public Mono<String> invoice(
        @P("owner") String owner, String invoiceId) {
    return Mono.just("invoice=" + invoiceId + ",owner=" + owner);
}
```

Đoạn trên **chưa phải chương trình độc lập**: cần Spring bean, `@EnableReactiveMethodSecurity`, imports và security context. Ý nghĩa: chỉ người có quyền `invoice:read`, có username trùng tham số `owner`, được phép gọi method.

- `authentication`: đối tượng `Authentication` do Spring Security xác lập;
- `authentication.name`: kết quả của `Authentication.getName()`;
- `#owner`: biến SpEL ánh xạ từ tham số method được gắn `@P("owner")`;
- `hasAuthority`: kiểm tra chính xác chuỗi `GrantedAuthority`;
- `and`: cả hai điều kiện phải đúng.

**Cảnh báo IDOR/BOLA:** `owner` là tham số người dùng có thể tự khai trong URL. Nếu attacker gọi `/api/invoice/alice/inv-of-bob`, biểu thức có thể đúng dù invoice ID thuộc Bob. Vì vậy **so tên method param với principal chỉ là một chốt**; khi đọc dữ liệu thật phải xác minh owner và tenant từ storage bằng resource ID. Xem mục 12.

### Sau bài học, bạn làm được gì?

1. Bật `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` đúng cho Spring WebFlux.
2. Giải thích root object/property `authentication`, `principal` và methods `hasRole`, `hasAuthority`.
3. Tham chiếu method arguments bằng tên `#owner`, bằng `@P("owner")` hoặc vị trí `#p0`/`#a0`.
4. Viết biểu thức có `and`/`or`, phân biệt rule `owner only` với `admin OR owner`.
5. Hiểu việc principal có thể là `UserDetails`, `Jwt`, `String` hoặc custom object.
6. Tách logic phức tạp sang bean SpEL `@ownerPolicy.canView(...)` trả `Mono<Boolean>` thay vì blocking.
7. Kiểm tra method security qua Spring AOP proxy, Reactor Context, HTTP 401/403 và test theo subscription.

## 2. Method security nằm ở đâu trong ứng dụng reactive?

Có hai tầng phân quyền phổ biến:

| Tầng | Cấu hình/API | Câu hỏi |
| --- | --- | --- |
| HTTP WebFlux | `SecurityWebFilterChain`, `ServerHttpSecurity.authorizeExchange` | URL này có cần đăng nhập, role hay scope không? |
| Method/service | `@PreAuthorize("...")` và các method-security interceptors | Người này được gọi **hàm nghiệp vụ với các đối số cụ thể** không? |

Method-level authorization được Spring Security áp dụng nhờ **Spring AOP proxy**, không phải Java tự thực thi annotation. Annotation chứa một chuỗi SpEL được phân tích khi đánh giá bảo mật. Sai tên biến/property thường là **lỗi runtime** chứ không phải lỗi javac.

```text
Browser / API client
  |
  v
HTTP WebFilter chain
  ├─ AuthenticationWebFilter: lấy/kiểm tra credentials
  ├─ SecurityContext trong Reactor Context
  └─ AuthorizationWebFilter: HTTP matcher
  |
  v
@RestController
  |
  v
InvoiceService được inject (Spring proxy)
  |
  v
Reactive method interceptor: @PreAuthorize
  ├─ DENY: phát lỗi AccessDeniedException -> HTTP thường 403
  └─ ALLOW: gọi nghiệp vụ, tiếp tục Mono/Flux -> HTTP thường 200
```

Đây là sơ đồ rút gọn; ứng dụng thật còn nhiều filter, entry point, CSRF, CORS, security context persistence, exception translation. Trong test HTTP Basic của bài, request không có credentials thường trả 401; user đã xác thực nhưng không thỏa SpEL thường trả 403.

### 2.1. Bật đúng annotation cho reactive

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {
    // Định nghĩa SecurityWebFilterChain và user store ở ví dụ đầy đủ.
}
```

Import `EnableReactiveMethodSecurity` từ `org.springframework.security.config.annotation.method.configuration`. Tùy bản Spring Security, `useAuthorizationManager` có thể là mặc định; chỉ định rõ giúp ví dụ Spring Security 6.5 dùng mô hình reactive AuthorizationManager, bao gồm hỗ trợ biểu thức boolean và bean trả `Mono<Boolean>`.

**Reactive return type:** phương thức được bảo vệ nên trả publisher như `Mono<T>` hoặc `Flux<T>`, để interceptor có thể tương tác với Reactor Context tại subscription. Không dùng ví dụ `@EnableMethodSecurity` của Servlet mà bỏ qua `@EnableReactiveMethodSecurity` rồi mong kết quả giống nhau.

### 2.2. Proxy và self-invocation

Nếu bạn `new InvoiceService()` thay vì lấy bean từ Spring context, annotation sẽ không tự thực thi. Nếu `public Mono<?> outer()` gọi `this.securedInner()` **trong cùng bean**, lời gọi nội bộ có thể đi tắt proxy. Nên đặt chốt lên method entrypoint thực sự được gọi qua Spring bean, hoặc tách service bảo mật thành bean riêng.

Method `private` hay `final` cũng có thể gây rắc rối với proxy tùy kiểu proxy. Thiết kế tốt: service Spring bean, method có thể được proxy, được inject vào controller; có test âm tính chứng minh việc từ chối thực sự xảy ra.

## 3. authentication: danh tính được Spring Security xác minh

Trong SpEL method security, `authentication` đại diện `org.springframework.security.core.Authentication`.

```text
authentication.name          -> Authentication.getName()
authentication.principal     -> Authentication.getPrincipal()
authentication.authorities   -> Authentication.getAuthorities()
authentication.authenticated -> Authentication.isAuthenticated()
```

Ví dụ:

```java
@PreAuthorize("authentication.name == #owner")
```

`authentication.name` được lấy từ **Authentication hiện tại**, không lấy từ `X-User`, `?username=` hay form field tự khai. Một ứng dụng Basic, session hoặc JWT có thể xác thực bằng cơ chế khác nhau nhưng cuối cùng Spring Security cung cấp Authentication tương ứng.

Các điều kiện thường gặp:

```java
@PreAuthorize("isAuthenticated() and #owner == authentication.name")
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("hasAuthority('invoice:read')")
@PreAuthorize("hasRole('ADMIN') or #owner == authentication.name")
```

Đây là bốn ví dụ riêng lẻ, **không** đặt liên tiếp lên cùng method để cố cộng dồn nhiều `@PreAuthorize`. Mỗi annotation biểu diễn một policy. `isAuthenticated()` giúp loại anonymous khỏi điều kiện; `hasRole('ADMIN')` thông thường đòi authority `ROLE_ADMIN`, còn `hasAuthority('invoice:read')` đòi đúng chuỗi `invoice:read`.

### 3.1. Authentication khác ThreadLocal

Spring Security reactive cung cấp `SecurityContext` thông qua **Reactor Context của subscription**. Code Java ở service đọc trực tiếp:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Đoạn trên trả `Mono<String>`, không phải một chuỗi sẵn có. Đừng gọi `.block()` trên Netty event loop, và đừng dùng `SecurityContextHolder.getContext()` kiểu imperative rồi cho rằng cùng thread theo suốt request. `publishOn` có thể đổi thread nhưng Reactor Context vẫn đi theo subscription trong Reactor chain hợp lệ.

`@PreAuthorize` được Spring Security reactive kết nối với Context này; nó không cần một static user variable. Khi test không HTTP, có thể cấp Authentication cho riêng subscription bằng `ReactiveSecurityContextHolder.withAuthentication(auth)`.

### 3.2. Không dựa riêng vào authentication.authenticated

Một `Authentication` đại diện anonymous cũng có thể tồn tại trong chain, tùy cấu hình. Nếu muốn user đã login, `isAuthenticated()` là một biểu thức thích hợp. Không kiểm tra chỉ `authentication.name != null`: tên đại diện `anonymousUser` hoặc principal giả không chứng minh login thành công.

Đừng dùng `authentication.credentials` trong authorization expression, log hoặc response: đó có thể là password/token hoặc đã bị xóa. Quyết định quyền nên dựa vào danh tính đã xác thực, authorities và trạng thái resource đáng tin cậy.

## 4. principal: kiểu object phụ thuộc authentication mechanism

Trong SpEL:

```text
principal ≈ authentication.principal
```

Nhưng **principal không phải lúc nào cũng là `UserDetails`**.

| Nguồn xác thực | Principal thường gặp | `principal.username` có an toàn không? |
| --- | --- | --- |
| HTTP Basic với `MapReactiveUserDetailsService` | Spring Security `UserDetails` | Có, nếu object có `getUsername()` |
| Form login với `UserDetailsService` | Thường là `UserDetails` | Có trong đúng kiểu implementation |
| OAuth2 Resource Server JWT | `Jwt` hoặc dạng principal từ converter | **Không tự giả định** có `username` |
| Custom service identity | `String` hoặc custom class | Tùy API của object |
| Anonymous | Principal đại diện anonymous | Không nên dùng làm người dùng thực |

So sánh:

```java
@PreAuthorize("principal.username == #owner")
```

chỉ phù hợp nếu principal có `getUsername()`. Nó hoạt động trong ví dụ HTTP Basic/UserDetails phía dưới. Cách ít phụ thuộc class hơn thường là:

```java
@PreAuthorize("authentication.name == #owner")
```

Nhưng ngay cả `authentication.name` cũng có thể được ánh xạ từ `sub`, `client_id` hoặc custom principal tùy authentication converter. Cần thống nhất **identity key** và tenant policy, không tự nghĩ tên trả về luôn là email.

### 4.1. SpEL đọc property như thế nào?

SpEL dùng property syntax tương ứng getter:

```text
authentication.name       -> getName()
principal.username        -> getUsername(), nếu tồn tại
authentication.principal  -> getPrincipal()
```

Nếu principal là `String` mà expression gọi `principal.username`, việc đánh giá có thể lỗi vì property không tồn tại. Null-safe `principal?.username` chỉ bảo vệ receiver null, **không tạo getter không có thật**. Thay vì biểu thức dài kiểu `principal.profile.organization.id`, hãy chuẩn hóa claims vào Authentication hoặc chuyển sang policy Java đã được test.

## 5. Tham số method: #owner, #p0, #a0

SpEL ký hiệu **`#`** cho variable. Khi Spring Security đánh giá `@PreAuthorize` trên method, đối số Java có thể được truy cập bằng **tên** hoặc **vị trí**.

```java
public Mono<String> read(String owner, String invoiceId)
```

Giả sử gọi `read("alice", "inv-42")`:

| Biểu thức | Giá trị | Cách xác định |
| --- | --- | --- |
| `#owner` | `alice` | Parameter name phải được discover hoặc annotate |
| `#invoiceId` | `inv-42` | Tên đối số thứ hai |
| `#p0` | `alice` | Tham số **vị trí 0** |
| `#a0` | `alice` | Alias theo vị trí 0 |
| `#p1` | `inv-42` | Tham số vị trí 1 |
| `#root` | Root evaluation object | Không phải `owner` hay `invoiceId` |

### 5.1. @P("owner") là lựa chọn tường minh

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize("#owner == authentication.name")
public Mono<String> own(@P("owner") String owner) {
    return Mono.just("own:" + owner);
}
```

Đây là **snippet trong một class/service**. `@P` cần import **`org.springframework.security.access.method.P`** (không tự bịa `org.springframework.security.core.parameters.P`). Dù Java compiler có hay không giữ parameter names, `@P("owner")` cho method security biết tên biến cần dùng.

### 5.2. Dùng parameter name metadata

Nếu method compile với `-parameters`, Spring Security có thể discover `owner` để dùng `#owner`. Với Maven:

```xml
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
```

Nhưng đừng mặc định mọi module/library đã được compile giống nhau. Khi dùng interfaces, proxies, bytecode không có parameter metadata hoặc build pipeline khác, `#owner` có thể không được bind đúng. Với quyền quan trọng, prefer `@P` hoặc test chắc chắn.

### 5.3. #p0 và #a0 dựa trên thứ tự

```java
@PreAuthorize("hasAuthority('invoice:read') and #p0 == authentication.name")
public Mono<String> position(String owner) {
    return Mono.just("position:" + owner);
}
```

`#p0` không cần tên `owner`. Tuy nhiên nếu đổi signature từ `position(String owner)` sang `position(String invoiceId, String owner)` mà quên cập nhật expression, `#p0` sẽ **so invoiceId với username**, có thể gây bug phân quyền. Named variables thường rõ hơn khi có nhiều tham số.

### 5.4. Sai tên biến hoặc nhầm ký hiệu

```java
// Sai nếu method chỉ có tham số tên owner:
@PreAuthorize("#user == authentication.name")
public Mono<String> own(String owner);
```

`#user` không tự trỏ đến `owner`. Tương tự `owner` không có dấu `#` có thể được SpEL hiểu như property trên expression root, không phải method variable. Viết `#owner` hoặc `#p0` rõ ràng và test trường hợp deny.

## 6. AND, OR, role/authority và bean trong SpEL

SpEL hỗ trợ `and`/`or` hoặc `&&`/`||`:

```java
@PreAuthorize("hasRole('ADMIN') or #owner == principal.username")
```

Admin **hoặc** owner được phép. Nếu dùng `and`, cần cả role và owner. Tránh nhầm khi chuyển từ requirement “admin OR owner” sang code “admin AND owner”.

Một số biểu thức tiêu biểu:

| Expression | Điều kiện | Chú ý |
| --- | --- | --- |
| `isAuthenticated()` | Caller đã được xác thực | Không nên chỉ kiểm tra name != null |
| `hasRole('ADMIN')` | Thường yêu cầu `ROLE_ADMIN` | Prefix mặc định `ROLE_` |
| `hasAuthority('invoice:read')` | Tên quyền chính xác | Không tự thêm prefix |
| `authentication.name == #owner` | Trùng username/owner param | Không chứng thực owner của invoice thực |
| `principal.username == #owner` | Getter của principal trùng owner | Chỉ khi principal có getter |
| `#p0 == authentication.name` | So đối số đầu | Có thể lệch khi refactor |
| `A and B` | Cần cả A và B | Logic AND |
| `A or B` | Cần A hoặc B | Logic OR |
| `@ownerPolicy.canView(authentication, #owner)` | Gọi bean Spring | Tách policy khỏi chuỗi dài |

### 6.1. Khi nào nên gọi bean thay vì nhồi một expression dài?

Nếu business policy liên quan nhiều vai trò, database ownership, tenant, lịch sử giao dịch hoặc quy tắc thay đổi thường xuyên, annotation SpEL dài rất khó audit. Spring Security hỗ trợ `@beanName.method(...)`; phần `@ownerPolicy` là bean Spring, không phải cùng loại với biến `#owner`.

```java
@PreAuthorize("@ownerPolicy.canView(authentication, #owner)")
public Mono<String> byPolicy(@P("owner") String owner) {
    return Mono.just("policy:" + owner);
}
```

Với `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`, bean được gọi trong biểu thức có thể trả **`Boolean` hoặc `Mono<Boolean>`** theo cơ chế reactive. Không dùng `repositoryCall.block()` trong biểu thức; hãy để policy trả publisher của kết quả bất đồng bộ, kèm test và timeout phù hợp.

## 7. Chú ý đến subscription, Reactor Context và lỗi 401/403

```text
Request Authorization: Basic valid for alice
  |
  v
Spring Security WebFlux -> Authentication(name=alice)
  |
  v
SecurityContext được mang trong Reactor Context
  |
  v
Controller gọi InvoiceService qua AOP proxy
  |
  v
@PreAuthorize("#owner == authentication.name")
  |
  +-- owner=alice  --> cho phép --> Publisher nghiệp vụ --> HTTP 200
  |
  +-- owner=bob    --> từ chối --> AccessDeniedException --> HTTP 403
```

**Chú ý:** một chuỗi reactive có assembly và subscription, không phải mọi hành động diễn ra đồng bộ khi gọi method. Method interceptor reactive áp authorization theo pipeline, nhận security context của subscription hiện tại. Một service tự tạo `subscribe()` bên trong callback có thể tách khỏi context và mất đường error/cancellation. Trả `Mono`/`Flux` thay vì `block()` hay `subscribe()` thủ công.

HTTP `authenticated()` từ chối anonymous trước khi tới method: thường **401** với Basic challenge. Nếu credentials đúng nhưng `@PreAuthorize` deny, lỗi ở method-level thường thành **403**. Không gán mọi 403 cho `@PreAuthorize`: CSRF, HTTP denyAll hoặc chốt policy khác cũng có thể tạo 403.

## 8. Project Java 17+ hoàn chỉnh với Spring Security WebFlux

Ví dụ cố định **Spring Boot 3.5.16** để có một baseline học tập đã phát hành; đây là bản cuối của nhánh 3.5 với hỗ trợ OSS đã kết thúc. Khi triển khai mới cần chọn nhánh Spring Boot còn được hỗ trợ (4.x), điều chỉnh dependency và test API theo migration guide. Dự án sau dùng Java 17+ và Spring Security 6.x do Boot quản lý.

**Bốn tài khoản demo** (password chung `demo123`, chỉ để học):

| Username | GrantedAuthority | Mục đích |
| --- | --- | --- |
| `alice` | `invoice:read` | Được đọc invoice của mình |
| `bob` | `invoice:read` | Được đọc invoice của mình |
| `admin` | `ROLE_ADMIN`, `invoice:read` | Có rule ngoại lệ theo role khi được khai báo |
| `visitor` | `ROLE_VIEWER` | Đã đăng nhập nhưng không có `invoice:read` |

Security HTTP chỉ yêu cầu `/api/**` authenticated. Quyền chi tiết được đặt trong `InvoiceService`, làm nổi bật chênh lệch giữa HTTP và method. Các endpoint là GET, nên không tắt CSRF.

### 8.1. Thư mục

```text
method-spel-webflux/
├── pom.xml
└── src/
    ├── main/java/demo/spel/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   ├── OwnerPolicy.java
    │   ├── InvoiceService.java
    │   └── InvoiceController.java
    └── test/java/demo/spel/
        ├── ReactiveMethodSpelHttpTests.java
        └── ReactiveMethodSpelPublisherTests.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>method-spel-webflux</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. Application.java

```java
package demo.spel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 8.4. SecurityConfiguration.java

```java
package demo.spel;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Demo: không hardcode secret thật trong source.
        String password = "demo123";

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode(password))
            .authorities("invoice:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode(password))
            .authorities("invoice:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(password))
            .authorities("ROLE_ADMIN", "invoice:read")
            .build();

        UserDetails visitor = User.withUsername("visitor")
            .password(encoder.encode(password))
            .authorities("ROLE_VIEWER")
            .build();

        return new MapReactiveUserDetailsService(
            alice, bob, admin, visitor);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Giải thích:** `@EnableReactiveMethodSecurity` đăng ký interceptor method, còn `SecurityWebFilterChain` cho HTTP Basic và chốt đăng nhập URL. `roles("ADMIN")` tương đương cấp `ROLE_ADMIN`; ví dụ dùng `authorities` tường minh để dễ kiểm tra cả role và permission. BCrypt lưu hash trong user store in-memory. Không dùng mẫu mật khẩu này ngoài localhost và không tắt HTTPS validation ở môi trường thật.

### 8.5. OwnerPolicy.java

```java
package demo.spel;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("ownerPolicy")
public class OwnerPolicy {

    public Mono<Boolean> canView(
            Authentication authentication, String owner) {
        return Mono.fromSupplier(() -> {
            if (authentication == null
                    || !authentication.isAuthenticated()) {
                return false;
            }

            boolean admin = authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

            boolean read = authentication.getAuthorities().stream()
                .anyMatch(a -> "invoice:read".equals(a.getAuthority()));

            boolean sameOwner = authentication.getName().equals(owner);
            return admin || (read && sameOwner);
        });
    }
}
```

`@Component("ownerPolicy")` tạo bean có tên khớp `@ownerPolicy` trong expression. `Mono.fromSupplier` không blocking và cho phép đánh giá ở subscription. Một policy thực tế có thể dùng repository reactive để tìm owner từ `invoiceId`. Đừng biến `Mono<Boolean>` thành boolean bằng `block()`.

### 8.6. InvoiceService.java

```java
package demo.spel;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InvoiceService {

    @PreAuthorize("isAuthenticated() and #owner == authentication.name")
    public Mono<String> own(@P("owner") String owner) {
        return Mono.just("own:" + owner);
    }

    // Demo Basic UserDetails có getter getUsername().
    @PreAuthorize("isAuthenticated() and principal.username == #owner")
    public Mono<String> byPrincipal(@P("owner") String owner) {
        return Mono.just("principal:" + owner);
    }

    @PreAuthorize("hasAuthority('invoice:read') and #p0 == authentication.name")
    public Mono<String> positional(String owner) {
        return Mono.just("position:" + owner);
    }

    @PreAuthorize("hasRole('ADMIN') or #owner == principal.username")
    public Mono<String> viewOrAdmin(@P("owner") String owner) {
        return Mono.just("view:" + owner);
    }

    @PreAuthorize("hasAuthority('invoice:read') and #owner == authentication.name")
    public Mono<String> invoice(
            @P("owner") String owner,
            @P("invoiceId") String invoiceId) {
        return Mono.just("invoice=" + invoiceId + ",owner=" + owner);
    }

    @PreAuthorize("@ownerPolicy.canView(authentication, #owner)")
    public Mono<String> byPolicy(@P("owner") String owner) {
        return Mono.just("policy:" + owner);
    }
}
```

Chính xác từng method:

- `own`: chỉ kiểm tra caller đã login và `owner` trùng `Authentication.getName()`.
- `byPrincipal`: kiểm tra property `username` trên principal `UserDetails`.
- `positional`: đối số đầu `#p0` trùng tên và có quyền `invoice:read`.
- `viewOrAdmin`: rule **OR**, admin có thể xem account khác, user thường chỉ xem account mình.
- `invoice`: kết hợp permission với named parameter; **không** truy vấn DB ownership thật.
- `byPolicy`: ủy quyền cho bean Java trả `Mono<Boolean>` theo reactive method security.

### 8.7. InvoiceController.java

```java
package demo.spel;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class InvoiceController {
    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/own/{owner}")
    public Mono<String> own(@PathVariable String owner) {
        return service.own(owner);
    }

    @GetMapping("/api/principal/{owner}")
    public Mono<String> principal(@PathVariable String owner) {
        return service.byPrincipal(owner);
    }

    @GetMapping("/api/position/{owner}")
    public Mono<String> position(@PathVariable String owner) {
        return service.positional(owner);
    }

    @GetMapping("/api/view/{owner}")
    public Mono<String> view(@PathVariable String owner) {
        return service.viewOrAdmin(owner);
    }

    @GetMapping("/api/invoice/{owner}/{invoiceId}")
    public Mono<String> invoice(
            @PathVariable String owner,
            @PathVariable String invoiceId) {
        return service.invoice(owner, invoiceId);
    }

    @GetMapping("/api/policy/{owner}")
    public Mono<String> policy(@PathVariable String owner) {
        return service.byPolicy(owner);
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> {
                Object principal = auth.getPrincipal();
                String principalName = principal instanceof UserDetails details
                    ? details.getUsername() : auth.getName();
                return "authentication=" + auth.getName()
                    + ";principal=" + principalName;
            });
    }
}
```

Controller nhận `InvoiceService` qua constructor injection, vì vậy lời gọi được chuyển qua proxy của Spring. Nó không tự `subscribe()`/ `block()`; đây là yêu cầu quan trọng trong WebFlux. Endpoint `/api/me` chỉ dùng trong demo để xem Authentication và principal, không cần lộ thông tin nhận dạng đầy đủ của security context trong production.

## 9. Bộ kiểm thử WebTestClient sử dụng HTTP Basic thật

Bộ test xác minh login và method security qua toàn bộ WebFlux stack. Dùng `bindToApplicationContext(...).apply(springSecurity())` để chạy filter chain trong bộ test; request gửi `Authorization: Basic ...` thật qua `HttpHeaders.setBasicAuth`. Không dùng `mockUser` để tuyên bố đã test password verification.

### 9.1. ReactiveMethodSpelHttpTests.java

```java
package demo.spel;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveMethodSpelHttpTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec getAs(String username, String path) {
        return client.get().uri(path)
            .headers(h -> h.setBasicAuth(username, "demo123"))
            .exchange();
    }

    @Test
    void publicHealthDoesNotNeedAuthentication() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void missingCredentialsReturn401BeforeMethodAuthorization() {
        client.get().uri("/api/own/alice")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void incorrectBasicPasswordReturns401() {
        client.get().uri("/api/own/alice")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void matchingAuthenticationNameAndOwnerAreAllowed() {
        getAs("alice", "/api/own/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("own:alice");
    }

    @Test
    void differentMethodOwnerIsDenied() {
        getAs("alice", "/api/own/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void anotherUserCanAccessTheirOwnOwnerMethod() {
        getAs("bob", "/api/own/bob")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("own:bob");
    }

    @Test
    void ownerOnlyCheckDoesNotRequireInvoiceReadAuthority() {
        getAs("visitor", "/api/own/visitor")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("own:visitor");
    }

    @Test
    void principalUsernameWorksForUserDetailsPrincipal() {
        getAs("alice", "/api/principal/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("principal:alice");
    }

    @Test
    void principalUsernameRejectsOtherOwner() {
        getAs("bob", "/api/principal/alice")
            .expectStatus().isForbidden();
    }

    @Test
    void positionalParameterP0AllowsSameOwner() {
        getAs("alice", "/api/position/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("position:alice");
    }

    @Test
    void positionalParameterP0RejectsDifferentOwner() {
        getAs("alice", "/api/position/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void positionalParameterAlsoRequiresInvoiceRead() {
        getAs("visitor", "/api/position/visitor")
            .expectStatus().isForbidden();
    }

    @Test
    void ownerCanViewOwnResource() {
        getAs("alice", "/api/view/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("view:alice");
    }

    @Test
    void ordinaryUserCannotViewAnotherOwner() {
        getAs("alice", "/api/view/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanViewAnotherOwnerUsingRoleExpression() {
        getAs("admin", "/api/view/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("view:alice");
    }

    @Test
    void adminDoesNotAutomaticallyBypassStrictOwnerOnlyRule() {
        getAs("admin", "/api/own/alice")
            .expectStatus().isForbidden();
    }

    @Test
    void namedOwnerAndInvoiceIdArgumentsBindCorrectly() {
        getAs("alice", "/api/invoice/alice/inv-42")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("invoice=inv-42,owner=alice");
    }

    @Test
    void invoiceRequiresOwnerMatch() {
        getAs("alice", "/api/invoice/bob/inv-42")
            .expectStatus().isForbidden();
    }

    @Test
    void invoiceAlsoRequiresReadAuthority() {
        getAs("visitor", "/api/invoice/visitor/inv-42")
            .expectStatus().isForbidden();
    }

    @Test
    void reactiveBeanPolicyAllowsOwnerWithPermission() {
        getAs("alice", "/api/policy/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("policy:alice");
    }

    @Test
    void reactiveBeanPolicyRejectsAnotherOwner() {
        getAs("alice", "/api/policy/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void reactiveBeanPolicyAllowsAdmin() {
        getAs("admin", "/api/policy/bob")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("policy:bob");
    }

    @Test
    void reactiveBeanPolicyRejectsVisitorWithoutReadAuthority() {
        getAs("visitor", "/api/policy/visitor")
            .expectStatus().isForbidden();
    }

    @Test
    void securityContextContainsExpectedPrincipal() {
        getAs("alice", "/api/me")
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("authentication=alice;principal=alice");
    }
}
```

Có **24 phương thức `@Test`**. Kết quả của mỗi test độc lập: HTTP Basic sai hoặc thiếu => 401; login đúng mà không thỏa SpEL => 403; đúng username/authority => 200. Điều kiện `principal.username` chỉ được chứng minh ở principal UserDetails của project.

### 9.2. Ma trận trọng tâm

| User | URL | SpEL nổi bật | Status dự kiến |
| --- | --- | --- | --- |
| Anonymous | `/api/own/alice` | HTTP authenticated | **401** |
| Alice, password sai | `/api/own/alice` | Authentication thất bại | **401** |
| Alice | `/api/own/alice` | `#owner == authentication.name` | **200** |
| Alice | `/api/own/bob` | Owner mismatch | **403** |
| Visitor | `/api/own/visitor` | Owner-only, không cần quyền invoice | **200** |
| Visitor | `/api/position/visitor` | Thiếu `invoice:read` | **403** |
| Alice | `/api/principal/alice` | `principal.username` | **200** |
| Alice | `/api/position/bob` | `#p0` mismatch | **403** |
| Alice | `/api/view/bob` | Không admin và không là owner | **403** |
| Admin | `/api/view/alice` | `hasRole('ADMIN')` | **200** |
| Admin | `/api/own/alice` | Rule chỉ cho owner | **403** |
| Alice | `/api/invoice/alice/inv-42` | Có authority, owner match | **200** |
| Alice | `/api/policy/bob` | Bean `Mono<Boolean>` trả false | **403** |
| Admin | `/api/policy/bob` | Bean có nhánh admin | **200** |

**Không cố định body lỗi 401/403** khi chưa tùy biến entry point và denied handler. Body/headers phụ có thể thay đổi theo Spring Boot, server và content negotiation.

## 10. Test publisher trực tiếp bằng StepVerifier

Test này dùng bean service từ Spring context nhưng **không khởi tạo HTTP request**. Thay vào đó cấp `Authentication` cho subscription qua `ReactiveSecurityContextHolder.withAuthentication`.

### ReactiveMethodSpelPublisherTests.java

```java
package demo.spel;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveMethodSpelPublisherTests {

    @Autowired
    InvoiceService service;

    private static Authentication auth(String username, String... authorities) {
        return new TestingAuthenticationToken(username, "unused", authorities);
    }

    @Test
    void publisherAllowsMatchingNameAndAuthority() {
        Mono<String> source = service.positional("alice")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "invoice:read")));

        StepVerifier.create(source)
            .expectNext("position:alice")
            .verifyComplete();
    }

    @Test
    void publisherDeniesDifferentName() {
        Mono<String> source = service.positional("bob")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "invoice:read")));

        StepVerifier.create(source)
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void publisherDeniesMissingAuthority() {
        Mono<String> source = service.positional("alice")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "ROLE_VIEWER")));

        StepVerifier.create(source)
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void publisherUsesIndependentContextPerSubscription() {
        Mono<String> source = service.own("bob");

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("bob", "invoice:read"))))
            .expectNext("own:bob")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "invoice:read"))))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

Có **4 test StepVerifier**, tổng cộng project có **28 test**. `TestingAuthenticationToken` là token **giả cho test**; `withAuthentication` cho phép tập trung kiểm tra rule method security nhưng **không xác minh mật khẩu thật**. Để kiểm tra HTTP Basic/password, vẫn cần WebTestClient với credentials thật ở mục 9.

Mỗi `contextWrite` chỉ áp dụng cho subscription phía upstream của nó; việc có hai subscribers với `bob` và `alice` không tự chia sẻ identity. Điều này rất quan trọng trong ứng dụng phục vụ nhiều request trên một nhóm event-loop threads.

## 11. Chạy Maven, kiểm tra output và thử curl

Từ thư mục chứa `pom.xml`, dùng Java 17+ và Maven tương thích:

```bash
java -version
mvn -version
mvn clean test
```

Kỳ vọng từ mã đã liệt kê: **28 phương thức test**, gồm 24 test WebTestClient và 4 test StepVerifier. Maven Surefire báo `Tests run: 28, Failures: 0, Errors: 0` và `BUILD SUCCESS` nếu môi trường/dependencies đáp ứng và tests không có lỗi ngoài dự kiến. **Đây là kỳ vọng của bài học, không phải tuyên bố đã chạy trên máy của bạn.** Xem `target/surefire-reports` để điều tra nếu kết quả khác.

Khởi động WebFlux server:

```bash
mvn spring-boot:run
```

Thử bằng tài khoản demo, trên localhost:

```bash
# Health public
curl -i http://localhost:8080/health

# Thiếu credentials: 401
curl -i http://localhost:8080/api/own/alice

# Đúng caller: 200
curl -i -u alice:demo123 http://localhost:8080/api/own/alice

# Caller alice, owner bob: 403
curl -i -u alice:demo123 http://localhost:8080/api/own/bob

# Principal UserDetails khớp username: 200
curl -i -u alice:demo123 http://localhost:8080/api/principal/alice

# Biến theo vị trí #p0: 200
curl -i -u alice:demo123 http://localhost:8080/api/position/alice

# ADMIN có nhánh OR: 200
curl -i -u admin:demo123 http://localhost:8080/api/view/bob

# Admin không vượt qua rule owner-only: 403
curl -i -u admin:demo123 http://localhost:8080/api/own/alice

# Bean SpEL reactive trả Mono<Boolean>
curl -i -u alice:demo123 http://localhost:8080/api/policy/alice
curl -i -u alice:demo123 http://localhost:8080/api/policy/bob
```

PowerShell có thể cần `curl.exe` thay `curl`. **Không dùng credentials thật trong command line** của môi trường production vì shell history/process inspection có thể chứa password. Dùng HTTPS/TLS cho hệ thống ngoài localhost, password hashing mạnh và secret management.

Một phản hồi thành công của `/api/own/alice`:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

own:alice
```

Một phản hồi bị method security từ chối:

```http
HTTP/1.1 403 Forbidden
```

Một phản hồi thiếu HTTP Basic authentication:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Header `realm` và các headers phụ không cố định trừ khi đã cấu hình riêng. Test ở mục 9 chỉ yêu cầu có challenge, không khóa cứng exact realm.

## 12. Ranh giới bảo mật: chủ tài khoản không phải chủ resource

SpEL sau:

```java
@PreAuthorize("#owner == authentication.name")
```

**không tự chống hết IDOR/BOLA**. Nếu `owner` do client gửi, attacker Alice có thể tạo URL `/api/invoice/alice/invoice-owned-by-bob`: `owner == authentication.name` đúng nhưng invoice thật không thuộc Alice. Do đó đừng để method dựa vào `owner` tự khai để quyết định resource có thuộc caller.

Thiết kế tốt hơn:

```text
1. Lấy identity + tenantId đáng tin từ Authentication/claims đã xác minh.
2. Tìm invoice thật theo invoiceId trong tenant scope.
3. Lấy ownerId thực tế từ invoice được lưu.
4. So ownerId với subjectId của Authentication, hoặc kiểm tra quyền admin
   được cấp cho tenant/resource đó.
5. Chỉ khi cho phép mới phát nội dung hoặc thực hiện mutation.
```

Ví dụ pseudocode repository reactive:

```java
// Minh họa API, cần tự định nghĩa InvoiceRepository, Invoice và auth context.
return repository.findByIdAndTenantId(invoiceId, trustedTenantId)
    .filter(invoice ->
        invoice.ownerId().equals(trustedSubjectId) || mayAdminRead)
    .switchIfEmpty(Mono.error(new AccessDeniedException("denied")));
```

Đây là **snippet kiến trúc chưa biên dịch độc lập**, nhằm cho thấy cách truy vấn theo tenant/resource thật. Trong một ứng dụng hoàn chỉnh, phải phân biệt resource thực sự không tồn tại với resource tồn tại nhưng bị cấm, xử lý tránh user enumeration, kiểm soát race/TOCTOU, và gắn chốt trước side effects.

Khi có nhiều tenant, cùng một username `alice` ở tenant A và B không phải cùng principal. Dùng subject ID + tenant scope từ nguồn tin cậy, không chỉ chuỗi username trần. Khi policy cần DB, bean SpEL trả `Mono<Boolean>` có thể đưa phép kiểm tra vào repository reactive thay vì cố gọi repository blocking trong annotation.

## 13. Method security không bảo đảm chạy nếu đi tắt proxy

Một anti-pattern:

```java
// Minh họa, chưa đầy đủ imports/package.
@Service
public class UnsafeService {
    public Mono<String> outer(String owner) {
        return inner(owner); // self-invocation trong cùng instance
    }

    @PreAuthorize("#owner == authentication.name")
    public Mono<String> inner(@P("owner") String owner) {
        return Mono.just("sensitive");
    }
}
```

`outer` gọi `this.inner` có thể bypass Spring AOP proxy, khiến annotation trên `inner` không được enforce. Sửa bằng một trong các cách:

- Gắn quyền trực tiếp vào entrypoint method `outer` nếu đó là boundary đúng.
- Đưa `inner` vào một Spring bean khác và inject bean đó để call qua proxy.
- Tách Java policy rồi gọi explicit trước thao tác nhạy cảm nếu cần enforcement độc lập với AOP.
- Viết **test âm tính**: user không có quyền phải nhận lỗi, không chỉ test các case cho phép.

Không tự `new` một service có annotation và tin rằng AOP sẽ hoạt động. Với reactive method security, nên kiểm tra cả return type lẫn đường gọi bean.

## 14. Những lỗi SpEL phổ biến và cách sửa

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `#owner` không nhận đúng giá trị | Tên parameter không được expose hoặc typo | Dùng `@P("owner")`, `-parameters`, test |
| Dùng `#user` trong method có `owner` | Sai tên biến | Đồng bộ tên annotation/parameter |
| Dùng `#p0` sau khi đổi thứ tự args | Trỏ nhầm đối số | Dùng `@P` hoặc cập nhật positional expression |
| `principal.username` lỗi với JWT | Principal không có getUsername() | Dùng `authentication.name` hoặc converter/policy riêng |
| `authentication.name` không giống email | Name có thể lấy từ JWT sub/ID | Chuẩn hóa subject key tin cậy |
| `hasRole('ADMIN')` không cho user có authority `ADMIN` | Mặc định cần `ROLE_ADMIN` | Cấp đúng prefix hoặc `hasAuthority('ADMIN')` |
| Admin vẫn bị deny ở owner-only | Rule không có ngoại lệ role | Đọc requirement, thêm nhánh OR chỉ nếu được phép |
| HTTP authenticated nhưng method 403 | HTTP chỉ xác thực, method kiểm tra owner/permission | Phân biệt hai tầng |
| Method không bao giờ deny | Method security chưa bật hoặc self-invocation | Bật config, gọi Spring proxy, viết deny test |
| Test bằng `new InvoiceService()` | Không có AOP proxy | Dùng `@SpringBootTest` inject service |
| Dùng imperative `SecurityContextHolder` trong WebFlux | Context gắn subscriber, không thread cố định | Dùng `ReactiveSecurityContextHolder` |
| `@ownerPolicy` không resolve | Sai tên bean hoặc package scan | Đặt `@Component("ownerPolicy")`, test |
| Bean return `Mono<Boolean>` bị xử lý sai | Dùng cơ chế method security cũ/chưa hỗ trợ | `useAuthorizationManager=true`, test đúng version |
| SpEL gọi `.block()` | Blocking event loop | Compose reactive pipeline |
| 403 khi POST dù quyền đúng | Có thể CSRF | Test CSRF token và method HTTP |
| So `owner` input với username vẫn có IDOR | Không kiểm tra owner thực của invoice ID | Query/authorize theo resource và tenant |
| Dùng `@PostAuthorize` sau side effects | Check diễn ra sau thao tác | Kiểm tra quyền trước read/write |
| Lộ authentication trong log | Có thể chứa credentials/token | Chỉ log tín hiệu cần thiết, redact secrets |

### Trình tự debug khuyến nghị

1. Xem HTTP SecurityWebFilterChain nào match; credentials có hợp lệ không?
2. Kiểm tra `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`.
3. Kiểm tra method được gọi trên Spring bean qua proxy, không qua self-invocation.
4. Xác nhận `Authentication.getName()` và type principal thật trong một môi trường test an toàn.
5. In test method arguments dự kiến, không in raw password/token.
6. Kiểm tra tên `@P`, biến `#owner`, `#p0` và thứ tự parameters.
7. Kiểm tra authorities thực sau converter/mapper, `ROLE_` và scope.
8. Nếu cần, tách policy bean và unit test logic theo owner/tenant/resource.
9. Kiểm tra error signal từ StepVerifier trước khi đổ lỗi cho exception handler HTTP.
10. Thêm negative tests để phát hiện chỗ bypass, đặc biệt self-invocation và URL thay đổi owner.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `authentication.name == #owner` so sánh những gì?  
**Trả lời:** So sánh tên caller từ Authentication đã xác thực với **giá trị tham số method** được expose bằng biến `#owner`.

**Câu 2.** `principal.username` có dùng nguyên khi chuyển từ HTTP Basic UserDetails sang JWT không?  
**Trả lời:** Không chắc. Principal JWT có thể không có `username`; kiểm tra converter hoặc dùng `authentication.name` theo identity policy.

**Câu 3.** Vì sao `#owner` có thể null/không resolve dù method có tham số `String owner`?  
**Trả lời:** Tên parameter có thể không được discover từ bytecode. Dùng `@P("owner")` hoặc bật `-parameters`, test trên build thật.

**Câu 4.** `#p0` khác `#owner` như thế nào?  
**Trả lời:** `#p0` dựa vị trí đầu tiên; `#owner` dựa tên. Nếu refactor đổi thứ tự args, `#p0` có thể trỏ nhầm.

**Câu 5.** `hasRole('ADMIN') or #owner == authentication.name` có bắt admin phải là owner không?  
**Trả lời:** Không. OR cho phép admin hoặc owner. Muốn AND phải viết AND và được business yêu cầu.

**Câu 6.** User Alice gọi `invoice("alice","id-of-bob")` thì expression so owner với username đã đủ chống IDOR chưa?  
**Trả lời:** Chưa. Chủ thực của invoice phải được kiểm tra từ database theo ID và tenant, không tin owner do client tự khai.

**Câu 7.** Cần gì để `@PreAuthorize` hoạt động trên WebFlux service?  
**Trả lời:** Reactive method security được bật, method reactive, Spring bean được AOP proxy và lời gọi đi qua proxy trong subscription có Authentication phù hợp.

**Câu 8.** Vì sao `@WithMockUser` không đủ xác minh HTTP Basic password?  
**Trả lời:** Mock user cấp sẵn Authentication, bỏ qua converter/password verifier. Cần WebTestClient gửi Basic header thật.

**Câu 9.** `@ownerPolicy.canView(authentication,#owner)` có thể trả `Mono<Boolean>` không?  
**Trả lời:** Có trong reactive method security dựa trên AuthorizationManager phiên bản được hỗ trợ; không gọi `block()`.

**Câu 10.** Vì sao method không deny khi gọi `this.securedMethod()`?  
**Trả lời:** Self-invocation có thể bypass Spring AOP proxy, cần bảo vệ entrypoint hoặc tách bean.

**Câu 11.** `@P` nằm ở package nào?  
**Trả lời:** `org.springframework.security.access.method.P`.

**Câu 12.** Vì sao đã login đúng vẫn nhận HTTP 403?  
**Trả lời:** HTTP authentication thành công nhưng method hoặc HTTP authorization từ chối vì owner/authority/CSRF hoặc policy khác.

**Câu 13.** Có nên gọi `SecurityContextHolder.getContext()` từ WebFlux request rồi lưu ThreadLocal không?  
**Trả lời:** Không. Reactive security sử dụng Reactor Context và `ReactiveSecurityContextHolder` gắn với subscription.

**Câu 14.** `@PostAuthorize` có thay thế mọi kiểm tra quyền trước mutation không?  
**Trả lời:** Không. Với side effects, kiểm tra sau method quá muộn; phải gate trước khi ghi dữ liệu hoặc gọi dịch vụ ngoài.

## 16. Checklist và tài liệu đọc thêm

- [ ] Đã bật `@EnableReactiveMethodSecurity` cùng cơ chế AuthorizationManager phù hợp.
- [ ] Method trả `Mono`/`Flux` và được gọi qua Spring bean/proxy.
- [ ] Không dùng ThreadLocal/imperative SecurityContextHolder để suy danh tính reactive.
- [ ] Chọn `authentication.name`/identity key đáng tin thay vì giả định mọi principal có `username`.
- [ ] Đã dùng `@P` hoặc `-parameters` cho named expressions; có test positional `#p0`.
- [ ] Rule AND/OR được rà soát đúng business requirements; `ROLE_` và authorities được map chuẩn.
- [ ] Có test âm tính cho owner mismatch, thiếu quyền, admin không được phép vượt rule owner-only.
- [ ] Nếu dùng bean SpEL, không block I/O; policy được test độc lập.
- [ ] Owner/tenant của invoice được kiểm tra từ storage theo ID, không từ path params tự khai.
- [ ] HTTP 401 và method 403 được test riêng bằng WebTestClient.
- [ ] StepVerifier xác minh Context riêng giữa subscriptions.
- [ ] Không để self-invocation/constructor `new` làm bypass AOP.
- [ ] Đã cân nhắc CSRF với browser POST và kiểm tra quyền trước side effects.
- [ ] Không log credentials, JWT, raw SecurityContext hoặc thông tin nhạy cảm.

**Tóm tắt:** Trong Spring Security reactive, `authentication` là danh tính được framework cung cấp; `principal` là object bên trong Authentication có kiểu phụ thuộc authentication mechanism; `#owner`/`#p0` chỉ là **giá trị tham số** method. `@PreAuthorize` cho phép kết hợp các nguồn này thành policy rõ ràng nhưng **không tự chứng minh ownership của resource thực**. Muốn an toàn phải dùng method security, đúng Reactor Context, proxy, test âm tính và truy vấn owner/tenant đáng tin cậy.

**Tài liệu chính thức:**

- Spring Security 6.5 – EnableReactiveMethodSecurity: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 – Reactive Web Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – Method Security Expressions and Parameters: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 – `@PreAuthorize`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html
- Spring Security 6.5 – `@P` annotation: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/method/P.html
- Spring Security 6.5 – ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security 6.5 – Testing reactive method security: https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html
- Spring Security 6.5 – WebTestClient test setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- OWASP API Security – Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- Spring Boot 3.5.16 release and end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
