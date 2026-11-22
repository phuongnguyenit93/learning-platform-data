# Chọn chỉ số từ mục tiêu và câu hỏi cần trả lời

**Chương:** Đo lường  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Đo lường kiểm thử chỉ có giá trị khi giúp nhóm đưa ra quyết định tốt hơn. Một dashboard có thể hiển thị hàng chục con số như số test đã chạy, tỷ lệ pass, code coverage, số lỗi được tìm thấy hoặc thời gian pipeline. Tuy nhiên, nếu không biết những con số đó trả lời câu hỏi nào, nhóm dễ tối ưu hoạt động đo được thay vì cải thiện chất lượng sản phẩm.

Chọn chỉ số cần bắt đầu từ mục tiêu, câu hỏi và quyết định mà người sử dụng thông tin phải đưa ra. Nếu mục tiêu là giảm rủi ro phát hành, nhóm cần biết những rủi ro quan trọng nào đã được kiểm tra và còn khoảng trống nào. Nếu mục tiêu là rút ngắn phản hồi, cần đo thời gian từ thay đổi đến kết quả đáng tin cậy, đồng thời hiểu phần thời gian chờ và điều tra. Nếu mục tiêu là cải thiện độ tin cậy của bộ tự động hóa, tỷ lệ pass đơn thuần không đủ; cần xem flaky test, retry, thời gian bảo trì và khả năng phát hiện lỗi.

Bài học này trình bày cách chuyển mục tiêu thành câu hỏi đo lường, lựa chọn chỉ số phù hợp, định nghĩa cách tính và nguồn dữ liệu, phân biệt chỉ số kết quả với chỉ số dẫn dắt, thiết kế dashboard có thể hành động và tránh các cách đo gây hiểu lầm. Trọng tâm là xây dựng một hệ thống đo lường phục vụ quyết định kiểm thử và cải tiến liên tục.

Sau bài học, người học có thể:

- Chuyển mục tiêu chất lượng hoặc vận hành thành câu hỏi cần trả lời.
- Phân biệt mục tiêu, câu hỏi, chỉ số, ngưỡng và hành động.
- Chọn một tập chỉ số cân bằng theo rủi ro và bối cảnh.
- Viết định nghĩa đo lường rõ ràng, có công thức, phạm vi và nguồn dữ liệu.
- Phân biệt chỉ số dẫn dắt, chỉ số kết quả và chỉ số cân bằng.
- Đánh giá giới hạn, độ tin cậy và khả năng bị diễn giải sai của chỉ số.
- Thiết kế dashboard và nhịp rà soát gắn với quyết định cụ thể.
- Dùng kết quả đo để điều chỉnh chiến lược kiểm thử mà không tạo động lực tối ưu sai lệch.

## 1. Bắt đầu từ mục tiêu, không bắt đầu từ dữ liệu sẵn có

Nhiều nhóm bắt đầu đo lường bằng cách xem công cụ hiện có cung cấp những biểu đồ nào. Cách làm này dễ tạo dashboard nhiều số nhưng thiếu liên hệ với quyết định. Một cách tốt hơn là xác định mục tiêu trước, sau đó mới tìm dữ liệu cần thu thập.

### 1.1. Phân biệt mục tiêu và chỉ số

- **Mục tiêu (goal):** trạng thái hoặc kết quả mà nhóm muốn đạt, ví dụ giảm rủi ro lỗi nghiêm trọng lọt đến người dùng.
- **Câu hỏi đo lường (measurement question):** điều cần biết để đánh giá tiến độ hoặc chọn hành động, ví dụ các luồng rủi ro cao đã được kiểm tra trên build phát hành chưa?
- **Chỉ số (metric):** đại lượng được định nghĩa để trả lời câu hỏi, ví dụ tỷ lệ luồng rủi ro cao có bằng chứng kiểm thử hợp lệ.
- **Ngưỡng hoặc mục tiêu định lượng (target/threshold):** mức tham chiếu để nhận diện tình trạng cần chú ý, ví dụ 100% kiểm tra bắt buộc phải hoàn tất trước khi phát hành.
- **Hành động (action):** quyết định được thực hiện khi đọc kết quả, ví dụ bổ sung kiểm thử, trì hoãn phát hành hoặc chấp nhận rủi ro theo thẩm quyền.

Một chỉ số không tự tạo ra cải tiến. Giá trị của nó nằm ở việc giúp trả lời câu hỏi và kích hoạt hành động phù hợp.

### 1.2. Ví dụ chuyển mục tiêu thành câu hỏi

| Mục tiêu | Câu hỏi cần trả lời | Chỉ số có thể dùng |
|---|---|---|
| Giảm lỗi nghiêm trọng lọt đến production | Những rủi ro nghiêm trọng nào vẫn chưa được kiểm tra hoặc phát hiện quá muộn? | Lỗi nghiêm trọng lọt sau phát hành; tỷ lệ rủi ro cao có bằng chứng kiểm tra |
| Rút ngắn phản hồi cho lập trình viên | Từ lúc gửi thay đổi đến khi có kết quả kiểm thử đáng tin cậy mất bao lâu? | Thời gian phản hồi CI; thời gian chờ build; thời gian phân loại thất bại |
| Tăng độ tin cậy của tự động hóa | Kết quả test có nhất quán và có thể giải thích không? | Tỷ lệ flaky; tỷ lệ retry; thời gian điều tra; tỷ lệ test có chủ sở hữu |
| Cải thiện hiệu quả hồi quy | Tập hồi quy có phát hiện lỗi quan trọng trong thời gian cho phép không? | Thời gian suite; lỗi phát hiện trước phát hành; phạm vi rủi ro được kiểm tra |
| Cải thiện quy trình sửa lỗi | Bản sửa có được xác minh đầy đủ và ít bị mở lại không? | Tỷ lệ retest đạt lần đầu; tỷ lệ mở lại; thời gian từ bàn giao đến đóng |
| Dùng nguồn lực hợp lý | Năng lực có được dành cho các rủi ro và công việc quan trọng không? | Tải theo loại công việc; thời gian chờ; tỷ lệ buffer sử dụng |

### 1.3. Viết câu hỏi có thể dẫn đến hành động

Câu hỏi tốt cần cụ thể và gắn với một quyết định. Ví dụ:

- “Chất lượng có tốt không?” quá rộng và không chỉ ra hành động.
- “Có bao nhiêu lỗi nghiêm trọng được phát hiện sau phát hành trong ba bản phát hành gần nhất, và nguyên nhân nào lặp lại?” giúp nhóm xem xét khoảng trống kiểm thử.
- “Bao nhiêu phần trăm pull request nhận được kết quả kiểm thử đáng tin cậy trong 15 phút?” giúp nhóm xem xét thời gian pipeline và phạm vi kiểm tra nhanh.
- “Những test nào retry nhiều lần nhưng không có nguyên nhân được xác định?” giúp nhóm ưu tiên xử lý flaky test.

Một câu hỏi có thể cần nhiều chỉ số. Ngược lại, một chỉ số có thể hỗ trợ nhiều câu hỏi nhưng cần diễn giải theo từng bối cảnh.

## 2. Xây dựng chuỗi mục tiêu → câu hỏi → chỉ số → hành động

Chuỗi này giúp bảo đảm mỗi số liệu có mục đích rõ ràng và không tồn tại chỉ để lấp đầy dashboard.

### 2.1. Bốn bước thiết kế

1. **Nêu mục tiêu:** mô tả kết quả cần cải thiện, đối tượng hưởng lợi và phạm vi.
2. **Đặt câu hỏi:** xác định điều chưa biết khiến nhóm chưa thể quyết định.
3. **Chọn chỉ số:** định nghĩa đại lượng có thể thu thập để trả lời câu hỏi.
4. **Quy định hành động:** nêu điều gì sẽ được xem xét khi chỉ số thay đổi hoặc vượt ngưỡng.

Ví dụ:

| Thành phần | Nội dung |
|---|---|
| Mục tiêu | Giảm thời gian phát hiện lỗi do thay đổi code |
| Câu hỏi | Từ commit đến khi có tín hiệu đáng tin cậy mất bao lâu? |
| Chỉ số chính | Median và percentile 90 của thời gian phản hồi CI |
| Chỉ số bổ sung | Thời gian xếp hàng, thời gian chạy, thời gian phân loại thất bại |
| Hành động | Tách suite nhanh, giảm hàng đợi, cải thiện runner hoặc loại flaky test khỏi cổng chặn theo chính sách |

### 2.2. Chọn người sử dụng và nhịp quyết định

Chỉ số có thể phục vụ nhiều cấp:

- **Developer:** cần phản hồi nhanh về thay đổi hiện tại và lỗi cụ thể.
- **Test engineer/QA:** cần biết phạm vi, độ ổn định, chất lượng dữ liệu và khoảng trống test.
- **Test lead:** cần điều phối nguồn lực, ưu tiên và rủi ro theo chu kỳ.
- **Engineering/release manager:** cần quyết định về phát hành, năng lực và đầu tư cải thiện.
- **Product owner/business owner:** cần hiểu rủi ro đối với người dùng và nghiệp vụ.

Một dashboard không nhất thiết phải phục vụ mọi đối tượng. Người dùng khác nhau cần mức chi tiết và tần suất khác nhau. Ví dụ, developer xem kết quả theo từng commit; lãnh đạo xem xu hướng theo tháng hoặc bản phát hành.

### 2.3. Kiểm tra xem chỉ số có thực sự cần thiết

Trước khi thêm chỉ số, hãy hỏi:

- Chỉ số này trả lời câu hỏi nào?
- Ai sẽ dùng nó?
- Quyết định nào có thể thay đổi nhờ thông tin này?
- Có dữ liệu đáng tin để tính không?
- Có chỉ số khác đã trả lời cùng câu hỏi không?
- Chi phí thu thập và duy trì có tương xứng không?
- Chỉ số có thể bị tối ưu sai hoặc gây hành vi không mong muốn không?

Nếu không xác định được người sử dụng hoặc hành động, nên cân nhắc chưa đưa chỉ số vào dashboard.

## 3. Phân biệt các loại chỉ số

Không phải mọi chỉ số đều phản ánh cùng một khía cạnh. Kết hợp các loại chỉ số giúp nhóm hiểu cả kết quả lẫn yếu tố dẫn đến kết quả.

### 3.1. Chỉ số dẫn dắt (leading indicators)

Chỉ số dẫn dắt phản ánh hoạt động hoặc điều kiện có thể ảnh hưởng đến kết quả tương lai. Ví dụ:

- Tỷ lệ thay đổi có phân tích rủi ro trước khi merge.
- Tỷ lệ test quan trọng có chủ sở hữu.
- Tỷ lệ migration được kiểm tra trên database sạch.
- Tỷ lệ test flaky được xử lý trong thời hạn.
- Tỷ lệ thay đổi có test ở tầng phù hợp.

Chỉ số dẫn dắt giúp nhóm can thiệp sớm, nhưng không bảo đảm kết quả cuối cùng. Tỷ lệ review rủi ro cao không chứng minh mọi rủi ro đã được nhận diện đúng.

### 3.2. Chỉ số kết quả (lagging indicators)

Chỉ số kết quả phản ánh điều đã xảy ra:

- Số hoặc tỷ lệ lỗi lọt đến production.
- Số incident liên quan đến thay đổi.
- Tỷ lệ rollback hoặc hotfix sau phát hành.
- Thời gian khắc phục sự cố.
- Tỷ lệ lỗi được mở lại sau retest.

Các chỉ số này quan trọng nhưng thường đến muộn và có thể chịu ảnh hưởng của nhiều yếu tố ngoài kiểm thử.

### 3.3. Chỉ số cân bằng (balancing measures)

Chỉ số cân bằng giúp phát hiện tác dụng phụ khi tối ưu một mục tiêu. Ví dụ:

- Giảm thời gian pipeline nhưng theo dõi lỗi lọt và phạm vi test bị bỏ qua.
- Tăng tỷ lệ tự động hóa nhưng theo dõi giờ bảo trì và tỷ lệ flaky.
- Tăng số test chạy nhưng theo dõi thời gian phản hồi và giá trị phát hiện lỗi.
- Tăng tỷ lệ đóng lỗi nhanh nhưng theo dõi tỷ lệ mở lại và lỗi tái diễn.

Nếu chỉ đo tốc độ, nhóm có thể bỏ kiểm tra quan trọng. Nếu chỉ đo số lượng test, nhóm có thể tạo nhiều test trùng lặp. Chỉ số cân bằng giúp nhìn thấy cái giá phải trả của một cải tiến.

### 3.4. Chỉ số hoạt động, chất lượng và hiệu quả

Có thể phân nhóm theo câu hỏi:

| Nhóm | Câu hỏi | Ví dụ |
|---|---|---|
| Hoạt động | Nhóm đã làm bao nhiêu? | Số test chạy, số build, số lỗi được retest |
| Chất lượng kết quả | Hệ thống hoặc test có đáng tin? | Lỗi lọt, flaky rate, tỷ lệ mở lại |
| Hiệu quả luồng | Công việc được hoàn thành nhanh và ổn định thế nào? | Lead time, cycle time, thời gian CI |
| Mức bảo vệ | Rủi ro quan trọng nào đã được kiểm tra? | Rủi ro có test, phạm vi yêu cầu có bằng chứng |
| Nguồn lực | Năng lực được sử dụng ra sao? | Giờ retest, giờ bảo trì, buffer, runner utilization |

Số lượng hoạt động không nên được dùng như đại diện duy nhất cho chất lượng hoặc hiệu quả.

## 4. Chọn chỉ số theo mục tiêu kiểm thử

Mỗi mục tiêu cần một tập chỉ số nhỏ, cân bằng và có định nghĩa rõ. Dưới đây là các ví dụ thường gặp trong chiến lược kiểm thử.

### 4.1. Mục tiêu: giảm rủi ro lỗi lọt

Câu hỏi:

- Lỗi nghiêm trọng nào xuất hiện sau phát hành?
- Những rủi ro quan trọng nào chưa có bằng chứng kiểm thử?
- Lỗi được phát hiện ở tầng nào và muộn đến đâu?

Chỉ số có thể dùng:

- Số lỗi production theo mức nghiêm trọng và nhóm nguyên nhân.
- Tỷ lệ lỗi nghiêm trọng được phát hiện trước phát hành.
- Tỷ lệ rủi ro cao có test và kết quả gần nhất còn hợp lệ.
- Tỷ lệ lỗi tái diễn có nguyên nhân tương tự.
- Số incident liên quan đến thay đổi chưa được kiểm tra ở tầng phù hợp.

Không nên chỉ đếm tổng số lỗi. Cần phân tích severity, mức phơi nhiễm, loại sản phẩm, số thay đổi và thời gian quan sát.

### 4.2. Mục tiêu: rút ngắn phản hồi CI

Câu hỏi:

- Mất bao lâu từ khi gửi thay đổi đến khi có kết quả đáng tin cậy?
- Thời gian bị tiêu tốn ở hàng đợi, build, test hay điều tra?
- Tập test nhanh có phát hiện lỗi quan trọng đủ sớm không?

Chỉ số:

- Median và percentile 90 của thời gian phản hồi.
- Thời gian chờ runner và thời gian thực thi.
- Tỷ lệ job bị retry hoặc bị hủy.
- Tỷ lệ lỗi quan trọng được phát hiện trong pipeline sớm.
- Tỷ lệ test flaky trong suite chặn merge.

Không chỉ đo thời gian trung bình vì một số job rất chậm có thể bị che khuất. Percentile giúp hiểu trải nghiệm của phần lớn lần chạy và các trường hợp chậm.

### 4.3. Mục tiêu: tăng độ tin cậy của tự động hóa

Câu hỏi:

- Kết quả có ổn định khi điều kiện tương đương không?
- Bao nhiêu thời gian dành cho điều tra thất bại giả?
- Test có chủ sở hữu và được cập nhật khi sản phẩm thay đổi không?

Chỉ số:

- Tỷ lệ lần chạy flaky được xác nhận.
- Số lần retry trên mỗi pipeline.
- Thời gian xử lý flaky test.
- Tỷ lệ test quarantine quá hạn.
- Tỷ lệ test có chủ sở hữu và metadata cần thiết.
- Tỷ lệ test quan trọng có kết quả ổn định qua các lần chạy đại diện.

Tỷ lệ pass đơn thuần không đủ vì một test có thể đạt sau nhiều lần retry hoặc không được chạy do bị bỏ qua.

### 4.4. Mục tiêu: cải thiện quy trình xử lý lỗi

Câu hỏi:

- Bản sửa có được retest đúng điều kiện không?
- Bao nhiêu lỗi phải mở lại?
- Thời gian chờ từ bàn giao đến retest là bao lâu?
- Hồ sơ đóng lỗi có đủ bằng chứng không?

Chỉ số:

- Tỷ lệ retest đạt lần đầu.
- Tỷ lệ mở lại theo severity và nhóm nguyên nhân.
- Thời gian từ `Ready for retest` đến kết quả.
- Tỷ lệ lỗi đóng có liên kết build và test run.
- Tỷ lệ lỗi được đóng theo resolution phù hợp.

Không dùng số lỗi đóng trong ngày làm thước đo hiệu suất duy nhất. Điều đó có thể khuyến khích đóng lỗi trước khi có đủ bằng chứng.

### 4.5. Mục tiêu: cải thiện độ bao phủ rủi ro

Câu hỏi:

- Các rủi ro nghiêm trọng đã được liên kết với test chưa?
- Các thay đổi có phân tích tác động và chọn hồi quy không?
- Những yêu cầu quan trọng nào chưa có bằng chứng?

Chỉ số:

- Tỷ lệ rủi ro quan trọng có test được duy trì.
- Tỷ lệ thay đổi có phân tích tác động và test liên quan.
- Số rủi ro cao chưa có kiểm tra hoặc có kiểm tra không còn hiệu lực.
- Tỷ lệ kiểm tra bắt buộc hoàn tất trước release.

Code coverage có thể bổ sung thông tin về mã đã được thực thi, nhưng không thay thế việc liên kết yêu cầu và rủi ro với test.

### 4.6. Mục tiêu: sử dụng nguồn lực hiệu quả

Câu hỏi:

- Nhóm dành bao nhiêu năng lực cho retest, regression và công việc đột xuất?
- Nguồn lực nào thường xuyên trở thành điểm nghẽn?
- Công sức bảo trì tự động hóa có tương xứng với lợi ích không?

Chỉ số:

- Giờ công theo loại công việc.
- Tỷ lệ buffer được sử dụng và số lần vượt buffer.
- Thời gian chờ môi trường, build hoặc chuyên gia.
- Chi phí mỗi lần chạy hoặc mỗi chu kỳ hồi quy.
- Giờ bảo trì trên mỗi nhóm test hoặc mỗi kỳ.

Không nên tối ưu utilization của từng người lên 100%. Một nhóm không có năng lực linh hoạt sẽ khó phản ứng với lỗi nghiêm trọng hoặc thay đổi bất ngờ.

## 5. Định nghĩa chỉ số một cách chính xác

Tên chỉ số giống nhau có thể được tính khác nhau giữa các nhóm. Nếu không có định nghĩa chung, dashboard dễ dẫn đến kết luận sai.

### 5.1. Mẫu định nghĩa chỉ số

Mỗi chỉ số nên có:

- **Tên:** ngắn, rõ và không gây hiểu nhầm.
- **Mục đích:** câu hỏi mà chỉ số trả lời.
- **Định nghĩa:** đại lượng được đo và đối tượng tính.
- **Công thức:** tử số, mẫu số, đơn vị và quy tắc lọc.
- **Phạm vi:** sản phẩm, môi trường, suite, nhóm hoặc khoảng thời gian.
- **Nguồn dữ liệu:** CI, test management, defect tracker, incident system hoặc time tracking.
- **Tần suất:** theo commit, ngày, sprint, release hoặc tháng.
- **Chủ sở hữu:** người chịu trách nhiệm về định nghĩa và chất lượng dữ liệu.
- **Ngưỡng/target:** mức tham chiếu cùng lý do.
- **Hành động:** điều cần xem xét khi chỉ số thay đổi.
- **Giới hạn:** những điều chỉ số không chứng minh.

### 5.2. Xác định tử số và mẫu số

Ví dụ “tỷ lệ test pass” cần làm rõ:

- Mẫu số là số test được lên lịch, số test thực sự bắt đầu hay số test có kết quả cuối?
- Test bị skip, blocked, timeout hoặc quarantine được tính thế nào?
- Retry được tính thành một test hay nhiều attempt?
- Test bị hủy do pipeline bị dừng có được đưa vào không?
- Tỷ lệ tính theo từng job, suite, commit hay khoảng thời gian?

Một định nghĩa có thể là:

\[
\text{Pass rate} = \frac{\text{Số test có kết quả PASS ở attempt đầu}}{\text{Số test đã bắt đầu và có kết quả phân loại}} \times 100\%
\]

Đây chỉ là một lựa chọn. Nếu nhóm muốn đo kết quả cuối sau retry, cần đặt tên riêng như `final pass rate` và vẫn báo cáo attempt đầu. Không gộp hai ý nghĩa vào cùng một biểu đồ.

### 5.3. Định nghĩa thời gian

Khi đo thời gian, xác định rõ điểm bắt đầu và kết thúc. Ví dụ:

- **CI queue time:** từ lúc job được xếp hàng đến lúc runner bắt đầu.
- **Execution time:** từ lúc test bắt đầu đến khi có kết quả.
- **Feedback time:** từ lúc thay đổi được gửi đến lúc người phát triển nhận được kết quả cần thiết.
- **Defect retest lead time:** từ lúc lỗi được chuyển sang sẵn sàng retest đến lúc có kết quả retest.

Không dùng từ “thời gian kiểm thử” nếu chỉ số thực tế đo cả thời gian chờ hoặc thời gian build. Tách thành phần giúp tìm đúng điểm nghẽn.

### 5.4. Định nghĩa đơn vị và phạm vi

Chỉ số có thể tính theo test, attempt, pipeline, build, lỗi, thay đổi, người dùng hoặc bản phát hành. Đơn vị phải nhất quán. Ví dụ, số lỗi trên mỗi release không thể so sánh trực tiếp với số lỗi trên mỗi tháng nếu tần suất phát hành thay đổi.

### 5.5. Quy định cách xử lý dữ liệu thiếu

Nếu thiếu timestamp, test không có owner hoặc incident chưa phân loại, cần xác định cách thể hiện. Không tự động coi dữ liệu thiếu là 0 hoặc PASS. Có thể dùng trạng thái `unknown`, `not recorded` hoặc loại khỏi phép tính với ghi chú rõ ràng.

## 6. Một số chỉ số thường dùng và giới hạn

Các chỉ số sau hữu ích khi được gắn với câu hỏi phù hợp. Không có chỉ số đơn lẻ nào đại diện cho toàn bộ chất lượng kiểm thử.

### 6.1. Tỷ lệ pass và fail

Cho biết kết quả các test đã chạy trong phạm vi xác định. Cần tách:

- Kết quả attempt đầu.
- Kết quả sau retry.
- Test bị skip hoặc blocked.
- Test bị quarantine.
- Lỗi sản phẩm, lỗi test và lỗi hạ tầng.

Tỷ lệ pass cao không đồng nghĩa chất lượng sản phẩm cao nếu bộ test ít giá trị, test quan trọng bị bỏ qua hoặc oracle yếu.

### 6.2. Tỷ lệ flaky

Một định nghĩa có thể dùng:

\[
\text{Flaky run rate} = \frac{\text{Số attempt có kết quả không nhất quán được xác nhận}}{\text{Tổng attempt đủ điều kiện}} \times 100\%
\]

Định nghĩa “đủ điều kiện” và “được xác nhận” phải rõ. Một lần fail rồi pass có thể chỉ là dấu hiệu nghi ngờ; không nên kết luận flaky nếu chưa so sánh điều kiện và bằng chứng.

### 6.3. Tỷ lệ lỗi lọt

Có thể theo dõi số lỗi được phát hiện sau phát hành hoặc tỷ lệ lỗi được phát hiện ở production so với tổng lỗi trong một nhóm đã xác định. Tuy nhiên, mẫu số cần được định nghĩa cẩn thận vì lỗi phát hiện sau phát hành có thể được báo cáo ở nhiều thời điểm và mức độ khác nhau.

Nên phân tích theo severity, loại lỗi, phiên bản, mức phơi nhiễm và nguyên nhân. Không so sánh số thô giữa các giai đoạn có quy mô người dùng hoặc tần suất phát hành rất khác nhau.

### 6.4. Code coverage

Code coverage đo phần mã được thực thi bởi test theo một tiêu chí như line, branch hoặc instruction coverage. Nó giúp tìm mã chưa được thực thi nhưng không chứng minh assertion có ý nghĩa hoặc hành vi đúng.

Coverage cao có thể đi cùng test yếu; coverage thấp ở mã không quan trọng có thể không phải ưu tiên. Hãy dùng nó như tín hiệu hỗ trợ phân tích, kết hợp với yêu cầu, rủi ro, mutation testing hoặc chất lượng lỗi được phát hiện khi phù hợp.

### 6.5. Thời gian phản hồi và thời gian pipeline

Thời gian trung bình có thể bị ảnh hưởng bởi một số job rất chậm. Dùng median và percentile, phân tích theo loại job và xem queue time riêng. Rút ngắn pipeline cần được cân bằng với phạm vi test và lỗi lọt.

### 6.6. Defect density

Số lỗi trên một đơn vị kích thước mã hoặc chức năng có thể hỗ trợ so sánh trong phạm vi tương đồng, nhưng cách đo kích thước và độ phức tạp có nhiều giới hạn. Không dùng defect density như thước đo chất lượng cá nhân hoặc để xếp hạng nhóm mà không xét bối cảnh.

### 6.7. Retest first-pass rate và reopen rate

Hai chỉ số này hỗ trợ đánh giá chất lượng bàn giao bản sửa và quy trình xác minh. Cần phân tích theo loại lỗi, độ phức tạp và mức nghiêm trọng. Tỷ lệ đạt lần đầu thấp có thể do bản sửa chưa tốt, nhưng cũng có thể do điều kiện retest thay đổi hoặc hồ sơ lỗi chưa đầy đủ.

### 6.8. Test effectiveness

Có thể xem xét số lỗi có ý nghĩa được phát hiện bởi một tập test trong một khoảng thời gian hoặc tỷ lệ lỗi đã biết được tái hiện bởi các ca kiểm tra. Cần tránh coi số lỗi tìm thấy càng nhiều luôn càng tốt: số lỗi có thể tăng do chất lượng giảm, phạm vi kiểm tra tăng hoặc cách phân loại thay đổi.

## 7. Chọn tập chỉ số cân bằng

Một dashboard tốt không cần có nhiều chỉ số. Nó cần có đủ góc nhìn để tránh kết luận sai và hỗ trợ quyết định.

### 7.1. Mô hình cân bằng tham khảo

Với mục tiêu giảm rủi ro phát hành, có thể dùng:

| Góc nhìn | Chỉ số chính | Chỉ số cân bằng |
|---|---|---|
| Kết quả chất lượng | Lỗi nghiêm trọng lọt sau release | Số incident và mức phơi nhiễm |
| Mức bảo vệ | Rủi ro cao có test hợp lệ | Rủi ro chưa có oracle hoặc test đã lỗi thời |
| Tốc độ phản hồi | Median/P90 CI feedback time | Tỷ lệ test quan trọng bị bỏ qua |
| Độ tin cậy | Flaky run rate | Retry rate và giờ điều tra |
| Hiệu quả nguồn lực | Giờ kiểm thử theo loại công việc | Giờ bảo trì và thời gian chờ |

### 7.2. Tránh chỉ số trùng lặp

Nếu hai chỉ số gần như trả lời cùng một câu hỏi và dẫn đến cùng hành động, có thể chỉ cần một chỉ số chính và một phân tích chi tiết. Ví dụ, số job fail và tỷ lệ job fail có thể cùng hữu ích nhưng cần phân biệt quy mô chạy. Không nên đưa cả hai lên vị trí nổi bật nếu không có quyết định riêng.

### 7.3. Chọn số lượng vừa đủ

Một nhóm có thể bắt đầu với một vài câu hỏi quan trọng và một tập chỉ số nhỏ. Khi có nhu cầu mới, bổ sung chỉ số dựa trên quyết định cần hỗ trợ. Dashboard có quá nhiều biểu đồ thường khiến tín hiệu quan trọng bị chìm.

### 7.4. Phân tích theo lát cắt phù hợp

Chỉ số tổng hợp có thể che giấu vấn đề. Hãy xem theo:

- Severity và loại rủi ro.
- Module, service hoặc luồng nghiệp vụ.
- Tầng kiểm thử.
- Môi trường và phiên bản.
- Nhóm thay đổi hoặc loại release.
- Test tự động và thủ công.
- Nhóm nguyên nhân: sản phẩm, test, dữ liệu, hạ tầng hoặc phụ thuộc.

Không phân đoạn quá nhỏ đến mức mẫu dữ liệu không đủ để kết luận. Cần nêu số lượng quan sát khi hiển thị tỷ lệ.

## 8. Đặt ngưỡng và mục tiêu có căn cứ

Ngưỡng giúp xác định khi nào cần xem xét, nhưng một con số không có bối cảnh có thể gây hành vi sai.

### 8.1. Phân biệt baseline, target và threshold

- **Baseline:** mức hiện tại được đo trong điều kiện và kỳ quan sát xác định.
- **Target:** mức mong muốn trong một khoảng thời gian.
- **Threshold:** ngưỡng kích hoạt điều tra hoặc hành động.
- **SLO/commitment:** mức dịch vụ hoặc chất lượng được cam kết với đối tượng liên quan, nếu tổ chức có áp dụng.

Ví dụ, baseline P90 CI feedback time hiện tại là 28 phút; mục tiêu là giảm xuống 20 phút trong quý; ngưỡng cảnh báo là P90 vượt 30 phút trong ba ngày liên tiếp. Các giá trị cần dựa trên dữ liệu và nhu cầu thực tế, không sao chép máy móc từ tổ chức khác.

### 8.2. Đặt ngưỡng theo rủi ro

Không phải mọi chỉ số cần cùng một ngưỡng. Với kiểm tra bắt buộc về phân quyền, mục tiêu có thể là 100% ca bắt buộc phải được thực thi và đạt trước release. Với thời gian pipeline, có thể dùng percentile và xu hướng thay vì một ngưỡng tuyệt đối.

### 8.3. Dùng xu hướng và biến động

Một ngày có tỷ lệ fail tăng chưa chắc là xu hướng. Cần xem khoảng thời gian, số lượng mẫu, mùa vụ, thay đổi sản phẩm và các sự kiện liên quan. Dùng biểu đồ theo thời gian, moving average hoặc percentile khi phù hợp.

### 8.4. Không tạo mục tiêu không thể kiểm soát

Ví dụ, đặt mục tiêu “không có lỗi production” có thể không thực tế vì chất lượng chịu ảnh hưởng của nhiều nhóm và yếu tố. Nhóm kiểm thử có thể cam kết những hoạt động trong phạm vi kiểm soát như kiểm tra rủi ro bắt buộc, duy trì test và cung cấp bằng chứng rõ ràng; kết quả production cần được theo dõi như mục tiêu chung của sản phẩm.

## 9. Chất lượng dữ liệu đo lường

Một chỉ số chỉ đáng tin khi dữ liệu nguồn đầy đủ, chính xác và nhất quán.

### 9.1. Nguồn dữ liệu phổ biến

- CI/CD: trạng thái job, thời gian queue/run, retry, commit và artifact.
- Test management: test case, requirement link, owner, trạng thái và lần thực thi.
- Defect tracker: severity, trạng thái, resolution, nguyên nhân và thời gian.
- Incident management: sự cố production, tác động, thời điểm phát hiện và khắc phục.
- Repository: diff, commit, review và lịch sử thay đổi.
- Monitoring/observability: latency, error rate, availability và trace.
- Resource planning/time tracking: giờ công, WIP, năng lực và thời gian chờ.

Không nhất thiết phải tích hợp mọi nguồn ngay từ đầu. Bắt đầu với dữ liệu cần thiết cho câu hỏi ưu tiên, sau đó mở rộng có kiểm soát.

### 9.2. Chuẩn hóa định danh

Để liên kết dữ liệu, cần có định danh nhất quán cho:

- Commit, build và pipeline run.
- Test case và test execution.
- Defect và incident.
- Requirement, risk và module.
- Release, môi trường và phiên bản.

Nếu mỗi hệ thống dùng mã khác nhau mà không có liên kết, phân tích nguyên nhân và truy vết sẽ khó khăn.

### 9.3. Xử lý dữ liệu trùng và thiếu

Một lỗi có thể xuất hiện trong nhiều báo cáo hoặc được mở ở nhiều hệ thống. Cần quy tắc hợp nhất và giữ lịch sử. Dữ liệu thiếu phải được đánh dấu rõ; không tự coi là không có lỗi hoặc test đã đạt.

### 9.4. Đồng bộ thời gian

Khi tính lead time hoặc thời gian phản hồi, các hệ thống cần dùng timestamp có múi giờ rõ, tốt nhất chuẩn hóa về UTC ở tầng lưu trữ và hiển thị theo nhu cầu. Đồng hồ hệ thống sai lệch có thể tạo thời lượng âm hoặc thứ tự sự kiện sai.

### 9.5. Bảo vệ dữ liệu và quyền truy cập

Dashboard có thể chứa thông tin về lỗ hổng, sự cố, dữ liệu khách hàng hoặc năng lực cá nhân. Áp dụng quyền truy cập theo vai trò, ẩn dữ liệu nhạy cảm và giới hạn thời gian lưu. Không dùng dữ liệu cá nhân để xếp hạng hiệu suất cá nhân nếu mục tiêu và quy định không cho phép.

## 10. Thiết kế dashboard phục vụ quyết định

Dashboard nên giúp người xem hiểu tình trạng, nguyên nhân có thể và hành động tiếp theo trong thời gian ngắn.

### 10.1. Cấu trúc dashboard

Một dashboard kiểm thử có thể chia thành:

1. **Tình trạng hiện tại:** các kiểm tra bắt buộc, release gate và rủi ro chưa giải quyết.
2. **Xu hướng chất lượng:** lỗi lọt, incident, lỗi tái diễn và severity.
3. **Tốc độ phản hồi:** thời gian CI, queue time, thời gian retest và regression.
4. **Độ tin cậy:** flaky, retry, quarantine và test thiếu owner.
5. **Mức bảo vệ:** rủi ro/requirment có test, thay đổi có phân tích tác động.
6. **Nguồn lực:** tải theo danh mục, thời gian chờ và buffer.

Không nhất thiết đưa mọi nhóm lên cùng một màn hình. Có thể tạo dashboard riêng cho developer, QA lead và release manager.

### 10.2. Hiển thị phạm vi và mẫu số

Khi hiển thị tỷ lệ, luôn cho biết số lượng quan sát. Ví dụ `95% pass (190/200 tests)` có ý nghĩa hơn `95%` đứng riêng. Nêu rõ suite, môi trường, kỳ thời gian và cách tính.

### 10.3. Hiển thị xu hướng thay vì một ảnh chụp

Một điểm dữ liệu chỉ phản ánh một thời điểm. Xu hướng theo ngày, sprint hoặc release giúp nhận diện thay đổi bền vững. Khi có sự kiện lớn như đổi runner hoặc thay cách phân loại, đánh dấu trên biểu đồ để người xem không diễn giải nhầm.

### 10.4. Cho phép đi từ tổng quan đến chi tiết

Người xem cần có khả năng mở từ một chỉ số đến các đối tượng liên quan: job, test, lỗi, incident hoặc thay đổi. Nếu dashboard chỉ hiển thị con số tổng mà không thể truy về nguồn, nó khó hỗ trợ điều tra.

### 10.5. Nêu hành động hoặc chủ sở hữu

Khi chỉ số vượt ngưỡng, dashboard hoặc báo cáo nên chỉ ra:

- Điều gì thay đổi?
- Phạm vi và mức độ ảnh hưởng?
- Có giả thuyết nguyên nhân nào?
- Ai chịu trách nhiệm điều tra?
- Khi nào xem xét lại?

Không nên tạo cảnh báo cho mọi dao động nhỏ. Cảnh báo quá nhiều khiến người dùng bỏ qua tín hiệu quan trọng.

## 11. Đọc chỉ số trong bối cảnh

Chỉ số không tự giải thích nguyên nhân. Cần kết hợp dữ liệu định lượng với bối cảnh thay đổi, điều tra định tính và hiểu biết miền nghiệp vụ.

### 11.1. Tương quan không chứng minh nguyên nhân

Nếu tỷ lệ test pass giảm sau khi cập nhật JDK, điều đó chưa chứng minh JDK gây lỗi. Cùng thời điểm có thể có thay đổi dependency, runner hoặc test data. Cần so sánh có kiểm soát và tìm bằng chứng.

### 11.2. Số lỗi tăng có thể là tín hiệu tích cực

Số lỗi được phát hiện có thể tăng vì:

- Chất lượng sản phẩm giảm.
- Phạm vi test mở rộng.
- Test mới có oracle tốt hơn.
- Nhóm cải thiện khả năng quan sát.
- Người dùng báo lỗi dễ dàng hơn.

Do đó, không nên kết luận chất lượng giảm chỉ từ số lỗi tăng. Phân tích severity, nơi phát hiện, phạm vi sử dụng và xu hướng theo thời gian.

### 11.3. Tỷ lệ pass tăng có thể che khoảng trống

Tỷ lệ pass có thể tăng nếu test fail bị quarantine, bị skip hoặc không được chạy. Cần theo dõi số test được lên lịch, bắt đầu, hoàn tất, bị bỏ qua và bị quarantine.

### 11.4. Coverage tăng không đồng nghĩa kiểm thử tốt hơn

Coverage có thể tăng do chạy thêm mã nhưng không có assertion có giá trị. Kết hợp với chất lượng test, mutation score nếu phù hợp, traceability và lỗi được phát hiện.

### 11.5. So sánh phải cùng cơ sở

Trước khi so sánh hai nhóm hoặc hai giai đoạn, kiểm tra:

- Cùng định nghĩa và công thức không?
- Cùng phạm vi và loại sản phẩm không?
- Số lượng quan sát có tương đương không?
- Mức độ thay đổi và tần suất phát hành có khác không?
- Có thay đổi công cụ hoặc cách thu thập dữ liệu không?

Nếu cơ sở khác nhau, cần điều chỉnh, phân đoạn hoặc giải thích giới hạn thay vì xếp hạng trực tiếp.

## 12. Tránh hành vi tối ưu sai lệch do chỉ số

Khi một chỉ số trở thành mục tiêu, người thực hiện có thể thay đổi hành vi để cải thiện con số mà không cải thiện kết quả thực. Đây là rủi ro cần xem xét khi thiết kế hệ thống đo lường.

### 12.1. Đếm số test để đo năng suất

Nếu đánh giá nhóm bằng số test được viết, có thể xuất hiện nhiều test trùng lặp, assertion yếu hoặc test ít giá trị. Hãy đo mức bảo vệ rủi ro, chất lượng bằng chứng, độ ổn định và lỗi được phát hiện.

### 12.2. Đếm số lỗi đóng

Nếu mục tiêu là đóng càng nhiều lỗi càng tốt, nhóm có thể đóng sớm, dùng resolution không phù hợp hoặc tránh nhận lỗi phức tạp. Cân bằng với tỷ lệ mở lại, chất lượng bằng chứng, lỗi tái diễn và severity.

### 12.3. Tối ưu tỷ lệ pass

Nếu chỉ nhìn tỷ lệ pass, nhóm có thể skip test khó, quarantine test thất bại hoặc retry cho đến khi đạt. Báo cáo cần giữ kết quả lần đầu, số lần chạy lại, test bị bỏ qua và phạm vi chưa kiểm tra.

### 12.4. Tối ưu thời gian pipeline bằng cách giảm kiểm tra

Giảm thời gian bằng cách bỏ test quan trọng có thể làm tăng lỗi lọt. Theo dõi đồng thời phạm vi rủi ro được kiểm tra, lỗi phát hiện muộn và thời gian phản hồi.

### 12.5. Dùng chỉ số để xếp hạng cá nhân

Chỉ số kiểm thử thường chịu ảnh hưởng của độ phức tạp, phân công, phụ thuộc và chất lượng đầu vào. Dùng chúng để đánh giá cá nhân một cách máy móc có thể làm giảm hợp tác và khuyến khích che giấu vấn đề. Ưu tiên dùng số liệu để cải thiện quy trình và năng lực hệ thống.

### 12.6. Đặt target mà không có baseline

Mục tiêu tùy ý có thể khiến nhóm tập trung vào con số không thực tế. Hãy đo baseline, hiểu biến động và đặt mục tiêu theo khả năng kiểm soát.

## 13. Ví dụ thiết kế bộ chỉ số cho một mục tiêu

Giả sử mục tiêu của nhóm là **giảm thời gian phát hiện lỗi quan trọng mà không làm giảm mức bảo vệ trước phát hành**.

### 13.1. Câu hỏi đo lường

- Thay đổi có nhận được phản hồi kiểm thử nhanh không?
- Các lỗi nghiêm trọng có được phát hiện trong tập chạy sớm không?
- Việc rút ngắn pipeline có làm giảm phạm vi kiểm tra không?
- Test trong tập chạy sớm có đáng tin cậy không?

### 13.2. Chọn chỉ số

| Loại | Chỉ số | Vai trò |
|---|---|---|
| Chính | Median và P90 thời gian từ commit đến kết quả CI đầu tiên | Đo tốc độ phản hồi |
| Kết quả | Số lỗi nghiêm trọng được phát hiện trước release và sau release | Theo dõi tác động chất lượng |
| Bảo vệ | Tỷ lệ rủi ro cao có test trong tập chạy sớm hoặc có kiểm tra bổ sung trước release | Ngăn tối ưu tốc độ bằng cách bỏ rủi ro |
| Tin cậy | Flaky run rate và retry rate của suite sớm | Đánh giá độ tin cậy tín hiệu |
| Cân bằng | Tỷ lệ test quan trọng bị skip/blocked và số lỗi mở lại | Phát hiện suy giảm chất lượng |

### 13.3. Định nghĩa chỉ số chính

**P90 CI feedback time** có thể được định nghĩa là percentile 90 của thời gian từ timestamp commit được nhận vào pipeline đến thời điểm có kết quả đầu tiên của tập kiểm tra bắt buộc.

Quy tắc cần nêu:

- Chỉ tính pipeline cho các thay đổi thuộc phạm vi đã chọn.
- Dùng timestamp nhất quán và cùng múi giờ lưu trữ.
- Kết quả đầu tiên không bao gồm thời gian retry.
- Job bị hủy hoặc bị chặn được báo cáo riêng, không âm thầm loại khỏi dữ liệu.
- Phân tích theo loại runner hoặc suite nếu khác biệt đáng kể.

### 13.4. Đặt baseline và target

Giả sử baseline trong bốn tuần là median 12 phút và P90 27 phút. Nhóm đặt mục tiêu giảm P90 xuống 20 phút trong tám tuần, đồng thời giữ tỷ lệ rủi ro cao có bằng chứng kiểm tra ở mức đã thống nhất và không làm tăng lỗi nghiêm trọng lọt sau release.

Các con số này chỉ là ví dụ. Nhóm cần kiểm tra khối lượng pipeline, số lượng thay đổi và tính mùa vụ trước khi so sánh.

### 13.5. Quyết định dựa trên kết quả

- Nếu P90 tăng do queue time, xem xét runner và lịch job.
- Nếu P90 tăng do test chậm, phân tích suite và mức song song.
- Nếu thời gian giảm nhưng test quan trọng bị skip tăng, xem lại chiến lược chọn test.
- Nếu flaky rate tăng, xử lý độ ổn định trước khi dựa vào kết quả để chặn merge.
- Nếu lỗi nghiêm trọng vẫn lọt, phân tích khoảng trống rủi ro thay vì chỉ tiếp tục tối ưu thời gian.

Ví dụ cho thấy một mục tiêu cần nhiều chỉ số bổ trợ để quyết định đúng.

## 14. Ví dụ định nghĩa một số chỉ số

### 14.1. Tỷ lệ rủi ro cao có bằng chứng kiểm thử

\[
\text{Risk evidence rate} = \frac{\text{Số rủi ro cao có test hợp lệ và kết quả còn hiệu lực}}{\text{Tổng số rủi ro cao trong phạm vi}} \times 100\%
\]

“Test hợp lệ” cần được định nghĩa, ví dụ test có oracle rõ, có chủ sở hữu, được chạy trên phiên bản phù hợp và có kết quả gần nhất đáp ứng chính sách. Một liên kết đến test chưa chạy không nên được tính là bằng chứng hoàn tất.

### 14.2. Tỷ lệ mở lại lỗi

\[
\text{Reopen rate} = \frac{\text{Số lỗi đã đóng rồi được mở lại trong kỳ}}{\text{Số lỗi được đóng trong kỳ}} \times 100\%
\]

Nhóm cần quy định cách xử lý lỗi trùng, lỗi mở lại nhiều lần và lỗi được mở lại ở kỳ khác. Nên phân đoạn theo severity và resolution.

### 14.3. Tỷ lệ test quarantine quá hạn

\[
\text{Overdue quarantine rate} = \frac{\text{Số test quarantine đã quá ngày rà soát}}{\text{Tổng số test quarantine đang mở}} \times 100\%
\]

Chỉ số này giúp nhận diện test bị cách ly mà không có hành động tiếp theo. Cần có owner và ngày rà soát cho mỗi test.

### 14.4. Tỷ lệ sử dụng buffer

\[
\text{Buffer utilization} = \frac{\text{Giờ công việc đột xuất đã sử dụng}}{\text{Giờ buffer đã dành}} \times 100\%
\]

Nếu vượt 100%, nhóm đã sử dụng nhiều hơn năng lực dự phòng. Nếu liên tục rất thấp, có thể điều chỉnh cách phân bổ, nhưng cần xét biến động và sự cố hiếm có hậu quả lớn.

### 14.5. Thời gian retest

Có thể đo thời gian từ lúc lỗi được chuyển sang `Ready for retest` đến lúc có kết quả retest đầu tiên. Nên tách thời gian chờ build/môi trường khỏi thời gian tester thực hiện và phân tích để tìm đúng điểm nghẽn.

## 15. Quy trình quản lý danh mục chỉ số

Chỉ số cần được duy trì như một phần của hệ thống kiểm thử. Khi mục tiêu, công cụ hoặc quy trình thay đổi, định nghĩa có thể cần cập nhật.

1. **Đề xuất câu hỏi:** nêu quyết định cần hỗ trợ và người sử dụng.
2. **Chọn chỉ số:** xác định đại lượng nhỏ nhất đủ trả lời câu hỏi.
3. **Định nghĩa:** viết công thức, phạm vi, đơn vị, mẫu số và ngoại lệ.
4. **Kiểm tra dữ liệu:** xác minh nguồn, độ đầy đủ, timestamp và định danh.
5. **Đo baseline:** thu thập dữ liệu trong kỳ đủ đại diện.
6. **Đặt ngưỡng hoặc target:** dựa trên baseline, rủi ro và khả năng kiểm soát.
7. **Thiết kế hành động:** quy định ai điều tra và quyết định gì khi có tín hiệu.
8. **Thử nghiệm dashboard:** kiểm tra người dùng có hiểu và dùng được thông tin không.
9. **Rà soát định kỳ:** kiểm tra chỉ số còn liên quan, chính xác và không tạo hành vi sai lệch.
10. **Ngừng chỉ số không còn giá trị:** giữ lịch sử cần thiết, thông báo thay đổi định nghĩa và tránh duy trì dashboard không ai sử dụng.

### 15.1. Thay đổi định nghĩa phải có phiên bản

Nếu đổi cách tính pass rate, severity hoặc thời gian phản hồi, cần ghi ngày hiệu lực và tác động đến so sánh lịch sử. Không nên nối dữ liệu được tính theo hai định nghĩa khác nhau mà không đánh dấu.

### 15.2. Có chủ sở hữu cho từng chỉ số

Chủ sở hữu chịu trách nhiệm:

- Duy trì định nghĩa và công thức.
- Xác minh nguồn dữ liệu.
- Theo dõi dữ liệu thiếu hoặc bất thường.
- Giải thích thay đổi và giới hạn.
- Phối hợp với người dùng chỉ số để cập nhật hành động.

Chủ sở hữu không nhất thiết là người tự thu thập mọi dữ liệu; họ bảo đảm chỉ số có ý nghĩa và đáng tin.

## 16. Những sai lầm thường gặp

### 16.1. Chọn chỉ số vì công cụ có sẵn

Một công cụ có thể cung cấp hàng chục biểu đồ nhưng không phải biểu đồ nào cũng hỗ trợ mục tiêu. Bắt đầu từ câu hỏi và chỉ dùng dữ liệu có liên quan.

### 16.2. Dùng một chỉ số đại diện cho chất lượng

Pass rate, coverage, số lỗi hoặc số test không đại diện cho toàn bộ chất lượng. Dùng tập chỉ số cân bằng và diễn giải theo bối cảnh.

### 16.3. Không định nghĩa mẫu số và ngoại lệ

Hai dashboard có thể cùng ghi “90% pass” nhưng một dashboard loại test bị skip, dashboard kia tính chúng là thất bại. Công thức và quy tắc lọc phải được công bố.

### 16.4. So sánh số thô giữa các phạm vi khác nhau

So sánh số lỗi giữa sản phẩm có lượng người dùng, tần suất phát hành và mức kiểm thử khác nhau có thể gây hiểu lầm. Phân đoạn hoặc chuẩn hóa theo đơn vị phù hợp.

### 16.5. Chỉ đo kết quả sau khi sự cố xảy ra

Chỉ số lagging cho biết điều đã xảy ra nhưng có thể quá muộn để can thiệp. Bổ sung chỉ số dẫn dắt về rủi ro, test, độ ổn định và phản hồi.

### 16.6. Không có chỉ số cân bằng

Tối ưu tốc độ mà không theo dõi phạm vi kiểm tra có thể làm tăng rủi ro. Tăng tự động hóa mà không theo dõi bảo trì có thể tạo gánh nặng. Mỗi mục tiêu chính nên có ít nhất một góc nhìn cân bằng phù hợp.

### 16.7. Đặt target tùy ý

Target không có baseline hoặc không thuộc khả năng kiểm soát có thể làm giảm niềm tin. Đo hiện trạng, hiểu biến động và thống nhất mục tiêu thực tế.

### 16.8. Biến chỉ số thành công cụ trừng phạt

Khi số liệu được dùng để xếp hạng hoặc phạt cá nhân, người thực hiện có thể che giấu lỗi, tránh công việc khó hoặc tối ưu con số. Dùng đo lường để cải thiện hệ thống và thảo luận minh bạch.

### 16.9. Duy trì chỉ số không ai dùng

Dashboard lỗi thời tạo chi phí và nhiễu. Rà soát người dùng, quyết định được hỗ trợ và ngừng chỉ số không còn giá trị.

## 17. Danh sách rà soát trước khi đưa chỉ số vào dashboard

Trước khi công bố một chỉ số, hãy kiểm tra:

- [ ] Chỉ số gắn với mục tiêu và câu hỏi cụ thể.
- [ ] Người sử dụng và quyết định được xác định.
- [ ] Tên, định nghĩa, công thức, tử số và mẫu số rõ ràng.
- [ ] Đơn vị, phạm vi và khoảng thời gian được nêu.
- [ ] Quy tắc xử lý retry, skip, blocked, quarantine và dữ liệu thiếu được xác định.
- [ ] Nguồn dữ liệu và chất lượng dữ liệu đã được xác minh.
- [ ] Có baseline trước khi đặt target nếu phù hợp.
- [ ] Có chỉ số cân bằng để phát hiện tác dụng phụ.
- [ ] Có phân đoạn phù hợp nhưng không tạo mẫu quá nhỏ.
- [ ] Dashboard hiển thị số lượng quan sát và xu hướng.
- [ ] Có owner, ngưỡng và hành động khi chỉ số thay đổi.
- [ ] Giới hạn và nguy cơ diễn giải sai được ghi rõ.
- [ ] Định nghĩa có phiên bản và ngày hiệu lực.
- [ ] Chỉ số được rà soát hoặc ngừng khi không còn phục vụ quyết định.

## 18. Kết luận

Chọn chỉ số đo lường cần bắt đầu từ mục tiêu và câu hỏi mà nhóm phải trả lời. Một chuỗi rõ ràng từ mục tiêu đến câu hỏi, chỉ số và hành động giúp tránh dashboard nhiều số nhưng không hỗ trợ quyết định. Chỉ số nên có định nghĩa, công thức, phạm vi, nguồn dữ liệu, chủ sở hữu và giới hạn diễn giải thống nhất.

Một hệ thống đo lường hữu ích kết hợp chỉ số dẫn dắt, chỉ số kết quả và chỉ số cân bằng; xem xét cả rủi ro, tốc độ, độ tin cậy, nguồn lực và chất lượng bằng chứng. Không nên dùng pass rate, coverage, số test hoặc số lỗi như đại diện duy nhất cho chất lượng. Hãy đo baseline, đặt mục tiêu có căn cứ, xem xu hướng trong bối cảnh và gắn mỗi tín hiệu với hành động cụ thể. Khi mục tiêu thay đổi hoặc chỉ số không còn giúp ra quyết định, cần cập nhật hoặc loại bỏ nó. Đo lường tốt không phải thu thập được nhiều số nhất, mà là có đủ thông tin đáng tin để lựa chọn hành động đúng.
