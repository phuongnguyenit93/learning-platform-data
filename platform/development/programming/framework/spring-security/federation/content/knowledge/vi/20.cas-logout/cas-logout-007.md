# Xử lý thông báo lặp, phiên đã hết hạn và sự cố mạng

> **Module:** Spring Security – federation · **Chủ đề cha:** Đăng xuất CAS. Bài học hướng dẫn xử lý **CAS Single Sign Out (SLO)** khi máy chủ CAS gửi thông báo đăng xuất **nhiều lần**, thông báo đến khi `HttpSession` đã hết hạn/đã đăng xuất, hoặc callback thất lạc vì sự cố mạng. Mục tiêu là xây cơ chế thu hồi phiên **an toàn, có tính idempotent, đúng người/đúng service, có quan sát được**, đồng thời không tuyên bố CAS có bảo đảm chuyển phát/hoàn tất SLO mà giao thức không cung cấp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **CAS SSO session (TGT/TGC)**, **Service Ticket (ST)**, **phiên HTTP của ứng dụng**, **ánh xạ ST → HttpSession** và **Single Sign Out notification**.
2. Diễn giải đường đi từ việc CAS kết thúc TGT đến ứng dụng nhận `logoutRequest` rồi vô hiệu hóa đúng session local.
3. Nêu rõ hành vi CAS SLO **back-channel POST** khác **front-channel browser/AJAX/iframe**, và thông điệp XML giống cú pháp SAML2 **không tự biến tích hợp này thành Spring Security SAML2 SLO**.
4. Giải thích tại sao CAS SLO theo CAS Protocol có tính **best-effort / fire-and-forget** ở phía máy chủ: CAS có thể bỏ qua lỗi khi gửi thông báo, không cam kết exactly-once delivery.
5. Xử lý thông báo lặp bằng **idempotency**: lần đầu hủy phiên, các lần sau không hủy nhầm phiên khác hoặc tạo lỗi nghiêm trọng.
6. Xử lý session đã timeout/đã logout: ánh xạ có thể không còn vì `SingleSignOutHttpSessionListener` đã dọn, hoặc `invalidate()` có thể gặp `IllegalStateException` trong điều kiện race.
7. Ngăn thông báo **đến trễ** sau khi user đã đăng nhập mới gây thu hồi nhầm session mới, bằng khóa correlation đúng phạm vi service-ticket và generation.
8. Thiết kế bảo vệ network ingress, TLS, nguồn callback, giới hạn XML/payload, chống replay/DoS và chống việc client giả mạo SessionIndex.
9. Hiểu vai trò của `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, `SingleSignOutHandler`/session mapping storage trong Java CAS Client và quan hệ với Spring Security `LogoutFilter`.
10. Xây runbook khi CAS không gọi được SP, callback trả lỗi HTTP, proxy timeout, mất session map khi restart hoặc node khác nhận notification.
11. Chạy chương trình **Java 17 độc lập** có đầu ra xác định để mô phỏng duplicate, expired session, unknown ticket, late callback và transport loss.
12. Lập bộ kiểm thử tích hợp, metrics và chính sách xác định session vẫn còn hoạt động hay đã bị thu hồi trên tất cả node.

**Phạm vi:** CAS service-ticket login và CAS Single Sign Out ở ứng dụng Java Servlet. Tham khảo Spring Boot 3.3.x/Spring Security 6.3.x với Java 17 và Apereo Java CAS Client. API/phụ thuộc servlet `javax`/`jakarta` khác nhau tùy phiên bản; khi triển khai phải xem các artifact thực sự được resolved và đối chiếu API đúng phiên bản. Những đoạn có ghi “mảnh cấu hình” chưa phải một ứng dụng độc lập.

## 2. Tình huống thực tế: CAS logout một lần, Portal nhận nhiều hoặc không nhận thông báo

Orders Portal đã dùng CAS login cho một người dùng:

~~~text
CAS server:
  TGT-1 / TGC        Phiên SSO ở CAS, do CAS quản lý

Orders Portal:
  ST-A               Service Ticket mà CAS cấp cho Orders
  JSESSIONID=app-71  Phiên web của Orders
  ST-A -> app-71     Ánh xạ phục vụ CAS Single Sign Out

Reports Portal:
  ST-B -> app-92     Một ứng dụng khác, phiên khác
~~~

Người dùng đăng xuất tại CAS. CAS hủy TGT và cố thông báo cho những ứng dụng đã tham gia SSO.

Nhưng có thể có các kết quả:

- **Normal:** Orders nhận thông báo ST-A, tìm `app-71`, gọi `invalidate()`, xóa Authentication trong phiên local.
- **Duplicate:** proxy retry hoặc CAS gửi lại khiến Orders nhận cùng thông báo hai lần. Sau lần đầu, `app-71` đã kết thúc; lần hai cần **không gây tác dụng phụ mới**.
- **Expired:** session `app-71` hết hạn trước khi CAS gửi thông báo. Mapping đã được listener dọn; không tìm thấy session là điều bình thường, **không phải lý do tạo session mới**.
- **Local logout first:** user đã đăng xuất ở Orders, sau đó CAS mới báo. Không cần cố xóa lại phiên đã mất.
- **Network loss:** CAS gọi Orders nhưng DNS/TLS/proxy lỗi; Orders không hề nhận thông báo. **Phiên app-71 có thể vẫn hoạt động** cho đến logout/session timeout/biện pháp thu hồi khác.
- **Late event after re-login:** user nhận một ST-C mới và tạo `app-103` sau khi phiên app-71 kết thúc. Thông báo cũ cho **ST-A** không được hủy nhầm `app-103`.

**Quy tắc mấu chốt:** Mỗi thông báo chỉ được tác động đến **phiên ứng dụng được liên kết với ticket/nguồn CAS ban đầu**, không phải “mọi session đang có cùng username”.

## 3. Năm đối tượng và vòng đời độc lập

| Đối tượng | Nơi quản lý | Vai trò trong SLO | Không được nhầm với |
| --- | --- | --- | --- |
| CAS TGT/TGC | CAS server + cookie domain CAS | Phiên SSO khiến CAS biết các dịch vụ đã tham gia và kích hoạt logout khi TGT kết thúc. | `JSESSIONID` của ứng dụng. |
| Service Ticket ST | CAS ticket registry | Được phát cho đúng `service` và **tiêu thụ** khi Portal xác minh. | ID phiên Java Servlet. |
| `HttpSession` | Portal/container/session store | Phiên local chứa SecurityContext, được invalidate khi có SLO notification hợp lệ. | TGT hay ST. |
| Mapping `ST → session` | CAS client tại Portal | Tìm phiên local cần hủy dựa trên SessionIndex/ticket của CAS. | Database user theo NameID hoặc email. |
| CAS SLO notification | CAS → Portal (back/front channel) | Yêu cầu Portal kết thúc phiên được nhắc đến. | Bằng chứng CAS đã tự hủy tất cả phiên của mọi ứng dụng. |

ST đã tiêu thụ ở bước login **vẫn có thể là khóa correlation** dùng cho logout sau này. Điều đó **không có nghĩa ST được phép xác minh lần hai**; CAS client chỉ lưu giá trị định danh để đối chiếu phiên được tạo từ ST ấy.

### 3.1. Ba đồng hồ khác nhau

~~~text
CAS SSO session:
  TGT issued ----------------------------- TGT expires / /logout

Service Ticket:
  ST issued -- ST validated once; consumed (login)

Application session:
  JSESSIONID created -------------------- local idle timeout / logout

SLO notification:
  CAS logout ---> POST queued/sent ---> SP received / timed out / missing
~~~

Các mốc này không nhất thiết trùng nhau. Ví dụ local HttpSession có thể hết hạn sau 20 phút không hoạt động, trong khi TGT CAS vẫn còn; hoặc CAS kết thúc TGT sớm nhưng SP đang chờ thông báo mà mạng không hoạt động.

## 4. CAS SLO diễn ra thế nào?

### 4.1. Back-channel: CAS server gửi HTTP POST trực tiếp

~~~text
Browser                 CAS Server              Orders Portal          Reports Portal
  |                         |                        |                      |
  |  GET CAS /logout        |                        |                      |
  |------------------------>| invalidate TGT         |                      |
  |                         |                        |                      |
  |                         |--- POST logoutRequest ->|                      |
  |                         |                        | lookup ST-A->app-71  |
  |                         |                        | invalidate session   |
  |                         |<-- HTTP response ------|                      |
  |                         |-------------------------- POST logoutRequest ->|
  |                         |                        |                      | lookup ST-B->app-92
  |                         |                        |                      | invalidate
  |<-- CAS logout page -----|                        |                      |
~~~

Theo CAS Protocol, server **có thể hỗ trợ SLO**, và khi gửi các SLO POST nó được phép **bỏ qua lỗi** để không ảnh hưởng khả dụng của chính CAS. Do đó:

- HTTP 200 từ Orders **không chứng minh** Reports cũng đã hủy session.
- CAS logout page thành công **không chứng minh** Orders nhận callback.
- Không thấy callback ở Orders **không chứng minh** CAS chưa hủy TGT.
- Một proxy retry không biến thao tác thành exactly once.
- CAS server có thể có cơ chế delivery/retry/cấu hình riêng theo version; **không giả định** mọi bản CAS sẽ tự retry tới khi tất cả SP xác nhận.

### 4.2. Ví dụ logoutRequest XML

Trong CAS SLO back-channel, payload thường là form field `logoutRequest` chứa XML có hình dạng SAML2 LogoutRequest:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_cas-logout-event-42"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z">
    <saml:NameID>alice</saml:NameID>
    <samlp:SessionIndex>ST-ORIGINAL-ORDERS-77</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

**Đây chỉ là XML minh họa, không mang chữ ký số thực.** Giá trị trong `SessionIndex` của thông báo CAS thông dụng là **service ticket ID dùng để đối chiếu phiên**; nó **không phải** Servlet `session.getId()`, và cũng không được chọn làm global user ID.

Hình dạng namespace `samlp`/`saml` trong CAS SLO **không có nghĩa** nên dùng `http.saml2Logout()` của Spring Security để nhận thông báo. CAS client có handler riêng và semantics khác SAML2 SP LogoutRequest/LogoutResponse.

### 4.3. Front-channel: browser/AJAX/iframe

CAS cũng có thể cấu hình front-channel SLO: trình duyệt được dùng làm phương tiện gửi thông báo tới ứng dụng, chẳng hạn AJAX/JSONP hoặc iframe theo profile/version.

Điểm hạn chế:
- Browser có thể đóng tab, chặn third-party cookies, chặn script, bị ad blocker/CSP tác động hoặc rớt mạng.
- Browser có thể không truy cập được endpoint mạng nội bộ của một SP, dù CAS server back-channel có thể.
- Mỗi loại CAS client không chắc hỗ trợ đầy đủ các biến thể front-channel; kiểm tra phiên bản và liên thông thực tế.
- Không coi một HTTP GET JSONP bất kỳ mang `logoutRequest` là quyền hủy session; bảo vệ origin/transport/payload và chọn đúng CAS client filter/profile.

**Chọn back-channel khi phù hợp kiến trúc**, nhưng nó cũng không có exactly-once guarantee; server-to-server vẫn có DNS/TLS/proxy/firewall/hàng đợi và network failures.

## 5. Java CAS client kết nối ST với HttpSession thế nào?

### 5.1. Thành phần chính

| Thành phần | Vai trò |
| --- | --- |
| `CasAuthenticationEntryPoint` | Spring redirect user tới CAS login để lấy ST. |
| `CasAuthenticationFilter` | Nhận ST ở callback, chuyển cho CAS authentication provider. |
| `CasAuthenticationProvider` + `Cas20ServiceTicketValidator` | Gọi CAS `/serviceValidate` qua HTTPS, xác thực user. |
| `SingleSignOutFilter` của Apereo CAS Client | Theo dõi ticket/session lúc login và xử lý CAS SLO notification khi đến. |
| `SingleSignOutHandler` | Thành phần thực hiện logic mapping/xử lý SLO bên trong Java CAS client. |
| `SessionMappingStorage` | Abstraction lưu ticket → session và quan hệ ngược để dọn mapping. |
| `SingleSignOutHttpSessionListener` | Dọn mapping khi `HttpSession` destroyed/expired. |
| `Spring Security LogoutFilter` | Local logout theo hành động người dùng trong ứng dụng; không phải handler nhận CAS SLO. |
| `SecurityContextRepository` | Persist/restore Authentication trong local HttpSession nếu ứng dụng stateful. |

Tên package phổ biến của các lớp Apereo là `org.apereo.cas.client.session.*`. Phải dùng **Java CAS Client** phù hợp `jakarta.servlet` khi chạy Spring Boot 3.x; không trộn bộ lọc cũ biên dịch với `javax.servlet` và container Jakarta.

### 5.2. Mapping được tạo lúc ứng dụng nhận ST

~~~text
GET /login/cas?ticket=ST-A
     |
     v
SingleSignOutFilter ghi nhận ST-A <-> HttpSession app-71
     |
     v
CasAuthenticationFilter / Provider
     |
     v
CAS /serviceValidate (server-to-server)
     |
     v
CAS success -> Spring SecurityContext trong app-71
~~~

Đây là **sơ đồ khái niệm**: thời điểm ghi mapping/session được tạo và tương tác với filter khác tùy version/registration/order. Phải kiểm tra integration test rằng mapping được tạo đúng **sau login hợp lệ**, không giữ ánh xạ tạo từ ticket validation thất bại như một nguồn quyền.

### 5.3. Mapping được sử dụng khi CAS gửi logout

~~~text
POST logoutRequest{SessionIndex=ST-A}
     |
     v
SingleSignOutFilter / handler
     |
     +-- ST-A mapped to app-71?
           |
           +-- yes -> invalidate(app-71)
           |         remove ST-A mapping
           |
           +-- no -> no local session to invalidate
                     log/metric with bounded detail
~~~

Một CAS SLO notification **không làm user đăng nhập**, không tạo SecurityContext và không được xử lý như request nghiệp vụ. Nó phải được nhận sớm trong filter chain/Servlet path trước khi bị redirect tới login/CSRF rule chặn nhầm.

### 5.4. Listener quan trọng khi session tự kết thúc

`SingleSignOutHttpSessionListener` dọn mapping khi local HttpSession được hủy do timeout, local logout hay shutdown thông thường theo semantics của container. Nếu không gắn listener tương thích hoặc callback của listener không chạy, ticket→session map có thể giữ reference tới session đã vô hiệu, gây memory leak, xử lý lặp và chẩn đoán sai.

**Không thể vì “mapping không tìm thấy” mà kết luận user chắc chắn chưa từng login.** Session có thể đã hết hạn, listener đã dọn đúng, node restart đã mất memory, hoặc event đến rất muộn. Phải dùng audit/metrics để phân biệt.

## 6. Thông báo lặp: xử lý idempotent thay vì cố tránh mọi duplicate

### 6.1. Vì sao có thể xuất hiện duplicate?

- CAS server/worker/proxy gửi lại do request trước bị timeout mà chưa biết SP đã xử lý hay chưa.
- Network gateway retry POST sau HTTP 502/503 hoặc đứt kết nối.
- Một event được replay qua hệ thống queue nội bộ.
- Browser front-channel bị refresh hoặc yêu cầu được gửi lại.
- Người vận hành thực hiện lại một workflow theo runbook.
- Hai đường truyền/instance routing cùng tới endpoint nếu cấu hình sai.

Không nên giả định CAS **luôn** retry; đây là những khả năng từ hạ tầng triển khai. Vì tính bất định của delivery, **receiver phải có thao tác idempotent**.

### 6.2. Định nghĩa đúng

Một thao tác idempotent thỏa điều kiện: **xử lý cùng một yêu cầu đăng xuất hợp lệ nhiều lần cho cùng phiên tạo ra trạng thái kết thúc như xử lý một lần**.

~~~text
Trước:
  session app-71 = ACTIVE
  ST-A -> app-71

SLO lần #1:
  session app-71 = INVALIDATED
  ST-A -> ended / mapping removed

SLO lần #2 (duplicate):
  app-71 vẫn INVALIDATED
  app-103 (phiên mới) vẫn ACTIVE
~~~

Lần hai **không được**:
- tạo session mới,
- hủy mọi session có username `alice`,
- hủy phiên vừa được user đăng nhập lại bằng ST-C,
- cấp/khôi phục Authentication,
- thực hiện hành động nghiệp vụ khác không thể idempotent,
- coi một `IllegalStateException` do session đã bị invalidated là lý do bật lại auth.

### 6.3. Hai mức độ kết quả

Cần phân biệt **trạng thái phiên** với **trạng thái xử lý event**:

| Kết quả | Ý nghĩa | Có nên làm gì? |
| --- | --- | --- |
| `INVALIDATED_NOW` | Tìm đúng phiên đang hoạt động và vừa hủy. | Ghi success, dọn mapping, metric. |
| `ALREADY_INVALIDATED` | Cùng ticket đã hủy trước đó. | Không hủy lại; ghi duplicate metric mức thấp. |
| `ALREADY_EXPIRED` | Phiên đã hết hạn trước notification. | Không tạo session, không báo lỗi hệ thống. |
| `ALREADY_LOGGED_OUT` | Người dùng đã local logout trước. | Không “undo”, coi đã kết thúc local. |
| `NOT_FOUND` | Không tìm được mapping ticket→session. | Không đoán; điều tra nếu tỷ lệ bất thường. |
| `INVALID_NOTIFICATION` | Nguồn/cấu trúc/binding không tin. | Reject, cảnh báo an ninh khi cần. |
| `PROCESSING_FAILURE` | Có session nhưng backend/session store lỗi khi hủy. | Alert/reconciliation; **không nói đã hủy thành công**. |

`NOT_FOUND` không được diễn giải thành `ALREADY_INVALIDATED` một cách chắc chắn, trừ khi có **tombstone/audit** đủ bằng chứng cho ticket tương ứng. Thay vào đó ghi “không tìm thấy mapping; không có tác động local được xác minh”.

### 6.4. HttpSession.invalidate có thể ném IllegalStateException

Trên Java Servlet, `HttpSession.invalidate()` có thể ném `IllegalStateException` khi phiên đã bị vô hiệu hóa. Trong race giữa timeout, local logout và CAS SLO, một implementation có thể gặp trường hợp này.

Cách xử lý:
1. Xác nhận sự kiện SLO là hợp lệ và mapping thuộc đúng session.
2. Dùng cơ chế atomic claim/state transition nếu tự viết store.
3. Khi thao tác invalidate báo session đã vô hiệu, **không thử khôi phục**; xác nhận qua session store nếu cần.
4. Không che các exception khác (DB/Redis unavailable, network partition) dưới nhãn “already invalidated”.
5. Không reissue cookie session cho callback.
6. Không leak SessionIndex hoặc ticket raw trong log.

Bộ lọc Apereo có sẵn cơ chế xử lý SLO; **không thay bằng một handler tự viết** nếu chưa hiểu source của version đã triển khai. Nếu cần idempotency cao hơn và audit chuyên biệt, bọc ở control plane/store được kiểm thử, không sửa format CAS XML tùy tiện.

## 7. Phiên đã hết hạn trước khi nhận SLO

### 7.1. Thứ tự sự kiện phổ biến

~~~text
T0  Portal xác thực ST-A -> tạo HttpSession app-71.
T1  Người dùng không hoạt động, app-71 hết idle timeout.
T2  Servlet container phát sessionDestroyed; CAS listener dọn mapping ST-A.
T3  CAS TGT kết thúc và gửi logoutRequest(SessionIndex=ST-A).
T4  Filter không tìm thấy mapping ST-A.
~~~

Với T0–T4, **không cần hủy lại app-71**: nó đã hết hạn. Nếu listener hoạt động đúng, `NOT_FOUND` sau timeout là một kết quả dự kiến.

Nhưng T4 **không tự cho phép kết luận** tất cả phiên của cùng user đã kết thúc: người này có thể có **một local session khác**, một tenant khác hoặc một lần login mới. CAS notification theo ticket cũ không được dùng như lệnh xóa mọi phiên trùng NameID.

### 7.2. Local logout trước SLO

~~~text
T0  User POST /logout tại Portal.
T1  Spring LogoutFilter invalidate app-71.
T2  SingleSignOutHttpSessionListener dọn ST-A -> app-71.
T3  User lựa chọn logout CAS tại https://cas.example/cas/logout.
T4  CAS gửi thông báo ST-A; Portal không còn mapping.
~~~

Tại T4, event không tìm thấy phiên là **hợp lý**. Điều cần kiểm tra là phiên ở T1 đã được hủy thật, chứ không phải ép listener giữ mapping mãi để lần sau có thể hủy lại.

### 7.3. Session đã bị GC/dọn nhưng mapping còn sót

Nếu listener không được đăng ký hoặc phiên bị xóa trong distributed session store không phát callback tương ứng, mapping có thể bị stale:
- Ticket vẫn trỏ tới session đã bị hủy hoặc không tìm được.
- Map in-memory giữ strong references tới HttpSession, tăng memory leak.
- SLO handler có thể gặp IllegalStateException.
- Sau nhiều tháng, metrics báo số “active ticket mappings” sai.

Cần có **cleanup theo session lifecycle/TTL**, metrics về mapping age và test session timeout thật, không chỉ test gọi logout thủ công.

### 7.4. Tombstones có giới hạn

Nếu nghiệp vụ cần phân biệt duplicate với unknown, có thể giữ **tombstone có TTL** theo khóa ticket đã hash/được bảo vệ:

~~~text
(approvedCasRealm, serviceRegistration, ticketHash)
 -> state = ENDED_BY_SLO
 -> endedAt, generation
 -> expiresAt = endedAt + shortRetention
~~~

Tombstone giúp ghi nhận duplicate mà không phải giữ `HttpSession` sống mãi. TTL phải gắn với latency/retry window và privacy retention policy, giới hạn kích thước và chỉ lưu thông tin tối thiểu. **Không được dựa tombstone vô hạn như một hệ thống đăng nhập**.

## 8. Thông báo cũ không được xóa phiên đăng nhập mới

### 8.1. Tình huống

~~~text
T0  Alice login -> ST-A -> session app-71.
T1  app-71 logout local, mapping ST-A kết thúc.
T2  Alice login lại -> ST-C -> session app-103.
T3  CAS gửi SLO muộn cho ST-A.
~~~

**Đúng:** chỉ đánh giá ST-A; app-103 vẫn hoạt động trừ khi nó có chính sách thu hồi riêng. **Sai:** dùng `NameID=alice` rồi hủy session hiện tại của alice bất kể ST.

Giữ khóa correlation có **source scope và generation**:

~~~text
CAS realm: cas-partner-A
Service: https://portal.example/login/cas
Ticket: ST-A
Session generation: app-71-created-at-T0

Event ST-A -> tìm app-71, không đụng app-103
~~~

Nếu CAS muốn logout toàn bộ session theo TGT, mỗi service ticket/phiên phải được quản lý theo hợp đồng với CAS. Một thông báo về ST-A **không tự cấp phép** SP hủy cả các phiên khác chỉ vì username giống nhau.

### 8.2. Race khi logout cũ tới đồng thời login mới

Trong multi-thread/multi-node:

- Callback SLO cũ bắt đầu tra mapping ST-A.
- Login mới đang tạo session B và mapping ST-B.
- Nếu implementation lưu `Map<username, HttpSession>`, callback cũ có thể trỏ nhầm session B.
- Nếu lưu `Map<realm+ticket, sessionGeneration>` và atomic state, callback chỉ xử lý phiên đúng.

Hãy chọn một **khóa không dựa username**. Dữ liệu user name phục vụ audit sau masking, không phải khóa SLO duy nhất.

## 9. Sự cố mạng: phân biệt delivery và hiệu lực logout

### 9.1. CAS không kết nối được SP

Các nguyên nhân phổ biến:

- DNS của service callback sai, chứng thư TLS hết hạn hoặc CA không tin.
- Firewall/NAT/ingress không cho CAS server tới SP.
- Load balancer hết backend hoặc trả 502/503.
- Endpoint SLO URL được cấu hình theo host nội bộ thay vì URL CAS server truy cập được.
- Session store của SP đang lỗi, không thể invalidate session.
- Proxy chặn POST body hoặc đổi content type/encoding.
- CAS timeout trước khi SP hoàn tất, nhưng SP **có thể đã hủy session**.

Theo CAS Protocol, CAS server có thể **bỏ qua lỗi SLO POST** để bảo vệ availability. Vì vậy **CAS logout thành công không phải distributed transaction cam kết SP đã logout**.

### 9.2. Ma trận bốn kết quả network

| Kịch bản | CAS thấy gì? | SP thấy gì? | Có thể kết luận? |
| --- | --- | --- | --- |
| Callback nhận/đã hủy, CAS nhận 2xx | Gửi thành công. | Hủy đúng session. | SP local ended **nếu backend đã xác nhận**. |
| Callback hủy xong nhưng response HTTP mất | CAS timeout, có thể retry tùy cấu hình. | Session đã kết thúc. | Duplicate sau retry là bình thường. |
| CAS không kết nối được tới SP | Network failure. | Không hề nhận notification. | Phiên local **có thể vẫn còn**. |
| SP nhận callback nhưng session store lỗi | Có thể thấy 5xx/timeout. | Không xác nhận hủy thành công. | Cần alert/reconcile, **không nói success**. |
| SP nhận duplicate sau khi mapping đã dọn | Có thể 2xx nếu xử lý idempotent. | Không có session mới bị hủy. | Event đã được xử lý ở mức endpoint, không chứng minh toàn federation. |

**Cảnh báo:** HTTP 2xx có thể chỉ nghĩa CAS client filter đã nhận và xử lý notification hợp lệ theo khả năng local. Nó **không phải** bằng chứng các SP khác đã logout.

### 9.3. Nên trả HTTP status gì?

- **2xx:** notification hợp lệ, xử lý hoàn tất hoặc session đã xác nhận kết thúc/đã xử lý idempotent.
- **4xx:** notification sai định dạng, nguồn không tin hoặc thiếu thông tin bắt buộc; tránh tiết lộ lý do chi tiết cho attacker.
- **5xx:** có lỗi server thật khiến không thể xác nhận invalidation, ví dụ session store unavailable.
- **Unknown mapping:** cân nhắc 2xx sau kiểm tra nguồn và quy trình idempotent nếu phù hợp CAS client; **không gắn nhãn đã invalidate** khi chưa có bằng chứng. Nếu chính sách muốn điều tra, metric/audit tách biệt.

CAS client filter có thể tự quyết định status; **không ép status thủ công bằng custom Controller** nếu làm hỏng filter behavior. Không dùng status code để thay cho audit “phiên nào thực sự đã kết thúc”.

### 9.4. Có nên retry SLO?

CAS protocol không bắt buộc guaranteed retries. Nếu tổ chức thêm queue/retry vào control plane:

1. Bảo toàn **original event ID/ticket scope**, không tạo giả một session ID mới.
2. Chỉ retry khi delivery/processing failure có thể phục hồi, với exponential backoff/jitter và giới hạn.
3. Receiver vẫn phải idempotent dù producer nghĩ đã loại trùng.
4. Event quá cũ phải tuân TTL/retention policy, không tác động session mới.
5. Không gửi lại raw ticket/XML tới logging/third-party queue thiếu bảo vệ.
6. Có DLQ/dead-letter và cảnh báo; **không hứa exactly once** khi không có transaction end-to-end.
7. Nếu sự kiện đến sau khi app session timeout, coi đã kết thúc local khi có bằng chứng session expired.
8. Tránh dùng network retries để gọi lại **CAS /serviceValidate** bằng ST cũ: đó là một thao tác khác, ST chỉ validate một lần.

## 10. Bảo vệ endpoint nhận CAS SLO

### 10.1. Vì sao cần trust boundary?

Mẫu CAS SLO phổ biến chứa XML kiểu SAML nhưng **không nên tự giả định mọi thông báo đã có chữ ký XML được framework xác minh**. Các bản CAS client/filter triển khai cơ chế mapping riêng. Nếu endpoint công khai chấp nhận yêu cầu tùy ý chỉ vì có `logoutRequest` và một SessionIndex đúng, attacker có thể cố đoán/lấy ST và kích hoạt logout không mong muốn.

**Biện pháp phòng vệ theo deployment:**

- Đặt CAS SLO receiver trong route đúng service và chỉ nhận từ các mạng/identity CAS được phép khi dùng back-channel.
- Dùng **HTTPS**, xác minh host và certificate; xem xét **mTLS** hoặc authenticated gateway khi CAS và SP hỗ trợ.
- Không tin `X-Forwarded-For`/`X-Real-IP` trừ khi ingress tự set và xóa header do client đưa.
- Tách back-channel và front-channel chính sách access; front-channel không thể giả định source IP của CAS server.
- Nếu contract có **signed CAS SLO messages**, xác minh chữ ký theo profile/trust anchors thật; không giả định có chữ ký khi chỉ nhìn tên phần tử `samlp:LogoutRequest`.
- Giới hạn body/timeout, parser chống XXE và xử lý URL-encoded field đúng encoding; ưu tiên Apereo filter đã cập nhật.
- Không dựng XML parser thủ công rồi gọi `session.invalidate()` từ `NameID`.
- Áp rate limit và telemetry, nhưng tránh để rate limiter loại nhầm CAS thật trong một sự kiện logout toàn công ty.
- Không biến callback thành endpoint đăng nhập, không tạo local Authentication khi nhận `logoutRequest`.
- Log hashed ticket/approved realm/service, không ghi raw ST, NameID hay SessionIndex.

### 10.2. Cẩn thận với CSRF

CAS SLO back-channel không có CSRF token của browser app. Nếu đặt filter trong Spring Security chain sau `CsrfFilter`, thông báo POST hợp lệ có thể nhận 403. Giải pháp là đặt **CAS SingleSignOutFilter đúng thứ tự trong Servlet/security filters** hoặc cấu hình matcher ngoại lệ **chỉ** cho callback protocol đã được xác thực qua kênh riêng.

**Không tắt CSRF toàn ứng dụng** chỉ để CAS SLO hoạt động: browser forms của Portal vẫn cần chống CSRF. Đồng thời, CSRF exemption **không** làm SLO notification trở nên đáng tin; source/binding validation vẫn bắt buộc.

### 10.3. Không tin Content-Type và HTTP 200 một cách mù quáng

- CAS có thể gửi `application/x-www-form-urlencoded` với field `logoutRequest`; reverse proxy phải cho body đi qua nguyên vẹn.
- Một filter khác có thể consume request body trước CAS filter; thứ tự filter quan trọng.
- HTTP 200 từ proxy cache/custom health endpoint **không chứng minh** CAS handler đã chạy.
- Nếu endpoint bị redirect 302 tới CAS login vì authorization rule, SLO đã không được xử lý dù proxy log có request.
- Không tạo MVC Controller `@PostMapping("/login/cas")` nhận logoutRequest rồi trả 200 mà không hủy phiên.

## 11. Multi-node: session mapping nằm ở đâu?

### 11.1. In-memory map không tự chia sẻ giữa các node

~~~text
CAS -> Load Balancer -> Node A:
       ST-A -> HttpSession app-71  (local map A)

CAS -> Load Balancer -> Node B:
       SLO SessionIndex=ST-A
       local map B: không thấy ST-A
       => không thể tìm app-71
~~~

Spring Security reference trình bày Java CAS client `SingleSignOutFilter` dùng một map local để tìm phiên. **Đừng mặc định** khi triển khai nhiều JVM hoặc dùng Spring Session/Redis, map CAS SLO tự trở thành distributed; chúng là hai loại storage khác nhau.

Nếu callback đến Node B nhưng mapping chỉ ở Node A, có thể báo `NOT_FOUND` dù app-71 còn active. Đây là rủi ro **SLO không đầy đủ**, không chỉ vấn đề log ồn.

### 11.2. Các cách vận hành

| Thiết kế | Ưu điểm | Giới hạn / phải test |
| --- | --- | --- |
| Sticky routing cho callback và login | Giảm mismatch node trong một số hạ tầng. | Back-channel từ CAS server **không có browser cookie**, sticky dựa cookie có thể vô hiệu. |
| Tất cả SLO routed tới đúng service instance | Tương đối đơn giản khi mapping biết origin. | Cần routing contract đáng tin, không suy node từ client-controlled header. |
| Shared session + shared ticket/session mapping | Callback đến node nào cũng tìm đúng target session. | Cần triển khai `SessionMappingStorage` tương thích; TTL/atomic claims/security. |
| Event bus fan-out tới các nodes | Có thể tìm mapping tại node đã tạo session. | Cần auth nội bộ, idempotency, retries, backpressure và reconciliation. |
| Local session timeout ngắn + SLO best-effort | Giảm thời gian phiên sót lại. | Không đảm bảo chấm dứt ngay; đánh đổi trải nghiệm. |

**Quan trọng:** lưu `HttpSession` Java object trong Redis không phải chiến lược đúng cho mọi Servlet container. Thường nên lưu **ticket → session ID/store key** tương thích session manager và dùng API được hỗ trợ để invalidate session trên node khác, kiểm tra serialization và lifecycle.

### 11.3. Số lượng mapping và memory

Một JVM có thể phục vụ hàng trăm nghìn sessions; nếu mapping không được dọn:
- Memory leak và GC pauses.
- Lookup stale sessions khiến duplicate trông như lỗi.
- User logout local nhưng mapping vẫn tham chiếu object.
- Node rolling restart mất mapping, callback sau đó bị miss.

Đăng ký `SingleSignOutHttpSessionListener` đúng môi trường, kiểm tra lifecycle `sessionDestroyed`, có cleanup orphan mappings, map size gauge và alert. Nếu dùng distributed store, cũng cần TTL/cleanup và consistency test.

### 11.4. Session rotation và correlation

Spring Security có thể thay Servlet session ID sau CAS login để chống session fixation. Mapping CAS client phải tiếp tục trỏ đúng **session object/lifecycle** hoặc session store key mới sau rotation.

Không tự giữ `Map<ST, oldJSESSIONID>` rồi dùng ID cũ để vô hiệu session sau rotation mà chưa test. Nếu app dùng Spring Session hoặc custom session strategies, cần test CAS SLO **sau khi session ID thay đổi**.

## 12. Session và CAS ticket là hai hệ thống có quyền thu hồi riêng

### 12.1. Local logout

~~~text
Browser -- POST /logout --> Portal
                              |
                              +-- Spring Security LogoutFilter
                              +-- clear Authentication
                              +-- invalidate HttpSession
                              +-- listener removes ST mapping
                              |
                         CAS TGT/TGC có thể còn
~~~

Local logout chỉ kết thúc Portal session. Nếu CAS TGT còn sống, mở trang bảo vệ có thể nhận **ST mới** và SSO lại ngay. Đây không chứng minh local logout không hoạt động.

### 12.2. CAS logout

~~~text
Browser -- CAS /logout --> CAS invalidates TGT
                                 |
                                 +-- best-effort notify Orders
                                 +-- best-effort notify Reports
                                 +-- other services per CAS profile
~~~

Nếu Orders nhận và xử lý thông báo đúng, local session kết thúc. Nếu không, CAS không có khả năng trực tiếp xóa cookie/session store của Orders chỉ bằng cách hủy TGT.

### 12.3. Local account disable/revoke

Đội bảo mật có thể disable user trong Portal ngay khi CAS SSO vẫn đang hoạt động. Ứng dụng phải thực thi policy nội bộ bằng account status, authorization check, session revocation hoặc deny list. **Không chỉ dựa CAS SLO để thu hồi quyền khẩn cấp** vì callback có thể mất.

### 12.4. Stateless clients

Ứng dụng **không dùng HttpSession** có thể sử dụng proxy ticket + `StatelessTicketCache`. CAS SLO thông dụng vốn dùng mapping ST→HttpSession để invalidate local session, nên **không tự xóa cache PT** và không tự revoke OAuth/JWT/opaque tokens của ứng dụng khác.

Nếu API dùng stateless authentication cache, phải có chính sách expiry/eviction/revocation riêng, không coi listener của HttpSession là giải pháp đủ.

## 13. State machine để vận hành sự kiện SLO

~~~text
LOGIN_VALIDATED
      |
      v
MAPPED_ACTIVE <------------------------------ CAS ticket correlated to session
      |
      +----> LOCAL_LOGOUT ---------> ENDED_LOCAL
      |
      +----> SESSION_TIMEOUT ------> ENDED_EXPIRED
      |
      +----> CAS_NOTIFICATION
                 |
                 +--> valid source and mapping -> ATOMIC_INVALIDATE -> ENDED_SLO
                 |
                 +--> duplicate of ended      -> NOOP_ALREADY_ENDED
                 |
                 +--> no mapping              -> NOT_FOUND / INVESTIGATE
                 |
                 +--> malformed/untrusted     -> REJECT_INVALID
                 |
                 +--> backend store failed    -> PROCESSING_FAILURE
      |
      +----> CAS notification never delivered -> MAY_REMAIN_ACTIVE
~~~

**Không thiết kế một cạnh** `ENDED_SLO → ACTIVE` vì retry thành công; đăng nhập mới phải tạo **ticket/session generation mới**. Một thông báo cũ không được gắn với session mới chỉ nhờ username.

### 13.1. HTTP outcome khác business outcome

Một mô hình audit có thể ghi:
- `DELIVERED`: HTTP endpoint nhận request.
- `VERIFIED`: endpoint xác nhận nguồn/binding/payload đúng chính sách.
- `CORRELATED`: tìm thấy ánh xạ ticket→session.
- `INVALIDATED`: session store xác nhận phiên target bị hủy.
- `NOOP_ALREADY_ENDED`: mapping/tombstone chứng minh đã kết thúc.
- `NO_MAPPING`: không đủ bằng chứng session target tồn tại.
- `PROCESSING_FAILED`: lỗi thật.

Một CAS server báo đã gửi thông báo chỉ chứng minh `DELIVERY_ATTEMPTED`, không chứng minh `INVALIDATED`.

## 14. Java 17 chạy độc lập: mô phỏng idempotency và thông báo tới trễ

Ví dụ này **không gọi CAS thật, không xử lý XML, không có HttpSession thật**. Nó mô phỏng correlation theo `CAS realm + service ticket`, trạng thái phiên và kết quả khi một notification bị gửi lặp. Không dùng mô phỏng để thay Java CAS Client hoặc cơ chế xác minh source trong production.

### 14.1. Tệp `CasSloIdempotencyDemo.java`

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

public class CasSloIdempotencyDemo {

    enum State {
        ACTIVE,
        ENDED_BY_SLO,
        ENDED_BY_TIMEOUT,
        ENDED_LOCALLY
    }

    enum Outcome {
        INVALIDATED_NOW,
        ALREADY_INVALIDATED,
        ALREADY_EXPIRED,
        ALREADY_LOGGED_OUT,
        NO_MAPPING
    }

    record TicketKey(String casRealm, String serviceTicket) {
    }

    static final class SessionRef {
        final String sessionGeneration;
        final AtomicReference<State> state =
            new AtomicReference<>(State.ACTIVE);

        SessionRef(String sessionGeneration) {
            this.sessionGeneration = sessionGeneration;
        }

        State current() {
            return state.get();
        }

        void expire() {
            state.compareAndSet(State.ACTIVE, State.ENDED_BY_TIMEOUT);
        }

        void logoutLocal() {
            state.compareAndSet(State.ACTIVE, State.ENDED_LOCALLY);
        }
    }

    static final class App {
        final Map<TicketKey, SessionRef> mapping =
            new ConcurrentHashMap<>();

        void register(
                String realm,
                String ticket,
                SessionRef session) {
            mapping.put(new TicketKey(realm, ticket), session);
        }

        Outcome onCasLogout(String realm, String ticket) {
            SessionRef target =
                mapping.get(new TicketKey(realm, ticket));

            if (target == null) {
                return Outcome.NO_MAPPING;
            }

            State previous = target.state.getAndUpdate(
                current -> current == State.ACTIVE
                    ? State.ENDED_BY_SLO
                    : current
            );

            return switch (previous) {
                case ACTIVE -> Outcome.INVALIDATED_NOW;
                case ENDED_BY_SLO -> Outcome.ALREADY_INVALIDATED;
                case ENDED_BY_TIMEOUT -> Outcome.ALREADY_EXPIRED;
                case ENDED_LOCALLY -> Outcome.ALREADY_LOGGED_OUT;
            };
        }
    }

    public static void main(String[] args) {
        App app = new App();

        SessionRef old =
            new SessionRef("app-71-generation-1");
        SessionRef renewed =
            new SessionRef("app-103-generation-2");
        SessionRef expired =
            new SessionRef("app-55-generation-1");
        SessionRef local =
            new SessionRef("app-66-generation-1");
        SessionRef networkLost =
            new SessionRef("app-88-generation-1");

        app.register("cas-A", "ST-A", old);
        app.register("cas-A", "ST-C", renewed);
        app.register("cas-A", "ST-EXPIRED", expired);
        app.register("cas-A", "ST-LOCAL", local);
        app.register("cas-A", "ST-NETWORK", networkLost);

        expired.expire();
        local.logoutLocal();

        System.out.println("first=" +
            app.onCasLogout("cas-A", "ST-A"));
        System.out.println("duplicate=" +
            app.onCasLogout("cas-A", "ST-A"));
        System.out.println("expired=" +
            app.onCasLogout("cas-A", "ST-EXPIRED"));
        System.out.println("local=" +
            app.onCasLogout("cas-A", "ST-LOCAL"));
        System.out.println("unknown=" +
            app.onCasLogout("cas-A", "ST-OTHER"));

        // CAS gửi sự kiện ST-A muộn; không nhắm vào session mới ST-C.
        System.out.println("lateOld=" +
            app.onCasLogout("cas-A", "ST-A"));
        System.out.println("newSession=" + renewed.current());

        // Một notification không đến do lỗi mạng: không có hàm
        // onCasLogout nào chạy cho ticket ST-NETWORK.
        System.out.println("networkLossSession=" +
            networkLost.current());

        // Cùng ticket string nhưng realm khác: không được tra chéo.
        System.out.println("wrongRealm=" +
            app.onCasLogout("cas-B", "ST-A"));

        System.out.println("otherTicket=" +
            app.onCasLogout("cas-A", "ST-C"));
        System.out.println("newAfterItsOwnLogout=" +
            renewed.current());
    }
}
~~~

### 14.2. Biên dịch và chạy

Với JDK 17+:

~~~bash
javac --release 17 CasSloIdempotencyDemo.java
java CasSloIdempotencyDemo
~~~

**Stdout xác định:**

~~~text
first=INVALIDATED_NOW
duplicate=ALREADY_INVALIDATED
expired=ALREADY_EXPIRED
local=ALREADY_LOGGED_OUT
unknown=NO_MAPPING
lateOld=ALREADY_INVALIDATED
newSession=ACTIVE
networkLossSession=ACTIVE
wrongRealm=NO_MAPPING
otherTicket=INVALIDATED_NOW
newAfterItsOwnLogout=ENDED_BY_SLO
~~~

### 14.3. Giải thích kết quả

- `first`: session cũ active vừa bị chuyển sang trạng thái ended.
- `duplicate`: cùng event không hủy lại session.
- `expired`: phiên target đã hết hạn, SLO là no-op an toàn.
- `local`: người dùng đã local logout trước, không phục hồi.
- `unknown`: không tìm được mapping, **không suy chắc session đã hủy**.
- `lateOld` và `newSession`: notification của ST-A không động vào session mới ST-C.
- `networkLossSession`: không có callback đồng nghĩa app session có thể vẫn ACTIVE.
- `wrongRealm`: ticket giống chuỗi nhưng CAS realm khác không được tra chéo.
- `otherTicket`: session mới chỉ bị hủy khi có thông báo **đúng ST-C**.
- `AtomicReference.getAndUpdate` mô phỏng atomic state transition trong **một JVM**, không có CAS XML signature, TLS, session store hay mạng.
- Bài demo giữ toàn bộ mappings để hiển thị duplicate. **Production phải dọn map/tombstones theo TTL và listener**, không giữ reference vô hạn.

### 14.4. Những gì code không thay thế

- Không thay `SingleSignOutFilter` của Apereo để parse/nhận notification.
- Không chứng minh source CAS đáng tin hoặc XML được ký.
- Không gọi `HttpSession.invalidate()` thật; trạng thái ended chỉ mô phỏng.
- Không xử lý distributed transactions giữa nhiều API nodes.
- Không tự bảo đảm CAS có retries hoặc delivery guarantee.
- Không tự xóa session ở các thiết bị/ứng dụng khác.

Tách **mô phỏng kiểm soát** khỏi **tích hợp CAS thực tế** là điều quan trọng; một test Java với map không thể chứng minh SLO production hoạt động qua load balancer.

## 15. Spring Boot 3.3 / Spring Security 6.3: cấu hình tích hợp SLO đúng chỗ

### 15.1. Bức tranh dependency và filter order

CAS integration của Spring Security dùng `spring-security-cas`; Apereo Java CAS Client mang các lớp `SingleSignOutFilter` và `SingleSignOutHttpSessionListener`. Trước khi triển khai, phải xác nhận CAS client artifact thực sự tương thích Servlet API của ứng dụng.

Mô hình flow:

~~~text
Servlet Container
    |
    +-- CharacterEncodingFilter (UTF-8)
    |
    +-- Apereo SingleSignOutFilter (nhận/stores ticket và SLO)
    |
    +-- Spring Security FilterChainProxy
          |
          +-- CsrfFilter/browser policy
          +-- CasAuthenticationFilter
          +-- LogoutFilter
          +-- AuthorizationFilter
    |
    +-- Controller/business endpoints
~~~

Đây là **sơ đồ thứ tự mong muốn**, không khẳng định mọi dự án tự có các filter trên chỉ bằng thêm một dependency. Nếu đặt Apereo filter ở Servlet container thì **không thêm lại cùng instance vào Spring Security chain**. Nếu tích hợp qua Spring chain thì phải đặt đúng thứ tự và tránh Spring Boot auto-register filter hai lần.

### 15.2. Gradle dependency gợi ý

`settings.gradle`:

~~~groovy
rootProject.name = 'cas-slo-demo'
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
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'
}
~~~

`spring-security-cas` được dùng cho CAS login; Apereo CAS client là dependency nền của module ở các bản tương ứng. **Kiểm tra dependency tree và loại Servlet namespace** (Jakarta vs Javax) trước khi chọn bản CAS client bổ sung hoặc bật SLO. Cấu hình chỉ là skeleton: không có CAS server, user mapping và service registry, ứng dụng không thể chứng minh SLO thật.

### 15.3. Java config cho CAS SLO Filter/Listener

Đoạn sau là **mảnh Spring Boot servlet-registration minh họa**, không phải `SecurityFilterChain` đầy đủ:

~~~java
package com.example.casslo;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSingleLogoutServletConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilter() {
        SingleSignOutFilter filter = new SingleSignOutFilter();
        FilterRegistrationBean<SingleSignOutFilter> registration =
            new FilterRegistrationBean<>(filter);

        registration.setName("casSingleSignOutFilter");
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
~~~

**Lưu ý bắt buộc:**

- Class Apereo phải thuộc **bản tương thích** với Spring Boot 3.x/Jakarta Servlet. Nếu version thiếu constructor/API hoặc còn dùng `javax.servlet`, không “ép compile” bằng cách trộn jar; cần chọn phiên bản tương thích theo dependency insight.
- Bộ lọc này đặt ở **Servlet chain**, trước `springSecurityFilterChain` theo ordering đã được kiểm chứng. Không đăng ký cùng filter một lần nữa qua `http.addFilterBefore(...)`.
- CAS SLO filter cần thấy callback từ CAS, gồm `logoutRequest` và ticket ở luồng login. Nếu app routing/proxy chỉ cho `/login/cas` nhưng thực tế CAS POST khác URL, cần chỉnh theo service registry/callback contract.
- `SingleSignOutHttpSessionListener` cần nhận đúng sự kiện `sessionDestroyed`/expiration của session manager đang dùng.
- Bản code chưa cấu hình CAS authentication provider, login filter hoặc local user/tenant mapping; các phần này phải được triển khai theo tài liệu CAS login.
- **Filter order số học chỉ là ví dụ**; hãy kiểm tra actual servlet filter registrations trong môi trường chạy, nhất là `CharacterEncodingFilter` và Spring Security.
- Không dùng `@Bean SingleSignOutFilter` đồng thời với `FilterRegistrationBean` khác gây servlet auto-registration hai lần.

### 15.4. Spring Security local logout phải giữ riêng

Mảnh DSL cho local logout:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/signed-out", "/error").permitAll()
        .anyRequest().authenticated()
    )
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/signed-out")
        .invalidateHttpSession(true)
        .clearAuthentication(true)
    );
~~~

`POST /logout` xử lý **local** session. Nếu muốn người dùng đăng xuất CAS toàn federation, cần điều hướng có chủ đích tới CAS server `/logout` qua URL cấu hình đáng tin sau local logout; **không** nhận `casLogoutUrl` do browser tùy ý cung cấp.

SLO notification từ CAS **không phải** browser local logout form: nó không có CSRF token của Portal, và handler phù hợp phải nhận đúng giao thức mà vẫn giữ CSRF protection ở những endpoint ứng dụng dựa cookie.

### 15.5. Kiểm tra sự thật bằng test, không chỉ bằng bean registration

Một ứng dụng có `SingleSignOutFilter` và `SingleSignOutHttpSessionListener` **chưa chắc SLO đúng** nếu:
- Filter không chạy trên path CAS đang POST.
- CAS client tạo mapping trước khi session thực sự được xác thực.
- Local session ID luân chuyển sau login nhưng mapping không cập nhật.
- Filter bị đặt sau security authorization và nhận 302/403.
- Container tạo hai filter instances vì đăng ký trùng.
- Multi-node callback tới sai node với local map.
- Session store/listener không đồng nhất, cleanup events bị mất.
- CAS server không hỗ trợ/không gửi SLO cho service đã đăng ký.
- Network ingress từ CAS tới callback bị chặn.

Bài lab phải dùng CAS test thật hoặc integration harness có kiểm soát; không gửi payload không xác minh vào production.

## 16. Thiết kế distributed mapping khi chạy nhiều node

Nếu không thể rely on local CAS client mapping, có thể thiết kế một **lớp quản lý SLO state** được kiểm thử, vẫn dùng CAS client parsing/trust policy. Schema tham khảo:

~~~sql
CREATE TABLE cas_slo_session_binding (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cas_realm_id VARCHAR(80) NOT NULL,
    service_id VARCHAR(120) NOT NULL,
    service_ticket_hash VARCHAR(128) NOT NULL,
    session_store_key VARCHAR(200) NOT NULL,
    session_generation VARCHAR(120) NOT NULL,
    state VARCHAR(24) NOT NULL CHECK (
        state IN ('ACTIVE', 'ENDED_SLO', 'ENDED_LOCAL', 'EXPIRED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE (cas_realm_id, service_id, service_ticket_hash)
);
CREATE INDEX cas_slo_active_expires
    ON cas_slo_session_binding (expires_at)
    WHERE state = 'ACTIVE';
~~~

**Đây là dữ liệu quản trị phụ trợ**, không phải implementation `SessionMappingStorage` có thể gắn ngay cho Apereo client. Phải đối chiếu API của client/session manager; một SQL record không tự cho phép invalidate một HttpSession trên JVM khác.

### 16.1. Atomic state transition

~~~sql
-- Chỉ gọi sau khi CAS notification đã qua trust/parser checks.
UPDATE cas_slo_session_binding
SET state = 'ENDED_SLO',
    ended_at = CURRENT_TIMESTAMP
WHERE cas_realm_id = :approved_realm
  AND service_id = :approved_service
  AND service_ticket_hash = :ticket_hash
  AND state = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Một update affected-row=1 có thể giúp xử lý duplicate, **nhưng chưa đồng nghĩa HttpSession đã bị invalidate**. Cần thiết kế chuỗi/transaction/outbox giữa mapping state và actual session-store revocation, tránh đánh dấu ENDED rồi fail khi xóa session.

### 16.2. Mô hình trạng thái hai pha an toàn hơn

~~~text
ACTIVE
  |
  | atomic claim
  v
REVOCATION_PENDING
  |
  +-- session store confirms invalidated --> ENDED_SLO
  |
  +-- transient store failure -----------> RETRYABLE_FAILURE
  |
  +-- session already gone -------------> ENDED_EXPIRED/ENDED_LOCAL
~~~

Một worker nội bộ có thể retry `REVOCATION_PENDING` với backoff, nhờ thao tác vô hiệu session idempotent và không cấp quyền cho session đã bị đánh dấu pending. Thiết kế này phức tạp hơn; không yêu cầu cho mọi Portal nhỏ.

### 16.3. Ticket hash và privacy

Service ticket là credential nhạy cảm; nếu phải lưu mapping trong DB:
- Dùng hash/keyed digest phù hợp threat model, tránh raw ticket trong logs.
- Chỉ lưu CAS realm/registered service do admin duyệt; không nhận từ request.
- Dùng unique constraint/TTL và purge records đã kết thúc.
- Không lưu NameID, email, full XML và SessionIndex raw trong metric labels.
- Hạn chế quyền truy vấn, bảo vệ backups và audit khi đọc dữ liệu correlation.

## 17. Monitoring, metrics và cảnh báo

### 17.1. Metric đề xuất

~~~text
cas_slo_notification_received_total{realm,service,channel}
cas_slo_notification_rejected_total{realm,reason_class}
cas_slo_session_invalidated_total{realm,service}
cas_slo_already_ended_total{realm,reason}
cas_slo_mapping_not_found_total{realm,service}
cas_slo_session_store_failure_total{service}
cas_slo_delivery_http_failure_total{service,status_class}
cas_slo_pending_revocation_age_seconds{service}
cas_slo_binding_active_count{service}
cas_slo_binding_expired_cleanup_total{service}
cas_slo_late_event_total{realm,service}
~~~

Đây **không phải metric tự có** trong Spring Security/Apereo CAS. Instrument tại đúng layer và giữ label cardinality thấp; không dùng service ticket, session ID, NameID, email hay raw XML làm label.

### 17.2. Logging phù hợp

Ví dụ event có cấu trúc, không lộ raw ticket:

~~~text
event=cas_slo_received
cas_realm=partner-a
service=orders-portal
channel=BACK_CHANNEL
ticket_hash_prefix=7c28...
received_at=2030-05-01T10:00:01Z

event=cas_slo_result
cas_realm=partner-a
service=orders-portal
result=ALREADY_EXPIRED
session_generation_ref=opaque-ref
duration_ms=7
~~~

Không ghi `logoutRequest` XML gốc hoặc TGC/TGT/ST vào log; các giá trị này có thể là credential hoặc PII và tạo nguy cơ replay/khai thác.

### 17.3. Các alert hữu ích

| Biểu hiện | Giả thuyết | Hành động |
| --- | --- | --- |
| `NOT_FOUND` tăng đột biến | Callback sai node, listener dọn quá sớm, session timeout ngắn, mapping restart. | So khớp node routing/session mapping và tuổi sự kiện. |
| `ALREADY_INVALIDATED` tăng | CAS/proxy retry hoặc duplicate queue. | Kiểm tra delivery/backoff, xác nhận không gây tác dụng phụ. |
| Callback không thấy trong một CAS logout test | Ingress, DNS, TLS, service URL hoặc CAS không bật SLO. | Kiểm tra CAS SLO logs và SP ingress; không assume logout completed. |
| SLO 403 | CSRF/authorization filter chặn trước CAS filter. | Sửa order/matcher; không tắt CSRF toàn ứng dụng. |
| SLO 302 tới CAS login | Callback bị đối xử như protected browser resource. | Đưa protocol filter đến đúng chỗ. |
| SLO 502/503 | Gateway hoặc session store unavailable. | Repair/retry policy/alerts, kiểm tra active sessions còn tồn tại. |
| Mapping count tăng nhưng session count giảm | Listener/cleanup lỗi. | Sửa sessionDestroyed, TTL và orphan cleanup. |
| Người dùng vẫn hoạt động sau CAS logout | Callback mất hoặc mapping không tìm thấy, session vẫn sống. | Reconcile/kill local session qua admin workflow. |
| Sau logout CAS user SSO lại bất thường | TGT chưa thực sự bị hủy, new login flow, cookie/cache issues. | Phân biệt session CAS và Portal, kiểm tra ticket mới. |
| SLO nhắm sai phiên | Mapping keyed by username, realm/tenant confusion. | Incident response, sửa correlation key và tests. |

## 18. Ma trận kiểm thử QA

| ID | Tình huống | Kết quả đúng |
| --- | --- | --- |
| L01 | ST hợp lệ login, CAS SLO tới đúng ticket. | Invalidate đúng một local session. |
| L02 | Gửi cùng logoutRequest hai lần. | Lần đầu hủy, lần sau no-op/idempotent. |
| L03 | Hai notifications tới đồng thời trên cùng node. | Một thao tác hủy hiệu lực; không double-effect. |
| L04 | HTTP response của lần đầu mất, proxy retry. | Phiên vẫn ended, callback lặp an toàn. |
| L05 | Local session timeout trước SLO. | Listener đã dọn mapping; không tạo session mới. |
| L06 | User local logout trước SLO. | CAS notification không phục hồi local Authentication. |
| L07 | Session.invalidate() gặp IllegalStateException do timeout race. | Phân loại already-ended, không nuốt lỗi store không liên quan. |
| L08 | Session store thật bị lỗi khi invalidating. | Alert/processing failure, không báo confirmed invalidated. |
| L09 | ST cũ tới sau lần login mới ST-C. | Không hủy session ST-C. |
| L10 | Hai users trùng NameID ở CAS realms khác nhau. | Không hủy cross-realm. |
| L11 | Một user có hai sessions được cấp bằng hai ST. | SLO của ST-A không tự phá ST-B ngoài chính sách. |
| L12 | Ticket không có mapping. | Không đoán user hay session; monitor NO_MAPPING. |
| L13 | Ticket mapping bị xóa khi node restart. | Không false success; kiểm tra persistence/routing. |
| L14 | Callback tới Node B, mapping chỉ ở Node A. | Fail closed/route đúng hoặc shared mapping; không xóa nhầm. |
| L15 | Callback tới Node B với distributed mapping. | Nhắm đúng session trên store shared. |
| L16 | Session ID thay do fixation protection sau CAS login. | Mapping vẫn tìm đúng phiên cuối. |
| L17 | Không có `SingleSignOutHttpSessionListener`. | Test phát hiện orphan mapping/leak, chặn go-live. |
| L18 | Filter SLO không nằm trước authorization. | Test phát hiện 302/403, không coi là success. |
| L19 | Filter được auto-register hai lần. | Test phát hiện duplicate xử lý và sửa registration. |
| L20 | Proxy chặn form field `logoutRequest`. | Callback fail/alert, không báo đã hủy. |
| L21 | Payload quá lớn/DOCTYPE/XXE. | Parser từ chối, không ảnh hưởng sessions. |
| L22 | Callback từ nguồn không tin/binding sai. | Reject theo kênh đã xác thực. |
| L23 | CAS có mTLS contract nhưng client cert sai. | Ingress từ chối, không logout. |
| L24 | CAS không kết nối SP vì firewall/DNS. | App session có thể vẫn active; alert/reconcile. |
| L25 | SP invalidate xong nhưng CAS nhận timeout. | Duplicate/retry có thể xảy ra; không hủy lại user. |
| L26 | CAS /logout thành công nhưng một SP không nhận SLO. | Không tuyên bố toàn federation ended. |
| L27 | CAS front-channel browser đóng tab. | Không assume notification arrived. |
| L28 | CAS front-channel JSONP không được client hỗ trợ. | Không silently claim completed; chọn profile phù hợp. |
| L29 | Callback nhận GET/SAMLResponse theo định dạng SAML2 khác. | Không đi nhầm SAML2 LogoutResponse validator. |
| L30 | CAS session đã expired nhưng local session chưa. | SLO tốt thì local hủy; nếu delivery fail thì cần timeout/revocation. |
| L31 | CAS SLO bị retry sau event TTL. | Không chạm session generation mới; audit late/expired. |
| L32 | Session user bị disable trước CAS SLO. | Local authorization vẫn deny dù notification thất lạc. |
| L33 | App dùng stateless PT cache. | HttpSession listener không mặc nhiên evict PT cache. |
| L34 | CAS gửi callback theo public service URL nhưng proxy route sai. | Sửa canonical URL/ingress, không tắt controls. |
| L35 | OAuth/JWT session khác cùng user đang tồn tại. | CAS SLO không tự revoke credential khác. |
| L36 | Revoke yêu cầu cross-node atomic. | Một logical revocation, không có reactivation sau race. |

### 18.1. Lab kiểm thử tích hợp

1. Dựng **CAS test server** và hai service apps được phép, enable back-channel SLO với HTTPS/test trust.
2. Cho user login Portal lấy ST-A; xác nhận CAS client đã tạo mapping từ ST-A sang HttpSession thực.
3. Gọi CAS `/logout`, xác nhận Portal nhận notification và HttpSession cũ không dùng lại được.
4. Trong môi trường test, gửi **chính notification hợp lệ** lần nữa nếu harness cho phép; kiểm tra idempotency và không chạm session mới.
5. Tạo session timeout trước khi CAS logout; kiểm tra listener cleanup.
6. Chặn callback network một lần bằng firewall test; xác nhận local session vẫn có thể tồn tại và phản ánh UNKNOWN.
7. Thử CAS server nhận 5xx khi SP session store unavailable; kích hoạt alert và kiểm tra reconciliation policy.
8. Chạy hai nodes, session store có/không shared mapping để đo hiệu lực.
9. Đổi session ID sau authentication, kiểm tra mapping vẫn theo phiên hiện tại.
10. Chạy kịch bản ST-A cũ đến khi ST-C login mới đã tạo, không xóa ST-C.
11. Thử front-channel riêng nếu tổ chức hỗ trợ; không mặc định mọi client xử lý JSONP/iframe.
12. Thu thập logs đã mask và metrics theo realm/service/result, không lưu ticket raw.

### 18.2. Tiêu chí QA pass

- CAS logout ở test chứng minh session local thực sự bị hủy trên các nodes mục tiêu.
- SLO duplicate không gây lỗi 500 hàng loạt hoặc logout sai session.
- Expired session dẫn tới cleanup/no-op an toàn, không tạo session.
- Message late không đụng login generation mới.
- Delivery failure không được diễn giải thành authenticated logout completed.
- Security filters không mở rộng quyền của untrusted SLO sender.
- User/tenant/revocation độc lập với độ tin cậy của SLO delivery.
- Không dùng ST SessionIndex để thay một user ID, login token hoặc quyền.
- CAS session và application session có timeout/logout policies rõ.
- Nêu giới hạn best-effort trong thông báo vận hành và UX.

## 19. Runbook cho các sự cố thường gặp

### 19.1. Trường hợp A — thông báo lặp nhiều lần

**Dấu hiệu:** cùng CAS realm/service/ticket correlation xuất hiện nhiều lần trong audit; session đã invalidated.

**Hành động:** xác nhận duplicate, đo số lần retry, kiểm tra proxy/gateway/idempotency store, không xóa username-wide sessions. Nếu hệ thống trả HTTP 200 cho duplicate, chỉ nói đã xử lý **idempotently**, không ghi false “new session invalidated”.

### 19.2. Trường hợp B — session đã hết hạn, không tìm được mapping

**Dấu hiệu:** SLO callback hợp lệ đến sau thời gian idle; `SingleSignOutHttpSessionListener` đã dọn ticket.

**Hành động:** so sánh timestamp/session expiration audit, không tạo session; nếu tần suất NO_MAPPING tăng đột ngột, kiểm tra session store, listener, node routing và TTL. Không dừng CAS login vì một duplicate đến muộn thông thường.

### 19.3. Trường hợp C — không có callback dù CAS logout

**Dấu hiệu:** CAS TGT bị hủy, nhưng Portal không có event, session JSESSIONID còn dùng được.

**Hành động:** xác nhận CAS có SLO enabled và loại delivery cho service; kiểm tra firewall/DNS/TLS/route, CAS outbound logs và SP ingress logs. Nếu nghi ngờ bảo mật, **thu hồi local sessions từ application store** bằng admin control và giảm max session lifetime theo policy. Không chỉ khuyên user logout CAS lần nữa rồi coi hoàn tất.

### 19.4. Trường hợp D — SP xử lý rồi CAS vẫn báo timeout

**Dấu hiệu:** Portal có audit `INVALIDATED_NOW`, CAS gọi POST nhưng upstream báo timeout.

**Hành động:** xác minh session thật đã hết; nếu retry thì receiver no-op và trả kết quả theo handler policy. Điều tra proxy timeouts/response path; không xem việc CAS mất ACK là lý do khôi phục session.

### 19.5. Trường hợp E — callback sai node

**Dấu hiệu:** mapping chỉ có trên Node A, callback rơi Node B; NO_MAPPING cao nhưng session vẫn active.

**Hành động:** chọn shared mapping/routing có xác thực/fan-out theo kiến trúc, kiểm tra multi-node integration. Không chỉ bật sticky cookie nếu CAS back-channel không có browser cookie. Đánh dấu SLO coverage ở mức chưa đạt cho đến khi khắc phục.

### 19.6. Trường hợp F — có POST giả gửi đến SLO endpoint

**Dấu hiệu:** traffic bất thường, SessionIndex không thuộc known ticket, nguồn IP/mTLS sai, body malformed hoặc nhiều lookup thất bại.

**Hành động:** rate-limit/block theo chính sách, bảo vệ ingress và source, kiểm tra audit/incident, không tiết lộ ticket mappings. Nếu đã xảy ra logout nhầm, điều tra phạm vi users và fix trust boundary trước khi mở lại endpoint.

## 20. Các câu hỏi tự đánh giá

**1. CAS /logout thành công có bảo đảm mọi SP session đã bị hủy?**  
Không. CAS SLO theo protocol có tính best-effort/fire-and-forget ở delivery; mỗi ứng dụng sở hữu và hủy phiên của mình.

**2. `SessionIndex` trong CAS SLO là gì?**  
Trong CAS SLO truyền thống, nó thường là service-ticket identifier dùng để đối chiếu tới local HttpSession, không phải raw Servlet session ID.

**3. Vì sao cần `SingleSignOutHttpSessionListener`?**  
Dọn ánh xạ khi session timeout/local logout, tránh leak và lookup stale.

**4. Nếu nhận lại cùng notification sau khi session đã invalidated thì làm gì?**  
No-op/idempotent, không hủy session khác cùng username.

**5. Không tìm thấy mapping thì đã chắc user logout không?**  
Không. Có thể expired, local logout, mất mapping trên node khác hoặc network/routing state sai.

**6. CAS gửi notification đến trễ, user đã login lại thì sao?**  
Chỉ xử lý ticket/generation gốc; không động session mới nếu có ticket khác.

**7. CAS server timeout khi gọi SLO có nghĩa SP chưa logout?**  
Không chắc. SP có thể đã hủy rồi nhưng ACK mất; phải kiểm chứng session store/audit.

**8. SP nhận thông báo nhưng session store hỏng, có nên trả success?**  
Không được ghi “local session invalidated” khi chưa có bằng chứng; xử lý failure/retry/reconciliation.

**9. Vì sao không dùng NameID để hủy tất cả sessions ngay?**  
Vì NameID không phải khóa ticket/session duy nhất, có thể trùng giữa realm/tenant và gây logout nhầm.

**10. CAS notification trông như SAML XML, có dùng `saml2Logout()` không?**  
Không tự động. CAS SLO dùng filter và mapping của Java CAS client, không phải SAML2 SP LogoutResponse workflow.

**11. Nếu app chạy hai node có shared HttpSession, SLO đã tự distributed chưa?**  
Chưa chắc; ticket→session mapping của CAS client có thể vẫn local.

**12. Có thể dùng CSRF token của browser để xác thực CAS back-channel POST không?**  
Thông thường không. Cần protocol filter/ingress source trust riêng; không tắt CSRF toàn app.

**13. Để tránh duplicate, có cần đảm bảo CAS gửi đúng một lần?**  
Không thể dựa hoàn toàn vào producer. Receiver phải idempotent và correlation theo ticket.

**14. CAS đã logout nhưng cached stateless proxy ticket còn hiệu lực ở API?**  
Có thể nếu có cache riêng chưa bị evict; HttpSession SLO không tự thu hồi cache/token khác.

## 21. Checklist production

- [ ] Xác định rõ CAS TGT/TGC, ST, HttpSession và mapping ST→session.
- [ ] CAS client `SingleSignOutFilter` được cấu hình đúng và chạy trước filter chặn callback.
- [ ] Có `SingleSignOutHttpSessionListener` phù hợp Servlet container/session manager.
- [ ] Callback path, service URL, TLS, ingress network và SLO propagation type đã được CAS/Portal thống nhất.
- [ ] Không tạo Authentication/session mới khi nhận `logoutRequest`.
- [ ] Ticket correlation theo trusted realm/service/ticket, không chỉ username/NameID.
- [ ] Notification duplicate gây no-op hoặc kết quả idempotent, không double side effect.
- [ ] Session đã expired/local logout được xử lý an toàn, không restore.
- [ ] Callback late không hủy session generation mới.
- [ ] Không sử dụng raw SessionIndex như HTTP session ID để xóa user-wide.
- [ ] Source SLO có trust boundary rõ (HTTPS/mTLS/network allowlist/profile validation), không tin spoofable header.
- [ ] Parser giới hạn payload, chống XXE, không đưa raw XML/PII/ticket vào log.
- [ ] Không tắt CSRF cho toàn bộ browser app, chỉ xử lý CAS SLO theo filter/protocol phù hợp.
- [ ] Multi-node có shared mapping hoặc authenticated routing/fan-out được kiểm thử.
- [ ] Session ID rotation không làm mất ticket mapping, sessionDestroyed cleanup đã test.
- [ ] Nếu dùng distributed store, có TTL, atomic claim, retryable failure và không đánh dấu ended trước khi revoke có bằng chứng.
- [ ] CAS server gửi SLO theo best-effort được nêu trong threat model; không coi CAS logout page là global proof.
- [ ] Có network timeout/5xx/502/DNS/TLS failure runbook.
- [ ] Có cơ chế thu hồi local sessions khẩn cấp ngoài CAS SLO nếu callback thất lạc.
- [ ] Local authorization/account disable vẫn có hiệu lực khi network outage.
- [ ] Stateless PT caches hoặc OAuth/API sessions có revocation policy riêng.
- [ ] Metrics tách received, verified, mapped, invalidated, expired, duplicate, not_found và failure.
- [ ] Có test L01–L36 hoặc bộ integration tương đương trên CAS test server và nhiều nodes.
- [ ] Khi nâng Spring Security/Apereo CAS client, kiểm tra API và Servlet namespace, chạy lại SLO regression tests.

## Ghi nhớ

> **CAS Single Sign Out là một cơ chế thông báo để ứng dụng tự kết thúc phiên, không phải giao dịch phân tán cam kết mọi nơi đã logout.** Khi nhận thông báo lặp, hủy đúng phiên **một lần** rồi no-op; khi session đã hết hạn, không tạo lại hoặc hủy phiên mới; khi callback mất vì mạng, **không giả định** local session đã được thu hồi. Dùng khóa **CAS realm + service ticket → session generation**, listener cleanup, kiểm soát ingress, idempotency, metrics và runbook để bảo vệ ranh giới tin cậy.

### Tài liệu tham khảo

- [Apereo CAS — CAS Protocol Specification, `2.3 /logout và Single Logout](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): SLO POST, session identifier, client behavior và xử lý lỗi kiểu fire-and-forget.
- [Apereo CAS — Logout & Single Signout](https://apereo.github.io/cas/development/installation/Logout-Single-Signout.html): CAS SSO session vs app session; back-channel và front-channel propagation; callback chỉ là thông báo.
- [Apereo Java CAS Client — README: Configuring Single Sign Out](https://github.com/apereo/java-cas-client#configuring-single-sign-out): `SingleSignOutFilter`, `SingleSignOutHttpSessionListener` và filter-order requirements.
- [Spring Security — CAS Authentication, Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CAS login/filter/provider, local logout khác CAS logout, map và listener cleanup.
- [Spring Security — Architecture / Filter Registration](https://docs.spring.io/spring-security/reference/servlet/architecture.html): thứ tự filters và rủi ro đăng ký Filter bean hai lần.
- [Spring Security — Logout Handling](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `LogoutFilter`, session invalidation, CSRF và logout success.
- [Jakarta Servlet API — HttpSession](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession): `invalidate()` và `IllegalStateException`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SessionCreationPolicy, SecurityContextRepository và session fixation protection.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie, session lifecycle và bảo vệ việc thu hồi.
