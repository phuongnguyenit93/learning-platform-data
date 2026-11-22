# Đăng nhập một lần (SSO) và mối quan hệ với liên kết danh tính

> **Bối cảnh:** Spring Security – federation (liên kết danh tính), phần **Tổng quan liên kết**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng **Single Sign-On (SSO)**, **identity federation**, xác thực (authentication) và phân quyền (authorization).
2. Phân biệt phiên đăng nhập tại **Identity Provider (IdP)** với phiên riêng của từng ứng dụng; biết vì sao SSO có thể diễn ra nhưng không được bảo đảm trong mọi lần truy cập.
3. Mô tả luồng SSO với OpenID Connect (OIDC) và đối chiếu với SAML 2.0.
4. Cấu hình một ứng dụng Spring Security đóng vai trò **Relying Party/OIDC Client** để đăng nhập qua IdP.
5. Nhận biết các ranh giới tin cậy, cách ánh xạ người dùng và những lỗi bảo mật phổ biến.

## 1. Bài toán thực tế: một nhân viên, nhiều ứng dụng

Một nhân viên sử dụng **HR Portal**, **CRM** và **Support Portal**. Cả ba ứng dụng đều cần biết ai đang truy cập, nhưng không nên tự giữ ba mật khẩu độc lập. Doanh nghiệp có thể dùng một IdP (chẳng hạn một hệ thống quản lý danh tính của tổ chức) để xác thực nhân viên. Nếu nhân viên vừa đăng nhập HR Portal và phiên IdP vẫn hợp lệ, khi vào CRM, IdP có thể xác nhận người dùng ngay mà không yêu cầu nhập mật khẩu lần nữa: đây là **trải nghiệm SSO**.

Nếu Support Portal do đối tác khác vận hành, doanh nghiệp và đối tác phải thiết lập quan hệ tin cậy, giao thức và quy tắc nhận danh tính để đối tác chấp nhận kết quả xác thực từ IdP của doanh nghiệp. Đó là **identity federation**. Khi giao diện đăng nhập của Support Portal chuyển người dùng về IdP và IdP tái sử dụng phiên sẵn có, **federation hỗ trợ tạo ra SSO xuyên ranh giới tổ chức**.

Hai khái niệm bổ trợ nhau nhưng không đồng nghĩa:

- **SSO** mô tả *trải nghiệm*: xác thực một lần rồi truy cập nhiều ứng dụng mà thường không nhập lại thông tin đăng nhập khi phiên/điều kiện bảo mật còn hợp lệ.
- **Federation** mô tả *quan hệ tin cậy và cách trao đổi danh tính*: một bên chấp nhận bằng chứng xác thực do một bên khác phát hành.
- Một hệ thống nội bộ có thể có SSO mà không cần liên kết danh tính giữa hai tổ chức. Một hệ thống federation cũng có thể yêu cầu xác thực lại hoặc MFA mỗi lần vì chính sách; do đó không phải lần truy cập nào cũng “không hỏi mật khẩu”.

## 2. Những vai trò và thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa trong bài | Ví dụ |
| --- | --- | --- |
| **User / End User** | Người dùng truy cập ứng dụng. | Nhân viên mở CRM. |
| **Identity Provider (IdP)** | Bên xác thực người dùng, quản lý phiên đăng nhập và phát hành thông tin/dấu hiệu về danh tính. | IdP của doanh nghiệp. |
| **Relying Party (RP)** | Ứng dụng tin vào kết quả xác thực của OpenID Provider theo OIDC. | CRM dùng OIDC Login. |
| **Service Provider (SP)** | Thuật ngữ phổ biến ở SAML cho ứng dụng nhận SAML assertion. | Cổng đối tác dùng SAML. |
| **Client Registration** | Cấu hình quan hệ giữa ứng dụng và nhà cung cấp: client ID, redirect URI, phạm vi, issuer… | Bản đăng ký `corp` trong Spring Boot. |
| **Authentication (xác thực)** | Xác định danh tính hoặc kiểm tra bằng chứng về người dùng. | Đăng nhập bằng mật khẩu + MFA tại IdP. |
| **Authorization (phân quyền)** | Quyết định người dùng đã xác thực có được phép thực hiện hành động hay không. | Chỉ nhân viên HR được xem dữ liệu lương. |
| **Trust relationship** | Thỏa thuận kỹ thuật/chính sách để ứng dụng chấp nhận danh tính từ một IdP nhất định. | RP cấu hình issuer, client ID, khóa xác minh. |

**Điểm mấu chốt:** “Được IdP xác thực” không đồng nghĩa “được phép dùng mọi tài nguyên”. Ứng dụng vẫn phải tự kiểm tra quyền truy cập dựa trên nhu cầu và chính sách của mình.

### Ba tình huống để tự đối chiếu

| Tình huống | Federation? | Có trải nghiệm SSO? |
| --- | --- | --- |
| Hai ứng dụng cùng tổ chức dùng một dịch vụ đăng nhập trung tâm, không có quan hệ tin cậy với tổ chức ngoài. | Không nhất thiết là federation xuyên tổ chức. | Có thể có, nhờ phiên IdP được tái sử dụng. |
| Cổng đối tác tin vào IdP của doanh nghiệp nhưng người dùng phải xác thực lại do chính sách bắt buộc. | Có. | Không “liền mạch” trong lần truy cập đó. |
| Cổng đối tác tin vào IdP của doanh nghiệp và IdP sử dụng phiên đang còn hiệu lực. | Có. | Thường có, nếu các điều kiện bảo mật cho phép. |

## 3. SSO hoạt động thế nào trong mô hình federation?

Hãy tưởng tượng hai ứng dụng **App A** và **App B**, mỗi ứng dụng được đăng ký làm OIDC Client riêng tại cùng một IdP.

~~~text
Trình duyệt người dùng         App A / App B                   IdP
        |                           |                            |
        |-- truy cập App A -------->|                            |
        |<-- chuyển hướng login ----|                            |
        |------------------------ đăng nhập / MFA --------------->|
        |<------------------- kết quả qua redirect ----------------|
        |-- callback cho App A ---->|-- đổi code / xác minh ----->|
        |                           |<-- ID Token / token --------|
        |<-- phiên riêng của A -----|                            |
        |                           |                            |
        |-- truy cập App B -------->|                            |
        |<-- chuyển hướng login ----|                            |
        |---------------------- yêu cầu tới IdP ----------------->|
        |<-- IdP dùng lại phiên nếu đủ điều kiện ------------------|
        |-- callback cho App B ---->|-- đổi code / xác minh ----->|
        |                           |<-- ID Token / token --------|
        |<-- phiên riêng của B -----|                            |
~~~

Ở lần đầu, người dùng cần thực sự đăng nhập với IdP. Sau đó, trình duyệt thường giữ cookie phiên của IdP theo chính sách của IdP. Khi App B chuyển trình duyệt sang IdP, IdP có thể nhận ra phiên này và hoàn tất yêu cầu mà không yêu cầu nhập lại mật khẩu. Mỗi ứng dụng vẫn thiết lập **phiên ứng dụng riêng** sau khi xử lý kết quả từ IdP.

Hệ quả cần nhớ:

- **Không dùng chung cookie phiên của App A với App B.** SSO thường xảy ra nhờ IdP xác thực người dùng cho nhiều ứng dụng, mỗi ứng dụng tự quản lý phiên của mình.
- **Không dùng chung ID Token hoặc Access Token một cách tùy tiện giữa các ứng dụng.** Token có đối tượng nhận, phạm vi, thời hạn và mục đích cụ thể.
- Nếu phiên IdP hết hạn, người dùng bị yêu cầu xác thực lại, hoặc bước MFA bắt buộc, lần vào App B vẫn có thể hiển thị đăng nhập.
- Nếu người dùng đang có phiên tại App A, việc hết phiên IdP không tự động làm phiên App A hết hiệu lực ngay; điều đó phụ thuộc thời hạn, cơ chế đồng bộ/logout của ứng dụng.

### “Một lần đăng nhập” kéo dài bao lâu?

Không có một thời gian SSO chung cho mọi ứng dụng. Nó chịu ảnh hưởng của **phiên IdP**, **phiên từng ứng dụng**, điều kiện tái xác thực (risk-based authentication, MFA, `max_age`/`prompt=login` trong OIDC khi được sử dụng), chính sách cookie và khả năng duy trì phiên khi trình duyệt điều hướng giữa các miền. Do đó cần định nghĩa yêu cầu SSO bằng hành vi và chính sách kiểm chứng được, thay vì hứa “đăng nhập một lần là vĩnh viễn”.

## 4. Giao thức: SAML 2.0, OIDC và OAuth 2.0

| Cơ chế | Mục đích chính | Dữ liệu/luồng tiêu biểu | Bối cảnh thường gặp |
| --- | --- | --- | --- |
| **SAML 2.0 Web Browser SSO** | Truyền thông tin xác thực giữa IdP và SP. | SAML AuthnRequest/Response chứa assertion XML, ký số. | Enterprise SSO và nhiều tích hợp B2B truyền thống. |
| **OpenID Connect (OIDC)** | Lớp xác thực danh tính xây trên OAuth 2.0. | Authorization Code Flow, ID Token (thường là JWT), user claims. | Ứng dụng web, mobile, hệ thống hiện đại. |
| **OAuth 2.0** | Ủy quyền truy cập tài nguyên/API. | Access token, scopes, token endpoint. | Client gọi API thay mặt người dùng hoặc ứng dụng. |

**Phân biệt rất quan trọng:** OAuth 2.0 tự nó là khung *ủy quyền*; không phải đặc tả chuẩn để “đăng nhập người dùng”. Khi cần xác thực danh tính người dùng theo mô hình chuẩn hóa, dùng **OIDC** (scope `openid` và xác minh ID Token) hoặc giao thức xác thực tương đương. Access token dành cho **resource server/API**; ID Token dành cho **OIDC Client/RP** và không nên gửi ID Token như bearer token để gọi API.

### 4.1. OIDC Authorization Code Flow (ứng dụng web server-side)

1. Người dùng yêu cầu trang được bảo vệ ở RP.
2. RP tạo yêu cầu tới authorization endpoint của IdP, gắn `client_id`, `redirect_uri`, `scope=openid`, `state` và các tham số bảo vệ phù hợp.
3. IdP kiểm tra phiên, có thể yêu cầu đăng nhập/MFA/đồng ý chia sẻ thông tin.
4. IdP chuyển trình duyệt về callback đã đăng ký, kèm **authorization code** và `state`.
5. RP kiểm tra state, dùng back-channel HTTPS đổi code tại token endpoint.
6. RP xác minh ID Token, đặc biệt là issuer (`iss`), audience (`aud`), chữ ký, thời hạn (`exp`), nonce khi áp dụng; thư viện còn xử lý các ràng buộc giao thức khác.
7. RP ánh xạ danh tính nhận được thành người dùng/quyền nội bộ theo chính sách; Spring Security lưu Authentication vào security context và quản lý phiên ứng dụng.
8. Truy cập tiếp theo vào RP có thể dùng phiên RP mà không lặp toàn bộ luồng. Khi vào một RP khác, IdP có thể tái sử dụng phiên IdP: đó là khả năng SSO.

**PKCE** giúp ràng buộc authorization code với client khởi tạo yêu cầu; cần dùng theo loại client và hồ sơ an toàn hiện hành. `state` bảo vệ luồng trả về khỏi việc ghép nhầm yêu cầu, `nonce` giúp ràng buộc ID Token với phiên xác thực OIDC khi áp dụng. Không nên tự hiện thực xác minh token hoặc xử lý callback bằng code thủ công khi Spring Security đã hỗ trợ.

### 4.2. SAML 2.0 Web Browser SSO

Luồng tương đương về ý tưởng: SP chuyển người dùng sang IdP bằng **AuthnRequest** (nếu SP-initiated); IdP trả **SAML Response/Assertion** qua trình duyệt tới **Assertion Consumer Service (ACS)** của SP; SP kiểm tra chữ ký và các điều kiện của assertion rồi tạo phiên ứng dụng. Cần chú ý **entity ID/issuer**, certificate tin cậy, audience, recipient, `InResponseTo`, hiệu lực thời gian và cấu hình ACS. OIDC và SAML khác về đối tượng/định dạng chứng thực; không nên lấy giả định xác minh JWT của OIDC áp vào XML assertion của SAML.

## 5. Liên kết danh tính bao gồm nhiều hơn giao thức đăng nhập

Một quan hệ federation đúng nghĩa đòi hỏi trả lời được:

1. **Tin ai?** Ứng dụng chấp nhận issuer/IdP nào, môi trường/tenant nào, bộ khóa chứng thực nào? Không chấp nhận issuer tùy ý do request tự truyền đến.
2. **Xác thực cái gì?** Chữ ký, người nhận, callback, thời hạn, request correlation và yêu cầu mức độ xác thực/MFA.
3. **Ai là tài khoản nội bộ?** Dựa vào định danh ổn định từ IdP, không dựa đơn thuần vào tên hiển thị hoặc email.
4. **Được làm gì?** Vai trò và quyền được cấp ở phía ứng dụng hoặc qua chính sách mapping được phê duyệt.
5. **Tài khoản đổi/trạng thái nghỉ việc xử lý thế nào?** Quy trình provision/deprovision, đồng bộ groups/roles, vô hiệu hóa phiên, audit và yêu cầu tái xác thực.
6. **IdP gặp sự cố thì sao?** Xử lý thời gian chờ, thông báo lỗi và chiến lược vận hành mà không mở đường bypass xác thực.

### Khóa định danh: issuer + subject

Trong OIDC, định danh an toàn để đối chiếu tài khoản thường được thiết kế từ **issuer (`iss`) + subject (`sub`)** trong ngữ cảnh RP được đăng ký, thay vì chỉ dùng `email`. Email có thể thay đổi, được tái sử dụng hoặc chưa được xác minh; `email_verified` nếu có cũng không thay thế mọi kiểm tra chính sách. Với pairwise subject, cùng một người có thể có các `sub` khác nhau giữa các RP, nên **không tự giả định mọi ứng dụng sẽ nhận cùng một subject**.

~~~text
Bảng ánh xạ nội bộ (minh họa)
provider_issuer                         external_subject        local_user_id
https://idp.example.org/realms/acme     u-7c93a1                1842
~~~

Sau khi xác thực, Spring Security biết principal nào đang đăng nhập. Việc ánh xạ principal thành tài khoản nghiệp vụ, cấp quyền phòng ban hoặc tạo tài khoản theo kiểu Just-in-Time (JIT) là **quyết định của ứng dụng**, cần quy tắc rõ ràng. Không tự cấp quyền quản trị chỉ từ một email có domain giống công ty.

## 6. Ví dụ Spring Security: ứng dụng đóng vai trò OIDC Relying Party

Ví dụ độc lập dùng **Java 17 + Spring Boot 3.3.x / Spring Security 6.x**, kiểu ứng dụng Servlet (Spring MVC). Đây là một ứng dụng RP, **không phải triển khai IdP**. Muốn hoàn tất đăng nhập, cần một OIDC IdP thật, có discovery endpoint hoạt động và đã đăng ký client tương ứng.

### 6.1. Cấu trúc dự án

~~~text
sso-federation-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/federationdemo/
    │   ├── FederationDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── resources/application.yml
~~~

`settings.gradle`

~~~groovy
rootProject.name = 'sso-federation-demo'
~~~

`build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Ba dependency có vai trò khác nhau: **Web** nhận HTTP request; **Security** thực thi chính sách bảo vệ endpoint; **OAuth2 Client** cung cấp luồng OAuth2 Login/OIDC, client registration và xử lý callback. Nếu bạn chỉ muốn một REST API nhận bearer access token từ client khác, đó là bài toán **OAuth2 Resource Server** và cấu hình khác với ví dụ login này.

### 6.2. Chương trình khởi động

`src/main/java/com/example/federationdemo/FederationDemoApplication.java`

~~~java
package com.example.federationdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederationDemoApplication.class, args);
    }
}
~~~

### 6.3. Bật OAuth2 Login và bảo vệ tài nguyên

`src/main/java/com/example/federationdemo/SecurityConfig.java`

~~~java
package com.example.federationdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

- Đường dẫn `/` công khai; `/me` được bảo vệ bởi quy tắc còn lại.
- `oauth2Login` khiến người dùng chưa xác thực được đưa vào luồng đăng nhập qua OIDC provider đã cấu hình.
- Spring Security xử lý các endpoint và callback mặc định; **không cần tự viết controller xử lý authorization code**.
- Mẫu này chỉ yêu cầu đăng nhập; các endpoint nhạy cảm phải bổ sung **authorization theo vai trò/quyền** phù hợp. Quy tắc `authenticated()` không đồng nghĩa đã có quyền nghiệp vụ.
- Với ứng dụng dùng phiên và form/HTTP POST, giữ bảo vệ CSRF mặc định; không tắt CSRF chỉ để “sửa lỗi đăng nhập”.

### 6.4. Hiển thị định danh được chứng thực

`src/main/java/com/example/federationdemo/DemoController.java`

~~~java
package com.example.federationdemo;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Open /me to sign in through the IdP";
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
~~~

`OidcUser` biểu diễn người dùng đã xác thực qua OIDC; ví dụ chỉ xuất **issuer và subject** để quan sát quan hệ tin cậy. Không trả về access token, ID Token đầy đủ, refresh token hoặc claim nhạy cảm ở endpoint demo hay log sản xuất.

### 6.5. Khai báo OIDC Client và IdP

`src/main/resources/application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-idp
            client-id: YOUR_CLIENT_ID
            client-secret: YOUR_CLIENT_SECRET
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
        provider:
          corp-idp:
            issuer-uri: https://idp.example.org/realms/acme
~~~

Đây là **các giá trị mẫu**, không phải IdP đang hoạt động. Thay `issuer-uri` bằng issuer URL thực do IdP công bố, và nạp `client-id`/`client-secret` qua biến môi trường hoặc secret manager khi triển khai, tránh commit bí mật vào Git. Với IdP có OIDC discovery, Spring có thể lấy endpoints và khóa công khai từ metadata của issuer; issuer và HTTPS phải được cấu hình/kiểm tra chính xác.

Tại phía IdP, tạo một confidential web client và đăng ký redirect URI cho môi trường local:

~~~text
http://localhost:8080/login/oauth2/code/corp
~~~

`corp` là `registrationId`, không phải tên người dùng. Endpoint khởi tạo đăng nhập mặc định:

~~~text
http://localhost:8080/oauth2/authorization/corp
~~~

URI callback mặc định dùng mẫu `{baseUrl}/login/oauth2/code/{registrationId}`. Khi chạy sau reverse proxy, phải bảo đảm base URL, HTTPS, host và forwarded headers phản ánh URL công khai đúng; URI chuyển hướng **phải khớp chính sách allow-list của IdP**.

### 6.6. Chạy và quan sát

Với Gradle đã cài trên máy (hoặc Gradle Wrapper tương ứng đã được tạo cho dự án):

~~~bash
gradle bootRun
~~~

Sau khi IdP và client được cấu hình đúng:

1. Mở `http://localhost:8080/`: nhận thông điệp công khai.
2. Mở `http://localhost:8080/me`: ứng dụng đưa bạn vào luồng OIDC; IdP xác thực người dùng nếu chưa có phiên phù hợp.
3. Sau callback hợp lệ, `/me` trả JSON có `issuer` và `subject` của người dùng thực. Giá trị phụ thuộc IdP và tài khoản nên **không có stdout/JSON cố định để sao chép**.
4. Đăng ký thêm một ứng dụng RP thứ hai tại cùng IdP, với client ID và redirect URI của chính nó. Truy cập RP thứ hai trong cùng trình duyệt khi phiên IdP còn hiệu lực để quan sát SSO. **Một RP đơn lẻ chưa chứng minh được tính năng SSO giữa nhiều ứng dụng.**

Nếu không có client/issuer hợp lệ, ứng dụng có thể không khởi động hoặc không hoàn tất đăng nhập; đó là điều kiện tích hợp bên ngoài chứ không phải chứng cứ SSO đã hoạt động.

## 7. Ba lớp phiên và vòng đời đăng xuất

Cần tách riêng ba trạng thái:

| Trạng thái | Được quản lý bởi | Tác dụng |
| --- | --- | --- |
| **Phiên IdP** | IdP trong trình duyệt/hệ thống IdP. | Cho phép IdP xác định người dùng đã xác thực khi RP khác chuyển hướng về. |
| **Phiên RP/App A** | App A / Spring Security và hạ tầng phiên của App A. | Cho phép request tiếp theo tới App A được nhận diện mà không phải quay lại IdP mỗi lần. |
| **Phiên RP/App B** | App B. | Độc lập với App A; chỉ có thể được tạo sau khi App B xử lý kết quả xác thực phù hợp. |

**Local logout** khỏi App A thường xóa phiên App A, nhưng **không mặc nhiên hủy phiên IdP hoặc App B**. Khi quay lại App A, phiên IdP có thể khiến người dùng đăng nhập lại tức thì theo SSO. **Single Logout (SLO)** là một khả năng riêng, phụ thuộc giao thức, hỗ trợ của IdP/RP và cấu hình triển khai (ví dụ RP-initiated logout với OIDC hoặc SAML logout). Không hứa “logout ở một ứng dụng là logout mọi nơi” nếu chưa thiết kế và kiểm thử.

Nếu doanh nghiệp có yêu cầu nhân viên nghỉ việc phải mất quyền ngay, chỉ xóa tài khoản ở IdP chưa đủ để bảo đảm mọi phiên RP kết thúc ngay. Cần xét TTL phiên tại RP, chính sách thu hồi, cơ chế back-channel/front-channel logout nếu tương thích, và vô hiệu hóa quyền nội bộ.

## 8. Các điểm kiểm tra bảo mật và vận hành

1. **Issuer và đối tượng nhận:** Chỉ tin các issuer được cấu hình; đối chiếu audience/client ID và các claims bắt buộc. Không tin token chỉ vì giải mã JWT thành công.
2. **Chữ ký và thời gian:** Dùng thư viện chuẩn xác minh chữ ký, khóa tin cậy/JWKS, `exp`, `nbf` và dung sai đồng hồ phù hợp; xử lý xoay vòng khóa ký.
3. **State, nonce, PKCE, callback:** Tuân thủ profile OIDC/OAuth2 tương ứng; cố định allow-list redirect URI, chống CSRF/login CSRF và mã độc điều hướng.
4. **TLS và cookie:** Dùng HTTPS trong triển khai, cookie phiên có thuộc tính Secure/HttpOnly/SameSite phù hợp; hiểu ảnh hưởng của chính sách trình duyệt đối với các luồng SSO.
5. **Phân quyền tách biệt xác thực:** Không gán vai trò admin tự động chỉ vì IdP trả email/nhóm tùy ý; xác định nguồn quyền, quy tắc mapping, tenant boundary và xử lý giảm quyền.
6. **Liên kết tài khoản:** Ưu tiên định danh ổn định (`iss` + `sub` trong ngữ cảnh RP), chính sách xác minh trước khi ghép tài khoản hiện có; phòng account takeover do ghép theo email đơn thuần.
7. **Quản lý bí mật:** Bảo vệ client secret, refresh token và session store; đặt least privilege cho scopes; không ghi token hoặc PII nhạy cảm vào log.
8. **MFA và chính sách tái xác thực:** SSO giảm nhập lại mật khẩu nhưng không đồng nghĩa bỏ MFA. Với thao tác có rủi ro, áp dụng yêu cầu xác thực mạnh hoặc xác thực lại theo chính sách IdP.
9. **Khả dụng và giám sát:** IdP trở thành điểm phụ thuộc chung; giám sát lỗi discovery, JWKS, redirect mismatch, đồng bộ thời gian và thay đổi cấu hình.
10. **Giới hạn trách nhiệm:** OIDC/SAML chứng thực danh tính cho RP; việc kiểm tra quyền truy cập tài nguyên trong ứng dụng vẫn phải có và được kiểm thử độc lập.

## 9. Bài thực hành và tiêu chí chấp nhận

Thiết lập **RP A** và **RP B** với client registration riêng tại cùng IdP thử nghiệm (mỗi RP có redirect URI chính xác). Thực hiện theo trình tự sau:

| Thử nghiệm | Thao tác | Kết quả cần kiểm tra |
| --- | --- | --- |
| Đăng nhập ban đầu | Mở RP A trong cửa sổ mới/chưa có phiên. | Trình duyệt tới IdP; sau xác thực, RP A có phiên hợp lệ. |
| SSO | Giữ phiên IdP, mở RP B. | IdP có thể cho qua mà không nhập lại mật khẩu; RP B tạo phiên riêng. Tùy chính sách có thể yêu cầu MFA. |
| Phân biệt phiên | Logout cục bộ tại RP A, giữ phiên IdP. | RP A mất phiên; RP B không nhất thiết bị ảnh hưởng; vào lại A có thể đăng nhập nhanh qua IdP. |
| Đăng xuất IdP | Xóa/kết thúc phiên IdP theo cách IdP hỗ trợ. | Lần xác thực *mới* cần đáp ứng chính sách IdP; phiên RP còn sống có thể vẫn hoạt động tới khi hết hạn/được thu hồi. |
| Bảo vệ tài nguyên | Gọi API nghiệp vụ không có quyền dù đã login. | RP từ chối truy cập theo authorization, không cấp quyền chỉ vì có SSO. |
| Cấu hình sai | Thử redirect URI hoặc issuer không khớp. | Luồng đăng nhập bị từ chối; không “bỏ qua xác minh để chạy được”. |
| Danh tính thay đổi | Đổi email/display name tại IdP, giữ subject ổn định. | Mapping người dùng không bị gắn nhầm với người khác chỉ vì đổi email. |

Khi đánh giá, cần phân biệt **sự kiện quan sát được** (có bị hỏi đăng nhập lần nữa không, phiên nào còn sống) với **nguyên nhân** (chính sách IdP, cookie, MFA, TTL, logout). Không dùng mỗi lần kiểm tra trên một trình duyệt để kết luận mọi user/browser đều nhận SSO giống nhau.

## 10. Những hiểu lầm phổ biến

**“SSO là các app dùng chung một mật khẩu.”** Không. SSO là cơ chế/ trải nghiệm xác thực qua điểm tin cậy chung; ứng dụng không nên nhận hoặc lưu mật khẩu của IdP.

**“Có federation thì chắc chắn không bao giờ phải đăng nhập lại.”** Sai. Federation tạo quan hệ tin cậy; IdP vẫn có thể bắt đăng nhập lại do hết phiên, MFA, thay đổi rủi ro hoặc yêu cầu ứng dụng.

**“OAuth2 Access Token là bằng chứng chuẩn về người dùng để login.”** Không chính xác. Access token cấp quyền gọi resource server; dùng OIDC và ID Token khi cần xác thực danh tính theo OIDC.

**“App B có thể dùng lại cookie phiên của App A.”** Thông thường không và không nên thiết kế như vậy. Hai ứng dụng tạo phiên riêng; IdP giúp hoàn tất xác thực với ít tương tác người dùng.

**“Nhận email từ IdP là đủ để ghép mọi tài khoản.”** Không. Email không phải khóa định danh bất biến; cần quy tắc liên kết dựa trên issuer/subject và chính sách xác minh.

**“Logout một app sẽ logout tất cả.”** Không mặc định. Cần thiết kế Single Logout và kiểm tra kết quả theo từng IdP/RP.

**“Spring Security cấu hình oauth2Login là đã có hệ thống IdP.”** Không. `oauth2Login` cấu hình ứng dụng làm OIDC/OAuth2 client; IdP là hệ thống khác và phải được đăng ký/thiết lập tin cậy.

## Tóm tắt kiến thức trọng tâm

- **SSO** nói về việc giảm yêu cầu đăng nhập lại khi truy cập nhiều ứng dụng.
- **Federation** nói về việc các bên chấp nhận kết quả xác thực từ một nguồn danh tính được tin cậy; federation thường là nền tảng để cung cấp SSO xuyên ranh giới.
- **OIDC/SAML** chuyển bằng chứng về danh tính từ IdP đến RP/SP; **OAuth2** tập trung vào ủy quyền tài nguyên.
- **Phiên IdP và phiên từng ứng dụng độc lập**; logout và thu hồi quyền cần thiết kế riêng.
- **Spring Security oauth2Login** giúp RP tham gia OIDC login, nhưng ứng dụng vẫn phải quản lý account mapping, authorization và bảo mật phiên.

### Tài liệu tham khảo chính thức

- [Spring Security – OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security – OAuth2 Login / OIDC](https://docs.spring.io/spring-security/reference/servlet/oauth2/)
- [Spring Security – SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
