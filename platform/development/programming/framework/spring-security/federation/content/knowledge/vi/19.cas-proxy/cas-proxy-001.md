# Tình huống dịch vụ cần gọi dịch vụ khác thay mặt người dùng với CAS Proxy

> **Module:** Spring Security – federation. **Nhóm:** CAS Proxy. Chủ đề: Một ứng dụng đã xác thực người dùng bằng Central Authentication Service (CAS) cần gọi một dịch vụ phía sau **thay mặt chính người dùng đó**. Bài học làm rõ các loại vé CAS, luồng **Proxy-Granting Ticket (PGT) → Proxy Ticket (PT)**, chuỗi proxy, chính sách trust và authorization tại từng dịch vụ. Ví dụ thuần **Java 17** chạy độc lập; cấu hình Spring Security CAS trình bày ở mức tích hợp và phải kiểm đúng phiên bản Spring Security/CAS Client, không giả định có một lệnh bật proxy duy nhất trên Spring Boot 3.5.x.

## 1. Mục tiêu và kiến thức đầu vào

Sau bài, người học phải làm được:

1. Giải thích tại sao **Service A đã login qua CAS** không thể đơn giản lấy `JSESSIONID` hoặc Service Ticket của mình gửi sang Service B để gọi API thay user.
2. Phân biệt chính xác **Ticket-Granting Ticket (TGT)**, **Ticket-Granting Cookie (TGC)**, **Service Ticket (ST)**, **Proxy-Granting Ticket (PGT)**, **Proxy-Granting Ticket IOU (PGTIOU)** và **Proxy Ticket (PT)**.
3. Mô tả cách A xin PGT khi xác minh ST thông qua `/serviceValidate` (hoặc `/p3/serviceValidate`), callback `pgtUrl` bằng HTTPS, đối chiếu `pgtIou` và xin PT từ `/proxy` cho **targetService B cố định**.
4. Mô tả cách B xác minh PT tại `/proxyValidate` hoặc `/p3/proxyValidate`, so `service`, xử lý `cas:proxies` và kiểm **chính sách trusted proxies**.
5. Phân định trách nhiệm của CAS Server, browser/user, A (proxying service), B (back-end target), Spring Security filter/provider và tầng authorization nghiệp vụ.
6. Áp dụng chính sách **least privilege**, destination allowlist, TLS, PGT storage, anti-replay, chống SSRF và ngăn chuyển PT/PGT sang service sai.
7. Thiết kế giải pháp Spring Security CAS ở A/B, hiểu `Cas20ProxyTicketValidator`, `ProxyGrantingTicketStorage`, `CasAuthenticationFilter` và `NamedCasProxyDecider` theo phiên bản.
8. Chạy Java 17 demo về chính sách proxy/target và so sánh stdout đã dự đoán; phân biệt demo với validation mật mã/giao thức thật.
9. Viết integration tests với CAS sandbox cho ST, PGTIOU, PGT, PT, /proxyValidate, chains, session expiry, cancellation và security failures.
10. So sánh CAS Proxy với **service account** và **OAuth2 Token Exchange / on-behalf-of** để tránh dùng sai cơ chế ở môi trường mới.

**Kiến thức nền:** CAS login flow, HTTP 302/HTTPS, cookies/HTTP session, CAS `/login` và `/serviceValidate`, Spring Security `Authentication`/`SecurityFilterChain`, TLS/PKIX, backend REST API và phân quyền resource.

**Phiên bản:** Các URL CAS protocol ở đây dựa trên CAS 2.0/3.0. Tài liệu Spring Security CAS có một số đoạn cấu hình XML/namespace từ các phiên bản cũ; phải đối chiếu với **module CAS và Java APIs của đúng phiên bản triển khai**, kiểm compatibility trước khi đưa vào production.

## 2. Bài toán thực tế: Portal cần gọi Reports API

Người dùng Lan đăng nhập **Portal (Service A)** qua CAS. Tại Portal, Lan nhấn “Xem báo cáo của tôi”. Portal cần gọi **Reports API (Service B)** để đọc dữ liệu chỉ Lan được phép xem.

~~~text
Lan + Browser
     |
     | 1. CAS SSO login
     v
Portal A (CAS-protected, stateful web app)
     |
     | 2. Server-to-server call: GET /reports/me
     v
Reports API B (CAS-protected, không có browser session của Lan)
     |
     | 3. Cần biết "đây là Lan, A thay mặt Lan"
     v
Dữ liệu và authorization theo Lan
~~~

**Tại sao không truyền cookie hoặc ST của A?**

- Cookie `JSESSIONID` là phiên local của Portal A, B không nhất thiết dùng cùng session store, và không có lý do được tin cookie đó.
- CAS `TGC` là cookie phiên SSO tại CAS Server, thuộc browser/CAS domain, không phải credential để A truyền cho B.
- CAS `ST-...` của A **chỉ dành cho một service identifier cụ thể**, dùng **một lần** khi A validate; không thể dùng lại cho B.
- User name trong HTTP header `X-User: lan` do A tự gửi **không phải chứng cứ** nếu B chưa có quan hệ ủy quyền và kênh tin cậy.
- Nếu A tự gọi B bằng **service account** của A, B biết “A đang gọi” nhưng chưa chắc biết cách phân biệt hay audit user Lan.

**CAS Proxy** giải bài toán **delegated authentication**: A lấy một **PT riêng** mà CAS phát dành cho **targetService B**, rồi B **tự** kiểm PT với CAS và biết tên user cùng chuỗi proxies được sử dụng. Sau đó B vẫn phải áp **authorization**.

### 2.1. Ai quyết định có nên proxy?

Cần đồng thuận của ít nhất ba bên:

1. **CAS Server** chỉ phát PGT/PT cho services đã được đăng ký và cho phép proxy qua chính sách của nó.
2. **Service A** chỉ xin PT khi người dùng đang có authentication hợp lệ và mục đích gọi B được phép, không chấp nhận targetService tùy ý từ user.
3. **Service B** chỉ chấp nhận PT khi CAS xác minh thành công **và** proxy chain chứa các intermediaries được B cho phép; sau đó kiểm user/tenant/roles/resource ownership.

CAS Proxy **không** tự mang một hệ thống OAuth scopes hoàn chỉnh hoặc bảo đảm mọi thao tác A thay user đều được phép.

## 3. Từ vựng vé CAS: ST, PGT, PGTIOU và PT

| Vật mang | Ai phát | Ai giữ/sử dụng | Công dụng | Ghi chú bảo mật |
| --- | --- | --- | --- | --- |
| **TGT** | CAS Server | CAS server-side ticket registry | Duy trì phiên SSO user | **Không** đưa TGT cho ứng dụng A/B |
| **TGC** | CAS Server | Browser gửi cho CAS | Cookie tham chiếu tới SSO session | Không phải token A gửi B |
| **ST-...** (Service Ticket) | CAS Server | Browser chuyển tới A; A gửi CAS xác minh | Xác thực user **cho service A** | Gắn `service`, one-time, TTL ngắn |
| **PGT-...** (Proxy-Granting Ticket) | CAS Server | **Service A**, thường qua HTTPS callback | Cho phép A xin nhiều PT thay user | **Không one-time**; secret quyền mạnh, cần bảo vệ |
| **PGTIOU-...** | CAS Server | A nhận trong callback và validation response | Ghép đúng PGT callback với ST validation | **Không phải** credential thay PGT |
| **PT-...** (Proxy Ticket) | CAS Server | A nhận rồi trình cho B; B validate CAS | Xác thực user **cho targetService B** | Gắn target, single-use validation, TTL ngắn |
| **CAS user/proxies** | CAS Server trả sau validation | A/B đọc từ response CAS đáng tin | Nhận user và lịch sử proxy | Không tự cấp quyền ứng dụng |

Các tiền tố `ST-`, `PGT-`, `PGTIOU-`, `PT-` giúp minh họa, nhưng **không dùng tiền tố thay việc validation**. Các ticket là bearer secrets: ai chiếm được giá trị thích hợp trong thời hạn có thể thử trình tới service đích.

### 3.1. ST và PT không thể trao đổi mục đích

~~~text
ST-A:
  issued for: https://portal.example.org/login/cas
  validate via CAS /serviceValidate with exact service A
  => only A, one-time

PT-B:
  issued by CAS /proxy using A's PGT,
  targetService = https://reports.example.org/api/cas
  validate via CAS /proxyValidate with exact service B
  => only B, one-time
~~~

Nếu B nhận `ST-A` rồi tự gọi `/proxyValidate` với service B, CAS phải từ chối vì service identifier không khớp. Nếu A dùng lại PT-B lần thứ hai, CAS phải từ chối theo tính single-use. Việc **A có session đã xác thực** không cho phép A tạo “CAS ticket” giả bằng cách gắn username vào JWT riêng.

### 3.2. PGT khác PT thế nào?

**PGT** là “quyền có thể xin proxy tickets tiếp”, vì vậy tác động khi bị lộ lớn hơn nhiều so với một PT ngắn hạn. Theo CAS protocol, PGT **có thể cấp nhiều PT**, không dùng một lần, và phải hết hiệu lực khi user logout CAS theo giao thức/policy; implementer vẫn cần kiểm cấu hình ticket registry, logout/revocation và time-to-live thực tế.

**PT** là một grant cụ thể cho một targetService B, hạn chế service và one-time. Mỗi lần A cần gọi B có thể phải xin PT mới tùy client flow. Không dùng PT-B cho Payroll API nếu nó được cấp cho Reports API.

**PGTIOU** chỉ là một khóa **correlation**, không phải vé truy cập. Giá trị PGTIOU trong CAS validation response phải ghép với cùng PGTIOU ở HTTPS callback để lấy đúng PGT, tránh nhầm các login gần nhau.

## 4. Toàn bộ chuỗi sự kiện từ Browser đến Reports API

Ví dụ các service identifiers:

~~~text
CAS Server base URL:  https://cas.example.org/cas
A callback for login: https://portal.example.org/login/cas
A PGT callback URL:   https://portal.example.org/login/cas/proxyreceptor
B targetService ID:   https://reports.example.org/api/cas
A calls business API: https://reports.example.org/api/reports/me
~~~

**Lưu ý:** `targetService` là identifier mà B yêu cầu lúc **xác thực PT**, **không bắt buộc** giống HTTP endpoint nghiệp vụ. Ví dụ B có một validation callback URL `/api/cas` cố định, trong khi endpoint dữ liệu là `/api/reports/me`. B phải xác định cách nhận PT và truy cập dữ liệu theo kiến trúc thật.

### 4.1. Các bước chi tiết

1. **Browser truy cập A**: `GET https://portal.example.org/private`; A chưa có local authentication.
2. **A gửi browser tới CAS `/login`** với `service=https://portal.example.org/login/cas`.
3. **CAS xác thực Lan** hoặc dùng SSO session TGC sẵn; CAS phát ST cho **service A** và chuyển browser về A: `/login/cas?ticket=ST-...`.
4. **A nhận ST**; khi gọi CAS `/serviceValidate` (hoặc `/p3/serviceValidate`), A gửi `ticket=ST-...`, `service=...A...` và **`pgtUrl=https://portal.example.org/login/cas/proxyreceptor`**.
5. **CAS xác minh ST** đúng service, chưa dùng/hết hạn; đồng thời kiểm policy “A có được proxy không” và HTTPS **PGT callback URL**.
6. **CAS Server mở kết nối HTTPS tới `pgtUrl`**. **Theo CAS 2.0/3.0 protocol callback truyền `pgtId` và `pgtIou` qua HTTP GET query parameters**, không phải POST; CAS phải kiểm TLS/PKIX peer certificate/trust của endpoint. A nhận callback và lưu bản ghi PGT theo PGTIOU với bảo mật tương xứng secret.
7. **A trả HTTP 200 cho callback hợp lệ**; CAS trả validation response cho ST A với `<cas:proxyGrantingTicket>PGTIOU-...</cas:proxyGrantingTicket>`. Nếu callback/trust fail, không có PGT usable; không được giả định proxy đã sẵn sàng.
8. **A ghép PGTIOU của response với callback**, lấy đúng PGT; tạo/giữ local authentication, lưu PGT trong secure storage liên quan user/session và chính sách.
9. **User nhấn xem Reports**; A kiểm quyền khởi tạo chức năng này, không lấy `targetService` từ input tùy ý.
10. **A gọi CAS `/proxy`** qua TLS với `pgt=PGT-...` và `targetService=https://reports.example.org/api/cas`. CAS kiểm PGT hợp lệ, proxy policy và target service, phát **PT-B**.
11. **A gọi B server-to-server** và trình PT-B theo contract của CAS client B (ví dụ HTTPS request có `ticket=PT-...` tại endpoint tiếp nhận CAS). **Không chuyển PGT** sang B.
12. **B gọi CAS `/proxyValidate` hoặc `/p3/proxyValidate`** với `ticket=PT-B` và **`service=https://reports.example.org/api/cas`**. CAS kiểm PT còn hiệu lực, một lần, target đúng và trả user + proxy chain.
13. **B kiểm proxy chain**, chỉ nhận A hoặc tập proxies được tin; lập user principal trong context request nếu pass.
14. **B tự authorization**: user Lan có được quyền xem báo cáo của Lan không, tenant/resource ID đúng không, dữ liệu được phép trả về chưa?
15. **B trả dữ liệu cho A**, A trả giao diện phù hợp cho Browser; log audit user, proxy A, action, outcome và correlation ID đã sanitize.

~~~text
Browser        Portal A             CAS Server               Reports B
   |               |                    |                       |
   | GET /private  |                    |                       |
   |-------------->|                    |                       |
   | 302 /login?service=A               |                       |
   |<--------------|                    |                       |
   |----------------------------------->|                       |
   |   login / TGC / ST-A               |                       |
   |<-----------------------------------|                       |
   |--- GET A?ticket=ST-A ------------->|                       |
   |               |-- /serviceValidate(ST-A, service=A,
   |               |                    pgtUrl=A/callback) ---->|
   |               |------------------->|                       |
   |               |                    |-- HTTPS GET A/callback
   |               |<-- pgtId + pgtIou--|                       |
   |               |---- HTTP 200 ----->|                       |
   |               |<-- user + PGTIOU --|                       |
   |               |                    |                       |
   | GET reports   |                    |                       |
   |-------------->|                    |                       |
   |               |-- /proxy(PGT,targetService=B)              |
   |               |------------------->|                       |
   |               |<------ PT-B -------|                       |
   |               |                    |                       |
   |               |----- HTTPS request with PT-B ------------>|
   |               |                    |      /proxyValidate(PT-B,service=B)
   |               |                    |<----------------------|
   |               |                    |------ user, proxies -->|
   |               |                    |                       | authorize
   |               |<------------------------ report data ------|
   |<-- HTML ------|                    |                       |
~~~

**Chú thích:** Đây là sơ đồ trình tự logic; vị trí mũi tên callback thể hiện kết nối **CAS→A**, không phải browser. Dữ liệu trong PGT callback được gửi **ngoài** response validation, rồi A ghép qua PGTIOU. CAS có thể callback trước khi A nhận response validation. Vì vậy PGT storage phải chịu được bất đồng bộ/race.

## 5. Những URI cần phân biệt

| URI của CAS Server | Ai gọi | Vé/đầu vào | Chức năng |
| --- | --- | --- | --- |
| `/login?service=A` | Browser | CAS TGC hoặc credentials | Phát ST dành A |
| `/serviceValidate?ticket=ST&service=A&pgtUrl=...` | A | ST và optional pgtUrl | Validate **ST**, xin PGT qua callback |
| `/p3/serviceValidate` | A | ST và optional pgtUrl | CAS 3 validation có thêm attributes, cùng semantics |
| `/proxy?pgt=PGT&targetService=B` | A | PGT do A giữ | Xin PT mới cho service B |
| `/proxyValidate?ticket=PT&service=B` | B | PT-B | Validate **PT hoặc ST** với target service |
| `/p3/proxyValidate` | B | PT/ST | CAS 3 proxy validation có attributes |
| `/logout` | Browser hoặc flow logout | CAS session | Kết thúc CAS SSO session theo policy |

**Đừng dùng `/serviceValidate` cho PT-B**: theo CAS protocol, `/proxyValidate` là endpoint hỗ trợ proxy tickets; `/serviceValidate` là endpoint service-ticket validation. Với Apereo CAS 3.0 có biến thể `/p3/...` để trả attributes. Hãy cấu hình đúng base CAS URL và version; ví dụ không nhất thiết phù hợp với mọi CAS server vendor.

**Các URL ví dụ không phải credential thật.** Ticket values có thể xuất hiện ở query string theo CAS protocol, vì vậy TLS là bắt buộc; cần redaction access logs, reverse-proxy logs, browser history/referrer/caches, traces và monitoring. A không nên lưu PT/PGT trong response body hoặc frontend JavaScript.

## 6. PGT callback: cơ chế chứng minh A thực sự là proxying service

A không thể cứ gửi `service=Portal` rồi yêu cầu một PGT bất kỳ. CAS kiểm **pgtUrl** để xác nhận ứng dụng A đang kiểm soát callback tại HTTPS endpoint đã đăng ký.

### 6.1. Bốn bước callback

~~~text
A --> CAS:
  /serviceValidate
    ?ticket=ST-for-A
    &service=https://portal.example.org/login/cas
    &pgtUrl=https://portal.example.org/login/cas/proxyreceptor

CAS --> A over HTTPS GET:
  /login/cas/proxyreceptor
    ?pgtId=PGT-issued-to-A
    &pgtIou=PGTIOU-random

A --> CAS:
  HTTP 200 OK

CAS --> A as ST validation response:
  <cas:proxyGrantingTicket>PGTIOU-random</cas:proxyGrantingTicket>

A:
  lookup PGT by matching PGTIOU
  verify correlation + state + permissions
  store PGT securely for subsequent /proxy
~~~

**Quan trọng:** CAS specification dùng **HTTP GET** khi CAS gửi `pgtId` và `pgtIou` tới proxy callback. Một số tài liệu/implementations có extensions khác (bao gồm chế độ truyền ticket được mã hóa/trực tiếp), không được trộn vào luồng callback tiêu chuẩn. Nếu CAS Server của bạn sử dụng tính năng tùy biến, hãy xác minh hợp đồng và tài liệu chính xác của version đang chạy.

### 6.2. Vì sao phải là HTTPS và PKIX?

CAS gửi **PGT là credential nhạy cảm** tới callback; nếu endpoint giả hoặc TLS verification bị bỏ qua, attacker có thể nhận PGT. Theo CAS protocol, `pgtUrl` phải là HTTPS; CAS phải xây peer trust tối thiểu bằng PKIX certificate chain/signature/validity. Ứng dụng A cũng phải đảm bảo callback URL thuộc allowlist, certificate hợp lệ và routing chỉ trỏ về A, không phải URL được user chọn qua `?pgtUrl=...`.

Mặt khác, **A cần phòng callback giả mạo**. Vì GET callback có thể bị attacker gửi thử, A nên sử dụng network policy, mTLS hoặc reverse-proxy allowlist khi khả thi, kết hợp correlation PGTIOU với một ST validation do CAS tin cậy vừa trả. Một PGTIOU callback không có kết quả CAS validation tương ứng **không được dùng** để tạo authenticated delegated identity.

### 6.3. Race condition và storage

CAS callback có thể tới A gần đồng thời với response validate ST. Nếu A chỉ có một biến static lưu PGT cuối cùng, hai user login cùng lúc có thể ghi đè:

~~~text
ST-Alice -> callback (PGTIOU-1, PGT-1)
ST-Bob   -> callback (PGTIOU-2, PGT-2)

Nếu chỉ lưu "latestPGT" -> có thể mix user!
Đúng: map PGTIOU -> PGT có TTL, concurrency-safe.
Khi validate ST:
  nhận PGTIOU-1 -> lấy PGT-1 đúng với Alice
  nhận PGTIOU-2 -> lấy PGT-2 đúng với Bob
~~~

Đường mapping phải chống replay/đè key, có TTL ngắn cho orphan IOU, cleanup và audit. Với cluster nhiều node, callback vào node khác với node validate ST cần **shared PGT storage** hoặc routing hợp lệ; đừng lưu chỉ in-memory khi cần HA. Giới hạn quyền đọc PGT theo user/session/tenant và không coi PGTIOU là user identity.

### 6.4. Có thể validate ST nhưng không có PGT không?

Có thể ST đã được xác minh như login bình thường nhưng **không có quyền hoặc không lấy được PGT** do proxy policy, TLS callback, connectivity hoặc chưa bật proxy ở CAS. Ứng dụng A có thể cho người dùng vào trang thông thường, nhưng chức năng **gọi B thay người dùng phải fail-closed**, không fallback bằng PGT của user khác hoặc service-account rộng quyền.

Một response có `cas:authenticationSuccess` **không tự chứng minh** PGT acquisition thành công; phải thấy PGTIOU hợp lệ và PGT callback tương ứng.

## 7. Từ PGT đến Proxy Ticket cho dịch vụ B

Sau login, A đã có PGT hợp lệ gắn với user. Khi user gọi tính năng cần B:

~~~text
A có PGT-Alice và targetService=B
    |
    v
GET https://cas.example.org/cas/proxy
    ?pgt=PGT-Alice
    &targetService=https://reports.example.org/api/cas
    |
    v
CAS validate PGT + registered service/proxy policy
    |
    +-- SUCCESS: <cas:proxyTicket>PT-for-B</cas:proxyTicket>
    |
    +-- FAILURE: <cas:proxyFailure code="...">...</...>
    |
A nhận PT-for-B, gọi B qua TLS
B validate PT-for-B với CAS cho targetService=B
~~~

### 7.1. CAS proxySuccess XML mẫu

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:proxySuccess>
    <cas:proxyTicket>PT-demo-target-B</cas:proxyTicket>
  </cas:proxySuccess>
</cas:serviceResponse>
~~~

Đây là XML **giả lập minh họa**, không có một ticket thực. Trước khi tin PT, A phải đảm bảo HTTPS CAS Server đúng được cấu hình, response thuộc request đang xử lý, XML parser an toàn, kết quả success thật và không có lỗi. Không ghi `PT-...` vào logs.

### 7.2. CAS proxyFailure XML mẫu

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:proxyFailure code="UNAUTHORIZED_SERVICE">
    Proxy service is not authorized to request this target
  </cas:proxyFailure>
</cas:serviceResponse>
~~~

Khi có lỗi như `INVALID_REQUEST`, `UNAUTHORIZED_SERVICE` hoặc hết hạn/revoked PGT, A phải **không gọi B với credential giả**. Frontend có thể hiển thị “Không thể truy cập báo cáo lúc này” thay vì tiết lộ ticket hoặc CAS internal configuration.

### 7.3. TargetService là một biên authorization

**Sai:**

~~~java
// Anti-pattern: không đưa input người dùng thành CAS targetService.
String targetService = request.getParameter("targetService");
String proxyUrl = casBaseUrl + "/proxy?targetService=" + targetService;
~~~

Kẻ tấn công có thể yêu cầu A xin PT cho một service khác hoặc khiến A gửi request HTTP tới một host nội bộ (SSRF/open proxy). **Đúng:** A có bảng allowlist cố định cho những targetService mà tính năng được phép sử dụng; không nối chuỗi URL theo input browser, đặc biệt không theo user-provided Host/forwarded headers.

Trong app production, đối với mỗi nghiệp vụ:
- Backend feature `GET_MY_REPORTS` → targetService `https://reports.example.org/api/cas`.
- Backend feature `VIEW_PAYROLL` → targetService khác nếu user và A có quyền; không tự mặc định.
- Không có entry approved → deny.
- Không theo redirect 3xx sang origin ngoài allowlist khi gửi PT. Gửi ticket qua TLS đến đúng endpoint, kiểm certificate và host.
- B kiểm HTTP request URI và resource authorization tương ứng; một PT cho B **không cấp vô hạn mọi quyền tại B**.

## 8. Service B xác minh Proxy Ticket và chuỗi proxy

B **không** được tin HTTP header `X-CAS-User` do A tự tạo. Thay vào đó B nhận PT, gọi CAS `/proxyValidate` với **`service` đúng identifier B**; CAS trả response chứa user và proxy chain nếu hợp lệ.

~~~text
Service A -- PT-B --> Service B
                         |
                         | /proxyValidate(ticket=PT-B, service=B)
                         v
                       CAS Server
                         |
                         +-- PT phát cho B?
                         +-- chưa dùng/hết hạn?
                         +-- user hợp lệ?
                         +-- proxy chain nào?
                         |
                         v
                cas:authenticationSuccess
                cas:user=Lan
                cas:proxies=[https://portal.example.org/.../proxyreceptor]
                         |
Service B:
  - kiểm toàn bộ proxy chain được phép
  - map Lan vào user/tenant của B
  - authorization theo resource
  - trả dữ liệu hoặc 403
~~~

### 8.1. CAS proxyValidate response mẫu

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>lan</cas:user>
    <cas:proxies>
      <cas:proxy>
        https://portal.example.org/login/cas/proxyreceptor
      </cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Giải thích:** `cas:user` là identity được CAS xác thực; `cas:proxies` nêu proxying services trong chuỗi. B cần policy quyết định các proxies nào được chấp nhận. Không sử dụng username trong header HTTP nếu CAS validation đã fail.

### 8.2. Thứ tự proxy chain và độ dài

CAS protocol yêu cầu danh sách proxies phản ánh thứ tự đi qua: **proxy được ghé gần nhất nằm đầu danh sách**. Khi A→Middle→B, B có thể thấy Middle rồi A. B phải quyết định mình chấp nhận trực tiếp A, Middle, hay chuỗi A+Middle theo đúng rule; không chỉ kiểm phần tử đầu hoặc “bất kỳ một proxy hợp lệ” nếu chính sách đòi đủ chuỗi.

Ví dụ:

~~~text
cas:proxies = [
  "https://gateway.example.org/cas/proxyreceptor",
  "https://portal.example.org/login/cas/proxyreceptor"
]

B chỉ tin Portal trực tiếp:
  -> DENY (có intermediary Gateway ngoài hợp đồng)

B tin chính xác Gateway rồi Portal:
  -> MAY ACCEPT, còn phải kiểm user/tenant/action.
~~~

### 8.3. Reject, AcceptAny và Named proxy policy

Spring Security CAS có các loại `CasProxyDecider` trong tài liệu:
- `RejectProxyTickets`: không nhận proxied credentials. Đây là lựa chọn an toàn cho service chỉ yêu cầu direct CAS login.
- `NamedCasProxyDecider`: nhận một danh sách những proxies đã được cấu hình là trusted (cần kiểm semantics của version và chain).
- `AcceptAnyCasProxy`: nhận bất kỳ proxy chain nào; **không phù hợp** với B chứa dữ liệu nhạy cảm nếu chưa có một biên trust khác thật mạnh.

**Tốt nhất:** CAS service registry phải kiểm **A được phép xin PGT/PT**, và B độc lập kiểm **proxy chain** trên từng request. Chỉ một trong hai không đủ. Không cấu hình “accept any proxy” để chữa một lỗi hostname/PGT callback chưa được xác minh.

### 8.4. PT cũng không tự cấp quyền xem báo cáo

B nhận một PT đúng CAS và đúng A vẫn cần kiểm:
- User Lan có active internal account tại B không?
- Tenant của Lan có quyền với báo cáo được yêu cầu không?
- Resource owner/scope/role policy của B cho phép `GET /reports/me` hoặc `GET /reports/{id}` không?
- Có rate limit, audit, read/write separation và chính sách delegation riêng không?
- Nếu A là một ứng dụng đa tenant, identity được map theo CAS issuer/service context có tránh trùng username không?

Một vé CAS chứng minh **authentication/delegation path**, không phải “Lan là admin” hoặc “A được thao tác dữ liệu của mọi người”.

## 9. Cấu hình Spring Security CAS: A và B khác nhau ở đâu?

Tài liệu Spring Security CAS mô tả những thành phần chính:
- `CasAuthenticationEntryPoint`: chuyển browser A tới CAS `/login` khi cần xác thực.
- `ServiceProperties`: định danh callback URL của A; `service` phải đúng CAS service identifier.
- `CasAuthenticationFilter`: nhận `ST`/`PT` qua URL đã cấu hình, tạo token để xác minh; có thể xử lý **proxy receptor** khi được cấp PGT storage.
- `CasAuthenticationProvider`: xác thực bằng `TicketValidator` CAS Client, nạp user details/authorities của ứng dụng.
- `Cas20ServiceTicketValidator`: kiểm ST cho flow thông thường.
- `Cas20ProxyTicketValidator`: dùng khi cần proxy support/PGT callback và validate PT phù hợp.
- `ProxyGrantingTicketStorage`: giữ PGT theo PGTIOU; liên hệ `CasAuthenticationFilter` và ticket validator.
- `CasProxyDecider`: quyết định tin chuỗi proxies nào, nhất là ở B.

**Cẩn thận:** Các Spring CAS docs vẫn trình bày nhiều snippet XML cấu hình lịch sử. Chúng mang giá trị về thành phần và flow nhưng **không phải một ứng dụng Spring Boot 3.5 có thể copy-paste chạy nguyên trạng**. Phải dùng `spring-security-cas` và CAS Client version tương thích, cấu hình Spring Security 6.5 APIs/filters bằng Java hoặc XML/bean definitions được kiểm thử.

### 9.1. Các thành phần tại A

Service A đóng hai vai:
1. **Nhận login bằng ST**: CAS filter/AuthenticationProvider kiểm ST của browser để tạo local authenticated session.
2. **Là proxying client**: ticket validator của A xin PGT bằng `pgtUrl`; filter của A nhận CAS callback, storage giữ PGT; backend client dùng PGT xin PT cho B.

**Đoạn XML cấu hình lịch sử minh họa mối liên hệ (không phải pom/app hoàn chỉnh):**

~~~xml
<!-- Phải xác nhận các API/constructor và thư viện với version thực tế. -->
<bean id="pgtStorage"
      class="org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl"/>

<bean id="proxyTicketValidator"
      class="org.apereo.cas.client.validation.Cas20ProxyTicketValidator">
  <constructor-arg value="https://cas.example.org/cas"/>
  <property name="proxyCallbackUrl"
            value="https://portal.example.org/login/cas/proxyreceptor"/>
  <property name="proxyGrantingTicketStorage" ref="pgtStorage"/>
</bean>

<bean id="casAuthenticationProvider"
      class="org.springframework.security.cas.authentication.CasAuthenticationProvider">
  <property name="ticketValidator" ref="proxyTicketValidator"/>
  <!-- serviceProperties, authenticationUserDetailsService,
       key và các thành phần bắt buộc khác phải được cấu hình thêm -->
</bean>

<bean id="casAuthenticationFilter"
      class="org.springframework.security.cas.web.CasAuthenticationFilter">
  <property name="proxyGrantingTicketStorage" ref="pgtStorage"/>
  <property name="proxyReceptorUrl"
            value="/login/cas/proxyreceptor"/>
  <!-- authenticationManager và filter chain chưa thể thiếu -->
</bean>
~~~

**Điểm bắt buộc:** `Cas20ProxyTicketValidator.proxyCallbackUrl` phải trỏ **đúng public HTTPS URL** mà CAS Server gọi, và `CasAuthenticationFilter.proxyReceptorUrl` phải match **đường nhận callback ở A** (đặc biệt khi sau reverse proxy). Cả ticket validator và filter phải dùng **cùng PGT storage**. Không dùng một global map ngoài framework để lưu “PGT hiện tại”.

### 9.2. A phải biết PGT của user nào

Đối với các ứng dụng stateful, Spring CAS provider/filter có thể lưu kết quả xác thực chứa CAS Assertion và ticket-related information. Từ lớp proxy client, cần xác định PGT/PGTIOU liên hệ đúng authenticated user/session. Nếu không có PGT do callback fail, không được lấy “PGT gần nhất” từ singleton.

PGT storage phải:
- Bảo vệ secrets at rest/in transit, encrypt nếu cần, RBAC least privilege.
- Có TTL, cleanup expired entries và số lượng bounded.
- Chịu concurrency/race và callback out-of-order.
- Hỗ trợ distributed session/cache khi chạy cluster (nếu cần).
- Không log PGT values/PGTIOU trực tiếp trong request logging.
- Thu hồi/cleanup khi user logout CAS hoặc app policy kết thúc session.
- Tránh công bố API “lấy PGT theo username” cho code không có quyền.

Trong Spring docs, `ProxyGrantingTicketStorageImpl` là ví dụ in-memory; docs cảnh báo **không dùng mặc định làm storage production** và phải cleanup. Việc bạn chọn Redis/DB/KMS hoặc implementation khác phải phù hợp ticket lifecycle và security controls.

### 9.3. B: nhận PT qua CAS validation rồi tự authorization

B cần `Cas20ProxyTicketValidator` hoặc validator tương đương thay vì chỉ `Cas20ServiceTicketValidator`. B đặt **service URL của chính nó** trong `ServiceProperties`/`ServiceAuthenticationDetails` và phân quyền proxy chain qua `CasProxyDecider`. Với stateless API, CAS client filter có thể xử lý request ticket trên mỗi request, nhưng phải bảo vệ replay/idempotency và cách truyền credential.

**Sơ đồ bean trách nhiệm** (conceptual, không đủ để chạy độc lập):

~~~text
B SecurityFilterChain
  -> CasAuthenticationFilter
       |__ serviceUrl resolver cho B
       |__ AuthenticationManager
            |__ CasAuthenticationProvider
                 |__ Cas20ProxyTicketValidator(CAS base URL)
                 |__ NamedCasProxyDecider(approved A callback URLs)
                 |__ user/authority service
  -> method/API authorization theo user + proxy identity
~~~

Cấu hình Spring Security CAS cho **stateless service** có điểm khác stateful Portal; CAS docs mô tả `authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource` và CAS stateless identifier. Đừng tự nghĩ rằng chỉ đặt `sessionCreationPolicy(STATELESS)` là một API sẽ validate PT đúng. Cần wiring CAS-specific filter/provider/ticket validation, và security review trên request URL/service identity.

### 9.4. Dependencies và phiên bản

Nếu thiết lập Spring Boot 3.5.x với Java 17, việc dùng CAS integration thường cần **module Spring Security CAS và thư viện Apereo CAS Client** tương thích, ngoài `spring-boot-starter-security`/`spring-boot-starter-web`. Không có property chuẩn kiểu `spring.security.cas.proxy.enabled=true` tự hoàn tất toàn bộ flow. Các package/class trong tài liệu Spring có thể khác theo lịch sử; kiểm Maven dependency tree/API trước khi xây SecurityFilterChain.

**Lựa chọn hiện đại:** Nếu nhu cầu chính là “API A gọi API B thay user” và B không bắt buộc sử dụng CAS protocol, cân nhắc **OAuth2 Token Exchange/on-behalf-of** với audience/scopes/consent và token validation phù hợp. Không tự xây converter từ CAS PGT sang JWT mà không có Authorization Server được tin.

## 10. Chính sách CAS Server: không phát PGT bừa bãi

CAS service registry phải có các entries đã được quản trị phê duyệt:

~~~text
Registered CAS Service A
  serviceId = https://portal.example.org/login/cas
  allowProxy = true, có điều kiện
  approved pgtUrl = https://portal.example.org/login/cas/proxyreceptor
  allowed/approved target services (theo CAS policy)
  attributes released = tối thiểu

Registered CAS Service B
  serviceId = https://reports.example.org/api/cas
  mayAcceptProxyTickets = true (theo CAS implementation)
  trusted proxiers = Service A (và chain cụ thể)
~~~

**Đây là pseudoconfiguration**, không phải JSON/YAML đúng của mọi phiên bản Apereo CAS. CAS Server/registry hỗ trợ proxy policy theo phiên bản và loại registration. Các triển khai Apereo hiện đại có thể **mặc định không cho proxy** nếu service chưa được duyệt; không suy rằng “CAS Proxy được mô tả trong protocol” nghĩa bất kỳ ứng dụng nào cũng xin được PGT.

### 10.1. Những policy cần khóa chặt

- Service IDs/`targetService` được đăng ký với CAS, không regex `.*` hay wildcard host rộng.
- Chỉ Service A đã duyệt được xin PGT, chỉ callback HTTPS đã duyệt.
- Callback certificate phải được CAS verify PKIX, không bypass trust manager.
- Chỉ PT đến targetService được phép; nếu CAS registry không enforce đủ, A còn có allowlist riêng.
- B phải deny unknown proxy chains, không `AcceptAnyCasProxy` khi không có một trust boundary thay thế.
- Ticket TTL, PGT inactivity, session logout revocation, audit, rate limits phải theo threat model.
- Authorization downstream (B) phải áp quyền user/tenant; CAS proxy không phải resource scope engine.

### 10.2. Không để pgtUrl thành SSRF

Vì CAS **chủ động gọi pgtUrl**, một service có khả năng chỉ định pgtUrl tùy ý có thể làm CAS Server gửi request tới địa chỉ nội bộ hoặc attacker, hoặc làm lộ PGT. Hãy giới hạn pgtUrl theo service registry và chính sách egress/URL validation, cấm redirects tới IP nội bộ/link-local/metadata endpoints, chỉ cho HTTPS, verify certificate chain/host. Không chấp nhận `https://example.org.evil.test` chỉ vì chứa substring.

A cũng phải không cho user sửa `pgtUrl`, CAS base URL hoặc targetService qua query params. Không bật mode trust-all certificates để debug.

## 11. Java 17 độc lập: policy A gọi B thay user

Mã sau **chạy được với JDK 17**, không cần Maven/CAS Server. Nó mô phỏng quyết định **có chấp nhận targetService B và proxy chain** trước khi request delegated được thực hiện. Mục tiêu là học chính sách “allowlist và fail-closed”, **không** tạo PGT/PT thật, không parse CAS XML, không validate TLS hoặc security assertion. Trong production, phải dùng CAS Client/Spring CAS validation chuẩn.

**Tệp `CasProxyPolicyDemo.java`:**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CasProxyPolicyDemo {

    record Request(String user, String action, String targetService) {}

    static final String REPORTS =
            "https://reports.example.org/api/cas";
    static final String PAYROLL =
            "https://payroll.example.org/api/cas";
    static final String PROXY_A =
            "https://portal.example.org/login/cas/proxyreceptor";

    // Chỉ những actions đã phê duyệt mới ánh xạ tới targetService.
    static final Map<String, String> APPROVED_ACTIONS = Map.of(
            "READ_MY_REPORTS", REPORTS);

    static final Set<String> ENABLED_USERS = Set.of("lan");

    static String authorizeProxyRequest(Request request) {
        if (!ENABLED_USERS.contains(request.user())) {
            return "DENY_USER";
        }
        String approved = APPROVED_ACTIONS.get(request.action());
        if (approved == null || !approved.equals(request.targetService())) {
            return "DENY_TARGET";
        }
        return "ALLOW_PGT_TO_PT";
    }

    // Chuỗi proxies phải được CAS xác nhận, không lấy từ header HTTP.
    static String authorizeBackend(
            String validatedCasUser,
            List<String> validatedProxyChain,
            String resourceOwner) {
        if (!ENABLED_USERS.contains(validatedCasUser)) {
            return "DENY_USER";
        }
        if (!validatedProxyChain.equals(List.of(PROXY_A))) {
            return "DENY_PROXY_CHAIN";
        }
        if (!validatedCasUser.equals(resourceOwner)) {
            return "DENY_RESOURCE";
        }
        return "ALLOW_REPORT";
    }

    public static void main(String[] args) {
        System.out.println("A valid=" + authorizeProxyRequest(
                new Request("lan", "READ_MY_REPORTS", REPORTS)));
        System.out.println("A otherTarget=" + authorizeProxyRequest(
                new Request("lan", "READ_MY_REPORTS", PAYROLL)));
        System.out.println("A disabled=" + authorizeProxyRequest(
                new Request("bob", "READ_MY_REPORTS", REPORTS)));

        System.out.println("B trusted=" +
                authorizeBackend("lan", List.of(PROXY_A), "lan"));
        System.out.println("B unknownProxy=" +
                authorizeBackend("lan",
                        List.of("https://evil.example/proxy"), "lan"));
        System.out.println("B extraHop=" +
                authorizeBackend("lan",
                        List.of("https://gateway.example/proxy", PROXY_A),
                        "lan"));
        System.out.println("B otherOwner=" +
                authorizeBackend("lan", List.of(PROXY_A), "bob"));
    }
}
~~~

Chạy:

~~~bash
javac CasProxyPolicyDemo.java
java CasProxyPolicyDemo
~~~

**Stdout chính xác:**

~~~text
A valid=ALLOW_PGT_TO_PT
A otherTarget=DENY_TARGET
A disabled=DENY_USER
B trusted=ALLOW_REPORT
B unknownProxy=DENY_PROXY_CHAIN
B extraHop=DENY_PROXY_CHAIN
B otherOwner=DENY_RESOURCE
~~~

**Giải thích từng kết quả:**

1. A chỉ được xin PT cho Reports khi user active và action `READ_MY_REPORTS` map đúng targetService.
2. A từ chối target Payroll dù user ghi `READ_MY_REPORTS`; không cho chọn target tùy ý.
3. User Bob không được mô phỏng là active, A từ chối.
4. B chấp nhận proxy chain **đã được CAS xác thực** gồm đúng A, và user Lan chỉ xem dữ liệu của Lan.
5. Proxy lạ bị B từ chối.
6. Chuỗi A→Gateway→B có thêm trung gian, bị B từ chối vì policy chỉ cho A trực tiếp.
7. Người dùng Lan không được đọc báo cáo của Bob chỉ vì đã có PT hợp lệ.

**Giới hạn:** `validatedCasUser` và `validatedProxyChain` trong demo là **tham số giả định đã đến từ CAS validation thành công**. Nếu production lấy từ HTTP header, request parameter hoặc XML chưa validate, kẻ tấn công có thể điền tuỳ ý và bypass. Demo không thể chứng minh CAS ticket thật; chỉ là unit test cho *authorization policy sau giao thức*.

## 12. Spring Boot 3.5/Java 17: ứng dụng B sau lớp CAS validation

Một lỗi kiến trúc là đưa toàn bộ CAS ticket validation vào controller nghiệp vụ thay vì filter/provider. Với Spring Boot 3.5.x, hãy gắn CAS adapter/filter trong SecurityFilterChain và chỉ cho MVC controller chạy khi authentication context đã được tạo.

**Code `ReportsController.java` dưới đây là skeleton Spring MVC**, có thể được biên dịch trong Spring Boot web + security project, nhưng **không tự triển khai CAS filter/ticket validation**. Nếu chưa có filter CAS, `Authentication` có thể đến từ cơ chế khác và **không được coi là đã CAS-proxy-validated**. Phải cấu hình CAS SecurityFilterChain riêng và guard loại authentication trước production.

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    // Chỉ dùng khi CAS authentication/provider đã được cấu hình.
    // Trong production phải kiểm authenticated CAS token,
    // approved proxies, tenant membership và resource access.
    @GetMapping("/api/reports/me")
    public ResponseEntity<Map<String, String>> myReports(
            Authentication authentication) {

        if (authentication == null || !authentication.isAuthenticated()) {
            return ResponseEntity.status(401)
                    .body(Map.of("error", "unauthenticated"));
        }
        // Đây là minh hoạ API response, KHÔNG phải quyết định
        // authorization hoàn chỉnh cho CAS proxy.
        return ResponseEntity.ok(Map.of(
                "user", authentication.getName(),
                "status", "authenticated"));
    }
}
~~~

**Phải hiểu rõ:** Code trên không chứa validation CAS PT, không xác minh proxy chain hoặc resource ownership; vì vậy **không được deploy như endpoint dữ liệu nhạy cảm** nếu không có security layer tương ứng. Trong hệ thống thật, check `CasAuthenticationToken`/details và quyền tenant/role trước khi truy xuất DB. Nếu token đến từ người dùng direct CAS login nhưng action yêu cầu proxied authentication, phải phân biệt và reject.

### 12.1. Những phần cần cấu hình tại A

- `CasAuthenticationEntryPoint` dẫn browser tới CAS `/login`.
- `ServiceProperties` đúng A callback service URL, được đăng ký tại CAS.
- `CasAuthenticationFilter` nhận ST và xử lý PGT callback `proxyReceptorUrl`.
- `CasAuthenticationProvider` dùng `Cas20ProxyTicketValidator`, `proxyCallbackUrl` và `ProxyGrantingTicketStorage`.
- `AuthenticationUserDetailsService` chỉ nạp roles/permissions đã phê duyệt; không nhận group strings tùy tiện thành admin.
- Storage có concurrency-safe IOU correlation, TTL, secure cleanup, cluster support.
- Service backend client lấy PT theo approved targetService, không truyền raw PGT tới B.

### 12.2. Những phần cần cấu hình tại B

- `ServiceProperties.service` đúng B service identifier, không lấy từ arbitrary Host.
- CAS filter/provider dùng `Cas20ProxyTicketValidator` (hoặc version/client equivalent) và `CasProxyDecider` deny-by-default.
- Validate ST/PT qua CAS Server TLS; kiểm CAS response authenticationSuccess, user, proxies, service binding và ticket replay/time.
- API authorization và identity linking riêng. Khi nhận PT, yêu cầu user và proxy chain đúng policy.
- Stateless requests không lưu chung session từ nhiều user; CAS PT là bearer one-time, phải thiết kế call lifecycle tương thích.
- Chặn direct access qua header `X-Authenticated-User` và bảo đảm không có một filter chain khác permitAll cùng URL.

**Đừng chỉ tin rằng Spring Security CAS authentication thành công là user được quyền xem mọi dữ liệu.** CAS provider xác thực, domain authorization tại B chịu trách nhiệm tiếp.

## 13. Vì sao targetService phải chính xác?

CAS PT bị ràng buộc với targetService được chỉ định lúc A xin PT. B xác minh PT bằng chính service identifier của B.

~~~text
A requests from CAS:
  /proxy?pgt=PGT-...&targetService=https://reports.example.org/api/cas

CAS issues:
  PT-... specifically for https://reports.example.org/api/cas

B validates:
  /proxyValidate?ticket=PT-...&service=https://reports.example.org/api/cas
  -> YES if valid and unused

B uses wrong service:
  /proxyValidate?ticket=PT-...&service=https://payroll.example.org/api/cas
  -> INVALID_SERVICE / failure
~~~

Phân biệt `targetService` identifier với URL endpoint business call. Trong CAS client, service URL đôi khi được xây từ request; backend sau proxy cần cấu hình/canonicalize chính xác scheme/host/port/path và chỉ tin forwarded headers từ **trusted reverse proxy**. Nếu B đang ở `http://service-b:8080` nhưng public CAS service ID là `https://reports.example.org/api/cas`, validation fail do mismatch. **Không khắc phục bằng wildcard validation**, phải sửa service identity/proxy configuration.

### 13.1. One-time validation và retry

PT được thiết kế cho **một lần validation**. Nếu A gọi B và timeout sau khi B đã validate PT, A **không thể** retry cùng PT và mong CAS chấp nhận lần hai. Cần có logic lấy PT mới, idempotency key nghiệp vụ và retry policy được kiểm soát. Với action ghi (payment/update), tuyệt đối không tự động làm lại business operation chỉ vì ticket validation response bị mất mà không có deduplication; delegated authentication và **business idempotency** là hai vấn đề riêng.

### 13.2. Không reuse PGT giữa users

PGT gắn user/session cụ thể. Một service A phục vụ hàng trăm người phải liên hệ PGT và authenticated context bằng khóa an toàn, không lấy một global `currentPGT`. Khi session hết hạn hoặc logout, phải xử lý revocation/cleanup và tránh queuing long-running jobs bằng credential của user đã rời phiên. Nếu một background job chạy sau logout, cần mô hình workload authorization đã phê duyệt, không âm thầm dùng PGT tồn tại mãi.

## 14. Chuỗi proxy nhiều hop: A → B → C

Một tình huống phức tạp hơn: Portal A cần Reports B, và B lại cần gọi Document Store C thay user. B muốn proxy tiếp, nó phải **được phép** và có khả năng xin PGT khi validate PT nó nhận, bằng `pgtUrl` tương ứng B.

~~~text
Lan Browser -> A
  CAS ST-A validation
      -> A PGT-A
  A /proxy(PGT-A,target=B)
      -> PT-B
  B /proxyValidate(PT-B,service=B,pgtUrl=B/receptor)
      -> B PGT-B (nếu allowed)
  B /proxy(PGT-B,target=C)
      -> PT-C
  C /proxyValidate(PT-C,service=C)
      -> cas:user=Lan
      -> cas:proxies có B trước A (most recent first)
~~~

**Không thể** vì B có PT-B mà tự ký/đổi tên nó thành PT-C. B phải xin PGT-B theo CAS proxy callback và xin PT-C từ CAS, hoặc sử dụng cơ chế ủy quyền khác được cấp phép.

### 14.1. Policy chuỗi nhiều hop

C có thể:
- Chỉ chấp nhận direct user CAS ST, không nhận PT (deny mọi proxies).
- Cho phép một hop từ A nhưng không qua B.
- Cho phép chính xác chain `[B, A]` theo thứ tự CAS trả.
- Cho phép một tập proxies nhưng có giới hạn số hop/tenant/action.

**Không kiểm chuỗi bằng** `proxies.contains("https://portal.example.org")` nếu còn proxy trung gian không tin; một phần tử tốt không làm cả chain an toàn. Không cho phép các proxy identities bắt đầu bằng substring/host suffix không được kiểm chuẩn.

### 14.2. Nếu B không được cấp PGT

Không thể proxy tiếp C dù B đã xác thực PT-B thành công. Đây là thiết kế an toàn hợp lý: quyền **được nhận delegated identity** khác quyền **được tiếp tục delegate**. CAS Server cần registry/PGT policy rõ cho từng service hop. B nên trả lỗi nghiệp vụ phù hợp, không dùng service account thay user mà không thông báo và không bypass proxy policy.

## 15. Authentication khác authorization và audit

Trong Reports B:

~~~text
CAS proxyValidate passes:
  principal=lan
  proxyChain=[Portal A]

Still not enough!
  |
  +-- internal identity link for CAS user?
  +-- user is active?
  +-- tenant scope matches?
  +-- action READ_MY_REPORTS allowed?
  +-- report belongs to Lan?
  +-- sensitive data redaction/purpose limitation?
  +-- rate limit / audit?
  |
  v
  200 data or 403
~~~

**CAS authentication** trả user/proxy chain theo trust; **authorization** quyết định hành động cụ thể. Nếu A được phép gọi B thay Lan, B không tự được trả dữ liệu Bob. Nếu CAS username `lan` có thể tồn tại ở nhiều CAS realms/tenants, B phải gắn CAS server issuer/registration vào identity link, không chỉ dùng bare username/email.

**Audit nên ghi** tenant, internal user ID, A/B service IDs, proxy chain đã chuẩn hóa, business action, resource ID đã sanitize, correlation ID và kết quả. **Không ghi** ST/PT/PGT/PGTIOU, cookies, raw XML attributes hoặc credentials. Vì CAS tickets có thể đi qua query, cần redaction từ ingress, app access logs, APM, tracing, errors và support screenshots.

## 16. So sánh lựa chọn thiết kế

| Phương án | Dùng khi | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **CAS Proxy (PGT/PT)** | A/B đều là CAS services, cần delegated user identity, CAS Server/registry hỗ trợ | Hợp CAS trust, PT target-bound và single-use, có proxy chain | Cấu hình callback/TLS/storage phức tạp; không có scopes OAuth chuẩn |
| **Service account của A** | B cần biết hệ thống A là caller, thao tác không nhất thiết “như user” | Đơn giản cho machine-to-machine, không phụ thuộc user session | Không đại diện quyền user; nếu truyền user header phải có thiết kế xác thực/audit bổ sung |
| **OAuth2 Token Exchange / OBO** | API hiện đại đã có Authorization Server, audience/scopes/delegation được thiết kế | Token cho resource/scope, dễ tích hợp APIs, chuẩn hóa policy | Cần AS/RS hỗ trợ; không tự đổi CAS PT thành OAuth token |
| **User direct-login B** | Browser có thể điều hướng tới B và B hỗ trợ CAS | Không cần A giữ PGT | Không giải được server-to-server call không có browser |
| **Truyền CAS ST-A sang B** | **Không dùng** | Không có | ST service-bound và one-time, B phải reject |
| **Dùng PGT-A trực tiếp làm B bearer token** | **Không dùng** | Không có | Tiết lộ credential có quyền xin nhiều PT |

**Lựa chọn theo “ai hành động” và “quyền gì”**: Nếu hệ thống cần chính xác “A làm thay Lan tại B” và cả hai đều CAS, dùng CAS Proxy với chain validation. Nếu chỉ là job hệ thống không gắn user, service account và scoped authorization có thể phù hợp hơn. Nếu kiến trúc mới là OAuth2/OIDC API, cân nhắc tiêu chuẩn delegated access riêng; không trộn mà thiếu trust translation.

## 17. Kiểm thử positive/negative với CAS sandbox

| Test | Thực hiện | Kỳ vọng |
| --- | --- | --- |
| ST login hợp lệ | User login A, CAS phát ST-A cho đúng service | A authenticated |
| ST replay | Gửi lại ST-A sau validation | CAS từ chối |
| ST wrong service | Validate ST-A với service B | `INVALID_SERVICE` / fail |
| A không gửi pgtUrl | Validate ST bình thường | Login có thể pass nhưng không có PGT cho proxy |
| A xin PGT policy denied | A chưa được CAS cho phép proxy | Không cấp PGT; B call fail-closed |
| PGT callback HTTPS/TLS lỗi | CAS không tin cert callback hoặc không reach | Không có usable PGT |
| Callback khác approved URL | `pgtUrl` do user/attacker điều khiển | Deny, không gửi PGT |
| Callback trả non-200 | Receptor lỗi | PGT issuance không thành công |
| Callback đến trước validation response | Race giữa CAS callback và A | Storage ghép PGTIOU đúng |
| Concurrent Alice/Bob | Hai PGTIOU xen kẽ | Không tráo PGT giữa users |
| PGTIOU mismatch | Có callback PGT-1 nhưng response PGTIOU-2 | Không ghép, không proxy |
| PGT bị lộ trong log | Ticket xuất hiện ở URL/log | Security incident, rotate/revoke và log redaction |
| /proxy đúng PGT target B | A xin PT-B | CAS trả PT-B |
| /proxy PGT expired/revoked | A cố xin PT từ PGT lỗi | ProxyFailure |
| /proxy target unknown | A xin PT cho URL lạ | CAS/A policy deny |
| PT-B đúng B | A trình PT-B; B proxyValidate(service=B) | CAS authSuccess + proxies |
| PT-B trình tại Payroll | Bên khác validate với service Payroll | Fail service binding |
| PT-B replay | Validate PT-B lần 2 | CAS từ chối |
| B dùng /serviceValidate cho PT | B cấu hình sai validator | Không xử lý PT theo protocol |
| Proxy chain rỗng khi B yêu cầu A | ST direct user đến B | B policy reject nếu chỉ cho qua A |
| Proxy chain có unknown hop | PT đến B qua gateway không được duyệt | B reject |
| Proxy chain A đúng nhưng user disabled | CAS authSuccess, internal account locked | 403 |
| User Lan đọc báo cáo Bob | B có PT đúng nhưng resource owner khác | 403 |
| CAS logout | User CAS SSO session kết thúc | PGT lifetime/revocation theo protocol; thử lại |
| CAS Server unavailable | /proxy hoặc /proxyValidate timeout | Fail-closed, không dựng user header |
| Callback lệch node | CAS callback node 2, validation node 1 | Shared PGT storage hoặc fail an toàn |
| Reverse proxy host sai | A/B service URL phát sinh internal host | Sửa public CAS service IDs, không bỏ validation |
| PT bị redirect sang external host | B có HTTP 302 tới attacker | A không chuyển tiếp ticket/cookie qua redirect |

### 17.1. Cách test để không nhầm lỗi

Nếu thay `targetService` sau khi PT đã phát, CAS validation fail, điều này chứng minh target binding. Nếu muốn test **proxy chain policy** riêng, dùng một CAS sandbox hợp lệ phát PT thật với proxy chain không nằm trong allowlist, rồi xác minh B vẫn reject. Chỉ gửi XML giả vào B mà không qua CAS có thể fail ngay ở bước ticket validation; test đó không chứng minh `NamedCasProxyDecider`.

Với PGT callback, kiểm đặc biệt **race, concurrency và cleanup**. Một unit test trong Java Map không chứng minh CAS HTTPS GET/PKIX, vì vậy phải có integration test với CAS sandbox và TLS cert hợp lệ.

## 18. Lỗi phổ biến và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| A login được nhưng không gọi B | A không xin được PGT | `pgtUrl`, callback/200, proxy policy, PGTIOU mapping |
| Không có `cas:proxyGrantingTicket` | CAS không cấp PGT | HTTPS callback PKIX, registered service, allowProxy |
| `INVALID_PROXY_CALLBACK` | URL/certificate/endpoint không đạt | Public HTTPS URL, chain trust, redirect, allowed callback |
| PGTIOU không match | Race, wrong storage, wrong node | Shared store, concurrency, TTL, correlation |
| CAS `/proxy` trả `UNAUTHORIZED_SERVICE` | A/target chưa được phép | CAS service registry/proxy policy |
| CAS `/proxy` trả `INVALID_REQUEST` | Thiếu `pgt` hoặc `targetService` | Correct parameters, no secrets in logs |
| B báo invalid ticket | PT expired/replayed/wrong service | Correct `/proxyValidate`, service URL, one-time |
| B thấy proxy chain lạ | Gateway/relay hoặc trust misconfiguration | Exact trusted proxies, hops order |
| B login thành công nhưng 403 | App authorization deny | User status, tenant, resource ownership |
| A mất PGT sau restart | In-memory storage không bền | Secure distributed storage/lifecycle strategy |
| Lỗi chỉ một node | Callback và validation đến khác node | Shared PGTIOU mapping hoặc affinity |
| Lỗi sau reverse proxy | scheme/host/port mismatch | CAS serviceId/pgtUrl, trusted forwarded headers |
| Các PT dùng lại thất bại | CAS PT one-time | Xin PT mới, idempotency/retry logic |
| Sau logout vẫn gọi B được | PGT/session/ticket lifecycle hoặc app cache | CAS logout revocation, B request validation, cache invalidation |
| B nhận user từ header attacker | B tin `X-User` không CAS validation | Remove header-based trust, enforce CAS validation |
| Debug app log chứa PT/PGT | URL query/tracing chưa redacted | Sanitization + incident response |

**Thứ tự chẩn đoán:** ST validation A → pgtUrl trust → CAS callback GET pgtId/pgtIou → PGTIOU correlation → /proxy target policy → PT presentation → B /proxyValidate exact service → proxy chain policy → B business authorization. Không sửa lỗi ở B bằng cách tắt validation ở CAS hoặc chấp nhận mọi proxy.

## 19. Security hardening và runbook

**PGT là credential nhạy cảm cao:**
- Lưu trong secret-aware store hoặc encrypted storage, chỉ runtime A đúng user/session được dùng.
- Không in PGT/PT/ST trong `toString()`, exception, tracing tags, URLs gửi cho browser, audit events hoặc application support tickets.
- Dùng HTTPS tới CAS và B, validate server certificates; bảo vệ callback TLS/PKIX và không dùng trust-all SSL context.
- Cấp privilege nhỏ nhất cho A và B, CAS registry deny-by-default, targetService allowlist.
- Quản lý TTL/cleanup, logout revocation, cache validity và race/session expiration.
- Chặn open redirects khi gửi PT; ngăn callback SSRF, X-Forwarded-Host spoofing và serviceId wildcard.
- Có monitoring: PGT acquisition failures, callback TLS failures, /proxy unauthorized, PT validation errors, trusted proxy rejection, user entitlement 403, ticket replay.
- Tách audit event metadata khỏi bearer secrets.

### Runbook khi PGT/PT bị lộ

1. **Containment:** thu hồi PGT/đóng CAS session hoặc áp CAS revocation policy, disable bị ảnh hưởng nếu cần; ngăn service A tiếp tục phát PT.
2. **Scope:** xác định user/session, CAS service registry, targetServices B, thời gian lộ, log/trace/backups và các calls đã xảy ra.
3. **Credentials:** xử lý ticket lifecycle, key/trust store khi có bằng chứng compromise, không nhầm xoay TLS cert với thu hồi ngay mọi PGT đã phát.
4. **Audit:** dùng metadata như correlation ID, source IP được tin, target service, action, status; không tải lại bản ticket sống sang nơi rộng quyền.
5. **Remediation:** redaction logs, allowlist stricter, egress TLS, proxy chain policy, storage permissions/TTL/cleanup và regression tests.
6. **Notification:** phối hợp owners của CAS, A và B, privacy/security theo quy trình tổ chức.
7. **Verification:** thử không thể /proxy với PGT cũ và B từ chối PT cũ; xác nhận không có bằng chứng user access vượt quyền.

## 20. Bài tập thực hành

**Bài A – xác định credentials.** Trình bày ST, PGT, PGTIOU, PT khác nhau thế nào; cái nào một lần, cái nào có thể xin nhiều tickets; giải thích vì sao không dùng `JSESSIONID` A làm credential của B.

**Bài B – vẽ luồng.** Vẽ sequence CAS login A, `/serviceValidate` có `pgtUrl`, CAS HTTPS **GET callback**, response có PGTIOU, A `/proxy`, B `/proxyValidate`. Chỉ ra chính xác ở đâu có browser và ở đâu server-to-server.

**Bài C – Java 17.** Chạy `CasProxyPolicyDemo.java` và đối chiếu stdout bảy dòng. Thêm targetService mới mà chưa thêm vào `APPROVED_ACTIONS` và chứng minh `DENY_TARGET`. Giải thích vì sao test Java này không kiểm CAS XML/TLS.

**Bài D – concurrency.** Alice/Bob login cùng lúc, callback PGTIOU-1 và PGTIOU-2 tới node 2, validation response tới node 1. Thiết kế shared storage với TTL, atomic lookup và cleanup chống nhầm PGT.

**Bài E – proxy chain.** B chỉ chấp nhận A. CAS xác nhận chain `[Gateway, A]`. B có nên chấp nhận chỉ vì có A? Vì sao? Thay chính sách để chấp nhận *chính xác* hai-hop nếu business đã phê duyệt.

**Bài F – endpoint compatibility.** So sánh B gọi `/serviceValidate` và `/proxyValidate` khi được trình PT. Giải thích vì sao targetService và service phải match.

**Bài G – security review.** User nhập `targetService=https://internal.example/metadata` hoặc `pgtUrl=https://attacker.example/capture`. Nêu hai nguy cơ và những lớp policy phải chặn.

**Bài H – quyền nghiệp vụ.** B verify PT của Lan qua A nhưng request đọc report của Bob. Tại sao 403 vẫn đúng? Thiết kế kiểm tenant/resource ownership.

**Bài I – retry và logout.** B đã validate PT thành công nhưng A timeout. A có thể dùng lại PT không? Có cần idempotency key không? Nếu user logout CAS, PGT phải được xử lý thế nào?

**Bài J – lựa chọn công nghệ.** Tổ chức xây API mới chỉ dùng OAuth2. So sánh CAS Proxy với service account và OAuth2 Token Exchange/OBO: cách nào phù hợp với resource scopes, audience và consent?

**Tiêu chí đạt:** Người học mô tả được chuỗi **ST-A → PGT callback/PGTIOU → PGT-A → PT-B → /proxyValidate → proxy chain policy → authorization tại B**, giữ được các bất biến **HTTPS, exact service/target binding, one-time PT, PGT secret, allowlist, trust và fail-closed**.

## 21. Nguồn tham khảo chính thức

- Apereo CAS Protocol Specification 3.0.3 – mục 2.5 proxy callback, 2.6 proxyValidate, 2.7 proxy, 3.1–3.4 ST/PT/PGT/PGTIOU: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS – Proxy Authentication, use case Service A gọi backend B bằng PT: https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html
- Apereo CAS – Registered Service Proxy Policy: https://apereo.github.io/cas/development/services/Configuring-Service-Proxy-Policy.html
- Spring Security – CAS Authentication, “Authenticating to a Stateless Service with CAS” và ProxyGrantingTicketStorage/Cas20ProxyTicketValidator: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security 6.5 – CAS Authentication reference theo phiên bản: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/cas.html
- CAS Client / Apereo CAS documentation portal: https://apereo.github.io/cas/
- RFC 8693 – OAuth 2.0 Token Exchange (giải pháp khác, không phải CAS Proxy): https://www.rfc-editor.org/rfc/rfc8693
- OWASP – Secrets Management Cheat Sheet (bảo vệ PGT/credentials): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
