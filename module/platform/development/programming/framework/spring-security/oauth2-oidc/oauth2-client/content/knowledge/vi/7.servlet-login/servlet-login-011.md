# 7.11. AuthenticationFailureHandler và trải nghiệm khi người dùng từ chối cấp quyền

## 1. Bài toán: người dùng bấm “Từ chối” trên màn hình cấp quyền

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client** dùng Servlet, đăng nhập qua nhà cung cấp danh tính thường gồm hai bước nhìn thấy được: người dùng xác thực tại nhà cung cấp (*Identity Provider*, IdP), sau đó chấp thuận hoặc từ chối những quyền mà ứng dụng yêu cầu. Có những nhà cung cấp bỏ qua màn hình chấp thuận nếu người dùng đã đồng ý trước đó, nhưng ứng dụng vẫn phải xử lý tình huống cấp quyền không thành công.

Ví dụ, một cổng thông tin nội bộ Spring Boot yêu cầu scope `openid`, `profile` và `email`. Khi browser được chuyển sang IdP, người dùng chọn **Cancel / Deny / Không đồng ý**. Thay vì trả authorization code, IdP có thể đưa browser về callback của ứng dụng với lỗi:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.com/login/oauth2/code/company?error=access_denied&state=STATE_VALUE
~~~

Ứng dụng cần phản hồi theo cách dễ hiểu:

- Nhận diện đây là **giao dịch đăng nhập/ủy quyền không thành công**.
- Không tạo phiên đăng nhập mới từ callback thất bại.
- Hiển thị thông báo trung tính, chẳng hạn “Bạn đã hủy hoặc yêu cầu cấp quyền chưa được chấp thuận”.
- Cho người dùng chọn **thử lại**, **quay về trang công khai** hoặc **liên hệ hỗ trợ** khi cần, nhưng không tự redirect lặp lại vô hạn đến IdP.
- Không hiện nguyên `error_description` hoặc thông tin nội bộ của provider trên giao diện.

Trong Spring Security Servlet, điểm mở rộng phù hợp cho **lỗi đăng nhập OAuth2/OIDC đã đi qua filter xử lý xác thực** là `AuthenticationFailureHandler`, được cấu hình thông qua `oauth2Login().failureHandler(...)`.

**Cần phân biệt:** “người dùng từ chối cấp quyền” là một lý do thất bại có thể gặp; **không phải mọi lỗi OAuth2/OIDC login đều là người dùng từ chối**. Sai cấu hình redirect URI, lỗi state, mã code hết hạn, lỗi mạng hoặc token không hợp lệ cần cách diễn giải khác.

## 2. Quy trình bình thường và nhánh từ chối

### 2.1. Hai kết quả từ authorization endpoint

Trong Authorization Code flow, Spring Security khởi tạo yêu cầu đến authorization endpoint của provider:

~~~http
GET /authorize?response_type=code
    &client_id=portal-client
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
    &scope=openid%20profile%20email
    &state=RANDOM_STATE
    &code_challenge=PKCE_CHALLENGE
    &code_challenge_method=S256
Host: id.example.com
~~~

Đây là yêu cầu được xuống dòng để dễ đọc; URL thực tế phải được mã hóa đúng. Provider có thể cho phép hoặc từ chối giao dịch.

**Trường hợp cho phép:**

~~~text
/login/oauth2/code/company?code=AUTHORIZATION_CODE&state=RANDOM_STATE
~~~

Spring Security đối chiếu giao dịch, đổi code tại token endpoint và tiếp tục xác thực OIDC. Nếu kết quả hợp lệ, ứng dụng có thể tạo phiên đăng nhập.

**Trường hợp từ chối:**

~~~text
/login/oauth2/code/company?error=access_denied&state=RANDOM_STATE
~~~

Không có authorization code hợp lệ để đổi lấy token; Spring Security xử lý lỗi xác thực. `AuthenticationFailureHandler` có thể quyết định phản hồi HTTP cuối cùng cho browser, ví dụ điều hướng đến trang giải thích sự cố.

### 2.2. Sơ đồ luồng với failure handler

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / Browser
    participant C as Spring Boot Servlet Client
    participant P as OAuth2/OIDC Provider
    participant F as AuthenticationFailureHandler
    U->>C: GET /reports (yêu cầu đăng nhập)
    C-->>U: Redirect tới /oauth2/authorization/company
    U->>C: Bắt đầu OAuth2 Authorization
    C-->>U: Redirect tới authorization endpoint
    U->>P: Xác thực và xem màn hình consent
    alt Người dùng cho phép
        P-->>U: Redirect callback với code + state
        U->>C: GET /login/oauth2/code/company?code=...
        C->>P: Đổi code lấy token
        P-->>C: Access Token và ID Token nếu OIDC
        C-->>U: Login thành công, vào ứng dụng
    else Người dùng từ chối / provider từ chối
        P-->>U: Redirect callback với error=access_denied + state
        U->>C: GET /login/oauth2/code/company?error=...
        C->>F: onAuthenticationFailure(request, response, exception)
        F-->>U: Redirect /auth/feedback?status=cancelled
        U->>C: GET /auth/feedback
        C-->>U: Trang giải thích và lựa chọn thử lại
    end
~~~

Ở cả hai nhánh, việc lưu và kiểm tra `state`, quản lý callback và trao đổi token thuộc trách nhiệm của Spring Security. Ứng dụng chỉ nên cung cấp giao diện thất bại phù hợp sau khi framework xử lý callback theo cơ chế chuẩn.

## 3. OAuth 2.0 thông báo lỗi như thế nào?

Theo quy trình OAuth 2.0, authorization server có thể redirect về client với các tham số mô tả lỗi. Ví dụ:

~~~http
GET /login/oauth2/code/company?error=access_denied
    &error_description=The%20request%20was%20not%20approved
    &state=RANDOM_STATE HTTP/1.1
Host: portal.example.com
~~~

Những trường thường gặp:

| Tham số | Mục đích | Có nên đưa nguyên văn ra UI? |
| --- | --- | --- |
| `error` | Mã lỗi máy có thể xử lý, ví dụ `access_denied` | Nên ánh xạ sang trạng thái UI đã cho phép |
| `error_description` | Diễn giải tùy chọn từ provider | **Không** hiển thị nguyên văn, vì là dữ liệu bên ngoài |
| `error_uri` | URI tài liệu lỗi tùy chọn | Không tự tạo link chuyển hướng tới URI chưa tin cậy |
| `state` | Giá trị ràng buộc response với authorization request trước đó | Spring Security phải xử lý theo giao dịch; không dùng làm chuỗi hiển thị |

Các mã lỗi OAuth 2.0 tại authorization endpoint có thể gồm:

| Mã lỗi | Ý nghĩa tổng quát | Gợi ý xử lý UX |
| --- | --- | --- |
| `access_denied` | Resource owner hoặc authorization server từ chối yêu cầu | Thông báo chưa được cấp quyền; có nút quay lại và thử lại |
| `invalid_request` | Yêu cầu thiếu/sai tham số hoặc không hợp lệ | Thông báo đăng nhập không thể hoàn tất; đội vận hành kiểm tra cấu hình |
| `unauthorized_client` | Client không được phép dùng cách yêu cầu này | Không bảo người dùng phải thử nhiều lần; cần xem cấu hình provider |
| `unsupported_response_type` | Provider không hỗ trợ kiểu response được xin | Lỗi tích hợp/cấu hình |
| `invalid_scope` | Scope yêu cầu sai, không được chấp nhận hoặc không hỗ trợ | Lỗi scope/policy, không tự coi là người dùng bấm từ chối |
| `server_error` | Provider không thể xử lý yêu cầu | Hiển thị lỗi tạm thời, hỗ trợ thử lại hợp lý |
| `temporarily_unavailable` | Provider tạm ngừng phục vụ | Thông báo thử lại sau, tránh redirect tự động liên tục |

Những lỗi khác có thể xảy ra tại **token endpoint** hoặc bên trong quá trình xác minh OIDC, chẳng hạn `invalid_client`, `invalid_grant`, issuer sai, ID Token chữ ký không hợp lệ hay state không khớp. Dù cuối cùng đi qua failure handler, **chúng không phải là `access_denied`** và phải được xem là thất bại khác.

**Một chi tiết quan trọng:** `access_denied` không chứng minh chắc chắn người dùng đã chủ động bấm “Từ chối”; authorization server có thể từ chối do chính sách tổ chức, consent bắt buộc hoặc hạn chế tài khoản. Giao diện nên dùng câu trung tính thay vì đổ lỗi cho người dùng.

## 4. AuthenticationFailureHandler là gì?

`AuthenticationFailureHandler` là giao diện của Spring Security được dùng để **quyết định phản hồi HTTP khi xác thực thất bại** trong cơ chế xử lý xác thực của Servlet.

Chữ ký phương thức:

~~~java
import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException exception
    ) throws IOException, ServletException;
}
~~~

Chữ ký này là dạng minh họa của giao diện. Các ví dụ Spring Boot 3/Spring Security 6 trở lên dùng `jakarta.servlet.*`. Ứng dụng Spring Boot 2 cũ sử dụng namespace Servlet khác và có thể có cấu hình DSL khác; không trộn API hai thế hệ.

Khi một authentication filter bắt được `AuthenticationException`, Spring Security có thể gọi handler để:

- Chuyển browser về một URL an toàn.
- Trả trang HTML thông báo.
- Trả JSON lỗi có cấu trúc trong trường hợp client thực sự là ứng dụng API.
- Ghi sự kiện thất bại ở mức metadata không nhạy cảm.
- Quyết định một đường dẫn hỗ trợ hoặc thử lại theo loại thất bại.

Handler **không có nhiệm vụ cấp Access Token**, tạo ID Token, sửa chữ ký JWT hoặc tự bỏ kiểm tra `state`. Nó cũng không phải `AccessDeniedHandler` dùng cho tình huống người đã xác thực nhưng bị từ chối quyền truy cập tài nguyên trong ứng dụng.

### 4.1. Phân biệt với các thành phần có tên gần giống

| Thành phần | Khi nào dùng? | Ví dụ |
| --- | --- | --- |
| `AuthenticationFailureHandler` | Đăng nhập/xác thực thất bại | OAuth2 callback có `error=access_denied`; mã authorization code lỗi |
| `AuthenticationSuccessHandler` | Đăng nhập thành công | Điều hướng đến trang trước đó, tạo phản hồi sau login |
| `AuthenticationEntryPoint` | Truy cập tài nguyên chưa xác thực và cần bắt đầu xác thực | Redirect browser chưa đăng nhập đến trang login |
| `AccessDeniedHandler` | Một yêu cầu HTTP bị từ chối quyền truy cập theo Spring Security | Người dùng đã đăng nhập nhưng không được xem trang admin |
| `OAuth2UserService` / `OidcUserService` | Tải/ánh xạ thông tin người dùng sau khi giao dịch OAuth2/OIDC phù hợp | Lấy UserInfo và tạo principal |
| `OAuth2AuthorizationRequestRepository` | Lưu yêu cầu ủy quyền để kiểm tra khi callback | Quản lý state và request gốc |

Một ứng dụng có thể cần cả bốn loại xử lý lỗi/vào hệ thống trên. Đừng cấu hình `AccessDeniedHandler` rồi kỳ vọng nó sẽ bắt được callback `error=access_denied`: đây là hai bối cảnh khác nhau, dù tên đều có từ “denied”.

### 4.2. Failure handler được gọi ở đâu trong OAuth2 Login?

Luồng thông thường của Spring Security Servlet:

~~~text
GET /oauth2/authorization/company
    -> OAuth2AuthorizationRequestRedirectFilter
    -> redirect đến Authorization Server

GET /login/oauth2/code/company?... 
    -> OAuth2LoginAuthenticationFilter
    -> authentication manager/provider xử lý response
    -> thành công: AuthenticationSuccessHandler
    -> thất bại: AuthenticationFailureHandler
~~~

Các lỗi **trước khi callback được xử lý bởi login filter**, chẳng hạn không tạo được authorization request, hỏng kết nối khi tải metadata ở startup hoặc lỗi phát sinh trong filter khác, **không bắt buộc đều đi qua** `oauth2Login().failureHandler(...)`. Với những trường hợp đó, cần quan sát đúng điểm lỗi và cấu hình cơ chế xử lý tương ứng; không dựa vào một handler để giải quyết mọi loại sự cố trong giao thức.

## 5. Ví dụ hoàn chỉnh cho Spring Security Servlet

Phần này minh họa ứng dụng Spring Boot có OIDC provider tên `company`. Khi người dùng từ chối consent, browser được chuyển đến trang phản hồi thân thiện. Với lỗi khác, ứng dụng hiển thị thông báo kỹ thuật chung và để đội vận hành tìm nguyên nhân qua log phù hợp.

### 5.1. Dependency và ClientRegistration

Ví dụ `build.gradle` cho Spring Boot 3.x đã dùng Spring Boot plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

Trên Spring Boot 4.x, tên starter tương ứng là `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`; chọn theo BOM/version thật của dự án. Thymeleaf chỉ là công cụ render trang ví dụ; có thể thay bằng view engine hoặc frontend phù hợp.

Cấu hình `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://id.example.com/realms/company
~~~

Issuer và client ID trong ví dụ cần thay bằng thông tin đã được xác minh của provider. Redirect URI thực tế phải khớp URI đã đăng ký tại IdP. Không commit client secret, và khi chạy production dùng HTTPS hợp lệ.

### 5.2. Implement failure handler: chỉ phân loại lỗi đã biết

Đặt tại `src/main/java/com/example/security/OAuth2LoginFailureHandler.java`:

~~~java
package com.example.security;

import java.io.IOException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

@Component
public final class OAuth2LoginFailureHandler implements AuthenticationFailureHandler {

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        // Giá trị dùng cho UI phải nằm trong danh sách cố định.
        String status = "failed";

        if (exception instanceof OAuth2AuthenticationException oauth2Exception) {
            String errorCode = oauth2Exception.getError().getErrorCode();
            if ("access_denied".equals(errorCode)) {
                status = "cancelled";
            }
        }

        // Redirect nội bộ cố định; không nối error_description từ provider.
        String target = request.getContextPath() + "/auth/feedback?status=" + status;
        response.sendRedirect(target);
    }
}
~~~

Giải thích từng lựa chọn:

1. `AuthenticationException` là lỗi tổng quát; với lỗi OAuth2, Spring Security có thể cung cấp `OAuth2AuthenticationException` và `OAuth2Error` chứa mã lỗi.
2. Chỉ mã `access_denied` được ánh xạ sang UI `cancelled`. Các lỗi khác dùng `failed`; không gán mọi lỗi thành “người dùng từ chối”.
3. `status` được tạo từ **hai giá trị cố định**, vì thế không đưa `error_description` hay tham số tùy ý từ browser vào URL đích.
4. Redirect dùng `request.getContextPath()` và đường dẫn nội bộ do ứng dụng kiểm soát; không nhận target URL từ query parameter hoặc giá trị do provider cung cấp.
5. Mã ví dụ không ghi log thông tin nhạy cảm, không tự sửa session/authorized client và không can thiệp vào xác minh state của Spring Security.

Một lỗi OAuth2 có thể bị bọc trong dạng `AuthenticationException` khác hoặc xảy ra ở filter khác, tùy tình huống; handler có **fallback an toàn** là `failed`. Muốn phân loại chi tiết hơn, hãy kiểm tra thực tế ở bước Content QA và quan sát các mã lỗi framework/provider trong môi trường kiểm thử.

### 5.3. Gắn handler vào `SecurityFilterChain`

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2LoginFailureHandler loginFailureHandler) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/auth/feedback",
                    "/error", "/css/**", "/images/**"
                ).permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .failureHandler(loginFailureHandler))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Hai quyết định cần thiết:

- `oauth2Login(...failureHandler(...))` liên kết handler với **luồng login** chứ không đăng ký một `@ControllerAdvice` chung cho toàn bộ ứng dụng.
- `/auth/feedback` là **trang public**. Nếu trang lỗi cũng yêu cầu đăng nhập, filter sẽ kích hoạt OAuth2 login tiếp, tạo vòng lặp redirect khó thoát sau khi người dùng vừa từ chối.

Với nhiều `SecurityFilterChain`, phải đặt cấu hình `oauth2Login()` và failure handler vào chain thực sự xử lý callback. Thứ tự và `securityMatcher` của các chain có thể khiến một chain khác bắt request trước.

### 5.4. Controller hiển thị trang phản hồi

Đặt tại `src/main/java/com/example/web/AuthFeedbackController.java`:

~~~java
package com.example.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class AuthFeedbackController {

    @GetMapping("/auth/feedback")
    public String feedback(
            @RequestParam(defaultValue = "failed") String status,
            Model model) {

        boolean cancelled = "cancelled".equals(status);
        if (cancelled) {
            model.addAttribute(
                "heading",
                "Đăng nhập chưa được hoàn tất");
            model.addAttribute(
                "message",
                "Bạn đã hủy hoặc nhà cung cấp chưa chấp thuận quyền được yêu cầu.");
        } else {
            model.addAttribute(
                "heading",
                "Chưa thể hoàn tất đăng nhập");
            model.addAttribute(
                "message",
                "Đã có sự cố trong quá trình đăng nhập. Bạn có thể thử lại hoặc liên hệ hỗ trợ.");
        }

        return "auth-feedback";
    }
}
~~~

Ở đây controller **không trực tiếp in giá trị `status` vào HTML**; nó chỉ dùng giá trị để chọn hai tập thông báo đã định nghĩa sẵn. Điều này bảo vệ giao diện nếu người dùng trực tiếp thay URL `?status=...`.

Tạo giao diện Thymeleaf tại `src/main/resources/templates/auth-feedback.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Thông báo đăng nhập</title>
</head>
<body>
<main>
    <h1 th:text="${heading}">Thông báo đăng nhập</h1>
    <p th:text="${message}">Đăng nhập chưa hoàn tất.</p>

    <p>
        <a th:href="@{/login}">Trở về trang chọn cách đăng nhập</a>
    </p>
    <p>
        <a th:href="@{/}">Về trang chủ</a>
    </p>
</main>
</body>
</html>
~~~

Trong template trên, `th:text` render nội dung theo cơ chế escape HTML của Thymeleaf. Các link dùng đường dẫn do ứng dụng kiểm soát, đồng thời hỗ trợ context path. `/login` có thể là trang login mặc định khi Spring Security tạo trang này hoặc là trang tùy biến của ứng dụng; nếu ứng dụng dùng trang login riêng, hãy đổi link cho đúng.

**Đừng tạo nút “Thử lại” bằng JavaScript tự kích hoạt nhiều lần.** Một liên kết cho người dùng tự chọn retry rõ ràng và dễ hiểu hơn. Nếu ứng dụng có nhiều provider, đưa về trang chọn provider thay vì giả định luôn retry cùng một nhà cung cấp.

### 5.5. Khi nào dùng handler có sẵn thay vì viết class riêng?

Nếu mọi lỗi đều cần chuyển về cùng trang, Spring Security có `SimpleUrlAuthenticationFailureHandler`:

~~~java
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

// Có thể cấu hình:
SimpleUrlAuthenticationFailureHandler handler =
    new SimpleUrlAuthenticationFailureHandler("/auth/feedback?status=failed");
~~~

Và gắn qua `oauth2Login(oauth2 -> oauth2.failureHandler(handler))`. Cách này đơn giản nhưng **không phân biệt** `access_denied` với lỗi cấu hình. Khi muốn điều chỉnh trải nghiệm dành riêng cho tình huống người dùng từ chối, custom `AuthenticationFailureHandler` như ví dụ trên phù hợp hơn.

## 6. Thiết kế trải nghiệm khi người dùng từ chối cấp quyền

Một trang xử lý từ chối nên trả lời ba câu hỏi: **Điều gì đã xảy ra? Quyền truy cập đã được cấp chưa? Người dùng có thể làm gì tiếp?**

### 6.1. Thông điệp phù hợp

| Tình huống | Nội dung nên hiển thị | Hành động phù hợp |
| --- | --- | --- |
| Người dùng từ chối consent hoặc provider từ chối `access_denied` | “Yêu cầu đăng nhập hoặc cấp quyền chưa được chấp thuận. Tài khoản chưa được kết nối trong lượt này.” | Quay về, thử lại khi sẵn sàng |
| User không muốn chia sẻ một scope nhạy cảm | “Để sử dụng tính năng này, ứng dụng cần quyền đã mô tả. Bạn có thể quay lại nếu không muốn cấp quyền.” | Giải thích mục đích scope, dừng hoặc chọn tính năng khác |
| Provider tạm thời không hoạt động | “Hiện chưa thể kết nối nhà cung cấp đăng nhập. Vui lòng thử lại sau.” | Nút thử lại có chủ đích, đường hỗ trợ |
| Client cấu hình sai hoặc token không hợp lệ | “Không thể hoàn tất đăng nhập. Vui lòng liên hệ bộ phận hỗ trợ nếu lỗi tiếp diễn.” | Gửi mã hỗ trợ/correlation ID nếu có |
| Người dùng đang liên kết thêm tài khoản ngoài nhưng từ chối | “Chưa liên kết tài khoản. Bạn vẫn có thể tiếp tục công việc trong ứng dụng nếu phiên hiện tại còn hợp lệ.” | Quay về màn hình quản lý liên kết, giữ dữ liệu nghiệp vụ |

Tránh các thông báo như “Bạn đã làm sai”, “Hệ thống bảo mật thất bại” hoặc “Không có quyền sử dụng” khi chỉ mới biết `access_denied`. Một người dùng có thể cố ý không chấp thuận quyền vì muốn bảo vệ dữ liệu; trải nghiệm không nên ép họ lặp lại consent.

### 6.2. Nguyên tắc làm rõ scope được yêu cầu

Trước khi chuyển sang provider, ứng dụng nên giải thích vì sao cần quyền: `openid` để thực hiện đăng nhập OIDC, `profile` để hiển thị tên/ảnh nếu có, `email` để đọc thuộc tính email khi provider cho phép, scope nghiệp vụ như `calendar.read` hoặc `files.read` để dùng chức năng tương ứng.

Không dùng nội dung như “Ứng dụng cần toàn quyền truy cập” nếu thực tế chỉ cần đọc một dữ liệu cụ thể. Nếu chức năng có thể chạy với ít quyền hơn, cân nhắc **scope tối thiểu** và chỉ xin thêm quyền ở thời điểm cần (*incremental authorization*) nếu provider hỗ trợ. Khi người dùng từ chối quyền bổ sung, một chức năng phụ có thể ngừng hoạt động mà không nhất thiết phải hủy mọi tính năng khác.

### 6.3. Tránh vòng lặp redirect

Thiết kế sau có thể gây vòng lặp:

~~~text
Người dùng từ chối tại IdP
    -> failure handler redirect /private-page
    -> /private-page yêu cầu đăng nhập
    -> Spring Security redirect lại IdP
    -> người dùng lại từ chối
    -> quay về /private-page ...
~~~

Để tránh:

1. Trang phản hồi là trang public và không tự phát lệnh OAuth2 login.
2. Trang có nút **thử lại do người dùng chủ động nhấn**.
3. Nếu sử dụng saved request trước đăng nhập, không tự phục hồi saved request sau một giao dịch login thất bại khiến trình duyệt quay về đúng URL đang bảo vệ trong vòng lặp.
4. Có đường về trang công khai hoặc liên hệ hỗ trợ.

Trong hệ thống SSO có nhiều cơ chế đăng nhập, cho người dùng chọn provider khác nếu sản phẩm cho phép; không tự thay provider và liên kết tài khoản khi chưa có quyết định người dùng.

### 6.4. Không gộp lỗi xác thực với lỗi thiếu quyền nghiệp vụ

Ví dụ người dùng đã OIDC login thành công nhưng bị từ chối vào trang quản trị của ứng dụng. Đó thường là trường hợp `403 Forbidden` do `AccessDeniedHandler` hoặc chính sách ứng dụng xử lý. Ngược lại, người dùng bấm “Cancel” tại IdP **trước khi cấp quyền đăng nhập** thuộc nhóm lỗi xác thực OAuth2/OIDC, đi qua failure handler thích hợp.

| Sự kiện | Lớp xử lý | Người dùng cần thấy |
| --- | --- | --- |
| Bấm “Deny” tại OAuth consent | OAuth2 login failure handler | Giao dịch đăng nhập/cấp quyền chưa hoàn tất |
| Sai state ở OAuth callback | OAuth2 login failure handler trong luồng callback, nếu filter bắt lỗi | Đăng nhập không hoàn tất; có thể thử lại |
| Đã login nhưng truy cập trang admin không có role | Authorization / AccessDeniedHandler | Không đủ quyền xem chức năng này |
| Downstream API trả `403` vì thiếu scope | HTTP client/API error handling | Tính năng chưa có quyền API cần thiết |
| Provider unreachable khi bootstrap discovery | Application configuration/startup handling | Sự cố tích hợp/vận hành, không nhất thiết đi qua login failure handler |

## 7. Bảo mật và quyền riêng tư của failure handler

### 7.1. Không tin trực tiếp query parameter của callback

Một callback OAuth2 có thể chứa `error`, `error_description` và `state`. Đây là dữ liệu đến qua browser, cần được xử lý trong ngữ cảnh giao dịch ủy quyền hợp lệ. **Không viết một controller công khai nhận `error=access_denied` rồi đánh dấu mọi callback là “người dùng từ chối”** hoặc dùng thông tin đó để tự cập nhật trạng thái bảo mật.

Spring Security lưu authorization request để liên kết callback với phiên giao dịch, kiểm tra state và thực hiện các bước giao thức phù hợp. Failure handler nhận `AuthenticationException` sau cơ chế xử lý của authentication filter; nó **không thay thế** quy trình xác minh giao dịch.

Nếu query callback bị giả mạo hoặc không gắn với authorization request, framework có thể phát sinh lỗi không phải `access_denied`. Với các trường hợp này, handler nên dùng nhánh lỗi chung, tránh khẳng định người dùng đã tự từ chối.

### 7.2. Không phản chiếu `error_description` ra trình duyệt

Giả sử provider gửi:

~~~text
error=access_denied
error_description=<untrusted text or HTML>
~~~

Nếu ứng dụng lấy `error_description` và đặt trực tiếp vào HTML, có thể tạo ra **cross-site scripting (XSS)** hoặc lộ thông tin cấu hình provider. Ngay cả khi framework hoặc template engine có escape HTML, diễn giải từ provider có thể chứa chi tiết không nên công bố cho người dùng.

Phương án an toàn: phân loại từ mã lỗi đã biết và hiển thị thông điệp được quản lý bởi ứng dụng. Giao diện có thể có một mã hỗ trợ ngẫu nhiên/correlation ID, còn log server lưu thông tin kỹ thuật tối thiểu tương ứng.

### 7.3. Không redirect đến URL do người dùng hoặc provider kiểm soát

Ví dụ không nên:

~~~java
// Phản ví dụ - không dùng trong ứng dụng:
String target = request.getParameter("returnUrl");
response.sendRedirect(target);
~~~

Nếu không có allowlist/kiểm tra chặt, đó có thể là **open redirect**. OAuth login đặc biệt nhạy cảm với việc điều hướng nhầm sang domain khác, nhất là khi URL chứa trạng thái phiên hoặc mã liên quan.

Hãy dùng route nội bộ cố định cho trạng thái lỗi. Nếu sản phẩm cần quay về màn hình trước đó, lưu ý định hướng điều hướng an toàn đã được ứng dụng thiết lập từ trước, không nhận tùy ý URL đích từ callback.

### 7.4. Ghi log thế nào?

Nên ghi dữ liệu hỗ trợ vận hành như:

~~~text
event=oauth2_login_failed
registration=company
outcome=consent_not_granted
correlation_id=7c9b... 
http_route=/login/oauth2/code/company
~~~

Đây là log mẫu mang tính minh họa, không yêu cầu ghi những trường chưa có dữ liệu. Nếu framework chưa xác minh giao dịch, không được tự tin gán thất bại cho một tài khoản/registration chỉ dựa trên query không tin cậy.

Không ghi:

- `authorization_code` hoặc toàn bộ URL callback có `code` và `state`.
- Access Token, ID Token, Refresh Token hay client secret.
- `error_description` nguyên bản khi có thể chứa dữ liệu nhạy cảm hoặc mã do bên ngoài kiểm soát.
- Địa chỉ email/tên tài khoản đầy đủ trừ khi có nhu cầu nghiệp vụ, chính sách lưu trữ và quyền truy cập tương ứng.

Nếu cần phân tích lỗi, dùng các enum lỗi an toàn và correlation ID, kiểm soát quyền đọc log, thời hạn lưu trữ và tần suất ghi để tránh tạo quá nhiều log từ callback giả mạo.

### 7.5. Xử lý session và authorized client sau lỗi

Không giả định một callback `access_denied` tạo ra `OAuth2AuthorizedClient` mới hoặc Token mới: khi Authorization Code flow bị từ chối, thường **không có code để đổi lấy token**.

Tuy nhiên, nếu user **đã đăng nhập từ trước** và đang thử liên kết thêm một provider, trạng thái phiên/authorized client hiện có cần được xử lý theo từng thiết kế. Cơ chế `AbstractAuthenticationProcessingFilter` và failure path có thể tác động `SecurityContext` trong request; không nên viết mô tả khẳng định mọi phiên cũ luôn giữ nguyên hay mọi phiên sẽ bị xóa.

Nếu nghiệp vụ là “kết nối tài khoản dịch vụ bên ngoài” bên trong một phiên đang hoạt động, hãy chủ động thiết kế luồng liên kết, bảo toàn dữ liệu công việc và kiểm tra cơ chế lưu Authentication; có thể cần flow riêng thay cho việc mặc định coi lần OAuth2 callback mới là một lần login thay thế.

## 8. Login thất bại khác “kết nối dịch vụ ngoài” thất bại

Hai màn hình có thể cùng dùng OAuth Authorization Code flow nhưng mục tiêu nghiệp vụ khác nhau:

| Bài toán | Nếu người dùng từ chối | Phản hồi mong muốn |
| --- | --- | --- |
| **Đăng nhập chính vào portal** bằng IdP | Chưa xác thực được danh tính mới | Không tạo login mới; hiển thị trang công khai có nút thử lại |
| **Liên kết Google Drive/Calendar** vào account đã có session | Chưa cấp quyền sử dụng API ngoài | Giữ màn hình quản lý tích hợp nếu session còn hợp lệ; đánh dấu liên kết chưa hoàn thành |
| **Xin thêm scope cho tính năng phụ** | Chức năng phụ chưa được cấp phép | Giải thích quyền tối thiểu cần có; cho quay lại phần còn dùng được |
| **Đổi provider đăng nhập** | Chưa hoàn tất giao dịch với provider mới | Giữ chính sách đăng nhập/định danh hiện có, không tự hợp nhất tài khoản |

Ví dụ, người dùng đã dùng portal bằng tài khoản công ty rồi muốn cho portal đọc lịch. Họ từ chối scope `calendar.read`. Điều đó **không đồng nghĩa người dùng không có quyền đăng nhập portal**; nó chỉ nói rằng token/ủy quyền cho tính năng lịch chưa được cấp. Luồng tích hợp có thể cần một authorization client flow và xử lý thất bại riêng, thay vì dùng toàn bộ logic login OIDC làm “connect account”.

Khi liên kết tài khoản nhiều provider, tránh cập nhật liên kết nội bộ cho đến khi đã nhận token cần thiết và kiểm tra chủ thể/consent theo yêu cầu. Đừng tự đánh dấu liên kết thành công chỉ vì browser đã quay về callback.

## 9. Nâng cấp failure handler khi ứng dụng có nhiều provider

Giả sử portal cho đăng nhập bằng `company` và `partner`. Khi giao dịch thất bại, UX có thể đưa người dùng về **trang chọn provider** để thử lại. Không nên lấy `registrationId` từ query tùy ý rồi redirect trực tiếp tới một domain hoặc tạo vòng lặp đăng nhập.

Một thiết kế đơn giản có thể dùng trạng thái UI cố định:

~~~text
/auth/feedback?status=cancelled
    -> "Bạn đã hủy hoặc yêu cầu chưa được chấp thuận."
    -> nút /login để chọn provider

/auth/feedback?status=failed
    -> "Không thể hoàn tất đăng nhập."
    -> nút /login, về trang chủ, hỗ trợ
~~~

Nếu thực sự cần hiển thị tên provider, ánh xạ từ **danh sách registration đã được cấu hình và tin cậy** vào nhãn có thể hiển thị, chẳng hạn “Tài khoản công ty” thay vì URL issuer hoặc giá trị do callback cung cấp. Khi người dùng có nhiều phương thức đăng nhập, một trang phản hồi chung giúp tránh những kịch bản bị mắc kẹt tại một provider.

### 9.1. Sử dụng error code trong business metrics

Đo sự cố thực tế có thể giúp cải thiện onboarding:

| Chỉ số | Cách diễn giải |
| --- | --- |
| Số lần OAuth2 login được bắt đầu | Tổng giao dịch ủy quyền được khởi tạo |
| Tỷ lệ callback có `access_denied` | Những giao dịch bị từ chối theo mã provider, không chắc toàn bộ do người dùng chủ động |
| Tỷ lệ lỗi giao thức/token | Khả năng xảy ra lỗi cấu hình, môi trường hoặc provider |
| Tỷ lệ người dùng tự thử lại | Mức độ hữu dụng của trang phản hồi |
| Số request vào trang feedback không kèm giao dịch hợp lệ | Không nên tự động coi là một login failure vì URL trang feedback là công khai |

Metric nên ưu tiên **số lượng tổng hợp** và mã lỗi an toàn. Không lưu toàn bộ consent response hoặc profile người dùng chỉ để phân tích tỷ lệ từ chối.

## 10. Kiểm thử tình huống một cách có kiểm soát

Khi phát triển ứng dụng với OIDC provider thử nghiệm, có thể kiểm tra luồng trải nghiệm qua các kịch bản sau. Đây là các **hành vi kỳ vọng để hiểu bài**, không phải kết quả chạy test:

| Kịch bản | Tác nhân | Kết quả mong đợi |
| --- | --- | --- |
| Người dùng cho phép scope | Login thành công, provider trả `code` | Spring Security xử lý token và điều hướng theo success handler |
| Người dùng bấm từ chối | Provider trả `error=access_denied` khi callback | Failure handler chọn `cancelled` và điều hướng đến trang feedback |
| Provider lỗi tạm thời | Provider trả `server_error` hoặc `temporarily_unavailable` | Trang thông báo lỗi chung, không đổ lỗi cho user |
| Người dùng mở trực tiếp `/auth/feedback` | Không có session đăng nhập | Trang public hiển thị an toàn, không tự redirect về IdP |
| URL feedback chứa `status=<script>...` | Người dùng chỉnh query | Controller dùng nhánh `failed`, không phản chiếu chuỗi tùy ý vào HTML |
| Callback state không khớp | Giao dịch OAuth2 không hợp lệ | Không cấp Authentication mới; hiển thị lỗi chung theo cơ chế filter phù hợp |
| Provider trả `invalid_scope` | Client request sai scope | Hiển thị lỗi; đội phát triển kiểm tra registration |
| Người dùng thử lại thủ công | Nhấn link trên trang feedback | Bắt đầu một giao dịch login mới, không tái sử dụng code/state cũ |
| User đã có session và từ chối cấp thêm scope | Flow liên kết/tăng scope | Tùy thiết kế tích hợp; không tự coi mọi hoạt động của user là thất bại |
| API nghiệp vụ trả `403` sau login | Access Token thiếu scope | Xử lý lỗi quyền API ở lớp downstream, không gán là consent login failure |

Ví dụ khi ứng dụng nhận callback giả mạo:

~~~text
GET /login/oauth2/code/company?error=access_denied&state=FAKE_STATE
~~~

Ứng dụng phải dựa vào framework để kiểm tra callback tương ứng với yêu cầu ủy quyền hợp lệ. **Không tự tạo Authentication bằng cách đọc `error` hoặc `state` trong controller.** Với test thực tế, cần một provider test hoặc môi trường tích hợp có khả năng chủ động trả các OAuth response khác nhau.

## 11. Những lỗi triển khai phổ biến

### Lỗi 1: Coi mọi OAuth2AuthenticationException là người dùng từ chối

**Hậu quả:** lỗi cấu hình, token endpoint hoặc ID Token chữ ký không đúng bị báo thành “Bạn đã từ chối”. Người dùng không có cách giải quyết và vận hành khó phát hiện sự cố thật.

**Cách xử lý:** chỉ ánh xạ mã `access_denied` vào thông điệp chấp thuận chưa thành công; mã còn lại dùng nhánh lỗi chung hoặc phân loại được kiểm soát.

### Lỗi 2: Redirect đến trang yêu cầu đăng nhập

**Hậu quả:** trang lỗi bị `anyRequest().authenticated()` bảo vệ, dẫn đến redirect lặp lại.

**Cách xử lý:** đưa `/auth/feedback` vào `permitAll()`, cho nút thử lại bằng hành động của người dùng.

### Lỗi 3: Hiển thị nguyên `error_description`

**Hậu quả:** lộ thông tin từ provider, có thể xuất hiện nội dung HTML hoặc chuỗi độc hại khi render.

**Cách xử lý:** dùng message đã định nghĩa trong ứng dụng; không phản chiếu dữ liệu bên ngoài.

### Lỗi 4: Dùng `AccessDeniedHandler` cho callback `access_denied`

**Hậu quả:** không bắt đúng sự kiện OAuth2 login failure vì authorization denial và application authorization denial là hai lớp khác nhau.

**Cách xử lý:** dùng `oauth2Login().failureHandler(...)` cho callback failure; dùng `AccessDeniedHandler` cho 403 trong ứng dụng.

### Lỗi 5: Ghi token và callback URL vào log

**Hậu quả:** lộ code, state hoặc token nếu log bị truy cập. Log quá chi tiết còn khiến dữ liệu nhạy cảm bị giữ lâu.

**Cách xử lý:** lưu mã lỗi đã phân loại, route tĩnh và correlation ID; không ghi giá trị credential.

### Lỗi 6: Tự sửa `state` để vượt qua callback lỗi

**Hậu quả:** phá vỡ ràng buộc CSRF giữa authorization request và response.

**Cách xử lý:** để Spring Security xử lý state/authorization request; tìm nguyên nhân mất session, SameSite cookie, proxy, redirect URI hoặc trình duyệt chặn cookie.

### Lỗi 7: Lấy trạng thái `cancelled` của URL feedback làm bằng chứng consent

**Hậu quả:** bất kỳ ai cũng có thể mở `/auth/feedback?status=cancelled`; query này không chứng minh họ từng bắt đầu hoặc từ chối một giao dịch thật.

**Cách xử lý:** trang feedback chỉ là giao diện. Không dùng nó để cập nhật security state hay audit bắt buộc; audit dựa trên sự kiện framework/server tin cậy.

### Lỗi 8: Hủy toàn bộ dữ liệu nghiệp vụ khi user hủy kết nối provider

**Hậu quả:** người dùng đang làm việc trong ứng dụng có thể mất bản nháp hoặc phiên chỉ vì từ chối scope của một tích hợp tùy chọn.

**Cách xử lý:** tách login chính và flow liên kết tài khoản/API ngoài; thiết kế session và trạng thái công việc phù hợp.

## 12. Tình huống thực tế và cách ra quyết định

### Tình huống A: Đăng nhập OIDC lần đầu bị từ chối

Người dùng chưa có session, chọn “Không đồng ý” tại IdP. Provider trả `access_denied`. Spring Security không có token mới để hoàn tất login.

**Ứng dụng:** hiển thị trang feedback public với thông điệp rõ ràng và nút quay lại `/login`. Không trả trang quản trị, không tự retry.

### Tình huống B: Nhà cung cấp chặn consent theo chính sách tổ chức

Người dùng nhấn “Đồng ý”, nhưng provider vẫn trả `access_denied` vì chính sách admin. Nếu UI viết “Bạn đã từ chối” là thiếu chính xác.

**Ứng dụng:** hiển thị “Yêu cầu chưa được chấp thuận” và đường hướng dẫn liên hệ quản trị viên khi cần; log metadata an toàn để vận hành phân biệt.

### Tình huống C: Sai `redirect_uri` sau deploy

Provider từ chối yêu cầu do callback URL được cấu hình lệch hostname hoặc port. Một số lỗi diễn ra trước callback và failure handler không được gọi.

**Ứng dụng:** sửa client registration, trusted proxy và danh sách URI được đăng ký ở IdP. Không tìm cách xử lý bằng cách đổi thông điệp `access_denied`.

### Tình huống D: Người dùng không cho phép đọc lịch

Người dùng đã đăng nhập portal. Khi mở tính năng đồng bộ lịch, ứng dụng yêu cầu quyền API bổ sung và người dùng bấm từ chối.

**Ứng dụng:** không đánh dấu calendar integration là đã kết nối. Nếu phiên portal còn hợp lệ, người dùng có thể tiếp tục công việc khác; cần flow tích hợp tách biệt để tránh tác động authentication chính.

### Tình huống E: Access Token dùng được cho UserInfo nhưng API trả 403

Login OIDC thành công; API công việc không chấp nhận quyền của Access Token.

**Ứng dụng:** kiểm tra audience, scope, resource indicators và policy của API. Đây là lỗi **sau đăng nhập**, không phải sự kiện consent bị từ chối tại màn hình OAuth authorization.

### Tình huống F: Browser gửi callback với `error=access_denied` nhưng thiếu state

Callback có thể không liên kết được với authorization request; framework có thể trả lỗi state/authorization request trước hoặc trong quá trình xử lý.

**Ứng dụng:** không bỏ qua state để có trang “hủy” đẹp hơn; chỉ hiển thị thông điệp an toàn tùy loại lỗi, bảo toàn kiểm tra CSRF của giao thức.

## 13. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security Javadoc — AuthenticationFailureHandler: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/AuthenticationFailureHandler.html
- Spring Security Javadoc — SimpleUrlAuthenticationFailureHandler: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html
- OAuth 2.0 Authorization Framework — Authorization Response Error (RFC 6749, Section 4.1.2.1): https://www.rfc-editor.org/rfc/rfc6749#section-4.1.2.1
- OpenID Connect Core 1.0 — Authentication Error Response: https://openid.net/specs/openid-connect-core-1_0.html

## 14. Kết luận thực hành

Trong Spring Security Servlet OAuth2/OIDC Login, hành trình xử lý **người dùng từ chối cấp quyền** nên diễn ra như sau:

~~~text
Người dùng từ chối hoặc provider không cấp quyền
  -> OAuth authorization response: error=access_denied
  -> Spring Security xử lý callback và ngữ cảnh giao dịch
  -> OAuth2 login AuthenticationException
  -> AuthenticationFailureHandler
  -> Redirect nội bộ tới /auth/feedback?status=cancelled
  -> Trang công khai giải thích tình huống, có lựa chọn thử lại

Lỗi khác như invalid_client, invalid_grant, state mismatch, mạng...
  -> Xử lý thích hợp hoặc thông điệp lỗi chung
  -> Không tự mô tả thành "người dùng từ chối"
~~~

**`AuthenticationFailureHandler` giúp biến sự kiện login thất bại thành phản hồi có chủ đích cho người dùng; nó không thay thế xác minh giao thức OAuth2/OIDC.** Chỉ phân loại những lỗi đủ tin cậy, không phản chiếu dữ liệu provider, bảo vệ state và session, tránh redirect loop, và để người dùng chủ động quyết định có thử đăng nhập/cấp quyền lại hay không.
