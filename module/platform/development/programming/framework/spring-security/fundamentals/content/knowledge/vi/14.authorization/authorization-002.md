# Phân biệt danh tính đã xác thực với tập quyền được cấp

> **Module:** Spring Security - fundamentals  
> **Nhóm kiến thức:** Phân quyền  
> **Câu hỏi trung tâm:** Một người dùng đã đăng nhập thành công thì có tự động được phép thực hiện mọi thao tác không? **Không.** Hệ thống cần biết *ai đang yêu cầu* và *người đó được làm gì trong ngữ cảnh cụ thể*.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **authentication (xác thực danh tính)** với **authorization (ra quyết định cho phép truy cập)** trong vòng đời một request.
- Đọc đúng hai nhóm thông tin cùng nằm trong đối tượng `Authentication` của Spring Security: thông tin principal/danh tính và tập `GrantedAuthority`/quyền được cấp.
- Giải thích vì sao `Authentication.isAuthenticated() == true` **không có nghĩa** người dùng có bất kỳ authority nào đang được yêu cầu.
- Phân biệt role, authority, permission, scope; biết cách `hasRole` và `hasAuthority` so khớp các chuỗi quyền.
- Nhận ra trường hợp đặc biệt của `AnonymousAuthenticationToken`, phân biệt trạng thái xác thực với token được đánh dấu `authenticated`.
- Thiết kế phép kiểm tra quyền ở cấp URL, phương thức và tài nguyên cụ thể; tránh nhầm lẫn giữa “đã đăng nhập” và “được xem/sửa tài liệu này”.

## 2. Hai câu hỏi bảo mật khác nhau

**Xác thực (authentication): “Bạn là ai, và bằng chứng danh tính có hợp lệ không?”**

Ví dụ, Alice gửi username/password; hệ thống đối chiếu thông tin đăng nhập. Hoặc client mang bearer token; resource server kiểm tra chữ ký, thời hạn, issuer và các điều kiện chấp nhận token. Sau khi xác thực thành công, Spring Security thường có một đối tượng `Authentication` biểu diễn principal được tin cậy trong phạm vi request hoặc phiên.

**Phân quyền (authorization): “Danh tính đã biết này có được phép thực hiện hành động đang yêu cầu lên tài nguyên này không?”**

Ví dụ, Alice được nhận diện hợp lệ nhưng chỉ có quyền xem hóa đơn; yêu cầu xóa hóa đơn cần quyền khác. Đăng nhập thành công không cấp quyền xóa.

~~~text
Client gửi request
       |
       v
[Authentication] Kiểm tra credential / token / session
       |
       +-- Không đạt: cần xác thực hoặc từ chối
       |
       v
[Authentication] Principal và các GrantedAuthority đã xác định
       |
       v
[Authorization] Hành động + tài nguyên + quy tắc áp dụng
       |
       +-- Không đạt: từ chối truy cập
       |
       v
Business logic được phép thực hiện
~~~

Trong HTTP API, hệ thống thường dùng **401 Unauthorized** khi request chưa có thông tin xác thực hợp lệ và **403 Forbidden** khi danh tính được công nhận nhưng thiếu quyền. Đây là quy ước phổ biến, không phải cách suy luận duy nhất từ mã trạng thái: ứng dụng dùng form login có thể chuyển hướng đến trang đăng nhập; CSRF, bộ lọc khác hoặc entry point tùy chỉnh cũng có thể làm kết quả khác đi.

### Ma trận tình huống

Giả sử ứng dụng quản lý chứng từ có ba quyền: `document:read`, `document:write` và `document:delete`.

| Người dùng | Xác thực | Authority được cấp | Xem | Sửa | Xóa |
| --- | --- | --- | --- | --- | --- |
| Alice | Thành công | `document:read` | Có | Không | Không |
| Bob | Thành công | `document:read`, `document:write` | Có | Có | Không |
| Carol | Thành công | `document:delete` | Không | Không | Có theo kiểm tra quyền thao tác |
| Khách chưa đăng nhập | Chưa có danh tính được tin cậy | Không có các quyền trên | Không | Không | Không |

Bảng chỉ mô phỏng **kiểm tra quyền theo hành động**; thực tế hệ thống có thể yêu cầu thêm quyền đọc trước khi xóa hoặc quyền sở hữu chứng từ. Quan trọng là **cùng trạng thái “đã xác thực”, tập quyền có thể hoàn toàn khác nhau**.

## 3. Một đối tượng `Authentication` chứa những gì?

Spring Security định nghĩa `org.springframework.security.core.Authentication`. Sau khi quá trình xác thực hợp lệ hoàn tất, nó thường chứa:

| API / dữ liệu | Dùng để trả lời | Ví dụ | Không nên suy diễn |
| --- | --- | --- | --- |
| `getPrincipal()` | Ai là chủ thể? | `UserDetails`, `Jwt`, `OAuth2User` hoặc tên user | Principal không phải danh sách quyền |
| `getName()` | Tên định danh do implementation cung cấp | `alice`, subject của token | Tên hiển thị không luôn là khóa định danh duy nhất xuyên tenant |
| `getCredentials()` | Bằng chứng dùng trong quá trình xác thực | Password/token, thường được xóa sau xác thực | Không log hoặc đưa credentials vào response |
| `getAuthorities()` | Chủ thể đang mang những quyền gì? | `ROLE_ADMIN`, `document:read`, `SCOPE_reports.read` | Không phải kết luận cuối cùng về mọi tài nguyên |
| `isAuthenticated()` | Token này có được đánh dấu đã xác thực theo semantics của implementation? | `true`/`false` | Không đồng nghĩa có `ROLE_ADMIN` hoặc được đọc tài liệu bất kỳ |
| `getDetails()` (khi implementation hỗ trợ) | Metadata bổ sung về lần xác thực | Chi tiết request | Không mặc định là nguồn quyền hay bằng chứng bảo mật |

`SecurityContext` chứa `Authentication`. Ở ứng dụng Servlet, Spring Security thường truy cập security context qua `SecurityContextHolder`; ở WebFlux dùng `ReactiveSecurityContextHolder` bên trong reactive publisher. **Cách truyền security context khác nhau**, nhưng phép phân biệt identity và authorities vẫn giữ nguyên.

### Cảnh báo về `isAuthenticated()`

Một request đăng nhập username/password trước khi được xác thực có thể được biểu diễn bằng token với `isAuthenticated() == false`. Sau khi `AuthenticationManager` hoặc `AuthenticationProvider` chấp nhận credentials, đối tượng kết quả có thể trả về `true`. Tuy nhiên, Spring Security còn có **anonymous authentication**: `AnonymousAuthenticationToken` thường được đánh dấu `isAuthenticated() == true` nhằm thuận tiện biểu diễn người dùng nặc danh trong ngữ cảnh bảo mật.

Vì vậy, phép kiểm tra thủ công:

~~~java
// KHÔNG đủ để quyết định rằng request là người dùng đăng nhập thực sự.
boolean loggedIn = authentication != null && authentication.isAuthenticated();
~~~

không phải một bản thay thế an toàn cho `authenticated()` trong DSL hoặc `AuthenticationTrustResolver`. Cơ chế phân quyền của Spring Security phân biệt anonymous, remember-me và fully authenticated khi cần; ví dụ `AuthenticationTrustResolver.isAnonymous(authentication)` nhận diện anonymous token.

## 4. `GrantedAuthority` là “quyền được cấp”, không phải “danh tính”

`Authentication.getAuthorities()` trả về một collection các `GrantedAuthority`. Interface này có phương thức `String getAuthority()`. Implementation phổ biến là `SimpleGrantedAuthority`, chứa chuỗi quyền để so khớp.

Ví dụ:

~~~text
Authentication:
  principal: "alice"
  authenticated: true
  authorities:
    - "ROLE_EMPLOYEE"
    - "document:read"
~~~

Trong ví dụ trên:

- `alice` cho biết principal là ai.
- `ROLE_EMPLOYEE` mô tả vai trò mà hệ thống gán cho principal.
- `document:read` mô tả một capability cụ thể.
- Không có `document:delete`, nên một quy tắc đòi `document:delete` phải từ chối Alice dù Alice có tên hợp lệ.

**Authority là dữ kiện đầu vào để đưa ra quyết định phân quyền.** Quyết định có thể còn phụ thuộc HTTP method, đường dẫn, thông tin tài nguyên trong cơ sở dữ liệu, tenant, thời điểm, quan hệ owner–resource hay chính sách nghiệp vụ.

### Role, permission, scope: cách đặt tên và ngữ nghĩa

| Khái niệm | Ví dụ | Ý nghĩa sử dụng |
| --- | --- | --- |
| **Role (vai trò)** | `ADMIN`, `EDITOR` | Nhóm trách nhiệm/chức năng của người dùng |
| **Role authority** | `ROLE_ADMIN` | Chuỗi authority thường được Spring Security dùng để biểu diễn role |
| **Permission / operation authority** | `document:read`, `invoice:approve` | Quyền được cấp theo thao tác |
| **OAuth2 scope** | `reports.read` → thường ánh xạ thành `SCOPE_reports.read` | Phạm vi được token ủy quyền, theo cấu hình ánh xạ của resource server |
| **Object-level policy** | “Alice chỉ được xem tài liệu thuộc phòng ban của Alice” | Quy tắc kết hợp subject, action, resource và context |

Spring Security không tự động hiểu rằng một chuỗi `ROLE_ADMIN` ngụ ý tất cả các `document:*`. Quan hệ “ADMIN được đọc/xóa” phải có trong mapping authority hoặc chính sách phân quyền của ứng dụng. Tương tự, claim `roles` nằm trong JWT **không tự nhiên trở thành** `ROLE_ADMIN` nếu cấu hình converter không ánh xạ nó.

### `hasRole` khác `hasAuthority` ở đâu?

Theo quy ước mặc định, `hasRole("ADMIN")` kiểm tra authority có tiền tố `ROLE_`, tức tương đương yêu cầu `ROLE_ADMIN`. `hasAuthority("ROLE_ADMIN")` yêu cầu **đúng chuỗi** đó; `hasAuthority("ADMIN")` kiểm tra chuỗi `ADMIN` và không tự thêm `ROLE_`. Tiền tố role có thể được tùy chỉnh bằng cấu hình tương ứng.

~~~text
Authorities hiện tại: ["ROLE_ADMIN", "document:read"]

hasRole("ADMIN")                 -> true  (mặc định khớp ROLE_ADMIN)
hasAuthority("ROLE_ADMIN")       -> true
hasAuthority("ADMIN")            -> false
hasAuthority("document:read")    -> true
hasAuthority("document:write")   -> false
~~~

Không tự thêm `ROLE_` vào lời gọi `hasRole` nếu đang dùng semantics mặc định; tránh việc kỳ vọng chuỗi được so khớp khác với dữ liệu thực được cấp. Tên authority là chuỗi nhạy với cách viết; thống nhất quy ước chữ hoa/thường và dấu phân cách giữa nơi cấp và nơi kiểm tra.

## 5. Thực hành Java 17+: cùng danh tính, tập quyền khác nhau

Ví dụ sau chạy độc lập dưới dạng ứng dụng console dùng `spring-security-core`. Nó chỉ mô phỏng các `Authentication` đã tạo để quan sát dữ liệu, **không phải chương trình đăng nhập hoặc bằng chứng một mật khẩu hợp lệ**.

Cấu trúc project:

~~~text
identity-authorities-demo/
├── build.gradle
└── src/main/java/demo/IdentityAuthoritiesDemo.java
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.IdentityAuthoritiesDemo'
}
~~~

File `src/main/java/demo/IdentityAuthoritiesDemo.java`:

~~~java
package demo;

import java.util.List;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class IdentityAuthoritiesDemo {

    private static void check(Authentication authentication, String authority) {
        boolean granted = authentication.getAuthorities().stream()
            .anyMatch(item -> authority.equals(item.getAuthority()));

        System.out.printf(
            "%s | tokenFlag=%s | %s=%s%n",
            authentication.getName(),
            authentication.isAuthenticated(),
            authority,
            granted
        );
    }

    public static void main(String[] args) {
        Authentication aliceReader =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(
                    new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
                    new SimpleGrantedAuthority("document:read")
                )
            );

        Authentication aliceEditor =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(
                    new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
                    new SimpleGrantedAuthority("document:read"),
                    new SimpleGrantedAuthority("document:write")
                )
            );

        Authentication bobAdmin =
            UsernamePasswordAuthenticationToken.authenticated(
                "bob",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
            );

        Authentication loginAttempt =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice",
                "not-a-real-password"
            );

        Authentication anonymous = new AnonymousAuthenticationToken(
            "demo-key",
            "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );

        AuthenticationTrustResolver resolver =
            new AuthenticationTrustResolverImpl();

        check(aliceReader, "document:write");
        check(aliceEditor, "document:write");
        check(bobAdmin, "document:read");
        System.out.println("loginAttempt | tokenFlag="
            + loginAttempt.isAuthenticated());
        System.out.println("anonymous | tokenFlag="
            + anonymous.isAuthenticated()
            + " | isAnonymous=" + resolver.isAnonymous(anonymous));
    }
}
~~~

Chạy với JDK 17+ và Gradle 8.x:

~~~bash
gradle run --quiet
~~~

Kết quả stdout:

~~~text
alice | tokenFlag=true | document:write=false
alice | tokenFlag=true | document:write=true
bob | tokenFlag=true | document:read=false
loginAttempt | tokenFlag=false
anonymous | tokenFlag=true | isAnonymous=true
~~~

**Phân tích kết quả:**

1. Cùng principal tên `alice`, hai đối tượng authentication trong bài thử có tập authority khác nhau. Danh tính **không đủ** để suy ra quyền của một phiên hay một token cụ thể.
2. `bob` có `ROLE_ADMIN` nhưng **không có** `document:read`. Hàm `check` kiểm tra chuỗi authority chính xác nên trả `false`. Chương trình không định nghĩa quy tắc “ROLE_ADMIN tương đương document:read”.
3. `loginAttempt` chưa qua xác thực nên có `tokenFlag=false`. Mật khẩu ở đây chỉ là dữ liệu thử, không có `AuthenticationManager` nào kiểm tra nó.
4. `anonymous` có `tokenFlag=true` nhưng `AuthenticationTrustResolver` vẫn nhận biết đó là anonymous. Chỉ dựa vào raw flag sẽ dẫn tới suy luận sai.
5. Constructor/factory `authenticated(...)` được dùng **chỉ để dựng fixture**. Trong hệ thống thực, object được tin cậy phải do cơ chế xác thực hợp lệ cung cấp; không tạo tùy ý token authenticated dựa trên username client gửi lên.

Chương trình `check` là phép kiểm tra quyền trực tiếp để học tập. Nó **không** thay thế `AuthorizationManager`, method security hay chính sách truy cập tài nguyên trong ứng dụng Spring.

## 6. Spring Security đưa danh tính và tập quyền đi qua request như thế nào?

Trong trường hợp phổ biến, luồng có dạng:

~~~text
Credentials / session / bearer token
          |
          v
AuthenticationManager + AuthenticationProvider
(hoặc thành phần xác thực tương đương của cơ chế đang dùng)
          |
          v
Authentication thành công:
  - principal
  - authenticated state
  - GrantedAuthority[]
          |
          v
SecurityContext theo phạm vi request/security execution
          |
          v
AuthorizationManager:
  - yêu cầu endpoint/method là gì?
  - authority được cấp có khớp chính sách không?
  - nếu kiểm tra ở mức domain, tài nguyên có thuộc quyền truy cập không?
          |
          +-- từ chối khi không đạt
          |
          v
Cho phép thực hiện business logic
~~~

Bước xác thực có thể tải authorities qua `UserDetailsService` đối với login username/password; hoặc chuyển scopes/claims từ token sang authorities qua converter đối với OAuth2 Resource Server; hoặc thông qua cơ chế tùy chỉnh. **Nguồn authorities và cách ánh xạ chúng phụ thuộc cấu hình**, không nên đoán từ tên user, tên role ở DB hoặc nội dung JWT nguyên gốc.

Đối với Servlet, `Authentication` thường được đặt trong `SecurityContext`, với `SecurityContextHolder` cung cấp API truy cập. Đối với WebFlux, Spring Security duy trì ngữ cảnh này trong Reactor Context và đọc qua `ReactiveSecurityContextHolder`; logic so sánh danh tính–quyền vẫn tương tự.

## 7. Kiểm tra quyền URL khác với kiểm tra “đăng nhập là đủ”

Ví dụ cấu hình cho ứng dụng Spring Security Servlet (Spring Security 6.x), đặt trong một class `@Configuration` của ứng dụng có Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.POST, "/documents/**")
                .hasAuthority("document:write")
            .requestMatchers(HttpMethod.DELETE, "/documents/**")
                .hasAuthority("document:delete")
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Các import cần thiết: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain` và `org.springframework.http.HttpMethod`. Đây là đoạn cấu hình **ghép vào ứng dụng Spring**, không phải file Java độc lập; ứng dụng còn cần cấu hình thực sự của cơ chế xác thực.

**Ý nghĩa từng kiểu kiểm tra:**

- `permitAll()`: URL công khai, không bắt buộc identity.
- `authenticated()`: yêu cầu một principal được hệ thống công nhận là authenticated theo Spring Security; không yêu cầu authority nghiệp vụ cụ thể.
- `hasAuthority("document:read")`: yêu cầu quyền đọc đúng tên, dù principal là Alice hay Bob.
- `hasRole("ADMIN")`: theo tiền tố role mặc định, yêu cầu `ROLE_ADMIN`.
- `denyAll()`: từ chối các request chưa được liệt kê — một chiến lược mặc định an toàn khi chủ đích chỉ mở một tập API nhỏ.

Thứ tự matcher quan trọng: Spring Security áp dụng quy tắc đầu tiên phù hợp cho một request trong `authorizeHttpRequests`. Do đó, không đặt `/documents/**.authenticated()` trước quy tắc `GET /documents/**.hasAuthority("document:read")` nếu muốn bảo vệ GET bằng quyền đọc: matcher rộng có thể bắt request trước.

**Một lưu ý độc lập:** Với Spring Security Servlet bật CSRF protection, một request `POST` hoặc `DELETE` từ trình duyệt có thể bị từ chối vì thiếu/không hợp lệ CSRF token ngay cả khi authority đúng. Đây là cơ chế bảo vệ khác với kiểm tra authority. Không tắt CSRF chỉ để làm ví dụ authority “chạy được” mà chưa đánh giá mô hình ứng dụng.

### Ví dụ yêu cầu `hasRole` và `hasAuthority`

Nếu `Authentication.getAuthorities()` hiện chứa:

~~~text
["ROLE_EDITOR", "document:read"]
~~~

thì:

| Quy tắc | Kết quả | Vì sao |
| --- | --- | --- |
| `authenticated()` | Cho qua bước kiểm tra trạng thái xác thực nếu token được công nhận | Chỉ yêu cầu authenticated |
| `hasRole("EDITOR")` | Đạt | Mặc định so với `ROLE_EDITOR` |
| `hasAuthority("ROLE_EDITOR")` | Đạt | So khớp chuỗi đúng |
| `hasAuthority("document:write")` | Không đạt | Quyền này không được cấp |
| `hasRole("ADMIN")` | Không đạt | Thiếu `ROLE_ADMIN` |

Kết quả trên giả sử đây là principal đã thực sự được công nhận, không phải anonymous token; không bao gồm các cơ chế bảo vệ request khác.

## 8. Kiểm tra quyền ở phương thức và tài nguyên cụ thể

Quyền chỉ được gắn với URL thường chưa đủ. Một service có thể được gọi qua REST, job nội bộ hoặc nơi khác; và cùng quyền `document:read` không nhất thiết cho phép xem **mọi** tài liệu.

Để bật kiểm tra method security với Spring Security, khai báo `@EnableMethodSecurity` trên configuration class; Spring Boot Starter Security không tự bật toàn bộ method authorization. Ví dụ minh họa:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Trong một Spring-managed service:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public Document loadDocument(long id) {
    return documentRepository.findById(id).orElseThrow();
}
~~~

Hai đoạn trên là **mã minh họa tích hợp**, không phải chương trình Java tự chạy: `Document`, `documentRepository` và Spring-managed service do ứng dụng cụ thể định nghĩa. `@PreAuthorize` cần method security thực sự được bật, thường áp dụng qua Spring proxy khi lời gọi đi qua bean; self-invocation bên trong cùng instance có thể bỏ qua proxy advice.

Điều kiện trên mới kiểm tra *quyền đọc nói chung*. Nếu hệ thống yêu cầu chỉ xem tài liệu của mình, cần thêm chính sách cấp tài nguyên dựa trên dữ liệu đáng tin cậy:

~~~text
Subject:     alice
Action:      document:read
Resource:    document #42, owner=bob
Authority:   alice có document:read
Policy:      document owner phải trùng subject

Kết quả:    DENY dù authentication hợp lệ và authority có mặt
~~~

Đưa kiểm tra ownership/tenant vào policy/service, lấy owner thật từ dữ liệu server thay vì tin vào `ownerId` do client gửi; tránh dùng mỗi `id` từ URL để suy ra quyền. Có thể kết hợp `@PreAuthorize` với một bean chính sách, ví dụ khái niệm `@documentPolicy.canRead(authentication, #id)`, trong đó policy thực sự truy vấn quyền sở hữu/quan hệ với tài nguyên trước khi trả kết quả. Đừng coi biểu thức đó là cơ chế kiểm tra ownership nếu bean chưa được triển khai.

### Authentication không phải authorization decision

Ví dụ kiểm tra thủ công:

~~~java
// Chỉ minh họa API; đây không phải authorization policy hoàn chỉnh.
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
String username = auth.getName();
boolean hasRead = auth.getAuthorities().stream()
    .anyMatch(a -> "document:read".equals(a.getAuthority()));
~~~

Ở đây `username` cho biết identity, `hasRead` cho biết một authority có tồn tại, nhưng chưa trả lời câu hỏi **Alice có được xem document #42 trong tenant Y hôm nay không?**. Câu trả lời đúng cần chính sách có đủ thuộc tính về resource và context.

## 9. Các tầng phân quyền có nhiệm vụ khác nhau

| Tầng | Quyết định tiêu biểu | Nguy cơ nếu thiếu |
| --- | --- | --- |
| Request/endpoint | `GET /documents/**` cần `document:read` | Truy cập endpoint nhạy cảm từ bên ngoài |
| Method/service | `approveInvoice()` cần `invoice:approve` | Một đường gọi nội bộ bỏ qua kiểm tra ở controller |
| Object/domain | Ai được xem tài liệu có `ownerId=...`? | IDOR/BOLA: đổi ID để đọc đối tượng người khác |
| Data/query | Giới hạn truy vấn theo tenant/owner thật | Trả về dữ liệu vượt phạm vi dù endpoint hợp lệ |

Không coi vai trò `ADMIN` là ngoại lệ ngầm với mọi kiểm tra tenant, quyền riêng tư hoặc quy tắc nghiệp vụ. Nếu một nhóm người dùng cần quyền xuyên tenant, hãy mô tả và kiểm soát ngoại lệ ấy bằng policy rõ ràng, có audit, thay vì diễn giải tự động từ tên role.

## 10. Quyền thay đổi theo thời gian và theo ngữ cảnh

Cùng một principal có thể có tập authorities khác nhau vì:

1. Một user có nhiều tenant/phòng ban; quyền trong tenant A không nhất thiết hợp lệ trong tenant B.
2. Role được đổi sau khi đăng nhập, nhưng session/JWT hiện tại vẫn mang tập claims hoặc authorities cũ cho tới khi được làm mới, hết hạn hoặc bị vô hiệu hóa theo thiết kế.
3. Một token được cấp scope hẹp chỉ cho đọc dù user có role rộng trong một hệ thống khác.
4. Một user có authority đọc nhưng resource đang bị khóa, đã bị thu hồi chia sẻ hoặc thuộc người khác.

**Quyền thực tế = identity đã được hệ thống tin cậy + grants được áp dụng + policy theo action/resource/context.** Không sao chép mọi role từ database vào token rồi cho rằng chúng sẽ luôn là trạng thái mới nhất; cần thiết kế chu kỳ refresh/revocation thích hợp với mức độ rủi ro.

Không lấy `getName()` làm định danh duy nhất nếu cùng tên có thể xuất hiện ở nhiều nguồn danh tính hoặc tenant. Ưu tiên stable user ID/subject được xác minh và kết hợp tenant boundary đúng cách; tuyệt đối không tin principal hoặc authority do client tự khai báo mà chưa được xác minh.

## 11. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| “Đã đăng nhập thì được sửa dữ liệu” | Trộn authentication với authorization | Dùng `hasAuthority`/policy riêng cho hành động |
| Dùng `isAuthenticated()` như bằng chứng chắc chắn không anonymous | Anonymous token có thể trả `true` | Dùng cơ chế `authenticated()`/`AuthenticationTrustResolver` |
| Gán `ROLE_ADMIN` nhưng gọi `hasAuthority("ADMIN")` | Sai chuỗi authority | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Thấy claim `scope=read` rồi đòi `hasAuthority("read")` | Resource server có thể ánh xạ sang `SCOPE_read` | Kiểm tra converter và chuỗi authority thực |
| Kiểm tra `document:read` rồi trả mọi document ID | Thiếu object-level authorization | Kiểm tra owner/tenant theo dữ liệu server |
| Tin quyền gửi từ body/header không được xác minh | Client tự nâng quyền | Authorities chỉ đến từ nguồn đã xác thực/kiểm soát |
| Tự tạo authenticated token từ dữ liệu request | Bỏ qua quá trình xác thực hợp lệ | Để `AuthenticationProvider`/cơ chế tin cậy xác nhận |
| Test chỉ dùng `@WithMockUser` mặc định rồi kết luận đủ quyền | Mock có thể mang authority khác production | Test cả đúng/sai authority và đường mapping thực |
| Ghi log toàn bộ `Authentication` | Có thể làm lộ thông tin nhạy cảm | Chỉ log user ID tối thiểu và quyết định audit cần thiết |
| Đọc `SecurityContextHolder` trong WebFlux như Servlet | Context reactive có semantics khác thread-local | Dùng `ReactiveSecurityContextHolder` trong pipeline |

## 12. Test đúng ranh giới danh tính và quyền

Một bộ kiểm thử tốt nên tách tình huống thành hai trục: **authentication state** và **granted authorities**. Ví dụ cho endpoint đọc tài liệu, với policy bắt buộc `document:read` và owner đúng:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Chưa đăng nhập / token không hợp lệ | Bị chặn tại authentication/entry point |
| Đã xác thực, không có `document:read` | Bị từ chối ở authorization |
| Đã xác thực, có `document:read`, đúng owner | Được phép nếu các điều kiện khác đều đạt |
| Đã xác thực, có `document:read`, sai owner | Bị từ chối bởi policy cấp tài nguyên |
| Đã xác thực, chỉ có `ROLE_ADMIN`, không có mapping quyền đọc | Theo quy tắc authority cụ thể, không mặc nhiên đạt |
| Một người dùng với token mới có grant khác token cũ | Quyết định phải dựa trên grants thực sự đang áp dụng |

Với `spring-security-test`, `@WithMockUser(username = "alice", authorities = "document:read")` mô phỏng identity và authority phục vụ bài test ở method/HTTP layer; `@WithMockUser(roles = "ADMIN")` tạo authority role theo tiền tố. Test mock như vậy kiểm tra **authorization**, không chứng minh quá trình login/token validation thật hoạt động. Muốn kiểm tra ánh xạ JWT scope/role và credentials thực, bổ sung integration test cho đường xác thực tương ứng.

Nên xác minh cả phản hồi không được cấp quyền lẫn việc logic dữ liệu **không được thực thi** khi bị từ chối. Với những hệ thống multi-tenant, kiểm thử truy cập chéo tenant bằng cùng document ID là đặc biệt có giá trị.

## 13. Tự kiểm tra

**Câu 1.** Alice đăng nhập thành công và `isAuthenticated()` trả `true`. Alice có được gọi endpoint yêu cầu `hasAuthority("invoice:approve")` không?

**Đáp án:** Chỉ khi `Authentication` mang authority `invoice:approve` và các chính sách khác cũng cho phép. Trạng thái xác thực riêng lẻ không đủ.

**Câu 2.** Trong mặc định của Spring Security, tại sao `hasRole("AUDITOR")` và `hasAuthority("AUDITOR")` có thể trả kết quả khác?

**Đáp án:** `hasRole("AUDITOR")` kiểm tra chuỗi `ROLE_AUDITOR` theo tiền tố mặc định, còn `hasAuthority("AUDITOR")` kiểm tra đúng chuỗi `AUDITOR`. Kết quả phụ thuộc authorities được cấp và cấu hình tiền tố.

**Câu 3.** Vì sao không nên dùng `authentication.isAuthenticated()` làm phép thử duy nhất để phân biệt khách nặc danh với người đăng nhập?

**Đáp án:** `AnonymousAuthenticationToken` có thể mang trạng thái `isAuthenticated() == true` dù biểu diễn anonymous principal. Cơ chế authorization/trust resolver của Spring Security có phân biệt loại token này.

**Câu 4.** Nếu Alice có `document:read`, liệu Alice có quyền xem document thuộc Bob?

**Đáp án:** Chưa đủ dữ kiện. Quyền đọc tổng quát không phải quyền đối với mọi object. Nếu policy yêu cầu owner trùng principal hoặc thuộc cùng tenant, cần kiểm tra chính sách đó trên dữ liệu do server kiểm soát.

**Câu 5.** Một JWT có claim `roles=["ADMIN"]`. Vì sao `hasRole("ADMIN")` có thể vẫn thất bại?

**Đáp án:** Role claim chỉ có ích cho Spring Security authorization nếu converter được cấu hình để ánh xạ thành `GrantedAuthority` thích hợp (thường `ROLE_ADMIN`). Đọc raw JWT claim không đồng nghĩa authority đã được cấp trong `Authentication`.

## 14. Kết luận và tài liệu đọc tiếp

**Xác thực xác lập chủ thể được tin cậy; phân quyền so sánh grants cùng chính sách với thao tác và tài nguyên cụ thể.** Trong Spring Security, hai nhóm dữ liệu cùng có thể nằm trong `Authentication`, nhưng chúng trả lời hai câu hỏi khác nhau. Nắm được điều này giúp chọn đúng API `getName`, `getAuthorities`, `hasAuthority`, `hasRole` và tránh cấp quyền chỉ vì user đã đăng nhập.

Tài liệu chính thức:

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
