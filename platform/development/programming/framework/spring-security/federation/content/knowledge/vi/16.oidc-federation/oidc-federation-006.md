# So sánh AuthnContext của SAML với acr, amr và yêu cầu xác thực lại trong OIDC

> **Chủ đề:** Spring Security – federation. **Nhóm:** OIDC và môi giới. Bài Knowledge này đối chiếu cách SAML 2.0 mô tả/yêu cầu **ngữ cảnh xác thực** qua `AuthnContext`, `RequestedAuthnContext` và `ForceAuthn` với các claim và tham số OIDC như `acr`, `amr`, `auth_time`, `acr_values`, `max_age` và `prompt=login`. Trọng tâm là cách một Relying Party (RP)/Service Provider (SP) hoặc **identity broker** đưa ra quyết định step-up an toàn, không chỉ dựa vào tên claim.

## 1. Đặt bài toán đúng: xác thực thành công không luôn đủ cho giao dịch nhạy cảm

Một ứng dụng Spring Security cho phép nhân viên đăng nhập qua IdP bằng SAML hoặc OIDC. Khi user chỉ mở trang thông tin, đăng nhập SSO thông thường có thể đủ. Nhưng khi user phê duyệt chuyển khoản, đổi quyền quản trị, tải hồ sơ nhạy cảm hoặc quản lý khóa, tổ chức có thể yêu cầu:

- **Mức bảo đảm xác thực (authentication assurance)** cụ thể, ví dụ chính sách đã phê duyệt về MFA hoặc phương thức chống phishing.
- **Lần xác thực đủ mới**, chẳng hạn được thực hiện trong vòng năm phút gần nhất.
- **Nguồn xác thực được phép** cho nghiệp vụ/tenant đó; không phải IdP bất kỳ có chữ ký hợp lệ.
- **Đúng chủ thể và phiên giao dịch**, chống login CSRF, assertion/token replay và thay account giữa các bước.
- **Quyền nghiệp vụ** tương ứng sau khi đã thỏa assurance, ví dụ membership/role/approval của chính tenant.

Vấn đề: SAML và OIDC dùng **ngôn ngữ khác nhau** để đưa ra hoặc yêu cầu bằng chứng. Một SAML `AuthnContextClassRef` không tự bằng một OIDC `acr`; OIDC `amr=["pwd","otp"]` chưa chứng minh đạt mọi chính sách mà ứng dụng gọi là “MFA”. Cả hai cũng cần tách **mức xác thực** khỏi **độ mới của lần xác thực**.

**Nguyên tắc an toàn:** Đầu tiên xác minh toàn bộ SAML assertion hoặc OIDC ID Token, sau đó kiểm tra chính sách assurance riêng theo **issuer + RP/SP + tenant + nghiệp vụ + thời gian**. Không tạo `ROLE_ADMIN`, không mở giao dịch nhạy cảm và không coi claim chưa kiểm chứng là đủ chỉ vì chuỗi chứa `mfa`, `high` hay `2fa`.

## 2. Phân biệt bốn khái niệm

| Khái niệm | Câu hỏi | SAML 2.0 thường dùng | OIDC thường dùng |
| --- | --- | --- | --- |
| **Authentication method** | Người dùng xác thực bằng phương thức nào? | AuthnContext có thể mô tả class/declaration; đôi khi IdP có attributes riêng | `amr` là danh sách tham chiếu phương thức, ví dụ `pwd`, `otp`, `mfa` |
| **Authentication assurance/context class** | Kết quả xác thực đáp ứng lớp/ngữ cảnh nào theo chính sách IdP? | `AuthnStatement/AuthnContext/AuthnContextClassRef` hoặc `AuthnContextDeclRef` | `acr` trong ID Token; ý nghĩa do profile/OP hoặc hợp đồng federation xác định |
| **Fresh authentication** | Lần xác thực của người dùng diễn ra khi nào và có đủ mới? | `AuthnStatement/@AuthnInstant`; yêu cầu xác thực mới bằng `AuthnRequest/@ForceAuthn` | `auth_time`, `max_age`, `prompt=login` |
| **Session reuse** | Có được dùng SSO session hiện tại không? | IdP xử lý `ForceAuthn`/`IsPassive` trong `AuthnRequest` | OP xử lý `prompt`, `max_age`, session policy |

**Ví dụ:** User đăng nhập bằng mật khẩu + OTP vào 08:00, đến 15:00 vẫn còn SSO session. IdP có thể tiếp tục đưa ra mức assurance thể hiện MFA đã thực hiện, nhưng **lần xác thực cách đó bảy tiếng** có thể không đạt yêu cầu “tươi trong 5 phút” cho một lệnh chuyển tiền. **Mức** và **độ mới** là hai điều kiện độc lập; session app còn hoạt động không thay thế chúng.

### 2.1. Không nhầm authentication assurance với authorization

- Một OIDC ID Token có `acr=high` không tự cấp `ROLE_ADMIN`.
- Một SAML Assertion có `AuthnContextClassRef` đạt yêu cầu không tự cấp quyền xem dữ liệu của tenant khác.
- Một IdP phát `amr=mfa` không thay thế kiểm tra đối tượng thanh toán, hạn mức, separation of duties hoặc step-up cho hành động cụ thể.
- Authentication strength là đầu vào của **policy decision**; authorization vẫn yêu cầu user, tenant, permission, action, resource, mức rủi ro, thời gian và trạng thái tài khoản.

## 3. SAML: `AuthnContext` nằm trong `AuthnStatement` của Assertion

Trong SAML 2.0, IdP có thể gửi thông tin xác thực trong `AuthnStatement`, bên trong chứa `AuthnContext`. Ví dụ XML rút gọn, **không phải Assertion đầy đủ để đăng nhập**:

```xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2030-04-05T09:55:00Z"
    SessionIndex="_session-123">
  <saml:AuthnContext>
    <saml:AuthnContextClassRef>
      urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken
    </saml:AuthnContextClassRef>
  </saml:AuthnContext>
</saml:AuthnStatement>
```

Các trường:

- **`AuthnInstant`:** thời điểm IdP xác thực người dùng, không phải lúc SP nhận assertion; không tự đồng nghĩa `IssueInstant` của SAML Response/Assertion.
- **`SessionIndex`:** tham chiếu phiên xác thực tại IdP, thường phục vụ SAML Single Logout, **không phải** `JSESSIONID` hoặc ID phiên web của SP.
- **`AuthnContextClassRef`:** URI định danh một **authentication context class**; giá trị là **lớp/phân loại**, không phải danh sách các bước xác thực chi tiết.
- **`AuthnContextDeclRef` / `AuthnContextDecl`:** có thể tham chiếu/mô tả cách xác thực cụ thể theo profile/hợp đồng, khác ClassRef; nhiều ứng dụng chỉ xử lý ClassRef nên phải xác nhận với IdP.
- **`Conditions`, `SubjectConfirmationData`, `AudienceRestriction`:** là ràng buộc khác về hiệu lực/đối tượng nhận; không được đánh đồng với thời điểm hoặc mức xác thực.

Ví dụ `TimeSyncToken` chỉ cho biết lớp được IdP khẳng định theo ngữ nghĩa class đó. **Không tự suy ra** lớp này có thể đạt mọi yêu cầu “MFA”, “phishing-resistant” hoặc “NIST AAL2” của ứng dụng. Các lớp SAML tiêu chuẩn có từ vựng kỹ thuật, còn **độ mạnh trong chính sách tổ chức phải được thỏa thuận và xác minh**.

### 3.1. Chỉ đọc AuthnContext sau khi assertion đã được kiểm chứng

Trình tự SP:

1. Resolve đúng `RelyingPartyRegistration` và IdP issuer đã tin.
2. Xác minh chữ ký bảo vệ đúng SAML Assertion/Response được dùng, tránh XML signature wrapping.
3. Kiểm `AudienceRestriction` = SP entityID, `Recipient`/`Destination` = ACS, `InResponseTo`, thời gian và replay theo profile.
4. Lấy `AuthnStatement/AuthnContext` và `AuthnInstant` **từ assertion đã xác minh**, ràng buộc với subject hiện tại.
5. Map class/declaration theo chính sách IdP cụ thể; kiểm tra assurance level và freshness mà nghiệp vụ yêu cầu.
6. Khi không đạt, **từ chối hành động nhạy cảm** và bắt đầu một flow step-up/reauth mới nếu IdP hỗ trợ.

Nếu IDP phát assertion ký hợp lệ nhưng `AuthnContextClassRef` không được phép cho giao dịch, có thể người dùng vẫn được đăng nhập vào ứng dụng theo chính sách thấp hơn, nhưng **không được thực hiện giao dịch bảo vệ mức cao**. Việc chặn ngay toàn bộ login hay chỉ chặn một action phụ thuộc thiết kế, nhưng không được coi authentication = authorization.

### 3.2. Một AuthnStatement không tự là lời cam kết “vừa xác thực”

Nhiều IdP có thể phát SAMLResponse mới dựa trên một SSO session cũ. Khi đó:

```text
Assertion IssueInstant: 2030-04-05T10:01:00Z
AuthnStatement AuthnInstant: 2030-04-05T08:00:00Z
App time now:              2030-04-05T10:01:10Z
```

SAMLResponse vừa phát **không chứng minh user vừa nhập mật khẩu/MFA**. Với nghiệp vụ yêu cầu fresh authentication trong 5 phút, `AuthnInstant` cách 121 phút là không đạt, dù assertion chưa hết hạn và chữ ký hợp lệ.

Thời điểm IdP xác thực có thể liên quan một session multi-factor/chained authentication phức tạp. Cần hỏi IdP: giá trị `AuthnInstant` thay đổi sau step-up hay giữ thời gian xác thực ban đầu? Nếu IdP không cam kết chính xác theo contract, không dùng nó một cách máy móc cho chính sách nhạy cảm.

## 4. SAML: cách SP **yêu cầu** authentication context trong AuthnRequest

SAML `AuthnRequest` có thể chứa:

- **`ForceAuthn`:** yêu cầu IdP trực tiếp xác thực lại presenter thay vì đơn thuần dựa trên một phiên xác thực trước đó, theo định nghĩa giao thức và chính sách IdP.
- **`IsPassive`:** yêu cầu IdP không tương tác trực tiếp với user. Nếu không thể đáp ứng, IdP trả lỗi thích hợp.
- **`RequestedAuthnContext`:** chứa một hoặc nhiều `AuthnContextClassRef` **hoặc** `AuthnContextDeclRef` cùng thuộc tính `Comparison`.
- **`RequestedAuthnContext/@Comparison`:** cách so sánh giá trị ngữ cảnh mà IdP có thể thỏa mãn.
- **`NameIDPolicy`, `Scoping`, `AssertionConsumerServiceURL`, `Issuer`:** các điều kiện protocol khác, không thay thế assurance.

Ví dụ fragment:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-stepup-42"
    Version="2.0"
    IssueInstant="2030-04-05T10:00:00Z"
    Destination="https://idp.partner.example/saml/sso"
    ForceAuthn="true"
    IsPassive="false">
  <saml:Issuer>https://app.example.org/saml2/service-provider-metadata/partner</saml:Issuer>
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef>
      urn:example:contract:partner:strong-v1
    </saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
```

Đây **chỉ là fragment minh họa**; ID/date/URI/certificate phải lấy từ flow thật, có thể cần ký AuthnRequest, và không dùng đoạn trên như test vector hợp lệ. URI `urn:example:contract:partner:strong-v1` là giá trị **giả định do một hợp đồng tích hợp riêng định nghĩa**, không phải SAML class chuẩn hay chứng cứ tự phát rằng đã MFA.

### 4.1. Ý nghĩa của `Comparison`

| Giá trị | Cách hiểu trong SAML | Lưu ý |
| --- | --- | --- |
| `exact` | Kết quả phải đúng một class/declaration được yêu cầu; đây là mặc định khi không khai báo | Phù hợp khi IdP yêu cầu exact URI; không tự chấp nhận URI “gần giống” |
| `minimum` | IdP có thể chọn ngữ cảnh được xem ít nhất mạnh bằng yêu cầu, **theo thứ tự/đánh giá của IdP** | Chỉ an toàn khi hai bên đã thống nhất cách IdP phân cấp các ngữ cảnh |
| `better` | IdP phải chọn ngữ cảnh được xem mạnh hơn, không chỉ bằng | “Mạnh hơn” không có thứ tự toàn cục giữa mọi class |
| `maximum` | IdP có thể chọn ngữ cảnh không mạnh hơn ngưỡng theo semantics tiêu chuẩn | Không phù hợp nếu mục tiêu là ép step-up tối thiểu mạnh hơn |

**Không tự tạo một bảng xếp hạng** tất cả URI SAML rồi cho rằng IdP nào cũng hiểu `minimum/better` giống nhau. Mô hình “mạnh hơn” phụ thuộc đánh giá của responder/IdP, và nhiều triển khai hỗ trợ giới hạn. Ví dụ Microsoft Entra có yêu cầu riêng: khi gửi `RequestedAuthnContext`, `Comparison` phải là `exact`; kiểm tra tài liệu **đúng IdP** trước khi yêu cầu `minimum` hoặc `better`.

Trong trường hợp không thể đáp ứng một `RequestedAuthnContext`, IdP theo SAML có thể trả `NoAuthnContext`. SP phải xem đó là **không thỏa yêu cầu**, không chuyển sang cho phép transaction nhạy cảm bằng phiên đang có.

### 4.2. `ForceAuthn=true` không đồng nghĩa “bắt buộc MFA”

`ForceAuthn` yêu cầu **xác thực lại**, nhưng **phương thức** xác thực có thể vẫn là mật khẩu nếu không có ngữ cảnh/assurance policy buộc mức cao hơn. Muốn fresh + high-assurance, cần cả:

1. IdP/SP thỏa thuận mức được phép qua `RequestedAuthnContext` và/hoặc policy tích hợp.
2. `ForceAuthn=true` khi giao dịch cần **tái xác thực thực sự**.
3. Sau response, SP kiểm **AuthnContext đã nhận** và **AuthnInstant còn mới**.
4. Application kiểm **user/tenant/permission và transaction binding**.

Chỉ cài `ForceAuthn=true` mà không kiểm mức xác thực có thể ép user nhập mật khẩu nhưng vẫn không đạt chính sách MFA.

### 4.3. `IsPassive=true` là chế độ không tương tác, không phải reauthentication

`IsPassive=true` yêu cầu IdP không hiển thị UI/tương tác với user. Nó hữu ích với những luồng passive SSO, nhưng **không phải** cách tốt để ép user thực hiện step-up bằng OTP hoặc passkey nếu cần UI. Kết hợp `ForceAuthn=true` và `IsPassive=true` có thể gây yêu cầu khó/không thể thỏa đối với nhiều IdP; thiết kế phải xử lý failure rõ thay vì silent fallback xuống mức thấp.

### 4.4. Luồng SAML step-up minh họa

```text
Browser đang có App Session mức cơ bản
             |
             | POST /payments/{id}/approve
             v
SP policy: high assurance + fresh <= 300 giây?
       | YES                       | NO
       v                           v
   Tiếp tục                Lưu pending transaction
   authorization                và request correlation
                                   |
                                   v
                              AuthnRequest:
                              ForceAuthn=true
                              RequestedAuthnContext exact strong
                                   |
                                   v
                           IdP reauthenticate/step-up
                                   |
                                   v
                           SP validate Response:
                         signature, issuer, audience,
                         recipient, InResponseTo, replay
                                   |
                                   v
                         Check AuthnContext + AuthnInstant
                                   |
                              OK? /  \ FAIL?
                               v        v
                          Bind to     Deny action,
                          same user   do not weaken policy
                               |
                               v
                        Recheck permission, tenant,
                        resource, transaction details
                               |
                               v
                           Approve
```

**Không dùng kết quả “HTTP 302 về app” làm bằng chứng step-up thành công**. Xác nhận phải có full validation và một quyết định policy sau callback; user có thể có session app đang đăng nhập nhưng IdP trả lỗi `NoAuthnContext` hoặc mức khác.

## 5. OIDC: ba claim `acr`, `amr`, `auth_time` không đồng nghĩa nhau

Một ID Token OIDC được OP ký có thể chứa payload dạng rút gọn như:

```json
{
  "iss": "https://op.partner.example/realms/finance",
  "sub": "user-42",
  "aud": "web-portal",
  "iat": 1901613600,
  "exp": 1901613900,
  "acr": "urn:example:contract:finance:high-v1",
  "amr": ["pwd", "otp"],
  "auth_time": 1901613500
}
```

**Đây là payload minh họa**, không phải ID Token đầy đủ và không phải JWT có thể dùng đăng nhập (không có header/chữ ký thật, thời gian chỉ dùng để minh họa). ID Token thực phải được Spring Security/OIDC client validate chữ ký, `iss`, `aud`, `exp`, `nonce`/state và các điều kiện của flow; **chỉ sau đó** mới dùng assurance claims.

### 5.1. `acr` — Authentication Context Class Reference

`acr` là một chuỗi mô tả **authentication context class được OP cho rằng đã thỏa**. Giá trị có thể là URI như `urn:example:contract:finance:high-v1`, chuỗi profile của OP hoặc giá trị do một tiêu chuẩn khác quy định.

- Không có một “acr=2” phổ quát đảm bảo NIST AAL2 cho mọi OP.
- Hai IdP có `acr` cùng chuỗi không tự có chính sách, bằng chứng, enrollment, recovery và chống phishing tương đương.
- Một OP có thể hỗ trợ vài giá trị `acr`, nhưng ý nghĩa/độ mạnh phải xác định trong **hợp đồng với OP/issuer cụ thể**.
- Một application có thể yêu cầu `acr` dưới dạng **Essential Claim** nếu OP hỗ trợ `claims` parameter; nếu chỉ gửi `acr_values` thì đó là yêu cầu **Voluntary** (xem mục 6).
- Khi đã nhận ID Token hợp lệ, RP vẫn phải **kiểm tra `acr`** theo danh sách giá trị đã phê duyệt và mục đích nghiệp vụ; không chỉ tin rằng OP nhận request nên chắc chắn thực thi.

### 5.2. `amr` — Authentication Methods References

`amr` là **mảng các phương thức xác thực** được dùng. RFC 8176/IANA có các giá trị tham chiếu, ví dụ:

| `amr` | Cách hiểu khái quát | Không được suy ra điều gì? |
| --- | --- | --- |
| `pwd` | Xác thực dùng mật khẩu | Không tự có MFA hoặc phishing resistance |
| `otp` | Dùng one-time password | Không tự biết OTP thuộc kênh/yếu tố nào và có phishing-resistant không |
| `mfa` | OP khẳng định có multi-factor authentication | Không tự chứng minh phương thức, độ mới, assurance level hoặc policy của tổ chức |
| `fpt` | Dùng dấu vân tay (fingerprint biometric) | Không tự bảo đảm xác thực đa yếu tố hoặc khóa có hardware attestation |
| `face` | Dùng facial recognition | Không tự là AAL3 hoặc một chứng chỉ chất lượng sinh trắc |
| `hwk` | Proof of possession của hardware-secured key | Không tự chứng minh toàn bộ trải nghiệm phishing-resistant nếu policy đòi thêm nguồn/thuộc tính |
| `swk` | Proof of possession của software-secured key | Không tương đương mặc định phần cứng |
| `sms` | Dùng SMS confirmation | Không bảo đảm chống phishing hoặc an toàn trước chuyển SIM |
| `rba` | Có risk-based authentication | Không có nghĩa user được thử thách MFA thực sự |
| Giá trị vendor-defined | Do OP/broker định nghĩa | Phải có hợp đồng, không tự coi string đó là quyền |

Dữ liệu `amr=["pwd","otp"]` có thể gợi ý hai phương thức tham gia. Nhưng một RP **không thể kết luận chỉ từ cú pháp rằng một MFA cụ thể đã đạt chính sách**: OP phải đáng tin, các phương thức phải được định nghĩa, các yếu tố phải độc lập khi policy yêu cầu, và bước xác thực phải còn đủ mới.

`amr` có thể vắng mặt tùy OP/flow. Khi cần một chính sách cụ thể dựa trên `amr`, nếu mảng không có hoặc có giá trị lạ, **không tự tạo `amr=["mfa"]`**. Áp dụng fail closed hoặc step-up theo policy.

### 5.3. `auth_time` — thời điểm xác thực thực tế

`auth_time` là **NumericDate** — số giây từ Unix epoch UTC — mà OP báo người dùng đã được xác thực. Nó khác:

- `iat`: khi ID Token được phát.
- `exp`: khi ID Token hết hiệu lực để được chấp nhận.
- Thời gian request frontend mới gửi.
- Thời gian server tạo local `HttpSession`.
- Lúc access token được refresh.
- `SAMLResponse/IssueInstant` khi broker phát downstream assertion.

OIDC Core quy định khi **`max_age` được gửi**, ID Token trả về **phải có `auth_time`**. Khi `auth_time` được yêu cầu là Essential Claim, nó cũng bắt buộc. RP phải kiểm tra độ mới so với policy; **ID Token có `exp` trong tương lai không bảo đảm `auth_time` đủ mới**.

Ví dụ:

```text
OP xác thực user lúc:      09:00:00 UTC
RP xin authorization mới: 10:00:00 UTC
OP dùng session SSO cũ:   10:00:02 UTC
ID Token iat:            10:00:03 UTC
ID Token auth_time:      09:00:00 UTC
RP yêu cầu fresh <= 300 giây
=> KHÔNG đạt, dù iat mới và token signature/exp hợp lệ.
```

Một OP có thể thực hiện reauthentication nhưng dùng một quy tắc riêng về mốc `auth_time` khi MFA được nâng; RP cần kiểm thử hành vi thật và thống nhất contract nếu quyết định phụ thuộc vào mốc này.

## 6. OIDC: các tham số **yêu cầu** xác thực khác nhau

### 6.1. `acr_values` — đề xuất lớp xác thực theo thứ tự ưu tiên

Ví dụ authorization request (URL được rút gọn):

```text
GET /authorize?
  response_type=code
  &client_id=web-portal
  &scope=openid
  &state=<opaque-correlation>
  &nonce=<opaque-nonce>
  &acr_values=urn%3Aexample%3Acontract%3Afinance%3Ahigh-v1
```

Trong request thực, URL phải được encode đúng và do OAuth2/OIDC client framework dựng; các giá trị state/nonce được sinh ngẫu nhiên và bảo vệ. `acr_values` là các chuỗi **cách nhau bằng dấu cách theo thứ tự ưu tiên** mà RP muốn OP sử dụng. Theo OIDC Core, tham số này yêu cầu `acr` dạng **Voluntary Claim**: OP có thể không trả đúng mức hoặc không trả `acr` theo cách RP mong muốn, tùy khả năng/profile. **Bắt buộc kiểm tra giá trị `acr` trong ID Token nhận về**; không dựa vào việc đã gửi `acr_values` để cấp phép.

Khi môi trường yêu cầu đảm bảo không được giảm cấp, hãy dùng chính sách OP/client phù hợp hoặc `claims` parameter với `acr` là Essential Claim và giá trị cụ thể theo OIDC, rồi vẫn kiểm chứng response. Không trộn lẫn hai phương thức yêu cầu `acr` mà không hiểu semantics.

### 6.2. `claims` parameter và Essential `acr`

Ví dụ JSON **giá trị của tham số `claims`** trong OIDC, cần URL-encode khi truyền:

```json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:contract:finance:high-v1"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
```

Theo OIDC Core, khi OP hỗ trợ `claims` parameter và RP yêu cầu Essential `acr` với danh sách giá trị, OP phải trả một `acr` khớp hoặc coi không đạt yêu cầu là failed authentication. **Điều đó không tự biến các chuỗi vendor-specific thành mức đảm bảo chuẩn**; RP phải kiểm tra issuer, token, `acr` và thời gian khi nhận. Không giả định mọi OP thực thi `claims` parameter đầy đủ; kiểm tra discovery và tích hợp với nhà cung cấp thật.

**Lưu ý giao thức:** Nếu vừa gửi `acr_values` vừa gửi `claims.id_token.acr` có các giá trị cụ thể, hành vi kết hợp trong OIDC Core có phần **không được quy định rõ**. Ưu tiên một cơ chế nhất quán theo hợp đồng với OP, kiểm thử trước production.

### 6.3. `prompt=login` — yêu cầu OP xác thực lại

`prompt=login` báo OP yêu cầu **tái xác thực user**, kể cả browser có SSO cookie. OP phải xử lý theo OIDC Core; nếu không thể reauthenticate, trả lỗi phù hợp. Tuy nhiên:

- Nó **không tự yêu cầu MFA**; có thể chỉ yêu cầu nhập mật khẩu hoặc một phương thức theo policy OP.
- Nó **không tự đảm bảo** RP kiểm được freshness nếu không có `auth_time` hoặc nguồn xác minh phù hợp.
- Một OP/broker có thể có cách diễn giải reauthentication khi ở phía trước một upstream IdP khác; cần kiểm thử xem upstream có thật sự bị yêu cầu auth mới hay broker chỉ reauthenticate user với phương thức khác.
- Một giá trị `prompt=login` từ query của client chưa xác minh không phải bằng chứng bảo mật; điều quan trọng là request do RP khởi tạo và ID Token được RP kiểm sau flow.

### 6.4. `max_age` — ràng buộc độ tuổi xác thực

`max_age=300` yêu cầu OP chỉ coi lần xác thực có tuổi tối đa **300 giây** là phù hợp; nếu quá, OP phải thử active reauthentication. Khi có `max_age`, response ID Token **phải chứa `auth_time`**. `max_age=0` có hiệu lực yêu cầu xác thực mới tương đương `prompt=login` theo đặc tả OIDC Core.

Ví dụ:

```text
max_age=300
OP auth_time = 10:00:00Z
RP nhận ID Token lúc 10:04:59Z
=> Freshness 299 giây: đạt policy nếu các điều kiện khác đạt

OP auth_time = 10:00:00Z
RP nhận ID Token lúc 10:05:01Z
=> 301 giây: quá hạn; phải từ chối action hoặc yêu cầu reauth
```

Khoảng dung sai đồng hồ phải nhỏ và có chính sách. Không dùng `iat` thay `auth_time`, không tự tăng `max_age` đến vài tiếng chỉ để che lỗi step-up. Trong các hệ thống nhiều hop broker, cần biết `auth_time` là thời gian broker xác thực user hay thời gian upstream IdP xác thực user; quy tắc ấy phải nằm trong contract.

### 6.5. `prompt=none` không phải cách ép MFA

`prompt=none` yêu cầu **không hiển thị UI**. Nếu user chưa có phiên phù hợp, consent/assurance không đáp ứng hoặc không thể auth im lặng, OP trả lỗi như `login_required` hoặc `interaction_required`. Không dùng `prompt=none` để thay `prompt=login`/`max_age` khi giao dịch cần người dùng tương tác lại.

### 6.6. `prompt=select_account` cũng không phải reauthentication

`prompt=select_account` yêu cầu lựa chọn account khi OP có thể; việc chọn account **không chứng minh user đã nhập lại mật khẩu hoặc hoàn thành MFA**. Với giao dịch giá trị cao, kiểm `sub` của account sau callback khớp account ban đầu, kiểm freshness và assurance theo policy.

## 7. Bảng đối chiếu trọng tâm: SAML so với OIDC

| Ý định | Cơ chế SAML 2.0 | Cơ chế OIDC | Giới hạn khi suy tương đương |
| --- | --- | --- | --- |
| **SP/RP yêu cầu ngữ cảnh** | `RequestedAuthnContext` với ClassRef/DeclRef | `acr_values` hoặc Essential `acr` trong `claims` | Giá trị và enforcement không có namespace/mức mạnh chung |
| **IdP/OP khai báo ngữ cảnh đã đạt** | `AuthnStatement/AuthnContextClassRef` | `acr` trong ID Token | Chỉ map theo hợp đồng issuer, không so tên |
| **Thông tin phương thức** | Lớp/declaration/attribute tùy IdP | `amr` list, ví dụ `pwd`, `otp` | Một class SAML không tự ánh xạ ra các AMR phương thức |
| **Thời điểm xác thực user** | `AuthnStatement/@AuthnInstant` | `auth_time` | Thời gian thuộc issuer/flow nào phải được xác định |
| **Yêu cầu active reauthentication** | `AuthnRequest ForceAuthn="true"` | `prompt=login` hoặc `max_age=0` | Không tự yêu cầu phương thức mạnh hơn |
| **Giới hạn tuổi xác thực** | Không có đối ứng chuẩn giống hệt `max_age` trong mọi SAML AuthnRequest; SP có thể dùng ForceAuthn và kiểm AuthnInstant | `max_age=N` và kiểm `auth_time` | Không thay bằng `IssueInstant`/`iat` |
| **Không được tương tác user** | `IsPassive="true"` | `prompt=none` | Cơ chế khác, lỗi/khả năng IdP khác |
| **Báo không đáp ứng assurance** | `NoAuthnContext` hoặc status lỗi theo SAML | OIDC error hoặc `acr` không đạt/thiếu (khi request voluntary) | Fail closed, không silent downgrade |
| **Đồng bộ/session** | `SessionIndex` / SAML SLO, SP HttpSession | OP `sid` và logout specs, RP HttpSession | Session ID không phải bằng chứng assurance |
| **Dữ liệu đã ký/được tin** | SAML Response/Assertion có chữ ký, issuer, audience, ACS, correlation | ID Token JWT có chữ ký, `iss/aud/nonce`, exp, state | Cần validation đầy đủ trước khi đọc claims |
| **Step-up ở broker** | Broker làm SP với upstream SAML; kiểm AuthnContext rồi map | Broker làm OP downstream; ký ID Token `acr/amr/auth_time` | **Không** suy mức cao chỉ từ login thành công |

**Không có chuyển đổi tự động đúng trong mọi trường hợp** kiểu `SAML AuthnContextClassRef = acr` hoặc `ForceAuthn = max_age=300`. Một broker có thể chủ động xây mapping có kiểm soát, nhưng chính broker chịu trách nhiệm trước RP về chất lượng chứng cứ và mức rủi ro.

### 7.1. Ví dụ hai phép so sánh sai

Sai:

```text
SAML AuthnContextClassRef =
  urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
=> OIDC amr=["mfa"]           // KHÔNG có cơ sở tự động

OIDC acr="2"
=> SAML AuthnContextClassRef="urn:...:TimeSyncToken"
=> đạt phishing-resistant MFA  // KHÔNG có cơ sở tự động
```

Đúng là:

```text
(issuer đã xác minh, class/method, thời gian, policyVersion, audience)
           |
           v
bảng assurance mapping có owner + contract + test/certification
           |
           v
mức nội bộ: BASIC / CONTRACT_STRONG
           |
           v
thẩm định action/tenant, freshness, risk, step-up
```

Không dùng các ví dụ URI class trong bài để khẳng định chuẩn assurance cụ thể của IdP thật.

## 8. Kiến trúc broker: SAML upstream → OIDC downstream

Trong môi giới danh tính, broker có thể đồng thời đóng hai vai trò:

```text
Browser        Upstream SAML IdP       Identity Broker (SAML SP + OIDC OP)       Downstream OIDC RP
   |                  |                            |                                    |
   | -- login to RP ------------------------------------------------------------->|
   |                  |                            |<--- authorize/acr_values/max_age -|
   |<------------------------------ redirect broker -----------------------------|
   |                  |<---- SAML AuthnRequest ------|                             |
   |                  |      ForceAuthn / context    |                             |
   |<---- authenticate / step-up at upstream -------|                             |
   |-------------------- SAMLResponse ------------->|                             |
   |                  |    broker validates assertion:
   |                  |    issuer, signing key,
   |                  |    audience, recipient, time,
   |                  |    InResponseTo, AuthnContext
   |                  |                            |
   |                  |                       policy mapping:
   |                  |                       SAML context + AuthnInstant
   |                  |                       -> allowed downstream acr/auth_time
   |                  |                            |
   |<--------------------------------------------- | ---- code response ---------->|
   |                  |                            |<- token request ------------|
   |                  |                            |-- signed ID Token ---------->|
   |                  |                            |   acr/amr/auth_time           |
   |                  |                            |                         RP verifies
   |                  |                            |                         issuer,aud,acr,time
```

**Một broker phát ID Token dưới issuer của chính broker**, ví dụ `https://broker.example.org`. Downstream RP không trực tiếp tin public key của upstream SAML IdP; nó tin broker theo quan hệ OIDC. Do vậy broker phải **chứng minh và chịu trách nhiệm** rằng `acr` nó phát thực sự có nguồn từ một SAML authentication context hợp lệ trong phạm vi chính sách.

### 8.1. Dữ liệu provenance nên được giữ nội bộ

Bản ghi minh họa:

```text
VerifiedUpstreamEvidence:
  protocol: SAML2
  upstreamIdpEntityId: https://idp.partner.example/entity
  upstreamSubjectKey: qualified persistent NameID
  upstreamSpEntityId: broker SAML SP entityID
  classRef: urn:example:contract:partner:strong-v1
  authenticationInstant: 2030-04-05T10:00:00Z
  assertionId: _assertion123
  inResponseTo: _request-456
  validationSucceeded: true
  trustedSigningCredentialVersion: cert-v4

BrokerPolicyDecision:
  policyVersion: assurance-map-v7
  downstreamClientId: web-portal
  requiredAssurance: FINANCE_STEP_UP
  mappedAcr: urn:example:broker:finance-high-v1
  mappedAmr: (only if independently justified by contract)
  mappedAuthTime: upstream authenticationInstant (only if semantically valid)
  decision: ALLOW

Downstream ID Token:
  iss: https://broker.example.org
  aud: web-portal
  sub: stable pairwise subject for downstream RP
  acr: urn:example:broker:finance-high-v1
  auth_time: ...
```

**Không copy nguyên upstream `NameID`, certificate hoặc user attributes nhạy cảm vào downstream token** nếu không cần. Mỗi RP phải có subject mapping ổn định, đúng audience và consent/privacy policy. `auth_time` phải phản ánh thời điểm **xác thực người dùng** theo contract, không phải timestamp khi broker phát ID Token.

### 8.2. Mapping phải là allowlist có phiên bản

Ví dụ **hợp đồng nội bộ giả định**:

| Upstream issuer đã kiểm chứng | Giá trị SAML được xác nhận | Downstream `acr` có thể phát | Điều kiện bổ sung |
| --- | --- | --- | --- |
| `https://idp.partner.example/entity` | `urn:example:contract:partner:strong-v1` | `urn:example:broker:finance-high-v1` | AuthnInstant đủ mới, verified assertion, policy v7 |
| Cùng IdP | `urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport` | `urn:example:broker:basic-v1` | Không tự phát `amr=mfa` |
| IdP thứ hai đã phê duyệt | Class URI được chứng minh theo contract của IdP thứ hai | Mapping riêng của IdP thứ hai | Cần review policy riêng |
| IdP lạ | Mọi URI/định danh | **Không ánh xạ, từ chối** | Không tự lập nguồn |
| Upstream thiếu AuthnContext | Missing | **Không tự map high** | Chỉ dùng chính sách fallback đã đánh giá |

**Bắt buộc có provenance:** Lưu issuer, protocol, registration, key/trust version, context, AuthnInstant, mappingVersion, policyVersion và downstream audience, rồi giới hạn lifetime. Nếu broker chỉ biết một SAMLResponse đã được ký mà không biết class được xác minh, không được phát downstream `acr=high` để “tương thích”.

### 8.3. Không làm giả `amr` khi upstream không nói phương thức cụ thể

Nếu SAML IdP chỉ khẳng định class “strong” nhưng **không mô tả rõ các phương thức cụ thể**, broker có thể được phép phát một `acr` downstream theo hợp đồng đã đánh giá, nhưng **không được tự tạo `amr=["pwd","otp"]`** nếu không có bằng chứng password + OTP thực sự được dùng. Cần tách:

- `acr`: mức/ngữ cảnh đã đạt theo chính sách trusted issuer.
- `amr`: danh sách phương thức **thực tế được khẳng định có căn cứ**.
- `auth_time`: mốc xác thực user theo chính sách tin cậy.
- `iat`: thời điểm broker phát token, không thể thay `auth_time`.

**Cảnh báo:** Một số bên có thể đưa `acr`/`amr` như custom SAML attributes; chúng vẫn phải có issuer, semantics và chữ ký đã kiểm chứng. Chuỗi `acr` xuất hiện trong bất kỳ attribute nào của SAML **không** có nghĩa có thể copy thẳng sang OIDC.

### 8.4. Reauthentication qua nhiều hop không có bảo đảm tự động

Khi RP downstream gửi `prompt=login` hoặc `max_age=0` tới broker, broker phải xác định:

- Có tự thực hiện reauthentication ở broker để thỏa contract hay phải yêu cầu upstream IdP làm mới?
- Nếu broker chuyển qua SAML, nó có tạo **AuthnRequest mới với `ForceAuthn=true`** đến upstream, có giữ correlation tới đúng downstream request không?
- IdP upstream có thực sự xác thực lại và phát `AuthnInstant` mới không?
- Broker có kiểm `RequestedAuthnContext`, class trả về, signature và freshness **trước khi** phát ID Token downstream không?
- Nếu upstream trả `NoAuthnContext`/không hỗ trợ ForceAuthn, broker có từ chối theo chính sách hay tự downgrade?
- Khi downstream user đổi account trong khi step-up, broker có chặn việc hoàn thành action của user ban đầu không?

**Không mặc định:** `prompt=login` tại RP → broker = `ForceAuthn=true` ở upstream, trừ khi broker được cấu hình/kiểm thử để thực hiện chính ánh xạ đó.

## 9. Xây Assurance Policy theo nguồn và hành động, không theo chuỗi chung chung

Một bảng chính sách nội bộ có thể là:

| Business action | Mức nội bộ | Freshness | Nguồn được phép | Xử lý khi không đạt |
| --- | --- | --- | --- | --- |
| Đọc trang công khai | ANONYMOUS | Không yêu cầu | Không | Không cần SSO |
| Đọc báo cáo thông thường | BASIC | Theo web session | IdP allowlisted | Login nếu chưa xác thực |
| Xem thông tin cá nhân nhạy cảm | VERIFIED | ≤ 30 phút | IdP hỗ trợ assurance mapping | Step-up nếu thiếu |
| Phê duyệt khoản chi lớn | FINANCE_STEP_UP | ≤ 5 phút | IdP có contract strong class/acr | Reauth + assurance + quyền phê duyệt |
| Đổi phương thức MFA | ACCOUNT_RECOVERY_STRONG | Độ mới theo policy rủi ro | IdP/OP được phê duyệt | Reauth đặc biệt, audit và cảnh báo |
| Cấp quyền quản trị | ADMIN_STEP_UP | ≤ 5 phút hoặc chặt hơn | Chính sách enterprise | Step-up, separation of duties, admin approval |

**Mỗi row là một policy decision độc lập.** Một user đạt `FINANCE_STEP_UP` vẫn phải có quyền phê duyệt khoản chi đó và thuộc đúng tenant. Một chứng cứ đạt mức cao cho action A không mặc nhiên được reuse vô hạn cho action B.

### 9.1. Định nghĩa một bản ghi evidence tối thiểu

```text
VerifiedAssurance:
  protocol               = OIDC | SAML2
  sourceIssuer            = verified iss / IdP entityID
  subjectKey              = verified subject
  registrationId          = Spring registration actually used
  contextReference        = verified acr / SAML AuthnContextClassRef
  methodReferences        = verified amr if present (OIDC)
  authenticationInstant   = auth_time / AuthnInstant, if contract supports
  issuedAt                = token/assertion issue time (separate)
  sessionId               = local session reference
  evidenceHashOrId        = server-side audit reference, not raw token
  assurancePolicyVersion  = server-approved version
  evaluatedAt             = current instant UTC
```

**Nguồn phải là dữ liệu đã validate**, không đơn thuần truyền DTO từ browser. Việc RP nhận một JSON `{"acr":"high"}` qua frontend không làm claim đáng tin.

### 9.2. Trình tự ra quyết định step-up

```text
Request business action
     |
     v
Session/local principal có hợp lệ? user/tenant/action được phép?
     |
     v
Assurance evidence còn thuộc đúng user, issuer, registration, session?
     |
     v
ContextRef nằm trong allowlist của source + policyVersion?
     |
     +--- NO ---> STEP_UP_REQUIRED
     |
     v
AuthenticationInstant có mặt và đủ mới?
     |
     +--- NO ---> REAUTHENTICATE
     |
     v
Không có rủi ro bổ sung (tenant, device, amount, policy upgrade)?
     |
     +--- NO ---> stronger step-up / deny
     |
     v
Authorize exact action/resource; consume pending transaction binding
```

Nếu user mới đăng nhập nhưng assurance chưa đủ, yêu cầu **step-up**. Nếu assurance đủ mà authentication time quá cũ, yêu cầu **reauthentication**. Nếu nguồn issuer chưa được phê duyệt, **từ chối** chứ không chỉ lặp vô hạn một login flow.

### 9.3. Tránh vòng lặp step-up vô hạn

Sai:

```text
User -> /approve
 -> redirect login with high acr
 -> OP returns low acr
 -> app redirects to same login again
 -> OP returns low acr
 -> loop vô hạn
```

Đúng: giới hạn số lần thử, ghi lý do không đạt, hiển thị thông báo/đường hỗ trợ và **không mở action**. Nếu OP không hỗ trợ level cao, cần thay đổi hợp đồng IdP hoặc chính sách, không bỏ kiểm tra `acr`/ClassRef. Tách lỗi “không đủ assurance” khỏi lỗi signature, issuer, audience, nonce, csrf hoặc session.

## 10. Spring Security OIDC: yêu cầu `max_age` / `acr_values` khi đăng nhập

Spring Security Servlet có `DefaultOAuth2AuthorizationRequestResolver` và `OAuth2AuthorizationRequest.Builder#additionalParameters` để bổ sung tham số OIDC vào Authorization Request. Đây là extension point chuẩn để thêm `max_age`, `acr_values` hoặc `prompt`.

**Ví dụ minh họa toàn bộ OIDC login dùng cùng yêu cầu**. Nó phù hợp làm phòng lab, **không** phải cách tốt nhất để step-up theo từng business action vì mọi login đều có yêu cầu giống nhau. Trong production cần chọn policy theo route/risk, lưu request context ở server và có cơ chế đảm bảo callback thuộc đúng step-up transaction.

File `src/main/java/com/example/federation/OidcAssuranceLoginConfig.java`:

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcAssuranceLoginConfig {

    @Bean
    SecurityFilterChain oidcWeb(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
            builder.additionalParameters(params -> {
                params.put(
                    "acr_values",
                    "urn:example:contract:finance:high-v1");
                params.put("max_age", "300");
            }));

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oidc -> oidc
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)))
            .build();
    }
}
```

**Điều kiện build:** Class thuộc ứng dụng Spring Boot servlet có Java 17+, Spring Security và `spring-security-oauth2-client`/`spring-boot-starter-oauth2-client`. Cần cấu hình `ClientRegistrationRepository` với issuer-uri, client ID, client secret/PKCE phù hợp, callback HTTPS đã đăng ký và OP thực tế; không phải class Java độc lập chạy bằng `javac` thuần.

Giải thích:

- `resolver` phát Authorization Request khi browser truy cập `GET /oauth2/authorization/{registrationId}`.
- `additionalParameters` giữ các tham số chuẩn do Spring xây dựng và thêm `acr_values` cùng `max_age`; **không tự tạo `state`, `nonce`, `code_challenge` hay `redirect_uri` từ dữ liệu không tin cậy**.
- `max_age=300` yêu cầu OP trả `auth_time`; RP **phải kiểm tra** claim đó trong flow/authorization policy.
- `acr_values` là yêu cầu voluntary; RP vẫn phải xem `acr` thật. URI sample là giá trị hợp đồng **minh họa**, không có ý nghĩa universal.
- Nếu môi trường yêu cầu essential acr, dùng `claims` request parameter theo OIDC Core và OP support; không đồng thời gắn `acr_values` + essential `acr` một cách tùy tiện vì semantics kết hợp không xác định rõ.
- Ví dụ **không tự làm mới Authentication hiện có ở tất cả request**. Nếu user đang có local session và truy cập `/approve`, Spring có thể trả trang trực tiếp mà không round-trip OIDC. Logic step-up phải **chủ động khởi tạo** một OAuth2 authorization flow mới khi yêu cầu, không chỉ cấu hình resolver.
- Khi dùng nhiều ClientRegistration, bổ sung chính sách theo issuer/client trong resolver và policy service; không áp URI “finance-high” lên OP không hỗ trợ.

### 10.1. Thêm `prompt=login` khi cần

Nếu **mọi login** trong một môi trường test phải yêu cầu OP reauthenticate, có thể thêm:

```java
resolver.setAuthorizationRequestCustomizer(builder ->
    builder.additionalParameters(params -> {
        params.put("prompt", "login");
        params.put("max_age", "0");
    }));
```

Đây là **phương án thay thế** cấu hình parameter ở trên, không đặt hai `setAuthorizationRequestCustomizer` để nghĩ rằng chúng tự merge; lời gọi sau có thể thay customizer trước. Với production, chỉ kích hoạt reauthentication khi action cần thiết. `prompt=login`/`max_age=0` **không** tự yêu cầu MFA; nếu transaction cần high assurance phải kiểm tra `acr`/contract riêng.

### 10.2. Kiểm tra claim hiệu lực sau OIDC login

Spring Security có `OidcUser` và `OidcIdToken` để đọc claim đã được framework validate. Interface `IdTokenClaimAccessor` cung cấp:

- `getAuthenticationContextClass()` → `acr`, có thể null.
- `getAuthenticationMethods()` → danh sách `amr`, có thể null.
- `getAuthenticatedAt()` → `auth_time` dưới dạng `Instant`, có thể null.
- `getIssuedAt()` → `iat`, **không** thay `auth_time`.
- `getIssuer()`, `getAudience()`, `getSubject()` → dùng đúng validation/identity context.

**Ví dụ controller chỉ báo kết quả kiểm tra, không tự cấp quyền và không trả claims nhạy cảm**. File `src/main/java/com/example/federation/OidcAssuranceStatusController.java`:

```java
package com.example.federation;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OidcAssuranceStatusController {

    private static final String TRUSTED_ISSUER =
        "https://op.partner.example/realms/finance";
    private static final String REQUIRED_ACR =
        "urn:example:contract:finance:high-v1";

    @GetMapping("/assurance-status")
    public Map<String, Boolean> status(
            @AuthenticationPrincipal OidcUser principal) {
        if (principal == null) {
            return Map.of("meetsExamplePolicy", false);
        }

        var idToken = principal.getIdToken();
        var issuer = idToken.getIssuer();
        String acr = idToken.getAuthenticationContextClass();
        Instant authTime = idToken.getAuthenticatedAt();
        Instant now = Instant.now();

        boolean trustedIssuer = issuer != null
            && TRUSTED_ISSUER.equals(issuer.toString());
        boolean correctAcr = REQUIRED_ACR.equals(acr);
        boolean fresh = authTime != null
            && !authTime.isAfter(now)
            && Duration.between(authTime, now)
                .compareTo(Duration.ofMinutes(5)) <= 0;

        return Map.of(
            "meetsExamplePolicy",
            trustedIssuer && correctAcr && fresh);
    }
}
```

**Lưu ý quan trọng:** Đây là endpoint demo báo boolean và **giả định Spring đã validate ID Token, registration và session**. Nếu có nhiều issuers/clients, cần xác định issuer và policy theo registration hiện tại, không hard-code một issuer cho toàn app. Production phải dùng policy service ở **trước action được bảo vệ**, thay vì để frontend tự quyết định dựa trên boolean của endpoint. Nếu idToken có `auth_time` tương lai do clock skew nhỏ, một chính sách có thể có bounded skew được phê duyệt; demo cố ý strict.

Code demo không kiểm `amr` để tự suy MFA; vì `amr` là nguồn phương thức có semantics phụ thuộc OP, chính sách high assurance ở đây được neo vào `acr` contract đã phê duyệt và freshness. Trong một hệ thống có rủi ro cao, cần verify enrollment, phishing-resistance, session revocation và transaction binding theo policy ngoài hai giá trị này.

**Không cung cấp endpoint `/assurance-status` cho người chưa xác thực** trong production; security chain phải yêu cầu login và không tiết lộ account/session information nếu không cần.

## 11. Spring Security SAML: yêu cầu `ForceAuthn` khi tạo AuthnRequest

Spring Security Servlet tích hợp `Saml2WebSsoAuthenticationRequestFilter`. Khi browser khởi tạo `GET /saml2/authenticate/{registrationId}`, framework có thể dùng `OpenSaml5AuthenticationRequestResolver` (Spring Security 7.x/OpenSAML5) để dựng AuthnRequest. Spring reference đưa ví dụ `setAuthnRequestCustomizer` để đặt `ForceAuthn=true`.

File `src/main/java/com/example/federation/SamlForceAuthnConfig.java` cho **Spring Security 7.x phù hợp OpenSAML 5**:

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml5AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class SamlForceAuthnConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver registrationResolver =
            new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml5AuthenticationRequestResolver resolver =
            new OpenSaml5AuthenticationRequestResolver(
                registrationResolver);

        resolver.setAuthnRequestCustomizer(context ->
            context.getAuthnRequest().setForceAuthn(true));

        return resolver;
    }
}
```

**Giải thích:**

- Resolver sử dụng `RelyingPartyRegistrationRepository` của Spring, phải có IdP metadata, ACS, entityID và signing/verifying credentials **hợp lệ**.
- `setForceAuthn(true)` yêu cầu IdP xác thực lại khi AuthnRequest được gửi. Nó không tự thêm `RequestedAuthnContext` hoặc bảo đảm IdP dùng MFA.
- Sample bật `ForceAuthn` cho **mọi** AuthnRequest do bean này xử lý; chỉ nên làm trong lab hoặc khi policy toàn hệ thống thật sự yêu cầu. Với action-level step-up, tạo request customizer có nguồn policy đáng tin và correlation, **không cho browser tự chọn ForceAuthn**.
- Trong Spring Security 6.x/OpenSAML 4, API có thể sử dụng `OpenSaml4AuthenticationRequestResolver` và package/version khác; **không thay class name tùy tiện**. Đọc đúng reference của bản đang dùng.
- Cấu hình trên không phải `SecurityFilterChain` hoàn chỉnh; ứng dụng vẫn phải cấu hình `saml2Login`, RP registrations và filters để xử lý SAMLResponse/ACS. Không xóa validation chữ ký, audience, recipient, `InResponseTo` hay replay để “test ForceAuthn”.
- Nếu IdP yêu cầu signed AuthnRequest, phải có private signing credential **của SP** và thuật toán/binding đúng; IdP quyết định liệu yêu cầu ForceAuthn/context có được chấp nhận.

### 11.1. Còn `RequestedAuthnContext` thì sao?

Khi cần class cụ thể, tạo đúng các OpenSAML objects `RequestedAuthnContext` và `AuthnContextClassRef` trong cùng `setAuthnRequestCustomizer`, rồi gán chúng vào AuthnRequest. Điều đó đòi hỏi builder/namespace/`AuthnContextComparisonTypeEnumeration` của **OpenSAML version đang chạy**; không nên copy Java builder khác major version mà không biên dịch.

Đầu ra AuthnRequest cần kiểm tra qua IdP test ở dạng XML đã giải mã:

```xml
<samlp:RequestedAuthnContext
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Comparison="exact">
  <saml:AuthnContextClassRef>
    urn:example:contract:partner:strong-v1
  </saml:AuthnContextClassRef>
</samlp:RequestedAuthnContext>
```

Phải xác nhận IdP hỗ trợ URI đó và `Comparison=exact`. **Không tự giả định URI custom là class chuẩn**. Với IdP chỉ chấp nhận các class standard, chọn đúng class hỗ trợ theo documentation nhưng vẫn phải đánh giá liệu class đó có đạt assurance policy của tổ chức hay không. Spring customizer giúp sinh yêu cầu; **không tự kiểm tra assurance trong SAMLResponse** cho action theo custom business policy nếu bạn không bổ sung enforcement.

### 11.2. Đọc AuthnContext/Instant khi SP cần enforcement riêng

Spring Security sử dụng OpenSAML để validate SAMLResponse và tạo `Saml2Authentication`. `Saml2AuthenticatedPrincipal` cho phép đọc NameID/attributes theo API, nhưng **AuthnStatement/`AuthnContextClassRef` không nhất thiết được hiển thị thành một authority hoặc claim chuẩn trong principal**.

Muốn áp business assurance policy, chọn một extension point **sau khi OpenSAML đã xác minh** ở authentication provider/response conversion với phiên bản cụ thể, trích xuất AuthnContext/Instant từ **assertion được ký/verified** và lưu một bản `VerifiedAssurance` riêng trong authenticated session. Không:

- Parse `SAMLResponse` lại từ HTTP parameter ở controller rồi tự lấy `AuthnContextClassRef`.
- Đọc `ClassRef` từ XML chưa được xác minh chữ ký.
- Gắn `ROLE_ADMIN` chỉ từ tên URI context.
- Dùng `AuthnStatement/SessionIndex` thay mốc AuthnInstant.
- So sánh “IssueInstant mới” để bỏ qua thời gian xác thực cũ.
- Bỏ validation SAML response khi IdP không trả ngữ cảnh mong muốn.

Trong Spring Security 7.x provider OpenSAML 5 có các API tùy chỉnh validation/conversion theo reference; Spring Security 6.x tương ứng OpenSAML version khác. Thiết kế bridge phải được test bằng SAMLResponse ký hợp lệ từ IdP test với đúng context.

## 12. Java 17 chạy độc lập: chính sách mức xác thực và độ mới

Để học nguyên lý ra quyết định mà không phải chạy IdP thật, tạo một **Java 17 console program**. Input của chương trình được xem là **evidence giả lập đã được một tầng OIDC/SAML tin cậy xác minh**; nó không parse JWT/SAML, không xác minh chữ ký và **không được dùng làm validator federation production**.

Chính sách minh họa:

- OP OIDC tin cậy: `https://op.example.org`. Chỉ `acr=urn:example:policy:oidc:strong-v1` được coi là strong.
- SAML IdP tin cậy: `https://idp.example.org/entity`. Chỉ `AuthnContextClassRef=urn:example:policy:saml:strong-v1` được ánh xạ thành strong.
- Freshness: `authenticationTime` không được cũ hơn 5 phút và không được nằm trong tương lai so với UTC time test.
- Mảng `amr` chỉ giúp mô tả phương thức, **không tự nâng mức** khi class/acr yếu.
- Issuer lạ bị từ chối, không khởi tạo thêm nguồn tin cậy.

File `FederatedAssurancePolicyDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

public final class FederatedAssurancePolicyDemo {

    enum Decision {
        ALLOW,
        STEP_UP_REQUIRED,
        REAUTHENTICATE,
        DENY_SOURCE,
        DENY_TIME
    }

    record VerifiedEvidence(
        String protocol,
        String issuer,
        String contextReference,
        Set<String> methods,
        Instant authenticatedAt
    ) { }

    private static final String OIDC_ISSUER =
        "https://op.example.org";
    private static final String SAML_ISSUER =
        "https://idp.example.org/entity";

    private static final String OIDC_STRONG =
        "urn:example:policy:oidc:strong-v1";
    private static final String SAML_STRONG =
        "urn:example:policy:saml:strong-v1";

    static Decision evaluate(
            VerifiedEvidence evidence,
            Instant now) {

        if (evidence == null || now == null) {
            return Decision.DENY_SOURCE;
        }

        String requiredContext;
        if ("OIDC".equals(evidence.protocol())
                && OIDC_ISSUER.equals(evidence.issuer())) {
            requiredContext = OIDC_STRONG;
        } else if ("SAML2".equals(evidence.protocol())
                && SAML_ISSUER.equals(evidence.issuer())) {
            requiredContext = SAML_STRONG;
        } else {
            return Decision.DENY_SOURCE;
        }

        if (!requiredContext.equals(evidence.contextReference())) {
            return Decision.STEP_UP_REQUIRED;
        }

        Instant authenticatedAt = evidence.authenticatedAt();
        if (authenticatedAt == null) {
            return Decision.REAUTHENTICATE;
        }
        if (authenticatedAt.isAfter(now)) {
            return Decision.DENY_TIME;
        }

        Duration age = Duration.between(authenticatedAt, now);
        if (age.compareTo(Duration.ofMinutes(5)) > 0) {
            return Decision.REAUTHENTICATE;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2030-04-05T10:00:00Z");

        VerifiedEvidence oidcStrong = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("pwd", "otp"), now.minusSeconds(120));

        VerifiedEvidence oidcStale = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("pwd", "otp"), now.minusSeconds(601));

        VerifiedEvidence oidcWeak = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, "urn:example:policy:oidc:basic-v1",
            Set.of("pwd"), now.minusSeconds(30));

        VerifiedEvidence oidcOnlyAmr = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, "urn:example:policy:oidc:basic-v1",
            Set.of("mfa"), now.minusSeconds(30));

        VerifiedEvidence samlStrong = new VerifiedEvidence(
            "SAML2", SAML_ISSUER, SAML_STRONG,
            Set.of(), now.minusSeconds(40));

        VerifiedEvidence samlWeak = new VerifiedEvidence(
            "SAML2", SAML_ISSUER,
            "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport",
            Set.of(), now.minusSeconds(40));

        VerifiedEvidence unknownIssuer = new VerifiedEvidence(
            "OIDC", "https://op.unknown.invalid", OIDC_STRONG,
            Set.of("mfa"), now.minusSeconds(40));

        VerifiedEvidence missingTime = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("mfa"), null);

        VerifiedEvidence futureTime = new VerifiedEvidence(
            "OIDC", OIDC_ISSUER, OIDC_STRONG,
            Set.of("mfa"), now.plusSeconds(30));

        System.out.println("oidcStrong=" +
            evaluate(oidcStrong, now));
        System.out.println("oidcStale=" +
            evaluate(oidcStale, now));
        System.out.println("oidcWeak=" +
            evaluate(oidcWeak, now));
        System.out.println("oidcOnlyAmr=" +
            evaluate(oidcOnlyAmr, now));
        System.out.println("samlStrong=" +
            evaluate(samlStrong, now));
        System.out.println("samlWeak=" +
            evaluate(samlWeak, now));
        System.out.println("unknownIssuer=" +
            evaluate(unknownIssuer, now));
        System.out.println("missingTime=" +
            evaluate(missingTime, now));
        System.out.println("futureTime=" +
            evaluate(futureTime, now));
    }
}
```

Biên dịch/chạy trên JDK 17+ từ thư mục chứa file:

```bash
javac --release 17 FederatedAssurancePolicyDemo.java
java FederatedAssurancePolicyDemo
```

Stdout chính xác:

```text
oidcStrong=ALLOW
oidcStale=REAUTHENTICATE
oidcWeak=STEP_UP_REQUIRED
oidcOnlyAmr=STEP_UP_REQUIRED
samlStrong=ALLOW
samlWeak=STEP_UP_REQUIRED
unknownIssuer=DENY_SOURCE
missingTime=REAUTHENTICATE
futureTime=DENY_TIME
```

**Giải thích:**

1. `oidcStrong` có issuer OP đúng, class strong và time đủ mới.
2. `oidcStale` có class strong nhưng xác thực cách 601 giây, quá giới hạn 300.
3. `oidcWeak` có freshness nhưng thiếu class strong.
4. `oidcOnlyAmr` có chuỗi `mfa` trong methods nhưng class vẫn basic, không được nâng mức.
5. `samlStrong` dùng **policy URI của SAML issuer riêng**, không dùng OIDC acr URI.
6. `samlWeak` có một SAML class phổ biến nhưng không nằm trong mapping strong đã duyệt.
7. `unknownIssuer` không được coi là nguồn tin chỉ vì nó đưa ra context strong.
8. `missingTime` không được “dùng iat thay” để cho qua.
9. `futureTime` bị từ chối; trong production dung sai clock skew phải có chính sách kiểm thử và giới hạn.

**Giới hạn bắt buộc:** `VerifiedEvidence` là record **giả lập**. Trong production nó phải được tạo từ **token/assertion đã được thư viện xác thực**, kèm subject, audience, transaction ID, session, tenant, expiry và trust metadata. Không tạo object VerifiedEvidence từ JSON do browser gửi. `evaluate` minh họa một điều kiện trong authorization engine, không tự thay kiểm tra permission hay object ownership.

## 13. Flow step-up trong ứng dụng đa IdP và đa tenant

Một SaaS có thể có OP OIDC doanh nghiệp và IdP SAML đối tác. Cùng giao dịch phê duyệt khoản chi, nhưng mỗi nguồn có **contract assurance khác nhau**:

| Tenant | Authentication source | Điều kiện mức | Freshness | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Finance A | Corporate OIDC | `acr` thuộc allowlist Corporate high | 5 phút | Nếu thiếu thì yêu cầu OIDC step-up |
| Finance A | Partner SAML | ClassRef thuộc allowlist Partner strong | 5 phút | Nếu thiếu thì SAML ForceAuthn + RequestedAuthnContext |
| Finance B | Corporate OIDC | Có thể yêu cầu level khác theo policy B | 5 phút hoặc chặt hơn | Không reuse quyền hoặc policy của A |
| Finance B | Unknown IdP | Không có contract/registration | Không áp dụng | Từ chối, không phát issuer/metadata request tùy ý |

**Broker cần biết source thực sự của kết quả upstream.** Hai đối tác có cùng chuỗi `acr` hoặc SAML class không tự được xếp ngang nhau nếu quy trình xác minh MFA, phục hồi tài khoản hay chống phishing khác nhau.

### 13.1. Tránh account-switching trong step-up

Giả sử account A đang có session và bắt đầu duyệt hóa đơn. Trong vòng redirect, browser có thể được OP hiển thị chọn account B. Nếu app chỉ kiểm high assurance rồi hoàn tất pending action của A, đây là lỗi.

Quy trình đúng:

1. Trước step-up, tạo pending action ở server: `actorAccountId=A`, `tenantId`, `resourceId`, hash/phiên bản nội dung giao dịch, CSRF/correlation và hết hạn ngắn.
2. Khởi tạo OIDC/SAML request có state/nonce hoặc Request ID/RelayState được bảo vệ, lưu liên kết với pending action.
3. Nhận response và xác minh issuer, signature, audience, nonce/state hoặc SAML InResponseTo, time, replay.
4. Resolve subject đã được chứng minh sang **cùng local account A** hoặc một cơ chế account linking được phê duyệt; **không** tự link bằng email.
5. Kiểm context + AuthnInstant/auth_time, issuer-allowlist, policy version, device/session relation.
6. Kiểm tenant membership, role và quyền trên resource tại thời điểm commit.
7. Kiểm payload/amount/payee vẫn khớp transaction đã duyệt; chống TOCTOU.
8. Đánh dấu pending action đã dùng một lần; không cho replay callback hoặc lặp lại approval.

### 13.2. “MFA chỉ bật trên IdP” chưa đủ

Có thể IdP có chính sách “mọi user phải MFA khi đăng nhập”, nhưng RP vẫn cần:

- Biết **IdP nào** phát bằng chứng và có thuộc trust contract.
- Biết **lần MFA/reauth gần nhất** khi action cần freshness.
- Biết OP/IdP đã không âm thầm downgrade do phương thức fallback, account recovery hoặc remembered device.
- Chặn login/assertion không có context theo policy.
- Phân quyền business independently.
- Có quy trình xử lý IdP outage, enrollment chưa hoàn tất hoặc `NoAuthnContext` mà **không** tự bỏ yêu cầu.

**Phishing-resistant** là yêu cầu riêng với “có OTP”. Một `amr` có giá trị `otp` không chứng minh đạt tiêu chí chống phishing; nếu chính sách cần FIDO/WebAuthn với xác minh rpId/origin/attestation thích hợp hoặc AAL cụ thể, cần agreement và bằng chứng của OP/IdP rõ ràng.

## 14. Các tình huống âm: claim hợp lệ nhưng chính sách vẫn thất bại

| Input đã được ký/verified | Tình huống | Kết quả đúng |
| --- | --- | --- |
| OIDC ID Token hợp lệ, `acr=basic` | RP yêu cầu `high` | **Không cấp action**, step-up hoặc deny |
| OIDC ID Token hợp lệ, `amr=["mfa"]`, không có `acr` | RP yêu cầu class high | Không tự coi amr đủ |
| OIDC ID Token hợp lệ, `acr=high`, `auth_time` 2 giờ trước | Action đòi fresh ≤5 phút | Reauthenticate |
| OIDC ID Token mới có `iat` gần hiện tại nhưng `auth_time` cũ | Token phát qua SSO | Không dùng iat thay auth_time |
| OIDC request chỉ có `acr_values=high` | OP trả `acr=low` hoặc thiếu `acr` | Phải đánh giá response và fail closed |
| OIDC `prompt=login` | OP yêu cầu user nhập lại password nhưng không MFA | Nếu action cần MFA thì vẫn chưa đạt |
| OIDC `max_age=300` | ID Token thiếu `auth_time` | Lỗi response so với OIDC request, không cấp action |
| OIDC `prompt=none` | OP không thể thỏa assurance silently | Trả lỗi/flow tương tác khác, không tự hạ policy |
| SAML `ForceAuthn=true` | IdP reauth bằng password, trả context basic | Nếu action cần strong thì không đạt |
| SAML `RequestedAuthnContext exact strong` | IdP trả `NoAuthnContext` | Từ chối action, báo rõ không hỗ trợ |
| SAML `AuthnInstant` quá cũ | AuthnContext class mạnh | Không đạt freshness |
| SAML context URI do IdP B phát giống URI IdP A | Contract mapping chỉ duyệt IdP A | Không tự tin IdP B |
| SAML assertion sai signature/issuer/audience/recipient | Context URI strong | Từ chối trước khi vào assurance policy |
| OIDC token từ issuer khác với expected client | `acr=high` | Từ chối, không sử dụng mapping issuer khác |
| Broker upstream SAML không có context | Broker downstream phát `acr=high` | **Lỗi broker**, RP không nên tin mapping chưa có chứng cứ |
| Broker phát `auth_time=iat` mới dù upstream auth cũ | Sai provenance/freshness | Không được coi là fresh; sửa broker |
| Step-up response xác minh cho account B | Pending transaction thuộc A | Từ chối, không auto-link bằng email |
| User đã step-up nhưng mất quyền tenant | Membership bị revoke | Từ chối action; assurance không thay authorization |
| Session ID khác hoặc request replay | Correlation bị sai | Từ chối, không cấp action |

**Phương pháp test:** Với SAML, dùng IdP test phát và **ký lại hợp lệ** các assertions mang context/instant sai để cô lập validator assurance; không chỉ sửa raw XML khiến chữ ký lỗi. Với OIDC, dùng OP test phát ID Tokens ký hợp lệ có `acr/amr/auth_time` thay đổi để chứng minh application policy thực sự kiểm tra, không chỉ test chữ ký.

## 15. Test matrix chi tiết cho OIDC, SAML và broker

### 15.1. OIDC authorization request

1. Login bình thường với OP test; capture browser Network **không lưu token vào ticket công khai**.
2. Phát yêu cầu `acr_values=contract-high`: kiểm tra tham số thực sự được gửi, OP nhận và ID Token trả `acr` theo test fixture.
3. Phát `max_age=300`: OP trả `auth_time`, RP kiểm tuổi xác thực theo UTC.
4. Phát `max_age=0` / `prompt=login`: kiểm tra có reauthentication theo contract, không suy từ một màn hình có vẻ mới.
5. Phát `claims` Essential `acr` trong OP hỗ trợ: khi mức không đạt, OP không được phát accepted high result theo policy.
6. Kiểm `prompt=none` khi IdP session hết: xử lý lỗi và UI tương tác phù hợp.
7. Kiểm OP hỗ trợ mảng `amr` theo RFC 8176 hoặc vendor claims; unknown values không được tự cấp quyền.
8. Kiểm `state`/`nonce` và client/issuer/audience validation qua Spring Security: mọi callback lạ/mismatch phải fail.
9. Kiểm browser có local session còn nhưng action yêu cầu step-up mới: hệ thống thực sự khởi phát OIDC flow mới, không chỉ tải trang đã login.
10. Kiểm user đổi account ở OP giữa các bước: pending transaction của user A không hoàn thành cho B.

### 15.2. SAML AuthnRequest và response

1. Xác định `registrationId`, SP entityID, ACS URL, IdP signing certificate từ metadata đã phê duyệt.
2. Khi user cần fresh auth, kiểm tra AuthnRequest được tạo với `ForceAuthn=true` (XML đã giải mã trong test an toàn).
3. Khi cần strong context, kiểm `RequestedAuthnContext Comparison=exact` và ClassRef đúng URI được IdP chấp nhận.
4. Kiểm request nếu IdP yêu cầu ký: chữ ký, binding Redirect/POST và `Issuer` đúng.
5. Cho IdP test trả AuthnStatement với context mạnh, AuthnInstant mới: assurance policy chấp nhận (nếu SAML validations đều đạt).
6. Cho IdP test trả context yếu, AuthnInstant mới: từ chối action vì mức.
7. Cho IdP test trả context mạnh, AuthnInstant cũ: từ chối vì freshness.
8. Cho IdP trả `NoAuthnContext`: từ chối, không fallback vào basic session cho nghiệp vụ high.
9. Kiểm `IsPassive=true` khi cần interactive MFA: xử lý failure, không silent accept.
10. Kiểm signed assertion từ IdP không tin, sai AudienceRestriction/Recipient/InResponseTo: phải bị từ chối trước khi đọc assurance.
11. Kiểm SAML HTTP-Redirect AuthnRequest và HTTP-POST SAMLResponse có thể vẫn là phối hợp hợp lệ; binding không quyết định assurance.
12. Kiểm phiên SP ở cluster, SameSite của cookie và request correlation; mất session không phải lý do bỏ InResponseTo.

### 15.3. Broker SAML → OIDC

1. RP downstream yêu cầu `acr` strong và `max_age`; broker phải nhận đúng.
2. Broker chọn upstream SAML IdP đã phê duyệt và biết mapping exact ClassRef→downstream acr.
3. Nếu upstream đã có session, broker biết khi nào phải dùng ForceAuthn cho freshness/step-up.
4. Upstream assertion phải có chữ ký, issuer/audience/recipient/time/correlation hợp lệ.
5. Broker kiểm AuthnContext/Instant, áp mapping theo issuer/contract và từ chối class chưa được duyệt.
6. Broker **không** phát `amr` phương thức mà upstream chưa có bằng chứng.
7. Broker phát ID Token đúng broker issuer, downstream audience/client, subject mapping, `acr/auth_time` và chữ ký của broker.
8. RP downstream kiểm ID Token, policy mức và freshness; không chỉ nhìn SSO success redirect.
9. Khi upstream không đáp ứng context hoặc không hỗ trợ ForceAuthn, broker không tự phát high acr.
10. Khi nhiều tenants/IdPs có cùng ClassRef string, mapping phải riêng source và policyVersion; không leak trust.
11. Khi step-up của account A trả token cho B, broker/RP phải từ chối.
12. Test logout/SLO sau step-up và local session expiry: một phiên browser còn hoạt động không có nghĩa assurance vẫn fresh.

## 16. Những lỗi triển khai thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `acr_values` đã gửi nhưng ID Token không có `acr` | Yêu cầu chỉ voluntary, OP không cung cấp hoặc policy không hỗ trợ | Xác nhận OP contract; dùng Essential `acr` khi khả dụng; kiểm response, fail closed |
| RP nhận `acr=2` nhưng không biết mức đó là gì | Giá trị vendor-defined, chưa có mapping theo issuer | Thỏa thuận ngữ nghĩa, assurance profile, giới hạn source |
| `amr=["mfa"]` nhưng RP vẫn từ chối | Chính sách đòi `acr` cụ thể hoặc fresh auth, không chỉ methods | Kiểm mức/thời gian, không ép role từ amr |
| OP `prompt=login` nhưng không thấy MFA | Reauthentication không đồng nghĩa strong auth | Bổ sung `acr`/IdP policy về phương thức và xác minh result |
| `max_age` đã đặt, ID Token không có `auth_time` | OP không tuân thủ hoặc config chưa hiệu lực | Kiểm version/discovery/authorization URI, từ chối action |
| Sau login mới, `auth_time` vẫn cũ | OP tái sử dụng session hoặc broker không propagate reauth | Kiểm OP logs/contract, `prompt`, ForceAuthn upstream, không thay bằng iat |
| SAML `ForceAuthn=true` vẫn thấy user không nhập password | IdP dùng phương thức tương tác khác, không thực thi, hoặc browser/session behavior | Kiểm IdP policy, AuthnInstant và context; fail action nếu không đạt |
| SAML `RequestedAuthnContext` báo `NoAuthnContext` | IdP không hỗ trợ URI/comparison hoặc policy không đủ | Chọn supported class theo contract; không xóa yêu cầu để cho phép action |
| SAML context mạnh nhưng AuthnInstant cũ | Step-up chưa tạo authentication event mới | Reauth đúng flow, kiểm thời gian được xác thực |
| Spring OIDC app không khởi phát lại login khi vào /approve | Local `HttpSession` vẫn authenticated | Thiết kế explicit step-up entry point/authorization flow với correlation |
| Spring SAML resolver có ForceAuthn nhưng custom class không xuất hiện | Chưa set RequestedAuthnContext bằng đúng OpenSAML builder | Tùy chỉnh theo version, kiểm AuthnRequest XML trong test |
| Broker phát downstream `acr=high` dù upstream basic | Mapping quá rộng, không kiểm origin hoặc fallback nguy hiểm | Exact allowlist issuer/class/freshness và audit provenance |
| RP kiểm `amr` từ UserInfo nhưng không có trong ID Token | OP chỉ phát amr ở nguồn khác hoặc claims không có hợp đồng | Chỉ dùng nguồn được phê duyệt, đồng bộ sub, không tự tin UserInfo string |
| OIDC login-loop vô hạn | OP luôn trả class thấp hơn policy | Dừng loop có kiểm soát, thông báo IdP không đáp ứng |
| Chênh lệch `auth_time` do NTP | Đồng hồ OP/RP lệch | Đồng bộ UTC/NTP; bounded skew thay vì vô hạn |
| Browser đổi account khi step-up | OP account chooser chọn subject khác | Match issuer+subject/localAccountId với pending transaction |
| Có MFA nhưng vẫn không được phê duyệt giao dịch | User thiếu role/tenant permission hoặc policy phân quyền | Kiểm authorization/business rules riêng |
| Bộ lọc SAML trả lỗi trước assurance check | Assertion sai signature/audience/recipient/InResponseTo | Sửa federation config, không tắt SAML validation |
| SAML `AuthnContextClassRef` trùng nhiều IdP | Chỉ so URI, không phân biệt issuer | Map theo issuer + URI + contract version |
| Chỉ đọc `iat` để tính freshness | Nhầm issued token với authentication time | Dùng `auth_time`/`AuthnInstant`, kiểm theo nguồn |
| “Spring đã login nên chắc đã đạt high assurance” | Spring SSO validation không tự biết policy nghiệp vụ đặc thù | Bổ sung assurance policy ở service/before protected action |

### 16.1. Debug theo thứ tự nguyên nhân

```text
1. SAML/OIDC evidence có được verify đúng issuer, key, audience,
   nonce/state hoặc InResponseTo, Recipient/Destination và thời gian?
2. Request có thực sự gửi đúng ForceAuthn/RequestedAuthnContext
   hoặc acr_values/claims/max_age/prompt qua mạng?
3. Nhà cung cấp đã xác thực lại hay tái sử dụng session?
4. ID Token/AuthnStatement thực tế báo context nào, auth time nào?
5. URI/context đó có nằm trong mapping của đúng issuer không?
6. Freshness có còn hợp lệ so với clock UTC và policy action?
7. Subject sau step-up có trùng original account/pending action?
8. User có quyền trên tenant/resource/giao dịch đó không?
9. Broker có làm sai provenance hoặc silent downgrade?
10. Nếu không thể đáp ứng high, app có fail closed và chặn loop?
```

Không bật debug bằng cách ghi toàn bộ ID Token, cookie, SAMLResponse hoặc private keys trong production. Trong lab, decode để quan sát nhưng chỉ xuất các trường không nhạy cảm/tổng hợp, xóa log/test artifacts theo chính sách.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** OIDC OP trả ID Token có `acr=high`, `amr=["pwd","otp"]`, `iat` vừa mới nhưng `auth_time` cách một giờ. App yêu cầu fresh trong 5 phút. Có đạt không?

**Đáp án:** Không. Mức/AMR không bù được freshness; dùng `auth_time` (đã verified), không dùng `iat`.

**Câu 2.** SP SAML gửi `ForceAuthn=true`. IdP xác thực lại bằng password và trả `AuthnContextClassRef=PasswordProtectedTransport`; nghiệp vụ đòi lớp strong riêng. Có được hoàn tất action không?

**Đáp án:** Không nếu lớp trả về không nằm trong policy cho action. ForceAuthn chỉ yêu cầu reauthentication, không tự bảo đảm mức strong.

**Câu 3.** RP gửi `acr_values=strong`, OP không trả `acr`. RP có được mặc định coi OP đã thỏa vì request không lỗi không?

**Đáp án:** Không. `acr_values` là voluntary. Cần kiểm ID Token và dùng cơ chế Essential `acr`/contract khi bắt buộc, hoặc fail closed.

**Câu 4.** Broker nhận SAML class `urn:example:contract:partner:strong-v1` từ issuer A và issuer B; chỉ A có hợp đồng assurance mạnh. Có được map cả hai sang OIDC high không?

**Đáp án:** Không. Mapping phải theo **issuer + class + contract**, không chỉ chuỗi class.

**Câu 5.** OIDC `amr=["mfa"]` có đủ để suy ra đã dùng phishing-resistant WebAuthn theo mọi chính sách không?

**Đáp án:** Không. `mfa` nói chung về nhiều yếu tố theo OP, không xác nhận loại yếu tố, chứng cứ FIDO/WebAuthn hoặc contract chống phishing.

**Câu 6.** OP đang có SSO session; RP gửi `prompt=none` và yêu cầu step-up cần UI. OP báo `interaction_required`. RP nên làm gì?

**Đáp án:** Thực hiện một flow tương tác được phép (`prompt=login`/`max_age` và `acr` policy), hoặc từ chối với thông báo rõ; không silently approve bằng session thấp.

**Câu 7.** Sau step-up, client chuyển sang account B trong OP. Hệ thống có thể dùng assurance mạnh của B để duyệt pending transaction do account A tạo không?

**Đáp án:** Không. Phải ràng buộc subject/local account, tenant, session, correlation và transaction trước khi commit.

**Câu 8.** Spring Security `oauth2Login()` và `saml2Login()` đã chạy đúng, có nghĩa `acr` và `AuthnContext` tự được map thành role ứng dụng không?

**Đáp án:** Không. Framework xác thực giao thức; assurance của từng business action và tenant permission là policy riêng cần enforcement.

## 18. Checklist triển khai production

- [ ] Định nghĩa riêng yêu cầu **mức xác thực**, **freshness** và **quyền nghiệp vụ**, không gộp vào một biến `isMfa`.
- [ ] Mỗi IdP/OP/broker có issuer/registration, key/metadata trust và authentication context contract được phê duyệt.
- [ ] SAML AuthnStatement `AuthnContextClassRef` / `AuthnInstant` chỉ được đọc sau khi assertion signature, issuer, audience, recipient, InResponseTo/replay hợp lệ.
- [ ] OIDC `acr/amr/auth_time` chỉ được dùng từ ID Token đã xác minh `iss/aud/signature/nonce/state/exp` theo flow.
- [ ] `acr_values` được hiểu là voluntary; nếu cần exact assurance thì dùng cơ chế OP support và kiểm returned `acr`/Essential claims.
- [ ] `amr` được đánh giá theo RFC 8176/issuer contract; không tự xem `mfa` hay `otp` là mọi mức security hoặc phishing-resistant.
- [ ] `auth_time`/`AuthnInstant` dùng cho freshness; không lấy `iat`/`IssueInstant` hoặc web session creation time thay thế.
- [ ] SAML `ForceAuthn` và `RequestedAuthnContext` được triển khai đúng, IdP hỗ trợ `Comparison`/class; có xử lý `NoAuthnContext`.
- [ ] OIDC `prompt=login`/`max_age` được cấu hình ở explicit step-up flow khi cần và xử lý lỗi theo specification.
- [ ] Broker có mapping allowlist **issuer + class/acr + version**, giữ provenance, không tạo downstream assurance cao hơn chứng cứ có thật.
- [ ] Nếu broker nhận `prompt=login`/`max_age=0`, có cơ chế thực sự reauthenticate upstream hoặc fail closed.
- [ ] Không gửi `amr` giả hoặc dùng `auth_time=iat` khi upstream đã xác thực từ lâu.
- [ ] Step-up flow có CSRF, state/nonce hoặc SAML InResponseTo, session correlation, replay protection và one-time pending transaction.
- [ ] Sau step-up, subject vẫn là cùng local account; tenant, permission, resource, amount/payee/operation được kiểm tra lại tại commit.
- [ ] Không redirect vòng lặp khi IdP không hỗ trợ mức yêu cầu; chặn action và báo lỗi có thể chẩn đoán.
- [ ] Session/app logout, OP SSO và MFA age được đánh giá độc lập; session còn không làm evidence đủ mới mãi.
- [ ] Clock UTC/NTP đồng bộ và clock-skew policy hẹp, không tự nới timestamp checks để qua QA.
- [ ] Tests có ID Token/SAML assertions ký hợp lệ nhưng context/freshness sai để cô lập assurance validator.
- [ ] Không đưa private key, raw SAMLResponse, ID Token, OTP, session cookie hoặc dữ liệu nhạy cảm vào log/ticket.
- [ ] Audit ghi mã chính sách, issuer verified, context decision, freshness, tenant và business action tối thiểu cần thiết.

**Kết luận:** Trong SAML, `AuthnContext` mô tả lớp/ngữ cảnh xác thực đã đạt, `RequestedAuthnContext` yêu cầu một lớp, `ForceAuthn` yêu cầu xác thực lại và `AuthnInstant` chỉ thời gian xác thực. Trong OIDC, `acr` mô tả lớp, `amr` mô tả phương thức, `auth_time` chỉ thời gian, còn `acr_values`/Essential `acr`, `max_age` và `prompt=login` là các cách **yêu cầu** mức và độ mới với semantics khác nhau. Khi có identity broker, **không tự chuyển đổi các claim bằng cách so chuỗi hoặc nâng cấp MFA**, mà phải giữ nguồn và bằng chứng, mapping theo contract, kiểm freshness và enforce quyền ở action cuối cùng.

## 19. Tài liệu tham khảo

1. [OpenID Connect Core 1.0 – Authentication Request, `acr`, `auth_time`, `max_age`, `claims`](https://openid.net/specs/openid-connect-core-1_0.html): định nghĩa claim, tham số prompt/max_age/acr_values, Essential ACR và yêu cầu RP xác minh.
2. [IETF RFC 8176 – Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176.html): các chuỗi `amr` được chuẩn hóa như `pwd`, `otp`, `mfa`, `hwk`, `fpt`.
3. [IANA – Authentication Method Reference Values Registry](https://www.iana.org/assignments/authentication-method-reference-values/): danh mục AMR hiện hành và chủ thể quản lý.
4. [OASIS SAML 2.0 Core – Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AuthnStatement/AuthnContext, RequestedAuthnContext, ForceAuthn/IsPassive, NoAuthnContext.
5. [OASIS SAML 2.0 AuthnContext](https://docs.oasis-open.org/security/saml/v2.0/saml-authn-context-2.0-os.pdf): bộ lớp/ngữ cảnh xác thực và ý nghĩa thuật ngữ.
6. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, AuthnRequest/Response, correlation.
7. [Spring Security – Producing SAML AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): OpenSaml authentication request resolver, ForceAuthn customizer, request storage.
8. [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validating SAMLResponse/Assertion và provider extension points.
9. [Spring Security – OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): `DefaultOAuth2AuthorizationRequestResolver` và bổ sung OIDC authorization parameters.
10. [Spring Security – OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): custom authorization endpoint/authorization request resolver.
11. [Spring Security API – IdTokenClaimAccessor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html): `getAuthenticationContextClass()`, `getAuthenticationMethods()` và `getAuthenticatedAt()`.
12. [Microsoft Entra – SAML protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol): ví dụ phụ thuộc nhà cung cấp, gồm hỗ trợ và giới hạn `RequestedAuthnContext Comparison`.
