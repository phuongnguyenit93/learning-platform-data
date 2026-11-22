# Thiết kế vượt nhu cầu và thiếu người chịu trách nhiệm vận hành

## 1. Vì sao một kiến trúc “đẹp” vẫn có thể thất bại?

Một kiến trúc đám mây không thành công chỉ nhờ có nhiều dịch vụ hiện đại, số lượng microservice lớn hoặc sơ đồ dự phòng phức tạp. Kiến trúc phải **đáp ứng nhu cầu nghiệp vụ được chứng minh**, đồng thời được một nhóm có đủ quyền hạn, công cụ và năng lực **vận hành trong suốt vòng đời**.

Trong học phần **CLOUD_ARCHITECTURE**, người học đi từ yêu cầu nghiệp vụ tới lựa chọn **mạng, compute, dữ liệu và mô hình triển khai**; mọi lựa chọn đều có đánh đổi về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**. Hai phản mẫu (antipattern) dưới đây thường xuất hiện cùng nhau:

1. **Thiết kế vượt nhu cầu (overengineering):** xây dựng quá nhiều thành phần, lớp trừu tượng hoặc cơ chế dự phòng khi chưa có yêu cầu, bằng chứng hay năng lực tương xứng.
2. **Thiếu người chịu trách nhiệm vận hành (unclear operational ownership):** hệ thống có thể triển khai được nhưng không có người/nhóm được giao rõ trách nhiệm theo dõi, xử lý sự cố, khôi phục, vá lỗi, kiểm soát chi phí và cải tiến.

Hai phản mẫu có thể độc lập: một hệ thống monolith đơn giản vẫn có thể “vô chủ”, còn một hệ thống rất phức tạp vẫn có đội vận hành chuyên nghiệp. Tuy nhiên, khi kết hợp, **độ phức tạp tăng trong khi năng lực chịu trách nhiệm không tăng tương ứng**, khiến sự cố lan rộng và việc sửa chữa chậm lại.

> **Nguyên tắc:** Kiến trúc tốt là kiến trúc **đủ cho mục tiêu hiện tại, có đường nâng cấp rõ ràng và vận hành được bằng nguồn lực thực tế**.

## 2. Nhận diện thiết kế vượt nhu cầu

**Overengineering không có nghĩa là dùng công nghệ phức tạp thì sai.** Một kiến trúc đa vùng, multi-region active-active hoặc giao dịch phân tán có thể hợp lý với dịch vụ yêu cầu tính sẵn sàng cực cao. Nó trở thành phản mẫu khi chi phí, rủi ro và công vận hành cao hơn giá trị nó mang lại ở **bối cảnh cụ thể**.

### Những dấu hiệu thường gặp

| Dấu hiệu | Biểu hiện cụ thể | Cần kiểm chứng gì? |
|---|---|---|
| Tách quá nhiều dịch vụ | Một nhóm nhỏ duy trì hàng chục service, mỗi service có pipeline, database và API riêng | Có nhu cầu scale/release độc lập không? Ai sở hữu API và dữ liệu? |
| Thiết kế cho tải giả định quá lớn | Xây autoscaling đa tầng, hàng đợi, sharding, caching phức tạp khi chưa đo tải | Lưu lượng đỉnh, throughput và độ trễ thực tế là bao nhiêu? |
| Dự phòng vượt SLO | Triển khai active-active nhiều region dù nghiệp vụ chấp nhận dừng lâu hơn | RTO, RPO, tính nhất quán dữ liệu, khả năng diễn tập và ngân sách có yêu cầu không? |
| Quá nhiều lớp trung gian | Dữ liệu đi qua nhiều API gateway, broker, proxy, adapter và service mesh | Mỗi lớp giải quyết vấn đề có thể đo được nào? |
| Tự xây thay vì dùng dịch vụ có sẵn | Viết scheduler, cơ chế secret hoặc database replication riêng | Có yêu cầu không được dịch vụ quản lý đáp ứng? Ai bảo trì mã đó? |
| Công nghệ “theo xu hướng” | Dùng Kubernetes, event sourcing, CQRS hoặc microservices như mặc định | Lợi ích so với giải pháp đơn giản đã được chứng minh chưa? |
| Quá nhiều cấu hình tổng quát | Tạo framework để hỗ trợ nhiều kịch bản chưa từng phát sinh | Có người dùng thực tế cho từng nhánh mở rộng không? |
| Quy trình triển khai nặng nề | Mọi thay đổi nhỏ đều cần sửa nhiều repo, contract và hạ tầng | Lead time, tần suất phát hành và tỷ lệ lỗi thay đổi ra sao? |

Những dấu hiệu trên là **gợi ý điều tra**, chưa phải bằng chứng kết luận. Chẳng hạn service mesh có thể mang lại khả năng kiểm soát lưu lượng và danh tính dịch vụ ở quy mô lớn; vấn đề là sử dụng nó mà không có yêu cầu hay người vận hành tương xứng.

### Nguyên nhân gốc rễ

- **Nhầm “có thể cần sau này” với “đang cần”:** chọn công nghệ cho mức tải hoặc mô hình kinh doanh chưa có xác suất và mốc xác định.
- **Đo lường thành công bằng số công nghệ sử dụng:** nhiều dịch vụ được coi là trưởng thành dù lead time, chi phí hay sự cố tăng.
- **Sao chép kiến trúc tham chiếu:** bê nguyên thiết kế của doanh nghiệp lớn vào sản phẩm và đội ngũ nhỏ mà bỏ qua giả định gốc.
- **Thiếu dữ liệu đo:** chưa benchmark, chưa tính TCO, chưa có SLO nhưng vẫn tối ưu cho throughput hoặc tính sẵn sàng rất cao.
- **Tách vai trò thiết kế và vận hành:** người quyết định không phải trực đêm, vá lỗ hổng, điều tra incident hay chịu ngân sách.
- **Sợ thay đổi về sau:** tối đa hóa tính “tổng quát” ngay từ đầu, dù nhiều thành phần sẽ không bao giờ được dùng.

### Hậu quả kỹ thuật và nghiệp vụ

Mỗi thành phần mới thêm **dependency**, cấu hình, chính sách IAM, vùng lỗi, đường mạng, nhật ký, kênh cảnh báo, hợp đồng API và trách nhiệm nâng cấp. Số dịch vụ tăng cũng tăng số tương tác có thể lỗi giữa chúng.

Với microservices không được thiết kế và vận hành phù hợp, một request đơn giản có thể đi qua nhiều network hop, phát sinh timeout, retry chồng retry, lỗi nhất quán dữ liệu và khó truy vết. Với active-active multi-region, bài toán không dừng ở “nhân đôi hạ tầng”: cần giải quyết định tuyến, sao chép, split-brain, xung đột cập nhật, giới hạn RPO và thử failover.

Tác động thường thấy là **thời gian phát triển dài hơn**, **thời gian khắc phục sự cố tăng**, **chi phí hạ tầng và nhân lực khó dự báo** và cuối cùng **độ tin cậy thực tế thấp hơn thiết kế kỳ vọng**.

## 3. Nhận diện hệ thống thiếu người chịu trách nhiệm vận hành

Một workload “có người phát triển” chưa chắc **có chủ sở hữu vận hành**. Trách nhiệm vận hành cần gắn với **một nhóm được xác định**, có quyền truy cập, năng lực, lịch trực, ngân sách, công cụ và tiêu chí để ra quyết định.

### Những biểu hiện dễ bỏ sót

- Pipeline deploy chạy thành công, nhưng không ai nhận cảnh báo 5xx hoặc database đầy.
- Dashboard được tạo, nhưng không có ngưỡng cảnh báo, người nhận và hướng dẫn xử lý.
- Backup tồn tại theo cấu hình mặc định, nhưng chưa từng **khôi phục thử**; không rõ ai quyết định restore.
- Bộ phận platform coi database thuộc ứng dụng; đội ứng dụng tưởng database đã được platform quản lý.
- Secret, certificate, domain hoặc API token có thời hạn hết hạn nhưng không có lịch kiểm tra/đổi.
- Một dịch vụ tự động scale làm tăng hóa đơn đột biến nhưng không ai theo dõi quyền sở hữu chi phí.
- Khi bị tấn công, không biết nhóm nào có quyền khóa truy cập, xoay khóa hoặc tạm ngưng kết nối.
- Sau khi bàn giao sản phẩm hoặc người phát triển nghỉ việc, không có tài liệu và người thay thế.

**“Tất cả cùng chịu trách nhiệm”** thường làm trách nhiệm bị phân tán: nếu không chỉ rõ ai quyết định và ai thực hiện, mọi người có thể chờ người khác.

### Một bảng cần có cho mọi workload

| Trách nhiệm | Câu hỏi có thể xác minh |
|---|---|
| **Service owner** | Ai chịu trách nhiệm về SLO, trải nghiệm người dùng và ưu tiên xử lý rủi ro? |
| **Technical owner** | Ai có quyền duyệt thay đổi kiến trúc, nâng phiên bản và sửa lỗi? |
| **On-call responder** | Khi cảnh báo production xuất hiện lúc 02:00, ai nhận và phản hồi? Người dự phòng là ai? |
| **Data owner** | Ai quyết định phân loại dữ liệu, truy cập, retention, backup và yêu cầu phục hồi? |
| **Security owner/đầu mối** | Ai đánh giá lỗ hổng, phân quyền, secret và xử lý sự cố bảo mật cùng đội an ninh? |
| **Infrastructure/platform owner** | Ai quản lý cluster, network, IaC, quota, dịch vụ nền và sự cố liên quan? |
| **Cost owner** | Ai chịu ngân sách, nhận cảnh báo, phê duyệt scale và làm cost review? |
| **Incident commander** | Ai điều phối sự cố nghiêm trọng, truyền thông và ra quyết định rollback/failover? |

Các vai trò có thể nằm trong **cùng một nhóm nhỏ**, nhưng phải được chỉ định. Không nhất thiết cần tám người độc lập hoặc một chức danh chính thức cho từng hàng.

## 4. Vì sao hai phản mẫu khuếch đại lẫn nhau?

~~~mermaid
flowchart TD
    A["Yêu cầu chưa rõ hoặc thiếu đo lường"] --> B["Thêm dịch vụ / layer / cơ chế dự phòng"]
    B --> C["Tăng số dependency và điểm có thể lỗi"]
    C --> D["Cần thêm quan sát, bảo trì, diễn tập và phối hợp"]
    D --> E{"Đã giao owner, on-call và runbook?"}
    E -- "Chưa" --> F["Cảnh báo không ai xử lý / lỗi âm thầm"]
    F --> G["MTTR tăng, chi phí tăng, mất niềm tin"]
    G --> H["Thêm công cụ hoặc lớp chữa cháy"]
    H --> B
    E -- "Rồi" --> I["Đánh giá lại giá trị và đo hiệu quả"]
    I --> J["Đơn giản hóa hoặc tăng năng lực vận hành"]
~~~

Ví dụ: một công ty đưa một API nhỏ qua **API gateway → service mesh → ba service nội bộ → hai message broker → nhiều database**. Khi checkout chậm, log bị phân tán, retry xảy ra ở nhiều tầng và không ai sở hữu toàn bộ trải nghiệm người dùng. Mỗi đội nói “dịch vụ của tôi vẫn xanh”, trong khi giao dịch cuối cùng thất bại.

Sự cố này có **hai nguồn vấn đề khác nhau**: luồng xử lý không cần thiết bị phân mảnh (**thiết kế**) và không có đội chịu trách nhiệm cuối cùng cho giao dịch checkout (**vận hành**). Chỉ thêm dashboard hoặc thêm một broker sẽ không xử lý cả hai.

## 5. Phân tích yêu cầu trước khi quyết định độ phức tạp

Kiến trúc sư cần chuyển lời mô tả mơ hồ thành **mục tiêu đo được và ràng buộc phải tuân thủ**.

| Câu nói ban đầu | Làm rõ thành câu hỏi | Dữ liệu cần thu thập |
|---|---|---|
| “Phải scale vô hạn” | Tải đỉnh hiện tại và dự báo 12 tháng là bao nhiêu? | RPS/TPS, concurrency, p95/p99 latency, throughput |
| “Phải luôn online” | SLO khả dụng và số phút gián đoạn chấp nhận là bao nhiêu? | Lịch sử sự cố, doanh thu bị ảnh hưởng, availability target |
| “Không được mất dữ liệu” | RPO thực sự bằng 0 cho mọi dữ liệu hay chỉ một số giao dịch? | Phân loại dữ liệu, RPO/RTO theo luồng nghiệp vụ |
| “Phải có microservices” | Đội nào cần release/scale độc lập? Ranh giới dữ liệu ở đâu? | Team topology, lead time, tần suất thay đổi, hot spots |
| “Cloud giúp tiết kiệm” | So sánh chi phí nào, trong bao lâu, gồm nhân lực chưa? | TCO ba năm, license, network, dual-run, vận hành |
| “Dùng multi-region cho an toàn” | Cần chịu được mất cả region? Dữ liệu có thể đồng bộ theo cách nào? | BIA, RTO/RPO, residency, kịch bản failover thực nghiệm |

**BIA (Business Impact Analysis)** giúp lượng hóa thiệt hại khi dịch vụ ngừng và phân biệt yêu cầu bắt buộc với mong muốn. Không nên áp dụng cùng SLO/RTO/RPO cho trang nội bộ ít sử dụng và dịch vụ thanh toán quan trọng.

### SLO, error budget và ngưỡng thực tế

Với tháng 30 ngày, một SLO khả dụng **99,9%** tương ứng khoảng **43,2 phút** thời gian không khả dụng được phép; **99,99%** chỉ khoảng **4,32 phút**. Đây là tính toán minh họa dựa trên thời gian tháng; trong thực tế cần xác định **cách đo SLI**, phạm vi người dùng, cách tính downtime và ngoại lệ hợp lệ trước khi dùng error budget.

SLO cao hơn thường đòi hỏi khả năng tự phục hồi, kiểm soát thay đổi, dự phòng và diễn tập tương ứng. Đừng tuyên bố “bốn số chín” chỉ nhờ chọn nhiều availability zone; sự cố cấu hình, dependency, dữ liệu hoặc chính ứng dụng vẫn có thể làm dịch vụ ngừng.

## 6. Cách chọn kiến trúc vừa đủ và có đường phát triển

Áp dụng một lộ trình ra quyết định thực dụng:

1. **Chốt bất biến nghiệp vụ:** giao dịch quan trọng, độ đúng dữ liệu, RTO/RPO, residency, security và mức tải phải chịu.
2. **Đặt phương án đơn giản làm chuẩn:** kiến trúc ít thành phần nhất có thể đáp ứng bất biến và được đội ngũ vận hành.
3. **Đo hoặc thử phương án chuẩn:** kiểm thử tải, thử failover, backup/restore, chi phí ước lượng và tốc độ triển khai.
4. **Xác định điểm nghẽn có bằng chứng:** CPU, database connection, I/O, latency, release coupling, sự cố hoặc ràng buộc sản phẩm.
5. **Chỉ thêm độ phức tạp để giải quyết một vấn đề cụ thể:** cache cho đọc lặp, queue cho xử lý bất đồng bộ, partition cho dữ liệu lớn, tách service cho scaling/release độc lập.
6. **Đặt điều kiện kích hoạt nâng cấp:** ví dụ p95 vượt ngưỡng liên tục, tải đỉnh vượt năng lực đã benchmark, thời gian phát hành bị cản trở hoặc recovery drill không đạt RTO.
7. **Giao ownership trước khi vận hành thành phần mới:** xác định nhóm trực, runbook, cảnh báo, cost center và lộ trình rollback.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ + SLO + ràng buộc"] --> B["Kiến trúc đơn giản khả thi"]
    B --> C["Benchmark, failure drill, TCO, security review"]
    C --> D{"Có bằng chứng không đạt?"}
    D -- "Không" --> E["Triển khai, quan sát, hẹn mốc đánh giá"]
    D -- "Có" --> F["Xác định nút thắt hoặc rủi ro cụ thể"]
    F --> G["So sánh các phương án khắc phục"]
    G --> H{"Đội ngũ có thể vận hành phương án?"}
    H -- "Chưa" --> I["Đơn giản hóa / đào tạo / managed service"]
    I --> G
    H -- "Có" --> J["Thêm năng lực cần thiết và đo lại"]
    J --> C
~~~

### Một số lựa chọn bắt đầu hợp lý (tùy bối cảnh)

- **Compute:** một ứng dụng stateless theo mô hình modular monolith trên nền tảng managed compute thường dễ vận hành hơn hàng chục microservice khi đội còn nhỏ.
- **Dữ liệu:** bắt đầu bằng một database quản lý với backup, giám sát và HA theo RTO/RPO; chỉ sharding hoặc chia database khi nhu cầu phân tách và dung lượng được chứng minh.
- **Mạng:** phân tách public/private, IAM và policy theo rủi ro; chỉ thêm service mesh, private connection đặc thù hoặc nhiều vùng khi có yêu cầu tương ứng.
- **Tích hợp:** API đồng bộ đơn giản cho hoạt động cần phản hồi tức thì; hàng đợi bất đồng bộ khi cần tách tải hoặc chịu burst, cùng với idempotency và giám sát queue.
- **Triển khai:** pipeline CI/CD có kiểm thử, rollout và rollback rõ trước khi xây quy trình phức tạp.

**Đơn giản không có nghĩa là bỏ an toàn.** Mã hóa dữ liệu, phân quyền tối thiểu, backup/restore, giám sát, logging, quản lý secret và kiểm soát thay đổi vẫn là năng lực nền, ngay cả khi ứng dụng chỉ có một dịch vụ.

## 7. Thiết lập ownership: ai chịu trách nhiệm điều gì?

### 7.1. Phân biệt trách nhiệm nhà cung cấp cloud với đội sử dụng

Cloud áp dụng mô hình **shared responsibility**: nhà cung cấp chịu trách nhiệm một phần về hạ tầng dịch vụ, tổ chức sử dụng vẫn chịu trách nhiệm đáng kể đối với cấu hình, dữ liệu và ứng dụng. Ranh giới thay đổi theo IaaS, PaaS hay SaaS, và theo hợp đồng dịch vụ.

| Thành phần | Với VM/IaaS | Với managed database/PaaS |
|---|---|---|
| Cơ sở vật lý, hạ tầng cloud nền | Nhà cung cấp cloud | Nhà cung cấp cloud |
| OS, runtime, bản vá | Tổ chức quản lý VM/OS và ứng dụng | Nhà cung cấp quản lý phần dịch vụ theo phạm vi cam kết; tổ chức vẫn quản lý mã và cấu hình của mình |
| Cấu hình IAM, mạng, policy, secret | Tổ chức sử dụng | Tổ chức sử dụng |
| Schema, truy vấn, quyền dữ liệu, tính đúng | Tổ chức sử dụng | Tổ chức sử dụng |
| Backup/restore và RTO/RPO | Tổ chức thiết kế, cấu hình, diễn tập | Nhà cung cấp có thể vận hành cơ chế backup; tổ chức vẫn xác định mục tiêu, cấu hình và kiểm chứng phục hồi |
| Giám sát hiệu năng ứng dụng và incident | Tổ chức sử dụng | Tổ chức sử dụng, phối hợp nhà cung cấp khi sự cố thuộc dịch vụ nền |

Sử dụng dịch vụ quản lý giúp giảm **việc tự vận hành hạ tầng**, nhưng **không chuyển giao kết quả SLO của ứng dụng** cho nhà cung cấp. Đội sở hữu vẫn phải nắm business metrics, cấu hình, quyền, giới hạn quota, kiểm thử và ứng phó sự cố.

### 7.2. Một ma trận RACI tối thiểu

Giả sử có ba nhóm: **Sản phẩm (SP)**, **Ứng dụng (APP)** và **Platform/SRE (PLT)**; các vai trò chuyên trách về an ninh, tài chính có thể tham gia các quyết định. RACI gồm **R (Responsible: thực hiện)**, **A (Accountable: chịu trách nhiệm cuối cùng)**, **C (Consulted: cần tham vấn)**, **I (Informed: được thông báo)**.

| Hoạt động | SP | APP | PLT |
|---|---|---|---|
| Xác định SLO và ưu tiên nghiệp vụ | **A** | R | C |
| Chất lượng ứng dụng, release, rollback code | I | **A/R** | C |
| Quản lý cloud network, cluster, nền tảng dùng chung | I | C | **A/R** |
| Theo dõi sức khỏe dịch vụ từ đầu đến cuối | C | **A/R** | R |
| Backup/restore dữ liệu ứng dụng | C | **A** | R |
| Điều phối incident ảnh hưởng người dùng | I | **A/R** | R |
| Kiểm soát chi phí dịch vụ | **A** | R | C |

Đây là **ví dụ để thảo luận**, không phải cơ cấu bắt buộc. Mỗi hoạt động nên có **một người/vai trò A rõ ràng** để tránh “cả hai cùng có quyền nhưng không ai quyết”. Nếu nền tảng do bên thứ ba quản lý, hợp đồng hỗ trợ và đường leo thang cũng phải được ghi rõ.

### 7.3. Ownership cần trở thành dữ liệu quản trị

Mỗi workload production nên có bản ghi ở service catalog hoặc kho cấu hình tương đương:

~~~yaml
service: order-api
environment: production
business_owner: commerce-product
technical_owner: order-team
on_call_primary: order-team-primary
on_call_backup: platform-oncall
platform_owner: cloud-platform
data_owner: commerce-data
slo:
  availability: "99.9%"
  latency_p95_ms: 300
runbook: "internal://runbooks/order-api"
dashboard: "internal://dashboards/order-api"
incident_channel: "internal://incidents/order-api"
cost_center: "commerce"
last_dr_drill: "YYYY-MM-DD"
review_due: "YYYY-MM-DD"
~~~

Ví dụ trên là **mẫu cấu trúc minh họa**, không phải dữ liệu nội bộ hay địa chỉ có thể truy cập. Các ngưỡng SLO là giả định; cần được thống nhất với yêu cầu nghiệp vụ. Quan trọng hơn tên trường là **khả năng truy ra người nhận cảnh báo và người có quyền xử lý ngay khi có lỗi**. Bản ghi ownership phải được cập nhật khi thay đổi đội ngũ hoặc chuyển giao dịch vụ.

## 8. Operational readiness trước khi đưa hệ thống vào production

Một kiến trúc có thể chạy đúng khi demo nhưng chưa đạt mức **sẵn sàng vận hành**. Dùng một **production readiness review (PRR)** với bằng chứng cụ thể:

| Nhóm kiểm tra | Bằng chứng cần có | Người phải xác nhận |
|---|---|---|
| **Quyền sở hữu** | Service owner, nhóm trực chính/dự phòng, escalation, lịch trực khả dụng | APP + PLT |
| **SLO/SLI** | Định nghĩa tỷ lệ lỗi, latency, availability, chỉ số nghiệp vụ; ngưỡng cảnh báo | SP + APP |
| **Quan sát** | Dashboard, logs/trace có correlation ID, cảnh báo đã thử gửi tới người trực | APP |
| **Khôi phục** | Backup policy, restore test, failover drill, số liệu RTO/RPO | APP + PLT + data owner |
| **Bảo mật** | IAM, secret rotation, quét lỗ hổng, logging kiểm toán, kế hoạch ứng phó | APP + security |
| **Triển khai** | CI/CD, rollback, kiểm thử smoke, change approval theo mức rủi ro | APP |
| **Năng lực** | Benchmark tải, quota, capacity plan, giới hạn dependencies | APP + PLT |
| **Chi phí** | Dự toán tháng, tag/cost center, budget alert, scale limit | SP + APP + finance |
| **Tài liệu** | Runbook, sơ đồ phụ thuộc, điểm liên hệ bên ngoài, ADR | APP |

Không phải mục nào cũng do cùng một đội **thực hiện**, nhưng phải biết ai **chịu trách nhiệm cuối**. Việc thiếu một phép thử quan trọng cần dẫn tới quyết định rõ: sửa trước khi go-live, chấp nhận rủi ro có thời hạn, hoặc hoãn triển khai.

### Runbook trả lời được câu hỏi gì?

Một runbook tốt nên viết theo **triệu chứng có thể quan sát**, ví dụ “p95 latency vượt ngưỡng 10 phút” thay vì “lỗi database” chung chung:

1. Người nhận cảnh báo và cách xác minh đó là sự cố thực, tác động đến ai.
2. Dashboard/log/trace và câu lệnh kiểm tra **an toàn** để khoanh vùng.
3. Các thao tác giảm ảnh hưởng: rollback release, giảm concurrency, tắt feature flag, scale đúng giới hạn, chuyển lưu lượng khi được phép.
4. Các **điều kiện cấm**: không xóa dữ liệu, không failover khi replication chưa đạt điều kiện, không chạy migration schema không thể đảo ngược trong lúc chữa cháy.
5. Mốc leo thang và người có quyền quyết định; cách truyền thông cho người dùng.
6. Cách xác nhận dịch vụ hồi phục và tạo postmortem để ngăn tái diễn.

Khi mọi thao tác khẩn cấp chỉ nằm trong trí nhớ một cá nhân, rủi ro vận hành vẫn cao dù sơ đồ kiến trúc rất đơn giản.

## 9. Thiết kế vận hành theo các trụ cột Well-Architected

| Trụ cột | Rủi ro từ hai phản mẫu | Cách cải thiện có thể kiểm chứng |
|---|---|---|
| **Operational Excellence (Vận hành xuất sắc)** | Không có owner, runbook; phát hành cần phối hợp nhiều nhóm | Service catalog, on-call, IaC, CI/CD, PRR, game day và postmortem |
| **Security (Bảo mật)** | Nhiều thành phần tăng bề mặt tấn công; không ai sở hữu secret/patch | IAM tối thiểu, inventory, policy, phân quyền rõ, secret rotation, security owner |
| **Reliability (Độ tin cậy)** | Phụ thuộc lồng nhau, retry storm, không ai làm DR drill | SLO/RTO/RPO, backup/restore test, failure isolation, circuit breaker khi phù hợp, owner trực |
| **Performance Efficiency (Hiệu quả hiệu năng)** | Scale quá nhiều nhưng latency vẫn cao vì network hop và DB bottleneck | Benchmark, profiling, đo p95/p99, giới hạn concurrency, right-sizing |
| **Cost Optimization (Tối ưu chi phí)** | Hệ thống luôn bật nhiều cluster/region, tài nguyên không ai nhận | Cost allocation, budget alert, TCO, decommission, review tài nguyên nhàn rỗi |
| **Sustainability (Bền vững)** | Cấp phát tài nguyên vượt tải, duplicate pipeline và compute rảnh | Dùng theo nhu cầu, tăng tỷ lệ sử dụng tài nguyên, xóa tài nguyên dư |

**Chi phí vận hành ẩn** thường bao gồm thời gian nâng version, vá lỗ hổng, duy trì dashboard, diễn tập failover, debug phân tán, quản lý certificate/secret, xử lý sự cố và onboarding thành viên mới. Một dịch vụ cloud rẻ theo đơn giá có thể đắt về **TCO** nếu nhóm phải tự quản lý quá nhiều thành phần.

Một lựa chọn “đơn giản hơn” vẫn phải đáp ứng tất cả **ràng buộc cứng**. Ví dụ yêu cầu lưu trú dữ liệu, phục hồi giao dịch, audit hoặc cách ly tenant là điều kiện bắt buộc; không được bỏ chỉ vì muốn giảm số dịch vụ.

## 10. Tình huống minh họa: nền tảng đặt hàng phát triển nhanh

### Bối cảnh giả định

Một công ty bán lẻ có **5 lập trình viên**, không có SRE trực riêng, xử lý **10.000 đơn hàng/ngày** và lưu lượng tăng khoảng **4 lần** khi khuyến mãi. Ứng dụng gồm đặt hàng, catalog, tồn kho, thanh toán và gửi email; mục tiêu hiện tại là phát hành hai lần/tuần, giữ dữ liệu đơn hàng đúng và có đường khôi phục khi lỗi.

Các con số trong tình huống chỉ dùng để luyện quyết định kiến trúc; không chứng minh trước rằng một mô hình nào đủ công suất. Cần đo **peak RPS, tỉ lệ ghi, kích thước database, độ trễ thanh toán, khả năng chịu downtime và RTO/RPO**.

### Phương án A: kiến trúc vượt nhu cầu

Đội đề xuất **15 microservices**, mỗi dịch vụ có repo/pipeline/database riêng, message broker trung gian cho mọi thao tác, service mesh, ba cluster Kubernetes và active-active ở hai region. Trong khi đó, không có lịch on-call, nhiều dashboard không có alert, chưa diễn tập restore và không ai chịu hóa đơn liên vùng.

Giả sử yêu cầu nghiệp vụ chưa chứng minh cần phát hành/scale độc lập cho 15 miền, kiến trúc này có rủi ro:

- Một request checkout đi qua nhiều network hop và dependency; retry có thể khiến side effect bị lặp.
- Các thay đổi transaction đơn hàng, kho và thanh toán khó giữ nhất quán giữa database.
- Khi một service lỗi, không rõ ai chịu trách nhiệm trải nghiệm checkout từ đầu đến cuối.
- Active-active đòi hỏi quy tắc phân xử cập nhật và kiểm thử chuyển vùng; không chỉ là “bật một tùy chọn”.
- Chi phí nền cố định và nhân công vận hành tăng trước khi có giá trị đo được.

### Phương án B: kiến trúc vừa đủ có thể mở rộng

Khởi đầu bằng **modular monolith** có ranh giới module rõ (order, inventory, catalog, payment), chạy trên nền tảng managed compute có nhiều instance khi cần. Dùng **managed relational database** với backup, cấu hình HA theo RTO/RPO, cơ chế cache cho truy vấn đọc có tải đo được, và hàng đợi cho tác vụ không cần phản hồi tức thời như gửi email.

~~~mermaid
flowchart TB
    U["Khách hàng"] --> E["DNS / WAF / Load balancer"]
    E --> A["Ứng dụng modular monolith<br/>Order | Inventory | Catalog | Payment"]
    A --> DB[("Managed relational database<br/>backup + HA theo RTO/RPO")]
    A --> Q["Queue cho tác vụ bất đồng bộ"]
    Q --> W["Worker gửi email / tác vụ nền"]
    A -.-> OBS["Metrics / logs / tracing / alerts"]
    W -.-> OBS
    DB -.-> OBS
    OBS --> O["On-call ứng dụng + Platform"]
~~~

Đây là sơ đồ **logic tham khảo**. Đối với dữ liệu đặt hàng, nhóm phải chứng minh cách đảm bảo tính nhất quán giao dịch, độ đúng khi retry, quyền truy cập và quá trình phục hồi. Các thành phần như cache, queue, HA đa vùng khả dụng chỉ nên đưa vào khi nhu cầu và thử nghiệm tương ứng xác nhận.

**Lợi ích khả dĩ:** số bước deploy và điểm lỗi ban đầu giảm; đội nhỏ có thể hiểu toàn luồng checkout; vẫn mở rộng theo chiều ngang nếu ứng dụng đủ stateless, database và các thành phần chung không thành bottleneck. **Giới hạn:** không phù hợp vô điều kiện cho mọi tải; cần benchmark, load test và thiết kế module để tránh coupling.

### So sánh hai phương án theo bằng chứng

| Tiêu chí | A: nhiều microservice/multi-region | B: modular monolith + managed services |
|---|---|---|
| Đáp ứng tải hiện tại | Chưa chứng minh, phải benchmark | Chưa chứng minh, phải benchmark |
| Deploy và thay đổi | Nhiều pipeline/hợp đồng; có thể độc lập nếu tổ chức sẵn sàng | Ít thành phần hơn, nhưng phát hành ứng dụng cùng nhau |
| Độ tin cậy | Có thể chịu lỗi vùng nếu thiết kế đúng; cũng có thêm failure mode | Có thể đạt SLO vừa phải nếu HA/restore/test đáp ứng |
| Tính nhất quán | Đòi hỏi thiết kế giao dịch xuyên dịch vụ | Giao dịch trong một DB thường dễ kiểm soát hơn |
| Chi phí/vận hành | Nền cố định, network và năng lực SRE cao | Dễ kiểm soát ở quy mô nhỏ, vẫn cần cost owner và on-call |
| Khả năng phát triển | Có thể scale/release riêng nếu ranh giới miền tốt | Có thể tách module thành service khi có bằng chứng cần thiết |

**Lựa chọn:** Nếu sau benchmark và kiểm tra SLO, phương án B đạt yêu cầu, nhóm có thể chọn B và ghi **điều kiện nâng cấp** (ví dụ module catalog cần scale độc lập do tải đọc, hay chu kỳ phát hành bị cản trở liên tục). Nếu B không thể đáp ứng ràng buộc bắt buộc, tăng mức độ phức tạp có chủ đích và bố trí năng lực vận hành trước khi triển khai.

### Giao trách nhiệm cho phương án B

- **Product owner:** xác nhận mức gián đoạn và RPO/RTO có thể chấp nhận, ưu tiên incident, chịu ngân sách sản phẩm.
- **Order team:** sở hữu SLO ứng dụng, release/rollback, on-call chính, xử lý lỗi thanh toán và tính đúng của giao dịch.
- **Platform team hoặc đối tác vận hành được chỉ định:** sở hữu mạng, nền tảng compute, IAM nền và hỗ trợ DB/network theo phân định; on-call dự phòng/escalation.
- **Data/security owner:** duyệt quyền dữ liệu, retention, mã hóa và tham gia diễn tập phục hồi, xử lý sự cố bảo mật.

Nếu đội ngũ hiện không thể bố trí người trực 24/7, cần **đàm phán lại mục tiêu hỗ trợ**, thuê hỗ trợ được quy định rõ trong hợp đồng hoặc đầu tư đội trực. Không nên công bố một SLA mà mô hình vận hành chưa thể đảm bảo.

## 11. Tình huống sự cố: không ai nhận lỗi lúc 02:00

Giả sử sau đợt phát hành, một thay đổi cấu hình làm số kết nối database tăng mạnh. API trả lỗi 503, nhưng dashboard dịch vụ riêng lẻ đều “xanh” vì mỗi service chỉ theo dõi CPU. Alert được gửi đến một channel không có lịch trực; on-call platform tưởng đó là lỗi ứng dụng, còn developer cho rằng database managed do nhà cung cấp chịu trách nhiệm.

### Phân tích hậu quả và nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hành động khắc phục |
|---|---|---|
| Khách không đặt hàng được | Connection pool/giới hạn DB, một bản release thay đổi hành vi | Đo end-to-end error rate, database connections, trace và release marker |
| Cảnh báo không ai nhận | Không có on-call/escalation | Giao primary/backup, kiểm tra gửi cảnh báo định kỳ |
| Không biết rollback hay scale | Không có runbook và quyền quyết định | Xác định mức tác động, người chỉ huy incident, bước rollback an toàn |
| Nhóm đổ trách nhiệm cho nhau | Không có owner xuyên suốt checkout | Một nhóm accountable cho SLO sản phẩm, phân nhiệm hỗ trợ rõ |
| Lỗi tương tự tái diễn | Thiếu postmortem/action owner | Ghi timeline, nguyên nhân hệ thống, hạn xử lý và kiểm chứng |

**Biện pháp nhanh:** người điều phối sự cố xác nhận tác động, chỉ định người điều tra ứng dụng và nền tảng, kiểm tra phiên bản mới và kết nối DB, dùng rollback hoặc giới hạn traffic nếu đó là cách an toàn, rồi xác nhận giao dịch đã phục hồi. **Biện pháp lâu dài:** bổ sung SLO người dùng, dashboard theo luồng checkout, load test trên giới hạn kết nối, quy tắc connection pooling, on-call và runbook.

Postmortem nên hỏi **vì sao hệ thống và quy trình cho phép lỗi tồn tại**, không dừng ở “ai đã thay cấu hình”. Một bài học hữu ích phải trở thành thay đổi có chủ sở hữu và ngày hoàn thành.

## 12. Cách sửa hai phản mẫu trong hệ thống đang chạy

Không nên vội viết lại mọi thứ. Một chương trình cải thiện có thể chia thành các bước tăng dần và đo tiến bộ:

### Bước 1: Lập bản đồ thực tế

Liệt kê service, database, queue, network hop, CI/CD, môi trường, tài khoản cloud, luồng dữ liệu và dependency. Với mỗi thành phần, gắn **nhóm sở hữu, mục tiêu nghiệp vụ, SLO liên quan, chi phí và người trực**. Các mục “owner chưa rõ” cần được ưu tiên xác minh.

### Bước 2: Khôi phục khả năng vận hành tối thiểu

Thiết lập cảnh báo tác động người dùng, primary/backup on-call, dashboard, runbook cho các lỗi lớn, backup/restore drill và cách rollback. Phân bổ quyền IAM phù hợp để người trực có thể xử lý, nhưng mọi thao tác nguy hiểm cần quyền phê duyệt và kiểm soát.

### Bước 3: Đánh giá điểm phức tạp có ít giá trị

Với mỗi layer, hỏi:

1. Thành phần này đang giải quyết **SLO, rủi ro hoặc nhu cầu sản phẩm** nào?
2. Có số liệu chứng minh nó hữu ích hơn phương án đơn giản không?
3. Nếu loại bỏ/gộp, ảnh hưởng tới dữ liệu, hợp đồng API và khả năng phục hồi là gì?
4. Ai vận hành, chi phí theo tháng/năm và thời gian xử lý sự cố tăng hay giảm?
5. Điều kiện nào khiến ta cần đưa nó trở lại?

Có thể **gộp service nhỏ**, loại bỏ broker không tạo giá trị, gom pipeline chung, chuyển phần tự quản lý sang managed service, xóa cluster/region không còn cần hoặc thay cơ chế custom bằng tiêu chuẩn sẵn có. Mỗi thay đổi phải có đánh giá **tương thích, migration dữ liệu, rollback và tác động bảo mật**.

### Bước 4: Di chuyển dần, đo trước và sau

Đặt baseline: p95 latency, error rate, lead time, deployment frequency, change failure rate, time to restore, số lần paging, chi phí/run hoặc chi phí/tháng. Đổi từng phần, làm canary/shadow test nếu phù hợp, so sánh SLI và hành vi nghiệp vụ, rồi mới ngừng hệ thống cũ.

### Bước 5: Duy trì cơ chế quyết định

Ghi **ADR (Architecture Decision Record)** cho quyết định lớn; có lịch review ownership, SLO và chi phí. Một thành phần mới chỉ được đưa vào production khi có **owner và operational readiness** tương ứng. Khi tổ chức thay đổi, các vai trò và quyền truy cập phải được bàn giao như một phần của thay đổi kiến trúc.

## 13. Ma trận quyết định: đơn giản hóa có điều kiện

Dùng ma trận để thảo luận, không dùng tổng điểm để bỏ qua điều kiện bắt buộc:

| Yếu tố | Câu hỏi chấm điểm | Bằng chứng |
|---|---|---|
| **Lợi ích nghiệp vụ** | Thành phần mới giải quyết yêu cầu quan trọng đến đâu? | SLO, yêu cầu sản phẩm, thiệt hại khi lỗi |
| **Chi phí triển khai** | Mất bao nhiêu thời gian, kinh phí để thiết kế, kiểm thử và chuyển đổi? | Ước lượng công sức, migration plan |
| **Chi phí vận hành** | Thêm bao nhiêu pager, dashboard, bản vá, license, quota và công debug? | TCO, duty roster, giá thành, toil |
| **Độ tin cậy** | Có loại bỏ failure mode hay tạo thêm failure mode? | Failure-mode analysis, drill |
| **Tính mở rộng** | Có cần scale/release độc lập trong giai đoạn dự báo? | Benchmark, capacity forecast, lead time |
| **Bảo mật & tuân thủ** | Có đáp ứng IAM, retention, residency, audit không? | Security review, data classification |
| **Khả năng sở hữu** | Có nhóm chịu trách nhiệm, quyền và năng lực trực chưa? | RACI, runbook, lịch trực, PRR |

Các yếu tố như **quy định dữ liệu, yêu cầu bảo mật tối thiểu, tính đúng giao dịch** có thể là điều kiện loại trực tiếp. Điểm tổng cao không hợp thức hóa một phương án vi phạm điều kiện đó.

### Mẫu ADR ngắn

~~~markdown
# ADR: Giữ modular monolith cho phiên bản đặt hàng hiện tại

## Bối cảnh
Tải hiện tại X RPS, p95 Y ms; mục tiêu SLO ...;
đội APP ... người, on-call ...

## Quyết định
Giữ ứng dụng theo các module có ranh giới rõ, triển khai qua
managed compute, dùng managed relational database.

## Phương án đã xem xét
1. Tiếp tục monolith hiện tại và tăng kiểm soát vận hành.
2. Tách microservices cho toàn bộ nghiệp vụ.
3. Chỉ tách module có điểm nghẽn đo được.

## Lý do và đánh đổi
Phương án chọn đáp ứng SLO khi thử tải ...;
ít dependency hơn; chấp nhận deploy cùng một ứng dụng.

## Ownership và điều kiện đánh giá lại
SLO owner: ...; on-call: ...; data owner: ...
Xem xét tách catalog khi đạt ... RPS hoặc lead time vượt ...
Hẹn review vào ...; ghi chi phí và kết quả benchmark.
~~~

ADR chỉ hữu ích khi dùng **bằng chứng thực**, được xem xét lại khi giả định thay đổi, và có owner chịu trách nhiệm cho hệ quả vận hành.

## 14. Bài tập áp dụng

Một nhóm 7 người đang xây nền tảng quản lý lịch đặt khám cho chuỗi phòng khám. Hệ thống mới có 5.000 lượt đặt/ngày, dự báo gấp ba trong một năm. Nhóm đề xuất Kubernetes ở ba region, 18 microservices, event sourcing cho mọi thay đổi và một database riêng cho mỗi service. Không có SLO, RTO/RPO, người trực hoặc runbook. Dữ liệu có thông tin nhạy cảm nên yêu cầu bảo vệ và kiểm soát truy cập nghiêm ngặt.

Hãy thực hiện:

1. Tìm **ít nhất năm dấu hiệu cần điều tra** về overengineering hoặc thiếu owner. Phân biệt điều đã biết với giả định chưa có số liệu.
2. Đề xuất **kiến trúc ban đầu** cho mạng, compute, dữ liệu, triển khai và giám sát. Nêu rõ những yêu cầu bảo mật, tính đúng và phục hồi không được phép giản lược.
3. Lập **ma trận RACI** cho SLO, release, DB/backup, bảo mật, trực sự cố và chi phí. Mỗi hoạt động có một A.
4. Đưa ra **ba chỉ số đánh giá** để biết khi nào nên tách service hoặc mở rộng vùng; nêu cách đo và điều kiện kích hoạt.
5. Viết một **runbook mini** cho tình huống người dùng không đặt lịch được vì database hết connection; nêu ai nhận alert, ai điều phối, cách giảm tác động và cách xác minh phục hồi.
6. Phân tích ít nhất **hai đánh đổi Well-Architected**: ví dụ thêm vùng dự phòng tăng tính sẵn sàng nhưng tăng chi phí/độ phức tạp dữ liệu, hoặc managed database giảm toil nhưng vẫn phải bảo vệ schema, IAM và diễn tập restore.

**Gợi ý tự kiểm tra:** Hệ thống có thể bắt đầu bằng modular monolith với managed compute và managed database, phân tách quyền/tài nguyên theo mức rủi ro, backup/HA đáp ứng RTO/RPO **sau khi xác nhận**. Không có cơ sở để khẳng định thiết kế này đạt tải nếu chưa benchmark. Thiết kế ba region có thể trở nên cần thiết nếu BIA, quy định hoặc SLO chứng minh. Với dữ liệu nhạy cảm, yêu cầu mã hóa, kiểm toán, quyền tối thiểu và retention vẫn phải được đáp ứng bất kể chọn monolith hay microservices.

## 15. Checklist phòng tránh phản mẫu

### Trước khi chốt kiến trúc

- [ ] Yêu cầu nghiệp vụ, tải hiện tại/đỉnh, RTO/RPO, SLI/SLO và ràng buộc tuân thủ đã được xác minh.
- [ ] Có phương án ít thành phần nhất đáp ứng ràng buộc; phương án phức tạp hơn có bằng chứng lợi ích.
- [ ] Đã tính **TCO**, gồm hạ tầng, license, công vận hành, on-call, diễn tập và chi phí truyền mạng.
- [ ] Mỗi dịch vụ/lớp mới có lý do, giả định, owner và điều kiện xem xét lại.
- [ ] Các phương án đã qua benchmark, security review và kiểm thử failure/restore tương ứng mức rủi ro.

### Trước khi go-live và trong vận hành

- [ ] Mỗi workload có **service owner, technical owner, primary/backup on-call** và escalation rõ.
- [ ] SLO/SLI được đo end-to-end; alert có người nhận và đã thử gửi.
- [ ] Có dashboard, logs/tracing, runbook, quyền thao tác và cơ chế rollback an toàn.
- [ ] Backup/restore và DR đã được diễn tập với kết quả đo so với RTO/RPO.
- [ ] Ownership về IAM, secret, patching, data retention, bảo mật và chi phí được phân định.
- [ ] CI/CD, release, change review và postmortem có người chịu trách nhiệm cải thiện.
- [ ] Định kỳ so sánh số liệu thực tế với ADR để **giảm độ phức tạp không còn tạo giá trị**.

**Kết luận:** Không nên tối ưu kiến trúc cho một tương lai chưa được chứng minh rồi để đội ngũ hiện tại gánh chi phí. Hãy **thiết kế theo nhu cầu có thể đo, giữ đường mở rộng hợp lý và giao trách nhiệm vận hành rõ ràng**. Một hệ thống đơn giản, bảo mật, phục hồi được và có người trực thường đáng tin cậy hơn một sơ đồ phức tạp không ai đủ khả năng chịu trách nhiệm.
