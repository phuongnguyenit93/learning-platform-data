# AuthenticationProvider dựa trên OpenSAML và quá trình tạo Saml2Authentication

> **Module:** Spring Security – federation. **Ngữ cảnh cha:** Luồng đăng nhập SAML2. Bài này đi sâu vào đường xử lý **SAMLResponse → Saml2AuthenticationToken → AuthenticationManager → AuthenticationProvider dùng OpenSAML → Saml2Authentication → SecurityContext** trên ứng dụng Spring Security Servlet. Các ví dụ chạy theo **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x**; những khác biệt khi lên Spring Security 7 được ghi rõ ở phần riêng.

## 1. Kết quả học tập

Sau khi hoàn thành bài, bạn có thể:

1. Chỉ đúng filter tạo AuthnRequest, filter xử lý SAMLResponse, lớp chuyển HTTP request thành authentication token và provider làm việc với OpenSAML.
2. Phân biệt `Saml2AuthenticationToken` **chưa xác thực** và `Saml2Authentication` **đã xác thực**, cùng vai trò của `AuthenticationManager` / `ProviderManager` và `RelyingPartyRegistration`.
3. Mô tả đầy đủ những lớp kiểm chứng trước khi cấp principal: signature, issuer, destination, status, decrypt, audience, bearer subject confirmation, thời gian, correlation và replay.
4. Hiểu vì sao một XML có NameID hoặc một cert tự ký không đủ để tạo session; nêu các ranh giới tin cậy giữa trình duyệt, IdP, SP và tài khoản nội bộ.
5. Giải thích provider chuyển Assertion hợp lệ thành `Saml2AuthenticatedPrincipal`, attributes, `GrantedAuthority` và `Saml2Authentication` thế nào; phân biệt `ROLE_USER` mặc định với quyền nghiệp vụ.
6. Cấu hình SAML Login hoạt động trên Spring Boot 3.5, quan sát authenticated principal an toàn và thay đổi provider/converter theo đúng API phiên bản.
7. Chẩn đoán login failures mà không tắt validation; viết ma trận kiểm thử xác thực và phân quyền có cả ca thành công lẫn ca âm.
8. Chỉ ra khác biệt **OpenSAML 4 ↔ 5** và Spring Security **6.5 ↔ 7.x** để tránh trộn API khi copy ví dụ.

**Kiến thức cần có:** HTTP POST/302, cookie/session và `SecurityFilterChain`, Spring `Authentication` / `SecurityContextHolder`, XML Signature/X.509 cơ bản, IdP entity ID, SP entity ID, ACS, SAML `AuthnRequest`, `Response` và `Assertion`. Bài này không dùng OAuth/OIDC để chứng minh đăng nhập: SAML 2.0 có các cấu trúc token và trust riêng.

## 2. Vị trí AuthenticationProvider trong kiến trúc Spring Security

Trong **Web Browser SSO Profile**, trình duyệt đưa người dùng tới IdP và đưa SAML response trở lại SP. SP chính là ứng dụng Spring Security của chúng ta. Cần tách **luồng tạo yêu cầu** và **luồng xác thực kết quả**.

~~~text
┌───────────────────────────────────────────────────────────────┐
│  A. KHỞI TẠO ĐĂNG NHẬP (SP-initiated)                        │
│                                                               │
│  Browser -> GET /saml2/authenticate/corporate                │
│    -> Saml2WebSsoAuthenticationRequestFilter                  │
│    -> resolve RelyingPartyRegistration                        │
│    -> sinh/sign/encode AuthnRequest theo IdP registration      │
│    -> lưu thông tin yêu cầu để correlation (thường session)   │
│    -> redirect hoặc POST qua browser tới IdP                 │
│                                                               │
│  IdP xác thực người dùng, phát SAMLResponse                    │
└───────────────────────────────────────────────────────────────┘
                          |
                          v
┌───────────────────────────────────────────────────────────────┐
│  B. NHẬN VÀ XÁC THỰC SAMLRESPONSE                             │
│                                                               │
│  Browser -> POST /login/saml2/sso/corporate                   │
│    + SAMLResponse=... [có thể kèm RelayState]                 │
│        |                                                      │
│        v                                                      │
│  Saml2WebSsoAuthenticationFilter                              │
│        |                                                      │
│        v                                                      │
│  Saml2AuthenticationTokenConverter                            │
│    -> lấy message và resolved RelyingPartyRegistration        │
│    -> khôi phục AuthnRequest liên quan nếu có                  │
│    -> Saml2AuthenticationToken [isAuthenticated=false]        │
│        |                                                      │
│        v                                                      │
│  AuthenticationManager / ProviderManager                      │
│        |                                                      │
│        v                                                      │
│  OpenSAML-backed AuthenticationProvider                       │
│    -> parse / verify / decrypt / validate                     │
│    -> map validated Assertion thành principal/authorities    │
│    -> Saml2Authentication [authenticated=true]                │
│        |                                                      │
│        v                                                      │
│  SecurityContextHolder (+ SecurityContextRepository/session) │
│    -> authorization / controller / service                     │
└───────────────────────────────────────────────────────────────┘
~~~

**Phân biệt trách nhiệm:**

| Thành phần | Nhận đầu vào | Trách nhiệm | Không nên làm |
| --- | --- | --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | URL khởi tạo SSO, registration | Sinh và gửi AuthnRequest, lưu request theo cơ chế repository | Quyết định SAMLResponse đã hợp lệ |
| `Saml2AuthenticationRequestRepository` | AuthnRequest đã tạo | Lưu/khôi phục dữ liệu giao dịch để đối chiếu lúc callback | Biến RelayState thành bằng chứng danh tính |
| `Saml2WebSsoAuthenticationFilter` | HTTP request tới ACS có `SAMLResponse` | Gọi converter rồi chuyển token cho AuthenticationManager; xử lý success/failure | Tự giải mã XML rồi cấp quyền bằng controller |
| `Saml2AuthenticationTokenConverter` | HTTP request, registration resolver/repository | Tạo `Saml2AuthenticationToken` theo registration đã tìm được | Tuyên bố token là đã xác thực |
| `AuthenticationManager` / `ProviderManager` | Authentication request token | Chọn và gọi AuthenticationProvider hỗ trợ loại token | Kiểm tra XML bằng logic tự phát ở controller |
| Provider dựa trên OpenSAML | Token chưa xác thực, metadata/credentials | Parse, verify, decrypt, validate, tạo authenticated result | Chấp nhận signer, issuer và endpoint từ dữ liệu chưa tin |
| `Saml2Authentication` | Principal/authorities đã được tạo sau validation | Đại diện kết quả login trong Spring Security | Thay thế kiểm tra quyền nghiệp vụ |
| `SecurityContextHolder` | Authentication thành công | Gắn principal hiện tại vào context của request | Tự động duy trì session khi app cấu hình stateless |

Ở đây **OpenSAML** là thư viện xử lý SAML protocol và XML Signature/Encryption. Spring Security bọc các hoạt động đó trong API authentication quen thuộc, đồng thời quản lý FilterChain, context, session, failure handlers và authorization.

## 3. Từ request tới response: SAML browser flow theo từng bước

### 3.1. Giai đoạn khởi tạo

1. User truy cập `GET /reports` được bảo vệ, chưa có session xác thực.
2. Spring Security chọn cơ chế login và có thể chuyển người dùng tới `/saml2/authenticate/{registrationId}`; nếu nhiều đối tác có thể cần trang chọn IdP.
3. `Saml2WebSsoAuthenticationRequestFilter` tra `RelyingPartyRegistration` đã cấu hình cho IdP/SP.
4. Bộ tạo request xây `AuthnRequest` với `ID`, `IssueInstant`, `Issuer` (SP entity ID), IdP destination và ACS. Nếu hợp đồng yêu cầu, SP dùng signing credential để ký.
5. Dữ liệu request được lưu bằng `Saml2AuthenticationRequestRepository`; mặc định thường là triển khai dựa trên HTTP session.
6. Browser gửi AuthnRequest đến IdP theo Redirect hoặc POST binding; IdP có thể yêu cầu mật khẩu, MFA, áp policy hoặc dùng phiên SSO đã có.
7. IdP gửi một `SAMLResponse`, thường qua HTTP POST đến ACS của SP, có `Status` và một hay nhiều Assertion (hoặc EncryptedAssertion).

**Vì sao cần lưu AuthnRequest?** Khi nhận response, SP có thể đối chiếu `InResponseTo` và thông tin giao dịch đã sinh, giảm rủi ro login CSRF và nhầm phiên. `RelayState` có thể hỗ trợ liên kết flow/điều hướng nhưng **không phải chữ ký hay bằng chứng xác thực người dùng**; không tin một RelayState chưa ràng buộc với session hoặc request đáng tin để chọn tài khoản.

### 3.2. Giai đoạn tiếp nhận ACS

Request điển hình:

~~~http
POST /login/saml2/sso/corporate HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PD94bWwgLi4u&RelayState=opaque-value
~~~

Giá trị trên chỉ minh họa dạng body; không phải SAMLResponse thực. ACS URL phải khớp metadata SP và registration tại IdP. Những môi trường proxy/load balancer cần tính đúng scheme, host, path và forwarded headers đáng tin.

Trong phiên bản phù hợp, filter nhận request rồi sử dụng `Saml2AuthenticationTokenConverter`. Converter giải mã dữ liệu ở mức transport phù hợp, xác định `RelyingPartyRegistration` cần dùng và cung cấp request đã khởi tạo nếu có. **Nó không tự đặt `authenticated=true`**. Sự tồn tại của SAMLResponse dưới dạng Base64/XML chỉ chứng minh một client đã gửi dữ liệu, chưa chứng minh IdP.

## 4. `Saml2AuthenticationToken`: dữ liệu chưa xác thực

`Saml2AuthenticationToken` là một implementation của Spring `AbstractAuthenticationToken` dùng mang **SAML Response chờ kiểm chứng** sang AuthenticationManager. Trong Spring Security 6.5:

- `getSaml2Response()` trả biểu diễn XML đã decode/decompress phù hợp (dữ liệu **chưa được tin**).
- `getRelyingPartyRegistration()` trả cấu hình bên nhận và đối tác đã resolve; đây là nguồn về IdP entity ID, SP entity ID, ACS và verification/decryption credentials.
- `getAuthenticationRequest()` có thể chứa AuthnRequest đã lưu; có thể `null` trong các trường hợp không có request tương ứng.
- `getPrincipal()` là `null` ở giai đoạn này.
- `isAuthenticated()` luôn là `false`. Việc gọi setter không biến nó thành chứng thực hợp lệ.

Không được đánh đồng token này với JWT, OIDC ID Token hoặc một `Saml2Authentication` đã đăng nhập.

**Ví dụ luồng dữ liệu (mã minh họa, không phải phương thức controller tự viết):**

~~~java
// Minh họa thứ tự các tầng; các biến filter/registration
// do Spring Security cung cấp, không phải code gọi trong controller.
Saml2AuthenticationToken pending =
        new Saml2AuthenticationToken(registration, decodedResponseXml);

Authentication verified = authenticationManager.authenticate(pending);
// Chỉ dùng verified khi authenticate() trả về kết quả hợp lệ.
~~~

Đoạn trên là **trích đoạn minh họa**, không phải file độc lập có thể biên dịch vì `registration`, `decodedResponseXml` và `authenticationManager` là biến từ tầng framework. Đừng tự dựng `Saml2AuthenticationToken` ở endpoint public rồi cho nó bypass các điều kiện về request repository, SP-initiated correlation hoặc registration resolution.

### Ranh giới chọn registration

`registrationId` (ví dụ `corporate`) là định danh nội bộ Spring, khác **IdP entity ID** và **SP entity ID** của giao thức. Trong nhiều đối tác, converter/resolver có thể dựa vào path, request state đã lưu hoặc issuer của message để tìm registration **trong danh sách được cấu hình trước**. Giá trị issuer đọc từ XML chưa verify có thể dùng như **gợi ý tra cứu ứng viên**, nhưng chỉ được coi là đúng **sau** khi provider xác minh signature và so sánh issuer/registration. Không tạo trust registration mới từ issuer hoặc metadata URL do request gửi.

## 5. `AuthenticationManager` và provider dựa trên OpenSAML

Spring Security sử dụng `AuthenticationManager` để xác thực một `Authentication` request. Triển khai phổ biến `ProviderManager` tìm một `AuthenticationProvider` có `supports(Saml2AuthenticationToken.class)` phù hợp. Với SAML, đó là provider sử dụng OpenSAML để xác minh response.

**Một số lớp quan trọng theo phiên bản:**

| Thành phần | Spring Security 6.5 | Spring Security 7.x |
| --- | --- | --- |
| Provider khi dùng OpenSAML 4 | `OpenSaml4AuthenticationProvider` | Không còn lựa chọn mặc định; cần cập nhật lên OpenSAML 5 |
| Provider khi dùng OpenSAML 5 | `OpenSaml5AuthenticationProvider` (khi đã chọn dependencies OpenSAML 5 phù hợp) | `OpenSaml5AuthenticationProvider` |
| Quy tắc chọn provider | Spring Security 6.5 chọn dựa trên OpenSAML dependency hiện diện; bản 6.5 thường mặc định OpenSAML 4 | OpenSAML 5 được ưu tiên/mặc định |
| Tầng bất biến | HTTP filter → `Saml2AuthenticationToken` → AuthenticationManager → validation → Authentication | Tư duy tổng thể giữ nguyên, API chuyển đổi principal/assertion có thay đổi |
| Custom converter | `OpenSaml4AuthenticationProvider.createDefaultResponseAuthenticationConverter()` với converter cho `ResponseToken` (khi dùng OpenSAML4) | API converter/accessor mới nên tham chiếu tài liệu 7.x, tránh copy nguyên code 6.x |
| Kết quả | `Saml2Authentication` với principal kiểu `Saml2AuthenticatedPrincipal` phổ biến | `Saml2Authentication`/`Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor` ngày càng được ưu tiên |

**Cảnh báo quan trọng về tài liệu mới nhất:** Trang Spring Security reference không có version trong URL thường hiển thị **Spring Security 7.x**, nên ví dụ `OpenSaml5AuthenticationProvider` ở đó không có nghĩa Spring Boot 3.5 dùng OpenSAML 5 mặc định. Hãy cố định phiên bản tài liệu theo dependency của project; khi nâng cấp kiểm tra cả Spring Security, OpenSAML, repository và API đã deprecated.

### `supports()` và `authenticate()`

- `supports(...)` cho biết provider có thể nhận loại token này hay không; **không khẳng định nội dung token hợp lệ**.
- `authenticate(...)` thực hiện toàn bộ nghiệp vụ xác thực theo provider. Khi thành công, provider trả một `Authentication` đã đánh dấu authenticated. Khi thất bại, nó phát `AuthenticationException` hoặc lỗi SAML tương ứng.
- `ProviderManager` có thể có nhiều provider; loại token quyết định provider tương thích. Một provider hỗ trợ SAML không đồng nghĩa có quyền xử lý form-login credentials hay Bearer JWT.

Nếu bạn thay AuthenticationManager bằng instance custom qua `saml2Login(saml2 -> saml2.authenticationManager(...))`, phải bảo toàn cơ chế kiểm chứng mặc định hoặc tự chịu trách nhiệm triển khai đầy đủ SAML security. Tránh thay provider chỉ để sửa tên hiển thị của principal hoặc role mapping, nếu converter/validator extension đã đáp ứng.

## 6. Pipeline OpenSAML: những việc phải đúng trước khi tạo principal

Luồng xử lý có nhiều công đoạn. Tài liệu Spring Security mô tả thứ tự khái quát: parse, verify response signature, decrypt encrypted assertions, validate response, verify assertions, decrypt assertion elements, validate assertions, rồi convert sang Authentication. Chi tiết có thể thay đổi theo bản OpenSAML và cách response được ký/mã hóa; **mọi nhánh hợp lệ vẫn phải bảo đảm message được tin và nội dung dùng để cấp principal đã được bảo vệ**.

### 6.1. Nhận và parse message

Provider nhận decoded SAML Response XML từ `Saml2AuthenticationToken`, chuyển thành OpenSAML `Response` và các object `Assertion` / `EncryptedAssertion`. Parser phải dùng cấu hình XML an toàn để tránh entity expansion/XXE và đối tượng không mong muốn. Khi dùng Spring Security/OpenSAML, hãy để thư viện parse; không tự tạo `DocumentBuilderFactory` tùy tiện rồi dùng một XPath để lấy NameID.

### 6.2. Kiểm chứng chữ ký

Khi response hoặc assertion có `Signature`, provider sử dụng **verification certificates của IdP trong RelyingPartyRegistration** để xác minh integrity và signer. Tùy profile:

- Có thể IdP ký `Response`, ký từng `Assertion` hoặc ký cả hai.
- Message không có chữ ký theo policy, chữ ký sai hoặc bằng cert không được tin phải bị từ chối.
- Việc chứng thư nằm ngay trong XML không tự biến nó thành trust anchor; key phải được buộc với asserting party đã cấu hình.
- Không tự viết XML Signature verifier hay coi `<Signature>` tồn tại là bằng chứng đủ.
- Không thực hiện XPath lấy NameID trên một phần tử **khác** phần tử được chữ ký bảo vệ, để tránh XML Signature Wrapping.

### 6.3. Giải mã các phần tử được mã hóa

Khi có `EncryptedAssertion`, `EncryptedID` hoặc `EncryptedAttribute`, OpenSAML dùng **decryption credentials của SP** trong registration để giải mã, nếu profile yêu cầu. Public encryption certificate trong SP metadata là nơi IdP lấy khóa để mã hóa; SP giữ private decryption key tương ứng.

Mã hóa thành công **không chứng minh nguồn phát**. Vẫn cần xác minh chữ ký và issuer/audience/timing. Với assertion được ký riêng, thứ tự giải mã các phần tử bên trong có thể ảnh hưởng chữ ký; vì vậy provider có cơ chế tách response decryption và assertion decryption. Đừng “tối ưu” bằng cách giải mã và sửa DOM trước khi xác minh đúng phạm vi chữ ký.

### 6.4. Xác minh Response

Những thông tin cần kiểm tra theo profile/cấu hình:

| Kiểm tra | Mục đích | Tình huống lỗi |
| --- | --- | --- |
| `StatusCode` thành công | IdP thực sự báo xác thực thành công | `Responder`, `Requester` hoặc `AuthnFailed` |
| `Response/Issuer` | Response thuộc asserting party được tin | Sai IdP entity ID/tenant |
| `Destination` | Response gửi về đúng ACS/SP | Proxy đổi scheme, host, path |
| `InResponseTo` khi có request liên quan | Gắn response với giao dịch SP-initiated | Chưa lưu request, sai session/RelayState |
| Chữ ký Response | Đảm bảo message/fields được bảo vệ khi response signed | Cert sai, signature mismatch, alg không hỗ trợ |
| Có assertion hợp lệ | Phải có chủ thể và thông tin authentication hợp lệ | Response không có assertion cần thiết |

Các điều kiện tương quan cụ thể phụ thuộc SP-initiated hay IdP-initiated flow. Với IdP-initiated, không có AuthnRequest đã phát để so khớp giống luồng SP-initiated; phải có chính sách cho phép hay từ chối IdP-initiated, replay protections và validation khác, không gán đại request ID.

### 6.5. Xác minh từng Assertion

Một Assertion chứa danh tính và các tuyên bố mà SP có thể dùng. Provider/validator cần kiểm tra:

1. **Signature hoặc phạm vi chữ ký Response phù hợp profile** bảo vệ Assertion. Không chấp nhận Assertion không được bảo vệ đúng chính sách.
2. **Assertion Issuer** đúng IdP đã tin; cảnh giác trường hợp Response/Assertion khác issuer.
3. `Conditions/NotBefore` và `NotOnOrAfter`: Assertion còn trong cửa sổ hợp lệ, với clock skew nhỏ và có monitoring NTP.
4. `AudienceRestriction`: Assertion được phát cho đúng **SP entity ID**, không phải cho ứng dụng khác.
5. `Subject`/`NameID` hoặc `EncryptedID` cùng `SubjectConfirmation`. Với bearer flow, `SubjectConfirmationData/Recipient` phải đúng ACS, `NotOnOrAfter` phù hợp và `InResponseTo` khi cần.
6. `AuthnStatement` và các giới hạn context mà ứng dụng yêu cầu, nếu liên quan đến policy MFA/authentication strength.
7. **Replay protection**: ngăn sử dụng lại Response/Assertion IDs trong cửa sổ hợp lệ, phối hợp state/correlation và nơi lưu request. Với triển khai cluster cần kiểm tra cơ chế lưu/tìm request/replay phù hợp, không mặc định một session in-memory giải quyết mọi topology.
8. Chỉ dùng `AttributeStatement` sau khi các checks phù hợp hoàn tất; không quyết định quyền admin vì một attribute tên `role=admin` xuất hiện trong XML chưa xác minh.

**Không nên khẳng định chỉ chữ ký valid là PASS.** Một signed Assertion có `Audience=app-B` không thể dùng đăng nhập app-A; một Assertion hết hạn cũng bị từ chối; một response bị replay không thể dùng tạo phiên mới vô thời hạn.

### 6.6. Lưu ý về phạm vi mặc định và customization

Spring Security/OpenSAML cung cấp validator mặc định nhưng mức độ đảm bảo từng profile cần đối chiếu **đúng phiên bản, bindings, cấu hình và customizations**. Đặc biệt, khi cần chống replay qua cluster, giới hạn IdP-initiated, điều kiện MFA hoặc yêu cầu xác minh NameID format riêng, có thể cần lớp kiểm tra bổ sung. Đừng tuyên bố mọi triển khai mặc định tự áp dụng mọi policy nghiệp vụ.

Khi custom `setResponseValidator` hoặc `setAssertionValidator`, **ghép thêm** checks vào validator mặc định nếu có thể. Thay hoàn toàn validator mà quên issuer, destination, time hoặc audience là lỗ hổng xác thực. Nếu một check chỉ phụ thuộc nghiệp vụ tenant/account, nên áp dụng sau protocol validation ở converter/service thay vì tắt kiểm chứng SAML.

## 7. Từ OpenSAML Assertion đến `Saml2Authentication`

Sau khi message vượt qua các bước kiểm chứng, provider chuyển các tuyên bố đã tin sang mô hình Spring Security.

Trong Spring Security 6.5, kết quả mặc định thường chứa:

- `Saml2AuthenticatedPrincipal`: principal có `getName()` thường dựa trên `Subject/NameID` của Assertion đầu tiên và có `getAttributes()` cùng `getFirstAttribute(name)`; cũng có thể có registration ID và thông tin session index tùy implementation.
- `GrantedAuthority`: ở cấu hình thông thường có `ROLE_USER` (và tùy phiên bản/feature có thể có authority biểu diễn yếu tố xác thực SAML). Đây là **quyền mặc định của tầng đăng nhập**, không phải chính sách nghiệp vụ.
- `Saml2Authentication`: một `Authentication` authenticated chứa principal, tập authorities và biểu diễn SAML Response trong API như `getSaml2Response()`.
- `SecurityContext`: được đặt theo success workflow của filter; trong ứng dụng dựa trên session, context có thể được lưu qua `SecurityContextRepository` để request sau nhận được Authentication.

**Điều cần phân biệt:** `Saml2AuthenticationToken` có `principal=null` và `isAuthenticated=false`; `Saml2Authentication` là kết quả sau validation với principal và `isAuthenticated=true`. Đừng tự gọi một constructor Saml2Authentication rồi coi đó là bằng chứng IdP; người có quyền tạo object Java cũng có thể tạo một token trông “authenticated”. Chỉ filter/provider chuẩn và policy của ứng dụng mới thiết lập provenance.

### 7.1. Dữ liệu của principal

| API | Trả về | Nên dùng thế nào |
| --- | --- | --- |
| `Authentication#getName()` | Tên principal theo converter | Hiển thị/log hạn chế, không tự giả định là unique user ID toàn cầu |
| `Saml2AuthenticatedPrincipal#getName()` | Thường NameID trong Assertion đã xác minh | Chỉ dùng làm khóa identity link khi kèm IdP/SP/format/qualifier phù hợp |
| `getRelyingPartyRegistrationId()` | ID cấu hình RP, ví dụ `corporate` | Ghép với IdP/SP metadata đã được tin |
| `getAttributes()` | Map các SAML Attributes, thường nhiều giá trị | Áp mapping có hợp đồng; không log mọi attribute |
| `getFirstAttribute(name)` | Giá trị đầu tiên của attribute cụ thể, nếu có | Kiểm tra null, type, dữ liệu từ đúng đối tác |
| `getAuthorities()` | Tập `GrantedAuthority` | Dùng authorization sau khi map tenant/role của ứng dụng |
| `Saml2Authentication#getSaml2Response()` | SAML Response XML ở dạng chuỗi, có thể vẫn chứa phần tử mã hóa | **Nhạy cảm**; không xuất endpoint/log/analytics |

**Một IdP có thể phát nhiều AttributeStatements hoặc nhiều assertion.** Converter mặc định tập trung vào assertion/attributes theo implementation; nếu nghiệp vụ phụ thuộc nhiều assertions, phải xác minh cách các phiên bản chuyển đổi, không tự giả định mọi AttributeStatement đều được gom. Nếu cần dữ liệu cụ thể, kiểm tra hợp đồng assertion và viết test.

### 7.2. Authentication không phải Authorization

Giả sử IdP xác thực thành công user U, tạo NameID hợp lệ. SP vẫn cần xác định:

- U thuộc tenant nào?
- Có identity link tới account nào, account có `ACTIVE` không?
- Tài khoản đã bị vô hiệu hóa hoặc bị thu hồi quyền chưa?
- Có `ROLE_REPORT_VIEWER` hay chỉ `ROLE_USER`?
- Có được xem tài nguyên `/reports/finance`, hoặc dữ liệu của tenant khác không?

Mỗi quyết định này thuộc policy của ứng dụng. Không dùng `hasRole("USER")` mặc định để mở mọi tài nguyên kinh doanh. Nếu mapping group/role từ IdP, phải biết group attribute name, issuer, danh sách giá trị cho phép, phiên bản hợp đồng và điều kiện MFA nếu yêu cầu.

## 8. Cách Spring hoàn tất đăng nhập và lưu phiên

Sau khi AuthenticationManager trả result hợp lệ, `Saml2WebSsoAuthenticationFilter` (lớp kế thừa `AbstractAuthenticationProcessingFilter`) kích hoạt success handling trong filter chain. Framework đặt Authentication vào `SecurityContextHolder` và tùy cấu hình lưu SecurityContext qua `SecurityContextRepository` (thường HTTP session ở ứng dụng web).

Chuỗi về mặt khái niệm:

~~~text
Validated Saml2Authentication
     ↓
AuthenticationSuccessHandler / success workflow
     ↓
SecurityContextHolder.getContext().setAuthentication(result)
     ↓
SecurityContextRepository.saveContext(...) (theo cấu hình)
     ↓
Redirect về request ban đầu hoặc URL thành công
     ↓
Request kế tiếp + session cookie -> SecurityContext được khôi phục
     ↓
AuthorizationFilter kiểm tra rule theo authorities/tenant
~~~

**Lưu ý phiên bản và cấu hình:** Hình này mô tả hành vi khái quát. Tên strategy/handler cụ thể và thời điểm lưu context có thể thay đổi theo Spring Security version, custom SecurityContextRepository, custom success handler và policy session. Nếu bạn cấu hình `SessionCreationPolicy.STATELESS` hoặc bỏ request/session repository không phù hợp, SAML browser SSO có thể gặp lỗi correlation hoặc không giữ được Authentication qua request kế tiếp.

**Trường hợp thất bại:** Provider ném `AuthenticationException` (thường dạng `Saml2AuthenticationException` chứa lỗi SAML). Filter chạy failure handling, không cấp Authentication thành công, xóa authentication context phù hợp và có thể redirect tới trang login/error. HTTP status cụ thể tùy configuration/failure handler. Không nên ghi “mọi lỗi SAML luôn là 401” vì browser login thường dùng redirect và có thể tạo vòng lặp nếu cấu hình sai.

## 9. Ví dụ Spring Boot 3.5.x / Java 17: quan sát kết quả đã xác thực

Ví dụ này tạo một SAML Service Provider cơ bản bằng Spring Security. **Có thể biên dịch khi Maven giải quyết dependencies**, nhưng chỉ đăng nhập hoàn chỉnh nếu bạn có **SAML IdP thử nghiệm thật**, metadata hợp lệ, SP entity ID và ACS được đăng ký đúng. URL IdP trong cấu hình là minh họa, không phải một endpoint hoạt động.

Cấu trúc thư mục:

~~~text
saml-auth-provider-demo/
├── pom.xml
└── src/main/
    ├── java/demo/SamlFlowApplication.java
    └── resources/application.yml
~~~

### 9.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>saml-auth-provider-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <name>Shibboleth Releases</name>
            <url>https://build.shibboleth.net/maven/releases</url>
            <snapshots><enabled>false</enabled></snapshots>
        </repository>
    </repositories>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-saml2-service-provider</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot dependency management ghép Spring Security phiên bản tương thích với Boot 3.5. Khai báo Shibboleth releases nếu môi trường build cần để giải quyết artifacts OpenSAML; quản trị dependency repository theo chính sách tổ chức và kiểm tra phiên bản được resolve bằng `mvn dependency:tree` khi debug.

### 9.2. `src/main/resources/application.yml`

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

`corporate` là `registrationId` nội bộ, còn `metadata-uri` phải thay bằng metadata **đã được tổ chức phê duyệt**. Việc cấu hình metadata-uri sẽ giúp Spring Boot tạo `RelyingPartyRegistrationRepository` và các dữ liệu xác minh IdP phù hợp; để nhận response, phải đăng ký SP entity ID và ACS (thường lấy từ SP metadata mà ứng dụng sinh) tại IdP.

**Nếu IdP yêu cầu signed AuthnRequest** hoặc encrypted assertion, bổ sung SP signing/decryption credentials theo cấu hình Boot và công bố public cert tương ứng ở SP metadata; đừng nhập IdP private key vào SP hoặc tắt signature verification.

### 9.3. `src/main/java/demo/SamlFlowApplication.java`

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlFlowApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DebugEndpoints {
        @GetMapping("/")
        String home() {
            return "Open /whoami to start SAML login";
        }

        @GetMapping("/whoami")
        Map<String, Object> whoami(Authentication authentication) {
            if (!(authentication instanceof Saml2Authentication saml)) {
                return Map.of("samlAuthenticated", false);
            }

            Saml2AuthenticatedPrincipal principal =
                    (Saml2AuthenticatedPrincipal) saml.getPrincipal();

            List<String> authorities = saml.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("samlAuthenticated", saml.isAuthenticated());
            result.put("authenticationType", saml.getClass().getSimpleName());
            result.put("registrationId",
                    principal.getRelyingPartyRegistrationId());
            result.put("principalPresent", principal.getName() != null);
            result.put("authorities", authorities);
            return result;
        }
    }
}
~~~

**Lưu ý bảo mật:** Endpoint chỉ trả metadata về trạng thái login; **không trả raw SAMLResponse, NameID, email, attributes, session cookie hay secret**. Endpoint `/whoami` được bảo vệ; nếu chưa đăng nhập, người dùng được hướng vào SAML login. Kiểm tra `authentication instanceof Saml2Authentication` minh họa kiểu result, không có ý nghĩa thay validate.

### 9.4. Đăng ký IdP và chạy

1. Tại IdP test, tạo **SAML SP application** phù hợp với URL của ứng dụng; nhập đúng SP entity ID và ACS từ SP metadata (thường có `/saml2/service-provider-metadata/corporate` hoặc endpoint tương đương tùy version).
2. Tải metadata IdP từ nguồn đã phê duyệt, thay `https://idp.example.org/saml/metadata` trong YAML. Kiểm tra IdP entity ID, SSO endpoint và signing cert.
3. Bảo đảm Java 17+, Maven và có thể truy cập metadata từ backend Spring. Chạy:

~~~bash
mvn spring-boot:run
~~~

4. Mở `http://localhost:8080/`: kết quả chính xác là:

~~~text
Open /whoami to start SAML login
~~~

5. Mở `http://localhost:8080/whoami` hoặc `http://localhost:8080/saml2/authenticate/corporate`. Browser được dẫn đến IdP, sau đó gửi SAMLResponse về ACS. Khi login đúng, controller có thể trả JSON theo dạng:

~~~json
{
  "samlAuthenticated": true,
  "authenticationType": "Saml2Authentication",
  "registrationId": "corporate",
  "principalPresent": true,
  "authorities": ["ROLE_USER"]
}
~~~

Đây là **hình dạng ví dụ**. Tập authorities hoặc tên authentication class có thể khác theo version/cấu hình; bản mới có thể cấp thêm authority như `FACTOR_SAML_RESPONSE`. Chỉ chuỗi công khai `GET /` ở trên là output cố định. Đăng nhập không thể chạy với URL IdP minh họa chưa tồn tại.

**Kết quả quan sát được:** Nếu `samlAuthenticated=true` và principal được provider tạo, request hiện tại đã qua luồng xác thực tương ứng. Để chứng minh bảo mật, còn cần các negative tests: signer sai, issuer sai, audience sai, time invalid, replay, decryption failure và permission denial.

### 9.5. Tại sao không in `getSaml2Response()`?

`Saml2Authentication#getSaml2Response()` có thể chứa SAML XML, NameID, attributes, session context, chữ ký và dữ liệu nhạy cảm. Dù login thành công, không nên đưa nó vào JSON, trace, log hoặc tài liệu chia sẻ. Muốn debug thông điệp, dùng môi trường thử nghiệm, kiểm soát quyền, che dữ liệu và xóa log theo retention policy.

## 10. Tùy biến OpenSAML-backed AuthenticationProvider trong Spring Security 6.5

Khi không thể đáp ứng nghiệp vụ bằng thuộc tính có sẵn, Spring Security cho phép tùy biến cách **đổi Assertion đã được kiểm chứng thành Authentication**. Điểm extension thường là `setResponseAuthenticationConverter` của provider. Dùng converter mặc định trước rồi thêm kiểm tra/mapping nghiệp vụ, tránh viết lại logic giải mã và verify.

### 10.1. Ví dụ cấu hình OpenSAML 4, Spring Security 6.5

**Chỉ dùng thay thế bean SecurityFilterChain ở mục 9**, không khai báo đồng thời hai filter chains trùng scope. Ví dụ sau minh họa giới hạn đúng registration, tra attributes đã xác minh và gán một quyền nghiệp vụ **được whitelist** khi group claim khớp hợp đồng IdP. Đây là lớp cấu hình hoàn chỉnh có thể biên dịch trong project ở mục 9 (không phụ thuộc user database); policy nhóm phải được thay bằng hợp đồng thật khi áp dụng production.

**Tệp `src/main/java/demo/CustomSamlSecurityConfiguration.java`:**

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml4AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomSamlSecurityConfiguration {

    @Bean
    SecurityFilterChain customSamlFilterChain(HttpSecurity http) throws Exception {
        OpenSaml4AuthenticationProvider provider =
                new OpenSaml4AuthenticationProvider();

        Converter<OpenSaml4AuthenticationProvider.ResponseToken,
                  Saml2Authentication> defaults =
                OpenSaml4AuthenticationProvider
                        .createDefaultResponseAuthenticationConverter();

        provider.setResponseAuthenticationConverter(responseToken -> {
            // Code chỉ chạy sau những validation protocol do provider thực hiện.
            Saml2Authentication verified = defaults.convert(responseToken);
            if (verified == null) {
                throw new BadCredentialsException("Missing SAML principal");
            }

            String registrationId = responseToken.getToken()
                    .getRelyingPartyRegistration().getRegistrationId();
            if (!"corporate".equals(registrationId)) {
                throw new BadCredentialsException("Unexpected SAML partner");
            }

            Saml2AuthenticatedPrincipal principal =
                    (Saml2AuthenticatedPrincipal) verified.getPrincipal();

            List<GrantedAuthority> authorities = new ArrayList<>();
            authorities.add(new SimpleGrantedAuthority("ROLE_USER"));

            // Chỉ ánh xạ khi thuộc tính "groups" từ IdP này đã
            // được thỏa thuận và có chính sách kiểm soát.
            List<Object> groups = principal.getAttributes()
                    .getOrDefault("groups", List.of());
            if (groups.contains("reports-read")) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"));
            }

            return new Saml2Authentication(
                    verified.getPrincipal(),
                    verified.getSaml2Response(),
                    authorities);
        });

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/reports/**")
                            .hasAuthority("ROLE_REPORT_VIEWER")
                        .anyRequest().authenticated())
                .saml2Login(saml -> saml
                        .authenticationManager(new ProviderManager(provider)))
                .saml2Metadata(metadata -> {})
                .build();
    }
}
~~~

**Điều chỉnh để tránh hai SecurityFilterChain:** Nếu dùng lớp trên, hãy bỏ bean `securityFilterChain` khỏi `SamlFlowApplication`; giữ các controller và `@SpringBootApplication`. Cách khác là đặt các đoạn provider/DSL vào bean filterChain đã có, giữ duy nhất một chain.

**Vì sao code này an toàn hơn việc tự xác thực XML?** Provider vẫn thực hiện parse/verify/decrypt/validate mặc định. Converter nhận `ResponseToken` sau quá trình validation; lấy principal đã xác minh, chỉ bật quyền được whitelist theo IdP đã đăng ký. Không có dòng nào cho phép một HTTP parameter tự cấp `ROLE_REPORT_VIEWER`.

**Giới hạn mẫu:** Mapping `groups.contains("reports-read")` đơn giản, giả định IdP đã bảo đảm group claim thuộc hợp đồng. Production cần identity link sang user nội bộ, tenant restriction, user status, scope của nhóm, audit và kiểm thử nhiều IdP. Không cấp `ROLE_ADMIN` từ claim chưa được phê duyệt; không dùng `principal.getName()` một mình làm khóa duy nhất nếu nhiều IdP/SP.

### 10.2. Provider mặc định và tùy biến validators

Một số nhu cầu có hook riêng:

| Nhu cầu | Điểm extension | Cảnh báo |
| --- | --- | --- |
| Điều chỉnh principal name sau khi kiểm chứng | Response authentication converter | Không làm mất identity namespace / IdP context |
| Ánh xạ group từ IdP sang authorities | Response authentication converter hoặc service map quyền sau login | Whitelist theo đối tác/tenant và kiểm tra account status |
| Thêm response policy riêng | Response validator | Dùng validator mặc định kết hợp checks mới |
| Bổ sung assertion condition | Assertion validator | Không thay toàn bộ default validation bằng một điều kiện yếu |
| Giải mã bằng HSM/remote cryptographic service | Response/assertion elements decrypter | Giữ đúng thứ tự XML signature / decrypt và error handling |
| Chọn RP/SP theo nhiều tenant | `RelyingPartyRegistrationResolver` / authentication converter | Chỉ chọn registration đã duyệt; không trust issuer từ input |
| Dùng hệ thống session phân tán | `Saml2AuthenticationRequestRepository`, session store phù hợp | Giữ correlation và chống replay trên các node |
| Thay toàn bộ luồng xác thực SAML | `saml2Login.authenticationManager(...)` | Rủi ro lớn: phải tự tái lập đầy đủ kiểm chứng giao thức |

**Version-specific:** `OpenSaml4AuthenticationProvider` chỉ tương ứng OpenSAML 4. Với OpenSAML 5 trong Spring Security 6.5, sử dụng class và method hợp lệ của phiên bản đó. Với Spring Security 7.x, kiểm tra các API mới `ResponseAuthenticationConverter`, `Saml2ResponseAssertionAccessor` và deprecations. Không đổi tên lớp bằng search/replace rồi giả định generic types, methods tương thích.

## 11. Tương quan AuthnRequest, RelayState và session qua nhiều instance

Một lỗi thực tế khi response quay về từ IdP là **không tìm thấy AuthnRequest ban đầu**:

- User bắt đầu flow ở instance A; callback quay về instance B nhưng không chia sẻ session/request repository.
- Browser không gửi session cookie do SameSite/Secure/domain/path hoặc HTTPS proxy sai.
- Ứng dụng dùng session policy stateless trong khi repository mặc định cần session.
- User mở hai login flows cùng lúc, state bị thay thế hoặc callback đến muộn.
- RelayState bị thay đổi, sai mapping hoặc bị coi là nguồn tin cậy độc lập.

Spring Security có `HttpSessionSaml2AuthenticationRequestRepository` làm lựa chọn mặc định trong các version phổ biến. Nếu dùng cluster, có thể dùng Spring Session/distributed session store hoặc request repository thích hợp. Nhưng đừng triển khai “lưu request theo RelayState từ query không ký” mà không ràng buộc với browser session/khởi tạo hợp lệ; có rủi ro login fixation và replay.

**Đọc đúng lỗi:** `InResponseTo` không khớp là vấn đề correlation; issuer/signature sai là vấn đề trust; decryption fail là vấn đề encryption credentials; account disabled là vấn đề authorization/provisioning. Chúng khác nhau và cần sửa ở vị trí khác nhau.

## 12. Đăng nhập nhiều IdP: ranh giới tin cậy và principal

Với hai registration:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate-a:
            assertingparty:
              metadata-uri: https://idp-a.example/saml/metadata
          corporate-b:
            assertingparty:
              metadata-uri: https://idp-b.example/saml/metadata
~~~

Đoạn YAML là ví dụ cấu trúc và cần IdP metadata có thật. Spring Security có thể phân biệt từng đối tác theo registration. Tuy nhiên **không được tự đồng nhất hai người** chỉ vì họ có cùng `NameID` hoặc email.

Mô hình liên kết account đúng về ý tưởng:

~~~text
SAML Authentication đã xác minh
  + trusted IdP entity ID
  + trusted SP entity ID
  + NameID format/qualifiers/value
       ↓
ExternalIdentityKey
       ↓ lookup
IdentityLink -> internal_user_id -> tenant policy -> authorities
~~~

- `registrationId` là khóa cấu hình hữu ích, nhưng nếu admin có thể thay issuer của registration trong khi giữ nguyên ID, phải quản lý migration và tránh alias lẫn người dùng.
- `NameID` kiểu persistent có thể pairwise theo SP; transient không dùng để lookup tài khoản lâu dài.
- SAML Attribute `email` có thể đổi/tái cấp; không auto-link account giữa IdP A/B bằng email đơn lẻ.
- Provider mặc định chứng minh danh tính theo IdP/registration; quyền nội bộ còn do ứng dụng quyết định.
- Để có tên/format/qualifier chính xác cho identity link, dùng điểm tích hợp với **assertion đã được xác minh**. API principal phổ biến ở Spring Security 6.x có thể không expose toàn bộ các trường NameID/qualifier; đừng parse bản XML HTTP chưa xác thực tại controller.

## 13. Failure path: khi provider từ chối SAMLResponse

`OpenSamlXAuthenticationProvider` có thể thất bại ở parser, signature, decrypt, response validator, assertion validator hoặc converter. Khi thất bại, Spring Security không chuyển nó thành authenticated session. Handler có thể hiển thị lỗi/redirect và có thể tiếp tục challenge.

| Triệu chứng | Giai đoạn có thể lỗi | Cách sửa |
| --- | --- | --- |
| `SAMLResponse` thiếu hoặc không decode được | ACS/converter/transport parsing | Kiểm tra POST binding, form field, encoding, body limit |
| Không tìm được registration | Converter/RP resolver | Kiểm tra registrationId, session/issuer mapping, IdP metadata |
| `invalid_signature` | Response/Assertion signature verifier | So sánh IdP verification cert, metadata cache, signer key rotation |
| `invalid_issuer` | Response/assertion validator | Đúng IdP entity ID và registration; không bỏ issuer check |
| `invalid_destination` | Response destination validator | ACS URL, scheme/host/port và trusted reverse proxy |
| `audience_mismatch` | Assertion validator | SP entity ID/metadata và AudienceRestriction tại IdP |
| `InResponseTo` không khớp | Request repository/correlation | Session cookie, load balancer, request lưu/truy hồi, flow SP-init |
| Assertion hết hạn / `NotBefore` | Assertion time validator | Đồng bộ đồng hồ NTP, tránh clock skew quá lớn |
| `EncryptedAssertion` không giải mã được | Response decrypter | Public encryption cert IdP dùng phải khớp private decryption key SP |
| `EncryptedID` / `EncryptedAttribute` lỗi | Assertion decrypter | Cấu hình credential, algorithm và thứ tự decrypt/signature |
| Response bị phát lại | State/replay control | Session/request correlation, cache replay phù hợp policy |
| AuthnRequest bị IdP từ chối | Request generation/signature/IdP policy | SP signing cert, binding, ACS, NameIDPolicy |
| Login thành công, sau đó 403 | Authorization | Role/tenant/account mapping tại ứng dụng |
| Login thành công nhưng request sau lại phải login | Session/SecurityContext persistence | Cookie, SecurityContextRepository, SameSite, stateless policy |
| Lỗi chỉ ở một server | Cluster state/config | Đồng bộ session, metadata, certs, clocks và rollout |

**Đừng sửa lỗi validation bằng cách làm yếu chính sách:** không bỏ chữ ký, issuer, audience, thời gian, subject confirmation hoặc cho phép KeyInfo tự định nghĩa trust key. Tập trung xác định đúng **bên phát hành → bên nhận → message → registration → validation**.

## 14. Ma trận kiểm thử cho AuthenticationProvider

| Kiểm thử | Kết quả mong đợi | Lớp chịu trách nhiệm |
| --- | --- | --- |
| Đã đăng ký đúng IdP, Response hợp lệ và Assertion hợp lệ | `Saml2Authentication` authenticated; principal và authorities hợp lệ | OpenSAML provider + converter |
| Token chưa qua provider | `Saml2AuthenticationToken.isAuthenticated()==false` | Request token |
| SAMLResponse không có/không decode được | Không tạo principal authenticated | Filter/token converter |
| Response ký bằng key lạ | Từ chối | Signature verification |
| Assertion signature bị sửa sau ký | Từ chối | Assertion signature verification |
| IdP Issuer khác registration đã tin | Từ chối | Issuer validation |
| Response đến ACS sai | Từ chối | Destination/Recipient check |
| Assertion Audience thuộc SP khác | Từ chối | AudienceRestriction |
| Response/Assertion hết thời gian hiệu lực | Từ chối | Time validators |
| Subject bearer không có Recipient hợp lệ | Từ chối | SubjectConfirmation validation |
| Không có AuthnRequest ứng với InResponseTo của SP-init | Từ chối hoặc fail correlation theo policy | Request repository/validator |
| SAMLResponse bị replay | Từ chối theo replay/correlation policy | State và replay controls |
| Decryption credential không khớp | Fail, không tạo session | OpenSAML decrypter |
| IdP-initiated response bị policy SP cấm | Từ chối | SP flow policy |
| Response có group claim không nằm trong whitelist | Không cấp authority đặc quyền | Custom converter/authorization |
| Assertion hợp lệ nhưng internal user bị khóa | Không cấp quyền ứng dụng | Account linking/policy |
| Một NameID trùng ở IdP A/B | Hai identity độc lập | User mapping service |
| Sau login có session cookie hợp lệ | SecurityContext được khôi phục ở request sau | Session/Context Repository |
| Sau login gọi endpoint đòi ROLE_REPORT_VIEWER, user chỉ ROLE_USER | 403 Forbidden | AuthorizationFilter |
| IdP signing key thay, SP cache metadata cũ | Login fail cho đến khi trust cập nhật; có rollover plan | Metadata/credential management |

### Kiểm thử tự động và kiểm thử tích hợp khác nhau

- **Unit test trên converter**: chỉ thích hợp khi converter nhận response đã được validator chuẩn xác thực; mock một `Saml2Authentication` không chứng minh pipeline XML signature an toàn.
- **MVC test giả lập principal**: hữu ích cho authorization controller và role mapping, nhưng **không** kiểm chứng OpenSAML parsing, signature, issuer hay audience.
- **Integration test với IdP test + metadata/keys**: cần để chứng minh flow end-to-end, request state, signature/decryption và callback.
- **Negative security test**: phải có signer sai, issuer sai, audience sai, expiration, replay và missing request correlation. Test theo môi trường staging có kiểm soát, tránh tấn công production.

## 15. Checklist vận hành và giám sát

1. **Registration:** Mỗi IdP/SP có entity IDs, ACS, SSO URL và verification credentials từ metadata đã được phê duyệt.
2. **Keys:** Lên lịch xoay IdP signing cert và SP decryption cert, quản lý overlap; không gửi private key sang đối tác.
3. **Sessions:** Kiểm tra cookie Secure/SameSite, session lifetime, security context persistence và repository dùng trong cluster.
4. **Clock:** Đồng bộ NTP; chỉ cho clock skew nhỏ cần thiết, có cảnh báo nếu nhiều response hết hạn.
5. **Error handling:** Sử dụng failure handler rõ ràng, hạn chế vòng lặp login; không tiết lộ full SAML XML hay danh tính người dùng trên error page.
6. **Logs:** Ghi request ID/correlation ID, registrationId, loại lỗi, timestamp ở mức tối thiểu; che NameID, email, SAMLResponse, Signature, session cookie và bí mật.
7. **Account mapping:** Tách tên principal SAML và user ID nội bộ, có tenant restrictions, role mapping whitelist, approval cho account linking mới.
8. **Monitoring:** Theo dõi login success/failure theo đối tác, số lỗi signature, missing correlation, decryption, mismatch audience, session lost và certificate rotation.
9. **Deployment:** Thử load balancer, host/proxy headers, ACS HTTPS, multi-instance metadata versions, session replication và rollback.
10. **Upgrades:** Khi chuyển Spring Security 6.x → 7.x, rà soát OpenSAML 5, converter/accessor mới và API deprecated, chạy integration tests đầy đủ.

## 16. Bài tập thực hành

**Bài A – vẽ chuỗi xử lý:** Tự vẽ lại đường SAMLResponse từ browser tới `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter`, `AuthenticationManager`, `OpenSaml4AuthenticationProvider`, `Saml2Authentication` và `SecurityContextHolder`. Ghi chính xác thời điểm `isAuthenticated` chuyển từ false sang true.

**Bài B – triển khai:** Dùng project mục 9 với IdP test. Kiểm tra SP metadata, IdP SSO endpoint, signing cert, ACS URL. Đăng nhập và xác nhận `/whoami` có `samlAuthenticated=true`. Không in raw response hoặc NameID lên endpoint public.

**Bài C – kiểm thử bảo mật:** Trong môi trường test, gửi Response ký bằng key khác, Audience sai và Assertion hết hạn. Chứng minh không có authenticated session được tạo. So sánh log error type với pipeline mục 6.

**Bài D – tùy biến provider:** Dùng ví dụ mục 10 **thay** filterChain mặc định. Cho IdP thử nghiệm phát `groups=reports-read` và `groups=other`; xác minh chỉ nhóm được whitelist có `ROLE_REPORT_VIEWER`. Phân tích vì sao sau bước protocol validation vẫn cần tenant/account policy.

**Bài E – session/correlation:** Chạy ứng dụng sau hai instance có load balancer. Cấu hình không dùng sticky session/distributed repository và tái hiện lỗi mất request (nếu môi trường tạo được); sau đó đồng bộ session/repository, xác nhận `InResponseTo` hoạt động. Giải thích vì sao không thể chỉ tin RelayState do trình duyệt gửi.

**Bài F – nâng cấp:** So sánh tài liệu Spring Security 6.5 OpenSAML support với tài liệu 7.x. Chỉ rõ lý do một code snippet chứa `OpenSaml5AuthenticationProvider` ở docs mới có thể không chạy trong project Boot 3.5 chưa đổi dependencies.

**Đạt bài** khi người học có thể giải thích end-to-end pipeline theo đúng token/filter/provider, triển khai được SAML login thật trên IdP thử nghiệm, phân biệt authentication và authorization, làm đúng custom converter, nêu được ít nhất năm lý do fail validation và không dựa vào SAML XML chưa xác minh để cấp principal.

## 17. Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Security SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security **6.5 OpenSAML Support** (mặc định OpenSAML4, cách chọn OpenSAML5): https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security 6.5 API – Saml2AuthenticationToken: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticationToken.html
- Spring Security 6.5 API – OpenSaml4AuthenticationProvider: https://javadoc.io/doc/org.springframework.security/spring-security-saml2-service-provider/6.5.0/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html
- Spring Security 7.0 Migration – SAML2, OpenSAML5 và assertion accessor: https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- Spring Boot 3.5 Reference – Spring Security và SAML 2.0: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles (Web Browser SSO): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
