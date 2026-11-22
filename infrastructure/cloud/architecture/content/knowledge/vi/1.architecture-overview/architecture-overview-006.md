# Lộ trình thiết kế và đánh giá kiến trúc đám mây

Thiết kế kiến trúc đám mây là quá trình chuyển **mục tiêu nghiệp vụ và các ràng buộc** thành một hệ thống có thể triển khai, đo lường, vận hành và cải tiến. Công việc không bắt đầu bằng câu hỏi “nên dùng Kubernetes hay serverless?”, mà bắt đầu bằng câu hỏi “hệ thống phải phục vụ ai, đáp ứng mức chất lượng nào và chúng ta chấp nhận những đánh đổi gì?”.

Một kiến trúc tốt không nhất thiết có nhiều dịch vụ. Nó lựa chọn đúng mức độ phức tạp để đạt yêu cầu về **độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí và vận hành**. Việc đánh giá kiến trúc theo tư duy *Well-Architected* giúp biến các lựa chọn đó thành những giả định có thể kiểm chứng và các rủi ro có thể xử lý.

Sau bài học, bạn có thể:

- Đi từ yêu cầu nghiệp vụ đến sơ đồ kiến trúc tổng thể, mạng, compute, dữ liệu và mô hình triển khai.
- Chuyển các phát biểu mơ hồ như “hệ thống phải nhanh, ổn định” thành mục tiêu đo được.
- Chọn giữa các phương án phổ biến dựa trên đặc tính tải, năng lực đội ngũ và tổng chi phí.
- Thiết kế đường đi của yêu cầu, dữ liệu, quyền truy cập và kịch bản xảy ra sự cố.
- Thực hiện một vòng đánh giá Well-Architected có bằng chứng, mức ưu tiên và kế hoạch cải thiện.

## 1. Nhìn toàn cảnh: các chặng của một quyết định kiến trúc

Một lộ trình thực tế có thể chia thành chín chặng. Thứ tự này giúp giảm việc chọn công nghệ quá sớm; trong dự án thực tế, các chặng có thể lặp lại khi xuất hiện dữ liệu mới.

| Chặng | Câu hỏi trọng tâm | Sản phẩm đầu ra có thể kiểm tra |
| --- | --- | --- |
| 1. Hiểu nghiệp vụ | Ai sử dụng, luồng nghiệp vụ nào quan trọng, điều gì tạo ra giá trị? | Phạm vi, sơ đồ ngữ cảnh, luồng sử dụng chính |
| 2. Lượng hóa chất lượng | Bao nhiêu người dùng, nhanh và sẵn sàng đến mức nào? | SLI/SLO, RTO/RPO, dự báo tải, ràng buộc |
| 3. Nhận diện dữ liệu và rủi ro | Dữ liệu gì, đi qua đâu, ai được truy cập? | Phân loại dữ liệu, luồng dữ liệu, ranh giới tin cậy |
| 4. Chọn cấu trúc ứng dụng | Khối nào cần tách, giao tiếp ra sao? | Sơ đồ thành phần, quyết định kiến trúc (ADR) |
| 5. Thiết kế hạ tầng | Mạng, compute, lưu trữ và database được đặt ở đâu? | Sơ đồ triển khai, lựa chọn dịch vụ, thiết kế mạng |
| 6. Thiết kế cho lỗi và tăng trưởng | Khi một thành phần hỏng hoặc tải tăng thì sao? | Phương án HA, mở rộng, backup, DR, thử nghiệm |
| 7. Thiết kế vận hành và chi phí | Làm sao phát hành, giám sát, ứng cứu và kiểm soát tiền? | IaC, CI/CD, runbook, dashboard, ước tính chi phí |
| 8. Đánh giá Well-Architected | Kiến trúc đang có rủi ro nào và có bằng chứng gì? | Danh sách phát hiện, mức ưu tiên, người phụ trách |
| 9. Kiểm chứng và cải tiến | Hệ thống thực tế có đáp ứng các giả định không? | PoC, kết quả đo, quyết định điều chỉnh, lịch đánh giá lại |

Đừng coi sơ đồ kiến trúc là kết quả cuối cùng. Một sơ đồ chỉ mô tả *các thành phần*; một thiết kế đầy đủ còn phải chỉ ra **lý do chọn**, **giới hạn**, **cách phát hiện lỗi** và **cách phục hồi**.

## 2. Chặng 1: xuất phát từ nhu cầu nghiệp vụ

Trước khi chọn nhà cung cấp cloud, hãy xác định:

1. **Người dùng và hành trình chính:** Ai truy cập hệ thống? Đâu là thao tác cần bảo vệ trước tiên: tìm kiếm, đăng nhập, đặt hàng hay thanh toán?
2. **Phạm vi và hệ thống phụ thuộc:** Thành phần nào do đội ngũ sở hữu? Có cổng thanh toán, hệ thống nhận diện, dịch vụ email hoặc hệ thống tại chỗ cần tích hợp không?
3. **Thời gian và ngân sách:** Khi nào cần ra mắt? Đội phát triển có bao nhiêu người, kỹ năng vận hành ra sao? Mức chi tiêu tối đa là bao nhiêu?
4. **Ràng buộc:** Có quy định về vùng lưu dữ liệu, thời gian lưu giữ, chứng cứ kiểm toán, hợp đồng và nhà cung cấp hiện hữu không?
5. **Mức độ thay đổi:** Sản phẩm còn thử nghiệm hay đã có tải ổn định? Có tính năng nào cần triển khai độc lập thường xuyên không?

**Ví dụ xuyên suốt:** một ứng dụng đặt lịch dịch vụ có khách hàng tạo lịch hẹn, nhân viên xử lý lịch và hệ thống gửi thông báo. Nhóm dự kiến 50.000 người dùng hoạt động hằng ngày; lưu lượng đỉnh khoảng 200 yêu cầu/giây; giờ cao điểm tập trung vào tìm kiếm và đặt lịch. Các con số này là **giả định để học và tính toán**, chưa phải dữ liệu đo từ sản phẩm thật.

Các luồng nghiệp vụ cần ưu tiên là:

- Khách hàng xem lịch trống và đặt lịch; không được tạo hai lịch trùng cho cùng một khung giờ.
- Nhân viên cập nhật trạng thái lịch; các thay đổi phải được lưu bền vững.
- Thông báo có thể gửi chậm trong thời gian ngắn, nhưng không được làm thất bại giao dịch đặt lịch.
- Quản trị viên xem nhật ký thao tác và xử lý khiếu nại.

Từ đó xuất hiện quyết định đầu tiên: **đặt lịch** là luồng cần tính nhất quán mạnh tại điểm ghi; **gửi thông báo** có thể tách khỏi luồng đồng bộ bằng hàng đợi. Đây là quyết định xuất phát từ nghiệp vụ, chưa phụ thuộc dịch vụ cloud cụ thể.

## 3. Chặng 2: chuyển kỳ vọng chất lượng thành mục tiêu đo được

Các yêu cầu “nhanh”, “an toàn” và “không downtime” không đủ để thiết kế hay nghiệm thu. Hãy gắn mỗi yêu cầu với đối tượng đo, ngưỡng, điều kiện đo và người chịu trách nhiệm.

| Thuộc tính | Mục tiêu minh họa | Hàm ý thiết kế |
| --- | --- | --- |
| Độ sẵn sàng | 99,9% yêu cầu đặt lịch hợp lệ thành công trong tháng, loại trừ lỗi do khách hàng nhập sai | Tránh một điểm lỗi duy nhất; đo theo hành trình nghiệp vụ |
| Độ trễ | 95% yêu cầu đọc lịch hoàn tất dưới 300 ms tại phía dịch vụ trong điều kiện tải dự kiến | Đo p95, tối ưu truy vấn, cân nhắc cache |
| Thông lượng | Chịu 200 yêu cầu/giây lúc cao điểm và tăng gấp đôi trong đợt khuyến mại | Thử tải, giới hạn và mở rộng có kiểm soát |
| Khôi phục | RTO tối đa 60 phút, RPO tối đa 15 phút với dữ liệu đặt lịch | Phương án khôi phục và lịch sao lưu/replication phù hợp |
| Bảo mật | Chỉ nhân viên được phân quyền mới xem dữ liệu khách hàng; ghi nhận truy cập nhạy cảm | IAM, xác thực, ủy quyền và audit log |
| Chi phí | Chi tiêu vận hành hằng tháng nằm trong ngân sách được duyệt ở tải cơ sở | Gắn nhãn chi phí, cảnh báo ngân sách và dự phòng |
| Khả năng vận hành | Có cảnh báo khi tỷ lệ lỗi vượt ngưỡng; có quy trình rollback | Observability, CI/CD, runbook và trực sự cố |

Hai khái niệm cần phân biệt:

- **SLI (Service Level Indicator):** phép đo thực tế, chẳng hạn tỷ lệ yêu cầu đặt lịch thành công hoặc độ trễ p95.
- **SLO (Service Level Objective):** mục tiêu áp cho SLI trong một khoảng thời gian, chẳng hạn 99,9% mỗi 30 ngày. Một SLO về tỷ lệ thành công 99,9% tương đương ngân sách lỗi 0,1% lượng yêu cầu đủ điều kiện; nó không tự động tương đương đúng 43,2 phút downtime nếu cách đo là theo yêu cầu. Với chỉ tiêu *uptime theo thời gian*, 99,9% trong 30 ngày tương đương tối đa khoảng 43,2 phút không sẵn sàng.

**RTO** là thời gian tối đa chấp nhận để khôi phục dịch vụ sau sự cố; **RPO** là lượng dữ liệu tối đa có thể mất, biểu diễn theo thời gian. Sao lưu hằng ngày không thể tự nó chứng minh đáp ứng RPO 15 phút. Có bản sao dự phòng cũng chưa chứng minh được RTO 60 phút nếu chưa diễn tập khôi phục.

Ghi rõ nguồn gốc từng mục tiêu: cam kết hợp đồng, yêu cầu tuân thủ, phân tích tác động nghiệp vụ hoặc giả định cần xác minh. Tránh chọn mức “năm số 9” khi nghiệp vụ không cần và nguồn lực không đủ, vì yêu cầu sẵn sàng càng cao thường kéo theo độ phức tạp và chi phí lớn hơn.

## 4. Chặng 3: phân tích tải, dữ liệu và ranh giới tin cậy

### 4.1. Ước lượng tải trước khi chọn kích thước

Thu thập ít nhất lưu lượng trung bình, lưu lượng đỉnh, tỷ lệ đọc/ghi, kích thước payload, độ lớn dữ liệu, mức tăng trưởng và đặc điểm mùa vụ. Kiểm tra các đỉnh đột ngột do sự kiện thay vì suy từ số người dùng đăng ký.

Ví dụ, với 200 yêu cầu/giây và thời gian xử lý trung bình **0,2 giây** ở một thành phần, định luật Little cho ước lượng sơ bộ khoảng:

~~~text
Số yêu cầu đồng thời trung bình ≈ tốc độ đến × thời gian xử lý trung bình
                               = 200 yêu cầu/giây × 0,2 giây
                               = 40 yêu cầu
~~~

Con số 40 chỉ mô tả số yêu cầu đang xử lý trung bình tại giả định trên. Nó **không phải** số container cần triển khai: còn phải đo CPU, bộ nhớ, I/O, contention, thời gian hàng đợi, giới hạn kết nối, mức tải an toàn và khả năng dự phòng. Kết quả sizing cuối cùng cần được kiểm chứng bằng load test.

### 4.2. Phân loại dữ liệu trước khi chọn storage

Với mỗi tập dữ liệu, xác định **độ nhạy cảm**, **nguồn dữ liệu chuẩn**, **mức nhất quán**, **thời gian lưu**, **quyền truy cập**, **khả năng phục hồi** và **vùng địa lý cho phép**.

| Nhóm dữ liệu | Đặc tính chính | Lựa chọn thường phù hợp |
| --- | --- | --- |
| Lịch hẹn, thanh toán, quyền sở hữu | Giao dịch và ràng buộc nhất quán | Cơ sở dữ liệu quan hệ được quản lý, transaction và constraint |
| Ảnh, tệp đính kèm | Đối tượng lớn, truy cập qua URL hoặc API | Object storage với chính sách truy cập và vòng đời |
| Phiên hoặc kết quả tìm kiếm có thể tái tạo | Truy cập nhanh, chấp nhận làm mới | Cache có TTL và chiến lược vô hiệu hóa |
| Sự kiện gửi thông báo | Xử lý bất đồng bộ, có thể retry | Queue/event service và worker |
| Metric, trace, log | Quan sát và điều tra sự cố | Dịch vụ quan sát với chính sách retention |

Không sao chép dữ liệu cá nhân vào log, trace, cache hoặc môi trường thử nghiệm nếu không có nhu cầu và biện pháp bảo vệ phù hợp. Một luồng dữ liệu chỉ “nằm trong cloud” vẫn có thể băng qua nhiều vùng tin cậy: người dùng Internet, dịch vụ ứng dụng, cơ sở dữ liệu, đối tác thứ ba và đội vận hành.

## 5. Chặng 4: chọn cấu trúc ứng dụng theo mức cần thiết

Trước khi chia microservice, hãy tìm các ranh giới nghiệp vụ và đánh giá cách nhóm phối hợp:

- **Monolith có cấu trúc (modular monolith):** thích hợp khi nhóm nhỏ, miền nghiệp vụ còn thay đổi, cần giao dịch nội bộ đơn giản. Vẫn tách module rõ ràng để giảm phụ thuộc.
- **Microservices:** phù hợp khi các miền có vòng đời triển khai, quy mô hoặc quyền sở hữu độc lập rõ rệt; đổi lại cần quản lý giao tiếp mạng, dữ liệu phân tán, quan sát và xử lý lỗi.
- **Kiến trúc hướng sự kiện:** phù hợp với tác vụ có thể xử lý sau, nhiều bên quan tâm đến sự kiện hoặc cần hấp thụ các đợt tải; đổi lại cần xử lý trùng lặp, thứ tự, retry và nhất quán cuối cùng.

Không cần chọn một nhãn duy nhất cho toàn hệ thống. Ví dụ đặt lịch có thể bắt đầu bằng **một ứng dụng chia module**, database quan hệ và một worker thông báo. Khi nhu cầu mở rộng hoặc tổ chức thay đổi, mới tách các miền thật sự có lợi khi triển khai độc lập.

### Lựa chọn compute

| Lựa chọn | Điểm mạnh | Chi phí và giới hạn cần cân nhắc |
| --- | --- | --- |
| Máy ảo (VM) | Kiểm soát hệ điều hành và runtime tốt, hỗ trợ workload đặc thù | Tự quản bản vá, hệ điều hành, autoscaling và dung lượng |
| Container trên dịch vụ được quản lý | Đóng gói nhất quán, triển khai thuận tiện, phù hợp API/worker | Phải thiết kế image, mạng, tài nguyên và health check |
| Kubernetes | Điều phối linh hoạt cho nhiều workload và tổ chức có năng lực nền tảng | Độ phức tạp vận hành, bảo mật và chi phí quản trị cao |
| Function/serverless | Tự động co giãn theo sự kiện, hữu ích cho tác vụ ngắn hoặc lưu lượng biến động | Giới hạn thời gian, cold start, kết nối, quota và cách tính phí |
| PaaS/managed application platform | Đẩy nhanh triển khai, giảm việc quản trị hạ tầng | Ít kiểm soát sâu hơn, phụ thuộc khả năng nền tảng |

Quyết định dựa trên **mức độ chủ động cần có**, **kiểu tải**, **trạng thái ứng dụng**, **độ nhạy độ trễ**, **quy định** và **khả năng vận hành**. Tên dịch vụ khác nhau giữa AWS, Azure và Google Cloud, nhưng nguyên tắc đánh đổi tương tự nhau.

### Đồng bộ và bất đồng bộ

Giữ trên đường xử lý đồng bộ những việc cần kết quả ngay để trả lời người dùng, chẳng hạn xác nhận đặt lịch và ghi transaction. Các việc như gửi email/SMS có thể đi qua queue để giảm độ trễ và cô lập lỗi nhà cung cấp thông báo.

Khi dùng queue, cần thiết kế **idempotency**: xử lý lại cùng một thông điệp không được tạo tác dụng phụ sai. Hệ thống phân phối thông điệp thường có thể giao lại thông điệp; không nên mặc định mỗi thông điệp được xử lý đúng một lần. Cần có retry với backoff, dead-letter queue, chính sách thời gian giữ, cảnh báo tồn đọng và cách phát lại an toàn. Nếu phải đảm bảo sự kiện được phát sau khi giao dịch database commit, cân nhắc mẫu **transactional outbox**.

## 6. Chặng 5: ghép các khối mạng, compute, dữ liệu và triển khai

Sơ đồ minh họa sau là một phương án khởi đầu cho ứng dụng đặt lịch. Các thành phần và đường nối thể hiện trách nhiệm logic; cách hiện thực cụ thể phải phù hợp dịch vụ được chọn.

~~~mermaid
flowchart TD
    U[Khách hàng và nhân viên] --> EDGE[DNS, TLS, CDN/WAF nếu cần]
    EDGE --> LB[Load balancer công khai]
    subgraph NET[Virtual network trong một region]
        LB --> APP[Ứng dụng stateless ở tối thiểu 2 availability zone]
        APP --> DB[(Managed relational database HA)]
        APP --> Q[Managed queue]
        Q --> W[Worker xử lý thông báo]
    end
    APP --> OBJ[(Object storage riêng tư)]
    APP --> OBS[Log, metric, trace]
    W --> OBS
    W --> EXT[Nhà cung cấp email/SMS]
    DB --> BAK[Backup và kiểm tra khôi phục]
~~~

Sơ đồ này cần được diễn giải theo bốn lớp:

**Lớp mạng và truy cập.** Thiết kế virtual network/VPC/VNet, phân đoạn subnet, route, ingress/egress, DNS và TLS. Chỉ đặt điểm vào bắt buộc ở lớp công khai; tầng ứng dụng và database nên ở mạng riêng khi giải pháp cho phép. Kiểm soát cổng, nguồn và đích bằng firewall/security group/ACL thích hợp. Kết nối ra Internet từ subnet riêng phải có đường egress hợp lệ, ví dụ NAT hoặc private endpoint tới dịch vụ hỗ trợ; một subnet “private” không tự động có đường đến mọi dịch vụ. Không đưa database trực tiếp lên Internet chỉ để tiện kết nối.

**Lớp compute.** Các bản sao ứng dụng nên stateless hoặc quản lý phiên ngoài tiến trình, có readiness/liveness check, timeout, giới hạn tài nguyên và cơ chế phát hành có rollback. Khi triển khai qua nhiều availability zone, phải kiểm chứng cả đường đi mạng, tải cân bằng và nơi lưu trạng thái đều chịu được sự cố một zone. Hai instance trong cùng một zone chưa tương đương với kiến trúc chịu lỗi một zone.

**Lớp dữ liệu.** Database quan hệ được quản lý phù hợp cho thao tác đặt lịch cần transaction và constraint tránh double booking. Thiết lập index, connection pooling, sao lưu, mã hóa, chính sách retention và cơ chế failover. Bản sao đọc có thể tăng năng lực truy vấn nhưng có thể trễ so với bản chính; đừng sử dụng replica cho bước xác nhận chỗ trống đòi hỏi nhất quán mà không kiểm chứng. Cache hữu ích khi xác định được chiến lược invalidation và giới hạn dữ liệu cũ.

**Lớp triển khai.** Tách môi trường dev/test/prod, dùng tài khoản/project/subscription hoặc ranh giới phân quyền phù hợp. Mô tả hạ tầng bằng **Infrastructure as Code (IaC)**, lưu phiên bản cấu hình, hạn chế thay đổi thủ công, và có pipeline kiểm tra trước khi phát hành. Secrets đặt trong hệ thống quản lý bí mật, không nằm trong mã nguồn hay image.

### Một số lựa chọn dữ liệu điển hình

| Câu hỏi | Gợi ý ra quyết định |
| --- | --- |
| Giao dịch có nhiều ràng buộc quan hệ và cần tính nhất quán mạnh? | Ưu tiên đánh giá relational database có transaction |
| Cần key-value truy cập lớn, schema linh hoạt, có thể chấp nhận mô hình nhất quán riêng? | Đánh giá NoSQL theo chính access pattern và khả năng transaction |
| Cần lưu tệp, ảnh, backup dài hạn? | Object storage, lifecycle policy, versioning/retention theo nhu cầu |
| Đọc lặp lại nhiều và có thể chấp nhận dữ liệu cũ một khoảng ngắn? | Cache kèm TTL, invalidation, giới hạn bộ nhớ |
| Tác vụ mất thời gian hoặc phụ thuộc đối tác bên ngoài? | Queue/event với retry, timeout, idempotency và DLQ |

Không dùng NoSQL chỉ vì “có thể scale”, cũng không dùng cache như dữ liệu chuẩn cho giao dịch. Sự phù hợp phụ thuộc mô hình truy cập, tính nhất quán, yêu cầu báo cáo và cách phục hồi.

## 7. Chặng 6: thiết kế trước cho lỗi, tăng tải và sự cố bảo mật

### 7.1. Phân biệt HA, backup và DR

- **High availability (HA):** hạn chế gián đoạn khi một thành phần hoặc miền lỗi gặp sự cố; ví dụ nhiều bản sao ứng dụng ở các zone khác nhau với health check và database có failover.
- **Backup:** lưu bản sao dữ liệu có thể phục hồi sau xóa nhầm, hỏng dữ liệu hoặc sự cố khác. Replication liên tục không thay thế backup: lỗi logic có thể được sao chép sang replica.
- **Disaster recovery (DR):** kế hoạch khôi phục sau sự cố vượt phạm vi HA, chẳng hạn mất cả region. DR có các chiến lược khác nhau, từ khôi phục từ backup đến hot standby ở region khác, và phải được lựa chọn theo RTO/RPO thực tế.

Thiết kế multi-region có thể giảm một số rủi ro nhưng làm tăng chi phí, độ trễ, độ phức tạp dữ liệu và vận hành; không phải mặc định bắt buộc cho mọi ứng dụng. Một kiến trúc multi-AZ chỉ giải quyết các tình huống trong phạm vi được cấu hình, không tự bảo đảm sống sót qua sự cố toàn region.

### 7.2. Chống lỗi dây chuyền

Khi một dịch vụ phụ thuộc chậm hoặc hỏng, hệ thống cần **timeout rõ ràng**, retry có giới hạn và backoff/jitter, circuit breaker hoặc giới hạn đồng thời khi phù hợp. Retry bừa bãi có thể nhân tải lên hệ thống đang quá tải. Tác vụ nền cần queue có backpressure; thao tác quan trọng cần idempotency key để chống tạo trùng khi người dùng gửi lại yêu cầu.

Kiểm thử các kịch bản: một instance chết; một zone không khả dụng; database failover; dịch vụ gửi email timeout; queue đầy; phát hành lỗi; backup cần restore; tài khoản truy cập bị thu hồi. Ghi nhận **thời gian phát hiện**, **thời gian khôi phục**, **mức mất dữ liệu thực tế** và những bước thủ công còn tồn tại.

### 7.3. Bảo mật theo các ranh giới tin cậy

Thiết kế bảo mật cần trải suốt đường đi dữ liệu, không chỉ có một lớp WAF:

1. Xác thực danh tính người dùng và dịch vụ; phân quyền ở từng API theo tài nguyên và vai trò.
2. Cấp quyền tối thiểu cho workload và người vận hành; phân tách vai trò triển khai, quản trị và đọc dữ liệu.
3. Mã hóa dữ liệu khi truyền bằng TLS; mã hóa khi lưu với quản trị khóa thích hợp và chính sách vòng đời.
4. Quản lý secrets tập trung, xoay vòng khi cần, không ghi token hoặc dữ liệu nhạy cảm vào log.
5. Kiểm tra image/thư viện, quản lý bản vá, rà soát cấu hình và theo dõi audit log.
6. Phân tích các đường tấn công quan trọng: lộ credential, sai cấu hình public storage, lạm dụng API, thay đổi dữ liệu trái phép, thất thoát backup.

Áp dụng mô hình **trách nhiệm chia sẻ** của cloud: nhà cung cấp quản lý một phần hạ tầng tùy loại dịch vụ; khách hàng vẫn phải chịu trách nhiệm thích hợp về cấu hình, danh tính, dữ liệu, quyền truy cập và bảo vệ ứng dụng. Dùng dịch vụ “managed” không đồng nghĩa hệ thống mặc nhiên an toàn.

## 8. Chặng 7: thiết kế vận hành và chi phí ngay từ đầu

Một phương án chạy được trong ngày demo nhưng không thể giám sát hoặc phục hồi sẽ khó đáp ứng SLO trong vận hành thật.

### Quan sát hệ thống

- **Metric:** request rate, error rate, latency p50/p95/p99, mức dùng CPU/RAM, connection pool, hàng đợi, tỷ lệ thất bại của worker và chỉ số nghiệp vụ như số lịch đặt thành công.
- **Log có cấu trúc:** timestamp, mức độ, tên dịch vụ, mã lỗi, correlation/request ID; che hoặc loại bỏ dữ liệu nhạy cảm.
- **Distributed tracing:** theo dõi hành trình qua API, database, queue và dịch vụ liên quan khi cần điều tra độ trễ.
- **Alert có hành động:** cảnh báo ưu tiên tín hiệu ảnh hưởng người dùng và ngân sách lỗi; liên kết tới dashboard, runbook và người trực. Cảnh báo CPU cao đơn lẻ chưa chắc tương ứng sự cố dịch vụ.

### Triển khai và ứng cứu

Thiết lập CI/CD với kiểm thử, quét bảo mật phù hợp, phê duyệt hoặc gate theo môi trường, triển khai từng phần (rolling/canary/blue-green tùy nền tảng), khả năng rollback và migration database tương thích ngược. Runbook cần nêu cách nhận biết triệu chứng, giảm tác động, chuyển quyền xử lý, khôi phục và làm postmortem.

### Tính tổng chi phí, không chỉ chi phí compute

Ước lượng cả compute, database, storage, IOPS, lưu lượng Internet và liên zone/region, load balancer/NAT, log/metric, backup, môi trường phi sản xuất, dịch vụ bên thứ ba và nhân công vận hành.

~~~text
Chi phí dự báo hằng tháng
  = compute + dữ liệu + mạng + quan sát + backup/DR
  + dịch vụ tích hợp + dự phòng theo biến động tải
~~~

Đây là mô hình phân loại chi phí, không phải công thức báo giá cloud. Giá thực phụ thuộc region, cấu hình, mức dùng, chính sách chiết khấu và cách tính phí từng dịch vụ. Nên ước tính ít nhất ba kịch bản: **tải cơ sở**, **cao điểm dự kiến** và **tăng trưởng vượt dự kiến**. Gắn tag/label cho môi trường và nhóm phụ trách; theo dõi chi phí trên mỗi giao dịch thành công khi có dữ liệu đáng tin cậy.

Một ví dụ đánh đổi: giữ hai instance ứng dụng luôn chạy có thể làm chi phí cơ sở cao hơn phương án co giãn mạnh, nhưng có thể phù hợp khi cần độ trễ ổn định và dự phòng một zone. Quyết định cuối phải dựa trên kết quả thử tải và mô hình chi phí, không dựa trên khẩu hiệu “serverless luôn rẻ” hay “VM luôn nhanh”.

## 9. Chặng 8: đánh giá kiến trúc theo Well-Architected

Well-Architected là khung câu hỏi và thực hành để xem xét workload một cách có hệ thống. Trong cách tiếp cận của AWS, khung này có **sáu trụ cột** dưới đây; các nền tảng khác có khung đánh giá tương tự nhưng thuật ngữ và dịch vụ hỗ trợ có thể khác.

| Trụ cột | Câu hỏi cần trả lời bằng bằng chứng | Dấu hiệu cần cải thiện |
| --- | --- | --- |
| Operational Excellence (vận hành xuất sắc) | Có runbook, CI/CD, rollback, review sự cố và thay đổi có kiểm soát? | Deploy thủ công, không biết ai xử lý cảnh báo |
| Security (bảo mật) | Quyền có tối thiểu, dữ liệu được bảo vệ, có audit và quản lý lỗ hổng? | Khóa nằm trong mã nguồn, tài nguyên public ngoài ý muốn |
| Reliability (độ tin cậy) | Đã kiểm thử lỗi thành phần, backup restore, failover, RTO/RPO? | Single point of failure, backup chưa từng restore |
| Performance Efficiency (hiệu năng) | Có đo tải, p95, bottleneck, quyết định sizing dựa trên dữ liệu? | Chọn cấu hình theo cảm tính, không có load test |
| Cost Optimization (tối ưu chi phí) | Có budget, quyền sở hữu chi phí, dự báo và phát hiện lãng phí? | Không biết tài nguyên nào làm hóa đơn tăng |
| Sustainability (bền vững) | Có giảm tài nguyên nhàn rỗi, tối ưu hiệu suất và vòng đời lưu dữ liệu? | Tài nguyên luôn bật dù không sử dụng, dữ liệu tồn tại vô hạn |

### Quy trình review có thể lặp lại

**Bước 1 — Chọn phạm vi workload.** Xác định hành trình nghiệp vụ cần đánh giá, môi trường, region, tập dữ liệu, phụ thuộc, SLO và người chịu trách nhiệm. Không đánh giá “toàn bộ công ty” bằng một câu trả lời chung chung.

**Bước 2 — Thu bằng chứng.** Dùng sơ đồ kiến trúc đang chạy, cấu hình IaC, kết quả đo, dashboard, kết quả restore/chaos test, log deploy, báo cáo quyền và chi phí. Phân biệt **đã triển khai**, **đã kiểm thử**, **mới dự định**.

**Bước 3 — Phỏng vấn theo sáu trụ cột.** Với mỗi câu hỏi, ghi câu trả lời, bằng chứng, độ không chắc chắn và hậu quả nếu giả định sai. Ví dụ “có backup tự động” là bằng chứng về việc *tạo* backup; để xác nhận khôi phục cần có kết quả restore và thời gian hoàn thành.

**Bước 4 — Xếp hạng rủi ro.** Ưu tiên theo tác động nghiệp vụ, khả năng xảy ra, mức phơi nhiễm và nỗ lực xử lý. Không dùng tổng điểm số duy nhất để che đi lỗi bảo mật hoặc rủi ro dữ liệu nghiêm trọng.

**Bước 5 — Tạo hành động có chủ sở hữu.** Mỗi phát hiện cần nêu hiện trạng, mục tiêu, phương án, người chịu trách nhiệm, thời hạn và cách nghiệm thu. Với rủi ro còn tồn tại do quyết định có chủ đích, ghi rõ người chấp nhận và thời điểm xem xét lại.

**Bước 6 — Đánh giá lại sau thay đổi.** Thực hiện review sau một thay đổi kiến trúc lớn, sự cố nghiêm trọng, thay đổi quy mô hoặc theo chu kỳ phù hợp; so sánh số liệu thực tế với mục tiêu ban đầu.

Ví dụ bảng ghi nhận phát hiện:

| Phát hiện | Bằng chứng | Tác động | Hành động ưu tiên | Tiêu chí hoàn tất |
| --- | --- | --- | --- | --- |
| Backup chưa thử restore | Có lịch backup, không có biên bản phục hồi | Có thể không đạt RTO/RPO | Diễn tập restore trong môi trường cô lập | Khôi phục dữ liệu đúng, đo RTO/RPO đạt mục tiêu |
| Ứng dụng chỉ chạy một zone | Sơ đồ triển khai và cấu hình | Zone lỗi có thể làm ngừng đặt lịch | Triển khai nhiều zone, kiểm thử chuyển tải | Ngắt một zone vẫn đáp ứng mức phục vụ đã thống nhất |
| Queue không có cảnh báo tồn đọng | Dashboard thiếu queue age và DLQ | Thông báo có thể trễ kéo dài | Bổ sung metric, alert và runbook | Cảnh báo hoạt động trong kiểm thử nghẽn queue |
| Không tách quyền triển khai production | Chính sách IAM hiện hành | Nguy cơ sửa/xóa ngoài ý muốn | Phân quyền tối thiểu và audit | Rà soát quyền, kiểm thử hành vi được/chưa được phép |

Khung review giúp **phát hiện và ưu tiên đánh đổi**, không phải chứng nhận rằng kiến trúc “không còn rủi ro”. Một workload nhỏ có thể chọn chấp nhận một số rủi ro có kiểm soát để tập trung vào giá trị nghiệp vụ, nhưng cần ghi nhận rõ.

## 10. Chặng 9: chứng minh kiến trúc bằng thực nghiệm

Khi bản thiết kế đã hình thành, thực hiện một **proof of concept (PoC)** hoặc lát cắt triển khai tối thiểu cho các giả định rủi ro cao nhất. Không cần dựng mọi thành phần cùng lúc; nên chọn thử nghiệm có thể đảo chiều quyết định kiến trúc.

Với ví dụ đặt lịch:

1. **Thử tải:** chạy luồng đọc lịch, tạo lịch và cập nhật trạng thái theo tải trung bình, đỉnh và tăng gấp đôi; đo p95, tỷ lệ lỗi, độ bão hòa database, chi phí ước tính.
2. **Thử tính đúng đắn:** cho nhiều yêu cầu cạnh tranh cùng khung giờ; kiểm tra constraint/transaction chặn double booking.
3. **Thử xử lý bất đồng bộ:** ngắt dịch vụ email, gửi lại thông điệp, gây lỗi worker; xác nhận không làm hỏng giao dịch và không phát thông báo trùng trái ý muốn.
4. **Thử chịu lỗi:** dừng một instance/zone giả lập trong phạm vi cho phép; đo thời gian phát hiện, chuyển tải và tác động lên SLO.
5. **Thử phục hồi:** khôi phục database từ backup/PITR theo giải pháp thực tế; ghi nhận lượng dữ liệu mất và thời gian khôi phục so với RPO/RTO.
6. **Thử bảo mật:** kiểm tra truy cập chéo tài khoản, quyền workload, bí mật, cấu hình public và khả năng truy vết thao tác.
7. **Thử rollback:** phát hành thay đổi có kiểm soát rồi quay lại bản an toàn, kể cả thay đổi schema có kế hoạch tương thích.

Ghi kết quả theo định dạng **giả định → phép thử → số đo → kết luận → quyết định**. Nếu chưa đạt, thay đổi giả định hoặc thiết kế rồi đo lại. Ví dụ, p95 vượt ngưỡng có thể do truy vấn và index trước khi do thiếu số lượng instance; tăng compute không phải lúc nào cũng giải quyết đúng nguyên nhân.

### Mẫu Architecture Decision Record (ADR)

ADR lưu bối cảnh và lý do chọn giải pháp để người đến sau hiểu sự đánh đổi:

~~~yaml
id: ADR-001
title: Su dung managed relational database cho lich hen
status: accepted
context:
  - Can tranh dat trung khung gio
  - Doi van hanh nho, can backup va failover co kiem soat
decision: Chon managed relational database co transaction va unique constraint
alternatives:
  - Tu quan ly database tren VM
  - NoSQL ket hop co che kiem soat xung dot
consequences:
  positive: Giam cong van hanh, giao dich ro rang
  tradeoff: Chi phi co so va phu thuoc vao dich vu managed
validation: Kiem thu concurrent booking, failover, restore va load test
review_when: Khi tai ghi tang manh hoac yeu cau du lieu thay doi
~~~

Đây là **mẫu tài liệu quyết định**, không phải cấu hình triển khai. Việc chọn managed database chỉ có ý nghĩa khi kiểm thử xác nhận phù hợp với transaction, hiệu năng và yêu cầu phục hồi cụ thể.

## 11. Bộ hồ sơ kiến trúc tối thiểu trước khi triển khai production

Một thiết kế có thể được bàn giao và review khi tối thiểu trả lời được các nhóm câu hỏi sau:

| Tài liệu / bằng chứng | Nội dung cần có |
| --- | --- |
| Sơ đồ ngữ cảnh và luồng dữ liệu | Actor, phụ thuộc ngoài, dữ liệu nhạy cảm, điểm vào/ra |
| Sơ đồ thành phần và triển khai | API, worker, database, queue, storage, vùng mạng, zone, luồng giao tiếp |
| Danh sách NFR/SLO | Chỉ số, công thức đo, mức mục tiêu, điều kiện và chủ sở hữu |
| ADR | Các lựa chọn chính, phương án thay thế, lý do, hệ quả, điều kiện xét lại |
| Mô hình bảo mật | Ranh giới tin cậy, IAM, secrets, mã hóa, audit, kiểm soát truy cập |
| Kế hoạch HA/DR | Điểm lỗi, backup, RTO/RPO, kịch bản khôi phục và kết quả diễn tập |
| Kế hoạch vận hành | CI/CD, IaC, alert, runbook, rollback, người trực và phương án xử lý |
| Ước tính chi phí | Tải cơ sở/cao điểm, giả định giá, chi phí mạng/log/backup, cảnh báo |
| Báo cáo Well-Architected | Phát hiện, bằng chứng, ưu tiên, chủ sở hữu, hạn xử lý |

Không nhất thiết phải có mười công cụ khác nhau để tạo bộ hồ sơ này. Các sơ đồ, tài liệu ngắn và cấu hình được quản lý phiên bản trong cùng một repository có thể đủ cho một đội nhỏ, miễn là thông tin được cập nhật và kiểm chứng.

## 12. Bài thực hành: tự thiết kế và review một workload

**Đề bài:** Bạn được giao thiết kế phiên bản đầu cho ứng dụng đặt lịch ở ví dụ trên, yêu cầu 200 RPS cao điểm, SLO thành công 99,9%/tháng, p95 API đọc dưới 300 ms, RTO 60 phút, RPO 15 phút; dữ liệu đặt lịch phải tránh trùng; thông báo được xử lý nền. Hãy coi các con số này là yêu cầu giả định cần xác nhận với chủ sản phẩm.

**Yêu cầu đầu ra:**

1. Vẽ sơ đồ ngữ cảnh và sơ đồ triển khai thể hiện rõ mạng public/private, API, database, queue, worker, object storage và điểm kết nối nhà cung cấp thông báo.
2. Giải thích vì sao chọn kiểu compute và database; nêu ít nhất **một phương án thay thế** cùng điều kiện khiến bạn đổi quyết định.
3. Chỉ ra ba điểm lỗi quan trọng, ảnh hưởng đến luồng đặt lịch và cách phát hiện/khôi phục.
4. Xây dựng phép thử chứng minh chống đặt trùng, retry an toàn, chịu lỗi một instance và phục hồi dữ liệu theo RPO/RTO.
5. Ước lượng các nhóm chi phí trong ba kịch bản tải; xác định chỉ số vận hành và cảnh báo chính.
6. Review theo cả sáu trụ cột Well-Architected; ghi ít nhất một phát hiện có bằng chứng và hành động nghiệm thu được cho mỗi trụ cột.

**Tiêu chí tự đánh giá:** Bạn giải thích được *mỗi thành phần phục vụ yêu cầu nào*, *điều gì xảy ra khi nó hỏng*, *đo bằng gì để biết thiết kế đạt yêu cầu*, và *có thể thay thế bằng phương án nào nếu giả định thay đổi*. Nếu một trong bốn câu hỏi chưa trả lời được, kiến trúc vẫn có một quyết định cần làm rõ.

## 13. Những sai lầm thường gặp cần tránh

- **Bắt đầu bằng tên dịch vụ:** Dễ dẫn đến kiến trúc phức tạp nhưng thiếu mục tiêu SLO, bảo mật và chi phí.
- **Đánh đồng triển khai nhiều bản sao với chịu lỗi toàn hệ thống:** Database, mạng, trạng thái phiên hoặc phụ thuộc bên ngoài vẫn có thể là điểm lỗi duy nhất.
- **Đánh đồng replication với backup:** Lỗi logic, xóa nhầm hoặc ransomware có thể lan sang bản sao đồng bộ.
- **Thiết kế scale chỉ bằng tăng số instance:** Database, connection pool, quota, hàng đợi và downstream service có thể thành nút thắt.
- **Dùng microservices khi chưa có ranh giới rõ:** Tăng giao tiếp mạng và vận hành trong khi chưa đem lại lợi ích độc lập thực tế.
- **Chỉ đánh giá sơ đồ trên giấy:** Không có load test, restore test hay diễn tập lỗi thì chưa đủ bằng chứng cho các cam kết.
- **Xem chi phí là bước cuối:** Chi phí lưu lượng mạng, log, backup và mô hình vận hành có thể ảnh hưởng trực tiếp đến lựa chọn kiến trúc.
- **Review một lần rồi bỏ quên:** Thay đổi workload, lưu lượng và cấu hình sẽ khiến kết luận cũ không còn đúng.

Kiến trúc đám mây là chuỗi quyết định có điều kiện. Bắt đầu từ mục tiêu nghiệp vụ, lượng hóa chất lượng, xây dựng phương án đơn giản nhất đáp ứng yêu cầu, ghi nhận đánh đổi, kiểm thử những giả định rủi ro cao và dùng Well-Architected để đánh giá định kỳ. Giá trị của lộ trình nằm ở khả năng **giải thích, đo lường và điều chỉnh** kiến trúc theo thực tế vận hành.
