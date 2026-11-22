# Những yếu tố đã hoàn tất và trạng thái chưa đạt mức xác thực yêu cầu (MFA trong Spring Security)

## 1. Mục tiêu và câu hỏi cốt lõi

Một người dùng nhập đúng mật khẩu và đã đăng nhập ứng dụng. Liệu có được phép mở trang thay đổi tài khoản ngân hàng, tạo API key quản trị, đổi email khôi phục hoặc xuất dữ liệu nhạy cảm ngay không? **Không nhất thiết.** Ứng dụng có thể yêu cầu thêm yếu tố xác thực thứ hai, hoặc yêu cầu một yếu tố đã hoàn tất phải đủ mới (fresh) trong vòng vài phút.

Đây là điểm quan trọng của xác thực nhiều yếu tố (Multi-Factor Authentication, **MFA**): trạng thái **“đã xác thực”** và trạng thái **“đã đạt mức xác thực mà tài nguyên yêu cầu”** không phải lúc nào cũng giống nhau.

Ví dụ: người dùng có mật khẩu hợp lệ nhưng chưa xác minh one-time token (OTT). Đăng nhập cơ bản đã thành công, song endpoint yêu cầu hai yếu tố vẫn **chưa được phép**. Ứng dụng nên đưa người dùng đến bước bổ sung còn thiếu (step-up) mà không bắt họ khởi tạo lại mọi thứ không cần thiết.

Sau bài học, bạn có thể:

1. Phân biệt `Authentication.isAuthenticated()`, `ROLE_*`, `FactorGrantedAuthority` và điều kiện MFA của từng endpoint.
2. Xác định danh sách **yếu tố đã hoàn tất**, **yếu tố còn thiếu** và **yếu tố đã hết thời gian hợp lệ**.
3. Diễn giải trạng thái từng phần trong luồng password → OTT/WebAuthn, điều gì được giữ trong `SecurityContext` và tại sao không tự cấp quyền đầy đủ sau bước đầu.
4. Dùng chức năng MFA chính thức của **Spring Security 7.x**: `@EnableMultiFactorAuthentication`, `FactorGrantedAuthority`, `AuthorizationManagerFactories.multiFactor()`.
5. Tạo chính sách bắt buộc MFA toàn hệ thống hoặc chỉ cho các trang quan trọng; quy định **validDuration**, điều kiện theo user và tổ hợp phương thức thay thế.
6. Biết giới hạn tương thích với Spring Security 6.x, WebFlux và những rủi ro của session, reauthentication, recovery.
7. Viết và kiểm thử mô hình minh họa bằng Java 17+, sau đó gắn với luồng Spring Security Servlet thực tế.

**Trọng tâm:** không phải hướng dẫn mọi loại OTP/passkey từ đầu, mà là **cách theo dõi bằng chứng đã có và xử lý khi bằng chứng đó chưa thỏa chính sách truy cập**.

## 2. “Đăng nhập thành công” khác “đủ mức để vào tài nguyên”

Trong Spring Security, `Authentication` mô tả principal, authorities và kết quả của một cơ chế xác thực. Với một lần đăng nhập password thành công, `isAuthenticated()` có thể là `true`. Điều đó chứng minh **password authentication đã được chấp nhận**, không tự chứng minh user đã hoàn tất các yếu tố bổ sung.

Một số vai trò:

| Trạng thái/thành phần | Trả lời câu hỏi | Có thay thế cho MFA không? |
| --- | --- | --- |
| `Authentication.isAuthenticated()` | Có một Authentication đã thành công chưa? | **Không**. Không biết endpoint yêu cầu những yếu tố nào |
| `ROLE_ADMIN` | Ứng dụng đã cấp vai trò admin cho principal chưa? | **Không**. Role là quyền nghiệp vụ, không phải bằng chứng login |
| `FACTOR_PASSWORD` | User đã được xác thực bằng password theo cơ chế có hỗ trợ chưa? | **Một bằng chứng**, chưa phải toàn bộ chính sách |
| `FACTOR_OTT` | User đã hoàn tất xác thực bằng one-time token chưa? | **Một bằng chứng** khác; nguồn phát token quyết định độ tin cậy thực tế |
| `FactorGrantedAuthority.getIssuedAt()` | Yếu tố được xác thực vào thời điểm nào? | Dùng kiểm tra tính mới; không tự chỉ rõ hạn hợp lệ |
| `AuthorizationManager` / MFA policy | Tài nguyên yêu cầu vai trò, những factor nào và trong bao lâu? | Đây là nơi quyết định đủ/chưa đủ cho **tài nguyên cụ thể** |
| `SecurityContext` và session | Bằng chứng/Authentication được duy trì ở request sau bằng cách nào? | Không được làm vượt quyền hoặc kéo dài hiệu lực yếu tố quá chính sách |

**Cần phân biệt thêm:** user đã đăng ký passkey hoặc đã bật MFA trong hồ sơ **không** có nghĩa vừa hoàn tất đăng nhập bằng passkey hoặc yếu tố thứ hai. *Registration/enrollment state* và *authentication-completed state* là hai dữ liệu khác nhau.

Một mô hình dễ hình dung:

```text
Identity:             learner
Application roles:    [ROLE_USER, ROLE_ADMIN]

Completed factors (evidence):
    FACTOR_PASSWORD  issuedAt = 11:45
    FACTOR_OTT       chưa có

Endpoint /profile:
    yêu cầu authenticated                   -> ĐỦ

Endpoint /admin/export:
    yêu cầu ROLE_ADMIN + FACTOR_PASSWORD
    (trong 10 phút) + FACTOR_OTT (trong 5 phút)
                                             -> CHƯA ĐỦ
    thiếu OTT; password cũng đã quá cũ
```

Đối với endpoint nhạy cảm, **authorization phải fail-closed** nếu một factor bắt buộc chưa có, quá cũ hoặc thuộc một phiên/người dùng khác.

## 3. Spring Security 7 ghi nhận yếu tố đã hoàn tất như thế nào?

Từ **Spring Security 7.0**, framework có mô hình MFA tích hợp với `FactorGrantedAuthority`. Đây là một dạng `GrantedAuthority` có thêm thông tin thời gian `issuedAt`, thay vì chỉ là tên quyền dạng chuỗi.

Những constant được tài liệu Spring sử dụng:

| Constant | Authority string | Cơ chế tương ứng |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Xác thực bằng password |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token Login của Spring |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn/passkey |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Cơ chế bearer token, không tự đồng nghĩa MFA |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code login |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 client certificate authentication |

Danh sách là ví dụ các factor Spring hỗ trợ; tùy bản phát hành có thêm constant hoặc tích hợp khác. **Không nhầm `FACTOR_*` với `ROLE_*` hay `SCOPE_*`:** factor ghi nhận *cách chứng minh danh tính*, còn role/scope thường liên quan *quyền sử dụng tài nguyên*.

### 3.1. Dấu thời gian của factor

Tài liệu API có thể tạo một `FactorGrantedAuthority` như sau:

```java
// Trích đoạn cho Spring Security 7.x:
FactorGrantedAuthority proof = FactorGrantedAuthority
    .withAuthority(FactorGrantedAuthority.PASSWORD_AUTHORITY)
    .issuedAt(Instant.now())
    .build();

String authority = proof.getAuthority();
Instant completedAt = proof.getIssuedAt();
```

Hai import là `java.time.Instant` và `org.springframework.security.core.authority.FactorGrantedAuthority`. Code này chỉ minh họa kiểu dữ liệu; **không được tạo factor “đã hoàn tất” từ request header hoặc user input** trước khi một cơ chế xác thực tương ứng thực sự thành công.

`issuedAt` ghi thời điểm bằng chứng được cấp. Chính bản thân authority **không khai báo “có hiệu lực 30 phút”**: cùng một lần xác thực password có thể đủ mới với trang hồ sơ (30 phút) nhưng không đủ mới với trang chuyển tiền (5 phút). Hạn được áp dụng **ở authorization policy** của từng tài nguyên.

### 3.2. Không thể tự đánh dấu hoàn tất

Đoạn code sau là **lỗi bảo mật**:

```java
// SAI: chỉ thấy header X-MFA-Done rồi tự cấp factor authority.
String done = request.getHeader("X-MFA-Done");
if ("true".equals(done)) {
    authorities.add(
        FactorGrantedAuthority.fromAuthority("FACTOR_OTT"));
}
```

Header từ client không phải bằng chứng người dùng đã kiểm tra OTT. Chỉ authentication mechanism đáng tin cậy (hoặc adapter đã xác minh bằng chứng từ IdP, theo hợp đồng chặt chẽ) mới được thêm factor.

**Kỹ thuật đúng:** password filter/provider xác minh password; one-time token filter/provider xác minh token tiêu thụ một lần; WebAuthn server xác minh challenge, origin và chữ ký. Sau khi mỗi cơ chế thành công, framework có cơ sở cập nhật các factors đã đạt.

## 4. Sơ đồ chuyển trạng thái “chưa đủ mức xác thực”

Lấy chính sách một ứng dụng: xem `/profile` cần một authentication hợp lệ; vào `/settings/security` cần password **và** OTT; vào `/admin/export` còn cần `ROLE_ADMIN`.

```text
                              [ANONYMOUS]
                                  |
                           nhập username/password
                                  |
                           xác minh mật khẩu
                                  v
             [AUTHENTICATED: FACTOR_PASSWORD]
                 |                    |
                 | GET /profile       | GET /settings/security
                 v                    v
           ĐƯỢC PHÉP             CHƯA ĐỦ MFA
                                      |
                         thiếu FACTOR_OTT
                                      |
                       challenge / step-up redirect
                                      |
                          user lấy OTT hợp lệ
                                      |
                              xác minh OTT
                                      v
          [AUTHENTICATED: FACTOR_PASSWORD + FACTOR_OTT]
                                      |
                     kiểm tra quyền, freshness, session
                                      |
                         GET /settings/security
                                      v
                                  ĐƯỢC PHÉP
```

**Một phần không đồng nghĩa anonymous.** Sau password, tài khoản đã được nhận diện; người dùng có thể được phép làm những việc có rủi ro thấp. Khi truy cập trang nhạy cảm mới bị yêu cầu thêm bằng chứng.

**Không nhất thiết luôn theo thứ tự password trước OTT.** Spring Security 7 có thể biết yếu tố nào còn thiếu và hướng user tới cơ chế phù hợp; tài liệu mô tả trường hợp user hoàn tất OTT trước thì được hướng quay lại password. Chính sách sản phẩm có thể yêu cầu thứ tự hoặc ràng buộc khác, nhưng không được gán “đã hoàn tất” cho bước chưa diễn ra.

### 4.1. Ma trận chính sách

Giả sử tất cả factor đều còn trong thời gian hợp lệ:

| Bằng chứng hiện có | `/profile` cần authenticated | `/settings` cần password + OTT | `/admin` cần password + OTT + ROLE_ADMIN |
| --- | --- | --- | --- |
| Không có | Từ chối hoặc chuyển sang login | Từ chối hoặc login | Từ chối hoặc login |
| Chỉ password | Cho phép | Thiếu OTT → step-up | Thiếu OTT, và có thể thiếu role |
| Chỉ OTT | Có thể đã authenticated trong luồng phù hợp | Thiếu password → step-up | Thiếu password, và có thể thiếu role |
| Password + OTT | Cho phép | Cho phép | Chỉ khi có ROLE_ADMIN |
| Password + OTT nhưng OTT hết hạn theo policy | Cho phép nếu không có ràng buộc bổ sung | Yêu cầu xác thực OTT mới | Yêu cầu OTT mới, và vẫn cần role |
| Có ROLE_ADMIN nhưng chỉ password | Cho phép | Thiếu OTT | **Không được bypass MFA chỉ vì có role admin** |

Đây là kết quả **logic của chính sách mẫu**. Phản hồi HTTP cuối có thể là chuyển hướng `302` tới cơ chế còn thiếu, `401` hay `403` tùy loại client và `AuthenticationEntryPoint`/AccessDeniedHandler được cấu hình. Đừng khẳng định mọi trạng thái “thiếu factor” đều phải trả 401.

### 4.2. Phân biệt bốn kiểu trạng thái chưa đủ

1. **Chưa có bất kỳ authentication nào:** request anonymous, cần một phương thức login.
2. **Có authentication nhưng thiếu yếu tố bắt buộc:** ví dụ password xong, OTT chưa xong.
3. **Đã có đủ loại yếu tố nhưng bằng chứng quá cũ:** yêu cầu reauthentication/step-up theo `validDuration`.
4. **Có đủ factor nhưng thiếu quyền nghiệp vụ:** ví dụ không có `ROLE_ADMIN`. Bổ sung OTT **không** tự giải quyết lỗi thiếu role.

UI/monitoring có thể trình bày rõ các trạng thái này cho người dùng/hỗ trợ, nhưng thông tin nội bộ cần được che khi người gọi chưa xác thực để tránh tiết lộ account existence hoặc chính sách quá chi tiết.

## 5. Tại sao “mức xác thực” là yêu cầu theo tài nguyên?

Không nên gán cứng mọi request cùng một mức xác thực. Một sản phẩm có thể quy định:

- Xem trang hồ sơ thông thường: user đã authenticated.
- Đổi địa chỉ giao hàng: có password hoặc passkey còn mới.
- Xem khóa API, đổi email bảo mật: password + yếu tố độc lập.
- Thực hiện thao tác tài chính lớn: yếu tố mạnh, giới hạn thời gian và có thể phải ràng buộc với giao dịch cụ thể.
- Admin thao tác trên người dùng khác: MFA + `ROLE_ADMIN` + kiểm tra tenant/object ownership.

Đây là **step-up authentication**: chỉ yêu cầu thêm bằng chứng khi mức rủi ro của hành động cần. Không nên dùng mức “MFA enabled” trong user profile thay cho việc đánh giá factor được cấp gần đây.

Một policy có thể biểu diễn bằng các phần:

```text
RequiredAuthenticationLevel(resource, subject, action, risk):
    identity must be authenticated
    required business roles/scopes must match
    required factor combinations must be satisfied
    each required factor must be fresh enough
    application/tenant/device/risk constraints must pass
```

Spring Security 7 cung cấp phần tổ chức authorization factor rất hữu ích; chính sách kinh doanh như hạn tiền chuyển hoặc yêu cầu ký giao dịch **vẫn phải được viết ở tầng nghiệp vụ**.

## 6. Phiên bản và dependency: Spring Security 7 so với 6.5

Đây là điểm quan trọng khi học hoặc thực hành vì API có khác biệt lớn:

| Hệ | Tình trạng MFA tích hợp | Cách triển khai |
| --- | --- | --- |
| **Spring Security 6.5 / Spring Boot 3.5** | Có password, OTT, WebAuthn riêng lẻ; **chưa có cùng mô hình MFA factor-aware và annotation `@EnableMultiFactorAuthentication` của 7.x** | Tự viết state machine/policy hoặc nâng cấp; không copy import 7.x vào app 6.5 |
| **Spring Security 7.0–7.1 / Spring Boot 4.x** | Có `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và `AuthorizationManagerFactories.multiFactor()` cho Servlet | Dùng MFA APIs chính thức với Web Security/AuthorizationManager |
| **Reactive WebFlux** | Ở tài liệu Spring Security 7.0/7.1, annotation MFA mới **chưa áp dụng tương đương cho reactive stack** | Không nhét `SecurityFilterChain` Servlet vào `SecurityWebFilterChain`; cần kiểm tra bản reactive hiện có và policy riêng |

Spring Security 7.0 được giới thiệu MFA như một tính năng mới (blog Spring ngày **21/10/2025**), vì vậy nếu IDE báo không có `FactorGrantedAuthority` hoặc `@EnableMultiFactorAuthentication`, cần xem **major version thực tế** trước khi thay import.

**Java:** Spring Boot 4 vẫn có Java 17 baseline dù hỗ trợ JDK mới. Ví dụ sử dụng Java 17 với Spring Boot `4.0.9` (bản được phát hành tháng 10/2026), Spring Framework 7 và Spring Security 7.x theo BOM của Boot. Trong hệ thống mới, ưu tiên nhánh vá lỗi hiện hành của tổ chức.

Ví dụ Maven dependencies trên Boot 4:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
</dependencies>
```

Trong Boot 4.x, `spring-boot-starter-webmvc` là starter rõ ràng cho Servlet MVC; không sử dụng ví dụ cũ và giả định tất cả dependency/module/test package giống Boot 3.x. **Không cần thêm một “MFA starter” riêng** để có `FactorGrantedAuthority` nếu Spring Security 7 config/web/core đã được starter/BOM tương ứng mang vào. OTT cần hệ thống **phân phối token đáng tin cậy** (email, SMS hay kênh khác), mà Spring Security **không thể tự cung cấp** thay ứng dụng.

Kiểm tra thực tế:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework.boot
mvn -v
```

Không trộn artifact Spring Security 7 vào Boot 3.x hoặc tự pin phiên bản Spring Framework ngoài BOM mà không có lý do kỹ thuật.

## 7. Cấu hình MFA trong Spring Security 7: ba cách

### 7.1. Bắt buộc password + OTT cho toàn bộ authorization rules

Theo tài liệu Spring Security 7, cách ngắn nhất là:

```java
// Trích đoạn @Configuration trong ứng dụng Spring Security 7.x
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
class GlobalMfaConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
```

Các import tương ứng: `org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication` và `org.springframework.security.core.authority.FactorGrantedAuthority`. Đây là **trích đoạn Spring config**; cần khai báo app, user store và OTT delivery như phần 9 mới có ứng dụng vận hành.

Ý nghĩa:

- `/admin/**` cần `ROLE_ADMIN + FACTOR_PASSWORD + FACTOR_OTT`.
- Các đường dùng `authenticated()` cũng cần hai factors theo factory toàn cục.
- `permitAll()` và những cơ chế đặc biệt không tự biến thành login mới; cơ chế MFA xử lý theo authorization rule mà factory áp dụng.
- Nếu có nhiều SecurityFilterChain và method security, phải kiểm tra phạm vi factory/annotation và test chính xác đường nào được bảo vệ.

### 7.2. Chỉ yêu cầu MFA ở endpoint nhạy cảm (selective MFA)

Không phải app nào cũng nên yêu cầu hai yếu tố ở mọi trang. Spring Security hỗ trợ giữ các route thường ở mức `authenticated()`, còn route nhạy cảm dùng factory riêng.

```java
// Trích đoạn cấu hình Spring Security 7.x:
@EnableMultiFactorAuthentication(authorities = {})
class SelectiveMfaConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        var mfa = AuthorizationManagerFactories.multiFactor()
            .requireFactors(
                FactorGrantedAuthority.PASSWORD_AUTHORITY,
                FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**")
                    .access(mfa.hasRole("ADMIN"))
                .requestMatchers("/settings/security/**")
                    .access(mfa.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
    }
}
```

Chú ý `@EnableMultiFactorAuthentication(authorities = {})` **bật hỗ trợ MFA mà không tạo yêu cầu factor toàn cục**. `mfa` chỉ là local variable, không publish thành `AuthorizationManagerFactory` Bean. Nếu publish nó thành Bean, các authorization rules khác có thể bị áp dụng MFA rộng hơn dự kiến.

Ý nghĩa: `/profile` chỉ cần login; `/settings/security/**` cần password+OTT; `/admin/**` cần password+OTT+role. Đây là mô hình gần nhất với trạng thái “đã có một số yếu tố nhưng chưa đạt mức cần thiết ở màn hình cụ thể”.

### 7.3. Yêu cầu factor tùy user hoặc thời gian

Khi sản phẩm dùng MFA opt-in hoặc có user đặc quyền, không nên viết từng filter thủ công. Spring Security cung cấp `AuthorizationManagerFactories.multiFactor().when(...)` và `RequiredAuthoritiesRepository` để xác định yêu cầu tùy user hoặc account settings.

Ví dụ cấu hình **minh họa**:

```java
// Một Bean factory tác động toàn cục khi có trong context:
@Bean
AuthorizationManagerFactory<Object> policy() {
    return AuthorizationManagerFactories.multiFactor()
        .requireFactors(
            FactorGrantedAuthority.PASSWORD_AUTHORITY,
            FactorGrantedAuthority.OTT_AUTHORITY)
        .when(auth -> "admin".equals(auth.getName()))
        .build();
}
```

Nếu điều kiện dựa trên tên đăng nhập, cần xem xét user rename, impersonation và multi-tenant; thông thường lookup bằng stable user ID/account security policy đáng tin cậy tốt hơn hard-code `"admin"`.

**Thời gian hợp lệ:** Spring Security hỗ trợ:

```java
// Chỉ trích đoạn: password cần còn mới trong 10 phút
var freshPassword = AuthorizationManagerFactories.multiFactor()
    .requireFactor(factor -> factor
        .passwordAuthority()
        .validDuration(Duration.ofMinutes(10)))
    .build();
```

Các policy khác nhau có thể đặt `validDuration` khác nhau cho cùng `FACTOR_PASSWORD`. Không thay đổi timestamp trong `FactorGrantedAuthority` để “làm mới” factor; phải yêu cầu **xác thực thật** lần nữa.

## 8. Java 17 độc lập: nhìn thấy rõ yếu tố thiếu và yếu tố hết hạn

Trước khi tích hợp Spring, có thể mô phỏng “danh sách yếu tố đã hoàn tất” và “yêu cầu của endpoint” bằng Java 17 thuần. Chương trình dưới **chạy được không cần Maven** và cho output xác định. Nó **không phải implementation thay thế của Spring MFA**; mục tiêu là giúp hiểu logic và kiểm tra các ca biên.

Tạo file `MfaFactorStateDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class MfaFactorStateDemo {

    record Proof(String authority, Instant issuedAt) {}

    record Required(String authority, Duration validFor) {}

    static List<String> missingOrExpired(
            List<Required> required,
            List<Proof> completed,
            Instant now) {

        List<String> problems = new ArrayList<>();

        for (Required requirement : required) {
            Optional<Proof> latest = completed.stream()
                .filter(p -> p.authority().equals(
                    requirement.authority()))
                .max(Comparator.comparing(Proof::issuedAt));

            if (latest.isEmpty()) {
                problems.add(requirement.authority() + ":MISSING");
            } else {
                Instant issued = latest.get().issuedAt();
                Instant deadline = issued.plus(
                    requirement.validFor());
                if (issued.isAfter(now) || !now.isBefore(deadline)) {
                    problems.add(requirement.authority() + ":EXPIRED");
                }
            }
        }
        return problems;
    }

    static String state(List<String> problems) {
        return problems.isEmpty()
            ? "GRANTED"
            : "DENIED " + problems;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");

        List<Proof> completed = new ArrayList<>();
        completed.add(new Proof(
            "FACTOR_PASSWORD",
            Instant.parse("2026-01-01T11:45:00Z")));

        List<Required> profile = List.of(
            new Required("FACTOR_PASSWORD",
                         Duration.ofMinutes(30)));

        List<Required> admin = List.of(
            new Required("FACTOR_PASSWORD",
                         Duration.ofMinutes(10)),
            new Required("FACTOR_OTT",
                         Duration.ofMinutes(5)));

        System.out.println("profile: " + state(
            missingOrExpired(profile, completed, now)));

        System.out.println("admin before OTT: " + state(
            missingOrExpired(admin, completed, now)));

        completed.add(new Proof("FACTOR_OTT", now));

        System.out.println("admin after OTT: " + state(
            missingOrExpired(admin, completed, now)));

        completed.add(new Proof("FACTOR_PASSWORD", now));

        System.out.println("admin after refresh: " + state(
            missingOrExpired(admin, completed, now)));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 MfaFactorStateDemo.java
java MfaFactorStateDemo
```

**Stdout chính xác:**

```text
profile: GRANTED
admin before OTT: DENIED [FACTOR_PASSWORD:EXPIRED, FACTOR_OTT:MISSING]
admin after OTT: DENIED [FACTOR_PASSWORD:EXPIRED]
admin after refresh: GRANTED
```

Giải thích:

- Password 15 phút trước: đủ mới cho `/profile` (giới hạn 30 phút) nhưng quá cũ cho `/admin` (giới hạn 10 phút).
- User hoàn tất OTT: `FACTOR_OTT` mới được chứng minh, nhưng password chưa được “tự làm mới”.
- Chỉ khi password được xác thực lại thật sự, cả hai factor đều đủ mới và yêu cầu của `/admin` mới được đáp ứng.
- Trong sản phẩm thật, check này còn phải kết hợp roles, account status và tài nguyên; ví dụ chỉ tập trung thời gian của factors.
- Tại ranh giới thời gian đúng `issuedAt + validDuration`, chương trình coi yếu tố đã hết hạn để **fail-closed**.

Không sao chép hàm `missingOrExpired` vào project rồi tự tạo `Proof` từ input client. Spring Security có sẵn `FactorGrantedAuthority` và authorization manager để xử lý bằng chứng do xác thực tin cậy tạo ra.

## 9. Ứng dụng Spring Boot 4 / Java 17: trải nghiệm password rồi OTT

Đây là ví dụ Spring Boot **4.0.9** / Spring Security **7.x** cho Servlet MVC, thể hiện một tài khoản vừa có role vừa có tình trạng yếu tố chưa đủ. Nó dùng **selective MFA** để thấy `/profile` vào được sau password, còn `/settings/security` yêu cầu password+OTT.

Vì OTT phải được **gửi tới chủ tài khoản**, ví dụ cấu hình SMTP an toàn qua biến môi trường và một địa chỉ email được server gắn cố định với user `learner`. Nếu không có SMTP test, ứng dụng có thể khởi động và login password, nhưng **không thể hoàn thành OTT delivery**. Đây là điều kiện hạ tầng thật, không nên “demo” bằng cách trả token vào public HTTP response.

### 9.1. Cấu trúc dự án

```text
mfa-factor-state/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/mfa/MfaApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/mfa/MfaApplicationTests.java
```

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mfa-factor-state</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-mail</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

Các module MVC/testing được đặt theo cách đóng gói của Boot 4; không dùng đường import `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` từ Boot 3 trong bài test Boot 4.

### 9.3. `application.yml`

```yaml
server:
  port: 8080

spring:
  mail:
    host: "${SMTP_HOST}"
    port: "${SMTP_PORT:587}"
    username: "${SMTP_USERNAME}"
    password: "${SMTP_PASSWORD}"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  demo:
    password: "${DEMO_PASSWORD}"
    recipient-email: "${DEMO_RECIPIENT_EMAIL}"
    sender-email: "${DEMO_SENDER_EMAIL}"
    public-base-url: "${PUBLIC_BASE_URL:http://localhost:8080}"
```

Dịch vụ cần SMTP có khả năng gửi thư đến user sở hữu account. Biến môi trường phải được cấu hình trong secret manager hoặc môi trường dev có SMTP sink; không đưa password/mail credentials vào Git.

### 9.4. `MfaApplication.java`

```java
package demo.mfa;

import java.security.Principal;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {})
@RestController
public class MfaApplication {

    public static void main(String[] args) {
        SpringApplication.run(MfaApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.password}") String password) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler delivery)
            throws Exception {

        var highAssurance = AuthorizationManagerFactories.multiFactor()
            .requireFactors(
                FactorGrantedAuthority.PASSWORD_AUTHORITY,
                FactorGrantedAuthority.OTT_AUTHORITY)
            .build();

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/ott/sent").permitAll()
                .requestMatchers("/admin/**")
                    .access(highAssurance.hasRole("ADMIN"))
                .requestMatchers("/settings/**")
                    .access(highAssurance.authenticated())
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott ->
                ott.tokenGenerationSuccessHandler(delivery))
            .build();
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler delivery(
            JavaMailSender sender,
            @Value("${app.demo.recipient-email}") String receiver,
            @Value("${app.demo.sender-email}") String from,
            @Value("${app.demo.public-base-url}") String publicBaseUrl) {

        var redirect =
            new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

        return (request, response, token) -> {
            // Demo có duy nhất một local user; receiver không lấy từ
            // request parameter do người lạ có thể chỉnh sửa.
            if ("learner".equals(token.getUsername())) {
                String link = UriComponentsBuilder
                    .fromUriString(publicBaseUrl)
                    .path("/login/ott")
                    .queryParam("token", token.getTokenValue())
                    .toUriString();

                SimpleMailMessage mail = new SimpleMailMessage();
                mail.setFrom(from);
                mail.setTo(receiver);
                mail.setSubject("Your one-time sign-in link");
                mail.setText("Use this link to finish authentication:\n"
                    + link);
                sender.send(mail);
            }
            redirect.handle(request, response, token);
        };
    }

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of(
            "login", "/login",
            "profile", "/profile",
            "mfaProtected", "/settings/security");
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/ott/sent")
    String sentPage() {
        return "If eligible, a sign-in link has been sent.";
    }

    @GetMapping("/profile")
    String profile(Principal principal) {
        return "profile:" + principal.getName();
    }

    @GetMapping("/settings/security")
    String securitySettings(Principal principal) {
        return "security:" + principal.getName();
    }

    @GetMapping("/admin/export")
    String admin(Principal principal) {
        return "admin:" + principal.getName();
    }
}
```

**Đọc cấu hình:**

- `@EnableMultiFactorAuthentication(authorities = {})` bật support MFA nhưng không ép factor lên mọi rule.
- `highAssurance.authenticated()` yêu cầu user đã authenticated **và** `FACTOR_PASSWORD` + `FACTOR_OTT` ở `/settings/**`.
- `highAssurance.hasRole("ADMIN")` yêu cầu thêm `ROLE_ADMIN` ở `/admin/**`.
- `/profile` chỉ dùng `authenticated()` nên sau bước password có thể truy cập, dù chưa có OTT.
- `formLogin()` và `oneTimeTokenLogin()` đều được cấu hình, để Spring có cơ chế bổ sung yếu tố còn thiếu.
- Spring Security tạo/kiểm tra one-time token và điều phối login; bean `delivery` chỉ làm nhiệm vụ **gửi token** đến kênh đã gắn với account.
- Link chứa token dùng một lần ở query để hỗ trợ trang login OTT mặc định, theo mẫu tài liệu Spring. Tránh log query string, đặt chính sách `Referrer-Policy: no-referrer` và kiểm soát URL/caching/tracing. Không lấy `publicBaseUrl` từ header tùy ý của client.

**Giới hạn production:** in-memory user store và default in-memory OTT service chỉ dùng cho demo. Với sản phẩm thật cần account repository, `JdbcOneTimeTokenService` hoặc store nhất quán nhiều node, TLS, SMTP bảo mật, rate limit và email verified/recovery policy. **Không chuyển mã này thành production chỉ bằng thay địa chỉ SMTP.**

### 9.5. Chạy và quan sát hai mức truy cập

Trên host có Java 17+, Maven và SMTP test/relay:

```bash
export DEMO_PASSWORD='a-strong-local-test-password'
export DEMO_RECIPIENT_EMAIL='learner@example.test'
export DEMO_SENDER_EMAIL='no-reply@example.test'
export SMTP_HOST='smtp.example.test'
export SMTP_PORT='587'
export SMTP_USERNAME='smtp-user'
export SMTP_PASSWORD='smtp-credential'
export PUBLIC_BASE_URL='http://localhost:8080'

mvn spring-boot:run
```

Các địa chỉ `example.test` là **giá trị minh họa**, không phải máy chủ SMTP thật; phải dùng SMTP/địa chỉ do bạn kiểm soát. Chỉ chạy HTTP loopback khi phát triển; triển khai thật phải dùng HTTPS và giá trị `PUBLIC_BASE_URL` chính xác.

Trong browser:

1. Mở `http://localhost:8080/profile`, được chuyển tới `/login`.
2. Đăng nhập bằng `learner` và password test đã đặt: `/profile` trả `profile:learner`.
3. Mở `/settings/security`: do mới có password, Spring Security đưa user qua luồng **OTT step-up** hoặc trang tương ứng thay vì cho phép thao tác ngay.
4. Từ trang OTT, gửi yêu cầu cấp one-time token cho user `learner`. Spring cần CSRF token cho POST tạo token.
5. Kiểm tra thư được gửi đến mailbox gắn với account, truy cập link đúng phiên/browser theo yêu cầu luồng đăng nhập và hoàn tất OTT.
6. Quay lại `/settings/security`: nếu cả hai factors hợp lệ, nhận `security:learner`.
7. Vào `/admin/export`: với role ADMIN và đủ factors, nhận `admin:learner`. Một user thường đã có factors nhưng không có `ROLE_ADMIN` vẫn bị từ chối.

**Không cài endpoint “/debug/get-ott” công khai.** Nó sẽ biến factor thứ hai thành một bí mật mà bất kỳ người gọi nào cũng có thể lấy, khiến MFA trở nên vô nghĩa.

OTT trong Spring là **One-Time Token Login** (thường gửi magic link), khác TOTP/HOTP 6 chữ số do authenticator app tạo. Nếu doanh nghiệp dùng TOTP, đó là integration khác, không tự nhận `FACTOR_OTT` chỉ vì một text field có sáu chữ số.

## 10. Kiểm thử tình trạng thiếu/đủ yếu tố trong Spring

Không thể chỉ dùng `@WithMockUser(roles = "ADMIN")` để chứng minh MFA hoàn tất. Nó tạo mock principal/authorities phục vụ test authorization cơ bản, **không làm bước password/OTT thực tế**.

Trong Spring Security 7, `AllRequiredFactorsAuthorizationManager` kiểm tra bằng chứng `FactorGrantedAuthority` và thời gian, không chỉ một chuỗi `"FACTOR_OTT"` tùy tiện. Muốn unit test authorization rules, có thể tạo một Authentication mock **được đánh dấu rõ là dữ liệu test** với factory factor:

```java
package demo.mfa;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.demo.password=test-password",
    "app.demo.recipient-email=learner@example.test",
    "app.demo.sender-email=sender@example.test",
    "app.demo.public-base-url=http://localhost:8080",
    "spring.mail.host=localhost",
    "spring.mail.port=1025"
})
@AutoConfigureMockMvc
class MfaApplicationTests {

    @Autowired
    MockMvc mvc;

    private static Authentication evidence(boolean withOtt) {
        List<GrantedAuthority> authorities = new ArrayList<>();
        authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
        authorities.add(
            FactorGrantedAuthority.withAuthority(
                FactorGrantedAuthority.PASSWORD_AUTHORITY)
                .issuedAt(Instant.now()).build());

        if (withOtt) {
            authorities.add(
                FactorGrantedAuthority.withAuthority(
                    FactorGrantedAuthority.OTT_AUTHORITY)
                    .issuedAt(Instant.now()).build());
        }

        return UsernamePasswordAuthenticationToken.authenticated(
            "learner", null, authorities);
    }

    @Test
    void publicPageIsAnonymousFriendly() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void profileNeedsOnlyFirstFactor() throws Exception {
        mvc.perform(get("/profile")
                .with(authentication(evidence(false))))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:learner"));
    }

    @Test
    void completedFactorsUnlockProtectedEndpoint() throws Exception {
        mvc.perform(get("/settings/security")
                .with(authentication(evidence(true))))
            .andExpect(status().isOk())
            .andExpect(content().string("security:learner"));
    }

    @Test
    void bothFactorsPlusRolePermitAdmin() throws Exception {
        mvc.perform(get("/admin/export")
                .with(authentication(evidence(true))))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:learner"));
    }
}
```

Chạy:

```bash
mvn test
```

Kỳ vọng: **4 test pass** nếu project/build/Bean cấu hình phù hợp. Các test này **không gửi mail** và **không dùng mã OTT thật**: chúng trực tiếp chèn Authentication có factor authorities mới cấp để kiểm tra quy tắc ở MVC.

**Phải kiểm thử trạng thái thiếu factor** bằng request có password nhưng không OTT, tuy nhiên không nên viết một assertion cứng rằng kết quả luôn là 403: mặc định Spring Security 7 có thể **redirect đến bước OTT** dựa vào yếu tố thiếu. Trong UI browser, kiểm tra Location và continuation; với JSON API, cấu hình entry point/denied handler theo hợp đồng API để trả mã 401/403 + trạng thái `step_up_required` mà không tiết lộ secret.

Để chứng minh MFA **thật sự hoạt động**, cần integration test password login → tạo OTT → delivery đến mailbox test → tiêu thụ token → kiểm tra authorities và truy cập route nhạy cảm. MockMvc ở trên chỉ kiểm tra policy, không xác minh an toàn của kênh mail, token expiry, CSRF hay account ownership.

## 11. Khi factor đã hoàn tất nhưng quá cũ

Một yếu tố có thể còn được ghi trong Authentication, song policy thời gian đã hết hạn:

```text
12:00 Password authentication thành công
12:01 OTT authentication thành công
12:05 /profile                         -> ĐƯỢC PHÉP
12:20 /settings/security:
      yêu cầu password trong 10 phút
      và OTT trong 5 phút             -> CHƯA ĐỦ (cả hai quá cũ)
12:21 Password reauthentication      -> CÓ password mới
      OTT chưa được xác minh lại      -> VẪN CHƯA ĐỦ
12:22 OTT reauthentication           -> CÓ cả hai mới
      /settings/security             -> ĐƯỢC PHÉP
```

Sơ đồ này minh họa một policy **freshness**, không phải default timeout tự động cho mọi factor. Spring Security tách `issuedAt` và `validDuration` để áp dụng yêu cầu khác nhau theo endpoint.

**Các lưu ý biên:**

- Khi đồng hồ server không đồng bộ, timestamp và TTL có thể bị đánh giá sai. Dùng nguồn thời gian nhất quán, test boundary cases và đồng bộ NTP.
- Không reset `issuedAt` chỉ vì session được gia hạn hoặc browser gửi request mới.
- Sau một lần yếu tố được làm mới, policy chỉ coi **yếu tố đó** mới; không mặc nhiên refresh những yếu tố khác.
- User vẫn đang giữ một session hợp lệ **không có nghĩa mọi bằng chứng bên trong session vĩnh viễn đủ mới**.
- Đối với high-risk operation, có thể yêu cầu reauthentication theo từng giao dịch/transaction binding hoặc risk signal bổ sung. Chỉ có “OTT trong 5 phút” chưa chắc ngăn attacker sử dụng một session bị chiếm trong khoảng 5 phút đó.

## 12. Tổ hợp yếu tố: không phải mọi đường đăng nhập cần cùng một cặp

Một số sản phẩm muốn cho phép **WebAuthn một mình** (nếu user verification/policy đủ mạnh) *hoặc* **password + OTT**. Spring Security 7 hỗ trợ kết hợp các nhóm điều kiện với `AllRequiredFactorsAuthorizationManager.anyOf(...)`.

Ví dụ **trích đoạn Spring 7**, dùng các factor-aware managers đã được cấu hình:

```java
AllRequiredFactorsAuthorizationManager<Object> passkey =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.webauthnAuthority())
        .build();

AllRequiredFactorsAuthorizationManager<Object> passwordAndOtt =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.passwordAuthority())
        .requireFactor(factor -> factor.ottAuthority())
        .build();

DefaultAuthorizationManagerFactory<Object> mfa =
    new DefaultAuthorizationManagerFactory<>();

mfa.setAdditionalAuthorization(
    AllRequiredFactorsAuthorizationManager.anyOf(
        passkey, passwordAndOtt));
```

Để hoàn thành cấu hình, đưa `mfa.authenticated()` vào `authorizeHttpRequests(...).requestMatchers(...).access(...)` và cung cấp các cơ chế thực tế `formLogin()`, `oneTimeTokenLogin()`, `webAuthn()` cùng credential repository.

**Chú ý:** đây là hai **tổ hợp được policy cho phép**, không phải kiểm tra “chỉ cần một yếu tố yếu bất kỳ”. Một WebAuthn passkey với user verification có thể đáp ứng tiêu chí rủi ro khác với một OTP qua email. Việc kết hợp nhóm factor phải dựa trên threat model và mức bảo đảm thực tế, không chỉ số lượng nhãn `FACTOR_*`.

## 13. Lưu trạng thái hoàn tất ở đâu và những gì phải vô hiệu?

### 13.1. Authentication và SecurityContext

Trong Servlet stack, Spring Security lưu `Authentication` trong `SecurityContextHolder` cho request hiện tại; tùy cấu hình `SecurityContextRepository`, nó được lưu/khôi phục qua HTTP session giữa các request.

Với MFA, framework cần một mô hình giữ được các factors đã chứng minh để bước tiếp theo **bổ sung** thay vì reset toàn bộ. Đừng tùy tiện ghi đè Authentication đã có bằng một Authentication chỉ chứa factor mới rồi làm mất factor cũ. Cũng đừng gộp factors của hai user hoặc hai session.

Dữ liệu logic trong session có thể hiểu như:

```text
SessionId: S-123
Principal: learner
Authorities: ROLE_ADMIN
CompletedFactors:
    FACTOR_PASSWORD (issuedAt: 12:00)
    FACTOR_OTT      (issuedAt: 12:01)
CurrentRequiredPolicy:
    /profile        -> authenticated
    /settings/**    -> PASSWORD + OTT
    /admin/**       -> ROLE_ADMIN + PASSWORD + OTT
```

Bảng mô tả khái niệm, **không phải schema session serialized chính xác của Spring Security**. Policy nên được đánh giá từ cấu hình/server-side mỗi request, không nên tin “CurrentRequiredPolicy” do browser cung cấp.

### 13.2. Session fixation, logout, revoke và biến động quyền

- Khi login/step-up thành công, bảo đảm session được bảo vệ khỏi fixation theo cấu hình Spring Security; cookie dùng `Secure`, `HttpOnly`, `SameSite` phù hợp.
- Logout phải xóa context/phiên hợp lệ và trạng thái challenge đang chờ; không giữ factors trong một cookie tự tạo rồi bỏ qua server verification.
- Khi account bị disable, user đổi password, thu hồi WebAuthn credential hoặc cập nhật quyền, cần có chiến lược invalidation/re-evaluation. Session cũ không phải giấy phép vĩnh viễn.
- Nếu có nhiều node, session store/challenge store cần nhất quán; OTT service mặc định in-memory không đáp ứng tự động phân tán hay restart. Xem `JdbcOneTimeTokenService` cho môi trường thích hợp.
- Nếu dùng JWT stateless mang “MFA completed” claim, server phát token phải hiểu đúng bằng chứng và thời điểm; resource server cần xác minh issuer, audience, signature, expiry và semantics của claim. Không tự lấy `mfa=true` từ request parameter.

### 13.3. Đừng phát lộ toàn bộ authentication

Có thể hiển thị trạng thái factor một cách an toàn (ví dụ “cần xác minh bổ sung”) cho user đã đăng nhập. Nhưng tránh trả raw `Authentication.getCredentials()`, token OTP, mã recovery hoặc thông tin session. Kể cả các authorities/issuedAt cũng là thông tin bảo mật nội bộ nên kiểm soát endpoint truy xuất.

## 14. OTT không phải OTP; độc lập giữa các yếu tố rất quan trọng

Spring Security hỗ trợ `oneTimeTokenLogin()` và tạo `FACTOR_OTT` khi cơ chế đó được hoàn tất. OTT thường là **magic link/token** server phát rồi phân phối cho user bằng email/SMS hoặc kênh khác.

**Đừng nhầm:** TOTP/HOTP là mã one-time từ shared secret theo thời gian/counter. Spring OTT không phải là một authenticator app TOTP mặc định. Việc thêm `oneTimeTokenLogin()` không tự tạo SMS gateway, SMTP service, recovery policy hoặc đảm bảo kênh phân phối mạnh.

MFA đúng nghĩa cần cân nhắc **độc lập của các yếu tố**:

- Password + magic link gửi vào cùng hộp thư dùng để reset password có thể phụ thuộc mạnh vào quyền kiểm soát mailbox; hãy đánh giá rủi ro thực tế.
- Password + WebAuthn có user verification và RP binding thường có tính chất khác với password + email OTT.
- Xác thực bằng password trên thiết bị đã bị malware kiểm soát, rồi token thứ hai cũng hiển thị trên cùng thiết bị, không triệt tiêu hoàn toàn nguy cơ chiếm session.
- FIDO2/passkey có thể cung cấp phishing-resistant authentication, nhưng việc cấp quyền/quản lý session và chống account recovery takeover vẫn thuộc trách nhiệm ứng dụng.

Những factor strings được framework dùng **không phải điểm AAL/NIST tự chứng nhận**. Nếu hệ thống phải tuân thủ chuẩn assurance (ví dụ NIST SP 800-63), cần xem loại authenticator, xác minh danh tính, storage, session, replay protection, recovery và toàn bộ rủi ro theo chuẩn, không tự quy đổi `FACTOR_PASSWORD+FACTOR_OTT` thành “AAL2 chắc chắn”.

## 15. Hành vi lỗi và cách xử lý UX/API

| Tình huống | Trạng thái logic | Cách xử lý hợp lý |
| --- | --- | --- |
| Anonymous truy cập `/profile` | Chưa xác thực | Browser: chuyển `/login`; API: 401 theo hợp đồng |
| Password đúng, chưa OTT; vào `/profile` | Đã có bằng chứng đủ cho endpoint | Cho phép |
| Password đúng, chưa OTT; vào `/settings/security` | Missing `FACTOR_OTT` | Step-up đến OTT challenge; chặn thao tác nhạy cảm |
| OTT đúng, chưa password; vào route cần cả hai | Missing `FACTOR_PASSWORD` | Đến password login |
| Có cả hai nhưng password quá 10 phút | Stale factor | Reauthenticate password (và OTT nếu cũng stale) |
| Có hai factor, thiếu `ROLE_ADMIN` | Thiếu quyền nghiệp vụ | 403 hoặc access denied; không “cho thành admin” sau OTT |
| OTT sai/hết hạn/đã tiêu thụ | Chưa hoàn thành factor | Từ chối, rate limit; không cấp `FACTOR_OTT` |
| User A có password, token của user B được gửi | Bằng chứng khác principal | Từ chối; không trộn identity/factors |
| User đăng ký passkey nhưng chưa dùng ở phiên này | Enrolled, chưa completed `FACTOR_WEBAUTHN` | Yêu cầu assertion nếu policy cần factor |
| OTT/mail service bị lỗi | Không thể hoàn tất factor | Fail-closed cho endpoint yêu cầu factor; báo retry an toàn |

### 15.1. 401, 403 hay 302?

Trong **web UI** có form login, khi thiếu factor Spring Security 7 có thể tự chuyển hướng tới cơ chế xác thực còn thiếu (ví dụ OTP/OTT page). Nếu resource là **JSON API**, không nên tự động redirect đến một HTML login page mà API client không hiểu; có thể cấu hình response theo contract như `401 step_up_required` hoặc `403 insufficient_authentication`, kèm thông tin có kiểm soát về phương thức tiếp theo.

Không dùng một HTTP status duy nhất để suy luận chính xác yếu tố đã có: HTTP response phụ thuộc `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, access-denied configuration, content negotiation và cơ chế authentication.

### 15.2. Tránh vòng redirect vô hạn

Nếu global MFA policy áp dụng lên cả màn hình dùng để hoàn tất factor, request có thể rơi vào vòng `/login` → `/ott/generate` → `/login`. Dùng DSL/entry point/framework tích hợp đúng và kiểm thử end-to-end; đừng tạo một `CustomAccessDeniedHandler` luôn redirect về cùng trang mà thiếu state máy xác thực.

## 16. Bảo mật và kiểm thử nâng cao

Checklist cho một hệ thống nhiều yếu tố có trạng thái hoàn tất:

1. **Mỗi factor được cấp đúng lúc:** chỉ sau thành công mật mã/credential verification, không dựa trên header/query/boolean trong request.
2. **Không hoán đổi principal:** password của A cộng OTT của B không được trở thành “A có đủ hai factor”.
3. **Không tái sử dụng OTT:** token hết hạn hoặc đã consume một lần phải bị từ chối, kể cả browser gửi lại request cũ.
4. **Freshness:** test thời điểm ngay trước, đúng tại và sau hạn `validDuration`; test clock skew.
5. **Step-up:** user có password nhưng thiếu OTT vào được route thấp, không vào được route cao; sau OTT mới vào được.
6. **Privilege:** đủ factor nhưng thiếu role/tenant ownership vẫn 403.
7. **Recovery:** khôi phục quyền truy cập không tự bỏ hết chính sách MFA; enrollment/đổi kênh OTP phải yêu cầu reauthentication đủ mạnh.
8. **Throttling:** hạn chế thử password, xin OTT, kiểm tra OTT, resend link và tạo factor mới để tránh enumeration/spam/DoS.
9. **Session:** kiểm thử session fixation, expiry, logout, nhiều tab, nhiều thiết bị và cluster.
10. **CSRF:** form password/OTT, settings và các POST tạo token phải bảo vệ theo mô hình browser; không tắt toàn bộ CSRF để “MFA chạy”.
11. **Transport:** HTTPS, cookies, bảo vệ query tokens khỏi referrer/log, secrets khỏi telemetry.
12. **Version:** kiểm tra Spring Boot 4/Security 7 packages và test actual dependency tree; không dùng code MFA 7.x trên 6.5.
13. **Audit:** ghi sự kiện “password verified”, “OTT verified”, “MFA required but incomplete” bằng user/session ID đã được bảo vệ; không log raw token/mật khẩu.
14. **Monitoring:** giám sát tỷ lệ step-up failure, token delivery delay, abuse và redirect loops mà không làm lộ dữ liệu cá nhân.

Một bài test cần đặc biệt có giá trị: user ban đầu đã có `ROLE_ADMIN` trong `Authentication` nhưng chỉ có `FACTOR_PASSWORD`. Nếu app vẫn cho `/admin/export` thì **chính sách MFA đã bị bypass**. Roles và factors phải cùng tham gia điều kiện truy cập, không dùng “role OR factor” trừ khi chính sách sản phẩm thật sự yêu cầu khác.

## 17. Câu hỏi tự kiểm tra

1. **Một Authentication có `isAuthenticated() == true` thì đã hoàn tất MFA chưa?** Không. Nó có thể chỉ chứng minh một cơ chế; cần kiểm tra policy của tài nguyên.
2. **Yếu tố đã hoàn tất được Spring Security 7 biểu diễn bằng gì?** `FactorGrantedAuthority` gồm authority name và `issuedAt`.
3. **Vì sao không chỉ lưu boolean `mfaDone=true`?** Nó không cho biết factor nào, thời điểm nào, thuộc user/session nào, còn hiệu lực ở endpoint nào.
4. **Password 15 phút trước và OTT vừa xong có vào route cần password trong 10 phút không?** Không; password phải được xác thực lại.
5. **Sự khác nhau giữa `ROLE_ADMIN` và `FACTOR_OTT`?** Role là quyền nghiệp vụ; factor là bằng chứng phương thức xác thực.
6. **Vì sao `@EnableMultiFactorAuthentication(authorities = {})` hữu ích?** Bật MFA support nhưng không ép yêu cầu factor toàn cục, cho phép chọn route cần step-up.
7. **Có thể dùng `@EnableMultiFactorAuthentication` trên Spring Security 6.5 không?** Không dùng cùng API của 7.x; cần nâng cấp hoặc thiết kế khác tương thích.
8. **OTT khác TOTP thế nào?** OTT thường server phát và phân phối token/link; TOTP là mã do authenticator tạo theo shared secret/time.
9. **Sau khi user đăng ký passkey có tự mang `FACTOR_WEBAUTHN` ở mọi request không?** Không; enrollment khác hoàn tất WebAuthn assertion trong phiên.
10. **Vì sao mock `@WithMockUser` không đủ để test actual MFA?** Nó không kiểm tra login mechanisms/token issuance và có thể không tạo đúng `FactorGrantedAuthority`.
11. **Thiếu factor luôn trả HTTP 401?** Không. Browser có thể nhận redirect step-up; API có thể theo contract 401/403, tùy handler.
12. **Spring Security 7 có cho yêu cầu “passkey hoặc password+OTT” không?** Có thể dùng `AllRequiredFactorsAuthorizationManager.anyOf(...)` kết hợp chính sách tương ứng.
13. **Vì sao phải invalidate/cập nhật factors sau thay đổi account?** Session có thể giữ Authentication cũ, trong khi quyền và phương thức xác thực đã thay đổi.
14. **Nếu mail server không gửi được OTT thì có được phép bỏ qua không?** Không. Route yêu cầu OTT phải fail-closed; cần chiến lược recovery được phê duyệt.

## 18. Tài liệu chính thức để tiếp tục

- Spring Security – Multi-Factor Authentication (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Spring Security – One-Time Token Login: https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html
- Spring Security – FactorGrantedAuthority API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security – EnableMultiFactorAuthentication API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- Spring Security – AuthorizationManagerFactories API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagerFactories.html
- Spring Security – AllRequiredFactorsAuthorizationManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AllRequiredFactorsAuthorizationManager.html
- Spring Security – Servlet authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security – MFA in Spring Security 7 (official blog, 21/10/2025): https://spring.io/blog/2025/10/21/multi-factor-authentication-in-spring-security-7/
- Spring Boot 4 – Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Spring Boot 4 – Testing applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot 4 – Web MVC starter: https://docs.spring.io/spring-boot/reference/web/index.html
