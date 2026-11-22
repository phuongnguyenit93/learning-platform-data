# Quản lý giả định, rủi ro và nợ kiến trúc

> **Chương:** Sơ đồ và quyết định  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ tới lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào cách ghi nhận, kiểm chứng và theo dõi những điều **chưa biết**, những điều **có thể gây tổn thất** và những **đánh đổi kỹ thuật còn tồn đọng** trong suốt vòng đời kiến trúc, theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **giả định (assumption)**, **rủi ro (risk)**, **vấn đề đang xảy ra (issue)**, **ràng buộc (constraint)** và **nợ kiến trúc (architecture debt)**.
2. Ghi một giả định có căn cứ, mức tin cậy, người sở hữu, kế hoạch kiểm chứng và điều kiện xem xét lại.
3. Viết rủi ro theo cấu trúc **nguyên nhân → sự kiện không chắc chắn → hậu quả**, đánh giá tác động, xác định biện pháp và người chấp nhận rủi ro còn lại.
4. Nhận diện nợ kiến trúc phát sinh từ các quyết định có chủ đích hoặc sự tiến hóa của hệ thống; đánh giá chi phí trì hoãn và phương án xử lý.
5. Liên kết **sơ đồ kiến trúc, yêu cầu chất lượng, ADR, giả định, rủi ro, nợ, thử nghiệm và runbook** để quyết định có thể truy vết.
6. Xây dựng nhịp rà soát và chỉ số theo dõi độ tin cậy, bảo mật, hiệu năng, mở rộng, chi phí và vận hành cho kiến trúc cloud.

## 1. Vì sao ba đối tượng này cần được quản lý cùng nhau?

Thiết kế cloud luôn bắt đầu khi thông tin chưa đầy đủ: chưa biết tải đỉnh, tỷ lệ lỗi của bên thứ ba, tốc độ tăng dữ liệu, mức chi phí sau sáu tháng hoặc yêu cầu vận hành cuối cùng của khách hàng. Nhóm phải đưa ra quyết định trước khi có thể kiểm chứng mọi thứ.

Nếu không ghi nhận các điểm chưa chắc chắn, sơ đồ kiến trúc dần trông như “sự thật đã được chứng minh”. Khi yêu cầu thay đổi, người mới khó biết tại sao một database được đặt ở một vùng cụ thể, vì sao chưa có vùng dự phòng hoặc vì sao nhiều dịch vụ đang chia sẻ một queue.

Ba khái niệm có quan hệ với nhau:

- **Giả định:** điều đang tạm coi là đúng để thiết kế có thể tiếp tục. Nếu sai, kiến trúc hoặc kế hoạch phải thay đổi.
- **Rủi ro:** sự kiện hoặc điều kiện **chưa chắc xảy ra** có thể ảnh hưởng tiêu cực đến mục tiêu nghiệp vụ hay yêu cầu chất lượng. Một giả định chưa kiểm chứng có thể làm tăng rủi ro.
- **Nợ kiến trúc:** giới hạn/đánh đổi ở cấu trúc hệ thống khiến việc thay đổi, vận hành hoặc đáp ứng chất lượng trong tương lai tốn kém hơn mức cần thiết. Nợ có thể chấp nhận tạm thời và cần được quản lý, không nhất thiết là lỗi thiết kế ngay lúc ra quyết định.

Ví dụ:

> **Giả định A-01:** Lưu lượng đạt tối đa 300 yêu cầu/giây trong ba tháng đầu.  
> **Rủi ro R-01:** Nếu tải thực tế cao hơn dự báo và database chung đạt giới hạn kết nối, checkout có thể vượt SLO độ trễ hoặc thất bại.  
> **Nợ D-01:** Nhóm tạm dùng một database cho Booking và Reporting để ra mắt nhanh; các truy vấn báo cáo nặng làm việc tách và mở rộng về sau khó hơn.

Giả định A-01 có thể được xác minh bằng dữ liệu phân tích thị trường và kiểm thử tải; rủi ro R-01 có thể giảm bằng giới hạn tài nguyên, giám sát và diễn tập tải; nợ D-01 có thể được xử lý bằng read replica, chuyển báo cáo sang một read model hoặc tách data pipeline khi có số liệu chứng minh.

## 2. Phân biệt giả định, rủi ro, vấn đề, ràng buộc và quyết định

| Đối tượng | Câu hỏi chính | Ví dụ trong thiết kế cloud | Hành động quản lý |
| --- | --- | --- | --- |
| **Giả định** | Ta đang coi điều gì là đúng khi chưa chắc? | Tải đỉnh dưới 300 req/s | Kiểm chứng, đo, chốt hạn và điều kiện vô hiệu |
| **Rủi ro** | Điều gì có thể xảy ra và gây thiệt hại? | Mất kết nối DB làm gián đoạn checkout | Phân tích tác động, xử lý, theo dõi rủi ro còn lại |
| **Issue** | Điều gì đã xảy ra hoặc đang sai? | DB đang hết connection trong production | Khắc phục sự cố theo quy trình và theo dõi kết quả |
| **Ràng buộc** | Giới hạn nào phải tuân thủ? | Dữ liệu phải lưu trong vùng được phê duyệt | Kiểm tra tính hợp lệ của mọi phương án |
| **Quyết định kiến trúc** | Ta chọn cách nào, vì sao? | Chọn multi-AZ và warm standby | Ghi ADR, phương án bỏ, bằng chứng, hậu quả |
| **Nợ kiến trúc** | Cấu trúc nào đang làm tăng chi phí hoặc cản trở tương lai? | Một schema dùng chung khiến release của hai domain phụ thuộc | Đo ảnh hưởng, đặt ngưỡng xử lý, theo dõi lộ trình |

**Điểm phân biệt quan trọng:**

- “Database đang lỗi” là **issue**; “database có thể lỗi khi tải tăng” là **risk**.
- “Công ty chỉ được lưu dữ liệu ở khu vực đã phê duyệt” là **constraint** cần được xác nhận từ nguồn có thẩm quyền; không nên biến yêu cầu pháp lý bắt buộc thành một rủi ro có thể chấp nhận bằng điểm số.
- “Giả định truy cập chủ yếu từ Việt Nam” không phải là quyết định chọn region. **Chọn region** là quyết định cần ghi lý do và các giả định phía sau.
- Một hệ thống chưa tách microservices không mặc nhiên có nợ kiến trúc. Chỉ gọi là nợ khi chỉ ra được **chi phí, rủi ro hoặc hạn chế cụ thể so với nhu cầu hiện tại hay dự kiến**.

### Quan hệ qua vòng đời thiết kế

~~~mermaid
flowchart TD
    Q["Yêu cầu nghiệp vụ và chất lượng"] --> A["Giả định có owner và bằng chứng"]
    Q --> ADR["Quyết định kiến trúc (ADR)"]
    A --> ADR
    ADR --> DIAG["Sơ đồ logic / triển khai / luồng dữ liệu"]
    A --> R["Rủi ro có thể phát sinh"]
    ADR --> R
    ADR --> D["Nợ kiến trúc / đánh đổi tồn đọng"]
    DIAG --> T["Kiểm thử, diễn tập và đo vận hành"]
    T --> A
    T --> R
    T --> D
    R --> REV["Rà soát và thay đổi có kiểm soát"]
    D --> REV
    REV --> ADR
~~~

Sơ đồ biểu diễn các liên kết về trách nhiệm và bằng chứng, không phải một trình tự luôn tuyến tính. Nhóm có thể phát hiện rủi ro hoặc nợ ở bất kỳ giai đoạn nào, kể cả sau nhiều năm chạy production.

## 3. Quản lý giả định như những giả thuyết có thể kiểm chứng

### 3.1. Cách viết một giả định tốt

Giả định tốt cần cụ thể, kiểm chứng được và có hậu quả nếu sai. Dùng mẫu:

> **Chúng ta giả định** [điều kiện/giá trị] **trong** [phạm vi và thời gian], **dựa trên** [nguồn chứng cứ]; **nếu sai** [tác động]; **sẽ kiểm chứng bằng** [phương pháp, mốc hoàn thành, owner].

Ví dụ:

> **A-01:** Trong ba tháng đầu sau phát hành, p95 tải ở cổng API không quá 300 request/giây trong khung giờ cao điểm, theo kế hoạch bán hàng hiện tại. Bằng chứng là lượng khách thử nghiệm và dự báo Product. Nếu sai, chính sách autoscaling và capacity database phải xem xét lại. SRE sẽ đối chiếu dự báo với load test và telemetry sau mỗi tuần vận hành trong tháng đầu.

Giá trị 300 request/giây ở đây là **giả định minh họa**, không phải ngưỡng khuyến nghị chung.

Một số nguồn giả định thường gặp trong thiết kế cloud:

| Khu vực | Giả định cần làm rõ | Cách kiểm chứng |
| --- | --- | --- |
| **Nghiệp vụ** | Người dùng đồng thời, sự kiện cao điểm, quốc gia truy cập | Phỏng vấn Product, số liệu thực, kịch bản tăng trưởng |
| **Mạng** | Độ trễ tới region, băng thông tới đối tác, độ ổn định DNS | Đo thực nghiệm từ địa điểm sử dụng, kiểm tra đường kết nối |
| **Compute** | CPU/ram mỗi request, tốc độ autoscaling, thời gian cold start | Benchmark, load test, quan sát khởi động và saturation |
| **Dữ liệu** | Tỷ lệ đọc/ghi, kích thước bản ghi, tốc độ tăng, nhu cầu nhất quán | Phân tích workload, thử index/partition, kiểm thử đồng thời |
| **Độ tin cậy** | Phụ thuộc có thể chịu lỗi cục bộ, replica đủ năng lực phục hồi | Fault injection, thử chuyển AZ/region, diễn tập restore |
| **Bảo mật** | Phân loại dữ liệu, vùng lưu trú được phép, cách quản lý identity | Xác nhận của Security/Legal, data flow mapping và threat model |
| **Chi phí** | Giá dự báo, tỷ lệ dùng tài nguyên, lượng dữ liệu ra/vào | Cost model, kiểm tra hóa đơn và cảnh báo ngân sách |
| **Vận hành** | Đội có khả năng trực 24/7, xử lý multi-region, quản lý IaC | Đánh giá năng lực, tabletop exercise, rehearsal runbook |

### 3.2. Sổ đăng ký giả định (Assumption Log)

| ID | Giả định | Mức tin cậy | Bằng chứng hiện có | Hậu quả nếu sai | Kiểm chứng / Hạn | Owner | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01 | Tải đỉnh không vượt 300 req/s trong giai đoạn thử nghiệm | Trung bình | Dự báo từ Product, ít dữ liệu production | API/DB có thể quá tải | Load test và đo tuần 1; trước go-live | SRE | Chưa xác nhận |
| A-02 | Đối tác thanh toán trả kết quả trong khoảng chấp nhận của checkout | Thấp | Kết quả sandbox | Request timeout, trạng thái thanh toán không rõ | Đo môi trường thực, thử lỗi; trước go-live | Nhóm Payment | Cần thử |
| A-03 | Vùng dự phòng được phê duyệt để lưu dữ liệu khách hàng | Thấp | Thảo luận sơ bộ | Thiết kế sao chép dữ liệu vi phạm chính sách | Security/Legal xác nhận bằng văn bản | Security | Chặn quyết định |
| A-04 | Nhóm trực vận hành có thể phục hồi trong 60 phút | Thấp | Runbook chưa diễn tập | Không đạt mục tiêu RTO | Diễn tập mất vùng, ghi thời gian thực | SRE | Cần thử |

**Mức tin cậy** nên dựa trên loại bằng chứng: tài liệu hợp đồng/chính sách, dữ liệu production, bài thử có điều kiện gần thực tế, prototype, ước tính chuyên gia hay suy đoán. Không nên gán “90% chắc chắn” nếu chưa có cơ sở định lượng.

Một giả định có thể ở các trạng thái: **Mới → Đang kiểm chứng → Đã xác nhận / Bị bác bỏ / Không còn áp dụng**. Khi bác bỏ, phải tìm các ADR, sơ đồ, risk register và kế hoạch kiểm thử đang phụ thuộc vào nó.

### 3.3. Ưu tiên kiểm chứng giả định

Không phải giả định nào cũng đáng tốn công bằng nhau. Ưu tiên dựa trên:

1. **Tác động nếu sai:** ảnh hưởng doanh thu, dữ liệu, tính đúng đắn, SLO, tuân thủ hay khả năng khôi phục?
2. **Độ bất định:** bằng chứng mạnh đến đâu, còn thiếu gì?
3. **Tính không thể đảo ngược:** sai ở bước này có buộc thay dữ liệu, region, hợp đồng hay nền tảng không?
4. **Thời điểm cần biết:** có chặn quyết định kiến trúc hoặc ngày phát hành sắp tới không?
5. **Chi phí kiểm chứng:** một spike, benchmark hay cuộc rà soát có thể giảm bao nhiêu bất định?

Ví dụ, giả định về **vùng lưu trú dữ liệu** phải xác nhận trước khi chọn nơi tạo replica; giả định về màu sắc dashboard có thể để sau. Ưu tiên kiểm chứng không giống xếp hạng mong muốn sản phẩm: giả định an toàn quan trọng phải được xử lý dù kiểm thử tốn công.

### 3.4. Thiết kế một phép thử bác bỏ được giả định

Giả định: “Một database primary với 2.000 kết nối tối đa có thể phục vụ tải mục tiêu.”

Phép thử cần mô tả:

- **Workload**: bao nhiêu giao dịch/giây, tỷ lệ đọc/ghi, dữ liệu tương đương bao nhiêu tenant/đơn hàng.
- **Môi trường**: cấu hình instance, pool kết nối, số replica, network, cache và điều kiện khởi tạo dữ liệu.
- **Chỉ số**: p95/p99, error rate, active connections, CPU, IOPS, lock waits, queue age và chi phí.
- **Tiêu chí quyết định**: ngưỡng nào phải đạt, ai phê duyệt và margin an toàn dự kiến.
- **Điều kiện thử thêm**: một replica lỗi, cache miss tăng, giao dịch có truy vấn nặng, vùng mạng có độ trễ cao.

Kết quả nên được ghi với ngày, cấu hình, phiên bản, dữ liệu thử và liên kết report. Một bài thử trên dataset nhỏ không chứng minh hệ thống chịu được tải production dài hạn.

## 4. Đăng ký rủi ro kiến trúc và cách đánh giá

### 4.1. Viết rủi ro đủ rõ để hành động

Cấu trúc hữu ích:

> **Do** [nguyên nhân/điều kiện], **có khả năng** [sự kiện chưa chắc xảy ra], **dẫn đến** [hậu quả lên mục tiêu đo được].

Ví dụ:

> **R-05:** Do payment provider có thể trả callback trễ sau khi API caller timeout, hệ thống có thể gửi lại lệnh thanh toán mà không tra cứu trạng thái, dẫn tới **thu tiền trùng** và phát sinh chi phí đối soát/hoàn tiền.

Câu “thanh toán có rủi ro” quá rộng; chưa có tác nhân, hậu quả hoặc đầu mối xử lý.

### 4.2. Phân nhóm rủi ro theo kiến trúc cloud

| Nhóm | Ví dụ sự kiện rủi ro | Tín hiệu cảnh báo / kiểm soát |
| --- | --- | --- |
| **Reliability/DR** | Mất cả vùng hoặc lỗi backup không thể restore | Replica lag, diễn tập DR, backup validation |
| **Security** | Lộ secret, quyền quá rộng, truy cập chéo tenant | IAM review, secret scanning, pentest/authorization tests |
| **Data integrity** | Đặt chỗ trùng, sự kiện bị xử lý hai lần, không nhất quán | Idempotency, constraint DB, reconciliation |
| **Performance** | Fan-out API, DB saturation, noisy neighbor | p95/p99, error rate, saturation, quota |
| **Scalability** | Không mở rộng kịp trong đợt cao điểm | Load test, autoscaling signal, queue age |
| **Cost** | Egress, replication hoặc log vượt ngân sách | Budget alerts, forecast, cost allocation |
| **Dependency/vendor** | Service cloud, DNS, API đối tác gặp sự cố | SLA/dependency map, fallback, timeout, tabletop |
| **Operations** | Cấu hình drift, thiếu quyền xử lý sự cố, runbook sai | IaC drift detection, diễn tập, on-call readiness |
| **Compliance** | Dữ liệu ở vùng chưa được phê duyệt | Data classification, flow mapping, Legal review |

### 4.3. Đánh giá khả năng xảy ra và mức ảnh hưởng

Một ma trận định tính giúp **sàng lọc**, không tạo ra xác suất chính xác:

| Khả năng \ Tác động | Thấp | Trung bình | Cao |
| --- | --- | --- | --- |
| **Thấp** | Theo dõi | Theo dõi hoặc giảm nhẹ | Ưu tiên kiểm soát |
| **Trung bình** | Giảm nhẹ khi hợp lý | Lập kế hoạch giảm nhẹ | Ưu tiên cao |
| **Cao** | Lập kế hoạch | Ưu tiên cao | Xử lý khẩn / escalated |

Mô tả các mức theo bối cảnh thực tế: tác động cao có thể là mất dữ liệu khách hàng, không đáp ứng điều kiện bảo mật, ngừng giao dịch kéo dài hoặc mất doanh thu lớn. Khả năng cao là sự kiện đã xuất hiện thường xuyên hoặc có bằng chứng mạnh cho thấy sẽ xảy ra trong chân trời đánh giá.

Nếu tổ chức dùng điểm số, có thể đặt thang **likelihood 1–5** và **impact 1–5** để hỗ trợ xếp hạng, nhưng phép nhân hai thang **thứ bậc (ordinal)** chỉ là chỉ báo thô; không nên coi “16” là tổn thất định lượng chính xác gấp đôi “8”. Với sự kiện có dữ liệu xác suất và thiệt hại đáng tin cậy, có thể ước tính **expected loss = xác suất × hậu quả**, đồng thời phân tích kịch bản đuôi rủi ro.

**Quan trọng:** rủi ro tuân thủ/pháp lý có điều kiện bắt buộc phải được xử lý theo yêu cầu có thẩm quyền; không thể dùng điểm thấp để tự phê duyệt vi phạm.

### 4.4. Risk Register thực dụng

| ID | Rủi ro và hậu quả | Khả năng / Ảnh hưởng | Kiểm soát hiện có | Kế hoạch xử lý | Owner / Hạn |
| --- | --- | --- | --- | --- | --- |
| R-01 | Mất region chính làm dịch vụ đặt chỗ ngừng quá RTO | Trung bình / Cao | Backup hằng ngày | Warm standby + diễn tập failover | SRE / trước go-live |
| R-02 | Retry không idempotent gây thu tiền trùng | Trung bình / Cao | Timeout API | Payment key, tra cứu trạng thái, test replay | Payment / sprint 3 |
| R-03 | Truy vấn báo cáo làm chậm checkout ở DB chung | Cao / Trung bình | Dashboard DB CPU | Queue/replica, quota, đo p95 checkout | Data / sprint 4 |
| R-04 | Nhầm region lưu backup dẫn đến vi phạm chính sách | Chưa xác định / Cao | Tag tài nguyên | Security/Legal duyệt vùng, policy-as-code | Security / trước provisioning |
| R-05 | Egress liên vùng tăng vượt ngân sách | Trung bình / Trung bình | Budget alerts | Đo lưu lượng thực, cost forecast, giới hạn replication | FinOps / hằng tháng |

Sau khi hành động hoàn tất, ghi **rủi ro còn lại (residual risk)**, bằng chứng và người có quyền chấp nhận. Một rủi ro không biến mất chỉ vì có ticket “đã triển khai retry”: cần chứng minh retry không làm phát sinh tác dụng phụ khi timeout, mất gói và nhận sự kiện trùng.

### 4.5. Bốn cách ứng phó rủi ro

- **Avoid — Tránh:** đổi giải pháp hoặc phạm vi để không tạo ra rủi ro cụ thể. Ví dụ không sao chép dữ liệu cá nhân sang vùng chưa được phép.
- **Mitigate — Giảm:** giảm khả năng hoặc hậu quả bằng kiểm soát. Ví dụ multi-AZ, backup có kiểm thử restore, IAM tối thiểu quyền, rate limit.
- **Transfer/Share — Chuyển giao/chia sẻ:** hợp đồng, bảo hiểm hoặc dịch vụ quản lý có thể chuyển một phần trách nhiệm/thiệt hại, nhưng **không xóa trách nhiệm** với dữ liệu hay khách hàng.
- **Accept — Chấp nhận:** ghi rõ lý do, thời hạn, ngưỡng kích hoạt, người có thẩm quyền và rủi ro còn lại; chỉ áp dụng nếu hợp lệ theo chính sách/risk appetite.

**Tránh “accept” ngầm** bằng cách không ghi rủi ro, không có owner hoặc tự cho rằng SLA nhà cung cấp sẽ bồi thường toàn bộ tổn thất.

## 5. Nợ kiến trúc là gì và hình thành như thế nào?

### 5.1. Từ đánh đổi hiện tại thành chi phí tương lai

**Architecture debt** là hậu quả tích lũy từ một thiết kế hoặc cấu trúc khiến hệ thống tốn nhiều công sức, rủi ro hoặc chi phí hơn khi thay đổi trong tương lai. Nó là một phần của technical debt, nhấn mạnh tác động ở **ranh giới thành phần, dữ liệu, phụ thuộc, mô hình triển khai, khả năng mở rộng và vận hành**.

Nợ có thể phát sinh do:

1. **Chủ động vay để ra mắt:** tạm dùng một queue chung vì chưa có dữ liệu tải để thiết kế phân cell.
2. **Thiếu thông tin:** chọn một region theo dự báo sai về vị trí khách hàng, sau đó cần di trú.
3. **Thay đổi yêu cầu:** từ 10 tenant tăng thành 1.000 tenant, giới hạn mô hình dữ liệu cũ trở nên nghiêm trọng.
4. **Tích lũy qua các thay đổi:** nhiều service dần phụ thuộc trực tiếp vào schema và API nội bộ của nhau.
5. **Bỏ qua công việc nền:** không có IaC, tracing, backup restore test, policy enforcement hoặc contract testing.

Không phải mọi lựa chọn đơn giản hóa đều là nợ. Nếu modular monolith vẫn đáp ứng SLO, chi phí và tốc độ phát hành, việc **chưa tách microservices** không tự thân tạo nợ.

### 5.2. “Gốc nợ” và “lãi nợ”

- **Principal — phần phải sửa:** công sức dự kiến để thiết kế lại, di trú dữ liệu, sửa phụ thuộc, kiểm thử và phát hành.
- **Interest — chi phí tiếp tục gánh:** mỗi lần triển khai mất thêm thời gian; chi phí hạ tầng phát sinh; sự cố lặp lại; tăng thời gian khôi phục; thêm lỗi bảo mật hoặc nhiều nhóm bị chặn.

Ví dụ nợ “cơ sở dữ liệu dùng chung”:

- Principal: tách quyền sở hữu Booking/Reporting, xây read model và di trú truy vấn.
- Interest: báo cáo chạy nặng làm tăng p95 checkout; migration của Reporting buộc Booking release cùng đợt; DB luôn cần nâng cấu hình cho tải hỗn hợp.

**Đừng tự động xóa mọi khoản nợ.** Một khoản nợ có principal lớn nhưng interest thấp và không đe dọa mục tiêu hiện tại có thể được theo dõi với ngưỡng đánh giá lại. Một khoản nợ có thể gây mất dữ liệu hoặc không đáp ứng yêu cầu bắt buộc cần xử lý sớm, bất kể áp lực ra mắt.

### 5.3. Debt Register

| ID | Khoản nợ | Lý do/ADR | Interest quan sát được | Phương án xử lý | Trigger/Owner |
| --- | --- | --- | --- | --- | --- |
| D-01 | Booking và Reporting dùng một DB primary | ADR-008: ưu tiên ra mắt MVP | p95 checkout tăng khi chạy báo cáo; tăng IOPS | Read replica/read model, chuyển batch | Khi p95 vượt mục tiêu hoặc DB > ngưỡng; Data |
| D-02 | Chưa có IaC cho vùng dự phòng | ADR-012: chỉ triển khai một vùng ban đầu | Cấu hình DR drift, diễn tập chậm | IaC + pipeline + runbook | Trước khi cam kết RTO mới; Platform |
| D-03 | API thay đổi không có contract test | Phát triển tích hợp nhanh | Lỗi consumer khi nâng phiên bản | Consumer-driven contract tests, version policy | Sự cố tương thích tiếp theo; API lead |
| D-04 | Logging đồng nhất nhưng thiếu trace xuyên dịch vụ | Chưa thiết lập correlation | MTTR tăng, khó truy nguyên | Tracing, trace propagation, dashboard | Khi luồng > 3 bước đồng bộ hoặc MTTR vượt ngưỡng; SRE |

Một bản ghi nợ nên có: **ID, thành phần, mô tả, nguyên nhân, bằng chứng, tác động, owner, phương án/ước tính, rủi ro khi xử lý, trigger và trạng thái**. Đánh dấu “đã trả” chỉ khi bằng chứng thực tế cho thấy tác động đã giảm và giải pháp cũ được loại bỏ hoặc giới hạn phù hợp.

## 6. Tách nợ kiến trúc khỏi “chưa hoàn thiện”

Không nên biến backlog thành một kho chứa mọi việc chưa làm. Ba loại cần xử lý khác nhau:

| Hiện tượng | Phân loại phù hợp | Ví dụ |
| --- | --- | --- |
| Khả năng mới chưa từng được yêu cầu | Feature backlog | Chưa có đa ngôn ngữ cho ứng dụng nội bộ |
| Đang vi phạm yêu cầu được chấp thuận | Defect / gap / issue | Không mã hóa dữ liệu nhạy cảm theo chính sách đã phê duyệt |
| Một lựa chọn thiết kế tạo chi phí thay đổi hoặc rủi ro tích lũy | Architecture debt | Nhiều team không thể phát hành vì chia sẻ schema không có ownership |
| Nguy cơ tương lai có thể gây mất mục tiêu | Risk | Backup có thể không restore đủ nhanh vì chưa diễn tập |
| Một dữ kiện chưa đủ chứng cứ | Assumption | Chỉ 10% khách hàng sẽ chạy báo cáo trong giờ cao điểm |

Các đối tượng có thể **liên kết**: một khoản nợ (không có kiểm thử restore tự động) làm tăng rủi ro (không đạt RTO) do giả định (nhóm vận hành có thể phục hồi thủ công trong 60 phút) chưa được xác minh. Không cần tạo ba ticket trùng lặp nội dung; nên tạo bản ghi theo trách nhiệm khác nhau và liên kết qua ID.

## 7. Liên kết sổ đăng ký với sơ đồ và ADR

Một bản vẽ kiến trúc chỉ hữu dụng nếu người xem biết **phiên bản nào đang mô tả production**, ranh giới nào là sự thật, thành phần nào mới dự kiến và quyết định nào đặt ra ràng buộc.

### 7.1. Sơ đồ cần thể hiện điều gì?

Ở mỗi mức sơ đồ, thêm thông tin hợp lý mà không làm rối:

- **Context diagram:** người dùng, hệ thống ngoài, nhà cung cấp và ranh giới trách nhiệm; ghi phụ thuộc trọng yếu có risk ID.
- **Container/Deployment diagram:** ứng dụng, DB, cache, queue, network, region, AZ, data flow; ghi trạng thái hiện tại hoặc mục tiêu và các giả định tác động lớn.
- **Component/Sequence diagram:** luồng nghiệp vụ quan trọng, retry, timeout, idempotency, chuyển trạng thái, điểm có thể trùng/mất thông điệp.
- **Data-flow / threat model:** phân loại dữ liệu, trust boundary, điểm mã hóa và nơi lưu/replicate.
- **Operational/DR diagram:** backup, replica, đường failover, quyền và dịch vụ phụ thuộc; liên kết runbook và phép thử.

Một sơ đồ nên có **tên, mục đích, phạm vi, ngày cập nhật, owner, trạng thái as-is/to-be và liên kết tài liệu liên quan**. Rủi ro quan trọng nên được biểu diễn bằng nhãn ngắn như R-02; chi tiết phân tích nằm trong risk register.

### 7.2. Ví dụ sơ đồ gắn assumption/risk/debt ID

~~~mermaid
flowchart LR
    U["Người dùng"] --> GW["Gateway / WAF"]
    GW --> API["Booking API\nA-01: tải đỉnh"]
    API --> DB[("DB primary - AZ 1\nR-01: lỗi region\nD-01: báo cáo dùng chung")]
    API --> PAY["Payment provider\nA-02: độ trễ callback\nR-02: thanh toán trùng"]
    DB --> BAK[("Backup\nR-03: restore chưa kiểm chứng")]
    DB -. "Read/analytics query" .-> REP["Reporting"]
~~~

Khi bản sơ đồ thay đổi, người review cần biết: liệu R-01 đã được giảm chưa, D-01 còn tồn tại không, và A-02 đã được đo trên môi trường đại diện chưa. Nếu một thành phần bị xóa, cần xem xét các ID liên kết trước khi đóng bản ghi.

### 7.3. Liên kết theo chuỗi yêu cầu → quyết định → bằng chứng

~~~text
REQ-AVAIL-01: RTO <= 60 phút và RPO <= 15 phút
  ├── A-04: đội trực có thể hoàn tất failover trong 60 phút?
  ├── R-01: mất region chính làm gián đoạn đặt chỗ
  ├── ADR-012: chọn warm standby tại region được phê duyệt
  │     ├── DIAG-DEPLOY-03: sơ đồ region/AZ/replication
  │     └── D-02: IaC vùng dự phòng chưa hoàn chỉnh
  ├── TEST-DR-05: diễn tập mất region, đo RTO/RPO
  └── RUNBOOK-DR-02: failover/failback và đối soát dữ liệu
~~~

Các ID là **ví dụ minh họa**. Chuỗi trên giúp trả lời câu hỏi của người kiểm tra: “Có thể chứng minh cam kết khôi phục không?” bằng cách truy tới phương án, sơ đồ, diễn tập và trạng thái nợ còn tồn.

## 8. Ghi ADR với giả định, rủi ro và điều kiện đảo ngược

**Architecture Decision Record (ADR)** là biên bản ghi một quyết định quan trọng cùng bối cảnh và hậu quả. Một ADR hữu ích không chỉ ghi “chọn dịch vụ X”, mà nói rõ **trong điều kiện nào lựa chọn đó đúng**.

### Ví dụ ADR rút gọn

~~~markdown
# ADR-012: Vùng dự phòng cho dịch vụ đặt chỗ

Trạng thái: Chấp thuận có điều kiện
Ngày: YYYY-MM-DD
Decision owner: Kiến trúc sư hệ thống và đại diện nghiệp vụ

Bối cảnh:
- REQ-AVAIL-01: RTO <= 60 phút; RPO <= 15 phút.
- REQ-COST-01: hạ tầng cloud không vượt ngân sách đã phê duyệt.
- A-03: vùng dự phòng hợp lệ về lưu trú dữ liệu (cần xác nhận).
- A-04: SRE có thể khôi phục trong thời gian yêu cầu.

Phương án:
A. Một region multi-AZ, backup định kỳ.
B. Region chính multi-AZ + warm standby region dự phòng.
C. Hai region active-active.

Quyết định đề xuất:
- Chọn B nếu A-03 được Security/Legal xác nhận và
  TEST-DR-05 chứng minh đạt cả RTO và RPO.
- Không công bố RTO/RPO đạt trước khi có kết quả diễn tập.

Đánh đổi và rủi ro:
- R-01: lỗi region, được giảm bằng standby và runbook.
- D-02: tạm thiếu IaC standby, phải xử lý trước cam kết.
- Replication có chi phí và không thay cho backup phục hồi thời điểm.

Điều kiện xem xét lại:
- Diễn tập DR không đạt; thay đổi chính sách dữ liệu;
  tải hoặc chi phí tăng vượt ngưỡng; mục tiêu RTO/RPO thay đổi.

Bằng chứng liên kết:
- DIAG-DEPLOY-03, TEST-DR-05, RUNBOOK-DR-02, COST-PLAN-01.
~~~

Các giá trị RTO/RPO chỉ là **yêu cầu minh họa**. Một mô hình multi-AZ hoặc warm standby không mặc nhiên bảo đảm mục tiêu; phải kiểm thử failover, replication lag, khả năng khôi phục dữ liệu và phụ thuộc ngoài vùng.

**Khi quyết định thay đổi**, tạo ADR mới hoặc cập nhật trạng thái ADR cũ thành *superseded* theo quy trình tổ chức, có liên kết hai chiều. Không xóa lịch sử đánh đổi đã từng dẫn tới kiến trúc hiện tại.

## 9. Ưu tiên hành động: kiểm chứng, giảm rủi ro hay trả nợ trước?

Không có một thang điểm chung áp dụng được cho mọi loại. Hãy thực hiện theo thứ tự:

1. **Điều kiện bắt buộc:** xử lý lỗ hổng, vi phạm chính sách/hợp đồng và lỗi đang gây ảnh hưởng với quy trình khẩn cấp thích hợp.
2. **Bất định làm thay đổi quyết định lớn:** kiểm chứng giả định có khả năng khiến nhóm chọn sai region, mô hình dữ liệu, cách phục hồi hoặc nền tảng.
3. **Rủi ro có hậu quả cao:** xây dựng kiểm soát, diễn tập và xác định rủi ro còn lại, đặc biệt với dữ liệu và luồng doanh thu.
4. **Nợ làm tăng chi phí và xác suất sự cố theo thời gian:** ưu tiên bằng số liệu MTTR, lỗi thay đổi, thời gian triển khai, hóa đơn và SLO.
5. **Công việc tối ưu bổ sung:** xem xét khi đã đạt yêu cầu chất lượng và nguồn lực còn lại.

Có thể lập **bảng lựa chọn hành động**:

| Việc | Giá trị nếu làm | Chi phí/nỗ lực | Tác động nếu trì hoãn | Quyết định minh họa |
| --- | --- | --- | --- | --- |
| Xác minh A-03 (vùng lưu dữ liệu) | Loại rủi ro chọn sai kiến trúc | Thấp/trung bình | Có thể buộc di trú dữ liệu | Làm trước provisioning |
| Diễn tập R-01 (mất region) | Xác nhận RTO/RPO | Trung bình | Có thể cam kết quá mức | Chặn go-live tới khi đạt |
| Sửa D-01 (Reporting chung DB) | Giảm p95 và độc lập thay đổi | Trung bình/cao | Lỗi tiếp diễn khi báo cáo tăng | Lập kế hoạch theo tải đo |
| Nâng cấp dashboard phụ | Cải thiện trải nghiệm nội bộ | Thấp | Ít ảnh hưởng mục tiêu cốt lõi | Có thể hoãn |

Có thể dùng phương pháp **chi phí trì hoãn so với quy mô công việc** cho các hạng mục tương đồng nếu có dữ liệu đủ tốt. Tuy nhiên số liệu ước tính cần ghi nguồn và khoảng bất định; không nên tạo sự chính xác giả hoặc gộp rủi ro tuân thủ bắt buộc vào danh sách để chấm điểm tùy ý.

### Chiến lược giảm nợ theo mức can thiệp

- **Ngăn nợ tăng:** hạn chế phụ thuộc mới vào schema chung, áp hợp đồng API và automated architecture checks.
- **Khoanh vùng:** quota, tách pool hoặc queue cho workload nặng, giới hạn blast radius.
- **Trả nợ từng phần:** tách read model trước, di trú dữ liệu từng nhóm, đo ảnh hưởng và gỡ đường cũ.
- **Thay đổi kiến trúc:** khi nợ làm tổn hại mục tiêu nền tảng, lập ADR mới và kế hoạch migration/rollback.
- **Chấp nhận có thời hạn:** khi chi phí sửa lớn hơn lãi đang gánh và không có vi phạm bắt buộc, ghi trigger để xem xét lại.

Ưu tiên các thay đổi **nhỏ, có thể đo và có đường quay lui** nếu không bắt buộc thực hiện thay đổi lớn ngay.

## 10. Đo lường để quản trị dựa trên bằng chứng

Chỉ số tốt phải trả lời được: giả định nào đã được chứng minh, rủi ro nào còn lớn và nợ nào thực sự gây tổn hại?

### 10.1. Chỉ số chất lượng cloud

| Mục tiêu | Chỉ số theo dõi | Nên làm gì khi vượt ngưỡng |
| --- | --- | --- |
| Độ tin cậy | SLI/SLO, error budget, tỷ lệ sự cố, MTTR, kết quả DR | Mở risk/issue, xác định dependency và kiểm chứng phục hồi |
| Hiệu năng | p95/p99 latency, saturation, throughput, queue age | Kiểm tra giả định tải, cache, DB, network và autoscaling |
| Bảo mật | Số sai lệch IAM, phát hiện cấu hình nguy hiểm, thời gian xử lý lỗ hổng | Escalate theo mức độ nguy hiểm, cập nhật threat model/ADR |
| Khả năng mở rộng | Tỷ lệ request bị throttling, autoscaling lag, growth rate | Kiểm thử capacity, điều chỉnh quota và kiến trúc dữ liệu |
| Chi phí | Dự báo ngân sách, cost/request, egress, DB/compute idle | Kiểm tra giả định tài nguyên, đưa nợ chi phí vào backlog |
| Vận hành | Lead time for change, deployment failure, toil, thời gian phục hồi | Xem xét nợ CI/CD, quan sát và ownership |
| Dữ liệu | Replication lag, backup success, restore verification, reconciliation errors | Kiểm tra RPO/RTO và rủi ro tính toàn vẹn dữ liệu |

**Error budget** là phần lỗi cho phép theo một SLO đã xác định. Nó có thể giúp Product và SRE thảo luận tốc độ phát hành so với độ ổn định, nhưng không thể dùng để biện minh cho việc bỏ qua nghĩa vụ bảo mật hoặc lưu trú dữ liệu.

### 10.2. Chỉ số quản lý giả định/rủi ro/nợ

- **Giả định:** số giả định ảnh hưởng lớn chưa có bằng chứng; tuổi của giả định; tỷ lệ xác minh trước mốc quyết định; số lần giả định bị bác bỏ gây thay đổi.
- **Rủi ro:** số rủi ro cao chưa có phương án xử lý; thời gian mở; mức rủi ro còn lại sau diễn tập; số rủi ro vượt ngưỡng nhưng chưa được owner phê duyệt.
- **Nợ kiến trúc:** thời gian chờ trả nợ; lãi nợ thể hiện qua sự cố, thời gian triển khai hoặc chi phí; phần chi phí vận hành do hạn chế thiết kế; tỷ lệ khoản nợ có trigger và owner rõ.
- **Độ truy vết:** ADR quan trọng có liên kết yêu cầu, sơ đồ, giả định, bằng chứng kiểm thử và runbook; số tài liệu không cập nhật sau thay đổi production.

Số ticket được đóng **không đủ** để chứng minh chất lượng kiến trúc tăng. Ví dụ đóng D-01 chỉ vì tạo read replica trong khi checkout vẫn chậm do lock contention khác thì chưa giải quyết được vấn đề.

## 11. Thiết lập vòng quản trị theo thay đổi và thời gian

Quản lý giả định, rủi ro và nợ không nên chỉ diễn ra lúc thiết kế ban đầu.

### 11.1. Một chu kỳ vận hành đề xuất

~~~mermaid
flowchart LR
    A["Thu thập: review kiến trúc, incident, telemetry"] --> B["Phân loại: assumption / risk / issue / debt"]
    B --> C["Owner + ảnh hưởng + hạn + liên kết ADR/sơ đồ"]
    C --> D["Kiểm chứng hoặc hành động xử lý"]
    D --> E["Đo kết quả và residual risk"]
    E --> F{"Có thay đổi mục tiêu/giả định?"}
    F -- "Có" --> G["Cập nhật ADR, sơ đồ, kế hoạch"]
    G --> A
    F -- "Không" --> H["Theo dõi trigger và ngày xem lại"]
    H --> A
~~~

Ở mỗi vòng, người chịu trách nhiệm phải phân biệt **quyết định đã phê duyệt**, **việc đang làm**, **điều còn giả định** và **rủi ro được chấp nhận**.

### 11.2. Sự kiện kích hoạt rà soát

- Ra mắt thị trường/kênh mới, thay đổi lưu lượng, nhiều tenant hoặc vùng dữ liệu mới.
- Thay đổi yêu cầu hợp đồng, chính sách bảo mật hoặc phân loại dữ liệu.
- Tăng trưởng chi phí cloud vượt dự báo, đổi mô hình giá hoặc dùng dịch vụ managed mới.
- SLO bị vi phạm, bài diễn tập DR không đạt, sự cố nghiêm trọng hoặc lỗi dữ liệu.
- Thay đổi lớn về API/DB/network, di trú region, multi-AZ/multi-region, tách service.
- Nhà cung cấp thay đổi giới hạn dịch vụ, vòng đời hỗ trợ hoặc chính sách vận hành.

### 11.3. Quyền sở hữu và phê duyệt

| Vai trò | Trách nhiệm |
| --- | --- |
| **Product/Business owner** | Xác nhận tác động tới người dùng, doanh thu, hạn chót và chấp nhận đánh đổi nghiệp vụ trong thẩm quyền |
| **Architecture/Tech lead** | Duy trì ADR, dependency map, giả định và nợ cấu trúc; đề xuất phương án |
| **SRE/Platform** | Chứng minh SLO, RTO/RPO, vận hành, quan sát và diễn tập DR |
| **Security/Legal** | Xác nhận điều kiện bảo mật, dữ liệu và tuân thủ, quyết định trong thẩm quyền |
| **Finance/FinOps** | Xác minh cost model, hạn mức, dự báo và chi phí thực |
| **Risk/Steering owner** | Giải quyết xung đột liên phòng ban, quyết định chấp nhận rủi ro còn lại theo chính sách |

Người đề xuất một rủi ro không nhất thiết có thẩm quyền **chấp nhận** rủi ro đó. Rủi ro vượt ngưỡng phải có đường chuyển cấp (escalation) rõ và thời hạn quyết định.

## 12. Tình huống xuyên suốt: ứng dụng đặt chỗ sắp mở rộng thị trường

### 12.1. Bối cảnh

Một ứng dụng đặt chỗ trên cloud đang dùng:

- API và worker trong một region với nhiều availability zone.
- Một database chính phục vụ Booking và Reporting, backup hằng ngày.
- API thanh toán bên ngoài.
- Nhóm vận hành nhỏ, chưa diễn tập chuyển sang region khác.

Kế hoạch kinh doanh đưa thêm khách hàng doanh nghiệp và chiến dịch có tải cao. Các mục tiêu được đề xuất (giá trị **minh họa**) gồm: p95 checkout không quá **400 ms** trong kịch bản tải thống nhất, **RTO ≤ 60 phút**, **RPO ≤ 15 phút**, và chi phí cloud không vượt ngân sách được phê duyệt. Security yêu cầu xác minh vùng lưu dữ liệu và backup trước mở rộng.

### 12.2. Phân tích

| ID | Phát biểu | Quan hệ | Việc tiếp theo |
| --- | --- | --- | --- |
| A-11 | Tải đỉnh không quá 800 request/giây | Ảnh hưởng capacity và cost | Load test với tỷ lệ đọc/ghi đại diện |
| A-12 | Một region dự phòng được phép lưu replica | Điều kiện bắt buộc cần chứng cứ | Xác nhận Security/Legal trước tạo tài nguyên |
| A-13 | Đội vận hành khôi phục trong 60 phút | Liên quan RTO | Tabletop và diễn tập DR thực tế |
| R-11 | Database quá tải do Reporting khi chiến dịch cao điểm, làm checkout chậm | Phụ thuộc A-11 và D-11 | Quota, chuyển read workload, đo p95 |
| R-12 | Backup và replica chưa thử restore có thể làm vượt RTO/RPO | Phụ thuộc A-13 | Diễn tập và ghi kết quả |
| R-13 | Timeout Payment tạo trạng thái không rõ, retry gây thu trùng | Liên quan dependency ngoài | Idempotency, tra cứu giao dịch, reconciliation |
| D-11 | Booking và Reporting dùng chung DB/schema | Lãi nợ: p95 và release coupling | Tách read model theo giai đoạn |
| D-12 | Hạ tầng dự phòng chưa có IaC | Lãi nợ: restore chậm, drift | Mẫu IaC, pipeline và runbook |

Nhóm **chưa thể cam kết** đạt RTO/RPO chỉ dựa vào việc có backup hoặc nhiều AZ. Nếu A-12 bị bác bỏ, phương án đa region đang xem xét cần thay đổi; không tự chuyển dữ liệu sang vùng chưa được duyệt.

### 12.3. Phương án và đánh đổi

| Phương án | Độ tin cậy / dữ liệu | Chi phí và vận hành | Rủi ro / nợ còn tồn |
| --- | --- | --- | --- |
| **P1: Giữ multi-AZ, cải thiện backup và DB** | Hợp lý cho lỗi AZ, chưa giải quyết triệt để mất cả region | Ít thay đổi hơn; chi phí có thể thấp hơn | R-12 khi region mất; D-11 có thể còn |
| **P2: Warm standby tại region được phê duyệt + IaC/DR** | Có tiềm năng đáp ứng phục hồi nếu replication/runbook được thử | Thêm replication, chi phí standby, vận hành liên vùng | A-12 phải xác nhận; R-12 cần diễn tập; dữ liệu có thể lệch |
| **P3: Active-active nhiều region** | Có thể giảm gián đoạn trong một số kịch bản | Phức tạp định tuyến, nhất quán, vận hành và chi phí cao | Split-brain, xung đột ghi, data residency, blast radius của phần chung |

Chưa có đủ bằng chứng để khẳng định một phương án **đạt ngưỡng**. Nhóm nên kiểm chứng A-12 và A-13, lập cost model, thử tải và mô phỏng kịch bản mất region. Sau đó mới phê duyệt ADR, ghi rủi ro còn lại và điều kiện rollback. Nếu mọi phương án đều không đáp ứng ngân sách và RTO/RPO, cần trình đúng người có quyền thay đổi phạm vi, ngân sách hoặc mục tiêu.

### 12.4. Kế hoạch hành động theo mốc

| Mốc | Kết quả phải có | Chủ sở hữu |
| --- | --- | --- |
| Trước chọn region dự phòng | Văn bản xác nhận vùng lưu dữ liệu và phân loại dữ liệu | Security/Legal |
| Trước chốt capacity | Load test, p95/p99, error rate, saturation và dự báo chi phí | SRE + Backend |
| Trước cam kết RTO/RPO | Kết quả diễn tập loss-of-region, restore và đối soát dữ liệu | SRE + Data |
| Trước mở chiến dịch | Kiểm thử idempotency Payment, retry, callback trễ, fault injection | Payment |
| Trong tháng đầu chạy thực tế | So sánh A-11 với traffic và cost thực, theo dõi R-11/D-11 | Product + SRE |
| Khi trigger D-11 xuất hiện | Tách read model hoặc điều chỉnh query/DB theo ADR cập nhật | Data + Architecture |

Kế hoạch này cho phép giảm bất định lớn **trước** khi cam kết với khách hàng, đồng thời theo dõi khoản nợ chưa cần sửa ngay bằng dấu hiệu đo cụ thể.

## 13. Mẫu tài liệu tối thiểu áp dụng được

Một hệ thống tài liệu nhỏ, dễ duy trì nên có các bảng hoặc công cụ quản lý tương ứng. Không cần triển khai nền tảng quản trị mới chỉ để quản lý vài chục mục; quan trọng là quyền sở hữu và khả năng truy vết.

### 13.1. Mẫu Assumption Record

~~~yaml
id: A-11
title: "Tải đỉnh không vượt 800 req/s"
scope: "Booking API, 3 tháng đầu sau ra mắt"
owner: "SRE lead"
confidence: medium
evidence: "Dự báo Product và số liệu thử nghiệm"
if_false: "Cần điều chỉnh capacity/API/DB và cost model"
validation:
  method: "Load test + telemetry tại production"
  due: "Trước chốt thiết kế capacity"
  success_criteria: "Kịch bản đo được phê duyệt"
links:
  - REQ-PERF-01
  - R-11
  - ADR-014
status: validating
~~~

Đây là **mẫu minh họa tài liệu**, không phải schema cấu hình bắt buộc trong repository. Tiêu chí thành công cần được làm cụ thể trong dự án; chẳng hạn mức throughput, p95, thời gian chạy và điều kiện dataset.

### 13.2. Mẫu Risk Record

~~~yaml
id: R-12
title: "Không đạt RTO/RPO khi mất region chính"
cause: "Chưa diễn tập restore/failover và kiểm chứng replica lag"
event: "Sự cố mất region hoặc backup không thể restore đúng hạn"
consequence: "Dịch vụ ngừng lâu hơn cam kết hoặc mất dữ liệu"
owner: "SRE lead"
likelihood: "Cần đánh giá qua diễn tập"
impact: high
response: "Diễn tập DR, kiểm tra backup, IaC và runbook"
evidence: "TEST-DR-05"
residual_risk: "Chờ kết quả diễn tập"
acceptance_owner: "Business/SRE theo quy trình phê duyệt"
trigger: "DR test lỗi, SLO bị vi phạm hoặc region thay đổi"
links:
  - A-13
  - D-12
  - ADR-014
status: open
~~~

### 13.3. Mẫu Debt Record

~~~yaml
id: D-11
title: "Reporting và Booking cùng phụ thuộc DB chính"
owner: "Data lead"
origin: "ADR-005 - giới hạn thời gian ra mắt"
impact:
  reliability: "Report query có thể làm p95 checkout tăng"
  delivery: "Migration phụ thuộc lịch release hai nhóm"
evidence:
  - "Dashboard p95 checkout và DB saturation"
candidate_remediation:
  - "Read model cho Reporting"
  - "Tách xử lý batch khỏi đường giao dịch"
estimate: "Cần spike để ước lượng"
trigger: "Report gây vi phạm SLO hoặc tạo release coupling"
review_date: "Kỳ rà soát kiến trúc tiếp theo"
links:
  - R-11
  - ADR-005
status: tracked
~~~

**Quy tắc chất lượng tài liệu:** nếu không xác định được **owner, bằng chứng và hành động/trigger**, bản ghi chỉ mới là ghi chú. Mẫu tốt hỗ trợ quyết định, không tự động thay thế giao tiếp giữa các bên.

## 14. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi giả định là sự thật kiến trúc | Chọn region/capacity sai nhưng không ai biết nguồn | Ghi assumption ID, mức tin cậy, hạn kiểm chứng |
| Để sơ đồ thiếu trạng thái as-is/to-be | Các team xây theo thiết kế chưa được triển khai | Ghi phiên bản, owner, ngày, phạm vi và liên kết ADR |
| Chấm rủi ro bằng một con số rồi đóng | Chưa biết residual risk và bằng chứng kiểm soát | Ghi nguyên nhân, hậu quả, mitigation, owner, phép thử |
| Đánh đồng backup tồn tại với DR đã đạt | Không đạt RTO/RPO khi sự cố | Diễn tập restore/failover và đối soát dữ liệu |
| Dùng điểm ưu tiên để bỏ qua compliance | Vi phạm điều kiện bắt buộc | Ràng buộc phải được xác minh và áp dụng trước chấm điểm |
| Xem mọi monolith là nợ | Tách dịch vụ quá sớm, tăng vận hành | Đánh giá tác động thực và yêu cầu đổi mới |
| Mọi rủi ro đều “accepted” | Không ai chịu trách nhiệm và không có ngưỡng | Chỉ người có thẩm quyền được chấp nhận rủi ro có thời hạn |
| Debt register chỉ là danh sách mong ước | Không có căn cứ ưu tiên | Đo interest, principal, trigger và owner |
| ADR ghi quyết định nhưng không ghi giả định | Không biết lúc nào phải xem xét lại | Liên kết assumption/risk/debt/test và mốc review |
| Chỉ cập nhật tài liệu khi audit | Sơ đồ và runbook lệch production | Kích hoạt cập nhật theo incident, deploy và thay đổi lớn |
| Giả định mọi rủi ro là độc lập | Đánh giá thấp lỗi cùng vùng/account/control plane | Phân tích dependency, common-cause failure, blast radius |
| Chỉ theo dõi số mục đã đóng | Che giấu rủi ro thực còn tồn | Đo SLO, DR, lỗi dữ liệu, chi phí và residual risk |

## 15. Bài tập thực hành

Một ứng dụng SaaS đặt chỗ dùng cloud trong một region, dự định mở rộng gấp năm lần lưu lượng và phục vụ khách hàng doanh nghiệp ở khu vực mới. Product muốn phát hành sau tám tuần; SRE yêu cầu khả năng khôi phục trong một giờ; Finance đề nghị chi phí tháng không tăng quá 30%; Security yêu cầu chứng minh dữ liệu nhạy cảm được lưu/replicate đúng phạm vi cho phép. Hiện Booking và Reporting dùng chung DB, chưa có distributed tracing đầy đủ.

**Yêu cầu thực hiện:**

1. Viết **năm giả định** có nguồn, mức tin cậy, hậu quả nếu sai, người chịu trách nhiệm và phép thử. Chỉ ra giả định nào cần xác nhận trước khi chọn region.
2. Xây **risk register ít nhất năm mục**, viết theo mẫu nguyên nhân → sự kiện → hậu quả; có likelihood/impact và biện pháp.
3. Xác định **ba khoản nợ kiến trúc** thực sự có tác động; nêu principal, interest, dữ liệu đo và điều kiện trả nợ.
4. Vẽ **sơ đồ triển khai as-is** với ứng dụng, DB, mạng, backup và đối tác ngoài; ghi assumption/risk/debt ID lên thành phần liên quan.
5. Đề xuất **hai phương án to-be** khác nhau về tính sẵn sàng, dữ liệu và TCO; chỉ rõ hạn chế chưa được kiểm chứng.
6. Viết **ADR** nêu quyết định có điều kiện, các giả định quan trọng, rủi ro còn lại, kế hoạch kiểm chứng và điều kiện xem xét lại.
7. Thiết kế **ba phép thử có tiêu chí nghiệm thu**: load test, restore/failover và kiểm tra bảo mật luồng dữ liệu. Nêu ai ký xác nhận kết quả.
8. Lập kế hoạch **một chu kỳ review tiếp theo**, gắn với ngưỡng SLO, chi phí, dữ liệu và tiến độ xử lý nợ.

**Gợi ý tự đánh giá:** câu trả lời chất lượng không cần tạo nhiều hồ sơ nhất; nó phải chỉ ra được điều gì đã biết, điều gì chưa chắc, tác động lên yêu cầu, người có quyền quyết định, bằng chứng cần thu thập và hành động cụ thể trước khi phát hành.

## 16. Checklist rà soát thiết kế

- [ ] Mọi quyết định quan trọng có ADR, owner, phương án thay thế và lý do lựa chọn.
- [ ] Sơ đồ có ngày, phạm vi, trạng thái as-is/to-be và liên kết yêu cầu.
- [ ] Giả định ảnh hưởng lớn có ID, nguồn, mức tin cậy, cách kiểm chứng và hạn.
- [ ] Giả định bị bác bỏ có đường truy vết tới ADR, sơ đồ, test và rủi ro liên quan.
- [ ] Risk register ghi nguyên nhân, sự kiện, hậu quả, owner, biện pháp và residual risk.
- [ ] Không có rủi ro bắt buộc tuân thủ bị chấp nhận tùy tiện hoặc thiếu phê duyệt.
- [ ] Đã xem xét lỗi chung của region/AZ, dependency, IAM, dữ liệu và control plane.
- [ ] Debt register ghi interest, principal, bằng chứng, trigger và phương án xử lý.
- [ ] Có SLI/SLO, capacity test, fault injection, backup validation và diễn tập DR phù hợp.
- [ ] Cost model bao gồm compute, data, network, egress, replication, quan sát và vận hành.
- [ ] Có người phê duyệt và lịch rà soát theo thời gian hoặc thay đổi trọng yếu.
- [ ] Các thay đổi production cập nhật được sơ đồ, runbook, ADR và danh mục rủi ro liên quan.

## Ghi nhớ

**Giả định** là điều cần kiểm chứng; **rủi ro** là sự kiện có thể gây tổn thất; **nợ kiến trúc** là chi phí hoặc giới hạn tích lũy từ cấu trúc thiết kế. Chúng liên quan chặt chẽ nhưng phải được ghi nhận, ưu tiên và xử lý theo cách phù hợp với bản chất từng đối tượng.

Một kiến trúc cloud có thể được vận hành và cải tiến lâu dài khi người kế nhiệm truy vết được **yêu cầu → giả định → quyết định/ADR → sơ đồ → phép thử → rủi ro còn lại → kế hoạch xử lý nợ**. Giá trị của việc quản lý này nằm ở các quyết định được kiểm chứng bằng dữ liệu về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**, chứ không nằm ở số lượng biểu mẫu đã điền.
