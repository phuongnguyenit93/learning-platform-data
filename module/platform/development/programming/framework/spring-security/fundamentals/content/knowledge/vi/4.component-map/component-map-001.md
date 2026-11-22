# SecurityContext chứa Authentication và danh tính hiện tại như thế nào?

> **Một ý tưởng cốt lõi:** Khi Spring Security đã xử lý xác thực cho một request, thông tin về **chủ thể đang thực hiện request đó** thường được biểu diễn bằng đối tượng `Authentication`, nằm trong `SecurityContext`, và mã ứng dụng truy cập context hiện tại qua `SecurityContextHolder`. Đừng hiểu `SecurityContext` là “session của trình duyệt” hoặc “database user”; nó là vùng chứa trạng thái bảo mật cho một phạm vi thực thi, được nạp và dọn theo cơ chế Spring Security.

Bài này thuộc nhóm **Bản đồ thành phần** của Spring Security, tập trung vào mô hình Spring MVC/Servlet và Spring Security 6.x. Ví dụ chạy bằng Java 17 và Spring Boot 3.5.x. Với WebFlux/reactive, cách truyền context dựa vào **Reactor Context**, không dùng mô hình `ThreadLocal` của Servlet làm giả định mặc định.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Vẽ quan hệ giữa `SecurityContextHolder`, `SecurityContext`, `Authentication`, `principal`, `credentials` và `GrantedAuthority`.
2. Giải thích authentication được tạo như thế nào sau login/Basic/Bearer, được đặt vào context ở đâu và tồn tại bao lâu.
3. Lấy username/principal/authorities an toàn trong controller hoặc service; phân biệt `authentication.getName()` với kiểu đối tượng trong `authentication.getPrincipal()`.
4. Hiểu vì sao `isAuthenticated() == true` **chưa đủ** để kết luận request do người dùng thật đăng nhập, và vì sao role khác quyền trên một tài nguyên cụ thể.
5. Phân biệt **lưu context cho request đang chạy** và **duy trì danh tính qua các request** bằng session, cookie hoặc xác thực lại từ token.
6. Tránh lỗi rò rỉ context qua thread pool, giả định sai với `@Async` và tự đặt `Authentication` chưa qua kiểm chứng.

## 2. Bản đồ thành phần

```text
                      Authentication mechanism
             (form login, HTTP Basic, JWT, OAuth2...)
                              |
                              v
                 AuthenticationManager / Provider
              [kiểm tra credential/nguồn danh tính]
                              |
                              v
                    Authentication (kết quả)
                name | principal | credentials
                 authorities | details | authenticated
                              |
                              v
                      SecurityContext
                 [authentication = object ở trên]
                              |
                              v
                    SecurityContextHolder
                [context hiện tại của luồng xử lý]
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
    URL/method authorization             Controller/Service
    (đọc authorities, identity)        (đọc current principal)
```

Các thành phần có vai trò khác nhau:

| Thành phần | Nó là gì? | Dùng để làm gì? |
| --- | --- | --- |
| `SecurityContextHolder` | API giữ/truy xuất context hiện tại qua `SecurityContextHolderStrategy`, mặc định dựa trên `ThreadLocal` trong Servlet | Trả về `SecurityContext` cho luồng đang xử lý |
| `SecurityContext` | Một đối tượng chứa `Authentication` | Gom thông tin bảo mật đã gắn với lần xử lý hiện tại |
| `Authentication` | Interface biểu diễn yêu cầu xác thực hoặc kết quả xác thực | Mang principal, credential, authority, chi tiết và trạng thái xác thực |
| `principal` | Chủ thể mà authentication biểu diễn, có kiểu tùy cơ chế | Xác định user/service account; ví dụ `UserDetails`, `Jwt`, `OAuth2User` |
| `credentials` | Thông tin dùng chứng minh danh tính, như password/token | Thường dùng lúc xác thực; có thể đã được xóa sau xác thực |
| `GrantedAuthority` | Permission/role/scope được cấp cho principal | Đầu vào cho authorization như `ROLE_USER`, `SCOPE_read` |
| `AuthenticationManager` | Hợp đồng thực hiện xác thực | Nhận token xác thực, trả token kết quả hoặc ném lỗi |
| `AuthenticationProvider` | Một cách xác minh credential cụ thể | Kiểm tra password, token hoặc cơ chế tương ứng |
| `SecurityContextRepository` | Cách đọc/ghi context qua request/response | Có thể liên hệ context với HTTP session, request attribute hoặc không lưu |

**Quan hệ được hỏi trực tiếp:**

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();

if (authentication != null) {
    String identityName = authentication.getName();
}
```

Đoạn này là mã minh họa để đặt trong luồng có Spring Security, **không phải một chương trình Java độc lập**. Nó đọc context đã được Spring Security gắn cho thread, rồi lấy authentication nếu có. Cần đặc biệt thận trọng với request ẩn danh, task chạy nền hoặc code không nằm trong security filter chain: `authentication` có thể `null` hoặc là anonymous token.

## 3. SecurityContext chứa gì, và không chứa gì?

`SecurityContext` là một interface nhỏ, có thao tác chính:

```java
Authentication authentication = context.getAuthentication();
context.setAuthentication(authentication);
```

Trong thực tế, context thường là `SecurityContextImpl`. Bản thân nó không chứa toàn bộ hệ thống người dùng; nó tham chiếu đến `Authentication` hiện tại. User profile, mật khẩu đã mã hóa trong database, thông tin tenant và ACL có thể nằm ở nơi khác. Đừng coi mọi thông tin của user trong persistence layer đều được tự động nạp vào context.

### 3.1. Các trường quan trọng trên Authentication

| API | Ý nghĩa chính | Cẩn thận |
| --- | --- | --- |
| `getName()` | Tên chủ thể theo cơ chế authentication | Với JWT/OIDC có thể là `sub` hoặc tên được ánh xạ; không mặc định là email |
| `getPrincipal()` | Đối tượng mô tả chủ thể | Có thể là `UserDetails`, chuỗi, `Jwt`, `OAuth2User` hoặc custom principal |
| `getCredentials()` | Dữ liệu chứng minh danh tính | Thường bị xóa sau khi xác thực; **không log, không trả về API** |
| `getAuthorities()` | Các quyền mức cao của principal | Không thay kiểm tra owner/tenant/resource |
| `getDetails()` | Metadata phụ theo kiểu authentication, ví dụ thông tin request | Không coi IP/metadata từ client là bằng chứng quyền |
| `isAuthenticated()` | Cờ trạng thái của đối tượng authentication | **Có thể true với `AnonymousAuthenticationToken`** |
| `setAuthenticated(...)` | Phương thức của interface cho một số implementation | Không được tự gắn `true` để “vượt qua login” |

Ví dụ khi Alice đăng nhập bằng username/password với `UserDetailsService`, authentication sau thành công có thể tương tự:

```text
SecurityContextImpl
└── Authentication = UsernamePasswordAuthenticationToken
    ├── principal = UserDetails(username="alice", ...)
    ├── credentials = null                  (đã xóa, tùy provider)
    ├── authorities = [ROLE_USER, PROFILE_READ]
    ├── details = WebAuthenticationDetails  (nếu có)
    └── authenticated = true
```

Với API dùng JWT Resource Server:

```text
SecurityContext
└── Authentication = JwtAuthenticationToken
    ├── principal = Jwt (claims đã được decoder xác minh)
    ├── name = thường từ claim "sub", tùy cấu hình
    ├── authorities = ví dụ [SCOPE_profile.read]
    └── authenticated = true
```

Hai authentication trên có thể mang cùng “người dùng Alice”, nhưng **không có cùng class principal**. Vì vậy, ép mọi principal về `UserDetails` là lỗi nếu ứng dụng hỗ trợ OAuth2/JWT. Với hệ thống thật, nên ánh xạ principal từ cơ chế tin cậy sang một **user ID nội bộ ổn định** để kiểm tra ownership/tenant, tránh dùng tên hiển thị hoặc email có thể thay đổi làm khóa nghiệp vụ.

### 3.2. Authentication cũng có thể là yêu cầu chưa được xác thực

Interface `Authentication` có **hai vai trò**:

- **Input:** token được tạo từ credential nhận được, ví dụ username/password chưa xác minh. `isAuthenticated()` thường là `false`.
- **Output:** sau `AuthenticationManager.authenticate(...)` thành công, provider trả authentication biểu diễn chủ thể đã được kiểm chứng, kèm authorities phù hợp.

Một cách nhìn khái niệm (không phải code cần tự viết cho form login mặc định):

```java
// Minh họa mô hình: các biến authenticationManager, username, password
// là đầu vào đã được cung cấp ở luồng xử lý riêng.
Authentication pending =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

Authentication verified = authenticationManager.authenticate(pending);
// verified là kết quả được provider chấp nhận hoặc authenticate() ném lỗi.
```

Nếu authentication thất bại, Spring Security không được dùng credential chưa xác minh như danh tính đã đăng nhập. Không viết code kiểu `new UsernamePasswordAuthenticationToken(username, null, authorities)` với quyền tự do lấy từ JSON client rồi gắn vào holder; constructor có authorities thường tạo token đã đánh dấu authenticated. Một API phải kiểm tra credential/claims trước khi cấp quyền.

## 4. SecurityContextHolder truy cập “hiện tại” bằng cách nào?

### 4.1. Mặc định trong Spring MVC/Servlet: ThreadLocal

Mặc định, `SecurityContextHolder` dùng chiến lược `MODE_THREADLOCAL`. Khi request đã được filter chain khởi tạo context, mã chạy **trên cùng luồng xử lý** thường có thể gọi `SecurityContextHolder.getContext()` mà không cần truyền context qua mọi hàm. Đó là ý nghĩa của chữ **current**: hiện tại **trong execution context** đang chạy, không phải một biến toàn cục cho toàn bộ JVM.

```text
Request Alice -> worker thread T1 -> Holder(T1) -> Context(Alice)
Request Bob   -> worker thread T2 -> Holder(T2) -> Context(Bob)
                                       |
                        Không chia sẻ context mặc định
```

Servlet container **tái sử dụng thread** để phục vụ các request khác nhau. Spring Security chịu trách nhiệm dọn holder khi request đi qua filter chain hoàn tất, tránh mang authentication của request A sang request B dùng lại thread. Nếu bạn tự thiết lập holder ngoài cơ chế chuẩn, cần xử lý vòng đời và dọn context bằng `try/finally` trong phạm vi do mình quản lý.

**Không** đặt current user vào biến `static`, singleton field của controller/service hoặc cache dùng chung với kỳ vọng mỗi request có giá trị khác nhau. Những vị trí đó có thể chia sẻ giữa nhiều thread và gây lộ danh tính giữa user.

### 4.2. Có thể lấy context ở nhiều lớp, nhưng cần chọn đúng API

Trong servlet service, có thể dùng:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication auth = context.getAuthentication();

if (auth == null) {
    // Không có authentication trong holder ở vị trí này.
    return;
}

String name = auth.getName();
Collection<? extends GrantedAuthority> roles = auth.getAuthorities();
```

Các import tương ứng:

```java
import java.util.Collection;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
```

Trong Spring MVC controller, nên ưu tiên tham số đã được framework resolve, vì rõ dependency và dễ test:

```java
// Minh họa phần method trong một @RestController.
@GetMapping("/me")
String me(Authentication authentication) {
    return authentication.getName();
}
```

Đối với principal cụ thể:

```java
// Chỉ phù hợp nếu cơ chế xác thực thật sự cung cấp UserDetails.
@GetMapping("/username")
String username(@AuthenticationPrincipal UserDetails principal) {
    return principal.getUsername();
}
```

Đối với toàn bộ context:

```java
@GetMapping("/context")
String name(@CurrentSecurityContext SecurityContext context) {
    Authentication auth = context.getAuthentication();
    return auth == null ? "(none)" : auth.getName();
}
```

`@AuthenticationPrincipal` và `@CurrentSecurityContext` thuộc `org.springframework.security.core.annotation`. Với tham số `Authentication` hoặc `Principal` thông thường, Spring MVC có thể lấy principal từ `HttpServletRequest`. Với request anonymous, tham số `Authentication` có thể **null** dù `SecurityContextHolder` vẫn có `AnonymousAuthenticationToken`. Nếu cần nghiên cứu context anonymous thực sự, dùng `@CurrentSecurityContext` hoặc holder, không dựa vào cast từ `HttpServletRequest.getUserPrincipal()`.

### 4.3. Vì sao SecurityContextHolder chỉ trả “danh tính hiện tại”, không phải quyền với dữ liệu?

Giả sử:

```text
Authentication:
  name = alice
  authorities = [ROLE_USER, REPORT_READ]
Request:
  GET /reports/99
Database:
  report 99.owner = bob
```

`Authentication` đủ để biết actor là Alice và có quyền chung `REPORT_READ`. Nó **không trả lời** report 99 thuộc ai. Service/repository phải kiểm tra owner, tenant, ACL, trạng thái và các ràng buộc nghiệp vụ đáng tin. Nếu chỉ kiểm tra `authentication.isAuthenticated()` hoặc `hasRole("USER")`, có thể gây lỗi IDOR/BOLA.

Nên hiểu hai chức năng tách nhau:

- **Authentication** cung cấp identity và authorities đã xác minh.
- **Authorization** áp policy cho action/resource, có thể đọc thông tin từ authentication **và** database, input đã kiểm chứng.

## 5. Luồng thực tế: từ request đến Authentication trong SecurityContext

Giả sử request sử dụng HTTP Basic:

```text
GET /me
Authorization: Basic <giá trị Base64 của username:password>
          |
          v
Servlet Filter Chain -> FilterChainProxy -> SecurityFilterChain
          |
          +-- SecurityContextHolderFilter
          |     lấy SecurityContext (hoặc deferred context) từ repository
          |
          +-- BasicAuthenticationFilter
          |     tạo authentication request từ Basic credentials
          |     gọi AuthenticationManager / provider
          |     nếu hợp lệ: gắn Authentication vào context hiện tại
          |
          +-- AnonymousAuthenticationFilter (nếu cần)
          |     cung cấp anonymous authentication nếu chưa có actor hợp lệ
          |
          +-- AuthorizationFilter
          |     quyết định GET /me có được đi tiếp không
          v
Controller / Service
          |
          v
SecurityContextHolder.getContext().getAuthentication()
          |
          v
Response; Spring Security dọn context khỏi holder cho request
```

Đây là mô hình khái niệm, không phải dump thứ tự mọi filter trong mọi ứng dụng. Filter thực tế phụ thuộc phiên bản, cấu hình, cơ chế login/JWT, các `SecurityFilterChain` và dispatcher type. Đối với Basic, request thường cần gửi credential ở mỗi lần gọi để được xác thực; khi dùng cấu hình stateless, không có chuyện một context ThreadLocal sống mãi sang request kế tiếp.

Các bước quan trọng:

1. **Bắt đầu request:** Spring Security thiết lập cơ chế truy cập context cho lần xử lý hiện tại. Context có thể được lấy từ `SecurityContextRepository` hoặc mới/không có authentication.
2. **Xác thực:** filter tương ứng chọn credential, gọi provider. Provider xác minh password/token/chứng thư trước khi tạo authentication tin cậy.
3. **Gắn vào context:** khi authentication thành công, context hiện tại mang kết quả để các filter phân quyền và handler dùng tiếp.
4. **Phân quyền:** có thể dựa vào authorities, trạng thái authenticated, cấu hình URL/method hoặc policy tùy chỉnh.
5. **Kết thúc request:** holder được dọn để request khác không nhận nhầm identity. Nếu ứng dụng yêu cầu tiếp tục đăng nhập giữa các request, persistence phải được xử lý qua repository và cơ chế session/token tương ứng.

### 5.1. Form login và session

Với ứng dụng web dùng session-based login, sau khi người dùng đăng nhập thành công, Spring Security có thể lưu security context trong HTTP session thông qua `SecurityContextRepository`. Ở request sau, cookie session đóng vai trò tìm session server tương ứng; framework nạp context cho request mới. **Cookie không phải bản sao đầy đủ của SecurityContext**, và context holder của thread mới không phải chính đối tượng ThreadLocal ở thread trước.

Theo mặc định phổ biến của Spring Security 6, `DelegatingSecurityContextRepository` kết hợp `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`. Thành phần request attribute giúp context còn dùng được qua một số dispatch như ERROR trong cùng request; HTTP session giúp liên hệ context giữa các request khi dùng session. Tuy nhiên, chính sách session, authentication mechanism và repository có thể được thay thế.

### 5.2. HTTP Basic/Bearer và API stateless

Với API stateless, mỗi request mang Basic credentials hoặc Bearer token. Spring Security xác thực lại credential/token theo cấu hình rồi tạo `Authentication` cho **request hiện tại**. Không có session server để nhớ người dùng giữa hai request trong mô hình này.

- Basic: `Authentication` thường là `UsernamePasswordAuthenticationToken` với `UserDetails` là principal sau provider xác minh.
- Bearer JWT Resource Server: `Authentication` thường là `JwtAuthenticationToken` với `Jwt` làm principal, các scope/role đã được ánh xạ. Chữ ký/issuer/audience/expiry và những claim bắt buộc phải được cấu hình kiểm tra phù hợp.
- Opaque token Resource Server: introspection và kiểu principal có thể khác JWT. Không nên giả định tất cả API Bearer đều có `Jwt`.
- OAuth2 Login/OIDC cho browser có thể tạo `OAuth2AuthenticationToken` với `OAuth2User`/`OidcUser` tùy flow. Context thường được duy trì theo session tương ứng.

### 5.3. Khi tự xây authentication, phải hiểu việc lưu context

Trong Spring Security 6, `SecurityContextHolderFilter` chủ yếu **nạp** context, không tự lưu mọi chỉnh sửa vào session. Nếu một custom filter/controller tự xác thực và muốn đăng nhập tiếp tục ở request sau, chỉ gọi `SecurityContextHolder.setContext(...)` thường **chưa đủ**. Phải dùng `SecurityContextRepository.saveContext(context, request, response)` theo thiết kế persistence phù hợp.

```java
// Mã minh họa bên trong một custom login handler có sẵn:
//  - AuthenticationManager authenticationManager
//  - SecurityContextRepository securityContextRepository
//  - HttpServletRequest request
//  - HttpServletResponse response
//  - String username, password
// Không copy đoạn này làm endpoint login production nếu chưa thiết kế đầy đủ
// CSRF, session fixation, failure handling và session authentication strategy.
Authentication pending =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

Authentication verified = authenticationManager.authenticate(pending);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
```

Ở snippet trên, `createEmptyContext()` tạo context mới thay vì lấy một context dùng chung rồi sửa tại chỗ; đó là hướng an toàn hơn khi có khả năng nhiều thread chia sẻ tham chiếu. Khi cần thực hiện đăng nhập tùy chỉnh, hãy tận dụng authentication filter/handler có sẵn để xử lý thêm session fixation, remember-me, redirect, events và error semantics đúng.

**Nhớ:** `SecurityContextRepository` là cách liên hệ context giữa các request, còn `SecurityContextHolder` là cách mã đang chạy truy cập context. Hai vai trò khác nhau.

## 6. Anonymous authentication: cái bẫy của isAuthenticated()

Khi anonymous authentication được bật (thường là mặc định trong HTTP Security), `AnonymousAuthenticationFilter` có thể đặt `AnonymousAuthenticationToken` trong context cho request chưa đăng nhập.

Ví dụ:

```text
SecurityContextHolder.getContext().getAuthentication()
  class: AnonymousAuthenticationToken
  name: anonymousUser
  authorities: [ROLE_ANONYMOUS]
  isAuthenticated(): true
```

Điều này **không có nghĩa khách chưa đăng nhập được xem như user hợp lệ**. `isAuthenticated()` là trạng thái của token object, và `AnonymousAuthenticationToken` thường trả `true`. Spring Security có `AuthenticationTrustResolver` để phân biệt anonymous, remember-me và fully authenticated theo yêu cầu của từng rule. Khi viết rule HTTP, dùng `authenticated()`/`fullyAuthenticated()`/`anonymous()` và các API phân quyền tương ứng; framework biết cách đánh giá anonymous thay vì tin một phép kiểm tra Boolean thô.

**Không nên viết logic bảo vệ endpoint như sau:**

```java
// SAI nếu chỉ dùng cờ Boolean làm bằng chứng user thật:
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
if (auth != null && auth.isAuthenticated()) {
    // Dòng này có thể chạy cho AnonymousAuthenticationToken.
}
```

Đối với mã cần đánh giá danh tính ở service không có rule method, có thể dùng policy rõ ràng hoặc `AuthenticationTrustResolver`:

```java
// Đoạn minh họa (không phải chương trình độc lập).
AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

Authentication auth = SecurityContextHolder.getContext().getAuthentication();
if (auth == null || trustResolver.isAnonymous(auth)) {
    throw new AccessDeniedException("Authentication required");
}
```

Trong ví dụ production, thường nên để Spring Security quản lý chặn quyền ở boundary bằng `@PreAuthorize` hoặc `authorizeHttpRequests`, sau đó kiểm tra owner/tenant nghiệp vụ. Khi trả lỗi, cần tuân theo hợp đồng 401 (chưa xác thực)/403 (không đủ quyền), không serialize đối tượng Authentication để debug qua API công khai.

## 7. Ví dụ chạy được: quan sát identity từ SecurityContext trong Spring Boot

Ta xây dựng một API nhỏ:

- `GET /public/context` công khai, đọc context bằng `@CurrentSecurityContext` và thể hiện sự khác nhau giữa anonymous và authenticated.
- `GET /me` yêu cầu đăng nhập, lấy `Authentication` và `@AuthenticationPrincipal UserDetails` từ Spring MVC, chỉ trả name + authorities.
- `GET /owner/{username}` minh họa service đọc context bằng `SecurityContextHolder` và từ chối truy cập dữ liệu của tên khác.
- `GET /admin` yêu cầu `ROLE_ADMIN`, minh họa authority được dùng cho rule URL.

Bài dùng **Spring Boot 3.5.16**, một phiên bản có thật trong dòng Spring Boot 3.5, Java 17, Spring Security 6.x. Các phần xử lý danh tính lưu trong bộ nhớ chỉ dành cho local/test. Dự án mới cần kiểm tra dòng Spring Boot được hỗ trợ và bản vá mới nhất.

### 7.1. Cấu trúc tệp

```text
security-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/context/SecurityContextDemoApplication.java
    └── test/java/demo/context/SecurityContextDemoApplicationTests.java
```

### 7.2. Maven dependencies

```xml
<!-- pom.xml -->
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
    <artifactId>security-context-demo</artifactId>
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

### 7.3. Toàn bộ mã ứng dụng

Tạo `src/main/java/demo/context/SecurityContextDemoApplication.java`:

```java
package demo.context;

import java.util.List;
import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityContextDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Chỉ cho ERROR dispatch của servlet container render lỗi.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/context").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/owner/*").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            // Mỗi request phải có credential riêng; không lưu login qua session.
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "PROFILE_READ")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "PROFILE_READ")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build());
    }
}

@RestController
class IdentityController {
    private final PrivateNoteService notes;

    IdentityController(PrivateNoteService notes) {
        this.notes = notes;
    }

    @GetMapping("/public/context")
    ContextView publicContext(@CurrentSecurityContext SecurityContext context) {
        Authentication auth = context.getAuthentication();
        return new ContextView(
            auth == null ? "(none)" : auth.getName(),
            auth != null && auth.isAuthenticated(),
            auth instanceof AnonymousAuthenticationToken
        );
    }

    @GetMapping("/me")
    MeView me(Authentication authentication,
              @AuthenticationPrincipal UserDetails principal) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new MeView(
            authentication.getName(),
            principal.getUsername(),
            authorities
        );
    }

    @GetMapping("/owner/{username}")
    String privateNote(@PathVariable String username) {
        return notes.readMine(username);
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-ok";
    }
}

@Service
class PrivateNoteService {
    @PreAuthorize("hasAuthority('PROFILE_READ')")
    public String readMine(String requestedOwner) {
        // Không lấy "user đang gọi" từ query parameter hoặc request body.
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || !requestedOwner.equals(auth.getName())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return "note-of-" + requestedOwner;
    }
}

// DTO trả về đúng các trường cần quan sát, không expose credentials/details.
record ContextView(String name, boolean authenticatedFlag, boolean anonymous) {}

record MeView(String name, String principalUsername,
              List<String> authorities) {}
```

Giải thích các chi tiết quyết định:

1. **`@CurrentSecurityContext SecurityContext`** cho phép controller quan sát authentication ngay cả khi request là anonymous. Khi anonymous filter đang bật, `name` thông thường là `anonymousUser`, `authenticatedFlag` có thể `true` và `anonymous` là `true`.
2. **`Authentication authentication`** ở method `/me` được framework resolve cho request đã xác thực. Trong ví dụ dùng Basic + `UserDetailsService`, `principal` nhận từ `@AuthenticationPrincipal UserDetails` tương ứng với cùng user.
3. **`SecurityContextHolder`** trong service đọc đúng identity đang gắn với request gọi đến. Đây là cách tra current context khi không truyền tường minh actor vào service; với domain phức tạp, có thể bọc nó trong adapter `CurrentUser` và truyền user ID đã kiểm chứng vào nghiệp vụ để dễ test.
4. `@EnableMethodSecurity` kích hoạt `@PreAuthorize("hasAuthority('PROFILE_READ')")` cho lời gọi từ controller qua service proxy. Bob có permission đọc profile nhưng không thể đọc profile của Alice vì service còn kiểm tra **đúng owner**.
5. `hasRole("ADMIN")` tương đương kiểm tra `ROLE_ADMIN` theo prefix mặc định, khác `hasAuthority("ADMIN")`. Tên authority phải khớp với cách đã gán cho principal.
6. **`SessionCreationPolicy.STATELESS`** được dùng có chủ ý để ví dụ không duy trì danh tính qua session. Mỗi request mới dùng HTTP Basic cần gửi credential lại để có authenticated context. `SecurityContextHolder` vẫn hoạt động **trong request**.
7. `DispatcherType.ERROR` được phép đi qua để servlet container render lỗi 404 đúng cách, nhưng không cho phép client tự do đi vào endpoint không khai báo. Các request ban đầu vẫn phải khớp rule.
8. Ví dụ chỉ dùng **GET** để đọc dữ liệu. Nếu thêm POST/PUT/DELETE, cần thiết kế CSRF/session/cookie, authorization cho method mới, validation và transaction phù hợp. Không suy ra CSRF không cần thiết cho mọi loại API.

### 7.4. Integration test với MockMvc

Tạo `src/test/java/demo/context/SecurityContextDemoApplicationTests.java`:

```java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityContextDemoApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void currentAuthenticationFollowsEachRequest() throws Exception {
        // Request ẩn danh vẫn có thể có AnonymousAuthenticationToken trong holder.
        mvc.perform(get("/public/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("anonymousUser"))
            .andExpect(jsonPath("$.anonymous").value(true))
            .andExpect(jsonPath("$.authenticatedFlag").value(true));

        // Endpoint yêu cầu auth sẽ chặn anonymous.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        // HTTP Basic thật: Spring Security xác thực qua InMemoryUserDetailsManager.
        mvc.perform(get("/me").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.principalUsername").value("alice"))
            .andExpect(jsonPath("$.authorities[0]").value("PROFILE_READ"))
            .andExpect(jsonPath("$.authorities[1]").value("ROLE_USER"));

        // Một request khác dùng danh tính Bob, không thừa hưởng Alice.
        mvc.perform(get("/me").with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("bob"));

        // Cùng một endpoint public nhưng context đã được Basic xác thực.
        mvc.perform(get("/public/context")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.anonymous").value(false));

        // Không gửi credentials cho request tiếp theo -> lại là anonymous.
        mvc.perform(get("/public/context"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.anonymous").value(true));

        // Context đúng chỉ là điều kiện đầu; service còn kiểm tra owner.
        mvc.perform(get("/owner/alice").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("note-of-alice"));

        mvc.perform(get("/owner/alice").with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isNotFound());

        // URL authorization dựa vào authorities hiện tại.
        mvc.perform(get("/admin").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        // Đường chưa khai báo bị deny; không tự mở dù đã login.
        mvc.perform(get("/unknown").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Bài test có một chuỗi kiểm chứng trong cùng phương thức: anonymous, xác thực thật bằng Basic, chuyển user giữa request, không rò rỉ context, phân quyền URL và owner check. Dùng `httpBasic(...)` kiểm thử đường xác thực qua Spring Security. Ngược lại, `@WithMockUser`/`user(...)` chủ yếu tạo principal mô phỏng để kiểm thử authorization, **không xác minh mật khẩu thật**.

### 7.5. Lệnh chạy và kết quả dự kiến

Tại thư mục có `pom.xml`, cần JDK 17+ và Maven 3.6.3+:

```bash
mvn test
mvn spring-boot:run
```

Nếu môi trường có đầy đủ dependency và cấu hình tương thích, `mvn test` chạy test phía trên; các lời gọi HTTP được kỳ vọng trả mã và JSON đã định nghĩa, không dựa vào một dòng stdout cố định từ Spring Boot.

Trong terminal khác:

```bash
curl -i http://localhost:8080/public/context
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u bob:demo-pass http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/owner/alice
curl -i -u bob:demo-pass http://localhost:8080/owner/alice
curl -i -u alice:demo-pass http://localhost:8080/admin
curl -i -u admin:demo-pass http://localhost:8080/admin
```

| Lời gọi | Status dự kiến | Minh họa |
| --- | --- | --- |
| `GET /public/context` không credential | `200` | `anonymous=true`, `name=anonymousUser` |
| `GET /me` không credential | `401` | Anonymous không vượt qua `authenticated()` |
| `GET /me` với Alice | `200` | `name=alice`, authority của Alice |
| `GET /me` với Bob | `200` | `name=bob`, độc lập với request trước |
| `GET /owner/alice` với Alice | `200` | Body `note-of-alice` |
| `GET /owner/alice` với Bob | `404` | Owner check từ authentication hiện tại |
| `GET /admin` với Alice | `403` | Không có `ROLE_ADMIN` |
| `GET /admin` với Admin | `200` | Body `admin-ok` |

Lưu ý: `curl -u` với HTTP Basic truyền mật khẩu dưới dạng Base64 trong header, **không phải mã hóa**. Các ví dụ `http://localhost` chỉ dành cho máy phát triển không có lưu lượng qua mạng không tin cậy. Production phải chạy HTTPS và thay account/password mẫu bằng nguồn identity được quản lý.

## 8. SecurityContext và xử lý bất đồng bộ, thread pool

### 8.1. Vì sao @Async có thể không thấy user?

Với mặc định `MODE_THREADLOCAL`:

```text
HTTP worker thread T1       async worker thread T2
SecurityContext(Alice)      không tự có SecurityContext(Alice)
         |
         +----- submit task -----> Runnable chạy trên T2
```

Nếu service chạy `@Async`, `CompletableFuture.supplyAsync(...)` hoặc một `Executor` riêng, mã đọc `SecurityContextHolder.getContext().getAuthentication()` trong luồng mới có thể nhận `null`. Điều này đúng theo mô hình ThreadLocal; không phải dấu hiệu “Spring Security ngẫu nhiên quên login”.

Có thể sử dụng các wrapper do Spring Security cung cấp, ví dụ `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextExecutor`, để gắn context thích hợp cho tác vụ và dọn lại trong `finally`. Ví dụ minh họa cách bọc một Runnable:

```java
// Đoạn minh họa bên trong request xử lý đã xác thực.
// Các import liên quan: java.lang.Runnable,
// org.springframework.security.concurrent.DelegatingSecurityContextRunnable.
Runnable businessTask = () -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    System.out.println(auth == null ? "(none)" : auth.getName());
};

Runnable delegated =
    new DelegatingSecurityContextRunnable(businessTask);

// Thực tế đưa delegated vào Executor do ứng dụng quản lý.
// Chạy trực tiếp bằng run() ở đây chỉ minh họa đối tượng được bọc.
delegated.run();
```

Trong ứng dụng thật, không tự tạo thread vô hạn mỗi request. Dùng `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextAsyncTaskExecutor` với executor đã cấu hình, hoặc truyền **actor ID đáng tin và permission cần thiết** thành input rõ ràng của tác vụ. Với job chạy trễ sau nhiều phút/giờ, authentication context snapshot có thể đã hết hạn hoặc quyền đã bị thu hồi. Thiết kế policy để kiểm tra lại quyền khi chạy và tránh đưa nguyên token/password vào hàng đợi.

### 8.2. Không lạm dụng MODE_INHERITABLETHREADLOCAL hoặc MODE_GLOBAL

`SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` cho thread **mới được tạo** kế thừa context từ thread cha trong một số tình huống, nhưng với thread pool dùng lại worker, cơ chế đó dễ gây hiểu lầm và rò rỉ danh tính nếu không được quản lý. `MODE_GLOBAL` chia sẻ context ở phạm vi JVM và thường **không phù hợp** cho web server đa người dùng. Thông thường, giữ `MODE_THREADLOCAL` và sử dụng integration được Spring Security hỗ trợ cho async.

### 8.3. WebFlux không dùng cùng mô hình

Trong ứng dụng reactive, các bước xử lý có thể chuyển thread và không có một ThreadLocal cố định đại diện cho request từ đầu đến cuối. Spring Security sử dụng `ReactiveSecurityContextHolder` dựa trên Reactor Context. Đừng copy nguyên service Servlet dùng `SecurityContextHolder.getContext()` sang WebFlux rồi giả định nó sẽ luôn cho đúng principal. Tham khảo API reactive khi làm module WebFlux.

## 9. Các lỗi thường gặp

### Lỗi A — “Holder = HttpSession”

**Sai:** gọi `SecurityContextHolder.getContext()` rồi nghĩ dữ liệu sẽ có sẵn ở mọi request sau.

**Đúng:** holder phục vụ phạm vi xử lý hiện tại; muốn lưu authentication qua request cần `SecurityContextRepository`/session hoặc xác thực lại token. Trong Spring Security 6 với custom login, cần hiểu rõ **explicit save**. Basic stateless có thể có một Authentication mới trên mỗi request.

### Lỗi B — Ép principal thành UserDetails trong mọi flow

**Sai:**

```java
// Chỉ đúng nếu authentication thật sự có UserDetails làm principal:
UserDetails user = (UserDetails) authentication.getPrincipal();
```

**Đúng:** xem loại authentication đã cấu hình và lấy identifier phù hợp. Với JWT thường dùng principal/claim từ Jwt hoặc tên đã được cấu hình; với OIDC dùng OidcUser; với Basic + DaoAuthenticationProvider có thể dùng UserDetails. Đưa mapping sang `CurrentUser` hoặc application principal do server tự thiết lập để domain không phụ thuộc nhiều kiểu token.

### Lỗi C — Dựa chỉ vào isAuthenticated()

**Sai:** `auth.isAuthenticated()` có thể là true trên `AnonymousAuthenticationToken`.

**Đúng:** dùng `authenticated()`/`fullyAuthenticated()`, `AuthenticationTrustResolver` hoặc policy server rõ ràng. Không đặt điều kiện Boolean duy nhất ngay trong controller rồi mặc định đó là bước bảo vệ đầy đủ.

### Lỗi D — Dùng getName() làm ownerId không ổn định

**Sai:** dùng email/tên hiển thị làm khóa tài nguyên trong ứng dụng nhiều tenant mà không hiểu cách identity provider định nghĩa principal name.

**Đúng:** ánh xạ `sub`/account ID từ nguồn tin cậy sang user ID ổn định, kiểm tra tenant và owner trong database. Test trường hợp email được đổi, hai identity provider cùng user name và subject bị tái sử dụng theo ngữ cảnh issuer.

### Lỗi E — Lộ credential khi log object authentication

**Sai:** trả `Authentication`/`SecurityContext` nguyên vẹn qua API hoặc ghi `toString()` vô điều kiện vào log. Có thể lộ details, claim, session metadata hoặc object chứa secret.

**Đúng:** tạo DTO chỉ chứa những trường cần thiết (ví dụ user ID ổn định, display name đã lọc, quyền công khai theo policy). Không log password, bearer token, refresh token hoặc cookie session; che thông tin nhạy cảm ở monitoring/tracing.

### Lỗi F — Dùng context như singleton toàn cục

**Sai:** lưu authentication vào field mutable của singleton service:

```java
// SAI: cùng một instance service phục vụ nhiều request.
class UnsafeService {
    Authentication currentUser;
}
```

**Đúng:** lấy identity đúng phạm vi request/thread, hoặc truyền actor ID/CurrentUser có kiểm chứng vào service. Với asynchronous code, dùng propagation có quản lý, không chia sẻ context giữa người dùng.

### Lỗi G — Tự gắn quyền vào Authentication từ dữ liệu client

**Sai:** tin `role=ADMIN` hoặc `X-User` do client gửi, tạo authentication với `authenticated=true` và bỏ qua xác minh.

**Đúng:** filter/provider/decoder phải chứng thực credential/claim qua ranh giới tin cậy rồi mới gán authorities. Phân quyền resource vẫn phải thực thi riêng dù authentication hợp lệ.

### Lỗi H — Dùng @PreAuthorize nhưng lời gọi không qua proxy

**Sai:** cho rằng `@PreAuthorize` luôn chạy khi gọi một method của chính cùng bean bằng `this.method()` hoặc quên bật `@EnableMethodSecurity`.

**Đúng:** kiến trúc rõ điểm kiểm soát, gọi qua bean được interceptor quản lý và test từ entrypoint thực. Với logic nhạy cảm, ràng buộc ở data/domain layer cũng cần được bảo đảm.

## 10. Một bảng phân biệt nhanh để tự kiểm tra hiểu biết

| Phát biểu | Đúng/sai | Giải thích |
| --- | --- | --- |
| `SecurityContextHolder` chứa một context cho mọi user trong JVM | Sai | Mặc định theo thread của Servlet, có chiến lược khác nếu cấu hình |
| `SecurityContext` thường giữ `Authentication` hiện tại | Đúng | API chính của context là lấy/đặt authentication |
| `Authentication` luôn có principal kiểu `UserDetails` | Sai | Có thể là Jwt, OAuth2User, chuỗi hoặc custom principal |
| `getCredentials()` luôn là password plaintext | Sai | Tùy flow và thường bị xóa sau xác thực |
| `Authentication.isAuthenticated() == true` bảo đảm user đăng nhập thật | Sai | AnonymousAuthenticationToken cũng có thể true |
| `getAuthorities()` cho biết người dùng được xem mọi object | Sai | Authorities thường là quyền mức cao, cần policy trên dữ liệu |
| `SecurityContextHolder` tự động lưu login vĩnh viễn | Sai | Request lifecycle khác session/token persistence |
| Stateless API vẫn có thể dùng `SecurityContextHolder` trong request | Đúng | Mỗi request được xác thực và thiết lập context riêng |
| `@Async` mới tạo thread luôn có principal từ request | Sai | Context propagation cần cấu hình/cơ chế phù hợp |
| Servlet và WebFlux dùng cùng cơ chế ThreadLocal hiện tại | Sai | WebFlux dùng ReactiveSecurityContextHolder |
| Spring Security luôn xóa holder ở điểm kết thúc request qua filter chain | Đúng trong luồng Spring Security chuẩn | Custom thread/filter cần tự quản vòng đời |
| HTTPS tự tạo `Authentication` cho user | Sai | TLS bảo vệ transport; authentication người dùng là cơ chế khác |

## 11. Checklist khi sử dụng danh tính hiện tại trong API thật

1. **Xác thực đầu vào:** credential/token/session có được server kiểm tra đúng và từ nguồn identity được tin cậy?
2. **Principal type:** code có phụ thuộc nhầm `UserDetails` trong khi hệ thống dùng JWT/OIDC không?
3. **Identity ổn định:** `getName()` có phải user ID phù hợp với policy owner/tenant, hay cần ánh xạ `subject` sang ID nội bộ?
4. **Authorizations:** các rule dựa vào authorities từ nguồn tin cậy và kiểm tra thêm resource cụ thể ở service?
5. **Anonymous:** API có kiểm tra đúng anonymous/remember-me/fully authenticated khi yêu cầu thao tác nhạy cảm?
6. **Session/stateless:** có hiểu request hiện tại và persistence giữa các request là hai phạm vi khác nhau? Custom login đã lưu context đúng chưa?
7. **Concurrency:** có ngữ cảnh user trong `@Async`/queue/callback không? Nếu có, được truyền có chủ đích và dọn đúng lúc không?
8. **Response/logging:** chỉ trả DTO tối thiểu, không lộ credential, claim nhạy cảm, token, session cookie?
9. **Test âm tính:** anonymous gọi private; user A gọi tài nguyên B; user không đủ role; hai request liên tiếp dùng hai principal khác nhau?
10. **Hạ tầng:** API truyền credential qua HTTPS, session/cookie flags và token lifetime được quản lý phù hợp?

## 12. Ghi nhớ

- **`SecurityContextHolder` → `SecurityContext` → `Authentication`** là đường đi phổ biến để lấy danh tính đang được xử lý trong Spring Security Servlet.
- `Authentication` gồm **principal, credentials, authorities, details** cùng trạng thái, nhưng kiểu dữ liệu thực phụ thuộc cơ chế login; không ép kiểu tùy tiện.
- **Current context ≠ HTTP session.** Holder cho biết ai đang hoạt động trong luồng xử lý; repository/session/token quyết định cách danh tính được khôi phục ở request sau.
- **AnonymousAuthenticationToken không phải user đã đăng nhập thật**, dù cờ `isAuthenticated()` có thể là true.
- **Identity không bằng permission trên mọi object.** Lấy principal từ nguồn tin cậy, áp chính sách quyền theo actor/action/resource/tenant/trạng thái.
- **ThreadLocal không tự đi qua async/thread pool.** Dùng propagation được quản lý và dọn context, hoặc truyền actor rõ ràng với kiểm tra lại quyền.

## Tài liệu tham khảo

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Anonymous Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html)
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security — Testing with Spring MVC](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Boot 3.5.16 artifact](https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-starter-parent/3.5.16/)
