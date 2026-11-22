# Dự toán nhiều phương án kiến trúc và phân tích độ nhạy

## 1. Vì sao phải dự toán nhiều phương án?

Một yêu cầu nghiệp vụ thường có nhiều cách triển khai trên cloud. Một API có thể chạy trên VM, container được quản lý hoặc serverless; dữ liệu có thể đặt trên database quan hệ đa vùng, database một vùng kèm bản sao phục hồi, hoặc mô hình tách write store và read projection. Mỗi phương án tạo ra chi phí khác nhau về compute, lưu trữ, network, license, vận hành, độ sẵn sàng và phục hồi.

Chọn phương án chỉ dựa trên giá compute theo giờ dễ dẫn tới quyết định sai. Một dịch vụ có compute rẻ nhưng cần nhiều node dự phòng, NAT gateway, cross-region replication, log ingestion và nhân sự trực vận hành có thể đắt hơn đáng kể. Ngược lại, phương án có đơn giá cao hơn có thể giảm số instance, thời gian quản trị, downtime hoặc công sức khắc phục sự cố.

**Dự toán nhiều phương án kiến trúc** là quá trình xây dựng các mô hình chi phí theo cùng giả định về workload, thời gian và mức dịch vụ, sau đó so sánh tổng chi phí sở hữu (TCO), chi phí trên đơn vị nghiệp vụ, rủi ro và độ nhạy với các biến số quan trọng.

**Phân tích độ nhạy (sensitivity analysis)** cho biết kết quả thay đổi thế nào khi một hoặc nhiều giả định thay đổi: lưu lượng tăng, dữ liệu lưu lâu hơn, giá egress tăng, tỷ lệ cache hit giảm, cần thêm vùng dự phòng hoặc chi phí vận hành cao hơn dự kiến.

Trong module **CLOUD_ARCHITECTURE**, dự toán là một phần của quyết định giữa network, compute, data, resilience, security và operations. Mục tiêu là cân bằng **chi phí, độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng và tính bền vững** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ cần phục vụ tìm kiếm, tạo booking, thanh toán, gửi thông báo và báo cáo. Nhóm kiến trúc xem xét ba phương án: VM/container tự quản lý, container platform được quản lý và serverless/event-driven. Không phương án nào mặc định rẻ nhất; kết quả phụ thuộc traffic profile, thời gian xử lý, mức dự phòng và năng lực đội vận hành.

## 2. Bắt đầu bằng baseline chung

So sánh chỉ có ý nghĩa khi các phương án đáp ứng cùng một nhu cầu. Trước khi điền đơn giá, hãy thống nhất baseline:

| Nhóm giả định | Nội dung cần chốt |
| --- | --- |
| Workload | Request/giây trung bình và đỉnh, concurrency, kích thước request/response, CPU và memory per operation |
| Dữ liệu | Số record, dung lượng ban đầu, tốc độ tăng, retention, backup, replication và tốc độ đọc/ghi |
| Network | Ingress/egress, cross-zone/region traffic, CDN/cache hit, NAT và private endpoint |
| Availability | SLO, số zone/region, failover capacity, RTO/RPO |
| Security | Encryption, key management, audit, private networking, security tooling và retention |
| Operations | Số môi trường, số release, on-call, patching, backup test, incident và support |
| Commercial | Region, currency, billing period, discount/commitment, license và support plan |
| Time horizon | 12/24/36 tháng, ngày bắt đầu, ramp-up và thời gian đạt tải ổn định |

Không lấy workload trung bình của phương án A so với peak của phương án B. Baseline cần nêu cả mức trung bình, peak, burst duration và tỷ lệ sử dụng trong ngày/tuần.

### 2.1. Workload profile

Một profile có thể mô tả:

~~~text
monthly_requests = 120,000,000
average_rps = monthly_requests / seconds_in_month
peak_rps = 8 * average_rps
average_request_compute_ms = 35
response_size_kb = 12
monthly_egress_gb = estimated_from_response_volume
data_growth_gb_per_month = 120
retention_months = 24
~~~

Giá trị trong ví dụ là giả định học tập. Trong dự án thật, lấy số liệu từ telemetry, load test, billing và business forecast; ghi rõ nguồn, thời gian quan sát, mức tin cậy và cách ngoại suy.

### 2.2. Không dùng một con số trung bình để mô tả mọi tải

Hai hệ thống có cùng 100 triệu request/tháng nhưng có thể có chi phí rất khác:

- Hệ thống A tải ổn định 24/7.
- Hệ thống B dồn phần lớn request vào hai khung giờ, cần burst capacity.
- Hệ thống C có ít request nhưng mỗi request chạy query nặng và giữ connection lâu.

Serverless có thể phù hợp với workload burst và idle dài; container/VM có thể hiệu quả với tải đều và predictable. Kết luận cần dựa trên profile đầy đủ, không chỉ request count.

## 3. Xác định phạm vi TCO

TCO (Total Cost of Ownership) bao gồm chi phí để đưa giải pháp vào vận hành và duy trì trong khoảng thời gian phân tích. Phạm vi có thể rộng hơn cloud invoice.

| Nhóm chi phí | Hạng mục điển hình |
| --- | --- |
| Compute | VM, container node, serverless invocation/duration, accelerator, autoscaling headroom |
| Data | Database instance, storage, IOPS, backup, snapshot, replication, cache, search/index |
| Network | Load balancer, NAT, private endpoint, CDN, DNS, egress, cross-zone/region transfer |
| Platform | Kubernetes control/worker, service mesh, registry, secrets, observability service |
| Security | KMS operations, WAF, vulnerability scanning, SIEM, audit retention, security support |
| Software | OS/database license, commercial middleware, monitoring agent, support subscription |
| Operations | Engineering/on-call time, patching, upgrade, capacity management, incident response |
| Delivery | CI/CD minutes, artifact storage, test environments, preview environments |
| Resilience | Warm standby, replica, multi-region capacity, DR exercise, backup restore testing |
| Migration | Refactor, data transfer, parallel run, dual-write, training and cutover |

### 3.1. Direct cost và indirect cost

Direct cost thường xuất hiện trực tiếp trên hóa đơn hoặc hợp đồng. Indirect cost có thể là thời gian của kỹ sư, chi phí phối hợp, thời gian downtime, công sức audit hoặc chi phí migration.

Không cộng mọi khoản một cách tùy tiện. Hãy quy định rõ:

- Khoản nào được tính vào TCO?
- Nhân công được tính theo loaded rate nào?
- Chi phí chung được phân bổ theo tỷ lệ nào?
- Downtime được tính theo lost contribution margin, penalty hay chỉ mô tả định tính?
- Chi phí one-time và recurring được tách thế nào?

Tách chi phí đã biết, chi phí ước tính và rủi ro khó lượng hóa. Điều này giúp người ra quyết định hiểu phần nào chắc chắn và phần nào phụ thuộc giả định.

## 4. Mô hình chi phí theo driver

Đừng lập dự toán bằng một tổng số duy nhất ngay từ đầu. Hãy phân rã chi phí theo driver có thể đo và dự báo.

Một mô hình tổng quát:

~~~text
TCO(horizon) =
    one_time_cost
  + recurring_fixed_cost
  + variable_cost(workload)
  + operations_cost
  + resilience_cost
  + risk_allowance
  - applicable_credits_or_discounts
~~~

Trong đó:

- One-time cost: migration, setup, training, initial data transfer.
- Fixed cost: reserved capacity, license, minimum cluster/node, support.
- Variable cost: request, compute duration, storage growth, I/O, egress.
- Operations cost: nhân lực, bảo trì, nâng cấp, kiểm thử khôi phục.
- Resilience cost: replica, standby, backup, capacity cho failover.
- Risk allowance: khoản dự phòng theo phương pháp được tổ chức chấp thuận; không dùng để che giấu thiếu dữ liệu.

### 4.1. Cost driver tree

~~~mermaid
flowchart TD
    TCO["Total Cost of Ownership"]
    TCO --> FIX["Fixed / committed"]
    TCO --> VAR["Usage-based"]
    TCO --> OPS["Operations"]
    TCO --> RES["Resilience"]
    TCO --> ONE["One-time"]
    FIX --> NODE["Baseline compute / license"]
    VAR --> REQ["Requests / compute time"]
    VAR --> DATA["Storage / IOPS / egress"]
    OPS --> ENG["Engineering / on-call / support"]
    RES --> DR["Replica / backup / standby"]
    ONE --> MIG["Migration / parallel run"]
~~~

Sơ đồ cho thấy các nhóm driver, không phải cấu trúc hóa đơn của một provider. Mỗi driver cần owner và nguồn số liệu.

## 5. Tính chi phí compute theo mô hình kiến trúc

Các mô hình compute có đơn vị tính khác nhau:

| Mô hình | Driver chi phí thường gặp | Cần đưa vào dự toán |
| --- | --- | --- |
| VM | Instance hours, size, OS/license, disk | Số instance tối thiểu, autoscaling, standby, patching |
| Container trên node pool | Node hours, CPU/memory, cluster fee tùy nền tảng | Daemon/system overhead, bin packing, idle node, upgrade |
| Managed container/serverless container | vCPU/memory duration, request hoặc capacity | Minimum instances, cold start strategy, concurrency |
| Function/serverless | Invocation, execution duration, allocated memory/CPU, provisioned concurrency | Retry, timeout, cold start, event volume, logging |
| Managed application platform | Instance/time, request, feature tier | Platform fee, autoscaling bounds, integration charges |

### 5.1. Tính utilization thay vì chỉ cộng số node

Giả sử một node có 8 vCPU nhưng workload chỉ dùng trung bình 2 vCPU. Không phải lúc nào có thể giảm node theo tỷ lệ 75% vì cần headroom cho peak, memory, replica placement, failure và system daemon.

Một ước tính đơn giản:

~~~text
required_nodes =
  ceil(peak_resource_demand / usable_resource_per_node)
~~~

Usable resource phải trừ phần dành cho OS, kube/system services, safety headroom và bin packing. Với HA nhiều zone, còn phải xác định năng lực còn lại khi mất một zone; không được giả định tất cả node đều có thể được sử dụng ở trạng thái bình thường và lúc failover cùng một cách.

### 5.2. Autoscaling không làm compute miễn phí

Autoscaling có thể giảm chi phí khi tải thấp, nhưng:

- Scale-out có độ trễ nên vẫn cần baseline capacity.
- Scale-in có thể bị hạn chế bởi disruption budget hoặc workload stateful.
- Peak burst có thể giữ node lâu hơn do cooldown.
- Nhiều replica có thể làm tăng connection tới database/cache.
- Scale theo CPU có thể không phản ánh queue latency hoặc request cost.

Dự toán cần mô phỏng capacity theo thời gian hoặc dùng utilization distribution, không lấy peak node count nhân toàn bộ số giờ nếu autoscaling hoạt động tốt; cũng không lấy average utilization nếu SLO yêu cầu capacity cao hơn trong peak.

## 6. Tính chi phí storage, database và backup

Chi phí dữ liệu có nhiều thành phần ngoài dung lượng primary:

~~~text
data_cost =
    primary_storage
  + replicas
  + backup_storage
  + snapshot_retention
  + IOPS_or_throughput
  + read/write_requests
  + data_transfer
~~~

### 6.1. Dự báo tăng trưởng

~~~text
stored_data(month_n) =
  initial_data + monthly_growth * n

retained_data =
  sum(data_created_in_each_period_still_within_retention)
~~~

Nếu dữ liệu bị xóa theo retention, dung lượng không tăng tuyến tính vô hạn. Nhưng backup/snapshot có thể giữ nhiều phiên bản hoặc block thay đổi; cách tính thực tế phụ thuộc cơ chế của dịch vụ.

### 6.2. Database tiering

So sánh database cần bao gồm:

- Compute tier và HA topology.
- Storage, IOPS, transaction log/WAL và backup.
- Read replica hoặc cross-region replication.
- Connection pooling, proxy và monitoring.
- License và hỗ trợ.
- Maintenance window và upgrade.
- Chi phí migration/compatibility nếu đổi engine.

Database nhỏ có đơn giá thấp nhưng không đáp ứng peak hoặc failover SLO có thể làm tăng chi phí gián đoạn. Database tier lớn cũng có thể lãng phí nếu query chưa tối ưu.

### 6.3. Backup và retention

Retention lâu làm tăng storage, nhưng retention ngắn có thể khiến tổ chức không đáp ứng recovery, audit hoặc yêu cầu nghiệp vụ. Dự toán backup phải tính frequency, retention, full/incremental behavior, cross-region copy, immutable storage, restore test và egress khi phục hồi.

## 7. Network và data transfer thường bị bỏ sót

Network cost có thể tăng nhanh khi dịch vụ chia nhỏ hoặc triển khai đa vùng:

- Internet egress.
- Cross-zone transfer giữa compute và database.
- Cross-region replication.
- NAT gateway processing/hour.
- Private endpoint hourly/request fee.
- Load balancer, CDN request/transfer.
- Service mesh sidecar overhead và east-west traffic.
- Backup/restore và migration transfer.

### 7.1. Luồng dữ liệu cần lập sơ đồ

~~~mermaid
flowchart LR
    U["Users"] --> CDN["CDN / Edge"]
    CDN --> API["API compute"]
    API --> DB["Database"]
    API --> CACHE["Cache"]
    API --> OBJ["Object storage"]
    DB --> REPL["Cross-region replica"]
    API --> EXT["External providers"]
    API --> NAT["NAT / Internet egress"]
~~~

Mỗi mũi tên nên có volume, kích thước trung bình, tỷ lệ nén, số lần gọi, tỷ lệ cache hit và vị trí zone/region. Nếu API và database nằm khác zone, một query có thể tạo data transfer lặp; nếu ảnh đi qua CDN thì origin egress có thể giảm.

### 7.2. Cache hit và egress

Cache hit có thể giảm request tới origin và data transfer từ origin, nhưng cache cũng có chi phí storage, request, invalidation và vận hành. Dự toán cần dùng hit ratio đo được hoặc giả định có biên; không đặt 99% chỉ vì cache đã bật.

## 8. Chi phí observability, security và platform services

Những dịch vụ hỗ trợ có thể chiếm tỷ trọng đáng kể:

| Dịch vụ | Driver | Câu hỏi dự toán |
| --- | --- | --- |
| Logs | GB ingest, retention, query | Có log debug quá nhiều? Có sampling/redaction? |
| Metrics | Samples/time series, cardinality, retention | Label nào tạo cardinality cao? |
| Traces | Span volume, sampling, retention | Sampling có giữ trace lỗi quan trọng? |
| SIEM/security analytics | Event ingest, retention, query | Log nào bắt buộc, log nào có thể lọc? |
| KMS | Key count, API operations, HSM tier | Bao nhiêu request mã hóa/giải mã? |
| WAF | Request count, rule tier | Traffic bot/attack làm tăng request fee không? |
| Container registry | Artifact storage, transfer, vulnerability scan | Bao nhiêu image/version được giữ? |
| CI/CD | Build minute, runner, artifact | Có preview environment/parallel build quá nhiều? |

Không giảm retention hoặc sampling một cách máy móc để hạ hóa đơn. Phải bảo toàn dữ liệu cần cho bảo mật, điều tra, compliance và SLO.

## 9. Chi phí vận hành và năng lực đội ngũ

Kiến trúc tự quản lý thường đổi hóa đơn cloud thấp hơn lấy công sức kỹ thuật nhiều hơn. Nền tảng managed thường có giá dịch vụ cao hơn nhưng giảm một phần patching, control plane, upgrade hoặc on-call. Mức giảm này cần được đo, không giả định.

Một mô hình quy đổi nhân công:

~~~text
annual_operations_cost =
  engineers_involved
  * average_hours_per_month
  * loaded_hourly_rate
  * 12
~~~

Có thể tách các hoạt động:

| Hoạt động | Câu hỏi |
| --- | --- |
| Patching/upgrade | Bao nhiêu giờ mỗi tháng và bao nhiêu lần outage/maintenance? |
| Capacity management | Ai theo dõi peak, quota và scaling? |
| Incident response | Số incident, thời gian trực và thời gian khôi phục? |
| Backup/DR | Bao lâu kiểm thử restore/failover? Cần bao nhiêu người? |
| Security/compliance | Bao nhiêu giờ cho access review, evidence và remediation? |
| Release/platform | Chi phí duy trì pipeline, module và cluster? |

Không nên tính toàn bộ thời gian kỹ sư vào một phương án nếu nhân sự vẫn phải làm việc khác trong tổ chức. Cần phân biệt incremental cost, opportunity cost và chi phí đã cố định.

## 10. Xây dựng các phương án kiến trúc có thể so sánh

Mỗi phương án cần mô tả topology, assumptions, SLO, failure mode, operational model và cost driver. Không chỉ ghi tên công nghệ.

Ví dụ ba phương án cho nền tảng đặt chỗ:

| Chiều | A: VM/container tự quản lý | B: Managed container platform | C: Serverless/event-driven |
| --- | --- | --- | --- |
| Compute | VM/cluster do đội tự vận hành | Managed cluster/runtime | Function/managed service |
| Scale | Autoscaling do team cấu hình | Platform hỗ trợ scheduling/autoscaling | Tự co giãn theo invocation/event trong quota |
| Database | Managed DB chung | Managed DB tương tự | Managed DB/serverless tier hoặc dịch vụ dữ liệu tương thích |
| Event | Broker tự quản lý/managed | Managed broker | Event service/queue tích hợp |
| Operations | Nhiều trách nhiệm hạ tầng | Trung bình | Ít quản lý compute, nhưng nhiều tích hợp và quota |
| Cost sensitivity | Node utilization, standby, license | Node/pod density, platform fee | Invocation, duration, concurrency, provisioned capacity |
| Rủi ro chính | Patching, capacity và cluster ops | Platform complexity, upgrade, node waste | Cold start, vendor limits, duration/egress và observability |

Các phương án phải đáp ứng cùng functional scope, security baseline, data residency, SLO và RTO/RPO. Nếu A có multi-zone nhưng C chỉ chạy một zone, chi phí không phải là phép so sánh công bằng.

## 11. Mô hình hóa theo kịch bản tải

Ít nhất nên có ba kịch bản:

| Kịch bản | Mô tả | Mục đích |
| --- | --- | --- |
| Low/adoption-slower | Người dùng tăng chậm, tải thấp | Kiểm tra chi phí nền và khả năng tránh overprovision |
| Base/expected | Theo forecast có cơ sở | Dùng làm ngân sách kế hoạch |
| High/growth | Tăng trưởng nhanh, peak lớn hoặc chiến dịch | Kiểm tra scalability, quota và chi phí biên |

Có thể bổ sung stress hoặc disruption scenario: mất một zone, failover region, cache cold start, retry storm hoặc traffic bot. Các tình huống này không chỉ tăng traffic mà còn thay đổi cost curve và headroom.

### 11.1. Ví dụ bảng giả định

| Driver | Low | Base | High |
| --- | ---: | ---: | ---: |
| Monthly requests | 60 triệu | 120 triệu | 240 triệu |
| Peak/base ratio | 4x | 8x | 12x |
| Data growth/month | 60 GB | 120 GB | 240 GB |
| Cache hit ratio | 92% | 85% | 75% |
| Cross-region transfer | Thấp | Trung bình | Cao |
| Support/operation effort | 20 h/tháng | 35 h/tháng | 55 h/tháng |

Các con số hoàn toàn giả định. High case có thể tạo chi phí tăng nhanh hơn 2 lần vì peak ratio tăng, hit ratio giảm và yêu cầu thêm capacity dự phòng.

## 12. So sánh TCO và unit economics

TCO cho biết tổng nguồn lực tài chính cần bỏ ra trong khoảng thời gian. Unit economics cho biết chi phí trên một đơn vị giá trị/nghiệp vụ.

Ví dụ đơn vị có thể chọn:

- Chi phí mỗi booking hoàn tất.
- Chi phí mỗi 1.000 search request hợp lệ.
- Chi phí mỗi active tenant/tháng.
- Chi phí mỗi GB dữ liệu được lưu và phục vụ.
- Chi phí mỗi event được xử lý thành công.

~~~text
cost_per_completed_booking =
  total_platform_cost / completed_bookings

cost_per_1k_searches =
  total_search_related_cost / eligible_searches * 1000
~~~

Mẫu số phải phản ánh outcome hợp lệ. Nếu booking thất bại do lỗi hệ thống, chỉ chia tổng chi phí cho số booking thành công có thể làm unit cost tăng, nhưng đó là tín hiệu hữu ích; không nên loại lỗi khỏi phép đo chỉ để làm số đẹp.

### 12.1. Không so unit cost nếu scope khác nhau

Phải thống nhất:

- Có bao gồm platform shared cost không?
- Có bao gồm backup, observability và security không?
- Booking có cùng định nghĩa completed không?
- Traffic bot/test được lọc như thế nào?
- Chi phí nhân công và migration có được phân bổ không?

## 13. Phân tích độ nhạy một biến

Sensitivity analysis thay đổi một giả định trong khi giữ các biến khác cố định để biết biến nào ảnh hưởng mạnh đến kết quả.

Ví dụ các biến:

- Request volume ±30%.
- Peak/base ratio từ 4x tới 12x.
- Cache hit ratio từ 70% tới 95%.
- Storage growth ±50%.
- Egress unit price ±20%.
- Loaded engineering hours ±25%.
- Standby capacity từ 20% tới 100%.

### 13.1. Bảng độ nhạy minh họa

Giả sử base TCO 36 tháng là 1.000.000 đơn vị tiền. Các mức sau chỉ là ví dụ:

| Biến thay đổi | Giá trị thấp | Base | Giá trị cao | TCO tương ứng minh họa |
| --- | ---: | ---: | ---: | ---: |
| Request volume | -30% | 0% | +30% | 900k / 1.000k / 1.120k |
| Egress price | -20% | 0% | +20% | 970k / 1.000k / 1.030k |
| Cache hit ratio | 95% | 85% | 70% | 970k / 1.000k / 1.100k |
| Data growth | -50% | 0% | +50% | 960k / 1.000k / 1.070k |
| Operations hours | -25% | 0% | +25% | 940k / 1.000k / 1.080k |

TCO tương ứng phải được tính từ cost model thực. Bảng chỉ minh họa cách trình bày và cho thấy request volume chưa chắc là driver mạnh nhất.

### 13.2. Tornado chart

Tornado chart sắp xếp các biến theo mức ảnh hưởng từ lớn tới nhỏ:

~~~text
TCO impact (illustrative)
Request volume       |<-------------------->
Cache hit ratio          |<---------------->
Operations effort            |<------------>
Data growth                     |<-------->
Egress price                       |<---->
~~~

Biến nằm đầu chart cần được đo tốt hơn, đưa vào forecast và theo dõi sát. Không cần thu thập độ chính xác cao như nhau cho mọi input.

## 14. Phân tích độ nhạy nhiều biến và Monte Carlo

Trong thực tế, request volume, cache hit, storage growth và egress thường có tương quan. Ví dụ traffic cao có thể làm cache hit tăng vì dữ liệu nóng hơn, hoặc giảm vì cardinality/query diversity tăng. Phân tích one-way không thể thể hiện hết tương tác này.

### 14.1. Scenario matrix

Có thể xây ba hoặc nhiều kịch bản phối hợp:

| Scenario | Request growth | Cache hit | Data growth | Operations effort |
| --- | ---: | ---: | ---: | ---: |
| Efficient growth | +30% | 92% | +20% | +10% |
| Expected | +50% | 85% | +40% | +20% |
| Stress growth | +100% | 70% | +80% | +50% |

Đây là cách đặt giả định nhất quán, không phải dự báo xác suất. Hãy giải thích tại sao các biến đi cùng nhau.

### 14.2. Monte Carlo ở mức khái niệm

Monte Carlo mô phỏng nhiều lần bằng cách lấy mẫu từ phân phối đầu vào để tạo phân phối kết quả TCO. Ví dụ request volume có phân phối tam giác quanh low/base/high; egress price có biên; incident hours có phân phối riêng.

Quy trình:

1. Chọn driver quan trọng và phân phối có cơ sở.
2. Xác định tương quan giữa các biến nếu có.
3. Lấy mẫu input cho mỗi lần chạy.
4. Tính TCO từ cùng công thức.
5. Lặp đủ số lần và xem median, percentile, tail risk.
6. So sánh phương án theo median và mức chi phí ở percentile mà tổ chức quan tâm.

Không gán phân phối xác suất chỉ vì cần đưa số vào mô hình. Khi thiếu dữ liệu, dùng range/scenario và trình bày uncertainty thay vì tạo ra xác suất giả chính xác.

## 15. Break-even và ngưỡng thay đổi quyết định

Một phương án có thể rẻ hơn ở traffic thấp nhưng đắt hơn khi tải vượt một ngưỡng. Break-even giúp tìm điểm giao nhau của cost curve.

Ví dụ đơn giản:

~~~text
Option A cost = fixed_A + variable_A * workload
Option B cost = fixed_B + variable_B * workload

Break-even workload =
  (fixed_B - fixed_A) / (variable_A - variable_B)
~~~

Chỉ dùng công thức khi các đơn vị và giả định tuyến tính phù hợp, mẫu số khác 0 và workload nằm trong phạm vi mô hình. Thực tế có tier pricing, autoscaling step, quota, minimum fee và discount nên cost curve thường không tuyến tính.

### 15.1. Ví dụ diễn giải

Option A có baseline rẻ nhưng cost/request cao; Option B cần cluster tối thiểu đắt hơn nhưng cost/request thấp hơn. Ở tải nhỏ A có thể rẻ; sau break-even, B có lợi thế. Nếu dự báo tăng trưởng không chắc chắn, quyết định cần xét cả khả năng chuyển đổi, chi phí migration và rủi ro capacity.

## 16. Đưa reliability và risk vào cùng mô hình

Không nên chọn phương án rẻ nhất nếu không đạt mục tiêu nghiệp vụ. So sánh phải kiểm tra:

| Chiều | Câu hỏi |
| --- | --- |
| Availability | Có đạt SLO trong failure domain đã định? |
| RTO/RPO | Restore/failover mất bao lâu và có thể mất dữ liệu bao nhiêu? |
| Performance | p95/p99 có đạt khi peak và failover không? |
| Security | IAM, network, encryption, audit và patching có đáp ứng baseline? |
| Scalability | Có scale trong giới hạn quota và thời gian cần thiết? |
| Operability | Đội có đủ kỹ năng, tool và on-call để vận hành? |
| Vendor/portability | Mức phụ thuộc dịch vụ riêng và chi phí rời nền tảng? |
| Sustainability | Tài nguyên nhàn rỗi, utilization, data transfer và workload efficiency ra sao? |

### 16.1. Cost of downtime

Có thể thêm tác động downtime vào phân tích:

~~~text
expected_downtime_cost =
  incident_frequency
  * average_duration
  * business_impact_per_time_unit
~~~

Đây là ước tính kỳ vọng đơn giản, cần thận trọng với mẫu nhỏ và sự cố tail. Tách downtime cost định lượng khỏi rủi ro pháp lý, uy tín hoặc an toàn khó quy đổi. Một kiến trúc có TCO cao hơn vẫn có thể là lựa chọn hợp lý nếu giảm rủi ro không chấp nhận được.

## 17. Chi phí và tính bền vững môi trường

Chi phí thấp và footprint môi trường thấp thường có liên hệ qua utilization, giảm tài nguyên nhàn rỗi và tránh data movement dư thừa, nhưng không phải lúc nào cũng đồng nhất. Một region hoặc dịch vụ rẻ hơn có thể có hệ số phát thải khác; workload cần latency thấp có thể buộc đặt gần người dùng.

Những yếu tố nên xem xét:

- CPU/memory utilization và thời gian idle.
- Right-sizing và autoscaling.
- Tần suất tạo môi trường tạm và thời gian cleanup.
- Dữ liệu trùng lặp, retention và lifecycle tiering.
- Network egress và cross-region transfer.
- Cache hợp lý để giảm compute/data retrieval, có tính cả cache overhead.
- Chọn region dựa trên latency, residency, availability, giá và dữ liệu phát thải có sẵn.
- Hiệu quả xử lý trên mỗi giao dịch/booking thay vì chỉ tổng tài nguyên.

### 17.1. Chỉ số hiệu quả tài nguyên

Có thể theo dõi:

- vCPU-second hoặc GB-memory-hour trên mỗi booking hoàn tất.
- GB egress trên mỗi 1.000 request hợp lệ.
- kWh hoặc carbon estimate trên đơn vị công việc nếu provider/phương pháp có dữ liệu đủ tin cậy.
- Tỷ lệ resource utilization và tỷ lệ idle capacity.
- Tỷ lệ dữ liệu được chuyển sang storage tier phù hợp.

Nếu dùng carbon estimate, phải ghi rõ nguồn hệ số, phạm vi (location-based/market-based nếu phương pháp có phân biệt), thời gian và sai số. Không trình bày số ước lượng như số đo trực tiếp nếu nó được suy ra từ proxy.

## 18. Độ tin cậy của dữ liệu giá và quản lý uncertainty

Cloud price thay đổi theo region, thời điểm, currency, tier, discount, enterprise agreement và loại traffic. Vì vậy phải lưu:

- Provider/service/region và SKU hoặc tier được giả định.
- Currency, billing unit và ngày lấy giá.
- On-demand hay commitment/reserved/savings plan.
- Discount eligibility, usage commitment và termination condition.
- Free tier/credit có thời hạn, không coi là chi phí dài hạn bằng 0.
- Tax/support fee nếu nằm trong phạm vi.
- Giá có thể thay đổi và ai chịu trách nhiệm cập nhật.

### 18.1. Confidence class

| Mức tin cậy | Nguồn | Cách dùng |
| --- | --- | --- |
| Cao | Invoice/usage thực tế, quote hợp đồng hoặc giá SKU đã xác minh | Base estimate |
| Trung bình | Calculator/export với cấu hình gần thực tế | Planning estimate |
| Thấp | Benchmark, giả định utilization hoặc traffic chưa đo | Range/scenario và cần xác minh |

Ước tính cần thể hiện range và confidence. Ví dụ TCO 36 tháng có thể là 0,9–1,2 triệu đơn vị tiền với base 1,03 triệu; cách trình bày này trung thực hơn một số lẻ dài không phản ánh độ chính xác thật.

## 19. Quy trình lập mô hình và quyết định

~~~mermaid
flowchart TD
    R["Business requirements and SLO"]
    W["Workload / data / traffic baseline"]
    A["Define comparable architecture options"]
    C["Build cost-driver model"]
    S["Scenario and sensitivity analysis"]
    Q["Check reliability, security, sustainability"]
    D["Decision and ADR"]
    M["Measure actual cost and recalibrate"]
    R --> W --> A --> C --> S --> Q --> D --> M
    M --> W
~~~

Các bước thực hiện:

1. Chốt business outcome, SLO, RTO/RPO và phạm vi.
2. Thu thập workload profile và data growth.
3. Xác định các phương án cùng đáp ứng yêu cầu.
4. Liệt kê cost driver và nguồn giá.
5. Tạo base estimate theo tháng và toàn horizon.
6. Chạy low/base/high và sensitivity cho driver quan trọng.
7. Đánh giá break-even, reliability, security, operations và sustainability.
8. Ghi assumptions, exclusions, uncertainty và risk.
9. Chọn phương án hoặc đề xuất prototype/load test để giảm uncertainty.
10. Sau triển khai, so forecast với actual invoice/usage và cập nhật mô hình.

## 20. Bài thực hành: so sánh ba phương án cho nền tảng đặt chỗ

**Bối cảnh giả định:** nền tảng có 120 triệu request/tháng, peak gấp 8 lần average, 120 GB dữ liệu mới mỗi tháng, 24 tháng retention, multi-zone database, backup cross-region và 99,9% availability target cho booking. Nhóm đang cân nhắc VM/container tự quản lý, managed container platform và serverless/event-driven.

### Nhiệm vụ

1. Xác minh workload baseline và ghi nguồn/độ tin cậy của từng input.
2. Mô tả topology cho cả ba phương án: compute, database, cache, queue, network, observability và DR.
3. Xây cost-driver tree cho từng phương án.
4. Tính TCO 12, 24 và 36 tháng; tách one-time, fixed, variable, operations và resilience.
5. Tính chi phí trên 1.000 search request và một booking hoàn tất.
6. Chạy low/base/high scenario và sensitivity cho traffic, cache hit, egress, data growth, node utilization và operation hours.
7. Xác định break-even workload giữa các phương án.
8. Đánh giá RTO/RPO, failure mode và capacity khi mất một zone/region.
9. Đánh giá sustainability bằng utilization và tài nguyên trên mỗi đơn vị công việc; nêu hạn chế dữ liệu phát thải.
10. So sánh uncertainty, lock-in, migration cost và kỹ năng vận hành.
11. Viết ADR với lựa chọn, phương án bị loại, assumptions, rủi ro và điều kiện đánh giá lại.

### Mẫu bảng TCO

| Cost category | Option A | Option B | Option C | Source/confidence |
| --- | ---: | ---: | ---: | --- |
| Compute baseline/peak | Input | Input | Input | SKU/usage |
| Database/storage/backup | Input | Input | Input | Tier/GB/IOPS |
| Network/CDN/egress | Input | Input | Input | GB/request/region |
| Platform/security/observability | Input | Input | Input | Service pricing |
| Operations labor | Input | Input | Input | Hours/rate |
| DR/standby/replication | Input | Input | Input | RTO/RPO topology |
| Migration/parallel run | Input | Input | Input | One-time estimate |
| Total 36-month TCO | Formula | Formula | Formula | Model version |

### Tiêu chí hoàn thành

- Mọi phương án dùng cùng workload, SLO, security và DR baseline.
- TCO tách recurring, variable, one-time và operations cost.
- Unit economics dùng outcome và mẫu số thống nhất.
- Có low/base/high, one-way sensitivity và tương tác biến quan trọng.
- Break-even được tính trong phạm vi giả định hợp lệ.
- Nêu rõ nguồn giá, thời điểm, currency, discount và confidence.
- Cost không được tối ưu bằng cách bỏ control bảo mật hoặc reliability bắt buộc.
- Sustainability metrics có phạm vi và độ tin cậy rõ.
- ADR ghi assumptions, exclusions, risks và trigger xem xét lại.

## 21. Checklist Well-Architected trước khi duyệt dự toán kiến trúc

- [ ] Các phương án dùng cùng workload baseline và functional scope.
- [ ] Peak, average, burst, concurrency và growth được mô tả riêng.
- [ ] SLO, RTO/RPO, security và data residency là điều kiện so sánh chung.
- [ ] TCO bao gồm compute, data, network, platform, security, operations, resilience và migration.
- [ ] Fixed, variable, one-time và indirect cost được phân biệt.
- [ ] Database, backup, replica, IOPS, log retention và data lifecycle được tính.
- [ ] Egress, cross-zone/region, NAT, CDN và private endpoint được tính theo data flow.
- [ ] Autoscaling/utilization/headroom được mô hình hóa theo workload profile.
- [ ] Chi phí observability, SIEM, KMS, WAF, registry và CI/CD được xem xét.
- [ ] Nhân công vận hành và kỹ năng đội ngũ được đưa vào với assumptions rõ.
- [ ] Có TCO theo nhiều horizon và unit cost theo outcome nghiệp vụ.
- [ ] Có low/base/high scenario, sensitivity và break-even analysis.
- [ ] Biến số có ảnh hưởng lớn được đo hoặc có kế hoạch giảm uncertainty.
- [ ] Giá có source, region, currency, date, billing unit và discount assumptions.
- [ ] Downtime/risk được xem xét cùng chi phí đầu tư, không bị bỏ qua khi khó định lượng.
- [ ] Sustainability được đánh giá bằng utilization, data movement và hiệu quả trên mỗi đơn vị công việc.
- [ ] ADR ghi assumptions, exclusions, confidence, risk và trigger đánh giá lại.
- [ ] Sau triển khai có quy trình so forecast với actual usage/invoice và hiệu chỉnh mô hình.

**Điểm cốt lõi:** dự toán kiến trúc chỉ đáng tin khi các phương án được so trên cùng baseline và cùng mức dịch vụ. TCO cần tính cả compute, data, network, security, resilience, vận hành và migration; unit economics nối chi phí với kết quả nghiệp vụ; sensitivity và break-even cho biết khi nào kết luận thay đổi. Ghi rõ nguồn giá, giả định, uncertainty và dữ liệu thực tế sau triển khai giúp quyết định chi phí có thể được kiểm chứng và cập nhật theo vòng đời kiến trúc.
