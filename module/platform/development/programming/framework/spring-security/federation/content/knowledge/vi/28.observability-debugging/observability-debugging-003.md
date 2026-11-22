# Đọc SAMLRequest, SAMLResponse và metadata trong môi trường thử nghiệm

> **Module:** Spring Security – federation. **Chủ đề cha:** Quan sát và gỡ lỗi. Bài Knowledge hướng dẫn kiểm tra một luồng **SAML 2.0 Web Browser SSO** ở môi trường thử nghiệm bằng cách thu thập đúng HTTP binding, giải mã `SAMLRequest` / `SAMLResponse`, đọc XML/metadata, so sánh các định danh và điều kiện bảo mật, rồi đối chiếu với cấu hình Spring Security Service Provider (SP) và Identity Provider (IdP). **Giải mã được XML không có nghĩa chữ ký đã hợp lệ, chứng thư đã được tin cậy, Assertion còn hiệu lực hoặc người dùng được phép đăng nhập.** Mọi thao tác phải dùng dữ liệu tổng hợp hoặc tài khoản thử nghiệm, tránh công cụ giải mã trực tuyến không được tổ chức phê duyệt.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **SP/Relying Party** với **IdP/Asserting Party**, `AuthnRequest`, `Response`, `Assertion`, `Issuer`, `NameID`, `RelayState`, metadata và ACS.
2. Dùng Developer Tools hoặc HTTP trace trong lab để tìm đúng `SAMLRequest`, `SAMLResponse`, `RelayState`, `SigAlg`, `Signature`, `SAMLart`, URL, method và content type.
3. Giải mã **HTTP-Redirect binding** theo đúng thứ tự: lấy tham số raw query → URL-decode một lần → Base64-decode → giải nén **raw DEFLATE** (RFC 1951, không phải gzip/zlib wrapper).
4. Giải mã **HTTP-POST binding**: browser gửi form `application/x-www-form-urlencoded`, giá trị tham số được form-decode → Base64-decode thành XML; **không tự DEFLATE** như Redirect.
5. Hiểu **HTTP-Artifact binding** chứa tham chiếu `SAMLart` chứ không có toàn bộ XML trên front channel; phải điều tra SOAP ArtifactResolve/ArtifactResponse trên back channel tin cậy.
6. Đọc `AuthnRequest`: `ID`, `IssueInstant`, `Destination`, `Issuer`, `AssertionConsumerServiceURL`/Index, `ProtocolBinding`, `NameIDPolicy`, `RequestedAuthnContext`, `ForceAuthn`/`IsPassive`.
7. Đọc `Response`/`Assertion`: `InResponseTo`, `Destination`, `StatusCode`, `Issuer`, `AudienceRestriction`, `SubjectConfirmationData Recipient/InResponseTo/NotOnOrAfter`, `Conditions NotBefore/NotOnOrAfter`, `AuthnStatement`, `AuthnContextClassRef`, attributes và `NameID`.
8. Đọc **IdP/SP metadata**: `entityID`, `IDPSSODescriptor`/`SPSSODescriptor`, `KeyDescriptor`, `SingleSignOnService`, `AssertionConsumerService`, `SingleLogoutService`, `validUntil`/`cacheDuration` và binding URLs.
9. Phân biệt **chữ ký XML** (`ds:Signature`, canonicalization/reference/digest/signature) với **chữ ký HTTP-Redirect query** (`SigAlg`/`Signature` trên tham số đã URL-encode, đúng thứ tự).
10. Không nhầm **chữ ký tồn tại** với **chữ ký hợp lệ và signer được trust**; biết khi nào không thể đọc `EncryptedAssertion` vì cần private key SP.
11. Dùng chương trình **Java 17 độc lập**, chỉ nhận file local, giới hạn kích thước, chặn DOCTYPE/external entities, đọc một số trường chẩn đoán và in stdout xác định.
12. Xem cách bật `saml2Login`, `saml2Metadata`, xác định endpoint Spring Security, cấp test IdP certificate và đối chiếu `RelyingPartyRegistration`.
13. Tạo ma trận so khớp **Request ↔ Response ↔ IdP metadata ↔ SP metadata ↔ Spring configuration** và truy nguyên các lỗi signature, issuer, audience, destination, recipient, session correlation, time skew, NameID và metadata rollover.
14. Tổ chức công cụ/trace an toàn: không ghi raw SAML XML chứa PII, không gửi HAR/token lên website lạ, không tắt signature validation để “debug”.
15. Thiết lập test âm tính, checklist QA và runbook phát hiện sai cấu hình trước khi triển khai production.

**Phạm vi:** SAML 2.0 HTTP-Redirect/POST/Artifact bindings, Spring Security Service Provider Servlet stack, Java 17+, XML/X.509 trust. Tên miền `.example.test`, đối tượng XML và chứng thư trong bài là dữ liệu tổng hợp minh họa. Chỉ bài `SamlLabInspector.java` là chương trình Java thuần chạy độc lập; các snippet Spring cần dự án Spring Boot/Security và IdP test. Mọi dữ liệu thu từ một tổ chức thực phải tuân chính sách bảo mật/retention.

## 2. Bức tranh một luồng SAML2 SP-initiated login

~~~text
Browser                  SP Spring Security                IdP
   |                            |                            |
   | GET /private               |                            |
   |--------------------------->|                            |
   | 302 /saml2/authenticate/lab|                            |
   |<---------------------------|                            |
   | GET /saml2/authenticate/lab|                            |
   |--------------------------->|                            |
   |   SAML AuthnRequest created + request state             |
   |<---- 302 IdP SSO endpoint, SAMLRequest, RelayState ----|
   |                            |                            |
   | GET IdP /sso?SAMLRequest=...&RelayState=...             |
   |-------------------------------------------------------->|
   |                            |  IdP validates AuthnRequest|
   |                            |  IdP authenticates user    |
   |<----------- HTML form (SAMLResponse, RelayState) -------|
   |                            |                            |
   | POST /login/saml2/sso/lab  |                            |
   |--------------------------->|                            |
   |                            | decode + verify signature  |
   |                            | issuer, audience, recipient|
   |                            | response/request correlation|
   |                            | Conditions, Subject, status|
   |                            | map local identity/roles   |
   |<------------ local SP session / redirected success ------|
~~~

**Những dấu vết cần thu:**
- Request SP → IdP thường là **HTTP-Redirect `SAMLRequest`**; cũng có thể **HTTP-POST `SAMLRequest`**, tùy cấu hình binding.
- Response IdP → SP ACS thường là **HTTP-POST `SAMLResponse`** đã Base64-encode trong form.
- Một số profile dùng **HTTP-Artifact**: front channel chỉ có `SAMLart`, response/assertion được resolve bằng back-channel SOAP.
- `RelayState` giúp liên hệ request/response/saved state trong một số triển khai; không phải bằng chứng user identity hay chữ ký tự thân.
- **Chỉ sau validation thực sự** Spring Security mới cấp `Saml2Authentication` và lưu `SecurityContext`/local session.

### 2.1. URL mặc định trong Spring Security

Ở cấu hình `saml2Login`/`saml2Metadata` thông dụng (đường dẫn có thể được tùy biến):

| Vai trò | Đường dẫn mẫu | Công dụng |
| --- | --- | --- |
| Bắt đầu login | `GET /saml2/authenticate/{registrationId}` | Tạo/gửi AuthnRequest tới IdP tương ứng. |
| Một dạng initiate khác | `GET /saml2/authenticate?registrationId=lab` | Định tuyến theo registration theo phiên bản/cấu hình hỗ trợ. |
| ACS nhận Response | `POST /login/saml2/sso/{registrationId}` | Nhận `SAMLResponse` rồi gọi Spring/OpenSAML validator. |
| ACS không có registrationId trong path | `POST /login/saml2/sso` | Có thể resolve RP từ stored authentication request/issuer theo cấu hình. |
| SP metadata | `GET /saml2/metadata` | Metadata cho RP registrations được công bố. |
| SP metadata cụ thể | `GET /saml2/metadata/{registrationId}` | Thông tin một RP. |
| Alias SP metadata | `GET /saml2/service-provider-metadata/{registrationId}` | Đường dẫn được Spring hỗ trợ. |

**Quan trọng:** `registrationId=lab` là **khóa cấu hình nội bộ**, không phải `entityID` của SP hoặc IdP, và không phải một IdP trust anchor có thể tự suy từ URL. Không giả định mọi Spring Security 6.x/7.x có cùng implementation class/provider (OpenSAML 4/5 khác theo version). Kiểm tra dependency versions thực tế của ứng dụng. Tài liệu Spring Security mô tả các endpoint và filter tương ứng.

## 3. Bắt gói trong browser DevTools mà không làm lộ dữ liệu

### 3.1. Chuẩn bị một phiên thử nghiệm cô lập

1. Dùng IdP **sandbox** và SP staging với tài khoản tổng hợp, không dùng production account.
2. Xóa phiên IdP/SP trong test browser profile hoặc dùng profile mới để bắt đầu từ trạng thái xác định.
3. Mở Developer Tools → **Network**, bật **Preserve log** để giữ các request khi browser redirect qua nhiều origin.
4. Chỉ chạy một flow `SP-initiated`; ghi thời gian, SP hostname, `registrationId`, user/test case ID.
5. Lọc request theo `saml2/authenticate`, IdP SSO URL và `login/saml2/sso`.
6. Xem **HTTP Method**, `Location`, query parameters, form data, response status và cookie scope; **không copy toàn bộ cookies/tokens**.
7. Nếu cần lưu một payload để lab decode, lưu ở file local có ACL giới hạn, dùng synthetic test user và xóa sau khi hoàn thành.
8. Khi gửi bug report, **redact `NameID`, email, attributes, XML signature values, RelayState, session cookies, SAMLResponse**; chỉ gửi các trường cần chẩn đoán hoặc secure attachment theo policy.

**Không paste HAR/SAMLResponse vào decoder website ngẫu nhiên.** Một signed SAML Assertion có thể chứa các định danh cá nhân, nhóm/quyền, session data và thuộc tính nhạy cảm. Một screenshot của Network panel cũng có thể lộ `Authorization`, cookies, `RelayState` và full URL.

### 3.2. Nhận biết request nào cần xem

| Dấu hiệu | Binding/ý nghĩa | Cách xử lý |
| --- | --- | --- |
| 302 Location tới IdP có `SAMLRequest=...` | HTTP-Redirect AuthnRequest. | URL-decode → Base64 → raw DEFLATE. |
| Form HTML gửi tới IdP có hidden `SAMLRequest` | HTTP-POST AuthnRequest. | Form-decode → Base64 → XML. |
| Form HTML gửi tới SP ACS có `SAMLResponse` | HTTP-POST Response. | Form-decode → Base64 → XML. |
| Location/form có `SAMLart` | Artifact binding. | Không thể lấy toàn Assertion chỉ từ artifact; cần ArtifactResolve/Response ở back channel. |
| `SigAlg` + `Signature` ở raw query | HTTP-Redirect query signature. | Kiểm chứng trên chuỗi URL-encoded đúng chuẩn; decode XML không đủ. |
| `ds:Signature` trong XML | XML Digital Signature. | Trust/crypto validation với SAML library, không chỉ nhìn thẻ. |
| `RelayState` | Application/request correlation. | Không tự dùng làm account ID hoặc URL redirect tùy ý. |

### 3.3. Có nên dùng HAR?

HAR rất hữu ích khi có redirect loop nhưng có thể chứa **cookies, query strings, authorization codes, POST bodies và dữ liệu cá nhân**. Chỉ export khi chính sách tổ chức cho phép và dùng phương tiện lưu trữ được kiểm soát. Cần redact dữ liệu trước khi chia sẻ, xóa bản tạm sau phân tích, đặt TTL và hạn chế truy cập. Đừng bật verbose logging của `SAMLResponse` trong production để đổi lấy một trace.

## 4. HTTP-Redirect: giải mã SAMLRequest chính xác

Một HTTP-Redirect binding có dạng:

~~~text
GET https://idp.example.test/sso?
  SAMLRequest=<url-encoded-base64-raw-deflate>
  &RelayState=<url-encoded-opaque-state>
  &SigAlg=<url-encoded-algorithm-uri>
  &Signature=<url-encoded-base64-signature>
~~~

Đây là sơ đồ; URL thực tế trên một dòng và có thể không mang mọi tham số.

### 4.1. Thứ tự giải mã bắt buộc

1. Lấy **giá trị `SAMLRequest` chưa bị biến đổi** trong raw query. Nếu cần xác minh query signature, giữ nguyên **các encoded substrings** ban đầu.
2. **URL-decode đúng một lần** giá trị tham số, gồm `%2B`/`%2F`/`%3D` và dấu `+` theo quy tắc encoding form/query thích hợp.
3. Dùng Base64 decoder để lấy dữ liệu nén.
4. **DEFLATE raw** bằng RFC 1951, tức Java `new Inflater(true)`; không dùng `GZIPInputStream`.
5. Parse XML an toàn với namespace-aware parser; giới hạn kích thước và vô hiệu hóa DTD/external entities.
6. Xem `AuthnRequest` root, `ID`, `IssueInstant`, `Destination`, `Issuer`, ACS URL và chính sách NameID/AuthnContext.
7. Ghi nhận thông tin cần chẩn đoán; không ghi raw XML/NameID vào công cụ logging bên ngoài.

~~~text
raw URL query
    |
    +--> preserve original URL-encoded SAMLRequest, RelayState, SigAlg
    |    for signature checking (if present)
    |
    +--> percent decode exactly once
    |
    +--> Base64 decode
    |
    +--> raw DEFLATE (nowrap=true)
    |
    +--> XML parser with external entities disabled
    |
    +--> diagnostic summary (NOT authentication verdict)
~~~

**Lỗi hay gặp:** dùng `Inflater(false)` mặc định có zlib wrapper khiến giải nén lỗi; hoặc copy một chuỗi từ DevTools đã URL-decode rồi decode thêm lần nữa. Nếu nhận `Illegal base64 character` hoặc `incorrect header check`, trước tiên kiểm tra binding và trạng thái encoding, không vội sửa IdP secret/certificate.

### 4.2. Chữ ký Redirect khác chữ ký XML

Với HTTP-Redirect binding, theo OASIS Bindings, chữ ký query (khi có) ký **chính xác** chuỗi có thứ tự:

~~~text
SAMLRequest=<original-url-encoded-value>&RelayState=<original-url-encoded-value>&SigAlg=<original-url-encoded-value>
~~~

Nếu không có `RelayState` thì bỏ **toàn bộ** `RelayState=...&`. Với một Redirect `SAMLResponse` thì thay khóa đầu tiên bằng `SAMLResponse`. Tham số `Signature` chứa chữ ký Base64 đã URL-encode, **không nằm trong nội dung được ký**.

- Phải xác minh chữ ký trên **octets của chuỗi encoded đúng quy tắc** và public key **được cấu hình tin cậy** cho đối tác; không đưa các tham số tùy ý khác vào chuỗi ký.
- Decode XML, sau đó serialize lại và verify chữ ký trên XML **không phải phép kiểm tra HTTP-Redirect signature**.
- Việc thấy `Signature`/`SigAlg` chứng minh có giá trị do sender gửi, **không chứng minh chữ ký đúng hoặc signer đáng tin**.
- Không dùng `SigAlg` từ request mà không allowlist thuật toán/phê duyệt trust policy. Thư viện SAML phải bảo vệ chống thuật toán yếu, chữ ký sai và việc thay `RelayState`.
- Chỉ đưa XML đã inflate vào viewer an toàn; việc “không thấy `ds:Signature`” trên AuthnRequest Redirect **không mặc định chứng minh request unsigned**, vì chữ ký có thể nằm ở query `Signature`.

**Không viết tay bộ kiểm tra XMLSig/RedirectSig cho production.** Dùng Spring Security/OpenSAML và certificate trust được cấu hình cho đúng đối tác.

### 4.3. Các trường đọc từ AuthnRequest

Ví dụ **XML tổng hợp, chưa ký**, dùng để minh họa cấu trúc:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-lab-17"
    Version="2.0"
    IssueInstant="2026-11-07T02:30:00Z"
    Destination="https://idp.example.test/sso"
    AssertionConsumerServiceURL="https://sp.example.test/login/saml2/sso/lab"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer>https://sp.example.test/saml2/service-provider-metadata/lab</saml:Issuer>
  <samlp:NameIDPolicy
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      AllowCreate="true"/>
  <samlp:RequestedAuthnContext Comparison="minimum">
    <saml:AuthnContextClassRef>urn:example:authn:workforce-mfa</saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

`urn:example:authn:workforce-mfa` là **profile ví dụ** do tổ chức định nghĩa, không tự là AuthnContextClassRef được mọi IdP công nhận. Cần thỏa thuận chính xác giữa SP/IdP.

| Trường | Cần đối chiếu với |
| --- | --- |
| `ID` | `Response.InResponseTo` hoặc `SubjectConfirmationData.InResponseTo` theo profile và request repository. |
| `IssueInstant` | Đồng hồ UTC, skew hợp lệ, request lifetime của SP/IdP. |
| `Destination` | IdP SingleSignOnService URL đúng metadata/binding. |
| `Issuer` | **SP entityID**, không phải hostname tùy tiện hay registrationId. |
| `AssertionConsumerServiceURL` | **ACS public HTTPS** của SP; IdP có allowlist/matches metadata không? |
| `AssertionConsumerServiceIndex` | Nếu dùng index từ metadata, IdP tra đúng index thay URL literal. |
| `ProtocolBinding` | Binding mà SP muốn IdP dùng để trả Response, thường HTTP-POST. |
| `NameIDPolicy.Format` | Thỏa thuận persistent/transient/email format; không ép một IdP phát kiểu không hỗ trợ. |
| `RequestedAuthnContext` | Policy yêu cầu assurance/context; không tin rằng chỉ request nghĩa là IdP đã đáp ứng. |
| `ForceAuthn` / `IsPassive` | Có yêu cầu reauthentication hoặc không tương tác UI; chỉ xuất hiện khi cấu hình. |

### 4.4. Redirect loop không đồng nghĩa lỗi Base64

Nếu browser cứ quay lại IdP, cần so sánh:
- SP đã tạo `AuthnRequest` mới mỗi lần hay đang retry cùng ID?
- IdP có reject `Destination`/`ACS`/`Issuer`/`NameIDPolicy`/signature không?
- Cookie SP giữ `AbstractSaml2AuthenticationRequest` trong session không còn sau redirect?
- User có IdP session nhưng không đạt AuthnContext/ForceAuthn requirement?
- Spring ACS POST có rơi vào sai `SecurityFilterChain` hoặc bị CSRF policy tùy biến chặn không?
- Domain/HTTPS/proxy có làm `{baseUrl}` sai khiến IdP POST đến host khác không?

**SAMLResponse vắng mặt** khác **SAMLResponse có nhưng validation fail**. Chọn đúng điểm gãy trước khi thay đổi cấu hình trust.

## 5. HTTP-POST: đọc SAMLResponse gửi đến ACS

SAML HTTP-POST binding gửi một form, thường có:

~~~html
<form method="post" action="https://sp.example.test/login/saml2/sso/lab">
  <input type="hidden" name="SAMLResponse" value="BASE64_OF_XML"/>
  <input type="hidden" name="RelayState" value="OPAQUE_STATE"/>
</form>
~~~

Trình duyệt gửi `application/x-www-form-urlencoded`. Trong Network panel, công cụ có thể hiển thị giá trị đã form-decode. Khi có `SAMLResponse` trong form:
1. Lấy **giá trị Base64 sau một lần form-decode**, không thêm URL-decode lần nữa.
2. Base64-decode ra UTF-8 XML bytes; **thông thường không DEFLATE**.
3. Parse XML an toàn, không xử lý DTD/external entities.
4. Xem root `samlp:Response`, `Issuer`, `Destination`, `InResponseTo`, `StatusCode`, `Assertion`/`EncryptedAssertion`.
5. Xác định chữ ký XML có tồn tại ở `Response` hoặc `Assertion`, **nhưng không kết luận crypto/trust validation từ sự tồn tại ấy**.
6. Đối chiếu metadata và `RelyingPartyRegistration` của đúng IdP/ACS.
7. Dùng provider thực của Spring/OpenSAML để đánh giá chữ ký, Conditions, SubjectConfirmation, identity mapping.

**Chú ý dấu `+` trong Base64:** trong raw form body `+` có nghĩa space theo form encoding; một Base64 có dấu plus sẽ được form-encode thành `%2B`. Nếu copy một chuỗi đã decode rồi gọi `URLDecoder` lần nữa, dấu `+` có thể biến thành space và làm hỏng payload. Công cụ Java bên dưới nhận **base64 đã form-decode**, không tự URL-decode lần thứ hai.

### 5.1. Ví dụ Response đã lược bỏ dữ liệu nhạy cảm

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-lab-17"
    Version="2.0"
    IssueInstant="2026-11-07T02:30:12Z"
    Destination="https://sp.example.test/login/saml2/sso/lab"
    InResponseTo="_req-lab-17">
  <saml:Issuer>https://idp.example.test/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <!-- Signed Assertion omitted in this schematic example. -->
</samlp:Response>
~~~

**Đây là một khung XML để đọc field, KHÔNG phải SAML Response hợp lệ có thể đăng nhập.** Nó cố ý thiếu signed Assertion/Subject/Conditions/trust certificate. Trong test ACS thực phải có signed fixture và validator; không được mock provider “always success” rồi nói signature QA PASS.

### 5.2. Thứ tự kiểm tra Response

| Cấp | Field | Ý nghĩa khi debug |
| --- | --- | --- |
| Response | `ID` | Identifier chống replay/đối chiếu audit tùy implementation. |
| Response | `InResponseTo` | Correlate AuthnRequest nếu SP-initiated; unsolicited/IdP-initiated có policy riêng. |
| Response | `Destination` | SP ACS URL người nhận thực tế. |
| Response | `Issuer` | IdP entity ID đã tin cậy. |
| Response | `StatusCode` | Success hoặc error protocol; Response vẫn có thể là XML hợp lệ nhưng login fail. |
| Response/Assertion | `ds:Signature` | Cần XML signature verify theo trusted cert/Reference, không chỉ nhìn thẻ. |
| Assertion | `Issuer` | IdP phát assertion; có thể cùng/khác Response Issuer theo profile, phải được validator kiểm tra. |
| Assertion | `ID`, `IssueInstant` | Assertion identity và thời điểm phát hành. |
| Assertion | `Subject/NameID` | Định danh theo contract; không mặc định là email hoặc local user ID. |
| SubjectConfirmationData | `Recipient` | ACS endpoint nhận assertion hợp lệ. |
| SubjectConfirmationData | `InResponseTo` | Correlate request (đặc biệt với bearer subject confirmation). |
| SubjectConfirmationData | `NotOnOrAfter` | Hạn cuối chấp nhận subject confirmation. |
| Conditions | `NotBefore`, `NotOnOrAfter` | Cửa sổ thời gian assertion, có thể có skew theo policy. |
| AudienceRestriction | `Audience` | **SP entityID** được phép tiêu thụ assertion, không chỉ domain tương tự. |
| AuthnStatement | `AuthnInstant`, `SessionIndex` | IdP authentication time/session reference, hữu ích SLO/freshness. |
| AuthnContextClassRef | AuthnContext | Phương thức/mức bảo đảm được IdP công bố, cần mapping đúng chính sách. |
| AttributeStatement | Name/NameFormat/values | Claims có thể đa giá trị và nhạy cảm; không tự grant admin. |

### 5.3. Xử lý Response báo lỗi

Ví dụ IdP trả `StatusCode` không phải Success, có thể chỉ ra:
- `Requester` hoặc `Responder`;
- `AuthnFailed`;
- `NoAuthnContext`;
- `InvalidNameIDPolicy` hoặc lỗi theo IdP implementation/profile.

Đọc code/subcode và IdP audit trong sandbox; không có nghĩa lúc nào cũng lỗi chữ ký hay tài khoản bị disable. Đừng thay cert khi Status rõ ràng báo yêu cầu AuthnContext không được đáp ứng.

### 5.4. EncryptedAssertion

Khi Response chứa `saml:EncryptedAssertion`, decoder chỉ thấy XML `EncryptedData/EncryptedKey`; **không thể** đọc subject/attributes nếu không có private key giải mã của SP đã được cấu hình. Không yêu cầu IdP tắt encryption vì mục đích debug trong production, không xuất private key lên máy cá nhân/website giải mã. Dùng test SP key trong sandbox, thư viện OpenSAML và audit có redaction.

## 6. HTTP-Artifact và các binding khác

HTTP-Artifact thường xuất hiện dưới dạng:

~~~text
GET https://sp.example.test/acs?SAMLart=<encoded-artifact>&RelayState=...
~~~

`SAMLart` là **tham chiếu**, không phải Base64 XML thông thường. IdP/SP phải thực hiện `ArtifactResolve` / `ArtifactResponse` trên back-channel, thường qua SOAP, để lấy SAML protocol message. Chỉ decode artifact thành bytes không sinh được full Assertion.

Kiểm thử đúng:
- xác định đúng ArtifactResolutionService endpoint/binding từ metadata;
- kiểm tra TLS/mTLS hoặc SOAP message signing/trust theo profile;
- kiểm tra artifact một lần/TTL và service binding;
- trace server-side resolver, **không** đưa private keys hoặc SOAP data lên online analyzer;
- phân biệt browser front-channel error với resolver back-channel DNS/TLS outage.

**Không áp công thức Redirect raw-DEFLATE cho `SAMLart`.** Tương tự, SAML SOAP binding, PAOS/ECP và logout bindings cần pipeline riêng; đừng kết luận mọi `SAMLRequest` luôn nén DEFLATE.

## 7. Đọc IdP metadata và SP metadata

Metadata là **hợp đồng mô tả các endpoints/keys/roles** mà các bên công bố; **không tự là trust anchor** nếu tệp metadata chưa được xác minh nguồn, signature hoặc kênh quản trị.

### 7.1. EntityDescriptor và EntitiesDescriptor

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.test/entity"
    validUntil="2026-12-01T00:00:00Z">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- KeyInfo/X509Certificate would be here. -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.test/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Đây là **sơ đồ metadata**; `KeyDescriptor` trống không phải credential hợp lệ để đưa vào RP config. Metadata thực cần certificate public key thuộc IdP đã được phê duyệt.

Một `EntitiesDescriptor` có thể bao nhiều `EntityDescriptor`; không được chọn entity đầu tiên bằng suy đoán hoặc dùng một signing certificate cho mọi entities. Metadata có thể có chữ ký XML ở root; việc thấy `ds:Signature` **không chứng minh** signer được tin cậy. Phải có external trust anchor, pinned certificate/fingerprint hoặc federation metadata-signing contract.

### 7.2. Các thành phần IdP metadata

| Element/attribute | Ý nghĩa | Kiểm tra |
| --- | --- | --- |
| `EntityDescriptor.entityID` | Định danh IdP theo SAML. | Exact match với Response/Assertion `Issuer` theo profile. |
| `IDPSSODescriptor.protocolSupportEnumeration` | Protocol IdP hỗ trợ. | Có SAML 2.0 protocol. |
| `SingleSignOnService.Binding` | Binding IdP chấp nhận. | Redirect/POST phù hợp với SP. |
| `SingleSignOnService.Location` | Destination của AuthnRequest. | Đúng host/path, TLS/allowlist. |
| `KeyDescriptor use="signing"` | Public certificate(s) xác minh chữ ký IdP. | Khóa tin cậy đúng, rotation policy. |
| `KeyDescriptor use="encryption"` | Public key phục vụ encryption theo vai trò/mô hình. | Không nhầm signer verify key với SP decrypt key. |
| `SingleLogoutService` | Logout endpoint và binding. | Không tự kết luận SLO đã bật/hoạt động. |
| `NameIDFormat` | Các NameID formats IdP công bố. | RequestedNameIDPolicy tương thích. |
| `validUntil` | Thời điểm metadata hết hiệu lực ở scope tương ứng. | Cache refresh/expiry policy. |
| `cacheDuration` | Gợi ý thời lượng cache metadata. | Không phải lúc certificate tự hết hạn. |

### 7.3. Các thành phần SP metadata

| Element/attribute | Ý nghĩa | Kiểm tra |
| --- | --- | --- |
| `EntityDescriptor.entityID` | SP entityID. | Khớp `AuthnRequest.Issuer` và `Assertion.Audience`. |
| `SPSSODescriptor.AuthnRequestsSigned` | SP/IdP policy về việc ký request. | Có đúng signing key/binding signature khi bắt buộc. |
| `SPSSODescriptor.WantAssertionsSigned` | Chính sách về Assertion signatures. | Verify profile/chữ ký thực tế, không chỉ attribute. |
| `AssertionConsumerService.Binding` | Binding tiếp nhận Response. | HTTP-POST/Artifact phù hợp. |
| `AssertionConsumerService.Location` | ACS URL public nhận Response. | Khớp Response `Destination` và Subject `Recipient`. |
| `AssertionConsumerService.index` | ACS endpoint index. | Khớp index trong AuthnRequest nếu dùng. |
| `KeyDescriptor use="signing"` | Public signing cert của SP. | IdP verify SP requests/logout theo thỏa thuận. |
| `KeyDescriptor use="encryption"` | SP public encryption key cho IdP mã hóa Assertion. | SP phải có private key tương ứng để decrypt. |
| `SingleLogoutService` | SP SLO endpoint. | Test LogoutRequest/Response riêng. |
| `validUntil`/`cacheDuration` | Validity/cache metadata nếu có. | Không lẫn với X509 validity. |

**Không suy từ chỉ `KeyDescriptor` rằng toàn bộ hệ thống tự thực hiện PKIX/CRL/OCSP hoặc tự trust metadata key**. Spring Security thường dùng credentials explicit-key gắn trong RP registration; trust management, certificate expiry/revocation checks, metadata signature validation, refresh và rollover cần chính sách cấu hình/test riêng. Một certificate public có trong metadata không chứng minh signer được tin, và hết hạn metadata khác với hết hạn X.509 certificate.

### 7.4. Cách phát hiện sai SP metadata do reverse proxy

Ví dụ external URL thật là `https://sp.example.test`, nhưng app Spring ở `http://internal-service:8080`. Nếu forwarded headers không được quản trị, SP metadata có thể phát:

~~~text
Wrong:
  entityID: http://internal-service:8080/saml2/service-provider-metadata/lab
  ACS:      http://internal-service:8080/login/saml2/sso/lab

Expected:
  entityID: https://sp.example.test/saml2/service-provider-metadata/lab
  ACS:      https://sp.example.test/login/saml2/sso/lab
~~~

IdP có thể reject AuthnRequest, hoặc trả Response có `Destination`/`Recipient` không khớp SP expectation. Giải pháp là **trusted public base URL / forwarded header strategy đúng** và metadata/registration được cập nhật ở IdP; **không tắt Destination/Recipient validation**.

### 7.5. Lấy metadata an toàn

Có thể tải metadata từ endpoint staging có nguồn đã kiểm chứng, ví dụ:

~~~bash
# Chỉ sandbox. Không dùng -k / --insecure khi TLS chưa được xác minh.
curl --fail --silent --show-error \
  --output sp-metadata.xml \
  https://sp.example.test/saml2/metadata/lab
~~~

Không tự động dùng nội dung từ một URL bất kỳ làm trust store production. Nếu metadata fetch qua HTTPS, vẫn phải xác định **nguồn** và chính sách xác thực metadata. XML signature, signed federation metadata hoặc pinned trust anchor có thể là yêu cầu theo hợp đồng. Nếu có nhiều `EntityDescriptor`, chọn đúng `entityID`/role, không lấy tùy tiện.

## 8. Spring Security: cấu hình SP để quan sát trong lab

### 8.1. Dependency và cấu hình tối thiểu

~~~groovy
// build.gradle (fragment trong dự án Spring Boot 3.x).
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

// Một số artifacts OpenSAML/Shibboleth cần repository
// chuyên dụng theo dependency/version thực tế, ví dụ:
// maven { url 'https://build.shibboleth.net/maven/releases/' }
~~~

Ví dụ `application.yml` cho **IdP test đã được duyệt**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          lab:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              entity-id: "https://idp.example.test/entity"
              singlesignon:
                url: "https://idp.example.test/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:lab-idp-signing.crt"
~~~

**Bắt buộc có file `lab-idp-signing.crt` thật từ test IdP được trust**, không lấy bừa certificate do Response tự khai. `sign-request:false` ở đây chỉ minh họa **nếu IdP sandbox cho phép unsigned AuthnRequest**; trong hệ thống yêu cầu signed requests phải cấu hình credential SP và policy phù hợp, không tắt yêu cầu ký để dễ debug. Không dùng mã này làm cấu hình production không kiểm tra.

### 8.2. Bật metadata endpoint và SAML2 login filter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SamlLabSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Spring Security có thể phát metadata ở `/saml2/metadata` và `/saml2/metadata/{registrationId}` khi `saml2Metadata` được bật. Endpoint đó xuất **public metadata**, không bao gồm private key, nhưng vẫn cần phân biệt SP với IdP entity ID và tránh gửi link sai.

### 8.3. Nơi các request/response đi qua

| Spring component | Công việc | Debug symptom |
| --- | --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Nhận initiate URL, tạo/gửi AuthnRequest. | 404/302 sai SSO URL, thiếu `SAMLRequest`. |
| `Saml2AuthenticationRequestRepository` (implementation tùy version) | Lưu state request để đối chiếu response. | `InResponseTo` không tìm thấy, lost HttpSession. |
| `Saml2WebSsoAuthenticationFilter` | Bắt ACS `SAMLResponse`. | Response POST tới URL sai chain, 401/403/redirect loop. |
| `Saml2AuthenticationToken` | Mang SAMLResponse và RP registration tới manager. | Resolve sai registration/certificate. |
| OpenSAML-backed authentication provider | Decode/validate signature, issuer, audience, expiry, subject confirmation. | Crypto/trust/Conditions fail. |
| `Saml2Authentication` / `Saml2AuthenticatedPrincipal` | Authentication/principal sau khi SAML đã được xác minh. | Principal thành công nhưng local role/tenant sai. |
| `RelyingPartyRegistrationRepository` | Chứa SP/IdP metadata/credentials đúng source. | Missing/wrong registration, stale IdP certificate. |

**Không bao giờ** thay provider bằng implementation “accept all XML” chỉ để đọc SAMLResponse. Giải mã offline chỉ hỗ trợ phân tích; authentication quyết định bởi filter/provider và trust config thật.

### 8.4. Debug logging có kiểm soát

Trong **sandbox cô lập**, có thể tạm tăng mức log:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.saml2: DEBUG
~~~

Tùy implementation, debug output có thể làm lộ principal/attributes hoặc chi tiết session. **Không bật TRACE vô thời hạn ở production**, không ghi raw SAMLResponse/NameID/cookies/token. Xem lọc dữ liệu, retention và quyền truy cập log. Nếu một vấn đề không cần debug token raw, dùng correlation ID, event reason class và timestamp.

### 8.5. Khi có nhiều IdPs

Hai registrations:

~~~text
registrationId=lab-corp  -> IdP entityID A; verify cert A; ACS A
registrationId=lab-partner -> IdP entityID B; verify cert B; ACS B
~~~

Không lấy `Issuer` do attacker gửi làm căn cứ tự nạp một certificate bất kỳ từ chính Response. RP resolution và credential lookup phải dựa trên **trusted registrations**, allowlist và stored request state; xử lý IdP-initiated flow cần policy đặc biệt nghiêm ngặt khi không có request ID từ trước.

## 9. Java 17: công cụ giải mã an toàn có giới hạn

Mục tiêu công cụ:
- **Chỉ đọc local files**, không fetch URL hoặc gửi payload ra mạng.
- Nhận `redirect-file` (chứa raw query có `SAMLRequest`), `post-file` (chỉ chứa giá trị Base64 của form `SAMLResponse` đã form-decode), `metadata-file` (XML metadata), hoặc `selftest`.
- Không in `NameID`, email, assertions, attributes, RelayState, cookies, private keys hay raw XML.
- Giới hạn file input và XML inflated output, không để decompression bomb phình vô hạn.
- Chặn DOCTYPE, external entities, XInclude và external schema fetching trong JAXP.
- Chỉ in **root type, ID, Issuer, Destination, số KeyDescriptor và dấu hiệu có thẻ Signature**.
- **Không** verify XMLSig, RedirectSig, metadata trust, NotBefore/NotOnOrAfter hoặc replay; **không** được sử dụng công cụ này để cấp quyền cho user.

### 9.1. `SamlLabInspector.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.SAXException;
import org.xml.sax.helpers.DefaultHandler;

public final class SamlLabInspector {
    private static final int MAX_FILE = 2_000_000;
    private static final int MAX_XML = 1_000_000;

    private static final String PROTOCOL =
        "urn:oasis:names:tc:SAML:2.0:protocol";
    private static final String ASSERTION =
        "urn:oasis:names:tc:SAML:2.0:assertion";
    private static final String METADATA =
        "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final String DSIG =
        "http://www.w3.org/2000/09/xmldsig#";

    private SamlLabInspector() {}

    private static byte[] readLimited(Path path) throws IOException {
        if (Files.size(path) > MAX_FILE) {
            throw new IOException("Input file exceeds limit");
        }
        byte[] bytes = Files.readAllBytes(path);
        if (bytes.length > MAX_FILE) {
            throw new IOException("Input file exceeds limit");
        }
        return bytes;
    }

    // Expects the RAW query without a leading URL/path.
    private static String getRawQueryValue(
            String rawQuery, String wanted) {
        String q = rawQuery.strip();
        if (q.startsWith("?")) {
            q = q.substring(1);
        }
        for (String part : q.split("&", -1)) {
            int equal = part.indexOf('=');
            if (equal < 0) {
                continue;
            }
            if (part.substring(0, equal).equals(wanted)) {
                return URLDecoder.decode(
                    part.substring(equal + 1),
                    StandardCharsets.UTF_8
                );
            }
        }
        return null;
    }

    private static byte[] decodePostBase64(String base64) {
        // post-file contains the Base64 FIELD VALUE already
        // form-decoded once by the browser/devtools.
        // Do not call URLDecoder again on this value.
        String clean = base64.replaceAll("\\s+", "");
        byte[] bytes = Base64.getDecoder().decode(clean);
        if (bytes.length > MAX_XML) {
            throw new IllegalArgumentException(
                "Decoded XML exceeds limit");
        }
        return bytes;
    }

    private static byte[] inflateRaw(byte[] compressed)
            throws IOException {
        Inflater inflater = new Inflater(true);
        try (InflaterInputStream in =
                 new InflaterInputStream(
                     new ByteArrayInputStream(compressed),
                     inflater);
             ByteArrayOutputStream out =
                 new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) != -1) {
                if (out.size() + n > MAX_XML) {
                    throw new IOException("Inflated XML exceeds limit");
                }
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        } finally {
            inflater.end();
        }
    }

    private static byte[] decodeRedirectQuery(String rawQuery)
            throws IOException {
        String value = getRawQueryValue(
            rawQuery, "SAMLRequest");
        if (value == null) {
            value = getRawQueryValue(rawQuery, "SAMLResponse");
        }
        if (value == null) {
            throw new IllegalArgumentException(
                "Expected SAMLRequest or SAMLResponse in raw query");
        }
        byte[] compressed = Base64.getDecoder().decode(
            value.replaceAll("\\s+", ""));
        if (compressed.length > MAX_FILE) {
            throw new IOException("Compressed input exceeds limit");
        }
        return inflateRaw(compressed);
    }

    private static Document parseXml(byte[] xml)
            throws Exception {
        if (xml.length > MAX_XML) {
            throw new IOException("XML exceeds limit");
        }
        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        factory.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler());
        Document document = builder.parse(
            new ByteArrayInputStream(xml));
        return document;
    }

    private static String directIssuer(Element root) {
        NodeList nodes = root.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node node = nodes.item(i);
            if (node instanceof Element e
                    && ASSERTION.equals(e.getNamespaceURI())
                    && "Issuer".equals(e.getLocalName())) {
                return e.getTextContent().strip();
            }
        }
        return "-";
    }

    private static String summary(byte[] xml)
            throws Exception {
        Document document = parseXml(xml);
        Element root = document.getDocumentElement();
        String kind = root.getLocalName();
        String namespace = root.getNamespaceURI();

        if (METADATA.equals(namespace)
                && ("EntityDescriptor".equals(kind)
                  || "EntitiesDescriptor".equals(kind))) {
            int idps = root.getElementsByTagNameNS(
                METADATA, "IDPSSODescriptor").getLength();
            int sps = root.getElementsByTagNameNS(
                METADATA, "SPSSODescriptor").getLength();
            int keys = root.getElementsByTagNameNS(
                METADATA, "KeyDescriptor").getLength();
            return "kind=" + kind
                + "; entityID=" + root.getAttribute("entityID")
                + "; idpDescriptors=" + idps
                + "; spDescriptors=" + sps
                + "; keyDescriptors=" + keys;
        }

        if (!PROTOCOL.equals(namespace)) {
            throw new IllegalArgumentException(
                "Unexpected XML namespace/root");
        }

        boolean signatureElement =
            root.getElementsByTagNameNS(
                DSIG, "Signature").getLength() > 0;

        return "kind=" + kind
            + "; id=" + root.getAttribute("ID")
            + "; issuer=" + directIssuer(root)
            + "; destination=" + root.getAttribute("Destination")
            + "; xmlSignatureElement=" + signatureElement;
    }

    private static byte[] deflateRaw(byte[] xml)
            throws IOException {
        Deflater deflater = new Deflater(
            Deflater.DEFAULT_COMPRESSION, true);
        try (ByteArrayOutputStream output =
                 new ByteArrayOutputStream();
             DeflaterOutputStream stream =
                 new DeflaterOutputStream(output, deflater)) {
            stream.write(xml);
            stream.finish();
            return output.toByteArray();
        } finally {
            deflater.end();
        }
    }

    private static void selftest() throws Exception {
        String auth = """
            <samlp:AuthnRequest
              xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
              xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
              ID="_req-test"
              Destination="https://idp.example.test/sso">
              <saml:Issuer>https://sp.example.test/metadata</saml:Issuer>
            </samlp:AuthnRequest>
            """;
        String response = """
            <samlp:Response
              xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
              xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
              ID="_res-test"
              Destination="https://sp.example.test/acs">
              <saml:Issuer>https://idp.example.test/entity</saml:Issuer>
            </samlp:Response>
            """;
        String metadata = """
            <md:EntityDescriptor
              xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
              entityID="https://idp.example.test/entity">
              <md:IDPSSODescriptor
                protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
                <md:SingleSignOnService
                  Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                  Location="https://idp.example.test/sso"/>
              </md:IDPSSODescriptor>
            </md:EntityDescriptor>
            """;

        byte[] compressed = deflateRaw(
            auth.getBytes(StandardCharsets.UTF_8));
        String query = "SAMLRequest=" + URLEncoder.encode(
            Base64.getEncoder().encodeToString(compressed),
            StandardCharsets.UTF_8);

        System.out.println("redirect: " +
            summary(decodeRedirectQuery(query)));
        System.out.println("post: " +
            summary(decodePostBase64(
                Base64.getEncoder().encodeToString(
                    response.getBytes(StandardCharsets.UTF_8)))));
        System.out.println("metadata: " +
            summary(metadata.getBytes(StandardCharsets.UTF_8)));

        String dangerous = """
            <!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]>
            <a>&x;</a>
            """;
        try {
            parseXml(dangerous.getBytes(StandardCharsets.UTF_8));
            throw new IllegalStateException(
                "DOCTYPE unexpectedly accepted");
        } catch (SAXException expected) {
            System.out.println("doctype=REJECTED");
        }
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length == 1 && "selftest".equals(args[0])) {
            selftest();
            return;
        }
        if (args.length != 2) {
            System.err.println(
                "Usage: selftest | redirect-file file"
                + " | post-file file | metadata-file file");
            System.exit(2);
        }
        byte[] input = readLimited(Path.of(args[1]));
        byte[] xml = switch (args[0]) {
            case "redirect-file" -> decodeRedirectQuery(
                new String(input, StandardCharsets.UTF_8));
            case "post-file" -> decodePostBase64(
                new String(input, StandardCharsets.UTF_8));
            case "metadata-file" -> input;
            default -> throw new IllegalArgumentException(
                "Unknown mode");
        };
        System.out.println(summary(xml));
    }
}
~~~

### 9.2. Biên dịch/chạy bằng JDK 17

~~~bash
javac --release 17 SamlLabInspector.java
java SamlLabInspector selftest
~~~

**Stdout chính xác của `selftest`:**

~~~text
redirect: kind=AuthnRequest; id=_req-test; issuer=https://sp.example.test/metadata; destination=https://idp.example.test/sso; xmlSignatureElement=false
post: kind=Response; id=_res-test; issuer=https://idp.example.test/entity; destination=https://sp.example.test/acs; xmlSignatureElement=false
metadata: kind=EntityDescriptor; entityID=https://idp.example.test/entity; idpDescriptors=1; spDescriptors=0; keyDescriptors=0
doctype=REJECTED
~~~

Mẫu `AuthnRequest` và `Response` trong selftest **cố ý không ký**, Response không có Assertion/Conditions, metadata không chứa signing key. Chúng chỉ kiểm tra **decoder/parser**, không phải valid SAML login fixtures. Nếu đưa vào ACS thật, provider phải reject theo validation policy.

### 9.3. Dùng công cụ với file đã được bảo vệ

~~~bash
# File query.txt chứa CHỈ raw query string bắt đầu SAMLRequest=...
java SamlLabInspector redirect-file query.txt

# File saml-response.b64 chứa CHỈ base64 FIELD VALUE
# của SAMLResponse đã được form-decode đúng một lần.
java SamlLabInspector post-file saml-response.b64

# File idp-metadata.xml là XML metadata sandbox đã được tải
# từ trusted IdP metadata source.
java SamlLabInspector metadata-file idp-metadata.xml
~~~

- Chương trình không log raw XML, nhưng các input files **vẫn có thể chứa PII/sensitive SAML data**. Lưu tạm trên máy QA an toàn, tránh commit, mã hóa/lifecycle nếu cần, xóa khi xong.
- `query.txt` phải chứa **raw query, không kèm `https://...?...`**. Nếu DevTools đã decode tham số, cần nhận biết trạng thái để không URL-decode hai lần. Với dấu `+` và `%2B`, sai một bước có thể phá Base64.
- `saml-response.b64` phải chứa **Base64 của field value**, không phải chuỗi raw form body `SAMLResponse=...&RelayState=...`.
- Với `SAMLart`, không dùng bất kỳ mode nào ở trên để giả định thu được Assertion.
- Với `EncryptedAssertion`, công cụ chỉ báo XML có các thẻ tương ứng ở ngoài; không giải mã content.
- `xmlSignatureElement=true` chỉ nói parser tìm thấy một thẻ `ds:Signature` ở đâu đó dưới root, **không** xác minh Reference/digest/algorithm/trust. Với Redirect, có thể **không có XML Signature nhưng vẫn có chữ ký query**; công cụ không verify `SigAlg`/`Signature`.
- `EntityDescriptor` có `KeyDescriptor` không đồng nghĩa metadata signer/key được xác minh.
- Giới hạn file 2 MB/XML inflated 1 MB là **giới hạn lab chọn để giảm rủi ro**, không phải SAML specification limit. IdP thực tế có thể phát XML lớn hơn; chỉ nâng giới hạn qua review rủi ro.

### 9.4. Vì sao không in NameID/attributes?

SAML assertions có thể chứa email, tên, employee ID, groups, permissions, tình trạng nhân sự hoặc thông tin định danh. Một công cụ debug nên mặc định:
- chỉ hiển thị root, ID dạng synthetic, issuer/destination tin cậy và số descriptors;
- cho biết có thẻ Signature **nhưng không nói signature pass**;
- không in toàn bộ `AttributeStatement`, `NameID`, XML signature value/KeyInfo/X509Certificate;
- nếu cần điều tra attribute mapping, dùng log đã redacted hoặc test data mà không chứa PII;
- không lưu raw HTTP bodies vào CI logs/screenshot/artifacts công khai.

## 10. Đối chiếu Request, Response và metadata: cùng một bảng

| Khẳng định cần xác minh | AuthnRequest | SAMLResponse/Assertion | Metadata/config |
| --- | --- | --- | --- |
| SP entity ID | `Issuer` ở AuthnRequest | `AudienceRestriction/Audience` | `SP EntityDescriptor.entityID`. |
| IdP entity ID | `Destination` là endpoint SSO, không phải entityID | `Response/Assertion.Issuer` | `IdP EntityDescriptor.entityID`. |
| ACS URL public | `AssertionConsumerServiceURL`/index | `Destination` và `SubjectConfirmationData.Recipient` | `SP AssertionConsumerService.Location` và RP registration. |
| Request correlation | `ID` | `InResponseTo` (Response/SubjectConfirmationData) | Stored AuthnRequest repository/session. |
| Response binding | `ProtocolBinding` nếu SP nêu | HTTP POST/Artifact route | `SP ACS.Binding`. |
| IdP SSO binding/URL | Request được gửi tới `Destination` | N/A | `IdP SingleSignOnService Binding/Location`. |
| NameID | `NameIDPolicy.Format` | `Subject/NameID.Format` và value | `IdP NameIDFormat` + identity contract. |
| Assurance | `RequestedAuthnContext`/ForceAuthn | `AuthnContextClassRef`/AuthnInstant | IdP/SP policy contract. |
| Signature trust | Redirect `SigAlg/Signature` hoặc XMLSig POST | XML `ds:Signature` trên Response/Assertion | Approved signing credential(s), signed metadata trust. |
| Time window | `IssueInstant` | `Conditions`/`SubjectConfirmationData` | Clock skew/cert and metadata validity policies. |
| Session logout | Request/Response context | `AuthnStatement.SessionIndex` | `SingleLogoutService` binding/URLs, state mapping. |

### 10.1. Ví dụ lỗi “Destination khớp nhưng Audience sai”

~~~text
AuthnRequest Issuer:
  https://sp.example.test/metadata/appA

SAMLResponse Destination:
  https://sp.example.test/login/saml2/sso/appA

Assertion Audience:
  https://sp.example.test/metadata/appB  (SAI)
~~~

SAMLResponse có thể POST đến đúng ACS A nhưng Assertion lại cấp cho SP B. **Không được** cho A login chỉ vì Destination khớp và chữ ký IdP hợp lệ. Phải kiểm tra Audience đúng **SP entityID A**.

### 10.2. Ví dụ lỗi “cùng NameID nhưng khác IdP”

~~~text
IdP-A entityID: https://idp-a.example.test/entity
NameID: user-17

IdP-B entityID: https://idp-b.example.test/entity
NameID: user-17
~~~

Hai NameID strings trùng nhau **không** chứng minh cùng local account. Khóa liên kết cần source/issuer/SP scope, hoặc immutable directory identity mapping có trust. Không tự map bằng `email` hoặc NameID value duy nhất.

### 10.3. Ví dụ lỗi “InResponseTo không khớp”

~~~text
SP stored AuthnRequest ID: _req-100
Response.InResponseTo:      _req-200
SubjectConfirmationData:   _req-200
~~~

Có thể do:
- mất HttpSession giữa redirect và ACS POST;
- browser khác/replay, request repository hết hạn;
- concurrent logins trên cùng browser làm state đổi tùy implementation;
- reverse proxy load balancing/session store không nhất quán;
- response attacker tự chế.

**Không tắt `InResponseTo` validation để làm test xanh** khi SP-initiated flow là yêu cầu; phân tích stored request state và IdP response production contract. Với IdP-initiated/unsolicited SSO, policy riêng cần bảo vệ replay/recipient/audience và không được vô điều kiện nhận mọi response.

### 10.4. Ví dụ lỗi “đúng signing cert nhưng không đọc được EncryptedAssertion”

- IdP signing verification cert dùng để xác minh chữ ký IdP.
- SP decryption private key dùng để giải mã Assertion mà IdP đã mã hóa bằng SP encryption public key.
- SP signing private key dùng để ký AuthnRequest/logout nếu cần.

Ba vai trò **khác nhau** dù một số triển khai dùng cùng keypair cho nhiều vai trò. Không gửi decryption private key tới IdP hay online decoder; không thay verify key của IdP bằng SP key.

## 11. XML Signature: cái nhìn thấy được và cái phải xác minh

### 11.1. Có `ds:Signature` chưa đủ

Trong XML có thể có:

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <!-- CanonicalizationMethod, SignatureMethod, Reference ... -->
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <ds:KeyInfo>...</ds:KeyInfo>
</ds:Signature>
~~~

Một parser XML chỉ cho biết thẻ xuất hiện. Để chấp nhận authentication phải kiểm tra:
1. **Signature Cryptography**: digest/reference/canonicalization/signature đúng trên đúng element/protocol profile.
2. **Trust**: signer certificate/public key thuộc RP registration/metadata đã được xác minh nguồn; không tự trust `KeyInfo` trong payload.
3. **Signed element consumption**: ứng dụng dùng **chính Assertion/Response đã được validator xác minh**, chống XML Signature Wrapping.
4. **Protocol Conditions**: đúng issuer, audience, recipient, InResponseTo, time window, SubjectConfirmation, replay policy.
5. **Local account**: valid SAML identity link và local permission/tenant checks.

Một Response hợp lệ có thể ký Response hoặc Assertion theo profile/trust configuration, song không phải “bất kỳ một chữ ký ở bất kỳ đâu” đều đủ. Dùng Spring/OpenSAML provider và policies tương ứng; không tự viết XPath lấy NameID đầu tiên khi chưa xác định signed subtree.

### 11.2. Metadata certificate và certificate validity

- `KeyDescriptor` chứa public keys/certs theo vai trò; nó **không phải private key**.
- Metadata có thể signed; chữ ký metadata khác với chữ ký một SAML Assertion.
- `validUntil` của metadata, X.509 `NotAfter` của certificate và `Conditions NotOnOrAfter` của assertion là **ba thời hạn riêng biệt**.
- Explicit-key verification dựa trust config không có nghĩa mọi đường đi đều tự kiểm tra PKIX chain/CRL/OCSP; việc kiểm tra certificate expiry/revocation phải được policy/implementation xác nhận riêng.
- Khi IdP rollover certificate, có thể cần một giai đoạn overlap keys được phê duyệt; **không** thay cert ngay chỉ vì Response có KeyInfo lạ.
- Không coi thông tin metadata tải được từ URL mới là nguồn trust mà không kiểm tra domain/source/signature/certificate pinning.

### 11.3. Xác minh chữ ký HTTP-Redirect đúng octets

Một số công cụ decode SAMLRequest rồi build lại query với giá trị được percent-encode theo cách khác. Hai URL có thể decode thành XML giống nhau nhưng **có octets khác nhau**, khiến query signature verify sai. Khi điều tra:
- lưu original raw query theo chính sách và tránh rewrite `+`/`%20`/`%2B`;
- dùng thứ tự canonical parameter string quy định bởi OASIS;
- đối chiếu `SigAlg`/verification credential từ SP metadata;
- tuyệt đối không test signature bằng cách so chuỗi `Signature` có tồn tại.

## 12. Troubleshooting theo triệu chứng

### 12.1. IdP báo “Invalid request” ngay khi nhận AuthnRequest

Kiểm tra `Issuer=SP entityID`, `Destination=IdP SSO URL`, AuthnRequest ID/IssueInstant, `AssertionConsumerServiceURL` có nằm allowlist IdP không, NameIDPolicy/AuthnContext policy, binding, signed request requirement và SigAlg/key. Nếu request dùng Redirect, xác minh raw-DEFLATE và query signature; đừng dùng POST XMLSig validator để verify nó.

### 12.2. Browser không POST SAMLResponse về ACS

Có thể IdP authentication fail, IdP không có session, user hủy login, ACS URL sai, network/proxy/CORS? Browser top-level form POST **không phải AJAX fetch**, nên không mặc định đổ lỗi CORS. Xem IdP status/error logs, HTML form action, browser navigation, TLS certificate và response status.

### 12.3. ACS nhận POST rồi trả 401/403/redirect loop

Kiểm tra:
- `Saml2WebSsoAuthenticationFilter` match đúng URL/HTTP method/registrationId chưa?
- Request bị bắt bởi một `SecurityFilterChain` API/stateless khác hay CSRF rule tùy biến?
- Có `RelyingPartyRegistrationRepository` chứa correct IdP cert/Issuer không?
- Signature/trust/audience/recipient/conditions/response correlation có fail?
- Session cookie/state bị mất vì SameSite cross-site POST, load balancer, reverse proxy?
- Failure handler trả 302 về login là hợp lệ về mặt HTTP nhưng **không chứng minh SAML validation pass**.

### 12.4. `Response.Status` không Success

Đọc StatusCode/SubStatus và IdP audit. `NoAuthnContext`, `InvalidNameIDPolicy` hoặc `AuthnFailed` yêu cầu xử lý khác nhau. Không tự đổi cert khi dấu vết cho thấy IdP từ chối AuthnContext.

### 12.5. “Signature element present” nhưng validation fail

Kiểm tra:
- ký trên Response hay Assertion, trust agreement yêu cầu cái gì;
- SP đang dùng IdP cert cũ hay cert ký mới chưa rollover;
- ký bằng untrusted key, reference/digest mismatch, XML bị biến đổi;
- Redirect query canonicalization khác, RelayState thay đổi;
- XML parser bị wrap/hardening lỗi, xung đột namespaces;
- certificate metadata khác nguồn có hợp lệ và đã trust không.

Không bỏ signature check hoặc tin cert embedded trong Response vì XML hiển thị chữ ký hợp lý.

### 12.6. “NotBefore” hoặc “NotOnOrAfter” fail

So sánh UTC clocks trên IdP/SP, timezone và NTP; kiểm tra thời gian assertion, SubjectConfirmation và request/response TTL riêng. Giới hạn clock skew phải có chính sách, không tăng vô hạn. Metadata expiry/X.509 validity **không thay** assertion Conditions.

### 12.7. “Audience”, “Recipient”, “Destination” khác nhau

- `Audience` phải match SP entityID;
- `Recipient` và `Destination` thường liên quan public ACS URL;
- `AuthnRequest.Issuer` là SP entityID;
- `Response/Assertion.Issuer` là IdP entityID;
- Sai `{baseUrl}` do HTTP backend + HTTPS frontend là nguyên nhân phổ biến.

Không “fix” bằng string replace assertion XML rồi đưa vào login; phá chữ ký và ẩn lỗi config.

### 12.8. “NameID bị sai format” hoặc app lấy email không đúng

Có thể IdP phát persistent/transient/emailAddress NameID theo thỏa thuận, hoặc attributes có đa giá trị. `NameID` không tự là local user ID; SAML `AttributeStatement` có `Name`/`NameFormat`/values cần mapping approved. Chữ ký hợp lệ không tự cấp role admin.

### 12.9. ArtifactResolve fail

Nếu chỉ có `SAMLart`, kiểm tra SOAP ArtifactResolutionService URL, network/TLS, SAML artifact one-time/expiry, IdP back-channel credentials và resolver logs. Không debug bằng Redirect inflater.

## 13. Test matrix: đúng binding, đúng trường, đúng trust

| ID | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| D01 | SP tạo HTTP-Redirect SAMLRequest đúng binding. | URL-decode/Base64/raw-DEFLATE cho AuthnRequest XML. |
| D02 | Chọn `Inflater(false)` cho raw DEFLATE. | Lỗi decode được nhận diện, sửa đúng inflater. |
| D03 | Gọi URLDecoder hai lần trên `SAMLRequest`. | Test phát hiện payload hỏng/khác raw query. |
| D04 | Raw Base64 form POST chứa `+` được decode hai lần. | Reject/cảnh báo; không biến `+` thành space. |
| D05 | POST `SAMLResponse` đúng Base64 XML không DEFLATE. | Decode và parse an toàn. |
| D06 | POST `SAMLRequest` tới IdP. | Base64 XML; không raw inflater. |
| D07 | GET/POST chứa `SAMLart`. | Nhận biết Artifact binding, không giả XML. |
| D08 | Redirect có SigAlg/Signature. | Xác minh query signature đúng encoded octets/trust. |
| D09 | Redirect có `Signature` nhưng invalid. | Validator reject, không chỉ kiểm tra có tham số. |
| D10 | POST XML có `ds:Signature` nhưng untrusted key. | Validator reject. |
| D11 | XML chứa DOCTYPE/external entity. | Inspector parser reject. |
| D12 | Compressed XML quá lớn (zip bomb). | Inspector giới hạn inflated bytes. |
| D13 | Response unsigned từ test IdP. | Spring ACS reject theo signing policy. |
| D14 | Response signed đúng test trusted cert. | Authentication provider có thể chấp nhận nếu mọi conditions hợp lệ. |
| D15 | Assertion signed nhưng Audience sai. | Reject. |
| D16 | Response Destination sai public ACS. | Reject. |
| D17 | SubjectConfirmationData Recipient sai. | Reject. |
| D18 | Response InResponseTo khác AuthnRequest ID. | Reject SP-initiated theo policy. |
| D19 | Missing request state/session. | Test failure rõ; không disable correlation. |
| D20 | Assertion Conditions chưa bắt đầu. | Reject ngoài allowed clock skew. |
| D21 | Assertion/SubjectConfirmation đã hết hạn. | Reject. |
| D22 | SAML Response non-Success status. | Không tạo authenticated session. |
| D23 | Assertion replayed ID/Response ID. | Chống replay theo implementation/policy. |
| D24 | EncryptedAssertion thiếu SP decrypt key. | Decrypt fail, không tắt encryption production. |
| D25 | Có nhiều assertions, signature wrapping payload. | Validator chỉ tiêu thụ signed/approved data. |
| D26 | NameIDPolicy yêu cầu persistent, IdP chỉ hỗ trợ transient. | Protocol error/negotiation, không tự map email. |
| D27 | AuthnContext requirement không đáp ứng. | IdP error/step-up theo policy. |
| D28 | IdP metadata entityID khác Response Issuer. | Reject/trust config review. |
| D29 | SP metadata entityID khác Assertion Audience. | Reject/metadata correction. |
| D30 | SP ACS public HTTPS khác runtime {baseUrl}. | Test phát hiện proxy/callback mismatch. |
| D31 | IdP SingleSignOnService Location sai. | AuthnRequest đi sai URL hoặc IdP reject. |
| D32 | SP ACS Binding khác IdP Response binding. | Test phát hiện binding mismatch. |
| D33 | Metadata có expired validUntil. | Refresh/trust policy không dùng stale metadata tùy tiện. |
| D34 | X509 signing cert rollover chưa được cấu hình. | Reject/alert; có approved overlap plan. |
| D35 | Metadata có KeyDescriptor nhưng chưa verify source. | Không auto-trust. |
| D36 | Signature embedded KeyInfo chứa attacker cert. | Không lấy làm trust anchor. |
| D37 | SAML Request ID trùng giữa concurrent logins. | Test phát hiện ID generation/session correlation risk. |
| D38 | RelayState bị thay đổi/open redirect. | Reject/tamper protection theo binding/profile. |
| D39 | Một IdP entityID ở multi-tenant RP bị resolve sai. | Không map sang wrong registration/account. |
| D40 | Same NameID từ hai IdPs. | Không auto-link local user theo NameID trần/email. |
| D41 | CSRF policy chặn ACS cross-site POST ngoài dự kiến. | Sửa filter matcher/protocol config, không tắt CSRF toàn app. |
| D42 | Browser SameSite không gửi request cookie vào ACS. | Phân tích cookie/session, test browser thật. |
| D43 | Metadata endpoint /saml2/metadata/lab phản hồi đúng EntityDescriptor. | SP metadata có entityID/ACS/cert đúng test setup. |
| D44 | Inspector phát hiện xmlSignatureElement=true. | Chỉ thông báo thẻ tồn tại; không báo signature pass. |
| D45 | Inspector selftest nhận unsigned synthetic Response. | Parser đọc field; ACS validation phải fail nếu gửi thật. |
| D46 | IdP ký Assertion bằng cert mới trong overlap period. | Chỉ trust khi cert được approved/rotation staged. |
| D47 | HAR có raw SAMLResponse/cookie. | QA fail privacy, redact/encrypt/restrict. |
| D48 | Bắt gói trên production account rồi paste lên online decoder. | QA fail, chuyển sang sandbox/local tool. |
| D49 | Browser chỉ có SAMLart, không thấy Assertion. | Đọc ArtifactResolve/Response ở trusted server logs. |
| D50 | Tắt signature/issuer/audience validation để test xanh. | Security QA fail, không chấp nhận. |
| D51 | SP gửi AuthnRequest POST nhưng tool cố raw-DEFLATE. | Binding detection fail, sửa pipeline. |
| D52 | Metadata EntityDescriptor chứa cả signing/encryption roles. | Phân biệt đúng trust/verifying/decrypting credentials. |

### 13.1. Lab A — đo luồng SAML2

1. SP/IdP staging đã trust credentials, browser mới.
2. Bắt Network và tìm HTTP-Redirect `SAMLRequest` → kiểm tra raw DEFLATE decode, `Issuer`, `Destination`, ACS.
3. Đăng nhập user thử nghiệm, tìm HTTP-POST `SAMLResponse` → Base64 decode thành XML.
4. So sánh `AuthnRequest.ID` với `InResponseTo`, `SP entityID` với `Audience`, IdP `entityID` với Response/Assertion Issuer.
5. Kiểm tra Response signed fixture bằng Spring/OpenSAML provider thật.
6. Không upload HAR/token/Assertion lên công cụ bên ngoài.

### 13.2. Lab B — metadata và rollover

1. Lấy SP metadata từ `/saml2/metadata/lab` trong sandbox.
2. Lấy IdP metadata từ nguồn đã được duyệt.
3. So `entityID`, SSO/ACS URLs, Binding, signing/encryption KeyDescriptor, `validUntil`/`cacheDuration`.
4. Mô phỏng rollover signing cert test có overlap window và negative untrusted signer.
5. Kiểm tra metadata refresh/pinning theo policy thay vì tin KeyInfo trong payload.

### 13.3. Lab C — negative SAML responses

Tạo signed synthetic fixtures với test IdP key:
- valid SP-initiated response với `InResponseTo` đúng;
- wrong audience và wrong recipient;
- expired/not-yet-valid conditions;
- untrusted signing key/invalid digest;
- response replay và EncryptedAssertion decrypt failure;
- NameID/attribute mapping sai, local account disabled.

**Không** test security provider bằng `MockMvc.with(authentication(new Saml2Authentication(...)))` vì cách đó cố ý bỏ qua signature/conditions validation.

## 14. Công cụ kiểm tra bổ sung và giới hạn

### 14.1. Browser SAML viewer extensions

Có extension hiển thị SAML messages ngay trong Network. Trước khi dùng:
- kiểm tra extension nguồn/mã/permissions và bản được tổ chức phê duyệt;
- chỉ dùng browser sandbox không giữ production sessions;
- bảo đảm extension không gửi dữ liệu tới server ngoài;
- không dựa vào icon “signature present” như cryptographic trust verdict;
- không bật extension độc quyền quyền truy cập mọi site trong browser làm việc chính.

### 14.2. `xmllint` và pretty-print

Pretty-printer có thể giúp đọc XML **sau khi đã decode**, nhưng XML từ IdP là untrusted input. Phải tắt network access/external entities, giới hạn input, không dùng một XML parser mặc định cho tài liệu lạ trong production. Hơn nữa, **reformatting XML có thể làm hỏng signature semantics/canonicalization** nếu được dùng để verify; pretty-print chỉ phục vụ hiển thị, không phải nguồn bytes cho chữ ký.

### 14.3. OpenSSL/certificate inspection

Với certificate fixture của IdP đã được cấp và quản trị, có thể xem subject/serial/dates/fingerprint:

~~~bash
openssl x509 -in lab-idp-signing.crt -noout \
  -subject -issuer -dates -serial -fingerprint -sha256
~~~

Đây là **kiểm tra mô tả public certificate**, không phải SAML signature verification. Nếu certificate ở metadata trong `ds:X509Certificate` dạng Base64 DER, cần trích xuất/định dạng PEM đúng trong sandbox trước khi chạy OpenSSL; không copy private key. Một fingerprint khớp cert được IdP gửi **chưa đủ** nếu nguồn fingerprint chưa được admin phê duyệt.

### 14.4. Test Signed Response bằng Spring/OpenSAML

Chỉ một integration test chạy qua `Saml2WebSsoAuthenticationFilter` với test `RelyingPartyRegistration`/trust credentials và một SAMLResponse signed fixture đúng có thể kiểm tra thực tế:
- signature trust, issuer, audience, destination, conditions;
- request/session correlation, bearer SubjectConfirmation;
- local user identity/role mapping;
- authenticated session sau callback;
- negative response không tạo session.

Nếu mock `AuthenticationManager` hoặc truyền `Saml2Authentication` đã dựng sẵn, đó là **test sau authentication**, không phải test XML security.

## 15. Runbook an toàn cho lỗi SAML login

1. **Xác định đúng flow:** SP-initiated hay IdP-initiated; Redirect, POST hay Artifact binding; registrationId/IdP nguồn nào.
2. **Tạo lại trên sandbox** có synthetic user, giờ UTC/NTP đúng, proxy và phiên trình duyệt sạch.
3. **Bắt minimal trace** qua Network Preserve log; ghi method/URL/status và tên tham số, không công khai payload.
4. **Giải mã local theo binding:** Redirect raw DEFLATE, POST Base64 XML, Artifact back-channel.
5. **So XML fields**: request ID, Issuers, Destination, ACS, Response Status, Audience, Recipient, Conditions, NameIDPolicy/AuthnContext.
6. **So metadata đã trusted**: entity IDs, SSO/ACS endpoints/bindings, signing verification certificate, validity/cache.
7. **Chạy validator thật**: xem Spring/OpenSAML authentication failure category, không suy signature pass từ XML parser.
8. **Kiểm tra state**: session cookie/SameSite, stored AuthnRequest, InResponseTo, Load Balancer/Redis, clock skew.
9. **Khoanh vùng sửa cấu hình**: URI/proxy/certificate rollover/NameIDPolicy/AuthnContext hoặc trust policy; không tắt crypto validation.
10. **Test hồi quy** với valid/invalid SAML fixtures (D01–D52), kiểm tra local account/tenant authorization.
11. **Khôi phục cấu hình log** về mức an toàn, redact/delete raw traces, rotate credentials nếu đã vô tình bị lộ.
12. **Ghi biên bản**: root cause, impacts, verified fix, owner, rollout/rollback, follow-up tests.

### 15.1. Mẫu báo cáo đã lược bỏ thông tin nhạy cảm

~~~text
scenario=SAML_SP_INITIATED_REDIRECT_POST
registration=lab
binding_request=HTTP-Redirect
binding_response=HTTP-POST
sp_entity_id_match=PASS
idp_issuer_match=PASS
acs_destination_match=FAIL
audience_match=PASS
in_response_to_match=PASS
signature_validation=NOT_EVALUATED_BY_INSPECTOR
provider_validation=FAIL_DESTINATION
raw_payload_shared=false
action=FIX_TRUSTED_PUBLIC_BASE_URL_AND_UPDATE_IDP_ACS
~~~

Không kết luận `signature_validation=PASS` từ việc `ds:Signature` có trong XML hay metadata chứa cert. Nếu chỉ mới parse, phải ghi `NOT_EVALUATED`.

### 15.2. Metrics và observability

Các metric đề xuất (**không** mặc định do Spring tự sinh):

~~~text
saml_authnrequest_created_total{registration,binding}
saml_authnrequest_failed_total{registration,reason_class}
saml_response_received_total{registration,binding}
saml_response_validation_failed_total{registration,reason_class}
saml_response_authenticated_total{registration}
saml_request_correlation_failed_total{registration}
saml_metadata_refresh_total{registration,result}
saml_metadata_key_rollover_total{registration,result}
saml_assertion_decryption_failed_total{registration}
saml_replay_rejected_total{registration}
~~~

Labels không chứa user name, NameID, email, SAMLResponse ID raw, session IDs, cookies, X509Certificate hoặc RelayState; tránh PII và high cardinality. Dùng test correlation ID opaque và logs có truy cập kiểm soát.

## 16. Những hiểu lầm cần loại bỏ

| Quan niệm sai | Lý do sai | Sửa |
| --- | --- | --- |
| “SAMLRequest Base64 luôn decode ra XML.” | Redirect binding còn raw DEFLATE. | Phát hiện binding trước decode. |
| “POST SAMLResponse cũng DEFLATE.” | POST binding thông thường Base64 XML trực tiếp. | Form-decode → Base64 → XML. |
| “Thấy Signature means login an toàn.” | Chưa verify crypto/trust/Conditions. | Dùng provider thật. |
| “Không có ds:Signature ở AuthnRequest Redirect là unsigned.” | Có thể có `SigAlg/Signature` trong URL query. | Kiểm tra query signature theo spec. |
| “Metadata có certificate nên tin được.” | Metadata có thể giả mạo, key chưa trust. | Trusted source/signature/pinning. |
| “validUntil metadata là hạn của cert.” | Metadata và X.509 là hai thời hạn khác nhau. | Theo dõi riêng. |
| “Issuer là URL IdP SSO endpoint.” | IdP entityID có thể khác SSO URL. | So với metadata entityID. |
| “Audience là ACS URL.” | Audience thường là SP entityID, khác Recipient/ACS. | So đúng trường. |
| “Response Destination đúng là đủ.” | Assertion Audience/Recipient/signature/time vẫn có thể sai. | Validate toàn bộ. |
| “Unsolicited Response không cần security.” | Thiếu request correlation tăng rủi ro replay/mix-up. | Policy riêng với strict checks. |
| “Có EncryptedAssertion thì browser decoder phải đọc được.” | Cần private decrypt key SP. | Dùng SP test key trong sandbox. |
| “SAMLart chính là SAMLResponse Base64.” | Artifact là reference, không phải XML. | Kiểm tra SOAP Artifact Resolution. |
| “NameID=email nên local user trùng email.” | Email có thể đổi/reassign, cross-IdP collision. | Trusted scoped account linking. |
| “MockMvc auth fixture pass => signed Response pass.” | Fixture bypass ACS signature validation. | Signed fixture integration test. |
| “Debug thì tắt signature validation.” | Bỏ trust boundary, che lỗi thực. | Fix key/metadata/clock/ACS. |
| “Cứ log raw SAMLResponse rồi xóa sau.” | Dễ lộ PII/credentials và backup retention. | Minimal/redacted evidence. |

## 17. Checklist trước khi kết luận QA

- [ ] Dùng user và IdP staging/test, không thu dữ liệu nhạy cảm production.
- [ ] Biết rõ SP-initiated/IdP-initiated và HTTP-Redirect/POST/Artifact binding.
- [ ] Lưu raw query encoded chỉ khi thật cần signature debug, dưới secure test storage.
- [ ] HTTP-Redirect: URL-decode một lần → Base64 → raw DEFLATE; không gzip/zlib wrapper.
- [ ] HTTP-POST: form-decode một lần → Base64 XML; không inflate.
- [ ] HTTP-Artifact: hiểu SAMLart cần SOAP back-channel resolution.
- [ ] XML parser chặn DTD/external entities/XXE và có input/decompression limits.
- [ ] Phân biệt signed Redirect query với XML `ds:Signature`.
- [ ] Không tuyên bố signature pass khi chỉ có `Signature` parameter hoặc XML element.
- [ ] `AuthnRequest Issuer`, Destination, ACS, RequestedAuthnContext và ID được đối chiếu.
- [ ] `Response Status`, Issuer, InResponseTo, Destination được đối chiếu.
- [ ] `Assertion Audience`, Conditions, SubjectConfirmation Recipient/InResponseTo/expiry và signature được provider verify.
- [ ] IdP metadata entityID, SSO Location/Binding, KeyDescriptors, validUntil được kiểm tra.
- [ ] SP metadata entityID, ACS public HTTPS, signing/encryption roles và bindings khớp.
- [ ] Metadata trust source/signature/pinning và rollover policies được xác minh.
- [ ] SAML XML signature verification dùng trusted IdP public keys; không trust KeyInfo chưa xác minh.
- [ ] Không bỏ InResponseTo/replay/clock skew limits vì test đang fail.
- [ ] Phân biệt metadata expiry/X.509 expiry/assertion time Conditions.
- [ ] EncryptedAssertion được decrypt chỉ bằng private key SP đã được quản trị trong sandbox.
- [ ] Spring Security SAML filter chain đúng endpoints, đúng RP registration/cert và session state.
- [ ] Local account/roles/tenant tiếp tục được kiểm tra sau authentication.
- [ ] Test D01–D52 hoặc equivalent coverage gồm nhiều negative crypto/protocol cases.
- [ ] Logs/HAR/fixtures được redacted, TTL giới hạn, không upload online decoder.
- [ ] Sau debug đã tắt verbose logging và bảo toàn security controls.

## Ghi nhớ

> **Đọc SAML là công việc quan sát, không phải xác thực.** Với **HTTP-Redirect**, giải mã `SAMLRequest` bằng **URL decode → Base64 → raw DEFLATE**; với **HTTP-POST**, giải mã `SAMLResponse` bằng **form decode → Base64 XML**. Sau đó đối chiếu **Request/Response/Assertion với IdP/SP metadata**, nhưng kết luận login an toàn phải dựa trên **signature/trust validation, time, issuer/audience/recipient, InResponseTo/replay và local authorization** do Spring Security/OpenSAML thực hiện. Chỉ dùng test data và không phát tán SAML payload chứa định danh cá nhân.

### Tài liệu tham khảo chính thức

- [OASIS — SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect raw DEFLATE, Base64, URL encoding, SigAlg/Signature, POST và Artifact.
- [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AuthnRequest, Response, Assertion, Conditions, NameID, SubjectConfirmation, Audience.
- [OASIS — SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityDescriptor/IDPSSODescriptor/SPSSODescriptor/KeyDescriptor/validUntil.
- [OASIS — SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, unsolicited/IdP-initiated, SubjectConfirmation.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/RP, AuthnRequest filter, ACS filter, provider validation, RP registration.
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): initiate endpoint, encoded Redirect request và request repository.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): Saml2Authentication, principal/attributes, response processing.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `saml2Metadata` DSL, metadata endpoints, RP registration.
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): SecurityFilterChain/FilterChainProxy ordering.
- [RFC 1951 — DEFLATE Compressed Data Format](https://www.rfc-editor.org/rfc/rfc1951.html): raw DEFLATE data model.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): secure JAXP parser configuration.
- [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature wrapping, issuer/trust, replay, validation.
