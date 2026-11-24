# Yêu cầu lưu trú dữ liệu và kiểm soát vị trí thực thi workload

Khi triển khai compute trên cloud, vị trí tạo và xử lý dữ liệu có thể quan trọng ngang với cấu hình CPU, bộ nhớ hoặc mạng. Một workload có thể chạy ở nhiều region, zone hoặc loại hạ tầng khác nhau; dữ liệu của nó cũng có thể xuất hiện trong object storage, database, snapshot, backup, log, cache, telemetry, model artifact và bản sao phục hồi thảm họa. Nếu chỉ chọn region cho máy ảo mà không kiểm soát các luồng dữ liệu đi kèm, tổ chức vẫn có thể vô tình đưa dữ liệu ra ngoài phạm vi được phép.

Yêu cầu lưu trú dữ liệu (data residency) quy định dữ liệu phải được lưu hoặc xử lý tại những địa điểm địa lý nhất định. Kiểm soát vị trí thực thi workload bảo đảm compute, dịch vụ phụ trợ và đường truyền dữ liệu tuân thủ ranh giới đó. Hai yêu cầu liên quan nhưng không đồng nhất: dữ liệu có thể được lưu trong một region nhưng được xử lý bởi workload ở region khác; ngược lại, compute có thể chạy tại địa phương nhưng log, backup hoặc telemetry lại được gửi sang nơi khác.

Bài học này hướng dẫn cách chuyển yêu cầu lưu trú dữ liệu thành chính sách kỹ thuật có thể thực thi và kiểm toán. Nội dung bao gồm phân loại dữ liệu, xác định phạm vi địa lý, lựa chọn region, giới hạn vị trí compute, kiểm soát bản sao và luồng dữ liệu, quản trị truy cập hỗ trợ, thiết kế DR, policy-as-code và thu thập bằng chứng tuân thủ. Sau bài học, bạn có thể:

- Phân biệt data residency, data sovereignty, data localization và data locality.
- Xác định dữ liệu nào cần lưu, xử lý, sao lưu hoặc truy cập trong phạm vi địa lý cụ thể.
- Lập bản đồ dữ liệu và dependency của workload qua các region và dịch vụ.
- Thiết kế allowlist region, policy tổ chức và guardrail ngăn triển khai sai vị trí.
- Kiểm soát vị trí của VM, container, Kubernetes node, serverless function và accelerator.
- Đánh giá snapshot, backup, log, telemetry, cache, secret và model artifact.
- Thiết kế cross-region replication và disaster recovery phù hợp với ràng buộc lưu trú.
- Kiểm thử, giám sát và lưu bằng chứng về vị trí thực thi cùng luồng dữ liệu.

## 1. Các khái niệm cần phân biệt

Các thuật ngữ địa lý dữ liệu thường được dùng thay thế cho nhau trong hội thoại, nhưng chúng mô tả những khía cạnh khác nhau. Khi chuyển yêu cầu pháp lý, hợp đồng hoặc chính sách nội bộ thành cấu hình cloud, cần xác định chính xác điều gì phải được giữ ở đâu và ai được phép truy cập.

| Khái niệm | Ý nghĩa | Câu hỏi chính |
|---|---|---|
| Data residency | Địa điểm địa lý nơi dữ liệu được lưu trữ hoặc duy trì | Dữ liệu nằm ở quốc gia/region nào? |
| Data sovereignty | Quyền tài phán và luật có thể áp dụng đối với dữ liệu hoặc nhà cung cấp kiểm soát dữ liệu | Luật và cơ quan có thẩm quyền nào có thể chi phối dữ liệu? |
| Data localization | Yêu cầu dữ liệu thuộc một phạm vi phải được lưu hoặc xử lý trong một quốc gia/vùng nhất định, đôi khi hạn chế chuyển ra ngoài | Có bắt buộc dữ liệu ở lại trong biên giới không? |
| Data locality | Mức độ gần nhau giữa dữ liệu và compute để giảm latency, chi phí truyền và tải mạng | Workload chạy gần dữ liệu đến mức nào? |
| Processing location | Địa điểm nơi dữ liệu được đọc, giải mã, biến đổi hoặc suy luận | Dữ liệu được xử lý ở đâu? |

Data residency không tự động trả lời mọi câu hỏi về sovereignty. Một dữ liệu được lưu tại một region vẫn có thể chịu ảnh hưởng bởi luật áp dụng cho nhà cung cấp hoặc tổ chức kiểm soát. Tương tự, data locality thường là mục tiêu hiệu năng và chi phí; nó không thay thế yêu cầu pháp lý về residency.

### Ví dụ phân biệt

Một ứng dụng phục vụ khách hàng tại Việt Nam lưu database ở region Singapore, chạy worker tại region đó và gửi bản sao backup tới một region khác:

- Vị trí database cho biết một phần residency.
- Worker ở Singapore cho biết processing location.
- Backup ở region thứ hai tạo thêm một bản dữ liệu cần được đánh giá.
- Nhân viên hỗ trợ truy cập database từ quốc gia khác tạo thêm câu hỏi về quyền truy cập xuyên biên giới và sovereignty.
- Việc database gần worker có thể cải thiện data locality nhưng không chứng minh đáp ứng yêu cầu localization.

Không thể kết luận cấu hình trên phù hợp hay không nếu chưa biết phân loại dữ liệu, hợp đồng, luật áp dụng, yêu cầu khách hàng và chính sách của tổ chức.

## 2. Xác định phạm vi yêu cầu lưu trú

Một yêu cầu như “dữ liệu phải ở trong quốc gia X” còn quá chung để triển khai. Cần làm rõ dữ liệu nào, thao tác nào, đối tượng nào và phạm vi dịch vụ nào bị ràng buộc.

### Các câu hỏi cần làm rõ

1. **Đối tượng dữ liệu:** dữ liệu cá nhân, hồ sơ tài chính, dữ liệu y tế, dữ liệu công, dữ liệu nội bộ, source code, model weights hay dữ liệu đã ẩn danh?
2. **Phạm vi địa lý:** quốc gia, vùng lãnh thổ, cloud region, availability zone hay địa điểm trung tâm dữ liệu?
3. **Trạng thái dữ liệu:** dữ liệu gốc, bản sao, backup, snapshot, cache, log, bản xuất, bản trung gian và dữ liệu đã xóa?
4. **Hoạt động:** lưu trữ, xử lý, truyền, sao lưu, khôi phục, hiển thị, hỗ trợ vận hành hay truy cập quản trị?
5. **Chủ thể truy cập:** người dùng, workload, nhà cung cấp, đội hỗ trợ, nhà thầu hoặc dịch vụ bên thứ ba?
6. **Thời hạn:** yêu cầu áp dụng liên tục, theo thời gian hợp đồng, trong thời gian xử lý hay cả thời gian lưu trữ sau khi kết thúc?
7. **Ngoại lệ:** có cho phép DR, hỗ trợ khẩn cấp, chuyển dữ liệu đã mã hóa hoặc dữ liệu đã khử định danh không?
8. **Bằng chứng:** cần cấu hình, audit log, chứng nhận, báo cáo region hay hồ sơ kiểm toán nào?

### Phân biệt yêu cầu theo loại dữ liệu

Không nên áp dụng một quy tắc địa lý cho toàn bộ workload nếu dữ liệu có nhiều mức nhạy cảm. Có thể lập ma trận:

| Loại dữ liệu | Ví dụ | Yêu cầu vị trí cần xác định |
|---|---|---|
| Dữ liệu nghiệp vụ chính | Hồ sơ khách hàng, giao dịch | Region lưu trữ, xử lý, backup và quyền truy cập |
| Dữ liệu định danh | Tên, địa chỉ, số định danh | Phạm vi lưu trữ, truy cập, truyền và xóa |
| Dữ liệu đã giả danh/ẩn danh | Token thay thế ID, thống kê tổng hợp | Tiêu chí xác định còn khả năng nhận diện hay không |
| Log và audit | Request ID, IP, principal, payload metadata | Region log, retention, SIEM export và quyền xem |
| Telemetry | Trace, metric label, crash dump | Có chứa payload, identifier hoặc secret không |
| Cache và dữ liệu tạm | Redis, local disk, temporary file | Vị trí, TTL, cleanup và bản sao |
| Backup/snapshot | Database snapshot, disk image | Region, vault, replication, retention và restore location |
| Model/data artifact | Weights, feature store, dataset | Nguồn gốc, vị trí lưu, nơi tải và nơi inference/training |
| Secret và key material | API key, encryption key | Vị trí quản lý, quyền truy cập, backup và key residency |

Một log chỉ chứa timestamp và trạng thái có thể ít nhạy cảm hơn log chứa request body, email hoặc IP. Cần phân loại theo nội dung thực tế và khả năng liên kết, không chỉ theo tên hệ thống tạo ra log.

## 3. Data inventory và data flow mapping

Muốn kiểm soát residency, trước hết phải biết dữ liệu đi qua những thành phần nào. Sơ đồ kiến trúc chỉ vẽ API và database thường chưa đủ; cần bao gồm các luồng phụ như log, metrics, backup, cache, replication, support tooling và CI/CD artifact.

### Lập inventory

Với mỗi tập dữ liệu, ghi nhận:

- Owner và business purpose.
- Data classification và tenant/subject scope.
- System of record và nguồn tạo dữ liệu.
- Storage service, account/project/subscription và region.
- Workload đọc/ghi và processing location.
- Luồng truyền ra ngoài, endpoint và bên nhận.
- Snapshot, backup, replica và retention.
- Encryption key, key owner và key location.
- Nhóm người dùng và workload có quyền truy cập.
- Yêu cầu xóa, export, audit và thời hạn lưu giữ.

### Lập bản đồ luồng

~~~mermaid
flowchart TD
    C["Client / data subject"] --> A["API tại Region A"]
    A --> F["Compute workload tại Region A"]
    F --> D[("Database tại Region A")]
    F --> O[("Object storage tại Region A")]
    F --> L["Logs / traces / metrics"]
    D --> B["Backup service"]
    O --> R["Replication / export"]
    L --> S["Central observability"]
    B --> DR["DR region"]
    R --> DR
~~~

Sơ đồ trên chỉ là khung phân tích. Mỗi mũi tên cần ghi loại dữ liệu, mục đích, giao thức, vùng nguồn/đích, mã hóa, quyền cho phép và thời hạn. Nếu một dịch vụ tự động replicate hoặc chuyển telemetry, cần đưa luồng đó vào inventory dù ứng dụng không gọi trực tiếp.

### Kiểm tra dữ liệu phát sinh gián tiếp

Những nguồn thường bị bỏ sót:

- Crash dump hoặc heap dump có thể chứa dữ liệu trong bộ nhớ.
- Trace span có thể ghi URL, query, header hoặc payload.
- Log của API Gateway, load balancer và WAF có thể lưu IP hoặc request metadata.
- Snapshot disk có thể chứa file tạm, swap hoặc cache.
- Container image có thể chứa dataset, model hoặc file cấu hình.
- CI artifact và build cache có thể chứa dữ liệu đầu vào.
- Support bundle và diagnostic package có thể được tải về máy hỗ trợ.
- Search index, data warehouse và feature store có thể tạo bản sao dữ liệu nghiệp vụ.

## 4. Chuyển yêu cầu thành policy kỹ thuật

Một yêu cầu residency có thể được mô tả thành các ràng buộc:

- Chỉ cho phép tạo compute và storage trong danh sách region được phê duyệt.
- Chỉ cho phép workload xử lý dữ liệu phân loại X kết nối tới storage cùng phạm vi.
- Cấm replication, export hoặc backup ra ngoài vùng được phép.
- Chỉ cho phép identity thuộc nhóm/tenant được phê duyệt truy cập dữ liệu.
- Log, trace và audit chứa dữ liệu nhạy cảm phải được lưu trong hệ thống đúng địa điểm.
- DR chỉ được dùng vùng dự phòng đã được đánh giá và phê duyệt.
- Thay đổi region hoặc luồng dữ liệu cần quy trình review và bằng chứng.

### Phân loại policy

| Lớp kiểm soát | Mục tiêu | Ví dụ |
|---|---|---|
| Preventive | Ngăn cấu hình vi phạm trước khi tạo tài nguyên | Deny region ngoài allowlist |
| Detective | Phát hiện tài nguyên hoặc luồng sai sau khi triển khai | Config rule, asset inventory, flow log |
| Corrective | Khắc phục vi phạm có kiểm soát | Cô lập workload, chuyển dữ liệu, thu hồi quyền |
| Governance | Quy định ai phê duyệt và ngoại lệ | Owner, ticket, expiry, risk acceptance |

Không nên chỉ dựa vào detective control nếu có thể ngăn triển khai sai ngay từ đầu. Tuy vậy, preventive policy không thay thế kiểm tra các luồng dữ liệu do dịch vụ managed hoặc cấu hình ứng dụng tạo ra.

### Region allowlist và deny-by-default

Tổ chức có thể xác định danh sách region được phép cho từng loại workload. Một policy mặc định từ chối region ngoài danh sách giúp giảm lỗi cấu hình do chọn nhầm region. Allowlist cần được duy trì theo danh mục region được tổ chức đánh giá, không nên tự động cho phép mọi region mới do cloud provider công bố.

Region allowlist không phải bằng chứng đầy đủ về residency. Một workload chạy ở region được phép vẫn có thể gửi log, backup hoặc dữ liệu tới endpoint ngoài phạm vi.

## 5. Kiểm soát vị trí của compute

Compute có thể xuất hiện dưới nhiều hình thức: VM, autoscaling group, container service, Kubernetes node, serverless function, managed job, GPU cluster hoặc dịch vụ inference. Mỗi loại có cách chọn region và cơ chế placement khác nhau.

### Máy ảo và node pool

Với VM:

- Chọn region và zone trong cấu hình resource.
- Giới hạn instance family và host location nếu có yêu cầu về loại hạ tầng.
- Đưa autoscaling group vào subnet và zone được phê duyệt.
- Kiểm soát disk, snapshot, image và backup cùng phạm vi địa lý.
- Giám sát việc tạo VM qua console, API, IaC và các tài khoản con.

Autoscaling không được phép tự chọn region ngoài allowlist chỉ để tìm capacity rẻ hoặc còn quota. Nếu vùng được phép hết capacity, cần có quy trình fallback đã phê duyệt.

### Container và managed container service

Với container:

- Chọn cluster hoặc service đặt trong region đã được phê duyệt.
- Kiểm tra registry và image layer được lưu ở đâu.
- Kiểm soát log driver, tracing exporter và artifact download.
- Xác minh service mesh, ingress, egress và sidecar không chuyển dữ liệu ngoài phạm vi.
- Xác định nơi lưu volume, persistent disk và ephemeral storage.

Một cluster nằm trong region hợp lệ nhưng pull image từ registry khác vùng vẫn tạo luồng dữ liệu xuyên vùng. Cần đánh giá cả vị trí image registry, cache và bản sao.

### Kubernetes node placement

Kubernetes có thể giới hạn vị trí Pod bằng node label, node affinity, taint/toleration và admission policy. Tuy nhiên, node label tự gán không phải bằng chứng địa lý đáng tin nếu người dùng workload có thể sửa label.

Ví dụ node pool đã được nền tảng hoặc automation đáng tin gắn label location:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: regulated-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: regulated-api
  template:
    metadata:
      labels:
        app: regulated-api
    spec:
      nodeSelector:
        topology.example.com/data-zone: approved-region-a
      containers:
        - name: api
          image: registry.example.com/regulated-api:2.4.0
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
~~~

Label topology.example.com/data-zone trong ví dụ là label nội bộ, không phải label Kubernetes chuẩn và phải được gắn bởi thành phần được tin cậy. Với ràng buộc địa lý, nên kết hợp:

- Node pool được tạo trong region đã phê duyệt.
- Label/taint do platform team quản lý và không cho tenant sửa.
- Node affinity bắt buộc (requiredDuringSchedulingIgnoredDuringExecution) khi cần ràng buộc cứng.
- Admission policy từ chối Pod không có placement constraint phù hợp.
- Kiểm soát cluster autoscaler chỉ mở rộng node pool được phép.

Nếu Pod bị reschedule, scheduler vẫn phải tuân thủ constraint. Cần kiểm tra cả init container, sidecar, DaemonSet và ephemeral workload.

### Serverless function và managed job

Với serverless:

- Chọn region của function và các trigger liên quan.
- Xác định region của event source, queue, scheduler và destination.
- Kiểm tra nơi lưu environment, deployment package và log.
- Kiểm soát invocation cross-region và quyền truy cập dịch vụ ở vùng khác.
- Xác minh managed runtime có xử lý hoặc lưu metadata ở địa điểm nào theo tài liệu dịch vụ.

Một function đặt trong region A nhưng đọc dữ liệu từ bucket region B vẫn có xử lý dữ liệu ở A và truyền dữ liệu qua ranh giới. Cần đánh giá theo định nghĩa yêu cầu cụ thể.

### Accelerator và inference workload

GPU/accelerator pool cũng là compute location. Với workload suy luận hoặc huấn luyện:

- Model weights và dataset cần có vị trí lưu được phê duyệt.
- Node GPU, host memory, scratch disk và cache phải nằm trong phạm vi.
- Serving endpoint và log request phải tuân thủ cùng phân loại dữ liệu.
- Model artifact tải từ registry cần xác định nguồn và region.
- Multi-region inference phải có chính sách phân vùng dữ liệu và routing rõ ràng.

## 6. Kiểm soát storage, snapshot và backup

Chọn region cho database hoặc bucket chỉ kiểm soát vị trí bản dữ liệu chính. Cần xác minh các cơ chế tạo bản sao tự động:

- Read replica và cross-region replica.
- Backup vault, snapshot copy và archive tier.
- Object replication và versioning.
- Database export, dump và data pipeline.
- Disk image và machine image.
- Cache persistence và recovery file.
- Search index, analytics store và data warehouse.

### Backup không tự động được miễn trừ

Một bản backup vẫn chứa dữ liệu gốc hoặc dữ liệu có thể khôi phục. Nếu yêu cầu residency áp dụng cho dữ liệu lưu trữ, backup thường cần được đánh giá cùng phạm vi. Không giả định backup ở region khác là hợp lệ chỉ vì nó không được truy cập thường xuyên.

### Thiết kế backup theo vùng

Có thể dùng:

- Backup trong cùng region, tách account/project và security boundary.
- Backup đa zone trong cùng region nếu đáp ứng yêu cầu availability.
- Backup cross-region chỉ tới region đã được phê duyệt.
- Immutable backup hoặc vault lock để chống xóa/sửa.
- Encryption bằng key phù hợp với yêu cầu quản lý và địa điểm.

Nếu chỉ cho phép dữ liệu ở một quốc gia, DR có thể cần triển khai trong cùng quốc gia hoặc vùng lãnh thổ được phép. Điều này có thể làm giảm số lựa chọn region và ảnh hưởng RTO/RPO. Cần ghi rõ trade-off và xin phê duyệt nếu phương án DR không đáp ứng đồng thời mọi yêu cầu.

### Kiểm tra đường phục hồi

Không chỉ kiểm tra nơi backup được ghi. Hãy kiểm thử:

1. Ai có quyền restore?
2. Restore có thể chọn region ngoài allowlist không?
3. Bản restore tạm thời xuất hiện ở đâu?
4. Log và snapshot trung gian được giữ bao lâu?
5. Key có thể được truy cập ở region DR không?
6. Sau khi khôi phục, traffic và replication có tạo luồng xuyên vùng không?
7. Bản dữ liệu tạm và bản cũ được xóa theo quy trình nào?

## 7. Kiểm soát log, telemetry và observability

Log và telemetry thường bị bỏ quên vì được xem là dữ liệu vận hành. Trên thực tế, chúng có thể chứa dữ liệu cá nhân, identifier, nội dung request, tên file, SQL statement, URL query, token hoặc stack trace.

### Các thành phần cần rà soát

- Application log và audit log.
- API Gateway, load balancer, WAF và firewall log.
- Distributed trace và span attribute.
- Metrics label và exemplars.
- Crash dump, heap dump và diagnostic bundle.
- APM/SaaS exporter và incident management integration.
- SIEM, data lake và log archive.

### Giảm dữ liệu nhạy cảm trước khi xuất log

- Không ghi raw request body nếu không cần.
- Redact token, email, số định danh và secret.
- Dùng request ID hoặc pseudonymous identifier khi phù hợp.
- Giới hạn label cardinality để tránh đưa identifier vào metric.
- Đặt sampling và retention theo phân loại.
- Chỉ export tới observability endpoint đã được phê duyệt.

### Địa điểm của nền tảng quan sát

Một workload có thể chạy trong region được phép nhưng gửi telemetry tới SaaS control plane ở nơi khác. Cần xác minh region của log workspace, trace backend, backup và support access. Nếu nhà cung cấp có lựa chọn data residency riêng cho telemetry, phải cấu hình và lưu bằng chứng tương ứng.

Không đưa dữ liệu nhạy cảm vào metric label hoặc trace chỉ để thuận tiện debug. Khi cần điều tra, dùng cơ chế truy cập tạm thời, được phê duyệt và có audit.

## 8. Network egress và luồng dữ liệu xuyên vùng

Kiểm soát vị trí thực thi không thể tách rời kiểm soát network. Workload ở region được phê duyệt vẫn có thể gửi dữ liệu tới public endpoint hoặc dịch vụ ở quốc gia khác.

### Xác định egress

Lập danh sách:

- Destination IP, hostname, service endpoint và region.
- Protocol, port và loại dữ liệu truyền.
- Lý do nghiệp vụ và owner.
- Có mã hóa TLS/mTLS không.
- Dữ liệu có được lưu ở destination không.
- Destination có subprocessors hoặc replica ở nơi khác không.

### Các cơ chế kiểm soát

- Egress firewall hoặc cloud network firewall.
- Route table và NAT gateway được quản lý.
- Private endpoint/PrivateLink/service endpoint cho dịch vụ cloud.
- DNS policy và kiểm soát domain allowlist.
- Service mesh egress gateway.
- VPC flow log hoặc network telemetry để phát hiện destination bất thường.
- DLP hoặc proxy inspection khi được phép và phù hợp.

Private connectivity giúp tránh public Internet và giảm bề mặt tấn công, nhưng không tự bảo đảm residency. Một private endpoint vẫn có thể trỏ tới service ở region khác hoặc dịch vụ có control plane/data processing ở phạm vi khác. Cần xác minh vị trí thực tế và semantics của dịch vụ.

### Cross-region API và replication

Khi workload gọi API ở region khác, cần xác định request có chứa dữ liệu thuộc phạm vi ràng buộc không. Với replication, cần biết dữ liệu nào được sao chép, thời điểm, thời hạn và quyền truy cập ở đích. Nếu chỉ metadata không nhạy cảm được truyền, vẫn cần kiểm tra liệu metadata có thể liên kết để nhận diện chủ thể hay không.

## 9. Quyền truy cập quản trị và hỗ trợ xuyên biên giới

Data residency không chỉ là nơi lưu disk. Quyền truy cập của nhân viên vận hành, nhà cung cấp và đội hỗ trợ có thể tạo ra một ranh giới khác.

Hãy xác định:

- Ai có thể mở console, shell, remote session hoặc database query?
- Support engineer có thể xem payload, log hoặc snapshot không?
- Quyền truy cập được cấp theo quốc gia, nhóm, thời gian hoặc ticket nào?
- Có thể dùng just-in-time access và approval không?
- Session có được ghi lại và audit không?
- Có thể dùng masked data hoặc diagnostic metadata thay cho dữ liệu gốc không?
- Nhà cung cấp có subprocessors hoặc support locations nào theo hợp đồng?

### Just-in-time và break-glass

Truy cập khẩn cấp nên có:

1. Sự kiện hoặc ticket có lý do cụ thể.
2. Người phê duyệt độc lập theo mức rủi ro.
3. Quyền tối thiểu và thời hạn ngắn.
4. MFA và xác thực mạnh.
5. Session logging hoặc audit trail.
6. Thu hồi tự động khi hết hạn.
7. Review sau sự cố.

Break-glass không nên là tài khoản dùng chung không kiểm soát. Nếu yêu cầu không cho phép truy cập từ một số địa điểm, cần thực thi bằng điều kiện identity/network và quy trình hỗ trợ phù hợp; không chỉ ghi trong runbook.

### Encryption và key control

Encryption at rest và in transit giảm nguy cơ lộ dữ liệu, nhưng không thay thế yêu cầu residency. Cần xem ai kiểm soát key, key được lưu ở đâu, ai có thể gọi decrypt và dịch vụ có thể xử lý plaintext ở đâu.

Customer-managed key có thể tăng quyền kiểm soát key lifecycle và audit, nhưng không tự chứng minh dữ liệu không thể truy cập từ ngoài vùng. Hãy phân tích quyền decrypt, key replication, HSM region, backup key và quy trình khôi phục.

## 10. Region selection và service eligibility

Không phải mọi cloud service, feature hoặc instance family đều có ở mọi region. Khi chọn vùng, cần đánh giá đồng thời yêu cầu địa lý và khả năng kỹ thuật.

### Ma trận lựa chọn region

| Tiêu chí | Câu hỏi đánh giá |
|---|---|
| Residency | Region có nằm trong phạm vi được phép không? |
| Service availability | Dịch vụ compute, storage, database, key management và logging có sẵn không? |
| Instance/accelerator | Loại CPU/GPU cần thiết có quota và capacity không? |
| Network | Có private connectivity và endpoint phù hợp không? |
| DR | Có vùng dự phòng được phê duyệt đáp ứng RTO/RPO không? |
| Data transfer | Có phát sinh luồng hoặc chi phí cross-region không? |
| Support | Mô hình hỗ trợ và quyền truy cập có phù hợp không? |
| Audit | Có bằng chứng vị trí, log và policy đủ để kiểm toán không? |
| Cost | Giá compute, storage, network và license có chấp nhận được không? |

### Khi dịch vụ không có trong region được phép

Không nên tự động chuyển dữ liệu sang region khác chỉ để sử dụng feature còn thiếu. Các lựa chọn có thể gồm:

- Chọn dịch vụ hoặc instance khác đã có trong vùng.
- Chạy thành phần cần thiết trên VM/container tự quản lý trong vùng.
- Thiết kế giảm phụ thuộc feature đó.
- Chờ nhà cung cấp hỗ trợ region phù hợp.
- Xin phê duyệt ngoại lệ dựa trên đánh giá rủi ro và yêu cầu pháp lý/hợp đồng.

Nếu không có lựa chọn phù hợp, phải ghi rõ constraint và quyết định kinh doanh. Không thể khẳng định tuân thủ khi dịch vụ cốt lõi xử lý dữ liệu ngoài phạm vi yêu cầu.

## 11. Kiểm soát region bằng policy tổ chức

Cloud provider thường có cơ chế policy cấp organization/account/project/subscription để giới hạn vị trí tạo tài nguyên. Tên gọi thay đổi theo nền tảng, nhưng mục tiêu là áp dụng guardrail tập trung.

### Các lớp policy thường gặp

- Allowed locations hoặc region restriction.
- Organization policy/Service Control Policy.
- IAM condition theo region hoặc resource location.
- Resource policy giới hạn nguồn và đích.
- Cloud governance rule hoặc policy-as-code.
- Admission policy cho Kubernetes.
- IaC policy check trong CI/CD.

### Nguyên tắc thiết kế

1. Xác định allowlist theo phân loại workload và data class.
2. Áp dụng ở cấp organization/account để tránh mỗi team tự chọn.
3. Dùng deny-by-default cho region không được phép.
4. Tách quyền phê duyệt ngoại lệ khỏi quyền deploy thường ngày.
5. Kiểm tra các dịch vụ không hỗ trợ location constraint giống compute.
6. Đưa policy vào version control và review như code.
7. Theo dõi policy drift và tài nguyên được tạo ngoài quy trình.

### Policy ví dụ dạng khai báo

Ví dụ YAML minh họa policy nội bộ cho pipeline kiểm tra IaC. Đây không phải schema chuẩn của một cloud provider; cần chuyển thành cú pháp policy engine mà tổ chức sử dụng.

~~~yaml
policy:
  name: compute-region-allowlist
  effect: deny
  applies_to:
    resource_types:
      - virtual_machine
      - kubernetes_node_pool
      - serverless_function
  allowed_locations:
    - approved-region-a
    - approved-region-b
  exception:
    requires:
      - owner
      - approval_ticket
      - expiry
      - data_classification
~~~

Policy cần được kiểm tra trên cả create và update. Một tài nguyên được tạo đúng region có thể bị thay đổi hoặc gắn với service ngoài vùng sau đó.

## 12. Kiểm soát vị trí trong Kubernetes

Trong Kubernetes, có nhiều cách biểu đạt vị trí và placement:

- Node labels cho region, zone và node pool.
- Node selector và required node affinity.
- Taint/toleration để cô lập node pool.
- Topology spread constraints để phân tán replica trong vùng cho phép.
- Admission controller để từ chối manifest không phù hợp.
- RBAC để giới hạn ai có thể sửa node label, namespace policy và workload.
- Cluster autoscaler/provisioner chỉ tạo node trong danh sách instance và region được phép.

### Không tin label do tenant tự khai báo

Một Pod có thể yêu cầu node label data-zone=approved-region-a, nhưng nếu người dùng có quyền sửa label trên node hoặc tự tạo node ở region khác rồi gắn label đó, ràng buộc sẽ mất ý nghĩa. Label địa lý cần được thiết lập bởi cloud controller hoặc platform automation được bảo vệ bằng RBAC.

### Admission policy

Admission policy có thể kiểm tra namespace, workload label, node selector, volume, image registry và service account trước khi nhận Pod. Ví dụ, workload mang nhãn data-class=restricted bắt buộc có node affinity vào node pool được phê duyệt và không được mount volume từ storage class ngoài danh sách.

Admission policy chỉ nhìn thấy object Kubernetes. Nó không tự xác minh vị trí thật của external database, registry, log sink hoặc endpoint. Cần kết hợp inventory và policy ở lớp cloud.

### Topology spread

Topology spread giúp phân tán replica theo zone để tăng availability, nhưng phải giới hạn trong các zone/region được phép. Nếu yêu cầu residency chỉ cho phép một region, có thể trải replica qua nhiều zone trong region đó; không tự mở rộng sang region khác chỉ để tăng availability.

## 13. Kiểm soát vị trí của serverless và managed services

Managed services giảm gánh nặng vận hành nhưng có thể trừu tượng hóa một số chi tiết vị trí. Trước khi dùng cho dữ liệu bị ràng buộc, cần xác minh:

- Region của resource endpoint và data plane.
- Nơi lưu metadata, backup và log.
- Cơ chế replication mặc định.
- Nơi xử lý support/diagnostic data.
- Có cấu hình multi-region hoặc global endpoint không.
- Control plane có thể đặt ở địa điểm khác với data plane hay không.
- Dịch vụ có cam kết residency riêng trong hợp đồng hay tài liệu không.

### Global endpoint và routing

Global load balancer, CDN, API gateway hoặc DNS-based routing có thể đưa request tới nhiều region. Nếu dữ liệu bị giới hạn, routing phải bảo đảm request chứa dữ liệu đó chỉ tới compute trong phạm vi. Cần kiểm tra failover tự động: khi region chính lỗi, hệ thống có thể chuyển traffic sang vùng không được phép hay không.

### Event bus và queue

Queue hoặc event bus có thể nằm ở region riêng. Khi function ở region A đọc message từ queue B, payload được truyền qua ranh giới. Cần xác định message chứa dữ liệu gì, retention ở đâu và dead-letter queue có cùng chính sách không.

Dead-letter queue thường bị bỏ sót trong data flow. Nó có thể giữ payload lỗi lâu hơn queue chính và có quyền truy cập rộng hơn.

## 14. Cross-region replication, DR và RTO/RPO

Disaster recovery thường khuyến nghị bản sao ở region khác để tránh sự cố vùng. Nhưng với yêu cầu residency, region DR cũng phải nằm trong phạm vi được phép hoặc có ngoại lệ rõ ràng.

### RTO và RPO

- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường biểu diễn bằng thời gian kể từ lần đồng bộ gần nhất.

Residency constraint có thể giới hạn số region DR khả dụng, làm tăng RTO/RPO hoặc chi phí. Cần thiết kế theo khả năng thực tế của provider và chính sách được phê duyệt.

### Các mô hình DR

| Mô hình | Đặc điểm | Lưu ý về residency |
|---|---|---|
| Backup/restore cùng region | Bản backup trong cùng vùng địa lý | Có thể không chống được sự cố toàn region |
| Multi-zone | Replica hoặc backup ở zone khác trong cùng region | Kiểm tra zone độc lập và vị trí địa lý của region |
| Cross-region trong cùng quốc gia | Bản sao sang region khác nhưng cùng phạm vi quốc gia được phép | Xác minh service, contract và routing |
| Cross-border DR | Bản sao ra ngoài biên giới | Chỉ dùng khi có căn cứ và phê duyệt phù hợp |
| Active-active | Nhiều region cùng xử lý traffic | Phải kiểm soát nơi request và dữ liệu được gửi tới |

### Failover không được phá vỡ ràng buộc

Runbook DR cần chỉ rõ:

- Region/zone nào được phép nhận dữ liệu.
- Ai phê duyệt failover.
- Traffic routing có thể chuyển tới đâu.
- Key và secret có khả dụng tại vùng DR không.
- Replica và backup có nhất quán không.
- Log và audit của quá trình DR được lưu ở đâu.
- Sau khi phục hồi, dữ liệu tạm và replica ngoài phạm vi được xử lý thế nào.

Nếu không có DR region hợp lệ, tổ chức cần ghi nhận rủi ro availability và quyết định chấp nhận hoặc thay đổi yêu cầu. Không nên âm thầm sao chép dữ liệu sang vùng không được phép khi có sự cố.

## 15. Data residency trong pipeline CI/CD và artifact

Pipeline build/deploy cũng xử lý dữ liệu và có thể tạo bản sao ở nhiều nơi:

- Source code, configuration và IaC state.
- Build logs và test output.
- Container image, package, model weights.
- Build cache và artifact repository.
- Dataset test, fixture và bản dump production dùng để debug.
- Deployment package và crash report.

### Các biện pháp kiểm soát

- Chọn runner/agent và artifact store ở vị trí được phê duyệt.
- Không dùng dữ liệu production trong test nếu chưa được phép và chưa có biện pháp giảm thiểu.
- Redact secret và dữ liệu cá nhân khỏi build log.
- Pin registry và package mirror đã được phê duyệt.
- Giới hạn quyền tải artifact và truy cập IaC state.
- Đặt retention và xóa cache theo policy.
- Ghi nhận region của runner, registry, artifact store và deployment target.

Nếu runner ở region khác kéo source hoặc dataset nhạy cảm để build, đây vẫn là luồng dữ liệu cần đánh giá dù ứng dụng cuối cùng chạy đúng vị trí.

## 16. Policy-as-code và kiểm tra trước khi triển khai

Policy-as-code cho phép tự động kiểm tra cấu hình trước khi tạo tài nguyên. Các công cụ có thể kiểm tra IaC plan, Kubernetes manifest hoặc cloud resource configuration.

### Những điều kiện nên kiểm tra

- Region/location nằm trong allowlist theo data class.
- Resource có tag/label owner, data classification và environment.
- Database, bucket, disk và backup dùng location phù hợp.
- Encryption và key reference đã cấu hình.
- Cross-region replication chỉ tới destination được phép.
- Function, node pool và managed job không có global routing trái phép.
- Kubernetes Pod có placement constraint cho data class bị hạn chế.
- Image registry, log sink và artifact source nằm trong phạm vi.
- Ngoại lệ có ticket, owner, lý do và expiry.

### Ví dụ kiểm tra manifest Kubernetes bằng policy nội bộ

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: restricted-worker
  labels:
    data-class: restricted
    owner: risk-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: restricted-worker
  template:
    metadata:
      labels:
        app: restricted-worker
    spec:
      nodeSelector:
        topology.example.com/data-zone: approved-region-a
      containers:
        - name: worker
          image: registry.approved.example/restricted-worker:3.1.0
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: restricted-data
~~~

Manifest này minh họa placement và registry theo quy ước nội bộ. Policy engine cần kiểm tra cả PVC, StorageClass, PV topology và region thật của storage backend. Node selector không thể bảo đảm volume nằm cùng vùng nếu storage class hoặc CSI driver cho phép attach từ nơi khác.

### Fail build khi vi phạm

Trong CI, có thể áp dụng:

1. Parse IaC plan hoặc manifest.
2. Xác định data classification và owner.
3. Resolve location của resource.
4. So với allowlist và dependency map.
5. Fail pipeline khi có vi phạm hoặc thiếu metadata bắt buộc.
6. Cho phép exception chỉ khi có approval và expiry.

Không nên cho phép pipeline tự động “sửa” region khi không biết dữ liệu có thể di chuyển hợp pháp hay không. Việc chuyển dữ liệu cần migration plan và approval riêng.

## 17. Phát hiện drift và giám sát liên tục

Một cấu hình đúng tại thời điểm deploy có thể thay đổi sau đó. Người vận hành có thể tạo resource qua console, một automation có thể đổi region hoặc một dịch vụ có thể bật replication mặc định.

### Detective controls

- Asset inventory định kỳ ghi nhận location, owner và data classification.
- Config rule hoặc cloud posture management phát hiện region ngoài allowlist.
- Audit log theo dõi create/update/delete và policy change.
- Network flow log phát hiện kết nối tới destination không được phép.
- Storage access log phát hiện truy cập hoặc replication bất thường.
- Kubernetes admission/audit log theo dõi Pod placement và node pool.
- Alert khi backup, export hoặc log sink thay đổi location.

### Xử lý drift

Khi phát hiện resource sai vùng:

1. Xác định data class, owner và dữ liệu thực sự hiện diện.
2. Ngăn luồng dữ liệu tiếp tục mở rộng nếu cần và được phê duyệt.
3. Bảo toàn audit evidence.
4. Đánh giá nghĩa vụ thông báo và quy trình incident theo tổ chức.
5. Lập kế hoạch di chuyển hoặc xóa dữ liệu có kiểm soát.
6. Xác minh backup, replica, cache, log và bản sao còn lại.
7. Sửa root cause trong IaC, policy hoặc quyền deploy.
8. Kiểm tra lại và đóng incident theo quy trình.

Không nên xóa ngay resource vi phạm nếu chưa xác định ảnh hưởng tới dữ liệu, bằng chứng, khả năng khôi phục và yêu cầu lưu giữ.

## 18. Quản trị ngoại lệ

Một số tình huống có thể cần ngoại lệ: thiếu capacity trong region được phép, dịch vụ chưa hỗ trợ, sự cố DR hoặc yêu cầu hỗ trợ nhà cung cấp. Ngoại lệ phải được quản trị như một quyết định rủi ro có giới hạn.

Một exception record nên có:

- Resource/workload và data classification.
- Yêu cầu gốc và policy bị ngoại lệ.
- Region/source/destination cụ thể.
- Loại dữ liệu và thao tác được phép.
- Mục đích và lý do nghiệp vụ.
- Owner kỹ thuật và người phê duyệt rủi ro.
- Biện pháp bù trừ như encryption, masking, tokenization hoặc access restriction.
- Thời điểm bắt đầu, expiry và kế hoạch kết thúc.
- Cách giám sát và bằng chứng.

Không dùng exception vô thời hạn hoặc wildcard region. Khi hết hạn, automation nên cảnh báo hoặc thu hồi quyền/luồng liên quan theo quy trình đã phê duyệt.

## 19. Ví dụ end-to-end: workload xử lý dữ liệu bị giới hạn vùng

Một ứng dụng xử lý hồ sơ khách hàng có yêu cầu nội bộ: dữ liệu định danh và nội dung hồ sơ chỉ được lưu và xử lý trong các region đã phê duyệt thuộc cùng phạm vi địa lý. Ứng dụng gồm API, worker, database, object storage, queue, log pipeline và backup.

### Thiết kế

1. Gắn data classification cho database record, object, queue payload và log có thể chứa dữ liệu.
2. Chọn account/project riêng cho workload và allowlist region.
3. Đặt API, worker, database, bucket, queue và key trong region được phê duyệt.
4. Dùng node pool và admission policy giới hạn Pod placement.
5. Chặn replication và export sang destination ngoài allowlist.
6. Cấu hình log redaction và log sink cùng phạm vi.
7. Đặt backup trong region/zone được phép và kiểm thử restore.
8. Giới hạn support access bằng JIT, approval và audit.
9. Kiểm tra runner, image registry và IaC state không kéo dữ liệu nhạy cảm ra ngoài.
10. Thu thập asset inventory, policy evaluation và audit evidence.

### Sơ đồ luồng dữ liệu

~~~mermaid
flowchart TD
    U["Client"] --> API["API / compute trong vùng được phép"]
    API --> Q["Queue trong vùng"]
    Q --> W["Worker trong node pool được kiểm soát"]
    W --> DB[("Database cùng phạm vi")]
    W --> OBJ[("Object storage cùng phạm vi")]
    DB --> BK["Backup vault được phê duyệt"]
    OBJ --> BK
    API --> LOG["Log đã redaction"]
    W --> LOG
    LOG --> OBS["Observability workspace được phê duyệt"]
    POL["Organization policy + admission + egress policy"] -. "Ràng buộc" .-> API
    POL -. "Ràng buộc" .-> W
    POL -. "Ràng buộc" .-> DB
~~~

### Kiểm thử

- Tạo VM hoặc node pool ở region không được phép phải bị policy từ chối.
- Tạo Pod restricted không có node affinity phải bị admission policy từ chối.
- Cấu hình replication tới bucket ngoài vùng phải bị chặn.
- Log chứa field nhạy cảm phải được redact trước khi export.
- Restore backup phải chỉ cho phép destination hợp lệ.
- Principal không được phê duyệt không thể đọc dữ liệu hoặc mở support session.
- Thay đổi region qua console phải tạo audit event và cảnh báo.

Ví dụ này mô tả cách chuyển một yêu cầu thành nhiều guardrail. Nó không khẳng định một cấu hình cụ thể đáp ứng luật của mọi quốc gia; yêu cầu pháp lý/hợp đồng cần được chủ sở hữu và bộ phận có thẩm quyền diễn giải trước khi triển khai.

## 20. Bằng chứng tuân thủ và audit

Để chứng minh kiểm soát đang hoạt động, cần lưu bằng chứng có thể truy xuất:

| Bằng chứng | Nội dung chứng minh |
|---|---|
| Cloud asset inventory | Resource ID, account/project, region, zone, owner, data class |
| Organization policy | Region allowlist và deny rule đang áp dụng |
| IaC plan/review | Thay đổi location được kiểm tra trước deploy |
| Kubernetes admission log | Workload bị từ chối hoặc chấp nhận theo placement policy |
| Network flow log | Luồng egress và destination thực tế |
| Storage replication configuration | Destination, encryption, retention và status |
| Backup/restore report | Vị trí backup và nơi phục hồi |
| IAM/access audit | Principal, thời điểm, resource và thao tác truy cập |
| Exception register | Ngoại lệ, approval, expiry và biện pháp bù trừ |
| Incident record | Vi phạm, xử lý, root cause và bằng chứng đóng sự cố |

Evidence cần có timestamp, nguồn, owner và retention phù hợp. Ảnh chụp console đơn lẻ thường không đủ vì có thể lỗi thời; ưu tiên export cấu hình, audit log và báo cáo inventory có thể tái lập.

## 21. Các lỗi thường gặp

1. **Chỉ chọn region cho VM:** bỏ sót database, backup, log, cache, registry và telemetry.
2. **Đồng nhất residency với sovereignty:** bỏ qua luật áp dụng, quyền truy cập và mô hình nhà cung cấp.
3. **Cho phép mọi region mới:** allowlist tự mở rộng mà không có review.
4. **Tin node label do tenant tự gắn:** placement constraint có thể bị giả mạo.
5. **Không kiểm tra volume topology:** Pod đúng node nhưng persistent storage ở vùng khác.
6. **Quên dead-letter queue:** payload lỗi được giữ ở nơi khác hoặc retention lâu hơn.
7. **Bỏ qua support access:** nhân viên hoặc subprocessors có thể truy cập dữ liệu từ địa điểm khác.
8. **Cho rằng encryption giải quyết residency:** ciphertext vẫn có thể thuộc phạm vi dữ liệu cần lưu trữ và quản lý.
9. **Không kiểm tra failover:** hệ thống tự chuyển traffic sang region không được phép.
10. **Dùng global endpoint không giới hạn:** request có thể tới compute ngoài phạm vi.
11. **Không phân loại telemetry:** trace và crash dump có thể chứa dữ liệu nhạy cảm.
12. **Không kiểm thử restore:** backup đúng vị trí nhưng quy trình restore tạo bản sao sai vùng.
13. **Chỉ kiểm tra lúc deploy:** drift do console, API hoặc automation không bị phát hiện.
14. **Ngoại lệ không hết hạn:** ràng buộc tạm thời trở thành quyền lâu dài.
15. **Tự động di chuyển dữ liệu khi policy fail:** có thể tạo thêm vi phạm hoặc mất dữ liệu.

## 22. Checklist thiết kế và vận hành

- [ ] Yêu cầu residency được diễn giải thành dữ liệu, hoạt động và phạm vi địa lý cụ thể.
- [ ] Data classification và owner được gắn cho workload và tài nguyên liên quan.
- [ ] Inventory bao gồm database, object, queue, cache, log, telemetry, backup và artifact.
- [ ] Data flow map ghi rõ source, destination, region, purpose và loại dữ liệu.
- [ ] Region allowlist được phê duyệt và quản lý tập trung.
- [ ] Organization policy ngăn tạo compute/storage ngoài vùng cho phép.
- [ ] VM, node pool, serverless, managed job và accelerator có placement constraint phù hợp.
- [ ] Kubernetes node labels do platform control quản lý; admission policy kiểm tra workload.
- [ ] PVC, PV, StorageClass và CSI topology phù hợp với vùng.
- [ ] Registry, image, model artifact, CI runner và build cache được đánh giá.
- [ ] Backup, snapshot, replica và DR destination đã được phê duyệt.
- [ ] Log, trace, metrics và crash dump được phân loại, redaction và lưu đúng vùng.
- [ ] Egress, private endpoint, global routing và cross-region API được kiểm soát.
- [ ] Support access, break-glass và key management có audit.
- [ ] Failover/restore được kiểm thử mà không vi phạm phạm vi địa lý.
- [ ] Policy-as-code chạy trong CI và phát hiện drift sau deploy.
- [ ] Exception có owner, approval, expiry và biện pháp bù trừ.
- [ ] Bằng chứng audit được lưu, có timestamp và có thể truy xuất.
- [ ] Có runbook xử lý resource sai vùng và bản sao dữ liệu ngoài phạm vi.

## 23. Bài tập vận dụng

Một tổ chức triển khai workload xử lý hồ sơ khách hàng. Chính sách nội bộ yêu cầu dữ liệu định danh chỉ được lưu và xử lý trong region A hoặc region B. Workload chạy bằng Kubernetes trong region A; database và object storage cũng ở A. Tuy nhiên:

- Backup database được copy sang region C.
- Log pipeline gửi trace sang một SaaS workspace ở region D.
- Cluster autoscaler được phép tạo node ở A và C.
- API Gateway dùng global routing và có thể failover sang C.
- Đội hỗ trợ có quyền đọc snapshot từ tài khoản quản trị chung.

1. Liệt kê các luồng hoặc thành phần có nguy cơ vi phạm yêu cầu.
2. Phân biệt vấn đề residency, processing location, access và data locality trong tình huống.
3. Đề xuất guardrail cho cluster autoscaler, API routing và backup.
4. Log/trace cần được thay đổi như thế nào trước khi gửi tới observability workspace?
5. Cần quản lý quyền support và snapshot ra sao?
6. Hãy đề xuất các kiểm thử tự động và bằng chứng audit để chứng minh cấu hình sau khi sửa.

Gợi ý: region C và D nằm ngoài allowlist theo chính sách giả định, nên backup, node pool, failover và telemetry cần được thay đổi hoặc có ngoại lệ được phê duyệt. Giới hạn node pool ở A/B; cấu hình routing chỉ failover tới vùng được phép; chuyển backup tới vault hợp lệ; redact payload/identifier trước khi export log và dùng workspace đúng vùng. Tách support identity, JIT access, approval, MFA và audit session. Kiểm thử policy deny, admission, replication destination, egress, restore location và failover target; lưu inventory, policy evaluation, flow log và access audit.

## Kết luận

Yêu cầu lưu trú dữ liệu cần được triển khai trên toàn bộ vòng đời dữ liệu và vị trí xử lý, không chỉ ở nơi đặt máy chủ chính. Hãy bắt đầu bằng phân loại dữ liệu và data flow map, sau đó áp dụng region allowlist, policy tổ chức, placement constraint, kiểm soát storage/backup, egress, telemetry và support access. DR và failover phải tuân thủ cùng ranh giới hoặc có ngoại lệ được phê duyệt. Policy-as-code, giám sát drift và bằng chứng audit giúp duy trì kiểm soát sau khi workload đã đi vào vận hành.
