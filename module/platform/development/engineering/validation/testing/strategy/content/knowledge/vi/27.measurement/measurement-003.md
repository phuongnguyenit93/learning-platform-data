# Đo thời gian có phản hồi và độ tin cậy của kết quả kiểm thử

Kiểm thử tạo ra giá trị khi nhóm nhận được thông tin đủ sớm để hành động và có thể tin vào thông tin đó. Một bộ kiểm thử chạy rất nhanh nhưng thường báo lỗi giả sẽ làm người phát triển mất thời gian điều tra. Một bộ kiểm thử đáng tin cậy nhưng chỉ trả kết quả sau nhiều giờ có thể khiến lỗi lan qua nhiều thay đổi trước khi được phát hiện. Vì vậy, chiến lược kiểm thử cần đo cả **thời gian có phản hồi** và **độ tin cậy của kết quả**.

Thời gian có phản hồi (feedback time) mô tả khoảng thời gian từ lúc một thay đổi hoặc yêu cầu kiểm thử được đưa vào quy trình đến khi người cần thông tin nhận được kết quả có thể sử dụng. Độ tin cậy của kết quả (test result reliability) mô tả mức độ kết quả phản ánh đúng trạng thái chất lượng của sản phẩm trong điều kiện đã xác định, với ít cảnh báo giả, ít lỗi bị bỏ sót và khả năng tái hiện phù hợp.

Hai yếu tố liên hệ chặt chẽ. Giảm thời gian chạy bằng cách bỏ các kiểm tra quan trọng có thể làm kết quả kém tin cậy. Tăng số lần chạy lại để xử lý flaky test có thể làm thời gian phản hồi dài hơn mà vẫn không cải thiện chất lượng tín hiệu. Nhóm cần đo đúng từng giai đoạn, hiểu nguồn gây biến động và chọn cải tiến dựa trên bằng chứng.

## 1. Vì sao cần đo thời gian phản hồi và độ tin cậy?

Nếu chỉ đo tổng thời gian pipeline, nhóm khó biết người phát triển đang phải chờ ở đâu. Một pipeline mất 25 phút có thể dành 3 phút chạy test và 22 phút chờ runner, tải dependency hoặc chờ môi trường. Hai tình huống cần cách cải thiện khác nhau.

Nếu chỉ đo tỷ lệ kiểm thử đạt, nhóm cũng không biết tín hiệu có đáng tin hay không. Tỷ lệ đạt cao có thể do sản phẩm tốt, nhưng cũng có thể do ca kiểm thử yếu, bị bỏ qua hoặc không kiểm tra rủi ro quan trọng. Tỷ lệ thất bại cao có thể chỉ ra nhiều lỗi sản phẩm, hoặc do môi trường không ổn định và test bị flaky.

Đo lường có mục tiêu giúp:

- Biết người phát triển nhận được tín hiệu nhanh đến đâu sau một thay đổi.
- Phân biệt thời gian xếp hàng, chuẩn bị môi trường, thực thi và phân tích kết quả.
- Phát hiện ca kiểm thử không ổn định hoặc tạo cảnh báo giả.
- Đánh giá khả năng tái hiện lỗi và chất lượng bằng chứng.
- Ưu tiên cải thiện test suite có tác động lớn đến dòng công việc.
- Xác định trade-off giữa tốc độ, phạm vi bao phủ và mức độ tin cậy.
- Theo dõi xem các thay đổi về công cụ, môi trường hoặc quy trình có thực sự cải thiện kết quả không.

Mục tiêu không phải làm cho mọi kiểm thử nhanh nhất có thể. Mục tiêu là cung cấp tín hiệu đúng lúc, đủ chính xác cho quyết định đang cần được đưa ra.

## 2. Xác định thời gian phản hồi cần đo

Trước khi đo, nhóm cần thống nhất điểm bắt đầu và điểm kết thúc. Nếu mỗi dashboard dùng mốc thời gian khác nhau, các con số sẽ không thể so sánh.

### 2.1. Các mốc thời gian trong một lần kiểm thử

Một lần chạy CI hoặc kiểm thử có thể gồm các mốc:

1. Thay đổi được đẩy lên hoặc pull request được tạo/cập nhật.
2. Pipeline được kích hoạt.
3. Job được đưa vào hàng đợi.
4. Runner bắt đầu nhận job.
5. Môi trường và dữ liệu được chuẩn bị.
6. Ca kiểm thử bắt đầu thực thi.
7. Ca hoặc suite kết thúc.
8. Kết quả được tổng hợp và lưu.
9. Thông báo được gửi đến người cần hành động.
10. Người phát triển xác nhận hoặc bắt đầu xử lý kết quả.

Các khoảng thời gian tương ứng có thể được đo riêng:

| Khoảng thời gian | Cách tính | Điều nó phản ánh |
|---|---|---|
| Trigger latency | Thời điểm pipeline bắt đầu trừ thời điểm thay đổi được ghi nhận | Độ trễ kích hoạt quy trình |
| Queue time | Runner bắt đầu nhận job trừ thời điểm job vào hàng đợi | Khả năng cung cấp runner và mức cạnh tranh tài nguyên |
| Setup time | Thời điểm test bắt đầu trừ thời điểm runner nhận job | Chi phí tải dependency, dựng môi trường và chuẩn bị dữ liệu |
| Execution time | Thời điểm test kết thúc trừ thời điểm test bắt đầu | Thời gian thực thi kiểm thử |
| Result processing time | Kết quả được công bố trừ thời điểm test kết thúc | Chi phí tổng hợp, phân loại và lưu báo cáo |
| Notification latency | Người nhận được thông báo trừ thời điểm kết quả được công bố | Độ trễ chuyển kết quả đến người cần biết |
| End-to-end feedback time | Người nhận có kết quả hữu ích trừ thời điểm thay đổi được ghi nhận | Thời gian thực tế từ thay đổi đến phản hồi có thể hành động |

Nếu người phát triển chỉ nhận được kết quả sau khi pipeline hoàn tất, end-to-end feedback time nên kết thúc ở thời điểm kết quả đến được kênh họ sử dụng. Nếu cần xác định thời gian đến khi có chẩn đoán hữu ích, có thể đo thêm thời gian triage riêng.

### 2.2. Phân biệt thời gian thực thi và thời gian chờ

Một suite có execution time ngắn vẫn có thể phản hồi chậm nếu runner thường xuyên xếp hàng hoặc môi trường cần chuẩn bị lâu. Ngược lại, một suite chạy 20 phút nhưng bắt đầu ngay và đưa ra kết quả đáng tin cậy có thể phù hợp với một pipeline nightly.

Hãy đo ít nhất ba lớp:

- **Thời gian chờ:** Job chưa thực sự làm công việc kiểm thử, ví dụ chờ runner hoặc khóa tài nguyên.
- **Thời gian chuẩn bị:** Tạo môi trường, cài dependency, nạp dữ liệu và khởi động dịch vụ.
- **Thời gian kiểm thử và công bố:** Thực thi, tổng hợp và gửi kết quả.

Phân tách này giúp tránh tối ưu nhầm. Nếu queue time là nút thắt, rút ngắn assertion hoặc giảm số ca sẽ không giải quyết được vấn đề chính.

### 2.3. Đo theo loại phản hồi

Không phải mọi kết quả đều có cùng giá trị hoặc thời điểm cần thiết. Có thể phân loại:

- **Phản hồi cục bộ:** Kết quả từ unit test hoặc kiểm tra tĩnh khi lập trình viên đang làm việc.
- **Phản hồi pull request:** Kết quả bắt buộc trước khi merge.
- **Phản hồi tích hợp:** Kết quả từ bộ kiểm thử chạy sau khi thay đổi được tích hợp.
- **Phản hồi theo lịch:** Kết quả từ nightly, weekly hoặc bộ kiểm thử mở rộng.
- **Phản hồi trước phát hành:** Bằng chứng cần thiết để quyết định phát hành.
- **Phản hồi sau triển khai:** Smoke test, health check và giám sát hành vi thực tế.

Đặt mục tiêu thời gian riêng cho từng nhóm sẽ thực tế hơn một ngưỡng chung. Unit test có thể cần phản hồi trong vài phút; kiểm thử tải hoặc hồi quy trên nhiều nền tảng có thể cần thời gian dài hơn nhưng phải hoàn thành trước mốc quyết định tương ứng.

## 3. Định nghĩa chỉ số thời gian một cách nhất quán

Mỗi chỉ số cần có tên, công thức, điểm đo, phạm vi dữ liệu và cách xử lý lần chạy bị hủy hoặc bị chặn.

Ví dụ định nghĩa:

| Chỉ số | Định nghĩa đề xuất | Lưu ý |
|---|---|---|
| Median feedback time | Trung vị thời gian từ trigger đến khi kết quả hữu ích được công bố | Ít bị ảnh hưởng bởi một số lần chạy rất dài |
| P90/P95 feedback time | Phân vị 90/95 của thời gian phản hồi | Thể hiện trải nghiệm ở các lần chạy chậm |
| Queue time P95 | Phân vị 95 của thời gian chờ runner | Hữu ích để đánh giá năng lực CI |
| Test execution duration | Tổng hoặc thời gian theo suite/ca thực thi | Cần làm rõ có tính thời gian chạy song song hay không |
| Time to first useful result | Thời điểm nhận được kết quả đầu tiên đủ để hành động trừ thời điểm trigger | Có thể khác thời điểm pipeline hoàn tất |
| Time to diagnosis | Thời điểm có phân loại hoặc nguyên nhân sơ bộ trừ thời điểm cảnh báo | Phản ánh khả năng chẩn đoán, không chỉ tốc độ máy |
| Feedback SLA attainment | Tỷ lệ lần chạy có feedback time nằm trong mục tiêu | Cần xác định rõ mẫu số và ngoại lệ |

Ví dụ, mục tiêu “95% pull request nhận được kết quả unit test trong 5 phút” cần làm rõ:

- Bắt đầu tính từ lúc push commit hay lúc pull request được cập nhật?
- Kết thúc khi job hoàn thành hay khi trạng thái được hiển thị?
- Những lần chạy bị hủy do commit mới có tính vào mẫu số không?
- Chỉ đo unit test hay bao gồm thời gian chờ runner và tải dependency?
- Khoảng đo là tuần, tháng hay một số lượng lần chạy tối thiểu?

Không thay đổi định nghĩa giữa các kỳ báo cáo nếu muốn so sánh xu hướng. Nếu cần đổi cách đo, hãy ghi nhận ngày thay đổi và tính lại dữ liệu lịch sử nếu có thể.

## 4. Dùng phân phối thay vì chỉ dùng trung bình

Thời gian kiểm thử thường có phân phối lệch: phần lớn lần chạy nhanh, một số lần rất chậm do queue, timeout hoặc môi trường. Trung bình có thể bị kéo lên bởi các giá trị cực đoan và không mô tả tốt trải nghiệm thường gặp.

Nên theo dõi:

- **Median (P50):** Một nửa lần chạy nhanh hơn hoặc bằng giá trị này.
- **P90:** 90% lần chạy hoàn tất trong khoảng thời gian này hoặc thấp hơn.
- **P95:** Hữu ích để theo dõi đuôi phân phối và trải nghiệm của phần lớn các lần chạy chậm.
- **P99:** Có thể dùng cho pipeline quan trọng nếu có đủ dữ liệu; cần thận trọng vì số mẫu nhỏ làm chỉ số biến động.
- **Min/max:** Chỉ dùng để phát hiện bất thường, không nên là chỉ số mục tiêu duy nhất.

Ví dụ, hai bộ kiểm thử đều có median 6 phút. Bộ A có P95 là 9 phút; bộ B có P95 là 28 phút. Người phát triển có trải nghiệm điển hình tương tự nhưng bộ B thường xuyên có lần chạy kéo dài, gây khó dự đoán thời gian chờ.

Khi so sánh, cần dùng cùng nhóm loại job, môi trường, runner class và khoảng thời gian. Không gộp unit test với load test rồi lấy một median chung vì hai loại hoạt động có mục tiêu và phân phối khác nhau.

## 5. Đo độ tin cậy của kết quả kiểm thử

Độ tin cậy không đồng nghĩa với tỷ lệ pass cao. Một kết quả đáng tin cậy cần phản ánh đúng điều kiện sản phẩm, được tạo từ phép kiểm tra phù hợp và có thể diễn giải hoặc tái hiện.

Các chiều chính gồm:

1. **Tính đúng của tín hiệu:** Khi test báo fail, có khả năng đó là lỗi sản phẩm hoặc sai lệch thực sự không? Khi test báo pass, phạm vi kiểm tra có đủ để hỗ trợ kết luận không?
2. **Tính ổn định:** Cùng sản phẩm và điều kiện tương đương có cho kết quả nhất quán không?
3. **Khả năng tái hiện:** Có thể chạy lại với cùng build, dữ liệu, cấu hình và seed để xác minh phát hiện không?
4. **Khả năng chẩn đoán:** Kết quả có chỉ ra ca, bước, đầu vào và bằng chứng liên quan không?
5. **Tính đầy đủ của phạm vi:** Bộ kiểm thử có bao phủ yêu cầu và rủi ro mà kết luận đang đề cập không?
6. **Tính toàn vẹn của dữ liệu:** Log, báo cáo và test result có gắn đúng build, môi trường và thời điểm không?

Một ca kiểm thử có thể ổn định nhưng kiểm tra sai yêu cầu. Một ca có thể phát hiện lỗi thật nhưng không tái hiện được vì thiếu dữ liệu hoặc log. Vì vậy, nên đo các chiều riêng và không dùng một tỷ lệ duy nhất để đại diện cho toàn bộ độ tin cậy.

## 6. Đo flaky test và độ ổn định

Flaky test là ca kiểm thử cho kết quả không nhất quán trong những điều kiện được cho là tương đương, chẳng hạn có lần pass và có lần fail dù sản phẩm không thay đổi. Flaky test làm giảm niềm tin vào pipeline và có thể che khuất lỗi thật.

### 6.1. Các chỉ số cơ bản

| Chỉ số | Cách tính hoặc ý nghĩa |
|---|---|
| Flaky failure rate | Số lần thất bại được xác định là không ổn định chia cho tổng số lần chạy, theo định nghĩa của nhóm |
| Retry recovery rate | Tỷ lệ lần chạy fail ban đầu nhưng pass khi chạy lại trong cùng điều kiện được kiểm soát |
| Pass/fail transition rate | Tỷ lệ ca có trạng thái thay đổi giữa các lần chạy lặp |
| Quarantine count | Số ca đang bị cách ly khỏi cổng chặn chính vì chưa đủ ổn định |
| Flaky recurrence | Tỷ lệ ca đã sửa nhưng tái xuất hiện tình trạng không ổn định |
| Time to stabilize | Thời gian từ khi phát hiện flaky test đến khi có bản sửa được xác nhận ổn định |

Những chỉ số này cần được định nghĩa cẩn thận. Retry recovery rate cao có thể cho thấy flaky test, nhưng cũng có thể là lỗi môi trường tạm thời hoặc race condition trong sản phẩm. Không tự động gắn nhãn mọi lần “fail rồi pass” là lỗi test.

### 6.2. Cách xác định flaky test

Khi một ca thất bại:

1. Giữ lại log, trace, dữ liệu và trạng thái lần chạy đầu.
2. Kiểm tra build, commit, cấu hình, runner và môi trường có thay đổi không.
3. Chạy lại có kiểm soát nếu việc chạy lại an toàn và không tạo tác dụng phụ trùng lặp.
4. So sánh kết quả, thời gian, tài nguyên và trạng thái phụ thuộc.
5. Phân loại nguyên nhân: lỗi sản phẩm, lỗi kiểm thử, lỗi môi trường, dữ liệu hoặc phụ thuộc ngoài.
6. Ghi nhận người phụ trách và kế hoạch khắc phục.

Không nên chạy lại liên tục cho đến khi pass rồi chỉ lưu kết quả cuối. Lần fail ban đầu là bằng chứng quan trọng và phải được giữ lại.

### 6.3. Đo độ ổn định bằng chạy lặp

Với một ca quan trọng, có thể chạy lặp nhiều lần trên cùng build và cấu hình để ước lượng mức ổn định. Ví dụ, chạy 50 lần trong điều kiện được kiểm soát. Nếu có 2 lần thất bại không tái hiện, cần điều tra trước khi đưa ca vào cổng chặn phát hành.

Số lần chạy cần phù hợp với rủi ro và chi phí. Một vài lần chạy pass không đủ chứng minh độ ổn định cao, đặc biệt với lỗi hiếm. Báo cáo nên nêu số mẫu và khoảng thời gian để người đọc hiểu giới hạn kết luận.

## 7. Phân biệt false positive và false negative

Độ tin cậy của kết quả còn phụ thuộc khả năng phân biệt lỗi thật và cảnh báo sai.

- **False positive:** Test báo lỗi nhưng sản phẩm thực tế đáp ứng yêu cầu trong điều kiện được kiểm tra. Nguyên nhân có thể là expected result sai, dữ liệu không hợp lệ, môi trường lỗi hoặc assertion quá chặt.
- **False negative:** Test báo đạt dù sản phẩm có lỗi hoặc không đáp ứng yêu cầu. Nguyên nhân có thể là assertion yếu, dữ liệu không bao phủ, kiểm tra bị bỏ qua hoặc oracle không phát hiện sai lệch.

Ví dụ, test chỉ kiểm tra API trả HTTP 200 có thể pass dù số dư tài khoản bị trừ hai lần. Đây là nguy cơ false negative vì kiểm tra không xác minh bất biến nghiệp vụ quan trọng. Một test so sánh ảnh giao diện theo từng pixel có thể fail do khác biệt render vô hại, tạo false positive nếu ngưỡng so sánh không phù hợp.

### 7.1. Các chỉ số liên quan

Khi có cách xác định kết quả chuẩn, nhóm có thể theo dõi:

- **Precision của cảnh báo:** Trong số các cảnh báo fail được điều tra, tỷ lệ được xác nhận là lỗi hoặc sai lệch thực tế.
- **Tỷ lệ cảnh báo giả:** Trong số cảnh báo fail, tỷ lệ không phải lỗi sản phẩm theo định nghĩa đã thống nhất.
- **Defect escape rate:** Tỷ lệ lỗi sản phẩm được phát hiện sau giai đoạn mà bộ kiểm thử được kỳ vọng phát hiện.
- **Mutation score:** Tỷ lệ mutant bị bộ kiểm thử phát hiện trên tổng mutant hợp lệ được xem xét, dùng như chỉ báo độ nhạy của test suite.
- **Assertion effectiveness:** Mức độ assertion kiểm tra kết quả quan trọng thay vì chỉ xác nhận thao tác đã chạy.

Không phải lúc nào cũng có thể tính false negative chính xác vì không biết toàn bộ lỗi chưa được phát hiện. Có thể dùng mutation testing, review test, phân tích lỗi lọt và kiểm thử thăm dò để ước lượng những điểm mù. Cần ghi rõ đây là chỉ báo thay thế, không phải phép đo đầy đủ mọi lỗi bị bỏ sót.

## 8. Đo khả năng tái hiện và chẩn đoán

Một phát hiện có giá trị cao hơn khi nhóm khác có thể tái hiện hoặc xác minh độc lập. Để đánh giá khả năng tái hiện, cần lưu đủ ngữ cảnh:

- Build ID, commit và phiên bản artifact.
- Phiên bản test suite và cấu hình chạy.
- Môi trường, runner, hệ điều hành, trình duyệt hoặc runtime.
- Dữ liệu đầu vào, testRunId và trạng thái ban đầu.
- Seed ngẫu nhiên, clock hoặc timezone nếu liên quan.
- Phiên bản dependency và endpoint phụ thuộc.
- Log, trace, screenshot hoặc bằng chứng cần thiết.
- Kết quả mong đợi và kết quả thực tế.

Có thể theo dõi:

- Tỷ lệ lỗi có thể tái hiện trong môi trường tương đương.
- Thời gian trung bình hoặc P90 để tái hiện lỗi.
- Tỷ lệ báo cáo có đủ dữ liệu để bắt đầu điều tra.
- Thời gian từ cảnh báo đến khi có phân loại nguyên nhân.
- Tỷ lệ lỗi bị đóng do thiếu bằng chứng hoặc không thể tái hiện.

Không nên yêu cầu mọi lỗi phải tái hiện giống hệt nếu hệ thống có tính ngẫu nhiên hoặc phân tán. Khi đó, cần lưu đủ dữ liệu và điều kiện để phân tích xác suất, quan hệ hoặc trạng thái cuối.

## 9. Đo chất lượng tín hiệu của toàn bộ test suite

Một suite đáng tin cậy cần cung cấp tín hiệu có ý nghĩa cho rủi ro đã xác định. Số lượng ca, code coverage hoặc tỷ lệ pass không thể tự mình chứng minh điều đó.

Những góc nhìn cần xem xét:

- **Liên kết với yêu cầu và rủi ro:** Ca nào kiểm tra yêu cầu hoặc rủi ro nào?
- **Độ nhạy:** Nếu hành vi quan trọng bị thay đổi sai, test có khả năng phát hiện không?
- **Độ bao phủ trường hợp:** Có luồng chính, ngoại lệ, giá trị biên và quyền truy cập quan trọng không?
- **Độ ổn định:** Ca có cho kết quả nhất quán trong điều kiện tương đương không?
- **Tính độc lập của oracle:** Expected result có căn cứ và không dùng lại cùng logic đang kiểm thử không?
- **Khả năng chẩn đoán:** Kết quả có giúp xác định vị trí và nguyên nhân không?
- **Tính cập nhật:** Test có còn phù hợp với phiên bản yêu cầu và sản phẩm hiện tại không?

Mutation testing có thể giúp đánh giá test suite có phát hiện các thay đổi sai có chủ đích hay không. Tuy nhiên, mutation score cao không chứng minh mọi yêu cầu được kiểm thử hoặc mọi lỗi thực tế sẽ bị phát hiện. Cần kết hợp với phân tích rủi ro, review và dữ liệu lỗi thực tế.

## 10. Xây dựng dashboard đo lường

Dashboard nên hỗ trợ quyết định và điều tra, không chỉ hiển thị nhiều biểu đồ. Một cấu trúc hữu ích có thể gồm:

### 10.1. Bảng thời gian phản hồi

| Nhóm kiểm thử | P50 feedback | P95 feedback | Queue P95 | Mục tiêu |
|---|---:|---:|---:|---:|
| Unit test pull request | 3 phút | 6 phút | 30 giây | P95 dưới 8 phút |
| API/contract test | 5 phút | 11 phút | 1 phút | P95 dưới 15 phút |
| Integration test | 12 phút | 28 phút | 3 phút | P95 dưới 35 phút |
| Nightly regression | 42 phút | 75 phút | 5 phút | Hoàn tất trước giờ làm việc |

Các số liệu trên chỉ minh họa cách trình bày, không phải ngưỡng chuẩn cho mọi dự án. Nhóm cần xác lập mục tiêu từ nhu cầu phát triển, quy mô test suite và rủi ro.

### 10.2. Bảng độ tin cậy

| Nhóm kiểm thử | Flaky rate | Retry recovery | Lỗi giả được xác nhận | Có thể tái hiện |
|---|---:|---:|---:|---:|
| Unit | 0,2% | 0,1% | Thấp | Cao |
| API/contract | 0,8% | 0,5% | Thấp | Cao |
| Integration | 3,5% | 2,4% | Trung bình | Trung bình |
| End-to-end UI | 6,0% | 4,8% | Cao | Trung bình |

Đây cũng là số liệu giả định. Dashboard thực tế cần nêu rõ cách tính, cửa sổ thời gian và số lần chạy. Nếu một nhóm chỉ có 10 lần chạy, tỷ lệ 10% có ý nghĩa khác nhóm có 10.000 lần chạy.

### 10.3. Phân đoạn dữ liệu

Nên có thể lọc theo:

- Repository, nhóm sản phẩm, nhánh hoặc loại thay đổi.
- Nhóm test, suite, ca kiểm thử hoặc mức rủi ro.
- Build, commit, môi trường và runner class.
- Lần chạy đầu và lần chạy lại.
- Kết quả pass, fail, blocked, skipped hoặc cancelled.
- Nguyên nhân được phân loại sau điều tra.

Không gộp các trạng thái khác bản chất. Một test bị skipped do điều kiện không đáp ứng không phải pass; một job bị hủy vì commit mới không giống job fail do assertion.

## 11. Thiết lập mục tiêu và SLO cho phản hồi

Nhóm có thể định nghĩa Service Level Objective (SLO) nội bộ cho thời gian phản hồi của các nhóm kiểm thử quan trọng. SLO giúp thống nhất kỳ vọng và phát hiện xu hướng suy giảm.

Ví dụ:

- 95% pull request nhận kết quả unit test trong vòng 8 phút.
- 90% integration test hoàn thành và công bố kết quả trong vòng 30 phút.
- 98% nightly regression có kết quả hoặc trạng thái blocked rõ ràng trước giờ làm việc.
- Tỷ lệ flaky của nhóm test chặn merge duy trì dưới ngưỡng nội bộ đã thống nhất.

Đây là ví dụ minh họa. Mục tiêu thực tế phải dựa trên dữ liệu nền, mức độ quan trọng và khả năng cung cấp tài nguyên. Không nên đặt SLO chỉ vì một con số đẹp hoặc dùng một mục tiêu cho tất cả repository.

### 11.1. Chọn ngưỡng hợp lý

Quy trình đề xuất:

1. Thu thập dữ liệu nền trong một khoảng thời gian đủ đại diện.
2. Phân đoạn theo loại test và môi trường.
3. Xác định thời gian phản hồi mà người dùng quy trình cần.
4. Chọn percentile phù hợp, thường dùng P90 hoặc P95 cho trải nghiệm chậm.
5. Xác định cách xử lý job bị hủy, blocked và retry.
6. Thử nghiệm mục tiêu và theo dõi tác động đến chất lượng.
7. Rà soát định kỳ khi quy mô test suite hoặc hạ tầng thay đổi.

Không nên tối ưu SLO thời gian bằng cách bỏ kiểm thử có giá trị cao. Nếu không thể đáp ứng, hãy cải thiện song song hóa, runner, dữ liệu, môi trường hoặc cách phân tầng test.

### 11.2. Error budget và đánh đổi

Với một SLO, nhóm có thể theo dõi tỷ lệ lần chạy vượt ngưỡng như một dạng error budget. Khi tỷ lệ vượt ngưỡng tăng, nhóm nên dành thời gian xử lý nguyên nhân thay vì tiếp tục thêm ca làm pipeline chậm hơn.

Ví dụ, nếu P95 feedback time của pull request vượt mục tiêu liên tục, hãy xem queue time, thời gian cài dependency, số ca chạy trùng lặp và mức song song. Nếu flaky rate tăng, cần ưu tiên độ tin cậy trước khi mở rộng số lượng test chặn.

## 12. Thu thập dữ liệu đo lường chính xác

Đo lường chỉ hữu ích khi dữ liệu đầu vào chính xác và có thể đối chiếu. Nên chuẩn hóa sự kiện cho mỗi lần chạy.

Một bản ghi tối thiểu có thể gồm:

```json
{
  "runId": "run-2026-00421",
  "buildId": "build-2.8.0-1452",
  "suite": "integration",
  "triggeredAt": "2026-11-16T09:00:00Z",
  "queuedAt": "2026-11-16T09:00:02Z",
  "startedAt": "2026-11-16T09:01:10Z",
  "testsStartedAt": "2026-11-16T09:02:30Z",
  "testsFinishedAt": "2026-11-16T09:13:40Z",
  "resultPublishedAt": "2026-11-16T09:14:05Z",
  "status": "failed",
  "attempt": 1,
  "environment": "test"
}
```

Đây là ví dụ cấu trúc, không phải schema bắt buộc. Trong hệ thống thực tế, cần đồng bộ đồng hồ giữa các thành phần hoặc dùng timestamp từ nguồn có độ tin cậy phù hợp. Nếu các mốc đến từ nhiều máy có clock skew, phép trừ thời gian có thể sai.

Các thực hành tốt:

- Dùng một `runId` duy nhất xuyên suốt pipeline và báo cáo.
- Ghi timestamp cho từng giai đoạn thay vì chỉ tổng thời gian.
- Gắn kết quả với commit, build, suite, môi trường và runner.
- Lưu attempt number để phân biệt lần chạy đầu với retry.
- Ghi trạng thái blocked, skipped, cancelled và failed riêng.
- Lưu nguyên nhân được xác nhận sau điều tra, không chỉ dựa trên mã exit.
- Bảo vệ dữ liệu cá nhân và bí mật trong log.
- Kiểm tra tính đầy đủ của telemetry trước khi dùng dashboard để ra quyết định.

## 13. Phân tích nguyên nhân khi thời gian phản hồi hoặc độ tin cậy suy giảm

Khi một chỉ số xấu đi, không nên lập tức tăng runner hoặc xóa test. Hãy tìm giai đoạn và nhóm nguyên nhân.

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Queue time tăng | Thiếu runner, nhiều job đồng thời, runner bị khóa | Kiểm tra tải, lịch chạy, giới hạn concurrency và thời gian cấp runner |
| Setup time tăng | Dependency tải chậm, image lớn, seed dữ liệu lâu | Kiểm tra cache, artifact, image và quy trình chuẩn bị |
| Execution time tăng | Suite phình to, test tuần tự, timeout dài | Phân tích thời gian theo ca, song song hóa và loại bỏ trùng lặp có kiểm soát |
| P95 tăng nhưng median ổn định | Một số runner hoặc môi trường bất thường | Phân đoạn theo runner, vùng, thời điểm và loại test |
| Retry recovery tăng | Flaky test, dependency biến động hoặc race condition | Giữ log lần đầu, phân loại và tái hiện có kiểm soát |
| False positive tăng | Oracle sai, dữ liệu không sạch, assertion quá chặt | Review expected result, fixture và điều kiện môi trường |
| False negative hoặc lỗi lọt tăng | Assertion yếu, thiếu trường hợp, test bị bỏ qua | Review rủi ro, mutation testing, test data và mapping yêu cầu |
| Khó tái hiện lỗi | Thiếu seed, build ID, log hoặc môi trường tương đương | Bổ sung telemetry và quy trình lưu bằng chứng |
| Kết quả công bố chậm | Tổng hợp report, upload artifact hoặc notification chậm | Đo riêng result processing và notification latency |

Phân tích nên bắt đầu từ dữ liệu của các lần chạy cụ thể. So sánh một lần chạy chậm với một lần bình thường cùng loại, cùng build hoặc cùng điều kiện để tìm khác biệt.

## 14. Cải thiện thời gian phản hồi mà vẫn giữ độ tin cậy

Một số biện pháp có thể giảm thời gian mà không làm mất bằng chứng quan trọng:

### 14.1. Phân tầng test theo thời điểm

Đưa kiểm tra nhanh và rủi ro cao vào pull request; chạy bộ hồi quy rộng hơn sau tích hợp hoặc theo lịch. Mỗi tầng cần có mục tiêu rõ và không được bỏ quên các rủi ro quan trọng.

### 14.2. Song song hóa có kiểm soát

Chia suite thành shard hoặc worker độc lập. Bảo đảm dữ liệu, tài khoản, queue và tài nguyên được cô lập. Song song hóa không hiệu quả nếu các worker tranh chấp database hoặc cùng chờ một dịch vụ giới hạn tốc độ.

### 14.3. Tối ưu setup và dependency

Dùng image được version hóa, cache dependency an toàn, seed dữ liệu hiệu quả và môi trường dùng một lần. Đo riêng setup time để biết cải tiến nào có tác động.

### 14.4. Loại bỏ kiểm tra trùng lặp có căn cứ

Nếu nhiều ca xác nhận cùng một điều kiện ở cùng cấp độ, có thể hợp nhất hoặc chuyển một số kiểm tra xuống cấp thấp hơn. Trước khi bỏ, cần xác nhận rủi ro vẫn được bao phủ ở vị trí khác.

### 14.5. Tăng khả năng chẩn đoán

Thông báo lỗi rõ, log có correlation ID và report liên kết trực tiếp với ca thất bại giúp giảm time to diagnosis. Đây là cách rút ngắn thời gian phản hồi hữu ích mà không nhất thiết giảm thời gian thực thi.

### 14.6. Quản lý retry

Retry chỉ nên dùng khi có lý do và giới hạn rõ. Ghi lại lần chạy đầu, số lần retry và kết quả từng attempt. Với thao tác có tác dụng phụ, cần idempotency hoặc dữ liệu riêng để tránh tạo giao dịch trùng.

## 15. Cải thiện độ tin cậy của kết quả

Để tăng độ tin cậy, nhóm cần xử lý cả thiết kế test, môi trường và quy trình phản hồi.

- Xác định test oracle từ yêu cầu, quy tắc nghiệp vụ hoặc nguồn độc lập.
- Tạo dữ liệu có thể tái tạo và cô lập giữa các lần chạy.
- Kiểm soát đồng hồ, timezone, random seed và dependency biến động.
- Loại bỏ phụ thuộc thứ tự giữa các ca.
- Thay sleep cố định bằng chờ điều kiện có timeout.
- Phân loại flaky test và theo dõi thời gian xử lý.
- Bổ sung assertion cho kết quả nghiệp vụ và bất biến quan trọng.
- Review test để tìm assertion yếu, test bị skip hoặc dữ liệu không đại diện.
- Dùng mutation testing hoặc fault injection phù hợp để đánh giá độ nhạy.
- Bảo đảm báo cáo gắn đúng build, commit, cấu hình và lần chạy.
- Rà soát test suite khi yêu cầu hoặc kiến trúc thay đổi.

Không nên tăng độ tin cậy bằng cách loại bỏ mọi ca từng thất bại. Cần phân biệt lỗi do test với lỗi thật của sản phẩm và giữ lại các kiểm tra có giá trị sau khi đã sửa nguyên nhân.

## 16. Ví dụ xuyên suốt: đo pipeline của một dịch vụ đặt hàng

Giả sử pipeline pull request có unit test, API test và integration test. Nhóm muốn người phát triển nhận phản hồi trong thời gian hợp lý và giảm cảnh báo giả.

Sau khi thu thập telemetry, nhóm thấy:

| Giai đoạn | Median | P95 | Nhận định |
|---|---:|---:|---|
| Queue | 1 phút | 9 phút | Một số giờ cao điểm thiếu runner |
| Setup | 3 phút | 5 phút | Tương đối ổn định |
| Unit test | 2 phút | 3 phút | Nhanh và ổn định |
| API test | 4 phút | 8 phút | Một dependency sandbox có độ trễ biến động |
| Integration test | 10 phút | 24 phút | Có tranh chấp dữ liệu khi chạy song song |
| Publish result | 20 giây | 50 giây | Không phải nút thắt chính |

Nhóm cũng thấy 4% lần chạy integration test fail ban đầu nhưng pass khi retry. Điều tra cho thấy một số ca dùng chung tài khoản và đơn hàng. Nhóm quyết định:

1. Tạo dữ liệu riêng theo `testRunId` cho mỗi worker.
2. Giới hạn số worker song song theo năng lực database.
3. Bổ sung timeout và telemetry cho sandbox.
4. Mở rộng runner trong khung giờ có queue time cao.
5. Giữ lại kết quả attempt đầu và phân loại retry recovery.
6. Bổ sung assertion kiểm tra giao dịch chỉ được ghi nhận một lần.

Sau cải tiến, nhóm đo lại cùng định nghĩa và cùng loại job. Nếu P95 giảm nhưng flaky rate tăng, cải tiến chưa đạt mục tiêu tổng thể. Nếu queue time giảm và kết quả ổn định hơn, nhóm có bằng chứng rằng cả tốc độ lẫn độ tin cậy đã cải thiện.

## 17. Tránh những cách đo gây hiểu lầm

- **Chỉ dùng trung bình:** Che khuất các lần chạy rất chậm ở đuôi phân phối.
- **Chỉ đo execution time:** Bỏ qua queue, setup, xử lý report và notification.
- **Chỉ nhìn tỷ lệ pass:** Không phản ánh test yếu, test bị skip hoặc false negative.
- **Coi retry pass là thành công:** Che giấu flaky test và mất bằng chứng lần fail đầu.
- **Gộp mọi loại test:** Làm số liệu khó diễn giải vì mục tiêu và thời gian khác nhau.
- **So sánh các kỳ với định nghĩa khác nhau:** Tạo xu hướng giả.
- **Đếm lỗi mà không phân loại:** Trộn lỗi sản phẩm, môi trường, dữ liệu và test.
- **Tối ưu thời gian bằng cách bỏ kiểm tra quan trọng:** Giảm thời gian nhưng làm yếu bằng chứng.
- **Đặt SLO không dựa trên dữ liệu:** Tạo áp lực chạy nhanh hoặc khuyến khích bỏ qua kiểm thử.
- **Không lưu ngữ cảnh lần chạy:** Không thể tái hiện hoặc giải thích kết quả.
- **Dùng tỷ lệ flaky với mẫu quá nhỏ:** Một vài lần chạy không đủ kết luận về độ ổn định lâu dài.
- **Đánh đồng mutation score với chất lượng toàn diện:** Mutation testing chỉ là một góc nhìn về độ nhạy của test suite.

## 18. Checklist đo lường và cải thiện

Trước khi dùng số liệu để thay đổi chiến lược kiểm thử, nhóm có thể rà soát:

- [ ] Đã định nghĩa điểm bắt đầu và kết thúc của feedback time.
- [ ] Queue, setup, execution, result processing và notification được đo riêng.
- [ ] Chỉ số được phân đoạn theo loại test, môi trường và runner phù hợp.
- [ ] Median và percentile được theo dõi cùng số lượng mẫu.
- [ ] Trạng thái pass, fail, blocked, skipped, cancelled và retry được phân biệt.
- [ ] Có định nghĩa và quy trình xác định flaky test.
- [ ] Lần fail đầu tiên được giữ lại khi có retry.
- [ ] False positive và nguy cơ false negative được xem xét bằng bằng chứng phù hợp.
- [ ] Test result gắn với build, commit, dữ liệu, cấu hình và môi trường.
- [ ] Có thể tái hiện hoặc điều tra lỗi từ thông tin đã lưu.
- [ ] Oracle và assertion được review theo yêu cầu và rủi ro.
- [ ] SLO phản hồi dựa trên dữ liệu nền và nhu cầu thực tế.
- [ ] Cải tiến thời gian không làm mất kiểm tra quan trọng.
- [ ] Các chỉ số được rà soát định kỳ và định nghĩa thay đổi được ghi nhận.

Đo thời gian có phản hồi và độ tin cậy của kết quả giúp nhóm hiểu liệu kiểm thử đang hỗ trợ phát triển đúng lúc và có thể tin cậy đến đâu. Khi phân tách các giai đoạn thời gian, theo dõi flaky test, kiểm tra false positive/negative và lưu đủ ngữ cảnh lần chạy, nhóm có thể cải thiện tốc độ mà vẫn giữ chất lượng bằng chứng cho quyết định kỹ thuật và phát hành.
