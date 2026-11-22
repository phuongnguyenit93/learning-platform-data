# Đăng xuất SAML 2.0 do Service Provider khởi tạo và do Identity Provider khởi tạo

## 1. Vì sao logout trong federation khác logout ứng dụng thông thường?

Với SAML 2.0, người dùng có thể đồng thời có **phiên ứng dụng tại Service Provider (SP)** và **phiên đăng nhập tập trung tại Identity Provider (IdP)**. Nếu họ chỉ xóa cookie/session của một ứng dụng, phiên IdP có thể vẫn còn. Khi truy cập lại ứng dụng, trình duyệt có thể thực hiện SSO ngay mà không yêu cầu nhập lại thông tin. Ngược lại, một IdP muốn kết thúc đăng nhập toàn hệ thống cần gửi tín hiệu đến các SP liên quan. Cơ chế giao thức cho việc này gọi là **SAML 2.0 Single Logout (SLO)**.

Hai hướng khởi tạo SLO:

- **Service Provider-initiated (SP-initiated, RP-initiated):** người dùng yêu cầu logout ở ứng dụng Spring Security. SP xóa phiên cục bộ, phát `<samlp:LogoutRequest>` đến IdP và có thể nhận `<samlp:LogoutResponse>` xác nhận.
- **Identity Provider-initiated (IdP-initiated, AP-initiated):** IdP bắt đầu một yêu cầu logout, gửi `<samlp:LogoutRequest>` đến SP. SP xác minh yêu cầu, kết thúc phiên ứng dụng phù hợp và gửi `<samlp:LogoutResponse>` về IdP.

Trong Spring Security, tài liệu thường dùng **RP** (*Relying Party*) tương ứng SP, và **AP** (*Asserting Party*) tương ứng IdP. Bài viết dùng SP/IdP, nhưng cần nhận ra hai cách gọi khi đọc API.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **local logout**, **SP-initiated SLO**, **IdP-initiated SLO** và ý tưởng “logout khỏi tất cả ứng dụng”.
2. Đọc đúng `LogoutRequest`, `LogoutResponse`, `Issuer`, `NameID`, `SessionIndex`, `InResponseTo`, `Status`, `RelayState`.
3. Vẽ và giải thích luồng HTTP/browser của cả hai hướng, xác định **bên khởi tạo**, **bên kiểm tra chữ ký** và **thời điểm session SP bị hủy**.
4. Bật Spring Security SAML SLO bằng `.saml2Logout(... )` cùng `RelyingPartyRegistration`, IdP metadata và signing credentials.
5. Phân biệt điểm vào `POST /logout` với callback `POST /logout/saml2/slo` (cấu hình mặc định trong tài liệu Spring).
6. Thiết kế lựa chọn **logout chỉ tại ứng dụng** và **logout federation** bằng endpoint riêng.
7. Biết giới hạn bảo đảm: một SLO Response thành công không tự khẳng định mọi hệ thống, mọi thiết bị và mọi session đã bị hủy.
8. Điều tra các vấn đề SLO thường gặp: IdP không có `SingleLogoutService`, sai chứng chỉ, thiếu NameID/SessionIndex, cookie SameSite, request hết hạn và response không quay lại.
9. Giữ an toàn trước logout giả mạo, session fixation, replay, XML signature wrapping, open redirect và log chứa dữ liệu cá nhân.
10. Kiểm thử bằng kịch bản Java 17 đơn giản, kiểm thử HTTP và IdP/SP logs một cách có thể lặp lại.

**Ngữ cảnh kỹ thuật:** Spring Boot 3.x, Spring Security 6.x hoặc 7.x **Servlet/MVC**, Java 17 trở lên và module `spring-security-saml2-service-provider`. Cần đối chiếu tài liệu đúng bản đang chạy. Tên miền `app.example.org` và `idp.example.org` trong bài chỉ minh họa.

## 2. Ba tầng phiên đăng nhập cần phân biệt

| Tầng | Nơi giữ trạng thái | Ví dụ | Ai có quyền hủy trực tiếp? |
| --- | --- | --- | --- |
| **SP local session** | HttpSession/SecurityContext/cookie của ứng dụng | `JSESSIONID` cho `app.example.org` | Ứng dụng SP quản lý session đó |
| **IdP SSO session** | Cookie/session của nhà cung cấp danh tính | Phiên SSO tại `idp.example.org` | IdP theo chính sách của mình |
| **Các SP khác** | Session/cookie riêng của các ứng dụng khác | HR, CRM, portal, reporting | Từng SP tương ứng |

### Local logout

Logout cục bộ thường làm các việc như:
- Vô hiệu hóa HTTP session hoặc hủy SecurityContext theo cấu hình Spring Security.
- Xóa cookie/remember-me token liên quan nếu logout handler của ứng dụng được cấu hình để xử lý.
- Đưa browser về trang logout success.

Local logout **không mặc nhiên gửi SAML LogoutRequest tới IdP**. Người dùng có thể quay lại ứng dụng và SSO lại ngay nếu IdP session còn.

### Federation logout (SLO)

SLO là **một protocol conversation** giữa SP và IdP. Với SLO, các bên trao đổi thông điệp ký/xác minh và có thể lần lượt phối hợp logout những SP tham gia. Tuy nhiên:
- Phải được **IdP và SP cùng hỗ trợ/cấu hình**.
- Phạm vi kết thúc các session khác phụ thuộc topology IdP, trạng thái SAML session, chính sách sản phẩm và kết quả từng SP.
- Có thể thất bại một phần hoặc không có callback.
- Không đồng nghĩa chấm dứt **mọi phiên browser, thiết bị, OAuth token, JWT hoặc mọi ứng dụng không tham gia SAML SLO**.

Do đó hai thông báo khác nhau là phù hợp: **“Đã đăng xuất khỏi ứng dụng này”** và **“Đã hoàn tất quá trình đăng xuất liên kết theo kết quả xác minh”**. Không dùng thông báo “đã đăng xuất khỏi tất cả thiết bị” khi chỉ có bằng chứng SP local logout.

## 3. SAML LogoutRequest và LogoutResponse là gì?

SAML 2.0 định nghĩa các message giao thức riêng cho logout, độc lập với `AuthnRequest` và login `Response`.

### 3.1 LogoutRequest

Một `LogoutRequest` dùng để yêu cầu kết thúc phiên liên quan đến một principal. Những thành phần đáng chú ý:

| Trường/phần tử | Tác dụng |
| --- | --- |
| `LogoutRequest@ID` | Định danh request để đối chiếu callback và chống replay |
| `LogoutRequest@IssueInstant` | Thời điểm phát hành |
| `LogoutRequest@Destination` | SLO endpoint dự kiến của bên nhận |
| `LogoutRequest@NotOnOrAfter` | Giới hạn hiệu lực nếu bên gửi cung cấp |
| `<Issuer>` | Entity ID bên khởi tạo yêu cầu |
| `<NameID>`, `<BaseID>` hoặc `<EncryptedID>` | Định danh principal theo SAML, không mặc nhiên là email |
| `<SessionIndex>` (tùy chọn, có thể nhiều) | Ràng buộc phiên SAML cần logout theo hợp đồng/protocol |
| `<ds:Signature>` hoặc chữ ký binding | Giúp bên nhận kiểm tra nguồn/tính toàn vẹn khi áp dụng |

Ví dụ một SP phát yêu cầu (XML minh họa cấu trúc, **chưa ký**, không phải thông điệp dùng để gửi production):

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_sp-logout-001"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.org/saml/slo">
  <saml:Issuer>https://app.example.org/saml/sp</saml:Issuer>
  <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-principal-123
  </saml:NameID>
  <samlp:SessionIndex>_session-idp-456</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Từ ví dụ, ID của **LogoutRequest** và SessionIndex là hai giá trị khác nhau. Cũng không có nghĩa NameID phải là tên người dùng của Spring hoặc địa chỉ email; có IdP dùng một định danh opaque, transient hoặc persistent, cùng các qualifier phù hợp.

### 3.2 LogoutResponse

`LogoutResponse` là câu trả lời cho một LogoutRequest, thường chứa:

- `LogoutResponse@ID`: ID của response.
- `LogoutResponse@InResponseTo`: ID của request đang được trả lời.
- `Issuer`: bên phát response.
- `Status/StatusCode`: kết quả SAML, ví dụ `Success` hoặc mã lỗi/partial logout.
- Chữ ký và ràng buộc nguồn đích theo trust policy.

Ví dụ IdP trả lời một SP-initiated LogoutRequest:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_idp-logout-response-002"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:02Z"
    InResponseTo="_sp-logout-001"
    Destination="https://app.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.example.org/issuer</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

Đây cũng chỉ là minh họa **chưa ký**, không thể coi là response đáng tin. Trong tích hợp thật, bên nhận cần xác minh signature theo binding/profile, issuer, destination, InResponseTo, thời gian và status, không kết thúc giao dịch chỉ vì XML có chữ “Success”.

### 3.3 RelayState trong SLO

Khi binding/flow dùng `RelayState`, nó là tham số **ngoài XML**, đi kèm `SAMLRequest` hoặc `SAMLResponse` trong query/form. Với HTTP Redirect/POST, SAML ràng buộc giá trị ngắn (80 byte theo chuẩn) và phản hồi theo cách giữ nguyên RelayState khi đã nhận. SP có thể dùng nó để nối lại giao dịch logout. **Không đặt private key, session token, username, data nhạy cảm hoặc URL redirect bên ngoài vào RelayState.**

Trong Spring Security, một `LogoutRequest` đã phát có thể được lưu trong session/repository để đối chiếu `RelayState` và `InResponseTo` của LogoutResponse. Nếu mất state, việc xác minh callback có thể thất bại ngay cả khi phía IdP đã thực hiện logout.

## 4. SP-initiated SLO: ai khởi tạo và ai kết thúc?

Đây là kịch bản người dùng đang ở ứng dụng Spring, nhấn nút **“Đăng xuất”** với ý định kết thúc đăng nhập liên kết.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as IdP
    B->>SP: POST /logout (+ CSRF)
    SP->>SP: LogoutHandlers xóa SecurityContext / HttpSession
    SP->>SP: Tạo và ký LogoutRequest (ID, Issuer, NameID)
    SP-->>B: Trang/form/redirect chuyển SAMLRequest tới IdP
    B->>I: LogoutRequest đến SingleLogoutService
    I->>I: Kiểm tra request, xử lý IdP session / phối hợp SP khác
    alt IdP gửi callback
        I-->>B: Form/redirect mang LogoutResponse
        B->>SP: POST /logout/saml2/slo với SAMLResponse
        SP->>SP: Verify response + InResponseTo + RelayState + Status
        SP-->>B: Redirect trang logout success
    else IdP không trả callback
        I-->>B: Trang kết thúc/flow riêng của IdP
        Note over SP,B: SP local session đã bị hủy
    end
~~~

Trong Spring Security theo tài liệu hiện đại, chuỗi này thường bắt đầu bằng **`POST /logout`** khi principal là `Saml2AuthenticatedPrincipal` và SLO đã được kích hoạt trên registration. Spring sẽ:

1. Chạy `LogoutHandler` để hủy state xác thực tại SP.
2. Dùng `Saml2RelyingPartyInitiatedLogoutSuccessHandler` và `Saml2LogoutRequestResolver` để dựng/ký/serialize LogoutRequest.
3. Đưa browser tới **SingleLogoutService của IdP** theo binding đã cấu hình/thương lượng.
4. Nếu IdP trả LogoutResponse, `Saml2LogoutResponseFilter` và validator kiểm tra callback.
5. Nếu callback hợp lệ, tiếp tục trang thành công sau logout theo cấu hình, thường ví dụ `/login?logout`.

**Trật tự đáng nhớ:** SP **đã kết thúc phiên cục bộ trước khi nhận** LogoutResponse. Một callback lỗi/không tới **không có nghĩa** SP phải tự tạo lại session cũ. Đồng thời không thể tuyên bố IdP và mọi SP khác đều logout chỉ vì phiên SP đã bị hủy.

### 4.1 Những điều SP biết chắc, và điều chỉ là kỳ vọng

| Sự kiện | SP có thể biết từ chứng cứ local? |
| --- | --- |
| LogoutHandler đã vô hiệu hóa session SP | **Có**, nếu logging/kiểm thử local chứng minh |
| SP đã tạo và gửi LogoutRequest | **Có**, từ request resolver và HTTP trace |
| IdP đã nhận request | Chỉ khi có HTTP/audit hoặc acknowledgment phù hợp |
| IdP đã hủy session SSO | Cần kết quả/audit/policy, không suy từ SP session |
| Tất cả SP khác đã logout | **Không** chỉ từ một response của một SP |
| Browser có thể quay về trang success | Phụ thuộc callback/IdP control/redirect policy |

Khi không có LogoutResponse từ IdP, hãy mô tả trạng thái federation là **chưa xác nhận**; không đảo ngược local logout hoặc cho phép truy cập tài nguyên bảo vệ vì thiếu callback.

## 5. IdP-initiated SLO: IdP chủ động yêu cầu SP kết thúc phiên

Kịch bản thứ hai xảy ra khi user logout ở cổng IdP hoặc chính sách IdP kết thúc phiên SSO. IdP có thể phát LogoutRequest đến những SP mà nó ghi nhận đang tham gia phiên federation.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant I as IdP
    participant SP as Spring Security SP
    B->>I: Logout khỏi cổng IdP hoặc IdP bắt đầu SLO
    I->>I: Xác định phiên/SP tham gia theo policy
    I-->>B: LogoutRequest đã ký, đích SP SLO
    B->>SP: POST /logout/saml2/slo với SAMLRequest
    SP->>SP: Kiểm tra chữ ký, issuer, Destination, NameID / session
    alt LogoutRequest hợp lệ và tìm đúng phiên
        SP->>SP: LogoutHandlers hủy session SP
        SP->>SP: Tạo và ký LogoutResponse
        SP-->>B: SAMLResponse gửi ngược về IdP SLO endpoint
        B->>I: POST LogoutResponse
        I->>I: Kiểm tra và tiếp tục orchestration
    else Request không hợp lệ
        SP-->>B: Từ chối/HTTP 400 hoặc xử lý lỗi theo config
    end
~~~

Trong tài liệu Spring Security, phần này do **`Saml2LogoutRequestFilter`** xử lý. Khi IdP gửi `SAMLRequest` tới SLO endpoint:

1. SP tìm registration tin cậy tương ứng với IdP, không tự chấp nhận mọi issuer do browser cung cấp.
2. `Saml2LogoutRequestValidator` kiểm tra những ràng buộc mà framework/profile áp dụng.
3. Nếu request hợp lệ, SP gọi các LogoutHandler để hủy phiên local và dọn state.
4. `Saml2LogoutResponseResolver` tạo/ký `LogoutResponse` trả IdP.
5. Browser chuyển response về IdP; **IdP thường là bên quyết định bước điều hướng cuối**, không phải SP.

**Khác với logout do SP khởi tạo:** không có user bấm nút `/logout` ở SP. Yêu cầu đi vào SP thông qua endpoint nhận **protocol message từ IdP**.

### 5.1 Tại sao phải xác minh LogoutRequest trước khi hủy session?

Vì LogoutRequest có thể làm **mất phiên đăng nhập**, một request giả mạo có thể tạo tấn công **logout CSRF/denial of service**:

~~~text
Kẻ xấu → POST /logout/saml2/slo
          SAMLRequest tự tạo hoặc bị sửa
          yêu cầu logout user khác
~~~

Nếu SP chấp nhận và xóa session chỉ dựa trên tên user/NameID, kẻ tấn công có thể ép logout hoặc gây gián đoạn cho người dùng khác. Cần:
- Xác minh **chữ ký** theo IdP verification credentials và binding.
- Kiểm tra `Issuer` đúng IdP registration đã phê duyệt.
- Kiểm tra `Destination` đúng SLO endpoint công khai của SP.
- Kiểm tra thời hạn và chống replay phù hợp.
- Ràng buộc `NameID`/`SessionIndex` với đúng phiên/người dùng trong phạm vi được phép.
- Không dùng body XML thô để hủy mọi session của một account khi chưa có thiết kế an toàn/được kiểm chứng.

**SessionIndex** là một định danh SAML session do IdP cung cấp trong `AuthnStatement` ở flow đăng nhập; nó không phải `JSESSIONID`. Một IdP/ứng dụng có thể có nhiều SAML session cho cùng subject. Khi thiết kế logout nhiều phiên, phải hiểu phạm vi từng `SessionIndex` và policy IdP, không suy rằng một NameID đủ để hủy mọi thiết bị.

## 6. So sánh nhanh hai hướng SLO

| Tiêu chí | SP-initiated SLO | IdP-initiated SLO |
| --- | --- | --- |
| Ai bắt đầu? | Người dùng/ứng dụng tại SP | IdP sau logout/policy ở cổng danh tính |
| HTTP trigger trong Spring | Thường `POST /logout` với user đã authenticated | `POST /logout/saml2/slo` mang `SAMLRequest` |
| Bên tạo `LogoutRequest` | SP | IdP |
| Bên kiểm tra request | IdP | SP |
| Bên gửi `LogoutResponse` | IdP | SP |
| Ai kiểm tra LogoutResponse? | SP | IdP |
| Lúc SP xóa session | Trước khi gửi request logout ra ngoài theo flow Spring | Sau khi nhận request và xác minh hợp lệ |
| Điều hướng cuối | SP có thể điều hướng khi nhận response hợp lệ; nếu không có callback phụ thuộc IdP/browser | IdP điều khiển browser sau khi SP trả response |
| Sự cố nổi bật | Không nhận callback, mất logout-request repository, IdP từ chối logout | Chữ ký inbound sai, NameID/session mismatch, cookie không tới, SLO URL sai |
| Có tự bảo đảm mọi SP đều logout? | Không | Không |

**Tên “initiated” nói về bên phát request đầu tiên**, không cho biết bên cuối cùng đang hiển thị trang hay bên nào có phiên cục bộ.

## 7. Metadata SAML cần gì để bật Single Logout?

Hai bên phải thống nhất **endpoint SLO** và **binding** trong metadata. Một IdP có thể hỗ trợ login SSO rất tốt nhưng **không công bố `SingleLogoutService`**, nghĩa là không được mặc định coi SLO được hỗ trợ.

Ví dụ trích đoạn **IdP metadata**:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleLogoutService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://idp.example.org/saml/slo"/>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/saml/sso"/>
</md:IDPSSODescriptor>
~~~

Ví dụ trích đoạn **SP metadata**:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleLogoutService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://app.example.org/logout/saml2/slo"
      ResponseLocation="https://app.example.org/logout/saml2/slo"/>
  <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://app.example.org/login/saml2/sso/corp"
      index="0" isDefault="true"/>
</md:SPSSODescriptor>
~~~

Đây là **các trích đoạn giải thích cấu trúc**, chưa đủ làm metadata đầy đủ vì thiếu entity descriptors, cert và điều kiện triển khai. Trong metadata hoàn chỉnh:
- `SingleSignOnService`: endpoint IdP nhận AuthnRequest để **đăng nhập**.
- `AssertionConsumerService`: endpoint SP nhận **login SAMLResponse**.
- `SingleLogoutService`: endpoint xử lý **LogoutRequest/LogoutResponse**.
- `Location` là endpoint request; `ResponseLocation` có thể cung cấp địa điểm response riêng nếu profile/binding hỗ trợ. Không tự suy hai URL luôn giống nhau.
- `Binding` cho biết thông điệp SAML được vận chuyển qua HTTP-POST, HTTP-Redirect hoặc binding khác mà hai bên hỗ trợ.

**Không nhầm ACS `/login/saml2/sso/corp` với SLO `/logout/saml2/slo`.** Nếu đặt LogoutRequest vào ACS, Spring có thể không tìm được filter phù hợp hoặc từ chối payload vì loại message không đúng.

### SLO có thể dùng Redirect hoặc POST nhưng đừng đoán

OASIS định nghĩa HTTP-Redirect và HTTP-POST bindings cho các thông điệp SAML phù hợp. Spring Security SLO trong tài liệu hướng dẫn cấu hình **IdP ký và POST LogoutRequest/LogoutResponse tới `/logout/saml2/slo`** để bảo đảm tương tác theo ví dụ mặc định. Việc đổi binding/GET endpoint cần phù hợp version Spring Security, endpoint filter, metadata và signing convention của IdP. **SAML login hỗ trợ Redirect AuthnRequest không có nghĩa SLO Response qua Redirect tự nhiên được cấu hình sẵn.**

## 8. Chữ ký, chứng thư và hai loại state quan trọng

### 8.1 SP signing credential và IdP verification credential

Để ký LogoutRequest/LogoutResponse, SP cần **private signing key và public X.509 certificate**. Để xác minh SAML message do IdP ký, SP cần **public signing certificate của IdP đã được tin** từ metadata hoặc cấu hình được phê duyệt.

| Message | Bên ký | Bên xác minh | Vật liệu bên xác minh cần |
| --- | --- | --- | --- |
| SP → IdP LogoutRequest | SP | IdP | SP public signing certificate |
| IdP → SP LogoutResponse | IdP | SP | IdP public signing certificate |
| IdP → SP LogoutRequest | IdP | SP | IdP public signing certificate |
| SP → IdP LogoutResponse | SP | IdP | SP public signing certificate |

Khóa ký SLO không phải IdP TLS certificate trừ khi bên cung cấp thực sự quản lý cùng key và chính sách cho phép. **Không yêu cầu IdP private key đưa về SP**.

### 8.2 Request repository khi SP khởi tạo

Nếu SP gửi LogoutRequest rồi xóa local session, vẫn phải **nhớ request ID/RelayState để so callback**. Spring Security hỗ trợ `Saml2LogoutRequestRepository` để giữ trạng thái `LogoutRequest`. Theo tài liệu, request được lưu trong session mặc định để xác minh `RelayState` và `InResponseTo`.

Điểm nhạy:
- Xóa local authenticated session và lưu transaction chờ callback phải được framework xử lý nhất quán theo version/config. Đừng tự hủy toàn bộ state trung gian trước khi request repository lưu xong.
- Khi chạy nhiều instance, phải đảm bảo logout callback tìm được state cần thiết (session store/sticky session hoặc repository triển khai phù hợp).
- Không dùng mỗi RelayState làm bằng chứng của LogoutResponse hợp lệ; cần chữ ký, issuer, destination, InResponseTo, status và TTL.
- Không để một response cũ có thể replay để hoàn tất giao dịch khác.

### 8.3 NameID và SessionIndex quyết định phạm vi logout

Trong SAML login, IdP có thể phát `AuthnStatement SessionIndex="...">` và `Subject/NameID`. Khi logout:
- **NameID** thường là định danh SAML mà IdP dùng liên hệ subject. Nó có thể khác tên hiển thị/email.
- **SessionIndex** có thể chỉ rõ phiên IdP/SP liên quan. Một principal có thể có nhiều session; nếu có nhiều SessionIndex, cách scope logout phải theo chuẩn và hợp đồng IdP.
- Một logout request **không có SessionIndex** không được tùy tiện suy là “mọi tài khoản/mọi thiết bị”; phải hiểu semantics và giới hạn session handling trong deployment.
- Khi custom `Saml2AuthenticatedPrincipal` hoặc NameID mapping, cần đảm bảo giá trị dùng khi tạo LogoutRequest là giá trị IdP chấp nhận; không đưa email từ application database vào NameID nếu IdP phát định danh opaque khác.

## 9. Cấu hình Spring Boot 3.x: bật SAML Single Logout

Spring Security tài liệu SLO đưa ra ba điều kiện chính:
1. IdP hỗ trợ SAML SLO và metadata có `SingleLogoutService`.
2. IdP được cấu hình để gửi signed `LogoutRequest` và signed `LogoutResponse` về endpoint SLO phù hợp của SP.
3. SP có signing key X.509/PKCS#8 để ký message mà SP gửi.

### 9.1 Build dependency

Trong một project Spring Boot Servlet hiện có, đoạn **Gradle Groovy DSL**:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **snippet** trong project đã cấu hình Boot plugin/BOM/version, không phải một file build hoàn chỉnh. Đặt Shibboleth releases vào repository management theo chính sách nếu mirror nội bộ yêu cầu; không tự gắn version OpenSAML trái Spring Security BOM. Đối với Maven, sử dụng dependency SAML SP tương ứng theo Spring Boot dependency management.

### 9.2 Boot application.yml

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/run/secrets/saml/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

Giải thích:
- `corp` là registration ID cục bộ, không mặc nhiên trùng IdP entity ID.
- `assertingparty.metadata-uri` trỏ đến **IdP metadata thật đã được thẩm định**. File ở `src/main/resources/saml/corp-idp.xml` phải công bố `SingleLogoutService` hợp lệ.
- `signing.credentials` là **private key/certificate thuộc SP**, không phải private key IdP.
- `singlelogout.url` công bố SLO public URL của SP; `{baseUrl}` lấy public base URL đã được giải quyết qua Spring/proxy config.
- Mẫu file key dùng đường `/run/secrets/saml/...` **trong container**, tránh đóng private key vào JAR/source control.
- Với IdP cần thêm SLO response binding/endpoint hoặc signing policy cụ thể, điều chỉnh theo metadata, khả năng sản phẩm và version Boot/Spring Security.
- Không trộn bean `RelyingPartyRegistrationRepository` tự tạo với Boot auto-configuration cùng registration mà không hiểu precedence.

**Chỉ cấu hình trong bài không tạo được federation thật.** Cần IdP test, public SP entity ID/ACS, metadata đã tin, cookie/session strategy và policy ký phù hợp.

### 9.3 SecurityFilterChain bật login và logout

Tệp `src/main/java/com/example/federation/SamlSloSecurityConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSloSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error", "/login").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Logout(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là **mã cấu hình trong Spring Boot project**, không phải chương trình Java độc lập chạy `javac SamlSloSecurityConfig.java` khi không có dependency. Class được Spring quét trong application context. Không có stdout cố định; kết quả phụ thuộc IdP metadata, browser và chứng thư thật.

**Vai trò của `.saml2Logout(Customizer.withDefaults())`:** cài đặt khả năng xử lý SLO cho SP. Một registration vẫn cần `singleLogoutServiceLocation` hoặc property tương ứng. Chỉ gọi DSL mà không có SLO service/khóa ký cần thiết **không bảo đảm SLO hoạt động**.

### 9.4 Form logout từ trình duyệt

Với cấu hình mặc định và CSRF protection bật, một form trong trang ứng dụng có thể sử dụng template engine Spring MVC/Thymeleaf:

~~~html
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất liên kết</button>
</form>
~~~

Đoạn trên cần được xử lý bởi **Thymeleaf trong Spring MVC**, không phải file HTML tĩnh thuần. Khi tích hợp Spring Security CSRF đúng cách, framework/template hỗ trợ gửi token cần thiết. Tự phát POST mà thiếu CSRF token có thể nhận HTTP 403 **trước khi** bộ lọc logout thực hiện SLO. Không đổi thành GET /logout để “đỡ CSRF” vì logout là hành động thay đổi trạng thái, cần chống logout CSRF.

Đối với các client không có template engine, lấy CSRF token bằng cơ chế app đã công bố hợp lệ và gửi qua form/header đúng policy. Đừng tắt CSRF toàn ứng dụng.

## 10. Thay thế: tự dựng RelyingPartyRegistration trong Java

Nếu dự án không dùng Boot SAML properties, Spring Security cho phép tự dựng repository từ IdP metadata.

**Mảnh cấu hình** sau đặt trong `@Configuration` của project, trong đó biến `signingPrivateKey`/`signingCertificate` đã được tải an toàn (ví dụ qua secret manager/KeyStore, hoặc helper Spring Resource thích hợp):

~~~java
Saml2X509Credential signing =
        Saml2X509Credential.signing(signingPrivateKey, signingCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp.xml")
        .registrationId("corp")
        .singleLogoutServiceLocation("{baseUrl}/logout/saml2/slo")
        .signingX509Credentials(credentials -> credentials.add(signing))
        .build();

RelyingPartyRegistrationRepository repository =
        new InMemoryRelyingPartyRegistrationRepository(registration);
~~~

Các tên class/import cần dùng:
- `org.springframework.security.saml2.core.Saml2X509Credential`.
- `org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations`.
- `RelyingPartyRegistration` và `RelyingPartyRegistrationRepository` cùng package registration.
- `InMemoryRelyingPartyRegistrationRepository` cho snapshot cấu hình.

Đây không phải đoạn Java hoàn chỉnh chạy độc lập; các biến key/cert cần được định nghĩa. Cấu hình đầy đủ cần public entity ID/ACS hợp lệ, IdP metadata, key pair, filter chain và thông số binding khớp IdP. Spring Security 6/7 có khác biệt OpenSAML implementation; **không trộn class/version** tùy ý.

### Những vấn đề cần xác nhận khi từ metadata khởi tạo

- Metadata IdP có `SingleLogoutService` hay không?
- IdP đưa SLO request đến đúng `Location` nào?
- IdP dự kiến nhận LogoutResponse ở đâu nếu `ResponseLocation` khác?
- SP metadata được IdP nhập có SLO URL chính xác, đúng HTTPS scheme/host/port?
- IdP công bố **public signing certificate**, và SP có trust tới certificate đó?
- SP signing key/cert có được IdP phê duyệt không?
- Phiên Spring có cùng NameID/SessionIndex mà IdP dùng khi SSO login không?

Nếu IdP metadata tải qua URL HTTPS ở startup, cần tính đến việc endpoint IdP không sẵn sàng: **đừng mặc định mỗi SLO chỉ đọc metadata một lần trên browser**. Registration/cache lifecycle phụ thuộc triển khai; nếu IdP đổi SLO endpoint hoặc signing cert, có thể cần refresh/redeploy.

## 11. Bảng endpoint Spring Security: đừng nhầm ba vai trò

| Mục đích | HTTP endpoint theo tài liệu Spring | Payload | Ghi chú |
| --- | --- | --- | --- |
| Khởi tạo logout tại SP | `POST /logout` | Form POST/CSRF do ứng dụng quản lý | SP-initiated SLO khi SAML principal và config phù hợp |
| IdP yêu cầu SP logout | `POST /logout/saml2/slo` | `SAMLRequest` chứa LogoutRequest | AP-initiated; SP xác minh rồi xóa local session |
| IdP trả lời SP LogoutRequest | `POST /logout/saml2/slo` | `SAMLResponse` chứa LogoutResponse | RP-initiated callback; SP xác minh request correlation |
| SP khởi tạo SAML login | `GET /saml2/authenticate/corp` | Sinh AuthnRequest | **Không phải logout** |
| SP nhận login Response | `POST /login/saml2/sso/corp` | `SAMLResponse` chứa login Response | **ACS, không phải SLO** |

Spring dùng cùng `/logout/saml2/slo` cho **LogoutRequest và LogoutResponse**, phân biệt thông điệp theo form parameter và filter tương ứng. Mặc định URL SLO **không nhất thiết chứa `{registrationId}`** vì framework có context/transaction để nhận diện registration. Một SLO endpoint có thể tùy chỉnh trong DSL/registration, nhưng phải cập nhật IdP metadata đồng thời.

### Các lớp Spring Security liên quan

| Lớp/giao diện | Vai trò |
| --- | --- |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Sau local logout, tạo đường SLO outbound từ SP |
| `Saml2LogoutRequestResolver` | Tạo, ký/serialize LogoutRequest outbound |
| `Saml2LogoutRequestFilter` | Nhận LogoutRequest inbound do IdP khởi tạo |
| `Saml2LogoutRequestValidator` | Kiểm tra yêu cầu IdP gửi tới SP |
| `Saml2LogoutResponseResolver` | Tạo LogoutResponse khi SP trả lời IdP |
| `Saml2LogoutResponseFilter` | Nhận callback LogoutResponse từ IdP |
| `Saml2LogoutResponseValidator` | Kiểm tra LogoutResponse inbound |
| `Saml2LogoutRequestRepository` | Lưu/đối chiếu request logout SP đã phát |
| `LogoutHandler` | Dọn SecurityContext, session và các state local được cấu hình |

Những lớp trên mô tả **Spring Security Servlet SAML SLO**. Không áp dụng nguyên trạng lên WebFlux, Spring Security SAML Extension 1.x hoặc IdP product khác. Các OpenSAML provider class có tên OpenSaml4/OpenSaml5 theo version; không import bừa.

## 12. Phân biệt local logout và SAML logout bằng hai endpoint

Một ứng dụng đôi khi muốn cho người dùng hai lựa chọn rõ ràng:

- “Đăng xuất khỏi **ứng dụng này**”: hủy phiên local, **không gửi** LogoutRequest IdP.
- “Đăng xuất khỏi **phiên SSO liên kết**”: bắt đầu SP-initiated SLO.

Spring Security cho phép cấu hình hai URL riêng theo tài liệu:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DistinctLogoutConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(saml -> {})
                .logout(logout -> logout.logoutUrl("/logout"))
                .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"))
                .build();
    }
}
~~~

Đây là **lựa chọn thay thế**, **không** đăng ký thêm bean `SecurityFilterChain` này cạnh một bean khác trùng matcher một cách tùy tiện. Đặt nó trong dự án Boot với metadata/idp/signing credentials và SecurityFilterChain phù hợp.

Sau cấu hình trên:
- `POST /logout` → local logout.
- `POST /saml2/logout` → khởi tạo SAML 2.0 SLO theo registration.
- Endpoint inbound SLO như `/logout/saml2/slo` vẫn xử lý protocol message, không phải nút logout của ứng dụng.

**UX cần rõ:** nếu user logout local rồi bấm login lại, IdP session có thể lập tức SSO họ trở vào. Đó **không tự chứng minh local logout thất bại**. Nếu chính sách bảo mật yêu cầu IdP session cũng kết thúc, cần SLO hợp lệ hoặc cơ chế IdP phù hợp.

## 13. IdP-initiated SLO có luôn xóa mọi phiên của một user không?

Không. Cần phân biệt **một phiên browser** mà Spring xử lý và **tập phiên toàn hệ thống**.

Giả sử một người dùng có:
- Browser A trên laptop, session SP-A1.
- Browser B trên laptop, session SP-A2.
- Browser C trên điện thoại, session SP-A3.
- Một session IdP khác trên máy ảo.
- Một ứng dụng không hỗ trợ SAML SLO.

Một `LogoutRequest` đến browser A có thể cho SP biết session liên quan tới browser đó, nhưng **không có bằng chứng tự động rằng ứng dụng đã hủy A2, A3 hoặc mọi phiên khác**. Nếu nghiệp vụ yêu cầu “global logout”, cần:
1. IdP và từng SP hỗ trợ khả năng định danh/tra session tương ứng;
2. hợp đồng phạm vi subject + SessionIndex;
3. cơ chế server-side session registry/revocation được thiết kế/cho phép;
4. chống request giả, phân quyền, audit, retry và idempotency;
5. xác minh được các session thật sự bị hủy.

**Không viết đoạn code nhận NameID rồi hủy mọi session của cùng email theo yêu cầu bất kỳ.** Đó là bề mặt tấn công DoS lớn nếu không có validation/trust chính xác. SAML SLO front-channel trên một browser không thể thay toàn bộ session governance cho mọi thiết bị và công nghệ.

## 14. SessionIndex: một ví dụ thực tế về nhầm lẫn danh tính

Trong login SAML, IdP có thể trả:

~~~xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2026-11-07T02:30:00Z"
    SessionIndex="_idp-session-001">
</saml:AuthnStatement>
~~~

Sau đó IdP muốn kết thúc phiên này và có thể phát LogoutRequest chứa:

~~~xml
<samlp:SessionIndex
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    >_idp-session-001</samlp:SessionIndex>
~~~

**Những thứ khác nhau:**
- SAML `SessionIndex` không phải HTTP session ID của servlet container.
- `AuthnRequest@ID` không phải SAML SessionIndex.
- `LogoutRequest@ID` chỉ định danh transaction logout.
- `LogoutResponse@InResponseTo` trỏ đến **LogoutRequest ID**, không phải SessionIndex.
- `NameID` có thể là một opaque principal đã được IdP cung cấp; đừng tự đổi format/qualifier rồi kỳ vọng IdP chấp nhận.

**Một ứng dụng có thể không nhận SessionIndex hoặc không lưu đủ thông tin** nếu IdP/registration/framework profile không cung cấp. Trong trường hợp đó, không tự bịa giá trị session để làm cho SLO có vẻ hoàn chỉnh; cần kiểm tra khả năng tích hợp thực tế.

## 15. Điều gì xảy ra nếu IdP không trả LogoutResponse?

Theo tài liệu Spring, trong SP-initiated flow, IdP có thể **không** redirect/form-submit callback về SP. Các lý do:
- IdP hiển thị trang kết thúc của mình.
- IdP báo partial logout hoặc lỗi ở giao diện riêng.
- Browser bị đóng trước khi quay về.
- Cookie, SameSite, CSP, WAF, proxy hoặc network cản trở.
- IdP và SP không thống nhất response destination/binding.
- IdP chưa cấu hình Reply/ResponseLocation chính xác.

Khi đó:
- SP local session đã có thể bị invalidated.
- Spring không nhận được callback để kiểm tra Status/response correlation.
- Không có bằng chứng đã logout ở IdP/mọi SP khác.
- User có thể ở lại trang IdP; app không điều khiển được UX của browser.
- Hệ thống cần metric/log tình huống “SP local logout done; federation outcome unknown”.

**Không tự khôi phục authenticated SecurityContext** chỉ vì IdP không phản hồi. Đừng tự đánh dấu “global logout success” khi thiếu bằng chứng.

Nếu IdP trả response nhưng signature, issuer, Destination, InResponseTo hoặc Status không hợp lệ, SP phải xử lý thất bại/HTTP 400 theo framework/profile. **Không bỏ validation** để lấy trang thành công.

## 16. PartialLogout và kết quả không đồng nhất

SAML Core có status code `PartialLogout` mô tả việc logout chỉ thành công một phần. Nó thường được biểu diễn như subcode phù hợp (ví dụ khi top-level phản ánh lỗi/responder), tùy cách IdP triển khai. Một IdP có thể gặp SP khác không phản hồi hoặc không thể kết thúc phiên trên một số thành phần.

Vì vậy hãy phân biệt:

| Quan sát | Điều có thể kết luận |
| --- | --- |
| SP đã invalidated HttpSession của user | Local SP logout được thực hiện |
| IdP trả LogoutResponse `Success` được SP xác minh | Bên IdP **báo cáo** xử lý yêu cầu thành công trong giao thức, theo phạm vi chính sách |
| IdP báo `PartialLogout` | Có phần chưa logout xong; cần tra IdP logs/session coverage |
| Không nhận callback | Không xác nhận được kết quả federated logout |
| HTTP 200 khi tải trang IdP | Chỉ là kết quả HTTP; không phải SAML StatusCode |
| User vẫn SSO vào được SP sau local logout | Có thể IdP session còn; cần xem federation session |
| User vẫn truy cập token/API khác sau SLO | SAML SLO không tự revoke OAuth/JWT/API tokens |

**Tránh suy** “Success = mọi thiết bị và ứng dụng đã logout”. SAML Status là thông tin do responder báo cáo trong một conversation; mức bảo đảm toàn hệ thống phụ thuộc việc IdP biết và hủy được những phiên nào, cùng cơ chế thực tế.

## 17. Kiểm thử chuyển tiếp logout trên browser

### Test 1 — SP-initiated thành công

1. Đăng nhập SP bằng IdP test, đảm bảo phiên ứng dụng hoạt động.
2. Trong DevTools bật **Network → Preserve log**; chỉ dùng dữ liệu test có quyền.
3. Bấm form POST logout với CSRF đúng.
4. Xác minh Spring đã invalidated phiên SP, không còn truy cập route bảo vệ bằng session cũ.
5. Thấy browser chuyển tới IdP SingleLogoutService với `SAMLRequest` chứa LogoutRequest, không phải AuthnRequest.
6. Kiểm tra IdP xử lý signed LogoutRequest theo issuer/key/policy.
7. Nếu IdP trả `SAMLResponse` LogoutResponse về SP, xem `InResponseTo` và status bằng công cụ test an toàn.
8. Xem Spring kiểm tra callback và chuyển tới trang logout thành công.
9. Thử mở lại route bảo vệ; nếu IdP còn phiên, có thể SSO lại — cần phân biệt đó là lỗi IdP SLO hay chỉ local logout.

**Kỳ vọng:** có bằng chứng local session hủy, message SLO được ký/tiếp nhận và callback được xác minh nếu xuất hiện.

### Test 2 — IdP-initiated thành công

1. Login vào SP qua IdP test.
2. Sang IdP và bắt đầu logout theo chức năng IdP có hỗ trợ SLO.
3. Xác nhận IdP thực sự **phát LogoutRequest đến SP**, không chỉ xóa cookie IdP.
4. Browser POST `SAMLRequest` đến `/logout/saml2/slo`.
5. Spring xác minh chữ ký, issuer, destination, NameID/session theo validator.
6. SP invalidates session và trả signed LogoutResponse về IdP.
7. Truy cập lại route bảo vệ của SP, kiểm tra session cũ không còn.
8. Quan sát IdP tiếp tục logout SP khác hoặc hiển thị kết quả, tùy policy.

**Kỳ vọng:** request giả/sai chữ ký không xóa session, request hợp lệ dẫn đến cleanup của phiên SP thích hợp.

### Test 3 — Local logout riêng

1. Đăng nhập SP từ IdP; ghi nhận session SP (không công bố cookie).
2. `POST /logout` với cấu hình hai endpoint ở mục 12.
3. Xác nhận **không** gửi LogoutRequest tới IdP.
4. Mở login SP mới; khi IdP session vẫn còn, IdP có thể SSO lại không tương tác.
5. Không gọi đây là bug của local logout; đây là điểm khác nhau có chủ đích.

### Test 4 — Federation partial/no callback

1. Trong IdP test, mô phỏng một SP tham gia SLO bị lỗi hoặc không phản hồi.
2. Kiểm tra IdP có `PartialLogout` hoặc trạng thái riêng hay không; không đoán.
3. Mô phỏng browser đóng trước callback SP.
4. Xác nhận local session SP vẫn bị hủy.
5. Ghi metric federated logout chưa xác nhận và UX fallback, không tự tạo lại session.

## 18. Kiểm thử tiêu cực và an ninh

| Tình huống | Điều kiện cần chứng minh |
| --- | --- |
| IdP-initiated `LogoutRequest` không ký hoặc signature sai | SP không cho kẻ gửi không tin hủy phiên |
| Request có issuer không khớp registration | Reject/không hủy session của đối tác khác |
| Request chứa NameID/SessionIndex không thuộc phiên | Không hủy nhầm user/session |
| Destination trỏ host/path khác | Không chấp nhận thông điệp sai đối tượng |
| Request hết hạn hoặc replay ID | Không thực thi lặp gây tác dụng phụ trái policy |
| SP-initiated LogoutResponse có InResponseTo khác request | Không coi callback là xác nhận giao dịch đang chờ |
| LogoutResponse không ký/cert sai | Không coi status thành công là tin cậy |
| Browser cross-site POST thiếu session cookie | Lỗi correlation/cookie được phân loại, không bỏ validation |
| POST logout thiếu CSRF token | Browser không thể tự ép user logout qua request giả |
| IdP không công bố SLO metadata | SP không coi login SSO = có SLO; cấu hình rõ/fallback |
| Proxy đặt sai scheme/host | SLO Destination/ResponseLocation được sửa từ public base URL |
| 2 tab logout gần nhau | State repository không nhầm request ID/RelayState; flow idempotent |
| Multi-node/SP pod khác nhận callback | Repository/session state có thể tìm được hoặc fail an toàn |
| Lỗi IdP khi logout SP-A rồi SP-B | Báo partial/unverified rõ, không nói logout mọi SP |

**Chỉ thực hiện các test giả mạo chữ ký, replay và session mismatch trong lab/IdP test** đã được cấp quyền; không sửa thông điệp thật trên hệ thống sản xuất rồi thử với người dùng thật.

## 19. Cookie SameSite và vấn đề session trong front-channel SLO

Browser có thể POST từ IdP đến SP trong một request **cross-site**. Cookie SP đặt `SameSite=Lax` thường không được gửi trên cross-site POST thông thường; `SameSite=Strict` càng hạn chế. Điều này có thể khiến SP không tìm thấy phiên đang đăng nhập khi nhận IdP-initiated LogoutRequest, hoặc không đối chiếu được state callback trong SP-initiated logout.

Khi chẩn đoán, cần phân biệt:
- **Phiên SP đã bị hủy có chủ đích** trong SP-initiated flow.
- **Phiên bị mất vì cookie không được browser gửi** trong IdP-initiated flow.
- **Logout request repository** giữ transaction ID/RelayState phục vụ callback.
- **IdP session** đang nằm ở domain IdP, không phải cookie SP.

Các bước:
1. Xem `Set-Cookie` của SP và `Cookie` trên request POST SLO bằng browser test.
2. Đối chiếu `SameSite`, `Secure`, `Domain`, `Path`, proxy HTTPS và browser policy.
3. Xác minh session store trong môi trường nhiều replica.
4. Nếu dùng `SameSite=None; Secure` cho yêu cầu cross-site theo thiết kế, phải đánh giá CSRF/logout forgery/session fixation độc lập.
5. Không cho phép LogoutRequest giả mạo chỉ vì muốn “bỏ lỗi mất cookie”.
6. Với iframe/third-party cookie, kiểm tra chính sách chặn của browser; `SAML POST binding` không tự vượt những chính sách đó.

**Không dùng CORS header để chữa mọi lỗi SLO form POST.** Top-level HTML form navigation khác cross-origin `fetch()`. Một HTTP 403 có thể là CSRF, endpoint filter hoặc protocol validation; cần phân loại bằng logs.

## 20. Điểm khác biệt giữa browser, SLO và back-channel

SAML Web Browser SLO thường dùng **front-channel**:
- IdP hoặc SP tạo SAML message;
- Browser mang message tới bên kia bằng redirect hoặc form POST;
- Browser tiếp tục chở response/đi qua các SP.

Nếu browser đóng cửa sổ, chặn cookie, chặn script auto-post, hoặc người dùng chuyển tab, một chuỗi federation logout có thể bị gián đoạn.

**Back-channel logout** là ý tưởng server–server trao đổi qua endpoint/method khác như SOAP tùy profile/capability; không phải mọi API của Spring Security SAML SLO hỗ trợ sẵn tất cả các binding/profile. Đừng suy rằng có OpenSAML trên classpath là SP đã cung cấp SOAP Single Logout, Artifact hoặc xóa mọi JWT token tự động. Phải chọn kiến trúc ứng với requirement.

### Tại sao đăng xuất ở ứng dụng A không làm B logout ngay?

Vì khi SP-A xóa local session, SP-B vẫn giữ session riêng. Chỉ khi IdP orchestrate SLO với SP-B, hoặc ứng dụng có cơ chế server-side session revocation riêng đã cấu hình, B mới có cơ hội hủy phiên của mình. Nếu B không tham gia SLO hoặc không nhận được thông điệp, phiên B có thể còn.

### Tại sao logout từ IdP không làm SP đang mở lập tức đổi màn hình?

Nếu không có request từ browser đến SP, SP có thể tiếp tục hiển thị trang đã được render trước đó trong tab đang mở. Việc cập nhật ngay UI còn phụ thuộc frontend session check, polling, SSE/WebSocket, hoặc điều hướng; **SLO protocol không tự biến mọi tab đã mở thành màn hình logout ngay tức thì**. Các request mới đến resource bảo vệ phải kiểm tra session/authentication theo chính sách.

## 21. Java 17 độc lập: mô phỏng quyết định logout theo thứ tự

Để hiểu khác biệt **“hủy local trước khi chờ IdP trả lời”** và **“xác minh request IdP rồi mới hủy local”**, chương trình này chỉ dùng JDK 17, chạy độc lập. Nó mô phỏng trạng thái, **không parse SAML XML**, không ký/xác minh mật mã, không hủy HttpSession thật và không đại diện mọi biến thể IdP.

Tệp `SamlLogoutDecisionDemo.java`:

~~~java
public final class SamlLogoutDecisionDemo {

    record Result(String local, String federation, String response) {
    }

    static Result spInitiated(boolean idpResponseVerified) {
        // Spring SP-initiated: local logout happens before external reply.
        String federation = idpResponseVerified ? "CONFIRMED" : "UNKNOWN";
        return new Result("LOGGED_OUT", federation, "NOT_APPLICABLE");
    }

    static Result idpInitiated(
            boolean requestSignatureValid,
            boolean matchingSession) {

        if (!requestSignatureValid || !matchingSession) {
            return new Result("ACTIVE", "UNKNOWN", "REJECTED");
        }
        // Only a verified IdP request for this session is accepted.
        return new Result("LOGGED_OUT", "REQUESTED", "SENT");
    }

    public static void main(String[] args) {
        Result a = spInitiated(true);
        Result b = spInitiated(false);
        Result c = idpInitiated(false, true);
        Result d = idpInitiated(true, true);

        System.out.println("SP verified: local=" + a.local()
                + ", federation=" + a.federation());
        System.out.println("SP no callback: local=" + b.local()
                + ", federation=" + b.federation());
        System.out.println("IdP invalid: response=" + c.response()
                + ", local=" + c.local());
        System.out.println("IdP valid: response=" + d.response()
                + ", local=" + d.local());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac SamlLogoutDecisionDemo.java
java SamlLogoutDecisionDemo
~~~

Stdout **chính xác**:

~~~text
SP verified: local=LOGGED_OUT, federation=CONFIRMED
SP no callback: local=LOGGED_OUT, federation=UNKNOWN
IdP invalid: response=REJECTED, local=ACTIVE
IdP valid: response=SENT, local=LOGGED_OUT
~~~

Giải thích:
- Cả hai nhánh SP-initiated đã đánh dấu local logout trước khi biết IdP có response hợp lệ hay không.
- Nhánh IdP-initiated từ chối request giả nên **không hủy local session**.
- Chỉ request IdP được mô phỏng “signature valid + matching session” mới đi tới local cleanup và LogoutResponse.
- Biến `idpResponseVerified=true` là **giả định đầu vào**, không phải minh chứng logout ở mọi SP.
- Trong sản phẩm thật, kiểm tra thêm issuer, destination, thời hạn, signature binding/XML, session index, replay, metadata trust, TLS và browser/session state. Không lấy hai Boolean của ví dụ làm bộ xác minh SAML production.

## 22. Nguyên tắc IdP-initiated: không chỉ kiểm tra chữ ký là đủ

SAML LogoutRequest hợp lệ về chữ ký nhưng **không đúng principal/session** vẫn có thể gây lỗi nghiêm trọng nếu SP logout nhầm user.

Tối thiểu cần kiểm tra:
1. **Trust anchor/registration:** request do IdP đang được liên kết với SP này phát, không phải IdP khác.
2. **Issuer:** entity ID khớp registration.
3. **Destination:** URL public, context path, binding/endpoint phù hợp.
4. **Signature:** chữ ký thuộc đúng message/query binding và key đáng tin.
5. **Subject:** NameID/format/qualifier khớp người dùng SAML ở session liên quan; không chỉ so username/email đã normalize tùy tiện.
6. **SessionIndex:** nếu có, dùng đúng nghĩa và scope; không coi index là HTTP cookie.
7. **Liveness:** IssueInstant/NotOnOrAfter nếu có, clock skew, request ID replay.
8. **User-session binding:** xác định local session nào được phép hủy; không hủy global theo bất kỳ NameID chưa xác minh.
9. **Response:** chỉ sau xác minh request mới tạo LogoutResponse/status phù hợp.
10. **Audit:** lưu sự kiện không chứa raw NameID/Assertion hoặc signed XML trong log công khai.

Theo tài liệu Spring, `Saml2LogoutRequestValidator` có nhiệm vụ xác minh đầu vào ở SLO endpoint. Nếu chính sách ứng dụng cần validation bổ sung, tùy chỉnh theo extension point của version, **ưu tiên delegate validator mặc định rồi kiểm tra thêm**, không thay bằng no-op validator.

## 23. Phân biệt lỗi giao thức với lỗi xác minh cục bộ

| Hiện tượng | Có phải “IdP logout thất bại”? | Kiểm tra |
| --- | --- | --- |
| Spring chưa có SLO vì IdP metadata thiếu `SingleLogoutService` | Chưa đủ cấu hình federation | Metadata, policy IdP và SP SLO registration |
| `POST /logout` trả 403 ngay | Không chắc | CSRF token, security filter chain và session |
| Spring phát LogoutRequest nhưng IdP từ chối signature | IdP report SP request không hợp lệ | SP signing key/cert, IdP trust, binding |
| IdP nhận LogoutRequest nhưng không gửi callback | Chưa xác nhận | IdP audit/UX/response endpoint, browser, proxy |
| `LogoutResponse` về SP có status lỗi | IdP report lỗi/partial | StatusCode tin cậy, phối hợp SP khác |
| Spring từ chối LogoutResponse vì InResponseTo sai | Lỗi tương quan SP/local hoặc message giả | LogoutRequestRepository, session, RelayState, replay |
| IdP-initiated request ký sai | SP từ chối đúng | IdP signing cert/metadata, request tampering |
| IdP-initiated request đúng nhưng sai NameID | SP phải tránh hủy nhầm | Identity mapping, qualifier, session binding |
| POST SLO không gửi cookie | Browser/session state issue | SameSite/Secure, domain, cross-site form |
| User local logout rồi SSO lại ngay | Có thể bình thường | IdP session còn vì chỉ local logout |
| Một app vẫn còn session sau SLO | Federation coverage chưa đầy đủ | SP có tham gia SLO, timeout, IdP orchestration |
| GET tới ACS thay vì SLO | Endpoint routing lỗi | SLO Location/ResponseLocation, binding, firewall |
| HTTP 200 trên trang IdP | Không đủ | SAML status và IdP session thực tế |
| API token vẫn hoạt động sau SAML SLO | Hệ thống token riêng chưa revoke | Token/session revocation ở application layer |

**Không dùng một HTTP status để đoán toàn bộ SLO**. Trạng thái SAML nằm trong `LogoutResponse/StatusCode`; lỗi Spring local có thể là signature, issuer, message parsing, session/correlation; lỗi nghiệp vụ/token thường nằm ngoài SAML.

### Một mẫu báo cáo sự cố có chứng cứ

~~~text
Scenario: RP-initiated SAML Single Logout
SP registration: corp
Local logout: completed (session invalidated)
SAML LogoutRequest: sent (ID recorded securely)
IdP callback: not observed
Federation result: unknown / not verified
Next investigation:
  - IdP SLO event log
  - SingleLogoutService binding and ResponseLocation
  - Browser SAML form/redirect and cookies
  - SP request repository correlation
~~~

Đây là mẫu ticket **không có dữ liệu cá nhân**, không phải stdout do Spring phát. Không in raw LogoutRequest, NameID thật, RelayState, cookie, private key hoặc IdP user identifiers vào log chia sẻ.

## 24. Các nguyên nhân thường gặp khiến SLO không hoạt động

### 24.1 Không bật saml2Logout

Nếu chỉ cấu hình `.saml2Login(... )` mà không có SLO DSL/registration, chức năng logout thường là local logout. Thêm đúng SLO configuration, nhưng phải có IdP support, signing credential và endpoint. Không biến UI text “logout SSO” thành cơ chế liên kết khi backend chưa hỗ trợ.

### 24.2 Thiếu SingleLogoutService

Một metadata IdP có `SingleSignOnService` chưa chắc có `SingleLogoutService`. Phải phối hợp IdP, không tự đoán SLO URL từ login URL hoặc sửa trùng một path tùy ý.

### 24.3 SP signing credential không hợp lệ

SP ký LogoutRequest/LogoutResponse bằng private key, IdP phải có public cert SP phù hợp. Nếu khóa/cert mismatch hoặc IdP metadata chưa cập nhật sau rotation, IdP sẽ từ chối. Không xuất private key cho IdP để “chữa” lỗi.

### 24.4 IdP verification certificate cũ

SP dùng public signing cert IdP để xác minh inbound request/response. Nếu IdP quay vòng ký SAML nhưng SP còn trust snapshot cũ, signature fail. Cập nhật metadata đã xác minh, có giai đoạn overlap/rotation theo policy và kiểm tra mọi replica.

### 24.5 NameID khác lúc login

IdP có thể dùng persistent/transient NameID, qualifier/format riêng. Nếu SP logout bằng application username không tương thích với NameID IdP gắn vào phiên, IdP có thể không tìm được session. Dùng chính danh tính SAML theo protocol/contract; tránh mapping tùy ý.

### 24.6 Cookie hoặc state bị mất

IdP-initiated POST về SP mà browser không gửi session cookie, hoặc SP-initiated callback đến pod khác, khiến request state/session mismatch. Cần xem SameSite, session store và repository trước khi thay protocol validation.

### 24.7 SLO URL sai do proxy

Ví dụ SP công bố `http://internal:8080/logout/saml2/slo` nhưng IdP gọi `https://app.example.org/logout/saml2/slo`. Destination validation hoặc routing thất bại. Đặt public base URL và chỉ tin forwarded headers từ proxy đáng tin; cập nhật IdP metadata.

### 24.8 Browser không hoàn thành chuỗi frontend

Một SLO flow cần browser mang tiếp nhiều POST/Redirect. Nếu browser đóng tab, chặn script hoặc IdP/third-party policy can thiệp, flow có thể không hoàn tất. Không gọi đây là "login assertion invalid" khi transaction logout chưa có response.

## 25. Kịch bản bảo mật: user logout khỏi ứng dụng nhưng vẫn đăng nhập lại

Một tình huống hỗ trợ thường gặp:

1. User mở ứng dụng A, đăng nhập qua IdP.
2. User nhấn logout, ứng dụng A hủy HttpSession.
3. User bấm “Truy cập lại A”.
4. A chuyển browser sang IdP; IdP cookie vẫn còn.
5. IdP trả SAMLResponse mới, A tạo session mới.
6. User nói “logout không có tác dụng”.

**Phân tích đúng:**
- Nếu nút đó chỉ thực hiện local logout, hành vi **SSO lại** hoàn toàn có thể xảy ra.
- Nếu nút được quảng cáo là federation logout, cần chứng minh A đã gửi LogoutRequest, IdP nhận/hoàn tất SLO, và phiên IdP tương ứng bị hủy; nếu không, lỗi thuộc cấu hình/SLO coverage.
- A không thể tự xóa HttpOnly cookie của IdP ở domain khác bằng JavaScript; browser security model không cho phép.
- Nếu SLO chỉ hủy phiên IdP ở browser A, không được hứa mọi thiết bị đã bị logout.

**Gợi ý UX:** hiển thị rõ lựa chọn “Chỉ đăng xuất khỏi ứng dụng” và “Đăng xuất khỏi phiên đăng nhập tập trung” nếu nghiệp vụ cần phân biệt; đồng thời mô tả giới hạn thực tế theo khả năng federation.

## 26. Kịch bản bảo mật: IdP phát request logout cho sai session

Một IdP có nhiều session/user có thể phát LogoutRequest mang NameID/SessionIndex không khớp browser SP đang mở. Một triển khai sơ sài sẽ:
- Chỉ kiểm tra chữ ký IdP rồi luôn hủy session bất kỳ trong browser;
- Hoặc tìm tất cả session theo email từ NameID và hủy hàng loạt;
- Hoặc không dùng request ID/replay protection.

Cách thiết kế tốt hơn:
1. Đảm bảo issuer và chữ ký request khớp IdP tin cậy.
2. Áp dụng điều kiện NameID/SessionIndex theo profile và implementation.
3. Không logout các account/tenant không liên quan.
4. Dùng session registry **chỉ nếu kiến trúc thực sự cần** và bảo vệ đúng request scope.
5. Nếu không tìm thấy session tương ứng, xử lý bằng response/error policy rõ; không tự coi là thành công toàn hệ thống.
6. Ghi audit có correlation ID, không lộ NameID và session keys.

**Spring Security có filter/validator phù hợp để xử lý SLO**, nhưng nếu business yêu cầu logout tất cả phiên/thiết bị, đó là khả năng bổ sung cần thiết kế và kiểm thử, không tự được tạo bởi `saml2Logout()`.

## 27. Checklist vận hành trong Kubernetes và nhiều node

- [ ] Mỗi pod có cùng IdP metadata/trust và SP signing keys thích hợp trong giai đoạn rollout.
- [ ] Public SP entity ID, ACS và SLO URL nhất quán trên các node.
- [ ] Logout callback đến node khác có thể tìm đúng request state qua session/redis cache/sticky session theo cấu hình.
- [ ] Có TTL, replay protection và cơ chế dọn logout transaction state.
- [ ] Cookie SameSite/Secure phù hợp SAML POST cross-site nhưng vẫn có CSRF/login/logout forgery protection.
- [ ] Không lưu private key trong container image hoặc source repository.
- [ ] Khi rotate IdP signing cert, update metadata/verification credentials được xác minh và tránh lệch phiên bản giữa pods.
- [ ] Khi rotate SP signing cert, IdP nhận public cert mới trước thời điểm SP ký bằng key mới.
- [ ] Các status SLO và metric phân biệt local / remote reported / verified / unknown / partial.
- [ ] Endpoint SLO chỉ được các filter/validation phù hợp xử lý; không đặt một controller mở cho POST arbitrary làm hủy session.
- [ ] Không tạo global session revocation từ NameID chưa tin.
- [ ] IdP outage/timeout không làm ứng dụng tạo lại session đã logout cục bộ.

## 28. Một bộ câu hỏi QA cho SP-initiated và IdP-initiated

**Bài 1.** Người dùng đang trong SP, bấm nút đăng xuất, SP gửi LogoutRequest tới IdP. Đây là luồng nào?

**Đáp án:** **SP-initiated (RP-initiated) SLO**. Bên tạo LogoutRequest đầu tiên là SP. Nếu IdP trả LogoutResponse, SP kiểm tra callback.

**Bài 2.** IdP gửi signed LogoutRequest đến `/logout/saml2/slo` của SP. Bên nào tạo LogoutResponse?

**Đáp án:** SP sau khi xác minh LogoutRequest, hủy local session phù hợp và dựng/ký LogoutResponse trả IdP. Đây là **IdP-initiated (AP-initiated)**.

**Bài 3.** Người dùng logout tại SP và nhìn thấy màn hình IdP, nhưng không thấy callback LogoutResponse về SP. SP có phải khôi phục session cũ?

**Đáp án:** **Không.** SP local logout đã diễn ra; kết quả federation chưa xác nhận. Không tạo lại session chỉ vì thiếu callback.

**Bài 4.** Một SLO LogoutResponse có `InResponseTo="_a"` nhưng LogoutRequest trong repository có ID `_b`. Có nên coi status Success là hợp lệ?

**Đáp án:** không. Correlation sai; phải xử lý theo validator và không gán thành công cho transaction chưa đúng.

**Bài 5.** IdP-initiated LogoutRequest ký sai nhưng có NameID trùng một user đang đăng nhập. Có được xóa session không?

**Đáp án:** không. NameID không thay signature/issuer/trust; request giả mạo phải bị từ chối.

**Bài 6.** User local logout thành công, mở lại app được SSO ngay. Có chắc logout thất bại không?

**Đáp án:** không. IdP session còn nên có thể tạo SP session mới. Phải xác định đó là local logout hay SLO, rồi kiểm chứng IdP flow.

**Bài 7.** LogoutRequest có SessionIndex. Có thể coi đó là `JSESSIONID` để tìm session không?

**Đáp án:** không. SessionIndex là định danh SAML do IdP cung cấp; servlet session ID là cơ chế riêng của SP.

**Bài 8.** Sau một SLO thành công, token API/JWT khác vẫn hoạt động. Đây có phải lỗi SAML ngay lập tức?

**Đáp án:** không nhất thiết. SAML SLO không tự revoke tokens của tất cả cơ chế khác. Cần thiết kế token revocation/session governance riêng theo requirement.

**Bài 9.** IdP metadata chỉ có SingleSignOnService mà không có SingleLogoutService. SP đã hỗ trợ logout SAML chưa?

**Đáp án:** chưa có bằng chứng SLO; phải yêu cầu IdP công bố/cấu hình SLO và SP đăng ký SLO URL, ký, verification đúng. Login SSO không chứng minh logout SSO.

**Bài 10.** Tại sao browser trả HTTP 200 trên một trang IdP không chứng minh LogoutResponse status Success?

**Đáp án:** HTTP status và SAML StatusCode là hai lớp khác nhau. Phải thấy LogoutResponse thực sự được phát và SP/IdP kiểm chứng theo flow.

**Bài 11.** Trong Spring Security, tại sao một GET tới `/logout` thường không đủ kích hoạt SLO?

**Đáp án:** Theo cấu hình CSRF và Spring logout mặc định, logout thay đổi state nên được kích hoạt bằng **POST kèm CSRF hợp lệ**, không phải GET vô điều kiện.

**Bài 12.** IdP-initiated LogoutRequest hợp lệ đã được SP xử lý, nhưng trang browser cuối cùng do IdP hiển thị. Đây có phải lỗi SP success handler?

**Đáp án:** không. Sau khi SP phát LogoutResponse, **IdP kiểm soát phần tiếp của browser** trong luồng này.

**Bài 13.** Một SP cũ không thể nhận SLO, IdP báo PartialLogout. SP hiện tại đã hủy local session. Có được thông báo “logout hoàn tất trên mọi ứng dụng” không?

**Đáp án:** không. Đây là **partial federation logout**, cần thông báo đúng phạm vi và hướng hỗ trợ cho ứng dụng chưa logout.

**Bài 14.** Nếu triển khai hai endpoint local và SAML logout, URL nào là giao thức inbound từ IdP?

**Đáp án:** thường vẫn `/logout/saml2/slo`; `/logout` hoặc `/saml2/logout` là **nút khởi tạo logout tại SP**, tùy DSL.

**Bài 15.** SAML logout request có chữ ký hợp lệ nhưng request chỉ rõ NameID/SessionIndex không thuộc principal của phiên hiện tại. Có thể hủy session vì IdP là đối tác tin cậy không?

**Đáp án:** không được hủy nhầm. Phải áp dụng quy tắc khớp principal/session của validator và flow hợp đồng; trust key là điều kiện cần, **không phải mọi điều kiện đủ**.

## 29. Checklist hoàn thiện SAML Single Logout

- [ ] Phân biệt rõ yêu cầu nghiệp vụ **local logout**, **SP-initiated SLO**, **IdP-initiated SLO** và “global logout” nhiều thiết bị.
- [ ] IdP metadata được xác minh có `SingleLogoutService` với binding/URL phù hợp.
- [ ] SP registration công bố public `singlelogout.url` đúng và IdP đã nhập metadata SP.
- [ ] Cấu hình SP signing private key và X.509 cert đúng; IdP có public cert SP để xác minh.
- [ ] SP có IdP public signing certificates đáng tin để xác minh inbound request/response.
- [ ] Bật `.saml2Logout(... )` trên đúng Servlet SecurityFilterChain.
- [ ] Nếu dùng SLO mặc định, user thực hiện `POST /logout` hợp lệ; không tắt CSRF toàn ứng dụng.
- [ ] Nếu cần local logout riêng, cấu hình hai trigger endpoints có ý nghĩa và UX không gây nhầm.
- [ ] Phân biệt payload `SAMLRequest` / `SAMLResponse` tại `/logout/saml2/slo`.
- [ ] Inbound LogoutRequest được kiểm tra signature/issuer/destination/NameID/session/time/replay trước local cleanup.
- [ ] LogoutResponse callback có kiểm tra signature/issuer/status/InResponseTo/RelayState.
- [ ] Có kế hoạch cookie SameSite, session state và multi-node request repository.
- [ ] Đã kiểm thử SP-initiated/IdP-initiated, invalid signature, missing callback, partial logout và user SSO lại.
- [ ] Metrics/audit phân biệt local completed với federation confirmed/partial/unknown.
- [ ] Không khẳng định mọi phiên/thiết bị/token đã bị hủy nếu không có khả năng revocation tương ứng.
- [ ] Log/HAR không chứa raw LogoutRequest/LogoutResponse, NameID thật, RelayState, cookies hay private keys.
- [ ] Có kịch bản rollback khi IdP metadata, certificate hoặc SLO URL thay đổi.

## 30. Ghi nhớ

**SP-initiated:** user yêu cầu logout ở SP → Spring xóa session cục bộ → SP gửi **LogoutRequest** → IdP xử lý, có thể gửi **LogoutResponse** về SP.  
**IdP-initiated:** IdP gửi **LogoutRequest** → SP **xác minh trước** → SP xóa session phù hợp → SP gửi **LogoutResponse** về IdP.

Trong cả hai hướng, **bên phát LogoutRequest là bên khởi tạo**, và **SAML Single Logout là một giao thức phối hợp**, không phải lời hứa tự động về mọi browser, ứng dụng, thiết bị và access token. Chính sách trust, metadata, key, callback, browser session và phạm vi federated logout phải được kiểm chứng độc lập.

### Tài liệu chính thức

1. Spring Security — *Performing Single Logout* (Spring Security 7.x, hai hướng SLO, endpoint, filter, validation, repository): https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
2. Spring Security 6.5 — *Performing Single Logout*: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
3. Spring Security — *Logging Out* (Servlet logout/CSRF): https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
4. Spring Security — *SAML 2.0 Login Overview* (khác biệt login vs logout): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
5. Spring Security API — *Saml2LogoutRequestRepository* (lưu request/correlation): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html
6. OASIS — *SAML V2.0 Core*, phần LogoutRequest/LogoutResponse, Status, SessionIndex: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
7. OASIS — *SAML V2.0 Profiles*, Single Logout Profile: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
8. OASIS — *SAML V2.0 Bindings* (HTTP Redirect/POST và RelayState): https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
9. OASIS — *SAML V2.0 Metadata*, SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
