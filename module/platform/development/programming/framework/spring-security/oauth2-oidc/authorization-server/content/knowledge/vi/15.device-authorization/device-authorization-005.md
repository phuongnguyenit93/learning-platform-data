# Đăng nhập, consent và phê duyệt hoặc từ chối yêu cầu thiết bị

> **Chương:** Device Authorization  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Phạm vi:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phiên bản minh họa:** Spring Boot 3.x, Spring Security 6.x, Spring Authorization Server 1.x trên Servlet stack. Với Spring Security 7.x, các lớp/configurer có thể đổi package hoặc cách tích hợp: đối chiếu tài liệu đúng phiên bản, không copy nguyên cấu hình major cũ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **Device Authorization Grant** (RFC 8628) tách việc yêu cầu quyền trên thiết bị hạn chế nhập liệu khỏi việc đăng nhập và consent trên trình duyệt thứ hai.
2. Phân biệt `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in` và `interval`.
3. Mô tả đầy đủ luồng **đăng nhập người dùng → xác minh user code → kiểm tra thông tin thiết bị/client → consent → phê duyệt hoặc từ chối → thiết bị polling token endpoint**.
4. Phân biệt trách nhiệm của `OAuth2DeviceAuthorizationEndpointConfigurer`, `OAuth2DeviceVerificationEndpointConfigurer` và `OAuth2TokenEndpointConfigurer` trong Spring Authorization Server.
5. Tạo một trang consent dành cho device flow, chuyển đúng `user_code`, `client_id`, `state`, scope đã đồng ý và CSRF token.
6. Thiết kế nhánh từ chối **thực sự làm grant chuyển sang trạng thái bị từ chối**, để token endpoint trả `access_denied`, thay vì chỉ đóng trình duyệt.
7. Kiểm thử các trường hợp chưa đăng nhập, mã sai/hết hạn, consent một phần, từ chối, polling quá nhanh, đăng nhập nhầm tài khoản, phishing và race condition.

**Nguyên tắc xuyên suốt:** Thiết bị có thể bắt đầu một yêu cầu cấp quyền, nhưng **không được coi yêu cầu đó đã được chấp thuận** chỉ vì người dùng mở trang xác minh hoặc đăng nhập thành công. **Quyết định đồng ý/từ chối phải gắn với đúng device authorization session, đúng user, client và phạm vi quyền đã xác minh.**

## 2. Bài toán thực tế: đăng nhập cho TV, máy in và thiết bị IoT

Giả sử người dùng muốn đăng nhập ứng dụng đặt phòng trên một smart TV. TV có thể hiển thị một mã ngắn, nhưng nhập mật khẩu dài hoặc làm MFA trực tiếp bằng điều khiển từ xa vừa khó vừa không an toàn.

Device Authorization Grant cho phép TV:

1. Liên hệ Authorization Server (AS) để xin một device authorization session.
2. Nhận `user_code` và đường dẫn `verification_uri` để hiển thị.
3. Để người dùng dùng **điện thoại hoặc máy tính đáng tin cậy** mở URL xác minh, đăng nhập vào AS và quyết định có cho phép TV truy cập hay không.
4. Trong khi đó, TV **poll** token endpoint theo khoảng thời gian được chỉ định.
5. Chỉ sau khi người dùng **phê duyệt**, AS mới cấp access token cho TV theo grant tương ứng.

Nếu người dùng **từ chối**, TV phải biết quyết định này qua lỗi giao thức và dừng polling. Nếu mã hết hạn, TV phải bắt đầu phiên mới khi người dùng chủ động yêu cầu. Đây là tình huống điển hình của RFC 8628. <https://www.rfc-editor.org/rfc/rfc8628>

### 2.1. Các vai trò

| Thành phần | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| **Resource Owner** | Người quyết định cấp quyền, ví dụ Lan | Thiết bị đang xin quyền |
| **Device / OAuth2 Client** | TV chạy ứng dụng `booking-tv` | Trình duyệt điện thoại dùng để login |
| **Secondary device / browser** | Điện thoại truy cập `verification_uri`, đăng nhập và consent | Nơi AS gửi access token của TV |
| **Authorization Server** | Tạo device session, xác thực user, ghi nhận quyết định và phát token | API nghiệp vụ (Resource Server) |
| **Resource Server** | Xác minh access token và áp dụng chính sách cho API | Trang xác minh mã thiết bị |

TV thường **không nhận mật khẩu của Lan**. Điện thoại **không chuyển refresh token hoặc access token của tài khoản cho TV qua QR/URL**; TV tự nhận token từ AS sau khi grant được chấp thuận.

## 3. Phân biệt `device_code` và `user_code`

Một response thành công của Device Authorization Endpoint thường có dạng:

~~~json
{
  "device_code": "opaque-high-entropy-device-code",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://auth.example.test/oauth2/device_verification",
  "verification_uri_complete": "https://auth.example.test/oauth2/device_verification?user_code=WDJB-MJHT",
  "expires_in": 600,
  "interval": 5
}
~~~

Đây là dữ liệu **minh họa**. Không dùng các giá trị mã cố định trong hệ thống thật; AS phải sinh code ngẫu nhiên, không thể dự đoán, giới hạn thời hạn và yêu cầu kiểm tra phù hợp.

| Thuộc tính | Bên sử dụng chính | Ý nghĩa và quy tắc |
| --- | --- | --- |
| `device_code` | Thiết bị / token endpoint | Chuỗi bí mật, entropy cao; TV dùng trong polling, **không hiển thị để người dùng nhập** |
| `user_code` | Người dùng nhập trên browser thứ hai | Mã ngắn dễ đọc/nhập, dùng để tìm đúng yêu cầu; không phải access token |
| `verification_uri` | Browser thứ hai | URL chính thức để người dùng truy cập và tự nhập `user_code` |
| `verification_uri_complete` | Browser/QR/NFC, khi AS cung cấp | URL có sẵn `user_code` để giảm thao tác nhập; vẫn cần xác nhận đúng thiết bị |
| `expires_in` | Thiết bị | Khoảng hiệu lực của device authorization session, tính theo giây |
| `interval` | Thiết bị | Khoảng polling tối thiểu, tính theo giây; nếu thiếu, RFC 8628 mặc định 5 giây |

**Điểm quan trọng:** `user_code` có entropy thấp hơn `device_code` vì người dùng phải nhập được. Do đó AS phải áp dụng rate limit, chống đoán mã, giới hạn thời hạn và đánh giá rủi ro phishing. **Không dùng `user_code` để thiết bị tự đổi token tại `/oauth2/token`.** Chỉ `device_code` có vai trò đó theo Device Grant.

### 3.1. Vì sao có hai mã?

~~~mermaid
flowchart LR
    D["TV / Device"]
    A["Authorization Server"]
    H["Điện thoại / browser"]
    U["Người dùng"]
    T["Token endpoint"]

    D -->|"Xin phiên device authorization"| A
    A -->|"device_code (giữ nội bộ)<br/>user_code + verification_uri (hiển thị)"| D
    U -->|"Nhập user_code hoặc quét QR"| H
    H -->|"Đăng nhập, kiểm tra, consent"| A
    D -->|"Poll bằng device_code"| T
    T -->|"Tra trạng thái grant tại AS"| A
~~~

Mã do người dùng thấy **chỉ có tác dụng xác định yêu cầu thiết bị chờ phê duyệt**. AS còn phải kiểm tra Resource Owner đã được xác thực, session còn hạn, client hợp lệ, scope không vượt quyền và yêu cầu không bị sử dụng lại.

## 4. Tổng quan trình tự đăng nhập, consent và ra quyết định

~~~mermaid
sequenceDiagram
    autonumber
    participant TV as TV / OAuth2 Client
    participant AS as Authorization Server
    participant DB as Authorization Store
    actor U as Resource Owner
    participant P as Browser trên điện thoại

    TV->>AS: POST /oauth2/device_authorization<br/>client_id + scope
    AS->>DB: Tạo device session PENDING
    AS-->>TV: device_code, user_code, verification_uri, interval, expires_in
    TV->>TV: Hiển thị URL và user_code
    TV->>AS: POST /oauth2/token<br/>grant_type=device_code + device_code + client_id
    AS-->>TV: authorization_pending
    U->>P: Mở verification_uri / quét QR
    P->>AS: GET /oauth2/device_verification
    opt Người dùng chưa đăng nhập
        AS-->>P: Chuyển tới /login
        U->>P: Đăng nhập, MFA nếu chính sách yêu cầu
        P->>AS: Tiếp tục device verification
    end
    U->>P: Nhập/xác nhận user_code
    P->>AS: Submit user_code
    AS->>DB: Tra session và client/scopes được yêu cầu
    AS-->>P: Hiển thị tên ứng dụng, quyền và mã để đối chiếu
    alt Phê duyệt
        U->>P: Chấp thuận scopes
        P->>AS: POST consent hợp lệ
        AS->>DB: Ghi trạng thái APPROVED / authorized scopes
        AS-->>P: Đã chấp thuận, hãy quay lại TV
        TV->>AS: Poll tiếp theo bằng device_code
        AS-->>TV: Access token (+ refresh token nếu chính sách cho phép)
    else Từ chối
        U->>P: Chọn Từ chối
        P->>AS: Gửi quyết định từ chối hợp lệ
        AS->>DB: Ghi DENIED / vô hiệu hóa quyền nhận token
        AS-->>P: Yêu cầu đã bị từ chối
        TV->>AS: Poll tiếp theo bằng device_code
        AS-->>TV: access_denied
    end
~~~

Sơ đồ là **mô hình giao thức và trạng thái mong muốn**. Tên trạng thái `PENDING`, `APPROVED`, `DENIED` chỉ mang tính mô hình hóa; chúng **không phải các giá trị enum bắt buộc có sẵn** trong mọi phiên bản Spring Authorization Server. Nếu tự phát triển luồng từ chối, phải bảo đảm provider và token endpoint thực sự cùng hiểu trạng thái từ chối.

### 4.1. Các trạng thái cần phân biệt

| Trạng thái logic | Người dùng/browser | Thiết bị polling |
| --- | --- | --- |
| **Pending** | Chưa nhập user code, chưa login hoặc chưa quyết định | `authorization_pending` |
| **Code invalid/expired** | Màn hình báo mã không tồn tại/hết hạn, cho nhập mã khác | `expired_token` nếu device code hết hạn |
| **Authenticated, chưa consent** | Đã đăng nhập nhưng phải xem và quyết định phạm vi quyền | Vẫn `authorization_pending` |
| **Approved** | Hiển thị hoàn tất, yêu cầu quay lại thiết bị | Lần polling hợp lệ có thể nhận token |
| **Denied** | Hiển thị đã từ chối, không tự cấp quyền | `access_denied`, client phải dừng polling |
| **Rate limited / polled too fast** | Không liên quan trực tiếp tới browser | `slow_down`; tăng khoảng polling |

Một người chỉ mới xác thực thành công ở trang login **không đủ** để đổi trạng thái thành Approved.

## 5. Bước 1 — Thiết bị tạo yêu cầu device authorization

### 5.1. RegisteredClient cần cho phép device grant

Trong Spring Authorization Server 1.x, một public client dành cho TV có thể được đăng ký với grant type `DEVICE_CODE`.

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

public final class DeviceClientFactory {

    private DeviceClientFactory() {}

    public static RegisteredClient bookingTv() {
        return RegisteredClient.withId("booking-tv-registration-id")
            .clientId("booking-tv")
            .clientName("Booking TV")
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.DEVICE_CODE)
            .scope("booking.read")
            .scope("profile")
            .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .build())
            .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
            .build();
    }
}
~~~

Đây là **mảnh mã minh họa registration**, chưa tạo toàn bộ AS. Cần lưu client qua `RegisteredClientRepository` thích hợp và thiết lập các service khác. Với public client, `client_id` là định danh công khai, **không chứng minh danh tính hoặc mức tin cậy của một TV vật lý**. Các client secret không nên nhúng vào firmware/app không bảo vệ được.

Đăng ký `requireAuthorizationConsent(true)` giúp diễn đạt chính sách yêu cầu user chấp thuận theo cơ chế AS. Tuy nhiên, muốn bảo đảm **mọi lần cấp cho từng thiết bị đều đòi xác nhận đúng thiết bị** thì phải đối chiếu hành vi consent được lưu, client policy và yêu cầu bảo mật. **Consent đã lưu cho cùng client/user không nhất thiết là bằng chứng người dùng nhận ra chiếc TV cụ thể đang xin quyền.**

### 5.2. Request tới device authorization endpoint

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=booking-tv&scope=booking.read%20profile
~~~

Với public client, AS nhận diện client thông qua `client_id` và các quy tắc registration. Với confidential client, phương thức client authentication phải đúng cơ chế được đăng ký. AS kiểm tra client có được dùng device authorization grant và các scope có hợp lệ hay không, rồi tạo một device session.

Device Authorization Endpoint **không phải** nơi người dùng nhập mật khẩu hoặc consent. Từ request đầu tiên này, AS chưa biết Resource Owner nào sẽ phê duyệt yêu cầu.

### 5.3. Thiết bị nên hiển thị gì?

Một màn hình phù hợp có thể viết:

> Trên điện thoại hoặc máy tính, truy cập **https://auth.example.test/oauth2/device_verification**.  
> Nhập mã: **WDJB-MJHT**.  
> Chỉ tiếp tục nếu bạn đang đăng nhập cho chiếc TV này. Mã hết hạn sau ít phút.

Màn hình thiết bị có thể cho quét QR dẫn đến `verification_uri_complete`, nhưng **vẫn hiển thị `user_code` ở dạng chữ** để người dùng đối chiếu trên browser. Không hiển thị `device_code` vì đó là credential dành cho polling. Không chuyển `device_code` vào URL hoặc QR.

## 6. Bước 2 — Người dùng mở verification URI và đăng nhập

Người dùng chuyển sang điện thoại, **trực tiếp mở URL chính thức của AS** bằng HTTPS. Nếu chưa đăng nhập, Spring Security yêu cầu xác thực Resource Owner.

### 6.1. Vai trò của login entry point

Authorization Server có thể sử dụng hai filter chain:

1. Chain OAuth2/OIDC chuyên xử lý các endpoint device authorization, device verification và token.
2. Chain ứng dụng quản lý form login, trang HTML bổ sung, session và yêu cầu xác thực của browser.

Request tới `/oauth2/device_verification` cần **người dùng thực** đã đăng nhập trước khi hoàn thành xác minh/consent. Nếu Spring Security chuyển hướng sang `/login`, phải đảm bảo:

- `GET /login` có thể truy cập khi anonymous.
- `POST /login` kiểm tra username/password/MFA theo policy.
- CSRF của form login không bị vô hiệu tùy tiện.
- `SecurityContext` và session được lưu để browser quay lại device verification.
- Mã đang xác minh hoặc request được lưu/khôi phục đúng khi login hoàn tất.
- Nếu người dùng đăng nhập nhầm tài khoản, UI phải thể hiện tài khoản hiện tại và cho phép dừng/chuyển tài khoản phù hợp.

**Không bao giờ nhận password ở TV rồi gửi trực tiếp về AS dưới danh nghĩa “device consent”.** Mục đích device grant là chuyển việc đăng nhập người dùng tới một browser đáng tin cậy hơn trên thiết bị khác.

### 6.2. Ví dụ cấu hình Spring Security cho user interaction

Ví dụ cho nhánh Spring Authorization Server 1.x, tập trung vào device endpoint và form login:

~~~java
@Configuration
public class DeviceFlowSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .deviceAuthorizationEndpoint(Customizer.withDefaults())
                .deviceVerificationEndpoint(verification -> verification
                    .consentPage("/device/consent"))
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Các import tiêu biểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
~~~

**Giới hạn quan trọng:** đây là **mảnh cấu hình** cho ứng dụng đã cung cấp `RegisteredClientRepository`, `OAuth2AuthorizationService`, các khóa và bean cần thiết cho AS, user authentication và session. `consentPage("/device/consent")` **chỉ trỏ đến giao diện do ứng dụng tự tạo**, không tự cung cấp controller và template.

Đường dẫn device mặc định từ `AuthorizationServerSettings` thường là:

~~~text
POST /oauth2/device_authorization   - thiết bị xin mã
GET/POST /oauth2/device_verification - xác minh user code / consent theo flow
POST /oauth2/token                   - thiết bị polling đổi device code
~~~

Nếu ứng dụng dùng custom settings, cần lấy path thực tế từ `AuthorizationServerSettings` thay vì hardcode `/oauth2/device_verification` ở giao diện. **Không đổi URL hiển thị trên TV mà bỏ qua cấu hình `verification_uri` và endpoint matcher.**

Một số major/version cấu hình device endpoints theo cách bật/tắt khác nhau; hãy khởi động ứng dụng và xác minh thực tế endpoint hoạt động thay vì suy từ tên method. Đường dẫn và behavior nêu trên được đối chiếu từ tài liệu Spring Authorization Server. <https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html>

## 7. Bước 3 — Nhập hoặc xác nhận user_code

### 7.1. Người dùng mở trang verification

Khi browser mở `verification_uri`, AS phải cung cấp cách nhận diện device session. Trong trường hợp nhập tay, người dùng nhập `user_code`. Nếu dùng `verification_uri_complete` hoặc QR, mã có thể được điền sẵn, nhưng **UI vẫn nên hiển thị mã và yêu cầu đối chiếu với mã trên TV**.

Mục tiêu của bước này:

1. Tìm đúng device authorization session đã được khởi tạo.
2. Xác minh session còn hạn và chưa hoàn tất/từ chối.
3. Liên kết session đang chờ với Resource Owner được xác thực.
4. Lấy client registration và phạm vi quyền đã yêu cầu để tạo màn consent.
5. **Chưa cấp token** chỉ vì user nhập được mã.

### 7.2. Mã sai, hết hạn hoặc đã xử lý

Với `user_code` không tồn tại, hết hạn hoặc đã dùng:

- Hiển thị lỗi không làm lộ thông tin về tài khoản khác.
- Cho người dùng kiểm tra mã trên TV hoặc bắt đầu lại ở thiết bị.
- Không tiếp tục consent cho một session không xác định.
- Không đưa `user_code` vào log/tracing dưới dạng plaintext nếu không thực sự cần.
- Có rate limiting/captcha/risk-based controls phù hợp để ngăn brute-force mã ngắn.
- Không cho lặp lại phê duyệt một session đã hoàn tất.

### 7.3. Mã không phải bằng chứng người đang có TV

Đây là điểm bảo mật quan trọng: user_code ngắn có thể bị một kẻ tấn công gửi qua email hoặc chat. Người dùng có thể nhập mã của **thiết bị do attacker kiểm soát** mà tưởng đang giúp đăng nhập cho TV của mình.

Vì vậy, chỉ khi user code đúng chưa đủ. Màn hình consent phải nói rõ:

- Ứng dụng hoặc client nào đang yêu cầu.
- Các quyền cụ thể được xin.
- Mã phải **khớp mã đang hiển thị trên thiết bị mà người dùng thực sự sở hữu/đang cấu hình**.
- Người dùng chỉ được phê duyệt nếu **chính họ vừa bắt đầu** quá trình ghép nối.
- Có lựa chọn **Từ chối** dễ thấy khi không nhận ra thiết bị.

Đối với những thiết bị/cơ chế hỗ trợ nhận diện có kiểm chứng, có thể hiển thị thông tin thiết bị đã được AS xác thực. **Không tin một chuỗi “TV của tôi” do client tùy ý gửi là danh tính phần cứng đã được xác minh.**

## 8. Bước 4 — Hiển thị consent và scope theo đúng client

Consent trả lời câu hỏi: **Resource Owner có chấp nhận cho client dùng những quyền nào không?**

Giả sử `booking-tv` xin:

~~~text
client_id: booking-tv
client_name: Booking TV
requested_scopes:
  - booking.read
  - profile
user_code: WDJB-MJHT
~~~

Trang consent nên hiển thị quyền bằng ngôn ngữ người dùng hiểu:

| Scope kỹ thuật | Mô tả có thể hiển thị |
| --- | --- |
| `booking.read` | Xem các đặt phòng mà tài khoản của bạn được phép truy cập |
| `profile` | Xem thông tin hồ sơ cơ bản theo chính sách |
| `booking.write` | Tạo hoặc chỉnh sửa đặt phòng — **không hiển thị nếu client không yêu cầu/không được phép** |

**Consent không thay quyền nghiệp vụ.** Ngay cả khi Lan đồng ý `booking.read`, Resource Server vẫn phải kiểm tra quyền trên từng booking/tenant. Không suy từ một scope được chấp thuận rằng TV có thể đọc mọi dữ liệu đặt phòng của mọi tài khoản.

### 8.1. Nguồn dữ liệu đáng tin cho màn consent

Một trang consent **không được tin hoàn toàn** `client_id`, `scope` và `user_code` trong query string do browser mang tới. Quy trình an toàn là:

1. Tìm `RegisteredClient` từ repository, không lấy tên ứng dụng tùy ý từ query.
2. Xác định device session đang chờ theo mã, trạng thái và phiên người dùng phù hợp.
3. So sánh scopes yêu cầu với scopes đăng ký và trạng thái authorization được AS lưu.
4. Chỉ hiển thị các scope có thể phê duyệt và mô tả do server kiểm soát.
5. Khi POST consent, **provider của AS kiểm tra lại trên server**; việc HTML có hidden fields không phải bảo vệ bảo mật.

Các đối tượng liên quan là `OAuth2Authorization`, `OAuth2AuthorizationConsent` và các service lưu chúng; không thể chỉ dùng `SecurityContextHolder` để thay thế trạng thái device session.

### 8.2. Consent có thể là tất cả hoặc một phần

Theo OAuth2, AS có thể cho phép Resource Owner chấp thuận một **tập con** các scope được yêu cầu. Nếu client yêu cầu `booking.read profile` và user chỉ chấp thuận `booking.read` thì token được cấp không được chứa `profile` trái ý user. Tuy nhiên, khả năng consent một phần và các scope bắt buộc phụ thuộc chính sách provider/client/version; phải kiểm thử hành vi thực tế.

**Không suy ra rằng bỏ trống checkbox là cách từ chối toàn bộ grant được mọi phiên bản hỗ trợ giống nhau.** Nếu muốn một hành động “Từ chối” có thể kiểm thử chắc chắn, thiết kế riêng một nhánh từ chối đúng giao thức như mục 10.

## 9. Trang consent tùy biến với Spring Authorization Server

### 9.1. Configurer dành riêng cho device verification

Spring Authorization Server có hai configurer khác nhau:

| Configurer | Endpoint | Vai trò |
| --- | --- | --- |
| `OAuth2DeviceAuthorizationEndpointConfigurer` | `/oauth2/device_authorization` | Nhận request từ thiết bị, cấp `device_code`/`user_code`, xác định `verification_uri` |
| `OAuth2DeviceVerificationEndpointConfigurer` | `/oauth2/device_verification` | Xác minh mã user, xử lý consent và tương tác browser |
| `OAuth2TokenEndpointConfigurer` | `/oauth2/token` | Xử lý device code polling và phát token/lỗi |

Ở device verification, Spring Authorization Server cung cấp các extension point như:

- `deviceVerificationRequestConverter(...)` / `deviceVerificationRequestConverters(...)`.
- `authenticationProvider(...)` / `authenticationProviders(...)`.
- `deviceVerificationResponseHandler(...)`.
- `errorResponseHandler(...)`.
- `consentPage(...)`.

Provider mặc định ở nhánh SAS 1.x có các lớp liên quan `OAuth2DeviceVerificationAuthenticationProvider` và `OAuth2DeviceAuthorizationConsentAuthenticationProvider`. Việc bổ sung custom provider phải không được bỏ các kiểm tra chuẩn về user code, client, user authentication, scope, consent state và code lifetime.

### 9.2. Những tham số của custom consent page

Theo API `OAuth2DeviceVerificationEndpointConfigurer.consentPage(...)`, khi redirect tới custom consent page, các tham số đáng chú ý gồm:

- `client_id` — client identifier.
- `scope` — danh sách scope, phân tách bằng khoảng trắng.
- `state` — token tương quan/chống CSRF của **luồng device consent**.
- `user_code` — mã user gắn device session.

Form consent cần **POST đến `AuthorizationServerSettings.getDeviceVerificationEndpoint()`**, kèm `client_id`, `state`, `user_code` và các `scope` được chấp thuận. Đây là điểm khác biệt đáng nhớ so với form consent của Authorization Code Grant thông thường, vốn POST tới authorization endpoint. <https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2DeviceVerificationEndpointConfigurer.html>

### 9.3. Ví dụ controller hiển thị consent

Giả định ứng dụng dùng Spring MVC và Thymeleaf. Đường dẫn trang custom `/device/consent` được xử lý bởi application/login chain, còn POST gửi về AS device verification endpoint:

~~~java
@Controller
public class DeviceConsentPageController {

    private final RegisteredClientRepository clients;

    public DeviceConsentPageController(RegisteredClientRepository clients) {
        this.clients = clients;
    }

    @GetMapping("/device/consent")
    String showConsent(
            @RequestParam("client_id") String clientId,
            @RequestParam("scope") String scope,
            @RequestParam("state") String state,
            @RequestParam("user_code") String userCode,
            Model model,
            Authentication authentication) {

        if (authentication == null
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        RegisteredClient client = clients.findByClientId(clientId);
        if (client == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Set<String> requestedScopes = Arrays.stream(scope.split(" "))
            .filter(value -> !value.isBlank())
            .collect(Collectors.toCollection(LinkedHashSet::new));

        if (!client.getScopes().containsAll(requestedScopes)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        model.addAttribute("clientId", client.getClientId());
        model.addAttribute("clientName", client.getClientName());
        model.addAttribute("state", state);
        model.addAttribute("userCode", userCode);
        model.addAttribute("scopes", requestedScopes);
        return "device-consent";
    }
}
~~~

Các import cần bổ sung từ Java/Spring gồm `Arrays`, `Set`, `LinkedHashSet`, `Collectors`, `Model`, `RegisteredClientRepository`, `RegisteredClient`, `Authentication`, `AnonymousAuthenticationToken`, `ResponseStatusException`, `HttpStatus` và các annotation MVC.

**Điểm giới hạn:** đoạn này chỉ là **lớp dựng giao diện**. Kiểm tra client và scope từ query không đủ để chứng minh `user_code` và `state` gắn đúng với **pending authorization trong store**. Phải để provider mặc định của AS xác minh POST hoặc xây thêm service đọc/đối chiếu pending session an toàn trước khi hiển thị thông tin nhạy cảm. Không biến controller UI thành nơi tự thay provider cấp token.

Trong production, nên kiểm tra `user_code` thuộc một session còn hạn và chưa hoàn tất, ràng buộc đúng client, thông tin device đã được xác minh nếu có và account đang đăng nhập. Việc dùng `AnonymousAuthenticationToken` trong ví dụ chỉ hỗ trợ kiểm tra sơ bộ; chính sách xác thực chuẩn nên được áp bằng filter chain.

### 9.4. Ví dụ template Thymeleaf cho nút “Phê duyệt”

~~~html
<h1>Cho phép thiết bị truy cập?</h1>

<p>
  Ứng dụng: <strong th:text="${clientName}">Booking TV</strong>
</p>

<p>
  Mã thiết bị: <strong th:text="${userCode}">WDJB-MJHT</strong>
</p>

<p>Chỉ tiếp tục khi mã này trùng với mã trên TV do bạn đang thiết lập.</p>

<form method="post" th:action="@{/oauth2/device_verification}">
  <input type="hidden" name="client_id" th:value="${clientId}">
  <input type="hidden" name="state" th:value="${state}">
  <input type="hidden" name="user_code" th:value="${userCode}">

  <div th:each="scopeValue : ${scopes}">
    <label>
      <input type="checkbox" name="scope" th:value="${scopeValue}">
      <span th:text="${scopeValue}">Quyền truy cập</span>
    </label>
  </div>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Phê duyệt các quyền đã chọn</button>
</form>
~~~

**Giả định của mẫu:** `AuthorizationServerSettings.getDeviceVerificationEndpoint()` đang là giá trị mặc định `/oauth2/device_verification`. Nếu thay đổi endpoint, phải đưa URI tương ứng từ cấu hình đáng tin cậy vào model thay vì hardcode action. Các giá trị request phải được output-escaped; template engine giải mã đúng các biểu thức `th:text`/`th:value`.

Với một số giao diện, “không chọn scope nào” có thể biểu thị từ chối hoặc phát sinh lỗi, tùy provider/version. Không dùng hành vi này làm contract bảo mật khi chưa kiểm chứng. Hãy thiết kế **nút từ chối rõ ràng** và kiểm thử kết quả như mục 10.

### 9.5. `state` của consent khác những giá trị dễ nhầm

| Giá trị | Dùng vào việc gì? |
| --- | --- |
| `user_code` | Người dùng nhận diện device session chờ xác minh |
| `device_code` | Thiết bị polling token endpoint; **không nằm trong HTML consent form** |
| `state` của device consent | Correlation/CSRF protection của tương tác consent do AS quản lý |
| `_csrf` của Spring Security | Bảo vệ HTTP form POST theo cơ chế CSRF đã cấu hình |
| `state` của Authorization Code Grant | Client ghép callback với authorization request thông thường |

Không tự tạo giá trị `state` mới khi render consent. Cũng không thay `state` bằng `user_code` hay `_csrf`. Mỗi giá trị có nguồn và mục đích riêng.

## 10. Phê duyệt và từ chối: hai quyết định phải có kết quả giao thức

### 10.1. Khi người dùng phê duyệt

Tại POST consent, AS phải kiểm tra:

1. Browser có Resource Owner đã xác thực; có chính sách re-authentication/MFA bổ sung nếu yêu cầu.
2. `state` và `user_code` đúng pending device session và chưa bị sử dụng.
3. Session chưa hết hạn và client ID của form khớp authorization đang chờ.
4. Các scope chấp thuận nằm trong phạm vi đã yêu cầu, registration và chính sách của client.
5. User chưa bị vô hiệu hóa hoặc mất điều kiện cấp quyền theo chính sách hiện hành.
6. Trạng thái phê duyệt được cập nhật bền vững, không cho cùng yêu cầu bị xử lý như mới lần nữa.

Sau phê duyệt, browser hiển thị thông báo kiểu:

> **Thiết bị đã được phê duyệt.** Hãy trở lại TV để hoàn tất đăng nhập. Nếu đây không phải thiết bị của bạn, hãy thu hồi quyền truy cập trong phần quản lý thiết bị.

TV **không tự nhận token qua browser**. Nó nhận token khi polling `/oauth2/token` lần tiếp theo hợp lệ, sau khi AS xác định phiên đã được phê duyệt.

### 10.2. Khi người dùng từ chối

Một thao tác từ chối đúng nghĩa phải làm:

1. Xác minh **ai** đang từ chối và **yêu cầu nào** đang được từ chối.
2. Xác định `user_code`, client, state và pending authorization tương ứng.
3. Ghi nhận quyết định từ chối hoặc vô hiệu hóa session theo mô hình AS, sao cho **token endpoint không thể phát token** từ `device_code` đó.
4. Phản hồi trên browser rằng yêu cầu đã bị từ chối.
5. Khi thiết bị polling, AS trả lỗi `access_denied` theo RFC 8628, nếu implementation lưu trạng thái denial như vậy.
6. Thiết bị phải dừng polling và hướng dẫn người dùng bắt đầu yêu cầu mới nếu muốn.

**Đóng trình duyệt, bấm Back hoặc không chọn checkbox nào không bảo đảm token endpoint sẽ nhận biết “từ chối”.** Nếu user không thao tác gì, yêu cầu thường vẫn pending rồi hết hạn; đây là trạng thái khác với explicit denial.

### 10.3. Đừng tự gán trạng thái DENIED bằng cách xóa record bừa bãi

Mẫu xử lý khái niệm:

~~~text
POST /device/deny   (endpoint tùy biến, không phải endpoint RFC 8628 chuẩn)
  1. Kiểm tra user authentication, CSRF và authorization của browser.
  2. Tìm đúng pending device session theo server-side state + user_code.
  3. Xác minh client, scope, thời hạn và quyền ra quyết định.
  4. Ghi DENIED atomically; revoke/invalidate grant theo mô hình của AS.
  5. Bảo đảm device-code token provider trả access_denied khi poll.
  6. Render trang từ chối an toàn.
~~~

Đây là **hợp đồng thiết kế**, không phải đoạn mã có thể sao chép chạy trực tiếp. Spring Authorization Server 1.x có provider/handler cho device verification và consent, nhưng **không nên mặc định giả định một endpoint `/device/deny` được tạo sẵn hoặc cứ xóa `OAuth2Authorization` là polling sẽ trả `access_denied`**. Nếu xóa record, token endpoint có thể coi mã không tồn tại/hết hạn và trả mã lỗi khác.

Đội phát triển cần lựa chọn một trong hai cách có kiểm chứng trên đúng version:

- Dùng **nhánh từ chối đã được framework hỗ trợ** theo behavior của phiên bản đang chạy, xác minh bằng integration test rằng polling trả `access_denied`.
- Hoặc bổ sung provider/handler cùng một mô hình trạng thái từ chối trong authorization store để token endpoint hiểu quyết định DENIED mà không bypass validation mặc định.

Khi tự bổ sung handler, ưu tiên giữ nguyên các provider mặc định và mở rộng có kiểm soát thay vì thay toàn bộ token endpoint. Không để user có thể gửi một mã của thiết bị khác để từ chối/cho phép thay người sở hữu.

### 10.4. Giao diện từ chối nên rõ ràng

Nút “Từ chối” nên hiển thị cùng màn consent và yêu cầu user xác nhận, nhưng không để nó **gửi cùng form approve kèm các scope đã chọn**. Nếu ứng dụng triển khai endpoint từ chối riêng thì cần form POST riêng, có CSRF, user code và correlation state được AS xác minh. Không dùng GET `/device/deny?user_code=...` để thay đổi trạng thái.

Sau từ chối, AS không phát code/token; thiết bị có thể hiển thị:

> Yêu cầu đăng nhập trên thiết bị đã bị từ chối. Bạn có thể thử lại bằng mã mới nếu chính bạn muốn kết nối.

Không tiết lộ tên user, email hoặc grant detail của người từ chối cho TV ngoài mức cần thiết, vì TV hoặc client có thể do người khác kiểm soát.

## 11. Polling tại token endpoint phản ánh quyết định ra sao?

Thiết bị gọi:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=DEVICE_CODE_FROM_RESPONSE&client_id=booking-tv
~~~

Với confidential client cần thêm client authentication theo registration. `client_id` của public client không phải bí mật; token endpoint phải kiểm tra `device_code` gắn đúng client và trạng thái authorization.

### 11.1. Các phản hồi chuẩn của RFC 8628

| Phản hồi ở token endpoint | Ý nghĩa | Thiết bị cần làm |
| --- | --- | --- |
| `authorization_pending` | User chưa hoàn tất tương tác | Tiếp tục polling sau ít nhất khoảng `interval` |
| `slow_down` | Đang polling quá nhanh | **Tăng khoảng polling thêm 5 giây** cho những lần tiếp theo |
| `access_denied` | Resource Owner đã từ chối yêu cầu | **Dừng polling** và thông báo phù hợp |
| `expired_token` | Device authorization session đã hết hạn | **Dừng polling**, chỉ tạo phiên mới khi người dùng có chủ đích |
| HTTP thành công có `access_token` | AS xác nhận grant đã đủ điều kiện | Lưu token an toàn, gọi RS theo scope/audience |
| `invalid_client` hoặc lỗi không phục hồi khác | Client hoặc request không hợp lệ | Dừng, xử lý lỗi cấu hình và không spam AS |

Nếu response ban đầu không có `interval`, thiết bị mặc định chờ **5 giây** giữa những lần polling. Khi gặp `slow_down`, phải tăng thêm 5 giây cho các lần kế tiếp. Nếu gặp timeout kết nối, RFC khuyến nghị backoff để giảm áp lực lên AS. Các lỗi khác ngoài những tình huống cho phép tiếp tục polling phải dừng theo giao thức. <https://www.rfc-editor.org/rfc/rfc8628#section-3.5>

### 11.2. Ví dụ response khi user chưa quyết định

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "authorization_pending"
}
~~~

Không coi HTTP 400 này là “thiết bị đăng nhập thất bại vĩnh viễn”. Đó là tín hiệu đúng của Device Grant trước khi user phê duyệt/từ chối.

### 11.3. Ví dụ response sau explicit denial

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "access_denied"
}
~~~

Sau response này, client không được tiếp tục polling mã cũ. Nếu chỉ tắt màn hình chờ nhưng vẫn gửi request ngầm, bạn đã vi phạm semantics và có nguy cơ tạo tải không cần thiết.

### 11.4. Khác biệt giữa Denied và Expired

- **Denied:** người dùng chủ động từ chối, và AS ghi nhận được trạng thái đó.
- **Expired:** hết `expires_in` mà chưa có quyết định hợp lệ, hoặc session được kết thúc do chính sách hết hạn.
- **Invalid code:** request dùng mã sai hoặc mã không thuộc client; response cụ thể phụ thuộc provider/RFC và tình trạng code.

Không ghi nhận `access_denied` chỉ vì một browser session tự đóng khi người dùng chưa chọn gì. Không cấp token từ mã đã hết hạn dù user vừa bấm phê duyệt sau đó.

## 12. Bảo mật đặc thù: remote phishing và xác minh sở hữu thiết bị

Device flow có bề mặt rủi ro khác Authorization Code + PKCE: người dùng chấp thuận trên **một thiết bị khác** so với thiết bị đang xin token. Các tín hiệu từ điện thoại dùng để approve không mặc nhiên chứng minh TV thật đang ở cạnh người dùng.

### 12.1. Ví dụ tấn công remote phishing

Kẻ tấn công chạy một client/device do mình kiểm soát, xin `user_code`, rồi nhắn người dùng:

> “Tài khoản của bạn cần xác minh. Vào auth.example.test/device và nhập mã ABCD-EFGH.”

Nếu người dùng làm theo và phê duyệt, token có thể được cấp **cho thiết bị của attacker**, không phải TV của người dùng. Hành vi này có thể xảy ra dù URL xác minh là domain AS thật.

**Biện pháp cốt lõi:** UI phải nhắc “Chỉ phê duyệt nếu bạn đang tự đăng nhập trên thiết bị ngay trước mặt”. Hiển thị user code, tên ứng dụng/client và phạm vi quyền; nếu có thông tin thiết bị đã được xác minh thì hiển thị thêm. Nên có nút từ chối dễ nhận thấy.

### 12.2. QR không tự làm flow an toàn hơn

`verification_uri_complete`/QR giảm thao tác nhập mã, nhưng **khi không phải gõ user code**, nguy cơ user phê duyệt một QR do attacker gửi có thể tăng. Vì vậy AS vẫn nên hiển thị mã và yêu cầu so với mã đang xuất hiện trên thiết bị.

Không tự động chấp thuận ngay khi quét QR hoặc mở deeplink. Người dùng phải có cơ hội đọc và đưa ra lựa chọn.

### 12.3. Rate limiting và chống đoán user_code

Vì user code ngắn để dễ nhập, AS cần:

- Tạo mã đủ entropy so với số lần thử dự kiến.
- Giới hạn số lần thử theo tài khoản, IP, session, mã và tín hiệu rủi ro phù hợp.
- TTL ngắn nhưng đủ cho người dùng mở browser, đăng nhập/MFA và ra quyết định.
- Không tiết lộ danh tính user hoặc client nhạy cảm khi mã sai.
- Cân nhắc khóa/throttle những phiên bị thử liên tục mà không làm DoS hàng loạt người dùng.
- Không tái sử dụng mã đã hoàn tất trong khoảng còn gây nhầm lẫn, theo chiến lược an toàn của AS.

Với `device_code`, cần entropy rất cao vì nó đóng vai trò credential dành cho token endpoint. Với `user_code`, cần thiết kế kết hợp entropy, time limit và rate limit. RFC 8628 trình bày những rủi ro này tại mục Security Considerations. <https://www.rfc-editor.org/rfc/rfc8628#section-5>

### 12.4. Step-up/MFA cho thiết bị nhạy cảm

Nếu TV có thể xem dữ liệu nhạy cảm hoặc thiết bị truy cập kho tài liệu nội bộ, AS có thể yêu cầu MFA hoặc bước xác minh bổ sung **trước khi phê duyệt**. Phải lưu/đánh giá assurance context theo chính sách và không cho endpoint consent tự bypass bước này.

Một thông báo “đã xác thực” từ session cũ không tự chứng minh người dùng vừa đáp ứng mức assurance được yêu cầu cho một thiết bị mới.

## 13. Session, CSRF và kho lưu authorization

### 13.1. Browser login cần session/CSRF phù hợp

Ở thiết bị thứ hai:

- Form login và POST consent có thể dựa vào session/cookie.
- CSRF protection phải được thiết kế đúng cho các request thay đổi trạng thái.
- Session phải giữ được principal qua redirect login/verification/consent.
- Đổi tài khoản hoặc logout giữa các bước phải làm mất khả năng approve với session không phù hợp.
- Cookie phải có chính sách `Secure`, `HttpOnly` và `SameSite` phù hợp, sử dụng HTTPS.
- Request cache/success handler phải quay lại đúng pending verification khi người dùng đăng nhập thành công.

**Không tắt CSRF toàn bộ Authorization Server** chỉ vì form consent POST trả 403. Thay vào đó, kiểm tra token của form, session, matcher, callback và chính sách endpoint cụ thể.

### 13.2. Authorization store cần bền vững khi có nhiều AS instance

~~~mermaid
flowchart TD
    TV["TV yêu cầu code / polling"]
    A["AS instance A"]
    B["AS instance B"]
    PHONE["Browser phê duyệt"]
    STORE[("Authorization / Consent Store<br/>chia sẻ nhất quán")]

    TV --> A
    TV --> B
    PHONE --> B
    A <--> STORE
    B <--> STORE
~~~

Có thể xảy ra:

1. Thiết bị lấy device code từ AS instance A.
2. Browser điện thoại mở verification URI và tới instance B.
3. Browser phê duyệt tại B.
4. TV poll lại tới A.

Nếu các instance chỉ dùng `InMemoryOAuth2AuthorizationService` riêng, A có thể không nhìn thấy quyết định ở B. Cần kho lưu/thiết kế phân phối có tính bền và nhất quán, ví dụ JDBC theo tài liệu Spring Authorization Server, và test multi-instance/rolling deployment.

### 13.3. Phê duyệt và polling đồng thời

Khi user nhấn Approve trùng thời điểm TV poll:

- Provider polling có thể trả `authorization_pending` nếu transaction chấp thuận chưa commit.
- Lần poll tiếp theo có thể thành công khi state đã được commit.
- Không được cấp token nếu consent transaction thất bại hoặc bị rollback.
- Khi một yêu cầu đồng thời bị từ chối và chấp thuận, phải xác định quy tắc **một quyết định cuối cùng**; không được để cả hai cùng có hiệu lực.
- Sau khi token đã phát, cần chính sách có thể kiểm tra lại quyền/thu hồi nếu user thao tác từ chối gần như đồng thời.

Với sản phẩm production cần test race condition và transaction/locking trên authorization store thật, không chỉ MockMvc một thread.

## 14. Kiểm thử đăng nhập, consent, approve và deny

### 14.1. Ma trận test

| Ca kiểm thử | Thiết lập | Điều cần xác minh |
| --- | --- | --- |
| Device request hợp lệ | Client `booking-tv` có grant `DEVICE_CODE` | AS cấp hai mã, verification URI và thời hạn |
| Browser chưa đăng nhập | Mở verification URI | AS dẫn đến login theo chính sách |
| Login sai password | Thử xác thực | Không thể approve device session |
| Login thành công | User được xác thực | Quay lại đúng verification session |
| User code sai | Nhập mã không tồn tại | Không mở consent cho grant khác |
| User code hết hạn | Vượt `expires_in` | Không thể approve; device poll không được token |
| User code đã xử lý | Gửi lặp lại | Không cấp grant thêm lần nữa |
| QR complete URI | Browser đã có user code | Vẫn có thông tin đối chiếu mã trên TV |
| Consent toàn bộ scope | User approve các scope hợp lệ | AS ghi approved scopes và token endpoint có thể phát token |
| Consent một phần | Chỉ chọn `booking.read` | Token không chứa scope chưa được chấp thuận |
| Scope bị sửa trên form | Gửi scope không đăng ký/không yêu cầu | AS từ chối, không cấp vượt quyền |
| Client ID bị sửa | Hidden field khác registration | AS từ chối, không approve nhầm client |
| `state` bị sửa | POST với state sai | AS từ chối, không tạo approval |
| CSRF bị thiếu | POST consent | Bị chặn theo chính sách |
| Bấm Từ chối | Deny hợp lệ theo implementation | Browser báo từ chối, polling trả `access_denied` |
| Bấm Back/đóng browser | Không gửi quyết định | Vẫn pending cho tới khi timeout; không tự approved |
| Poll trước khi quyết định | Device code hợp lệ | `authorization_pending` |
| Poll quá nhanh | Vi phạm `interval` | `slow_down` theo RFC/policy |
| Poll sau thời hạn | Device code hết hạn | `expired_token` |
| Device code sai client | Public client ID khác hoặc sai client authentication | Từ chối, không phát token |
| Đăng nhập nhầm tài khoản | User session khác người dự kiến | UI làm rõ account và không tự approve |
| Hai device session trùng thời điểm | Hai user code đang pending | Không approve nhầm mã khác |
| Phê duyệt/từ chối đồng thời | Race condition | Một quyết định cuối cùng, không cấp token sai |
| AS hai instance | Yêu cầu/consent/poll đi qua hai AS | Quyết định được chia sẻ đúng |
| User bị khóa trước approve | User status thay đổi | Chính sách bảo mật được áp dụng, không cấp quyền trái phép |

### 14.2. Kiểm thử browser login

Sử dụng `spring-security-test` và MockMvc để kiểm tra trang verify yêu cầu user đã đăng nhập. Ví dụ khung:

~~~java
@Test
void deviceVerificationRequiresAuthenticatedResourceOwner()
        throws Exception {
    mockMvc.perform(get("/oauth2/device_verification")
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location", containsString("/login")));
}
~~~

Ví dụ cần được điều chỉnh theo chính sách GET endpoint và default verification page của **phiên bản đang dùng**. Nếu trang xác minh nhập user code cho phép GET anonymous rồi mới yêu cầu login tại POST, test phải phản ánh đúng thiết kế; mục tiêu bắt buộc là **không hoàn tất verification/consent khi chưa xác thực**.

### 14.3. Kiểm thử consent custom

Với custom consent page, cần có các test sau:

1. Browser đã đăng nhập, `user_code` hợp lệ, pending → hiển thị đúng tên client và scopes.
2. Trang chỉ dùng dữ liệu đăng ký/server state để xây tên và mô tả quyền; không echo HTML/JavaScript từ query.
3. Form POST gửi đúng `client_id`, `state`, `user_code`, scopes được chọn và CSRF token khi cần.
4. POST scope ngoài grant → bị từ chối.
5. POST cho một user code đã hết hạn → bị từ chối.
6. POST từ user/account không phù hợp → bị từ chối.
7. Approval thành công → cập nhật state; device poll nhận token đúng client/scopes.
8. Denial thành công → cập nhật state; device poll nhận `access_denied` và dừng.
9. Hai request thay đổi trạng thái đồng thời không thể cùng được chấp nhận.

`@WithMockUser` có thể giúp test một phần rule authorization, nhưng **không chứng minh** login, lưu session, consent provider hoặc device token polling thực sự hoạt động. Bài test end-to-end cần chạy qua filter chain và authorization store thật/fixture đáng tin.

### 14.4. Test polling không được bỏ qua RFC 8628

Một thiết bị chuẩn nên:

~~~text
Khởi tạo interval = response.interval nếu có, ngược lại 5 giây
Lặp cho tới khi thành công, bị từ chối, hết hạn hoặc lỗi terminal:
  - Chờ ít nhất interval trước khi gửi lần tiếp theo
  - authorization_pending -> giữ interval và thử lại
  - slow_down -> tăng interval thêm 5 giây, rồi thử lại
  - timeout -> backoff; không spam AS
  - access_denied / expired_token -> dừng
  - thành công -> dừng, lưu access token an toàn
  - lỗi terminal khác -> dừng và thông báo
~~~

Đây là pseudocode hành vi của **Client**, không phải bean Java trong AS. Test ở phía client cần mô phỏng clock, timeout, retry/backoff và hủy flow khi user chủ động rời màn hình.

## 15. Vận hành và chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| TV có mã nhưng URL xác minh trả 404 | Endpoint chưa bật, settings/matcher sai | Kiểm tra `AuthorizationServerSettings` và device verification configurer |
| Browser mở mã nhưng bị redirect login lặp | Trang login/verification không đúng chain hoặc session không được lưu | Kiểm tra `@Order`, security matcher, login entry point, session cookie |
| Đăng nhập xong mất user code | Request cache/redirect làm rơi correlation | Bảo toàn verification context trên server, test qua login redirect |
| Consent có sai tên client | UI tin `client_id`/tên từ query | Tra `RegisteredClientRepository`, kiểm tra pending state |
| Consent POST trả 403 | Thiếu CSRF, session hết hạn, state sai | Kiểm tra form và CSRF/session; không tắt CSRF toàn cục |
| Đã approve nhưng TV vẫn pending | Authorization store không chia sẻ hoặc transaction chưa commit | Test multi-instance/persistence, monitor cập nhật authorization |
| Bấm Deny nhưng TV vẫn pending | UI chỉ đóng trang, chưa ghi trạng thái từ chối | Triển khai/kiểm thử explicit denial đúng contract |
| Bấm Deny nhưng TV nhận `expired_token` thay `access_denied` | Record bị xóa/hết hạn thay vì ghi denial | Kiểm tra cách provider/token endpoint diễn giải trạng thái |
| TV polling liên tục rất nhanh | Không tôn trọng `interval` hoặc `slow_down` | Sửa client/backoff, rate limit |
| Mã bị đoán nhiều | Thiếu entropy/rate limiting | Throttle và security monitoring |
| Có dấu hiệu remote phishing | User bị lừa nhập mã của thiết bị attacker | Cảnh báo user, revoke token, tăng xác nhận sở hữu thiết bị |
| User đã approve nhưng API trả 403 | Scope/audience hoặc quyền trên dữ liệu không phù hợp | Kiểm tra token và chính sách RS độc lập |

### 15.1. Log gì cho đúng?

Nên có request ID, correlation ID, client ID đáng tin, loại endpoint, thời gian tạo/hết hạn, trạng thái logic và kết quả policy, sự kiện approve/deny, latency polling.

Không log raw `device_code`, full `user_code`, session cookie, access token, refresh token, client secret hoặc dữ liệu cá nhân không cần thiết. Nếu cần liên kết sự kiện của một phiên, dùng ID nội bộ dành cho audit hoặc token identifier được bảo vệ và có retention policy.

### 15.2. Theo dõi các chỉ số hữu ích

- Tỷ lệ device sessions chuyển từ pending sang approved/denied/expired.
- P50/P95 thời gian từ yêu cầu thiết bị đến lúc người dùng hoàn tất.
- Tỷ lệ user code nhập sai và số lần bị rate limit.
- Số request polling mỗi device session, tỷ lệ `slow_down`.
- Tỷ lệ token issuance thất bại sau approval.
- Sự khác biệt trạng thái giữa các AS instance.
- Sự kiện nghi ngờ remote phishing, revoke và session compromise.

Không nên tăng chi tiết logging bằng cách ghi toàn bộ mã để có chỉ số dễ hơn.

## 16. Tình huống minh họa: ghép nối TV Booking

Một người dùng mở ứng dụng Booking trên TV và chọn “Liên kết tài khoản”. TV xin `device_code` và `user_code`, hiển thị mã `WDJB-MJHT` kèm URL của AS. Lan dùng điện thoại truy cập URL và đăng nhập. AS tìm pending device session, hiển thị rằng **Booking TV** xin quyền đọc booking và hồ sơ.

**Nếu đúng là TV của Lan**, cô đối chiếu mã, chấp thuận `booking.read` nhưng có thể không đồng ý `profile` nếu policy hỗ trợ consent một phần. AS ghi kết quả và TV nhận access token sau một lần polling tiếp theo hợp lệ. Booking API vẫn kiểm tra token còn hạn, issuer, audience, scope và dữ liệu được phép xem.

**Nếu Lan không hề thao tác trên TV**, cô chọn **Từ chối**. AS ghi trạng thái từ chối và TV/thiết bị đang chờ nhận `access_denied`. Không cấp token chỉ vì Lan đã đăng nhập vào điện thoại.

**Nếu Lan đóng browser mà không chọn gì**, thiết bị vẫn pending rồi hết hạn. Đây là kết quả khác với việc chủ động từ chối; giao diện và log phải phân biệt được hai trường hợp.

## 17. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Nguyên tắc sửa |
| --- | --- | --- |
| Coi user login là approval | Phát token dù user chưa đồng ý | Chờ verification + consent/decision hợp lệ |
| Hiển thị `device_code` cho người dùng | Lộ credential của token endpoint | Chỉ hiển thị `user_code` |
| Dùng `user_code` để đổi token | Sai giao thức, tăng bề mặt tấn công | Token endpoint nhận `device_code` |
| Tự cấp token ngay khi user mở verification URI | Bỏ qua quyết định của user | Cần xác thực, đối chiếu mã và phê duyệt |
| Tin mọi query parameter của consent page | Phê duyệt nhầm client/scope | Tra registration và pending server state, validate lại khi POST |
| Quét QR là tự động chấp thuận | Dễ bị lừa remote phishing | Hiển thị mã, client, scopes và nút quyết định rõ ràng |
| “Từ chối” chỉ đóng trang | TV vẫn pending, không có decision | Ghi denial và bảo đảm polling nhận lỗi |
| Xóa authorization rồi khẳng định sẽ trả `access_denied` | Có thể nhận expired/invalid token thay vì denial | Thiết kế denial state/provider nhất quán |
| Không phân biệt `state` và `_csrf` | Lỗi CSRF/correlation, có thể cho phép POST sai | Bảo vệ đúng cả hai cơ chế |
| Consent từ browser anonymous | Người lạ có thể phê duyệt | Authentication Resource Owner bắt buộc |
| Tắt CSRF toàn ứng dụng | Làm yếu form login và consent | Bảo vệ POST theo matcher/policy |
| Không throttle user code | Brute-force user code ngắn | Entropy, TTL, rate limit |
| Không tôn trọng polling interval | Gây quá tải AS và sai RFC | Bám `interval`/`slow_down` |
| Chạy AS nhiều instance với storage in-memory riêng | Device poll không thấy approval | Authorization store chia sẻ |
| Nhận client display name do TV tự khai là thiết bị tin cậy | Giả mạo thông tin thiết bị | Phân biệt metadata đăng ký và hardware attestation |
| Bỏ kiểm tra scope ở RS | TV được xem dữ liệu vượt quyền | RS kiểm tra audience/scope/object-level permission |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao user chỉ cần mở `verification_uri` và đăng nhập chưa đủ để thiết bị nhận access token?

**Đáp án:** Login chỉ xác thực Resource Owner. AS còn phải xác minh đúng user code/device session, kiểm tra client/scopes, consent và ghi nhận quyết định phê duyệt hợp lệ.

**Câu 2.** `device_code` và `user_code` khác nhau thế nào?

**Đáp án:** `device_code` là credential entropy cao để thiết bị polling token endpoint; `user_code` là mã ngắn cho người dùng nhập/đối chiếu tại browser verification. Không tráo vai trò hai mã.

**Câu 3.** Khi quét QR có `verification_uri_complete`, user có thể bỏ kiểm tra mã trên TV không?

**Đáp án:** Không nên. AS vẫn cần cho user đối chiếu mã và xác nhận thiết bị đang thực sự được ghép nối để giảm remote phishing.

**Câu 4.** Có thể dùng `OAuth2AuthorizationEndpointConfigurer.consentPage(...)` để tùy chỉnh consent của device flow không?

**Đáp án:** Không phải điểm cấu hình đúng. Device flow dùng `OAuth2DeviceVerificationEndpointConfigurer.consentPage(...)`, và form POST tới device verification endpoint.

**Câu 5.** Form consent device flow cần những tham số nào?

**Đáp án:** Theo API SAS 1.x, tối thiểu là `client_id`, `state`, `user_code` và các `scope` đã đồng ý; cùng CSRF token nếu security policy yêu cầu. POST tới `AuthorizationServerSettings.getDeviceVerificationEndpoint()`.

**Câu 6.** User bấm “Từ chối” nhưng backend chỉ redirect đến “Đã từ chối” mà không cập nhật authorization. Đúng chưa?

**Đáp án:** Chưa. Device poll có thể tiếp tục pending rồi hết hạn. Cần một quyết định từ chối được AS ghi nhận, không thể cấp token, và kết quả token endpoint phù hợp như `access_denied`.

**Câu 7.** Khi TV nhận `authorization_pending` và `slow_down`, xử lý có giống nhau không?

**Đáp án:** Không hoàn toàn. Cả hai đều có thể tiếp tục polling, nhưng `slow_down` bắt buộc tăng khoảng chờ thêm 5 giây cho các lần tiếp theo.

**Câu 8.** Nếu browser của user và polling request đi tới hai AS instance khác nhau, vấn đề chính là gì?

**Đáp án:** Cả hai cần nhìn thấy cùng trạng thái device authorization và quyết định consent. Kho lưu tách biệt/in-memory riêng có thể dẫn đến trạng thái không nhất quán.

**Câu 9.** Sau approval, TV có thể truy cập mọi booking không?

**Đáp án:** Không. Access token chỉ chứa quyền đã được cấp theo chính sách; Resource Server phải kiểm tra token, scope, audience và quyền trên từng đối tượng dữ liệu.

## 19. Checklist trước khi đưa vào production

- [ ] Client/device được đăng ký đúng `DEVICE_CODE` grant và scope cho phép.
- [ ] Device Authorization/Verification/Token Endpoints được bật và dùng URI từ settings/metadata phù hợp.
- [ ] `device_code` có entropy cao, không hiển thị cho người dùng, không log.
- [ ] `user_code` đủ entropy và được bảo vệ bằng TTL/rate limit/chống brute-force.
- [ ] Thiết bị hiển thị URL AS chính thức và user code; QR chỉ là cách nhập thuận tiện.
- [ ] Browser verification yêu cầu user authentication và MFA/step-up theo policy.
- [ ] Consent hiển thị đúng client, scopes và mã khớp trên thiết bị.
- [ ] Form approval dùng đúng `client_id`, `state`, `user_code`, scope, CSRF token và endpoint POST.
- [ ] Tùy biến consent không bỏ qua provider/validator mặc định của Spring Authorization Server.
- [ ] Nút “Từ chối” thực sự làm grant không thể phát token và polling báo lỗi theo hợp đồng đã test.
- [ ] Phân biệt denied, pending, expired, invalid trong UI, API và audit.
- [ ] Device client tôn trọng `interval`, `slow_down`, timeout/backoff và ngừng poll sau lỗi terminal.
- [ ] Không dùng session browser của điện thoại như token của TV.
- [ ] Authorization/consent store chia sẻ và nhất quán trên nhiều AS instances.
- [ ] Có test các tình huống user code sai, scope/state bị sửa, anonymous, expired, approve/deny và race condition.
- [ ] Có biện pháp giảm remote phishing, code guessing và session compromise.
- [ ] Có chính sách revoke và xử lý access token sau khi thiết bị bị mất/thu hồi quyền.

## 20. Tài liệu và tiêu chuẩn tham khảo

Nên xem đúng phiên bản Spring đang chạy:

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 8628, Section 3.3 — User Interaction](https://www.rfc-editor.org/rfc/rfc8628#section-3.3)
- [RFC 8628, Section 3.5 — Token Endpoint Responses](https://www.rfc-editor.org/rfc/rfc8628#section-3.5)
- [RFC 8628, Section 5 — Security Considerations](https://www.rfc-editor.org/rfc/rfc8628#section-5)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — OAuth2DeviceVerificationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2DeviceVerificationEndpointConfigurer.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)

## 21. Kết luận

Trong Device Authorization Grant, **TV khởi tạo yêu cầu**, nhưng **người dùng mới quyết định** có cấp quyền hay không bằng cách đăng nhập và xử lý consent trên browser thứ hai. `user_code` dùng để xác định phiên đang chờ; `device_code` là credential của thiết bị dùng tại token endpoint. Đăng nhập thành công chưa có nghĩa consent đã được cấp.

Để triển khai đúng trên Spring Authorization Server, cần kết nối mạch lạc **Device Authorization Endpoint → Device Verification Endpoint → user login/consent → trạng thái approval/denial trong authorization store → Device Code Grant tại Token Endpoint**. Nhánh phê duyệt phải chỉ cấp đúng scopes đã chấp thuận; nhánh từ chối phải thực sự ngăn cấp token và báo kết quả giao thức, không chỉ thay đổi giao diện. Khi kết hợp bảo vệ chống phishing, CSRF, code guessing, polling quá nhanh, nhiều instance và kiểm thử đồng thời, hệ thống mới có thể cho người dùng liên kết thiết bị hạn chế nhập liệu một cách an toàn và có thể vận hành.

