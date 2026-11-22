# Đánh giá chi phí thực tế, khả năng vận hành và rủi ro còn lại

## 1. Vì sao đánh giá kiến trúc phải vượt qua bản vẽ hệ thống?

Một kiến trúc cloud có thể trông hợp lý trên sơ đồ: các dịch vụ được phân tách, database được quản lý, ứng dụng có autoscaling, dữ liệu có backup và mạng dùng nhiều vùng sẵn sàng. Tuy nhiên, kiến trúc đó chưa chắc phù hợp với doanh nghiệp nếu:

- Hóa đơn thực tế sau ba tháng cao gấp đôi dự toán do lưu lượng mạng, log, backup và môi trường thử nghiệm.
- Hệ thống có nhiều thành phần nhưng đội vận hành chưa có người trực, quyền truy cập, dashboard hoặc quy trình khôi phục.
- Phần mềm đạt mục tiêu độ trễ trong điều kiện bình thường nhưng chưa chứng minh được khả năng phục hồi khi vùng sẵn sàng hoặc dịch vụ phụ thuộc gặp sự cố.
- Các kiểm soát đã triển khai vẫn để lại rủi ro mất dữ liệu, gián đoạn, lộ thông tin hoặc phụ thuộc nhà cung cấp mà chưa có người chịu trách nhiệm.

Trong học phần **CLOUD_ARCHITECTURE**, việc đánh giá kiến trúc cần nối **yêu cầu nghiệp vụ → lựa chọn mạng, compute, dữ liệu và triển khai → chi phí thực tế → khả năng vận hành → rủi ro còn lại**. Đây là cách ứng dụng tư duy **Well-Architected**: không chỉ hỏi hệ thống *có chạy được không*, mà còn hỏi *chạy bền vững, an toàn, mở rộng và phục hồi được với nguồn lực hiện có hay không*.

**Mục tiêu bài học:** Sau khi học, người đọc có thể xây dựng mô hình tổng chi phí sở hữu (TCO) có kiểm chứng; đánh giá mức sẵn sàng vận hành; lập sổ đăng ký rủi ro còn lại (residual risk register); so sánh phương án theo tiêu chí, ràng buộc và bằng chứng; đưa ra quyết định chấp nhận, bổ sung kiểm soát hoặc trì hoãn triển khai.

### 1.1. Ba câu hỏi chính

| Chiều đánh giá | Câu hỏi cần trả lời | Bằng chứng tối thiểu |
| --- | --- | --- |
| **Chi phí thực tế** | Tốn bao nhiêu để xây dựng, duy trì, mở rộng và khôi phục? Giá thành biến đổi thế nào theo tải? | Hóa đơn cloud, dữ liệu sử dụng, giả định giá, bảng TCO, mô hình kịch bản |
| **Khả năng vận hành** | Đội ngũ có thể phát hiện, xử lý, khôi phục và thay đổi hệ thống an toàn không? | SLO, dashboard, cảnh báo, runbook, diễn tập restore/failover, phân công trách nhiệm |
| **Rủi ro còn lại** | Sau khi áp dụng kiểm soát, rủi ro nào vẫn tồn tại; ai có quyền chấp nhận và theo dõi? | Risk register có nguyên nhân, tác động, kiểm soát, mức còn lại, chủ sở hữu và mốc rà soát |

Ba chiều liên quan trực tiếp: một phương án rẻ về hạ tầng có thể đắt về nhân lực vận hành; một phương án dự phòng đắt hơn có thể giảm thiệt hại gián đoạn; một kiểm soát bảo mật tốt có thể tăng chi phí và độ trễ. Vì vậy, không nên tối ưu một chiều mà không đo các chiều còn lại.

## 2. Xác định phạm vi và chuẩn so sánh trước khi tính toán

Không có “kiến trúc tốt nhất” nếu thiếu bối cảnh. Trước buổi architecture review, xác nhận tối thiểu:

1. **Nghiệp vụ:** khối lượng giao dịch, doanh thu hoặc tác động khi ngừng dịch vụ, thời điểm cao điểm, mùa vụ, dữ liệu quan trọng.
2. **Workload:** số request, số giao dịch thành công, kích thước dữ liệu, tần suất đọc/ghi, tỷ lệ cache hit, lưu lượng nội bộ và ra ngoài cloud.
3. **Chất lượng dịch vụ:** SLO về tính sẵn sàng, độ trễ, tỷ lệ lỗi; RTO và RPO cho từng nhóm dữ liệu/chức năng.
4. **Bảo mật và tuân thủ:** quyền truy cập, mã hóa, quản lý bí mật, phân vùng mạng, dữ liệu cư trú, lưu log và thời hạn lưu trữ.
5. **Ràng buộc triển khai:** ngân sách, lịch ra mắt, kỹ năng đội ngũ, trách nhiệm trực sự cố, công nghệ hiện có, khả năng khóa nhà cung cấp.
6. **Thời gian phân tích:** chi phí tháng hiện tại, năm đầu, ba năm; tải cơ sở, tải đỉnh, tình huống mất một vùng và tăng trưởng.

### 2.1. Phân biệt điều kiện bắt buộc và tiêu chí tối ưu

**Điều kiện bắt buộc (hard constraint/gate)** phải được kiểm tra trước khi chấm điểm:

- Dữ liệu cá nhân không được đặt ở khu vực trái với yêu cầu cư trú dữ liệu.
- Tác vụ thanh toán phải có cơ chế ngăn xử lý trùng và đủ nhật ký kiểm toán.
- RPO của dữ liệu giao dịch không vượt ngưỡng nghiệp vụ đã phê duyệt.
- Phương án phải có người trực sự cố và quy trình khôi phục đã kiểm thử.

Nếu một phương án vi phạm điều kiện bắt buộc, điểm chi phí thấp **không** làm nó trở nên chấp nhận được. Các tiêu chí có thể đánh đổi như latency thấp hơn, tính linh hoạt, mức tự động hóa hoặc chi phí nhỏ hơn chỉ nên dùng để chọn **giữa các phương án đã vượt qua gate**.

### 2.2. Bảng baseline và nguồn bằng chứng

| Thuộc tính | Ví dụ giá trị giả định | Nguồn cần xác minh khi làm thật |
| --- | --- | --- |
| API request/tháng | 2.000.000 | API gateway và application metrics |
| Đơn hàng hoàn tất/tháng | 100.000 | Hệ thống nghiệp vụ/ledger |
| Thời gian vận hành | Khoảng 730 giờ/tháng | Thời lượng dịch vụ, vùng, giờ cao điểm |
| Lưu lượng internet và liên vùng | Đo theo GB hoặc TB/tháng | Billing, network flow, CDN và NAT metrics |
| Tăng trưởng dự kiến | Kịch bản 0%, 30%, 100% | Dự báo kinh doanh, dữ liệu lịch sử |
| SLO và RPO/RTO | Do chủ sở hữu nghiệp vụ phê duyệt | SLA, BIA (business impact analysis), DR policy |
| Chi phí nhân lực | Giờ làm việc × suất chi phí đầy đủ | Timesheet, nhân sự, đơn giá phân bổ |

**Lưu ý:** Các con số trong bài là dữ liệu minh họa để học cách tính. Chúng **không** đại diện cho báo giá của một cloud provider hoặc khả năng đạt SLO thực tế của bất kỳ cấu hình nào.

## 3. Đánh giá chi phí thực tế: từ hóa đơn đến tổng chi phí sở hữu

### 3.1. Phân biệt giá niêm yết, chi phí thực trả và TCO

- **Giá niêm yết:** đơn giá theo giờ, GB, request, IOPS hoặc lượng dữ liệu; chưa chắc phản ánh mức giảm giá, cam kết sử dụng, thuế hay cấu hình hiện tại.
- **Chi phí thực trả (actual spend):** số tiền đã sử dụng trong kỳ theo billing và hợp đồng, sau điều chỉnh có thể gồm credit, discount và thuế theo cách báo cáo.
- **Tổng chi phí sở hữu (Total Cost of Ownership – TCO):** chi phí hạ tầng, dịch vụ bên thứ ba và phần nguồn lực cần thiết để xây dựng, vận hành, bảo mật, hỗ trợ, thay đổi và khôi phục hệ thống trong một khoảng thời gian.
- **Unit economics:** chi phí trên một đơn vị giá trị nghiệp vụ, ví dụ USD/đơn hàng thành công, USD/1.000 giao dịch xử lý hoặc chi phí trên mỗi khách hàng hoạt động.

Không được dùng riêng bảng giá compute để kết luận TCO. Một dịch vụ có CPU rẻ có thể phát sinh phí NAT, data transfer, hỗ trợ hoặc chi phí vận hành thủ công rất lớn.

### 3.2. Những khoản phải có trong cost inventory

| Nhóm | Thành phần cần đưa vào | Bẫy dễ bỏ sót |
| --- | --- | --- |
| **Compute** | VM, container, serverless, load balancer, job nền, autoscaling, tài nguyên idle | Instance chạy 24/7, minimum replicas, cold start dẫn đến over-provisioning |
| **Database** | Instance, vCPU/RAM, storage, IOPS, read replica, backup, PITR, replication | I/O tính phí, tăng storage, vùng dự phòng, restore để thử nghiệm |
| **Storage** | Object storage, block/file storage, snapshot, retention, truy xuất, lifecycle | Lưu nhiều phiên bản, phí lấy dữ liệu từ tier lạnh, backup trùng |
| **Networking** | Internet egress, cross-region/cross-zone traffic, NAT gateway, private endpoints, CDN, DNS | Phí theo GB cộng phí theo giờ; gọi dịch vụ qua đường mạng sai thiết kế |
| **Messaging và integration** | Queue, broker, event stream, API calls, notification, ETL | Retry, DLQ, retention và số lần đọc/ghi |
| **Observability** | Log ingestion, retention, metrics cardinality, traces, SIEM, alerting | Log debug bật liên tục, trace quá nhiều, label cardinality cao |
| **Security** | WAF, secrets manager, KMS, vulnerability scanning, audit logs, key rotation | Khoản tính theo request, key, API call và dung lượng audit |
| **DR/HA** | Backup khác vùng, standby, replication, dự phòng năng lực failover, diễn tập | Tài nguyên dự phòng chạy thường trực hoặc tăng tải đột biến khi failover |
| **Môi trường phụ** | Dev, test, staging, preview, CI/CD runner, benchmark | Nhiều môi trường giống production chạy ngoài giờ |
| **Con người và quy trình** | Trực on-call, xử lý incident, patch, nâng cấp, compliance, kiểm toán, đào tạo | SRE/DBA/toil không xuất hiện trong hóa đơn cloud |
| **Chi phí một lần** | Migration, đào tạo, IaC, refactor, data backfill, hợp đồng tích hợp | Bỏ qua công sức chuyển đổi và thời gian hai hệ thống cùng hoạt động |

**Ranh giới đếm chi phí phải rõ:** phí support có thể được phân bổ theo toàn tài khoản; log trong monitoring platform có thể đã bao gồm chi phí lưu trữ riêng. Khi tính TCO phải tránh tính hai lần, ghi phương pháp phân bổ cho chi phí dùng chung.

### 3.3. Công thức và chu kỳ phân tích

~~~text
Cost_month =
    Compute
  + Data_platform
  + Storage_and_backup
  + Network
  + Messaging_and_integration
  + Observability
  + Security_and_support
  + DR_and_other_shared_allocations

Operations_month =
    Sum(Hours_by_role * Fully_loaded_hourly_rate)
  + External_support_services

TCO_month_equivalent =
    Cost_month
  + Operations_month
  + One_time_migration_cost / Amortization_months

Cost_per_successful_order =
    Allocated_TCO_month / Successful_orders_month

TCO_12_months =
    Sum(monthly_actual_or_forecast_TCO over 12 months)
~~~

Giá trị **monthly equivalent** giúp so sánh phương án, nhưng không phải một chuẩn kế toán bắt buộc: cách ghi nhận vốn hóa, khấu hao, amortization và tiền mặt thanh toán phụ thuộc chính sách doanh nghiệp. Phần một lần cần tách rõ để báo cáo năm đầu và các năm sau không bị che khuất.

Đối với hạ tầng tính theo giờ, chi phí sơ bộ bằng **số giờ sử dụng × đơn giá hiệu dụng**. Đối với giao dịch, dùng **số lượng request × đơn giá tương ứng với tier giá**, thêm phí data transfer nếu có. Khi áp dụng discount/cam kết mua trước, phải phân biệt chi phí **amortized** với số tiền thực chi trong kỳ.

### 3.4. Đối chiếu actual với estimate theo kiểu FinOps

Một vòng đánh giá chi phí có thể triển khai hàng tháng:

1. **Phân bổ (allocate):** Gắn thẻ service, môi trường, đội sở hữu, cost center, workload và sản phẩm; định nghĩa quy tắc phân bổ chi phí dùng chung.
2. **Đối soát (reconcile):** So hóa đơn đã phát hành với bảng cost explorer và dữ liệu sử dụng, chốt kỳ và cách xử lý credit/thuế/discount.
3. **Giải thích chênh lệch (variance):** Tách tăng giá do **tăng số lượng sử dụng**, **thay đổi đơn giá/tier**, **thay đổi kiến trúc** và **chi phí một lần**.
4. **Đo đơn vị giá trị:** Chi phí trên giao dịch thành công, trên GB dữ liệu hoặc trên khách hàng hoạt động; kiểm tra cả số lượng giao dịch thất bại.
5. **Đưa ra hành động:** Sửa rightsizing, retention, routing, caching, reservation/commitments hoặc lịch chạy non-prod; gắn owner và mức tiết kiệm dự kiến.
6. **Xác nhận kết quả:** Đo spend và SLO sau tối ưu để tránh tiết kiệm chi phí nhưng làm tăng lỗi hoặc giảm an toàn.

Sai lầm phổ biến là nhìn hóa đơn tăng 20% và kết luận kiến trúc kém, trong khi lượng đơn hàng tăng 50%. Phải đánh giá **tổng chi phí và chi phí/đơn vị** cùng lúc. Ngược lại, chi phí/đơn vị giảm nhưng tổng vượt ngân sách vẫn cần quyết định kinh doanh riêng.

## 4. Ví dụ định lượng: chọn phương án triển khai

Giả sử một hệ thống đơn hàng có hai lựa chọn:

- **Phương án A:** ứng dụng theo modular monolith trên managed containers, chạy qua nhiều availability zone trong một region; database managed, backup và restore; chưa có warm standby vùng khác.
- **Phương án B:** nhiều service tách rời và một region dự phòng **warm standby**; có thêm replication, queue và công cụ điều hành failover.

Cả hai đều phải được kiểm tra theo cùng workload: **2 triệu API request và 100.000 đơn hàng thành công mỗi tháng**. Giả sử tải, retention log, cấu hình bảo mật và đơn giá đã được quy đổi về USD/tháng để so sánh. Bảng dưới đây chỉ là **bộ dữ liệu giả định**, không phải bảng giá thị trường.

### 4.1. Bảng chi phí minh họa (USD/tháng)

| Hạng mục | Phương án A | Phương án B |
| --- | ---: | ---: |
| Compute ứng dụng và job nền | 1.200 | 1.900 |
| Database | 950 | 1.450 |
| Cache, queue, integration | 280 | 650 |
| Storage và backup | 260 | 460 |
| Internet egress, NAT, cross-zone | 720 | 1.260 |
| Log, metrics, tracing | 420 | 800 |
| WAF, secrets, support và phân bổ dịch vụ chung | 310 | 510 |
| Hạ tầng DR liên vùng và replication | 0 | 1.180 |
| **Tổng dịch vụ cloud/tháng** | **4.140** | **8.210** |

Để đánh giá **khả năng vận hành**, giả sử:

- Công sức vận hành thường kỳ của A là **90 giờ/tháng**; của B là **160 giờ/tháng**.
- Suất chi phí nhân lực đầy đủ giả định **45 USD/giờ**.
- Chi phí chuyển đổi/thiết lập một lần: A **1.800 USD**, B **5.400 USD**, phân bổ để so sánh trong **12 tháng**.

| Chỉ tiêu | A | B |
| --- | ---: | ---: |
| Dịch vụ cloud/tháng | 4.140 | 8.210 |
| Vận hành/tháng | 90 × 45 = 4.050 | 160 × 45 = 7.200 |
| Chi phí một lần phân bổ/tháng | 1.800 / 12 = 150 | 5.400 / 12 = 450 |
| **TCO tương đương/tháng** | **8.340** | **15.860** |
| **TCO 12 tháng giả định tải không đổi** | **100.080** | **190.320** |
| **TCO/đơn hàng thành công** | **0,0834 USD** | **0,1586 USD** |

Với bộ giả định này, phương án B có **TCO năm đầu cao hơn 90.240 USD**. Đây **không** phải bằng chứng A luôn tốt hơn: B có thể đáp ứng yêu cầu DR mà A không thể đạt, hoặc giảm tổn thất do gián đoạn. Hơn nữa, công sức vận hành và phí liên vùng thực tế phải được đo/ước lượng bằng dữ liệu riêng của đội; áp bảng giả định vào hệ thống thật sẽ cho kết luận sai.

### 4.2. Đưa chất lượng dịch vụ vào so sánh

Giả định nghiệp vụ cần phục hồi đơn hàng ở region khác trong vòng **60 phút** và mất không quá **5 phút dữ liệu** khi mất hoàn toàn region chính. Đây là yêu cầu ví dụ cần được chủ sở hữu hệ thống phê duyệt. Khi đó:

- **A** có thể rẻ hơn nhưng **không vượt gate DR** nếu chỉ có backup và chưa chứng minh restore dưới 60 phút/RPO dưới 5 phút.
- **B** là **ứng viên** đáp ứng tốt hơn nhờ warm standby, nhưng vẫn cần diễn tập kiểm chứng RTO/RPO, kiểm soát quyền ghi và xác nhận replication lag; có standby không đồng nghĩa tự động đạt yêu cầu.
- Có thể xuất hiện **phương án C** tiết kiệm hơn B, ví dụ modular monolith cùng database có replication liên vùng và failover runbook. Cần định giá và kiểm thử trước khi kết luận B tối ưu.

Nếu bài toán không yêu cầu DR liên vùng hoặc có RTO/RPO rộng hơn, tổng chi phí vận hành của B có thể không xứng với lợi ích. Ngược lại, nếu mỗi giờ dừng checkout gây thiệt hại lớn, mức chênh 90.240 USD/năm có thể được biện minh, nhưng chỉ khi tính được **mức giảm rủi ro thực sự**.

### 4.3. Phân tích độ nhạy

Điểm ước tính đơn thường che giấu rủi ro chi phí. Với mỗi phương án, cần ít nhất ba kịch bản:

| Kịch bản | Thay đổi cần mô phỏng | Tín hiệu rủi ro |
| --- | --- | --- |
| **Base** | Tải và traffic như baseline | Chi phí trung bình, khả năng vận hành hiện tại |
| **High growth** | Tăng request/đơn, storage và log; có hotspot | Compute autoscale, database IOPS, egress và log tăng theo tỷ lệ nào |
| **Failure/DR** | Một region ngừng, traffic chuyển vùng, replay queue, restore | Phí chuyển dữ liệu, hạ tầng dự phòng tăng tải, năng lực đội trực |
| **Provider pricing change** | Giảm discount hoặc hết cam kết giá | Mức lệ thuộc đơn giá và cam kết tiêu thụ |
| **Low usage** | Lượng giao dịch giảm nhưng chi phí nền không đổi | TCO/đơn hàng tăng, commitment bị sử dụng dưới mức |

Trong bảng A/B, nếu chỉ khoản **network** tăng gấp đôi và các giả định khác giữ nguyên, cloud spend A tăng thêm **720 USD/tháng**, B tăng thêm **1.260 USD/tháng**. Đây là một **sensitivity test**, không phải dự đoán rằng lưu lượng sẽ tăng. Phải kiểm tra xem thay đổi xảy ra do egress internet, cross-zone hay replication để chọn tối ưu đúng chỗ.

Nên báo cáo khoảng ước tính và mức tin cậy (ví dụ P50/P90 từ mô phỏng khi có dữ liệu lịch sử), kèm **giả định nào có ảnh hưởng mạnh nhất**. Không gán nhãn P90 nếu mới có ba con số đoán thủ công.

## 5. Khả năng vận hành: đánh giá hệ thống và con người

Một kiến trúc vận hành tốt cần **hệ thống quan sát được**, **quy trình được thực hành** và **người chịu trách nhiệm rõ ràng**. Một sơ đồ chứa “managed” service không có nghĩa nhà cung cấp sẽ chịu trách nhiệm triển khai, cấp quyền, khôi phục dữ liệu hay phản ứng với sự cố nghiệp vụ cho doanh nghiệp.

### 5.1. Các năng lực phải chứng minh

| Năng lực | Cần có trong thiết kế | Bằng chứng đánh giá |
| --- | --- | --- |
| Ownership/on-call | Chủ hệ thống, lịch trực, escalation, kênh liên hệ | RACI, lịch trực, phân công từng service |
| Observability | Metrics, logs, traces, correlation ID, health check | Dashboard và truy vết một request từ đầu đến cuối |
| SLO/error budget | SLO đo từ góc nhìn người dùng, phân biệt lỗi phụ thuộc | Báo cáo SLI, alert policy và thống kê lỗi |
| Incident response | Phân loại mức độ, người điều phối, cơ chế liên lạc | Runbook và biên bản diễn tập |
| Backup/restore | Backup, retention, mã hóa, kiểm tra restore, quyền truy cập | Bản ghi restore thật và thời gian phục hồi |
| DR/failover | Phạm vi sự cố, điều kiện promote, fencing, failback | Kết quả diễn tập RPO/RTO, kiểm thử dữ liệu |
| Deployment/rollback | CI/CD, IaC, canary/blue-green, rollback, feature flag | Change log và kết quả triển khai thử |
| Security operations | Quản lý secrets, patch, IAM, audit, threat response | Báo cáo scan, review quyền, rotation, audit |
| Capacity/performance | Test peak load, saturation, autoscaling, quota | Load test, CPU/memory/IOPS, latency p95/p99 |
| Data operations | Migration có rollback, schema versioning, đối soát | Kế hoạch migration, kiểm thử backfill và restore |
| Cost operations | Budget, anomaly alert, tag, unit cost, owner | Báo cáo spend và quyết định tối ưu đã thực thi |
| Knowledge transfer | Tài liệu hệ thống, người thay thế, quy trình bàn giao | Runbook có người thứ hai thực hiện thành công |

### 5.2. SLO và tín hiệu phải gắn với trải nghiệm người dùng

Ví dụ SLI của checkout:

~~~text
Availability SLI =
    Số yêu cầu checkout hợp lệ được hệ thống xử lý theo tiêu chí thành công
    /
    Tổng số yêu cầu checkout hợp lệ

Latency SLI =
    Tỷ lệ yêu cầu hợp lệ có thời gian xử lý <= ngưỡng đã cam kết
~~~

Phải định nghĩa chính xác trường hợp nào được tính là **hợp lệ** và **thành công**: yêu cầu hết hàng bị từ chối đúng nghiệp vụ có thể không phải lỗi dịch vụ, trong khi API trả 202 rồi saga mắc kẹt hàng giờ có thể vẫn là thất bại về **thời gian hoàn tất đơn**.

Một SLO minh họa **99,9% thời gian thành công trong cửa sổ 30 ngày** tương đương **0,1% error budget**, tức **43,2 phút trong 30 ngày** nếu quy đổi theo mô hình thời gian liên tục. Đây không phải cam kết uptime của kiến trúc; cách đo thực tế phải dựa trên định nghĩa SLI, traffic và cửa sổ đánh giá.

Đội vận hành cần alert trên **triệu chứng ảnh hưởng khách hàng** (tỷ lệ lỗi, latency, backlog, đơn hàng không hoàn tất) cùng tín hiệu nguyên nhân (CPU, IOPS, replication lag, quota). Cảnh báo quá nhiều theo ngưỡng tài nguyên không có hành động cụ thể sẽ làm tăng alert fatigue.

### 5.3. Định lượng mức sẵn sàng vận hành

Có thể dùng thang điểm thực dụng **0–2** cho từng năng lực:

- **0 – Chưa có:** không có owner hoặc chưa có cơ chế/bằng chứng.
- **1 – Có thiết kế:** đã mô tả và cấu hình nhưng chưa được thử dưới điều kiện gần production.
- **2 – Đã chứng minh:** có người chịu trách nhiệm, triển khai và minh chứng test/diễn tập gần đây.

Ví dụ đánh giá giả định:

| Năng lực | A | B | Nhận xét |
| --- | ---: | ---: | --- |
| Dashboard và SLO cho checkout | 2 | 2 | Cả hai đã có dashboard và alert |
| Restore database | 2 | 1 | B chưa thử restore dữ liệu phụ thuộc liên vùng |
| Failover/failback | 1 | 0 | B có thiết kế phức tạp hơn nhưng chưa diễn tập |
| Rollback triển khai | 2 | 1 | B thiếu quy trình rollback đồng bộ nhiều service |
| On-call/escalation | 2 | 1 | B chưa bàn giao đầy đủ runbook |
| **Tổng minh họa (trên 10)** | **9** | **5** | Điểm đo **readiness**, không phải chất lượng cuối cùng |

Điểm số chỉ phục vụ ưu tiên việc cần làm. Nếu **failover** là gate bắt buộc, phương án B có điểm **0** ở mục này vẫn phải được xem là **chưa sẵn sàng triển khai**, dù tổng điểm đủ cao. Đánh giá phải ghi **minh chứng** và **ngày kiểm tra**, không chỉ ghi con số.

### 5.4. Đánh giá công sức vận hành thực tế

Tách ba loại effort:

1. **Toil lặp lại:** sửa lỗi thủ công, xử lý alert không hữu ích, restart service, khôi phục job, làm công việc có thể tự động hóa.
2. **Bảo trì có kế hoạch:** patch, nâng cấp runtime/database, quản lý chứng chỉ, schema migration, diễn tập DR, cải thiện bảo mật.
3. **Ứng phó sự cố và cải tiến:** incident, postmortem, reliability engineering, đào tạo, tối ưu hiệu suất.

Đo **giờ công theo loại việc và service**, tần suất sự cố, thời gian phát hiện và thời gian phục hồi; sau đó quy đổi ra chi phí. Không nên “tính 0 USD” cho on-call chỉ vì nhân viên đang nhận lương cố định. Tuy nhiên, tránh đếm cùng một giờ người vừa ở bảng hoạt động hằng tháng vừa trong hạng mục dự án một lần.

### 5.5. Runbook phải có các hành động rõ ràng

Một runbook phục hồi database tối thiểu nên trả lời:

~~~text
Trigger:
  Cần khôi phục do mất dữ liệu / lỗi logic / region unavailable.

Detect & scope:
  Xác định dữ liệu và ứng dụng bị ảnh hưởng.
  Ghi lại thời điểm, commit/replication position và các request chưa rõ kết quả.

Decide:
  Incident commander xác nhận loại sự cố và phạm vi restore.
  Data owner xác nhận RPO được chấp nhận và các nghiệp vụ cần dừng ghi.

Execute:
  Cô lập nguồn lỗi.
  Khôi phục backup/snapshot tại môi trường an toàn.
  Kiểm tra tính toàn vẹn và khóa truy cập.
  Thực hiện switch hoặc promote theo cơ chế được phê duyệt.

Verify:
  Đọc/ghi thử có kiểm soát, kiểm tra số liệu nghiệp vụ và latency.
  Đối soát giao dịch, event, thanh toán hoặc job chưa xử lý.

Communicate & close:
  Ghi RTO/RPO thực tế, thời điểm phục hồi, ảnh hưởng tới khách hàng.
  Lập action item có owner và hạn hoàn thành.
~~~

Runbook phải được **diễn tập** với người ngoài nhóm thiết kế để kiểm chứng rằng các bước thực thi được; một tài liệu đẹp nhưng yêu cầu quyền truy cập không ai có vẫn là rủi ro vận hành.

## 6. Rủi ro còn lại: từ danh sách mối lo đến quyết định chấp nhận

### 6.1. Phân biệt rủi ro ban đầu, kiểm soát và rủi ro còn lại

**Inherent risk (rủi ro vốn có)** là mức rủi ro trước khi tính đến các kiểm soát hiện hữu. **Control** là biện pháp phòng ngừa, phát hiện hoặc phục hồi. **Residual risk (rủi ro còn lại)** là phần phơi nhiễm vẫn tồn tại **sau** khi đánh giá các kiểm soát đã triển khai và hiệu quả thực tế của chúng.

Ví dụ:

~~~mermaid
flowchart LR
    T[Sự kiện đe dọa: xóa nhầm dữ liệu] --> I[Tác động nếu không kiểm soát]
    I --> C[Kiểm soát: IAM, backup, PITR, restore drill]
    C --> E{Kiểm soát hoạt động thật?}
    E -->|Có bằng chứng| R[Đánh giá rủi ro còn lại]
    E -->|Chưa có bằng chứng| U[Rủi ro chưa được chứng minh đã giảm]
    R --> D{Mức còn lại trong khẩu vị rủi ro?}
    D -->|Có| A[Chủ sở hữu phê duyệt chấp nhận]
    D -->|Không| M[Giảm thiểu / tránh / chuyển giao / thay thiết kế]
~~~

Chỉ ghi “đã có backup” không đủ để giảm rủi ro nếu chưa từng restore; chỉ ghi “có WAF” không đủ để kết luận không còn rủi ro bảo mật.

### 6.2. Cấu trúc sổ đăng ký rủi ro (risk register)

Mỗi dòng nên có:

- **ID và phát biểu rủi ro** theo cấu trúc: *Do nguyên nhân X, sự kiện Y có thể xảy ra, gây tác động Z lên mục tiêu nghiệp vụ*.
- **Tài sản/phạm vi** bị ảnh hưởng: dữ liệu, service, khách hàng, bên thứ ba, region, loại giao dịch.
- **Likelihood và impact** trước/sau kiểm soát, ghi phương pháp và mức tin cậy.
- **Kiểm soát hiện tại**, bằng chứng test/giám sát, điểm yếu còn lại.
- **Hướng xử lý:** giảm thiểu, tránh, chuyển giao hoặc chấp nhận; chi phí và tác động lên kiến trúc.
- **Owner quyết định, owner hành động, deadline**, trạng thái và thời điểm rà soát.
- **Trigger** làm đánh giá không còn hợp lệ: workload tăng, thay đổi luật/hợp đồng, incident, hết hỗ trợ, thay đổi provider.

Ví dụ giả định:

| ID | Phát biểu rủi ro và tác động | Kiểm soát đã có | Rủi ro còn lại | Owner và hành động |
| --- | --- | --- | --- | --- |
| R-01 | Mất region chính gây ngừng checkout quá RTO | Backup liên vùng, standby và DNS failover | **Cao** nếu chưa thử promotion và đối soát giao dịch | SRE lead: diễn tập failover/failback, đo RTO/RPO |
| R-02 | Lỗi schema migration gây mất/corrupt dữ liệu | Migration pipeline, versioned schema, PITR | **Trung bình** do rollback dữ liệu chưa được kiểm chứng | DBA: rehearsal trên bản sao dữ liệu sát thực |
| R-03 | Traffic đột biến vượt quota downstream làm backlog kéo dài | Autoscaling, queue, retry/backoff | **Trung bình** do chưa thử quá tải nhà cung cấp | Platform owner: load test và quota plan |
| R-04 | Secrets bị lộ dẫn đến truy cập trái phép | Secrets manager, least-privilege IAM, audit | **Trung bình/cao** nếu chưa có rotation và response drill | Security owner: rotation, detection, rehearsal |
| R-05 | Cloud egress và log vượt ngân sách | Budget alerts, retention, tagging | **Trung bình** vì dự báo chưa đủ tải failover | FinOps owner: cảnh báo theo service, test cost spike |

Các mức trên **chỉ minh họa**; trong đánh giá thật không được gán “cao/trung bình” khi chưa biết số liệu, xác suất, mức thiệt hại và hiệu lực kiểm soát.

### 6.3. Cách chấm likelihood × impact và giới hạn

Một ma trận định tính có thể dùng thang 1–5:

| Điểm | Khả năng (likelihood) | Mức tác động (impact) |
| --- | --- | --- |
| 1 | Rất hiếm theo định nghĩa nội bộ | Ảnh hưởng nhỏ, không vượt SLO nghiêm trọng |
| 2 | Thấp | Giảm chất lượng trong phạm vi dễ khôi phục |
| 3 | Có thể xảy ra | Ngừng một chức năng hoặc cần can thiệp đáng kể |
| 4 | Cao | Gián đoạn diện rộng hoặc tổn thất nghiệp vụ lớn |
| 5 | Rất cao | Ảnh hưởng nghiêm trọng đến người dùng, tài chính, tuân thủ |

~~~text
Risk_score = Likelihood_score × Impact_score

Example:
  Likelihood = 3
  Impact = 4
  Residual_score = 12 / 25
~~~

**Đây là thang thứ bậc do tổ chức tự định nghĩa, không phải xác suất toán học.** Điểm 12 không có nghĩa xác suất 12% và không nên cộng máy móc các score để suy ra tổn thất kỳ vọng. Ranh giới thấp/vừa/cao và quyền chấp nhận phải được thống nhất trước cuộc review.

Nếu có dữ liệu ước tính hợp lệ, có thể tính **annualized expected loss**:

~~~text
Expected_annual_loss ≈ P(event in year) × Financial_impact_if_event

Ví dụ giả định:
  Xác suất sự cố/năm = 0,08
  Thiệt hại nếu xảy ra = 80.000 USD
  Tổn thất kỳ vọng ≈ 6.400 USD/năm
~~~

Con số kỳ vọng không đại diện cho thiệt hại cực đoan, tổn thất phi tài chính hoặc rủi ro tương quan (ví dụ lỗi cấu hình làm hỏng cả primary và replica). Không dùng nó để “mua rẻ” việc vi phạm luật hay điều kiện bắt buộc. Một kiểm soát chi phí 4.000 USD/năm chỉ nên được so với **mức giảm rủi ro do kiểm soát tạo ra**, không so trực tiếp với toàn bộ rủi ro chưa kiểm soát.

### 6.4. Bốn cách xử lý rủi ro

| Cách xử lý | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Mitigate – giảm thiểu** | Thêm PITR, WAF, rate limiting, đối soát, failover drill | Kiểm tra hiệu quả và chi phí, cập nhật risk còn lại |
| **Avoid – tránh** | Không cho active-active ghi cùng đơn hàng nếu chưa giải quyết split-brain | Thay thiết kế, thu hẹp tính năng hoặc dừng tác vụ |
| **Transfer/share – chuyển giao/chia sẻ** | Bảo hiểm, hợp đồng hỗ trợ, dịch vụ managed | Trách nhiệm pháp lý và tác động với khách hàng thường không mất hoàn toàn |
| **Accept – chấp nhận** | Chấp nhận trễ cache vài phút đối với dữ liệu không quan trọng | Cần đúng người phê duyệt, thời hạn và trigger tái đánh giá |

Không nên để status “accepted” vĩnh viễn. Rủi ro phải được xem lại khi thay đổi sản phẩm, khối lượng dữ liệu, quyền truy cập, topology hoặc sau một incident quan trọng.

## 7. Tổng hợp ba chiều thành quyết định kiến trúc

### 7.1. Quy trình review đề xuất

~~~mermaid
flowchart TD
    REQ[Xác nhận yêu cầu nghiệp vụ và ràng buộc] --> OPT[Định nghĩa các phương án và boundary]
    OPT --> G{Qua hard gates?}
    G -->|Không| RED[Loại hoặc thiết kế lại phương án]
    G -->|Có| COST[Đánh giá actual/TCO và kịch bản tải]
    COST --> OPS[Đánh giá operational readiness bằng bằng chứng]
    OPS --> RISK[Đánh giá residual risk và owner]
    RISK --> DEC{Rủi ro còn lại có thể chấp nhận?}
    DEC -->|Không| ACT[Thêm kiểm soát / đổi thiết kế / chờ triển khai]
    ACT --> COST
    DEC -->|Có| ADR[Ghi decision record, điều kiện và thời hạn]
    ADR --> VERIFY[Đo sau triển khai, review lại khi có trigger]
~~~

Đầu ra không nên chỉ là một điểm tổng. Phải biết phương án nào **bị loại vì vi phạm bắt buộc**, phương án nào **cần thêm bằng chứng**, phương án nào **được chọn có điều kiện** và ai chịu trách nhiệm.

### 7.2. Chấm điểm có trọng số khi đã qua gate

Ví dụ tổ chức ưu tiên độ tin cậy và khả năng vận hành:

| Tiêu chí (điểm 1–5) | Trọng số | A | B |
| --- | ---: | ---: | ---: |
| Reliability sau kiểm chứng | 25% | 3 | 5 |
| Operational readiness | 20% | 5 | 2 |
| Rủi ro được kiểm soát | 30% | 4 | 4 |
| TCO/đơn hàng | 15% | 5 | 2 |
| Latency/khả năng đáp ứng tải | 10% | 3 | 4 |
| **Tổng điểm có trọng số** | **100%** | **4,00** | **3,55** |

Cách tính:

~~~text
Weighted_score(option) =
    Sum(weight_i × score_i), với Sum(weight_i) = 1

A = 0,25×3 + 0,20×5 + 0,30×4 + 0,15×5 + 0,10×3 = 4,00
B = 0,25×5 + 0,20×2 + 0,30×4 + 0,15×2 + 0,10×4 = 3,55
~~~

**Giới hạn quan trọng:** Các số 1–5 trong bảng là **giả định minh họa**, không phải kết quả đánh giá thật và không thể thay cho gate. Nếu RTO/RPO liên vùng là điều kiện bắt buộc, A không đủ điều kiện và không được chọn chỉ vì đạt 4,00. Nếu B chưa có test failover hoặc bị chấm readiness 2/5 do thiếu runbook, quyết định có thể là **chưa triển khai B cho đến khi hoàn thành kiểm soát**, hoặc khảo sát phương án thứ ba.

Điểm cho **rủi ro được kiểm soát** phải tính theo chiều “điểm cao = tốt” trong bảng này; nếu nơi khác dùng “risk score cao = nguy hiểm”, không được trộn hai quy ước. Cần ghi định nghĩa và nguồn chứng cứ cho mỗi điểm.

### 7.3. Architecture Decision Record (ADR) mẫu

Một biên bản review đủ dùng nên có:

~~~markdown
# ADR: Lựa chọn kiến trúc cho hệ thống đơn hàng

## Bối cảnh
- Workload: ...
- Yêu cầu SLO: ...
- RPO / RTO: ...
- Ràng buộc dữ liệu và bảo mật: ...

## Các phương án
- A: ... Ưu / nhược ...
- B: ... Ưu / nhược ...
- C (nếu có): ...

## Bằng chứng
- TCO năm đầu và 3 năm: ... (nguồn billing/forecast, ngày chốt)
- TCO trên đơn hàng: ...
- Kết quả load test, restore/failover drill: ...
- Operational readiness và các khoảng trống: ...
- Residual risk (ID, mức còn lại, owner): ...

## Quyết định
- Chọn: ...
- Cơ sở: ... (điều kiện bắt buộc và đánh đổi)
- Điều kiện trước production: ...
- Rủi ro được chấp nhận bởi: ... / ngày ...

## Theo dõi
- Người chịu trách nhiệm: ...
- Metric/SLO/cost budget: ...
- Ngày review lại: ...
- Trigger review sớm: ... (tăng tải, incident, thay đổi giá/kiến trúc)
~~~

ADR không chỉ ghi “chọn B vì hiện đại”. Cần ghi **vì sao phương án được chọn phù hợp với yêu cầu đã kiểm tra**, phần bất định còn lại và tình huống khiến quyết định phải thay đổi.

## 8. Đánh giá kiến trúc theo vòng đời, không chỉ trước go-live

### 8.1. Trước khi triển khai

- Chốt baseline và yêu cầu phi chức năng với chủ sở hữu nghiệp vụ, security, SRE và FinOps.
- Ước lượng TCO bằng dữ liệu minh họa hoặc pilot; liệt kê giả định và phạm vi giá chưa xác thực.
- Review điểm lỗi đơn, quyền truy cập, phục hồi dữ liệu, giới hạn dịch vụ và phụ thuộc bên ngoài.
- Kiểm tra mọi hard gate; lập risk register với owner, cách giảm thiểu và thời hạn.
- Viết runbook, cấu hình observability, backup, cảnh báo ngân sách và kiểm tra quyền khẩn cấp.

### 8.2. Trong pilot hoặc pre-production

- Chạy benchmark với tải đại diện cả **average, peak và hotspot**; đo autoscaling, throughput, p95/p99.
- Thử mất kết nối database, quota downstream, queue backlog và duplicate request.
- Thực hiện **restore từ backup thật**, kiểm tra tính toàn vẹn dữ liệu và thời gian phục hồi.
- Nếu có DR liên vùng, diễn tập failover/failback, đối soát replication và xác định RPO/RTO đo được.
- Quan sát lượng log, storage, traffic và chi phí trên một đơn vị; cập nhật forecast từ số liệu thật.
- Chạy security review, threat modeling, secret rotation và kiểm tra IAM tối thiểu.

### 8.3. Sau khi đi vào hoạt động

| Nhịp đánh giá | Nội dung | Kết quả mong đợi |
| --- | --- | --- |
| Hằng ngày / theo sự kiện | SLO, incident, budget anomaly, backlog, lỗi bảo mật | Xử lý tín hiệu ảnh hưởng người dùng |
| Hằng tuần | Top cost drivers, hot service, alert noise, toil | Hành động tối ưu có owner |
| Hằng tháng | Actual vs forecast, TCO/unit, residual risk, review alert và quota | Cập nhật quyết định ngân sách và rủi ro |
| Hằng quý hoặc theo mức rủi ro | Restore/failover drill, quyền truy cập, capacity, vendor dependencies | Bằng chứng DR/readiness mới và kế hoạch cải tiến |
| Sau incident/thay đổi lớn | Re-review kiến trúc, ADR, threat model, forecast | Thay đổi kiểm soát, chủ sở hữu, scope hoặc quyết định |

Tần suất là gợi ý; hệ thống tài chính hoặc dữ liệu nhạy cảm có thể cần kiểm tra thường xuyên hơn. Những hoạt động chưa thể chạy tự động cần có lịch và kết quả ghi nhận để không bị bỏ quên.

## 9. Những phản mẫu thường gặp khi đánh giá

| Phản mẫu | Vì sao dẫn đến kết luận sai | Cách khắc phục |
| --- | --- | --- |
| So giá bằng một VM hoặc một database | Bỏ sót network, backup, log, DR, người vận hành | Cost inventory và TCO theo workload |
| Chọn cấu hình rẻ nhất ở tải trung bình | Không biết peak/hotspot/region failure | Kịch bản và load test có số liệu |
| Dùng hóa đơn hiện tại như dự báo tương lai | Không tính tăng trưởng, discount hết hạn, retention | Forecast theo biến điều khiển và sensitivity |
| Khẳng định HA vì có nhiều AZ/region | Chưa kiểm tra phụ thuộc chung, failover và dữ liệu | Fault injection, restore, đối soát RPO/RTO |
| Dùng managed service để thay thế trách nhiệm on-call | Khách hàng vẫn chịu lỗi cấu hình, quyền, vận hành ứng dụng | RACI và kiểm chứng runbook |
| Đánh giá rủi ro theo cảm tính, không owner | Không ai xử lý hoặc chấp nhận có thẩm quyền | Risk register có bằng chứng, hạn và escalation |
| Cộng risk score định tính thành “tổn thất tiền” | Trộn thang thứ bậc với xác suất/tác động tài chính | Giữ định tính hoặc mô hình định lượng có giả định rõ |
| Chọn theo tổng điểm dù vi phạm hard gate | Điểm tốt ở chi phí che rủi ro bắt buộc | Kiểm tra gate trước weighted scoring |
| Chỉ đo uptime API | Không thấy saga lỗi, dữ liệu mất, người dùng không hoàn tất mục tiêu | SLI/SLO theo kết quả nghiệp vụ |
| Tài liệu review không được cập nhật | Quyết định dựa trên tải, luật hoặc giá cũ | Trigger re-review, owner, ngày hết hạn chứng cứ |

## 10. Bài thực hành: lập review cho hệ thống đơn hàng

### 10.1. Đề bài

Một nhóm đề xuất triển khai hệ thống checkout lên cloud với hai phương án A/B ở mục 4. Họ có ngân sách **160.000 USD cho năm đầu**, mục tiêu phục hồi **không quá 60 phút**, RPO **không quá 5 phút** khi mất toàn bộ region chính, và yêu cầu phải có người trực xử lý giao dịch sai lệch.

Số liệu trong bài là **giả định**. Hãy thực hiện:

1. Kiểm tra tổng chi phí 12 tháng, nêu phương án nào vượt ngân sách và vượt bao nhiêu nếu không có tối ưu thêm.
2. Chỉ ra lý do không được chọn A chỉ dựa trên mức TCO/đơn hàng nếu A chưa chứng minh RTO/RPO.
3. Liệt kê các bằng chứng B phải có trước khi được coi là sẵn sàng: failover, data integrity, backup, quyền ghi, con người và monitoring.
4. Chọn ba rủi ro còn lại có tác động lớn nhất theo đặc thù checkout, ghi owner và hành động cụ thể.
5. Đề xuất **một phương án C** để đánh giá bổ sung; chỉ rõ điều kiện nào cho thấy C có thể là lựa chọn hợp lý.
6. Viết một ADR ngắn ghi rõ phương án tạm chọn hoặc quyết định chờ kiểm chứng, các gate, chi phí, risk acceptance và ngày rà soát.

### 10.2. Hướng dẫn giải tham khảo

- Theo phép tính ở mục 4, **A = 100.080 USD/năm**; **B = 190.320 USD/năm**. Với ngân sách 160.000 USD, **B vượt 30.320 USD**, còn **A dưới ngân sách 59.920 USD**.
- **A chưa thể được phê duyệt** nếu chưa có bằng chứng đáp ứng gate RTO/RPO; nếu chỉ backup không đủ, phải bổ sung cơ chế DR hoặc thay cấu hình.
- **B cũng chưa đủ điều kiện triển khai** nếu failover/failback chưa được test và khả năng vận hành mới ở mức thiết kế. Cần đo RPO/RTO thật, kiểm tra không có hai write owner, đối soát các đơn và khoản thanh toán chưa rõ kết quả.
- Có thể đánh giá **C: modular monolith nhiều AZ, database có replica/standby liên vùng và cơ chế promote có fencing**. Cần đo TCO, khả năng phục hồi và burden vận hành thay vì giả định nó luôn rẻ hoặc luôn đúng.
- Quyết định phù hợp tại thời điểm chưa có kiểm thử có thể là **“chưa duyệt production; phê duyệt pilot/DR drill và cập nhật cost model”**, với owner, hạn và tiêu chí chấp nhận cụ thể. Đây là một kết quả đánh giá hợp lệ, không phải thất bại của review.

### 10.3. Checklist tự đánh giá đầu ra

- [ ] Có mô tả workload, traffic, dữ liệu và SLO/RTO/RPO cụ thể.
- [ ] Có tính đủ cloud service, data transfer, observability, backup, DR, support và công sức vận hành.
- [ ] Chi phí actual/forecast có nguồn, phạm vi, thời kỳ, giả định giá, phương pháp phân bổ.
- [ ] Có cost/unit nghiệp vụ và ít nhất một sensitivity scenario.
- [ ] Có bằng chứng ownership, monitoring, runbook, restore/failover và rollback.
- [ ] Có risk register sau kiểm soát với owner, deadline, trigger review và người chấp nhận rủi ro.
- [ ] Hard gates được xét trước, không bị bù bằng điểm chi phí.
- [ ] Quyết định ADR phản ánh trade-off, giới hạn bằng chứng và điều kiện trước production.
- [ ] Có lịch đo lại sau triển khai, nhất là sau incident, thay đổi tải, thay đổi giá hoặc topology.

## 11. Kết luận

Đánh giá kiến trúc cloud đáng tin cậy phải dựa trên **chi phí đủ phạm vi và kiểm chứng được**, **khả năng vận hành đã được thực hành**, cùng **rủi ro còn lại được ghi nhận và có người chịu trách nhiệm**. Một mô hình triển khai có thể rẻ trên hóa đơn nhưng tốn nhân lực; một lựa chọn nhiều vùng dự phòng có thể giảm rủi ro gián đoạn nhưng tăng chi phí, độ trễ và độ phức tạp.

Quy trình thực dụng là **chốt yêu cầu bắt buộc → đo workload và TCO → diễn tập vận hành → đánh giá hiệu lực kiểm soát và residual risk → so sánh những phương án đạt gate → ghi quyết định có điều kiện → theo dõi và tái đánh giá**. Nhờ vậy, kiến trúc được lựa chọn theo mục tiêu nghiệp vụ và năng lực thực tế thay vì theo số lượng dịch vụ cloud hay mức độ hấp dẫn của sơ đồ.
