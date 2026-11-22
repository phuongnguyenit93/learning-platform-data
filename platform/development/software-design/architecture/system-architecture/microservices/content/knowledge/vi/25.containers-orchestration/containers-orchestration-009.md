# Đánh giá khi nền tảng đơn giản hơn Kubernetes đã đáp ứng đủ

## 1. Mục tiêu bài học

Trong một kiến trúc microservices, việc có nhiều dịch vụ độc lập không tự động đồng nghĩa phải triển khai bằng Kubernetes. Kubernetes giải quyết các bài toán điều phối container nhiều node, tái tạo replica, routing nội bộ, tài nguyên, cập nhật phiên bản và policy. Nhưng Kubernetes cũng là một hệ thống phân tán cần được cấu hình, bảo vệ, giám sát, nâng cấp và vận hành. Khi yêu cầu thực tế đơn giản, **nền tảng ít phức tạp hơn có thể mang lại độ tin cậy tương đương trong phạm vi mục tiêu, với tổng chi phí thấp hơn**.

Bài này hướng dẫn cách quyết định giữa máy ảo (VM) và systemd, Docker Compose, PaaS, managed container/serverless platform và Kubernetes. Mục tiêu là chọn **nền tảng đơn giản nhất đáp ứng yêu cầu được chứng minh**, không chọn công cụ chỉ vì phổ biến hay muốn “chuẩn bị cho tương lai” một cách vô hạn.

Bạn sẽ học cách:

1. Tách quyết định kiến trúc ứng dụng khỏi quyết định nền tảng triển khai.
2. Định nghĩa SLO, RTO, RPO, traffic, khối lượng vận hành và ràng buộc compliance.
3. So sánh phạm vi trách nhiệm giữa VM, Compose, PaaS, managed containers và Kubernetes.
4. Xây bảng tiêu chí cứng, bảng chấm điểm có trọng số và mô hình Total Cost of Ownership (TCO).
5. Thiết kế một hệ thống “đơn giản nhưng production-ready” với versioned deploy, rollback, secrets, observability và backup.
6. Nhận diện tín hiệu tăng trưởng khiến Kubernetes thực sự có lợi ích đủ lớn.
7. Lập ADR và lộ trình nâng cấp nền tảng theo bằng chứng thay vì cảm tính.

Ví dụ sử dụng hệ thống đặt hàng gồm Order, Payment, Inventory, Notification, một API Gateway, database và message broker. Những con số, cấu hình và tên nhà cung cấp trong ví dụ mang tính minh họa; cần hiệu chỉnh theo hệ thống thật.

## 2. Container, microservices và orchestration là ba quyết định khác nhau

**Container** đóng gói một ứng dụng và môi trường chạy của nó. **Microservices** là một kiểu phân chia hệ thống theo trách nhiệm nghiệp vụ, hợp đồng giao tiếp và vòng đời triển khai. **Orchestration** quản lý nơi chạy, số replica, restart, networking, rolling update, tài nguyên và các điều kiện phục hồi của workload.

Có thể:

- Chạy một monolith trong container.
- Chạy nhiều microservices trên các VM với systemd.
- Dùng Docker Compose cho vài container trên một máy.
- Dùng PaaS để triển khai mỗi service riêng mà không quản trị node.
- Dùng một managed container service để autoscale API và worker.
- Dùng Kubernetes để điều phối nhiều loại workload theo policy.
- Kết hợp các cách trên nếu ranh giới trách nhiệm rõ.

Bảng dưới tách nhu cầu khỏi công cụ:

| Nhu cầu | Có thể giải quyết bằng nền tảng đơn giản? | Lưu ý |
|---|---|---|
| Đóng gói Java service | Có, container/JAR | Không cần Kubernetes |
| Restart khi process chết | Có, systemd/container runtime/PaaS | Không đồng nghĩa HA khi host chết |
| HTTPS và domain | Có, reverse proxy/LB/PaaS | Cần bảo vệ TLS và certificate renewal |
| Chạy 2–3 bản sao API | Có, nhiều VM hoặc managed replicas | Phải có load balancing và data consistency |
| Deploy image theo version | Có, pipeline + registry | Pin digest và lưu release record |
| Centralized logging | Có, agent hoặc provider logs | Cần retention, alert và quyền truy cập |
| Autoscaling theo traffic | Nhiều managed platforms hỗ trợ | Kiểm quota, cold start, backpressure |
| Multi-zone failover | Có thể qua managed platform | Phải xác minh failure domains thực tế |
| Custom scheduling/policy nhiều workload | Khó hơn trên nền tảng đơn giản | Kubernetes có thể phù hợp |
| Operators, CRDs và self-service platform | Cần nền tảng có extensibility | Kubernetes là lựa chọn đáng cân nhắc |

**Số microservice không phải thước đo đủ.** Tám API stateless, lưu lượng ổn định và database managed có thể dễ vận hành trên PaaS. Ba workload nhưng cần GPU scheduling, phân vùng mạng phức tạp và job phân tán có thể khiến orchestrator nâng cao trở nên hợp lý.

## 3. Kubernetes thực sự giúp gì?

Kubernetes có các primitives phổ biến:

- §Deployment§ quản lý replica và rolling update.
- §Service§, §EndpointSlice§ và Ingress/gateway component hỗ trợ discovery và routing.
- §ConfigMap§, §Secret§, workload identity integration giúp phân phối cấu hình.
- §Job§ và §CronJob§ cho một số tác vụ nền và định kỳ.
- §HorizontalPodAutoscaler§ để scale theo metric phù hợp.
- §PersistentVolume§ để kết nối workload với lưu trữ có vòng đời rõ.
- RBAC, admission policies, quotas, scheduling rules và controllers cho quản trị.
- Tính mở rộng qua custom resources/operators khi thực sự cần.

Kubernetes **không tự giải quyết**:

- Double charge, oversell hoặc retry không có idempotency.
- Schema migration, backward compatibility giữa hai service.
- Thiết kế database, backup/restore và tính toàn vẹn dữ liệu.
- Deadlock ứng dụng, query chậm, timeout chain và retry storm.
- SLA, on-call, incident response và trách nhiệm vận hành.
- Business metrics xuyên services và tính đúng đắn của workflow.
- Lỗi cấu hình secrets, IAM hoặc thiếu audit.
- Khả năng phục hồi sau outage nếu mọi replica cùng phụ thuộc một DB lỗi.

Một service không đúng về logic nghiệp vụ khi đặt trên Kubernetes vẫn không đúng. Nhiều replica còn có thể làm race condition rõ hơn. Trước khi chuyển nền tảng, phải xác định **bottleneck nằm ở orchestration hay ở thiết kế ứng dụng/dữ liệu**.

## 4. Năm nhóm lựa chọn thực tế

### 4.1. VM với systemd hoặc container runtime

Phù hợp khi chỉ có một hoặc vài service, traffic dự đoán được, team quen Linux, không cần autoscaling phức tạp. Một VM có thể chạy JAR Java, hoặc nhiều container. Systemd/container runtime xử lý restart và logs cơ bản.

Điểm mạnh là ít lớp vận hành, dễ debug và chi phí tương đối dễ dự báo. Điểm yếu là OS patch, hardening, secret distribution, backup, provisioning và failover do đội sở hữu. **Một VM là single point of failure** nếu không có phương án dự phòng, dù service tự restart sau crash.

### 4.2. Docker Compose trên một host

Compose khai báo services, volumes, networks, environment, restart policy và thứ tự khởi động. Nó hữu ích cho local/test và một số hệ thống nhỏ chấp nhận giới hạn một host.

Compose giúp tái tạo cấu hình, nhưng không tự có multi-node scheduling, failover cấp cluster hay autoscaling đa node như orchestration platform. §depends_on§ là cơ chế hỗ trợ startup; **không bảo đảm dependency luôn sẵn sau startup**. Backup volumes, secrets, rolling update, monitoring và host failure vẫn cần thiết kế.

### 4.3. PaaS ứng dụng

Một Platform as a Service có thể tiếp nhận source hoặc image rồi quản lý nhiều phần về runtime, deployment, SSL/TLS, routing, logs và scaling. Phù hợp với nhóm tập trung vào sản phẩm, không có platform team và workload tương thích với giới hạn provider.

Cần kiểm kỹ các ràng buộc: private network, runtime, background jobs, request timeouts, region, instance affinity, startup, secrets, quotas và chính sách giá. Không mặc định mọi PaaS có cùng mức độ HA hoặc kiểm soát bảo mật.

### 4.4. Managed container/serverless container platform

Đội cung cấp container image và cấu hình tài nguyên/concurrency; platform quản lý phần lớn hạ tầng. Hợp với HTTP API/worker stateless và traffic biến động, nhưng cần kiểm cold start, thời lượng job, persistent connections, egress và data locality. Ở tải liên tục cao, mô hình billing có thể khác đáng kể so với VM/cluster.

### 4.5. Kubernetes tự quản hoặc managed Kubernetes

Hợp khi có nhiều workload/team, policies phức tạp, yêu cầu scheduling, multi-zone, private networking, custom operators và khả năng mở rộng control plane. Managed Kubernetes giảm một số phần quản lý control plane, nhưng workload security, add-ons, networking, cost, upgrades và operations vẫn cần owner.

Nhóm không có người phụ trách cluster phải tính cả học tập, runbook, incident, upgrade và bảo mật. Ngược lại, khi một Kubernetes platform dùng chung đã trưởng thành, chi phí biên để đưa thêm một service lên có thể nhỏ.

## 5. Phân tích từ requirements, không từ tên công nghệ

Một cuộc đánh giá nên có bảng đầu vào:

| Nhóm yêu cầu | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Business | Người dùng cần điều gì, khi nào? | SLA/SLO, workflow |
| Traffic | Trung bình/đỉnh, RPS, concurrency, growth? | Metrics, dự báo |
| Reliability | Một host/zone lỗi có được phép downtime? | RTO/RPO, error budget |
| Deployment | Tần suất deploy, yêu cầu canary/rollback? | Release history |
| Workload | API, stream, queue worker, batch, GPU? | Diagram, process profile |
| Data | Stateful data ở đâu, backup thế nào? | DB/storage inventory |
| Networking | Internal routes, private connectivity, TLS? | Threat model |
| Security | IAM, secret rotation, audit, tenant isolation? | Policy, test |
| Compliance | Data region, retention, encryption? | Yêu cầu chính thức |
| Team | Ai xử lý sự cố và nâng cấp hệ thống? | On-call, kỹ năng |
| Finance | Infra bill, labor, incidents, tools? | TCO estimate |
| Future | Điều kiện nào đổi quyết định? | Growth trigger |

Tránh yêu cầu mơ hồ như “enterprise grade” hay “scalable”. Hãy đổi thành tiêu chí đo được, ví dụ “chịu 250 request/giây với P99 dưới 1 giây”, “mất một instance không làm mất hơn 1% giao dịch”, “khôi phục database trong 30 phút với mất dữ liệu tối đa 5 phút”.

## 6. Phân biệt hard constraints và preference

**Hard constraint** là điều kiện bắt buộc. Một nền tảng không đáp ứng thì phải bị loại hoặc có phương án bổ sung được kiểm chứng:

- Region/dữ liệu không được ra khỏi phạm vi cho phép.
- Bắt buộc hỗ trợ protocol/connection duration hoặc tài nguyên đặc biệt.
- RTO/RPO và mức failover định lượng.
- Private networking, identity, secrets và audit bắt buộc.
- Quota đủ cho peak và khả năng xin nâng quota trong thời gian cần.
- Đáp ứng chính sách mã hóa, backup, truy cập dữ liệu và compliance.

**Preference** là mong muốn có thể so sánh bằng trọng số:

- Đơn giản để onboard engineer.
- Chi phí thấp hơn.
- Thời gian deploy ngắn hơn.
- Tính portable.
- Dễ tích hợp với CI/CD hiện tại.
- Dễ quan sát, debug và hỗ trợ incident.
- Mức linh hoạt khi tương lai thay đổi.

Đừng để lựa chọn điểm cao ở nhóm “dễ sử dụng” che một hard constraint không đạt. Cũng không dựng cluster phức tạp vì một tính năng chỉ có thể cần sau nhiều năm mà chưa có business case.

## 7. Khi nền tảng đơn giản đã đáp ứng đủ

Các tín hiệu phổ biến:

1. Traffic hiện tại và peak đã được load-test trong giới hạn platform.
2. P95/P99, error rate và business completion đạt SLO.
3. HA/recovery phù hợp RTO/RPO với phương án được chọn.
4. Ứng dụng có health checks, graceful shutdown, logging/metrics/alerts.
5. Pipeline triển khai pin image/artifact version, smoke test và rollback.
6. Database/queue có backup, restore, replication nếu cần.
7. Secrets và quyền truy cập được quản lý, không hardcode.
8. Security/compliance được kiểm tra trên môi trường thật.
9. Nhóm có runbook và có thể xử lý sự cố trong nguồn lực hiện có.
10. Tổng chi phí vận hành và incident thấp hơn hoặc tương đương giải pháp phức tạp.

Một hệ thống 5 service, một region, database/queue managed, 200 RPS peak, vài deploy mỗi tuần và đội bốn người có thể phù hợp với managed containers. Đó là giả định; điều kiện “đủ” phải được chứng minh bằng load test, failure test và tổng chi phí.

### 7.1. Không đánh đồng “đủ” với “không cần kỹ thuật vận hành”

Dù không dùng Kubernetes, vẫn phải quản lý TLS, network isolation, identity, secrets, backup, observability, deploy, rollback, quota và on-call. Lựa chọn đơn giản **giảm bề mặt vận hành**, không xóa trách nhiệm vận hành.

## 8. Khi Kubernetes bắt đầu có lợi ích rõ

Hãy cân nhắc Kubernetes khi có nhu cầu thực và lặp lại:

- Nhiều nhóm muốn self-service deployment theo tiêu chuẩn chung.
- Khó quản lý scripts deploy riêng, policy và quyền của hàng chục workloads.
- Cần custom scheduling, topology, GPU/device allocation hoặc jobs phức tạp.
- Nhiều loại workload cùng dùng chung resource pool và policy.
- Cần CRDs/operators, admission controls hoặc network policies vượt khả năng PaaS.
- Provider quota, cost hoặc giới hạn runtime thực sự gây vấn đề đo được.
- Multi-cluster hoặc multi-environment operation là yêu cầu kinh doanh hiện tại.
- Đội platform đã có năng lực quản lý node, cluster, IAM, networking, add-ons và upgrades.
- Cần chuẩn hóa phần mềm hạ tầng nhiều đội và đã có ROI ước lượng.
- Managed platform không thể đáp ứng một hard constraint quan trọng.

Nếu chỉ có “microservices nhiều hơn năm” hoặc “công nghệ phổ biến trên thị trường”, chưa đủ bằng chứng.

## 9. High availability phải được định lượng

| Câu hỏi | Câu trả lời cần có |
|---|---|
| Downtime được phép? | SLO theo tháng/quý, error budget |
| Lỗi nào phải chịu được? | Process, VM, node, zone, region |
| RTO? | Bao lâu dịch vụ phải phục hồi |
| RPO? | Bao nhiêu dữ liệu có thể mất |
| Failover? | Tự động, bán tự động hay thủ công |
| Dữ liệu lâu dài? | DB replication, backup, restore |
| Routing? | LB health, DNS TTL, endpoint propagation |
| Business correctness? | No duplicate charge, no lost orders |

**Một VM** có thể phù hợp nếu RTO cho phép restore/redeploy sau host failure. §Restart=always§ không bảo vệ khi máy chủ chết.

**Managed platform** có thể cung cấp multi-instance và failover, nhưng cần xác minh instances có nằm trên failure domains độc lập, hành vi khi lỗi và chi phí tính năng.

**Kubernetes** có khả năng phân bố Pod, nhưng ba Pod cùng một node/zone hoặc dùng một DB lỗi vẫn không đạt HA. Replica count không thay thế data architecture, topology và test.

### 9.1. Fault test tối thiểu

Thử trong môi trường cho phép: kill một instance; làm mất một VM/zone giả lập; DB timeout; ngắt broker tạm thời; deploy revision lỗi; thu hồi secret test; khởi động lại service khi có workflow đang xử lý. Đo số người/đơn bị ảnh hưởng, thời gian recovery và trạng thái nghiệp vụ cuối.

## 10. Stateful data có thể là bài toán khó hơn orchestration

Nhiều tổ chức có thể dùng PaaS cho API stateless nhưng database, cache, broker và object storage được quản lý riêng. Đây là kiến trúc hợp lý khi mục tiêu giảm công chăm sóc stateful infrastructure.

Đặt các câu hỏi:

1. Ai trực khi disk đầy, replication lag hoặc DB failover?
2. Backup có test restore và RPO/RTO thật không?
3. App có sử dụng session/local file gây khó horizontal scale không?
4. Schema migration có backward compatibility khi rolling deploy không?
5. Có thể đặt data trong đúng region, network và security policy không?
6. Chi phí managed database so với tự vận hành thế nào nếu tính giờ kỹ sư và downtime?
7. Có idempotency, transactional outbox và reconciliation cho cross-service workflows không?

Đưa API lên Kubernetes không bắt buộc đưa PostgreSQL/Kafka vào cùng cluster. Một database được quản lý có thể làm giảm rủi ro nhiều hơn việc chọn một orchestrator phức tạp.

## 11. Chi phí thực sự: Total Cost of Ownership

Không chỉ so tiền VM với tiền cluster. Công thức mô hình:

\[
TCO = C_{compute} + C_{network} + C_{storage} + C_{managed} + C_{tooling} + C_{labor} + C_{incident} + C_{migration}
\]

Các khoản gồm:

- Compute, memory, idle capacity, autoscaling baseline.
- Load balancer, public IP, NAT/egress, TLS/certificates.
- Database/cache/broker/storage, backup, restore, DR environments.
- Logs, metrics, traces, retention và alerting.
- Registry, CI/CD, scanning, build runners.
- Engineer hours cho patch, upgrade, networking, IAM và incidents.
- On-call, training, runbook và maintenance.
- Tổn thất do downtime, hiệu quả release bị chậm.
- Migration và thời gian chạy hai hệ thống song song.

### 11.1. Bảng so sánh giả định

| Khoản/tháng (đơn vị giả định) | Hai VM | Managed PaaS | Kubernetes mới |
|---|---:|---:|---:|
| Compute/network/storage | 550 | 800 | 700 |
| Tooling/observability | 150 | 180 | 280 |
| Công vận hành quy đổi | 650 | 280 | 1.750 |
| Sự cố/bảo trì dự phòng | 220 | 140 | 450 |
| **Tổng** | **1.570** | **1.400** | **3.180** |

Bảng chỉ minh họa cách cộng chi phí, **không phải báo giá hiện hành của nhà cung cấp**. K8s có thể tiết kiệm hơn khi có platform team dùng chung và resource pooling ở quy mô lớn; một PaaS có thể đắt hơn ở tải ổn định cao. Phải thay số thật và so cùng mức SLO.

### 11.2. Sensitivity analysis

Tính lại khi peak tăng gấp ba, số deploy/tuần tăng từ 3 lên 30, hoặc phải chịu outage cả một zone. Nếu đáp ứng yêu cầu mới buộc VM phải có nhiều host, LB, replicated data, automation và on-call bổ sung, TCO của VM có thể tăng đáng kể.

Đừng lấy chi phí của một VM single-host để so với Kubernetes multi-zone trong khi mục tiêu HA khác nhau.

## 12. Ma trận quyết định có trọng số

Sau khi loại phương án không đáp ứng hard constraints, chấm mỗi tiêu chí §1–5§ và nhân trọng số.

| Tiêu chí | Trọng số minh họa |
|---|---:|
| Đáp ứng SLO/recovery | 25 |
| TCO theo 12 tháng | 20 |
| Khả năng vận hành bằng đội hiện có | 20 |
| Release/rollback và developer experience | 15 |
| Security/compliance | 10 |
| Growth/portability | 10 |
| **Tổng** | **100** |

Ví dụ điểm cho một đội nhỏ chạy stateless services:

| Phương án | SLO | TCO | Operations | Release | Security | Growth | Tổng/500 |
|---|---:|---:|---:|---:|---:|---:|---:|
| VM + Compose | 3×25 | 4×20 | 3×20 | 2×15 | 3×10 | 2×10 | 295 |
| Managed containers | 4×25 | 4×20 | 5×20 | 4×15 | 4×10 | 4×10 | 420 |
| Kubernetes mới | 4×25 | 2×20 | 2×20 | 4×15 | 4×10 | 5×10 | 330 |

Bảng là giả định để luyện phương pháp; điểm phải có evidence, reviewer và sensitivity analysis. Nếu công ty đã có Kubernetes platform ổn định, điểm Operations/TCO có thể tăng. **Không biến bảng điểm thành công thức máy móc**.

## 13. Thiết kế proof of concept để kiểm chứng

Thử nghiệm giới hạn trên một workload đại diện:

1. Chọn API dùng database, worker dùng queue và một đường async nếu có.
2. Đặt acceptance criteria: P99, error rate, workflow completion, startup time, RTO, secret isolation, rollback time.
3. Dựng 1–2 phương án khả thi, cùng artifact và dataset.
4. Bắn normal/peak/spike load với arrival rate phù hợp.
5. Inject instance crash, dependency timeout, deploy lỗi và restart khi có in-flight work.
6. Xác minh business invariants, không chỉ API 200.
7. Đo giờ setup, số bước deploy/rollback, runbook và mức khó debug.
8. Đọc bill/estimated cost, thêm labor và risk.
9. Ghi kết quả vào ADR, nêu điểm chưa chắc và trigger review.

Không cần dựng full Kubernetes production chỉ để biết managed PaaS đang đáp ứng yêu cầu: PoC nên vừa đủ kiểm tra giả thuyết khác biệt.

## 14. Ví dụ triển khai đơn giản bằng systemd

Một API Java nội bộ, tải ổn định, không cần autoscaling có thể chạy dưới systemd:

~~~ini
[Unit]
Description=Internal Orders API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=orders-api
Group=orders-api
WorkingDirectory=/opt/orders-api
ExecStart=/usr/bin/java -jar /opt/orders-api/orders-api.jar
Restart=on-failure
RestartSec=5
EnvironmentFile=/etc/orders-api/app.env
TimeoutStopSec=40
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
~~~

Đây là cấu hình minh họa. Phải tạo account, artifact, quyền file, environment và phương án secret delivery; §EnvironmentFile§ không nên chứa secret rõ trong Git. Nếu JVM treo nhưng process không thoát, systemd §Restart=on-failure§ không tự biết được điều đó; có thể cần watchdog/health monitor phù hợp.

Kết hợp reverse proxy/TLS, firewall, DB managed, backup, metrics/logs, deploy script và rollback. Với một host, luôn ghi rõ RTO nếu máy chết. Nhu cầu HA cấp host yêu cầu thêm redundancy hoặc platform khác.

## 15. Ví dụ Docker Compose một host

~~~yaml
services:
  orders:
    image: registry.example.invalid/orders:1.4.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db:5432/orders"
      SPRING_DATASOURCE_USERNAME: "app"
      ORDERS_DB_PASSWORD_FILE: "/run/secrets/db_password"
    secrets:
      - db_password
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8080/readyz > /dev/null"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 45s

  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: app
      POSTGRES_PASSWORD_FILE: "/run/secrets/db_password"
    volumes:
      - dbdata:/var/lib/postgresql/data
    secrets:
      - db_password
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d orders"]
      interval: 10s
      timeout: 3s
      retries: 5

secrets:
  db_password:
    file: ./secrets/db_password.txt

volumes:
  dbdata:
~~~

**Điều kiện cần hiểu:**

- Image §orders:1.4.0§ là ví dụ, image phải tồn tại thật.
- §ORDERS_DB_PASSWORD_FILE§ là hợp đồng giả định của ứng dụng: Spring Boot không tự động biến mọi biến §*_PASSWORD_FILE§ thành password. Code/config cần đọc file và cấu hình DataSource đúng.
- Healthcheck dùng §curl§, image thực phải có binary hoặc thay bằng healthcheck executable phù hợp.
- §/readyz§ phải được app expose và phản ánh khả năng phục vụ.
- Tệp secret không được commit, cần file permission và rotation; Compose file secrets không tự thay thế secret manager.
- §dbdata§ là lưu trữ một host, cần backup/restore; volume không tự bảo đảm HA.
- §depends_on§ hỗ trợ thứ tự startup, không bảo đảm service khác vẫn healthy trong runtime.
- Bind §127.0.0.1§ nghĩa là API chỉ lắng nghe qua loopback host; muốn public phải có reverse proxy/TLS được cấu hình riêng.
- Compose không tự cung cấp rolling update đa node. Nên có maintenance window hoặc một phương án chuyển traffic sang instance khác khi deploy.

### 15.1. Khi nào Compose không còn phù hợp?

Khi một host failure không được phép gây downtime, cần tự động scale đa host, policy deployment nhiều team, isolation phức tạp hoặc scripts failover ngày càng tốn công, hãy đánh giá PaaS/managed containers/orchestrator. Đừng tự xây một control plane bằng nhiều script chỉ để tránh dùng dịch vụ managed phù hợp.

## 16. Ví dụ managed containers cho microservices

~~~text
External clients
    |
    v
Managed HTTPS ingress
    |
    +--> Order API: multiple managed instances
    |      +--> Managed relational database
    |      +--> Managed queue
    |
    +--> Payment API: multiple managed instances
    |      +--> PSP sandbox/production with scoped credentials
    |
    +--> Inventory API: multiple managed instances
    |
Managed queue --> Notification/Inventory workers
~~~

Lợi ích tiềm năng: mỗi API deploy độc lập, health checks, scaling/traffic routing được quản lý và ít phải chăm sóc node. Cần PoC xác minh:

- Region/zone distribution và failure recovery.
- Secrets, workload identity và private network.
- Cold start, max concurrency, job duration và request timeout.
- Graceful shutdown khi có queue/message đang xử lý.
- Per-service quota, rate limiting và egress cost.
- Logging/tracing/metrics, RBAC và retention.
- Deploy revision, traffic split/canary và rollback.
- Chi phí ở workload ít tải, đều tải và spike.

Managed platform không thay transactional outbox, idempotency, state machine, schema migration hay reconciliation.

## 17. Production readiness không phụ thuộc Kubernetes

| Năng lực | Bằng chứng cần có |
|---|---|
| Versioned artifact | Đọc được image digest/commit đang chạy |
| CI/CD | Build/test/deploy không dựa vào lệnh bí mật trên máy cá nhân |
| Config | Có source of truth và hiệu lực theo environment |
| Secrets | Không hardcode, có scoped identity, rotation, audit |
| HTTPS/network | Chỉ mở routes cần thiết, kiểm ingress/egress |
| Health | Startup/readiness/liveness theo lifecycle |
| Rollback | Diễn tập revert một release lỗi |
| Backup/restore | Thử restore và đo RPO/RTO |
| Monitoring | Logs, metrics, tracing, alerts, correlation |
| Capacity | Load/spike test tại peak dự kiến |
| Recovery | Fault test và runbook khi host/dependency mất |
| Security update | Patch OS/runtime/base image có owner |
| Compliance | Region, retention, encryption và audit kiểm chứng |

Một VM hoặc PaaS có đầy đủ năng lực này có thể production-ready cho phạm vi cụ thể. Ngược lại, một cluster Kubernetes chưa có backup, secrets, monitoring và incident process vẫn có thể không production-ready.

## 18. CI/CD không cần phức tạp để an toàn

~~~mermaid
flowchart TD
    A[Commit] --> B[Build and unit tests]
    B --> C[Dependency and security scan]
    C --> D[Versioned artifact or image]
    D --> E[Integration and contract tests]
    E --> F[Deploy staging]
    F --> G[Smoke and load tests]
    G --> H[Approve revision]
    H --> I[Deploy production]
    I --> J{Business and technical SLI healthy?}
    J -->|Yes| K[Record release]
    J -->|No| L[Rollback / stop rollout]
~~~

Với VM/Compose, có thể dùng script deploy idempotent: tải image digest cụ thể, cấp cấu hình, chạy schema migration đã kiểm soát, cập nhật container, đợi readiness, smoke test, lưu release metadata và rollback nếu failure. Mỗi bước cần log, exit code rõ và tránh lộ token.

Với PaaS, tận dụng revisioned deployments, traffic splitting/rollback nếu nền tảng hỗ trợ; vẫn phải chạy contract tests và theo dõi business outcomes. Không trộn thay platform với thay domain schema trong một release khó đảo ngược.

## 19. Readiness, liveness và graceful shutdown

Nền tảng đơn giản vẫn cần phân biệt:

- **Startup:** instance đã khởi tạo config, server và tài nguyên thiết yếu chưa?
- **Readiness:** instance có nên nhận traffic mới không?
- **Liveness:** tiến trình có treo không thể tự hồi phục và cần restart không?
- **Shutdown:** khi bị dừng, có drain request/message và giữ idempotency không?

Nếu API mất DB vài giây, restart toàn bộ fleet vì liveness kiểm DB có thể làm sự cố tệ hơn. Nếu một Pod/instance đang shutdown nhưng LB còn route, người dùng có thể nhận 502/503. Những vấn đề này hiện diện dù dùng Kubernetes hay managed platform.

### 19.1. Health không bằng hoàn thành nghiệp vụ

Order API trả 202 Accepted và instance healthy nhưng Payment callback không về, Inventory event đang kẹt. Cần đo workflow completion, stuck paid orders, queue lag và compensation. **Green deployment không chứng minh toàn bộ quy trình đúng**.

## 20. Scaling: đúng bottleneck trước khi đổi nền tảng

Khi latency tăng và throughput không còn tăng, hãy phân rã:

- CPU/memory/throttling ở application.
- DB connections, slow query, locks và I/O.
- Queue lag và hot partitions.
- Cache hit/miss, contention theo SKU/order.
- PSP/vendor quotas và network latency.
- Retry amplification, timeout budgets và request fan-out.
- Load generator và arrival rate thực tế.

Nếu DB là bottleneck, chuyển API từ PaaS sang Kubernetes nhưng vẫn dùng cùng DB có thể không giúp. Thêm replica cũng có thể làm connection/lock pressure tăng.

**Vertical scaling:** tăng tài nguyên instance, ít thay đổi nhưng có giới hạn và single-host risk.

**Horizontal scaling:** cần stateless runtime hoặc shared state, LB, idempotency, cache/data consistency và backend capacity.

**Autoscaling:** phải đo từ lúc có quyết định scale đến lúc capacity usable; cold start và startup budget có thể khiến scale-out không kịp spike ngắn.

## 21. Portability và vendor lock-in

Kubernetes có API chung nhưng ứng dụng vẫn có thể phụ thuộc vào cloud IAM, load balancer, storage classes, managed DB, DNS, networking và observability. Vì vậy “dùng YAML chuẩn” không đồng nghĩa chuyển cloud bằng một lệnh.

PaaS cũng có phụ thuộc provider, nhưng container image, HTTP contracts, SQL interface và cấu hình tách biệt có thể giảm effort chuyển đổi. Để quản lý lock-in:

1. Liệt kê cụ thể API/service độc quyền đang dùng.
2. Ghi dữ liệu có export/backup theo định dạng phục hồi được không.
3. Tách business logic khỏi adapter theo mức hợp lý.
4. Tránh xây abstraction phức tạp cho một cuộc migration chưa có kế hoạch.
5. Nếu multi-cloud thực sự là yêu cầu, chạy PoC chuyển ứng dụng và dữ liệu để đo effort.

**Portability nên được đo bằng thời gian/chi phí chuyển**, không dùng như một nhãn marketing.

## 22. Đội ngũ là một phần của kiến trúc

Câu hỏi về staffing:

- Ai có thể restore database lúc nửa đêm?
- Ai quản lý OS/cluster upgrades và security patches?
- Ai kiểm gateway/ingress, DNS, certificates và networking?
- Một engineer mới mất bao lâu để deploy và rollback?
- Có đủ người trực on-call hay một người là single point of knowledge?
- Có runbook đã diễn tập và quyền truy cập phù hợp?
- Có thể phân biệt lỗi ứng dụng với lỗi hạ tầng qua traces/metrics không?
- Công việc platform có làm chậm product development không?

Kubernetes không “xấu” vì khó; nó đòi hỏi kỹ năng và ownership tương ứng. Nếu tổ chức đã có platform team dùng chung, một workload mới có thể có vận hành tốt hơn trên cluster hiện tại. Nếu không có team, managed service có thể an toàn và kinh tế hơn.

## 23. Cách đo rủi ro vận hành

| Sự cố | VM/Compose | Managed platform | Kubernetes |
|---|---|---|---|
| Host hỏng | Cần dự phòng/restore | Tùy provider/instance count | Cần topology và data layer đúng |
| Process chết | systemd/runtime restart | Managed restart | Kubelet/controller restart |
| Config sai | Script/release rollback | Revision/rollback tùy provider | Rollout/revert manifests |
| DB lỗi | App phải degrade/retry | App phải degrade/retry | App phải degrade/retry |
| Secrets lộ | Host/secret policy | IAM/secret integration | IAM/RBAC/secret management |
| Network sai | Firewall/proxy | Provider networking | CNI/NetworkPolicy/Ingress |
| Scale thiếu | Manual/automation | Quota/autoscaling | HPA/nodes/quotas |
| Operator mistake | Scripts và file permissions | Console/API roles | Cluster permissions và controllers |

Không nền tảng nào loại trừ common-mode failure. Ba replica dùng cùng credential bị revoke hoặc cùng DB hỏng vẫn có thể mất chức năng. Rủi ro phải được đánh giá ở **toàn bộ đường đi nghiệp vụ**, không chỉ một nền tảng.

## 24. Tín hiệu định lượng để nâng cấp nền tảng

Nên định nghĩa trước các trigger, ví dụ:

- P99 hoặc error budget vượt ngưỡng do **giới hạn platform đã xác nhận**.
- Peak capacity thực vượt quota và không thể tăng theo SLA.
- Chi phí managed platform tăng nhanh hơn TCO Kubernetes sau khi tính nhân sự.
- Số nhóm/workloads tăng khiến scripts và policy khó kiểm soát.
- Có yêu cầu scheduling/network/security mới platform không đáp ứng.
- Tần suất release cao làm deployment hiện tại tạo lỗi thường xuyên.
- MTTD/MTTR cao **do thiếu khả năng platform**, sau khi đã loại trừ observability ứng dụng.
- Multi-region/multi-cluster là bắt buộc và có ngân sách vận hành.
- Cần shared platform team/self-service có business case được duyệt.

Ví dụ trigger trong ADR: “Đánh giá lại nếu traffic peak vượt 1.000 workflow/giây trong hai quý hoặc chi phí managed platform vượt 30% TCO dự báo sau tối ưu.” Các con số là giả định để minh họa cách viết.

**Trigger phải buộc nhóm thu dữ liệu**, không phải tự động ra lệnh “chuyển Kubernetes”.

## 25. Lộ trình trưởng thành theo giai đoạn

### Giai đoạn A — MVP có kỷ luật

Một monolith hoặc vài API, managed DB, Compose/PaaS, versioned deployment, basic logs, auth, backup và SLO cơ bản. Ưu tiên xác thực sản phẩm.

### Giai đoạn B — Production có trách nhiệm

Thêm CI/CD, readiness/liveness, alerts, backups được diễn tập, rollback, secrets rotation, load test, incident runbook và on-call owner.

### Giai đoạn C — Tăng service và traffic

Managed replicas, queues, cache, connection budgets, idempotency, trace xuyên services, progressive delivery, data lifecycle và capacity planning.

### Giai đoạn D — Platform engineering

Khi ROI rõ, chuẩn hóa deployment templates, IAM/policy, observability, cost management và self-service. Kubernetes có thể là công cụ của nền tảng này, nhưng không phải mục tiêu tự thân.

### Giai đoạn E — Điều phối nâng cao khi cần

Multi-cluster, custom operators, service mesh, advanced scheduling và cross-region governance. Chọn từng thành phần theo yêu cầu được đo, tránh tích lũy add-ons chỉ vì có sẵn.

## 26. Nếu quyết định migrate lên Kubernetes

Không nên chuyển toàn bộ ứng dụng, database, CI/CD và schema trong một lần. Lộ trình giảm rủi ro:

1. Ghi business case, hard constraints và baseline TCO/SLO.
2. Chuẩn hóa image digest, config, secrets và health endpoints.
3. Tách stateful data khỏi local filesystem và đánh giá managed DB.
4. Thiết kế workload identity, ingress, egress, DNS, TLS và RBAC.
5. Dựng platform nhỏ với monitoring, security policy, upgrades và backup.
6. Chuyển một stateless service ít rủi ro trước.
7. Dùng canary/traffic split theo khả năng ingress để so sánh cũ/mới.
8. Kiểm tail latency, failure recovery, business workflow correctness và cost.
9. Giữ rollback route, API/schema compatibility và dữ liệu nhất quán.
10. Di chuyển service tiếp theo chỉ khi bằng chứng tốt.
11. Đào tạo on-call, cập nhật incident runbook và platform ownership.
12. Dừng/điều chỉnh nếu lợi ích không đạt kỳ vọng.

### 26.1. Những chi phí migration hay bị bỏ quên

- Secret delivery và rotation khác.
- IAM/workload identity và audit.
- Ingress routing, DNS, certificates và private network.
- Migrations/transaction compatibility, workflow consistency.
- Health probes và graceful shutdown thay đổi.
- Retry, circuit breaker và connection pools khi có nhiều replica.
- Logs/metrics/tracing và cost observability.
- Upgrade policies, base images, supply chain.
- Incident drills, training và documentation.
- Hai hệ thống chạy song song, chi phí rollback và cutover.

Một migration “chạy được trên cluster” mới là bước đầu, chưa chứng minh hệ thống vận hành tốt hơn.

## 27. Architecture Decision Record minh họa

~~~markdown
# ADR: Deployment platform for checkout microservices
Status: Accepted
Date: 2026-11-12

## Context
- 6 stateless services, one managed DB, one managed queue
- Peak target: 250 requests/second
- One region; team of 4 engineers
- Need versioned deployment, TLS, secret isolation and rollback

## Options
A. Two VMs with Compose and load balancer
B. Managed container platform
C. Managed Kubernetes cluster

## Constraints
- Required region and private database access
- RTO and RPO must be measurable
- Payment side effects must be idempotent
- Alerts and audit are mandatory

## Decision
Choose B for the current release.

## Evidence
- Peak/load and dependency-failure PoC meet SLO
- Multi-instance recovery tested
- Secret/IAM integration confirmed
- 12-month TCO and on-call effort reviewed

## Tradeoffs
- Provider-specific deployment configuration
- Some long-running worker constraints

## Revisit when
- Quota or cost threshold is exceeded
- Custom scheduling/network policies become necessary
- Several teams need self-service platform operations
~~~

Đây là **mẫu quyết định giả định**, không phải ADR đã được chấp thuận của dự án cụ thể. Một ADR tốt lưu được lý do, bằng chứng, tradeoffs, owner và điều kiện đánh giá lại. Nó giúp người đến sau không lặp tranh luận chỉ dựa vào sở thích công nghệ.

## 28. Tình huống tổng hợp: nền tảng nào cho cửa hàng trực tuyến?

### 28.1. Giả định

Hệ thống có Order API, Payment API, Inventory API, Notification Worker và Admin API, managed relational DB, managed queue, một region. Peak 300 RPS; đội bốn engineers kiêm vận hành; 5 lần deploy/tuần; cần hai replica cho API quan trọng và rollback trong vài phút. Không có workload GPU hoặc scheduling đặc biệt.

### 28.2. Lựa chọn A — VM + Compose

Dễ hiểu, tài nguyên ổn định, nhưng yêu cầu HA khiến phải có hai host, LB, deployment strategy, routing, secrets và failover automation. Cần kiểm RTO khi một host chết và đảm bảo database/queue durable.

### 28.3. Lựa chọn B — Managed containers

Có thể deploy độc lập, nhiều replicas, health routing và integrated IAM/secrets, nếu provider hỗ trợ. Nhóm tập trung vào code và workflows. Cần PoC xác nhận instance distribution, private network, cold start, quota, rollback và cost.

### 28.4. Lựa chọn C — Managed Kubernetes

Đáp ứng nhiều nhu cầu điều phối, nhưng đội chưa có cluster owner. Phải trả thêm chi phí setup, network policies, ingress, node lifecycle, upgrades, observability và training.

### 28.5. Kết quả giả định

Nếu B đạt hard constraints, SLO, failure tests và có TCO thấp hơn, chọn B kèm ADR và trigger review. Nếu sau hai năm có 60 service, nhiều team, streaming/batch đặc thù và platform team, kết luận có thể chuyển về Kubernetes. **Quyết định đúng phụ thuộc thời điểm và bằng chứng**.

## 29. Những sai lầm thường gặp

1. “Đã dùng container thì phải lên Kubernetes.” Hai quyết định khác nhau.
2. “Microservices bắt buộc cần cluster.” Số service không chứng minh yêu cầu orchestration.
3. “Một VM rẻ nhất.” Bỏ qua labor, downtime, HA và backup.
4. “Kubernetes tự đảm bảo HA.” DB, zone, ingress, data và policy vẫn có thể là single point of failure.
5. “Managed Kubernetes không cần người vận hành.” Add-ons, IAM, nodes, cost và incidents vẫn cần owner.
6. “Managed platform luôn an toàn/compliant.” Cần kiểm tính năng theo provider/region/tier và policy thật.
7. “Chọn thứ có nhiều tính năng nhất.” Tính năng không dùng vẫn tăng độ phức tạp, cấu hình và trách nhiệm.
8. “Kubernetes sẽ sửa performance.” Bottleneck DB/lock/PSP không biến mất.
9. “Kubernetes đảm bảo portability.” Cloud add-ons và data layer vẫn gây lock-in.
10. “Chỉ nhìn P95 API.” Bỏ qua async workflows, paid orders kẹt và tail latency.
11. “Compose restart policy là HA.” Host failure vẫn làm ngừng tất cả container.
12. “Bỏ qua CI/CD vì chỉ một máy.” Dễ deploy nhầm version, thiếu rollback và audit.
13. “Di chuyển toàn bộ service một lượt.” Làm tăng blast radius và khó phân biệt lỗi.
14. “Chuyển platform trước khi đo workload.” Không có bằng chứng lợi ích.
15. “Đặt ngưỡng Kubernetes theo số service tùy ý.” Không phản ánh traffic, team, security và SLO.
16. “Cứ ở nền tảng cũ mãi vì đơn giản.” Khi hard constraints thay đổi, cần đánh giá lại.
17. “Giải quyết độ phức tạp scripts bằng thêm scripts.” Có thể nên chuyển sang managed service phù hợp.
18. “Đặt tất cả workloads lên cùng một platform bằng mọi giá.” Cần chọn theo workload, nhưng cũng cân nhắc chi phí multi-platform.

## 30. Bài tập thực hành

### Bài A — Chọn nền tảng cho nhóm ba người

Có bốn service, 50 RPS trung bình, 180 RPS peak, một region, DB managed, hai deploy/tuần. SLO cho phép maintenance window ngắn. Hãy so sánh VM+Compose, managed containers và Kubernetes theo hard constraints, TCO, recovery và on-call. Viết một đoạn ADR và ba trigger để review lại.

### Bài B — Khi nào Kubernetes thắng?

Một công ty có 10 team và 70 workloads gồm API, stream processors, GPU jobs và CronJobs, yêu cầu network policy riêng. Có platform team, nhưng deployment hiện tại rải rác VM/PaaS khó quản trị. Lập business case gồm self-service, RBAC, policy, resource pooling, team cost và migration risk.

### Bài C — Tính TCO

Giả sử:
- VM: infra 600/tháng, vận hành 30 giờ × 35/giờ.
- PaaS: infra 1.000/tháng, vận hành 8 giờ × 35/giờ.
- K8s: infra 900/tháng, vận hành 45 giờ × 35/giờ, tools 200/tháng.

Tính tổng, so sánh lại khi PaaS tăng 50% compute cost. Nếu một VM không đạt yêu cầu HA, tại sao không thể kết luận VM là tốt nhất dù giá nhỏ nhất?

### Bài D — Fault test một VM

Owner nói “có §restart: unless-stopped§ nên không downtime”. Hãy lập test process crash, host failure, disk full, DB outage và deploy lỗi; nêu expected behavior và RTO. Thiết kế cải tiến tối thiểu để đạt HA cấp host.

### Bài E — Tìm bottleneck thật

Managed platform P99 tốt ở 200 RPS nhưng trượt ở 400 RPS; CPU app còn thấp, DB connection pool đầy, retry tăng. Có cần Kubernetes không? Đề xuất điều tra transaction duration, query plan, pool budget, DB quota, retry amplification và thử lại.

### Bài F — Migration có rollback

Order API từ PaaS sang Kubernetes vì policy mạng mới. Lập kế hoạch service identity, config/secrets, ingress, canary, event/schema compatibility, tracing, rollback traffic và đối soát payment side effects.

### Bài G — Viết ma trận quyết định

Với hệ thống do bạn tự chọn, tạo bảng hard constraints, trọng số, điểm từng lựa chọn và evidence. Thử thay đổi hai giả định (tăng SLO, tăng traffic hoặc giảm on-call staff) rồi giải thích vì sao quyết định thay đổi hoặc giữ nguyên.

## 31. Checklist áp dụng vào dự án thật

- [ ] Có mô tả workflow, SLO, RTO/RPO và failure domains.
- [ ] Có số liệu traffic trung bình, peak, concurrency, growth và workload mix.
- [ ] Phân loại stateless/stateful, API/worker/batch/stream/GPU.
- [ ] Có hard constraints bảo mật, region, network, compliance và provider quota.
- [ ] Đã đánh giá ít nhất một lựa chọn đơn giản.
- [ ] Mỗi phương án đã được kiểm tra những yêu cầu bắt buộc.
- [ ] Có PoC với load, restart, failover, deploy lỗi và rollback.
- [ ] Không bỏ qua tính đúng đắn nghiệp vụ như no duplicate charge.
- [ ] Có TCO gồm compute, tools, labor, on-call, incidents và migration.
- [ ] Có owner cho patch, upgrade, secret rotation, backup, incident.
- [ ] Artifact/image pin version, cấu hình theo môi trường và release record.
- [ ] Có logs, metrics, traces, alerts và runbook dễ thực hiện.
- [ ] DB/queue có durability, backup và restore được diễn tập.
- [ ] Có security/IAM và network boundaries được kiểm thử.
- [ ] Có ADR với tradeoffs, assumptions và trigger review.
- [ ] Migration nếu có được chia giai đoạn, có rollback và data compatibility.

## 32. Kết luận

Kubernetes là công cụ mạnh để điều phối workload nhiều node và hỗ trợ platform engineering, nhưng không phải đích đến bắt buộc của mọi hệ thống container hoặc microservices. VM, Docker Compose, PaaS và managed containers có thể là lựa chọn hợp lý khi đáp ứng được SLO, bảo mật, khôi phục, scale, triển khai và chi phí đã xác định.

Quyết định tốt nhất được tạo từ **bằng chứng của workload và đội vận hành**: định nghĩa yêu cầu cứng; thử phương án đơn giản; đo TCO toàn phần; kiểm fault/recovery và kết quả nghiệp vụ; lưu ADR; đặt trigger rõ để đánh giá lại khi nhu cầu thật sự thay đổi. **Giữ kiến trúc đơn giản là một lựa chọn có kỷ luật, miễn là độ đúng và khả năng phục hồi đã cam kết vẫn được chứng minh.**