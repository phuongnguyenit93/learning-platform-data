# Saml2AuthenticationTokenConverter và lựa chọn đăng ký phù hợp

## 1. Bài toán: một ACS, nhiều đối tác SAML

Trong ứng dụng **Spring Security Servlet** sử dụng **SAML 2.0 Web Browser SSO**, **Service Provider (SP/Relying Party)** có thể được cấu hình với một hoặc nhiều **Identity Provider (IdP/Asserting Party)**. Khi trình duyệt POST SAMLResponse về **Assertion Consumer Service (ACS)**, Spring Security cần biết: **phản hồi này thuộc cấu hình đối tác nào để dùng đúng issuer, verification certificates, SP entityId, ACS và các quy tắc xác minh?**

Thành phần trọng tâm là **Saml2AuthenticationTokenConverter**. Nó là một **AuthenticationConverter** chuyển **HttpServletRequest chứa SAMLResponse** thành **Saml2AuthenticationToken chưa xác thực**, đồng thời **chọn RelyingPartyRegistration** tương ứng. Kết quả được đưa tới **AuthenticationManager / OpenSAML authentication provider** để kiểm chứng Response và Assertion. Converter **không phải** thành phần kết luận người dùng đã đăng nhập.

Ví dụ, SP có hai registration:

| Thuộc tính | Registration corp | Registration partner |
| --- | --- | --- |
| **registrationId** | corp | partner |
| **IdP entityID** | https://login.corp.example.org/saml | https://idp.partner.example.org/saml |
| **IdP SSO URL** | URL do Corp IdP công bố | URL do Partner IdP công bố |
| **IdP verification certificates** | Khóa ký của Corp IdP | Khóa ký của Partner IdP |
| **SP entityID** | Có thể riêng theo registration | Có thể riêng theo registration |
| **SP ACS** | /login/saml2/sso/corp | /login/saml2/sso/partner |

Nếu phản hồi của **Corp IdP** bị xác minh bằng certificate của **Partner IdP**, hoặc nếu phản hồi dành cho **SP corp** được gán sai vào **SP partner**, đăng nhập phải thất bại. Converter giúp **xác định cấu hình cần thử kiểm tra**, còn authentication provider quyết định **SAMLResponse có thực sự hợp lệ với cấu hình ấy hay không**.

Bài học tập trung vào **luồng đăng nhập SAML2, Spring Boot 3.x/Spring Security 6.x, Java 17+**. Cách chọn registration và API có thể thay đổi chi tiết theo phiên bản; các ví dụ thực hành dùng Spring Boot **3.3.5** để thống nhất cú pháp.

## 2. Những đối tượng dễ nhầm tên

| Đối tượng / lớp | Ý nghĩa | Có xác thực người dùng không? |
| --- | --- | --- |
| **RelyingPartyRegistration** | Cấu hình quan hệ giữa SP và một asserting party: entityId, ACS, IdP issuer/SSO URL, khóa xác minh, khóa ký/giải mã. | Không. |
| **RelyingPartyRegistrationRepository** | Kho các registration được phép, tra cứu theo registrationId. | Không. |
| **registrationId** | Khóa kỹ thuật do ứng dụng đặt, như corp hoặc partner, để nhận diện cấu hình. | Không; không phải SAML entityID. |
| **RelyingPartyRegistrationResolver** | Chiến lược tìm một registration từ HTTP request và registrationId được cung cấp. | Không. |
| **DefaultRelyingPartyRegistrationResolver** | Resolver có sẵn, dùng repository để tìm registration và giải các placeholder URL phụ thuộc request. | Không. |
| **Saml2AuthenticationTokenConverter** | Lấy SAMLResponse và chọn registration, tạo authentication request token. | **Không xác minh** SAML Response/Assertion. |
| **Saml2AuthenticationToken** | Token **chưa xác thực** mang Response, registration và, khi có, AuthnRequest liên quan. | Chưa. |
| **Saml2WebSsoAuthenticationFilter** | Nhận callback ACS và ủy quyền chuyển đổi/xác thực cho converter và AuthenticationManager. | Điều phối. |
| **AuthenticationManager + OpenSAML provider** | Xác minh chữ ký, issuer, điều kiện SAML, correlation, giải mã và tạo Authentication hợp lệ. | **Có, nếu toàn bộ điều kiện đạt.** |
| **Saml2Authentication** | Kết quả Authentication của người dùng sau khi SAML hợp lệ. | Đã xác thực; quyền ứng dụng vẫn phải được kiểm tra riêng. |

**registrationId không phải userId, NameID, IdP issuer hay SP entityID.** Một IdP có thể có nhiều registration trong cùng ứng dụng SP, chẳng hạn cho các tenant/SP entityID khác nhau; và một registration có thể trỏ tới một IdP với chính sách riêng.

Ví dụ:

~~~text
registrationId: corp
IdP entityID:   https://login.corp.example.org/saml
SP entityID:    https://app.example.com/saml2/service-provider-metadata/corp
SP ACS:         https://app.example.com/login/saml2/sso/corp
~~~

Ba giá trị sau không nhất thiết giống nhau. ID trong URL ACS giúp chọn registration, **nhưng không tự chứng minh danh tính của IdP đã gửi bản tin**.

## 3. Converter nằm đâu trong luồng Web Browser SSO?

Sơ đồ SP-initiated login:

~~~text
Browser                  Spring Security SP                    Corp IdP
   |-- GET /private ------------>|                                |
   |<-- redirect /saml2/authenticate/corp ------------------------|
   |                             |-- tạo AuthnRequest (ID=_r1) ->|
   |                             |-- lưu request + registrationId |
   |------------------------ AuthnRequest đến IdP ---------------->|
   |<-------------------- form SAMLResponse sau login ------------|
   |-- POST /login/saml2/sso/corp --> Saml2WebSsoAuthenticationFilter
   |                                  |
   |                                  v
   |                         Saml2AuthenticationTokenConverter
   |                                  |
   |                        chọn RelyingPartyRegistration
   |                        + lấy AuthnRequest đã lưu nếu có
   |                        + tạo Saml2AuthenticationToken
   |                                  |
   |                                  v
   |                       AuthenticationManager/OpenSAML provider
   |                        kiểm chữ ký, issuer, audience,
   |                        destination, recipient, thời hạn,
   |                        InResponseTo và điều kiện profile
   |                                  |
   |                        hợp lệ: tạo Saml2Authentication
   |<--------------- local session / truy cập tài nguyên --------|
~~~

Các bước chính:

1. **Saml2WebSsoAuthenticationRequestFilter** chuẩn bị AuthnRequest cho registration **corp** và gửi browser tới IdP tương ứng.
2. Một **Saml2AuthenticationRequestRepository** lưu thông tin AuthnRequest đang chờ; mặc định phổ biến của Spring Security Servlet là **HttpSessionSaml2AuthenticationRequestRepository**.
3. IdP xác thực người dùng và trả SAMLResponse qua browser đến ACS của ứng dụng.
4. **Saml2WebSsoAuthenticationFilter** kích hoạt tại endpoint xử lý callback và gọi AuthenticationConverter.
5. **Saml2AuthenticationTokenConverter** tìm registration phù hợp bằng ngữ cảnh request/URL hoặc thông tin Response khi cần, rồi tạo **Saml2AuthenticationToken**.
6. **AuthenticationManager** xác thực token bằng SAML provider của phiên bản Spring Security/OpenSAML đang dùng.
7. Chỉ sau khi kiểm chứng thành công, Spring Security tạo **Authentication đã xác thực**, cập nhật SecurityContext và có thể duy trì phiên ứng dụng.

**Đừng đặt dấu bằng giữa “converter chọn được registration” và “user đã xác thực”.** Chọn registration là bước tìm cấu hình kiểm tra; chữ ký và toàn bộ điều kiện SAML mới xác định login có được chấp nhận.

## 4. Converter chọn registration theo những tín hiệu nào?

Theo tài liệu Spring Security, cơ chế mặc định thông thường có thể sử dụng **AuthnRequest đã lưu**, **registrationId từ đường callback** và khi không tìm được hai tín hiệu đó thì **Issuer của SAMLResponse** để định vị registration. Thứ tự và fallback chính xác phụ thuộc version/implementation; không nên tự viết bản clone rồi cho rằng mọi Spring Security 6.x/7.x luôn dùng cùng một thuật toán nội bộ.

### 4.1. Ngữ cảnh AuthnRequest đã lưu

Trong **SP-initiated flow**, Spring tạo AuthnRequest và lưu thông tin giao dịch, bao gồm registrationId được dùng khi yêu cầu phát ra. Khi Response quay lại, converter có thể tra cứu **AuthnRequest đã được gắn với browser/session** và xác định registration ban đầu.

Đây là tín hiệu mạnh về **ngữ cảnh lựa chọn**, vì SP biết nó đã khởi tạo login tới IdP nào. Tuy nhiên, nó không phải lý do để bỏ qua xác minh **Response.InResponseTo**, **SubjectConfirmationData.InResponseTo**, issuer, chữ ký, audience và destination.

Ví dụ:

~~~text
SP đã tạo AuthnRequest ID=_req_101 cho registrationId=corp
IdP POST Response tới ACS
Converter lấy lại request đã lưu -> biết registrationId=corp
Authentication provider kiểm Response có thực sự khớp _req_101,
IdP corp, SP entityID, ACS, chữ ký và thời hạn hay không
~~~

Nếu Response lại mang issuer của **partner**, việc converter tìm ra **corp** từ request đã lưu **không hợp thức hóa** Response. Provider phải từ chối do sai quan hệ tin cậy, hoặc điều kiện SAML khác không khớp.

### 4.2. registrationId ở đường ACS

Endpoint mặc định phổ biến:

~~~text
POST /login/saml2/sso/{registrationId}
~~~

Ví dụ:

~~~text
POST /login/saml2/sso/corp
POST /login/saml2/sso/partner
~~~

Spring có thể dùng **registrationId** trong URL để tra **RelyingPartyRegistrationRepository**. Nếu không tìm thấy registrationId được chỉ rõ, phải **từ chối cấu hình không tồn tại** theo cơ chế xử lý lỗi phù hợp; không tự thêm một registration hoặc chấp nhận issuer tùy ý.

**URL chỉ là tín hiệu định tuyến**, không phải bằng chứng IdP. Bất kỳ client nào cũng có thể gửi POST đến đường ACS; vẫn phải kiểm chữ ký từ verification credentials của đúng IdP và toàn bộ điều kiện SAML.

### 4.3. Response.Issuer khi thiếu request/registrationId

Với ACS **không có registrationId**, hoặc trường hợp không tìm được ngữ cảnh đã lưu, Spring có thể cố suy ra registration từ **Issuer trong SAML Response**.

Ví dụ:

~~~text
POST /saml/acs
  SAMLResponse có Response.Issuer = https://idp.partner.example.org/saml

Kho registration:
  corp    -> issuer https://login.corp.example.org/saml
  partner -> issuer https://idp.partner.example.org/saml

Có một registration khớp issuer -> partner là ứng viên để xác minh.
~~~

**Issuer lấy từ Response ở bước này là dữ liệu chưa được tin cậy** vì bản tin do trình duyệt gửi tới. Nó chỉ là một **gợi ý để chọn khóa và cấu hình**; phải **xác minh chữ ký, issuer, destination, audience, certificate và các điều kiện SAML** trước khi xác nhận danh tính.

**Trường hợp nguy hiểm:** Hai registration có **cùng IdP entityID**, ví dụ **corp-eu** và **corp-us**, nhưng khác SP entityID, ACS hoặc tenant. Khi không có request đã lưu và không có registrationId ở URL, **chỉ dùng issuer để phân biệt không đủ thông tin**. Hãy thiết kế ACS riêng, duy trì ngữ cảnh đăng nhập hoặc có chiến lược resolver bổ sung đã được kiểm chứng; **không chọn ngẫu nhiên một registration**.

### 4.4. Bảng quyết định thực tế

| AuthnRequest đã lưu? | URL có registrationId? | Response.Issuer | Hướng xử lý |
| --- | --- | --- | --- |
| Có, thuộc corp | Có corp | Corp IdP | Chọn cấu hình corp làm ứng viên; provider tiếp tục xác minh tất cả điều kiện. |
| Có, thuộc corp | Không có ID trên path | Corp IdP | Có thể tìm corp từ request đã lưu; vẫn phải correlation đúng. |
| Không | Có partner | Partner IdP | Tìm partner từ repository; phải xác minh issuer, chữ ký, ACS, audience và chính sách unsolicited. |
| Không | Không | Issuer chỉ khớp một registration | Có thể lookup bằng Response.Issuer; xác minh toàn bộ bản tin. |
| Không | Không | Issuer khớp nhiều registration | **Không đủ căn cứ để chọn duy nhất**; cần ngữ cảnh hoặc resolver phù hợp. |
| Không | Có invalid-id | Bất kỳ | Từ chối registration không tồn tại; không tự tạo đối tác. |
| Có corp | Có partner | Bất kỳ | Tình huống **xung đột ngữ cảnh**; điều tra callback/URL/registration, không cố cho login chỉ nhờ một trường khớp. |
| Có corp | Có corp | Partner IdP | Bản tin không khớp trust; provider phải từ chối dù URL có corp. |
| Không | Không | Issuer chưa đăng ký | Từ chối đối tác không tin cậy. |

Bảng nêu **quyết định an toàn cần đạt**, không phải bảng khẳng định thứ tự mọi câu lệnh nội bộ của từng phiên bản. Đặc biệt, khi các tín hiệu mâu thuẫn, phải để provider và chính sách kiểm chứng bắt lỗi; **không chủ động nới lỏng validation để hợp thức hóa mismatch**.

## 5. RelyingPartyRegistrationRepository và resolver

**RelyingPartyRegistrationRepository** là nguồn cấu hình **những đối tác được phép**. Các registration có thể được cấu hình bằng Spring Boot YAML/properties, dựng thủ công từ IdP metadata, hoặc được lấy từ repository do ứng dụng quản lý.

**RelyingPartyRegistration** chứa hai mặt:

- **Relying party (SP)**: entityId, assertionConsumerServiceLocation, signingX509Credentials, decryptionX509Credentials, logout endpoints theo cấu hình.
- **Asserting party (IdP)**: entityId/issuer, singleSignOnServiceLocation/binding, verificationX509Credentials, thông tin logout, policy ký AuthnRequest.

**DefaultRelyingPartyRegistrationResolver** dùng repository để tìm cấu hình theo request và registrationId, đồng thời giúp giải template placeholders theo ngữ cảnh request. Ví dụ, các URL dùng **{baseUrl}** cần phản ánh đúng scheme/host/port công khai của ứng dụng.

Không nhầm:

~~~text
RelyingPartyRegistrationRepository   kho các registration được tin cậy
DefaultRelyingPartyRegistrationResolver   chọn/resolve registration từ request
Saml2AuthenticationTokenConverter    tạo token xác thực đầu vào gắn registration
OpenSAML provider                     quyết định Response/Assertion hợp lệ
~~~

Dùng đúng một registration không có nghĩa converter có thể bỏ qua tất cả kiểm tra: với một IdP, **Response.Issuer vẫn phải khớp IdP entityID**, và chữ ký/điều kiện SAML vẫn phải được xác minh.

### Khi nào nên giữ mặc định?

Giữ converter/resolver mặc định khi:

- ACS sử dụng URL của framework với **{registrationId}**;
- SP-initiated flow duy trì AuthnRequest trong repository mặc định;
- mỗi IdP có metadata và verification cert đúng;
- không có yêu cầu routing nhiều tenant hoặc binding đặc biệt;
- cấu hình **saml2Login()** hoạt động với IdP sandbox.

Không thêm converter tùy chỉnh chỉ vì hệ thống có hai IdP; nhiều registration là khả năng bình thường của Spring Security SAML2 SP.

## 6. AuthnRequestRepository và vấn đề correlation/session

Khi SP khởi tạo SAML login, IdP sẽ mất một khoảng thời gian để xác thực người dùng, MFA và trả Response. Spring phải tìm lại request ban đầu để liên kết login:

~~~text
AuthnRequest.ID = _req_101
registrationId  = corp
saved request   = ngữ cảnh SAML trong session/repository
Response.InResponseTo = _req_101
SubjectConfirmationData.InResponseTo = _req_101
~~~

**HttpSessionSaml2AuthenticationRequestRepository** là lựa chọn mặc định phổ biến: nó gắn AuthnRequest chờ với **HttpSession của browser**. Có lợi ích bảo mật rõ ràng: nếu attacker cố đưa Response của phiên đăng nhập attacker vào browser nạn nhân, browser nạn nhân không có AuthnRequest tương ứng và phải bị từ chối theo chính sách correlation.

Đừng coi việc tìm được response từ **RelayState** hay **InResponseTo** là bằng chứng request đó thuộc **chính browser đang đăng nhập**. Nếu dùng distributed cache mà chỉ lookup bằng một ID do browser gửi, có thể làm mất cơ chế chống **login CSRF/login fixation** vốn có khi request gắn với HttpSession. Cần thiết kế binding browser/session và chống replay.

Các lỗi thường gặp khiến mất request chờ:

1. **Session cookie không quay lại** sau redirect POST từ IdP vì SameSite, Secure, domain, proxy hoặc browser policy.
2. **Timeout** của session khi người dùng nhập MFA quá lâu.
3. **Cluster** nhiều node chưa chia sẻ HttpSession hoặc routing không nhất quán.
4. **Đa tab** tạo nhiều AuthnRequests; custom repository chỉ lưu một bản và ghi đè bản còn lại.
5. **Sai registrationId/ACS** giữa request gửi đi, metadata SP và Response trả về.
6. **Chuyển HTTP/HTTPS hoặc hostname** giữa AuthnRequest và callback làm cookie/session và template URL không nhất quán.
7. **Request đã tiêu thụ** nhưng Response được gửi lần thứ hai.

Không chữa những tình huống này bằng cách tắt kiểm tra **InResponseTo** hoặc mặc định cho phép unsolicited login. Phải sửa cookie/session, repository, expiry, proxy và cấu hình IdP.

### Một URL ACS chung có dùng được không?

Về mặt thiết kế, có thể cần **shared ACS** chẳng hạn:

~~~text
https://app.example.com/saml/acs
~~~

khi đối tác IdP không chấp nhận đường callback có registrationId. Nhưng nếu URL chung không chứa ID, hệ thống cần **tín hiệu lookup khác** (AuthnRequest đã lưu hoặc issuer duy nhất, hoặc chiến lược resolver có căn cứ). Đồng thời, cấu hình:

- **Saml2LoginConfigurer.loginProcessingUrl** phải nhận POST ở endpoint mới;
- **RelyingPartyRegistration.assertionConsumerServiceLocation** của mỗi registration phải đồng bộ URL ACS được IdP đăng ký;
- bộ converter và repository phải tìm đúng đối tác;
- **Response.Destination**, **SubjectConfirmationData.Recipient** và **Audience** vẫn phải được provider kiểm chứng.

Đổi **loginProcessingUrl** một mình mà quên đổi **ACS metadata/IdP registration** sẽ khiến IdP gửi Response đến URL cũ hoặc khiến validation không khớp.

## 7. IdP-initiated SSO và vấn đề issuer fallback

**SP-initiated SSO**: browser bắt đầu từ SP, SP tạo AuthnRequest, lưu registrationId và request ID rồi gửi IdP. Đây là mô hình dễ liên kết response với session nhất.

**IdP-initiated SSO** (unsolicited): người dùng bấm ứng dụng trên portal IdP, IdP gửi Response tới SP **khi SP không gửi AuthnRequest**. Vì không có request đang chờ, converter có thể phải dựa trên URL/issuer để tìm registration.

Trong unsolicited flow:

- Không có **AuthnRequest.ID** để gắn với Response.InResponseTo theo cách SP-initiated.
- Phải có chính sách chủ động cho phép hoặc từ chối unsolicited cho từng đối tác.
- Chữ ký, IdP issuer, recipient, destination, audience, assertion expiration, chống replay và chống login CSRF vẫn quan trọng.
- SAML Response chứa issuer là **untrusted input** trước khi chữ ký/điều kiện được xác minh.
- Một IdP có thể dùng cùng issuer cho nhiều SP registration, nên chỉ dựa vào issuer có thể không đủ.

Spring Security có khả năng nhận SAML responses từ IdP-initiated flows tùy cấu hình và phiên bản, nhưng **không được suy ra rằng mọi mode unsolicited mặc định đều đạt chính sách của tổ chức**. Nếu nghiệp vụ không cần IdP-initiated, hãy quy định chính sách từ chối và kiểm thử; nếu cần, thiết kế chống login CSRF và replay cùng IdP admin.

## 8. Ví dụ Spring Boot 3.3.5 / Java 17 với hai IdP

Ví dụ sau có **một SP Spring**, hai registration **corp** và **partner**. Mỗi registration dùng metadata IdP độc lập. Framework lựa chọn cấu hình phù hợp khi callback và kiểm chứng Response theo đối tác; ứng dụng không tự đọc NameID từ SAMLResponse chưa xác thực.

**Điều kiện bắt buộc:**

- Java 17+, Maven có thể tải dependency;
- Hai IdP thật hoặc hai cấu hình sandbox IdP có metadata hợp lệ;
- IdP đã đăng ký **SP entityID + ACS URL** tương ứng từng registration;
- Private key signing/decryption của SP được bổ sung nếu đối tác yêu cầu;
- Chạy localhost chỉ để học; production dùng HTTPS public URL và cấu hình proxy an toàn.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>saml-registration-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
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

Đây là Spring Security **Service Provider**, không phải SAML IdP. Kho Shibboleth có thể cần cho OpenSAML; dùng repository và chính sách quản lý phụ thuộc đã được tổ chức phê duyệt.

### 8.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${CORP_IDP_METADATA_URI}
          partner:
            assertingparty:
              metadata-uri: ${PARTNER_IDP_METADATA_URI}

server:
  port: 8080
  servlet:
    session:
      timeout: 30m
~~~

**CORP_IDP_METADATA_URI** và **PARTNER_IDP_METADATA_URI** là hai biến môi trường chứa **URL metadata IdP thật**. Phải thay bằng địa chỉ do đối tác quản trị IdP xác nhận; ví dụ domain **example.org** trong bài chỉ là minh họa. Không dùng URL chưa kiểm chứng làm nguồn trust.

Boot tạo **RelyingPartyRegistrationRepository** có registrationId **corp** và **partner**. Mỗi entry chứa issuer/SSO URL/certificate từ metadata tương ứng, còn SP entityID và ACS được cấu hình theo mặc định hoặc ghi đè đúng đăng ký tại IdP.

### 8.3. Application

**src/main/java/com/example/samlregistration/SamlRegistrationApplication.java**

~~~java
package com.example.samlregistration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlRegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlRegistrationApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig dùng converter mặc định

**src/main/java/com/example/samlregistration/SecurityConfig.java**

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Quan trọng:** Mặc dù không viết trực tiếp tên **Saml2AuthenticationTokenConverter** trong SecurityConfig, Spring Security vẫn cấu hình converter mặc định cho SAML login. Đó là lựa chọn phù hợp khi dùng ACS chuẩn và request repository bình thường.

### 8.5. Controller chỉ sử dụng principal đã xác thực

**src/main/java/com/example/samlregistration/DemoController.java**

~~~java
package com.example.samlregistration;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SAML registration demo";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return "NameID=" + user.getName();
    }
}
~~~

Controller không tự chạm vào **SAMLResponse**; người dùng chỉ truy cập được **/me** sau khi Spring Security/OpenSAML hoàn tất xác minh và thiết lập Authentication.

### 8.6. Chạy và quan sát

Đặt biến môi trường metadata URI thật theo hệ điều hành rồi chạy trong thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Các hành vi kiểm tra:

1. **GET http://localhost:8080/** trả đúng body **SAML registration demo** khi ứng dụng khởi động thành công.
2. **GET http://localhost:8080/saml2/authenticate/corp** khởi tạo login tới **Corp IdP**; Spring lưu AuthnRequest gắn với registration corp.
3. **GET http://localhost:8080/saml2/authenticate/partner** khởi tạo login tới **Partner IdP**.
4. **POST http://localhost:8080/login/saml2/sso/corp** là ACS callback theo URL mặc định cho corp, nhận tham số SAMLResponse từ IdP. **Không** tự POST dữ liệu giả để bỏ qua chữ ký.
5. **GET http://localhost:8080/saml2/metadata/corp** xuất **SP metadata corp**, giúp kiểm tra entityID/ACS; tương tự đối với partner.
6. **GET http://localhost:8080/me** khi chưa có Authentication sẽ bắt đầu login (với nhiều IdP, có thể hiển thị trang lựa chọn IdP), và sau khi nhận SAML Response hợp lệ sẽ trả chuỗi **NameID=<giá trị do IdP phát hành>**. Không có stdout cố định cho NameID vì tùy tài khoản IdP.

Với hai IdP, **mỗi registration phải được test riêng** từ redirect, issuer và SSO endpoint đến ACS, certificate, assertion audience và quyền truy cập cuối cùng.

## 9. Khi nào cần cấu hình converter tường minh?

Trong đa số ứng dụng, **không cần tự tạo Saml2AuthenticationTokenConverter**. Nhưng nếu cần resolver khác hoặc muốn thay đổi cách nhận callback, Spring Security có điểm mở rộng **saml2Login.authenticationConverter(AuthenticationConverter)**.

Ví dụ **thay toàn bộ SecurityConfig trước bằng phiên bản này**. Nó chủ động dựng converter theo **DefaultRelyingPartyRegistrationResolver** nhưng **không thay validator** hay tự xác thực Assertion.

**src/main/java/com/example/samlregistration/SecurityConfig.java – phiên bản thay thế**

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationTokenConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultRelyingPartyRegistrationResolver(registrations);
        var converter = new Saml2AuthenticationTokenConverter(resolver);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml2 -> saml2.authenticationConverter(converter))
            .saml2Metadata(metadata -> {});

        return http.build();
    }
}
~~~

Trong cấu hình này:

- Resolver tìm **RelyingPartyRegistration** từ repository theo tín hiệu request; converter nhận resolver để tạo **Saml2AuthenticationToken**.
- **Saml2AuthenticationTokenConverter** có khả năng lấy AuthnRequest đã lưu qua **Saml2AuthenticationRequestRepository**. Khi tùy biến request repository, phải đảm bảo **filter tạo AuthnRequest, converter và filter callback ACS dùng cùng repository/nguồn trạng thái**; tránh tình trạng request lưu một nơi nhưng callback tìm nơi khác.
- **saml2Login.authenticationConverter(...)** thay chiến lược chuyển HTTP request thành token. Nó **không** có chức năng bỏ qua signature/issuer/audience checks của OpenSAML.
- Ví dụ dùng resolver mặc định nhằm minh họa ranh giới API; trong thực tế chỉ cần cấu hình tường minh nếu có lý do. **Không tạo hai SecurityConfig bean cùng lúc**.
- Nếu cần dùng custom **RelyingPartyRegistrationResolver**, phải định nghĩa rõ cách chọn đối tác và vẫn giữ xác minh SAML từ provider sau khi chọn.

### Thay ACS URL đồng bộ ba chỗ

Giả sử nghiệp vụ đòi endpoint **/custom/saml/acs**. Không đủ chỉ đổi DSL:

~~~java
// Minh họa đoạn cấu hình chèn vào saml2Login trong SecurityFilterChain:
.saml2Login(saml2 -> saml2.loginProcessingUrl("/custom/saml/acs"))
~~~

Đoạn này **không chạy độc lập**; cần khai báo **assertionConsumerServiceLocation** của RelyingPartyRegistration phù hợp và cấu hình **Reply URL/ACS** của IdP là **https://public-host/custom/saml/acs**. Khi endpoint không chứa **{registrationId}**, cần đặc biệt kiểm tra converter nhận ra registration từ request đã lưu hoặc lookup issuer một cách không mơ hồ; có thể phải custom converter theo phiên bản.

Nếu bỏ qua một trong các điều kiện trên, kết quả thường là callback **404, registration not found, invalid Destination/Recipient hoặc mismatch ACS**. Không sửa bằng cách cho phép bất kỳ issuer/ACS nào.

## 10. Lựa chọn registration cho nhiều tenant

Một **IdP** có thể cấp SAML cho **nhiều tenant**, hoặc một SP dùng **một ACS chung** cho nhiều đối tác. Khi đó phải phân biệt ít nhất ba loại dữ kiện:

| Thuộc tính | Vai trò | Có đáng tin ngay khi nhận HTTP request không? |
| --- | --- | --- |
| **registrationId** từ URL | Gợi ý chọn entry trong repository. | **Không** phải bằng chứng IdP. |
| **Response.Issuer** | Gợi ý IdP nào phát Response. | **Chưa đáng tin** trước khi kiểm chữ ký. |
| **AuthnRequest đã lưu trong session** | Ngữ cảnh giao dịch SP đã tạo. | Là dữ kiện do SP quản lý, nhưng vẫn phải kiểm khớp Response và điều kiện bảo mật. |
| **HTTP Host / X-Forwarded-Host** | Có thể hỗ trợ định tuyến tenant/ACS. | Chỉ dùng khi proxy đáng tin và allowlist host được cấu hình chặt. |
| **NameID / Attributes** | Danh tính/thuộc tính do Assertion khai báo. | **Chỉ tin sau khi provider đã xác minh Assertion**. |
| **Tenant query parameter** | Dữ kiện browser cung cấp. | Không dùng để tự chọn trust/certificate không kiểm soát. |

**Đặc biệt nguy hiểm:** lấy một tham số request như **?tenant=arbitrary** rồi tải metadata/certificate từ URL do browser đưa vào. Đó là cho phép client chưa xác thực điều khiển nguồn tin cậy và có thể tạo lỗ hổng **SSRF, confused-deputy hoặc đăng nhập sai tenant**.

Một hệ thống multi-tenant an toàn thường:

1. Duy trì **allowlist** các registrationId, IdP entityID, SP entityID và ACS URL đã được phê duyệt.
2. Với **SP-initiated flow**, lưu correlation giữa browser session, AuthnRequest.ID và registration đã chọn.
3. Nếu dùng URL chung, xây **deterministic lookup** không mơ hồ hoặc yêu cầu registrationId trong route/host đã được kiểm soát.
4. Không dùng issuer chưa xác minh làm chính sách cấp quyền; issuer chỉ hỗ trợ chọn cấu hình cho bước **verification**.
5. Sau authentication, ánh xạ principal sang **tenant nội bộ** và kiểm tra authorization ở tầng business, không dựa duy nhất vào đường ACS.
6. Có negative tests: issuer sai, cert sai, audience sai, tenant khác, request ID thiếu/hết hạn, response replay và host header giả.

### Hai registration trỏ cùng IdP issuer

Giả sử **corp-vn** và **corp-sg** đều dùng **IdP entityID=https://login.corp.example.org/saml**, nhưng SP entityId/ACS khác nhau. **Issuer fallback không thể tự chọn giữa hai registration nếu thiếu thông tin khác.**

Một thiết kế đáng tin thường giữ **registrationId từ AuthnRequest đã lưu**, dùng **ACS riêng** hoặc resolver có quy tắc định tuyến đã phê duyệt. Không dùng **IdP user email/NameID chưa xác thực** để chọn tenant.

## 11. Ví dụ Java 17 độc lập: mô phỏng nguyên tắc chọn registration

Đây là **chương trình Java 17 chạy độc lập** để hiểu các **tín hiệu chọn đối tác** và trường hợp mơ hồ. Nó **không phản ánh từng nhánh nội bộ của Spring Security**, **không xử lý SAMLResponse** và **không đủ để xác thực**. Mô phỏng cố ý áp dụng **chính sách từ chối xung đột** khi request/route khác nhau, vì trong tích hợp thật nên điều tra mismatch trước khi đăng nhập.

**RegistrationChoiceDemo.java**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class RegistrationChoiceDemo {

    static String choose(
            String savedRegistrationId,
            String routeRegistrationId,
            String responseIssuer,
            Set<String> allowed,
            Map<String, List<String>> byIssuer) {

        if (savedRegistrationId != null) {
            if (!allowed.contains(savedRegistrationId)) {
                return "UNRESOLVED";
            }
            if (routeRegistrationId != null
                    && !savedRegistrationId.equals(routeRegistrationId)) {
                return "CONFLICT";
            }
            return savedRegistrationId;
        }

        if (routeRegistrationId != null) {
            return allowed.contains(routeRegistrationId)
                    ? routeRegistrationId : "UNRESOLVED";
        }

        List<String> candidates = byIssuer.getOrDefault(responseIssuer, List.of());
        if (candidates.size() != 1) {
            return "UNRESOLVED";
        }

        String only = candidates.get(0);
        return allowed.contains(only) ? only : "UNRESOLVED";
    }

    public static void main(String[] args) {
        Set<String> allowed = Set.of("corp-vn", "corp-sg", "partner");

        Map<String, List<String>> byIssuer = Map.of(
                "https://login.corp.example.org/saml",
                List.of("corp-vn", "corp-sg"),
                "https://idp.partner.example.org/saml",
                List.of("partner"));

        String corpIssuer = "https://login.corp.example.org/saml";
        String partnerIssuer = "https://idp.partner.example.org/saml";

        System.out.println("saved request: "
                + choose("corp-vn", "corp-vn", corpIssuer, allowed, byIssuer));
        System.out.println("route: "
                + choose(null, "partner", partnerIssuer, allowed, byIssuer));
        System.out.println("issuer unique: "
                + choose(null, null, partnerIssuer, allowed, byIssuer));
        System.out.println("issuer ambiguous: "
                + choose(null, null, corpIssuer, allowed, byIssuer));
        System.out.println("conflict: "
                + choose("corp-vn", "corp-sg", corpIssuer, allowed, byIssuer));
        System.out.println("unknown route: "
                + choose(null, "unknown", partnerIssuer, allowed, byIssuer));
    }
}
~~~

Biên dịch và chạy JDK 17+:

~~~bash
javac RegistrationChoiceDemo.java
java RegistrationChoiceDemo
~~~

**stdout chính xác:**

~~~text
saved request: corp-vn
route: partner
issuer unique: partner
issuer ambiguous: UNRESOLVED
conflict: CONFLICT
unknown route: UNRESOLVED
~~~

Giải thích:

- **saved request** minh họa ngữ cảnh SP-initiated đã biết và route nhất quán.
- **route** minh họa registrationId có sẵn ở ACS.
- **issuer unique** minh họa chỉ có một đối tác trong allowlist khớp issuer.
- **issuer ambiguous** minh họa cùng IdP issuer thuộc nhiều registration; không chọn tùy tiện.
- **conflict** là chính sách **từ chối xung đột của chính chương trình mô phỏng**, không tuyên bố chính xác một exception/nhánh mặc định của converter Spring.
- **unknown route** từ chối ID không đăng ký, không tự tìm metadata mới.

**Không dùng hàm choose() trên production SAMLResponse để tạo Authentication.** Một lựa chọn chỉ trở thành đăng nhập hợp lệ khi Spring Security/OpenSAML **xác minh toàn bộ Response/Assertion, chữ ký, issuer, audience, recipient, destination, thời gian, correlation và replay policy**.

## 12. Những giới hạn của việc tìm registration bằng issuer

**Response.Issuer ở đâu?** Nó là một phần tử trong **SAML protocol Response**, không phải thuộc tính URL callback. Converter có thể phải đọc phần thông tin này để tìm ứng viên xác minh; nhưng trước khi chữ ký và trust được chứng minh, kẻ tấn công có thể gửi bất kỳ XML/Base64 nào vào ACS.

**Vì sao không dùng issuer làm chứng cứ?** Nếu attacker sửa Issuer thành IdP X, điều đó không cấp cho attacker khóa ký của IdP X. Khi converter chọn configuration X, provider phải xác minh chữ ký bằng certificate của X và từ chối nếu không khớp. Nếu ứng dụng tự tin issuer và đánh dấu Authentication thành công, ứng dụng đã bỏ mất ranh giới bảo mật quan trọng nhất.

**Nếu có hai IdP cùng sử dụng issuer?** Về mô hình federation, entityID nên định danh nhất quán đối tác; nếu hai cấu hình trùng issuer, cần giải quyết ambiguity. Không dựa vào thứ tự repository để chọn registration; cần ngữ cảnh đáng tin như registrationId/ACS và request correlation.

**Nếu metadata IdP thay đổi issuer?** Không tự chấp nhận issuer mới từ Response; trước hết cần xác minh thay đổi theo quy trình onboarding/rotation IdP, cập nhật registration và kiểm thử.

**Nếu response có Response.Issuer và Assertion.Issuer khác nhau?** Cần provider kiểm tra issuer ở cả những vị trí theo profile. Không cho phép một lớp dùng issuer A còn lớp kia dùng issuer B để vượt qua xác minh.

**Nếu Response được ký bằng khóa không trong registration đã chọn?** Phải từ chối theo trust policy. Không thử tuần tự mọi certificate từ mọi tenant rồi kết luận “khóa nào xác minh được thì tenant đó đúng” nếu không có hợp đồng định tuyến và chính sách an toàn.

## 13. Ma trận kiểm thử cho converter và chọn đối tác

Trong môi trường test, tạo **SAMLResponse hợp lệ được ký bằng khóa thử nghiệm** để kiểm tra đúng một điều kiện tại một thời điểm. Nếu chỉ sửa XML đã được ký, chữ ký có thể sai trước khi đến validation được muốn kiểm tra; không suy luận nguyên nhân từ lỗi chung.

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | SP gửi AuthnRequest corp, IdP corp trả đúng Response về ACS corp | Converter chọn đúng candidate; provider xác minh và có thể đăng nhập. |
| 2 | SP gửi AuthnRequest partner, IdP partner trả đúng Response về ACS partner | Tương tự, đúng registration partner. |
| 3 | URL ACS chỉ rõ corp nhưng registration không tồn tại trong repository | Không chọn được registration; từ chối xác thực. |
| 4 | ACS chọn corp, Response issuer partner, chữ ký partner hợp lệ | **Từ chối** vì không đúng trust/profile của corp. |
| 5 | ACS có corp nhưng Response được ký bằng cert không được corp tin cậy | **Từ chối** signature/trust. |
| 6 | AuthnRequest được lưu cho corp, Response.InResponseTo khác request ID | **Từ chối** correlation. |
| 7 | URL ACS đúng nhưng SubjectConfirmationData.Recipient là ACS khác | **Từ chối** bearer confirmation. |
| 8 | Response.Destination không khớp ACS public URL | **Từ chối** destination/profile validation. |
| 9 | AudienceRestriction không chứa SP entityID của registration được chọn | **Từ chối** audience. |
| 10 | Session chứa request chờ bị mất trên callback | Không cho phép bypass InResponseTo; kiểm tra cookie/repository. |
| 11 | IdP-initiated unsolicited Response được gửi tới một ACS đã đăng ký | Chỉ chấp nhận nếu **policy cho phép unsolicited**, và mọi validation/replay/login CSRF đều đạt. |
| 12 | IdP-initiated Response có issuer không đăng ký | Không chấp nhận unknown IdP. |
| 13 | URL chung không ID, một IdP issuer map tới hai registration | Resolver phải xử lý ambiguity; không tùy tiện chọn một. |
| 14 | Response vượt NotOnOrAfter hoặc Conditions đã hết hạn | **Từ chối**, dù issuer/registrationId đúng. |
| 15 | IdP đổi cert không thông báo và SP chưa cập nhật trust | **Từ chối** chữ ký; thực hiện rotation đúng quy trình. |
| 16 | Response được replay sau khi AuthnRequest đã tiêu thụ | **Từ chối** theo cơ chế one-time/correlation/replay áp dụng. |
| 17 | App chạy qua HTTPS proxy nhưng ACS metadata là HTTP internal | Cần sửa base URL/forwarded headers; không tắt recipient/destination validation. |
| 18 | Hai tab login song song tới hai IdP và custom request store chỉ giữ một entry | Kiểm tra store/correlation, không tự ghép Response với request khác. |
| 19 | Bản tin không có SAMLResponse hoặc Base64/XML lỗi | Không tạo Authentication; trả lỗi phù hợp, không coi request là anonymous đã đăng nhập. |
| 20 | Custom converter trả Saml2AuthenticationToken nhưng không validate chữ ký | AuthenticationManager phải tiếp tục validation; custom converter **không được tự đặt authenticated=true**. |

Một testcase âm tính được xem là đạt khi SP **từ chối đúng phản hồi không hợp lệ**. Không đặt mục tiêu “chạy qua được hết” bằng cách giảm mức validation.

## 14. Chẩn đoán lỗi thường gặp

| Biểu hiện | Kiểm tra trước | Hướng sửa |
| --- | --- | --- |
| **Relying party registration not found** | registrationId trong ACS, YAML và repository. | Sửa ID/path hoặc thêm registration đã được phê duyệt. |
| **Không tìm thấy registration khi ACS URL chung** | Có AuthnRequest đã lưu không? Response issuer có định vị được duy nhất không? | Dùng URL chứa ID, giữ request correlation hoặc thiết kế resolver rõ ràng. |
| **Issuer mismatch** | IdP Response.Issuer, assertingParty entityId của registration được chọn. | Sửa cấu hình/đối tác; không bỏ issuer check. |
| **Invalid signature** | IdP verification certificates, key rotation, signed Response/Assertion policy. | Cập nhật metadata/cert qua quy trình tin cậy. |
| **InResponseTo mismatch** | AuthnRequest ID đã lưu, HttpSession, repository và callback. | Sửa session/cookie/TTL/cluster, không bỏ correlation. |
| **Recipient/Destination mismatch** | ACS của registration, URL public, reverse proxy và metadata. | Đồng bộ HTTPS host/path/port ở cả SP và IdP. |
| **Login qua một tab được, tab khác lỗi** | Nhiều AuthnRequests song song và cơ chế lưu/đọc chúng. | Thiết kế request store hỗ trợ concurrency hoặc quy định UX phù hợp. |
| **IdP portal SSO không chạy nhưng SP-initiated chạy** | Unsolicited policy, ACS, issuer fallback, RelayState và login CSRF. | Thiết kế/kiểm thử IdP-initiated riêng nếu cần. |
| **Response khớp issuer nhưng audience sai** | SP entityId và AudienceRestriction của Assertion. | Sửa IdP application registration và metadata. |
| **Sau proxy URL đổi giữa GET login và POST callback** | Forwarded host/scheme, cookie SameSite/Secure và LB. | Đồng bộ public baseUrl và cấu hình proxy đáng tin. |
| **Đăng nhập đúng user nhưng sai tenant quyền** | Map principal sang tenant/authorities sau validation. | Authorization riêng; không lấy tenant từ trường chưa kiểm chứng. |

### Log cần thiết mà vẫn an toàn

Trong sandbox/debug, có thể log **registrationId**, đường ACS (không có payload), correlation ID nội bộ, loại lỗi validation và phương thức lookup đã dùng. Chỉ log issuer/host đã được chuẩn hóa theo chính sách; không dump raw SAMLResponse, Assertion, chữ ký, NameID nhạy cảm, cookie phiên, authorization credentials hoặc private key. Luồng chọn đối tác cần có đủ dấu vết để xác định request được đăng ký từ đâu, nhưng **log không được tạo lỗ hổng mới**.

## 15. Các hiểu nhầm quan trọng

1. **“Saml2AuthenticationTokenConverter xác thực người dùng.”** Sai: nó **chuẩn bị token đầu vào** và chọn registration; provider kiểm chứng.
2. **“registrationId là IdP entityID.”** Sai: registrationId là tên kỹ thuật trong repository; IdP issuer là một giá trị SAML riêng.
3. **“Đường /login/saml2/sso/corp chứng minh Response đến từ corp IdP.”** Sai: mọi client có thể POST URL; chữ ký/issuer/profile mới chứng minh nguồn hợp lệ.
4. **“Có một IdP nên không cần RelyingPartyRegistration.”** Sai: ứng dụng vẫn cần cấu hình trust/SP/IdP để xác minh.
5. **“Chỉ dùng Response.Issuer là đủ với multi-tenant.”** Sai: cùng issuer có thể map nhiều registration, Response trước validation chưa đáng tin.
6. **“Nếu converter tìm được request trong HttpSession thì bỏ InResponseTo validation.”** Sai: request lưu là dữ kiện để **kiểm tra correlation**, không thay thế correlation.
7. **“Chỉ cần đổi loginProcessingUrl, không cần đổi ACS metadata.”** Sai: IdP cần gửi Response tới đúng URL và SP phải xác minh recipient/destination.
8. **“Muốn mọi IdP đều hoạt động thì thử tất cả cert đến khi verify được.”** Sai: rủi ro nhầm trust tenant; phải dùng policy đăng ký và kiểm chứng đúng đối tác.
9. **“Có custom converter là có thể return Authentication đã xác thực.”** Sai: converter không nên tự xác nhận Response chưa được provider validate.
10. **“IdP-initiated luôn có InResponseTo.”** Sai: không có AuthnRequest gốc; cần policy riêng và phòng login CSRF/replay.
11. **“Spring Security phiên bản nào cũng có cùng lớp/provider.”** Sai: API, package OpenSAML và khả năng customization thay đổi giữa 6.x và 7.x; kiểm tra javadoc đúng dependency.
12. **“Giải quyết không tìm được registration bằng cách tắt signature validation.”** Sai: mất bảo mật, phải sửa route/repository/correlation/configuration.

## 16. Câu hỏi ôn tập

**1. Vì sao converter phải chọn RelyingPartyRegistration trước khi xác minh Response?**  
Vì provider cần biết **IdP issuer được kỳ vọng, verification certificates, SP entityId, ACS và các chính sách** để xác minh Response theo đúng đối tác.

**2. Converter đã tạo Saml2AuthenticationToken thì user được coi là đã đăng nhập chưa?**  
**Chưa.** Đó là token chưa xác thực; AuthenticationManager/OpenSAML provider kiểm SAMLResponse/Assertion rồi mới có Saml2Authentication hợp lệ.

**3. Một Response ở /login/saml2/sso/corp nhưng Issuer thuộc partner. Có nên cho đăng nhập vì route hợp lệ?**  
**Không.** Route chỉ chọn cấu hình; issuer/chữ ký/audience/destination phải khớp registration được tin cậy.

**4. Hai registration cùng IdP issuer, callback không có registrationId, không có AuthnRequest đã lưu. Issuer fallback có đủ không?**  
**Không.** Cần ngữ cảnh lựa chọn duy nhất hoặc một resolver an toàn; không chọn tùy tiện.

**5. Mất HttpSession sau MFA làm SP không tìm được AuthnRequest. Hành động đúng?**  
Kiểm tra **SameSite, Secure, domain, timeout, proxy, session cluster và request repository**. Không bỏ InResponseTo validation.

**6. Có nên viết custom AuthenticationConverter khi hai registration khác nhau và URL mặc định đã hoạt động?**  
Thường **không cần**. Converter mặc định xử lý trường hợp nhiều registration với URL và request context bình thường; tùy biến chỉ khi yêu cầu cụ thể không được hỗ trợ.

**7. IdP-initiated unsolicited Response cần điều gì ngoài việc map issuer?**  
Phải có **chính sách cho phép rõ ràng** và tất cả validation chữ ký, issuer, recipient, audience, thời gian, chống replay/login CSRF; không có request đã lưu thì phải thiết kế rủi ro riêng.

## 17. Nguồn tham khảo chính thức

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML Web Browser SSO, Saml2WebSsoAuthenticationFilter, converter và authentication provider.
2. [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): tùy biến ACS, RelyingPartyRegistration lookup, AuthenticationConverter, validation và mapping principal.
3. [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): Saml2AuthenticationRequestRepository, HttpSession, RelayState, các rủi ro khi lưu request trong cache.
4. [Spring Security Javadoc – Saml2AuthenticationTokenConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html): constructor với RelyingPartyRegistrationResolver, convert và authentication request repository. **Xem đúng version 6.x khi triển khai Boot 3.x.**
5. [Spring Security Javadoc – DefaultRelyingPartyRegistrationResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/DefaultRelyingPartyRegistrationResolver.html): resolve registration từ request, registrationId và template URLs.
6. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): yêu cầu tương quan AuthnRequest/Response, issuer/audience/destination/recipient của Web Browser SSO.

**Ghi nhớ:** **Saml2AuthenticationTokenConverter chọn cấu hình đối tác và tạo token chưa xác thực; AuthenticationManager/OpenSAML provider xác minh SAMLResponse bằng chính cấu hình đó.** Trong hệ thống nhiều IdP/tenant, **AuthnRequest đã lưu, registrationId ở ACS và Response.Issuer** là những tín hiệu có mục đích khác nhau; không biến bất kỳ tín hiệu chưa được xác minh nào thành bằng chứng danh tính.
