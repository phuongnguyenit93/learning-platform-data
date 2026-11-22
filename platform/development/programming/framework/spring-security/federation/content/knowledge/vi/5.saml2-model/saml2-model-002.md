# Entity ID của Service Provider và Identity Provider trong SAML 2.0

## 1. Mục tiêu và bối cảnh

Trong **SAML 2.0 federation**, một ứng dụng nghiệp vụ thường đóng vai **Service Provider (SP)**: ứng dụng cần biết nên tin nhà cung cấp danh tính nào. Hệ thống đăng nhập tập trung đóng vai **Identity Provider (IdP)**: hệ thống cần biết ứng dụng nào đang yêu cầu đăng nhập và được phép nhận kết quả xác thực.

SAML xác định mỗi bên bằng một **Entity ID**. Hai Entity ID là một phần của hợp đồng tin cậy giữa SP và IdP. Khi khai báo sai, cấu hình có thể trông hợp lệ và người dùng thậm chí đăng nhập thành công tại IdP, nhưng SP vẫn không thể chấp nhận SAML Response hoặc IdP không công nhận AuthnRequest.

Bài học này giải thích:

- Entity ID của SP và IdP là gì, khác nhau ở đâu và vì sao phải dùng giá trị chính xác.
- Entity ID xuất hiện tại đâu trong **SAML metadata, AuthnRequest, Response và Assertion**.
- Phân biệt Entity ID với **ACS URL, SSO URL, metadata URL, registrationId và NameID**.
- Cách đối chiếu cấu hình hai bên trong Spring Security SAML 2.0.
- Các ranh giới tin cậy, tình huống sai cấu hình, nguyên tắc đổi Entity ID và cách kiểm thử.

Ví dụ xuyên suốt sử dụng tên miền `example.test` và URN giả định để học cấu trúc, không đại diện một nhà cung cấp đang vận hành.

## 2. Entity ID là gì?

**Entity ID** là định danh của một **SAML entity** (một bên tham gia federation), thể hiện qua thuộc tính `entityID` trên phần tử metadata `<EntityDescriptor>`. Giá trị có dạng URI, chẳng hạn:

```text
SP Entity ID  = urn:example:shop:orders:sp
IdP Entity ID = https://idp.example.test/saml/issuer
```

Trong ví dụ:

- `urn:example:shop:orders:sp` biểu diễn **ứng dụng đặt hàng** khi nó tham gia SAML với tư cách SP.
- `https://idp.example.test/saml/issuer` biểu diễn **máy chủ danh tính** khi nó phát thông điệp hoặc assertion SAML.
- **Hai giá trị không phải hai tên của cùng một đối tượng**. Cần khai báo đúng mỗi vai trò.

Entity ID là **định danh logic**. Nó không tự động là địa chỉ HTTP mà trình duyệt phải gọi. Một Entity ID trông như URL có thể không truy cập được qua trình duyệt; URI dạng `urn:` càng không phải endpoint web. Dịch vụ thực sự gửi/nhận SAML message được khai báo **riêng** trong metadata bằng các `Location` và binding tương ứng.

Vì là định danh theo hợp đồng, SP và IdP phải thống nhất **chính xác chuỗi Entity ID**. Các khác biệt như dấu `/` cuối, đường dẫn, chữ hoa/thường, scheme hoặc tenant có thể khiến hai bên xem đó là các danh tính khác nhau. Không tự `trim`, đổi lowercase, bỏ slash hoặc viết lại một Entity ID đang được phía đối tác dùng.

### 2.1. Hai câu hỏi Entity ID trả lời

| Câu hỏi | Định danh liên quan | Ai kiểm tra? |
| --- | --- | --- |
| “AuthnRequest này do ứng dụng SP nào yêu cầu?” | **SP Entity ID** trong `AuthnRequest/Issuer` | IdP, đối chiếu ứng dụng đã đăng ký |
| “SAML Response/Assertion này do IdP nào phát hành?” | **IdP Entity ID** trong `Response/Issuer` và/hoặc `Assertion/Issuer` theo cấu trúc giao thức | SP, đối chiếu IdP đã tin cậy |
| “Assertion này dành cho SP nào?” | **SP Entity ID** trong `AudienceRestriction/Audience` | SP, kiểm tra audience |
| “Kết quả đăng nhập phải gửi tới địa chỉ nào?” | **ACS URL** của SP | IdP dùng để gửi; SP kiểm tra recipient/destination |
| “Người dùng đăng nhập là ai?” | `NameID` và/hoặc thuộc tính assertion đã xác minh | SP và hệ thống nghiệp vụ |
| “IdP có thể nhận yêu cầu ở đâu?” | **SSO endpoint URL** của IdP | SP dùng để gửi yêu cầu |

**Entity ID định danh hệ thống; NameID định danh chủ thể bên trong assertion.** Không dùng SP Entity ID/IdP Entity ID làm user ID hoặc thay thế cơ chế liên kết tài khoản người dùng.

## 3. Metadata: nơi công bố Entity ID và hợp đồng kỹ thuật

SAML metadata là tài liệu XML cho phép hai hệ thống mô tả vai trò, endpoint, binding, thông tin khóa/certificate và tùy chọn giao thức. Điểm bắt đầu thường là:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:shop:orders:sp">
    ...
</md:EntityDescriptor>
```

Thuộc tính **`entityID`** ở đây là định danh của entity, còn `<SPSSODescriptor>` hoặc `<IDPSSODescriptor>` thể hiện vai trò SAML SSO. Đừng nhầm `entityID` với `ID` của phần tử XML: thuộc tính `ID` (khi có) là định danh XML, thường phục vụ tham chiếu/chữ ký của tài liệu, **không phải SP/IdP Entity ID**.

### 3.1. Ví dụ SP metadata

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:shop:orders:sp">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
      WantAssertionsSigned="true">
    <md:AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://shop.example.test/login/saml2/sso/corp"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
```

Cách đọc:

- `EntityDescriptor/@entityID`: **SP Entity ID** = `urn:example:shop:orders:sp`.
- `SPSSODescriptor`: khai báo entity có vai trò Service Provider.
- `AssertionConsumerService/@Location`: **ACS URL**, nhận SAML Response từ IdP bằng binding khai báo.
- `Binding=...HTTP-POST`: cách trình duyệt chuyển thông điệp đến ACS; không phải Entity ID.
- `WantAssertionsSigned=true`: tuyên bố SP muốn assertion được ký. Chính sách tiếp nhận thực tế phải được cấu hình/kiểm tra tương ứng.

Đây là **đoạn metadata rút gọn để phân biệt các trường**. Tài liệu production có thể cần `KeyDescriptor`, certificate, phần tử bổ sung, chữ ký metadata và các điều kiện theo đối tác. Không dùng bản rút gọn như một cấu hình federation an toàn hoàn chỉnh.

### 3.2. Ví dụ IdP metadata

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.test/saml/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.test/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

Cách đọc:

- `EntityDescriptor/@entityID`: **IdP Entity ID** = `https://idp.example.test/saml/issuer`.
- `IDPSSODescriptor`: khai báo IdP hỗ trợ SAML SSO.
- `SingleSignOnService/@Location`: **SSO endpoint**, nơi SP chuyển hướng hoặc gửi AuthnRequest theo binding.
- Địa chỉ metadata mà SP dùng để tải XML có thể là `https://idp.example.test/saml/metadata` — một URL thứ ba, **không bắt buộc trùng** IdP Entity ID.

Ví dụ đã bỏ qua certificate của IdP vì mục đích trình bày. Trong cấu hình thật, SP phải sở hữu **bộ khóa/certificate xác minh đáng tin** để kiểm tra chữ ký response/assertion theo chính sách. Việc XML chứa đúng `entityID` **không chứng minh** XML hay thông điệp đó đáng tin.

### 3.3. Metadata URL khác Entity ID thế nào?

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| SP Entity ID | `urn:example:shop:orders:sp` | Định danh SP trong liên kết |
| IdP Entity ID | `https://idp.example.test/saml/issuer` | Định danh IdP trong liên kết |
| SP metadata URL | `https://shop.example.test/saml2/metadata/corp` | Nơi IdP/đối tác có thể tải mô tả SP |
| IdP metadata URL | `https://idp.example.test/saml/metadata` | Nơi SP có thể tải mô tả IdP |
| SP ACS URL | `https://shop.example.test/login/saml2/sso/corp` | Nơi trình duyệt POST SAML Response |
| IdP SSO URL | `https://idp.example.test/saml/sso` | Nơi gửi AuthnRequest theo binding |
| SP SLO / IdP SLO URL | Tùy cấu hình Single Logout | Nơi trao đổi LogoutRequest/LogoutResponse |

Một metadata URL có thể phân phối metadata của nhiều entity, hoặc một entity có thể được công bố qua nhiều URL. Vì vậy **không suy Entity ID chỉ từ đường dẫn tải metadata**.

## 4. Entity ID trong luồng SAML 2.0 Web Browser SSO

Giả sử ứng dụng đặt hàng là SP và IdP doanh nghiệp là hệ thống xác thực.

```text
Trình duyệt        SP: shop.example.test              IdP: idp.example.test
    |                        |                                  |
    | GET /orders            |                                  |
    |----------------------->|                                  |
    |                        | AuthnRequest (Issuer = SP ID)     |
    |                        |--------------------------------->|
    |                        |                                  | xác thực user
    |                        |                                  |
    |                        | Response / Assertion              |
    |                        | Issuer = IdP ID                   |
    |                        | Audience = SP ID                  |
    |<---------------------------------------------------------|
    | POST SAMLResponse tới ACS                                |
    |----------------------->|                                  |
    |                        | kiểm tra trust, ký số, audience, |
    |                        | destination, thời gian, context  |
    |                        |--> tạo Authentication nếu hợp lệ  |
    |<-----------------------|                                  |
```

Sơ đồ chỉ minh họa sự chuyển giao qua trình duyệt; không thể hiện chính xác mọi HTTP redirect/POST trung gian.

### Bước 1 — SP xác định cấu hình liên kết

Khi cần đăng nhập SAML, Spring Security chọn một **`RelyingPartyRegistration`**, tức cấu hình ghép một SP với một IdP. Mỗi registration có `registrationId` nội bộ để tra cứu.

Một registration trong Spring Security có thể là:

```text
registrationId = corp
SP entityId    = urn:example:shop:orders:sp
SP ACS         = https://shop.example.test/login/saml2/sso/corp
IdP entityId   = https://idp.example.test/saml/issuer
IdP SSO        = https://idp.example.test/saml/sso
```

**`corp` không phải SP Entity ID hoặc IdP Entity ID.** Nó là khóa cấu hình/đường dẫn giúp Spring Security chọn registration. SP Entity ID vẫn là `urn:example:shop:orders:sp`.

### Bước 2 — SP phát AuthnRequest

SP xây dựng thông điệp `<samlp:AuthnRequest>`; ví dụ các trường liên quan:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://idp.example.test/saml/sso"
    AssertionConsumerServiceURL="https://shop.example.test/login/saml2/sso/corp">
  <saml:Issuer>urn:example:shop:orders:sp</saml:Issuer>
</samlp:AuthnRequest>
```

Đây là XML **minh họa trường định danh, không phải request ký số/hoàn chỉnh**. Trong giao thức thực, SP/IdP còn phải kiểm tra binding, chữ ký AuthnRequest nếu cần, thời gian, yêu cầu bảo mật và sự phù hợp với metadata.

- `Issuer` của **AuthnRequest** thường chứa **SP Entity ID**.
- `Destination` là **IdP SSO endpoint**, không phải IdP Entity ID.
- `AssertionConsumerServiceURL` là nơi SP muốn nhận Response; IdP chỉ gửi đến ACS đã đăng ký/tin cậy, không cho phép URL tùy ý.
- `ID` của AuthnRequest là mã riêng của **một yêu cầu** để liên kết Response, khác Entity ID.

### Bước 3 — IdP xác minh SP và đăng nhập người dùng

IdP đối chiếu `Issuer` với SP được đăng ký trong trust configuration; kiểm tra ACS URL/binding, yêu cầu ký số, chính sách client và các điều kiện chống request giả. Sau đó IdP xác thực người dùng theo chính sách của mình (có thể dùng MFA/phiên SSO).

Một IdP được cấu hình tốt **không** gửi SAML assertion tới ACS bất kỳ mà request tự chỉ định. Người dùng/attacker không được quyết định SP Entity ID hay ACS mới chỉ bằng cách sửa thông điệp.

### Bước 4 — IdP phát SAML Response/Assertion

Các mảnh XML sau minh họa quan hệ định danh:

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:05Z"
    InResponseTo="_req_001"
    Destination="https://shop.example.test/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.test/saml/issuer</saml:Issuer>
  <saml:Assertion ID="_assertion_001"
                  Version="2.0"
                  IssueInstant="2026-01-01T10:00:05Z">
    <saml:Issuer>https://idp.example.test/saml/issuer</saml:Issuer>
    <saml:Conditions>
      <saml:AudienceRestriction>
        <saml:Audience>urn:example:shop:orders:sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
```

Đây là **XML cắt gọn để chỉ ra vị trí `Issuer` và `Audience`**, cố ý bỏ chữ ký, Subject, SubjectConfirmation, Status và ràng buộc thời gian thực tế. Nó **không phải** một SAML Response đầy đủ hay an toàn để gửi đến ACS.

Trong phản hồi đầy đủ:

- `Response/Issuer` và `Assertion/Issuer` thường xác định **IdP Entity ID**; cần kiểm tra theo cấu trúc, chính sách và chữ ký thực tế.
- `AudienceRestriction/Audience` của assertion hướng tới **SP Entity ID**. Đó là một trong những ràng buộc ngăn assertion dành cho SP A bị dùng ở SP B.
- `Response/@Destination` là **ACS URL** của SP; `SubjectConfirmationData/@Recipient` trong bearer confirmation thường cũng phải khớp nơi nhận hợp lệ.
- `InResponseTo` liên hệ Response/SubjectConfirmationData với AuthnRequest trước đó khi là SP-initiated flow. Nếu hỗ trợ IdP-initiated/unsolicited login, chính sách và cơ chế kiểm tra khác cần được xác định cẩn thận.
- Chữ ký, điều kiện thời gian, `InResponseTo`, `Recipient`, `Destination`, `SubjectConfirmation`, `Audience` và chính sách chống replay **đều quan trọng**. Khớp Entity ID thôi **không đủ** để chấp nhận phản hồi.

### Bước 5 — SP xác minh và tạo phiên ứng dụng

Spring Security SAML 2.0 sử dụng cấu hình registration và cơ chế xử lý SAML của framework/OpenSAML để kiểm tra phản hồi theo cấu hình. Nếu hợp lệ, nó tạo `Authentication` cho ứng dụng. Sau đó hệ thống nghiệp vụ quyết định người đó có quyền gì.

Mọi kiểm tra Entity ID phải được đặt trong **chuỗi xác minh SAML hoàn chỉnh**. Không viết một servlet tự parse XML, so sánh `Issuer` và cho đăng nhập mà bỏ kiểm tra chữ ký hoặc các điều kiện assertion.

## 5. Ranh giới tin cậy giữa hai Entity ID

### 5.1. IdP xác minh danh tính SP

SP gửi yêu cầu có `Issuer=SP Entity ID`. IdP dùng định danh đó để tìm cấu hình đã đăng ký: ACS allowlist, cách ký yêu cầu, certificate của SP và chính sách đăng nhập. Nếu `Issuer` không tồn tại hoặc không thuộc đối tác được cho phép, IdP phải từ chối/không áp dụng trust của một SP khác.

Điều này giúp tránh việc một SP giả tự nhận quyền của ứng dụng khác rồi yêu cầu IdP gửi assertion tới endpoint của attacker.

### 5.2. SP xác minh danh tính IdP và người nhận

Khi nhận Response, SP phải xác minh nó đến từ IdP đã đăng ký và có **chữ ký hợp lệ với khóa đáng tin**. `Issuer=IdP Entity ID` là chỉ dấu danh tính logic; certificate/chữ ký cung cấp bằng chứng mật mã. Cả hai phải khớp trust configuration.

Sau đó SP phải kiểm tra assertion **dành cho SP của mình**, bằng audience và các ràng buộc khác. Không chấp nhận assertion chỉ vì người dùng tồn tại ở IdP nào đó. Token cho ứng dụng khác có thể mang NameID tương tự nhưng không được đem dùng tại SP này.

### 5.3. Vì sao không thể chỉ dựa vào Entity ID?

Entity ID là một chuỗi công khai, có thể đọc từ metadata hoặc message. Attacker có thể viết cùng chuỗi đó trong XML giả. **Chuỗi khớp không chứng minh danh tính**. Tin cậy thực tế còn phụ thuộc:

1. Nguồn metadata/cấu hình IdP được quản trị xác thực.
2. Certificate/khóa verification được gắn với đúng IdP.
3. Chữ ký thông điệp/assertion được kiểm tra theo chính sách.
4. `Issuer`, `Audience`, ACS, `Destination`, `Recipient`, thời hạn, correlation và replay được kiểm tra.
5. Quyền của người dùng được kiểm tra tiếp ở tầng nghiệp vụ.

Không nhận metadata từ URL do request tùy ý đưa vào rồi lập tức tin certificate trong metadata đó; như vậy attacker có thể tự tạo “IdP đáng tin” cho cùng Entity ID.

## 6. Phân biệt Entity ID với các định danh liên quan

| Thuộc tính | Gắn với | Ý nghĩa | Có thể trùng Entity ID? |
| --- | --- | --- | --- |
| SP Entity ID | SP | Định danh dịch vụ tham gia federation | Là chính giá trị định danh SP |
| IdP Entity ID | IdP | Định danh máy chủ phát SAML assertion | Là chính giá trị định danh IdP |
| `registrationId` trong Spring | Một cặp cấu hình RP–AP | Chọn cấu hình local, xuất hiện trong nhiều URL mặc định | Có thể do người cấu hình trùng chuỗi nhưng **không phải cùng khái niệm** |
| SP metadata URL | Máy chủ phân phối XML metadata | Địa điểm tải mô tả SP | Có thể cùng URL-style entityID nhưng không bắt buộc |
| IdP metadata URL | Máy chủ phân phối XML metadata | Địa điểm tải mô tả IdP | Có thể khác IdP entityID |
| ACS URL | SP | Endpoint nhận SAML Response | Nên xem là trường riêng; có thể thay trong khi Entity ID giữ nguyên |
| SSO URL | IdP | Endpoint nhận AuthnRequest | Không phải IdP Entity ID |
| SLO URL | SP hoặc IdP | Endpoint trao đổi Single Logout | Không phải Entity ID |
| `NameID` | Người dùng trong assertion | Danh tính subject theo format/qualifier | Không phải Entity ID của hệ thống |
| `AuthnRequest/@ID` | Một phiên yêu cầu đăng nhập | Liên kết request/response và chống replay | Không phải Entity ID |
| X.509 certificate | Khóa ký/xác minh của SP/IdP | Tin cậy mật mã cho thông điệp/metadata | Không phải Entity ID; việc xoay chứng thư có thể giữ nguyên Entity ID |

Ví dụ “`https://shop.example.test/saml2/metadata/corp` là Entity ID” chỉ đúng **nếu SP thực sự đã cấu hình Entity ID bằng đúng giá trị đó**; không thể suy ra chỉ từ việc đây là URL xem metadata.

## 7. Cấu hình bằng Spring Security và Spring Boot

Spring Security Servlet hỗ trợ ứng dụng làm **SAML 2.0 Relying Party/Service Provider**. Trong một `RelyingPartyRegistration`:

- **Phía relying party** chứa `entityId` (SP), `assertionConsumerServiceLocation`, signing/decryption credentials nếu dùng.
- **Phía asserting party** chứa `entityId` (IdP), SSO/SLO endpoints và verification credentials/metadata.
- `registrationId` là tên định danh **cục bộ cho cặp cấu hình**, ví dụ `corp`, `partner-a`; nó khác cả hai Entity ID.

### 7.1. Mẫu application.yml

Ví dụ cho Spring Boot 3.x / Spring Security 6.x với các property SAML2 phù hợp:

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:shop:orders:sp"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://idp.example.test/saml/metadata"
```

Giải thích chính xác:

- `corp` là **registrationId**, dùng để chọn cấu hình này.
- `entity-id` dưới `registration.corp` là **SP Entity ID**. IdP phải đăng ký ứng dụng bằng cùng chuỗi `urn:example:shop:orders:sp`.
- `acs.location` là **địa chỉ nhận assertion** của SP. Khi `baseUrl=https://shop.example.test`, giá trị có thể được giải thành `https://shop.example.test/login/saml2/sso/corp`.
- `assertingparty.metadata-uri` là **đường dẫn lấy IdP metadata**, không phải IdP Entity ID. Spring lấy IdP Entity ID từ `EntityDescriptor/@entityID` của metadata được tin cậy.
- Trong triển khai thực tế, IdP cần công bố certificate và endpoint phù hợp. Nếu IdP yêu cầu AuthnRequest được ký hoặc assertion giải mã, phải cấu hình signing/decryption credentials tương ứng. Mẫu này **chỉ cho thấy mapping Entity ID/metadata/ACS**, không tự chứng minh hệ thống đã hoàn thành mọi điều kiện security của IdP.

Tùy phiên bản Spring Boot, cấu trúc/khả năng của một số property có thể khác; đối chiếu **configuration metadata của phiên bản đang chạy** thay vì chép config của framework đời khác. Các ví dụ này nhắm đến **Spring Security hiện đại**, không phải dự án Spring Security SAML Extension cũ dùng các bean và đường dẫn khác.

### 7.2. SecurityFilterChain hiển thị SAML metadata

Tệp `SecurityConfig.java` trong package của ứng dụng (ví dụ `com.example.shop`), minh họa cấu hình servlet:

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **một class trong dự án Spring Boot**, không phải chương trình chạy trực tiếp bằng `javac` thuần JDK. Dự án cần dependency web/security và `org.springframework.security:spring-security-saml2-service-provider`, repository để giải quyết OpenSAML nếu môi trường build cần, cũng như registration/certificate/IdP được cấu hình đúng.

Với DSL `saml2Metadata`, Spring Security có thể công bố metadata cho registration tại các URL mặc định như:

```text
/saml2/metadata
/saml2/metadata/{registrationId}
/saml2/service-provider-metadata/{registrationId}
```

Endpoint thực tế và cách trình bày có thể thay bằng cấu hình Spring Security. IdP nên nhập SP metadata hoặc cùng bộ **SP Entity ID + ACS URL + certificate** đã được kiểm chứng. Nếu có reverse proxy/TLS termination, đảm bảo metadata xuất ra host, scheme, port và path **công khai** phù hợp; không nên công bố ACS `http://localhost:8080/...` cho IdP ngoài mạng.

### 7.3. Lấy Entity ID ra để đối chiếu

Trong ứng dụng có `RelyingPartyRegistrationRepository`, có thể xem cấu hình của registration cụ thể, ví dụ:

```java
RelyingPartyRegistration registration =
    repository.findByRegistrationId("corp");

String spEntityId = registration.getEntityId();
String idpEntityId =
    registration.getAssertingPartyMetadata().getEntityId();

String acs = registration.getAssertionConsumerServiceLocation();
```

Đoạn trên chỉ là **trích đoạn sử dụng API trong một method có sẵn biến `repository`**, không phải một file Java độc lập. Tên method/API có thể thay giữa các phiên bản Spring Security; đọc Javadoc của version thực tế. Cần so khớp hai Entity ID này với metadata/registration phía đối tác và đảm bảo `acs` chính xác.

**Không sửa `registrationId` để “vá” IdP Entity ID sai.** Nếu IdP đổi entityID, cần cập nhật đúng asserting-party metadata/trust configuration và phối hợp xác minh, không đổi một nhãn local rồi hy vọng validation bỏ qua.

## 8. Ví dụ Java 17 độc lập: kiểm tra cặp Entity ID theo hợp đồng

Đoạn này chỉ mô phỏng **so sánh các chuỗi định danh đã được rút ra từ một message tin cậy**, nhằm làm rõ sự khác nhau giữa issuer và audience. Nó **không parse, giải mã, xác minh chữ ký hoặc chấp nhận SAML Response thật**. Trong hệ thống thực tế, để xác thực SAML phải dùng Spring Security/OpenSAML và đủ ràng buộc giao thức.

Tệp `EntityIdContractDemo.java`:

```java
import java.util.Objects;

public class EntityIdContractDemo {

    record FederationPair(String spEntityId, String idpEntityId) {
        FederationPair {
            Objects.requireNonNull(spEntityId);
            Objects.requireNonNull(idpEntityId);
        }
    }

    static boolean matchesPartyIds(
            FederationPair configured,
            String responseIssuer,
            String assertionAudience) {
        return configured.idpEntityId().equals(responseIssuer)
                && configured.spEntityId().equals(assertionAudience);
    }

    public static void main(String[] args) {
        FederationPair pair = new FederationPair(
                "urn:example:shop:orders:sp",
                "https://idp.example.test/saml/issuer"
        );

        System.out.println("expected=" + matchesPartyIds(
                pair,
                "https://idp.example.test/saml/issuer",
                "urn:example:shop:orders:sp"
        ));

        System.out.println("wrongIssuer=" + matchesPartyIds(
                pair,
                "https://other-idp.example.test/saml/issuer",
                "urn:example:shop:orders:sp"
        ));

        System.out.println("wrongAudience=" + matchesPartyIds(
                pair,
                "https://idp.example.test/saml/issuer",
                "urn:example:shop:payroll:sp"
        ));

        System.out.println("trailingSlash=" + matchesPartyIds(
                pair,
                "https://idp.example.test/saml/issuer/",
                "urn:example:shop:orders:sp"
        ));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac EntityIdContractDemo.java
java EntityIdContractDemo
```

Stdout chính xác:

```text
expected=true
wrongIssuer=false
wrongAudience=false
trailingSlash=false
```

Giải thích:

- `expected=true` khi IdP Entity ID của bên phát hành và SP Entity ID trong audience đều khớp cấu hình.
- `wrongIssuer=false`: thông điệp khai issuer khác nhà cung cấp đã đăng ký.
- `wrongAudience=false`: assertion dành cho SP khác, dù IdP đúng.
- `trailingSlash=false`: `/issuer` và `/issuer/` là hai chuỗi khác nhau trong so sánh định danh.

**Cảnh báo phạm vi ví dụ:** các phép `equals` chỉ làm rõ quan hệ **nhãn định danh**, không chứng minh nguồn gốc của giá trị đưa vào. Chỉ khi SAML đã qua chữ ký, điều kiện thời gian, Destination/Recipient, SubjectConfirmation, InResponseTo, replay và kiểm tra registration phù hợp mới có thể tạo phiên xác thực. Không dùng hàm `matchesPartyIds` làm validator SAML độc lập.

## 9. Một SP liên kết nhiều IdP: quản lý cặp entity

Một ứng dụng có thể cho nhân viên công ty A và đối tác B đăng nhập từ hai IdP khác nhau. Spring Security lưu **một registration cho mỗi mối quan hệ SP–IdP**.

Ví dụ:

| registrationId | SP Entity ID | IdP Entity ID | ACS |
| --- | --- | --- | --- |
| `employee` | `urn:example:shop:orders:sp` | `https://idp-a.example.test/saml` | `https://shop.example.test/login/saml2/sso/employee` |
| `partner` | `urn:example:shop:orders:sp` | `https://idp-b.example.test/issuer` | `https://shop.example.test/login/saml2/sso/partner` |

Việc **dùng cùng SP Entity ID qua nhiều IdP** là lựa chọn có thể hợp lệ nếu từng IdP được đăng ký với đúng SP entity/ACS/binding và ứng dụng tách đúng trust configuration. Trong các tổ chức yêu cầu danh tính SP riêng cho mỗi đối tác hoặc mỗi môi trường, SP Entity ID cũng có thể khác theo registration. Không có quy tắc chung rằng **một registrationId bắt buộc tương ứng một SP Entity ID duy nhất trên toàn hệ thống**.

Nguyên tắc an toàn:

1. Quản lý từng cặp theo **IdP Entity ID, certificate, endpoints, SP Entity ID, ACS**. Không tin “cùng hostname” nghĩa là cùng IdP.
2. Chọn `RelyingPartyRegistration` bằng cơ chế Spring Security hỗ trợ, đồng thời xác minh response dựa trên trust config của registration được chọn.
3. Không để attacker gửi `Issuer` tùy ý và khiến SP tải metadata mới rồi tin vào certificate của attacker.
4. Không dùng assertion từ IdP A với cấu hình/certificate của B chỉ vì cả hai đăng ký một ứng dụng chung.
5. Nếu có nhiều ứng dụng SP ở cùng domain, **audience, ACS và định danh registration** phải đủ rõ để assertion của ứng dụng này không được chấp nhận bởi ứng dụng khác.
6. Nếu dùng identity broker trung gian, SP thường tin **Entity ID của broker** đã cấu hình. Entity ID của IdP upstream là một phần quan hệ tin cậy riêng giữa broker và upstream, không được suy diễn từ assertion nhận tại SP.

## 10. Entity ID khi có nhiều môi trường và reverse proxy

Một lỗi phổ biến là build/deploy ở các môi trường khác nhau nhưng không quản lý Entity ID, metadata và endpoint tương ứng:

```text
DEV SP Entity ID  = urn:example:shop:dev:sp
UAT SP Entity ID  = urn:example:shop:uat:sp
PROD SP Entity ID = urn:example:shop:prod:sp
```

Mỗi môi trường nên có cấu hình trust và URL công khai rõ ràng, nhất là khi IdP cho phép phân quyền/ACS/certificate khác nhau. Không bắt buộc mọi tổ chức đặt Entity ID theo mẫu trên, nhưng cần một phương án tránh nhầm dev/prod và cross-environment login.

**Ví dụ lỗi proxy:**

```text
Người dùng mở         https://shop.example.test
Proxy chuyển đến      http://orders-service:8080
Spring phát ACS       http://orders-service:8080/login/saml2/sso/corp
IdP đăng ký ACS       https://shop.example.test/login/saml2/sso/corp
```

Khi đó IdP có thể từ chối AuthnRequest vì ACS không có trong danh sách cho phép; hoặc SAML Response gửi về endpoint công khai nhưng SP kiểm tra Destination/Recipient thấy sai.

Cách xử lý:

- Cấu hình reverse proxy gửi `Forwarded` hoặc `X-Forwarded-*` **từ proxy đáng tin**, và cấu hình Spring Boot/Spring Security để tạo URL từ nguồn header được kiểm soát.
- Kiểm tra nội dung SP metadata **tại địa chỉ công khai**: `entityID`, ACS `Location`, binding và certificate.
- Đối chiếu bản ghi đã nhập tại IdP, tránh nhầm tên miền, path, dấu slash hoặc port.
- Nếu chọn SP Entity ID dạng `urn:`, entity ID có thể giữ ổn định khi host thay đổi, **nhưng ACS vẫn phải cập nhật** nếu địa chỉ tiếp nhận đổi. Nếu Entity ID theo `{baseUrl}`, thay public base URL có thể đồng thời làm đổi Entity ID.
- Không cho phép header forwarded từ Internet trực tiếp quyết định trust URL nếu backend có thể bị gọi không qua proxy; chặn đường vòng vào backend, cấu hình trusted proxies.

## 11. Khi xoay khóa, đổi endpoint hoặc đổi Entity ID

Ba thay đổi vận hành có mức ảnh hưởng khác nhau:

| Thay đổi | Điều gì giữ nguyên? | Việc cần phối hợp |
| --- | --- | --- |
| Xoay certificate IdP | Entity ID thường **giữ nguyên** | SP nhập/refresh khóa xác minh theo nguồn metadata đáng tin, có khoảng chồng khóa nếu chính sách cho phép |
| Đổi IdP SSO endpoint | Entity ID có thể **giữ nguyên** | SP cập nhật endpoint/binding từ metadata đã xác thực |
| Đổi SP ACS URL | SP Entity ID có thể **giữ nguyên** | IdP cập nhật allowlist/metadata SP; SP cấu hình route và Destination/Recipient |
| Đổi SP Entity ID | Định danh SP **thay đổi** | IdP đăng ký/cập nhật SP, mapping audience và trust; kiểm thử luồng trước khi chuyển |
| Đổi IdP Entity ID | Định danh IdP **thay đổi** | SP cập nhật asserting-party metadata/trust và kiểm thử Issuer; có thể tác động liên kết user |
| Đổi `registrationId` local | Có thể không đổi Entity ID | Cập nhật login URL, ACS có `{registrationId}` và metadata/IdP liên quan |

**Đổi Entity ID không phải thao tác chỉ đổi nhãn trên màn hình.** Khi SP Entity ID thay đổi, IdP có thể coi đó là **ứng dụng SP mới**; SAML Audience, AuthnRequest Issuer, SP metadata và cấu hình certificate/ACS phía IdP đều phải ăn khớp. Khi IdP Entity ID đổi, SP không nên tự bỏ qua issuer validation để “đăng nhập cho qua”.

Quy trình đề xuất:

1. Chụp lại cấu hình đã được phê duyệt: hai Entity ID, metadata, ACS/SSO, certificate và profile/binding.
2. Xác định thay đổi là **entity identity**, **endpoint**, hay **key material** — không gộp ba loại.
3. Chuẩn bị cấu hình mới ở cả SP và IdP, với phương án chuyển đổi có kiểm soát.
4. Thử đăng nhập SP-initiated; nếu dùng IdP-initiated, thử riêng và xác minh chính sách correlation/replay.
5. Kiểm tra issuer, audience, recipient, destination, signature, session và quyền nghiệp vụ.
6. Theo dõi lỗi và loại bỏ cấu hình/khóa cũ theo kế hoạch, không để legacy trust tồn tại vô thời hạn.

## 12. Lỗi thường gặp, dấu hiệu và cách khắc phục

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra đúng |
| --- | --- | --- |
| IdP báo không nhận biết ứng dụng | `AuthnRequest/Issuer` không khớp SP Entity ID đã đăng ký | So SP Entity ID trong metadata IdP quản lý với Issuer request |
| IdP từ chối ACS | `AssertionConsumerServiceURL` không nằm trong allowlist | So ACS đăng ký, binding, scheme, port, path |
| SP báo issuer không hợp lệ | IdP Entity ID trong assertion/response khác cấu hình | So metadata `entityID` của IdP với issuer thực tế đã xác minh |
| SP báo audience không hợp lệ | Assertion Audience là Entity ID khác | So `AudienceRestriction/Audience` với SP Entity ID đang dùng |
| SP báo Destination/Recipient không hợp lệ | ACS hoặc proxy URL không khớp | So destination/recipient, URL công khai và metadata |
| SP không tìm thấy registration | `registrationId` hoặc cách chọn registration sai | So URL `/saml2/authenticate/{registrationId}`, repository/registration |
| Chữ ký không hợp lệ dù Entity ID đúng | Certificate/thuật toán/khóa ký không khớp, metadata cũ hoặc chữ ký bị sửa | Kiểm tra trust certificate và rotation, signature policy |
| Đăng nhập IdP thành công nhưng SP từ chối | Assertion không qua một trong các điều kiện SP | Kiểm tra lỗi theo **đúng loại**: issuer, audience, signature, recipient, thời gian, correlation |
| Chỉ lỗi ở production sau reverse proxy | `{baseUrl}`/ACS được tạo từ host/scheme nội bộ | So metadata công khai và cấu hình trusted proxy |
| Không kết nối được khi đổi entityID | Đối tác chưa cập nhật metadata/trust | Phối hợp đổi cả hai bên, kiểm thử luồng chuyển đổi |
| Nhiều IdP, token của A bị xử lý như B | Sai chọn registration hoặc mapping trust | Tách issuer, verification credentials và registration, xác minh chặt |
| Tên người dùng trùng | NameID trùng trong các IdP | Đây là bài toán **định danh người dùng**, không giải quyết bằng cách đổi SP Entity ID |

Không tắt xác minh chữ ký, issuer hoặc audience để khắc phục lỗi cấu hình. Gỡ một điều kiện quan trọng có thể biến sự cố đăng nhập thành lỗ hổng chấp nhận assertion không dành cho ứng dụng.

## 13. Kiểm thử hợp đồng Entity ID một cách có hệ thống

Các kiểm thử nên xác nhận:

| Ca kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Đăng nhập hợp lệ | AuthnRequest Issuer là SP ID; Response/Assertion từ IdP đã đăng ký; Audience là SP ID | Sau **toàn bộ** validation, tạo phiên đăng nhập |
| SP ID sai | Request Issuer không khớp SP đăng ký tại IdP | IdP từ chối hoặc không áp dụng trust của SP |
| IdP ID sai | Response/Assertion có issuer của IdP khác | SP từ chối |
| Audience sai | Assertion dành cho SP khác | SP từ chối |
| Thiếu/không hợp lệ signature | Issuer và Audience đúng nhưng chữ ký sai | SP từ chối |
| ACS sai | Response Destination/Recipient không khớp endpoint hợp lệ | SP từ chối |
| Replay response | Cùng Response/Assertion được gửi lại sau khi dùng | Bị ngăn theo chính sách replay/correlation |
| Hết thời hạn | Assertion ngoài NotBefore/NotOnOrAfter phù hợp | SP từ chối |
| Dấu `/` cuối khác | Entity ID có hoặc thiếu slash | Xác định giá trị hợp đồng, không tự sửa chuẩn hóa |
| Đổi hostname proxy | Public URL khác internal URL | SP metadata và ACS phản ánh public URL được tin cậy |
| Hai IdP | A và B khác entityID/certificate | Response của A không được chấp nhận như B |
| Đổi certificate | Entity ID giữ nguyên, khóa ký mới hợp lệ | Chỉ chấp nhận khóa mới sau cập nhật trust theo chính sách |
| Đổi SP ID | Audience mới, SP metadata/IdP registration mới | Hoạt động sau đồng bộ, từ chối assertion dành cho ID cũ khi đã thu hồi |

Kiểm thử **negative cases** quan trọng không kém “đăng nhập thành công”: việc từ chối một assertion sai issuer/audience chứng minh trust boundary đang có tác dụng. Có thể chạy integration test với IdP thử nghiệm và bộ SAML test harness; không dùng XML cắt gọn trong bài làm mẫu token hợp lệ.

## 14. Checklist triển khai với đối tác SAML

- [ ] Ghi rõ SP Entity ID đã duyệt, chính xác đến dấu `/`, scheme, path, chữ hoa/thường.
- [ ] Ghi rõ IdP Entity ID từ metadata đáng tin; không suy từ SSO URL hoặc tên nhà cung cấp.
- [ ] Xác nhận `registrationId` trong Spring Security chỉ là nhãn cấu hình; biết chính xác SP/IdP entityId của từng registration.
- [ ] Đối chiếu SP metadata `EntityDescriptor/@entityID` với `AuthnRequest/Issuer`.
- [ ] Đối chiếu IdP metadata `EntityDescriptor/@entityID` với `Response/Issuer` / `Assertion/Issuer` theo yêu cầu giao thức.
- [ ] Đối chiếu `AudienceRestriction/Audience` với SP Entity ID, không thay bằng ACS URL.
- [ ] Đối chiếu ACS, SSO, SLO URL và binding; xác minh địa chỉ public sau reverse proxy.
- [ ] Thiết lập tin cậy certificate/metadata và chính sách chữ ký an toàn; có quy trình rotation.
- [ ] Kiểm tra response/assertion validation đủ issuer, audience, destination, recipient, time, subject confirmation, InResponseTo/replay theo profile được hỗ trợ.
- [ ] Kiểm thử IdP-initiated flow riêng nếu cần; không mặc định mọi response unsolicited đều có thể chấp nhận.
- [ ] Tách cấu hình dev/UAT/prod và từng IdP; ghi rõ ai sở hữu thay đổi Entity ID.
- [ ] Lưu vết lỗi SAML ở mức đủ phân tích; không ghi nguyên SAMLResponse chứa thông tin nhạy cảm vào log sản xuất.
- [ ] Sau xác thực thành công, hệ thống nghiệp vụ tiếp tục kiểm tra user mapping, trạng thái account, tenant và permission.

## 15. Câu hỏi tự kiểm tra

**1. SP Entity ID là URL nhận SAML Response phải không?** Không. URL nhận là **ACS URL**. SP Entity ID có thể có dạng URL hoặc URN nhưng được dùng làm định danh logic của SP.

**2. Trong `AuthnRequest`, `Issuer` thường là của ai?** Là **SP Entity ID**. `Destination` là **SSO endpoint của IdP**.

**3. Khi SP nhận assertion, giá trị Audience phải khớp gì?** Theo SAML Web Browser SSO, phải phù hợp **SP Entity ID** của registration đang xử lý, cùng các điều kiện validation khác.

**4. `https://idp.example.test/saml/metadata` có luôn là IdP Entity ID không?** Không. Đó có thể chỉ là URL tải metadata. Đọc `EntityDescriptor/@entityID` để biết IdP Entity ID.

**5. Nếu IdP đổi certificate nhưng không đổi Entity ID, SP có phải đổi SP Entity ID không?** Thông thường không. SP cần cập nhật/refresh trust key, kiểm tra chữ ký và phối hợp rotation; Entity ID là định danh logic độc lập với key material.

**6. Vì sao một Response có issuer và audience đúng vẫn có thể nguy hiểm?** Vì attacker có thể giả chuỗi. SP còn phải kiểm tra chữ ký được tin cậy, recipient/destination, thời hạn, request correlation, subject confirmation và chống replay.

**7. `registrationId=corp` trong Spring có thể dùng làm issuer cho IdP không?** Không mặc định. Đó là khóa local. IdP Entity ID phải đến từ metadata/cấu hình trusted asserting party.

**8. Có được dùng SP Entity ID làm ID người dùng không?** Không. Nó định danh hệ thống SP; SAML `NameID`/thuộc tính subject đã xác minh mới giúp ánh xạ danh tính người dùng theo hợp đồng với IdP.

## Tài liệu tham khảo

- Spring Security, **SAML 2.0 Login Overview**, cách tổ chức `RelyingPartyRegistration`, giá trị mặc định Entity ID và ACS: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **SAML 2.0 Metadata**, đọc metadata IdP và xuất SP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **Authenticating SAML Responses**, xác minh response và cấu hình authentication: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**, cấu hình ký yêu cầu: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot 3.5, **SAML 2.0 Relying Party** properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS, **SAML 2.0 Metadata Specification**, `EntityDescriptor`, `IDPSSODescriptor`, `SPSSODescriptor`: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf

**Ghi nhớ:** trong SAML 2.0, **SP Entity ID** xác định ứng dụng yêu cầu đăng nhập và là đối tượng mà assertion hướng tới; **IdP Entity ID** xác định nhà phát hành được tin cậy. Entity ID không phải ACS/SSO/metadata URL hay NameID. Federation an toàn đòi hỏi **đúng cả hai Entity ID cùng certificate, endpoint, audience và mọi điều kiện xác minh SAML**, rồi mới cho ứng dụng tạo phiên và áp dụng quyền nghiệp vụ.