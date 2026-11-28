# Incident report: xây dựng báo cáo sự cố bảo mật có bằng chứng và khả năng kiểm chứng

**Incident report** là tài liệu có cấu trúc ghi nhận một sự cố an ninh: điều gì đã xảy ra, hệ thống và dữ liệu nào có thể bị ảnh hưởng, bằng chứng nào hỗ trợ nhận định, tổ chức đã ứng phó thế nào, tác động ra sao và cần làm gì để giảm khả năng tái diễn. Báo cáo có giá trị khi người đọc phân biệt được **sự thật đã xác minh**, **giả thuyết đang điều tra**, **điều chưa biết** và **quyết định được đưa ra trên cơ sở bằng chứng**.

Trong chương **Incident response** thuộc module **SECURITY_SECURITY_ASSURANCE**, báo cáo sự cố còn là một phần của security assurance: xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật, liên kết phân tích rủi ro, yêu cầu, security controls với kiểm thử, audit, khắc phục phát hiện và cải tiến liên tục trong phát triển, vận hành. Một incident report tốt không chỉ kể lại quá trình xử lý mà còn giúp kiểm chứng **control nào hoạt động, control nào thất bại, kết quả khắc phục đã được thử lại hay chưa**.

Bài học trình bày phương pháp viết báo cáo nội bộ có thể kiểm toán, từ lúc ghi nhận ban đầu đến bản kết thúc điều tra và vòng cải tiến. Các yêu cầu báo cáo cho cơ quan quản lý, khách hàng hoặc đối tác phụ thuộc luật, hợp đồng và bối cảnh cụ thể; cần được xác định riêng với bộ phận có trách nhiệm thay vì suy diễn rằng một mẫu báo cáo nội bộ đáp ứng tất cả nghĩa vụ thông báo.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt incident report, incident ticket, nhật ký sự kiện, post-incident review và thông báo bên ngoài.
2. Xác định mục đích, đối tượng đọc, phạm vi, thời điểm chốt dữ liệu và trách nhiệm phê duyệt báo cáo.
3. Tổ chức thông tin thành các phần rõ ràng: tóm tắt điều hành, phân loại, phạm vi, timeline, bằng chứng, tác động, nguyên nhân và khắc phục.
4. Gắn từng nhận định quan trọng với evidence ID, nguồn, thời gian, độ tin cậy và giới hạn điều tra.
5. Xây dựng timeline phù hợp khi nhiều hệ thống có múi giờ, đồng hồ và thời gian thu thập khác nhau.
6. Đánh giá hiệu lực security controls qua bằng chứng phát hiện, ngăn chặn, ứng phó và phục hồi.
7. Định nghĩa corrective/preventive actions có owner, hạn xử lý và phép kiểm lại, phục vụ assurance liên tục.
8. Nhận diện các lỗi báo cáo thường gặp, đặc biệt là khẳng định vượt quá bằng chứng hoặc công bố dữ liệu nhạy cảm không cần thiết.

## 2. Incident report là gì và dùng để làm gì?

### 2.1. Vai trò trong quy trình incident response

Một sự cố có thể bắt đầu từ cảnh báo SOC, phát hiện của người dùng, kết quả pentest, hệ thống giám sát hoặc thông báo bên thứ ba. Trong quá trình xử lý, đội phụ trách cần ghi lại những quyết định và dấu vết kỹ thuật ngay khi chúng xảy ra. Incident report tổng hợp, chuẩn hóa và diễn giải các dữ kiện đó cho người có trách nhiệm.

Các mục đích chính:

- **Hỗ trợ quyết định:** cho quản lý và các đội liên quan biết mức ảnh hưởng, rủi ro còn lại, hành động đang thực hiện và điểm cần phê duyệt.
- **Hỗ trợ điều tra:** cho phép xác định nguồn và thứ tự của các bằng chứng, phân biệt sự kiện xác nhận với khả năng chưa đủ dữ liệu.
- **Truy trách nhiệm:** ghi rõ người chỉ huy sự cố, đội tham gia, hành động đã phê duyệt, thời gian và kết quả.
- **Phục vụ audit:** chứng minh tổ chức có phát hiện, phân loại, phản ứng, bảo toàn bằng chứng và xác minh quá trình phục hồi.
- **Cải tiến kiểm soát:** liên kết nguyên nhân, lỗ hổng kiểm soát và finding với corrective/preventive action có khả năng retest.
- **Giao tiếp:** cung cấp phiên bản thông tin phù hợp cho nhóm kỹ thuật, lãnh đạo, pháp chế, bảo vệ dữ liệu, khách hàng hoặc đối tác.

Một báo cáo chỉ có số lượng alert và các lệnh đã chạy khó chứng minh chất lượng response. Ngược lại, một bài kể chuyện mạch lạc nhưng không có evidence reference cũng khó được người khác kiểm tra độc lập.

### 2.2. Phân biệt các tài liệu

| Tài liệu | Mục đích | Mức độ cập nhật |
|---|---|---|
| **Alert / security event** | Tín hiệu hoặc bản ghi cho thấy điều cần xem xét | Tự động hoặc theo sự kiện |
| **Incident ticket / case** | Điều phối tác vụ, người phụ trách, trạng thái và lịch sử xử lý | Cập nhật liên tục khi ứng phó |
| **Investigation notes** | Ghi nhận quan sát, truy vấn, giả thuyết, kết quả thử | Có thể rất chi tiết và chưa chuẩn hóa |
| **Incident report** | Tổng hợp sự cố có hệ thống, liên kết nhận định với bằng chứng | Bản sơ bộ, các lần cập nhật và bản hoàn chỉnh |
| **Post-incident review / retrospective** | Phân tích yếu tố hệ thống, bài học và cải tiến sau sự cố | Sau khi đủ dữ kiện và ổn định vận hành |
| **External notification** | Thông báo theo nghĩa vụ pháp lý, hợp đồng hoặc đối tượng nhận cụ thể | Theo điều kiện và hạn do nghĩa vụ áp dụng quy định |

Incident report có thể chứa phần lessons learned, nhưng không phải lúc nào cũng thay thế được hoạt động retrospective chuyên sâu. Một bản report gửi ra ngoài có thể cần bản rút gọn, quy trình phê duyệt, giữ bí mật và khung thời hạn riêng.

### 2.3. Câu hỏi mà báo cáo phải trả lời

1. **What:** sự kiện hay hành vi nào đã được xác minh?
2. **When:** dấu hiệu đầu tiên, lúc phát hiện, phân loại, cô lập, phục hồi xảy ra khi nào?
3. **Where:** hệ thống, tài khoản, môi trường, vùng mạng và dữ liệu nào thuộc phạm vi?
4. **Who:** ai là owner, người tham gia xử lý, ai có quyền liên quan? Có xác định được tác nhân tấn công hay chưa?
5. **How:** đường vào, kỹ thuật, chuỗi hành vi và cơ chế ảnh hưởng có bằng chứng gì?
6. **Impact:** ảnh hưởng đã xác nhận và ảnh hưởng tiềm tàng đến bí mật, toàn vẹn, sẵn có, nghiệp vụ và dữ liệu.
7. **Response:** đã làm gì, tại sao, với kết quả nào và còn rủi ro gì?
8. **Evidence:** nhận định xuất phát từ log, snapshot, artifact hoặc phỏng vấn nào?
9. **Next:** control nào phải sửa, ai chịu trách nhiệm, khi nào kiểm tra lại?

Không cần chờ trả lời trọn vẹn tất cả mới viết bản sơ bộ; phần chưa biết phải được ghi rõ và cập nhật theo bằng chứng mới.

## 3. Vòng đời báo cáo và cơ chế phiên bản

### 3.1. Các thời điểm phát hành

| Trạng thái tài liệu | Khi dùng | Nội dung cần ưu tiên |
|---|---|---|
| **Initial / preliminary** | Ngay sau khi xác nhận có incident hoặc nghi vấn đủ nghiêm trọng | Tình hình đã biết, giả thuyết chính, phạm vi sơ bộ, hành động ưu tiên, liên hệ |
| **Update / interim** | Khi phạm vi, tác động, bằng chứng hoặc quyết định quan trọng thay đổi | Những thay đổi so với bản trước, tiến độ response, khoảng trống thông tin |
| **Final investigation report** | Sau khi điều tra đủ theo tiêu chí tổ chức | Timeline có dẫn chứng, kết luận, tác động, RCA với mức độ tin cậy, hành động |
| **Addendum / follow-up** | Khi có bằng chứng mới hoặc hành động khắc phục được xác minh sau khi phát hành final | Phần thay đổi, lý do, bằng chứng và tác động đến kết luận cũ |

Không nên âm thầm sửa báo cáo đã được phê duyệt mà không giữ dấu vết. Nếu phát hiện nhận định cũ sai, phải cập nhật rõ **phiên bản, điểm thay đổi, thời gian, người phê duyệt và kết luận được thay thế**.

### 3.2. Metadata quản trị báo cáo

Một bản báo cáo nên có:

| Trường | Ý nghĩa |
|---|---|
| incident_id | Định danh duy nhất liên kết ticket, log, evidence và actions |
| report_id, version | Xác định bản báo cáo và lịch sử phát hành |
| title, incident_type | Tên mô tả hành vi và loại sự cố, tránh kết luận vượt chứng cứ |
| status | Preliminary, Investigating, Contained, Recovered, Closed hoặc quy ước tổ chức |
| severity, confidence | Mức ưu tiên tác động và mức tin cậy đối với kết luận |
| first_observed_at, detected_at | Tách thời gian hoạt động sớm nhất đã thấy và thời gian tổ chức phát hiện |
| report_cutoff_at | Mốc dữ liệu cuối cùng dùng trong phiên bản báo cáo |
| incident_commander / owner | Người điều phối và chịu trách nhiệm |
| report_author, reviewers | Người soạn, người kiểm tra và phê duyệt |
| classification / audience | Mức độ nhạy cảm, đối tượng được phép xem |
| affected_services | Liên kết tài sản, dịch vụ, owner và scope |
| references | Liên kết tài liệu, ticket, evidence ID, report bổ sung |

Có thể có những trạng thái xử lý sự cố song song với trạng thái báo cáo. Ví dụ, incident đã được containment nhưng tài liệu vẫn đang chờ kiểm tra độc lập. Không đặt tên trạng thái gây hiểu lầm rằng **đóng ticket** là đã hoàn tất mọi hành động phòng ngừa.

### 3.3. Quy trình phê duyệt

Người phụ trách sự cố xác nhận phần diễn biến, đại diện hạ tầng/ứng dụng xác nhận thay đổi và phục hồi, đội security assurance xác minh liên kết control và bằng chứng. Khi có dữ liệu cá nhân, nghĩa vụ hợp đồng, bằng chứng pháp lý hoặc yêu cầu thông báo, cần có chủ thể có thẩm quyền về pháp lý, privacy và truyền thông tham gia theo quy trình nội bộ.

Mục tiêu của review là phát hiện tuyên bố thiếu căn cứ, thông tin sai phạm vi và hành động chưa kiểm chứng. Review không nên làm mất phần mô tả bất định cần thiết.

## 4. Cấu trúc tổng thể của một incident report

Một bố cục thực tế, có thể điều chỉnh theo độ nghiêm trọng:

1. **Thông tin định danh và trạng thái:** incident ID, severity, version, owner, report cutoff.
2. **Executive summary:** điều đã xác nhận, ảnh hưởng, response, tình trạng hiện tại, rủi ro còn lại.
3. **Scope và bối cảnh hệ thống:** asset, service, dữ liệu, ranh giới tin cậy và phụ thuộc.
4. **Detection và initial assessment:** nguồn alert, cách phân loại, thời điểm nhận biết, giả thuyết ban đầu.
5. **Timeline có evidence reference:** các mốc quan trọng, nguồn thời gian, confidence.
6. **Technical findings:** kỹ thuật, đường vào, hành vi và bằng chứng ủng hộ/phản bác.
7. **Impact assessment:** bí mật, toàn vẹn, sẵn có, nghiệp vụ, khách hàng và hệ thống liên đới.
8. **Response actions:** triage, containment, eradication, recovery, validation, ưu tiên và chủ sở hữu.
9. **Root cause và contributing factors:** nguyên nhân đã xác nhận, điều chưa xác định, điều kiện hệ thống cho phép sự cố.
10. **Control effectiveness và assurance gaps:** control có hiệu lực, thất bại, chưa kiểm chứng.
11. **Corrective/preventive actions:** finding, owner, priority, deadline, test/retest.
12. **Residual risk và quyết định còn mở:** ngoại lệ, phê duyệt, giám sát bổ sung.
13. **Bài học và liên hệ chương trình bảo mật:** thay đổi detection, policy, architecture, training, tabletop.
14. **Evidence register / phụ lục:** nguồn, checksum, custody, truy vấn đã dùng, báo cáo chi tiết và quyền truy cập.

Mức độ chi tiết tùy audience. Executive summary nên đủ để lãnh đạo ra quyết định mà không phải đọc log thô; phần kỹ thuật và appendix cho phép người kiểm tra tái dựng lập luận.

## 5. Executive summary: ngắn nhưng có thể tin cậy

Một đoạn mở đầu tốt thường trả lời bốn điểm: **điều đã xảy ra, ảnh hưởng đã xác nhận, trạng thái khắc phục và những gì chưa biết**.

### 5.1. Ví dụ mô tả chưa đạt

> Hệ thống bị hacker tấn công dữ dội gây rò rỉ dữ liệu nghiêm trọng. Đội kỹ thuật đã khắc phục hoàn toàn và mọi thứ an toàn.

Đoạn trên thiếu asset, thời điểm, bằng chứng, phạm vi và có thể chứa khẳng định vượt quá dữ liệu. Không được kết luận "rò rỉ" khi chỉ quan sát thấy quyền truy cập bất thường mà chưa xác định việc đọc hoặc đưa dữ liệu ra ngoài.

### 5.2. Ví dụ mô tả có trách nhiệm

> Ngày 28/11/2026, đội giám sát phát hiện các lệnh API bất thường từ một workload identity thuộc dịch vụ thanh toán. Audit log xác nhận danh tính này được dùng để thay đổi một chính sách truy cập ngoài quy trình. Quyền của danh tính đã bị thu hồi và thay đổi chính sách đã được hoàn nguyên. Đến mốc báo cáo 11:30 UTC, chưa có bằng chứng xác nhận dữ liệu khách hàng bị truy xuất hoặc chuyển ra ngoài; khả năng truy cập dữ liệu trong khoảng 09:05–09:31 UTC vẫn đang được đối chiếu với audit log nguồn lưu trữ. Đội hạ tầng và bảo mật đã tăng giám sát, đánh giá secret liên quan và triển khai biện pháp ngăn thay đổi quyền tương tự.

Ví dụ mang tính giả định, không mô tả sự cố thật. Cách viết tách được **hành vi xác nhận**, **khoảng rủi ro** và **điều còn chưa kết luận**.

### 5.3. Mức độ khẳng định phù hợp

| Trạng thái chứng cứ | Cách viết nên dùng |
|---|---|
| Có log và đối chiếu độc lập | "Audit log A và B xác nhận hành động X tại thời điểm Y." |
| Một nguồn tin cậy nhưng chưa đối chiếu | "Nguồn A ghi nhận X; đang đối chiếu với nguồn B." |
| Suy luận hợp lý từ chuỗi dấu vết | "Bằng chứng hiện tại phù hợp với giả thuyết X; chưa loại trừ Y." |
| Chưa có dữ liệu | "Chưa xác định được X do thiếu dữ liệu trong khoảng Y." |
| Không tìm thấy dấu hiệu trong tập kiểm tra | "Không phát hiện X trong các nguồn và khoảng thời gian đã kiểm." |
| Kiểm tra không bao phủ toàn bộ | "Kết luận chỉ áp dụng cho phạm vi A, B; phạm vi C chưa được đánh giá." |

Điều này giúp tránh nhầm **không tìm thấy bằng chứng** với **bằng chứng rằng sự việc không xảy ra**.

## 6. Phân loại sự cố và xác định phạm vi

### 6.1. Severity và confidence khác nhau

**Severity** thể hiện mức ưu tiên xử lý hoặc ảnh hưởng của sự cố theo chính sách nội bộ. **Confidence** thể hiện mức độ chắc chắn của nhận định. Hai trục phải được đánh giá riêng.

Ví dụ:

- Mức độ nghiêm trọng **cao**, confidence **thấp**: có khả năng hệ thống có dữ liệu nhạy cảm bị truy cập nhưng chưa thu đủ log.
- Mức độ nghiêm trọng **trung bình**, confidence **cao**: đã xác nhận một cấu hình sai tại môi trường thử, không có đường truy cập dữ liệu sản xuất.
- Severity có thể được **nâng** khi scope tăng hoặc có bằng chứng mới; cần ghi lý do và lịch sử thay đổi.

Không tự tạo quy tắc điểm số cho toàn tổ chức. Báo cáo phải dẫn định nghĩa severity đang áp dụng và cơ sở gắn mức.

### 6.2. Ranh giới sự cố

Phạm vi phải thể hiện rõ:

| Thành phần | Cần mô tả |
|---|---|
| Dịch vụ | Tên, owner, môi trường, dependency quan trọng |
| Tài khoản/danh tính | Identity người, service account, role, token, phiên truy cập |
| Tài sản | Host, container, cluster, cloud account/project/subscription, database, bucket |
| Dữ liệu | Phân loại, chủ thể dữ liệu, nhóm đối tượng có thể bị ảnh hưởng |
| Mạng | Phạm vi kết nối, đường vào, kết nối nội bộ và egress đáng chú ý |
| Thời gian | First known activity, last known activity và giới hạn quan sát |
| Ngoài phạm vi | Hệ thống được loại trừ có căn cứ, hệ thống chưa thể kiểm tra |

Danh sách **"không bị ảnh hưởng"** cần dựa trên dữ liệu kiểm tra có phạm vi rõ. Nếu chưa có telemetry từ một cluster liên thông, phải ghi **chưa xác định**, thay vì mặc định không ảnh hưởng.

### 6.3. Đánh giá tác động theo CIA và nghiệp vụ

- **Confidentiality (bí mật):** có thể hoặc đã có việc đọc, xuất, sao chép dữ liệu trái phép?
- **Integrity (toàn vẹn):** có thay đổi quyền, dữ liệu, cấu hình hoặc artifact không được phép?
- **Availability (sẵn có):** gián đoạn dịch vụ, giảm chất lượng hoặc thất bại giao dịch?
- **Business/operations:** số người dùng/dịch vụ bị ảnh hưởng, khung thời gian, SLA và chi phí khắc phục.
- **Privacy/third-party:** dữ liệu cá nhân, hợp đồng đối tác hoặc nghĩa vụ liên quan có cần đánh giá riêng không?

**Confirmed impact**, **potential impact** và **unknown impact** phải được ghi tách biệt. Không định lượng số bản ghi bị lộ nếu chỉ biết phạm vi quyền đọc.

## 7. Xây dựng timeline dựa trên chứng cứ

Timeline giúp liên kết diễn biến kỹ thuật, quyết định response và mốc kinh doanh. Cần ghi mốc thời gian theo chuẩn thống nhất, ưu tiên UTC với timezone rõ, và giữ timestamp gốc trong evidence.

### 7.1. Những loại thời gian dễ nhầm

- **Event time:** lúc hệ thống nguồn cho biết hành động xảy ra.
- **Detection time:** lúc hệ thống hoặc người có trách nhiệm nhận biết tín hiệu đáp ứng tiêu chí phát hiện.
- **Alert delivery time:** lúc cảnh báo đến queue hoặc kênh nhận.
- **Triage time:** lúc đội phụ trách bắt đầu xác minh.
- **Containment time:** lúc biện pháp hạn chế thực sự có hiệu lực.
- **Recovery time:** lúc hệ thống đáp ứng tiêu chí phục hồi đã đặt ra.
- **Evidence collection time:** lúc dữ liệu được thu hoặc xuất cho điều tra.
- **Report cutoff time:** mốc thông tin cuối cùng được đưa vào phiên bản báo cáo.

Không thay thế event time bằng ingest time nếu hai mốc khác nhau. Với nguồn có clock drift, timestamp chỉ nên được coi là ước lượng trong sai số có thể chứng minh.

### 7.2. Timeline mẫu

Tình huống giả định: credential workload bị sử dụng để sửa IAM policy trên cloud.

| Thời gian (UTC) | Diễn biến | Bằng chứng | Trạng thái |
|---|---|---|---|
| 09:05 | Có API call thay đổi quyền từ workload identity | E-001: audit API | **Đã xác nhận** |
| 09:12 | Detection rule tạo cảnh báo | E-002: rule execution/alert | **Đã xác nhận** |
| 09:17 | Analyst nhận case và bắt đầu triage | E-003: case history | **Đã xác nhận** |
| 09:22 | Đội phản ứng xác nhận thay đổi ngoài quy trình | E-004: change record + audit | **Đã xác nhận** |
| 09:31 | Thu hồi quyền của workload identity; thử lại cho thấy lệnh tương đương bị từ chối | E-005: IAM change + authorization test | **Đã xác nhận trong phạm vi thử** |
| 09:46 | Hoàn nguyên policy bị thay đổi | E-006: policy revision/diff | **Đã xác nhận** |
| 10:10 | Bắt đầu đối chiếu khả năng truy cập dữ liệu | E-007: investigation ticket | **Đang điều tra** |
| 11:25 | Dịch vụ hoàn tất kiểm tra chức năng và vận hành ổn định trong phạm vi đã đánh giá | E-008: test/monitoring | **Đã xác nhận trong phạm vi thử** |

Các ID và mốc trên chỉ dùng để học cách trình bày. Cần lưu **đường dẫn/nguồn evidence thực tế** và thông tin người xác minh.

### 7.3. Đo thời gian response đúng nghĩa

Theo bảng giả định:

- Từ hành động được quan sát đầu tiên (09:05) đến alert (09:12): **7 phút**.
- Từ alert (09:12) đến triage (09:17): **5 phút**.
- Từ hành động đầu tiên (09:05) đến containment được xác minh (09:31): **26 phút**.
- Từ hành động đầu tiên (09:05) đến phục hồi được xác minh (11:25): **2 giờ 20 phút**.

Những số liệu trên là độ trễ **trong ví dụ**, không tự biến thành MTTD/MTTR của tổ chức. Mean Time to Detect/Respond cần xác định quần thể incident, cách tính và mốc thống nhất. Nếu hoạt động của attacker bắt đầu trước 09:05 nhưng không có telemetry, đây chỉ là thời gian từ **earliest observed activity**, chưa chắc là thời gian từ lúc thực sự bắt đầu compromise.

### 7.4. Xử lý sai lệch đồng hồ và sự kiện đến muộn

Khi ghép log từ nhiều nguồn:

1. Lưu cả timestamp gốc và timestamp theo UTC sau khi chuẩn hóa.
2. Ghi nguồn đồng hồ, múi giờ, clock drift hoặc timestamp không đáng tin.
3. Phân biệt timestamp của sự kiện, lúc hệ thống tiếp nhận và lúc điều tra thu thập.
4. Dùng request ID, trace ID, identity và thứ tự logic để hỗ trợ tương quan.
5. Ghi rõ những mốc chỉ biết theo khoảng ước lượng hoặc thứ tự tương đối.
6. Cập nhật timeline khi log đến muộn hoặc có bằng chứng bổ sung, giữ dấu vết phiên bản.

Một timeline chính xác đến từng mili giây nhưng các nguồn chưa đồng bộ không có nghĩa đã xác định được thứ tự thực tế chính xác tương ứng.

## 8. Evidence register và chain of custody

### 8.1. Evidence register

Mọi nhận định kỹ thuật quan trọng cần tham chiếu đến evidence ID ổn định thay vì phụ thuộc vào một ảnh chụp màn hình không rõ nguồn.

| Trường | Công dụng |
|---|---|
| evidence_id | Định danh duy nhất của hiện vật |
| source_system | Nguồn dữ liệu hoặc hệ thống tạo ra |
| artifact_type | Audit log, SIEM export, disk/memory image, config snapshot, ticket, phỏng vấn |
| source_time_range | Khoảng thời gian mà artifact phản ánh |
| collected_at, collected_by | Thời điểm và danh tính thu thập |
| collection_method | Công cụ/truy vấn/phương pháp và phiên bản |
| original_location | Nơi lưu bản gốc hoặc tham chiếu |
| digest/signature | Hash/chữ ký nếu áp dụng, cùng trust anchor |
| custody_reference | Hồ sơ bàn giao, truy cập và chuyển đổi |
| access_classification | Mức nhạy cảm và quyền đọc |
| limitations | Các giới hạn: retention, mất log, sampling, clock drift |

Không cần đưa tất cả dữ liệu thô vào thân báo cáo. Có thể lưu trong kho bằng chứng có phân quyền, ghi ID và đường dẫn truy xuất phù hợp.

### 8.2. Chuỗi xử lý chứng cứ

~~~mermaid
flowchart LR
    S["Nguồn bằng chứng"] --> C["Thu thập có ghi nhận"]
    C --> I["Hash / verify / metadata"]
    I --> V["Kho bảo quản bản gốc"]
    V --> A["Bản sao phân tích"]
    A --> F["Finding và timeline"]
    F --> R["Kết luận có dẫn chứng"]
    V --> U["Audit quyền / custody"]
~~~

Một quy trình tối thiểu:

1. Nhận diện artifact và phạm vi cần thu, quyết định quyền được phép.
2. Thu bằng công cụ phù hợp, ghi lệnh/truy vấn, thời điểm, người thu và điều kiện môi trường.
3. Tính hash trên đúng byte của artifact khi thích hợp; so với manifest/chữ ký nguồn nếu có.
4. Bảo quản bản gốc theo retention, phân quyền và quy trình xử lý dữ liệu.
5. Phân tích trên bản sao; ghi rõ redaction, normalization hoặc chuyển đổi.
6. Mỗi lần bàn giao/cấp quyền truy cập có log ai, khi nào, mục đích và đối tượng.
7. Kiểm chứng lại trước khi dùng kết quả cho báo cáo kết thúc điều tra.

**Hash khớp chỉ cho biết bản hiện tại khớp với mốc đã tin cậy; không chứng minh sự kiện trong log là đúng thực tế.** Nếu nguồn bị chiếm quyền trước khi log được tạo, cần đối chiếu từ hệ thống độc lập.

### 8.3. Bảo vệ dữ liệu nhạy cảm

Incident evidence có thể chứa:

- Credential, token, secret hoặc private key.
- IP, username, email, thông tin cá nhân và dữ liệu khách hàng.
- Cấu hình truy cập, đường dẫn quản trị và chi tiết kỹ thuật nhạy cảm.
- Các cuộc trao đổi, nhận định pháp lý hoặc thông tin liên quan đến trách nhiệm hợp đồng.

Báo cáo phục vụ lãnh đạo nên dùng mức chi tiết cần thiết; phụ lục nhạy cảm có thể được giới hạn. Không gửi log thô chứa token vào nhóm chat hoặc tài liệu công khai. **Redaction phải có quy trình rõ** để vẫn giữ khả năng kiểm chứng bằng bản gốc được bảo vệ.

## 9. Technical findings: diễn giải bằng chứng thành kết luận

### 9.1. Cấu trúc một finding điều tra

Một finding nên trình bày:

1. **Claim:** điều gì được phát hiện.
2. **Evidence:** ID nguồn hỗ trợ, thời gian và vùng kiểm tra.
3. **Method:** truy vấn, phép so sánh, phân tích hoặc test.
4. **Confidence:** mức độ tin cậy và lý do.
5. **Alternative hypotheses:** giả thuyết khác và bằng chứng ủng hộ/phản bác.
6. **Limitations:** mất log, chưa kiểm tra một hệ thống, thời gian không chắc chắn.
7. **Security implication:** rủi ro hoặc control bị ảnh hưởng.
8. **Next step:** hành động điều tra hoặc khắc phục.

Ví dụ:

> **Finding F-01 — Thay đổi policy ngoài quy trình.** Cloud audit log E-001 ghi nhận hành động thay đổi policy từ workload identity vào 09:05 UTC. Đối chiếu change register E-004 không tìm thấy phê duyệt tương ứng cho account và khoảng thời gian đó. Policy snapshot E-006 cho thấy quyền đọc rộng hơn baseline. Kết luận có độ tin cậy cao về việc xảy ra thay đổi ngoài quy trình trong phạm vi account đã kiểm; chưa xác định nguyên nhân credential được sử dụng bởi ai.

Một finding có thể xác nhận hành vi và ảnh hưởng mà vẫn **chưa kết luận được danh tính con người đứng sau**.

### 9.2. Một tuyên bố không nên viết vượt mức dữ liệu

- "Tài khoản bị hack" có thể cần chuyển thành "Có dấu hiệu sử dụng credential ngoài mô hình hành vi được phép; chưa xác định cách credential bị lộ".
- "Không rò rỉ dữ liệu" có thể cần chuyển thành "Chưa phát hiện hoạt động truy xuất bất thường trong các log và khung thời gian hiện có; còn khoảng telemetry chưa được xác minh".
- "Đã xử lý triệt để" có thể cần chuyển thành "Đã thu hồi credential A và kiểm tra lại với phép thử B; còn chờ đánh giá các credential cùng nhóm".

Trong báo cáo, **unknown** là kết quả có giá trị quản trị khi đi kèm lý do, kế hoạch thu thập bổ sung và quyết định giảm rủi ro phù hợp.

### 9.3. Phân biệt kỹ thuật, dấu hiệu và attribution

Log cho thấy một IP hoặc principal thực hiện lệnh không tự chứng minh danh tính tác nhân thật. Địa chỉ IP có thể là proxy, VPN hoặc hạ tầng dùng chung. Principal có thể được dùng bằng credential bị đánh cắp. Đánh giá attribution cần bằng chứng riêng và mức confidence; không tùy tiện gắn tên cá nhân, nhóm hay quốc gia khi chỉ có telemetry kỹ thuật.

### 9.4. Các quyết định phản ứng cũng cần bằng chứng

Một hành động chứa rủi ro vận hành có thể được lựa chọn trước khi điều tra đầy đủ, ví dụ vô hiệu hóa khóa truy cập gây ảnh hưởng cho ứng dụng. Báo cáo nên ghi:

- Vì sao cần hành động tại thời điểm đó.
- Ai có thẩm quyền phê duyệt hoặc tình huống khẩn cấp áp dụng.
- Dự kiến ảnh hưởng tới nghiệp vụ.
- Cách thực thi, thời điểm có hiệu lực và phép kiểm hiệu quả.
- Kết quả, side effects và phương án rollback/khôi phục nếu phù hợp.

Điều này giúp audit thấy response được quản trị theo rủi ro và có khả năng giải thích.

## 10. Response actions và tiêu chí đóng từng giai đoạn

### 10.1. Các nhóm hoạt động

| Giai đoạn | Câu hỏi đánh giá | Bằng chứng nên thu |
|---|---|---|
| **Triage** | Tín hiệu có đúng đối tượng, đủ căn cứ và cần kích hoạt incident không? | Alert, nguyên tắc phân loại, case history |
| **Analysis** | Phạm vi, đường vào và ảnh hưởng đã được kiểm tra theo giả thuyết nào? | Timeline, truy vấn, evidence ID, hypotheses |
| **Containment** | Biện pháp giới hạn còn hiệu lực và có ngăn hành vi thuộc phạm vi không? | IAM/network changes, deny test, monitoring |
| **Eradication** | Nguyên nhân hoặc artifact bị kiểm soát đã bị loại bỏ trong phạm vi nào? | Image re-deploy, secret revoke, cấu hình sửa, scan/test |
| **Recovery** | Chức năng và tính an toàn tối thiểu đã được kiểm chứng lại chưa? | Functional tests, config checks, telemetry baseline |
| **Post-incident monitoring** | Có dấu hiệu tái diễn, lối đi chưa xử lý hoặc dịch vụ bị ảnh hưởng phụ không? | Alert, hunting result, monitoring report |
| **Lessons learned** | Control nào cần thay đổi và ai thực hiện? | Findings, action register, retest evidence |

Một công việc có thể diễn ra đồng thời với công việc khác; tên giai đoạn không nhất thiết là mốc thời gian tuyệt đối. Ví dụ, bảo toàn bằng chứng phải diễn ra sớm khi có nguy cơ log/host bị xóa, kể cả khi containment khẩn cấp đang được thực hiện.

### 10.2. Kiểm chứng containment

Việc đã áp một chính sách chặn không đồng nghĩa containment thực sự hiệu quả. Cần thử hành vi bị cấm từ đúng danh tính, đường truy cập hoặc vùng tài sản trong phạm vi an toàn. Cần theo dõi token phiên cũ, quyền thừa kế, credential dự phòng và những hệ thống có thể chưa nhận thay đổi. Nếu chưa thể kiểm thử trực tiếp, ghi giới hạn và phương án quan sát bù trừ.

### 10.3. Kiểm chứng recovery

Hệ thống phục hồi cần đáp ứng đồng thời:

- Chức năng nghiệp vụ quan trọng hoạt động theo tiêu chí đã định.
- Cấu hình, quyền, khóa và image thuộc phạm vi được xác minh đúng baseline.
- Các đường phát hiện và logging cần thiết trở lại hoạt động, có test end-to-end nếu phù hợp.
- Không còn dấu hiệu tấn công đã biết trong phạm vi giám sát được kiểm.
- Những ngoại lệ, rủi ro còn lại được ghi và có owner.
- Có quyết định phê duyệt phục hồi từ người có thẩm quyền.

"Service trả HTTP 200" chỉ chứng minh một mặt của khả năng vận hành; không tự chứng minh nguyên nhân sự cố đã được loại bỏ hoặc dữ liệu không bị sửa.

## 11. Root cause analysis: từ diễn biến đến nguyên nhân có căn cứ

Root cause analysis (RCA) nhằm xác định **cơ chế và điều kiện hệ thống dẫn đến sự cố**, làm rõ vì sao các lớp phòng ngừa, phát hiện hoặc phản ứng không đạt mục tiêu. RCA không nên chỉ kết thúc bằng nhận định "do nhân viên sai" hoặc "do hacker khai thác".

### 11.1. Phân biệt các lớp nguyên nhân

| Lớp phân tích | Câu hỏi | Ví dụ giả định |
|---|---|---|
| **Trigger / initiating event** | Hành động hoặc điều kiện nào khởi phát chuỗi được quan sát? | Một workload identity gửi yêu cầu sửa IAM policy |
| **Entry point / exposure** | Tại đâu kẻ tấn công hoặc lỗi vận hành có thể tác động? | Token tồn tại ở runtime không phù hợp |
| **Technical mechanism** | Thao tác nào cho phép vượt quyền hoặc ảnh hưởng tài sản? | Quyền policy update rộng hơn nhu cầu |
| **Contributing factors** | Điều kiện nào làm khả năng xảy ra hoặc tác động tăng lên? | Thiếu đánh giá quyền định kỳ, thiếu boundary policy |
| **Detection gap** | Vì sao phát hiện không sớm hơn hoặc không đủ ngữ cảnh? | Cloud audit có nhưng rule alert bị suppression |
| **Response gap** | Vì sao containment hoặc recovery chậm, có thiếu playbook? | Không rõ owner quyền quản trị workload |
| **Systemic/process cause** | Điều gì trong quy trình cho phép lỗi tồn tại và tái diễn? | Pipeline tạo service identity không bắt buộc review IAM |

Ví dụ, câu "lỗi do lộ token" mới mô tả một yếu tố cần điều tra. RCA cần xem bằng chứng về cách token có thể bị lấy, quyền sử dụng token, lý do hệ thống không chặn thay đổi nguy hiểm và vì sao việc phát hiện chỉ xảy ra sau một khoảng thời gian.

### 11.2. Không đưa mọi giả thuyết thành nguyên nhân xác nhận

Giả sử log chứng minh một credential đã thực hiện hành động bất thường. Tuy nhiên, chưa tìm thấy chứng cứ credential đã bị lấy từ kho secrets, tệp build hay bộ nhớ tiến trình.

Một báo cáo tốt có thể viết:

- **Đã xác nhận:** credential của workload identity A được dùng để gọi API B.
- **Đã xác nhận:** role A có quyền thay đổi policy C ngoài nhu cầu của workload.
- **Giả thuyết:** credential có thể đã bị lộ qua một quy trình debug; chưa có bằng chứng đủ xác nhận.
- **Đã loại trừ trong phạm vi:** không tìm thấy thay đổi trong pipeline cấp phát credential trong kỳ đã kiểm.
- **Chưa thể xác định:** nguồn gốc người thực hiện và cách họ có credential.

RCA phải cho phép **"chưa xác định được đường vào"** khi dữ liệu không đủ; vẫn có thể khắc phục quyền quá rộng và giám sát thiếu mà không chờ kết luận tuyệt đối.

### 11.3. Công cụ phân tích nguyên nhân

Các phương pháp có thể dùng:

- **5 Whys:** đặt câu hỏi liên tiếp để lần đến cơ chế hệ thống, tránh suy diễn câu trả lời khi không có chứng cứ.
- **Causal graph:** biểu diễn quan hệ nguyên nhân, điều kiện, hành vi, phát hiện và tác động.
- **Fault tree:** mô hình các điều kiện kết hợp dẫn đến sự kiện không mong muốn.
- **Barrier/control analysis:** xác định lớp phòng ngừa, phát hiện, đáp ứng nào tồn tại, hoạt động hoặc không đạt.
- **Timeline correlation:** đối chiếu chuỗi event và thay đổi để phân biệt sự kiện đồng thời với quan hệ nhân quả.

Sơ đồ causal graph minh họa:

~~~mermaid
flowchart TD
    P["Workload identity có quyền rộng"] --> A["API thay đổi policy được chấp nhận"]
    C["Credential được sử dụng ngoài quy trình"] --> A
    A --> I["Policy cấp quyền đọc rộng hơn baseline"]
    L["Detection rule không có coverage phù hợp"] --> D["Cảnh báo đến muộn"]
    I --> R["Tăng khả năng truy cập dữ liệu"]
    D --> R
    R --> U["Impact thực tế cần kiểm tra từ data audit"]
~~~

Sơ đồ thể hiện **mô hình giả định**. Trong báo cáo thật, mỗi cạnh nhân quả quan trọng phải dựa trên evidence hoặc được gắn trạng thái hypothesis; không biến sơ đồ trở thành kết luận tự động.

## 12. Đánh giá hiệu lực security controls từ sự cố

Sự cố là một cơ hội kiểm tra cách security controls hoạt động trong tình huống thực. Nhưng **việc xảy ra incident không có nghĩa tất cả control đều thất bại**: một số control đã phát hiện, cô lập hoặc giới hạn phạm vi đúng như thiết kế.

### 12.1. Mapping từ rủi ro tới control và bằng chứng

| ID | Control liên quan đến báo cáo/response | Assertion kiểm chứng | Evidence mẫu |
|---|---|---|---|
| **IRR-01** | Incident classification | Có tiêu chí kích hoạt và mức severity được áp nhất quán | Case intake, classification decision |
| **IRR-02** | Ownership và escalation | Incident có commander/owner, phân quyền và escalation rõ | On-call/assignments, approval records |
| **IRR-03** | Timely detection | Đường phát hiện tạo alert đúng scope/kỳ yêu cầu | Event, rule hit, alert history |
| **IRR-04** | Telemetry completeness | Nguồn log cần thiết có dữ liệu đủ phạm vi và thời gian | Inventory, data-source coverage, pipeline metrics |
| **IRR-05** | Evidence preservation | Chứng cứ quan trọng được thu, bảo vệ và đối chiếu integrity | Evidence register, hashes, custody |
| **IRR-06** | Triage/analysis | Mỗi quyết định chính có dữ liệu và reasoning có thể kiểm tra | Case notes, query/evidence references |
| **IRR-07** | Containment effectiveness | Hành vi gây hại bị giới hạn trong scope đã xác nhận | IAM/network change, deny test, monitoring |
| **IRR-08** | Eradication verification | Đường tấn công/credential/artifact nằm trong scope được xử lý | Revoke, rebuild, scan, validation results |
| **IRR-09** | Recovery safety | Dịch vụ đạt tiêu chí chức năng và cấu hình bảo mật | Functional test, baseline check, sign-off |
| **IRR-10** | Stakeholder communication | Đúng nhóm nhận thông tin, có lịch sử cập nhật và phê duyệt | Communications log, report version |
| **IRR-11** | Impact assessment | Confirmed/potential/unknown impact được tách và có căn cứ | Data audit, asset inventory, service telemetry |
| **IRR-12** | Root cause and contributing factors | Kết luận về nguyên nhân được gắn evidence/confidence | Findings, causal analysis, assumptions |
| **IRR-13** | Corrective action tracking | Action có owner, due date, tiêu chí đóng và retest | Action register, change records, tests |
| **IRR-14** | Lessons learned integration | Bài học được chuyển thành thay đổi policy, control hoặc diễn tập | Updated baseline, runbook, validation cycle |
| **IRR-15** | Residual risk governance | Rủi ro còn mở được chấp thuận/giám sát đúng thẩm quyền | Risk record, exception, review date |

### 12.2. Kết luận theo từng control

Đề xuất phân biệt:

- **PASS_WITH_SCOPE:** bằng chứng và phép kiểm hỗ trợ assertion đã được xác nhận trong phạm vi nêu rõ.
- **FAIL:** có chứng cứ control không đáp ứng tiêu chí bắt buộc.
- **INCONCLUSIVE:** chứng cứ hiện tại không đủ để kết luận đạt hoặc không đạt.
- **NOT_TESTED:** chưa có phép kiểm thích hợp.
- **NOT_APPLICABLE:** có lý do phù hợp để control không áp trong scope.
- **ACCEPTED_RISK / EXCEPTION:** control chưa đạt nhưng đã có quyết định chấp nhận có điều kiện; không đổi thành PASS.

Ví dụ, alert được tạo sau 7 phút có thể chứng minh hệ thống đã phát hiện **hành vi mẫu**. Nó không đủ để kết luận mọi đường leo thang quyền đều được bao phủ hoặc việc xử lý cảnh báo luôn đúng SLA.

### 12.3. Evidence quality và assurance limit

Một report có chất lượng cần ghi được:

1. **Coverage:** nguồn dữ liệu và tài sản nào đã kiểm, còn thiếu phần nào?
2. **Freshness:** thời điểm evidence được thu, mốc chốt kỳ, có thay đổi sau đó không?
3. **Integrity:** bằng chứng có cơ chế bảo vệ và đối chiếu gì?
4. **Reproducibility:** truy vấn, script hoặc test có đủ thông tin để chạy lại theo quyền thích hợp không?
5. **Independence:** chứng cứ có đến từ nhiều nguồn độc lập khi cần không?
6. **Confidence:** kết luận dựa trên dấu vết trực tiếp hay suy luận?
7. **Limitations:** thông tin chưa đủ, hệ thống nằm ngoài scope, downtime của logging, sampling hoặc clock skew.

Không nên dùng chữ **"compliant"** hay **"fully secure"** cho toàn bộ môi trường chỉ dựa trên một incident review. Kết luận phải tương ứng với control và phạm vi đã có bằng chứng.

## 13. Corrective action và preventive action

### 13.1. Phân biệt hành động

- **Immediate containment:** hạn chế thiệt hại đang diễn ra (ví dụ khóa credential bị nghi lạm dụng).
- **Eradication:** xử lý phương tiện hoặc trạng thái nguy hiểm liên quan sự cố (ví dụ loại bỏ persistence, sửa quyền).
- **Corrective action:** sửa nguyên nhân làm control không đáp ứng kỳ vọng (ví dụ thay policy tạo role để không cấp quyền rộng).
- **Preventive action:** giảm khả năng lỗi tương tự xảy ra trong các hệ thống hoặc quy trình khác (ví dụ policy-as-code, review/đào tạo).
- **Detection improvement:** bổ sung telemetry, rule, playbook và phép kiểm để nhận biết sớm hơn.
- **Assurance action:** kiểm tra lại hiệu lực và tính bền vững của những thay đổi đã triển khai.

Các nhóm có thể giao nhau. Điều quan trọng là mỗi action có **tiêu chí kết thúc đo được**, tránh chỉ ghi "nâng cao bảo mật" hoặc "rà soát định kỳ".

### 13.2. Action register minh họa

| Action ID | Finding liên kết | Kết quả mong đợi | Owner | Hạn giả định | Bằng chứng đóng |
|---|---|---|---|---|---|
| AC-01 | F-01: IAM quá quyền | Role workload không thể sửa policy ngoài nhu cầu | Platform IAM | 2026-12-02 | Effective permission review + deny test |
| AC-02 | F-02: thiếu detection | Rule phát hiện thay đổi policy ở mọi account production trong inventory | Detection team | 2026-12-04 | Inventory đối soát + positive/negative end-to-end test |
| AC-03 | F-03: quản lý credential | Workload lấy credential ngắn hạn theo mô hình approved | Application team | 2026-12-10 | Cấu hình, pipeline, test rotation/revocation |
| AC-04 | F-04: gap response | Playbook xác định owner, bước containment và escalation | Incident response lead | 2026-12-06 | Diễn tập tabletop và kết quả thực hành |
| AC-05 | F-05: log coverage | Kho log ghi nhận đủ nhóm sự kiện theo yêu cầu | Cloud security | 2026-12-08 | Data-source coverage, test event, integrity check |

Ngày hạn và danh tính owner là ví dụ. Trong thực tế phải căn cứ severity, khả năng thực hiện và phê duyệt mức rủi ro.

### 13.3. Khi nào được đóng action?

Một action có thể xem là **đã triển khai** khi thay đổi được đưa vào hệ thống nhưng chưa chắc là **đã chứng minh hiệu lực**. Cần ít nhất:

1. Có ticket/change record liên kết đúng finding.
2. Có thay đổi thực tế tại tất cả tài sản trong phạm vi.
3. Có bài kiểm tra dương/âm hoặc phép kiểm cấu hình phù hợp, ghi thời gian và môi trường.
4. Có người độc lập hoặc người được phân quyền xác nhận theo quy trình.
5. Có đánh giá rủi ro còn lại và ngoại lệ nếu chưa bao phủ hết.
6. Có cập nhật baseline/monitoring để phát hiện tái diễn.

Nếu ticket được đánh dấu Done nhưng production còn replica dùng cấu hình cũ, finding chưa thể coi đã được retest PASS trên toàn phạm vi.

## 14. Mẫu incident report nội bộ có thể tái sử dụng

Mẫu sau có thể sao chép và điền theo hệ thống, độ nghiêm trọng và đối tượng đọc. Đây là khung tham khảo; phải bổ sung yêu cầu riêng của tổ chức, hợp đồng hoặc pháp lý nếu áp dụng. Chỉ giữ thông tin nhạy cảm trong phạm vi phân quyền.

~~~markdown
# Incident report — [INCIDENT_ID] — [TIÊU ĐỀ NGẮN]

## 1. Metadata
- Incident ID: [INC-...]
- Report version / status: [v1.0 / Preliminary / Final / Addendum]
- Classification / audience: [Internal restricted / nhóm được xem]
- Severity / confidence: [theo chính sách + căn cứ]
- Incident commander / owner: [đội/chức năng]
- Report author / reviewed by / approved by: [...]
- First known event: [UTC + evidence]
- Detected at: [UTC + evidence]
- Report cutoff: [UTC]
- Related ticket, change, evidence repository: [refs]

## 2. Executive summary
[2–5 đoạn: điều đã xác nhận; phạm vi/tác động; hành động;
trạng thái hiện tại; điều chưa xác định; rủi ro còn lại]

## 3. Scope và bối cảnh
- Dịch vụ/tài sản/môi trường: [...]
- Chủ sở hữu: [...]
- Dữ liệu liên quan và phân loại: [...]
- Hệ thống liên đới: [...]
- Phạm vi đã kiểm tra: [...]
- Ngoài phạm vi/chưa kiểm tra: [...]

## 4. Phát hiện và phân loại
- Detection source: [alert/log/human/report]
- Initial hypothesis: [...]
- Severity decision và thay đổi: [...]
- Escalation và các mốc phê duyệt: [...]

## 5. Timeline (UTC)
| Thời gian | Hành vi hoặc quyết định | Evidence ID | Confidence |
|---|---|---|---|
| [..] | [..] | [E-...] | [confirmed/hypothesis] |

## 6. Technical findings
### F-01 — [Tên finding]
- Claim: [...]
- Evidence + phương pháp: [...]
- Những giả thuyết thay thế: [...]
- Độ tin cậy và giới hạn: [...]
- Security implication: [...]

## 7. Impact assessment
- Confidentiality confirmed / potential / unknown: [...]
- Integrity confirmed / potential / unknown: [...]
- Availability confirmed / potential / unknown: [...]
- Business/user impact: [...]
- Những gì chưa thể kết luận: [...]

## 8. Response actions và kết quả
- Triage/analysis: [...]
- Containment, thời gian hiệu lực, validation: [...]
- Eradication, validation: [...]
- Recovery, tiêu chí nghiệm thu: [...]
- Monitoring bổ sung và trạng thái hiện tại: [...]

## 9. Root cause / contributing factors
- Root cause đã xác nhận: [...]
- Điều kiện hỗ trợ: [...]
- Detection/response gaps: [...]
- Giả thuyết chưa xác minh: [...]
- Causal evidence: [...]

## 10. Security control assurance
| Control ID | Assertion | Kết quả | Evidence | Scope/limit |
|---|---|---|---|---|
| [..] | [..] | [PASS/FAIL/INCONCLUSIVE] | [E-...] | [..] |

## 11. Corrective/preventive actions
| Action ID | Finding | Owner | Due date | Test/retest | Status |
|---|---|---|---|---|---|
| [AC-...] | [F-...] | [..] | [..] | [..] | [..] |

## 12. Residual risk và quyết định mở
- Rủi ro còn lại: [...]
- Quyết định chấp nhận/ngoại lệ: [...]
- Approver, expiry, review date: [...]
- Bằng chứng/công việc đang chờ: [...]

## 13. Communications và obligations
- Đội liên quan đã được thông báo: [...]
- Quyết định về nghĩa vụ báo cáo bên ngoài: [owner và ref]
- Nơi lưu bản thông báo đã phê duyệt (nếu có): [...]

## 14. Evidence register và phụ lục
| Evidence ID | Source | Time range | Collected at | Integrity | Custody ref |
|---|---|---|---|---|---|
| [E-...] | [..] | [..] | [..] | [digest/signature] | [..] |

## 15. Approval, changes và follow-up
- Review/approval: [...]
- Report revision history: [...]
- Next checkpoint / addendum conditions: [...]
~~~

Mẫu này giúp người viết không bỏ sót các loại thông tin. Nhưng **điền đủ trường** không tự chứng minh tính chính xác. Cần xác minh chất lượng nguồn, phạm vi điều tra và ngôn ngữ kết luận.

## 15. Ví dụ hoàn chỉnh: nghi sử dụng trái phép workload identity

Tình huống dưới đây được tạo để học cách báo cáo; không đề cập một doanh nghiệp, incident hoặc kết quả điều tra có thật.

### 15.1. Metadata và phạm vi

~~~yaml
incident_id: "INC-2026-118"
title: "Unauthorized IAM policy change using workload identity"
report:
  version: "v1.0"
  status: "Final investigation summary"
  cutoff_at: "2026-11-28T11:30:00Z"
  classification: "INTERNAL-RESTRICTED"
severity: "HIGH"
confidence_overall: "MEDIUM"
ownership:
  incident_commander: "incident-response-team"
  technical_owner: "platform-team"
  report_owner: "security-assurance-team"
scope:
  service: "payments-api"
  environment: "production"
  affected_identity: "payments-runtime-role"
  affected_resource: "payments-data-policy"
  first_observed_at: "2026-11-28T09:05:00Z"
  detected_at: "2026-11-28T09:12:00Z"
references:
  case: "INC-2026-118-case"
  evidence_register: "INC-2026-118-evidence"
~~~

### 15.2. Executive summary

Vào 09:12 UTC ngày 28/11/2026, hệ thống phát hiện thay đổi quyền bất thường bằng workload identity của dịch vụ thanh toán. Cloud audit E-001 cho thấy một lệnh sửa policy tại 09:05 UTC; đối chiếu quy trình thay đổi E-004 không tìm thấy phê duyệt cho hoạt động đó trong phạm vi account đã kiểm. Đội phản ứng thu hồi quyền và xác minh một lệnh tương đương bị từ chối lúc 09:31 UTC. Policy được hoàn nguyên lúc 09:46 UTC, dịch vụ vượt qua các kiểm tra phục hồi lúc 11:25 UTC.

**Đã xác nhận:** một policy cấp quyền đọc rộng hơn baseline tồn tại trong khoảng điều tra. **Chưa xác nhận:** có dữ liệu nào đã bị truy xuất ngoài ý muốn hoặc được chuyển khỏi hệ thống trong khoảng đó. Data access audit đang được đối chiếu và thiếu một phần dữ liệu trong khoảng cần xem xét. Vì vậy, bản này chỉ khẳng định containment đã được kiểm chứng trong scope; kết luận về confidentiality vẫn là **INCONCLUSIVE**.

### 15.3. Findings

| Finding | Điều đã xác nhận | Bằng chứng | Giới hạn |
|---|---|---|---|
| F-01: IAM policy change | Workload identity sửa policy ngoài danh sách change đã kiểm | E-001, E-004, E-006 | Chưa kết luận ai điều khiển identity |
| F-02: IAM privilege exposure | Role có khả năng thực hiện thay đổi ngoài nhu cầu nghiệp vụ | E-009: effective permission | Chưa đánh giá tất cả role cùng loại |
| F-03: Data access uncertainty | Chưa thể kết luận tình trạng truy xuất dữ liệu toàn kỳ | E-007: data audit gap | Bằng chứng thiếu cho một phần cửa sổ |
| F-04: Detection delay | Rule tạo alert 7 phút sau hoạt động đầu tiên quan sát | E-001, E-002 | Chưa biết có hoạt động sớm hơn |
| F-05: Response ownership | Phải tra cứu thủ công owner của workload identity | E-003 và case notes | Chưa đánh giá mọi account |

Các E-ID chỉ minh họa phương pháp nối claim với evidence; trong báo cáo thật, mỗi tham chiếu phải trỏ đến hiện vật được bảo vệ và có thể kiểm chứng.

### 15.4. Causality và quyết định

**Nguyên nhân được xác minh:** quyền của workload identity rộng hơn nhu cầu ứng dụng, cho phép sửa policy trong phạm vi account. **Contributing factor:** quy trình cấp quyền chưa buộc kiểm thử deny cho các API quản trị nhạy cảm.

**Giả thuyết chưa xác minh:** credential có thể đã được truy cập từ môi trường runtime bị lỗi; cần điều tra nguồn phát lệnh và quản lý secret. Báo cáo không kết luận đã có data exfiltration khi chưa có bằng chứng tương ứng.

### 15.5. Action và residual risk

- **AC-01:** giới hạn quyền workload identity ở mức cần thiết; test deny trên thao tác sửa policy.
- **AC-02:** mở rộng phát hiện IAM policy change trên tất cả account thuộc inventory; test end-to-end.
- **AC-03:** kiểm tra nguồn cấp credential và rút ngắn thời gian sống của credential theo khả năng nền tảng.
- **AC-04:** cải tiến mapping owner và playbook containment; diễn tập trên môi trường được phép.
- **AC-05:** xác minh data access audit, ghi rõ khoảng log thiếu và biện pháp theo dõi bù trừ.
- **Residual risk:** còn khả năng có truy cập dữ liệu chưa được chứng minh hoặc loại trừ trong cửa sổ E-007; chủ sở hữu rủi ro phải quyết định mức giám sát và nghĩa vụ đánh giá tiếp theo.

**Định nghĩa "final" của báo cáo:** kết thúc phần điều tra đã đủ điều kiện theo quy trình; một số hành động và đánh giá có thể tiếp tục bằng addendum, với owner và hạn rõ. Không giấu các điểm chưa đóng chỉ để tài liệu có trạng thái Final.

## 16. Giao tiếp, bảo mật thông tin và nghĩa vụ bên ngoài

### 16.1. Mỗi audience cần mức chi tiết khác nhau

| Audience | Thông tin cần ưu tiên | Điều cần hạn chế |
|---|---|---|
| Incident commander và đội kỹ thuật | Timeline chi tiết, lệnh, evidence, trạng thái containment và blockers | Không đưa secret thật vào ticket rộng quyền |
| SOC/detection engineering | Detection gaps, rule effectiveness, telemetry và test case | Không kết luận attribution ngoài phạm vi |
| Lãnh đạo/nghiệp vụ | Tác động, khả năng vận hành, rủi ro còn lại, quyết định cần duyệt | Tránh quá nhiều log thô hoặc thuật ngữ không cần thiết |
| Security assurance/audit | Control mapping, test, evidence integrity, finding, retest | Tránh thiếu scope và giới hạn bằng chứng |
| Pháp chế/privacy/compliance | Loại dữ liệu, chủ thể bị ảnh hưởng, thời điểm, nghĩa vụ liên quan, quyết định | Không tự công bố nhận định chưa được rà soát |
| Khách hàng/đối tác/cơ quan quản lý | Nội dung, hình thức, đối tượng và thời hạn theo nghĩa vụ áp dụng | Không tiết lộ dữ liệu/tài sản ngoài phạm vi được phê duyệt |

**Nội dung báo cáo bên ngoài** phải tuân theo yêu cầu cụ thể của pháp luật, hợp đồng, thẩm quyền và quy trình phê duyệt. Incident report nội bộ không tự thay thế được thông báo chính thức.

### 16.2. Communications log

Nên ghi:

- Thời điểm gửi và người gửi.
- Đối tượng nhận hoặc nhóm nhận được ủy quyền.
- Bản thông tin đã được phê duyệt.
- Quyết định hoặc phản hồi cần theo dõi.
- Thời điểm cập nhật kế tiếp.
- Thông tin đã được sửa ở bản sau, kèm lý do.

Khi điều tra còn mở, thông báo có thể cần nêu **"tại thời điểm chốt báo cáo"** để tránh cảm giác đây là kết luận vĩnh viễn.

### 16.3. Bảo mật và khả năng chia sẻ

Tài liệu có thể chứa dữ liệu giúp kẻ tấn công biết đường nội bộ, credential reference và lỗ hổng chưa khắc phục. Cần:

1. Gắn classification và giới hạn người xem.
2. Tách phụ lục nhạy cảm khỏi bản tóm tắt phù hợp audience.
3. Dùng evidence link có kiểm soát thay vì đính toàn bộ dữ liệu thô.
4. Che thông tin cá nhân/secret trong bản chia sẻ, giữ bản gốc theo cơ chế pháp chứng.
5. Lưu version và audit truy cập/phê duyệt.
6. Xác định retention của báo cáo và chứng cứ theo yêu cầu tổ chức/pháp lý.

## 17. Đo chất lượng phản ứng và chất lượng báo cáo

Một báo cáo là nguồn để đánh giá hiệu quả tổ chức phản ứng, nhưng KPI phải được định nghĩa rõ ràng.

### 17.1. Chỉ số thời gian

| Chỉ số | Cách đo | Giới hạn |
|---|---|---|
| **Time to detect** | Detected at − incident start/first observed theo định nghĩa | Không dùng earliest observed thay actual start mà không nêu giới hạn |
| **Time to triage** | Start triage − alert received | Phải xác định mốc handoff và trường hợp alert trùng |
| **Time to contain** | Verified containment − mốc khởi tính đã khai báo | Thời điểm "gửi lệnh chặn" khác thời điểm chặn có hiệu lực |
| **Time to recover** | Recovery criteria met − mốc khởi tính đã khai báo | Hồi phục dịch vụ khác với đóng mọi corrective action |
| **Time to report** | Bản báo cáo được phê duyệt/phát hành − mốc kích hoạt cần báo cáo | Có các loại preliminary/final, không gộp |
| **Retest lead time** | Retest PASS − corrective action được triển khai | Có thể có thay đổi scope trong khi chờ |

Khi tổng hợp trung bình, phải xác định quần thể incident, loại severity, dữ liệu thiếu và cách xử lý ngoại lệ. **Mean** có thể bị chi phối bởi một sự cố rất dài; có thể bổ sung median, percentile và phân tổ.

### 17.2. Chỉ số chất lượng bằng chứng và hành động

| Chỉ số | Cách tính gợi ý | Lưu ý |
|---|---|---|
| Evidence traceability | Finding quan trọng có evidence ID và phương pháp / tổng finding cần evidence | ID có tồn tại không đồng nghĩa hiện vật đáng tin |
| Timeline completeness | Mốc bắt buộc có timestamp và nguồn / tổng mốc bắt buộc | Không ép điền giờ chính xác nếu thật sự chưa biết |
| Impact confidence | Tỷ lệ kết luận impact có scope và confidence rõ | Không phạt người ghi INCONCLUSIVE có căn cứ |
| Control evaluation coverage | Control áp dụng đã được đánh giá / tổng control cần đánh giá | NOT_TESTED khác PASS |
| Action closure verification | Action đã retest PASS / action đánh dấu đã triển khai | Tránh coi "Done" là verified |
| Overdue corrective actions | Action quá hạn chưa có retest đạt / tổng action quá hạn | Phải gắn severity và rủi ro còn lại |
| Repeat finding rate | Finding cùng nguyên nhân xuất hiện lại trong scope đã sửa | Cần mã nguyên nhân và phạm vi so sánh nhất quán |

Chỉ số có thể hỗ trợ phát hiện xu hướng, nhưng không nên dùng để khuyến khích đội phản ứng **hạ severity, đóng ticket sớm hoặc bỏ ghi "unknown"** nhằm làm báo cáo trông đẹp hơn.

### 17.3. Assurance liên tục sau incident

~~~mermaid
flowchart TD
    I["Incident evidence"] --> A["Report: claim + scope"]
    A --> F["Finding / control gaps"]
    F --> C["Corrective / preventive action"]
    C --> T["Deploy + retest"]
    T --> V{"Assertion đạt?"}
    V -- "Chưa" --> F
    V -- "Đạt trong scope" --> B["Cập nhật baseline / rule / runbook"]
    B --> M["Monitoring + diễn tập định kỳ"]
    M --> A
~~~

Mỗi finding nên trở thành một phần của **control register/risk register** hoặc hệ thống quản lý hành động phù hợp, sao cho việc hoàn tất không chỉ nằm trong một file báo cáo khó theo dõi.

## 18. QA nội bộ cho incident report trước khi phát hành

Một bước review đáng tin cậy có thể thực hiện theo checklist:

- [ ] Report có incident ID, version, classification, owner, thời điểm chốt và audience.
- [ ] Executive summary phân biệt hành vi đã xác nhận, tác động, trạng thái và unknown.
- [ ] Severity có định nghĩa và căn cứ; confidence không bị đồng nhất với severity.
- [ ] Scope liệt kê asset, danh tính, môi trường, khoảng thời gian và phần chưa đánh giá.
- [ ] Các timestamp có timezone, nguồn và ghi chú drift nếu cần.
- [ ] Timeline phân biệt event, alert, triage, containment, recovery và thời điểm thu chứng cứ.
- [ ] Mọi claim kỹ thuật quan trọng có evidence ID, nguồn và phương pháp.
- [ ] Evidence được phân quyền/bảo vệ, có chain of custody và integrity metadata khi thích hợp.
- [ ] Kết luận impact tách confirmed, potential và unknown, không suy diễn từ quyền thành hành vi thực tế.
- [ ] RCA phân biệt nguyên nhân có căn cứ, contributing factor và giả thuyết.
- [ ] Response action có kết quả kiểm chứng thay vì chỉ ghi "đã thực hiện".
- [ ] Security control mapping nêu PASS, FAIL, INCONCLUSIVE hoặc NOT_TESTED đúng phạm vi.
- [ ] Corrective actions có owner, due date, test/retest criteria và risk owner.
- [ ] Rủi ro còn lại/ngoại lệ có người quyết định, hạn và giám sát.
- [ ] Thông tin nhạy cảm và nội dung external communication được rà soát đúng thẩm quyền.
- [ ] Có người phê duyệt, revision history, điều kiện thêm addendum và tài liệu liên kết.

**Readability check:** người không tham gia ứng phó có thể hiểu kết luận chính trong executive summary, còn người kiểm toán có thể truy evidence từ claim và lặp lại phép kiểm trong phạm vi quyền được cấp.

## 19. Sai lầm thường gặp

| Nhận định hoặc cách làm sai | Hướng khắc phục |
|---|---|
| "Không thấy event exfiltration nên không có rò rỉ." | Xem dữ liệu nguồn nào thực sự bao phủ hành vi, phân biệt không thấy trong mẫu với không xảy ra. |
| "Đã block IP nên sự cố được xử lý hoàn toàn." | Kiểm chứng đường truy cập khác, credential, session và nguyên nhân; nêu residual risk. |
| "Đã restart server nên đã eradication." | Kiểm tra persistence, image/config, quyền và kết quả scan/retest. |
| "Timeline ghi giờ rất chính xác nên đáng tin." | Đối chiếu clock drift, timezone, event/ingest time và correlation. |
| "Log SIEM là bằng chứng đầy đủ." | Kiểm tra telemetry coverage, tính toàn vẹn, missing events và nguồn độc lập. |
| "Một IP lạ xác định được ai tấn công." | Tách chỉ dấu kỹ thuật khỏi attribution; đánh giá confidence và nguồn. |
| "Severity cao chắc chắn có breach dữ liệu." | Severity có thể phản ánh rủi ro tiềm tàng; impact xác nhận cần bằng chứng riêng. |
| "RCA là lỗi của kỹ sư triển khai." | Xem điều kiện hệ thống, quyền, policy, review, detection và quy trình. |
| "Đã gửi báo cáo final nên không cần cập nhật." | Dùng addendum hoặc follow-up cho evidence mới và action chưa đóng. |
| "Ticket Done nghĩa là remediation hoàn tất." | Đóng theo test/retest đạt trên asset thực tế trong phạm vi yêu cầu. |
| "Báo cáo càng nhiều log thô càng đầy đủ." | Cần truy xuất evidence có kiểm soát và mô tả kết luận rõ, tránh lộ dữ liệu. |
| "Chỉ cần báo cáo kỹ thuật là đủ mọi nghĩa vụ." | Kiểm tra riêng yêu cầu pháp lý, privacy, hợp đồng và thông báo theo thẩm quyền. |

## 20. Bài tập tự kiểm tra

**Câu 1.** Một đội thấy alert ở 09:20, audit log cho biết hành động đáng ngờ lúc 09:10, nhưng log của host có dấu hiệu lệch đồng hồ 8 phút. Bạn sẽ ghi timeline thế nào?

**Gợi ý:** Lưu timestamp gốc, nguồn, cách quy đổi và ghi sai số/độ tin cậy. Không dùng một giờ tuyệt đối thiếu xác minh; có thể dùng khoảng ước lượng và correlation theo request ID.

**Câu 2.** Thấy principal có quyền đọc bucket, có thể viết "đã xảy ra data exfiltration" không?

**Gợi ý:** Không. Quyền truy cập tạo khả năng ảnh hưởng; cần bằng chứng hành vi đọc/chuyển dữ liệu. Nếu log không đầy đủ, ghi potential impact hoặc unknown.

**Câu 3.** Policy bị thay ngoài quy trình và đã hoàn nguyên. Finding có thể đóng ngay không?

**Gợi ý:** Cần xác minh IAM permission, các phiên/credential liên quan, trạng thái policy đã có hiệu lực và scope khắc phục. Nếu action phòng ngừa còn mở, phải giữ action riêng hoặc residual risk có owner.

**Câu 4.** Một báo cáo ghi "không có máy chủ nào khác bị ảnh hưởng", nhưng đội điều tra chỉ kiểm tra 3 trong 10 máy cùng subnet. Câu này cần sửa gì?

**Gợi ý:** Viết "Không phát hiện dấu hiệu trong ba máy đã kiểm" và nêu bảy máy chưa kiểm, lý do, phương án kiểm thêm hoặc biện pháp giảm rủi ro.

**Câu 5.** Đội response chứng minh containment trong 26 phút. Có thể kết luận MTTD của tổ chức là 26 phút không?

**Gợi ý:** Không. 26 phút là khoảng đo từ mốc hành động đến containment của một sự cố giả định. MTTD là metric phát hiện, cần định nghĩa start/detection và nhiều incident phù hợp.

**Câu 6.** Một kỹ sư đã thay policy-as-code và merge PR. Báo cáo action đã khắc phục triệt để có thiếu gì?

**Gợi ý:** Cần xác nhận thay đổi đã deploy trên toàn scope, trạng thái có hiệu lực và phép kiểm cho thấy hành động từng bị khai thác không còn được phép, cùng evidence retest và phê duyệt.

**Câu 7.** Trong quá trình điều tra có thêm evidence làm thay đổi nhận định tác động. Báo cáo final đã phát hành cần xử lý thế nào?

**Gợi ý:** Tạo addendum hoặc phiên bản mới theo quy trình, nêu nhận định cũ và mới, nguồn bằng chứng, thời gian, người review và đối tượng cần nhận cập nhật.

## 21. Bài thực hành: tự lập incident report có thể kiểm toán

Giả sử bạn là thành viên đội security assurance. Tổ chức có một dịch vụ xử lý đơn hàng với cloud workload identity. Hệ thống cảnh báo về một thay đổi quyền ngoài quy trình ở production. Cần tạo báo cáo tóm tắt cùng action register cho buổi review.

**Dữ kiện giả định được cung cấp:**

- 14:10 UTC: cloud audit ghi một sự kiện cấp quyền đọc object storage cho role ứng dụng.
- 14:16 UTC: alert được tạo và gửi đến SOC queue.
- 14:24 UTC: analyst xác nhận không thấy change ticket tương ứng.
- 14:37 UTC: IAM role bị giới hạn; authorization test cho lệnh thay policy bị từ chối.
- 14:58 UTC: policy được khôi phục về baseline.
- 15:35 UTC: ứng dụng vượt qua kiểm thử chức năng.
- Data access audit mới có một phần, thiếu khoảng 14:05–14:30 UTC.
- Không có bằng chứng đáng tin xác định credential đã bị lấy bằng cơ chế nào.

**Yêu cầu thực hành:**

1. Viết executive summary khoảng 120–200 từ; chỉ khẳng định điều đã được chứng minh.
2. Lập timeline UTC với evidence ID giả lập rõ ràng và ghi confidence từng mốc.
3. Tách **confirmed impact**, **potential impact** và **unknown**; tránh viết "đã rò rỉ" khi không có bằng chứng.
4. Nêu ít nhất ba giả thuyết về đường vào, cách tìm bằng chứng ủng hộ/phản bác; không tự xác nhận.
5. Đánh giá tối thiểu các control về privilege management, detection, logging completeness, containment và recovery.
6. Đề xuất năm corrective/preventive actions có owner theo vai trò, thời hạn, phép kiểm lại.
7. Chỉ rõ điều kiện để bản báo cáo có thể được phát hành Final và điều kiện cần addendum sau đó.

**Tiêu chí đánh giá:**

| Tiêu chí | Đạt khi |
|---|---|
| Tính trung thực | Không có kết luận không tương xứng với chứng cứ |
| Khả năng truy vết | Mọi nhận định quan trọng chỉ được dẫn đến evidence ID và nguồn |
| Phạm vi | Có tài sản, khoảng thời gian và hệ thống chưa đủ dữ liệu |
| Phân tích nguyên nhân | Phân biệt trigger, control gap và hypothesis |
| Hiệu lực response | Có bằng chứng containment/recovery thay vì chỉ có change ticket |
| Hành động | Action có owner, hạn, tiêu chí retest và residual risk |
| Phiên bản tài liệu | Có cutoff time, classification, approval và update path |

## Kết luận

**Incident report** là tài liệu giúp tổ chức hiểu và kiểm chứng một sự cố bảo mật bằng chứng cứ có nguồn rõ ràng. Báo cáo có giá trị khi tách **sự thật, suy luận và phần chưa biết**; gắn diễn biến với timeline và evidence; đo chính xác tác động; giải thích các quyết định containment, eradication, recovery; phân tích nguyên nhân có căn cứ; và theo dõi action đến khi retest.

Trong **SECURITY_SECURITY_ASSURANCE**, incident report trở thành đầu vào quan trọng cho continuous assurance: mỗi phát hiện được nối với control, owner, corrective action, phép kiểm và kết quả xác minh lại. Cách làm đó biến kinh nghiệm ứng phó thành năng lực bảo mật có thể đo, kiểm toán và cải tiến qua các lần thay đổi hệ thống.

