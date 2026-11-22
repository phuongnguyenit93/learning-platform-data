# Đối chiếu callback và thông điệp đăng xuất với đúng đăng ký ban đầu

> **Module:** Spring Security – federation · **Chủ đề cha:** Nhiều IdP và tenant. Bài học phân tích cách một Service Provider (SP) sử dụng Spring Security SAML2 **ràng buộc LogoutResponse/LogoutRequest với đúng RelyingPartyRegistration, IdP, tenant và phiên đã khởi tạo**. Trọng tâm là tránh nhầm registration khi SLO callback đến một URL dùng chung, sau khi phiên HTTP của SP đã bị hủy, hoặc khi nhiều tenant có cùng một IdP issuer.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích tại sao `RelyingPartyRegistration` biểu diễn **một quan hệ SP–IdP cụ thể**, còn `registrationId` chỉ là khóa cấu hình của Spring, không tự là bằng chứng đáng tin được gửi từ IdP.
2. Phân biệt **SP/RP-initiated SLO callback** với **IdP/AP-initiated LogoutRequest**; hiểu vì sao chỉ RP-initiated mới có LogoutRequest gốc của SP để dùng `InResponseTo`.
3. Mô tả đường đi của `LogoutRequest ID`, `RelayState`, `Saml2LogoutRequestRepository`, `Issuer`, `Destination`, chữ ký và metadata khi callback quay về SP.
4. Xây ràng buộc **registration ban đầu → trusted IdP → SP entity ID → tenant → logout attempt**, không cho query/path/body tự ý đổi context.
5. Xử lý hai tenant dùng cùng IdP issuer, hai IdP dùng cùng NameID/SessionIndex, callback tới node khác, session đã bị invalidated và response đến muộn.
6. Tách **định tuyến tạm** theo endpoint/issuer khỏi **xác minh cuối cùng** bằng trusted registration, chữ ký, các trường giao thức và correlation.
7. Dùng `saml2Logout`, `Saml2LogoutRequestRepository` và các validator của Spring Security mà **không thay thế kiểm tra bảo mật mặc định bằng parser XML tự viết**.
8. Chạy ví dụ Java 17 độc lập về phép đối chiếu callback với original attempt, có stdout kiểm chứng, và xem project Spring Boot 3.3/Spring Security 6.3 có hai registration.
9. Tạo ma trận test multi-IdP/multi-tenant bao gồm cross-tenant callback, request mix-up, replay, key rollover, callback URL dùng chung và AP-initiated SLO.

**Phạm vi:** SAML2 Single Logout (SLO) trong ứng dụng Servlet SP. Bài không thay thế tài liệu vận hành IdP. Những API Spring cụ thể cần đối chiếu phiên bản; phần ví dụ cấu hình bên dưới lấy **Java 17, Spring Boot 3.3.x, Spring Security 6.3.x** làm baseline.

## 2. Bối cảnh: một callback dùng chung, nhiều quan hệ tin cậy

Hệ thống Orders Portal hỗ trợ:

| registrationId nội bộ | Tenant nghiệp vụ | SP entity ID | IdP entity ID |
| --- | --- | --- | --- |
| `partner-a` | `tenant-A` | `https://orders.example/saml2/sp/partner-a` | `https://idp-a.example/saml` |
| `partner-b` | `tenant-B` | `https://orders.example/saml2/sp/partner-b` | `https://idp-b.example/saml` |
| `shared-a` | `tenant-C` | `https://orders.example/saml2/sp/shared-a` | `https://idp-shared.example/saml` |
| `shared-b` | `tenant-D` | `https://orders.example/saml2/sp/shared-b` | `https://idp-shared.example/saml` |

Hai registration `shared-a` và `shared-b` được IdP cùng một hệ thống phục vụ, nên **IdP issuer giống nhau** nhưng SP entity ID và tenant khác nhau.

Để IdP trả thông điệp SLO, ứng dụng có thể công bố một callback chung:

~~~text
https://orders.example/logout/saml2/slo
~~~

**Bài toán:** nếu browser POST vào callback này một LogoutResponse có `Issuer=https://idp-shared.example/saml`, SP chọn `shared-a` hay `shared-b`? **Chỉ dùng Issuer sẽ không đủ** vì Issuer giống nhau. Nếu tin `?registrationId=shared-b` từ browser, kẻ tấn công có thể tìm cách chuyển cách giải thích thông điệp sang tenant khác.

Với **RP-initiated SLO**, SP **đã biết registration tại thời điểm phát LogoutRequest** và có thể lưu dữ liệu request gốc. Callback phải được đối chiếu với **context gốc đã phát**, không được chọn lại tenant tự do chỉ bằng các chuỗi trên HTTP response.

Với **AP-initiated SLO**, không có LogoutRequest gốc của SP. Khi đó cần một cách giải quyết registration **không nhập nhằng** dựa trên endpoint/tenant binding và những bằng chứng được IdP ký, sau đó xác minh message theo **đúng** trust config. Nếu một Issuer tương ứng nhiều registration, phải bổ sung cách định tuyến đã được duyệt hoặc từ chối, **không chọn ngẫu nhiên cái đầu tiên**.

## 3. Những khái niệm phải tách biệt

| Khái niệm | Ai định nghĩa? | Dùng vào việc gì? | Không nên dùng như |
| --- | --- | --- | --- |
| `registrationId` | Ứng dụng Spring Security. | Khóa truy cập `RelyingPartyRegistrationRepository`. | Bằng chứng chứng minh IdP/tenant vì nó xuất hiện trong path/query. |
| SP `entityId` | Quan hệ liên kết SP–IdP đã công bố/duyệt. | Danh tính SP trong giao thức; tách hai tenant dùng chung IdP. | URL nhận callback (`Destination`) nếu hai giá trị khác nhau. |
| IdP `entityId` / `Issuer` | IdP công bố và SP tin theo metadata. | Xác định bên ký/phát LogoutRequest/LogoutResponse. | Khóa tenant duy nhất nếu một IdP phục vụ nhiều registration. |
| SP SLO callback URL | SP công bố trong metadata/cấu hình. | Đích nhận message SLO. | Thay thế việc xác minh InResponseTo/issuer/signature. |
| `LogoutRequest.ID` | Bên phát LogoutRequest. | Ghép response với request gốc. | ID của local user hoặc tenant. |
| `LogoutResponse.InResponseTo` | IdP gửi trong response cho RP-initiated. | Phải trỏ đúng ID request gốc. | Giá trị tự khai để tạo request gốc mới. |
| `RelayState` | State qua SAML binding. | Giúp framework tra lại request/correlation khi callback. | Bằng chứng tin cậy nếu không đối chiếu request đã lưu. |
| `NameID` / `SessionIndex` | Assertion đã xác thực/IdP đã phát theo profile. | Chọn session cần logout khi đúng trust scope. | Khóa user toàn cục giữa các IdP/tenant. |
| Chứng thư verification | Trusted registration/metadata. | Xác minh chữ ký của đúng IdP. | Chứng thư tùy ý lấy từ `ds:KeyInfo` do browser chuyển tới. |
| Tenant nghiệp vụ | Ứng dụng SP sau khi nhận diện đáng tin. | Giới hạn session, quyền và resource. | Query parameter do browser tự chọn ở callback. |

**Bốn ranh giới:** định tuyến → xác minh thông điệp SAML → xác định phiên chịu ảnh hưởng → thực hiện local logout/authorization. Không được vì tìm đúng URL callback mà bỏ qua ba bước sau.

## 4. Sơ đồ RP-initiated SLO: quan hệ gốc không được thay giữa chừng

~~~text
Browser              SP Orders / Registration partner-a         IdP A
   |                            |                                 |
   | POST /saml2/logout         |                                 |
   |--------------------------->| Đọc authenticated principal     |
   |                            | -> partner-a                    |
   |                            | Phát LogoutRequest ID=_reqA    |
   |                            | RelayState=opaqueA             |
   |                            | Lưu request gốc + context A     |
   |                            | Hủy local session theo flow    |
   |<---- browser chuyển IdP ---|                                 |
   |-------------------------------- LogoutRequest -------------->|
   |                            |                                 | Logout
   |<-------------------------------- LogoutResponse --------------|
   | POST /logout/saml2/slo     |                                 |
   |--------------------------->| Tra original request opaqueA    |
   |                            | Khôi phục đúng registration A   |
   |                            | Verify issuer/key/destination   |
   |                            | Check InResponseTo=_reqA       |
   |                            | Chống replay/expiry             |
   |<---- kết quả hợp lệ -------|                                 |
~~~

Đối với callback RP-initiated, **principal có thể đã bị xóa khỏi SecurityContext** vì logout local xảy ra trước khi gửi SLO. Vì vậy không thể luôn dựa vào `SecurityContextHolder.getContext().getAuthentication()` trong response callback để biết ban đầu dùng registration nào. Framework cần một **LogoutRequest đã lưu**, và ứng dụng multi-tenant phải bảo toàn mapping ấy nếu custom repository/resolver.

### 4.1. LogoutRequest do SP phát

Ví dụ mảnh XML outbound:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-partner-a-01"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://idp-a.example/slo">
    <saml:Issuer>https://orders.example/saml2/sp/partner-a</saml:Issuer>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        pa-4819
    </saml:NameID>
    <samlp:SessionIndex>idp-session-731</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Các giá trị là ví dụ cấu trúc. Trong thực tế, SP ký LogoutRequest theo binding/chính sách và dùng NameID, SessionIndex phù hợp với Assertion/Authentication gốc. **Không tạo SessionIndex từ HTTP session ID của SP.** XML chưa ký trong tài liệu không thể dùng làm LogoutRequest thật.

Request được gửi qua browser tới **IdP A SLO endpoint** từ trusted metadata; không có lý do hợp lệ để callback của nó được diễn giải như registration `partner-b` chỉ vì browser thêm tham số.

### 4.2. LogoutResponse IdP trả

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_res-partner-a-01"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:09Z"
    InResponseTo="_req-partner-a-01"
    Destination="https://orders.example/logout/saml2/slo">
    <saml:Issuer>https://idp-a.example/saml</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
</samlp:LogoutResponse>
~~~

Callback có **Issuer = IdP A** và **Destination = SP callback URL**; không tự xuất hiện một thuộc tính `tenantId` chuẩn trong LogoutResponse để SP tin. Việc chọn registration dựa vào **original LogoutRequest + trusted registration configuration**, sau đó xác minh response tương ứng.

Với HTTP-Redirect binding, chữ ký có thể nằm ở query parameters theo profile thay vì là `ds:Signature` bên trong XML. Bộ validator phải xử lý đúng binding; không tự kết luận “XML không có ds:Signature” nên response chắc chắn không ký, cũng không tự coi `SigAlg`/`Signature` do client đưa lên là trusted.

### 4.3. Đối chiếu theo thứ tự

1. Tìm `Saml2LogoutRequest` gốc qua repository/state mà framework đã phát và lưu, không tạo mới.
2. Lấy `registrationId` từ original request và truy `RelyingPartyRegistration` **từ trusted repository**.
3. Kiểm tra original request vẫn còn trong thời hạn chấp nhận, chưa được dùng và thuộc đúng tenant/trust context.
4. Xác minh chữ ký LogoutResponse **bằng verification credentials của IdP trong registration gốc**.
5. Kiểm tra `Issuer` của response đúng IdP entity ID trong registration.
6. Kiểm tra `Destination` đúng endpoint SP nhận SLO được công bố cho registration trong environment hiện tại.
7. Kiểm tra `InResponseTo` đúng LogoutRequest.ID mà SP đã phát; đối chiếu `RelayState` bằng cơ chế repository đã cấu hình.
8. Kiểm tra Status theo profile; `Success`, `PartialLogout` và lỗi phải được diễn giải có chủ đích.
9. Đánh dấu attempt consumed một cách nguyên tử để chặn replay/nhận lặp, hoàn tất audit và UX.
10. Local session đã kết thúc **không được phục hồi** khi callback bị từ chối hoặc tới muộn.

**Quan trọng:** Đây là **logic kiểm soát tổng thể**, không phải lời hứa rằng mọi callback Spring Security mặc định đều thực hiện tất cả custom tenant checks và audit. Lớp SAML validation sẵn có phải được giữ nguyên; kiểm tra bổ sung về tenant/config version/correlation cần được triển khai và kiểm thử khi sản phẩm yêu cầu.

## 5. Vì sao không chỉ dựa vào Issuer hoặc registrationId trong URL?

### 5.1. Issuer có thể không định danh duy nhất tenant

~~~text
tenant-C  -> registration shared-a -> IdP issuer = shared.example/idp
tenant-D  -> registration shared-b -> IdP issuer = shared.example/idp

LogoutResponse.Issuer = shared.example/idp
~~~

Issuer đúng **IdP**, nhưng **chưa đủ** chỉ ra SP entity ID/tenant nào. Với RP-initiated callback, original request sẽ giúp xác định đúng registration. Nếu original request không còn hoặc không tìm được, không tự chọn tenant-C vì nó đứng trước trong danh sách.

### 5.2. registrationId là hint, không phải trust proof

Các URL dạng:

~~~text
/logout/saml2/slo
/logout/saml2/slo/partner-a
/logout/saml2/slo?registrationId=partner-b
~~~

Cần phân biệt:

- `/logout/saml2/slo` là callback chung trong tài liệu Spring Security SLO.
- Biến thể có `{registrationId}` ở endpoint chỉ sử dụng **khi đã cấu hình/kiểm thử resolver và metadata phù hợp**; đừng tự giả định tất cả đường dẫn biến thể đều hoạt động.
- Query parameter `registrationId=partner-b` **không phải bằng chứng** response thuộc B. Ứng dụng có thể dùng route hint để tìm ứng viên, nhưng **bắt buộc** kiểm tra signature, IdP issuer, request correlation và tenant context.
- Không có quy tắc “cứ path có partner-a là response được tin bằng cert của partner-a mà không cần `InResponseTo`”.

Nếu trước đó original LogoutRequest thuộc `partner-a`, nhưng callback mang hint `partner-b`, fail closed thay vì “chuyển” request sang B rồi dùng khóa B để xem có qua verification không.

### 5.3. Cùng NameID và SessionIndex chưa đủ

~~~text
IdP A: NameID=user-42, SessionIndex=session-2
IdP B: NameID=user-42, SessionIndex=session-2
~~~

Hai chuỗi giống nhau không có nghĩa cùng người hay cùng session. Dữ liệu session nằm trong **nguồn IdP + registration/tenant + SP scope**. Đặc biệt, đừng dùng `SessionIndex` làm khóa duy nhất toàn cục trong bảng logout hoặc dùng nó để xóa session của một tenant khác.

### 5.4. Nếu một IdP chung dùng cùng chứng thư cho hai registration

Xác minh chữ ký bằng cùng public key vẫn không giải quyết được ambiguity: certificate xác minh được **nguồn IdP**, không tự chứng minh callback nhắm `shared-a` hay `shared-b`. Cần giữ **request gốc, SP entity ID và tenant binding** ở control plane. Nếu không có original attempt cho RP-initiated flow, không được nhận callback chỉ vì “signed by shared IdP”.

## 6. AP-initiated LogoutRequest: không có original SP LogoutRequest

Trong **IdP/AP-initiated SLO**, IdP chủ động gửi `LogoutRequest` tới SP:

~~~text
IdP B ---- signed SAMLRequest ----> /logout/saml2/slo
                                   |
                                   +-- Resolve trusted registration candidate
                                   +-- Verify signature with that IdP's keys
                                   +-- Validate Issuer/Destination/conditions
                                   +-- Identify NameID/SessionIndex in scope
                                   +-- Invalidate only matching SP session
                                   +-- Send signed LogoutResponse to IdP B
~~~

Không có RP-initiated LogoutRequest do SP phát trước đó nên **không đòi LogoutResponse.InResponseTo trỏ một SP request chưa từng tồn tại**. Thay vào đó, cần ràng buộc **IdP message sender → đúng registration → đúng session target**.

### 6.1. Trường cần xác minh trên AP-initiated request

| Trường/nguồn | Cách kiểm tra | Rủi ro nếu bỏ |
| --- | --- | --- |
| `SAMLRequest`/binding | Parse theo SAML2 binding và bộ xử lý an toàn. | Xử lý nhầm XML không đúng profile. |
| XML/query signature | Xác minh bằng key tin trong đúng IdP registration. | Attacker giả LogoutRequest xóa session. |
| `Issuer` | Phù hợp IdP entity ID đáng tin. | Logout chéo IdP. |
| `Destination` | Nhắm đúng SLO endpoint SP đã công bố/được phép. | Dùng request cho SP/tenant khác. |
| `NameID` | So sánh với subject từ SAML authentication đã xác minh trong **issuer scope**. | Một chuỗi giống nhau làm logout nhầm user. |
| `SessionIndex` | Phù hợp session IdP phát và SP đã lưu, nếu profile/IdP có. | Xóa mọi session chỉ vì tên giống. |
| Time/ID/replay | Có ID, thời hạn hợp lệ khi áp dụng, chống xử lý lại. | Request cũ/lặp khiến logout ngoài ý muốn. |
| Registration/tenant context | Không nhập nhằng, được xác minh với trust config và session mapping. | Xóa phiên sai tenant. |

Nếu **IdP chung** phục vụ nhiều tenant dùng cùng `Issuer` và callback URL chung, cần có **tenant-specific route/config** được ký kết hoặc một resolver đối chiếu session/profile một cách an toàn. Nếu không đủ dữ kiện để phân biệt, **từ chối** AP-initiated request thay vì quét mọi session/tenant rồi logout tất cả các kết quả trùng.

### 6.2. Đường dẫn dành riêng theo tenant có ích nhưng chưa đủ

Ví dụ một deployment có URL công bố:

~~~text
https://orders.example/tenant-c/logout/saml2/slo
https://orders.example/tenant-d/logout/saml2/slo
~~~

Đường dẫn có thể giúp **định tuyến tới ứng viên**. Tuy nhiên client có thể gọi bất kỳ URL; nó chỉ an toàn khi resolver đã được cấu hình, metadata/IdP biết đúng endpoint, và message sau đó được kiểm chứng theo IdP/SP entity ID/NameID/SessionIndex đúng tenant. Không tạo một MVC controller nhận `SAMLRequest` rồi tự xóa session bằng `tenantId` trong path mà không đi qua Spring SAML validator.

### 6.3. Bất đối xứng RP vs AP cần nhớ

| Điểm | RP-initiated callback | AP-initiated request |
| --- | --- | --- |
| Ai phát message gốc? | SP phát LogoutRequest. | IdP phát LogoutRequest. |
| Original SP request đã lưu? | **Có**; phải đối chiếu. | **Không** có cho lần khởi tạo đó. |
| `InResponseTo` | Dùng trong LogoutResponse để tham chiếu request của SP. | LogoutRequest đến SP không mang ý nghĩa đó. |
| Cách tìm registration | Theo original request + trusted repository. | Resolver lấy ứng viên theo trusted context, sau đó verify request. |
| Chọn session | RP đã biết user/session ban đầu. | Xác định phiên cần logout bằng validated IdP identity + SessionIndex/profile. |
| Response của SP | Nhận và xử lý IdP LogoutResponse. | SP tạo LogoutResponse để trả IdP. |

## 7. `RelayState`, `InResponseTo` và request repository

### 7.1. Vai trò khác nhau

- `LogoutRequest.ID`: ID mà SP tự tạo cho RP-initiated SLO.
- `LogoutResponse.InResponseTo`: trỏ chính xác ID đó.
- `RelayState`: state chuyển qua browser theo binding, thường dùng làm khóa truy hồi/correlation tới request gốc.
- `Saml2LogoutRequestRepository`: interface Spring Security lưu request outbound để callback có thể được đối chiếu.
- `RelyingPartyRegistrationRepository`: nơi cung cấp trust/config của IdP/SP, **không** phải nơi lưu mọi LogoutRequest.

Một giá trị `RelayState` đoán được, bị sửa hoặc không tìm thấy **không được dùng để mở một request mới**. Kiểm tra `InResponseTo` và chữ ký phải đi đôi với việc truy đúng request đã lưu.

### 7.2. Spring Security lưu request để làm gì?

Theo Spring Security reference, `LogoutRequest` outbound được lưu để kiểm tra `RelayState` và `InResponseTo` ở `LogoutResponse`. Tài liệu nêu cách mặc định dựa vào **HTTP session**; có thể thay `Saml2LogoutRequestRepository` bằng implementation phù hợp khác qua DSL.

~~~java
// Mảnh cấu hình trong SecurityFilterChain, KHÔNG phải class độc lập.
http.saml2Logout(saml -> saml
    .logoutRequest(req -> req
        .logoutRequestRepository(myCustomLogoutRequestRepository)
    )
);
~~~

Đoạn này chỉ minh họa **điểm mở rộng** khi thực sự có implementation; không có bean nào tên `myCustomLogoutRequestRepository` tự xuất hiện. Muốn viết repository bền vững cần tra interface đúng version, kiểm tra save/load/remove semantics, serialization, TTL, race conditions và một lần sử dụng.

**Cảnh báo:** trong RP-initiated SLO, local session thường bị hủy trước khi browser tới IdP. Không tự thiết kế một listener xóa sạch request correlation khi invalidating session. Nếu tùy biến repository, phải bảo đảm framework vẫn truy được request sau cleanup theo lifecycle thực tế.

### 7.3. Hai node và load balancer

~~~text
Browser -> Node 1: LogoutRequest _req1, RelayState rs1
             |
             | persistent/replicated request state
             v
          Shared session/store
             ^
             |
Browser -> Node 2: callback rs1, InResponseTo _req1
~~~

Nếu Node 2 không tìm được original request, không “fallback” sang registration chỉ dựa vào IdP Issuer hoặc trial các verification keys từ mọi IdP. Đó là một **lỗi correlation**, cần fail closed và kiểm tra session affinity, Spring Session, shared store hoặc custom `Saml2LogoutRequestRepository` có TTL và atomic consumption.

**Những quy tắc store quan trọng:**

1. Tạo request ID và state khó đoán, phù hợp binding và không dùng chung giữa tenants.
2. Lưu một record có `registrationId`, tenant/trust scope, LogoutRequest ID, RelayState và deadline.
3. Khi callback đến, đối chiếu tất cả ràng buộc với request gốc.
4. Mark consumed/delete record **atomic**, không cho hai node cùng chấp nhận.
5. Dùng TTL có giới hạn; response sau hạn phải bị xử lý theo late-response policy, không kéo dài vô hạn.
6. Đừng dùng request-store record như nơi lưu toàn bộ raw XML, NameID và PII nếu không thực sự cần.
7. Kể cả metadata/registration refresh, cần chính sách pin **phiên bản trust config dùng khi phát request** và xử lý key rollover một cách minh bạch.

### 7.4. Khi registration cấu hình đã thay đổi giữa request và callback

Ví dụ:

~~~text
T0: SP phát LogoutRequest cho partner-a với IdP key A.
T1: IdP rotate key: metadata tin cậy đã thêm B.
T2: Browser mang LogoutResponse ký bằng B về SP.
~~~

Cần chính sách rollover/trust rõ: ký B có thể được chấp nhận nếu B nằm trong trusted set hiện tại và đúng IdP/registration, nhưng không được vì rotation mà **chọn sang registration B/tenant B**. Ngược lại, nếu A bị compromise và đã bị revoke, tuyệt đối không khôi phục A chỉ để chấp nhận callback đang chờ.

Có thể lưu `config_version`/trust version trong attempt để audit. Cách chấp nhận key trước/sau rotation phải tuân security policy, không hardcode “mọi key cũ đều OK” hoặc “mọi request được cấp lúc A thì phải ký bằng A”.

## 8. Quy trình xác minh một callback RP-initiated

### Bước 1 — Phân loại message, chưa tin nội dung

`SAMLResponse` trên endpoint logout có thể chứa **LogoutResponse**, khác với `SAMLResponse` dùng cho đăng nhập SAML Assertion Consumer Service. Không dùng một handler chung tự giải mã rồi lấy `Issuer`/`NameID` không kiểm chứng để tạo session.

Các parser/binding handler an toàn của Spring/OpenSAML phải được sử dụng, có giới hạn payload và chống XXE/XML Signature Wrapping theo cấu hình bảo mật.

### Bước 2 — Khôi phục attempt gốc

Dùng `RelayState`/request repository được framework cấu hình để lấy original LogoutRequest. Nếu không tồn tại: **REJECT_NO_ORIGINAL**. Đối với RP-initiated callback, không chấp nhận một response unsolicited chỉ vì nó mang chữ ký hợp lệ.

### Bước 3 — Cố định registration từ attempt gốc

Truy `RelyingPartyRegistrationRepository.findByRegistrationId(original.registrationId)`; kiểm tra mapping ban đầu gắn với đúng tenant/SP entity ID và chưa quá hạn. Nếu URL chứa route hint khác registration gốc, **REJECT_CROSS_REGISTRATION**; không cho browser quyết định lại.

### Bước 4 — Chữ ký và nguồn

Xác minh chữ ký theo đúng SAML binding bằng các verification credentials của **IdP thuộc registration gốc**, kiểm tra Issuer và role/metadata đã tin. Không chấp nhận cert tùy ý bên trong `ds:KeyInfo` hoặc “thử mọi certificate cho đến khi có cái verify được” để suy ra tenant.

### Bước 5 — Đích và ID

Kiểm tra `Destination` đúng SLO callback URL của SP cho registration đó, với scheme/host/path public đã được công bố. Kiểm tra `InResponseTo` đúng ID outbound original request, không chỉ có chuỗi tương tự. `RelayState` phải khớp state do SP phát.

**Không tự so sánh Destination với SP entity ID**: cả hai có thể là URL nhưng có ngữ nghĩa khác nhau. `Destination` là **endpoint URL**, còn entity ID là danh tính SP.

### Bước 6 — Thời hạn, status và replay

Kiểm tra IssueInstant/time/NotOnOrAfter khi áp dụng, deadline nội bộ, request state chưa consumed. Diễn giải Status theo profile. Nếu IdP trả nested `PartialLogout` dưới `Success`, UX vẫn phải báo còn participant chưa xác nhận; nếu chưa có response, không tự suy global success.

### Bước 7 — Finalize có tính nguyên tử

Consume original attempt một lần, audit bản ghi kết quả theo registration và tenant, thông báo mức chắc chắn. **Không tạo lại session đã logout** khi callback lỗi hoặc đến trễ.

## 9. Kịch bản nhầm registration cần phòng vệ

| Tình huống | Nếu làm sai | Kiểm soát đúng |
| --- | --- | --- |
| Callback của A mang `?registrationId=B`. | Dùng trust/tenant B, có thể ghi success sai. | Đối chiếu path hint với original A, từ chối mismatch. |
| Hai tenant có cùng IdP Issuer. | Chọn tenant đầu tiên từ issuer. | RP callback dựa original request; AP request cần tenant route/scope không nhập nhằng. |
| Hai IdP phát cùng NameID và SessionIndex. | Xóa session sai người/tenant. | Dùng issuer/registration/SP scope + validated session info. |
| RelayState đoán được hoặc không được đối chiếu. | Request mix-up hoặc callback gắn nhầm. | RelayState opaque, lookup request, check InResponseTo. |
| LogoutResponse có chữ ký hợp lệ bởi IdP khác. | Chọn IdP mới theo cert verify được. | Cert/trust scope cố định từ original registration. |
| LogoutResponse sai Destination. | Chấp nhận response dành cho SP khác. | So khớp public SP callback URL. |
| Response thiếu original request. | Chấp nhận unsolicited SLO success. | Reject no original cho RP-initiated callback. |
| Callback tới node không có HTTP session. | Resolver chọn registration ngẫu nhiên. | Shared correlation store/session đúng thiết kế; fail closed. |
| IdP gửi request AP-initiated tới callback chung. | Resolve nhầm tenant từ Issuer. | Verified resolver theo endpoint + session + IdP contract. |
| Registration đổi `registrationId` khi có pending attempt. | Không tìm thấy request/khôi phục sai. | Quy trình migration/alias an toàn, giữ context đến khi TTL hết. |
| Key rollover xảy ra khi logout đang chờ. | Dùng key của tenant khác để “sửa” lỗi. | Trust version/metadata pinning và kiểm thử rotation. |
| Response đến muộn sau khi attempt consumed. | Replay làm đổi audit/đăng nhập lại. | Reject replay/expired, local logout không bị đảo ngược. |

## 10. Java 17: mô hình đối chiếu callback với original request

Ví dụ độc lập sau **không parse XML SAML và không verify chữ ký thật**. Một bản ghi `VerifiedCallback` trong code chỉ là **dữ liệu giả lập đầu ra của một SAML validator đáng tin**; cờ boolean trong demo **không được dùng thay chữ ký thật trong production**.

Mục tiêu: chứng minh rằng **đúng Issuer vẫn không đủ** khi hai registration cùng một IdP; original request và đúng registration/trust scope phải khớp.

### 10.1. Tệp `SloCallbackBindingDemo.java`

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class SloCallbackBindingDemo {

    record Registration(
        String registrationId,
        String tenantId,
        String idpEntityId,
        String spEntityId,
        String sloCallback,
        String verificationKeyId) {
    }

    record Attempt(
        String logoutRequestId,
        String relayState,
        String registrationId,
        String tenantId,
        String spEntityId,
        long expiresAt) {
    }

    // CHỈ dữ liệu giả lập sau khi provider đã validate SAML.
    record VerifiedCallback(
        String inResponseTo,
        String relayState,
        String issuer,
        String destination,
        String validatedRegistrationId,
        String validatedKeyId,
        boolean signatureTrusted) {
    }

    enum Decision {
        ACCEPTED,
        NO_ORIGINAL_REQUEST,
        UNTRUSTED_SIGNATURE,
        EXPIRED,
        REQUEST_ID_MISMATCH,
        REGISTRATION_MISMATCH,
        TENANT_CONTEXT_MISMATCH,
        ISSUER_MISMATCH,
        DESTINATION_MISMATCH,
        WRONG_KEY_SCOPE,
        REPLAY
    }

    static Decision check(
            VerifiedCallback callback,
            Map<String, Attempt> originalByRelay,
            Map<String, Registration> trustedRegistrations,
            Set<String> alreadyConsumed,
            long now) {

        Attempt original = originalByRelay.get(callback.relayState());
        if (original == null) {
            return Decision.NO_ORIGINAL_REQUEST;
        }

        Registration registration =
            trustedRegistrations.get(original.registrationId());

        if (registration == null || !callback.signatureTrusted()) {
            return Decision.UNTRUSTED_SIGNATURE;
        }

        if (now >= original.expiresAt()) {
            return Decision.EXPIRED;
        }

        if (!original.logoutRequestId().equals(callback.inResponseTo())) {
            return Decision.REQUEST_ID_MISMATCH;
        }

        if (!registration.registrationId().equals(
                callback.validatedRegistrationId())) {
            return Decision.REGISTRATION_MISMATCH;
        }

        if (!registration.tenantId().equals(original.tenantId())
                || !registration.spEntityId().equals(original.spEntityId())) {
            return Decision.TENANT_CONTEXT_MISMATCH;
        }

        if (!registration.idpEntityId().equals(callback.issuer())) {
            return Decision.ISSUER_MISMATCH;
        }

        if (!registration.sloCallback().equals(callback.destination())) {
            return Decision.DESTINATION_MISMATCH;
        }

        if (!registration.verificationKeyId().equals(
                callback.validatedKeyId())) {
            return Decision.WRONG_KEY_SCOPE;
        }

        if (!alreadyConsumed.add(original.logoutRequestId())) {
            return Decision.REPLAY;
        }

        return Decision.ACCEPTED;
    }

    public static void main(String[] args) {
        long now = Instant.parse("2030-05-01T10:00:00Z")
            .getEpochSecond();

        String issuer = "https://idp-shared.example/saml";
        String callbackUrl = "https://orders.example/logout/saml2/slo";

        Registration a = new Registration(
            "shared-a", "tenant-C", issuer,
            "https://orders.example/saml2/sp/shared-a",
            callbackUrl, "shared-idp-key");

        Registration b = new Registration(
            "shared-b", "tenant-D", issuer,
            "https://orders.example/saml2/sp/shared-b",
            callbackUrl, "shared-idp-key");

        Map<String, Registration> trusted = Map.of(
            a.registrationId(), a,
            b.registrationId(), b);

        Attempt reqA = new Attempt(
            "_req-A", "relay-A", "shared-a", "tenant-C",
            a.spEntityId(), now + 60);

        Attempt reqB = new Attempt(
            "_req-B", "relay-B", "shared-b", "tenant-D",
            b.spEntityId(), now + 60);

        Map<String, Attempt> requests = Map.of(
            reqA.relayState(), reqA,
            reqB.relayState(), reqB);

        // Concurrent set ở một JVM; production cần atomic store
        // dùng chung giữa nhiều node.
        Set<String> consumed = ConcurrentHashMap.newKeySet();

        VerifiedCallback goodA = new VerifiedCallback(
            "_req-A", "relay-A", issuer, callbackUrl,
            "shared-a", "shared-idp-key", true);

        VerifiedCallback goodB = new VerifiedCallback(
            "_req-B", "relay-B", issuer, callbackUrl,
            "shared-b", "shared-idp-key", true);

        VerifiedCallback wrongTenant = new VerifiedCallback(
            "_req-A", "relay-A", issuer, callbackUrl,
            "shared-b", "shared-idp-key", true);

        VerifiedCallback wrongRequest = new VerifiedCallback(
            "_req-B", "relay-A", issuer, callbackUrl,
            "shared-a", "shared-idp-key", true);

        VerifiedCallback wrongIssuer = new VerifiedCallback(
            "_req-A", "relay-A", "https://other-idp.example/saml",
            callbackUrl, "shared-a", "shared-idp-key", true);

        VerifiedCallback wrongDestination = new VerifiedCallback(
            "_req-A", "relay-A", issuer,
            "https://other-sp.example/logout/saml2/slo",
            "shared-a", "shared-idp-key", true);

        VerifiedCallback badSignature = new VerifiedCallback(
            "_req-A", "relay-A", issuer, callbackUrl,
            "shared-a", "shared-idp-key", false);

        VerifiedCallback noOriginal = new VerifiedCallback(
            "_req-X", "relay-unknown", issuer, callbackUrl,
            "shared-a", "shared-idp-key", true);

        System.out.println("unknown=" +
            check(noOriginal, requests, trusted, consumed, now));
        System.out.println("crossTenant=" +
            check(wrongTenant, requests, trusted, consumed, now));
        System.out.println("wrongRequest=" +
            check(wrongRequest, requests, trusted, consumed, now));
        System.out.println("wrongIssuer=" +
            check(wrongIssuer, requests, trusted, consumed, now));
        System.out.println("wrongDestination=" +
            check(wrongDestination, requests, trusted, consumed, now));
        System.out.println("badSignature=" +
            check(badSignature, requests, trusted, consumed, now));
        System.out.println("expired=" +
            check(goodB, requests, trusted, consumed, now + 61));
        System.out.println("tenantA=" +
            check(goodA, requests, trusted, consumed, now));
        System.out.println("replay=" +
            check(goodA, requests, trusted, consumed, now));
        System.out.println("tenantB=" +
            check(goodB, requests, trusted, consumed, now));
    }
}
~~~

### 10.2. Biên dịch và chạy

Với JDK 17+:

~~~bash
javac --release 17 SloCallbackBindingDemo.java
java SloCallbackBindingDemo
~~~

**Stdout chính xác:**

~~~text
unknown=NO_ORIGINAL_REQUEST
crossTenant=REGISTRATION_MISMATCH
wrongRequest=REQUEST_ID_MISMATCH
wrongIssuer=ISSUER_MISMATCH
wrongDestination=DESTINATION_MISMATCH
badSignature=UNTRUSTED_SIGNATURE
expired=EXPIRED
tenantA=ACCEPTED
replay=REPLAY
tenantB=ACCEPTED
~~~

### 10.3. Bài học rút ra từ code

- Hai registrations cùng `Issuer`, cùng `SLO callback URL` và cùng verification key, nhưng khác SP entity ID/tenant; chỉ biết Issuer hoặc cert **không đủ** chọn tenant.
- `originalByRelay` là mô phỏng lookup request do SP đã tạo, không phải dữ liệu browser tự ý định nghĩa.
- `validatedRegistrationId` và `signatureTrusted` được **giả lập**: trong production chúng phải là kết quả từ SAML provider thực sự kiểm chứng signing key theo **original registration**, không lấy từ HTTP query/body.
- `alreadyConsumed.add(...)` ngăn replay trong một JVM; nhiều instance cần Redis/SQL transaction hoặc store khác có **atomic consume + TTL**.
- `EXPIRED` dùng thời hạn 60 giây **chỉ để minh họa**, không phải thời hạn mặc định của Spring Security hoặc SAML2.
- `ACCEPTED` chỉ chứng minh đã qua các quy tắc mô phỏng; **không tự xóa session HTTP** và không thay SAML cryptographic validation.

**Tình huống quan trọng nhất:** `wrongTenant` có đúng IdP issuer và verification key nhưng sai registration — vẫn bị từ chối. Đây là khác biệt giữa “biết người ký” và “biết message này thuộc giao dịch/tenant nào”.

## 11. Spring Boot 3.3 / Spring Security 6.3: ví dụ hai registration SLO

Mẫu dưới đây trình bày **cách cấu hình hai quan hệ SP–IdP độc lập**, giữ SAML logout callback cho framework xử lý. Nó chỉ sử dụng bộ lọc/validator SLO mặc định; muốn thêm kiểm toán tenant và custom request store phải triển khai extension point riêng ở mục 12.

### 11.1. Cấu trúc dự án

~~~text
multi-tenant-slo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/slo/
    │   ├── MultiTenantSloApplication.java
    │   ├── SecurityConfig.java
    │   └── PageController.java
    └── resources/
        ├── application.yml
        └── templates/
            ├── index.html
            └── signed-out.html
~~~

### 11.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-tenant-slo'
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

### 11.3. Main application

`src/main/java/com/example/slo/MultiTenantSloApplication.java`:

~~~java
package com.example.slo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiTenantSloApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiTenantSloApplication.class, args);
    }
}
~~~

### 11.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            entity-id: "https://orders.example/saml2/sp/partner-a"
            assertingparty:
              metadata-uri: ${IDP_A_METADATA_URI}
            signing:
              credentials:
                - private-key-location: "file:${SP_A_SIGNING_KEY}"
                  certificate-location: "file:${SP_A_SIGNING_CERT}"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
              binding: POST

          partner-b:
            entity-id: "https://orders.example/saml2/sp/partner-b"
            assertingparty:
              metadata-uri: ${IDP_B_METADATA_URI}
            signing:
              credentials:
                - private-key-location: "file:${SP_B_SIGNING_KEY}"
                  certificate-location: "file:${SP_B_SIGNING_CERT}"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
              binding: POST
~~~

**Đọc cấu hình:**

- Hai `registrationId` khác nhau, và SP entity ID cũng khác nhau.
- Mỗi IdP metadata URL được **quản trị cung cấp qua biến môi trường**; phải trỏ tới issuer/endpoint/certificate tin cậy thực tế.
- SP signing credentials phục vụ việc ký LogoutRequest/LogoutResponse theo hợp đồng. Không commit private key trong source, không đưa SAML signing key lên browser.
- Hai SP registration có thể công bố **cùng một SLO callback URL**. Với RP-initiated callback, original request vẫn phải quyết định registration; không lấy host/path dùng chung làm tenant key.
- `singlelogout.url` là **SP endpoint**, còn IdP LogoutService endpoint lấy từ `SingleLogoutService` trong metadata IdP.
- Mẫu giả định **cả hai IdP đều hỗ trợ SLO** và đã thống nhất binding/signing. Nếu một IdP không hỗ trợ, giữ local-only cho registration đó; không tự dự đoán URL hoặc bật SLO mù quáng.
- Cần cấu hình entity ID/ACS/SLO public URL tại từng IdP tương ứng. `https://orders.example` chỉ biểu diễn host tích hợp; khi chạy thực tế phải thay bằng domain deployment đã được tổ chức sở hữu.
- Với reverse proxy/load balancer, thiết lập forwarded headers và canonical HTTPS origin tin cậy để `{baseUrl}` không bị tính từ Host header do attacker thao túng.

**Đa tenant có cùng IdP:** có thể đặt `IDP_A_METADATA_URI` và `IDP_B_METADATA_URI` trỏ cùng nguồn, nhưng mỗi SP registration vẫn phải được IdP định danh bằng đúng SP entity ID và callback. Nếu IdP không phân biệt được hai SP registrations theo metadata/hợp đồng, cần sửa mô hình tích hợp chứ không tự giải quyết bằng cách chọn tenant từ một query param.

### 11.5. SecurityConfig.java

`src/main/java/com/example/slo/SecurityConfig.java`:

~~~java
package com.example.slo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
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
            )
            .saml2Logout(saml -> saml
                .logoutUrl("/saml2/logout")
            )
            .build();
    }
}
~~~

**Hai thao tác khác nhau:**

- `POST /logout` = local logout qua Spring Security; nó không phát `LogoutRequest` theo cấu hình tách endpoint này.
- `POST /saml2/logout` = người dùng khởi tạo SLO cho **registration của Authentication hiện tại**, không tùy ý chọn IdP từ query.
- `/logout/saml2/slo` = default callback xử lý SAML LogoutRequest/LogoutResponse do Spring filters sở hữu.
- Không viết Spring MVC controller cùng callback, không chặn/disable các validator mặc định để tự chọn tenant.
- Không tắt CSRF toàn cục; các form phía ứng dụng cần CSRF token. Callback SAML do bộ lọc SLO xử lý theo binding/profile.
- Việc bật `saml2Logout` không tự tạo phân quyền nghiệp vụ hay tenant isolation: authorization vẫn là nhiệm vụ của ứng dụng.

**Cần nhấn mạnh:** ví dụ chỉ cho thấy **framework routing/trust cấu hình chuẩn**. Nó không tự tạo một custom `Saml2LogoutRequestRepository` phân tán hay chứng minh rằng hai registrations cùng issuer có thể xử lý mọi trường hợp AP-initiated không nhập nhằng.

### 11.6. PageController.java

`src/main/java/com/example/slo/PageController.java`:

~~~java
package com.example.slo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/")
    public String index() {
        return "index";
    }

    @GetMapping("/signed-out")
    public String signedOut() {
        return "signed-out";
    }
}
~~~

### 11.7. index.html

`src/main/resources/templates/index.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8"/>
    <title>Đăng xuất SAML2</title>
</head>
<body>
<h1>Đăng xuất trong hệ thống nhiều IdP</h1>
<p>
    SLO sẽ dùng registration của người đang đăng nhập.
    Không sử dụng tham số tenant do trình duyệt tự đặt
    để chuyển sang IdP khác.
</p>

<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Chỉ đăng xuất ứng dụng</button>
</form>

<form th:action="@{/saml2/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Yêu cầu SAML Single Logout</button>
</form>
</body>
</html>
~~~

### 11.8. signed-out.html

`src/main/resources/templates/signed-out.html`:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"/>
    <title>Đã đăng xuất</title>
</head>
<body>
<h1>Đã đăng xuất khỏi ứng dụng này</h1>
<p>
    Phiên tại ứng dụng đã kết thúc. Phiên tại IdP
    hoặc ứng dụng khác có thể vẫn tồn tại nếu SLO
    không được hỗ trợ hoặc chưa xác nhận.
</p>
</body>
</html>
~~~

**Lưu ý:** trang này nói về local logout; khi SLO diễn ra qua browser, trang cuối có thể do IdP quyết định. Nếu hệ thống yêu cầu hiển thị kết quả `Success`/`PartialLogout`, cần bổ sung state tracking và success/failure handling được tích hợp với validator theo đúng Spring Security version.

### 11.9. Chạy và kiểm thử với IdP test

Với JDK 17 và Gradle wrapper phù hợp:

~~~bash
./gradlew bootRun
~~~

Trong Windows PowerShell, dùng `.\gradlew.bat bootRun`.

Cần cung cấp metadata IdP và cặp signing key/certificate thực, đăng ký đúng SP entity ID/ACS/SLO callback tại cả hai IdP. Thiếu metadata hoặc key có thể khiến ứng dụng không khởi động hoặc SLO không thành công; code **không chứa IdP giả để tự xác thực**.

1. Đăng nhập với registration `partner-a` qua `/saml2/authenticate/partner-a`; xác nhận principal thuộc đúng IdP A.
2. Gửi POST `/saml2/logout` với CSRF token: kiểm tra browser được chuyển tới IdP A, không phải B.
3. Cho IdP A trả LogoutResponse đã ký và đúng InResponseTo; kiểm tra validation và kết quả.
4. Lặp với `partner-b` và chắc chắn sử dụng IdP B.
5. Dùng IdP test cùng issuer ở hai registrations để thử ambiguity; nếu framework cần resolver thêm, **không** dùng bản demo chung để khẳng định trường hợp đó đã tự được giải quyết.
6. Thử callback sai registration hint hoặc sai original request ID; phải bị từ chối, không cập nhật tenant khác.
7. Thử callback đi tới node khác để xác minh session/request repository và correlation.

**Giới hạn demo:** nó chưa triển khai việc custom audit state và shared correlation store; các kiểm thử cross-node, concurrent consume và mapping nhiều tenant cùng issuer đòi setup thêm phù hợp hệ thống production.

## 12. Extension points Spring Security cần biết

### 12.1. Những lớp liên quan

| Class/interface | Vai trò |
| --- | --- |
| `RelyingPartyRegistrationRepository` | Trả metadata/config đáng tin cho một registration ID. |
| `RelyingPartyRegistrationResolver` | Quyết định registration từ request/context khi cần tùy chỉnh, không thay SAML verification. |
| `Saml2AuthenticatedPrincipal` | Khi user đang đăng nhập, có `getRelyingPartyRegistrationId()`. |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Sau local logout, tạo và gửi LogoutRequest đến IdP của principal. |
| `Saml2LogoutRequestResolver` | Tạo signed LogoutRequest từ authentication/registration. |
| `Saml2LogoutRequestRepository` | Lưu/load/remove request để kiểm tra RelayState/InResponseTo. |
| `Saml2LogoutResponseFilter` | Nhận LogoutResponse cho RP-initiated flow. |
| `Saml2LogoutResponseValidator` | Xác minh response theo registration và request gốc. |
| `Saml2LogoutRequestFilter` | Nhận AP-initiated LogoutRequest. |
| `Saml2LogoutRequestValidator` | Xác minh LogoutRequest với registration/Authentication tương ứng. |
| `Saml2LogoutResponseResolver` | Tạo LogoutResponse cho AP-initiated flow. |

Tên triển khai OpenSAML 4/5 và vị trí một số extension point thay đổi theo phiên bản. Tài liệu Spring Security **6.3.5** xác nhận `Saml2LogoutResponseValidator` kiểm tra signature, issuer, destination, status và sự phù hợp với original logout request. **Không tự thay validator bằng code chỉ kiểm tra tenantId**.

### 12.2. Cấu hình custom request repository

Khi có một implementation đúng interface/version:

~~~java
// Mảnh DSL cho SecurityFilterChain; cần bean customRepository thật.
http.saml2Logout(saml -> saml
    .logoutRequest(req -> req
        .logoutRequestRepository(customRepository)
    )
);
~~~

Các điều kiện để dùng trong production:

- `saveLogoutRequest` ghi trước khi browser rời SP.
- `loadLogoutRequest` tìm đúng request theo correlation context, không trả request của session khác.
- `removeLogoutRequest`/consume phải ngăn replay/race giữa hai callback.
- TTL, key version và binding theo issuer/registration/tenant được quản lý rõ.
- Multi-node có shared store/replication khi callback không được đảm bảo quay lại node cũ.
- Không mất state chỉ vì local HTTP session bị invalidated.
- Giữ đúng semantics mà `Saml2LogoutResponseValidator` mong đợi.

**Không dùng chỉ một cookie chứa raw LogoutRequest hoặc tự ghép JSON từ browser làm trusted repository**. Kể cả token được ký, vẫn cần quản lý expiry, replay và liên kết với đúng user/tenant.

### 12.3. Cấu hình validator tùy chỉnh

Spring Security cho phép:

~~~java
// Mảnh DSL; customValidator phải delegate/trust đúng version.
http.saml2Logout(saml -> saml
    .logoutResponse(response -> response
        .logoutResponseValidator(customValidator)
    )
);
~~~

Đây **không phải class độc lập**. Cần đối chiếu API và implementation version chính xác. Một validator bổ sung tenant nên:

1. **Gọi default delegate** để xác minh chữ ký, Issuer, Destination, status và tương ứng request gốc.
2. Nếu delegate trả lỗi, **giữ lỗi**, không đổi thành success.
3. Với kết quả hợp lệ, kiểm tra original registration/tenant context, nonce và trạng thái attempt đã được cấp.
4. Fail closed khi trường hợp multi-tenant ambiguity không được giải quyết.
5. Không parse raw HTTP SAMLResponse rồi tin một XML element khác với phần tử framework đã xác minh (rủi ro XML Signature Wrapping).

### 12.4. Custom resolver và lựa chọn IdP

Nếu ứng dụng có IdP-initiated SLO trên callback dùng chung mà không có Authentication/session hiện hành, một resolver tùy chỉnh có thể cần thiết. Nhưng **resolver là nơi chọn ứng viên registration**, không phải nơi cho phép request bypass SAML verification.

Không viết resolver kiểu:

~~~java
// MẪU SAI: không dùng trong hệ thống nhiều tenant.
String selected = httpRequest.getParameter("registrationId");
return registrations.findByRegistrationId(selected);
~~~

Nếu không đi kèm kiểm tra nguồn, chữ ký và tenant scope, attacker có thể chọn IdP trust context. Một thiết kế đúng phải dựa vào **trusted route contract/allowlisted issuer/SP context, validated subject/session binding**, và **không nhập nhằng**. Nếu IdP issuer dùng chung cho nhiều registrations, phải xác định bằng thêm bằng chứng phù hợp profile/metadata hoặc từ chối AP request.

## 13. Cơ sở dữ liệu correlation và audit: mẫu thiết kế

Một bảng ví dụ cho production có nhiều node (PostgreSQL):

~~~sql
CREATE TABLE saml_slo_attempt (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    logout_request_id VARCHAR(255) NOT NULL UNIQUE,
    relay_state_hash VARCHAR(128) NOT NULL UNIQUE,
    registration_id VARCHAR(120) NOT NULL,
    tenant_id VARCHAR(120) NOT NULL,
    idp_entity_id TEXT NOT NULL,
    sp_entity_id TEXT NOT NULL,
    sp_slo_callback TEXT NOT NULL,
    config_version VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    outcome VARCHAR(40) NOT NULL
        CHECK (outcome IN (
            'PENDING', 'ACCEPTED', 'PARTIAL', 'FAILED',
            'EXPIRED', 'INVALID_RESPONSE', 'UNKNOWN'
        ))
);
CREATE INDEX saml_slo_attempt_due
    ON saml_slo_attempt (expires_at)
    WHERE consumed_at IS NULL;
~~~

Đây là **schema khái niệm**, không tự tương đương một `Saml2LogoutRequestRepository` chạy được. Schema dùng `relay_state_hash` để tránh log/plaintext state nếu policy cho phép, nhưng cách tra lookup phải nhất quán với format token, khóa hash và khả năng rotation. `config_version` phục vụ audit/rollover; không được tự bỏ trust-current checks vì đã lưu một version cũ.

Cần cân nhắc:

- Request correlation lấy từ bộ tạo request trusted, không phải JSON do browser gửi.
- Atomic claim trong transaction, ví dụ chỉ chuyển `PENDING → ACCEPTED` khi `consumed_at IS NULL` và deadline còn hợp lệ.
- Một response invalid không được làm thay đổi outcome của một request khác.
- Tenant ID trong bảng lấy từ trusted registration/user context, không từ HTTP header tùy ý.
- Nhiều callback đồng thời cho cùng request ID chỉ một callback hợp lệ được chấp nhận.
- Delete/purge record theo retention; log không chứa NameID, SessionIndex, private key hoặc SAML raw payload.

### 13.1. Ví dụ SQL atomic consume

~~~sql
-- Sau khi bộ SAML validator đã xác minh response và context:
UPDATE saml_slo_attempt
SET consumed_at = CURRENT_TIMESTAMP,
    outcome = 'ACCEPTED'
WHERE logout_request_id = :request_id
  AND registration_id = :registration_id
  AND tenant_id = :tenant_id
  AND outcome = 'PENDING'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Ứng dụng phải yêu cầu **affected rows = 1** để đánh dấu một attempt accepted. Đây chỉ là phần **atomic state transition**, không tự kiểm tra chữ ký, RelayState, InResponseTo, issuer, Destination hay Status. Nếu IdP trả PartialLogout, outcome phải là `PARTIAL` thay vì ACCEPTED theo model nghiệp vụ. Đừng áp câu SQL này trước khi SAML message đã được xác minh.

## 14. Key rollover, metadata refresh và registration changes

### 14.1. Một IdP thay cert khi LogoutRequest đang bay

T0 SP lưu original request thuộc partner-a. T1 IdP công bố signing key mới, SP refresh trusted metadata. T2 IdP gửi LogoutResponse ký bằng key mới.

Cần:

1. Giữ **original registration binding** đến hết thời hạn request, không chuyển sang một registration khác vì key mới.
2. Đánh giá key theo **trust policy** và metadata được chấp nhận của chính IdP/registration đó.
3. Nếu rotation A→A+B→B hợp lệ, test acceptance phù hợp. Nếu A bị compromise, phải remove A theo incident policy.
4. Không khôi phục key bị revoke chỉ vì một request cũ đang chờ.
5. Test response đến sau metadata refresh và qua nhiều node khác nhau.

### 14.2. Đổi `registrationId` nhưng không đổi SAML entity ID

`registrationId` là khóa cấu hình. Đổi tên từ `partner-a` sang `supplier-a` trong lúc có SLO attempts đang chờ có thể làm `Saml2LogoutRequestRepository` giữ ID cũ mà lookup thất bại.

Giải pháp thường là giữ alias/registration tương thích trong cửa sổ ngắn được kiểm soát hoặc hoàn thành/đóng attempts trước khi đổi, với migration policy và audit. **Không fallback sang mọi registration để tìm cái verify được**.

### 14.3. Đổi SP entity ID hoặc IdP issuer

Đây là thay đổi **trust identity**, nghiêm trọng hơn đổi registrationId. Original request phát cho SP/IdP cũ không tự hợp lệ cho entity ID mới. Phải thống nhất metadata, certificates, SLO URLs, tenant mapping và kế hoạch cutover; tránh dùng alias thiếu kiểm soát làm rộng trust boundary.

## 15. Nếu callback bị mất hoặc thông điệp có lỗi

| Sự kiện | Trạng thái phù hợp | Điều không được làm |
| --- | --- | --- |
| Không tìm thấy original LogoutRequest | `NO_ORIGINAL_REQUEST` | Đoán registration theo issuer rồi chấp nhận response. |
| Original request hết TTL | `EXPIRED` / late callback | Chấp nhận lại để “đỡ lỗi đăng xuất”. |
| SAML signature/Issuer sai | `INVALID_RESPONSE` | Chuyển sang cert IdP khác để thử tùy ý. |
| `InResponseTo` không khớp | `REQUEST_ID_MISMATCH` | Ghép vào attempt theo NameID/tenant hint. |
| `RelayState` bị sửa | `CORRELATION_FAILURE` | Tự tạo request mới có cùng ID từ XML nhận. |
| Tenant context mismatch | `REGISTRATION_MISMATCH` | Logout sai tenant hoặc báo success cho tenant khác. |
| IdP báo `PartialLogout` | `PARTIAL_LOGOUT` | Tuyên bố mọi SP khác đã logout. |
| Browser không quay lại | `TIMEOUT_UNKNOWN` | Khẳng định IdP đã/chưa logout một cách chắc chắn. |
| Callback lặp/replay | `REPLAY_REJECTED` | Chạy thêm cleanup hoặc ghi success lần nữa. |
| Local session đã bị hủy | `LOCAL_LOGOUT_DONE` | Phục hồi session chỉ vì callback lỗi. |

**Không trả raw issuer, NameID, SessionIndex, stack trace hoặc nguyên văn SAML XML ra trình duyệt.** Thông báo cho người dùng nên đơn giản: “Phiên ứng dụng đã kết thúc; chưa thể xác nhận đăng xuất liên thông ở những nơi khác” nếu chưa có response đã xác minh.

## 16. Logging, metrics và điều tra không làm lộ định danh

Gợi ý log có cấu trúc:

~~~text
event=saml_slo_started
registration_id=partner-a
tenant_id=tenant-A
attempt_id=opaque-internal-id
request_id_hash=...
idp_issuer_ref=approved-idp-ref
slo_callback_ref=approved-callback-ref

event=saml_slo_response_checked
attempt_id=opaque-internal-id
correlation=PASS
issuer_and_signature=PASS
destination=PASS
result=PARTIAL
~~~

Dấu `...` biểu diễn giá trị vận hành do hệ thống tạo khi triển khai; **không log raw payload**. Log nên giới hạn số lượng field không kiểm soát và tránh dùng NameID, email hay SessionIndex làm metric labels.

Metric đề xuất (không phải Spring Security tự cung cấp):

~~~text
saml_slo_callback_total{registration_id,result}
saml_slo_registration_mismatch_total{registration_id}
saml_slo_no_original_total{registration_id}
saml_slo_replay_total{registration_id}
saml_slo_late_callback_total{registration_id}
saml_slo_request_store_load_failure_total{node}
saml_slo_ap_initiated_total{registration_id,result}
~~~

Dùng `registration_id`/`node` hữu hạn và được quản trị, không đặt callback request ID/RelayState làm label high-cardinality. Alert khi `NO_ORIGINAL_REQUEST` tăng đột biến; thường gợi ý mất HTTP session/correlation store, proxy/cookie/SameSite, cấu hình node, TTL hoặc replay.

## 17. Ma trận kiểm thử trọng yếu

| ID | Tình huống | Kết quả đúng |
| --- | --- | --- |
| R01 | SP A phát LogoutRequest, IdP A trả LogoutResponse đúng Issuer/ID/destination/signature. | Chấp nhận theo original registration A. |
| R02 | Callback có `registrationId=B` nhưng original A. | Reject cross-registration, không gắn B. |
| R03 | IdP A và B cùng phát một NameID value. | Không dùng value làm khóa tenant/trust. |
| R04 | Hai registration chung IdP issuer và shared callback URL. | RP callback xác định theo original request, không chỉ Issuer. |
| R05 | Hai registration chung IdP issuer và public verification key. | Vẫn cần original SP scope/tenant binding. |
| R06 | LogoutResponse có `InResponseTo` của request khác. | Reject mismatch. |
| R07 | RelayState đúng nhưng chữ ký không tin cậy. | Reject signature. |
| R08 | Chữ ký hợp lệ nhưng Issuer sai. | Reject issuer. |
| R09 | Chữ ký hợp lệ nhưng Destination tới SP khác. | Reject destination. |
| R10 | Callback không có original request. | Reject unsolicited RP LogoutResponse. |
| R11 | Callback tới node khác, store chia sẻ hoạt động. | Verify đúng original registration. |
| R12 | Callback tới node khác, store không có request. | Reject/fail closed, không đoán tenant. |
| R13 | Duplicate/replay cùng LogoutResponse. | Một lần consume, lần sau reject. |
| R14 | Callback đến sau TTL. | Expired/late response theo policy, không restore session. |
| R15 | Browser không quay lại IdP callback. | TIMEOUT_UNKNOWN, local logout vẫn có hiệu lực. |
| R16 | Metadata IdP rotate signing cert A→B khi request chờ. | Trust đúng IdP, không chọn registration khác. |
| R17 | SP `registrationId` đổi giữa request/callback. | Migration/alias có giới hạn hoặc fail closed. |
| R18 | AP-initiated LogoutRequest từ IdP A, session của A. | Verify và logout đúng session/tenant. |
| R19 | AP-initiated LogoutRequest từ IdP A, NameID trùng user B. | Không logout session B. |
| R20 | AP-initiated với issuer dùng chung hai tenants và không có route đáng tin. | Reject ambiguity. |
| R21 | AP-initiated request có chữ ký sai. | Reject, không hủy session tùy ý. |
| R22 | AP-initiated request replay. | Reject duplicate theo profile/policy. |
| R23 | SLO success nhưng local account thuộc tenant khác. | Không đổi quyền hoặc data tenant đó. |
| R24 | SP session đã invalidated trước callback. | Request repo vẫn resolve original; không dựa vào current principal. |
| R25 | IdP không hỗ trợ SLO trong metadata. | Chỉ local logout, không tạo request giả. |
| R26 | Response có top-level Success + nested PartialLogout. | Ghi partial, không báo full federation success. |
| R27 | Requester/Responder error hợp lệ. | Ghi failure theo status, local logout giữ nguyên. |
| R28 | SLO URL qua reverse proxy bị sai scheme/host. | Sửa canonical base URL, không tắt Destination validation. |
| R29 | Multi-node nhận hai callback cùng request đồng thời. | Atomic consume, không double-finalize. |
| R30 | Callback chứa XML/HTTP param `tenantId` do client tự khai. | Không dùng làm trust/tenant authority. |

### 17.1. Kế hoạch test tích hợp

1. Cấu hình hai IdP test với issuer và signing cert khác nhau.
2. Cấu hình hai tenant dùng **cùng issuer** nhưng SP entity ID/registration khác nhau; thử RP callback về URL chung.
3. Chạy login thật và lưu original SLO attempt bằng repository chuẩn.
4. Phát SLO, trả LogoutResponse đúng; đo correlation/replay và kết quả UX.
5. Với IdP test có quyền cấu hình, tạo LogoutResponse sai InResponseTo, sai Destination, sai signing key và sai Issuer.
6. Gửi callback đến Node 2 khi request được tạo ở Node 1; thử shared store hoạt động và mất state.
7. Thử AP-initiated request từ IdP A trong khi có session ở tenant B với NameID tương tự.
8. Thử metadata refresh/rotation và outstanding SLO request; không nới key trust.
9. Thử response đến muộn, partial và no-response; đánh dấu trạng thái trung thực.
10. Giữ CSRF cho local logout, để Spring SAML filters xử lý inbound protocol theo profile.

**Lưu ý:** Java demo mục 10 chỉ kiểm tra các quy tắc **mô phỏng sau validation**, chưa thực hiện cryptography thật. Project mục 11 dùng Spring SAML2 framework nhưng **không tự bao phủ hết các tình huống custom multi-tenant resolver/request-store**; các test R02/R04/R05/R11/R20/R29 cần cấu hình hoặc code hạ tầng tương ứng và kiểm tra kết quả thật.

## 18. Lỗi triển khai thường gặp

| Cách làm sai | Vì sao sai? | Giải pháp |
| --- | --- | --- |
| “Callback có `Issuer=A` nên registration=A.” | Một Issuer có thể có nhiều registrations/tenants. | Original request hoặc resolver có trusted disambiguation. |
| “Đường dẫn `/slo/B` chứng minh tenant B.” | Browser có thể gọi path này. | Verify message và so khớp original B/tenant scope. |
| “Chỉ cần chữ ký đúng một cert bất kỳ.” | Cert IdP khác/attacker có thể ký một XML tự tạo. | Verification credentials thuộc đúng registration. |
| “Cùng NameID/SessionIndex thì cùng user.” | Namespace IdP/tenant khác nhau. | Key theo issuer/SP scope và session binding. |
| “Không tìm thấy original request thì tự tạo record từ InResponseTo.” | Attacker có thể giả request/correlation. | Fail closed, điều tra repository/session. |
| “Callback không có Authentication nên lấy tenant từ query.” | SP thường đã invalidated session trước SLO callback. | Request repository lưu context ban đầu. |
| “Đổi registrationId trong lúc pending rồi tìm thử mọi tenant.” | Trust boundary bị mở rộng. | Cutover/alias có kiểm soát và TTL. |
| “Đến callback rồi mới xem metadata URL do HTTP body nói.” | Metadata bị điều khiển bởi input không tin. | Chỉ dùng trusted metadata/config đã duyệt. |
| “Dùng XML parser riêng để đọc status.” | Có nguy cơ XML Signature Wrapping/parse khác phần tử ký. | Spring/OpenSAML validator, extension points. |
| “Bỏ InResponseTo vì IdP trả Success.” | Không gắn response với request nào. | Từ chối nếu không có original/correlation. |
| “Local logout fail thì báo SLO success.” | Chưa xóa session ứng dụng. | Kiểm tra từng lớp logout độc lập. |
| “SLO lỗi thì khôi phục phiên local cũ.” | Session đã invalidated, không an toàn. | Login mới khi cần. |
| “Một request ID có thể complete nhiều lần.” | Replay/race hoặc audit sai. | Atomic consume/idempotency. |
| “Dùng HTTP Host header để xây Destination tin cậy.” | Host header injection/reverse proxy sai. | Canonical HTTPS base URL từ trusted config. |

## 19. Câu hỏi tự kiểm tra

**1. Vì sao `registrationId` không nhất thiết xuất hiện trong callback SLO mặc định?**  
Vì Spring có thể suy ra registration từ user đang đăng nhập hoặc original LogoutRequest đã được lưu cho RP-initiated callback. Điều này chỉ an toàn nếu thông điệp vẫn được kiểm tra theo đúng registration.

**2. Callback có Issuer đúng IdP, vậy đã đủ chấp nhận chưa?**  
Chưa. Cần chữ ký, Destination, request correlation, tenant context và các điều kiện theo profile.

**3. Hai tenants cùng IdP issuer, làm sao phân biệt RP callback?**  
Dựa vào LogoutRequest/RelayState/ID **gốc** mà SP đã phát cho registration đã biết; không chỉ theo Issuer.

**4. `InResponseTo` để làm gì?**  
Tham chiếu chính xác LogoutRequest ID do SP phát; giúp chặn unsolicited/mix-up responses.

**5. Nếu RP-initiated LogoutResponse không tìm được original request?**  
Fail closed. Không “xây lại” original từ nội dung response hoặc đoán registration.

**6. AP-initiated LogoutRequest có original LogoutRequest từ SP không?**  
Không. Phải resolve trusted registration và matching user/session theo nguồn IdP/signature/NameID/SessionIndex.

**7. Có thể dùng `SessionIndex` của IdP A để xóa session IdP B không?**  
Không; chuỗi không có tính duy nhất toàn federation.

**8. Vì sao chữ ký cùng một IdP không phân biệt được hai tenants của IdP ấy?**  
Bởi nguồn ký giống nhau; còn tenant/SP entity ID phải được xác định theo original transaction hoặc verified route/session context.

**9. Khi callback tới Node 2 nhưng request ở Node 1, nên làm gì?**  
Dùng session/request store phù hợp multi-node; nếu không tìm được thì reject thay vì đoán.

**10. Thay URL callback sang một host khác có thể sửa bằng việc tắt Destination validation không?**  
Không. Cần cập nhật public URL/metadata/reverse proxy và giữ validation.

**11. Nếu LogoutResponse đúng chữ ký nhưng `InResponseTo` của request khác?**  
Reject request mismatch; chữ ký đúng không cho phép chuyển kết quả giữa attempts.

**12. Sau khi callback đã verify success, có thể truy cập tài nguyên tenant khác không?**  
Không. Logout không trao quyền; authorization của SP luôn phải độc lập.

## 20. Checklist production

- [ ] Xác định mỗi `registrationId` và trust relationship SP–IdP trong repository.
- [ ] SP entity ID, IdP issuer, tenant và SLO URL có ranh giới rõ.
- [ ] RP callback được đối chiếu original LogoutRequest đã lưu trước khi logout local.
- [ ] `RelayState` và `InResponseTo` được kiểm chứng chính xác.
- [ ] Xác minh signature và Issuer bằng certificate thuộc **đúng registration**, không trial mọi cert để chọn tenant.
- [ ] So khớp `Destination` với callback public URL, không nhầm SP entity ID.
- [ ] Không chấp nhận RP LogoutResponse unsolicited khi thiếu original.
- [ ] AP-initiated request có resolver không nhập nhằng; NameID/SessionIndex được so sánh trong đúng IdP/tenant scope.
- [ ] Không chọn tenant từ path/query/body mà không kiểm tra nguồn và correlation.
- [ ] Session/LogoutRequestRepository sống qua local logout và callback cross-node khi cần.
- [ ] TTL, atomic consume và chống replay được kiểm thử trong multi-node.
- [ ] IdP key rotation/metadata refresh không làm thay registration gốc.
- [ ] Không khôi phục local Authentication nếu callback bị từ chối hoặc đến muộn.
- [ ] Có outcomes rõ cho Success, Partial, Failure, Invalid và Timeout Unknown.
- [ ] Không ghi raw SAML XML, NameID, SessionIndex, private key hoặc cookie trong log mặc định.
- [ ] Chỉ bật SLO cho IdP đã hỗ trợ và kiểm thử, local-only luôn có.
- [ ] Reverse proxy/base URL/cert được cấu hình đúng với metadata của IdP.
- [ ] Có test R01–R30 trong staging hoặc bộ test bao phủ tương đương.
- [ ] Không chỉnh những lớp validation mặc định chỉ để khắc phục một lỗi interoperability.
- [ ] Khi nâng Spring Security/OpenSAML, đối chiếu Javadoc API và regression tests theo version.

## Ghi nhớ

> **LogoutResponse của một RP-initiated SLO phải được đối chiếu với chính LogoutRequest mà SP đã phát — cùng ID, RelayState, trusted IdP, registration, SP scope và tenant.** Callback URL chung, chữ ký đúng của một IdP, hoặc `registrationId` do trình duyệt cung cấp **không đủ** để chọn đúng tenant. Với AP-initiated SLO, không có original SP LogoutRequest; cần resolver không nhập nhằng và xác minh source/session trước khi xóa local session. Khi không có đủ bằng chứng, **fail closed**, không logout hoặc gắn success nhầm sang tenant khác.

### Tài liệu chính thức

- [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): request/response flow, callback chung, `Saml2LogoutRequestRepository`, các bộ lọc/validator và tùy chỉnh SLO endpoints.
- [Spring Security 6.3.5 — Saml2LogoutResponseValidator Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/authentication/logout/Saml2LogoutResponseValidator.html): mặc định xác minh chữ ký, issuer, destination, status và sự tương ứng với request gốc.
- [Spring Security 6.3.2 — RelyingPartyRegistration API](https://docs.spring.io/spring-security/site/docs/6.3.2/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html): cặp SP/IdP và `registrationId`.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): resolution của registration và cấu trúc RelyingPartyRegistrationRepository.
- [OASIS — SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `LogoutRequest`/`LogoutResponse`, `InResponseTo`, `Issuer`, `Status` và `SessionIndex`.
- [OASIS — SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Single Logout Profile, bindings, xử lý message và session participants.
- [OASIS — Metadata for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `SingleLogoutService`, SP entity ID và IdP entity ID.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout handlers, session invalidation và CSRF.
