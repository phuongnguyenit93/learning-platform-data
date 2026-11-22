# Theo dõi tỷ lệ thiếu ổn định và chi phí chạy lại

Một bộ kiểm thử có thể xanh trong lần chạy này nhưng đỏ ở lần chạy tiếp theo dù mã nguồn và cấu hình không thay đổi. Những lần kết quả thay đổi trong cùng điều kiện làm giảm niềm tin vào pipeline, khiến kỹ sư phải chạy lại để xác nhận, trì hoãn phản hồi và làm tăng chi phí hạ tầng lẫn công sức điều tra. Nếu nhóm chỉ nhìn tỷ lệ pass cuối cùng sau khi retry, vấn đề có thể bị che khuất và chất lượng tín hiệu kiểm thử ngày càng khó đánh giá.

Theo dõi tỷ lệ thiếu ổn định (flakiness) và chi phí chạy lại giúp nhóm đo mức độ đáng tin của bộ test, nhận diện nơi phát sinh kết quả không nhất quán và lượng hóa tác động của việc chạy thêm. Việc đo cần phân biệt lỗi sản phẩm, lỗi test, lỗi môi trường và lỗi phụ thuộc bên ngoài. Một lần chạy lại thành công chỉ là tín hiệu cần điều tra; nó chưa chứng minh lỗi ban đầu là false positive.

Trong chiến lược đo lường kiểm thử, các chỉ số này nên được theo dõi theo test, suite, commit, môi trường và thời gian. Kết quả cần phản ánh cả lần chạy đầu lẫn các lần chạy lại, để nhóm cải thiện độ ổn định mà vẫn giữ được khả năng phát hiện lỗi thật.

## 1. Hiểu tỷ lệ thiếu ổn định của test

Một test được xem là thiếu ổn định (flaky test) khi cùng một phiên bản mã, dữ liệu và điều kiện môi trường có thể cho kết quả khác nhau giữa các lần thực thi, mà không có thay đổi hợp lệ giải thích sự khác biệt đó. Ví dụ, một test có lúc pass, lúc fail vì phụ thuộc vào thời gian, thứ tự chạy, trạng thái dùng chung, lịch thực thi thread hoặc dịch vụ bên ngoài.

Một lần fail rồi pass khi chạy lại là dấu hiệu nghi ngờ, nhưng chưa đủ để kết luận. Có thể lần đầu gặp sự cố hạ tầng; cũng có thể ứng dụng thực sự có lỗi race condition chỉ xuất hiện không thường xuyên. Cần xem log, trace, trạng thái môi trường và cách tái hiện trước khi gắn nhãn flaky.

### Dấu hiệu thường gặp

- Test UI đôi khi timeout vì phần tử xuất hiện chậm hoặc selector không ổn định.
- Test phụ thuộc vào thời gian thực thi hoặc dùng sleep cố định.
- Nhiều test dùng chung tài khoản, bản ghi hoặc tài nguyên và làm thay đổi trạng thái của nhau.
- Test chạy song song nhưng giả định thứ tự hoặc trạng thái toàn cục.
- Test phụ thuộc vào dữ liệu ngẫu nhiên nhưng không lưu seed để tái hiện.
- Test gọi dịch vụ ngoài có quota, độ trễ hoặc thời gian khả dụng không ổn định.
- Test kiểm tra eventual consistency quá sớm hoặc dùng ngưỡng timeout không phù hợp.
- Runner thiếu CPU/bộ nhớ hoặc có tải nền biến động.
- Đồng hồ hệ thống, múi giờ hoặc lịch chạy ảnh hưởng đến kết quả.

### Phân biệt flaky test với các loại thất bại khác

| Loại kết quả | Đặc điểm | Cách xử lý ban đầu |
|---|---|---|
| Lỗi xác định (deterministic failure) | Cùng điều kiện thường tái hiện cùng một lỗi | Điều tra sản phẩm hoặc test theo stack trace và bằng chứng |
| Test thiếu ổn định | Kết quả thay đổi giữa các lần chạy tương đương | Tái hiện có kiểm soát và tìm nguồn không xác định |
| Lỗi môi trường | Runner, mạng, database hoặc dịch vụ phụ thuộc không đáp ứng | Phân loại sự cố hạ tầng và kiểm tra tác động đến các test khác |
| Lỗi dữ liệu | Fixture thiếu, trạng thái dùng chung hoặc dữ liệu không đúng kỳ vọng | Kiểm tra setup, cô lập và cleanup dữ liệu |
| Lỗi phụ thuộc bên ngoài | API sandbox, quota hoặc dịch vụ đối tác gián đoạn | Ghi nhận phụ thuộc và đánh giá khả năng mô phỏng hoặc retry an toàn |

Các nhóm có thể chồng lấn. Ví dụ, test thiếu ổn định có thể bắt nguồn từ một race condition của sản phẩm. Khi đó kết quả không nhất quán là vấn đề thật của hệ thống và cần được xử lý như một defect, không chỉ là vấn đề chất lượng test.

## 2. Phân biệt các chỉ số ổn định

Không có một tỷ lệ duy nhất mô tả đầy đủ mức thiếu ổn định. Cần chọn chỉ số phù hợp với câu hỏi và ghi rõ mẫu số, khoảng thời gian, cách lấy mẫu.

### Tỷ lệ test thiếu ổn định

Tỷ lệ test thiếu ổn định theo tập test là phần trăm test riêng biệt được xác nhận có kết quả không nhất quán trong số test có đủ quan sát lặp lại trong kỳ:

\[
Flaky\ Test\ Ratio =
\frac{\text{Số test có kết quả không nhất quán đã xác nhận}}
{\text{Số test có đủ lần chạy so sánh}}
\times 100\%
\]

Mẫu số chỉ gồm test có đủ lần chạy tương đương để đánh giá. Nếu một test chỉ chạy một lần, chưa thể kết luận nó ổn định hay thiếu ổn định. Cần công khai tiêu chí “đủ lần chạy”, chẳng hạn ít nhất hai lần chạy tương đương, hoặc một số lần lặp được quy định trong chương trình đo.

### Tỷ lệ kết quả thay đổi khi chạy lại

Tỷ lệ này đo mức độ các lần chạy lại tạo kết quả khác lần chạy ban đầu:

\[
Retry\ Pass\ Rate =
\frac{\text{Số lần chạy lại chuyển từ fail sang pass}}
{\text{Số lần fail ban đầu được chạy lại hợp lệ}}
\times 100\%
\]

Đây là chỉ số vận hành hữu ích, nhưng không đồng nghĩa với tỷ lệ flaky đã xác nhận. Một lần fail có thể do sự cố môi trường tạm thời hoặc lỗi sản phẩm không ổn định. Cần ghi nhãn “fail-then-pass” hoặc “candidate flaky” cho đến khi điều tra.

### Tỷ lệ chạy lại

\[
Rerun\ Rate =
\frac{\text{Số lần thực thi bổ sung sau lần chạy đầu}}
{\text{Tổng số lần thực thi ban đầu}}
\times 100\%
\]

Tỷ lệ này đo mức độ pipeline phải chạy thêm. Cần định nghĩa rõ một lần chạy lại là một test attempt, một job, một suite hay toàn bộ workflow. Không trộn các cấp độ trong cùng mẫu số.

### Tỷ lệ thất bại lần chạy đầu

\[
Initial\ Failure\ Rate =
\frac{\text{Số lần chạy đầu thất bại}}
{\text{Tổng số lần chạy đầu}}
\times 100\%
\]

Chỉ số này cho thấy tín hiệu thất bại ban đầu của pipeline. Nó cần được báo cáo riêng với tỷ lệ pass sau retry. Nếu chỉ nhìn kết quả cuối sau retry, nhóm có thể thấy pipeline xanh trong khi số lần fail ban đầu đang tăng.

### Ví dụ phân biệt chỉ số

Giả sử trong một tuần:

- Có 1.000 test khác nhau được thực thi.
- 800 test có đủ lần chạy tương đương để đánh giá.
- 40 test có kết quả pass/fail không nhất quán đã được xác nhận.
- Có 200 lần fail ban đầu được retry hợp lệ.
- 60 lần retry chuyển từ fail sang pass.

Khi đó:

- Flaky test ratio = 40 / 800 = 5%.
- Retry pass rate = 60 / 200 = 30%.

Hai tỷ lệ trả lời hai câu hỏi khác nhau. Tỷ lệ đầu cho biết phạm vi test thiếu ổn định trong tập đủ quan sát; tỷ lệ thứ hai cho biết các lần fail được retry thường đổi kết quả đến mức nào. Không thể dùng 30% làm tỷ lệ flaky của toàn bộ suite.

## 3. Xác định đơn vị đo và mẫu số

Trước khi lập dashboard, nhóm cần thống nhất đơn vị đếm. Một test có thể chạy nhiều lần trong một job; một job có thể chạy nhiều suite; một workflow có thể chứa nhiều job trên các môi trường khác nhau.

Các đơn vị thường dùng:

- **Test case:** định danh logic của một test, không thay đổi chỉ vì đổi tên hiển thị.
- **Test attempt:** một lần thực thi test case.
- **Job run:** một lần thực thi một job CI.
- **Suite run:** một lần chạy tập test.
- **Pipeline run:** toàn bộ workflow cho một commit hoặc sự kiện.
- **Rerun event:** hành động yêu cầu chạy lại một test, job, suite hoặc pipeline.

Ví dụ, một test thất bại rồi được retry hai lần tạo ra ba test attempt nhưng chỉ có một test case. Nếu đếm test case thì số lượng là một; nếu đếm attempt thì số lượng là ba. Báo cáo cần ghi rõ đang dùng cách đếm nào.

### Mẫu số phải phản ánh cơ hội quan sát

Một test chỉ chạy một lần không thể được xem là đã chứng minh ổn định. Khi tính flaky test ratio, nên giới hạn mẫu số ở các test có đủ lần chạy so sánh theo tiêu chí đã công bố.

Nếu chỉ retry test sau khi fail, mẫu quan sát bị thiên lệch về các trường hợp có vấn đề. Để ước lượng ổn định của toàn bộ suite, có thể chọn một tập test đại diện chạy lặp lại theo lịch, trên cùng build và môi trường đã kiểm soát. Ghi riêng số test chưa đủ quan sát.

### Cửa sổ thời gian

Có thể theo dõi chỉ số theo:

- Ngày để phát hiện sự cố mới.
- Tuần để đánh giá xu hướng.
- Tháng hoặc chu kỳ phát hành để theo dõi cải thiện.
- Một commit hoặc pull request để điều tra thay đổi cụ thể.

Không nên so sánh hai tỷ lệ nếu cửa sổ thời gian, tập test, môi trường hoặc cách lấy mẫu khác nhau mà không giải thích. Khi suite tăng gấp đôi, tỷ lệ có thể thay đổi chỉ vì mẫu số và cơ cấu test thay đổi.

## 4. Thu thập dữ liệu cho từng lần chạy

Đo lường đáng tin cậy cần dữ liệu chi tiết đến từng test attempt. Chỉ lưu tổng số pass/fail của một workflow sẽ không đủ để xác định test nào gây chạy lại và vì sao.

### Trường dữ liệu khuyến nghị

| Trường | Mục đích |
|---|---|
| test_id | Định danh ổn định của test case |
| suite | Nhóm hoặc tầng kiểm thử |
| run_id và job_id | Liên kết với lần chạy CI |
| attempt | Số thứ tự lần thực thi |
| commit_sha | Phiên bản mã đang kiểm tra |
| branch hoặc pull_request | Ngữ cảnh thay đổi |
| environment | Môi trường, dịch vụ và cấu hình |
| runner_type | Loại runner, OS và tài nguyên |
| started_at và duration | Thời điểm và thời gian thực thi |
| result | Pass, fail, timeout, skipped hoặc error |
| retry_reason | Lý do thực hiện lần chạy lại |
| seed | Seed ngẫu nhiên nếu test dùng dữ liệu ngẫu nhiên |
| artifact_ref | Link log, screenshot, trace hoặc report |
| failure_category | Test, product, infra, data hoặc external dependency |
| flaky_status | Chưa phân loại, nghi ngờ, xác nhận hoặc đã khắc phục |

Nên lưu cả kết quả lần chạy đầu và tất cả lần chạy lại. Nếu chỉ giữ kết quả cuối, không thể tái dựng lịch sử fail-then-pass.

### Giữ định danh ổn định

Tên test có thể thay đổi khi refactor. Hãy dùng ID ổn định hoặc quy tắc ánh xạ để tránh một test bị tính thành hai test khác nhau sau khi đổi tên. Nếu test được tách hoặc gộp, ghi lại quan hệ giữa ID cũ và mới để phân tích xu hướng không bị đứt đoạn.

### Bảo vệ dữ liệu

Log, screenshot và trace có thể chứa token, dữ liệu cá nhân hoặc thông tin khách hàng. Chỉ thu thập phần cần thiết, che dữ liệu nhạy cảm, giới hạn quyền truy cập và đặt thời hạn lưu trữ phù hợp. Không đưa secret hoặc dữ liệu production vào nhãn, dashboard hay artifact.

## 5. Thiết kế phép đo lặp lại có kiểm soát

Muốn kết luận một test thiếu ổn định, cần so sánh những lần chạy có điều kiện tương đương. Nếu commit, dữ liệu, phiên bản dịch vụ hoặc môi trường thay đổi, kết quả khác nhau có thể là hệ quả hợp lệ của thay đổi đó.

### Giữ các điều kiện so sánh

Khi thực hiện phép chạy lặp để chẩn đoán, cố gắng giữ:

- Cùng commit và artifact build.
- Cùng phiên bản test runner và dependency.
- Cùng cấu hình môi trường.
- Cùng dữ liệu hoặc seed có thể tái hiện.
- Cùng dịch vụ phụ thuộc hoặc stub đã định nghĩa.
- Cùng cách khởi tạo và cleanup.
- Cùng giới hạn tài nguyên khi mục tiêu là đo độ ổn định.

Nếu cần thay đổi một điều kiện để tìm nguyên nhân, ghi rõ đó là thí nghiệm chẩn đoán, không gộp kết quả với mẫu đo chuẩn.

### Chạy lặp có mục tiêu

Không cần chạy lại toàn bộ suite hàng chục lần. Có thể:

1. Chọn test có lịch sử fail-then-pass.
2. Chạy lặp test đó trên cùng commit và môi trường.
3. Ghi từng attempt và seed.
4. So sánh log, thời gian, thứ tự và tài nguyên.
5. Tăng số lần lặp chỉ khi cần đủ bằng chứng.
6. Dừng khi tìm được nguyên nhân hoặc đạt giới hạn chẩn đoán đã đặt.

Đối với suite lớn, chạy một mẫu test đại diện theo lịch có thể giúp phát hiện test thiếu ổn định ngay cả khi lần chạy đầu không thất bại.

### Cẩn trọng với chạy song song

Chạy đồng thời có thể làm lộ race condition, nhưng cũng có thể gây nhiễu do runner quá tải hoặc tài nguyên dùng chung. Hãy phân biệt hai mục tiêu:

- Đo độ ổn định trong cấu hình pipeline thực tế, bao gồm mức song song thực tế.
- Chẩn đoán nguyên nhân bằng cách giảm song song hoặc cô lập tài nguyên.

Nếu test chỉ fail khi chạy song song, đó có thể là lỗi cô lập test hoặc lỗi đồng thời của sản phẩm. Không nên loại bỏ điều kiện song song khỏi phép đo vận hành chỉ để làm tỷ lệ đẹp hơn.

## 6. Tìm nguyên nhân gốc của test thiếu ổn định

Tỷ lệ chỉ cho biết vấn đề ở mức nào; điều tra nguyên nhân mới giúp giảm nó. Nên phân loại theo nhóm để ưu tiên biện pháp sửa.

### Thời gian và đồng bộ

Test dùng sleep(2) để chờ phần tử hoặc sự kiện thường không ổn định khi môi trường chậm hơn dự kiến. Dùng điều kiện chờ có giới hạn, polling trạng thái thực tế và timeout phù hợp. Với eventual consistency, xác định điều kiện hoàn tất nghiệp vụ thay vì giả định một khoảng thời gian cố định.

### Trạng thái và dữ liệu dùng chung

Test có thể cùng sửa một tài khoản, đơn hàng hoặc bảng dữ liệu. Kết quả phụ thuộc thứ tự và mức song song. Tạo dữ liệu riêng theo test run, dùng namespace hoặc tenant riêng, và cleanup bằng cơ chế có thể lặp lại an toàn.

### Ngẫu nhiên và phụ thuộc thứ tự

Nếu test sinh dữ liệu ngẫu nhiên, lưu seed và input để tái hiện. Nếu test chỉ pass sau khi test khác chạy trước, cần loại bỏ phụ thuộc thứ tự bằng setup riêng và kiểm tra khả năng chạy độc lập.

### Giao diện và trình duyệt

Selector dựa vào vị trí hoặc cấu trúc DOM dễ thay đổi. Ưu tiên locator theo vai trò, nhãn hoặc thuộc tính ổn định. Chờ trạng thái giao diện có ý nghĩa, tránh click trước khi overlay biến mất và thu thập screenshot/trace khi thất bại.

### Runner và hạ tầng

CPU, bộ nhớ, disk, mạng hoặc container dùng chung có thể biến động. So sánh test fail với metric runner, tải hệ thống, thời gian queue và lỗi mạng. Nếu nhiều test độc lập cùng thất bại trên một runner hoặc vùng triển khai, nghi ngờ hạ tầng trước khi sửa từng test.

### Dịch vụ bên ngoài

Sandbox hoặc API đối tác có thể giới hạn quota, thay đổi dữ liệu hoặc có thời gian bảo trì. Ghi nhận mã phản hồi, latency và tình trạng dịch vụ. Dùng stub cho logic không cần xác minh tích hợp thật, nhưng vẫn duy trì test tích hợp có mục tiêu để kiểm tra hợp đồng và đường đi thật.

### Lỗi không xác định của sản phẩm

Một race condition, cache inconsistency hoặc lỗi xử lý retry có thể chỉ xuất hiện dưới tải hoặc một lịch thực thi nhất định. Nếu test đang phơi bày một hành vi người dùng có thể gặp, không gắn nhãn flaky để bỏ qua. Tạo defect cho sản phẩm, mô tả điều kiện kích hoạt và giữ bằng chứng tái hiện.

## 7. Phân loại và quản lý trạng thái flaky

Một quy trình phân loại giúp mọi người dùng cùng một ngôn ngữ và ngăn việc gắn nhãn tùy tiện.

Có thể dùng các trạng thái:

- **Unclassified:** mới có dấu hiệu không nhất quán, chưa điều tra.
- **Suspected flaky:** có lần chạy thay đổi kết quả trong điều kiện gần tương đương.
- **Confirmed flaky:** đã xác nhận nguồn không xác định trong test hoặc môi trường thực thi.
- **Product intermittent defect:** lỗi không thường xuyên thuộc hành vi sản phẩm.
- **Infrastructure issue:** lỗi do runner, mạng hoặc dịch vụ nền tảng.
- **Fixed, awaiting observation:** đã sửa và đang theo dõi các lần chạy tiếp theo.
- **Stable:** đạt tiêu chí ổn định trong cửa sổ quan sát đã định.

### Tiêu chí xác nhận

Trước khi xác nhận flaky, nên xem xét:

1. Commit và artifact có giống nhau không?
2. Môi trường và dữ liệu có tương đương không?
3. Lỗi có thể tái hiện bằng cùng seed không?
4. Test có phụ thuộc thời gian, thứ tự hoặc trạng thái dùng chung không?
5. Có lỗi hạ tầng hoặc dịch vụ ngoài cùng thời điểm không?
6. Hành vi fail có phải lỗi thật mà người dùng có thể gặp không?
7. Có log hoặc trace đủ để giải thích khác biệt không?

Không nhất thiết phải có một số lần chạy cố định cho mọi test. Test có rủi ro cao hoặc tần suất sử dụng lớn có thể cần nhiều bằng chứng hơn. Hãy quy định ngưỡng tối thiểu theo loại test và mức ảnh hưởng.

### Quarantine có kiểm soát

Nếu một test liên tục làm pipeline nhiễu, nhóm có thể tạm thời đưa nó vào quarantine để các test khác tiếp tục cung cấp tín hiệu. Tuy nhiên:

- Test vẫn phải được thực thi hoặc theo dõi theo lịch phù hợp.
- Quarantine phải có owner và ticket sửa.
- Ghi lý do, ngày bắt đầu và ngày hết hạn.
- Không tính test quarantined là pass.
- Không loại bỏ kiểm tra có rủi ro cao mà không có quyết định phù hợp.
- Đặt điều kiện để đưa test trở lại gate chính.
- Báo cáo số lượng và tuổi của test đang quarantine.

Quarantine là biện pháp vận hành tạm thời, không phải cách đóng vấn đề.

## 8. Thiết kế chính sách retry và rerun

Retry có thể giúp thu thập thêm bằng chứng, nhưng chính sách thiếu giới hạn sẽ che giấu lỗi và làm chi phí tăng. Cần phân biệt retry tự động trong một job, rerun test đơn lẻ, rerun job và rerun toàn bộ pipeline.

### Chỉ retry có giới hạn

Một chính sách có thể cho phép một lần retry đối với test thất bại để thu thập thêm dữ liệu. Với một số loại lỗi hạ tầng đã được nhận diện, có thể có quy tắc retry riêng. Không nên retry vô hạn hoặc retry mọi loại lỗi như nhau.

Mỗi lần retry cần ghi:

- Lý do retry.
- Số attempt.
- Kết quả lần đầu và kết quả retry.
- Thời gian thực thi và queue time.
- Điều kiện môi trường.
- Quyết định cuối cùng của gate.

### Không biến fail-then-pass thành pass âm thầm

Nếu lần đầu fail nhưng retry pass, kết quả nên được thể hiện là flaky-recovered, unstable hoặc trạng thái tương đương theo quy ước. Báo cáo vẫn cần giữ lần fail đầu tiên. Với test trọng yếu, có thể tiếp tục chặn pipeline cho đến khi điều tra hoặc có quyết định ngoại lệ.

Nếu lần retry cũng fail cùng lỗi, khả năng lỗi xác định cao hơn, nhưng vẫn cần phân loại. Nếu nhiều test cùng fail do runner mất kết nối, đây có thể là lỗi hạ tầng.

### Chọn cấp độ chạy lại

- **Rerun test đơn lẻ:** phù hợp khi cần chẩn đoán một test và setup có thể tái lập.
- **Rerun nhóm test:** phù hợp khi lỗi có thể liên quan đến trạng thái chung hoặc tương tác trong suite.
- **Rerun job:** phù hợp khi cần tái tạo toàn bộ điều kiện của runner/job.
- **Rerun pipeline:** chỉ nên dùng khi phụ thuộc giữa các job hoặc trạng thái workflow khiến chạy riêng lẻ không đủ.

Rerun càng rộng thì chi phí càng cao và càng khó xác định nguyên nhân nếu môi trường thay đổi. Chọn phạm vi nhỏ nhất vẫn giữ được điều kiện cần kiểm tra.

### Phân biệt retry lỗi tạm thời và retry lỗi xác định

Có thể retry lỗi kết nối hoặc runner khi có bằng chứng đó là sự cố tạm thời và thao tác an toàn. Không nên tự động retry các lỗi assertion nghiệp vụ, lỗi dữ liệu hoặc lỗi bảo mật mà không giữ trạng thái thất bại ban đầu. Retry một giao dịch có tác dụng phụ cũng cần idempotency hoặc cơ chế dọn dẹp để không tạo dữ liệu trùng.

## 9. Đo thời gian và chi phí chạy lại

Chi phí chạy lại gồm phần tài nguyên thực thi bổ sung, thời gian pipeline bị kéo dài và công sức con người để xác minh, điều tra, sửa chữa. Cần đo riêng các thành phần để tránh nhầm chi phí runner với thời gian chờ hoặc thời gian kỹ sư.

### Thời gian thực thi bổ sung

\[
T_{extra} = \sum_{i=1}^{m} Duration(Rerun_i)
\]

Đây là tổng thời gian thực thi bổ sung của các lần chạy lại trong kỳ. Nếu các job chạy song song, tổng runner time có thể lớn hơn thời gian lịch thực tế.

### Độ trễ pipeline do chạy lại

\[
T_{delay} = \sum_{j=1}^{n} (QueueWait_j + Execution_j)
\]

Đây là tổng thời gian chờ và thực thi của các lần chạy lại. Khi đo thời gian chậm của một pipeline cụ thể, cần tính phần chạy lại nằm trên đường găng; không cộng máy móc toàn bộ thời gian song song để suy ra độ trễ lịch.

### Chi phí runner

\[
C_{runner} = \sum_{i=1}^{m} ExtraRunnerMinutes_i \times UnitCostPerMinute_i
\]

Nếu runner tự quản lý, đơn giá có thể được ước lượng từ chi phí máy, lưu trữ, điện năng và vận hành theo quy tắc nội bộ. Nếu dùng runner theo phút, lấy đơn giá theo loại runner và thời điểm tính phí.

### Chi phí nhân lực

\[
C_{labor} = \sum_{r=1}^{p} InvestigationHours_r \times LoadedHourlyRate_r
\]

Trong đó LoadedHourlyRate là chi phí giờ lao động theo cách tính của tổ chức, có thể bao gồm chi phí nhân sự và chi phí liên quan. Nếu tổ chức không quy đổi giờ lao động ra tiền, hãy báo số giờ điều tra và sửa chữa riêng.

### Tổng chi phí trực tiếp

\[
C_{total} = C_{runner} + C_{labor} + C_{service} + C_{other}
\]

C_service có thể gồm quota sandbox, API đối tác hoặc dịch vụ tính phí theo request. C_other gồm chi phí trực tiếp khác có thể quy về hoạt động chạy lại. Không đưa thời gian chậm giao hàng vào tổng chi phí tiền tệ nếu chưa có phương pháp định giá rõ; hãy báo nó thành chỉ số tác động riêng.

### Chi phí cơ hội

Rerun có thể chiếm runner và thời gian kỹ sư đáng lẽ dùng cho công việc khác. Theo dõi số giờ bị tiêu hao và số pipeline bị chậm giúp thể hiện chi phí cơ hội. Nếu muốn quy đổi thành tiền, cần công bố giả định và tránh cộng trùng với chi phí nhân lực đã tính.

## 10. Xây dựng dashboard và báo cáo xu hướng

Dashboard nên trả lời được test nào gây mất ổn định, xu hướng thay đổi ra sao và chi phí đang phát sinh ở đâu. Không chỉ hiển thị một tỷ lệ tổng toàn hệ thống.

### Các chỉ số cốt lõi

| Chỉ số | Câu hỏi được trả lời |
|---|---|
| Flaky test ratio | Bao nhiêu test đủ dữ liệu có kết quả không nhất quán? |
| Retry pass rate | Bao nhiêu lần fail ban đầu chuyển sang pass sau retry? |
| Initial failure rate | Bao nhiêu lần chạy đầu thất bại? |
| Rerun rate | Tần suất cần chạy thêm là bao nhiêu? |
| Extra runner minutes | Bao nhiêu phút runner được tiêu thụ thêm? |
| Pipeline delay | Việc chạy lại kéo dài thời gian phản hồi bao nhiêu? |
| Investigation hours | Nhóm mất bao nhiêu giờ điều tra và sửa test? |
| Quarantined test count | Có bao nhiêu test đang bị quarantine và đã tồn tại bao lâu? |
| Reopen rate | Bao nhiêu test đã được đánh dấu ổn định nhưng lại tái phát? |

### Phân rã theo chiều

Nên có thể lọc theo:

- Test ID, suite và tầng kiểm thử.
- Nhóm sở hữu và repository.
- Branch, commit hoặc pull request.
- OS, browser, runtime, database và loại runner.
- Thời gian trong ngày hoặc lịch chạy.
- Loại lỗi: test, product, infra, data hoặc external dependency.
- Trạng thái quarantine và tuổi của vấn đề.

Tỷ lệ tổng có thể che khuất một nhóm nhỏ test gây phần lớn rerun. Bảng xếp hạng theo số lần chạy lại, runner minutes và giờ điều tra giúp nhóm ưu tiên sửa những test có tác động lớn.

### Theo dõi xu hướng thay vì một điểm dữ liệu

Dùng cửa sổ trượt theo tuần hoặc theo số lần chạy để tránh phản ứng quá mức với một ngày bất thường. Ghi lại thay đổi về số test, tần suất chạy và chính sách retry. Khi suite tăng hoặc chuyển runner, cần đánh dấu thay đổi để người xem hiểu sự khác biệt trong biểu đồ.

### Ví dụ cấu trúc dashboard

Một dashboard vận hành có thể gồm:

1. Flaky test ratio theo tuần.
2. Retry pass rate và initial failure rate theo suite.
3. Top test theo số rerun và runner minutes.
4. Chi phí runner và giờ điều tra theo nhóm.
5. Test quarantine theo owner và tuổi.
6. Phân loại nguyên nhân theo môi trường.
7. Danh sách test có xu hướng xấu đi sau một commit hoặc thay đổi runner.

Dashboard phải cho phép đi từ chỉ số tổng đến từng lần chạy và artifact để điều tra.

## 11. Đặt mục tiêu và ngưỡng cảnh báo

Mục tiêu ổn định cần phù hợp với vai trò của suite. Một suite chạy trong pull request có thể cần tín hiệu tin cậy cao và thời gian phản hồi ngắn; một bộ test thăm dò ban đêm có thể chấp nhận mức biến động khác nếu được phân loại rõ.

Không nên chọn một ngưỡng tùy tiện như “flaky rate dưới 1%” cho mọi dự án. Hãy:

1. Đo baseline trong một khoảng thời gian đủ đại diện.
2. Tách test trọng yếu khỏi test ít rủi ro.
3. Xác định mức rerun và chi phí có thể chấp nhận.
4. Đặt mục tiêu cải thiện theo từng giai đoạn.
5. Định nghĩa hành động khi vượt ngưỡng.
6. Rà soát lại sau khi thay đổi suite hoặc hạ tầng.

### Ví dụ ngưỡng vận hành

Tổ chức có thể đặt quy tắc nội bộ như:

- Test trọng yếu không được có trạng thái flaky đã xác nhận khi làm gate phát hành.
- Test có nhiều lần fail-then-pass trong một cửa sổ ngắn phải được ưu tiên điều tra.
- Test quarantine phải có owner, ticket và thời hạn.
- Rerun rate vượt baseline trong nhiều kỳ liên tiếp kích hoạt rà soát runner và test.
- Chi phí runner bổ sung vượt ngân sách suite phải có kế hoạch khắc phục.

Đây là ví dụ về chính sách, không phải ngưỡng chuẩn áp dụng cho mọi tổ chức. Ngưỡng cần được định nghĩa cùng cách đo, mẫu số và thời gian quan sát.

### Cảnh báo sớm và cảnh báo hành động

- **Cảnh báo sớm:** tỷ lệ retry pass tăng, một test bắt đầu dao động hoặc runner minutes tăng bất thường.
- **Cảnh báo hành động:** test quan trọng mất ổn định, pipeline release bị trì hoãn vượt ngưỡng hoặc chi phí chạy lại vượt giới hạn đã duyệt.

Cảnh báo cần có owner, liên kết đến test và hướng điều tra. Nếu không có hành động rõ ràng, dashboard dễ trở thành nơi xem số liệu mà không cải thiện hệ thống.

## 12. Tối ưu test để giảm rerun

Sau khi phân loại nguyên nhân, chọn biện pháp sửa tương ứng. Không dùng một giải pháp chung cho mọi test.

### Làm test đồng bộ và có điều kiện

- Thay sleep cố định bằng wait theo điều kiện có timeout.
- Chờ trạng thái nghiệp vụ hoàn tất thay vì chỉ chờ HTTP response.
- Dùng polling có giới hạn và thông báo lỗi rõ khi hết thời gian.
- Chọn timeout theo phân bố thời gian thực tế và mục tiêu của test.
- Tránh tăng timeout quá lớn để che lỗi treo hoặc hiệu năng suy giảm.

### Cô lập dữ liệu và tài nguyên

- Tạo fixture riêng cho từng test hoặc test run.
- Dùng transaction, namespace hoặc tenant riêng khi phù hợp.
- Đảm bảo cleanup chạy cả khi test fail.
- Tránh phụ thuộc vào thứ tự thực thi.
- Dùng idempotency cho thao tác có thể được retry.
- Không dùng tài khoản hoặc bản ghi dùng chung nếu test có thể thay đổi trạng thái.

### Kiểm soát ngẫu nhiên

- Lưu seed và dữ liệu đầu vào.
- Dùng seed ổn định cho test hồi quy.
- Tách test fuzz/property-based có đầu vào ngẫu nhiên khỏi gate ổn định nếu cần, nhưng vẫn lưu counterexample và chạy lại để tái hiện.
- Không loại bỏ hoàn toàn ngẫu nhiên nếu mục tiêu là tìm lỗi; hãy quản lý nó như một chế độ kiểm thử riêng.

### Cải thiện selector và quan sát UI

- Ưu tiên locator ổn định theo role, label hoặc test ID.
- Chờ overlay, animation và request quan trọng hoàn tất theo điều kiện.
- Thu thập screenshot, DOM snapshot và trace khi fail.
- Không dùng vị trí pixel hoặc thứ tự phần tử nếu không cần thiết.
- Tránh chia sẻ trạng thái browser giữa các test độc lập.

### Ổn định hạ tầng và runner

- Cấp phát tài nguyên phù hợp với suite.
- Theo dõi CPU, memory, disk, network và queue time.
- Chuẩn hóa image và phiên bản công cụ.
- Cô lập runner khi test cần trạng thái riêng.
- Giới hạn song song nếu tài nguyên dùng chung bị quá tải.
- Phân biệt lỗi runner với lỗi ứng dụng qua telemetry và mã lỗi.

## 13. Quản lý quarantine và nợ kỹ thuật của test

Test thiếu ổn định thường tạo ra nợ kỹ thuật: nhóm biết test không đáng tin nhưng trì hoãn sửa vì vẫn có thể retry. Nợ này cần được quản lý như công việc có owner và thời hạn.

Một bản ghi quarantine nên có:

| Trường | Nội dung |
|---|---|
| Test ID | Định danh test |
| Lý do | Bằng chứng về kết quả không nhất quán |
| Nguyên nhân nghi ngờ | Timing, data, infra, dependency hoặc product |
| Tác động | Pipeline, rủi ro bị che khuất và tần suất chạy |
| Owner | Người chịu trách nhiệm sửa |
| Ticket | Công việc theo dõi |
| Ngày bắt đầu | Khi test được quarantine |
| Hạn xử lý | Thời điểm phải xem xét lại |
| Điều kiện gỡ | Tiêu chí ổn định và số lần quan sát cần thiết |

### Định nghĩa điều kiện gỡ quarantine

Không nên gỡ chỉ vì test pass một lần. Có thể yêu cầu:

- Nguyên nhân đã được xử lý hoặc có giải thích được chấp nhận.
- Test chạy lặp lại trong điều kiện đại diện mà không tái phát.
- Test chạy độc lập và trong suite song song nếu đó là chế độ thực tế.
- Log và assertion đủ rõ để phân biệt lỗi.
- Owner cập nhật ticket và bằng chứng.
- Test được đưa lại vào gate theo quy trình.

### Theo dõi tuổi và mức độ ưu tiên

Một test quarantine lâu ngày có thể làm giảm phạm vi kiểm thử mà nhóm không còn nhận ra. Theo dõi tuổi quarantine, số lần chạy, mức độ rủi ro và tổng chi phí rerun liên quan. Nếu số test quarantine tăng, đó là dấu hiệu cần cải thiện nền tảng test hoặc quy trình bảo trì.

## 14. Đánh giá tác động đến thời gian phản hồi CI/CD

Rerun làm tăng thời gian phản hồi cho developer. Cần phân biệt tổng thời gian thực thi với thời gian từ khi push code đến khi có kết quả đáng tin cậy.

### Các thành phần thời gian

- Thời gian chờ runner.
- Thời gian setup môi trường.
- Thời gian chạy lần đầu.
- Thời gian chạy lại.
- Thời gian thu thập artifact.
- Thời gian điều tra thủ công.
- Thời gian chờ quyết định hoặc phê duyệt.

Một pipeline có runner time thấp nhưng queue time cao vẫn làm developer chờ lâu. Ngược lại, nhiều job chạy song song có thể có tổng runner minutes cao nhưng wall-clock delay thấp. Báo cáo nên hiển thị cả hai.

### Tác động của retry lên feedback loop

Khi pipeline tự động retry trước khi trả kết quả, developer có thể nhận feedback muộn hơn và không biết lần chạy đầu đã fail. Khi pipeline trả kết quả fail ngay, developer có thể tự rerun và mất thêm thời gian. Cần chọn chính sách dựa trên mục tiêu: phát hiện lỗi nhanh, giảm nhiễu, hay thu thập bằng chứng chẩn đoán.

Một cách cân bằng là báo kết quả lần đầu ngay, tiếp tục retry có giới hạn trong trạng thái riêng và cập nhật kết quả cuối cùng mà không xóa lịch sử. Developer nhìn thấy cả lỗi ban đầu và trạng thái xác minh sau đó.

### Xác định suite nào cần tối ưu trước

Ưu tiên suite có một hoặc nhiều đặc điểm:

- Chạy ở mọi pull request.
- Có thời gian queue hoặc rerun lớn.
- Chặn merge hoặc release.
- Có nhiều test thiếu ổn định.
- Tốn runner minutes hoặc giờ điều tra đáng kể.
- Kiểm tra luồng rủi ro cao nên không thể đơn giản quarantine.

Sửa một test thường chạy trong mọi pull request có thể mang lại lợi ích lớn hơn sửa nhiều test chỉ chạy hàng tháng.

## 15. Ví dụ thực hành: đo chi phí chạy lại trong một tháng

Giả sử một nhóm theo dõi suite tích hợp trong một tháng và thu thập được:

- 20.000 lần chạy đầu của test.
- 400 lần chạy đầu thất bại.
- 300 lần fail được retry hợp lệ.
- 90 lần retry chuyển từ fail sang pass.
- 1.000 test riêng biệt có đủ quan sát lặp lại.
- 50 test có kết quả không nhất quán đã được xác nhận.
- Các lần chạy lại tiêu thụ thêm 450 runner minutes.
- Thời gian queue của các lần chạy lại cộng dồn là 1.200 phút.
- Nhóm dành 18 giờ để điều tra và sửa các test liên quan.

### Tính các chỉ số

Initial failure rate:

\[
400 / 20{,}000 \times 100\% = 2\%
\]

Retry pass rate:

\[
90 / 300 \times 100\% = 30\%
\]

Flaky test ratio trong tập đủ quan sát:

\[
50 / 1{,}000 \times 100\% = 5\%
\]

Rerun rate nếu tính theo số lần retry trên tổng lần chạy đầu:

\[
300 / 20{,}000 \times 100\% = 1.5\%
\]

Các tỷ lệ này cần được ghi đúng tên và mẫu số. 30% là retry pass rate, 5% là tỷ lệ test không nhất quán đã xác nhận trong tập đủ quan sát.

### Tính chi phí trực tiếp

Giả sử runner có đơn giá 0,08 đơn vị tiền cho mỗi phút và chi phí lao động quy đổi là 50 đơn vị tiền mỗi giờ:

\[
C_{runner} = 450 \times 0.08 = 36
\]

\[
C_{labor} = 18 \times 50 = 900
\]

\[
C_{total} = 36 + 900 = 936
\]

Chi phí trực tiếp ước tính là 936 đơn vị tiền, chưa tính chi phí dịch vụ ngoài hoặc chi phí cơ hội do pipeline chậm. Thời gian queue 1.200 phút được báo riêng vì không đồng nghĩa với 1.200 phút runner được tính phí.

### Xác định hành động ưu tiên

Nhóm nên xem top test theo số lần fail-then-pass, runner minutes và giờ điều tra. Nếu một test checkout gây 20% rerun nhưng kiểm tra luồng thanh toán quan trọng, ưu tiên sửa test hoặc điều tra race condition của sản phẩm. Nếu nhiều test cùng timeout trên một loại runner, kiểm tra tài nguyên và tải nền trước khi sửa từng test.

Sau khi sửa, tiếp tục đo cùng định nghĩa trong cửa sổ tương đương. So sánh tỷ lệ, số lần chạy, thành phần suite và cấu hình runner để xác nhận cải thiện có thật.

## 16. Tránh các cách tối ưu làm sai lệch chỉ số

Một số cách làm có thể khiến dashboard đẹp hơn nhưng làm mất khả năng phát hiện lỗi.

- **Retry vô hạn đến khi pass:** che giấu lỗi không ổn định và làm tăng chi phí.
- **Chỉ lưu kết quả cuối:** xóa mất bằng chứng fail ban đầu.
- **Tính test chỉ chạy một lần là ổn định:** không đủ dữ liệu để kết luận.
- **Đổi môi trường giữa các lần retry nhưng vẫn so sánh như tương đương:** làm sai phép đo.
- **Quarantine không thời hạn:** âm thầm giảm phạm vi bảo vệ.
- **Tăng timeout cho mọi test:** có thể che lỗi treo và kéo dài feedback loop.
- **Chạy lại toàn bộ suite cho một test lỗi:** lãng phí tài nguyên nếu không cần setup chung.
- **Gộp lỗi sản phẩm vào flaky test:** bỏ qua defect không thường xuyên.
- **Bỏ qua lỗi hạ tầng trong thống kê:** làm sai lệch đánh giá chất lượng test.
- **So sánh tỷ lệ mà không ghi mẫu số:** tạo kết luận sai khi suite thay đổi.
- **Đặt mục tiêu số đẹp nhưng không gắn hành động:** khuyến khích che giấu trạng thái thay vì sửa nguyên nhân.
- **Tự động bỏ qua assertion sau retry:** làm yếu cổng chất lượng.

Chỉ số cần khuyến khích sửa nguyên nhân, không khuyến khích giảm số liệu bằng cách đổi cách đếm.

## 17. Quy trình vận hành theo dõi và cải thiện

Có thể tổ chức vòng lặp cải thiện theo các bước:

1. **Thu thập:** lưu kết quả từng attempt cùng metadata và artifact.
2. **Phát hiện:** tính chỉ số theo test, suite, môi trường và thời gian.
3. **Phân loại:** xác định test, product, infra, data hoặc external dependency.
4. **Ưu tiên:** xếp theo mức rủi ro, tần suất, chi phí và tác động đến pipeline.
5. **Điều tra:** tái hiện có kiểm soát, so sánh log và tìm nguyên nhân.
6. **Khắc phục:** sửa test, sản phẩm, dữ liệu hoặc hạ tầng.
7. **Xác minh:** chạy lặp theo tiêu chí đã định và đưa test trở lại gate.
8. **Đánh giá:** so sánh xu hướng, chi phí và tỷ lệ tái phát.
9. **Cập nhật:** điều chỉnh chính sách retry, ngưỡng cảnh báo và kế hoạch bảo trì.

### Phân công trách nhiệm

- **Test owner:** điều tra và sửa test, cập nhật trạng thái flaky.
- **Test lead:** quản lý chỉ số, ưu tiên và chính sách retry/quarantine.
- **Developer hoặc service owner:** xử lý lỗi sản phẩm khi có bằng chứng.
- **Platform/DevOps:** điều tra runner, network, tài nguyên và dịch vụ CI.
- **Engineering manager hoặc release owner:** xử lý xung đột nguồn lực và rủi ro phát hành.

Một test có thể liên quan nhiều nhóm. Cần có một owner điều phối chính để tránh ticket bị chuyển qua lại mà không có tiến triển.

## 18. Danh sách kiểm tra thiết kế đo lường flakiness và rerun

**Định nghĩa và dữ liệu**

- Flaky test, retry, rerun và attempt đã được định nghĩa rõ chưa?
- Mỗi tỷ lệ có công thức, mẫu số và cửa sổ thời gian không?
- Kết quả lần đầu và các lần chạy lại có được lưu riêng không?
- Test có ID ổn định và metadata commit, môi trường, runner, seed không?
- Test chưa đủ số lần quan sát có được phân biệt không?

**Phân loại và điều tra**

- Có phân biệt lỗi test, sản phẩm, hạ tầng, dữ liệu và dịch vụ ngoài không?
- Có quy trình tái hiện trong điều kiện tương đương không?
- Có thu thập log, trace, screenshot và metric runner phù hợp không?
- Test có thể chạy độc lập và song song theo điều kiện thực tế không?
- Có owner và ticket cho từng test thiếu ổn định không?

**Retry và quarantine**

- Retry có giới hạn và lý do rõ ràng không?
- Fail-then-pass có được báo riêng thay vì âm thầm chuyển thành pass không?
- Rerun có dùng phạm vi nhỏ nhất cần thiết không?
- Quarantine có owner, hạn xử lý và tiêu chí gỡ không?
- Test trọng yếu có được bảo vệ khỏi việc bỏ qua tùy tiện không?

**Chi phí và cải thiện**

- Runner minutes, queue time, labor hours và chi phí dịch vụ có được tách riêng không?
- Dashboard có phân rã theo test, suite, môi trường và nhóm sở hữu không?
- Có theo dõi xu hướng và test gây chi phí lớn nhất không?
- Mục tiêu có gắn với hành động và trách nhiệm cụ thể không?
- Sau khi sửa, có đo lại trên cửa sổ và điều kiện tương đương không?

## Kết luận

Theo dõi tỷ lệ thiếu ổn định và chi phí chạy lại giúp đánh giá độ tin cậy của tín hiệu kiểm thử và tác động thực tế của những lần thực thi bổ sung. Nhóm cần phân biệt tỷ lệ test thiếu ổn định, retry pass rate, initial failure rate và rerun rate; mỗi chỉ số phải có đơn vị, mẫu số và cửa sổ quan sát rõ ràng. Việc lưu lịch sử từng attempt, so sánh trong điều kiện tương đương, phân loại nguyên nhân và giới hạn retry giúp tránh che giấu lỗi sản phẩm. Khi đo riêng runner time, queue delay, giờ điều tra và chi phí dịch vụ, nhóm có thể ưu tiên sửa test gây ảnh hưởng lớn, quản lý quarantine có thời hạn và cải thiện feedback loop CI/CD bằng bằng chứng có thể kiểm tra lại.
