# AuthorityAuthorizationManager và AuthenticatedAuthorizationManager trong Spring Security

## 1. Bài toán: quyền được cấp và trạng thái đăng nhập là hai điều khác nhau

Một ứng dụng có các API sau:

- `GET /api/reports`: chỉ user có quyền `report:read`.
- `GET /api/admin`: chỉ user có role `ADMIN`.
- `GET /api/me`: ai đã xác thực cũng được xem.
- `GET /api/sensitive`: cần xác thực **đầy đủ**, không chấp nhận phiên remember-me.
- `GET /api/export`: vừa cần quyền `report:export`, vừa cần xác thực đầy đủ.

Những yêu cầu này được giải quyết bằng hai nhóm chính sách có ý nghĩa khác nhau:

- **`AuthorityAuthorizationManager<T>`**: kiểm tra các `GrantedAuthority` trong `Authentication`, ví dụ `report:read` hoặc `ROLE_ADMIN`.
- **`AuthenticatedAuthorizationManager<T>`**: phân loại trạng thái của `Authentication`, ví dụ anonymous, đã xác thực, remember-me hoặc fully authenticated.

Cả hai triển khai giao diện **`AuthorizationManager<T>`** trong Spring Security. Việc sử dụng sẵn các lớp này thường đủ cho các yêu cầu role/authority và trạng thái đăng nhập, trong khi một chính sách phụ thuộc owner, tenant, thuộc tính bản ghi hoặc dữ liệu nghiệp vụ có thể cần thêm `AuthorizationManager` riêng.

**Mục tiêu học tập:** hiểu luồng quyết định ủy quyền, phân biệt role với authority và remember-me với fully authenticated, sử dụng các factory method đúng, kết hợp các manager, tích hợp vào `SecurityFilterChain`, viết kiểm thử được cả allow/deny và nhận biết những ranh giới mà hai manager không kiểm tra.

Bài viết dùng API của **Spring Security 6.5.x**, Java 17 và Spring Boot 3.5.x cho ví dụ chạy đầy đủ. Spring Security 7.x có thêm các tiện ích factory; đừng suy luận mọi API xuất hiện ở bản mới đều đã có trong 6.5.

## 2. Nền tảng: AuthorizationManager<T> nhận dữ liệu gì?

Trong ứng dụng servlet, luồng thông thường là:

```text
HTTP request
  → SecurityFilterChain
  → Authentication filter: lấy/xây Authentication
  → AuthorizationFilter
      → chọn rule đầu tiên khớp request
      → AuthorizationManager<RequestAuthorizationContext>
          → Supplier<Authentication>
          → RequestAuthorizationContext
          → AuthorizationResult: granted / denied
      → cho request tiếp tục hoặc từ chối
  → Controller → Service
```

Spring Security không bắt mọi ứng dụng tự xây manager mới; khi viết `.hasRole("ADMIN")` hoặc `.authenticated()` trong DSL `authorizeHttpRequests`, framework đã tạo/ghép các thành phần ủy quyền cần thiết. Khi muốn dùng manager một cách tường minh, dùng `.access(AuthorizationManager)`.

Giao diện có generic parameter `T` để biểu thị **đối tượng đang được ủy quyền**. Với servlet request thông thường, `T` là `RequestAuthorizationContext`; với ủy quyền trên method, `T` có thể là `MethodInvocation`. Hai manager đang học **chủ yếu đọc Authentication**, nên có thể tái sử dụng theo nhiều kiểu `T`, nhưng điều đó không có nghĩa chúng tự kiểm tra URL, owner hay tham số phương thức.

Trong Spring Security 6.5, phương thức nên sử dụng khi gọi trực tiếp là:

```java
AuthorizationResult result = manager.authorize(authenticationSupplier, object);
boolean allowed = result != null && result.isGranted();
```

Đây là **mã minh họa API**, cần manager, supplier và object cùng kiểu trong chương trình thực. `AuthorizationResult` có method `isGranted()`. `AuthorizationManager#authorize(...)` xuất hiện từ Spring Security 6.4; `check(...)` đã được đánh dấu deprecated trong dòng 6.5. Với manager có thể abstain, kết quả có thể là `null`. Hai built-in manager này thông thường trả quyết định allow/deny rõ ràng cho Authentication hợp lệ.

`Supplier<Authentication>` cho phép framework **trì hoãn việc truy xuất Authentication** đến khi cần; không gọi `supplier.get()` chỉ để kiểm tra một request `permitAll`. Khi viết manager tự định nghĩa, đừng giả định đối tượng cần xét đã chắc chắn có những thuộc tính nghiệp vụ mà bạn muốn nếu kiểu `T` không cung cấp chúng.

## 3. AuthorityAuthorizationManager: kiểm tra GrantedAuthority

### 3.1. GrantedAuthority là gì?

Một `Authentication` chứa danh sách đối tượng `GrantedAuthority`. Mỗi authority thường có tên chuỗi, ví dụ:

```text
User: alice
Authorities:
  ROLE_ADMIN
  report:read
  report:export
```

`GrantedAuthority#getAuthority()` là giá trị được so khớp. Ví dụ `SimpleGrantedAuthority("report:read")` mang chính xác chuỗi `report:read`. `AuthorityAuthorizationManager` không tự đọc database phân quyền hay tìm nhóm trong JWT; nó xét **authority đã được đưa vào Authentication** bởi authentication provider, converter hoặc security setup.

Factory methods thiết yếu của `AuthorityAuthorizationManager`:

| Factory | Yêu cầu | Ví dụ authority cần có |
|---|---|---|
| `hasAuthority("report:read")` | Có đúng authority này | `report:read` |
| `hasAnyAuthority("read", "write")` | Có **ít nhất một** trong các authority | `read` hoặc `write` |
| `hasRole("ADMIN")` | Theo factory mặc định, có role đã thêm tiền tố `ROLE_` | `ROLE_ADMIN` |
| `hasAnyRole("ADMIN", "SUPPORT")` | Có ít nhất một role đã thêm `ROLE_` | `ROLE_ADMIN` hoặc `ROLE_SUPPORT` |

Cả `hasAnyAuthority` và `hasAnyRole` biểu diễn **OR**, không phải yêu cầu tất cả quyền. Để biểu diễn AND, dùng `AuthorizationManagers.allOf(...)`, hoặc policy cụ thể.

### 3.2. Role và authority có thực sự giống nhau?

Role thường được lưu bằng một authority có tiền tố `ROLE_`. Ở các factory tĩnh này:

```java
AuthorityAuthorizationManager.hasRole("ADMIN");
AuthorityAuthorizationManager.hasAuthority("ROLE_ADMIN");
```

Với cấu hình mặc định, cả hai có thể chấp nhận người có `ROLE_ADMIN`. Nhưng ý nghĩa của đối số khác nhau:

- `hasRole("ADMIN")` tự thêm `ROLE_` trước khi so khớp.
- `hasAuthority("ROLE_ADMIN")` dùng nguyên chuỗi được cung cấp.
- `hasAuthority("ADMIN")` chỉ chấp nhận authority đúng `ADMIN`, không tự thêm `ROLE_`.
- `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")` là **cách dùng sai** và factory này có thể ném `IllegalArgumentException` do tên đã có tiền tố.

Cần phân biệt API khác của framework có hỗ trợ custom role prefix (ví dụ `GrantedAuthorityDefaults`, factory cấu hình riêng) với lệnh gọi trực tiếp `AuthorityAuthorizationManager.hasRole(...)`, vốn được định nghĩa với tiền tố `ROLE_`. Nếu dự án dùng tiền tố tùy biến, kiểm tra chính xác manager đang được tạo; có thể chọn `hasAuthority("MYROLE_ADMIN")` hoặc dùng factory phù hợp thay vì mặc định giả định `ROLE_`.

### 3.3. Quyết định minh họa

Giả sử Authentication của `alice` có `ROLE_ADMIN` và `report:read`:

| Quy tắc | Kết quả | Lý do |
|---|---|---|
| `hasRole("ADMIN")` | Allow | Có `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Allow | So khớp chính xác |
| `hasAuthority("ADMIN")` | Deny | Không có authority `ADMIN` |
| `hasAuthority("report:read")` | Allow | Có `report:read` |
| `hasAnyAuthority("report:write", "report:read")` | Allow | Có một quyền được yêu cầu |
| `hasAnyRole("SUPPORT", "USER")` | Deny | Không có `ROLE_SUPPORT` hay `ROLE_USER`, nếu không cấu hình role hierarchy |

Quy tắc kiểm tra **quyền hiện diện trong Authentication**; không tự xác minh dữ liệu đã được fetch, ownership của record hay tenant. Một user có `report:read` ở tenant A không vì thế tự động được đọc report thuộc tenant B.

### 3.4. Vai trò của RoleHierarchy

Trong hệ thống có `ROLE_ADMIN > ROLE_USER`, một manager có thể được cấu hình để mở rộng quyền reachable từ hierarchy. API có method `setRoleHierarchy(...)`:

```java
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

RoleHierarchy hierarchy =
    RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > ROLE_USER");

AuthorityAuthorizationManager<RequestAuthorizationContext> manager =
    AuthorityAuthorizationManager.hasRole("USER");
manager.setRoleHierarchy(hierarchy);
```

Đây là **đoạn minh họa cấu hình**, cần được đặt trong method/bean thích hợp. User có `ROLE_ADMIN` có thể được manager này chấp nhận khi yêu cầu `ROLE_USER` nhờ hierarchy. Manager được tạo bằng factory tĩnh mặc định dùng `NullRoleHierarchy` nếu chưa gọi `setRoleHierarchy`; **đừng cho rằng một bean RoleHierarchy tự động được gắn vào mọi manager mà bạn tự `new` hoặc tạo bằng factory tĩnh**. Khi dùng DSL/factory/framework khác, cơ chế truyền cấu hình có thể khác, cần test chính sách cuối cùng.

Role hierarchy mô tả quan hệ role, không thay thế tenant boundary hay phân quyền trên từng record.

## 4. AuthenticatedAuthorizationManager: trạng thái xác thực

`AuthenticatedAuthorizationManager<T>` giải quyết câu hỏi “loại Authentication hiện tại có đủ điều kiện không?” thông qua `AuthenticationTrustResolver`, theo mặc định là `AuthenticationTrustResolverImpl`.

Factory methods:

| Factory | Ý nghĩa |
|---|---|
| `authenticated()` | User đã xác thực theo trust resolver; **không phải anonymous** |
| `fullyAuthenticated()` | Xác thực đầy đủ, không phải anonymous hoặc remember-me |
| `rememberMe()` | Authentication có nguồn gốc remember-me |
| `anonymous()` | Authentication được đánh dấu anonymous |

**Chú ý:** `authenticated()` thường **chấp nhận remember-me**. `fullyAuthenticated()` thường **không chấp nhận remember-me**. Dùng `fullyAuthenticated()` cho thao tác yêu cầu xác nhận danh tính mạnh hơn, ví dụ thay đổi mật khẩu hoặc phê duyệt lệnh nhạy cảm, nhưng điều này **không tự kiểm tra MFA hay mức độ xác thực theo tiêu chuẩn riêng của ứng dụng**.

Bảng minh họa với các token điển hình, chưa có custom `AuthenticationTrustResolver`:

| Trạng thái | `anonymous()` | `authenticated()` | `fullyAuthenticated()` | `rememberMe()` |
|---|---:|---:|---:|---:|
| AnonymousAuthenticationToken | ✓ | ✗ | ✗ | ✗ |
| RememberMeAuthenticationToken | ✗ | ✓ | ✗ | ✓ |
| UsernamePasswordAuthenticationToken đã được xác thực | ✗ | ✓ | ✓ | ✗ |

`Authentication#isAuthenticated()` là một cờ trên token; tự đọc cờ này không đủ để phân biệt anonymous, remember-me và fully authenticated. Ví dụ `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` về mặt cấu trúc token, nhưng trust resolver vẫn nhận diện nó là anonymous. Vì vậy đừng tự viết policy kiểu `authentication.isAuthenticated()` rồi coi tương đương `AuthenticatedAuthorizationManager.authenticated()`.

### 4.1. “Đã đăng nhập” không đồng nghĩa có quyền

User `bob` đăng nhập bằng username/password nhưng chỉ có `ROLE_USER`:

- `AuthenticatedAuthorizationManager.authenticated()` → allow.
- `AuthenticatedAuthorizationManager.fullyAuthenticated()` → allow.
- `AuthorityAuthorizationManager.hasRole("ADMIN")` → deny.
- `AuthorityAuthorizationManager.hasAuthority("report:read")` → deny.

Ngược lại, một Authentication được tạo đúng chuẩn mà có authority cần thiết vẫn phải đáp ứng **trạng thái xác thực mong muốn** nếu chính sách yêu cầu điều đó. Với hành động nhạy cảm, kết hợp cả hai thay vì chỉ kiểm tra một vế.

### 4.2. Các giới hạn cần biết

`AuthenticatedAuthorizationManager` không tự kiểm tra:
- Password vừa nhập lại hay không, user đã vượt qua MFA chưa.
- JWT `acr`, `amr` hoặc thời điểm `auth_time` có đáp ứng chính sách step-up hay không.
- User đã bị khóa trong hệ thống nghiệp vụ nhưng token/session vẫn còn hợp lệ.
- User có quyền sửa record thuộc một tenant khác hay không.

Những yêu cầu này cần authentication process và/hoặc custom `AuthorizationManager` có thêm dữ liệu tin cậy. Có thể thay `AuthenticationTrustResolver` qua `setTrustResolver(...)` nhưng không nên sửa trust resolver chỉ để giấu một chính sách nghiệp vụ; thay vào đó định nghĩa policy được kiểm thử rõ ràng.

## 5. So sánh trực tiếp: khi nào chọn manager nào?

| Yêu cầu nghiệp vụ | Manager phù hợp | Ví dụ |
|---|---|---|
| Có quyền đọc báo cáo | `AuthorityAuthorizationManager` | `hasAuthority("report:read")` |
| Là admin hoặc support | `AuthorityAuthorizationManager` | `hasAnyRole("ADMIN", "SUPPORT")` |
| Đăng nhập là đủ | `AuthenticatedAuthorizationManager` | `authenticated()` |
| Không chấp nhận remember-me | `AuthenticatedAuthorizationManager` | `fullyAuthenticated()` |
| Chỉ phiên remember-me | `AuthenticatedAuthorizationManager` | `rememberMe()` |
| Chỉ người chưa đăng nhập | `AuthenticatedAuthorizationManager` | `anonymous()` |
| Đã xác thực đầy đủ **và** có quyền export | **Kết hợp hai manager** | `AuthorizationManagers.allOf(...)` |
| Có quyền đọc **một hóa đơn cụ thể** | Manager nghiệp vụ cần thêm object/context | So sánh tenant và owner từ DB tin cậy |

Một nguyên tắc thiết kế dễ nhớ: **“Ai đang đăng nhập và ở mức nào?” → AuthenticatedAuthorizationManager. “Được cấp quyền/role nào?” → AuthorityAuthorizationManager. “Có quyền trên đối tượng cụ thể này không?” → policy nghiệp vụ.**

## 6. Kết hợp nhiều AuthorizationManager

Spring Security có tiện ích `AuthorizationManagers` trong package `org.springframework.security.authorization`.

**Yêu cầu đồng thời (AND)**:

```java
AuthorizationManagers.allOf(
    AuthenticatedAuthorizationManager.fullyAuthenticated(),
    AuthorityAuthorizationManager.hasAuthority("report:export")
)
```

**Chấp nhận một trong các quyền (OR)**:

```java
AuthorizationManagers.anyOf(
    AuthorityAuthorizationManager.hasRole("ADMIN"),
    AuthorityAuthorizationManager.hasAuthority("support:read")
)
```

Hai đoạn trên là **biểu thức tạo manager**, đặt trong vị trí mong đợi `AuthorizationManager<T>` để Java suy ra generic `T`. Với AND, phải thỏa các điều kiện; với OR, đủ một điều kiện hợp lệ. Chú ý thứ tự evaluation và trường hợp manager custom trả `null` (abstain) khi thiết kế tổ hợp phức tạp; đừng coi `null` là allow. Với hai built-in manager ở đây, kết quả thông thường là rõ ràng.

Có thể dùng DSL ngắn khi không cần tái sử dụng manager:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .requestMatchers("/api/me").authenticated()
    .anyRequest().denyAll()
);
```

Đây là **đoạn cấu hình trong method SecurityFilterChain** chứ chưa phải chương trình độc lập. DSL tự tạo/delegate manager, giúp code ngắn. Khi cần ghép điều kiện, tái sử dụng policy hoặc cấu hình hierarchy/trust resolver cụ thể, `.access(...)` với manager tường minh rõ ràng hơn.

## 7. Ví dụ đầy đủ: Spring Boot 3.5.6, Java 17, HTTP endpoints và MockMvc

Dự án không dùng database, để tập trung vào logic ủy quyền. Dùng Spring Boot 3.5.6 (quản lý Spring Security 6.5.x), Maven, Java 17 và `spring-security-test`. Ví dụ này dùng `@RestController` và chỉ các GET endpoint nên không cần thêm ngoại lệ CSRF cho thao tác ghi.

Cấu trúc file:

```text
authz-manager-demo/
  pom.xml
  src/main/java/com/example/authz/AuthzManagerApplication.java
  src/main/java/com/example/authz/SecurityConfig.java
  src/main/java/com/example/authz/DemoController.java
  src/test/java/com/example/authz/SecurityConfigTest.java
```

### 7.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>authz-manager-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 7.2. Application

**`src/main/java/com/example/authz/AuthzManagerApplication.java`**

```java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzManagerApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzManagerApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain sử dụng hai manager

**`src/main/java/com/example/authz/SecurityConfig.java`**

```java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin")
                    .access(AuthorityAuthorizationManager.hasRole("ADMIN"))

                .requestMatchers("/api/reports")
                    .access(AuthorityAuthorizationManager.hasAuthority("report:read"))

                .requestMatchers("/api/ops")
                    .access(AuthorityAuthorizationManager.hasAnyRole("ADMIN", "OPS"))

                .requestMatchers("/api/me")
                    .access(AuthenticatedAuthorizationManager.authenticated())

                .requestMatchers("/api/sensitive")
                    .access(AuthenticatedAuthorizationManager.fullyAuthenticated())

                .requestMatchers("/api/remembered")
                    .access(AuthenticatedAuthorizationManager.rememberMe())

                .requestMatchers("/api/guest")
                    .access(AuthenticatedAuthorizationManager.anonymous())

                .requestMatchers("/api/export")
                    .access(AuthorizationManagers.allOf(
                        AuthenticatedAuthorizationManager.fullyAuthenticated(),
                        AuthorityAuthorizationManager.hasAuthority("report:export")
                    ))

                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Điểm cần đọc trong cấu hình:
1. `.requestMatchers(...)` quyết định **URL nào** đi tới policy.
2. `.access(...)` nhận một `AuthorizationManager<RequestAuthorizationContext>`; Java suy ra generic từ vị trí gọi.
3. `AuthorityAuthorizationManager` kiểm tra authority trong Authentication.
4. `AuthenticatedAuthorizationManager` phân biệt anonymous, remember-me và fully authenticated.
5. `AuthorizationManagers.allOf(...)` yêu cầu cả hai điều kiện của `/api/export`.
6. `.anyRequest().denyAll()` phủ đường dẫn còn lại theo nguyên tắc default-deny.
7. `.httpBasic(...)` cung cấp một cơ chế xác thực HTTP Basic cho ứng dụng thử. Trong triển khai thật có thể thay bằng login session, OAuth2 resource server/JWT, hoặc cơ chế tổ chức chọn. Manager ủy quyền không phụ thuộc trực tiếp vào cách password/JWT được xác minh.

Lưu ý thứ tự matcher: Spring áp dụng **quy tắc đầu tiên khớp**. Đặt pattern tổng quát như `/api/**` lên đầu có thể che các rule chi tiết phía sau. Endpoint `/api/guest` cố ý chỉ cho anonymous để minh họa API `anonymous()`; trang đăng ký/tài liệu công khai thường phù hợp với `permitAll()` hơn.

### 7.4. Controller minh họa

**`src/main/java/com/example/authz/DemoController.java`**

```java
package com.example.authz;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "reports";
    }

    @GetMapping("/api/ops")
    public String ops() {
        return "ops";
    }

    @GetMapping("/api/me")
    public String me() {
        return "me";
    }

    @GetMapping("/api/sensitive")
    public String sensitive() {
        return "sensitive";
    }

    @GetMapping("/api/remembered")
    public String remembered() {
        return "remembered";
    }

    @GetMapping("/api/guest")
    public String guest() {
        return "guest";
    }

    @GetMapping("/api/export")
    public String export() {
        return "export";
    }
}
```

Các endpoint trả chuỗi cố định để kiểm thử chính sách độc lập với quyền sở hữu tài liệu và cấu trúc database. Đây là ứng dụng học tập, chưa có API business thực và không cho phép thao tác ghi.

### 7.5. MockMvc kiểm thử allow/deny, anonymous và remember-me

**`src/test/java/com/example/authz/SecurityConfigTest.java`**

```java
package com.example.authz;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {
    @Autowired
    MockMvc mvc;

    private static RememberMeAuthenticationToken remembered(String authority) {
        return new RememberMeAuthenticationToken(
            "demo-key",
            "saved-user",
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminRoleGrantsAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "ADMIN")
    void rawAdminAuthorityDoesNotEqualRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void exactReportAuthorityGrantsRead() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void wrongReportAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPS")
    void opsRoleSatisfiesAnyRole() throws Exception {
        mvc.perform(get("/api/ops"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void unrelatedRoleDoesNotSatisfyAnyRole() throws Exception {
        mvc.perform(get("/api/ops"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void authenticatedUserCanOpenMe() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousUserIsChallengedForMe() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void normalLoginIsFullyAuthenticated() throws Exception {
        mvc.perform(get("/api/sensitive"))
            .andExpect(status().isOk());
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        mvc.perform(get("/api/sensitive")
                .with(authentication(remembered("ROLE_USER"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberMeIsStillAuthenticatedForMe() throws Exception {
        mvc.perform(get("/api/me")
                .with(authentication(remembered("ROLE_USER"))))
            .andExpect(status().isOk());
    }

    @Test
    void rememberMeCanOpenRememberMeOnlyEndpoint() throws Exception {
        mvc.perform(get("/api/remembered")
                .with(authentication(remembered("ROLE_USER"))))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void normalLoginDoesNotCountAsRememberMe() throws Exception {
        mvc.perform(get("/api/remembered"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCanOpenGuestOnlyEndpoint() throws Exception {
        mvc.perform(get("/api/guest"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void authenticatedUserDoesNotCountAsAnonymous() throws Exception {
        mvc.perform(get("/api/guest"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:export")
    void fullyAuthenticatedExporterIsAllowed() throws Exception {
        mvc.perform(get("/api/export"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readPermissionDoesNotGrantExport() throws Exception {
        mvc.perform(get("/api/export"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberedExporterLacksFullAuthentication() throws Exception {
        mvc.perform(get("/api/export")
                .with(authentication(remembered("report:export"))))
            .andExpect(status().isForbidden());
    }
}
```

Giải thích hai công cụ test:

- `@WithMockUser` tạo security context với Authentication kiểm thử. `roles = "ADMIN"` tạo authority `ROLE_ADMIN`; `authorities = "ADMIN"` tạo đúng `ADMIN`, không thêm prefix.
- `RememberMeAuthenticationToken` tạo trạng thái remember-me cho test. Test dùng request post-processor `authentication(...)` để đặt Authentication giả lập; **không** khẳng định đã triển khai cookie remember-me, password hoặc login thật.

Chạy ở thư mục có `pom.xml`:

```bash
mvn test
```

**Kỳ vọng theo thiết kế:** 18 test pass; các request allow trả HTTP 200, user đăng nhập nhưng thiếu quyền trả 403, request anonymous vào endpoint yêu cầu xác thực trả 401 nhờ HTTP Basic entry point. Dòng log Maven/Surefire không cố định và kết quả kỳ vọng này cần được xác nhận bằng chạy thực tế trên dependency đã khóa. Bài học không khẳng định Maven đã được thực thi.

Có thể chạy ứng dụng bằng:

```bash
mvn spring-boot:run
```

Không khai báo user/password thực trong ví dụ. Nếu cần thử HTTP Basic thủ công, cung cấp user qua cấu hình môi trường bảo mật phù hợp; **không dùng tài khoản được tự sinh trong log làm cơ chế vận hành**. Với bài kiểm thử phân quyền, `MockMvc + @WithMockUser` đã cung cấp danh tính kiểm thử có kiểm soát.

### 7.6. Bảng diễn giải kết quả chính

| Endpoint | Giả lập người gọi | Kỳ vọng |
|---|---|---|
| `/api/admin` | `ROLE_ADMIN` | 200 |
| `/api/admin` | Authority `ADMIN` (không có `ROLE_ADMIN`) | 403 |
| `/api/reports` | `report:read` | 200 |
| `/api/reports` | Chỉ `report:write` | 403 |
| `/api/me` | Đăng nhập bình thường | 200 |
| `/api/me` | Anonymous | 401 |
| `/api/me` | Remember-me | 200 |
| `/api/sensitive` | Remember-me | 403 |
| `/api/remembered` | Remember-me | 200 |
| `/api/remembered` | Đăng nhập đầy đủ | 403 |
| `/api/guest` | Anonymous | 200 |
| `/api/guest` | Đăng nhập đầy đủ | 403 |
| `/api/export` | Fully authenticated + `report:export` | 200 |
| `/api/export` | Chỉ `report:read` | 403 |
| `/api/export` | Remember-me + `report:export` | 403 |

Cần phân biệt **401** và **403** theo cấu hình exception handling: khi chưa xác thực và bị chặn, HTTP Basic thường trả 401 để yêu cầu xác thực; khi đã xác thực nhưng không có quyền, thường trả 403. Nếu dùng login form, OAuth2 entry point, custom exception handler hay API gateway, phản hồi HTTP có thể khác. Manager trả quyết định quyền; việc biến quyết định thành response là công việc của filter chain và entry point.

## 8. Kiểm tra AuthorizationManager trực tiếp không cần web server

Có thể unit test manager riêng, không đi qua `SecurityFilterChain`. Dưới đây là **test class bổ sung, chạy được với `pom.xml` ở trên** nếu tạo file như chỉ dẫn.

**`src/test/java/com/example/authz/ManagerUnitTest.java`**

```java
package com.example.authz;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ManagerUnitTest {
    @Test
    void exactAuthorityVsRolePrefix() {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
            "alice", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
        );

        AuthorityAuthorizationManager<Object> role =
            AuthorityAuthorizationManager.hasRole("ADMIN");
        AuthorityAuthorizationManager<Object> rawAuthority =
            AuthorityAuthorizationManager.hasAuthority("ADMIN");

        assertTrue(role.authorize(() -> alice, new Object()).isGranted());
        assertFalse(rawAuthority.authorize(() -> alice, new Object()).isGranted());
    }

    @Test
    void configuredRoleHierarchyGrantsImpliedRole() {
        Authentication admin = UsernamePasswordAuthenticationToken.authenticated(
            "admin", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
        );

        AuthorityAuthorizationManager<Object> userRule =
            AuthorityAuthorizationManager.hasRole("USER");
        assertFalse(userRule.authorize(() -> admin, new Object()).isGranted());

        userRule.setRoleHierarchy(
            RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > ROLE_USER")
        );
        assertTrue(userRule.authorize(() -> admin, new Object()).isGranted());
    }

    @Test
    void rememberMeIsAuthenticatedButNotFullyAuthenticated() {
        Authentication token = new RememberMeAuthenticationToken(
            "demo-key", "alice",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

        AuthenticatedAuthorizationManager<Object> authenticated =
            AuthenticatedAuthorizationManager.authenticated();
        AuthenticatedAuthorizationManager<Object> fully =
            AuthenticatedAuthorizationManager.fullyAuthenticated();
        AuthenticatedAuthorizationManager<Object> remembered =
            AuthenticatedAuthorizationManager.rememberMe();

        assertTrue(authenticated.authorize(() -> token, new Object()).isGranted());
        assertFalse(fully.authorize(() -> token, new Object()).isGranted());
        assertTrue(remembered.authorize(() -> token, new Object()).isGranted());
    }
}
```

Với file này, `mvn test` dự kiến chạy **21 test** (18 test HTTP + 3 test unit), không có test thất bại nếu môi trường và dependency đúng như mô tả. Các test dùng `authorize(...)` theo API 6.4+ thay cho `check(...)` deprecated.

Unit test trực tiếp rất hữu ích để kiểm tra một rule đơn lẻ. Tuy nhiên, nó **không** chứng minh matcher order, authentication filters, remember-me cookie hoặc exception translation trong ứng dụng web. Vì thế nên giữ cả unit test và integration test ở các đường nhạy cảm.

## 9. Dùng hai manager ở đâu ngoài HTTP?

`AuthorityAuthorizationManager<T>` và `AuthenticatedAuthorizationManager<T>` là các implementation generic của `AuthorizationManager<T>`. Với `T = MethodInvocation`, chúng có thể tham gia một advisor custom dành cho method security; tuy nhiên **`@PreAuthorize` sử dụng cơ chế Method Security expression manager riêng** và không có nghĩa mọi `@PreAuthorize` trực tiếp gọi hai class này.

Ví dụ một đoạn cấu hình method security phổ biến hơn:

```java
@PreAuthorize("hasRole('ADMIN') or hasAuthority('report:read')")
public Report readReport(long reportId) {
    return repository.findById(reportId).orElseThrow();
}
```

Đây là **mẫu service**, cần `@EnableMethodSecurity`, entity/repository và imports; nó không phải file độc lập. Với Method Security, hãy hiểu vai trò của `PreAuthorizeAuthorizationManager`/SpEL, AOP proxy và việc tham chiếu method arguments.

Khi cần một chính sách sử dụng cả request context lẫn record id, hai built-in manager chỉ là khối ghép nhỏ. Bạn có thể triển khai:

```java
public final class TenantPolicy implements AuthorizationManager<RequestAuthorizationContext> {
    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {
        // Đọc user từ authentication, tenant/id từ context/request,
        // rồi kiểm tra quyền theo dữ liệu nghiệp vụ tin cậy.
        return new AuthorizationDecision(false);
    }
}
```

Đây là **sườn minh họa cần hoàn thiện**, không phải chính sách triển khai được: phải thêm imports `Authentication`, `Supplier`, `AuthorizationResult`, `AuthorizationDecision`, `RequestAuthorizationContext`, định nghĩa policy thực và trả quyết định đúng. Dòng `false` chỉ thể hiện **fail closed mặc định** khi chưa có quyết định hợp lệ; không thay cho một hàm ủy quyền thực tế.

Ở dự án đã có rule HTTP, có thể áp dụng manager custom qua `.requestMatchers("/tenant/**").access(tenantPolicy)`, đồng thời giữ nguyên các chính sách role và authentication khác. Nếu không có kiểm tra quyền tại service/data boundary, một luồng gọi repository hoặc message consumer khác có thể vượt qua HTTP rule.

## 10. Các bẫy quan trọng và cách sửa

### 10.1. Đánh đồng authenticated với được phép làm mọi việc

`authenticated()` chỉ yêu cầu trạng thái đã xác thực; nó không biết quyền `payment:approve`, tenant, owner, account suspended hoặc mức MFA. Với endpoint nhạy cảm, thêm `hasAuthority(...)` hoặc policy nghiệp vụ và test cả người dùng có quyền lẫn thiếu quyền.

### 10.2. Nhầm String role, authority và JWT scope

Một JWT converter có thể tạo authority dạng `SCOPE_reports.read`, trong khi policy lại đòi `report:read`. Hai chuỗi không giống nhau, nên bị từ chối. Hãy thiết kế và kiểm tra mapping từ claims JWT, roles database hoặc nhóm LDAP sang `GrantedAuthority`. `AuthorityAuthorizationManager` không tự dịch tên scope/role.

### 10.3. Gửi "ROLE_ADMIN" cho hasRole

Với `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")`, factory tĩnh tự thêm `ROLE_` và có thể từ chối tham số đã có prefix. Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`.

### 10.4. Giả định @WithMockUser mô phỏng remember-me

`@WithMockUser` mặc định là authenticated user đầy đủ. Muốn kiểm tra `rememberMe()`, dùng `RememberMeAuthenticationToken`, integration test thực hoặc test luồng cookie remember-me; khi kiểm tra HTTP FilterChain, đảm bảo post-processor thực sự đi qua Spring Security test integration.

### 10.5. Quên custom RoleHierarchy khi tự tạo manager

`AuthorityAuthorizationManager.hasRole("USER")` độc lập mặc định không biết ADMIN có bao hàm USER. Khi manager được tạo trực tiếp, đặt `setRoleHierarchy(...)` nếu đó là mô hình tổ chức. Đối với cấu hình DSL/factory toàn cục, xem cơ chế áp dụng hierarchy của phiên bản đang dùng.

### 10.6. Dùng anonymous-only như public endpoint

`AuthenticatedAuthorizationManager.anonymous()` **khác** `permitAll()`. Một endpoint anonymous-only thường từ chối cả user đã đăng nhập. Với landing page và tài liệu công khai cần truy cập cho mọi người, dùng `permitAll()` sẽ đúng hơn.

### 10.7. Cho remember-me vào endpoint rủi ro cao

Remember-me được thiết kế cho trải nghiệm tiếp tục phiên, thường có mức đảm bảo khác tương tác đăng nhập đầy đủ. Với xuất dữ liệu nhạy cảm, đổi password, thanh toán, dùng `fullyAuthenticated()` rồi bổ sung policy step-up/MFA nếu cần. Đừng coi `fullyAuthenticated` tự kiểm tra MFA.

### 10.8. Tin vào HTTP 401/403 mà bỏ qua kết quả bên trong

Manager cấp phép hoặc từ chối trước controller khi đặt trong filter chain; các background job, service gọi trực tiếp hoặc phương thức nội bộ không phải tự nhiên được chặn bởi HTTP rule. Thêm kiểm tra tại service hoặc tầng dữ liệu cho nghiệp vụ cần bất biến bảo mật.

### 10.9. Tự gọi check() theo thói quen cũ

Trong Spring Security 6.5, `AuthorizationManager#check(...)` đã deprecated; API hiện đại là `authorize(...)` trả `AuthorizationResult`. Khi đọc mẫu code cũ, phải xét version đang dùng; đừng ép một API mới vào project cũ chưa có.

### 10.10. Ghép manager theo kiểu OR khi chính sách cần AND

Ví dụ một người có `ROLE_SUPPORT` nhưng không có `report:export` **không nên** được export chỉ vì một nhánh hợp lệ. Kiểm tra thật kỹ lựa chọn `AuthorizationManagers.anyOf` (OR) và `allOf` (AND); bắt buộc viết test về tình huống “đạt một điều kiện nhưng thiếu điều kiện kia”.

### 10.11. Tin vào authority của header do client tự gửi

Server phải tạo `Authentication` từ cơ chế xác thực đáng tin cậy. Header tự khai `X-Role: ADMIN` không phải `GrantedAuthority` trừ khi application có converter/filter xác minh chữ ký/nguồn dữ liệu và ý định sử dụng. Nếu cấu hình thiếu an toàn đưa header vào Authentication mà không xác minh, cả hai manager sẽ kiểm tra trên dữ liệu không đáng tin.

### 10.12. Thứ tự RequestMatcher và đường dẫn ngoài dự kiến

Một rule `/api/**` đặt trước `/api/admin` có thể bắt mọi request và làm rule admin không bao giờ chạy. Xác minh path matcher, HTTP method, servlet path, dispatcher type và `anyRequest().denyAll()` bằng MockMvc/HTTP test.

## 11. Checklist khi đưa vào ứng dụng thật

1. Liệt kê những endpoint cần **quyền cụ thể**, những endpoint chỉ cần **đăng nhập** và những endpoint đòi **xác thực đầy đủ**.
2. Thống nhất tên authority/role, tiền tố `ROLE_` và quy tắc ánh xạ claims hoặc nhóm từ hệ thống danh tính.
3. Với chính sách role/authority, dùng `AuthorityAuthorizationManager` hoặc DSL tương ứng; kiểm tra role hierarchy nếu có.
4. Với tình trạng đăng nhập, dùng `AuthenticatedAuthorizationManager`; phân biệt anonymous, remember-me, fully authenticated, đừng giả định cờ `isAuthenticated` là tất cả.
5. Với nhiều yêu cầu phải đồng thời đúng, dùng `AuthorizationManagers.allOf`; chỉ dùng `anyOf` khi OR thật sự là chính sách.
6. Với owner/tenant/record-level access, kiểm tra dữ liệu tin cậy bằng custom manager, service policy hoặc query có điều kiện quyền.
7. Đặt matcher cụ thể trước matcher tổng quát, kết thúc bằng default-deny phù hợp.
8. Viết integration test allow/deny, phân biệt role/authority, anonymous/remember-me/fully authenticated và thiếu một điều kiện khi dùng AND.
9. Đọc dependency tree để xác định Spring Security/Boot version thực; dùng `authorize(...)` trên 6.4+ và lưu ý API thay đổi ở 7.x.
10. Không giả định HTTP rule tự bảo vệ background/service calls; xác minh các ranh giới nghiệp vụ còn lại.

## 12. Tự kiểm tra kiến thức

**Câu 1.** `alice` có `ROLE_ADMIN`. `hasAuthority("ADMIN")` có allow không?

**Giải thích:** Không, vì `hasAuthority` so khớp chuỗi chính xác. `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` mới tương ứng với chuỗi này (với role prefix mặc định).

**Câu 2.** User remember-me có thể đi vào `.authenticated()` không? Còn `.fullyAuthenticated()`?

**Giải thích:** Thông thường có thể đi vào `authenticated()`, nhưng không đạt `fullyAuthenticated()`, vì trust resolver phân biệt nguồn remember-me.

**Câu 3.** `hasAnyAuthority("a", "b")` có cần cả hai không?

**Giải thích:** Không, đó là OR. Nếu cần cả hai, tổ hợp hai manager bằng `AuthorizationManagers.allOf(...)` hoặc xây chính sách tương đương.

**Câu 4.** Một manager `hasRole("ADMIN")` có biết user được phép sửa tài liệu của người khác không?

**Giải thích:** Nó chỉ biết role trong Authentication. Quy tắc ownership/tenant trên tài liệu phải được định nghĩa và thực thi riêng.

**Câu 5.** Vì sao `@WithMockUser(authorities = "ADMIN")` không qua `hasRole("ADMIN")` trong test?

**Giải thích:** Attribute `authorities` đưa vào đúng chuỗi `ADMIN`; không tự gắn `ROLE_` như khi sử dụng `roles = "ADMIN"`. Nhờ vậy test chứng minh sự khác biệt giữa role và authority.

## 13. Nguồn tài liệu chính thức

- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `GrantedAuthority`, `AuthorizationManager`, mô tả `AuthorityAuthorizationManager`, `AuthenticatedAuthorizationManager` và composition.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, matcher, rule, request authorization và MockMvc test.
- [Spring Security 6.5 — AuthorityAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html): factory `hasRole`/`hasAuthority` và `setRoleHierarchy`.
- [Spring Security 6.5 — AuthenticatedAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthenticatedAuthorizationManager.html): `authenticated`, `fullyAuthenticated`, `rememberMe`, `anonymous` và trust resolver.
- [Spring Security 6.5 — AuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize(...)`, `verify(...)` và `check(...)` deprecated.

**Ghi nhớ:** Hai manager giải quyết hai chiều độc lập của bảo mật: **được cấp quyền gì** và **đang được xác thực theo cách nào**. Dùng đúng nhà máy `hasAuthority`/`hasRole` hoặc `authenticated`/`fullyAuthenticated`, kết hợp theo AND/OR khi cần và bổ sung policy nghiệp vụ khi quyền phụ thuộc tài nguyên cụ thể.