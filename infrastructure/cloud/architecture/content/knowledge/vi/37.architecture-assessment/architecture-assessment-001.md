# Xây dựng checklist theo các thuộc tính chất lượng

## 1. Vì sao đánh giá kiến trúc cần checklist?

Một bản thiết kế đám mây có thể chạy đúng chức năng trong buổi demo nhưng vẫn thất bại khi tải tăng, một Availability Zone gặp sự cố, tài khoản bị lộ quyền, hóa đơn cloud vượt dự toán hoặc đội vận hành không thể xác định nguyên nhân lỗi. Những vấn đề này thuộc **thuộc tính chất lượng** (*quality attributes*): các đặc tính cho biết hệ thống thực hiện chức năng **tốt đến mức nào** trong những điều kiện cụ thể.

Trong module **CLOUD_ARCHITECTURE**, mục tiêu của việc xây dựng checklist là biến yêu cầu nghiệp vụ thành câu hỏi kiến trúc có thể kiểm chứng, qua đó đánh giá các lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Checklist giúp nhóm nhìn rõ đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành, đồng thời tổ chức đánh giá theo tư duy **Well-Architected**.

Checklist hiệu quả không phải danh sách “đã bật mã hóa”, “đã có autoscaling”, “đã sử dụng managed database” để tích dấu. Mỗi mục cần làm rõ:

- **Rủi ro cần tránh:** hệ thống có thể thất bại như thế nào?
- **Kỳ vọng:** hành vi nào là chấp nhận được khi gặp rủi ro đó?
- **Bằng chứng:** tài liệu, cấu hình, kết quả kiểm thử hoặc số liệu nào chứng minh?
- **Người chịu trách nhiệm:** ai xác nhận, xử lý và chấp nhận rủi ro còn lại?
- **Quyết định:** đạt, chưa đạt, cần kiểm chứng hay không áp dụng; có được triển khai tiếp không?

Sau bài học, người học có thể tự xây dựng checklist theo chất lượng, đặt tiêu chí đo được, đối chiếu bằng chứng, ưu tiên vấn đề và đưa ra quyết định kiến trúc có căn cứ.

## 2. Phân biệt yêu cầu chức năng, thuộc tính chất lượng và ràng buộc

| Loại yêu cầu | Trả lời câu hỏi | Ví dụ của nền tảng đặt hàng |
| --- | --- | --- |
| **Chức năng** | Hệ thống làm được việc gì? | Người dùng có thể tạo đơn, thanh toán và xem lịch sử. |
| **Thuộc tính chất lượng** | Hệ thống thực hiện chức năng đó tốt đến mức nào và trong hoàn cảnh nào? | Khi lưu lượng tăng gấp 5, 95% yêu cầu xem đơn hoàn tất trong 400 ms; không mất đơn đã xác nhận khi lỗi một node. |
| **Ràng buộc** | Những điều kiện nào buộc phải tuân theo? | Dữ liệu cá nhân chỉ lưu ở vùng được phê duyệt; ngân sách tối đa; phải dùng một giao thức tích hợp cụ thể. |
| **Giả định** | Điều gì đang được coi là đúng nhưng chưa có bằng chứng? | Đối tác thanh toán sẽ chịu được 300 request/giây và retry từ ứng dụng. |
| **Quyết định kiến trúc** | Chọn phương án nào để thỏa yêu cầu và chấp nhận đánh đổi nào? | Đặt dịch vụ API stateless sau load balancer, sử dụng hàng đợi bền vững cho xử lý nền. |

Đừng viết “phải có tính sẵn sàng cao” như một tiêu chí đạt/không đạt. Nhóm cần xác định **mức sẵn sàng mục tiêu**, khoảng thời gian tính, phạm vi dịch vụ được tính, sự cố cần chịu được và bằng chứng chứng minh.

Ví dụ: “API tạo đơn đạt SLO khả dụng 99,9% trong một tháng theo tỷ lệ request hợp lệ được phục vụ thành công” rõ ràng hơn “HA tốt”. Với tháng giả định 30 ngày, 0,1% thời gian tương đương 43,2 phút; tuy nhiên **SLO đo theo request** và **SLO đo theo thời gian** không nhất thiết cho cùng kết quả. Phải xác định công thức SLI trước khi diễn giải con số.

Cũng cần phân biệt:

- **SLI** (*Service Level Indicator*): đại lượng đo chất lượng đang quan sát, như tỷ lệ yêu cầu thành công hoặc độ trễ p95.
- **SLO** (*Service Level Objective*): mục tiêu nội bộ đặt cho SLI.
- **SLA** (*Service Level Agreement*): cam kết theo thỏa thuận, có thể bao gồm điều kiện và hậu quả khi vi phạm.
- **RTO** (*Recovery Time Objective*): thời gian tối đa mục tiêu để khôi phục dịch vụ sau sự cố.
- **RPO** (*Recovery Point Objective*): lượng dữ liệu tối đa có thể mất, thường diễn tả theo khoảng thời gian. RPO bằng 0 cho giao dịch đã xác nhận đòi hỏi cơ chế bảo toàn tương ứng, không thể suy ra từ việc có backup hằng ngày.

Tỷ lệ SLA do nhà cung cấp cloud công bố cho một dịch vụ riêng lẻ **không phải** bảo đảm khả dụng đầu-cuối cho ứng dụng được ghép từ nhiều thành phần.

## 3. Chọn nhóm thuộc tính chất lượng phù hợp

Không có một checklist cố định cho mọi kiến trúc. Nhóm cần chọn những thuộc tính quan trọng theo nghiệp vụ, người dùng, dữ liệu, phụ thuộc và mô hình vận hành.

| Thuộc tính | Điều cần quan sát | Ví dụ chỉ báo / phép kiểm chứng |
| --- | --- | --- |
| **Tính đúng đắn và toàn vẹn dữ liệu** | Kết quả nghiệp vụ có chính xác, nhất quán, không thiếu hoặc trùng? | Số giao dịch đã xác nhận thất lạc; đối soát đơn–thanh toán; kiểm tra idempotency. |
| **Khả dụng** (*availability*) | Dịch vụ có phục vụ được khi người dùng cần? | Tỷ lệ yêu cầu thành công theo khoảng đo; kịch bản mất instance/zone. |
| **Độ tin cậy và khả năng phục hồi** (*reliability/resilience*) | Có chịu lỗi, suy giảm chức năng có kiểm soát và phục hồi đúng? | Lỗi dependency, failover test, thời gian phục hồi, mất dữ liệu. |
| **Hiệu năng** (*performance*) | Có đáp ứng tốc độ và thông lượng mục tiêu? | p50/p95/p99, throughput, saturation, queue waiting time. |
| **Khả năng mở rộng** (*scalability*) | Khi tăng người dùng/tải, hệ thống tăng năng lực ra sao? | Stress test, autoscaling reaction, quota, giới hạn DB connections. |
| **Bảo mật và riêng tư** (*security/privacy*) | Tài nguyên và dữ liệu có được bảo vệ phù hợp? | Threat model, IAM, mã hóa, scan lỗ hổng, kiểm tra truy cập trái phép. |
| **Khả năng quan sát và vận hành** (*observability/operability*) | Có phát hiện, chẩn đoán, khắc phục sự cố đủ nhanh? | Dashboard SLI, alert, trace, log, runbook, diễn tập on-call. |
| **Khả năng thay đổi và bảo trì** (*maintainability/modifiability*) | Có thể sửa, nâng cấp, triển khai an toàn? | CI/CD, rollback release, kiểm thử hợp đồng, thời gian thay đổi. |
| **Khả năng tương tác** (*interoperability*) | Có tích hợp đáng tin cậy với hệ thống khác? | API contract, schema compatibility, retry/backoff, rate limit. |
| **Hiệu quả chi phí** (*cost efficiency*) | Chi phí có tương xứng với mức chất lượng? | Dự báo tải, đơn giá mỗi giao dịch, ngân sách, cost anomaly. |
| **Khả năng chuyển đổi** (*portability*) | Có thể di chuyển thành phần khi cần mà không quá tốn kém? | Danh sách API phụ thuộc nhà cung cấp, quy trình export/restore, IaC. |
| **Tính bền vững** (*sustainability*) | Có tránh lãng phí tài nguyên trong vòng đời hệ thống? | Right-sizing, autoscaling, xử lý dữ liệu không còn cần thiết. |

Các nhóm trên có quan hệ với sáu trụ cột thường dùng trong cách đánh giá **Well-Architected**: **Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, Sustainability**. Hai cách phân loại có mục đích khác nhau: thuộc tính chất lượng mô tả hành vi mong muốn của hệ thống; trụ cột giúp tổ chức đánh giá quyết định thiết kế và thực hành vận hành.

Một câu hỏi có thể thuộc nhiều nhóm. Chẳng hạn, tăng số replica cải thiện khả dụng nhưng ảnh hưởng chi phí; bật log truy cập giúp kiểm toán và điều tra nhưng tăng chi phí, đồng thời cần bảo vệ dữ liệu nhạy cảm trong log. Checklist cần ghi lại **đánh đổi**, không cố ép mỗi quyết định vào đúng một ô.

## 4. Chuyển yêu cầu mơ hồ thành kịch bản chất lượng đo được

Cách tốt để tạo checklist là viết **quality attribute scenario** gồm sáu phần:

1. **Nguồn tác động** (*source*): ai hoặc sự kiện nào tạo tình huống?
2. **Tác động** (*stimulus*): điều gì xảy ra?
3. **Môi trường** (*environment*): hệ thống ở trạng thái nào khi tác động xảy ra?
4. **Thành phần chịu ảnh hưởng** (*artifact*): API, database, hàng đợi, vùng mạng hay toàn hệ thống?
5. **Phản ứng mong muốn** (*response*): hệ thống nên làm gì?
6. **Thước đo** (*response measure*): chấp nhận kết quả dựa trên số liệu nào?

### Ví dụ A: Đột biến tải

| Thành phần | Nội dung minh họa |
| --- | --- |
| Nguồn | Ứng dụng khách và người dùng cuối |
| Tác động | Số yêu cầu xem đơn tăng gấp 5 trong vòng 2 phút |
| Môi trường | Giờ cao điểm; hệ thống đang chạy bình thường |
| Thành phần | CDN, API, cache, connection pool, PostgreSQL |
| Phản ứng | Mở rộng API, giới hạn truy cập tới DB, trả lỗi có kiểm soát khi quá tải |
| Thước đo | Trong phép thử tải đại diện: p95 dưới 400 ms, tỷ lệ lỗi hệ thống dưới 1%, không vượt giới hạn kết nối DB |

### Ví dụ B: Lỗi một Availability Zone

| Thành phần | Nội dung minh họa |
| --- | --- |
| Nguồn | Sự cố hạ tầng |
| Tác động | Một zone đang phục vụ ứng dụng ngừng hoạt động |
| Môi trường | Đang có giao dịch thanh toán và đơn hàng |
| Thành phần | Load balancer, compute, database, queue |
| Phản ứng | Chuyển tiếp lưu lượng sang thành phần khỏe; duy trì tính đúng đắn đơn hàng |
| Thước đo | Khôi phục luồng tạo đơn trong 10 phút; không mất đơn đã báo thành công; không tạo thanh toán trùng |

### Ví dụ C: Truy cập dữ liệu trái quyền

| Thành phần | Nội dung minh họa |
| --- | --- |
| Nguồn | Tài khoản workload bị cấp quyền quá rộng hoặc token bị lộ |
| Tác động | Yêu cầu đọc dữ liệu khách hàng ngoài phạm vi được phép |
| Môi trường | Production, nhiều nhóm người dùng |
| Thành phần | IAM, API, database, log audit |
| Phản ứng | Từ chối truy cập, ghi nhận sự kiện và cảnh báo có thể điều tra |
| Thước đo | Bài kiểm thử quyền âm tính bị từ chối đúng; không trả dữ liệu trái quyền; dấu vết audit đủ ID, thời điểm và ngữ cảnh, tránh lộ dữ liệu nhạy cảm |

Các con số trong ví dụ chỉ dùng để học cách viết tiêu chí; không phải chuẩn mặc định cho mọi sản phẩm. Ngưỡng thật phải do người sở hữu nghiệp vụ, kiến trúc và vận hành thống nhất, dựa trên nhu cầu và dữ liệu tải.

**Quy tắc:** Nếu checklist không chỉ rõ “đạt” nghĩa là gì, hãy quay lại viết kịch bản trước khi chấm.

## 5. Thiết kế cấu trúc của một checklist có thể sử dụng lại

Một mục checklist không nên chỉ là câu hỏi có/không. Mẫu lưu trữ phù hợp cho review thiết kế:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **ID** | Định danh ổn định, truy vết qua nhiều lần review | REL-03 |
| **Nhóm thuộc tính** | Nhóm chất lượng chịu ảnh hưởng chính | Reliability |
| **Câu hỏi/rủi ro** | Điều cần xác minh và hậu quả nếu sai | Khi database failover, API có mất đơn đã xác nhận không? |
| **Phạm vi và kịch bản** | Workload, môi trường, failure mode áp dụng | API thanh toán ở production, mất node DB chính |
| **Tiêu chí chấp nhận** | Ngưỡng và điều kiện đo | Không mất giao dịch đã xác nhận; khôi phục trong RTO đã phê duyệt |
| **Cách kiểm chứng** | Phương pháp và nguồn bằng chứng | Failover rehearsal, log giao dịch, đối soát, số liệu RTO |
| **Kết quả** | PASS / FAIL / PARTIAL / NOT_VERIFIED / N/A | NOT_VERIFIED |
| **Mức độ rủi ro** | P0, P1 hoặc P2 theo tác động nghiệp vụ | P0 |
| **Người sở hữu, hạn xử lý** | Trách nhiệm và thời điểm đóng việc | DBA và SRE trước ngày cutover |
| **Liên kết** | ADR, sơ đồ, cấu hình, kết quả test, ticket | ADR-12, TEST-DR-04 |

Nên quy định kết quả nhất quán:

- **PASS:** Có bằng chứng phù hợp với phạm vi và tiêu chí đã định; bằng chứng còn hiệu lực với phiên bản kiến trúc đang xét.
- **FAIL:** Đã kiểm chứng và thấy không đạt tiêu chí.
- **PARTIAL:** Chỉ một phần tiêu chí được đáp ứng hoặc phạm vi thử nghiệm chưa đủ.
- **NOT_VERIFIED:** Chưa có bằng chứng đủ sức kết luận, kể cả khi thiết kế “có vẻ đúng”.
- **N/A:** Không áp dụng và phải có lý do, người chấp thuận; tránh dùng N/A để bỏ qua rủi ro.

Không gộp NOT_VERIFIED vào PASS. Một mẫu kiến trúc có sơ đồ đúng nhưng chưa được thử tải, thử khôi phục hoặc kiểm tra quyền chỉ nên được ghi nhận là **đã thiết kế**, chưa phải **đã chứng minh**.

### Mẫu một mục dạng YAML

~~~yaml
id: REL-03
attribute: reliability
scope: "Production - API tạo đơn và PostgreSQL"
question: "Mất một database node có làm mất đơn đã xác nhận không?"
scenario: "Failover node chính khi có 100 giao dịch/giây"
acceptance:
  rpo: "0 cho đơn đã xác nhận"
  rto: "10 phút"
evidence_required:
  - "Báo cáo diễn tập failover"
  - "Bản đối soát trước/sau theo transaction ID"
  - "Đo thời gian phát hiện và phục hồi"
result: NOT_VERIFIED
risk: P0
owner: "Nhóm dữ liệu và SRE"
due: "Trước phê duyệt production"
decision_link: "ADR-012"
~~~

Đoạn YAML là **mẫu nội dung checklist** minh họa, không phải cấu trúc bắt buộc của kho học liệu hoặc cấu hình thực thi. Trong thực tế, có thể lưu checklist bằng spreadsheet, issue tracker hoặc công cụ review có khả năng truy vết.

## 6. Chuẩn bị đầu vào trước khi đặt câu hỏi

Checklist chỉ có giá trị khi mô tả đúng hệ thống đang được đánh giá. Tối thiểu cần thu thập:

1. **Bối cảnh nghiệp vụ:** người dùng, hành trình quan trọng, tổn thất nếu ngừng dịch vụ hoặc sai dữ liệu.
2. **Nhu cầu phi chức năng:** SLI/SLO, RTO/RPO, tải, tăng trưởng, ngân sách, mức bảo vệ dữ liệu, yêu cầu tích hợp.
3. **Kiến trúc hiện tại và dự kiến:** sơ đồ context, container/component, data flow, vùng tin cậy, tài khoản và network boundary.
4. **Danh mục tài nguyên và phụ thuộc:** DNS, CDN, load balancer, compute, database, cache, hàng đợi, dịch vụ bên thứ ba, CI/CD.
5. **Đặc tính dữ liệu:** phân loại nhạy cảm, lưu trú dữ liệu, mức nhất quán, quyền sở hữu, backup, lifecycle, luồng xóa dữ liệu.
6. **Mô hình vận hành:** on-call, dashboard, cảnh báo, quản lý thay đổi, quyền truy cập khẩn cấp, runbook, diễn tập.
7. **Bằng chứng đã có:** kết quả test, dashboard production, incident history, đánh giá bảo mật, bill, ADR và giả định còn chưa kiểm chứng.

Nếu kiến trúc mới chưa có traffic production, có thể dùng phép thử đại diện để ước lượng; phải gắn nhãn rõ **bằng chứng thử nghiệm**, không trình bày như số đo vận hành thực tế.

### Truy vết từ nghiệp vụ đến mục kiểm tra

~~~mermaid
flowchart TD
  B[Nhu cầu nghiệp vụ] --> S[Quality attribute scenario]
  S --> Q[Câu hỏi và tiêu chí checklist]
  Q --> D[Quyết định kiến trúc / ADR]
  Q --> E[Bằng chứng kiểm chứng]
  D --> T[Thiết kế / cấu hình triển khai]
  T --> E
  E --> G{Đạt tiêu chí?}
  G -->|Đạt| P[PASS, ghi phạm vi và phiên bản]
  G -->|Chưa đạt| R[Rủi ro, chủ sở hữu, phương án xử lý]
  G -->|Chưa đo được| N[NOT_VERIFIED, kế hoạch test]
  R --> Q
  N --> E
~~~

Sơ đồ nhấn mạnh tính **truy vết và vòng phản hồi**. Đánh giá kiến trúc không kết thúc ở buổi review; khi thiết kế thay đổi hoặc có bằng chứng mới, trạng thái checklist phải được cập nhật.

## 7. Bộ checklist mẫu theo các thuộc tính chất lượng

Các bảng sau là **thư viện câu hỏi khởi đầu**. Trước khi dùng trong dự án, nhóm phải điền ngưỡng cụ thể, mức rủi ro, người phụ trách và bằng chứng cho từng dòng.

### 7.1. Tính đúng đắn, nhất quán và toàn vẹn dữ liệu

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| DATA-01 | Với giao dịch quan trọng, nguồn dữ liệu nào có thẩm quyền và phạm vi transaction ở đâu? | Data flow, ownership, schema, mô tả transaction boundary. |
| DATA-02 | Một thao tác retry có thể tạo đơn/thanh toán/hóa đơn trùng không? | Test idempotency, unique constraint, correlation ID. |
| DATA-03 | Khi ghi DB thành công nhưng gửi event thất bại, làm sao sự kiện không bị mất? | Transactional outbox hoặc giao thức tương đương, test lỗi. |
| DATA-04 | Có xử lý được event trễ, gửi lại, sai thứ tự và bản ghi xóa không? | Consumer contract, test retry/order/dead-letter. |
| DATA-05 | Dữ liệu đọc có thể trễ tới đâu và các nghiệp vụ nào bắt buộc đọc trạng thái mới? | Sơ đồ replica/cache, consistency requirement, test. |
| DATA-06 | Khi migration hoặc restore, làm sao đối soát đủ bản ghi và kết quả nghiệp vụ? | Watermark, so khóa, tổng nghiệp vụ, checksum, báo cáo sai lệch. |

**Điểm dừng bắt buộc điển hình:** Nếu đã trả lời “thanh toán thành công” nhưng thiết kế cho phép mất bản ghi thanh toán trong một kịch bản lỗi nằm trong phạm vi yêu cầu RPO = 0, cần xử lý trước khi chấp nhận thiết kế.

### 7.2. Khả dụng, độ tin cậy và khôi phục

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| REL-01 | SLI/SLO của các luồng người dùng quan trọng đã được định nghĩa chính xác chưa? | SLO document: numerator, denominator, exclusions, cửa sổ đo. |
| REL-02 | Có single point of failure ở ingress, compute, database hoặc dependency không? | Sơ đồ failure domain, kết quả kiểm tra AZ/node failure. |
| REL-03 | Backup có khôi phục được và RPO/RTO có đạt khi diễn tập không? | Restore test, failover exercise, số liệu thực tế. |
| REL-04 | Timeout, retry, exponential backoff, jitter, circuit breaker được đặt ở đâu? | Cấu hình, test sự cố dependency và retry storm. |
| REL-05 | Khi mất một vùng/zone hoặc cloud service, hệ thống suy giảm chức năng ra sao? | Kịch bản fault injection, danh sách chức năng ưu tiên. |
| REL-06 | Mất kết nối với dịch vụ bên ngoài có gây tắc toàn bộ hệ thống không? | Bulkhead, queue, fallback policy, runbook xử lý backlog. |
| REL-07 | Có kiểm soát triển khai gây lỗi: canary, blue/green, rollback ứng dụng và dữ liệu? | Release pipeline, rehearsal, chiến lược tương thích schema. |

**Lưu ý:** Multi-AZ thường nhằm ứng phó lỗi trong một region; nếu yêu cầu phục hồi khi **mất region**, cần chiến lược dự phòng riêng, xử lý replication, DNS/routing và tính nhất quán dữ liệu. Có bản sao ở region khác không tự động bảo đảm RPO bằng 0.

### 7.3. Hiệu năng và khả năng mở rộng

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| PERF-01 | Đã mô tả tải bình thường, đỉnh tải và tốc độ tăng tải theo hành trình người dùng chưa? | Traffic profile, giả định, business forecast. |
| PERF-02 | Đã có mục tiêu latency p95/p99, throughput và tỷ lệ lỗi cho từng API quan trọng chưa? | SLO, performance test plan. |
| PERF-03 | Từng tầng có ngưỡng saturation và giới hạn tài nguyên nào? | CPU/memory, DB IOPS, connections, quota, queue depth. |
| PERF-04 | Autoscaling phản ứng đủ nhanh và có nguy cơ tạo đột biến vào DB không? | Load/ramp test, scaling logs, connection pool metrics. |
| PERF-05 | Cache, CDN, pagination và index có phù hợp mẫu truy cập thực tế không? | Query plan, cache hit ratio, profiling, test invalidation. |
| PERF-06 | Khi lượng tải vượt thiết kế, hệ thống có cơ chế backpressure, rate limit và ưu tiên chức năng không? | Stress test, queue limit, load-shedding policy. |
| PERF-07 | Có kiểm thử tải đồng thời trên các đường API, event consumer và batch không? | End-to-end benchmark ở dataset đại diện. |

**Lưu ý:** Dùng CPU trung bình để kết luận hiệu năng thường không đủ. Với API, cần theo dõi độ trễ đuôi (p95/p99), lỗi và giới hạn tầng phụ thuộc. Mở rộng compute có thể **làm database quá tải nhanh hơn** nếu không quản lý connection pool và concurrency.

### 7.4. Bảo mật, quyền riêng tư và tuân thủ

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| SEC-01 | Đã xác định tài sản quan trọng, trust boundary và các luồng dữ liệu nhạy cảm chưa? | Threat model, data flow, phân loại dữ liệu. |
| SEC-02 | Có nguyên tắc quyền tối thiểu cho người dùng, dịch vụ, CI/CD và quyền khẩn cấp không? | IAM policy review, access test, quy trình cấp/thu hồi quyền. |
| SEC-03 | Dịch vụ nội bộ/database có bị truy cập từ Internet ngoài ý muốn không? | Network topology, firewall/SG/NSG, scan và test kết nối. |
| SEC-04 | Dữ liệu được mã hóa khi truyền và lưu, khóa/secret được quản lý và luân chuyển thế nào? | TLS settings, KMS/Key Vault, secret rotation test. |
| SEC-05 | API xử lý authentication, authorization, validation và rate limiting đúng chưa? | Security test, test phân quyền theo resource/tenant. |
| SEC-06 | Log/traces có lộ token, thông tin cá nhân, bí mật hoặc dữ liệu tài chính không? | Log review, masking, retention/access policy. |
| SEC-07 | Các ràng buộc về vị trí dữ liệu, lưu giữ, xóa và khả năng kiểm toán được đáp ứng chưa? | Data inventory, location policy, retention/deletion test. |
| SEC-08 | Supply chain có scan dependency/image, ký artifact và kiểm soát provenance/CI permissions không? | Pipeline policy, scan report, deployment attestation nếu áp dụng. |

Đừng lấy việc dịch vụ cloud cung cấp mã hóa hay IAM làm bằng chứng rằng ứng dụng đã an toàn. Theo mô hình trách nhiệm chia sẻ, đội ứng dụng vẫn phải cấu hình quyền, luồng dữ liệu và phòng thủ phù hợp.

### 7.5. Khả năng vận hành, quan sát và thay đổi

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| OPS-01 | Ai là owner và on-call cho từng thành phần, dependency, dữ liệu và SLO? | RACI/on-call roster, runbook. |
| OPS-02 | Có dashboard hiển thị tỷ lệ lỗi, latency, saturation và các tín hiệu nghiệp vụ không? | Dashboard, metrics catalog, alert rule. |
| OPS-03 | Có correlation ID/trace để truy từ API tới DB, queue và worker không? | Trace mẫu, distributed trace coverage. |
| OPS-04 | Cảnh báo có ngưỡng, người nhận, mức độ nghiêm trọng và hành động tiếp theo không? | Alert inventory, kết quả diễn tập sự cố. |
| OPS-05 | Có quy trình triển khai, rollback, feature flag và tương thích schema để giảm rủi ro release không? | CI/CD, deployment history, rehearsal. |
| OPS-06 | Có dùng IaC, review cấu hình, phát hiện drift và quản lý secrets ở pipeline không? | Repository IaC, plan review, drift detection evidence. |
| OPS-07 | Có thực hiện postmortem và theo dõi hành động phòng ngừa sau sự cố không? | Incident record, backlog cải tiến, owner và hạn xử lý. |

**Quan sát được** khác với **có log**: nếu log không có request ID, metric không phân biệt được endpoint hoặc cảnh báo chỉ báo CPU cao mà không gắn với tác động người dùng, thời gian chẩn đoán vẫn có thể kéo dài.

### 7.6. Chi phí và tính bền vững

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| COST-01 | Dự toán đã bao gồm compute, DB, storage, backup, NAT, egress, log và dữ liệu liên vùng chưa? | Cost model, giả định tải và bảng giá theo region. |
| COST-02 | Có xác định đơn vị chi phí hữu ích cho nghiệp vụ không? | Chi phí mỗi 1.000 yêu cầu, mỗi đơn, mỗi tenant hoặc mỗi GB xử lý. |
| COST-03 | Cấu hình dự phòng và autoscaling có xung đột ngân sách không? | Peak scenario, cost envelope, capacity plan. |
| COST-04 | Có tag/label, phân bổ chi phí, budget alert và người chịu trách nhiệm không? | Billing dashboard, policy tags, alert test. |
| COST-05 | Có cơ chế lifecycle cho object/log/backup, môi trường thử nghiệm và tài nguyên nhàn rỗi không? | Retention policy, lifecycle rules, inventory. |
| COST-06 | Đã cân nhắc hiệu quả tài nguyên cùng yêu cầu tin cậy chưa? | Right-sizing, utilization trend, policy tắt tài nguyên không cần thiết. |

Tối ưu chi phí không có nghĩa là giảm replica một cách máy móc. Cần kiểm tra chất lượng đầu ra khi thay đổi mức dự phòng và khả năng mở rộng. Tính bền vững cũng không nên dùng để viện cớ cắt giảm tài nguyên bảo vệ dữ liệu hoặc giảm khả năng phục hồi thiết yếu.

### 7.7. Khả năng tương tác, thay đổi và chuyển nền tảng

| ID | Câu hỏi phải trả lời | Bằng chứng gợi ý |
| --- | --- | --- |
| INT-01 | API, event schema và hợp đồng dữ liệu có versioning và chính sách tương thích không? | OpenAPI/AsyncAPI, contract tests, deprecation plan. |
| INT-02 | Có kế hoạch xử lý quota, timeout và retry của đối tác không? | Integration tests, rate-limit model, DLQ/reconciliation. |
| MOD-01 | Các bounded context có giao diện rõ, giảm thay đổi lan truyền không? | Component diagram, dependency map, lịch sử thay đổi. |
| MOD-02 | Hạ tầng/cấu hình có tái tạo được và có quy trình kiểm tra thay đổi không? | IaC, pipeline, reproducibility test. |
| PORT-01 | Các phụ thuộc độc quyền cloud hoặc định dạng dữ liệu khó xuất đã được ghi nhận chưa? | Dependency inventory, ADR, exit plan theo mức cần thiết. |

**Portability không phải mục tiêu bắt buộc của mọi hệ thống.** Có thể chủ động dùng dịch vụ cloud đặc thù nếu lợi ích hơn chi phí lock-in; checklist phải ghi được quyết định và phương án ứng phó, thay vì buộc dùng mẫu kiến trúc chung cho mọi trường hợp.

## 8. Thêm tiêu chí chấp nhận, bằng chứng và mức ưu tiên

Checklist thường thất bại vì câu hỏi quá rộng: “Có backup không?”, “Có bảo mật không?”, “Có monitoring không?”. Cần làm rõ **bao nhiêu**, **trong tình huống nào**, **đã thử bằng cách nào**.

| Câu hỏi chung | Phiên bản có thể kiểm chứng | Bằng chứng phù hợp |
| --- | --- | --- |
| Có backup? | Có thể khôi phục PostgreSQL về thời điểm được yêu cầu, trong RTO/RPO đã duyệt? | Restore rehearsal có số liệu thời gian, đối soát dữ liệu. |
| Có auto scale? | Khi traffic tăng 5 lần trong 2 phút, p95 và lỗi có nằm trong SLO? | Load test, thời điểm scale-out, DB connections, p95. |
| Có bảo mật dữ liệu? | Workload A có bị chặn khi đọc tenant B; log không chứa token? | Test quyền âm tính, log review, IAM config. |
| Có monitoring? | Khi API lỗi 5xx vượt ngưỡng, alert đến đúng người và chỉ ra runbook? | Alert simulation, alert delivery time, runbook link. |
| Có tối ưu chi phí? | Tổng chi phí cho tải dự kiến và tải đỉnh có nằm trong khung ngân sách? | TCO estimate với giả định, cost anomaly/budget alerts. |

### Xếp mức độ rủi ro

Dùng ba mức đơn giản làm ví dụ:

- **P0 — Chặn phê duyệt:** có nguy cơ tổn hại dữ liệu trọng yếu, vi phạm ràng buộc bắt buộc, truy cập trái phép nghiêm trọng hoặc không có phương án khôi phục phù hợp cho luồng cốt lõi. P0 FAIL hoặc P0 NOT_VERIFIED chưa thể được coi là đã giải quyết.
- **P1 — Cần xử lý theo hạn rõ ràng:** gây suy giảm SLO, gián đoạn vận hành đáng kể hoặc tăng chi phí lớn, nhưng có biện pháp giảm thiểu và người chịu trách nhiệm chấp thuận trong phạm vi cụ thể.
- **P2 — Cải tiến:** chưa tối ưu, có thể đưa vào backlog nếu rủi ro còn lại được chấp nhận rõ ràng.

P0/P1/P2 là cách phân loại minh họa, không phải quy định chung của Well-Architected. Tổ chức có thể dùng severity khác; cần xác định ý nghĩa và thẩm quyền phê duyệt trước khi review.

### Chấm mức độ hoàn thành mà không che lấp rủi ro

Có thể đo **tỷ lệ mục áp dụng đã có bằng chứng PASS**:

~~~text
Coverage = Số mục PASS / Số mục áp dụng × 100%
~~~

Ở đây “mục áp dụng” gồm PASS, FAIL, PARTIAL và NOT_VERIFIED; chỉ loại N/A có lý do hợp lệ. Chẳng hạn 18 PASS trên 24 mục áp dụng là 75% coverage. **Đây là chỉ số tiến độ đánh giá, không phải chỉ số mức an toàn.** Một thiết kế có 95% PASS vẫn không nên được phê duyệt nếu còn P0 liên quan mất dữ liệu hoặc phân quyền.

Thay vì chỉ xem phần trăm, báo cáo phải hiển thị riêng: số P0 chưa đóng, số P1 chưa đóng, bằng chứng quá cũ, các giả định trọng yếu và người chấp nhận rủi ro. Khi tiêu chí là điều kiện bắt buộc, áp dụng **hard gate** trước khi tính bất kỳ điểm tổng hợp nào.

## 9. Ví dụ điền checklist cho một hệ thống đặt hàng cloud

### 9.1. Bối cảnh kiến trúc

Một doanh nghiệp chuyển ứng dụng đặt hàng sang cloud. Kiến trúc dự kiến:

- HTTPS qua CDN/WAF và load balancer tới dịch vụ API Java stateless.
- Managed PostgreSQL lưu đơn hàng và thanh toán; object storage lưu hóa đơn.
- Hàng đợi và worker xử lý email, webhook; transactional outbox bảo đảm event được phát từ giao dịch đã ghi.
- API chạy nhiều instance qua nhiều zone khi dịch vụ hỗ trợ; database có cấu hình HA và backup.
- Telemetry gồm metrics, traces, log có correlation ID; IAM theo từng workload.

Yêu cầu **giả định cho bài tập**: p95 của API tạo đơn dưới 500 ms ở tải mục tiêu 200 yêu cầu/giây; không mất đơn đã xác nhận; RTO 30 phút cho sự cố thuộc phạm vi kế hoạch; dự toán chi phí trong ngân sách đã được duyệt. Kịch bản lớn như mất cả region hoặc thất bại của nhà cung cấp thanh toán cần xác định yêu cầu riêng.

### 9.2. Bảng kết quả review minh họa

| ID | Tiêu chí và bằng chứng quan sát | Kết quả | Ưu tiên | Việc cần làm |
| --- | --- | --- | --- | --- |
| DATA-02 | Có khóa idempotency cho API tạo đơn, nhưng chưa chạy test retry sau timeout. | NOT_VERIFIED | P0 | Bổ sung test gửi lặp và xác minh không phát sinh đơn/thanh toán trùng. |
| REL-02 | API nhiều instance; database đã có HA theo thiết kế nhưng chưa diễn tập failover. | PARTIAL | P1 | Thử lỗi node/zone trong phạm vi hỗ trợ, đo tác động với luồng tạo đơn. |
| REL-03 | Backup mỗi ngày; RPO giao dịch đã xác nhận yêu cầu bằng 0 nhưng chưa có giải pháp được chứng minh cho failover/cutover. | FAIL | P0 | Thiết kế cơ chế bảo toàn, kiểm chứng transaction và phục hồi; không suy RPO = 0 từ backup hằng ngày. |
| PERF-02 | Load test 200 request/giây: p95 460 ms, lỗi hệ thống 0,3% theo phép đo đại diện. | PASS | P1 | Ghi phạm vi, thời điểm, dữ liệu test; bổ sung test peak và endurance riêng. |
| SEC-02 | IAM workload tách biệt; một service account còn có quyền quản trị database rộng hơn nhu cầu. | FAIL | P0 | Thu hẹp quyền và test các quyền bị từ chối. |
| OPS-02 | Có dashboard latency/error, chưa có cảnh báo và runbook lỗi outbox backlog. | PARTIAL | P1 | Thêm alert queue age/outbox lag và diễn tập xử lý. |
| COST-01 | Có dự toán compute/DB nhưng chưa tính egress, log retention và backup. | PARTIAL | P1 | Bổ sung TCO theo tải thường, đỉnh tải và tăng trưởng. |
| PORT-01 | Phụ thuộc API object storage đã được ghi trong ADR; tổ chức chấp nhận lock-in hiện tại. | PASS | P2 | Đặt mốc xem xét lại khi thay đổi chiến lược đa cloud. |

**Kết luận ví dụ:** Chưa thể ra quyết định **GO** vì còn DATA-02, REL-03 và SEC-02 ở mức P0 chưa đạt hoặc chưa được chứng minh. Số mục PASS hay độ trễ đã đạt không thể bù trừ rủi ro mất giao dịch và cấp quyền quá rộng.

Một review đúng phải phân biệt:

- **Quan sát:** “Tại phép thử tải X, p95 đo được 460 ms ở 200 request/giây”.
- **Suy luận có điều kiện:** “Có thể đạt mục tiêu hiệu năng trong phạm vi cấu hình và dataset đã thử”.
- **Điểm chưa biết:** “Chưa có bằng chứng cho ngày cao điểm, failover hoặc data skew”.
- **Hành động:** “Đội hiệu năng đo lại ở tải đỉnh; đội dữ liệu cung cấp diễn tập khôi phục”.
- **Quyết định:** “Chưa phê duyệt production khi còn P0”.

## 10. Xử lý các đánh đổi giữa thuộc tính chất lượng

Một kiến trúc tốt không cực đại hóa mọi thuộc tính cùng lúc. Checklist nên giúp lộ ra quyết định và đánh đổi có thể xem xét:

| Lựa chọn | Lợi ích thường kỳ vọng | Đánh đổi/rủi ro cần đánh giá |
| --- | --- | --- |
| Thêm replica và multi-zone | Tăng khả dụng và chịu lỗi | Thêm chi phí, cơ chế failover, khả năng dữ liệu trễ. |
| Dùng cache | Giảm độ trễ và tải database | Invalidations, dữ liệu cũ, vận hành cache, quyền riêng tư. |
| Tăng tính nhất quán mạnh | Giảm bất đồng dữ liệu với giao dịch nhạy cảm | Có thể tăng độ trễ, giảm khả dụng khi chia cắt mạng. |
| Chuyển xử lý sang hàng đợi | Giảm coupling và hấp thụ spike | Eventual consistency, retry, ordering, backlog, idempotency. |
| Dùng dịch vụ managed/serverless | Giảm vận hành OS và một phần hạ tầng | Quota, cold start, pricing theo request, lock-in, giới hạn cấu hình. |
| Tăng observability/log retention | Chẩn đoán sự cố và kiểm toán tốt hơn | Chi phí lưu log, bảo vệ dữ liệu nhạy cảm, cardinality metrics. |
| Tăng bảo vệ bằng network/private endpoint | Thu hẹp bề mặt tấn công | Routing, DNS, chi phí egress/NAT, phức tạp vận hành. |

Khi hai mục checklist xung đột, đừng đánh dấu một mục là “không áp dụng” để loại xung đột. Hãy ghi thành **Architecture Decision Record (ADR)** với: yêu cầu ưu tiên, các phương án, dữ liệu thử nghiệm, tác động tới từng thuộc tính, rủi ro còn lại và người phê duyệt.

Ví dụ: mục tiêu p95 rất thấp và yêu cầu luôn đọc dữ liệu mới nhất có thể xung đột khi dùng cache. Thay vì chọn theo cảm tính, phân nhóm endpoint: tra cứu danh mục sản phẩm có thể cho phép stale dữ liệu ngắn hạn; số dư hoặc trạng thái thanh toán có thể phải đọc nguồn dữ liệu có thẩm quyền. Thiết kế và checklist cần phản ánh **chính sách nhất quán theo nghiệp vụ**.

## 11. Quy trình tổ chức một buổi đánh giá kiến trúc

### Giai đoạn 1: Xác định phạm vi và người tham gia

Chủ trì review phải biết đây là **đánh giá ý tưởng**, **đánh giá trước production**, **đánh giá sau sự cố** hay **đánh giá định kỳ**. Độ sâu bằng chứng khác nhau theo giai đoạn. Mời đúng người: đại diện nghiệp vụ, kiến trúc sư, chủ ứng dụng, SRE/vận hành, chuyên gia dữ liệu, an ninh và tài chính cloud khi cần.

Đầu ra là danh sách luồng nghiệp vụ cần bảo vệ, ranh giới hệ thống và chất lượng nào có ưu tiên cao.

### Giai đoạn 2: Chốt kịch bản và ngưỡng

Với mỗi thuộc tính quan trọng, viết ít nhất một tình huống **bình thường**, **tải đỉnh** hoặc **sự cố** phù hợp. Chốt cách đo SLI/SLO, phạm vi RTO/RPO, giới hạn chi phí và điều kiện pháp lý/bảo mật. Ghi rõ các giả định chưa được chứng minh.

Đầu ra là danh sách tình huống cùng tiêu chí có thể kiểm thử, được các bên đồng ý.

### Giai đoạn 3: Điền checklist kèm bằng chứng

Mỗi chủ sở hữu tự đánh giá nhưng review chéo những mục P0/P1. Không chỉ nhìn slide hoặc sơ đồ: yêu cầu cấu hình IAM/network, test report, dashboard, query plan, runbook, hóa đơn mô phỏng và bằng chứng restore tùy mục.

Ghi rõ **phiên bản kiến trúc**, ngày đo và môi trường. Bằng chứng từ sandbox không mặc nhiên chứng minh production.

### Giai đoạn 4: Phân tích failure mode và quyết định

Chọn vài điểm rủi ro cao để “đi bộ qua tình huống” (*scenario walkthrough*): mất zone, timeout đối tác, database failover, quá hạn queue, lộ service account, tăng tải bất ngờ. Với từng bước, hỏi: lỗi được phát hiện ở đâu, ai xử lý, dữ liệu còn đúng không, ai có quyền dừng triển khai?

Phân loại P0/P1/P2; ghi vấn đề cần sửa, biện pháp tạm, chủ sở hữu, hạn hoàn thành và rủi ro còn lại.

### Giai đoạn 5: Phê duyệt có điều kiện và theo dõi

Quyết định review nên là một trong:

| Quyết định | Điều kiện |
| --- | --- |
| **GO** | Các điều kiện bắt buộc đã đạt; bằng chứng đủ và phạm vi được hiểu rõ. |
| **GO có điều kiện** | Chỉ còn rủi ro mà chính sách cho phép chấp nhận tạm, có biện pháp giảm thiểu, người chấp thuận và hạn đóng. Không dùng cho P0 bị chính sách xác định là blocker. |
| **NO-GO** | Có điều kiện bắt buộc thất bại, thiếu bằng chứng trọng yếu, hoặc rủi ro không được chấp thuận. |

Không dùng chữ ký review một lần làm bằng chứng vô thời hạn. Thay đổi dữ liệu, phiên bản database, topology network, traffic profile hoặc integration quan trọng có thể làm mất hiệu lực bằng chứng trước đó.

### Mẫu báo cáo review

~~~text
Hệ thống / phiên bản kiến trúc:
Ngày review / loại review:
Người tham gia:
Luồng nghiệp vụ quan trọng:
SLO / RTO / RPO / ngân sách / ràng buộc bảo mật:
Tổng mục áp dụng:
PASS / FAIL / PARTIAL / NOT_VERIFIED / N/A:
P0 chưa đóng (ID, rủi ro, owner, hạn):
P1 chưa đóng (ID, phương án giảm thiểu, owner, hạn):
Các giả định quan trọng:
Bằng chứng / ADR / test report:
Quyết định: GO | GO có điều kiện | NO-GO
Người có thẩm quyền và ngày phê duyệt:
Mốc đánh giá lại:
~~~

## 12. Kiểm chứng checklist theo giai đoạn vòng đời

### Khi mới thiết kế

Chủ yếu dựa trên yêu cầu, threat model, sơ đồ, ADR, kiến trúc tham chiếu và phân tích failure mode. Những mục cần đo tải hoặc thử lỗi nên ở trạng thái **NOT_VERIFIED**, kèm kế hoạch kiểm chứng.

### Khi thực hiện proof of concept

Dựng lát cắt đủ đại diện qua ingress → compute → dữ liệu → queue/worker → telemetry. Thử một số kịch bản ưu tiên: lỗi kết nối DB, xử lý trùng event, autoscaling, quyền IAM tối thiểu, khôi phục backup. Ghi rõ giới hạn POC như dataset nhỏ, traffic giả lập hoặc region khác.

### Trước production

Cần bằng chứng sát môi trường thực hơn: test hợp đồng, kiểm thử tải, backup restore, incident drill, cấu hình policy, giám sát và cảnh báo, cost envelope. Đối chiếu phiên bản triển khai/IaC với phiên bản được review.

### Trong vận hành

Dùng số liệu SLI/SLO, incident, cost trend, vulnerability findings, capacity và thay đổi workload để kiểm tra lại rủi ro. Checklist định kỳ có thể tập trung vào thay đổi, nhưng không được mất các yêu cầu bất biến như bảo vệ dữ liệu, quyền riêng tư và khả năng phục hồi.

## 13. Những sai lầm khiến checklist thiếu giá trị

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Checklist có hàng trăm câu hỏi giống nhau cho mọi dự án | Tốn công, người đánh giá chỉ tick cho xong | Dùng thư viện câu hỏi, chọn theo hành trình và rủi ro của hệ thống. |
| Viết “có/không” mà không có ngưỡng | Không phân biệt cấu hình tồn tại với chất lượng đạt yêu cầu | Gắn kịch bản, SLI/SLO, phạm vi và bằng chứng. |
| Chấp nhận hình kiến trúc hoặc lời khẳng định làm bằng chứng PASS | Chưa biết thiết kế chạy ra sao khi lỗi hoặc tải thật | Giữ NOT_VERIFIED đến khi test/measurement phù hợp. |
| Gộp mọi mục vào điểm tổng và bỏ qua blocker | P0 có thể bị che bởi nhiều mục dễ đạt | Tách hard gate, công bố P0/P1 chưa đóng. |
| Không ghi rõ ai xử lý | Rủi ro nằm mãi trên báo cáo | Gắn owner, hạn, cách xác minh việc đã sửa. |
| Bỏ qua queue, batch và hệ thống bên thứ ba | Tính đúng đắn đầu-cuối không được bảo đảm | Theo dõi toàn bộ business flow và các integration boundary. |
| Xem SLA của cloud là SLO ứng dụng | SLA không tính toàn bộ dependency/ứng dụng | Đo end-to-end và tính failure domain thực. |
| Đánh giá một lần rồi không xem lại | Kết luận lỗi thời sau thay đổi tải, tính năng hay topology | Đặt trigger đánh giá lại theo thay đổi và sự cố. |
| Nhầm N/A với “chưa làm” | Rủi ro bị xóa khỏi phạm vi | N/A cần giải thích; chưa có bằng chứng là NOT_VERIFIED. |

## 14. Bài tập thực hành

Một nền tảng học trực tuyến triển khai trên cloud có:

- Frontend sau CDN/WAF; API Java chạy container tự mở rộng; PostgreSQL managed lưu bài làm và điểm.
- Object storage lưu tệp nộp; queue và worker chấm tự động; nhà cung cấp ngoài gửi email và SMS.
- Bình thường 200 yêu cầu/giây; trong kỳ thi, đỉnh có thể gấp 8 lần. Mọi bài đã được hệ thống xác nhận nộp phải được bảo toàn.
- Yêu cầu minh họa: API nộp bài có p95 dưới 600 ms khi đạt tải mục tiêu, thời gian phục hồi sự cố mất một zone dưới 20 phút, ngân sách hằng tháng không vượt ngưỡng được nghiệp vụ phê duyệt.
- Có hai nhóm người dùng: học viên chỉ đọc bài của chính mình; giảng viên được xem bài và điểm trong lớp mình phụ trách.

Hãy lập checklist với **ít nhất 15 mục**, bao phủ tính đúng đắn dữ liệu, reliability, performance/scalability, security/privacy, observability/operability và cost. Với mỗi mục, điền ID, câu hỏi, tình huống, ngưỡng, bằng chứng cần thu thập, mức ưu tiên và người phụ trách.

Tiếp đó, giả định nhóm kỹ thuật cung cấp các bằng chứng sau:

1. Ở 200 yêu cầu/giây, p95 đo được 420 ms; chưa có test ở tải gấp 8 lần.
2. Backup PostgreSQL chạy hằng ngày, chưa diễn tập restore.
3. API nộp bài có idempotency key, nhưng worker chấm chưa chống xử lý trùng sau retry.
4. Mỗi ứng dụng có service account riêng, nhưng giảng viên vẫn có thể gọi API đọc điểm của lớp khác nếu biết ID.
5. Dashboard có CPU và lỗi HTTP, chưa có metric về số bài đã nhận, số bài chưa chấm hoặc tuổi backlog.
6. Chi phí đã tính compute và database, chưa tính object storage, egress, logs và chế độ tăng tải kỳ thi.

**Yêu cầu đầu ra của bài tập:**

- Chấm từng mục thành PASS, FAIL, PARTIAL, NOT_VERIFIED hoặc N/A, ghi rõ bằng chứng tương ứng.
- Chỉ ra các P0 khiến kiến trúc chưa đủ điều kiện **GO**. Giải thích vì sao độ trễ đã đạt ở tải thường không chứng minh đạt ở tải thi.
- Viết hai quality attribute scenarios đo được: một cho peak load; một cho sự cố database hoặc mất zone.
- Chọn ba phép thử ưu tiên nhất và nêu kết quả nào được coi là đạt.
- Đề xuất một ADR ghi nhận đánh đổi giữa giữ thêm compute dự phòng và mục tiêu tiết kiệm chi phí.
- Lập báo cáo review cuối cùng gồm quyết định, người chịu trách nhiệm, thời hạn và điều kiện đánh giá lại.

### Hướng dẫn tự đánh giá

Bài làm tốt cần chứng minh ba điểm. Thứ nhất, tiêu chí kiểm chứng gắn với **hành trình người dùng quan trọng**, đặc biệt bài đã xác nhận nộp và việc giảng viên không được truy cập dữ liệu ngoài lớp. Thứ hai, mức PASS có **bằng chứng phù hợp**; những gì chưa thử như tải đỉnh hoặc khôi phục vẫn được ghi nhận là chưa kiểm chứng. Thứ ba, báo cáo đưa ra **quyết định có căn cứ** và backlog xử lý được, thay vì chỉ liệt kê rủi ro chung chung.

## 15. Kết luận phương pháp

Checklist theo thuộc tính chất lượng là cầu nối từ yêu cầu nghiệp vụ đến quyết định kiến trúc có thể thử nghiệm. Quy trình nhất quán là **chọn luồng quan trọng → xác định thuộc tính và kịch bản → đặt ngưỡng → thiết kế câu hỏi → thu bằng chứng → phân loại rủi ro → ra quyết định → đánh giá lại**.

Một kiến trúc “Well-Architected” không phải kiến trúc có nhiều dịch vụ cloud hay có bảng checklist được tick kín. Đó là thiết kế mà nhóm hiểu được hành vi của hệ thống trong các điều kiện quan trọng, có bằng chứng cho các cam kết, biết rõ đánh đổi và chủ động xử lý những rủi ro chưa chấp nhận được.
