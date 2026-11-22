# RelyingPartyRegistrationRepository và InMemoryRelyingPartyRegistrationRepository trong Spring Security SAML 2.0

**RelyingPartyRegistrationRepository** là interface mà Spring Security dùng để tìm cấu hình liên kết SAML 2.0 của một ứng dụng **Relying Party (RP) / Service Provider (SP)** với **Asserting Party (AP) / Identity Provider (IdP)**. **InMemoryRelyingPartyRegistrationRepository** là triển khai phổ biến, giữ một hoặc nhiều cấu hình `RelyingPartyRegistration` trong bộ nhớ.

Nếu một ứng dụng phải đăng nhập qua IdP doanh nghiệp, Spring Security cần biết **IdP nào được tin cậy, URL SSO ở đâu, chứng thư nào xác minh chữ ký, SP Entity ID là gì, ACS nhận SAMLResponse ở đâu**. Những thông tin này nằm trong `RelyingPartyRegistration`; repository giúp các bộ lọc đăng nhập và thành phần liên quan tìm đúng registration bằng `registrationId`.

**Ý chính cần nhớ:** repository quản lý **cấu hình tin cậy cho cặp SP–IdP**, không phải kho người dùng, không giữ mật khẩu, không lưu phiên đăng nhập, không thực hiện authorization và không trực tiếp xác minh SAML assertions.

## 1. Ba khái niệm: Registration, Repository, InMemory Repository

| Thành phần | Loại | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| `RelyingPartyRegistration` | Class dữ liệu cấu hình | Diễn tả một cặp RP/SP và AP/IdP, từ định danh đến endpoint và credentials | Kết nối Portal với IdP công ty |
| `RelyingPartyRegistrationRepository` | Interface | Tra cứu `RelyingPartyRegistration` theo khóa | `findByRegistrationId("corp")` |
| `InMemoryRelyingPartyRegistrationRepository` | Class triển khai | Lưu các registration khi khởi tạo và cung cấp lookup/iteration | Hai registrations `corp`, `partner` |
| `IterableRelyingPartyRegistrationRepository` | Interface mở rộng | Cho phép duyệt toàn bộ registrations | Dùng cho metadata tổng hợp hoặc trang chọn IdP |
| `RelyingPartyRegistrations` | Utility class | Hỗ trợ tạo builder từ SAML IdP metadata | `fromMetadataLocation(...)` |

Nhìn từ góc độ dependency:

~~~text
SAML login components
         |
         v
RelyingPartyRegistrationRepository (interface)
         |
         +-----------------------------+
         |                             |
         v                             v
InMemoryRelyingParty...       Custom / caching repository
         |                             |
         v                             v
RelyingPartyRegistration(s)   RelyingPartyRegistration(s)
         |
         v
SP metadata + IdP metadata + X.509 credentials
~~~

Tách interface khỏi implementation cho phép dùng **InMemory** lúc cấu hình ít thay đổi, hoặc chuyển sang repository tùy chỉnh khi cần nhiều tenant hay cập nhật metadata động, trong khi phần xử lý login phụ thuộc chủ yếu vào hợp đồng tra cứu.

## 2. RelyingPartyRegistration thật sự chứa gì?

Mỗi đối tượng đại diện một **cặp RP–AP** có thể dùng trong SAML Web Browser SSO. Để tạo một registration, SP cần thông tin về **mình** và thông tin đáng tin cậy về **IdP**:

| Bên | Thuộc tính/metadata | Mục đích |
| --- | --- | --- |
| SP | `registrationId` | Khóa nội bộ để chọn registration, ví dụ `corp` |
| SP | `entityId` | Entity ID mà IdP nhận diện trong SAML |
| SP | `assertionConsumerServiceLocation` | URL nhận SAML Response tại SP |
| SP | `signingX509Credentials` | Private key và certificate mà SP dùng để ký khi cần |
| SP | `decryptionX509Credentials` | Credentials để giải mã SAML assertions được IdP mã hóa |
| IdP | `assertingPartyMetadata(...).entityId(...)` | Định danh asserting party/issuer đáng tin cậy |
| IdP | `singleSignOnServiceLocation` và binding | URL/cách gửi AuthnRequest |
| IdP | `verificationX509Credentials` | Chứng thư công khai dùng để kiểm chứng chữ ký phía IdP |
| Hai bên | Signing requirements, logout endpoints, NameID format... | Quy tắc giao thức đã thỏa thuận |

**Đặc biệt dễ nhầm giữa ba ID:**

- **`registrationId`** là nhãn nội bộ do SP chọn cho cặp registration, chẳng hạn `corp`. Giá trị này thường xuất hiện trong URL đăng nhập mặc định.
- **SP `entityId`** là định danh trong metadata và thông điệp SAML để IdP biết SP nào đang yêu cầu xác thực.
- **IdP `entityId`** là định danh của hệ thống xác thực được SP tin cậy, thường dùng khi kiểm tra issuer.

Chúng **không buộc phải bằng nhau**. Ví dụ:

| registrationId | SP entityId | IdP entityId |
| --- | --- | --- |
| `corp` | `https://portal.example.test/saml/sp` | `https://idp.example.test/entity` |
| `partner` | `https://portal.example.test/saml/partner` | `https://login.partner.example.test/idp` |

Nếu IdP trả Response từ issuer đã biết nhưng gửi đến ACS/recipient của registration khác, việc chỉ so khớp email hoặc một issuer không đủ để cho đăng nhập. Chọn đúng registration là một phần của bảo vệ tenant và quan hệ tin cậy.

## 3. Vai trò repository trong luồng SAML2 Web Browser SSO

~~~text
(1) Browser                  (2) Spring Security SP
    GET /private  ------------->  Authorization yêu cầu login
                                         |
                                         v
                               RelyingPartyRegistrationRepository
                                         |
                          findByRegistrationId("corp")
                                         |
                                         v
                               RelyingPartyRegistration
                         IdP SSO URL, SP entityId, ACS, cert...
                                         |
                                         v
(3) Browser  <-------------  Tạo SAML AuthnRequest
       |                                 
       +---------> (4) IdP xác thực người dùng
                          |
                          v
                    SAML Response
                          |
                          v
(5) Browser ----------> (6) SP / ACS
                              |
                              v
                  Resolve registration phù hợp
                              |
                     Xác minh SAML response
                              |
                              v
                      Spring Authentication
                              |
                      Authorization nghiệp vụ
~~~

Khi browser bắt đầu `/saml2/authenticate/corp`, Spring thường có thể tìm registration dựa trên `corp`. Trong lúc nhận SAML Response, cơ chế resolve có thể dựa trên **AuthnRequest đã lưu**, thông tin issuer hoặc một chiến lược resolver tùy trường hợp. Vì vậy **không được giả định tất cả callback chỉ lookup bằng path**.

Repository cung cấp **cấu hình**. Các filter, authentication provider và thư viện SAML bên dưới chịu trách nhiệm xây/đọc message và kiểm chứng chữ ký, điều kiện thời gian, recipient, audience và ràng buộc request phù hợp.

### Các endpoint mặc định thường gặp

| Endpoint | Vai trò |
| --- | --- |
| `/saml2/authenticate/{registrationId}` | Tạo AuthnRequest cho một registration |
| `/login/saml2/sso/{registrationId}` | ACS xử lý SAML Response với cấu hình login processing mặc định |
| `/saml2/metadata/{registrationId}` | Xuất SP metadata nếu bật `saml2Metadata` |
| `/saml2/metadata` | Có thể xuất metadata cho nhiều registrations nếu có khả năng duyệt |
| `/saml2/service-provider-metadata/{registrationId}` | URL metadata tương thích được Spring Security hỗ trợ |

Ngoài các đường dẫn mang registrationId, phiên bản hiện hành còn hỗ trợ một số endpoint không mang id; logic resolve từ ngữ cảnh đã xác thực, request hoặc issuer phải được đánh giá cẩn thận. **Tự đổi ACS URL** cần đồng bộ cả `assertionConsumerServiceLocation`, filter login processing và cấu hình IdP.

## 4. Hợp đồng RelyingPartyRegistrationRepository

Package:

~~~java
org.springframework.security.saml2.provider.service.registration
~~~

Phương thức cốt lõi của interface:

~~~java
RelyingPartyRegistration findByRegistrationId(String registrationId);
~~~

**Hành vi:** tìm một `RelyingPartyRegistration` theo `registrationId`; trả về **null** nếu không tìm được. Đây không phải API dùng để tìm người dùng, kiểm tra login hoặc phân quyền.

Ví dụ cấu hình có `corp` và `partner`:

~~~text
repository:
  "corp"      => registration SP + IdP doanh nghiệp
  "partner"   => registration SP + IdP đối tác

findByRegistrationId("corp")      => registration doanh nghiệp
findByRegistrationId("missing")   => null
~~~

Trong một số phiên bản Spring Security 6.x/7.x, interface còn hỗ trợ `findUniqueByAssertingPartyEntityId(String entityId)`: tra cứu registration duy nhất ứng với IdP entityId, hoặc trả null nếu không duy nhất/không tồn tại. **Nếu hai registrations cùng dùng một issuer**, không thể chỉ dựa vào issuer để tự chọn ngẫu nhiên một registration.

`RelyingPartyRegistrationRepository` không bắt buộc là Iterable. Khi các chức năng như trang chọn IdP, metadata đa registration cần liệt kê tập cấu hình, triển khai `IterableRelyingPartyRegistrationRepository` hoặc đồng thời hỗ trợ `Iterable<RelyingPartyRegistration>` tùy API phiên bản. `InMemoryRelyingPartyRegistrationRepository` đã hỗ trợ iteration.

### Ví dụ sử dụng ở service

Giả sử đã inject `RelyingPartyRegistrationRepository repository`:

~~~java
RelyingPartyRegistration registration =
        repository.findByRegistrationId("corp");

if (registration == null) {
    throw new IllegalStateException("Unknown registration: corp");
}

String chosenRegistrationId = registration.getRegistrationId();
~~~

Đây là **đoạn mã nằm trong method của ứng dụng**, sử dụng biến `repository` đã có; không phải Java standalone có `main`. Với cấu hình `corp`, `chosenRegistrationId` bằng chuỗi `corp`. Sự tồn tại của registration **không chứng minh người dùng đã xác thực**.

## 5. InMemoryRelyingPartyRegistrationRepository hoạt động như thế nào?

Class:

~~~java
org.springframework.security.saml2.provider.service.registration
    .InMemoryRelyingPartyRegistrationRepository
~~~

Đường dẫn package phía trên được xuống dòng chỉ để đọc; import Java thật phải dùng tên package một dòng. Class có các constructor nhận **varargs** hoặc **Collection** `RelyingPartyRegistration`:

~~~java
new InMemoryRelyingPartyRegistrationRepository(corp);
new InMemoryRelyingPartyRegistrationRepository(corp, partner);
new InMemoryRelyingPartyRegistrationRepository(registrations);
~~~

Trong ví dụ cuối, `registrations` là `Collection<RelyingPartyRegistration>`. Triển khai hỗ trợ:

- `findByRegistrationId(String)` để lấy registration theo ID.
- `findUniqueByAssertingPartyEntityId(String)` khi có duy nhất cặp tương ứng.
- `iterator()` để duyệt những registration đã cấu hình.

**Ưu điểm:** ít mã, lookup gọn, không cần một database chỉ để chứa tập cấu hình SAML, dễ đăng ký bean, hỗ trợ nhiều IdP và hoạt động tốt khi tập registration ổn định.

**Giới hạn:** đây là bộ cấu hình lưu trong process. InMemory **không tự lưu xuống database**, **không tự thêm tenant** khi người dùng đăng ký, **không tự polling metadata IdP** và **không tự xoay chứng thư** sau khi một registration đã được xây. Khi restart, ứng dụng tạo lại repository từ bean/properties. Khi IdP đổi khóa hoặc SSO URL, cần cơ chế refresh/triển khai mới có kiểm soát.

“Có chữ InMemory” không có nghĩa chỉ được dùng cho demo; production với một hoặc vài IdP ít thay đổi vẫn có thể sử dụng, miễn là đã quản lý key rotation, monitoring và thay đổi cấu hình.

## 6. Ví dụ Java 17+: cấu hình một registration qua metadata IdP

Mục tiêu: một ứng dụng **Spring Boot 3.x / Spring Security 6.x, Servlet MVC** đăng nhập qua IdP doanh nghiệp có `registrationId=corp`, dùng repository InMemory do mình khai báo.

Điều kiện trước khi chạy:

1. Dự án có Spring Boot Web/Security và module **`spring-security-saml2-service-provider`** tương thích.
2. Có metadata IdP thật được quản trị cung cấp, ví dụ `src/main/resources/saml/corp-idp-metadata.xml`.
3. SP đã được đăng ký ở IdP với **SP Entity ID** và **ACS** khớp; phải cấp credentials ký/giải mã nếu giao thức và IdP yêu cầu.
4. Ví dụ tối thiểu chưa cung cấp SP private key ký AuthnRequest. Chỉ dùng nguyên mẫu khi IdP **không bắt buộc SP ký AuthnRequest** và không cần cấu hình decryption riêng.
5. Mọi giá trị `example.test` khác trong bài chỉ minh họa; không đại diện cho nhà cung cấp đang hoạt động.

Tệp: **src/main/java/com/example/security/SamlSecurityConfig.java**

~~~java
package com.example.security;

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
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
            .registrationId("corp")
            .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
            .assertionConsumerServiceLocation(
                "{baseUrl}/login/saml2/sso/{registrationId}")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích từng phần:**

1. **`fromMetadataLocation(...)`** đọc IdP metadata tại `classpath:`, `file:` hoặc endpoint HTTPS được tin cậy và tạo `RelyingPartyRegistration.Builder`. Metadata IdP thường chỉ mô tả IdP; cấu hình SP như private key ký AuthnRequest có thể phải bổ sung riêng.
2. **`.registrationId("corp")`** thiết lập khóa ổn định dùng để tra cứu trong repository và ở endpoint đăng nhập `/saml2/authenticate/corp`.
3. **`.entityId(...)`** thiết lập RP/SP Entity ID mà IdP dùng để nhận diện ứng dụng. Placeholder `{baseUrl}` và `{registrationId}` được Spring Security hỗ trợ; IdP phải thấy một URL/ID cuối cùng khớp cấu hình SP.
4. **`.assertionConsumerServiceLocation(...)`** xác định endpoint nhận SAMLResponse. Đường dẫn mặc định trong ví dụ phù hợp với `Saml2WebSsoAuthenticationFilter`.
5. **`new InMemoryRelyingPartyRegistrationRepository(corp)`** lưu registration trong process. Spring Security lấy bean `RelyingPartyRegistrationRepository` để tra cứu cấu hình.
6. **`.saml2Login(Customizer.withDefaults())`** bật luồng đăng nhập SAML. **`.saml2Metadata(Customizer.withDefaults())`** bật endpoint công bố metadata SP để IdP sử dụng khi đăng ký.

**Đây là class cấu hình thuộc một dự án Spring Boot**, không phải chương trình độc lập biên dịch/chạy bằng `javac`/`java` không có dependency. Không có stdout cố định. Mã Java nêu trên dùng các API có trong Spring Security 6.x; khi ứng dụng nâng cấp major version, phải kiểm tra lại API và đặc biệt các thay đổi OpenSAML/deprecation.

### Không nhầm metadata đầu vào và metadata đầu ra

- **Đầu vào:** `corp-idp-metadata.xml` chứa thông tin **IdP** (entity ID, SSO endpoint, certificate/binding); builder đọc nó để biết IdP nào được tin.
- **Đầu ra:** `/saml2/metadata/corp` có thể xuất **SP metadata** dựa trên registration; giúp quản trị IdP xác nhận entity ID, ACS và certificate SP nếu có.
- **Không tự tạo file IdP metadata giả** với placeholder certificate rồi sử dụng cho login thật. Nếu dùng URL metadata phải xác minh nguồn, TLS và chiến lược cập nhật.

## 7. Tích hợp nhiều IdP trong cùng một repository

Ứng dụng Portal của công ty có IdP nội bộ và IdP đối tác. Thay **method bean repository** ở mục 6 bằng:

~~~java
@Bean
RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
    RelyingPartyRegistration corp = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
        .registrationId("corp")
        .build();

    RelyingPartyRegistration partner = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/partner-idp-metadata.xml")
        .registrationId("partner")
        .build();

    return new InMemoryRelyingPartyRegistrationRepository(corp, partner);
}
~~~

Đoạn code này **dùng các import, package và class ở mục 6** và được dùng **thay thế** method bean cũ; không được tạo hai bean cùng kiểu mà không xác định rõ bean Spring Security nên sử dụng.

Khi cấu hình xong:

| URL | Chọn cấu hình |
| --- | --- |
| `/saml2/authenticate/corp` | IdP doanh nghiệp |
| `/saml2/authenticate/partner` | IdP đối tác |
| `/login/saml2/sso/corp` | Callback theo cấu hình corp |
| `/login/saml2/sso/partner` | Callback theo cấu hình partner |
| `/saml2/metadata/corp` | SP metadata của cặp corp |
| `/saml2/metadata/partner` | SP metadata của cặp partner |

Trong thực tế, Spring Security có thể resolve SAML Response qua ngữ cảnh AuthnRequest hoặc issuer, không nhất thiết bắt buộc callback luôn có registrationId ở path. **Không tự nhận một Response của corp dưới registration partner**; phải giữ ràng buộc tenant, request state, audience, recipient và chữ ký chính xác.

Với nhiều registration, trang login mặc định có thể hiện lựa chọn IdP nếu repository hỗ trợ iteration. `InMemoryRelyingPartyRegistrationRepository` đáp ứng yêu cầu này.

### Một IdP với nhiều registration

Khi nhiều tenant hoặc môi trường **cùng một IdP entityId**, tìm “registration duy nhất theo issuer” có thể trở nên mơ hồ. `findUniqueByAssertingPartyEntityId` chỉ phù hợp khi có đúng một cặp cho issuer đó; nếu nhiều cặp, cần quy tắc resolve theo request, tenant đáng tin và context của SAML authentication. Việc lấy email/chọn tenant tùy ý trước khi kiểm chứng assertion có thể dẫn đến cross-tenant login.

## 8. Cấu hình bằng Spring Boot properties thay cho @Bean

Với cấu hình chuẩn, Spring Boot có khả năng tự tạo `RelyingPartyRegistrationRepository` từ properties SAML2 nếu dependency và điều kiện auto-configuration phù hợp. Ví dụ Spring Boot 3.x:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp-metadata.xml"
~~~

**Chú ý:** đây là **phương án thay thế** cho bean repository tự khai báo. Khóa **`corp`** được Spring Boot dùng làm `registrationId`. Cần xem lại cú pháp property theo phiên bản Spring Boot đang sử dụng và cấu hình SP signing/decryption credentials nếu cần.

| Tiêu chí | Dùng `application.yml` | Dùng `@Bean` với InMemory |
| --- | --- | --- |
| Một IdP, cấu hình đơn giản | Gọn và dễ quản lý | Gọn nhưng cần mã Java |
| Nhiều IdP | Nhiều key ở `registration` | Nhiều đối tượng registration |
| Đọc metadata IdP | Qua property `metadata-uri` | Qua `fromMetadataLocation` hoặc builder thủ công |
| Thay đổi cấu hình khi đang chạy | Không tự xảy ra chỉ do sửa file | InMemory không tự refresh |
| Logic khởi tạo tùy chỉnh | Khả năng bị giới hạn bởi property binding | Dễ kết hợp cấu hình từ hệ thống riêng |
| Integration test & review | Kiểm tra YAML và property binding | Kiểm tra Java factory/bean |

Nếu công bố **bean repository của riêng mình**, Spring Boot thường không tạo bean mặc định tương tự từ properties nữa. Vì vậy không cấu hình cả hai nguồn rồi giả định Spring sẽ tự hợp nhất chúng. Hãy xác định nơi lấy metadata và owner của một tập registration để tránh xung đột.

## 9. Tạo registration bằng metadata hay cấu hình thủ công?

### Lựa chọn A: IdP cung cấp metadata XML đáng tin cậy

~~~java
RelyingPartyRegistration corp = RelyingPartyRegistrations
    .fromMetadataLocation("https://idp.example.test/metadata")
    .registrationId("corp")
    .build();
~~~

Mẫu dùng HTTPs metadata như trên đòi endpoint thực sự truy cập được, certificate và XML hợp lệ. `example.test` chỉ là domain giả; không chạy thực tế cho tới khi thay bằng IdP thật. Utility giúp lấy issuer, endpoint SSO và verification certificates từ metadata, giảm việc sao chép thủ công thông số.

### Lựa chọn B: Cấu hình asserting party thủ công

Trong trường hợp IdP không cấp metadata, `RelyingPartyRegistration.withRegistrationId(...)` cho phép khai báo issuer, SSO URL, binding và **`verificationX509Credentials`** từ certificate tin cậy. Tuy nhiên, code cấu hình sẽ dài hơn và phải quản lý chính xác dữ liệu PKI.

Mảnh code minh họa **bên trong builder**:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistration
    .withRegistrationId("corp")
    .assertingPartyMetadata(party -> party
        .entityId("https://idp.example.test/entity")
        .singleSignOnServiceLocation("https://idp.example.test/sso")
        .wantAuthnRequestsSigned(false)
        .verificationX509Credentials(credentials ->
            credentials.add(idpVerificationCredential)))
    .build();
~~~

**Lưu ý:** biến `idpVerificationCredential` là `Saml2X509Credential` được tạo từ **chứng thư X.509 hợp lệ của IdP** theo quy trình tin cậy của tổ chức. Vì ví dụ không cung cấp chứng thư thực, đây là **đoạn tích hợp minh họa** và không phải chương trình Java có thể chạy độc lập; phải thay bằng cấu hình thực tế. Giá trị `wantAuthnRequestsSigned(false)` chỉ phù hợp khi IdP thực sự không yêu cầu signed requests.

Metadata của IdP **không tự cấp** SP private key. Nếu IdP bắt buộc ký AuthnRequest, phải cấu hình SP signing credentials; nếu IdP mã hóa assertion, phải cấp SP decryption credentials. Không nhầm **IdP verification certificate** với **SP signing private key**.

## 10. Vì sao Iterable quan trọng với metadata và trang chọn IdP?

Interface `RelyingPartyRegistrationRepository` chủ yếu giải quyết **lookup**. Một số tiện ích cần **enumeration**:

1. Trang login mặc định cần biết ứng dụng có những asserting parties nào để hiển thị lựa chọn khi có nhiều IdP.
2. Metadata SP xuất toàn bộ registration qua endpoint không có id cần duyệt danh sách.
3. Công cụ kiểm tra cấu hình/monitoring có thể cần thống kê các registrations đang được khai báo.

`InMemoryRelyingPartyRegistrationRepository` là một triển khai **`IterableRelyingPartyRegistrationRepository`** và có `iterator()`. Một custom repository chỉ implements `RelyingPartyRegistrationRepository` sẽ **không tự có** khả năng duyệt; khi cần listing, nên chọn interface/adapter có Iterable theo tài liệu của phiên bản.

**Không nhầm** iteration với tính năng tự phát hiện IdP trên Internet. Danh sách chỉ bao gồm những registration mà ứng dụng đã cấu hình, có nguồn trust được cấp phép và đi qua chính sách xác minh phù hợp.

## 11. Hạn chế của InMemory: cập nhật cấu hình và key rotation

Ví dụ khi tạo bean:

~~~text
Startup:
  Đọc IdP metadata ở version A
       |
       v
  Tạo RelyingPartyRegistration
       |
       v
  Lưu vào InMemory repository
       |
       v
  Login trong quá trình ứng dụng chạy

IdP xoay certificate hoặc đổi SSO endpoint sang version B
       |
       v
  Repository cũ KHÔNG tự biết version B
       |
       v
  Có thể phát sinh login lỗi nếu không cập nhật
~~~

Việc `fromMetadataLocation` đọc URL HTTPS lúc startup **không chứng minh** rằng nó sẽ tự làm mới ở mỗi lần đăng nhập. Nhiều vấn đề phát sinh khi IdP xoay chứng thư, đổi endpoint SSO, thay đổi binding hoặc ngừng hỗ trợ một cert cũ.

Ba chiến lược phổ biến:

- **Tĩnh + deploy có kiểm soát:** lưu metadata/cert được xác minh trong cấu hình, cập nhật deployment khi IdP chuẩn bị rotation. Phù hợp ít IdP và có quy trình release rõ ràng.
- **Tái tạo registration từ metadata đáng tin:** theo dõi IdP metadata rồi xây lại registrations với cơ chế atomic/configuration update phù hợp, không tự chỉnh mutable map ở nơi Spring Security đang đọc.
- **Metadata refresh/caching:** ở phiên bản có hỗ trợ, dùng `CachingRelyingPartyRegistrationRepository` với supplier từ repository/metadata và CacheManager; hoặc xây repository tùy chỉnh dựa trên metadata repository có refresh được cung cấp bởi thư viện. Phải quản lý TTL, cache invalidation, lỗi mạng và khả năng fallback an toàn.

Đừng nhầm **cache** với đồng bộ mọi loại state: cache chỉ giúp điều tiết việc nạp lại metadata khi được thiết kế đúng. **Không tự động cập nhật user session hoặc thu hồi authorization**. Khi IdP thay certificate, tuyệt đối không tắt chữ ký SAML để giảm lỗi tạm thời.

### Cần bảo vệ metadata URL

Metadata SAML chứa thông tin tin cậy (issuer, endpoints, certificates). URL nhập tự do từ khách hàng/tenant không được đưa thẳng vào `fromMetadataLocation` khi chưa kiểm soát danh sách nguồn, network access, TLS và chính sách phê duyệt. Nếu không, ứng dụng có nguy cơ đọc nguồn giả hoặc gây SSRF ở các hệ thống cấu hình động.

## 12. Metadata SP và ràng buộc với reverse proxy

SP metadata thường được IdP sử dụng để ghi nhận **SP Entity ID, ACS URL và chứng thư của SP**. Khi bật:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Spring Security có thể công bố metadata tại `/saml2/metadata`, `/saml2/metadata/{registrationId}` và các đường dẫn tương thích được hỗ trợ.

Một tình huống thường gặp:

~~~text
Browser: https://portal.example.test
              |
       Reverse Proxy HTTPS
              |
       Spring app: http://10.0.0.5:8080
~~~

Nếu `{baseUrl}` bị xác định thành `http://10.0.0.5:8080` do forwarded headers sai, metadata có thể phát ra **ACS và SP Entity ID không khớp** URL bên ngoài mà IdP đã đăng ký. Khi đó IdP có thể từ chối yêu cầu hoặc gửi response tới địa chỉ không phù hợp.

Giải pháp gồm xác định URL công khai, cấu hình reverse proxy/forwarded headers đúng cơ chế tin cậy và kiểm tra metadata thực tế ở môi trường production. Đừng chấp nhận mọi `X-Forwarded-Host` từ Internet nếu không có proxy đáng tin bảo vệ, vì nó ảnh hưởng đến URL được sinh trong các thông điệp.

**Nguyên tắc nhất quán:** những giá trị entityId/ACS mà IdP đã đăng ký phải đúng với cấu hình repository và endpoint thực tế của SP.

## 13. Bảo mật khi sử dụng repository

`InMemoryRelyingPartyRegistrationRepository` không trực tiếp kiểm tra authentication của user. Khi đăng nhập, các thành phần Spring Security dùng registration để kiểm tra SAML Response và tạo `Authentication`. Cần đảm bảo:

1. **Đúng IdP issuer:** chỉ chấp nhận asserting parties được cho phép; đừng dựa vào email, query string hoặc tên người dùng để bỏ qua issuer verification.
2. **Đúng certificate trust:** kiểm tra chữ ký bằng verification credentials từ metadata/chứng thư đã được phê duyệt. Không dùng certificate không xác minh nguồn.
3. **Đúng audience và recipient:** một Response hợp lệ về chữ ký nhưng dành cho SP khác không được chấp nhận.
4. **Đúng thời hạn và request binding:** kiểm tra các trường `NotBefore`, `NotOnOrAfter`, `InResponseTo`, subject confirmation và replay khi áp dụng.
5. **SP private keys riêng:** ký AuthnRequest và giải mã assertion cần private keys thuộc SP, được lưu an toàn, không đưa vào log/YAML công khai.
6. **Tenant isolation:** tránh trường hợp registration của IdP A được sử dụng khi xử lý Response cho IdP B hoặc môi trường khác.
7. **Phân quyền độc lập:** `Saml2AuthenticatedPrincipal` là bằng chứng authentication; quyền truy cập admin, dữ liệu và resource cần kiểm tra authorization theo policy.
8. **Session và logout riêng:** repository lưu trust config; session SP, cookie, Single Logout và lifecycle account là các trách nhiệm khác.
9. **Kế hoạch certificate rotation:** theo dõi hạn, thời điểm triển khai metadata mới và giai đoạn chuyển giao giữa cert cũ/mới khi IdP hỗ trợ.
10. **Giám sát hợp lý:** theo dõi lỗi SAML và metadata, nhưng không ghi toàn bộ SAML assertions hoặc private keys/PII vào log.

**Ví dụ sai:** Dev lấy IdP entityId từ request chưa xác minh, tìm một registration cùng issuer, rồi cho phép đăng nhập vào tenant do query parameter lựa chọn. Điều này có thể vượt ranh giới tenant. **Cách đúng:** dùng state của AuthnRequest, id/tenant đã được ràng buộc và xác minh thông điệp theo đúng cặp SP–IdP.

## 14. Chẩn đoán lỗi trong ứng dụng

| Vấn đề | Nguyên nhân có thể | Kiểm tra/giải pháp |
| --- | --- | --- |
| `findByRegistrationId("corp")` trả null | Sai key, bean chứa tập registration khác | Xác nhận method bean, registrationId và endpoint được gọi |
| Startup báo không đọc được metadata | Đường dẫn classpath sai, HTTPS lỗi, XML không hợp lệ | Kiểm tra resource trong `src/main/resources`, trust nguồn và log startup |
| Browser chuyển đến IdP không đúng | Registration hoặc SSO URL/binding không đúng | Kiểm tra URL `/saml2/authenticate/{id}` và metadata IdP |
| IdP báo không nhận diện SP | SP Entity ID chưa đăng ký hoặc không khớp | So metadata SP với cấu hình IdP |
| IdP từ chối unsigned AuthnRequest | IdP yêu cầu SP signing | Cấu hình signing credentials; kiểm tra yêu cầu của IdP |
| SAMLResponse đến nơi nhưng Spring báo validation failure | Signature, issuer, recipient, audience hoặc thời gian sai | Đối chiếu metadata và debug đã ẩn thông tin nhạy cảm |
| ACS trả `404` hoặc filter không chạy | URL callback không khớp login processing URL | Đồng bộ ACS builder, `saml2Login` và IdP |
| Sau rotation IdP, chữ ký không còn hợp lệ | Repository giữ chứng thư cũ | Làm mới metadata/chứng thư bằng quy trình an toàn |
| `/saml2/metadata` không trả danh sách | Chưa bật metadata DSL hoặc repository không Iterable | Bật `saml2Metadata`, dùng implementation iterable |
| User đăng nhập thành công nhưng nhận `403` | Thiếu authority hoặc quyền nghiệp vụ | Kiểm tra mapping principal/attributes và authorization |
| Sai tenant khi nhiều registration chung issuer | Lookup theo issuer không duy nhất | Thiết kế resolver có state/registrationId đáng tin |
| Chạy sau proxy sinh ACS HTTP nội bộ | Sai external base URL hoặc forwarded headers | Chuẩn hóa HTTPS public URL và proxy trust |

Không nên “sửa” lỗi bằng cách bỏ kiểm tra chữ ký, audience, recipient, thời gian hoặc cho phép mọi tenant. Những lỗi đó thường chỉ ra cấu hình trust/registration đang không tương thích.

## 15. Một vài tình huống lựa chọn implementation

### A. Một IdP công ty, cấu hình ổn định

Ví dụ intranet Portal chỉ đăng nhập qua IdP doanh nghiệp. Spring Boot properties hoặc bean InMemory là lựa chọn đơn giản. Nên kiểm thử trước ngày xoay chứng thư và lên lịch deploy metadata mới.

### B. Ba đối tác B2B

Portal phục vụ ba tổ chức đối tác. Tạo ba `RelyingPartyRegistration` (mỗi registrationId rõ ràng), trả về một InMemory repository. Bắt buộc kiểm tra **tenant isolation** dù người dùng đã xác thực thành công qua IdP đối tác.

### C. Nhiều tenant tự thêm IdP khi chạy

Số tenant thay đổi thường xuyên; metadata, certificate và chính sách xác thực có thể được quản trị viên cập nhật. InMemory tạo một lần lúc startup không đủ linh hoạt. Hãy thiết kế custom repository hoặc cơ chế metadata refresh/cache đáng tin, kiểm soát quyền thay đổi cấu hình và xác minh nguồn IdP.

### D. Chuyển giữa staging và production

Không dùng chung SP Entity ID, ACS hoặc private key một cách tùy tiện. Mỗi môi trường nên có registration rõ ràng; đảm bảo URL công khai, metadata và cấu hình IdP đúng môi trường. Tránh hard-code một domain rồi dùng cùng bean trong cả staging/production.

### E. IdP thay chứng thư ký hàng quý

Nếu nhóm vận hành muốn không restart khi xoay chứng thư, cần cơ chế metadata repository refresh hoặc cache có TTL phù hợp, chấp nhận các khóa được phê duyệt trong giai đoạn chuyển giao. Kiểm thử failure mode khi IdP metadata endpoint không truy cập được; không nới lỏng verify signatures.

## 16. Checklist triển khai và QA

- [ ] Xác định mỗi cặp SP–IdP có `registrationId` ổn định, không đụng nhau.
- [ ] Có SP Entity ID, ACS, IdP Entity ID, SSO endpoint và binding đúng.
- [ ] Metadata IdP được lấy từ nguồn có thể kiểm chứng, chứa verification cert phù hợp.
- [ ] Có SP signing/decryption credentials nếu chính sách IdP hoặc giao thức yêu cầu.
- [ ] Chọn một nguồn cấu hình rõ ràng: Boot properties hoặc bean repository.
- [ ] Khi dùng InMemory, hiểu vòng đời cập nhật cấu hình sau startup.
- [ ] Với nhiều registration, kiểm thử request initiation và callback theo từng IdP, kể cả IdP issuer trùng.
- [ ] Nếu cần metadata tổng hợp/trang chọn IdP, repository hỗ trợ Iterable.
- [ ] Đã thử endpoint SSO, ACS và metadata thực tế ở môi trường có HTTPS/proxy.
- [ ] Có kế hoạch certificate rotation, metadata refresh, monitoring và xử lý lỗi an toàn.
- [ ] Không cho phép một cấu hình tenant dùng để xác thực response của tenant khác.
- [ ] Tách biệt authentication từ SAML với authorization theo role, tenant và tài nguyên.

## 17. Câu hỏi tự kiểm tra

**1. `RelyingPartyRegistrationRepository` lưu tài khoản hoặc mật khẩu người dùng không?**  
Không. Nó lưu **cấu hình SAML cho RP/AP**, không chứa dữ liệu đăng nhập cá nhân hay session.

**2. `registrationId="corp"` có buộc phải bằng SAML Entity ID?**  
Không. Registration ID là khóa nội bộ. SP Entity ID và IdP Entity ID là định danh protocol.

**3. `findByRegistrationId("missing")` trả về gì khi không tìm thấy?**  
Trả về **null** theo hợp đồng API.

**4. Một InMemory repository có thể chứa nhiều IdP?**  
Có. Dùng constructor varargs/Collection với nhiều `RelyingPartyRegistration`.

**5. Lấy metadata HTTPS ở startup có bảo đảm tự refresh khi IdP thay chứng thư?**  
Không. Phải thiết kế cập nhật/rebuild repository hoặc cơ chế metadata refresh/cache.

**6. Vì sao `IterableRelyingPartyRegistrationRepository` hữu ích?**  
Nó cho phép liệt kê registration, hỗ trợ một số chức năng như trang chọn IdP và metadata tổng hợp.

**7. IdP issuer giống nhau ở hai registrations có thể tự chọn một bằng issuer không?**  
Không an toàn nếu không phân biệt được duy nhất. Cần context của request/tenant đáng tin.

**8. Sau khi SAML login thành công, user có tự có quyền quản trị?**  
Không. Các kiểm tra authorization ở ứng dụng vẫn là bắt buộc.

**9. Có thể triển khai InMemory ở production không?**  
Có, nếu tập cấu hình ổn định và vận hành key rotation/metadata updates được kiểm soát.

**10. Tại sao SP signing key khác IdP verification certificate?**  
SP dùng **private key của mình** để ký (nếu cần); SP dùng **public certificate của IdP** để xác minh chữ ký thông điệp từ IdP.

## 18. Kết luận

**`RelyingPartyRegistrationRepository` là hợp đồng tra cứu registration của Spring Security SAML2; `InMemoryRelyingPartyRegistrationRepository` là implementation lưu các registration trong bộ nhớ và hỗ trợ iteration.** Dùng implementation này cho trường hợp một vài IdP và cấu hình tương đối tĩnh. Khi nhiều tenant thay đổi liên tục, cần lookup động, refresh metadata hoặc xoay chứng thư thường xuyên, cân nhắc repository/metadata layer được thiết kế riêng. Trong mọi trường hợp, giữ chính xác ranh giới **issuer – entity ID – ACS – certificate – audience – tenant**, và tách authentication khỏi authorization.

### Tài liệu chính thức

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security 6.5 API — `RelyingPartyRegistrationRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrationRepository.html
- Spring Security 6.5 API — `InMemoryRelyingPartyRegistrationRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/InMemoryRelyingPartyRegistrationRepository.html
- Spring Security 6.5 API — `RelyingPartyRegistrations`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html
