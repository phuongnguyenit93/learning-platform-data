# Đánh giá mức sẵn sàng, rủi ro và phương án di chuyển

## 1. Mục tiêu học tập và bối cảnh

Di chuyển ứng dụng lên đám mây (cloud migration) là một quyết định kiến trúc và vận hành, không đơn thuần là chuyển máy chủ sang một hạ tầng khác. Với **CLOUD_ARCHITECTURE**, người thiết kế cần đi từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai; sau đó cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành** theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Lập danh mục ứng dụng, dữ liệu, hạ tầng và phụ thuộc để biết chính xác đối tượng sẽ di chuyển.
- Đánh giá mức sẵn sàng của từng workload bằng tiêu chí có thể kiểm chứng, tách điểm tổng hợp khỏi các điều kiện bắt buộc.
- Xác định và ưu tiên rủi ro kỹ thuật, nghiệp vụ, bảo mật, dữ liệu, pháp lý và vận hành.
- Lựa chọn phương án di chuyển phù hợp với mục tiêu kinh doanh, năng lực đội ngũ và ràng buộc của hệ thống.
- Đề xuất các đợt di chuyển (wave), kịch bản chuyển đổi (cutover), quay lui (rollback) và thước đo chấp nhận sau di chuyển.

**Đầu ra mong muốn** của một đợt đánh giá là một hồ sơ quyết định gồm: sơ đồ trạng thái hiện tại, yêu cầu trạng thái đích, danh mục phụ thuộc, điểm sẵn sàng, sổ rủi ro, phương án đề xuất cho từng workload, kế hoạch thử nghiệm và tiêu chí go/no-go.

## 2. Trước khi quyết định: xác định lý do và phạm vi

Không thể chọn đúng phương án nếu chưa trả lời được vì sao tổ chức cần di chuyển. Các động lực thường gặp gồm hết hạn hợp đồng trung tâm dữ liệu, tăng tải theo mùa, rút ngắn thời gian phát hành, cải thiện khôi phục thảm họa hoặc giảm công sức quản trị hạ tầng. Các động lực này có thể dẫn đến kiến trúc đích khác nhau.

Đối với mỗi ứng dụng, ghi lại:

| Nhóm câu hỏi | Nội dung cần làm rõ | Ví dụ đầu ra |
| --- | --- | --- |
| Nghiệp vụ | Hệ thống phục vụ quy trình nào? Thời gian ngừng chấp nhận được? | Đặt hàng 24/7; tối đa 30 phút gián đoạn có kế hoạch |
| Chất lượng dịch vụ | Mức tải hiện tại, tăng trưởng, độ trễ và tính sẵn sàng yêu cầu? | P95 dưới 300 ms tại tải mục tiêu |
| Dữ liệu | Dữ liệu nào nhạy cảm? Quy mô, tốc độ tăng, yêu cầu lưu trữ? | CSDL giao dịch 500 GB; giữ bản sao lưu theo chính sách |
| Tính liên tục | RTO và RPO của từng hệ thống? | RTO 2 giờ; RPO 15 phút |
| Tuân thủ | Ràng buộc hợp đồng, lưu trú dữ liệu, kiểm toán và bên thứ ba? | Danh sách nghĩa vụ cần bộ phận pháp chế xác nhận |
| Tổ chức | Ai quyết định, ai vận hành, ai hỗ trợ khi có sự cố? | Business owner, application owner, platform, security, DBA |
| Kinh tế | Chi phí hiện tại, ngân sách chuyển đổi, thời hạn và cách đo lợi ích? | Tổng chi phí sở hữu dự kiến trong 3 năm |

Hai chỉ số phải được hiểu đúng:

- **RTO (Recovery Time Objective)**: thời gian mục tiêu để khôi phục dịch vụ sau sự cố. RTO không đồng nghĩa thời gian downtime được phép trong một đợt cutover có kế hoạch.
- **RPO (Recovery Point Objective)**: khoảng mất dữ liệu tối đa có thể chấp nhận khi khôi phục, tính theo thời điểm dữ liệu được phục hồi so với thời điểm sự cố. RPO 15 phút cần cơ chế và phép thử thực tế để chứng minh.

Mục tiêu của kiến trúc đích phải đo được. “Lên cloud để nhanh hơn” chưa đủ để quyết định; “đáp ứng P95 dưới 300 ms trong đợt tải 2.000 người dùng đồng thời” cho phép thiết kế và kiểm thử.

## 3. Khảo sát trạng thái hiện tại: xây bản đồ workload và phụ thuộc

### 3.1. Danh mục tối thiểu

Tập hợp bằng phỏng vấn, công cụ discovery, giám sát hiện có và đối chiếu cấu hình thực tế. Không nên tin hoàn toàn vào CMDB nếu lâu chưa cập nhật.

| Tài sản | Cần thu thập | Vì sao quan trọng |
| --- | --- | --- |
| Ứng dụng và dịch vụ | Phiên bản runtime, hệ điều hành, chủ sở hữu, giờ cao điểm, SLA | Xác định tương thích và mức độ quan trọng |
| Compute | vCPU, RAM, sử dụng P50/P95, đĩa, tự động hóa triển khai | Chọn kích thước ban đầu và mức co giãn |
| Mạng | Luồng vào/ra, DNS, firewall, VPN, liên kết riêng, băng thông, độ trễ | Tránh bỏ sót kết nối và điểm nghẽn |
| Dữ liệu | Hệ CSDL, dung lượng, tăng trưởng, giao dịch, khóa, backup, mã hóa | Lập cách đồng bộ và kiểm tra nhất quán |
| Tích hợp | API, hàng đợi, lịch chạy batch, SFTP, SMTP, IdP, nhà cung cấp | Xác định thứ tự di chuyển |
| Vận hành | Logging, metrics, tracing, alert, CI/CD, IaC, runbook, trực sự cố | Đảm bảo đội ngũ có thể vận hành |
| Pháp lý và bảo mật | Phân loại dữ liệu, quyền truy cập, bí mật, chứng chỉ, yêu cầu kiểm toán | Thiết kế biện pháp kiểm soát phù hợp |

Với dữ liệu khó quan sát, nên ghi rõ mức độ tin cậy: **đã đo**, **được chủ hệ thống xác nhận** hoặc **chưa xác minh**. Giả định chưa xác minh phải trở thành hạng mục kiểm tra trước khi quyết định.

### 3.2. Bản đồ phụ thuộc thay vì danh sách máy chủ

Một ứng dụng hiếm khi hoạt động độc lập. Ví dụ:

~~~mermaid
flowchart LR
    U[Khách hàng] --> DNS[DNS / CDN]
    DNS --> W[Web và API]
    W --> DB[(CSDL giao dịch)]
    W --> Q[Hàng đợi]
    Q --> B[Worker xử lý đơn]
    B --> X[Đối tác vận chuyển]
    W --> ID[Định danh / SSO]
    B --> R[(Hệ thống báo cáo)]
~~~

Nếu web/API được đưa lên cloud nhưng worker, CSDL hoặc hệ thống định danh vẫn ở trung tâm dữ liệu cũ, mỗi lời gọi xuyên mạng sẽ tạo thêm độ trễ và rủi ro kết nối. Cần đo **luồng giao tiếp** (ai gọi ai, giao thức, tần suất, dung lượng, độ trễ), không chỉ xác định máy chủ nằm ở đâu.

Sử dụng bản đồ này để nhận diện **migration group**: các thành phần phải chuyển cùng đợt hoặc cần hợp đồng giao tiếp tương thích tạm thời. Với phụ thuộc vòng, có thể giữ giao diện ổn định trong giai đoạn chuyển tiếp rồi tách sau.

### 3.3. Phân loại độ quan trọng và độ phức tạp

Một cách thực dụng là phân theo hai trục:

- **Ảnh hưởng nghiệp vụ khi lỗi**: thấp, trung bình, cao, thiết yếu.
- **Phức tạp di chuyển**: thấp, trung bình, cao theo số phụ thuộc, trạng thái dữ liệu, giới hạn downtime, yêu cầu tuân thủ, tương thích phần mềm và khả năng tự động hóa.

Ứng dụng tác động thấp và ít phụ thuộc thường phù hợp để thử nghiệm cách triển khai, đo đạc và đào tạo đội ngũ. Ứng dụng thiết yếu có nhiều giao dịch cần nhiều bằng chứng kiểm thử hơn, ngay cả khi hạ tầng đích trông có vẻ đơn giản.

## 4. Đánh giá mức sẵn sàng theo tiêu chí có bằng chứng

“Mức sẵn sàng” là khả năng **di chuyển và vận hành an toàn trong kiến trúc đích**. Không nên chỉ hỏi ứng dụng có chạy được trên máy ảo cloud hay không.

### 4.1. Khung chấm điểm mẫu

Chấm mỗi chiều từ **0 đến 4**:

- **0 – Chưa biết**: chưa có chủ sở hữu hoặc bằng chứng đáng tin.
- **1 – Chưa đạt**: tồn tại thiếu sót nghiêm trọng cần khắc phục.
- **2 – Có điều kiện**: đã biết hướng xử lý nhưng chưa kiểm chứng đầy đủ.
- **3 – Sẵn sàng có kiểm soát**: điều kiện chính đã đáp ứng, có kết quả kiểm thử.
- **4 – Đã chứng minh**: đáp ứng bằng tài liệu, tự động hóa và bài kiểm tra lặp lại được.

| Chiều đánh giá | Trọng số minh họa | Bằng chứng mong đợi |
| --- | ---: | --- |
| Mạng và kết nối | 20% | Định tuyến, DNS, firewall, băng thông và độ trễ đã thử |
| Tương thích ứng dụng | 20% | PoC runtime, thư viện, giấy phép, phụ thuộc |
| Dữ liệu và khôi phục | 20% | Backup/restore thành công, kiểm tra dữ liệu, thử RPO/RTO |
| Vận hành | 15% | Giám sát, cảnh báo, quyền trực sự cố, runbook, CI/CD |
| Bảo mật và tuân thủ | 15% | Định danh, phân quyền, mã hóa, audit và kiểm soát bắt buộc |
| Kinh tế và năng lực | 10% | Ước tính TCO, ngân sách, người phụ trách và năng lực kỹ thuật |

Công thức với tổng trọng số bằng 100%:

**Readiness (%) = Σ [điểm chiều / 4 × trọng số chiều]**

Ví dụ điểm lần lượt là **3, 2, 2, 1, 3, 2** thì:

**Readiness = 3/4 × 20% + 2/4 × 20% + 2/4 × 20% + 1/4 × 15% + 3/4 × 15% + 2/4 × 10% = 55%**.

55% thể hiện các khoảng trống cần xử lý; **không** phải xác suất di chuyển thành công. Ngưỡng đánh giá là quy ước nội bộ, phải được hiệu chuẩn theo độ quan trọng và bằng chứng của từng hệ thống. Ví dụ, đội ngũ có thể chọn dưới 60% là “cần chuẩn bị thêm”, 60–79% là “chỉ được pilot có kiểm soát”, từ 80% là “có thể đề nghị xét go-live”, nhưng không được dùng ngưỡng điểm thay thế bước phê duyệt.

### 4.2. Các cổng bắt buộc (hard gates)

Một workload vẫn có thể **không được di chuyển**, dù điểm tổng hợp cao, nếu còn các điều kiện như:

1. Chưa xác nhận quyền sử dụng và nơi lưu dữ liệu theo hợp đồng/quy định áp dụng.
2. Chưa có backup nhất quán và kết quả kiểm thử restore.
3. Không chứng minh được cơ chế cấp quyền tối thiểu, quản lý bí mật hoặc ghi nhật ký truy cập bắt buộc.
4. Chưa có chủ sở hữu ứng dụng, đội xử lý sự cố hoặc kế hoạch truyền thông khi cutover.
5. Không đáp ứng mục tiêu downtime, RTO/RPO và không có phương án giảm thiểu được chấp nhận.
6. Chưa hiểu đường truyền/phụ thuộc thiết yếu có thể làm gián đoạn giao dịch.

Quy tắc quyết định: **điểm tổng hợp hỗ trợ ưu tiên cải thiện; hard gates quyết định có đủ điều kiện triển khai hay chưa**.

### 4.3. Gắn đánh giá với Well-Architected

Để nhìn vượt ra ngoài “máy chạy được”, đối chiếu thiết kế với các trụ cột phổ biến: vận hành xuất sắc, bảo mật, độ tin cậy, hiệu năng, tối ưu chi phí và tính bền vững. Không phải mọi cloud provider sử dụng cùng tên và số trụ cột; hãy áp dụng framework cụ thể của nền tảng đã chọn.

Câu hỏi gợi ý: có thể tự động khôi phục và quan sát sự cố? Quyền có thể được kiểm toán? Thử lỗi một vùng sẵn sàng có mất dữ liệu hoặc vượt RTO? Tăng tải có làm tăng chi phí ngoài dự báo? Đội ngũ có đo điện năng/tài nguyên lãng phí và giảm kích thước dư thừa?

## 5. Lập sổ rủi ro để quyết định bằng chứng

Rủi ro cần ghi theo cấu trúc **nguyên nhân → sự kiện → tác động**, cùng chủ sở hữu, phương án xử lý và dấu hiệu kích hoạt. “Mạng có vấn đề” không đủ để hành động; “kết nối WAN bị quá tải khi đồng bộ CSDL dẫn đến tăng độ trễ giao dịch và trễ cutover” là rủi ro có thể kiểm thử.

Để ưu tiên ban đầu, chấm **xác suất L** từ 1 (hiếm) đến 5 (rất có thể) và **mức ảnh hưởng I** từ 1 (nhỏ) đến 5 (nghiêm trọng), sau đó tính **L × I**. Điểm 1–25 chỉ dùng để sắp xếp việc xử lý và không có nghĩa là đo lường xác suất thực. Với rủi ro an toàn hoặc vi phạm quy định, vẫn cần áp dụng hard gate độc lập.

| Rủi ro | L × I | Hành động giảm thiểu | Dấu hiệu / bằng chứng | Chủ sở hữu |
| --- | ---: | --- | --- | --- |
| Băng thông không đủ khi chuyển dữ liệu | 4 × 4 = 16 | Đo throughput, thử đồng bộ, giới hạn tải và cân nhắc truyền offline | Thời gian copy mẫu, độ trễ ứng dụng | Network lead |
| Không tương thích phiên bản CSDL | 3 × 5 = 15 | Kiểm tra extension, collation, SQL, replication và chạy PoC | Kết quả thử chức năng và hiệu năng | DBA |
| Sai cấu hình phân quyền/IAM | 3 × 5 = 15 | IaC, review quyền tối thiểu, quét chính sách, audit | Kết quả kiểm tra truy cập | Security lead |
| Phụ thuộc đối tác dùng IP cố định | 3 × 4 = 12 | Kiểm kê allowlist, chuẩn bị IP/NAT và xác nhận với đối tác | Kiểm thử kết nối end-to-end | Integration owner |
| Chi phí tăng khi vận hành song song | 4 × 3 = 12 | Đặt ngân sách, nhãn chi phí, hạn mức và thời hạn xóa môi trường cũ | Báo cáo chi phí theo ngày | FinOps owner |
| Dữ liệu thay đổi sau thời điểm snapshot | 3 × 5 = 15 | Replication/CDC, kiểm tra lag và thao tác đóng băng ghi khi cutover | Lệch dữ liệu, đối soát bản ghi | Data owner |

Sau giảm thiểu, đánh giá lại **rủi ro còn lại (residual risk)** và người có thẩm quyền chấp nhận. Sổ rủi ro phải được cập nhật khi thiết kế hoặc giả định thay đổi, không chỉ hoàn thành một lần lúc kickoff.

## 6. Lựa chọn phương án di chuyển: bộ chiến lược 7R

Các chữ R là một **khung lựa chọn**, không phải thứ tự phải thực hiện. Mỗi ứng dụng, CSDL hoặc thành phần có thể đi theo một chiến lược riêng.

| Phương án | Khi phù hợp | Lợi ích | Đánh đổi hoặc rủi ro |
| --- | --- | --- | --- |
| **Retire** – loại bỏ | Ít sử dụng, không còn giá trị, đã có chức năng thay thế | Giảm nợ kỹ thuật và chi phí | Phải xác nhận quyền lưu giữ dữ liệu, phụ thuộc còn sót |
| **Retain** – giữ lại | Bị ràng buộc pháp lý/giấy phép, độ trễ đặc thù, chưa có lợi ích chuyển | Tránh thay đổi sớm khi chưa đủ điều kiện | Vẫn phải quản lý vận hành, bảo mật, kết nối hybrid |
| **Rehost** – chuyển hạ tầng gần như nguyên trạng | Cần di chuyển nhanh, ứng dụng tương thích VM | Ít thay đổi mã, dễ xác định phạm vi ban đầu | Có thể giữ nguyên giới hạn mở rộng và chi phí cao |
| **Replatform** – tối ưu nền tảng vừa đủ | Có thể thay DB, runtime, container hoặc dịch vụ managed mà ít đổi nghiệp vụ | Giảm công sức vận hành, tận dụng dịch vụ cloud | Kiểm thử tương thích, cấu hình và hiệu năng |
| **Repurchase** – thay bằng sản phẩm/SaaS | Nghiệp vụ phổ biến, giải pháp SaaS đáp ứng yêu cầu | Chuyển trách nhiệm vận hành nhiều phần cho nhà cung cấp | Di chuyển dữ liệu, lock-in, thay đổi quy trình, tích hợp |
| **Refactor / Rearchitect** – thiết kế lại | Cần tính đàn hồi, tự phục hồi, đổi mô hình phát hành hoặc mở rộng mạnh | Tối ưu kiến trúc dài hạn | Chi phí xây dựng, thời gian và rủi ro thay đổi lớn |
| **Relocate** – chuyển nền ảo hóa hoặc stack tương thích | Có cơ chế chuyển cả cụm/VM giữa các nền tương thích | Rút ngắn thay đổi tầng ứng dụng | Phụ thuộc năng lực dịch vụ, giấy phép và tương thích hạ tầng |

Thuật ngữ “6R/7R” có thể khác nhau giữa các tài liệu. Khi lập báo cáo, ghi rõ ý nghĩa từng R để tránh cùng từ nhưng khác phạm vi.

### 6.1. Quy trình chọn phương án

~~~mermaid
flowchart TD
    A[Bắt đầu với workload và yêu cầu] --> B{Còn giá trị nghiệp vụ?}
    B -- Không --> C[Retire và xử lý lưu trữ dữ liệu]
    B -- Có --> D{Bắt buộc giữ tại chỗ?}
    D -- Có --> E[Retain và thiết kế kết nối hybrid]
    D -- Không --> F{SaaS đáp ứng chức năng, dữ liệu và tuân thủ?}
    F -- Có --> G[Đánh giá Repurchase]
    F -- Không --> H{Cần đổi kiến trúc để đạt NFR?}
    H -- Có --> I[Refactor / Rearchitect]
    H -- Không --> J{Có lợi ích rõ khi đổi dịch vụ nền tảng?}
    J -- Có --> K[Replatform]
    J -- Không --> L{Có cơ chế di chuyển nguyên stack tương thích?}
    L -- Có --> M[Relocate hoặc Rehost, so sánh TCO]
    L -- Không --> N[Rehost nếu tương thích, hoặc xem xét lại]
~~~

Sơ đồ hỗ trợ sàng lọc; phương án cuối cùng cần kiểm thử, đánh giá chi phí, xác nhận quyền sở hữu dữ liệu và đánh giá rủi ro. **Retain** không đồng nghĩa bỏ qua hiện đại hóa: vẫn có thể triển khai bảo vệ, backup và quan sát cho hệ thống giữ tại chỗ.

### 6.2. Một số đánh đổi đặc trưng

**Độ tin cậy:** chuyển VM sang một vùng đám mây không tự tạo ra HA/DR. Cần xem failure domain, số bản sao, vùng sẵn sàng, backup và phép thử phục hồi.

**Bảo mật:** cloud cung cấp công cụ như IAM, KMS, firewall, log nhưng đội ngũ vẫn phải thiết kế, cấu hình và vận hành các phần thuộc trách nhiệm của mình theo mô hình shared responsibility.

**Khả năng mở rộng:** rehost có thể nâng kích thước máy, nhưng bottleneck ở CSDL đơn, lock hoặc session state vẫn tồn tại. Replatform/refactor có thể cần để scale theo chiều ngang.

**Chi phí:** chi phí cloud gồm compute, storage, backup, truyền dữ liệu ra ngoài/giữa vùng, dịch vụ managed, giám sát và hỗ trợ. Trong giai đoạn chuyển, hệ cũ và hệ mới thường chạy song song. So sánh **TCO 3 năm** cùng chi phí chuyển đổi và chi phí/rủi ro khi chưa đạt mục tiêu, tránh chỉ so giá máy ảo theo tháng.

**Vận hành:** dịch vụ managed giảm một số việc bảo trì nhưng đòi hỏi năng lực mới: IaC, giám sát, kiểm soát quyền, backup/restore, kiểm soát quota và chi phí.

## 7. Thiết kế trạng thái đích và nền tảng tối thiểu

Một kế hoạch di chuyển có thể thất bại dù ứng dụng đã tương thích nếu chưa chuẩn bị **landing zone**. Các năng lực tối thiểu thường gồm:

1. **Tổ chức tài khoản/project/subscription:** phân tách môi trường, quy chuẩn tên và nhãn chi phí, quyền chủ sở hữu, hạn mức.
2. **Định danh và quyền:** tích hợp identity provider, MFA cho quản trị, quyền tối thiểu, tài khoản dịch vụ, chu kỳ quản lý khóa và bí mật.
3. **Mạng:** phân đoạn mạng, subnet, routing, kiểm soát outbound/inbound, DNS, hybrid VPN/đường kết nối, kế hoạch IP tránh trùng.
4. **Bảo vệ dữ liệu:** phân loại, mã hóa khi lưu và truyền, quản lý khóa, snapshot/backup, lưu giữ và kiểm thử restore.
5. **Quan sát và phản ứng:** log tập trung, metrics, tracing, cảnh báo theo SLO, thời gian lưu log, quy trình trực sự cố.
6. **Triển khai:** CI/CD, hạ tầng dưới dạng mã (IaC), review thay đổi, kiểm tra cấu hình, cơ chế quay lui phiên bản.
7. **Quản trị chi phí:** ngân sách, cảnh báo vượt ngưỡng, tagging và báo cáo theo ứng dụng, môi trường, nhóm phụ trách.

Các tài nguyên nên được thiết kế theo **failure domain** và yêu cầu thực tế: ít nhất phải xác định việc hỏng một instance, một zone hoặc mất kết nối hybrid ảnh hưởng thế nào đến dịch vụ. Tránh mặc định rằng đa vùng luôn cần thiết; hãy đối chiếu chi phí, độ phức tạp và RTO/RPO.

## 8. Đánh giá riêng việc di chuyển dữ liệu

Di chuyển dữ liệu thường quyết định cửa sổ downtime và khả năng quay lui của hệ thống có trạng thái.

| Cách tiếp cận | Cơ chế điển hình | Phù hợp khi | Điều kiện cần kiểm tra |
| --- | --- | --- | --- |
| Offline / backup-restore | Dừng ghi, lấy bản backup, chuyển và restore | Dữ liệu vừa phải, chấp nhận downtime | Thời gian sao chép, restore, toàn vẹn |
| Online / replication | Đồng bộ liên tục, thu hẹp lag, chuyển vai trò ghi tại cutover | Downtime ngắn, nguồn và đích hỗ trợ | Thứ tự giao dịch, replication lag, failover |
| CDC và chuyển theo giai đoạn | Truyền thay đổi qua log dữ liệu | Hệ thống lớn, cần song song và kiểm tra | Idempotency, schema evolution, trùng/mất sự kiện |
| Chuyển đổi định dạng / ETL | Trích xuất, làm sạch, chuyển đổi rồi nạp | Đổi mô hình dữ liệu hoặc thay SaaS | Mapping, đối soát, chất lượng và quy tắc nghiệp vụ |

**Ước tính thô thời gian chuyển** dữ liệu: thời gian tối thiểu ≈ dung lượng dữ liệu / thông lượng thực tế. Với 500 GB qua đường truyền đạt thực tế 100 MB/s, riêng luồng truyền lý tưởng cũng khoảng 5.000 giây (xấp xỉ 83 phút), **chưa** tính backup, mã hóa, nén, xác minh, truyền lại và restore. Thử nghiệm với mẫu đủ lớn để đo throughput thực tế và thời gian xử lý đầu cuối.

Kiểm tra dữ liệu ở nhiều mức: số lượng bản ghi, checksum hoặc hash theo lô phù hợp, khóa ngoại, tổng tiền/giao dịch theo ngày, độ trễ đồng bộ và kết quả truy vấn nghiệp vụ. Chỉ “DB mở được” không phải bằng chứng đủ.

Nếu hệ thống nguồn và đích cùng nhận ghi, phải có thiết kế giải quyết xung đột, thứ tự sự kiện và xử lý trùng. **Dual-write** có thể gây sai lệch; không nên dùng mặc định để né downtime. Với một nguồn ghi duy nhất, cần xác định **điểm chuyển quyền ghi** và các bước bảo đảm client không tiếp tục ghi nhầm vào nguồn cũ.

## 9. Chia wave, thử nghiệm và chuyển đổi

### 9.1. Sắp xếp đợt di chuyển

Một kế hoạch có thể chia như sau:

| Giai đoạn | Phạm vi | Điều cần chứng minh trước khi qua giai đoạn |
| --- | --- | --- |
| Foundation | Landing zone, connectivity, bảo mật, quan sát | Kiểm tra chính sách, luồng mạng, backup và cảnh báo |
| Pilot | Dịch vụ ít quan trọng, ít phụ thuộc | Tự động triển khai, truy cập, xử lý sự cố, chi phí |
| Wave 1 | Nhóm ứng dụng ít dữ liệu / ít phụ thuộc | Kiểm thử tích hợp, hiệu năng, khôi phục và rollback |
| Wave 2 | Ứng dụng trọng yếu và dữ liệu giao dịch | Rehearsal cutover, đối soát, năng lực trực và phê duyệt |
| Optimization | Rightsizing, autoscaling, cải tiến kiến trúc | SLO, chi phí thực tế, tính ổn định và bàn giao |

Một wave cần xem xét tính liên kết phụ thuộc, không chỉ độ khó đơn lẻ. Hệ thống ít quan trọng nhưng nhiều phụ thuộc với lõi giao dịch có thể không phù hợp làm pilot.

### 9.2. Runbook cutover mẫu

**Trước cutover**

- Chốt change window, người chịu trách nhiệm, kênh liên lạc, mức gián đoạn cho phép và quyết định go/no-go.
- Xác minh backup và khả năng restore; kiểm tra sức khỏe hệ nguồn/đích, replication lag, quota và kết nối đối tác.
- Chạy thử cutover trên môi trường tương đương; đo thời gian từng bước và điều chỉnh kế hoạch.
- Chốt các chỉ số quan sát: lỗi, p95/p99 latency, queue lag, CPU/memory, connection pool, số lượng đơn và chênh lệch dữ liệu.
- Chuẩn bị quy trình giảm tải, tạm dừng batch/ghi nếu cần, cùng kế hoạch thông báo người dùng.

**Trong cutover**

1. Công bố bắt đầu; ghi thời điểm và phiên bản cấu hình.
2. Tạm dừng hoặc điều phối ghi ở nguồn theo thiết kế; đợi replication lag đạt ngưỡng chấp nhận.
3. Xác minh dữ liệu cuối cùng và chuyển vai trò nguồn ghi; cập nhật endpoint, DNS hoặc định tuyến.
4. Chạy smoke test qua đường truy cập thật: đăng nhập, đặt hàng, thanh toán giả lập, hàng đợi, API đối tác.
5. Theo dõi SLO và đối soát nghiệp vụ trong thời gian quan sát đã định.
6. Chủ sở hữu được phân quyền quyết định tiếp tục, xử lý tiến hoặc quay lui theo tiêu chí công bố trước.

**Sau cutover**

- Theo dõi tăng cường, đối soát số liệu, cập nhật runbook, inventory, sơ đồ, tài liệu hỗ trợ.
- Chỉ ngừng hạ tầng cũ sau khi hết thời gian giữ dự phòng và hoàn thành yêu cầu lưu trữ, kiểm toán, tuân thủ.
- Ghi nhận sai lệch giữa kế hoạch và thực tế, cập nhật ước lượng cho wave tiếp theo.

### 9.3. Rollback phải xét dữ liệu mới

Nếu đã nhận ghi ở hệ đích, chuyển traffic về hệ nguồn cũ **không** tự đảm bảo dữ liệu nhất quán. Phải xác định trước một trong các cách có thể kiểm chứng: đồng bộ ngược có kiểm soát, phục hồi bằng bản sao nhất quán, thao tác nghiệp vụ bù trừ hoặc **forward fix**. Khi không có đường rollback dữ liệu an toàn, đặt **mốc không thể quay lui** và yêu cầu phê duyệt phù hợp trước khi vượt mốc đó.

Tiêu chí go/no-go cần khách quan, ví dụ: hoàn tất restore rehearsal trong giới hạn RTO; lỗi giao dịch không vượt ngưỡng đã duyệt; dữ liệu đối soát khớp; mọi hard gate đạt; nhóm trực và đại diện nghiệp vụ có mặt. Không nên thông qua chỉ dựa trên việc “máy chủ đang xanh”.

## 10. Ví dụ xuyên suốt: hệ thống đặt hàng

Giả sử một doanh nghiệp có hệ thống đặt hàng gồm web/API chạy trên VM, CSDL quan hệ 500 GB, worker gửi yêu cầu tới đối tác vận chuyển và bộ báo cáo batch mỗi đêm. Doanh nghiệp muốn giảm công sức quản trị máy chủ và tăng năng lực chịu tải mùa cao điểm. Đây là **tình huống giả định** để minh họa quyết định, không phải cấu hình mặc định áp dụng cho mọi doanh nghiệp.

Yêu cầu được thống nhất:

- RTO cho dịch vụ đặt hàng: **2 giờ**; RPO: **15 phút**.
- P95 của luồng tạo đơn tại tải mục tiêu: **dưới 300 ms**.
- Cần ghi nhật ký truy cập dữ liệu nhạy cảm, áp dụng phân quyền tối thiểu và mã hóa dữ liệu.
- Phải thử tích hợp với đối tác đang sử dụng danh sách IP cho phép.

### 10.1. Bằng chứng khảo sát

| Thành phần | Phát hiện | Phương án sơ bộ |
| --- | --- | --- |
| Web/API | Tương thích runtime đích; session được giữ trong bộ nhớ một máy | Replatform sau khi chuyển session sang kho dùng chung hoặc thiết kế stateless |
| CSDL | Có extension chưa xác nhận hỗ trợ trên DB managed | PoC tương thích trước khi chọn managed DB; tạm Rehost nếu chưa đạt |
| Worker tích hợp | Đối tác chỉ nhận traffic từ IP đã đăng ký | Chuẩn bị egress IP ổn định, xác nhận allowlist, test end-to-end |
| Báo cáo đêm | Chạy 1 lần/ngày, không cần độ trễ thấp | Chuyển sau dịch vụ lõi nếu phụ thuộc dữ liệu rõ ràng |
| Vận hành | Chưa có tracing, cảnh báo dựa trên SLO | Bổ sung observability và diễn tập xử lý sự cố trước pilot |

Giả sử khung chấm ở phần 4 cho ra **55%**. Hệ thống chưa đủ căn cứ go-live vì **restore chưa được diễn tập** và extension CSDL chưa xác minh. Việc có thể khởi động web trên VM cloud chỉ là một phần của đánh giá.

### 10.2. Quyết định và trình tự đề xuất

1. Xây landing zone, IAM, logging, kết nối tới đối tác và môi trường thử nghiệm với IaC.
2. Chạy PoC extension/SQL của CSDL managed; đo hiệu năng và thử restore. Nếu không đạt, cân nhắc Rehost CSDL có kiểm soát trong đợt đầu.
3. Chuyển web/API sang nền hỗ trợ autoscaling sau khi giải quyết session state, cấu hình health check và khả năng xử lý request lặp.
4. Kiểm chứng đồng bộ dữ liệu với rehearsal có đủ kích thước, đo replication lag và thử đối soát tổng số đơn/doanh thu.
5. Di chuyển cùng nhóm thành phần cần độ trễ thấp; giữ tích hợp tạm thời qua đường hybrid đã thử.
6. Cutover theo runbook và theo dõi chỉ số nghiệp vụ, không chỉ metrics hạ tầng.
7. Sau giai đoạn ổn định, đánh giá tối ưu database, thay đổi kiến trúc báo cáo và tắt hạ tầng cũ.

Ví dụ minh họa một kết luận có điều kiện: **replatform ứng dụng trước, chọn CSDL sau PoC**, thay vì bắt buộc tất cả thành phần “lên managed services” trong một lần. Phương án này giảm rủi ro tương thích và vẫn tiến dần tới mục tiêu vận hành.

## 11. Hồ sơ quyết định kiến trúc và bàn giao

Đối với mỗi workload, tài liệu quyết định (ADR hoặc biểu mẫu tương đương) nên nêu đầy đủ:

| Mục | Câu trả lời cần có |
| --- | --- |
| Vấn đề và mục tiêu | Động lực nghiệp vụ, NFR, phạm vi, các ràng buộc |
| Trạng thái hiện tại | Kiến trúc, dữ liệu, phụ thuộc, chủ sở hữu, điều chưa biết |
| Phương án đã cân nhắc | Ở lại, Rehost, Replatform, Repurchase, Refactor… cùng bằng chứng |
| Phương án chọn | Kiến trúc đích và lý do chấp nhận đánh đổi |
| Tính sẵn sàng | Điểm các chiều, hard gates, backlog và ngày kiểm tra lại |
| Rủi ro | L/I, mitigation, residual risk, owner, quyết định chấp nhận |
| Kế hoạch | Wave, rehearsal, cutover, rollback/forward fix, điều kiện go/no-go |
| Đo lường | SLO, RPO/RTO đã thử, chi phí thực tế, tác động nghiệp vụ |
| Bàn giao | Runbook, monitoring, lịch trực, người duyệt và tài liệu sau di chuyển |

Khi đánh giá thành công, cần xét **thời gian dài hơn thời điểm cutover**: hệ thống có giữ ổn định khi có sự cố, mở rộng đúng cách, khôi phục theo yêu cầu, đáp ứng kiểm soát bảo mật và nằm trong dự toán chi phí không.

## 12. Lỗi phổ biến và cách phòng tránh

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Bắt đầu từ VM mà bỏ qua nghiệp vụ | Chọn nền tảng không đáp ứng downtime/SLO | Chốt mục tiêu đo được trước discovery |
| Dựa vào danh sách server, quên luồng phụ thuộc | Đứt kết nối API, job, định danh, đối tác | Vẽ và kiểm thử dependency map |
| Mặc định cloud sẽ tự đảm bảo HA và an toàn | Single point of failure và quyền quá rộng | Thiết kế failure domain, IAM, backup, audit |
| Dùng điểm readiness làm giấy phép go-live | Bỏ sót hard gate pháp lý, dữ liệu, bảo mật | Tách cổng bắt buộc khỏi thang điểm |
| Chỉ kiểm thử chức năng | Sự cố khi tải cao, sao lưu hoặc failover | Test tải, phục hồi, bảo mật và tình huống lỗi |
| Không tính chi phí chuyển dữ liệu và chạy kép | Vượt ngân sách | TCO cùng dự báo giai đoạn chuyển tiếp |
| Chỉ có kế hoạch rollback ứng dụng | Dữ liệu đã ghi ở hệ đích không thể về nguồn an toàn | Định nghĩa chiến lược dữ liệu và mốc không thể quay lui |
| Tắt hệ cũ ngay sau cutover | Mất khả năng đối soát hoặc vi phạm lưu giữ | Có tiêu chí decommission được phê duyệt |

## 13. Bài thực hành áp dụng

Bạn nhận ba workload:

- **A – Cổng thông tin nội bộ:** ít phụ thuộc, dữ liệu tĩnh, có thể ngừng 4 giờ.
- **B – Xử lý thanh toán:** nhiều tích hợp, dữ liệu giao dịch liên tục, RPO gần 0 theo yêu cầu nghiệp vụ.
- **C – Báo cáo cũ:** ít người truy cập, dữ liệu có thể phải lưu theo chính sách.

Hãy lập bảng gồm **business owner, dependency, hard gates, readiness score, 7R được chọn, lý do, rủi ro còn lại và wave** cho từng workload. Trình bày kế hoạch kiểm thử và tiêu chí go/no-go cho workload B.

**Hướng giải tham khảo:** A là ứng viên pilot Rehost/Replatform sau khi kiểm tra quyền truy cập và backup. B nên chờ discovery phụ thuộc, thử replication, đối soát và xác minh RPO mục tiêu trước khi chọn Replatform hay Refactor; không thể suy ra phương án chỉ từ nhãn “thanh toán”. C là ứng viên Retire nếu đã xác nhận không còn nhu cầu, giải quyết lưu giữ dữ liệu và loại bỏ phụ thuộc. Không có phương án đúng tuyệt đối nếu chưa xác định đầy đủ điều kiện.

## 14. Ghi nhớ khi đưa ra quyết định

Một đề xuất di chuyển đáng tin cậy phải trả lời được **di chuyển để đạt mục tiêu gì; thành phần nào phụ thuộc nhau; bằng chứng nào chứng minh đủ sẵn sàng; rủi ro nào được kiểm soát; vì sao chọn phương án đó; kiểm chứng trước và sau cutover bằng cách nào; ai sẽ vận hành hệ thống mới**.

Hãy đánh giá từng workload như một quyết định có điều kiện và có thể kiểm chứng. Di chuyển an toàn diễn ra khi mục tiêu, kiến trúc, dữ liệu, con người và kế hoạch vận hành đều sẵn sàng, chứ không chỉ khi hạ tầng đích đã được tạo.
