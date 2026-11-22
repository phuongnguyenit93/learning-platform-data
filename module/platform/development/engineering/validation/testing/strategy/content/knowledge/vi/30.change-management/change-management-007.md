# Đo hiệu quả trước và sau trong điều kiện so sánh phù hợp

Khi thay đổi quy trình, công cụ, kiến trúc hoặc cách kiểm thử, nhóm thường muốn biết thay đổi đó có tạo ra kết quả tốt hơn hay không. Một cách tiếp cận phổ biến là đo một số chỉ số trước khi thay đổi, triển khai thay đổi rồi đo lại sau đó. Tuy nhiên, hai con số trước và sau chỉ có ý nghĩa khi chúng được thu thập trong điều kiện đủ tương đồng và cùng phản ánh một khái niệm.

Ví dụ, thời gian pipeline giảm từ 20 phút xuống 12 phút có vẻ là cải thiện rõ rệt. Nhưng nếu giai đoạn sau chạy ít test hơn, dùng runner mạnh hơn hoặc có ít tải cạnh tranh hơn, không thể kết luận riêng thay đổi quy trình đã làm pipeline nhanh hơn mà vẫn giữ chất lượng. Tương tự, số incident giảm sau một release có thể do lưu lượng thấp, mùa vụ hoặc thay đổi cách ghi nhận sự cố.

Đo hiệu quả trước và sau cần xác định mục tiêu, chỉ số, phạm vi, cửa sổ đo, điều kiện so sánh và những yếu tố có thể gây nhiễu. Khi có thể, hãy dùng nhóm đối chứng hoặc thiết kế đánh giá mạnh hơn phép so sánh đơn giản. Kết quả cần thể hiện cả mức thay đổi, độ bất định và giới hạn của kết luận.

## 1. Mục tiêu của phép đo trước và sau

Phép đo trước và sau (before-and-after measurement) so sánh kết quả của một hệ thống, quy trình hoặc nhóm đối tượng ở hai thời điểm:

- **Trước thay đổi (baseline):** trạng thái được đo trước khi can thiệp.
- **Sau thay đổi (post-change):** trạng thái được đo sau khi thay đổi đã được triển khai và có đủ thời gian ổn định.

Mục tiêu có thể là:

- Đánh giá một thay đổi có đạt mục tiêu đã đặt ra không.
- Xác định mức cải thiện hoặc suy giảm của chỉ số.
- Phát hiện tác động phụ hoặc rủi ro mới.
- Kiểm tra giả thuyết về nguyên nhân và kết quả.
- Quyết định tiếp tục, mở rộng, điều chỉnh hoặc hoàn tác thay đổi.
- Cung cấp bằng chứng cho quản lý thay đổi và cải tiến liên tục.

Phép đo này thường được dùng để đánh giá thay đổi trong chiến lược kiểm thử, chẳng hạn:

- Chuyển một số kiểm thử từ giai đoạn phát hành sang pull request.
- Tự động hóa một bộ regression test.
- Áp dụng kiểm thử theo rủi ro hoặc chọn test theo vùng mã thay đổi.
- Thay đổi cấu hình runner hoặc cách chạy song song.
- Bổ sung contract test giữa các dịch vụ.
- Thay đổi quy trình triage lỗi hoặc quản lý flaky test.
- Áp dụng quality gate mới trước khi triển khai.

Một kết quả tốt không chỉ là chỉ số mục tiêu tăng hoặc giảm theo mong muốn. Nhóm cần xác minh thay đổi có thực sự tạo ra giá trị, có duy trì chất lượng và có tác động ngoài dự kiến hay không.

## 2. Xác định câu hỏi và giả thuyết trước khi đo

Trước khi thu thập dữ liệu, hãy viết rõ câu hỏi cần trả lời. Câu hỏi càng cụ thể thì việc chọn chỉ số và điều kiện so sánh càng dễ.

Ví dụ câu hỏi chưa đủ rõ:

- Quy trình mới có tốt hơn không?
- Pipeline có nhanh hơn không?
- Chất lượng có tăng không?

Ví dụ câu hỏi có thể đo:

- Sau khi chuyển unit test liên quan sang pull request, thời gian từ lúc mở PR đến phản hồi kiểm thử đầu tiên có giảm không?
- Việc chạy regression theo rủi ro có làm giảm tổng thời gian pipeline mà không tăng lỗi lọt sau merge không?
- Sau khi bổ sung contract test, số lỗi tương thích API được phát hiện trước tích hợp có tăng không?
- Sau khi áp dụng quy trình triage flaky test, tỷ lệ test không ổn định có giảm trong bốn tuần tiếp theo không?

### 2.1. Viết giả thuyết có thể kiểm chứng

Một giả thuyết nên nêu:

- Thay đổi được đánh giá.
- Đối tượng hoặc phạm vi áp dụng.
- Kết quả dự kiến.
- Chỉ số chính.
- Các chỉ số bảo vệ để phát hiện tác động phụ.
- Khoảng thời gian đánh giá.

Ví dụ:

> Khi áp dụng chạy test theo dependency graph cho các pull request của dịch vụ Order, thời gian phản hồi kiểm thử trung vị sẽ giảm ít nhất 25% trong bốn tuần, trong khi tỷ lệ lỗi lọt sau merge và tỷ lệ test bị bỏ sót không tăng.

Giả thuyết này xác định một chỉ số mục tiêu và hai điều kiện bảo vệ. Nó cũng giới hạn phạm vi và thời gian đánh giá. Nếu chỉ đo thời gian pipeline, nhóm có thể vô tình tối ưu tốc độ bằng cách bỏ kiểm thử có giá trị.

### 2.2. Phân biệt mục tiêu, chỉ số và tiêu chí quyết định

- **Mục tiêu:** kết quả tổ chức muốn đạt, ví dụ giảm thời gian phản hồi.
- **Chỉ số:** đại lượng được đo, ví dụ thời gian từ PR creation đến test result.
- **Tiêu chí quyết định:** điều kiện để kết luận, ví dụ giảm tối thiểu 25% mà không làm tăng defect escape rate vượt ngưỡng đã thống nhất.

Không nên đợi đến khi thấy dữ liệu sau thay đổi mới chọn chỉ số có kết quả thuận lợi. Hãy thống nhất định nghĩa và tiêu chí trước khi triển khai.

## 3. Chọn chỉ số phù hợp với loại thay đổi

Chỉ số phải phản ánh mục tiêu và có thể đo ổn định ở cả hai giai đoạn. Nên dùng một chỉ số chính cùng một số chỉ số phụ và chỉ số bảo vệ.

### 3.1. Chỉ số về tốc độ và luồng công việc

- Thời gian từ commit đến phản hồi kiểm thử đầu tiên.
- Thời gian từ mở PR đến khi có kết quả required checks.
- Thời gian chạy pipeline hoặc từng stage.
- Thời gian chờ runner và thời gian thực thi thực tế.
- Thời gian từ phát hiện defect đến khi xác minh bản sửa.
- Thời gian từ quyết định Go đến khi hoàn tất triển khai.

Phải xác định điểm bắt đầu và kết thúc. "Thời gian pipeline" có thể là thời gian thực tế trôi qua, tổng thời gian CPU của các job hay thời gian chờ trong hàng đợi; ba đại lượng này không giống nhau.

### 3.2. Chỉ số về chất lượng và độ tin cậy

- Tỷ lệ defect escape sau một điểm kiểm soát.
- Số incident liên quan đến thay đổi trên mỗi release hoặc mỗi đơn vị lưu lượng.
- Tỷ lệ test flaky.
- Tỷ lệ test bị skip, blocked hoặc quarantine.
- Tỷ lệ lỗi được phát hiện trước merge so với sau triển khai.
- Tỷ lệ rollback hoặc hotfix sau release.
- Tỷ lệ test quan trọng có bằng chứng đạt.

Không nên chỉ dùng số defect tuyệt đối nếu số release, số giao dịch hoặc mức độ sử dụng thay đổi đáng kể giữa hai giai đoạn.

### 3.3. Chỉ số về phạm vi và mức bảo vệ

- Bao phủ yêu cầu có bằng chứng đạt.
- Bao phủ rủi ro theo trọng số.
- Bao phủ hành trình quan trọng.
- Số nhánh hoặc điều kiện quan trọng chưa được kiểm tra.
- Số contract được xác minh trong pipeline.
- Tỷ lệ thay đổi có test liên quan chạy thành công.

Các chỉ số bao phủ cần định nghĩa rõ mẫu số và trạng thái bằng chứng. Một test được liên kết với yêu cầu nhưng chưa chạy không thể được tính như bằng chứng đạt.

### 3.4. Chỉ số về chi phí và năng lực

- Runner minutes hoặc giờ máy.
- Chi phí cloud và dịch vụ kiểm thử.
- Số job chạy lại.
- Số giờ công bảo trì test.
- Mức sử dụng CPU, RAM, browser và database.
- Chi phí trên mỗi PR, release hoặc lần chạy có giá trị.

Một thay đổi giảm thời gian nhưng tăng mạnh chi phí tài nguyên có thể không đem lại hiệu quả tổng thể.

### 3.5. Chỉ số bảo vệ (guardrail metrics)

Guardrail giúp phát hiện việc tối ưu một mục tiêu làm suy giảm phần khác. Ví dụ:

| Mục tiêu chính | Chỉ số bảo vệ |
|---|---|
| Giảm thời gian pipeline | Defect escape, test skipped, coverage rủi ro cao |
| Giảm chi phí runner | Thời gian chờ, độ ổn định và tỷ lệ job timeout |
| Tăng số test tự động | Tỷ lệ flaky, chi phí bảo trì và độ tin cậy assertion |
| Rút ngắn thời gian phát hành | Incident sau release, rollback và lỗi dữ liệu |
| Tăng throughput API | Error rate, latency p95/p99 và tính nhất quán |

Chỉ số bảo vệ cần có ngưỡng chấp nhận trước khi bắt đầu đo.

## 4. Định nghĩa phép đo nhất quán

Một trong những nguyên nhân phổ biến khiến so sánh trước và sau sai lệch là định nghĩa chỉ số thay đổi giữa hai giai đoạn.

Với mỗi chỉ số, ghi:

- Tên và mục đích.
- Đơn vị đo.
- Công thức và tử số/mẫu số.
- Điểm bắt đầu, điểm kết thúc hoặc sự kiện tạo dữ liệu.
- Nguồn dữ liệu và cách thu thập.
- Quy tắc loại trừ.
- Cách xử lý giá trị thiếu, trùng hoặc bất thường.
- Phân đoạn cần theo dõi.
- Owner và phiên bản định nghĩa.

Ví dụ, nếu đo thời gian phản hồi PR:

- Bắt đầu: thời điểm PR được mở hoặc cập nhật commit cuối cùng.
- Kết thúc: thời điểm tất cả kiểm tra bắt buộc hoàn tất lần đầu.
- Đơn vị: phút.
- Loại trừ: thời gian PR bị đóng hoặc bị đánh dấu draft theo quy tắc thống nhất.
- Phân đoạn: ngôn ngữ, loại thay đổi, kích thước PR và module.

Nếu giai đoạn trước chỉ đo thời gian job chạy, còn giai đoạn sau đo thời gian từ lúc mở PR đến lúc có kết quả, hai con số không thể so sánh trực tiếp.

### 4.1. Dùng cùng đơn vị phân tích

Đơn vị phân tích có thể là:

- Một lần chạy pipeline.
- Một pull request.
- Một commit.
- Một release.
- Một giao dịch hoặc một người dùng hoạt động.
- Một ngày/tuần của một dịch vụ.

Không trộn đơn vị. Ví dụ, so sánh số defect trên mỗi release với số defect trên mỗi tuần có thể tạo kết luận sai nếu tần suất phát hành thay đổi.

### 4.2. Chuẩn hóa theo mẫu số

Khi quy mô hoạt động khác nhau, dùng tỷ lệ hoặc chỉ số trên một đơn vị phù hợp:

\[
\text{Defect rate} =
\frac{\text{Số defect trong phạm vi}}
{\text{Số release hoặc đơn vị hoạt động}}
\]

Ví dụ, báo cáo defect trên 100 release hoặc trên 10.000 giao dịch có thể dễ so sánh hơn số defect tuyệt đối. Mẫu số phải được chọn theo cơ chế phát sinh defect và không được thay đổi giữa hai giai đoạn.

### 4.3. Giữ nguyên quy tắc phân loại

Nếu định nghĩa "incident nghiêm trọng" thay đổi giữa hai giai đoạn, tỷ lệ incident trước và sau không còn cùng ý nghĩa. Nếu cần đổi định nghĩa, hãy tính lại dữ liệu lịch sử theo định nghĩa mới khi có thể, hoặc ghi rõ đây là điểm gãy trong chuỗi dữ liệu.

## 5. Chọn baseline trước thay đổi

Baseline là trạng thái tham chiếu để so sánh. Baseline kém đại diện sẽ làm mọi kết luận sau đó thiếu tin cậy.

### 5.1. Chọn cửa sổ thời gian phù hợp

Baseline cần đủ dài để phản ánh biến động bình thường. Độ dài phụ thuộc vào:

- Chu kỳ phát hành.
- Mùa vụ và lịch hoạt động của người dùng.
- Tần suất phát sinh sự cố.
- Độ biến động của workload.
- Số lượng test run hoặc giao dịch.
- Thời gian cần để một thay đổi bộc lộ tác động.

Một ngày dữ liệu có thể đủ để kiểm tra latency của một workload ổn định, nhưng không đủ để so sánh số incident hiếm gặp. Với chỉ số ít xảy ra, cần thời gian dài hơn hoặc một cách đo nhạy hơn.

### 5.2. Loại trừ hoặc đánh dấu giai đoạn bất thường

Sự cố lớn, bảo trì, chiến dịch khuyến mại, thay đổi lưu lượng hoặc downtime có thể làm baseline không đại diện. Không nên xóa dữ liệu bất lợi một cách tùy tiện. Hãy:

- Xác định quy tắc loại trừ trước.
- Ghi nguyên nhân và thời điểm.
- Giữ dữ liệu gốc để kiểm tra lại.
- Có thể báo cáo cả kết quả bao gồm và không bao gồm giai đoạn bất thường.

Nếu một sự cố là đặc điểm thường xuyên của hệ thống, loại bỏ nó khỏi baseline có thể làm đánh giá quá lạc quan.

### 5.3. Lưu cấu hình và ngữ cảnh baseline

Ghi lại:

- Phiên bản ứng dụng và test suite.
- Cấu hình CI runner và hạ tầng.
- Môi trường, dữ liệu và dependency.
- Lưu lượng, request mix và số người dùng.
- Lịch phát hành và thay đổi đồng thời.
- Phiên bản công cụ đo và định nghĩa chỉ số.

Baseline không chỉ là một con số; đó là con số cùng điều kiện đã tạo ra nó.

## 6. Đảm bảo điều kiện trước và sau có thể so sánh

So sánh hợp lệ cần kiểm soát hoặc ít nhất ghi nhận các yếu tố có thể ảnh hưởng đến kết quả.

### 6.1. Các yếu tố cần xem xét

| Yếu tố | Cách làm sai lệch kết quả | Cách kiểm soát |
|---|---|---|
| Lưu lượng | Sau thay đổi có ít request hơn nên latency giảm | So sánh cùng workload hoặc chuẩn hóa theo request mix |
| Cấu hình hạ tầng | Runner sau thay đổi mạnh hơn | Giữ cấu hình giống nhau hoặc đo và điều chỉnh |
| Dữ liệu | Dataset sau nhỏ hơn hoặc cache nóng hơn | Dùng dataset tương đương và ghi trạng thái cache |
| Thành phần phụ thuộc | Database hoặc vendor đổi phiên bản | Ghi phiên bản và kiểm tra tác động |
| Mùa vụ | Lưu lượng theo ngày/tuần khác nhau | So sánh cùng ngày hoặc cùng chu kỳ |
| Nhóm người dùng | Sau thay đổi có nhiều người dùng nhẹ hơn | Phân đoạn theo cohort và hành vi |
| Thay đổi đồng thời | Một tối ưu khác được triển khai cùng lúc | Ghi change log, tách tác động nếu có thể |
| Cách đo | Instrumentation hoặc định nghĩa metric đổi | Giữ cùng định nghĩa hoặc hiệu chỉnh chuỗi lịch sử |
| Nhân sự và quy trình | Nhóm trực hoặc cách xử lý thay đổi | Ghi nhận thay đổi vận hành và phân tích ảnh hưởng |

### 6.2. So sánh cùng loại workload

Với kiểm thử hiệu năng, cần giữ tương đồng về:

- Arrival rate và concurrency.
- Request mix và payload.
- Think time và thời lượng.
- Kích thước dữ liệu.
- Warm-up và trạng thái cache.
- Cấu hình generator và SUT.
- Tải nền và dịch vụ phụ thuộc.

Nếu mục tiêu chính là đánh giá khả năng chịu tải sau khi thay đổi, có thể dùng nhiều mức tải giống nhau ở cả hai giai đoạn để so sánh đường cong hiệu năng.

### 6.3. So sánh cùng loại thay đổi

Với quy trình CI, PR nhỏ và PR lớn có thời gian chạy khác nhau. Nếu sau thay đổi có nhiều PR nhỏ hơn, thời gian trung bình có thể giảm dù quy trình không hiệu quả hơn. Hãy phân tầng theo kích thước PR, loại module, ngôn ngữ hoặc loại test.

### 6.4. Ghi nhận thay đổi đồng thời

Nếu cùng lúc thay đổi runner, test selection, cache và số worker, không thể quy toàn bộ cải thiện cho một yếu tố duy nhất. Có thể đánh giá cả gói thay đổi như một can thiệp tổng thể, nhưng phải nói rõ giới hạn khi muốn quy nguyên nhân cho từng thành phần.

## 7. Chọn thiết kế đánh giá phù hợp

So sánh trước và sau đơn giản dễ thực hiện nhưng yếu về khả năng chứng minh nguyên nhân. Khi có thể, hãy dùng thiết kế mạnh hơn.

### 7.1. So sánh trước và sau đơn giản

Đo cùng chỉ số trên cùng hệ thống trước và sau thay đổi.

Phù hợp khi:

- Muốn đánh giá nhanh một thay đổi nhỏ.
- Điều kiện môi trường khá ổn định.
- Không thể tạo nhóm đối chứng.
- Mục tiêu là theo dõi xu hướng hơn là khẳng định quan hệ nhân quả.

Hạn chế: mọi yếu tố khác thay đổi cùng thời điểm đều có thể góp phần tạo ra kết quả.

### 7.2. Nhóm đối chứng

Chọn một nhóm không nhận thay đổi trong cùng khoảng thời gian. Nhóm can thiệp và nhóm đối chứng nên tương đồng về đặc điểm quan trọng.

Ví dụ, áp dụng quy trình test selection mới cho một số dịch vụ, giữ các dịch vụ tương đồng khác dùng quy trình cũ trong thời gian đánh giá. So sánh sự thay đổi ở cả hai nhóm.

Hạn chế: hai nhóm có thể khác nhau về kiến trúc, lưu lượng, đội ngũ hoặc độ phức tạp. Cần kiểm tra mức tương đồng và tránh để thay đổi lan sang nhóm đối chứng.

### 7.3. A/B test hoặc phân nhóm ngẫu nhiên

Nếu có thể phân bổ ngẫu nhiên đối tượng vào nhóm can thiệp và đối chứng, đây thường là thiết kế mạnh để giảm sai lệch lựa chọn. Ví dụ, phân luồng một tỷ lệ pull request hoặc workload tương đương qua hai cấu hình runner.

Cần bảo đảm việc phân nhóm không gây ảnh hưởng lẫn nhau, có đủ số quan sát và không vi phạm chính sách an toàn hoặc trải nghiệm người dùng.

### 7.4. Difference-in-differences (DiD)

Khi có nhóm can thiệp và nhóm đối chứng, có thể so sánh mức thay đổi của hai nhóm:

\[
\text{DiD} =
(\text{After}_{T} - \text{Before}_{T})
-
(\text{After}_{C} - \text{Before}_{C})
\]

Trong đó \(T\) là nhóm được áp dụng thay đổi và \(C\) là nhóm đối chứng.

Ví dụ, thời gian phản hồi PR của nhóm can thiệp giảm 8 phút, trong khi nhóm đối chứng giảm 2 phút do runner chung được nâng cấp. Ước lượng DiD là \(-8 - (-2) = -6\) phút. Có thể diễn giải rằng thay đổi ở nhóm can thiệp gắn với mức giảm thêm khoảng 6 phút so với xu hướng đối chứng, nếu các giả định của phương pháp phù hợp.

DiD dựa trên giả định quan trọng rằng nếu không có can thiệp, xu hướng của hai nhóm sẽ tương tự (parallel trends). Cần xem dữ liệu trước can thiệp để đánh giá giả định này. Nếu hai nhóm có xu hướng khác nhau hoặc có spillover, kết luận sẽ yếu.

### 7.5. Chuỗi thời gian gián đoạn (interrupted time series)

Đo chỉ số ở nhiều thời điểm trước và sau thay đổi để xem mức hoặc xu hướng có thay đổi tại thời điểm can thiệp hay không. Phương pháp này hữu ích khi không có nhóm đối chứng nhưng có dữ liệu theo thời gian đủ dài.

Cần xem xét mùa vụ, xu hướng nền, các sự kiện xảy ra cùng thời điểm và thay đổi cách đo. Một điểm tăng/giảm ngay sau release chưa đủ chứng minh nguyên nhân.

### 7.6. Rollout theo từng giai đoạn

Triển khai thay đổi lần lượt cho các nhóm hoặc dịch vụ. Nhóm chưa được triển khai có thể tạm thời làm đối chứng, nếu đủ tương đồng và không bị ảnh hưởng gián tiếp.

Thiết kế này cho phép quan sát rủi ro ở quy mô nhỏ trước khi mở rộng. Tuy nhiên, cần ghi rõ thứ tự triển khai và lý do chọn nhóm; nhóm được triển khai sớm có thể khác nhóm triển khai muộn.

## 8. Tính mức thay đổi

### 8.1. Chênh lệch tuyệt đối

\[
\Delta = \text{After} - \text{Before}
\]

Ví dụ, thời gian pipeline giảm từ 20 phút xuống 12 phút:

\[
\Delta = 12 - 20 = -8 \text{ phút}
\]

Chênh lệch tuyệt đối dễ hiểu và hữu ích khi đơn vị đo có ý nghĩa trực tiếp.

### 8.2. Thay đổi tương đối

\[
\text{Relative Change} =
\frac{\text{After} - \text{Before}}{\text{Before}}
\times 100\%
\]

Với ví dụ trên:

\[
\frac{12 - 20}{20}\times 100\% = -40\%
\]

Thời gian giảm 40% so với baseline. Nếu chỉ số càng thấp càng tốt, có thể gọi đây là mức cải thiện 40%. Với chỉ số càng cao càng tốt, cần diễn giải dấu và chiều thay đổi cho rõ.

Không dùng tỷ lệ phần trăm khi baseline bằng 0 hoặc rất gần 0 mà không chọn cách biểu diễn khác. Khi đó, báo cáo chênh lệch tuyệt đối hoặc một chỉ số có mẫu số phù hợp hơn.

### 8.3. Tỷ lệ và mẫu số

Với defect rate:

\[
\text{Defect Rate} =
\frac{\text{Defect được phát hiện trong phạm vi}}
{\text{Số release trong phạm vi}}
\times 100
\]

Nếu giai đoạn trước có 6 defect trên 100 release và giai đoạn sau có 4 defect trên 100 release, tỷ lệ giảm từ 6 xuống 4 trên 100 release, tương đương giảm tương đối khoảng 33,3%. Cần kiểm tra định nghĩa defect và mức độ nghiêm trọng có nhất quán không.

### 8.4. Dùng phân vị khi dữ liệu lệch

Thời gian pipeline, latency và thời gian xử lý thường có phân bố lệch. Trung bình có thể bị ảnh hưởng bởi một số lần chạy rất lâu. Nên xem thêm:

- Median/p50 cho trải nghiệm điển hình.
- p90/p95/p99 cho phần đuôi phân bố.
- Min/max để phát hiện giá trị bất thường, nhưng không dùng riêng chúng để kết luận.
- Phân bố hoặc biểu đồ theo thời gian để nhìn biến động.

So sánh p95 trước và sau cần đủ số quan sát và cùng cách thu thập. Không nên so sánh percentile từ các mẫu rất nhỏ như thể chúng ổn định.

## 9. Đánh giá độ bất định và độ tin cậy

Mọi phép đo đều có biến động. Một mức thay đổi nhỏ có thể chỉ là dao động ngẫu nhiên hoặc do số mẫu ít.

### 9.1. Báo cáo số quan sát

Luôn nêu:

- Số PR, pipeline run, release, request hoặc người tham gia.
- Số quan sát bị loại và lý do.
- Số lần test bị retry hoặc blocked.
- Phạm vi thời gian và số nhóm được đo.

Không chỉ báo cáo phần trăm. Tỷ lệ 50% từ 2 quan sát khác nhiều so với 50% từ 2.000 quan sát.

### 9.2. Khoảng tin cậy

Khi phù hợp, báo cáo khoảng tin cậy cho chênh lệch hoặc tỷ lệ. Cách tính phụ thuộc loại dữ liệu:

- Tỷ lệ thành công/thất bại có thể dùng khoảng tin cậy cho tỷ lệ nhị thức.
- Thời gian chạy thường lệch có thể dùng bootstrap hoặc phương pháp phù hợp với phân bố.
- Dữ liệu theo nhóm hoặc theo thời gian cần xét sự phụ thuộc giữa các quan sát.

Khoảng tin cậy rộng cho thấy kết quả còn bất định. Không nên chỉ nhìn việc một khoảng có chứa 0 hay không; cần xem độ lớn tác động có ý nghĩa thực tế hay không.

### 9.3. Ý nghĩa thống kê và ý nghĩa thực tế

Một thay đổi nhỏ có thể có ý nghĩa thống kê khi số mẫu rất lớn nhưng không tạo khác biệt đáng kể trong vận hành. Ngược lại, một cải thiện lớn nhưng mẫu nhỏ có thể đáng quan tâm dù chưa đủ dữ liệu để kết luận chắc chắn.

Trước khi đo, hãy xác định mức thay đổi tối thiểu có ý nghĩa (minimum practically important difference). Ví dụ, giảm 30 giây trong pipeline 2 giờ có thể ít giá trị hơn giảm 3 phút trong pipeline 5 phút, tùy mục tiêu và số lần chạy.

### 9.4. Không dừng đo ngay khi thấy kết quả mong muốn

Nếu liên tục kiểm tra dữ liệu và dừng ngay khi đạt ngưỡng, xác suất kết luận nhầm có thể tăng. Hãy đặt trước thời lượng, số mẫu hoặc quy tắc dừng. Nếu cần giám sát liên tục vì an toàn, tách quy tắc dừng khẩn cấp khỏi tiêu chí kết luận hiệu quả cuối cùng.

## 10. Phân đoạn dữ liệu và tránh kết luận sai

Một chỉ số tổng thể có thể che giấu kết quả trái ngược giữa các nhóm. Ví dụ, thời gian pipeline trung bình giảm vì tỷ lệ PR nhỏ tăng, trong khi PR lớn lại chậm hơn.

Nên phân đoạn theo:

- Dịch vụ, module hoặc repository.
- Loại thay đổi và kích thước PR.
- Ngôn ngữ, build tool hoặc loại test.
- Nhóm người dùng, tenant hoặc khu vực.
- Mức tải, request mix và thời điểm trong ngày.
- Runner, môi trường và cấu hình.
- Mức độ rủi ro và loại release.

### 10.1. Cẩn trọng với Simpson's paradox

Simpson's paradox xảy ra khi xu hướng trong từng nhóm khác với xu hướng tổng hợp do tỷ trọng nhóm thay đổi. Ví dụ, mỗi nhóm PR có thể chậm hơn một chút sau thay đổi, nhưng thời gian trung bình toàn hệ thống lại giảm vì giai đoạn sau có nhiều PR nhỏ hơn.

Để tránh:

- Báo cáo số liệu tổng cùng số liệu theo nhóm.
- Giữ cách phân nhóm nhất quán.
- Cân nhắc chuẩn hóa theo cơ cấu nhóm.
- Giải thích khi tỷ trọng nhóm thay đổi.

### 10.2. Tránh chọn mẫu thuận tiện

Không chỉ lấy những lần chạy thành công, những release ít lỗi hoặc những người dùng dễ tiếp cận. Cần định nghĩa cách chọn mẫu và giữ lại các lần thất bại, timeout hoặc bị blocked theo quy tắc đã thống nhất.

Nếu có loại trừ, ghi rõ số lượng, lý do và tác động có thể có đến kết quả.

## 11. Kiểm soát các yếu tố gây nhiễu

Yếu tố gây nhiễu (confounder) vừa có liên quan đến thời điểm áp dụng thay đổi vừa có thể ảnh hưởng đến kết quả.

Ví dụ:

- Cùng lúc nâng cấp runner và tối ưu test selection.
- Lưu lượng production giảm trong giai đoạn sau.
- Đội ngũ thay đổi cách phân loại incident.
- Một dịch vụ phụ thuộc được nâng cấp.
- Thay đổi sản phẩm làm request mix khác đi.
- Có chiến dịch khuyến mại hoặc ngày nghỉ.
- Cách đo được thay đổi hoặc metric bị mất dữ liệu.

### 11.1. Cách xử lý

- Thiết kế nhóm đối chứng khi có thể.
- Giữ điều kiện đo giống nhau.
- Ghi nhận thay đổi đồng thời.
- Phân đoạn theo yếu tố có thể gây nhiễu.
- Chuẩn hóa theo workload hoặc cơ cấu đối tượng.
- Dùng chuỗi thời gian để xem xu hướng trước và sau.
- Thực hiện phân tích độ nhạy với các quy tắc loại trừ khác nhau.

Không phải yếu tố gây nhiễu nào cũng có thể loại bỏ. Nếu không kiểm soát được, hãy hạ mức khẳng định và mô tả giới hạn trong báo cáo.

## 12. Quy trình đo trước và sau

### Bước 1: Xác định thay đổi và câu hỏi

Mô tả chính xác can thiệp, phạm vi, nhóm chịu tác động và kết quả mong đợi. Ghi giả thuyết cùng chỉ số chính và guardrail.

### Bước 2: Chốt định nghĩa đo

Xác định công thức, đơn vị, nguồn dữ liệu, mẫu số, quy tắc loại trừ và phân đoạn. Bảo đảm cách đo trước và sau giống nhau.

### Bước 3: Thu thập baseline

Chọn cửa sổ đủ đại diện, lưu dữ liệu thô, số quan sát, cấu hình và ngữ cảnh. Kiểm tra tính đầy đủ và ổn định của instrumentation.

### Bước 4: Chọn thiết kế so sánh

Quyết định dùng pre/post đơn giản, nhóm đối chứng, A/B, DiD, chuỗi thời gian hoặc rollout theo giai đoạn. Ghi giả định và giới hạn.

### Bước 5: Triển khai thay đổi có kiểm soát

Ghi phiên bản, thời điểm, nhóm áp dụng và thay đổi đồng thời. Nếu rủi ro cao, triển khai canary hoặc theo từng nhóm.

### Bước 6: Đợi trạng thái ổn định và đo sau

Đặt thời gian warm-up hoặc thời gian để tác động bộc lộ. Thu thập dữ liệu với cùng định nghĩa và điều kiện phù hợp.

### Bước 7: Kiểm tra chất lượng dữ liệu

Kiểm tra thiếu dữ liệu, trùng lặp, thay đổi schema, lệch thời gian, sai đơn vị và sự khác biệt về cách ghi nhận.

### Bước 8: Phân tích mức thay đổi và độ bất định

Tính chênh lệch tuyệt đối, tương đối hoặc DiD khi phù hợp. Xem phân bố, khoảng tin cậy, phân đoạn và guardrail.

### Bước 9: Diễn giải và đưa ra quyết định

Phân biệt quan sát với kết luận nhân quả. Quyết định mở rộng, điều chỉnh, giữ nguyên hoặc rollback theo tiêu chí đã đặt.

### Bước 10: Lưu kết quả và theo dõi dài hạn

Lưu baseline, dữ liệu sau, công thức, cấu hình, quyết định và hành động tiếp theo. Theo dõi xem hiệu quả có duy trì hay suy giảm theo thời gian.

~~~mermaid
flowchart TD
    A["Xác định thay đổi và giả thuyết"]
    B["Chốt chỉ số, công thức và guardrail"]
    C["Thu thập baseline cùng ngữ cảnh"]
    D["Chọn thiết kế so sánh phù hợp"]
    E["Triển khai thay đổi có kiểm soát"]
    F["Đo sau trong điều kiện tương đương"]
    G["Kiểm tra chất lượng và tính so sánh của dữ liệu"]
    H["Phân tích chênh lệch, độ bất định và yếu tố gây nhiễu"]
    I["Quyết định tiếp tục, điều chỉnh hoặc rollback"]
    J["Lưu bằng chứng và theo dõi dài hạn"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J
~~~

## 13. Ví dụ: đánh giá thay đổi quy trình kiểm thử CI

Giả sử nhóm áp dụng test selection theo dependency graph cho các pull request của một dịch vụ Java. Mục tiêu là giảm thời gian phản hồi mà vẫn bảo vệ các yêu cầu và rủi ro quan trọng.

### 13.1. Thiết kế phép đo

- Phạm vi: repository Order Service.
- Baseline: bốn tuần trước khi thay đổi.
- Giai đoạn sau: bốn tuần sau khi rollout và ổn định.
- Chỉ số chính: median thời gian từ PR mở đến kết quả required checks đầu tiên.
- Chỉ số bảo vệ: defect escape trên 100 PR, tỷ lệ test bị skip, tỷ lệ flaky và risk coverage.
- Điều kiện: cùng loại runner, cùng định nghĩa thời gian, cùng quy tắc loại PR draft.
- Phân đoạn: PR nhỏ/lớn và loại thay đổi.

Nếu có một dịch vụ tương đồng chưa áp dụng thay đổi, nhóm có thể dùng làm nhóm đối chứng. Cần kiểm tra xu hướng trước đó và mức tương đồng của hai dịch vụ.

### 13.2. Dữ liệu minh họa

| Chỉ số | Trước | Sau | Thay đổi |
|---|---:|---:|---:|
| Median phản hồi PR | 20 phút | 12 phút | Giảm 8 phút (40%) |
| Defect escape trên 100 PR | 3,0 | 2,8 | Giảm khoảng 6,7% |
| Tỷ lệ flaky test | 4,0% | 4,2% | Tăng 0,2 điểm phần trăm |
| Test bị skip | 0,5% | 1,8% | Tăng 1,3 điểm phần trăm |
| Risk coverage cho rủi ro High/Critical | 96% | 91% | Giảm 5 điểm phần trăm |

Các số liệu trên chỉ là ví dụ minh họa. Thời gian phản hồi đã giảm đáng kể, nhưng tỷ lệ test bị skip tăng và bao phủ rủi ro giảm. Vì vậy, chưa thể kết luận thay đổi thành công chỉ dựa vào tốc độ.

### 13.3. Điều tra nguyên nhân

Nhóm phát hiện dependency graph không nhận diện một số thay đổi trong file cấu hình chung, nên một vài test bảo vệ rủi ro cao không được chọn. Nhóm cần:

- Sửa quy tắc phát hiện dependency.
- Bổ sung tập test nền luôn chạy cho các thay đổi cấu hình và thư viện chung.
- Xác minh lại risk coverage.
- Chạy lại phép đo sau khi sửa.
- Giữ guardrail về test skip và defect escape trong quality gate.

### 13.4. Quyết định

Nhóm có thể giữ thay đổi trong phạm vi canary nếu có biện pháp bù trừ và người có thẩm quyền chấp nhận rủi ro; nếu không, cần tạm dừng mở rộng hoặc quay về cấu hình cũ. Chỉ mở rộng khi tốc độ cải thiện đi cùng mức bảo vệ tối thiểu đã thống nhất.

Ví dụ này minh họa vì sao phải đo nhiều chiều: chỉ số mục tiêu cho thấy lợi ích, còn guardrail phát hiện tác động phụ có thể làm mất chất lượng.

## 14. Diễn giải kết quả và giới hạn kết luận

Khi báo cáo, phân biệt ba mức phát biểu:

- **Quan sát:** "Median thời gian PR giảm từ 20 xuống 12 phút trong giai đoạn đo."
- **Liên hệ:** "Mức giảm xuất hiện sau khi áp dụng test selection và cùng thời điểm với thay đổi runner."
- **Nhân quả:** "Test selection làm thời gian PR giảm 8 phút."

Mức thứ ba đòi hỏi thiết kế đánh giá đủ mạnh để loại trừ các giải thích thay thế. Một phép so sánh trước/sau đơn giản thường chỉ hỗ trợ mô tả thay đổi và gợi ý mối liên hệ, không tự chứng minh nguyên nhân.

### 14.1. Các câu hỏi trước khi kết luận

- Baseline có đại diện không?
- Hai giai đoạn có cùng định nghĩa và đơn vị đo không?
- Có thay đổi đồng thời nào ảnh hưởng kết quả không?
- Cơ cấu đối tượng hoặc workload có thay đổi không?
- Số quan sát có đủ và có độc lập không?
- Có dữ liệu thiếu hoặc loại trừ không?
- Chỉ số chính và guardrail có cùng chiều kết quả không?
- Tác động có ý nghĩa thực tế và có duy trì không?
- Có nhóm đối chứng hoặc dữ liệu xu hướng trước đó không?

### 14.2. Tránh tuyên bố quá mức

Nếu chỉ có dữ liệu mô tả, dùng cách diễn đạt như "ghi nhận", "đi cùng với", "sau khi áp dụng" hoặc "phù hợp với giả thuyết". Chỉ dùng "gây ra" hoặc "làm tăng/giảm" khi thiết kế và bằng chứng hỗ trợ kết luận nhân quả.

## 15. Báo cáo kết quả trước và sau

Một báo cáo có thể tái sử dụng nên gồm:

| Thành phần | Nội dung |
|---|---|
| Mục tiêu | Vấn đề và quyết định cần hỗ trợ |
| Thay đổi | Mô tả can thiệp, phạm vi và ngày triển khai |
| Giả thuyết | Kết quả dự kiến và guardrail |
| Chỉ số | Định nghĩa, công thức, đơn vị và nguồn |
| Baseline | Cửa sổ thời gian, số mẫu, cấu hình và ngữ cảnh |
| Giai đoạn sau | Cửa sổ đo, thời gian ổn định và số mẫu |
| Điều kiện so sánh | Workload, cohort, môi trường và yếu tố khác biệt |
| Phương pháp | Pre/post, đối chứng, A/B, DiD hoặc time series |
| Kết quả | Giá trị trước/sau, chênh lệch và phân đoạn |
| Độ bất định | Khoảng tin cậy, biến động và giới hạn mẫu |
| Guardrail | Chỉ số bảo vệ và các ngưỡng bị vượt |
| Giới hạn | Confounder, dữ liệu thiếu và giả định |
| Kết luận | Quan sát được hỗ trợ đến mức nào |
| Quyết định | Mở rộng, điều chỉnh, giữ nguyên hoặc rollback |
| Hành động | Owner, thời hạn và mốc đo tiếp theo |

Nên lưu dữ liệu thô hoặc truy vấn tái lập cùng phiên bản định nghĩa metric. Biểu đồ tổng hợp cần cho phép xem chi tiết theo nhóm và theo thời gian.

## 16. Những sai lầm thường gặp

- **So sánh hai khoảng thời gian không tương đồng:** mùa vụ hoặc workload làm thay đổi kết quả.
- **Đổi định nghĩa chỉ số giữa chừng:** số liệu trước và sau không còn cùng ý nghĩa.
- **Chỉ chọn chỉ số thuận lợi:** che giấu tác động phụ lên chất lượng hoặc chi phí.
- **Dùng số tuyệt đối khi quy mô thay đổi:** số lỗi tăng có thể chỉ vì số release tăng.
- **Bỏ qua mẫu số:** tỷ lệ có thể thay đổi do số quan sát khác nhau.
- **Kết luận nhân quả từ một phép pre/post đơn giản:** bỏ qua yếu tố gây nhiễu.
- **Không giữ baseline và cấu hình:** không thể tái lập hoặc giải thích kết quả.
- **Loại dữ liệu bất lợi sau khi xem kết quả:** tạo thiên lệch lựa chọn.
- **Không phân đoạn:** số tổng che giấu nhóm bị suy giảm.
- **Chỉ nhìn trung bình:** bỏ qua đuôi phân bố và các trường hợp rất chậm.
- **Dừng đo khi đạt mục tiêu:** tăng nguy cơ kết luận nhầm do quan sát lặp lại.
- **Không đo sau khi hiệu ứng ổn định:** kết quả ngắn hạn có thể không duy trì.
- **Tối ưu một chỉ số làm suy giảm chỉ số khác:** ví dụ pipeline nhanh hơn vì bỏ test quan trọng.

## 17. Checklist đo hiệu quả trước và sau

- [ ] Câu hỏi đánh giá và giả thuyết được viết trước khi đo.
- [ ] Thay đổi, phạm vi và thời điểm áp dụng được xác định.
- [ ] Chỉ số chính và guardrail được chọn theo mục tiêu.
- [ ] Công thức, đơn vị, mẫu số và quy tắc loại trừ nhất quán.
- [ ] Baseline đủ đại diện và có lưu ngữ cảnh.
- [ ] Cửa sổ trước/sau xét đến mùa vụ và chu kỳ hoạt động.
- [ ] Workload, dữ liệu, môi trường và cấu hình có thể so sánh.
- [ ] Thay đổi đồng thời và yếu tố gây nhiễu được ghi nhận.
- [ ] Thiết kế đối chứng hoặc phương pháp đánh giá phù hợp được chọn.
- [ ] Số quan sát và dữ liệu thiếu được báo cáo.
- [ ] Chênh lệch tuyệt đối, tương đối và độ bất định được diễn giải đúng.
- [ ] Dữ liệu được phân đoạn để phát hiện kết quả khác biệt giữa nhóm.
- [ ] Guardrail được kiểm tra trước khi kết luận thành công.
- [ ] Kết luận không vượt quá bằng chứng về quan hệ nhân quả.
- [ ] Quyết định, owner và hành động tiếp theo được ghi nhận.
- [ ] Có kế hoạch theo dõi hiệu quả dài hạn.

## 18. Duy trì vòng lặp đo lường và cải tiến

Đo hiệu quả không kết thúc khi báo cáo được gửi. Kết quả cần quay lại quy trình quản lý thay đổi:

1. So sánh kết quả với giả thuyết và tiêu chí quyết định.
2. Xác định lợi ích, tác động phụ và nhóm bị ảnh hưởng.
3. Quyết định giữ, mở rộng, điều chỉnh hoặc rollback.
4. Giao owner cho hành động còn lại.
5. Cập nhật baseline sau khi thay đổi được chấp nhận ổn định.
6. Theo dõi chỉ số bảo vệ và hiệu quả dài hạn.
7. Dùng kết quả để cải thiện thiết kế cho lần thay đổi tiếp theo.

Không cập nhật baseline mới quá sớm khi thay đổi còn trong giai đoạn thử nghiệm hoặc có ngoại lệ chưa đóng. Nếu baseline được thay đổi, lưu lịch sử để có thể so sánh xu hướng dài hạn.

~~~mermaid
flowchart TD
    A["Giả thuyết và baseline đã chốt"]
    B["Triển khai thay đổi"]
    C["Đo kết quả trong điều kiện phù hợp"]
    D["So sánh chỉ số chính và guardrail"]
    E{"Đạt mục tiêu mà không vi phạm guardrail?"}
    F["Mở rộng và cập nhật baseline"]
    G["Điều chỉnh hoặc rollback"]
    H["Ghi nhận bài học và cập nhật kế hoạch"]
    I["Theo dõi dài hạn"]
    A --> B --> C --> D --> E
    E -->|Có| F --> I
    E -->|Không| G --> H
    I --> H
    H -. "Giả thuyết cải tiến tiếp theo" .-> A
~~~

Đo hiệu quả trước và sau chỉ có giá trị khi hai giai đoạn được so sánh bằng cùng định nghĩa, đơn vị và điều kiện đủ tương đồng. Khi nhóm xác định baseline đại diện, kiểm soát yếu tố gây nhiễu, chọn thiết kế đánh giá phù hợp và xem cả chỉ số chính lẫn guardrail, kết quả sẽ hỗ trợ quyết định quản lý thay đổi đáng tin cậy hơn. Báo cáo cần nêu rõ điều gì đã quan sát, điều gì có thể quy cho thay đổi và điều gì vẫn chưa chắc chắn để tổ chức tiếp tục cải tiến dựa trên bằng chứng.
