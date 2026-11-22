# Authentication với hai vai trò: yêu cầu xác thực và danh tính đã được xác thực

## 1. Vì sao một interface `Authentication` lại có hai ý nghĩa?

Trong Spring Security, `org.springframework.security.core.Authentication` là **một hợp đồng dữ liệu dùng ở hai thời điểm của quá trình xác thực**:

1. **Yêu cầu xác thực (authentication request):** một cơ chế nhận thông tin từ client tạo ra đối tượng `Authentication` để nói “tôi muốn xác minh danh tính này bằng bằng chứng này”. Đối tượng lúc đó **chưa đáng tin cậy**, thường có `isAuthenticated() == false`.
2. **Danh tính đã được xác thực (authenticated principal):** sau khi `AuthenticationManager` và `AuthenticationProvider` kiểm tra thành công, chúng trả về một `Authentication` biểu diễn danh tính được tin cậy theo cơ chế vừa áp dụng, thường có `isAuthenticated() == true` cùng các `GrantedAuthority` đã xác định.

Đây là **hai vai trò của cùng interface**, không phải hai class bắt buộc khác nhau, và không có nghĩa framework chỉ đổi một cờ trên chính đối tượng đầu vào. Một provider thường **tạo đối tượng kết quả mới** với principal phong phú hơn, quyền đã xác minh và credentials đã được xử lý. Khi thất bại, quá trình thường **ném `AuthenticationException`**, thay vì trả một danh tính đã xác thực.

Hãy coi `Authentication` là **phong bì truyền giữa các thành phần bảo mật**: lúc đầu chứa điều cần chứng minh, sau khi thành công chứa kết quả có thể dùng để áp dụng chính sách. Nội dung phong bì phụ thuộc kiểu xác thực, không chỉ giới hạn username/password.

### Mục tiêu sau bài học

- Phân biệt request token và authenticated token thông qua **thời điểm tạo, người tạo, trạng thái, principal, credentials và authorities**.
- Hiểu vì sao `AuthenticationManager.authenticate(...)` thường nhận và trả **cùng kiểu interface** nhưng ý nghĩa khác nhau.
- Dùng đúng `UsernamePasswordAuthenticationToken.unauthenticated(...)` để tạo yêu cầu username/password; quan sát đối tượng sau `DaoAuthenticationProvider`.
- Biết lúc nào `Authentication` được đặt vào `SecurityContext`, và vì sao **“có object” không đồng nghĩa “đã được xác thực”**.
- Tránh lỗi bảo mật như tự gán `isAuthenticated = true`, tự tạo quyền tin cậy hoặc ghi log mật khẩu.

## 2. Các thuộc tính giữ nguyên tên nhưng đổi vai trò

Giao diện `Authentication` kế thừa `Principal`. Những phương thức thường dùng:

| Phương thức | Ở dạng yêu cầu chưa xác thực | Ở dạng kết quả đã xác thực |
| --- | --- | --- |
| `getPrincipal()` | Thứ client khai báo muốn nhận diện, ví dụ chuỗi `"lan"`. Chưa được chứng minh. | Chủ thể đã xác minh; có thể là `UserDetails`, `Jwt`, `OAuth2User` hoặc đối tượng tùy cơ chế. |
| `getCredentials()` | Bằng chứng dùng để kiểm tra, ví dụ mật khẩu, bearer token hoặc đối tượng bằng chứng khác. | Có thể đã bị xóa/null sau khi xác thực; **không được dựa vào nó để truy xuất lại mật khẩu**. |
| `getAuthorities()` | Thường rỗng đối với username/password ban đầu; không nên tự coi quyền do client gửi là đáng tin cậy. | Danh sách quyền đã được provider xây dựng/ánh xạ, ví dụ `ROLE_READER`. |
| `isAuthenticated()` | Thường `false`: chưa qua bước chứng thực thích hợp. | Thường `true`: provider đã trả kết quả đáng tin cậy theo cơ chế cụ thể. |
| `getDetails()` | Có thể mang metadata request như IP/chi tiết phiên nếu filter đặt. | Không phải bằng chứng về vai trò hay danh tính; có thể được chuyển tiếp tùy provider. |
| `getName()` | Tên suy ra từ principal được khai báo. | Tên chủ thể được xác minh; không nên coi là khóa định danh toàn cục khi tích hợp IdP. |

`principal` không phải lúc nào cũng là `UserDetails`. Code viết `(UserDetails) authentication.getPrincipal()` cho mọi loại đăng nhập sẽ lỗi khi ứng dụng chuyển sang resource server JWT, OIDC hoặc pre-authentication.

`getAuthorities()` chỉ cung cấp các quyền được gắn trên token; quyền truy cập endpoint còn tùy **quy tắc authorization**. Có `ROLE_READER` không có nghĩa được đọc mọi dữ liệu của mọi người dùng.

### Cần hiểu đúng `isAuthenticated()`

- `isAuthenticated() == false` trên request token có nghĩa **yêu cầu chưa được chứng minh**.
- `isAuthenticated() == true` trên kết quả provider cho biết token đã được xác thực theo cơ chế đó. Nó **không nói người dùng được phép thực hiện mọi hành động**.
- Một `AnonymousAuthenticationToken` có thể báo `true` ở phương thức này vì cách biểu diễn anonymous trong framework. Vì vậy khi kiểm tra người dùng đăng nhập thật, **đừng chỉ viết `authentication != null && authentication.isAuthenticated()`**. Spring Security dùng thêm cơ chế nhận biết anonymous/remember-me, chẳng hạn `AuthenticationTrustResolver` trong các kiểm tra `authenticated()` và `fullyAuthenticated()`.

## 3. Ai tạo yêu cầu, ai trả kết quả?

Một luồng username/password Servlet điển hình:

```text
Client gửi username/password
     |
     v
Authentication filter (HTTP Basic, form login hoặc filter phù hợp)
     |
     | tạo UsernamePasswordAuthenticationToken.unauthenticated(...)
     |   principal = "lan"                 [CHƯA XÁC THỰC]
     |   credentials = mật khẩu
     |   isAuthenticated = false
     v
AuthenticationManager.authenticate(request)
     |
     v
ProviderManager chọn AuthenticationProvider hỗ trợ token
     |
     v
DaoAuthenticationProvider
     |---- UserDetailsService lấy user từ kho danh tính
     |---- PasswordEncoder so mật khẩu đã nhập với hash
     |---- kiểm tra trạng thái tài khoản và chính sách provider
     |
     +--- sai: ném AuthenticationException
     |
     +--- đúng: trả Authentication được xác thực
                     principal = UserDetails của "lan"
                     authorities = [ROLE_READER]
                     isAuthenticated = true          [ĐÃ XÁC THỰC]
     |
     v
Filter nhận kết quả và đặt vào SecurityContext
     |
     v
Authorization kiểm tra quyền truy cập
     |
     v
Controller/service xử lý request đã được cho phép
```

**Lưu ý 1 — đầu vào và đầu ra:** chữ ký thường thấy là:

```java
Authentication authenticated = authenticationManager.authenticate(request);
```

Hai biến có cùng kiểu interface `Authentication` nhưng **không có cùng mức độ tin cậy**. Không dùng object request chưa xác thực như thể nó là kết quả. Provider có thể trả một implementation khác, không bắt buộc sửa lại object ban đầu.

**Lưu ý 2 — bộ điều phối:** `AuthenticationManager` là hợp đồng; `ProviderManager` là triển khai phổ biến, thử các `AuthenticationProvider` phù hợp kiểu token. `DaoAuthenticationProvider` dùng cho username/password; xác thực JWT/OIDC dùng cơ chế và provider/token khác.

**Lưu ý 3 — trách nhiệm của filter:** gọi trực tiếp `authenticationManager.authenticate(...)` trong một service **không tự bảo đảm** kết quả sẽ được đặt vào `SecurityContext`, được lưu qua các request hoặc kích hoạt toàn bộ xử lý thành công/thất bại của một login filter. Khi dùng cơ chế filter chuẩn, framework quản lý việc đó theo cấu hình.

## 4. `UsernamePasswordAuthenticationToken`: một class, hai trạng thái

`UsernamePasswordAuthenticationToken` là ví dụ điển hình của mô hình này.

**Tạo yêu cầu chưa xác thực:**

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "lan",
        "DemoPass123!"
    );

System.out.println(request.isAuthenticated()); // false
```

Factory `unauthenticated(principal, credentials)` xây token chứa dữ liệu **chưa được kiểm tra**. Với username/password thông thường, danh sách authorities ở trạng thái này rỗng.

**Provider tạo kết quả sau khi kiểm tra:**

```java
Authentication result = authenticationManager.authenticate(request);
System.out.println(result.isAuthenticated()); // true nếu không ném exception
```

Một provider xác thực thành công có thể tạo token tin cậy thông qua API nội bộ thích hợp, chẳng hạn `UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)`. **Code nghiệp vụ không được gọi factory này để tự “công nhận” user vừa nhập tên và mật khẩu mà chưa kiểm tra.**

Không dùng `request.setAuthenticated(true)` để bỏ qua `AuthenticationManager`: triển khai token có thể từ chối bằng `IllegalArgumentException`; quan trọng hơn, thay cờ không làm mật khẩu đúng lên, không chứng minh danh tính và không làm các authorities do client gửi trở nên hợp lệ.

Một điều rất dễ nhầm:

```text
BEFORE: request.isAuthenticated() == false
AFTER : result.isAuthenticated()  == true
```

Không nên viết hoặc kỳ vọng rằng:

```text
request.isAuthenticated() tự động chuyển thành true
request == result luôn luôn đúng
request.getPrincipal() và result.getPrincipal() luôn cùng class
result.getCredentials() luôn còn nguyên mật khẩu
```

## 5. Demo Java 17+ chạy độc lập với Spring Security 6.5

Ví dụ dưới đây dùng **Java 17+, Spring Security 6.5.11 và Gradle**. Nó chạy ở console để quan sát rõ trạng thái trước và sau xác thực, không cần web server và không can thiệp vào session. `InMemoryUserDetailsManager` là kho user thử nghiệm; `DaoAuthenticationProvider` cùng `BCryptPasswordEncoder` thực hiện xác minh thật.

Cấu trúc tệp:

```text
authentication-two-roles/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AuthenticationRolesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'authentication-two-roles'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.AuthenticationRolesDemo'
}
```

`src/main/java/demo/AuthenticationRolesDemo.java`:

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class AuthenticationRolesDemo {

    public static void main(String[] args) {
        // (1) Kho danh tính và logic kiểm tra credential.
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetails user = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();
        UserDetailsService users = new InMemoryUserDetailsManager(user);

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(provider);

        // (2) Đầu vào: lời yêu cầu xác thực, chưa phải user được tin cậy.
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!");

        System.out.println("request.authenticated=" + request.isAuthenticated());
        System.out.println("request.name=" + request.getName());
        System.out.println("request.authorityCount=" + request.getAuthorities().size());
        System.out.println("request.hasCredentials=" + (request.getCredentials() != null));

        // (3) Provider xác minh hash và trả kết quả mới đã xác thực.
        Authentication result = manager.authenticate(request);

        System.out.println("result.authenticated=" + result.isAuthenticated());
        System.out.println("result.name=" + result.getName());
        System.out.println("result.principalIsUserDetails="
                + (result.getPrincipal() instanceof UserDetails));
        System.out.println("result.hasReaderRole="
                + result.getAuthorities().stream().anyMatch(
                        authority -> "ROLE_READER".equals(authority.getAuthority())));

        // (4) Demo đặt kết quả trong context; filter web thường làm việc này.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);

        try {
            Authentication current =
                    SecurityContextHolder.getContext().getAuthentication();
            System.out.println("context.name=" + current.getName());
        } finally {
            SecurityContextHolder.clearContext();
        }
        System.out.println("context.cleared="
                + (SecurityContextHolder.getContext().getAuthentication() == null));

        // (5) Không có kết quả thành công khi password sai.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrongPassword=BadCredentialsException");
        }
    }
}
```

Chạy tại thư mục gốc dự án bằng Gradle và JDK 17+ (hoặc Gradle Wrapper tương thích):

```bash
gradle run --quiet
```

Các dòng `System.out.println` của chương trình, theo đúng thứ tự:

```text
request.authenticated=false
request.name=lan
request.authorityCount=0
request.hasCredentials=true
result.authenticated=true
result.name=lan
result.principalIsUserDetails=true
result.hasReaderRole=true
context.name=lan
context.cleared=true
wrongPassword=BadCredentialsException
```

Nếu dependency logger phát thông tin riêng, các dòng log đó có thể khác; phần trên là stdout do chương trình demo tự in. `BCryptPasswordEncoder` tạo hash có salt ngẫu nhiên nên **không in hoặc so sánh literal hash**.

### Phân tích từng bước

**(1) Chuẩn bị kho danh tính:** `UserDetailsService` chỉ tải user; `PasswordEncoder` so mật khẩu được gửi vào với mật khẩu đã băm. `DaoAuthenticationProvider` kết hợp hai thành phần và kiểm tra điều kiện tài khoản.

**(2) Tạo request:** `request.getName()` đã là `lan` nhưng **đây mới là tên do client khai báo**. `getCredentials()` chứa chuỗi demo; việc có credentials không chứng minh chúng đúng. Số authorities ban đầu là 0.

**(3) Nhận result:** `manager.authenticate(request)` chỉ trả kết quả nếu một provider hỗ trợ đã xác thực thành công. `isAuthenticated()` là `true`, `principal` là đối tượng `UserDetails`, quyền `ROLE_READER` được lấy từ nguồn đã cấu hình. Không viết code phụ thuộc `result.getCredentials()` vì `ProviderManager` mặc định có thể xóa credentials sau xác thực.

**(4) Dùng `SecurityContext`:** demo tự đặt authentication đã xác minh vào context chỉ để cho thấy cách truy xuất. Đây là ví dụ console; trong HTTP request thực, filter bảo mật chịu trách nhiệm quản lý context theo cấu hình. `clearContext()` trong `finally` tránh giữ ngữ cảnh ở luồng console sau khi xong.

**(5) Password sai:** provider không trả authenticated token và ném `BadCredentialsException`. Đây không phải lỗi cấp quyền: yêu cầu chưa chứng minh được danh tính.

### Vì sao demo này không cần Spring Boot?

`Authentication`, `AuthenticationManager`, `ProviderManager`, `DaoAuthenticationProvider` và `SecurityContextHolder` thuộc **Spring Security**. Spring Boot có thể cấu hình/khởi tạo các thành phần trong ứng dụng web, nhưng **hai vai trò request/result của interface** tồn tại độc lập với Boot. Khi đặt chúng vào Spring Boot, thường để filter chuẩn gọi manager và duy trì context theo request, thay vì tự gọi thủ công như demo console.

## 6. Dùng `Authentication` trong ứng dụng Spring Boot thực tế

Ở endpoint HTTP đã qua bộ lọc bảo mật, controller có thể nhận `Authentication` hiện hành:

```java
// Đoạn minh họa nằm trong một @RestController của ứng dụng đã
// cấu hình Spring Security; không phải một class chạy độc lập.
@GetMapping("/me")
public Map<String, Object> me(Authentication authentication) {
    if (authentication == null) {
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
    return Map.of(
        "username", authentication.getName(),
        "authorities", authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
```

Cần các import `Map`, `Authentication`, `GrantedAuthority`, `GetMapping`, `ResponseStatusException` và `HttpStatus`; route này phải được bảo vệ bằng `SecurityFilterChain` phù hợp. Code trên **chỉ trình bày cách dùng principal/authorities**, không thay thế quy tắc `authorizeHttpRequests(...)` và không tự quyết định quyền bằng một tên được truyền từ request body.

Trong Spring MVC/Servlet, người đọc có thể gặp:

- `Authentication authentication` trong method controller: đại diện cho ngữ cảnh bảo mật hiện hành, khi framework cung cấp tham số này.
- `SecurityContextHolder.getContext().getAuthentication()`: cách truy cập ngữ cảnh hiện tại khi cần ngoài controller; có thể là `null`, hoặc token anonymous.
- `@AuthenticationPrincipal`: đưa **principal đã được xác thực** vào một tham số theo kiểu phù hợp; không bắt buộc mọi principal là `UserDetails`.
- `hasRole(...)` / `hasAuthority(...)`: quyết định **có được phép** truy cập, khác với `isAuthenticated()`.

Không nên biến `getName()` thành một kiểm tra sở hữu tài nguyên duy nhất nếu endpoint xử lý đối tượng nhiều người dùng; cần đối chiếu principal ổn định với tài nguyên và chính sách nghiệp vụ.

## 7. Cơ chế xác thực khác vẫn sử dụng cùng ý tưởng

Hai vai trò không bị ràng buộc vào `UsernamePasswordAuthenticationToken`:

| Cơ chế | Biểu diễn đầu vào chưa tin cậy | Biểu diễn sau khi kiểm chứng |
| --- | --- | --- |
| Username/password | Username + mật khẩu trong request token. | Principal đã xác thực (thường `UserDetails`), authorities từ provider. |
| HTTP Basic | Filter đọc `Authorization: Basic ...` rồi tạo token yêu cầu username/password. | Kết quả provider dùng trong `SecurityContext` của request. |
| Form login | Filter đọc tham số form rồi tạo yêu cầu xác thực. | Kết quả được dùng để thiết lập phiên/ngữ cảnh theo cấu hình đăng nhập. |
| JWT bearer token | Filter/manager nhận bearer token chưa được tin cậy. | Sau khi xác minh chữ ký, issuer, thời hạn và điều kiện đã cấu hình, có thể tạo `JwtAuthenticationToken` với principal/claims và authorities được ánh xạ. |
| OIDC/OAuth2 login | Có luồng ủy quyền, callback và kiểm chứng bằng chứng từ IdP, không chỉ cặp username/password. | Authenticated principal của cơ chế OAuth2/OIDC, có thể có attributes/claims và authorities. |

Mỗi cơ chế có cách tạo và kiểm chứng token riêng. **Không ép mọi token thành `UsernamePasswordAuthenticationToken`** hay giả định `principal` lúc nào cũng có mật khẩu. Với JWT, access token có thể đóng vai trò đầu vào để kiểm chứng và không hề cần gọi `UserDetailsService` ở mỗi request; điều đó không thay đổi nguyên tắc chung “đầu vào chưa tin cậy → xác minh → kết quả đáng tin cậy”.

Mức độ tin cậy sau khi xác thực có **phạm vi**: ví dụ JWT được xác thực không có nghĩa người sở hữu được xem mọi hóa đơn. Authorization, kiểm tra account policy và kiểm tra quyền trên dữ liệu vẫn là các quyết định riêng.

## 8. `Authentication` và `SecurityContext`: tách hai trách nhiệm

`Authentication` là **đối tượng mô tả yêu cầu/kết quả danh tính**. `SecurityContext` là **nơi giữ authentication cho ngữ cảnh xử lý hiện hành**; `SecurityContextHolder` cung cấp truy cập tới ngữ cảnh đó.

Trong HTTP request Servlet, Spring Security thường đọc/tạo context ở đầu chuỗi filter, cập nhật context sau một cơ chế xác thực thành công, rồi kết thúc và dọn context phù hợp. Việc **duy trì qua request tiếp theo** có thể dựa vào session và `SecurityContextRepository`, hoặc tạo lại từ credentials/token trên request mới; phụ thuộc cấu hình và cơ chế bảo mật.

Ba nhận định cần tách:

1. `AuthenticationManager.authenticate(request)` **trả đối tượng kết quả**; bản thân việc gọi thủ công không bảo đảm context web được cập nhật.
2. `SecurityContextHolder.getContext().setAuthentication(result)` **đặt kết quả cho ngữ cảnh hiện hành**; thao tác này không mặc nhiên lưu phiên hay gửi cookie đăng nhập.
3. **Authentication khác authorization**: sau khi đã có result đáng tin cậy, bộ kiểm tra quyền mới quyết định request có được đi tiếp hay không.

Khi tự xây dựng custom authentication filter, cần hiểu contract của filter, xử lý thành công/thất bại, session/context repository, vấn đề request đồng thời và clear context. Đừng suy luận rằng chỉ cần gọi một setter ở service là đã hoàn tất “login” an toàn.

## 9. Các sai lầm phổ biến và cách sửa

### Sai lầm 1: tự tạo “authenticated token” từ input chưa kiểm chứng

```java
// Sai về nguyên tắc bảo mật: chưa kiểm tra password hay token.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest, null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
```

Code trên cấp niềm tin/quyền dựa trên dữ liệu do client có thể kiểm soát. Chỉ thành phần xác thực đáng tin cậy, sau khi hoàn tất kiểm tra cần thiết, mới nên tạo result có `isAuthenticated() == true` và authorities.

**Đúng:** tạo request bằng `unauthenticated(...)`; chuyển tới `AuthenticationManager` được cấu hình và chỉ dùng giá trị trả về sau khi thành công.

### Sai lầm 2: tưởng request đã được biến đổi tại chỗ

```java
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
    username, password);
Authentication result = manager.authenticate(request);
// Dùng result; không giả định request chính là result.
```

Nếu giữ lại request làm authentication hiện hành, bạn có thể giữ lại token chưa xác thực hoặc credential nhạy cảm. Hãy dùng **kết quả trả về**.

### Sai lầm 3: kiểm tra mỗi `isAuthenticated()` để nhận biết người dùng thật

Cần phân biệt anonymous và remember-me theo chính sách. `AuthenticationTrustResolver` có các phép kiểm tra tương ứng; trong cấu hình HTTP Spring Security, `authenticated()`, `fullyAuthenticated()` và rule theo role là các lựa chọn đúng ngữ cảnh hơn một biểu thức tự kiểm tra cờ ngây thơ.

### Sai lầm 4: coi thông tin ở request là quyền đã cấp

Client có thể gửi `role=ADMIN`, một claim tự chế hoặc username bất kỳ. Chỉ tin những dữ liệu đã qua cơ chế kiểm chứng, và phải ánh xạ authorities ở phía server. Kiểm tra “đã đăng nhập” không thay thế kiểm tra quyền trên từng tài nguyên.

### Sai lầm 5: in `getCredentials()` hoặc toàn bộ token ra log

Token/request có thể chứa password hoặc bearer token. Ngay cả khi result đã xóa credentials, log đối tượng ban đầu hay metadata không được kiểm soát vẫn rò rỉ bí mật. Chỉ ghi thông tin audit an toàn như kết quả, loại mechanism, mã lỗi tổng quát, correlation ID; không ghi raw secret.

### Sai lầm 6: dùng `getPrincipal()` mà không xét kiểu token

Với username/password dùng `DaoAuthenticationProvider`, principal sau xác thực thường là `UserDetails`. Với OIDC có thể là `OidcUser`; với resource server là `Jwt` hoặc principal theo converter. Dùng các abstraction phù hợp hoặc `getName()` cùng quy tắc ánh xạ identity ổn định.

### Sai lầm 7: bỏ xử lý thất bại

`AuthenticationManager.authenticate(...)` có thể ném `BadCredentialsException`, `DisabledException`, `LockedException` hoặc subclass khác của `AuthenticationException`. Không được bắt mọi exception rồi trả token đã xác thực “để ứng dụng chạy tiếp”. Với web login, để bộ lọc xử lý exception theo cơ chế đăng nhập và hạn chế làm lộ thông tin phân biệt “không tồn tại user” với “sai mật khẩu”.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Token có `principal="lan"` và `getCredentials()!=null`. Nó đã được xác thực chưa?

**Trả lời:** Chưa thể kết luận. Một request token có thể chứa username và password hoàn toàn sai. Phải xét trạng thái và quy trình provider xác minh, không suy ra từ việc có dữ liệu.

**Câu 2.** Sau `manager.authenticate(request)` thành công, có nên lấy `request.getAuthorities()` để phân quyền không?

**Trả lời:** Không. Dùng `result.getAuthorities()` từ đối tượng đã được xác thực và áp dụng chính sách authorization.

**Câu 3.** `AnonymousAuthenticationToken.isAuthenticated()` có thể trả `true`. Có nên suy ra người dùng đã đăng nhập thành công không?

**Trả lời:** Không. Spring Security phân biệt anonymous/remember-me với xác thực thực sự bằng cơ chế kiểm tra mức độ tin cậy.

**Câu 4.** Một phương thức console gọi `manager.authenticate(...)` thành công có tự tạo session đăng nhập HTTP không?

**Trả lời:** Không. Kết quả xác thực và việc gắn/lưu `SecurityContext` là hai trách nhiệm khác nhau. Phần phiên web thuộc cấu hình và cơ chế filter/repository.

**Câu 5.** JWT đã được xác minh có nghĩa user được gọi mọi API không?

**Trả lời:** Không. Xác thực token chỉ cung cấp danh tính/claims đáng tin cậy theo kiểm chứng đã cấu hình; authorization quyết định quyền cụ thể.

## 11. Tài liệu đối chiếu

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): quan hệ `Authentication`, `AuthenticationManager`, `ProviderManager` và `SecurityContextHolder`.
- [Spring Security — Authentication API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html): contract, principal, credentials, authorities, `isAuthenticated()`.
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): hai factory `unauthenticated(...)` và `authenticated(...)`.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): kiểm tra credentials với `UserDetailsService` và `PasswordEncoder`.
- [Spring Security — AuthenticationTrustResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): phân biệt authenticated, anonymous và remember-me.

**Ý chính:** cùng interface `Authentication` có thể mô tả cả **đề nghị xác thực chưa được tin cậy** lẫn **kết quả xác thực đã qua kiểm chứng**. Sự chuyển đổi niềm tin diễn ra ở `AuthenticationManager`/`AuthenticationProvider`. Sau đó framework đặt **kết quả**, chứ không phải request chưa kiểm chứng, vào ngữ cảnh bảo mật để các chính sách quyền sử dụng.