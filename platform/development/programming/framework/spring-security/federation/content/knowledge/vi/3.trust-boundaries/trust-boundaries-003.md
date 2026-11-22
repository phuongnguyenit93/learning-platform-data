# Phân biệt danh tính do đối tác khẳng định với quyền do ứng dụng quyết định

> Module: **Spring Security – federation** · Chủ đề cha: **Ranh giới tin cậy**. Bài học tập trung vào ranh giới giữa **bằng chứng danh tính nhận từ đối tác** và **quyết định cho phép truy cập của ứng dụng**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **đối tác xác thực thành công một người dùng** không có nghĩa người đó được quyền dùng mọi chức năng của ứng dụng.
2. Phân biệt **identity claim**, **principal**, **external group/role**, **local account**, **permission** và **authorization decision**.
3. Xác định điểm nào trong luồng OIDC/SAML là **xác minh bằng chứng từ đối tác**, điểm nào là **ánh xạ danh tính** và điểm nào là **thực thi chính sách quyền nội bộ**.
4. Thiết kế ánh xạ danh tính theo issuer và subject ổn định, tách khỏi email/tên hiển thị; từ chối mặc định khi không tồn tại liên kết hoặc quyền phù hợp.
5. Hiện thực một ví dụ Spring Security (Servlet, OIDC Login) mà IdP xác nhận người dùng, còn ứng dụng tự cấp quyền nghiệp vụ.
6. Nhận diện rủi ro leo thang quyền do tin nhầm claim, nhầm tenant, ghép tài khoản bằng email, cache quyền hoặc thiếu kiểm tra quyền trên từng tài nguyên.

## 1. Tình huống: đối tác xác thực, ứng dụng quyết định quyền

Công ty A vận hành **Partner Orders Portal** cho nhiều nhà cung cấp. Nhân viên của Nhà cung cấp B đăng nhập bằng tài khoản tại **Identity Provider (IdP)** của B. IdP phát hành thông tin danh tính qua OIDC, ví dụ:

~~~json
{
  "iss": "https://idp.partner-b.example/realms/business",
  "sub": "user-5f2c",
  "email": "buyer@partner-b.example",
  "email_verified": true,
  "groups": ["partner-admin"]
}
~~~

Các claim trên là **dữ liệu ví dụ** trong một ID Token/UserInfo đã được xử lý theo giao thức; không phải JSON tự do do trình duyệt gửi là có thể tin. Giả sử RP đã xác minh hợp lệ token và nguồn phát hành, ứng dụng có thể kết luận: **IdP được tin cậy này khẳng định chủ thể `user-5f2c` là người vừa xác thực**.

Ứng dụng **chưa thể** từ đó kết luận:

- Chủ thể đó thuộc đúng **tài khoản nhà cung cấp B** trong cơ sở dữ liệu nội bộ.
- Chủ thể có thể xem **đơn hàng của nhà cung cấp C**.
- Chuỗi `partner-admin` có nghĩa là quyền `APP_ADMIN` của ứng dụng.
- Người dùng có thể **duyệt thanh toán**, **thay đổi giá**, **xem dữ liệu riêng tư**.
- Quyền vẫn hợp lệ tại thời điểm hiện tại khi tài khoản nội bộ đã bị khóa.

**Quy tắc cốt lõi: IdP có thẩm quyền khẳng định danh tính trong phạm vi quan hệ tin cậy; ứng dụng có thẩm quyền quyết định quyền truy cập tài nguyên mà mình sở hữu.** Đối tác có thể cung cấp tín hiệu phục vụ phân quyền nếu đã có thỏa thuận rõ ràng, nhưng ứng dụng phải diễn giải và kiểm soát tín hiệu đó theo chính sách của mình.

## 2. Đường đi từ identity assertion đến authorization decision

~~~text
[Trình duyệt / User]
         |
         | Chuyển hướng đăng nhập theo OIDC hoặc SAML
         v
[IdP của đối tác]
         |
         | ID Token / SAML assertion: "Tôi đã xác thực subject này"
         v
+-----------------------------------------------------------+
| RANH GIỚI TIN CẬY CỦA ỨNG DỤNG (RP / SP)                    |
|                                                           |
| [1] Kiểm tra chữ ký, issuer, audience, thời hạn, flow      |
|                   |                                       |
| [2] Nhận external identity = issuer + subject             |
|                   |                                       |
| [3] Liên kết tới local account / tenant; kiểm tra active  |
|                   |                                       |
| [4] Nạp entitlement/quyền đã được ứng dụng phê duyệt      |
|                   |                                       |
| [5] Kiểm tra action + resource + tenant + context         |
|                   |                                       |
|           ALLOW hoặc DENY                                 |
+-----------------------------------------------------------+
~~~

Tách **năm bước** này để biết nên đặt kiểm tra ở đâu:

1. **Xác minh giao thức:** Chỉ chấp nhận bằng chứng hợp lệ từ IdP được phép. Một claim chưa được xác minh chỉ là dữ liệu không đáng tin cậy.
2. **Nhận dạng external identity:** Trích ra định danh ổn định trong ngữ cảnh IdP, thường là cặp `iss` và `sub` đối với OIDC.
3. **Liên kết danh tính sang tài khoản nội bộ:** Tìm user/partner/tenant mà ứng dụng đã đăng ký; có thể từ chối dù IdP xác thực thành công.
4. **Xác lập quyền nội bộ:** Nạp trạng thái tài khoản, vai trò và quyền từ nguồn do ứng dụng quản lý hoặc một hợp đồng ủy quyền quyền được phê duyệt.
5. **Quyết định trên từng request/tài nguyên:** Kiểm tra người dùng có quyền thực hiện hành động này trên **đúng đối tượng** này, tại thời điểm này hay không.

Mốc quan trọng: **authentication** diễn ra để xác nhận ai đang truy cập, còn **authorization** quyết định người đó được làm gì. Federation giúp RP/SP dựa vào IdP để xác thực, nhưng không thay thế các luật nghiệp vụ của RP/SP.

## 3. Các loại dữ liệu: cái gì được khẳng định, cái gì được cấp quyền?

| Dữ liệu / khái niệm | Bên tạo hoặc kiểm soát chính | Có thể kết luận điều gì? | Không thể tự suy ra điều gì? |
| --- | --- | --- | --- |
| OIDC `iss` + `sub` | IdP, sau khi RP xác minh ID Token | Định danh của một subject tại issuer cụ thể | Quyền xem, sửa, xóa dữ liệu |
| Email, tên, avatar | IdP / hệ thống hồ sơ | Thuộc tính của subject, tùy nguồn/độ tin cậy | Khóa liên kết bất biến, quyền admin |
| `email_verified` | IdP theo chính sách xác minh email | IdP khẳng định địa chỉ đã được xác minh theo cơ chế của mình | Tài khoản nội bộ được phép dùng mọi chức năng |
| `groups`, `roles` bên ngoài | IdP/đối tác hoặc directory của họ | Thành viên nhóm/vai trò **theo ngữ nghĩa của đối tác** | Tương đương `ROLE_ADMIN` nội bộ |
| `acr` / `amr` / thời điểm xác thực | IdP | Ngữ cảnh/cách thức xác thực được báo cáo, nếu RP xử lý đúng | Quyền nghiệp vụ; mức quyền cao hơn mặc định |
| OAuth2 `scope` của access token | Authorization Server theo ngữ cảnh token | Phạm vi ủy quyền của client/token dành cho resource server | Quyền mọi hành động của người dùng trong RP |
| Local account, local partner ID | Ứng dụng quản lý | Tài khoản/đơn vị nghiệp vụ đã gắn với external identity | Mọi tài nguyên đều có thể truy cập |
| `APP_ORDER_READ`, `APP_APPROVE_PAYMENT` | Chính sách của ứng dụng | Quyền ứng dụng công nhận nếu tài khoản và điều kiện hợp lệ | Bỏ qua kiểm tra tenant và ownership |
| Quyết định `ALLOW` / `DENY` | Authorization layer của ứng dụng | Có/không cho phép một hành động trên tài nguyên cụ thể | Một quyền vĩnh viễn cho toàn bộ hệ thống |

**Claim đã ký và hợp lệ** chứng minh rằng *issuer đã đưa ra khẳng định ấy*; chữ ký không khiến **mọi nội dung claim có thẩm quyền như chính sách ứng dụng**. Ví dụ một đối tác có thể đặt tên nhóm nội bộ là `admin` nhưng ứng dụng không vì thế mà cấp `APP_SUPER_ADMIN`.

### Nên đặt tên permission theo ứng dụng

Thay vì dùng trực tiếp external group `partner-admin` làm `ROLE_ADMIN`, hãy định nghĩa quyền nội bộ có nghĩa hẹp: `APP_ORDER_READ`, `APP_ORDER_CREATE`, `APP_ORDER_APPROVE`, `APP_PARTNER_USER_MANAGE`. Sau đó ứng dụng mới quyết định người dùng/đơn vị nào được hưởng quyền nào.

Như vậy đối tác thay đổi tên nhóm hoặc tổ chức không vô tình thay đổi ý nghĩa của một quyền nhạy cảm trong ứng dụng.

## 4. Những ranh giới tin cậy trong OIDC và SAML

### 4.1. OIDC: ID Token là bằng chứng về xác thực, không phải giấy phép toàn quyền

Trong **OIDC Authorization Code Flow**, RP chuyển trình duyệt sang IdP, nhận authorization code tại callback, đổi code qua back-channel, rồi xác minh ID Token. Các kiểm tra phụ thuộc profile và loại client, trong đó cần nắm:

- **Issuer `iss`:** Khớp chính xác IdP đã cấu hình; không lấy issuer bất kỳ do người dùng tự chọn mà bỏ qua quy trình đăng ký tin cậy.
- **Audience `aud`:** Token được phát hành cho đúng client/RP; xử lý `azp` khi profile yêu cầu.
- **Chữ ký và khóa:** Xác minh bằng khóa tin cậy của issuer, không chỉ giải mã ba phần của JWT.
- **Thời hạn và tính hợp lệ:** Kiểm tra `exp`, các ràng buộc thời gian, nonce và liên kết state/authorization request khi áp dụng.
- **Đường dẫn trả về:** Kiểm soát redirect URI chính xác, dùng HTTPS ngoài phát triển local và cơ chế bảo vệ luồng OAuth2/OIDC.
- **Nguồn claim:** UserInfo/claims bổ sung phải được liên kết đúng với subject đã xác thực; không tin header hoặc JSON do client tự gửi thay cho token đã xác minh.

Sau đó mới đọc `sub`, tra tài khoản và đánh giá chính sách quyền. **ID Token dành cho RP để xác thực người dùng; access token dùng cho resource server/API**. Không dùng ID Token làm bearer API token, cũng không xem mọi `scope` là vai trò nghiệp vụ.

### 4.2. SAML 2.0: Assertion được xác minh, quyền vẫn do SP quyết định

Với SAML, Service Provider kiểm tra issuer tin cậy, chữ ký, audience, recipient/destination, thời hạn assertion, correlation với AuthnRequest (`InResponseTo` khi áp dụng), điều kiện subject confirmation và cách nhận tại ACS. Khi hợp lệ, SP biết IdP khẳng định một NameID/subject cùng các attributes. **Một SAML attribute tên `Role=Manager` cũng không tự động trở thành `APP_APPROVE_PAYMENT`** nếu SP chưa có chính sách mapping tương ứng.

OIDC và SAML khác định dạng và quy tắc xác minh, nhưng cùng ranh giới: **assertion nhận từ đối tác ≠ quyền nội bộ**.

### 4.3. External group có bao giờ được dùng để phân quyền không?

**Có thể**, nếu ứng dụng và đối tác có **hợp đồng quyền được ủy thác** rõ ràng: issuer/tenant cụ thể, namespace của claim, danh sách group được phép, cách quản lý thành viên, quy trình review, giới hạn quyền tối đa, audit, đồng bộ thay đổi và cơ chế thu hồi. Ứng dụng vẫn phải chuyển đổi qua bảng mapping do mình kiểm soát, ví dụ:

| Issuer tin cậy | External group được thỏa thuận | Local permission tối đa | Điều kiện bổ sung |
| --- | --- | --- | --- |
| `partner-b` | `buyers-read-only` | `APP_ORDER_READ` | Account active, thuộc Partner B |
| `partner-b` | `buyers-create` | `APP_ORDER_CREATE` | Account active, thuộc Partner B |
| `partner-b` | `partner-admin` | Không mặc định cấp quyền nội bộ | Phê duyệt và mapping riêng nếu thật sự cần |
| Issuer khác | Bất kỳ | Không tự cấp | Chưa có trust contract |

Nhóm bên ngoài chỉ là **một input** của quyết định có kiểm soát. Mọi ngoại lệ phải được giải thích bằng chính sách có thể kiểm toán.

## 5. Liên kết danh tính với tài khoản nội bộ an toàn

### 5.1. Khóa liên kết

Một thiết kế thường dùng với OIDC:

~~~text
external_identity
--------------------------------------------------------------
issuer                                    subject      local_id
https://idp.partner-b.example/realms/biz   user-5f2c    user_104
https://idp.partner-c.example/realms/biz   user-5f2c    user_999
~~~

Dù hai issuer dùng cùng `sub`, đây có thể là **hai người hoàn toàn khác nhau**. Vì vậy không tra cứu bằng mỗi subject. Ngược lại, không dùng email làm khóa duy nhất vì email có thể đổi, được tái sử dụng hoặc bị cấu hình sai. OIDC có thể phát hành **pairwise subject**, trong đó một người có `sub` khác nhau giữa các RP; không dùng `sub` để tự suy đoán người giống nhau xuyên nhiều ứng dụng.

Mô hình minh họa:

~~~text
external_identity(issuer, subject, local_user_id)
local_user(id, status, partner_id)
local_permission(local_user_id, permission)
partner_order(id, owner_partner_id, status)
~~~

Đặt unique constraint trên cặp `(issuer, subject)`, kiểm tra account còn hoạt động, nạp partner ID nội bộ từ liên kết đã duyệt. Với đa tenant, cần biểu diễn tenant/trust policy nhất quán ở lớp dữ liệu và ở mọi truy vấn; không suy ra tenant từ parameter do trình duyệt cung cấp.

### 5.2. Cấp tài khoản lần đầu (provisioning/JIT)

Nếu ứng dụng hỗ trợ Just-in-Time provisioning, **việc tạo local account không đồng nghĩa tự cấp quyền**. Đường an toàn có thể là:

1. Xác minh assertion OIDC/SAML.
2. Nếu chưa có cặp issuer/subject trong bảng liên kết, tạo tài khoản trạng thái `PENDING` hoặc từ chối và yêu cầu quy trình phê duyệt.
3. Chỉ gán `partner_id` khi đã có chứng cứ/hợp đồng đáng tin cậy; không tin query string `?partnerId=...`.
4. Sau khi nhân sự/luồng quản trị phê duyệt, cấp những permission tối thiểu.
5. Mọi lần dùng quyền đều kiểm tra trạng thái account và phạm vi tài nguyên.

Nhờ vậy **xác thực thành công với IdP mới** không biến thành cơ chế cho người bất kỳ ở đối tác tự tham gia ứng dụng với quyền cao.

### 5.3. Thu hồi và thay đổi quyền

Nhân viên rời đối tác, đổi bộ phận hoặc bị khóa tài khoản: IdP có thể thay đổi group, nhưng ứng dụng cần bảo đảm **quyền nội bộ bị thu hồi kịp thời**. Có thể dùng đồng bộ provisioning (như SCIM nếu phù hợp), sự kiện thu hồi, kiểm tra trạng thái ở database theo request, TTL ngắn và chiến lược kết thúc phiên. Nếu chỉ gán GrantedAuthority **một lần khi đăng nhập**, phiên dài có thể giữ quyền cũ; đối với hành động nhạy cảm, phải kiểm tra quyền cập nhật tại thời điểm thực thi hoặc có cơ chế invalidation đáng tin cậy.

## 6. Công thức kiểm tra quyền nghiệp vụ

Cho hành động “xem đơn hàng”, quyết định quyền nên dựa trên tất cả điều kiện cần thiết:

~~~text
ALLOW_VIEW_ORDER(user, order)
    = authenticated_and_verified(user)
      AND linked_local_account_exists(user.issuer, user.subject)
      AND local_account.status == ACTIVE
      AND local_account.permissions contains APP_ORDER_READ
      AND local_account.partner_id == order.owner_partner_id
      AND any_resource_specific_policy_is_satisfied
~~~

Điều kiện **được xác thực** và **có permission** là cần nhưng chưa đủ khi dữ liệu thuộc nhiều đối tác. Một người của Partner B có thể có `APP_ORDER_READ`, nhưng chỉ để xem đơn hàng của Partner B. Khi query dữ liệu, ràng buộc ở service/repository, ví dụ `WHERE order_id = :id AND owner_partner_id = :partnerIdFromLocalAccount`. Không nhận partner ID từ request rồi dùng để quyết định phạm vi, và không chỉ ẩn nút trên giao diện.

### Ma trận kết quả

| Identity từ IdP | Liên kết local | Local permission | Đơn hàng thuộc | Quyết định |
| --- | --- | --- | --- | --- |
| Hợp lệ | Account active, Partner B | `APP_ORDER_READ` | Partner B | **ALLOW** |
| Hợp lệ | Account active, Partner B | `APP_ORDER_READ` | Partner C | **DENY** |
| Hợp lệ | Account active, Partner B | Không có `APP_ORDER_READ` | Partner B | **DENY** |
| Hợp lệ, claim `groups=["admin"]` | Account active, Partner B | Không có `APP_ORDER_READ` | Partner B | **DENY** |
| Hợp lệ | Chưa liên kết / local disabled | Bất kỳ claim ngoài | Bất kỳ | **DENY** |
| Issuer/signature/audience không hợp lệ | Không tin cậy | Bất kỳ | Bất kỳ | **REJECT AUTHENTICATION** |

Về HTTP, “chưa có phiên xác thực” thường dẫn tới chuyển hướng đăng nhập ở ứng dụng web OIDC; “đã đăng nhập nhưng thiếu quyền” thường là **403 Forbidden**. Cách phản hồi thực tế phụ thuộc entry point và yêu cầu của client/API.

## 7. Ví dụ Java 17 + Spring Security: xác thực bằng OIDC, quyền lấy từ ứng dụng

Ví dụ dưới đây là **Servlet web application** dùng Spring Boot 3.3.x / Spring Security 6.x, chạy Java 17 trở lên. Ứng dụng đóng vai **OIDC Relying Party**. IdP xác thực người dùng; ứng dụng chủ động map identity thành `GrantedAuthority` mang namespace `APP_`. Mục tiêu là minh họa ranh giới quyền, không tạo IdP riêng.

**Để chạy tích hợp thật**, cần IdP có OIDC discovery, client ID, client secret, redirect URI hợp lệ, và biết subject của tài khoản được phép trong môi trường thử nghiệm.

### 7.1. Cấu trúc dự án

~~~text
federated-access-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/federatedaccess/
    │   ├── FederatedAccessApplication.java
    │   ├── LocalAccessService.java
    │   ├── SecurityConfig.java
    │   └── PartnerController.java
    └── resources/application.yml
~~~

`settings.gradle`

~~~groovy
rootProject.name = 'federated-access-demo'
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

### 7.2. Main

`src/main/java/com/example/federatedaccess/FederatedAccessApplication.java`

~~~java
package com.example.federatedaccess;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederatedAccessApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederatedAccessApplication.class, args);
    }
}
~~~

### 7.3. LocalAccessService: nguồn quyền do ứng dụng kiểm soát

`src/main/java/com/example/federatedaccess/LocalAccessService.java`

~~~java
package com.example.federatedaccess;

import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class LocalAccessService {

    private final String trustedIssuer;
    private final String approvedSubject;

    public LocalAccessService(
            @Value("${spring.security.oauth2.client.provider.partner-idp.issuer-uri}")
            String trustedIssuer,
            @Value("${demo.approved-subject}") String approvedSubject) {
        this.trustedIssuer = trustedIssuer;
        this.approvedSubject = approvedSubject;
    }

    public Set<String> permissionsFor(String issuer, String subject) {
        // Mô phỏng một liên kết (issuer, subject) đã được nội bộ duyệt.
        if (trustedIssuer.equals(issuer) && approvedSubject.equals(subject)) {
            return Set.of("APP_ORDER_READ");
        }
        return Set.of(); // Không có liên kết hợp lệ => không có permission.
    }
}
~~~

Đây là **allow-list mô phỏng dữ liệu nội bộ** để bài học tự chứa, *không phải cơ chế lưu quyền dùng cho production*. Trong hệ thống thật, `LocalAccessService` sẽ tra local database theo cặp issuer/subject, kiểm tra `ACTIVE`, tenant, partner ID, entitlement và quy trình phê duyệt. Đối tác không được tự gửi giá trị `APP_ORDER_READ` để được cấp quyền.

### 7.4. SecurityConfig: gán authorities từ nguồn nội bộ

`src/main/java/com/example/federatedaccess/SecurityConfig.java`

~~~java
package com.example.federatedaccess;

import java.util.HashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> localOidcUserService)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/partner/orders")
                    .hasAuthority("APP_ORDER_READ")
                .anyRequest().denyAll()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(localOidcUserService)
                )
            )
            .build();
    }

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> localOidcUserService(
            LocalAccessService accessService) {

        OidcUserService delegate = new OidcUserService();

        return userRequest -> {
            // Spring Security thực hiện xử lý/xác minh OIDC trước bước này.
            OidcUser federatedUser = delegate.loadUser(userRequest);
            String issuer = federatedUser.getIdToken().getIssuer().toString();
            String subject = federatedUser.getSubject();

            // Chỉ tạo authorities của CHÍNH ứng dụng từ nguồn nội bộ.
            Set<GrantedAuthority> localAuthorities = new HashSet<>();
            localAuthorities.add(new SimpleGrantedAuthority("APP_AUTHENTICATED"));
            for (String permission : accessService.permissionsFor(issuer, subject)) {
                localAuthorities.add(new SimpleGrantedAuthority(permission));
            }

            // Không chuyển thẳng groups/roles hoặc SCOPE_ bên ngoài
            // thành quyền nghiệp vụ của ứng dụng.
            return new DefaultOidcUser(
                localAuthorities,
                federatedUser.getIdToken(),
                federatedUser.getUserInfo()
            );
        };
    }
}
~~~

Giải thích kỹ từng bước:

1. `OidcUserService` mặc định nhận kết quả OIDC và xây principal sau khi các thành phần Spring Security xử lý luồng đăng nhập. Không nên tự parse JWT/khai báo header `X-User` làm bằng chứng xác thực thay nó.
2. `federatedUser.getIdToken().getIssuer()` và `getSubject()` là **định danh ngoài đã xác minh trong luồng**; ta dùng chúng làm khóa tra cứu cục bộ.
3. `LocalAccessService.permissionsFor(...)` là nơi **ứng dụng quyết định entitlement**, không lấy `groups` trong token làm quyền ứng dụng.
4. `APP_AUTHENTICATED` chỉ là authority nền để biểu diễn đã có principal hợp lệ; **không được dùng nó để bảo vệ dữ liệu nghiệp vụ**. Kể cả khi không có permission, danh sách authorities vẫn không rỗng.
5. `DefaultOidcUser` được tạo lại với authorities ứng dụng. Người dùng không được cấp `APP_ORDER_READ` sẽ **không** qua được quy tắc `hasAuthority("APP_ORDER_READ")`.
6. `anyRequest().denyAll()` ngăn các endpoint chưa được khai báo công khai ngoài ý muốn. Các filter dành cho OIDC login/callback xử lý tuyến đăng nhập.
7. Đây là **mapping lúc đăng nhập**; trong production, phải giải quyết bài toán quyền bị thu hồi trong khi phiên đang sống.

**Lưu ý về `APP_AUTHENTICATED`:** đây là tên giả lập, không có ngữ nghĩa đặc biệt mặc định trong Spring Security. Việc đã đăng nhập được biểu diễn qua `Authentication`; authority nền chỉ nhằm không tạo tập authorities rỗng. Quyền nghiệp vụ chỉ là các authority có ý nghĩa cụ thể như `APP_ORDER_READ`.

### 7.5. Controller: quan sát danh tính và chặn chức năng theo quyền

`src/main/java/com/example/federatedaccess/PartnerController.java`

~~~java
package com.example.federatedaccess;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PartnerController {

    @GetMapping("/")
    public String home() {
        return "Open /me, then try /partner/orders";
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {

        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject(),
            "localAuthorities", authorities
        );
    }

    @GetMapping("/partner/orders")
    public List<String> orders() {
        // Dữ liệu giả lập, KHÔNG chứa đơn hàng thật.
        return List.of("demo-order-001", "demo-order-002");
    }
}
~~~

- `/me` chỉ dành cho debug/học tập và cho phép mọi người **đã xác thực** quan sát mình đang có authorities nào. Khi triển khai thật, hãy bỏ endpoint debug hoặc giới hạn dữ liệu.
- `/partner/orders` chỉ trả dữ liệu mẫu khi SecurityFilterChain thấy `APP_ORDER_READ`. Người đăng nhập thành công nhưng không được nội bộ duyệt sẽ thấy quyền nền và **bị từ chối** khi gọi đường dẫn đơn hàng.
- Trong nghiệp vụ thật, không trả toàn bộ đơn hàng chỉ vì có `APP_ORDER_READ`: service/repository phải kiểm tra **đơn hàng thuộc partner nào** trước khi trả dữ liệu. Ví dụ controller ở đây chỉ có hai chuỗi giả định để tập trung vào ranh giới danh tính/quyền.

### 7.6. Cấu hình OIDC

`src/main/resources/application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-idp
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          partner-idp:
            issuer-uri: ${PARTNER_OIDC_ISSUER_URI}

demo:
  approved-subject: ${PARTNER_ALLOWED_SUB}
~~~

Cấu hình trên sử dụng **biến môi trường**. Đăng ký với IdP một confidential OIDC web client, redirect URI local:

~~~text
http://localhost:8080/login/oauth2/code/partner
~~~

Điểm khởi phát login mặc định là `/oauth2/authorization/partner`. Sử dụng issuer URL thật, HTTPS và client credentials theo cấu hình IdP; không commit client secret. `PARTNER_ALLOWED_SUB` phải là subject ổn định **của người được nội bộ duyệt**, không phải email hoặc tên hiển thị.

Có thể chạy với Gradle cài sẵn trên máy hoặc dự án đã có Gradle Wrapper phù hợp:

~~~bash
gradle bootRun
~~~

Ứng dụng chỉ chạy/đăng nhập thành công khi các biến môi trường được đặt đúng và IdP có thể truy cập. Đây là **tích hợp phụ thuộc IdP**, nên không có JSON kết quả hoặc subject cố định cho mọi môi trường.

### 7.7. Quan sát để chứng minh ranh giới

1. Cấu hình `PARTNER_ALLOWED_SUB` trùng subject của tài khoản test đã được nội bộ phê duyệt. Đăng nhập tại `/me`: thấy `APP_AUTHENTICATED` và `APP_ORDER_READ`.
2. Mở `/partner/orders`: nhận danh sách đơn hàng *giả lập*.
3. Đăng nhập bằng một subject khác cùng IdP. `/me` vẫn cho thấy **issuer và subject hợp lệ** cùng authority nền `APP_AUTHENTICATED`, nhưng **không có `APP_ORDER_READ`**.
4. Mở lại `/partner/orders`: bị **403 Forbidden** (đã đăng nhập nhưng thiếu quyền).
5. Nếu cấu hình issuer, audience hoặc callback không hợp lệ, luồng OIDC không hoàn tất xác thực; đó là lỗi **authentication/trust validation**, khác với 403 do thiếu local permission.
6. Nếu đối tác gắn `groups=["partner-admin"]` cho người chưa được duyệt, quyền ứng dụng **vẫn không tăng** vì ví dụ không dùng claim đó để gán permission.

Từ thử nghiệm này rút ra được một tiêu chí kiểm chứng cụ thể: **hai người cùng được IdP xác thực có thể nhận quyết định truy cập khác nhau vì local permission khác nhau**.

## 8. Kiểm tra quyền trên tài nguyên, không chỉ trên URL

Filter `hasAuthority("APP_ORDER_READ")` ở ví dụ chỉ trả lời “người dùng có permission đọc đơn hàng nói chung không?”. Khi endpoint là `GET /partner/orders/{orderId}`, quyết định cần thêm **ownership hoặc tenant boundary**:

~~~java
// Minh họa logic ở tầng service; không phải một class độc lập để chạy.
boolean canReadOrder(LocalAccount account, PartnerOrder order) {
    return account.active()
        && account.permissions().contains("APP_ORDER_READ")
        && account.partnerId().equals(order.ownerPartnerId());
}
~~~

Một phương án Spring Security là bật `@EnableMethodSecurity` và dùng `@PreAuthorize` cho điều kiện authority ở service, đồng thời kiểm tra partner/ownership trong cùng service/repository. Không dùng riêng `@PreAuthorize("isAuthenticated()")` cho dữ liệu đa tenant và không nhận `partnerId` từ request làm nguồn quyền. Dù UI ẩn nút “Xem đơn hàng”, API vẫn phải từ chối truy cập trái quyền.

Nếu nghiệp vụ yêu cầu hiệu lực thu hồi tức thì, việc nạp permissions duy nhất ở `OidcUserService` tại login là chưa đủ. Cần thêm kiểm tra quyền live ở tầng service, session invalidation hoặc cơ chế làm mới có giới hạn; cân nhắc độ trễ, tải database và tính nhất quán.

## 9. Các lỗi triển khai phổ biến và cách sửa

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Giải mã JWT rồi tin ngay `role=admin` | Giải mã không xác minh chữ ký/issuer/audience; claim chưa chắc có thẩm quyền cấp quyền nội bộ | Dùng thư viện OIDC/SAML xác minh chuẩn; mapping local quyền có kiểm soát |
| Coi `email` là khóa định danh duy nhất | Email đổi hoặc tái sử dụng; nguy cơ chiếm tài khoản khi ghép nhầm | Dùng định danh theo `(issuer, subject)` và quy trình link account |
| Tra theo `sub` không kèm issuer | Hai IdP có thể phát cùng subject | Gắn issuer và trust contract/tenant vào liên kết |
| Map mọi `groups=admin` thành `ROLE_ADMIN` | “Admin” bên đối tác có thể chỉ là admin của tenant họ | Namespace và allow-list mapping được duyệt; quyền tối thiểu |
| Dùng `SCOPE_openid` / `SCOPE_email` làm quyền nghiệp vụ | Scope trong OAuth/OIDC không tương đương quyền đọc đơn hàng | Quyền ứng dụng như `APP_ORDER_READ`, kiểm tra riêng |
| Mặc định cấp quyền cho user chưa liên kết | Bất kỳ nhân viên đối tác có tài khoản IdP đều có thể truy cập | Từ chối/JIT pending, yêu cầu phê duyệt |
| Chỉ kiểm tra `authenticated()` | Đăng nhập thành công bị hiểu thành “toàn quyền” | Kiểm tra permission và resource ownership |
| Chỉ kiểm tra `partnerId` do client gửi | Đổi request parameter có thể xem dữ liệu tenant khác | Lấy partner ID từ local account, ràng buộc truy vấn dữ liệu |
| Tạo authority tại login rồi giữ mãi | Người bị thu hồi quyền vẫn dùng phiên cũ | Kiểm tra lại trạng thái/quyền hoặc invalidate session |
| Chỉ ẩn chức năng trên frontend | API vẫn có thể bị gọi trực tiếp | Enforce authorization ở backend |
| Gộp quyền từ nhiều IdP mà không tách issuer | Trộn ngữ nghĩa và ranh giới tổ chức | Trust policy riêng cho từng issuer/tenant |
| Tự động “sửa” lỗi issuer hoặc signature bằng cách bỏ validation | Đổi lỗi cấu hình thành lỗ hổng xác thực | Sửa IdP/client/redirect/JWKS, không vô hiệu hóa xác minh |

### Không đánh đồng “đối tác đáng tin cậy” với “mọi claim của đối tác có quyền lực tối đa”

Trust nên được mô tả theo **phạm vi**: ai được phép phát hành chứng thực, loại chứng thực nào, dành cho RP nào, subject nào có thể link, claim nào có thể dùng làm input quyền và trần quyền nào được cho phép. Việc đã tin một IdP để xác thực **không** tự động là hợp đồng cho IdP ấy cấp mọi quyền ở tất cả ứng dụng.

## 10. Bài thực hành kiểm chứng (QA cho học viên)

Với một IdP thử nghiệm và hai tài khoản hợp lệ, chạy demo ở mục 7. Chuẩn bị subject A được local allow-list và subject B chưa được cấp local permission. Ghi nhận kết quả theo bảng sau:

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| T1 – Identity hợp lệ, local permission có | Login bằng A; cấu hình `PARTNER_ALLOWED_SUB=A` | `/me` có `APP_ORDER_READ`, `/partner/orders` thành công |
| T2 – Identity hợp lệ, local permission không có | Login bằng B | `/me` thể hiện subject B, `/partner/orders` 403 |
| T3 – Có external admin claim | IdP cấp group admin cho B (nếu môi trường cho phép) | B vẫn không có `APP_ORDER_READ` |
| T4 – IdP không hợp lệ | Cấu hình issuer/callback sai trong môi trường test | Đăng nhập bị chặn; không có quyền được cấp do bỏ qua kiểm tra |
| T5 – Subject trùng, issuer khác | Mô phỏng hai external identity khác issuer cùng subject | Không trỏ về cùng local account chỉ vì `sub` bằng nhau |
| T6 – Khác tenant/partner | Cùng permission nhưng order thuộc partner khác | Service từ chối theo ownership |
| T7 – Tài khoản bị disable | Local account chuyển `ACTIVE` sang `DISABLED` | Request nhạy cảm bị từ chối sau khi chính sách thu hồi có hiệu lực |
| T8 – Không có link | Subject mới đăng nhập hợp lệ qua IdP | Không được tự cấp quyền đọc/duyệt dữ liệu |

**Tiêu chí hoàn thành:** giải thích được tại sao T2/T3 bị 403 dù IdP đã xác thực người dùng; tại sao T5 là lỗi ranh giới issuer; và tại sao T6 vẫn phải từ chối dù authority cấp ứng dụng đang có giá trị.

## 11. Câu hỏi tự đánh giá

1. **Nếu ID Token ký đúng và có `groups=["admin"]`, bạn có nên dùng ngay `hasRole("ADMIN")`?** Không. Chữ ký chỉ xác nhận nguồn và tính toàn vẹn; ý nghĩa claim và quyền nội bộ phải được ánh xạ theo chính sách.
2. **Tại sao thường ghép `iss` và `sub` để liên kết tài khoản OIDC?** `sub` có phạm vi theo issuer; chỉ email hoặc chỉ subject dễ nhầm người/tenant.
3. **Người dùng chưa có local account nhưng đăng nhập IdP thành công thì sao?** Chỉ biết họ đã được IdP xác thực. Ứng dụng từ chối quyền nghiệp vụ hoặc vào quy trình provisioning/phê duyệt phù hợp.
4. **Đã có `APP_ORDER_READ` thì xem mọi đơn hàng được không?** Không. Cần kiểm tra ownership, tenant, trạng thái và chính sách tài nguyên.
5. **Vì sao thu hồi quyền ở database chưa chắc làm phiên hiện có mất quyền ngay?** Một số ứng dụng chụp authorities khi đăng nhập; phải kiểm tra lại hoặc làm vô hiệu phiên theo chính sách.
6. **Khi nào external group có thể dùng làm input phân quyền?** Khi có trust contract, giới hạn issuer/tenant, mapping được duyệt, cơ chế đồng bộ và kiểm toán; ứng dụng vẫn là bên quyết định.

## Ghi nhớ

> **Đối tác trả lời “người này là ai theo hệ thống của tôi”. Ứng dụng trả lời “người này, sau khi liên kết với tài khoản nội bộ, được phép làm gì với tài nguyên cụ thể của tôi”.**

Giữ tách biệt **verified external identity → local identity link → local entitlement → resource-level authorization** để federation mở rộng đăng nhập mà không chuyển toàn bộ quyền kiểm soát nghiệp vụ cho đối tác.

### Tài liệu chính thức để học sâu

- [Spring Security – OAuth2 Login, cấu hình nâng cao và mapping authorities](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security – OAuth2 Login, luồng đăng nhập và client registration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [OpenID Connect Core 1.0 – ID Token, subject và xác minh](https://openid.net/specs/openid-connect-core-1_0.html)
