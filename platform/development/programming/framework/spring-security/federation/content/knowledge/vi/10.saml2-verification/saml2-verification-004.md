# Kiểm tra Issuer, Destination và ứng dụng tiếp nhận trong SAML 2.0

> **Module:** Spring Security – federation. **Nhóm kiến thức:** Kiểm chứng SAML2. Bài học này giải thích cách xác định IdP phát hành SAML Response, endpoint nhận Response, ứng dụng có quyền sử dụng Assertion và giao dịch đăng nhập tương ứng. Các ví dụ dùng **Java 17**, Spring Boot **3.5.x** và Spring Security **6.x** trên Servlet stack.

## 1. Sau bài học cần hiểu gì?

Người học có thể phân biệt: **Issuer** là định danh IdP; **Destination** là URL nơi protocol Response được gửi; **Audience** là SP entity ID được phép sử dụng Assertion; **Recipient** là URL nhận bearer SubjectConfirmation; và **InResponseTo** ràng buộc kết quả với AuthnRequest đã tạo. Người học cũng cần:

- Biết những giá trị kỳ vọng đến từ **RelyingPartyRegistration và SAML metadata đáng tin**, không đến từ HTTP parameter tùy ý.
- Hiểu tại sao Response có chữ ký hợp lệ vẫn không được chấp nhận khi Destination, Audience, Recipient hoặc giao dịch không khớp.
- Đọc XML, đối chiếu IdP/SP metadata, cấu hình Spring Security, chạy ví dụ Java 17 và xác minh các lỗi thực tế.
- Thực hiện kiểm thử âm cho IdP mix-up, cross-SP replay, ACS mismatch, mất session và request correlation.
- Phân biệt kiểm chứng giao thức thành công với authorization và tenant policy sau login.

**Kiến thức nền:** HTTP POST/Redirect, session cookie, HTTPS, Spring Security `Authentication` / `SecurityFilterChain`, SAML `AuthnRequest` / `Response` / `Assertion`, chữ ký XML và khái niệm entity ID.

## 2. Mô hình bốn bên và ranh giới tin cậy

SAML Web Browser SSO gồm người dùng, trình duyệt, IdP (Asserting Party) và SP (Relying Party). IdP xác thực người dùng rồi phát SAML Response. Trình duyệt chỉ **chuyển** message đến Assertion Consumer Service (ACS); trình duyệt không phải bên chứng nhận danh tính.

~~~text
User / Browser
    |
    | GET /private
    v
SP (Spring Security)
    |-- xác định RelyingPartyRegistration
    |-- tạo AuthnRequest có ID
    |-- lưu state tương ứng session
    |
    +---------------> IdP đã đăng ký
                          |-- xác thực user / MFA
                          |-- phát/ký Response hoặc Assertion
                          |
Browser <----------------+
    |
    | POST SAMLResponse
    v
SP ACS (Assertion Consumer Service)
    |
    +-- xác minh signing certificate của đúng IdP
    +-- Issuer đúng IdP entity ID
    +-- Destination đúng ACS
    +-- AudienceRestriction đúng SP entity ID
    +-- Recipient đúng ACS
    +-- InResponseTo đúng request đã lưu
    +-- Conditions/thời gian/replay/status hợp lệ
    |
Saml2Authentication + SecurityContext
    |
Authorization theo tenant/user/role ứng dụng
~~~

Sơ đồ gồm nhiều điều kiện độc lập. Một điều kiện vượt qua không chứng minh các điều kiện còn lại. **Login SAML thành công** cũng không mặc nhiên cấp quyền xem dữ liệu nhạy cảm.

## 3. Phân biệt nguồn phát, đích gửi và bên sử dụng

| Yếu tố | Nằm ở đâu | So khớp với | Thí dụ |
| --- | --- | --- | --- |
| **Response Issuer** | `samlp:Response/saml:Issuer` | IdP entity ID trong asserting party registration | `https://idp.example.org/saml` |
| **Assertion Issuer** | `saml:Assertion/saml:Issuer` | IdP entity ID phù hợp profile và trust | `https://idp.example.org/saml` |
| **Destination** | `samlp:Response/@Destination` | SP ACS URI | `https://portal.example.org/login/saml2/sso/corp` |
| **Audience** | `saml:Conditions/saml:AudienceRestriction/saml:Audience` | SP entity ID | `urn:example:portal:sp` |
| **Bearer Recipient** | `saml:SubjectConfirmationData/@Recipient` | SP ACS URI | `https://portal.example.org/login/saml2/sso/corp` |
| **InResponseTo** | `Response/@InResponseTo` và bearer confirmation | ID của `AuthnRequest` được lưu | `_req123` |
| **Thời hạn** | `Conditions`, `SubjectConfirmationData` | Thời gian hiện tại, skew giới hạn | `NotBefore` / `NotOnOrAfter` |

**Issuer không phải ACS:** Issuer nhận diện IdP ký hoặc phát Assertion, không phải nơi Response POST đến. **Destination không phải Audience:** Destination là URL HTTP của ACS; Audience là tên logic của SP (entity ID), có thể là URN. **Recipient và Destination** nhiều khi cùng giá trị ACS nhưng áp trên hai lớp khác nhau: protocol Response và bearer SubjectConfirmation.

### Địa chỉ mẫu có chủ đích khác nhau

~~~text
IdP entity ID: https://idp.example.org/saml
IdP metadata:  https://idp.example.org/metadata
SP entity ID:  urn:example:portal:sp
SP ACS URL:    https://portal.example.org/login/saml2/sso/corp
Spring registrationId: corp
~~~

IdP entity ID và IdP metadata URL không nhất thiết bằng nhau. SP entity ID cũng không phải một endpoint phải tải bằng HTTP. `registrationId` là tên cấu hình của Spring Security, không phải trường `Issuer` hay `Audience` của SAML.

## 4. XML minh họa toàn bộ ràng buộc

Đoạn dưới nhằm **đọc cú pháp**, chưa có chữ ký và chưa phải assertion production hợp lệ; ngày/ID là ví dụ.

~~~xml
<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_resp567"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:00Z"
  InResponseTo="_req123"
  Destination="https://portal.example.org/login/saml2/sso/corp">

  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="_assert789"
      Version="2.0"
      IssueInstant="2030-01-01T10:00:00Z">
    <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
    <saml:Subject>
      <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        opaque-user
      </saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_req123"
          Recipient="https://portal.example.org/login/saml2/sso/corp"
          NotOnOrAfter="2030-01-01T10:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2030-01-01T09:59:00Z"
        NotOnOrAfter="2030-01-01T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>urn:example:portal:sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
      AuthnInstant="2030-01-01T09:59:50Z"
      SessionIndex="_idp-session-42">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>
          urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Phân tích:

1. `Response/Issuer` và `Assertion/Issuer` bằng IdP entity ID dự kiến. Cả hai phải được xử lý theo trust/profile phù hợp, không chỉ đọc một chuỗi.
2. `Response/@Destination` chỉ đúng ACS URL cho response.
3. `AudienceRestriction` chứa SP entity ID; nó **khác** ACS URI.
4. Bearer `Recipient` cũng chỉ ACS; đây là điều kiện trình Assertion ở endpoint đã định.
5. `Response/@InResponseTo` và `SubjectConfirmationData/@InResponseTo` dùng request ID mà SP sinh và lưu.
6. `NotBefore/NotOnOrAfter` cùng bearer expiration kiểm soát hiệu lực.
7. `NameID` chỉ định người dùng theo namespace của IdP; không thay thế issuer, audience hoặc quyền nghiệp vụ.
8. `StatusCode=Success` cần được kiểm tra nhưng không tự chứng minh message đã được ký đúng.

Vì ví dụ **không có `ds:Signature`**, SP thực tế phải từ chối theo yêu cầu ký của SAML profile. Nếu có encrypted assertion, SP phải giải mã bằng private key của chính SP nhưng vẫn phải kiểm chứng chữ ký và mọi điều kiện.

## 5. Kiểm tra Issuer: ai thực sự phát hành?

`Issuer` có namespace SAML Assertion, xuất hiện ở Response hoặc Assertion. Với SAML Web Browser SSO trực tiếp, issuer thường bằng **entity ID của IdP** trong `RelyingPartyRegistration.assertingPartyMetadata`.

Một thiết lập trust hợp lệ bắt đầu từ:

1. Quản trị viên phê duyệt IdP/tenant và nguồn metadata.
2. SP tải hoặc nạp metadata đã được xác thực, ghi nhận IdP entity ID và signing public certificate.
3. Spring Security tạo registration chứa định danh và verification credentials.
4. Khi nhận Response, OpenSAML kiểm chứng chữ ký của phần tử được bảo vệ với **public key tin cậy thuộc IdP**, rồi kiểm tra issuer/registration.
5. Bất kỳ sự khác biệt không được phê duyệt nào phải dẫn tới authentication failure.

**Lưu ý về thứ tự:** Framework có thể đọc Issuer chưa xác thực như một **gợi ý** để tìm registration đã tồn tại. Tuyệt đối không xem việc lookup đó là xác thực, không tự tải metadata mới từ URL Issuer do browser gửi.

### Giả chữ ký và issuer mix-up

Kẻ tấn công có thể tạo RSA key riêng, ký XML hợp lệ và điền `Issuer=https://idp.example.org/saml`. Nếu SP tin ngay certificate nằm trong SAMLResponse, chữ ký sẽ khớp về toán học nhưng nguồn phát không có thẩm quyền. **Chỉ dùng verification key từ registration của IdP đã tin**; không tin public key tự công bố trong message.

Một IdP A có thể ký response hợp lệ nhưng **không được phép cấp danh tính cho tenant B**. Vì vậy ứng dụng còn phải gắn registration với tenant, user population và policy; issuer hợp lệ chỉ là một điều kiện của authentication, không phải authorization.

### Issuer trong Response và Assertion

Response do IdP A phát có thể chứa Assertion khai Issuer B. SP không nên lấy `NameID` từ Assertion đó và giả định nó thuộc A. Với các profile thông thường, Response/Assertion issuer cần tương thích với IdP đã được tin. Việc xác minh chữ ký phải bảo vệ đúng phần tử chứa các claim được dùng để tạo Authentication, ngăn XML Signature Wrapping. Để OpenSAML thực hiện thay vì tự XPath một `Assertion` bất kỳ.

## 6. Kiểm tra Destination: Response gửi tới ACS nào?

`Response/@Destination` là URI đích của protocol message, trong Web Browser SSO HTTP-POST thường chính là **Assertion Consumer Service URL**.

~~~text
SP expected ACS:
https://portal.example.org/login/saml2/sso/corp

Response Destination:
https://portal.example.org/login/saml2/sso/corp
→ Trùng URL; tiếp tục các kiểm tra khác.

Response Destination:
https://payroll.example.org/login/saml2/sso/payroll
→ Sai ứng dụng; Portal không chấp nhận.
~~~

Destination có những điều kiện về presence theo SAML Core/binding/profile; không khẳng định **mọi** SAML message đều bắt buộc khai Destination. Với browser SSO tại ACS, SP phải có chính sách ràng buộc đúng đích; nếu một profile cho phép vắng mặt, phải xem xét cùng chữ ký, Recipient, Audience và correlation, **không tắt kiểm chứng toàn cục**.

**Các mismatch thực tế:**

| Expected ACS | Destination nhận được | Nhận định |
| --- | --- | --- |
| `https://portal.example.org/login/saml2/sso/corp` | Chính xác URL đó | Đúng đích |
| `https://portal.example.org/login/saml2/sso/corp` | `http://portal.example.org/login/saml2/sso/corp` | Sai scheme |
| `https://portal.example.org/login/saml2/sso/corp` | `https://internal:8080/login/saml2/sso/corp` | Sai public host/proxy |
| `https://portal.example.org/login/saml2/sso/corp` | `https://portal.example.org/login/saml2/sso/corp/` | Khác trailing slash |
| `https://portal.example.org/login/saml2/sso/corp` | `https://portal.example.org/login/saml2/sso/other` | Nhầm registration |
| `https://portal.example.org/login/saml2/sso/corp` | `https://portal.example.org/old-acs` | IdP registration cũ |

Không tự thay giá trị Destination trong XML đã ký; như thế phá tính toàn vẹn. Không viết wildcard matcher chỉ so hostname rồi chấp nhận mọi path. Sửa metadata, IdP app registration, proxy và endpoint cho đồng nhất.

### Reverse proxy và X-Forwarded headers

Browser có thể truy cập `https://portal.example.org` nhưng reverse proxy chuyển request vào `http://app:8080`. Nếu SP metadata/ACS được tạo theo host/scheme nội bộ, IdP có thể phát response có Destination không tương thích.

Giải pháp: đặt public ACS rõ ràng, đối chiếu metadata được publish và AuthnRequest `AssertionConsumerServiceURL`, chỉ tin forwarded headers do **proxy đáng tin** cung cấp và xóa header tương ứng từ client ngoài. Không để người dùng tác động `Host`/`X-Forwarded-Host` rồi thay đổi callback, vì có thể gây host-header poisoning hoặc open redirect.

## 7. AudienceRestriction: Assertion dành cho SP nào?

`AudienceRestriction/Audience` trong `Conditions` là **đối tượng có quyền dùng Assertion**. Trong Web Browser SSO, audience thường là **SP entity ID**, ví dụ `urn:example:portal:sp`, thay vì một URL HTTP endpoint.

~~~xml
<saml:Conditions
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  NotBefore="2030-01-01T09:59:00Z"
  NotOnOrAfter="2030-01-01T10:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:portal:sp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Giả sử Portal và Payroll dùng **cùng IdP** và cùng tin public signing certificate của IdP. Một Assertion có signature hợp lệ và Issuer đúng nhưng Audience chỉ bằng `urn:example:payroll:sp` phải bị Portal từ chối. Đây là kiểm soát chống **cross-SP assertion replay/token substitution**.

Nếu một `AudienceRestriction` có nhiều Audience hoặc một Assertion có nhiều restrictions, phải dùng quy tắc chuẩn SAML và validator của thư viện; không chỉ tìm chuỗi entity ID ở bất kỳ vị trí nào trong XML.

**Thay SP entity ID là thay hợp đồng bảo mật:** phải cập nhật IdP app registration, audience, metadata và cân nhắc persistent NameID theo cặp SP nếu ứng dụng đã có identity links. Đừng xem entity ID như label tùy ý có thể đổi mà không migration.

## 8. Recipient: nơi có thể trình bearer SubjectConfirmation

Bearer `SubjectConfirmation` thường chứa `Recipient` trỏ ACS. Nó giới hạn endpoint mà bearer Assertion được phép sử dụng, cùng `NotOnOrAfter` và `InResponseTo`.

~~~xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID>opaque-user</saml:NameID>
  <saml:SubjectConfirmation
    Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
      InResponseTo="_req123"
      Recipient="https://portal.example.org/login/saml2/sso/corp"
      NotOnOrAfter="2030-01-01T10:05:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
~~~

**Destination đúng nhưng Recipient sai vẫn phải bị từ chối** nếu không tồn tại confirmation đáp ứng profile. Ngược lại, Recipient đúng mà Response Destination sai cũng không qua được kiểm chứng Response. Bearer NotOnOrAfter và Conditions NotOnOrAfter là hai điều kiện có thể tồn tại đồng thời, không kiểm một cái thay cái kia.

Một Assertion có thể chứa nhiều `SubjectConfirmation`. SP phải xác nhận có confirmation phù hợp với method, recipient, thời hạn và correlation theo profile, thay vì tùy tiện lấy phần tử đầu tiên hoặc bỏ qua một trường.

## 9. InResponseTo và giao dịch SP-initiated

Khi SP chủ động bắt đầu SSO, nó sinh `AuthnRequest` có ID ngẫu nhiên/duy nhất và lưu state trong `Saml2AuthenticationRequestRepository`, thường gắn HTTP session.

~~~text
SP sinh AuthnRequest ID="_req123"
    |
    +-- lưu request + registration + session context
    |
    +-- Redirect/POST qua browser tới IdP
                                         |
                              IdP xác thực và phát response
                                         |
                         Response InResponseTo="_req123"
                         bearer InResponseTo="_req123"
                                         |
                              browser POST về ACS
                                         |
                       SP tìm request đã lưu và so khớp
                                         |
                  kiểm issuer/destination/audience/recipient...
                                         |
                           mới tạo authenticated session
~~~

`RelayState` có thể hỗ trợ gắn request/response theo binding và implementation nhưng **không phải bằng chứng nhận dạng**. Đừng dùng một RelayState tùy ý để chọn tenant, tài khoản hoặc redirect URL ngoài allowlist.

| Kịch bản | Phản ứng |
| --- | --- |
| SP-initiated: ID đã lưu và InResponseTo khớp | Có thể tiếp tục validation |
| InResponseTo của một request khác | Từ chối |
| Phiên HTTP mất request do timeout | Authentication failure; sửa cookie/session, không bỏ correlation |
| Callback chuyển tới node khác không chia sẻ request repository | Thiết lập shared session/repository phù hợp |
| Response đã dùng bị POST lại | Từ chối theo correlation/replay policy |
| IdP-initiated không có AuthnRequest tương ứng | Chỉ chấp nhận nếu policy cụ thể cho phép unsolicited flow và có các biện pháp bổ sung |

**Login CSRF:** nếu SP nhận Response hợp lệ của attacker vào browser của người khác mà không ràng giao dịch, người dùng có thể vô tình bị đăng nhập vào tài khoản attacker. Correlation và xử lý session giúp bảo vệ trước loại mix-up này. Với IdP-initiated, không có request gốc để kiểm InResponseTo như SP-initiated, nên phải đánh giá rủi ro riêng.

## 10. Spring Security xử lý kiểm chứng thế nào?

Trong Servlet, `Saml2WebSsoAuthenticationFilter` nhận POST ở ACS, `Saml2AuthenticationTokenConverter` trích response và resolve `RelyingPartyRegistration`, tạo `Saml2AuthenticationToken` chưa được xác thực. `AuthenticationManager` chuyển cho OpenSAML-backed AuthenticationProvider để xác minh chữ ký, giải mã và kiểm tra Response/Assertion. Kết quả thành công là `Saml2Authentication`.

~~~text
POST /login/saml2/sso/corp
      |
Saml2WebSsoAuthenticationFilter
      |
Saml2AuthenticationTokenConverter
      |-- response XML + registration + saved request
      |
Saml2AuthenticationToken (untrusted)
      |
AuthenticationManager
      |
OpenSAML AuthenticationProvider
      |-- signature / IdP cert
      |-- Issuer + Destination
      |-- Assertion signature / Issuer
      |-- AudienceRestriction
      |-- bearer Recipient/InResponseTo
      |-- Conditions/time/status/replay
      |
Saml2Authentication (authenticated)
      |
SecurityContext + session
      |
Role/tenant/account policy của ứng dụng
~~~

Spring Security 6.5 có các đường xử lý OpenSAML 4/5 tùy dependencies, còn các tài liệu Spring Security 7 hiện tại thường dùng OpenSAML 5. Trình tự kiểm chứng có thể thay đổi giữa phiên bản, nhưng **không được bỏ điều kiện tin cậy**. Khi tùy biến `ResponseValidator` hoặc `AssertionValidator`, ưu tiên ghép thêm vào validator mặc định. Thay toàn bộ validator chỉ bằng việc so sánh Issuer có thể làm mất các kiểm tra chữ ký, audience, time hoặc recipient cần thiết.

### Chọn RelyingPartyRegistration

`registrationId` như `corp` dùng định tuyến trong ứng dụng. Spring Security có thể chọn registration dựa trên URL callback, AuthnRequest đã lưu hoặc Issuer chưa xác minh làm hint trong tập registrations được quản trị. Chỉ sau validation mới có thể tin message đến từ IdP đã đăng ký. Không tự sinh registration mới từ issuer URL do client cung cấp hoặc nhập public key tự do từ Response.

## 11. Ví dụ Spring Boot 3.5.x và Java 17

Ví dụ là một ứng dụng SP Servlet tối thiểu. Nó biên dịch với Maven, nhưng **cần IdP SAML test thật**, metadata IdP đáng tin và đăng ký SP entity ID/ACS chính xác để hoàn thành login. URL IdP là minh họa.

**pom.xml:**

~~~xml
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
  <artifactId>saml-recipient</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
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
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
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
~~~

**src/main/java/demo/SamlRecipientApplication.java:**

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlRecipientApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlRecipientApplication.class, args);
    }

    @Bean
    RelyingPartyRegistrationRepository registrations() {
        RelyingPartyRegistration corp =
                RelyingPartyRegistrations
                    .fromMetadataLocation("https://idp.example.org/saml/metadata")
                    .registrationId("corp")
                    .entityId("urn:example:portal:sp")
                    .assertionConsumerServiceLocation(
                        "http://localhost:8080/login/saml2/sso/corp")
                    .build();
        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String index() {
            return "Open /me to start SAML authentication";
        }

        @GetMapping("/me")
        Map<String, String> me(
                @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
            return Map.of(
                "registrationId", principal.getRelyingPartyRegistrationId(),
                "authenticated", "true");
        }
    }
}
~~~

**Giải thích:** `fromMetadataLocation(...)` nhận cấu hình IdP đáng tin, có thể gọi metadata khi khởi động. `registrationId` là tên nội bộ. `entityId(...)` đặt **SP entity ID** (Audience dự kiến); `assertionConsumerServiceLocation(...)` đặt **SP ACS URL** (Destination/Recipient). `saml2Login()` để Spring Security/OpenSAML tự xác minh; `/me` chỉ cho request authenticated và không trả raw NameID/Assertion. IdP phải thực sự được đăng ký SP entity ID `urn:example:portal:sp` và ACS `http://localhost:8080/login/saml2/sso/corp`. HTTP localhost chỉ dùng test nếu IdP chấp nhận; production dùng HTTPS public ACS.

Nếu IdP yêu cầu SP ký AuthnRequest hoặc encrypt Assertion, bổ sung signing/decryption credentials của SP và công bố public certificate tương ứng; không đưa private key IdP vào SP.

**Chạy:** sau khi thay metadata URI bằng giá trị thật và đăng ký IdP:

~~~bash
mvn spring-boot:run
~~~

Truy cập `http://localhost:8080/` có response body cố định:

~~~text
Open /me to start SAML authentication
~~~

Truy cập `http://localhost:8080/me` hoặc `/saml2/authenticate/corp` để bắt đầu SSO. Sau callback hợp lệ, `/me` có dạng:

~~~json
{"registrationId":"corp","authenticated":"true"}
~~~

Nếu Issuer/Destination/Audience/Recipient không khớp hoặc state bị mất, login thất bại và không có JSON authenticated đó. Hãy so **SP metadata được sinh ra**, IdP registration và AuthnRequest thay vì tự sửa XML.

## 12. Java 17 độc lập: các expected values độc lập nhau

Chương trình dưới đây có thể chạy với JDK 17. Nó **chỉ mô phỏng việc kiểm tra chuỗi trong bài học sau khi giả định thông điệp đã được xác thực**, không xử lý SAML/XML Signature, nhiều Audience, thời gian, replay hoặc SubjectConfirmation semantics thật. Trong ứng dụng production luôn dùng validator chuẩn của Spring Security/OpenSAML.

**SamlTargetCheck.java:**

~~~java
import java.util.ArrayList;
import java.util.List;

public class SamlTargetCheck {
    record Expected(String issuer, String spEntityId,
                    String acs, String requestId) {}

    record Received(String responseIssuer, String assertionIssuer,
                    String destination, String audience,
                    String recipient, String inResponseTo) {}

    static List<String> errors(Expected e, Received r) {
        List<String> result = new ArrayList<>();
        if (!e.issuer().equals(r.responseIssuer())) {
            result.add("ResponseIssuer");
        }
        if (!e.issuer().equals(r.assertionIssuer())) {
            result.add("AssertionIssuer");
        }
        if (!e.acs().equals(r.destination())) {
            result.add("Destination");
        }
        if (!e.spEntityId().equals(r.audience())) {
            result.add("Audience");
        }
        if (!e.acs().equals(r.recipient())) {
            result.add("Recipient");
        }
        if (!e.requestId().equals(r.inResponseTo())) {
            result.add("InResponseTo");
        }
        return result;
    }

    static void show(String name, Expected e, Received r) {
        List<String> failures = errors(e, r);
        System.out.println(name + ": " +
                (failures.isEmpty() ? "PASS" : "FAIL " + failures));
    }

    public static void main(String[] args) {
        Expected e = new Expected(
                "https://idp.example.org/saml",
                "urn:example:portal:sp",
                "https://portal.example.org/login/saml2/sso/corp",
                "_req123");

        Received valid = new Received(
                e.issuer(), e.issuer(), e.acs(),
                e.spEntityId(), e.acs(), e.requestId());

        show("valid", e, valid);
        show("issuer", e, new Received(
                "https://other.example/saml", valid.assertionIssuer(),
                valid.destination(), valid.audience(),
                valid.recipient(), valid.inResponseTo()));
        show("destination", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                "https://other.example/acs", valid.audience(),
                valid.recipient(), valid.inResponseTo()));
        show("audience", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                valid.destination(), "urn:example:payroll:sp",
                valid.recipient(), valid.inResponseTo()));
        show("recipient", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                valid.destination(), valid.audience(),
                "https://other.example/acs", valid.inResponseTo()));
        show("request", e, new Received(
                valid.responseIssuer(), valid.assertionIssuer(),
                valid.destination(), valid.audience(),
                valid.recipient(), "_another-request"));
    }
}
~~~

Chạy:

~~~bash
javac SamlTargetCheck.java
java SamlTargetCheck
~~~

**Stdout chính xác:**

~~~text
valid: PASS
issuer: FAIL [ResponseIssuer]
destination: FAIL [Destination]
audience: FAIL [Audience]
recipient: FAIL [Recipient]
request: FAIL [InResponseTo]
~~~

Chương trình cho thấy Issuer, Destination, Audience, Recipient và InResponseTo phải được so với **năm giá trị có nguồn gốc tin cậy riêng**. Nó không chứng minh tính hợp lệ mật mã. `String.equals` ở đây chỉ là phương tiện minh họa; validation SAML đầy đủ có quy tắc với nhiều AudienceRestriction/SubjectConfirmation, encoding, binding, time và signature.

## 13. Ma trận negative tests và sai sót thường gặp

| Test | Kỳ vọng |
| --- | --- |
| IdP signing cert tin cậy, Issuer/ACS/Audience/Recipient/Request khớp, message còn hiệu lực | Tiếp tục tạo Authentication |
| Response Issuer sai IdP | Từ chối |
| Assertion Issuer không phù hợp | Từ chối |
| Chữ ký giả bằng certificate do attacker tự công bố | Từ chối |
| Response ký hợp lệ nhưng Destination sang SP B | SP A từ chối |
| Response Destination đúng nhưng bearer Recipient là SP B | SP A từ chối |
| Assertion ký hợp lệ, Audience là entity ID SP B | SP A từ chối |
| Destination dùng HTTP dù ACS chính thức là HTTPS | Từ chối hoặc lỗi được phát hiện theo policy |
| Destination dùng internal host sau proxy | Từ chối; sửa public ACS |
| InResponseTo sai request đang chờ | Từ chối trong SP-initiated flow |
| Callback mất session/request repository | Lỗi correlation; không tự bỏ check |
| IdP-initiated dù SP chỉ cho SP-initiated | Từ chối theo policy |
| Assertion đã hết hạn/chưa NotBefore | Từ chối |
| Gửi lại Response/Assertion đã sử dụng | Từ chối theo replay/correlation policy |
| Decrypt thành công nhưng signature hoặc audience sai | Vẫn từ chối |
| NameID đúng nhưng user bị disabled | Không cấp quyền ứng dụng |
| SAML Authentication thành công nhưng thiếu quyền nghiệp vụ | 403 đối với tài nguyên được bảo vệ |

**Lưu ý khi tạo test:** Nếu sửa Audience/Destination bằng tay *sau khi ký*, chữ ký sẽ fail; test đó không chứng minh validator Audience hay Destination đang hoạt động. Muốn kiểm tra chính xác, dùng IdP test phát **message ký hợp lệ cho SP B**, rồi trình tại SP A trong môi trường cách ly. Không gửi các thử nghiệm đó vào hệ thống production.

### Tra cứu lỗi theo nguyên nhân

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| `invalid_issuer` | IdP entity ID và registration/tenant |
| `invalid_destination` | Public ACS scheme, host, path, port; proxy config |
| `audience_mismatch` | SP entity ID và IdP app registration |
| `invalid_recipient` | Bearer SubjectConfirmationData và ACS |
| `InResponseTo` không khớp | AuthnRequest ID, session cookie, repository, load balancer |
| `invalid_signature` | IdP signing cert/metadata, key rotation và signed element |
| Lỗi chỉ một node | Metadata/cert, session store, clocks giữa các instance |
| Login loop | Cookie Secure/SameSite, ACS redirect, failure handler |
| 403 sau login | Tenant, user status, role/authority mapping |

**Không khắc phục bằng cách** bỏ issuer/signature checks, viết matcher wildcard cho ACS, tắt audience hoặc cho phép bất kỳ Response không có state. Khôi phục đúng IdP/SP metadata, proxy, session và quy tắc đăng nhập.

## 14. Checklist triển khai và bài tập

**Checklist khi kết nối một IdP mới:**

- [ ] Xác minh IdP entity ID, metadata source và signing certificates qua kênh được phê duyệt.
- [ ] Cố định SP entity ID và public ACS URL trong SP metadata/IdP registration.
- [ ] Kiểm tra Response/Assertion Issuer, Destination, Audience, bearer Recipient và InResponseTo.
- [ ] Duy trì chữ ký, thời gian, SubjectConfirmation, Status, replay và correlation validation.
- [ ] Thử multi-IdP, wrong-tenant và cross-SP assertion acceptance.
- [ ] Kiểm tra reverse proxy/HTTPS, trusted forwarded headers và distributed session khi chạy cluster.
- [ ] Không đưa raw SAMLResponse, NameID, attributes hoặc session cookie vào log không được bảo vệ.

**Bài tập 1 – đọc XML:** Ghi ra IdP entity ID, SP entity ID, ACS và AuthnRequest ID từ mẫu mục 4. Nêu lý do `Audience` không phải `Destination`.

**Bài tập 2 – hai ứng dụng cùng IdP:** IdP A ký một Assertion cho Payroll, rồi Response được POST tới Portal. Hãy nêu các checks có thể từ chối mà không cần làm sai chữ ký.

**Bài tập 3 – Java 17:** Chạy `SamlTargetCheck.java`. Đổi `assertionIssuer` để thấy `FAIL [AssertionIssuer]`. Giải thích vì sao code demo không thay OpenSAML.

**Bài tập 4 – Spring Security:** Đăng ký SP từ ví dụ với IdP test. Quan sát SP metadata và chạy login thành công, rồi thay ACS trong IdP registration để tái hiện Destination/Recipient mismatch.

**Bài tập 5 – reverse proxy:** Backend thấy `http://app:8080` còn public URL là `https://portal.example.org`. Xác định và sửa sai khác; không tin `X-Forwarded-Host` do người dùng tự gửi.

**Bài tập 6 – correlation:** Cho callback đến node không có session/request đã lưu. Nêu lý do InResponseTo fail và phương án dùng distributed repository hoặc session affinity phù hợp.

**Đạt bài khi** giải thích được cặp ánh xạ: **IdP entity ID ↔ Issuer**, **SP entity ID ↔ Audience**, **ACS ↔ Destination/Recipient**, **AuthnRequest ID ↔ InResponseTo**, và chứng minh chữ ký đúng vẫn không cho phép dùng Assertion ở SP sai đối tượng.

## 15. Nguồn chuẩn để đối chiếu

- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 – OpenSAML Support: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SP Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – SAML2 Relying Party: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core – Issuer/Conditions/SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Metadata – EntityDescriptor/ACS: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
