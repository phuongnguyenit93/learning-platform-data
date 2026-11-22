# Quan sát xuyên tài khoản, khu vực và môi trường lai

## 1. Vì sao observability phân tán cần một thiết kế riêng?

Một hệ thống cloud lớn hiếm khi nằm gọn trong một account hoặc một region. Ứng dụng có thể chạy ở nhiều tài khoản theo môi trường và domain nghiệp vụ; database và object storage ở các region khác nhau; một phần workload vẫn ở data center; dịch vụ SaaS hoặc đối tác nằm ngoài tổ chức. Khi xảy ra sự cố, người vận hành cần trả lời một câu hỏi xuyên suốt: request của người dùng đã đi qua những thành phần nào, ở đâu, có lỗi hoặc chậm tại điểm nào, ai sở hữu thành phần đó và có thể truy cập evidence bằng cách nào?

Nếu mỗi account, region và môi trường lai dùng một hệ thống log/metric/trace không liên kết, đội vận hành phải chuyển console, đổi credential, ghép timestamp thủ công và khó nhìn thấy quan hệ giữa các lỗi. Ngược lại, đẩy toàn bộ telemetry về một nơi bằng quyền quản trị rộng có thể phá ranh giới bảo mật, vi phạm yêu cầu vị trí dữ liệu và tạo một điểm tập trung có sức ảnh hưởng rất lớn.

**Quan sát xuyên môi trường là bài toán liên kết tín hiệu và quyền kiểm soát, không đơn giản là gom mọi log vào một bucket.** Kiến trúc cần quyết định dữ liệu nào được tập trung, dữ liệu nào ở lại vùng nguồn, ai được đọc, collector nào có thể chuyển tiếp, context nào dùng để correlation và cách hoạt động khi central observability bị lỗi.

Trong module **CLOUD_ARCHITECTURE**, observability giúp đánh giá độ tin cậy, hiệu năng, bảo mật và chi phí của kiến trúc cloud/hybrid. Thiết kế phải kết nối các nhóm vận hành mà vẫn giữ least privilege, data residency, khả năng phục hồi và tính sẵn sàng của telemetry theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Mô hình hóa telemetry flow qua nhiều account, region và môi trường hybrid.
- Thiết kế collector, gateway và central observability theo trust boundary.
- Dùng OpenTelemetry và quy ước chung để chuẩn hóa logs, metrics, traces và resource attributes.
- Liên kết trace/request/event xuyên service mà không tạo cardinality hoặc rò rỉ dữ liệu.
- Thiết lập cross-account access, federated query, routing và quyền điều tra có kiểm soát.
- Xử lý network partition, collector outage, buffer, retry và telemetry loss.
- Thiết kế dashboard, alert, SLO và incident workflow xuyên môi trường.
- Quản trị vị trí dữ liệu, retention, chi phí và quyền truy cập đối với telemetry.

## 2. Các chiều phân tán cần quan sát

Một workload có thể phân tán theo nhiều chiều đồng thời:

| Chiều | Ví dụ | Vấn đề quan sát |
| --- | --- | --- |
| Account/project/subscription | Prod, non-prod, security, shared services, từng business unit | Identity và quyền truy cập khác nhau; cần tổng hợp mà không cấp admin toàn tổ chức |
| Region | Primary, DR, edge region, region phục vụ khách hàng | Latency liên vùng, replication lag, routing và data residency |
| Availability zone | Node, subnet, storage và database replica khác AZ | Lỗi cục bộ, correlated failure và topology |
| Hybrid location | On-premises, colocation, branch, cloud VPC/VNet | Kết nối riêng, firewall, proxy, NAT và đồng bộ thời gian |
| Runtime | VM, Kubernetes, serverless, managed database, appliance | Cách thu thập và resource identity khác nhau |
| Organization boundary | Cloud provider, SaaS, MSP, vendor | Trust, quyền truy cập và mức telemetry có thể lấy |
| Environment | Development, test, staging, production | Tránh dữ liệu/test noise che sự cố production |

### 2.1. Tách topology giám sát khỏi topology ứng dụng

Ứng dụng có thể chạy ở 20 account nhưng observability chỉ cần một số collector/gateway và một vài backend. Không nhất thiết mỗi account có một stack đầy đủ, và cũng không nhất thiết mọi telemetry phải rời khỏi account nguồn. Có thể duy trì collector nhẹ tại mỗi account/cluster, chuyển tiếp dữ liệu đã lọc đến backend trung tâm, còn dữ liệu nhạy cảm hoặc dung lượng lớn được query liên kết tại chỗ.

### 2.2. Xác định failure domain của observability

Observability phải phát hiện được sự cố ở chính nó. Hãy xác định riêng:

- Agent/collector ở host hoặc cluster.
- Gateway/relay tại account hoặc region.
- Message buffer/queue và network path.
- Central ingestion/API endpoint.
- Metrics, logs và trace storage.
- Query, alerting, dashboard và notification.
- Identity, KMS, DNS, certificate và control plane.

Nếu collector và ứng dụng dùng chung một network route hoặc credential, một sự cố/security incident có thể đồng thời làm mất telemetry. Cần có góc nhìn độc lập đủ để phát hiện việc ngừng thu thập.

## 3. Kiến trúc telemetry hub-and-spoke

Một pattern phổ biến là triển khai collector hoặc gateway ở từng trust boundary, sau đó chuyển telemetry qua kênh được xác thực tới một hoặc nhiều backend. Backend có thể tập trung, phân vùng theo region hoặc kết hợp local storage với federated query.

~~~mermaid
flowchart TB
    subgraph A["Account A / Region 1"]
        AppA["Services / VMs / Pods"] --> ColA["OTel Collector A"]
    end
    subgraph B["Account B / Region 2"]
        AppB["Services / Managed DB"] --> ColB["OTel Collector B"]
    end
    subgraph H["Hybrid / Data center"]
        AppH["VMs / Network / Legacy"] --> ColH["Local Agent / Gateway"]
    end
    ColA -->|Authenticated export| Hub["Regional telemetry gateway"]
    ColB -->|Authenticated export| Hub
    ColH -->|Private link / TLS| Hub
    Hub --> Route["Normalize / filter / route"]
    Route --> Metrics["Metrics backend"]
    Route --> Logs["Logs backend"]
    Route --> Traces["Trace backend"]
    Metrics --> UI["Central dashboards / alerting"]
    Logs --> UI
    Traces --> UI
~~~

Sơ đồ là một cấu hình tham khảo. Với yêu cầu data residency, hub có thể là một hub cho từng jurisdiction/region; central UI chỉ query metadata hoặc dữ liệu đã được phê duyệt.

### 3.1. Vai trò từng lớp

- **Instrumentation/agent:** tạo metric, log và span tại ứng dụng, host hoặc platform.
- **Local collector:** nhận telemetry tại process/host/cluster, batch, enrich context và lọc dữ liệu.
- **Regional/account gateway:** xác thực exporter, giới hạn rate, routing và buffer tạm.
- **Central backend:** lưu trữ, index, query, correlation, alert và dashboard.
- **Federation/query layer:** kết hợp dữ liệu ở nhiều backend mà không bắt buộc copy toàn bộ về một kho.

### 3.2. Vì sao không gửi trực tiếp từ mọi workload tới SaaS?

Kết nối trực tiếp có thể đơn giản ở quy mô nhỏ, nhưng khi có hàng nghìn workload sẽ khó quản lý credential, network egress, retry, schema, filtering và chi phí. Local collector tạo một điểm thực thi policy và giúp ứng dụng không phụ thuộc trực tiếp vào backend observability.

Tuy nhiên, collector trở thành dependency của telemetry. Phải quản lý capacity, HA, config rollout, credential rotation và monitoring riêng; không đặt một collector đơn lẻ làm điểm lỗi cho cả region.

## 4. Chọn central, regional hay federated observability

| Mô hình | Mô tả | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Centralized | Telemetry được chuyển về một backend tập trung | Search/correlation dễ, vận hành một nền tảng | Egress, data residency, blast radius và cardinality tập trung |
| Regional | Mỗi region có backend riêng; dashboard/alert có thể quản lý theo vùng | Locality, resilience và quyền dữ liệu rõ hơn | Truy vấn xuyên vùng và quản trị nhiều backend |
| Federated | Dữ liệu ở nhiều nguồn, query layer liên kết khi cần | Giảm copy, phù hợp data boundary | Query phức tạp, latency và availability phụ thuộc nhiều backend |
| Hybrid | Metrics/alerts trung tâm, raw logs/traces phân vùng hoặc ở lại địa phương | Cân bằng correlation và data sovereignty | Phải thiết kế rõ loại dữ liệu, retention và routing |

### 4.1. Chọn theo loại tín hiệu

- **Metrics:** thường có thể aggregate hoặc remote-write tới backend trung tâm nếu label/cardinality và residency cho phép.
- **Logs:** có thể chứa PII, secret, payload hoặc thông tin điều tra; thường cần filter, redact và routing theo data class.
- **Traces:** có thể được sample tại nguồn, giữ span context và attributes đã cho phép; payload-sensitive attributes cần loại bỏ.
- **Security events:** có thể cần lưu ở security account riêng, write-only từ workload và quyền đọc tách biệt với đội phát triển.
- **Network flow/audit logs:** có thể có volume lớn và thông tin hạ tầng; cần retention/query policy riêng.

Không cần một pipeline duy nhất cho tất cả loại telemetry. Dùng policy routing theo signal, classification, region và retention.

## 5. Chuẩn hóa context bằng OpenTelemetry

OpenTelemetry (OTel) là bộ tiêu chuẩn và công cụ mở để tạo, thu thập và export traces, metrics và logs. Nó giúp giảm phụ thuộc vào một vendor-specific agent và làm các service khác runtime có thể dùng chung semantic conventions.

### 5.1. Resource attributes và service identity

Một telemetry record cần context để trả lời “nó đến từ service nào, môi trường nào và ở đâu?”. Các thuộc tính thường hữu ích:

| Attribute | Ví dụ | Ghi chú |
| --- | --- | --- |
| service.name | checkout-api | Tên service ổn định |
| service.namespace | commerce | Business/system domain |
| service.version | 2.8.1 | Phiên bản deployment |
| deployment.environment.name | production | Môi trường |
| cloud.provider | aws, azure, gcp | Provider |
| cloud.account.id | account identifier | Có thể nhạy cảm; dùng allowlist và policy |
| cloud.region | region code | Vị trí workload |
| cloud.availability_zone | zone identifier | Hỗ trợ điều tra topology |
| k8s.cluster.name | prod-cluster-a | Cluster identity |
| host.id | stable host identity | Tránh hostname không ổn định nếu không cần |

Chỉ thêm attribute có giá trị vận hành. Không đưa email, customer ID, request body, token hoặc resource identifier nhạy cảm vào label metric.

### 5.2. Correlation context

Để nối log với trace, dùng trace ID/span ID hoặc correlation ID được tạo và truyền theo W3C Trace Context khi phù hợp. Trace ID giúp liên kết span và log; nó không phải ID người dùng và không nên được dùng làm nhãn metric có cardinality cực lớn.

Ví dụ log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-18T10:15:30Z",
  "severity": "ERROR",
  "service.name": "checkout-api",
  "deployment.environment.name": "production",
  "cloud.region": "region-a",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event.name": "payment.authorize",
  "error.type": "DependencyTimeout"
}
~~~

Đây là ví dụ schema minh họa; không log card number, authorization header hoặc dữ liệu cá nhân vào message/attribute chỉ để thuận tiện correlation.

### 5.3. Semantic conventions và naming

Đặt quy ước:

- Tên service, namespace, environment và region có danh mục chuẩn.
- Unit đo có hậu tố/metadata rõ; counter, gauge và histogram không bị trộn semantics.
- Log severity và event name thống nhất.
- Error type tách khỏi error message có thể chứa dữ liệu động.
- Dashboard và alert dùng label chung nhưng hạn chế dimension có cardinality cao.

Nếu mỗi account tự đặt prod, production, prd hoặc region theo tên tùy ý, tổng hợp dashboard sẽ phân mảnh và bỏ sót dữ liệu.

## 6. Cross-account identity và trust boundary

Observability hub thường cần đọc telemetry từ nhiều account nhưng không cần quản trị toàn bộ tài nguyên nguồn. Nên dùng identity chuyên biệt cho telemetry export và phân biệt quyền ghi telemetry với quyền query dữ liệu.

### 6.1. Tách quyền ingest và query

- Workload/collector chỉ có quyền gửi telemetry vào endpoint/tenant được chỉ định.
- Collector không cần quyền đọc mọi log hoặc truy cập database ứng dụng.
- Backend ingestion identity không mặc nhiên có quyền quản trị account nguồn.
- Analyst/incident responder có quyền query theo account, region, environment và data class.
- Security team có quyền truy cập audit/security signal theo quy trình độc lập.
- Platform admin không mặc nhiên được đọc payload customer-sensitive.

### 6.2. Cross-account role assumption

Với cloud hỗ trợ role delegation, account nguồn có thể cho phép telemetry service ở account giám sát assume một role chỉ có quyền đọc/đẩy metric/log cần thiết. Trust policy phải giới hạn principal, external ID hoặc condition phù hợp dịch vụ, session duration và resource scope. Tránh wildcard principal và quyền quản trị toàn phần.

Mô hình khác là collector ở account nguồn chủ động export qua TLS/mTLS tới endpoint trung tâm; central backend không cần assume role ngược vào account nguồn. Cách này thường đơn giản hóa quyền đọc và phù hợp network boundary, nhưng cần quản trị credential/certificate và egress.

### 6.3. Quyền JIT khi điều tra

Khi incident cần truy vấn log restricted hoặc vào account production, cấp quyền Just-in-Time theo incident/ticket, MFA, thời hạn, scope và audit. Sau điều tra, quyền tự hết hạn hoặc được thu hồi. Nếu có break-glass, phải có approver, notification, session record và review sau sự kiện.

### 6.4. Phân tách production và non-production

Không nên để người dùng non-production mặc định đọc telemetry production. Dùng tenant/project/index riêng hoặc policy theo environment. Synthetic test và load test cần label rõ để không làm méo alert production.

## 7. Kết nối hybrid và đường truyền telemetry

Môi trường hybrid thường có nhiều ranh giới mạng: data center, branch, cloud VPC/VNet, transit hub, firewall, proxy, private endpoint và Internet egress. Collector cần gửi được telemetry khi vẫn giữ segmentation và hạn chế mở inbound.

### 7.1. Ưu tiên đường truyền phù hợp

| Kiểu kết nối | Đặc điểm | Lưu ý observability |
| --- | --- | --- |
| Private connectivity | VPN site-to-site, dedicated circuit hoặc private backbone | Kiểm tra route, MTU, bandwidth, failover và DNS |
| Private service endpoint | Workload tới collector/backend qua private endpoint | Kiểm tra DNS private zone, endpoint policy và region scope |
| TLS qua Internet | Egress outbound tới endpoint được allowlist | TLS verification, proxy, egress IP và certificate lifecycle |
| Store-and-forward | Collector buffer khi mất mạng rồi gửi khi kết nối lại | Giới hạn buffer, disk pressure, replay rate và retention |
| Local backend + federation | Dữ liệu giữ trong data center/region, query từ nơi khác | Query path, identity và availability của federated source |

Thường nên để collector chủ động mở outbound connection tới gateway thay vì mở inbound từ central observability vào mọi network. Điều này giảm bề mặt tấn công và phù hợp nhiều môi trường có firewall nghiêm.

### 7.2. Network path phải có redundancy

Đường telemetry qua một VPN tunnel, một NAT gateway hoặc một gateway VM đơn lẻ có thể trở thành single point of failure. Cần đánh giá:

- Hai đường kết nối độc lập hoặc route failover.
- Capacity đủ cho log burst, trace export và metrics steady-state.
- Firewall/proxy idle timeout phù hợp với connection keepalive.
- DNS resolution ở cả private/public path.
- MTU và packet fragmentation khi truyền batch lớn.
- Egress quota và giới hạn connection.

Không để telemetry cạnh tranh không giới hạn với transaction traffic. Có thể dùng QoS, queue hoặc network policy để giới hạn telemetry burst mà vẫn giữ một luồng critical metrics/security signals.

### 7.3. Đồng bộ thời gian

Correlation giữa log, trace và audit phụ thuộc timestamp. Host/on-prem appliance có clock skew có thể làm thứ tự sự kiện sai. Dùng NTP/PTP theo yêu cầu hạ tầng, theo dõi clock offset và ghi nhận cả event time lẫn observed/ingest time khi cần.

Không thay event timestamp bằng ingest timestamp mà không lưu cả hai; độ trễ gửi telemetry có thể làm người điều tra hiểu nhầm sự cố xảy ra muộn hơn.

## 8. Resilience của collector và telemetry pipeline

Telemetry pipeline phải chịu được mất mạng, backend unavailable và burst. Mục tiêu không nhất thiết là không mất bất kỳ telemetry nào; phải phân loại tín hiệu critical, giới hạn buffer và xác định loss budget.

### 8.1. Agent và gateway high availability

- Chạy nhiều collector/gateway trên các node/AZ khác nhau nếu workload quan trọng.
- Dùng load balancing hoặc service discovery có health check.
- Tránh gateway dùng một disk hoặc credential duy nhất.
- Cập nhật cấu hình theo canary và có rollback.
- Giới hạn batch/queue để không làm cạn RAM/disk trên node ứng dụng.
- Theo dõi collector self-metrics và exporter failures.

### 8.2. Buffer, retry và backpressure

Khi backend tạm thời không khả dụng, collector có thể retry và buffer. Cần xác định:

- Memory queue hay persistent queue; dung lượng giới hạn bao nhiêu?
- Retry có exponential backoff và jitter không?
- Khi queue đầy, drop newest, drop oldest, block producer hay shed low-priority signals?
- Có nguy cơ app bị chậm vì telemetry exporter blocking không?
- Replay sau outage có tạo ingest storm hoặc phí tăng đột biến không?
- Log/trace/metric có retention khác nhau và được ưu tiên ra sao?

Không buffer vô hạn. Persistent queue giúp sống qua restart nhưng cần disk encryption, quota, cleanup và theo dõi. Queue cạn dung lượng phải phát cảnh báo độc lập.

### 8.3. At-least-once và duplicate

Retry khi không rõ backend đã nhận batch hay chưa có thể gửi lại cùng telemetry. Pipeline phải chấp nhận duplicate hoặc hỗ trợ deduplication theo semantics backend. Không giả định mọi exporter/receiver cung cấp exactly-once delivery.

### 8.4. Out-of-order và late arrival

Network partition và buffering có thể khiến telemetry tới muộn hoặc sai thứ tự. Metrics backend cần xử lý timestamp, temporality và late sample theo quy định. Log query nên cho phép sort theo event time và thấy ingest delay. Trace có thể thiếu span do một collector path lỗi; điều tra viên cần biết trace incomplete chứ không kết luận service đã bỏ qua span.

### 8.5. Telemetry loss budget

Đặt mục tiêu theo tín hiệu:

| Signal | Mức ưu tiên tham khảo | Chính sách khi thiếu dung lượng |
| --- | --- | --- |
| Security/audit events | Rất cao | Gửi sang kênh bền vững/ưu tiên riêng; alert khi không giao được |
| RED metrics/SLO metrics | Cao | Giữ aggregation và buffer ngắn; theo dõi scrape/export gap |
| Error logs | Cao | Sampling có điều kiện, giữ error class và correlation |
| Debug logs | Thấp hơn | Có thể drop/sample khi áp lực |
| Detailed traces | Theo tail-sampling policy | Giảm sampling có kiểm soát, giữ error/slow traces |

Đây là hướng ưu tiên, không thay yêu cầu pháp lý hoặc policy tổ chức. Audit events có thể cần một pipeline chuyên dụng thay vì collector observability chung.

## 9. Cardinality, volume và chất lượng telemetry

Cross-account observability có thể tạo lượng dữ liệu rất lớn. Mỗi account/cluster/service/route/tenant thêm dimension; nếu dùng identifier động làm metric label, số time series có thể tăng không kiểm soát.

### 9.1. Cardinality

Cardinality là số tổ hợp giá trị label/attribute tạo ra series hoặc index dimension. Những thuộc tính như request ID, user ID, session ID, URL đầy đủ và exception message thường có cardinality cao.

Best practice:

- Dùng route template như /orders/{id}, không dùng URL chứa ID cụ thể.
- Không đưa trace ID/request ID vào metric labels; giữ chúng trong log/trace context.
- Dùng error type/status class thay vì raw exception text.
- Giới hạn tenant dimension hoặc dùng aggregation theo tier khi tenant count lớn.
- Theo dõi active series, index size, label churn và dropped samples.
- Có cardinality budget cho instrumentation mới.

### 9.2. Normalize nhưng không làm mất nguồn gốc

Collector có thể đổi attribute name, map severity hoặc normalize region/environment. Giữ source identity và original context cần thiết để truy ngược nguồn, đồng thời có transform version để biết dữ liệu đã được biến đổi ra sao.

Không ghi đè field nguồn nếu việc đó làm mất evidence. Với normalization quan trọng, giữ source attribute trong namespace riêng và canonical attribute cho query.

### 9.3. Sampling traces

Head sampling quyết định lấy trace từ đầu request; tail sampling quyết định sau khi quan sát trace hoặc một phần span, có thể ưu tiên lỗi và request chậm. Tail sampling cần state/buffer và thường yêu cầu routing các span cùng trace về đúng collector/sampler instance.

Trong môi trường nhiều region, sampling policy có thể được quản lý chung nhưng thực thi tại regional collector để tránh gửi mọi span thô ra ngoài. Giữ trace ID xuyên service, cấu hình policy version và theo dõi sampling rate thực tế.

Không so sánh trace volume giữa hai region nếu sampling rate khác nhau mà không biết metadata về policy.

### 9.4. Metric aggregation

Pre-aggregation ở nguồn giảm network và storage nhưng có thể mất khả năng drill-down. Chọn metric histogram và bucket phù hợp SLO; tránh tính average của average khi không có weight. Khi aggregate cross-account, phân biệt counter reset, temporality, unit và scrape interval.

## 10. Correlation xuyên service, account và region

Một request có thể đi qua browser, edge, API gateway, service A, queue, worker B, database C và SaaS provider. Để điều tra end-to-end, cần correlation context nhất quán và quy ước truyền qua cả synchronous lẫn asynchronous boundary.

### 10.1. Distributed trace

Trace gồm các span liên kết bằng parent/child hoặc span links. Khi queue/event tạo asynchronous work, consumer có thể dùng trace context được inject trong message header hoặc tạo trace mới liên kết bằng span link theo mô hình phù hợp.

~~~mermaid
sequenceDiagram
    participant U as User region A
    participant API as API account A
    participant Q as Queue region A
    participant W as Worker account B
    participant DB as Database region B
    U->>API: HTTP request + trace context
    API->>Q: Publish message + propagated context
    API-->>U: Accepted
    Q->>W: Deliver message
    W->>DB: Query/update
    DB-->>W: Result
    W-->>Q: Acknowledge
~~~

Với async processing, trace ban đầu có thể kết thúc trước khi job hoàn tất. Dùng span link hoặc business operation ID để liên kết hai giai đoạn mà không kéo dài một trace vô hạn.

### 10.2. Propagation qua trust boundary

Không tin trace header do client ngoài tổ chức gửi mà không validation. External caller có thể tạo trace ID tùy ý hoặc dùng baggage chứa dữ liệu nhạy cảm. Gateway có thể tạo trace mới và chỉ giữ một số context đã allowlist.

Baggage truyền theo request có thể bị gửi sang nhiều service/vendor. Chỉ đưa metadata không nhạy cảm, giới hạn kích thước và không dùng nó làm nơi truyền token, email hoặc customer profile.

### 10.3. Correlation khi vendor không hỗ trợ trace

Nếu SaaS hoặc legacy service không hỗ trợ W3C trace context, ghi span bao quanh outbound call ở service gọi, capture operation name, endpoint class, status, duration và request/correlation ID do mình quản lý. Không ghi raw payload hoặc secret. Với batch, dùng job ID và event ID được tạo ở hệ thống nguồn.

### 10.4. Trace continuity và sampling gap

Một trace có thể thiếu span do sampling khác nhau, context bị mất tại queue hoặc exporter lỗi. Gắn sampling decision/trace state metadata và theo dõi missing-span rate nếu có thể. Dashboard cần cho biết trace incomplete hoặc một service chưa instrumented, tránh kết luận nhầm rằng downstream không được gọi.

## 11. Dashboard, alert và SLO xuyên môi trường

Central observability có ích khi người vận hành chuyển được từ triệu chứng của người dùng tới service, dependency và failure domain. Dashboard nên tổ chức theo hành trình nghiệp vụ, sau đó drill-down đến region/account/instance.

### 11.1. Tổ chức dashboard theo ba cấp

| Cấp | Câu hỏi | Thành phần |
| --- | --- | --- |
| Global/business | Hành trình quan trọng có hoạt động không? Region nào đang suy giảm? | SLO, availability, latency, traffic, error và trạng thái DR |
| Service/domain | Service hoặc business domain nào gây ảnh hưởng? | RED metrics, dependency, queue, database, deployment |
| Resource/diagnostic | Thành phần cụ thể nào lỗi? | Host/Pod, network path, trace, log, event và config change |

Nên có filter chuẩn cho environment, account, region, AZ, cluster, namespace, service và version. Filter phải phản ánh nguồn dữ liệu thực tế; không tạo dropdown có hàng triệu giá trị tenant hoặc request ID.

### 11.2. SLO và error budget

SLO nên đo trải nghiệm hoặc kết quả nghiệp vụ. Với một API, có thể theo dõi tỷ lệ request thành công dưới ngưỡng latency; với pipeline async, đo tỷ lệ job hoàn tất trước deadline hoặc queue age.

Khi tổng hợp nhiều region:

- Xác định denominator và traffic weighting rõ ràng.
- Không để region ít traffic bị che bởi region lớn nếu region nhỏ có khách hàng critical.
- Có SLO riêng cho từng jurisdiction/tenant class khi yêu cầu khác nhau.
- Phân biệt lỗi do client, dependency và platform nhưng không loại lỗi khỏi SLO nếu người dùng vẫn chịu ảnh hưởng.
- Theo dõi telemetry coverage để biết SLO measurement có thiếu dữ liệu không.

Error budget burn rate có thể tạo alert sớm khi SLO tiêu hao nhanh. Một dashboard tổng hợp tốt cần cho phép chuyển từ global burn rate đến region/service mà không thay đổi định nghĩa SLI.

### 11.3. Alert routing

| Điều kiện | Route gợi ý | Nội dung cần kèm |
| --- | --- | --- |
| SLO burn rate cao | On-call service owner/incident channel | Service, region, impact, burn window và runbook |
| Một region mất telemetry | Observability/platform team | Collector health, last seen, network path và affected accounts |
| Security/audit event nghiêm trọng | Security operations | Principal, resource, action, account và evidence reference |
| Replication/queue lag tăng | Data/platform owner | Lag, age, partition, downstream health và RPO/SLA |
| Cardinality/ingestion cost tăng | Observability owner | Source, metric family, account, label và trend |

Alert phải có owner, severity, deduplication, inhibition/suppression, escalation và runbook. Không gửi một notification cho mỗi instance khi một lỗi region ảnh hưởng hàng nghìn resource; group theo service/failure domain và giữ link tới chi tiết.

### 11.4. Alert khi telemetry biến mất

“Không có metric” không đồng nghĩa “không có lỗi”. Tạo heartbeat hoặc expected-source inventory để phát hiện account/region/service không gửi telemetry. Monitor collector self-metrics, last successful export, dropped records, queue utilization và backend ingestion delay.

Có thể đặt canary telemetry record định kỳ từ từng account/region và kiểm tra nó xuất hiện trong backend đúng SLA. Cần monitor độc lập với chính backend đang được kiểm tra để tránh mất cả dữ liệu lẫn cảnh báo.

### 11.5. Cross-region incident correlation

Trong incident đa vùng, dùng một incident ID chung, chuẩn hóa timestamp, service identity và deployment version. Correlate alert với change event, network event, identity event và deployment timeline. Global dashboard cần cho thấy region nào là nguồn dữ liệu, không chỉ gộp tất cả thành một service label.

## 12. Data governance và privacy cho telemetry

Telemetry thường bị xem là dữ liệu kỹ thuật ít nhạy cảm, nhưng log, trace và metric có thể chứa thông tin cá nhân, bí mật thương mại, topology nội bộ hoặc credential. Khi chuyển telemetry xuyên region/account, nó có thể chịu yêu cầu residency, retention và access tương tự dữ liệu nghiệp vụ.

### 12.1. Classification theo signal và field

Phân loại telemetry theo:

- Operational metrics ít nhạy cảm.
- Security/audit events.
- Logs có identifier, URL, query hoặc payload.
- Traces có attributes/baggage và dependency information.
- Network flow, IP, DNS query và host inventory.
- Crash dump, memory dump hoặc diagnostic bundle.

Không chỉ gắn một nhãn chung cho index. Field hoặc event cụ thể có thể cần masking, restricted index hoặc local-only retention.

### 12.2. Redaction tại nguồn

Redact ở application instrumentation hoặc local collector trước khi export. Dùng allowlist attribute, transform processor và schema validation. Ưu tiên không thu thập payload hơn là nhận toàn bộ rồi hy vọng xóa sau.

Các trường cần đặc biệt kiểm tra:

- Authorization, cookie, session token và API key.
- Email, phone, address, account/customer identifier.
- Payment, health hoặc authentication data.
- Query parameter, SQL literal và message body.
- Internal hostname/IP hoặc topology nếu được phân loại restricted.

Redaction regex có thể bỏ sót encoding hoặc cấu trúc lồng nhau; cần test với dữ liệu đại diện và secret scanning. Không sửa dữ liệu forensic cần thiết mà không có policy; security log phải có đường lưu riêng và quyền hạn hẹp.

### 12.3. Data residency và regional retention

Nếu log/trace chứa dữ liệu bị giới hạn địa lý, regional collector/backend phải lưu và query trong boundary được phép. Central control plane có thể chỉ giữ aggregate đã duyệt, source metadata tối thiểu hoặc alert summary không chứa payload. Hãy đánh giá cả backup, index replica, query cache, support access và telemetry của chính observability vendor.

### 12.4. Retention và deletion

Retention nên khác nhau theo tín hiệu và use case. Metrics đã aggregate có thể giữ lâu để trend; debug logs thường giữ ngắn; security audit theo policy riêng; traces sampling có thể giữ theo incident/debug window.

Khi có yêu cầu xóa hoặc tenant offboarding, cần tìm cả index, replica, export, archive, cache và backup theo chính sách. Ghi trạng thái và evidence nhưng không lưu lại payload đã bị xóa trong ticket/audit.

## 13. Vận hành cấu hình và instrumentation ở quy mô lớn

Khi có nhiều account/region, collector config và instrumentation version dễ lệch nhau. Một policy central giúp đồng nhất nhưng triển khai sai có thể làm ngừng telemetry trên toàn bộ fleet.

### 13.1. Quản lý config

- Version hóa collector pipeline, receivers, processors, exporters và routing rules.
- Quản lý endpoint/credential qua secret manager, không nhúng vào config plain text.
- Dùng template theo account/region/runtime nhưng có override được kiểm soát.
- Validate schema/config trước deploy và chạy canary ở một nhóm nhỏ.
- Giám sát config version thực tế đang chạy trên từng collector.
- Có rollback tự động khi export error, dropped data hoặc resource usage vượt ngưỡng.

### 13.2. Phân phối instrumentation

Tạo thư viện hoặc base image dùng chung cho service metadata, trace propagation, log correlation và metric naming. Cho phép exception có lý do; không buộc mọi legacy application phải nâng instrumentation cùng lúc. Theo dõi coverage theo service criticality và runtime.

### 13.3. Collector upgrades

Nâng collector cần chú ý receiver/exporter compatibility, memory limits, queue persistence, schema transformation và version skew. Rollout theo ring: lab, non-production, một nhóm production, rồi mở rộng. Khi một collector version có lỗi, rollback không nên làm mất persistent queue.

### 13.4. Observability of observability

Theo dõi:

- Collector process uptime, CPU, memory và restart.
- Received/exported/refused/dropped spans, metrics và logs.
- Export queue size, retry, send failures và persistent storage.
- Backend ingest delay, rejected samples và index/write failures.
- Query latency, dashboard availability và alert notification delay.
- Coverage/heartbeat theo account, region, cluster và environment.

Các metric này cần được gửi tới một monitoring path độc lập hoặc có fallback, nếu không sự cố ở chính observability sẽ không được phát hiện.

## 14. Chi phí và tối ưu hiệu quả telemetry

Chi phí observability thường phụ thuộc volume ingest, retention, cardinality, query, replica, egress và số user/license. Gom nhiều account vào một backend có thể tăng hiệu quả vận hành nhưng cũng làm cost tập trung và khó quy trách nhiệm.

### 14.1. Cost allocation

Gắn nguồn telemetry với account, region, service, environment và owner để phân bổ:

- Ingest bytes hoặc samples theo loại signal.
- Active time series và cardinality contribution.
- Log retention/storage và index footprint.
- Trace volume/sampling rate.
- Cross-region transfer và gateway processing.
- Query bytes scanned, dashboard/API usage và alert volume.

Không dùng customer ID hoặc request ID làm cost label metric. Gán cost theo resource/service group có cardinality kiểm soát.

### 14.2. Tối ưu theo signal

- Giảm debug log trong production, tăng tạm thời khi incident có phê duyệt.
- Dùng structured log và redact trước export.
- Aggregate metric ở nguồn khi không cần raw high-frequency sample.
- Tail-sample traces để giữ error/slow trace và giảm trace bình thường.
- Tách security/audit logs khỏi debug logs để có retention và access phù hợp.
- Áp lifecycle cho archive log và query theo nhu cầu thực.
- Loại bỏ metric không có consumer hoặc không hỗ trợ quyết định vận hành.

### 14.3. Không tiết kiệm bằng cách bỏ tín hiệu quan trọng

Giảm sampling hoặc retention có thể làm mất bằng chứng điều tra. Xác định critical signal, minimum retention và required coverage trước khi tối ưu cost. Trong incident, temporary debug mode cần expiry tự động để không duy trì volume lớn sau khi kết thúc.

## 15. Ví dụ tổng thể: observability cho nền tảng cloud và data center

Một nền tảng thương mại điện tử có account production riêng cho từng business domain, một security account, hai region cloud và một cụm legacy tại data center. Checkout chạy trên Kubernetes; order database là managed service; worker xử lý event qua queue; data center kết nối bằng private circuit; một đối tác SaaS cung cấp payment.

### 15.1. Thiết kế luồng telemetry

~~~mermaid
flowchart TB
    subgraph C1["Cloud account: checkout / region A"]
        K1["Kubernetes + API"] --> O1["OTel Daemon/Agent"]
        O1 --> G1["Regional collector gateway"]
    end
    subgraph C2["Cloud account: worker / region B"]
        K2["Workers + Queue"] --> O2["OTel Collector"]
        O2 --> G2["Regional collector gateway"]
    end
    subgraph DC["Data center"]
        Legacy["Legacy application / network"] --> Agent["Local collector"]
    end
    SaaS["Payment SaaS"] --> APITrace["Outbound client spans"]
    G1 --> Hub["Observability hub"]
    G2 --> Hub
    Agent --> Hub
    APITrace --> Hub
    Hub --> Policy["Normalize / redact / route"]
    Policy --> Metrics["Metrics store"]
    Policy --> Logs["Regional log stores"]
    Policy --> Traces["Trace store"]
    Policy --> Sec["Security account audit store"]
    Metrics --> Dash["Federated dashboards / alerting"]
    Logs --> Dash
    Traces --> Dash
    Sec --> Dash
~~~

### 15.2. Các quyết định quan trọng

- Checkout và worker có collector theo cluster/account, gửi qua authenticated gateway.
- Resource attributes giữ service, environment, account và region để filter.
- Database metrics lấy từ telemetry dịch vụ managed, không đòi cài agent vào host provider quản lý.
- Private circuit là đường chính từ data center; outbound TLS qua đường dự phòng được kiểm soát.
- Trace context theo W3C được truyền qua API và queue; outbound payment call ghi span nhưng không log payment payload.
- Security audit được route tới security account với quyền write-only từ workload.
- Raw logs có thể lưu tại regional backend; global dashboard query theo policy hoặc chỉ nhận aggregate đã duyệt.
- Synthetic transaction từ từng region kiểm tra toàn bộ journey và cảnh báo khi collector/backend ngừng nhận dữ liệu.

### 15.3. Khi gateway region A mất

Collector tại account nguồn giữ buffer trong giới hạn. App vẫn phục vụ độc lập, không chờ exporter đồng bộ. Heartbeat của gateway mất sẽ tạo alert qua monitoring path phụ. Khi gateway phục hồi, export replay theo rate limit; pipeline kiểm tra duplicate/late arrival và theo dõi ingest delay. Nếu buffer gần đầy, ưu tiên security events và SLO metrics theo policy, giảm debug logs và phát cảnh báo telemetry loss.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng một admin credential cho mọi account | Blast radius lớn và khó audit | Per-account identity, scoped role và JIT |
| Gửi toàn bộ logs về một region | Có thể vi phạm residency hoặc lộ PII | Redaction, regional backend và policy routing |
| Không chuẩn hóa service/region labels | Dashboard thiếu nhất quán, khó correlation | Semantic conventions và registry |
| Dùng customer/request ID làm metric label | Cardinality và chi phí bùng nổ | Giữ ID trong log/trace, dùng aggregate label |
| Collector đồng bộ với app request path | Backend observability lỗi làm app chậm | Async export, bounded queue và timeout |
| Không monitor collector | Mất telemetry mà không biết | Heartbeat, self-metrics và independent monitor |
| Retry không giới hạn | Memory/disk cạn, ingest storm khi hồi phục | Backoff, cap, queue limit và replay throttling |
| Xem trace thiếu span là bằng chứng service không được gọi | Điều tra sai nguyên nhân | Theo dõi sampling, propagation và export gaps |
| Alert từng instance | Notification storm | Group theo service/failure domain và deduplicate |
| Không phân tách ingest/query permission | Collector hoặc analyst có quyền quá rộng | Separate identity và policy theo role/data class |
| Không có cost attribution | Một account làm tăng bill toàn nền tảng | Source tags, volume dashboard và budget |
| Coi central backend là điểm duy nhất | Mất dashboard/alert khi central outage | Regional fallback và monitoring độc lập |

## 17. Bài thực hành: quan sát một dịch vụ hybrid đa region

Một nền tảng đặt hàng chạy ở hai cloud region, ba account production và một data center. API checkout, worker xử lý queue, database managed, network gateway và một SaaS payment provider đều là một phần của hành trình người dùng. Trong giờ cao điểm, checkout p99 tăng, queue age ở region B vượt SLA, nhưng dashboard trung tâm không có log mới từ data center.

**Yêu cầu bài làm:**

1. Vẽ telemetry topology theo account/region/on-prem; chỉ rõ agent, collector, gateway, backend và federation layer.
2. Chọn centralized, regional hay hybrid observability cho metrics, logs, traces và security audit.
3. Định nghĩa resource attributes và naming conventions để lọc theo service, account, region, environment và version.
4. Thiết kế cross-account identity cho ingest và query; nêu quyền nào collector không cần có.
5. Mô tả trace propagation qua HTTP, queue và SaaS call; xử lý khi đối tác không hỗ trợ trace context.
6. Xác định nguyên nhân có thể khiến data center không có log mới: agent, network, proxy, clock, buffer hay backend; thiết kế heartbeat.
7. Đề xuất buffer/retry/backpressure và telemetry loss budget khi gateway region A/B mất kết nối.
8. Chọn sampling/cardinality controls và chỉ ra attribute không được dùng làm metric label.
9. Thiết kế dashboard SLO, queue age, replication/dependency health và alert routing.
10. Đánh giá data residency, PII redaction, retention và quyền support của observability vendor.
11. Lập bảng cost allocation và đề xuất cách giảm debug volume mà vẫn giữ security evidence.
12. Xây dựng kế hoạch kiểm thử outage collector, mất private circuit, backend reject, credential expiry và config rollout lỗi.

### Gợi ý đánh giá

Một thiết kế tốt có local collector và gateway chịu trách nhiệm lọc/chuẩn hóa tại trust boundary; app không bị block khi telemetry backend lỗi; heartbeat phát hiện nguồn mất dữ liệu; security audit có pipeline và quyền riêng. Trace ID liên kết log/span nhưng không biến thành metric label; queue age và SLO được tổng hợp theo region mà không che region ít traffic.

Bài làm phải chỉ rõ data nào được gửi đi đâu, qua identity nào, giữ bao lâu và ai được query. Khi gateway mất, có buffer hữu hạn, replay throttling và telemetry loss policy. Central dashboard không được là cách duy nhất để phát hiện central observability outage.

## 18. Checklist trước khi đưa observability đa môi trường vào production

- [ ] Có inventory account, region, AZ, on-prem, SaaS và owner của từng workload.
- [ ] Telemetry topology có collector/gateway tại trust boundary và failure domain rõ.
- [ ] Chọn centralized/regional/federated theo từng signal, residency và cost.
- [ ] Resource attributes/naming conventions thống nhất cho service, environment, account và region.
- [ ] Trace/log correlation và context propagation qua HTTP, queue và vendor đã được kiểm thử.
- [ ] Cross-account ingest/query identity tách biệt; không dùng admin credential chung.
- [ ] JIT/break-glass access có MFA, scope, expiry và audit.
- [ ] Network path có redundancy, TLS/mTLS, DNS và egress policy.
- [ ] Collector/backend có HA, bounded buffer, retry/backoff và backpressure.
- [ ] Có monitoring độc lập cho collector heartbeat, export failure, queue full và ingest delay.
- [ ] Cardinality budget, sampling policy và duplicate/late telemetry behavior được xác định.
- [ ] Logs/traces/metrics đã redacted; secret và PII không bị export ngoài policy.
- [ ] Regional retention, backup, query cache và support access được đánh giá.
- [ ] SLO/dashboard/alert grouping có owner, severity, escalation và runbook.
- [ ] Cost allocation theo account/service/signal và budget alert đã được thiết lập.
- [ ] Config/instrumentation version hóa, validate, canary, rollback và drift detection.
- [ ] Có kiểm thử collector outage, network partition, backend outage và replay storm.
- [ ] Có tài liệu incident workflow xuyên nhóm và evidence preservation.
- [ ] Telemetry coverage được đánh giá theo mức criticality của service.
- [ ] Có định kỳ review vendor, retention, sampling và cost để tránh drift.

**Ghi nhớ:** Quan sát xuyên tài khoản, khu vực và môi trường lai cần context nhất quán, telemetry flow có kiểm soát và quyền truy cập phù hợp từng trust boundary. Dùng collector/gateway tại nguồn, chuẩn hóa OpenTelemetry, liên kết trace/log/event và chọn tập trung, regional hoặc federation theo data class. Pipeline phải chịu được network/backend outage bằng buffer hữu hạn, retry có giới hạn và monitoring độc lập. Hãy đo SLO và coverage end-to-end, đồng thời kiểm soát privacy, cardinality, retention và cost để observability giúp khôi phục hệ thống mà không trở thành một rủi ro mới.
