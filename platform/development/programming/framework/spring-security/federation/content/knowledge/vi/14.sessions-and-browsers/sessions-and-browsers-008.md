# Đăng nhập nhiều tab và xử lý nhiều yêu cầu đang chờ trong Spring Security SAML 2.0

Khi một người dùng mở **nhiều tab cùng ứng dụng Service Provider (SP)** rồi đăng nhập qua **SAML 2.0 federation**, mỗi tab có thể phát sinh một `AuthnRequest` khác nhau trước khi Identity Provider (IdP) kịp trả `SAMLResponse`. Một tình huống đặc biệt thường gặp là **HTTP session của SP vừa hết hạn**: tất cả tab cùng phát hiện chưa được xác thực, gần như đồng thời chuyển hướng tới IdP và tạo nhiều yêu cầu đăng nhập đang chờ (*pending authentication requests*).

Nếu SP chỉ lưu một `AuthnRequest` trong cùng `HttpSession`, yêu cầu sau có thể ghi đè yêu cầu trước. Khi phản hồi của tab đầu tiên trở về, `InResponseTo` của nó không còn khớp request mà repository đang lưu: login thất bại dù IdP đã xác thực đúng. Ngược lại, nếu để giải quyết đa tab mà chỉ dùng `RelayState` tra cứu request từ một cache toàn cục **không ràng buộc với trình duyệt**, SP có thể mở ra rủi ro **login CSRF / session swapping**.

**Mục tiêu của bài:** hiểu chính xác ranh giới giữa **tab, browser session, SAML transaction và SecurityContext**; thiết kế kho lưu **nhiều giao dịch chờ** an toàn; ghép từng response với **đúng** request; xử lý callback đến sai thứ tự, trùng lặp, hết hạn và đồng thời trên nhiều node; cấu hình/kiểm thử cùng Spring Security mà **không vô hiệu hóa xác thực SAML**.

## 1. Bốn khái niệm tuyệt đối không đánh đồng

| Khái niệm | Phạm vi thực tế | Ý nghĩa cho đăng nhập nhiều tab |
| --- | --- | --- |
| **Browser tab** | Một ngữ cảnh giao diện; có thể có trạng thái `sessionStorage` riêng. | Hai tab có thể khởi tạo **hai** luồng SSO khác nhau. |
| **`HttpSession` / cookie SP** | Thường chia sẻ giữa các tab cùng origin trong **một browser profile**. | Hai tab thường có **cùng** `JSESSIONID`, nên kho lưu một slot dễ bị ghi đè. |
| **SAML `AuthnRequest@ID` + `RelayState`** | **Một** giao dịch xác thực SP-initiated; phải độc lập theo từng lần khởi tạo. | Tab A có `req-A`/`relay-A`; tab B có `req-B`/`relay-B`. |
| **Spring Security `Authentication` + `SecurityContext`** | Danh tính đăng nhập mà SP duy trì trong HTTP session/cơ chế persistence của mình. | Một khi đăng nhập thành công, những tab chia sẻ session **cùng sử dụng danh tính** đó ở các request tiếp theo. |

**Không có “mỗi tab một phiên đăng nhập Spring Security độc lập” chỉ vì người dùng có hai tab.** Nếu trình duyệt gửi cùng cookie phiên tới SP, hai tab có thể thấy cùng tài khoản đã xác thực và cùng trạng thái logout/role. Muốn hai tài khoản khác nhau cùng lúc, thường phải dùng profile trình duyệt, container cookie hoặc phiên/browser context được cách ly thực sự, không chỉ thêm một biến JavaScript đặt tên “tabSession”.

Cũng không nhầm `AuthnRequest@ID` với `SAMLResponse@ID`, `Assertion@ID`, `AuthnStatement@SessionIndex` hay `JSESSIONID`. Chúng là những định danh của các đối tượng khác nhau.

## 2. Kịch bản lỗi cơ bản: hai tab và một slot request

Giả sử người dùng cùng origin `https://sp.example.org`, và cả hai tab đang dùng browser session `S-100`:

~~~text
Thời điểm    Tab A                  SP / HttpSession S-100                Tab B
----------------------------------------------------------------------------------------
T0           GET /reports/42        Chưa đăng nhập
T1           AuthnRequest req-A --> Lưu pending = req-A
             RelayState relay-A
             Redirect đến IdP

T2                                                                      GET /settings
T3                                   Lưu pending = req-B  <-- GHI ĐÈ
                                     (req-A không còn)
                                                                         AuthnRequest req-B
                                                                         RelayState relay-B
                                                                         Redirect đến IdP

T4           IdP trả Response-A:
             InResponseTo=req-A
             RelayState=relay-A
             POST tới ACS
T5                                   Repository tải pending=req-B
                                     req-A != req-B
                                     => correlation FAIL

T6                                                                      Response-B về ACS
T7                                   Nếu req-B vẫn còn và hợp lệ,
                                     callback B có thể thành công
~~~

Ở **Spring Security 6.2.1**, một vấn đề đa tab với `HttpSessionSaml2AuthenticationRequestRepository` đã được ghi nhận công khai: các `AuthnRequest` dùng chung một khóa trong session, request mới ghi đè request trước; tác giả quan sát lỗi `InResponseTo` khi callback trả về không cùng thứ tự. Có giải pháp cache theo `RelayState` về sau, nhưng đi kèm lưu ý bảo mật. **Không suy từ ví dụ này rằng mọi phiên bản hoặc mọi custom repository đều có hành vi y hệt**; phải kiểm tra class/version đang chạy.

### 2.1. Các triệu chứng dễ nhận thấy

- Tab A và B đều chuyển tới IdP, nhưng một tab báo lỗi `InResponseTo mismatch` hoặc “AuthenticationRequest not found”.
- Khi session hết hạn, mở lại nhiều tab khiến lỗi tăng, trong khi đăng nhập bằng một tab đơn lẻ vẫn chạy.
- Callback của tab B đến trước A; B đăng nhập thành công, A có thể gặp session/cookie đổi sau **session fixation protection**.
- Người dùng đăng nhập xong nhưng lại được đưa về trang của **tab khác** vì SavedRequest/target URL chỉ có một slot chia sẻ trong session.
- Hai tab chủ động dùng hai IdP/tenant/account khác nhau và callback đến gần nhau, khiến danh tính cuối cùng trong shared SecurityContext không như người dùng mong muốn.
- Production có nhiều node, request lưu trên node A nhưng callback đến B khi session store chưa đồng bộ.

Cần phân biệt **lỗi correlation**, **lỗi cookie/session**, **lỗi SAML signature/conditions**, **xung đột ghi SecurityContext** và **lỗi redirect sau login**. Chúng có thể cùng xuất hiện nhưng không có cùng cách sửa.

## 3. Luồng SAML 2.0 liên quan đến nhiều yêu cầu chờ

### 3.1. Bắt đầu AuthnRequest tại SP

Một luồng SP-initiated thông dụng:

1. Browser mở tài nguyên cần xác thực tại SP; Spring Security xác định người dùng chưa có `Authentication` hợp lệ.
2. `Saml2WebSsoAuthenticationRequestFilter` kích hoạt endpoint `/saml2/authenticate/{registrationId}`.
3. `Saml2AuthenticationRequestResolver` tạo `AuthnRequest` với `ID` duy nhất, chọn `RelyingPartyRegistration`, Destination là IdP SSO endpoint và tạo `RelayState` theo binding/profile.
4. `Saml2AuthenticationRequestRepository` lưu **giao dịch đang chờ** trước khi browser tới IdP.
5. Browser được chuyển tới IdP SSO, thường bằng HTTP-Redirect binding (hoặc POST khi hai bên cấu hình hỗ trợ).

Một request chờ không chỉ là chuỗi ID. Nó cần gắn với **registration, issuer IdP dự kiến, SP entityID, ACS, thời điểm, phiên trình duyệt và trạng thái điều hướng**. Các thuộc tính SAML sau đó được dùng để xác minh thông điệp phản hồi.

### 3.2. IdP trả Response về ACS

Trong SAML HTTP-POST binding, IdP gửi form có `SAMLResponse` và có thể `RelayState` tới ACS `/login/saml2/sso/{registrationId}`. `Saml2WebSsoAuthenticationFilter` nhận request, converter tải `RelyingPartyRegistration` và giao dịch đang chờ, rồi `AuthenticationManager`/OpenSAML provider xác minh.

Những đối chiếu liên quan trực tiếp đến một giao dịch:

| Đầu vào của response | Phải khớp với |
| --- | --- |
| `Response@InResponseTo` trong SP-initiated SSO | **`AuthnRequest@ID`** đã phát trước đó, theo quy tắc profile/validator. |
| `SubjectConfirmationData@InResponseTo` (bearer) | **ID của AuthnRequest gốc**; không dùng ID của request khác trong cùng session. |
| `RelayState` | Giá trị thuộc chính **giao dịch đang chờ** theo binding, không phải URL redirect bất kỳ. |
| `Issuer` + chữ ký | **IdP/khóa đã đăng ký** của giao dịch; không chọn IdP tin cậy chỉ vì XML tự khai issuer. |
| `Destination` và `Recipient` | **ACS URL** của SP phù hợp với registration và endpoint thực nhận. |
| `AudienceRestriction` | **SP entityID** đúng. |
| Conditions/SubjectConfirmation validity | Khoảng hiệu lực và profile của assertion; không chấp nhận hết hạn. |
| Assertion/Response replay key | Chưa bị sử dụng trước đó theo cơ chế chống phát lại. |

**Chỉ có `RelayState` đúng chưa đủ:** response vẫn phải có chữ ký/issuer/audience/destination/recipient/time/correlation đúng. **Chỉ có `InResponseTo` đúng cũng chưa đủ:** nếu request ID có thể được lấy từ cache chỉ bằng dữ liệu do trình duyệt gửi, SP vẫn có thể không biết **chính trình duyệt này** đã khởi tạo login trước đó hay chưa.

## 4. Hành vi mong đợi khi có hai request hợp lệ

Giả sử cùng phiên `S-100`, hai giao dịch độc lập:

| Thuộc tính | Tab A | Tab B |
| --- | --- | --- |
| AuthnRequest ID | `req-A` | `req-B` |
| RelayState | `relay-A` | `relay-B` |
| Registration | `corporate` | `corporate` |
| Trang mong muốn sau login | `/reports/42` | `/settings` |
| Trạng thái | Pending | Pending |

Một kho đa giao dịch sẽ lưu:

~~~text
BrowserSession S-100:
  relay-A -> Pending(requestId=req-A, registration=corporate,
                     returnRoute=/reports/42, expiresAt=T+180s)
  relay-B -> Pending(requestId=req-B, registration=corporate,
                     returnRoute=/settings, expiresAt=T+180s)
~~~

Nếu **Response-B về trước**:

1. SP xác minh Response-B và tìm **pending B** theo định danh giao dịch **trong session S-100**.
2. So `InResponseTo=req-B`, relay và registration của B; bảo đảm assertion dành cho SP này.
3. Bản ghi B được **tiêu thụ đúng một lần**, bản ghi A **vẫn còn**.
4. Nếu Response-A đến sau và phiên/correlation còn hợp lệ, SP có thể xác minh A theo bản ghi A. Việc có công bố thêm Authentication hay không còn phụ thuộc **chính sách một SecurityContext chung và phiên đã đăng nhập từ B**.

**Bất biến:** B không bao giờ được dùng `req-A` chỉ vì cùng browser session, và hoàn tất B **không xóa hàng loạt A**. Không tự hạ cấp một response có `InResponseTo` lỗi thành **IdP-initiated/unsolicited login** để người dùng “khỏi thấy lỗi”.

### 4.1. Tab nào sẽ trở thành tài khoản đang đăng nhập?

Mặc dù pending A/B độc lập, **SecurityContext của chúng có thể dùng chung `HttpSession`**. Nếu A và B đăng nhập **cùng local account**, ứng dụng có thể áp dụng chính sách cho phép hoàn tất nếu giao dịch còn hợp lệ; tuy nhiên phải xử lý race của session persistence, session ID rotation, saved requests và logic chuyển trang.

Nếu A và B đăng nhập **hai danh tính khác nhau** (ví dụ IdP A/tenant A và IdP B/tenant B), không được vô tình “last callback wins” rồi đổi account đang chạy trên tab còn lại. Chính sách an toàn thường là **không cho thay principal của một session đã xác thực bởi một callback chồng chéo**, trừ khi người dùng đã chủ động bắt đầu luồng chuyển tài khoản có ràng buộc. Có thể buộc hoàn tất session hiện hành hoặc yêu cầu đăng xuất/đăng nhập bằng browser context khác. Việc chọn policy phải nhất quán ở tất cả node.

**Cùng session cookie = cùng ranh giới xác thực**, nên UI tab A không được giả định người dùng vẫn là principal A nếu tab B đã thay đổi session. Mọi API phải kiểm tra danh tính/tenant và quyền của request hiện hành ở server.

## 5. Thiết kế kho pending requests cho đa tab

### 5.1. Cấu trúc một pending transaction

~~~text
PendingSamlLogin:
  transactionKey = random opaque RelayState (32 hoặc 43 byte ASCII)
  authnRequestId = "_request-7ef"
  browserSessionBinding = hash(server-side session ID / secret)
  registrationId = "corporate"
  expectedIdpIssuer = "urn:example:idp:corporate"
  spEntityId = "urn:example:sp:portal"
  expectedAcs = "https://sp.example.org/login/saml2/sso/corporate"
  safeReturnRouteId = "reports:42"
  issuedAtUtc = "2026-11-07T03:00:00Z"
  expiresAtUtc = "2026-11-07T03:03:00Z"
  state = "PENDING"
  consumedAtUtc = null
~~~

Dùng **một bản ghi cho mỗi `AuthnRequest`**, không dùng một thuộc tính cố định duy nhất trong `HttpSession` khi business case cần nhiều pending requests. Nếu muốn lưu ngay trong session, có thể dùng `Map<RelayState, PendingRequest>` gắn với session, nhưng phải giải quyết đồng thời, persistence và cleanup. Nếu dùng Redis/DB, khóa tra cứu phải ràng buộc thêm với **phiên trình duyệt được tin** chứ không chỉ với relay.

**Không lưu dữ liệu nhạy cảm** như mật khẩu, token, assertion plaintext, cookie hoặc toàn bộ báo cáo vào RelayState; giá trị qua trình duyệt/IdP và có thể xuất hiện trong log. `RelayState` của SAML HTTP bindings được quy định tối đa **80 byte**; ưu tiên 24 byte ngẫu nhiên → Base64URL không padding 32 byte ASCII hoặc 32 byte ngẫu nhiên → 43 byte ASCII.

### 5.2. Các bất biến dữ liệu bắt buộc

1. **Duy nhất theo giao dịch:** mỗi request có ID SAML và RelayState khác, dù cùng tab hoặc cùng cookie.
2. **Không ghi đè:** khi tạo B, A không bị mất và không bị thay thế bởi bất cứ “current request” slot dùng chung nào.
3. **Phạm vi browser:** lookup phải chứng minh giao dịch thuộc **đúng session/browser** khởi tạo hoặc một bằng chứng browser binding tương đương.
4. **Phạm vi federation:** registration, issuer IdP, SP entityID và ACS phải đúng với request đã tạo.
5. **TTL:** pending phải hết hạn trong một thời gian ngắn; callback quá hạn bị từ chối.
6. **Single use:** giao dịch chỉ được hoàn tất một lần với thao tác **atomic compare-and-remove / transition PENDING → CONSUMED**.
7. **Replay protection:** assertion/response replay store là tầng **khác** với việc tiêu thụ pending request; cả hai cần áp dụng.
8. **Memory bound:** giới hạn số request pending mỗi session, ví dụ 4–8 hoặc mức theo sản phẩm; có rate limiting theo session/IP.
9. **Cleanup:** dọn các bản ghi hết hạn hoặc session đã invalidated; không xóa nhầm request đang chờ của tab khác.
10. **Fail closed:** nếu không thể lấy/kiểm chứng binding hoặc kho trạng thái không nhất quán, không mặc định coi callback là hợp lệ.

Không nên xóa A chỉ vì B thành công. Nhưng cũng không nên **giữ vô hạn** các request cũ hay cho mọi `InResponseTo` ngẫu nhiên được sử dụng sau khi người dùng logout hoặc phiên đã chuyển principal. Mọi trạng thái liên quan phải có vòng đời và chính sách hủy rõ.

### 5.3. Khi nào nên từ chối tạo thêm request?

Nếu cùng browser session đã có nhiều pending SSO, có hai lựa chọn sản phẩm:

- **Cho nhiều giao dịch độc lập**, ví dụ tối đa 5 giao dịch, mỗi giao dịch ràng buộc ID/Relay/TTL/registration; quan sát và xử lý cookie/session concurrency như đã nêu.
- **Gộp/điều phối luồng đăng nhập**, chỉ cho một login đang diễn ra trong session, các tab khác chờ hoặc chuyển tới trạng thái đăng nhập chung. Hướng này có thể đơn giản hơn nếu ứng dụng không cần hai IdP hoặc nhiều return targets; vẫn phải xử lý timeout, reload, failover và tránh một tab xóa giao dịch của tab khác.

Nếu sản phẩm chỉ cần “người dùng đăng nhập một lần cho toàn bộ tab”, **gộp khởi tạo SSO** có thể hữu ích hơn thêm nhiều pending requests, nhưng **không tự động gộp** các yêu cầu có registration/tenant khác nhau hoặc các luồng đang chờ mà chưa có chính sách rõ. Dù chọn hướng nào, mỗi callback vẫn phải được validate và tương quan chính xác.

## 6. Spring Security: repository mặc định và các lựa chọn tùy biến

### 6.1. Repository trong luồng chuẩn

Spring Security Servlet định nghĩa interface `Saml2AuthenticationRequestRepository<T extends AbstractSaml2AuthenticationRequest>` với các thao tác:

- `saveAuthenticationRequest(request, httpRequest, httpResponse)`: lưu request trước khi gửi IdP.
- `loadAuthenticationRequest(httpRequest)`: lấy request liên quan callback.
- `removeAuthenticationRequest(httpRequest, httpResponse)`: lấy và xóa một request khi giao dịch cần được tiêu thụ.

`Saml2WebSsoAuthenticationRequestFilter` dùng repository để lưu request, còn `Saml2WebSsoAuthenticationFilter`/`Saml2AuthenticationTokenConverter` dùng nó khi xác thực response. Một custom repository phải tích hợp **cùng logic và cùng nguồn lưu ở cả hai chiều**; đừng chỉ thay resolver gửi AuthnRequest mà quên converter lúc callback.

Tài liệu Spring Security hiện hành cho biết **`HttpSessionSaml2AuthenticationRequestRepository`** là mặc định và lưu `AbstractSaml2AuthenticationRequest` trong `HttpSession`. Trong các phiên bản đã được báo cáo dùng một khóa session cố định, nó có thể **ghi đè pending request** khi khởi tạo nhiều luồng. Đó là lý do phải kiểm thử chính xác phiên bản runtime và chọn repository phù hợp.

### 6.2. CacheSaml2AuthenticationRequestRepository không tự chứng minh browser binding

Từ **Spring Security 6.5**, có **`CacheSaml2AuthenticationRequestRepository`**, cho phép lookup AuthnRequest thông qua cache gắn với RelayState mà không phụ thuộc hoàn toàn vào `HttpSession`. Đây có thể là cách giảm va chạm của các request chờ và hỗ trợ tình huống mất session cookie do `SameSite=Strict`.

Nhưng tài liệu Spring Security nêu rõ một **đánh đổi bảo mật**: cache này có thể chứng minh request từng được **ứng dụng tạo**, nhưng không tự chứng minh request được tạo **bởi chính trình duyệt đang đưa SAMLResponse tới ACS**. Nếu chỉ dùng `InResponseTo` hoặc `RelayState` để tra cache toàn cục, một kẻ tấn công có thể khởi tạo giao dịch trong browser của mình rồi tìm cách đưa phản hồi tới browser của nạn nhân, dẫn đến **login fixation / login CSRF / session swapping** trong cấu hình bị ảnh hưởng.

**Không xem “đổi sang CacheSaml2AuthenticationRequestRepository” là bản sửa không có rủi ro.** Muốn vừa hỗ trợ nhiều tab vừa chống login CSRF, thiết kế cần **browser-bound multi-request store**: có nhiều key theo giao dịch nhưng lookup/consume còn phải chứng minh sự liên quan với browser session/bằng chứng được tạo trước đó và bảo vệ khỏi attacker kiểm soát giá trị relay.

### 6.3. Mẫu cấu hình Spring Security thường dùng

Ví dụ `SecurityFilterChain` cho một ứng dụng Spring Boot Servlet đã có `RelyingPartyRegistration` hợp lệ:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **cấu hình Spring Boot**, không phải chương trình có thể biên dịch bằng `javac` thuần nếu thiếu Spring Security, IdP metadata và credentials. Nó bật SAML login nhưng **chưa giải quyết trường hợp nhiều request trong một session**; phải kiểm chứng repository đang được cấu hình.

Với repository tự triển khai, cần đăng ký một **bean `Saml2AuthenticationRequestRepository<AbstractSaml2AuthenticationRequest>`** theo DSL/API của phiên bản:

~~~text
@Bean authenticationRequestRepository():
    return BrowserBoundMultiRequestRepository(
        sharedPendingStore,
        sessionBindingPolicy,
        transactionTtl,
        idpRegistrationPolicy)

Các class BrowserBound... ở đây chỉ là mô hình kiến trúc,
KHÔNG phải class có sẵn trong Spring Security.
~~~

Cấu hình phải đảm bảo filter gửi request và converter xử lý callback cùng sử dụng một repository, xử lý tương quan trong đường đi chính thức của framework. Nếu code tùy biến làm “load request theo RelayState” trước khi Spring xác minh response, phần **định tuyến registration** có thể dùng dữ liệu chưa tin, nên vẫn phải giữ binding/trust checks. Không tự tạo một `Authentication` từ NameID khi chưa chạy OpenSAML validator.

### 6.4. Đối chiếu phiên bản

| Thành phần / hành vi | Điểm cần kiểm tra |
| --- | --- |
| `HttpSessionSaml2AuthenticationRequestRepository` | Dùng session nào/attribute nào; có hỗ trợ nhiều pending requests không trong **dependency thực tế**? |
| `CacheSaml2AuthenticationRequestRepository` | Có ở **6.5+**; hành vi cache/lookup, TTL và giới hạn browser binding. |
| `OpenSaml4AuthenticationProvider` | Gặp trong Spring Security 6.x dùng OpenSAML 4 (tùy release). |
| `OpenSaml5AuthenticationProvider` | Gặp trong tài liệu các release mới dùng OpenSAML 5. |
| `Saml2AuthenticationTokenConverter` | Cách tìm `RelyingPartyRegistration` và pending request khi không có `registrationId` trong ACS URL. |
| `SessionAuthenticationStrategy` / `SecurityContextRepository` | Session ID rotation, persistence và xử lý hai callback song song khi một callback đã thành công. |

Không giả định chỉ nâng dependency sẽ tự giải quyết toàn bộ **concurrency của session, return URL và tài khoản khác nhau**. Cần integration test với version và container thực tế.

## 7. Java 17 runnable: một session có nhiều AuthnRequest đang chờ

Chương trình sau mô phỏng một **browser-bound pending request store**, dùng `ConcurrentHashMap` và `SecureRandom` để minh họa đa tab, callback đến ngược thứ tự, session mismatch, TTL và dùng một lần. Nó **không parse SAML, không kiểm tra signature và không tạo Spring Authentication**; hàm `complete` chỉ nên được gọi trong luồng thật **sau khi SAMLResponse đã được xác minh bằng provider chính thức** và issuer/registration/`InResponseTo` đã được đối chiếu.

Tệp **`PendingSamlRequestsDemo.java`**:

~~~java
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class PendingSamlRequestsDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    record Pending(String authnRequestId, String registrationId,
                   String safeReturnRoute, Instant expiresAt) {}

    static class Store {
        private final ConcurrentMap<String, ConcurrentMap<String, Pending>>
                byBrowserSession = new ConcurrentHashMap<>();

        private static String allowRoute(String candidate) {
            return switch (candidate) {
                case "/reports", "/settings", "/dashboard" -> candidate;
                default -> "/dashboard";
            };
        }

        String begin(String browserSession, String authnRequestId,
                     String registration, String route, Instant now) {
            ConcurrentMap<String, Pending> pending =
                    byBrowserSession.computeIfAbsent(
                        browserSession, ignored -> new ConcurrentHashMap<>());
            Pending entry = new Pending(authnRequestId, registration,
                    allowRoute(route), now.plusSeconds(180));

            String relay;
            do {
                byte[] bytes = new byte[24];
                RANDOM.nextBytes(bytes);
                relay = Base64.getUrlEncoder()
                        .withoutPadding().encodeToString(bytes);
            } while (pending.putIfAbsent(relay, entry) != null);

            return relay;
        }

        String complete(String browserSession, String relayState,
                        String verifiedInResponseTo,
                        String verifiedRegistration, Instant now) {
            ConcurrentMap<String, Pending> pending =
                    byBrowserSession.get(browserSession);
            if (pending == null || relayState == null) {
                return "DENY";
            }
            Pending entry = pending.get(relayState);
            if (entry == null
                    || !Objects.equals(entry.authnRequestId(),
                                       verifiedInResponseTo)
                    || !Objects.equals(entry.registrationId(),
                                       verifiedRegistration)
                    || !now.isBefore(entry.expiresAt())) {
                return "DENY";
            }
            // remove(key, value) là atomic: chỉ một callback tiêu thụ.
            return pending.remove(relayState, entry)
                    ? entry.safeReturnRoute() : "DENY";
        }

        int pendingCount(String browserSession) {
            ConcurrentMap<String, Pending> pending =
                    byBrowserSession.get(browserSession);
            return pending == null ? 0 : pending.size();
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        Instant t = Instant.parse("2026-11-07T03:00:00Z");

        String relayA = store.begin(
                "browser-1", "req-A", "corporate", "/reports", t);
        String relayB = store.begin(
                "browser-1", "req-B", "corporate", "/settings", t);

        System.out.println(relayA.length());
        System.out.println(store.pendingCount("browser-1"));

        // Trình duyệt khác không thể tiêu thụ request của browser-1.
        System.out.println(store.complete(
                "browser-other", relayA, "req-A", "corporate",
                t.plusSeconds(1)));

        // Response-B tới trước Response-A vẫn match đúng giao dịch.
        System.out.println(store.complete(
                "browser-1", relayB, "req-B", "corporate",
                t.plusSeconds(2)));
        System.out.println(store.complete(
                "browser-1", relayA, "req-A", "corporate",
                t.plusSeconds(3)));

        // Replay B phải thất bại.
        System.out.println(store.complete(
                "browser-1", relayB, "req-B", "corporate",
                t.plusSeconds(4)));

        String relayC = store.begin(
                "browser-1", "req-C", "corporate",
                "/dashboard", t);
        System.out.println(store.complete(
                "browser-1", relayC, "req-C", "corporate",
                t.plusSeconds(181)));

        System.out.println(store.pendingCount("browser-1"));
    }
}
~~~

Biên dịch/chạy bằng Java 17 trở lên:

~~~bash
javac PendingSamlRequestsDemo.java
java PendingSamlRequestsDemo
~~~

**Stdout chính xác** (giá trị RelayState ngẫu nhiên không được in ra):

~~~text
32
2
DENY
/settings
/reports
DENY
DENY
1
~~~

Giải thích:

1. 24 byte ngẫu nhiên, Base64URL không padding, cho **32 ký tự ASCII/32 byte**, dưới giới hạn SAML RelayState 80 byte.
2. Hai tab đã tạo **hai pending entries** trong cùng `browser-1`.
3. `browser-other` không thể dùng RelayState của phiên khác.
4. Response B đến trước vẫn tìm đúng `req-B`, được lấy `/settings`.
5. Response A đến sau vẫn còn và khớp `req-A`, được lấy `/reports`.
6. Replay Response B không thể tiêu thụ lại pending B.
7. Response C đến sau TTL 180 giây bị từ chối.
8. C còn trong map ở trạng thái hết hạn nên số entry còn là 1: production **phải có TTL eviction/cleanup**; ví dụ cố ý chưa thực hiện dọn bộ nhớ.

**Ranh giới của ví dụ:** phương thức `complete` không tự xác thực các tham số được gọi là “verified”, chỉ kiểm tra logic lưu trạng thái. Production phải lấy các dữ kiện này **sau xác minh SAML**, thêm issuer/SP entityID/ACS/audience vào binding; dùng kho trạng thái có nhất quán/TTL/capacity cho nhiều node; không cho phép attacker tự cung cấp `browserSession` làm chuỗi HTTP. Giá trị phiên trong demo giả lập `HttpSession` server-side, không phải token do query param gửi đến. Mẫu trên mô phỏng hai callback được kiểm tra lần lượt; **không tự giải quyết tình huống hai callback cùng lúc ghi vào SecurityContext**.

### 7.1. Vì sao dùng `remove(key, value)`?

Với hai request đồng thời cùng `RelayState`, cả hai có thể đọc `entry` hợp lệ. Nếu dùng `get` rồi `remove(key)` rồi **luôn chấp nhận**, có nguy cơ cả hai xem là lần đầu. `ConcurrentMap.remove(key, value)` chỉ cho **một callback** tiêu thụ đúng entry ở một JVM. Trong Redis/SQL cần thao tác **compare-and-delete / state transition atomic** tương đương trên shared store.

### 7.2. Không tự bảo mật bằng `sessionStorage` hoặc `tabId`

`sessionStorage` trong browser có thể dùng để ghi **ý định giao diện theo tab**, như “tab này muốn mở reports”, nhưng không phải nguồn tin cho `issuer`, `InResponseTo`, quyền truy cập hay session binding tại server. SAML HTTP-POST ACS là navigation qua IdP: JavaScript state ở tab có thể còn hoặc mất tùy luồng, nhưng server vẫn cần **pending request đã bảo vệ**. Một `tabId` do client tự khai không chứng minh người gọi đang dùng đúng browser đã khởi tạo.

## 8. Return URL: tránh tab A bị đưa về trang của tab B

Sau khi xác thực thành công, Spring Security có thể dùng **SavedRequestAwareAuthenticationSuccessHandler** và `RequestCache` để trả về tài nguyên trước login. Vì các tab thường chia sẻ session, **saved request ở session có thể bị thay đổi bởi tab khác** nếu workflow chỉ có một vị trí lưu mục tiêu.

Ví dụ:

~~~text
Tab A muốn /reports/42  -> session.savedRequest=/reports/42
Tab B muốn /settings    -> session.savedRequest=/settings
Tab A hoàn tất login    -> bị đưa tới /settings   (nhầm tab)
~~~

Không nên “sửa” bằng cách đặt `RelayState` bằng URL tuyệt đối tùy ý rồi `sendRedirect(RelayState)` vì **open redirect** và rủi ro vượt giới hạn 80 byte. Hãy lưu `safeReturnRoute` **riêng trong mỗi pending transaction** sau khi kiểm tra allowlist route/tenant, chỉ phục hồi route sau **SAML validation + transaction consume**. Nếu không tìm được route, dùng **fallback nội bộ cố định**, ví dụ `/dashboard`, hoặc trả lỗi giao dịch; không dựa vào `Referer` hay URL do IdP/browser cung cấp.

Lưu ý: **route đích hợp lệ không đồng nghĩa user có quyền xem tài nguyên**. Nếu A yêu cầu `/reports/42` thuộc tenant khác, authorization backend vẫn phải từ chối dù AuthnRequest và RelayState hợp lệ.

### 8.1. Một ví dụ route mapping thay vì URL thô

| Dữ liệu được phép lưu trước login | Đường dẫn SP tạo sau login |
| --- | --- |
| `route=dashboard` | `/dashboard` |
| `route=settings` | `/settings` |
| `route=report; id=42` với report ID hợp lệ | `/reports/42` |
| URL ngoài hoặc route không thuộc allowlist | `/dashboard` hoặc từ chối |

Không lưu thông tin mật, token, kết quả tìm kiếm nhạy cảm hoặc SAMLResponse trong RelayState. Nếu cần deep-link có query parameters, phải kiểm tra/encode từng thành phần theo chính sách ứng dụng trước khi lưu server-side state.

## 9. Cookie, SameSite và session fixation: ba nguồn lỗi khác nhau

### 9.1. SameSite khi IdP POST về ACS

SAML **HTTP-POST binding** thường là **cross-site POST từ IdP về SP**. Với nhiều trình duyệt, cookie `SameSite=Lax` không được gửi cho cross-site POST thông thường; `SameSite=Strict` càng hạn chế. Một request chờ được lưu trong `HttpSession` có thể trở thành **không tìm thấy** ở ACS vì trình duyệt không gửi cookie.

Biện pháp tùy môi trường là cấu hình chính sách cookie tương thích (ví dụ `SameSite=None; Secure` cho cookie phù hợp trên HTTPS, theo khả năng browser), hoặc thiết kế **transaction binding cookie** bảo vệ riêng. Phải đánh giá CSRF và tracking policy; không gắn `SameSite=None` trên mọi cookie mà không xem xét rủi ro. Spring Security có ngoại lệ CSRF theo đúng **ACS endpoint** cho SAML POST; không tắt CSRF toàn site.

**Cực kỳ quan trọng:** dùng cache chỉ theo RelayState để vượt tình huống cookie không được gửi **không tự tái tạo mối liên hệ an toàn với browser khởi tạo**. Cần một bằng chứng binding còn kiểm chứng được khi callback đến, thay vì bỏ correlation.

### 9.2. Session fixation protection đổi session ID sau login

Spring Security thường bảo vệ session fixation bằng cách đổi session ID khi authentication thành công, ví dụ `changeSessionId` trên Servlet container hiện đại. Nếu response B thành công trước, session cookie có thể được xoay; response A còn đang từ IdP quay về có thể gửi **cookie cũ** hoặc request song song đang dùng snapshot của session trước khi thay đổi.

Lúc này lỗi không chỉ là “repository đã ghi đè”; có thể là:

- Pending A bị đặt trong session ID cũ nhưng callback A tới sau khi phiên đã đổi.
- Node A/B đồng thời commit `SecurityContext`, session strategy hoặc cookie.
- Browser nhận hai response `Set-Cookie` gần nhau và thứ tự áp dụng cuối cùng không phải thứ tự yêu cầu.
- Một callback đã xác thực cùng principal, callback khác muốn đổi principal/tenant.

**Không nên tắt session fixation protection** chỉ để làm đa tab hết lỗi. Thiết kế phải có chính sách giữ/migrate pending transactions qua session ID rotation an toàn theo framework và đảm bảo browser-bound evidence vẫn phù hợp. Với những luồng đã bị mất bằng chứng, kết thúc an toàn bằng lỗi rõ ràng và bắt đầu giao dịch mới.

### 9.3. Một profile khác / trình duyệt ẩn danh

Hai tab thường cùng cookie, nhưng Chrome profile khác, Firefox container khác, cửa sổ ẩn danh hoặc trình duyệt khác có **cookie jar riêng**. Khi session khác, cùng user ở IdP chưa chắc đồng nghĩa SP cho phép cùng một RelayState/callback. Đừng dùng email/NameID để kéo giao dịch từ phiên A sang phiên B. Nếu mục tiêu kinh doanh là đồng bộ “đăng nhập trên nhiều thiết bị”, đó là vấn đề IdP SSO/session management, **khác** bài toán nhiều AuthnRequest đang chờ trong cùng browser session.

## 10. Multi-node và bộ nhớ dùng chung

Một ứng dụng SP chạy sau load balancer có thể tạo AuthnRequest trên **node A** rồi nhận ACS callback tại **node B**. Nếu dùng `HttpSession` cục bộ, node B không có pending request. Nếu dùng cache phân tán chỉ theo RelayState, node B có thể tìm thấy pending nhưng **có thể mất browser binding** nếu thiết kế kém.

~~~text
Browser (hai tab, cùng cookie)
       |
       v
   Load Balancer
   /           \
Node A          Node B
begin req-A     begin req-B / callback A, B
   \            /
    \          /
    Shared HttpSession + Pending Transaction Store
       key: browser-session-binding + RelayState
       value: AuthnRequest ID, IdP registration,
              ACS, trusted return route, TTL
       atomic consume: mỗi transaction một lần
~~~

**Các bảo đảm vận hành nên có:**

- Session store chia sẻ/replication đáng tin cậy; lưu session đã đổi ID theo cơ chế hỗ trợ của Servlet/Spring Session.
- Pending requests có key theo browser/session **và** giao dịch, không chỉ một key tĩnh.
- Atomic insert/consume khi callback song song; một request chỉ một bên thắng.
- TTL ngắn cho pending; cleanup theo policy và giới hạn số pending mỗi session.
- Key theo namespace ứng dụng/môi trường/IdP, không trộn hai tenant.
- Không eviction sớm các pending requests còn hợp lệ vì áp lực bộ nhớ nếu không có fallback an toàn.
- Khi store timeout/partition, **fail closed** thay vì mặc định chấp nhận response không tương quan.
- Xem xét **strong consistency**/failover nếu không muốn cùng giao dịch được tiêu thụ hai lần.
- Có logs/metrics không chứa SAMLResponse hay cookie để phân biệt duplicate, expired, wrong browser, wrong request ID, node mismatch.

**Sticky session** có thể giảm thiếu session ngẫu nhiên, nhưng không thay thế thiết kế bảo vệ khi rolling deployment, failover, tab tạo hai request và callback vượt node.

## 11. Cạnh tranh ghi SecurityContext: điều kiện quan trọng ngoài pending store

Nhiều request chờ được lưu riêng giải quyết lỗi ghi đè `AuthnRequest`, **chưa giải quyết** việc nhiều callback đồng thời **cùng ghi SecurityContext trong một browser session**.

### 11.1. Các dạng cạnh tranh

| Tình huống | Rủi ro | Chính sách khuyến nghị |
| --- | --- | --- |
| A và B cùng local principal, callback lệch vài giây. | Session ID/cookie xoay, saved request/redirect nhầm tab. | Có thể coalesce/idempotent theo policy; kiểm thử session persistence và URL riêng giao dịch. |
| A là account X, B là account Y, cùng cookie. | Một callback ghi đè `Authentication` của callback kia. | **Không âm thầm đổi principal**; yêu cầu flow chuyển tài khoản có chủ đích hoặc reject callback xung đột. |
| A dùng IdP tenant A, B tenant B. | IdP mix-up hoặc user bị chuyển tenant không mong muốn. | Pin registration/issuer/tenant vào pending request, reject mismatch. |
| B đã login, A là callback muộn của giao dịch trước logout. | Phiên cũ có thể được phục hồi trái ý muốn. | Revocation/epoch/transaction generation; không chấp nhận pending thuộc phiên đã logout hoặc đã chuyển identity. |
| B tạo session mới, A mang cookie cũ. | Không tìm thấy pending hoặc tạo lại session sai. | Session rotation-aware binding, fail closed nếu không chứng minh được giao dịch. |
| Client retry POST ACS của B. | Hai lần tạo Authentication/session từ cùng assertion. | Single-use pending + assertion replay protection. |

Nên có **login generation** hoặc epoch cho mỗi browser/session để hủy những pending requests thuộc **thế hệ phiên đã bị thu hồi**, nếu mô hình nghiệp vụ chỉ cho một login cuối cùng. Nhưng nếu epoch khiến callback A cũ bị từ chối, đó là **quyết định có chủ ý**; đừng tuyên bố A vẫn độc lập được cho phép như trong mọi cấu hình. Phải chọn rõ ưu tiên giữa UX “đa tab đều thành công” và chính sách “chỉ một authentication tại một thời điểm”.

### 11.2. Cách tối ưu khi cả năm tab cùng hết hạn

Một giải pháp ứng dụng có thể áp dụng **single-flight login**: thay vì tất cả tab đều khởi tạo SAML, một tab trở thành “leader” bắt đầu AuthnRequest, các tab khác chờ tín hiệu hoặc truy vấn lại trạng thái auth sau khi hoàn tất. `BroadcastChannel`, `storage` event hoặc trạng thái server giúp phối hợp UX, nhưng phải xử lý leader tab bị đóng và timeout. **Những tín hiệu client này không phải bằng chứng xác thực**; server vẫn phải xác minh SAMLResponse và session.

Nếu chỉ một tab thật sự cần SSO, sẽ ít pending requests và ít race hơn. Tuy nhiên, không dựa hoàn toàn vào leader logic: browser có thể mất message, disable JS hoặc mở tab mới. Backend vẫn phải có hành vi an toàn khi nhiều request đến.

## 12. Kiểm thử bắt buộc: các tình huống và expected results

| Kịch bản | Kết quả an toàn |
| --- | --- |
| Một tab khởi tạo req-A và nhận response A đúng hạn. | Xác minh SAML, consume A, tạo authentication theo policy. |
| Hai tab cùng session tạo A/B, response B về trước A. | Mỗi response match đúng `InResponseTo`/RelayState; không dùng nhầm pending. |
| Ba tab A/B/C, C bị timeout nhưng A/B còn hạn. | C bị từ chối; A/B không bị xóa tùy tiện. |
| Response A có `InResponseTo=req-B`. | **Từ chối**, không lấy bất kỳ request đang chờ nào để “vá” mismatch. |
| Response A có đúng ID nhưng RelayState của B. | **Từ chối**; không được chọn request khác. |
| Response A đến với browser session khác. | **Từ chối** dù request tồn tại trong cache toàn cục. |
| Response A gửi lại sau khi đã consume. | **Từ chối replay**, không tạo session mới. |
| Phát lại một assertion có chữ ký hợp lệ nhưng request ID không còn pending. | Từ chối; không chuyển sang IdP-initiated. |
| A dùng IdP-X nhưng callback chứa issuer IdP-Y. | Từ chối; registration được pin với giao dịch. |
| Hai callback cùng claim/relay trên hai node. | Tối đa một callback qua gate atomic. |
| Hai callback khác nhau cùng principal cùng lúc. | Xử lý theo chính sách session generation; không lỗi ngẫu nhiên do overwrite. |
| Hai callback khác principal cùng cookie. | Không âm thầm đổi principal; reject/switch account có chủ đích. |
| B login thành công, A callback sau logout. | A không khôi phục session đã thu hồi. |
| Session cookie bị chặn bởi SameSite. | Không hạ cấp correlation; chẩn đoán cookie, áp dụng binding an toàn hoặc yêu cầu login mới. |
| Callback đến node khác sau rolling deployment. | Tìm state chung đúng session nếu khả dụng, hoặc fail closed. |
| SavedRequest của tab B ghi đè A. | Return route theo từng transaction hoặc fallback nội bộ; không open redirect. |
| RelayState bị đổi thành `https://evil.example/`. | Không lấy làm `Location` chuyển hướng. |
| RelayState dài quá 80 byte. | Không tạo/không chấp nhận theo chính sách binding, không cắt cụt âm thầm. |
| 100 request cùng session trong vài giây. | Rate limit/cap pending; không cạn RAM/Redis. |
| Logout diễn ra khi vẫn còn pending requests. | Invalidate/cancel pending liên quan theo policy, không cho callback cũ đăng nhập lại. |

### 12.1. Test harness thực tế cho Spring Boot

Dùng một **IdP test** (hoặc bộ SAMLResponse có chữ ký hợp lệ với trust anchor test), một ứng dụng Spring Boot đang chạy và một trình duyệt với DevTools. Khuyến nghị:

1. Đặt timeout phiên thấp trong **test environment** (không áp dụng nguyên cho production).
2. Mở 3–5 tab cùng origin, cho tất cả vào resource cần login.
3. Điều phối cho từng tab phát AuthnRequest gần cùng thời điểm và ghi lại **chỉ request IDs/RelayState đã che bớt**; không log assertion hay cookie thật.
4. Cố ý làm IdP trả response theo thứ tự B → A → C.
5. Kiểm tra mỗi response chỉ khớp một pending, không bị ghi đè; khi hết hạn thì bị từ chối.
6. Chạy lại với **hai Spring Boot instances** dùng shared store/session.
7. Kiểm tra trường hợp browser không gửi cookie ở POST ACS, session fixation rotation, redirect theo tab và account conflict.
8. Nếu custom repository, viết unit tests cho atomic remove/expiry/cap và integration tests chứng minh Spring filter/converter thực sự gọi repository đó.

**Không tắt validator chữ ký, audience, recipient, InResponseTo, replay trong test để tuyên bố đa tab đã được xử lý an toàn.** Test storage đơn lẻ không chứng minh toàn bộ SAML login flow đúng.

## 13. Bảng chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| `InResponseTo` sai chỉ khi login nhiều tab. | Repository chỉ giữ request cuối, hoặc callback match sai relay. | Đếm pending theo session, requestId/RelayState; kiểm tra triển khai/version và multi-entry store. |
| Authentication request not found sau cross-site POST. | Cookie `SameSite` khiến mất session, hoặc session ID đã xoay. | Kiểm tra cookie được gửi vào ACS, SessionRepository và session fixation strategy. |
| Tab A bị chuyển tới trang tab B. | `SavedRequest` chung bị ghi đè, redirect lấy từ global state. | Lưu safe route theo mỗi transaction, success handler xử lý có giới hạn. |
| Một request SAML được xác thực hai lần. | Không atomic consume, thiếu replay store. | Single-use pending và assertion replay marker. |
| Multi-node chỉ node A đăng nhập được. | Session/request store cục bộ, thiếu replication. | Shared session/store, atomic semantics, consistency. |
| Đăng nhập thành user/tenant không mong muốn. | Hai callback ghi SecurityContext chung, hoặc IdP mix-up. | Pin registration/issuer/tenant, điều phối account switch, kiểm tra principal trước commit. |
| Callback cũ đăng nhập lại sau logout. | Outstanding request không được hủy theo session generation. | Revoke pending và session epoch khi logout. |
| Sau khi bật cache theo RelayState, login CSRF test qua. | Cache không có browser binding. | Khôi phục browser/session proof, fail closed khi không có. |
| Tab vẫn thấy trang “chưa login” dù browser đã đăng nhập. | UI state stale, JS/SPA chưa refresh hoặc request cũ. | Re-check server session; xử lý refresh UX, không thay đổi security principal dựa vào JS. |
| RelayState đúng nhưng signature fail. | SAML trust/key/issuer sai; là lỗi riêng với storage. | Kiểm tra provider SAML validators, metadata, certificate rotation. |
| Spring trả 403 khi IdP POST ACS. | ACS path/filter chain/CSRF ngoại lệ không khớp. | So metadata ACS và runtime matcher; đừng tắt CSRF toàn site. |

**Thứ tự debug:** (1) request vào đúng filter không → (2) cookie/browser session có được giữ không → (3) repo có đúng pending ID/relay/registration không → (4) provider xác minh SAML gì → (5) session persistence/rotation có race không → (6) redirect target thuộc transaction nào → (7) authorization nghiệp vụ có cho phép tài nguyên đích không.

### 13.1. Log/metric tối thiểu

Để theo dõi production, gợi ý các metric **tự định nghĩa** (không phải metrics có sẵn của framework):

~~~text
saml_pending_created_total{registration}
saml_pending_count_per_session_histogram
saml_pending_expired_total
saml_pending_not_found_total
saml_pending_browser_mismatch_total
saml_pending_inresponse_to_mismatch_total
saml_pending_replay_total
saml_multitab_concurrent_callback_total
saml_auth_session_rotation_conflict_total
saml_return_route_fallback_total
saml_pending_store_latency
~~~

Với audit, ghi `correlationId`, registration đã cấu hình, requestId rút gọn/hash, node, loại lỗi, timestamp UTC và số pending. Tránh log toàn bộ `SAMLRequest`, `SAMLResponse`, NameID, session cookie, assertion, private key hoặc RelayState chứa thông tin nhạy cảm. Đặc biệt, khi thiếu cookie vì `SameSite`, **không log cookie raw** để “debug nhanh”.

## 14. Những cách sửa sai thường gặp

1. **“Chỉ giữ AuthnRequest mới nhất, response cũ thì coi như login mới.”** Sai: không được bỏ `InResponseTo`; cần trạng thái từng transaction hoặc một chính sách single-flight rõ.
2. **“Đưa mọi AuthnRequest vào Redis theo RelayState là đủ.”** Sai: nếu không có browser binding có thể mở login CSRF/session swapping.
3. **“Tab nào có `tabId` là session độc lập.”** Sai: các tab cùng cookie chia sẻ `HttpSession`/SecurityContext.
4. **“Có đúng RelayState nghĩa là XML đã được xác minh.”** Sai: RelayState không phải chữ ký hay credential.
5. **“Response-A match request-B vì cùng user.”** Sai: `InResponseTo` phải đúng ID của AuthnRequest đã phát.
6. **“Cho dùng lại pending nếu retry POST bị lỗi.”** Sai: phải có single-use/idempotency và assertion replay protection.
7. **“Khi B thành công thì xóa toàn bộ pending kể cả A mà không báo.”** Sai nếu sản phẩm hỗ trợ đa request; cần policy rõ và thông báo UX hợp lý.
8. **“Để browser quyết định return URL sau login.”** Sai: có thể open redirect; dùng server-side safe route per transaction.
9. **“Tắt SameSite/CSRF/session fixation hết cho dễ.”** Sai: phải chọn cấu hình cookie và ngoại lệ ACS đúng phạm vi, giữ CSRF và fixation defense.
10. **“Sticky session nghĩa là không cần shared state.”** Sai: không bảo đảm khi failover và không chống hai request ghi đè trong cùng node.
11. **“Callback nào đến sau sẽ được quyền đổi user.”** Sai: phải có chính sách account switch, đặc biệt khi hai IdP/tenant khác nhau.
12. **“A hết hạn thì chấp nhận B có ID tương tự.”** Sai: ID và RelayState là theo từng transaction, không tự fallback.
13. **“Chỉ unit test Map<RelayState, Request> là đủ.”** Sai: phải test Spring filter/converter/provider, cookie, proxy và hai node.
14. **“Sau khi logout, các pending cũ vẫn được phép thành công.”** Sai: cần gắn pending với session generation/revocation policy.
15. **“Session cookie Lax luôn đi cùng SAML POST.”** Sai: nhiều cross-site POST không mang cookie Lax; phải kiểm thử browser thật.

## 15. Checklist thiết kế production

1. Có phân biệt rõ **browser HTTP session**, tab UI, từng AuthnRequest và SecurityContext không?
2. Có tạo **request ID + opaque RelayState riêng** cho mỗi giao dịch, giới hạn RelayState ≤80 byte không?
3. Repository có thể chứa **nhiều pending** trong cùng browser session mà không ghi đè không?
4. Lookup/consume có **ràng buộc browser session**, registration, issuer, ACS và chính xác `InResponseTo` không?
5. Có **TTL, cap số lượng pending, cleanup, atomic consume và replay protection** không?
6. Có cấm tự hạ cấp SP-initiated thành IdP-initiated khi mất pending không?
7. Có kiểm soát return route theo từng giao dịch và chặn open redirect không?
8. Có kiểm thử SameSite khi IdP trả HTTP-POST đến ACS trên browser thực không?
9. Có kế hoạch session fixation rotation và nhiều callback đồng thời cùng ghi SecurityContext không?
10. Có chính sách khi hai callback khác principal/IdP/tenant cùng browser session không?
11. Nếu có nhiều node/region, shared store có đáp ứng consistency/fail-closed khi failover không?
12. Khi logout/account revoked, pending thuộc phiên cũ có bị hủy theo chính sách không?
13. Có test phản hồi đảo thứ tự, duplicate, timeout, sai browser/issuer, các tab cùng lúc và lỗi IdP không?
14. Có log/metric an toàn không tiết lộ assertion, cookie, SAMLResponse hay thông tin cá nhân không?

## 16. Tự kiểm tra kiến thức

1. **Hai tab cùng origin có thường có hai `JSESSIONID` khác nhau không?** — Không; thường chia sẻ cookie/SP HTTP session trong cùng browser profile.
2. **Vì sao nhiều AuthnRequest tạo ra lỗi `InResponseTo`?** — Nếu repository chỉ lưu một request cho cả session, request sau có thể thay request trước.
3. **Cần lưu một hay nhiều pending khi hỗ trợ nhiều tab?** — Nhiều pending theo **transaction ID/RelayState**, có browser binding; hoặc điều phối single-flight login có chủ đích.
4. **Có thể chỉ dùng RelayState để tra cache toàn cục rồi chấp nhận response không?** — Không, thiếu bằng chứng callback thuộc trình duyệt đã khởi tạo.
5. **Response-B về trước Response-A có làm A mất hiệu lực không?** — Không nhất thiết ở transaction store đa giao dịch; nhưng session generation và security policy có thể yêu cầu chặn A.
6. **`InResponseTo` so với trường nào?** — `AuthnRequest@ID` của chính giao dịch đã khởi tạo.
7. **Nếu SameSite=Strict làm mất cookie ở ACS, bỏ session binding có ổn không?** — Không; cần cơ chế browser proof thay thế, hoặc từ chối an toàn.
8. **Hai callback cùng phiên nhưng hai user khác nhau có thể âm thầm last-wins không?** — Không nên; phải có chính sách chuyển tài khoản tường minh.
9. **Tại sao `SavedRequest` có thể đưa tab A về trang tab B?** — Vì return target có thể là state chia sẻ trong HttpSession.
10. **Đã tiêu thụ pending A thì có được dùng lại SAMLResponse A không?** — Không; cần single-use và assertion replay protection.
11. **Sao không tắt session fixation protection để tránh cookie đổi?** — Vì sẽ giảm bảo vệ phiên; thay vào đó thiết kế xử lý session rotation/concurrency.
12. **Nếu người dùng đã logout nhưng Response-A cũ về muộn, có cho đăng nhập lại không?** — Phải áp dụng session generation/revocation policy; không tự khôi phục phiên đã bị chấm dứt.

## Tài liệu tham khảo

- [Spring Security — Producing AuthnRequests; HttpSessionSaml2AuthenticationRequestRepository và CacheSaml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security — Authenticating SAML Responses và Saml2AuthenticationTokenConverter](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security API — Saml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationRequestRepository.html)
- [Spring Security API — HttpSessionSaml2AuthenticationRequestRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/HttpSessionSaml2AuthenticationRequestRepository.html)
- [Spring Security API — CacheSaml2AuthenticationRequestRepository (6.5+)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/CacheSaml2AuthenticationRequestRepository.html)
- [Spring Security — Authentication Persistence và SecurityContextRepository](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Session Management / Session Fixation Protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security GitHub #14793 — Multi-tab SAML request overwrite case, design tradeoffs](https://github.com/spring-projects/spring-security/issues/14793)
- [OASIS SAML 2.0 Profiles — Web Browser SSO, InResponseTo, SubjectConfirmation](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [OASIS SAML 2.0 Bindings — RelayState và HTTP-POST/Redirect](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf)
