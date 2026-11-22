# Liên kết quyết định phát hành với người chịu trách nhiệm

Một bản dựng có thể vượt qua nhiều kiểm thử nhưng vẫn cần một quyết định rõ ràng trước khi phát hành: ai có quyền cho phép triển khai, ai chịu trách nhiệm xác nhận bằng chứng, ai chấp nhận rủi ro còn lại và ai có quyền dừng hoặc quay lui khi tình hình thay đổi? Nếu các vai trò này không được xác định, quyết định thường bị trì hoãn, bị ngầm hiểu là đã được chấp thuận hoặc được đưa ra bởi người không có đủ thông tin và thẩm quyền.

Liên kết quyết định phát hành với người chịu trách nhiệm nghĩa là mỗi quyết định quan trọng trong vòng đời release phải có **một chủ thể chịu trách nhiệm cuối cùng, căn cứ rõ ràng, phạm vi quyền hạn và dấu vết có thể truy vết**. Người thực hiện kiểm thử cung cấp bằng chứng; người sở hữu dịch vụ đánh giá khả năng vận hành; chuyên gia bảo mật đánh giá rủi ro bảo mật; product xác nhận tác động nghiệp vụ; người có thẩm quyền phát hành đưa ra quyết định theo chính sách. Một quyết định không thể chỉ dựa vào việc pipeline chuyển sang màu xanh hoặc một cuộc họp kết thúc mà không ai phản đối.

## 1. Vì sao quyết định phát hành cần gắn với trách nhiệm?

Phát hành là quyết định chấp nhận đưa một phiên bản phần mềm, cấu hình hoặc thay đổi dữ liệu vào môi trường có người dùng và quy trình thực tế. Quyết định đó có thể ảnh hưởng đến:

- Tính đúng đắn của chức năng và dữ liệu.
- Bảo mật, quyền riêng tư và quyền truy cập.
- Hiệu năng, độ sẵn sàng và khả năng phục hồi.
- Trải nghiệm người dùng và quy trình nghiệp vụ.
- Tương thích API, dịch vụ và nhà cung cấp bên ngoài.
- Khả năng hỗ trợ, giám sát, rollback và xử lý sự cố.
- Cam kết hợp đồng, quy định và thời hạn phát hành.

Khi có sự cố, nhóm cần biết ai đã xác nhận bằng chứng, ai đã chấp nhận rủi ro, ai quyết định tiếp tục rollout và ai có quyền dừng. Nếu trách nhiệm không rõ, các bên có thể đổ lỗi cho nhau hoặc giả định rằng một nhóm khác đã kiểm tra.

Quyết định có trách nhiệm giúp:

- Tránh tình trạng nhiều người cùng nghĩ người khác sẽ quyết định.
- Bảo đảm rủi ro được chấp nhận bởi đúng cấp thẩm quyền.
- Làm rõ bằng chứng nào cần có trước khi chuyển giai đoạn.
- Đẩy nhanh quyết định khi có dữ liệu đầy đủ.
- Cho phép dừng phát hành khi điều kiện an toàn thay đổi.
- Tạo lịch sử để học hỏi sau release hoặc incident.

## 2. Phân biệt người thực hiện, người chịu trách nhiệm và người có quyền quyết định

Các vai trò thường bị dùng lẫn lộn. Cần phân biệt:

- **Responsible:** người trực tiếp thực hiện công việc hoặc tạo ra kết quả, chẳng hạn chạy regression, triển khai hoặc kiểm tra dashboard.
- **Accountable:** người chịu trách nhiệm cuối cùng về kết quả hoặc quyết định trong phạm vi được giao. Mỗi quyết định nên có một Accountable rõ ràng.
- **Approver/Decision owner:** người có quyền phê duyệt một quyết định cụ thể, chẳng hạn Go/No-Go hoặc chấp nhận rủi ro. Vai trò này có thể trùng với Accountable nhưng phải được xác định rõ theo chính sách.
- **Consulted:** người cung cấp chuyên môn hoặc ý kiến cần thiết trước khi quyết định.
- **Informed:** người cần được thông báo về quyết định và kết quả.

Người chạy test không mặc nhiên có quyền chấp thuận release. QA có thể xác nhận phạm vi và kết quả kiểm thử, nhưng việc chấp nhận rủi ro nghiệp vụ, bảo mật hoặc vận hành cần đúng chủ sở hữu và thẩm quyền. Ngược lại, người phê duyệt release không nên tự kết luận rằng test đã đạt nếu không có bằng chứng từ người thực hiện và hệ thống kiểm thử.

### 2.1. Một quyết định, một người chịu trách nhiệm cuối cùng

Có thể có nhiều người tham gia đánh giá, nhưng cần một người hoặc vai trò chịu trách nhiệm cuối cùng cho từng loại quyết định. Ví dụ:

- Product owner chịu trách nhiệm chấp nhận mức sẵn sàng về nghiệp vụ.
- Service owner chịu trách nhiệm về readiness kỹ thuật của dịch vụ.
- Security owner quyết định chấp nhận rủi ro bảo mật trong phạm vi được ủy quyền.
- Release manager điều phối và ghi nhận quyết định Go/No-Go theo chính sách.
- Incident commander hoặc người trực vận hành có quyền kích hoạt dừng rollout trong tình huống khẩn cấp.

Không nên gán một trách nhiệm chung chung cho "team". Nhóm có thể cùng thực hiện, nhưng phải chỉ ra người nhận quyết định và chịu trách nhiệm cuối cùng.

## 3. Các quyết định cần có chủ sở hữu

Không chỉ quyết định Go/No-Go mới cần gắn trách nhiệm. Trong vòng đời phát hành có nhiều quyết định liên quan.

| Quyết định | Nội dung | Chủ thể chịu trách nhiệm điển hình |
|---|---|---|
| Xác định phạm vi release | Chức năng, dịch vụ, migration và cấu hình nào được đưa vào | Product owner và release owner |
| Xác nhận tiêu chí readiness | Điều kiện chất lượng và vận hành phải đạt | Release owner phối hợp với QA và service owner |
| Xác nhận bằng chứng kiểm thử | Phạm vi test, kết quả, khoảng trống và độ tin cậy | QA/test lead hoặc test owner |
| Chấp nhận rủi ro nghiệp vụ | Tác động lên người dùng, giao dịch và quy trình | Product/business owner |
| Chấp nhận rủi ro bảo mật | Rủi ro còn lại về bảo mật và dữ liệu | Security/risk owner theo thẩm quyền |
| Xác nhận năng lực vận hành | Monitoring, capacity, runbook, on-call và phục hồi | Service owner/SRE |
| Phê duyệt triển khai | Cho phép đưa artifact vào môi trường đích | Release decision owner |
| Tiếp tục hoặc dừng rollout | Quyết định dựa trên metric và tín hiệu sau triển khai | Release owner hoặc incident commander theo tình huống |
| Rollback/roll-forward | Chọn hành động phục hồi và điều phối thực hiện | Service owner/incident commander |
| Đóng release | Xác nhận phát hành hoàn tất, rủi ro và hành động còn lại đã được bàn giao | Release owner |

Tên chức danh có thể khác giữa tổ chức. Điều quan trọng là quyết định nào cũng có owner, giới hạn thẩm quyền và người thay thế khi owner vắng mặt.

## 4. Xác định mô hình quản trị phát hành

Mô hình phù hợp phụ thuộc quy mô, mức độ rủi ro, kiến trúc và yêu cầu tuân thủ.

### 4.1. Mô hình do nhóm dịch vụ quyết định

Service team tự đánh giá readiness và quyết định phát hành trong giới hạn đã được tổ chức ủy quyền. Mô hình này phù hợp với nhóm trưởng thành, có ownership rõ và các quality gate được tự động hóa.

Điều kiện cần:

- Có service owner và release owner rõ.
- Chính sách release và tiêu chí bắt buộc được công bố.
- Rủi ro vượt thẩm quyền được escalated.
- Có giám sát, rollback và on-call.
- Quyết định được ghi lại trong hệ thống.

### 4.2. Mô hình phê duyệt tập trung

Một vai trò hoặc hội đồng thay đổi/phát hành xem xét các release có ảnh hưởng rộng, rủi ro cao hoặc yêu cầu tuân thủ đặc biệt. Mô hình này giúp phối hợp nhiều nhóm nhưng có thể làm chậm phản hồi nếu mọi thay đổi đều phải qua cùng một cấp.

Nên giới hạn phê duyệt tập trung cho các loại thay đổi cần điều phối liên tổ chức, thay đổi hạ tầng lớn, migration khó đảo ngược hoặc release có tác động đáng kể.

### 4.3. Mô hình kết hợp với policy gate tự động

Các kiểm tra định lượng và điều kiện rõ ràng được thực thi tự động; con người quyết định các vấn đề cần đánh giá rủi ro hoặc ngữ cảnh. Ví dụ, pipeline tự chặn khi test bắt buộc thất bại hoặc phát hiện lỗ hổng vượt ngưỡng; release owner xem xét rủi ro còn lại và bằng chứng vận hành trước khi cho phép rollout.

Tự động hóa không nên giả vờ quyết định thay con người ở các trường hợp cần thẩm quyền chấp nhận rủi ro. Cũng không nên yêu cầu người phê duyệt xác nhận thủ công những điều kiện có thể được kiểm tra máy móc một cách đáng tin cậy.

## 5. Thiết kế ma trận trách nhiệm

Ma trận RACI giúp thống nhất vai trò trong các hoạt động. RACI gồm:

- **R — Responsible:** thực hiện.
- **A — Accountable:** chịu trách nhiệm cuối cùng.
- **C — Consulted:** được tham vấn trước quyết định.
- **I — Informed:** được thông báo.

Ví dụ minh họa cho một release dịch vụ:

| Hoạt động/quyết định | Product owner | Development lead | QA/Test lead | Security owner | SRE/Service owner | Release manager |
|---|---|---|---|---|---|---|
| Chốt phạm vi và mục tiêu release | A | R | C | C | C | I |
| Xác định tiêu chí chất lượng | A | R | R | C | C | I |
| Thực hiện và báo cáo kiểm thử | I | R | A/R | C | C | I |
| Xác nhận rủi ro bảo mật | C | R | C | A | C | I |
| Xác nhận readiness vận hành | I | R | C | C | A | I |
| Đánh giá readiness tổng thể | A | R | R | C | C | C |
| Điều phối Go/No-Go | C | C | C | C | C | A |
| Thực hiện triển khai | I | R | C | I | A/R | C |
| Dừng rollout khi có tín hiệu nguy hiểm | I | R | C | C | A | C |
| Đóng release và bàn giao | A | R | C | C | R | A/R |

Ma trận trên chỉ là ví dụ. Một tổ chức có thể giao quyền Go/No-Go cho service owner hoặc release commander. Không nên sao chép máy móc ma trận mà không xét chính sách và cấu trúc thực tế. Mỗi hàng cần có một A duy nhất; nếu nhiều vai trò cùng được ghi A, cần làm rõ ai có quyền quyết định cuối cùng.

### 5.1. RACI không thay thế quyền hạn

RACI mô tả sự tham gia, không tự cấp quyền. Quyền phê duyệt phải được quy định trong chính sách, ủy quyền hoặc quy trình quản trị. Người được tham vấn có quyền đưa ra cảnh báo chuyên môn, nhưng không mặc nhiên có quyền chặn hoặc cho phép release nếu chính sách chưa quy định.

Với các điều kiện không thể miễn trừ, chẳng hạn yêu cầu pháp lý hoặc chính sách an toàn bắt buộc, quyền quyết định cần tuân theo cơ chế tuân thủ tương ứng.

## 6. Xây dựng tiêu chí Go/No-Go có thể kiểm chứng

Go/No-Go không nên là cảm nhận tổng quát như "có vẻ ổn". Cần có tiêu chí rõ và bằng chứng cho từng tiêu chí.

### 6.1. Các nhóm tiêu chí

**Phạm vi và chức năng**

- Yêu cầu trong phạm vi release đã được xác nhận.
- Hành trình nghiệp vụ quan trọng có bằng chứng phù hợp.
- Defect nghiêm trọng đã được xử lý hoặc có quyết định rủi ro hợp lệ.
- Thay đổi API, schema và dữ liệu có phương án tương thích.

**Kiểm thử và chất lượng**

- Các suite bắt buộc đã chạy trên đúng artifact hoặc phiên bản.
- Kết quả fail, blocked, skipped và quarantined được thể hiện rõ.
- Không có khoảng trống Critical/High chưa được đánh giá.
- Bằng chứng đủ mới, truy vết được và có thể tái lập.

**Bảo mật và dữ liệu**

- Các kiểm tra bảo mật bắt buộc đạt.
- Lỗ hổng vượt ngưỡng được xử lý hoặc có quyết định đúng thẩm quyền.
- Secret, quyền truy cập và dữ liệu được cấu hình phù hợp.
- Nghĩa vụ quyền riêng tư và lưu giữ dữ liệu được đáp ứng.

**Vận hành**

- Dashboard, alert, log, trace và health check sẵn sàng.
- Capacity và quota đủ cho workload dự kiến.
- Runbook, on-call và escalation path được xác định.
- Backup, restore, rollback hoặc roll-forward được kiểm chứng phù hợp.

**Phát hành**

- Artifact có định danh bất biến và nguồn gốc rõ ràng.
- Cấu hình và feature flag được review.
- Lịch triển khai, phụ thuộc và người thực hiện được xác nhận.
- Kế hoạch truyền thông và hỗ trợ người dùng sẵn sàng.

### 6.2. Phân biệt điều kiện chặn và điều kiện cảnh báo

Không phải mọi tiêu chí có cùng mức độ. Nên phân loại:

- **Hard gate:** điều kiện bắt buộc; không đạt thì không được chuyển tiếp.
- **Conditional gate:** có thể tiếp tục khi có biện pháp bù trừ và phê duyệt đúng thẩm quyền.
- **Advisory:** cảnh báo cần được ghi nhận và theo dõi nhưng không tự động chặn.

Ví dụ, lỗi phân quyền cho phép đọc dữ liệu tenant khác thường là hard gate. Một sai lệch nhỏ trong báo cáo nội bộ có thể là advisory nếu không ảnh hưởng quyết định hay nghĩa vụ. Việc phân loại phải được xác định trước và không thay đổi tùy tiện khi release gặp áp lực thời gian.

### 6.3. Không dùng một điểm tổng để che rủi ro nghiêm trọng

Một release có thể đạt 95% tiêu chí nhưng vẫn còn một lỗi Critical. Điểm trung bình không thể bù cho một điều kiện chặn. Dashboard nên hiển thị riêng:

- Các hard gate chưa đạt.
- Rủi ro Critical/High chưa được giải quyết.
- Ngoại lệ đang hoạt động và thời hạn.
- Bằng chứng chưa có hoặc đã lỗi thời.
- Người chịu trách nhiệm cho từng khoảng trống.

## 7. Chuẩn bị gói bằng chứng cho quyết định

Người ra quyết định cần một gói thông tin nhất quán, có thể kiểm tra nhanh nhưng vẫn cho phép đi sâu khi cần.

### 7.1. Nội dung gói release

- Release ID, phiên bản, commit và artifact digest.
- Phạm vi thay đổi và các thành phần bị ảnh hưởng.
- Kết quả build và test theo từng loại.
- Coverage yêu cầu, rủi ro và hành trình quan trọng.
- Defect còn mở, mức độ và tác động.
- Kết quả security, performance và compatibility.
- Trạng thái migration, dữ liệu và phụ thuộc bên thứ ba.
- Monitoring, alert, runbook và on-call.
- Kế hoạch triển khai, canary, rollback/roll-forward.
- Ngoại lệ, người phê duyệt, mitigation và hạn hết hiệu lực.
- Khuyến nghị của các owner và quyết định cần đưa ra.

### 7.2. Đánh giá độ tin cậy của bằng chứng

Mỗi bằng chứng cần trả lời:

- Được tạo trên artifact hoặc phiên bản nào?
- Được chạy trong môi trường và cấu hình nào?
- Test suite có bao phủ đúng phạm vi không?
- Có test bị bỏ qua, flaky hoặc blocked không?
- Kết quả còn mới so với thay đổi hiện tại không?
- Có thể truy cập báo cáo, log hoặc trace gốc không?
- Ai xác nhận kết quả và khi nào?

Không dùng kết quả pass của một build cũ để chứng minh build mới đạt nếu thay đổi có thể ảnh hưởng đến phạm vi kiểm tra. Nếu pipeline chạy trên commit khác artifact phát hành, phải có cách xác minh tính tương đương.

### 7.3. Tóm tắt cho người quyết định

Tóm tắt nên nêu:

1. Release định đưa điều gì vào môi trường?
2. Các hard gate đã đạt chưa?
3. Rủi ro quan trọng nào còn tồn tại?
4. Ai đã đánh giá từng rủi ro?
5. Có ngoại lệ nào và khi nào hết hạn?
6. Nếu có sự cố, ai dừng rollout và ai điều phối phục hồi?
7. Quyết định nào đang cần được đưa ra?

Tránh chỉ gửi một liên kết dashboard mà không nêu kết luận, khoảng trống và quyết định cần thiết.

## 8. Quy trình ra quyết định Go/No-Go

### Bước 1: Mở phiên đánh giá release

Release owner xác nhận phạm vi, artifact, môi trường đích, thời điểm triển khai và người tham gia cần thiết. Những người không liên quan không cần tham dự, nhưng phải có đại diện đủ thẩm quyền.

### Bước 2: Kiểm tra hard gate

Đối chiếu các điều kiện bắt buộc với bằng chứng. Nếu có hard gate chưa đạt, mặc định chưa được Go trừ khi chính sách cho phép một quy trình ngoại lệ cụ thể. Không suy diễn rằng im lặng đồng nghĩa chấp thuận.

### Bước 3: Xem xét rủi ro còn lại

Các owner trình bày defect, khoảng trống, ngoại lệ và tác động. Xác định khả năng xảy ra, hậu quả, phạm vi phơi nhiễm, khả năng phát hiện và phục hồi.

### Bước 4: Xác nhận biện pháp giảm thiểu

Kiểm tra feature flag, giới hạn lưu lượng, canary, monitoring, rollback, hỗ trợ và người trực. Mỗi biện pháp cần có owner và điều kiện kích hoạt.

### Bước 5: Thu thập ý kiến chuyên môn

QA xác nhận trạng thái kiểm thử; security xác nhận rủi ro bảo mật; SRE/service owner xác nhận vận hành; product xác nhận tác động nghiệp vụ. Các bên cần nêu rõ ý kiến đồng ý, phản đối hoặc điều kiện kèm theo.

### Bước 6: Người có thẩm quyền quyết định

Decision owner ghi rõ một trong các kết quả:

- **Go:** cho phép triển khai theo phạm vi và kế hoạch đã duyệt.
- **Go with conditions:** chỉ cho phép khi các điều kiện bổ sung được đáp ứng và theo dõi.
- **No-Go:** không triển khai cho đến khi các vấn đề được giải quyết hoặc đánh giá lại.
- **Defer:** hoãn để thu thập thêm bằng chứng, chờ phụ thuộc hoặc xử lý rủi ro.

### Bước 7: Ghi nhận và truyền đạt quyết định

Lưu người quyết định, thời điểm, căn cứ, phạm vi, điều kiện, rủi ro chấp nhận và người chịu trách nhiệm hành động. Thông báo cho các nhóm triển khai, vận hành, hỗ trợ và bên liên quan.

### Bước 8: Xác minh điều kiện trước khi bắt đầu

Trước khi triển khai, kiểm tra lại những điều kiện có thể thay đổi như trạng thái môi trường, phụ thuộc, quota, lịch bảo trì và readiness của on-call. Một quyết định Go không phải giấy phép vô thời hạn nếu điều kiện nền đã thay đổi.

## 9. Quyền dừng, rollback và tiếp tục rollout

Quyền cho phép bắt đầu triển khai và quyền dừng triển khai cần được quy định riêng. Trong sự cố, người trực vận hành có thể cần dừng rollout ngay mà không chờ một cuộc họp phê duyệt.

### 9.1. Quy định quyền dừng

Chính sách nên xác định:

- Ai có thể tạm dừng rollout khi metric vượt ngưỡng.
- Ai có thể tắt feature flag.
- Ai có thể kích hoạt rollback hoặc roll-forward.
- Ai là incident commander khi sự cố nghiêm trọng.
- Ai thông báo cho product, support và khách hàng.
- Ai quyết định tiếp tục rollout sau khi điều kiện phục hồi.

Với nguy cơ gây mất dữ liệu, lộ dữ liệu hoặc ảnh hưởng diện rộng, cần có quyền dừng khẩn cấp cho vai trò vận hành được chỉ định. Quy trình hậu kiểm sẽ đánh giá quyết định sau đó; không nên trì hoãn biện pháp bảo vệ khẩn cấp chỉ để chờ đủ người tham gia.

### 9.2. Tiêu chí dừng rollout

Ví dụ:

- Error rate vượt ngưỡng đã xác định trong khoảng thời gian liên tục.
- p95/p99 latency vượt SLO.
- Tỷ lệ giao dịch thất bại hoặc dữ liệu không nhất quán tăng.
- Alert bảo mật hoặc truy cập trái phép được kích hoạt.
- Queue backlog hoặc saturation tăng không kiểm soát.
- Health/readiness check thất bại.
- Tín hiệu từ người dùng hoặc support cho thấy hành trình chính bị lỗi.

Ngưỡng phải được xác định theo dịch vụ và workload, không dùng một con số tùy ý cho mọi hệ thống.

### 9.3. Quyết định tiếp tục sau khi dừng

Sau khi dừng, cần:

1. Xác định phạm vi và mức độ ảnh hưởng.
2. Ổn định dịch vụ và bảo vệ dữ liệu.
3. Điều tra nguyên nhân dựa trên log, metric, trace và phiên bản.
4. Xác minh bản sửa hoặc phương án phục hồi.
5. Chạy lại các kiểm tra phù hợp.
6. Đánh giá rủi ro còn lại.
7. Decision owner phê duyệt tiếp tục hoặc hủy release.

Không tự động tiếp tục chỉ vì metric trở lại bình thường trong một khoảng ngắn nếu nguyên nhân chưa được hiểu hoặc biện pháp phòng ngừa chưa sẵn sàng.

## 10. Quản lý bất đồng và escalation

Có thể xảy ra tình huống QA khuyến nghị No-Go do test thất bại, product muốn phát hành vì thời hạn, security không chấp nhận một rủi ro hoặc SRE cho rằng năng lực chưa đủ.

Quy trình xử lý:

- Nêu chính xác tiêu chí hoặc rủi ro gây bất đồng.
- Đưa ra bằng chứng và giả định của từng bên.
- Phân biệt yêu cầu bắt buộc với lựa chọn có thể đánh đổi.
- Xác định ai có quyền quyết định cuối cùng theo chính sách.
- Escalate khi rủi ro vượt thẩm quyền của decision owner.
- Ghi ý kiến bất đồng, quyết định và lý do.
- Đặt điều kiện theo dõi hoặc rà soát lại nếu vẫn tiếp tục.

Không giải quyết bất đồng bằng cách bỏ phiếu khi chính sách đã giao quyền cho một vai trò hoặc khi vấn đề thuộc yêu cầu không thể miễn trừ. Người có quyền quyết định cần chịu trách nhiệm về lựa chọn và rủi ro được chấp nhận.

### 10.1. Khi nào cần escalation?

- Rủi ro vượt ngưỡng chấp nhận của nhóm.
- Có khả năng ảnh hưởng nhiều dịch vụ hoặc khách hàng.
- Có xung đột với nghĩa vụ bảo mật, pháp lý hoặc hợp đồng.
- Không có người đủ thẩm quyền phê duyệt.
- Người quyết định có xung đột lợi ích.
- Các nhóm không thống nhất về phạm vi ảnh hưởng hoặc bằng chứng.
- Kế hoạch rollback hoặc phục hồi không đáng tin cậy.

## 11. Quyết định trong các mô hình phát hành khác nhau

### 11.1. Phát hành theo lô (batch release)

Một phiên bản được triển khai theo cửa sổ định trước. Cần xác định release owner, người triển khai, người giám sát, người trực và người có quyền dừng. Go/No-Go được ghi trước cửa sổ; sau triển khai có smoke test và xác nhận vận hành.

### 11.2. Progressive delivery/canary

Triển khai cho một phần lưu lượng trước. Decision owner cần phê duyệt:

- Nhóm người dùng hoặc tỷ lệ lưu lượng ban đầu.
- Thời gian quan sát tối thiểu.
- Metric và ngưỡng mở rộng.
- Điều kiện dừng và rollback.
- Người theo dõi và người có quyền tiếp tục.

Mỗi lần tăng tỷ lệ lưu lượng là một quyết định tiếp tục rollout, cần dựa trên bằng chứng mới. Không nên xem phê duyệt canary ban đầu là phê duyệt tự động cho 100% lưu lượng.

### 11.3. Continuous deployment

Pipeline có thể tự động triển khai khi policy gate đạt. Trong mô hình này, quyền quyết định được ủy quyền trước vào policy, test bắt buộc, giới hạn rollout và cơ chế rollback. Owner vẫn phải chịu trách nhiệm về chính sách, cấu hình, giám sát và phản ứng khi điều kiện vượt ngưỡng.

Tự động triển khai không loại bỏ trách nhiệm; nó chuyển một phần quyết định lặp lại thành quy tắc đã được phê duyệt và kiểm soát.

### 11.4. Emergency release

Release khẩn cấp có thể rút ngắn một số bước nhưng cần có quy trình riêng:

- Điều kiện nào được xem là khẩn cấp.
- Ai có quyền tuyên bố và phê duyệt.
- Kiểm tra tối thiểu không thể bỏ qua.
- Biện pháp giảm thiểu cho kiểm tra chưa thực hiện.
- Cách ghi nhận ngoại lệ và thông báo.
- Thời hạn hoàn tất kiểm tra sau phát hành.
- Review sau sự cố hoặc sau release.

Không nên dùng nhãn emergency để bỏ qua quy trình thông thường khi chỉ có áp lực tiến độ.

## 12. Mẫu bản ghi quyết định phát hành

Một bản ghi ngắn gọn có thể dùng trong ticket, change record hoặc hệ thống quản lý release.

| Trường | Nội dung cần ghi |
|---|---|
| Release ID | Mã release duy nhất |
| Artifact/version | Phiên bản, commit SHA, image digest hoặc checksum |
| Phạm vi | Dịch vụ, tính năng, migration và môi trường |
| Decision | Go, Go with conditions, No-Go hoặc Defer |
| Decision owner | Người/vai trò đưa ra quyết định cuối cùng |
| Người thực hiện | Người triển khai và người giám sát |
| Bằng chứng | Build, test, security, performance, readiness và report |
| Rủi ro còn lại | Mô tả, mức độ, phạm vi và tác động |
| Ngoại lệ | Exception ID, approver, mitigation và ngày hết hạn |
| Điều kiện rollout | Canary, tỷ lệ lưu lượng, metric và thời gian quan sát |
| Dừng/phục hồi | Ngưỡng dừng, rollback/roll-forward và người có quyền kích hoạt |
| Owner hành động | Người phụ trách từng việc còn mở và thời hạn |
| Thời điểm | Thời gian quyết định và cửa sổ triển khai |
| Lịch sử | Thay đổi quyết định, phê duyệt và lý do |

### 12.1. Ví dụ bản ghi

~~~text
Release: ORDERS-2026.11.16-rc2
Artifact: orders-service@sha256:<digest>
Scope: Order API, inventory adapter, payment callback handler
Decision: GO WITH CONDITIONS
Decision owner: Release manager được ủy quyền
Evidence:
  - Unit/component/integration suites: PASS
  - Payment E2E sandbox: BLOCKED (vendor maintenance)
  - Idempotency and callback contract tests: PASS
  - Security scan: PASS
  - Load profile: within agreed SLO
Residual risk:
  - Live sandbox end-to-end confirmation unavailable for this candidate
Mitigation:
  - Limit rollout to canary cohort
  - Monitor callback failures and duplicate transaction signals
  - Re-run sandbox E2E before expanding rollout
Stop authority: On-call service owner
Action owner: Payment integration team
Review deadline: Before rollout expansion
Rollback: Disable new callback path and restore previous handler
~~~

Đây là ví dụ cấu trúc, không phải mẫu phê duyệt mặc định. Nếu chính sách yêu cầu E2E thanh toán phải đạt trước bất kỳ triển khai nào, trạng thái BLOCKED không thể được chuyển thành Go with conditions chỉ bằng bản ghi này.

## 13. Ví dụ thực tế: quyết định phát hành dịch vụ đặt hàng

Giả sử một release thay đổi xử lý callback thanh toán và cập nhật tồn kho. Regression test đạt phần lớn, nhưng một test E2E với sandbox bị blocked do nhà cung cấp bảo trì. Đồng thời, nhóm đã kiểm tra contract, idempotency và luồng xử lý callback bằng môi trường tích hợp.

### 13.1. Bằng chứng và ý kiến

- QA xác nhận test unit, component, integration và contract đạt; E2E sandbox chưa có kết quả.
- Development giải thích thay đổi handler và cung cấp log/trace của các test thay thế.
- Security xác nhận không có thay đổi quyền hoặc dữ liệu nhạy cảm ngoài phạm vi đã đánh giá.
- SRE xác nhận metric callback, duplicate transaction và backlog đã có alert; rollback đã được diễn tập.
- Product đánh giá tác động nghiệp vụ và chấp nhận chỉ triển khai cho nhóm canary nếu điều kiện được đáp ứng.
- Vendor owner xác nhận thời gian sandbox dự kiến hoạt động trở lại.

### 13.2. Quyết định có điều kiện

Decision owner xem xét chính sách hard gate trước. Nếu E2E sandbox là điều kiện bắt buộc không thể miễn trừ, release phải hoãn. Nếu chính sách cho phép ngoại lệ và rủi ro còn lại nằm trong thẩm quyền:

- Ghi exception ID và thời hạn.
- Chỉ mở canary nhỏ.
- Theo dõi callback failure, duplicate và order state mismatch.
- Dừng rollout nếu bất kỳ ngưỡng an toàn nào vượt giới hạn.
- Chạy E2E sandbox trước khi mở rộng.
- Giao service owner quyền dừng và rollback.

### 13.3. Ai chịu trách nhiệm?

QA chịu trách nhiệm về tính chính xác của kết quả test và phần bằng chứng còn thiếu. Vendor owner điều phối xác minh phụ thuộc bên ngoài. SRE/service owner chịu trách nhiệm giám sát và phản ứng. Product owner chấp nhận tác động nghiệp vụ trong thẩm quyền. Release decision owner đưa ra Go/No-Go cuối cùng và ghi rõ điều kiện.

Không ai có thể thay thế trách nhiệm của người khác bằng cách nói "QA đã pass" hoặc "vendor đang bảo trì". Quyết định dựa trên tổng hợp bằng chứng và đúng thẩm quyền.

## 14. Theo dõi trách nhiệm sau khi quyết định

Sau Go hoặc Go with conditions, trách nhiệm vẫn tiếp tục:

- Release owner theo dõi các điều kiện đã phê duyệt.
- Người triển khai xác nhận đúng artifact và cấu hình.
- SRE/on-call theo dõi metric, alert và tín hiệu sự cố.
- QA xác minh smoke/regression sau triển khai theo kế hoạch.
- Product/support theo dõi phản hồi và tác động người dùng.
- Owner ngoại lệ hoàn tất kiểm tra còn thiếu trước hạn.
- Service owner quyết định dừng hoặc phục hồi khi ngưỡng bị vượt.

Một quyết định Go with conditions cần có cơ chế kiểm tra điều kiện tự động hoặc thủ công được chỉ định. Nếu điều kiện không được đáp ứng, phải kích hoạt hành động đã thống nhất; không để điều kiện chỉ tồn tại trong biên bản.

## 15. Đo lường chất lượng của quy trình quyết định

Có thể theo dõi các chỉ số:

- Tỷ lệ release có decision owner được xác định trước.
- Tỷ lệ quyết định có đủ gói bằng chứng và bản ghi.
- Thời gian từ khi readiness hoàn tất đến khi có quyết định.
- Tỷ lệ release bị dừng sau khi bắt đầu rollout.
- Tỷ lệ điều kiện Go with conditions được hoàn tất đúng hạn.
- Số ngoại lệ quá hạn hoặc được gia hạn nhiều lần.
- Tỷ lệ rollback và nguyên nhân.
- Số incident liên quan đến rủi ro đã được chấp nhận.
- Thời gian phát hiện và dừng rollout khi có tín hiệu bất thường.
- Tỷ lệ hành động sau release được đóng đúng hạn.

Không nên tối ưu bằng cách làm cho mọi quyết định đều Go hoặc rút ngắn thời gian phê duyệt bất kể rủi ro. Mục tiêu là quyết định đúng, đủ nhanh, có căn cứ và có thể thực thi.

## 16. Những sai lầm thường gặp

- **Không chỉ định decision owner:** cuộc họp kết thúc nhưng không ai chịu trách nhiệm quyết định.
- **Nhiều người cùng được ghi A:** không rõ ai có tiếng nói cuối cùng.
- **Nhầm người chạy test với người phê duyệt release:** kết quả kiểm thử bị dùng vượt quá ý nghĩa.
- **Cho rằng pipeline xanh đồng nghĩa release an toàn:** bỏ qua rủi ro, môi trường, cấu hình và vận hành.
- **Không phân biệt hard gate và advisory:** điều kiện bắt buộc bị biến thành cảnh báo có thể bỏ qua.
- **Chấp nhận rủi ro sai thẩm quyền:** người không sở hữu rủi ro tự cho phép ngoại lệ.
- **Không ghi ý kiến bất đồng:** mất dấu các cảnh báo đã được nêu trước phát hành.
- **Go không có phạm vi hoặc thời hạn:** quyết định bị dùng cho artifact, môi trường hoặc cửa sổ khác.
- **Không quy định quyền dừng:** đội vận hành phải chờ phê duyệt trong lúc sự cố đang lan rộng.
- **Phê duyệt canary rồi mặc định mở rộng:** không đánh giá bằng chứng mới giữa các bước rollout.
- **Ngoại lệ không có owner và deadline:** điều kiện tạm thời trở thành nợ lâu dài.
- **Không có bản ghi quyết định:** sau incident không thể biết ai đã chấp nhận rủi ro và dựa trên điều gì.

## 17. Checklist liên kết quyết định với trách nhiệm

- [ ] Mỗi loại quyết định phát hành có một decision owner rõ ràng.
- [ ] Responsible, Accountable, Consulted và Informed được phân biệt.
- [ ] Quyền hạn được xác định trong chính sách hoặc ủy quyền.
- [ ] Mỗi hard gate có tiêu chí, nguồn bằng chứng và owner.
- [ ] Rủi ro còn lại được gắn với risk owner có thẩm quyền.
- [ ] QA, Security, Product và SRE xác nhận phần bằng chứng thuộc trách nhiệm của họ.
- [ ] Gói release có artifact/version, phạm vi, test report và trạng thái defect.
- [ ] Ngoại lệ có ID, mitigation, approver, owner và thời hạn.
- [ ] Go, Go with conditions, No-Go và Defer được ghi rõ.
- [ ] Điều kiện rollout có metric, ngưỡng và thời gian quan sát.
- [ ] Quyền dừng, rollback và tiếp tục rollout được quy định.
- [ ] Có người thay thế khi decision owner hoặc on-call vắng mặt.
- [ ] Bất đồng và escalation được ghi nhận.
- [ ] Quyết định được liên kết với release, build và incident.
- [ ] Điều kiện sau phát hành được theo dõi đến khi hoàn tất.

## 18. Luồng quyết định và trách nhiệm phát hành

~~~mermaid
flowchart TD
    A["Tạo release candidate và xác định phạm vi"]
    B["Thu thập bằng chứng build, test, security, performance"]
    C["Các owner xác nhận phần trách nhiệm của mình"]
    D["Tổng hợp hard gate, defect và rủi ro còn lại"]
    E{"Có hard gate chưa đạt?"}
    F["No-Go hoặc xử lý theo quy trình bắt buộc"]
    G["Đánh giá ngoại lệ và thẩm quyền chấp nhận"]
    H["Decision owner đưa ra Go/Conditional Go/Defer"]
    I["Triển khai theo phạm vi và điều kiện đã duyệt"]
    J["Theo dõi metric và điều kiện rollout"]
    K{"Ngưỡng an toàn đạt?"}
    L["Tiếp tục rollout và đóng release"]
    M["Dừng rollout, rollback hoặc xử lý incident"]
    N["Ghi quyết định, owner và hành động còn lại"]
    A --> B --> C --> D --> E
    E -->|Có| F
    E -->|Không| G --> H --> I --> J --> K
    K -->|Có| L --> N
    K -->|Không| M --> N
    F --> N
~~~

Liên kết quyết định phát hành với người chịu trách nhiệm giúp tổ chức biết ai xác nhận bằng chứng, ai đánh giá rủi ro, ai có quyền cho phép triển khai và ai phải hành động khi điều kiện thay đổi. Khi quyền hạn, hard gate, gói bằng chứng, ngoại lệ, quyền dừng và trách nhiệm sau triển khai được quy định rõ, quyết định Go/No-Go trở nên minh bạch và có thể truy vết. Điều đó giúp phát hành có kỷ luật mà vẫn đủ linh hoạt để xử lý các tình huống thực tế.
