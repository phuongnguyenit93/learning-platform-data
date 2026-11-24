# Spring Security recovery boundary — Ranh giới khôi phục tài khoản trong Spring Security

## 1. Recovery có thể công khai ở HTTP nhưng vẫn phải kiểm soát quyền

Người mất mật khẩu, MFA, passkey hoặc thiết bị thường chưa thể đăng nhập theo cách thông thường. Vì vậy, một số endpoint recovery phải tiếp nhận request từ người chưa xác thực.

Điều đó tạo ra một ranh giới dễ hiểu sai:

> Cho phép một request đi vào luồng recovery không đồng nghĩa cho phép request đó thay đổi tài khoản.

Spring Security kiểm soát request và trạng thái xác thực của ứng dụng. Miền account recovery phải kiểm soát bằng chứng, mục đích, phạm vi cấp quyền, token dùng một lần, chống lạm dụng và hậu quả của việc thay credential.

Nếu cấu hình `permitAll()` rồi controller cập nhật mật khẩu chỉ dựa trên account ID từ request, hệ thống đã mở đường thay credential trái phép. Ngược lại, nếu bắt mọi endpoint recovery phải `authenticated()`, người thực sự mất phương thức xác thực có thể không bắt đầu được.

Bài học này trình bày cách đặt ranh giới giữa hai phần ấy trong một ứng dụng **Spring Security Servlet**, dùng DSL và tài liệu tham chiếu dòng **6.5**. Ví dụ không xác định phiên bản dependency đang dùng trong một repository cụ thể và không phải bộ triển khai recovery hoàn chỉnh. Khi dùng dòng khác, cần đối chiếu API, matcher và hành vi mặc định tương ứng.

## 2. Bốn trạng thái quyền không nên bị trộn

Có thể mô hình hóa:

~~~mermaid
flowchart LR
    A[Chưa xác thực] --> B[Đang chứng minh điều kiện recovery]
    B --> C[Quyền recovery giới hạn]
    C --> D[Thay đổi được phép và hoàn tất kiểm soát]
    D --> E[Đăng nhập theo cơ chế thông thường]
    E --> F[Session và quyền ứng dụng]
~~~

Mỗi bước có nghĩa khác nhau:

| Trạng thái | Điều có thể biết | Điều chưa được tự cấp |
|---|---|---|
| Chưa xác thực | Có một request muốn bắt đầu recovery | Quyền thay credential |
| Đang chứng minh | Attempt tồn tại và đang thu bằng chứng | Quyền truy cập dữ liệu tài khoản |
| Có recovery grant | Một thao tác cụ thể đã được cho phép có điều kiện | Session ứng dụng đầy đủ |
| Đã hoàn tất thay đổi | Credential hoặc authenticator đã được xử lý theo policy | Mọi quyền nhạy cảm không cần xác thực lại |
| Đăng nhập bình thường | Đã qua cơ chế xác thực được áp dụng cho ứng dụng | Quyền vượt ngoài authorization của tài khoản |

Một token đặt lại mật khẩu không nên tự biến thành `ROLE_USER`. Kết quả xác minh một challenge cũng chưa tự cho phép thay MFA, thêm passkey và đổi email.

Nếu ứng dụng cần một luồng sau recovery có quyền hạn tạm thời, hãy định nghĩa rõ scope, thời hạn và các hành động được phép. Đừng dùng trạng thái “đã đăng nhập một phần” mà mọi endpoint chỉ kiểm tra `authenticated()`.

## 3. Spring Security làm gì, recovery service làm gì?

### 3.1. Ranh giới trách nhiệm

| Thành phần | Trách nhiệm điển hình |
|---|---|
| Servlet container và filter chain | Tiếp nhận request, áp dụng các filter |
| Spring Security | Chọn chain, áp dụng kiểm soát request, CSRF, authentication và authorization đã cấu hình |
| Recovery application service | Điều phối attempt, policy, verifier và thao tác recovery |
| Kho trạng thái có thẩm quyền | Kiểm soát version, thời hạn, tiêu thụ token và cập nhật nguyên tử |
| Credential/authenticator service | Thực hiện đúng loại thay đổi được cấp quyền |
| Session/token control plane | Thực thi thu hồi hoặc hạn chế quyền sau recovery |
| Notification và audit | Ghi nhận, gửi thông báo và cung cấp dữ liệu vận hành phù hợp |

Spring Security có thể cung cấp các điểm mở rộng để tích hợp, nhưng không thể tự suy ra policy recovery của sản phẩm chỉ từ một URL.

Ví dụ, `PasswordEncoder` giải quyết việc biến đổi và kiểm tra mật khẩu ở dạng lưu trữ phù hợp. Nó không xác minh người gọi có quyền đặt mật khẩu cho tài khoản nào, không chống replay recovery token và không tự thu hồi mọi session.

### 3.2. Filter chain là cửa vào, không phải toàn bộ quyết định nghiệp vụ

Theo [Spring Security Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html), request được xử lý qua cơ chế filter, với `FilterChainProxy` lựa chọn `SecurityFilterChain` phù hợp. Thứ tự và cấu hình filter quyết định những kiểm soát nào thực sự chạy.

Đối với recovery, cần trả lời hai câu riêng:

1. Request này có được phép đi đến endpoint không?
2. Người giữ bằng chứng/grant này có được thực hiện thao tác cụ thể không?

Câu thứ nhất có thể được trả lời bằng URL authorization. Câu thứ hai cần kiểm tra nghiệp vụ có thẩm quyền, không thể suy từ việc request đã qua chain.

## 4. Chọn chain đúng trước khi chọn rule

### 4.1. Hai cấp matcher

Trong cấu hình Java:

- `securityMatcher(...)` giới hạn những request mà một chain có thể xử lý.
- `requestMatchers(...)` bên trong `authorizeHttpRequests` chọn rule authorization trong chain đó.

Nếu chain có ưu tiên cao đã match, request không được đi tiếp qua mọi chain khác để cộng dồn chính sách. Một rule ở chain phía sau có thể không bao giờ áp dụng cho request ấy.

Tài liệu [Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html#_choosing_securitymatcher_or_requestmatchers) giải thích hai cấp matcher và lưu ý request không match chain nào sẽ không được Spring Security bảo vệ. Vì vậy cần có chain bao phủ phần còn lại của ứng dụng.

### 4.2. `anyRequest()` chỉ có nghĩa trong chain đang xét

Ví dụ một chain chỉ match `/account-recovery/**`, thì `anyRequest().denyAll()` ở trong đó chỉ chặn các request còn lại thuộc phạm vi chain ấy.

Nó không chặn toàn bộ ứng dụng. Ngược lại, một catch-all chain có thứ tự quá cao có thể lấy mất recovery request trước khi chain chuyên biệt có cơ hội xử lý.

Với endpoint nhạy cảm, nên xác định cả method và path. Cho phép POST hoàn tất recovery không có nghĩa cho phép GET, PUT hoặc mọi route thêm sau này trong cùng namespace.

### 4.3. Kiểm tra path theo thực tế triển khai

Context path, servlet path, proxy rewrite và nhiều servlet có thể làm cách match khác với điều lập trình viên đang tưởng tượng.

Đừng mặc định một annotation controller và một chuỗi matcher chắc chắn nói về cùng URL sau mọi lớp proxy. Ranh giới phải được xác nhận bằng request thực tế và cấu hình của môi trường triển khai.

Các route quản trị hoặc hỗ trợ không nên vô tình nằm dưới một wildcard công khai rộng như `/account-recovery/**` mà không có rule chặn rõ.

## 5. `permitAll()` khác với bỏ qua Spring Security

### 5.1. `permitAll()` chỉ giải quyết authorization ở cửa HTTP

Một request được permit vẫn có thể bị các kiểm soát khác từ chối, chẳng hạn CSRF. Nó cũng vẫn đi qua các filter được cấu hình trong chain.

Theo [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html), các rule authorization được xét theo thứ tự, và `permitAll` cho phép truy cập endpoint mà không yêu cầu quyền tại rule đó.

Trong recovery, cách dùng hợp lý là:

~~~text
HTTP layer:
    Cho phép gọi endpoint bắt đầu/hoàn tất recovery.

Domain layer:
    Chỉ thay đổi tài khoản nếu bằng chứng, grant và trạng thái đều hợp lệ.
~~~

Tên “public endpoint” không làm cho thao tác bên trong trở thành thao tác không cần kiểm chứng.

### 5.2. Không dùng `web.ignoring()` để chữa lỗi recovery

Bỏ qua namespace recovery ở mức web security có thể bỏ luôn các filter bảo vệ mà ứng dụng đang dựa vào. Nó không tương đương với permit một số endpoint cần thiết trong chain.

Nếu gặp 403, cần xác định nó đến từ CSRF, authorization hay kiểm tra nghiệp vụ. Đưa cả namespace ra khỏi Spring Security chỉ làm mất kiểm soát mà chưa giải quyết nguyên nhân.

Tương tự, thêm `permitAll()` không tự sửa được một custom filter vẫn bắt token đăng nhập cho mọi path. Cần điều chỉnh phạm vi và thứ tự của filter đó theo thiết kế.

## 6. Một cấu hình tách ranh giới cho browser recovery

Giả sử ứng dụng dùng cùng origin, recovery có các endpoint:

| Endpoint | Vai trò |
|---|---|
| GET `/account-recovery/csrf` | Cấp dữ liệu CSRF cho client chưa đăng nhập |
| POST `/account-recovery/requests` | Tiếp nhận yêu cầu bắt đầu recovery |
| POST `/account-recovery/password/complete` | Nhận bằng chứng/grant và mật khẩu mới |
| Các route recovery khác | Bị từ chối cho đến khi được thiết kế rõ |

Thiết kế minh họa chọn:

- Giữ CSRF cho luồng browser.
- Không nạp/lưu authentication ứng dụng qua session trong recovery chain.
- Không biến recovery thành form login hoặc HTTP Basic.
- Không lưu recovery request thành saved request để phát lại sau đăng nhập.
- Đặt một chain khác bao phủ phần còn lại.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
@EnableWebSecurity
public class RecoveryBoundaryConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain recoveryChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/account-recovery/**")
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()
                )
            )
            .requestCache(cache -> cache.disable())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    HttpMethod.GET,
                    "/account-recovery/csrf"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.POST,
                    "/account-recovery/requests",
                    "/account-recovery/password/complete"
                ).permitAll()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/error").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

Đây là phần cấu hình ranh giới; nó giả định cơ chế đăng nhập bình thường được cấu hình ở ứng dụng. Không có tài khoản demo, provider recovery hoặc chính sách MFA tự động được tạo bởi đoạn code này.

### 6.1. Vì sao dùng `NullSecurityContextRepository`?

Repository này không lưu authentication cho request sau. Trong cấu hình trên, recovery được thiết kế như luồng sử dụng bằng chứng riêng, không lấy session ứng dụng cũ làm bằng chứng ngầm.

Cách hoạt động của các repository được mô tả trong [Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html). Phải phân biệt nơi lưu context với nơi kiểm tra bằng chứng recovery.

Lựa chọn này không có nghĩa:

- Mọi ứng dụng đều phải tách theo cách này.
- Session đang tồn tại của ứng dụng đã bị thu hồi.
- Không thành phần nào còn tạo `HttpSession`.
- Code phía sau không thể tự ghi authentication bằng cách khác.

Đặc biệt, CSRF repository mặc định có thể sử dụng session. **Không lưu authentication qua session** và **không dùng session cho bất kỳ mục đích nào** là hai điều khác nhau.

Nếu policy cần tận dụng một authenticator còn hoạt động để xác thực lại, nên có luồng được thiết kế riêng cho trường hợp ấy. Ví dụ tách anonymous recovery khỏi authenticated credential management, thay vì lén đọc session cũ trong service.

### 6.2. Vì sao tắt request cache cho chain recovery?

Một saved request phù hợp cho luồng truy cập trang được bảo vệ rồi đăng nhập. Với recovery, không nên để việc đăng nhập sau đó vô tình phát lại một request chứa thông tin nhạy cảm hoặc làm lẫn mục tiêu recovery với đích truy cập ứng dụng.

Tắt request cache ở chain recovery không tắt bộ cache của mọi thành phần, cũng không thay thế `Cache-Control` trên response. Hai cơ chế có mục đích khác nhau.

### 6.3. Chain này không tự bao phủ mọi lối vào

Nếu có GraphQL, RPC, message consumer hoặc service nội bộ thực hiện cùng thao tác thay credential, chúng cũng phải gọi logic cấp quyền thích hợp.

Tương tự, filter được đăng ký trực tiếp với servlet container có thể chạy ngoài dự đoán của riêng chain trên. Cần hiểu cấu hình thực tế, không chỉ nhìn hai bean `SecurityFilterChain`.

## 7. Giữ CSRF đúng cho luồng browser

### 7.1. Anonymous không có nghĩa không có CSRF

CSRF liên quan tới việc browser tự gửi ngữ cảnh như cookie khi bị một site khác tác động. Người chưa đăng nhập vẫn có thể có session dùng cho CSRF hoặc trạng thái recovery.

Do đó, không nên suy rằng endpoint permitAll thì không cần CSRF. Cũng không nên tắt toàn bộ CSRF chỉ vì đang truyền recovery token trong JSON.

Một recovery token là bằng chứng nghiệp vụ; CSRF token là kiểm soát nguồn gốc/ngữ cảnh request theo thiết kế của ứng dụng. Có trường hợp bearer-only API cần mô hình khác, nhưng phải đánh giá theo cơ chế truyền credential thực tế.

[Spring Security CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) mô tả bảo vệ mặc định với unsafe methods và cách client lấy token qua endpoint trước khi xác thực.

### 7.2. Endpoint lấy CSRF token

Một controller nhỏ cho cấu hình trên:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/account-recovery")
public class RecoveryCsrfController {

    @GetMapping("/csrf")
    public ResponseEntity<CsrfView> csrf(CsrfToken token) {
        CsrfView view = new CsrfView(
            token.getHeaderName(),
            token.getParameterName(),
            token.getToken()
        );

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(view);
    }

    public record CsrfView(
        String headerName,
        String parameterName,
        String token
    ) {
    }
}
~~~

Client cần giữ cookie tương ứng và gửi token theo tên header được trả về. Với cách xử lý CSRF mặc định của dòng tham chiếu, dùng token được endpoint cung cấp thay vì tự giả định có thể đọc một cookie và gửi lại dưới mọi cấu hình.

~~~javascript
const csrfResponse = await fetch("/account-recovery/csrf", {
  credentials: "same-origin",
  cache: "no-store"
});

if (!csrfResponse.ok) {
  throw new Error("Không thể chuẩn bị request khôi phục");
}

const csrf = await csrfResponse.json();

const response = await fetch(
  "/account-recovery/password/complete",
  {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({
      token: recoveryTokenFromSafeInput,
      newPassword: passwordFromForm
    })
  }
);
~~~

Các biến cuối là giá trị từ luồng giao diện đã được thiết kế, không phải chuỗi hardcode. Không ghi chúng vào console, analytics hoặc error report.

Không cho phép một origin tùy ý có credential đọc endpoint CSRF. Nếu triển khai cross-origin, cần thiết kế CORS, cookie, trusted origins và CSRF như một hệ thống thống nhất.

### 7.3. CORS, SameSite và CSRF không thay thế nhau

CORS kiểm soát một số quyền tương tác của browser giữa các origin; nó không phải bộ verifier recovery. SameSite là một thuộc tính cookie hỗ trợ giảm một số đường tấn công, không tự giải quyết mọi nguồn request không mong muốn.

Nếu dùng cookie recovery, browser tự đính kèm cookie ấy trong những điều kiện cấu hình cho phép. Cần đánh giá lại CSRF ngay cả khi không lưu authentication bằng session.

GET không nên tiêu thụ token hoặc cập nhật credential. Trình quét email, trình duyệt tải trước và proxy có thể mở link. Landing page có thể phục vụ bước trình bày, nhưng thao tác thay đổi cần request và kiểm chứng thích hợp.

## 8. Controller chỉ chuyển một lệnh có phạm vi rõ

Một controller hoàn tất password recovery có thể gọi application service:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/account-recovery")
public class CompletePasswordRecoveryController {

    private final TrustedRecoveryTenantResolver tenantResolver;
    private final CompletePasswordRecoveryService recoveryService;

    public CompletePasswordRecoveryController(
            TrustedRecoveryTenantResolver tenantResolver,
            CompletePasswordRecoveryService recoveryService) {
        this.tenantResolver = tenantResolver;
        this.recoveryService = recoveryService;
    }

    @PostMapping("/password/complete")
    public ResponseEntity<Void> complete(
            HttpServletRequest request,
            @Valid @RequestBody CompletePasswordBody body) {

        var tenant = tenantResolver.resolveForRecovery(request);

        recoveryService.complete(
            tenant,
            body.token(),
            body.newPassword()
        );

        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }

    public record CompletePasswordBody(
        @NotBlank
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String token,

        @NotBlank
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String newPassword
    ) {
        @Override
        public String toString() {
            return "CompletePasswordBody[REDACTED]";
        }
    }
}
~~~

`TrustedRecoveryTenantResolver` và `CompletePasswordRecoveryService` là các thành phần miền cần được triển khai; đoạn này chỉ minh họa ranh giới controller. Bean Validation, JSON và Spring MVC phải được cấu hình trong ứng dụng dùng ví dụ.

Điểm cần giữ:

- Không nhận account ID rồi tin rằng người gọi có quyền với account đó.
- Không chọn subject từ một session không liên quan tới grant.
- Không set `SecurityContextHolder` chỉ vì service trả thành công.
- Không trả lại token hoặc password trong response.
- Không dùng `@NotBlank` thay cho kiểm tra token và policy mật khẩu.

Record có secret được override `toString` để tránh một đường rò rỉ dễ gặp. `WRITE_ONLY` giúp không serialize các property này ra JSON theo cấu hình Jackson tương ứng, nhưng không ngăn HTTP body logger, APM hoặc debugger thu chúng.

Ứng dụng vẫn cần giới hạn kích thước request và độ dài trường theo profile hợp lệ, đồng thời kiểm soát log ở mọi lớp.

### 8.1. Tenant phải được giải quyết bằng ngữ cảnh có căn cứ

Resolver cần dựa trên mô hình tenant của ứng dụng: host đã được xác minh, route đã ánh xạ và cấu hình tin cậy, hoặc cơ chế tương đương.

Một header `X-Tenant-ID` do client tự gửi chưa tự chứng minh phạm vi. Khi lookup token và attempt, service vẫn phải kiểm tra chúng thuộc đúng tenant và subject.

Nếu cùng browser đang có session tài khoản A nhưng token hợp lệ thuộc tài khoản B, thao tác phải tuân theo chính sách và subject của bằng chứng được kiểm tra, không trộn ngầm hai danh tính.

### 8.2. Endpoint bắt đầu cần phản hồi công khai phù hợp

POST requests có thể tiếp nhận một account hint và trả thông điệp chung theo policy. Backend vẫn cần xử lý rate limit, danh tính chưa rõ, lựa chọn phương án và rủi ro.

Phản hồi “đã tiếp nhận” không nên được hiểu là đã phát một grant. Không dựa vào status HTTP của bước bắt đầu để gán người gọi là chủ tài khoản.
