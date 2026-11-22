# SAML 2.0, OpenID Connect, CAS và Kerberos trong hệ sinh thái danh tính

> **Ngữ cảnh:** Giao thức SSO (Single Sign-On) trong hệ sinh thái Spring Security và quản trị danh tính doanh nghiệp. Mục tiêu là hiểu luồng xác thực, vai trò của các thành phần, cách tích hợp và tiêu chí lựa chọn giao thức; không xem bốn giao thức là những cách phát hành token có thể hoán đổi tùy ý.

## 1. Nền tảng: SSO, xác thực và liên kết danh tính

**SSO** cho phép người dùng đăng nhập một lần tại một miền tin cậy rồi truy cập nhiều ứng dụng đã liên kết mà không nhập lại thông tin đăng nhập ở từng ứng dụng. SSO thường dựa vào phiên ở nhà cung cấp danh tính (Identity Provider, **IdP**) và cơ chế chuyển kết quả xác thực về ứng dụng.

Cần phân biệt:

- **Authentication (xác thực):** Bạn là ai? Ví dụ, IdP xác minh mật khẩu, MFA, khóa bảo mật hoặc thông tin Windows domain.
- **Authorization (phân quyền):** Bạn được làm gì trong ứng dụng? Quyền đọc báo cáo, sửa dữ liệu hay quản trị vẫn do chính sách của ứng dụng/quản trị truy cập quyết định.
- **Federation (liên kết danh tính):** Thiết lập quan hệ tin cậy để tổ chức/ứng dụng khác chấp nhận kết quả xác thực từ hệ thống danh tính đã chọn.
- **Provisioning:** Tạo, cập nhật, vô hiệu hóa tài khoản (ví dụ bằng SCIM hoặc đồng bộ danh bạ). Provisioning khác với đăng nhập SSO.
- **Session:** Sau khi xác thực thành công, ứng dụng web thường vẫn tạo phiên và cookie riêng. Đăng nhập một lần **không** có nghĩa bốn giao thức dùng chung một cookie hay cùng tự động đăng xuất.

Mô hình tham chiếu:

~~~text
Người dùng + trình duyệt
        |
        v
  Ứng dụng (Spring Security) ----> Chính sách quyền ứng dụng
        |
        | Yêu cầu xác thực qua giao thức phù hợp
        v
  IdP / OP / CAS Server / KDC
        |
        +---- Nguồn tài khoản: AD, LDAP, cơ sở dữ liệu, MFA
        |
        +---- Có thể làm identity broker giữa Kerberos, SAML và OIDC
~~~

Trong thực tế, **Active Directory/LDAP** thường là nguồn danh tính; **AD FS, Keycloak, Okta, Microsoft Entra ID hoặc Apereo CAS** có thể đóng vai trò cổng đăng nhập/federation tùy cấu hình. **KDC** (Key Distribution Center) là cơ sở hạ tầng cấp ticket Kerberos. Một sản phẩm IdP có thể hỗ trợ nhiều giao thức cùng lúc, nhưng mỗi kết nối ứng dụng vẫn cần cấu hình tin cậy riêng.

## 2. Bản đồ bốn giao thức

| Giao thức | Hai phía chính | Bằng chứng xác thực chuyển đi | Kịch bản tiêu biểu | Đặc điểm |
|---|---|---|---|---|
| **SAML 2.0** | IdP (Asserting Party) ↔ SP (Service Provider/Relying Party) | XML `SAMLResponse` chứa assertion, thường có chữ ký số | SSO B2B, SaaS/ứng dụng doanh nghiệp, tích hợp với hệ thống cũ | Metadata XML, chứng thư X.509, HTTP Redirect/POST |
| **OpenID Connect (OIDC)** | OpenID Provider (OP) ↔ Relying Party (RP/client) | `id_token` và có thể `access_token`/`refresh_token` | Web/mobile hiện đại, cloud IdP, tích hợp API | Lớp danh tính trên OAuth 2.0, JSON/JWT, discovery/JWKS |
| **CAS protocol** | CAS Server ↔ CAS-enabled Service | Service Ticket (ST) opaque, xác minh từ back channel | Đại học, cổng thông tin và ứng dụng có sẵn CAS | `service` URL phải khớp, ST thường dùng một lần |
| **Kerberos V5 + SPNEGO** | Client ↔ KDC ↔ service principal | Kerberos service ticket trong HTTP `Negotiate` | Windows domain, intranet, desktop/browser đã đăng nhập AD | KDC, realm, SPN, keytab, đồng bộ thời gian/DNS |

**Quy tắc quan trọng:** OAuth 2.0 tự thân là framework ủy quyền, **không** đảm bảo định danh người dùng. OIDC bổ sung lớp xác thực (đặc biệt là `id_token`). Ngược lại, một SAML assertion, CAS ST hay Kerberos ticket **không** phải access token OAuth 2.0 để đem gọi API bất kỳ.

## 3. SAML 2.0 — Federation qua assertion XML

### 3.1. Thành phần và luồng SP-initiated

- **SP/Relying Party:** ứng dụng nhận người dùng; trong Spring Security là ứng dụng dùng `saml2Login`.
- **IdP/Asserting Party:** nơi xác thực người dùng và ký SAML response/assertion.
- **Metadata:** tài liệu XML trao đổi `entityID`, endpoint SSO/ACS, binding và chứng thư tin cậy.
- **ACS (Assertion Consumer Service):** endpoint trên SP nhận `SAMLResponse`, thường bằng HTTP POST.

Luồng điển hình:

1. Trình duyệt vào trang cần bảo vệ của SP.
2. SP tạo `AuthnRequest`, điều hướng trình duyệt tới IdP (thường HTTP-Redirect binding).
3. IdP xác thực hoặc dùng lại phiên SSO/MFA đã có.
4. IdP gửi `SAMLResponse` qua trình duyệt tới ACS của SP (thường HTTP-POST binding).
5. SP kiểm chữ ký, issuer, audience, recipient/destination, thời hạn, tương quan request và các ràng buộc của assertion; sau đó tạo `Authentication` và phiên ứng dụng.
6. Ứng dụng tự xét quyền truy cập từ định danh/attribute đã ánh xạ.

**SP-initiated** có `AuthnRequest` để liên hệ phản hồi với yêu cầu; **IdP-initiated** có thể không có tương quan này, nên cần xét kỹ cơ chế chống phát lại, phiên không mong đợi và nguy cơ login CSRF trước khi bật.

Một số trường SAML đáng hiểu:

- `Issuer`: bên phát hành; phải khớp cấu hình tin cậy.
- `Subject/NameID`: định danh người dùng; không mặc định ổn định hay toàn cục.
- `AudienceRestriction`: assertion dành cho SP nào.
- `NotBefore/NotOnOrAfter`: cửa sổ hợp lệ, cần đồng bộ giờ.
- `InResponseTo`: liên kết tới yêu cầu khi có SP-initiated flow.
- `AttributeStatement`: thuộc tính người dùng/nhóm; phải ánh xạ quyền có kiểm soát.

**Ký số** xác thực tính toàn vẹn và nguồn assertion/response; **mã hóa assertion** bảo vệ nội dung khi có cấu hình, không tự xảy ra vì đã ký. Chứng thư xác minh và rotation phải được quản lý; tuyệt đối không chấp nhận chữ ký từ chứng thư bất kỳ do client tự đưa.

### 3.2. Spring Security với SAML

Spring Security hỗ trợ ứng dụng làm **SAML Service Provider**, không biến ứng dụng thành SAML IdP chỉ bằng gọi `saml2Login()`. Thành phần chính là `spring-security-saml2-service-provider` và `RelyingPartyRegistrationRepository`. Với Spring Boot, có thể khai báo IdP metadata như sau:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          enterprise-saml:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
~~~

Đây là **cấu hình minh họa**: URL phải là metadata thực sự từ IdP được tin cậy; SP phải được đăng ký bên IdP, cùng entity ID, ACS URL và chính sách ký/mã hóa. Metadata được lấy qua mạng cần có nguồn/chuỗi tin cậy phù hợp. Một số triển khai cần khai báo rõ chứng thư, khóa ký của SP, hoặc điều chỉnh ACS theo reverse proxy.

Endpoint mặc định phổ biến của Spring Security:

- `/saml2/authenticate/{registrationId}`: bắt đầu yêu cầu đăng nhập.
- `/login/saml2/sso/{registrationId}`: nhận response tại ACS.
- `/saml2/metadata/{registrationId}`: xuất metadata SP khi bật `saml2Metadata`.

Luồng sản xuất cần kiểm tra metadata và đăng ký SP ở cả hai đầu. Với thư viện dựa trên OpenSAML, cấu hình build có thể cần Maven repository Shibboleth theo tài liệu phiên bản đang dùng.

## 4. OpenID Connect — Xác thực trên OAuth 2.0

### 4.1. Định nghĩa và các token

OIDC là lớp xác thực bổ sung cho OAuth 2.0. Ứng dụng là **Relying Party/client**; nhà cung cấp định danh là **OP**.

- **Authorization code:** mã ngắn nhận qua redirect; ứng dụng đổi ở token endpoint, không coi là danh tính và không dùng như access token.
- **`id_token`:** JWT chứa claims về sự kiện xác thực, dành cho **client/RP**. Kiểm `iss` (issuer), `aud` (client ID), chữ ký/JWKS, `exp` và `nonce` nếu có yêu cầu.
- **`access_token`:** dành cho **resource server/API**; có thể là JWT hoặc opaque, không nên mặc định tự giải mã như JWT. Kiểm token theo chính sách resource server.
- **`refresh_token`:** nếu được cấp, dùng xin token mới và phải lưu trữ/bảo vệ chặt hơn; không phải token định danh.
- **`scope=openid`:** dấu hiệu yêu cầu OIDC; `profile`, `email` là các scope tùy nhu cầu. `sub` là định danh ổn định trong phạm vi issuer và theo chính sách OP.

OIDC discovery tại đường dẫn `/.well-known/openid-configuration` giúp client lấy URL authorization/token/UserInfo, JWKS và thông tin khả năng của OP.

### 4.2. Authorization Code Flow với PKCE

1. RP tạo `state` chống CSRF và PKCE `code_verifier`/`code_challenge`; có thể tạo `nonce` để ràng buộc ID Token.
2. Trình duyệt được chuyển tới authorization endpoint của OP kèm `client_id`, `redirect_uri`, `response_type=code`, `scope=openid`, `state` và PKCE.
3. OP xác thực (có thể dùng phiên SSO/MFA), chuyển browser về redirect URI đã đăng ký cùng `code`/`state`.
4. RP kiểm `state` rồi gửi code và `code_verifier` đến token endpoint qua back channel; confidential client còn xác thực client nếu được yêu cầu.
5. RP kiểm ID Token, tạo phiên đăng nhập ứng dụng; chỉ đưa access token tới API phù hợp audience/scope.

**PKCE** ngăn việc kẻ tấn công chặn mã code rồi đổi token; nên sử dụng cho cả public client và các luồng code hiện đại khi OP hỗ trợ. Ưu tiên exact redirect URI đã đăng ký, HTTPS, cookie an toàn; không đặt access token/ID token tùy tiện vào localStorage hay URL.

### 4.3. Spring Security với OIDC

Trong ứng dụng Spring Boot có `spring-boot-starter-oauth2-client`, cấu hình tối thiểu:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise-oidc:
            provider: enterprise-oidc
            client-id: demo-client
            client-secret: REPLACE_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          enterprise-oidc:
            issuer-uri: https://idp.example.org/realms/company
~~~

Giá trị `client-id`/`client-secret` là placeholder và phải thay qua nguồn cấu hình/bí mật bảo mật; không commit secret thật. Khi `issuer-uri` hợp lệ, Spring có thể dùng discovery. Mặc định thường có:

- `/oauth2/authorization/enterprise-oidc`: bắt đầu login.
- `/login/oauth2/code/enterprise-oidc`: redirect URI xử lý authorization code.

Spring Security dùng `oauth2Login()` để đăng nhập người dùng; `oauth2ResourceServer()` là chức năng **khác** để API kiểm access token. Khi dùng `openid` scope, Spring Security chọn đường xử lý OIDC, có thể truy cập `OidcUser` và các claims tin cậy sau xác thực.

**OIDC logout** có local logout, RP-Initiated Logout và tùy khả năng OP có back-channel logout. Không được suy ra rằng xóa cookie Spring đã chấm dứt phiên tại OP hoặc mọi ứng dụng khác.

## 5. Ví dụ tích hợp Spring Boot: SAML và OIDC cùng một ứng dụng

Dưới đây là **mã Java hoàn chỉnh ở mức lớp ứng dụng**, dùng Java 17+ và Spring Boot hỗ trợ Spring Security 6/7. Đây không phải chương trình `javac` độc lập: cần dự án Spring Boot, các dependency, IdP hoạt động và cấu hình client/SP đã đăng ký mới thực hiện được đăng nhập thực.

Tạo dự án Spring Boot với các dependency tương ứng: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, `spring-security-saml2-service-provider`. Dùng dependency management cùng dòng Spring Boot/Spring Security tương thích.

Tệp `src/main/java/com/example/sso/FederationDemoApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FederationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederationDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/saml2/metadata/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SSO demo";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Cấu hình `application.yml` có thể kết hợp hai nhánh `spring.security.oauth2.client` và `spring.security.saml2.relyingparty` ở trên. Lệnh chạy trong **thư mục dự án Maven có Maven Wrapper**:

~~~bash
./mvnw spring-boot:run
~~~

Kiểm tra `GET /` trả đúng chuỗi phản hồi `SSO demo`; truy cập `GET /me` khi chưa đăng nhập sẽ dẫn tới quy trình xác thực. Sau khi đăng nhập thành công, `/me` trả tên trong `Authentication` (giá trị thực tế phụ thuộc principal/mapper của IdP). Không thể ấn định stdout console hay danh tính của người dùng khi chưa có môi trường IdP thật.

**Giải thích:** `SecurityFilterChain` yêu cầu xác thực cho `/me`; `oauth2Login` và `saml2Login` cài hai cơ chế authentication tương ứng; `saml2Metadata` xuất metadata SP để đăng ký với IdP. Không gọi đồng thời hai flow cho một lần login: người dùng chọn registration/cơ chế thích hợp, còn ứng dụng đều nhận `Authentication` của Spring Security. Khi triển khai sau load balancer/reverse proxy, kiểm soát `X-Forwarded-*` từ proxy đáng tin và xác minh external base URL/ACS/redirect URI.

## 6. CAS — Central Authentication Service

### 6.1. CAS server, TGC, TGT và Service Ticket

**CAS** vừa là tên một giao thức SSO dạng ticket vừa là tên hệ sinh thái phần mềm **Apereo CAS**. CAS Server có thể hỗ trợ OIDC/SAML qua module tương ứng, nhưng **CAS protocol** dùng luồng service ticket riêng.

Luồng tiêu biểu:

1. Người dùng mở service, chẳng hạn `https://app.example.org/login/cas`.
2. Service chuyển trình duyệt đến `https://sso.example.org/cas/login?service=<encoded-service-url>`.
3. CAS Server xác thực người dùng hoặc dùng phiên SSO đã tồn tại. TGT được quản lý phía CAS server; browser giữ cookie **TGC** liên hệ tới phiên SSO, không phải tùy tiện mang TGT tới ứng dụng.
4. CAS chuyển browser về đúng `service` với query `ticket=ST-...`.
5. **Backend của service** gọi endpoint xác minh như `/cas/serviceValidate` kèm ticket và **chính xác service URL** đã khai báo.
6. Nếu validation thành công, service tạo session nội bộ và gán danh tính/roles. ST thường ràng buộc một service và dùng một lần; không lưu ST làm credential dài hạn.

Ví dụ dạng luồng HTTP (URL minh họa, không phải ST thật):

~~~http
GET https://sso.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas

HTTP/1.1 302 Found
Location: https://app.example.org/login/cas?ticket=ST-example-once

GET https://sso.example.org/cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-example-once
~~~

Không suy ra URL đã mã hóa giống nhau từ chuỗi `service` hơi khác (scheme/host/port/path). CAS có thể hỗ trợ **Proxy-Granting Ticket/Proxy Ticket** cho một service thay mặt người dùng truy cập service khác; phải hạn chế proxy được phép, không bật mặc định chấp nhận mọi proxy.

### 6.2. Tích hợp Spring Security và CAS

Spring Security có các thành phần CAS như `CasAuthenticationEntryPoint` (redirect), `CasAuthenticationFilter` (nhận ticket), `CasAuthenticationProvider` (gọi validator), `ServiceProperties` (định nghĩa service URL). Thường phối hợp thư viện client Apereo CAS để xác minh ST. Cấu hình CAS **không** chỉ là gọi `oauth2Login()`; phải khai báo CAS server, service URL/validator và wiring filter/provider theo đúng phiên bản.

Trình tự cấu hình:

1. Đăng ký service URL HTTPS chính xác tại CAS Server.
2. Cấu hình entry point chuyển đến CAS login; filter bắt callback ticket; provider xác minh back channel qua HTTPS và tải/mapping authorities.
3. Kiểm tra lần đăng nhập đầu, reuse SSO cookie, ticket hết hạn, ticket bị phát lại, sai `service`, session timeout và đường logout.
4. Nếu tổ chức đã bật OIDC/SAML trên Apereo CAS, cân nhắc dùng Spring `oauth2Login`/`saml2Login` tới CAS dưới vai trò IdP/OP cho ứng dụng mới.

**Single Logout:** CAS server có thể gửi thông báo logout tới các service đã liên kết, nhưng xử lý session/cookie, trình duyệt và kết nối mất mạng cần kiểm chứng. Đăng xuất local một service không chắc sẽ xóa SSO session ở CAS.

## 7. Kerberos V5 và SPNEGO — SSO dựa trên ticket mạng nội bộ

### 7.1. Realm, KDC, TGT và service ticket

Kerberos sử dụng mật mã khóa đối xứng và các ticket do **KDC** cấp. Trong domain Windows, domain controller thường đảm nhiệm dịch vụ Kerberos. Danh tính dạng `alice@EXAMPLE.ORG` là **principal**; dịch vụ HTTP có SPN như `HTTP/app.example.org@EXAMPLE.ORG`.

Hai giai đoạn cần phân biệt:

1. Sau khi xác thực với **Authentication Service (AS)** thuộc KDC, client nhận **Ticket-Granting Ticket (TGT)**. TGT cho phép yêu cầu ticket dịch vụ mà không gửi lại mật khẩu mỗi lần.
2. Client yêu cầu **Ticket-Granting Service (TGS)** cấp **service ticket** cho SPN cụ thể. Trình duyệt/HTTP client gửi ticket tới server trong cơ chế **SPNEGO/HTTP Negotiate**. Server dùng khóa của principal (thường từ **keytab**) để xác minh.

Ví dụ trao đổi HTTP minh họa (chuỗi token là opaque, không thể dùng để xác thực):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate

GET /private HTTP/1.1
Host: app.example.org
Authorization: Negotiate <opaque-spnego-token>
~~~

Trình duyệt cần được phép dùng Integrated Windows Authentication/Negotiate cho host; SPN, DNS, domain trust, KVNO/keytab, cơ chế mã hóa và đồng bộ đồng hồ phải đúng. Cùng một tài khoản domain **không** tự động chứng minh mọi browser sẽ thực hiện SPNEGO với mọi website.

### 7.2. Tích hợp Spring Security Kerberos

Với **Spring Security 7**, Kerberos nằm trong dòng Spring Security, có artifact `spring-security-kerberos-core` và `spring-security-kerberos-web`; dự án phiên bản cũ có thể dùng tọa độ extension khác và phải đối chiếu tài liệu ứng với version thực tế.

Ở servlet web app, `SpnegoAuthenticationProcessingFilter` đọc HTTP `Authorization: Negotiate` và chuyển token tới cấu hình authentication provider/Kerberos service validator. Phần còn lại cần:

- Service principal/SPN đúng FQDN; keytab có key phù hợp và chỉ cấp quyền đọc tối thiểu cho server.
- KDC/realm, DNS, đồng bộ NTP, trust domain và cơ chế mã hóa hỗ trợ.
- Cấu hình HTTP challenge/entry point, filter chain, map principal → tài khoản/quyền.
- Phương án dự phòng cho thiết bị ngoài domain hoặc trình duyệt không hỗ trợ; fallback phải có chính sách rõ ràng.

Ở máy đã đăng nhập domain, `klist` giúp kiểm tra ticket hiện có; dùng trace/công cụ Kerberos phù hợp hệ điều hành để phân biệt lỗi thiếu TGT, sai SPN, sai keytab với lỗi Spring authorization.

**Điểm khác biệt:** Kerberos tối ưu cho network SSO trong realm/trust domain. Đây không phải giao thức đưa identity assertion qua internet như OIDC/SAML. Đăng xuất web app không tự hủy TGT trong hệ điều hành.

## 8. Bốn giao thức cùng tồn tại trong doanh nghiệp

### 8.1. Identity broker và trust boundaries

Ví dụ: máy trạm Windows xác thực Kerberos với AD; một identity broker dùng Windows Integrated Authentication ở upstream rồi phát hành **OIDC ID Token** hoặc **SAML assertion** cho các ứng dụng cloud. Ứng dụng Spring Security chỉ cần tin tưởng **issuer/IdP đã đăng ký**, không xử lý trực tiếp Kerberos ticket của người dùng ngoài browser.

~~~text
Windows user --Kerberos/SPNEGO--> AD/KDC + Identity Broker
                                           |
                           +---------------+-----------------+
                           |                                 |
                      OIDC (OP)                           SAML (IdP)
                           |                                 |
                   Spring web/mobile RP                Spring SAML SP
                           |
                 API Resource Server (access token)
~~~

CAS cũng có thể đứng giữa hệ thống cũ dùng CAS ticket và ứng dụng mới dùng OIDC/SAML. **Broker/translation** là một lần xác thực và phát hành bằng chứng mới dưới chính sách của issuer; không đơn giản đổi đuôi chuỗi ST thành JWT hay tin mọi assertion từ mọi phía.

### 8.2. Chọn giao thức theo bài toán

| Nhu cầu | Ưu tiên đánh giá | Giải thích |
|---|---|---|
| Ứng dụng mới, web/mobile/cloud IdP, gọi API | **OIDC** | Authorization Code + PKCE, discovery, token/claims và OAuth resource-server |
| SSO B2B với đối tác đã dùng SAML, SaaS doanh nghiệp | **SAML 2.0** | Federation qua metadata/chữ ký số; hệ sinh thái doanh nghiệp rộng |
| Ứng dụng cũ/cổng học vụ đang dùng CAS | **CAS protocol** hoặc CAS làm broker | Giữ tương thích ST/validator; có thể hiện đại hóa qua OIDC |
| Intranet Windows, user đã vào domain | **Kerberos + SPNEGO** | Không nhập lại mật khẩu trong môi trường KDC/SPN đúng |
| Cần nhiều loại client/legacy cùng lúc | **Identity broker** | Giảm số mối quan hệ tin cậy và thống nhất MFA/chính sách |

Quyết định còn phụ thuộc client thực tế, yêu cầu MFA, khả năng logout, đội vận hành, audit, vòng đời khóa/chứng thư, danh tính liên tổ chức và năng lực sửa legacy app.

## 9. Ánh xạ danh tính, phân quyền và vòng đời người dùng

Một người có thể xuất hiện dưới các dạng **NameID** (SAML), cặp **issuer + sub** (OIDC), tên CAS và **UPN/principal** (Kerberos). Không nên coi mọi giá trị `email` hay `username` là khóa người dùng toàn cục: email có thể đổi, trùng trong tổ chức hoặc tái cấp.

Thiết kế thực tế:

1. Chọn khóa liên kết danh tính theo **issuer + định danh ổn định** và tenant/realm; lưu mapping sang user nội bộ.
2. Chuẩn hóa attributes/claims/groups từ nguồn **đã xác thực**, hạn chế đặc quyền và xử lý tài khoản bị khóa/không còn thuộc tổ chức.
3. Tách quyết định đăng nhập khỏi quyết định cấp quyền. “Đã login với IdP” không mặc định có `ROLE_ADMIN`.
4. Kiểm soát JIT provisioning, SCIM, vô hiệu hóa tài khoản, session/token revocation và cấp lại quyền; kế hoạch offboarding không dừng ở việc xóa mật khẩu.
5. Phân biệt principal người dùng với credential gọi API. API phải kiểm access token theo issuer, audience, expiry, scope/permission của **chính API đó**.

## 10. Checklist bảo mật và kiểm thử

| Lỗi/tấn công | Điều cần kiểm |
|---|---|
| Tin nhầm IdP hoặc bị giả assertion/token | Pin issuer/metadata/JWKS/chứng thư tin cậy; kiểm chữ ký, thuật toán được phép và rotation |
| Replay hoặc login response không liên quan | SAML `InResponseTo`/conditions/time/replay cache; CAS ST single-use; OIDC `state`/PKCE/nonce khi áp dụng; Kerberos replay protection |
| Token dùng sai nơi | Không dùng OIDC `id_token` để gọi API; resource server kiểm audience/scope; không coi CAS ST là bearer lâu dài |
| Redirect sai/cookie bị lộ | HTTPS, callback/ACS/service URI khớp, trusted reverse proxy, HttpOnly/Secure/SameSite phù hợp, session fixation protection |
| Thiếu quyền dù xác thực thành công | Kiểm mapping group/role, tenant, principal ổn định và trạng thái tài khoản |
| Vấn đề giờ và khóa | Đồng bộ NTP, expiry/not-before, SAML cert/JWKS rotation, Kerberos keytab/KVNO, secret lifecycle |
| Logout không nhất quán | Test local logout, IdP logout, SAML SLO/CAS SLO/OIDC logout tùy hỗ trợ; Kerberos TGT tồn tại độc lập |
| IdP/KDC lỗi hoặc browser không hỗ trợ | Phương án truy cập khẩn cấp, timeout/retry có giới hạn, cảnh báo vận hành, fallback có chính sách |

**Kịch bản kiểm thử tối thiểu** cho một tích hợp:

- Người dùng chưa đăng nhập → được chuyển đúng IdP/OP/CAS hoặc nhận HTTP Negotiate đúng.
- Đăng nhập thành công → chỉ tạo phiên ở ứng dụng có quyền; truy cập tài nguyên yêu cầu đúng authority.
- Đã có phiên SSO → đăng nhập app thứ hai không cần nhập lại credential nếu chính sách cho phép.
- Sai issuer/audience/ACS/service/redirect URI, chữ ký/cert, state, ticket đã dùng/hết hạn → bị từ chối.
- Người dùng không có role hoặc đã bị vô hiệu hóa → không truy cập tài nguyên dù luồng xác thực trước đó từng thành công.
- Logout, timeout, MFA step-up, thay khóa/chứng thư, sai lệch giờ và IdP tạm ngừng → kết quả phù hợp chính sách và có log/metric để chẩn đoán.

## 11. Câu hỏi kiểm tra hiểu bài

1. **SAML assertion khác OIDC ID Token thế nào?** Cùng biểu đạt kết quả xác thực nhưng khác định dạng, bộ vai trò, endpoint, cơ chế xác thực và quy tắc kiểm chứng; ứng dụng không hoán đổi chúng trực tiếp.
2. **Vì sao OAuth 2.0 chưa đồng nghĩa với SSO danh tính?** OAuth 2.0 giải quyết ủy quyền; OIDC định nghĩa xác thực danh tính qua `id_token` và các ràng buộc của OP/RP.
3. **Vì sao CAS ST không lưu dùng lại?** ST ràng buộc service và được thiết kế dùng cho một lần kiểm chứng; tái sử dụng là dấu hiệu replay.
4. **TGT khác service ticket Kerberos thế nào?** TGT dùng xin ticket cho dịch vụ từ TGS; service ticket được trình cho SPN đích thông qua giao thức ứng dụng/SPNEGO.
5. **Nếu công ty có AD và nhiều ứng dụng Spring cloud?** Thường cân nhắc broker/IdP tích hợp AD/Kerberos ở upstream rồi đưa OIDC/SAML tới ứng dụng; thiết kế phân quyền và logout riêng.

## 12. Tài liệu chính thức để tra cứu theo phiên bản

- Spring Security — SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — OAuth 2.0/OIDC Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- Spring Security — CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security — Kerberos: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Apereo CAS — CAS Protocol Specification: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html

Các tên artifact, endpoint tùy chỉnh và DSL có thể thay đổi giữa Spring Security 6, 7 và bản phát hành sau. Khi triển khai thực tế, khóa phiên bản dependency và đối chiếu tài liệu chính xác của phiên bản đó.
