# Tài liệu chiến lược: Ghi lịch phản hồi, nguồn lực, tiêu chí và cách báo cáo

## 1. Mục đích của tài liệu chiến lược kiểm thử

Chiến lược kiểm thử cần mô tả cách nhóm tổ chức hoạt động kiểm thử để cung cấp bằng chứng chất lượng đúng lúc cho quyết định phát hành và vận hành. Một tài liệu chỉ liệt kê loại test hoặc công cụ sẽ chưa đủ để điều phối công việc nếu không cho biết ai thực hiện, khi nào cần phản hồi, nguồn lực nào phải sẵn sàng, điều kiện nào được xem là đạt và kết quả được báo cáo ra sao.

Ghi rõ lịch phản hồi, nguồn lực, tiêu chí và cách báo cáo giúp các nhóm cùng hiểu:

- Khi nào cần cung cấp thông tin và ai là người nhận.
- Công việc cần những vai trò, kỹ năng, môi trường và công cụ nào.
- Chất lượng được đánh giá theo tiêu chí và bằng chứng nào.
- Khi nào một kết quả được xem là đạt, chưa đạt hoặc chưa đủ dữ liệu.
- Ai có trách nhiệm xử lý rủi ro, chấp nhận ngoại lệ và đưa ra quyết định.
- Báo cáo nào cần được tạo ở từng giai đoạn và cách truy vết kết luận.

Trong **VALIDATION_TESTING_STRATEGY**, các nội dung này cần liên kết thành một cơ chế vận hành. Lịch phản hồi phải dựa trên mốc công việc và thời gian xử lý; kế hoạch nguồn lực phải đáp ứng lịch; tiêu chí phải có phương pháp và nguồn bằng chứng; báo cáo phải phản ánh đúng trạng thái và giới hạn của bằng chứng.

## 2. Bốn phần cần được ghi thống nhất

### 2.1. Lịch phản hồi

Lịch phản hồi quy định thời điểm hoặc sự kiện kích hoạt việc cập nhật thông tin. Nó có thể gồm:

- Nhịp cập nhật trạng thái hằng ngày hoặc theo ca.
- Mốc hoàn thành test design, test execution, triage và retest.
- Thời hạn phản hồi defect theo severity.
- Thời điểm review rủi ro và quality gate.
- Mốc báo cáo trước khi phát hành.
- Cơ chế thông báo ngay khi xuất hiện sự cố nghiêm trọng.

Lịch cần nêu rõ người cập nhật, người nhận, nội dung tối thiểu và kênh chính thức. Một cuộc họp định kỳ không thay thế việc thông báo khẩn khi một tiêu chí bắt buộc bị vi phạm.

### 2.2. Nguồn lực

Nguồn lực gồm:

- Nhân sự và kỹ năng theo vai trò.
- Thời gian có thể phân bổ và mức ưu tiên.
- Môi trường, thiết bị, license và công cụ.
- Dữ liệu kiểm thử và quyền truy cập.
- CI runner, hạ tầng, sandbox và dịch vụ phụ thuộc.
- Hỗ trợ từ nhóm sản phẩm, vận hành, bảo mật hoặc nhà cung cấp.

Kế hoạch cần ghi cả chủ sở hữu, thời điểm cần, capacity và phương án khi nguồn lực chưa sẵn sàng.

### 2.3. Tiêu chí

Tiêu chí xác định điều kiện để đánh giá chất lượng hoặc hoàn tất một hoạt động:

- Phạm vi được đánh giá.
- Điều kiện đạt và ngưỡng định lượng nếu có.
- Phương pháp kiểm tra hoặc đo lường.
- Nguồn dữ liệu và yêu cầu về độ đầy đủ.
- Người có thẩm quyền xác nhận.
- Cách xử lý khi chưa đạt hoặc chưa đủ bằng chứng.

Tiêu chí cần được thống nhất trước khi đánh giá. Không thay đổi ngưỡng sau khi xem kết quả chỉ để tạo trạng thái đạt.

### 2.4. Báo cáo

Báo cáo biến dữ liệu kiểm thử thành thông tin phục vụ quyết định. Một báo cáo cần nêu:

- Phạm vi, phiên bản và cửa sổ đánh giá.
- Công việc đã hoàn thành và phần còn lại.
- Kết quả so với tiêu chí.
- Defect, incident và rủi ro quan trọng.
- Nguồn lực hoặc phụ thuộc đang cản trở.
- Bằng chứng, giới hạn và mức độ tin cậy.
- Quyết định, người chịu trách nhiệm và thời hạn tiếp theo.

## 3. Thiết kế lịch phản hồi

### 3.1. Chọn nhịp phản hồi theo tính chất công việc

Không phải mọi thông tin đều cần cập nhật với cùng tần suất. Hãy chọn cadence theo tốc độ thay đổi, mức độ rủi ro và thời gian cần để hành động:

| Nhịp phản hồi | Nội dung phù hợp | Người nhận chính |
| --- | --- | --- |
| Theo sự kiện/ngay lập tức | Incident nghiêm trọng, tiêu chí bắt buộc bị vi phạm, blocker ảnh hưởng mốc phát hành | Incident lead, owner kỹ thuật, release owner |
| Hằng ngày | Tiến độ test, test fail mới, blocker, thay đổi kế hoạch và nhu cầu hỗ trợ | Test lead, delivery lead, nhóm phát triển |
| Theo mốc | Test design review, hoàn tất integration, performance run, security assessment, UAT | Người phụ trách workstream và người phê duyệt |
| Hằng tuần | Xu hướng defect, coverage, capacity, rủi ro và dự báo | Project/product lead và các trưởng nhóm |
| Trước quality gate | Bằng chứng theo tiêu chí, ngoại lệ, rủi ro còn lại và đề xuất quyết định | Release authority và các owner liên quan |
| Sau phát hành | Theo dõi chỉ số, incident, defect lọt và bài học | Vận hành, sản phẩm, kỹ thuật và QA |

Nhịp cụ thể phụ thuộc quy mô dự án. Một nhóm nhỏ có thể dùng cập nhật bất đồng bộ; một release nhiều nhóm có thể cần các mốc đồng bộ và báo cáo theo workstream.

### 3.2. Mỗi lịch phải có điều kiện kích hoạt

Một lịch rõ ràng trả lời:

1. Sự kiện hoặc thời điểm nào kích hoạt cập nhật?
2. Ai chuẩn bị thông tin?
3. Ai xác nhận tính chính xác?
4. Ai cần nhận?
5. Thông tin nào bắt buộc phải có?
6. Thời hạn phản hồi là bao lâu?
7. Nếu không có phản hồi hoặc có blocker thì escalation tới ai?

Ví dụ, khi test lead phát hiện một defect Critical có khả năng ảnh hưởng dữ liệu khách hàng, người phát hiện phải thông báo ngay theo kênh incident đã thống nhất. Không chờ tới cuộc họp trạng thái ngày hôm sau.

### 3.3. Phân biệt lịch họp và thời hạn phản hồi

Lịch họp là thời điểm các bên trao đổi. Thời hạn phản hồi là khoảng thời gian người nhận cần đưa ra hành động hoặc quyết định.

Ví dụ:

- Triage defect High được tổ chức lúc 10:00 mỗi ngày.
- Owner của defect High cần xác nhận người xử lý và hướng khắc phục trong thời hạn đã thống nhất.
- Nếu quá thời hạn mà chưa có owner, test lead chuyển blocker tới delivery lead.

Ghi riêng hai loại thời gian giúp tránh tình trạng mọi người chờ tới cuộc họp tiếp theo dù công việc đang bị chặn.

### 3.4. Xác định SLA phản hồi theo mức độ

Có thể xây dựng mục tiêu phản hồi nội bộ theo severity:

| Mức độ | Ví dụ mục tiêu phản hồi ban đầu | Nội dung cần xác nhận |
| --- | --- | --- |
| Critical | Ngay khi xác minh sơ bộ | Người điều phối, containment, phạm vi và kênh cập nhật |
| High | Trong cùng ngày làm việc hoặc theo SLA dự án | Owner, ảnh hưởng, kế hoạch xử lý và mốc retest |
| Medium | Trong chu kỳ triage đã công bố | Ưu tiên, workaround và release target |
| Low | Trong backlog review định kỳ | Owner hoặc quyết định theo dõi/hoãn |

Đây là ví dụ để thiết kế quy ước. Nhóm cần thống nhất thời hạn theo giờ làm việc, múi giờ, lịch trực, yêu cầu hợp đồng và quy trình incident của tổ chức. Không áp dụng các thời hạn minh họa như cam kết mặc định.

### 3.5. Lịch phản hồi mẫu theo một chu kỳ release

| Giai đoạn | Sự kiện/mốc | Cập nhật cần có | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| Lập kế hoạch | Scope và risk baseline được thống nhất | Phạm vi, lịch, capacity, tiêu chí và phụ thuộc | Test lead |
| Chuẩn bị | Môi trường và dữ liệu sẵn sàng | Readiness, phiên bản, quyền, blocker | Environment/data owner |
| Thiết kế | Test cases và coverage được review | Rủi ro được bao phủ, khoảng trống, approval | Test designer và reviewer |
| Thực thi | Suite hoặc campaign hoàn tất từng phần | Pass/fail/blocked, evidence, defect mới | Test execution owner |
| Triage | Defect được phân loại | Severity, priority, owner, ETA, retest condition | Triage lead |
| Retest | Bản sửa sẵn sàng | Build, test result, regression impact | Test owner |
| Quality gate | Đến mốc quyết định | Tiêu chí, bằng chứng, ngoại lệ và rủi ro còn lại | Release authority |
| Sau phát hành | Hết cửa sổ theo dõi | Incident, escaped defect, metric và bài học | Operations/product/test lead |

## 4. Lập kế hoạch và quản lý nguồn lực

### 4.1. Bắt đầu từ phạm vi và năng lực cần thiết

Ước lượng nguồn lực sau khi đã xác định:

- Hệ thống, tính năng và rủi ro trong phạm vi.
- Các cấp độ và loại kiểm thử cần thực hiện.
- Số lượng nền tảng, vai trò, luồng và biến thể dữ liệu.
- Mức độ tự động hóa và công việc thủ công.
- Mốc review, triage, retest và báo cáo.
- Các phụ thuộc cần nhóm khác hoặc nhà cung cấp hỗ trợ.

Không phân bổ người chỉ theo tổng số test case. Một số hoạt động cần chuyên môn hiếm hoặc thời gian sử dụng môi trường riêng, nên số lượng test không phản ánh đầy đủ nhu cầu.

### 4.2. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm điển hình | Đầu ra |
| --- | --- | --- |
| Test/QA lead | Chiến lược, lịch, capacity, rủi ro và báo cáo tổng | Test plan, status, quality assessment |
| Test designer | Phân tích yêu cầu, thiết kế test và coverage | Test cases, traceability |
| Test automation engineer | Framework, script, CI và độ ổn định suite | Automated tests, execution evidence |
| Manual/exploratory tester | Khám phá hành vi, xác minh trải nghiệm và edge cases | Session notes, defect evidence |
| Developer/component owner | Phân tích nguyên nhân, sửa lỗi và cung cấp build | Fix, technical analysis, change details |
| Environment/data owner | Cấp phát môi trường, dataset, quyền và reset | Readiness confirmation |
| Security/performance specialist | Đánh giá chuyên sâu theo rủi ro | Assessment results, findings |
| Product/domain owner | Làm rõ nghiệp vụ và tiêu chí chấp nhận | Acceptance decision, priority |
| Release authority | Đánh giá quality gate và quyết định phát hành | Go/no-go hoặc risk acceptance |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng trách nhiệm phê duyệt và người chịu trách nhiệm cuối cùng vẫn phải rõ.

### 4.3. Phân biệt effort, duration và capacity

- **Effort:** công sức cần để thực hiện, thường tính bằng giờ công hoặc ngày công.
- **Duration:** thời gian lịch từ khi bắt đầu tới khi hoàn tất.
- **Capacity:** khả năng cung cấp nguồn lực trong một khoảng thời gian.

Ví dụ, 10 ngày công có thể cần hai người làm trong khoảng một tuần nếu công việc chia tách được và cả hai có đủ capacity. Nếu công việc phụ thuộc một chuyên gia chỉ rảnh hai ngày mỗi tuần, duration có thể dài hơn đáng kể.

Kế hoạch cần tính đến:

- Phần trăm thời gian thực tế dành cho dự án.
- Họp, hỗ trợ vận hành, nghỉ phép và công việc khác.
- Kỹ năng chuyên biệt và người thay thế.
- Trình tự phụ thuộc giữa các công việc.
- Thời gian chờ môi trường, dữ liệu hoặc phê duyệt.
- Giới hạn chạy song song và tài nguyên dùng chung.

### 4.4. Lập ma trận nguồn lực theo thời điểm

| Workstream | Vai trò chính | Thời điểm cần | Capacity/đầu vào | Phụ thuộc |
| --- | --- | --- | --- | --- |
| Test design | Test designer, domain reviewer | Trước test execution | Yêu cầu và acceptance criteria ổn định | Product owner |
| Automation | Automation engineer | Trong development và regression | Framework, runner, test data | Developer, CI owner |
| Environment | Environment owner | Trước integration/system test | Namespace, database, secrets | Platform/DevOps |
| Performance | Performance specialist | Trước performance gate | Hạ tầng và workload | Platform, data owner |
| Security | Security specialist | Theo risk plan và trước release gate | Scope, account, test environment | Security owner |
| Triage/retest | Developer và tester | Khi có defect và build sửa lỗi | Defect evidence, fix build | Component owner |

Ma trận nên thể hiện cả người thay thế hoặc phương án dự phòng cho vai trò có tính quyết định.

### 4.5. Nguồn lực phi nhân sự

Ngoài nhân lực, cần lập kế hoạch cho:

- Môi trường local, CI, integration, staging và performance.
- Thiết bị, browser, hệ điều hành và license.
- CI runner, storage, database và message broker.
- Sandbox provider, quota và credential.
- Dataset, tài khoản, secret và thời gian làm mới.
- Công cụ log, metric, trace, test management và defect tracking.

Với mỗi tài nguyên, ghi owner, thời điểm cần, capacity, thời hạn đặt chỗ và quy trình cleanup. Môi trường dùng chung cần có lịch điều phối để các test không làm nhiễm dữ liệu của nhau.

### 4.6. Xử lý thiếu nguồn lực

Khi nguồn lực không đáp ứng lịch, cần đánh giá theo thứ tự:

1. Xác định công việc và tiêu chí nào chịu ảnh hưởng.
2. Đánh giá rủi ro nếu giảm phạm vi hoặc hoãn hoạt động.
3. Xem khả năng chuyển lịch, chạy song song hoặc tự động hóa.
4. Bổ sung người có đúng kỹ năng hoặc hỗ trợ từ nhóm khác.
5. Điều chỉnh mốc và báo cáo tác động tới release.
6. Ghi quyết định và người có thẩm quyền chấp thuận.

Không âm thầm bỏ test bảo mật, test dữ liệu hoặc tiêu chí bắt buộc chỉ vì thiếu capacity. Nếu cần chấp nhận rủi ro, phải ghi rõ ngoại lệ.

## 5. Xác định tiêu chí chất lượng và điều kiện hoàn tất

### 5.1. Phân biệt tiêu chí kiểm thử và tiêu chí phát hành

**Tiêu chí kiểm thử** xác định một hoạt động hoặc test case có kết quả như mong đợi hay không. **Tiêu chí phát hành** xác định bằng chứng tổng thể có đủ để chấp nhận release hay không.

Ví dụ:

- Test case: API trả 403 khi user không có quyền.
- Test suite: tất cả test bắt buộc trong suite phân quyền đã chạy và kết quả được phân loại.
- Release gate: không còn defect Critical/High chưa được xử lý hoặc chấp nhận theo quy trình.
- Performance gate: p95 latency đáp ứng ngưỡng dưới workload đã định.

Không nên suy ra release đạt chỉ vì một suite pass. Cần xét các tiêu chí liên quan, phạm vi, rủi ro và bằng chứng.

### 5.2. Cấu trúc một tiêu chí có thể đánh giá

Mỗi tiêu chí nên xác định:

- ID và mô tả.
- Thuộc tính hoặc rủi ro cần kiểm soát.
- Phạm vi và phiên bản.
- Điều kiện đạt/không đạt.
- Phương pháp kiểm tra hoặc đo.
- Ngưỡng đủ bằng chứng.
- Nguồn dữ liệu và cửa sổ đánh giá.
- Người xác nhận và thẩm quyền ngoại lệ.

Ví dụ:

> Với API tạo booking trong build phát hành, tỷ lệ request lỗi nghiệp vụ không vượt quá 0,5% trên workload 100 request/giây trong 15 phút sau warm-up. Bộ đo phải gắn build ID, ghi tổng request và giữ lại các timeout thuộc workload.

### 5.3. Kết hợp tiêu chí định lượng và định tính

| Loại tiêu chí | Ví dụ | Cách đánh giá |
| --- | --- | --- |
| Định lượng | p95 latency, error rate, defect count | Metric, ngưỡng, số mẫu và cửa sổ đo |
| Định tính | Quy trình người dùng dễ hiểu, thông báo lỗi rõ | Checklist, review có tiêu chí và ghi nhận người đánh giá |
| Tuân thủ/hợp đồng | API schema, quyền truy cập, yêu cầu audit | Contract test, security test, evidence review |
| Hoàn tất quy trình | Tài liệu, sign-off, rollback plan | Kiểm tra artifact và phê duyệt |

Tiêu chí định tính cũng cần mô tả hành vi có thể quan sát. Tránh dùng các từ như “tốt”, “nhanh” hoặc “dễ dùng” mà không có rubric hoặc câu hỏi đánh giá cụ thể.

### 5.4. Trạng thái kết quả

Sử dụng trạng thái phân biệt:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Đạt (Met) | Bằng chứng hợp lệ cho thấy tiêu chí được đáp ứng |
| Chưa đạt (Not met) | Bằng chứng hợp lệ cho thấy tiêu chí bị vi phạm |
| Chưa đánh giá (Not assessed) | Chưa thực hiện hoặc chưa có dữ liệu |
| Chưa đủ bằng chứng (Insufficient evidence) | Có dữ liệu nhưng thiếu mẫu hoặc phạm vi |
| Bị chặn (Blocked) | Phụ thuộc, quyền hoặc môi trường ngăn việc đánh giá |
| Không áp dụng (N/A) | Ngoài phạm vi với lý do được phê duyệt |

Không chuyển trạng thái chưa đánh giá thành đạt. Một lần chạy test bị lỗi do môi trường cũng không tự động chứng minh sản phẩm vi phạm tiêu chí.

### 5.5. Quality gate

Quality gate là điểm kiểm tra để xác định có thể chuyển sang giai đoạn tiếp theo hoặc phát hành hay không. Một gate có thể gồm:

- Điều kiện bắt buộc phải đạt.
- Bằng chứng tối thiểu phải có.
- Defect và rủi ro được phép tồn tại theo chính sách.
- Các ngoại lệ cần phê duyệt.
- Người có thẩm quyền quyết định.
- Hành động nếu gate không đạt.

Ví dụ:

| Điều kiện | Ngưỡng minh họa | Bằng chứng |
| --- | --- | --- |
| Test bắt buộc | Tất cả test critical pass | Execution report gắn build |
| Defect | Không còn Critical chưa xử lý | Defect register và triage decision |
| Phân quyền | Không có lỗi truy cập trái quyền trong scope | Security/API test evidence |
| Hiệu năng | p95 dưới ngưỡng đã duyệt | Benchmark report với workload rõ |
| Rollback | Có phương án và đã xác minh bước chính | Runbook và kết quả rehearsal |

Ngưỡng thực tế phải do dự án hoặc tổ chức phê duyệt. Bảng trên chỉ minh họa cách ghi.

## 6. Liên kết lịch, nguồn lực và tiêu chí

Ba phần này cần được lập cùng nhau:

- Lịch xác định thời điểm cần bằng chứng.
- Tiêu chí xác định bằng chứng nào phải có.
- Nguồn lực xác định ai và tài nguyên nào tạo ra bằng chứng đúng hạn.

Ví dụ, performance gate cần kết quả trước ngày release review. Điều đó kéo theo:

1. Performance environment phải sẵn sàng trước cửa sổ đo.
2. Dataset và workload phải được xác nhận.
3. Performance specialist phải có capacity.
4. Bộ đo và dashboard phải gắn build ID.
5. Kết quả cần được review trước gate.
6. Nếu môi trường trễ, release owner phải được thông báo về tác động.

Nếu chỉ ghi ngày performance test mà không đặt lịch môi trường hoặc người phân tích, mốc đó không có cơ sở thực thi. Nếu chỉ cấp người mà không xác định tiêu chí, nhóm có thể hoàn thành hoạt động nhưng không tạo được bằng chứng phục vụ quyết định.

### 6.1. Ma trận tích hợp

| Mốc | Bằng chứng cần tạo | Nguồn lực cần | Tiêu chí hoàn tất | Báo cáo |
| --- | --- | --- | --- | --- |
| Design review | Test design và risk coverage | Tester, domain reviewer | Scope và oracle được duyệt | Design review notes |
| Environment ready | Readiness, version, access và dataset | Environment/data owner | Các dependency cần thiết sẵn sàng | Readiness report |
| Test execution | Test result, log, trace và defect | Tester, automation, CI | Phạm vi đã chạy và trạng thái được phân loại | Execution report |
| Defect triage | Severity, impact, owner và plan | Developer, tester, product | Mỗi defect có quyết định xử lý | Defect summary |
| Retest | Kết quả trên build sửa lỗi | Developer, tester | Fix được xác minh và regression liên quan pass | Retest report |
| Release gate | Tổng hợp tiêu chí và rủi ro | Test lead, release authority | Gate được đáp ứng hoặc ngoại lệ được duyệt | Quality assessment |
| Post-release | Metric và incident | Operations, product, QA | Cửa sổ theo dõi hoàn tất | Post-release report |

## 7. Xây dựng cách báo cáo

### 7.1. Báo cáo theo đối tượng nhận

Không phải mọi người nhận đều cần cùng mức chi tiết:

| Đối tượng | Thông tin cần ưu tiên |
| --- | --- |
| Nhóm phát triển | Test fail, log/trace, bước tái hiện, build và defect |
| Test lead | Coverage, tiến độ, blocker, nguồn lực và rủi ro |
| Product/domain owner | Ảnh hưởng người dùng, acceptance criteria và lựa chọn nghiệp vụ |
| Delivery/project lead | Mốc, phụ thuộc, forecast và tác động tới kế hoạch |
| Release authority | Quality gate, defect nghiêm trọng, ngoại lệ và rủi ro còn lại |
| Operations/support | Thay đổi vận hành, cảnh báo, workaround và hướng dẫn xử lý |

Có thể duy trì một nguồn dữ liệu chi tiết rồi tạo các bản tóm tắt theo vai trò. Không nên để các báo cáo khác nhau chứa những trạng thái mâu thuẫn.

### 7.2. Báo cáo trạng thái hằng ngày

Một bản cập nhật ngắn nên trả lời:

- Kế hoạch hôm nay và kết quả đã hoàn thành.
- Test/suite nào đã chạy, trạng thái ra sao.
- Defect mới, defect đã đóng và defect đang chờ.
- Blocker hoặc phụ thuộc đang ảnh hưởng tiến độ.
- Nguồn lực cần hỗ trợ.
- Kế hoạch tiếp theo và thay đổi mốc nếu có.

Ví dụ:

~~~text
Ngày: 16/11
Build: R42.3 / commit abc123
Phạm vi: Booking API và payment callback

Đã hoàn thành:
- 42/50 integration tests đã chạy
- 39 pass, 2 fail, 1 blocked
- Đã xác minh lại 3 defect đã sửa

Vấn đề:
- 1 defect High về callback lặp đang được điều tra
- 1 test blocked do sandbox hết quota

Tác động:
- Cần bổ sung quota trước 14:00 ngày mai để giữ mốc retest

Hành động:
- Payment owner kiểm tra idempotency
- Environment owner xác nhận quota
- Test lead cập nhật quality gate sau retest
~~~

### 7.3. Báo cáo chất lượng theo mốc

Báo cáo tại quality gate cần có:

1. Release, build và phạm vi được đánh giá.
2. Tiêu chí, ngưỡng và trạng thái từng tiêu chí.
3. Test execution summary và coverage.
4. Defect/incident theo severity và trạng thái.
5. Kết quả hiệu năng, bảo mật, tương thích hoặc các đánh giá liên quan.
6. Dữ liệu thiếu, phần chưa đánh giá và giới hạn.
7. Rủi ro còn lại, workaround và ngoại lệ.
8. Khuyến nghị của test lead.
9. Quyết định, người phê duyệt và thời điểm.

Không chỉ đưa tỷ lệ pass tổng. Báo cáo phải cho biết mẫu số, test bị bỏ qua, phạm vi chưa chạy và tiêu chí bắt buộc chưa đạt.

### 7.4. Báo cáo incident hoặc defect nghiêm trọng

Thông báo ban đầu cần nhanh và đủ để điều phối:

- Điều gì đã xảy ra hoặc đang nghi ngờ?
- Thành phần, phiên bản và môi trường nào liên quan?
- Tác động đã xác minh và phạm vi chưa biết.
- Biện pháp containment đang áp dụng.
- Người điều phối và owner kỹ thuật.
- Thời điểm cập nhật tiếp theo.

Báo cáo ban đầu có thể chưa có root cause. Ghi rõ điều đã biết, điều đang điều tra và không biến giả thuyết thành kết luận.

### 7.5. Chọn kênh và lưu nguồn chính thức

Quy định:

- Kênh thông báo khẩn.
- Công cụ theo dõi defect/incident.
- Nơi lưu test report và evidence.
- Dashboard và nguồn metric.
- Nơi lưu quyết định quality gate.
- Quyền truy cập và thời hạn lưu.

Chat có thể dùng để điều phối nhanh, nhưng quyết định và bằng chứng quan trọng cần được ghi vào hệ thống nguồn chính thức để truy vết.

## 8. Trách nhiệm, phê duyệt và escalation

### 8.1. Làm rõ người thực hiện và người quyết định

Có thể dùng mô hình RACI:

- **Responsible:** người trực tiếp thực hiện công việc.
- **Accountable:** người chịu trách nhiệm cuối cùng và có quyền quyết định.
- **Consulted:** người cần được tham vấn.
- **Informed:** người cần được thông báo.

Ví dụ:

| Hoạt động | Test lead | Developer lead | Product owner | Release authority |
| --- | --- | --- | --- | --- |
| Lập test plan | A/R | C | C | I |
| Xác minh defect | R | A/R | C | I |
| Chấp nhận nghiệp vụ | C | C | A/R | I |
| Đề xuất quality status | A/R | C | C | I |
| Quyết định release | C | C | C | A/R |

Ma trận cần được điều chỉnh theo cơ cấu thực tế. Không để nhiều người cùng được ghi là Accountable cho một quyết định cuối cùng nếu không có cơ chế phân quyền rõ.

### 8.2. Điều kiện escalation

Escalation cần được kích hoạt khi:

- Defect Critical hoặc incident nghiêm trọng xuất hiện.
- Tiêu chí bắt buộc chưa đạt hoặc không có bằng chứng.
- Blocker đe dọa mốc release.
- Nguồn lực then chốt không sẵn sàng.
- Owner không phản hồi trong SLA đã thống nhất.
- Có xung đột về severity, phạm vi hoặc kết luận chất lượng.
- Có rủi ro bảo mật, dữ liệu hoặc tuân thủ cần xử lý theo quy trình chuyên biệt.

Thông tin escalation nên gồm vấn đề, tác động, thời hạn cần quyết định, phương án khả thi và người có thẩm quyền.

### 8.3. Quản lý ngoại lệ và chấp nhận rủi ro

Nếu một tiêu chí không đạt hoặc chưa có đủ bằng chứng nhưng dự án muốn tiếp tục, cần một quyết định có kiểm soát:

- Tiêu chí và phạm vi được ngoại lệ.
- Bằng chứng và lý do.
- Tác động/rủi ro còn lại.
- Biện pháp giảm thiểu.
- Thời hạn ngoại lệ.
- Người phê duyệt có thẩm quyền.
- Điều kiện đánh giá lại hoặc thu hồi ngoại lệ.

Ngoại lệ không làm thay đổi kết quả đo ban đầu. Báo cáo cần giữ trạng thái thực tế và ghi riêng quyết định chấp nhận rủi ro.

## 9. Quản lý phiên bản và duy trì tài liệu chiến lược

### 9.1. Tài liệu cần có chủ sở hữu

Ghi rõ:

- Document owner.
- Người review và phê duyệt.
- Phiên bản và ngày hiệu lực.
- Phạm vi áp dụng.
- Lịch review định kỳ.
- Nơi lưu bản chính thức.
- Lịch sử thay đổi.

Tài liệu chiến lược cần được xem xét khi có thay đổi về kiến trúc, rủi ro, quy trình release, tổ chức nhóm, công cụ hoặc yêu cầu tuân thủ.

### 9.2. Thay đổi có kiểm soát

Khi sửa lịch, nguồn lực, tiêu chí hoặc báo cáo:

1. Nêu lý do thay đổi.
2. Xác định phần quy trình và nhóm bị ảnh hưởng.
3. Đánh giá tác động tới mốc, capacity và quality gate.
4. Review với owner liên quan.
5. Phê duyệt theo quy trình.
6. Cập nhật version và change log.
7. Thông báo cho người sử dụng tài liệu.

Không thay đổi ngưỡng hoặc SLA một cách âm thầm. Các thay đổi này có thể ảnh hưởng đến quyết định chất lượng và cam kết giữa nhóm.

### 9.3. Giữ tài liệu thực tế và có thể sử dụng

Tài liệu cần ngắn gọn ở phần quy định vận hành và liên kết tới các chi tiết thay đổi thường xuyên như lịch trực, dashboard, test report hoặc danh sách owner. Tránh sao chép dữ liệu biến động vào nhiều nơi khiến chúng nhanh chóng lệch nhau.

Rà soát:

- Lịch phản hồi có còn khả thi?
- Vai trò và owner có còn đúng?
- Capacity và phụ thuộc có thay đổi?
- Tiêu chí có còn phù hợp với rủi ro?
- Báo cáo có được sử dụng để ra quyết định?
- Các ngoại lệ cũ đã hết hạn hoặc cần gia hạn?

## 10. Ví dụ tích hợp: chiến lược kiểm thử cho một release

Giả sử release R42 bổ sung luồng thanh toán và xác nhận booking. Các rủi ro chính gồm callback lặp, truy cập sai tenant, timeout và tải tăng.

### 10.1. Lịch phản hồi

- Daily update lúc 16:00 cho tiến độ test và blocker.
- Defect Critical được báo ngay theo incident channel.
- Triage defect High mỗi ngày làm việc.
- Performance result được review trước quality gate.
- Release assessment được gửi trước cuộc họp quyết định.
- Sau phát hành có cửa sổ theo dõi metric và incident.

### 10.2. Nguồn lực

- Một test lead điều phối scope và gate.
- Hai tester phụ trách API/integration và exploratory.
- Một automation engineer duy trì regression suite.
- Một developer owner cho payment adapter và một owner cho booking service.
- Environment owner cấp staging, broker và payment sandbox.
- Performance specialist chuẩn bị workload và phân tích percentile.
- Security reviewer xác nhận tenant isolation.

### 10.3. Tiêu chí

- Callback lặp không tạo ledger entry trùng.
- Người dùng không đọc được booking thuộc tenant khác.
- Các test critical của booking/payment pass.
- p95 và error rate đáp ứng ngưỡng được phê duyệt dưới workload đã định.
- Không còn defect Critical chưa được xử lý hoặc ngoại lệ được phê duyệt.
- Bằng chứng gắn với build R42 và cấu hình đã ghi.

### 10.4. Báo cáo và quyết định

Test lead tổng hợp trạng thái theo từng tiêu chí, liên kết report và defect. Nếu payment sandbox bị gián đoạn khiến một phần integration test chưa chạy, báo cáo ghi Insufficient evidence hoặc Blocked cho phạm vi đó. Không ghi pass chỉ vì các test đã chạy đều thành công.

Release authority xem kết quả, rủi ro, ngoại lệ và phương án giảm thiểu để đưa ra quyết định. Sau phát hành, nhóm theo dõi callback duplicate, payment failure, booking confirmation và incident để kiểm tra giả định của chiến lược.

## 11. Mẫu tài liệu vận hành chiến lược

~~~text
Tên tài liệu:
Document owner:
Version / effective date:
Phạm vi release/sản phẩm:
Người review / phê duyệt:

1. Lịch phản hồi
- Daily/weekly cadence:
- Milestone:
- Event-triggered notification:
- Người gửi / người nhận:
- SLA phản hồi:
- Escalation path:

2. Nguồn lực
- Vai trò / owner:
- Effort / capacity:
- Thời điểm cần:
- Môi trường / thiết bị / license:
- Dữ liệu / công cụ / dependency:
- Phương án dự phòng:

3. Tiêu chí
- Criterion ID:
- Phạm vi:
- Điều kiện đạt:
- Ngưỡng / phương pháp:
- Nguồn và mức đủ bằng chứng:
- Người xác nhận:
- Ngoại lệ được phép:

4. Báo cáo
- Báo cáo theo nhịp:
- Báo cáo theo milestone:
- Quality gate report:
- Incident/defect report:
- Kênh và hệ thống nguồn:
- Quyền truy cập / retention:

5. Quản trị
- RACI:
- Quy trình quyết định:
- Risk acceptance:
- Lịch review tài liệu:
- Change log:
~~~

## 12. Checklist rà soát tài liệu chiến lược

- [ ] Phạm vi và mục tiêu kiểm thử được mô tả rõ.
- [ ] Lịch phản hồi có cadence, trigger, người gửi/nhận và thời hạn.
- [ ] Có cơ chế thông báo ngay cho sự kiện nghiêm trọng.
- [ ] Họp định kỳ được phân biệt với SLA phản hồi.
- [ ] Nguồn lực được phân theo vai trò, kỹ năng và thời điểm.
- [ ] Effort, duration và capacity được phân biệt.
- [ ] Môi trường, dữ liệu, công cụ, thiết bị và phụ thuộc có owner.
- [ ] Có phương án khi nguồn lực hoặc môi trường không sẵn sàng.
- [ ] Tiêu chí có phạm vi, ngưỡng, phương pháp và nguồn bằng chứng.
- [ ] Trạng thái đạt, chưa đạt, chưa đánh giá và blocked được phân biệt.
- [ ] Quality gate nêu điều kiện, người quyết định và hành động khi không đạt.
- [ ] Báo cáo phù hợp với từng đối tượng nhận và có nguồn chính thức.
- [ ] Báo cáo nêu mẫu số, phạm vi, giới hạn và rủi ro còn lại.
- [ ] RACI và escalation path rõ ràng.
- [ ] Ngoại lệ có người phê duyệt, phạm vi, thời hạn và biện pháp giảm thiểu.
- [ ] Tài liệu có owner, version, approval và lịch review.
- [ ] Thay đổi lịch, nguồn lực hoặc tiêu chí được quản lý phiên bản và thông báo.

Một tài liệu chiến lược hữu ích kết nối lịch phản hồi, nguồn lực, tiêu chí và báo cáo thành một quy trình có thể vận hành. Khi mỗi mốc có người chịu trách nhiệm, mỗi tiêu chí có bằng chứng, mỗi khoảng trống có hành động và mỗi quyết định có người phê duyệt, nhóm có thể điều phối kiểm thử minh bạch và đưa ra quyết định chất lượng đúng thời điểm.
