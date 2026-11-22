# Các endpoint SSO, ACS, SLO và binding trong metadata SAML 2.0

Trong một hệ thống **SAML 2.0 federation**, ứng dụng nhận kết quả đăng nhập là **Service Provider (SP/Relying Party)**, còn hệ thống xác thực người dùng là **Identity Provider (IdP/Asserting Party)**. Hai bên không đoán đường dẫn của nhau: họ trao đổi **metadata XML** để biết định danh, các endpoint, binding, chứng thư và khả năng hỗ trợ của đối tác.

**Phân biệt ngay ba loại endpoint:**

| Phần tử metadata | Thuộc bên nào? | Nhận thông điệp nào? | Chức năng |
| --- | --- | --- | --- |
| `SingleSignOnService` (**SSO**) | **IdP**; nằm trong `IDPSSODescriptor`. | SP gửi `AuthnRequest` đến IdP. | Bắt đầu xác thực người dùng. |
| `AssertionConsumerService` (**ACS**) | **SP**; nằm trong `SPSSODescriptor`. | IdP gửi SAML `Response` chứa assertion. | SP xác minh kết quả đăng nhập, thiết lập phiên nếu hợp lệ. |
| `SingleLogoutService` (**SLO**) | Có thể có ở **IdP và SP**. | `LogoutRequest` và `LogoutResponse`. | Phối hợp kết thúc phiên đăng nhập liên kết. |

**Hướng đi chủ đạo:** SP gửi yêu cầu đăng nhập tới **IdP SSO** → IdP trả kết quả về **SP ACS**. Khi logout liên kết, bên khởi tạo gửi thông điệp tới **SLO endpoint của bên nhận**. Mỗi endpoint khai báo `Binding` để chỉ rõ *cách vận chuyển thông điệp*, chứ `Binding` không phải URL hay quyền đăng nhập.

## 1. Metadata có những gì?

Một tệp metadata thường chứa `<md:EntityDescriptor>` với `entityID` và một hoặc nhiều role descriptor. Tệp tổng hợp có thể chứa `<md:EntitiesDescriptor>` bọc nhiều entity. Các phần tử liên quan:

~~~text
IdP metadata
EntityDescriptor  @entityID = IDP_ENTITY_ID
└── IDPSSODescriptor
    ├── KeyDescriptor                 khóa ký/mã hóa được công bố
    ├── SingleLogoutService           IdP SLO nếu hỗ trợ
    ├── NameIDFormat                  định dạng tên định danh nếu công bố
    └── SingleSignOnService           một hay nhiều IdP SSO endpoints

SP metadata
EntityDescriptor  @entityID = SP_ENTITY_ID
└── SPSSODescriptor
    ├── KeyDescriptor                 khóa SP nếu có
    ├── SingleLogoutService           SP SLO nếu hỗ trợ
    ├── NameIDFormat                  các dạng NameID được hỗ trợ
    └── AssertionConsumerService      một hay nhiều SP ACS endpoints
~~~

Các metadata thực còn có thể có `validUntil`, `cacheDuration`, `AuthnRequestsSigned`, `WantAuthnRequestsSigned`, `WantAssertionsSigned`, `ArtifactResolutionService` và các extension. **`entityID` là định danh logic**, có thể có dạng URL hoặc URN; nó **không nhất thiết là URL truy cập được**. Cần tách biệt:

- **SP entityID**: giá trị mà IdP dùng xác định SP/audience, ví dụ `urn:example:sp:portal`.
- **IdP entityID**: danh tính nhà phát hành SAML đáng tin, ví dụ `urn:example:idp:corporate`.
- **Metadata URL**: nơi tải tài liệu XML để thiết lập/đồng bộ cấu hình, ví dụ `https://idp.example.org/metadata`.
- **SSO/ACS/SLO Location**: địa chỉ trao đổi thông điệp khi thực sự login/logout.

Nếu lấy metadata URL làm SSO URL, hoặc lấy ACS URL làm SP entityID mà không chủ đích cấu hình như vậy, tích hợp sẽ sai dù tất cả chuỗi đều trông giống URL.

## 2. IdP metadata: SingleSignOnService

Ví dụ XML có tính **minh họa các endpoint**, lược bỏ khóa, chữ ký metadata và các thuộc tính triển khai khác:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:idp:corporate">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/slo"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso/redirect"/>

    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso/post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Trong đó `SingleSignOnService/@Location` là **địa chỉ IdP nhận `AuthnRequest` từ SP**. `Binding` cho biết SP phải gửi yêu cầu qua HTTP-Redirect hay HTTP-POST. Có **hai SSO endpoint** chỉ có nghĩa IdP công bố hai lựa chọn: SP phải chọn đúng **cặp Binding + Location** được hỗ trợ, không trộn binding từ mục này với URL của mục khác.

`SingleLogoutService` ở đây là **SLO của IdP**; nó không thay cho `SingleSignOnService`, dù một số sản phẩm có thể đặt cả hai trên cùng đường dẫn HTTP.

Với luồng SP-initiated SSO, SP lập `AuthnRequest`, lưu trạng thái giao dịch trong session/correlation store của trình duyệt khởi tạo và chuyển trình duyệt đến **IdP SSO Location** đã chọn. Việc truy cập endpoint IdP này chỉ bắt đầu quá trình, **chưa có SAML Response được ứng dụng xác minh**.

## 3. SP metadata: AssertionConsumerService

SP công bố endpoint để IdP trả kết quả bằng `AssertionConsumerService` (ACS). Một ví dụ:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:sp:portal">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.org/logout/saml2/slo"/>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.org/login/saml2/sso/corporate"
        index="0"
        isDefault="true"/>

    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://sp.example.org/saml/acs/partner"
        index="1"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

**Giải nghĩa các trường ở ACS:**

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `Binding` | Cách **IdP gửi Response đến ACS**; HTTP-POST thường gặp trong Web Browser SSO. |
| `Location` | URL cụ thể mà **SP thực sự có handler nhận SAML Response**. |
| `index` | Chỉ số endpoint trong danh sách ACS; thuộc tính **bắt buộc** của `AssertionConsumerService`. |
| `isDefault` | Xác định endpoint được dùng mặc định theo quy tắc metadata/profile khi thích hợp. |
| `ResponseLocation` | Thuộc tính tùy chọn của kiểu endpoint; không cần để diễn đạt ACS Web SSO thông thường. |

Nếu SP đăng ký nhiều ACS, `AuthnRequest` có thể đề nghị `AssertionConsumerServiceIndex` hoặc một địa chỉ ACS theo quy tắc giao thức; IdP phải đối chiếu với **đăng ký và metadata SP được tin cậy**. Không được lấy URL ACS bất kỳ do browser gửi tới để đưa SAML Response có thông tin nhạy cảm ra ngoài.

Thông thường IdP sinh HTML form có `action` trỏ về ACS và trình duyệt POST trường `SAMLResponse` (Base64 của XML). SP cần phân tích, kiểm tra **chữ ký, issuer, destination, recipient, audience, thời hạn, correlation, replay** rồi mới thiết lập phiên. ACS **không phải** endpoint để SP gửi `AuthnRequest` tới IdP.

### 3.1. `entityID` và ACS URL khác nhau

Giả sử IdP có cấu hình:

~~~text
SP Identifier / Audience: urn:example:sp:portal
Reply URL / ACS:        https://sp.example.org/login/saml2/sso/corporate
Response binding:       HTTP-POST
~~~

Assertion có `AudienceRestriction` tham chiếu **SP entityID**, trong khi `Response@Destination` và bearer `SubjectConfirmationData@Recipient` phải phù hợp **ACS URL** theo profile và cấu hình. Chữ ký và audience đúng **không thay được** kiểm tra đúng ACS/recipient. Đây là hai loại ràng buộc khác nhau.

## 4. SAML Binding là gì?

Binding quy định cách thông điệp SAML được gửi qua giao thức vận chuyển. Nó được biểu diễn bằng URI chuẩn, không đơn thuần bằng chữ `GET` hoặc `POST`.

| Binding | URI chuẩn | Cách dùng điển hình | Giới hạn/điều cần nhớ |
| --- | --- | --- | --- |
| **HTTP-Redirect** | `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect` | SP gửi `AuthnRequest` tới IdP SSO; SLO cũng có thể dùng. | Dữ liệu SAML được mã hóa trong query string (thường DEFLATE → Base64 → URL encode); giới hạn độ dài URL, chữ ký theo quy tắc Redirect binding. |
| **HTTP-POST** | `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST` | IdP gửi `Response` tới SP ACS; cũng dùng được với AuthnRequest hoặc SLO nếu cả hai hỗ trợ. | Form POST chứa `SAMLRequest` hoặc `SAMLResponse` Base64, thông thường xác minh chữ ký XML theo profile/chính sách. |
| **HTTP-Artifact** | `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Artifact` | Trình duyệt mang artifact, bên nhận lấy thông điệp đầy đủ qua kênh sau. | Cần artifact resolution với endpoint/back-channel được cấu hình, thường SOAP; đổi mỗi URI Binding không đủ để bật tính năng. |
| **SOAP** | `urn:oasis:names:tc:SAML:2.0:bindings:SOAP` | Artifact resolution hoặc profile back-channel. | Thông điệp trực tiếp giữa máy chủ, không phải redirect của trình duyệt. |

Một **metadata role** có thể công bố nhiều endpoint hỗ trợ nhiều binding. Chỉ những tổ hợp binding/endpoint mà cả SP và IdP triển khai mới nên được chọn. Chữ ký của HTTP-Redirect được bảo vệ theo cơ chế binding khác với XML Signature trong các thông điệp HTTP-POST; sử dụng parser/validator thư viện thay vì tự xác minh bằng cách decode Base64.

### 4.1. Hai chặng SSO có thể có binding khác nhau

~~~text
Bước 1: SP ---- AuthnRequest bằng HTTP-Redirect ----> IdP SSO
             chọn theo SingleSignOnService của IdP

Bước 2: IdP ---- SAML Response bằng HTTP-POST ------> SP ACS
             chọn theo AssertionConsumerService của SP
~~~

Đây là phối hợp **rất thường gặp và hợp lệ**. `Binding` của IdP SSO áp dụng cho **yêu cầu gửi đến IdP**, còn `Binding` của SP ACS áp dụng cho **phản hồi gửi về SP**. Vì thế thông báo lỗi “mismatch” không được suy ra chỉ vì một bên dùng Redirect, bên kia dùng POST.

### 4.2. `AuthnRequest@ProtocolBinding` chỉ binding của response

Trong `AuthnRequest`, `ProtocolBinding` (nếu có) thể hiện **binding SP muốn dùng để nhận SAML Response**, không phải binding dùng để vận chuyển chính `AuthnRequest`.

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-7a"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.org/saml/sso/redirect"
    AssertionConsumerServiceIndex="0"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"/>
~~~

Ví dụ này diễn đạt: request đi tới IdP SSO Redirect endpoint, nhưng response được mong đợi theo **POST binding tới ACS index 0**. Đây là trích đoạn diễn giải thuộc tính, **không phải AuthnRequest hoàn chỉnh** vì thiếu Issuer, trạng thái bảo vệ chữ ký và các phần khác theo profile.

**`RelayState` không phải binding hoặc endpoint.** Nó mang trạng thái liên quan giao dịch đi kèm SAML message. Trong SP-initiated SSO, RP/SP phải xác minh phản hồi thuộc **đúng yêu cầu và phiên trình duyệt khởi tạo**; `RelayState` hoặc `InResponseTo` từ callback không đủ nếu không đối chiếu dữ liệu đã lưu an toàn.

## 5. SingleLogoutService: SLO tồn tại ở cả hai chiều

Khác với SSO/ACS có vai trò chủ yếu một chiều, `SingleLogoutService` có thể xuất hiện trong **cả IDPSSODescriptor và SPSSODescriptor**, vì IdP hoặc SP đều có thể phải **nhận** `LogoutRequest` hoặc `LogoutResponse`.

Ví dụ:

~~~xml
<!-- SingleLogoutService bên trong IDPSSODescriptor -->
<md:SingleLogoutService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
    Location="https://idp.example.org/saml/slo"/>

<!-- SingleLogoutService bên trong SPSSODescriptor -->
<md:SingleLogoutService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://sp.example.org/logout/saml2/slo"/>
~~~

**`Location`** cho biết đích nhận thông điệp của dịch vụ logout. Một endpoint dạng SLO có thể thêm **`ResponseLocation`** để nhận **phản hồi** tại URL khác với đích nhận **yêu cầu**. Nếu không có `ResponseLocation`, phản hồi liên quan có thể được xử lý tại `Location` theo quy tắc metadata. Đây không phải một URL dự phòng để cân bằng tải.

### 5.1. SP-initiated SLO

1. Người dùng gửi yêu cầu logout tới SP; SP xác định phiên và IdP liên quan.
2. SP tạo, ký/bảo vệ `LogoutRequest` theo yêu cầu binding/profile và gửi tới **IdP SingleLogoutService**.
3. IdP xác minh, xử lý logout và trả `LogoutResponse` về **SP SingleLogoutService** phù hợp.
4. SP xác minh response (có thể có `InResponseTo`) và hoàn tất luồng logout/phản hồi trình duyệt theo chính sách.

### 5.2. IdP-initiated SLO

1. IdP gửi `LogoutRequest` tới **SP SingleLogoutService** qua binding đã hỗ trợ.
2. SP xác minh issuer/chữ ký, `Destination`, NameID/SessionIndex khi có, tìm và hủy phiên liên quan.
3. SP phát `LogoutResponse` tới **IdP SingleLogoutService** phù hợp.

**SLO khác với local logout:** chỉ xóa cookie phiên SP không tự đăng xuất mọi phiên tại IdP/SP khác. Mặt khác, một request SLO được gửi đi cũng không bảo đảm mọi ứng dụng đã logout thành công: có thể không hỗ trợ, mạng lỗi hoặc trả partial logout. Hệ thống phải có chính sách xử lý lỗi, timeout và audit.

Với Spring Security, endpoint nhận SLO không phải ACS. Nếu định tuyến LogoutResponse về `/login/saml2/sso/...`, SP sẽ xử lý sai loại thông điệp hoặc từ chối.

## 6. Bảng ánh xạ thường gặp khi cấu hình đối tác

Giao diện quản trị của các IdP dùng nhiều thuật ngữ khác nhau. Ánh xạ dựa trên **bên phát / bên nhận**, tránh suy diễn từ chữ “SSO URL”:

| Tên trong màn hình cấu hình | Giá trị lấy từ đâu? |
| --- | --- |
| **IdP Sign-in URL / IdP SSO URL** | `IDPSSODescriptor/SingleSignOnService/@Location` của binding tương ứng. |
| **IdP Issuer / Entity ID** | `EntityDescriptor/@entityID` của IdP. |
| **SP Identifier / Audience URI / SP Entity ID** | `EntityDescriptor/@entityID` của SP. |
| **Reply URL / Assertion Consumer URL / ACS URL** | `SPSSODescriptor/AssertionConsumerService/@Location`. |
| **Response Binding / ACS Binding** | `AssertionConsumerService/@Binding`, thường là HTTP-POST. |
| **IdP Logout URL** | `IDPSSODescriptor/SingleLogoutService/@Location` hoặc ResponseLocation khi phù hợp. |
| **SP Logout Callback URL** | `SPSSODescriptor/SingleLogoutService/@Location` hoặc ResponseLocation nếu đã cấu hình. |
| **Certificate verifying IdP signatures** | `KeyDescriptor` của IdP từ metadata **đã xác lập tin cậy**. |
| **Metadata URL** | Điểm tải XML metadata bên cung cấp, **không phải endpoint thực hiện SSO**. |

Ví dụ một liên kết:

~~~text
SP entity ID:           urn:example:sp:portal
IdP entity ID:          urn:example:idp:corporate
IdP SSO (Redirect):     https://idp.example.org/saml/sso/redirect
SP ACS (POST):          https://sp.example.org/login/saml2/sso/corporate
IdP SLO (Redirect):     https://idp.example.org/saml/slo
SP SLO (POST):          https://sp.example.org/logout/saml2/slo
~~~

Trong tình huống này, SP gửi AuthnRequest qua Redirect đến **IdP SSO**, IdP POST Response về **SP ACS**. Khi SP chủ động logout liên kết, nó có thể gửi LogoutRequest qua Redirect tới **IdP SLO**, rồi nhận LogoutResponse qua **SP SLO** theo binding đã được hai bên hỗ trợ. Cần tách riêng hai đối tượng **endpoint** và **giao thức chuyển thông điệp** để cấu hình đúng.

## 7. SAML endpoints trong Spring Security Servlet

Spring Security cung cấp `RelyingPartyRegistration` chứa cấu hình SP và metadata IdP. Ứng dụng Servlet dùng `saml2Login` để tạo AuthnRequest/nhận Response, `saml2Metadata` để xuất SP metadata, và `saml2Logout` khi cần phối hợp SLO.

| Đường dẫn Spring Security thường dùng | Chức năng |
| --- | --- |
| `/saml2/authenticate/{registrationId}` | **Điểm kích hoạt tại SP**: sinh/gửi AuthnRequest đến IdP SSO. Không phải một `SingleSignOnService` của SP. |
| `/login/saml2/sso/{registrationId}` | **SP ACS**: nhận `SAMLResponse` và xác thực. |
| `/logout/saml2/slo` | **SP SLO** khi được bật: nhận LogoutRequest/LogoutResponse. |
| `/saml2/metadata` | **Phát hành metadata SP**; không phải endpoint dùng để login/logout. |
| `/saml2/metadata/{registrationId}` | Phát hành metadata cho registration cụ thể; có thêm biến thể `/saml2/service-provider-metadata/{registrationId}`. |
| `POST /logout` | Yêu cầu logout từ ứng dụng; có thể khởi tạo SLO **nếu** đã bật và registration hỗ trợ. |

Những đường dẫn là **mặc định/biến thể trong tài liệu Spring Security Servlet hiện hành**; có thể khác khi tùy biến cấu hình hoặc giữa các phiên bản. Handler nhận SAML Response thực tế và `AssertionConsumerService.Location` công bố **phải nhất quán**.

### 7.1. Cấu hình IdP metadata và SP SLO

Ví dụ `application.yml` trong **ứng dụng Spring Boot** có `spring-security-saml2-service-provider`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
            signing:
              credentials:
                - private-key-location: classpath:credentials/sp-signing.key
                  certificate-location: classpath:credentials/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

Ví dụ giả định hệ thống **đã có** khóa riêng, chứng thư X.509, metadata IdP và hỗ trợ SLO hợp lệ. Các file trong `credentials/` là những vị trí giả định cho ứng dụng triển khai; không có dữ liệu bí mật nào được cung cấp trong bài. Khi chỉ cần SSO ban đầu và IdP không hỗ trợ SLO, không nên khai báo SLO/signing như thể nó đã hoạt động.

### 7.2. Cấu hình `SecurityFilterChain`

Tệp `src/main/java/example/federation/SamlEndpointsSecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlEndpointsSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **cấu hình Spring Security trong project Spring Boot**, **không thể biên dịch độc lập bằng `javac`** khi không có thư viện Spring và registration thực tế. `saml2Login` xử lý SSO, `saml2Metadata` cho phép xuất SP metadata, `saml2Logout` bật cơ chế SLO khi registration và IdP hỗ trợ. Không tự tạo servlet controller nhận XML SAML rồi bỏ qua validation của framework.

Các thành phần quan trọng ở runtime:

- `Saml2WebSsoAuthenticationRequestFilter`: xử lý điểm khởi tạo, tạo/gửi `AuthnRequest`, dựa trên cấu hình IdP SSO.
- `Saml2AuthenticationRequestRepository`: giữ yêu cầu đang chờ và trạng thái tương quan (mặc định dùng HttpSession trong triển khai phổ biến).
- `Saml2WebSsoAuthenticationFilter` cùng authentication provider: xử lý response tại ACS, xác minh trước khi tạo phiên.
- `Saml2MetadataFilter`/cấu hình `saml2Metadata`: phát hành XML SP metadata.
- Các filter/resolver SAML logout: xử lý `LogoutRequest` và `LogoutResponse` theo registration và khóa/tin cậy đã cấu hình.

**Nếu tùy biến `loginProcessingUrl`**, cũng phải cập nhật `assertionConsumerServiceLocation` trong `RelyingPartyRegistration` hoặc cấu hình tương ứng, sau đó đăng ký lại metadata/ACS tại IdP. Nếu đổi đường dẫn SLO, chỉnh runtime handler **và** `SingleLogoutService.Location` của SP; không chỉ sửa một nơi.

### 7.3. Hostname và reverse proxy

SP có thể chạy nội bộ tại `http://localhost:8080` nhưng người dùng truy cập `https://sp.example.org`. Nếu metadata xuất `http://localhost:8080/login/saml2/sso/corporate`, IdP sẽ chuyển response đến địa chỉ không dùng được bên ngoài hoặc validator phát hiện `Destination`/`Recipient` không đúng. Cần cấu hình public `{baseUrl}`, trust các forwarded headers chỉ từ proxy phù hợp và **đọc lại SP metadata đã xuất** để kiểm tra entity ID, ACS, SLO đều dùng host/scheme/context path công khai.

Khi IdP gửi SAML Response bằng cross-site HTTP-POST, cookie phiên của trình duyệt có thể bị ảnh hưởng bởi `SameSite`. Khắc phục bằng cơ chế session/correlation và cấu hình cookie phù hợp, **không vô hiệu hóa kiểm tra `InResponseTo`** để cho callback đi qua.

## 8. Metadata công bố khả năng, không tự tạo sự tin cậy

Metadata có thể chứa `KeyDescriptor` với khóa signing/encryption, các endpoint, binding và thời hạn metadata. Nhưng **đọc được XML không có nghĩa đối tác được phép tin cậy**.

Khi triển khai phải:

1. Chỉ nhận metadata IdP từ nguồn quản trị **đã được cấp phép và xác thực**; xác minh chữ ký metadata bằng trust anchor được tin cậy nếu áp dụng. Không coi chứng thư bên trong XML chưa xác thực là bằng chứng tự tin chính XML ấy.
2. Khóa xác minh `Response`/`Assertion` phải lấy từ đối tác được đăng ký, kiểm tra mục đích khóa và kế hoạch **certificate rotation**; quản lý `validUntil`, `cacheDuration` và thời điểm refresh hợp lý.
3. Không dùng `entityID`, `Location` hoặc ACS URL nhận từ request chưa xác minh để tự động tạo một đăng ký SAML mới.
4. Xác minh XML signature đúng đối tượng, issuer, `Destination`, `Recipient`, audience, `Conditions` (bao gồm thời hạn), `SubjectConfirmation` và chống replay; sử dụng thư viện SAML đáng tin cậy.
5. Với SP-initiated SSO, `InResponseTo` phải trỏ tới `AuthnRequest` đã lưu trong **phiên/giao dịch trình duyệt khởi tạo**, không chỉ dựa vào `RelayState` từ callback.
6. Nếu cho phép IdP-initiated SSO không có AuthnRequest trước, phải áp dụng **chính sách riêng**; không tự chuyển giao dịch SP-initiated thất bại sang chế độ unsolicited để bypass ràng buộc.
7. Với SLO, kiểm tra issuer/chữ ký/destination, NameID/SessionIndex và trạng thái request-response phù hợp; không logout nhầm phiên.
8. Không bỏ validator để “sửa” lỗi cấu hình endpoint. Phải sửa đúng metadata, khóa, binding hoặc runtime handler đang không khớp.

Metadata chỉ hỗ trợ thiết lập **địa chỉ và quan hệ tin cậy**; sau khi đăng nhập, quyền vào API, tài nguyên, tenant và bản ghi vẫn do lớp authorization của SP/API kiểm tra.

## 9. Lỗi tích hợp thường gặp và phương pháp kiểm tra

| Triệu chứng | Nguyên nhân có thể xảy ra | Kiểm tra phù hợp |
| --- | --- | --- |
| SP gửi `AuthnRequest` tới URL của chính SP. | Nhầm `AssertionConsumerService.Location` với IdP `SingleSignOnService.Location`. | Theo dõi điểm gửi của request; phải là **IdP SSO**. |
| IdP báo “ACS mismatch”, “Reply URL invalid”. | ACS không đúng metadata/registration IdP, sai scheme/hostname/port/path. | So sánh ACS Location, cấu hình IdP, URL public sau proxy. |
| IdP chấp nhận request Redirect nhưng callback POST lỗi 404/405. | Runtime SP thiếu ACS handler hoặc không nhận binding/method đã công bố. | Kiểm tra SP `AssertionConsumerService.Binding/Location` và route thực tế. |
| Login lỗi vì “SSO Redirect khác ACS POST”. | Đánh đồng binding của hai chặng. | Redirect áp dụng SP→IdP, POST áp dụng IdP→SP; khác nhau vẫn hợp lệ. |
| `AudienceRestriction` thất bại. | SP entityID không khớp audience assertion. | Đọc SP `EntityDescriptor/@entityID`, không so audience với ACS URL. |
| `Destination`/`Recipient` không khớp. | IdP trả về sai ACS URL hoặc proxy làm sai public URL. | So khớp SAML Response/SubjectConfirmationData với ACS công bố. |
| Không tìm được `AuthnRequest` chờ / `InResponseTo` mismatch. | Mất session/cookie, thay đổi transaction, callback sai trình duyệt. | Kiểm tra correlation, cookie SameSite, TTL, storage nhiều instance. |
| `POST /logout` thành công nhưng IdP vẫn còn đăng nhập. | Chỉ logout local, thiếu SLO metadata/khóa/feature. | Xem cả IdP và SP SLO endpoints, `saml2Logout`, registration signing credentials. |
| `LogoutResponse` gửi tới ACS. | Nhầm endpoint SLO của SP với endpoint ACS. | Kiểm tra `SingleLogoutService.Location/ResponseLocation` của bên nhận. |
| Response/XML có chữ ký nhưng SP vẫn từ chối. | Audience, issuer, thời hạn, recipient, binding hoặc `InResponseTo` sai. | Kiểm tra từng validator, không bỏ qua signature/correlation. |
| Sau certificate rotation login đồng loạt lỗi. | Metadata/key tin cậy không được cập nhật đúng lúc. | Quản lý refresh, chứng thư trong `KeyDescriptor`, rollover an toàn. |
| Metadata phát ra URL `localhost`. | SP sinh metadata từ scheme/host nội bộ sau proxy. | Điều chỉnh external base URL và forwarded headers, xuất XML kiểm lại. |

### Kiểm thử luồng SSO và SLO

1. **SSO bình thường:** người dùng vào SP → gửi AuthnRequest đúng IdP SSO binding/location → IdP POST Response tới đúng SP ACS → session hợp lệ.
2. **Binding không được hỗ trợ:** cấu hình IdP chỉ nhận HTTP-Redirect nhưng SP cố POST AuthnRequest. Mong đợi: lỗi cấu hình/đăng nhập; không tự gửi tới endpoint khác không được đăng ký.
3. **Sai ACS:** IdP POST tới URL cũ hoặc URL không đúng. Mong đợi: không tạo phiên, phân tích nguyên nhân ở cấu hình đối tác/proxy.
4. **Sai audience/destination:** assertion dành entityID khác hoặc URL khác. Mong đợi: từ chối dù chữ ký còn hợp lệ.
5. **Response phát lại/sai phiên:** `InResponseTo` không khớp hoặc dùng lại response. Mong đợi: từ chối, không bỏ qua correlation.
6. **SLO từ SP và từ IdP:** cả hai hướng phải dùng đúng SLO `Location`/`ResponseLocation`, binding, chữ ký và phiên liên quan; xử lý cả lỗi/partial logout.
7. **Key rotation/metadata expiry:** sau cập nhật metadata đã tin cậy, giao dịch vẫn xác minh đúng, không nhận khóa lạ từ callback.

### Câu hỏi tự kiểm

- **IdP cần URL nào để gửi SAML Response?** SP `AssertionConsumerService.Location`, với binding đã thống nhất.
- **SP cần URL nào để gửi AuthnRequest?** IdP `SingleSignOnService.Location`, theo binding của mục đó.
- **Nếu IdP SSO dùng HTTP-Redirect, ACS có được dùng HTTP-POST không?** Có; hai chặng độc lập.
- **Trong `AuthnRequest`, `ProtocolBinding=HTTP-POST` nói về chặng nào?** Binding IdP dùng để trả **Response tới ACS**.
- **Vì sao cả IdP và SP có SLO endpoint?** Vì mỗi bên có thể phải nhận LogoutRequest/LogoutResponse.
- **`ResponseLocation` của SLO có phải đường dẫn dự phòng không?** Không; nó phân biệt đích nhận response với đích nhận request nếu được cung cấp.
- **Metadata URL có thể dùng làm ACS URL không?** Không; metadata URL cung cấp XML cấu hình, ACS nhận response SAML thực tế.

## 10. Ghi nhớ

- **SSO = IdP nhận yêu cầu đăng nhập**, **ACS = SP nhận kết quả đăng nhập**, **SLO = bên nhận thông điệp đăng xuất**.
- **Binding + Location** là cặp cần đi cùng nhau và thuộc đúng role trong metadata.
- **Entity ID**, metadata URL, ACS, SSO và SLO là các định danh/địa chỉ **khác trách nhiệm**.
- **SSO request binding** và **ACS response binding** có thể khác nhau.
- **Spring Security** có filter cho AuthnRequest, ACS, SLO và phát hành metadata, nhưng metadata phải khớp **runtime handler và đối tác đã cấu hình**.
- **Chữ ký hợp lệ, endpoint đúng, correlation đúng và thời hạn còn hiệu lực** đều cần cho một lần đăng nhập an toàn.

## Tài liệu tham khảo

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html)
- [Spring Security — SAML AuthnRequest](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html)
- [OASIS SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Errata 05 — ResponseLocation](https://docs.oasis-open.org/security/saml/v2.0/errata05/csd01/saml-v2.0-errata05-csd01.html)
