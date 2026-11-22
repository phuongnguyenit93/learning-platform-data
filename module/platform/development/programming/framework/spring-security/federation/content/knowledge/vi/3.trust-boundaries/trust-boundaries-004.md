# Giới hạn bên phát hành và ứng dụng được phép nhận thông tin xác thực trong federation

**Module:** Spring Security – federation  
**Ngữ cảnh:** Ranh giới tin cậy (trust boundary)

## 1. Mục tiêu bài học

Trong đăng nhập liên kết (federated identity/SSO), ứng dụng thường nhận một kết quả xác thực do hệ thống khác tạo ra, ví dụ **ID Token** của OpenID Connect (OIDC) hoặc **SAML Assertion**. Để tin kết quả đó một cách an toàn, ứng dụng phải xác định rõ:

1. **Ai được phép phát hành?** Chỉ tin những Identity Provider/OpenID Provider (IdP/OP) đã được tổ chức đăng ký và phê duyệt.
2. **Kết quả được phát cho ai?** Chỉ ứng dụng, client hoặc service đúng đối tượng nhận mới được chấp nhận kết quả đó.
3. **Kết quả được dùng vào việc gì?** ID Token chứng minh sự kiện đăng nhập cho OIDC client; OAuth access token cấp quyền truy cập API; SAML Assertion được gửi cho Service Provider (SP) tương ứng.
4. **Còn hiệu lực và khớp giao dịch không?** Kiểm tra chữ ký, thời gian, các tham số chống replay/mix-up, ràng buộc phiên và chính sách quyền truy cập.

Hai kiểm tra trung tâm là **issuer (bên phát hành)** và **audience/recipient (bên nhận dự kiến)**. Chỉ kiểm tra rằng chữ ký số “hợp lệ” là chưa đủ: một token có thể thực sự được ký bởi một IdP đáng tin nhưng được phát cho **ứng dụng khác**.

## 2. Hình dung ranh giới tin cậy

Ví dụ công ty triển khai:

- **OP/Authorization Server:** https://login.example.org/realms/company
- **Ứng dụng web A:** client_id **staff-portal**, cần OIDC để đăng nhập nhân viên.
- **Ứng dụng web B:** client_id **vendor-portal**, dành cho nhà cung cấp.
- **API báo cáo:** resource identifier/audience **urn:reports-api**.
- **IdP thử nghiệm:** https://test-login.example.org/realms/company, không được dùng cho production.

Ranh giới hợp lệ:

~~~text
[Người dùng]
     |
     | Đăng nhập
     v
[OP production: login.example.org/realms/company]
     | ID Token: iss=OP production, aud=staff-portal
     +----------------------------------------------> [staff-portal]
     |                                                       |
     |  Access Token: iss=OP production, aud=urn:reports-api  | gọi API
     +-------------------------------------------------------v
                                                     [reports-api]
~~~

**staff-portal** không được nhận ID token dành cho **vendor-portal**. **reports-api** không được chấp nhận ID token dành cho **staff-portal** thay cho access token dành cho API. Cả hai không được tin token do **test-login** phát hành chỉ vì tên miền hoặc khóa có vẻ tương tự.

Một nhà phát hành có thể cung cấp nhiều ứng dụng; một ứng dụng cũng có thể hỗ trợ nhiều nhà phát hành. **Mỗi quan hệ tin cậy phải được phê duyệt và kiểm chứng độc lập**, không tự suy ra rằng “cùng hệ thống SSO” là được nhận mọi token.

## 3. Issuer là gì và vì sao phải giới hạn?

Trong OIDC/JWT, claim **iss** biểu diễn định danh của bên phát hành token, thường là một URL HTTPS. Ví dụ:

~~~json
{
  "iss": "https://login.example.org/realms/company",
  "sub": "employee-847",
  "aud": "staff-portal",
  "exp": 1794100000,
  "iat": 1794096400
}
~~~

Đây là **payload minh họa**, không phải token thật và không chứng minh điều gì nếu chưa kiểm tra chữ ký. Giá trị thời gian chỉ phục vụ giải thích.

Ở ứng dụng tin cậy token, phải:

1. Cấu hình issuer **đúng và đầy đủ**, bao gồm cả đường dẫn tenant/realm. So sánh issuer theo định danh mà provider công bố; không dùng quy tắc “có chứa chuỗi”, “cùng hậu tố domain” hay “cùng tổ chức”.
2. Lấy metadata/discovery và khóa công khai JWKS từ **nhà phát hành đã đăng ký** qua kênh đáng tin, không lấy URL máy chủ bất kỳ từ payload/header chưa được xác minh rồi tự động kết nối tới đó.
3. Xác minh chữ ký bằng khóa phù hợp với issuer và thuật toán được chấp thuận; kiểm tra hạn dùng, not-before, các claim bắt buộc.
4. So sánh **iss** trong token với issuer đã cấu hình cho quan hệ tin cậy đang xử lý.
5. Có chính sách quản trị vòng đời issuer: ai duyệt kết nối mới, tenant nào được phép, đổi khóa/metadata thế nào, thu hồi trust ra sao.

Ví dụ **https://login.example.org/realms/company** và **https://login.example.org/realms/partner** có thể ở cùng một máy chủ nhưng là **hai issuer khác nhau**. Nếu hệ thống chỉ cho nhân viên công ty đăng nhập, token từ realm đối tác phải bị từ chối trừ khi một chính sách federation riêng cho phép.

**JWKS không phải danh sách nhà phát hành được phép.** JWKS trả khóa để kiểm tra chữ ký; quyết định tin issuer phải tồn tại trước khi tin khóa. Header như **kid** chỉ hỗ trợ chọn khóa thích hợp, không cho phép client tự chọn issuer hay tự tải khóa từ URL tùy ý như **jku/x5u**.

## 4. Audience/recipient là gì và vì sao quan trọng?

**aud** (audience) mô tả người nhận mà token hướng tới. Bên nhận phải kiểm tra rằng **mình thực sự được liệt kê trong audience**, không chỉ rằng token do một issuer đáng tin phát hành.

Cách hiểu phụ thuộc loại token:

| Loại kết quả | Bên phát hành | Bên được phép nhận | Kiểm tra chính |
| --- | --- | --- | --- |
| **OIDC ID Token** | OpenID Provider | **OIDC client/Relying Party (RP)** | **iss** trùng OP tin cậy, **aud** có **client_id** của RP |
| **OAuth 2.0 JWT access token** | Authorization Server | **Resource Server/API** | **iss** trùng AS tin cậy, **aud** có mã định danh API dự kiến; kiểm tra quyền/scope |
| **OAuth 2.0 opaque access token** | Authorization Server | Resource Server có quan hệ introspection | API xác minh/introspect trạng thái và đích sử dụng theo quy ước AS/API; không thể tự đọc JWT claim |
| **SAML Assertion** | SAML IdP | **Service Provider (SP)** | Chữ ký, **Issuer**, **AudienceRestriction**, **Recipient/Destination** và điều kiện liên quan |

Hai giá trị **aud** cho hai mục đích thường khác nhau:

~~~json
{
  "token_kind": "ID Token (mô tả ngoài token)",
  "iss": "https://login.example.org/realms/company",
  "sub": "employee-847",
  "aud": "staff-portal"
}
~~~

~~~json
{
  "token_kind": "JWT access token (mô tả ngoài token)",
  "iss": "https://login.example.org/realms/company",
  "sub": "employee-847",
  "aud": ["urn:reports-api"],
  "scope": "reports.read"
}
~~~

**token_kind** ở hai khối trên chỉ là nhãn giải thích do tài liệu thêm vào, **không phải claim chuẩn mặc định của OIDC/OAuth**. Những JSON này cũng lược bỏ các trường và phần chữ ký cần có trong token thực tế.

Hệ quả:

- ID token có **aud=staff-portal** được web client nhận để chứng minh danh tính; API **reports-api** phải từ chối nếu được gửi ID token ấy như Bearer access token.
- Access token có **aud=urn:reports-api** không phải bằng chứng OIDC login dành cho **staff-portal**, ngay cả khi bên phát hành là cùng OP.
- Access token có **aud=urn:billing-api** không được dùng để gọi **reports-api**, dù mang scope trông giống **reports.read**.
- Kiểm tra **scope/roles** là bước **sau** khi đã xác nhận token đúng issuer và audience; scope không sửa được lỗi sai audience.

Trong OIDC, **aud** của ID token có thể là một chuỗi hoặc danh sách. RP phải xác minh danh sách chứa **client_id** của chính mình; khi có audience bổ sung thì phải áp dụng yêu cầu tin cậy đối với các audience đó. Không so sánh bằng cách tìm chuỗi con.

## 5. Phân biệt iss, aud, azp, client_id, sub và các URL khác

| Trường | Vai trò | Điều không nên nhầm |
| --- | --- | --- |
| **iss** | “Ai phát hành token này?” | Không phải domain của trình duyệt hay email người dùng |
| **aud** | “Token này được phát cho bên nhận nào?” | Không phải danh sách role hoặc quyền |
| **azp** trong ID token OIDC | “Authorized party”; được dùng trong các trường hợp quy định bởi OIDC/extension, thường liên quan client nhận ủy quyền | Không thay thế bắt buộc kiểm tra **aud** |
| **client_id** | ID ứng dụng đăng ký tại AS/OP; với JWT access token theo profile RFC 9068 còn có claim **client_id** | Không mặc định đồng nghĩa audience của access token |
| **sub** | Định danh chủ thể trong phạm vi issuer | Không phải ID toàn cục giữa mọi tenant; không mặc định là email |
| **redirect_uri** | Endpoint client nhận phản hồi authorization code | Không thay thế **aud**; redirect URI cần được đăng ký/kiểm tra riêng |
| **scope** | Quyền client yêu cầu/được cấp cho API | Không chứng minh danh tính theo OIDC |
| **kid** | Gợi ý chọn khóa xác minh từ tập khóa đáng tin | Không cho phép tự chọn nhà phát hành hay thay thế việc xác minh chữ ký |

### Khi nào kiểm tra azp?

Với **OIDC ID token**, client kiểm tra audience chứa client_id của mình. Nếu ID token có **azp**, hãy áp dụng quy tắc OIDC/extension tương ứng; trường hợp thông dụng client xác minh **azp** trùng client_id của mình. Với nhiều audience cần xem xét cả bên được tin cậy và nghĩa của azp, không chấp nhận vô điều kiện.

**Không đồng nhất azp với client_id trong mọi loại access token.** Một số IdP đưa claim **azp** vào access token, nhưng đây không phải cấu trúc chung của OAuth 2.0. Nếu API phải giới hạn **ứng dụng nào được phép gọi**, hãy yêu cầu token profile và claim định danh client mà chính AS đã chuẩn hóa/cam kết (ví dụ **client_id** theo RFC 9068); kiểm chứng chúng sau khi token đã được xác minh, kết hợp chính sách scope và subject.

### Khi nào dùng (iss, sub)?

Khóa liên kết tài khoản người dùng nên dựa trên **cặp (issuer, subject)**. Hai issuer khác nhau có thể phát cùng **sub** nhưng nói về hai người khác nhau. Đổi issuer hoặc đổi cách ánh xạ tenant là một sự kiện an ninh/dữ liệu cần được xử lý rõ ràng, không tự gộp theo **sub** hay email.

## 6. Quy trình nhận ID token từ một OP được phép

Ví dụ RP **staff-portal** chỉ chấp nhận đăng nhập từ **https://login.example.org/realms/company**:

1. Quản trị viên đăng ký RP ở OP: **client_id=staff-portal**, redirect URI chính xác và phương thức xác thực client nếu là confidential client; khai báo scope phù hợp.
2. RP cấu hình **provider/issuer cố định đã được duyệt** và dùng metadata của issuer này để tìm authorization endpoint, token endpoint, JWKS.
3. Người dùng truy cập chức năng login. RP gửi authorization request có **openid**, Authorization Code Flow, **state**, PKCE và nonce khi yêu cầu; lưu ngữ cảnh issuer và request.
4. RP nhận callback, đối chiếu request đã khởi tạo (chống CSRF, mix-up), trao đổi code với **token endpoint đúng issuer**.
5. RP lấy ID token và xác minh tối thiểu: chữ ký/thuật toán được chấp thuận, **iss**, **aud chứa client_id=staff-portal**, hạn **exp**, các điều kiện **iat/nbf** nếu áp dụng, **nonce nếu đã gửi**, và **azp** theo quy tắc OIDC liên quan.
6. RP chỉ tạo phiên ứng dụng sau khi token vượt qua xác minh; định danh người dùng nội bộ dựa trên **(iss, sub)**.
7. RP thực thi kiểm tra phân quyền nghiệp vụ riêng. **Xác thực người dùng không tự động cấp mọi quyền**.

**Nguyên tắc fail closed:** nếu không xác minh được issuer, chữ ký, audience, callback hoặc các điều kiện quan trọng thì dừng đăng nhập; không tự “tạm bỏ qua kiểm tra” để giữ trải nghiệm SSO.

### Hai OP cùng được phép

Nếu RP hỗ trợ cả **company** và **partner**, phải cấu hình hai **ClientRegistration/provider** đã được duyệt. Request bắt đầu với provider nào phải được đối chiếu với phản hồi provider đó. Khi client liên hệ nhiều AS, cần chống **authorization server mix-up** (ví dụ issuer trong response theo RFC 9207 hoặc biện pháp tương đương được chuẩn hóa), tránh dùng nhầm token endpoint/khóa của provider khác.

Chỉ dùng email có domain **@example.org** để quyết định tự động tin một URL issuer mới là **không an toàn**. Địa chỉ email hoặc claim tenant lấy từ token chưa xác minh chỉ có thể là **gợi ý chọn cấu hình trong allowlist**, không phải chứng cứ để mở rộng allowlist.

## 7. Quy trình API nhận access token đúng audience

Giả sử **reports-api** nhận request Bearer, token phát bởi issuer production:

1. Xác định **các issuer được phép** cho API theo cấu hình/tập policy cố định.
2. Với JWT, chọn validator/khóa đã gắn với issuer tin cậy, xác minh chữ ký và thuật toán.
3. So sánh **iss** chính xác và kiểm tra **exp/nbf** trong giới hạn clock skew hợp lý.
4. Kiểm tra **aud** có **urn:reports-api**. Token có audience dành cho ứng dụng khác phải bị từ chối.
5. Nếu API yêu cầu profile JWT access token như RFC 9068, kiểm tra thêm loại token **typ=at+jwt** hoặc **application/at+jwt**, cùng các claim bắt buộc của profile; không mặc định coi mọi JWT là access token.
6. Kiểm tra **scope/permission** cho endpoint (ví dụ **reports.read**) và quyền nội bộ/tenant của subject. Nếu chỉ một số client được gọi API, xác minh danh tính client từ claim do issuer định nghĩa và chính sách cho phép.
7. Sau khi tất cả điều kiện đạt, API mới xử lý yêu cầu.

Nếu token là **opaque**, resource server không thể xác minh chữ ký JWT và claim theo cách trên; dùng **token introspection** hoặc cơ chế AS công bố, rồi thực thi kiểm tra audience/quyền tương đương dựa trên thông tin AS trả về. Không tự decode chuỗi opaque như JWT.

**Lưu ý về OAuth:** access token có thể đại diện người dùng hoặc machine client (ví dụ **client_credentials**). Có token hợp lệ chưa chắc là người dùng đã đăng nhập tương tác. Nếu nghiệp vụ cần “nhân viên đã đăng nhập”, phải thiết kế yêu cầu về subject, grant/auth context và kiểm soát phù hợp; không suy ra chỉ từ scope.

## 8. Triển khai bằng Spring Security 6.x và Spring Boot 3.x (Java 17+)

Ví dụ minh họa một ứng dụng Spring MVC vừa làm **OIDC Relying Party** cho **/me**, vừa làm **OAuth 2.0 Resource Server** cho **/api/reports**. Hai luồng sử dụng cùng issuer production nhưng **kiểm tra audience khác nhau**.

Đây là mã có thể đưa vào **dự án Maven Spring Boot 3.x, Java 17+**. Để chạy thực tế, tổ chức phải có OP với issuer/discovery hợp lệ, đăng ký client **staff-portal**, cấu hình audience **urn:reports-api**, phát access token đúng scope, và cung cấp biến môi trường. URL **example.org** chỉ là chỗ minh họa, không phải dịch vụ đăng nhập thực.

### 8.1. Maven dependencies

Thêm các dependency sau trong **pom.xml** của dự án Spring Boot dùng BOM/parent thích hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 8.2. application.yml – chỉ tin issuer đã được duyệt

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/company
          audiences:
            - urn:reports-api
~~~

Ý nghĩa:

- **client.provider.company.issuer-uri** giới hạn OP mà OIDC client tin tưởng. Từ issuer, Spring lấy metadata để thực hiện login và xác minh ID token dành cho **client_id** đã đăng ký.
- **resourceserver.jwt.issuer-uri** giúp API kiểm tra **iss** của JWT access token và tìm khóa ký theo cấu hình issuer.
- **resourceserver.jwt.audiences** kiểm tra **aud** của JWT có **urn:reports-api**, tránh chấp nhận token của client/API khác.
- **client-id** phải trùng client đăng ký ở OP. Chỉ dùng biến môi trường hoặc secret manager cho client secret; không đưa secret thật vào source control.
- Đăng ký chính xác redirect URI trên OP, mặc định với registrationId **staff** là **{baseUrl}/login/oauth2/code/staff**. Không cấu hình wildcard redirect URI.
- Nếu issuer có nhiều tenant/realm, cấu hình đúng issuer của tenant được phép; không tự thay bằng issuer gốc hoặc hostname gần giống.

### 8.3. Hai filter chain tách ứng dụng web và API

**SecurityConfig.java** – thuộc package **com.example.federation**:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_reports.read"))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

- **/api/** là API Bearer token, phân quyền theo authority **SCOPE_reports.read** (Spring thường ánh xạ scope OAuth sang authority có tiền tố **SCOPE_**).
- Trang **/me** đi qua OIDC login, nhận thông tin người dùng đã được xác thực. Hai filter chain phân biệt cơ chế nhận chứng cứ.
- Chỉ tắt CSRF đối với các endpoint API phi trạng thái dùng Bearer theo thiết kế này; phần web login giữ CSRF mặc định.
- Việc có nhiều chain không làm xuất hiện thêm nhà phát hành tin cậy. Cả hai chain vẫn phải sử dụng chính sách issuer và audience đã cấu hình.

### 8.4. Controller quan sát danh tính đã xác minh

**DemoController.java** – cùng package:

~~~java
package com.example.federation;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getSubject()
        );
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(@AuthenticationPrincipal Jwt token) {
        return Map.of(
            "issuer", token.getClaimAsString("iss"),
            "audience", String.join(",", token.getAudience()),
            "subject", String.valueOf(token.getSubject())
        );
    }
}
~~~

Các giá trị trả về phụ thuộc token do OP thực tế phát hành; tài liệu không giả định subject, JWT hay JSON cố định. Trong production, tránh lộ claim không cần thiết và áp dụng chính sách bảo vệ dữ liệu.

**Chạy:** đặt các class này trong ứng dụng Spring Boot có **@SpringBootApplication**, cấu hình parent/BOM Maven, issuer thực và biến **OIDC_CLIENT_ID/OIDC_CLIENT_SECRET**; chạy **mvn spring-boot:run**. URL bắt đầu đăng nhập thủ công là **/oauth2/authorization/staff**. Truy cập **/me** khi chưa đăng nhập sẽ đi vào luồng OIDC login. Nếu issuer minh họa chưa thay bằng IdP thật, ứng dụng sẽ không thể hoàn thành login và resource-server discovery.

**Kỳ vọng kiểm tra API** (với IdP thật đã cấu hình):

| Yêu cầu tới /api/reports | Kết quả mong đợi |
| --- | --- |
| Không có Bearer token | **401 Unauthorized** |
| Access token sai issuer, sai audience, hết hạn hoặc chữ ký sai | **401 Unauthorized** |
| Access token hợp lệ đúng issuer/audience nhưng thiếu scope **reports.read** | **403 Forbidden** |
| Access token hợp lệ đúng issuer/audience và có scope **reports.read** | **200 OK**, controller trả metadata ví dụ |

Các mã trạng thái là hành vi điển hình theo cấu hình nêu trên; chi tiết body/header có thể phụ thuộc phiên bản Spring Security và error handling của dự án.

### 8.5. Nếu chỉ cho một nhóm client gọi API

Kiểm tra **issuer + audience** xác định nhà phát hành và API nhận token. Tuy nhiên, cùng một API có thể phục vụ nhiều client. Nếu nghiệp vụ quy định chỉ **staff-portal** và một batch client có thể gọi một endpoint, bổ sung **chính sách định danh client** sau khi token được xác thực.

Chẳng hạn nếu AS cam kết phát **JWT access token theo RFC 9068** có claim **client_id**, resource server có thể viết validator tùy chỉnh để chỉ nhận client ID trong allowlist. Một ví dụ rút gọn cho **chỉ client staff-portal**:

~~~java
// Ví dụ phương pháp, đặt cùng lớp @Configuration.
// Cần các import org.springframework.security.oauth2.jwt.*,
// org.springframework.security.oauth2.core.*,
// org.springframework.security.oauth2.core.validator.*.
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://login.example.org/realms/company";
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> allowedAudience = jwt ->
        jwt.getAudience().contains("urn:reports-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> allowedClient = jwt ->
        "staff-portal".equals(jwt.getClaimAsString("client_id"))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Client is not allowed", null));

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        allowedAudience,
        allowedClient
    ));
    return decoder;
}
~~~

**Cách dùng an toàn:** đây là **ví dụ bổ sung để thay thế cấu hình JwtDecoder mặc định**, không tự động ghép vào code ở mục 8.3. Cần thêm import cụ thể để đưa vào lớp cấu hình của dự án. Bean này phải tiếp tục kiểm tra **issuer, thời gian, audience**; khi triển khai theo **RFC 9068** cần bổ sung kiểm tra **token type/typ** và các yêu cầu profile, không cho rằng đoạn rút gọn đã bao phủ mọi chính sách. Đặc biệt, chỉ yêu cầu **client_id** nếu token thật có claim được AS bảo đảm; với OP dùng claim khác, phải xác nhận semantics từ tài liệu OP trước khi viết validator. Nếu chính sách cho nhiều client, thay phép so sánh đơn bằng allowlist.

Không sử dụng **sub** hoặc **email** để suy ra client ứng dụng. Cũng không dùng một claim client chưa xác minh để tự quyết định chấp nhận issuer mới.

## 9. SAML federation: ranh giới tương tự, tên trường khác

Trong SAML 2.0 SSO, SP nhận **SAML Response/Assertion** từ IdP. Ý tưởng tương ứng:

- **Issuer:** định danh EntityID của IdP đã thiết lập quan hệ trust; kiểm tra chữ ký bằng certificate/metadata tin cậy tương ứng.
- **AudienceRestriction:** giới hạn assertion cho **SP entityID** phù hợp, tránh SP khác tái sử dụng.
- **SubjectConfirmationData.Recipient:** giới hạn endpoint/ACS được nhận bearer assertion.
- **Destination, InResponseTo, NotBefore, NotOnOrAfter:** ràng buộc phản hồi với endpoint, yêu cầu đăng nhập và khoảng hiệu lực theo profile/flow.
- **Replay prevention và correlation:** chống assertion bị dùng lại hoặc response được gắn vào yêu cầu sai; kiểm tra điều kiện theo profile.

Ví dụ IdP phát assertion cho SP **https://portal.example.org/saml/metadata** thì SP **https://admin.example.org/saml/metadata** không thể nhận thay chỉ vì dùng cùng certificate xác minh IdP.

**Đừng áp dụng máy móc claim tên OIDC vào XML SAML.** Kiểm tra issuer, audience và recipient là ý niệm chung về trust boundary, còn trường, profile chữ ký, quy tắc response và thư viện kiểm tra khác nhau. Với Spring Security SAML2 Service Provider, cấu hình **relying party registration** gồm asserting party/metadata và kiểm tra SAML qua module tương ứng, không dùng **oauth2Login()** để xử lý SAML.

## 10. Rủi ro khi triển khai sai

### 10.1. Trust bất kỳ issuer / tự tải JWKS theo token

**Sai:** API đọc claim **iss** chưa xác minh, ghép URL discovery/JWKS tùy ý rồi tin chữ ký từ URL đó. Kẻ tấn công có thể lập issuer và tự ký token “hợp lệ” theo khóa của chính họ, thậm chí gây SSRF khi API gọi tới host nội bộ.

**Đúng:** chỉ chọn issuer từ allowlist đáng tin, metadata/JWKS gắn với issuer đã phê duyệt; chống SSRF và giữ chính sách thuật toán/chữ ký phù hợp.

### 10.2. Chỉ kiểm tra chữ ký và exp, bỏ qua aud

**Sai:** staff-portal nhận ID token của vendor-portal hoặc reports-api nhận access token phát cho billing-api vì cả hai đều do OP company ký.

**Đúng:** mỗi RP/API kiểm tra audience dành riêng cho mình, đồng thời kiểm tra đúng mục đích/loại token.

### 10.3. Token substitution: dùng ID token như access token

**Sai:** API chấp nhận ID token Bearer có **aud=staff-portal**. Trong một số kiến trúc, điều này có thể dẫn đến lộ quyền vì token được phát cho luồng login chứ không cho API.

**Đúng:** API chỉ nhận access token đúng profile và audience của API. Nếu dùng JWT access token theo RFC 9068, yêu cầu **typ=at+jwt** hoặc giá trị tương đương chuẩn khi cấu hình validator theo profile; quy tắc xác minh cho ID/access token phải tách biệt.

### 10.4. Nhầm tenant vì cùng email hoặc sub

**Sai:** hai tenant có **sub=123** hoặc email giống nhau thì coi là cùng người dùng.

**Đúng:** định danh và quyền gắn với **(iss, sub)**, tenant đã phê duyệt và ánh xạ rõ ràng; xác thực tenant/organization claim theo chính sách sau xác minh.

### 10.5. Tạo client/redirect URI quá rộng

**Sai:** bất kỳ client/redirect URI nào trên cùng domain đều được nhận code/token; client production dùng redirect URI wildcard hoặc secret chia sẻ.

**Đúng:** đăng ký client riêng, redirect URI chính xác, Authorization Code + PKCE, bảo vệ state/nonce và secret của confidential client; cấp scope và audience tối thiểu.

### 10.6. Lỗi mix-up khi nhiều IdP

**Sai:** RP khởi tạo login tại OP A nhưng nhận callback và xử lý bằng token endpoint/khóa OP B.

**Đúng:** gắn request với issuer đã chọn; đối chiếu issuer của authorization response theo RFC 9207 hoặc biện pháp tương đương; từ chối phản hồi sai luồng.

### 10.7. Định dạng token hoặc thuật toán không phù hợp

**Sai:** coi bất kỳ chuỗi ba đoạn Base64URL nào là JWT hợp lệ; chấp nhận **alg=none**; dùng thuật toán/khóa ngoài chính sách hoặc chỉ decode payload.

**Đúng:** kiểm tra chữ ký thực sự, thuật toán được cho phép, khóa thuộc issuer tin cậy; xây quy tắc xác minh riêng cho từng loại JWT và yêu cầu nội dung bắt buộc.

### 10.8. Có login thì mặc định có mọi quyền

**Sai:** người đã được IdP xác thực sẽ được tự động quyền admin trong mọi ứng dụng.

**Đúng:** định danh từ issuer/audience hợp lệ chỉ là bước xác thực. Phân quyền dựa trên vai trò, scope, quyền dữ liệu, tenant và điều kiện nghiệp vụ được kiểm tra tại từng ứng dụng/API.

## 11. Phương án quản trị trust trong hệ thống nhiều ứng dụng

Một chính sách cấu hình nên ghi rõ cho từng consumer:

| Consumer | Trusted issuer | Audience được nhận | Loại chứng cứ | Quyền/điều kiện bổ sung |
| --- | --- | --- | --- | --- |
| **staff-portal** | issuer **company** | OIDC ID token có **aud=staff-portal** | OIDC ID token | nonce, azp nếu áp dụng, liên kết (iss, sub) |
| **vendor-portal** | issuer **partner** đã duyệt | OIDC ID token có **aud=vendor-portal** | OIDC ID token | tenant đối tác, role vendor |
| **reports-api** | issuer **company** | access token có **aud=urn:reports-api** | JWT/opaque access token phù hợp | **reports.read**, chính sách client nếu có |

Khi thêm một bên phát hành, quy trình nên gồm: xác minh tổ chức vận hành IdP; xác nhận issuer chính xác và metadata; duyệt client registration/redirect URI; quy tắc ID/access token; kiểm thử token sai issuer/sai audience; giới hạn tenant và kế hoạch thu hồi trust. Không trao quyền truy cập API hoặc làm user-linking chỉ dựa trên trường email được chia sẻ.

**Key rotation:** khóa ký có thể được luân phiên trong cùng một issuer. Ứng dụng có thể refresh JWKS theo cơ chế thư viện và cache phù hợp, nhưng **thay đổi khóa không được mở rộng tập issuer tin cậy**. Khi ngừng tin một OP, xóa/chặn cấu hình trust theo quy trình vận hành và xử lý phiên/token còn hiệu lực theo chính sách riêng.

**Multiple issuers cho API:** chọn authentication manager/decoder theo issuer **trong danh sách cho phép**, rồi kiểm tra audience và policy tương ứng từng issuer. Dữ liệu iss trong JWT chưa xác minh chỉ có thể là **selector vào allowlist**; không được biến nó thành URL discovery tự do. Một API được phép nhận nhiều issuer **không đồng nghĩa** chấp nhận tất cả tenant hoặc mapping claim giống nhau.

## 12. Bài tập phân loại chấp nhận/từ chối

Giả định **staff-portal** chỉ tin issuer **company** và có client_id **staff-portal**; **reports-api** chỉ tin issuer **company** và yêu cầu audience **urn:reports-api** cùng scope **reports.read**.

| Tình huống | Quyết định | Lý do |
| --- | --- | --- |
| ID token **iss=company**, **aud=staff-portal**, chữ ký/thời gian/nonce hợp lệ | RP **có thể chấp nhận** | Đúng issuer và audience, còn cần đầy đủ điều kiện OIDC |
| ID token **iss=company**, **aud=vendor-portal** | RP **từ chối** | Sai audience dù chữ ký đúng |
| ID token **iss=test-login**, **aud=staff-portal** | RP **từ chối** | Issuer không được duyệt |
| ID token **iss=company**, **aud=staff-portal**, chữ ký sai | RP **từ chối** | Không xác minh được nguồn phát hành thực sự |
| Access token **iss=company**, **aud=urn:reports-api**, có **reports.read** và hợp lệ | API **có thể chấp nhận** | Đúng issuer, audience và quyền, còn tùy policy khác |
| Access token **iss=company**, **aud=urn:billing-api**, có **reports.read** | API **từ chối** | Scope không thay thế audience |
| Access token **iss=company**, **aud=urn:reports-api**, thiếu **reports.read** | API **từ chối quyền** | Authentication có thể hợp lệ nhưng authorization chưa đạt |
| ID token **aud=staff-portal** gửi làm Bearer tới reports-api | API **từ chối** | Sai loại token và audience |
| Access token signed OK nhưng đã quá **exp** | API **từ chối** | Đã hết hiệu lực |
| ID token với **sub=123** từ issuer partner | Không tự ghép user company có **sub=123** | Subject chỉ ổn định trong phạm vi issuer |

Lưu ý chữ **“có thể chấp nhận”** vì bảng chưa liệt kê mọi điều kiện: chính sách xác thực, scope, client, token type, key, request binding và tenant vẫn phải đáp ứng.

### Câu hỏi kiểm tra

**Câu 1:** Nếu hệ thống sử dụng chung JWKS, liệu mọi ứng dụng trong công ty đều có thể nhận cùng một ID token?  
**Trả lời:** Không. Mỗi RP vẫn phải kiểm tra **iss**, **aud chứa client_id của chính mình**, chữ ký và các điều kiện xác thực khác. Việc cùng dùng khóa phát hành không biến client B thành audience hợp lệ của token dành cho client A.

**Câu 2:** API chỉ cấu hình **issuer-uri** trong Spring Security đã đủ chống token gửi nhầm API chưa?  
**Trả lời:** Chưa. Phải kiểm tra audience riêng của API, ví dụ thuộc tính **resourceserver.jwt.audiences**, và quyền/scope; nếu cần còn phải kiểm tra token type và client được phép.

**Câu 3:** Claim **iss** của JWT chưa xác minh ghi domain mới thì có nên tải JWKS domain đó không?  
**Trả lời:** Không. Chỉ được chọn một issuer đã có trong allowlist tin cậy; sau đó dùng metadata/key gắn với issuer đó và kiểm chứng token.

**Câu 4:** Nếu một token có **aud** đúng, có thể bỏ qua signature vì “đã gửi đúng ứng dụng”?  
**Trả lời:** Không. Audience chỉ là một claim có thể bị sửa trong token chưa xác minh. Chữ ký, issuer, thời gian, loại token và audience đều cần được kiểm chứng.

**Câu 5:** Một API hợp lệ cho nhiều client, có nhất thiết phải giới hạn client nào được gọi không?  
**Trả lời:** Tùy nghiệp vụ. **aud** bảo đảm token hướng tới API; nếu chính sách chỉ cho một nhóm ứng dụng gọi, phải có kiểm tra bổ sung client identity (và scope/quyền) dựa trên token profile được issuer bảo đảm.

## 13. Checklist trước khi đưa federation lên production

- [ ] Chỉ có issuer/OP/IdP nằm trong allowlist đã duyệt; dùng URL/EntityID **chính xác theo tenant**.
- [ ] Metadata, JWKS/certificate và thuật toán kiểm tra được ràng buộc với đúng issuer tin cậy; không dynamic trust từ token chưa xác minh.
- [ ] OIDC RP xác minh ID token có **aud đúng client_id**, kiểm tra **iss, exp, signature, nonce/azp** theo quy tắc OIDC.
- [ ] OAuth resource server chỉ nhận access token đúng **issuer, audience API, thời gian, signature/introspection** và token profile được triển khai.
- [ ] Tách quy tắc ID token, access token và SAML Assertion; không token substitution.
- [ ] Kiểm tra **state/PKCE**, redirect URI exact, chống mix-up với nhiều IdP và replay.
- [ ] Định danh người dùng theo **(iss, sub)** và ràng buộc tenant/đơn vị đã được cấp quyền.
- [ ] Quyền API/ứng dụng (scope, role, permission, client allowlist) được kiểm tra riêng sau xác thực.
- [ ] Đã thử các tình huống âm: sai issuer, sai audience, sai loại token, sai chữ ký, hết hạn, thiếu quyền, tenant không được phép.
- [ ] Secret và token được bảo vệ; có quy trình key rotation, thu hồi liên kết trust và logout/session phù hợp.

**Quy tắc ghi nhớ:** **Issuer trả lời “Tôi có tin bên phát hành chứng cứ này không?”; audience trả lời “Chứng cứ này có được phát cho chính tôi không?”; kiểm tra quyền trả lời “Chủ thể/client này có được làm hành động yêu cầu không?”. Phải đạt cả ba tầng trước khi cho phép thao tác.**

## 14. Tài liệu tham khảo chính thức

- [OpenID Connect Core 1.0 – ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation): quy tắc xác minh **iss, aud, azp, signature, exp, nonce**.
- [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): kiểm tra issuer, audience, **typ=at+jwt** và **client_id** của JWT access token theo profile.
- [RFC 8725 – JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): validation riêng cho từng loại JWT, chống cross-JWT confusion.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect URI, PKCE, CSRF và bảo vệ mix-up.
- [RFC 9207 – Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): xác minh issuer trong authorization response khi client hỗ trợ nhiều AS.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): khai báo OIDC client registration và issuer.
- [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer-uri, audiences, decoder, token validators.
- [Spring Security – SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): relying party và SAML SP trust.
