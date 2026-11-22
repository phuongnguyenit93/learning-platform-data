# Ý nghĩa của getName, getPrincipal, getCredentials và getAuthorities trong Spring Security

> **Phạm vi:** mô hình danh tính của **Spring Security Authentication** trên Java 17+, tập trung vào API `org.springframework.security.core.Authentication`. Bài học giải thích chính xác bốn phương thức, sự khác nhau giữa yêu cầu xác thực và kết quả đã xác thực, cách đọc trong ứng dụng Spring MVC, các ngoại lệ theo loại đăng nhập và rủi ro bảo mật. Ví dụ có phần Java chạy độc lập với dependency Spring Security 6.3.x. Trọng tâm là **hiểu dữ liệu nhận dạng**, không thiết kế toàn bộ quy tắc phân quyền hay một hệ thống OAuth2 mới.

## 1. Bức tranh tổng thể: bốn câu hỏi khác nhau

Trong Spring Security, `Authentication` biểu diễn **một yêu cầu xác thực** được gửi đến `AuthenticationManager` hoặc **kết quả xác thực** của một danh tính hiện tại. Đối tượng đó thường được đặt vào `SecurityContext` sau khi đăng nhập thành công.

```text
SecurityContextHolder
    └── SecurityContext
         └── Authentication
              ├── getName()        -> tên biểu diễn danh tính
              ├── getPrincipal()   -> đối tượng đại diện cho danh tính
              ├── getCredentials() -> bằng chứng xác thực (có thể đã được xóa)
              ├── getAuthorities() -> quyền/role/scope đã được cấp
              ├── isAuthenticated() -> trạng thái tin cậy của token
              └── getDetails()     -> thông tin phụ của lần xác thực (nếu có)
```

Bốn phương thức chính **không đồng nghĩa và không thay thế nhau**:

| Phương thức | Kiểu trả về trong Java | Trả lời câu hỏi | Ví dụ thường gặp |
| --- | --- | --- | --- |
| `getName()` | `String` | Danh tính này được gọi bằng tên gì? | `mai`, một subject ID |
| `getPrincipal()` | `Object` | Ai hoặc cái gì đang được đại diện bởi token này? | `String` username, `UserDetails`, `Jwt`, `OidcUser` |
| `getCredentials()` | `Object` | Bằng chứng nào được đưa ra để chứng minh danh tính? | Mật khẩu, secret/token, hoặc `null` |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` | Những quyền/role/scope nào gắn với danh tính đã được xác thực? | `ROLE_USER`, `ROLE_ADMIN`, `SCOPE_profile` |

Điểm dễ nhầm: **`getName()` là chuỗi định danh**, **`getPrincipal()` có thể là đối tượng giàu thuộc tính**, **`getCredentials()` là dữ liệu nhạy cảm**, còn **`getAuthorities()` dùng cho việc quyết định truy cập**. Không thể suy ra password từ name, không thể suy ra quyền chỉ từ username và không nên suy ra user nội bộ chỉ từ một trường tùy ý trong principal của nhà cung cấp ngoài.

### Authentication có hai trạng thái ý nghĩa khác nhau

```text
Người dùng nhập username/password
    ↓
Authentication request
    principal   = "mai"          (String)
    credentials = mật khẩu vừa nhập
    authorities = []             (chưa được cấp quyền đáng tin)
    authenticated = false
    ↓
AuthenticationManager -> AuthenticationProvider -> kiểm tra credential
    ↓
Authentication result thành công
    principal   = UserDetails(...) hoặc kiểu tùy provider
    credentials = thường đã xóa (null)
    authorities = [ROLE_LEARNER] (dữ liệu do hệ thống tin cậy cấp)
    authenticated = true
    ↓
SecurityContext (và các cơ chế lưu/khôi phục context của request)
```

**Cùng một interface nhưng dữ liệu trước và sau xác thực có thể khác cả kiểu lẫn giá trị.** Không nên ép kiểu kết quả dựa trên ví dụ của một provider duy nhất.

## 2. getName(): tên danh tính dùng để hiển thị hoặc tra cứu có điều kiện

Chữ ký:

```java
String name = authentication.getName();
```

`Authentication` **extends `java.security.Principal`**; `getName()` đến từ hợp đồng `Principal`. Với các implementation phổ biến kế thừa `AbstractAuthenticationToken`, tên được suy ra từ principal: chẳng hạn `UserDetails.getUsername()`, `AuthenticatedPrincipal.getName()`, `Principal.getName()`, hoặc cách biểu diễn chuỗi của principal phù hợp. Vì vậy kết quả **phụ thuộc loại `Authentication` và loại principal**.

Các ví dụ:

- Đăng nhập username/password với `UserDetails` tên `mai`: `getName()` thường trả `mai`.
- OAuth2/OIDC Login: tên có thể dựa vào thuộc tính/claim được cấu hình cho principal, không nhất thiết trùng username trong DB nội bộ.
- JWT Resource Server: `JwtAuthenticationToken` thường lấy subject (`sub`) làm tên mặc định, nhưng có thể tùy chỉnh cách ánh xạ.
- Một token anonymous có thể có tên `anonymousUser`; đó **không phải** dấu hiệu người dùng thật đã login.

**Dùng đúng:** hiển thị một mã/tên danh tính đã được backend chấp nhận, dùng khi hệ thống đã xác định chính xác ý nghĩa và tính duy nhất của name. **Không dùng mặc định làm khóa user toàn cục** trong mọi kịch bản. Với OIDC, ánh xạ danh tính ngoài bền vững thường gắn với cặp **issuer + subject (`iss` + `sub`)**; email/display name có thể đổi, trùng hoặc chưa xác thực. Với hệ thống nhiều tenant, phải đưa ranh giới tenant vào quy tắc định danh.

**Không suy diễn:** `getName()` không cung cấp mật khẩu, số điện thoại, quyền truy cập hay bảo đảm người dùng đã đăng nhập. Cũng không được giả định nó luôn bằng `((UserDetails) getPrincipal()).getUsername()` vì principal có thể không phải `UserDetails`.

## 3. getPrincipal(): đối tượng đại diện cho người hoặc thực thể được xác thực

Chữ ký:

```java
Object principal = authentication.getPrincipal();
```

`principal` là khái niệm tổng quát cho *chủ thể được nhận diện*. API khai báo `Object` để hỗ trợ nhiều kiểu thông tin và cơ chế authentication.

### Trước và sau khi xác thực username/password

- **Đầu vào:** `UsernamePasswordAuthenticationToken.unauthenticated("mai", "secret")` có principal là chuỗi `"mai"`.
- **Kết quả:** `DaoAuthenticationProvider` thường trả một `Authentication` có principal là đối tượng `UserDetails` chứa username, authorities và cờ trạng thái account (nếu không cấu hình trả principal dạng String).
- **Ngoại lệ hợp lệ:** ứng dụng có thể sử dụng custom principal kiểu `CurrentUser` chứa internal user ID, tenant ID hoặc thông tin cần thiết khác; không nhất thiết là entity JPA.

### Khi tích hợp cơ chế khác

| Hình thức | Ví dụ principal thường gặp | Cần cẩn trọng |
| --- | --- | --- |
| Username/password trước xác thực | `String` | Chỉ là tên khai báo, chưa được tin |
| Username/password thành công | `UserDetails` hoặc custom user | Có thể có password hash/trạng thái nhạy cảm |
| JWT Resource Server | `Jwt` | Đã được kiểm tra qua provider phù hợp, nhưng các claims còn phải được diễn giải theo issuer/audience và nghiệp vụ |
| OAuth2 Login | `OAuth2User` | Thuộc tính user tùy provider/registration |
| OIDC Login | `OidcUser` | `sub`, issuer, claims; tránh nhầm email với ID duy nhất |
| Anonymous Authentication | Thường là chuỗi `anonymousUser` | Không phải authenticated end-user theo nghĩa nghiệp vụ |

Khi cần truy cập kiểu chuyên biệt, kiểm tra bằng **`instanceof`**, không ép kiểu vô điều kiện:

```java
Object principal = authentication.getPrincipal();

if (principal instanceof UserDetails userDetails) {
    String username = userDetails.getUsername();
    // Phù hợp khi principal thực sự là UserDetails.
} else {
    String name = authentication.getName();
    // Xử lý kiểu principal khác theo cơ chế đã được cấu hình.
}
```

Đoạn trên là **minh họa bên trong một method đã có biến `authentication`**, không phải một lớp Java chạy độc lập. Trong code production, nếu ứng dụng quy định một custom principal cụ thể, hãy trừu tượng hóa việc chuyển từ external identity sang internal user ID ở tầng đăng nhập hoặc identity mapping. Hạn chế để toàn bộ controller/service phải đoán mọi kiểu provider.

**Không trả trực tiếp `authentication.getPrincipal()` qua REST API.** Principal có thể chứa password hash, email, token claims, thuộc tính nội bộ hoặc object graph không dành cho client. Tạo DTO chỉ gồm các trường thực sự được phép công bố.

## 4. getCredentials(): bằng chứng xác thực, không phải hồ sơ người dùng

Chữ ký:

```java
Object credentials = authentication.getCredentials();
```

Credentials là dữ liệu chứng minh principal có quyền tuyên bố danh tính. Trong username/password flow, giá trị thường là mật khẩu **do client vừa gửi**. Với cơ chế khác nó có thể là token, secret hoặc dữ liệu đặc thù provider. Kiểu `Object` phản ánh sự đa dạng này; **không được mặc định ép thành `String`**.

### Vòng đời an toàn

1. Request ban đầu có thể giữ raw password để `AuthenticationProvider` kiểm tra với password hash được lấy từ nơi lưu user.
2. Khi xác thực thành công, `ProviderManager` mặc định xóa credentials khỏi kết quả nếu kết quả hỗ trợ `CredentialsContainer`; các lớp token tiêu chuẩn thường hỗ trợ cơ chế này. `getCredentials()` sau login do đó **có thể trả `null`**.
3. Với custom `AuthenticationManager`, custom token hoặc provider khác, khả năng xóa phụ thuộc implementation. Không mặc định rằng **mọi** token đã được xóa.
4. Nếu principal/details cũng chứa đối tượng hỗ trợ `CredentialsContainer`, cơ chế xóa có thể ảnh hưởng cả đối tượng đó; thiết kế cache user và đối tượng chia sẻ phải tránh giữ/cấp lại bản mutable bị xóa credentials.

**Tuyệt đối tránh:**

```java
// SAI: không đưa credentials vào response, log hay metrics.
return authentication.getCredentials();

// SAI: không thể dùng getCredentials() sau login để "lấy lại mật khẩu".
String password = (String) authentication.getCredentials();
```

Các đoạn trên là **ví dụ cần tránh**, không phải lời khuyên triển khai. Không in toàn bộ `Authentication`/principal ra log trong môi trường thật vì implementation hoặc custom `toString()` có thể bộc lộ dữ liệu; cần redaction thích hợp. Không lưu raw password vào `SecurityContext`/HTTP session để dùng về sau. Nếu cần thay mật khẩu, xác thực lại/thiết kế flow riêng theo chính sách.

**Phân biệt ba khái niệm:**

- `getCredentials()`: bằng chứng client đưa ra ở một bước authentication; có thể bị xóa.
- `UserDetails.getPassword()`: thông thường là **password hash đã lưu**, dùng cho `PasswordEncoder.matches(...)`; không phải mật khẩu gốc và cũng có thể chịu ảnh hưởng của credential erasure.
- `getDetails()`: thông tin phụ của request (ví dụ metadata từ remote address, session ID tùy cấu hình). Đây là phương thức **khác** `getCredentials()`, không được xem như nguồn dữ liệu chứng minh danh tính.

## 5. getAuthorities(): những quyền được cấp cho principal

Chữ ký:

```java
Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
```

`GrantedAuthority` biểu diễn **một quyền mức ứng dụng**. Nó có phương thức `getAuthority()` trả về tên quyền dạng `String` (một số authority phức tạp có thể không biểu diễn được bằng chuỗi và trả `null`). Hợp đồng `Authentication#getAuthorities()` trả một collection, **không trả `null`**; trước khi token được xác thực, collection có thể rỗng.

Ví dụ:

- `ROLE_USER`, `ROLE_ADMIN`, `ROLE_LEARNER`: dạng role phổ biến.
- `SCOPE_profile`, `SCOPE_orders.read`: cách ánh xạ scope thường gặp trong OAuth2 Resource Server; phụ thuộc converter/configuration.
- `orders:read`: authority tùy ứng dụng, cần quy ước và bộ kiểm tra phù hợp.

Vai trò của authorities trong luồng:

```text
AuthenticationProvider / nguồn danh tính được tin cậy
    ↓ gán authorities sau khi xác thực
Authentication.getAuthorities()
    ↓
AuthorizationManager / @PreAuthorize / request authorization rules
    ↓
Cho phép hoặc từ chối thao tác
```

**Authorities không đồng nghĩa xác thực:** một tài khoản có thể đã xác thực mà collection authorities rỗng; request vẫn có thể bị cấm vì yêu cầu quyền. Ngược lại, danh sách quyền do client gửi lên trong request đăng nhập không tự trở thành quyền đáng tin. Hệ thống phải cấp/ánh xạ authorities từ nguồn đã xác minh.

### hasRole và hasAuthority

Trong Spring Security, rule `hasRole("ADMIN")` theo cấu hình mặc định kiểm tra authority `ROLE_ADMIN`; rule `hasAuthority("ROLE_ADMIN")` khớp chính xác chuỗi đó. Vì vậy cần phân biệt:

```java
// Minh họa cấu hình một số request authorization rule:
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/reports/**").hasAuthority("reports:read")
```

Đây là **các dòng trong cấu hình `authorizeHttpRequests`**, không phải chương trình Java độc lập. Prefix role có thể được tùy chỉnh; đừng tự thêm hoặc xóa `ROLE_` theo suy đoán nếu ứng dụng đã có quy ước riêng. Authorization cho từng bản ghi (ví dụ chỉ được đọc đơn hàng của tenant mình) thường cần kiểm tra ngữ cảnh nghiệp vụ; một authority toàn cục chưa đủ để quyết định quyền với từng object.

### Cách đọc authorities an toàn

```java
List<String> names = authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .filter(Objects::nonNull)
        .sorted()
        .toList();
```

Đoạn này cần import `java.util.List`, `java.util.Objects` và `GrantedAuthority`, đồng thời giả định đã có biến `authentication`. `filter(Objects::nonNull)` chủ động loại bỏ dạng authority phức tạp không cung cấp tên chuỗi. Nếu hệ thống dùng kiểu đó, bộ authorization phù hợp phải hiểu trực tiếp representation của nó.

## 6. Java 17+ runnable: quan sát bốn trường trước và sau xác thực thật

Ví dụ dưới đây chạy **không cần web server**. Nó dựng một tài khoản in-memory, dùng `PasswordEncoder` để tạo password hash, để `DaoAuthenticationProvider` thực sự kiểm tra credential, và dùng `ProviderManager` trả kết quả. Mục tiêu là thấy **vì sao trước và sau authentication các getter thay đổi**. Dữ liệu demo không dùng cho production.

Cấu trúc thư mục:

```text
auth-fields-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AuthFieldsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'auth-fields-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
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
    implementation 'org.springframework.security:spring-security-core:6.3.10'
}

application {
    mainClass = 'demo.AuthFieldsDemo'
}
```

`src/main/java/demo/AuthFieldsDemo.java`:

```java
package demo;

import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class AuthFieldsDemo {
    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails account = User.withUsername("mai")
                .password(encoder.encode("demo-password"))
                .roles("LEARNER")
                .build();

        UserDetailsService users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-password");

        show("request", request);

        Authentication result = manager.authenticate(request);

        show("result", result);
    }

    static void show(String stage, Authentication authentication) {
        Object principal = authentication.getPrincipal();

        String principalType = (principal == null)
                ? "null"
                : principal.getClass().getSimpleName();

        String credentialsState = (authentication.getCredentials() == null)
                ? "absent"
                : "present";

        String authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .collect(Collectors.joining(","));

        if (authorities.isEmpty()) {
            authorities = "(none)";
        }

        System.out.printf(
                "%s | name=%s | principal=%s | credentials=%s"
                        + " | authorities=%s | authenticated=%s%n",
                stage,
                authentication.getName(),
                principalType,
                credentialsState,
                authorities,
                authentication.isAuthenticated());
    }
}
```

Tại thư mục `auth-fields-demo`, chạy bằng một Gradle 8.x tương thích với Java 17:

```bash
gradle run
```

Nếu project đã có Gradle Wrapper, dùng `./gradlew run` trên macOS/Linux hoặc `gradlew.bat run` trên Windows. Chương trình in hai dòng chính (ngoài log do Gradle tự sinh):

```text
request | name=mai | principal=String | credentials=present | authorities=(none) | authenticated=false
result | name=mai | principal=User | credentials=absent | authorities=ROLE_LEARNER | authenticated=true
```

**Phân tích từng giá trị:**

1. `request.getName()` và `result.getName()` đều là `mai`, dù principal đổi từ `String` sang `UserDetails`: name là tên, không phải type của đối tượng.
2. `request.getPrincipal()` có type `String`. `result.getPrincipal()` là đối tượng `org.springframework.security.core.userdetails.User` (một `UserDetails`) do `DaoAuthenticationProvider` trả về.
3. `request.getCredentials()` có dữ liệu đầu vào; hàm `show` **chỉ in trạng thái `present`**, không in secret. `result.getCredentials()` đã bị xóa bởi `ProviderManager` mặc định trong luồng mẫu. **Không dùng kết quả này để tuyên bố mọi custom provider đều xóa được.**
4. `request.getAuthorities()` rỗng; sau khi account được kiểm tra đúng bằng `PasswordEncoder`, result có `ROLE_LEARNER` từ `UserDetails`.
5. `request.isAuthenticated()` là `false` và result là `true`. Giá trị `true` chỉ đáng tin khi được tạo qua một cơ chế xác thực được tin cậy, không phải chỉ vì lập trình viên tự điền một cờ.

**Thử thay đổi để hiểu sâu hơn:** đổi credential thành `"wrong"`; `manager.authenticate(...)` sẽ ném một `AuthenticationException` (thường là `BadCredentialsException`) thay vì trả result thành công. Thêm role thứ hai bằng `.roles("LEARNER", "EDITOR")`; sau thành công, danh sách authorities tăng. Thay username ở request bằng tên không tồn tại; việc xác thực thất bại không tự tạo một account. Không cố tình viết `setAuthenticated(true)` hoặc tự dựng authenticated token để “qua kiểm tra mật khẩu”: đó là bỏ qua ranh giới tin cậy.

## 7. Dùng trong Spring MVC/Spring Boot mà không lộ secret

Trong một request được Spring Security bảo vệ, controller có thể nhận `Authentication` trực tiếp; hoặc dùng `SecurityContextHolder.getContext().getAuthentication()` khi thật sự cần. Tạo DTO chỉ chứa thông tin phù hợp để client xem:

```java
package demo.web;

import java.util.List;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    public record MeResponse(String name, List<String> authorities) {}

    @GetMapping("/me")
    public MeResponse me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .toList();

        return new MeResponse(authentication.getName(), authorities);
    }
}
```

Đây là **class controller hoàn chỉnh**, nhưng để chạy như ứng dụng web cần đặt trong một Spring Boot project có `spring-boot-starter-web`, `spring-boot-starter-security`, một entry point `@SpringBootApplication` và cấu hình xác thực. Endpoint `/me` **phải được bảo vệ bằng rule `authenticated()`** để bảo đảm parameter không là null và response không chứa danh tính anonymous. Tùy mục đích, có thể chỉ trả `name` và bỏ authorities nếu UI không cần chúng.

Ví dụ cấu hình bảo vệ endpoint `/me`, minh họa trong một `@Configuration` có bean `SecurityFilterChain`:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/me").authenticated()
            .anyRequest().permitAll())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Các import cần thiết cho đoạn config này: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.annotation.web.builders.HttpSecurity` và `org.springframework.security.web.SecurityFilterChain`. Cấu hình mẫu cần kết hợp với một nguồn user/`AuthenticationProvider` được thiết lập đúng; đừng hiểu nó là chương trình độc lập có thể chạy.

Nếu chỉ cần principal đã được mapping theo type, Spring MVC còn có `@AuthenticationPrincipal`. Ví dụ `@AuthenticationPrincipal UserDetails user` thích hợp khi chắc chắn provider trả `UserDetails`; nếu ứng dụng chuyển sang JWT/OIDC, hãy xem lại kiểu tham số đó hoặc xây một lớp mapping thống nhất.

**Câu hỏi về Anonymous:** `SecurityContext` có thể chứa `AnonymousAuthenticationToken` khi chưa login. Loại token này có thể trả `isAuthenticated() == true` theo đặc tính implementation; vì thế **không** dùng duy nhất phép kiểm tra cờ đó để xác định “người dùng thật đã đăng nhập”. Ưu tiên để Spring Security kiểm tra `authenticated()`/`fullyAuthenticated()` theo chính sách hoặc dùng `AuthenticationTrustResolver` phù hợp khi buộc phải kiểm tra bằng code.

## 8. So sánh getter ở các cơ chế authentication khác nhau

Các giá trị dưới đây là **ví dụ thường gặp**, không phải contract cố định cho mọi implementation, custom converter hay phiên bản.

| Ngữ cảnh | `getName()` | `getPrincipal()` | `getCredentials()` | `getAuthorities()` |
| --- | --- | --- | --- | --- |
| Username/password request | Username đầu vào | `String` username | Raw password trước xử lý | Rỗng, chưa đáng tin |
| Username/password thành công | Username của user | `UserDetails` hoặc custom principal | Thường xóa/null | Role/permission được cấp |
| JWT Resource Server | Thường là `sub` | `Jwt` | Tùy token implementation/vòng đời; không xuất ra | Authority ánh xạ từ scope/claim theo config |
| OIDC Login | Theo name attribute được chọn | `OidcUser` | Tùy implementation; không xuất ra | Authorities được mapping bởi client/provider |
| Anonymous | Thường `anonymousUser` | Có thể là chuỗi anonymous | Không phải mật khẩu của user thật | Có thể mang `ROLE_ANONYMOUS` |

Đặc biệt với JWT/OIDC: `getPrincipal()` có thể chứa claims đã được xác minh bởi luồng xác thực nhưng không phải mọi claim đều nên hiển thị hoặc tin làm quyền. **Quyền API** phải đến từ issuer đáng tin và converter được thiết kế đúng; đừng cho client tự gửi `"roles":["ADMIN"]` rồi gắn trực tiếp vào `Authentication` mà không xác thực nguồn. `getName()` và `getPrincipal()` vẫn phải được hiểu theo ranh giới tổ chức, tenant, issuer và user mapping.

## 9. Kiểm thử: kiểm tra gì ở mỗi phương thức?

Một bộ kiểm thử tối thiểu nên bao gồm cả **Authentication object** lẫn **hành vi request thật**.

| Trường hợp | Điều phải chứng minh |
| --- | --- |
| Tạo `UsernamePasswordAuthenticationToken.unauthenticated` | `getPrincipal()` giữ input username, `getCredentials()` nhận credential, `isAuthenticated() == false`, authorities rỗng |
| Xác thực hợp lệ bằng `AuthenticationManager` | Name chính xác; principal phù hợp provider; authorities đến từ nguồn tin cậy; trạng thái xác thực thành công |
| Mật khẩu sai | Throw `AuthenticationException`; không phát sinh trusted result |
| Cơ chế erase credentials mặc định | Trong luồng tiêu chuẩn hỗ trợ `CredentialsContainer`, kết quả không còn raw password |
| Đổi nguồn từ user/password sang JWT/OIDC | Không ép principal về `UserDetails` khi type không phù hợp |
| Không có user/anonymous | Protected endpoint không vô tình trả `anonymousUser` như user đã login |
| Authorities trống hoặc thiếu `ROLE_ADMIN` | Login có thể hợp lệ nhưng request cần admin vẫn bị từ chối |
| Rule `hasRole("ADMIN")` so với `hasAuthority("ROLE_ADMIN")` | Hiểu đúng prefix mặc định và các tùy chỉnh hiện tại |
| REST response/logging | Không chứa credentials, raw `Authentication`, password hash hoặc secret |
| Resource thuộc tenant khác | Có quyền tổng quát không có nghĩa có quyền với mọi bản ghi |

Khi dùng `spring-security-test`, `@WithMockUser` giúp kiểm thử các rule yêu cầu principal/authority mà không phải chạy form login. Tuy nhiên **nó không chứng minh password được mã hóa hay provider thật xác thực đúng**. Cần ít nhất một test qua `AuthenticationManager`/login filter thật cho tuyến username/password; và test với JWT/IdP simulator phù hợp khi dùng những cơ chế đó.

## 10. Lỗi thường gặp và cách sửa

1. **Dùng `getName()` làm ID DB duy nhất cho mọi loại login.** Tên hiển thị/username có thể đổi và tên từ IdP ngoài có namespace riêng. Chuẩn hóa sang internal user ID; với OIDC lưu issuer + subject theo chính sách linking.
2. **Ép `getPrincipal()` thành `UserDetails` không kiểm tra.** Login qua JWT/OIDC hoặc custom principal sẽ gây `ClassCastException`. Kiểm tra type hoặc dùng mapping layer.
3. **Trả principal nguyên trạng cho frontend.** Dễ vô tình trả password hash hoặc claims nhạy cảm. Dùng DTO/field allowlist.
4. **Lấy password bằng `getCredentials()` sau login.** Credential thường đã bị xóa; dù còn cũng không được sử dụng lại để xác thực dịch vụ khác. Thiết kế token/service-to-service authentication riêng.
5. **Ghi log `Authentication` không kiểm soát.** Tùy custom implementation có thể lộ dữ liệu. Chỉ log sự kiện tối thiểu như loại xác thực, kết quả, correlation ID; không log credential/token.
6. **Đồng nhất `getAuthorities()` với “đã login”.** Authorities có thể rỗng; kiểm tra authenticated và policy đúng chỗ.
7. **So sánh role sai tiền tố.** `hasRole("ADMIN")` mặc định yêu cầu `ROLE_ADMIN`, trong khi `hasAuthority(...)` kiểm tra chuỗi cụ thể.
8. **Cho client tự khai authorities và coi là trusted.** Quyền phải được xác minh/cấp từ nguồn an toàn trong authentication/authorization pipeline.
9. **Chỉ kiểm tra `isAuthenticated()` để loại anonymous.** Anonymous token có thể mang cờ true; dùng authentication trust resolver hoặc bảo vệ endpoint bằng Spring Security.
10. **Cho rằng xóa credentials có nghĩa xóa mọi thông tin nhạy cảm khỏi principal.** Password hash, claims, personal attributes và details cần được quản lý/redact riêng.
11. **Dùng object Authentication cũ sau thay đổi trạng thái tài khoản/quyền.** Session hoặc token có thể giữ authorities đã cấp ở thời điểm trước; chính sách refresh/revocation/revalidation phải thiết kế độc lập.
12. **Tự tạo authenticated token trong application controller.** Điều này bỏ qua ranh giới tin cậy. Thực hiện xác thực qua manager/provider/filter thích hợp.

## 11. Bài tập tổng hợp và tiêu chí hoàn thành

**Bài tập A — Đọc đúng từng trường:** chạy `AuthFieldsDemo` ở mục 6, ghi lại hai dòng output và giải thích vì sao `getName()` giữ nguyên nhưng `getPrincipal()`, `getCredentials()`, `getAuthorities()` thay đổi. Đổi username hoặc mật khẩu sai để quan sát đường thất bại.

**Bài tập B — Thay đổi role:** thêm role `EDITOR` cho user, dự đoán chuỗi authority, chạy lại để so với kết quả. Giải thích vì sao `ROLE_EDITOR` xuất hiện dù khai `.roles("EDITOR")`.

**Bài tập C — DTO an toàn:** viết endpoint `GET /me` chỉ cho user đã xác thực, trả name và authorities trong DTO. Kiểm tra response không chứa password hash, raw credentials, bearer token hoặc toàn bộ principal.

**Bài tập D — Nhiều loại principal:** liệt kê kiểu principal khi dùng form login, JWT Resource Server và OIDC Login. Đề xuất cách chuyển thành `CurrentUser(id, tenantId, displayName)` nội bộ; xác định trường nào được dùng để liên kết ổn định và trường nào chỉ dùng để hiển thị.

**Bài tập E — Anonymous và 403:** thử gọi protected endpoint khi chưa login, đã login nhưng thiếu authority, và đã login có đúng authority. Giải thích riêng authentication và authorization, và vì sao `isAuthenticated()` đơn độc không đủ kết luận trong mọi trường hợp.

**Đạt bài** khi có thể trả lời nhanh bốn câu: `getName()` là tên gì, `getPrincipal()` có thể là type nào, vì sao `getCredentials()` sau xác thực có thể null, và `getAuthorities()` được ai cấp và dùng ở đâu. Quan trọng hơn, người học phải biết **không xuất credential/principal thô** và **không biến authorities do client khai thành quyền đáng tin**.

## 12. Tài liệu chính thức để đối chiếu

- [Spring Security 6.3.10 — Authentication API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/Authentication.html): chữ ký các getter, principal/credential/authorities và hợp đồng trạng thái xác thực.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContext`, vai trò của `Authentication`, `AuthenticationManager` và provider.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `GrantedAuthority`, role prefix và cơ chế kiểm tra quyền.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): luồng lấy `UserDetails` và kiểm tra password.
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): token chưa xác thực/đã xác thực.
- [Spring Security — ProviderManager API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/ProviderManager.html): chuỗi provider và chính sách erase credentials.

**Ghi nhớ về phiên bản:** ví dụ chạy dựa vào API Spring Security **6.3.x**, tương ứng dòng Spring Boot 3.3.x. Khi dự án sử dụng Spring Security 7 hoặc hệ thống custom, kiểm tra lại constructor/API và cấu hình thực tế; không áp dụng máy móc một ví dụ username/password cho JWT, OIDC hoặc anonymous.