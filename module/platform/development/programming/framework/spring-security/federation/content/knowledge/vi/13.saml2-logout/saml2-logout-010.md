# Xử lý IdP không hỗ trợ SLO, lỗi một phần và thời gian chờ

> **Module:** Spring Security – federation. **Chủ đề cha:** Đăng xuất SAML2. Bài học hướng dẫn xây dựng chính sách đăng xuất an toàn cho một ứng dụng Service Provider (SP) khi Identity Provider (IdP) không hỗ trợ Single Logout (SLO), chỉ một số dịch vụ thực hiện logout, hoặc trình duyệt không nhận được LogoutResponse trong thời gian dự kiến.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **local logout**, **SP/RP-initiated SLO** và **IdP/AP-initiated SLO**.
2. Xác định năng lực SLO từ `SingleLogoutService` trong metadata tin cậy, đồng thời kiểm tra binding và signing credentials.
3. Thiết kế local-only fallback khi IdP chỉ có SSO, không hứa rằng mọi phiên ở IdP/ứng dụng khác đã biến mất.
4. Hiểu `Success`, `PartialLogout`, `Requester`, `Responder`, response sai chữ ký hoặc hoàn toàn không có response.
5. Giải thích vì sao `PartialLogout` có thể là **status cấp hai bên dưới top-level Success**, nhưng toàn bộ SP khác chưa chắc đã đăng xuất.
6. Thiết kế timeout **không phụ thuộc vào giả định browser sẽ quay lại** sau khi chuyển tới IdP.
7. Tách `POST /logout` và `POST /saml2/logout` trong Spring Security, giữ callback `/logout/saml2/slo` cho bộ lọc SAML.
8. Chạy Java 17 minh họa state machine, xây ví dụ Spring Boot 3.3 có hai chế độ local-only và SLO opt-in.
9. Bảo đảm chữ ký, issuer, đích, `InResponseTo`, `RelayState`, session scope và chống replay không bị bỏ qua khi xử lý lỗi.
10. Lập kế hoạch kiểm thử lỗi, chậm trễ, đa IdP và session phân tán; viết thông báo đúng mức độ xác nhận.

**Giới hạn:** Bài viết nói về **Spring Security Servlet SAML2 Service Provider**. Với Spring Security/OpenSAML version khác 6.3 hoặc IdP đặc thù, phải xem Javadoc/metadata và thử nghiệm thực tế. SAML SLO không tự đồng nghĩa đăng xuất mọi thiết bị hoặc mọi ứng dụng ngoài federation.

## 2. Một nút logout, ba kết quả khác nhau

Giả sử nhân viên Partner A đã đăng nhập Orders Portal (SP A) và Reports Portal (SP B), đồng thời còn cookie xác thực ở IdP.

| Tầng phiên | Ai sở hữu? | Local logout ở Orders tác động ra sao? |
| --- | --- | --- |
| Session HTTP tại Orders Portal | SP A | Có thể hủy một cách chắc chắn khi request local được xử lý. |
| Cookie/phiên SSO của IdP | IdP | SP A không thể trực tiếp xóa cookie ở domain IdP. |
| Session HTTP tại Reports Portal | SP B | Không bị local logout của SP A tự xóa. |
| Phiên ở browser/thiết bị khác | Các bên tương ứng | SLO front-channel không tự đảm bảo global device revocation. |

**Kết quả 1 — Local-only:** Orders Portal xóa session local. IdP vẫn có thể còn phiên, vì vậy khi mở lại một trang bảo vệ ở Orders, người dùng có thể được SSO lại ngay. Đây là khác biệt giữa local session và IdP session, không nhất thiết là lỗi.

**Kết quả 2 — IdP báo SLO thành công:** Orders Portal đã logout local và gửi SAML `LogoutRequest`; IdP xử lý và trả một `LogoutResponse` hợp lệ. SP có thể báo **IdP đã xác nhận xử lý**, nhưng vẫn không nên hứa rằng các thiết bị không tham gia SAML federation đều đã logout.

**Kết quả 3 — Partial hoặc chưa rõ:** IdP không liên hệ được Reports Portal, trả `PartialLogout`; hoặc browser không quay lại SP với `LogoutResponse`. SP chỉ biết chắc session local đã bị hủy, còn tình trạng session bên ngoài **chưa được xác nhận hoàn toàn**.

Chính sách an toàn là lưu và hiển thị **mức bằng chứng**, không gom mọi tình huống vào một Boolean `isLoggedOut=true`.

## 3. Ba luồng logout và ai được quyền kết thúc phiên

### 3.1. Local logout

~~~text
Browser                   Orders SP                 IdP           Reports SP
  |                          |                      |                |
  |--- POST /logout -------->|                      |                |
  |                          | invalidate session   |                |
  |                          | clear authentication |                |
  |<-- /signed-out ----------|                      |                |
  |                          |     KHÔNG LIÊN HỆ IdP / Reports        |
~~~

Local logout là phương án mặc định thích hợp khi IdP **không cung cấp SLO**. Nó không gửi SAML LogoutRequest và không cần chờ mạng IdP trước khi hủy phiên tại SP.

Trang kết thúc nên là `permitAll` và **không redirect tới trang bảo vệ** một cách tự động; nếu không, IdP session còn sống có thể SSO ngay, khiến người dùng nghĩ logout thất bại.

### 3.2. RP/SP-initiated SLO

~~~text
Browser           Orders SP                  Partner IdP             Reports SP
   |                   |                         |                       |
   |-- POST SLO ------>|                         |                       |
   |                   | local logout            |                       |
   |<-- browser action-|                         |                       |
   |-------------------- LogoutRequest -------->|                       |
   |                   |                         |-- LogoutRequest ----->|
   |                   |                         |<-- LogoutResponse ----|
   |<-------------------- LogoutResponse -------|                       |
   |-- SLO callback -->| verify response        |                       |
   |<-- result --------|                         |                       |
~~~

Spring Security thực hiện local `LogoutHandler` trước, sau đó `Saml2RelyingPartyInitiatedLogoutSuccessHandler` xây và chuyển một `LogoutRequest` tới IdP. Nếu IdP gửi `LogoutResponse` trở lại, `Saml2LogoutResponseFilter` xử lý và kiểm tra theo validator.

**Điểm quan trọng:** Sau khi chuyển browser sang IdP, SP **không còn quyền kiểm soát navigation**. IdP có thể không trả browser lại hoặc một participant có thể chặn luồng logout.

### 3.3. AP/IdP-initiated SLO

~~~text
Partner IdP           Browser/transport           Orders SP
    |                         |                        |
    |---- signed LogoutRequest ----------------------->|
    |                         |                 verify request
    |                         |                 logout target session
    |<--------------------------- LogoutResponse ------|
~~~

IdP chủ động gửi `LogoutRequest` đến SP; SP phải xác minh nguồn/đích và đúng phiên được chỉ định **trước khi cleanup**. Không chấp nhận một HTTP POST tùy ý có tên `SAMLRequest` như quyền xóa session của người khác.

Khi SP gửi LogoutResponse về IdP, quyền điều hướng browser tiếp tục thuộc về IdP/transport. `AP-initiated` cũng không tự đảm bảo mọi participant thực thi thành công.

## 4. Điều kiện IdP thực sự hỗ trợ SLO

Một IdP có `SingleSignOnService` nhưng không có `SingleLogoutService` vẫn có thể đăng nhập SAML2 bình thường.

Mảnh XML metadata **chỉ hỗ trợ SSO**:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.partner.example/sso"/>
</md:IDPSSODescriptor>
~~~

Mảnh XML có SLO:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.partner.example/slo"
        ResponseLocation="https://idp.partner.example/slo/response"/>
</md:IDPSSODescriptor>
~~~

Đây là **XML minh họa**, không phải một metadata thật đã ký hoặc đăng ký. Trong tích hợp thực tế, metadata phải đến từ **nguồn đáng tin cậy**, có issuer và credentials đúng hợp đồng.

### 4.1. Checklist capability trước khi bật SLO

| Câu hỏi | Nếu không đáp ứng |
| --- | --- |
| Có `SingleLogoutService` hợp lệ trong metadata IdP? | Chỉ dùng local logout; không đoán URL `/slo`. |
| IdP cho phép SP/RP-initiated logout? | Không tự bật flow RP-initiated. |
| IdP có thể gửi AP-initiated LogoutRequest theo profile đã thống nhất? | Không quảng bá capability AP-initiated. |
| Binding POST/Redirect phù hợp, response endpoint đúng? | Sửa cấu hình phía IdP và SP. |
| SP có signing key/certificate được IdP tin? | Chưa thể phát signed LogoutRequest đúng yêu cầu. |
| SP có SLO URL public, đúng host/scheme/HTTPS và metadata? | Chưa thể nhận callback đúng cách. |
| IdP có trả LogoutResponse và hỗ trợ Status code nào? | Xác định error/fallback và kiểm thử interoperability. |
| Các SP khác tham gia SLO đúng cách? | Không thể hứa logout liên thông toàn bộ. |
| Có monitoring và cách xử lý PartialLogout/timeout? | Không nên mô tả SLO là bảo đảm hoàn tất. |

**Có phần tử metadata chưa chứng minh hệ thống sẵn sàng.** Cần kiểm thử chữ ký, NameID/SessionIndex, callback, SessionIndex semantics và hành vi thực của IdP.

## 5. IdP không hỗ trợ SLO: local-only an toàn

Quy tắc triển khai:

1. Hủy session local và xóa `SecurityContext`/Authentication thông qua Spring Security logout handlers.
2. Không gửi `LogoutRequest` tới một URL suy đoán; không dùng URL SSO làm URL SLO.
3. Không hứa đã xóa cookie IdP hay session của SP khác.
4. Trang logout phải `permitAll`, không tự khởi tạo một luồng login mới.
5. Trên máy dùng chung, hướng dẫn logout trực tiếp tại IdP/các ứng dụng liên quan và thực hiện biện pháp bảo mật thiết bị theo chính sách.
6. Không cho trình duyệt nhập `redirectUri` tùy ý để kết thúc logout; tránh open redirect.
7. Lặp lại một local logout đã xử lý không được tạo thêm quyền hay khôi phục session.
8. Nếu cần logout mọi thiết bị, phải phối hợp **session revocation** tại từng hệ thống/IdP; SAML front-channel SLO không đủ để tự đảm bảo toàn bộ.

**Thông báo UX phù hợp:**

> “Bạn đã đăng xuất khỏi ứng dụng này. Phiên đăng nhập tại nhà cung cấp danh tính và các ứng dụng khác có thể vẫn còn. Trên máy dùng chung, hãy đăng xuất tại các dịch vụ liên quan theo hướng dẫn của tổ chức.”

Không dùng: “Đã đăng xuất khỏi tất cả ứng dụng và thiết bị” nếu SP không có bằng chứng.

### 5.1. Vì sao logout local xong có thể SSO lại?

~~~text
T0: Orders SP có session A; IdP có session I.
T1: Local logout tại Orders: A bị hủy; I chưa bị tác động.
T2: Browser mở GET /orders/private.
T3: SP không thấy session A -> khởi tạo SAML AuthnRequest.
T4: IdP thấy session I -> có thể phát SAMLResponse không hỏi password.
T5: SP tạo session B mới.
~~~

Chuỗi trên **không tự chứng minh local logout không hoạt động**. Cần phân biệt với một lỗi thật như session A chưa bị hủy, cookie local còn hiệu lực trái chính sách hoặc cache quyền không được xóa.

### 5.2. Local-only khác auto-fallback sau SLO fail

Khi biết **trước** rằng IdP không có SLO, chọn local logout có chủ đích. Khi **đã bắt đầu** SLO rồi mới gặp timeout, local session thường đã bị hủy; không thể tự chuyển browser về một flow khác và kết luận đã xử lý IdP. Hãy ghi `TIMEOUT_UNKNOWN`, không lặng lẽ gắn nhãn `SUCCESS`.

## 6. PartialLogout theo OASIS: một kết quả không trọn vẹn

### 6.1. Phân cấp mã trạng thái

SAML2 Core, mục 3.7.3.2, phân biệt trạng thái logout của **session authority** với việc các **session participants** có xác nhận được hay không. Khi session authority kết thúc phiên của chính mình nhưng một hoặc nhiều participant không xác nhận, `LogoutResponse` có thể chứa:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-resp-2"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:20Z"
    InResponseTo="_logout-req-1"
    Destination="https://orders.example/logout/saml2/slo">

    <saml:Issuer>https://idp.partner.example/saml</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success">
            <samlp:StatusCode
                Value="urn:oasis:names:tc:SAML:2.0:status:PartialLogout"/>
        </samlp:StatusCode>
    </samlp:Status>
</samlp:LogoutResponse>
~~~

**Ví dụ cố ý không có XML Signature thật**, chỉ học cấu trúc, không được đưa vào SLO endpoint để đăng nhập/đăng xuất thật.

- **Top-level Success:** IdP/session authority báo đã xử lý phiên của **chính mình** theo SAML Core.
- **Second-level PartialLogout:** Không thể xác nhận tất cả session participants đã kết thúc phiên.
- Local SP trong RP-initiated flow có thể đã hủy phiên trước đó; `PartialLogout` không đồng nghĩa local session vẫn còn.
- Không chuyển `Success + PartialLogout` thành một nhãn duy nhất “GLOBAL SUCCESS”.

### 6.2. So sánh kết quả phản hồi

| SAML LogoutResponse | Có thể kết luận sau khi xác minh? | Không được kết luận |
| --- | --- | --- |
| Top-level `Success`, không có partial | IdP báo đã xử lý logout theo phạm vi SAML. | Mọi thiết bị và ứng dụng ngoài federation đều logout. |
| Top-level `Success` + nested `PartialLogout` | IdP báo phiên của mình kết thúc; một số SP không được xác nhận. | Tất cả SP đã logout thành công. |
| `Requester` | Request bị phản đối/không hợp lệ theo xử lý của IdP. | IdP chắc chắn đã logout. |
| `Responder` | IdP gặp lỗi xử lý. | Có thể tự giả vờ response thành công. |
| Response chữ ký/issuer/destination sai | Không thể tin nội dung status. | Tin `Success` vì XML có chuỗi này. |
| Không có response | Không có xác nhận từ IdP. | Remote logout chắc chắn thành công **hoặc** thất bại. |

Tài liệu Spring Security có `Saml2LogoutResponseValidator` để xử lý LogoutResponse, nhưng **không mặc định cho rằng mọi phiên bản sẽ map nested PartialLogout sang outcome UI nghiệp vụ theo ý bạn**. Phải có integration tests/extension points cho phần diễn giải, và không bỏ qua các validator sẵn có.

### 6.3. Các loại lỗi một phần

- IdP gọi SP B nhưng SP B đang bảo trì hoặc mạng lỗi.
- Một participant không hỗ trợ SAML Logout binding được dùng.
- Browser bị chặn bởi privacy settings, SameSite/cookie hoặc chuyển hướng liên tiếp.
- IdP đã kết thúc phiên nhưng không nhận được xác nhận cuối từ mọi SP.
- Một SP xử lý logout nhưng response mất trên đường quay lại.
- Một participant kết thúc phiên ở browser hiện tại nhưng còn phiên ở thiết bị khác (ngoài chứng cứ mà SAML SLO cung cấp).

**Khi PartialLogout:** local logout vẫn giữ hiệu lực, hiển thị thông báo giới hạn, ghi log/metric và hướng dẫn user logout trực tiếp các ứng dụng còn khả năng đang đăng nhập. Không spam vô hạn LogoutRequest để ép có status Success.

## 7. Timeout không phải bằng chứng remote logout thất bại

### 7.1. Browser front-channel

~~~text
SP: POST /saml2/logout
    -> invalidate local session
    -> create/sign LogoutRequest
    -> browser goes to IdP SLO endpoint
    -> IdP may contact other SPs
    -> browser closes / network loss / callback never arrives
    -> SP does not get LogoutResponse
~~~

Kết quả đúng: **LOCAL SESSION ENDED** (nếu cleanup hoàn tất) và **IdP/others UNKNOWN**.

Thời gian chờ kết nối HTTP của một `RestTemplate` hoặc database pool không thể ép browser tự gửi callback sau khi browser đã rời SP. Cần phân biệt **network/server timeout** và **SLO response-correlation deadline**.

### 7.2. Nhiều đồng hồ timeout

| Mốc | Ý nghĩa | Tránh nhầm với |
| --- | --- | --- |
| HTTP server/client timeout | Một request hoặc kết nối có giới hạn thời gian. | Deadline browser quay về từ IdP. |
| Browser navigation/visibility | Browser có thể đóng tab hoặc không cho redirect. | Sự kiện remote logout fail. |
| SLO attempt deadline | Thời gian SP chờ confirmation cho LogoutRequest ID. | Thời hạn phiên IdP thực sự. |
| `LogoutRequest.NotOnOrAfter` khi áp dụng | Hạn xử lý request theo SAML profile. | Local HTTP session expiry. |
| SP session timeout | Hạn của phiên ứng dụng. | Hạn của LogoutResponse correlation state. |
| IdP SSO session timeout | Do IdP quyết định. | Giới hạn access local sau khi đã revoke. |

Ví dụ SP có thể chọn **deadline 60 giây** để đổi trạng thái từ PENDING thành `TIMEOUT_UNKNOWN`. Đây **chỉ là giá trị policy minh họa**, không phải mặc định của SAML/Spring. Nếu response đến muộn nhưng hợp lệ, có thể audit sự kiện late-response theo chính sách; không tự làm sống lại session hay viết đè trạng thái gây hiểu nhầm.

### 7.3. Khi dùng SOAP/back-channel

Nếu federation có SLO qua SOAP, các outbound HTTP client thực sự cần connect/read timeout, retry budget, circuit breaker và fail policy. Đây là luồng khác front-channel. Không dùng các timeout backend như một tuyên bố rằng mọi `LogoutRequest` đã tới participant qua browser.

Nếu mạng lỗi, có thể còn phiên tại IdP hoặc bên khác. Kết quả SLO không chắc chắn là điều bình thường cần phản ánh trong outcome.

## 8. Luồng quyết định trạng thái và bằng chứng

~~~text
USER_REQUESTED_LOGOUT
          |
          v
LOCAL_SESSION_ENDED
          |
          +-- IdP no SLO ----------> LOCAL_ONLY
          |
          +-- SLO enabled ---------> SLO_REQUESTED
                                      |
                                      +--> verified Success -> IDP_REPORTED_SUCCESS
                                      |
                                      +--> verified Partial -> PARTIAL_LOGOUT
                                      |
                                      +--> verified error   -> PROTOCOL_FAILURE
                                      |
                                      +--> invalid response -> INVALID_RESPONSE
                                      |
                                      +--> no response
                                                |
                                                +-- before deadline -> PENDING
                                                +-- after deadline  -> TIMEOUT_UNKNOWN
~~~

Trong RP-initiated SLO, **không phục hồi local session cũ** chỉ vì LogoutResponse lỗi hoặc timeout. Nếu người dùng muốn đăng nhập lại, phải qua flow authentication mới.

### 8.1. Correlation data

Một bản ghi chẩn đoán có thể gồm:

~~~text
attempt_id              internal random ID
registration_id         cấu hình RP-IdP đã xác minh
idp_entity_id           issuer đáng tin
logout_request_id       ID SAML LogoutRequest
sent_at                 thời điểm bắt đầu
local_logout_at         thời điểm hủy session local
deadline_at             mốc chờ response
outcome                 PENDING | PARTIAL | TIMEOUT_UNKNOWN | ...
response_id             nếu có
response_validated      boolean
top_status/nested_status chỉ sau khi đã xác minh
~~~

Không lưu raw `SAMLRequest`/`SAMLResponse`, NameID, SessionIndex, cookie hay private key trong log hoạt động mặc định. Nếu có nhu cầu điều tra, bảo vệ dữ liệu theo retention/access policy riêng.

Spring Security sử dụng `Saml2LogoutRequestRepository` để duy trì dữ liệu cần đối chiếu `RelayState` và `InResponseTo` cho LogoutResponse. Nếu thay repository mặc định hoặc chạy multi-node, phải kiểm tra correlation sống qua session invalidation và load balancer; đừng thay thư viện bằng một map tùy tiện không xử lý concurrency.

### 8.2. Những kiểm tra không được bỏ qua

1. Chọn đúng `RelyingPartyRegistration`/IdP theo context đã xác thực; không tin issuer do client nhập.
2. Xác minh XML signature bằng chứng thư tin cậy và đối tượng được ký thật sự.
3. Kiểm tra `Issuer`, `Destination`, binding, phiên bản/thời gian theo profile.
4. Với RP-initiated, đối chiếu `InResponseTo`/`RelayState` với LogoutRequest có thật và chưa dùng.
5. Chống replay/duplicate ID; không cho response cũ hoàn tất attempt mới.
6. AP-initiated request phải nhắm đúng user/session/tenant theo `NameID`/`SessionIndex` và policy.
7. Chỉ đọc status và kết luận success/partial **sau** các bước xác minh.
8. Local session logout thành công không phụ thuộc việc status remote sau đó là gì.

Không tự parse XML bằng XPath bên ngoài provider rồi sử dụng `//StatusCode` đầu tiên như nguồn trạng thái đã tin; cũng không tắt CSRF toàn cục chỉ vì IdP callback không có form CSRF token.

## 9. Java 17: state machine chạy độc lập

Một chương trình độc lập minh họa cách chuyển kết quả từ **bằng chứng đã được SAML provider xác minh** thành outcome nghiệp vụ. Chương trình **không** parse SAML XML hoặc verify signature; nó chỉ phân loại kết quả.

### 9.1. Tệp LogoutOutcomeDemo.java

~~~java
public class LogoutOutcomeDemo {

    enum Evidence {
        NONE,
        VERIFIED_SUCCESS,
        VERIFIED_PARTIAL,
        VERIFIED_ERROR,
        INVALID_RESPONSE
    }

    enum Outcome {
        LOCAL_ONLY,
        PENDING,
        IDP_REPORTED_SUCCESS,
        PARTIAL_LOGOUT,
        TIMEOUT_UNKNOWN,
        PROTOCOL_FAILURE,
        INVALID_RESPONSE
    }

    static Outcome decide(
            boolean localEnded,
            boolean sloSupported,
            Evidence evidence,
            boolean deadlinePassed) {

        if (!localEnded) {
            throw new IllegalArgumentException(
                "Local session must end before classifying");
        }

        if (!sloSupported) {
            return Outcome.LOCAL_ONLY;
        }

        return switch (evidence) {
            case VERIFIED_SUCCESS -> Outcome.IDP_REPORTED_SUCCESS;
            case VERIFIED_PARTIAL -> Outcome.PARTIAL_LOGOUT;
            case VERIFIED_ERROR -> Outcome.PROTOCOL_FAILURE;
            case INVALID_RESPONSE -> Outcome.INVALID_RESPONSE;
            case NONE -> deadlinePassed
                ? Outcome.TIMEOUT_UNKNOWN
                : Outcome.PENDING;
        };
    }

    public static void main(String[] args) {
        System.out.println("unsupported=" +
            decide(true, false, Evidence.NONE, false));
        System.out.println("pending=" +
            decide(true, true, Evidence.NONE, false));
        System.out.println("success=" +
            decide(true, true, Evidence.VERIFIED_SUCCESS, false));
        System.out.println("partial=" +
            decide(true, true, Evidence.VERIFIED_PARTIAL, false));
        System.out.println("timeout=" +
            decide(true, true, Evidence.NONE, true));
        System.out.println("error=" +
            decide(true, true, Evidence.VERIFIED_ERROR, false));
        System.out.println("invalid=" +
            decide(true, true, Evidence.INVALID_RESPONSE, false));
    }
}
~~~

### 9.2. Lệnh và stdout

Với JDK 17+:

~~~bash
javac --release 17 LogoutOutcomeDemo.java
java LogoutOutcomeDemo
~~~

**Stdout chính xác:**

~~~text
unsupported=LOCAL_ONLY
pending=PENDING
success=IDP_REPORTED_SUCCESS
partial=PARTIAL_LOGOUT
timeout=TIMEOUT_UNKNOWN
error=PROTOCOL_FAILURE
invalid=INVALID_RESPONSE
~~~

- Không có SLO -> local logout được xác nhận, IdP và SP khác chưa có bằng chứng.
- PENDING -> đã gửi request nhưng chưa có response và chưa tới deadline.
- `IDP_REPORTED_SUCCESS` -> **IdP báo** xử lý thành công, không khẳng định mọi thiết bị.
- `PARTIAL_LOGOUT` -> không phải mọi participant xác nhận.
- `TIMEOUT_UNKNOWN` -> không có bằng chứng IdP đã thành công hoặc thất bại.
- `INVALID_RESPONSE` -> không dùng status chưa được xác minh.
- Ví dụ giả định `localEnded=true`; nếu local logout không thành công, phải xử lý lỗi local riêng thay vì đoán một remote outcome.

**Phạm vi code:** Đây là mô phỏng nghiệp vụ sau khi có validation. Không copy `Evidence.VERIFIED_SUCCESS` từ HTTP request chưa được xác minh; production chỉ cấp evidence này từ một bộ xác thực SAML đáng tin.

## 10. Spring Security: phân biệt hai endpoint và callback

Spring Security cung cấp:

| Endpoint / thành phần | Chức năng |
| --- | --- |
| `POST /logout` | Local logout mặc định; hủy session/authentication qua `LogoutHandler`. |
| `POST /saml2/logout` | Tên endpoint **tùy chỉnh trong ví dụ** để khởi tạo RP-initiated SLO. |
| `POST /logout/saml2/slo` | SAML message endpoint mặc định để nhận LogoutRequest/LogoutResponse từ IdP. |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Phát LogoutRequest sau khi xử lý local logout. |
| `Saml2LogoutRequestFilter` | Xác minh và xử lý IdP-initiated LogoutRequest. |
| `Saml2LogoutResponseFilter` | Xác minh LogoutResponse cho RP-initiated flow. |
| `Saml2LogoutRequestRepository` | Lưu correlation state để đối chiếu response. |
| `Saml2LogoutRequestValidator`, `Saml2LogoutResponseValidator` | Các bộ xác minh SAML logout message theo framework/version. |

**Đừng nhầm** `/login/saml2/sso/{registrationId}` (ACS đăng nhập), `/logout/saml2/slo` (callback SLO của SP) và `/saml2/logout` (thao tác user khởi tạo SLO trong bài).

Tài liệu Spring Security minh họa tách hai endpoint:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
~~~

Từ đó, `POST /logout` chỉ logout local; `POST /saml2/logout` gửi SLO nếu IdP/registration hỗ trợ. **Không bật `saml2Logout` chỉ vì IdP hỗ trợ login**. Profile và registration phải đúng hợp đồng.

## 11. Ứng dụng minh họa Spring Boot 3.3 / Java 17

### 11.1. Cấu trúc

~~~text
saml-safe-logout/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samllogout/
    │   ├── SamlSafeLogoutApplication.java
    │   ├── SecurityConfig.java
    │   └── PageController.java
    └── resources/
        ├── application.yml
        └── templates/
            ├── home.html
            └── signed-out.html
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-safe-logout'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven { url 'https://build.shibboleth.net/maven/releases/' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

### 11.2. Main class

`src/main/java/com/example/samllogout/SamlSafeLogoutApplication.java`:

~~~java
package com.example.samllogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSafeLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSafeLogoutApplication.class, args);
    }
}
~~~

### 11.3. application.yml và profile opt-in

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}

app:
  saml:
    slo-enabled: false

---
spring:
  config:
    activate:
      on-profile: slo
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            signing:
              credentials:
                - private-key-location: "file:${SP_SAML_SIGNING_KEY}"
                  certificate-location: "file:${SP_SAML_SIGNING_CERT}"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
              binding: POST

app:
  saml:
    slo-enabled: true
~~~

- Chế độ mặc định **local-only** không yêu cầu có SLO service.
- Profile `slo` chỉ dùng **sau khi** IdP công bố `SingleLogoutService` tương thích, hai phía chốt bindings, chữ ký và SP SLO URL.
- Metadata URI là nguồn đáng tin; SP signing key/certificate phải được cấu hình qua secret/file ở máy chạy, không commit vào Git.
- `singlelogout.url` mô tả **SP callback SLO URL**, không phải IdP endpoint. IdP SLO endpoint đến từ metadata đã tin cậy.
- `{baseUrl}` là Spring URI template, còn `${...}` sau thay thế là placeholder Spring lấy từ environment.
- Có profile SLO không chứng minh nó chạy đúng; cần kiểm thử callback và response hợp lệ.

### 11.4. SecurityConfig.java

`src/main/java/com/example/samllogout/SecurityConfig.java`:

~~~java
package com.example.samllogout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${app.saml.slo-enabled:false}") boolean sloEnabled)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            );

        if (sloEnabled) {
            http.saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
        }

        return http.build();
    }
}
~~~

**Đúng phạm vi:** Khi `sloEnabled=false`, code không bật SLO và vẫn có logout local. Khi `true`, Spring SAML filter hỗ trợ request SLO cùng cấu hình registration.

Không tắt CSRF toàn cục; không tạo MVC Controller cho `/logout/saml2/slo` vì filter SAML cần xử lý callback thật. Nếu IdP dùng binding hoặc endpoint khác, phải cấu hình đồng bộ ở cả SP và IdP theo tài liệu đúng phiên bản.

### 11.5. PageController.java

`src/main/java/com/example/samllogout/PageController.java`:

~~~java
package com.example.samllogout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    private final boolean sloEnabled;

    public PageController(
            @Value("${app.saml.slo-enabled:false}") boolean sloEnabled) {
        this.sloEnabled = sloEnabled;
    }

    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("sloEnabled", sloEnabled);
        return "home";
    }

    @GetMapping("/signed-out")
    public String signedOut() {
        return "signed-out";
    }
}
~~~

`sloEnabled` chỉ là cờ của **cấu hình quản trị** cho một IdP; không phải phép kiểm tra runtime mọi participant đều logout. Với multi-IdP, một cờ toàn hệ thống không đủ.

### 11.6. home.html

`src/main/resources/templates/home.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8"/>
    <title>Đăng xuất</title>
</head>
<body>
<h1>Quản lý phiên đăng nhập</h1>
<p>
    Thoát ứng dụng này không nhất thiết kết thúc phiên tại IdP
    hoặc các ứng dụng liên quan.
</p>

<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Đăng xuất khỏi ứng dụng</button>
</form>

<div th:if="${sloEnabled}">
    <p>
        IdP đã được quản trị cấu hình hỗ trợ SAML SLO.
        Một số ứng dụng có thể vẫn không xác nhận logout.
    </p>
    <form th:action="@{/saml2/logout}" method="post">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}"/>
        <button type="submit">Yêu cầu đăng xuất liên thông</button>
    </form>
</div>
</body>
</html>
~~~

Form dùng `POST` và token CSRF do Spring/Thymeleaf cung cấp. Không đổi thành `GET` logout gây tác dụng phụ. Không nhận `sloEnabled` từ browser để quyết định tính năng hoặc IdP endpoint.

### 11.7. signed-out.html

`src/main/resources/templates/signed-out.html`:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"/>
    <title>Đã đăng xuất</title>
</head>
<body>
<h1>Đã đăng xuất khỏi ứng dụng</h1>
<p>
    Phiên tại ứng dụng này đã kết thúc. Phiên tại IdP và
    các ứng dụng khác có thể vẫn còn hoạt động.
</p>
<p>
    Nếu sử dụng máy dùng chung, hãy đăng xuất tại những
    dịch vụ liên quan theo hướng dẫn của tổ chức.
</p>
</body>
</html>
~~~

Trang này xác nhận **local logout**, không thay một verified SLO status. Khi RP-initiated SLO đã chuyển browser tới IdP, trang cuối có thể không do SP kiểm soát.

### 11.8. Chạy và giới hạn thực nghiệm

Với Java 17 và Gradle wrapper phù hợp:

~~~bash
./gradlew bootRun
~~~

Chế độ SLO opt-in, chỉ sau khi IdP đã hỗ trợ và cung cấp key/cert thích hợp:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=slo'
~~~

Trên Windows PowerShell có thể dùng `.\gradlew.bat`. `PARTNER_A_IDP_METADATA_URI`, `SP_SAML_SIGNING_KEY` và `SP_SAML_SIGNING_CERT` cần là dữ liệu **thực**. Không có IdP hoặc metadata được đăng ký, ứng dụng không chứng minh login/SLO thành công và có thể không khởi động vì cấu hình thiếu.

Quan sát: chế độ mặc định chỉ hiện form local; profile `slo` thêm form khởi tạo SLO. Local logout chuyển tới trang signed-out được permitAll. SLO logout có thể đưa browser tới IdP và **không có trang cuối cố định**.

**Giới hạn mẫu:** code trên chưa có outcome store, monitor timeout hay bản dịch `PartialLogout` thành trang UX. Bài có state machine mục 8–9 để thiết kế lớp bổ sung khi triển khai production; không khẳng định thêm `.saml2Logout(...)` tự giải quyết partial/timeout UX.

## 12. Multi-IdP: chọn năng lực theo registration, không theo một nút toàn cục

Một SP có thể tin:

~~~text
registration_id  metadata_has_slo  flow_tested  policy_enabled
partner-a        true              true         true
partner-b        false             false        false
partner-c        true              false        false
~~~

Partner A được phép hiển thị lựa chọn SLO; B và C chỉ local-only cho đến khi có hợp đồng và kết quả test. **Không mượn SLO endpoint hoặc signing certificate của A để gửi logout cho B**.

- Lấy registration từ `Authentication`/`Saml2AuthenticatedPrincipal` đã xác minh, không từ request parameter chưa tin cậy.
- IdP A và B có thể cùng NameID/SessionIndex string nhưng hai nguồn khác nhau; không xóa session sai tenant.
- Thông tin `SingleLogoutService` phải đến từ trusted metadata của đúng IdP.
- Nếu IdP chỉ hỗ trợ một hướng (RP-initiated hoặc AP-initiated), cần ghi rõ khả năng theo hướng.
- Khi callback tới node khác, bảo đảm correlation repository hoặc shared session storage phù hợp.
- Không kỳ vọng IdP-initiated request đến đúng phiên nếu ứng dụng chỉ tìm theo raw NameID và không kiểm tra SessionIndex/issuer.

`saml2Logout()` bật capability ở filter chain, nhưng vẫn phải có SLO support ở `RelyingPartyRegistration`. Một toggle toàn cục như ví dụ mục 11 **không thay thế** feature policy riêng cho mỗi đối tác trong ứng dụng đa tenant.

## 13. Xử lý logout response lỗi mà không nới bảo mật

### 13.1. Verified Success, Partial, Error và Invalid khác nhau

Chỉ áp outcome sau khi đã xác minh:
- **Verified Success:** IdP báo thành công trong phạm vi SAML.
- **Verified Partial:** top-level Success nhưng nested PartialLogout.
- **Verified Error:** top-level Requester/Responder hoặc code lỗi hợp lệ khác.
- **Invalid Response:** signature, Issuer, Destination, InResponseTo hay trust không đạt.
- **No Response:** chưa xác định, tới deadline thì TIMEOUT_UNKNOWN.

Nếu bộ validator mặc định của Spring không expose trạng thái nested theo cách UI cần, phải có extension được tài liệu version hỗ trợ, vẫn **delegate tới validator mặc định** để không bỏ check. Không dùng raw untrusted XML ở controller để cập nhật `SUCCESS`.

### 13.2. Tránh retry mù

Một LogoutRequest có ID và dữ liệu correlation. Gửi lại request ID cũ hoặc phát hàng chục request mới khi browser không quay về có thể gây replay, mixed responses và audit sai. Nếu cần retry, phải thiết kế như **một attempt mới được điều khiển**, có request ID/correlation mới theo profile, giới hạn số lần, tôn trọng trạng thái session và ghi rõ IdP có thể đã thực hiện logout trước đó.

Đừng loop `LogoutRequest` cho tới khi thấy `Success` chỉ để che việc một participant khác không hỗ trợ SLO.

### 13.3. Không phục hồi local session cũ

Một lỗi SLO sau khi local logout thành công không thể được sửa bằng cách khôi phục `SecurityContext`/JSESSIONID cũ. Nếu người dùng cần tiếp tục, một phiên mới phải trải qua authentication/authorization mới. Kể cả response cũ tới rất muộn, cũng không cấp lại quyền chỉ vì `Status=Success`.

## 14. UX và thông báo theo bằng chứng

| Outcome | Thông báo gợi ý |
| --- | --- |
| `LOCAL_ONLY` | “Đã đăng xuất khỏi ứng dụng này. Phiên tại IdP và ứng dụng khác có thể vẫn còn.” |
| `PENDING` | “Đã kết thúc phiên tại ứng dụng. Đang chờ xác nhận đăng xuất liên thông.” |
| `IDP_REPORTED_SUCCESS` | “IdP thông báo đã xử lý SLO thành công trong phạm vi liên kết.” |
| `PARTIAL_LOGOUT` | “Đã đăng xuất khỏi ứng dụng, nhưng IdP chưa xác nhận mọi dịch vụ liên quan đã đăng xuất.” |
| `TIMEOUT_UNKNOWN` | “Đã đăng xuất khỏi ứng dụng. Chưa nhận được xác nhận từ IdP.” |
| `PROTOCOL_FAILURE` | “Đã đăng xuất khỏi ứng dụng. Yêu cầu đăng xuất liên thông gặp lỗi.” |
| `INVALID_RESPONSE` | “Đã đăng xuất khỏi ứng dụng. Phản hồi SLO không thể xác minh.” |

Tránh ngôn ngữ “đã thoát toàn bộ hệ thống” sau một response thiếu `PartialLogout` nhưng không có chứng cứ về các ứng dụng/thiết bị ngoài federation.

Trang sau logout phải `permitAll`, không tự gọi protected API để tránh tự SSO lại. Nếu browser bị kẹt khi IdP fan-out, cần hướng dẫn người dùng kiểm tra dịch vụ khác và logout thủ công theo chính sách máy dùng chung.

## 15. Monitoring và hành động vận hành

### 15.1. Các metric được đề xuất (không phải metric mặc định)

~~~text
saml_slo_attempt_total{registration_id,mode}
saml_slo_response_total{registration_id,outcome}
saml_slo_partial_total{registration_id}
saml_slo_timeout_total{registration_id}
saml_slo_invalid_response_total{registration_id,reason_class}
saml_slo_local_only_total{registration_id}
saml_slo_pending_age_seconds{registration_id}
~~~

Các label không nên chứa NameID, email, raw SessionIndex hoặc request payload vì rủi ro PII và high cardinality. Cần ghi `attemptId`/`registrationId` đã được duyệt, thời điểm local logout, request ID, deadline, kết quả validation và nguyên nhân lỗi ở mức vừa đủ.

### 15.2. Triệu chứng và hướng chẩn đoán

| Triệu chứng | Khả năng lỗi | Hành động |
| --- | --- | --- |
| IdP không có SingleLogoutService | Không hỗ trợ SLO hoặc metadata không đúng. | Local-only, trao đổi lại hợp đồng. |
| SLO timeout tăng cao | IdP outage, callback bị chặn, session state mất trên node khác. | Kiểm tra browser/network/IdP và correlation repository. |
| PartialLogout tăng | Một số SP khác chậm/không phản hồi. | Phối hợp IdP và các SP; không sửa status thành success. |
| LogoutResponse invalid signature | Cert/trust sai, rotation, giả mạo. | Kiểm tra signing cert, issuer và registration. |
| Requester error | LogoutRequest không hợp lệ hoặc thiếu dữ liệu profile. | Kiểm tra NameID, SessionIndex, binding, chữ ký. |
| Đăng xuất xong SSO ngay | Phiên IdP còn sống hoặc trang redirect sai. | Kiểm tra khác biệt local/IdP, trang signed-out permitAll. |
| Callback đến nhưng InResponseTo không tìm thấy | Request repository không đúng node hoặc expiry/replay. | Shared store và regression tests; không bỏ correlation. |

## 16. Bộ kiểm thử SLO

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| S01 | IdP không công bố SingleLogoutService. | Không bật SLO, chỉ local logout. |
| S02 | Metadata có SLO nhưng đối tác chưa test. | Chưa quảng bá global logout. |
| S03 | Local POST logout với CSRF hợp lệ. | Session local bị hủy, signed-out permitAll. |
| S04 | Sau local logout, cookie IdP vẫn còn. | Có thể SSO lại; UX không khẳng định IdP đã logout. |
| S05 | RP-initiated gửi LogoutRequest hợp lệ, IdP trả Success. | Local session ended + verified IdP report. |
| S06 | IdP trả Success và nested PartialLogout. | Outcome PARTIAL, không biến thành global success. |
| S07 | IdP trả Requester hoặc Responder. | Local logout còn hiệu lực, outcome PROTOCOL_FAILURE. |
| S08 | LogoutResponse sai chữ ký/issuer. | Reject status, outcome INVALID_RESPONSE. |
| S09 | InResponseTo/RelayState sai. | Reject, không ghép nhầm attempt. |
| S10 | Browser đóng tab, không quay lại. | Sau deadline TIMEOUT_UNKNOWN. |
| S11 | Response hợp lệ tới sau deadline. | Late-response policy rõ, không khôi phục session. |
| S12 | Hai yêu cầu logout đồng thời. | Không trộn request IDs, state và callback. |
| S13 | IdP gửi LogoutRequest hợp lệ. | SP xóa đúng session theo profile, trả LogoutResponse. |
| S14 | IdP-initiated request giả mạo/thiếu trust. | Từ chối, không xóa session tùy ý. |
| S15 | Multi-IdP A hỗ trợ SLO, B không. | A dùng đúng flow, B local-only. |
| S16 | Hai IdP có cùng NameID/SessionIndex. | Không lẫn tenant/session/issuer. |
| S17 | SP local logout rồi SLO lỗi. | Không restore Authentication cũ. |
| S18 | LogoutResponse quay về node khác. | Correlation vẫn đúng hoặc fail closed, không false success. |
| S19 | IdP signing certificate rotate. | Verify bằng trusted metadata cập nhật; không tắt chữ ký. |
| S20 | SP signing cert không được IdP tin. | IdP có thể reject request; local logout còn hiệu lực. |
| S21 | Backend network timeout. | Phân biệt với browser callback timeout. |
| S22 | User bị revoke khi SLO đang chạy. | Không cấp lại quyền do response tới muộn. |
| S23 | SLO endpoint sai host/path sau reverse proxy. | Sửa metadata/URL, không tự redirect tùy ý. |
| S24 | Trang signed-out tự gọi protected API. | Test phát hiện và sửa vòng SSO tự khởi động. |

Các test S06–S12 và S18 **chưa tự động được đáp ứng bởi code mẫu mục 11**. Cần state store, status extraction và correlation policy đúng phiên bản/framework để triển khai trước production.

## 17. Runbook các sự cố thường gặp

**A — IdP không hỗ trợ SLO:** Tắt opt-in SLO ở registration, giữ local logout. Cung cấp hướng dẫn tự đăng xuất IdP/ứng dụng khác. Không dựng endpoint SLO bằng cách đoán URL.

**B — PartialLogout:** Xác minh response, phân loại PARTIAL, giữ local session đã hủy, hỏi IdP participant nào không xác nhận, cảnh báo khi tăng bất thường. Không retry vô hạn.

**C — No response/timeout:** Chờ deadline có giới hạn, đánh dấu TIMEOUT_UNKNOWN, điều tra browser/network/reverse proxy/IdP/LogoutRequestRepository. Không suy IdP chắc chắn logout hoặc chưa logout.

**D — Invalid LogoutResponse:** Từ chối status, ghi loại lỗi chữ ký/issuer/correlation không chứa PII, khắc phục trust/config. Không bỏ SAML validators.

**E — SSO lại ngay:** Kiểm tra session local đã hủy thật chưa; nếu đúng, xác định IdP session còn hiệu lực và trang signed-out có bị redirect protected path không. Không coi mọi SSO nhanh là lỗi logout.

## 18. Câu hỏi tự đánh giá

**1. IdP có SSO nhưng không có SLO, nên dùng cách nào?**  
Local logout an toàn, nói rõ rằng IdP/ứng dụng khác có thể vẫn đăng nhập.

**2. Success + PartialLogout có mâu thuẫn không?**  
Không. Status cấp trên thuộc session authority; cấp hai cho biết một số participant không xác nhận.

**3. Không nhận LogoutResponse sau 60 giây nghĩa là IdP logout thất bại?**  
Không, chỉ có thể nói chưa xác nhận; `TIMEOUT_UNKNOWN` là nhãn phù hợp.

**4. Nếu SP đã hủy local session, response lỗi có được tạo lại session cũ không?**  
Không. Muốn đăng nhập lại phải qua authentication mới.

**5. Tại sao không được tin Status XML do browser gửi trước khi verify?**  
Vì Status chưa xác minh có thể bị giả mạo; phải kiểm tra chữ ký/issuer/correlation.

**6. IdP-initiated LogoutRequest không có CSRF token, có nên tắt CSRF toàn cục?**  
Không. Dùng filter và validator SAML đúng profile; giữ CSRF cho local actions.

**7. LogoutRequestRepository dùng để làm gì?**  
Giữ dữ liệu giúp đối chiếu LogoutResponse bằng ID/RelayState và chống nhầm/replay.

**8. Có thể dùng SessionIndex trùng nhau để logout phiên ở IdP khác không?**  
Không. Session phải được xác định trong trust scope đúng issuer/registration.

**9. Sau SLO Success có thể khẳng định mọi thiết bị đều logout không?**  
Không; chỉ nói IdP báo kết quả theo phạm vi SAML.

**10. Tại sao local page sau logout cần permitAll?**  
Tránh tự kích hoạt SAML login lại khi IdP còn cookie SSO.

## 19. Checklist triển khai

- [ ] Local logout hoạt động độc lập với IdP availability.
- [ ] Có capability check từ metadata trusted theo từng registration.
- [ ] Không bật `saml2Logout` cho IdP không có SLO hợp lệ.
- [ ] SP signing key/cert và SLO callback đã được IdP đăng ký.
- [ ] `POST /logout` và `POST /saml2/logout` được phân biệt rõ.
- [ ] Callback `/logout/saml2/slo` do framework xử lý, không có controller tự parse.
- [ ] Signature, Issuer, Destination, InResponseTo, RelayState, session scope và replay được xác minh.
- [ ] PENDING/PARTIAL/TIMEOUT_UNKNOWN không bị đẩy thành SUCCESS khi thiếu bằng chứng.
- [ ] Local session không được khôi phục khi remote SLO lỗi.
- [ ] Cấu hình CSRF được giữ cho local forms; callback SAML dùng filter riêng.
- [ ] Thời hạn browser callback và backend connection timeout được phân biệt.
- [ ] Multi-node có correlation state phù hợp, callback cross-node đã test.
- [ ] Multi-IdP/tenant không dùng lẫn chứng thư, endpoints hoặc SessionIndex.
- [ ] Trang signed-out permitAll, không tự gọi protected API.
- [ ] Có metrics/alerts/runbook không làm lộ NameID, raw response hoặc private key.
- [ ] Kiểm thử ít nhất S01–S24 theo phạm vi hệ thống.
- [ ] Đã đọc tài liệu đúng phiên bản Spring Security/OpenSAML thực tế.

## Ghi nhớ

> **Local logout là việc SP có thể xác nhận; SLO bên IdP là một yêu cầu giao thức cần bằng chứng.** IdP không hỗ trợ SLO → local-only. IdP trả `PartialLogout` → không phải mọi SP xác nhận. Không có LogoutResponse vì timeout → **không biết**, không phải thành công. Giữ các ràng buộc SAML, không phục hồi session đã hủy, và không hứa nhiều hơn điều được xác minh.

### Tài liệu tham khảo chính thức

- [Spring Security – Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated SLO, local vs SLO endpoint, LogoutRequestRepository, filters/validators và callback.
- [Spring Security – Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): LogoutFilter, session invalidation, CSRF và logout success.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration và các endpoint.
- [OASIS – SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf), mục 3.7.3.2: PartialLogout là second-level status khi session participants không xác nhận.
- [OASIS – SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Single Logout Profile, bindings và xử lý session.
- [OASIS – SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html), mục 5.3: logout liên thông qua nhiều SP.
- [OASIS – Metadata for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): SingleLogoutService, Binding, Location và ResponseLocation.
- [Spring Boot 3.3 – Security and SAML2](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): Relying-party registration, credentials và singlelogout properties.
