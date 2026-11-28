# Bảo vệ secret khỏi gửi qua network

**Secret** là thông tin mà người hoặc hệ thống không được phép sở hữu có thể dùng để xác thực, ký dữ liệu, truy cập tài nguyên, giải mã hoặc thực hiện một hành động đặc quyền. Ví dụ gồm **API key, bearer token, OAuth refresh token, private key, mật khẩu database, session cookie, cloud credentials, webhook signing secret và khóa truy cập dịch vụ**. Một secret bị đưa vào **HTTP request, DNS query, application log chuyển tới SaaS, email, message queue, object storage hoặc một kết nối mạng không được phê duyệt** có thể rời khỏi ranh giới kiểm soát, dù request được mã hóa bằng HTTPS và trả về HTTP 200.

Trong chương **Kiểm soát egress và chống thất thoát dữ liệu** của module **SECURITY_NETWORK_SECURITY**, mục tiêu không chỉ là **mã hóa gói tin**, mà là **không gửi secret đến đối tượng không cần biết, không cho workload tùy ý truy cập đích ngoài phạm vi, phát hiện các luồng rủi ro và giảm tác hại khi secret đã lộ**. Bài kết nối **network segmentation, firewall/egress gateway, VPN, IDS/IPS, TLS/mTLS, DNS security, cloud networking, Kubernetes NetworkPolicy, secret management, SIEM và DLP** để xây dựng phòng vệ từ mã ứng dụng đến mạng và vận hành.

> **Phạm vi và an toàn:** toàn bộ secret, tên miền, địa chỉ IP, sự kiện và request dưới đây đều là **giả lập**, không phải credentials thật. Không thử gửi token production đến endpoint để “xem DLP có bắt được không”. Chỉ kiểm thử với chuỗi **synthetic marker** tại sink do tổ chức kiểm soát và có quyền. Không thu thập/giải mã lưu lượng của người khác để tìm secret; hoạt động kiểm tra TLS hoặc packet capture phải tuân thủ chính sách riêng tư và quyền truy cập.

## 1. Mục tiêu học tập

Hoàn thành bài này, người học có thể:

1. Phân biệt **secret, identifier, PII, credential, encryption key, token và dữ liệu nhạy cảm khác**; hiểu giá trị, phạm vi và vòng đời của mỗi loại.
2. Vẽ luồng secret từ **secret manager → workload → request/proxy/DNS → destination**, cùng các trust boundaries có thể rò rỉ.
3. Giải thích vì sao **TLS/HTTPS/mTLS bảo vệ transport nhưng không xác định một đích có được phép nhận secret hay không**.
4. Nhận diện đường lộ phổ biến qua **URL path/query, headers, cookies, JSON body, redirect, webhook, tracing, crash report, telemetry, SaaS, CI/CD và cloud network egress**.
5. Phân biệt **secret cần thiết trong một giao thức xác thực hợp lệ** với secret bị gửi quá mức hoặc đến sai đối tượng; không “chặn mọi Authorization header” một cách máy móc.
6. Thiết kế **policy theo luồng dữ liệu và danh tính đích**, gồm allowlist ứng dụng, destination authorization, egress firewall, proxy, NetworkPolicy và IAM.
7. Giải thích khả năng/giới hạn của **DLP nội dung, secret scanning, entropy/fingerprint detection, TLS inspection và metadata/flow-based monitoring**.
8. Tạo **redaction/sanitization** trước khi log, trace, gửi lỗi hoặc tích hợp bên thứ ba; xử lý các biến thể mã hóa/định dạng mà không làm mất bằng chứng điều tra.
9. Xây dựng kế hoạch bảo vệ **Kubernetes Secrets, workload identity, cloud IAM, CI/CD tokens, third-party SDKs và service meshes**.
10. Thực hiện lab **không dùng secret thật** với yêu cầu allow/deny, bộ sự kiện tổng hợp, negative tests và evidence checklist.
11. Xử lý tình huống nghi lộ bằng **containment, revoke/rotate, audit usage, impact analysis và hậu kiểm** theo risk/owner.

## 2. Secret là gì và vì sao nguy cơ qua network đặc biệt?

### 2.1. Bí mật không đồng nghĩa mọi chuỗi có vẻ ngẫu nhiên

| Loại | Ví dụ giả lập | Điều cần bảo vệ |
| --- | --- | --- |
| **API key** | REDACTED_API_KEY | Quyền dùng API, quota, billing/data access |
| **Access token** | TEST_TOKEN_NOT_VALID | Quyền theo audience, scope, thời hạn |
| **Refresh token** | REDACTED_REFRESH_TOKEN | Khả năng xin access token mới, thường nhạy cảm hơn |
| **Private key** | SYNTHETIC_PRIVATE_KEY_PLACEHOLDER | Chữ ký/giải mã/định danh của chủ thể |
| **Database password** | REDACTED_DB_PASSWORD | Truy cập tài khoản và dữ liệu database |
| **Session cookie** | session=REDACTED | Phiên người dùng, nguy cơ session hijack |
| **Webhook signing secret** | REDACTED_WEBHOOK_SECRET | Giả mạo chữ ký sự kiện nếu lộ |
| **Cloud credential** | REDACTED_CLOUD_CREDENTIAL | Quyền IAM trên tài nguyên cloud |
| **Kubernetes ServiceAccount token** | REDACTED_K8S_TOKEN | Quyền gọi Kubernetes API theo RBAC/audience |
| **Encryption/KEK/DEK** | REDACTED_KEY_MATERIAL | Bảo mật dữ liệu mã hóa, vòng đời khóa |
| **PII** | Tên, số liên lạc, địa chỉ | Dữ liệu nhạy cảm cần DLP, nhưng không phải mọi PII là secret xác thực |
| **Public certificate/public key** | Public certificate | Không mặc định là secret; private key mới cần giữ kín |

Một UUID của request, trace ID hoặc hash công khai **không tự động là secret**. Ngược lại, một chuỗi ngắn dễ đọc vẫn có thể là credential thật. Phát hiện phải dựa vào **ngữ cảnh, định dạng, nguồn phát hành, phân loại dữ liệu và khả năng sử dụng**, không chỉ chiều dài hoặc entropy.

### 2.2. Ba thuộc tính làm một secret bị lộ trở nên nghiêm trọng

- **Authority (quyền):** token chỉ đọc một resource khác token cho phép quản trị toàn account.
- **Exposure (phạm vi lộ):** một log nội bộ có RBAC hẹp khác một telemetry SaaS, public paste hoặc webhook sang bên thứ ba.
- **Lifetime/revocability (thời gian và thu hồi):** short-lived audience-bound token khác static key không hết hạn; private key ký payload có thể đòi thay certificate/trust nếu bị lộ.

**Độ nghiêm trọng không đo bằng số byte đã rời khỏi mạng.** Một API key vài chục ký tự có thể nguy hiểm hơn một file báo cáo lớn không chứa thông tin bí mật.

### 2.3. “Secret bị gửi” khác “secret được sử dụng đúng”

Gửi một **bearer access token** trong Authorization header tới **đúng resource server, đúng TLS endpoint và đúng audience/scope** là một bước cần thiết của nhiều giao thức. Mục tiêu phòng vệ **không phải chặn mọi token rời process**, mà là:

1. Token **chỉ đến đúng dịch vụ** được phép tiếp nhận.
2. Token **không nằm trong URL, log, telemetry, query hay redirect** khi không cần.
3. Token mang **quyền tối thiểu**, có lifetime phù hợp và không bị tái sử dụng sai audience.
4. Đường truyền xác thực **đúng peer**; ứng dụng không bỏ kiểm tra chứng chỉ.
5. Secret có thể **thu hồi và thay mới** khi nghi lộ.

Một request hợp lệ còn có thể đi qua gateway/mesh; cần biết **proxy nào nhìn thấy token**, ai được truy cập proxy logs và headers nào bị redaction.

### 2.4. Ranh giới tin cậy của secret

~~~mermaid
flowchart LR
  M["Secrets manager / KMS\nrole-scoped access"] --> W["Application workload\nmemory / bounded scope"]
  W --> A["Approved auth endpoint\nTLS + audience checks"]
  W --> L["Logs / traces\nredaction needed"]
  W --> P["Proxy / egress gateway\nallowlist + telemetry"]
  P --> S["Approved external service\ncontract and identity"]
  P -. "Deny unapproved" .-> U["Unknown SaaS / Internet"]
  W -. "Prevent data leak" .-> D["DNS, redirect,\nthird-party SDK"]
  L --> SIEM["Controlled log sink\nRBAC + retention"]
~~~

Đường hợp lệ không có nghĩa **mọi hop được xem secret**. Trong thiết kế tốt, credentials chỉ đi vào nơi **giao thức yêu cầu**, và hệ thống logging/tracing thường chỉ giữ metadata hoặc dấu vết đã khử nhạy cảm.

### 2.5. Bí mật trong ba trạng thái

| Trạng thái | Ví dụ | Control ưu tiên |
| --- | --- | --- |
| **At rest** | Secret store, etcd, file/volume, CI variable | Encryption at rest, IAM/RBAC, audit, retention |
| **In use** | Token trong process memory, app config | Least privilege, không dump/log, bounded lifetime, secret manager |
| **In transit** | HTTP header/body, gRPC metadata, queue, DNS, proxy | Destination validation, TLS/mTLS, egress policy, DLP/redaction |

Mã hóa **at rest** không giải quyết tự động việc process lấy secret và gửi đi. Mã hóa **in transit** không ngăn chính process gửi secret tới server không đáng tin; cả hai cần kết hợp với **destination restrictions và authorization**.

## 3. Threat model: secret rời khỏi ranh giới như thế nào?

### 3.1. Một luồng secret có nhiều vị trí bị lộ

~~~mermaid
sequenceDiagram
  participant SM as Secret manager
  participant APP as Application
  participant PROXY as Egress proxy / mesh
  participant DNS as DNS resolver
  participant DEST as External destination
  participant OBS as Logs / traces
  SM-->>APP: Short-lived credential
  APP->>DNS: Resolve approved hostname
  DNS-->>APP: Destination address
  APP->>PROXY: Request with scoped auth (if required)
  PROXY->>DEST: TLS connection to verified peer
  DEST-->>APP: Authorized response (via proxy path)
  APP-->>OBS: Status, request ID, redacted metadata
~~~

Đây là **đường hợp lệ**. Các đường rủi ro có thể là application đưa token vào URL khiến nó vào access log; SDK gửi diagnostics sang vendor; proxy ghi Authorization header; ứng dụng nhận redirect và vô ý chuyển credentials; code làm DNS query chứa chuỗi nhạy cảm; CI job tải logs/artifacts sang một storage ngoài phạm vi.

### 3.2. Nguồn gây lộ không chỉ là kẻ tấn công

**Rò rỉ do lỗi vận hành/lập trình:**

- Ghi nguyên request/response có token vào debug logs.
- Đưa access token vào query string để “dễ debug”.
- HTTP client gửi auth headers qua redirect không đúng trust domain.
- Một thư viện telemetry mặc định thu thập HTTP headers/bodies.
- Webhook diagnostic hoặc incident ticket tự động đính kèm cấu hình có secrets.
- CI step bật verbose trace in ra environment variables.

**Rò rỉ khi workload bị compromise hoặc lạm dụng quyền:**

- Một process có quyền đọc credential gửi dữ liệu tới đích không được phê duyệt.
- Một service account quyền cao hoặc node metadata credential làm tăng impact.
- Một dependency hoặc agent có egress quá rộng hoạt động ngoài luồng mong đợi.
- Một insider tạo connector/automation gửi thông tin từ môi trường nhạy cảm sang dịch vụ riêng.

**Rò rỉ qua trust boundary sai:**

- Dịch vụ staging dùng credentials production.
- Data plane được phép đi tới VPC peer, SaaS tenant hoặc object store sai chủ sở hữu.
- Proxy/Gateway thay TLS termination nhưng không kiểm soát headers/logs.
- DNS, backup, analytics và APM là **một destination network** thường bị bỏ quên trong data-flow inventory.

### 3.3. Điều kiện để xảy ra tổn thất

Một lỗ hổng có thể cần đồng thời:

1. Secret tồn tại ở một **component có thể sử dụng/đọc**.
2. Component tạo **kết nối network hoặc output artifact**.
3. Egress/route/gateway **cho phép đến một recipient không được duyệt** hoặc trusted recipient lưu/chuyển tiếp dữ liệu sai cách.
4. Dữ liệu nhạy cảm **thực sự được truyền/ghi** ra ngoài ranh giới.
5. Token vẫn còn giá trị hoặc nội dung có thể gây tác hại.

Không thể kết luận secret bị đánh cắp chỉ từ một flow TCP/443 ALLOW. Nhưng một **known credential xuất hiện trong log của hệ thống ngoài phạm vi** có thể đủ để kích hoạt revoke/rotate, ngay cả khi chưa có bằng chứng credential được sử dụng.

### 3.4. Dữ liệu là “allowed business data” hay secret?

Một hệ thống có thể được phép chuyển **báo cáo thống kê không định danh** ra SaaS nhưng không được gửi **API token của production hoặc private key** trong chính payload đó. Vì thế egress approval phải có cả:

- **Destination approval:** domain/endpoint/tenant/account nào được phép?
- **Data approval:** kiểu dữ liệu và mức nhạy cảm nào được gửi?
- **Purpose and retention:** mục đích nghiệp vụ, processing, địa điểm lưu, thời hạn xóa.
- **Credential handling:** token nào được dùng để xác thực và token nào **không được phép là dữ liệu xuất đi**?

**Network allow không tự chứng minh data flow được phép.** Đây là điểm giao giữa egress controls và Data Loss Prevention (DLP).

## 4. Các kênh mạng thường làm secret bị gửi ra ngoài

### 4.1. HTTP URL path và query string

Đặt token trong URL có thể khiến nó xuất hiện ở **proxy access logs, web server logs, history, application metrics, cache keys, tracing, CDN analytics hoặc systems ghi nhận redirect**. Ví dụ không nên dùng:

~~~text
https://api.example.test/v1/export?access_token=REDACTED
https://reports.example.test/credential/REDACTED
~~~

Không nên coi **TLS** là biện pháp đủ cho token trong URL: TLS bảo vệ trên đường truyền đến endpoint, nhưng endpoint/proxy/telemetry có thể ghi URL sau khi giải mã. Với browser, **Referer** có thể tiết lộ URL hoặc một phần URL theo Referrer-Policy và ngữ cảnh; không mặc định mọi trình duyệt gửi toàn bộ query trong mọi tình huống.

Biện pháp:

- Dùng cơ chế xác thực đã được chuẩn hóa của API, ví dụ **Authorization header** khi đúng giao thức.
- **Không bao gồm secrets trong path/query** ngay cả với endpoint nội bộ.
- Strip/redact các tham số nhạy cảm trong access logs, tracing và analytics.
- Không dùng raw URL chứa credentials trong alert/ticket.
- Áp **Referrer-Policy** phù hợp ở web apps; không coi đây là biện pháp duy nhất.
- Với presigned URLs, dù URL không phải mật khẩu tài khoản, nó là **capability token** có thể cấp quyền truy cập; phải giới hạn thời hạn, quyền, scope và tránh ghi raw URL.

### 4.2. HTTP headers và cookies

Headers có thể chứa:

~~~http
GET /v1/account HTTP/1.1
Host: api.example.test
Authorization: Bearer REDACTED_ACCESS_TOKEN
Cookie: session=REDACTED_SESSION
X-Api-Key: REDACTED_API_KEY
~~~

**Đây là dạng cấu trúc minh họa, không dùng credential thật.** Một số headers chứa secrets là cần thiết cho **đúng server**, nhưng người vận hành phải tránh:

- Log toàn bộ headers theo mặc định ở edge proxy, service mesh hoặc middleware.
- Copy headers vào error reporting/trace spans.
- Chuyển Authorization/Cookie sang **host ngoài trust boundary** qua redirect hoặc manual HTTP client behavior.
- Dùng cùng token cho nhiều audiences/tenants không liên quan.
- Gửi header API key đến webhook của đối tác không cần khóa này.

**Không nên tự viết redirect handler “forward all headers”**. Dùng HTTP client có chính sách redirect bảo vệ credentials theo origin, và kiểm tra behavior bằng integration tests trong sandbox. Với cookie trên web, dùng **Secure, HttpOnly, SameSite, Path/Domain scope** phù hợp để giảm exposure theo cơ chế browser, nhưng cookies vẫn có thể xuất hiện trong server-side logging nếu lập trình sai.

### 4.3. HTTP request body, gRPC metadata và WebSocket messages

Một API có thể nhận password/token trong **request body hợp lệ** ở endpoint xác thực. Khi đó:

- Request body chứa secret phải đến **đúng auth endpoint**.
- Gateway/WAF/APM không ghi full body không cần thiết.
- Input validation/serialization không thêm trường credentials vào DTO trả về.
- Middleware “dump request on error” phải **redact** hoặc tắt đối với endpoints nhạy cảm.
- gRPC metadata dùng cho authentication cần được xử lý tương tự HTTP headers; không đẩy raw metadata sang tracing.
- WebSocket messages có thể mang token trong message payload; không mặc định HTTP handshake telemetry đã bao phủ mọi frames.

**POST không bảo đảm secret an toàn hơn GET** nếu ứng dụng vẫn log body hoặc gửi sai đích. Yếu tố quyết định là **data minimization, destination identity và logging boundary**.

### 4.4. HTTP redirects và cross-origin boundary

Một ứng dụng gọi một API được duyệt nhưng server trả HTTP redirect sang hostname khác. Có vài trường hợp:

- Redirect nằm trong cùng trust domain, phù hợp hợp đồng API.
- Redirect sang CDN/object store được duyệt cho một download không mang credentials.
- Redirect sang **host không được duyệt**, không được tiếp nhận bearer token/cookie/API key.

Để phòng vệ:

1. Chỉ chấp nhận redirect theo **allowlist origin/host/scheme** và mục đích.
2. Không forward credentials đến **khác origin** nếu không có thiết kế xác thực rõ.
3. Giữ HTTPS và xác thực hostname/certificate tại mọi hop.
4. Giới hạn số lần redirect và không để redirect phá vỡ policy egress.
5. Test cả response **3xx** trong các HTTP client/SDK quan trọng.

**Thư viện HTTP có thể tự bỏ headers nhạy cảm khi redirect khác host**, nhưng hành vi khác theo client/version và custom code. Không giả định bảo vệ này có ở mọi connector.

### 4.5. DNS là một kênh dữ liệu cần kiểm soát

DNS queries thông thường mang **domain names**; resolver/authoritative DNS/observability có thể nhìn thấy tên được truy vấn, theo topology và cơ chế bảo vệ. Nếu dữ liệu nhạy cảm bị chèn vào subdomain, phần đó có thể rời khỏi ranh giới mạng.

Ví dụ cấu trúc rủi ro (chỉ là marker giả lập):

~~~text
REDACTED_MARKER.unapproved.example.test
~~~

Đây là **dấu hiệu cần phát hiện**, không phải yêu cầu thực hiện DNS exfiltration. Phòng vệ:

- Ép workloads dùng **resolvers được quản lý**, chặn direct external DNS ngoài policy.
- Quản lý DNS egress TCP/UDP 53 và **DoT/DoH** theo kiến trúc; không giả định chặn UDP 53 là đủ.
- Alert truy vấn tới **domain mới/độ dài bất thường/tần suất bất thường**; tránh đánh đồng tất cả subdomains dài với malicious, vì có CDN/telemetry hợp lệ.
- Dùng DNS security logs có quyền truy cập và retention phù hợp.
- Không cho API secret đi vào DNS names, cache keys hoặc analytics dimensions ngay từ ứng dụng.

### 4.6. Log shipping, tracing, metrics và crash reporting

Đây là **network egress rất thường xuyên nhưng dễ được mặc định tin cậy**:

~~~text
Application error
  -> raw exception/request context
  -> APM/OTel collector
  -> SaaS telemetry tenant
  -> long-retention searchable logs
~~~

Những vị trí có thể chứa secrets:

- Exception messages chứa connection strings.
- HTTP client spans có URL query, Authorization/Cookie, body.
- Stack trace có environment variable hoặc CLI arguments.
- Log line debug in nguyên cấu hình.
- Metrics labels chứa token/session ID làm **high-cardinality** và rò dữ liệu.
- Crash dumps/core dumps chứa process memory.
- Network request capture ở reverse proxy hoặc service mesh access logging.

**Redact tại nguồn trước khi dữ liệu vào collector**, sau đó kiểm tra ở pipeline/collector và đích. Một secret đã vào SaaS logs có thể được replication/indexing, khó xóa hoàn toàn ngay cả khi UI hiển thị được mask.

### 4.7. Webhooks, email, chatbots và third-party SDKs

Một webhook integration cần được xem như **data export**. Những ví dụ:

- Alerting bot gửi full environment/config vào chat channel.
- CI bot đính kèm .env hoặc raw deployment manifest vào ticket.
- Payment/analytics SDK thu thập request body chứa session token.
- Support tool gửi diagnostic archive có private key.
- Email automation gửi link signed URL còn hiệu lực tới danh sách nhận sai.

Kiểm soát gồm **allowlisted recipient/tenant, message schema whitelist, data classification, DLP trước khi gửi, access control trên connectors** và sample payload review. Một vendor “được duyệt” cho metrics không nhất thiết được duyệt nhận **production API key**.

### 4.8. Message queues, object storage và CI artifacts

Không chỉ socket HTTP trực tiếp:

- Publish secrets vào **Kafka/RabbitMQ/SQS-like topics**, nơi nhiều consumers có thể đọc.
- Upload backup/config chứa secrets vào object storage bucket khác account.
- Lưu Docker build args, env dumps, Maven/Gradle build logs hoặc CI job output có credentials.
- Ghi full Kubernetes Secret manifest vào CI artifacts.
- Đồng bộ developer diagnostics sang external file share.

Các bước này có thể **hợp lệ ở network layer**, nhưng gây **lộ dữ liệu tới người nhận sai**. DLP cần bao gồm destinations dạng message brokers/storage services và **resource-level IAM/ACL**—network firewall không nhìn ra bucket/key/topic có đúng đối tượng hay không.

### 4.9. Non-HTTP traffic không giống nhau

Các giao thức ngoài HTTP có thể có **đường dữ liệu/metadata khác**; egress review nên inventory DNS, SMTP, SSH, file transfer, UDP/QUIC, syslog, custom TCP, DNS-over-HTTPS và service mesh bypass. Không khẳng định mọi payload đều được thấy bởi một HTTP proxy.

Kiểm soát **non-HTTP traffic** qua firewall/CNI ACL, protocol gateways, secure configuration và app-level authorization. Với ICMP/ICMPv6, tránh chặn mù vì **Path MTU Discovery và network diagnostics** có thể phụ thuộc một số types. Tập trung vào **đường truyền dữ liệu không được duyệt**, không chỉ một danh sách port.

## 5. Vì sao mã hóa đường truyền không ngăn exfiltration?

### 5.1. TLS bảo vệ cái gì?

Khi được cấu hình đúng, TLS cung cấp **confidentiality/integrity cho dữ liệu giữa TLS endpoints** và xác thực server identity qua certificate validation (mTLS còn xác thực client theo thiết kế). Nhưng TLS **không kiểm tra việc app có quyền gửi một database password tới đích đó không**.

~~~mermaid
flowchart LR
  W["Workload có secret"] --> C{"Đích/recipient\nđược phép nhận?"}
  C -- "Có" --> TLS["HTTPS/mTLS\nverify peer"]
  TLS --> AP["Approved recipient\nuse minimal credential"]
  C -- "Không" --> DENY["Block before transmission\napp policy + egress ACL"]
  C -. "Sai cấu hình" .-> BAD["HTTPS tới host sai\nvẫn có thể mã hóa"]
  BAD --> X["Unauthorized recipient\nreceives secret"]
~~~

**Kết nối HTTPS mã hóa thành công tới một server không được phép là một thất bại của policy dữ liệu**, không phải thành công bảo mật chỉ vì có ổ khóa trong URL.

### 5.2. TLS termination points là trust boundaries

Một request có thể đi:

~~~text
App -> Service mesh sidecar -> Egress proxy -> HTTPS destination
~~~

Hoặc:

~~~text
Browser -> CDN/WAF -> API gateway -> application
~~~

Tùy thiết kế, TLS được **terminate và tạo lại** tại một hoặc nhiều proxy. Mỗi điểm termination có thể:

- Đọc một phần payload/headers ở dạng rõ.
- Log/capture dữ liệu nếu được cấu hình.
- Bổ sung forwarded headers hoặc tracing context.
- Áp WAF/DLP/authorization và chuyển tiếp.

**mTLS giữa hai sidecars không bảo đảm token không lọt vào access log của application hoặc gateway**. Hãy vẽ đúng TLS endpoints, sở hữu khóa, trust domain và quyền xem logs.

### 5.3. Không tắt certificate verification để “đỡ lỗi”

Nếu một SDK bị TLS hostname/CA error khi gọi destination mới, không sửa bằng **verify=false**, bỏ hostname check hay tự tin mọi chứng chỉ. Giải pháp đúng:

1. Xác minh đích dự kiến, hostname/SAN, issuer/trust store.
2. Sửa certificate chain hoặc DNS/route.
3. Nếu dùng corporate inspection proxy, quản lý **trust root** và phạm vi TLS interception theo chính sách.
4. Test cả certificate expiry/rotation và redirect.
5. Không cho phép secret rời process tới một peer chưa xác minh.

### 5.4. TLS inspection/DLP có giới hạn

Một enterprise secure web gateway có thể inspection nội dung TLS **khi được phép và kỹ thuật hỗ trợ**. Nhưng:

- **TLS 1.3, certificate pinning, client mTLS, QUIC/HTTP3, ECH và app protocols** ảnh hưởng khả năng nhìn nội dung, tùy sản phẩm/cấu hình.
- Inspection tạo thêm **trust/key/privacy boundary** và có thể gây lỗi một số ứng dụng.
- Egress qua **direct VPC route, NAT, VPN, private endpoint** có thể bỏ proxy nếu network không buộc path.
- DLP không thể phân tích plaintext **mà nó không nhìn thấy**; metadata-based detection là một lớp bổ sung, không tương đương payload inspection.
- Quan sát encrypted data không mặc định biết **token nào nằm trong body**; cần kiểm tra tại source/app hoặc nơi terminate TLS hợp lệ.

Không dùng kỹ thuật bẻ khóa TLS để trích credentials. Mục tiêu là **policy tại nơi được ủy quyền, telemetry đủ, kiểm soát egress và redaction ở nguồn**.

### 5.5. Payload mã hóa hợp lệ vẫn có thể mang secret sai phép

Đôi khi hệ thống gửi một file mã hóa đến storage ngoài tổ chức. Network DLP có thể chỉ thấy **ciphertext**, không thấy secret bên trong. Vì thế cần:

- **Data classification** trước khi tạo file/export.
- DLP ở **application/workload/storage boundary trước encryption** khi được cấp quyền.
- Approval của destination bucket/account/tenant, không chỉ hostname.
- KMS/key release policies và resource-level IAM.
- Audit sự kiện **tạo archive, mã hóa, publish/upload và download**.

**Không chọn giữa “DLP” và “encryption”**: chúng giải quyết hai rủi ro khác nhau và phải được xếp đúng chỗ trong luồng dữ liệu.

## 6. Thiết kế trust boundaries và egress policy

### 6.1. Phân nhóm điểm đến

| Destination class | Ví dụ | Chính sách |
| --- | --- | --- |
| **Approved auth server** | Token endpoint của identity provider | Cho phép scope hẹp, TLS validation, credentials đúng audience |
| **Approved resource API** | API dùng token theo nghiệp vụ | Chỉ đúng principal/token và endpoint |
| **Internal secrets manager** | Vault/cloud secret manager/private endpoint | Least privilege IAM, TLS/mTLS, audit |
| **Central observability** | OTel/APM/log collector | Chỉ metadata/redacted fields, retention/RBAC |
| **Approved vendor/SaaS** | Payments/analytics/CRM tenant cụ thể | Data contract, tenant-bound access, DLP |
| **Internal message broker/storage** | Queue/topic/bucket/project | Resource-level policy và classification |
| **Unapproved Internet** | Host chưa được review | Default deny hoặc phê duyệt có thời hạn |
| **Unapproved private peer** | VPC peering, VPN partner, shadow endpoint | Không coi private IP là trust |
| **Node/metadata/control plane** | Cloud metadata, node services | Không cho ordinary workloads quyền ngoài nhu cầu |

Destination inventory cần có **hostname/identity, IP ranges nếu thích hợp, protocol/port, principal được dùng, loại dữ liệu được phép, owner, reason, expiry và nơi lưu audit**.

### 6.2. Egress allowlist theo đúng nhu cầu

Nguyên tắc:

1. **Default-deny egress** ở trust tiers có yêu cầu; allow từng dependency hợp lệ.
2. Cho phép **đúng hostname/service identity/resource** khi hệ thống hỗ trợ, không chỉ CIDR rộng.
3. Kết hợp **L3/L4 firewall/NetworkPolicy** và **L7 gateway policy** khi cần.
4. Chỉ đưa **secret đúng audience** đến endpoint nhận secret; không forward qua redirect khác origin.
5. Khi một đích SaaS dùng CDN/shared IPs, tránh phụ thuộc IP allowlist thuần túy như bằng chứng tenant được ủy quyền.
6. Xem cả IPv4/IPv6 và non-HTTP protocols.
7. Khi buộc traffic qua egress proxy, **chặn direct path** ở CNI/cloud firewall.
8. Theo dõi policy drift, exception expiry và negative tests.

Một địa chỉ IP có thể phục vụ nhiều host/tenants; một FQDN có thể đổi IP theo thời gian. **Không có một tín hiệu destination duy nhất luôn đủ cho cả routing và data authorization**.

### 6.3. Tách ba quyết định

~~~text
Decision A — Network reachability:
  Is workload W allowed to connect to destination D:port?

Decision B — Recipient and transport:
  Is D the verified TLS peer / service / account/tenant intended?

Decision C — Data authorization:
  Is secret S allowed to be disclosed to D for purpose P?
~~~

Nếu A và B đều PASS nhưng C FAIL, **phải chặn hoặc loại bỏ secret khỏi payload**. Ngược lại, một API yêu cầu token hợp lệ không thể hoạt động nếu A chặn mọi outbound connections; thiết kế phải mở đúng minimal route cho hợp đồng API.

### 6.4. Thứ tự kiểm soát và rủi ro false assurance

Một cơ chế DLP ở **egress proxy** không có tác dụng đối với traffic bypass proxy qua Node NAT hoặc VPC peering. Một NetworkPolicy ở Pod không tự xác minh **TLS certificate/audience**, và một token chỉ có scope đọc cũng có thể làm rò thông tin nếu gửi tới untrusted host.

Do đó áp dụng **multi-point enforcement**:

~~~mermaid
flowchart LR
  A["App outbound request"] --> V["Schema validation\nredaction, allowlist"]
  V --> NP["CNI NetworkPolicy\nor host firewall"]
  NP --> GW["Egress gateway/SWG\nTLS identity + DLP"]
  GW --> C["Cloud route/firewall\nblock direct bypass"]
  C --> D["Approved recipient\nIAM/resource policy"]
  OBS["Proxy/CNI/app/cloud audit"] -. "Correlate" .-> V
  OBS -. "Correlate" .-> GW
  OBS -. "Correlate" .-> D
~~~

Sơ đồ biểu diễn các **lớp quyết định**, không phải thứ tự packet processing bắt buộc: NetworkPolicy có thể apply ở trước/sau NAT tùy CNI, còn gateway có thể là đích trực tiếp của app. Kiểm tra **effective routes**, không chỉ tài liệu kiến trúc.

## 7. Giảm nhu cầu vận chuyển secret bằng quản trị danh tính và vòng đời

### 7.1. Secret không xuất hiện ở đâu thì không thể bị gửi nhầm từ đó

Đây là nguyên tắc **data minimization**: giảm copy và scope của secret trước khi dùng DLP. Ưu tiên:

- Dùng **workload identity/federation** thay cho static long-lived cloud access keys khi hệ thống hỗ trợ.
- Dùng **short-lived, audience-bound, purpose-bound access tokens**, giảm scope tối đa.
- Không copy production secrets vào staging/dev.
- Không đưa secrets vào source code, Dockerfile layer, image build arguments, git history hoặc CI job artifacts.
- Đưa credentials cho **workload cần dùng**, không cho mọi containers trong Pod/host.
- Nếu một API có thể dùng **server-to-server exchange**, không gửi private key hoặc master secret tới client.
- Sử dụng **broker/proxy thực sự giữ credential** khi kiến trúc cho phép, thay vì phân phối raw credential cho từng Pod.
- Giảm số nơi cần log request bodies/headers.

**DLP là lớp cuối cùng để phát hiện/chặn sai sót**, không phải lý do để cấp secret rất rộng rồi cố quét mọi request.

### 7.2. Secret manager, KMS và application code

Một kiến trúc:

~~~mermaid
sequenceDiagram
  participant ID as Workload identity provider
  participant APP as App workload
  participant SM as Secret manager
  participant API as Approved service
  APP->>ID: Authenticate workload identity
  ID-->>APP: Short-lived scoped assertion
  APP->>SM: Authorized secret request over TLS
  SM-->>APP: Scoped credential / reference
  APP->>API: Only required credential for intended audience
  API-->>APP: Authorized result
  APP->>APP: Discard/rotate local credential on schedule
~~~

Điểm cần kiểm soát:

1. **Ai có quyền đọc secret nào?** IAM/RBAC theo workload, namespace, environment và purpose.
2. **Token có scope/audience/lifetime gì?** Không dùng admin credential cho một lệnh read-only.
3. **Secret có được cache ở đâu?** Không ghi disk/log/dump bừa bãi, tôn trọng TTL.
4. **Có rotation/revocation được không?** Tránh static credentials nếu có lựa chọn an toàn.
5. **Có audit access và suspicious usage không?** Khi lộ, biết cần thay gì.
6. **Có peer identity được xác minh** khi kết nối tới secret manager không?

**KMS key management** thường cung cấp API mã hóa/giải mã hoặc unwrap thay vì xuất raw root key. Nếu kiến trúc có thể sử dụng **key references hoặc cryptographic operations**, không xuất trực tiếp private key/KEK sang ứng dụng không cần.

### 7.3. Kubernetes Secrets không phải security boundary hoàn chỉnh

Kubernetes Secret resource có thể lưu dữ liệu base64-encoded trong manifest/API. **Base64 không phải encryption**. Để bảo vệ:

- Hạn chế **RBAC get/list/watch Secrets**, vì list/watch cũng có thể tiết lộ nội dung theo quyền.
- Bật **encryption at rest** cho dữ liệu nhạy cảm trong datastore/control plane theo khả năng cluster.
- Dùng external secret provider/CSI hoặc operators theo security requirements, quản lý quyền đồng bộ rõ.
- Hạn chế **mount** chỉ secrets workload cần; nếu có lựa chọn workload identity/direct API, cân nhắc giảm bản sao.
- Không chạy kubectl dump secrets vào CI logs hoặc ticket.
- Hạn chế debug/ephemeral containers và host privileged access tới volumes/process.
- Kiểm tra token projection, expiry/audience/bound token behavior thay vì giả định ServiceAccount tokens luôn static và vĩnh viễn.
- Không để Kubernetes API token lộ qua egress/metadata paths; audit quyền cloud/node tương ứng.

**Dù Secrets encrypted at rest, ứng dụng có thể giải mã để sử dụng và vô ý đưa nó vào network request**. Vì thế app redaction/egress control vẫn cần.

### 7.4. Env vars, mounted files và command-line arguments

Secret đưa vào **environment variable** có thể thuận tiện, nhưng có thể lộ qua debug prints, environment dumps, crash reports, child processes hoặc quyền quan sát process tùy OS/container. Mounted file có thể giúp rotation theo một số provider nhưng vẫn có rủi ro **filesystem access, backup và logging**.

Không có một hình thức phân phối an toàn tuyệt đối trong mọi ứng dụng. So sánh:

| Cơ chế | Điểm mạnh | Điều phải kiểm soát |
| --- | --- | --- |
| Env vars | Dễ tích hợp, phổ biến | Logs/dumps, process access, restart/rotation |
| Mounted secret file | Filesystem permissions, dễ tham chiếu | File access, backups, rotation notification |
| Runtime secret API | On-demand, audit, scope | Network identity, retries, cache/lifetime |
| Workload identity/federation | Giảm static key, short-lived tokens | Trust config, audience/scope, credential endpoint |
| KMS operation/key reference | Không xuất key material trong một số thiết kế | IAM, operation scope, data policy |

**Đừng log toàn bộ environment để debug một lỗi network**. Dùng health/status codes và identifiers được khử nhạy cảm.

### 7.5. Lợi ích và giới hạn của secret rotation

Rotation giúp giảm **cửa sổ khai thác**, nhưng không xóa lịch sử secret đã tới logs/backups; nếu cùng secret dùng cho nhiều systems, còn có downtime risk. Quy trình:

1. Xác định owner, nơi cấp phát, phụ thuộc và môi trường sử dụng.
2. Tạo credential mới với đúng least privilege.
3. Triển khai theo thứ tự có thể **chồng thời gian an toàn** khi provider hỗ trợ.
4. Xác minh các clients hợp lệ đổi sang credential mới.
5. **Revoke** credential cũ, không chỉ “đổi giá trị trong UI”.
6. Kiểm tra mọi nơi còn dùng secret cũ (connection failures/audit).
7. Đánh giá log/artifact retention và xử lý theo quy trình dữ liệu.

Với token có thời hạn ngắn, **revocation** có thể không được hỗ trợ tức thời ở mọi hệ thống; cần biết timeout/audience và biện pháp giảm rủi ro bổ sung. Với certificate/private key lộ, phải xem **certificate rotation, trust, signing consequences**.

### 7.6. Machine-to-machine authentication cần token đúng đích

Một service S có token cho API-A nhưng gọi API-B bằng cùng token là lỗi **credential audience boundary**. Nếu API-B không được phép nhận token, việc TLS connection tới B thành công không sửa được lỗi.

Ràng buộc tối thiểu:

~~~text
Credential:
  issuer       = approved identity provider
  audience     = API-A only
  permissions  = report:read
  lifetime     = short, rotated

Destination:
  scheme       = https
  host         = api-a.example.test
  TLS peer     = validated
  owner        = approved integration team
  allowed data = report query + audience-bound token
~~~

**Không truyền cùng token sang APM/trace/error exporter**. Logger chỉ nên ghi tên API, request ID, response category và authenticated principal reference đã được đánh giá riêng.

## 8. Redaction và kiểm soát dữ liệu trước khi gửi

### 8.1. Redact ở nguồn là ranh giới mạnh nhất cho telemetry

Các logger/collector nên có **allowlist các trường có thể ghi** thay vì mặc định log full request. Khi bắt buộc ghi một phần request để debug:

- Strip/mask **Authorization, Cookie, Set-Cookie, X-Api-Key, Proxy-Authorization** và các custom auth headers.
- Redact query parameters như **token, key, credential, password, secret, signature, code** theo semantics; không chỉ tên chính xác.
- Thay credentials trong JSON/body hoặc gRPC metadata bằng **[REDACTED]**.
- Không đưa secret vào exception message hoặc metrics labels.
- Không ghi private keys, session cookies, refresh tokens và raw cloud credentials dù tắt APM sampling.
- Test với synthetic test markers để chứng minh **mọi nơi thu thập** xử lý đúng.

**Chỉ mask khi hiển thị trên dashboard không đủ** nếu raw data đã lưu ở collector, object storage hoặc SaaS index. Redaction cần xảy ra **trước khi ghi hoặc egress**.

### 8.2. Allowlist schema tốt hơn blacklists thuần túy

Ví dụ event an toàn:

~~~json
{
  "event_type": "external_api_call",
  "workload": "orders-api",
  "destination": "api-a.example.test",
  "method": "POST",
  "route_template": "/v1/orders/{id}",
  "http_status": 200,
  "duration_ms": 37,
  "authenticated_principal_ref": "service-account:orders-api",
  "request_id": "req-synthetic-001",
  "secret_fields": "omitted"
}
~~~

Tránh log:

~~~json
{
  "url": "https://api-a.example.test/v1/orders?id=123&access_token=REDACTED",
  "headers": {
    "Authorization": "Bearer REDACTED",
    "Cookie": "session=REDACTED"
  },
  "payload": "RAW_BODY_MAY_CONTAIN_SECRET"
}
~~~

Ví dụ thứ hai chỉ có **placeholder**, nhưng thiết kế ghi raw request vẫn không an toàn khi sử dụng với secret thật.

### 8.3. Quy trình redaction định hướng schema

~~~text
function safeTelemetry(event):
    safe = {
      "timestamp": event.timestamp,
      "workload": sanitizeIdentifier(event.workload),
      "method": event.http.method,
      "route_template": getApprovedRouteTemplate(event.http.path),
      "status": event.http.status,
      "request_id": validateSafeRequestId(event.request_id)
    }

    # Never append raw URL, raw headers, cookies, body or env.
    # For exceptional debug fields: classify then redact before export.
    if hasApprovedDebugException(event):
        safe["diagnostic_code"] = approvedErrorCategory(event.error)

    return safe
~~~

Pseudocode này cho thấy **chỉ thu những trường cần thiết**; không phải engine tự nhận diện mọi secret trong mọi schema. Route template **không nên chứa object ID nhạy cảm** nếu không được phép; user ID/tenant ID đôi khi cũng là dữ liệu cá nhân cần kiểm soát.

### 8.4. Tại sao regex và masking có giới hạn?

Các vấn đề:

- Secret có thể **không có pattern cố định** hoặc là chuỗi base64 trông giống dữ liệu thường.
- Regex có thể bỏ sót **encoded, split, multiline, nested JSON/XML, binary payloads**.
- Một field tên password đôi khi là giá trị test, không phải secret thật.
- Mask đầu/cuối vẫn có thể lộ thông tin nhạy cảm khi token ngắn hoặc có format predictable.
- Log processor có thể chỉ redact một field nhưng **request body hoặc exception stack** còn giữ bản sao.
- Hash một password giá trị thấp/ít entropy có thể bị dò ngoại tuyến nếu dùng plain hash và công bố rộng.

Ưu tiên **không thu**, sau đó **schema-based redaction**, rồi **pattern/context DLP** như một lớp kiểm tra phụ. Không xem regex như cam kết dữ liệu không bao giờ lộ.

### 8.5. Khóa/chuỗi đã lộ trong logs cần xử lý thế nào?

Nếu secret đã đi vào logger:

1. **Không copy thêm** raw secret vào ticket/alert/email để báo cáo.
2. Xác định quyền truy cập và replication/exports của log sink.
3. Thu hồi/rotate credential theo owner với mức ưu tiên phù hợp.
4. Giảm/đóng đường ghi secret mới; kiểm tra pipeline đã redacted.
5. Yêu cầu **secure deletion/retention actions** nếu nền tảng cho phép và chính sách yêu cầu.
6. Xem audit sử dụng secret trong khoảng exposure.
7. Chỉ giữ fingerprint/evidence cần thiết, có quyền truy cập hạn chế.

**Xóa một dòng trên dashboard không chứng minh mọi bản sao ở backup/index/storage đã bị xóa**. Cần xác nhận với data owner/vendor và retention policy.

### 8.6. Canary marker giúp kiểm thử mà không dùng secret thật

Đặt một marker giả lập, ví dụ:

~~~text
TRAINING_SECRET_MARKER_2026_001_NOT_A_CREDENTIAL
~~~

Marker này **không được hệ thống nào chấp nhận để xác thực**; nó chỉ là **test canary**. Dùng trong sandbox để kiểm tra:

- Request không được phép có bị ngăn trước khi egress?
- Logger có lược bỏ marker trong output?
- DLP engine có cảnh báo đúng khi marker xuất hiện trong payload được quan sát?
- Collector alert có chứa **vị trí và class** mà không copy raw payload?
- Positive traffic không chứa marker có tiếp tục hoạt động?

Không dùng một secret thật rồi gắn hậu tố TRAINING để test; nó vẫn là secret và vẫn có thể bị lộ.

## 9. DLP: phát hiện và chặn secret trong luồng dữ liệu

### 9.1. DLP có thể kiểm tra tại những vị trí nào?

**Data Loss Prevention** tập hợp các biện pháp phân loại, phát hiện, giám sát và ngăn dữ liệu nhạy cảm xuất hiện ở destination không được phép. DLP có thể được đặt:

- **Source/application:** kiểm tra payload trước khi serialization, HTTP client hoặc SDK gửi.
- **Endpoint/agent:** giám sát ứng dụng, clipboard/file upload hoặc process network theo quyền và nền tảng.
- **Network egress gateway/SWG:** quan sát những flows thực sự đi qua, đôi khi inspection TLS theo chính sách.
- **API gateway/Service mesh proxy:** kiểm tra request/response khi proxy có nội dung và đã được thiết kế để xử lý.
- **Storage/SaaS CASB/API scanning:** kiểm tra files/objects đã upload hoặc SaaS configuration theo quyền.
- **CI/CD pipeline:** quét config/artifacts/build output **trước khi publish**.
- **Log/telemetry pipeline:** redact hoặc chặn dữ liệu nhạy cảm trước khi đi tới external collector.

Không có vị trí nào bao phủ được toàn bộ hệ thống. **TLS end-to-end, direct egress bypass, non-HTTP payload và binary/encoded data** có thể tạo blind spots ở một gateway.

### 9.2. Các phương pháp phát hiện

| Phương pháp | Ví dụ chính đáng | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| **Exact match / fingerprint** | Đối chiếu marker đã đăng ký | Precision cao với known secret | Không thấy secret mới/chưa đăng ký |
| **Structured pattern** | Định dạng credential do tổ chức phát | Dễ vận hành | False positive/negative với variants |
| **Entropy + context** | Chuỗi random gần field token | Phát hiện unknown formats | Random IDs/hashes gây false positive |
| **Field/name classification** | Authorization, password, private_key | Rõ data semantics | Secret trong field tên lạ vẫn lọt |
| **Data classification/tagging** | Object/column labeled restricted | Phù hợp governance | Phụ thuộc tagging/propagation |
| **ML/classifier** | Nhận diện patterns bất thường | Bao quát ngữ cảnh | Cần hiệu chỉnh/giải thích; lỗi và privacy |
| **Behavioral/network anomalies** | New destination/rare port/high egress | Thấy cả khi không đọc plaintext | Không biết chắc nội dung chứa secret |
| **Resource-level audit** | IAM đọc secret rồi upload object | Correlate activity/intent | Không tự khẳng định object payload |

**Không chỉ dùng entropy threshold** để chặn traffic production: hashes, compressed data, random IDs và ciphertext có thể trông giống token. Policy nên kết hợp **destination, owner, classification, known patterns và thời điểm**.

### 9.3. Exact secret detection mà không xuất raw secret lên SIEM

Một tổ chức có thể duy trì **inventory fingerprints** của những secret được phép kiểm tra, với hạn chế truy cập nghiêm ngặt. Khi cần matching các giá trị nhạy cảm:

- Dùng **HMAC với khóa bí mật quản lý tập trung** cho giá trị canonicalized thay vì đẩy raw secret/unsalted hash vào analytics rộng.
- Match chỉ ở **trusted detection component**; không phát hành khóa HMAC hay bảng fingerprints ra ngoài.
- DLP alert ghi **secret class/fingerprint reference/owner/destination/decision**, không ghi nguyên giá trị.
- Với secret rất ngắn/low entropy, phải xem nguy cơ inference/brute-force và giới hạn tập người xem.
- **Canonicalization** phải rõ: trimming, encoding, case sensitivity, Unicode/URL decoding chỉ khi phù hợp semantics và có giới hạn tránh biến đổi dữ liệu sai.
- Duy trì versions khi secret rotate và xóa fingerprints không còn cần.

**Không có HMAC nào thay được quyền kiểm soát detector**: một component vừa thấy raw payload vừa có thể truy vấn tập known secrets phải được bảo vệ chặt như security processing system.

### 9.4. Chính sách theo mức độ tin cậy

Một policy minh họa:

| Signal | Destination | Action | Lý do |
| --- | --- | --- | --- |
| Known private-key material | Bất kỳ external SaaS không được duyệt | **Block + incident** | Dữ liệu cực nhạy cảm |
| Known prod API token | Authorized resource server của token | **Allow scoped + no raw logging** | Sử dụng hợp lệ |
| Known prod token | Vendor analytics/telemetry | **Block + incident** | Wrong recipient |
| Marker synthetic | Training sink | **Detect only/test** | Không phải credential thực |
| Unknown high-entropy string | Approved API, đúng business schema | **Inspect/contextual review** | Có thể là ID hợp lệ |
| Unknown high-entropy string | Unknown external endpoint | **Risk score + restrict** | Destination risk và classification |
| Plain text debug output không chứa secret | Internal controlled collector | **Allow + retention** | Telemetry hợp lệ |
| Employee PII | Vendor chưa có hợp đồng xử lý | **Block/review** | DLP data governance |

Đây là **chính sách mẫu**. Không tự cài production block dựa trên một detector không được kiểm thử; cần data owner/security approval, false-positive assessment và rollback plan.

### 9.5. DLP decision cần ghi evidence đúng mức

Một synthetic event an toàn:

~~~json
{
  "event_id": "dlp-synthetic-001",
  "event_time": "2026-11-28T06:10:00Z",
  "workload": "orders-api",
  "principal": "sa:orders-api",
  "destination_host": "unapproved.example.test",
  "destination_class": "unapproved_external",
  "data_class": "credential_marker",
  "match_type": "synthetic_canary",
  "fingerprint_ref": "training-marker-001",
  "action": "block",
  "raw_payload_in_event": false,
  "policy_version": "egress-policy-v3",
  "synthetic": true
}
~~~

**Không ghi** toàn bộ request body, bearer token hoặc TLS private key để “có bằng chứng tốt hơn”. Incident response có thể giữ một số evidence được ủy quyền ở store riêng, nhưng alert thông thường nên chỉ chứa **references, hashes/fingerprints an toàn và context**.

### 9.6. Đơn vị chặn: request, connection hay export job?

Đặt DLP ở các lớp khác nhau tạo kết quả:

- **Application check:** từ chối tạo request hoặc loại bỏ field nhạy cảm.
- **HTTP proxy:** có thể block request/upload khi payload được inspection; cần xử lý streaming đúng.
- **TCP firewall/NetworkPolicy:** deny connection theo đích/port, thường **không phân tích nội dung**.
- **SaaS/API scan:** có thể phát hiện **sau upload**, cần quarantine/delete/revoke nhưng không phải chặn trước.
- **CI secret scanner:** ngăn artifact/code được publish; không thay runtime egress security.

Phải nói chính xác **prevention, detection hoặc post-exposure remediation**. Một CASB chỉ quét object sau khi upload **không được báo cáo là đã chặn secret trước khi rời cluster**.

### 9.7. False positives, false negatives và xử lý ngoại lệ

Các nguồn false positive:

- Random request IDs hoặc hash checksums trông giống tokens.
- Test fixtures chứa dữ liệu giả.
- Base64-encoded images/small files.
- JWT-like strings trong documentation.
- Authentication headers hợp lệ gửi đúng resource server.

Các nguồn false negative:

- Secret format tùy biến.
- Payload encrypted/binary chưa thể inspect.
- Redirect hoặc direct egress bỏ DLP gateway.
- Secrets bị split, transformed hoặc nằm trong nested archives.
- Detector outdated khi provider đổi format.

Quy trình tuning:

1. Test với **synthetic corpus** gồm positive, negative và edge cases.
2. Đo precision/recall trong **mẫu được phép** và không cố thu raw production secrets để train.
3. Bổ sung context: field, principal, recipient, endpoint, policy owner.
4. Dùng **detect-only** trong thời gian đánh giá khi phù hợp, có risk acceptance.
5. Chuyển block cho những classes/matches đáng tin cậy sau review.
6. Có kênh giải quyết false positive có SLA và **exception expiry**.
7. Giám sát false negatives qua incident feedback và kiểm tra thay đổi.

**Không cho một người có quyền tạo ngoại lệ vĩnh viễn bypass DLP cho mọi destinations**. Hạn chế theo workload, purpose, data class, target, expiry và phê duyệt.

### 9.8. TLS inspection không đồng nghĩa “đọc được mọi secret”

Ngay cả với proxy giải mã HTTPS hợp lệ, DLP vẫn có thể không hiểu **compressed, multipart, protobuf, encrypted body, nested zip hoặc application-specific encoding**. Cần:

- Giới hạn parser/size/decompression để tránh DoS.
- Phân loại data format và xử lý streaming/large bodies an toàn.
- Chỉ inspect khi có privacy/legal authorization.
- Có xử lý **fail-open/fail-closed** rõ nếu engine timeout hoặc unsupported content.
- Chuyển high-risk sensitive actions sang **source-level validation** khi network inspection không đủ.
- Ghi coverage/unsupported protocol, không báo “100% scan” khi có blind spots.

### 9.9. DLP chính xác phải gắn với mục tiêu nghiệp vụ

Một payment integration có thể cần gửi **payment token được thiết kế cho provider**, nhưng không bao giờ được gửi **private signing key** của doanh nghiệp. Một support ticket có thể cần request ID nhưng không cần Session Cookie. Vì thế **contextual allowlist dữ liệu** là biện pháp khả thi hơn quy tắc “mọi chuỗi trông giống token đều bị chặn”.

## 10. Kiến trúc egress controls nhiều tầng

### 10.1. Kiểm soát ở ứng dụng

**Primary layer**:

- HTTP client wrapper validate **approved host/scheme/port/redirect chain**.
- Payload schema whitelist cho integrations.
- Không đính kèm global Authorization header cho mọi request client tạo.
- Secret được inject theo **destination-specific credential provider**.
- Rate limit/export approval cho bulk data.
- Application audit: ai/khi nào/export gì, không ghi raw secret.

**Không tin client-side URL check bằng string prefix** để xác nhận destination. Hostnames phải parse/canonicalize theo URL parser an toàn; quan tâm DNS resolution, redirect và môi trường proxy. Với backend-sensitive applications, chỉ sử dụng **destination IDs đã đăng ký** thay vì cho người dùng truyền URL tùy ý.

### 10.2. Kiểm soát ở container/host

- Least-privilege process, không chạy application với quyền cấu hình network/host firewall không cần.
- Egress policy trên container/Pod, default deny ở trust tiers nhạy cảm.
- Pod Security/admission hạn chế **hostNetwork, privileged capabilities và secondary interfaces** nếu không được duyệt.
- Block trực tiếp tới node/cloud metadata credentials ngoài use case.
- Giám sát eBPF/CNI/host flows theo Pod UID/workload identity khi khả dụng.
- Hạn chế access tới secrets ở container runtime, /proc, volumes, process dumps và debug endpoints.

### 10.3. Kiểm soát ở network/cloud boundary

- VPC/subnet routing, cloud SG/NACL/firewall và NAT/egress gateway.
- DNS resolver enforcement, DNS security, private DNS rules và DoH/DoT governance.
- Private service endpoints chỉ cho phép đúng **resource/account/tenant** khi provider hỗ trợ.
- Network segmentation để production không tự thấy partner/dev SaaS integrations.
- Hạn chế routes vào VPC peering/VPN/on-prem theo prefix allowlists.
- Proxy/SWG kiểm soát TLS hostname/recipient và DLP payload khi được ủy quyền.
- Log/export visibility ở những alternate paths (bypass prevention).

### 10.4. Kiểm soát ở tài nguyên nhận

Một network connection tới host object storage được duyệt nhưng vào **bucket/tenant sai** vẫn là dữ liệu thất thoát. Controls cần:

- Resource policies và IAM chỉ đúng bucket/object/prefix/queue/topic.
- Data classification tags và approved sharing scopes.
- Per-account/tenant destination validation.
- Object write audit và retention/quarantine.
- Scoped authentication/certificates và revocation.

### 10.5. Egress gateway với đường bypass

~~~mermaid
flowchart TB
  W["Workload with limited secret"] --> CNI["Pod egress ACL"]
  CNI --> P["Approved egress proxy / SWG"]
  P --> V["Verify TLS peer and destination"]
  V --> DLP["DLP on inspectable allowed content"]
  DLP --> DEST["Approved API/tenant"]
  CNI -. "Attempt direct path" .-> NAT["Node NAT / VPC peering"]
  NAT -. "Deny by cloud firewall" .-> BLOCK["Unauthorized destination"]
  AUD["App / CNI / proxy / resource audit"] -. "evidence" .-> P
  AUD -. "evidence" .-> NAT
~~~

Một egress gateway chỉ bảo vệ được **traffic đi qua**. Ngăn trực tiếp phải ở **mạng bên dưới**. Không cho rằng Service mesh egress policies tự biến VPC route thành một firewall không thể bypass.

### 10.6. Đánh giá những đường nằm ngoài HTTP proxy

| Đường | Có thể proxy HTTP nhìn thấy? | Kiểm soát bổ sung |
| --- | --- | --- |
| Direct UDP DNS/DoT/DoH | Tùy proxy/route/protocol | DNS governance + firewall |
| UDP/QUIC/HTTP3 | Không mặc định ở mọi HTTP proxy | Protocol policy, gateway compatibility |
| Private VPC peering | Có thể bypass public egress proxy | VPC routes/firewall, app IAM |
| On-prem VPN/private circuit | Có thể là direct private path | Prefix ACL, DLP at source, resource auth |
| Secondary CNI interface | Tùy mesh/CNI | Per-interface rules, admission |
| HostNetwork/NodePort | Tùy dataplane | Host firewall, cloud SG, auditing |
| Object storage API through private endpoint | Có thể không đi SWG | Endpoint resource policy, data classification |
| SaaS SDK embedded in app | Nếu request đi proxy đã enforce | SDK governance, payload allowlist |
| Message broker publish | L4 gateway có thể không hiểu nội dung | Topic ACL, schema/DLP producer |
| Log exporter/API telemetry | Có thể là service-specific path | Redaction at source + collector |

Không chỉ so “có một rule allow/deny” mà cần test **source IP/identity, destination, protocol, path, IPv4/IPv6, NAT state và final resource permission**.

### 10.7. Fail-safe behavior với egress DLP

Khi DLP engine hoặc proxy lỗi:

- Với **high-risk destinations/secrets**, thiết kế có thể yêu cầu **fail closed** cho export nhạy cảm.
- Với telemetry không nhạy cảm, có thể dùng **bounded local buffering** hoặc graceful degradation để tránh mất availability.
- **Không fallback sang direct Internet** nếu policy yêu cầu proxy; fallback path phải được phê duyệt và có controls tương đương.
- Bật health/latency alerts cho proxy/DLP; ghi coverage gaps.
- Dùng canary, queues có quota/timeouts và recovery runbook.

Không có một chính sách fail closed áp được cho mọi hệ thống mà không xét SLO, availability và privacy. **Phân loại data path**, review các tradeoffs và thử nghiệm failure modes.

## 11. Kubernetes, cloud, service mesh và CI/CD: kiểm soát các nguồn secret

### 11.1. Kubernetes Pod có thể nhận secret bằng nhiều cách

Đường cấp credential trong một cluster có thể là:

~~~text
Kubernetes Secret / external secret provider
  -> mounted volume or controlled environment/config
  -> application process
  -> HTTP client / SDK / database driver
  -> CNI / proxy / gateway / VPC route
  -> intended destination OR unintended destination
~~~

Một Pod bị giới hạn NetworkPolicy egress vẫn có thể gửi token tới **đích được allow** nhưng sai mục đích, chẳng hạn nhúng database password vào một analytics request. Vì vậy:

- **Secret access policy** xác định Pod nào được đọc.
- **Data schema policy** xác định trường nào được gửi đến từng integration.
- **NetworkPolicy/egress gateway** xác định nơi Pod được kết nối.
- **Workload identity/TLS** xác định phía nhận và quyền truy cập.
- **DLP/application audit** xác minh dữ liệu và hành vi không vượt mục đích.

### 11.2. Mẫu default-deny egress cho một namespace ứng dụng

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: client-deny-egress
  namespace: secret-egress-lab
spec:
  podSelector:
    matchLabels:
      app: test-client
  policyTypes:
    - Egress
~~~

Đây là ví dụ **cho namespace lab**, không áp trực tiếp production. Khi CNI thực thi NetworkPolicy, các Pods được chọn trở thành **egress-isolated**; cần thêm allow rules cho các destinations cần thiết. **Nếu một policy khác đã allow rộng**, các allow rules được cộng gộp và default-deny này không làm traffic đã được policy khác cho phép biến mất.

Không dùng NetworkPolicy như một **content-aware DLP engine**: nó không đọc HTTP header/body để nhận biết token. Nó là **lớp ngăn kết nối tới đích không được phép**.

### 11.3. Mẫu allow egress tới một Pod được chỉ định

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: client-allow-approved-sink
  namespace: secret-egress-lab
spec:
  podSelector:
    matchLabels:
      app: test-client
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: approved-sink
      ports:
        - protocol: TCP
          port: 8080
~~~

Trong cùng namespace, một podSelector trong egress chọn **Pod đích**, không phải Service object. Khi client dùng Service ClusterIP có targetPort 8080, behavior liên quan translation/NAT và nơi policy thực thi có thể khác theo CNI; hãy kiểm chứng **Service và direct Pod IP paths**.

**Một Pod được gắn nhãn approved-sink không tự có quyền nhận secret production.** Đây chỉ là rule allow reachability trong lab. Để tránh label spoofing, hạn chế quyền gắn/sửa labels và dùng **recipient identity + application authorization**.

### 11.4. DNS egress dưới default-deny

Nếu application gọi hostname, cần route tới resolver đúng. Ví dụ allow DNS tới CoreDNS Pods theo convention thường gặp:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: client-allow-cluster-dns
  namespace: secret-egress-lab
spec:
  podSelector:
    matchLabels:
      app: test-client
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Không portable mặc định:** CoreDNS labels, NodeLocal DNSCache, resolver IP, CNI policy order và DNS proxying khác nhau giữa clusters. Cần xác minh **DNS endpoints thực**. Một allow đúng YAML nhưng không match DNS sẽ tạo DNS outage; tránh sửa bằng cách allow all outbound.

### 11.5. Secrets, ServiceAccount và node metadata

Kubernetes ServiceAccount token và cloud workload credentials cần:

- **Audience and lifetime scoping**, tránh token dùng được cho quá nhiều services.
- Least-privilege RBAC ở Kubernetes API.
- Cloud workload identity thay static cloud keys khi hỗ trợ.
- Bảo vệ metadata/credential endpoints theo cloud node design; không giả định chỉ một network policy ở Pod là đủ để chặn mọi host-mediated traffic.
- Giới hạn privileged/hostNetwork Pods và secondary interfaces.
- Auditing việc cấp token/secret và abnormal cloud API calls.

**Không bật automountServiceAccountToken** cho Pods không cần gọi Kubernetes API, khi có thể cấu hình an toàn. Nếu ứng dụng cần token, cấp scope đúng—đừng disable credential rồi sửa bằng cluster-admin credentials tĩnh.

### 11.6. CI/CD secrets và network egress

Build runner và deployment agents thường có quyền đọc secrets/registry tokens/cloud credentials. Nguy cơ:

- Một step in ra **env** hoặc set verbose shell logging.
- Secrets bị copy vào Docker image layer, artifact, test report.
- Job upload artifact/log tới **bucket/tenant ngoài phạm vi**.
- Third-party CI action/dependency thực thi với broad repository/network access.
- Pull request từ nguồn không đáng tin chạy với production secrets.
- Docker build script dùng build argument chứa credential, khiến build metadata/layer bị lộ tùy công cụ.

Control:

1. Cấp secrets **chỉ cho jobs/branches/environments tin cậy**.
2. Dùng **OIDC federation/ephemeral credentials**, giới hạn token permissions.
3. Pin, review, sandbox third-party actions/build dependencies.
4. Không để untrusted fork code chạy trong job có production secrets.
5. Tách build và publish permissions.
6. Scan **source, build logs, artifacts, container images** trước khi xuất bản.
7. Giới hạn **network egress của runner** và package registry destinations.
8. Bảo vệ logs và tự động **revoke/rotate** khi pipeline phát hiện credential thật.

### 11.7. Egress từ dependency và third-party SDK

Một library hoặc SDK có thể mở kết nối riêng để gửi:

- Crash diagnostics, analytics.
- License/feature usage.
- Version/update checks.
- Support telemetry.
- Remote configuration.

Quy trình dependency governance nên hỏi **đích mạng nào, payload/headers gì, cơ chế opt-in/opt-out, retention, quốc gia/tenant lưu dữ liệu và ai sở hữu quyền thay cấu hình**. **SCA/SBOM** hữu ích để inventory dependencies nhưng **không tự chứng minh network destinations hoặc payload**; cần runtime telemetry và network policy.

### 11.8. Cloud private endpoint vẫn phải giới hạn resource

Private endpoint đến object storage hoặc secrets manager **thu hẹp đường mạng**, nhưng còn phải kiểm tra:

- Destination cloud account/project/subscription và resource IDs.
- Resource policies (bucket/container/topic/secret).
- IAM role của workload và scope request.
- TLS peer identity, endpoint DNS mapping.
- VPC endpoint policy khi provider hỗ trợ.
- Flow/audit logs từ bên nguồn và bên nhận.

**Cùng một cloud service hostname hoặc shared network endpoint không đồng nghĩa quyền ghi mọi bucket/tenant đã được duyệt.** Một upload vào bucket bên ngoài tổ chức có thể là egress trái policy dù IP traffic nằm trong private cloud backbone.

### 11.9. Service mesh sidecar và egress gateway

Một sidecar có thể origination TLS, gắn identity, routing và telemetry; nhưng không phải **mọi Pod/port/interface/protocol** chắc chắn đi qua sidecar. Egress controls phải xét:

- Pod chưa inject hoặc mesh migration chưa hoàn tất.
- hostNetwork/secondary interface.
- Port/IP range exclusions và redirect behavior.
- UDP/QUIC/DNS traffic không hỗ trợ như HTTP TCP.
- VPC NAT/peering routes ngoài egress gateway.
- L7 proxy chỉ thấy opaque TLS không kiểm tra HTTP payload.

**Sidecar running không chứng minh DLP enforcement**, và **mTLS không chứng minh secret không rời khỏi trusted audience**. Kết hợp NetworkPolicy/cloud firewall với kiểm soát payload tại ứng dụng.

### 11.10. Egress qua VPN/hybrid và doanh nghiệp đối tác

Một Pod gửi credentials tới dịch vụ on-prem có thể đi:

~~~text
Pod -> CNI/Node -> VPC route -> VPN/private circuit -> on-prem service
~~~

Cần hỏi **IP source sau NAT, route trả lời, firewall, IAM, TLS endpoint, log coverage và contract cho data exchange**. Private circuit không tự đồng nghĩa application payload đã mã hóa hay secret được gửi đúng đối tượng. Khi đối tác thay DNS/IP/CDN, review lại destination allowlist và dữ liệu có thể đi theo đường mới.

### 11.11. Multi-cluster và Kubernetes Secrets replication

Khi nhiều clusters dùng chung workloads:

- Không copy cùng admin secret sang mọi cluster theo thói quen.
- Dùng identities/roles theo cluster, environment và trust domain.
- Replicate secrets chỉ khi có business need, encryption/audit/rotation đồng bộ.
- Kiểm tra Service Export/Gateway/DNS không làm một endpoint mới tự nhận quyền cũ.
- Khi failover sang DR, xác minh resource recipient, certificates và egress policy tương đương.
- Audit secret store access theo **cluster ID, workload UID và event time**.

**HA/DR không được tạo đường xuất secret ít kiểm soát hơn production**. Backup path phải có security policy parity.

## 12. Lab an toàn: chặn đích egress sai và phát hiện marker giả lập

### 12.1. Mục đích

Lab có **hai phần độc lập**:

**Phần A — Network:** dùng một Kubernetes sandbox để chứng minh workload chỉ được **kết nối đến service đã duyệt**, không tới service ngoài policy. **Không cần secret thật** để làm NetworkPolicy test.

**Phần B — Data:** mô phỏng **secret marker không phải credential** trong một event/request mẫu, kiểm tra redaction và DLP decision trước khi cho phép gửi tới sink. Có thể làm phần B **offline** hoàn toàn; không phải truyền marker qua Internet hoặc một endpoint không thuộc quyền kiểm soát.

Yêu cầu:

- Cluster lab riêng hoặc namespace do bạn sở hữu, CNI **thực thi Kubernetes NetworkPolicy**.
- Image sources được phê duyệt; ví dụ dùng image phổ biến để minh họa nhưng production cần pin digest, scan và policy.
- Không dùng production secrets, real tokens, real private keys, dữ liệu khách hàng.
- Không chạy test thay đổi network policy trên namespaces production, hệ thống DNS/CNI hoặc workloads không thuộc bài học.
- Nếu không có cluster lab, dùng **decision matrix/synthetic events** ở phần B mà không cần thực thi kubectl.

### 12.2. Topology

~~~mermaid
flowchart LR
  C["test-client Pod\nno real secret"] --> NP{"Egress NetworkPolicy"}
  NP -- "TCP/8080 approved" --> AS["approved-sink\nService/Pod"]
  NP -. "TCP/8080 denied" .-> US["unapproved-sink\nService/Pod"]
  C --> DNS["Cluster DNS\nallowed explicitly"]
  DLP["Synthetic DLP check\nredact before export"] -. "Decision only, offline" .-> C
~~~

Khi test **denied path**, chính việc kết nối thất bại mới là kết quả mong đợi. Không chuyển sang mạng bên ngoài để có một endpoint “unapproved” thật, vì đó không cần thiết và có thể phát sinh rò dữ liệu.

### 12.3. Manifest workload sandbox

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: secret-egress-lab
  labels:
    purpose: synthetic-egress-training
---
apiVersion: v1
kind: Pod
metadata:
  name: approved-sink
  namespace: secret-egress-lab
  labels:
    app: approved-sink
spec:
  automountServiceAccountToken: false
  containers:
    - name: http
      image: python:3.12-alpine
      command: ["python", "-u", "-m", "http.server", "8080", "--bind", "0.0.0.0"]
      ports:
        - containerPort: 8080
      securityContext:
        runAsUser: 10001
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Pod
metadata:
  name: unapproved-sink
  namespace: secret-egress-lab
  labels:
    app: unapproved-sink
spec:
  automountServiceAccountToken: false
  containers:
    - name: http
      image: python:3.12-alpine
      command: ["python", "-u", "-m", "http.server", "8080", "--bind", "0.0.0.0"]
      ports:
        - containerPort: 8080
      securityContext:
        runAsUser: 10001
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Pod
metadata:
  name: test-client
  namespace: secret-egress-lab
  labels:
    app: test-client
spec:
  automountServiceAccountToken: false
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsUser: 10001
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Service
metadata:
  name: approved-sink
  namespace: secret-egress-lab
spec:
  selector:
    app: approved-sink
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      protocol: TCP
---
apiVersion: v1
kind: Service
metadata:
  name: unapproved-sink
  namespace: secret-egress-lab
spec:
  selector:
    app: unapproved-sink
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      protocol: TCP
~~~

**Đây không phải production manifest:** chưa có resource quotas, requests/limits, readiness probes, image digest, network sandbox hardening đầy đủ hoặc tracing. Python HTTP server chỉ cho việc kiểm chứng HTTP connectivity; **không được dùng để tiếp nhận token thật**.

### 12.4. Xác nhận baseline trước khi áp network policy

Sau khi tạo những resources trong cluster được phép:

~~~bash
kubectl get pods -n secret-egress-lab -o wide
kubectl get services -n secret-egress-lab
kubectl get endpointslices -n secret-egress-lab

kubectl exec -n secret-egress-lab test-client -- \
  wget -T 3 -qO- http://approved-sink:8080/

kubectl exec -n secret-egress-lab test-client -- \
  wget -T 3 -qO- http://unapproved-sink:8080/
~~~

Trước khi có policy mới, cả hai connections **có thể** thành công nếu CNI/cluster đã cho phép giao tiếp, không có policy khác và Pods/Services sẵn sàng. **Không xem baseline là mặc định đảm bảo của mọi cluster**—nếu lab có policies hiện hữu, chúng có thể chặn sẵn.

### 12.5. Áp policy đã thiết kế ở mục 11

Sử dụng ba policies thuộc mục 11 trong namespace **secret-egress-lab**: default-deny egress của test-client, allow approved-sink TCP/8080 và allow đúng DNS resolver (điều chỉnh theo CNI/CoreDNS thực).

Chạy lại hai requests ở mục 12.4. Kỳ vọng:

| Client | Destination | Expected outcome |
| --- | --- | --- |
| test-client | approved-sink:8080 | **Allow** nếu source egress/destination ingress đều phù hợp |
| test-client | unapproved-sink:8080 | **Deny** vì không thuộc egress allowlist |
| test-client | DNS resolver được duyệt | **Allow** cho name resolution |
| test-client | External Internet không nằm trong policy | **Deny**, trừ exceptions/host paths khác |

Nếu **unapproved-sink vẫn reachable**, phải kiểm tra **các NetworkPolicy khác chọn test-client, CNI enforcement, NAT/Service translation và labels**. Nếu **DNS fail** nhưng Pod IP direct test cho kết quả dự kiến, cần sửa DNS allowance theo resolver thật; không mở all egress.

### 12.6. Giới hạn phép thử NetworkPolicy

Kết quả NetworkPolicy **chỉ chứng minh tính reachability của test path trong CNI**. Nó **không chứng minh** một payload chứa token đã được DLP phát hiện. Cũng không chứng minh bucket/tenant resource-level permission được kiểm soát.

Một approved-sink vẫn có thể nhận **secret sai phép** nếu ứng dụng cố gửi. Vì vậy cần phần B—redaction và data-policy checks trước serialization/export.

### 12.7. Dataset synthetic cho kiểm thử DLP

~~~json
[
  {
    "id": "T01",
    "destination": "approved-sink",
    "field": "request_id",
    "value": "req-001",
    "data_class": "operational_metadata"
  },
  {
    "id": "T02",
    "destination": "unapproved-sink",
    "field": "debug_note",
    "value": "TRAINING_SECRET_MARKER_2026_001_NOT_A_CREDENTIAL",
    "data_class": "synthetic_sensitive_marker"
  },
  {
    "id": "T03",
    "destination": "approved-sink",
    "field": "authorization",
    "value": "Bearer TEST_TOKEN_NOT_VALID",
    "data_class": "synthetic_auth_header"
  },
  {
    "id": "T04",
    "destination": "approved-sink",
    "field": "error_category",
    "value": "upstream_timeout",
    "data_class": "operational_metadata"
  }
]
~~~

Kỳ vọng:

- T01 và T04 có thể đi vào log đã allowlist nếu policy cho phép.
- T02 cần **deny vì destination không được duyệt**, đồng thời marker không nên được copy nguyên vào alert production-style.
- T03 minh họa **synthetic authentication data**. Chỉ cho phép token thật trong request tới **đúng authentication/resource server**, không vào telemetry sink. Với log output, trường Authorization phải bị omit/redact.

**Tên approved-sink trong lab không biến nó thành resource server hợp lệ cho bearer token.** Bài học là phân biệt *network route được phép* với *credential disclosure được phép*.

### 12.8. Pseudocode cho data export guard

~~~text
function safeOutbound(workload, destinationId, payload):
    policy = policyRegistry.lookup(workload, destinationId)
    if policy is missing or expired:
        return BLOCK("destination not approved")

    verified = resolveAndVerifyRecipient(policy)
    if not verified:
        return BLOCK("recipient identity not verified")

    classification = classifyPayload(payload)
    if classification contains forbiddenSecretClassFor(policy):
        recordEventWithoutRawSecret(workload, policy, classification)
        return BLOCK("unauthorized data class")

    safePayload = serializeOnlyApprovedFields(payload, policy)
    if safePayload contains unexpected credential fields:
        return BLOCK("unexpected credential field")

    return SEND_WITH_TLS_VALIDATION(safePayload, policy)
~~~

Đây là **pseudocode giáo dục**, không phải thư viện kiểm tra URL/TLS/DLP hoàn chỉnh. Triển khai thực cần giải quyết **DNS/redirect/rebinding, encoded content, streaming, parser errors, caller authorization, recipient identity, failures và race conditions**. Thường nên dùng một egress client/gateway đã được security review thay vì tự viết lại transport security.

### 12.9. Bộ test case phòng vệ

| ID | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| E01 | Client→approved-sink trước policy | Có thể allow tùy baseline |
| E02 | Client→unapproved-sink trước policy | Có thể allow tùy baseline |
| E03 | Client→approved-sink sau policy | Allow |
| E04 | Client→unapproved-sink sau policy | Deny |
| E05 | DNS được duyệt sau policy | Allow |
| E06 | DNS ngoài phạm vi | Deny qua control tương ứng |
| E07 | Host/IP ngoài allowlist | Deny |
| E08 | Approved domain nhưng sai TLS peer | Deny, không bỏ verify |
| E09 | Approved hostname redirect ra unapproved origin | Không forward secret, deny/review |
| E10 | Secret đặt trong URL query synthetic | Redact/deny log/export |
| E11 | Authorization field trong telemetry | Omit/redact |
| E12 | Known synthetic marker tới unapproved | Block + no raw event payload |
| E13 | Known synthetic marker tới approved telemetry | Omit/redact nếu không có business purpose |
| E14 | Request ID ngẫu nhiên, không phải secret | Không tạo block sai chỉ vì entropy |
| E15 | Upload tới approved service nhưng wrong tenant | Deny bằng resource/recipient policy |
| E16 | Alternate direct NAT path | Deny nếu gateway là bắt buộc |
| E17 | IPv6 destination ngoài policy | Deny bằng IPv6 controls |
| E18 | Pod hostNetwork/secondary interface (mô phỏng) | Có compensating controls |
| E19 | DLP engine timeout high-risk export | Fail-safe theo risk policy |
| E20 | DLP collector không có heartbeat | Coverage alert, không kết luận không traffic |
| E21 | Short-lived token expired | Reject ở identity/server layer |
| E22 | Token đúng audience gửi auth endpoint | Cho phép có kiểm soát, không log raw token |
| E23 | Cloud object storage đúng host, wrong bucket | Resource policy deny |
| E24 | CI artifact chứa fake marker | Scanner detect trước publish |
| E25 | Proxy logs request không có token | Chỉ status/route metadata cần thiết |
| E26 | Pod IP được cấp lại | Correlate theo Pod UID/event time |
| E27 | DNS queries chứa synthetic marker | Detect anomaly, không copy full string không cần |
| E28 | Secrets manager API truy cập bởi unauthorized SA | RBAC/IAM deny |

**E08–E09, E16–E19, E21–E24 và E27–E28** là tình huống mô phỏng nếu lab không có hạ tầng tương ứng. Không thử làm lộ credential thật, làm hỏng DNS hoặc đổi cloud routes của production.

### 12.10. Dọn lab và lưu evidence

Lưu **manifest đã duyệt, policy effective state, Pod/Service endpoints, positive/negative results và redacted DLP events**. Khi dọn, chỉ xóa resources thuộc namespace lab mình sở hữu; không xóa namespace chia sẻ/production.

Bài thu hoạch nên trả lời: **NetworkPolicy đã ngăn đường đi nào? Data guard đã ngăn nội dung nào? Lớp nào còn không quan sát được encrypted/body payload? Nếu sink được phép nhưng credential không được phép thì ai chặn?**

## 13. Telemetry, SIEM và phát hiện khả năng thất thoát secret

### 13.1. Một nguồn log chỉ nhìn thấy một phần sự thật

| Nguồn | Bằng chứng có thể cung cấp | Không tự chứng minh |
| --- | --- | --- |
| **Secret manager audit** | Ai/role nào đọc secret và thời điểm | Secret sau đó được gửi tới đâu |
| **Application audit** | API operation, destination ID, data classification | Packet network đi qua route nào nếu không có trace |
| **HTTP/egress proxy logs** | Host/method/status/route, policy decision | Nội dung khi TLS opaque, unproxied path |
| **DLP event** | Class/fingerprint/destination/decision tại điểm scan | Mọi encrypted/bypass traffic đều đã scan |
| **CNI/NetworkPolicy logs** | Pod/IP/port/allow-deny theo khả năng plugin | Secret bytes hoặc business authorization |
| **Cloud VPC flow logs** | Network tuples/bytes qua điểm capture | Pod identity nếu NAT, payload khi TLS |
| **DNS logs** | Hostname được truy vấn, latency/rcode | Connection sau đó thành công hoặc secret nằm trong TLS |
| **SWG/CASB** | Web/SaaS requests hoặc cloud objects theo integration | Mọi network/private paths nếu ngoài scope |
| **CI logs/scanners** | Secret trong artifact/config/commit nếu scanner thấy | Runtime data leak khi service chạy |
| **Kubernetes/cloud audit** | Ai sửa policy, secret access IAM, route/SG | Payload đã bị tiết lộ hay chưa |
| **Destination resource audit** | Bucket/topic/API read/write, principal/tenant | Nguồn request trước NAT nếu thiếu identity mapping |
| **Collector heartbeat** | Nguồn telemetry có hoạt động | Không có traffic khi logs im lặng |

Để kết luận một secret bị gửi, cần **bằng chứng ở lớp nội dung hoặc nguồn cấp secret**, nơi việc xử lý plaintext được ủy quyền, và **evidence của destination/outcome**. Chỉ thấy network flow TCP/443 hoặc DNS lookup **không chứng minh nội dung đã rời khỏi mạng**.

### 13.2. Tương quan theo thời gian và danh tính

Ví dụ:

~~~text
10:00:00Z  secret-manager: workload orders-api reads secretRef=api-a/read
10:00:01Z  app-egress: orders-api plans destination=api-a, route=/v1/order
10:00:01Z  CNI: orders-api PodIP 10.244.1.12 -> egress-gw TCP/443 allow
10:00:02Z  proxy: peer=api-a.example.test TLS verified, status=200
10:00:02Z  app: data_class=non-sensitive-order-ref, action=completed
~~~

Chuỗi này gợi ý **luồng hợp lệ** nếu resource-level policy, scopes và ownership được xác minh. Nhưng không được tự suy secretRef đã được đưa vào payload, vì secret manager read có thể chỉ là auth operation.

Ngược lại:

~~~text
10:05:00Z  secret-manager: workload exporter reads prod-secretRef
10:05:02Z  CNI: exporter -> unapproved external IP TCP/443 allow
10:05:03Z  app-egress: destination not registered
10:05:03Z  proxy: no event
10:05:04Z  collector-health: healthy
~~~

Đây là **suspicious sequence**, không tự là confirmed exfil. Cần kiểm tra effective route, NAT, payload checks ở nguồn, actual TLS peer và ứng dụng đã gửi gì; nếu secret cực nhạy cảm và bằng chứng đủ lo ngại, thực hiện **proportionate containment/rotation** theo playbook.

### 13.3. Pod IP và NAT mapping theo event time

Ở Kubernetes:

- Pod IP có thể **được cấp lại** cho Pod khác sau khi Pod cũ bị xóa.
- Nhiều Pods có thể dùng một **Node/NAT public IP** khi egress.
- Một CNI overlay có thể làm VPC logs chỉ thấy **Node IP tunnel traffic**.
- HostNetwork/secondary interface có thể không đi cùng capture scope.

Khi forensic, join theo **cluster ID, namespace, Pod UID, Node, Pod IP, service account, IPAM allocation time, NAT translation records và event timestamp**. **Đừng xem snapshot Pod hiện tại** là bằng chứng chủ thể của flow tuần trước.

### 13.4. Các cảnh báo hữu ích

| Rule | Đầu vào | Ý nghĩa cần điều tra |
| --- | --- | --- |
| Secret access → unapproved egress | Secret manager + app/CNI flow | Có thể credential bị đưa ra ngoài |
| DLP matched known secret at outbound boundary | DLP fingerprint + destination | Nội dung nhạy cảm nằm trong payload được scan |
| New destination for secret-bearing workload | Flow/DNS baseline + asset inventory | Shadow integration hoặc route drift |
| Direct DNS/DoH outside resolver policy | Network/endpoint logs | Bypass resolver policy hoặc config sai |
| Spike bytes to partner/VPC peer | Cloud flow + app audit | Có thể bulk export, backup hoặc data movement |
| Egress gateway traffic drops but NAT traffic rises | Proxy+CNI/VPC telemetry | Direct-route bypass hoặc collector issues |
| Authorization header appears in APM field | Scanner at log pipeline | Redaction gap gây exposure tại telemetry |
| CI artifact includes credential-shaped value | Pre-publish scanner | Có thể public artifact risk |
| Broad egress rule or SG added | Kubernetes/cloud audit | Thay đổi trust boundary |
| Pod suddenly requests Secrets it never used | Kubernetes/secret manager audit | Overprivilege hoặc compromise |
| Collector heartbeat missing | Exporter health/ingestion | Coverage gap, không phải không traffic |

Thiết kế detection phải chứa **expected behavior** theo workload/time-of-day. Một backup hợp lệ có thể tạo spike bytes; yêu cầu là **review identity, destination và data policy**, không kết luận xâm nhập chỉ từ lượng bytes.

### 13.5. Mẫu SIEM event không chứa secret

~~~json
{
  "event_type": "possible_secret_egress",
  "event_time": "2026-11-28T06:15:00Z",
  "workload": {
    "cluster": "training-cluster",
    "namespace": "payments",
    "pod_uid": "synthetic-pod-uid-001",
    "service_account": "payments-api"
  },
  "destination": {
    "class": "unapproved_external",
    "host": "unapproved.example.test",
    "resource_tenant": "unknown"
  },
  "detection": {
    "class": "credential_like_payload",
    "confidence": "high",
    "match_reference": "fingerprint-ref-001",
    "raw_secret_logged": false
  },
  "network": {
    "protocol": "HTTPS",
    "observed_at": "approved_egress_proxy",
    "decision": "blocked"
  },
  "evidence_quality": "payload_inspected_at_authorized_boundary",
  "synthetic": true
}
~~~

Không ghi **raw credential**, và không tự sao chép cặp host/tenant từ log vào ticket không bảo mật nếu chúng chứa dữ liệu cá nhân. Trong alert thật, confidence cần có **định nghĩa/thang đo** rõ và có thể audit detector logic.

### 13.6. SLO/metric về coverage, không chỉ số lượng alert

Các metric:

- % workloads có **egress owner và approved destination registry**.
- % high-risk workloads có **default-deny enforced** với negative test.
- % outbound bytes/requests có **route/peer identity** quan sát được ở boundary phù hợp.
- DLP **precision/false-positive rate**, theo data class.
- % APM/log events đã **redacted trước xuất** theo canary tests.
- Token lifetime và % secrets có rotation owner.
- **Mean time to contain/rotate** khi confirmed exposure.
- Số exception quá hạn/không có owner.
- Collector heartbeat, ingestion lag và alternate-path coverage.

**Không báo “0 detected leaks” là bảo đảm an toàn nếu 30% traffic đi ngoài DLP visibility**. Kết quả cần luôn ghi **denominator và blind spots**.

### 13.7. Privacy trong DLP và observability

Một detector có thể tiếp xúc với dữ liệu người dùng hoặc secret hợp lệ khi inspection. Vì vậy:

1. Chỉ xử lý tại **điểm có quyền và mục đích rõ**.
2. Giới hạn nhân sự truy cập **matched content** và key fingerprints.
3. Dùng **data minimization**, redaction và retention có thời hạn.
4. Tách **operational telemetry** khỏi forensic evidence store.
5. Không tự thu thập full encrypted packets hoặc bật TLS interception rộng trên thiết bị người dùng ngoài chính sách.
6. Với nhà cung cấp DLP/SIEM, review tenant isolation, subprocessors, khu vực lưu dữ liệu và deletion guarantees.

## 14. Threat modeling theo STRIDE và đường tấn công

### 14.1. Bảo vệ những tài sản nào?

- Secret values và **khả năng dùng/thu hồi** chúng.
- IAM principals/workload identities có quyền cấp hoặc truy cập secret.
- Source code, CI pipelines, containers và runtime memory.
- Approved recipients/tenant/resource IDs.
- Routes, DNS, firewalls, proxies và egress policies.
- DLP detectors, fingerprint keys và log/evidence stores.
- Customer data và business processes mà credential có thể truy cập.

Ranh giới tin cậy: **Secret store → workload**, **workload → proxy**, **proxy → cloud/Internet/private peer**, **application → APM/CI/third party**, **data export → storage tenant**.

### 14.2. STRIDE

| STRIDE | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Spoofing** | Gửi token tới hostname/recipient giả hoặc spoof trusted header | TLS peer validation, audience binding, secure redirect |
| **Tampering** | Sửa egress allowlist hoặc logging redaction config | IaC/GitOps review, RBAC/admission, audit |
| **Repudiation** | Secret xuất hiện ở vendor nhưng không biết job nào gửi | App request IDs, workload identity, resource audit |
| **Information disclosure** | Credential vào URL/log/telemetry hoặc arbitrary HTTPS upload | Redaction at source, DLP, destination policy |
| **Denial of service** | DLP fail-closed không có capacity/timeout, làm ngưng API | Risk-based failure modes, scaling, circuit breaker |
| **Elevation of privilege** | Lộ long-lived high-scope key rồi bị dùng cho admin actions | Least privilege, workload identity, short lifetime, revoke |

### 14.3. Attack tree theo phòng vệ

~~~mermaid
flowchart TD
  A["Secret có thể rời khỏi trust boundary"] --> B{"Luồng phát sinh"}
  B --> C["Ứng dụng/SDK vô ý\nđưa vào request/log"]
  B --> D["Workload có quyền bị lạm dụng"]
  B --> E["Route/proxy bypass\nđích không được duyệt"]
  B --> F["Third-party storage/CI\nresource policy sai"]
  C --> C1["Schema allowlist,\nredact before telemetry"]
  D --> D1["Least privilege identity,\nsecret access audit"]
  E --> E1["Network egress deny,\nTLS peer/destination validation"]
  F --> F1["Resource IAM,\nartifact scanning, retention"]
  C1 --> G["DLP + correlate + incident response"]
  D1 --> G
  E1 --> G
  F1 --> G
~~~

Đây là sơ đồ **phòng vệ**, không hướng dẫn cách lấy/truyền credentials. Phân tích phải có **conditions and controls**; không tự suy một host mới hoặc một request thành công đồng nghĩa credential thực đã lộ.

### 14.4. Ma trận rủi ro

| ID | Nguy cơ | Điều kiện | Tác động | Kiểm soát |
| --- | --- | --- | --- | --- |
| SEC-01 | Token trong URL | Query/path được log | Credential exposure | No-secret-URL, structured logging |
| SEC-02 | Authorization header vào APM | Middleware capture raw headers | Vendor/log exposure | Redact at source |
| SEC-03 | Cross-origin redirect leak | Client forwards credentials không kiểm soát | Wrong recipient | Redirect origin policy |
| SEC-04 | Plain HTTP ngoài ý định | TLS bị bỏ/peer không xác minh | Interception/MITM | TLS/hostname validation, HSTS theo web use case |
| SEC-05 | HTTPS tới unapproved domain | Egress open | Encrypted exfil path | Default-deny and recipient approval |
| SEC-06 | DNS nhúng dữ liệu | Resolver egress unrestricted | Sensitive DNS content | Managed DNS and anomaly detection |
| SEC-07 | DoH/QUIC bypass | Proxy chỉ bắt một protocol | Blind spot | Protocol-aware egress controls |
| SEC-08 | Egress gateway bypass | Direct Node NAT/peering route | Policy/DLP không áp | Cloud/CNI deny direct |
| SEC-09 | CI env dump | Untrusted step/verbose logging | Credential vào logs | CI permissions, masking and scanning |
| SEC-10 | Container image chứa key | Dockerfile copy/build arg | Secret persisted in artifact | Build pipeline scanning, secret mounts |
| SEC-11 | Cloud IAM quá rộng | Token bị lộ có admin rights | Mở rộng blast radius | Least privilege, short life |
| SEC-12 | K8s Secret RBAC rộng | Pods/users list/get Secrets | Credential exposure | RBAC/encryption/admission |
| SEC-13 | Node metadata credential leak | Pod có host/metadata access | Cloud privilege misuse | Workload identity, metadata restrictions |
| SEC-14 | Wrong storage bucket/tenant | Network host allowed, resource not verified | Data export sai đích | Resource IAM/tenant validation |
| SEC-15 | Analytics vendor SDK gửi payload | Third-party defaults | PII/secret leak | SDK governance, field allowlist |
| SEC-16 | DLP chỉ detect sau upload | CASB scan asynchronous | Exposure trước chặn | Pre-export controls + remediation |
| SEC-17 | False positive block | Pattern broad/entropy-only | Outage/business impact | Contextual detector, staged policy |
| SEC-18 | False negative hidden payload | Encrypted/binary/unsupported parser | Blind spot | Source-level check, visibility metrics |
| SEC-19 | DLP fingerprint store lộ | Weak hashes/overbroad access | Reveal known secrets | HMAC, key management, access policy |
| SEC-20 | Log retention quá dài | Raw token lưu/index/backups | Long-tail exposure | Redact at source, retention/revoke |
| SEC-21 | Pod IP tái sử dụng | SIEM current snapshot attribution | Chặn nhầm workload | Pod UID, IPAM event time |
| SEC-22 | DR path khác security | Failover qua route không được kiểm soát | Bypass controls | Policy parity, DR game day |
| SEC-23 | Unapproved connector/webhook | Integration tự cấu hình | Secret sang SaaS ngoài scope | Connector allowlist, payload schema |
| SEC-24 | Private VPC peer “được tin” mặc định | Không có app/data classification | Private exfil | Transit firewall, IAM, DLP at source |

### 14.5. Đánh giá theo khả năng sử dụng secret

Không nên xếp mức severity theo **secret type** một cách tuyệt đối. Ví dụ:

- **Read-only short-lived test token** với audience hẹp có tác động thấp hơn admin production token, nhưng vẫn phải thu hồi nếu sai đích.
- **Refresh token** hoặc long-lived cloud key có thể tạo rủi ro kéo dài dù bytes ít.
- **Private key** dùng ký dữ liệu hoặc giải mã có thể đòi rotation chứng chỉ và đánh giá payloads đã ký.
- **Credentials đã hết hạn** có thể ít nguy cơ sử dụng tiếp, nhưng sự tồn tại của bản sao trong log cho thấy **pipeline redaction failure** cần sửa.
- **Shared key** được nhiều apps dùng có blast radius lớn và rotation phức tạp, nên cần phân tách secret ownership.

Khi incident, kết hợp **quyền, lifetime, scope, destination, evidence thực tế và khả năng thu hồi**.

## 15. Incident response khi nghi secret đã đi qua network

### 15.1. Phân loại phát hiện

| Tình trạng | Ví dụ | Mức bằng chứng |
| --- | --- | --- |
| **Exposure possibility** | Egress TCP/443 tới host lạ từ Pod có quyền secret | Network anomaly, chưa thấy payload |
| **Policy/control gap** | App có raw Authorization header logger nhưng chưa thấy log output | Lỗ hổng cấu hình cần sửa |
| **Detected secret in inspected payload** | DLP match credential fingerprint tại boundary | Có evidence secret trong nội dung được scan |
| **Confirmed disclosure** | Credential xuất hiện ở external log/object store/recipient trái phép | Dữ liệu đã rời phạm vi theo bằng chứng |
| **Confirmed misuse** | API/IAM audit ghi credential bị dùng trái quyền | Có evidence sử dụng credential, cần đánh giá actions |
| **Insufficient visibility** | Gateway logs mất, collector down, TLS path không inspect | Chưa xác định; không kết luận an toàn |

Không chờ chứng cứ **misuse** mới thu hồi khi đã có **confirmed disclosure** một live credential quan trọng. Ngược lại, không tuyên bố breach chỉ từ một IP egress lạ nếu chưa có bằng chứng dữ liệu, dù vẫn có thể cần containment theo rủi ro.

### 15.2. Quy trình ứng cứu

~~~mermaid
flowchart TD
  A["Alert: possible secret egress"] --> B["Triage: classify evidence,\nowner, scope, data class"]
  B --> C{"Live credential\nor sensitive data exposed?"}
  C -- "Có / credible high risk" --> D["Contain route/source\nand revoke/rotate secret"]
  C -- "Chưa rõ" --> E["Preserve evidence\nand investigate without raw sharing"]
  D --> F["Audit usage and external recipient\nscope/retention"]
  E --> F
  F --> G["Fix root cause: code/redaction,\nnetwork/DLP/IAM policy"]
  G --> H["Verify positive + negative tests,\nrestore controlled service"]
  H --> I["Postmortem, expiry, detection improvements"]
~~~

### 15.3. Bước 1 — Triage và khoanh phạm vi

Xác minh:

1. **Secret class**: token, password, refresh token, key material, signed URL hay dữ liệu khác?
2. **Owner và authority**: hệ thống cấp phát, rights, environment, resources/scope.
3. **Destination**: hostname, account/tenant/bucket/topic, trust domain; có duyệt không?
4. **Path**: app, APM, CI, browser, webhook, DNS, cloud egress, proxy, private peer.
5. **Exposure window**: từ khi nào đến khi nào; credential còn sống không?
6. **Evidence quality**: raw secret chỉ ở secure forensic store hay SIEM cũng đã chứa bản sao?
7. **Availability/impact**: revocation có làm ngưng service hay mất khôi phục không?

Với secrets có quyền rất cao hoặc private key không thể “bỏ qua”, kích hoạt incident owner và kế hoạch rotation nhanh ngay cả khi investigation tiếp tục.

### 15.4. Bước 2 — Containment chính xác

Có thể thực hiện theo IR/change authority:

- **Chặn kết nối** tới destination không được duyệt tại app egress, CNI/firewall/gateway.
- Thu hồi/disable **connector/webhook/CI job** đang gửi payload nhạy cảm.
- Tắt **verbose/debug request logging** nhưng giữ audit metadata cần thiết.
- Cô lập workload bị compromise hoặc thu hẹp IAM role.
- Chặn upload tới wrong bucket/tenant bằng resource policy.
- Giới hạn các egress exception và direct NAT/VPC routes.
- Thêm payload schema redaction ở nguồn, không chỉ DLP rule tại proxy.

**Không tắt toàn bộ DNS, cluster networking hoặc secrets manager** khi chỉ có một integration sai—containment phải cân bằng ảnh hưởng dịch vụ và rủi ro.

### 15.5. Bước 3 — Revoke/rotate không làm sai thứ tự

Các hệ thống khác nhau có khả năng rotate/revoke khác nhau. Runbook:

~~~text
Incident: prod API credential exposed

Identify:
  credential owner and issuing authority
  current scope/audience/expiry
  all authorized consumers

Contain:
  stop unauthorized export path
  restrict identity/resource permissions if needed

Rotate:
  provision replacement with least privilege
  update legitimate consumers via secret manager
  verify authorized functionality
  revoke/disable leaked credential

Verify:
  old credential no longer authenticates where expected
  audit past use and alert on attempted reuse
  check logs/artifacts/third-party copies
~~~

Khi rủi ro cao, **revoke ngay** có thể cần ưu tiên hơn rollout trơn tru. Nếu key được dùng cho nhiều services, rotation có thể cần **emergency overlap/dual-key period** theo provider, nhưng phải được kiểm soát và giám sát. Không lưu credential cũ trong tài liệu hậu kiểm.

Với **private key signing/certificates**, cần xem certificate chain, key pairs, trust stores, signed artifacts và quy trình thu hồi/tái phát. Với **database password**, kiểm tra sessions/privileges, audit và credential caching.

### 15.6. Bước 4 — Đánh giá sử dụng trái quyền và dữ liệu đã rời đi

Không chỉ xem token đã được gửi hay chưa; xem:

- API/IAM/DB activity của principal trong **exposure window**.
- Remote IP, request ID, user agent và tenant, nhưng nhớ **NAT/shared IP không phải identity đủ**.
- Có resource reads/writes, privilege changes hoặc data export không.
- Nếu secret được gửi tới vendor, xác định **điểm lưu/retention/replication/access logs** của vendor trong phạm vi hợp đồng và pháp lý.
- Dữ liệu có được mã hóa end-to-end? Có ai có quyền giải mã?
- Có compliance/breach notification obligations hay không? Tra cứu bộ phận pháp chế/chính sách tổ chức.

**Không được phóng đại “đã bị khai thác”** nếu chỉ có evidence exposure. Nhưng cũng không coi việc server trả 4xx là bằng chứng payload chưa tới bất kỳ proxy/log nào—có thể đã được ghi ở gateway trước khi ứng dụng từ chối.

### 15.7. Bước 5 — Xử lý bản sao trong logs/artifacts

Nếu raw secret đã được gửi tới:

- **SIEM/APM:** giảm quyền xem, xóa theo chính sách/vendor API và xác minh các bản sao/backups khi có thể.
- **CI artifact/image registry:** vô hiệu hóa link, remove/quarantine artifacts theo quy trình; rebuild không chứa secret.
- **Object store:** khóa/quarantine, xóa theo retention/immutability constraints, kiểm tra versioning/replication.
- **Chat/ticket/email:** thu hồi access, giới hạn forwarding, xử lý notification và bản sao.
- **Third-party SaaS:** liên hệ owner/vendor security để biết lưu ở đâu, retention và deletion.

Nếu không thể xóa đầy đủ, **credential revocation/rotation càng quan trọng**. Cần ghi rõ điều đã xác minh và điều chưa thể xác minh.

### 15.8. Bước 6 — Root cause và regression

| Root cause | Khắc phục lâu dài |
| --- | --- |
| Token trong URL | Thay API client/auth pattern, sanitize URL logs |
| Request body/headers vào APM | Allowlist fields và redact trước export |
| Forward credentials khi redirect | Origin-bound client policy, integration tests |
| Egress allow-all | NetworkPolicy/SWG/cloud firewall allowlist, negative tests |
| Proxy bypass | Chặn direct NAT/peering path, route governance |
| Third-party SDK gửi quá nhiều | Vendor SDK config, schema allowlist, egress policy |
| CI logs chứa credentials | Job permissions, masking, artifacts scan, federation |
| Wrong SaaS tenant/bucket | Resource IAM, destination registry, tenant validation |
| Static long-lived credential | Workload identity/short-lived token + rotation |
| False-positive DLP nhiều | Context-aware tuning, controlled exception expiry |
| Không có logs ở bypass path | CNI/cloud/app telemetry và collector health |

Sau fix, test:

1. Approved API vẫn nhận đúng token/audience qua TLS, hoạt động bình thường.
2. Unapproved destination bị chặn network-level.
3. Secret không còn xuất hiện trong logs/trace/artifact.
4. DLP alert không chứa raw credential.
5. Direct IP, DNS alternate, private VPC, IPv6, redirect không bypass.
6. Old credential đã bị vô hiệu hóa theo provider behavior.
7. Monitoring/reporting có coverage đủ và ghi nhận exceptions.

### 15.9. Báo cáo incident tối thiểu

~~~text
Incident ID: IR-SECRET-EGRESS-EXAMPLE
Severity: preliminary (reviewed by incident commander)
Credential class: API token, not included in report
Owner: application + IAM
Destination: approved/unapproved/unknown
Evidence:
  DLP fingerprint ref / audit event IDs / flow IDs
  no raw credential in shared report
Exposure window: start/end or unknown
Containment: completed/in progress
Revocation/rotation: completed/in progress/not applicable
Suspected misuse: evidence-based / unknown
Root cause: code/config/egress policy/vendor logging
Affected data/resources: confirmed/possible/unknown
Remediation owner, validation and exception expiry
~~~

**Báo cáo phải có uncertainty** khi chưa có payload, recipient or credential-use evidence. Một incident được đóng khi **đường rò đã được sửa, credential an toàn và negative tests chứng minh controls hoạt động**, không phải chỉ khi alert không còn xuất hiện.

## 16. Tình huống vận hành và cách xử lý

### Tình huống A — API key xuất hiện trong URL của HTTP client

Một service đưa key vào query string khi gọi endpoint của vendor. Requests đều dùng HTTPS và thành công. Đội vận hành thấy query string trong APM trace/searchable access logs.

**Phân tích:** đây là **exposure qua telemetry**, dù TLS không bị phá. Đầu tiên loại bỏ query-secret design, chuyển sang phương thức auth được API hỗ trợ, redact traces/logs **trước export**, xác định những nơi log đã được gửi và **rotate key** theo mức rủi ro. Không báo “không có vấn đề vì HTTPS”.

### Tình huống B — Redirect đến host khác với header Authorization

Một integration có redirect hợp lệ tới CDN để download file, nhưng HTTP client tùy biến copy mọi headers cho request mới. CDN không được duyệt nhận bearer token của API chính.

**Phân tích:** kiểm tra **origin-bound credential forwarding**. Bỏ auth header ở destination khác origin nếu không có hợp đồng rõ; verify TLS peer mỗi hop; review access logs ở đích. Test với placeholder token trong sandbox, không gửi key thật để tái hiện.

### Tình huống C — Telemetry exporter có quyền egress riêng

Ứng dụng được default-deny egress và chỉ cho phép API-A. Nhưng APM sidecar được mở Internet và có cấu hình thu full HTTP headers; token trong app requests đến API-A xuất hiện trong vendor telemetry.

**Phân tích:** ứng dụng vẫn gọi đúng recipient nghiệp vụ nhưng **telemetry là đường dữ liệu khác**. Đặt redaction ngay tại producer/sidecar, hạn chế export schema, cấp egress riêng cho collector và kiểm tra dữ liệu đã lưu ở vendor. Không đủ sửa NetworkPolicy của app.

### Tình huống D — DLP báo một hash checksum giống token

Một pipeline upload artifact chứa SHA-256 checksum, detector entropy báo “high-confidence credential” khiến deploy bị block.

**Phân tích:** checksum không phải credential chỉ vì giống chuỗi ngẫu nhiên. Điều chỉnh **context/format/field classification**; phê duyệt detector version bằng synthetic test, không tạo allow-all đối với toàn pipeline. Duy trì strict rules cho private keys/known valid credentials.

### Tình huống E — Network egress deny nhưng storage bucket sai account

App chỉ kết nối tới một object storage domain được phép, song SDK cấu hình sai bucket thuộc tài khoản không nằm trong hợp đồng dữ liệu. Firewall và TLS đều PASS.

**Phân tích:** **đích thật là resource/tenant**, không chỉ host. Cần resource-level IAM/endpoint policy, destination registry và kiểm tra bucket owner/account. Nếu đã upload secret/file nhạy cảm, xử lý **confirmed disclosure** theo quyền/retention và revoke/rotate những keys liên quan.

### Tình huống F — DoH khiến DNS security dashboard im lặng

Một dependency sử dụng DNS over HTTPS tới resolver không nằm trong danh sách. CoreDNS logs không thấy tên miền vendor mới, nhưng VPC flow cho outbound HTTPS.

**Phân tích:** DNS visibility chỉ bao phủ **resolvers được quản lý**. Kiểm kê SDK, egress routes và DoH policy; áp DNS governance phù hợp ở app/cloud firewall/SWG. Không kết luận có secret trong DoH chỉ từ TLS flow; nếu cần, đánh giá DNS metadata tại endpoint được phép.

### Tình huống G — Secret được đưa vào CI artifact

CI build task tạo diagnostic bundle gồm config/environment và upload artifacts cho người review. Scan phát hiện một credential còn hiệu lực.

**Phân tích:** ngăn publish artifact mới, restrict/quarantine existing artifact, **revoke/rotate** credential, rà quyền và lịch sử download, sửa bundle generator/runner permissions. Quét repo không đủ vì secret xuất hiện **runtime trong CI output**.

### Tình huống H — Pod Kubernetes có thể lấy node credential

Một workload thông thường có đường tới node metadata hoặc IAM identity rộng. Nó còn có network route tới public Internet.

**Phân tích:** hai lỗi kết hợp tăng blast radius: **identity overprivilege** và **egress unrestricted**. Cần workload identity scoped, metadata controls theo provider, Pod Security, egress deny và cloud API audit. Không dùng một NetworkPolicy đơn lẻ làm bằng chứng mọi host/metadata paths bị chặn.

### Tình huống I — DLP proxy outage, SDK tự dùng direct Internet

Proxy hết capacity, HTTP client tự đổi sang direct route; service vẫn gửi dữ liệu nhưng DLP logs giảm.

**Phân tích:** đây có thể là **fail-open bypass** do fallback trái policy. Chặn direct NAT/egress bằng CNI/cloud firewall; thiết kế queue/timeouts và fail-safe cho high-risk exports. Kiểm tra liệu request có thực sự chứa secret trước khi kết luận disclosure, nhưng có thể cần containment tức thời.

### Tình huống J — Private peering bị coi là “nội bộ an toàn”

Production cluster nối VPC của đối tác qua peering. Developers cho rằng vì IP private nên có thể gửi debug archives chứa access tokens đến service đối tác.

**Phân tích:** trust boundary là **organization/account/data contract**, không phải RFC1918. Giới hạn route/prefix và outbound service permissions; redact bundles; áp mTLS/IAM và data classification. Nếu token đã tới đối tác, xem contract/retention và rotate.

### Tình huống K — Không có secret trong gateway logs nhưng app vẫn xuất

Egress gateway DLP báo không có alert. Nhưng application logs cho thấy một worker upload full configuration to a private endpoint qua hostNetwork route, không qua gateway.

**Phân tích:** DLP **không bao phủ alternate path**. Cần xác nhận Pod network mode, routing, cloud VPC flow, resource owner và nội dung đã chuyển. Đóng direct route, hạn chế hostNetwork, giữ app-level classification kiểm tra trước export.

### Tình huống L — HTTPS inspection phát hiện token nhưng tạo vấn đề riêng tư

Security triển khai TLS inspection rộng; proxy log full payload để forensic. DLP tìm được vài credentials nhưng chính proxy trở thành nơi chứa khối lượng lớn secret/PII.

**Phân tích:** inspection có **trust boundary và privacy risk** riêng. Điều chỉnh data minimization/redaction, quyền truy cập, retention và điểm inspection được phê duyệt. Không lưu raw credentials chỉ để chứng minh detector đã match; dùng fingerprint references.

### Tình huống M — Vendor telemetry ở tenant sai

Một APM SDK gửi traces đến hostname đúng của nhà cung cấp nhưng API key cấu hình nhầm tenant thuộc công ty con/đối tác. DLP tại firewall theo domain vẫn allow.

**Phân tích:** **tenant identity** là một phần recipient approval. Quản lý SDK project/tenant config và token scopes, theo dõi storage destination ở app audit, kiểm tra vendor access/retention. Domain allowlist không đủ.

### Tình huống N — Cùng token dùng cả production và staging

Staging có egress rộng phục vụ thử nghiệm. Một lỗi debug logger gửi production token được copy sang staging vào external logs.

**Phân tích:** thiết kế **environment separation** đã sai từ đầu. Cấp credentials riêng theo environment, audience/scope và quyền; xoay prod token, tách secret stores/CI access, chặn staging từ đọc prod. Egress staging rộng không nên tạo đường tới dữ liệu production.

### Tình huống O — Signed URL bị paste vào chat

Một link tải dữ liệu có chữ ký và TTL còn hiệu lực được gửi vào channel chat chung để “debug”. Link là quyền truy cập tạm thời dù không phải access key chính.

**Phân tích:** coi **presigned URL như capability credential**. Hạn chế thời gian, phạm vi object/method, quyền chia sẻ, log redaction và quy trình revoke nếu provider hỗ trợ; với object nhạy cảm có thể cần thay object location/policy hoặc hết hạn link, tùy cơ chế.

### Tình huống P — Network log có nhiều bytes, DLP không thấy nội dung

Pod gửi 800 MB qua TLS tới một endpoint mới. VPC flow cho thấy bytes nhưng không có app/DLP payload logs. Team tuyên bố dữ liệu khách hàng đã bị lấy.

**Phân tích:** đó là **anomaly có thể nghiêm trọng**, nhưng nội dung chưa được xác nhận. Đối chiếu workload business job, destination/tenant, object/resource audit và data classification. Nếu egress trái quyền, containment có thể phù hợp; báo cáo nêu **possible export** chứ không gọi confirmed data theft khi chưa có evidence.

### Tình huống Q — Egress policy IPv4 đúng nhưng IPv6 mở

Workload dual-stack có thể kết nối đến đích qua IPv6 mặc dù IPv4 firewall rule chặn host tương ứng.

**Phân tích:** policy phải review **IPv4/IPv6 routes, DNS A/AAAA, CNI ipBlocks và firewall**. Chạy negative tests trên cả hai families; không copy CIDR IPv4 sang IPv6 một cách máy móc.

### Tình huống R — SaaS integration cần token hợp lệ nên DLP gây lỗi

Một rule DLP chặn mọi Authorization header trong mọi HTTPS request, kể cả khi API-A yêu cầu token đúng audience. Business requests đều fail.

**Phân tích:** DLP **không được chặn auth flow hợp lệ một cách không phân biệt**. Thiết kế **recipient-aware policy**: token chỉ đến API-A đúng endpoint, không được gửi vào telemetry/unapproved destinations; redaction ở logs luôn áp. Dùng high-confidence exact-match/destination controls, không cho phép mọi token.

### Tình huống S — DLP alert chứa chính secret

Detector tìm thấy credential thật và gửi alert gồm toàn bộ token vào SIEM/chatbot. Alert giúp phát hiện nhưng làm thêm bản sao secret ở nhiều hệ thống.

**Phân tích:** đây là **secondary exposure do security telemetry**. Ngăn raw secret trong alert, dùng secret class/fingerprint reference, giảm quyền xem, rotate token, sửa pipeline và xác minh các bản sao đã được xử lý.

### Tình huống T — DR failover làm egress bypass

Primary region dùng central proxy/DLP. Khi DR failover, secondary subnet có Internet NAT trực tiếp, proxy không nằm trong đường. Ứng dụng vẫn hoạt động và có thể upload sang SaaS.

**Phân tích:** **security policy parity** phải là tiêu chí DR, không chỉ SLO/route availability. Kiểm tra alternate paths, logging, DLP on source, allowlists/recipient validation và rollback; không ký duyệt DR chỉ vì HTTP 200.

## 17. Checklist phòng chống lộ secret qua network

### 17.1. Secret ownership và giảm bề mặt

- [ ] Mỗi credential có **owner, issuer, purpose, environment, audience, scope, lifetime và rotation plan**.
- [ ] Không lưu production secrets trong source code, CI logs, container images hoặc staging.
- [ ] Dùng workload identity/short-lived tokens hoặc secret manager khi phù hợp.
- [ ] Least-privilege IAM/RBAC và không cấp quyền đọc all secrets cho application.
- [ ] Secrets không được dùng như user IDs, request IDs, metrics labels hoặc URL query parameters.
- [ ] Nếu có presigned URLs, xem chúng là capability tokens, hạn chế TTL/scope/logging.
- [ ] Có revoke/rotation runbook và audit usage.

### 17.2. Data-flow và recipient governance

- [ ] Mọi integration xuất dữ liệu có **approved host/service/account/tenant/bucket/topic/recipient**.
- [ ] Phân loại **credential type, user data, business data và diagnostic metadata** được phép gửi.
- [ ] Truyền token đúng audience và resource endpoint có TLS certificate validation.
- [ ] Redirect cross-origin không forward credentials ngoài policy.
- [ ] Vendor SDK/webhook/email/chat/CI/artifact uploads có schema/owner/retention rõ.
- [ ] Internal/private VPC peers/on-prem được review như **trust boundaries**, không coi mọi private IP đều được tin.
- [ ] Resource IAM/ACL chặn wrong bucket/project/tenant dù network allow.

### 17.3. Egress network và DNS

- [ ] Default-deny egress ở high-risk workloads, allow theo dependency tối thiểu.
- [ ] NetworkPolicy được CNI **thực sự enforce** và có negative tests.
- [ ] DNS resolvers được quản lý, DoH/DoT/UDP/QUIC được xét theo protocol scope.
- [ ] Proxy/SWG/DLP có thể quan sát path và có route/firewall ngăn direct bypass.
- [ ] Cloud SG/NACL/firewall/peering/VPN/private endpoints kiểm tra cả IPv4/IPv6.
- [ ] hostNetwork, secondary interfaces và node metadata paths có controls riêng.
- [ ] TLS/mTLS peer verification không bị tắt để khắc phục lỗi.
- [ ] DR/failover không mở network egress rộng hơn primary ngoài quyết định có kiểm soát.

### 17.4. Redaction, logging và DLP

- [ ] Application logs dùng **allowlist fields**; Authorization/Cookie/secret body/query bị redact **trước export**.
- [ ] APM/OTel spans, metrics labels, crash reports, proxy logs và CI logs không lưu raw credentials.
- [ ] DLP có detector theo **exact known secret/fingerprint/pattern/context**, không chỉ entropy.
- [ ] Fingerprint/HMAC keys và DLP matched content được giới hạn quyền truy cập.
- [ ] TLS inspection chỉ ở điểm được ủy quyền và có privacy/legal review.
- [ ] Unsupported encrypted/binary paths và non-HTTP flows được báo cáo như coverage gaps.
- [ ] False positives/negatives có measurement, owner, tuning và exception expiry.
- [ ] DLP alerts **không chép raw secret** vào SIEM/chat.
- [ ] Có synthetic canary marker tests chứng minh masking và block, không dùng key thật.

### 17.5. Điều tra, IR và chứng cứ

- [ ] CNI/VPC/DNS/proxy/app/secret-manager/cloud audit đủ để correlate sự kiện theo **event time và workload identity**.
- [ ] Pod IP/NAT translation được map theo thời điểm, không dùng snapshot hiện tại để quy nguồn cũ.
- [ ] Có collector heartbeat và ghi rõ telemetry blind spots.
- [ ] Severity phân biệt **possible egress, confirmed disclosure, confirmed credential misuse**.
- [ ] IR plan gồm containment, revoke/rotate, resource audit, vendor retention và security validation.
- [ ] Có emergency rollback không tắt TLS verification, DLP toàn hệ thống hoặc mở egress allow-all.
- [ ] Hậu kiểm có root cause, owner, negative tests và thời hạn remediation.

### 17.6. Bảng nghiệm thu

| Hạng mục | Evidence bắt buộc | PASS khi |
| --- | --- | --- |
| Inventory | Secret metadata không chứa value, owners và recipient registry | Secret nào được ai dùng/cho đích nào rõ |
| TLS trust | Certificate validation tests, approved host/redirect policy | Không gửi secret sang peer sai |
| Payload control | Schema redaction tests, synthetic markers | Forbidden fields không rời app/collector |
| Egress isolation | CNI/cloud/SWG effective configs + negative tests | Unapproved destination không reachable |
| Resource access | IAM/bucket/topic/tenant policy tests | Wrong tenant/resource denied |
| DLP | Positive/negative synthetic corpus, precision metrics | Known credential classes detected/blocked đúng nơi |
| Logs | Proxy/CNI/DNS/app/CI telemetry, no raw secrets | Evidence đủ và không tự gây thêm rò rỉ |
| Coverage | HostNetwork/IPv6/private path/failover tests | Không có blind spot chưa được chấp nhận |
| IR readiness | Rotation, revoke, vendor deletion/retention runbook | Có thể xử lý exposure đúng hạn |
| Lifecycle | Change approvals và exception expiry | Không có allow-all/temporary exception vô chủ |

**Không nghiệm thu bằng một lần HTTPS thành công hoặc một DLP dashboard báo 0 alerts.** Phải chứng minh secret **không đi vào payload không cần thiết**, đích sai bị chặn và những luồng mà DLP không thấy được vẫn có controls tương ứng.

## 18. Bài tập thiết kế và câu hỏi ôn tập

### 18.1. Bài tập thiết kế: bảo vệ một hệ thống microservices nhiều vùng

Giả sử một doanh nghiệp có:

~~~text
Production Kubernetes cluster:
  Orders API -> payment provider (HTTPS)
  Reporting -> approved analytics tenant (HTTPS)
  Audit/logs -> observability SaaS
  Batch exporter -> cloud object storage
  Internal service -> on-prem ERP via private VPN

Secrets:
  Orders has short-lived payment API token
  Reporting has read-only warehouse credential
  CI runner has deployment token
  Workloads use workload identities to read secret manager

Network:
  Primary egress through SWG/DLP
  Node NAT still exists as an alternate route
  DR cluster has different VPC CIDR/egress path
  DNS resolvers and cloud private endpoints

Risk:
  Third-party SDKs emit telemetry
  Some workers run with hostNetwork for legacy reasons
  APM previously captured full HTTP headers
~~~

**Yêu cầu:**

1. Vẽ **data-flow diagram**: secret issuer/manager, mỗi workload, mọi egress network hop và intended recipient.
2. Phân loại **secret nào phải được sử dụng để xác thực với đích nào**, và secret nào tuyệt đối không được đưa vào dữ liệu business export.
3. Lập **destination registry** với hostname, tenant, resource ID, data class, protocol/port, owner và TTL của exception.
4. Thiết kế **Kubernetes NetworkPolicy + cloud firewall** chặn node NAT bypass và unapproved destinations.
5. Nêu phương án xử lý **DNS/DoH, IPv6, VPC peering, private endpoint và hostNetwork**.
6. Giải thích vì sao **HTTPS không thay resource-level authorization** của object storage.
7. Thiết kế **application schema/redaction** để APM chỉ nhận request ID, route template và status, không nhận token.
8. Xây **DLP detection policy** cho known credentials, suspicious unknown values và false-positive tuning.
9. Đưa ra **positive/negative synthetic tests** cho token đúng audience tới payment API và marker sai mục đích tới analytics/log sink.
10. Viết **CI/CD guardrails** cho PR từ nhánh không đáng tin, artifact scanning và ephemeral credentials.
11. Thiết kế telemetry correlation **Pod UID/IPAM/NAT/CNI/app/DLP** không lưu raw secret.
12. Mô tả **fail-closed/fallback** khi SWG/DLP mất khả dụng mà vẫn đảm bảo SLO cần thiết.
13. Lập kế hoạch **DR game day** để test policy parity trên backup routes.
14. Viết playbook **revoke/rotate** token sau confirmed exposure, gồm audit sử dụng và xử lý vendor logs.
15. Đề xuất **ownership metrics** và phương án review exceptions định kỳ.

**Tiêu chí đạt:** đúng đích network thôi chưa đủ; payload và quyền nhận phải được kiểm soát. Một luồng đến host được duyệt nhưng sai tenant hoặc chứa prod private key vẫn bị ngăn. Phải phân biệt network deny, DLP content block, TLS identity failure và application authorization.

### 18.2. Câu hỏi tự kiểm tra

**Câu 1.** Secret khác một random request ID thế nào?

*Gợi ý:* Secret có khả năng cấp quyền, ký, giải mã hoặc xác thực; random ID không tự là credential.

**Câu 2.** Vì sao một API key vài byte có thể nguy hiểm hơn một file vài GB?

*Gợi ý:* Rủi ro phụ thuộc authority/scope/lifetime và khả năng bị lạm dụng, không chỉ dung lượng.

**Câu 3.** Secret gửi qua HTTPS tới host sai có còn là rò rỉ không?

*Gợi ý:* Có thể. TLS mã hóa đường truyền nhưng không xét recipient có được phép biết secret.

**Câu 4.** Trường hợp nào Authorization header chứa bearer token là hợp lệ?

*Gợi ý:* Gửi đúng token/audience/scope đến verified resource server theo giao thức auth.

**Câu 5.** Vì sao token không nên nằm trong URL query?

*Gợi ý:* URL dễ đi vào access logs, traces, caches, history, redirects và các hệ thống khác.

**Câu 6.** POST body có an toàn tuyệt đối hơn GET query không?

*Gợi ý:* Không. Body vẫn có thể bị log/thu ở proxy, APM hoặc gửi sai đích.

**Câu 7.** Redirect cross-origin nguy hiểm khi nào?

*Gợi ý:* Khi HTTP client forward token/cookie ngoài intended recipient/trust domain.

**Câu 8.** HTTPS có tự ngăn API gửi password vào telemetry vendor không?

*Gợi ý:* Không. Cần schema whitelist/redaction và destination/data authorization.

**Câu 9.** Vì sao DNS queries cũng cần governance?

*Gợi ý:* Domain names có thể tiết lộ thông tin hoặc mang marker nhạy cảm; DoH/DoT tạo visibility khác.

**Câu 10.** Chặn UDP/53 có kiểm soát toàn bộ DNS egress không?

*Gợi ý:* Không. TCP/53, DoH/DoT, resolver proxy và đường khác cần xem theo thiết kế.

**Câu 11.** Vì sao private VPC peer không tự là trusted recipient?

*Gợi ý:* Trust phụ thuộc owner/account, IAM, data contract và resource identity, không chỉ IP private.

**Câu 12.** Egress NetworkPolicy có đọc được raw Authorization header không?

*Gợi ý:* NetworkPolicy chuẩn L3/L4 không làm content-aware DLP.

**Câu 13.** Kubernetes Secret base64 có phải encryption bảo vệ credential không?

*Gợi ý:* Không. Base64 là encoding; cần encryption at rest, RBAC và runtime controls.

**Câu 14.** Tại sao secret manager không đủ để tránh network exfiltration?

*Gợi ý:* App được cấp secret có thể dùng/gửi sai sau khi đọc; cần egress/data policy.

**Câu 15.** Workload identity giảm rủi ro gì so với static shared key?

*Gợi ý:* Có thể giảm phạm vi/copies và dùng short-lived audience-bound permissions.

**Câu 16.** TLS interception proxy có nhìn được tất cả encrypted traffic không?

*Gợi ý:* Không. Phụ thuộc protocol, TLS modes, pinning, mTLS, ECH, routing và quyền inspection.

**Câu 17.** Nếu payload bị mã hóa trước khi upload, network DLP có thể biết private key nằm trong đó không?

*Gợi ý:* Không mặc định; cần kiểm soát/classification trước mã hóa hoặc tại storage boundary.

**Câu 18.** Vì sao DLP entropy-only dễ false positive?

*Gợi ý:* Hashes, checksums, random identifiers và ciphertext có thể giống token.

**Câu 19.** Exact-match fingerprint và pattern detection khác nhau thế nào?

*Gợi ý:* Fingerprint match known value; pattern nhận diện định dạng, có thể bỏ sót/nhầm.

**Câu 20.** Vì sao không ghi raw credential vào DLP alert?

*Gợi ý:* Alert/CI/SIEM là một egress/storage path mới, làm tăng exposure.

**Câu 21.** Redaction ở UI dashboard có đủ nếu raw request đã ở data lake không?

*Gợi ý:* Không. Cần redact trước export/storage và xử lý copies đã có.

**Câu 22.** Một egress proxy không thấy traffic nhưng cloud NAT logs có bytes: kết luận gì?

*Gợi ý:* Có thể direct path bypass hoặc collector outage; chưa khẳng định secret trong payload.

**Câu 23.** Tại sao phải xác minh bucket/tenant khi host storage đã được allow?

*Gợi ý:* Một host có thể phục vụ nhiều accounts/resources; resource-level IAM quyết định quyền nhận.

**Câu 24.** Pod hostNetwork có nhất thiết chịu cùng NetworkPolicy enforcement như Pod thường?

*Gợi ý:* Không. Cần CNI/host firewall và Pod Security behavior theo sản phẩm.

**Câu 25.** IPv4 deny policy có mặc định chặn IPv6 không?

*Gợi ý:* Không; phải xét IPv6 routes, DNS AAAA, ipBlocks và firewall.

**Câu 26.** Một VPC flow TCP/443 allow có chứng minh data exfiltration không?

*Gợi ý:* Không. Chỉ là metadata; cần authorized payload/app/resource audit.

**Câu 27.** Secret manager audit read rồi một HTTPS flow tới host lạ có đủ kết luận breach chưa?

*Gợi ý:* Có tín hiệu đáng điều tra/containment tùy risk, chưa biết secret đã nằm trong payload.

**Câu 28.** Tại sao phải join Pod IP với Pod UID theo event time?

*Gợi ý:* IP có thể tái sử dụng; snapshot hiện tại có thể quy sai nguồn.

**Câu 29.** Khi phát hiện live token trong external log, có nên chờ evidence token bị sử dụng mới rotate?

*Gợi ý:* Không với credential có nguy cơ; confirmed disclosure đủ để kích hoạt revoke/rotation tùy playbook.

**Câu 30.** Rotation token có xóa bản sao trong vendor logs không?

*Gợi ý:* Không. Nó vô hiệu hóa quyền cũ; phải xử lý retention/access/delete riêng.

**Câu 31.** Vì sao một rule chặn mọi Authorization header sẽ gây lỗi?

*Gợi ý:* Nó cấm luôn auth flows hợp lệ; cần recipient-aware policy và redaction đối với logs.

**Câu 32.** Khi DLP không parse được binary payload, có nên báo rằng đã scan hoàn toàn?

*Gợi ý:* Không. Ghi coverage gap và áp source/storage data validation.

**Câu 33.** Nếu DR có direct NAT bypass SWG, điều gì cần bổ sung?

*Gợi ý:* Security policy parity, network deny alternate routes và DR negative tests.

**Câu 34.** API token chỉ đọc có cần bảo vệ không?

*Gợi ý:* Có. Nó có thể mở dữ liệu nhạy cảm, dù impact thấp hơn admin token.

**Câu 35.** Một hệ thống có 0 alerts DLP có an toàn tuyệt đối không?

*Gợi ý:* Không. Phải biết tỷ lệ traffic được scan, false negatives và blind spots.

**Câu 36.** Khi phát hiện secret trong CI artifact, cần làm gì ngoài xóa artifact?

*Gợi ý:* Revoke/rotate, audit access, sửa producer/CI permissions và xử lý copies.

**Câu 37.** Có nên gửi một secret thật tới training sink để test detection không?

*Gợi ý:* Không. Dùng synthetic marker không có giá trị xác thực.

**Câu 38.** Khi default-deny chặn DNS, cách sửa đúng là gì?

*Gợi ý:* Cho phép đúng resolver/protocol/path theo CNI, không mở all Internet.

**Câu 39.** Application authorization khác network egress allow thế nào?

*Gợi ý:* Egress allow trả lời có route tới đích; application/data authorization quyết định principal được gửi hoặc truy cập loại dữ liệu nào.

**Câu 40.** Điều kiện tối thiểu để đóng finding lộ secret?

*Gợi ý:* Đường rò được sửa, credential được revoke/rotate khi cần, logs/copies được xử lý theo policy, negative tests và telemetry chứng minh controls đã phục hồi, impact đã được đánh giá.

### 18.3. Bài tập phân tích nhật ký giả lập

~~~text
09:00:00Z Secret-manager: app-a reads secretRef=provider-a-key
09:01:00Z App audit: app-a prepares request to provider-a
09:01:01Z Proxy: TLS peer provider-a.example.test, response 200
09:02:00Z APM: synthetic marker found in unredacted debug field
09:02:02Z DLP: outbound to telemetry vendor, marker matched, BLOCK
09:03:00Z Cloud flow: app-b through NAT to unknown IP TCP/443, 42 KB
09:03:05Z Egress gateway: no matching request
09:03:07Z Gateway log-exporter: healthy
09:04:00Z CI scanner: synthetic credential marker in build artifact
09:05:00Z Resource audit: no unapproved object writes observed
~~~

**Yêu cầu:**

1. Event nào chứng minh **secret manager được đọc**, event nào chứng minh **network flow**, event nào có **payload-level marker match**?
2. Có thể kết luận app-b đã gửi production token tới unknown IP không? Vì sao?
3. DLP **BLOCK** lúc 09:02:02 chứng minh gì, và còn cần xem secret đã vào collector trước đó hay chưa?
4. Nếu marker ở 09:02 là credential production thật, thứ tự containment/rotation/audit nào phù hợp?
5. Tại sao proxy không có event lúc 09:03 là tín hiệu điều tra nhưng chưa đủ chứng minh gateway bypass?
6. CI artifact marker lúc 09:04 có cần gửi ra Internet để kiểm thử không?
7. Tại sao “no unapproved object writes” không chứng minh không có API call/data disclosure nào khác?
8. Đề xuất hai positive tests và ba negative tests để xác nhận fixes.

**Đáp án định hướng:** 09:00 là secret-access audit, không tự chứng minh nội dung sau đó bị tiết lộ. 09:02 có bằng chứng **marker trong debug/APM pipeline** và DLP đã block một outbound path cụ thể; cần xác minh có bản sao trước điểm block hay không. 09:03 là **network anomaly** chưa biết payload; kiểm tra NAT/proxy/app logs. 09:04 cho thấy scanner tìm marker **trước khi publish**, không cần upload thử. Không có object write vào một resource không chứng minh không có **HTTPS response/body upload hoặc một destination khác**.

## 19. Tổng kết

- **Bảo vệ secret khỏi gửi qua network bắt đầu trước khi packet được tạo**: giảm cấp phát secret, xác định mục đích sử dụng, chỉ gửi đúng phần cần thiết tới recipient được phê duyệt và redact dữ liệu trước log/export.
- **HTTPS/TLS/mTLS bảo vệ đường truyền và xác minh peer theo thiết kế, nhưng không tự ngăn ứng dụng gửi credential đến sai destination/tenant**. TLS thành công không đồng nghĩa data transfer được phép.
- **URL query/path, headers/cookies, request body, redirects, DNS, tracing/APM, webhooks, CI artifacts, storage và message queues** đều có thể là đường dữ liệu khiến secret rời khỏi trust boundary.
- **Workload identity, least-privilege IAM, short-lived/audience-bound credentials, secret manager và KMS** giảm số lượng/quyền của secrets cần di chuyển; **base64 hoặc Kubernetes Secret encryption at rest không thay runtime controls**.
- **Redaction ở nguồn** và structured telemetry allowlist mạnh hơn việc chỉ mask trên dashboard; không cho raw tokens, private keys hoặc customer payloads đi vào SIEM/alerts.
- **DLP có nhiều phương pháp**: exact fingerprint, pattern, entropy/ngữ cảnh, data classification và behavior analytics. Không detector nào tự bao phủ mọi encrypted/binary/direct network path, và false positives cần được đo/tuning.
- **NetworkPolicy, DNS governance, cloud firewall, SWG/egress gateway, service mesh và resource-level IAM** cần kết hợp: L3/L4 policy hạn chế đích, L7/recipient checks xác thực điểm đến, payload checks bảo vệ dữ liệu.
- **Private endpoint, VPC peering và SaaS host allowlist** không tự chứng minh bucket/account/tenant được phép nhận dữ liệu. Data authorization phải gắn với **resource và purpose**.
- **Observability cần nhiều nguồn và event-time attribution**: secret manager, app audit, CNI/VPC/DNS/proxy/DLP, CI và resource audit. Một TCP/443 flow không chứng minh exfil, và không có DLP alert không chứng minh không có leak.
- Khi có **confirmed disclosure** live credential, ưu tiên **containment và revoke/rotation theo rủi ro**, sau đó kiểm tra misuse, xử lý copies/logs/vendor retention, sửa root cause và chạy lại positive/negative tests.
- **Mục tiêu cuối cùng**: workloads chỉ có credentials cần thiết, chỉ được gửi dữ liệu đúng class đến destination/tenant có quyền, những alternate network paths bị kiểm soát, và tổ chức có chứng cứ đủ để **chặn, phát hiện, thu hồi và phục hồi** khi xảy ra sai sót.
