# Đối chiếu InResponseTo với yêu cầu đăng nhập đã lưu trong SAML 2.0

**Module:** Spring Security – federation  
**Ngữ cảnh:** Kiểm chứng SAML2  
**Phạm vi:** SAML 2.0 Web Browser SSO Profile, Spring Boot 3.x, Spring Security 6.x và Java 17+.

## 1. Mục tiêu của bài học

Trong SAML 2.0 **SP-initiated Single Sign-On**, Service Provider (SP) khởi động đăng nhập bằng một **AuthnRequest** gửi tới Identity Provider (IdP). Khi IdP hoàn tất xác thực, browser gửi **SAMLResponse** về Assertion Consumer Service (ACS) của SP. Chỉ xác minh chữ ký SAMLResponse là **chưa đủ**: SP còn phải đối chiếu phản hồi với **yêu cầu đăng nhập do đúng phiên trình duyệt của SP đã khởi tạo**.

Khóa nối quan trọng là **InResponseTo**. Nó tham chiếu tới **ID của AuthnRequest gốc**. Việc so khớp này cùng với việc lưu yêu cầu trong một repository phù hợp giúp:

- Ngăn ứng dụng nhận nhầm phản hồi dành cho một yêu cầu khác hoặc một phiên khác.
- Giảm rủi ro **login CSRF/session swapping**: kẻ tấn công cố đưa một phản hồi hợp lệ của họ vào trình duyệt nạn nhân để thay danh tính đăng nhập.
- Phát hiện response không có yêu cầu gốc, yêu cầu đã được dùng hoặc hết hiệu lực.
- Gắn việc xử lý response với đúng **RelyingPartyRegistration**, IdP, SP entityID và ACS.
- Không tạo **Authentication/SecurityContext** cho một SAML Response chưa chứng minh được mối quan hệ với phiên đăng nhập đang xử lý.

**InResponseTo là điều kiện liên kết giao dịch, không phải chữ ký số.** Một giá trị InResponseTo đúng nhưng chữ ký/Issuer/Audience/Recipient sai vẫn phải bị từ chối. Ngược lại, response có chữ ký hợp lệ nhưng InResponseTo trỏ tới request không tồn tại hoặc thuộc phiên khác cũng không thể được chấp nhận trong luồng SP-initiated yêu cầu correlation.

## 2. Ba ID rất dễ bị nhầm

SAML 2.0 có ít nhất ba định danh nên phân biệt:

| Trường | Ví dụ | Ai tạo? | Vai trò |
| --- | --- | --- | --- |
| **AuthnRequest.ID** | **_REQ_7f3** | SP | Định danh duy nhất của yêu cầu xác thực đi tới IdP |
| **Response.ID** | **_RESP_9a1** | IdP | Định danh của thông điệp Response, khác với request ID |
| **Response.InResponseTo** | **_REQ_7f3** | IdP | Trỏ ngược tới **AuthnRequest.ID** đã được SP phát |

Thêm một trường đặc biệt trong assertion:

**SubjectConfirmationData.InResponseTo** (đối với xác nhận chủ thể kiểu bearer) thường cũng cần trùng **AuthnRequest.ID** của yêu cầu gốc theo SAML Web Browser SSO Profile.

Vì vậy với ví dụ trên:

~~~text
AuthnRequest.ID                       = _REQ_7f3
SAMLResponse.ID                       = _RESP_9a1
SAMLResponse.InResponseTo             = _REQ_7f3
Assertion/SubjectConfirmationData
                      .InResponseTo   = _REQ_7f3
~~~

**Không so sánh Response.ID với AuthnRequest.ID.** Hai thông điệp được sinh ở hai bên khác nhau và nên có ID khác nhau. Giá trị phải trùng với request ID là các thuộc tính **InResponseTo** tương ứng.

**RelayState không phải InResponseTo.** RelayState là dữ liệu của HTTP binding để giữ trạng thái tương quan/điều hướng qua IdP, thường là một giá trị opaque. Nó có thể giúp tìm request đã lưu, nhưng không thay thế việc xác minh XML Response/Assertion hoặc gắn phản hồi với browser khởi tạo yêu cầu.

## 3. Luồng SP-initiated SSO: lưu và đối chiếu

~~~text
Trình duyệt A                      SP (Spring Security)                 IdP
      |                                   |                             |
      | GET /private                      |                             |
      |---------------------------------->| cần login                  |
      |<----------------------------------| redirect                    |
      | GET /saml2/authenticate/company   |                             |
      |---------------------------------->| tạo AuthnRequest           |
      |                                   | ID = _REQ_7f3              |
      |                                   | lưu trong HttpSession A    |
      |                                   | lưu registrationId/RelayState
      |<----------------------------------| redirect SAMLRequest ------>|
      |                                   |                             | xác thực
      | POST /login/saml2/sso/company     |<----------------------------|
      | SAMLResponse:                     |                             |
      | InResponseTo = _REQ_7f3           |                             |
      |---------------------------------->| lấy request đã lưu         |
      |                                   | đối chiếu đúng session A   |
      |                                   | Response.InResponseTo      |
      |                                   | SubjectConfirmationData   |
      |                                   | chữ ký/Issuer/Audience/... |
      |                                   | consume request 1 lần      |
      |<----------------------------------| tạo phiên nếu hợp lệ       |
~~~

### Bước 1 – SP phát AuthnRequest

Khi người dùng chưa xác thực truy cập tài nguyên được bảo vệ:

1. Spring Security chuyển browser tới **/saml2/authenticate/{registrationId}**, ví dụ **/saml2/authenticate/company**.
2. **Saml2WebSsoAuthenticationRequestFilter** và request resolver/factory tạo AuthnRequest.
3. AuthnRequest có **ID duy nhất và khó đoán**, Issuer SP, Destination/endpoint IdP, ACS thông tin phù hợp, IssueInstant và các thuộc tính cần thiết.
4. SP lưu đối tượng yêu cầu tương quan trước khi đưa SAMLRequest tới browser/IdP.
5. Browser nhận redirect hoặc POST theo SAML binding và tới đúng IdP.

Điểm mấu chốt là **SP phải giữ bằng chứng rằng phiên browser của chính mình đã tạo ra AuthnRequest với ID cụ thể**, chứ không chỉ tin bất kỳ chuỗi request ID do callback mang về.

### Bước 2 – IdP gửi SAMLResponse

Sau khi xác thực người dùng, IdP tạo Response có **InResponseTo** tham chiếu AuthnRequest.ID. Assertion chứa bearer SubjectConfirmationData, với **InResponseTo**, Recipient, NotOnOrAfter và các điều kiện tương ứng. Browser thường **POST** SAMLResponse tới ACS:

~~~http
POST /login/saml2/sso/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...
 
SAMLResponse=BASE64_SAML_RESPONSE&RelayState=OPAQUE_VALUE
~~~

Đây là **mô tả request**; các giá trị đều là placeholder, không phải SAMLResponse thật. Không đưa response/token thực vào tài liệu, log, URL tracking hoặc công cụ quan sát công khai.

### Bước 3 – SP lấy request gốc

Spring Security sử dụng **Saml2AuthenticationRequestRepository** để tìm AuthnRequest đã phát. Cấu hình mặc định là **HttpSessionSaml2AuthenticationRequestRepository**, lưu request trong **HttpSession** của browser.

Nếu browser không mang đúng cookie session, HttpSession bị hết hạn, hoặc load balancer chuyển callback sang node không nhìn thấy session, request gốc có thể không tìm được. Khi đó, hệ thống không nên “chữa” bằng cách lấy bất kỳ request có cùng ID toàn hệ thống mà bỏ kiểm tra liên kết với browser.

### Bước 4 – Xác minh correlation và SAML

Tùy phiên bản Spring Security và OpenSAML, converter/provider/validators phối hợp:

- Tìm **RelyingPartyRegistration** tương ứng.
- Lấy AuthnRequest từ repository theo chính sách đã cấu hình.
- Kiểm tra **Response.InResponseTo** so với AuthnRequest.ID khi flow yêu cầu.
- Kiểm tra **SubjectConfirmationData.InResponseTo** của bearer confirmation theo quy tắc SAML Profile.
- Kiểm tra signature, Issuer, Destination, AudienceRestriction, Recipient, conditions/time, subject confirmation và các yêu cầu khác.
- Chỉ khi tất cả điều kiện đạt mới tạo **Saml2Authentication** và **SecurityContext**.

**Không coi việc tìm thấy request cùng ID là đủ.** Trường InResponseTo trong XML vẫn phải nằm trong dữ liệu đã được xác minh đầy đủ, và các điều kiện khác phải thỏa mãn.

### Bước 5 – Hoàn tất và không tái sử dụng

Request đã hoàn tất cần được **consume/xóa**, hoặc đánh dấu đã sử dụng theo chính sách, sao cho một response replay không tạo thêm một giao dịch đăng nhập mới. Với repository phân tán, thao tác consume phải an toàn trước xử lý đồng thời. Các triển khai SAML đầy đủ còn cần chính sách phát hiện replay ở cấp **Response/Assertion ID**, không chỉ request ID.

Không tự ghi Authentication vào SecurityContext khi correlation thất bại; ghi trạng thái thất bại đủ để chẩn đoán nhưng không để lộ SAMLResponse, session cookie hoặc identifier nhạy cảm.

## 4. Ví dụ XML: các thuộc tính cần đối chiếu

Đây là **mảnh XML minh họa** đã bỏ chữ ký và nhiều trường bắt buộc; **không sử dụng làm assertion hợp lệ**.

### 4.1. AuthnRequest do SP tạo

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_REQ_7f3"
    Version="2.0"
    IssueInstant="2026-11-07T08:00:00Z"
    Destination="https://idp.example.org/sso"
    AssertionConsumerServiceURL=
        "https://portal.example.org/login/saml2/sso/company">
    <saml:Issuer>https://portal.example.org/saml/sp/company</saml:Issuer>
</samlp:AuthnRequest>
~~~

Ý nghĩa: **ID="_REQ_7f3"** chính là định danh SP sẽ lưu; Issuer là entityID của SP, Destination là endpoint IdP, ACS URL là nơi SP nhận phản hồi.

### 4.2. Response do IdP tạo

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_RESP_9a1"
    Version="2.0"
    IssueInstant="2026-11-07T08:01:00Z"
    Destination="https://portal.example.org/login/saml2/sso/company"
    InResponseTo="_REQ_7f3">
    <saml:Issuer>https://idp.example.org/saml/company</saml:Issuer>
    <saml:Assertion ID="_ASSERT_22b">
        <saml:Subject>
            <saml:SubjectConfirmation
                Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData
                    InResponseTo="_REQ_7f3"
                    Recipient="https://portal.example.org/login/saml2/sso/company"
                    NotOnOrAfter="2026-11-07T08:05:00Z"/>
            </saml:SubjectConfirmation>
        </saml:Subject>
    </saml:Assertion>
</samlp:Response>
~~~

**Các điểm cần nhận diện:**

- Response.ID **_RESP_9a1** khác AuthnRequest.ID **_REQ_7f3**.
- Response.InResponseTo và SubjectConfirmationData.InResponseTo cùng tham chiếu **_REQ_7f3**.
- **Destination/Recipient** hướng tới đúng ACS của SP.
- **Issuer** là IdP đã được SP phê duyệt, không phải tên miền do browser tự đưa vào.
- **NotOnOrAfter** là ràng buộc thời gian của bearer confirmation, độc lập với thời gian sống session SP.
- Ví dụ lược bỏ chữ ký và Conditions/AudienceRestriction/NameID; một hệ thống thật phải kiểm tra đầy đủ theo profile, không chấp nhận XML mẫu này.

## 5. InResponseTo khác RelayState, Session và Request ID như thế nào?

| Thông tin | Nó chứng minh điều gì? | Có đủ để xác thực user? |
| --- | --- | --- |
| **Response.InResponseTo** | Response tuyên bố trả lời một AuthnRequest.ID | **Không**: còn kiểm tra request đã lưu, session và SAML validation |
| **SubjectConfirmationData.InResponseTo** | Bearer assertion ràng buộc tới AuthnRequest | **Không**: còn chữ ký, SubjectConfirmation, time, Recipient... |
| **RelayState** | State của HTTP binding, thường dùng correlation/điều hướng | **Không**: không mặc nhiên là bằng chứng xác thực hay session |
| **HttpSession ID** | Browser đang trình diện một định danh phiên SP | **Không**: session có thể tồn tại khi anonymous |
| **AuthnRequest.ID** | SP đánh dấu một yêu cầu đăng nhập cụ thể | **Không**: chỉ là khóa đối chiếu |
| **Response.ID / Assertion.ID** | Định danh duy nhất của response/assertion | **Không**: còn kiểm tra tính toàn vẹn/đích nhận, và chống replay |
| **Authentication/SecurityContext** | Kết quả Spring Security chấp nhận sau kiểm chứng | Là cơ sở cho authentication, nhưng vẫn cần authorization |

**RelayState không phải anti-CSRF token mặc định theo nghĩa có thể bỏ kiểm tra khác.** Nếu làm repository chỉ dựa RelayState/Response.InResponseTo để tìm request toàn cục, phải có cơ chế độc lập liên kết giao dịch với đúng browser và chống replay. Nếu RelayState dùng làm URL điều hướng, phải allowlist đường dẫn nội bộ hoặc validate nghiêm ngặt để tránh open redirect.

**Cùng một session không có nghĩa các tab không thể đụng nhau.** Khi người dùng mở nhiều cửa sổ login song song, cần biết request repository cụ thể lưu một request hay nhiều request đang chờ, cách lookup theo RelayState/ID và hành vi overwrite/consume của phiên bản đang dùng. Không tự suy đoán rằng HttpSession tự bảo đảm mọi luồng song song đều được xử lý đúng.

## 6. Spring Security: request repository mặc định làm gì?

Spring Security cung cấp các thành phần:

1. **Saml2WebSsoAuthenticationRequestFilter** tạo và lưu **AbstractSaml2AuthenticationRequest** trước khi gửi SAMLRequest.
2. **Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>** là interface chịu trách nhiệm lưu/tải/loại bỏ request.
3. **HttpSessionSaml2AuthenticationRequestRepository** là triển khai mặc định, gắn request với HttpSession của browser.
4. **Saml2WebSsoAuthenticationFilter** cùng **Saml2AuthenticationTokenConverter** dùng repository để lấy request gốc khi nhận Response.
5. **OpenSAML AuthenticationProvider** xử lý XML/cryptographic validation và tạo Authentication nếu hợp lệ.

Các API chính của repository:

~~~java
void saveAuthenticationRequest(
    T authenticationRequest,
    HttpServletRequest request,
    HttpServletResponse response);

T loadAuthenticationRequest(HttpServletRequest request);

T removeAuthenticationRequest(
    HttpServletRequest request,
    HttpServletResponse response);
~~~

Đây là **chữ ký diễn giải** của các phương thức interface; trong mã thật, kiểu T là một subclass của **AbstractSaml2AuthenticationRequest**, các phương thức đọc/xóa có thể trả null khi không tìm thấy. Chú ý **removeAuthenticationRequest** có ý nghĩa xóa request khỏi repository, không phải xóa session đăng nhập SP.

Từ đối tượng yêu cầu đã lưu, có thể lấy:

- **getId()**: ID AuthnRequest (dùng đối chiếu InResponseTo).
- **getRelayState()**: RelayState nếu có.
- **getRelyingPartyRegistrationId()**: ID đăng ký liên kết SP–IdP.
- **getSamlRequest()**: thông điệp AuthnRequest đã mã hóa để gửi qua binding.
- **getAuthenticationRequestUri()** và **getBinding()**: URL đích và binding gửi request.

Các getter này phục vụ phân tích **request đã phát ra**, không chứng minh response là hợp lệ nếu chưa qua provider xác minh.

### Vì sao lưu ở HttpSession hữu ích?

Nếu attacker tạo một SAMLResponse hợp lệ cho **phiên của attacker**, đưa nó cho browser của nạn nhân, SP của nạn nhân không có AuthnRequest tương ứng trong **HttpSession của nạn nhân**, nên luồng SP-initiated có thể từ chối. Đây là lợi thế chống login substitution so với repository toàn cục tìm request chỉ bằng InResponseTo.

Tuy nhiên browser có thể không gửi cookie khi IdP POST cross-site; đây là vấn đề vận hành cần giải quyết, **không phải lý do mặc định tắt correlation**.

## 7. Ví dụ Spring Boot 3 / Spring Security 6: giữ cơ chế mặc định

Đây là **mã cho dự án Servlet/MVC Spring Boot 3.x, Java 17+**. Mẫu sử dụng **RelyingPartyRegistrations.fromMetadataLocation** và **saml2Login()**. Để chạy SSO thực tế, cần metadata IdP đã kiểm duyệt, IdP thực, SP đã đăng ký với entityID/ACS phù hợp, chứng thư/khóa SP nếu IdP yêu cầu và HTTPS công khai phù hợp.

Không cần viết controller riêng để đọc SAMLResponse, và không cần tự viết AuthenticationProvider chỉ để kiểm tra InResponseTo.

### 7.1. Dependencies trong pom.xml

Trong Maven project có Spring Boot parent/BOM tương thích, thêm:

~~~xml
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
~~~

Không ép phiên bản OpenSAML không tương thích với Spring Security đang dùng. Cấu hình sau dùng các class public API của Spring Security 6.x.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    metadata-location: classpath:metadata/company-idp.xml
server:
  servlet:
    session:
      timeout: 20m
~~~

Đặt metadata IdP thật (bao gồm certificate/endpoint có hiệu lực) tại **src/main/resources/metadata/company-idp.xml**. Giá trị **20m** là idle timeout của HttpSession SP, không phải hạn của SAML assertion. Nếu muốn chạy thử localhost, phải đăng ký ACS/entityID localhost hoặc dùng HTTPS test domain và cấu hình IdP tương ứng.

### 7.3. SamlCorrelationApplication.java

**src/main/java/com/example/saml/SamlCorrelationApplication.java**

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlCorrelationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlCorrelationApplication.class, args);
    }
}
~~~

### 7.4. SamlSecurityConfig.java

**src/main/java/com/example/saml/SamlSecurityConfig.java**

~~~java
package com.example.saml;

import org.springframework.beans.factory.annotation.Value;
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
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.metadata-location}") String location) {

        RelyingPartyRegistration registration =
            RelyingPartyRegistrations
                .fromMetadataLocation(location)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Giải thích quan trọng:**

- **saml2Login()** cấu hình hai đầu: tạo AuthnRequest và nhận Response/Assertion, sử dụng **Saml2AuthenticationRequestRepository**.
- Spring Security mặc định có **HttpSessionSaml2AuthenticationRequestRepository**, nên AuthnRequest được lưu trong session browser trước khi redirect đến IdP.
- SP không tự công khai endpoint chấp nhận assertion theo arbitrary URL; **ACS** phải được cấu hình và đăng ký chính xác ở IdP.
- **registrationId=company** liên kết yêu cầu với IdP company đã được tin; **entityId** là định danh giao thức SP.
- Không tắt CSRF toàn bộ ứng dụng, không đặt **SessionCreationPolicy.STATELESS** cho browser SAML2 chain trừ khi có thiết kế thay thế tương đương về lưu request/phiên.
- Mẫu này **không mặc nhiên chạy được với domain example.org**; IdP phải thực sự cung cấp metadata, ký response và chấp nhận SP registration.

### 7.5. Controller chỉ đọc danh tính đã xác minh

**src/main/java/com/example/saml/SamlController.java**

~~~java
package com.example.saml;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlController {

    @GetMapping("/")
    public String home() {
        return "SAML correlation demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of(
            "name", principal.getName(),
            "registrationId", principal.getRelyingPartyRegistrationId());
    }
}
~~~

**Không nên dump SAMLResponse trong controller** hoặc lấy NameID trực tiếp từ HTTP body để “bỏ qua lỗi InResponseTo”. Principal được Spring cung cấp sau khi cơ chế xác thực chấp nhận response. Trong production, giảm thiểu dữ liệu định danh đưa ra HTTP response.

### 7.6. Chạy và kết quả mong đợi

Trong project Maven Spring Boot hợp lệ với JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Nếu metadata có thể nạp và ứng dụng khởi động, request public:

~~~bash
curl -i http://localhost:8080/
~~~

Body đúng theo controller:

~~~text
SAML correlation demo
~~~

Đối với request login thật:

~~~text
GET /saml2/authenticate/company
  -> AuthnRequest được tạo/lưu trong session
  -> browser chuyển tới IdP
  -> IdP xác thực và gửi SAMLResponse
  -> POST /login/saml2/sso/company
  -> repository cung cấp request gốc cho flow xác minh
  -> Authentication được tạo khi response thỏa mọi điều kiện
~~~

Đây là **trình tự giải thích**, không phải stdout có thể cố định khi chưa có IdP thật. Nếu ACS công khai đang là **https://portal.example.org/**, không thể mong IdP callback về **http://localhost:8080/** mà không thay đổi cấu hình đã đăng ký của cả hai phía.

## 8. Khi muốn tường minh request repository

Đối với ứng dụng có cấu hình phức tạp, bạn có thể khai báo bean repository như sau (thêm vào lớp **@Configuration** của project SAML2):

~~~java
@Bean
Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>
authenticationRequestRepository() {
    return new HttpSessionSaml2AuthenticationRequestRepository();
}
~~~

Các import liên quan:

~~~java
import org.springframework.security.saml2.provider.service.authentication.AbstractSaml2AuthenticationRequest;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.HttpSessionSaml2AuthenticationRequestRepository;
~~~

**Lưu ý:** Đây là **cấu hình tường minh tương đương mặc định**, không phải yêu cầu bắt buộc và không cần copy lại nếu repository mặc định đã đáp ứng. Nếu dùng custom repository, bảo đảm cùng repository được dùng lúc gửi AuthnRequest và lúc nhận SAMLResponse, đồng thời cấu hình đúng theo API của phiên bản Spring Security đang chạy.

### Dùng Spring Session khi có nhiều node

Nếu callback tới node khác so với node tạo AuthnRequest, **HttpSession memory** chỉ ở node đầu sẽ không còn đủ. Spring Session có thể lưu HttpSession trong Redis/DB chung để request repository truy cập cùng dữ liệu ở mọi instance.

Dependency ví dụ trong project Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Ứng dụng cần cấu hình Redis đáng tin, TLS/ACL, session timeout, cookie domain/path và serialization tương thích. Spring Session thay lớp HttpSession ở Servlet, nên **HttpSessionSaml2AuthenticationRequestRepository** vẫn làm việc với session logic đó. Không đẩy raw SAMLResponse vào Redis dưới tên key do client định nghĩa.

Nếu doanh nghiệp cần nhiều request đang chờ cùng lúc, kiểm tra giới hạn implementation/repository và xây chiến lược đồng thời đúng, có TTL và consume atomic; không suy đoán repository mặc định đã hỗ trợ tất cả trường hợp đa tab.

## 9. CacheSaml2AuthenticationRequestRepository và rủi ro RelayState

Spring Security còn có **CacheSaml2AuthenticationRequestRepository** để lưu AuthnRequest trong cache, hữu ích khi muốn tránh phụ thuộc hoàn toàn vào HTTP session trong một số cấu hình cookie/SameSite. Tuy nhiên có cảnh báo bảo mật rất quan trọng:

**Nếu request chỉ được tra cứu toàn cục bằng RelayState hoặc InResponseTo, ta biết response trỏ tới request nào nhưng chưa biết request đó do đúng browser hiện tại khởi tạo.**

Ví dụ tấn công login substitution:

1. Attacker khởi tạo SSO ở browser của họ, tạo request ID **_REQ_ATTACKER**.
2. IdP cấp một SAMLResponse hợp lệ cho tài khoản attacker, chứa InResponseTo **_REQ_ATTACKER**.
3. Attacker cố khiến browser nạn nhân POST response đó đến SP.
4. Nếu SP chỉ tra request toàn cục bằng InResponseTo mà **không ràng buộc browser/session**, có thể chấp nhận response và tạo phiên nạn nhân đăng nhập dưới tài khoản attacker.

Đây là một dạng **login CSRF**, có thể làm nạn nhân thao tác trên tài khoản do attacker kiểm soát, lộ dữ liệu được nhập vào tài khoản đó hoặc gây nhầm lẫn authorization.

**Thiết kế giảm rủi ro** khi dùng distributed cache:

- Dùng **RelayState ngẫu nhiên, khó đoán, có TTL ngắn**, sinh bởi SP chứ không tin giá trị client cung cấp.
- Lưu ánh xạ **RelayState → pending request** có bảo vệ truy cập, giới hạn thời hạn và consume một lần.
- Ràng buộc pending request với một bí mật/marker được **browser khởi tạo** giữ riêng (cookie/session/context đã bảo vệ); kiểm tra đúng ràng buộc đó khi nhận Response.
- Không ghi nhận một **InResponseTo đúng** là đủ: vẫn cần đúng browser, registration, IdP, signature, audience, recipient và time.
- Đặt **single-use atomic consume** và cơ chế chặn replay Response/Assertion ID.
- Nếu sử dụng SameSite cookie khác vì HTTP-POST callback, cần kiểm thử browser/ACS thực, không “xóa kiểm tra InResponseTo” để sửa cookie.

**Không tạo custom repository chỉ vì thấy callback POST mất session.** Trước tiên kiểm tra thuộc tính cookie, HTTPS, SameSite, reverse proxy và session store. Cơ chế cache cần thiết kế/thử nghiệm nghiêm ngặt để giữ được ràng buộc đăng nhập.

## 10. Java 17 runnable: mô phỏng đối chiếu request ID và session

Ví dụ sau chỉ mô phỏng **correlation table** và việc consume một lần. Đây **không phải SAML validator**, không parse XML, không kiểm tra chữ ký, không tạo Authentication. Các giá trị ID cố định chỉ dùng làm test, không đại diện cách phát sinh request ID an toàn trong production.

**Tệp CorrelationExample.java:**

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class CorrelationExample {

    record Pending(String requestId, String browserSession) { }

    private final Map<String, Pending> requests =
        new ConcurrentHashMap<>();

    public void save(Pending pending) {
        requests.put(pending.requestId(), pending);
    }

    public boolean consume(
            String browserSession,
            String responseInResponseTo,
            String subjectConfirmationInResponseTo) {

        if (responseInResponseTo == null
                || !responseInResponseTo.equals(
                    subjectConfirmationInResponseTo)) {
            return false;
        }

        Pending pending = requests.get(responseInResponseTo);
        if (pending == null
                || !pending.browserSession().equals(browserSession)) {
            return false;
        }

        return requests.remove(responseInResponseTo, pending);
    }

    public static void main(String[] args) {
        CorrelationExample check = new CorrelationExample();
        check.save(new Pending("_REQ_123", "browser-A"));

        System.out.println("wrongSession=" +
            check.consume("browser-B", "_REQ_123", "_REQ_123"));
        System.out.println("assertionMismatch=" +
            check.consume("browser-A", "_REQ_123", "_REQ_OTHER"));
        System.out.println("matched=" +
            check.consume("browser-A", "_REQ_123", "_REQ_123"));
        System.out.println("replay=" +
            check.consume("browser-A", "_REQ_123", "_REQ_123"));
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac CorrelationExample.java
java CorrelationExample
~~~

**Stdout chính xác:**

~~~text
wrongSession=false
assertionMismatch=false
matched=true
replay=false
~~~

Phân tích:

- Browser B không được dùng pending request thuộc browser A.
- SubjectConfirmationData.InResponseTo không đúng → không consume.
- Lần đúng đầu tiên → consume thành công, xóa phần tử bằng thao tác **remove(key, expected)** có điều kiện.
- Lần gửi lại → không tìm được pending request, do đó thất bại.

**Không copy lớp này vào SAML login thực**: nó không xác minh signature, issuer, audience, time, Recipient, session-cookie security, XML parsing hay chống replay tổng thể; bản đồ cũng không có TTL, giới hạn kích thước và kiểm soát phân tán. Với Spring Security, dùng **saml2Login()** và request repository/validator chuẩn. Mục tiêu của Java demo là diễn giải **logic correlation**, không hướng dẫn thay thế OpenSAML AuthenticationProvider.

Trong hệ thống phân tán, một **ConcurrentHashMap cục bộ** không chia sẻ giữa các node; nếu thiết kế pending requests trong Redis/DB, cần TTL, atomic compare-and-delete và binding browser để tránh race/replay.

## 11. IdP-initiated SSO: trường hợp không có AuthnRequest gốc

SAML Web Browser SSO Profile có trường hợp **unsolicited / IdP-initiated Response**: IdP tự bắt đầu login và gửi Response đến SP mà trước đó browser **không có AuthnRequest** do SP gửi.

Trong trường hợp này:

- Theo profile, unsolicited **Response không có InResponseTo**.
- Bearer **SubjectConfirmationData cũng không được chứa InResponseTo** tham chiếu một request không tồn tại.
- SP không có AuthnRequest đã lưu để thực hiện correlation như SP-initiated SSO.
- Điều đó **không có nghĩa** SP có thể chấp nhận response tùy ý: vẫn phải kiểm tra signature, Issuer, AudienceRestriction, Destination/Recipient, NotOnOrAfter, replay, IdP trust và chính sách ứng dụng.

**Chính sách khuyến nghị:** Nếu ứng dụng không cần IdP-initiated login, hãy chỉ cho phép **SP-initiated SSO** và từ chối unsolicited response bằng cơ chế phù hợp phiên bản/IdP. Nếu có yêu cầu kinh doanh bắt buộc IdP-initiated:

1. Liệt kê IdP/tenant được phê duyệt và endpoint ACS được phép.
2. Xác nhận cơ chế IdP-initiated được Spring Security phiên bản đang dùng hỗ trợ/cấu hình và đã kiểm thử.
3. Áp dụng trust/subject/recipient/time validation đầy đủ và chặn replay.
4. Chống **login CSRF/session swapping** theo khả năng thiết kế và chính sách rủi ro; không viện dẫn “không có InResponseTo” để bỏ qua những biện pháp khác.
5. Chỉ cho phép điều hướng hậu đăng nhập tới đích an toàn; không dùng RelayState tùy ý làm URL redirect mở.

**Không ép unsolicited Response vào nhánh so khớp request giả.** SP-initiated và IdP-initiated là hai mode riêng với security trade-off khác nhau. Mặc định/cách cấu hình acceptance có thể khác theo Spring Security và IdP, vì vậy phải kiểm tra implementation và test âm thay vì suy đoán.

## 12. Replay prevention: InResponseTo cần thiết nhưng chưa đủ

Ví dụ một SAMLResponse hợp lệ được gửi lại hai lần:

- Nếu lần đầu đã sử dụng request gốc, lần thứ hai **không còn pending request** và phải thất bại trong mô hình SP-initiated strict.
- Nếu repository chỉ **load mà không consume**, request cũ có thể bị tái sử dụng.
- Nếu response khác có cùng InResponseTo nhưng được ký/đủ điều kiện, phải xét policy một lần cho request và replay IDs; không vì “chữ ký đúng” mà cho một request tạo vô hạn session.
- Nếu transaction bị lỗi giữa khâu consume và hoàn tất login, thiết kế retry phải rõ ràng, không tự cấp phép nhiều lần.
- Các SAML assertion còn có **NotOnOrAfter** và các ràng buộc thời gian. Kiểm tra hạn giúp giới hạn cửa sổ tấn công nhưng **không thay thế replay cache** khi profile/chính sách yêu cầu.

Đối với **Response.ID** và **Assertion.ID**, có thể cần lưu vết đã sử dụng với TTL phù hợp cho thời gian còn hiệu lực của assertion, đồng thời tránh lưu toàn bộ dữ liệu nhạy cảm không cần thiết. Việc Spring Security mặc định có thực hiện replay cache ở mức nào tùy version/provider/extension; **không nên tuyên bố rằng kiểm tra InResponseTo đã thay thế toàn bộ kiểm soát replay**.

## 13. SameSite cookie và session correlation trên ACS POST

Một lỗi thực tế phổ biến:

1. Browser mở trang SP, có HttpSession A.
2. SP lưu AuthnRequest trong session A và đưa browser đến IdP.
3. IdP POST SAMLResponse từ domain khác về ACS.
4. Browser **không gửi cookie session A** vì SameSite/cookie policy.
5. SP không tìm được AuthnRequest gốc và báo lỗi correlation/InResponseTo dù IdP đã phát Response hợp lệ.

Các bước kiểm tra:

- Dùng DevTools/Network xem **POST ACS có mang cookie session SP không**, so với cookie đã được phát trước redirect.
- Xác nhận **Secure**, **HttpOnly**, Domain, Path, HTTPS và **SameSite**.
- Với cross-site HTTP-POST, **SameSite=Lax/Strict có thể ngăn cookie**. Có thể cần **SameSite=None; Secure** với HTTPS và CSRF protection phù hợp.
- Kiểm tra reverse proxy không biến public HTTPS thành hostname/scheme nội bộ, không tạo cookie sai domain/path.
- Kiểm tra session timeout; nếu user xác thực ở IdP quá lâu, AuthnRequest đã lưu có thể hết trước callback.
- Nếu nhiều node, kiểm tra session store và phân phối/khả năng deserialize.

Ví dụ **production khi đã xác nhận cần cross-site POST cookie**:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: none
      timeout: 20m
~~~

Không áp cấu hình này máy móc cho thử nghiệm HTTP localhost. **SameSite=None** không thay thế CSRF protection ở endpoints nghiệp vụ; SAML ACS có cơ chế kiểm chứng riêng và ngoại lệ CSRF theo filter đã cấu hình, nhưng các thao tác thay đổi trạng thái của ứng dụng vẫn cần bảo vệ.

**Không sửa lỗi cookie bằng cách bỏ kiểm tra InResponseTo, signature hoặc AudienceRestriction.** Đó là mở lỗ hổng để chữa một sự cố về lưu trạng thái.

## 14. Nhiều IdP và nhiều tab: kết nối đúng request với đúng trust

### 14.1. Hai RelyingPartyRegistration

Một SP có thể dùng IdP **company** và **partner**, mỗi IdP có entityID, verification certificates, SSO endpoint, chính sách riêng. Khi browser khởi tạo request qua:

~~~text
/saml2/authenticate/company
/saml2/authenticate/partner
~~~

Pending request không chỉ có ID mà còn liên kết **registrationId**/bên IdP đã chọn, ACS và browser tương ứng. Khi nhận response:

- Không được nhận Response của IdP partner để hoàn tất request company.
- Không chọn metadata/JWKS/certificate mới từ Issuer chưa xác minh hoặc query parameter do browser tự đưa.
- Không dùng chung NameID/email của hai IdP để tự gộp thành một user nếu chưa có chính sách mapping.
- Khi request được phát tới IdP nào, response phải được validate theo configuration IdP đó.

### 14.2. Hai tab cùng phiên

Ví dụ tab 1 khởi tạo **_REQ_A**, tab 2 khởi tạo **_REQ_B** trong cùng HttpSession. Nếu repository chỉ giữ một pending request hoặc cleanup theo cách đặc thù, tab 2 có thể ghi đè tab 1. Khi response tab 1 quay về, SP không tìm thấy request **_REQ_A**.

Cách xử lý đúng:

- Kiểm tra hành vi của repository trong phiên bản Spring Security dùng thật.
- Nếu cần đăng nhập song song, thiết kế kho pending requests theo ID/RelayState có **giới hạn dung lượng, TTL, browser-session binding và atomic consume**.
- Không từ bỏ kiểm tra request correlation để “hỗ trợ nhiều tab”.
- Nếu muốn hạn chế song song, cung cấp UX thích hợp để người dùng chỉ thực hiện một flow đang chờ tại một thời điểm.
- Test callback ngược thứ tự, đồng thời và logout giữa chừng.

### 14.3. Reverse proxy, public ACS và session

Nếu SP chạy ở **http://10.0.0.3:8080** sau reverse proxy nhưng public ACS là **https://portal.example.org/login/saml2/sso/company**, các giá trị Recipient/Destination phải nhất quán với public URL. Header **Forwarded / X-Forwarded-*** chỉ nên tin từ proxy quản lý; cookie domain và Secure phải phù hợp HTTPS thực.

Sai ACS/Issuer/metadata thường dẫn tới lỗi SAML validation riêng, **không nên dồn hết cho InResponseTo** chỉ vì cùng xuất hiện ở callback.

## 15. Bảng tình huống cho phép/từ chối

Giả định browser A phát **AuthnRequest.ID=_REQ_A** cho IdP company, request được lưu trong HttpSession A. SP chỉ cho SP-initiated SSO và yêu cầu một lần sử dụng.

| Tình huống | Kết luận | Giải thích |
| --- | --- | --- |
| Response.InResponseTo=_REQ_A, bearer InResponseTo=_REQ_A, đúng session A, chữ ký và các điều kiện khác hợp lệ | **Có thể chấp nhận** | Correlation đạt, còn phụ thuộc toàn bộ SAML validation và policy |
| Response.InResponseTo=_REQ_B | **Từ chối** | Không trùng pending request của session A |
| Response.InResponseTo=_REQ_A nhưng bearer InResponseTo=_REQ_OTHER | **Từ chối** | SubjectConfirmationData không trùng request gốc |
| Response trỏ _REQ_A nhưng browser B gửi | **Từ chối** | Request gốc thuộc browser/session A, không thuộc B |
| Response.InResponseTo=_REQ_A nhưng request đã được consume | **Từ chối** | Replay hoặc xử lý trùng giao dịch |
| Response trỏ _REQ_A nhưng signature sai | **Từ chối** | Correlation không thay thế cryptographic validation |
| Response trỏ _REQ_A nhưng Issuer=IdP partner không được chọn | **Từ chối** | Sai quan hệ tin cậy |
| Response trỏ _REQ_A nhưng Recipient là ACS ứng dụng khác | **Từ chối** | Sai đích nhận |
| Response đúng nhưng NotOnOrAfter đã qua | **Từ chối** | Bearer subject confirmation hết hiệu lực |
| Response không có InResponseTo khi SP đang yêu cầu SP-initiated | **Từ chối theo policy strict** | Không chứng minh được request gốc |
| IdP-initiated Response không có InResponseTo nhưng SP đã phê duyệt mode này | **Xét riêng theo chính sách** | Không có request correlation; vẫn phải kiểm tra trust, signature, recipient, time và replay |

Từ **“có thể chấp nhận”** là chủ ý: một check InResponseTo PASS chỉ là **một điều kiện cần**, không kết luận user đã xác thực toàn bộ.

## 16. Kiểm thử âm và quy trình QA

Một bộ test an ninh hữu ích phải tạo **SAMLResponse thật được ký bởi test IdP** hoặc sử dụng fixture/SDK hỗ trợ. Không tự sửa XML đã ký rồi suy ra correlation validator hoạt động hay không, vì sửa XML sẽ làm signature sai và request có thể bị từ chối **trước khi kiểm tra InResponseTo**.

### 16.1. Test nên có

1. **Happy path:** request đúng, response/subject confirmation khớp ID, đúng browser session, signature/issuer/audience/time hợp lệ → login thành công.
2. **Sai Response.InResponseTo:** dùng response hợp lệ từ test IdP nhưng tham chiếu request khác → từ chối.
3. **Sai bearer InResponseTo:** test IdP phát một assertion có SubjectConfirmationData khác request → từ chối.
4. **Missing request:** xóa/expire pending request trước callback → từ chối trong SP-initiated strict.
5. **Wrong browser:** response được tạo cho browser A, gửi vào browser B → từ chối.
6. **Replay:** POST lại response sau khi request đã consume → không tạo login mới.
7. **Đổi IdP:** pending request company, response ký bởi partner → từ chối.
8. **Wrong audience/recipient:** giữ correlation đúng nhưng SAML target sai → từ chối.
9. **Expired assertion:** response tới sau NotOnOrAfter → từ chối.
10. **Cookie missing:** browser không gửi session cookie trên ACS POST → xử lý lỗi rõ ràng, không bỏ correlation.
11. **Multi-node:** khởi tạo ở node A, callback node B với session store chung → hoạt động đúng.
12. **Parallel tabs:** hai requests và callbacks quay về ngược thứ tự → hành vi theo repository đã được xác nhận, không chấp nhận sai request.
13. **Unsolicited:** nếu policy cấm thì từ chối; nếu policy cho phép thì test tập validation riêng.
14. **Open redirect:** RelayState độc hại không được dùng để chuyển browser tới domain ngoài chưa phê duyệt.

### 16.2. Quan sát và ghi log an toàn

Trong môi trường phát triển có thể bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Theo dõi **registrationId**, trạng thái tìm pending request, kết quả validation, response status và correlation ID cho log. Tuyệt đối không log raw **SAMLResponse**, SAMLRequest XML chứa dữ liệu nhạy cảm, session cookie, private key, NameID/attributes cá nhân không cần thiết.

Một số lỗi có thể được biểu diễn bằng **Saml2AuthenticationException** cùng mã như **INVALID_IN_RESPONSE_TO**; thông điệp và vị trí ném lỗi thay đổi theo Spring Security/OpenSAML version. Đừng phụ thuộc duy nhất vào một string error message trong test tự động; kiểm tra cả response behavior và trạng thái SecurityContext.

## 17. Các lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| **InResponseTo mismatch** | Response dùng request ID khác hoặc repository trỏ request khác | Đối chiếu request ID, session, registration và thứ tự callbacks |
| **Missing AuthnRequest** | Session hết hạn, cookie thiếu, node khác, repository bị ghi đè | Kiểm tra HttpSession/cookie/Spring Session và lifecycle pending request |
| **Login loop** | Không lưu correlation đúng, callback thất bại liên tục | Dò redirect chain, error status và request repository; không tắt validator |
| **Chỉ tab thứ hai login được** | Repository lưu một pending request tại một thời điểm | Kiểm tra thiết kế nhiều tab và giới hạn implementation |
| **POST ACS không có JSESSIONID** | SameSite, Secure, Domain/Path hoặc proxy | Kiểm tra DevTools cookies, HTTPS, SameSite=None; Secure nếu cần |
| **Callback tới node khác không thấy request** | HttpSession memory riêng từng instance | Spring Session/Redis hoặc routing đúng với failover |
| **Signature valid nhưng login bị từ chối** | InResponseTo, issuer, audience, recipient, time hoặc subject confirmation lỗi | Xem validation cụ thể, không chỉ chữ ký |
| **IDP-initiated login bị từ chối** | SP yêu cầu request gốc; unsolicited chưa được phê duyệt/cấu hình | Tách mode, xác nhận policy; không giả mạo request ID |
| **Nạn nhân bị đăng nhập vào tài khoản lạ** | Thiếu browser-session binding/login CSRF defense | Điều tra repository/RelayState/global cache và giới hạn unsolicited |
| **Sau nâng cấp Spring Security lỗi** | Khác biệt provider/validator/repository API hoặc mặc định | Kiểm tra tài liệu đúng version, viết lại regression tests |
| **RelayState dẫn tới trang ngoài** | Dùng RelayState làm URL không kiểm tra | Validate/allowlist destination, ưu tiên opaque server-side mapping |

**Cách tìm lỗi có thứ tự:** kiểm tra **đường khởi tạo AuthnRequest → request được lưu → browser session cookie → IdP response → lấy đúng pending request → đối chiếu InResponseTo → signature/Issuer/Audience/Recipient/time → Authentication**. Đừng bắt đầu bằng cách tắt kiểm chứng để “test cho qua”.

## 18. Checklist production

- [ ] SP chỉ tin IdP/metadata/verification certificate được phê duyệt; có registrationId/ACS rõ ràng.
- [ ] SP-initiated flow tạo **AuthnRequest.ID** duy nhất và lưu pending request trước khi gửi browser sang IdP.
- [ ] **Saml2AuthenticationRequestRepository** được dùng nhất quán ở cả hai chiều.
- [ ] **Response.InResponseTo** được đối chiếu với **AuthnRequest.ID** đã lưu.
- [ ] **Bearer SubjectConfirmationData.InResponseTo** được xác minh theo SAML Web Browser SSO Profile.
- [ ] Pending request được gắn với **đúng browser/session**, không chỉ InResponseTo/RelayState toàn cục.
- [ ] Chỉ có một lần consume; có kiểm soát replay Response/Assertion theo profile và policy.
- [ ] Chữ ký, Issuer, AudienceRestriction, Recipient/Destination, Conditions/time vẫn được xác minh độc lập.
- [ ] **SP-initiated** và **IdP-initiated/unsolicited** được phân biệt bằng policy tường minh.
- [ ] Cookie/session trên cross-site ACS POST được kiểm thử, không bỏ correlation vì SameSite.
- [ ] Nếu nhiều instance, session/pending request có store chung, TTL, giới hạn kích thước và thao tác atomic phù hợp.
- [ ] Nếu hỗ trợ nhiều IdP, request/response gắn với đúng registration và issuer được phê duyệt.
- [ ] Nếu hỗ trợ nhiều tab, đã test callbacks ngược thứ tự, pending request không bị dùng chéo.
- [ ] RelayState không được dùng làm open redirect hoặc bằng chứng đăng nhập tự thân.
- [ ] Có test âm cho missing/wrong/expired/replayed request, wrong browser, wrong IdP và malformed response.
- [ ] Log có kiểm soát, không ghi SAMLResponse/session cookie/private key/NameID nhạy cảm.
- [ ] Chỉ thiết lập **SecurityContext** và phiên SP sau khi toàn bộ SAML validation hoàn tất.

**Kết luận:** **InResponseTo** trả lời câu hỏi “SAMLResponse/Assertion này có phản hồi đúng AuthnRequest mà SP đã phát cho phiên browser này không?”. Sự trùng khớp phải dựa trên **request đã lưu và ràng buộc phiên**, kết hợp signature, issuer, audience, recipient, thời gian và chống replay. Trong Spring Security, ưu tiên **saml2Login() + HttpSessionSaml2AuthenticationRequestRepository** mặc định khi phù hợp, thay vì viết logic đối chiếu XML ở controller.

## 19. Tài liệu tham khảo

- [Spring Security – SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): Saml2WebSsoAuthenticationRequestFilter, request repository mặc định, RelayState và cảnh báo khi chuyển sang cache.
- [Spring Security – SAML 2.0 Authentication Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): Saml2AuthenticationTokenConverter, OpenSAML provider và response/assertion validators.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): luồng SAML Web Browser SSO.
- [Spring Security 6.5 – Saml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html): save/load/remove request.
- [Spring Security 6.5 – HttpSessionSaml2AuthenticationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/web/HttpSessionSaml2AuthenticationRequestRepository.html): implementation lưu AuthnRequest trong HttpSession.
- [OASIS SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO Profile, processing rules, unsolicited responses và InResponseTo.
- [OASIS SAML 2.0 Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-errata-2.0-cd-04.html): bearer SubjectConfirmationData.InResponseTo và quy tắc xử lý.
