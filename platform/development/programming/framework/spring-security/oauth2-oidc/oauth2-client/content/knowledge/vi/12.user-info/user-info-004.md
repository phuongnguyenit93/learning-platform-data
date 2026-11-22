# 12.4. User-name-attribute và lựa chọn định danh principal

## 1. Vấn đề: ứng dụng nên gọi người dùng là ai sau khi đăng nhập OIDC?

Giả sử một ứng dụng **Employee Portal** được xây dựng bằng **Spring Boot** và **Spring Security OAuth 2.0 Client**. Người dùng chọn đăng nhập qua OpenID Provider (**OP**) của công ty. Sau khi Authorization Code Flow hoàn tất, ứng dụng nhận được thông tin người dùng:

~~~json
{
  "sub": "a1c9f22b-8b27-41d7-84e1-0cd741df7a60",
  "preferred_username": "minh.nguyen",
  "name": "Nguyễn Văn Minh",
  "email": "minh.nguyen@example.test",
  "email_verified": true
}
~~~

Vậy ứng dụng nên sử dụng giá trị nào khi gọi `Authentication.getName()`, lưu bảng người dùng hoặc hiển thị trên giao diện?

- `sub` là **subject identifier** do OP cấp.
- `preferred_username` thường thuận tiện để hiển thị hoặc tìm kiếm.
- `email` là địa chỉ liên hệ; có thể thay đổi hoặc được tái sử dụng tùy chính sách.
- `name` là tên người dùng để hiển thị; có thể trùng giữa nhiều người.

Nếu nhầm **tên hiển thị**, **tên principal của Spring Security** và **định danh nội bộ dùng để liên kết tài khoản**, hệ thống có thể sinh các lỗi khó phát hiện: một tài khoản bị nhân đôi khi đổi email, hai người bị ghép nhầm vì trùng tên, token đã cấp không tìm lại được theo principal name, hoặc đăng nhập từ hai IdP bị đồng nhất sai.

Trong Spring Security, property **`user-name-attribute`** giúp chọn **thuộc tính dùng làm tên principal** khi xây dựng `OAuth2User`/`OidcUser`. Tuy nhiên, đó **không phải** cơ chế tự động xác minh danh tính, liên kết tài khoản nội bộ hoặc phân quyền.

> Ví dụ sử dụng **Java 17+, Spring Boot 3 và Spring Security 6**, ứng dụng web **Servlet/Spring MVC** đăng nhập qua OIDC. Địa chỉ, ID và claim chỉ là dữ liệu minh họa. Với hệ thống thật, phải kiểm tra claims, scope và hợp đồng của IdP được lựa chọn.

## 2. Phân biệt bốn khái niệm dễ nhầm

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| **Principal object** | `OidcUser`, `OAuth2User` | Đối tượng biểu diễn người dùng đã được xác thực trong Spring Security |
| **Principal name** | Kết quả `Authentication.getName()` | Chuỗi định danh mà nhiều thành phần Spring Security đọc để ghi log hoặc tra authorized client |
| **External identity key** | Cặp `(iss, sub)` | Khóa liên kết ổn định giữa tài khoản ở OP và tài khoản trong ứng dụng |
| **Display name** | `Nguyễn Văn Minh` hoặc `minh.nguyen` | Thông tin trình bày trên UI; thường có thể thay đổi |

Trong một lần đăng nhập OIDC, **principal name** có thể mặc định bằng `sub`, còn **display name** được lấy từ `name` hoặc `preferred_username`. Hai giá trị không cần giống nhau.

Nếu Employee Portal có cơ sở dữ liệu riêng, ứng dụng còn có thể cấp **internal user ID**, ví dụ một UUID của bảng `users`. Internal ID đó cũng không nhất thiết trùng principal name hay `sub` của IdP.

~~~text
OIDC Provider
  iss = https://login.example.test/realms/company
  sub = a1c9f22b-8b27-41d7-84e1-0cd741df7a60
           │
           │ ánh xạ danh tính sau khi xác thực
           ▼
Employee Portal
  users.id = 8dc7... (internal UUID)
  display_name = "Nguyễn Văn Minh"
           │
           ▼
Ứng dụng sử dụng internal user ID cho nghiệp vụ
~~~

**Kết luận nền tảng:** không sử dụng display name để thay cho khóa xác thực/khóa liên kết danh tính.

## 3. OAuth2User, OidcUser và Authentication.getName()

Trên Servlet stack, sau khi Spring Security OAuth2 Login thành công, request thường có một `Authentication` thuộc loại `OAuth2AuthenticationToken`. Authentication này chứa principal và registration ID của OAuth Client đã sử dụng.

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String principalName = authentication.getName();

if (authentication instanceof OAuth2AuthenticationToken oauth) {
    String registrationId = oauth.getAuthorizedClientRegistrationId();
    // Ví dụ: "company".
}
~~~

Khi đăng nhập **OIDC**, principal thường là `OidcUser`, ví dụ `DefaultOidcUser`. Khi đăng nhập OAuth 2.0 **không có scope openid** và lấy thông tin từ UserInfo kiểu OAuth2, principal thường là `OAuth2User` (ví dụ `DefaultOAuth2User`).

Hai loại principal có những điểm khác biệt:

| Nội dung | `OAuth2User` | `OidcUser` |
|---|---|---|
| Mục đích | Mô hình người dùng dựa trên thông tin OAuth2 provider | Mô hình người dùng OIDC dựa trên ID Token và có thể có UserInfo |
| API tên principal | `getName()` | `getName()` |
| Các thuộc tính | `getAttributes()` | Claims OIDC, thông thường truy cập qua `getClaims()` |
| ID Token | Không phải thành phần bắt buộc | Có `getIdToken()` |
| UserInfo | Phụ thuộc provider và cấu hình | Có thể có `getUserInfo()` hoặc `null` |
| Subject | Phụ thuộc schema/provider | `sub` là claim cốt lõi trong ID Token |
| Tên mặc định | Cần thuộc tính tên phù hợp với provider | Thường dùng `sub` |

### 3.1. Authentication.getName() từ đâu ra?

Trong một lần đăng nhập OAuth2/OIDC được cấu hình chuẩn, `OAuth2AuthenticationToken.getName()` phản ánh tên của principal bên trong. Với `DefaultOidcUser`, `getName()` dựa trên khóa tên (`nameAttributeKey`) được cấu hình; mặc định thường là `sub`.

Điều đó có nghĩa:

~~~java
String valueA = authentication.getName();
String valueB = ((OidcUser) authentication.getPrincipal()).getName();
~~~

Trong ngữ cảnh Authentication chứa `OidcUser` như trên, hai giá trị đại diện cùng **principal name**. Chúng **không tự động là email** và cũng **không tự động là tên đầy đủ để hiển thị**.

### 3.2. Không coi registrationId là danh tính người dùng

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` có thể trả về `company`. Đây là ID của **OAuth Client registration**, không phải `sub` người dùng và không phải `client_id` đã đăng ký tại IdP.

Ví dụ:

~~~text
registrationId : company
client_id      : employee-portal
issuer         : https://login.example.test/realms/company
subject        : a1c9f22b-8b27-41d7-84e1-0cd741df7a60
~~~

Chỉ hai giá trị cuối, **issuer** và **subject**, hợp thành khóa định danh OIDC bên ngoài theo mô hình tin cậy phù hợp.

## 4. Nguồn dữ liệu: ID Token, UserInfo và hồ sơ ứng dụng

Trong OIDC Authorization Code Flow, **ID Token** là token mô tả một sự kiện xác thực người dùng tại OP, với các claim đã được kiểm tra theo quy tắc OIDC. Các claim nền tảng gồm:

- `iss`: issuer của OP.
- `sub`: subject identifier của người dùng tại OP.
- `aud`: đối tượng nhận ID Token, thường chứa client ID của Portal.
- `exp`, `iat`: thời gian liên quan đến hiệu lực token.

Tùy scope, consent và cấu hình nhà cung cấp, ID Token có thể chứa thêm thông tin hồ sơ; tuy nhiên không nên mặc định tất cả claim như email hoặc name luôn hiện diện trong ID Token.

**UserInfo endpoint** là endpoint OIDC để lấy thông tin bổ sung về người dùng bằng access token phù hợp. Response UserInfo thường có `sub`, và có thể có `preferred_username`, `email`, `name`, `picture`, v.v. theo chính sách OP.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Browser
    participant Portal as Spring Security OAuth2 Client
    participant OP as OpenID Provider
    participant DB as Portal User Database

    User->>Browser: Bắt đầu đăng nhập
    Browser->>Portal: GET /oauth2/authorization/company
    Portal-->>Browser: Chuyển đến OP
    Browser->>OP: Authentication/consent
    OP-->>Browser: Callback với authorization code
    Browser->>Portal: GET /login/oauth2/code/company?code=...
    Portal->>OP: Đổi code lấy token
    OP-->>Portal: ID Token, access token, ...
    Portal->>OP: GET UserInfo (khi cấu hình/điều kiện cho phép)
    OP-->>Portal: Claims hồ sơ
    Portal->>Portal: OidcUser có getName() và getClaims()
    Portal->>DB: Tìm external identity bằng (iss,sub)
    DB-->>Portal: Internal user ID
    Portal-->>Browser: Phiên đăng nhập ứng dụng
~~~

**UserInfo là nguồn dữ liệu hồ sơ**, không phải một bảng danh tính tùy ý để chọn email rồi bỏ qua ID Token. Trong OIDC, giá trị `sub` từ UserInfo phải nhất quán với subject của ID Token; nếu không khớp, không được dùng response đó để gắn với người dùng đã đăng nhập.

### 4.1. Khi nào UserInfo không có?

Tùy provider và cấu hình, Spring Security có thể không gọi UserInfo, hoặc UserInfo endpoint không được cung cấp/hỗ trợ, hoặc scope/consent không cho phép một số claim xuất hiện. Vì thế:

- `OidcUser.getUserInfo()` có thể bằng `null`.
- `OidcUser.getIdToken()` là nguồn đáng tin cậy cho `iss` và `sub` của giao dịch OIDC đã xác minh.
- `email`, `preferred_username` hoặc `name` có thể vắng mặt.

Không thiết kế dữ liệu nghiệp vụ theo giả định **UserInfo luôn có email** hoặc **email luôn verified**.

## 5. Property user-name-attribute của Spring Security

Trong Spring Boot, provider-specific settings có đường dẫn:

~~~text
spring.security.oauth2.client.provider.<provider-id>.user-name-attribute
~~~

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

Ý nghĩa của property:

1. Spring Boot bind giá trị đó vào metadata của `ClientRegistration.ProviderDetails.UserInfoEndpoint` tương ứng.
2. User service xử lý thông tin người dùng có thể dùng khóa này khi tạo `DefaultOAuth2User` hoặc `DefaultOidcUser`.
3. Giá trị được chọn ảnh hưởng đến tên principal mà `getName()` trả về, **không biến claim đó thành một danh tính đã được kiểm chứng bổ sung**.

**Đừng nhầm:** `user-name-attribute` là **tên key trong tập claims/attributes**, không phải giá trị username cố định. Khai báo `user-name-attribute: preferred_username` có nghĩa lấy **giá trị thuộc tính preferred_username** của người dùng, không phải đặt tên mọi principal là chuỗi `preferred_username`.

### 5.1. Default cho OIDC

Trong OIDC, khóa mặc định của `DefaultOidcUser` thường là **`sub`**. Vì `sub` thuộc nhóm claim bắt buộc của ID Token, đây là lựa chọn hợp lý để có một principal name gắn với subject.

Nếu provider cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            user-name-attribute: preferred_username
~~~

thì user service có thể chọn `preferred_username` làm name attribute **nếu claim đó tồn tại trong tập claims của principal**. Nếu provider không trả claim này (hoặc chỉ trả ở một nhánh cấu hình khác), việc lấy tên có thể không hoạt động như kỳ vọng. Không sử dụng property này để ép IdP phát hành một claim mới: **property chỉ chọn khóa, không cấp scope/claim**.

### 5.2. Provider ID không phải registration ID, dù có thể trùng

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

Trong ví dụ, **registration ID** là `portal-company`, **provider ID** là `company`. Property `user-name-attribute` đặt ở **provider.company**, không phải `registration.portal-company`.

Khi đăng nhập, URL thường là `/oauth2/authorization/portal-company`. Callback mặc định sẽ chứa registration ID nếu template sử dụng `{registrationId}`.

## 6. Cấu hình OIDC Client hoàn chỉnh với sub

Một cấu hình thực tế cho Portal:

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

Ở đây:

- **`openid`** cho biết client thực hiện OIDC login.
- **`profile`** và **`email`** yêu cầu những nhóm claim tương ứng theo OIDC; provider vẫn quyết định có phát hành/đưa chúng vào UserInfo hay không.
- **`user-name-attribute: sub`** chọn subject làm tên principal.
- **`OIDC_CLIENT_SECRET`** phải được cấp từ môi trường chạy/secret manager, không commit.
- **`issuer-uri`** là danh tính OP để Spring Security sử dụng khi discovery và xác minh theo cấu hình.

Dependency tối thiểu trên Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`SecurityFilterChain` cơ bản:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ứng dụng **server-side session login**. Callback mặc định do Spring Security xử lý ở `/login/oauth2/code/company`. Không cần tự tạo controller để đổi authorization code lấy ID Token, và không tắt CSRF toàn cục chỉ vì sử dụng đăng nhập liên kết.

## 7. Đọc principal đúng cách trong Controller

Spring Security cho phép lấy principal đã xác thực qua `@AuthenticationPrincipal`. Ví dụ một endpoint giới hạn cho người dùng đã đăng nhập:

~~~java
package com.example.portal.web;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(
        @AuthenticationPrincipal OidcUser user
    ) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("principalName", user.getName());
        result.put("subject", user.getSubject());
        result.put("displayName", preferredDisplayName(user));
        return result;
    }

    private String preferredDisplayName(OidcUser user) {
        String fullName = user.getFullName();
        if (fullName != null && !fullName.isBlank()) {
            return fullName;
        }
        String preferred = user.getPreferredUsername();
        if (preferred != null && !preferred.isBlank()) {
            return preferred;
        }
        return "Người dùng";
    }
}
~~~

Trong endpoint minh họa:

- `user.getName()` là tên principal theo cấu hình Spring Security.
- `user.getSubject()` là claim `sub` OIDC.
- `user.getFullName()` và `user.getPreferredUsername()` chỉ dùng cho **hiển thị**.

Không đưa thẳng toàn bộ `user.getClaims()`, ID Token hoặc access token về frontend chỉ để hiển thị tên người dùng. Claims có thể chứa thông tin cá nhân và token là credential nhạy cảm.

### 7.1. Nên trả định danh nào cho browser?

Endpoint `/me` ở trên cố ý trả `subject` để giúp người học quan sát. Trong production, nếu frontend chỉ cần tên hiển thị và thông tin tài khoản nội bộ, API thường nên trả **internal user ID**, **display name** và quyền/đặc tính đã được ứng dụng cho phép; không nhất thiết phơi bày `sub` của IdP.

**Không xem internal user ID là bí mật có thể thay thế authorization.** Dù là UUID khó đoán, mọi endpoint vẫn phải kiểm tra người gọi được phép đọc/sửa tài nguyên.

## 8. Khi nào không nên đổi user-name-attribute sang email?

Một thay đổi thường thấy:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            user-name-attribute: email
~~~

Người viết có thể muốn `Authentication.getName()` dễ đọc hơn. Vấn đề là email **không có cùng bảo đảm định danh như `sub`**.

### 8.1. Email có thể thay đổi

~~~text
Tháng 1:
  iss = https://login.example.test/realms/company
  sub = u-10293
  email = minh.nguyen@example.test

Tháng 6:
  iss = https://login.example.test/realms/company
  sub = u-10293
  email = minh.tran@example.test
~~~

Đây có thể vẫn là **một người dùng duy nhất** tại OP. Nếu ứng dụng dùng email làm primary key cho bảng liên kết tài khoản, nó dễ coi lần đăng nhập sau là tài khoản mới hoặc mất dữ liệu nghiệp vụ đã gắn trước đó.

### 8.2. Email không phải lúc nào cũng có hoặc được xác minh

Provider có thể không trả email; `email_verified` có thể là false hoặc không có. Ngay cả email đã được xác minh cũng không đảm bảo nó sẽ **không đổi**, **không tái cấp** hoặc **luôn duy nhất trên tất cả IdP**.

### 8.3. Email có thể trùng giữa hai issuer

Hai hệ thống danh tính:

~~~text
IdP A: iss=https://login.company-a.test; sub=4582; email=shared@example.test
IdP B: iss=https://login.company-b.test; sub=9901; email=shared@example.test
~~~

**Không tự động ghép tài khoản** chỉ vì email giống nhau. Liên kết hai external identities vào cùng internal user cần một quy trình có kiểm tra quyền sở hữu và chủ đích của ứng dụng.

### 8.4. Principal name ảnh hưởng đến dữ liệu kỹ thuật

Một số triển khai của `OAuth2AuthorizedClientService` lưu authorized client theo **registration ID và principal name**. Nếu principal name đổi từ `sub` sang `email` hoặc email thay đổi, cách tra authorized client có thể thay đổi theo.

Do đó, thay `user-name-attribute` không chỉ thay chuỗi hiển thị; nó có thể ảnh hưởng tới session, audit log, việc tra token đã cấp và các chỗ phụ thuộc `Authentication.getName()`.

**Lựa chọn khuyến nghị:** giữ định danh ổn định cho principal name khi có thể, còn tên dễ đọc lấy từ claim hồ sơ riêng.

## 9. Lựa chọn định danh: sub, preferred_username, email hay name?

| Thuộc tính | Ưu điểm | Hạn chế | Vai trò khuyến nghị |
|---|---|---|---|
| **sub** | Subject do OP cấp; không nhằm hiển thị; định danh theo issuer | Có thể khó đọc; không duy nhất toàn cầu nếu thiếu issuer | Làm thành phần chính của external identity key |
| **iss + sub** | Phân biệt người dùng theo đúng issuer đã phát hành danh tính | Phải quản lý issuer nhất quán, migration và cấu trúc dữ liệu | Khóa liên kết bên ngoài khi dùng OIDC |
| **preferred_username** | Dễ nhận biết, thường giống tài khoản đăng nhập | Có thể đổi/trùng/vắng mặt, tùy provider | Tên hiển thị hoặc tên gợi ý |
| **email** | Phục vụ liên hệ, tìm kiếm và thông báo | Có thể đổi, tái cấp hoặc chưa xác minh | Thuộc tính hồ sơ; liên kết chỉ với quy trình kiểm chứng riêng |
| **name** | Thân thiện với người dùng | Không duy nhất, ngôn ngữ/dấu/định dạng thay đổi | Tên đầy đủ để hiển thị |
| **Internal user ID** | Do ứng dụng quản lý, độc lập với IdP | Cần bảng ánh xạ và quy trình cấp phát | Primary key của dữ liệu nghiệp vụ |

Không có claim nào trong bảng tự động trở thành **role/permission**. Spring Security dùng **authorities** và chính sách phân quyền cho việc cho phép truy cập; name attribute chỉ giải quyết **cách gọi principal**.

## 10. Vì sao khóa ngoài nên gồm cả issuer và subject?

Trong OIDC, `sub` được xác định **trong phạm vi của issuer**. Không nên giả định hai issuer khác nhau không thể phát cùng chuỗi subject.

Ví dụ:

~~~text
Issuer: https://login.company-a.test
Subject: 123456

Issuer: https://login.company-b.test
Subject: 123456
~~~

Hai cặp này đại diện cho **hai external identities khác nhau**.

Mô hình dữ liệu khuyến nghị:

~~~text
ExternalIdentity
  issuer  = https://login.company-a.test
  subject = 123456
  user_id = 8dc7... (internal user)
~~~

Với cơ sở dữ liệu quan hệ, có thể xây dựng bảng:

~~~sql
CREATE TABLE app_user (
    id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(255),
    email VARCHAR(320),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE external_identity (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_ext_identity_user
        FOREIGN KEY (user_id) REFERENCES app_user(id),
    CONSTRAINT uq_ext_identity_iss_sub
        UNIQUE (issuer, subject)
);
~~~

Đây là mô hình minh họa, không áp đặt loại SQL/dialect hoặc cách lưu UUID. Ý tưởng chính:

1. Một **internal user** có ID riêng dùng trong dữ liệu nghiệp vụ.
2. Bảng `external_identity` liên kết từng external identity với internal user.
3. Constraint `UNIQUE (issuer, subject)` ngăn một external identity bị ánh xạ trùng sang hai user.
4. Nếu cần liên kết nhiều IdP, có thể thêm nhiều dòng external identity cùng trỏ về một internal user **sau khi xác minh chủ sở hữu và áp dụng chính sách liên kết tài khoản**.

### 10.1. Bảo toàn giá trị issuer/subject

Với giá trị nhận từ ID Token đã được framework xác thực:

- Dùng issuer **đúng như danh tính IdP đã được tin cậy**, không tự thay bằng URL authorization endpoint hoặc tên miền rút gọn.
- Xử lý `sub` như **opaque string**: không parse thành email/username/ID số, không đổi chữ hoa–thường hoặc cắt khoảng trắng tùy tiện.
- Không tự chuẩn hóa issuer bằng cách xóa path, realm hoặc thay slash mà không có chính sách rõ.
- Nếu tổ chức di chuyển issuer/tenant, thực hiện migration/linking có kiểm soát thay vì giả định sub giữ nguyên.

**Pairwise subject:** một số OP phát `sub` khác nhau cho cùng người dùng giữa các client hoặc sector identifier. Vì vậy **issuer+sub** là khóa tốt cho **danh tính mà client này nhận được**, không phải một số định danh con người dùng chung mọi ứng dụng bất kể OP configuration.

## 11. Lấy issuer và subject đáng tin cậy từ OidcUser

Trong ứng dụng OIDC đã cấu hình đúng, `OidcUser` cho phép truy cập ID Token:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ExternalIdentityKey(String issuer, String subject) {

    public static ExternalIdentityKey from(OidcUser user) {
        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getIdToken().getSubject();
        return new ExternalIdentityKey(issuer, subject);
    }
}
~~~

Khi sử dụng `ExternalIdentityKey.from(user)`, ứng dụng phải bảo đảm `user` thực sự đến từ luồng OIDC login đã được xác minh bởi Spring Security; không tự tạo `OidcUser` từ JSON body do client gửi.

**Vì sao lấy từ ID Token?** Nó chứa issuer và subject thuộc kết quả xác thực OIDC mà framework kiểm tra. Một request trực tiếp từ browser gửi `{"iss":"...","sub":"..."}` không mang bằng chứng xác thực tương đương.

Ứng dụng có thể lưu thêm `email`, `preferred_username`, `name` vào hồ sơ để hiển thị và cập nhật sau mỗi lần đăng nhập; nhưng không dùng các trường có thể đổi đó thay cho khóa external identity.

### 11.1. Không cần tự đọc JWT bằng Base64

Tránh quy trình:

~~~text
ID Token JWT
  -> Base64 decode payload
  -> lấy sub
  -> tin ngay người dùng đã xác thực
~~~

Base64 decoding **không xác minh chữ ký hoặc các claim bảo mật**. Khi ứng dụng sử dụng `oauth2Login()` tiêu chuẩn, hãy dựa trên principal đã được framework tạo sau khi hoàn tất xác thực OIDC, đồng thời giữ cấu hình issuer/client registration đúng và luôn cập nhật bản vá Spring Security theo quy trình.

## 12. Tùy biến principal name bằng OidcUserService

Trong một số sản phẩm, yêu cầu tích hợp buộc `Authentication.getName()` dùng `preferred_username` thay vì `sub`. Có thể dùng cấu hình `user-name-attribute` nếu provider luôn cấp claim phù hợp. Khi cần **logic fallback** hoặc quy tắc lựa chọn động, có thể tùy biến **OIDC user service**.

Spring Security Servlet cung cấp hook:

~~~java
http.oauth2Login(login -> login
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService))
);
~~~

Ví dụ giữ cơ chế load user chuẩn, chỉ thay name attribute khi claim hiện diện:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.util.StringUtils;

@Configuration
class CustomOidcPrincipalConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService() {
        OidcUserService delegate = new OidcUserService();

        return userRequest -> {
            OidcUser loaded = delegate.loadUser(userRequest);
            String username =
                loaded.getClaimAsString("preferred_username");

            if (!StringUtils.hasText(username)) {
                // Giữ principal mặc định thay vì gán tên rỗng.
                return loaded;
            }

            return new DefaultOidcUser(
                loaded.getAuthorities(),
                loaded.getIdToken(),
                loaded.getUserInfo(),
                "preferred_username"
            );
        };
    }
}
~~~

Cấu hình SecurityFilterChain sử dụng bean trên:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService
    ) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(customOidcUserService)))
            .build();
    }
}
~~~

**Đây là cấu hình thay thế** `SecurityFilterChain` ở mục 6, không phải chain thứ hai cần thêm nguyên văn vào cùng ứng dụng.

Phần quan trọng:

- `OidcUserService` mặc định tiếp tục xử lý OIDC UserInfo và xây dựng principal theo chính sách Spring Security.
- `DefaultOidcUser` được tạo với `nameAttributeKey = "preferred_username"` khi claim có mặt.
- Khi claim vắng mặt, giữ nguyên principal đã load; mặc định thông dụng là dùng `sub`.
- **issuer và subject trong ID Token không đổi** chỉ vì principal name thay đổi.
- Không tự tin tưởng claim do frontend gửi hoặc tự cấp authorities mới trong bước đặt tên.

**Lưu ý kiến trúc:** fallback tên principal ở trên là ví dụ kỹ thuật, không có nghĩa nên dùng username làm khóa lưu dữ liệu. Nếu yêu cầu chỉ là **hiển thị tên đẹp trên giao diện**, cách đơn giản và an toàn hơn là giữ `getName()` ổn định rồi lấy `getFullName()` hoặc `getPreferredUsername()` cho UI như mục 7.

## 13. user-name-attribute với OAuth2 Login không phải OIDC

Không phải mọi OAuth 2.0 provider đều hỗ trợ OIDC. Một OAuth2 provider có thể cung cấp user-info endpoint riêng với response:

~~~json
{
  "id": 98765,
  "login": "minhnguyen",
  "display_name": "Minh Nguyen",
  "email": "minh@example.test"
}
~~~

Response không có `sub`. Nếu registration dùng OAuth2 Login không có scope `openid`, Spring Security có thể tạo `DefaultOAuth2User` dựa trên user attributes; khi đó cần chỉ định attribute nào đóng vai trò principal name.

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          partner:
            authorization-uri: https://login.partner.example.test/oauth2/authorize
            token-uri: https://login.partner.example.test/oauth2/token
            user-info-uri: https://api.partner.example.test/v1/profile
            user-name-attribute: id
~~~

Đây là **ví dụ một provider OAuth2 tùy chỉnh**, không phải metadata thực của một dịch vụ có thật. IdP/Authorization Server phải hỗ trợ user-info endpoint và cách gửi bearer token tương ứng.

Với response `{"id":98765,...}`, Spring có thể chọn trường `id` làm tên principal. Tùy cơ chế `DefaultOAuth2User`, giá trị được chuyển thành chuỗi khi lấy tên.

**Khác biệt then chốt:**

- **OIDC:** có **ID Token** với `iss`, `sub` và cơ chế validation OIDC chuẩn; dùng cặp issuer/subject để ánh xạ danh tính bên ngoài.
- **OAuth2 thuần:** schema user-info phụ thuộc provider. Trường `id`, `login` hoặc `username` chỉ có ý nghĩa theo tài liệu provider, không tự được nâng lên thành claim OIDC `sub`.

Nếu tích hợp OAuth2 thuần, application cần thiết kế namespace của external identity (provider ID, đối tượng phát hành/nguồn đáng tin cậy, user identifier) dựa trên hợp đồng và khả năng thay đổi provider. Không tự ép mọi provider có cùng độ bảo đảm về danh tính như OIDC.

### 13.1. Vì sao cần user-name-attribute ở OAuth2 thuần?

Giả sử response có `id` nhưng provider không khai báo schema name mặc định. Nếu không chọn được thuộc tính làm tên, `DefaultOAuth2User` có thể không được xây dựng như mong đợi. Với provider tùy chỉnh, `user-name-attribute` thường là cấu hình quan trọng để Spring Security biết nên trả gì từ `getName()`.

Đặt tên key đúng với JSON: `id` không tương đương `user_id` hoặc `username` nếu provider không cung cấp những trường đó.

## 14. Nhiều OIDC Provider: tránh nhầm subject giữa các issuer

Giả sử Portal hỗ trợ:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Hai provider có cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          company:
            issuer-uri: ${COMPANY_ISSUER_URI}
            user-name-attribute: sub
          partner:
            issuer-uri: ${PARTNER_ISSUER_URI}
            user-name-attribute: sub
~~~

Đây là **ví dụ thay thế** cấu hình một provider ở mục 6, không phải phần cần dán nối vào cùng block YAML với key `spring.security.oauth2.client` trùng.

Hai principal có thể cùng trả `getName() = "12345"`:

~~~text
company: iss=https://login.company.example.test, sub=12345
partner: iss=https://login.partner.example.test, sub=12345
~~~

Điều đó không có nghĩa chúng là cùng một user. Khi ánh xạ đến cơ sở dữ liệu nội bộ, luôn sử dụng **issuer + subject** thay vì chỉ `Authentication.getName()`.

### 14.1. Việc dùng email để tự động link hai provider có an toàn không?

Không nên mặc định. Hai IdP có chính sách đăng ký/kiểm chứng email khác nhau, và một email có thể được tái cấp hoặc thuộc một tổ chức khác theo thời gian.

Nếu ứng dụng cho phép **link account**, nên yêu cầu người dùng đang xác thực ở một danh tính đáng tin cậy chủ động xác nhận việc liên kết với danh tính thứ hai, hoặc áp dụng quy trình quản trị đã được tổ chức phê duyệt. Có thể cần đánh giá **email_verified**, issuer, thời điểm xác thực và các yếu tố rủi ro khác, nhưng không coi mỗi email trùng là bằng chứng liên kết đủ mạnh.

## 15. Quy trình provisioning / mapping user khi login thành công

Khi OIDC login tạo `OidcUser`, ứng dụng có thể dùng một service nghiệp vụ để ánh xạ external identity vào internal user.

Quy trình:

~~~mermaid
flowchart TD
    A["OIDC login thành công, OidcUser đã xác minh"] --> B["Lấy iss và sub từ ID Token"]
    B --> C{"Đã có external_identity(iss,sub)?"}
    C -->|Có| D["Tải internal user ID đã liên kết"]
    C -->|Chưa| E{"Chính sách cho phép tự tạo user?"}
    E -->|Có| F["Tạo internal user và external identity trong transaction"]
    E -->|Không| G["Yêu cầu invitation/admin approval hoặc báo chưa được cấp quyền"]
    D --> H["Cập nhật thuộc tính hồ sơ được phép"]
    F --> H
    H --> I["Dùng internal user ID cho nghiệp vụ"]
~~~

**Không lấy email làm điều kiện duy nhất** ở bước C. Khóa tra cứu là issuer + subject.

Ví dụ service code dạng Java:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;

@Service
public class IdentityMappingService {

    private final ExternalIdentityRepository externalIdentities;

    public IdentityMappingService(
        ExternalIdentityRepository externalIdentities
    ) {
        this.externalIdentities = externalIdentities;
    }

    public String requireInternalUserId(OidcUser user) {
        ExternalIdentityKey key = ExternalIdentityKey.from(user);
        return externalIdentities
            .findInternalUserId(key.issuer(), key.subject())
            .orElseThrow(() ->
                new IllegalStateException("Account has not been provisioned"));
    }
}
~~~

Trong ví dụ này, `ExternalIdentityRepository` là abstraction do ứng dụng tự định nghĩa cho việc tra cứu database; Spring Security không tạo sẵn repository nghiệp vụ này. Mục tiêu là minh họa **cách dùng khóa danh tính**, không phải trình bày một ứng dụng persistence hoàn chỉnh.

Nếu tổ chức cho phép auto-provision, quá trình tạo user và external identity nên có transaction, uniqueness constraint và xử lý xung đột khi hai request đăng nhập cùng lúc. Không tạo nhiều account chỉ vì hai request cùng nhận thấy “chưa có user” trước khi commit.

### 15.1. Thông tin hiển thị cập nhật theo quy tắc riêng

Sau khi tìm được internal user, ứng dụng có thể cập nhật:

- `display_name` từ `name` hoặc `preferred_username`.
- `email` để liên hệ, kèm trạng thái xác minh.
- `picture` nếu chính sách cho phép hiển thị ảnh hồ sơ.

Thông tin này có thể thay đổi từ mỗi lần đăng nhập. Nếu ứng dụng cho phép người dùng tự chỉnh sửa hồ sơ, cần xác định **nguồn nào được ưu tiên** và những trường nào được đồng bộ từ IdP, tránh ghi đè thay đổi hợp lệ của người dùng.

## 16. Email_verified, scope và mức tin cậy của claim

OIDC hỗ trợ các claim hồ sơ như `email` và `email_verified`. Khi sử dụng:

~~~java
String email = user.getEmail();
Boolean emailVerified = user.getEmailVerified();
~~~

cần xem **emailVerified** theo dữ liệu thực tế, có thể bằng `null` nếu claim không được cung cấp. Không tự suy luận email đã được xác minh chỉ vì người dùng đăng nhập OIDC thành công.

Scope `email` là **yêu cầu truy cập các claim email theo chính sách provider**, không đảm bảo mọi request sẽ được cấp email. Tương tự, scope `profile` không đảm bảo `name` hoặc `preferred_username` luôn xuất hiện.

Nếu một quy trình yêu cầu email đã được xác minh (ví dụ gửi thông báo nhạy cảm), hãy xác định chính sách xử lý khi `email_verified` không có hoặc false. **Không dùng email_verified để thay thế việc kiểm tra authorization** cho các tài nguyên nghiệp vụ.

### 16.1. Không để user-name-attribute thành quyền truy cập

Ví dụ không an toàn:

~~~java
// Không phân quyền bằng chuỗi username dễ đổi:
if ("admin@example.test".equals(authentication.getName())) {
    // Cho phép thao tác quản trị
}
~~~

Một principal name có thể được cấu hình từ email hoặc preferred_username; các giá trị đó có thể đổi và không phải authority.

Thay vào đó, hệ thống cần **authorization policies** dựa trên roles/permissions đã được xác định từ nguồn tin cậy, qua quá trình mapping được kiểm soát:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasAuthority("PORTAL_ADMIN")
    .anyRequest().authenticated()
);
~~~

Việc cấp `PORTAL_ADMIN` phải được ứng dụng quản lý riêng. Đặt `user-name-attribute: email` không tự tạo hoặc thay đổi authority.

## 17. Tác động tới OAuth2AuthorizedClient và session

Sau khi OAuth2 Login thành công, ứng dụng có thể lưu `OAuth2AuthorizedClient` chứa access token và refresh token nếu được cấp.

Một số cơ chế lưu authorized client tổ chức dữ liệu theo:

~~~text
clientRegistrationId + principalName
~~~

Ví dụ:

~~~text
company + a1c9f22b-8b27-41d7-84e1-0cd741df7a60
~~~

Nếu sau đó đổi cấu hình `user-name-attribute` sang `email`, tên principal có thể thành `minh.nguyen@example.test`. Những dữ liệu tra theo tên cũ có thể không còn được tìm thấy theo cùng khóa.

Hậu quả tùy cách lưu trữ:

- Authorized client cũ có thể không được lookup bằng principal name mới.
- Cơ chế refresh hoặc lấy token ở request tiếp theo có thể hoạt động khác dự kiến.
- Log và audit có thể xuất hiện hai giá trị principal name cho cùng người dùng.
- Logic ứng dụng tự dùng `Authentication.getName()` làm khóa dữ liệu có thể thấy một “tài khoản mới” giả.

**Thay name attribute trong hệ thống đã chạy là thay đổi có tác động vận hành**, không đơn thuần là đổi tên hiển thị. Cần xác định phạm vi dữ liệu cũ, kế hoạch migration hoặc yêu cầu đăng nhập lại và cách kiểm tra thực tế.

### 17.1. Khi principal name là sub nhưng có nhiều provider

Nếu hệ thống có nhiều OIDC issuer, `getName()` từ hai user có thể trùng chuỗi `sub`. Với dữ liệu nghiệp vụ, dùng `(iss,sub)`. Với storage của authorized client, cần hiểu thêm registration ID, principal name và schema lưu trữ mà phiên bản Spring Security/deployment đang sử dụng.

Không tự cho rằng principal name mặc định đã là một khóa danh tính **toàn hệ thống**.

## 18. Tùy biến tên hiển thị mà không đổi principal name

Trong phần lớn ứng dụng, nhu cầu là hiển thị “Xin chào Minh” chứ không phải thay đổi danh tính kỹ thuật. Có thể viết một service chuyên xử lý display name:

~~~java
package com.example.portal.profile;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;

@Service
public class DisplayNameService {

    public String getDisplayName(OidcUser user) {
        String name = user.getFullName();
        if (hasText(name)) {
            return name;
        }

        String username = user.getPreferredUsername();
        if (hasText(username)) {
            return username;
        }

        return "Người dùng";
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

Khi dùng, ứng dụng vẫn giữ:

~~~text
OidcUser.getName()         -> subject (khóa tên principal kỹ thuật)
DisplayNameService         -> "Nguyễn Văn Minh"
ExternalIdentityKey        -> (issuer, subject)
App User ID                -> UUID nội bộ
~~~

Đó là mô hình **phân tách trách nhiệm** rõ ràng hơn việc đổi `user-name-attribute` để mọi nơi lấy tên dễ đọc.

**Lưu ý giao diện:** tên hiển thị lấy từ claims là dữ liệu chưa được tin cậy để xây HTML thủ công. Template engine/JSON serializer cần escape phù hợp để tránh XSS khi đưa chuỗi tùy biến ra browser.

## 19. Kiểm thử principal name bằng Spring Security Test

Các bài kiểm thử trong ứng dụng Servlet có thể dùng `spring-security-test` để giả lập principal OIDC và xác minh controller sử dụng đúng thuộc tính, không cần đăng nhập thật qua IdP trong mỗi unit test.

### 19.1. Controller minh họa để test

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/identity")
    Map<String, String> identity(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "principalName", user.getName(),
            "subject", user.getSubject()
        );
    }
}
~~~

### 19.2. MockMvc với oidcLogin()

~~~java
package com.example.portal.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class IdentityControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void principalNameDefaultsToSubject() throws Exception {
        mockMvc.perform(get("/identity")
                .with(oidcLogin().idToken(token -> token
                    .claim("sub", "employee-42")
                    .claim("preferred_username", "minh.nguyen"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("employee-42"))
            .andExpect(jsonPath("$.principalName").value("employee-42"));
    }
}
~~~

Ví dụ MockMvc tạo một principal giả lập để kiểm tra controller. Khi chạy `@SpringBootTest`, profile `test` vẫn cần cung cấp hoặc mock những bean/configuration mà Spring Security OAuth2 Client cần khi khởi tạo context, chẳng hạn `ClientRegistrationRepository` và provider metadata phù hợp. `oidcLogin()` **không tự kiểm tra metadata discovery, chữ ký ID Token hoặc toàn bộ callback flow**.

### 19.3. Test lựa chọn nameAttributeKey tùy chỉnh

Có thể unit-test cách Spring Security biểu diễn principal bằng `DefaultOidcUser` trực tiếp với một ID Token giả lập có các claims:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;

Instant now = Instant.now();
OidcIdToken idToken = new OidcIdToken(
    "test-id-token-value",
    now,
    now.plusSeconds(300),
    Map.of(
        "iss", "https://login.example.test",
        "sub", "employee-42",
        "aud", "employee-portal",
        "preferred_username", "minh.nguyen"
    )
);

DefaultOidcUser defaultPrincipal = new DefaultOidcUser(
    Set.of(new SimpleGrantedAuthority("OIDC_USER")),
    idToken
);

DefaultOidcUser friendlyPrincipal = new DefaultOidcUser(
    Set.of(new SimpleGrantedAuthority("OIDC_USER")),
    idToken,
    "preferred_username"
);

System.out.println(defaultPrincipal.getName());  // employee-42
System.out.println(friendlyPrincipal.getName()); // minh.nguyen
System.out.println(friendlyPrincipal.getSubject()); // employee-42
~~~

Ở đây token giả dùng cho **unit test của model principal**, không đại diện cho một ID Token đã được xác minh từ OP. Nhận xét quan trọng: **thay nameAttributeKey chỉ thay getName(), không thay subject trong ID Token**.

Không xây luồng production bằng cách nhận JWT thô từ request rồi tự tạo `DefaultOidcUser`. Trong production, ID Token cần được Spring Security xác minh thông qua OAuth2/OIDC login infrastructure.

## 20. Troubleshooting: getName không như mong đợi

| Triệu chứng | Khả năng nguyên nhân | Cách tiếp cận |
|---|---|---|
| `Authentication.getName()` là chuỗi dài khó đọc | Mặc định dùng `sub` | Giữ làm định danh kỹ thuật; lấy `name` hoặc `preferred_username` cho UI |
| Đặt `user-name-attribute: email` nhưng login lỗi | Claim email không có trong dữ liệu mà user service sử dụng | Xác nhận provider cấp claim, scope và UserInfo/ID Token theo chính sách |
| `preferred_username` có lúc null | Provider không luôn phát claim này | Dùng fallback cho display name, không coi là khóa bắt buộc |
| User đổi email thì hệ thống tạo tài khoản mới | Ứng dụng đang dùng email làm external identity key | Ánh xạ bằng `iss + sub`, migration có kiểm soát |
| Hai người từ hai OP bị coi là cùng tài khoản | Chỉ dùng `sub` hoặc email làm khóa toàn hệ thống | Kết hợp issuer+subject và kiểm tra account linking |
| Login thành công nhưng authorized client cũ không được tìm thấy | Principal name đã đổi, key storage thay đổi | Kiểm tra cấu hình name attribute và khóa repository/service |
| `UserInfo.getSubject()` khác ID Token sub | Response UserInfo không thuộc đúng người dùng/giao dịch | Không sử dụng response sai; kiểm tra provider, token và validation |
| `OidcUser.getUserInfo()` là null | UserInfo không được gọi/không có dữ liệu phù hợp | Chỉ dùng claims có sẵn, không giả định UserInfo luôn tồn tại |
| API trả 403 dù username đúng | Quyền/authority không đủ | Kiểm tra authorization, scope, roles; name không cấp quyền |
| `getName()` đổi sau khi chỉnh property | `user-name-attribute` thay khóa name | Xác định ảnh hưởng tới session, audit và authorized client storage |
| OAuth2 provider trả `id` thay vì `sub` | Provider không phải OIDC | Dùng provider-specific user-name-attribute và mapping riêng |

Khi điều tra, chỉ ghi **cấu trúc hoặc tên những claim hiện có** và các mã lỗi cần thiết. Không in toàn bộ ID Token, access token, refresh token, cookie hoặc dữ liệu hồ sơ nhạy cảm vào log.

## 21. Những sai lầm thiết kế phổ biến

**Sai lầm 1 — Dùng `email` làm primary key của user.** Email có thể đổi hoặc được tái cấp; cần internal ID và external identity mapping ổn định.

**Sai lầm 2 — Cho rằng `user-name-attribute` xác minh danh tính.** Property chỉ chọn claim nào làm tên principal; việc xác thực thuộc OAuth2/OIDC login và validation của framework/provider.

**Sai lầm 3 — Tên hiển thị cũng là username kỹ thuật.** `name` có thể trùng, rỗng hoặc chứa ngôn ngữ/ký tự đặc biệt; không thích hợp làm khóa hệ thống.

**Sai lầm 4 — `sub` là duy nhất trên Internet.** Subject phải được hiểu trong namespace issuer; nhiều OP có thể dùng cùng chuỗi sub.

**Sai lầm 5 — UserInfo luôn tồn tại và luôn có email.** Việc phát claims phụ thuộc provider, scope, consent, endpoint và cấu hình client.

**Sai lầm 6 — Có email_verified nghĩa là có quyền truy cập.** Email verification chỉ liên quan trạng thái kiểm chứng email; authorization cần kiểm tra roles/permissions riêng.

**Sai lầm 7 — Đổi principal name để sửa UI.** Nếu UI cần tên đẹp, dùng display name riêng. Thay name attribute có thể ảnh hưởng authorized client storage.

**Sai lầm 8 — Ghép account đa IdP bằng email trùng.** Cần quy trình liên kết danh tính có kiểm soát, không suy luận tự động từ thuộc tính hồ sơ.

**Sai lầm 9 — Xây OidcUser từ JSON tự khai.** Không tin chuỗi `iss/sub` do browser tự gửi; principal phải được hình thành sau xác thực OIDC hợp lệ.

## 22. Tình huống thực hành

### 22.1. Tình huống A: nhân viên đổi họ và email

Trước thay đổi:

~~~text
iss = https://login.example.test/realms/company
sub = emp-0042
preferred_username = minh.nguyen
email = minh.nguyen@example.test
~~~

Sau thay đổi:

~~~text
iss = https://login.example.test/realms/company
sub = emp-0042
preferred_username = minh.tran
email = minh.tran@example.test
~~~

**Câu hỏi:** nên tạo một internal user mới hay giữ nguyên?

**Hướng giải:** giữ nguyên internal user nếu cặp **issuer+subject** vẫn giống nhau và không có lý do khác để vô hiệu liên kết. Cập nhật thuộc tính hồ sơ theo chính sách. Không sử dụng thay đổi email để tự tạo user mới.

### 22.2. Tình huống B: hai OP cùng có sub=42

~~~text
company: iss=https://login.company.example.test, sub=42
partner: iss=https://login.partner.example.test, sub=42
~~~

**Câu hỏi:** có thể lưu một bảng chỉ chứa sub làm unique key không?

**Hướng giải:** không nên. Cần namespace theo issuer và áp dụng unique constraint cho **issuer + subject**. Việc hai external identities trỏ đến cùng internal user, nếu cần, phải thực hiện bằng account linking đã được xác minh.

### 22.3. Tình huống C: người dùng yêu cầu tên dễ đọc trên header

Ứng dụng hiện hiển thị:

~~~text
Xin chào a1c9f22b-8b27-41d7-84e1-0cd741df7a60
~~~

**Câu hỏi:** có cần đặt `user-name-attribute: name` không?

**Hướng giải:** không bắt buộc. Giữ `getName()` là định danh ổn định và hiển thị `getFullName()` hoặc `getPreferredUsername()` với fallback. Như vậy không gây tác động không cần thiết đến kho authorized client và audit.

### 22.4. Tình huống D: OAuth2 provider không trả ID Token

Provider trả:

~~~json
{"id": 7744, "login": "partner-user", "name": "Partner User"}
~~~

**Câu hỏi:** nên đặt user-name-attribute thành gì?

**Hướng giải:** nếu `id` là định danh user được provider cam kết theo tài liệu của mình, có thể đặt `provider.partner.user-name-attribute: id` cho `OAuth2User`. Không gọi trường `id` đó là OIDC `sub` nếu provider không hỗ trợ OIDC.

### 22.5. Tình huống E: đổi principal name trong phiên đang chạy

Đội phát triển thay cấu hình từ:

~~~yaml
user-name-attribute: sub
~~~

thành:

~~~yaml
user-name-attribute: preferred_username
~~~

**Câu hỏi:** cần đánh giá điều gì khi triển khai?

**Hướng giải:** ngoài việc kiểm tra claim hiện diện, phải xem các thành phần dùng `Authentication.getName()`, session hiện có, khóa lưu authorized client, audit log, bảng liên kết user và quy trình chuyển đổi. Không coi đây chỉ là thay đổi UI.

## 23. Checklist thiết kế user identity và profile

| Câu hỏi | Hướng khuyến nghị |
|---|---|
| Ứng dụng đăng nhập OIDC hay OAuth2 thuần? | Phân biệt theo protocol và principal type; không đồng nhất schema |
| Principal name mặc định là gì? | Với OIDC thường là `sub`; xác nhận config của từng provider |
| `user-name-attribute` có thật sự cần thay? | Chỉ thay khi có yêu cầu chức năng rõ ràng |
| Khóa liên kết OIDC ngoài hệ thống là gì? | **Issuer + subject** của principal đã xác minh |
| User nội bộ có ID riêng không? | Nên có internal primary key độc lập IdP |
| Name/email/username dùng cho việc gì? | Hiển thị, liên hệ, tìm kiếm theo chính sách; không mặc định là khóa |
| Claims có thể vắng mặt hoặc thay đổi không? | Có; thiết kế fallback và quy trình cập nhật hồ sơ |
| Email đã verified chưa? | Kiểm tra `email_verified` khi nghiệp vụ yêu cầu |
| Đa IdP có thể trùng sub/email không? | Có; dùng issuer namespace và account linking có kiểm chứng |
| Đổi name attribute có tác động storage không? | Kiểm tra principalName trong authorized client storage/audit |
| Role được lấy từ đâu? | Từ authority/authorization mapping đã được kiểm soát, không phải name |
| Có trả toàn bộ token/claims cho UI không? | Không; chỉ trả thông tin ứng dụng cần và được phép công bố |

## 24. Kết luận

Trong Spring Security OAuth 2.0/OIDC Client, **`user-name-attribute`** xác định **tên thuộc tính dùng làm principal name**, ảnh hưởng đến kết quả của `getName()`. Với **OIDC**, mặc định thường chọn **`sub`**; với **OAuth2 provider không dùng OIDC**, có thể phải khai báo key như `id` hoặc `login` dựa trên UserInfo schema của provider.

**Principal name không đồng nghĩa khóa danh tính người dùng trong cơ sở dữ liệu.** Với OIDC, dùng **`(iss, sub)`** từ ID Token đã được xác minh để xác định external identity, sau đó ánh xạ sang **internal user ID** của ứng dụng. Các claim **`name`**, **`preferred_username`** và **`email`** phục vụ hồ sơ/hiển thị và có thể thay đổi; không nên dùng chúng làm khóa chính hoặc cơ sở phân quyền.

Khi nhu cầu chỉ là tên hiển thị dễ đọc, hãy giữ principal name ổn định và xây một lớp display-name riêng. Chỉ tùy biến `user-name-attribute` hoặc `OidcUserService` khi thực sự cần, đồng thời đánh giá tác động đến **authorized client storage, session, audit và account linking**. Cách tách biệt **danh tính đã xác thực**, **khóa người dùng nội bộ** và **thuộc tính hồ sơ** giúp Portal hoạt động nhất quán với UserInfo, đa provider và thay đổi thông tin người dùng theo thời gian.
