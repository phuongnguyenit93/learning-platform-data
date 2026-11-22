# Đăng nhập SAML 2.0 do IdP khởi tạo và rủi ro khi không có yêu cầu tương ứng

> **Chủ đề:** Spring Security – federation. **Nhóm:** Luồng đăng nhập SAML2. Bài học tập trung vào **IdP-initiated SSO**, còn gọi là **unsolicited SAML Response**, cách nó khác **SP-initiated SSO**, vì sao thiếu `AuthnRequest`/`InResponseTo` tạo ra rủi ro đặc biệt, và cách đánh giá, tích hợp, kiểm thử với ứng dụng Spring Security đóng vai trò Service Provider (SP).

## 1. Nắm đúng bản chất IdP-initiated SSO

Trong SAML 2.0 Web Browser SSO, có hai cách thường gặp để khởi động đăng nhập:

- **SP-initiated:** người dùng vào ứng dụng SP trước. SP tạo `AuthnRequest`, chuyển trình duyệt sang IdP xác thực; IdP trả `SAMLResponse` liên hệ với yêu cầu đang chờ. SP có cơ sở đối chiếu **đăng nhập được chính trình duyệt/phiên này khởi tạo**.
- **IdP-initiated:** người dùng bắt đầu ở portal hoặc dashboard ứng dụng của IdP, chẳng hạn bấm biểu tượng một ứng dụng SaaS. IdP tự tạo `SAMLResponse` và chuyển qua browser tới **Assertion Consumer Service (ACS)** của SP **mà SP không hề gửi AuthnRequest trước đó**.

Trong trường hợp thứ hai, thông điệp gọi là **unsolicited response**: "không được yêu cầu trước" từ góc nhìn SP. Đó **không mặc định là thông điệp giả**; nó có thể được IdP hợp lệ ký và chứa assertion hợp lệ. Rủi ro là SP thiếu một bằng chứng về **ý định đăng nhập** của chính phiên trình duyệt đang nhận response.

Các vai trò cần nhớ:

| Thành phần | Trách nhiệm |
|---|---|
| **Identity Provider (IdP)** | Xác thực người dùng, thực hiện MFA/policy, tạo và ký SAML Response/Assertion theo thỏa thuận |
| **Service Provider (SP)** | Kiểm nguồn IdP, chữ ký, audience, recipient, thời hạn, chống replay và cấp phiên/authority ứng dụng |
| **Browser/User Agent** | Vận chuyển redirect hoặc HTML form POST; không được tin làm nguồn assertion |
| **ACS endpoint** | Đường dẫn SP nhận `SAMLResponse` qua binding (HTTP-POST trong ví dụ) |
| **`AuthnRequest`** | Yêu cầu SAML do SP phát, có ID để IdP liên hệ response trong SP-initiated flow |
| **`InResponseTo`** | Mã liên hệ response/subject confirmation với ID AuthnRequest gốc khi là solicited response |
| **`RelayState`** | Thông số binding đưa trạng thái/điểm đến điều hướng; phải được xác minh/sanitized theo contract, đặc biệt ở IdP-initiated |

**Đừng nhầm:** IdP-initiated **không có AuthnRequest tương ứng** khác hoàn toàn với **SP-initiated bị mất session**. Nếu trước đó SP đã thực sự phát AuthnRequest nhưng mất request state/cookie, không được "chữa" bằng cách mặc nhiên phân loại response đó thành unsolicited và bỏ kiểm tra tương quan.

## 2. Hai luồng nhìn cạnh nhau

### 2.1. SP-initiated SSO (có request correlation)

~~~text
Browser (phiên B)             Spring Security SP                 IdP
    | GET /private                    |                             |
    +-------------------------------->|                             |
    |                                 | sinh AuthnRequest ID=_req123 |
    |                                 | lưu request/state gắn phiên B|
    |<----------- Redirect SAMLRequest=_req123                      |
    +--------------------------------------------------------------->|
    |                                         xác thực/MFA           |
    |<------------------- Form POST SAMLResponse --------------------+
    +-- POST ACS -------------------->|                             |
    |                                 | Response.InResponseTo=_req123
    |                                 | SubjectConfirmationData
    |                                 |  .InResponseTo=_req123
    |                                 | xác minh chữ ký + điều kiện
    |                                 | đối chiếu request ID, phiên B
    |<------------------- tạo phiên đăng nhập nếu hợp lệ ------------|
~~~

**Giá trị bảo vệ của `InResponseTo`:** Nếu IdP trả về response cho `_req123` và SP còn request phù hợp trong ngữ cảnh **cùng browser/session**, SP có thể kiểm mối liên hệ giữa phản hồi và luồng đăng nhập đã khởi tạo. Đây là một lớp ngăn **login CSRF/session swapping** ngoài chữ ký/assertion validation. Chỉ so một chuỗi `InResponseTo` với ID tồn tại toàn cục mà **không gắn với browser/session** có thể vẫn chưa đáp ứng mục đích chống CSRF.

### 2.2. IdP-initiated SSO (không có request correlation)

~~~text
Browser                         IdP portal                  Spring Security SP
    | GET /my-apps                 |                               |
    +----------------------------->|                               |
    | Đã login/MFA tại IdP         |                               |
    | Click "Portal SP"            |                               |
    |                              | tạo Response mới, không nhận   |
    |                              | AuthnRequest từ SP             |
    |<-------- HTML form POST ------+                               |
    +----------------------- POST /login/saml2/sso/corporate ----->|
                                                                   |
                                     Kiểm chữ ký/issuer/audience/  |
                                     recipient/time/replay và policy|
                                                                   |
    |<--------------------------- SP tạo session nếu chấp nhận -----+
~~~

SP có thể **biết IdP đã xác thực một danh tính**, nhưng **không thể chứng minh bằng request correlation rằng browser đang nhận response đã chủ động yêu cầu tạo phiên với danh tính đó**. Việc browser tới từ portal IdP là một giả định về quá trình điều hướng, không phải một chứng cứ mật mã chứa trong response.

### 2.3. So sánh nhanh

| Tiêu chí | SP-initiated | IdP-initiated |
|---|---|---|
| Ai khởi tạo luồng SAML? | SP khi người dùng vào app | IdP/portal khi người dùng bấm app tile |
| Có `AuthnRequest` từ SP? | **Có** | **Không** |
| Có pending request ID trong SP? | **Có** nếu state còn nguyên | **Không** |
| `Response.InResponseTo` | Trỏ tới request đã phát theo profile | **Phải vắng mặt** ở unsolicited |
| `SubjectConfirmationData.InResponseTo` | Trỏ tới request gốc theo profile | **Phải vắng mặt** ở unsolicited bearer confirmation |
| Chống login CSRF bằng request/session correlation? | Có thể triển khai chặt chẽ | **Không có cùng bảo đảm này** |
| Chữ ký, issuer, audience, recipient, time | **Bắt buộc kiểm** | **Vẫn bắt buộc kiểm** |
| Chống replay assertion | **Bắt buộc theo profile** | **Bắt buộc theo profile** |
| RelayState | Có thể gắn với request đã lưu | Có thể IdP gửi unsolicited; phải kiểm nghiêm ngặt |
| Khi nào nên dùng? | Ưu tiên cho app web hiện đại có thể kiểm soát entrypoint | Chỉ khi yêu cầu từ IdP portal/legacy và đã đánh giá rủi ro |

## 3. Các quy tắc chuẩn SAML 2.0 về unsolicited response

**OASIS SAML 2.0 Profiles, §4.1.5** cho phép IdP khởi tạo SSO bằng cách gửi một unsolicited `Response` tới SP. Nhưng có những ràng buộc rất cụ thể:

1. **Response không được chứa `InResponseTo`.** Với bearer `SubjectConfirmationData`, thuộc tính `InResponseTo` cũng **không được hiện diện**.
2. Khi dùng metadata, IdP nên gửi Response/artifact tới **ACS được đánh dấu mặc định** của SP nếu không có chỉ định tương ứng.
3. Có thể dùng binding-specific `RelayState` theo thỏa thuận trước giữa IdP/SP để chỉ nơi tiếp tục điều hướng hoặc tài nguyên nội bộ sau đăng nhập. SP nên xác định **điểm đến mặc định an toàn** nếu không có RelayState.
4. Các kiểm tra của Web Browser SSO vẫn áp dụng: signature/trust, confirmation, recipient, expiration, audience, replay protection và policy của SP. Thiếu AuthnRequest **không cho phép bỏ mọi validation khác**.

**OASIS Errata 05** làm rõ nguy cơ **CSRF** do không thể bảo đảm browser đã chủ động khởi tạo luồng SAML ở SP. Errata cũng khuyến nghị SP có khả năng **tắt nhận unsolicited response** khi cần. Với HTTP-POST, các assertion được dùng phải **được bảo vệ bởi chữ ký số**, có thể bằng chữ ký từng Assertion hoặc chữ ký Response bao phủ assertion theo errata; không cho phép unsigned plain assertion chỉ vì đây là IdP-initiated.

**Tránh nhầm ngữ nghĩa:** "Không có `InResponseTo`" là **đúng cấu trúc** của một unsolicited response đã được cho phép; không có nghĩa "bỏ kiểm `InResponseTo` trên mọi Response". Ngược lại, một response có `InResponseTo` trỏ tới request không tồn tại phải được xử lý như **response solicited không hợp lệ**, chứ không âm thầm coi thành unsolicited.

### 3.1. XML minh họa: IdP-initiated

Đoạn dưới đây là **sơ đồ XML rút gọn**, có dấu `...` thay dữ liệu bắt buộc và chữ ký; **không phải SAML Response hợp lệ để đưa vào ACS**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp_unsolicited_01"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
  <!-- ds:Signature, Status và dữ liệu được ký đặt theo chuẩn/profile -->
  <saml:Assertion ID="_assertion_unsolicited_01">
    <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
    <!-- ds:Signature hoặc chữ ký hợp lệ ở Response -->
    <saml:Subject>
      <saml:NameID>user-123</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://sp.example.org/login/saml2/sso/corporate"
            NotOnOrAfter="2026-11-07T05:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Trong mẫu IdP-initiated, cả `Response` và bearer `SubjectConfirmationData` **không có thuộc tính `InResponseTo`**. Các giá trị `ID`, thời hạn và user là ví dụ; thời điểm ở ví dụ không có ý nghĩa khi ứng dụng thật chạy.

### 3.2. XML minh họa: SP-initiated

Với response **có yêu cầu tương ứng**, phần liên hệ sẽ mang ID của AuthnRequest, ví dụ:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_resp_solicited_02"
    InResponseTo="_authnrequest_987"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <!-- Issuer, Signature, Status, Assertion... -->
  <saml:Assertion ID="_assertion_solicited_02">
    <saml:Subject>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            InResponseTo="_authnrequest_987"
            Recipient="https://sp.example.org/login/saml2/sso/corporate"
            NotOnOrAfter="2026-11-07T05:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
  </saml:Assertion>
</samlp:Response>
~~~

Đây vẫn là **XML phác thảo** thiếu namespace declarations và phần tử cần thiết. Khi đọc thực tế, đừng so thẻ bằng regex hay tự tạo validator XML; dùng OpenSAML và Spring Security để xác minh signature/reference và các điều kiện.

## 4. Thiếu yêu cầu tương ứng tạo ra lỗ hổng gì?

### 4.1. Login CSRF / session swapping

**CSRF khi đăng nhập** khác CSRF gọi API chuyển tiền. Kịch bản khái niệm:

1. Attacker có tài khoản hợp lệ của **attacker** tại IdP; IdP có thể phát hành SAML Response **được ký hợp lệ** cho tài khoản đó và SP đích.
2. Attacker tìm cách khiến browser **nạn nhân** gửi Response đó tới ACS trong cửa sổ hiệu lực (ví dụ thông qua trang tự động submit form trên một miền khác).
3. Nếu SP cho phép unsolicited response và response chưa từng được dùng, SP có thể tạo session **của attacker** trên browser nạn nhân.
4. Nạn nhân nhìn thấy đã đăng nhập nhưng thực chất đang ở **tài khoản do attacker sở hữu**. Nếu nạn nhân thêm dữ liệu hay thực hiện thao tác, dữ liệu có thể nằm trong tài khoản attacker, gây lộ thông tin hoặc nhầm lẫn nghiệp vụ.

Đây là **account/session confusion**. Không nhất thiết attacker chiếm được session của nạn nhân hay giả chữ ký IdP. Chữ ký **vẫn hợp lệ** vì response thực sự do IdP phát cho attacker. Chính điểm thiếu là **ràng buộc response với việc nạn nhân đã chủ động khởi tạo một login flow tại SP**.

**Điểm tinh tế:** Replay cache không chắc chặn lần **đầu tiên** một Response hợp lệ được dùng ở browser sai. Replay cache chỉ chặn **dùng lại** khi ID đã bị tiêu thụ. Chữ ký và TLS cũng không tự giải quyết login CSRF: chúng bảo vệ nguồn/tính toàn vẹn và đường truyền chứ không xác minh **ý định login của chính browser này**.

### 4.2. Replay / message insertion

Nếu SP không quản lý ID assertions/responses đã dùng, attacker có thể thử đưa lại cùng một SAMLResponse trong thời gian còn hiệu lực. Với bearer assertion theo Web Browser SSO HTTP-POST, SP phải chống replay, tối thiểu lưu **assertion ID đã được dùng** trong thời gian assertion còn hợp lệ theo `SubjectConfirmationData.NotOnOrAfter`; có thể kết hợp kiểm Response ID và `OneTimeUse` khi profile/policy quy định.

- **Replay cache** cần nhất quán giữa các instance của SP trong cluster, tránh instance A từ chối nhưng instance B chưa biết ID đã dùng.
- Cache TTL phải phủ ít nhất cửa sổ hợp lệ cần bảo vệ và giới hạn clock skew tương ứng; tránh TTL ngắn khiến assertion hết hạn trên giấy nhưng được reuse trong thực tế.
- Không coi việc SAMLResponse bị Base64-encode là mật mã hoặc một cơ chế chống replay.
- Không đặt thời hạn assertion/SubjectConfirmation quá dài để "dễ test".

Một unsolicited response có chữ ký nhưng expired, sai audience, sai recipient hoặc bị replay **vẫn phải bị từ chối**.

### 4.3. RelayState và open redirect

Trong SP-initiated, RelayState thường giúp SP khôi phục trạng thái do chính SP tạo, ví dụ URL protected resource ban đầu. Trong IdP-initiated, **SP không có request state do chính mình phát trước**, nên RelayState có thể là dữ liệu do IdP đưa sang; không mặc định trusted, và trong một số binding nó **không được bảo vệ tính toàn vẹn**.

Nếu SP nhận giá trị như `RelayState=https://external.example.net/collect` rồi redirect browser đến URL bất kỳ, có nguy cơ:

- **Open redirect:** login hoàn tất rồi chuyển đến domain attacker.
- **Phishing:** user nghĩ đang được SP điều hướng tới tài nguyên đáng tin.
- **Thông tin rò rỉ:** query string hoặc fragment nội bộ bị đưa tới nơi không chủ đích.
- **Kết nối nhầm tenant/đích:** RelayState bị dùng để chọn tenant/IdP/role mà không qua chính sách.

**Chính sách an toàn:** Dùng **allowlist URL nội bộ hoặc định danh đích opaque** do SP kiểm soát. Ưu tiên relative paths có path prefix hợp lệ, loại bỏ URL bắt đầu bằng `//`, scheme không được phép, CR/LF và encoding bất thường; normalize/parse URI bằng thư viện đúng ngữ nghĩa, tránh regex tự viết. Nếu dữ liệu không hợp lệ, chọn **default landing page** hoặc từ chối theo policy. Không để RelayState tự quyết định vai trò, user hay IdP tin cậy.

### 4.4. Nhầm IdP/tenant hoặc danh tính liên kết

Một SP hỗ trợ nhiều IdP có thể nhận Response từ IdP A khi browser đang mong đợi IdP B, hoặc bị gửi tới ACS của registration không phù hợp. Trước khi xác thực, **không được chọn trust bằng dữ liệu chưa được kiểm** rồi mở rộng tất cả keys. SP phải gắn Response với **RelyingPartyRegistration** đã định nghĩa, **issuer**, certificate và **đúng SP entityID/audience**.

Các hệ thống hỗ trợ **account linking** dựa trên email càng dễ nguy hiểm: một địa chỉ email có thể thay đổi, tái sử dụng, trùng tenant hoặc không được xác minh theo chính sách. Không liên kết tài khoản hoặc nâng quyền chỉ vì unsigned/untrusted attribute hay chuỗi email ở response.

### 4.5. Rủi ro khi IdP mở portal cho mọi người dùng

Người dùng có thể bấm app tile khi chưa có SP account/local authorization phù hợp. Lỗi vận hành thường thấy:

- IdP xác thực thành công nhưng SP không tìm được tài khoản ứng dụng.
- SP tạo user JIT mà chưa kiểm entitlement/lifecycle, gây tài khoản rác.
- IdP gửi thuộc tính thiếu nhóm, tenant hoặc NameID không ổn định.
- IdP-initiated login tạo session không khớp trạng thái nạn nhân đang thao tác trong SP (ví dụ đang có một tài khoản khác).

Việc gán app tile tại IdP **không đồng nghĩa** cấp quyền vào tất cả tính năng trong SP. SP vẫn phải map roles và kiểm account status, session switching, logout/hết hạn.

## 5. Chữ ký, mã hóa và điều kiện SAML vẫn là bắt buộc

Tuy IdP-initiated không có AuthnRequest, **mọi kiểm tra xác thực SAML còn lại không được bỏ**. Checklist:

| Kiểm tra | Trường/nguồn | Vì sao quan trọng |
|---|---|---|
| Trusted issuer | `Response.Issuer` / `Assertion.Issuer` | Chỉ IdP đã đăng ký mới được phát assertion cho SP |
| XML signature | Signed Response hoặc signed Assertions theo profile | Chống dữ liệu giả/sửa; dùng public cert của đúng IdP |
| Signature coverage | XMLDSig `Reference` / đúng node | Tránh XML Signature Wrapping và chọn sai assertion |
| Audience | `AudienceRestriction` | Không dùng assertion dành cho SP khác |
| Destination | `Response.Destination` | Response phải hướng tới ACS hiện tại |
| Recipient | Bearer `SubjectConfirmationData.Recipient` | Xác nhận assertion dành đúng ACS |
| Conditions | `NotBefore/NotOnOrAfter` | Chỉ chấp nhận trong cửa sổ hợp lệ |
| SubjectConfirmation | Bearer Method, `NotOnOrAfter` và những trường áp dụng | Kiểm ngữ cảnh dùng bearer assertion |
| Unsolicited shape | **Không** có `InResponseTo` ở Response và bearer confirmation | Tuân thủ profile; không giả lập request từ SP |
| Replay defense | Assertion ID cache / policy của SP | Không tái sử dụng bearer assertion |
| Status | SAML `StatusCode` | Chỉ tạo session sau thành công hợp lệ |
| Principal mapping | `NameID`, issuer, tenant, attributes | Không nhầm account hoặc tự cấp quyền |
| Authorization | Internal roles/permissions | Authentication không đồng nghĩa quyền admin |

**Response ký vs Assertion ký:** với HTTP-POST Web Browser SSO, assertion được dùng phải có sự bảo vệ của chữ ký hợp lệ — có thể ký chính Assertion hoặc ký Response bao phủ assertion, theo OASIS errata. Cấu hình IdP/SP cụ thể có thể yêu cầu tầng chữ ký chặt hơn. Một Response không ký và mọi assertion không ký **không được xem là hợp lệ** chỉ vì xuất phát từ portal IdP.

**EncryptedAssertion:** mã hóa giúp bảo mật thông tin assertion cho SP giữ private decryption key, nhưng **giải mã thành công không chứng minh nguồn IdP**. Vẫn phải kiểm chữ ký và điều kiện; chữ ký Response ký ciphertext hoặc chữ ký Assertion nằm bên trong ciphertext tùy cách IdP cấu hình.

**TLS:** HTTPS là cần thiết cho IdP SSO, ACS, metadata, nhưng không thay signature verification của XML SAML. Browser form POST có thể bị tạo lại; một kết nối TLS hợp lệ từ browser không làm browser trở thành trusted issuer.

## 6. "Không có InResponseTo" không đồng nghĩa "mất an toàn tuyệt đối"

Đánh giá phải tách:

1. **Assertion xác thực:** Một unsolicited response được ký hợp lệ, đúng issuer/recipient/audience, chưa hết hạn và chưa bị dùng có thể chứng minh IdP đã xác thực chủ thể mà assertion mô tả.
2. **Ý định và phiên browser:** Không có pending request nên SP thiếu cơ sở tương quan sự kiện này với hành động đăng nhập mà chính browser/người dùng đã khởi tạo tại SP.
3. **Chính sách chấp nhận:** Tổ chức có thể quyết định **không chấp nhận** IdP-initiated; hoặc **chấp nhận có kiểm soát** vì yêu cầu portal/legacy, sau khi đánh giá và giảm thiểu rủi ro.

Vì vậy "không có `InResponseTo`" không phải lý do tự động bỏ mọi bước kiểm. Chỗ bất khả chính là **không thể khôi phục một AuthnRequest chưa từng được tạo** để lấy security guarantee tương đương SP-initiated.

**Ưu tiên thiết kế:** Nếu kiểm soát cả app và entrypoint, cho portal IdP **liên kết tới trang/URL bắt đầu SP-initiated login** (hoặc deep link của SP), để SP phát AuthnRequest và lưu browser state; IdP sau đó trả response có correlation. Cách này có thể giữ UX "bấm tile" nhưng vẫn dùng **SP-initiated SAML** phía giao thức, nếu IdP và routing cho phép.

## 7. Quyết định cho phép IdP-initiated trong sản phẩm

### 7.1. Khi nào nên từ chối?

Ưu tiên từ chối unsolicited response nếu:

- Ứng dụng có thể bắt đầu SP-initiated flow, không cần interop legacy.
- Dữ liệu/tác vụ có rủi ro cao, account confusion hoặc login CSRF là đáng kể.
- SP sử dụng account linking/JIT provisioning nhạy cảm và không có cơ chế xác nhận user intent.
- Không có replay cache chia sẻ giữa instances hoặc không quản lý được IdP trust/keys.
- Không có cách kiểm RelayState, issuer/tenant hoặc session switching rõ ràng.
- Nhà cung cấp framework/phiên bản không có cơ chế kiểm soát nhận unsolicited đáp ứng policy yêu cầu.

**Lưu ý:** "Tắt IdP-initiated" cần thực thi ở **SP**, không chỉ giấu app tile ở IdP; attacker vẫn có thể thử POST unsolicited response đến ACS nếu SP còn chấp nhận.

### 7.2. Khi buộc phải hỗ trợ

Phối hợp cả đội SP/IdP và security để xác định:

- **Allowlist IdP registrations** được phép unsolicited, không bật mặc định cho mọi IdP/tenant.
- Chỉ nhận tại **ACS/host công khai chính xác**; không dựa vào hostname do client tự đưa.
- **Trusted signing keys**, strict issuer/audience/destination/recipient/time/subject confirmation/replay.
- **Giới hạn thời hạn**, chính sách MFA và assertion attributes phù hợp.
- **RelayState allowlist hoặc opaque identifier**, default landing page an toàn, không open redirect.
- **Chính sách khi SP đã có session khác:** cân nhắc từ chối silent account switch, yêu cầu user xác nhận chuyển tài khoản hoặc bắt đầu lại SP-initiated flow. Cách này giảm nhầm lẫn tài khoản nhưng không khôi phục được correlation của unsolicited response.
- **Không liên kết tài khoản hoặc cấp quyền nhạy cảm** chỉ từ một email attribute mà không có kiểm tra federation và vòng đời.
- **Giám sát sự kiện** unsolicited login, failed signature/audience, replay, account switch và issuer mismatch.
- **Positive/negative integration tests** với IdP thật, browser/cookie policy và các trường hợp request giả/expired/replayed.

**Thực tế bảo mật:** Một trang xác nhận thao tác hoặc yêu cầu người dùng tự bấm tiếp trong SP có thể giảm rủi ro vô ý, nhưng không nên tuyên bố nó biến IdP-initiated thành SP-initiated hay giải quyết hoàn toàn login CSRF. Để có request correlation thực, phải khởi tạo luồng từ SP trước.

## 8. Spring Security Servlet SAML2: đường đi request và chỗ đặt policy

Spring Security có module **`spring-security-saml2-service-provider`** để ứng dụng Servlet làm SAML SP. Luồng mặc định thường dùng:

- `/saml2/authenticate/{registrationId}` để bắt đầu SP-initiated, tạo `AuthnRequest`.
- `/login/saml2/sso/{registrationId}` làm ACS nhận POST `SAMLResponse`.
- `Saml2WebSsoAuthenticationRequestFilter` thực hiện phần tạo AuthnRequest.
- `Saml2WebSsoAuthenticationFilter` xử lý SAMLResponse, gọi converter và authentication provider.
- `Saml2AuthenticationTokenConverter` giải quyết registration/token.
- `OpenSaml5AuthenticationProvider` (ở dòng Spring Security dùng OpenSAML 5) kiểm chữ ký, issuer, destination, assertion, decryption, conditions rồi tạo `Saml2Authentication`.
- `RelyingPartyRegistrationRepository` chứa SP/IdP entityID, ACS, cert, SSO endpoint cho registration.

Tài liệu Spring Security SAML2 overview mô tả **hai cách** khiến IdP phát response: đi tới IdP và chọn app tile, hoặc vào trang SP được bảo vệ để SP redirect. Vì vậy một ACS có thể nhận SAMLResponse không khởi tạo từ SP trong một số cấu hình/version.

**Không suy luận từ tài liệu legacy:** Tài liệu **Spring Security SAML Extension** cũ có property `supportUnsolicitedResponse` trên `ExtendedMetadata`. Đây **không phải** một property chung của Spring Security SAML2 Service Provider hiện đại. Trước khi triển khai policy "chỉ nhận solicited", phải xác định **version**, provider, converter/validator được dùng và nơi kiểm request correlation. Không chép nguyên cấu hình XML Spring SAML Extension cũ vào ứng dụng Spring Boot mới.

### 8.1. Spring Boot config cho SP (minh họa)

Trong dự án Servlet Spring Boot (có dependency web, security và `spring-security-saml2-service-provider`), cấu hình một IdP:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://sp.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://sp.example.org/login/saml2/sso/corporate"
            assertingparty:
              metadata-uri: "https://idp.example.org/metadata"
~~~

Đường dẫn và domain đều là **minh họa**. IdP phải thực sự đăng ký SP entityID/ACS và cấp metadata tin cậy. Property names có thể thay đổi theo Spring Boot version; đối chiếu bản tài liệu chính xác của dự án. **Cấu hình này chỉ cho biết SP tin IdP nào**, không phải một chính sách "chặn unsolicited" hoàn chỉnh.

### 8.2. Java 17+ SecurityFilterChain cho SAML login

Tệp `src/main/java/com/example/saml/SamlSpApplication.java` (chạy trong một project Spring Boot Servlet có dependency phù hợp):

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlSpApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlSpApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML SP demo";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }
}
~~~

Đây là **mã Java đầy đủ của class ứng dụng**, nhưng **không thể chạy bằng `javac` thuần** vì cần Spring Boot/Security classpath, BOM và một IdP đã đăng ký. Với project Maven có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Khi server đã chạy thành công, `GET /` trả `SAML SP demo`. `GET /private` cần xác thực; kết quả redirect, cookie, username và log phụ thuộc IdP/registration/cấu hình thực tế, không có stdout giả định.

**Quan trọng:** Class cấu hình trên **không thực thi chính sách chỉ nhận solicited** và cũng không đảm bảo có replay cache mở rộng phù hợp mọi production topology. Đây là baseline; trước go-live phải thực hiện kiểm thử theo mục 12 và áp dụng policy/extension point được phiên bản thực tế hỗ trợ.

### 8.3. Cách tiếp cận kiểm soát unsolicited

Nếu sản phẩm yêu cầu **chỉ SP-initiated**, thiết kế hành vi mục tiêu như sau:

~~~text
Nhận POST tại ACS
  |
  +-- Resolve registration / kiểm issuer + signature + conditions
  |
  +-- Response có InResponseTo?
  |       |
  |       +-- Có -> chỉ chấp nhận nếu có request ID đang chờ
  |                 gắn đúng browser/session và ràng buộc hợp lệ
  |
  +-- Response không có InResponseTo?
          |
          +-- Policy cho phép unsolicited với IdP này?
                  |
                  +-- Không -> từ chối / đưa về SP start-login
                  |
                  +-- Có -> kiểm mọi điều kiện SAML + replay +
                           RelayState/session/account-switch policy
                           rồi mới cân nhắc tạo phiên
~~~

Sơ đồ là **security requirement**, không phải code pipeline API bảo đảm chính xác thứ tự callback của mọi Spring Security release. Khi tùy biến, chọn extension point mà tài liệu phiên bản đang dùng hỗ trợ (ví dụ authentication converter/provider response validator/handler hoặc integration gateway), kiểm signature trước khi dùng dữ liệu chưa tin cậy, và duy trì toàn bộ validation mặc định. Không thay provider thành parser tự viết chỉ để đọc `InResponseTo`.

**Điểm khác biệt khi xử lý lỗi:** Một response **có** `InResponseTo` nhưng SP không còn request tương ứng **không được chuyển sang nhánh unsolicited**. Nó có claim rằng phản hồi một request cụ thể; nếu request ID sai/mất/cross-session thì fail an toàn.

### 8.4. Request repository và session trong SP-initiated

Khi SP tạo `AuthnRequest`, Spring Security cần nơi lưu/khôi phục request để liên kết sau callback. Có thể là HTTP session hoặc một repository do ứng dụng cung cấp, tùy phiên bản/config. Cần kiểm:

- Browser có giữ **cookie phiên** qua redirect/POST từ IdP không (SameSite, Secure, domain).
- Sau reverse proxy, SP có nhận đúng scheme/host/path public không.
- Trong deployment nhiều instances, request state có được dùng lại đúng instance/chung storage không.
- Có chống session fixation và xử lý nhiều tab/callback đến muộn không.
- Việc hết hạn hoặc mất state trả lỗi đúng; **không tắt correlation** chỉ để "đăng nhập chạy".

Đây là lỗi khác với unsolicited Response hợp lệ theo profile: SP-initiated thất bại do thiếu state thì cần sửa cookie/repository/clock/proxy.

## 9. Java 17 độc lập: mô phỏng quyết định về request correlation

Chương trình dưới đây minh họa **quy tắc policy ở mức khái niệm**. Nó giả định chữ ký, issuer, audience, recipient, thời hạn và replay **đã được thư viện SAML chuyên dụng xác minh** và **không phải SAML validator**. Không dùng nó để thay OpenSAML trong production.

Tệp `SamlInitiationPolicyDemo.java`:

~~~java
public class SamlInitiationPolicyDemo {

    static String decide(
            boolean samlValidated,
            boolean responseHasInResponseTo,
            boolean matchingPendingRequestForBrowser,
            boolean allowUnsolicited) {

        if (!samlValidated) {
            return "REJECT: invalid SAML";
        }

        if (responseHasInResponseTo) {
            if (matchingPendingRequestForBrowser) {
                return "ACCEPT: correlated request";
            }
            return "REJECT: missing browser request";
        }

        if (!allowUnsolicited) {
            return "REJECT: unsolicited disabled";
        }

        return "REVIEW: unsolicited policy checks";
    }

    public static void main(String[] args) {
        System.out.println(decide(true, true, true, false));
        System.out.println(decide(true, true, false, true));
        System.out.println(decide(true, false, false, false));
        System.out.println(decide(true, false, false, true));
        System.out.println(decide(false, false, false, true));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac SamlInitiationPolicyDemo.java
java SamlInitiationPolicyDemo
~~~

Stdout chính xác:

~~~text
ACCEPT: correlated request
REJECT: missing browser request
REJECT: unsolicited disabled
REVIEW: unsolicited policy checks
REJECT: invalid SAML
~~~

**Giải thích từng case:**

1. SAML đã được xác minh, có `InResponseTo` và pending request của đúng browser → correlation đạt.
2. Response khai `InResponseTo` nhưng SP không có request của browser dù policy cho phép unsolicited → **vẫn từ chối**, không fallback.
3. Response không khai `InResponseTo`, policy không cho unsolicited → từ chối.
4. Response không khai `InResponseTo`, policy cho unsolicited → mới chỉ **đủ điều kiện xem xét**, còn bắt buộc kiểm Replay/RelayState/session/account policy.
5. SAML không qua signature/condition validation → từ chối bất kể có hay không có request.

Việc cố tình trả `REVIEW` ở case 4 giúp tránh nhầm rằng chỉ bật flag `allowUnsolicited` là đã giải quyết mọi rủi ro. Đây là mã minh họa deterministic, **không có XML parser, certificate, request repository hay HTTP handler**.

## 10. Ví dụ RelayState: điều hướng nội bộ sau IdP-initiated login

Giả sử IdP portal có ba nút "Dashboard", "Reports", "Account". Không nên để IdP gửi một URL bất kỳ rồi SP redirect thẳng. Một thỏa thuận an toàn hơn:

| Giá trị RelayState | Đích hợp lệ sau khi login |
|---|---|
| `dashboard` | `/dashboard` |
| `reports` | `/reports` |
| `account` | `/account` |
| trống/không nhận diện | `/home` |

Điều kiện quan trọng: ánh xạ phải do **SP** định nghĩa; chỉ dùng RelayState làm chỉ dẫn điều hướng **sau khi SAML đã được xác thực**, không dùng để chọn account/role/issuer. Nếu cần redirect sang miền bên ngoài, phải có allowlist URL chính xác và quy tắc chuẩn hóa chặt, bao gồm scheme, port, hostname, path và các biến thể encoding.

Tránh các cách xử lý nguy hiểm như:

~~~java
// Ví dụ KHÔNG AN TOÀN: chỉ minh họa anti-pattern.
response.sendRedirect(request.getParameter("RelayState"));
~~~

Dòng trên không tự kiểm miền đích, dễ trở thành open redirect. Cách triển khai thực sẽ cần logic allowlist và xử lý ngữ cảnh đúng của Spring Security, chứ không lấy đoạn anti-pattern này làm code chạy.

## 11. Bảng kịch bản xử lý: không được bỏ qua kiểm tra nào?

| Trường hợp | `InResponseTo` | Tình trạng xác thực | Kỳ vọng của SP |
|---|---|---|---|
| SP-initiated đúng browser và request ID | Có, khớp | Chữ ký/conditions hợp lệ | Cho phép theo session, role và policy |
| SP-initiated request ID sai | Có, không khớp | Chữ ký hợp lệ | **Từ chối** vì thiếu correlation |
| SP-initiated browser mất cookie/session | Có nhưng không còn request trong phiên | Chữ ký hợp lệ | **Từ chối**, sửa session/cookie |
| IdP-initiated, policy cấm | Không | Chữ ký hợp lệ | **Từ chối** và hướng người dùng bắt đầu ở SP |
| IdP-initiated, policy cho phép | Không | Chữ ký/conditions/replay hợp lệ | Xem xét chấp nhận theo ràng buộc bổ sung, biết rõ rủi ro login CSRF |
| IdP-initiated nhưng Response có `InResponseTo` | Có | Có thể ký hợp lệ | Không hợp lệ với hình thức unsolicited theo OASIS |
| IdP-initiated nhưng bearer confirmation có `InResponseTo` | Có tại `SubjectConfirmationData` | Có thể ký hợp lệ | Không hợp lệ với unsolicited bearer confirmation |
| IdP-initiated sai issuer/cert | Không | Không xác thực được | **Từ chối** |
| IdP-initiated sai `Audience` | Không | Chữ ký hợp lệ | **Từ chối** |
| IdP-initiated sai `Recipient`/ACS | Không | Chữ ký hợp lệ | **Từ chối** |
| IdP-initiated hết hạn | Không | Chữ ký hợp lệ | **Từ chối** |
| IdP-initiated assertion ID đã dùng | Không | Chữ ký hợp lệ | **Từ chối replay** |
| IdP-initiated RelayState trỏ domain ngoài chưa duyệt | Không | Chữ ký hợp lệ | Không redirect ra ngoài; default landing hoặc từ chối |
| IdP-initiated claim role admin từ issuer không được phép | Không | Claim không đủ policy | Không cấp quyền; kiểm issuer/role mapping |
| IdP-initiated khi SP đã login user khác | Không | Chữ ký hợp lệ | Theo policy phải xử lý account switching, không silent replace tùy tiện |

Các case "chữ ký hợp lệ" **chưa đủ** để chứng minh quyền được cấp. Trong ứng dụng có yêu cầu bảo mật cao, policy có thể chọn luôn từ chối unsolicited để giữ đầy đủ request correlation.

## 12. Test tích hợp với Spring Security và IdP thực

### 12.1. Positive tests

1. **SP-initiated baseline:** browser chưa đăng nhập vào trang cần bảo vệ, SP phát `AuthnRequest`; IdP trả `Response.InResponseTo` trỏ đúng ID và bearer confirmation phù hợp; SP chỉ tạo phiên sau mọi kiểm tra.
2. **IdP portal app tile:** khi policy thật sự cho phép, browser vào portal IdP rồi click tile; IdP phát response **không có `InResponseTo`** ở cả Response và bearer confirmation; SP nhận POST đúng ACS.
3. **Issuer/registration mapping:** kiểm đúng IdP entityID, signing cert và SP Audience; chạy với từng tenant được phép.
4. **Default landing page:** IdP không gửi RelayState → SP điều hướng đến một URL nội bộ an toàn.
5. **Allowed RelayState:** giá trị định danh nội bộ đã thỏa thuận → chuyển đúng trang sau khi xác minh SAML.
6. **Role/account checks:** user được IdP gán app nhưng thiếu role nội bộ vẫn không truy cập tài nguyên bị hạn chế.
7. **Replay cache phân tán:** cùng assertion ID không được dùng ở hai node khi hệ thống có nhiều replicas.

### 12.2. Negative tests — bắt buộc

| Bài test | Kết quả mong muốn |
|---|---|
| Policy chỉ SP-initiated, gửi unsolicited có chữ ký hợp lệ | SP **từ chối** vì thiếu request correlation |
| Response có `InResponseTo` ngẫu nhiên | SP **từ chối**, không fallback unsolicited |
| Có request ID tồn tại nhưng thuộc **browser/session khác** | SP **từ chối** |
| Response thiếu `InResponseTo`, có bearer confirmation chứa `InResponseTo` | SP **từ chối** theo unsolicited profile |
| Chữ ký sai hoặc cert thuộc IdP không tin cậy | SP **từ chối** |
| Assertion signature được wrap/Reference không trỏ node đang dùng | SP **từ chối** |
| Sai issuer/audience/recipient/destination | SP **từ chối** |
| Expired/not-before invalid hoặc clock sai vượt skew | SP **từ chối** |
| Replay Response/Assertion lần hai | SP **từ chối** |
| RelayState là URL miền attacker hoặc `javascript:` | SP không redirect đến URL đó |
| Có sẵn session user A, response định danh user B | Xử lý theo account-switch policy; không silent confusion |
| Thay group/role từ payload chưa xác minh | Không được cấp authority |
| IdP chưa assign user vào app | Không phát hành phiên hợp lệ |
| IdP bị gián đoạn/metadata signing cert rotate | Fail an toàn, thông báo rõ và có khả năng khôi phục |

**Cách kiểm đúng:** Không chỉ dùng mock authentication để test business route. Cần tích hợp với **test IdP** có thể phát unsolicited, solicited, wrong-audience, expired, duplicated và các trường hợp không hợp lệ. Với test SAML negative case, không cần tự tạo chữ ký giả rồi kết luận provider đúng; test harness phải xác minh kết quả rejection đã mong muốn.

### 12.3. Test login CSRF thực tế dưới góc phòng thủ

Sử dụng **test accounts và môi trường kiểm thử có quyền**, mô phỏng sự khác biệt:

- Một browser **không có pending AuthnRequest** nhận một unsolicited Response hợp lệ.
- Khi policy cấm unsolicited, browser phải **không tạo phiên**; khi policy cho phép, ghi nhận rõ rủi ro và các bước giảm thiểu.
- Một response hợp lệ về ID/cert nhưng trỏ **NameID khác user đang có session** không được silently đổi danh tính ngoài policy.
- Kiểm log có event loại SSO, issuer, registration, lý do lỗi, session correlation status và assertion ID dạng hash khi cần; không log raw Base64 response/PII.

**Phân biệt kết quả:** "Replay bị từ chối" không chứng minh đã chặn **login CSRF lần đầu**. "Signature validation thành công" không chứng minh browser đã tự phát AuthnRequest.

## 13. Logging, metrics và vận hành

Nên quan sát những sự kiện có cấu trúc:

- `saml.login.initiation=sp|idp` dựa trên phân loại đã xác minh.
- `saml.login.result=success|failure` và category lỗi: signature, issuer, audience, recipient, request correlation, expired, replay, RelayState, account switch.
- `registrationId`, tenant hoặc IdP issuer **được allowlist**.
- Thời gian xử lý, số lượng unsolicited attempts theo IdP, tỷ lệ invalid responses.
- Cảnh báo khi số unsolicited responses tăng đột biến, khi một assertion ID được dùng lại, hoặc khi metadata/certificate đổi.
- Clock/NTP, session repository, cache cluster và IdP availability.

**Giới hạn log:** Tránh log nguyên `SAMLResponse`, JWT, private key, NameID/email/attributes nhạy cảm hoặc cookie. Nếu cần correlation để điều tra, hash ID và áp dụng retention/access control phù hợp.

Khi rollout chính sách **cấm unsolicited**, chuẩn bị UX cho người dùng bấm app tile IdP:

1. Thống nhất với IdP admin việc tile sẽ **đến SP start-login URL** thay vì phát unsolicited assertion.
2. Kiểm SP phát AuthnRequest đúng registration/entityID và lưu session state trước khi chuyển IdP.
3. Kiểm callback solicited thành công trên browser và thiết bị mục tiêu.
4. Giám sát tỷ lệ lỗi request correlation, proxy/cookie và chuyển hướng.
5. Không tắt validation hay mở rộng allowlist toàn bộ IdP khi xảy ra lỗi.

Khi cần duy trì IdP-initiated legacy, lập **tài liệu ngoại lệ** về IdP, ACS, data sensitivity, controls, người phê duyệt, giới hạn thời gian và test lại sau thay đổi.

## 14. Các lỗi hiểu sai phổ biến

**Sai 1: "IdP đã ký nên không thể có login CSRF."** Sai. Một response ký hợp lệ cho **tài khoản attacker** vẫn có thể bị đưa tới browser nạn nhân trước khi được sử dụng; thiếu request/session correlation là vấn đề riêng.

**Sai 2: "Không có InResponseTo là lỗi XML."** Sai đối với IdP-initiated theo profile; unsolicited **phải không có** trường ấy. Nhưng SP có quyền không cho phép unsolicited theo security policy.

**Sai 3: "SP mất AuthnRequest thì coi response là IdP-initiated."** Sai. Response có `InResponseTo` hoặc đã là phản hồi một flow solicited phải được kiểm với pending state; mất session là lỗi cần sửa.

**Sai 4: "Replay cache sẽ giải quyết login CSRF."** Không đủ. Cache ngăn dùng lại sau khi assertion ID đã được ghi nhận; lần đầu gửi sang browser sai có thể vẫn là vấn đề.

**Sai 5: "RelayState đến từ IdP nên chắc chắn là an toàn."** Sai. RelayState có thể không có integrity protection theo binding và không nên dùng làm URL redirect tự do.

**Sai 6: "Spring Security có property supportUnsolicitedResponse ở mọi phiên bản."** Sai. Đây là tên cấu hình trong **Spring Security SAML Extension cũ**; không được mặc nhiên áp dụng vào `spring-security-saml2-service-provider` hiện đại. Kiểm documentation và integration code chính xác.

**Sai 7: "Bỏ kiểm CSRF toàn app là cách cần thiết để SAML POST chạy."** Sai. ACS là callback đặc biệt cần xử lý cross-site POST đúng theo framework, nhưng không nên vô hiệu hóa CSRF protection cho toàn bộ các POST business routes; nếu phải exclude CSRF ở endpoint SAML, chỉ scope chính xác và dựa vào signature/conditions/replay cùng security policy.

**Sai 8: "SSO xong là có quyền admin."** Sai. SAML authentication và application authorization là hai bước độc lập; IdP identity/claims phải được xác minh rồi mapping quyền có kiểm soát.

## 15. Checklist thiết kế và nghiệm thu

- [ ] Đã quyết định **allow/deny unsolicited** theo nghiệp vụ, rủi ro và version/framework hiện tại.
- [ ] Nếu có thể, tile ở IdP chuyển tới **SP-initiated entrypoint**, SP phát AuthnRequest có state.
- [ ] Nếu nhận unsolicited, Response và bearer `SubjectConfirmationData` **không có `InResponseTo`**.
- [ ] Response có `InResponseTo` chỉ được chấp nhận khi **khớp pending request của đúng browser/session**.
- [ ] IdP issuer, trusted signing cert, SP entityID/audience, destination/recipient và binding khớp metadata.
- [ ] Chữ ký bảo vệ đúng Assertion/Response, XML parsing hardened, không signature wrapping.
- [ ] Có cache chống replay bearer assertion dùng chung trong cluster theo cửa sổ hợp lệ.
- [ ] Expiry/NotBefore/SubjectConfirmationData, clock skew và account states được kiểm.
- [ ] RelayState chỉ dùng giá trị được phép, default landing an toàn; không open redirect.
- [ ] Không tự động account linking hoặc silent account switching rủi ro cao.
- [ ] SP kiểm authorization riêng, user IdP được assign và MFA theo yêu cầu.
- [ ] CSRF exceptions (nếu cần cho ACS) chỉ giới hạn đúng SAML callback, không ảnh hưởng business routes.
- [ ] Kiểm positive/negative với test IdP, nhiều browser, nhiều tabs, session hết hạn và nhiều replicas.
- [ ] Có log/metrics/audit mức phù hợp và kế hoạch tắt hỗ trợ unsolicited khi không còn cần thiết.

## 16. Câu hỏi tự kiểm tra

1. **Một unsolicited SAML Response hợp lệ có `InResponseTo` không?** Không. Theo SAML Profiles §4.1.5, Response và bearer SubjectConfirmationData của unsolicited flow không được có trường này.
2. **IdP-initiated có thể đúng chuẩn nhưng vẫn rủi ro không?** Có. Thiếu correlation với browser login intent khiến login CSRF/account confusion vẫn là nguy cơ.
3. **Vì sao signature đúng không đảm bảo login intent?** Signature chứng minh dữ liệu có nguồn và toàn vẹn theo trust; không chứng minh browser nạn nhân đã khởi tạo AuthnRequest.
4. **Một response có `InResponseTo=_a1` nhưng session mất _a1 có thể được chấp nhận như unsolicited không?** Không. Đó là solicited response mất correlation; phải fail an toàn và sửa session flow.
5. **Có thể dùng RelayState làm redirect URL thẳng không?** Không. Phải allowlist/normalize hoặc chuyển qua opaque key sang đích nội bộ tin cậy.
6. **Replay cache ngăn được tất cả login CSRF không?** Không. Nó không bảo đảm người sử dụng **lần đầu tiên** chính là browser đã muốn login.
7. **Làm sao giữ trải nghiệm "click app tile" nhưng vẫn có SP-initiated?** Để tile mở SP login entrypoint; SP sinh AuthnRequest và redirect IdP trong một round-trip mới.
8. **Trong Spring Security hiện đại, có nên copy property `supportUnsolicitedResponse` của Spring SAML Extension cũ?** Không; phải kiểm phiên bản và điểm mở rộng đang dùng.
9. **Login IdP-initiated thành công có đủ cấp quyền vào chức năng nhạy cảm không?** Không; kiểm authorization và có thể yêu cầu step-up/reconfirm theo risk model.
10. **Điều gì nên xuất hiện trong test report?** Initiation mode, validation/trust/correlation/replay, session/account result, RelayState, roles và negative scenarios.

## 17. Nguồn chính thức để tra cứu

- OASIS SAML 2.0 Profiles, **§4.1.3–4.1.5** (Web Browser SSO, bearer confirmation, unsolicited responses): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS **SAML V2.0 Errata 05** (làm rõ ký assertion/Response và cảnh báo CSRF, RelayState): https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- OWASP SAML Security Cheat Sheet, **Unsolicited Response Considerations**: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- Spring Security Servlet SAML2 Login Overview, API/luồng và cách IdP tạo response: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Authenticating SAML2 Responses (validators, converter, authentication provider): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security **SAML Extension** legacy reference (chỉ dùng để so sánh lịch sử, không dùng config cho module mới): https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/

**Nguyên tắc cần nhớ:** IdP-initiated SSO có thể được chuẩn SAML cho phép và IdP ký hợp lệ, nhưng khi SP **không có AuthnRequest đang chờ**, SP thiếu chứng cứ liên hệ response với **ý định đăng nhập của browser**. Nếu nghiệp vụ không bắt buộc, ưu tiên SP-initiated. Nếu bắt buộc hỗ trợ, vẫn kiểm chữ ký/issuer/audience/recipient/time/replay/authority, giới hạn RelayState và xác định rõ rủi ro login CSRF không thể xóa bỏ hoàn toàn chỉ bằng chữ ký.
