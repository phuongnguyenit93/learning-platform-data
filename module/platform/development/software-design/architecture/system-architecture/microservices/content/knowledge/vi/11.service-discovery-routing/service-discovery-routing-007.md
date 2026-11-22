# Service mesh: khả năng cung cấp, chi phí và điều kiện áp dụng

> **Nguyên tắc:** Service mesh là một lớp hạ tầng giúp quản lý giao tiếp giữa các workload hoặc microservices, thường cung cấp workload identity, mTLS, định tuyến, chính sách truy cập, resilience và telemetry. Nó không phải thành phần bắt buộc của kiến trúc microservices, không thay thế thiết kế bounded context, quyền sở hữu dữ liệu, API contract hay khả năng xử lý lỗi nghiệp vụ. Quyết định áp dụng cần dựa trên nhu cầu thật, lợi ích đo được và chi phí vận hành dài hạn.

Bài học thuộc mục **Khám phá và định tuyến** trong chủ đề **Software Design, System Architecture, Microservices**. Trọng tâm của bài là câu hỏi: *service mesh cung cấp những gì, nó khiến hệ thống phức tạp thêm ra sao, và khi nào sử dụng là hợp lý?*

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích service mesh, data plane, control plane, workload identity và cách luồng request đi qua proxy.
2. Phân biệt service mesh với Kubernetes Service/DNS, ingress, API gateway, CNI, NetworkPolicy và thư viện resilience trong ứng dụng.
3. Nhận diện các khả năng thường có: discovery nâng cao, traffic splitting, mTLS, authorization, timeout, retry, quan sát và egress policy.
4. Xác định giới hạn: mesh không tạo distributed transaction, exactly-once, semantic API compatibility hoặc phân quyền nghiệp vụ.
5. So sánh sidecar và một số hình thức sidecarless/ambient; nhận diện điều kiện để dùng L4 hay L7 policy.
6. Ước lượng chi phí CPU, RAM, latency, cấu hình, telemetry, vận hành và phạm vi ảnh hưởng khi lỗi.
7. Lập pilot với baseline, SLO, kiểm thử sự cố và phương án rollback.
8. Quyết định áp dụng mesh hay giữ công cụ hiện tại trên cơ sở bằng chứng.

## 2. Bài toán dẫn đến service mesh

Một hệ thống có các service:

~~~text
Client -> API Gateway -> Ordering
                           |--> Pricing
                           |--> Inventory
                           +--> Payment
Catalog -> Search
Fulfillment -> Shipping
~~~

Giữa các service có nhiều vấn đề chung:

- Ordering tìm endpoint hiện tại của Pricing khi pod được tạo/hủy thế nào?
- Hai workload chứng minh danh tính và mã hóa lưu lượng nội bộ ra sao?
- Service nào được gọi Inventory, ở port/endpoint nào?
- Làm sao route 5% lưu lượng tới phiên bản Pricing mới trong canary?
- Timeout, retry, circuit breaker và cân bằng tải được thống nhất ở đâu?
- Làm sao đo latency, error rate và traffic giữa các service?
- Có thể đặt policy xuyên nhiều service mà không sửa từng ứng dụng hay không?

Ở quy mô nhỏ, Kubernetes Service + DNS, REST/gRPC client có timeout, NetworkPolicy và OpenTelemetry thường đã đủ. Ở quy mô lớn, nhiều team và nhiều ngôn ngữ có thể tự triển khai TLS, retry, metrics và routing khác nhau, gây khó quản trị. Mesh cung cấp một lớp **thực thi chính sách giao tiếp dùng chung** để giải quyết một phần các vấn đề này.

**Điều không nên làm:** kết luận “có nhiều container thì phải dùng service mesh”. Số service là tín hiệu quy mô, không chứng minh một tính năng cụ thể cần thiết.

## 3. Service mesh là gì?

Service mesh là lớp hạ tầng điều khiển, bảo vệ và quan sát traffic giữa workload. Hai khái niệm trung tâm:

**Data plane** là thành phần xử lý traffic thật: proxy cạnh workload, proxy cấp node hoặc một đường dữ liệu khác theo sản phẩm. Data plane có thể thực hiện mTLS, routing, load balancing, chính sách L4/L7 và telemetry trong phạm vi được hỗ trợ.

**Control plane** cung cấp cấu hình, endpoint, chứng chỉ/danh tính và policy cho data plane. Control plane thông thường không nằm trên mọi đường request giữa hai ứng dụng; nó định hướng proxy để proxy xử lý traffic.

~~~text
                   +------------------------+
                   |   Mesh Control Plane   |
                   | endpoints / policies   |
                   | identity / certificates|
                   +-----------+------------+
                               |
                       distributes configs
                        /               \
                       v                 v
+----------------------------+   +----------------------------+
| Workload A Pod             |   | Workload B Pod             |
| [Application A]            |   | [Application B]            |
|         |                  |   |         ^                  |
|    [Proxy A] ====== mTLS ====== [Proxy B]                 |
+----------------------------+   +----------------------------+
~~~

Ứng dụng vẫn làm việc với contract nghiệp vụ. Ví dụ Ordering yêu cầu ReserveStock, còn Inventory quyết định giữ hàng hợp lệ hay bị từ chối. Mesh có thể đảm bảo identity, mã hóa và timeout của kết nối; nó **không quyết định** có đủ hàng hay không.

### 3.1. Không phải toàn bộ traffic tự đi qua mesh

Cần xác minh workload nào đã tham gia mesh và traffic nào được proxy capture:

- Namespace hoặc pod có được inject/enroll vào mesh không?
- Có workload chạy hostNetwork hoặc đường kết nối đặc biệt không?
- Lưu lượng TCP, HTTP, gRPC, database, UDP và giao thức tùy biến được hỗ trợ đến mức nào?
- Có ingress/egress gateway, sidecar bypass hoặc policy ngoại lệ không?
- App đã tự TLS và proxy chỉ thấy dữ liệu mã hóa hay chưa?
- NetworkPolicy/CNI có cho phép luồng hợp lệ đi qua không?

**Cluster đã cài mesh không có nghĩa mọi đường kết nối đều được mã hóa, quan sát hoặc kiểm soát bởi mesh.** Phải kiểm chứng data path thực tế.

## 4. Có mesh và không có mesh: khác nhau ở trách nhiệm

Không có mesh, một ứng dụng Spring Boot thường dùng HTTP client, DNS, timeout/retry, TLS và telemetry SDK:

~~~text
[Ordering Application]
   |- Pricing HTTP client
   |- TLS/client authentication
   |- timeout / retry policies
   |- metrics / tracing
   |- business workflow
   +-> [Inventory Service]
~~~

Khi có mesh:

~~~text
[Ordering Application]
   |- domain/API contract
   |- workflow, idempotency
   |- application metrics / tracing
   +-> [Mesh data plane]
       |- identity / transport mTLS
       |- route / load balancing
       |- selected traffic policies
       |- transport telemetry
       +-> [Inventory Service]
~~~

Một số concerns được chuyển ra lớp hạ tầng, nhưng ứng dụng vẫn phải hiểu:

- Timeout có phải đã xử lý thành công hay chưa xác định?
- Có được retry thao tác tạo payment không?
- Khi Inventory trả hết hàng, Order chuyển trạng thái gì?
- Có được dùng giá cũ nếu Pricing unavailable không?
- Ai sở hữu dữ liệu và bất biến của giao dịch?

**Dịch chuyển chính sách giao tiếp không đồng nghĩa chuyển quyền quyết định nghiệp vụ cho mesh.**

## 5. Các khả năng thường được cung cấp

| Nhóm | Service mesh có thể cung cấp | Điều cần xác minh |
| --- | --- | --- |
| Discovery và endpoint routing | Danh sách endpoint, cân bằng tải, route theo subset | Kubernetes Service/DNS đã có nhiều chức năng cơ bản |
| Traffic shaping | Weighted routing, canary, header-based rule nếu L7 được hỗ trợ | Phiên bản đích vẫn phải tương thích API/data |
| mTLS | Workload authentication và mã hóa kết nối | Không bao phủ đường bypass hoặc đối tác ngoài trust domain |
| Authorization | Chính sách theo identity nguồn/đích, namespace, port/path khi có L7 | Không thay authorization theo user, tenant, resource |
| Resilience | Timeout, retry, outlier detection, circuit breaking tùy sản phẩm | Không tự hiểu idempotency và business failure |
| Telemetry | Metrics request, latency, error, topology, access logs | Không thay domain metrics và tracing ứng dụng |
| Egress | Policy outbound, kiểm soát qua egress gateway | Không tự thay TLS/auth tới nhà cung cấp bên ngoài |
| Multi-cluster | Kết nối/trust/routing qua cluster theo khả năng sản phẩm | Network partition, CA/trust domain và vận hành phức tạp |
| Traffic security | Bảo mật giao tiếp trong phạm vi mesh | Không thay security toàn hệ thống hoặc encryption at rest |

Bảng chỉ mô tả **các năng lực thường thấy**, không hứa một sản phẩm cụ thể hỗ trợ toàn bộ. Quyết định dựa vào phiên bản công cụ, data plane mode và khả năng tương thích với workload.

## 6. Khám phá dịch vụ: mesh có bổ sung gì cho Kubernetes Service/DNS?

Kubernetes vốn có Service, EndpointSlice và DNS để giúp ứng dụng gọi một tên dịch vụ mà không cần biết từng pod IP:

~~~text
Ordering
  |
  v
pricing.commerce.svc.cluster.local
  |
  v
Kubernetes Service -> Pricing Pod A / Pod B / Pod C
~~~

Mesh có thể sử dụng cùng thông tin endpoint để áp policy chi tiết:

~~~text
Ordering -> Mesh route
              |-- 90% -> Pricing v1 endpoints
              +-- 10% -> Pricing v2 endpoints
~~~

Lợi ích tăng thêm có thể là:
- Traffic split theo version.
- Route theo thuộc tính HTTP/header khi data plane hiểu L7.
- Mô hình load balancing nâng cao hoặc locality.
- Một bộ chính sách timeout/retry và đo latency theo source/destination.
- Tập trung cấu hình thay vì sửa logic routing trong ứng dụng.

**Không nên cài mesh chỉ để có DNS service discovery** nếu Kubernetes đã đáp ứng đủ. Cần chỉ ra nhu cầu discovery/routing nâng cao nào hiện chưa được giải quyết.

## 7. Canary và traffic splitting

Giả sử Catalog v2 vừa bổ sung thuật toán xếp hạng kết quả. Mesh có thể hỗ trợ route một phần lưu lượng:

~~~text
Incoming product queries
      |
      v
Catalog routing policy
      |---- 95% ---> Catalog v1
      +----- 5% ---> Catalog v2
~~~

Nhưng traffic 5% **request** không nhất thiết là 5% người dùng. Một người dùng có thể đi qua cả hai phiên bản trong nhiều request nếu không có session affinity hoặc routing theo user phù hợp.

Trước canary cần:

1. Contract v1/v2 cùng xử lý được request và response trong rolling window.
2. Migration database đã theo hướng expand–migrate–contract.
3. Dữ liệu do v2 ghi không phá rollback về v1.
4. Có metrics theo phiên bản, lỗi kỹ thuật và business outcome.
5. Có route rollback đã thử nghiệm.
6. Có phân tích thao tác stateful và độ bền session.

**Mesh giúp chuyển traffic; nó không kiểm tra tính tương thích nghiệp vụ thay bạn.**

### 7.1. Mirroring/shadow traffic

Một số mesh hỗ trợ mirror request sang bản mới mà không lấy response bản mới trả cho client. Không mirror mù thao tác có side effect: thu tiền, tạo đơn, giữ kho hoặc gửi email. Với đọc dữ liệu, cũng phải cân nhắc quyền truy cập, dữ liệu nhạy cảm và tải nhân đôi.

## 8. Bảo mật: mTLS và workload identity

mTLS giúp hai phía kết nối xác thực lẫn nhau và mã hóa đường truyền trong phạm vi mesh. Danh tính thường gắn với workload/service account/trust domain, đôi khi dùng mô hình SPIFFE hoặc cơ chế tương đương.

~~~text
Ordering workload identity
         |
      mTLS channel
         |
Inventory workload identity
         |
  policy: allow Ordering -> Inventory
~~~

Cần phân biệt:
- **User identity:** người sử dụng là ai.
- **Workload identity:** tiến trình/service nào đang gọi.
- **Business subject:** merchant/tenant/order chịu quy tắc nghiệp vụ.

Mesh có thể chứng minh Ordering được gọi Inventory; nó không chứng minh Ordering được sửa reservation của mọi merchant. Authorization theo orderId, tenant, kho hoặc vai trò của người dùng vẫn phải được kiểm tra ở miền nghiệp vụ.

### 8.1. STRICT và PERMISSIVE khi di chuyển

Có mô hình policy cho phép một giai đoạn permissive để workload ngoài mesh vẫn giao tiếp, sau đó mới strict mTLS. Khi chuyển cần inventory tất cả nguồn traffic, gồm health probes, jobs, legacy clients và service ở namespace khác.

Bật STRICT trước khi chắc tất cả caller phù hợp sẽ tạo outage. Test cả đường hợp lệ và đường phải bị từ chối.

### 8.2. Chứng chỉ và vòng đời danh tính

Cần vận hành issuance, rotation, expiry, đồng bộ thời gian và trust bundle. Nếu certificate hết hạn hoặc root CA đổi sai thứ tự, nhiều workload có thể đồng loạt lỗi handshake.

Cần dashboard thời hạn chứng chỉ, owner, cảnh báo và diễn tập sự cố. Không coi mTLS là một nút bật rồi quên.

## 9. L4 và L7: chính sách nào áp dụng ở đâu?

**L4** quan tâm địa chỉ, port, transport và kết nối; có thể hỗ trợ mTLS/identity ở cấp đường truyền.

**L7** hiểu nội dung protocol ứng dụng như HTTP method, host, path, header hoặc tên method gRPC, nếu proxy có khả năng giải mã và phân tích.

Ví dụ:
- Cho phép Ordering kết nối Inventory port 8080: policy ở cấp kết nối có thể đủ.
- Chỉ cho Ordering gọi POST /reservations, không được gọi DELETE /stock: cần policy hiểu HTTP.
- Route GET /products theo header canary: cần L7 HTTP routing.

Nếu workload dùng custom TCP protocol hoặc TLS end-to-end mà mesh không giải mã, proxy có thể chỉ hiểu L4. Không viết policy theo HTTP path rồi giả định nó luôn có tác dụng.

## 10. Resilience: timeout, retry và circuit breaking

Mesh có thể áp traffic policy tập trung, nhưng **lỗi mạng và lỗi nghiệp vụ phải được phân biệt**.

### 10.1. Timeout không có nghĩa thao tác thất bại

Ordering gọi Inventory ReserveStock. Inventory đã commit, response bị mất. Proxy hoặc client timeout. Nếu retry bằng commandId mới, Inventory có thể giữ hàng thêm lần nữa.

Ứng dụng cần idempotency key ổn định và Inventory cần deduplication/unique constraint hoặc cơ chế tương đương. Proxy không biết hai POST đại diện cùng một ý định nghiệp vụ.

### 10.2. Retry amplification

Nếu app retry ba lần và mesh cũng retry ba lần:

~~~text
App attempt 1 -> Mesh attempt 1,2,3
App attempt 2 -> Mesh attempt 1,2,3
App attempt 3 -> Mesh attempt 1,2,3

Possible downstream attempts: 9
~~~

Trong outage, việc này có thể khiến downstream càng quá tải. Cần xác định lớp chịu trách nhiệm retry, giới hạn số lần, deadline, backoff/jitter và chỉ retry lỗi thật sự có thể hồi phục.

Không áp retry đồng loạt cho POST thanh toán, hoàn tiền hay cập nhật trạng thái mà chưa xác nhận hợp đồng idempotent.

### 10.3. Deadline đầu cuối

Ví dụ client chỉ chờ 800 ms:

~~~text
Client deadline:       800 ms
Auth/Gateway budget:   100 ms
Ordering local work:   150 ms
Downstream budget:     400 ms
Response and margin:   150 ms
~~~

Đây là ví dụ khái niệm, không phải cấu hình chuẩn. Timeout ở mesh phải phù hợp ngân sách còn lại, không được đặt mỗi hop timeout 3 giây rồi để request vượt deadline.

### 10.4. Circuit breaker và outlier detection

Proxy có thể hạn chế kết nối đến endpoint lỗi hoặc chuyển traffic khỏi endpoint bất thường. Nhưng HTTP 4xx do từ chối nghiệp vụ khác với transport failure/5xx. Một policy quá nhạy có thể loại endpoint khỏe chỉ vì API trả nhiều “không đủ hàng” hợp lệ.

Fallback phải do nghiệp vụ quyết định. Khi Pricing không phản hồi, không được tự trả “giá 0” hoặc xác nhận đơn với quote chưa hợp lệ chỉ để giảm lỗi kỹ thuật.

## 11. Observability: metrics và tracing

Mesh có thể cung cấp request rate, latency, error rate, traffic topology, một số access log và trace/span ở đường giao tiếp. Đây là lợi ích lớn khi nhiều ngôn ngữ hoặc team sử dụng client khác nhau.

Ví dụ metrics quan tâm:
- Service A gọi Service B bao nhiêu RPS?
- p95/p99 request latency giữa hai workload?
- Tỷ lệ lỗi 5xx/timeout/transient errors?
- Traffic phân bố giữa các version ra sao?
- Có proxy bị saturation hoặc lỗi kết nối nhiều không?

Nhưng proxy thường không biết:
- Có bao nhiêu đơn CONFIRMED thành công theo chính sách?
- Một payment đã được captured hay chỉ authorized?
- Reservation thất bại vì hết hàng hay vì lỗi dữ liệu?
- Saga có đang ở trạng thái bù trừ hay không?

Cần bổ sung application metrics, structured logs, distributed tracing và correlation ID. Với workflow async qua queue, mesh không tự nối được toàn bộ quan hệ nghiệp vụ nếu ứng dụng không truyền causation/event identifiers.

### 11.1. Chi phí quan sát

Access logs có thể ghi lượng lớn dữ liệu và gây nguy cơ lộ thông tin nhạy cảm nếu không lọc. Metrics với nhãn high-cardinality và tracing 100% traffic có thể khiến phí lưu trữ tăng nhanh. Cần chính sách sampling, retention, label cardinality, mask PII/secret và xác định chủ sở hữu dashboard.

## 12. Sidecar và sidecarless/ambient

### 12.1. Sidecar

~~~text
Pod A: App A + Proxy A
Pod B: App B + Proxy B

App A -> Proxy A -> Network -> Proxy B -> App B
~~~

Ưu điểm:
- Enforcement gần ứng dụng.
- Có thể hỗ trợ nhiều chính sách L4/L7.
- Telemetry theo workload thuận tiện.

Chi phí:
- Proxy tiêu thụ CPU/RAM ở mỗi pod.
- Startup, shutdown và readiness phức tạp hơn.
- Certificate và proxy config thay đổi theo vòng đời pod.
- Lỗi injection hoặc proxy có thể làm application pod không kết nối được.
- Nhiều workload nhỏ dẫn đến số lượng proxy lớn.

### 12.2. Sidecarless/ambient

Một số kiến trúc dùng đường dữ liệu dùng chung ở cấp node cho L4, và một waypoint/L7 proxy nếu cần chính sách HTTP chi tiết:

~~~text
Workloads
   |
   v
Node-level secure tunnel (L4)
   |
   +----> optional L7 waypoint
   |
   v
Destination workload
~~~

Điều này có thể giảm một số chi phí sidecar trên mỗi pod, nhưng không miễn phí. Cần đo tài nguyên của node-level component, waypoint, control plane và ảnh hưởng khi một component chung lỗi. Tính năng L7 có thể không được cung cấp nếu chỉ bật L4.

**Không so sánh bằng khẩu hiệu “sidecarless luôn nhẹ hơn”.** So sánh theo workload, cấu hình policy, failure domain và chi phí thực tế.

## 13. Phân biệt với các thành phần khác

| Thành phần | Vai trò chính | Quan hệ với mesh |
| --- | --- | --- |
| Kubernetes Service/DNS | Tên và endpoint dịch vụ | Có thể đủ cho discovery cơ bản |
| Ingress/Gateway | Traffic từ bên ngoài vào cluster | Mesh chủ yếu quản lý east-west; có khả năng tích hợp |
| API Gateway | Public API, auth client, rate limit, BFF, developer-facing policies | Chồng lấn một số chức năng, phạm vi thường khác |
| CNI/NetworkPolicy | Network connectivity và phân đoạn L3/L4 | Bổ sung security/connectivity; không tự là full mesh |
| App resilience library | Timeout/retry/bulkhead/circuit breaker trong code | Có thể dùng thay hoặc cùng mesh; phải tránh policy chồng |
| OpenTelemetry SDK/collector | Trace, metrics, logs từ ứng dụng | Cần để hiểu workflow/domain ngoài proxy |
| Contract testing | Đảm bảo các API/message version tương thích | Mesh không thay công việc này |
| Service mesh | Workload traffic, identity, policy, telemetry | Thêm một lớp nền tảng có chi phí vận hành |

Không phải mọi hệ thống cần tất cả thành phần. Hãy lập bảng chức năng hiện đã có để tránh cấu hình hai nơi cùng kiểm soát route, retry hoặc authorization theo cách xung đột.

## 14. Chi phí tài nguyên và độ trễ

### 14.1. Sidecar overhead tính theo số pod

Một phép tính **giả định** chỉ để minh họa:

~~~text
200 pods có sidecar
Mỗi sidecar reserve trung bình:
  Memory: 80 MiB
  CPU:    50 millicores

Total requested memory: 200 * 80 MiB = 16,000 MiB (~15.6 GiB)
Total requested CPU:    200 * 50m    = 10 CPU cores
~~~

80 MiB và 50m **không phải benchmark hoặc khuyến nghị sizing**; usage thật phụ thuộc traffic, route count, proxy implementation, certificate, logs, L7 filters và cấu hình. Phân biệt CPU/RAM requests với usage thực tế. Không dùng con số này để cấp tài nguyên production nếu chưa đo.

### 14.2. Request latency

Proxy có thể thêm chi phí TLS, serialization/parsing, filters, routing và telemetry. Tác động phải đo bằng:
- p50/p95/p99 end-to-end.
- RPS, payload size, HTTP/1.1, HTTP/2, gRPC hoặc TCP.
- Same-node, cross-node, cross-zone traffic.
- Connection reuse, CPU throttling, memory pressure.
- mTLS, L4/L7 policy và access logs bật/tắt.
- Số hop và fan-out của các workflow quan trọng.

Không có quy tắc “mesh luôn thêm đúng X ms”. Một số routing policy có thể tránh endpoint lỗi và cải thiện chất lượng tổng thể, nhưng vẫn cần đo SLO của người dùng.

### 14.3. Control plane và cấu hình

Control plane xử lý cập nhật endpoint, policy, certificate, topology và cấu hình. Với nhiều pod churn, nhiều route và nhiều policy, CPU/memory, config convergence và network overhead có thể đáng kể. Phải thiết kế HA, cấu hình phạm vi phù hợp và cảnh báo.

### 14.4. Telemetry storage

Proxy metrics/logs/tracing có thể làm tăng phí observability; label cardinality và log retention nên được kiểm soát. Một hệ thống có thể tiết kiệm code instrumentation nhưng phát sinh chi phí lưu trữ/cảnh báo và vận hành hơn trước.

## 15. Chi phí vận hành và tổ chức

Cần một platform owner thực sự chịu trách nhiệm:
- Cài đặt, upgrade và tương thích phiên bản mesh với Kubernetes/CNI/gateway.
- Certificate issuance, rotation, expiry, trust domain.
- Policy as code, review, canary và rollback.
- Proxy injection/enrollment, readiness, startup/shutdown.
- Routing, TLS errors, mesh telemetry, incident response.
- Capacity control, control-plane HA và runbook sự cố.
- Hướng dẫn app teams về timeout/retry/idempotency và trách nhiệm ứng dụng.
- Auditing policy, quyền sửa cấu hình và lịch deprecation.

Một rule policy sai có thể ảnh hưởng hàng chục service. Một rule route sai có thể gửi traffic tới phiên bản không tương thích. Một cơ chế retry sai có thể tăng tải diện rộng. **Mesh tập trung chính sách cũng có nghĩa nó tập trung khả năng gây sự cố nếu thiếu quản trị.**

### 15.1. Debug có thêm thành phần

Không mesh:

~~~text
Client -> App
~~~

Có mesh:

~~~text
Client -> Proxy A -> Network -> Proxy B -> App
             |                     |
        TLS/routing          authorization
        timeout              health/telemetry
~~~

Khi request lỗi phải phân biệt:
- 403 do policy hay do application authorization?
- 503 do không có endpoint, proxy lỗi, TLS handshake hay app unavailable?
- Request chậm do L7 filter, connection pool, network hay database?
- Có retry từ mesh và app cùng lúc không?
- Proxy sidecar đã nhận config mới chưa?

Vận hành cần khả năng nhìn vào data plane config, identity, policy và metrics, không chỉ log ứng dụng.

## 16. Mesh không giải quyết những gì?

**Không tự thiết kế bounded context:** 30 service chia theo controller vẫn là kiến trúc coupling cao, dù có mesh.

**Không thay data ownership:** hai service cùng ghi một bảng vẫn cần được phân rã quyền sở hữu đúng.

**Không tạo ACID transaction xuyên database:** Ordering, Inventory, Payment vẫn cần Saga/process manager, bù trừ và reconciliation khi có workflow dài.

**Không bảo đảm exactly-once business effect:** proxy retry có thể tạo request trùng; Payment/Inventory phải idempotent.

**Không thay quản lý API version:** canary không tự giúp consumer cũ hiểu schema/semantics mới.

**Không thay object-level authorization:** mTLS workload không biết user nào có quyền xem Order cụ thể.

**Không tự sửa database chậm:** một SQL query 800 ms sẽ không thành nhanh chỉ vì đi qua Envoy hoặc proxy khác.

**Không bảo đảm tracing nghiệp vụ:** transport telemetry không tự giải thích một payment đã captured hay chỉ authorized.

**Không tự cung cấp compliance hoàn chỉnh:** dữ liệu nghỉ, quản lý secret, audit, vulnerability management và quy định pháp lý vẫn là công việc riêng.

**Không xóa chi phí của hệ phân tán:** network failure, contract versioning và dữ liệu lệch vẫn cần thiết kế đúng.

## 17. Khi nào mesh đáng cân nhắc?

### 17.1. Nhiều team và nhiều ngôn ngữ

Nếu mỗi nhóm tự quản lý mTLS, retry, routing và telemetry, rất khó kiểm tra chính sách và sửa lỗi đồng nhất. Mesh có thể tạo nền tảng chung nếu có platform team đủ năng lực.

### 17.2. Nhu cầu workload identity/mTLS rõ

Khi security yêu cầu xác định workload nguồn/đích, mã hóa east-west và có policy truy cập thống nhất, mesh là một lựa chọn đáng xem xét, cùng với các giải pháp security/networking khác.

### 17.3. Canary/traffic policy lặp lại thường xuyên

Nếu nhiều service cần traffic splitting, locality routing hoặc policy L7 phức tạp, mesh có thể tránh việc từng team tự viết proxy/routing. Phải kiểm thử contract compatibility của mọi version.

### 17.4. Incident cross-service khó quan sát

Nếu thiếu metrics source-destination, service topology hoặc transport-level latency, mesh telemetry có thể giúp đáng kể; vẫn cần instrumentation ứng dụng cho business events.

### 17.5. Có năng lực vận hành

Đội nền tảng cần CI/CD, config-as-code, alerting, certificate management, rollback và quy trình triển khai an toàn. Một mesh trên nền vận hành yếu có thể làm outage khó xử lý hơn.

## 18. Khi nào chưa nên dùng?

- **Ứng dụng nhỏ** chỉ có vài service, DNS/discovery, HTTP client và metrics đã đáp ứng tốt.
- **Không có vấn đề cụ thể** về security/telemetry/routing cần giải quyết.
- **Chưa rõ ranh giới nghiệp vụ**, các service dùng chung database và deploy lockstep.
- **Không có người chịu trách nhiệm** control plane và certificate lifecycle.
- **Workload rất nhạy với latency hoặc memory** mà chưa có ngân sách proxy.
- **Chỉ mong tự sửa reliability:** retry và circuit breaker không hiểu business semantics.
- **Chức năng bị trùng** với gateway, CNI, SDK hoặc công cụ hiện có mà chưa có lý do hợp nhất.
- **Thiếu khả năng đo lường:** không có baseline để biết mesh giúp hay hại.

Không có ngưỡng số lượng service nào tự quyết định “bắt buộc mesh”. Có hệ thống ít service nhưng yêu cầu bảo mật đặc biệt cần dùng; có hệ thống nhiều service vẫn vận hành tốt với công cụ khác.

## 19. Đánh giá lựa chọn thay thế

**Phương án A — Giữ Kubernetes Service/DNS + thư viện ứng dụng:** phù hợp khi nhu cầu đơn giản, các nhóm tuân thủ chuẩn SDK, không cần traffic policy phức tạp. Dùng OpenTelemetry, TLS phù hợp, network policy và client resilience có kiểm soát.

**Phương án B — Áp mesh cho một namespace/nhóm workload:** phù hợp khi có nhu cầu cao ở một khu vực nhạy cảm hoặc cần pilot. Phải kiểm tra giao tiếp giữa meshed và unmeshed workloads.

**Phương án C — Mesh diện rộng:** có thể phù hợp khi nhu cầu thống nhất identity/routing/telemetry đủ lớn, có platform ownership và pilot thành công. Phải đánh giá blast radius của cấu hình chung.

**Phương án D — Sidecarless/ambient hoặc L4-only path:** phù hợp nếu mục tiêu chủ yếu là identity/mTLS và muốn giảm overhead per-pod, nhưng phải kiểm tra L7 waypoint, failure domain và tổng chi phí.

**Quyết định tốt là chọn mức phức tạp nhỏ nhất giải quyết được yêu cầu đã chứng minh.**

## 20. Ví dụ Istio: chia traffic canary

Ví dụ sau mang tính **minh họa** cho một mesh sử dụng các CRD Istio. Trước khi dùng thật phải kiểm tra API/version được cluster hỗ trợ, label workload, namespace và cách enrollment.

~~~yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: catalog-subsets
  namespace: commerce
spec:
  host: catalog.commerce.svc.cluster.local
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
---
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: catalog-routing
  namespace: commerce
spec:
  hosts:
    - catalog.commerce.svc.cluster.local
  http:
    - route:
        - destination:
            host: catalog.commerce.svc.cluster.local
            subset: v1
          weight: 95
        - destination:
            host: catalog.commerce.svc.cluster.local
            subset: v2
          weight: 5
~~~

Điều kiện:
- Catalog v1/v2 cùng được Kubernetes Service chọn.
- Pod có label version tương ứng.
- Data plane của request nhận policy L7 này.
- Hai phiên bản có API và database tương thích trong rollout.
- Có metrics canary và rollback route đã được thử.

Đừng dùng traffic split làm lý do bỏ kiểm tra version compatibility. Nếu Catalog v2 ghi dữ liệu khiến v1 không đọc được, rollback route cũng không khôi phục được hệ thống.

## 21. Ví dụ Istio: ý tưởng mTLS và AuthorizationPolicy

Một policy yêu cầu mTLS cho workload Inventory theo selector:

~~~yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: inventory-mtls
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: inventory
  mtls:
    mode: STRICT
~~~

Một rule minh họa chỉ nhận nguồn từ service account Ordering:

~~~yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: inventory-allow-ordering
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: inventory
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/commerce/sa/ordering
~~~

Các ví dụ chỉ thể hiện **ý định chính sách**, chưa tính ngoại lệ vận hành, health, port/path và trust domain thực tế. Trong production, phải xác minh workload identity, selector, chính sách mặc định, giao thức L4/L7, luồng ngoài mesh và khả năng rollback. Không bật STRICT trên một namespace khi còn caller không tham gia mesh mà chưa có kế hoạch di chuyển.

## 22. Spring Boot vẫn cần xử lý nghiệp vụ và timeout

Service Ordering có thể sử dụng cổng domain:

~~~java
package example.ordering.application;

public interface ReservationPort {
    ReservationDecision reserve(
            String orderId,
            String sku,
            int quantity,
            String commandId);
}

public record ReservationDecision(
        String reservationId,
        boolean accepted,
        String reason) {}
~~~

Adapter HTTP:

~~~java
package example.ordering.infrastructure.inventory;

import example.ordering.application.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class InventoryHttpAdapter implements ReservationPort {
    private final RestClient client;

    InventoryHttpAdapter(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory.commerce.svc.cluster.local")
                .build();
    }

    @Override
    public ReservationDecision reserve(
            String orderId, String sku, int quantity, String commandId) {
        return client.post()
                .uri("/internal/reservations")
                .header("Idempotency-Key", commandId)
                .body(new ReserveRequest(orderId, sku, quantity))
                .retrieve()
                .body(ReservationDecision.class);
    }
}

record ReserveRequest(String orderId, String sku, int quantity) {}
~~~

Mã minh họa phân lớp, không phải ví dụ production đầy đủ. Việc dùng URL http trong app có thể phù hợp khi mesh thực hiện mTLS ở lớp proxy theo data path đã kiểm chứng; không được suy ra mọi traffic đều mã hóa chỉ vì có mesh. HTTP client vẫn cần timeout, TLS/auth ở chặng phù hợp, xử lý lỗi và telemetry.

Header Idempotency-Key chỉ có tác dụng khi Inventory thật sự lưu và kiểm tra khóa ổn định. Timeout có thể xảy ra sau khi Inventory commit; Ordering phải tra kết quả hoặc giữ trạng thái chưa xác định, không tự tạo reservation mới.

## 23. Điều gì xảy ra khi mesh gặp lỗi?

### 23.1. Control plane unavailable

Một số data plane có thể tiếp tục dùng cấu hình đã nhận khi control plane lỗi. Nhưng proxy mới, endpoint mới, config change và certificate rotation có thể bị ảnh hưởng. Hành vi phụ thuộc implementation, không bảo đảm chung.

Kiểm thử:
- Existing connections.
- New connections đến endpoint hiện có.
- Pod khởi động trong lúc control plane unavailable.
- Chứng chỉ sắp hết hạn.
- Cập nhật route/policy chưa được phân phối.
- Rollback config khi control plane chưa phục hồi.

### 23.2. Sidecar hoặc node-level data plane lỗi

App có thể vẫn sống nhưng mọi kết nối đi qua proxy gặp lỗi. Cần readiness, startup/shutdown ordering, graceful drain, liveness và nguồn telemetry phân biệt lỗi proxy với app.

Ở mô hình sidecarless, node-level component lỗi có thể ảnh hưởng nhiều workload cùng node. Sự tập trung tài nguyên thay đổi **failure domain** và cần được thử nghiệm.

### 23.3. Policy sai

Một AuthorizationPolicy sai có thể từ chối mọi caller. Một route sai có thể gửi 100% traffic tới bản lỗi. Một retry policy sai có thể gây retry storm. Cần GitOps/config review, phân quyền sửa policy, thử trên một phạm vi nhỏ và cách revert rõ ràng.

### 23.4. Certificate lifecycle lỗi

Clock skew, CA rotation sai hoặc certificate expiry có thể gây handshake failure diện rộng. Cần alerts, runbook, khả năng chẩn đoán trust chain, identity và chứng chỉ.

## 24. Multi-cluster và egress

Multi-cluster đòi hỏi DNS/naming, network connectivity, trust domain/CA, service identity, locality, failover, traffic cost, data residency và cách xử lý network partition. Mesh có thể hỗ trợ một phần, nhưng không biến ứng dụng thành đa vùng an toàn về dữ liệu.

Egress tới payment gateway, email provider hoặc API đối tác cần quản lý TLS/auth riêng, API key, secret, rate limit, egress allowlist và audit. mTLS nội bộ không tự kéo dài tới đối tác nằm ngoài trust domain. Có egress gateway cũng không chứng minh toàn bộ outbound bị kiểm soát nếu có bypass.

## 25. Pilot: áp dụng theo bằng chứng

### Bước 1 — Xác định mục tiêu và baseline

Ví dụ mục tiêu:
- 100% traffic giữa các workload được chọn dùng identity/mTLS, kiểm chứng bằng thử nghiệm.
- Giảm thời gian điều tra sự cố cross-service.
- Đưa canary không phải sửa code routing từng service.
- Giữ p95/p99 và CPU/RAM overhead trong ngân sách đã định.

Thu baseline trước khi cài mesh: latency, RPS, error rate, throughput, CPU/RAM, kết nối, metrics hiện có và thời gian vận hành.

### Bước 2 — Chọn phạm vi nhỏ, rủi ro thấp

Chọn một namespace/service pair có luồng request rõ, ít side effect, dễ rollback. Không bắt đầu bằng luồng thanh toán capture nếu platform chưa có kinh nghiệm chẩn đoán proxy.

### Bước 3 — Vẽ data path

Ghi inbound/outbound, external dependencies, cổng, protocol, workload identities, service account và traffic nào bị bypass. Đảm bảo mesh policy được áp dụng ở đúng đường đi.

### Bước 4 — Áp cấu hình tối thiểu

Bắt đầu telemetry và policy cần thiết; không bật retry tự động diện rộng. Thử migration mTLS an toàn khi có workload cũ. Không thêm rule chỉ vì công cụ hỗ trợ.

### Bước 5 — Thử failure modes

Test mTLS allow/deny, policy sai, certificate rotation, pod restart, proxy crash, control-plane outage, request timeout, canary rollback và traffic ngoài mesh. Cần xác nhận thao tác side effect không bị nhân đôi.

### Bước 6 — Đo tải và chi phí

So sánh p95/p99, error rate, CPU/RAM, connection pool, telemetry cost, failover behavior và vận hành incident trên cùng workload. Tách số đo từng phiên bản để tránh nhầm lẫn thay đổi do tải hoặc release ứng dụng.

### Bước 7 — Quyết định mở rộng hoặc dừng

Nếu mesh giải quyết mục tiêu, overhead trong giới hạn, platform team vận hành được và rollback an toàn, mở rộng theo từng nhóm workload. Nếu không có lợi ích rõ hoặc quá phức tạp, giữ kiến trúc không mesh là kết quả hợp lý.

## 26. Tình huống thực hành

### Bài 1 — Ít service

Hệ thống có bốn Spring Boot service, DNS/Service discovery hoạt động tốt, có tracing và timeout. Có cần cài mesh không?

**Gợi ý:** Chưa đủ bằng chứng. Hỏi nhu cầu cụ thể: mTLS giữa workload, security governance, canary hay telemetry thiếu. Nếu công cụ hiện tại đáp ứng SLO, không phải thêm mesh.

### Bài 2 — Nhiều team, chính sách lệch nhau

Một tổ chức có 80 service, 12 nhóm và ba ngôn ngữ; mỗi nhóm tự cấu hình TLS/retry, đội security khó kiểm chứng. Mesh có ích không?

**Gợi ý:** Đáng cân nhắc vì lợi ích chuẩn hóa workload identity, mTLS và policy. Phải có platform owner, pilot, baseline và so sánh phương án khác.

### Bài 3 — Canary tính sai tiền

Pricing v2 đổi amount từ đồng sang minor units đa currency, Ordering v1 không hiểu. Mesh chuyển 10% request tới v2 và gây sai giá.

**Gợi ý:** Đây là lỗi semantic contract compatibility. Cần expand–migrate–contract, version API hoặc capability gate trước khi traffic split.

### Bài 4 — Retry nhân đôi reservation

Inventory đã giữ hàng nhưng response thất lạc. Mesh retry POST, Inventory không dedup và trừ tồn hai lần.

**Gợi ý:** Không bật retry mù. Thiết kế idempotency key ổn định, unique constraint/dedup transaction, tra cứu trạng thái và reconciliation.

### Bài 5 — mTLS chỉ bật một phần

Một batch job ngoài mesh vẫn gọi Inventory bằng plaintext. Dashboard báo mesh đang bật mTLS.

**Gợi ý:** Kiểm tra enrollment, đường bypass, strict policy và network policy; không coi dashboard là bằng chứng bảo vệ toàn hệ thống.

### Bài 6 — p99 tệ hơn

Thêm sidecar cho nhiều pod nhỏ; p50 gần như không đổi nhưng p99 tăng ở peak load.

**Gợi ý:** Đo CPU throttling, memory, proxy filter, mTLS, logs, connection reuse, node saturation và kiểm tra sidecarless nếu phù hợp. So sánh với baseline thật.

### Bài 7 — Authorization sai phạm vi

Mesh cho phép Ordering gọi Inventory nhưng merchant A vẫn đọc được reservation của merchant B.

**Gợi ý:** Mesh chủ yếu kiểm tra workload identity. Inventory phải thực hiện authorization theo tenant, merchant, orderId và domain context.

### Bài 8 — Control plane lỗi

Existing proxies còn hoạt động, pod mới không nhận được config/chứng chỉ.

**Gợi ý:** Data plane có thể dùng cached config nhưng new proxy vẫn cần enrollment/control plane theo implementation. Cần HA, runbook, telemetry và diễn tập sự cố.

### Bài 9 — Egress payment provider

Payment team nghĩ mTLS trong mesh tự bảo vệ API tới đối tác ngoài cluster.

**Gợi ý:** Không. Phải cấu hình egress, TLS tới đối tác, auth credentials, giới hạn outbound, audit và idempotency.

### Bài 10 — Sidecarless

Hệ thống nhiều pod nhỏ, cần mTLS phổ biến nhưng chỉ vài service cần policy L7.

**Gợi ý:** Cân nhắc node-level L4 dataplane và L7 waypoint chọn lọc nếu công cụ hỗ trợ. Đo overhead và kiểm tra failure domain, không coi sidecarless là zero cost.

## 27. Checklist quyết định áp dụng

### Nhu cầu
- [ ] Có bài toán cụ thể chứ không chỉ muốn sử dụng công nghệ mới.
- [ ] Cần workload identity/mTLS, traffic policy hoặc telemetry thống nhất ở quy mô đủ lớn.
- [ ] Đã so sánh với DNS, API gateway, CNI, NetworkPolicy, client resilience và OpenTelemetry.
- [ ] Có baseline và mục tiêu đo được.

### Kiến trúc
- [ ] Biết workload/namespace nào tham gia mesh và data path thực.
- [ ] Biết điểm thực thi L4, L7, ingress/egress và đường bypass.
- [ ] Có contract compatibility cho canary/rolling updates.
- [ ] Application vẫn xử lý business state, idempotency, transaction và authorization.
- [ ] Retry, timeout và circuit breaking có owner rõ.

### Vận hành
- [ ] Có platform owner, security reviewer, on-call và runbook.
- [ ] Có GitOps/config review, policy canary và cách rollback.
- [ ] Có quản lý certificate, trust domain, rotation và expiry.
- [ ] Có kiểm thử proxy/control-plane outage và pod lifecycle.
- [ ] Có đo p95/p99, CPU, RAM và telemetry cost dưới tải.
- [ ] Có cảnh báo và khả năng chẩn đoán policy/TLS/routing lỗi.

### Hiệu quả
- [ ] Pilot chứng minh lợi ích gắn với vấn đề ban đầu.
- [ ] Không làm tăng tail latency/error rate vượt ngân sách.
- [ ] Chi phí vận hành và phạm vi lỗi được chấp nhận.
- [ ] Có điều kiện mở rộng, tạm dừng hoặc loại bỏ mesh nếu không phù hợp.

## 28. Ghi nhớ

1. **Mesh là lớp quản lý giao tiếp, không phải lớp giải quyết nghiệp vụ.**
2. **Data plane xử lý traffic; control plane phân phối policy, endpoint và identity.**
3. **mTLS, traffic routing, policy và telemetry** là các lợi ích phổ biến, tùy implementation và data path.
4. **Kubernetes Service/DNS đã giải quyết discovery cơ bản**; không phải dùng mesh mới gọi được service theo tên.
5. **Mesh không tự bảo đảm distributed transaction, exactly-once, semantic compatibility hoặc user authorization.**
6. **Retry sai có thể nhân đôi side effect**; idempotency vẫn thuộc service sở hữu nghiệp vụ.
7. **Sidecar, sidecarless và ambient đều có chi phí**, phân bố CPU/RAM và failure domain khác nhau.
8. **Chi phí vận hành là đáng kể:** control plane, certificate, policy, proxy, telemetry và troubleshooting.
9. **Chọn áp dụng bằng bằng chứng và pilot đo được**, không dựa vào số lượng container hay xu hướng.
10. **Mức độ phức tạp phải tương xứng với yêu cầu.** Một hệ thống microservices có thể hoàn toàn đúng đắn mà không cần service mesh.
