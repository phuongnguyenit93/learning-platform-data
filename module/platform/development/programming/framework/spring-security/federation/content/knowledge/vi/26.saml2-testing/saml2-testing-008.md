# Kiểm thử assertion hết hạn, chưa có hiệu lực và lệch đồng hồ trong SAML 2.0

> **Module:** Spring Security – federation · **Nhóm:** Kiểm thử SAML2. Bài học hướng dẫn thiết kế và thực hiện kiểm thử **thời gian hiệu lực của SAML Assertion** trong luồng Web Browser SSO: `Conditions@NotBefore`, `Conditions@NotOnOrAfter`, thời hạn `SubjectConfirmationData@NotOnOrAfter`, `IssueInstant`, `AuthnInstant`, `SessionNotOnOrAfter` và **clock skew** giữa IdP (Identity Provider) với SP (Service Provider). Bao gồm các ranh giới bằng nhau, độ chính xác mili-giây, sự lệch đồng hồ hai chiều, cấu hình Spring Security/OpenSAML, negative tests ở ACS, quản lý fixtures có chữ ký hợp lệ và một chương trình Java 17 chạy độc lập để kiểm tra quy tắc thời gian. Tên miền và dữ liệu dưới đây đều là ví dụ.

## 1. Tại sao phải kiểm thử thời gian ngay cả khi chữ ký đã đúng?

Khi user đăng nhập bằng SAML2, Identity Provider phát một `Response` chứa `Assertion` rồi browser POST đến Assertion Consumer Service (ACS) của Service Provider. Giả sử chữ ký của IdP đã được xác minh bằng chứng thư đã tin cậy và `Issuer` đúng. **Điều đó vẫn chưa đủ**: một Assertion đã hết hạn hoặc còn chưa đến thời điểm hiệu lực không được chấp nhận chỉ vì người ký là đúng IdP.

Tình huống điển hình:

```text
Identity Provider clock = 10:00:00 UTC
Service Provider clock  = 09:58:00 UTC

SAML Assertion:
  NotBefore    = 10:00:00 UTC
  NotOnOrAfter = 10:05:00 UTC

SP xem timestamp bằng giờ local 09:58:00:
  -> assertion chưa có hiệu lực.

Ngược lại khi SP nhanh hơn IdP:
  -> một assertion vừa phát có thể bị đánh giá đã quá hạn
     gần cuối validity window.
```

Hệ thống phân tán, container, domain controllers, proxy và IdP có thể lệch đồng hồ. Một mức **allowed clock skew** nhỏ giúp tránh lỗi SSO sai do vài giây lệch đồng hồ. Nhưng nới quá nhiều — ví dụ cho phép hàng chục phút/hàng giờ — có thể vô tình mở rộng cửa sổ dùng lại Assertion đã hết hạn.

**Mục tiêu:** Reject chính xác những Assertion không hợp lệ, cho phép dung sai đồng hồ **có giới hạn và được đo**, vẫn giữ signature, issuer, audience, recipient, correlation và replay checks.

### Sau bài học, bạn làm được gì?

1. Giải thích các timestamp và mối quan hệ giữa `Response`, `Assertion`, `Conditions`, `SubjectConfirmationData`, `AuthnStatement`.
2. Hiểu `NotBefore` **bao gồm điểm đầu** và `NotOnOrAfter` **không bao gồm điểm cuối**.
3. Kiểm thử ở mốc bằng nhau, ±1 ms, ±skew và ngoài skew; không chỉ test “đã hết hạn một ngày”.
4. Biết một Assertion có thể hợp `Conditions` nhưng **hết hạn bearer confirmation**.
5. Tách **skew tolerance** khỏi việc **nới thời gian sống Assertion**, session và replay cache.
6. Cấu hình `OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(...)` theo Spring Security docs và nhận biết sự khác nhau giữa các phiên bản.
7. Tạo SAML fixture **được ký hợp lệ bởi IdP kiểm thử** và sửa thời gian **trước khi ký** để kiểm tra đúng validator.
8. Dùng Java `Clock.fixed`, `Instant`, `Duration` để test deterministic, không `Thread.sleep`.
9. Kiểm tra negative cases qua ACS/Spring Security: không tạo Authentication, không sinh local authenticated session, không log raw Assertion.
10. Triển khai monitoring và runbook khi NTP, time zone, cache hoặc IdP/SP clock bị lệch.

## 2. Luồng xử lý SAML2 và nơi kiểm tra thời gian

```text
Browser                 SP / Spring Security               IdP
   |                            |                           |
   | GET /protected             |                           |
   |--------------------------->|                           |
   |<---------------------------| redirect AuthnRequest     |
   |------------------------------------------------------->|
   |                            |                           |
   |<-------------------------------------------------------|
   |     SAMLResponse with signed Assertion                  |
   |                                                        |
   | POST /login/saml2/sso/corporate                        |
   |--------------------------->|                           |
   |                            | 1. Resolve registration   |
   |                            | 2. Parse/decode Response  |
   |                            | 3. Verify trusted signing |
   |                            | 4. Validate issuer/aud    |
   |                            | 5. Validate time windows  |
   |                            | 6. Validate SubjectConf   |
   |                            | 7. Check InResponseTo     |
   |                            | 8. Enforce replay policy  |
   |                            | 9. Create Authentication  |
   |<---------------------------| success / failure         |
```

Spring Security Servlet SAML2 thường xử lý qua `Saml2WebSsoAuthenticationFilter` và `Saml2AuthenticationTokenConverter`, sau đó một OpenSAML authentication provider. Tài liệu Spring Security hiện hành mô tả `OpenSaml5AuthenticationProvider`; trong codebase Spring Security 6.x cũ có thể gặp `OpenSaml4AuthenticationProvider`. **Không copy API 5.x sang release khác mà không kiểm tra tương thích.**

**Quan trọng:** thử timestamp của XML trước khi signature verification chỉ là kiểm thử parser/utility. Bảo đảm SAML SSO an toàn phải kiểm **trên response đã có chữ ký hợp lệ và được ràng buộc với IdP đáng tin**. Nếu test input được sửa thời gian sau khi ký, failure có thể do **signature invalid**, không phải do temporal validator.

## 3. Những trường thời gian khác nhau trong SAML2

| Thuộc tính | Vị trí | Vai trò chính | Không nên nhầm với |
| --- | --- | --- | --- |
| `Response@IssueInstant` | `samlp:Response` | Thời điểm tạo protocol response; có thể có chính sách chặn response quá cũ/từ tương lai | Assertion validity window |
| `Assertion@IssueInstant` | `saml:Assertion` | Thời điểm tạo Assertion; có thể dùng freshness/max age rule | `Conditions@NotBefore` |
| `Conditions@NotBefore` | `saml:Conditions` | Thời điểm Assertion bắt đầu được sử dụng | `AuthnInstant` |
| `Conditions@NotOnOrAfter` | `saml:Conditions` | Mốc Assert­ion hết hiệu lực **exclusive** | `SessionNotOnOrAfter` |
| `SubjectConfirmationData@NotOnOrAfter` | `SubjectConfirmation` với bearer | Hạn cuối bearer confirmation/presentation tại ACS | Conditions expiration |
| `SubjectConfirmationData@Recipient` | bearer confirmation | ACS đích mà subject confirmation hợp lệ | Issuer URL |
| `SubjectConfirmationData@InResponseTo` | bearer confirmation | Correlate AuthnRequest trong SP-initiated flow | Signature timestamp |
| `AuthnStatement@AuthnInstant` | `saml:AuthnStatement` | Lúc user xác thực tại IdP; có thể đã từ trước do SSO | Thời điểm Response phát |
| `AuthnStatement@SessionNotOnOrAfter` | `saml:AuthnStatement` | Hạn phiên SSO được IdP thông báo theo profile | Hạn nhận bearer Assertion |
| `Request@IssueInstant` | `samlp:AuthnRequest` | Thời điểm SP khởi tạo request | IdP session lifetime |

Một SAML Assertion có thể có nhiều `AuthnStatement` và nhiều bearer `SubjectConfirmation`. Validator phải đánh giá đúng **phần tử được phép theo SAML profile**, không lấy timestamp đầu tiên trong XML bất kể nó thuộc cấu trúc nào.

### 3.1. XML minh họa

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-example"
    Version="2.0"
    IssueInstant="2026-11-07T09:59:50Z"
    Destination="https://portal.example.org/login/saml2/sso/corporate"
    InResponseTo="_request-example">

  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>

  <saml:Assertion ID="_assertion-example"
       Version="2.0"
       IssueInstant="2026-11-07T09:59:50Z">

    <saml:Issuer>https://idp.example.org/saml</saml:Issuer>

    <saml:Subject>
      <saml:NameID>opaque-user-id</saml:NameID>
      <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_request-example"
          Recipient="https://portal.example.org/login/saml2/sso/corporate"
          NotOnOrAfter="2026-11-07T10:02:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-11-07T09:59:00Z"
        NotOnOrAfter="2026-11-07T10:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://portal.example.org/sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
        AuthnInstant="2026-11-07T09:45:00Z"
        SessionNotOnOrAfter="2026-11-07T17:00:00Z">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>
          urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
```

**Đây là fixture đọc hiểu XML, chưa chứa `ds:Signature` nên không phải một SAML Response được phép đăng nhập production.** Khi làm integration test, ký hợp lệ bằng key của IdP test và tạo đầy đủ element/signature/reference/metadata. Việc chỉnh XML sau khi ký làm signature invalid. `NameID` là chuỗi giả, không đưa user thật vào fixtures.

### 3.2. Vì sao bearer và Conditions có hạn riêng?

Ở ví dụ trên, `Conditions@NotOnOrAfter=10:05`, nhưng bearer `SubjectConfirmationData@NotOnOrAfter=10:02`. Với SP dùng bearer Web SSO, không được nhận Assertion tại 10:03 chỉ vì Conditions vẫn còn hiệu lực: **bearer confirmation đã hết hạn**. Tùy profile, các confirmation khác nhau có thể được đánh giá độc lập; không được “chọn thời hạn lớn nhất của mọi phần tử” một cách tùy tiện.

### 3.3. AuthnInstant có thể cũ mà Response vừa mới

Trong SSO, user đăng nhập IdP lúc 09:00, vào app B lúc 09:50, IdP phát Assertion mới lúc 09:50. `AuthnInstant=09:00` và `Assertion@IssueInstant=09:50` là điều có thể bình thường. Không reject chỉ vì `AuthnInstant` cũ hơn `NotBefore`, nếu assurance/max-authentication-age policy vẫn cho phép.

Nếu nghiệp vụ cần **reauthentication gần đây**, nên dùng SAML AuthnRequest/`ForceAuthn` hoặc authn freshness policy riêng, rồi validate `AuthnInstant`/`AuthnContext`. **Không mở rộng/skew Conditions** để thay chính sách fresh authentication.

## 4. Quy tắc thời gian theo SAML Core

### 4.1. Không có clock skew

Theo SAML Core, `NotBefore` là mốc bắt đầu và `NotOnOrAfter` là mốc kết thúc. Nếu cả hai hiện diện, phải có `NotBefore < NotOnOrAfter`.

Với thời điểm tin cậy `now` từ **đồng hồ SP**:

```text
Assertion Conditions có hiệu lực khi:

    now >= NotBefore
AND now <  NotOnOrAfter

Không hợp lệ nếu:
    now <  NotBefore      => chưa có hiệu lực
OR  now >= NotOnOrAfter   => hết hạn
```

**Chính thời điểm `NotBefore` là hợp lệ; chính thời điểm `NotOnOrAfter` là không hợp lệ.** Đây là trường hợp boundary test bắt buộc.

### 4.2. Thêm clock skew cho phép

Giả sử policy cấu hình `S = 60 giây`. Một cách diễn đạt logic dung sai phổ biến:

```text
Điều kiện bắt đầu:
    now + S >= NotBefore

Điều kiện kết thúc:
    now - S < NotOnOrAfter

Tương đương:
    now >= NotBefore - S
AND now <  NotOnOrAfter + S
```

Với những phép tính này, **giới hạn đầu và cuối vẫn có ranh giới riêng**. Ở mốc `now = NotOnOrAfter + S` phải **reject** vì `NotOnOrAfter` là exclusive.

Đây là **mô hình kiểm thử** phổ biến nhằm hiểu extension hai phía. Cách một OpenSAML version áp skew cho từng `Condition`, `SubjectConfirmationData`, `IssueInstant` hay `AuthnStatement` phụ thuộc validator/profile cụ thể; **không tự cho rằng một biến S áp giống hệt mọi timestamp**. Khi test thật cần đối chiếu Spring/OpenSAML version và cấu hình hiện hành.

### 4.3. Chính sách ví dụ

```text
SP now:             2026-11-07T10:00:00Z
Allowed skew S:      PT60S
Conditions:
  NotBefore:         2026-11-07T09:55:00Z
  NotOnOrAfter:      2026-11-07T10:05:00Z
SubjectConfirmationData:
  NotOnOrAfter:      2026-11-07T10:02:00Z
```

Ở `10:00`, cả Conditions và bearer confirmation đều hợp lệ. Nếu SP lúc 10:02:30 và bearer NotOnOrAfter=10:02, chấp nhận hay reject tùy `S=60s` của validator; mặc dù có thể chấp nhận trong 30s grace, assertion **không tự biến thành có hiệu lực đến 10:05+60s** cho bearer. Các hạn phải được kiểm **độc lập**.

### 4.4. S là một security policy, không phải phương án chữa NTP

Một mức dung sai nhỏ có thể cần do độ trễ mạng, clock offset, scheduling và JDK precision. Nhưng nới S từ 60 giây lên 30 phút:

- Cho phép Assertion **chưa có hiệu lực** sớm hơn 30 phút.
- Cho phép expired Assertion được dùng muộn hơn 30 phút.
- Tăng cửa sổ tấn công replay nếu replay cache/correlation không chặn tốt.
- Che vấn đề NTP hoặc hệ thống phát timestamps sai.
- Có thể vi phạm profile/security policy của RP–IdP.

Mọi giá trị S cần được threat-model và đo đạc; **60s ở đây chỉ là giá trị minh họa**, không phải default Spring Security hay yêu cầu chung của SAML. Tài liệu Spring Security đưa ví dụ 10 phút để giải thích API; **ví dụ API không phải khuyến nghị vận hành 10 phút cho mọi hệ thống**.

## 5. Điều kiện bị thiếu hoặc sai: tách Core semantics và profile policy

### 5.1. Conditions attributes có thể không hiện diện

SAML Core cho phép `NotBefore` hoặc `NotOnOrAfter` không có. Khi thiếu một biên, biên đó **không được Core chỉ định**, không phải XML parse error tự động. Nếu thiếu cả hai, điều kiện thời gian của `Conditions` tự thân không giới hạn, nhưng các SAML conditions khác vẫn có thể áp dụng.

**Trong Web SSO thực tế**, SP có thể áp profile/policy chặt hơn như yêu cầu expiry, giới hạn lifetime tối đa, assertion age, bearer `NotOnOrAfter` và replay prevention. Không nói “Core luôn bắt buộc cả hai”, cũng không vô tình nhận Assertion không expiry vì “SAML Core cho phép”.

### 5.2. Bắt buộc kiểm interval khi có hai biên

```text
NotBefore    = 2026-11-07T10:05:00Z
NotOnOrAfter = 2026-11-07T10:03:00Z
```

Đây là interval trái ngược và phải reject; không dùng skew để làm khoảng thời gian invalid bỗng “có vẻ hợp lệ”. Nếu hai timestamps bằng nhau, khoảng thời gian rỗng, cũng không hợp lệ.

### 5.3. Negative test thiếu expiry

Nếu IdP test cố tình phát Conditions không có `NotOnOrAfter`:

- Xác định **policy SP** có bắt buộc hay không.
- Đảm bảo bearer `SubjectConfirmationData@NotOnOrAfter` vẫn được kiểm theo Web SSO profile.
- Nếu business/SP policy yêu cầu bounded lifetime, reject missing Conditions expiry hoặc áp max age từ IssueInstant theo rule đã duyệt.
- Không bịa expected result “luôn reject theo SAML Core” nếu chỉ một optional attribute bị thiếu.

### 5.4. Invalid timestamp string

XML schema của SAML dựa trên `xs:dateTime`. Các trường hợp:

```text
2026-11-07T10:00:00Z       ISO UTC bình thường
2026-11-07T10:00:00.123Z   Sub-second precision
2026-11-07T17:00:00+07:00  Cùng instant như 10:00Z
not-a-time                 Sai định dạng
2026-13-99T25:61:00Z       Sai date/time
```

Parse theo **XML Schema dateTime/Instant chính xác**, không dùng `LocalDateTime` rồi tự suy múi giờ system. Không xóa phần mili-giây gây sai ở ranh giới. Nếu profile yêu cầu UTC `Z`, IdP và SP phải thống nhất; format offset cần được parse đúng semantics khi được cho phép.

## 6. Những ranh giới cần test chính xác

Giả sử `now = 10:00:00.000Z` và `S = 60s`, các mốc sau chỉ xét **Conditions** trước, coi các checks khác là valid.

| # | NotBefore | NotOnOrAfter | Kỳ vọng theo công thức dung sai |
| --- | --- | --- | --- |
| 1 | 09:55:00 | 10:05:00 | ACCEPT |
| 2 | 10:00:00 | 10:05:00 | ACCEPT — bằng NotBefore |
| 3 | 10:01:00 | 10:05:00 | ACCEPT — đúng lower skew boundary |
| 4 | 10:01:00.001 | 10:05:00 | REJECT — chưa hiệu lực > 60s |
| 5 | 10:00:59 | 10:05:00 | ACCEPT — future trong skew |
| 6 | 09:55:00 | 10:00:00 | ACCEPT nếu policy cho 60s skew, dù đã tới logical end |
| 7 | 09:55:00 | 09:59:00 | **REJECT** — bằng upper skew boundary |
| 8 | 09:55:00 | 09:59:00.001 | ACCEPT — còn 1ms trong extended window |
| 9 | 09:55:00 | 09:58:59 | REJECT — expired > 60s |
| 10 | 10:01:01 | 10:05:00 | REJECT — not-yet-valid > 60s |
| 11 | 10:03:00 | 10:02:00 | REJECT — invalid interval |
| 12 | 10:00:00 | 10:00:00 | REJECT — zero-length interval |

Các ví dụ đều giả định **đồng hồ tin cậy đã cố định** và một policy skew chính xác. Kiểm thử integration cần xác nhận validator thực của Spring/OpenSAML đúng mong đợi; nếu implementation có phép so khác ở mốc millisecond, hãy xác minh version và chốt tolerance behavior bằng test thay vì đoán.

### 6.1. Tại sao test đúng 1ms quan trọng?

Nếu lập trình viên viết `now <= NotOnOrAfter` thay vì `now < NotOnOrAfter`, case mốc bằng nhau bị chấp nhận sai. Nếu thời gian bị chuyển thành epoch seconds bằng phép làm tròn, value `09:59:00.001` có thể bị coi bằng `09:59:00` và tạo lỗi boundary. Các test nên dùng `Instant` với nanosecond precision và `Duration`, không tự cắt về phút.

### 6.2. Vì sao không dùng sleep để test expiry?

`Thread.sleep(60_000)` làm test chậm, flaky vì scheduler, CI load, clock adjustments và network. Với unit test logic thuần, dùng `Clock.fixed(Instant, ZoneOffset.UTC)` và dịch `Instant`, hoặc dependency injection clock. Với integration test OpenSAML, tạo **signed fixtures có timestamps tương đối với đồng hồ kiểm thử**; nếu framework không inject Clock dễ dàng, đặt timestamps xa biên để test reject và reserve exact boundary cho unit/controlled-time tests.

## 7. Điều kiện bearer SubjectConfirmationData có thời hạn riêng

### 7.1. Vì sao phải kiểm bearer?

Trong SAML Web Browser SSO bearer profile, Assertion không được coi là authentication của user chỉ vì Conditions valid. `SubjectConfirmationData` còn ràng buộc:

- `Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"`.
- `Recipient` đúng ACS URL của SP.
- `NotOnOrAfter` chưa vượt quá hiệu lực cho bearer confirmation, với allowable skew nếu áp dụng.
- `InResponseTo` đúng ID AuthnRequest đã gửi trong SP-initiated flow.
- Một số profile cho phép `Address` tùy policy và giới hạn network/proxy.

OASIS SAML2 Web SSO profile quy định bearer `SubjectConfirmationData` phải có `Recipient` và `NotOnOrAfter`; điều kiện `NotBefore` trong bearer confirmation **không được dùng** theo profile cơ bản, dù một số profile khác có rules riêng. Không trộn `Conditions@NotBefore` với bearer `SubjectConfirmationData@NotBefore`.

### 7.2. Test Conditions hợp lệ nhưng bearer hết hạn

```text
now                             = 10:00:00Z
skew                            = 60s
Conditions.NotBefore            = 09:50:00Z
Conditions.NotOnOrAfter         = 10:10:00Z
SubjectConfirmation.NotOnOrAfter = 09:58:59Z
```

Conditions vẫn hợp lệ, nhưng bearer quá hạn hơn 60s ⇒ **REJECT**. Đây là test bắt buộc để tránh lỗi code chỉ nhìn `Conditions@NotOnOrAfter`.

### 7.3. Test bearer vừa hết hạn trong skew

```text
now                              = 10:00:00Z
skew                             = 60s
Conditions.NotOnOrAfter          = 10:10:00Z
SubjectConfirmation.NotOnOrAfter = 09:59:30Z
```

Theo mô hình dung sai ±60s ở phần 4, thời điểm bearer này vẫn trong grace ⇒ **có thể ACCEPT về mặt thời gian**, nhưng chỉ khi đúng validator policy và tất cả checks khác pass. Nếu security policy không muốn grace cho bearer, cấu hình validator/check riêng tương ứng và test quyết định đó.

### 7.4. Một Assertion có nhiều SubjectConfirmation

SAML profile có thể cho phép nhiều confirmation alternatives. Không dùng `min/max` đơn giản trên các timestamps và bỏ qua `Method`/`Recipient`/`InResponseTo`. Validator có thể thành công khi **ít nhất một bearer confirmation hợp lệ theo profile**, nhưng mọi phần tử được sử dụng phải được kiểm tương ứng. Một confirmation quá hạn không được “cứu” bởi một confirmation dành cho ACS/Request khác.

## 8. IssueInstant và AuthnInstant không phải Conditions

### 8.1. Response/Assertion IssueInstant

`IssueInstant` phản ánh thời điểm đối tượng được phát hành. Nó hữu ích để giới hạn tuổi message và phát hiện mốc xa tương lai khi policy triển khai. Tuy nhiên:

- Không thay thế `Conditions@NotBefore/NotOnOrAfter` hoặc `SubjectConfirmationData@NotOnOrAfter`.
- Một Response vừa phát có thể chứa Assertion có hạn khác.
- Policy freshness có thể giới hạn max assertion age, max response age và future issue allowance.
- Cần phân biệt `Response@IssueInstant` với `Assertion@IssueInstant`, không đọc một trường duy nhất.
- Nếu có nhiều assertions, phải kiểm mỗi assertion theo profile; không lấy IssueInstant đầu tiên trên toàn document.

### 8.2. AuthnInstant và ForceAuthn

`AuthnInstant` ghi thời điểm **user được xác thực tại IdP**, có thể cách lúc SAMLResponse được phát hàng giờ nếu user đã SSO. Một SP có yêu cầu “đã xác thực trong 15 phút gần nhất” cần policy `maxAuthenticationAge` hoặc AuthnRequest `ForceAuthn` nếu IdP support; không nên giả sử `Assertion@NotOnOrAfter` là bằng chứng login mới.

### 8.3. SessionNotOnOrAfter

`AuthnStatement@SessionNotOnOrAfter` nói về **phiên đăng nhập tại IdP** và chính sách dùng context lâu dài. Nó không thay thế expiry của bearer assertion nhận tại ACS. Trong SAML Web SSO profile/errata, SP nên bỏ security context khi `SessionNotOnOrAfter` đã đến trừ khi reestablish identity theo profile; cách local session framework enforce cần được kiểm thử.

### 8.4. Skew khác nhau theo field

Một application có thể áp skew cho Assertion Conditions, áp policy riêng cho `Response@IssueInstant`, áp maxAuthAge cho `AuthnInstant`, và policy khác cho session. **Không tăng một biến “clockSkew=1h” để giải quyết mọi lỗi thời gian**. Cần phân tích validator nào thật sự từ chối và tại sao, điều chỉnh đồng hồ hoặc policy đúng field.

## 9. Chữ ký, replay và thời gian là ba lớp bảo vệ riêng

### 9.1. Assertion expired vẫn có signature hợp lệ

Chữ ký XML của IdP không tự “hết hạn” khi đồng hồ tiến tới `NotOnOrAfter`. Một Assertion từ tuần trước có thể **cryptographically valid** với IdP key nhưng **temporal invalid**. Unit test chữ ký sẽ pass, login phải reject.

### 9.2. Replay có thể xảy ra ngay trong validity window

Giả sử Assertion valid từ 10:00 đến 10:05. Kẻ giữ được SAMLResponse có thể thử POST lại lúc 10:01. Tất cả timestamp checks pass; nếu SP không có `InResponseTo` tracking, unique assertion/response ID replay detection hoặc token-use policy, có nguy cơ reuse.

**Clock skew không ngăn replay.** Cần:
- Validate `InResponseTo` với AuthnRequest SP đã lưu/đúng session khi áp dụng.
- Replay cache cho assertion/response IDs hoặc equivalent replay protection theo framework/profile.
- Không để duplicate POST lập Authentication mới, kể cả trước expiration.
- Store replay entries có TTL ít nhất bao phủ risk window hợp lệ **kể cả skew**; điều chỉnh theo profile.
- Không chấp nhận untrusted XML certificate hay wrong audience để “xem test có pass”.

### 9.3. Session còn sống sau Assertion hết hạn có phải lỗi?

Không mặc nhiên. Assertion `NotOnOrAfter` thường giới hạn **thời điểm assertion có thể dùng để xác thực**, không tự yêu cầu mọi local application session lập từ nó kết thúc đúng mốc Conditions. Local session lifetime, `SessionNotOnOrAfter`, logout, reauthentication và authorization có policy khác.

Trong test:

- Expired Assertion **chưa từng được chấp nhận** không được tạo new SecurityContext.
- Sau khi Assertion hợp lệ đã tạo local session, việc user có còn login sau khi assertion validity window kết thúc tùy session policy; không coi đó là “expired assertion accepted” nếu thực tế app chỉ dùng session cookie.

## 10. Clock skew thực tế: chậm hay nhanh?

### 10.1. SP chậm hơn IdP

```text
Real/IdP time  = 10:00:00
SP time        = 09:58:30
IdP NotBefore  = 10:00:00
Skew SP        = 60s
```

SP đang **chậm 90s**, vượt allowed skew 60s ⇒ Assertion được xem là **NOT_YET_VALID**. Fix cần là đồng bộ NTP/chrony/VM clock và kiểm tra trust time source; không nới 10 phút chỉ để mọi người tạm đăng nhập được.

### 10.2. SP nhanh hơn IdP

```text
IdP time                  = 10:00:00
SP time                   = 10:02:00
Bearer NotOnOrAfter        = 10:01:00
Skew SP                   = 60s
```

SP nhanh 120s, bearer expiry chỉ cách 60s so với IdP; tại SP now=10:02 và bearer end + skew=10:02, **đã chạm upper boundary (exclusive) ⇒ reject**. Cần sửa đồng hồ và test precision, không đổi logic thành ≤.

### 10.3. Clock source và JVM

Java `Instant.now()` dùng system clock qua JVM; đồng hồ host/VM/container cần NTP đồng bộ. Time zone chỉ ảnh hưởng cách hiển thị local time, **không nên thay đổi Instant UTC**. DST trong hệ điều hành không tự làm SAML UTC thay đổi; sử dụng `LocalDateTime` rồi so XML UTC có thể gây lỗi giả khi DST thay đổi.

Nếu SP chạy nhiều pods, một pod lệch +90s còn pods khác đúng có thể tạo lỗi login “ngẫu nhiên”. Hãy đo offset, NTP sync health và isolate stale nodes. Không đồng bộ bằng cách đọc timestamp từ request browser: đó là nguồn **không đáng tin**.

## 11. Spring Security: cấu hình clock skew có kiểm soát

### 11.1. API hiện hành của OpenSAML5 provider

Theo Spring Security reference hiện hành, một cách cấu hình là tạo `OpenSaml5AuthenticationProvider` rồi đặt `AssertionValidator.builder().clockSkew(Duration)`.

Ví dụ **Spring Boot/Security fragment**:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider.AssertionValidator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlClockSkewConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        AssertionValidator validator = AssertionValidator.builder()
                .clockSkew(Duration.ofSeconds(60))
                .build();

        provider.setAssertionValidator(validator);

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)))
            .build();
    }
}
```

**Đây không phải một Java file tự chạy.** Cần Spring Security SAML2 dependencies, `RelyingPartyRegistrationRepository` tin cậy, Spring app, ACS, signing/verifying keys và IDP test. Ví dụ dùng **60s minh họa**, không khẳng định đó là Spring default hay thời gian bắt buộc.

### 11.2. Không thay validator mặc định bằng “always accept”

Một custom validator như:

```java
// ANTI-PATTERN — KHÔNG DÙNG TRONG SẢN XUẤT.
// provider.setAssertionValidator(assertionToken ->
//     Saml2ResponseValidatorResult.success());
```

sẽ bỏ đi các checks SAML protocol có thể quan trọng. Khi cần thêm validation cho `OneTimeUse` hoặc giới hạn stricter maximum age, ưu tiên **composite/extend defaults** của provider và dùng official builder APIs tương ứng release. Đừng cố chữa 401 bằng cách loại `Conditions`/`SubjectConfirmation` validators.

### 11.3. 4.x, 5.x, Spring Security 6 và 7

- Một số Spring Security 6.x sử dụng `OpenSaml4AuthenticationProvider` và constructor/static factory validators khác; docs migration và Javadoc của release là nguồn chuẩn.
- Các docs hiện hành mô tả `OpenSaml5AuthenticationProvider.AssertionValidator.builder()` và `clockSkew(Duration)`.
- Spring Security 7 thay đổi một số model xác thực và thứ tự Response/Assertion validation; không phụ thuộc một exception message hoặc static method name của bản khác.
- OpenSAML 4.x/5.x có differences ở validation parameters và `Duration` vs numeric millis trong một số APIs; không copy snippets từ OpenSAML 3.x rồi truyền kiểu sai.
- Việc set assertion clock skew **không nhất thiết** thay mọi validator của `Response@IssueInstant` hay local session TTL. Phải chạy integration tests của chính version.

### 11.4. Các checks khác vẫn cần được giữ

Dù thời gian được dung sai, SP phải xác minh:

- Trusted IdP certificate/signature, không tự tin `ds:KeyInfo`.
- Issuer matches trusted registration.
- AudienceRestriction chứa đúng RP entityID.
- Destination/Recipient trùng ACS expected.
- InResponseTo hợp lệ với pending AuthnRequest nếu SP-initiated.
- SubjectConfirmation bearer có đủ dữ liệu.
- Assertion/Response replay prevention.
- XML parser an toàn (XXE/DTD/oversize) và đúng signed subtree.
- Local authorization từ trusted/approved claims.

**Không có giá trị clockSkew nào biến một signature invalid hoặc wrong audience thành valid.**

## 12. Thiết kế test fixtures đúng để cô lập lỗi thời gian

### 12.1. Phương pháp tạo fixture

1. Dựng **IdP kiểm thử** hoặc SAML message factory (ví dụ OpenSAML) với trusted signing key riêng của test realm.
2. Cấu hình SP có `RelyingPartyRegistration` trỏ đúng test IdP entityID, ACS, audience, certificate.
3. Tạo một AuthnRequest và lưu ID/state tương ứng nếu test SP-initiated.
4. Sinh XML với `IssueInstant`, `Conditions` và bearer `SubjectConfirmationData` theo từng test case.
5. **Ký sau khi set timestamps**: cập nhật digest, canonicalization và signature bằng **đúng private key IdP test**.
6. Encode SAMLResponse theo binding thực tế (HTTP-POST thường Base64 XML) và gửi ACS.
7. Xác nhận Response hợp lệ về signature/issuer/audience trước khi phán đoán time validator.
8. Theo dõi Authentication, session, failure code đã sanitize và protected route behavior.
9. Không đem production SAML assertions/certs/private keys vào CI logs/fixtures.
10. Fixture XML có thể tạo timestamp gần `Instant.now()` ở từng test, không hardcode mốc 2026 rồi chạy vào năm 2027 khiến positive tests hết hạn.

### 12.2. Sai lầm khi chỉ chỉnh một Base64 đã ký

```text
signedXml = load("valid-response.xml")
tampered = signedXml.replace("10:05:00Z", "09:00:00Z")
POST Base64(tampered)
assertLoginFailed()
```

Kết quả reject có thể đến từ **signature invalid** vì XML đã bị thay sau ký. Test đó **không chứng minh** `Conditions@NotOnOrAfter` được kiểm. Để test expiration phải **tạo lại response hợp lệ về signature** với timestamp thay đổi, hoặc test temporal validator unit-level với dữ liệu có trust đã giả lập rõ.

### 12.3. Positive control + negative control

Mỗi nhóm test nên có:

- **Positive control:** signed Response đã được setup đầy đủ, các timestamps valid ⇒ login success.
- **Negative case:** chỉ thay một thời gian cần test, **ký lại hợp lệ** ⇒ login reject vì time validator.
- **Independent invalid signature test:** sửa XML sau ký hoặc ký bằng untrusted key ⇒ reject vì trust/signature, không coi là time validation coverage.
- **Wrong audience/recipient control:** ký hợp lệ nhưng wrong recipient ⇒ reject theo protocol, không được “cứu” bởi skew.

### 12.4. Không rò dữ liệu trong fixtures

Fixtures nên dùng `opaque-user-test`, test issuer URL, test keypair và synthetic timestamps. Tuyệt đối không lưu full production `SAMLResponse` có `NameID`/claims/token vào Git, issue tracker hoặc CI artifacts. Khi cần debug chỉ lưu allowlisted reason codes và request correlation ID.

## 13. Java 17 chạy được: kiểm thử Conditions và bearer expiry

Ví dụ sau **không dùng Spring hoặc OpenSAML**. Nó mô phỏng hai checks thời gian:

1. `Conditions@NotBefore / @NotOnOrAfter`.
2. `SubjectConfirmationData@NotOnOrAfter` của một bearer confirmation.

Nó dùng `Clock.fixed` để test exact boundaries, `Duration.ofSeconds(60)` làm dung sai minh họa, và `Instant` thay `LocalDateTime`. Đồng thời giới hạn skew configuration trong demo không quá 60 giây theo **policy ví dụ**. Chương trình không parse/signed SAML XML, không verify signature, recipient, issuer, audience, InResponseTo, XML IDs/replay, AuthnInstant hoặc SessionNotOnOrAfter. Không dùng hàm này thay provider thật.

Lưu file `SamlTimeBoundaryDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class SamlTimeBoundaryDemo {

    record Window(
            Instant notBefore,
            Instant notOnOrAfter,
            Instant bearerNotOnOrAfter) {}

    enum Decision {
        ACCEPT,
        BAD_INTERVAL,
        NOT_YET_VALID,
        ASSERTION_EXPIRED,
        BEARER_EXPIRED
    }

    static Decision validate(
            Window window,
            Clock clock,
            Duration allowedSkew) {

        Objects.requireNonNull(window, "window");
        Objects.requireNonNull(clock, "clock");
        Objects.requireNonNull(allowedSkew, "allowedSkew");
        Objects.requireNonNull(window.notBefore(), "notBefore");
        Objects.requireNonNull(window.notOnOrAfter(), "notOnOrAfter");
        Objects.requireNonNull(
                window.bearerNotOnOrAfter(), "bearerNotOnOrAfter");

        // Demo policy, not a universal SAML/Spring default.
        if (allowedSkew.isNegative()
                || allowedSkew.compareTo(
                    Duration.ofSeconds(60)) > 0) {
            throw new IllegalArgumentException(
                    "Skew outside approved demo policy");
        }

        Instant now = clock.instant();

        // Interval must be nonempty independent of skew.
        if (!window.notBefore().isBefore(
                window.notOnOrAfter())) {
            return Decision.BAD_INTERVAL;
        }

        // NotBefore is inclusive; tolerate SP behind by S.
        if (now.plus(allowedSkew).isBefore(
                window.notBefore())) {
            return Decision.NOT_YET_VALID;
        }

        // NotOnOrAfter is exclusive even after skew.
        if (!now.isBefore(
                window.notOnOrAfter().plus(allowedSkew))) {
            return Decision.ASSERTION_EXPIRED;
        }

        // Bearer confirmation has its own expiry.
        if (!now.isBefore(
                window.bearerNotOnOrAfter()
                      .plus(allowedSkew))) {
            return Decision.BEARER_EXPIRED;
        }

        return Decision.ACCEPT;
    }

    static Window window(
            Instant now,
            long nbOffsetSeconds,
            long endOffsetSeconds,
            long bearerEndOffsetSeconds) {

        return new Window(
                now.plusSeconds(nbOffsetSeconds),
                now.plusSeconds(endOffsetSeconds),
                now.plusSeconds(bearerEndOffsetSeconds));
    }

    static void show(String label, Window w,
                     Clock clock, Duration skew) {
        System.out.println(
                label + ": " + validate(w, clock, skew));
    }

    public static void main(String[] args) {
        Instant now =
                Instant.parse("2026-11-07T10:00:00Z");
        Clock fixed =
                Clock.fixed(now, ZoneOffset.UTC);
        Duration sixtySeconds =
                Duration.ofSeconds(60);

        show("Valid", window(now, -120, 120, 90),
                fixed, sixtySeconds);
        show("Future 61s", window(now, 61, 300, 300),
                fixed, sixtySeconds);
        show("Future exactly 60s",
                window(now, 60, 300, 300),
                fixed, sixtySeconds);
        show("Future within 30s",
                window(now, 30, 300, 300),
                fixed, sixtySeconds);
        show("Expired 61s",
                window(now, -300, -61, 300),
                fixed, sixtySeconds);
        show("Expired exactly 60s",
                window(now, -300, -60, 300),
                fixed, sixtySeconds);
        show("Expired within 30s",
                window(now, -300, -30, 300),
                fixed, sixtySeconds);
        show("Bearer expired 61s",
                window(now, -120, 120, -61),
                fixed, sixtySeconds);
        show("Bearer within 30s",
                window(now, -120, 120, -30),
                fixed, sixtySeconds);
        show("Bad interval",
                window(now, 180, 60, 300),
                fixed, sixtySeconds);
        show("Zero skew expired",
                window(now, -300, -30, 300),
                fixed, Duration.ZERO);
    }
}
```

Biên dịch và chạy:

```bash
javac SamlTimeBoundaryDemo.java
java SamlTimeBoundaryDemo
```

Stdout **chính xác**:

```text
Valid: ACCEPT
Future 61s: NOT_YET_VALID
Future exactly 60s: ACCEPT
Future within 30s: ACCEPT
Expired 61s: ASSERTION_EXPIRED
Expired exactly 60s: ASSERTION_EXPIRED
Expired within 30s: ACCEPT
Bearer expired 61s: BEARER_EXPIRED
Bearer within 30s: ACCEPT
Bad interval: BAD_INTERVAL
Zero skew expired: ASSERTION_EXPIRED
```

### 13.1. Giải thích boundary math

- `Future 61s`: `now+60s < NotBefore=now+61s` ⇒ reject.
- `Future exactly 60s`: `now+60s = NotBefore` ⇒ accept vì điểm đầu inclusive.
- `Expired exactly 60s`: `now = NotOnOrAfter+60s` ⇒ reject vì điểm cuối exclusive.
- `Expired within 30s`: `now < NotOnOrAfter+60s` ⇒ temporal accept trong skew policy minh họa.
- `Bearer expired 61s`: Conditions còn valid nhưng bearer past limit ⇒ reject.
- `Bad interval`: hai biên đảo ngược ⇒ reject, dù skew có thể đủ lớn để làm hai comparisons tạm pass.
- `Zero skew expired`: không có grace, end đã trước now 30s ⇒ reject.

### 13.2. Vì sao demo phải kiểm cả bearer?

Một validator chỉ kiểm `Conditions` có thể nhận Assertion tại 10:00 dù bearer `NotOnOrAfter=09:58:59`. Trong Web SSO bearer profile, đây là lỗi quan trọng. Demo cho thứ tự: validate interval, Conditions lower/upper, sau đó bearer upper. Integration test ngoài demo phải kiểm `Recipient` và `InResponseTo` với request thực.

### 13.3. Những gì demo chưa làm

- Không parse `SAMLResponse` XML, không Base64 decode.
- Không verify IdP signing certificate/XML Signature.
- Không kiểm `AudienceRestriction`, `Destination`, `Recipient`, `Issuer` hoặc `InResponseTo`.
- Không bảo vệ against replay, duplicate assertion IDs hay XML Signature Wrapping.
- Không xử lý multiple `SubjectConfirmation` alternatives và profiles khác bearer.
- Không kiểm `Response@IssueInstant`, `Assertion@IssueInstant`, `AuthnInstant` hoặc `SessionNotOnOrAfter`.
- Không quản lý real NTP, system clocks, asymmetric one-way skew hay precision policy của OpenSAML.
- Không tạo Spring Security `Authentication` hoặc `HttpSession`.

Ví dụ là một **test oracle** dạy logic thời gian đã định nghĩa, không phải implementation sản xuất.

## 14. Test case theo lớp kiểm soát

### 14.1. Conditions NotBefore

| Test | Input | Kết quả mong đợi |
| --- | --- | --- |
| NB-01 | NotBefore cách hiện tại 5 phút về quá khứ | Pass nếu các checks khác valid |
| NB-02 | NotBefore == now, S=0 | Pass — inclusive |
| NB-03 | NotBefore = now+1 ms, S=0 | Reject |
| NB-04 | NotBefore = now+S | Pass theo ±S model |
| NB-05 | NotBefore = now+S+1 ms | Reject |
| NB-06 | NotBefore là timestamp UTC hợp lệ, time zone display SP khác | Kết quả theo Instant, không theo local wall-clock |
| NB-07 | NotBefore có offset +07:00 cùng instant UTC | Parse/compare đúng nếu profile/parser cho phép offset |
| NB-08 | NotBefore="not-a-time" | Reject parsing/validation |
| NB-09 | NotBefore thiếu nhưng profile khác yêu cầu age limit | Hành vi theo contract, không tự coi Core luôn bắt buộc |

### 14.2. Conditions NotOnOrAfter

| Test | Input | Kết quả mong đợi |
| --- | --- | --- |
| EXP-01 | NotOnOrAfter > now nhiều phút | Temporal pass |
| EXP-02 | NotOnOrAfter == now, S=0 | Reject — exclusive |
| EXP-03 | NotOnOrAfter = now-1ms, S=0 | Reject |
| EXP-04 | NotOnOrAfter = now-S | Reject — upper skew boundary |
| EXP-05 | NotOnOrAfter = now-S+1ms | Có thể pass theo ±S model |
| EXP-06 | NotOnOrAfter = now-S-1ms | Reject |
| EXP-07 | NotOnOrAfter < NotBefore | Reject invalid interval |
| EXP-08 | NotOnOrAfter == NotBefore | Reject zero-length interval |
| EXP-09 | NotOnOrAfter thiếu, Web SSO policy yêu cầu bounded lifetime | Reject theo policy nếu đã cấu hình |
| EXP-10 | End cực xa tương lai | Test max assertion TTL/age policy, không mặc định unlimited |
| EXP-11 | Hết hạn nhưng signature hợp lệ | Reject vì time, không được tạo Authentication |

### 14.3. Bearer confirmation

| Test | Input | Kỳ vọng |
| --- | --- | --- |
| SC-01 | Bearer NotOnOrAfter hợp lệ, Conditions hợp lệ | Pass temporal |
| SC-02 | Bearer expired >S, Conditions còn valid | Reject |
| SC-03 | Bearer = now-S | Reject tại upper skew boundary |
| SC-04 | Bearer trong permitted skew | Hành vi theo actual validator policy |
| SC-05 | Bearer expiry thiếu trong Web Browser SSO | Reject theo profile |
| SC-06 | Bearer Recipient sai ACS | Reject dù timestamps valid |
| SC-07 | Bearer InResponseTo sai pending request | Reject |
| SC-08 | Multiple confirmations: một expired, một đúng thời gian nhưng wrong Recipient | Không chấp nhận tự động |
| SC-09 | SubjectConfirmationData NotBefore trong bearer Web SSO | Reject theo profile nếu cấm |
| SC-10 | Bearer valid nhưng Conditions expired | Reject |

### 14.4. IssueInstant, AuthnInstant, SessionNotOnOrAfter

| Test | Mục đích |
| --- | --- |
| ISSUE-01 | Response@IssueInstant quá xa tương lai, kiểm response freshness policy |
| ISSUE-02 | Assertion@IssueInstant quá cũ dù Conditions có vẻ dài, áp max assertion age nếu yêu cầu |
| ISSUE-03 | Response IssueInstant và Assertion IssueInstant khác nhau hợp lý, không dùng nhầm |
| AUTH-01 | AuthnInstant cũ nhưng user SSO session còn hợp lệ, không reject sai nếu maxAuthAge chưa yêu cầu |
| AUTH-02 | AuthnInstant quá cũ so với high-assurance step-up policy, request reauth |
| AUTH-03 | AuthnInstant tương lai >allowed skew, reject theo policy |
| SESS-01 | SessionNotOnOrAfter đã qua, local security context xử lý theo SP/profile policy |
| SESS-02 | SessionNotOnOrAfter còn xa nhưng bearer expired, không chấp nhận new login |
| PREC-01 | Fractional seconds/UTC offsets được parse không mất precision |

## 15. Test lại SAMLResponse đã ký: lưu ý triển khai

### 15.1. Assertion được ký còn nguyên nhưng hết hạn

Một fixture được **ký từ trước khi hết hạn** và lưu trong test có thể vẫn verify chữ ký thành công. Khi gửi nó tới ACS sau mốc end, SP phải reject. Đây là test tốt ở mức integrated production path, nhưng nếu muốn test đúng ±1 ms thì cần kiểm clock của JVM/CI có thể điều khiển; tránh test brittle do latency.

### 15.2. Muốn test NotBefore tương lai, phải ký lại

Để tạo future assertion đúng:

1. Generate XML with `NotBefore=now+S+epsilon`.
2. Cấp đúng `NotOnOrAfter` ở tương lai và bearer expiry không gây conflict.
3. Set `Response/Assertion@IssueInstant` và `InResponseTo` hợp lệ theo test profile.
4. Ký bằng **private key test IdP**, không phải key attacker hay credential production.
5. Base64 encode theo SAML HTTP-POST.
6. POST lên ACS; assert no authenticated session, reason code NOT_YET_VALID ở telemetry nếu ứng dụng expose nội bộ.

### 15.3. Test clock skew khi đồng hồ khác nhau

Test lớp logic bằng `Clock.fixed` với offset, và integration test bằng:

- Một bộ fixture có timestamps chính xác so với clock SP.
- Một test IdP có controllable issuance clock (test-only).
- Một test SP JVM/container có virtual clock hoặc dependency-injected trusted Clock nếu framework cho phép.
- Test NTP mismatch có kiểm soát trong staging; không cố chỉnh host clocks production để “thử”.

**Không để CI tests thay đổi system clock** máy shared runner hoặc production host. Môi trường test giờ ảo/recorded fixtures cần cô lập.

### 15.4. Signing order trong XMLDSig

Với signed Assertion và signed Response, sửa child nodes như `Conditions` có thể invalidate digest/signature cấp Assertion hoặc Response. Không “resign một level” nếu outer signature còn reference đến modified subtree. Sử dụng trusted OpenSAML test factories kiểm đúng signature coverage và re-sign những phần cần thiết; kiểm bằng positive control trước khi chạy negative test.

## 16. Spring Security integration test: khẳng định kết quả cuối, không chỉ HTTP status

### 16.1. Mô hình test infrastructure

```text
JUnit test / Test IdP / trusted test signing key
        |
        +-- Generate valid signed SAML Response
        +-- Case-specific timestamps
        +-- Valid expected ACS, Audience, Issuer, InResponseTo
        |
        v
Spring Boot Test + MockMvc or embedded test server
        |
        +-- SAML ACS /login/saml2/sso/corporate
        +-- RelyingPartyRegistration configured for Test IdP
        +-- OpenSAML temporal validators
        +-- AuthenticationSuccessHandler / FailureHandler
        |
        v
ASSERT:
  no authenticated principal on expired/not-yet-valid
  no local authenticated session is created
  protected endpoint still requires login
  safe error code, no raw SAML assertion in logs
```

### 16.2. Pseudocode test lifecycle

```java
// Mô tả workflow cho một test harness đã có IdP signing helper.
// Không phải JUnit class độc lập; helper đã được app test cung cấp.
Instant clockAt = trustedTestClock.instant();

byte[] validSigned = testIdp.signSamlResponse(
    responseWithConditions(
        clockAt.minusSeconds(30),
        clockAt.plusSeconds(120)
    )
);

byte[] expiredSigned = testIdp.signSamlResponse(
    responseWithConditions(
        clockAt.minusSeconds(600),
        clockAt.minusSeconds(121)
    )
);

assertSamlLoginAccepted(validSigned);
assertSamlLoginRejected(expiredSigned);
assertNoSecurityContextForRejectedResponse();
```

**Điểm cốt lõi:** test helper phải giữ mọi metadata/protocol checks còn lại valid để cô lập thời gian. `expiredSigned` là signed response mới được ký lại với test key; không dùng string replace trên signed fixture.

### 16.3. Đừng cứng hóa mong đợi status 401/302

Spring Security có thể redirect tới login page (3xx), trả 401/403 hoặc failure handler riêng. Một HTTP 302 sau ACS không chứng minh reject nếu nó redirect đến dashboard; một HTTP 200 cũng có thể là generic error page. Test nên kiểm **Authentication result**, `SecurityContextHolder`/session state và protected resource với cookie đã dùng, kèm internal allowlisted reason code. Không dựa chỉ vào HTTP status.

### 16.4. Tránh false positive do sai chỗ khác

Nếu fixture sai `InResponseTo`, wrong signing cert, wrong Audience hoặc missing bearer Recipient, login có thể fail trước khi temporal validator chạy. Khi test mục tiêu là `EXPIRED_ASSERTION` hoặc `NOT_YET_VALID`, kiểm bằng trace đã sanitize/validator unit test và **positive control** rằng same fixture ngoại trừ time pass toàn bộ checks.

### 16.5. Replay cache trong tests

Repeated assertion ID có thể bị từ chối vì replay trước cả timestamp. Mỗi test nên có fresh Assertion/Response IDs và AuthnRequest IDs hoặc reset **test-only replay store** đúng cách. Đồng thời có test riêng xác nhận duplicate valid signed Assertion bị reject. Không disable replay protection trong full-stack tests cho dễ.

## 17. Multi-pod, NTP, network latency và production behavior

### 17.1. Khi một pod lệch giờ

```text
IdP:        10:00:00
SP pod A:   10:00:02   PASS
SP pod B:   09:58:20   NOT_YET_VALID
SP pod C:   10:02:15   có thể EXPIRED bearer
```

Các pods dùng cùng signing cert, RelyingPartyRegistration và code vẫn có thể cho kết quả khác vì system clocks. Một phần login failures dưới load balancer là **clue của clock drift**. Cần kiểm time synchronization và VM/container host clocks trên **mọi nodes**, không chỉ server chính.

### 17.2. Network latency vs clock skew

Độ trễ giữa IdP issue và SP receive không hoàn toàn là clock offset. Một Response bị network queue/large POST/redirect chậm có thể đến sau bearer expiry dù đồng hồ chuẩn. Giải pháp có thể là giảm latency hoặc IdP phát bearer lifetime đúng profile, không mở skew vô hạn. Monitor latency separately from clock drift.

### 17.3. Timezone và DST

SAML dateTime thường ở UTC dạng `Z`. `2026-11-07T10:00:00Z` và `2026-11-07T17:00:00+07:00` đại diện cùng `Instant`. So string trực tiếp sẽ báo khác, nhưng về thời gian thì bằng nhau. Không parse thành `LocalDateTime.now()` của Asia/Ho_Chi_Minh hoặc timezone container rồi so với UTC không quy đổi.

### 17.4. Đồng hồ nhảy ngược/nhảy xuôi

NTP lớn, VM suspend/resume, leap/clock correction có thể làm system clock thay đổi. Thời điểm test có thể chạm interval ranh giới khi logger một thời điểm, validator một thời điểm khác. Khi debug, ghi **UTC event timestamp** và khoảng lệch đo được, không tự dùng log time thay validator time. Có thể cần synchronized clocks/monotonic elapsed metrics; SAML wall-clock validity vẫn phụ thuộc trusted actual time.

### 17.5. Multi-region và disaster recovery

Khi failover sang region khác, các nodes nên đồng bộ time, config skew/IDP registrations và replay caches. Nếu replay store chỉ local, một Assertion còn trong time window có thể được gửi lại đến region B sau khi region A đã nhận. Thời gian chính xác không thay distributed replay protection. Kiểm thử failover với same response ID và time windows.

## 18. Troubleshooting: lỗi nào, fix gì?

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `NotBefore` tương lai vài giây | Clock drift/lệch timestamp phát từ IdP | Đo NTP offset, config skew nhỏ có giới hạn |
| `NotBefore` tương lai 2 phút, S=60s | SP chậm hoặc IdP clock nhanh vượt policy | Sync clocks, không nới tùy tiện |
| `NotOnOrAfter` đã qua | Response delay, reused response, SP nhanh | Kiểm IDP issuance/latency và cache |
| Conditions valid nhưng bearer expired | `SubjectConfirmationData@NotOnOrAfter` sớm hơn | Kiểm bearer limits độc lập |
| 401/redirect lặp trên pod B | Pod B clock lệch hoặc config skew khác | Per-pod timestamp/NTP/status |
| Chỉ boundary milliseconds fail | Precision rounding hoặc comparison inclusive sai | Test Instant/millis, xem implementation |
| Valid XML test cũng fail | Wrong signature/issuer/ACS/InResponseTo | Fix fixture trước khi kết luận time |
| Expired XML test pass unexpectedly | Skew quá lớn, validator bị override/no expiry policy | Xác minh actual assertion validator config |
| Missing Conditions expiry được accept | Core cho phép omitted, SP policy chưa giới hạn | Thêm required lifetime/max age policy nếu cần |
| `AuthnInstant` cũ nhưng Response mới | User đã SSO lâu tại IdP | Áp maxAuthAge/ForceAuthn theo use case |
| `SessionNotOnOrAfter` quá hạn | SSO session expiry riêng | Rà local session policy/SLO |
| SAML parse lỗi với offset/timezone | Parser/format/schema issue | Dùng XML schema compliant parser |
| Replay valid Assertion được accept | Thiếu correlation/replay cache | Bật replay protection và tests |
| 302 sau ACS nhưng có authenticated user | Failure test chỉ assert HTTP status | Assert SecurityContext/session/protected route |
| Release mới login fail | OpenSAML/Spring defaults/API thay đổi | Review release notes/validation chain |
| Logs in raw Assertion | Debug statement/APM captures | Sanitize và bảo vệ logs ngay |

### 18.1. Không log XML chứa user data để gỡ lỗi

SAML Assertion có thể chứa `NameID`, email, roles, session index và dữ liệu danh tính nhạy cảm. Không dump raw `SAMLResponse` hoặc decoded XML vào application/proxy/APM logs. Ghi:

```json
{
  "event": "saml_authentication_rejected",
  "registration": "corporate",
  "reason_code": "ASSERTION_EXPIRED",
  "clock_skew_policy_seconds": 60,
  "verification_stage": "assertion_conditions",
  "correlation_id": "opaque-internal-event",
  "result": "rejected"
}
```

JSON là **audit event minh họa**. Không log raw token, XML, NameID, assertion ID, session cookies, cert private keys hoặc unbounded user-controlled values làm metric labels. Với monitoring clocks, dùng per-node clock offset/health và aggregate counts thay raw identities.

## 19. Security test matrix tổng hợp

| Case | Trạng thái chữ ký | Conditions | Bearer | Expected |
| --- | --- | --- | --- | --- |
| T01 Baseline | Trusted valid | Trong hạn | Trong hạn | ACCEPT |
| T02 Expired 2 phút, S=1 phút | Trusted valid | Expired | Trong hạn | REJECT |
| T03 NotBefore +61s, S=60s | Trusted valid | Chưa hiệu lực | Trong hạn | REJECT |
| T04 NotBefore +60s, S=60s | Trusted valid | Lower skew edge | Trong hạn | Temporal pass |
| T05 End = now-60s, S=60s | Trusted valid | Upper skew edge | Trong hạn | REJECT |
| T06 End = now-59.999s | Trusted valid | Inside upper grace | Trong hạn | Temporal pass |
| T07 Conditions valid, bearer expired | Trusted valid | Trong hạn | Expired | REJECT |
| T08 Conditions expired, bearer valid | Trusted valid | Expired | Trong hạn | REJECT |
| T09 Bad NotBefore > NotOnOrAfter | Trusted valid | Sai interval | Trong hạn | REJECT |
| T10 Missing bearer NotOnOrAfter | Trusted valid | Trong hạn | Thiếu bound | REJECT theo Web SSO |
| T11 Expired + wrong audience | Trusted valid | Expired | Trong hạn | REJECT; không dùng để khẳng định time-only test |
| T12 Valid time + wrong signature | Untrusted | Trong hạn | Trong hạn | REJECT signature |
| T13 Valid time + wrong Recipient | Trusted valid | Trong hạn | Wrong ACS | REJECT |
| T14 Valid time + wrong InResponseTo | Trusted valid | Trong hạn | Wrong request | REJECT |
| T15 Duplicate valid Assertion | Trusted valid | Trong hạn | Trong hạn | REJECT replay |
| T16 Valid signed but IDP B issuer | Trusted key other tenant | Trong hạn | Trong hạn | REJECT issuer-key binding |
| T17 Conditions thiếu NotOnOrAfter | Trusted valid | Unbounded upper | Trong hạn | Theo strict SP policy đã định |
| T18 Future AuthnInstant | Trusted valid | Trong hạn | Trong hạn | Theo authn freshness/clock policy |
| T19 Old AuthnInstant | Trusted valid | Trong hạn | Trong hạn | Reauth nếu maxAuthAge yêu cầu |
| T20 SessionNotOnOrAfter past | Trusted valid | Trong hạn | Trong hạn | Local session policy phải xử lý |
| T21 UTF-8/fractional timestamps | Trusted valid | Boundary 1ms | Trong hạn | Parse/compare chính xác |
| T22 System timezone khác nhau | Trusted valid | Cùng UTC instant | Trong hạn | Same decision |
| T23 Pod A UTC đúng / Pod B drift | Trusted valid | Gần boundary | Trong hạn | Metrics phát hiện offset |
| T24 Skew 30 phút không duyệt | Trusted valid | Mở rộng quá mức | Trong hạn | Configuration QA FAIL |
| T25 Real expired assertion được gửi lại sau logout | Trusted valid | Expired | Có thể expired | REJECT |
| T26 XML thay sau ký để đổi NotOnOrAfter | Invalid signature | Bất kỳ | Bất kỳ | REJECT signature, không tính temporal test |
| T27 Missing Conditions cả hai | Trusted valid | Unbounded | Trong hạn | Theo profile/max-lifetime policy |
| T28 SAML signed Assertion có malicious unsigned sibling | Trusted valid partial | Bất kỳ | Bất kỳ | REJECT/ignore unsigned node |
| T29 Wrong issuer nhưng timestamp pass | Valid math/other key | Trong hạn | Trong hạn | REJECT |
| T30 Expired Assertion không tạo authenticated session | Trusted valid | Expired | Trong hạn | SecurityContext rỗng/new login denied |

### 19.1. Kiểm thử CI nên phân tầng

**Unit (nhanh, deterministic):** Logic comparison với `Clock.fixed`, các mốc ±1ns/±1ms/±skew. **Provider-level:** OpenSAML/Spring assertion validation có ký hợp lệ, parser an toàn. **E2E:** browser/ACS/request correlation, cookies, failure handler, session isolation. **Operations:** NTP drift, multi-pod, metrics và replay cache distribution.

### 19.2. Test priority khi thời gian hạn chế

Ưu tiên tối thiểu 8 test có giá trị nhất:

1. Baseline signed valid accepts.
2. Expired Conditions reject.
3. Future NotBefore reject.
4. Expiry at exact `NotOnOrAfter` reject với S=0.
5. Boundary at `NotOnOrAfter + S` reject.
6. Conditions valid nhưng bearer expired reject.
7. Signature invalid nhưng time valid reject.
8. Duplicate signed Assertion reject dù còn trong validity window.

Sau đó mở rộng max lifetime, AuthnInstant, session policy và multi-region tests.

## 20. Runbook xử lý sự cố clock skew

### 20.1. Khi user báo “SSO chỉ lỗi lúc đăng nhập mới”

1. Xác định có phải request tới ACS thực sự hay login redirect loop khác.
2. Dùng internal reason code phân biệt `ASSERTION_NOT_YET_VALID`, `ASSERTION_EXPIRED`, `SUBJECT_CONFIRMATION_EXPIRED`, `INVALID_SIGNATURE`, `WRONG_ISSUER`, `REPLAY`.
3. Đo current UTC và NTP offset trên **SP pod**, IdP node, reverse proxy nodes nếu có tác động đến flow.
4. Xem config `clockSkew` thực tế theo release và registration; không suy từ sample code.
5. Xác định Assertion Conditions và bearer end **trong test environment/sanitized privileged diagnostics**, không dump raw production assertion.
6. Kiểm tra latency từ IdP phát Response đến browser ACS callback.
7. Xác nhận state/correlation/ACS Destination và TLS forward headers đúng.
8. Nếu clocks lệch, sửa NTP/time sync; không tắt expiration check.
9. Chỉ điều chỉnh skew nếu có policy approval, đo blast radius, và giữ nhỏ nhất có thể.
10. Retest positive+negative+boundary và kiểm hệ thống đã hết lỗi; theo dõi p95/percentile authentication delays.

### 20.2. Khi IdP phát time window quá ngắn

IdP có thể phát bearer hạn 30 giây, nhưng browser đã mất 40 giây do MFA/redirect/proxy. Nếu đồng hồ đúng, SP reject là hợp lý. Phối hợp IdP để đặt validity window cân đối theo SAML Web SSO profile và risk policy, tối ưu redirect/network latency. Không dùng một skew lớn để thay đổi lifetime từ IdP mà không có review.

### 20.3. Khi IdP timestamp bị đặt theo múi giờ sai

Nếu IdP ghi `2026-11-07T10:00:00Z` trong khi thực tế là giờ UTC+7 chưa đổi, timestamp bị lệch 7 giờ. Đây là **bug phát timestamp**, không phải case nên chữa bằng clockSkew 7 giờ. Sửa issuer serialization và NTP; test `Instant` tương đương giữa `Z` và `+07:00`.

### 20.4. Khi có dấu hiệu replay/malicious reuse

Nếu nhiều POST trùng assertion ID/timestamp trong cùng window, đừng tự mở thời gian để user đăng nhập. Kiểm tra replay store, InResponseTo, IP/path bất thường và incident response. Ngay cả khi timestamp valid, reused signed assertion không được tự động tạo session mới. Không log raw SAMLResponse trong incident tickets.

## 21. Production checklist

- [ ] IdP/SP clocks đồng bộ NTP, đo offset theo node/region.
- [ ] SAML timestamp comparisons dựa trên UTC `Instant` và precision phù hợp.
- [ ] `Conditions@NotBefore` inclusive; `NotOnOrAfter` exclusive được kiểm ở boundaries.
- [ ] Validity interval invalid/zero-length bị reject.
- [ ] Bearer `SubjectConfirmationData@NotOnOrAfter` được kiểm **độc lập**.
- [ ] Bearer `Recipient`/`InResponseTo` được validate theo Web SSO profile.
- [ ] Allowed skew S có owner, nhỏ, versioned và test ±S.
- [ ] Không dựa sample 10 phút trong docs làm production default.
- [ ] Không bypass default validators hoặc globally ignore expiry để giảm 401.
- [ ] Trusted signature, issuer, audience, destination và replay checks vẫn chạy.
- [ ] SAML fixtures negative cases được **re-sign sau khi chỉnh timestamps**.
- [ ] Positive control và negative time control cùng signing key/profile.
- [ ] Test hết hạn Assertion không tạo authenticated SecurityContext/session.
- [ ] Replay cache, InResponseTo store và session isolation kiểm thử E2E.
- [ ] Phân biệt `AuthnInstant`/`SessionNotOnOrAfter` với `Conditions` lifetime.
- [ ] Test missing Conditions attributes theo SP security policy.
- [ ] Java17 unit tests deterministic bằng `Clock.fixed`, không `sleep`/manual clock changes.
- [ ] Test time zone offset, precision 1ms và parser invalid dates.
- [ ] CI/staging test NTP drift, multiple pods và failover.
- [ ] Monitoring có allowlisted reason codes, không raw SAML XML/PII.
- [ ] Spring Security/OpenSAML version cụ thể được pin và regression tested.
- [ ] Max assertion age, session TTL và reauthentication freshness có policy riêng.
- [ ] Incident runbook ưu tiên sửa clock/IdP issuance, không kéo dài skew vô hạn.

## 22. Câu hỏi ôn tập

**1. `NotBefore` bằng giờ hiện tại có hợp lệ không?**  
Có, mốc bắt đầu **inclusive**.

**2. `NotOnOrAfter` bằng giờ hiện tại có hợp lệ không (S=0)?**  
Không, mốc kết thúc **exclusive**.

**3. Khi S=60s, `NotOnOrAfter=now-60s` thì thế nào?**  
Theo quy tắc grace hai phía minh họa, **reject**, vì `now=NotOnOrAfter+S` là upper boundary không bao gồm.

**4. `NotBefore=now+60s` có được nhận khi S=60s?**  
Có thể pass temporal theo công thức `now+S>=NotBefore`, nhưng các checks khác vẫn bắt buộc.

**5. Conditions còn hạn thì bearer SubjectConfirmationData hết hạn có được login không?**  
Không. Bearer confirmation là điều kiện độc lập.

**6. Vì sao `AuthnInstant` cũ không tự chứng minh Assertion hết hạn?**  
Nó ghi thời điểm user xác thực tại IdP; khi IdP SSO còn, Assertion mới có thể được phát sau. MaxAuthAge là chính sách riêng.

**7. Có thể xem chữ ký đúng là thời gian đúng không?**  
Không. XML chữ ký có thể giữ hiệu lực toán học dù Assertion đã quá hạn.

**8. SAML Core yêu cầu bắt buộc cả NotBefore và NotOnOrAfter trong Conditions không?**  
Không. Các biên có thể không hiện diện; SAML Web SSO và SP có thể thêm profile/lifetime policy chặt hơn.

**9. Làm thế nào để chứng minh test đã fail vì expiry chứ không phải invalid signature?**  
Tạo fixture với timestamp expired **trước khi ký**, ký lại bằng trusted IdP test key, chứng minh positive control pass.

**10. Test dùng `Thread.sleep` có bất lợi gì?**  
Flaky/chậm phụ thuộc CI clock và scheduling; dùng `Clock.fixed` cho unit tests.

**11. Đồng hồ SP lệch +2 phút nhưng IdP đúng thì sao?**  
Có thể reject assertion gần end quá sớm; kiểm NTP/time sync, không tự nới skew quá lớn.

**12. SAML Response có `IssueInstant` mới thì Assertion Conditions expired vẫn pass được không?**  
Không. IssueInstant không thay Conditions expiry.

**13. Replay Assertion trong validity window có bị reject không?**  
Phải reject theo replay/correlation policy; thời gian valid không cho phép tái sử dụng tùy ý.

**14. Sau khi user login hợp lệ, Conditions expiry đến thì app session có tự hết không?**  
Không tự động chỉ vì Assertion expires; local session và `SessionNotOnOrAfter` có lifecycle/policy riêng.

**15. Spring Security hiện hành cấu hình skew qua API nào?**  
`OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(Duration)`, sau đó `setAssertionValidator`; check version.

**16. Có nên thay validator mặc định bằng hàm luôn success để giải quyết expired login?**  
Không. Đó là lỗi bảo mật, có thể bỏ issuer/audience/subject checks.

**17. Nếu hai pods trả quyết định khác nhau với cùng Assertion?**  
Kiểm clock offsets, config skew, signing trust state và replay routing theo từng pod/region.

**18. Một file fixture bị sửa `NotOnOrAfter` sau khi ký có đủ để chứng minh expiry validation không?**  
Không. Failure có thể chỉ do signature sai; phải re-sign và isolate.

**19. `SubjectConfirmationData@NotBefore` có nên dùng để test Web SSO bearer NotBefore không?**  
Không trộn với `Conditions@NotBefore`. Web Browser SSO bearer profile cơ bản cấm `NotBefore` trong bearer confirmation; test schema/profile riêng.

**20. Nới skew 1 ngày để tránh lệch đồng hồ có an toàn không?**  
Không. Nó kéo dài cửa sổ chấp nhận expired/future assertions; cần sửa NTP/IdP issuance và dùng tolerance có giới hạn.

## 23. Tài liệu và tiêu chuẩn tham khảo

- [OASIS SAML 2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Conditions`, `NotBefore`/`NotOnOrAfter` semantics, subject confirmation, AuthnStatement và timestamp data types.
- [OASIS SAML 2.0 Profiles — Web Browser SSO](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): bearer `SubjectConfirmationData`, `Recipient`, `NotOnOrAfter`, request correlation và session guidance.
- [OASIS SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0-cd-02.html): Web SSO bearer expiry, Recipient, InResponseTo và SessionNotOnOrAfter.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `OpenSaml5AuthenticationProvider`, AssertionValidator `clockSkew(Duration)`, customizing defaults và SAML2 validation.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): ACS filter, signature/time/subject/audience verification pipeline.
- [Spring Security — SAML2 Migration Notes](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html): `OpenSaml5AuthenticationProvider`/`AssertionValidator` API and version evolution.
- [OpenSAML 5.2.2 — SAML2AssertionValidationParameters](https://shibboleth.net/api/java-opensaml/5.2.2/org/opensaml/saml/saml2/assertion/SAML2AssertionValidationParameters.html): `CLOCK_SKEW` parameter and time-related validation context.
- [Java 17 — java.time.Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed` và dependency-injected clock cho deterministic tests.
- [Java 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): UTC instant comparison và precision.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature validation, replay, protocol restrictions và secure XML.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): redaction SAML Assertions, secrets, session IDs và identity data.

**Ghi nhớ:** `NotBefore` là **inclusive**, `NotOnOrAfter` là **exclusive**. Với skew có giới hạn S, kiểm thử cả **now+S** ở lower bound lẫn **NotOnOrAfter+S** ở upper bound; mốc cuối vẫn phải bị từ chối. `Conditions` và `SubjectConfirmationData` có **cửa sổ độc lập**, trong khi `AuthnInstant`, `IssueInstant` và `SessionNotOnOrAfter` giải quyết các câu hỏi khác. Mọi integration test expiration phải dùng **Response/Assertion được ký hợp lệ** với timestamp thiết lập **trước khi ký**, giữ issuer/audience/recipient/InResponseTo đúng và có replay protection. Khi thời gian lệch, ưu tiên sửa đồng hồ/NTP và IdP issuance, **không tắt temporal validator hay nới skew không kiểm soát**.