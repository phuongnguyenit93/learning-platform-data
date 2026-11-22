# Kiểm thử audience, recipient, destination và InResponseTo không khớp trong Spring Security SAML 2.0

## 1. Mục tiêu và phạm vi bài học

Trong **SAML 2.0 Web Browser Single Sign-On**, một Service Provider (SP), hay **Relying Party (RP)** trong Spring Security, nhận một `samlp:Response` cùng một hoặc nhiều `saml:Assertion` từ Identity Provider (IdP). Ngay cả khi **XML signature được xác minh bằng certificate đáng tin**, SP vẫn phải biết **response thực sự dành cho ai, gửi đến endpoint nào và là kết quả của AuthnRequest nào**.

Bốn kiểm tra thường quyết định tính an toàn của SAML login:

1. **Audience:** `saml:Conditions/saml:AudienceRestriction/saml:Audience` phải cho phép **SP Entity ID được cấu hình**; không được lấy email, registrationId hoặc hostname tùy ý làm thay thế.
2. **Recipient:** `saml:SubjectConfirmationData/@Recipient` của một **bearer SubjectConfirmation hợp lệ** phải trỏ đến **ACS endpoint của SP** trong profile đã thỏa thuận; không dùng assertion dành cho endpoint khác.
3. **Destination:** `samlp:Response/@Destination` phải chỉ đến **đích tiếp nhận SAML Response** đúng theo binding/profile và chính sách triển khai. Trên Web Browser SSO ACS, thường là **URL ACS public thực tế**.
4. **InResponseTo:** với **SP-initiated SSO**, `Response/@InResponseTo` và `SubjectConfirmationData/@InResponseTo` phải phù hợp với **AuthnRequest ID đã lưu** và thuộc đúng **trình duyệt/login transaction**.

Đề bài thuộc nhóm **Kiểm thử SAML2**. Đây là bài học hướng vào **negative/integration security testing**, không phải phần hướng dẫn bỏ qua validator khi một IdP gửi dữ liệu không khớp.

Sau bài học bạn có thể:

- Chỉ đúng vị trí của từng trường trong XML, phân biệt các trường nằm ở **Response / Assertion / SubjectConfirmationData**.
- Tạo bảng expected values theo `RelyingPartyRegistration` và môi trường ingress/proxy.
- Viết test lần lượt thay sai **Audience, Recipient, Destination, Response InResponseTo và Bearer InResponseTo**.
- Đảm bảo dữ liệu fixture vẫn **được ký hợp lệ** để chứng minh lỗi xuất phát từ **policy validation**, không chỉ từ việc XML signature đã bị hỏng.
- Kiểm những góc cạnh: thiếu trường, nhiều AudienceRestrictions, nhiều SubjectConfirmations, HTTP↔HTTPS, host alias, port/path, cross-tenant SP, ID khác, browser session khác và response replay.
- Dùng đúng **Spring Security SAML 2.0 / OpenSAML** với default validators; biết lý do không nên loại bỏ các validator chỉ để SSO “chạy”.
- Kiểm kết quả bảo mật: **không tạo Authentication, không dùng phiên hoặc roles cũ để làm kết quả test giả, không tạo session trái phép**, bất kể HTTP failure handler trả 401, 302 hay 403.
- Chạy một chương trình **Java 17 độc lập** mô phỏng quy tắc binding và 24 ca kiểm thử có stdout xác định, đồng thời hiểu rằng mô hình này **không phải implementation SAML crypto**.

**Nguyên tắc kiểm thử:** *Một SAML Response ký đúng nhưng sai đối tượng hoặc sai giao dịch vẫn phải bị từ chối.* Không suy ra “kiểm Audience/Recipient/… đã hoạt động” chỉ bằng cách sửa XML đã ký và nhìn thấy login fail vì **signature invalid**.

## 2. Chuẩn bị một bộ giá trị cố định cho test

Ví dụ ứng dụng thử nghiệm:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| Spring `registrationId` | `corp` | Khóa nội bộ để chọn cấu hình relying party |
| **SP Entity ID** | `https://portal.example.test/saml2/metadata/corp` | **Audience** mong đợi |
| Public **ACS URL** | `https://portal.example.test/login/saml2/sso/corp` | **Recipient/Destination** mong đợi khi ACS nhận Web Browser SSO POST |
| **IdP Entity ID** | `https://idp.example.test/metadata` | Issuer mà SP tin cậy |
| Test browser session | `browser-A` | Ràng buộc pending AuthnRequest |
| AuthnRequest ID | `_req_a` | Giá trị chính xác được SP phát và lưu |
| Response ID | `resp-_req_a` | Ví dụ response ID duy nhất |
| Assertion ID | `assert-_req_a` | Ví dụ assertion ID duy nhất |
| Current time test | `2026-01-01T12:00:00Z` | Mốc cố định cho lifetime tests |
| Bearer expiry | `2026-01-01T12:05:00Z` | `NotOnOrAfter` hợp lệ cho baseline |

**Các URL và ID là dữ liệu giả của môi trường thử nghiệm**, không phải server có thật. SP Entity ID **không bắt buộc là URL có thể GET truy cập**, dù nhiều sản phẩm đặt giống metadata URL. `registrationId=corp` **không tự là SP Entity ID** và cũng không phải IdP issuer.

### 2.1. Vì sao phải đóng băng expected values?

Nếu test tạo assertion sai rồi đồng thời sửa SP configuration để xem nó có đăng nhập hay không, bạn đã đổi **hai biến cùng lúc**, không kiểm đúng regression về binding.

Trước khi chạy:

1. Ghi nhận metadata của RP/IdP ở test environment.
2. Ghi **RelyingPartyRegistration.getEntityId()** / equivalent đã resolve ra giá trị đầy đủ.
3. Ghi **assertionConsumerServiceLocation** đã resolve, scheme/host/port/path công khai.
4. Ghi **issuer IdP** tin cậy và signing certificate của test IdP.
5. Lưu request ID `_req_a` từ một **AuthnRequest SP-initiated thực tế**.
6. Biết session/browser nào đang giữ AuthnRequest repository entry.
7. Cố định thời gian và clock-skew trong test bằng clock/test harness khi có thể.
8. Bảo đảm fixture baseline được ký bởi **test IdP key** có certificate **đã đăng ký trong test RP**, không dùng khóa production.

**Test từng trường bằng cách đổi một trường**, ngoại trừ các test dành riêng cho phối hợp nhiều trường.

## 3. SAML Response và các trường xuất hiện ở đâu?

Một cấu trúc rút gọn, **chỉ minh họa vị trí XML, chưa có chữ ký và không phải fixture có thể đăng nhập**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="resp-_req_a"
    Version="2.0"
    IssueInstant="2026-01-01T12:00:00Z"
    Destination="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_req_a">
  <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="assert-_req_a"
      Version="2.0"
      IssueInstant="2026-01-01T12:00:00Z">
    <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>

    <saml:Subject>
      <saml:NameID>alice@example.test</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://portal.example.test/login/saml2/sso/corp"
            InResponseTo="_req_a"
            NotOnOrAfter="2026-01-01T12:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-01-01T11:59:00Z"
        NotOnOrAfter="2026-01-01T12:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>
          https://portal.example.test/saml2/metadata/corp
        </saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement
        AuthnInstant="2026-01-01T11:59:55Z"/>
  </saml:Assertion>
</samlp:Response>
~~~

Các mốc được chọn để minh họa và không đủ tạo SAML Response hợp lệ: chữ ký/KeyInfo, canonicalization, status/encoding/binding, AuthnContext, Subject/Assertion profile constraints, các trường/format khác vẫn cần đúng trong fixture thật.

**Đừng copy XML này, Base64-encode và kỳ vọng đăng nhập được**. Cần test fixture thực sự được IdP/test signer tạo với đúng XMLDSig và certificate đã tin.

### 3.1. Sơ đồ lớp dữ liệu

~~~text
Response
  @ID
  @Destination                  -> đúng ACS endpoint
  @InResponseTo                 -> AuthnRequest ID của RP
  Issuer                        -> đúng IdP đã đăng ký
  Status
  Assertion
    @ID
    Issuer                      -> đúng issuer/profile
    Subject
      NameID
      SubjectConfirmation Method="bearer"
        SubjectConfirmationData
          @Recipient             -> đúng ACS recipient
          @InResponseTo          -> AuthnRequest ID
          @NotOnOrAfter          -> còn hiệu lực
    Conditions
      AudienceRestriction
        Audience                 -> đúng SP Entity ID
    AuthnStatement
~~~

**Response Destination và SubjectConfirmationData Recipient có thể trùng URL trong Web Browser SSO nhưng là hai trường khác nhau, có tác dụng kiểm khác nhau, nằm ở hai lớp khác nhau.** Test phải đổi từng trường độc lập.

## 4. Audience: assertion này dành cho SP nào?

Trong SAML Core, `AudienceRestriction` là một condition ràng buộc những relying parties được phép dùng assertion. Trong ví dụ:

~~~xml
<saml:AudienceRestriction>
  <saml:Audience>
    https://portal.example.test/saml2/metadata/corp
  </saml:Audience>
</saml:AudienceRestriction>
~~~

**Giá trị so khớp là SP Entity ID được cấu hình**, không phải:

- `registrationId` như `corp`;
- URL của IdP;
- URL login page;
- path API `/reports`;
- `Recipient`/ACS URL (trừ trường hợp entityId tình cờ được cấu hình giống ACS);
- hostname chung;
- email NameID của người dùng.

### 4.1. Negative test: Audience của SP khác

Fixture hợp lệ về chữ ký nhưng có:

~~~xml
<saml:Audience>
  https://other.example.test/saml2/metadata/other
</saml:Audience>
~~~

Kỳ vọng: assertion **không được chấp nhận làm Authentication** tại Portal, dù issuer và signature đúng.

**Đừng sửa Audience sau khi ký**; thay Audience **trước khi ký lại bằng test key** để test thực sự đến AudienceRestriction validator. Nếu sửa sau ký, lỗi thường là invalid signature, không chứng minh Audience được kiểm.

### 4.2. Nhiều Audience trong cùng một AudienceRestriction

SAML Core cho phép nhiều Audience trong một restriction. Ý nghĩa thông thường: **ít nhất một Audience phù hợp** trong **một** `AudienceRestriction`.

Ví dụ:

~~~xml
<saml:AudienceRestriction>
  <saml:Audience>
    https://portal.example.test/saml2/metadata/corp
  </saml:Audience>
  <saml:Audience>
    https://other.example.test/sp
  </saml:Audience>
</saml:AudienceRestriction>
~~~

Một assertion như vậy **không tự sai** chỉ vì có một Audience khác đi kèm, nếu SP Entity ID có trong tập được phép và các điều kiện khác hợp lệ. Bộ test không được áp quy tắc “mọi Audience đều phải bằng entityId hiện tại” khi SAML profile cho phép nhiều audience.

Ngược lại, nhiều **AudienceRestriction** là các điều kiện áp đồng thời: nếu một restriction không có SP hiện tại thì assertion **không đáp ứng đầy đủ** tập conditions.

~~~xml
<saml:Conditions>
  <saml:AudienceRestriction>
    <saml:Audience>https://portal.example.test/saml2/metadata/corp</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>https://other.example.test/sp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

**Expected:** reject. Đừng viết test sai rằng cứ có một Audience hợp lệ ở bất kỳ restriction nào thì các restriction khác được bỏ qua.

### 4.3. Các biến thể Audience cần test

| Trường hợp | Giá trị | Kỳ vọng |
| --- | --- | --- |
| Baseline | Đúng `RP Entity ID` | PASS nếu toàn response hợp lệ |
| SP khác | `https://other.example.test/sp` | FAIL |
| Thiếu restriction khi profile yêu cầu | Không có AudienceRestriction | FAIL theo test security policy |
| Restriction rỗng | Không có Audience | FAIL |
| Khác path | `.../metadata/corp2` | FAIL |
| Khác scheme | `http://portal...` thay HTTPS | FAIL |
| Khác chữ hoa/thường | URL identity khác đúng value đã đăng ký | FAIL nếu identity không trùng chính xác |
| Thêm slash | `.../corp/` | FAIL nếu không phải entityId được đăng ký |
| Prefix attack | `.../corp.evil.example` | FAIL |
| Cùng restriction có cả đúng và một giá trị khác | Có RP entityId hợp lệ | Không reject chỉ vì có giá trị khác |
| Hai restrictions, một không chứa RP | Mỗi restriction phải thỏa | FAIL |
| EntityId SP ở tenant khác | `.../metadata/tenant-b` | FAIL |

**So sánh Audience theo xác thực entity identity, không dùng `startsWith(...)`, `contains("portal")` hoặc `endsWith("corp")`.** Cần tránh normalization tùy tiện làm hai entity identifiers khác nhau bị coi là một.

## 5. Recipient: bearer subject này được đưa đến ACS nào?

`Recipient` nằm trong:

~~~xml
<saml:Subject>
  <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
        Recipient="https://portal.example.test/login/saml2/sso/corp"
        InResponseTo="_req_a"
        NotOnOrAfter="2026-01-01T12:05:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
~~~

Trong **SAML Web Browser SSO bearer profile**, Recipient ràng buộc **ACS endpoint mà bearer assertion được trình**. SAML Core định nghĩa trường có thể tùy chọn ở schema chung, nhưng **Web Browser SSO bearer profile** áp những yêu cầu mạnh hơn. Vì thế không suy từ XML Schema rằng có thể bỏ Recipient và vẫn dùng assertion để login.

### 5.1. Wrong Recipient với chữ ký vẫn đúng

Ví dụ đổi thành:

~~~xml
Recipient="https://other.example.test/saml/acs"
~~~

Response `Destination` và Audience vẫn đúng Portal, nhưng bearer recipient sai.

**Expected:** không có bearer SubjectConfirmation hợp lệ cho Portal → **FAIL authentication**. Không chấp nhận vì “response đã POST đúng URL” hoặc “Audience đúng” khi **Recipient không trùng ACS**.

### 5.2. Các bẫy so URL

| Sai khác | Vì sao quan trọng? |
| --- | --- |
| `https://portal.example.test/login/saml2/sso/corp/` | Slash cuối khác ACS |
| `https://portal.example.test/login/saml2/sso/corp2` | Khác registration/path |
| `http://portal.example.test/...` | HTTP downgrade khác URI/transport |
| `https://portal.example.test:8443/...` | Port khác public ACS |
| `https://portal.example.test.evil.test/...` | Host prefix attack |
| `https://portal.example.test/login/saml2/sso/corp?x=1` | Query khác registered endpoint |
| `https://other.example.test/login/saml2/sso/corp` | Host/tenant khác |
| Empty hoặc missing Recipient | Không đáp ứng bearer profile |

Ở ingress hoặc load balancer, **internal URL** có thể là `http://app-node:8080`, trong khi **public ACS** là `https://portal.example.test/login/saml2/sso/corp`. Cần cấu hình trusted forwarded headers và `RelyingPartyRegistration.assertionConsumerServiceLocation` theo đúng public URL. **Không tắt Recipient validation** chỉ để sửa lỗi host/scheme.

### 5.3. Nhiều SubjectConfirmations: không reject sai

Một assertion có thể có **nhiều `SubjectConfirmation`**. Theo SAML Web Browser SSO, nếu có **ít nhất một bearer confirmation đáp ứng đầy đủ profile**, subject confirmation có thể thành công (các yêu cầu assertions khác vẫn phải đúng).

Ví dụ một confirmation sai Recipient, một confirmation đúng Recipient/InResponseTo/timing, thì **không tự fail** chỉ vì confirmation thứ nhất sai. Bộ kiểm thử cần:

- Với ca **tất cả confirmations sai Recipient**: FAIL.
- Với ca **có ít nhất một bearer confirmation thực sự hợp lệ**: PASS **nếu toàn bộ kiểm tra khác hợp lệ**.
- Không trộn một Recipient đúng của confirmation A với một InResponseTo đúng của confirmation B để tạo một “confirmation tổng hợp” không tồn tại. **Cùng một confirmation** phải thỏa mọi điều kiện.

Một test sai thường viết: `any recipient == expected` **AND** `any InResponseTo == expected`. Điều này có thể cho PASS từ **hai confirmations khác nhau**, là nguy cơ bypass. Đúng hơn: `any confirmation where recipient AND requestId AND time AND method all valid`.

## 6. Destination: Response được gửi đến endpoint nào?

`Destination` nằm ở **Response**:

~~~xml
<samlp:Response
    Destination="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_req_a">
~~~

Nó ràng buộc **nơi nhận message** theo profile/binding và cấu hình SP. Đừng nhầm với `Destination` của **AuthnRequest** gửi **từ SP đến IdP**: hai message ngược chiều, target khác nhau.

**Trong bài test này**, chính sách ACS là: **Response Destination bắt buộc và phải bằng public ACS URI chính xác**. Việc một SAML XML schema cho phép thuộc tính Destination vắng mặt trong một số ngữ cảnh **không tự là cho phép ứng dụng bỏ kiểm ràng buộc đích**. Test cần xác định policy/binding đã thỏa thuận với IdP.

### 6.1. Sai Destination nhưng Recipient đúng

Ví dụ:

~~~text
Response Destination:
  https://other.example.test/saml/acs

Assertion SubjectConfirmationData Recipient:
  https://portal.example.test/login/saml2/sso/corp
~~~

Kỳ vọng: **FAIL**. Recipient đúng không chữa được Destination sai.

### 6.2. Destination đúng nhưng Recipient sai

Ví dụ:

~~~text
Response Destination:
  https://portal.example.test/login/saml2/sso/corp

Bearer Recipient:
  https://other.example.test/saml/acs
~~~

Kỳ vọng: **FAIL**. Destination đúng không chữa được Recipient sai.

### 6.3. Thiếu Destination

Một số profile hoặc trường hợp binding có quy tắc tùy thuộc message được ký/chính sách giao thức. Không khẳng định “mọi SAML Response thiếu Destination đều sai XML schema”. Tuy nhiên với **Web Browser SSO ACS policy test yêu cầu Destination**, thiếu trường này phải **FAIL**.

Nếu app hiện tại mặc định chấp nhận Response thiếu Destination theo một profile/phiên bản thư viện khác, đó là một quyết định an toàn cần được đánh giá và có test riêng; **không viết lại expected là PASS chỉ vì framework mặc định đang PASS**. Xác định yêu cầu OASIS Profile, IdP contract, chữ ký và compliance/security policy rồi cấu hình check bổ sung khi cần.

### 6.4. Không chỉ so servlet request URL tự ráp

Trong môi trường reverse proxy:

~~~text
Browser -> https://portal.example.test/login/saml2/sso/corp
                  |
                  v
Ingress: terminate TLS, forward trusted headers
                  |
                  v
App node -> http://app-node:8080/login/saml2/sso/corp
~~~

Ứng dụng phải hiểu **ACS public endpoint** đã đăng ký chứ không lấy nguyên `request.getRequestURL()` nội bộ rồi kết luận IdP gửi sai. Thiết kế:

- Cấu hình `assertionConsumerServiceLocation` cố định hoặc resolvable placeholders một cách nhất quán.
- Đảm bảo chỉ ingress **đáng tin** được gửi `Forwarded` / `X-Forwarded-*`; chặn client spoof.
- Không tự cho mọi host/scheme/path “được chấp nhận” theo `Host` header do attacker cung cấp.
- Kiểm integration với LB/proxy thực, không chỉ local port 8080.
- Dùng exact matching phù hợp registered ACS/URI, không dùng `startsWith`.

## 7. InResponseTo: liên kết Response với AuthnRequest đã khởi tạo

**SP-initiated SSO**:

~~~text
Browser A
  -> SP /saml2/authenticate/corp
  -> tạo <AuthnRequest ID="_req_a" ...>
  -> lưu (requestId=_req_a, browserSession=A, registrationId=corp,
          relayState, timestamp, expected IdP)
  -> redirect/POST AuthnRequest tới IdP

IdP
  -> <Response InResponseTo="_req_a">
       <SubjectConfirmationData InResponseTo="_req_a" .../>
     </Response>
  -> browser POST SAMLResponse tới ACS

SP
  -> load request từ repository của browser A
  -> compare Response InResponseTo và bearer InResponseTo với ID _req_a
  -> kiểm issuer/signature/destination/audience/recipient/time...
  -> xác thực user và quản lý one-time use/replay
~~~

Hai trường cần phân biệt:

1. **`Response/@InResponseTo`**: protocol-level correlation với AuthnRequest.
2. **`SubjectConfirmationData/@InResponseTo`**: ràng buộc subject bearer confirmation với AuthnRequest trong Web Browser SSO.

**Không chỉ kiểm một trường** trong khi bỏ qua trường còn lại. Spring Security hiện đại dùng **ResponseValidator** cho Response-level và **BearerSubjectConfirmationValidator** / assertion validation cho bearer-level checks. Trong test phải thay sai từng trường riêng để biết lớp nào bị bypass.

### 7.1. Negative test Response InResponseTo sai

~~~xml
<samlp:Response InResponseTo="_req_other">
~~~

Trong khi browser A có pending request `_req_a`, bearer InResponseTo vẫn `_req_a`.

Kỳ vọng: **FAIL**. Không chỉ tin bearer ID hoặc vì assertion signature hợp lệ.

### 7.2. Negative test Bearer InResponseTo sai

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_req_other"
    NotOnOrAfter="2026-01-01T12:05:00Z"/>
~~~

Response InResponseTo vẫn `_req_a`.

Kỳ vọng: nếu **không có bearer confirmation hợp lệ khác**, **FAIL**. Không chỉ tin Response-level ID.

### 7.3. Mất pending AuthnRequest hoặc sai browser

Những trường hợp không thể chấp nhận trong **SP-initiated-only policy**:

- `InResponseTo` bằng `_req_a` nhưng HttpSession A **không có pending request đó**.
- Browser B mang response của browser A, dù `InResponseTo=_req_a`, do attacker copy.
- Request đã được dùng thành công, response cũ được POST lại.
- Request thuộc `corp` nhưng callback resolve sang registrationId tenant/provider khác.
- Pending request hết TTL hoặc đã bị hủy khi logout/account switch.
- Browser A dùng state/RelayState của giao dịch khác để lookup toàn cục.
- `InResponseTo` missing/blank trong một flow mà SP vừa phát AuthnRequest.
- Response-level và bearer-level InResponseTo **khác nhau**, không có proof nhất quán.

Spring Security dùng `HttpSessionSaml2AuthenticationRequestRepository` để lưu request trong HttpSession theo mặc định trong phiên bản hiện hành. Nó tạo **browser binding tự nhiên**, điều mà một global cache chỉ lookup request bằng `RelayState` hoặc `InResponseTo` không tự cung cấp. Nếu thay repository bằng Redis/cache, cần bảo vệ **browser-session binding, TTL, atomic consume và issuer/registration association**.

### 7.4. IdP-initiated / unsolicited SSO là trường hợp riêng

Có những triển khai IdP-initiated SSO, người dùng nhấn application tile tại IdP và IdP POST response không tham chiếu AuthnRequest do SP tạo.

**Không mặc nhiên mọi `InResponseTo` thiếu đều sai trên mọi SAML deployment.** Nhưng:

- Nếu chính sách ứng dụng **SP-initiated-only**, thiếu request/InResponseTo → **FAIL**.
- Nếu chủ động cho **IdP-initiated**, phải có profile/policy riêng, IdP registration allowlist, signature, issuer, audience, recipient, destination, time, assertion replay và session/account-switch safeguards.
- Không “fallback sang unsolicited” tự động chỉ vì `InResponseTo` sai.
- Theo Web Browser SSO unsolicited profile, không được gắn một InResponseTo giả để làm ra vẻ có AuthnRequest.
- Không dùng `RelayState` như chứng cứ browser này đã khởi tạo giao dịch, trừ khi nó nằm trong cơ chế session-bound được thiết kế và kiểm thực sự.
- Một response hợp lệ của IdP cho **tài khoản Mallory** vẫn không nên tự thay session Alice nếu không có approved account-switch policy.

Trong bài test này, **baseline là SP-initiated-only** và mọi unsolicited response phải bị từ chối.

## 8. Yêu cầu signature: tránh negative test sai mục tiêu

### 8.1. Vì sao sửa raw XML rồi Base64-encode là không đủ?

XMLDSig bảo vệ các phần XML được ký. Nếu bạn:

1. Lấy SAML Response hợp lệ từ IdP test;
2. Sửa `<saml:Audience>` hoặc `@Recipient`, `@Destination`, `@InResponseTo`;
3. Giữ nguyên `ds:Signature`;
4. Base64 lại và POST ACS;

thì validator có thể reject **vì XML signature digest/signature invalid**, ngay cả khi không kiểm Audience/Recipient/Destination/InResponseTo. Đó là false confidence về security coverage.

### 8.2. Cách tạo fixture đúng

Dùng **test-only IdP/signing key** và một library đã biết đúng cho SAML signing:

~~~text
A. Generate baseline from test IdP
   - registered test IdP issuer
   - valid Response/Assertion signature as configured
   - valid timing/NameID/AuthnStatement
   - expected audience, recipient, destination, InResponseTo
   - pending AuthnRequest for the browser

B. Clone fixture object BEFORE signing
   - change EXACTLY ONE tested field

C. Serialize, canonicalize and sign again with TEST IdP signing credential
   - preserve proper signed element and XMLDSig Reference
   - retain trusted test certificate in RP

D. POST re-signed fixture to actual Spring ACS
   - same browser HttpSession/AuthnRequest repository where appropriate

E. Assert:
   - SAML protocol/security validation rejects the named field
   - NO new Saml2Authentication/authorized session
   - NO success handler/business protected content
   - reason/evidence indicates expected validation condition
~~~

**Không sử dụng khóa ký production, không commit private key thật và không tạo chữ ký giả bằng cách đổi một boolean trong integration test.** Với test self-signed cert, certificate phải được cấu hình là trusted **chỉ tại test RP**, tách biệt production trust store.

### 8.3. Vị trí chữ ký cũng quan trọng

SAML cho phép signatures ở `Response`, `Assertion` hoặc cả hai theo metadata/profile. Một thay đổi ở thuộc tính `Destination` có thể làm hỏng chữ ký nếu Response được ký, nhưng **không nhất thiết** làm hỏng chữ ký Assertion nếu chỉ Assertion được ký. Vì vậy không chỉ dựa vào signature failure.

Test nên có ít nhất:

- **Signed Response** cấu hình như IdP thật, sai Destination nhưng **re-sign Response**.
- **Signed Assertion** cấu hình như IdP thật, sai Audience/Recipient/confirmation InResponseTo nhưng **re-sign Assertion**.
- Nếu production cho cả hai kiểu, thêm **signature placement variants**, xác nhận tầng validation luôn chạy.
- Test riêng unsigned/wrong cert/wrapping/duplicate IDs; không gộp với four-binding validation.
- Với encrypted assertion, decrypt đúng rồi validate; không tự sửa ciphertext sau encryption và coi đó là test Audience.

### 8.4. Đọc nguyên nhân validation, không chỉ HTTP status

A negative test đủ sức chứng minh phải trả lời:

- Fixture có đến **ResponseValidator/AssertionValidator** không?
- XML signature đã pass ở mức phù hợp hay fail sớm?
- Field nào thực sự khác expected value?
- `AuthenticationManager` có throw/return failure đúng không?
- `SecurityContext` của browser mới có được tạo không?
- Nếu browser đã có phiên trước đó, test có đang đọc **old Authentication** rồi hiểu nhầm đó là login success không?
- Error code/trace có được ghi **không lộ raw SAMLResponse** không?

HTTP failure handler có thể redirect `302 /login?error`; không phải lúc nào fail cũng là 401/403. **Kiểm trạng thái authenticated/session quan trọng hơn mã status đơn lẻ**.

## 9. Validator nào trong Spring Security kiểm trường nào?

Ở Spring Security SAML 2.0 hiện đại (tài liệu 7.x):

~~~text
Saml2WebSsoAuthenticationRequestFilter
  -> tạo AuthnRequest
  -> Saml2AuthenticationRequestRepository (mặc định HttpSession)

Browser + IdP
  -> POST SAMLResponse + RelayState tới ACS

Saml2WebSsoAuthenticationFilter
  -> Saml2AuthenticationTokenConverter
  -> AuthenticationManager
  -> OpenSaml5AuthenticationProvider
       -> validate trusted signatures / decryption as configured
       -> ResponseValidator
            IssuerValidator
            DestinationValidator
            InResponseToValidator / response request correlation
       -> AssertionValidator
            AudienceRestrictionValidator
            BearerSubjectConfirmationValidator
            Conditions / timing / restrictions
       -> convert to Saml2Authentication

SecurityContextRepository / authorization
~~~

**Tên lớp/đường validate có thể khác giữa Spring Security 6.x/OpenSAML 4 và Spring Security 7.x/OpenSAML 5.** Tài liệu Spring 7.x mô tả `OpenSaml5AuthenticationProvider` và `ResponseValidator/AssertionValidator` rõ ràng.

Spring Security docs nói:

- `OpenSaml5AuthenticationProvider` kiểm **Issuer** và **Destination** ở Response validation.
- `Response#InResponseTo` có validator riêng; có thể bị loại bỏ nếu cấu hình **ResponseValidator thay thế thiếu bước đó**.
- Assertion validation mặc định bao gồm **AudienceRestriction** và **SubjectConfirmation**, trong đó bearer confirmation xử lý các ràng buộc `Recipient/InResponseTo`.
- Custom validation nên **giữ các defaults**, rồi bổ sung kiểm tra. **Không thay cả validator bằng một subset không đầy đủ**.

### 9.1. Cấu hình ứng dụng test với mặc định an toàn

Ví dụ Spring Boot 3.x/4.x và Spring Security Servlet; kiểm version alignment trên project thật:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Bằng Java config:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class Saml2SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **Spring integration snippet**, không phải Java class độc lập chạy chỉ bằng `javac`. Cần `RelyingPartyRegistrationRepository` và IdP metadata, certificate trust, đúng ACS callback và test session. Nếu tự override `AuthenticationManager` hoặc `OpenSaml5AuthenticationProvider`, phải kiểm các default validators còn được áp.

Một cấu hình Boot minh họa (metadata URL giả):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "https://portal.example.test/saml2/metadata/corp"
            assertion-consumer-service-location: "https://portal.example.test/login/saml2/sso/corp"
            assertingparty:
              metadata-uri: "https://idp.example.test/metadata"
~~~

**Không sử dụng endpoint/certificate thật của production cho test mutation.** Cấu hình Boot chính xác theo phiên bản đã ghép Spring Security; tham số bổ sung có thể cần theo metadata/certificate/bindings/SSL. URI public và `registrationId` phải tương ứng với ACS request của test.

### 9.2. Không vô tình loại bỏ InResponseToValidator

Spring docs minh họa rằng bạn có thể thay `ResponseValidator` và chọn subset như Destination và Issuer. Đó là **cơ chế customization**, nhưng nếu loại `InResponseToValidator` khỏi luồng SP-initiated mà không có thay thế tương đương, có thể mở cửa nhận response không liên kết request.

Định hướng đúng:

~~~text
Use default Spring/OpenSAML validators
  + additional project-specific validation
  + additional logging/metrics (redacted)

Do NOT:
  replace defaults with only signature + issuer
  skip AudienceRestriction to accept "legacy IdP"
  skip BearerSubjectConfirmation to fix Recipient errors
  skip Response InResponseTo due to lost HttpSession
  skip Destination due to reverse-proxy host mismatch
~~~

Nếu cần custom validator, dùng API **giữ defaults** (tài liệu Spring mô tả `ResponseValidator.withDefaults(customValidator)`), và chạy lại toàn bộ negative suite. Đừng đánh đồng một getter như `response.getDestination()` với một validator chính sách thật.

### 9.3. Trusted proxy và public ACS

Spring Security docs hỗ trợ placeholders `{baseUrl}`, `{registrationId}`, `{baseScheme}`, `{baseHost}`, `{basePort}` trong SP entityId/ACS; chúng được resolve theo deployment/config.

Nếu gateway chuyển `https://portal.example.test` thành `http://internal:8080`:

- Dùng public ACS ổn định trong metadata/registration.
- Chỉ trust forwarded headers từ reverse proxy được phép; không để client tự định public URL qua Host.
- Test wrong Destination cho **public URI** theo policy, không phải một guessed internal URL.
- Cập nhật IdP metadata/ACS config khi đổi hostname/scheme/path theo change management, **không bỏ Recipient/Destination validation**.

## 10. Test fixture matrix: mỗi trường một biến

Giả sử baseline `RP`, `ACS`, `IDP`, `_req_a` và `browser-A` ở phần 2:

| ID | Trường thay đổi | Fixture được ký lại | Expected |
| --- | --- | --- | --- |
| T00 | Không thay đổi | Baseline hoàn chỉnh | PASS; tạo authenticated session |
| T01 | Audience = `https://other.example.test/sp` | Signature valid | **FAIL** |
| T02 | AudienceRestriction thiếu theo policy | Signature valid | **FAIL** |
| T03 | AudienceRestriction rỗng | Signature valid | **FAIL** |
| T04 | Audience có SP entityId + một audience khác trong cùng restriction | Signature valid | PASS nếu mọi điều kiện khác đúng |
| T05 | Hai AudienceRestrictions; restriction 2 không có SP | Signature valid | **FAIL** |
| T06 | Audience khác path/tenant | Signature valid | **FAIL** |
| T07 | Audience prefix lookalike | Signature valid | **FAIL** |
| T08 | Recipient = ACS của SP khác | Signature valid | **FAIL** |
| T09 | Recipient = đúng ACS + `/evil` | Signature valid | **FAIL** |
| T10 | Recipient thiếu | Signature valid | **FAIL** |
| T11 | Recipient đúng nhưng `NotOnOrAfter` hết hạn | Signature valid | **FAIL** |
| T12 | Hai bearer confirmations, một hoàn toàn hợp lệ | Signature valid | PASS theo profile khi toàn bộ checks khác đúng |
| T13 | Hai bearer confirmations, mỗi cái chỉ đúng một nửa điều kiện | Signature valid | **FAIL** |
| T14 | Destination = ACS của RP khác | Signature valid | **FAIL** |
| T15 | Destination = HTTP thay HTTPS | Signature valid | **FAIL** |
| T16 | Destination thiếu dưới strict ACS policy | Signature valid | **FAIL** |
| T17 | Destination = đúng nhưng Recipient sai | Signature valid | **FAIL** |
| T18 | Recipient = đúng nhưng Destination sai | Signature valid | **FAIL** |
| T19 | Response InResponseTo = `_req_other` | Signature valid | **FAIL** |
| T20 | Response InResponseTo = null | Signature valid | **FAIL** trong SP-initiated-only |
| T21 | Bearer InResponseTo = `_req_other` | Signature valid | **FAIL** nếu không có confirmation hợp lệ khác |
| T22 | Response InResponseTo và Bearer InResponseTo khác nhau | Signature valid | **FAIL** |
| T23 | Request ID tồn tại nhưng nằm trong browser B | Signature valid | **FAIL** ở browser A |
| T24 | Pending AuthnRequest không còn | Signature valid | **FAIL** |
| T25 | AuthnRequest bị dùng/tiêu thụ rồi | Signature valid | **FAIL** replay |
| T26 | Wrong issuer/certificate | Vary as independent test | **FAIL**, tránh nhầm với field test |
| T27 | Assertion/Response replay ID cũ | Signature valid | **FAIL** |
| T28 | RegistrationId của SP khác nhưng cùng IdP | Signature valid | **FAIL** nếu audience/ACS/request binding sai |
| T29 | Clock lệch quá policy | Signature valid | **FAIL** |
| T30 | SAMLResponse đã ký bị sửa hậu ký | Signature invalid | **FAIL** vì signature, KHÔNG tính là proof T01–T22 |
| T31 | IdP-initiated unsolicited response | Signature valid | **FAIL** với SP-initiated-only |
| T32 | RelayState tampered/open redirect | Theo fixture policy | **FAIL** nếu làm sai correlation/redirect allowlist |
| T33 | URL ACS alias/case/trailing slash không được đăng ký | Signature valid | **FAIL** khi không match expected ACS |
| T34 | Cùng NameID ở tenant khác | Signature valid | **FAIL** nếu issuer/audience/registration sai |
| T35 | Session cookie cũ nhưng response của browser khác | Signature valid | **FAIL**, không tạo Account confusion |

**Mỗi test nên nêu rõ nó đang đánh giá Response, Assertion hay bearer confirmation**, và response chỉ được xem là PASS sau khi cả **protocol validation** và **local session policy** hoàn thành.

## 11. Cách thiết lập integration test thật

Một test end-to-end qua Spring Security FilterChain nên:

1. Tạo **test IdP key pair và X.509 certificate** riêng, lưu trong test secrets hoặc controlled fixtures; cấu hình test RP tin certificate đó.
2. Cấu hình `RelyingPartyRegistration` với đúng `entityId`, `assertionConsumerServiceLocation`, IdP issuer, trusted verification certificate.
3. Khởi tạo **SP-initiated AuthnRequest** bằng `GET /saml2/authenticate/corp` qua một browser/MockHttpSession.
4. Lấy **AuthnRequest ID/RelayState** thực tế từ test harness/repository.
5. Dùng OpenSAML/test IdP helper tạo **signed Response** với Assertion và bearer SubjectConfirmation đúng baseline.
6. POST response theo đúng binding và content type, thường `SAMLResponse=Base64(UTF-8 XML)` và `RelayState` nếu có, tới ACS `/login/saml2/sso/corp` với **đúng session/browser**.
7. Assert baseline PASS: tạo `Saml2Authentication` đúng external identity và local authorities.
8. Tạo các mutations **trước khi ký lại**, giữ những trường còn lại như baseline; POST từng fixture với **fresh request/session/response IDs**.
9. Assert từng negative: **không có login success, không có authenticated session mới, không trả protected content**.
10. Test riêng browser đã có login cũ; một response bị reject không được tạo **Authentication mới**. Không suy từ `isAuthenticated()` của **old session** rằng negative response đã login thành công.
11. Test với nhiều browser, hai IdPs/tenants, nhiều replicas hoặc Redis nếu repository không local.
12. Thu reason codes/validator categories trong test logs đã redacted, không log full XML/assertion/token.

### 11.1. MockMvc skeleton: POST vào ACS thật

Đoạn mã **chỉ là integration-test fragment**, không tạo signed response; `signedSamlResponseXml` phải được fixture helper tạo và ký lại **trước khi POST**:

~~~java
String encoded = Base64.getEncoder().encodeToString(
    signedSamlResponseXml.getBytes(StandardCharsets.UTF_8));

MvcResult result = mockMvc.perform(
    post("/login/saml2/sso/corp")
        .session(browserSessionWithAuthnRequest)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("SAMLResponse", encoded)
        .param("RelayState", relayStateFromRequest))
    .andReturn();

// Assert security outcome via session/Authentication and login handler.
// Failure status may be 302, 401, or another configured response.
// Do NOT assert "403" as the only acceptable negative outcome.
~~~

**Imports** (Spring Security Test/MockMvc dependencies required):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
~~~

Có thể cần các Spring test annotations/config để tạo `mockMvc`, `MockHttpSession` và fake trusted test IdP. Nếu ACS được Spring Security miễn kiểm `CsrfFilter` theo filter setup hiện hành, phải đảm bảo **chỉ đúng ACS URL** có exemption; không `csrf.disable()` toàn app.

**Không dùng `SecurityMockMvcRequestPostProcessors.saml2Login()` làm bằng chứng validation**: test post processor có thể dựng một `Saml2Authentication` giả hợp lệ **bỏ qua XML/SAML signature/ResponseValidator/AssertionValidator**. Nó hữu ích để test authorization sau login, nhưng **không chứng minh** Audience/Recipient/Destination/InResponseTo mismatch bị reject.

### 11.2. Bảo toàn expected request trong negative test

Một lỗi test harness:

~~~text
Test A:
  dùng _req_a, POST negative fixture
Test B:
  dùng lại _req_a, POST fixture khác
  nhưng request repo đã bị removed hoặc session bị thay
Test B fail do missing request, không phải wrong Recipient.
~~~

Giải pháp: **mỗi test lập phiên và AuthnRequest mới**, response/assertion IDs mới, test clock rõ, hoặc reset fixture repository có kiểm soát trong test isolation. Không dùng chung state mutable qua các tests làm kết quả phụ thuộc thứ tự.

### 11.3. Phân biệt failure stage

Có thể phân tách test observability:

~~~text
SIGNATURE_INVALID
ISSUER_MISMATCH
DESTINATION_MISMATCH
IN_RESPONSE_TO_MISMATCH
AUDIENCE_MISMATCH
RECIPIENT_MISMATCH
BEARER_EXPIRED
AUTHN_REQUEST_MISSING
BROWSER_SESSION_MISMATCH
ASSERTION_REPLAY
LOCAL_USER_DISABLED
~~~

Đây là **category names do đội test đặt**, không phải error codes tiêu chuẩn bắt buộc mà Spring luôn phát. Exception class/message thay đổi theo Spring/OpenSAML version; nên assert **security outcome** và nếu có instrumentation thì assert reason category đã ổn định, thay vì phụ thuộc từng chữ trong exception string.

## 12. Java 17 chạy độc lập: mô hình binding và negative tests

Chương trình sau **chạy với JDK 17+**, không cần Spring/OpenSAML/KDC/IdP/mạng. Nó mô hình hóa các quy tắc:

- SAML Response đã qua một **trusted signature verifier giả lập**.
- Đúng IdP issuer, Destination, pending AuthnRequest và browser binding.
- Assertion có đúng issuer và đáp ứng **mọi** AudienceRestriction; **OR trong restriction**, **AND giữa các restrictions**.
- Có **ít nhất một bearer SubjectConfirmation** thỏa đồng thời Recipient, InResponseTo và `NotOnOrAfter`.
- Response IDs và Assertion IDs chỉ được dùng một lần; pending request bị consume sau success.
- Wrong/missing Audience, Recipient, Destination, Response/Bearer InResponseTo, sai issuer/signature, wrong browser, expired bearer và replay đều bị reject.

**Giới hạn bảo mật:** `signatureVerified` là **kết quả giả lập đáng tin từ test verifier**, **không phải boolean lấy từ SAML XML, client HTTP header hoặc JSON**. Chương trình **không kiểm XMLDSig, certificate trust, XML parsing, schema, encryption, clock-skew policy đầy đủ, assertion conditions/NameID/subject confirmation method, multi-node replay hay XSW**. Nó **không được dùng làm SAML AuthenticationProvider production**. Để test thực tế hãy dùng OpenSAML/Spring Security test RP và signed fixtures như phần 11.

Tệp **Saml2BindingNegativeTestDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class Saml2BindingNegativeTestDemo {
    static final String RP = "https://portal.example.test/saml2/metadata/corp";
    static final String ACS = "https://portal.example.test/login/saml2/sso/corp";
    static final String IDP = "https://idp.example.test/metadata";
    static final Instant NOW = Instant.parse("2026-01-01T12:00:00Z");

    record Pending(String requestId, String browserId) {}
    record Bearer(String recipient, String inResponseTo,
                  Instant notOnOrAfter) {}
    record Assertion(String id, String issuer,
                     List<Set<String>> audienceRestrictions,
                     List<Bearer> bearerConfirmations) {}
    record Response(String id, String issuer, String destination,
                    String inResponseTo, boolean signatureVerified,
                    Assertion assertion) {}

    static final class Policy {
        final Map<String, Pending> requests = new HashMap<>();
        final Set<String> usedResponses = new HashSet<>();
        final Set<String> usedAssertions = new HashSet<>();

        void start(String requestId, String browserId) {
            requests.put(requestId, new Pending(requestId, browserId));
        }

        boolean validate(String browserId, Response r) {
            // signatureVerified is the output of a TRUSTED MOCK verifier.
            // Never accept it from SAML XML, HTTP params or user input.
            if (r == null || !r.signatureVerified()
                    || !IDP.equals(r.issuer())
                    || !ACS.equals(r.destination())
                    || r.id() == null || r.id().isBlank()
                    || r.inResponseTo() == null) return false;
            Pending pending = requests.get(r.inResponseTo());
            if (pending == null || !pending.browserId().equals(browserId))
                return false;
            Assertion a = r.assertion();
            if (a == null || a.id() == null || a.id().isBlank()
                    || !IDP.equals(a.issuer())
                    || a.audienceRestrictions() == null
                    || a.audienceRestrictions().isEmpty()) return false;

            // OR within one AudienceRestriction, AND across restrictions.
            for (Set<String> restriction : a.audienceRestrictions()) {
                if (restriction == null || !restriction.contains(RP))
                    return false;
            }
            if (a.bearerConfirmations() == null
                    || a.bearerConfirmations().isEmpty()) return false;
            boolean hasValidBearer = false;
            for (Bearer confirmation : a.bearerConfirmations()) {
                if (confirmation != null
                        && ACS.equals(confirmation.recipient())
                        && pending.requestId().equals(
                            confirmation.inResponseTo())
                        && confirmation.notOnOrAfter() != null
                        && NOW.isBefore(confirmation.notOnOrAfter())) {
                    hasValidBearer = true;
                    break;
                }
            }
            if (!hasValidBearer
                    || usedResponses.contains(r.id())
                    || usedAssertions.contains(a.id())) return false;
            // Simplified single-process consume; not cluster-safe/atomic.
            if (!requests.remove(pending.requestId(), pending)) return false;
            usedResponses.add(r.id());
            usedAssertions.add(a.id());
            return true;
        }
    }

    static Response base(String requestId) {
        return new Response("resp-" + requestId, IDP, ACS, requestId, true,
            new Assertion("assert-" + requestId, IDP,
                List.of(Set.of(RP)),
                List.of(new Bearer(ACS, requestId,
                    NOW.plus(Duration.ofMinutes(5))))));
    }

    static Response withAssertion(Response r, Assertion a) {
        return new Response(r.id(), r.issuer(), r.destination(),
            r.inResponseTo(), r.signatureVerified(), a);
    }
    static Response withBearer(Response r, Bearer b) {
        Assertion a = r.assertion();
        return withAssertion(r, new Assertion(a.id(), a.issuer(),
            a.audienceRestrictions(), List.of(b)));
    }
    static Response withAudience(Response r,
            List<Set<String>> restrictions) {
        Assertion a = r.assertion();
        return withAssertion(r, new Assertion(a.id(), a.issuer(),
            restrictions, a.bearerConfirmations()));
    }
    static void check(String label, boolean passes) {
        System.out.println(label + "=" + passes);
    }

    public static void main(String[] args) {
        Policy policy = new Policy();
        policy.start("_req_a", "browser-A");
        Response good = base("_req_a");

        check("wrongAudienceRejected", !policy.validate("browser-A",
            withAudience(good, List.of(Set.of(
                "https://evil.example.test/sp")))));
        check("missingAudienceRejected", !policy.validate("browser-A",
            withAudience(good, List.of())));
        check("oneWrongRestrictionRejected", !policy.validate("browser-A",
            withAudience(good, List.of(Set.of(RP),
                Set.of("https://other.example.test/sp")))));
        check("wrongRecipientRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(
                "https://other.example.test/acs", "_req_a",
                NOW.plusSeconds(300)))));
        check("recipientPrefixTrickRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(
                ACS + "/evil", "_req_a", NOW.plusSeconds(300)))));
        check("missingRecipientRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(
                null, "_req_a", NOW.plusSeconds(300)))));
        check("wrongDestinationRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(),
                "https://other.example.test/acs", good.inResponseTo(),
                true, good.assertion())));
        check("httpDowngradeRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(),
                "http://portal.example.test/login/saml2/sso/corp",
                good.inResponseTo(), true, good.assertion())));
        check("missingDestinationRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(), null,
                good.inResponseTo(), true, good.assertion())));
        check("wrongResponseInResponseToRejected",
            !policy.validate("browser-A",
                new Response(good.id(), good.issuer(),
                    good.destination(), "_req_other",
                    true, good.assertion())));
        check("missingResponseInResponseToRejected",
            !policy.validate("browser-A",
                new Response(good.id(), good.issuer(),
                    good.destination(), null,
                    true, good.assertion())));
        check("wrongBearerInResponseToRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(ACS, "_req_other",
                NOW.plusSeconds(300)))));
        check("expiredBearerRejected", !policy.validate("browser-A",
            withBearer(good, new Bearer(ACS, "_req_a",
                NOW.minusSeconds(1)))));
        check("wrongIssuerRejected", !policy.validate("browser-A",
            new Response(good.id(), "https://fake-idp.example.test",
                good.destination(), good.inResponseTo(), true,
                good.assertion())));
        check("untrustedSignatureRejected", !policy.validate("browser-A",
            new Response(good.id(), good.issuer(),
                good.destination(), good.inResponseTo(), false,
                good.assertion())));
        check("crossBrowserRejected",
            !policy.validate("browser-B", good));
        check("unsignedDoesNotConsumeRequest",
            policy.requests.containsKey("_req_a"));

        check("validBaselineAccepted",
            policy.validate("browser-A", good));
        check("sameResponseReplayRejected",
            !policy.validate("browser-A", good));
        check("requestConsumedAfterSuccess",
            !policy.requests.containsKey("_req_a"));

        policy.start("_req_b", "browser-B");
        Response goodB = base("_req_b");
        check("alternativeAllowedAudienceAccepted",
            policy.validate("browser-B",
                withAudience(goodB, List.of(Set.of(
                    RP, "https://alias.example.test/sp")))));

        policy.start("_req_c", "browser-C");
        Response goodC = base("_req_c");
        Bearer invalid = new Bearer("https://bad.example.test/acs",
            "_req_c", NOW.plusSeconds(300));
        Assertion a = goodC.assertion();
        Assertion withTwo = new Assertion(a.id(), a.issuer(),
            a.audienceRestrictions(), List.of(invalid,
                new Bearer(ACS, "_req_c", NOW.plusSeconds(300))));
        check("oneValidBearerAmongTwoAccepted",
            policy.validate("browser-C",
                withAssertion(goodC, withTwo)));

        policy.start("_req_d", "browser-D");
        Response goodD = base("_req_d");
        check("missingRequestRejected",
            !policy.validate("browser-D",
                new Response("resp-unknown", goodD.issuer(), ACS,
                    "_req_unknown", true, goodD.assertion())));
        check("laterUnsolicitedResponseRejected",
            !policy.validate("browser-X", base("_req_nobody")));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 Saml2BindingNegativeTestDemo.java
java Saml2BindingNegativeTestDemo
~~~

**Stdout chính xác sau khi biên dịch/chạy trên JDK 17:**

~~~text
wrongAudienceRejected=true
missingAudienceRejected=true
oneWrongRestrictionRejected=true
wrongRecipientRejected=true
recipientPrefixTrickRejected=true
missingRecipientRejected=true
wrongDestinationRejected=true
httpDowngradeRejected=true
missingDestinationRejected=true
wrongResponseInResponseToRejected=true
missingResponseInResponseToRejected=true
wrongBearerInResponseToRejected=true
expiredBearerRejected=true
wrongIssuerRejected=true
untrustedSignatureRejected=true
crossBrowserRejected=true
unsignedDoesNotConsumeRequest=true
validBaselineAccepted=true
sameResponseReplayRejected=true
requestConsumedAfterSuccess=true
alternativeAllowedAudienceAccepted=true
oneValidBearerAmongTwoAccepted=true
missingRequestRejected=true
laterUnsolicitedResponseRejected=true
~~~

### 12.1. Diễn giải kết quả

- `wrongAudienceRejected` và `oneWrongRestrictionRejected`: không dùng assertion cho SP sai; nhiều restrictions được xử lý theo đúng ý nghĩa logic.
- `wrongRecipientRejected`, `recipientPrefixTrickRejected` và `missingRecipientRejected`: bearer confirmation phải đúng public ACS, không chấp nhận prefix path hoặc thiếu recipient.
- `wrongDestinationRejected`, `httpDowngradeRejected`, `missingDestinationRejected`: Response phải nhắm ACS chính xác dưới chính sách strict.
- `wrongResponseInResponseToRejected` và `wrongBearerInResponseToRejected`: hai cấp request binding được kiểm độc lập.
- `crossBrowserRejected`: browser B không dùng được AuthnRequest do browser A giữ.
- `unsignedDoesNotConsumeRequest`: một input bị từ chối trong demo không làm mất request của browser A.
- `validBaselineAccepted`: một response đầy đủ, đúng mọi điều kiện, được chấp nhận.
- `sameResponseReplayRejected` và `requestConsumedAfterSuccess`: request đã dùng không thể tái sử dụng.
- `alternativeAllowedAudienceAccepted`: một restriction chứa SP entityId cùng audience khác vẫn có thể thỏa, không được reject sai.
- `oneValidBearerAmongTwoAccepted`: một trong hai bearer confirmations đầy đủ hợp lệ đủ đáp ứng phần subject confirmation.
- `missingRequestRejected` và `laterUnsolicitedResponseRejected`: policy SP-initiated-only không accept response không có request trước đó.

**Phân biệt:** đây là **logic model** dùng after-crypto booleans giả lập, không chứng minh OpenSAML thật xử lý XMLDSig/Conditions/SubjectConfirmation. Một bài test production phải có fixture XML được ký **sau khi** sửa trường và chạy thật qua `OpenSaml5AuthenticationProvider`.

## 13. Edge cases hay bỏ sót

### 13.1. Response Destination đúng nhưng ACS HTTP request khác

Nếu Response Destination = `https://portal.example.test/login/saml2/sso/corp` nhưng attacker POST đến endpoint ứng dụng khác được route tới cùng filter, server phải giải quyết việc đối chiếu **destination theo ACS policy và endpoint thực nhận**. Không dùng một endpoint tổng quát nhận mọi signed SAMLResponse cho mọi tenant mà bỏ registration/ACS mapping.

### 13.2. Recipient đúng nhưng bearer confirmation dành cho request khác

Ngay cả khi Recipient đúng ACS, một `SubjectConfirmationData/@InResponseTo` của `_req_other` không thuộc AuthnRequest `_req_a`. Đây là trường hợp replay/login injection cần negative test riêng.

### 13.3. Replay ID trong nhiều browser

Một Response ID/Assertion ID đã dùng không nên được chấp nhận lại qua browser khác. Chỉ lưu replay trong một HttpSession local có thể không đủ nếu cùng signed assertion được POST tới multiple nodes. Với các assertion profiles yêu cầu replay protection, dùng policy/cache được chia sẻ và TTL phù hợp.

### 13.4. Nhiều assertions trong một Response

Không chọn “assertion đầu tiên có Audience đúng” rồi bỏ qua các phần khác chưa được xác minh. Mỗi assertion dự định dùng để tạo Authentication phải có issuer/signature/conditions/subject confirmation hợp lệ; identities và attributes từ các assertions không được trộn trái profile.

### 13.5. Signed Response vs signed Assertion

Một RP có thể nhận Response-signed, Assertion-signed hoặc cả hai theo IdP contract. Test xác định **đúng phần được bảo vệ** và kiểm signature placement/trust. Nếu Response chỉ ký mà assertion unsigned bên trong, không được tin một assertion “lạ” ngoài phần được bảo vệ. Nếu Assertion ký riêng, thay Response Destination vẫn cần Response-level validation. XML signature wrapping là test riêng, không được gộp thành test field mismatch.

### 13.6. RelayState không phải nguồn tin cậy độc lập

`RelayState` giúp mang/tra request state hoặc return location; không coi chuỗi này tự là bằng chứng browser đã khởi tạo giao dịch. Nếu `CacheSaml2AuthenticationRequestRepository` lookup bằng RelayState global, cần thêm browser binding/one-time consume. Không redirect tới external URL chỉ vì RelayState chứa URI.

### 13.7. Request hợp lệ nhưng local user bị khóa

Sau tất cả SAML validation, vẫn phải kiểm mapping external identity với local user/tenant/roles. Một assertion hợp lệ cho Alice không đảm bảo Alice được truy cập tài chính hoặc admin API.

## 14. Chính sách báo lỗi và SecurityContext

Trong integration tests, các mismatch phải không tạo **Authenticated Saml2Authentication** cho callback đó.

**Tuy nhiên cần phân biệt:**

- Browser **anonymous** trước callback: sau negative response phải **vẫn anonymous**.
- Browser đã có session **Alice**: một negative response của Mallory không được thay thành Mallory; app có thể vẫn giữ Alice hoặc clear session theo policy, nhưng test phải xác nhận **không có new login**.
- SAML filter failure handler có thể redirect 302 hoặc trả 401; không hardcode một status cố định nếu app policy không quy định.
- Không gọi controller trực tiếp hoặc set SecurityContext giả trong test rồi tuyên bố **OpenSAML validator** đã reject field.
- Không chỉ assert `/private` trả 200 trong một session cũ: có thể 200 nhờ **existing Authentication**, dù callback mới thực ra thất bại.
- Nếu custom authentication converter/validator fail open và tạo `ROLE_USER` từ NameID trước khi validate signature/conditions, đó là lỗi nghiêm trọng.

Một bộ assert tốt nên bao gồm:

~~~text
Given browser state before callback:
  oldSessionUser = none OR alice
  pendingRequestId = _req_a
When:
  POST signed mutated SAMLResponse
Then:
  negative test did NOT create new authenticated identity
  success handler not invoked
  no new privilege/tenant assignment
  protected endpoint not reachable as asserted attacker identity
  response/assertion replay not accepted
  reason category matches target mismatch if instrumented
~~~

## 15. Troubleshooting bảng lỗi thường gặp

| Triệu chứng | Khả năng | Cách xử lý |
| --- | --- | --- |
| Audience mismatch | IdP dùng ACS URL thay SP entityId hoặc sai tenant | Đối chiếu RP entityId/metadata và IdP audience config |
| Recipient mismatch | IdP gửi tới old ACS/alias/path | Đồng bộ ACS URL trong IdP metadata, RP registration |
| Destination mismatch | Public HTTPS vs internal HTTP do reverse proxy | Fix public base URL, trusted forwarded headers |
| InResponseTo mismatch | Pending AuthnRequest missing/ID khác, wrong browser | Kiểm HttpSessionSaml2AuthenticationRequestRepository/RelayState |
| Test sửa XML rồi luôn fail | Chữ ký XMLDSig hỏng | Re-sign fixture trước khi POST |
| InResponseTo test fail do no session | Cookie SameSite không gửi trên SAML POST | Thiết kế SameSite/ACS binding đúng, không bỏ correlation |
| Một test pass trên máy A, fail B | Request repo local, replicas không share session | Spring Session/Redis hoặc sticky sessions có design |
| Callback không đúng registration | IdP issuer, tenant, ACS route không liên kết | Kiểm RelyingPartyRegistration resolver và registrationId |
| Wrong Recipient nhưng vẫn pass | Bearer SubjectConfirmation validator bị disable/custom sai | Restore default validator, regression test |
| Wrong Audience nhưng vẫn pass | AudienceRestrictionValidator bị loại | Restore default assertion conditions validation |
| Wrong Destination nhưng vẫn pass | DestinationValidator bị bỏ | Restore default response validation |
| Wrong Response InResponseTo pass | ResponseValidator custom thiếu InResponseToValidator | Dùng defaults + extensions, kiểm SP-init policy |
| Wrong Bearer InResponseTo pass | BearerSubjectConfirmationValidator bị bỏ hoặc chọn sai confirmation | Test per-bearer all-fields binding |
| Fail chỉ khi SAML encrypted | Decryption/key/ordering khác fixture | Kiểm encrypted assertion flow và signature validation stage |
| App login thành công nhưng user không có role | Local user mapping/authorization | Tách SAML validation khỏi local roles |
| Login lỗi nhưng /private vẫn 200 | Old SecurityContext/HttpSession còn | Kiểm new Authentication, not only HTTP status |
| IdP-initiated response thiếu request | Unsolicited flow | Tách policy riêng, không áp rule SP-init lẫn lộn |
| IdP cert rollover lỗi tất cả | Signing certificate không khớp | Update metadata trust theo kênh tin cậy, không disable signature |
| Receiver mismatch nhiều hostnames | CNAME/ingress canonicalization không nhất quán | Cố định public ACS, test exact paths |
| Authentication bị chấp nhận hai lần | Replay cache/one-time request consume thiếu | Triển khai state/cache và tests nhiều nodes |
| Mismatch ở only one node | Host, proxy, config, session store khác | Kiểm node, metadata, session storage và source of truth |

### 15.1. Runbook kiểm thử lỗi đúng lớp

1. **Từ log redacted**, xác định `registrationId`, expected entityId/ACS/issuer.
2. Kiểm test có tạo **AuthnRequest mới** trong đúng browser session trước mỗi response không.
3. Kiểm signature của fixture (test key) đã pass; nếu không, **chưa có coverage** về field được thay.
4. Đối chiếu Audience với SP Entity ID, không với ACS.
5. Đối chiếu Recipient tại bearer SubjectConfirmationData với public ACS.
6. Đối chiếu Destination tại Response với endpoint nhận theo policy/profile.
7. Đối chiếu Response/Bearer InResponseTo với AuthnRequest ID và request repository/browser binding.
8. Kiểm timing/clock-skew, replay state và issuer/certificate.
9. Kiểm browser cookie SameSite và forwarded headers ở ingress.
10. Kiểm chính xác **Auth result và session mới**; đừng bị existing session che kết quả.
11. Nếu không match, sửa metadata/configuration/test fixture; **không disable validators**.
12. Lưu regression test và giám sát rejection categories.

## 16. Đối tượng nào nên được test bằng unit, integration hay end-to-end?

| Level | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Unit test domain policy** | Hiểu logic exact field binding | Java 17 mock ở phần 12 |
| **Unit test custom validator** | Kiểm extension nếu thực sự có | OpenSAML objects đã được validate/trusted theo helper |
| **Spring Security integration** | Chạy real filter/provider/signature/issuer/conditions | MockMvc POST signed fixture vào ACS |
| **Browser + test IdP e2e** | Kiểm SameSite, RelayState, redirects, session correlation | Browser A/B, multi-tab, IdP POST, login failure |
| **Ingress/proxy environment** | Kiểm public ACS/Destination và forwarded headers | HTTPS public → HTTP internal, host alias |
| **Security regression** | Ngăn validator bị vô tình bỏ/weakening | Wrong Audience/Recipient/Destination/InResponseTo remains rejected |

**Phải có cả positive baseline và negative controls.** Nếu mọi response đều fail do keytab/IdP/certificate sai, test suite có thể “xanh” vì các assertions negative luôn đúng nhưng thực ra SAML login đã hỏng. Positive test bắt buộc phải PASS trong cùng cấu hình.

## 17. Các anti-pattern cần tránh

1. **“Signature đúng là đăng nhập được.”** Sai: vẫn cần Audience, Recipient, Destination, InResponseTo, time, issuer, replay.
2. **“Audience là ACS URL.”** Sai nếu SP Entity ID khác ACS.
3. **“Destination và Recipient giống nhau nên chỉ cần kiểm một.”** Sai: hai trường ở hai lớp khác nhau.
4. **“Response InResponseTo đúng là đủ.”** Sai nếu bearer confirmation InResponseTo sai.
5. **“Có một bearer có Recipient đúng, một bearer khác có InResponseTo đúng, nên pass.”** Sai: cùng một bearer phải thỏa tất cả.
6. **“Mỗi Audience trong một restriction đều phải giống SP.”** Sai với semantics nhiều audiences trong cùng restriction.
7. **“SAML Response chưa có pending AuthnRequest thì luôn là malformed XML.”** Sai: có IdP-initiated profile; nhưng có thể **bị cấm theo policy ứng dụng**.
8. **“Bỏ InResponseToValidator để sửa SameSite cookie.”** Sai: làm suy yếu correlation/login fixation defense.
9. **“Bỏ DestinationValidator để chạy qua reverse proxy.”** Sai: sửa public URL/metadata và forwarded header trust.
10. **“Test sửa ký tự trong signed XML mà bị reject là đủ.”** Sai: có thể fail signature, không test field.
11. **“Dùng spring-security-test saml2Login() là test được XML.”** Sai: auth test post processor có thể bypass XML validation.
12. **“Chỉ assert HTTP 401.”** Chưa đủ: failure handler có thể 302, old SecurityContext có thể còn.
13. **“Đếm Request ID mà không bind browser.”** Không đủ: response của attacker có thể được lookup trong global cache.
14. **“Dùng startsWith/endsWith để so entity IDs.”** Rủi ro prefix/lookalike host/path.
15. **“Bật mọi unsolicited response vì IdP portal cần tile.”** Không: cần allowlist, separate policy và account-switch protections.
16. **“Cho test IdP dùng certificate production để dễ integration.”** Không cần thiết và nguy hiểm; dùng riêng môi trường thử nghiệm.

## 18. Checklist hoàn thành trước production

- [ ] Đã xác định chính xác SP Entity ID, ACS URL, IdP Entity ID và registrationId.
- [ ] Đã phân biệt Audience, Recipient, Destination và hai InResponseTo fields.
- [ ] Có baseline signed response đúng và **PASS** qua real Spring Security SAML filter.
- [ ] Test wrong Audience với chữ ký **vẫn hợp lệ** → FAIL.
- [ ] Test missing/empty AudienceRestriction theo policy → FAIL.
- [ ] Test nhiều Audience trong cùng restriction đúng semantics OR.
- [ ] Test nhiều AudienceRestrictions đúng semantics AND.
- [ ] Test wrong Recipient, missing Recipient, URL prefix/path/HTTPS mismatch → FAIL.
- [ ] Test nhiều bearer confirmations: chỉ PASS nếu **một confirmation** thỏa mọi điều kiện.
- [ ] Test wrong Destination (khác host/path/scheme) → FAIL.
- [ ] Test missing Destination theo strict ACS policy → FAIL.
- [ ] Test Destination đúng nhưng Recipient sai và ngược lại → FAIL.
- [ ] Test Response InResponseTo sai/thiếu trong SP-initiated flow → FAIL.
- [ ] Test Bearer InResponseTo sai/thiếu trong SP-initiated flow → FAIL.
- [ ] Test browser session khác dù request ID giống → FAIL.
- [ ] Test AuthnRequest không còn/replayed/expired → FAIL.
- [ ] Test SAML Response/Assertion ID replay → FAIL.
- [ ] Test IdP issuer/certificate trust riêng biệt → FAIL.
- [ ] Test time conditions/bearer NotOnOrAfter, clock skew → FAIL ngoài cửa sổ.
- [ ] Test SP-init-only policy từ chối unsolicited response.
- [ ] Nếu IdP-init được bật: có policy riêng, kiểm assertions đầy đủ và chống silent account switch.
- [ ] `OpenSaml5AuthenticationProvider` (hoặc provider version tương ứng) vẫn áp default response/assertion validators.
- [ ] Không có custom validator vô tình loại InResponseTo/Audience/Recipient/Destination.
- [ ] Test qua **MockMvc real ACS**, không chỉ post processor tạo Saml2Authentication giả.
- [ ] Signed fixture được **thay trường trước khi ký lại** bằng test IdP key.
- [ ] Key/certificate test không liên quan production secrets.
- [ ] Callback không tạo SecurityContext/session user mới khi negative test fail.
- [ ] Không nhầm old session Authentication với kết quả callback mới.
- [ ] Public ACS, metadata và trusted ingress forwarding khớp cấu hình.
- [ ] SameSite cookie/bindings hoạt động trên cross-site SAML POST.
- [ ] Multiple tabs/nodes có request repository và replay cache phù hợp.
- [ ] Session fixation/account switch/local authorization được bảo vệ.
- [ ] Có logs lý do theo category nhưng không ghi raw SAMLResponse, NameID, assertion, cookie hoặc khóa ký.
- [ ] Có regression tests tự động chạy khi update Spring Security/OpenSAML/IdP metadata.

## 19. Câu hỏi tự kiểm tra

**1. Audience cần so với giá trị nào?**

**SP Entity ID** mà RP được đăng ký, không tự là ACS URL hoặc registrationId.

**2. Recipient xuất hiện ở lớp nào?**

Trong bearer `SubjectConfirmationData` của `Assertion/Subject`, không phải trực tiếp thuộc tính Response.

**3. Destination xuất hiện ở lớp nào?**

Thuộc tính `samlp:Response/@Destination`, định danh đích nhận SAML message theo binding/profile.

**4. Với SP-initiated SSO, InResponseTo kiểm ở đâu?**

Cả Response-level và bearer SubjectConfirmationData-level; chúng phải liên kết AuthnRequest ID đã lưu trong đúng browser transaction.

**5. Một SAML Response có chữ ký đúng nhưng Audience là tenant B có được login tại tenant A không?**

Không, nếu assertion không đáp ứng AudienceRestriction của SP A. Signature không thay policy audience.

**6. Nếu sửa Audience sau khi IdP ký rồi login fail, có chứng minh AudienceValidator chạy không?**

Không. Lỗi có thể là XML signature. Phải thay trước khi **re-sign** fixture và xác nhận validation stage.

**7. Vì sao Destination đúng không bù được Recipient sai?**

Vì Response được gửi đúng endpoint nhưng bearer assertion **không dành cho endpoint đó**; cả hai ràng buộc độc lập.

**8. Một AudienceRestriction có hai audiences, trong đó một đúng SP, có luôn fail không?**

Không. Trong cùng restriction, có thể đáp ứng nếu **một audience phù hợp**. Nhưng nếu có nhiều restrictions thì phải đáp ứng từng restriction.

**9. Có hai bearer confirmations, một có Recipient đúng và một có InResponseTo đúng, nhưng không có mục nào đúng cả hai: pass không?**

Không. Phải có **một** confirmation hợp lệ cho toàn bộ điều kiện của nó.

**10. Tại sao test đổi InResponseTo ở Response phải tách khỏi test đổi Bearer InResponseTo?**

Vì đó là **hai lớp validator**. Bỏ một trong hai có thể để response pass sai.

**11. Có thể lookup AuthnRequest bằng InResponseTo từ cache global rồi coi an toàn không?**

Không đủ. Cần biết request được **browser/session này** tạo, cùng IdP/registration và chưa bị dùng.

**12. SAML IdP-initiated response không có InResponseTo có luôn sai không?**

Không bắt buộc sai nếu deployment **cho phép unsolicited SSO**. Nhưng với **SP-initiated-only policy** thì phải reject.

**13. `SameSite=Lax` có thể gây lỗi gì?**

Cookie RP thường không được gửi trên cross-site SAML ACS POST, nên SP có thể mất AuthnRequest trong session; phải sửa cookie/binding không bỏ correlation.

**14. Test không login được nên có thể chỉ assert status=401?**

Không đủ. Failure handler có thể redirect 302; cần kiểm Authentication mới không được tạo và không có quyền truy cập mới.

**15. Vì sao phải có positive baseline?**

Nếu IdP certificate/test setup sai khiến **mọi fixture fail**, negative tests có thể giả PASS mà không thực sự kiểm được bốn field.

**16. Có nên loại AudienceRestrictionValidator/Recipient validation khi một IdP legacy gửi sai trường?**

Không. Sửa IdP metadata/ACS/issuer/conditions hoặc thiết kế phương án migration được security review; bỏ validator tạo rủi ro token substitution.

**17. SP Entity ID có nhất thiết là một URL ACS không?**

Không. Entity ID nhận diện SP; ACS URL nhận SAML Response. Chúng có thể là URI khác nhau.

**18. Nếu user đang có session Alice và callback SAML bị từ chối, vì sao request tiếp theo vẫn 200?**

Có thể browser vẫn có **old Authentication Alice**. Negative test phải kiểm **không tạo login mới**, không coi old session 200 là SAML validation pass.

## 20. Tài liệu tham khảo

- OASIS, **SAML 2.0 Core**, `AudienceRestriction`, `SubjectConfirmationData`, `Response Destination`, `InResponseTo`, Conditions: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS, **SAML 2.0 Profiles**, Web Browser SSO, bearer Recipient, InResponseTo, solicited/unsolicited: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS, **SAML 2.0 Approved Errata**, clarification về bearer Recipient/InResponseTo/Audience và thời hạn: https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-errata-2.0-cd-04.html
- Spring Security, **SAML 2.0 Login Overview**, AuthnRequest/Response flow, filter chain, relying party/ACS: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**, `OpenSaml5AuthenticationProvider`, `ResponseValidator`, `AssertionValidator`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Producing AuthnRequests**, `Saml2AuthenticationRequestRepository`, `HttpSessionSaml2AuthenticationRequestRepository` và cảnh báo login fixation khi dùng cache global: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **SAML 2.0 Relying Party Metadata**, SP entityID, ACS URL, IdP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **Testing Servlet Security**, phân biệt security test post processors với end-to-end protocol validation: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Security, **Session Management**, SecurityContextRepository, session fixation, Spring Session: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OWASP, **SAML Security Cheat Sheet**, XML signature, recipient/audience/response correlation và replay defenses: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- OWASP, **Testing for SAML**, security testing notes: https://owasp.org/www-project-web-security-testing-guide/

**Kết luận:** kiểm thử SAML 2.0 không dừng ở việc chữ ký hợp lệ. **Audience** buộc assertion đúng **SP Entity ID**; **Recipient** buộc bearer confirmation đúng **ACS**; **Destination** buộc **Response** đúng endpoint nhận; **InResponseTo** buộc Response và bearer confirmation vào **AuthnRequest đã được SP tạo cho browser này**. Để test có giá trị, hãy tạo **signed negative fixtures** (thay trường **trước** khi ký lại), chạy chúng qua **real Spring Security SAML filter/provider**, kiểm không phát sinh Authentication/session mới và duy trì các default validators. Trường sai không được trở thành “hợp lệ” chỉ vì ứng dụng tìm được NameID hoặc IdP signature vẫn đúng.