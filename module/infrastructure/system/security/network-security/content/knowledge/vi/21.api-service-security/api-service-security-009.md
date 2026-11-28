# Bảo vệ health check và management endpoint trong API và network service security

**Health check endpoint** là điểm mà hệ thống vận hành sử dụng để xác định một tiến trình, instance hoặc dịch vụ có còn sống, sẵn sàng nhận lưu lượng hay đã khởi động xong. **Management endpoint** là bề mặt quản trị để quan sát hoặc thay đổi trạng thái hệ thống, ví dụ xem metrics, kiểm tra cấu hình, điều chỉnh log level, đọc thông tin runtime hoặc thực hiện thao tác quản lý. Hai loại endpoint thường xuất hiện trên cùng một ứng dụng, nhưng **không có cùng mức độ nhạy cảm, nhu cầu truy cập hoặc chính sách bảo vệ**.

Trong chương **API và network service security** của học phần **SECURITY_NETWORK_SECURITY**, bảo vệ các endpoint này liên quan đến firewall, phân đoạn mạng, VPN/ZTNA, TLS/mTLS, xác thực, phân quyền, giám sát IDS/IPS, bảo vệ DNS, kiến trúc cloud và phòng vệ trước quá tải. Một route được gọi là **/health** không tự an toàn vì có tên “health”; một route có tiền tố **/internal** không tự trở thành private nếu load balancer vẫn công khai nó.

Bài học tập trung vào việc **giữ health check hoạt động đáng tin cậy cho bộ điều phối**, đồng thời **không phơi bày thông tin hoặc quyền quản trị** ra những vùng không được phép. Các ví dụ dùng hostname **.example**, dải IP private và tên tài nguyên giả định. Mọi phép thử chủ động và thay đổi policy chỉ thực hiện trong lab hoặc hệ thống được cấp quyền, với phương án khôi phục phù hợp.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **liveness, readiness, startup probe, synthetic health check** và management operation.
2. Xác định caller hợp lệ của từng endpoint: kubelet, load balancer, monitoring, SRE, SOC hay API consumer.
3. Đánh giá rủi ro **lộ thông tin, lộ secret, thay đổi cấu hình, lạm dụng tài nguyên và bypass firewall**.
4. Thiết kế topology tách **public API, probe surface, metrics plane và management plane** theo nguyên tắc tối thiểu quyền.
5. Áp dụng authentication/authorization, mTLS, VPN/ZTNA, network policy và audit đúng với từng lớp.
6. Cấu hình, phân tích và kiểm thử các probe **Kubernetes** mà không gây restart loop hoặc failover liên hoàn.
7. Đánh giá việc phơi bày **Spring Boot Actuator** hoặc endpoint quản trị tương đương trên service khác.
8. Giải thích vì sao HTTP 200 đơn lẻ không chứng minh ứng dụng sẵn sàng hoặc hệ thống an toàn.
9. Thiết kế response tối thiểu, rate/timeout budgets và giám sát tránh biến health check thành nguồn gây DoS.
10. Xây ma trận **positive/negative tests**, phương án rollout, rollback và runbook xử lý sự cố.

## 2. Health endpoint và management endpoint khác nhau thế nào?

| Loại | Mục tiêu | Caller hợp lệ | Mức dữ liệu/quyền mong muốn |
|---|---|---|---|
| **Liveness** | Quyết định có cần khởi động lại container/process không | Bộ điều phối được phép, agent nội bộ | Một tín hiệu rất nhỏ, không tiết lộ dependency |
| **Readiness** | Quyết định instance có thể nhận traffic mới không | Bộ điều phối/LB phù hợp | Trạng thái sẵn sàng, ít thông tin |
| **Startup** | Cho biết ứng dụng đã hoàn thành giai đoạn khởi động chưa | Bộ điều phối | Trạng thái start, không cần debug details |
| **Load balancer health** | Chọn backend trong target pool | LB hoặc health-check service | Kết quả có phản ánh đúng khả năng phục vụ qua đường LB |
| **Synthetic transaction** | Kiểm chứng giao dịch người dùng qua các hop thật | Monitoring có danh tính/được duyệt | Kết quả nghiệp vụ được kiểm soát, có audit |
| **Metrics** | Quan sát latency, resource, error, business SLI | Monitoring scraper được cấp quyền | Metadata giới hạn, không có secret |
| **Management read-only** | Xem configuration/threads/runtime/status | SRE/operations/SOC theo role | Có thể rất nhạy cảm, cần xác thực và log |
| **Management mutation** | Đổi config, log level, cache, restart, shutdown | Admin được phê duyệt | Đặc quyền cao, yêu cầu xác thực mạnh và phê duyệt |

**Một endpoint /status do đội phát triển tự tạo có thể thực hiện bất kỳ việc gì**. Tên gọi không xác định hành vi thực tế: phải xem code, framework, plugin và route mapping.

### 2.1. Câu hỏi đầu tiên: đây là data plane hay management plane?

- **Data plane:** thực hiện request nghiệp vụ của người dùng, thường qua public API hoặc API B2B.
- **Management plane:** phục vụ người vận hành, bộ điều phối, hệ thống giám sát và công cụ cấu hình.
- **Control plane:** quyết định cấu hình/triển khai/định tuyến, có thể chứa những API thay đổi policy, traffic hoặc identity.

Một health endpoint rất nhỏ có thể được phục vụ cùng data plane để giám sát đúng listener. Nhưng **không nên mặc định phơi bày cả management plane ra Internet vì một route health cần được LB đọc**.

## 3. Các ranh giới tin cậy của endpoint vận hành

~~~mermaid
flowchart LR
    INTERNET[Public Client] --> EDGE[CDN / WAF / LB]
    EDGE -->|Routes API public| APP[Application listener]
    LB[LB Health Checker] -->|Probe tối thiểu| HEALTH[Probe listener hoặc route]
    K[Kubelet / Orchestrator] -->|Liveness/readiness/startup| HEALTH
    MON[Monitoring scraper] -->|mTLS / auth| MET[Metrics endpoint]
    SRE[SRE qua VPN/ZTNA] -->|MFA + RBAC| MGMT[Management API]
    MGMT --> OPS[Runtime / Config Operations]
    APP --> DATA[(Data + Dependencies)]
    EDGE -.Không định tuyến.-> MGMT
    MGMT -.Audit events.-> SIEM[SIEM / SOC]
    HEALTH -.Trạng thái probe.-> OBS[Metrics & alerts]
~~~

Sơ đồ là kiến trúc tham chiếu. Trong thực tế probe và app có thể ở cùng listener, nhưng **public routing rules**, caller identity và response policy phải được xác định rõ.

### 3.1. Phân tầng đường vào

| Vùng mạng | Được phép | Không nên có quyền mặc định |
|---|---|---|
| Internet public | API public và những health endpoint tối thiểu khi thực sự bắt buộc | Debug, heap dump, env, loggers, management mutation |
| Edge/LB | Gọi probe đúng backend, port và path được phê duyệt | Truy cập toàn bộ management API |
| Orchestrator/node | Probe Pod/workload theo cơ chế được quản lý | Sửa cấu hình hoặc lấy secret từ management plane |
| Monitoring network | Scrape metrics cần thiết với identity phù hợp | Gọi shutdown, loggers mutation, dump runtime |
| SRE/admin network | Management operations theo role, approval và audit | Quyền cao cấp cho mọi tài khoản/thiết bị |
| Service-to-service | Application API đã phân quyền, internal health khi cần | Tin tất cả private IP là admin |

**Private IP không đồng nghĩa an toàn tuyệt đối.** Một workload bị chiếm ở cùng VPC/namespace có thể gửi request tới một endpoint quản trị nếu phân đoạn và xác thực không đủ.

## 4. Liveness, readiness và startup probe: ba câu hỏi khác nhau

Ba loại probe không thể hoán đổi tùy tiện. Chúng điều khiển hành vi khôi phục trong hệ thống điều phối.

### 4.1. Liveness: tiến trình có đang bị kẹt không?

**Liveness probe** trả lời: *container/process có còn ở trạng thái mà restart có thể giúp phục hồi không?* Ví dụ: process deadlock, event loop kẹt hoàn toàn hoặc không thể đáp ứng request cơ bản.

Không nên đưa một dependency chung như database hoặc dịch vụ thanh toán vào **liveness** nếu outage của dependency đó không thể giải quyết bằng cách restart. Nếu tất cả Pod cùng kiểm tra DB lỗi rồi tự restart, hệ thống có thể tạo **restart storm** khiến sự cố tệ hơn.

### 4.2. Readiness: instance có nhận lưu lượng mới được không?

**Readiness probe** trả lời: *instance có đáp ứng yêu cầu để được đưa vào đường phân phối traffic mới không?* Khi readiness fail, các cơ chế như Kubernetes Service thường ngừng chọn Pod làm endpoint **cho những kết nối mới**, theo sự hội tụ của trạng thái endpoints và data plane.

Điều này không nhất thiết đóng ngay mọi kết nối đang mở; behavior phụ thuộc LB/proxy và ứng dụng. **Readiness fail không tự restart container.**

Một readiness check có thể xét:
- Ứng dụng đã khởi tạo các thành phần cần thiết.
- Listener/routing và cấu hình quan trọng đã sẵn sàng.
- Các dependency **thực sự bắt buộc để instance phục vụ lưu lượng hiện tại** có trạng thái hợp lệ, theo mô hình caching/timeout.
- Instance đang draining hoặc bảo trì nên tạm ngừng nhận request mới.

**Không đưa tất cả external services vào readiness một cách máy móc.** Một dependency không bắt buộc, hoặc đã có fallback, không nên làm rút toàn bộ replicas khỏi service.

### 4.3. Startup: ứng dụng đã hoàn thành khởi động?

**Startup probe** hữu ích với ứng dụng khởi động lâu, migrate hoặc warm-up trước khi sẵn sàng. Trong Kubernetes, khi startup probe chưa thành công, nó **ngăn liveness và readiness probes bắt đầu kiểm tra**; khi startup thành công, hai probe kia hoạt động theo cấu hình.

Startup không thay readiness về lâu dài. Cũng không nên dùng startup probe để che lấp một dependency luôn thất bại.

### 4.4. Bảng so sánh hành vi

| Probe | Câu hỏi | Nếu thất bại nhiều lần | Phụ thuộc bên ngoài? |
|---|---|---|---|
| **Liveness** | Restart có giúp ứng dụng trở lại trạng thái phục vụ? | Kubelet có thể khởi động lại container theo policy | Thường **tránh** dependency chia sẻ |
| **Readiness** | Instance có nên nhận request mới? | Pod bị đánh dấu chưa sẵn sàng và rút khỏi endpoints theo hệ thống | Chỉ những dependency thực sự cần và đánh giá cẩn thận |
| **Startup** | Đã qua giai đoạn khởi động chưa? | Có thể restart nếu vượt ngưỡng thất bại | Phụ thuộc vào thiết kế startup |
| **Synthetic health** | Giao dịch thực có hoàn tất qua đường người dùng? | Tạo cảnh báo/SLO, không tự buộc kubelet restart | Có thể kiểm tra nhiều dependency |

**Thất bại của probe cần có tác dụng phục hồi mong muốn.** Đừng cấu hình probe dựa trên việc endpoint trả 200 ở máy phát triển mà không tính sự cố production.

## 5. Vòng đời một Pod và các probe

~~~mermaid
flowchart TD
    START[Container bắt đầu] --> SP{Startup probe thành công?}
    SP -->|Chưa, trong budget| WAIT[Tiếp tục chờ và kiểm tra]
    WAIT --> SP
    SP -->|Vượt ngưỡng thất bại| RESTART[Restart container theo policy]
    SP -->|Có| LP{Liveness OK?}
    LP -->|Không, vượt failure threshold| RESTART
    LP -->|Có| RP{Readiness OK?}
    RP -->|Có| TRAFFIC[Eligible nhận traffic qua Service]
    RP -->|Không| NTRAFFIC[Không chọn cho traffic mới]
    TRAFFIC --> RP
    NTRAFFIC --> RP
~~~

Đây là mô hình khái niệm cho Kubernetes. Hành vi của API server, EndpointSlice, kube-proxy/CNI và các load balancer có độ trễ hội tụ, không phải tất cả quyết định chuyển trạng thái tức thì.

### 5.1. Tác động bảo mật

Một liveness probe có chi phí quá lớn hoặc phụ thuộc mạng bên ngoài dễ bị ảnh hưởng bởi lỗi quá tải; kẻ tấn công đã có thể gây tải API công khai đôi khi khiến probe trễ, kéo theo restart hàng loạt. Vì vậy:
- Probe phải **nhẹ, ổn định và bounded-time**.
- Không để request người dùng bình thường giữ khóa hoặc luồng xử lý làm health bị treo quá lâu.
- Không trả stack trace/DB detail khi probe fail.
- Có budget, threshold phù hợp và cách quan sát vòng restart.
- Không dùng liveness để “sửa” vấn đề dependency chung.

## 6. Thiết kế response health tối thiểu

### 6.1. Ví dụ phản hồi lành mạnh

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"status":"UP"}
~~~

Nếu không cần JSON, một status code đơn giản hoặc body rất nhỏ cũng có thể đáp ứng probe. Các hệ thống có thể dùng **200, 204** hoặc những mã thành công khác theo hợp đồng, miễn phù hợp bộ kiểm tra đang dùng.

### 6.2. Khi dịch vụ chưa sẵn sàng

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store

{"status":"NOT_READY"}
~~~

**503** ở đây là ví dụ phản hồi readiness. Một số framework dùng **OUT_OF_SERVICE**, **DOWN** hoặc status mapping riêng. Điều quan trọng là orchestrator/LB phải diễn giải mã phản hồi theo đúng cấu hình.

### 6.3. Không để response trở thành tài liệu hệ thống

Tránh công khai qua health:
- Tên server DB, database schema, private IP/subnet, internal DNS.
- Version phần mềm/vulnerability details không cần thiết.
- Stack trace, exception với credential/URL chứa token.
- Thông tin cluster membership hoặc topology chi tiết.
- Đường dẫn filesystem, environment variables hoặc runtime flags.
- Danh sách upstream/partner endpoints hoặc danh sách node.
- Chi tiết lỗi xác thực/trạng thái user trong hệ thống.

Các chi tiết đó có thể dành cho **diagnostics API đã được xác thực**, log nội bộ và dashboard giám sát với quyền tối thiểu.

### 6.4. Health check và HTTP caching

Probe thay đổi theo trạng thái runtime; cache có thể trả kết quả cũ khiến LB giữ instance lỗi hoặc rút instance đang khỏe. Với những endpoint phục vụ trạng thái tức thời, thường nên **tránh caching ngoài ý muốn** (ví dụ Cache-Control: no-store), nhưng cần xem provider health checker có tôn trọng header hay không.

**Không để một CDN công khai cache chung response health và dùng nó làm bằng chứng readiness của từng backend**; phải phân biệt kết quả của edge và từng target.

## 7. Management endpoint có thể tiết lộ gì?

Các runtime/framework cung cấp nhiều loại endpoint vận hành; tùy phiên bản và plugin, chúng có thể gồm:

| Endpoint hoặc chức năng | Giá trị vận hành | Rủi ro nếu công khai |
|---|---|---|
| Health details/dependencies | Tìm service/DB nào lỗi | Lộ cấu trúc hạ tầng và trạng thái dependency |
| Metrics/Prometheus | CPU, memory, latency, per-route counters | Lộ hostname, URL, tenant labels, topology hoặc dữ liệu nhạy cảm qua labels |
| Environment/configuration | Kiểm tra properties và flags | Có thể lộ secret hoặc cách cấu hình security |
| Heap dump | Phân tích memory leak | Có thể chứa token, password, PII và toàn bộ dữ liệu ứng dụng |
| Thread dump | Chẩn đoán deadlock | Có thể lộ path, class, URL, stack và dữ liệu điều tra nhạy cảm |
| Logger management | Xem/đổi log level | Bật debug gây lộ token/PII hoặc tạo tải lớn |
| Shutdown/restart | Quản lý vòng đời | Gây gián đoạn dịch vụ ngay nếu bị lạm dụng |
| Route mappings/beans | Gỡ lỗi ứng dụng | Lộ đường quản trị, cấu trúc framework và surface |
| Log files/audit events | Điều tra sự cố | Lộ tài khoản, endpoint, secret nếu logging sai |
| Cache management | Flush hoặc invalidation | Gây tải DB, thay đổi hành vi người dùng |
| Feature flags/config writes | Điều chỉnh runtime | Có thể bỏ auth, tắt giám sát hoặc mở route |

**Không phải sản phẩm/framework nào tự bật toàn bộ các endpoint trên.** Phải xác minh bản chạy thật, dependency/plugin và cấu hình exposure. Một endpoint có khả năng thay đổi trạng thái cần được coi là **privileged operation**, không chỉ là một HTTP route.

### 7.1. Read-only không đồng nghĩa ít rủi ro

Heap dump hoặc environment view có thể chỉ là HTTP GET, nhưng trả dữ liệu đủ để làm lộ credentials hoặc topology. **Giới hạn quyền xem cũng quan trọng như quyền ghi.**

### 7.2. Tên path không phải cơ chế an ninh

Không đạt yêu cầu nếu chỉ:
- Đổi **/actuator** thành một chuỗi khó đoán.
- Đặt **/internal** hoặc **/debug** mà vẫn public.
- Chuyển management từ port 8080 sang 9091 nhưng firewall cho cả Internet.
- Chỉ kiểm tra header **X-Internal: true** do caller tự khai báo.
- Giới hạn theo một IP nhưng reverse proxy tin mọi X-Forwarded-For.

**Security by obscurity** có thể giảm nhiễu scan, nhưng không thay identity, network isolation và audit.

## 8. Mô hình rủi ro cho health và management endpoint

Một attacker có thể là:
- Người ngoài Internet gửi request tới route public.
- Client hợp lệ cố sử dụng management endpoint ngoài quyền.
- Workload bị xâm nhập ở cùng subnet/namespace.
- Tài khoản vận hành bị lộ token hoặc mất MFA.
- Người có quyền sửa CDN/LB/Ingress mở route management ngoài ý muốn.
- Pipeline/agent CI/CD bị chiếm và thay cấu hình monitoring/probes.
- Một nguồn traffic gây tải khiến health endpoint không phản hồi đúng.

### 8.1. Các chuỗi rủi ro thường gặp

**Lộ thông tin:**

~~~text
Management route public
    -> không có authN hoặc authZ không đủ
    -> response gồm config/metrics/dump
    -> lộ danh tính dịch vụ hoặc dữ liệu nhạy cảm
~~~

**Thay đổi vận hành trái quyền:**

~~~text
Admin endpoint có quyền mutate
    -> token bị lộ / policy overly broad
    -> đổi log level hoặc trigger restart/cache flush
    -> gián đoạn và mất kiểm soát dữ liệu/log
~~~

**Phản ứng dây chuyền vì probe sai:**

~~~text
DB chung lỗi
    -> mọi Pod liveness check DB
    -> liveness fail trên mọi Pod
    -> restart storm + cache cold + DB reconnect spike
    -> outage kéo dài
~~~

### 8.2. Sự hiện diện của endpoint không tự chứng minh khai thác

Một route /actuator/health được công khai có thể chỉ trả một kết quả tối thiểu theo nhu cầu của LB. Đây không tự là **lỗ hổng nghiêm trọng** nếu mức thông tin và exposure được phê duyệt. Rủi ro cần đánh giá dựa trên **response, quyền thực tế, đường mạng và đối tượng được phép dùng**.

## 9. Nguyên tắc thiết kế: tách bề mặt công khai và quản trị

Nên phân loại các route theo mức quyền trước khi viết ingress/firewall:

| Nhóm | Ví dụ | Thiết kế mặc định |
|---|---|---|
| **Public business API** | /v1/orders, /v1/products | TLS + authentication/authorization theo hợp đồng |
| **Public minimal availability** | /health/public khi thật cần | Response cực nhỏ, limit, không debug |
| **Local orchestration probes** | /livez, /readyz, /startupz | Chỉ phục vụ đường probe của orchestration, không route public |
| **Monitoring endpoint** | /metrics, /actuator/prometheus | Monitoring network + authenticated scraper/mTLS theo khả năng |
| **Read-only diagnostics** | Thread states, config summary | SRE via VPN/ZTNA + RBAC + audit |
| **Privileged management** | Logger mutation, cache flush, shutdown | Admin role riêng, MFA/JIT, approval và audit |
| **Debug/test endpoints** | /debug, /test-only | Không expose ở production hoặc chỉ trong lab cô lập |

### 9.1. Ưu tiên tách listener/port nếu phù hợp

Một ứng dụng có thể dùng:
- **App listener:** phục vụ API tại port dành cho ingress.
- **Probe route trên app listener:** rất nhỏ, không được public route.
- **Management listener:** port riêng, chỉ trong mạng quản trị.
- **Metrics listener:** chỉ nhận scrape từ monitoring plane khi có cơ chế.

Tách port giúp viết policy rõ hơn, **nhưng không tự tạo bảo mật** nếu port phụ vẫn được công khai.

### 9.2. Kiểm tra hệ quả khi tách management port

Nếu probes chỉ kiểm tra management listener, ứng dụng có thể báo UP dù **listener phục vụ người dùng bị lỗi**. Vì vậy khi dùng cổng management riêng, cần cân nhắc đặt probe ngắn ở **cổng ứng dụng** hoặc một kiểm tra end-to-end khác để xác minh đúng đường thực.

Ngược lại, nếu ràng management listener vào **127.0.0.1**, kubelet hoặc LB từ ngoài network namespace có thể không tới được. Mọi lựa chọn binding phải xét topology, Pod IP, hostNetwork, sidecar, container boundaries và quyền truy cập từ node.

## 10. Xác thực và phân quyền cho management plane

### 10.1. Ba tầng kiểm soát

1. **Network:** chỉ VPN/ZTNA, management subnet, private endpoint, firewall/security group hoặc workload identity được phép kết nối.
2. **Authentication:** SSO/MFA cho người vận hành; mTLS/service account/token được quản lý cho machine clients.
3. **Authorization:** vai trò khác nhau cho **read metrics**, **view diagnostics**, **change configuration**, **restart/shutdown**.

**Chỉ có IP allowlist không đủ cho management API nhạy cảm.** NAT, proxy, tài khoản bị chiếm trong subnet cho phép hoặc host bị kiểm soát đều có thể vượt điều kiện IP.

### 10.2. Ma trận quyền

| Role/identity | Health tối thiểu | Metrics | Diagnostics | Thay log level | Restart/shutdown |
|---|---|---|---|---|---|
| Kubelet/probe caller | Allow theo route | Deny | Deny | Deny | Deny |
| Load balancer checker | Allow theo endpoint đã chọn | Deny | Deny | Deny | Deny |
| Monitoring scraper | Allow nếu cần | Allow read | Deny | Deny | Deny |
| SOC read-only | Allow | Theo nhu cầu | Giới hạn với approval | Deny | Deny |
| SRE operator | Allow | Allow | Allow có audit | Theo policy | Không mặc định |
| Break-glass admin | Theo policy | Theo policy | Theo policy | Khi có sự cố/phê duyệt | Chỉ quy trình khẩn cấp |
| Public anonymous client | Chỉ minimal public health nếu được phê duyệt | Deny | Deny | Deny | Deny |

**RBAC** theo vai trò có thể được bổ sung bằng **ABAC** theo environment, owner, thời gian, device posture hoặc change ticket. Một danh tính SRE production không mặc nhiên có quyền sửa toàn bộ tenant/region.

### 10.3. MFA, JIT và break-glass

- **MFA** bảo vệ quyền admin tương tác, đặc biệt khi truy cập từ xa.
- **Just-in-time (JIT)** cấp quyền có thời hạn thay vì quyền admin thường trực.
- **Privileged Access Management (PAM)** hoặc bastion có thể quản lý phiên và ghi audit.
- **Break-glass** có quy trình khẩn cấp, credential được bảo vệ và hậu kiểm bắt buộc.
- **Service identity/mTLS** cho automation, tránh dùng một shared human account.
- **Revocation/rotation** cần kiểm thử cả session/token đang hoạt động và cache của gateway.

## 11. Bảo vệ probe không yêu cầu user login như thế nào?

Một kubelet hoặc LB health checker có thể không hỗ trợ OAuth login/MFA cho mỗi probe; buộc tất cả request tới /readyz qua interactive SSO có thể khiến health luôn fail và gây outage.

Giải pháp không phải “mở toàn bộ management endpoints không auth”, mà là:

1. Cung cấp **probe endpoint rất hẹp**, không chứa cấu hình hoặc hành vi mutation.
2. Định tuyến chỉ theo **kênh health checker đã được phép**.
3. Không công bố probe routes qua public API ingress nếu không cần.
4. Không gắn dữ liệu nhạy cảm hoặc response có nhiều chi tiết.
5. Tối ưu response time và resource budget; không phụ thuộc vào IdP cho probe nội bộ.
6. Có network identity, mTLS hoặc auth machine-to-machine **nếu nền tảng hỗ trợ và phù hợp**.
7. Giữ những endpoint còn lại phía sau authN/authZ mạnh.
8. Kiểm thử caller ngoài scope không truy cập được management API.

**Kubelet HTTP probe** có những giới hạn về cách cấu hình xác thực; có thể gửi HTTP headers theo probe spec nhưng không mặc định hỗ trợ vòng đời OAuth/MFA. Một static token đặt trong manifest cũng tạo rủi ro secret/rotation và không thay thế mạng được kiểm soát.

### 11.1. Khi LB buộc cần health public

Một số mô hình LB dùng health check từ địa chỉ/identity của dịch vụ mà operator cần cho phép qua firewall. Cần:
- Xác định nguồn và cách xác minh nguồn do provider công bố.
- Route riêng phục vụ health, response tối thiểu.
- Restrict origin theo LB/edge và tránh alternate public IP.
- Giới hạn tốc độ và theo dõi abuse phù hợp, không chặn nhầm checker.
- Không expose metrics/config/admin chỉ vì checker cần GET /health.

## 12. Kubernetes: cấu hình liveness, readiness và startup

Đoạn dưới đây là **ví dụ YAML cho Pod container** trong một Deployment được quản lý. Ứng dụng phải thực sự cài các route **/livez, /readyz và /startupz** trả HTTP status phù hợp; Kubernetes không tự tạo ba route này cho mọi ứng dụng.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: registry.example/orders-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /startupz
              port: http
            periodSeconds: 5
            failureThreshold: 24
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
            timeoutSeconds: 2
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 3
            successThreshold: 1
            timeoutSeconds: 2
~~~

Đây là **mẫu học thuật**, không phải ngưỡng tối ưu cho mọi ứng dụng. Kubelet HTTP probe gửi request tới Pod IP/port theo cơ chế nền tảng; application phải sẵn sàng lắng nghe trên địa chỉ phù hợp.

### 12.1. Cách hiểu thời gian

Với ví dụ:
- Startup probe có **periodSeconds: 5**, **failureThreshold: 24**. Có thể cho ứng dụng một ngân sách xấp xỉ 120 giây cho startup trong điều kiện probe liên tục thất bại, nhưng **thời gian chính xác phụ thuộc scheduler, thời gian thực thi probe và trạng thái container**.
- Liveness fail nhiều lần có thể dẫn tới restart; không nên để lệ thuộc database chung.
- Readiness fail không restart container, mà khiến Pod không được xem sẵn sàng nhận traffic Service.
- **timeoutSeconds: 2** cần được kiểm tra với latency thực và runtime pauses.

Không chọn threshold chỉ bằng phép tính lý thuyết: phải xem **cold start, GC pauses, CPU throttling, network jitter, deployment rollout và tài nguyên node**.

### 12.2. Phân biệt HTTP success và lỗi

Kubernetes HTTP probe nhìn HTTP status trả về; thường **200–399** được coi thành công cho HTTP probe. Vì vậy nếu endpoint health redirect **302** sang login, probe có thể bị đánh giá khác với ý định vận hành hoặc tạo cảnh báo liên quan redirect. Không dùng redirect tới SSO để bảo vệ một probe nội bộ; phải thiết kế đúng route/network.

Các hành vi chi tiết như redirect handling và header mặc định phụ thuộc phiên bản/cấu hình, cần kiểm thử ở cluster thật.

### 12.3. Node-originated traffic và NetworkPolicy

**Kubernetes NetworkPolicy không nên được hiểu là công cụ mặc định chặn mọi request từ node/kubelet tới Pod.** Traffic từ node lưu trú Pod có thể được đối xử đặc biệt/theo semantics của nền tảng và CNI. Do đó:
- Không chỉ dựa vào một policy “deny all pods” để kết luận management port không reachable từ mọi nguồn node.
- Xác minh tính năng CNI, hostNetwork, node traffic và đường đi của probe.
- Bảo vệ node access và Kubernetes RBAC, audit những người có thể sửa Pod spec/Service/Ingress.
- Dùng service mesh, sidecar, network identity và app-level auth khi cần.

**NetworkPolicy không thực thi được nếu CNI không hỗ trợ đúng khả năng cần dùng**; kiểm tra với dữ liệu thực tế trên cluster.

## 13. Spring Boot Actuator: endpoint nào nên expose?

**Spring Boot Actuator** cung cấp nhiều endpoint vận hành có tên phổ biến như **health, info, metrics, prometheus, env, configprops, beans, mappings, loggers, threaddump, heapdump** và những chức năng khác tùy dependency/version. **Không phải tất cả đều được bật hoặc công khai theo mặc định.** Mức exposure và cơ chế security phụ thuộc phiên bản, Spring Security và cấu hình ứng dụng.

### 13.1. Ví dụ cấu hình chỉ expose health qua HTTP

~~~yaml
# application.yml minh họa cho Spring Boot tương thích
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
~~~

Ý tưởng:
- Chỉ exposure **health** qua Actuator web endpoints.
- Không đưa chi tiết dependency ra caller thông thường.
- Bật các nhóm probe health khi phiên bản hỗ trợ.
- Khi property **add-additional-paths** được hỗ trợ và bật, có thể expose **/livez và /readyz trên cổng ứng dụng**; phải kiểm tra cấu hình thực tế.

**Các đường dẫn cụ thể, hành vi probe tự động và supported properties phụ thuộc Spring Boot version.** Một số bản tự nhận diện Kubernetes và bật probe groups; không sao chép cấu hình mà bỏ qua kiểm chứng version.

### 13.2. Cổng management riêng

Một cách tách bề mặt vận hành:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
~~~

Cổng 9091 **không tự private**. Cần bảo vệ **Pod/host/network listener, Service, Ingress, security group và firewall**. Nếu ứng dụng cần probe trên **cổng 8080**, hãy sử dụng route đã được hỗ trợ hoặc triển khai handler nhỏ đúng nhiệm vụ.

Nếu chọn **management.server.address: 127.0.0.1** trên management port khác, chỉ có tiến trình trong network namespace phù hợp mới tới được; **kubelet HTTP probe từ node không mặc nhiên truy cập localhost bên trong Pod**. Phải xác minh đường probe thực trước khi triển khai.

### 13.3. Không expose mọi endpoint để tiện debug

Cấu hình kiểu **exposure.include: "*"** có thể làm tăng bề mặt nguy hiểm khi có actuator endpoints tương ứng, đặc biệt nếu network/authN/authZ không được thiết kế. Ngay cả khi một endpoint chỉ **read-only**, dữ liệu env, configprops, heap dump hoặc mappings có thể nhạy cảm.

Chỉ bật endpoint cần thiết, phân quyền theo operation và kiểm chứng **method**: một số management actions có thể dùng POST hoặc những phương thức khác. Không coi việc một URL trả 404 trong một phép thử là bằng chứng toàn bộ surface đã được khóa.

### 13.4. SecurityFilterChain và thứ tự policy

Với Spring Security, có thể dùng **filter chain riêng cho Actuator** và filter chain cho business API. Cần xác định rõ:
- Matcher nào thực sự bao phủ Actuator endpoints.
- Thứ tự các filter chains (không để generic permissive chain áp trước).
- Cho phép **health minimal** theo network scope nếu cần.
- Yêu cầu role/scope cụ thể cho metrics/diagnostics/mutation.
- Mô hình xác thực token/mTLS và authorization.
- CSRF/session policy nếu management UI dùng cookie.
- Audit và việc tách quyền của admin.

Một khung **pseudopolicy**, không phải Spring Security Java code compile trực tiếp:

~~~yaml
# Chính sách logic để review, KHÔNG phải cấu hình Spring Security
route_policies:
  - path: /livez
    methods: [GET]
    caller: kubelet-orchestrator-network
    auth: narrow-probe-policy
    response: minimal
  - path: /readyz
    methods: [GET]
    caller: kubelet-orchestrator-network
    auth: narrow-probe-policy
    response: minimal
  - path: /actuator/prometheus
    methods: [GET]
    caller: authenticated-metrics-scraper
    required_role: metrics.read
  - path: /actuator/loggers/**
    caller: privileged-operators-only
    required_role: diagnostics.manage
    audit: mandatory
  - path: /actuator/**
    default: deny
~~~

**Không dùng chỉ X-User-Role/X-Internal do client cung cấp** để xác định caller trong policy như trên. Identity phải đến từ TLS peer đã xác thực, token đúng audience/scope hoặc kênh mạng được kiểm soát và được ứng dụng xác minh.

## 14. Prometheus và metrics endpoint

Metrics endpoint chứa những dữ liệu hữu ích về CPU, memory, HTTP latency, error, garbage collector, connections hoặc business counters. Nếu công khai, nó có thể tiết lộ:
- Tên service, instance, namespace hoặc availability zone.
- Danh sách API routes và dependency labels.
- Mức tải, thời gian deploy và pattern lưu lượng.
- Tenant/user/account IDs nếu developer tạo nhãn thiếu kiểm soát.
- Hostname, IP, queue names hoặc thông tin nhạy cảm khác trong custom metrics.
- High-cardinality labels khiến hệ thống giám sát tốn bộ nhớ.

### 14.1. Kênh scrape đáng tin

Một kiến trúc tốt:
- Scraper được xác thực/ủy quyền như một **service principal**.
- Endpoint **metrics** chỉ được định tuyến qua monitoring network hoặc service-to-service identity.
- TLS/mTLS theo mức bảo vệ dữ liệu và trust boundary.
- RBAC của Kubernetes/service discovery giới hạn ai có thể đọc Pod/Service metadata.
- Không công khai port metrics qua NodePort/Ingress ngoài ý muốn.
- Có giới hạn response size, thời gian scrape và số lượng series.

**Scraper có quyền đọc metrics không cần quyền sửa log level hoặc shutdown.**

### 14.2. Phân biệt endpoint được scrape và đường truy cập API

Một Prometheus Pod có thể tới **/metrics** thông qua ClusterIP hoặc Pod IP, trong khi public Ingress chỉ định tuyến **/v1/**. Nhưng điều này chỉ đúng nếu ingress/network policy/service config chặn được mọi đường khác; một NodePort cũ hoặc public LB có thể bypass thiết kế.

### 14.3. Không đặt secret trong metric label

Không dùng token, email, đầy đủ URL chứa query secrets, user identifiers hoặc request bodies làm metric labels. Ngoài rò rỉ, nhãn có cardinality rất lớn còn có thể làm **metrics storage và CPU quá tải**.

Ưu tiên **route templates** thay vì raw path chứa object IDs, cùng nhãn service/operation/response class được kiểm soát.

## 15. Bảo vệ debug, heap dump và runtime diagnostics

Các hoạt động điều tra sự cố có thể cần heap dump, thread dump, log level debug hoặc trace sampling. Chúng thuộc **diagnostic operations nhạy cảm**, dù chỉ được gọi bằng HTTP GET.

### 15.1. Vì sao heap dump nguy hiểm?

Heap có thể chứa:
- Access tokens, session objects và API keys trong memory.
- Cấu trúc request/response, PII hoặc dữ liệu thanh toán.
- Internal URLs, database clients và cấu hình runtime.
- Thông tin người dùng hoặc secret chưa được xóa khỏi object.

Bảo vệ gồm **restricted access, encryption at rest/in transit, short retention, audit download**, giới hạn nơi lưu và bảo đảm file sau xử lý được xóa theo policy.

### 15.2. Thay đổi log level cũng có rủi ro

Bật DEBUG/TRACE có thể:
- Ghi thêm Authorization headers hoặc credential nếu logging library sai.
- Tăng I/O, memory, log ingest cost.
- Làm log nhạy cảm tồn tại lâu trong SIEM/observability.
- Gây quá tải khi traffic cao.

Vì vậy thao tác đổi log level cần **role riêng, thời hạn tự khôi phục (nếu nền tảng hỗ trợ), approval và audit**, cùng quy trình rollback.

### 15.3. Không dùng management API cho thao tác nguy hiểm khi không cần

Một lệnh shutdown hoặc config mutation qua public HTTP làm tăng attack surface đáng kể. Nếu cơ sở hạ tầng đã có orchestrator có quyền thực thi restart/rollout, cân nhắc **không expose chức năng tương đương trong ứng dụng**.

## 16. Chống DoS đối với health check và management plane

Probe tưởng như đơn giản nhưng có thể bị lạm dụng thành cơ chế gây tải.

### 16.1. Health endpoint không nên làm tác vụ đắt tiền

Tránh:
- Query DB lớn ở mỗi GET /health.
- Gọi hàng chục downstream APIs đồng bộ mỗi vài giây.
- Đọc toàn bộ bảng hoặc tính báo cáo để xác định READY.
- Tải lại config, refresh cache lớn, tạo temp file.
- Gọi dịch vụ bên ngoài không timeout.
- Tự động ghi dữ liệu/khởi động migration mỗi lần được probe.

Thay vào đó:
- Dùng **local state** hoặc phép kiểm tra hằng số/nhẹ nếu hợp mô hình.
- Dependency checks cần thiết phải có timeout và isolation budget.
- Cache trạng thái kiểm tra dependency trong khoảng phù hợp nếu cần, nhưng hiểu rủi ro stale result.
- Dùng readiness để biểu diễn năng lực phục vụ thật, không lạm dụng liveness.
- Đo CPU/latency riêng của probe để phát hiện regression.

### 16.2. Một ví dụ ước lượng tải

Giả định 100 Pod, mỗi Pod được probe bởi 2 hệ thống, mỗi hệ thống gọi **mỗi 5 giây**:

\[
R \approx \frac{100 \times 2}{5} = 40 \text{ request/giây}
\]

Nếu mỗi health request lại mở một kết nối DB hoặc gọi API ngoài, số lượng công việc có thể lớn hơn nhiều, đặc biệt trong deploy/restart storm. Đây là phép tính minh họa, chưa tính retry, độ lệch thời gian, nhiều probes hoặc LB checks từ nhiều vùng.

### 16.3. Giới hạn để không phá health checker

Rate limiting trên probe cần thận trọng:
- Nhận biết caller hợp lệ và tần suất probes.
- Không áp chung quota anonymous public API cho traffic từ kubelet/LB nếu khiến checker nhận 429.
- Có network scope và limit dựa trên behavior không làm probe dồn hàng đợi.
- Tránh các policy WAF/CAPTCHA/browser challenges trên endpoint dành cho machine health.
- Giữ response nhỏ và hạn chế concurrent expensive checks.
- Giám sát **429/403/5xx từ chính probe** để phát hiện policy sai.

**Đừng dùng CAPTCHA, SSO redirect hoặc quota chặt của API public trên /readyz**: điều này có thể tự gây outage.

## 17. Dependency checks: chọn gì cho liveness và readiness?

Một service phục vụ Orders API có thể phụ thuộc:
- Local HTTP handler và runtime.
- Database orders.
- Token validation/JWKS cache/IdP.
- Cache Redis.
- Message broker để phát event.
- External payment API.
- Internal DNS.
- Cloud secret/config store.

### 17.1. Mỗi dependency có mức quan trọng khác nhau

| Dependency | Liveness | Readiness | Synthetic/business check |
|---|---|---|---|
| Local process/event loop | Có thể phù hợp | Có thể phù hợp | Gián tiếp |
| App initialization đã hoàn thành | Thường không ở liveness sau startup | Có | Có |
| Orders DB bắt buộc cho request chính | Thường không | Có thể, nếu hết DB thì không thể serve | Có, kiểm tra giao dịch an toàn |
| Redis cache có fallback | Thường không | Có thể không | Theo mục tiêu SLO |
| Async email/notification | Không | Thường không nếu không cản request chính | Đo ở workflow riêng |
| External payment gateway | Không | Cân nhắc, thường không nếu mất làm toàn Pod rút khỏi pool | Có, trong synthetic non-destructive |
| IdP tạm unavailable nhưng có cached keys hợp lệ | Không | Phụ thuộc logic auth và policy | Kiểm tra token validation thực |
| DNS resolver/network | Không trực tiếp | Chỉ khi ảnh hưởng thực sự tới phục vụ | Test end-to-end qua đường cần thiết |

### 17.2. Tránh thác đổ vì readiness toàn cụm

Nếu cùng một DB bị lỗi, tất cả 50 Pods fail readiness, Service không còn ready endpoints. Việc này **có thể là phản ánh đúng trạng thái không phục vụ**, nhưng cần hiểu hệ quả với cache, recovery và clients. Không nên dùng một external API không bắt buộc khiến toàn hệ thống ngừng nhận traffic, thay vì fallback/error handling có kiểm soát.

Thiết kế đúng là một **quyết định nghiệp vụ và availability**, không phải quy tắc “tất cả dependencies vào readiness”.

### 17.3. Synthetic check nên tác động thấp

Synthetic transaction đo end-to-end qua DNS, TLS, proxy, auth và ứng dụng, nhưng cần:
- **Test account/tenant riêng** có phạm vi và hạn mức rõ.
- Tránh tạo đơn hàng/thu tiền thật hoặc tác vụ không idempotent.
- Không dùng mật khẩu/token trong logs hoặc URL.
- Có rollback/cleanup cho dữ liệu giả, nếu tạo trong lab.
- Giới hạn tần suất và timeout.
- Theo dõi từ nhiều vị trí/zone phù hợp.

## 18. Origin bypass, HTTP headers và danh tính probe

Một vấn đề phổ biến: đội vận hành chặn **/actuator/** ở public gateway, nhưng một origin Pod/VM/LB vẫn có public IP và người ngoài có thể kết nối trực tiếp tới port management.

### 18.1. Kiểm soát end-to-end

1. **Inventory** mọi listener, port, Service, Ingress, NodePort, LoadBalancer, security group và VPN route.
2. Tách management port khỏi public listener khi phù hợp.
3. Chỉ cho **trusted management/monitoring/orchestrator paths** tới port tương ứng.
4. Có **application-level auth** với endpoint nhạy cảm, không chỉ firewall.
5. Kiểm tra **IPv4 và IPv6**, cả những địa chỉ public bổ sung.
6. Tránh alternate hostnames hoặc legacy routes không có owner.
7. Giám sát change drift khi Helm chart, IaC, CNI, LB hoặc cloud policy thay đổi.
8. Test từ một caller **ngoài danh sách cho phép** trong môi trường được duyệt.

### 18.2. Không tin header khai báo nguồn nội bộ

Những header như:
- X-Forwarded-For
- X-Real-IP
- X-Internal
- X-Management-Request
- X-User-Role

không tự là bằng chứng identity. Client HTTP có thể tự gửi chúng. Cần **trusted proxy chain**, strip/rebuild identity headers ở biên và xác thực kênh giữa proxy với backend.

### 18.3. IP allowlist có thể cần nhưng chưa đủ

IP allowlist hữu ích cho source ranges của LB/monitoring, nhưng:
- CIDR của cloud provider có thể thay đổi.
- VPN/NAT làm nhiều client chia sẻ IP.
- Host trong subnet được phép có thể bị xâm nhập.
- Một request đi qua nhiều proxies có thể gây nhầm source IP.
- Cloud security group rule có thể áp sai NIC/port.

Nên bổ sung mTLS/service identity hoặc token scope cho management có dữ liệu/quyền nhạy cảm.

## 19. Kubernetes Service, Ingress và NetworkPolicy

### 19.1. Đặt tên các port rõ ràng

Một Pod có thể có:
- **http:** cổng ứng dụng.
- **metrics:** cổng xuất số liệu monitoring.
- **management:** cổng riêng cho admin API.

Nhưng đặt tên port không tạo chính sách bảo mật. **Service type, Ingress/Gateway routes, LB listeners và NetworkPolicy** quyết định đường thực tế.

### 19.2. Đề xuất cấu trúc mạng

~~~mermaid
flowchart LR
    USER[Public Client] --> ING[Public Ingress]
    ING -->|Chỉ app port| APP[API Pod]
    SCRAPE[Prometheus / Monitoring] -->|metrics port đã cấp quyền| APP
    OPS[VPN/ZTNA SRE] -->|management port + auth| APP
    K[Node kubelet] -->|HTTP probe theo cấu hình| APP
    NET[Cloud SG / CNI / NetworkPolicy] -.Giới hạn các đường.-> APP
    ING -.Không route management.-> APP
~~~

Kubernetes NetworkPolicy là một lớp có điều kiện thực thi theo CNI và hướng traffic. **Không thay thế app authentication**, không tự chặn mọi traffic từ node/host network và không bảo đảm một Service không bị expose qua cấu hình cloud ngoài cluster.

### 19.3. Một policy logic tối thiểu

~~~yaml
# Pseudopolicy để review, không phải Kubernetes NetworkPolicy schema hoàn chỉnh
workload: orders-api
allowed_ingress:
  - caller: public-api-gateway
    ports: [8080]
    routes: [/v1/*]
  - caller: monitoring-scraper
    ports: [9090]
    auth: service-identity
  - caller: approved-sre
    ports: [9091]
    auth: mTLS-plus-role
  - caller: kubelet-probe
    ports: [8080]
    routes: [/livez, /readyz]
default:
  unknown-port: deny
  unauthorized-route: deny
audit:
  management-writes: required
~~~

Một NetworkPolicy chuẩn chủ yếu quyết định theo **Pod/namespace selectors, IP blocks, ports và giao thức**; nó **không tự lọc HTTP path hoặc OAuth roles**. Các yếu tố routes/roles ở trên phải được thực thi bởi gateway, service mesh hoặc application. Vì vậy ví dụ chỉ là **policy yêu cầu**, không phải YAML có thể áp dụng trực tiếp.

### 19.4. Cloud managed load balancer

Khi dùng cloud LB hoặc serverless/container service:
- Kiểm tra **health check port/path/protocol** riêng.
- Xác định nguồn probe của provider và identity được hỗ trợ.
- Chỉ expose routes dự định; tránh public management listener.
- Theo dõi **cross-zone/region** health và routing.
- Đảm bảo TLS ở upstream, không tắt certificate verification để “health up”.
- Dùng resource policies/private endpoints/IAM theo capability dịch vụ.
- Kiểm tra failover không tự mở thêm quản trị trên backup region.

## 20. Monitoring plane có cần TLS/mTLS không?

Một số nền tảng scrape metrics qua HTTP trong một subnet/cluster đã được kiểm soát; một số tổ chức yêu cầu TLS/mTLS cho mọi chặng quan trọng. Lựa chọn phụ thuộc **trust boundary và chính sách dữ liệu**, nhưng không nên kết luận “nội bộ nên plaintext luôn an toàn”.

### 20.1. Các mục tiêu bảo vệ

- **Confidentiality:** metrics có thể lộ topology/labels nhạy cảm.
- **Integrity:** metrics giả có thể đánh lừa cảnh báo hoặc capacity decisions.
- **Peer authentication:** scraper đúng service identity, endpoint đúng workload.
- **Authorization:** chỉ scrape endpoint được cấp phép, không được mutate.
- **Availability:** một mTLS/certificate error không nên âm thầm làm mất giám sát.

### 20.2. Lỗi chứng chỉ làm cả fleet “mù” giám sát

Nếu certificate của monitoring scraper hết hạn hoặc service trust bundle bị thay, các targets có thể trả handshake error. Không được kết luận tất cả applications đều down nếu chỉ mất metrics: cần nguồn kiểm chứng độc lập như application SLI hoặc synthetic tests.

Ngược lại, nếu monitoring bị ngắt, cần cảnh báo **absence of telemetry** để tránh “dashboard trống nghĩa hệ thống khỏe”.

## 21. Quan sát và logs không làm lộ bí mật

### 21.1. Nên ghi những gì?

| Trường | Giá trị |
|---|---|
| Event time (UTC) và source/ingest time | Xây timeline, tìm trễ log |
| Workload/service ID, environment, region | Xác định phạm vi lỗi |
| Endpoint class (health/metrics/management) | Phân loại rủi ro |
| Normalized route + method | Không ghi raw path có secret |
| Caller identity, role hoặc verified source | Attribution có căn cứ |
| Allowed/denied decision và policy version | Biết rule nào thực thi |
| HTTP status và latency | Sự cố/probe timing |
| Probe type và failure reason category | Tránh nhầm liveness với readiness |
| Container restart count/readiness transitions | Xác định restart loop |
| AuthN/AuthZ outcome | Phát hiện truy cập quản trị trái quyền |
| Change ID, actor, before/after state | Audit mutation |
| Request/correlation ID | Liên hệ gateway/app/monitoring |
| Rate-limit/timeout metrics | Phát hiện abuse và policy sai |

### 21.2. Không nên ghi gì?

- Bearer token, API key, session cookie, private key.
- Raw environment variables chứa secret.
- Nội dung heap dump hoặc thread dump không được redacted.
- Password, MFA seed hoặc database connection URL có credential.
- PII/customer data trong health response, query hoặc metrics labels.
- Toàn bộ Authorization/X-API-Key headers.
- Raw stack trace trả về caller ngoài boundary.

**Chuyển secret từ response sang logs không phải khắc phục triệt để**; dữ liệu đó vẫn có thể bị lộ qua monitoring, ticket hoặc một người xem log có quyền quá rộng.

### 21.3. 401, 403 và 404

- **401 Unauthorized:** thiếu hoặc không đạt cơ chế authentication theo hợp đồng HTTP.
- **403 Forbidden:** caller có identity nhưng không đủ quyền theo policy, hoặc resource bị chặn.
- **404 Not Found:** route không tồn tại; đôi khi dùng để hạn chế tiết lộ về endpoint, nhưng không thay authorization.
- **503 Service Unavailable:** có thể biểu diễn readiness DOWN hoặc service không sẵn sàng; cần ngữ cảnh route.

**Ẩn một management endpoint bằng 404 không bảo vệ được nếu cùng chức năng còn ở route/port khác**. Hãy kiểm tra đường thực tế.

## 22. Chỉ số và cảnh báo riêng cho health/management

Một hệ thống cần theo dõi **sức khỏe ứng dụng** và **sức khỏe cơ chế kiểm tra**.

### 22.1. Chỉ số về health/probe

- Liveness/readiness/startup probe success rate và latency.
- Số lần restart trong khoảng thời gian.
- Thời gian từ deploy đến Ready.
- Số Pod Ready/Desired theo deployment/zone.
- Số lần chuyển trạng thái Ready↔NotReady.
- Số instance LB Healthy/Unhealthy và thời gian mất target.
- Synthetic transaction success/error theo region/network path.
- HTTP 401/403/429/5xx của probe routes (thường là dấu hiệu cấu hình).
- Probe timeouts và CPU/throttling liên quan.

### 22.2. Chỉ số management security

- Request bị deny tới /actuator, /metrics, /admin hoặc cổng quản trị từ vùng ngoài policy.
- Failed admin auth/invalid certificate và role violations.
- Management policy changes, log level change events.
- Bất thường về truy cập dump/config hoặc download dữ liệu lớn.
- Certificate expiry, mTLS handshake failure trên monitoring/management plane.
- Port/Ingress/SG policy drift và route mới không có owner.
- Telemetry loss hoặc scraping errors.
- Unauthorized privilege escalation attempts trong log được phép thu.

### 22.3. Tính tỷ lệ thành công

Ví dụ minh họa: 5.000 readiness probes trong một cửa sổ, 4.975 thành công.

\[
\text{Probe success rate} = \frac{4975}{5000}\times 100\% = 99.5\%.
\]

Tỷ lệ cao **không chứng minh toàn bộ ứng dụng khỏe**. Nếu probe quá nông, backend có thể trả 200 cho /readyz nhưng mọi request tạo đơn đều lỗi. Cần kết hợp **synthetic business transactions và user-facing SLI**.

### 22.4. Không dùng mỗi ngưỡng CPU để quyết định READY

CPU cao không luôn có nghĩa một instance không thể phục vụ, và CPU thấp không bảo đảm DB route hoạt động. Readiness nên phản ánh khả năng **nhận request mới trong ngữ cảnh kiến trúc**, không chỉ một ngưỡng hệ thống đơn lẻ.

## 23. Quy trình triển khai an toàn

### Giai đoạn 1 — Inventory và phân loại

1. Liệt kê application listeners, health/metrics/debug/admin endpoints.
2. Xác định **caller hợp lệ**, đường network, authentication, response type và owner từng route.
3. Phân loại endpoint: minimal health, monitoring, diagnostics, privileged mutation.
4. Đối soát API gateway, Ingress, Service, NodePort, cloud SG/LB và pod network.
5. Kiểm tra mã nguồn/framework exposure theo phiên bản thực tế.
6. Lập bản đồ **public path vs private management path**.

### Giai đoạn 2 — Thiết kế policy

1. Public API route không dẫn tới admin/dumps.
2. Probe dùng endpoint nhẹ và tối thiểu thông tin.
3. Metrics chỉ được scrape từ monitoring identity.
4. Diagnostics cần authN/authZ và audit.
5. Mutation cần quyền cao, MFA/JIT/approval phù hợp.
6. Bảo vệ cả IPv4/IPv6, node/cloud alternate paths.
7. Định nghĩa latency/timeout/failure thresholds.
8. Có giám sát policy drift, false positives và telemetry loss.

### Giai đoạn 3 — Pilot và negative testing

1. Triển khai staging, kiểm chứng liveness/readiness/startup theo lifecycle.
2. Test khi DB/cache/IdP chậm hoặc mất, không gây restart cascade.
3. Test public caller tới routes quản trị phải bị chặn.
4. Test metrics scraper hợp lệ và caller không hợp lệ.
5. Test route/token/mTLS/role và audit cho management operations.
6. Đo tác động của rate limits/SSO redirects lên probes.
7. Thử rollout, termination/draining và failback.
8. Chỉ triển khai production sau khi đã có rollback và owner.

### Giai đoạn 4 — Vận hành liên tục

1. Theo dõi probe results, restart storms, readiness transitions và synthetic business success.
2. Theo dõi auth failure, management changes, certificate expiry và drift.
3. Review routes không dùng, debug flags và privileges.
4. Kiểm thử sau khi đổi library/Actuator/Kubernetes/CNI/cloud LB.
5. Bảo vệ logs/metrics/dump retention và quyền truy cập.
6. Diễn tập dependency outage, node outage, gateway failover và telemetry outage.
7. Kiểm tra security parity tại region/cluster dự phòng.

## 24. Ma trận kiểm thử health check và management endpoint

| Test | Điều kiện | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| H01 | Pod khởi động bình thường | Startup pass; readiness pass sau khi phục vụ được | Kubelet events + app logs |
| H02 | App đã khởi động nhưng chưa nhận request | Readiness fail, liveness không tự fail nếu process khỏe | Probe metrics + EndpointSlice |
| H03 | Local process thực sự bị kẹt trong lab | Liveness phát hiện và restart theo threshold | Restart count, event timeline |
| H04 | DB chung tạm lỗi | Không gây restart storm do liveness | Probe + DB metrics |
| H05 | Dependency không bắt buộc bị lỗi | Readiness theo policy, không rút toàn bộ nếu còn fallback | Business SLI + readiness |
| H06 | Client public GET minimal health nếu route được duyệt | Chỉ status tối thiểu, không tiết lộ topology | HTTP response |
| H07 | Internet caller tới metrics/debug | Bị chặn nếu không thuộc exposure policy | Gateway/firewall logs |
| H08 | Monitoring scraper đúng identity | Đọc metrics theo quyền | Scrape/auth logs |
| H09 | Scraper không có cert/token hợp lệ | Từ chối | mTLS/auth logs |
| H10 | SRE read-only gọi endpoint mutation | Từ chối, có audit | 403 + audit event |
| H11 | Admin hợp lệ đổi cấu hình trong lab | Chỉ được phép theo change approval, có before/after audit | IAM + management logs |
| H12 | Caller giả X-Forwarded-For thuộc IP nội bộ | Không bypass source-based policy | Edge peer identity |
| H13 | Gọi trực tiếp origin/management port từ ngoài network scope | Không reachable hoặc bị auth deny | SG/flow + app logs |
| H14 | Các NodePorts/LoadBalancers cũ | Không còn đường công khai management ngoài ý muốn | Resource inventory |
| H15 | IPv6 tới management endpoint | Cùng policy chặn như IPv4 | IPv6 flow/firewall |
| H16 | Health trả 302 sang SSO | Không bị hiểu sai là Healthy; sửa routing theo thiết kế | Probe outcome/redirect logs |
| H17 | Monitoring/certificate trust bị lỗi | Có alert thiếu telemetry, không nhầm app toàn bộ down | Scraper/IdP/cert logs |
| H18 | Health endpoint bị request nhiều ở lab trong budget | Có resource bound, không leak/không cạn worker | Latency/CPU/error |
| H19 | Heap dump/config endpoint read-only | Chỉ admin đủ quyền có thể truy cập, dữ liệu được bảo vệ | RBAC/audit |
| H20 | Endpoints không dùng bị tắt | Trả deny/404 theo policy trên mọi port/path | App mapping + negative probes |
| H21 | Rolling deploy/draining | Pod rút khỏi new traffic trước khi shutdown phù hợp | Readiness transitions + inflight |
| H22 | Region B failover | Health, auth, monitoring, management network parity | Config diff + transactions |
| H23 | TLS ở management plane sai certificate | Machine client từ chối theo policy | TLS verification logs |
| H24 | Liveness/readiness probes trên main vs management port | Phát hiện app port lỗi dù management port vẫn up | App port/synthetic checks |
| H25 | Management operation trái quyền qua VPN | Bị chặn dù có đường mạng | AuthZ + firewall/route logs |
| H26 | Log chứa token trong tình huống debug lab | Redaction/controls phát hiện và không publish secret | Logging tests |
| H27 | Endpoint mới từ dependency upgrade | Exposure không tự mở; có config regression test | Route inventory + CI |
| H28 | Startup chậm theo budget được phê duyệt | Startup probe không restart sớm | Startup timestamps + events |
| H29 | Probe response/cache bị stale | Checker đánh giá trạng thái từ target đúng, không cache sai | Header/probe event |
| H30 | Incident làm SIEM ingest trễ | Có phân biệt event time/ingest time và alert log loss | SIEM pipeline health |

**Không đánh dấu PASSED chỉ vì YAML/probe route tồn tại.** Cần ghi environment, owner, test time, policy version, thực tế quan sát, expected behavior và evidence. Chỉ chạy các ca gây gián đoạn trong lab hoặc change window được phê duyệt.

## 25. Thực hành an toàn: chỉ kiểm tra endpoint trong lab

Không cần thử khai thác hoặc quét endpoints trên hệ thống của người khác để học chủ đề này. Bắt đầu bằng **đọc cấu hình và chạy một vài request nhỏ** tới tài sản do mình quản trị.

### 25.1. Xem HTTP status và headers của health

~~~bash
# Một request nhỏ tới endpoint lab do bạn quản trị
curl --silent --show-error --max-time 5 \
  -i https://api.lab.example/health
~~~

Quan sát HTTP status, Content-Type, Cache-Control, body và các thông tin có thể bị lộ. Không mặc định **/health** tồn tại trên mọi API; thay bằng route thực tế của lab.

### 25.2. Xem trạng thái probes trong Kubernetes đã có quyền

~~~bash
# Chỉ đọc cấu hình và status, cần Kubernetes RBAC
kubectl get pods -n lab -o wide

kubectl describe pod orders-api-0 -n lab

kubectl get endpointslices -n lab

kubectl get events -n lab --sort-by=.lastTimestamp
~~~

**orders-api-0** chỉ là tên minh họa. Tùy workload, Pod có thể được Deployment tạo với tên khác. Lệnh describe có thể chứa environment hoặc metadata nhạy cảm; không xuất kết quả ra kênh công khai nếu chứa thông tin hạ tầng.

### 25.3. Xem route ingress và Service để phát hiện exposure

~~~bash
# Xem cấu hình network objects trong namespace được phép
kubectl get ingress,services -n lab -o wide

# Nếu cluster hỗ trợ Gateway API và RBAC cho phép
kubectl get gateways,httproutes -n lab

# Xem policies đã khai báo
kubectl get networkpolicies -n lab
~~~

Không lấy kết quả **get networkpolicies** làm bằng chứng chúng được CNI thực thi đầy đủ; cần kiểm tra support và negative connectivity tests đúng scope. Các lệnh chỉ đọc cũng có thể bộc lộ private hostnames/IP, vì vậy cần giới hạn chia sẻ.

### 25.4. Spring Boot: kiểm tra minimal health nếu được phép

~~~bash
# Đường minh họa, chỉ gọi một lần và không có credentials trong URL
curl --silent --show-error --max-time 5 \
  -i https://api.lab.example/actuator/health
~~~

Một phản hồi minimal health là có chủ đích nếu policy cho phép. **Không thử hàng loạt actuator paths để đoán dữ liệu nhạy cảm** trên môi trường không thuộc quyền; thay vào đó kiểm tra chính sách exposure/route mapping từ hệ thống quản trị được cấp quyền.

### 25.5. Đọc kết quả đúng mức

Nếu response là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

Có thể nói **một request tới route này đã được phục vụ thành công tại thời điểm đó**. Chưa thể kết luận:
- Tất cả Pods đều Ready.
- Database có thể xử lý giao dịch tạo đơn hàng.
- App listener khác hoặc region khác đang khỏe.
- Management endpoints đã được chặn.
- Không có dữ liệu nhạy cảm trong metrics/logs.
- Caller không được phép đã bị từ chối.

Vì vậy phải kết hợp probe telemetry, synthetic API transaction, chính sách network và negative tests.

## 26. Chẩn đoán các sự cố thường gặp

### 26.1. API vẫn hoạt động nhưng Kubernetes restart liên tục

**Dấu hiệu:** Pod có nhiều restarts, liveness thường fail; khách hàng gặp gián đoạn.

**Phân tích:** có thể liveness probe phụ thuộc DB, timeout quá thấp, JVM GC/CPU throttling, auth redirect hoặc port/path sai. Đối chiếu probe events, latency, deployment history và resource metrics. **Không tăng failureThreshold vô hạn** để che một lỗi nghiêm trọng; sửa nguyên nhân và đo theo workload.

### 26.2. Readiness luôn fail sau khi bật Spring Security

**Dấu hiệu:** app listener trả 302 tới login hoặc 401 cho /readyz; không Pod nào Ready.

**Phân tích:** probe route bị bảo vệ bằng interactive auth, matcher Spring Security sai, proxy route nhầm port hoặc Spring Boot probe path không được bật. Thiết kế lại minimal probe path và network scope; **không tắt security cho toàn /actuator/**.

### 26.3. Health UP nhưng API nghiệp vụ lỗi

**Dấu hiệu:** /health phản hồi 200, /v1/orders trả 500.

**Phân tích:** health có thể chỉ kiểm tra process, không kiểm tra DB/route/auth hoặc user transaction. Tách readiness theo dependency quan trọng và **synthetic business checks**; không đưa toàn bộ external systems vào liveness.

### 26.4. Prometheus mất dữ liệu sau khi bật mTLS

**Dấu hiệu:** scrape failed, app user success vẫn bình thường.

**Phân tích:** cert expired, wrong trust bundle, mTLS identity hoặc NetworkPolicy/Service route sai. Kiểm tra scraper và endpoint ở cùng thời điểm, bảo vệ cert/key; không kết luận ứng dụng down chỉ vì metrics mất.

### 26.5. Một NodePort cũ phơi bày management port

**Dấu hiệu:** public Ingress chặn /actuator nhưng port ngoài do Service khác vẫn reachable.

**Phân tích:** origin bypass. Inventory toàn Service, NodePort, LB, SG, host networking và IPv6; đóng đường không được duyệt, áp auth riêng trên management và test từ caller ngoài scope.

### 26.6. WAF chặn cả health checker

**Dấu hiệu:** health bị trả 403/429/challenge; LB lần lượt loại mọi backend.

**Phân tích:** policy áp nhầm từ public API lên machine probe, có thể do new rules hoặc nguồn LB thay đổi. Tách rule/route theo danh tính health checker, response tối thiểu; không xóa toàn WAF để sửa một probe.

### 26.7. Heap dump xuất hiện trong ticket công khai

**Dấu hiệu:** người vận hành đính kèm dump để debug mà không biết nó chứa token.

**Phân tích:** sự cố dữ liệu nhạy cảm; hạn chế truy cập, xử lý theo incident runbook, đánh giá bí mật đã lộ và rotate/revoke khi cần. Sửa quy trình thu/lưu/chia sẻ diagnostics, không chỉ xóa file mà bỏ qua bản sao và hệ thống lưu trữ.

### 26.8. Failover region thành công nhưng debug mở trên backup

**Dấu hiệu:** region B trả 200 cho API, nhưng management listener dùng config cũ.

**Phân tích:** **security parity thất bại**. Dùng config/policy as code, audit drift, canary và test denied flows cho cả primary/backup. Availability đạt không được dùng để bỏ qua authN/authZ của management.

## 27. Runbook khi nghi ngờ management endpoint bị phơi bày

### Giai đoạn A — Xác minh phạm vi và bằng chứng

1. Xác định hostname, route/port, cloud account, region, cluster, owner và phiên bản.
2. Kiểm tra **điểm truy cập thật**: Ingress/LB, origin, IPv4/IPv6, private/VPN route.
3. Xác định endpoint có thực sự enable, có authN/authZ không, trả loại dữ liệu gì.
4. Tương quan access logs, WAF, firewall/flow, application audit và management events.
5. Đánh giá liệu có **secret/dump/privileged action** đã bị truy cập hay chỉ có probe minimal.
6. Lưu chứng cứ đúng quyền; không đưa token, raw dump hoặc PII vào báo cáo mở.

### Giai đoạn B — Giảm tác động

- Nếu management route không cần thiết: đóng exposure tại edge/Ingress/Service và xác minh đường thay thế không còn.
- Nếu endpoint cần cho probe: giữ **probe tối thiểu** cho đúng caller, không mở rộng mọi actuator routes.
- Nếu có dữ liệu nhạy cảm bị đọc: phối hợp incident response, kiểm tra retention/log, rotate/revoke secret theo đánh giá.
- Nếu có quyền quản trị bị lạm dụng: thu hồi session/role, điều tra thay đổi runtime và kiểm tra integrity.
- Nếu có dấu hiệu DoS: rate/limit traffic trái phép, giữ kubelet/LB probe được phép, giám sát SLO.
- Nếu rollout mới làm health fail: áp rollback về **cấu hình an toàn đã phê duyệt**, không mở management public để chữa gấp.

### Giai đoạn C — Phục hồi và xác minh

1. Xác minh public business API vẫn phục vụ đúng.
2. Kubelet/LB health check trở lại ổn định và không có restart storm.
3. Metrics/diagnostics chỉ caller có quyền mới truy cập được.
4. Test management role read vs mutate, xác minh audit.
5. Test từ Internet, VPN ngoài role, namespace khác và vùng cloud dự phòng theo scope.
6. Kiểm tra logs không chứa secret và alert về thay đổi endpoint còn hoạt động.
7. Đóng incident sau khi có bằng chứng **availability và security đều đạt**.

### Giai đoạn D — Phòng ngừa tái diễn

- Quy định review endpoint exposure trong pull request/deployment.
- Đưa negative tests của management endpoints vào pipeline phù hợp.
- Có owner/expiration cho các ngoại lệ mở debug.
- Theo dõi Service/Ingress/SG mới hoặc policy drift.
- Tài liệu hóa version-specific behavior của Actuator/Kubernetes/CNI.
- Diễn tập cert expiry, failed dependency và log loss.

## 28. Tình huống luyện tập và lời giải gợi ý

### Tình huống A — Liveness phụ thuộc database

Một API có 20 replicas. DB ngừng hoạt động 30 giây; mọi Pod thất bại liveness và đồng loạt restart.

**Gợi ý:** đây là một anti-pattern. Liveness không nên phụ thuộc DB dùng chung nếu restart không khắc phục DB outage. Chuyển các dependency checks phù hợp sang readiness hoặc synthetic monitoring theo design, test hiệu quả recovery và tránh đồng bộ restart.

### Tình huống B — Endpoint /health trả đầy đủ DB hostnames

Một public /health trả trạng thái từng DB node, phiên bản framework và hostname private.

**Gợi ý:** health response tiết lộ topology. Chỉ trả trạng thái tối thiểu cho public checker; chuyển diagnostic details sang protected route/monitoring với quyền thích hợp.

### Tình huống C — Spring Security chặn readiness

Sau triển khai, /readyz redirect đến login. Kubernetes xem Pod chưa sẵn sàng.

**Gợi ý:** route bị đưa vào interactive auth; cần kiểm tra security matcher, path/port và probe settings. Chỉ cho phép machine probe tối thiểu qua network scope, không mở tất cả Actuator.

### Tình huống D — Metrics port có IP private nhưng vẫn bị đọc trái quyền

Một Pod cùng namespace đã bị xâm nhập và gọi /metrics qua ClusterIP.

**Gợi ý:** private IP không bảo đảm caller đáng tin. Dùng identity/auth/mTLS phù hợp, network segmentation, tenant isolation, kiểm soát labels và quyền read.

### Tình huống E — Đổi log level không cần xác thực

Actuator loggers endpoint cho phép ghi cấu hình log chỉ vì server nằm sau VPN.

**Gợi ý:** VPN là lớp network, không thay admin AuthZ. Yêu cầu role riêng, audit, approval/JIT và hạn chế endpoint exposure; không bật write operations cho mọi VPN user.

### Tình huống F — Gateway chặn /actuator nhưng VM lộ port 9091

Public LB chỉ có /v1/**, nhưng VM có security group mở port 9091 từ 0.0.0.0/0.

**Gợi ý:** có origin/port bypass. Sửa SG/routing, bind listener đúng, bổ sung authN/authZ và kiểm thử đường trực tiếp. Tên port riêng không tự là private.

### Tình huống G — Readiness check gọi external payment API

Payment provider trả lỗi 2 phút; Orders API vẫn có thể hiển thị sản phẩm và trạng thái đơn, nhưng toàn bộ replicas bị rút khỏi Service.

**Gợi ý:** cần phân biệt dependency bắt buộc với chức năng có thể degrade/fallback. Không để một dịch vụ ngoài tùy chọn làm mất toàn API; dùng synthetic transaction/circuit breaker và policy readiness theo business goal.

### Tình huống H — LB kiểm tra 200 nhưng request người dùng bị 502

Health check đi thẳng tới app management port; public API port của gateway lại có route/TLS error.

**Gợi ý:** health check ở sai chặng. Thiết kế thêm probe hoặc synthetic test qua public path và app listener; không suy từ management 200 ra user transaction success.

### Tình huống I — Synthetic check vô tình tạo giao dịch thật

Monitoring POST một đơn hàng thử mỗi 10 giây trên production, gây tăng dữ liệu và gửi email.

**Gợi ý:** synthetic test phải có tenant/test identity và thao tác an toàn, idempotent hoặc cleanup; giới hạn tần suất, tránh tác động tiền thật hoặc dữ liệu người dùng.

### Tình huống J — Worker /metrics bị chặn sau rotate certificate

Prometheus mất metrics vì client cert chưa được rollout, nhưng liveness/readiness của API bình thường.

**Gợi ý:** giám sát TLS/mTLS certificate riêng; có alert scraping failure, rollover và canary. Không vội tăng liveness failure threshold hay restart toàn app.

### Tình huống K — Readiness liên tục flapping

Một Pod liên tục Ready↔NotReady do dependency check timeout khi tải cao.

**Gợi ý:** xem budget, CPU throttling, caching, circuit breaker, period/timeout/threshold và thực tế service SLO. Tránh tự tăng ngưỡng vô hạn hoặc bỏ check; xác định nguyên nhân biến động.

### Tình huống L — Public health bị cache ở CDN

CDN trả 200 cached của /health mặc dù backend mới triển khai đang lỗi.

**Gợi ý:** health cần phản ánh target và thời điểm đúng, tránh caching không chủ đích; tách edge health và backend readiness, kiểm tra LB target checks và synthetic transaction.

### Tình huống M — Management UI có MFA nhưng API token quá rộng

SRE login qua MFA, nhưng một service token dùng để đọc metrics cũng gọi được endpoint thay config.

**Gợi ý:** MFA cho người không sửa được overly broad machine token. Tách scopes/roles cho metrics read và config mutate; rotate/revoke token, audit và least privilege.

### Tình huống N — Kubelet probe từ node xuyên NetworkPolicy

Đội bảo mật nghĩ NetworkPolicy deny ingress đã chặn mọi traffic từ node tới Pod management port.

**Gợi ý:** node-originated traffic có semantics/đường thực thi đặc thù. Cần kiểm tra CNI, hostNetwork, kubelet path và bảo vệ node, sử dụng app auth phù hợp cho endpoints nhạy cảm; không suy từ Pod-to-Pod deny ra node-to-Pod deny.

### Tình huống O — Endpoint mới xuất hiện sau nâng cấp dependency

Sau upgrade framework, một management capability mới được bật hoặc đường mapping thay đổi, nhưng pipeline chỉ test business API.

**Gợi ý:** thêm inventory/version-specific tests cho management exposure, review defaults và deny policies. Đánh giá route/method/caller thực tế thay vì giả định cấu hình phiên bản cũ còn giữ nguyên.

### Tình huống P — Region dự phòng phục vụ API nhưng admin không an toàn

Failover sang region B; API 200, nhưng management security group của region B rộng hơn và không có audit log.

**Gợi ý:** failover là thất bại về **security parity** dù availability đạt. Đồng bộ IaC/policies, test âm tính management access, theo dõi drift và audit retention.

## 29. Sai lầm thường gặp

1. **Coi /health là vô hại vì tên gọi.** Body có thể tiết lộ dependency hoặc credential.
2. **Dùng health và management chung một policy.** Minimal probe và admin mutation có trust boundary khác nhau.
3. **Dùng DB check trong liveness mặc định.** Gây restart storm khi dependency chung lỗi.
4. **Dùng readiness thay thế hoàn toàn synthetic transaction.** Có thể bỏ qua lỗi end-to-end.
5. **Cho rằng readiness fail restart container.** Kubernetes thường chỉ bỏ Pod khỏi endpoints mới.
6. **Quên startup probe ở ứng dụng khởi động lâu.** Liveness có thể restart sớm.
7. **Chỉ probe management listener mà quên app listener.** Báo UP giả khi cổng phục vụ lỗi.
8. **Tách port management nhưng firewall vẫn public.** Port riêng không đồng nghĩa private.
9. **Chỉ chặn /actuator trên public ingress.** Có thể còn origin, NodePort hoặc alternate route.
10. **Expose toàn bộ Actuator cho tiện debug.** Mở config, dumps và privileged controls.
11. **Cho rằng read-only không nhạy cảm.** Heap dump/config có thể chứa secret.
12. **Đưa token/PII vào metric labels.** Rò dữ liệu và tăng cardinality.
13. **Mở /metrics cho mọi Pod vì “nội bộ”.** Workload bị xâm nhập có thể đọc dữ liệu.
14. **Chỉ dùng IP allowlist cho admin.** Không xác thực người dùng/role thật.
15. **Tin X-Forwarded-For do client gửi.** Có thể giả source IP khi policy sai.
16. **Bật SSO redirect cho kubelet probe.** Dẫn đến readiness/liveness lỗi.
17. **Dùng một token tĩnh trong probe manifest mà không quản lý lifecycle.** Tăng rủi ro secret exposure.
18. **Đánh đồng mTLS với authorization.** Client có cert chưa chắc có quyền mutate.
19. **Dùng chung role metrics.read và config.write.** Vi phạm least privilege.
20. **Cho rằng NetworkPolicy chặn hoàn toàn kubelet node traffic.** Cần kiểm chứng theo CNI/semantics.
21. **Cho rằng Kubernetes tự tạo /livez /readyz cho ứng dụng.** App/framework phải cung cấp route hoặc cấu hình.
22. **Để health query DB nặng ở mỗi request.** Probe trở thành nguồn DoS.
23. **Rate limit probe cùng public API.** Gây 429 và loại backend hợp lệ.
24. **Không tách readiness và application/business health.** Báo khỏe giả hoặc gây rút fleet sai.
25. **Không đặt timeout/dependency budget.** Một health check treo vô hạn.
26. **Không cảnh báo missing telemetry.** Scraper lỗi làm dashboard trống nhưng không ai biết.
27. **Bỏ qua TLS cert rotate trên management plane.** Giám sát hoặc vận hành bị gián đoạn.
28. **Không xem IPv6 và hostNetwork/NodePort.** Có đường khác vào endpoint nhạy cảm.
29. **Coi request HTTP 200 là bằng chứng toàn bộ hệ thống an toàn.** Phải test denied access và nghiệp vụ.
30. **Không kiểm thử failover.** Region dự phòng có thể mất WAF, RBAC hoặc audit.
31. **Đăng heap dump vào ticket chung.** Làm lộ secret dù endpoint đã khóa.
32. **Không có owner và expiry cho debug exposure.** Ngoại lệ tồn tại quá lâu.
33. **Không audit log level/config mutations.** Không biết ai gây thay đổi hành vi.
34. **Bật lại anonymous diagnostics để xử lý outage.** Tạo lỗ hổng mới thay vì rollback có kiểm soát.
35. **Không xem lại cấu hình sau nâng cấp framework.** Defaults/routes có thể thay đổi theo phiên bản.

## 30. Checklist triển khai bảo vệ health check và management endpoint

- [ ] Có inventory đầy đủ health/probe/metrics/debug/admin routes và port, kèm owner.
- [ ] Phân loại rõ liveness, readiness, startup, synthetic và privileged management.
- [ ] Xác định caller hợp lệ, network boundary, identity và policy cho từng loại.
- [ ] Public ingress chỉ phục vụ routes được phê duyệt; không expose admin/dumps.
- [ ] Không coi private IP, port riêng hoặc tên /internal là bằng chứng bảo mật.
- [ ] Probe chỉ trả thông tin tối thiểu và không có secret/topology nhạy cảm.
- [ ] Có response/HTTP status và cache behavior phù hợp với health checker.
- [ ] Liveness không phụ thuộc external shared services nếu restart không giúp phục hồi.
- [ ] Readiness phản ánh khả năng nhận traffic mới, tránh rút toàn bộ replicas không cần thiết.
- [ ] Startup probe dùng khi cần, threshold/timeout dựa trên dữ liệu runtime.
- [ ] Probe nhẹ, có budget, không tạo query nặng và không bị WAF/SSO làm hỏng.
- [ ] Test app listener và user-facing synthetic path, không chỉ management port.
- [ ] Metrics chỉ được scrape bởi monitoring identity đã phê duyệt.
- [ ] Không có bearer token/PII/secret trong metric labels và logs.
- [ ] Diagnostics/dumps bị giới hạn quyền và lưu trữ an toàn.
- [ ] Management read-only và mutation có roles/scopes khác nhau.
- [ ] Admin tương tác có MFA/JIT/approval/audit phù hợp.
- [ ] Automation có service identity, credential rotation và session/revocation policy.
- [ ] Có TLS/mTLS peer validation theo trust boundaries; cert expiry được giám sát.
- [ ] Kiểm soát Service/Ingress/NodePort/LoadBalancer/cloud SG và các origin paths.
- [ ] Kiểm tra IPv4/IPv6, node traffic, hostNetwork và khả năng thực thi của CNI.
- [ ] Không tin forwarded/identity headers từ client ngoài trusted proxy chain.
- [ ] Không expose toàn bộ Spring Actuator chỉ để phục vụ health/Prometheus.
- [ ] Đã kiểm tra behavior phụ thuộc Spring Boot/Kubernetes/cloud provider version.
- [ ] Có negative tests cho public caller, wrong identity, wrong role và direct-origin.
- [ ] Có test dependency outage, restart storm, readiness flapping và startup chậm.
- [ ] Có cảnh báo missing telemetry, probe failure, management privilege misuse và config drift.
- [ ] Có SLO ứng dụng và synthetic transaction độc lập với probe.
- [ ] Failover giữa region/cluster giữ authN/authZ, network, TLS và audit tương đương.
- [ ] Có rollback an toàn, change owner và incident response runbook.
- [ ] Review định kỳ debug endpoints, framework upgrades, permissions và retention.
- [ ] Không coi một GET 200 hoặc trạng thái Pod Ready là chứng minh đầy đủ an toàn.

## 31. Tổng kết

**Bảo vệ health check và management endpoint** là việc cân bằng hai yêu cầu tưởng mâu thuẫn: **bộ điều phối phải quan sát được trạng thái dịch vụ một cách tin cậy**, còn **công cụ chẩn đoán và quyền quản trị phải được cô lập, xác thực, phân quyền và kiểm toán**. Liveness, readiness, startup và synthetic health trả lời những câu hỏi khác nhau; nếu nhầm lẫn, hệ thống có thể báo khỏe giả, không nhận traffic hoặc tạo restart storm khi dependency gặp sự cố.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, kiến trúc vững chắc cần **phân đoạn và hạn chế đường vào, TLS/mTLS theo từng hop, RBAC/MFA cho management, probe tối thiểu không tiết lộ thông tin, metrics/diagnostics có bảo vệ, giới hạn tải và kiểm chứng đường trực tiếp tới origin**. Khi kết hợp **positive và negative tests, ứng dụng SLO, telemetry và runbook**, đội vận hành vừa khôi phục dịch vụ kịp thời, vừa tránh biến các endpoint đáng lẽ phục vụ quản trị thành cửa ngõ mới cho lộ dữ liệu hoặc chiếm quyền hệ thống.
