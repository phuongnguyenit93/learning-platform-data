# Phân biệt tiến độ thực hiện với bằng chứng về chất lượng

Trong module **VALIDATION_TESTING_STRATEGY**, báo cáo kiểm thử cần trả lời hai câu hỏi riêng biệt: nhóm đã hoàn thành bao nhiêu công việc và hiện có bằng chứng gì về chất lượng sản phẩm. **Tiến độ thực hiện** mô tả mức độ hoàn thành các hoạt động hoặc phạm vi công việc đã lên kế hoạch. **Bằng chứng về chất lượng** là kết quả có thể kiểm tra, gắn với yêu cầu và điều kiện cụ thể, giúp đánh giá sản phẩm đáp ứng tiêu chí đến đâu.

Hai khái niệm có liên quan nhưng không thay thế nhau. Nhóm có thể hoàn thành 100% test case đã lên kế hoạch nhưng phát hiện nhiều lỗi nghiêm trọng. Ngược lại, một số kiểm thử trọng yếu có thể đã cung cấp bằng chứng tốt về rủi ro quan trọng dù phần kiểm thử còn lại chưa hoàn tất. Nếu báo cáo chỉ có một con số “80% hoàn thành” hoặc “95% pass”, người đọc có thể hiểu nhầm tiến độ là chất lượng, hoặc tỷ lệ pass là mức độ sẵn sàng phát hành.

Bài học này hướng dẫn cách định nghĩa và đo tiến độ, xác định bằng chứng chất lượng, liên kết hai loại thông tin trong báo cáo, tránh các chỉ số gây hiểu nhầm và sử dụng chúng trong quyết định quản lý. Mục tiêu là giúp nhóm biết công việc đang ở đâu, chất lượng đã được chứng minh đến mức nào, còn khoảng trống nào và cần hành động gì tiếp theo.

## 1. Phân biệt hai câu hỏi quản lý

### 1.1. Tiến độ trả lời “đã làm đến đâu?”

Tiến độ (progress) mô tả phần công việc đã hoàn thành so với phạm vi hoặc kế hoạch đã xác định. Trong kiểm thử, có thể theo dõi:

- Yêu cầu đã được phân tích.
- Test condition và test case đã thiết kế, review.
- Dữ liệu và môi trường đã chuẩn bị.
- Test case đã thực thi.
- Automation đã phát triển và tích hợp.
- Lỗi đã được xác minh, phân loại hoặc retest.
- Báo cáo và hồ sơ bằng chứng đã hoàn tất.
- Các hoạt động còn blocked hoặc đang chờ phụ thuộc.

Tiến độ là thông tin về hoạt động và trạng thái công việc. Nó cho biết nhóm đã thực hiện những gì, còn bao nhiêu việc và có khả năng hoàn tất đúng mốc hay không.

### 1.2. Bằng chứng chất lượng trả lời “đã chứng minh được điều gì?”

Bằng chứng chất lượng (quality evidence) là kết quả và dữ liệu có thể kiểm tra để hỗ trợ một kết luận về sản phẩm hoặc quy trình. Ví dụ:

- Test case xác nhận một quy tắc nghiệp vụ.
- Kết quả API và trạng thái dữ liệu chứng minh một giao dịch được xử lý đúng.
- Contract test chứng minh provider đáp ứng hợp đồng đã xác định.
- Báo cáo hiệu năng cho thấy latency trong điều kiện tải cụ thể.
- Kết quả kiểm tra bảo mật xác nhận hoặc phát hiện rủi ro.
- Bằng chứng accessibility cho thấy một hành trình có thể hoàn thành bằng bàn phím.
- Dữ liệu production monitoring cho thấy tỷ lệ lỗi sau triển khai.
- Báo cáo migration đối chiếu dữ liệu trước và sau chuyển đổi.

Bằng chứng có thể cho thấy tiêu chí đạt hoặc không đạt. Một test thất bại được tái hiện và ghi nhận đầy đủ vẫn là bằng chứng chất lượng quan trọng vì nó cho thấy sản phẩm chưa đáp ứng yêu cầu.

### 1.3. So sánh trực tiếp

| Khía cạnh | Tiến độ thực hiện | Bằng chứng về chất lượng |
|---|---|---|
| Câu hỏi | Công việc đã hoàn thành đến đâu? | Sản phẩm đáp ứng tiêu chí đến mức nào? |
| Đối tượng đo | Hoạt động, nhiệm vụ, phạm vi và trạng thái | Hành vi, thuộc tính chất lượng và rủi ro |
| Dữ liệu | Số việc hoàn tất, còn lại, blocked, thời gian | Kết quả, dữ liệu, log, trace, metrics, artifact |
| Ví dụ | 80/100 test case đã thực thi | 72 test đạt, 5 test phát hiện lỗi, 3 test bị blocked |
| Ý nghĩa | Khả năng hoàn tất kế hoạch | Mức độ có căn cứ để kết luận về chất lượng |
| Không chứng minh được | Sản phẩm đã tốt hoặc sẵn sàng phát hành | Toàn bộ công việc đã hoàn tất hoặc đúng tiến độ |

Một báo cáo tốt trình bày cả hai góc nhìn và giải thích mối quan hệ giữa chúng.

### 1.4. Hoàn thành công việc không đồng nghĩa với đạt chất lượng

Một test case có thể được đánh dấu “đã chạy” nhưng kết quả không cung cấp bằng chứng hợp lệ nếu:

- Dữ liệu tiền điều kiện không đúng.
- Test chạy trên sai phiên bản artifact.
- Môi trường không có phụ thuộc cần thiết.
- Assertion không kiểm tra đúng tiêu chí.
- Log hoặc dữ liệu quan sát bị thiếu.
- Kết quả bị ghi nhận thủ công mà không có căn cứ.

Tương tự, một hoạt động “đã review” không chứng minh nội dung đã được review đầy đủ hoặc các phát hiện đã được xử lý. Trạng thái hoàn thành phải có định nghĩa rõ và được tách khỏi kết luận chất lượng.

## 2. Định nghĩa tiến độ kiểm thử có thể đo được

### 2.1. Xác định phạm vi và đơn vị theo dõi

Trước khi tính tiến độ, cần biết mẫu số là gì. Có thể theo dõi theo:

- Yêu cầu hoặc acceptance criteria.
- Test condition.
- Test case hoặc test procedure.
- Test suite.
- Hành trình E2E.
- Nhiệm vụ automation.
- Hạng mục chuẩn bị môi trường và dữ liệu.
- Defect cần xác minh hoặc retest.
- Deliverable như báo cáo hoặc hồ sơ release.

Không nên dùng một đơn vị chung cho mọi hoạt động. “8 yêu cầu”, “120 test case” và “4 môi trường” không thể cộng trực tiếp thành một tổng tiến độ nếu chưa có quy tắc trọng số.

### 2.2. Định nghĩa trạng thái công việc

Một workflow đơn giản có thể gồm:

- **Not started:** chưa bắt đầu.
- **Ready:** đã đủ điều kiện để bắt đầu.
- **In progress:** đang thực hiện.
- **Waiting:** đang chờ sự kiện hoặc phụ thuộc.
- **Blocked:** không thể tiếp tục do vấn đề cần tháo gỡ.
- **Review:** đang chờ review hoặc xác nhận.
- **Done:** hoàn tất theo định nghĩa công việc.

Với test execution, cần có trạng thái riêng như Pass, Fail, Blocked, Skipped, Not run hoặc Invalid. Không nên dùng “Done” thay cho “Pass”: một test đã thực thi và phát hiện lỗi có thể hoàn tất hoạt động thực thi nhưng kết quả chất lượng là Fail.

### 2.3. Đo tiến độ theo số lượng

Một công thức đơn giản:

```
Tiến độ thực thi (%) =
    Số test case đã thực thi hợp lệ
    / Tổng số test case thuộc phạm vi
    × 100
```

Ví dụ, có 100 test case trong phạm vi và 80 test đã thực thi hợp lệ:

```
Execution progress = 80 / 100 × 100 = 80%
```

Con số này cho biết 80% test case đã được thực thi. Nó không cho biết 80% test case đạt, cũng không chứng minh các yêu cầu quan trọng đã được bao phủ.

Nếu một test bị đánh dấu executed nhưng chạy sai build hoặc thiếu dữ liệu, cần phân loại lại theo quy tắc và không tính như một lần thực thi hợp lệ.

### 2.4. Đo tiến độ theo deliverable hoặc công việc

Có thể theo dõi riêng:

- 100% yêu cầu đã được review.
- 90% test case đã được thiết kế.
- 75% test data đã sẵn sàng.
- 60% automation đã tích hợp.
- 80% test case trong phạm vi đã chạy.
- 50% defect cần retest đã được xác minh.

Các tỷ lệ này có mẫu số khác nhau. Hãy hiển thị tên chỉ số, tử số, mẫu số và trạng thái còn lại. Không lấy trung bình các tỷ lệ trên để tạo một “tiến độ tổng” nếu chưa có mô hình trọng số được thống nhất.

### 2.5. Tiến độ theo trọng số

Khi công việc có độ lớn khác nhau, có thể dùng trọng số đã thống nhất trước:

```
Tiến độ có trọng số (%) =
    Tổng trọng số của các hạng mục hoàn tất
    / Tổng trọng số của toàn bộ hạng mục
    × 100
```

Ví dụ, một hành trình thanh toán có trọng số 5 vì rủi ro cao, còn một kiểm tra nội dung có trọng số 1. Hoàn tất hành trình thanh toán đóng góp nhiều hơn vào tiến độ theo mô hình này.

Cần lưu:

- Cách xác định trọng số.
- Ai phê duyệt.
- Thời điểm khóa phạm vi.
- Quy tắc khi thêm, bỏ hoặc thay đổi hạng mục.
- Cách xử lý công việc dở dang.

Không nên thay trọng số giữa chừng chỉ để tỷ lệ tiến độ trông tốt hơn. Trọng số phản ánh kế hoạch ưu tiên công việc; nó không thay thế bằng chứng chất lượng.

## 3. Xác định bằng chứng chất lượng cần thu thập

### 3.1. Bắt đầu từ yêu cầu và rủi ro

Mỗi bằng chứng cần liên kết với một câu hỏi chất lượng cụ thể:

- Quy tắc nghiệp vụ nào đang được xác minh?
- Thuộc tính chất lượng nào cần đo?
- Rủi ro nào cần giảm?
- Điều kiện và ngưỡng chấp nhận là gì?
- Nguồn dữ liệu nào có thẩm quyền?
- Bằng chứng nào đủ để người khác kiểm tra kết luận?

Ví dụ, với yêu cầu “không được tạo giao dịch thanh toán trùng khi retry”, bằng chứng có thể gồm request với cùng idempotency key, phản hồi, số giao dịch ghi nhận, trạng thái cuối và đối chiếu ledger. Chỉ có response HTTP thành công chưa đủ chứng minh không có giao dịch trùng.

### 3.2. Các loại bằng chứng

| Loại bằng chứng | Ví dụ | Câu hỏi được hỗ trợ |
|---|---|---|
| Functional | Expected/actual, trạng thái nghiệp vụ | Chức năng có đúng quy tắc không? |
| API/contract | Request, response, schema, mã lỗi | Các thành phần có tuân thủ hợp đồng không? |
| Data integrity | Bản ghi trước/sau, đối soát | Dữ liệu có đúng và nhất quán không? |
| Performance | Latency, throughput, error rate | Hệ thống đáp ứng mục tiêu tải không? |
| Security | Findings, request tái hiện, cấu hình | Có rủi ro bảo mật nào được phát hiện? |
| Accessibility | Thao tác bàn phím, screen reader, audit | Người dùng có thể hoàn thành tác vụ theo tiêu chí không? |
| Reliability | Restart, failover, recovery evidence | Hệ thống có phục hồi đúng không? |
| Operational | Logs, metrics, traces, alerts | Hệ thống có thể quan sát và vận hành không? |

Một test suite có thể tạo nhiều loại bằng chứng. Cần tránh lưu nhiều file nhưng không xác định file nào hỗ trợ tiêu chí nào.

### 3.3. Bằng chứng cần có ngữ cảnh

Bằng chứng nên gắn với:

- Requirement hoặc quality criterion ID.
- Test case và test run ID.
- Build, commit hoặc artifact digest.
- Môi trường và cấu hình.
- Dữ liệu và trạng thái ban đầu.
- Thời điểm, timezone và người hoặc hệ thống thực hiện.
- Công cụ và phiên bản.
- Kết quả mong đợi và thực tế.
- Vị trí lưu bằng chứng và giới hạn.

Thiếu ngữ cảnh có thể khiến một ảnh chụp hoặc report không còn ý nghĩa khi ứng dụng đã đổi phiên bản.

### 3.4. Phân biệt bằng chứng đạt và bằng chứng phát hiện lỗi

Bằng chứng chất lượng không chỉ là bằng chứng “đạt”. Cần giữ cả:

- Kết quả xác nhận tiêu chí được đáp ứng.
- Kết quả cho thấy tiêu chí không được đáp ứng.
- Kết quả không đủ dữ liệu để kết luận.
- Kết quả bị chặn do môi trường hoặc phụ thuộc.
- Kết quả không hợp lệ do phương pháp đo sai.

Một lỗi có bằng chứng tái hiện tốt giúp nhóm hiểu giới hạn của sản phẩm và ưu tiên sửa. Không nên loại bỏ kết quả fail khỏi báo cáo chỉ để thể hiện tiến độ tích cực.

## 4. Đo tiến độ và đo chất lượng bằng các chỉ số riêng

### 4.1. Chỉ số tiến độ

Một số chỉ số tiến độ:

- Test design completion: tỷ lệ test case đã thiết kế và review.
- Test execution progress: tỷ lệ test case đã thực thi hợp lệ.
- Automation implementation progress: tỷ lệ kịch bản đã phát triển và tích hợp.
- Environment readiness: tỷ lệ điều kiện môi trường đã sẵn sàng.
- Defect retest progress: tỷ lệ lỗi đã được retest.
- Deliverable completion: tỷ lệ hồ sơ hoặc báo cáo đã hoàn tất.
- Blocked work: số lượng và tuổi công việc bị chặn.
- Remaining work: số hạng mục và effort còn lại.

Các chỉ số cần nêu rõ phạm vi và cách tính. Ví dụ, “Automation 70%” cần giải thích mẫu số là test case nào: toàn bộ regression, nhóm rủi ro cao hay những trường hợp được chọn để tự động hóa.

### 4.2. Chỉ số và tín hiệu chất lượng

Tùy mục tiêu, có thể theo dõi:

- Requirement coverage hoặc risk coverage.
- Tỷ lệ test pass/fail/blocked/invalid.
- Defect theo severity và priority.
- Defect density hoặc xu hướng lỗi theo thành phần, khi định nghĩa phù hợp.
- Defect leakage và escaped defects.
- Tỷ lệ lỗi tái mở.
- Độ ổn định của test suite.
- Latency, throughput và error rate.
- Mức độ đáp ứng tiêu chí bảo mật, accessibility và reliability.
- Kết quả đối soát dữ liệu.
- Sự cố và tín hiệu vận hành sau triển khai.

Không có một chỉ số chất lượng duy nhất phù hợp với mọi sản phẩm. Chọn metric theo thuộc tính cần chứng minh và nguồn dữ liệu đáng tin cậy.

### 4.3. Tỷ lệ pass không phải điểm chất lượng tổng thể

Công thức:

```
Pass rate = Pass / (Pass + Fail) × 100%
```

Cách tính này loại Blocked, Skipped và Not run khỏi mẫu số. Vì vậy, cần báo cáo các trạng thái còn lại riêng và giải thích quy ước. Nếu tổ chức dùng mẫu số khác, phải ghi rõ.

Ví dụ:

- 100 test case thuộc phạm vi.
- 80 test đã thực thi hợp lệ.
- 72 Pass.
- 5 Fail.
- 3 Blocked.
- 20 Not run.

Pass rate trong số test đã có kết quả Pass hoặc Fail là:

```
72 / (72 + 5) × 100% ≈ 93,5%
```

Execution progress là 80/100 = 80%. Hai con số mô tả hai điều khác nhau. Báo cáo 93,5% pass mà không nêu 20 test chưa chạy và 3 test blocked sẽ tạo ấn tượng sai về mức độ xác minh.

### 4.4. Coverage không đồng nghĩa với tính đúng

Coverage có thể đo số yêu cầu, nhánh, dòng mã, API hoặc rủi ro được liên kết với kiểm thử. Coverage cao không tự chứng minh assertion có chất lượng hoặc dữ liệu đủ đại diện.

Ví dụ, một test có thể thực thi một dòng mã nhưng không kiểm tra kết quả. Vì vậy, coverage là tín hiệu về phạm vi, cần kết hợp với tiêu chí, kết quả và bằng chứng.

### 4.5. Kết hợp leading và lagging indicators

- **Leading indicators:** tín hiệu sớm như mức sẵn sàng môi trường, chất lượng yêu cầu, risk coverage, số test chưa thiết kế, flaky rate.
- **Lagging indicators:** kết quả đã xảy ra như defect lọt production, sự cố, lỗi khách hàng, rollback và chi phí sửa sau phát hành.

Leading indicators giúp dự báo và hành động trước; lagging indicators cho biết hậu quả và hiệu quả thực tế. Không nên chỉ dùng lagging indicators vì khi lỗi đã lọt production, cơ hội phòng ngừa đã qua.

## 5. Liên kết tiến độ với bằng chứng mà không đánh đồng

### 5.1. Mỗi hoạt động hoàn tất phải tạo ra đầu ra có thể kiểm tra

Có thể quy định đầu ra tối thiểu cho từng loại công việc:

| Hoạt động | Định nghĩa hoàn tất về tiến độ | Bằng chứng chất lượng liên quan |
|---|---|---|
| Review yêu cầu | Các yêu cầu trong phạm vi đã được xem xét | Quyết định, câu hỏi mở, acceptance criteria |
| Thiết kế test | Test case đã được tạo và review | Liên kết requirement, dữ liệu, expected result |
| Chuẩn bị môi trường | Môi trường sẵn sàng theo checklist | Version, config, health và dependency checks |
| Test execution | Test đã chạy hợp lệ và có trạng thái | Kết quả, log, trace, dữ liệu |
| Defect retest | Retest đã hoàn tất | Bản sửa, bước tái hiện, kết quả sau sửa |
| Performance test | Kịch bản đo đã chạy theo kế hoạch | Raw data, mô hình tải, metrics và điều kiện |
| Báo cáo | Báo cáo đã được hoàn tất và review | Liên kết bằng chứng, giới hạn và kết luận |

Điều này giúp tiến độ có đầu ra cụ thể. Tuy nhiên, “đã tạo test case” chỉ chứng minh công việc thiết kế hoàn tất, không chứng minh sản phẩm đạt tiêu chí mà test case đó sẽ kiểm tra.

### 5.2. Dùng ma trận truy vết

Một ma trận có thể liên kết:

```text
Requirement / Risk
    -> Quality criterion
        -> Test condition / Test case
            -> Execution run
                -> Evidence
                    -> Result / Defect
                        -> Quality decision
```

Ma trận cho phép nhìn thấy cả phần công việc đã làm và khoảng trống bằng chứng:

- Yêu cầu chưa có test case: khoảng trống thiết kế.
- Test case có nhưng chưa chạy: tiến độ thực thi còn thiếu.
- Test đã chạy nhưng thiếu evidence: chưa đủ căn cứ.
- Evidence có nhưng kết quả fail: tiêu chí chưa đạt.
- Evidence pass nhưng không đại diện môi trường mục tiêu: có giới hạn cần ghi rõ.
- Tiêu chí đạt nhưng chưa được người có thẩm quyền xem xét: quyết định chưa hoàn tất.

### 5.3. Phân loại trạng thái bằng chứng riêng

Nên có trạng thái bằng chứng như:

- **Not collected:** chưa thu thập.
- **Collected:** đã thu thập nhưng chưa đánh giá.
- **Validated:** đã kiểm tra tính đầy đủ và hợp lệ.
- **Accepted:** được chấp nhận làm căn cứ cho tiêu chí trong phạm vi xác định.
- **Rejected:** không thể dùng do sai phương pháp, thiếu ngữ cảnh hoặc không đáng tin.
- **Superseded:** đã được thay thế bởi bằng chứng mới hơn.

Trạng thái này không nên bị trộn với trạng thái test execution. Một test có thể hoàn tất nhưng evidence chưa validated; một evidence có thể được thu thập nhưng cần review trước khi dùng trong quyết định.

### 5.4. Báo cáo phần trăm cùng khoảng trống

Ví dụ:

- 80% test case đã thực thi.
- 93,5% pass trong số test có kết quả Pass/Fail.
- 3 test blocked, 20 test chưa chạy.
- 100% rủi ro Critical đã có bằng chứng được review.
- 2 rủi ro High chưa được xác minh trên tích hợp thật.
- 1 lỗi S1 đang mở và chặn promotion.

Báo cáo này cho thấy tiến độ thực thi chưa hoàn tất nhưng một phần rủi ro quan trọng đã có bằng chứng; đồng thời vẫn có các điều kiện chặn quyết định. Không thể kết luận phát hành chỉ từ tỷ lệ pass.

## 6. Theo dõi tiến độ qua vòng đời kiểm thử

### 6.1. Giai đoạn phân tích và thiết kế

Tiến độ có thể theo dõi:

- Yêu cầu đã được review.
- Rủi ro đã được phân loại.
- Acceptance criteria đã được làm rõ.
- Test condition và test case đã được thiết kế.
- Test data requirement đã được xác định.
- Test case đã được peer review.

Bằng chứng chất lượng ở giai đoạn này gồm traceability, tiêu chí rõ ràng, ví dụ nghiệp vụ và kết quả review. Đây là bằng chứng về mức sẵn sàng của thiết kế kiểm thử, chưa phải bằng chứng sản phẩm thực thi đúng.

### 6.2. Giai đoạn chuẩn bị

Tiến độ có thể theo dõi:

- Môi trường được cấp.
- Tài khoản và quyền được thiết lập.
- Dữ liệu được tạo.
- Công cụ và runner được cấu hình.
- Script được tích hợp.
- Smoke check của môi trường hoàn tất.

Bằng chứng cần có version, config, trạng thái dependency, dữ liệu và kết quả kiểm tra sẵn sàng. Môi trường “đã cấp” không đồng nghĩa với môi trường đủ điều kiện đo hoặc kiểm thử.

### 6.3. Giai đoạn thực thi

Tiến độ theo dõi số test đã chạy, số còn lại, blocked và thời gian thực thi. Bằng chứng gồm:

- Kết quả từng test.
- Request/response hoặc thao tác.
- Dữ liệu trước và sau.
- Log, trace và artifact.
- Môi trường và phiên bản.
- Kết quả kiểm tra tính hợp lệ.

Cần giữ cả pass và fail. Không loại test fail khỏi số liệu chỉ vì lỗi đã được biết hoặc đang chờ sửa.

### 6.4. Giai đoạn xử lý lỗi và retest

Tiến độ theo dõi:

- Defect đã triage.
- Defect đã phân công.
- Defect đang sửa.
- Defect đã triển khai bản sửa.
- Defect đã retest.
- Defect đã đóng hoặc mở lại.

Bằng chứng chất lượng gồm bước tái hiện, nguyên nhân nếu đã xác định, commit/build chứa bản sửa, kết quả retest và regression. “Developer đã sửa” là trạng thái công việc; “lỗi không còn tái hiện và không gây hồi quy trong phạm vi đã kiểm tra” mới là kết luận dựa trên bằng chứng.

### 6.5. Giai đoạn báo cáo và phát hành

Tiến độ có thể theo dõi việc hoàn thiện báo cáo, review và phê duyệt. Bằng chứng cần tổng hợp:

- Tiêu chí đã đạt/chưa đạt.
- Rủi ro đã và chưa được kiểm tra.
- Lỗi còn mở theo severity/priority.
- Giới hạn môi trường.
- Chỉ số phi chức năng.
- Quyết định chấp nhận rủi ro.
- Bằng chứng sau triển khai nếu có.

Một báo cáo đã hoàn tất không có nghĩa mọi tiêu chí đều đạt. Báo cáo có thể hoàn tất chính xác bằng cách nêu các tiêu chí chưa được xác minh.

## 7. Xây dựng dashboard tiến độ và chất lượng

### 7.1. Tách khu vực hiển thị

Một dashboard hữu ích nên có ít nhất hai khu vực:

**Tiến độ và dòng công việc**

- Phạm vi test case.
- Test design completion.
- Execution progress.
- Automation progress.
- Số việc blocked và tuổi chờ.
- Effort thực tế so với dự kiến.
- Dự báo ngày hoàn tất.

**Bằng chứng và trạng thái chất lượng**

- Requirement/risk coverage.
- Pass, fail, blocked, skipped và invalid.
- Defect theo severity và priority.
- Các tiêu chí chất lượng đã được xác minh.
- Bằng chứng đang chờ review hoặc bị từ chối.
- Rủi ro còn lại và giới hạn.
- Performance/security/reliability indicators.

Hai khu vực nên liên kết qua cùng requirement, test run và release ID để người đọc đi từ tổng quan đến bằng chứng chi tiết.

### 7.2. Hiển thị mẫu số và định nghĩa

Không hiển thị “90%” mà không nói đó là gì. Mỗi tỷ lệ nên có:

- Tên metric.
- Tử số và mẫu số.
- Phạm vi.
- Thời điểm cập nhật.
- Trạng thái bị loại khỏi mẫu số.
- Quy tắc tính.
- Nguồn dữ liệu.

Ví dụ “90% executed” cần chỉ rõ 90/100 test case đã thực thi hợp lệ; 5 blocked và 5 chưa chạy có được tách riêng không.

### 7.3. Dùng xu hướng thay vì một snapshot

Một ảnh chụp dashboard tại một thời điểm không cho biết tiến độ đang tăng hay giảm. Theo dõi theo thời gian:

- Execution progress mỗi ngày.
- Defect discovery và closure trend.
- Flaky rate.
- Blocked time.
- Requirement/risk coverage.
- Tỷ lệ retest thành công.
- Performance trend.
- Defect leakage sau phát hành.

Xu hướng giúp nhận ra việc tiến độ tăng nhưng chất lượng không cải thiện, hoặc số test pass tăng vì phạm vi test đã bị thu hẹp.

### 7.4. Tránh dashboard khuyến khích hành vi sai

Nếu chỉ thưởng cho tỷ lệ pass hoặc số test đã chạy, nhóm có thể vô tình:

- Bỏ test khó hoặc rủi ro cao.
- Giảm assertion để test dễ pass.
- Chuyển test fail thành skipped.
- Đóng lỗi khi chưa retest.
- Tăng số lượng test đơn giản nhưng không tăng coverage rủi ro.

Dashboard nên phản ánh chất lượng bằng nhiều nguồn bằng chứng và cho thấy phần chưa biết, thay vì chỉ tối ưu một con số.

## 8. Sử dụng thông tin tiến độ và chất lượng trong quyết định

### 8.1. Dự báo hoàn tất công việc

Tiến độ giúp dự báo:

- Effort còn lại.
- Năng lực cần bổ sung.
- Phụ thuộc có thể gây trễ.
- Công việc blocked.
- Ngày hoàn tất dự kiến.

Dự báo cần tính đến việc công việc còn lại có thể khó hơn phần đã hoàn tất. Ví dụ, các test dễ đã chạy trước; phần còn lại có thể gồm integration, security hoặc dữ liệu phức tạp. Không nên ngoại suy tuyến tính từ tốc độ đầu kỳ nếu độ khó không đồng đều.

### 8.2. Đánh giá mức sẵn sàng chất lượng

Bằng chứng chất lượng giúp trả lời:

- Các tiêu chí trọng yếu đã được xác minh chưa?
- Rủi ro Critical/High còn khoảng trống nào?
- Lỗi nghiêm trọng còn mở không?
- Bằng chứng có hợp lệ và gắn với đúng artifact không?
- Môi trường có đại diện đủ cho kết luận không?
- Có ngoại lệ hoặc rủi ro được chấp nhận không?

Một dự án có thể đúng tiến độ nhưng chưa sẵn sàng phát hành. Ngược lại, một số tiêu chí trọng yếu có thể đạt dù toàn bộ test execution chưa xong; quyết định khi đó phải theo chính sách và người có thẩm quyền.

### 8.3. Không dùng tiến độ để thay quality gate

Ví dụ, “đã chạy 95% test” không phải lý do tự động cho phép phát hành nếu 5% còn lại bao gồm kiểm thử phân quyền hoặc migration trọng yếu. Quality gate cần dựa vào tiêu chí và rủi ro đã xác định.

Tương tự, “100% test pass” không đủ nếu test suite chưa bao phủ yêu cầu quan trọng, dùng sai artifact hoặc evidence không hợp lệ.

### 8.4. Báo cáo rủi ro và quyết định có điều kiện

Nếu còn khoảng trống, báo cáo:

- Phần công việc chưa hoàn thành.
- Tiêu chí chưa có bằng chứng.
- Lý do và tác động.
- Biện pháp thay thế hoặc giảm thiểu.
- Người có thẩm quyền chấp nhận.
- Điều kiện hoặc thời hạn xem xét lại.

Không gộp trạng thái chưa xác minh vào “đạt có điều kiện” nếu chưa có quyết định và chủ sở hữu rủi ro.

## 9. Ví dụ tổng hợp: báo cáo regression cho release candidate

Giả sử release candidate có 100 test case trong phạm vi, gồm các hành trình thanh toán, quản lý đơn, phân quyền và báo cáo.

### 9.1. Báo cáo tiến độ

| Hoạt động | Kế hoạch | Thực tế | Tiến độ |
|---|---:|---:|---:|
| Review yêu cầu và rủi ro | 20 | 20 | 100% |
| Thiết kế test case | 100 | 100 | 100% |
| Chuẩn bị dữ liệu | 10 bộ | 10 bộ | 100% |
| Test execution | 100 | 80 | 80% |
| Retest defect đã sửa | 8 | 5 | 62,5% |
| Báo cáo cuối | 1 | 0 | 0% |

Các dòng có đơn vị khác nhau nên không cộng trực tiếp để tạo một tỷ lệ tổng. Bảng cho biết các hoạt động nào đã xong và phần nào còn lại.

### 9.2. Bằng chứng chất lượng

Trong 80 test đã thực thi hợp lệ:

- 72 Pass.
- 5 Fail.
- 3 Blocked.
- 20 Not run.

Pass rate trên số test có kết quả Pass/Fail là 93,5%. Tuy nhiên:

- Một lỗi S1 liên quan phân quyền vẫn đang mở.
- Hai test High risk bị blocked do sandbox.
- 20 test chưa chạy, trong đó có test migration và báo cáo.
- 5 defect đã có bản sửa nhưng mới 5/8 được retest.

Do đó, 93,5% không thể được diễn giải thành “chất lượng đạt 93,5%” hoặc “release sẵn sàng”. Bằng chứng cho thấy có hành vi đạt, có lỗi đã phát hiện và có khoảng trống quan trọng.

### 9.3. Kết luận quản lý phù hợp

Một kết luận có căn cứ có thể nêu:

> Tiến độ thiết kế và chuẩn bị dữ liệu đã hoàn tất; 80% test case trong phạm vi đã được thực thi hợp lệ. Trong số test có kết quả Pass/Fail, tỷ lệ pass là 93,5%. Tuy nhiên, còn một lỗi S1 về phân quyền, hai kiểm thử High risk bị blocked và 20 test chưa chạy. Chưa đủ bằng chứng để đề xuất promotion. Nhóm cần xử lý lỗi S1, khôi phục sandbox, hoàn tất các kiểm thử migration và báo cáo, sau đó đánh giá lại quality gate.

Kết luận này phân biệt rõ tình trạng công việc với chất lượng đã được chứng minh và hành động cần thực hiện.

## 10. Những sai lầm thường gặp

1. **Đồng nhất tiến độ với chất lượng:** cho rằng hoàn thành nhiều công việc đồng nghĩa sản phẩm tốt.
2. **Dùng pass rate làm tiến độ:** bỏ qua test chưa chạy và công việc chuẩn bị.
3. **Dùng execution progress làm release readiness:** không xem xét kết quả fail, rủi ro và bằng chứng.
4. **Không định nghĩa mẫu số:** các tỷ lệ không thể so sánh hoặc kiểm tra.
5. **Gộp Pass, Blocked và Skipped:** làm sai ý nghĩa của kết quả.
6. **Đếm test đã chạy nhưng không kiểm tra tính hợp lệ:** tính cả test sai build hoặc thiếu dữ liệu.
7. **Chỉ lưu kết quả tổng hợp:** không truy ra test case, dữ liệu và bằng chứng gốc.
8. **Bỏ qua lỗi nghiêm trọng vì tỷ lệ pass cao:** dùng trung bình che giấu rủi ro trọng yếu.
9. **Cộng tỷ lệ của các nhóm khác nhau:** tạo tiến độ tổng không có cơ sở.
10. **Thay đổi phạm vi hoặc trọng số giữa kỳ không ghi nhận:** làm tiến độ tăng giả tạo.
11. **Chỉ theo dõi hoạt động, không theo dõi khoảng trống bằng chứng:** không biết điều gì chưa được chứng minh.
12. **Dashboard chỉ hiển thị màu xanh:** che blocked, invalid, giới hạn môi trường và rủi ro còn lại.
13. **Đóng defect để cải thiện tiến độ:** chưa có bằng chứng retest.
14. **Dùng chỉ số để xếp hạng cá nhân:** tạo động cơ tối ưu số liệu thay vì cải thiện chất lượng.

## 11. Checklist phân biệt tiến độ thực hiện với bằng chứng về chất lượng

- [ ] Tiến độ và chất lượng được định nghĩa thành hai nhóm thông tin riêng.
- [ ] Phạm vi, đơn vị và mẫu số của từng chỉ số tiến độ được xác định.
- [ ] Trạng thái công việc phân biệt Not started, In progress, Waiting, Blocked, Review và Done.
- [ ] Trạng thái thực thi phân biệt Pass, Fail, Blocked, Skipped, Invalid và Not run.
- [ ] Mỗi tiêu chí chất lượng liên kết với requirement, risk và test case.
- [ ] Bằng chứng có build, artifact, môi trường, dữ liệu, thời điểm và nguồn thu thập.
- [ ] Kết quả fail và khoảng trống được giữ lại trong báo cáo.
- [ ] Pass rate được tính theo quy tắc rõ và hiển thị mẫu số.
- [ ] Coverage được diễn giải là phạm vi, không phải bằng chứng tính đúng.
- [ ] Các chỉ số tiến độ không được dùng thay quality gate.
- [ ] Bằng chứng có trạng thái thu thập, xác minh và chấp nhận riêng khi cần.
- [ ] Dashboard hiển thị tiến độ, chất lượng, blocked work và rủi ro còn lại.
- [ ] Trọng số tiến độ được thống nhất và thay đổi có lịch sử.
- [ ] Dự báo hoàn tất xét đến độ khó của phần việc còn lại và phụ thuộc.
- [ ] Quyết định promotion dựa trên tiêu chí và bằng chứng hợp lệ.
- [ ] Ngoại lệ có người chấp nhận, lý do và biện pháp theo dõi.
- [ ] Báo cáo nêu rõ điều đã hoàn thành, điều đã chứng minh và điều chưa được xác minh.

Phân biệt tiến độ thực hiện với bằng chứng về chất lượng giúp nhóm tránh nhầm lẫn giữa việc đã làm và kết quả đã chứng minh. Khi tiến độ được đo theo phạm vi công việc rõ ràng, còn chất lượng được đánh giá bằng bằng chứng gắn với tiêu chí và rủi ro, báo cáo sẽ trung thực hơn, dự báo có cơ sở hơn và quyết định phát hành phản ánh đúng những gì nhóm đã biết.
