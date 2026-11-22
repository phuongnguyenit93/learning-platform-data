# Thiết kế principal riêng với định danh ổn định và dữ liệu tối thiểu

> **Phạm vi:** Mô hình danh tính trong Spring Security (Servlet). Bài học giải thích cách thiết kế principal của ứng dụng, chọn định danh ổn định, giới hạn thông tin đưa vào `SecurityContext`, và tích hợp principal sau khi xác thực đúng cách. Ví dụ thực hành dùng Java 17+, Spring Boot và HTTP Basic để dễ quan sát; nguyên tắc còn áp dụng cho session, JWT và OIDC khi ánh xạ danh tính phù hợp.

## 1. Vấn đề thực tế: username và email không phải định danh bền vững

Giả sử bảng `users` có hai hàng:

| id | username | email | display_name |
| --- | --- | --- | --- |
| `550e8400-e29b-41d4-a716-446655440000` | `an` | `an@example.test` | An |
| `dc42f6ca-4e97-4d78-bbb3-a2720196e351` | `binh` | `binh@example.test` | Bình |

Hôm nay An đổi username từ `an` sang `an.nguyen` hoặc đổi email. Nếu đơn hàng lưu `owner_username = "an"` thì hệ thống phải cập nhật dữ liệu liên quan, hoặc có nguy cơ không tìm thấy chủ sở hữu sau khi đổi tên. Nếu username cũ có thể được đăng ký lại, sử dụng username làm khóa phân quyền còn nguy hiểm hơn: dữ liệu của tài khoản cũ có thể bị gắn nhầm với tài khoản mới.

Trong khi đó, `users.id` có thể được thiết kế **bất biến** qua toàn bộ vòng đời tài khoản. Đơn hàng chỉ cần lưu `owner_user_id` trỏ tới ID này. Thay đổi username/email không làm biến đổi quan hệ sở hữu.

**Ý tưởng chính:** principal ở tầng application nên chứa **định danh nội bộ ổn định**, chỉ kèm một vài thuộc tính thật sự cần cho request hiện tại. Chức năng xác thực có thể dùng username/email để tìm hồ sơ, nhưng ứng dụng nghiệp vụ nhận diện user bằng ID đã được xác minh.

Lưu ý: `Principal.getName()` là một tên biểu diễn chủ thể; tên này **không đương nhiên** là khóa nghiệp vụ bất biến. Với custom principal, hãy thiết kế API rõ ràng như `userId()` để nơi kiểm tra sở hữu dùng đúng ID.

## 2. Principal là gì và nằm ở đâu trong Spring Security?

`Principal` là khái niệm về một chủ thể được biểu diễn trong ngữ cảnh bảo mật. Trong Java có interface `java.security.Principal` với `getName()`. Trong Spring Security, đối tượng `Authentication` mang những thông tin chính:

- `getPrincipal()`: đối tượng đại diện chủ thể; có thể là `UserDetails`, `Jwt`, `OidcUser`, một chuỗi hoặc custom principal.
- `getCredentials()`: bằng chứng xác thực, ví dụ password; thường cần loại bỏ sau khi kiểm tra.
- `getAuthorities()`: quyền mà framework có thể dùng để authorization.
- `isAuthenticated()`: trạng thái token; không nên dùng riêng giá trị này để kết luận một người dùng thực đã đăng nhập vì có thể có anonymous token.

Spring Security đặt `Authentication` của request vào `SecurityContext`; trong nhiều ứng dụng Servlet đồng bộ, ngữ cảnh được truy cập qua `SecurityContextHolder` và framework xử lý việc đặt/dọn nó trong vòng đời request.

```text
Client gửi credential (chưa đáng tin)
          |
          v
AuthenticationFilter / cơ chế login
          |
          v
AuthenticationManager -> AuthenticationProvider
          |                  |
          |                  +-- xác minh credential, tài khoản, nguồn danh tính
          v
Authentication đã xác thực
    | principal = AppPrincipal(userId, username)
    | authorities = tập quyền đã cấp
    | credentials = null / được xóa thích hợp
          |
          v
SecurityContext của request
          |
          +--> @AuthenticationPrincipal: lấy userId đáng tin
          |
          +--> Authorization: kiểm tra authority và điều kiện nghiệp vụ
```

Vị trí **phát hành** custom principal rất quan trọng: nó phải được tạo bởi một cơ chế xác thực **sau khi bằng chứng đã hợp lệ**, hoặc được ánh xạ từ token/identity provider đã được kiểm chứng. Tạo `AppPrincipal(id)` trực tiếp từ query/body/header do client gửi rồi tự dựng token "authenticated" sẽ phá vỡ ranh giới tin cậy.

## 3. Định danh ổn định cần đáp ứng tiêu chí nào?

Một ID tốt cho principal ứng dụng thường có các đặc điểm:

1. **Không đổi khi thông tin hiển thị đổi:** username, email, số điện thoại, tên hồ sơ và ảnh đại diện đều có thể đổi.
2. **Không được tái sử dụng cho một chủ thể khác:** tài khoản bị khóa/xóa không nên khiến ID cũ trở thành ID của người mới.
3. **Có phạm vi duy nhất rõ ràng:** ID toàn cục hoặc cặp `(tenantId, userId)` nếu user ID chỉ duy nhất trong mỗi tenant.
4. **Được gắn từ nguồn có thẩm quyền:** DB, identity service hoặc kết quả mapping từ provider đã xác minh.
5. **Không cấp thêm quyền chỉ vì đoán được ID:** UUID và số tuần tự đều là định danh, không phải bí mật dùng để xác thực.
6. **Được truyền xuyên các tầng dưới kiểu dữ liệu rõ ràng:** `UUID` hoặc một value object như `UserId` tốt hơn việc chắp vá username ở từng service.
7. **Không gây phụ thuộc vào thông tin có thể thay đổi:** resource ownership, audit actor ID và foreign key nên dùng ID ổn định.

`UUID` là lựa chọn dễ minh họa, nhưng hệ thống có thể dùng `long`, ULID hoặc mã nội bộ khác nếu bảo đảm tính bất biến và duy nhất theo phạm vi. UUID **không thay thế authorization**; người dùng biết UUID của Bình vẫn không được phép đọc dữ liệu của Bình.

### Hệ thống đa tenant

Nếu ID `42` có thể xuất hiện ở tenant A lẫn tenant B, chỉ lưu `userId=42` trong principal là không đủ để phân biệt. Có thể dùng:

```java
record AppPrincipal(java.util.UUID tenantId, java.util.UUID userId, String username) {}
```

Đây là **phác thảo dữ liệu**, chưa phải custom principal hoàn chỉnh. Chỉ thêm `tenantId` khi nó là một phần của phạm vi danh tính đã được xác thực; không lấy tenant từ header tự khai mà thiếu cơ chế xác minh. Khi truy cập tài nguyên, cần đồng thời kiểm tra tenant và user/permission. Nếu ID người dùng đã duy nhất toàn cục, tenant vẫn có thể cần như **ngữ cảnh phân quyền** nhưng không nhất thiết phải là thành phần khóa danh tính.

### Danh tính liên kết từ Identity Provider

Trong OIDC, cặp `(issuer, subject)` thường là khóa nhận diện có ý nghĩa trong phạm vi issuer đã tin cậy. Subject `sub` không nên được giả định là duy nhất giữa các issuer; email không phải khóa lâu dài, kể cả khi có trạng thái xác minh email. Ứng dụng có thể duy trì bảng mapping:

```text
identity_links:
  issuer           subject          internal_user_id
  https://idp-A    abc-123          550e8400-e29b-41d4-a716-446655440000
  https://idp-B    x-999            550e8400-e29b-41d4-a716-446655440000
```

Hai tài khoản ở hai provider **chỉ được liên kết** đến cùng ID khi quy trình account linking đáng tin thực sự chứng minh/cho phép điều đó. Không tự ghép tài khoản chỉ vì email trùng.

## 4. Nguyên tắc dữ liệu tối thiểu trong principal

Không nên đưa cả entity `User` hoặc kết quả query tài khoản vào `Authentication.getPrincipal()` chỉ vì framework cho phép.

| Dữ liệu | Có nên đặt vào custom principal? | Lý do |
| --- | --- | --- |
| `userId` ổn định | **Có** | Khóa tham chiếu tin cậy cho nghiệp vụ, audit, chủ sở hữu |
| `tenantId` khi thuộc phạm vi danh tính | Có điều kiện | Cần để phân biệt danh tính/phạm vi quyền nếu ứng dụng đa tenant |
| `username` ngắn, không bí mật | Tùy nhu cầu | Hữu ích cho `getName()`, log có kiểm soát; có thể đã cũ sau đổi tên |
| `displayName`, avatar | Thường **không** | Dữ liệu giao diện thay đổi; tải từ profile service khi hiển thị |
| Email, số điện thoại, địa chỉ | Thường **không** | PII, dễ thay đổi, tăng nguy cơ lộ qua serialization/log |
| Password thô, password hash, API key, access token | **Không** | Bí mật hoặc dữ liệu chứng thực; không thuộc mô hình danh tính tối thiểu |
| JPA entity, collection lazy, quan hệ 2 chiều | **Không** | Dễ lỗi lazy loading, vòng tham chiếu, rò dữ liệu, trạng thái mutable |
| `authorities` | Thường lưu trên **Authentication** | Spring Security đã có `getAuthorities()`; tránh hai nguồn quyền xung đột |
| Dữ liệu profile ít dùng | **Không** | Tăng bộ nhớ/session và độ cũ của thông tin |

Không có một danh sách trường tuyệt đối cho mọi ứng dụng. Một service cần account type hoặc region để kiểm soát chính sách có thể mang thuộc tính đã được chứng thực, nhưng phải rõ nguồn dữ liệu và cách cập nhật. **Càng ít trường không thiết yếu, càng ít dữ liệu cũ và bề mặt rò rỉ.**

### Thiết kế bất biến

Trong Java 17+, `record` phù hợp cho một snapshot identity nhỏ:

```java
import java.security.Principal;
import java.util.UUID;

record AppPrincipal(UUID userId, String username) implements Principal {
    @Override
    public String getName() {
        return username;
    }
}
```

Đây là **mảnh mã minh họa**, cần đặt đúng package và file/lớp chứa để dùng. Record có các accessor `userId()` và `username()`, không có setter; không phải entity, không chứa password. `getName()` giúp các tích hợp Java/Spring lấy tên thông thường, nhưng nơi kiểm tra sở hữu dùng `userId()`.

Nếu ứng dụng có session serialization hoặc clustered session, hãy cân nhắc contract `Serializable`, phiên bản payload và cơ chế refresh; khi cần có thể khai báo record implements `Principal, Serializable`. Với HTTP Basic demo ở phần tiếp theo, ta quan sát principal theo từng request.

## 5. Ví dụ đầy đủ: provider kiểm tra credential rồi tạo principal tối thiểu

Ví dụ này chủ ý tách ba cấu trúc:

- `StoredAccount`: dữ liệu lưu trữ, **chứa password hash** và quyền nguồn; chỉ tầng xác thực sử dụng.
- `AppPrincipal`: danh tính kết quả, chỉ chứa `UUID userId` và `username`; **không chứa password hash**.
- `Authentication`: kết quả Spring Security, chứa `AppPrincipal` và `GrantedAuthority` sau khi kiểm chứng.

Để minh họa ranh giới rõ ràng, ví dụ dùng custom `AuthenticationProvider` cho username/password và một kho tài khoản in-memory. Trong dự án thật, thường nên dùng cơ chế chuẩn như `DaoAuthenticationProvider`/`UserDetailsService` khi phù hợp, hoặc converter của OAuth2 Resource Server cho token; custom provider chỉ cần khi có lý do rõ ràng như chủ động tách principal công khai khỏi hồ sơ chứa credential.

**Điều kiện:** Java 17+, dự án Spring Boot Servlet với starter Spring Web và Spring Security, Gradle/Maven wrapper đã cấu hình. Nếu dùng Spring Initializr, tạo project với hai dependency **Spring Web** và **Spring Security**, giữ version Spring Boot tương thích với Java được chọn.

Tạo file duy nhất `src/main/java/com/example/principaldemo/PrincipalDemoApplication.java`:

```java
package com.example.principaldemo;

import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PrincipalDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PrincipalDemoApplication.class, args);
    }
}

// Danh tính được phép đi tới controller/service.
// Không chứa password hash, email, token, JPA entity.
record AppPrincipal(UUID userId, String username) implements Principal {
    @Override
    public String getName() {
        return username;
    }
}

// Mô hình lưu trữ riêng, chỉ provider được sử dụng khi xác thực.
record StoredAccount(
        UUID id,
        String username,
        String passwordHash,
        boolean enabled,
        List<String> authorityNames) {
}

final class AccountStore {
    private final Map<String, StoredAccount> byUsername;

    AccountStore(StoredAccount account) {
        this.byUsername = Map.of(account.username(), account);
    }

    StoredAccount findByUsername(String username) {
        return byUsername.get(username);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        StoredAccount account = new StoredAccount(
                UUID.fromString("550e8400-e29b-41d4-a716-446655440000"),
                "an",
                encoder.encode("demo-password"),
                true,
                List.of("orders:read"));
        return new AccountStore(account);
    }

    @Bean
    AuthenticationProvider demoAuthenticationProvider(
            AccountStore accounts,
            PasswordEncoder encoder) {

        return new AuthenticationProvider() {
            @Override
            public Authentication authenticate(Authentication request)
                    throws AuthenticationException {

                if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                    return null;
                }

                Object credential = request.getCredentials();
                if (!(credential instanceof String password)) {
                    throw new BadCredentialsException("Bad credentials");
                }

                StoredAccount account = accounts.findByUsername(
                        request.getName());

                // Chỉ kết quả kiểm tra thành công mới sinh trusted principal.
                if (account == null
                        || !account.enabled()
                        || !encoder.matches(password, account.passwordHash())) {
                    throw new BadCredentialsException("Bad credentials");
                }

                AppPrincipal principal = new AppPrincipal(
                        account.id(), account.username());

                List<GrantedAuthority> authorities = account.authorityNames()
                        .stream()
                        .map(name -> (GrantedAuthority)
                                new SimpleGrantedAuthority(name))
                        .toList();

                return UsernamePasswordAuthenticationToken.authenticated(
                        principal,
                        null, // Không mang password vào Authentication kết quả.
                        authorities);
            }

            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(type);
            }
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthenticationProvider demoAuthenticationProvider)
            throws Exception {

        return http
                .authenticationProvider(demoAuthenticationProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/orders/my")
                            .hasAuthority("orders:read")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(@AuthenticationPrincipal AppPrincipal principal) {
        return "id=" + principal.userId()
                + "; username=" + principal.username();
    }

    @GetMapping("/orders/my")
    String myOrders(@AuthenticationPrincipal AppPrincipal principal) {
        return "ownerId=" + principal.userId();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin ok";
    }
}
```

### Vì sao ví dụ dùng custom provider thay vì ép mọi thứ vào `UserDetails`?

`UserDetailsService` thường tải `UserDetails` bao gồm password hash, cờ tài khoản và authorities để `DaoAuthenticationProvider` kiểm tra. Cách này là lựa chọn chuẩn, hữu ích ở nhiều ứng dụng. Tuy nhiên, nếu trả nguyên `UserDetails` làm principal, đối tượng gắn trong `Authentication` có thể chứa thêm dữ liệu không cần thiết hoặc password hash, tùy implementation và cơ chế xóa credential. Việc đưa cả JPA entity vào `UserDetails` càng làm khó kiểm soát dữ liệu.

Ở ví dụ trên, `AccountStore` giữ thông tin phục vụ xác thực; provider so khớp password **trước khi** tạo `AppPrincipal`. `UsernamePasswordAuthenticationToken.authenticated(...)` chỉ được gọi trong nhánh đã xác minh thành công, với credentials đặt `null`. Phần còn lại của ứng dụng không cần biết cấu trúc lưu trữ password.

Custom provider trong production còn phải quan tâm khóa tài khoản, timing/user enumeration, MFA, rate limit, theo dõi đăng nhập, phân tách exception, session/token lifecycle và đồng bộ với hệ thống lưu trữ. Đoạn code là **demo học tập** cho ranh giới giữa credential và principal, không phải toàn bộ chức năng đăng nhập an toàn sẵn cho production.

### Chạy bằng build tool

Từ thư mục gốc project Gradle:

```bash
./gradlew bootRun
```

Hoặc, với project Maven:

```bash
./mvnw spring-boot:run
```

Trên PowerShell dùng `.\gradlew.bat bootRun` hoặc `.\mvnw.cmd spring-boot:run`. File ví dụ có import Spring nên **không thể chỉ gọi `javac` một mình** mà thiếu classpath/dependencies của Spring Boot.

Trong terminal khác:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -s -u an:demo-password http://localhost:8080/orders/my
curl -i http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i -u an:demo-password http://localhost:8080/admin
curl -s -u an:demo-password "http://localhost:8080/me?userId=00000000-0000-0000-0000-000000000000"
```

Trên Windows PowerShell nếu `curl` được ánh xạ sang cmdlet khác, dùng `curl.exe` cho các lệnh tương đương.

**Body chính xác của ba lệnh đầu trong demo:**

```text
pong
id=550e8400-e29b-41d4-a716-446655440000; username=an
ownerId=550e8400-e29b-41d4-a716-446655440000
```

**Ba lệnh có `-i`:** lần lượt có trạng thái HTTP **401**, **401**, **403**. Nội dung header và error body tùy phiên bản/cấu hình. Lệnh cuối có thể nhận body giống lệnh `/me` hợp lệ: giá trị `userId` trong query không được controller dùng để xác định danh tính, nên không thể thay thế UUID của principal. Trình bày này giả định chạy đúng ứng dụng demo, không có security chain hoặc filter khác can thiệp.

**Lưu ý:** HTTP Basic chỉ Base64-encode credential và cần HTTPS khi sử dụng thực tế; không dùng password minh họa ngoài localhost/dev. Việc sử dụng password hash BCrypt trong `StoredAccount` để đối chiếu là đúng hướng, nhưng không tự đáp ứng mọi yêu cầu bảo vệ tài khoản.

## 6. Điểm kiểm chứng quan trọng trong mã

Xét lần lượt hai thời điểm khác nhau:

**Trước khi xác thực:** Spring Security tạo yêu cầu kiểu `UsernamePasswordAuthenticationToken` chứa username/password từ Basic Authorization header; `request.getName()` là username tự khai, chưa đủ để tin cậy. `AccountStore.findByUsername` tìm hồ sơ theo username nhưng **không xác thực** người gọi chỉ bằng việc tìm thấy tài khoản.

**Sau khi xác thực:** `PasswordEncoder.matches(password, account.passwordHash())` xác nhận credential; provider mới tạo:

```java
AppPrincipal principal = new AppPrincipal(
        account.id(), account.username());

return UsernamePasswordAuthenticationToken.authenticated(
        principal, null, authorities);
```

Đây là **mảnh mã từ provider đầy đủ** ở trên. Constructor/factory đáng tin chỉ được dùng sau kiểm tra thành công, không phải để đánh dấu dữ liệu client thành "đã login".

Tại controller:

```java
@GetMapping("/me")
String me(@AuthenticationPrincipal AppPrincipal principal) {
    return "id=" + principal.userId()
            + "; username=" + principal.username();
}
```

`@AuthenticationPrincipal` trích `Authentication.getPrincipal()` cho request hiện tại. Controller không truy vấn lại thông tin đăng nhập, không nhận một `userId` do caller tự khai, và không cần chạm vào password hash. Với một principal tùy biến, giữ kiểu và contract nhất quán giữa authentication mechanism và web/controller.

**Authority không đồng nhất với principal.** Principal trả lời "ai"; tập `GrantedAuthority` trên `Authentication` giúp framework trả lời một phần "được phép gì". Một người có quyền `orders:read` vẫn cần kiểm tra đối tượng/tenant cụ thể khi ứng dụng có phân quyền theo tài nguyên.

## 7. Truyền danh tính tối thiểu vào tầng nghiệp vụ

Trong ứng dụng lớn hơn, controller có thể chuyển đúng ID và quyền/ngữ cảnh cần thiết cho service. Ví dụ ý tưởng:

```java
@GetMapping("/orders/mine")
List<OrderView> mine(@AuthenticationPrincipal AppPrincipal principal) {
    return orderService.findVisibleForOwner(principal.userId());
}
```

Đây là **mảnh thiết kế**, chỉ biên dịch khi có `OrderView`, `orderService` và các import/bean tương ứng. Query nghiệp vụ sau đó nên dùng ID này như tham số được server xác thực:

```sql
SELECT id, status, total
FROM orders
WHERE owner_user_id = :authenticatedUserId;
```

Đây là SQL minh họa; tên bảng/cột phụ thuộc schema. Điều cốt lõi là `authenticatedUserId` đến từ principal đáng tin.

Với tài nguyên đã biết ID, vẫn cần kiểm tra **quyền trên đối tượng**:

```text
GET /orders/987

1. Security filter xác thực request và cấp AppPrincipal(userId=A).
2. Authorization kiểm tra quyền API tương ứng nếu có.
3. Service tải đơn hàng 987.
4. Service/Policy kiểm tra owner_user_id của đơn hàng là A
   hoặc chủ thể có quyền đặc biệt được policy cho phép.
5. Chỉ khi đúng mới trả thông tin.
```

Không lấy `ownerUserId` từ body hoặc query để quyết định ai là chủ sở hữu đang đăng nhập; với endpoint tạo đơn hàng, server tự gán chủ sở hữu dựa trên principal. Nếu cần làm việc "thay mặt" tài khoản khác, phải có policy ủy quyền riêng và ghi nhận cả actor thực lẫn subject thay mặt.

### Audit và log

Nên ghi lại **actor ID ổn định** làm khóa truy vết, cùng correlation/request ID, loại thao tác, đối tượng và thời điểm phù hợp. Username/display name có thể phục vụ giao diện log, nhưng không dùng làm khóa duy nhất. Hạn chế log toàn bộ `Authentication` hoặc `principal.toString()` vì khi cấu trúc principal thay đổi có thể vô tình ghi thêm PII/claims/secret.

## 8. Khi username/email thay đổi, khi tài khoản bị khóa

Một principal thường là **snapshot** của danh tính tại thời điểm xác thực. Phân biệt thông tin bất biến và thông tin phải được làm mới.

### Đổi username hoặc email

- `userId` vẫn giữ nguyên; foreign key và audit actor ID không thay.
- `username` chứa trong session/token cũ có thể còn giá trị cũ tới khi làm mới ngữ cảnh hoặc đăng nhập lại.
- Profile màn hình nên được đọc từ profile service theo `userId` khi cần dữ liệu mới nhất.
- Nếu hệ thống cho phép đăng nhập bằng email, email chỉ là **lookup key** tại thời điểm xác thực, không phải owner ID hoặc phép gán quyền.

Ví dụ trước và sau:

| Thời điểm | `userId` | `username` | Sở hữu đơn hàng |
| --- | --- | --- | --- |
| Trước đổi tên | `550e8400-...` | `an` | Khóa `userId` |
| Sau đổi tên | `550e8400-...` | `an.nguyen` | Vẫn cùng khóa `userId` |
| Session chưa refresh | `550e8400-...` | Có thể vẫn `an` | Khóa `userId` không đổi |

### Khóa tài khoản, xóa quyền hoặc xóa người dùng

Principal chứa ID ổn định **không có nghĩa account luôn hợp lệ vĩnh viễn**. Nếu account bị khóa sau login, session hoặc token chưa hết hạn vẫn có thể chứa authentication cũ. Chính sách vận hành phải quyết định:

- Vô hiệu hóa các session đang tồn tại hoặc bắt buộc đăng nhập lại.
- TTL ngắn và cơ chế revocation/rotation cho token.
- Kiểm tra trạng thái account/quyền hiện thời ở bước quan trọng.
- Giữ khóa tham chiếu audit ngay cả khi account bị vô hiệu hóa hoặc xóa theo chính sách lưu trữ.

Không nên sao chép `enabled` từ DB vào principal rồi tin nó luôn cập nhật. Đặc biệt, thao tác quyền cao có thể cần tra cứu policy hiện hành thay vì hoàn toàn dựa vào snapshot cũ.

## 9. Thiết kế principal khi dùng JWT, OIDC hoặc service account

Cách dùng `AppPrincipal` cụ thể ở demo hoạt động vì custom provider **chủ động tạo đúng kiểu**. Không nên giả định mọi `Authentication.getPrincipal()` của mọi giao thức đều là `AppPrincipal`.

### JWT Resource Server

Spring Security khi xác minh JWT thường xây `JwtAuthenticationToken` với principal là `Jwt`; việc chỉ khai báo `record AppPrincipal` không tự chuyển token thành principal này. Muốn business dùng một model thống nhất, có thể:

1. Xác minh chữ ký, issuer, thời hạn và audience phù hợp qua cấu hình resource server.
2. Dùng subject hoặc claim đáng tin cùng issuer để đối chiếu tới internal user ID theo mapping được quản lý.
3. Tạo application identity/context thông qua converter/resolver đã kiểm soát thay vì ép cast `Jwt` thành `AppPrincipal`.
4. Giữ các scope/authority trên `Authentication` hoặc một cấu trúc quyền tin cậy có thiết kế rõ ràng.
5. Không nhầm `sub` toàn cục giữa các issuer; không dùng claim tự khai từ JSON request.

Một sơ đồ dễ nhớ:

```text
Signed JWT --(signature/iss/aud/exp validation)--> Verified Jwt
       |
       +-- issuer + subject --> trusted account mapping --> internal userId
       |
       +-- verified scope/claims --> authorities
       |
       v
Application identity for business (userId, possibly tenantId)
```

Đây là **phương án thiết kế**; không có chuyện Spring Security tự thực hiện mọi bước mapping nội bộ nếu ứng dụng chưa cấu hình chúng.

### OIDC login

Khi dùng login qua Identity Provider, `OidcUser` thường mang claims và phương thức nhận diện riêng của provider. Ứng dụng nên chuyển thành identity ứng dụng khi cần: nội bộ có `userId` bất biến, còn IDP `issuer + sub` dùng để liên kết tài khoản. Các trường như `email`, `preferred_username`, `name` là thông tin nhận diện/hiển thị theo hợp đồng của provider, có thể đổi và có các yêu cầu kiểm chứng riêng.

### Service-to-service

Một client/service được xác thực có thể có **service principal**, không có `userId` người dùng. Ép mọi principal thành user record sẽ gây nhầm "service đang gọi" với "người dùng cuối". Thiết kế rõ loại chủ thể:

```java
sealed interface Actor permits UserActor, ServiceActor {}

record UserActor(java.util.UUID userId) implements Actor {}
record ServiceActor(String clientId) implements Actor {}
```

Đây là mô hình **minh họa** để diễn đạt sự phân biệt, không tự tích hợp với Spring Security nếu chưa có converter/provider. Nếu một API chấp nhận cả user và service, policy phải biết thao tác nào yêu cầu user thực và thao tác nào dành cho service. Không tự động mang quyền của user cuối qua nhiều service chỉ từ một header text.

## 10. Những lựa chọn thiết kế có vẻ tiện nhưng gây lỗi

| Lựa chọn dễ mắc | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng username/email làm khóa owner | Đổi tên, tái sử dụng hoặc sai chuẩn hóa dẫn đến nhầm sở hữu | Dùng internal user ID bất biến |
| Dùng `getName()` làm ID mà không kiểm tra contract | Tùy principal, tên có thể là username, subject, email | Dùng accessor `userId()` hoặc typed actor ID |
| Đặt toàn bộ entity JPA vào principal | Lazy loading, vòng tham chiếu, mutation, dữ liệu nhạy cảm trong session | Dùng DTO/record tối thiểu không phụ thuộc persistence |
| Đặt password hash/access token vào principal | Credential có thể lộ qua log, serialization hoặc memory | Giữ tại cơ chế xác minh, tách khỏi principal kết quả |
| Dùng `new AppPrincipal(request.userId)` rồi tự coi đã đăng nhập | Client giả danh tài khoản khác | Chỉ tạo sau trusted authentication |
| Coi UUID là "khó đoán nên đủ bảo mật" | ID không phải secret; lộ ID vẫn gây IDOR nếu không có policy | Authorization ở resource và tenant |
| Dùng role trong principal và một danh sách role khác trong `Authentication` | Hai nguồn quyền có thể lệch nhau | Đặt authority theo contract thống nhất |
| Mặc định mọi `getPrincipal()` là `AppPrincipal` | JWT/OIDC/anonymous/service dùng kiểu khác | Converter/resolver hoặc typed actor phù hợp |
| Giữ username, role, enabled mãi trong session | Thông tin cũ sau thay đổi chính sách | Chiến lược refresh/revocation |
| Để public endpoint luôn cast principal không null | Anonymous hoặc không có principal kiểu ứng dụng | Đặt bảo vệ endpoint, xử lý null/anonymous đúng cách |
| Dùng ID không phân biệt tenant | Trùng user ID giữa tenant; rò dữ liệu qua biên tenant | ID phạm vi rõ, khóa ghép hoặc mapping tenant đáng tin |
| Dùng `toString()` của principal làm log chính | Lộ dữ liệu hoặc mất ổn định khi thêm field | Log actor ID/tác vụ cần thiết một cách có kiểm soát |

Một chi tiết khác: `record` giúp bất biến **mặt cấu trúc**, nhưng nếu record chứa `List` hoặc `Map` mutable thì bản thân dữ liệu bên trong vẫn có thể đổi. Với principal tối thiểu chỉ chứa `UUID` và `String`, vấn đề này được tránh; nếu cần collection, dùng immutable copy như `List.copyOf(...)` và giới hạn dữ liệu đưa vào.

## 11. Kiểm thử các bất biến quan trọng

Thay vì chỉ thử "đăng nhập có thành công", kiểm tra hành vi bảo vệ định danh:

1. **Đăng nhập đúng:** với `an:demo-password`, `/me` trả đúng UUID nội bộ, không chỉ trả username.
2. **Đăng nhập sai:** password sai hoặc user không tồn tại không tạo `Authentication` đáng tin và không trả principal của account được tự khai.
3. **Giả mạo userId:** vẫn dùng Basic credential của An nhưng thêm `?userId=<ID của Bình>`; business phải coi actor là An.
4. **Đổi username/email:** account vẫn giữ user ID; owner foreign key và audit không thay. Thông tin hiển thị có thể cần refresh.
5. **Thiếu authority:** đã xác thực nhưng gọi `/admin` khi không có `ROLE_ADMIN` nhận 403 trong demo.
6. **Vượt quyền trên object:** có quyền `orders:read` nhưng cố đọc đơn hàng thuộc account/tenant khác phải bị policy từ chối.
7. **Principal khác kiểu:** nếu tích hợp JWT/OIDC/service account, resolver phải tạo đúng application identity hoặc từ chối rõ ràng; không `ClassCastException` âm thầm trong nghiệp vụ.
8. **Rò rỉ dữ liệu:** JSON response, log, session/token và debug không lộ password hash, raw credential hoặc hồ sơ PII.
9. **Thu hồi/disable:** sau khi khóa account hoặc đổi quyền, kiểm chứng thời điểm những request đang tồn tại bị từ chối theo chính sách đã thiết kế.
10. **Tính độc lập với frontend:** thay đổi field do client gửi không được sửa danh tính nhận được từ `@AuthenticationPrincipal`.

Với ứng dụng đa tenant, bổ sung kịch bản user IDs trùng nhau giữa hai tenant nếu schema cho phép. Với federated login, bổ sung kịch bản cùng email nhưng khác `issuer + sub`, tránh auto-link thiếu chứng cứ.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không dùng email làm foreign key `orders.owner`?  
**Trả lời:** Email có thể đổi, bị thu hồi/tái sử dụng và không luôn là khóa duy nhất toàn hệ thống. ID nội bộ bất biến giữ quan hệ sở hữu ổn định.

**Câu 2.** Thêm `UUID userId` vào custom principal đã đủ thay thế authentication chưa?  
**Trả lời:** Chưa. ID là dữ liệu biểu diễn danh tính; chỉ sau khi bằng chứng xác thực hợp lệ mới được phát hành `Authentication` tin cậy mang principal đó.

**Câu 3.** Vì sao ví dụ tách `StoredAccount` và `AppPrincipal`?  
**Trả lời:** Hồ sơ lưu trữ cần password hash/trạng thái/quyền để xác thực, nhưng controller/service chỉ cần ID và tên ngắn; tách ra giảm dữ liệu dư thừa và rủi ro lộ credential.

**Câu 4.** Một client biết UUID của người khác có đủ quyền đọc tài nguyên người đó không?  
**Trả lời:** Không. UUID chỉ là định danh. Server còn phải xác thực actor và kiểm tra chính sách trên tài nguyên cụ thể.

**Câu 5.** Thêm `@AuthenticationPrincipal AppPrincipal` vào API JWT hiện có thì chắc chắn dùng được ngay không?  
**Trả lời:** Không. Authentication của JWT có thể dùng `Jwt` làm principal. Cần cấu hình mapping/converter hoặc abstraction của application để nhận đúng kiểu.

**Câu 6.** Username của An thay đổi nhưng session giữ principal cũ; nên tin ID hay username để xác định owner?  
**Trả lời:** Tin `userId` bất biến và đã được xác thực. Username trong snapshot có thể stale; tải lại từ nguồn profile nếu cần hiển thị mới nhất.

## 12. Kết luận thiết kế

Một custom principal tốt cần xác định rõ **chủ thể được ánh xạ từ nguồn tin cậy nào**, **ID có ổn định và duy nhất trong phạm vi nào**, **dữ liệu gì thực sự cần cho request**, và **ai chịu trách nhiệm làm mới hoặc thu hồi danh tính/quyền khi thay đổi**.

Với một ứng dụng người dùng thông thường, một record kiểu `AppPrincipal(UUID userId, String username)` là khởi điểm hợp lý. Nó được tạo **sau** authentication, truy cập qua `@AuthenticationPrincipal`, và truyền `userId` tới nghiệp vụ để kiểm tra quyền trên đối tượng. `Authentication` vẫn nắm authorities và Spring Security vẫn thực hiện authorization; custom principal không thay thế các cơ chế đó.

**Quy tắc nhớ:** Dùng định danh **bất biến** để biết *ai*, giữ principal **tối thiểu** để hạn chế dữ liệu không cần, và kiểm tra **quyền thực tế** khi quyết định *người đó được làm gì*.

### Tài liệu tham khảo chính thức

- [Spring Security 7 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html)
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security — Basic Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/basic.html)
- [Spring Security — Authentication Principal](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/servlet-api.html)
- [Spring Security — HTTP Authorization](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html)
