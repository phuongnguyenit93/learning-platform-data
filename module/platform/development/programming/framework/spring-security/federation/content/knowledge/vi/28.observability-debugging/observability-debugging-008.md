# Chẩn đoán CAS INVALID_SERVICE, INVALID_TICKET và chuyển hướng lặp trong Spring Security

## 1. Tại sao ba triệu chứng này thường đi cùng nhau?

Một ứng dụng dùng **Spring Security – federation** để đăng nhập qua **Apereo CAS** thường hoạt động như sau: khi người dùng vào tài nguyên yêu cầu xác thực, ứng dụng chuyển browser tới CAS Server; CAS xác thực người dùng rồi phát một **Service Ticket (ST)**; browser quay về callback của ứng dụng; ứng dụng dùng ST gọi CAS **/serviceValidate** (hoặc endpoint validation phù hợp); sau khi CAS xác minh, Spring Security tạo `Authentication` và duy trì phiên local.

Nếu dịch vụ thực hiện sai một trong các bước, bạn có thể thấy:

- **`INVALID_SERVICE`**: CAS xác định service được cung cấp khi validate ticket không khớp với service mà ticket được phát cho.
- **`INVALID_TICKET`**: ticket đã mất hiệu lực, không tồn tại, hết hạn, bị sử dụng trước đó hoặc không đáp ứng một số yêu cầu validation như `renew` theo giao thức.
- **“Too many redirects” / ERR_TOO_MANY_REDIRECTS**: browser liên tục đi từ ứng dụng sang CAS và quay lại nhưng **không bao giờ thiết lập một phiên ứng dụng có thể dùng được**. Vòng lặp có thể do validation thất bại, hoặc validation **thành công** mà session cookie / SecurityContext bị mất.

**Điểm rất quan trọng trong CAS protocol:** **Service Ticket được validate một lần duy nhất**, bất kể lần kiểm tra thành công hay thất bại. Đặc biệt, **`INVALID_SERVICE` tiêu thụ ticket**. Khi sửa cấu hình service URL rồi thử **lại đúng ticket cũ**, kết quả tiếp theo thường là **`INVALID_TICKET`**. Nếu bỏ qua điều này, người vận hành dễ nhầm “đã sửa URL nhưng CAS vẫn không nhận ticket”.

Bài này thuộc nhóm **Quan sát và gỡ lỗi**. Mục tiêu:

1. Đọc chính xác các lỗi theo **CAS protocol**, phân biệt với lỗi **service registry không cho phép ứng dụng**.
2. So sánh ba nơi dùng `service`: redirect tới `/login`, callback nhận ST và back-channel `/serviceValidate`.
3. Xác định sai khác scheme/host/port/path/query/trailing slash, external URL với internal URL sau load balancer/proxy, encode URL hai lần và dynamic parameters.
4. Hiểu vòng đời ST, retry/replay, expiration, `renew=true`, ST và PT, session CAS/TGC so với Spring `JSESSIONID`.
5. Đọc **Spring Security `ServiceProperties`, `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `Cas20ServiceTicketValidator`** và các cấu hình liên quan.
6. Lấy redirect trace và log/correlation an toàn mà **không ghi raw ticket hay cookie**.
7. Phân biệt vòng lặp do **validation fail** và vòng lặp do **session không persist** dù validation success.
8. Tạo runbook: tái hiện → phân nhánh nguyên nhân → sửa đúng chỗ → thử **ST mới** → xác nhận có phiên ứng dụng → regression test.
9. Chạy demo **Java 17** mô phỏng các error codes và hai kiểu redirect loop, kèm stdout được kiểm chứng.
10. Xây checklist test và metric giám sát lỗi production.

**Giới hạn:** CAS là một giao thức SSO riêng. Không áp ngữ nghĩa của Kerberos service ticket, SAML Assertion, OIDC ID Token hoặc OAuth Authorization Code lên CAS Service Ticket. CAS ST không phải JWT và không phải cookie browser.

## 2. Luồng CAS chuẩn: phân biệt CAS SSO session và ứng dụng session

~~~text
Browser                 Spring Security Web App              Apereo CAS
   |                             |                                |
   | GET /private                |                                |
   |---------------------------->|                                |
   |                             | Chưa có Authentication          |
   |<----------------------------| 302 /cas/login?service=S        |
   |------------------------------------------------------------->|
   |                             |                                | Có SSO/TGC?
   |                             |                                | Login nếu cần
   |<-------------------------------------------------------------|
   | 302 S?ticket=ST-NEW-1       |                                |
   |                             |                                |
   | GET /login/cas?ticket=ST-NEW-1                              |
   |---------------------------->|                                |
   |                             | CasAuthenticationFilter        |
   |                             | -> CasAuthenticationProvider   |
   |                             | -> TicketValidator             |
   |                             |                                |
   |                             | GET /cas/serviceValidate       |
   |                             | ?service=S&ticket=ST-NEW-1     |
   |                             |------------------------------->|
   |                             | <cas:authenticationSuccess>    |
   |                             |<-------------------------------|
   |                             |                                |
   |                             | Load UserDetails/roles         |
   |                             | Save SecurityContext/session   |
   |<----------------------------| Set-Cookie: JSESSIONID=...     |
   | 302 /private                |                                |
   |---------------------------->|                                |
   | Cookie: JSESSIONID=...      |                                |
   |<----------------------------| 200 /private                   |
~~~

Trong ví dụ:

~~~text
CAS base URL:  https://sso.example.test/cas
CAS login:     https://sso.example.test/cas/login
CAS validate:  https://sso.example.test/cas/serviceValidate

Public service / CAS callback:
  https://portal.example.test/login/cas

Protected business endpoint:
  https://portal.example.test/private
~~~

**Service callback** và **business URL** không nhất thiết giống nhau. Trong cấu hình Spring Security CAS stateful điển hình, `ServiceProperties.service` phải trỏ tới URL mà **`CasAuthenticationFilter` giám sát**, theo mặc định `/login/cas`. Redirect trở lại trang `/private` là nhiệm vụ của success handler/saved request sau khi xác thực, **không phải bằng cách validate ST cho `/private`**.

### 2.1. Các từ cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **`service` của CAS** | URL định danh service mà CAS sẽ redirect về và gắn service ticket khi phát ticket; được dùng lại trong validation |
| **Service registry** | Danh mục/pattern/policy các service CAS Server được phép phục vụ |
| **ST — Service Ticket** | Credential opaque dành cho một service, **single-use validation** |
| **TGC — Ticket Granting Cookie** | Cookie đăng nhập SSO của **CAS Server**, cho phép cấp các ST mới theo chính sách |
| **TGT — Ticket Granting Ticket của CAS** | Bằng chứng SSO server-side liên quan TGC; không phải Kerberos TGT và không được gửi làm ST tới Spring callback |
| **`JSESSIONID`** | Cookie phiên **của ứng dụng Spring**, độc lập với TGC |
| **`CasAuthenticationEntryPoint`** | Bắt đầu SSO bằng redirect browser tới CAS login |
| **`CasAuthenticationFilter`** | Nhận artifact ticket tại callback theo filter processes URL |
| **`CasAuthenticationProvider`** | Dùng TicketValidator xác thực ticket và nạp UserDetails/authorities |
| **`Cas20ServiceTicketValidator`** | Client gọi endpoint CAS ticket validation; không tin ST chỉ vì có chuỗi bắt đầu bằng `ST-` |

Nếu người dùng vẫn có **CAS TGC hợp lệ** nhưng app không giữ được `JSESSIONID`, mỗi lần app redirect sang CAS, CAS có thể phát một **ST mới** gần như ngay lập tức. Điều đó tạo redirect loop cực nhanh dù người dùng đã đăng nhập CAS.

## 3. Đọc đúng CAS protocol error codes

Giao thức CAS 2.0/3.x `/serviceValidate` trả XML với một trong hai nhánh:

**Thành công** (rút gọn):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Thất bại** (ví dụ):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    Service identifier does not match ticket
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

Các XML trên chỉ minh họa cấu trúc, không phải response thực của một CAS Server cụ thể. **Message body chi tiết thay đổi theo phiên bản/config**, không nên parse bằng substring chứa từ “invalid”. Parse XML namespace/element/error code đúng và **không cho phép XXE** nếu tự viết client (ưu tiên CAS client library).

### 3.1. Bảng ý nghĩa theo đặc tả

| Error code | Nghĩa theo CAS protocol | Nên điều tra |
| --- | --- | --- |
| **`INVALID_REQUEST`** | Thiếu tham số request bắt buộc | `service`, `ticket`, encoding, param names |
| **`INVALID_TICKET_SPEC`** | Ticket/validation không thỏa loại/spec yêu cầu | PT dùng với `/serviceValidate`, sai validation profile |
| **`INVALID_TICKET`** | Ticket không hợp lệ, hết hạn, đã dùng/không được nhận; cũng có thể do `renew=true` với ticket không được cấp sau primary authentication | ST lifecycle, retry, expiry, renew, CAS ticket store |
| **`INVALID_SERVICE`** | Ticket **đã tồn tại hợp lệ**, nhưng service khi validation **không khớp** service gắn với ticket; ticket bị hủy | URL service tại CAS login vs validation, scheme/host/port/path/query |
| **`UNAUTHORIZED_SERVICE_PROXY`** | Service không được phép proxy authentication | PGT/proxy policy, không nhầm ST service mismatch |
| **`INVALID_PROXY_CALLBACK`** | Proxy callback/credentials không thỏa bảo mật | HTTPS PGT callback, cert trust, route |
| **`INTERNAL_ERROR`** | CAS gặp lỗi nội bộ khi validation | CAS logs, ticket registry, storage/cluster, dependency failures |

CAS Server/versions có thể bổ sung error codes; bảng là bộ **minimum protocol codes**. Không nên dựa vào mỗi tên để kết luận tuyệt đối một root cause khi chưa xem **CAS logs và service/ticket correlation**.

**Phân biệt:** thông báo CAS login **“Application Not Authorized”** thường xảy ra do **service URL không được service registry chấp nhận**, khác với **`INVALID_SERVICE`** ở ticket validation: ticket có thể được phát hợp lệ nhưng khi validate service bị sai.

### 3.2. Error code nằm ở đâu?

Trong trình duyệt, bạn thường thấy redirect/cookie/HTTP 302; **`INVALID_SERVICE` và `INVALID_TICKET` thường xuất hiện ở phản hồi XML back-channel** giữa ứng dụng và CAS. Client browser có thể chỉ thấy trang login lỗi hoặc vòng lặp.

Dấu hiệu cần thu:

- Browser HAR: chuỗi 302 và URL **đã redacted**.
- CAS Server logs: code của validation failure, registration/service ID, timestamp, request correlation.
- Spring app logs: exception từ `TicketValidator`/`CasAuthenticationProvider`; service URL dùng validation, callback path, session persistence.
- Gateway/ingress logs: public host/scheme, forwarded headers được tin, cookie/SameSite/Path.
- Metrics: number of CAS redirects mỗi browser/session, validation failure rates, successful validations nhưng session mất.

**Không ghi raw `ticket` / TGC / JSESSIONID vào log**, kể cả khi debug.

## 4. INVALID_SERVICE: sai service URL ở bước nào?

### 4.1. Bản chất bảo vệ chống ticket substitution

Khi CAS phát ST cho:

~~~text
https://portal.example.test/login/cas
~~~

ticket đó **không thể dùng như credential cho**:

~~~text
https://reports.example.test/login/cas
~~~

dù hai ứng dụng cùng sử dụng CAS Server. Service binding ngăn một ticket của service A bị mang sang service B.

Với Spring Security CAS thông dụng:

~~~text
ServiceProperties.service:
  https://portal.example.test/login/cas

CasAuthenticationEntryPoint:
  redirects to
  https://sso.example.test/cas/login
      ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas

CAS issues ST for:
  https://portal.example.test/login/cas

Browser callback:
  https://portal.example.test/login/cas?ticket=ST-NEW-1

CasAuthenticationProvider / TicketValidator:
  GET https://sso.example.test/cas/serviceValidate
      ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
      &ticket=ST-NEW-1
~~~

Phía Spring dùng cùng **`ServiceProperties`** cho entrypoint/provider và đúng callback filter. Nếu CAS phát ST cho một chuỗi service khác với chuỗi validator gửi thì có thể xảy ra **`INVALID_SERVICE`**.

### 4.2. Một mâu thuẫn service có thể biến thành hai error codes liên tiếp

~~~text
T1  CAS cấp ST-1 cho service=https://portal.example.test/login/cas
T2  App validate ST-1 với service=http://app:8080/login/cas
T3  CAS: INVALID_SERVICE
    ST-1 bị TIÊU THỤ theo CAS protocol
T4  Người vận hành sửa service=http://... thành https://portal...
T5  Người vận hành thử validate LẠI ST-1
T6  CAS: INVALID_TICKET, vì ST-1 không còn hợp lệ
T7  Browser khởi tạo CAS login MỚI, CAS phát ST-2
T8  App validate ST-2 với service=https://portal... -> SUCCESS
~~~

Vì vậy quy trình test đúng sau khi sửa **`INVALID_SERVICE`** là **khởi tạo một vòng CAS login mới để được cấp ST mới**. Không tự retry cùng một ST hoặc thêm retries network để “chờ đồng bộ”.

### 4.3. Các khác biệt URL thường gây INVALID_SERVICE

| Service dùng lúc phát ticket | Service lúc validation | Kết quả trong strict matching profile |
| --- | --- | --- |
| `https://portal.example.test/login/cas` | Cùng chuỗi | PASS nếu ST còn hiệu lực |
| `https://portal.example.test/login/cas` | `http://portal.example.test/login/cas` | FAIL: scheme |
| `https://portal.example.test/login/cas` | `http://app:8080/login/cas` | FAIL: internal vs public |
| `https://portal.example.test/login/cas` | `https://portal-internal.example.test/login/cas` | FAIL: host |
| `https://portal.example.test/login/cas` | `https://portal.example.test:8443/login/cas` | FAIL: port |
| `https://portal.example.test/login/cas` | `https://portal.example.test/app/login/cas` | FAIL: context path |
| `https://portal.example.test/login/cas` | `https://portal.example.test/login/cas/` | FAIL: trailing slash |
| `https://portal.example.test/login/cas` | `https://portal.example.test/login/cas?lang=vi` | FAIL: query |
| `https://portal.example.test/login/cas` | `https://portal.example.test/private` | FAIL: callback vs protected page |
| `https://portal.example.test/login/cas` | `https://evil.example.test/login/cas` | FAIL: cross-service substitution |
| `https://portal.example.test/login/cas?x=1&y=2` | Cùng parameters nhưng canonical form khác | Phải đối chiếu đúng service matching strategy của CAS |

**Lưu ý chính xác:** CAS protocol gắn ticket với **service identifier**, và CAS Server có các **service matching strategies/normalization rules** cấu hình được. Bảng đang áp **strict identity matching** để minh họa lỗi; không có một chuẩn URI canonicalization tùy ý mà client được phép tin luôn tương đương. Đừng “sửa” bằng `startsWith("https://portal")` hoặc regex quá rộng trong ticket validation.

### 4.4. Registry match và ticket match là hai phép kiểm khác nhau

**Service registry** có thể cho phép một **pattern** như `^https://portal\.example\.test/login/cas$` hoặc một tập URLs được duyệt. Registry quyết định **dịch vụ có được dùng CAS hay không**.

**Ticket validation** cần service đúng **identifier mà ST đã phát cho**, theo matching policy. Đăng ký pattern cho hai URLs không có nghĩa một ST phát cho URL A tự hợp lệ với URL B.

Ví dụ registry sai:

~~~text
^https://.*       # Cho mọi HTTPS host - QUÁ RỘNG
~~~

Một cấu hình như vậy có thể làm CAS chấp nhận ứng dụng không chủ đích. **Không mở registry toàn Internet** để chữa `INVALID_SERVICE`. Hãy sửa chính xác service identifier và đăng ký đúng application.

### 4.5. URL encoding: phân biệt biểu diễn HTTP và giá trị service

Trong CAS login/validation request, `service` là **query parameter được URL-encode**. Ví dụ:

~~~text
Giá trị service gốc:
  https://portal.example.test/login/cas

Khi truyền trong CAS URL:
  service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
~~~

CAS server **decode tham số** rồi xử lý service identifier. Nếu một gateway/client vô tình **encode hai lần**, giá trị sau một vòng decode có thể vẫn là `https%3A%2F%2F...` thay vì URL gốc, gây mismatch/registry error.

Kiểm tra:

- Ai chịu trách nhiệm encode query parameter? Spring CAS client hay application custom redirect?
- Có nối string query trực tiếp rồi gọi `URLEncoder` trên **cả URL CAS** không?
- Có chèn `?ticket=...` vào `service` trước khi validate không?
- Có thêm dynamic tracking parameters, query localization, session id `;jsessionid`, fragment hoặc slash khác không?
- Proxy có rewrite/normalize query/path hoặc redirect `http→https` không?

**Không so raw URL-encoded strings như thể đó là canonical service values**; decode đúng một tầng trong test trace và so **giá trị logic** theo CAS service matcher.

## 5. INVALID_TICKET: ticket thật sự không được dùng nữa

### 5.1. Nguyên nhân theo giao thức

CAS Service Ticket:

- Là chuỗi opaque, **không nên tự parse hoặc đoán user từ ticket**.
- Chỉ dành cho **service** được gắn lúc phát ticket.
- **Chỉ được validate một lần**. CAS protocol nêu rõ ticket hết hiệu lực sau **một validation attempt**, **kể cả thất bại**.
- Có **thời gian sống ngắn** theo CAS ticket expiration policy; hết hạn thì validation fail.
- Phụ thuộc CAS ticket registry/store đang giữ record tương ứng.
- Có thể chịu yêu cầu `renew=true` khi validate.

Nguyên nhân `INVALID_TICKET` phổ biến:

1. **Replay:** callback bị refresh/back hoặc browser/proxy gửi lại cùng `ticket`.
2. **Double validation:** hai servlet filters, hai authentication managers hoặc duplicate requests cùng gọi `/serviceValidate` cho một ST.
3. **Ticket đã bị tiêu thụ bởi `INVALID_SERVICE` trước đó**.
4. **Ticket hết hạn** do user ở browser lâu, network delay, queue, clock/policy chênh.
5. **Ticket không tồn tại ở registry**: ký tự thay đổi/URI parsing sai, CAS store/cache bị mất, deployment cluster không thống nhất store.
6. **`renew=true`** nhưng ticket được phát từ session SSO (không có primary credentials login cho lần phát đó).
7. **Không đúng ticket/endpoint type** (PT dùng với `/serviceValidate` hoặc ST dùng ở nơi yêu cầu proxy ticket) — error cụ thể có thể là `INVALID_TICKET_SPEC` hoặc lỗi khác tùy implementation.
8. **Ticket giả/không được CAS Server này cấp** hoặc môi trường stage/prod CAS bị trộn.
9. **Load balancer/session ticket registry replication lỗi**: ticket được cấp tại một node nhưng validation đến nơi không thấy.
10. **Client tái sử dụng token ở các requests API stateless** trong khi ST đã single-use.

### 5.2. Các dấu hiệu nên ghi lại

| Bằng chứng | Khả năng |
| --- | --- |
| Validation lần đầu SUCCESS, lần hai INVALID_TICKET | Single-use hoạt động đúng |
| Validation lần đầu INVALID_SERVICE, lần hai INVALID_TICKET | Mismatch đã tiêu thụ ticket |
| Validation lần đầu INVALID_TICKET dù service đúng | ST unknown/expired/already used/renew mismatch |
| Hai app nodes cùng validate một ticket | Race/double-validation |
| Lỗi chỉ khi quay lại browser bằng Back/Refresh | Callback replay |
| Lỗi sau redirect rất chậm | Ticket expired / time policy |
| Lỗi chỉ khi `sendRenew=true` | Primary-auth requirement không được thỏa |
| Lỗi chỉ sau CAS Server rollout | Ticket registry keys/cache/store/cluster problem |
| Lỗi khi dùng PT với `/serviceValidate` | Wrong validation endpoint/ticket type |
| Mỗi lần sinh ST mới nhưng đều INVALID_TICKET | CAS server issuer/registry, expiration, renew, client config |
| App dùng ST như cookie dài hạn | Anti-pattern: ST không phải reusable session token |

**Không tăng ticket TTL hoặc tắt replay protection như cách chữa đầu tiên.** Hãy xác định nguyên nhân. Với security policy cần ST ngắn hạn/single-use, thay đổi TTL/ticket policies không phải sửa client logic.

### 5.3. Renew = đòi primary authentication, không phải auto retry

Trong Spring Security `ServiceProperties#setSendRenew(true)` yêu cầu CAS không chỉ dùng sẵn SSO session khi phát ST; việc validate với `renew` cũng yêu cầu ticket chứng minh primary credentials authentication theo CAS contract.

Tình huống:

~~~text
Browser có TGC / SSO login từ trước
App/CAS client validation dùng renew=true
Ticket không được phát trong primary login tương ứng
=> CAS có thể trả INVALID_TICKET theo CAS spec
~~~

Đừng đổi `renew=true` thành false theo phản xạ nếu ứng dụng có yêu cầu **fresh authentication/step-up**. Hãy kiểm CAS `/login` nhận cùng renew policy, browser có thực sự nhập credentials mới không, và CAS validator dùng cùng `ServiceProperties`.

### 5.4. ST và PT khác nhau

- **ST** được CAS cấp để browser truy cập một ứng dụng; `/serviceValidate` xác minh ST.
- **PT** là **Proxy Ticket** cho service-to-service delegation; phù hợp `/proxyValidate` và proxy authorization policy.
- **PGT** là Proxy Granting Ticket, được cấp theo cơ chế callback/ủy quyền riêng, không phải ST.

Nếu một `PT-...` được đưa tới `/serviceValidate`, CAS protocol quy định **không được coi đó là ST thành công**; error cụ thể có thể thuộc nhóm ticket specification. Không sửa bằng cách đổi chuỗi `PT-` thành `ST-` hoặc skip verification.

Spring Security CAS cũng có **`authenticateAllArtifacts` và `ServiceAuthenticationDetailsSource`** cho các use cases proxy/stateless riêng. Không bật tùy tiện trên một web app stateful chỉ để nhận ticket ở mọi path.

## 6. Redirect loop: ba nhánh cần phân biệt ngay

“Too many redirects” là **triệu chứng của HTTP/browser**, không phải một CAS protocol error code. Để tìm nguyên nhân, trước hết xem **CAS ticket validation đã thành công bao giờ chưa**.

### Nhánh A: Validation thất bại ở mọi vòng

~~~text
GET /private
  -> 302 CAS /login?service=PUBLIC_SERVICE
CAS phát ST-1
  -> 302 /login/cas?ticket=ST-1
App validate ST-1 với WRONG_SERVICE
  <- CAS INVALID_SERVICE
App vẫn anonymous
  -> 302 CAS /login?service=PUBLIC_SERVICE
CAS phát ST-2
  -> 302 /login/cas?ticket=ST-2
App validate ST-2 với WRONG_SERVICE
  <- CAS INVALID_SERVICE
... lặp liên tục ...
~~~

Đặc trưng:

- Mỗi vòng có **ST mới**, không phải cùng ST.
- CAS SSO/TGC có thể vẫn hợp lệ nên CAS login redirect rất nhanh.
- CAS validation fail nhiều lần: `INVALID_SERVICE`, `INVALID_TICKET`, TLS, certificate/trust errors hoặc network failures.
- App không tạo Authentication/session vì chưa có validation success.

**Ưu tiên:** xem **lỗi validation gốc đầu tiên**, service lúc CAS phát ticket và service lúc validator gửi. Không bắt đầu bằng xóa toàn bộ cookies hay tăng thời gian session.

### Nhánh B: Validation thành công nhưng phiên ứng dụng không duy trì

~~~text
GET /private
  -> 302 CAS /login?service=PUBLIC_SERVICE
CAS phát ST-1
  -> /login/cas?ticket=ST-1
App /serviceValidate ST-1 -> authenticationSuccess
App tạo SecurityContext = alice
App trả Set-Cookie: JSESSIONID=S1
Browser GET /private nhưng KHÔNG gửi JSESSIONID=S1
  -> App vẫn anonymous
  -> CAS /login?service=PUBLIC_SERVICE
CAS phát ST-2
  -> /login/cas?ticket=ST-2
App validation SUCCESS
  -> Set-Cookie: JSESSIONID=S2
Browser lại không gửi cookie ...
~~~

Đặc trưng:

- CAS validation **SUCCESS** ở các vòng.
- Spring app tiếp tục redirect CAS vì **không load lại SecurityContext** ở request kế tiếp.
- Nguyên nhân thường là **Cookie Path/Domain/SameSite/Secure**, khác hostname, HTTP/HTTPS, reverse proxy, session cookie bị browser chặn, hoặc **SecurityContextRepository không save**.
- Ứng dụng **stateless** hoặc `SessionCreationPolicy.STATELESS` ngoài ý muốn trong khi flow CAS browser cần session stateful.
- Session lưu node A nhưng request đến node B, Redis/Spring Session không chia sẻ hoặc sticky-session không ổn.

**Ưu tiên:** đọc Set-Cookie và **Cookie header của request kế tiếp**, session ID opaque đã được hash, SecurityContext save/load, shared store.

### Nhánh C: CAS/login/entrypoint hoặc URL routing tự redirect

~~~text
GET /login/cas?ticket=ST-1
  -> route không match CasAuthenticationFilter
  -> anyRequest().authenticated() tiếp tục coi anonymous
  -> CasAuthenticationEntryPoint chuyển về CAS login
  -> CAS lại redirect /login/cas?ticket=ST-2
  -> callback vẫn bị bỏ qua
... lặp ...
~~~

Nguyên nhân:

- Spring Security FilterChain matcher không bao phủ `/login/cas`, hoặc `filterProcessesUrl` không khớp.
- Application context path bị nhân đôi: `/app/login/cas` vs `/login/cas`.
- Reverse proxy rewrite callback path/host sai, handler route khác nhận ticket.
- CAS filter đứng sai SecurityFilterChain/order; custom redirect filter chạy trước khi CAS filter xử lý.
- Redirect tới `/login` của ứng dụng lại bị yêu cầu authentication và chuyển về CAS, tạo loop ngay cả khi không có ST.
- Login success handler chuyển về URL protected khác scope/cookie hoặc chuyển sang HTTP/host alias.
- Forced HTTPS redirects/proxy TLS termination gây `http→https→http` loop.
- `gateway=true` orchestration hoặc saved-request loop, nếu dùng.
- CAS Server tự có redirect loop do TGC/SSO cookie bị chặn trên CAS domain; trace cho biết vòng lặp ở **CAS login host**, không chỉ app host.

**Ưu tiên:** phân loại các `Location` theo hostname/path/status/Set-Cookie và xác minh **callback thực sự được CAS filter xử lý**.

## 7. Giải thích các cấu hình Spring Security CAS liên quan

Tài liệu Spring Security CAS có những thành phần chính:

~~~text
ExceptionTranslationFilter
      |
      +-> CasAuthenticationEntryPoint
      |     - CAS login URL
      |     - ServiceProperties.service
      |
      v
Browser CAS login + ST redirect
      |
      v
CasAuthenticationFilter (default /login/cas)
      - extracts ?ticket
      - submits CAS service ticket Authentication
      |
      v
ProviderManager
      |
      v
CasAuthenticationProvider
      - ServiceProperties
      - Cas20ServiceTicketValidator
      - UserDetailsService / authorities
      |
      v
SecurityContextRepository
      - HttpSession / Spring Session
      |
      v
SavedRequest / success redirect / authorization
~~~

**`ServiceProperties.service` là điểm bắt đầu điều tra.** Javadoc `CasAuthenticationFilter` giải thích khi filter giám sát `/login/cas`, giá trị `ServiceProperties.getService()` được dùng làm `service` khi validate ST. Nó phải nhất quán với URL callback thực tế.

Đây là CAS client cho Spring Security, không phải Spring Security SAML2/OIDC; đừng thêm `saml2Login` hoặc `oauth2Login` để “chữa” CAS callback nếu ứng dụng không có flow tương ứng.

### 7.1. Dependency và version alignment

Ví dụ Gradle (project đã có Boot/Spring dependency management):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

CAS client library `org.apereo.cas.client:cas-client-core` là dependency của module trong các nhánh tương ứng. Dùng BOM/plugin alignment phù hợp Java/Jakarta Servlet version; **không trộn** Spring Security CAS 5.x/6.x/7.x với CAS client packages không tương thích. Tài liệu CAS Spring Security có một số ví dụ XML từ đời trước nhưng **Javadoc 7.x** vẫn công bố `ServiceProperties`, `CasAuthenticationFilter`, `CasAuthenticationEntryPoint` và `CasAuthenticationProvider`.

**Đừng hard-code “latest” version vào bài mẫu**; kiểm release/BOM trên project. Spring Boot 3.x và 4.x có dependency/Jakarta API khác nhau; code minh họa cần compile với tổ hợp đã chọn.

### 7.2. Cấu hình mẫu Spring Java: cùng một service URL

Ví dụ bean cấu hình cho web app nhận callback tại `https://portal.example.test/login/cas`:

~~~java
package com.example.portal.security;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class CasWebSecurityConfig {
    private static final String SERVICE =
        "https://portal.example.test/login/cas";
    private static final String CAS_BASE =
        "https://sso.example.test/cas";

    @Bean
    ServiceProperties casServiceProperties() {
        ServiceProperties props = new ServiceProperties();
        props.setService(SERVICE);
        props.setSendRenew(false);
        return props;
    }

    @Bean
    CasAuthenticationProvider casProvider(
            ServiceProperties casServiceProperties,
            UserDetailsService userDetailsService) {
        CasAuthenticationProvider provider = new CasAuthenticationProvider();
        provider.setServiceProperties(casServiceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(CAS_BASE));
        provider.setKey("portal-cas-provider-identity");
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain casFilterChain(
            HttpSecurity http,
            ServiceProperties casServiceProperties,
            CasAuthenticationProvider casProvider) throws Exception {

        CasAuthenticationEntryPoint entry = new CasAuthenticationEntryPoint();
        entry.setLoginUrl(CAS_BASE + "/login");
        entry.setServiceProperties(casServiceProperties);

        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setFilterProcessesUrl("/login/cas");
        filter.setServiceProperties(casServiceProperties);
        filter.setAuthenticationManager(new ProviderManager(casProvider));
        filter.setSecurityContextRepository(repository);
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .authenticationProvider(casProvider)
            .securityContext(context -> context
                .securityContextRepository(repository))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entry))
            .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

Đây là **Spring integration configuration**, không phải Java 17 standalone. Cần CAS Server thật hoặc mock server hỗ trợ protocol, certificate chain, `UserDetailsService` an toàn, session persistence, HTTPS ingress, CSRF/logout policy, và integration test với Spring version đã chọn.

Những điểm đáng kiểm:

- `ServiceProperties.service` là một **public callback URL** cố định và đúng.
- `CasAuthenticationEntryPoint` và `CasAuthenticationProvider` dùng **cùng bean ServiceProperties**.
- `CasAuthenticationFilter.filterProcessesUrl` giám sát đúng đường callback `/login/cas` sau context path.
- `Cas20ServiceTicketValidator(CAS_BASE)` dùng base URL của **CAS Server**, không phải URL của ứng dụng.
- `CasAuthenticationProvider` nạp local `UserDetailsService`/roles **sau khi CAS xác minh ticket**.
- `HttpSessionSecurityContextRepository` là lựa chọn cho phiên browser stateful; `filter.setSecurityContextRepository(...)` đặc biệt cần lưu ý trong Spring Security 6/7 custom filter.
- `ChangeSessionIdAuthenticationStrategy` giúp giảm session fixation sau login.
- Nếu có nhiều `SecurityFilterChain`, phải đảm bảo callback và protected resources nằm trong chính sách phù hợp; filter không bị auto-register/execute hai lần.
- Nếu chọn dynamic service URLs hoặc `authenticateAllArtifacts=true` cho proxy/stateless use case, cần cơ chế `ServiceAuthenticationDetailsSource` và ticket URL binding đúng theo Spring docs; **đừng bật như bản vá cho `INVALID_SERVICE`**.
- Không thêm `formLogin`/`httpBasic` fallback vào CAS-only chain trừ khi có policy; một provider fallback sai có thể tạo authentication downgrade.

### 7.3. Có một redirect loop vì filter URL không match

Ví dụ:

~~~text
ServiceProperties.service = https://portal.example.test/app/login/cas
CasAuthenticationFilter.filterProcessesUrl = /login/cas
Servlet context path = /app
Reverse proxy strips /app before app

Observed callback at backend:
  /login/cas?ticket=ST-...

Nếu route/context path hoặc SecurityFilterChain matchers không nhất quán:
  CAS filter có thể không nhận ticket.
  Browser lại bị entrypoint chuyển về CAS.
~~~

Đây là một ví dụ **cần kiểm request path và servlet context thực tế**, không phải quy tắc tự động “có /app là sai”. Spring xử lý servlet context path và filter path theo framework semantics; hãy đo bằng trace/integration test, **không đoán**.

## 8. Reverse proxy/TLS làm sai service

Một kiến trúc hay gặp:

~~~text
Browser:
  https://portal.example.test/login/cas

Load balancer:
  terminates TLS, rewrites Host/Path
  X-Forwarded-Proto: https
  X-Forwarded-Host: portal.example.test

Spring app:
  http://portal-pod:8080/login/cas
~~~

Nếu CAS entrypoint xây service từ **public URL** nhưng validator/filter tự tính bằng **internal URL**, ticket có thể bị từ chối. Nếu cả hai dùng một giá trị sai internal URL, CAS Server có thể từ chối service từ service registry hoặc browser không truy cập được callback.

### 8.1. Checklist đúng cách

- Xác định **một source of truth** cho public service callback.
- Có service registry entry cho **public service identifier** được duyệt, không mở regex `.*`.
- Dùng `ServiceProperties.service` chính xác khi các Spring CAS components dựa vào service cố định.
- Nếu app sử dụng dynamic URLs, kiểm từng thành phần có lấy cùng **trusted external URL** hay không.
- Reverse proxy set `Forwarded/X-Forwarded-*` **chỉ từ trusted proxy**; loại bỏ/chặn headers spoofed từ Internet.
- Với Spring Boot, có thể cấu hình forwarding strategy ở mức Servlet/proxy phù hợp; **kiểm bằng request thực tế**, không chỉ nhìn một YAML property.
- Đảm bảo scheme HTTPS, host, port, context path và path case/trailing slash nhất quán.
- Kiểm URL-encoding đúng một lần; service query parameters không thay đổi bất ngờ.
- Không encode `JSESSIONID`/ticket vào service định danh nếu không có contract được duyệt.
- Không bỏ TLS validation để chữa lỗi handshake. CAS ticket validation back-channel dùng HTTPS trusted CA.
- Không chấp nhận Host-header injection để build login redirect hoặc service URL attacker-controlled.

### 8.2. Vì sao 302 HTTP→HTTPS cũng liên quan?

Nếu gateway và app không thống nhất public scheme, có thể:

~~~text
Browser -> https://portal.example.test
Proxy -> http://app:8080
Spring sees http and redirects to https://app:8080
Proxy redirects back to public https://portal...
... loop scheme/host ...
~~~

Ở nhánh này có thể **chưa hề có ticket validation**. Hãy dùng HAR để biết redirect xảy ra trước CAS login, ở CAS Server, hay sau callback.

## 9. Những vấn đề session khiến CAS validation thành công nhưng vẫn loop

### 9.1. Hai cookie ở hai host

| Cookie | Domain mặc định | Chức năng | Khi mất |
| --- | --- | --- | --- |
| **CAS TGC** | `sso.example.test` | Duy trì CAS SSO; CAS có thể cấp ST mới | CAS có thể phải login lại |
| **Application JSESSIONID** | `portal.example.test` | Duy trì Spring local authentication | App anonymous sau callback, redirect CAS tiếp |
| **Session store key** | Backend Redis/JDBC/container | Mapping Session ID → SecurityContext | Session cookie có nhưng app không load được state |

**Không xóa TGC rồi giả định app `JSESSIONID` đã bị hủy**, và không xóa JSESSIONID rồi giả định user đã logout hoàn toàn CAS. CAS Single Logout (SLO) có cơ chế riêng; local logout và central logout có lifecycle khác nhau.

### 9.2. Browser không lưu/gửi JSESSIONID

Các lỗi thường gặp:

- `Set-Cookie` có Domain khác hostname người dùng đang truy cập.
- `Path` không bao phủ `/private` hoặc callback/saved request.
- `SameSite` bị browser chặn trong một flow cross-site/embedded nhất định; cookie policy không phù hợp.
- `Secure` cookie chỉ gửi qua HTTPS; app/redirect trở lại HTTP.
- Browser privacy settings, third-party cookie blocking hoặc sandboxed iframe.
- Multiple apps cùng cookie name/domain/path gây session collision.
- Session ID bị regenerate nhưng Set-Cookie của success response bị proxy bỏ.
- Browser chuyển giữa `www.portal` và `portal` khiến cookie host-only không khớp.
- Cookie size/headers bị gateway giới hạn hoặc browser từ chối.
- Proxy tái viết `Set-Cookie: Path/Domain/SameSite` sai.

**Kiểm request kế tiếp đã có Cookie header mang đúng opaque session ID chưa**. Không cần nhìn giá trị cookie thật; trong browser DevTools có thể so existence/attributes theo authorized debugging.

### 9.3. Spring không lưu hoặc không khôi phục SecurityContext

Với Spring Security Servlet stateful, cần đảm bảo:

- `CasAuthenticationFilter`/custom filter lưu successful Authentication vào `SecurityContextRepository`.
- `SecurityContextHolderFilter`/repository load ở request sau theo session.
- Không có `SessionCreationPolicy.STATELESS` hoặc `NullSecurityContextRepository` vô ý trong CAS browser chain.
- Login success handler không invalidate phiên hoặc xóa SecurityContext ngay sau validation.
- Có session fixation strategy hợp lệ, không gọi session invalidation sau khi đã save và mất state.
- Multiple filter chains không làm callback thành công ở chain A nhưng `/private` được xử lý ở chain B với repository khác.
- Spring Session/Redis/JDBC có serializer/version compatible và shared session store.
- Account status/roles/business authorization không bị nhầm với CAS validation failure: **CAS success rồi HTTP 403** có thể là local authorization, không phải CAS ticket error.

Trong Spring Security 6/7, custom authentication filters có thể cần **explicit save**. Javadoc `CasAuthenticationFilter` có `setSecurityContextRepository`. Kiểm behavior đúng version, đừng tự copy cấu hình cũ của Spring Security 5 mà không kiểm session persistence.

### 9.4. Tại sao không nên retry ST khi mất session?

Nếu CAS validation đã **thành công** nhưng app không lưu `JSESSIONID`, dùng lại ST-1 trong browser có thể khiến CAS trả `INVALID_TICKET`, vì ST-1 đã single-use. **Sửa local session**, sau đó tạo **login flow mới với ST mới**. Đừng thay thế session bằng ST cache trong browser.

Spring có `StatelessTicketCache` cho một số **proxy ticket/stateless** integrations, nhưng đó là thiết kế chuyên biệt chứ **không thay thế HttpSession cho browser CAS login**. Không bật cache ticket một cách đại trà để né validation lỗi.

## 10. Phương pháp quan sát: lấy trace mà không làm lộ tickets

### 10.1. Trace tối thiểu một lần login

Ghi nhận theo một **traceId**:

~~~text
01 CLIENT GET /private
   app-authenticated=false
   app-session-present=false

02 APP 302 Location: https://sso.example.test/cas/login?service=<redacted>
   serviceFingerprint=svc-a3b2

03 CAS 302 Location: https://portal.example.test/login/cas?ticket=<REDACTED>
   issuedServiceFingerprint=svc-a3b2

04 CLIENT GET /login/cas?ticket=<REDACTED>
   callbackMatchedCasFilter=true
   appSessionPresent=true/false

05 APP -> CAS /serviceValidate
   validationServiceFingerprint=svc-c7d9
   ticketRef=opaque-hmac-ref

06 CAS -> APP authenticationFailure code=INVALID_SERVICE

07 APP failureHandler -> 302 CAS login
   loginRedirectCount=2
~~~

**Service fingerprint** và **ticketRef** ở đây là định dạng minh họa, không phải SHA-256 thật từ log. Trong production nếu cần correlation của ST, có thể dùng **HMAC với khóa riêng chỉ dành cho quan sát** trên ticket ID, giữ TTL rất ngắn; tránh raw ticket hoặc hash không có secret dễ bị correlation ngoài ý muốn. Với `service`, có thể log **tên cấu hình đã duyệt** hoặc canonical service ID không nhạy cảm, tùy chính sách.

### 10.2. Cần ba giá trị service để so

| Mốc | Giá trị cần biết |
| --- | --- |
| `/cas/login?service=...` | **S_issue**: service mà CAS nhận để cấp ticket |
| URL browser callback | **S_callback**: nơi ST thực sự được gửi; đối chiếu filterProcessesUrl |
| `/cas/serviceValidate?service=...` | **S_validate**: service application đưa tới CAS để validate |

**Nếu `S_issue != S_validate`** → điều tra **`INVALID_SERVICE`**.  
**Nếu `S_callback` không được CAS filter xử lý** → điều tra **routing/filter/entrypoint loop**.  
**Nếu service + validation đúng nhưng session không persist** → điều tra **Cookie/SecurityContext/session store**.

Không chỉ nhìn browser Location rồi tưởng đó là `service` validator dùng; validation là **server-to-server call** và có thể dùng giá trị khác.

### 10.3. HTTP 302 chain: dùng browser/network trace hoặc tool test

Trong môi trường **test, không chứa credentials thực**, có thể quan sát:

~~~bash
curl --head --max-redirs 0 \
  "https://portal.example.test/private"
~~~

`curl -I` dùng HEAD, nên filter behavior có thể khác GET trong một số ứng dụng. Kết quả này hữu ích để nhìn entrypoint `Location` nhưng **không tái hiện đầy đủ browser cookie/SSO loop**. Browser DevTools HAR có thể tái hiện tốt hơn; **phải redact `ticket`, cookies, auth params** trước khi chia sẻ.

Có thể dùng:

~~~bash
curl --location --max-redirs 6 \
  --output /dev/null \
  --write-out 'redirects=%{num_redirects} final=%{http_code}\n' \
  "https://portal.example.test/private"
~~~

Chỉ chạy trong **môi trường/URL thử nghiệm** hoặc được phép, và tránh verbose logs để khỏi ghi authentication tickets trong Location. Redirect count không tự xác định lỗi CAS; cần so CAS logs/app logs.

### 10.4. Tuyệt đối thận trọng khi gọi CAS validation thủ công

Ví dụ protocol-level (không chứa ticket thật):

~~~text
GET /cas/serviceValidate
    ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
    &ticket=ST-FRESH-TEST-TICKET
~~~

Đây là cấu trúc request, không phải ST hợp lệ. Vì validation **tiêu thụ ticket**, chạy `curl`/Postman trực tiếp bằng **ST của một browser đang login** có thể làm browser login thất bại ngay sau đó. Chỉ dùng **ST mới trong test fixture/realm được phép**, và mỗi test **lấy ST mới**.

Tránh:

- Lưu raw ticket vào shell history, CI logs, proxy access logs, screenshots hoặc bug tracker.
- Copy ST từ production HAR sang terminal nhiều người.
- Gửi `ticket` vào hệ thống APM ngoài phạm vi data privacy.
- Thử hàng loạt tickets; ST là credentials nhạy cảm.
- Gọi `/serviceValidate` hai lần bằng cùng ST rồi suy ra kết quả lần hai là nguyên nhân đầu tiên.

## 11. Chẩn đoán theo giả thuyết: phân nhánh nhanh

| Tín hiệu đầu tiên | Giả thuyết | Kiểm tra tiếp | Cách sửa |
| --- | --- | --- | --- |
| **`INVALID_SERVICE`** ngay lần đầu | S_issue ≠ S_validate | Compare decoded service strings, public URL, path | Đồng bộ `ServiceProperties.service` và callback |
| **`INVALID_TICKET`** sau `INVALID_SERVICE` | Ticket đã bị consume | CAS timeline theo ticketRef | Lấy ST mới sau sửa service |
| **`INVALID_TICKET`** ngay lần đầu | Replay/expired/renew/unknown | CAS ticket store/expiry/client logs | Tách đúng root cause |
| **`INVALID_TICKET`** khi `renew=true` | Ticket từ SSO chứ không primary login | sendRenew ở login và validation | Điều chỉnh fresh-auth flow đúng policy |
| **`INVALID_TICKET_SPEC`** với PT | Sai ticket type/validation endpoint | Check PT/ST and /proxyValidate | Dùng đúng protocol endpoint |
| “Application Not Authorized” tại CAS login | Service registry không match | CAS registered services/regex | Sửa registry đúng public callback |
| CAS validation SUCCESS nhưng loop | Session/cookie/ SecurityContext không persist | Set-Cookie vs next Cookie; repository | Fix session store/cookie attributes |
| Không có call tới /serviceValidate | CAS filter không bắt ticket | Callback route/matcher/filter chain | Fix `filterProcessesUrl`/ordering |
| /login/cas trả 302 tới CAS trước validate | Callback bị authorize/redirect sai | Chain matcher, route, saved request | Cho CAS filter xử lý callback đúng |
| Browser ở CAS login liên tục, không thấy callback | CAS SSO/TGC/cookie/login policy | CAS auth logs/cookie domain, MFA/renew | Fix CAS-side cookie/webflow |
| 302 http↔https | Forwarding TLS config | Location URLs / trust proxy headers | Fix trusted external URL scheme |
| Một node ổn, node khác lỗi | Config/session/ticket registry bất nhất | Compare node versions/keys/cache | Đồng bộ configuration/shared store |
| Lỗi sau logout | CAS SSO vs app session lifecycle | SLO events, logout redirect | Thiết kế logout đúng kỳ vọng |
| 403 sau CAS success | Local user/role issue | UserDetailsService / authorities | Fix business authorization, không đổi ST |
| API stateless dùng ST lặp | Không có session, ST single-use | TicketValidator usage/caching | Dùng auth scheme phù hợp API |

**Một 302 chain có thể có nhiều nguyên nhân cùng tồn tại.** Ưu tiên bằng chứng từ **lần validation đầu tiên**; các lỗi downstream như “ticket unknown” sau khi bị consume chỉ là triệu chứng thứ cấp.

## 12. Java 17 độc lập: mô phỏng CAS error codes và redirect loop

Đoạn mã dưới đây là chương trình **Java 17 chạy bằng `javac/java`**, không cần Spring, CAS Server, network hay certificates. Nó mô phỏng chính sách CAS:

- Registry có hai **services được phép**.
- Mỗi ST phát ra gắn **đúng service**.
- `validate` loại ticket khỏi kho **ngay khi có một validation attempt**.
- Khi service khác, trả **INVALID_SERVICE** và ticket vẫn bị tiêu thụ.
- Lặp cùng ticket trả **INVALID_TICKET**.
- Hết hạn, unknown ticket, `renew=true` không thỏa primary login và thiếu parameters bị từ chối.
- Proxy ticket với `/serviceValidate` không được coi là ST.
- Hai mô phỏng redirect loop riêng: mismatch service lặp, và **CAS success nhưng app không giữ session cookie**.
- Trường hợp cấu hình đúng có thể hoàn tất login sau một redirect.

**Cảnh báo:** đây là **mock protocol state machine**; không tạo ST có giá trị, không kết nối CAS, không xác minh authentication thực. Bộ kiểm đúng `service` minh họa **strict matching**, CAS Server thật có thể cấu hình service matching strategy. `sessionCookiePersists` giả lập kết quả browser/session, không phải cookie parser. Mã này **không phải production CAS client, không dùng làm AuthenticationProvider**.

Tệp **CasFailureDiagnosticsDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CasFailureDiagnosticsDemo {
    static final String PUBLIC_SERVICE =
        "https://portal.example.test/login/cas";
    static final String ALTERNATE_SERVICE =
        "https://reports.example.test/login/cas";
    static final Instant NOW = Instant.parse("2026-11-07T10:00:00Z");
    static final Duration TICKET_TTL = Duration.ofMinutes(5);

    record Ticket(String issuedService, Instant createdAt,
                  boolean primaryLogin, boolean proxyTicket) {}
    record Check(String code, boolean accepted) {
        static Check error(String code) {
            return new Check(code, false);
        }
        static Check success() {
            return new Check("AUTHENTICATION_SUCCESS", true);
        }
    }

    static final class MockCas {
        final Set<String> registeredServices =
            new HashSet<>(Set.of(PUBLIC_SERVICE, ALTERNATE_SERVICE));
        final Map<String, Ticket> tickets = new HashMap<>();
        int sequence;

        String issue(String service, boolean primary, Instant now) {
            if (!registeredServices.contains(service)) return null;
            String id = "ST-LAB-" + (++sequence);
            tickets.put(id, new Ticket(service, now, primary, false));
            return id;
        }
        String issueProxy(String service, Instant now) {
            if (!registeredServices.contains(service)) return null;
            String id = "PT-LAB-" + (++sequence);
            tickets.put(id, new Ticket(service, now, true, true));
            return id;
        }
        Check validate(String ticketId, String validationService,
                       boolean renew, Instant now, String endpoint) {
            if (ticketId == null || ticketId.isBlank()
                    || validationService == null
                    || validationService.isBlank()) {
                return Check.error("INVALID_REQUEST");
            }
            // CAS service tickets have single-use validation semantics.
            Ticket ticket = tickets.remove(ticketId);
            if (ticket == null) return Check.error("INVALID_TICKET");
            if (now.isBefore(ticket.createdAt())
                    || !now.isBefore(ticket.createdAt().plus(TICKET_TTL))) {
                return Check.error("INVALID_TICKET");
            }
            if (!ticket.issuedService().equals(validationService)) {
                return Check.error("INVALID_SERVICE");
            }
            if (ticket.proxyTicket()
                    && "/serviceValidate".equals(endpoint)) {
                return Check.error("INVALID_TICKET_SPEC");
            }
            if (renew && !ticket.primaryLogin()) {
                return Check.error("INVALID_TICKET");
            }
            return Check.success();
        }
    }

    static final class LocalApp {
        final MockCas cas;
        final String validationService;
        int serviceValidationFailures;
        int casRedirects;
        boolean sessionCookiePersists;
        boolean authenticatedSession;

        LocalApp(MockCas cas, String validationService,
                 boolean sessionCookiePersists) {
            this.cas = cas;
            this.validationService = validationService;
            this.sessionCookiePersists = sessionCookiePersists;
        }

        boolean visitProtectedResource(int maxCycles) {
            for (int i = 0; i < maxCycles; i++) {
                if (authenticatedSession) return true;
                casRedirects++;
                String newTicket = cas.issue(PUBLIC_SERVICE, false, NOW);
                Check check = cas.validate(newTicket, validationService,
                    false, NOW.plusSeconds(i + 1), "/serviceValidate");
                if (!check.accepted()) {
                    serviceValidationFailures++;
                    continue;
                }
                // A successful CAS validation is not enough if the
                // local SecurityContext/session cookie never persists.
                if (sessionCookiePersists) {
                    authenticatedSession = true;
                }
            }
            return authenticatedSession;
        }
    }

    static void expect(String label, boolean value) {
        System.out.println(label + "=" + value);
    }

    public static void main(String[] args) {
        MockCas cas = new MockCas();
        String valid = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("validTicketAndServiceAccepted",
            cas.validate(valid, PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").accepted());
        expect("sameTicketReplayIsInvalidTicket",
            "INVALID_TICKET".equals(
                cas.validate(valid, PUBLIC_SERVICE, false, NOW,
                    "/serviceValidate").code()));

        String mismatch = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("wrongServiceFirstInvalidService",
            "INVALID_SERVICE".equals(
                cas.validate(mismatch, ALTERNATE_SERVICE, false, NOW,
                    "/serviceValidate").code()));
        expect("mismatchConsumesTicket",
            "INVALID_TICKET".equals(
                cas.validate(mismatch, PUBLIC_SERVICE, false, NOW,
                    "/serviceValidate").code()));

        String wrongScheme = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("httpHttpsMismatch",
            "INVALID_SERVICE".equals(cas.validate(wrongScheme,
                "http://portal.example.test/login/cas", false, NOW,
                "/serviceValidate").code()));

        String wrongPath = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("pathMismatch",
            "INVALID_SERVICE".equals(cas.validate(wrongPath,
                "https://portal.example.test/app/login/cas",
                false, NOW, "/serviceValidate").code()));

        String trailingSlash = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("trailingSlashMismatch",
            "INVALID_SERVICE".equals(cas.validate(trailingSlash,
                PUBLIC_SERVICE + "/", false, NOW,
                "/serviceValidate").code()));

        String queryMismatch = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("queryMismatch",
            "INVALID_SERVICE".equals(cas.validate(queryMismatch,
                PUBLIC_SERVICE + "?lang=vi", false, NOW,
                "/serviceValidate").code()));

        String hostMismatch = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("hostMismatch",
            "INVALID_SERVICE".equals(cas.validate(hostMismatch,
                "https://portal-internal.example.test/login/cas",
                false, NOW, "/serviceValidate").code()));

        String expired = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("expiredTicketRejected",
            "INVALID_TICKET".equals(cas.validate(expired,
                PUBLIC_SERVICE, false, NOW.plusSeconds(301),
                "/serviceValidate").code()));

        String refreshed = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("freshTicketAfterConfigRepairAccepted",
            cas.validate(refreshed, PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").accepted());

        String notRenewed = cas.issue(PUBLIC_SERVICE, false, NOW);
        expect("renewRequiresPrimaryAuthentication",
            "INVALID_TICKET".equals(cas.validate(notRenewed,
                PUBLIC_SERVICE, true, NOW,
                "/serviceValidate").code()));

        String renewed = cas.issue(PUBLIC_SERVICE, true, NOW);
        expect("renewWithPrimaryAuthenticationAccepted",
            cas.validate(renewed, PUBLIC_SERVICE, true, NOW,
                "/serviceValidate").accepted());

        String proxy = cas.issueProxy(PUBLIC_SERVICE, NOW);
        expect("proxyTicketRejectedByServiceValidate",
            "INVALID_TICKET_SPEC".equals(cas.validate(proxy,
                PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").code()));

        expect("missingTicketInvalidRequest",
            "INVALID_REQUEST".equals(cas.validate(null, PUBLIC_SERVICE,
                false, NOW, "/serviceValidate").code()));
        expect("missingServiceInvalidRequest",
            "INVALID_REQUEST".equals(cas.validate("ST-any", null,
                false, NOW, "/serviceValidate").code()));
        expect("unknownTicketInvalidTicket",
            "INVALID_TICKET".equals(cas.validate("ST-unknown",
                PUBLIC_SERVICE, false, NOW,
                "/serviceValidate").code()));
        expect("unregisteredServiceRejectedAtIssuance",
            cas.issue("https://evil.example.test/callback",
                false, NOW) == null);

        LocalApp wrongApp = new LocalApp(new MockCas(),
            "http://portal.example.test/login/cas", true);
        expect("serviceMismatchCausesLoginLoop",
            !wrongApp.visitProtectedResource(3));
        expect("loopRepeatedCASRedirects",
            wrongApp.casRedirects == 3);
        expect("loopRepeatedValidationFailures",
            wrongApp.serviceValidationFailures == 3);

        LocalApp noCookie = new LocalApp(new MockCas(),
            PUBLIC_SERVICE, false);
        expect("lostApplicationSessionCausesLoop",
            !noCookie.visitProtectedResource(3));
        expect("ticketValidationMaySucceedDuringLoop",
            noCookie.serviceValidationFailures == 0);
        expect("missingCookieRepeatedRedirects",
            noCookie.casRedirects == 3);

        LocalApp healthy = new LocalApp(new MockCas(),
            PUBLIC_SERVICE, true);
        expect("healthySessionStopsRedirects",
            healthy.visitProtectedResource(3));
        expect("healthyLoginUsesOneRedirect",
            healthy.casRedirects == 1);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CasFailureDiagnosticsDemo.java
java CasFailureDiagnosticsDemo
~~~

**Stdout chính xác** đã kiểm bằng JDK 17:

~~~text
validTicketAndServiceAccepted=true
sameTicketReplayIsInvalidTicket=true
wrongServiceFirstInvalidService=true
mismatchConsumesTicket=true
httpHttpsMismatch=true
pathMismatch=true
trailingSlashMismatch=true
queryMismatch=true
hostMismatch=true
expiredTicketRejected=true
freshTicketAfterConfigRepairAccepted=true
renewRequiresPrimaryAuthentication=true
renewWithPrimaryAuthenticationAccepted=true
proxyTicketRejectedByServiceValidate=true
missingTicketInvalidRequest=true
missingServiceInvalidRequest=true
unknownTicketInvalidTicket=true
unregisteredServiceRejectedAtIssuance=true
serviceMismatchCausesLoginLoop=true
loopRepeatedCASRedirects=true
loopRepeatedValidationFailures=true
lostApplicationSessionCausesLoop=true
ticketValidationMaySucceedDuringLoop=true
missingCookieRepeatedRedirects=true
healthySessionStopsRedirects=true
healthyLoginUsesOneRedirect=true
~~~

### 12.1. Giải thích kết quả

- `validTicketAndServiceAccepted=true`: ST mới, đúng service và còn hạn được chấp nhận.
- `sameTicketReplayIsInvalidTicket=true`: validate lần hai của ST đã dùng bị từ chối.
- `wrongServiceFirstInvalidService=true`: lần validate đầu sai service trả lỗi tương ứng.
- `mismatchConsumesTicket=true`: sau INVALID_SERVICE, cùng ticket trở thành INVALID_TICKET.
- `httpHttpsMismatch`, `pathMismatch`, `trailingSlashMismatch`, `queryMismatch`, `hostMismatch`: từng biến thể service URI không được strict matcher chấp nhận.
- `expiredTicketRejected=true`: ST quá TTL bị reject.
- `freshTicketAfterConfigRepairAccepted=true`: thay service cho đúng cần **ticket mới**.
- `renewRequiresPrimaryAuthentication=true`: SSO-issued ST không đáp ứng validation renew trong mock.
- `renewWithPrimaryAuthenticationAccepted=true`: ST mới cấp sau primary auth có thể đáp ứng renew.
- `proxyTicketRejectedByServiceValidate=true`: proxy ticket không được thay ST.
- `missingTicketInvalidRequest`, `missingServiceInvalidRequest` và `unknownTicketInvalidTicket`: phân biệt request thiếu parameters và unknown ticket.
- `unregisteredServiceRejectedAtIssuance=true`: service registry chặn dịch vụ lạ **trước khi phát ST**.
- `serviceMismatchCausesLoginLoop=true` và `loopRepeatedValidationFailures=true`: lặp vì CAS validation fail.
- `lostApplicationSessionCausesLoop=true` và `ticketValidationMaySucceedDuringLoop=true`: lặp **dù CAS validation success**, do local session không được giữ.
- `healthySessionStopsRedirects=true`: cả CAS validation lẫn Spring session persistence đúng thì thoát loop.

**Không suy output này là kết quả chạy với một CAS Server thật.** Demo chỉ mô phỏng logic protocol để kiểm nhận thức; integration testing cần server/IdP test thực và Spring CAS filter provider.

## 13. Test matrix: negative và positive controls

| Test | Bố trí | Kỳ vọng |
| --- | --- | --- |
| Baseline fresh ST | CAS login+validation cùng service, cookie app hoạt động | PASS, Authentication và session duy trì |
| Wrong scheme | Ticket cho HTTPS, validate HTTP | INVALID_SERVICE theo strict matching |
| Wrong host | Public hostname vs internal app hostname | INVALID_SERVICE |
| Wrong port | 443 vs 8443 | INVALID_SERVICE nếu identifier không khớp |
| Wrong path | `/login/cas` vs `/app/login/cas` | INVALID_SERVICE |
| Wrong trailing slash | `/login/cas` vs `/login/cas/` | INVALID_SERVICE |
| Query parameter drift | Thêm `?lang=vi` ở một bên | Mismatch theo service matcher |
| Double encoded service | Browser/validator decode không cùng identifier | Registry/mismatch error |
| Ticket cho application khác | CAS ST service B, validate service A | INVALID_SERVICE; ticket tiêu thụ |
| Revalidate same ST | Dùng ST đã SUCCESS | INVALID_TICKET |
| Retry ST sau INVALID_SERVICE | Dùng lại ST cũ sau sửa URL | INVALID_TICKET |
| Fresh ST after fix | Bắt đầu login mới và dùng URL đúng | PASS |
| Expired ST | Chờ quá TTL | INVALID_TICKET |
| Unknown ST | Fake/không có registry record | INVALID_TICKET |
| Missing ticket | `/serviceValidate` không có ticket | INVALID_REQUEST |
| Missing service | `/serviceValidate` không có service | INVALID_REQUEST |
| Renew mismatch | CAS issue từ SSO, validation renew=true | INVALID_TICKET hoặc policy-specific failure |
| Renew primary login | Fresh primary auth + renew policy | PASS nếu các điều kiện khác đúng |
| PT sent to /serviceValidate | Wrong ticket type | FAIL, code tùy implementation/spec |
| Service not registered | CAS login nhận service ngoài allowlist | CAS “not authorized”; **không** gọi đó là INVALID_SERVICE theo ticket match |
| Duplicate callback | Hai filters hoặc hai requests validate cùng ST | Chỉ một attempt thành công, attempt sau FAIL |
| Two replicas, nonshared CAS ticket store | Ticket phát node A, validate node B | FAIL/unknown ticket; fix cluster store |
| CAS TLS trust failed | App không xác minh cert CAS | Fail closed; không disable TLS |
| Filter URL mismatch | Callback không đi qua CasAuthenticationFilter | Loop; không có validation call |
| Wrong SecurityFilterChain | Callback vào chain khác | Loop hoặc 404 |
| CAS validation SUCCESS, no app cookie | Browser không gửi JSESSIONID | Loop dù ST hợp lệ |
| CAS validation SUCCESS, context not saved | NullSecurityContextRepository | Loop/anonymous request sau |
| Cookie Path sai | Session chỉ gửi ở callback không gửi /private | Loop |
| Cookie Domain sai | Host khác nhau qua redirects | Loop |
| Spring Session missing across replicas | Cookie có nhưng node B không restore | Loop |
| CAS TGC blocked | CAS không giữ SSO state | CAS login/cookie errors; có thể loop trong CAS |
| http↔https bounce | Proxy forwarding không đúng | Redirect loop trước CAS validation |
| Callback URL redirects again | Success handler quay lại login page protected | Loop |
| Browser refresh ticket callback | ST đã dùng | INVALID_TICKET, không xem là new login |
| CAS success nhưng user local disabled | UserDetailsService/account status deny | App authentication fail, không hạ policy |
| CAS success nhưng local 403 | Authorities thiếu | 403, không nhầm CAS ticket validation |
| CAS logout rồi app còn session | Không có SLO/invalidation | Có thể vẫn authenticated local |
| App logout rồi CAS còn TGC | App tự SSO login mới | Đúng theo session lifecycle nếu không central logout |
| Request với credential spoof | Client tự đặt `ticket=ST-fake` | Không tạo user; CAS validation bắt buộc |

**Mỗi negative test cần fresh ST độc lập.** Một suite dùng lại ticket giữa tests rất dễ cho kết quả sai vì ST bị consume. **Luôn có positive baseline** cùng CAS config để bảo đảm tests không “pass” chỉ vì mọi request đều thất bại do SSL/ticket store.

## 14. Spring integration testing: kiểm đúng end-to-end

Một test CAS client đúng nên dựng:

1. **CAS Server thử nghiệm** hoặc một HTTP test server mô phỏng chính xác CAS protocol, có cơ chế phát/consume tickets.
2. Spring `CasAuthenticationEntryPoint` và `CasAuthenticationFilter` thực.
3. `CasAuthenticationProvider` với `Cas20ServiceTicketValidator` trỏ đến test CAS endpoint.
4. Browser/HTTP client hỗ trợ cookies và redirects, có kiểm soát max redirects.
5. Test service property đúng, callback URL đúng và một `UserDetailsService` chứa test user.
6. Test **sai một biến mỗi lần**: public HTTPS vs internal HTTP, path/port/query, renew, ticket expiry, duplicate callback, cookie loss.
7. Test CAS verification success thực sự dẫn tới `SecurityContext`/HttpSession được giữ ở request sau.
8. Test error handler có đưa user quay lại login theo policy, nhưng không lặp vô hạn không kiểm soát.
9. Nếu có proxy/ingress, test forwarded headers/host reconstruction ở môi trường tương đương production.
10. Test CAS SLO/logout riêng: app session vs CAS TGC.

Ví dụ **MockMvc skeleton minh họa request callback**, **không phải CAS validation test đầy đủ**:

~~~java
// Cần @SpringBootTest, @AutoConfigureMockMvc và đúng test CAS server.
// ticket là ST mới phát đúng service, KHÔNG dùng ST production.
MvcResult callback = mockMvc.perform(
    get("/login/cas")
        .param("ticket", freshTestServiceTicket)
        .session(browserSession))
    .andReturn();

// Sau callback, kiểm Authentication/session và request /private:
// - ticket validation success -> auth đúng user, local roles đúng
// - session/cookie được persist
// - request protected không lại redirect CAS
// - negative ticket không tạo new auth
~~~

Không đơn giản dùng `SecurityMockMvcRequestPostProcessors.user("alice")` để khẳng định CAS ticket validator hoạt động; nó bỏ qua CAS protocol. Và một ST không được validate hai lần trong hai assertions/calls.

### 14.1. Test login loop với max redirects

Đối với HTTP integration client, đặt **giới hạn redirects** nhỏ, ví dụ 6–10, và assert:

- Normal login không vượt ngưỡng theo môi trường.
- Với wrong service/cookie missing, test phát hiện loop thay vì chạy vô hạn.
- Trace có phân loại: `validationFailureCount > 0` hay `validationSuccessCount > 0 but sessionMissing`.
- Browser không nhận authentication của user khi validation fail.
- Không ghi ticket/cookies trong test logs.
- Sau fix, **login mới** tạo session tồn tại và request sau không redirect.

**Không làm tăng max redirects vô hạn** để “chữa” lỗi. Đây là triệu chứng, không phải setting thiếu.

## 15. Logs/metrics cho quan sát vận hành

### 15.1. Sự kiện đề xuất

**CAS ticket validation thất bại:**

~~~text
event=CAS_TICKET_VALIDATION_FAILED
traceId=trace-73ae
serviceConfigId=portal-public
serviceFingerprint=svc-9fb4
casErrorCode=INVALID_SERVICE
httpCallbackPath=/login/cas
localSessionPresent=false
authPath=CAS_ST
~~~

**Validation thành công nhưng session không duy trì:**

~~~text
event=CAS_LOGIN_SUCCESS_BUT_SESSION_NOT_RESTORED
traceId=trace-744c
serviceConfigId=portal-public
casValidated=true
sessionCookieObserved=false
securityContextRestored=false
nextRequestPath=/private
~~~

**Redirect loop threshold:**

~~~text
event=CAS_REDIRECT_LOOP_SUSPECTED
traceId=trace-818a
appRedirectToCasCount=5
validationFailureCount=5
validationSuccessCount=0
reason=SERVICE_URL_MISMATCH
~~~

Tên event/reason trên là **thiết kế log minh họa**, không phải CAS/Spring builtin log codes.

### 15.2. Metrics nên có

| Metric | Dimensions hợp lý | Cảnh báo |
| --- | --- | --- |
| `cas_login_redirect_total` | service config ID, environment | Redirects tăng không tương ứng logins |
| `cas_ticket_validate_total{result}` | success/fail, protocol error category | Tỷ lệ INVALID_SERVICE/INVALID_TICKET tăng đột biến |
| `cas_ticket_validate_duration` | CAS endpoint group, environment | Timeout/latency tăng |
| `cas_redirects_per_login_flow` | histogram, not ticket ID | Chuỗi redirect quá dài |
| `cas_success_session_missing_total` | service config ID, node | CAS success nhưng không có context ở request sau |
| `cas_ticket_replay_suspected_total` | environment/reason | Replays/duplicate filters |
| `spring_session_restore_failure_total` | node, store backend | Session cookie có nhưng auth mất |
| `cas_unauthorized_service_total` | registered service ID | Service registry mismatch hoặc attack |
| `cas_validation_http_error_total` | status group, TLS/network | CAS endpoint/TLS failures |
| `cas_slo_session_invalidate_total` | integration type | Theo dõi central logout propagation |

**Không đặt `ticket`, username/email/`JSESSIONID`, raw service query hoặc token trên metric labels**: cardinality cao và rủi ro privacy/credential leakage. Dùng service config IDs, HTTP error classes, deployment env và CAS protocol code.

### 15.3. Bật debug có kiểm soát

Trong staging/test có thể bật có thời hạn log categories liên quan Spring Security CAS/CAS client/Apereo CAS và reverse proxy, **theo đúng version**. Log level DEBUG không đồng nghĩa được phép ghi credentials; nếu library vô tình ghi URL đầy đủ `ticket=...`, phải cấu hình redaction từ source/proxy/appender.

Production nên log reason codes và correlation references, không bật `TRACE` trên toàn bộ `org.springframework.security` hoặc toàn bộ HTTP headers trong thời gian dài chỉ để tìm một mismatch.

## 16. Runbook xử lý một sự cố thật

### Pha A — Khoanh vùng trong một flow

1. Chọn một browser/test account được phép; tạo **một phiên mới**.
2. Xác nhận URL đang ở **ứng dụng hay CAS Server**, redirect liên tục giữa host nào.
3. Capture 302 chain **đã redacted** cùng trace ID, status, Location host/path, Set-Cookie/Cookie presence.
4. Lấy **CAS Server validation error đầu tiên** và Spring client validation outcome của **ST đầu tiên**.
5. Nếu không có validation call, kiểm **callback path/chain/filter** trước khi đi sâu vào CAS tickets.
6. Nếu có validation success, chuyển ngay sang nhánh session persistence.
7. Nếu có failure code, phân loại theo bảng ở phần 3; không suy tất cả thành “wrong password”.

### Pha B — Nếu INVALID_SERVICE

1. Lấy **service khi CAS phát ST** (S_issue) từ CAS login request/log.
2. Lấy **service khi TicketValidator validate ST** (S_validate) từ server-side log/redacted trace.
3. So scheme, public/internal host, port, context path, case, slash, query và encoding.
4. So Spring `ServiceProperties.service`, CAS entrypoint, CAS filter URL, TicketValidator.
5. Kiểm CAS registered service: public callback được allow và là giá trị dự kiến.
6. Fix app/proxy/metadata ở **một source of truth**, không mở rộng regex vô tội vạ.
7. **Tạo ST mới** và retest; không dùng lại ST đã INVALID_SERVICE.
8. Confirm success + persisted Spring session + protected resource 200/authorized theo policy.

### Pha C — Nếu INVALID_TICKET

1. Kiểm cùng ticket đã validate trước đó chưa, có duplicate request/filter không.
2. Nếu trước đó có `INVALID_SERVICE`, coi `INVALID_TICKET` sau là secondary effect.
3. Kiểm CAS ticket registry lookup/expiration policy và timestamp.
4. Kiểm `renew=true` ở login/validation, primary-auth expectations.
5. Kiểm ST/PT, endpoint `/serviceValidate`/`/proxyValidate`.
6. Kiểm CAS Server cluster registry storage/replication/keys; có khác staging/prod không.
7. Kiểm browser back/refresh hoặc retry từ load balancer/APM/proxy có gửi lại ST không.
8. Dùng **fresh ST mỗi test**, không kéo dài TTL hoặc disable replay protection.
9. Xác nhận CAS validation sau fix thực sự thành công và local auth được cấp.

### Pha D — Nếu redirect loop nhưng CAS validation SUCCESS

1. Kiểm callback filter tạo Authentication và success handler có chạy không.
2. Kiểm server Set-Cookie `JSESSIONID` sau success.
3. Kiểm browser có gửi Cookie đúng `Domain/Path/SameSite/Secure` ở request kế tiếp không.
4. Kiểm `SecurityContextRepository` đã save/restore context.
5. Kiểm session store/Spring Session/Redis trên nhiều replicas; request có đi node khác không.
6. Kiểm response success redirect có chuyển host/HTTP/port làm cookie không hợp lệ không.
7. Kiểm session fixation handler/logout/CSRF filters có invalidated session ngay sau login không.
8. Kiểm business authorization: thiếu local roles có thể tạo 403, không phải CAS issue.
9. Nếu cookie/repository đúng mà vẫn loop, kiểm SecurityFilterChain matcher/order và redirect target.
10. Lặp lại với browser fresh, ST mới; healthy flow chỉ redirect CAS **một chu kỳ** và tiếp tục dùng app session.

### Pha E — Kiểm đợt triển khai

- Có thay đổi public hostname, TLS termination, context path, ingress headers?
- CAS registered service regex/version/priority có đổi không?
- Spring Boot/Spring Security/CAS client upgraded và thay filter token class/behavior?
- CAS Server ticket registry store/cluster/shared cache có lỗi?
- Deploy version mới đồng bộ trên tất cả nodes chưa?
- Cookie SameSite/Domain/Path thay đổi do proxy hoặc app server?
- Session serializer/schema incompatibility qua rolling deploy?
- CAS logout/SLO policy có đổi không?
- `renew` policy, MFA/step-up flow có đổi không?
- Monitoring có cho phép phân biệt validation failure với session loss không?

## 17. Các anti-pattern nguy hiểm

1. **“INVALID_SERVICE thì đổi mọi service URLs thành regex .*.”** Sai: làm rộng CAS service registry, tăng nguy cơ giả mạo service.
2. **“Thử lại ticket cũ sau khi sửa config.”** Sai: ST single-use; mismatch cũng consume.
3. **“CAS trả INVALID_TICKET nghĩa password user sai.”** Sai: có thể replay/expiry/renew/unknown.
4. **“CAS TGC tồn tại nên Spring app chắc có session.”** Sai: hai cookie khác lifecycle/domain.
5. **“CAS validation SUCCESS mà loop thì cần restart CAS.”** Chưa đúng: xem local cookie/repository/proxy.
6. **“Bỏ xác thực TLS cho CAS URL để test nhanh.”** Sai: đưa ST/identity qua kết nối không đáng tin.
7. **“Bật authenticateAllArtifacts cho tất cả URL sẽ hết lỗi.”** Không phù hợp browser stateful, có rủi ro ticket handling khác.
8. **“Đem ST từ production HAR gọi curl nhiều lần.”** Sai: lộ credentials và tiêu thụ ST.
9. **“Chỉ xem status 302, không xem Location và back-channel.”** Không đủ phân loại vòng lặp.
10. **“Mọi CAS validation HTTP 200 là authenticationSuccess.”** Sai: CAS `/serviceValidate` có thể HTTP 200 nhưng body `authenticationFailure`.
11. **“CAS login cho phép service wildcard, nên không thể INVALID_SERVICE.”** Sai: registry authorization và ticket binding là hai phép kiểm.
12. **“Nếu lỗi một lần, proxy tự retry request /serviceValidate là an toàn.”** Sai: ticket đã được consume; retry sẽ fail hoặc tạo chẩn đoán sai.
13. **“Để cookie Secure nhưng quay lại HTTP chỉ vì LB path.”** Sai: browser không gửi cookie xuống HTTP; sửa public TLS route.
14. **“Chỉ tắt auth cho /login/cas để xử lý callback.”** Không đủ: CAS filter phải bắt ticket và validate, không chỉ permitAll.
15. **“Redirect loop thì tăng maxRedirects.”** Không giải quyết nguyên nhân, chỉ kéo dài loop.
16. **“Cache ST như refresh token.”** Sai: ST là single-use service credential.
17. **“Bỏ sendRenew dù business yêu cầu primary auth.”** Có thể hạ assurance; sửa flow và policy thay vì bypass.
18. **“Thấy /private 200 sau callback nên validation đã thành công.”** Có thể browser còn old SecurityContext; test phải kiểm user/flow mới.
19. **“Thông báo Application Not Authorized chính là INVALID_SERVICE.”** Sai: cần phân biệt registry rejection với ticket validation mismatch.
20. **“Dùng cùng CAS filter trong hai SecurityFilterChains hoặc auto-register hai lần.”** Có thể làm double validation/replay; phải kiểm filter registration.
21. **“Cứ lấy Host/X-Forwarded-Proto từ client để build service URL.”** Mở cửa Host-header spoofing/open redirect; trust proxy only.
22. **“Lưu full ticket trong observability platform.”** Ticket là credential có thể bị lợi dụng khi chưa consume; phải redact.

## 18. Checklist vận hành và code review

- [ ] Đã xác nhận CAS login URL, CAS validation URL và public Spring callback URL.
- [ ] `ServiceProperties.service` nhất quán với `CasAuthenticationFilter.filterProcessesUrl` và CAS registered service.
- [ ] EntryPoint và AuthenticationProvider dùng cùng ServiceProperties hoặc cấu hình equivalent không lệch.
- [ ] `S_issue`, `S_callback`, `S_validate` được so trong cùng một flow.
- [ ] URL-encoding `service` đúng một lần ở tầng HTTP; không có drift query/slash/port.
- [ ] Public scheme/host/port/context path đúng dù app chạy sau ingress/LB.
- [ ] Forwarded/Host headers chỉ tin từ reverse proxy đã xác minh.
- [ ] CAS service registry cho phép đúng service, không wildcard rộng.
- [ ] CAS TLS server certificate được verify và transport HTTPS.
- [ ] Fresh ST được dùng cho **mỗi validation attempt**, không retry ST đã consume.
- [ ] Kết quả `INVALID_SERVICE` được hiểu là đã invalidate ticket.
- [ ] `INVALID_TICKET` được phân nhánh thành replay/expired/renew/unknown/type/registry.
- [ ] `sendRenew` và fresh-auth policy được kiểm với CAS login và validation.
- [ ] ST/PT/PGT và `/serviceValidate` vs `/proxyValidate` không bị nhầm.
- [ ] CAS filter xử lý callback đúng route và đúng SecurityFilterChain, không bị double registration.
- [ ] CAS validation success/failure được parse từ XML body, không chỉ từ HTTP code.
- [ ] App tạo `Authentication` chỉ sau CAS validation success, nạp local roles/tenant.
- [ ] CAS success đi kèm SecurityContextRepository save vào session stateful.
- [ ] Spring session cookie tồn tại và được browser gửi lại trên protected request.
- [ ] Cookie Secure/HttpOnly/SameSite/Domain/Path và public host đã được test.
- [ ] Spring Session/Redis/JDBC/replica configurations nhất quán.
- [ ] Session fixation/logout/SLO không xóa session không đúng thời điểm.
- [ ] Có runbook cho redirect loop trước CAS, tại CAS, tại callback và sau CAS success.
- [ ] Có cap/max redirects trong e2e tests, không tạo infinite loops.
- [ ] Có tests wrong service, mismatch→invalid_ticket, expired, renew, replay, unknown ticket.
- [ ] Có tests CAS success nhưng missing cookie/SecurityContext để phân biệt với validation fail.
- [ ] Có positive baseline và fresh ST khi retest sau fix.
- [ ] Log/metrics có CAS protocol error category và service config ID.
- [ ] Không log raw tickets, TGC, JSESSIONID, user credentials, full validation URL.
- [ ] Các thay đổi registry, public URL và session cookie được review và regression test.

## 19. Câu hỏi tự kiểm tra

**1. CAS `INVALID_SERVICE` và “Application Not Authorized” có giống nhau không?**

Không. `INVALID_SERVICE` là **service gắn vào ticket không khớp service dùng validation**; “Application Not Authorized” thường là CAS service registry từ chối service URL khi login.

**2. Một ST vừa nhận INVALID_SERVICE có thể validate lại với URL đúng không?**

Không. CAS protocol yêu cầu **invalidate ticket sau validation attempt**, kể cả mismatch. Lần sau thường là `INVALID_TICKET`.

**3. Vì sao browser có thể liên tục đi từ app sang CAS dù CAS đã xác thực user?**

Vì app có thể không nhận ticket, validation fail hoặc **không giữ được local SecurityContext/JSESSIONID**, trong khi CAS TGC vẫn tồn tại và cấp ST mới nhanh.

**4. Nếu CAS validation trả XML authenticationSuccess nhưng browser lại vào /login/cas, kiểm gì trước?**

Kiểm **session cookie, SecurityContextRepository, success handler/redirect target và filter chain**. Không mặc định lỗi CAS.

**5. `ServiceProperties.service` nên trỏ tới /private không?**

Thông thường không. Với Spring CAS stateful mặc định, nó nên là **URL callback mà CasAuthenticationFilter giám sát**, ví dụ `https://portal.example.test/login/cas`.

**6. Những sai khác URI nào dễ gây INVALID_SERVICE?**

Scheme HTTP/HTTPS, hostname public/internal, port, context path, trailing slash, query parameters và cách encode.

**7. Vì sao URL registry regex chấp nhận nhiều hosts không đồng nghĩa ST có thể dùng chéo các hosts?**

Registry quyết định ai **được dùng CAS**; ST còn bị **gắn service identifier cụ thể** và phải kiểm đúng khi validation.

**8. `INVALID_TICKET` có nhất thiết là ticket giả không?**

Không. Ticket có thể đã dùng, hết hạn, bị consume do mismatch, không còn trong store hoặc không đáp ứng `renew`.

**9. HTTP 200 từ /serviceValidate có đủ chứng minh login success không?**

Không. Cần đọc `<cas:authenticationSuccess>` hay `<cas:authenticationFailure code=...>` trong body.

**10. CAS `renew=true` khác retry login thế nào?**

Nó yêu cầu **primary authentication freshness** thay vì chỉ dùng CAS SSO session; validation có thể reject ST không thỏa.

**11. Có thể dùng proxy ticket với /serviceValidate không?**

Không như ST thông thường. CAS proxy validation có endpoint/quy tắc riêng, và `/serviceValidate` không được trả success cho PT.

**12. Làm sao biết redirect loop do Cookie hay do CAS protocol?**

Nếu CAS liên tục báo `authenticationFailure`, xử lý ticket/service; nếu CAS liên tục báo `authenticationSuccess` nhưng app vẫn anonymous ở request tiếp, xử lý cookie/SecurityContext.

**13. Browser refresh callback URL có thể gây INVALID_TICKET không?**

Có. ST đã được validate một lần, nên refresh lại `?ticket=ST-...` là replay.

**14. Có nên tăng TTL khi ticket thường xuyên hết hạn?**

Chỉ sau khi điều tra root cause và security review. Không dùng TTL để che double validation, slow callback hay proxy misrouting.

**15. CAS local logout có đồng nghĩa user logout central SSO không?**

Không. CAS TGC và Spring JSESSIONID có lifecycle khác; cần phối hợp Single Logout nếu yêu cầu.

**16. Chỉ cần `http.authorizeHttpRequests(...).permitAll("/login/cas")` là callback CAS chạy?**

Không. Callback còn phải được **CasAuthenticationFilter** bắt, chuyển ST tới TicketValidator và lưu auth/session.

**17. Vì sao nhiều replicas gây INVALID_TICKET hoặc redirect loop?**

CAS ticket registry và Spring session stores là hai tầng riêng; không chia sẻ ticket registry gây unknown ST, không chia sẻ app session gây loop sau validation success.

**18. Có nên đưa Service Ticket vào metric labels để debug?**

Không. ST là credential và có high cardinality; dùng redacted/correlation refs với retention/authorization chặt.

## 20. Tài liệu chính thức

- **Apereo CAS 2.0 Protocol Specification** — `/login`, `/serviceValidate`, `INVALID_SERVICE`, `INVALID_TICKET`, single-use ST, `renew` và proxy tickets: https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html
- **Apereo CAS Protocol Specification (development docs)** — các error codes, CAS ST lifecycle và các endpoint: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- **Apereo CAS Troubleshooting Guide** — “Too many redirects”, `INVALID_TICKET`, registered service mismatch, tickets/SSL: https://apereo.github.io/cas/development/installation/Troubleshooting-Guide.html
- **Apereo CAS Ticket Validation** — service matching strategy và ticket service binding: https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html
- **Apereo CAS Single Logout** — local application sessions vs CAS session/TGC, SLO: https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html
- **Spring Security CAS Authentication** — ServiceProperties, CasAuthenticationEntryPoint, CasAuthenticationFilter, CasAuthenticationProvider, Cas20ServiceTicketValidator, proxy/static: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- **Spring Security Javadoc: CasAuthenticationFilter** — `/login/cas` default, service URL, ticket request parameter và SecurityContextRepository: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html
- **Spring Security Javadoc: ServiceProperties** — service, sendRenew, artifactParameter, authenticateAllArtifacts: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html
- **Spring Security Javadoc: CasAuthenticationProvider** — TicketValidator, ServiceProperties, UserDetailsService, userDetailsChecker: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- **Spring Security Javadoc: CasAuthenticationEntryPoint** — CAS login URL, service URL, redirect behavior: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationEntryPoint.html
- **Spring Security Session Management** — HttpSession, SecurityContextRepository, fixation, explicit save: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- **OWASP Session Management Cheat Sheet** — cookie flags, session fixation, expiration/logout: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- **OWASP Logging Cheat Sheet** — redaction of tokens/secrets và incident-ready logs: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

**Tóm kết:** Khi thấy **CAS `INVALID_SERVICE`**, hãy đối chiếu **service lúc phát ST và service lúc validate**, đồng thời nhớ rằng mismatch **đã tiêu thụ ticket**. Khi thấy **`INVALID_TICKET`**, kiểm **single-use/replay, expiration, renew, unknown ticket, ticket type và CAS cluster**, không suy ngay password sai. Khi thấy **redirect loop**, trước hết hỏi **CAS ticket validation đã thành công chưa**; nếu chưa, đi theo nhánh ticket/service; nếu đã thành công mà Spring vẫn anonymous, đi theo nhánh **JSESSIONID/SecurityContextRepository/session store/filter chain**. Luôn dùng **ST mới khi retest**, giữ HTTPS/service allowlist, không log credentials, và xác nhận điểm kết thúc là **một phiên ứng dụng có thể truy cập tài nguyên đúng quyền mà không redirect vô hạn**.