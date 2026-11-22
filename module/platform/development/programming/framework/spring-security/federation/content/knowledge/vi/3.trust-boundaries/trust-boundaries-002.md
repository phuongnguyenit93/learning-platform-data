# Thiết lập tin cậy bằng metadata, khóa, chứng thư và cấu hình đối tác

> **Phạm vi:** Spring Security – federation / Ranh giới tin cậy. Bài này hướng dẫn cách thiết lập và vận hành quan hệ tin cậy giữa ứng dụng và nhà cung cấp danh tính (Identity Provider – IdP) khi dùng **OpenID Connect (OIDC)** hoặc **SAML 2.0**, bao gồm cấu hình đối tác, xác minh thông điệp, quản trị khóa/chứng thư, xoay khóa và kiểm thử. Ví dụ Spring dùng ứng dụng **Servlet/MVC**, Java 17+ và Spring Security 6.x trong Spring Boot 3.x. Một cấu hình minh họa chỉ hoạt động khi IdP và client/SP thực sự được đăng ký đúng.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Xác định **ranh giới tin cậy**: bên nào phát hành tuyên bố danh tính, bên nào xác minh, bên nào lập phiên và bên nào quyết định quyền truy cập.
2. Đọc đúng **OIDC Discovery metadata/JWKS** và **SAML IdP/SP metadata**; phân biệt dữ liệu mô tả endpoint với bằng chứng mật mã.
3. Thiết lập **nguồn tin cậy ban đầu** (trust bootstrap) và cấu hình đối tác bằng issuer/entity ID, client ID, redirect/ACS, khóa/chứng thư, thuật toán và policy.
4. Phân biệt **TLS certificate**, **chứng thư ký SAML**, **khóa công khai trong JWKS**, **khóa riêng của SP**, **client secret**, **ID Token** và **access token**.
5. Cấu hình một ứng dụng Spring Security nhận đăng nhập OIDC hoặc SAML mà không vô tình tin issuer, khóa, chứng thư hay URL do người dùng tùy ý cung cấp.
6. Thiết kế vòng đời khóa, xoay chứng thư, kiểm tra thông điệp không hợp lệ, thay đổi đối tác và quy trình xử lý sự cố.

## 2. Mô hình tin cậy: ai công bố, ai xác minh?

**Federation** cho phép một ứng dụng dựa trên kết quả xác thực do một hệ thống khác phát hành. Với OIDC, ứng dụng là **Relying Party (RP)**, IdP đóng vai **OpenID Provider (OP)**. Với SAML, ứng dụng là **Service Provider (SP)** và hệ thống xác thực là **IdP/Asserting Party**.

```text
               +------------------------+
               | IdP/OP đáng tin cậy    |
               | Xác thực người dùng    |
               | Giữ khóa RIÊNG ký      |
               +-----------+------------+
                           |
          (1) metadata: issuer/entity ID, endpoint,
              khóa CÔNG KHAI hoặc chứng thư
                           |
                           v
 +------------------+   (2) cấu hình tin cậy    +--------------------+
 | Chủ ứng dụng /    | ------------------------> | RP/SP Spring       |
 | quản trị đối tác  |                          | Security           |
 +------------------+                          +---------+----------+
                                                         ^
               (3) kết quả xác thực có chữ ký             |
 IdP/OP --------------------------------------------> RP/SP
                                                       |
                           (4) xác minh chữ ký, issuer, |
                               audience, thời gian,    |
                               ngữ cảnh giao dịch      |
                                                       v
                                             Tạo Authentication
                                             + phiên ứng dụng
                                                       |
                                            (5) kiểm tra quyền
```

Điểm quan trọng nhất là **metadata và khóa chỉ có ý nghĩa khi ứng dụng biết vì sao nguồn công bố chúng đáng tin**. Một tập tin XML chứa chứng thư, hay một JWKS chứa public key, **không tự biến nơi phát hành thành IdP được phép đăng nhập**. Người quản trị phải thiết lập đối tác từ kênh đã xác thực, giới hạn issuer/entity ID và endpoint hợp lệ, rồi ứng dụng mới dùng metadata để kiểm chứng thông điệp.

**Bốn lớp tin cậy cần phân biệt:**

| Lớp | Câu hỏi | Kiểm soát thường gặp |
| --- | --- | --- |
| Quan hệ đối tác | Tổ chức/tenant/IdP này có được phép xác thực người dùng cho ứng dụng không? | Danh sách đối tác được phê duyệt, người sở hữu, hợp đồng, tenant và quy trình change |
| Metadata và khóa | Ứng dụng biết issuer, endpoint, khóa công khai/chứng thư từ đâu? | Địa chỉ metadata cố định, HTTPS, nguồn phân phối xác thực, kiểm tra chứng thư/metadata theo chính sách |
| Giao dịch xác thực | Response/token/assertion có thật sự do đúng đối tác phát hành, dành cho đúng RP/SP và còn hiệu lực không? | Chữ ký, `iss`/`Issuer`, `aud`/`Audience`, `exp`, `state`, `nonce`, `InResponseTo`, chống replay |
| Quyền và vòng đời | Danh tính đó được làm gì, phiên còn hiệu lực bao lâu và lúc nào phải thu hồi? | Ánh xạ tài khoản, tenant, role, session, provisioning/deprovisioning, logout, audit |

**Ví dụ phản chứng:** Kẻ tấn công có thể tạo một JWT, tự sinh RSA key, đăng public key vào JWKS của họ và ký JWT hợp lệ bằng private key tương ứng. Chữ ký có thể xác minh toán học, nhưng ứng dụng **phải từ chối** nếu issuer/key không nằm trong quan hệ đối tác đã được phê duyệt. **Xác minh chữ ký khác với quyết định tin bên ký.**

## 3. Phân biệt chính xác các loại metadata, khóa và chứng thư

| Thành phần | OIDC/OAuth 2.0 | SAML 2.0 | Điều ứng dụng cần bảo đảm |
| --- | --- | --- | --- |
| Danh tính bên phát hành | `issuer` (URI, giá trị `iss`) | `entityID` của IdP, `Issuer` trong assertion | Khớp đối tác đã cấu hình; tránh nhầm tenant |
| Metadata | JSON OpenID Provider Configuration | XML `EntityDescriptor`/`IDPSSODescriptor` | Lấy từ nguồn đúng, xác thực và theo dõi thay đổi |
| Endpoint | `authorization_endpoint`, `token_endpoint`, `jwks_uri`… | `SingleSignOnService`, có thể có `SingleLogoutService` | Scheme, host, đường đi phù hợp allowlist và deployment |
| Khóa xác minh | JWKS, khóa public được mô tả bằng JWK | X.509 certificate trong `KeyDescriptor` hoặc cấu hình tin cậy | Chỉ dùng khóa của issuer/entity ID đã chấp thuận |
| Khóa ký riêng của IdP | IdP giữ bí mật, ký ID Token/SAML Assertion | IdP giữ bí mật, ký Assertion/Response | RP/SP không cần và không được đòi private signing key của IdP |
| Thông tin đăng ký bên nhận | `client_id`, secret/phương thức client auth, `redirect_uri`, scope | SP `entityID`, ACS URL, bindings, metadata, SP certificates | IdP phải đăng ký đúng bên nhận |
| Kết quả đăng nhập | ID Token (JWT), có thể kèm UserInfo | `SAMLResponse`/`Assertion` | Kiểm chứng ngữ nghĩa **sau khi** xác minh nguồn phát và chữ ký |
| Bảo vệ kênh | HTTPS/TLS cho discovery, token, callback | HTTPS/TLS cho metadata, SSO, ACS | TLS bảo vệ đường truyền; không thay thế xác minh thông điệp |
| Mật liệu bí mật của ứng dụng | Client secret/private key JWT/client credential tùy cấu hình | Private key SP khi ký request hoặc giải mã assertion | Lưu trong secret manager, phân quyền và có kế hoạch xoay |

**Không đồng nhất các thuật ngữ:**

- **TLS certificate của `https://idp.example.org`** phục vụ xác thực máy chủ và mã hóa kênh HTTPS; nó có thể do CA công cộng cấp.
- **JWK/JWKS** biểu diễn khóa xác minh chữ ký token (thường RSA/EC). Một JWK có thể kèm `x5c`, nhưng không phải mọi JWKS đều chứa chứng thư. Trust thường đến từ issuer/discovery endpoint đã cấu hình và TLS, không đơn thuần từ chuỗi CA của `x5c`.
- **Chứng thư X.509 trong SAML metadata** chứa public key dùng kiểm tra chữ ký SAML. Nó có thể là chứng thư tự ký; việc tin nó thường dựa trên cấu hình IdP/metadata cụ thể, **không mặc định là kiểm tra Web PKI như chứng thư TLS**.
- **Private key** phải nằm ở hệ thống sở hữu nó. RP/SP chỉ cần public key của IdP để kiểm tra chữ ký IdP; SP có thể cần private key của **chính SP** để ký `AuthnRequest` hoặc giải mã Assertion.
- **Client secret** của OAuth confidential client là thông tin xác thực client tại token endpoint, không phải khóa dùng xác minh chữ ký của ID Token.
- **Mã hóa** bảo vệ tính bí mật; **ký số** hỗ trợ xác minh toàn vẹn và nguồn phát; **xác thực danh tính** còn cần issuer, audience, thời gian và ngữ cảnh phiên.

## 4. Khởi tạo quan hệ tin cậy: điểm xuất phát phải được kiểm soát

Một quá trình onboarding đối tác nên bắt đầu **ngoài luồng đăng nhập của người dùng**:

1. **Xác định chủ thể:** tên tổ chức, người phụ trách IdP, tenant/realm, hệ thống môi trường (test, staging, production) và mục đích xác thực.
2. **Trao đổi định danh tĩnh:** OIDC issuer URL hoặc SAML IdP `entityID`; RP `client_id` hoặc SP `entityID`; giới hạn tập đối tác được phép.
3. **Trao đổi metadata từ kênh đáng tin:** portal quản trị có xác thực, kênh quản trị nội bộ, URL HTTPS được phê duyệt hoặc tệp ký được xác minh theo chính sách. Không nhập metadata URL từ tham số query của trình duyệt.
4. **Đăng ký điểm trả về:** OIDC `redirect_uri` chính xác; SAML ACS URL và bindings tương thích. Phân biệt từng môi trường và xử lý proxy thật.
5. **Định nghĩa chính sách token/assertion:** thuật toán được chấp thuận, audience, thời hạn, clock skew, MFA/ACR nếu có yêu cầu, thuộc tính danh tính bắt buộc, mapping role.
6. **Thiết lập tài khoản và kiểm thử:** test user, nhóm, tình huống không được cấp quyền, logout, rotation, IdP downtime. Chỉ bật production sau khi hoàn tất kiểm thử âm.
7. **Ghi lại dấu vết thay đổi:** ngày nhận metadata, phiên bản/chứng thư, người phê duyệt, thời hạn, lịch rotate và cách rollback.

**Trust bootstrap khác trust runtime:** Bước bootstrap cho phép đưa đúng đối tác và public key vào cấu hình; bước runtime xác minh từng message dựa trên cấu hình đó. Một redirect được gửi tới ứng dụng không được phép tự mở rộng trust store.

### Mẫu hồ sơ đối tác (tài liệu nghiệp vụ, không phải cấu hình Spring Boot)

```yaml
partner:
  id: corp-idp-prod
  owner: identity-platform-team
  environment: production
  protocol: oidc
  issuer: https://login.example.org/realms/employees
  relying-party:
    client-id: portal-web-prod
    redirect-uri: https://portal.example.org/login/oauth2/code/corporate
  accepted-signing-algorithms: [RS256]
  identity-key: [issuer, subject]
  account-mapping: internal-user-id
  change-process: security-approved
  rotation-contact: identity-platform-team
```

Dữ liệu trên chỉ mô tả **hợp đồng tin cậy**. Những giá trị như domain, client ID và thuật toán là ví dụ; phải lấy từ đối tác thật. Không đưa client secret/private key vào hồ sơ chia sẻ rộng. Không dùng `accepted-signing-algorithms` như một cấu hình Spring Boot có sẵn nếu chưa triển khai validator/decoder tương ứng.

## 5. OIDC: khám phá metadata và xác minh đúng issuer

Với OIDC, **OpenID Provider Configuration** là tài liệu JSON giúp RP khám phá endpoint và khả năng của OP. Khi dùng issuer tiêu chuẩn `https://login.example.org/realms/employees`, RP cần thực hiện discovery đúng quy tắc OIDC và xác nhận giá trị `issuer` trong tài liệu trả về **bằng chính xác issuer tin cậy đã cấu hình**. Không suy diễn issuer từ hostname của callback hay giá trị `iss` của token chưa kiểm tra.

Những trường cần nhận biết:

| Field | Mục đích | Sai sót dễ gặp |
| --- | --- | --- |
| `issuer` | Định danh duy nhất của OP; ID Token có `iss` tương ứng | Nhầm tenant, bỏ qua path/realm hoặc dấu slash |
| `authorization_endpoint` | Nơi trình duyệt đi xác thực/cấp quyền | Chuyển tới endpoint không được cấu hình/phê duyệt |
| `token_endpoint` | Backend đổi authorization code lấy token | Lộ client secret, sai client auth hoặc gửi code sang endpoint giả |
| `jwks_uri` | Địa chỉ bộ public signing keys của OP | Dùng URL từ header `jku` do token đề xuất thay cho URL tin cậy |
| `response_types_supported` | Những kiểu response được OP hỗ trợ | Dùng flow không phù hợp với web app |
| `id_token_signing_alg_values_supported` | Thuật toán OP công bố có thể dùng ký ID Token | Cho phép thuật toán yếu/ngoài chính sách chỉ vì metadata liệt kê |
| `end_session_endpoint` (nếu có) | Endpoint phục vụ logout theo khả năng OP | Coi logout RP luôn xóa phiên IdP |

**Mẫu trích đoạn JSON minh họa cấu trúc** (chỉ có các trường tiêu biểu, chưa phải metadata hoàn chỉnh):

```json
{
  "issuer": "https://login.example.org/realms/employees",
  "authorization_endpoint": "https://login.example.org/realms/employees/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.org/realms/employees/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.org/realms/employees/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

**Kiểm tra nguồn:** HTTPS bảo vệ lần tải metadata và JWKS; URL issuer phải có nguồn gốc từ hồ sơ đối tác đã phê duyệt; endpoint khám phá phải thuộc phạm vi có thể kiểm soát. Nếu doanh nghiệp vận hành IdP dùng path hoặc endpoint tùy biến, cấu hình phải phản ánh chính xác metadata được phát hành, không sửa `issuer` theo suy đoán.

### 5.1. JWKS không phải “danh sách ai cũng được tin”

**JSON Web Key Set (JWKS)** chứa tập khóa công khai, mỗi khóa có thể có `kty`, `kid`, `use`, `alg`, `n`/`e` (RSA) hoặc `crv`/`x`/`y` (EC). `kid` giúp lựa chọn khóa trong tập khóa **đã gắn với issuer**, bản thân `kid` không chứng minh ai là issuer. Hai IdP khác nhau có thể trùng `kid`.

Đối với ID Token ký bằng JWT, một pipeline đúng là:

1. Xác định **đối tác/registration đã cấu hình** theo luồng login đã khởi tạo.
2. Sử dụng metadata/JWKS của **issuer đó** để tìm khóa ứng viên theo `kid` và thuật toán được cho phép.
3. Xác minh chữ ký và từ chối thuật toán không được phê duyệt, `alg=none`, hoặc cố dùng HMAC key như RSA public key.
4. Kiểm tra `iss`, `aud`, `exp`, `iat` và `nonce` khi có; kiểm tra `azp` theo quy tắc OIDC nếu ID Token có nhiều audience; áp dụng kiểm soát `state` trên callback.
5. Xây `Authentication` và lập session RP **sau** toàn bộ kiểm tra; giữ việc cấp authority độc lập với kết luận xác thực.

**Không lấy `jku`, `x5u`, `kid` hoặc `iss` chưa tin từ JWT rồi tự động tải khóa tại URL tùy ý**. Đây là đường dẫn thường dẫn tới key substitution, SSRF hoặc cross-tenant token acceptance. Bản thân JWT đã giải mã Base64URL nhưng chưa xác minh **không phải dữ liệu đáng tin**.

### 5.2. ID Token khác access token; audience của API khác audience của client

- **ID Token** là tuyên bố danh tính cho RP/client; `aud` phải phù hợp `client_id` và các ràng buộc OIDC. Nó **không** dùng làm Bearer credential gọi API chỉ vì có chữ ký.
- **Access token** do Authorization Server cấp cho Resource Server; API phải kiểm tra chữ ký hoặc introspection, issuer, audience phù hợp **API**, thời hạn và scope/authority. ID Token có thể có cùng `iss` nhưng audience khác.
- **Client authentication** khi RP đổi code có thể dùng `client_secret_basic`, `private_key_jwt` hoặc phương thức IdP cho phép; client secret không thay thế quy tắc xác minh ID Token.
- **Authorization Code + PKCE** bảo vệ giao dịch đổi code; `state` chống login CSRF và liên kết callback; `nonce` liên kết ID Token với phiên giao dịch khi flow yêu cầu. Cấu hình tin cậy đúng vẫn cần các kiểm soát theo giao dịch này.

## 6. Cấu hình OIDC Relying Party trong Spring Security

Ví dụ tối thiểu cho **ứng dụng Spring Boot 3.5.0/Java 17**. Nó dùng endpoint khám phá issuer, callback được đăng ký và `oauth2Login()`. Mã không chứa bí mật thật và không giả định bạn đã có IdP. Thiết kế này minh họa **một** OIDC partner được quản trị tĩnh.

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>federation-trust</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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

**Tệp `src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile
        provider:
          corporate:
            issuer-uri: ${OIDC_ISSUER_URI}
```

**Tệp `src/main/java/demo/FederationTrustApplication.java`:**

```java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FederationTrustApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationTrustApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/")
        String home() {
            return "Open /whoami to authenticate with the corporate IdP";
        }

        @GetMapping("/whoami")
        Map<String, String> whoami(@AuthenticationPrincipal OidcUser user) {
            return Map.of(
                    "issuer", user.getIdToken().getIssuer().toString(),
                    "subject", user.getIdToken().getSubject());
        }
    }
}
```

**Tại IdP**, tạo một **web/confidential OIDC client** có client ID/secret tương ứng và đăng ký chính xác `http://localhost:8080/login/oauth2/code/corporate`. `OIDC_ISSUER_URI` phải là issuer được chính OP công bố, gồm cả path/realm/tenant. Khi chạy qua reverse proxy hoặc ở production, dùng callback HTTPS, host public và cấu hình forwarded headers từ **proxy đáng tin**.

**Chạy trên bash:**

```bash
export OIDC_ISSUER_URI='https://login.example.org/realms/employees'
export OIDC_CLIENT_ID='portal-demo'
export OIDC_CLIENT_SECRET='actual-secret-from-your-test-idp'
mvn spring-boot:run
```

**Trên PowerShell:** đặt lần lượt `$env:OIDC_ISSUER_URI`, `$env:OIDC_CLIENT_ID`, `$env:OIDC_CLIENT_SECRET` bằng giá trị IdP thử nghiệm rồi chạy `mvn spring-boot:run`. Các giá trị trên chỉ minh họa: thay bằng registration thật mới có thể chạy đăng nhập.

Vào `http://localhost:8080/` để xem chuỗi cố định **`Open /whoami to authenticate with the corporate IdP`**. Vào `http://localhost:8080/whoami` sẽ yêu cầu đăng nhập; sau callback hợp lệ, endpoint trả JSON gồm `issuer` và `subject` do IdP cung cấp nên **không có kết quả giá trị cụ thể cố định**. Endpoint mở đầu luồng bằng tay là `/oauth2/authorization/corporate`.

**Bài học cấu hình:** `issuer-uri` là trust anchor ở mức định danh OP trong registration đã được phê duyệt; Spring Security sử dụng provider metadata và khóa công khai để thực hiện xác minh ID Token trong OIDC login. Không tự viết bộ parser JWT hoặc tự giải mã token rồi tin claims. `client-secret` phải được truyền từ kho bí mật/môi trường, giới hạn quyền đọc, không commit vào Git và không ghi log.

### Khi ứng dụng là OAuth2 Resource Server, cấu hình khác

Một **API** nhận Bearer access token nên sử dụng mô hình Resource Server, thường trong **dịch vụ riêng**. Với JWT, ví dụ phần cấu hình của API dùng Spring Boot 3.5.x:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/employees
          audiences: api://orders
```

Phải có dependency `spring-boot-starter-oauth2-resource-server` và security filter chain phù hợp, ví dụ sử dụng `oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))`. `audiences` là audience **của API** theo hợp đồng cấp token, không thay bằng client ID của trang login. API còn cần quy tắc `hasAuthority(...)` hoặc phân quyền nghiệp vụ cho từng tài nguyên. Nếu AS phát opaque token, dùng introspection với thông tin xác thực phù hợp; không coi opaque token là JWT.

**Tình huống thay thế hợp lệ:** Có Resource Server cần khởi động ngay cả khi OP tạm thời không phục vụ discovery; cấu hình thêm `jwk-set-uri` cố định **cùng** `issuer-uri` được phê duyệt có thể tránh phụ thuộc việc gọi discovery lúc startup, trong khi vẫn duy trì kiểm tra issuer. Khi dùng URL JWKS tĩnh, người vận hành chịu trách nhiệm xác minh URL, rotation và audience; không tắt issuer validation để “cho dễ chạy”.

## 7. SAML 2.0: metadata và chứng thư ký của hai phía

Trong SAML Web Browser SSO, metadata thường là XML:

- **IdP `EntityDescriptor`** có `entityID`, `IDPSSODescriptor`, `SingleSignOnService` (binding và location), `KeyDescriptor` cho signing/encryption nếu công bố, tùy chọn logout.
- **SP `EntityDescriptor`** có `entityID`, `SPSSODescriptor`, `AssertionConsumerService` (ACS), optional SingleLogoutService, các binding, và chứng thư SP dùng ký yêu cầu/giải mã khi cần.
- Chứng thư trong `KeyDescriptor use="signing"` là public key để xác minh chữ ký. Chứng thư `use="encryption"` dành cho mã hóa/giải mã theo vai trò; **không thay thế lẫn nhau**.
- SAML XML metadata có thể được **ký ở cấp metadata**; khác với chữ ký của **SAML Response/Assertion**. Nếu policy yêu cầu metadata signature, phải có khóa đáng tin để xác minh metadata trước khi cập nhật cấu hình. Metadata không ký chỉ nên được chấp nhận từ kênh trao đổi được bảo vệ, đã xác thực và có kiểm soát phiên bản.

**Luồng đăng ký:**

```text
SP owner                                  IdP owner
  |  Cung cấp SP entityID, ACS, bindings     |
  |----------------------------------------->|
  |     Nhận IdP entityID, SSO URL, cert     |
  |<-----------------------------------------|
  |                                            |
  |  SP lưu trust: IdP entityID + signing cert|
  |  IdP lưu registration: SP entityID + ACS  |
  |                                            |
  |  SP tạo AuthnRequest -------------------->|
  |<-- SAMLResponse ký qua trình duyệt -------|
  |  SP xác minh rồi mới tạo session          |
```

**Cần xác minh những gì trên SAML Response/Assertion?**

1. **Chữ ký XML hợp lệ** trên thành phần được chính profile và cấu hình bảo vệ (Response hoặc Assertion phù hợp), dựa trên chứng thư của IdP được tin; không lấy chứng thư gửi kèm message để tự coi là trust anchor mới.
2. **`Issuer`** phải là IdP/entity ID được cấu hình; đúng **`Destination`** của Response và **`Recipient`** trong SubjectConfirmationData theo thực tế triển khai.
3. **`AudienceRestriction`** phải chỉ đúng SP entity ID; trường hợp gửi Assertion cho SP A không được chấp nhận tại SP B.
4. **`NotBefore`, `NotOnOrAfter`**, có thể thêm điều kiện thời gian khác, được kiểm tra bằng đồng hồ đồng bộ và clock skew rất giới hạn.
5. **`InResponseTo`** phải khớp AuthnRequest đang chờ khi dùng SP-initiated flow. Phải xử lý correlation cho phiên/trình duyệt tương ứng, không chỉ nhìn XML “có chữ ký”.
6. **Replay protection:** dùng ID của Response/Assertion và trạng thái giao dịch để ngăn dùng lại trong khoảng hiệu lực; không tự triển khai xác minh XML bằng cách so sánh chuỗi hoặc regex.
7. **NameID/attributes:** chỉ nhận sau khi thông điệp qua kiểm chứng; ánh xạ tenant/user và authority theo chính sách nội bộ. Không tự cấp `ROLE_ADMIN` theo attribute chưa được thỏa thuận.

**Khác biệt quan trọng:** Chứng thư SAML IdP có thể tự ký và không thuộc Web PKI. Giá trị tin cậy nằm ở việc ứng dụng đã nhận/chấp thuận certificate đúng đối tác qua metadata/khâu onboarding. Tuy nhiên vẫn phải theo dõi hiệu lực chứng thư, lịch đổi khóa, thuật toán và chính sách validation của tổ chức. Một `X509Certificate` hợp lệ về cú pháp không bảo đảm assertion đáng tin nếu **entity ID hoặc audience sai**.

### 7.1. Cấu hình SP bằng metadata trong Spring Security

Khi sử dụng SAML 2.0 trên Servlet, dependency tiêu biểu là `org.springframework.security:spring-security-saml2-service-provider`. Ví dụ **đoạn cấu hình tích hợp** dưới đây giả định project đã có dependency Spring Security, Spring Web và một URL metadata IdP được phê duyệt. Đây là **mẫu thay thế cho cấu hình OIDC** ở mục 6 nếu ứng dụng chọn SAML; không ghép cả hai vào một `SecurityFilterChain` rồi coi là hai flow độc lập.

**Tệp `SamlSecurityConfiguration.java`** (trích đoạn lớp cấu hình, đặt trong package ứng dụng):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration corporate =
                RelyingPartyRegistrations
                        .fromMetadataLocation("https://sso.example.org/metadata")
                        .registrationId("corporate-saml")
                        .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
                        .assertionConsumerServiceLocation(
                                "{baseUrl}/login/saml2/sso/{registrationId}")
                        .build();

        return new InMemoryRelyingPartyRegistrationRepository(corporate);
    }

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
```

**Giải thích giới hạn:** Đường dẫn metadata là URL minh họa, phải đổi sang IdP thật. Cấu hình `fromMetadataLocation(...)` tạo registration từ metadata đã cung cấp; **chỉ thực hiện với nguồn đã được phê duyệt**. Nếu IdP cần `AuthnRequest` được ký hoặc Assertion được mã hóa, bổ sung credential của SP trong `RelyingPartyRegistration` và đăng public certificate của SP tại IdP. Ví dụ chưa cấu hình private key SP, logout, role mapping, replay storage trên cluster hay policy doanh nghiệp.

Đường đăng nhập mặc định thường bắt đầu bằng `/saml2/authenticate/corporate-saml`, ACS là `/login/saml2/sso/corporate-saml`. Với `saml2Metadata()`, ứng dụng có thể công bố metadata để IdP đăng ký SP; URL thực tế tùy `registrationId`, base URL và phiên bản. Hãy đối chiếu **metadata sinh ra bởi ứng dụng** với cấu hình tại IdP thay vì gõ lại endpoint theo trí nhớ.

**Không giả định thư viện tự làm mọi việc vận hành:** tùy phiên bản và cách cung cấp `RelyingPartyRegistration`, metadata/JWKS có thể được nạp hoặc cache tại thời điểm khác nhau; nhất là registration SAML được tạo một lần lúc startup thì việc cập nhật file metadata tại nguồn **không bảo đảm** tự cập nhật signing certificate trong tiến trình. Phải thử nghiệm kịch bản rotation và quy trình reload/restart phù hợp.

## 8. Metadata là hợp đồng kỹ thuật, không thay thế chính sách tin cậy

Cả OIDC và SAML đều có thể công bố hàng loạt endpoint/thuộc tính. Đừng mặc định đưa mọi trường vào ứng dụng:

- **Chỉ tin đối tác đã duyệt**: `registrationId` là mã nội bộ; OIDC `issuer` và SAML `entityID` là danh tính giao thức; chúng phải được ràng buộc 1–1 theo cấu hình rõ ràng hoặc theo quy tắc đa tenant có kiểm soát.
- **Không coi hostname giống nhau là cùng danh tính**: `https://idp.example.org/realm/a` khác `https://idp.example.org/realm/b`; `client_id` khác cũng có thể có policy khác.
- **Không dùng discovery như một open proxy**: URL khai báo từ request `?issuer=...` hoặc metadata XML do người dùng tải lên phải được kiểm duyệt. Nếu app tải tài liệu chưa tin, có rủi ro SSRF, truy cập địa chỉ nội bộ, thay endpoint và key substitution.
- **Giới hạn alg**: chỉ chấp nhận thuật toán chữ ký mà chính sách và thư viện hỗ trợ an toàn. Không ép thư viện chấp nhận `none` hoặc trộn RSA/HMAC. Khi metadata quảng cáo nhiều alg, lựa chọn thực tế vẫn bị giới hạn bởi policy RP/SP.
- **Giới hạn redirect/ACS**: callback phải đúng URL đã đăng ký và reverse proxy được cấu hình đúng. Không dùng ký tự wildcard rộng, open redirect, tên miền staging trong production hoặc URL tùy ý từ header không tin.
- **Quản lý thay đổi**: nhận metadata mới phải biết thay đổi gì (issuer/entity ID, endpoint, cert/key, alg), có approval và thử nghiệm; không tự coi mọi thay đổi từ remote host là được phép về nghiệp vụ.
- **Đồng bộ thời gian**: token/assertion ngắn hạn chịu ảnh hưởng clock skew; NTP và monitoring là một phần của vận hành tin cậy.
- **Quản lý danh tính**: mapping user theo khóa ổn định, ví dụ cặp `(issuer, sub)` với OIDC; SAML phụ thuộc NameID/attribute được thỏa thuận. Email hiếm khi là khóa định danh vĩnh viễn.
- **Tách authentication/authorization**: IdP xác thực người dùng; RP/API vẫn tự quyết quyền nội bộ và tenant. Nếu nhận role/group từ IdP, cần quy tắc mapping, đặc biệt với thuộc tính trùng tên ở nhiều đối tác.

### Đối tác nhiều tenant

Khi nhiều đối tác cùng đăng nhập vào một sản phẩm, mỗi đối tác có hồ sơ tin cậy và khóa tách biệt. Ví dụ:

```text
registration: company-a -> OIDC issuer https://idp-a.example/realms/work
registration: company-b -> OIDC issuer https://idp-b.example/tenant/b

company-a public keys KHÔNG được dùng xác minh token của company-b
company-b subject "123" KHÔNG phải cùng người với company-a subject "123"
```

Nếu định tuyến đối tác từ email domain, subdomain hoặc tham số tenant, kiểm tra mapping tenant tại backend và chỉ chọn **registration đã tồn tại, được phép**. Không tạo registration/issuer mới tự động từ đầu vào chưa xác thực. Với SAML, ràng buộc `RelyingPartyRegistration`, IdP entity ID, ACS và tenant người dùng; ngăn Assertion của đối tác A được xử lý trong ngữ cảnh B.

## 9. Chính sách lưu khóa và mật liệu bí mật

| Mật liệu | Nằm ở đâu | Ai cần quyền gì? | Quy tắc vận hành |
| --- | --- | --- | --- |
| OIDC signing **private key** | Hệ thống IdP/OP | Chỉ dịch vụ ký và nhóm bảo mật IdP | Không xuất private key sang RP; quản lý trong HSM/KMS nếu phù hợp |
| OIDC signing **public key/JWKS** | Endpoint công khai do OP quản trị | RP/RS tải để xác minh | Ràng với issuer, cache, theo dõi `kid`/alg/rotation |
| OAuth **client secret** | RP backend/secret manager và IdP | Chỉ hệ thống đổi code và người có thẩm quyền | Không commit, không log, không gửi xuống frontend |
| SAML IdP **signing private key** | IdP | Chỉ IdP | Bảo vệ tuyệt đối; công bố cert xác minh qua metadata |
| SAML IdP **signing certificate** | Metadata/trust config tại SP | SP cần public cert | Đối chiếu nguồn, theo dõi hết hạn, chấp nhận key rollover có kế hoạch |
| SAML SP **signing/decryption private key** | SP/secret manager | Chỉ SP cần thao tác ký/giải mã | Private key không gửi IdP; IdP nhận public certificate tương ứng |
| HTTPS **server private key** | TLS endpoint/reverse proxy | Chỉ thành phần kết thúc TLS | Quản lý theo PKI/TLS; không dùng thay logic xác minh federation |

**Khi nhập chứng thư SAML**, có thể dùng lệnh `keytool -printcert -file idp-signing.cer` để xem Subject, Issuer, thời hạn và fingerprints; thao tác này giúp **đối chiếu** chứng thư với nguồn đáng tin, không tự động phê duyệt chứng thư đó.

### Ví dụ Java 17 kiểm tra chứng thư X.509 nhận được

Đây là tiện ích **đọc certificate public và in thông tin kiểm kê**, không phải code xác minh SAML Response/Assertion. Java 17 cung cấp sẵn `CertificateFactory`, `MessageDigest` và `HexFormat`.

**Tệp `InspectCertificate.java`:**

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HexFormat;

public class InspectCertificate {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java InspectCertificate <certificate-file>");
            System.exit(2);
        }

        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            X509Certificate cert =
                    (X509Certificate) factory.generateCertificate(input);
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(cert.getEncoded());

            System.out.println("Subject: " + cert.getSubjectX500Principal());
            System.out.println("Issuer: " + cert.getIssuerX500Principal());
            System.out.println("Not before: " + cert.getNotBefore());
            System.out.println("Not after: " + cert.getNotAfter());
            System.out.println("SHA-256: " +
                    HexFormat.ofDelimiter(":").withUpperCase().formatHex(digest));
        }
    }
}
```

**Biên dịch/chạy:**

```bash
javac InspectCertificate.java
java InspectCertificate idp-signing.cer
```

File `idp-signing.cer` phải là chứng thư X.509 DER hoặc PEM hợp lệ. Chương trình in Subject, Issuer, thời hạn và SHA-256 fingerprint **phụ thuộc chứng thư thật**, nên không thể đưa ra một stdout cố định. Nếu file hỏng hoặc không phải certificate, `CertificateException` sẽ được phát sinh và chương trình không in thông tin giả. Khi import cert, so sánh fingerprint với đối tác qua **kênh độc lập đã xác thực**; không chấp nhận fingerprint chỉ vì nó trùng với certificate nằm trong chính tệp chưa tin.

**Tránh nhầm:** Phép băm SHA-256 fingerprint xác định bytes của certificate, **không chứng minh** IdP sở hữu domain, private key tương ứng hay có quyền phát hành người dùng trong tenant. Xác minh thông điệp SAML phải giao cho bộ kiểm chứng giao thức của Spring Security/OpenSAML đã được cấu hình đúng.

## 10. Vòng đời khóa và chứng thư: kế hoạch rotation

Một cấu hình ban đầu đúng sẽ trở nên lỗi thời nếu không có chính sách thay khóa. Các lý do phổ biến: hết hạn certificate, nghi ngờ lộ private key, thay IdP, nâng cấp thuật toán, đổi HSM/KMS, áp dụng chính sách mật mã mới.

**Quy trình xoay khóa ký an toàn (khi không có sự cố lộ khóa):**

1. **Chuẩn bị:** đối tác tạo signing keypair mới, lưu private key trong kho được bảo vệ; xác định thời gian `T0` và danh sách SP/RP chịu ảnh hưởng.
2. **Công bố public key/certificate mới trước:** với OIDC bổ sung JWK mới vào JWKS; với SAML đưa certificate mới vào metadata/config bên nhận theo cách thư viện hỗ trợ; chưa ngừng xác minh chữ ký bằng khóa cũ.
3. **Làm mới/cập nhật bên nhận:** xác nhận các RP/API đã có thể chọn khóa mới. Với cache JWKS, hiểu refresh policy; với SAML registration tĩnh, có thể cần cập nhật cấu hình và rollout ứng dụng.
4. **Chuyển signer tại IdP:** bắt đầu ký message mới bằng private key mới. `kid` (OIDC) hoặc cert signing (SAML) phải được bên nhận biết và tin.
5. **Quan sát:** theo dõi login success/failure, lỗi `unknown kid`, signature validation, SAML signature, từng tenant và instance; bảo đảm clock đồng bộ.
6. **Giữ overlap hợp lý:** khóa cũ vẫn có thể cần để xác minh token/assertion hợp lệ chưa hết hạn và xử lý các hệ thống lag; khoảng thời gian phụ thuộc TTL token, cache, delay và profile giao thức.
7. **Thu hồi khóa cũ:** sau khi hết thời gian cần thiết, xóa khỏi tập trusted keys/certs, thu hồi quyền dùng private key, cập nhật tài liệu và ghi bằng chứng hoàn tất.

**Nếu nghi ngờ private key bị lộ**, quy trình khẩn cấp khác với rotation bình thường: ngừng tin khóa bị lộ càng sớm càng tốt, phân tích token/assertion đã cấp, chủ động thu hồi session/credential khi có thể, truyền thông sự cố và chuyển sang khóa sạch. Không giữ overlap chỉ vì thói quen nếu khóa cũ đã bị xâm phạm.

**Thời hạn certificate khác thời hạn token:** một SAML certificate có thể hết hạn dù Assertion mới được ký ngắn hạn; một ID Token có thể hết hạn dù JWK vẫn đang công bố. Kiểm tra riêng chính sách kiểm chứng certificate, JWT TTL, session TTL và thời điểm rotate của IdP.

## 11. Kiểm thử tin cậy: bắt buộc có tình huống âm

| Kiểm thử | Hành vi kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| OIDC issuer đúng + ID Token hợp lệ | RP đăng nhập thành công | Đường tin cậy hoạt động |
| JWT có chữ ký hợp lệ bằng key của issuer **chưa được duyệt** | Từ chối | Không tin signer tùy ý |
| ID Token đúng chữ ký nhưng `aud` sai client | Từ chối | Chống token substitution |
| Access token của API X dùng tại API Y | API Y từ chối | Đúng audience từng tài nguyên |
| JWT `alg=none` hoặc alg ngoài allowlist | Từ chối | Thuật toán phải được giới hạn |
| Token `kid` không có trong JWKS tin cậy | Từ chối; refresh theo policy nếu phù hợp | Không tải khóa từ URL do token cung cấp |
| ID Token quá hạn hoặc nonce/callback state sai | Từ chối | Đúng ngữ cảnh và thời gian |
| SAML Response ký bởi cert của IdP lạ | Từ chối | Chứng thư phải thuộc đối tác |
| SAML Assertion sai `AudienceRestriction`/ACS recipient | Từ chối | Không dùng assertion sai đối tượng |
| SAML `InResponseTo` không khớp, message replay | Từ chối | Chống giả mạo callback/phát lại |
| Metadata tự đổi SSO URL sang domain lạ | Phát hiện, chặn/không áp dụng trước phê duyệt | Thay đổi endpoint cần quản lý |
| OIDC JWKS thêm key hợp lệ rồi signer chuyển key | Vẫn đăng nhập thành công trong giai đoạn rollout | Rotation có overlap đúng |
| Xóa key cũ sau thời gian an toàn | Token mới vẫn pass; token cũ hết hạn bị từ chối | Không phụ thuộc key cũ mãi |
| Quyền admin không có trong mapping user | User login được nhưng endpoint admin trả 403 | Tách xác thực với ủy quyền |
| User `sub=123` ở issuer A và `sub=123` ở issuer B | Hai principal độc lập | Không gộp account sai tenant |
| IdP mất kết nối hoặc cert hết hạn | Lỗi có kiểm soát, không bỏ qua validation | Fail closed |

Để chạy kiểm thử âm, sử dụng IdP và client **trong môi trường thử nghiệm**, không sửa token/signature để tấn công production. Thu thập status HTTP, phiên, registration ID và mã lỗi đã được làm sạch; không ghi ID Token, access token, secret, SAML Assertion nguyên bản hoặc session cookie vào dashboard/log công khai.

### Bảng đối chiếu triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách chẩn đoán |
| --- | --- | --- |
| OIDC discovery không khởi tạo được | Issuer URL sai, DNS/TLS lỗi, proxy chặn, metadata thiếu field | Từ backend truy cập URL cấu hình; xác minh hostname và giá trị `issuer` |
| `invalid_issuer` / token bị reject | Sai realm/tenant/issuer trong ID Token | So sánh `iss` với cấu hình đã duyệt; giữ nguyên xác minh |
| `invalid_signature` / unknown `kid` | JWKS cache cũ, ký bằng key mới chưa công bố, key sai issuer | Đối chiếu thay đổi JWKS và lịch rotation, refresh có kiểm soát |
| `invalid_client` khi đổi code | Client secret sai/đã xoay, cách client auth không khớp | Kiểm tra cấu hình client tại IdP và kho secret |
| `redirect_uri_mismatch` | Scheme/host/port/path, callback không đăng ký, proxy sai | Đọc authorization request thực và URI được đăng ký |
| SAML `invalid_signature` | Cert ký thay đổi, metadata sai, ký thành phần không như kỳ vọng | Kiểm tra chứng thư được tin, chữ ký và phiên bản cấu hình |
| SAML `invalid_destination` hoặc audience | ACS/entity ID khác IdP config, load balancer thay host | So sánh SP metadata, Assertion/Response và URL thực |
| SAML `InResponseTo` lỗi | Mất session, request state, IdP-initiated response ngoài chính sách | Kiểm tra correlation/cluster session, phân biệt flow |
| Đăng nhập được nhưng không xem tài nguyên | Role/authority mapping hoặc tenant policy từ chối | Kiểm tra ứng dụng trả 403, không nới rule authentication |
| Một số instance lỗi sau rotate | Rolling deployment dùng trust config không đồng nhất | Kiểm tra mọi instance có registration/cert/JWKS cache đúng |

**Nguyên tắc sửa lỗi:** Không vô hiệu hóa xác minh chữ ký, issuer, audience, thời hạn hay HTTPS chỉ để làm thông luồng đăng nhập. Hãy sửa **nguồn metadata**, registration, secret, cert, proxy và mapping cho đúng hợp đồng.

## 12. Quy trình đưa đối tác mới vào hệ thống

Một quy trình onboarding có thể đưa vào runbook:

**Bước A – hợp đồng và ranh giới.** Ghi đối tác, tenant, protocol (OIDC/SAML), user population, owner, môi trường, quyền được cấp và trách nhiệm rotation. Xác định đối tác có thể phát hành danh tính cho ai.

**Bước B – bootstrap metadata.** Tiếp nhận issuer/entity ID và metadata qua kênh được xác thực. Kiểm tra HTTPS, signature metadata nếu có yêu cầu, endpoint ngoài dự kiến, chứng thư/public key và thời hạn; lập baseline và fingerprint.

**Bước C – registration hai phía.** OIDC: đăng `client_id`, auth method, redirect URI, scopes, issuer. SAML: trao đổi IdP/SP metadata, entity IDs, ACS URL, bindings, signing/encryption certificates. Không dùng chung client secret hoặc SP private key giữa production và môi trường thử nếu không có chính sách cho phép.

**Bước D – cấu hình Spring.** Dùng `ClientRegistration`/OIDC `oauth2Login()` hoặc `RelyingPartyRegistration`/SAML `saml2Login()`; bảo đảm mỗi registration ràng đúng đối tác. API dùng Resource Server với audience/scope riêng khi nhận token.

**Bước E – thử cả hai hướng.** Chạy ca đăng nhập thành công, sai issuer, sai audience, signature, hết hạn, replay, thiếu quyền, redirect/ACS sai, thay key và IdP unavailable. Xem log đã lược bỏ bí mật.

**Bước F – phê duyệt và vận hành.** Bật đối tác trên production, bật metric login failure/rotation, xác định người nhận alert, kế hoạch rollback, lịch kiểm tra certificate expiry, thời hạn rà soát quyền và thời gian phản ứng sự cố.

**Bước G – offboarding.** Khi dừng hợp tác hoặc IdP thay đổi chủ sở hữu: tắt registration/tenant routing, thu hồi liên kết account/token/credential theo chính sách, kết thúc session phù hợp, gỡ cert/public key, dọn role mapping và audit.

### Checklist một trang cho người triển khai

- [ ] Có **issuer/entity ID từ đối tác được duyệt**, không lấy từ request của người dùng.
- [ ] URL metadata/JWKS/SSO được xác thực nguồn và kiểm tra thay đổi.
- [ ] Có cấu hình **client ID/redirect URI** (OIDC) hoặc **SP entity ID/ACS** (SAML) ở cả hai phía.
- [ ] Phân biệt đúng public signing key/certificate, TLS cert, client secret và private key SP.
- [ ] Validation đảm bảo issuer, audience, signature/alg, expiration và giao dịch `state`/`nonce`/`InResponseTo`.
- [ ] Mapping identity/tenant/authority không lấy email/group chưa tin làm quyền admin.
- [ ] Có rotation plan, lịch expiry, thử nghiệm cache/reload và rollback.
- [ ] Có kiểm thử âm, log không rò rỉ token/assertion/secret và monitoring phù hợp.

## 13. Bài tập thực hành

**Bài 1 – phân tích thiết kế:** Cho một cổng nhân viên dùng OIDC và ứng dụng kế toán cũ dùng SAML. Hãy vẽ hai đường tin cậy độc lập, chỉ rõ: bên ký, nơi lưu public key/cert, danh tính issuer/entity ID, redirect URI hoặc ACS, nơi cấp session và nơi thực hiện authorization.

**Bài 2 – kiểm tra hợp đồng:** Một đối tác gửi JWKS có hai khóa `kid=k1` và `kid=k2`, rồi chuyển signer từ `k1` sang `k2`. Hãy mô tả thứ tự triển khai tối thiểu để RP không bị downtime. Giải thích tại sao chỉ đổi tên `kid` trong cấu hình chưa đủ và vì sao không cho phép key từ `jku` tùy ý.

**Bài 3 – triển khai OIDC:** Dùng project mục 6 với IdP thử nghiệm. Xác nhận issuer từ discovery metadata trùng `OIDC_ISSUER_URI`, callback trùng registration, `/whoami` chỉ trả identity sau login. Thử đổi `OIDC_ISSUER_URI` sang realm khác và ghi nhận failure có kiểm soát; không sửa code để bỏ issuer validation.

**Bài 4 – triển khai SAML:** Lấy IdP metadata từ kênh được phê duyệt; kiểm tra entity ID, SingleSignOnService, signing cert. Cấu hình SP `entityID` và ACS giống IdP registration. Dùng một test user, rồi thử response sai audience hoặc cấu hình signing cert sai trong môi trường test để xác nhận ứng dụng từ chối.

**Bài 5 – phân tích sự cố:** Hai IdP phát cùng subject `"a123"`. Đội phát triển dùng `sub` đơn lẻ làm khóa bảng account. Hãy nêu cách sửa mô hình định danh, migration để tránh trộn tài khoản, và cách chứng minh mapping mới cô lập người dùng giữa hai IdP.

**Tiêu chí đạt:** Người học giải thích được **nguồn tin cậy ban đầu → metadata → khóa/chứng thư → xác minh từng thông điệp → mapping danh tính/tenant → authorization → vòng đời rotation/offboarding**; vận hành được ít nhất một RP/SP với IdP thử nghiệm và chứng minh ca token/assertion sai issuer hoặc audience bị từ chối.

## 14. Tài liệu gốc để đối chiếu

- Spring Security – OAuth 2.0 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/login/metadata.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- RFC 7517 – JSON Web Key: https://www.rfc-editor.org/rfc/rfc7517
- RFC 7519 – JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- OASIS SAML 2.0 Technical Overview: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
