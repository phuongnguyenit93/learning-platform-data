# Kiểm tra AudienceRestriction và SubjectConfirmation Recipient trong SAML2

> **Chủ đề:** Spring Security – federation. **Mạch kiến thức:** Kiểm chứng SAML2. Bài trình bày hai ràng buộc độc lập nhưng bắt buộc phải hiểu cùng nhau khi một Service Provider (SP/Relying Party) tiếp nhận SAML Response từ Identity Provider (IdP/Asserting Party): **`<AudienceRestriction>` trong Assertion Conditions** và **`Recipient` của bearer `<SubjectConfirmationData>`**. Phạm vi chính là SAML 2.0 Web Browser SSO với ứng dụng Java 17+/Spring Security.

## 1. Kết quả học tập và vấn đề cần giải quyết

Sau khi học, bạn có thể:

1. Nêu chính xác **AudienceRestriction giới hạn ai được sử dụng assertion**, còn **Recipient xác định ACS endpoint được phép nhận bearer assertion**.
2. Phân biệt **SP entityID**, **Assertion Consumer Service (ACS) URL**, `Response/@Destination`, `Issuer` và `InResponseTo`; biết giá trị nào phải so sánh với giá trị nào.
3. Giải thích tại sao assertion **chữ ký hợp lệ** nhưng có `Audience` hoặc `Recipient` sai phải bị từ chối.
4. Đọc cấu trúc SAML XML để nhận biết `Conditions`, `AudienceRestriction`, `SubjectConfirmation` và `SubjectConfirmationData`; hiểu các ràng buộc thời gian, correlation và replay.
5. Biết cách quản lý entityID/ACS/certificate của SP qua `RelyingPartyRegistration` trong Spring Security, kể cả phía sau HTTPS reverse proxy.
6. Tạo kiểm thử **happy path và fail-closed** khi audience sai, recipient sai, timestamp sai, response gửi sang SP/tenant khác, request ID không khớp.
7. Tránh sai sót phổ biến: lấy ACS URL làm audience, lấy IdP entityID làm audience, chỉ kiểm tra hostname, sửa XML đã ký rồi kết luận từ lỗi signature, bỏ validation để chữa lỗi proxy.

**Thông điệp chính:** Có ba câu hỏi độc lập phải trả lời đúng: **“Ai phát hành?”** (issuer + trusted signing key), **“Phát hành cho ứng dụng nào?”** (`AudienceRestriction`) và **“Bearer assertion có thể giao tới đâu?”** (`SubjectConfirmationData Recipient`). Chữ ký của IdP **không thay thế** hai kiểm tra sau.

## 2. Hệ thống ví dụ và các định danh

Giả sử có một IdP và hai ứng dụng web riêng, mỗi ứng dụng đều đăng ký liên kết SAML với IdP:

| Thành phần | Định danh/đường dẫn minh họa | Vai trò |
| --- | --- | --- |
| **IdP** | `https://idp.example.org/issuer` | IdP `entityID`; khẳng định nguồn phát hành |
| **SP A** | `https://pay.example.org/saml2/service-provider-metadata/pay` | SP A `entityID`, định danh logic của ứng dụng nhận |
| **ACS của SP A** | `https://pay.example.org/login/saml2/sso/pay` | URL thực tế browser POST `SAMLResponse` của SP A |
| **SP B** | `https://hr.example.org/saml2/service-provider-metadata/hr` | SP B `entityID`, **khác** SP A |
| **ACS của SP B** | `https://hr.example.org/login/saml2/sso/hr` | URL ACS của SP B, **khác** SP A |
| **registrationId nội bộ Spring của SP A** | `pay` | Khóa tra cứu một `RelyingPartyRegistration`, **không phải entityID** |
| **registrationId nội bộ Spring của SP B** | `hr` | Khóa tra cứu một registration khác |

Ở môi trường của bạn, `entityID` có thể là một URN như `urn:company:application:pay`, **không nhất thiết là URL có thể GET**. Mặc định trong nhiều cấu hình Spring, entityID được tạo từ `{baseUrl}/saml2/service-provider-metadata/{registrationId}`, nhưng có thể tùy chỉnh độc lập với ACS. Vì vậy **không được suy ra Audience từ ACS hoặc ngược lại**.

### 2.1. Hai trường cần xác minh nằm ở đâu?

```text
SAML Response (trình duyệt POST tới SP A ACS)
  |
  +-- Response/@Destination = https://pay.example.org/login/saml2/sso/pay
  +-- Response/Issuer       = https://idp.example.org/issuer
  |
  +-- Assertion (được IdP ký hoặc nằm trong Response được ký)
       |
       +-- Assertion/Issuer = https://idp.example.org/issuer
       |
       +-- Subject
       |    +-- SubjectConfirmation Method="...:bearer"
       |          +-- SubjectConfirmationData
       |                Recipient    = https://pay.example.org/login/saml2/sso/pay
       |                InResponseTo = _request-123
       |                NotOnOrAfter = ... (thời điểm hết hạn xác nhận chủ thể)
       |
       +-- Conditions
            +-- AudienceRestriction
                  +-- Audience = https://pay.example.org/saml2/service-provider-metadata/pay
```

**Chú ý:** `Response/@Destination` và `SubjectConfirmationData/@Recipient` thường cùng là **ACS URL** trong browser SSO, còn `Audience` là **SP entityID**, thường khác ACS URL. Chúng là các ràng buộc riêng, không nên gộp thành một phép so sánh.

### 2.2. Luồng kiểm chứng

```text
(1) User truy cập /private trên SP A
        |
(2) SP A sinh AuthnRequest, lưu ID _request-123 và trạng thái tương ứng
        |
(3) Browser đến IdP, người dùng xác thực
        |
(4) IdP phát Response và Assertion cho SP A
        |    Issuer            = IdP entityID
        |    Audience          = SP A entityID
        |    Recipient         = SP A ACS
        |    InResponseTo      = _request-123
        |    Thời hạn          = còn hiệu lực
        |
(5) Browser POST SAMLResponse tới SP A ACS
        |
(6) Spring Security/OpenSAML kiểm tra chữ ký, nguồn phát,
    destination, conditions, subject confirmation,
    correlation, thời gian và các điều kiện áp dụng
        |
      VALID? ------- Không -----> TỪ CHỐI, không tạo Authentication
        |
       Có
        v
(7) Tạo Authentication/session tại SP A; tiếp tục phân quyền nghiệp vụ
```

Nếu cùng response bị chuyển sang ACS của SP B, **SP B phải từ chối** bởi audience dành cho SP A và/hoặc recipient/destination không dành cho SP B, dù hai SP cùng tin cùng một IdP.

## 3. `AudienceRestriction`: “Assertion này dành cho SP nào?”

### 3.1. Cấu trúc và mục đích

Trong SAML 2.0, `Conditions` của `Assertion` có thể chứa một hoặc nhiều `AudienceRestriction`, và mỗi `AudienceRestriction` chứa các phần tử `Audience`. Trong Web Browser SSO bearer profile, assertion được sử dụng phải có audience restriction phù hợp với SP. Ví dụ:

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                 NotBefore="2030-03-10T10:00:00Z"
                 NotOnOrAfter="2030-03-10T10:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://pay.example.org/saml2/service-provider-metadata/pay</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
```

Giải thích:

- `Audience` không mô tả “người dùng nào” hoặc “nhóm quyền nào”; nó mô tả **đối tượng được phép dùng assertion**.
- SP đối chiếu với **chính entityID của mình**, đã đăng ký và được IdP phê duyệt, không lấy tùy tiện `Host` header hoặc tên tenant do request tự khai báo.
- Không dùng cách so khớp chuỗi lỏng `startsWith("https://pay.example.org")`, `contains("pay")` hoặc xóa phần path. Một tên miền có thể phục vụ nhiều SP/entityID khác nhau.
- Không chấp nhận audience mang **IdP entityID** chỉ vì IdP là nguồn phát: `Issuer` và `Audience` có vai trò khác nhau.
- Một audience hợp lệ **không cho phép** assertion trở thành bearer token dùng để gọi OAuth Resource Server/API bất kỳ. SAML browser SSO có tiêu chí và endpoint riêng.

### 3.2. Luật OR/AND khi có nhiều AudienceRestriction

Theo SAML 2.0 và errata: **nhiều `Audience` bên trong cùng một `AudienceRestriction` là quan hệ OR**, nhưng **nhiều `AudienceRestriction` độc lập trong cùng assertion là quan hệ AND** (phải thỏa từng điều kiện).

Ví dụ 1 — OR trong một condition:

```xml
<saml:AudienceRestriction xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Audience>urn:example:sp:pay</saml:Audience>
  <saml:Audience>urn:example:sp:billing</saml:Audience>
</saml:AudienceRestriction>
```

Nếu SP entityID là `urn:example:sp:pay`, condition này thỏa. Nếu SP entityID là `urn:example:sp:hr`, condition này không thỏa.

Ví dụ 2 — AND giữa hai condition:

```xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:pay</saml:Audience>
    <saml:Audience>urn:example:sp:billing</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:pay</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
```

Với SP `urn:example:sp:pay`, cả hai condition đều thỏa. Với SP `urn:example:sp:billing`, condition đầu thỏa nhưng condition thứ hai không thỏa, nên **toàn bộ phần audience restriction không hợp lệ**. Một validator chỉ gom tất cả audience của mọi condition thành một tập duy nhất rồi kiểm tra “có chứa entityID” sẽ tạo false positive.

**Thực hành an toàn:** Để thư viện SAML kiểm tra các conditions theo đúng semantics. Không tự code parser String/regex rồi chọn phần tử `Audience` đầu tiên hoặc bất kỳ phần tử khớp nào mà bỏ qua condition khác.

### 3.3. Nếu thiếu `AudienceRestriction`?

Trong profile Web Browser SSO bearer, bearer assertion phải có `AudienceRestriction` chứa SP identifier. Vì vậy, khi tích hợp browser SSO, một assertion thiếu ràng buộc audience là **lỗi cấu hình/phát hành cần từ chối**, không phải cơ hội để “bỏ qua vì IdP đã ký”. Ở những profile SAML khác, quy tắc sử dụng assertions có thể khác; không khái quát tùy tiện từ browser SSO cho mọi trường hợp.

Nếu IdP phát audience sai, hãy sửa **cấu hình SP Entity ID / Audience URI / Relying Party Identifier ở IdP** cho trùng entityID đã xuất bản, không đổi SP entityID cho khớp ngẫu nhiên assertion giả hoặc loại bỏ audience validator.

## 4. `SubjectConfirmationData Recipient`: “Bearer assertion này được chuyển tới ACS nào?”

### 4.1. Bearer SubjectConfirmation và dữ liệu ràng buộc

Ở browser SSO, bearer assertion phải có `SubjectConfirmation` với:

```text
Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"
```

Bên trong, `SubjectConfirmationData` xác định điều kiện mà một SP được phép dùng để **xác nhận người mang assertion chính là chủ thể được IdP khẳng định**. Ví dụ:

```xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID>user-42</saml:NameID>
  <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
        Recipient="https://pay.example.org/login/saml2/sso/pay"
        InResponseTo="_request-123"
        NotOnOrAfter="2030-03-10T10:04:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
```

Trong Web Browser SSO bearer profile:

- **`Recipient` phải chỉ đúng ACS URL mà SAML Response được đưa tới**, ví dụ `https://pay.example.org/login/saml2/sso/pay`.
- **`NotOnOrAfter`** đặt thời điểm hết hiệu lực của việc xác nhận bearer, là ràng buộc riêng với thời gian của `Conditions`. Khi đến mốc này, xác nhận không còn hợp lệ (có thể có dung sai đồng hồ được chính sách cho phép).
- **`InResponseTo`** khi response là đáp ứng của một `AuthnRequest` phải khớp ID của request đã được SP khởi tạo và theo dõi. Với unsolicited/IdP-initiated SSO theo profile, ràng buộc này không được có; bên nhận phải có chính sách rõ có chấp nhận luồng không yêu cầu trước hay không.
- **`Address`**, nếu được IdP gửi, có thể hạn chế địa chỉ IP phía browser; phải hiểu giới hạn của NAT/proxy và hành vi kiểm tra theo profile. Không xem nó là tiêu chí thay thế Recipient/audience.
- Đối với **bearer Web Browser SSO**, `SubjectConfirmationData` không được dùng `NotBefore` theo profile; cần phân biệt điều này với `Conditions/NotBefore` hợp lệ trong assertion.
- Có thể có **nhiều** `SubjectConfirmation`. SP phải tìm được ít nhất một bearer confirmation hợp lệ theo profile và kiểm tra độc lập các điều kiện của nó; không chấp nhận một phần từ confirmation A cộng một phần từ confirmation B thành một confirmation “tưởng tượng”.

**Điểm tinh tế:** `Recipient` không phải một “whitelist domain” chung. `https://pay.example.org/login/saml2/sso/pay` khác `https://pay.example.org/other`, khác `http://pay.example.org/login/saml2/sso/pay` và khác ACS của tenant khác. Chỉ kiểm tra hostname hoặc path prefix sẽ bỏ sót sai đích.

### 4.2. Đối chiếu Recipient với cái gì?

Không đối chiếu `Recipient` với:

- IdP `entityID`.
- `AudienceRestriction/Audience`.
- URL đăng nhập `/saml2/authenticate/{registrationId}` của SP (điểm **khởi tạo** AuthnRequest).
- URL metadata SP `/saml2/metadata/{registrationId}`, trừ khi ứng dụng vô tình dùng một cấu hình ACS không chuẩn trùng URL đó (không nên).
- Header `Referer`/`Origin` hay raw `Host` không được kiểm soát từ phía browser.

Cần đối chiếu với **ACS URL thực tế/được đăng ký** mà SP đang phục vụ theo đúng RP registration và route của SAML Response. Trong Spring Security, khái niệm tương ứng là `RelyingPartyRegistration.getAssertionConsumerServiceLocation()` sau khi resolve giá trị URL/deployment và được dùng bởi provider/validation.

Với nhiều ACS/binding hợp lệ, lựa chọn ACS nào đã nhận response phải ràng buộc với registration, binding và hợp đồng IdP; không “cho qua nếu Recipient trùng một URL bất kỳ trong toàn hệ thống”. Mỗi tenant/SP phải bị giới hạn vào chính các ACS đã được phê duyệt cho nó.

### 4.3. Vì sao cần kiểm tra cả Audience và Recipient?

Một hệ thống nhiều SP dùng chung IdP có nguy cơ **cross-service assertion replay**: người tấn công cố đưa SAMLResponse đã phát cho SP A sang SP B. Nếu chỉ kiểm tra chữ ký IdP thì response vẫn có thể hợp lệ về mật mã. Nếu chỉ kiểm tra Audience, vẫn có thể có lỗi đưa response vào ACS sai của cùng SP/tenant hoặc route nhầm. Nếu chỉ kiểm tra Recipient, SP có thể bỏ sót trường hợp assertion không dành cho application entityID của mình.

Kết luận đúng phải là phép **AND của các thuộc tính độc lập**, không lựa chọn “Audience **hoặc** Recipient”.

## 5. Bốn trường dễ nhầm: Issuer, Audience, Destination, Recipient

| Trường SAML | Vị trí | Giá trị SP A mong đợi | Câu hỏi bảo mật |
| --- | --- | --- | --- |
| **Issuer** | `Response/Issuer` và `Assertion/Issuer` | `https://idp.example.org/issuer`, thuộc IdP được cấu hình | Bằng chứng đến từ nhà phát hành nào? |
| **Audience** | `Assertion/Conditions/AudienceRestriction/Audience` | `https://pay.example.org/saml2/service-provider-metadata/pay` | Assertion này cấp cho SP entityID nào? |
| **Destination** | `Response/@Destination` | `https://pay.example.org/login/saml2/sso/pay` | Toàn bộ SAML Response được chỉ định gửi tới địa chỉ nào? |
| **Recipient** | `Assertion/Subject/SubjectConfirmation/SubjectConfirmationData/@Recipient` | `https://pay.example.org/login/saml2/sso/pay` | Bearer assertion được phép xác nhận ở ACS URL nào? |
| **InResponseTo** | `Response/@InResponseTo` và `SubjectConfirmationData/@InResponseTo` khi áp dụng | `_request-123` đã phát và lưu | Đây có phải câu trả lời cho AuthnRequest đúng phiên không? |
| **NotOnOrAfter** | `Conditions` và `SubjectConfirmationData` (hai vị trí riêng) | Tương lai so với thời điểm nhận trong chính sách skew | Assertion và việc xác nhận bearer còn hiệu lực không? |

**Issuer là bên phát**, **Audience là định danh SP**, **Destination và Recipient là URL ACS**. Trong trường hợp điển hình, Destination và Recipient trùng nhau, nhưng sự trùng khớp không khiến một kiểm tra trở thành thừa: chúng nằm ở cấp độ message và subject confirmation khác nhau.

**Cảnh báo về chữ ký XML:** Việc lấy một trường từ XML chưa được xác minh chữ ký, sau đó so sánh đúng chuỗi, không chứng minh trường đó thực sự được IdP khẳng định. Cần xác minh chữ ký hợp lệ **bao phủ đúng nội dung assertion/response mà application sử dụng**, tránh XML signature wrapping và lựa chọn sai element. Spring Security tích hợp OpenSAML để xử lý việc này; không tự parse Base64 thành XML rồi tin các trường chỉ vì chúng có vẻ đúng.

## 6. Cấu trúc SAML Response tổng hợp để học cách đối chiếu

Đoạn sau là **tài liệu minh họa, KHÔNG phải SAMLResponse hợp lệ để đem đăng nhập**: không chứa `ds:Signature`, bộ thuộc tính/protocol hoàn chỉnh và credential được tin cậy. Mục đích là cho thấy vị trí từng trường.

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-10"
    Version="2.0"
    IssueInstant="2030-03-10T10:00:00Z"
    InResponseTo="_request-123"
    Destination="https://pay.example.org/login/saml2/sso/pay">
  <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion
      ID="_assertion-20"
      Version="2.0"
      IssueInstant="2030-03-10T10:00:00Z">
    <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user-42</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://pay.example.org/login/saml2/sso/pay"
            InResponseTo="_request-123"
            NotOnOrAfter="2030-03-10T10:04:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions
        NotBefore="2030-03-10T09:59:00Z"
        NotOnOrAfter="2030-03-10T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://pay.example.org/saml2/service-provider-metadata/pay</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement
        AuthnInstant="2030-03-10T10:00:00Z"/>
  </saml:Assertion>
</samlp:Response>
```

Dùng các giá trị minh họa trên, ở thời điểm `2030-03-10T10:01:00Z`, nếu IdP/khóa ký/trạng thái/correlation đều hợp lệ và các điều kiện khác đạt, hai đối chiếu chính là:

```text
expectedAudience =
  "https://pay.example.org/saml2/service-provider-metadata/pay"
actualAudience =
  "https://pay.example.org/saml2/service-provider-metadata/pay"
=> khớp

expectedACS =
  "https://pay.example.org/login/saml2/sso/pay"
actualRecipient =
  "https://pay.example.org/login/saml2/sso/pay"
=> khớp

actualDestination =
  "https://pay.example.org/login/saml2/sso/pay"
=> khớp ACS

actualInResponseTo = "_request-123"
=> khớp ID AuthnRequest đã lưu
```

Đừng thử gửi đoạn XML trên vào ACS để kiểm tra login: nó không có chữ ký và các yếu tố cần thiết; Spring phải từ chối. Để kiểm chứng **riêng audience/recipient**, cần assertion được **IdP thử nghiệm ký hợp lệ**, chỉ thay đúng claim/URL mục tiêu rồi ký lại.

## 7. Spring Security xác minh những gì và ở đâu?

### 7.1. Đường xử lý mặc định

Ở Spring Security SAML2 Servlet Web SSO:

1. `Saml2WebSsoAuthenticationRequestFilter` khởi tạo `AuthnRequest` ở URL tương ứng, ví dụ `/saml2/authenticate/pay`, và lưu correlation theo cấu hình.
2. Browser được IdP xác thực và POST `SAMLResponse` tới ACS `/login/saml2/sso/pay`.
3. `Saml2WebSsoAuthenticationFilter` xử lý request, tạo `Saml2AuthenticationToken` và resolve `RelyingPartyRegistration`.
4. Authentication provider dựa trên OpenSAML kiểm tra chữ ký, issuer, destination, assertion conditions (bao gồm audience restriction), subject confirmation cùng các điều kiện áp dụng. Một lỗi kiểm chứng làm xác thực thất bại.
5. Chỉ khi xác thực thành công, `SecurityContext`/session mới được thiết lập; controller và phân quyền nghiệp vụ tiếp tục xử lý.

Các tên class/provider OpenSAML và API tùy chỉnh có thể khác giữa Spring Security 6.x, 7.x và cấu hình dependency; tham chiếu tài liệu **đúng bản đang dùng**. Bài không thay default validator bằng logic tự viết: kiểm chứng SAML là chức năng bảo mật trọng yếu, cần để framework và OpenSAML thực hiện theo tiêu chuẩn.

### 7.2. Cấu hình SP entityID và ACS trong Spring Boot

Giả sử có Java 17+, Spring Boot servlet stack tương thích, dependency `spring-security-saml2-service-provider` và IdP test đã được phê duyệt. File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          pay:
            entity-id: "https://pay.example.org/saml2/service-provider-metadata/pay"
            assertion-consumer-service-location: "https://pay.example.org/login/saml2/sso/pay"
            assertingparty:
              entity-id: "https://idp.example.org/issuer"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
              singlesignon:
                url: "https://idp.example.org/saml/sso"
                sign-request: false
```

**Giải thích bảo mật:**

- `registration.pay` tạo khóa định danh nội bộ `pay`.
- `entity-id` là **SP entityID**. IdP phải phát `AudienceRestriction/Audience` tương ứng giá trị này.
- `assertion-consumer-service-location` là **địa chỉ ACS HTTPS**. IdP phải gửi `SAMLResponse` tới đây và đặt `SubjectConfirmationData Recipient`/`Response Destination` phù hợp.
- `assertingparty.entity-id` là **IdP entityID**; đừng đưa nó vào `Audience` của assertion dành cho SP.
- `verification.credentials.certificate-location` cung cấp **public certificate của IdP** để xác minh chữ ký SAML; file phải là chứng thư thật được kiểm chứng từ IdP, không phải certificate tự tạo bằng cách copy từ assertion do user gửi.
- `singlesignon.url` là endpoint của IdP **nhận AuthnRequest**, không phải ACS của SP.
- `sign-request: false` chỉ minh họa tình huống IdP test cho phép unsigned AuthnRequest. Khi đối tác yêu cầu ký, dùng SP signing credentials và cấu hình ký đúng; không giảm chính sách ký để né lỗi audience/recipient.

**Các domain `example.org` là địa chỉ minh họa**; để chạy thật phải thay bằng IdP test, SP FQDN, certificate và ACS đã được đăng ký. Chạy cùng một cấu hình này trên `localhost` mà không có DNS/TLS tương ứng sẽ không thành công; đó là vấn đề môi trường/registration, không phải lý do tắt audience validation.

### 7.3. Bật đúng filter chain

File `src/main/java/com/example/saml/SamlSecurityConfig.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/login", "/error",
                    "/saml2/authenticate/**",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/login/saml2/sso",
                    "/login/saml2/sso/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **một class của dự án Spring Boot có các dependency liên quan**, không phải chương trình Java độc lập chạy bằng `javac` khi không có Maven/Gradle và application context. `saml2Login` đảm bảo ACS đi qua bộ lọc SAML, còn `saml2Metadata` công bố metadata SP theo cấu hình.

`permitAll` cho POST ACS chỉ cho phép browser **chưa có phiên** gửi response đến bộ lọc; nó **không bỏ qua** kiểm tra chữ ký, AudienceRestriction hoặc Recipient. Không dùng `web.ignoring("/login/saml2/sso/**")` hoặc tự viết controller giải Base64 `SAMLResponse` để tạo session. Nếu ứng dụng có nhiều `SecurityFilterChain`, phải bảo đảm ACS thực sự được chain SAML xử lý.

Thư viện tích hợp thường cấu hình **CSRF exception hẹp cho SAML ACS**; không tắt CSRF của toàn bộ ứng dụng web để chữa lỗi 403. Với web app dùng cookie session, những POST nghiệp vụ vẫn phải được bảo vệ CSRF.

### 7.4. Lấy chính SP metadata làm nguồn đối chiếu

Khi bật `saml2Metadata`, kiểm tra metadata SP được xuất ở endpoint tương ứng, ví dụ:

```text
https://pay.example.org/saml2/metadata/pay
```

Trong XML SP metadata, xem `EntityDescriptor/@entityID` và `SPSSODescriptor/AssertionConsumerService/@Location`. Sau đó đối chiếu chính xác với **Entity ID/Audience URI** và **ACS URL/Reply URL** mà IdP đã đăng ký.

`entityID` dùng cho Audience, còn `AssertionConsumerService Location` dùng cho Recipient/Destination. Đừng chỉ nhìn giao diện IdP ghi “URL” rồi chọn nhầm: mỗi giao diện nhà cung cấp có tên trường khác nhau. Cần ghi hai giá trị vào tài liệu tích hợp và kiểm tra lại sau mỗi thay đổi URL, proxy hoặc tenant.

## 8. Vì sao reverse proxy và đa môi trường dễ tạo lỗi?

### 8.1. Sai `{baseUrl}` khi TLS kết thúc ở gateway

Ví dụ trình duyệt dùng:

```text
https://pay.example.org/login/saml2/sso/pay
```

Nhưng Spring Boot chạy phía sau ingress với địa chỉ nội bộ:

```text
http://pay-service:8080/login/saml2/sso/pay
```

Nếu metadata/ACS do Spring phát dựa trên sai scheme/host/port, có thể xuất `Recipient`/`Destination` không trùng URL public. Khắc phục **ở cấu hình canonical URL và reverse proxy**, không sửa signature XML hoặc tắt kiểm tra Recipient.

Hướng kiểm soát:

1. Công bố một SP entityID ổn định và ACS URL HTTPS đúng FQDN.
2. Cấu hình ingress/proxy chuyển thông tin host/proto đúng, xóa các forwarded headers do client tự đưa vào và chỉ cho backend tin proxy được phê duyệt. Khi dùng Spring Boot, kiểm tra cách cấu hình `server.forward-headers-strategy` phù hợp topology.
3. Có thể đặt `entity-id` và `assertion-consumer-service-location` tường minh như ví dụ, để không bị lệch do request origin; nhưng vẫn cần bảo đảm routing thực tế đưa POST tới đúng ACS/filter.
4. Kiểm tra metadata **sau triển khai**, không chỉ file YAML trên máy local.
5. Không dùng so sánh thô với `request.getRequestURL()` nếu request ở backend đã bị rewrite hoặc chứa Host giả. Bộ kiểm chứng phải dùng cấu hình RP/ACS đã phê duyệt và request context đáng tin cậy.
6. Nếu IdP phát response tới URL HTTP nội bộ thay vì HTTPS public, sửa cấu hình IdP/ACS. **Không** thêm HTTP URL vào tập allowed recipients chỉ để “cho chạy được”.

### 8.2. Sai do dấu slash, port hoặc path

Các chuỗi sau có thể trông giống nhau nhưng **không tương đương** cho giao thức/registration:

```text
https://pay.example.org/login/saml2/sso/pay
https://pay.example.org/login/saml2/sso/pay/
https://pay.example.org:8443/login/saml2/sso/pay
https://pay.example.org/saml2/sso/pay
http://pay.example.org/login/saml2/sso/pay
```

Không tự `trim`, lowercase toàn URL (kể cả path), bỏ slash, bỏ port hoặc chuyển scheme khi kiểm chứng SAML. Chuỗi URL phải phù hợp với metadata, thông điệp và cách matching của bộ validator theo profile và policy. Trong trường hợp có reverse proxy, sửa từ **nguồn cấu hình chính xác** để tất cả bên nhất quán.

### 8.3. Đa tenant / nhiều registration

Nếu ứng dụng host nhiều tenant và mỗi tenant có RP entityID riêng:

- `registrationId` của từng tenant phải resolve về đúng `RelyingPartyRegistration`.
- SP entityID và ACS của tenant A không được tự động dùng làm danh sách audience/recipient hợp lệ cho tenant B.
- Không quyết định trust của token chỉ theo một query parameter, raw `Host` hoặc `Issuer` từ SAML chưa xác minh.
- Trước khi xác thực, SP phải xác định registration đúng theo cơ chế an toàn của framework, rồi **gắn các kiểm tra audience, recipient, IdP issuer và certificate vào registration đó**.
- Nếu tenant dùng chung ACS path, cần cơ chế resolve tenant/registration tin cậy và giới hạn audience/correlation tương ứng; không chấp nhận một SAMLResponse từ tenant khác chỉ vì hostname ACS trùng.
- IdP có thể cấp assertion dành cho nhiều `Audience`, nhưng bên nhận không được tự cho rằng điều này cấp quyền cross-tenant. Tenant boundaries và authorizations vẫn phải được kiểm tra riêng.

**Tình huống cảnh báo:** Người dùng từ SP A gửi `SAMLResponse` sang SP B, cả hai cùng tin certificate của IdP. Nếu SP B chỉ làm `verifySignature` rồi cấp session theo `NameID`, đó là lỗi nghiêm trọng. `AudienceRestriction` và `Recipient` là hai lớp bắt buộc giúp tránh việc chấp nhận sai đối tượng.

## 9. Thời gian, InResponseTo và replay: không tách rời khỏi Recipient

### 9.1. Hai cửa sổ hiệu lực độc lập

`Conditions/@NotBefore` và `Conditions/@NotOnOrAfter` giới hạn hiệu lực **của assertion**. Trong khi đó, `SubjectConfirmationData/@NotOnOrAfter` giới hạn thời điểm **bearer subject có thể được xác nhận**. Một assertion chưa hết hạn theo `Conditions` vẫn có thể không chấp nhận được nếu SubjectConfirmationData đã hết hạn.

Ví dụ:

```text
Conditions:
  NotBefore       = 10:00:00 UTC
  NotOnOrAfter    = 10:10:00 UTC

SubjectConfirmationData:
  Recipient       = https://pay.example.org/login/saml2/sso/pay
  NotOnOrAfter    = 10:03:00 UTC

SP nhận tại      = 10:04:00 UTC
=> Conditions vẫn còn hạn, NHƯNG bearer confirmation đã hết hạn
=> Không được dùng xác nhận chủ thể này
```

Sai đồng hồ giữa IdP/SP có thể làm request vừa phát đã “expired” hoặc “not yet valid”. Nên đồng bộ NTP trên IdP, SP và reverse proxy. Clock-skew allowance phải nhỏ, có chính sách, không phải cách thay thế sửa đồng hồ hoặc bỏ kiểm tra `NotOnOrAfter`.

### 9.2. `InResponseTo` và giới hạn IdP-initiated SSO

Với SP-initiated SSO, IdP trả response cho AuthnRequest đã khởi tạo. `InResponseTo` ở response và bearer confirmation (khi áp dụng) phải gắn với ID request còn hợp lệ và đã được SP lưu. Nếu ID không khớp hoặc request đã được sử dụng, từ chối; **Recipient đúng không bù được InResponseTo sai**.

Với IdP-initiated (unsolicited) SSO, profile không có AuthnRequest để ghép; chính sách xử lý sẽ khác và bảo vệ login CSRF/replay khó hơn. Chỉ bật nếu có nhu cầu và được đánh giá rủi ro, không tắt kiểm tra `InResponseTo` trên mọi luồng để chữa lỗi SSO do session. Nếu một response khai báo unsolicited nhưng kèm InResponseTo trái quy tắc profile, phải xử lý theo profile chứ không tùy tiện bỏ qua.

### 9.3. Replay cache

Assertion bearer trong thời hạn ngắn vẫn có thể bị gửi lại bởi kẻ lấy được SAMLResponse (nếu có thể vượt qua các biện pháp khác). SP cần kiểm soát Message ID/Assertion ID, trạng thái request và chống replay tương ứng profile/implementation. Không lưu raw assertion trong log, không mở ACS qua HTTP; dùng HTTPS, bảo vệ session cookie và bảo đảm lưu trạng thái dùng một lần nhất quán giữa các node của cluster.

**Một ID Token/OAuth Access Token không thể thay thế việc đối chiếu assertion SAML:** mục tiêu và mô hình bảo vệ khác nhau. Resource Server OAuth2 kiểm tra issuer/audience của access token cho API; SP SAML2 kiểm tra issuer, AudienceRestriction, Recipient, Destination, subject confirmation và correlation theo SAML.

## 10. Ví dụ Java 17 độc lập để hiểu quy tắc so sánh

Ví dụ sau **chỉ minh họa logic điều kiện sau khi giả định thông tin đã được một bộ SAML validator đáng tin cậy phân tích, xác minh chữ ký và xác định đúng message**. Nó **không parse XML, không kiểm tra chữ ký, không validate SAML thực tế** và tuyệt đối **không được dùng thay Spring Security/OpenSAML trong production**.

File `SamlBoundaryDemo.java`, chạy trên JDK 17+ không cần thư viện ngoài:

```java
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class SamlBoundaryDemo {

    record BearerConfirmation(
            String recipient,
            Instant notOnOrAfter,
            String inResponseTo) { }

    // Giả sử mỗi Set đại diện một AudienceRestriction;
    // các Set trong List là nhiều restriction độc lập.
    static boolean matchesForLearning(
            List<Set<String>> audienceRestrictions,
            List<BearerConfirmation> bearerConfirmations,
            String expectedEntityId,
            String expectedAcs,
            String expectedRequestId,
            Instant receivedAt) {

        // Browser SSO: phải có audience restriction.
        boolean audienceValid = !audienceRestrictions.isEmpty()
            && audienceRestrictions.stream()
                .allMatch(group -> group.contains(expectedEntityId));

        // Từng bearer confirmation phải thỏa TẤT CẢ ràng buộc.
        boolean subjectValid = bearerConfirmations.stream()
            .anyMatch(confirmation ->
                expectedAcs.equals(confirmation.recipient())
                && receivedAt.isBefore(confirmation.notOnOrAfter())
                && expectedRequestId.equals(confirmation.inResponseTo()));

        return audienceValid && subjectValid;
    }

    public static void main(String[] args) {
        String entityId = "urn:example:sp:pay";
        String acs = "https://pay.example.org/login/saml2/sso/pay";
        String requestId = "_request-123";
        Instant now = Instant.parse("2030-03-10T10:01:00Z");

        List<Set<String>> validAudience =
            List.of(Set.of(entityId, "urn:example:sp:billing"),
                    Set.of(entityId));

        List<BearerConfirmation> validBearer =
            List.of(new BearerConfirmation(
                acs, now.plusSeconds(60), requestId));

        System.out.println("valid=" + matchesForLearning(
            validAudience, validBearer,
            entityId, acs, requestId, now));

        System.out.println("wrongSecondAudience=" + matchesForLearning(
            List.of(Set.of(entityId),
                    Set.of("urn:example:sp:hr")),
            validBearer, entityId, acs, requestId, now));

        System.out.println("wrongRecipient=" + matchesForLearning(
            validAudience,
            List.of(new BearerConfirmation(
                "https://hr.example.org/login/saml2/sso/hr",
                now.plusSeconds(60), requestId)),
            entityId, acs, requestId, now));

        System.out.println("expiredBearer=" + matchesForLearning(
            validAudience,
            List.of(new BearerConfirmation(
                acs, now.minusSeconds(1), requestId)),
            entityId, acs, requestId, now));

        System.out.println("wrongRequestId=" + matchesForLearning(
            validAudience,
            List.of(new BearerConfirmation(
                acs, now.plusSeconds(60), "_other-request")),
            entityId, acs, requestId, now));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SamlBoundaryDemo.java
java SamlBoundaryDemo
```

Stdout xác định (không phụ thuộc đồng hồ máy vì `now` được cố định):

```text
valid=true
wrongSecondAudience=false
wrongRecipient=false
expiredBearer=false
wrongRequestId=false
```

**Điều mô phỏng đúng:** Các `Audience` trong một `AudienceRestriction` dùng OR, các restrictions dùng AND; các thuộc tính của một bearer confirmation phải cùng thỏa; nhiều confirmations (đã lọc theo Method hợp lệ) có thể dùng quy tắc chọn một confirmation đạt đủ điều kiện. **Điều ví dụ cố tình bỏ qua:** XML Signature, canonicalization, `Issuer`, `Response Destination`, `Conditions NotBefore/NotOnOrAfter`, replay, trust keys, SAML processing profiles, metadata refresh và các extension. Vì vậy kết quả `true` chỉ có nghĩa **bài toán logic nhỏ này đúng**, không có nghĩa SAMLResponse đã được xác thực.

## 11. Tạo test tích hợp có giá trị chẩn đoán

Để kiểm thử Audience/Recipient thực sự, tạo **IdP test có chứng thư ký đã đăng ký** và cấu hình một SP test HTTPS có entityID/ACS cố định. Thay đổi **cấu hình phát assertion phía IdP test** để tạo case âm, hoặc dùng fixture SAML được ký lại bằng **khóa kiểm thử mà SP tin trong test**. Không lấy một SAMLResponse ký hợp lệ rồi sửa chuỗi XML thô: chữ ký sẽ hỏng trước, khiến test chỉ chứng minh “signature invalid”, không chứng minh Audience/Recipient validator đang hoạt động.

### 11.1. Ma trận test bắt buộc

| Ca kiểm thử | SAML input đã ký hợp lệ từ IdP test | Kết quả SP phải làm |
| --- | --- | --- |
| **Happy path** | Audience = SP entityID, Recipient = ACS, Destination = ACS, request ID đúng, thời gian hợp lệ | Đăng nhập, tạo Authentication/session đúng SP |
| **Audience sai SP** | Audience = `urn:example:sp:hr` trong khi SP entityID = `urn:example:sp:pay` | **Từ chối**, không tạo session |
| **Audience nhầm ACS URL** | Audience = `https://pay.example.org/login/saml2/sso/pay` nhưng SP entityID khác | Từ chối, sửa claim ở IdP thay vì sửa validator |
| **Audience chứa hai lựa chọn trong một condition** | Một `AudienceRestriction` chứa entityID SP và một entityID khác | Condition có thể hợp lệ với SP nếu các điều kiện khác đều đạt |
| **Hai AudienceRestriction độc lập, chỉ một cái khớp** | Restriction A chứa SP entityID, restriction B không chứa | Từ chối do AND giữa restrictions |
| **Thiếu AudienceRestriction** | Bearer assertion trong Web Browser SSO không có audience condition | Từ chối |
| **Recipient gửi SP B** | Recipient = ACS của SP B, các trường khác vẫn dành SP A | Từ chối |
| **Recipient chỉ khác slash/port/scheme** | Recipient lệch URL ACS đang dùng | Từ chối; không bỏ qua URL mismatch |
| **Destination sai nhưng Recipient đúng** | Response Destination không đúng URL ACS | Từ chối theo kiểm chứng message destination |
| **Recipient đúng nhưng Audience sai** | Một ràng buộc đạt, một ràng buộc không đạt | Từ chối: hai lớp là AND |
| **Audience đúng nhưng Recipient sai** | Ngược ca trên | Từ chối |
| **Bearer hết hạn** | SubjectConfirmationData NotOnOrAfter đã qua, Conditions còn hạn | Từ chối nếu không có confirmation khác hợp lệ |
| **Conditions hết hạn** | Conditions NotOnOrAfter đã qua, bearer còn hạn | Từ chối |
| **Sai InResponseTo** | Đã ký lại; ID không trùng AuthnRequest đang chờ | Từ chối |
| **Replay cùng Assertion ID/Response** | Gửi lại response đã tiêu thụ trong điều kiện phải chống replay | Từ chối theo policy, không tạo phiên mới |
| **Sai IdP signing key** | Assertion do nguồn khác ký, dù Audience/Recipient khớp | Từ chối trước khi tin claims |
| **Nhiều confirmations** | Một confirmation sai, một bearer confirmation đủ mọi điều kiện | Xử lý theo quy tắc profile/validator: chỉ được xác nhận nếu có confirmation **độc lập** hoàn toàn hợp lệ |
| **Tenant A vs tenant B** | SP A entityID, ACS của tenant B hoặc ngược lại | Từ chối, không cross-tenant session |
| **Proxy xuất metadata sai host** | IdP phát theo ACS HTTP/internal khác HTTPS public | Từ chối; sửa SP metadata/IdP config/trusted proxy |

**Trình tự test:** Mỗi lần chỉ thay **một** biến trên test IdP; giữ issuer, ký số, time window, request correlation và route còn lại hợp lệ để xác định nguyên nhân. Nếu sửa nhiều biến một lúc, kết quả fail không chứng minh validator nào đã từ chối.

### 11.2. Kiểm tra response qua mạng nhưng tránh lộ dữ liệu

Dùng browser DevTools Network trong môi trường test:

1. Truy cập một URL được bảo vệ của SP rồi để Spring tạo `AuthnRequest`.
2. Xác nhận browser tới IdP đúng registration; sau login POST `SAMLResponse` về đúng ACS HTTPS.
3. Xác định **endpoint path, HTTP method, status/redirect và cookie behavior**; không copy raw `SAMLResponse`, `RelayState`, cookie hoặc private key vào issue tracker.
4. Nếu login thành công, xác nhận `SecurityContext` có `Saml2Authentication` phù hợp SP và endpoint nghiệp vụ vẫn được phân quyền.
5. Với ca âm, xác nhận **không tạo phiên xác thực** (kể cả HTTP 302 về trang login); không chỉ nhìn HTTP status.
6. Bật log debug có kiểm soát trong test và che dữ liệu nhạy cảm; đối chiếu lỗi audience, subject confirmation, recipient, issuer, destination hoặc request correlation.
7. Kiểm tra behavior khi hai tab/browser session, session cluster và IdP-initiated flow (nếu hỗ trợ). Điều này phát hiện tình huống `InResponseTo` gắn sai trạng thái.

**Đừng log nguyên `SAMLResponse` hoặc XML Assertion trong production:** XML có thể chứa NameID, email, thuộc tính nhân sự, thông tin phiên và các dữ liệu cá nhân khác. Log nên giữ issuer/registrationId, mã tương quan, loại lỗi, thời gian và kết quả, không giữ bí mật.

## 12. Tìm lỗi trong thực tế

| Dấu hiệu | Khả năng nguyên nhân | Cách xác minh/sửa |
| --- | --- | --- |
| `AudienceRestriction` không khớp | IdP đặt SP identifier sai, dùng ACS làm audience, môi trường staging/prod trộn entityID | Đối chiếu SP metadata `EntityDescriptor/@entityID` với Audience URI/Relying Party Identifier bên IdP |
| `Recipient` không khớp | IdP đăng ký ACS sai scheme/host/path/port, reverse proxy rewrite, nhiều tenant | Đối chiếu SP metadata ACS, URL POST browser thực tế và `SubjectConfirmationData/@Recipient` trong fixture test hợp lệ |
| Audience trùng nhưng Recipient sai | Assertion có audience đúng SP nhưng chuyển đến ACS khác | Không bỏ Recipient validator; sửa ACS/binding/IdP |
| Recipient trùng nhưng Audience sai | IdP phát claim cho SP/entityID khác | Không bỏ AudienceRestriction validator; sửa issuer registration |
| `Destination` mismatch | Response/@Destination trỏ endpoint khác hoặc SP nhận qua alias | Sửa canonical ACS và configuration ở hai bên; không sửa XML đã ký |
| “Assertion has expired” khi mới đăng nhập | Đồng hồ IdP/SP sai, `Conditions` hoặc `SubjectConfirmationData` hết hạn | Đồng bộ NTP/UTC, so sánh từng time window, kiểm tra lệch đồng hồ hợp lý |
| `InResponseTo` mismatch | Mất HttpSession, SP chưa lưu request, session affinity/SameSite, sai tab/tenant | Kiểm tra request repository, cookie HTTPS/SameSite, cluster session và binding |
| Signature valid nhưng SP vẫn lỗi | Audience, Recipient, Destination, Issuer, time, replay hoặc policy khác không đạt | Xem loại lỗi validator thay vì tắt các kiểm tra khác |
| Kiểm tra “chỉ hostname” vẫn qua | Validator tự viết so sánh prefix/host thay vì exact ID/ACS | Gỡ custom acceptance logic, dùng thư viện SAML và regression test |
| SSO trên localhost được nhưng production lỗi | `{baseUrl}`/proxy headers, entityID hoặc ACS public khác | Fix canonical URLs, cấu hình forwarded headers chỉ từ trusted proxy và xuất SP metadata thực |
| Nhận response của tenant khác | Repository resolve registration sai, nhiều SP cùng certificate/ACS | Gắn registration với issuer + audience + recipient + request correlation đúng tenant |
| Sau đổi certificate/metadata login lỗi | IdP/SP trust keys cũ, issuer/entityID/ACS thay đổi không đồng bộ | Thực hiện rollover theo kế hoạch, review diff metadata, đừng bỏ signature validation |
| POST ACS bị chặn 403 CSRF | Filter chain/URL ACS bị thay, exception CSRF không khớp | Kiểm tra chain SAML và matcher ACS, không tắt CSRF toàn bộ web |

**Quy trình chẩn đoán ưu tiên:**

```text
1. SAMLResponse tới đúng HTTPS ACS và đúng SecurityFilterChain?
2. IdP đã được cấu hình với entityID/signing certificate đáng tin?
3. Chữ ký bảo vệ đúng message/assertion được xử lý?
4. Assertion/Conditions/AudienceRestriction có chứa SP entityID?
5. Bearer SubjectConfirmationData/Recipient có đúng ACS đã nhận?
6. Response/Destination có trùng ACS? InResponseTo có đúng request?
7. Conditions và bearer expiration còn hạn? ID có bị replay?
8. Sau xác thực, session và phân quyền nghiệp vụ có đúng?
```

## 13. Những giả định không được đưa vào production

**Không nên viết logic kiểu này:**

```java
// Anti-pattern minh họa; tuyệt đối không dùng làm validator SAML.
if (xml.contains("pay.example.org")) {
    loginUser();
}
```

Nó vừa bỏ qua signature/issuer, vừa không phân biệt Audience/Recipient/Destination, lại dễ bị XML signature wrapping và chuỗi xuất hiện ở một phần tử không có thẩm quyền. Cũng không chấp nhận yêu cầu như “tắt AudienceRestriction validator để SSO hoạt động”, “bỏ Recipient vì IdP không gửi”, hoặc “thêm mọi URL thuộc cùng domain vào accepted recipients”.

Những thay đổi validator phải thực hiện **chỉ khi có yêu cầu profile đặc biệt đã được đánh giá**, vẫn bảo vệ các ràng buộc SAML bắt buộc và có bộ test âm/dương đầy đủ. Khi tích hợp IdP lỗi cấu hình, ưu tiên sửa chính xác tại IdP/registration/metadata; không giảm bảo mật SP.

## 14. Câu hỏi luyện tập và đáp án

**Câu 1.** Một assertion do IdP tin cậy ký, `AudienceRestriction` chứa entityID SP A nhưng browser POST vào ACS SP B. SP B có nên chấp nhận vì chữ ký hợp lệ?

**Đáp án:** **Không**. Signature chỉ xác minh nguồn/tính toàn vẹn; assertion không dành cho SP B. Audience và Recipient/Destination phải khớp với SP B/ACS của SP B cùng các kiểm tra khác.

**Câu 2.** IdP gửi `Audience` là `https://pay.example.org/login/saml2/sso/pay` trong khi SP `entityID` là `https://pay.example.org/saml2/service-provider-metadata/pay`. Cả hai URL cùng host; hợp lệ không?

**Đáp án:** **Không** với cấu hình này. Audience phải so với **SP entityID**, không phải ACS URL. Cần sửa Audience/Entity ID mà IdP đăng ký.

**Câu 3.** Có hai `AudienceRestriction`: đầu tiên chứa `urn:sp:pay`, thứ hai chỉ chứa `urn:sp:hr`. SP entityID là `urn:sp:pay`. Có đạt không?

**Đáp án:** Không. Các phần tử Audience trong một restriction là OR, nhưng các restriction là AND. Restriction thứ hai không khớp nên thất bại.

**Câu 4.** `Conditions/NotOnOrAfter` còn 5 phút nhưng `SubjectConfirmationData/NotOnOrAfter` đã qua 1 phút. Recipient đúng, có cho login?

**Đáp án:** Không thể dùng subject confirmation đã hết hạn; nếu không có confirmation hợp lệ khác theo profile, phải từ chối. Cần kiểm tra hai mốc độc lập và đồng bộ thời gian.

**Câu 5.** SP phía sau proxy thấy URL HTTP nội bộ, IdP phát Recipient HTTPS public. Nên bỏ Recipient check hay sửa proxy/cấu hình?

**Đáp án:** Sửa canonical HTTPS ACS, metadata, host/proto forwarding từ proxy được tin và đăng ký IdP. Không bỏ Recipient/Destination validation.

**Câu 6.** Ta sửa một ký tự trong `Audience` của SAMLResponse đã ký rồi POST lại, Spring báo “invalid signature”. Điều này có chứng minh audience validator từ chối không?

**Đáp án:** Không. Khi chữ ký đã sai, không cô lập được validation của audience. Dùng IdP test phát/đăng ký audience sai rồi **ký lại hợp lệ** bằng khóa test được SP tin, hoặc fixture integration do hệ kiểm thử SAML tạo chuẩn.

## 15. Checklist nghiệm thu

- [ ] SP entityID và ACS HTTPS được khai báo rõ, xuất hiện chính xác trong metadata SP và đăng ký IdP.
- [ ] IdP `entityID` và public signing certificate được kiểm chứng từ nguồn tin cậy.
- [ ] `AudienceRestriction` chứa SP entityID theo đúng semantics OR trong một restriction / AND giữa nhiều restrictions.
- [ ] Bearer `SubjectConfirmationData Recipient` trùng ACS của registration và thông điệp đang nhận; không so sánh chỉ host/path prefix.
- [ ] `Response Destination`, `InResponseTo` (khi áp dụng), `Conditions`, bearer expiry, chữ ký và replay được xác minh độc lập.
- [ ] Không nhận assertion từ SP/tenant khác chỉ vì IdP được dùng chung.
- [ ] Không tự viết bộ XML validator hoặc bỏ kiểm tra audience/recipient trong Spring Security.
- [ ] Reverse proxy/forwarded headers/HTTPS host được tin cậy và cấu hình nhất quán; metadata thực tế đã được kiểm tra.
- [ ] Test âm được phát hành/ký **hợp lệ** để cô lập audience/recipient, không chỉ làm hỏng chữ ký bằng cách sửa XML raw.
- [ ] Đã kiểm thử clock skew, session correlation, nhiều bearer confirmations, multiple restrictions và SAMLResponse replay.
- [ ] Log không lưu raw assertions, NameID nhạy cảm, session cookie hay private key.

**Kết luận:** `AudienceRestriction` trả lời **“Assertion dành cho SP entityID nào?”**; `SubjectConfirmationData Recipient` trả lời **“Bearer assertion này có thể được xác nhận tại ACS URL nào?”**. Trong browser SSO, cả hai phải đúng, đồng thời chữ ký/issuer, `Response Destination`, thời gian, `InResponseTo` và chống replay cũng phải đạt. Với Spring Security, giải pháp đúng là cấu hình RP `entityId`/`assertionConsumerServiceLocation` nhất quán với IdP và để OpenSAML kiểm tra đầy đủ, **không hạ kiểm chứng để che lỗi cấu hình**.

## 16. Tài liệu tham khảo chính thức

- [OASIS SAML 2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Conditions`, `AudienceRestriction`, `SubjectConfirmation`, `SubjectConfirmationData`.
- [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO bearer confirmation, `Recipient`, `NotOnOrAfter`, `InResponseTo`.
- [OASIS SAML Errata 05](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html): làm rõ quan hệ OR/AND của `AudienceRestriction` và các yêu cầu bearer profile.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, ACS và quy trình OpenSAML xác minh assertion conditions.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): công bố SP metadata để đối chiếu `entityID`/ACS.
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): bảo vệ đường dẫn nghiệp vụ sau khi xác thực.
