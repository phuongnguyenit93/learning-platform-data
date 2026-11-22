# authenticated, anonymous, rememberMe và fullyAuthenticated trong Spring Security

Trong một ứng dụng có đăng nhập, câu hỏi “người dùng đã xác thực chưa?” chưa đủ để xác định mọi quyền truy cập. Spring Security phân biệt người truy cập **ẩn danh**, người **được nhận diện trở lại từ thông tin ghi nhớ đăng nhập** và người **được xác thực đầy đủ**. Bốn điều kiện ủy quyền `authenticated`, `anonymous`, `rememberMe` và `fullyAuthenticated` giúp chính sách sử dụng các mức tin cậy đó.

Bài này thuộc chủ đề **Phân quyền** của Spring Security fundamentals: mục tiêu là hiểu đúng điều kiện xét quyền, viết quy tắc HTTP/method security và dự đoán kết quả trước khi kiểm thử. Ví dụ chính dùng Java 17+, Spring Security 6.3.x với Servlet (`HttpSecurity`). Cuối bài phân biệt phần có thể áp dụng cho WebFlux; không sao chép máy móc cú pháp Servlet sang reactive.

## 1. Bài toán: một danh tính có nhiều trạng thái tin cậy

Hãy hình dung ứng dụng ngân hàng có ba chức năng:

- Trang giới thiệu: bất kỳ ai đều đọc được.
- Xem bảng điều khiển cá nhân: người dùng đã đăng nhập trực tiếp hoặc được đăng nhập lại bằng remember-me có thể xem.
- Thay đổi thông tin thanh toán: yêu cầu phiên xác thực đầy đủ; đăng nhập lại chỉ bằng cookie remember-me không đủ.

Nếu cấu hình tất cả bằng `authenticated()`, người dùng được khôi phục từ remember-me có thể đi vào cả trang nhạy cảm. Nếu cấu hình nhầm `rememberMe()` ở trang cá nhân, một người vừa đăng nhập trực tiếp có thể bị từ chối dù mức xác thực của họ mạnh hơn. Do vậy, trước hết cần phân biệt **bốn điều kiện** và **những trạng thái đối tượng `Authentication`** mà chúng nhận diện.

Spring Security sử dụng khái niệm mức độ tin cậy xác thực (*authentication trust level*) để quyết định truy cập. Đây là một khía cạnh của **authorization** (có quyền thực hiện hành động hay không), nhưng nó dựa trên cách ứng dụng **authentication** (xác định danh tính). Không đồng nhất nó với quyền nghiệp vụ như `ROLE_ADMIN`.

## 2. Bảng so sánh bắt buộc phải nắm

Bảng dưới giả sử bộ kiểm tra tin cậy và token mặc định của Spring Security, người dùng có trạng thái đầy đủ hợp lệ, và quy tắc chỉ xét đúng một điều kiện tương ứng.

| Trạng thái của yêu cầu | `authenticated()` | `anonymous()` | `rememberMe()` | `fullyAuthenticated()` |
| --- | :---: | :---: | :---: | :---: |
| Khách ẩn danh với `AnonymousAuthenticationToken` | ❌ | ✅ | ❌ | ❌ |
| Người dùng được nhận diện qua `RememberMeAuthenticationToken` | ✅ | ❌ | ✅ | ❌ |
| Người dùng đã đăng nhập đầy đủ (chẳng hạn `UsernamePasswordAuthenticationToken` thành công) | ✅ | ❌ | ❌ | ✅ |

Đọc bảng theo từng điều kiện:

- **`authenticated()`**: chấp nhận người dùng đã được xác thực và không ẩn danh; **bao gồm remember-me và xác thực đầy đủ**.
- **`anonymous()`**: chỉ khớp với trạng thái ẩn danh mà Spring Security nhận diện; nó **không** phải tên khác của `permitAll()`.
- **`rememberMe()`**: đúng khi người dùng được nhận diện bởi cơ chế remember-me; trong các bộ kiểm tra mặc định, **người đăng nhập đầy đủ không được coi là “đăng nhập bằng remember-me”**.
- **`fullyAuthenticated()`**: đúng khi người dùng đã xác thực nhưng **không phải anonymous hoặc remember-me**.

Bảng mô tả **điều kiện riêng lẻ**, chưa bao gồm vai trò, quyền tài nguyên, thời hạn phiên, ràng buộc thiết bị hoặc cơ chế xác thực nhiều yếu tố. Đường dẫn có thể dùng thêm `hasRole` / `hasAuthority` và nhiều kiểm tra khác.

**Lưu ý về trạng thái không có `Authentication` (`null`):** đó không phải một `AnonymousAuthenticationToken`. Trong cấu hình Servlet thông thường, `AnonymousAuthenticationFilter` tạo token ẩn danh khi cần; nếu chủ động tắt cơ chế này, đừng mặc định điều kiện `anonymous()` vẫn có token ẩn danh để xét. Khi không có danh tính hợp lệ, những quy tắc yêu cầu xác thực không được coi là đạt.

## 3. authenticated(): có xác thực, bao gồm remember-me

### Ý nghĩa

`authenticated()` là điều kiện phổ biến cho trang cá nhân hoặc API yêu cầu danh tính đã được xác thực. Nó cho phép:

- Người dùng vừa đăng nhập bằng mật khẩu/OIDC hoặc cơ chế xác thực hoàn chỉnh tương ứng.
- Người dùng được phục hồi đăng nhập bằng remember-me, nếu ứng dụng thực sự hỗ trợ và đã xác thực thành công cookie remember-me.

Nó **không** cho phép khách ẩn danh chỉ vì Spring Security đã đặt một token ẩn danh vào ngữ cảnh bảo mật.

Ví dụ Servlet:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/account/**").authenticated()
        .anyRequest().denyAll()
);
~~~

Nếu `/account/profile` cần hiển thị hồ sơ cơ bản thì đây có thể là chính sách thích hợp. Nếu `/account/change-password` cũng nằm dưới mẫu này, hãy tạo ngoại lệ riêng dùng `fullyAuthenticated()` hoặc một chính sách xác thực mạnh hơn và đặt quy tắc cụ thể trước quy tắc rộng.

### Vì sao không kiểm tra trực tiếp Authentication.isAuthenticated()?

`Authentication.isAuthenticated()` là cờ thể hiện đối tượng token đã được đánh dấu xác thực; nó **không phải toàn bộ hợp đồng của điều kiện `authenticated` trong Spring Security**. Đặc biệt, `AnonymousAuthenticationToken` thường có `isAuthenticated() == true` để thống nhất cách làm việc với ngữ cảnh bảo mật, nhưng nó **không** đại diện cho người dùng đã đăng nhập.

Đoạn kiểm tra tự viết sau dễ mắc lỗi:

~~~java
// Sai nếu xem đây là định nghĩa của "người dùng đã đăng nhập".
boolean loggedIn = authentication != null && authentication.isAuthenticated();
~~~

Hãy dùng quy tắc được framework cung cấp, hoặc khi phải kiểm tra thủ công thì dùng `AuthenticationTrustResolver` / `AuthenticatedAuthorizationManager` phù hợp thay vì chỉ dựa vào cờ.

## 4. anonymous(): yêu cầu khách ẩn danh, không có nghĩa “trang công khai”

Spring Security có thể đặt `AnonymousAuthenticationToken` vào `SecurityContextHolder` trong chuỗi Servlet để các thành phần phía sau luôn có thông tin đại diện người truy cập, kể cả khi chưa đăng nhập. Token thường mang tên như `anonymousUser` và quyền `ROLE_ANONYMOUS`.

Điều kiện `anonymous()` dùng khi muốn **chỉ khách chưa đăng nhập** truy cập một chức năng, chẳng hạn một trang khởi động trải nghiệm riêng dành cho khách.

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/guest-only/**").anonymous()
        .anyRequest().authenticated()
);
~~~

Khi đã đăng nhập đầy đủ hoặc đang được nhận diện qua remember-me, yêu cầu khớp `/guest-only/**` không đáp ứng `anonymous()`. Đó là điều kiện về **trạng thái người truy cập**; nó không tự động chuyển hướng người đã đăng nhập sang trang khác.

**Khác biệt với `permitAll()`:**

| Quy tắc | Khách ẩn danh | Remember-me | Xác thực đầy đủ | Mục tiêu |
| --- | :---: | :---: | :---: | --- |
| `permitAll()` | ✅ | ✅ | ✅ | Tài nguyên công khai cho mọi người |
| `anonymous()` | ✅ | ❌ | ❌ | Chỉ khách chưa đăng nhập |
| `authenticated()` | ❌ | ✅ | ✅ | Người dùng đã xác thực |

Trang đăng nhập, trang giới thiệu, tài nguyên tĩnh thường phù hợp với `permitAll()`: người đã đăng nhập vẫn có thể tải chúng nếu cần. Trang chỉ khách chưa đăng nhập là tình huống cụ thể hơn; đừng sử dụng `anonymous()` đơn thuần vì cho rằng nó đồng nghĩa “public”.

Trong Servlet, `AnonymousAuthenticationFilter` thường chạy khi chưa có `Authentication`, nhưng chỉ khi cơ chế anonymous đã được bật trong chuỗi bảo mật. Trong WebFlux, cách đưa anonymous vào ngữ cảnh và cấu hình có khác biệt, nên phải kiểm tra API/cấu hình reactive của phiên bản đang dùng.

## 5. rememberMe(): biết người dùng nhờ cơ chế ghi nhớ đăng nhập

### Remember-me thực sự hoạt động thế nào?

Remember-me là cơ chế giúp nhận diện lại người dùng qua những lần truy cập sau, thường bằng cookie dài hạn. Trên Servlet, Spring Security hỗ trợ giải pháp dựa trên chữ ký token hoặc token lưu bền vững phía máy chủ. Khi cookie hợp lệ và bộ lọc remember-me chạy đúng, hệ thống tạo `RememberMeAuthenticationToken` và đưa vào ngữ cảnh bảo mật.

Luồng khái quát:

~~~text
Đăng nhập tương tác thành công
  ↓
Ứng dụng cấp cookie remember-me (nếu đã bật và đáp ứng điều kiện cấp)
  ↓
Một lần truy cập sau, không còn phiên đăng nhập trực tiếp
  ↓
RememberMeAuthenticationFilter kiểm tra cookie hợp lệ
  ↓
RememberMeAuthenticationToken
  ↓
authenticated()  = true
rememberMe()     = true
fullyAuthenticated() = false
~~~

Điểm mấu chốt là **remember-me có thể xác thực danh tính ở mức được ghi nhớ**, nhưng ứng dụng có thể cần một bước xác thực trực tiếp khác trước các thao tác nhạy cảm.

### rememberMe() không có nghĩa “remember-me hoặc mạnh hơn”

Điều kiện `rememberMe()` của `AuthenticatedAuthorizationManager` / DSL Servlet kiểm tra đúng loại người dùng được **nhận diện bằng remember-me**, không phải phép so sánh mức tin cậy “ít nhất remember-me”. Vì vậy:

- `rememberMe()`: người dùng remember-me **đạt**; người đăng nhập đầy đủ **không đạt**.
- `authenticated()`: **cả** hai trạng thái đã xác thực đều đạt.
- `fullyAuthenticated()`: chỉ người dùng xác thực đầy đủ đạt.

Điều kiện `rememberMe()` hợp lý khi cần **phân biệt nhóm phiên remember-me** để cung cấp một hành vi hoặc đường dẫn đặc thù. Đối với chức năng mà cả người remember-me lẫn người đăng nhập trực tiếp đều được phép dùng, **nên chọn `authenticated()`**, có thể kết hợp thêm vai trò/quyền.

### Remember-me khác gì một phiên HTTP được duy trì?

Một người có cookie phiên (`JSESSIONID` hoặc cơ chế lưu phiên tương tự) sau khi đăng nhập thành công có thể vẫn là người dùng **fully authenticated** trong các yêu cầu sau; phiên sống lâu không tự động biến thành remember-me. Ngược lại, khi phiên trực tiếp không còn, cơ chế remember-me có thể nhận diện lại bằng cookie riêng rồi tạo `RememberMeAuthenticationToken`.

Không được suy luận loại xác thực chỉ từ “trình duyệt tự động đăng nhập” hay “có cookie”. Cần xem `Authentication` được tạo bằng bộ lọc/cơ chế nào.

### An toàn khi dùng remember-me

Cookie remember-me là dữ liệu xác thực nhạy cảm. Với ứng dụng thật, cần HTTPS, thuộc tính cookie phù hợp (`Secure`, `HttpOnly`, `SameSite` theo ngữ cảnh), thời hạn hợp lý, quy trình vô hiệu hóa khi đăng xuất/đổi mật khẩu và chiến lược lưu token. Cookie dài hạn nếu bị đánh cắp có thể bị tái sử dụng đến khi hết hiệu lực hoặc bị thu hồi.

Chức năng như đổi mật khẩu, chuyển tiền hoặc đổi phương thức khôi phục tài khoản không nên chỉ dựa vào remember-me. `fullyAuthenticated()` có thể là một **lớp yêu cầu bổ sung**, nhưng chưa thay thế được việc xác thực lại gần thời điểm giao dịch hay MFA khi chính sách yêu cầu.

## 6. fullyAuthenticated(): không ẩn danh và không dùng remember-me

`fullyAuthenticated()` yêu cầu Spring Security coi người dùng đã xác thực bằng cách khác với remember-me. Điểm khác `authenticated()` là nó **loại remember-me**.

Ví dụ cho trang nhạy cảm:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/account/confirm-sensitive/**").fullyAuthenticated()
        .requestMatchers("/account/**").authenticated()
        .anyRequest().denyAll()
);
~~~

Quy tắc cụ thể cần nằm **trước** `/account/**` vì cấu hình chọn quy tắc khớp đầu tiên. Khi người dùng remember-me truy cập `/account/confirm-sensitive/email`, điều kiện `fullyAuthenticated` không đạt. Tùy cấu hình xử lý lỗi và điểm bắt đầu xác thực, ứng dụng có thể yêu cầu đăng nhập lại thay vì đơn giản trả 403.

**Không được suy ra `fullyAuthenticated()` có nghĩa:**

- Người dùng vừa nhập mật khẩu ở yêu cầu hiện tại.
- Đã thực hiện MFA, sinh trắc học, passkey hoặc bước xác thực bổ sung.
- Phiên còn mới trong vài phút gần đây.
- Người dùng có một vai trò đặc biệt như ADMIN.

Nó chỉ nói về **phân loại mức tin cậy do `AuthenticationTrustResolver` nhận diện**. Một phiên được tạo sau khi đăng nhập đầy đủ từ nhiều giờ trước có thể vẫn đạt. Muốn xác thực tăng cường (*step-up authentication*) hay xác thực lại gần thời điểm giao dịch, cần quy tắc và cơ chế riêng: dấu thời gian xác thực, thông tin mức đảm bảo từ nhà cung cấp danh tính, xác minh lại yếu tố hoặc xác thực riêng cho giao dịch; tuyệt đối không dùng tên điều kiện này để thay cho bằng chứng MFA.

## 7. Cơ chế nội bộ: AuthenticationTrustResolver

Spring Security không xác định bốn điều kiện đơn thuần bằng việc so sánh chuỗi `"anonymous"` hay `"remember-me"`. Thành phần tiêu biểu là `AuthenticationTrustResolver`, với cách triển khai `AuthenticationTrustResolverImpl`. Trong mô hình mặc định:

~~~text
Authentication
    |
    +-- null / không có xác thực hợp lệ
    |       └── không đạt authenticated / fullyAuthenticated
    |
    +-- AnonymousAuthenticationToken
    |       └── anonymous
    |
    +-- RememberMeAuthenticationToken
    |       └── remembered
    |
    +-- Token đã xác thực đầy đủ (và không thuộc hai nhóm trên)
            └── fullyAuthenticated
~~~

Các phép kiểm tra tương ứng:

- `isAnonymous(authentication)`: nhận diện người dùng ẩn danh, thường qua `AnonymousAuthenticationToken`.
- `isRememberMe(authentication)`: nhận diện người dùng được nhớ đăng nhập, thường qua `RememberMeAuthenticationToken`.
- `isAuthenticated(authentication)`: giá trị xác thực phù hợp, không phải anonymous; thường bao gồm remember-me và fully authenticated.
- `isFullyAuthenticated(authentication)`: xác thực phù hợp nhưng không phải remember-me; cũng loại anonymous.

Về logic, với cấu hình tin cậy mặc định:

~~~text
authenticated        = authenticated and NOT anonymous
rememberMe           = token được đánh dấu remember-me
fullyAuthenticated   = authenticated and NOT remember-me
anonymous            = token được đánh dấu anonymous
~~~

Dòng thứ nhất là **ý nghĩa của chính sách**: không nhầm nó với phép gọi `Authentication.isAuthenticated()` vốn có thể trả true trên token anonymous. Nếu dùng `AuthenticationTrustResolver` tùy chỉnh, hành vi có thể khác vì cách phân loại token đã thay đổi.

### Trường hợp không có token và cách xử lý HTTP

Không có `Authentication` hợp lệ hoặc có token anonymous không đồng nghĩa framework luôn trả cùng một mã HTTP. Một yêu cầu tới đường dẫn cần đăng nhập có thể nhận HTTP 401 nếu cấu hình HTTP Basic/Bearer, hoặc HTTP 302 tới màn hình đăng nhập với form login. Khi người dùng đã đăng nhập nhưng thiếu quyền nghiệp vụ, 403 là phản hồi thường thấy. Với phiên remember-me bị chặn vì yêu cầu `fullyAuthenticated`, bộ lọc xử lý ngoại lệ có thể kích hoạt lại quá trình xác thực.

Do đó, **hãy phân biệt kết quả quyết định quyền với phản hồi HTTP cuối cùng**. Những thành phần như `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler` (Servlet) quyết định bước tiếp theo theo trạng thái xác thực và cấu hình.

## 8. Cấu hình Servlet hoàn chỉnh: bốn điều kiện trên bốn URL

Dưới đây là cấu hình Java 17+ dùng Spring Boot với `spring-boot-starter-web` và `spring-boot-starter-security`. Đặt trong `SecurityConfig.java` dưới thư mục nguồn Java và thêm dòng `package` cho phù hợp dự án.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/css/**", "/login").permitAll()
                .requestMatchers("/guest-only/**").anonymous()
                .requestMatchers("/remember-only/**").rememberMe()
                .requestMatchers("/account/payment/**").fullyAuthenticated()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ý nghĩa các đường dẫn:

| Đường dẫn | Quy tắc | Ví dụ mục đích |
| --- | --- | --- |
| `/`, `/css/**`, `/login` | `permitAll()` | Tài nguyên công khai |
| `/guest-only/**` | `anonymous()` | Trải nghiệm chỉ cho khách |
| `/remember-only/**` | `rememberMe()` | Minh họa đường dẫn chỉ dành cho trạng thái remember-me |
| `/account/payment/**` | `fullyAuthenticated()` | Từ chối phiên chỉ nhận diện qua remember-me |
| `/account/**` | `authenticated()` | Tài khoản cơ bản, chấp nhận remember-me lẫn đầy đủ |
| Mọi đường dẫn chưa có quy tắc | `denyAll()` | Mặc định từ chối |

**Đây là ví dụ giảng dạy về điều kiện xét quyền.** Các endpoint trong bảng cần được hiện thực riêng (Controller, HTML, v.v.) thì yêu cầu thực tế mới trả nội dung. Cấu hình remember-me còn cần `UserDetailsService` thích hợp và chính sách cookie/token chuẩn cho môi trường triển khai; đoạn trên không tự tạo cơ sở dữ liệu người dùng hoặc Controller. Trên hệ thống thật, đường `/remember-only/**` rất ít khi cần; thường dùng `authenticated()` để cả hai trạng thái đã xác thực cùng truy cập.

**Thứ tự quy tắc quyết định kết quả:** Nếu viết `.requestMatchers("/account/**").authenticated()` trước `.requestMatchers("/account/payment/**").fullyAuthenticated()`, đường dẫn nhạy cảm sẽ khớp quy tắc rộng trước, làm mất yêu cầu xác thực đầy đủ. Đây là lỗi phân quyền nghiêm trọng ngay cả khi từng dòng đơn lẻ đều đúng cú pháp.

### Bật remember-me không tự biến mọi phiên thành remember-me

`.rememberMe(Customizer.withDefaults())` kích hoạt cơ chế ghi nhớ đăng nhập trong ứng dụng Servlet. Người dùng đăng nhập thường vẫn có thể được xem là fully authenticated. Chỉ khi request sau đó được xác thực bằng remember-me, Spring Security mới tạo token loại remember-me. Hãy kiểm thử **cả** đăng nhập trực tiếp, phục hồi từ cookie và phiên đã đăng xuất.

Trong ứng dụng sản xuất, nên chỉ định khóa ký và kho lưu token bền vững theo yêu cầu, thay vì mặc định coi cấu hình minh họa là đủ an toàn. Vẫn phải xử lý chống CSRF, ràng buộc cookie, vòng đời token và hủy hiệu lực khi thông tin đăng nhập thay đổi.

## 9. Dùng trong bảo mật phương thức: @PreAuthorize

Bốn điều kiện cũng xuất hiện dưới dạng biểu thức Spring Security, phù hợp khi kiểm tra **hành động nghiệp vụ**, không chỉ URL. Đối với Java Servlet sử dụng method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Sau khi bật, có thể bảo vệ phương thức bằng các biểu thức:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountService {

    @PreAuthorize("isAuthenticated()")
    public String readBasicProfile() {
        return "Basic profile";
    }

    @PreAuthorize("isAnonymous()")
    public String startGuestOnboarding() {
        return "Guest onboarding";
    }

    @PreAuthorize("isRememberMe()")
    public String explainRememberedSession() {
        return "Remembered session";
    }

    @PreAuthorize("isFullyAuthenticated() and hasRole('USER')")
    public String viewSensitiveAccountDetails() {
        return "Sensitive details";
    }
}
~~~

Mã ở trên là hai tệp Java độc lập trong **một ứng dụng Spring** (`MethodSecurityConfiguration.java` và `AccountService.java`). Chúng được trình bày để minh họa biểu thức và cần chạy bên trong ứng dụng có cấu hình method security. Đừng gọi các phương thức trực tiếp bằng một đối tượng được tạo qua `new AccountService()` rồi coi đó là kiểm thử bảo mật: gọi như vậy bỏ qua đối tượng proxy/interceptor mà Spring dùng để thi hành `@PreAuthorize`.

Có hai lưu ý quan trọng:

1. `hasRole('USER')` kiểm tra quyền `ROLE_USER` theo quy ước mặc định, **khác** với tình trạng fully authenticated. Một người có `ROLE_USER` nhưng chỉ được nhận diện qua remember-me **không** đạt `isFullyAuthenticated()`.
2. `isRememberMe()` là điều kiện chỉ khớp trạng thái remember-me. Nếu yêu cầu được phép từ remember-me trở lên, dùng `isAuthenticated()` thay vì `isRememberMe()`.

Với method security trong WebFlux, cơ chế cấu hình và chuỗi phản ứng phải phù hợp (`@EnableReactiveMethodSecurity` đối với cấu hình reactive); không trộn proxy và cách đọc ngữ cảnh bảo mật của Servlet với Reactor.

## 10. Kiểm thử bằng token thật của Spring Security

Không nên chỉ kiểm thử bằng một `UsernamePasswordAuthenticationToken` rồi suy diễn hành vi của anonymous/remember-me. Trong các phép thử đơn vị, hãy tạo đúng ba loại token và xác nhận từng điều kiện.

Giả sử dự án dùng Spring Boot 3.3.x với Spring Security 6.3.x, có các phụ thuộc:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đặt `TrustLevelTest.java` trong `src/test/java` của dự án (thêm dòng `package` theo thư mục thực tế). Ví dụ sau kiểm tra cả `AuthenticationTrustResolver` và `AuthenticatedAuthorizationManager`; `check(...)` là API có trong Spring Security 6.3.x.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrustLevelTest {

    private final AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

    private Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "demo-key", "guest",
                AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS"));
    }

    private Authentication remembered() {
        return new RememberMeAuthenticationToken(
                "demo-key", "mai",
                AuthorityUtils.createAuthorityList("ROLE_USER"));
    }

    private Authentication fullyLoggedIn() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "mai", "n/a",
                AuthorityUtils.createAuthorityList("ROLE_USER"));
    }

    @Test
    void anonymousTokenIsNotARealLogin() {
        Authentication auth = anonymous();

        // Bẫy: cờ của anonymous token có thể vẫn là true.
        assertTrue(auth.isAuthenticated());
        assertTrue(trust.isAnonymous(auth));
        assertFalse(trust.isAuthenticated(auth));
        assertFalse(trust.isRememberMe(auth));
        assertFalse(trust.isFullyAuthenticated(auth));
    }

    @Test
    void rememberMeIsAuthenticatedButNotFullyAuthenticated() {
        Authentication auth = remembered();

        assertFalse(trust.isAnonymous(auth));
        assertTrue(trust.isAuthenticated(auth));
        assertTrue(trust.isRememberMe(auth));
        assertFalse(trust.isFullyAuthenticated(auth));
    }

    @Test
    void interactiveLoginIsFullyAuthenticated() {
        Authentication auth = fullyLoggedIn();

        assertFalse(trust.isAnonymous(auth));
        assertTrue(trust.isAuthenticated(auth));
        assertFalse(trust.isRememberMe(auth));
        assertTrue(trust.isFullyAuthenticated(auth));
    }

    @Test
    void policyFactoriesDistinguishTheFourStates() {
        Object resource = new Object();
        Authentication guest = anonymous();
        Authentication remembered = remembered();
        Authentication full = fullyLoggedIn();

        var anyAuthenticated =
                AuthenticatedAuthorizationManager.<Object>authenticated();
        var onlyAnonymous =
                AuthenticatedAuthorizationManager.<Object>anonymous();
        var onlyRemembered =
                AuthenticatedAuthorizationManager.<Object>rememberMe();
        var onlyFully =
                AuthenticatedAuthorizationManager.<Object>fullyAuthenticated();

        assertFalse(anyAuthenticated.check(() -> guest, resource).isGranted());
        assertTrue(anyAuthenticated.check(() -> remembered, resource).isGranted());
        assertTrue(anyAuthenticated.check(() -> full, resource).isGranted());

        assertTrue(onlyAnonymous.check(() -> guest, resource).isGranted());
        assertFalse(onlyAnonymous.check(() -> remembered, resource).isGranted());
        assertFalse(onlyAnonymous.check(() -> full, resource).isGranted());

        assertFalse(onlyRemembered.check(() -> guest, resource).isGranted());
        assertTrue(onlyRemembered.check(() -> remembered, resource).isGranted());
        assertFalse(onlyRemembered.check(() -> full, resource).isGranted());

        assertFalse(onlyFully.check(() -> guest, resource).isGranted());
        assertFalse(onlyFully.check(() -> remembered, resource).isGranted());
        assertTrue(onlyFully.check(() -> full, resource).isGranted());
    }
}
~~~

Chạy phép thử trong dự án đã cấu hình JUnit Platform:

~~~bash
./gradlew test --tests '*TrustLevelTest'
~~~

Trên Windows dùng `gradlew.bat test --tests "*TrustLevelTest"`. **Kết quả kỳ vọng:** bốn phương thức thử nghiệm đều đạt. Đây là kỳ vọng theo hợp đồng và các token được tạo trong mã, không phải bản ghi một lần thực thi thực tế.

Mục đích kiểm thử này là chứng minh bảng trạng thái; nó không kiểm tra việc cấp cookie, chạy `RememberMeAuthenticationFilter`, chọn bộ lọc HTTP hay phát mã trạng thái. Cần thêm phép thử tích hợp `MockMvc` hoặc HTTP thực tế để xác nhận các luồng đó. Với Spring Security có API `AuthorizationManager.authorize(...)` được ưu tiên ở phiên bản mới hơn, điều chỉnh lời gọi `check(...)` theo phiên bản đang sử dụng.

## 11. Kiểm thử HTTP: dự đoán quyết định, rồi mới xem mã trạng thái

Để kiểm thử tích hợp cấu hình ở mục 8, tạo controller có các đường dẫn tương ứng. Thực hiện mỗi yêu cầu với **ba trạng thái xác thực** và đối chiếu xem nó được phép đi tiếp qua lớp bảo mật hay không:

| Endpoint | Anonymous | Remember-me | Fully authenticated |
| --- | :---: | :---: | :---: |
| `/` | Cho qua | Cho qua | Cho qua |
| `/guest-only/welcome` | Cho qua | Chặn | Chặn |
| `/remember-only/info` | Chặn | Cho qua | Chặn |
| `/account/profile` | Chặn | Cho qua | Cho qua |
| `/account/payment/confirm` | Chặn | Chặn | Cho qua |
| `/unknown` | Chặn | Chặn | Chặn |

“Cho qua” ở đây nghĩa là **đạt bước ủy quyền**. Nếu không có controller xử lý, yêu cầu vẫn có thể nhận 404. “Chặn” nghĩa là **không đạt bước ủy quyền**, chưa khẳng định sẽ luôn trả 401/403: form login có thể đưa người dùng về màn hình đăng nhập, và phiên remember-me bị từ chối ở nơi cần đăng nhập đầy đủ có thể kích hoạt đăng nhập lại.

Để mô phỏng trạng thái khi kiểm thử, nên:

- Sử dụng cơ chế anonymous của bộ lọc hoặc `@WithAnonymousUser` nếu đang dùng Spring Security Test.
- Dùng `@WithMockUser` để đại diện người dùng đã xác thực trong phép thử quyền; nó **không** tương đương token remember-me.
- Để kiểm thử nhánh remember-me riêng, cung cấp `RememberMeAuthenticationToken` qua bộ hỗ trợ kiểm thử `SecurityMockMvcRequestPostProcessors.authentication(...)` hoặc phát sinh cookie remember-me thật và đi qua chuỗi bộ lọc.
- Khi kiểm tra tính đúng đắn của cookie/chuỗi đăng nhập, phải dùng bài kiểm thử tích hợp thực tế thay vì chỉ tạo token thủ công.

Khi thất bại, ghi rõ trạng thái `Authentication`, tên bộ lọc/chính sách quyết định và đường dẫn được khớp. Một trạng thái HTTP duy nhất thường không đủ để suy ra điều kiện nào đã chặn.

## 12. Kết hợp trạng thái xác thực với vai trò/quyền

Bốn điều kiện trả lời “người dùng đã được nhận diện theo cách nào?”, còn `hasRole` / `hasAuthority` trả lời “người dùng mang quyền gì?”. Hai câu hỏi độc lập:

- Một tài khoản remember-me có `ROLE_ADMIN` vẫn có thể **không đạt** `fullyAuthenticated()`.
- Một tài khoản đã đăng nhập đầy đủ nhưng không có `ROLE_ADMIN` vẫn **không đạt** `hasRole("ADMIN")`.
- `authenticated()` không tự động cấp quyền ADMIN hoặc quyền thao tác trên một đối tượng tài nguyên.

Chính sách thường cần kết hợp điều kiện, chẳng hạn “đã đăng nhập đầy đủ **và** có quyền phê duyệt”. Ở method security:

~~~java
@PreAuthorize("isFullyAuthenticated() and hasAuthority('PAYMENT_APPROVE')")
public void approvePayment(String paymentId) {
    // Logic nghiệp vụ thực hiện sau khi interceptor cho phép.
}
~~~

Đây là **đoạn phương thức minh họa**, cần đặt trong bean Spring có cấu hình method security. Kiểm tra vai trò/quyền ở tầng phương thức quan trọng khi cùng hành động có thể được gọi từ HTTP, sự kiện hoặc các luồng nội bộ khác. Đồng thời, quyền trên từng bản ghi (chủ sở hữu, chi nhánh, số tiền, trạng thái) vẫn phải được đánh giá riêng.

Dù có `fullyAuthenticated()` và `PAYMENT_APPROVE`, nếu nghiệp vụ yêu cầu xác thực lại trong 5 phút hoặc MFA với mức đảm bảo xác định, hãy kiểm tra thông tin thời gian/cấp độ xác thực tương ứng; không coi việc đã đăng nhập đầy đủ là bằng chứng tự động về độ mới hoặc MFA.

## 13. Cần phân biệt Servlet và WebFlux

Bốn điều kiện được đề cập trong bài là khái niệm/phương thức kiểm tra của Spring Security, nhưng **giao diện cấu hình HTTP không hoàn toàn giống nhau giữa Servlet và WebFlux**.

Trong Servlet, `HttpSecurity.authorizeHttpRequests(...)` hỗ trợ trực tiếp `authenticated()`, `anonymous()`, `rememberMe()` và `fullyAuthenticated()` trên bộ dựng quy tắc URL (tùy phiên bản API). Servlet cũng có chuỗi `RememberMeAuthenticationFilter` và các dịch vụ ghi nhớ đăng nhập.

Trong WebFlux, cấu hình phổ biến là `ServerHttpSecurity.authorizeExchange(...)`. API `AuthorizeExchangeSpec.Access` hỗ trợ `authenticated()`, `permitAll()`, `denyAll()` và các quy tắc vai trò/quyền; **không mặc định có cùng bốn phương thức DSL Servlet**. Nếu cần điều kiện phân biệt trạng thái token, có thể sử dụng `.access(ReactiveAuthorizationManager<AuthorizationContext>)` và chỉ đọc danh tính qua Publisher do framework cấp, không dùng `SecurityContextHolder` kiểu `ThreadLocal` để giả định ngữ cảnh request reactive.

Ví dụ minh họa một chính sách WebFlux yêu cầu xác thực đầy đủ, theo hợp đồng `ReactiveAuthorizationManager` trong Spring Security 6.3.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        AuthenticationTrustResolver trust =
                new AuthenticationTrustResolverImpl();

        ReactiveAuthorizationManager<AuthorizationContext> requireFull =
                (authentication, context) -> authentication
                        .map(auth -> new AuthorizationDecision(
                                trust.isFullyAuthenticated(auth)))
                        .defaultIfEmpty(new AuthorizationDecision(false));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/sensitive/**").access(requireFull)
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là **cấu hình thay thế khi ứng dụng dùng WebFlux**, không đặt cùng ứng dụng Servlet phía trên. Nó kiểm tra đối tượng `Authentication` mà Publisher phát ra và chuyển trường hợp không có dữ liệu thành quyết định từ chối. Nó **không tự cài đặt remember-me cho WebFlux**; muốn có remember-me theo nghĩa cookie riêng phải thiết kế và kiểm thử quy trình xác thực tương thích với ứng dụng reactive. Những token custom hoặc bộ phân loại tin cậy tùy chỉnh cũng cần được xem xét để biết `isFullyAuthenticated` có phù hợp chính sách hay không.

## 14. Những nhầm lẫn dẫn đến lỗ hổng phân quyền

1. **Nhầm `anonymous()` với `permitAll()`.** Điều kiện đầu chỉ dành cho ẩn danh, còn điều kiện sau cho mọi trạng thái truy cập.
2. **Nhầm `rememberMe()` với “remember-me hoặc đăng nhập mạnh hơn”.** Điều kiện này nhận diện **đúng** trạng thái remember-me; muốn cả người đăng nhập đầy đủ, hãy chọn `authenticated()`.
3. **Nhầm `authenticated()` với `fullyAuthenticated()`.** Điều kiện authenticated bao gồm remember-me, nên không tự động phù hợp với mọi thao tác nhạy cảm.
4. **Dựa vào `Authentication.isAuthenticated()` mà quên token ẩn danh.** Hãy dùng chính sách của framework hoặc `AuthenticationTrustResolver`.
5. **Dùng `fullyAuthenticated()` như bằng chứng đã hoàn thành MFA.** Điều kiện này không đảm bảo phương thức xác thực, độ mới, thiết bị hay mức rủi ro.
6. **Đặt quy tắc URL rộng trước quy tắc nhạy cảm.** `/account/**` bắt trước `/account/payment/**` khiến chính sách riêng không được xét.
7. **Cho rằng có cookie là remember-me.** Cookie phiên HTTP và cookie remember-me là hai loại khác nhau; kiểm tra token xác thực thực tế.
8. **Tự gắn cứng mọi từ chối thành 403.** Chưa đăng nhập/remember-me cần đăng nhập lại có thể kích hoạt `AuthenticationEntryPoint`.
9. **Không bật hoặc không cấu hình đúng remember-me mà vẫn viết quy tắc `rememberMe()`.** Khi không có đường tạo `RememberMeAuthenticationToken`, việc kiểm thử nhánh này không có ý nghĩa thực tế.
10. **Copy DSL Servlet sang WebFlux.** Các phương thức API có thể khác nhau; xác nhận phiên bản và giao diện thực tế trước khi dùng.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng được khôi phục từ cookie remember-me muốn xem `/account/profile` được bảo vệ bằng `authenticated()`. Có đạt điều kiện không?

**Đáp án:** Có, nếu remember-me được xác thực hợp lệ; `authenticated` chấp nhận remember-me.

**Câu 2.** Người dùng đã đăng nhập trực tiếp truy cập `/remember-only/info` có điều kiện `rememberMe()`. Có đạt điều kiện không?

**Đáp án:** Không theo cách phân loại mặc định; `rememberMe()` kiểm tra trạng thái remember-me, không có nghĩa “ít nhất đã được ghi nhớ”. Muốn cho cả hai trạng thái, dùng `authenticated()`.

**Câu 3.** `AnonymousAuthenticationToken.isAuthenticated()` trả true. Điều đó có chứng minh khách đã đăng nhập không?

**Đáp án:** Không. `AuthenticationTrustResolver.isAnonymous(...)` vẫn nhận diện đây là khách ẩn danh và `isAuthenticated(...)` không xem token ấy là đăng nhập người dùng.

**Câu 4.** Có thể dùng `fullyAuthenticated()` để bảo đảm thao tác chỉ được thực hiện trong vòng 5 phút sau khi nhập lại mật khẩu không?

**Đáp án:** Không. Cần cơ chế xác thực lại và kiểm tra dấu thời gian hoặc bằng chứng xác thực bổ sung.

**Câu 5.** `permitAll()` và `anonymous()` có cho cùng kết quả với người dùng đã đăng nhập không?

**Đáp án:** Không. `permitAll()` cho phép; `anonymous()` không khớp.

**Câu 6.** Một tài khoản remember-me có vai trò ADMIN có tự động đi qua `fullyAuthenticated()` không?

**Đáp án:** Không. Vai trò ADMIN và mức tin cậy xác thực là hai điều kiện khác nhau. Chính sách có thể yêu cầu cả hai.

## Tài liệu đối chiếu

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthenticatedAuthorizationManager` và mức tin cậy.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): quy tắc URL, thứ tự matcher, `permitAll` và xử lý quyền.
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html): vai trò của `AnonymousAuthenticationToken`.
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html): token/cookie và `RememberMeServices`.
- [AuthenticationTrustResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html): `isAuthenticated`, `isAnonymous`, `isRememberMe` và `isFullyAuthenticated`.
- [AuthenticatedAuthorizationManager API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/AuthenticatedAuthorizationManager.html): các bộ quản lý `authenticated`, `anonymous`, `rememberMe`, `fullyAuthenticated`.
- [ServerHttpSecurity.AuthorizeExchangeSpec.Access API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html): các điều kiện trực tiếp của DSL WebFlux.
