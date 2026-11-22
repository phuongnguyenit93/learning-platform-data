# Vai trò kiến trúc sư và sự phối hợp với phát triển, bảo mật, vận hành

## 1. Kiến trúc sư giải quyết vấn đề gì?

Thiết kế kiến trúc ứng dụng đám mây không bắt đầu bằng câu hỏi “nên dùng dịch vụ cloud nào?”, mà bắt đầu bằng **yêu cầu nghiệp vụ, các ràng buộc và những đánh đổi cần chấp nhận**. Một ứng dụng có thể chạy được trên một máy chủ nhưng vẫn chưa đáp ứng yêu cầu về khả năng phục hồi, an toàn dữ liệu, khả năng mở rộng, chi phí hoặc khả năng vận hành lâu dài.

**Kiến trúc sư giải pháp (solution architect)** có trách nhiệm tạo ra và duy trì bức tranh kỹ thuật tổng thể: chuyển mục tiêu nghiệp vụ thành các quyết định thiết kế có lý do, thống nhất ranh giới giữa các thành phần và bảo đảm những quyết định đó có thể triển khai, kiểm chứng, vận hành. Trong một tổ chức, chức năng này có thể do một kiến trúc sư chuyên trách, principal engineer hoặc tech lead đảm nhận; chức danh không quyết định toàn bộ quyền hạn.

Ví dụ, yêu cầu “khách hàng phải đặt chỗ thành công ngay cả vào giờ cao điểm” dẫn tới một chuỗi câu hỏi:

- “Thành công” được đo bằng tỷ lệ yêu cầu hợp lệ hoàn tất, thời gian phản hồi hay tỷ lệ không đặt trùng chỗ?
- Lưu lượng bình thường và đỉnh là bao nhiêu? Đỉnh có thể kéo dài bao lâu?
- Dữ liệu đặt chỗ phải nhất quán đến mức nào? Điều gì xảy ra nếu dịch vụ gửi thông báo bị lỗi?
- Hệ thống phải phục hồi trong bao lâu, được phép mất tối đa bao nhiêu dữ liệu?
- Ngân sách, năng lực đội ngũ, khu vực triển khai và nghĩa vụ bảo vệ dữ liệu là gì?

Kiến trúc sư cùng các bên liên quan biến những câu hỏi này thành yêu cầu có thể đo lường, đề xuất phương án, nêu rõ đánh đổi và ghi lại quyết định. Kiến trúc không chỉ là một sơ đồ; nó là **tập hợp các quyết định, giới hạn và bằng chứng cho thấy hệ thống đáp ứng mục tiêu**.

### Kết quả cần nắm sau bài học

Sau bài này, bạn có thể:

1. Giải thích trách nhiệm và giới hạn của vai trò kiến trúc sư trong vòng đời ứng dụng đám mây.
2. Phân biệt phần việc của kiến trúc sư với nhóm phát triển, bảo mật và vận hành, đồng thời nhận ra trách nhiệm chung giữa họ.
3. Tổ chức một quyết định kiến trúc có tham gia của các nhóm liên quan, nêu được lý do và hệ quả của quyết định.
4. Đánh giá một phương án dựa trên độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 2. Trách nhiệm cốt lõi của kiến trúc sư

| Trách nhiệm | Câu hỏi cần trả lời | Đầu ra có thể kiểm chứng |
|---|---|---|
| Hiểu nghiệp vụ và ràng buộc | Hệ thống tạo giá trị gì? Điều gì bắt buộc phải đúng? | Mục tiêu, luồng nghiệp vụ quan trọng, giả định và các giới hạn đã được xác nhận |
| Chuyển yêu cầu thành thuộc tính chất lượng | Cần nhanh, an toàn, sẵn sàng và dễ vận hành đến mức nào? | Chỉ tiêu có thể đo: độ trễ, tải đỉnh, SLO, RPO/RTO, ngân sách |
| Đề xuất kiến trúc tổng thể | Đâu là ranh giới thành phần, đường đi dữ liệu, điểm tích hợp và điểm lỗi? | Sơ đồ hệ thống, phương án triển khai, luồng dữ liệu và các lựa chọn thay thế |
| Ra quyết định có cân nhắc đánh đổi | Vì sao chọn phương án A thay vì B? Khi nào cần xem lại? | Architecture Decision Record (ADR), giả định, rủi ro và tiêu chí thay đổi |
| Căn chỉnh với phát triển, bảo mật, vận hành | Phương án có làm được, bảo vệ được, quan sát được và khôi phục được không? | Thiết kế được phản biện, kế hoạch thử nghiệm, tiêu chí sẵn sàng vận hành |
| Theo sát thực tế sau triển khai | Số liệu production có xác nhận giả định ban đầu không? | Kết quả đo, cải tiến, ADR cập nhật hoặc quyết định thay thế |

Kiến trúc sư không nhất thiết trực tiếp viết mọi dòng mã, vận hành mọi máy chủ hay phê duyệt mọi thay đổi. Tuy nhiên, họ phải hiểu đủ sâu các hệ quả của những lĩnh vực này để thiết kế có thể trở thành một hệ thống thực tế. Kiến trúc tốt là công việc **liên tục và có phản hồi**, không phải bản vẽ được hoàn thành một lần ở đầu dự án.

### Từ yêu cầu chức năng đến yêu cầu phi chức năng

**Yêu cầu chức năng** mô tả hệ thống làm gì: tìm kiếm phòng, tạo đặt chỗ, thanh toán, gửi thông báo. **Yêu cầu phi chức năng / thuộc tính chất lượng** mô tả hệ thống phải thực hiện các chức năng đó tốt đến mức nào và trong điều kiện nào:

| Thuộc tính | Ví dụ yêu cầu đo được | Hệ quả thiết kế cần trao đổi |
|---|---|---|
| Hiệu năng | 95% yêu cầu tìm kiếm có độ trễ dưới 300 ms khi tải đạt ngưỡng đã thống nhất | Cache, truy vấn dữ liệu, giới hạn tài nguyên, kiểm thử tải |
| Độ tin cậy | SLO thành công của thao tác đặt chỗ đạt 99,9% trong tháng, loại trừ yêu cầu không hợp lệ theo quy tắc đo đã định | Xử lý lỗi, timeout, idempotency, giới hạn phụ thuộc |
| Phục hồi | RPO tối đa 15 phút, RTO tối đa 60 phút cho một kịch bản sự cố cụ thể | Backup, khôi phục, diễn tập, chi phí dự phòng |
| Bảo mật | Dữ liệu nhạy cảm được kiểm soát truy cập theo vai trò và không xuất hiện trong log | IAM, mã hóa, phân loại dữ liệu, lọc log, audit |
| Mở rộng | Vẫn đáp ứng SLO khi tải tăng gấp 5 lần vào một đợt cao điểm dự báo | Scale-out, hàng đợi, giới hạn kết nối, thử nghiệm tải |
| Chi phí | Chi phí vận hành nằm trong ngân sách đã duyệt dưới tải dự kiến | Dự báo, cảnh báo ngân sách, chính sách lưu trữ và tối ưu tài nguyên |

Các con số trên **chỉ là ví dụ minh họa**, không phải tiêu chuẩn mặc định cho mọi ứng dụng. Một mục tiêu thiếu cách đo, điều kiện tải hoặc người chịu trách nhiệm thường chưa đủ rõ để làm cơ sở thiết kế.

Một số thuật ngữ quan trọng:

- **SLI (Service Level Indicator):** chỉ số quan sát được, ví dụ tỷ lệ yêu cầu đặt chỗ thành công.
- **SLO (Service Level Objective):** mục tiêu cho SLI trong một khoảng thời gian xác định.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, tính theo thời gian, trong phạm vi kịch bản khôi phục đã xác định.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau sự cố thuộc phạm vi đã xác định.

Không nên tự động coi SLO là cam kết pháp lý với khách hàng; cam kết dịch vụ (SLA) có thể được xác định riêng.

## 3. Kiến trúc sư phối hợp với những ai?

Sự phân chia dưới đây là **mô hình tham khảo**. Quyền quyết định cuối cùng thay đổi theo tổ chức, quy định và mô hình vận hành. Những công việc tác động qua nhiều nhóm cần có người chịu trách nhiệm rõ ràng.

| Vai trò | Trọng tâm | Những gì cần phối hợp với kiến trúc sư |
|---|---|---|
| Product owner / đại diện nghiệp vụ | Giá trị khách hàng, phạm vi và ưu tiên | Mục tiêu, hành trình quan trọng, chi phí cơ hội, mức rủi ro chấp nhận |
| Tech lead / nhóm phát triển | Thiết kế chi tiết, mã nguồn, kiểm thử, tích hợp | Ranh giới dịch vụ, hợp đồng API, mô hình dữ liệu, lỗi và khả năng hiện thực |
| Chuyên gia bảo mật / AppSec / cloud security | Mối đe dọa và kiểm soát rủi ro | Phân loại dữ liệu, định danh, phân quyền, mạng, mã hóa, audit, yêu cầu tuân thủ |
| SRE / Platform / Cloud Operations | Triển khai, vận hành, độ tin cậy, khôi phục | SLO, giám sát, cảnh báo, triển khai an toàn, runbook, backup và diễn tập |
| Data engineer / DBA (nếu có) | Vòng đời dữ liệu và tính toàn vẹn | Lược đồ, giao dịch, khả năng khôi phục, lưu giữ, đồng bộ và năng lực hệ dữ liệu |
| FinOps / tài chính (nếu có) | Hiệu quả chi phí cloud | Dự báo tải, đơn giá, ngân sách, gắn thẻ chi phí, phân tích chi phí trên một giao dịch |

Mô hình phối hợp hiệu quả cần ba điều: **thảo luận sớm**, **quyết định rõ ràng** và **phản hồi từ triển khai/vận hành**. Một thiết kế chỉ được đưa cho đội bảo mật ngay trước ngày phát hành, hoặc chỉ được trao cho đội vận hành sau khi đã lên production, thường phát sinh sửa đổi đắt đỏ.

## 4. Phối hợp với nhóm phát triển

Nhóm phát triển biết rõ mã nguồn hiện tại, phụ thuộc hệ thống, nợ kỹ thuật và chi phí thay đổi. Kiến trúc sư cung cấp hướng tổng thể và các ràng buộc cần giữ; kỹ sư phát triển góp dữ liệu thực tế và chủ động thiết kế chi tiết.

### Các điểm cần thống nhất

1. **Ranh giới và hợp đồng:** thành phần nào sở hữu dữ liệu nào, giao tiếp đồng bộ hay bất đồng bộ, API trả lỗi thế nào, tương thích phiên bản ra sao.
2. **Tính nhất quán:** thao tác nào cần giao dịch mạnh (như xác nhận một chỗ còn trống), dữ liệu nào có thể cập nhật sau (như email thông báo).
3. **Xử lý lỗi:** timeout, retry có giới hạn, backoff, idempotency, circuit breaker hoặc cô lập lỗi khi phù hợp. Retry thiếu kiểm soát có thể làm quá tải lan rộng.
4. **Hiệu năng và mở rộng:** dự đoán điểm nghẽn bằng phép đo, xem xét số kết nối DB, bộ nhớ, cache, quy mô hàng đợi và tải đỉnh.
5. **Khả năng thay đổi:** tách cấu hình khỏi mã, thiết kế migration an toàn, hợp đồng kiểm thử, khả năng rollback và triển khai từng phần.

Ví dụ, kiến trúc sư đề xuất dùng hàng đợi cho thông báo đặt chỗ. Nhóm phát triển cần phản biện: “Làm sao tránh gửi email trùng nếu message được xử lý lại?”, “Làm sao bảo đảm sự kiện được phát sau khi giao dịch đặt chỗ commit?”. Từ phản biện này có thể hình thành cơ chế **consumer idempotent** và, nếu cần, **transactional outbox**. Những chi tiết đó là một phần của kiến trúc, dù được chốt thông qua thiết kế cùng nhóm phát triển.

### Cách làm việc hữu ích

- Thống nhất **tiêu chí chấp nhận kiến trúc** trước khi mã hóa: hợp đồng API, cách xử lý lỗi, giới hạn tải và các điều kiện bảo mật.
- Tổ chức design review ngắn khi quyết định ảnh hưởng đến nhiều thành phần hoặc khó đảo ngược; để kỹ sư trình bày phương án và bằng chứng.
- Tạo thử nghiệm nhỏ (proof of concept) để kiểm chứng điều còn chưa biết, ví dụ giới hạn kết nối DB dưới tải, thay vì tranh luận bằng trực giác.
- Ghi quyết định và lý do bằng ADR; những điều chỉnh cục bộ không ảnh hưởng ràng buộc chung nên được nhóm phát triển tự quyết.

Kiến trúc sư cần tránh trở thành nút thắt phê duyệt từng chi tiết code. Một nguyên tắc hữu ích là: **quyết định càng khó đảo ngược và ảnh hưởng càng rộng, mức phối hợp càng phải cao**.

## 5. Phối hợp với nhóm bảo mật

Trên cloud, nhà cung cấp và khách hàng cùng tham gia bảo mật theo **mô hình trách nhiệm chia sẻ**. Ranh giới chính xác thay đổi theo dịch vụ IaaS/PaaS/SaaS và nhà cung cấp; việc dùng managed service không tự động bảo đảm ứng dụng, danh tính, dữ liệu và cấu hình của khách hàng đã an toàn.

Kiến trúc sư cùng nhóm bảo mật thực hiện **security by design**, đưa kiểm soát vào quyết định sớm thay vì chờ quét lỗi cuối chu kỳ.

| Câu hỏi thiết kế | Nội dung cần có trong phương án |
|---|---|
| Dữ liệu gì được xử lý? | Phân loại dữ liệu cá nhân/nhạy cảm, mục đích sử dụng, lưu giữ và xóa |
| Ai được truy cập? | Danh tính người dùng/dịch vụ, quyền tối thiểu, tách vai trò và kiểm soát truy cập đặc quyền |
| Dữ liệu đi đâu? | Sơ đồ luồng dữ liệu, ranh giới tin cậy, mã hóa khi truyền và khi lưu, yêu cầu khu vực lưu trữ |
| Thành phần nào công khai Internet? | Điểm vào, phân đoạn mạng, WAF khi phù hợp, chính sách inbound/outbound |
| Bí mật được quản lý ra sao? | Secret manager, rotation, không hard-code token/mật khẩu trong mã hay pipeline |
| Phát hiện và truy vết thế nào? | Audit log phù hợp, dữ liệu log được che/lọc, phát hiện bất thường, quyền truy cập log |
| Nếu bị tấn công thì sao? | Kịch bản đe dọa, giới hạn phạm vi ảnh hưởng, quy trình ứng cứu và khôi phục |

### Threat modeling là hoạt động chung

Một phiên **mô hình hóa mối đe dọa (threat modeling)** nên có ít nhất người hiểu nghiệp vụ, kiến trúc/luồng dữ liệu, người phát triển và người phụ trách bảo mật. Quy trình đơn giản:

1. Vẽ luồng dữ liệu, các tài sản cần bảo vệ và ranh giới tin cậy.
2. Liệt kê tác nhân, điểm vào và tình huống lạm dụng: giả mạo danh tính, truy cập trái phép vào đặt chỗ của người khác, lộ dữ liệu trong log, gọi API quá mức.
3. Đánh giá khả năng xảy ra và mức tác động theo phương pháp của tổ chức.
4. Chọn kiểm soát phù hợp, phân công triển khai, xác định cách kiểm chứng và chấp nhận phần rủi ro còn lại qua người có thẩm quyền.

Ví dụ: API lấy chi tiết đặt chỗ phải xác minh **người gọi có quyền đối với đúng bản ghi**, không chỉ xác nhận người dùng đã đăng nhập. Nhóm phát triển thực hiện kiểm tra ở lớp ứng dụng; bảo mật đặt tiêu chí kiểm thử; kiến trúc sư bảo đảm luồng định danh, quyền truy cập và phân tách dịch vụ hỗ trợ cơ chế đó.

Kiểm thử tự động, quét dependency, kiểm tra hạ tầng dưới dạng mã và kiểm thử phân quyền giúp phản hồi sớm. Tuy nhiên, công cụ quét không thay thế được việc hiểu luồng nghiệp vụ và mô hình đe dọa.

## 6. Phối hợp với nhóm vận hành và SRE

Một hệ thống chỉ “chạy được trên môi trường thử nghiệm” chưa phải thiết kế hoàn chỉnh. Nhóm vận hành và SRE giúp trả lời: khi lỗi xảy ra lúc 2 giờ sáng, có phát hiện được vấn đề, xác định nguyên nhân, giảm tác động và khôi phục trong mục tiêu không?

### Thiết kế để quan sát, triển khai và khôi phục

**Khả năng quan sát (observability)** cần được thiết kế từ đầu:

- **Metrics:** thông lượng, tỷ lệ lỗi, độ trễ, độ bão hòa tài nguyên và chỉ số nghiệp vụ như tỷ lệ xác nhận đặt chỗ.
- **Logs:** có cấu trúc, mã liên kết yêu cầu (correlation ID), không lộ dữ liệu nhạy cảm, có chính sách lưu giữ.
- **Traces:** theo dõi luồng yêu cầu qua gateway, dịch vụ, DB và hàng đợi khi việc phân tán khiến chẩn đoán khó khăn.
- **Alert:** gắn với tác động lên người dùng và SLO; cảnh báo có người nhận và cách xử lý, tránh báo động quá nhiều nhưng không có hành động.

**Triển khai an toàn** thường cần hạ tầng dưới dạng mã (Infrastructure as Code - IaC), pipeline kiểm tra, cấu hình tách biệt môi trường, thay đổi có thể truy vết và cơ chế rollback hoặc roll-forward. Phương án phát hành từng phần (canary/blue-green) chỉ nên chọn khi mức độ rủi ro và năng lực vận hành biện minh được độ phức tạp bổ sung.

**Khả năng khôi phục** không chỉ là có bản backup:

1. Nêu rõ các kịch bản: một instance hỏng, một vùng khả dụng mất kết nối, DB bị xóa nhầm, lỗi triển khai, mất cả khu vực.
2. Với từng kịch bản, xác định mức phục hồi mong muốn và giới hạn ngân sách.
3. Thiết kế bản sao, backup, retention, quyền khôi phục và phụ thuộc giữa các bước.
4. Thử khôi phục trên môi trường phù hợp; đo **RPO/RTO thực tế** và cải tiến nếu không đạt.

Kiến trúc sư cần đưa chi phí và độ phức tạp vận hành vào lựa chọn thiết kế. Đưa một dịch vụ đơn giản lên kiến trúc nhiều vùng, nhiều cluster có thể cải thiện một loại khả năng chịu lỗi nhưng cũng tăng cấu hình sai, yêu cầu trực ca và chi phí.

### Bộ bàn giao tối thiểu cho vận hành

Một hệ thống sẵn sàng đi vào production thường cần: sơ đồ hiện hành, chủ sở hữu dịch vụ, cách triển khai/rollback, SLI/SLO và dashboard, điều kiện cảnh báo, runbook xử lý lỗi phổ biến, phương án backup/khôi phục, danh sách phụ thuộc quan trọng và quy trình escalation. Những nội dung này cần được vận hành thử cùng đội phát triển, thay vì chỉ lưu thành tài liệu.

## 7. Quy trình phối hợp từ yêu cầu đến production

~~~mermaid
flowchart TD
    A["Nghiệp vụ: mục tiêu và giới hạn"] --> B["Kiến trúc sư + các nhóm: xác nhận yêu cầu chất lượng"]
    B --> C["Đề xuất phương án và đánh đổi"]
    C --> D["Phát triển + Bảo mật + Vận hành: phản biện thiết kế"]
    D --> E["ADR, sơ đồ, tiêu chí chấp nhận"]
    E --> F["Triển khai và kiểm chứng: test, tải, bảo mật, phục hồi"]
    F --> G{"Đạt tiêu chí?"}
    G -- "Chưa" --> C
    G -- "Đạt" --> H["Phát hành có kiểm soát"]
    H --> I["Quan sát SLO, sự cố, chi phí"]
    I --> C
~~~

Quy trình trên không bắt buộc thực hiện tuần tự theo kiểu “bàn giao qua từng phòng ban”. Ở đội sản phẩm làm việc theo sprint, các hoạt động có thể lặp lại trong mỗi increment. Điều quan trọng là **các quyết định có người sở hữu, có ý kiến của nhóm chịu tác động và có tiêu chí kiểm chứng**.

### Mẫu phân công trách nhiệm (RACI) tham khảo

RACI dùng bốn ký hiệu: **R** (Responsible: trực tiếp thực hiện), **A** (Accountable: chịu trách nhiệm cuối cùng), **C** (Consulted: được tham vấn), **I** (Informed: được thông báo). Một hoạt động nên có người A rõ ràng; một người có thể đồng thời là A và R.

| Hoạt động | Nghiệp vụ | Kiến trúc sư | Phát triển | Bảo mật | Vận hành/SRE |
|---|---|---|---|---|---|
| Chốt mục tiêu, ưu tiên, giới hạn chi phí | A | R | C | C | C |
| Quyết định cấu trúc hệ thống tổng thể | C | A/R | C | C | C |
| Thiết kế API và logic chi tiết | I | C | A/R | C | C |
| Thiết lập baseline kiểm soát bảo mật | I | C | R | A | C |
| Định nghĩa giám sát, runbook, diễn tập khôi phục | C | C | R | C | A |
| Phát hành và xác nhận sẵn sàng vận hành | I | C | R | C | A |

Đây chỉ là **ví dụ phân vai**, không phải quy tắc áp dụng cứng. Một tổ chức có thể giao quyền phát hành cho release manager hoặc delivery lead; các quyết định chấp nhận rủi ro bảo mật, tuân thủ và ngân sách cần đúng thẩm quyền nội bộ.

### Một quyết định nên được ghi như thế nào?

**Architecture Decision Record (ADR)** là bản ghi ngắn lưu bối cảnh và lý do của một quyết định đáng kể. Một mẫu đủ dùng:

~~~text
ADR-007 — Gửi thông báo bất đồng bộ sau khi tạo đặt chỗ
Trạng thái: Accepted
Bối cảnh: Thời gian phản hồi thao tác đặt chỗ không nên phụ thuộc
           vào độ sẵn sàng của dịch vụ email bên ngoài.
Phương án:
  A. Gọi email trực tiếp trong request.
  B. Ghi đặt chỗ vào DB, công bố sự kiện sau khi commit,
     worker xử lý email bất đồng bộ.
Quyết định: Chọn B; dùng outbox nếu cần bảo đảm đồng bộ
            giữa commit DB và phát sự kiện.
Hệ quả: Request nhanh hơn và cô lập lỗi email; đổi lại
        thông báo có độ trễ, cần retry, idempotency,
        theo dõi hàng đợi và xử lý message lỗi.
Kiểm chứng: Test khi email provider lỗi; đo thời gian từ
             xác nhận đặt chỗ đến khi gửi thông báo.
Xem lại khi: Độ trễ thông báo vượt ngưỡng nghiệp vụ
             hoặc khối lượng vận hành tăng quá mức.
~~~

ADR không thay thế thiết kế API, sơ đồ triển khai hay runbook. Giá trị của nó là cho người đến sau biết **vì sao** hệ thống đang được thiết kế như vậy và điều gì có thể khiến quyết định cần thay đổi.

## 8. Tình huống thực hành: thiết kế hệ thống đặt chỗ trên cloud

Giả sử một nền tảng đặt phòng đang chuyển từ ứng dụng đơn khối lên cloud. Đội sản phẩm đưa ra các giả định ban đầu để thảo luận:

- Tìm kiếm phòng chiếm phần lớn lưu lượng; hoạt động tăng mạnh trong các chiến dịch ngắn.
- Không được xác nhận hai đặt chỗ trùng một phòng trong cùng khoảng thời gian.
- Khi hệ thống email lỗi, đặt chỗ vẫn phải được ghi nhận và người dùng nhận được kết quả rõ ràng.
- Các giao dịch quan trọng phải được theo dõi; dữ liệu cá nhân phải được bảo vệ; doanh nghiệp có ngân sách cloud hữu hạn.

Đây mới là bối cảnh. Kiến trúc sư chưa thể tuyên bố hệ thống “đạt HA” nếu chưa có SLO, kịch bản lỗi và cách kiểm thử. Sau khi trao đổi cùng các nhóm, họ có thể chọn cấu trúc ban đầu như sau:

~~~mermaid
flowchart LR
    U["Web / Mobile"] --> G["API Gateway / WAF"]
    G --> S["Ứng dụng / Booking API"]
    S --> D[("Managed relational DB")]
    S --> C[("Cache tìm kiếm")]
    S --> O["Outbox / Message queue"]
    O --> W["Worker gửi thông báo"]
    W --> E["Email provider"]
    S -. "Logs / Metrics / Traces" .-> M["Observability"]
    W -. "Logs / Metrics / Traces" .-> M
    D -. "Backup / Restore" .-> B["Kho bản sao lưu"]
~~~

*Sơ đồ logic để trao đổi trách nhiệm và luồng dữ liệu; chưa biểu diễn toàn bộ mạng, vùng khả dụng, firewall, IAM hoặc các cơ chế sẵn sàng cao. Các lựa chọn đó cần được thiết kế dựa trên yêu cầu và nhà cung cấp thực tế.*

### Trường hợp 1: Tránh đặt trùng phòng

- **Nghiệp vụ** xác định quy tắc trùng lịch, thời hạn giữ chỗ, hoàn/hủy và tình huống thanh toán chưa xong.
- **Kiến trúc sư + phát triển + chuyên gia dữ liệu** xác định một nơi có quyền quyết định tính hợp lệ của đặt chỗ. Có thể dùng giao dịch DB, khóa thích hợp hoặc ràng buộc dữ liệu để bảo đảm không xác nhận hai giao dịch xung đột; việc chỉ đọc cache trước khi ghi là không đủ.
- **Bảo mật** bảo đảm người dùng chỉ được thao tác trên dữ liệu và tài nguyên mà họ được phép.
- **Vận hành** theo dõi tỷ lệ xung đột, lỗi transaction, lock contention và độ trễ trong giờ cao điểm.

Quyết định thiết kế phải được chứng minh bằng **kiểm thử đồng thời**: gửi nhiều yêu cầu tranh chấp cùng một chỗ và xác nhận chỉ một yêu cầu hợp lệ được commit.

### Trường hợp 2: Nhà cung cấp email bị lỗi

- Đặt chỗ được xác nhận sau khi giao dịch dữ liệu thành công, không chờ kết quả email.
- Sự kiện được lưu và chuyển đến worker; nếu worker nhận lại cùng thông điệp, hành động phải có cơ chế chống xử lý trùng khi nghiệp vụ yêu cầu.
- Dashboard hiển thị số message chưa xử lý, độ tuổi thông điệp cũ nhất, số lần thử lại và số thông điệp cần can thiệp.
- Runbook quy định cách xử lý message lỗi, khi nào thông báo cho khách hàng và cách khôi phục backlog.

Đây là đánh đổi giữa **độ trễ thông báo** và **tính độc lập của giao dịch đặt chỗ**. Nhóm nghiệp vụ phải xác nhận thông báo đến chậm bao lâu là chấp nhận được.

### Trường hợp 3: Mất một vùng khả dụng

Trước khi chọn multi-AZ, nhóm vận hành và kiến trúc sư cần phân biệt: chỉ một instance lỗi, cả vùng khả dụng lỗi hay cả region lỗi? Mỗi phạm vi đòi hỏi cơ chế phục hồi và chi phí khác nhau. Với kiến trúc managed DB nhiều vùng khả dụng, vẫn phải xem xét failover, kết nối ứng dụng, giới hạn DNS/client timeout và hoạt động khôi phục dữ liệu khi xóa nhầm. **Multi-AZ không thay thế backup**, cũng không tự động giải quyết mất cả region.

### Ma trận đánh đổi

| Quyết định | Lợi ích có thể đạt | Chi phí/rủi ro phát sinh | Ai cần cùng quyết định? |
|---|---|---|---|
| Dùng managed database | Giảm một phần việc bảo trì hạ tầng, có tùy chọn backup/failover | Phụ thuộc dịch vụ, giới hạn cấu hình, chi phí và kết nối | Kiến trúc, phát triển/DBA, vận hành, bảo mật |
| Thêm cache cho tìm kiếm | Giảm độ trễ và tải đọc DB | Dữ liệu cũ, invalidation phức tạp; không dùng cache làm nguồn xác nhận đặt chỗ | Phát triển, kiến trúc, nghiệp vụ |
| Thông báo qua queue | Cô lập lỗi nhà cung cấp, xử lý tải theo đợt | Bất đồng bộ, xử lý trùng/lỗi, giám sát backlog | Kiến trúc, phát triển, vận hành |
| Triển khai nhiều vùng khả dụng | Chịu một số loại lỗi hạ tầng tốt hơn | Chi phí, failover, kết nối và kiểm thử phức tạp | Nghiệp vụ, kiến trúc, vận hành, tài chính |
| Kiểm soát truy cập tối thiểu | Giảm phạm vi tác động khi lộ danh tính/quyền | Cần thiết kế vai trò, quản trị và kiểm thử định kỳ | Bảo mật, phát triển, vận hành |

Không có lựa chọn “tốt nhất” tách khỏi bối cảnh. Kiến trúc sư cần mô tả lợi ích **kèm điều kiện để đạt lợi ích đó**, sự đánh đổi và phép thử xác nhận.

## 9. Đánh giá theo tư duy Well-Architected

Các nhà cung cấp cloud có bộ nguyên tắc Well-Architected với tên và cách nhóm trụ cột khác nhau. Khi đánh giá một thiết kế, có thể dùng các góc nhìn chung sau; không nên hiểu đây là một checklist chứng nhận tự động.

| Góc nhìn | Câu hỏi phản biện | Bằng chứng cần tìm |
|---|---|---|
| Độ tin cậy | Thành phần nào lỗi sẽ ảnh hưởng toàn bộ nghiệp vụ? Đã thử phục hồi chưa? | Kết quả failover, restore test, SLO và lịch sử sự cố |
| Bảo mật | Quyền có tối thiểu không? Dữ liệu nhạy cảm có đi qua log, hàng đợi, bản sao lưu không? | Data flow, threat model, kiểm thử quyền, audit và quản lý secrets |
| Hiệu năng / khả năng mở rộng | Hệ thống suy giảm thế nào tại tải đỉnh? Nút cổ chai ở đâu? | Load test, độ trễ p95/p99, tỷ lệ lỗi, giới hạn DB/queue |
| Tối ưu chi phí | Tài nguyên nào tăng theo lưu lượng? Chi phí/đơn vị nghiệp vụ có theo dõi được không? | Dự báo, cost allocation, cảnh báo ngân sách, kết quả tối ưu |
| Vận hành xuất sắc | Ai nhận cảnh báo, xử lý lỗi và triển khai rollback? | Ownership, IaC, CI/CD, dashboard, runbook, diễn tập |
| Bền vững tài nguyên (khi phù hợp) | Tài nguyên có bị cấp dư, xử lý lặp hoặc lưu giữ quá lâu không? | Số liệu sử dụng tài nguyên, retention và lịch tối ưu |

Điều quan trọng là **xem xét mối liên hệ giữa các góc nhìn**: thêm bản sao dữ liệu có thể tăng khả năng sẵn sàng nhưng tăng chi phí, yêu cầu quản lý quyền và tác động môi trường. Thu hẹp tài nguyên có thể giảm chi phí nhưng cần đo lại hiệu năng và dự phòng.

## 10. Dấu hiệu phối hợp tốt và những sai lầm thường gặp

### Những dấu hiệu tích cực

- Nhóm nghiệp vụ biết hệ thống đang tối ưu mục tiêu nào và đánh đổi điều gì.
- Phát triển có đủ quyền chủ động trong thiết kế chi tiết và biết khi nào cần trao đổi thay đổi kiến trúc.
- Bảo mật tham gia từ lúc lập mô hình dữ liệu/luồng truy cập, có cách kiểm chứng từng kiểm soát.
- Vận hành tham gia xác định SLO, triển khai, theo dõi, khôi phục và trực sự cố.
- Mọi quyết định quan trọng có lý do, giả định, người chịu trách nhiệm và điều kiện xem xét lại.
- Đội ngũ điều chỉnh kiến trúc dựa trên số liệu tải, sự cố và chi phí thực tế.

### Sai lầm và cách sửa

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chọn công nghệ trước khi hiểu nghiệp vụ | Kiến trúc phức tạp hoặc không đạt yêu cầu chính | Chốt use case, thuộc tính chất lượng và giả định trước khi đánh giá công nghệ |
| Kiến trúc sư ra quyết định một chiều | Nhóm triển khai thiếu đồng thuận; vấn đề thực tế bị bỏ sót | Review với người thực hiện và người trực vận hành; ghi lại phản biện |
| “Bảo mật sẽ kiểm tra trước release” | Lộ vấn đề thiết kế muộn, phải sửa lớn | Threat modeling, chính sách IAM và kiểm thử bảo mật trong quá trình phát triển |
| Chỉ đo CPU, không đo trải nghiệm nghiệp vụ | Dashboard xanh nhưng khách hàng vẫn không đặt được | Định nghĩa SLI theo hành trình quan trọng và cảnh báo theo tác động |
| Có backup nhưng chưa từng thử restore | Không biết khả năng đạt RTO/RPO | Lập lịch diễn tập, đo kết quả và xử lý lỗ hổng khôi phục |
| Chọn microservices/multi-region theo xu hướng | Tăng chi phí tích hợp, giám sát và trực vận hành | So sánh với phương án đơn giản hơn dựa trên tải, đội ngũ và yêu cầu cụ thể |
| Không cập nhật ADR và sơ đồ | Tài liệu sai lệch so với production | Gắn cập nhật tài liệu với thay đổi kiến trúc và sự cố quan trọng |

## 11. Checklist để chuẩn bị một buổi review kiến trúc

Dùng danh sách dưới đây khi kiến trúc sư mời phát triển, bảo mật, vận hành và nghiệp vụ đánh giá một thay đổi:

- [ ] Đã nêu luồng nghiệp vụ trọng tâm, người dùng bị ảnh hưởng và người quyết định ưu tiên.
- [ ] Đã phân biệt yêu cầu bắt buộc, mục tiêu mong muốn và giả định còn thiếu dữ liệu.
- [ ] Có tiêu chí đo hiệu năng, độ tin cậy, bảo mật, phục hồi và chi phí phù hợp phạm vi.
- [ ] Có sơ đồ thành phần, luồng dữ liệu, ranh giới tin cậy và phụ thuộc bên ngoài.
- [ ] Nêu ít nhất một phương án thay thế hợp lý và các đánh đổi của quyết định chính.
- [ ] Nhóm phát triển xác nhận thiết kế có thể triển khai và kiểm thử, gồm cả lỗi và trường hợp đồng thời.
- [ ] Nhóm bảo mật đã đánh giá dữ liệu, định danh, quyền, secrets, nhật ký và rủi ro tồn dư.
- [ ] Nhóm vận hành đã rà soát deployment, quan sát, cảnh báo, runbook, backup và khôi phục.
- [ ] Quyết định quan trọng được lưu bằng ADR với chủ sở hữu và điều kiện xem xét lại.
- [ ] Có kế hoạch kiểm chứng bằng phép đo trước phát hành, theo dõi sau phát hành và cơ chế cập nhật thiết kế.

**Kết luận:** Kiến trúc sư tạo ra sự thống nhất giữa **điều doanh nghiệp cần**, **điều đội phát triển có thể xây**, **điều đội bảo mật có thể bảo vệ** và **điều đội vận hành có thể duy trì**. Chất lượng kiến trúc đám mây thể hiện qua các đánh đổi được hiểu rõ, quyết định có thể giải thích và kết quả được kiểm chứng trong môi trường thực tế.
