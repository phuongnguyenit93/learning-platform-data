# Giới hạn của xác thực giả lập khi kiểm thử bộ kiểm chứng SAML thực tế

## 1. Bài toán: test đăng nhập xanh có chứng minh SAML Response đáng tin?

Một ứng dụng Spring Boot dùng **Spring Security SAML 2.0** để cho nhân viên đăng nhập qua Identity Provider (IdP). Đội phát triển viết:

~~~java
@Test
@WithMockUser(username = "linh", roles = "ANALYST")
void analystCanReadReports() throws Exception {
    mvc.perform(get("/reports"))
       .andExpect(status().isOk());
}
~~~

Bài test trên có giá trị: endpoint được phép xử lý request mang principal và role giả như kỳ vọng. Nhưng test này **không đi qua bộ kiểm chứng SAML Response thực tế**. Nó không chứng minh chữ ký XML do IdP đáng tin cậy phát, không kiểm `AudienceRestriction`, `Recipient`, `Destination`, `Issuer`, `InResponseTo`, giới hạn thời gian, decryption, chống replay hay chính sách tin cậy certificate.

Đây là bài Knowledge thuộc **Spring Security - federation → Kiểm thử SAML2**, chủ đề **“Giới hạn của xác thực giả lập khi kiểm thử bộ kiểm chứng SAML thực tế”**.

### Mục tiêu học tập

Sau bài này, bạn sẽ:
1. Phân biệt test authorization bằng mock user với test **SAML cryptographic/protocol verification**.
2. Hiểu chuỗi Spring Security `Saml2WebSsoAuthenticationFilter → Saml2AuthenticationTokenConverter → AuthenticationManager → OpenSAML provider → Saml2Authentication`.
3. Giải thích những trường hợp kiểm thử với `@WithMockUser`, `MockMvc.with(user())`, `with(authentication())` và mock manager là hợp lý, cũng như phạm vi chúng không kiểm tra.
4. Thiết kế các tầng unit/slice, provider-level, ACS HTTP integration và browser/IdP E2E.
5. Sinh **fixtures có chữ ký hợp lệ** bằng khóa thử nghiệm, phân biệt lỗi signature với lỗi semantic validators.
6. Kiểm issuer/trust/certificate, audience, destination, recipient, subject, time, correlation, encryption và replay.
7. Xử lý saved AuthnRequest/RelayState và khác biệt SP-initiated vs IdP-initiated.
8. Test các ca negative nhưng **không vô hiệu hóa xác minh chữ ký trong Spring**.
9. Viết MockMvc tests chạy filter/provider thật và xác nhận SecurityContext sau callback.
10. Hiểu rủi ro validator customization khi nâng Spring Security/OpenSAML.
11. Chạy demo Java 17 độc lập phân loại độ mạnh bằng chứng test, không giả làm SAML verifier.
12. Chuẩn bị ma trận QA và runbook release.

**Môi trường:** Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x, SAML 2.0 Web Browser SSO. OpenSAML provider và customization API khác nhau theo bản; các đoạn Spring code phải kiểm chứng theo dependency thật. Domain `sp.example.org`/`idp.example.org` và keys trong bài là dữ liệu giả.

---

## 2. Hai câu hỏi kiểm thử khác hẳn nhau

**Câu hỏi A — nếu một người dùng đã được xác thực và có quyền, ứng dụng hoạt động thế nào?**

Ví dụ:
- Analyst được đọc báo cáo, viewer không được sửa.
- Admin không được truy cập tenant khác chỉ vì có vai trò admin.
- `@PreAuthorize`, `AuthorizationManager`, controller hoặc business service hoạt động đúng.
- Mapping local principal sang account ID, role và resource ACL được kiểm.

Đây là phạm vi phù hợp với mock user, MockMvc request post-processors và stubbed downstream dependencies.

**Câu hỏi B — người dùng này có thực sự được IdP hợp lệ xác nhận cho SP này trong SAML Response không?**

Ví dụ:
- XML Signature có thật, valid, bảo vệ đúng XML object?
- Chữ ký đến từ verification key được đăng ký cho đúng IdP?
- Response/Assertion có đúng Issuer, Audience, Destination, Recipient?
- Time/SubjectConfirmation/Request correlation hợp lệ?
- Assertion có bị replay, sửa chữ ký hoặc chưa decrypt được?
- IdP B có thể giả dữ liệu IdP A không?

Đây là **SAML protocol validation**. Tạo sẵn `Authentication` không trả lời những câu hỏi ấy.

| Test | Bảo đảm chính | Không chứng minh |
| --- | --- | --- |
| `@WithMockUser` | Logic truy cập với principal/roles giả | Chữ ký SAML, issuer, audience, time |
| `with(user("linh"))` | SecurityContext được nạp vào request test | IdP thực sự xác thực linh |
| `with(authentication(fake))` | Code sau khi đã có Authentication | Provider xác thực XML |
| Mock AuthenticationManager success | Success handling sau manager | OpenSAML validators đã chạy |
| POST XML tự dựng không ký | Parser/error path của unsigned/malformed XML | Positive verifier |
| Real OpenSAML provider + signed fixture | Protocol/crypto validation theo cấu hình | Browser/cookie/proxy đầy đủ |
| MockMvc ACS + real provider | Filter/converter/provider trên Servlet request | Tương thích IdP/browser production |
| Staging IdP/browser E2E | Protocol interoperability + network/browser | Tất cả negative security cases |

**Câu kiểm tra:** bài test có **thực sự gọi provider xử lý SAML Response XML** không? Nếu không, đừng báo “SAML signature validator passed”.

## 3. Luồng SAML thực tế trong Spring Security

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring SP
    participant IDP as Test IdP
    B->>SP: GET /private
    SP-->>B: Redirect /saml2/authenticate/test-idp
    B->>SP: GET AuthnRequest endpoint
    SP->>SP: Sinh AuthnRequest; lưu state nếu cấu hình
    SP-->>B: Redirect IdP với SAMLRequest/RelayState
    B->>IDP: Chuyển AuthnRequest tới IdP
    IDP-->>B: HTML form có signed SAMLResponse
    B->>SP: POST /login/saml2/sso/test-idp
    SP->>SP: Saml2WebSsoAuthenticationFilter
    SP->>SP: Converter decode response, resolve relying party
    SP->>SP: AuthenticationManager -> OpenSAML provider
    SP->>SP: Verify signatures/trust/conditions/decryption
    alt Valid
        SP->>SP: Saml2Authentication / SecurityContext
        SP-->>B: Thành công theo login flow
    else Invalid
        SP->>SP: AuthenticationFailureHandler/EntryPoint
        SP-->>B: Error/redirect; không cấp Authentication
    end
~~~

Những component đáng nhớ:

- `Saml2WebSsoAuthenticationRequestFilter`: tạo AuthnRequest để bắt đầu SP-initiated login.
- `Saml2WebSsoAuthenticationFilter`: nhận form POST `SAMLResponse` tại ACS.
- `Saml2AuthenticationTokenConverter`: lấy response và tìm đúng `RelyingPartyRegistration`.
- `AuthenticationManager`: chuyển token tới provider.
- `OpenSaml4AuthenticationProvider` ở các cấu hình Spring Security 6.x hoặc `OpenSaml5AuthenticationProvider` trong bản hỗ trợ tương ứng và Spring Security 7.x.
- OpenSAML provider: verify signature, kiểm issuer/destination, decrypt, validate assertion/time/subject/audience, tạo Authentication.
- `SecurityContext`: lưu kết quả sau khi validation thành công.

**Không kết luận một HTTP 302 từ ACS là login thành công**: nó có thể redirect về IdP hoặc trang lỗi. Đối chiếu authentication state và endpoint được bảo vệ ở request tiếp theo.

### Đường mock bỏ qua điều gì?

~~~text
Mock request + with(user("analyst"))
  -> SecurityContext đã có user
  -> AuthorizationFilter
  -> Controller
~~~

Đường này **không** khởi tạo signed AuthnRequest, không decode SAMLResponse, không lookup trusted IdP certificate, không chạy XML Signature và assertion validators. Đây là giới hạn có chủ đích để test business logic nhanh, **không phải lỗ hổng tự thân của MockMvc**.

## 4. Bốn tầng kiểm thử và cách đặt tên kết quả

| Tầng | Mục tiêu | Công cụ | Tên kết quả trung thực |
| --- | --- | --- | --- |
| T1 — Unit/Slice | Authorization/business policy với user giả | JUnit, `@WithMockUser`, `user()`, Mockito | `AUTHORIZATION_MOCK_PASS` |
| T2 — Real Provider | XML crypto/trust + semantic conditions | OpenSAML provider thật, signed fixtures | `SAML_VERIFIER_PASS` |
| T3 — ACS integration | Filter, request converter, repository, session, redirect | `@SpringBootTest`, MockMvc, filters/provider thật | `SAML_ACS_INTEGRATION_PASS` |
| T4 — Browser/IdP E2E | IdP metadata, browser POST, TLS, proxy, SameSite/cookies | Staging test IdP/browser | `SAML_E2E_PASS` |

T1 có thể chạy mọi commit, T2 thường chạy khi thay authentication, T3 trong CI và T4 trong staging/nightly/release. Nhưng một **positive E2E** không thay mọi negative tests T2; một **mock authorization test** không thay T2/T3.

### Tên test phải đúng evidence

- Đúng: `analystCanReadOwnReportWithMockPrincipal()`.
- Đúng: `signedAssertionWithWrongAudienceIsRejected()` khi fixture chữ ký vẫn hợp lệ.
- Sai: `idpSignatureValidated()` khi test chỉ sử dụng `@WithMockUser`.
- Sai: `samlLoginSucceeded()` khi assertion duy nhất là HTTP 302 từ ACS.
- Sai: `replayPrevented()` khi response chỉ bị chặn do hết hạn.

## 5. @WithMockUser có ích nhưng không chứng minh SAML

Spring Security Test cho phép test gán một principal tùy chọn vào SecurityContext:

~~~java
package com.example.portal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "linh", roles = "ANALYST")
    void analystCanReadReport() throws Exception {
        mvc.perform(get("/reports"))
                .andExpect(status().isOk());
    }
}
~~~

**Điều kiện:** project phải có `GET /reports` thực sự cho analyst trả 200, Spring Boot Test, Spring Security Test và filter chain phù hợp. Đây là một **class integration test trong Spring project**, không có `main()` và không biên dịch bằng `javac` độc lập. Nếu endpoint cần tenant/object-level authorization, phải bổ sung setup và assertions tương ứng.

Những trường hợp mock rất hữu ích:
1. Thiếu role bị 403.
2. Đúng role nhưng sai tenant vẫn bị 403.
3. User disabled theo app account gate bị deny.
4. Controller không lộ dữ liệu người khác.
5. Method security không bị bỏ qua vì code refactor.
6. Khi service/repository lỗi, error handling không tiết lộ thông tin.

**Nhưng** user giả `linh` không cần có account ở IdP, không có SAML XML và không có signature. Vậy test chỉ chứng minh behavior **sau authentication**, không chứng minh nguồn authentication đáng tin.

## 6. MockMvc.with(user()) và with(authentication()) cũng bỏ qua verifier

Ví dụ Spring Security MockMvc:

~~~java
mvc.perform(get("/reports")
        .with(user("linh").roles("ANALYST")));
~~~

Với authentication tự tạo:

~~~java
mvc.perform(get("/reports")
        .with(authentication(preparedAuthentication)));
~~~

Hai snippet cần test class/fields/imports phù hợp, và `preparedAuthentication` là object do test tự tạo. Spring Security docs cũng hỗ trợ `securityContext(testContext)`.

Các post-processors này **nạp security state giả**. Chúng có thể test controller, authorization managers và session-related behavior, nhưng không:
- Parse SAMLResponse;
- Verify XML Signature;
- Kiểm RelyingPartyRegistration;
- Decrypt EncryptedAssertion;
- Kiểm issuer/recipient/time;
- Consume correlation state;
- Detect replay theo SAML policy.

Với `MockMvcBuilders.standaloneSetup`, còn phải đưa Spring Security `FilterChainProxy` hoặc `springSecurity()` vào test nếu muốn assertions thực sự phản ánh security filters. Khi dùng Boot auto-configured MockMvc cũng cần xác minh security filters được đăng ký.

## 7. Mock AuthenticationManager: một integration test giả mạo dễ mắc

Ví dụ anti-pattern:

~~~java
// Mã minh họa trong test; không dùng làm provider validation test.
when(authenticationManager.authenticate(any()))
        .thenReturn(fakeAuthenticatedSaml2Authentication);
~~~

Nếu `AuthenticationManager` được Mockito/mock bean trả success, provider OpenSAML không chạy. Bất kỳ request nào được filter chuyển tới manager giả có thể được test xem như “authenticated”, kể cả response vốn unsigned hoặc sai issuer.

### Những thứ phải giữ thật ở tầng T2/T3

- `Saml2WebSsoAuthenticationFilter` và token converter khi kiểm ACS.
- `RelyingPartyRegistrationRepository` có IdP entityId, SP entityId, ACS và trusted test verification credentials.
- `AuthenticationManager/ProviderManager` có **OpenSAML provider thực**.
- Response/assertion validators đúng configuration.
- Decryption credentials nếu production có encrypted assertions.
- AuthnRequest repository nếu kiểm SP-initiated correlation.
- Failure handler + security context persistence phù hợp.

Có thể mock business repository hay remote API **sau khi SAML validation** nếu điều đó không xóa nguyên nhân muốn test. Nhưng không mock chính component mà test tuyên bố kiểm chứng.

## 8. Ví dụ SAML Response để hiểu cấu trúc, không phải login fixture hợp lệ

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/test-idp"
    InResponseTo="_request-001">
  <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion-001"
      IssueInstant="2026-11-07T04:00:00Z" Version="2.0">
    <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>
    <saml:Subject>
      <saml:NameID>opaque-user-123</saml:NameID>
      <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
          InResponseTo="_request-001"
          Recipient="https://sp.example.org/login/saml2/sso/test-idp"
          NotOnOrAfter="2026-11-07T04:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="2026-11-07T03:59:00Z"
                     NotOnOrAfter="2026-11-07T04:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://sp.example.org/saml2/metadata</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
~~~

**XML này không có XML Signature** và không thể được dùng như một successful SAML login fixture. SAML StatusCode Success hoặc NameID không chứng minh IdP đã xác thực người dùng. Thời gian và IDs chỉ là giả.

### Những quy tắc cần test

| Rule | Vấn đề bảo mật |
| --- | --- |
| Signature + signed references | Nội dung không bị sửa/ghép sai |
| Trusted verification certificate | Chỉ tin IdP được phê duyệt |
| Issuer | Response/Assertion đến đúng IdP |
| Destination | Response được gửi đúng ACS |
| AudienceRestriction | Assertion dành cho đúng SP |
| Bearer SubjectConfirmation | Recipient, expiry và InResponseTo theo profile |
| Time conditions | Không chấp nhận assertion quá sớm/quá hạn |
| Request correlation | Không gán response cho phiên/request khác |
| Replay/OneTimeUse | Không dùng lại assertion trái chính sách |
| Decryption | Xử lý encrypted identity/attributes bằng đúng key |
| Principal/roles | Không map dữ liệu chưa xác minh thành quyền |
| XML parser safety | Không XXE/signature wrapping/ambiguous ID |

Không mọi rule đều được thực thi giống nhau trên mọi phiên bản/customization; cần kiểm code/config đang chạy.

## 9. XML Digital Signature: tồn tại Signature tag chưa đủ

Một bộ kiểm chứng SAML cần xác nhận:
1. XML Signature có giá trị mật mã hợp lệ.
2. Verification key thuộc **trusted IdP metadata/certificate** đã cấu hình.
3. Signed reference bao phủ **Response/Assertion mà SP sẽ dùng**.
4. XML ID references và namespace không bị signature wrapping/confusion.
5. Nếu có nhiều assertions, code không lấy principal từ assertion chưa được bảo vệ đúng.
6. Algorithms/transform policies được chấp nhận theo cấu hình.
7. Không tin certificate do chính XML chưa được tin tự cung cấp làm root of trust.

**Không tự regex `ds:Signature`, `NameID`, `Attribute` rồi tạo Authentication.** Dùng Spring Security/OpenSAML.

### Trường hợp test xấu

~~~text
Sinh XML có NameID=admin
Base64 encode XML
POST tới ACS
Test kỳ vọng login thành công
~~~

Nếu Response/Assertion chưa có chữ ký tin cậy, **provider hợp lệ phải từ chối theo signing policy**. Nếu test lại pass, xem:
- AuthenticationManager/provider có bị mock không?
- ACS filter có chạy không?
- Test đã tạo Authentication từ trước không?
- Có custom provider bỏ verification không?
- Test chỉ xem HTTP status thay vì SecurityContext không?

Không bao giờ sửa bằng cách tắt signature validation trên profile test rồi dùng kết quả đó chứng minh SAML an toàn.

## 10. Một lỗi rất phổ biến: sửa Audience sau khi ký

Giả sử bạn có một fixture **đã ký**:

~~~text
Audience = https://sp.example.org/metadata
Signature = valid
~~~

Bạn mở XML và đổi thành:

~~~text
Audience = https://other-sp.example.org/metadata
Signature = now invalid, because signed content changed
~~~

Provider từ chối. Nhưng test tên `wrongAudienceShouldBeRejected` có thể pass **chỉ do chữ ký sai**, trong khi validator AudienceRestriction đã bị vô hiệu hóa.

**Muốn kiểm semantic rule**, hãy dựng fixture có trường sai từ đầu và **ký hợp lệ bằng private key của test IdP được SP tin cậy**. Các field khác (issuer/recipient/time/correlation) phải đúng để request đi tới đúng validator.

### Các ca negative nên tạo thế nào?

| Rule đang test | Fixture cần |
| --- | --- |
| Signature tampering | Signed fixture rồi sửa byte trong signed content, không ký lại |
| Untrusted signer | Signed fixture bằng key B không nằm trong trust credentials của IdP A |
| Wrong issuer | Signed fixture có issuer sai, trong khi các điều kiện độc lập phù hợp |
| Wrong audience | Audience sai **trước khi ký**, chữ ký vẫn hợp lệ |
| Wrong destination | Destination sai trước khi ký |
| Wrong recipient | Bearer SubjectConfirmationData Recipient sai trước khi ký |
| Expired | Điều kiện thời gian quá hạn, fixture được ký hợp lệ |
| Future NotBefore | NotBefore vượt skew, chữ ký hợp lệ |
| Wrong InResponseTo | Signed response tham chiếu request ID không tồn tại/không khớp |
| Missing signature | Response/Assertions thiếu chữ ký bắt buộc |
| Replay | Cùng signed assertion/response được gửi nhiều lần trong điều kiện còn hạn |

Test failure nên kiểm **không có Authentication mới**. Nếu framework expose structured error, có thể kiểm category; không regex raw exception message có thể chứa PII.

## 11. Chữ ký Response vs Assertion và multi-assertion

SAML cho phép chữ ký ở Response và/hoặc Assertion theo profile và IdP/SP contract. Spring Security docs mô tả logic verification tương ứng, không thể mặc định mọi Assertion luôn có chữ ký riêng nếu entire Response signed được provider chấp nhận.

Bộ test nên có:
1. Signed Response với assertions phù hợp.
2. Signed Assertion trong Response theo contract.
3. Response và Assertion đều signed.
4. Không có signature hợp lệ.
5. Signed Response nhưng Assertion bị thay sau signing.
6. Signed Assertion A với Assertion B được thêm vào XML.
7. Duplicate IDs/ambiguous signed references.
8. Wrong signer nhưng cùng NameID/group attributes.
9. Assertion không được kiểm nhưng có role ADMIN.
10. Multi-assertion với các statements khác nhau theo provider behavior.

**Không lấy thuộc tính từ bất kỳ Assertion nào mà chưa qua các validation yêu cầu**. Test nên nhắm tới “đúng principal/authority được tạo từ đúng assertion được xác minh”, không chỉ xem một signature method trả true.

## 12. Issuer, registrationId và tenant isolation

Giả sử SP tin hai IdPs:
- `https://idp-hr.example.org` với key A.
- `https://idp-partner.example.org` với key B.

Hai IdPs có thể cùng phát NameID `alex` hoặc cùng email. Điều đó không chứng minh cùng người.

Rủi ro:
- Test dùng chung một verification certificate cho mọi registrations;
- AuthnRequest đăng ký IdP A nhưng ACS resolver chọn B;
- Assertion Issuer khác Response Issuer;
- `registrationId` URL không khớp configured IdP;
- Signed SAML response của tenant khác tạo local admin vì email trùng;
- Metadata rotation sai môi trường nhưng test chỉ có một mocked provider.

Các test cần:
1. Signed fixture A được chấp nhận trong registration A khi hợp lệ.
2. Signed fixture B **không** được lẫn sang A.
3. Issuer sai bị từ chối ngay cả khi NameID đúng.
4. Untrusted cert bị từ chối dù XML signature tự nhất quán.
5. Local account mapping scoped theo IdP issuer và stable external subject.
6. Nếu có IdP-initiated login, routing/registration inference không làm mất tenant isolation.

Dù test chứng minh signature hợp lệ, authorization sau login vẫn phải kiểm business tenant/resource ownership.

## 13. Audience, Destination, Recipient là ba yêu cầu khác nhau

| Trường SAML | Ý nghĩa | Negative test |
| --- | --- | --- |
| `AudienceRestriction/Audience` | Đối tượng SP entityId được phép tiêu thụ assertion | Audience entityId của SP khác |
| `Response@Destination` | Nơi Response được gửi | Internal URL thay cho public ACS |
| `SubjectConfirmationData@Recipient` | Endpoint trình bearer assertion | ACS của tenant/host khác |
| `InResponseTo` | Tương quan AuthnRequest theo flow | ID không khớp |
| `Issuer` | IdP asserting party | Issuer không đăng ký |

Các trường **không đồng nghĩa**. Audience thường là SP entityId, còn Recipient/Destination thường liên quan ACS URL. Một test wrong audience không thể được thay bằng test wrong destination.

### Reverse proxy

Nếu public ACS là `https://sp.example.org/login/saml2/sso/test-idp` nhưng Spring tự nhận request scheme HTTP/host nội bộ, validation có thể fail dù IdP làm đúng.

Cần kiểm:
- SP metadata và `assertionConsumerServiceLocation`.
- Public base URL và entityId.
- Trusted forwarded host/proto headers đã được ingress strip/overwrite.
- ACS matcher/registrationId ở Spring.
- IdP ACS allow-list khớp public URL.
- Nhiều pods có cùng cấu hình.

**Đừng bỏ Destination/Recipient validation để chữa mismatch proxy.** Mock Authentication cũng không thể phát hiện trường hợp này.

## 14. Time validation: NotBefore, NotOnOrAfter và skew

SAML response/assertion có nhiều time-related fields. Kiểm:
- `Conditions@NotBefore`.
- `Conditions@NotOnOrAfter`.
- `SubjectConfirmationData@NotOnOrAfter`.
- `IssueInstant` theo profile.
- NTP/clock skew giữa SP và IdP.
- Boundaries trước/sau expiry.
- Static fixture cũ đã hết hạn.

**Một XML signed ở thời điểm tạo fixture có thể không dùng được nhiều ngày sau**. Đừng tăng clock skew hàng giờ để test pass. Có thể sinh signed fixture với time fields ở thời điểm test hoặc inject test clock đúng API nếu framework cho phép.

Ví dụ cases:
1. Điều kiện hợp lệ trong cửa sổ.
2. NotBefore tương lai ngoài skew.
3. NotOnOrAfter vừa hết hạn.
4. SubjectConfirmation hết hạn dù Conditions còn.
5. Time skew trong tolerance.
6. Time skew ngoài tolerance.
7. Fixture time mới nhưng signature untrusted (phải fail trust).
8. Assertion time hợp lệ nhưng request correlation sai.

Spring Security hỗ trợ cấu hình clock skew trên assertion validator ở các version API tương ứng. **Không suy default skew giống nhau giữa các phiên bản**.

## 15. InResponseTo, request repository và RelayState

Trong **SP-initiated SSO**, Spring tạo `AuthnRequest` và có thể lưu state/correlation trong session/repository, rồi IdP trả SAMLResponse liên hệ request đó. `RelayState` liên quan browser state/flow theo binding.

**Một test trực tiếp POST Response tới ACS không có saved AuthnRequest có thể fail đúng vì thiếu correlation.** Đừng vô hiệu hóa InResponseTo validator chỉ vì fixture được xây ngoài luồng.

### Kiểm thử đúng flow

~~~text
1. GET /saml2/authenticate/test-idp
2. SP sinh AuthnRequest ID và lưu request state
3. Test IdP đọc AuthnRequest trong redirect/binding
4. Test IdP tạo Response ký hợp lệ:
     InResponseTo đúng
     Recipient/Destination đúng
     Audience đúng
     Valid time conditions
5. Browser/test client POST SAMLResponse + RelayState
   với cùng browser session/cookie
6. SP parse/verify/correlate, tạo Authentication
7. Request tiếp theo vào protected route, kiểm principal/role
~~~

Nếu cần negative correlation, tạo **response có signature hợp lệ** nhưng `InResponseTo` của request khác hoặc missing state theo policy.

### IdP-initiated SSO

IdP-initiated unsolicited Response có thể không có AuthnRequest/InResponseTo theo trường hợp tích hợp được cho phép. Phải đánh giá riêng:
- Hệ thống có bật hỗ trợ unsolicited hay không;
- Có kiểm issuer/trust/audience/recipient/time không;
- Không có request-bound CSRF/correlation; rủi ro login CSRF/identity confusion;
- RelayState/open redirect policy;
- Những IdP nào được phép initiating flow.

**Không áp một giả định “InResponseTo luôn bắt buộc” cho mọi product/flow**, và cũng không xóa correlation bảo vệ flow SP-initiated chỉ để chấp nhận unsolicited response.

## 16. Replay: signed assertion vẫn có thể bị dùng lại

XML Signature có thể hoàn toàn hợp lệ khi attacker hoặc một browser automation gửi lại cùng Response. Chữ ký chứng minh nội dung và nguồn đã ký, **không chứng minh chưa từng được sử dụng**.

Các lớp bảo vệ:
- Condition/SubjectConfirmation expiry;
- AuthnRequest correlation và state consumption;
- OneTimeUse condition nếu IdP phát;
- Replay cache cho assertion/response ID nếu policy yêu cầu;
- Session binding;
- Cluster-wide store và atomic check nếu nhiều nodes;
- Giới hạn cửa sổ valid và monitoring.

**Không mặc định Spring Security đã thực thi global replay cache trong mọi version.** Tài liệu OpenSAML provider cho phép thêm `OneTimeUseConditionValidator` như một phần customization; cần test thực tế nếu nghiệp vụ yêu cầu “một assertion chỉ chấp nhận một lần”.

### Các ca replay cần khác nhau

| Test | Điều cần chứng minh |
| --- | --- |
| Cùng SAMLResponse được gửi lại trong cùng session | Request correlation/one-time state hoạt động |
| Replay khi response vẫn còn hạn | Không chỉ bị time validator chặn |
| Replay sau hết hạn | Chỉ chứng minh expiry denial nếu thiếu control |
| Replay qua session khác | State không phụ thuộc browser duy nhất |
| Replay qua pod khác | Shared replay/correlation store nếu cần |
| Replay đồng thời | Atomic consume chống race |
| Cùng Assertion ID, Response ID khác | Assertion-level replay policy |
| Có OneTimeUse condition | Validator thực sự xử lý OneTimeUse |

Nếu dùng chỉ `HashSet` trong một JVM, không tuyên bố bảo vệ đa vùng/multi-node.

## 17. EncryptedAssertion và decryption không thể mock

SAML có thể có:
- `EncryptedAssertion`;
- `EncryptedID`;
- `EncryptedAttribute`.

Spring Security/OpenSAML cần decryption credentials phù hợp trong `RelyingPartyRegistration`. **Signing key và encryption key không nhất thiết là một**. Một mock Authentication không thể kiểm:
- SP private key có khớp encrypted test assertion không?
- Assertion được decrypt rồi verify/validate đúng thứ tự không?
- Những attribute mã hóa có bị bỏ sót khi map roles không?
- Rotation keys/certificates có làm login fail không?

Bộ fixtures nên gồm:
1. Unencrypted signed baseline nếu profile cho phép.
2. EncryptedAssertion bằng SP test public key; app decrypt success.
3. Wrong SP decryption key; fail.
4. Corrupted ciphertext; fail.
5. EncryptedID/EncryptedAttribute nếu production sử dụng.
6. Signed Response chứa encrypted assertion.
7. Signed Assertion có encrypted attributes.
8. Key rotation overlap với test certificates.

**Không dùng production signing/decryption private keys trong CI.** Test IdP và SP test key pairs độc lập. Tất cả test artifacts phải tránh chứa thông tin người dùng thật.

## 18. Parser và XML signature wrapping

Ngoài chữ ký, XML có những trường hợp an toàn cần kiểm:
- XML DTD/external entity resolution (XXE);
- Entity expansion/oversized XML/DoS;
- Duplicate XML IDs;
- Signature reference không trỏ đến assertion mà app đang dùng;
- Multiple assertions/AttributeStatements khác nhau;
- Namespace confusion/canonicalization;
- Untrusted X509Data embedded trong XML;
- Malformed Base64/invalid XML;
- XML parser không tự mở URL/file từ input.

Không tự parse SAML bằng regex trích `NameID`. Dùng OpenSAML/Spring Security có security configuration phù hợp.

### Một payload minh họa cho parser-negative test

~~~xml
<!DOCTYPE samlp:Response [
  <!ENTITY fake SYSTEM "file:///nonexistent-test-only">
]>
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:Status>&fake;</samlp:Status>
</samlp:Response>
~~~

Payload chỉ minh họa nguy cơ entity, **không phải SAML success fixture**. Negative test cần bảo đảm parser không resolve external entity và không tạo Authentication. Đừng để fixture thử nghiệm truy cập files/network nhạy cảm.

## 19. Thiết kế signed fixtures an toàn

Để tạo một valid fixture thật:
1. Tạo **test IdP entityID** riêng.
2. Dùng **test signing private key**, đưa public cert vào SP test trusted verification credentials.
3. Dùng SP entityId, public ACS, registrationId chính xác.
4. Sinh AuthnRequest ID và tương quan state khi test SP-initiated.
5. Sinh Response/Assertion time conditions hợp lệ.
6. Chọn signing scope phù hợp: signed Response hoặc Assertion theo profile.
7. Tạo XML Signature sau khi đã điền tất cả dữ liệu được ký.
8. Đặt principal/attributes giả, không dùng email/PII thật.
9. Encode đúng HTTP-POST binding.
10. Xóa/rotate state nếu test chạy song song hoặc nhiều nodes.

Có thể dùng một IdP thử nghiệm độc lập hoặc OpenSAML fixture factory được test. **Không “ký” bằng cách gắn một thẻ SignatureValue giả** và không lấy công cụ mã hóa Base64 làm thay signature.

### Ba nhóm fixture

**VALID:** signed/trusted, đúng audience/recipient/issuer/time/correlation.

**INVALID_CRYPTO:** unsigned, tampered signature, untrusted certificate, wrong reference.

**INVALID_SEMANTIC_BUT_SIGNED:** wrong audience/destination/recipient/issuer/time/correlation mà **signature vẫn hợp lệ** bằng trusted lab key. Nhóm thứ ba là điều kiện để xác nhận semantic validators hoạt động.

### Kiểm soát fixture freshness

- Generate fixtures theo test clock, không dùng static response đã hết hạn.
- Tránh random IDs trùng giữa test runs.
- Khi test replay, **chủ ý** dùng lại ID và lưu control run.
- Lưu fixture provenance, issuer, signing key alias (không private key), expected rule.
- Không đưa test IdP trust certificate vào production SP configuration ngoài quy trình riêng.
- Một fixture từ một IdP SaaS staging có thể chứa state chỉ hợp lệ trong ít phút; không gửi lại sau nhiều ngày để kiểm positive login.

## 20. Provider-level test: tập trung vào validation nhưng chưa đủ E2E

Ở T2, dùng:
- `Saml2AuthenticationToken` chứa real Base64 SAMLResponse theo constructor/API của version.
- OpenSAML provider thật.
- RelyingPartyRegistration với test IdP verification certificate và test SP decryption credential.
- Valid/invalid signed fixtures.
- Assertion/response validators production-like.

Kiểm:
- Valid fixture → Authentication thành công theo policy.
- Invalid fixture → AuthenticationException hoặc failure result; không tạo Authentication.
- Principal/attributes/authorities đúng assertion được xác minh.
- Error category nếu có structured evidence.

**Không truyền `Saml2Authentication` đã tạo sẵn vào provider test**. Nó là output của authentication, không phải SAMLResponse input cần verify.

### Giới hạn của provider test

Nó không đảm bảo:
- URL ACS nhận POST đúng;
- CSRF filter exception/matcher đúng;
- AuthnRequest repository lưu/request correlation qua browser;
- Session fixation/cookie persistence;
- Reverse proxy X-Forwarded-Host/Proto, TLS;
- Browser HTML POST form encoding;
- Redirect và RelayState;
- Metadata fetch/certificate rollover vận hành.

Đó là lý do cần T3 và T4.

## 21. ACS HTTP integration test với MockMvc

Spring Security default thường nhận:

~~~http
POST /login/saml2/sso/test-idp HTTP/1.1
Host: sp.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=[TEST_SESSION]

SAMLResponse=[BASE64_SIGNED_RESPONSE]&RelayState=[STATE]
~~~

Các chuỗi trong dấu ngoặc vuông chỉ minh họa, không phải credentials hợp lệ.

### Skeleton test Spring Boot

~~~java
package com.example.saml;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class SamlAcsIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void malformedSamlResponseIsProcessedBySecurityChain()
            throws Exception {

        MockHttpSession browser = new MockHttpSession();
        var response = mvc.perform(
                post("/login/saml2/sso/test-idp")
                        .session(browser)
                        .param("SAMLResponse", "not-base64"))
                .andReturn();

        // Skeleton only: replace with assertions that:
        // 1. No successful Saml2Authentication exists in browser state.
        // 2. A protected route stays inaccessible after callback.
        // 3. The configured failure handler was invoked.
        // 4. No sensitive SAML data appears in response/logs.
        org.junit.jupiter.api.Assertions.assertNotNull(response);
    }
}
~~~

**Giới hạn rõ ràng:** chỉ assert `assertNotNull(response)` **không đủ chứng minh verifier đã từ chối**; skeleton chỉ minh họa cách HTTP request chạm ACS trong test app. Test production phải thêm assertions theo session/response contract của dự án. `@SpringBootTest` cần thực sự load Spring SecurityFilterChain và OpenSAML provider, không mock manager. Nếu test không có relying party registration, callback có thể fail vì configuration trước khi XML parse.

### Quy trình tích hợp đầy đủ hơn

~~~text
arrange:
  Boot app + SecurityFilterChain thật
  IdP test cert trong RelyingPartyRegistration
  AuthnRequest repository/session thật
  Test IdP có key pair ký phù hợp
  Test browser bắt đầu GET /saml2/authenticate/test-idp

act:
  Test IdP đọc AuthnRequest ID
  Tạo signed SAMLResponse với exact InResponseTo/Recipient/Audience
  Browser dùng cùng cookie/session POST SAMLResponse + RelayState

assert:
  ACS/filter/provider chạy thành công hoặc thất bại theo fixture
  Valid response tạo đúng principal/role/account session
  Invalid response không tạo Authentication mới
  Protected endpoint sau login phù hợp
  Không lộ SAMLResponse/PII trong HTTP response/log
~~~

### Kiểm CSRF

IdP HTTP-POST tới ACS thường không có CSRF token của Spring app. Spring SAML2 integration có handling cho callback theo framework; nếu thêm custom security chains/CSRF matchers, cần test thật. **Không tắt CSRF toàn ứng dụng** chỉ vì ACS trả 403; kiểm filter order, matcher, callback path, method và Content-Type.

### Kiểm HTTP 302 đúng nghĩa

- Redirect tới protected return URL sau login có thể là success.
- Redirect về login/error có thể là failure.
- Status 302 không phải SAML StatusCode.
- Dùng Browser/session tiếp theo để xác định user **đã authenticated chưa**.

## 22. Kiểm local user/role mapping sau khi protocol valid

Provider có thể tạo `Saml2Authentication` với NameID và SAML attributes. Ứng dụng phải tiếp tục:
- Lookup app account theo stable identity + issuer scope;
- Không auto-link bằng email/UPN chỉ vì claim giống nhau;
- Kiểm account ACTIVE, tenant membership;
- Ánh xạ group attributes → local GrantedAuthorities theo approved policy;
- Xử lý multi-valued AttributeStatement đúng;
- Check resource ownership và object-level ACL;
- Invalidate/refresh session/role khi user bị disable/chuyển tổ chức;
- Tránh cấp ADMIN theo arbitrary `groups` attribute chưa được kiểm.

So sánh:

~~~text
Mock:
  username = linh
  roles = [FINANCE_ADMIN]
  expected = 200

SAML thật:
  NameID = opaque-4ab2
  groups = [finance-viewers]
  app account = DISABLED
  resource tenant = people
  expected = DENY
~~~

Hai kết quả khác nhau **không mâu thuẫn**. Mock test không hề đi qua verified SAML identity + account policy.

## 23. Replay tests cần multi-session và multi-node nếu có SLA

Một lưu ý đặc biệt: test replay cùng SAMLResponse sau nhiều phút có thể fail chỉ vì expiry. Để kiểm replay thực:
1. Dùng signed valid assertion còn hạn.
2. Cho một lượt login hợp lệ đầu tiên.
3. Replay cùng response/assertion trước expiry.
4. Thử lại trong cùng session, session khác và node khác theo topology.
5. Nếu yêu cầu OneTimeUse, xác nhận validator/cache thực sự enforce.
6. Kiểm concurrent duplicate submissions và atomicity.
7. Theo dõi Assertion ID/Response ID theo policy nhưng không log raw XML/tokens.
8. Không cho session B thừa hưởng Authentication của A.

**Không tuyên bố “replay prevented” chỉ vì test IDP-generated Response đã expired**. Và cũng không mặc định mọi hệ Spring Security có distributed replay cache được bật.

## 24. Validator customization và nâng Spring Security

Spring Security version có khác biệt:
- Spring Security 6.x dùng OpenSAML provider tương ứng dependencies (OpenSAML 4 hoặc OpenSAML 5 khi hỗ trợ).
- Spring Security 7.x reference mặc định dùng `OpenSaml5AuthenticationProvider`.
- Response/Assertion validator hooks, decryption và principal conversion có thể thay theo version.
- Migration 7 có thay đổi thứ tự response validation và assertion validation.
- `OneTimeUseConditionValidator` có thể cần custom registration khi yêu cầu.
- Một custom `ResponseValidator` hoặc `AssertionValidator` có thể **thay thế default rules** nếu dùng API sai.

Cần test những điều sau mỗi upgrade:
1. Valid signed response vẫn được chấp nhận.
2. Invalid/unsigned/untrusted signer vẫn bị từ chối.
3. Wrong audience/recipient/destination/time signed fixtures vẫn fail.
4. Request correlation/RelayState vẫn đúng.
5. Decryption và principal mapping không thay ngoài ý định.
6. Replay policy vẫn giữ nguyên.
7. Failure handlers và session persistence không cấp Authentication sau invalid response.

**Không tắt hoặc loại validator mặc định chỉ để test thuận tiện.** Nếu custom validator cần thêm checks, ưu tiên composition với default validator theo official API và viết negative tests cho cả rules mặc định.

## 25. Negative test matrix đề xuất

| Nhóm | Fixture/đầu vào | Kỳ vọng |
| --- | --- | --- |
| XML | Malformed Base64 | Không authentication |
| XML | Invalid XML/DTD/XXE | Không authentication, không external entity read |
| Signature | Unsigned response/assertions | Bị từ chối theo signing policy |
| Signature | Tampered signed bytes | Signature failure |
| Signature | Trusted signature bảo vệ wrong element | Không dùng nội dung sai |
| Trust | Valid signature bằng untrusted test cert | Bị từ chối |
| Issuer | Signed response issuer khác registration | Bị từ chối |
| Tenant | Same NameID dưới IdP khác | Không map chung account |
| Audience | Wrong audience nhưng signed valid | Audience rejection |
| Destination | Wrong ACS destination signed valid | Destination rejection |
| Recipient | Wrong bearer recipient signed valid | SubjectConfirmation rejection |
| InResponseTo | Saved request khác signed response | Correlation rejection theo flow |
| Time | Expired signed assertion | Expiry rejection |
| Time | Future NotBefore ngoài skew | Time rejection |
| Status | SAML non-Success status | Không authentication |
| Encryption | Correct test SP private key | Success nếu hợp lệ |
| Encryption | Wrong decryption key | No authentication |
| Replay | Second use trước expiry | Deny nếu one-time policy yêu cầu |
| Multiple assertions | Unsigned injected assertion | Không được dùng |
| RelayState | Arbitrary external return URL | Không open redirect |
| Session | Invalid response sau previous session | Không tạo/nâng quyền phiên mới |
| Reverse proxy | Wrong forwarded Host/Proto | Không bỏ validation, sửa URL config |
| Browser | SameSite/session state | E2E đúng nếu môi trường cho phép |
| Authorization | Valid SAML nhưng app account disabled | Deny |
| Multi-node | Saved request/replay state on other pod | Đúng policy |
| Rotation | New IdP test cert | Trust cập nhật theo approved metadata |

### Vì sao fixtures phải độc lập?

Nếu sai audience nhưng không ký lại, signature validator có thể là nơi chặn đầu tiên. Nếu expired + wrong key, test không chứng minh expiry validator. Nếu wrong InResponseTo nhưng không có saved request, test chỉ chứng minh thiếu repository. **Bảo đảm duy nhất một điều kiện sai mỗi khi muốn kiểm một validator cụ thể.**

## 26. Java 17 standalone: phân loại độ mạnh bằng chứng test

Chương trình sau không parse SAML, không tạo chứng chỉ và không thay OpenSAML/Spring. Nó mô phỏng một **bộ phân loại evidence**: một test có giả SecurityContext không, có real provider + signed trusted fixture không, có semantic negative cases không, và có chạy ACS/IdP E2E không.

Tệp `SamlTestEvidenceDemo.java`:

~~~java
public final class SamlTestEvidenceDemo {

    record Evidence(
            boolean mockAuthentication,
            boolean realProvider,
            boolean signedFixture,
            boolean trustedTestKey,
            boolean semanticNegativeCases,
            boolean acsHttpFlow,
            boolean browserIdpFlow) {
    }

    static String classify(Evidence e) {
        if (e.mockAuthentication()) {
            return "MOCK_AUTHORIZATION_ONLY";
        }
        if (!e.realProvider()) {
            return "NO_REAL_VERIFIER";
        }
        if (!e.signedFixture()) {
            return "NO_VALID_SIGNED_FIXTURE";
        }
        if (!e.trustedTestKey()) {
            return "NO_TRUST_VALIDATION";
        }
        if (!e.semanticNegativeCases()) {
            return "VALIDATOR_COVERAGE_INCOMPLETE";
        }
        if (!e.acsHttpFlow()) {
            return "PROVIDER_VALIDATION_ONLY";
        }
        if (!e.browserIdpFlow()) {
            return "ACS_INTEGRATION_ONLY";
        }
        return "BROWSER_E2E_COVERED";
    }

    public static void main(String[] args) {
        System.out.println("Mock user: " + classify(
                new Evidence(true, false, false, false,
                        false, false, false)));
        System.out.println("Mock manager: " + classify(
                new Evidence(false, false, false, false,
                        false, true, false)));
        System.out.println("Unsigned XML: " + classify(
                new Evidence(false, true, false, false,
                        false, true, false)));
        System.out.println("Untrusted key: " + classify(
                new Evidence(false, true, true, false,
                        false, false, false)));
        System.out.println("Happy path only: " + classify(
                new Evidence(false, true, true, true,
                        false, false, false)));
        System.out.println("Verifier: " + classify(
                new Evidence(false, true, true, true,
                        true, false, false)));
        System.out.println("ACS integration: " + classify(
                new Evidence(false, true, true, true,
                        true, true, false)));
        System.out.println("Full E2E: " + classify(
                new Evidence(false, true, true, true,
                        true, true, true)));
    }
}
~~~

Chạy:

~~~bash
javac SamlTestEvidenceDemo.java
java SamlTestEvidenceDemo
~~~

Stdout **chính xác**:

~~~text
Mock user: MOCK_AUTHORIZATION_ONLY
Mock manager: NO_REAL_VERIFIER
Unsigned XML: NO_VALID_SIGNED_FIXTURE
Untrusted key: NO_TRUST_VALIDATION
Happy path only: VALIDATOR_COVERAGE_INCOMPLETE
Verifier: PROVIDER_VALIDATION_ONLY
ACS integration: ACS_INTEGRATION_ONLY
Full E2E: BROWSER_E2E_COVERED
~~~

**Giới hạn:** mọi Boolean do developer tự khai; đây **không phải công cụ kiểm chứng crypto hay kiểm thử chạy SAML**. Trong CI, bằng chứng phải có test report, fixture provenance, provider execution và staging E2E logs. Kết quả `BROWSER_E2E_COVERED` cũng không chứng minh tất cả attack vectors đã được test.

## 27. Staging IdP/browser E2E phát hiện lỗi mà mock không thấy

Một test browser thực phải bao gồm:
- Public HTTPS của SP và IdP;
- Entity IDs/metadata/ACS URL đúng;
- Redirect binding của AuthnRequest;
- HTTP-POST binding của SAMLResponse;
- Browser cookies/SameSite/session;
- RelayState/request repository;
- MFA/IdP conditional access theo policy;
- Reverse proxy TLS/forwarded headers;
- Certificate rollover và metadata refresh;
- User/tenant/role mapping sau login;
- Session fixation/logout nếu yêu cầu;
- Multi-node auth state;
- NTP/time skew thực.

**MockMvc không mô phỏng đầy đủ browser cross-domain cookies, proxy TLS và IdP session.** T3 success không tự đảm bảo T4 success. Và T4 happy-path success không thay negative verifier tests T2.

### Staging safety

- Không copy IdP production private key vào test.
- Không cấu hình SP production tin test signing certificate ngoài migration được duyệt.
- Không lưu SAMLResponse thật chứa PII vào CI logs.
- Không bỏ certificate verification khi proxy lỗi.
- Không mở wildcard issuer/audience/ACS chỉ để test pass.
- Dùng test subjects/test tenants độc lập.
- Xóa test sessions/replay records giữa các runs.

## 28. Lỗi thiết kế kiểm thử thường gặp

| Anti-pattern | Vì sao sai | Thay bằng |
| --- | --- | --- |
| Chỉ có @WithMockUser | Không chạm verifier | Signed provider/ACS tests |
| Mock AuthenticationManager | Bỏ chữ ký/trust/validators | Real OpenSAML provider |
| Tạo unsigned XML và expect success | Khuyến khích bỏ security checks | Test IdP ký bằng test key |
| Wrong audience nhưng phá signature | Không cô lập audience | Sinh wrong audience rồi ký lại |
| Tin certificate trong XML tự khai | Trust poisoning | Registered IdP trusted credentials |
| Tắt InResponseTo khi test thiếu state | Mất correlation protection | Sinh AuthnRequest trước |
| Chỉ assert HTTP 302 | Không biết success/failure | Check SecurityContext và protected route |
| Dùng NameID/email làm account key chung | Tenant confusion/takeover | Issuer-scoped subject binding |
| Static fixture hết hạn, tắt time validation | Giảm bảo mật | Fresh signed fixture/test clock |
| Replay test sau expiry | Test time chứ không test replay | Reuse trước expiry |
| Không test encrypted assertions | Production decryption có thể lỗi | Test encryption keys riêng |
| CSRF 403 ở ACS, tắt CSRF cả site | Web routes mất CSRF defense | Sửa ACS matcher/filter config |
| Không test multiple assertions | Có thể đọc unsigned data | Signature scope negative cases |
| Production signing key trong CI | Lộ root of trust | Test-only keypairs |
| E2E happy path nhưng không negative cases | Chỉ chứng minh tương thích | Add signed semantic negative tests |
| Không test local account disabled | SAML valid vẫn có thể cấp access sai | App account gate and ACL tests |
| Nâng Spring/OpenSAML chỉ chạy mocks | Không thấy validator regressions | Chạy lại T2/T3/T4 |

## 29. Logging và runbook điều tra test failures

Khi SAML login/test fail:
1. Xác định test thuộc T1/T2/T3/T4.
2. Xác định request tới AuthnRequest endpoint hay ACS.
3. Đảm bảo không có mock AuthenticationManager.
4. Kiểm signed fixture freshness và test certificate trust.
5. Kiểm SAML Issuer/SP entity ID/registrationId.
6. Kiểm Destination, Recipient, Audience độc lập.
7. Kiểm InResponseTo/saved AuthnRequest/RelayState.
8. Kiểm NotBefore/NotOnOrAfter/clock skew.
9. Kiểm decryption keys nếu có encrypted assertion.
10. Kiểm actual failure status/handler và SecurityContext.
11. Kiểm principal/attributes/local roles và account state.
12. Với E2E, kiểm cookies, HTTPS, proxy, metadata, NTP.
13. Đối chiếu negative case có thật sự giữ chữ ký hợp lệ không.
14. Không bỏ validation để sửa test đỏ; sửa fixture/flow/config đúng nguyên nhân.

### Event mẫu đã redact

~~~json
{
  "event": "saml_authentication_failed",
  "traceId": "saml-opaque-test-001",
  "registrationId": "test-idp",
  "category": "AUDIENCE_VALIDATION",
  "fixtureId": "signed-wrong-audience",
  "result": "DENY"
}
~~~

Đây là mẫu log nội bộ, không phải default Spring event. Nếu provider chỉ trả generic failure, không bịa category bằng cách parse raw message. Không log raw SAMLResponse/XML, NameID, Attributes, cookies, private keys hoặc session IDs.

Metric labels chỉ nên dùng approved registration alias/categorical reason, không dùng user email hoặc assertion IDs có cardinality lớn.

## 30. Kiểm thử khi nâng cấp Spring Security/OpenSAML

Mỗi lần upgrade:
1. Xác nhận phiên bản provider mặc định.
2. Kiểm custom response/assertion validators còn **chứa các default checks**.
3. Chạy valid signed fixture.
4. Chạy invalid signature/untrusted cert/issuer.
5. Chạy signed wrong audience/recipient/destination/time/InResponseTo.
6. Chạy encrypted fixture nếu dùng.
7. Chạy replay/OneTimeUse theo policy.
8. Kiểm principal converter/authorities mapping.
9. Kiểm request repository/RelayState.
10. Chạy browser staging E2E với proxy/cert rollover.

Spring Security 7 documentation có thay đổi về thứ tự response/Assertion validation và principal conversion. Không suy rằng API 6.x cho `OpenSaml4AuthenticationProvider` và 7.x cho `OpenSaml5AuthenticationProvider` giống hệt nhau.

## 31. Checklist QA trước release

- [ ] T1 mock authorization, T2 provider, T3 ACS và T4 staging IdP được phân biệt rõ.
- [ ] Không dùng mock Authentication làm bằng chứng chữ ký SAML.
- [ ] T2/T3 thực sự chạy OpenSAML provider, không mock AuthenticationManager.
- [ ] RelyingPartyRegistration trỏ đúng test IdP trusted certificate.
- [ ] Positive fixture có chữ ký hợp lệ và còn thời hạn.
- [ ] Tampered/unsigned/untrusted cert phải bị từ chối.
- [ ] Wrong issuer/audience/destination/recipient được **ký hợp lệ** để isolate rule.
- [ ] Time tests có fresh signed fixture, boundaries và clock skew.
- [ ] SP-initiated tests lưu AuthnRequest/session/RelayState đúng.
- [ ] IdP-initiated unsolicited flow có policy riêng nếu được hỗ trợ.
- [ ] Multiple assertions/signature reference/XXE/oversized XML có negative tests.
- [ ] Replay test trước expiry, cross-session/node nếu chính sách yêu cầu.
- [ ] OneTimeUse/replay cache không được mặc định tồn tại nếu chưa kiểm.
- [ ] Encrypted assertions/decryption dùng test SP keypair, không production key.
- [ ] ACS post thực đi qua SecurityFilterChain và provider.
- [ ] Failure không tạo Authentication hoặc nâng privilege.
- [ ] Không dùng HTTP 200/302 một mình để chứng minh login success.
- [ ] Principal/attributes/roles từ verified assertion và app account gate.
- [ ] Disabled user hoặc tenant sai bị chặn dù assertion valid.
- [ ] Browser E2E kiểm metadata, HTTPS/ACS, cookies, SameSite, proxy, MFA.
- [ ] Certificate rollover và metadata refresh có integration case.
- [ ] Không bỏ signature/time/audience validators chỉ để test xanh.
- [ ] Test-only keys và fixtures tránh dữ liệu người dùng thật.
- [ ] Logs/metrics không tiết lộ SAMLResponse/keys/PII/tokens.
- [ ] Báo cáo test ghi rõ tầng bằng chứng và giới hạn còn lại.

## 32. Câu hỏi ôn tập và đáp án

**Câu 1.** `@WithMockUser(roles="ADMIN")` pass có chứng minh IdP ký đúng không?

**Đáp án:** không. Nó nạp SecurityContext giả và không chạy SAML verifier.

**Câu 2.** `MockMvc.with(user("linh"))` có phải đăng nhập SAML từ IdP không?

**Đáp án:** không, đó là request post-processor tạo user giả.

**Câu 3.** Mock AuthenticationManager trả Saml2Authentication có kiểm Audience không?

**Đáp án:** không nếu provider thật không được gọi.

**Câu 4.** SAMLResponse chứa StatusCode Success và NameID có phải hợp lệ không?

**Đáp án:** chưa. Cần XML signature/trust/conditions/correlation đúng.

**Câu 5.** Thay Audience sau khi ký rồi response bị từ chối có chứng minh AudienceRestrictionValidator không?

**Đáp án:** không chắc. Chữ ký hỏng trước. Phải ký lại response có wrong audience bằng trusted test key.

**Câu 6.** Signed assertion bởi IdP B có được xem là của IdP A nếu NameID giống không?

**Đáp án:** không. Issuer, certificate và relying party registration phải khớp.

**Câu 7.** Audience và Recipient giống nhau không?

**Đáp án:** không. Audience nhắm SP entityID; Recipient nhắm ACS nhận bearer assertion theo profile.

**Câu 8.** Tại sao POST ACS trực tiếp không có AuthnRequest có thể fail?

**Đáp án:** thiếu InResponseTo/request repository correlation ở SP-initiated flow.

**Câu 9.** RelayState là chữ ký của SAML Response không?

**Đáp án:** không. Nó liên hệ state/navigation theo binding và cần bảo vệ chống tamper/open redirect.

**Câu 10.** Assertion có chữ ký hợp lệ có thể bị replay không?

**Đáp án:** có. Signature không chứng minh one-time use, cần expiry/correlation/cache theo chính sách.

**Câu 11.** Replay sau expiry chứng minh global replay cache hoạt động không?

**Đáp án:** không. Có thể chỉ time validator từ chối.

**Câu 12.** Spring Security 7 dùng provider SAML2 mặc định nào theo reference?

**Đáp án:** `OpenSaml5AuthenticationProvider`, phụ thuộc version configuration thực tế.

**Câu 13.** HTTP 302 tại ACS có chứng minh login success không?

**Đáp án:** không. Có thể là failure redirect; kiểm SecurityContext và protected route.

**Câu 14.** Provider test đã pass có chứng minh SameSite cookies hoạt động trên browser thật không?

**Đáp án:** không, cần staging browser E2E.

**Câu 15.** EncryptedAssertion cần gì để được xử lý?

**Đáp án:** SP decryption private key/config phù hợp cùng signature/trust/conditions validation.

**Câu 16.** Valid SAML Response có thể login user đã disabled trong app không?

**Đáp án:** không nên. App-local account gate phải deny theo policy dù protocol valid.

**Câu 17.** Khi nâng Spring Security, có thể chỉ chạy mock tests không?

**Đáp án:** không; cần signed provider/ACS/E2E regression.

**Câu 18.** Một happy-path staging login pass chứng minh không có XML Signature Wrapping bug không?

**Đáp án:** không. Cần negative verifier/security cases.

**Câu 19.** Vì sao không dùng production IdP signing private key trong CI?

**Đáp án:** nguy cơ lộ signing authority; dùng test-only keypairs.

**Câu 20.** Nhiều negative cases đều thất bại bằng SIGNATURE_INVALID có nghĩa toàn bộ semantic validators đã được test không?

**Đáp án:** không. Có thể không case nào tới semantic validator; sửa fixtures để vẫn có valid signature.

## 33. Kết luận

**Mock authentication là công cụ tốt để kiểm authorization khi giả định một người dùng đã được xác thực. Nó không phải bằng chứng rằng SP có thể xác minh SAML Response thật.**

Để kiểm bộ kiểm chứng SAML:
1. Dùng **provider thật** với trusted test IdP key và **signed fixtures**.
2. Test signature, issuer, audience, recipient, destination, time và request correlation bằng các **negative fixtures độc lập**, ký hợp lệ cho lỗi semantic.
3. Test ACS Servlet filter, saved AuthnRequest, RelayState và SecurityContext.
4. Test replay/OneTimeUse nếu chính sách yêu cầu; không giả định mọi version đã có cache.
5. Test decryption, multi-assertion và XML parser safety.
6. Chạy staging IdP/browser E2E để kiểm proxy/cookie/metadata/interoperability.
7. Giữ tách biệt SAML authentication với local user/role/resource authorization.
8. Không tắt validation để test pass.

**Tư duy đúng:** mock trả lời “nếu user đã có Authentication thì app xử lý thế nào?”; real verifier trả lời “SAML Response có thật sự được IdP tin cậy xác nhận cho đúng SP, còn hạn, đúng request và không vi phạm policy không?”. Chỉ khi đo đúng hai vấn đề, kết quả QA mới trung thực.

### Tài liệu chính thức

1. Spring Security — SAML2 Login Overview, ACS filter và OpenSAML provider: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
2. Spring Security — Authenticating SAML Responses, validators/decryption/OneTimeUse: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
3. Spring Security — AuthnRequest and Request Repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
4. Spring Security — Running Test as User in MockMvc (@WithMockUser/user/authentication): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
5. Spring Security — MockMvc integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
6. Spring Security — SAML2 migration 7: https://docs.spring.io/spring-security/reference/migration-7/saml2.html
7. OASIS — SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
8. OASIS — SAML 2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
9. OASIS — SAML 2.0 Bindings: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
10. W3C — XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
11. OWASP — SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
