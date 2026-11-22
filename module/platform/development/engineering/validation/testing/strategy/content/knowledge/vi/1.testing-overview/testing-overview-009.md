# Giới hạn của kiểm thử và cách trình bày mức độ tin cậy

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), kết quả kiểm thử là bằng chứng cho thấy hệ thống hoạt động đúng trong những điều kiện đã được kiểm tra. Kết quả đó giúp nhóm đánh giá rủi ro và đưa ra quyết định phát hành, nhưng không thể chứng minh rằng phần mềm hoàn toàn không có lỗi.

Vì vậy, một báo cáo kiểm thử tốt cần làm rõ ba điều: **đã kiểm tra những gì, bằng chứng thu được mạnh đến đâu, và những rủi ro nào vẫn còn tồn tại**. Bài học này trình bày các giới hạn thường gặp và cách diễn đạt mức độ tin cậy sao cho chính xác, có thể kiểm chứng và hữu ích cho người ra quyết định.

## 1. Vì sao kiểm thử không thể chứng minh phần mềm không có lỗi?

### 1.1. Không thể kiểm tra mọi tổ hợp đầu vào và trạng thái

Một chức năng có thể nhận nhiều loại dữ liệu, chịu ảnh hưởng của quyền truy cập, cấu hình, trạng thái trước đó, thời điểm thực thi và tương tác với các dịch vụ khác. Số tổ hợp có thể tăng rất nhanh. Với hệ thống có nhiều thành phần, việc kiểm tra toàn bộ đường đi và trạng thái thường không khả thi.

Nhóm kiểm thử phải chọn các trường hợp đại diện dựa trên yêu cầu và rủi ro. Một trường hợp đã chạy thành công chỉ chứng minh hành vi tương ứng trong điều kiện đó; nó không tự động đại diện cho mọi đầu vào hoặc mọi trạng thái khác.

Ví dụ, kiểm thử chức năng đặt hàng với một sản phẩm còn hàng và một địa chỉ hợp lệ chưa đủ để kết luận luồng đặt hàng an toàn khi sản phẩm vừa hết hàng, địa chỉ không hợp lệ, mã giảm giá hết hạn hoặc hai người dùng cùng mua sản phẩm cuối cùng.

### 1.2. Kết quả mong đợi đôi khi không rõ ràng

Một ca kiểm thử cần có kết quả mong đợi để so sánh với kết quả thực tế. Tuy nhiên, yêu cầu có thể mơ hồ, quy tắc nghiệp vụ có thể chưa được thống nhất hoặc tài liệu có thể không phản ánh hành vi mà người dùng thực sự cần.

Nếu kết quả mong đợi được xác định sai, kiểm thử vẫn có thể chạy xanh dù sản phẩm đang làm sai yêu cầu. Đây là lý do việc xác nhận tiêu chí chấp nhận, quy tắc nghiệp vụ và dữ liệu kiểm thử quan trọng không kém việc viết mã kiểm thử.

### 1.3. Môi trường kiểm thử không hoàn toàn giống môi trường thật

Môi trường kiểm thử có thể khác môi trường sản xuất về phiên bản hệ điều hành, cấu hình, dữ liệu, tải, quyền truy cập, mạng hoặc dịch vụ bên thứ ba. Một tích hợp được thay thế bằng mock cũng không thể phản ánh đầy đủ mọi hành vi của hệ thống thật.

Do đó, kết quả trên môi trường thử nghiệm chỉ hỗ trợ kết luận trong phạm vi môi trường và cấu hình đã nêu. Với những luồng phụ thuộc vào cơ sở dữ liệu, hàng đợi, cổng thanh toán hoặc dịch vụ bên ngoài, cần ghi rõ phần nào đã được kiểm tra với hệ thống thật và phần nào chỉ được mô phỏng.

### 1.4. Một số lỗi chỉ xuất hiện theo thời điểm hoặc mức tải

Lỗi tranh chấp dữ liệu, deadlock, timeout, lỗi mạng chập chờn và lỗi đồng bộ có thể phụ thuộc vào thứ tự thực thi hoặc tải hệ thống. Một lần chạy thành công không đủ để loại trừ những lỗi hiếm gặp này.

Các bài kiểm thử tải, kiểm thử chịu tải, kiểm thử phục hồi và chạy lặp lại giúp tăng bằng chứng cho những thuộc tính đó. Tuy nhiên, chúng vẫn chỉ đại diện cho kịch bản, quy mô và thời lượng đã thực hiện.

### 1.5. Bản thân bộ kiểm thử cũng có thể có lỗi

Ca kiểm thử có thể chứa dữ liệu sai, điều kiện kiểm tra thiếu chặt chẽ hoặc giả lập không phản ánh đúng hành vi thực tế. Một bài kiểm thử flaky (lúc đạt, lúc không đạt trong cùng điều kiện) cũng làm giảm độ tin cậy của kết quả.

Vì vậy, bộ kiểm thử cần được xem như một phần mềm cần bảo trì: có người sở hữu, có tiêu chí đánh giá, có dữ liệu ổn định và có cơ chế điều tra khi kết quả bất thường.

## 2. Phân biệt kết quả đạt, độ bao phủ và mức độ tin cậy

Ba khái niệm này liên quan với nhau nhưng trả lời những câu hỏi khác nhau.

| Khái niệm | Câu hỏi được trả lời | Giới hạn khi diễn giải |
|---|---|---|
| Tỷ lệ kiểm thử đạt | Trong số các ca đã thực thi, có bao nhiêu ca đạt? | Không cho biết các rủi ro quan trọng đã được kiểm tra hay chưa. |
| Độ bao phủ (coverage) | Mã nguồn, nhánh, yêu cầu hoặc luồng nào đã được chạm tới? | Có thực thi một dòng lệnh không đồng nghĩa đã kiểm tra đầy đủ hành vi của dòng lệnh đó. |
| Mức độ tin cậy | Bằng chứng hiện có hỗ trợ kết luận đến mức nào đối với một phạm vi và rủi ro cụ thể? | Phải nêu phạm vi, giả định, bằng chứng và phần chưa được xác minh. |

Ví dụ, độ bao phủ dòng lệnh đạt 100% chỉ cho biết các dòng được đo đã được thực thi. Nó không chứng minh mọi giá trị biên, nhánh nghiệp vụ, lỗi tích hợp hoặc tình huống đồng thời đều đã được kiểm tra. Tương tự, tỷ lệ đạt 99% có thể vẫn là tín hiệu đáng lo nếu ca thất bại nằm ở luồng thanh toán quan trọng.

Không nên dùng riêng một con số để đại diện cho chất lượng hoặc mức độ tin cậy của toàn bộ sản phẩm. Nếu có dùng tỷ lệ, hãy ghi rõ mẫu số, phạm vi và cách tính. Ví dụ: “95/100 ca đã thực thi đạt” rõ ràng hơn “95% chất lượng”.

## 3. Xây dựng mức độ tin cậy từ bằng chứng

Mức độ tin cậy nên được đánh giá theo từng tính năng, luồng nghiệp vụ hoặc thuộc tính chất lượng. Một hệ thống có thể có độ tin cậy cao đối với luồng đăng nhập nhưng chỉ ở mức trung bình đối với xử lý thanh toán hoặc khả năng phục hồi khi mất kết nối.

### 3.1. Xác định phạm vi và rủi ro trước khi kiểm thử

Trước tiên, xác định phiên bản đang đánh giá, yêu cầu liên quan, người dùng bị ảnh hưởng và hậu quả nếu chức năng thất bại. Có thể ưu tiên theo các yếu tố:

- Mức độ nghiêm trọng đối với người dùng hoặc hoạt động kinh doanh.
- Khả năng xảy ra lỗi và tần suất sử dụng chức năng.
- Độ phức tạp của thay đổi và số lượng thành phần phụ thuộc.
- Khả năng phát hiện, khôi phục hoặc giảm thiểu khi lỗi xảy ra.
- Yêu cầu về bảo mật, quyền riêng tư, dữ liệu và tuân thủ.

Các luồng có hậu quả cao cần bằng chứng sâu hơn. Một thay đổi nhỏ trong màn hình ít quan trọng có thể cần phạm vi kiểm thử khác với thay đổi ảnh hưởng đến quyền truy cập hoặc tính toàn vẹn dữ liệu.

### 3.2. Kết hợp nhiều lớp kiểm thử

Mỗi lớp kiểm thử phát hiện một nhóm vấn đề khác nhau:

| Lớp kiểm thử | Bằng chứng chính | Điểm cần lưu ý |
|---|---|---|
| Unit test | Quy tắc và logic của đơn vị nhỏ hoạt động theo kỳ vọng. | Có thể bỏ sót lỗi do kết nối giữa các thành phần. |
| Component test | Một thành phần hoạt động với các phụ thuộc được kiểm soát. | Chất lượng phụ thuộc vào mức độ đại diện của môi trường và test double. |
| Integration test | Các thành phần trao đổi dữ liệu và phối hợp đúng. | Cần kiểm tra giao diện, cấu hình, giao dịch và xử lý lỗi. |
| Contract test | Hai phía của một giao tiếp tuân thủ hợp đồng đã thống nhất. | Không thay thế hoàn toàn kiểm thử đầu cuối với hệ thống thật. |
| End-to-end test | Luồng người dùng đi qua nhiều thành phần hoạt động như dự kiến. | Thường chậm, dễ phụ thuộc môi trường và khó xác định nguyên nhân lỗi. |
| Exploratory test | Người kiểm thử tìm ra hành vi bất ngờ qua việc khám phá có định hướng. | Cần ghi lại mục tiêu, dữ liệu và phát hiện để có thể theo dõi. |
| Non-functional test | Hiệu năng, khả năng chịu tải, bảo mật, khả năng truy cập hoặc phục hồi đáp ứng mục tiêu. | Phải nêu rõ điều kiện, công cụ và giới hạn phép đo. |

Không cần áp dụng mọi lớp với cùng mức độ cho mọi thay đổi. Hãy chọn lớp kiểm thử theo rủi ro và loại lỗi cần phát hiện, đồng thời giải thích các lớp chưa thực hiện nếu chúng có liên quan đến quyết định phát hành.

### 3.3. Thiết kế trường hợp kiểm thử có chủ đích

Một bộ kiểm thử có giá trị cần bao gồm nhiều nhóm tình huống, chẳng hạn:

- Trường hợp thông thường và luồng thành công chính.
- Giá trị biên, dữ liệu trống, dữ liệu sai định dạng và dữ liệu ngoài miền hợp lệ.
- Quyền truy cập hợp lệ và không hợp lệ.
- Trạng thái chuyển tiếp, thao tác lặp lại và yêu cầu trùng lặp.
- Timeout, mất kết nối, dịch vụ phụ thuộc ngừng hoạt động và thử lại.
- Dữ liệu lớn, tải cao hoặc nhiều yêu cầu đồng thời khi phù hợp.
- Khả năng phục hồi và tính nhất quán sau khi xảy ra lỗi.

Có thể dùng phân vùng tương đương, phân tích giá trị biên, bảng quyết định và kiểm thử chuyển trạng thái để chọn trường hợp đại diện. Việc chọn trường hợp nên có lý do rõ ràng, gắn với yêu cầu hoặc rủi ro cụ thể.

### 3.4. Đánh giá độ ổn định và khả năng tái lập

Kết quả chỉ có giá trị khi nhóm có thể tin rằng nó phản ánh hành vi của sản phẩm. Cần theo dõi ca kiểm thử flaky, dữ liệu dùng chung gây ảnh hưởng lẫn nhau, thứ tự chạy, phụ thuộc thời gian và cấu hình môi trường.

Khi một ca kiểm thử thất bại, cần phân loại nguyên nhân: lỗi sản phẩm, lỗi kiểm thử, lỗi môi trường hay lỗi dịch vụ phụ thuộc. Không nên âm thầm bỏ qua hoặc xóa ca kiểm thử chỉ để làm cho pipeline xanh. Nếu phải tạm vô hiệu hóa một ca, hãy ghi rõ lý do, người phụ trách và kế hoạch khôi phục.

### 3.5. Kết hợp bằng chứng sau khi triển khai

Với các rủi ro không thể tái hiện đầy đủ trong môi trường kiểm thử, có thể bổ sung bằng chứng từ triển khai có kiểm soát: theo dõi tỷ lệ lỗi, độ trễ, log, trace, cảnh báo, canary release hoặc cơ chế rollback.

Các tín hiệu sản xuất giúp phát hiện vấn đề thực tế nhưng không thay thế kiểm thử trước phát hành. Cần có ngưỡng theo dõi và người chịu trách nhiệm phản ứng khi tín hiệu vượt ngưỡng.

## 4. Trình bày mức độ tin cậy

Có thể dùng ba mức **Cao**, **Trung bình** và **Thấp** để giao tiếp nhất quán. Đây là cách phân loại phục vụ quyết định của dự án, không phải thang đo phổ quát. Nhóm cần thống nhất tiêu chí áp dụng trước khi sử dụng.

| Mức độ | Khi nào có thể sử dụng | Cách diễn đạt phù hợp |
|---|---|---|
| Cao | Các luồng và rủi ro trọng yếu trong phạm vi đã xác định có bằng chứng từ những lớp kiểm thử phù hợp; môi trường đủ đại diện; kết quả ổn định; không còn lỗi nghiêm trọng chưa xử lý trong phạm vi. | “Mức độ tin cậy cao đối với các luồng đã nêu trên phiên bản và môi trường được kiểm tra. Những rủi ro ngoài phạm vi vẫn cần được theo dõi.” |
| Trung bình | Luồng chính đã được kiểm tra nhưng còn khoảng trống có ý nghĩa, chẳng hạn một số tích hợp chỉ được mô phỏng, kiểm thử phi chức năng chưa đầy đủ hoặc còn lỗi mức trung bình có biện pháp xử lý. | “Mức độ tin cậy trung bình. Các luồng chính đã đạt, nhưng tích hợp với dịch vụ bên ngoài chưa được xác minh đầy đủ.” |
| Thấp | Thiếu bằng chứng cho luồng trọng yếu; môi trường không đại diện; kết quả không ổn định; còn lỗi nghiêm trọng hoặc nhiều tình huống quan trọng chưa được kiểm tra. | “Mức độ tin cậy thấp do luồng quan trọng chưa được xác minh trên môi trường phù hợp. Chưa đủ bằng chứng để khuyến nghị phát hành.” |

Khi đánh giá, hãy xét đồng thời mức độ quan trọng của rủi ro và độ mạnh của bằng chứng. Một khoảng trống nhỏ ở chức năng ít quan trọng có thể chấp nhận được, nhưng một khoảng trống tương tự ở chức năng bảo mật hoặc thanh toán có thể làm thay đổi quyết định.

Không nên gộp các thuộc tính khác nhau thành một mức duy nhất nếu điều đó che khuất rủi ro. Có thể báo cáo riêng mức độ tin cậy về chức năng, hiệu năng, bảo mật và khả năng phục hồi.

## 5. Cấu trúc một báo cáo mức độ tin cậy

Một báo cáo ngắn vẫn cần đủ thông tin để người đọc hiểu kết luận được đưa ra dựa trên điều gì. Nên bao gồm:

1. **Phạm vi:** tính năng, yêu cầu, luồng người dùng, phiên bản hoặc mã build được đánh giá.
2. **Rủi ro trọng yếu:** điều gì có thể xảy ra nếu chức năng lỗi và mức ảnh hưởng.
3. **Bằng chứng:** các lớp kiểm thử đã chạy, số ca đạt/thất bại/bỏ qua và độ bao phủ có liên quan.
4. **Chất lượng bộ kiểm thử:** ca flaky, lỗi môi trường, dữ liệu hoặc giả lập có thể ảnh hưởng kết quả.
5. **Lỗi còn mở:** mức độ nghiêm trọng, ảnh hưởng, cách giảm thiểu và người phụ trách.
6. **Giới hạn:** môi trường, tích hợp, dữ liệu hoặc tình huống chưa được xác minh.
7. **Đánh giá:** mức độ tin cậy, lý do và khuyến nghị hành động tiếp theo.

### Ví dụ minh họa

Giả sử nhóm đánh giá luồng thanh toán của một phiên bản mới:

- Phạm vi: tạo đơn hàng, tính tổng tiền và nhận kết quả thanh toán.
- Bằng chứng: 64 ca kiểm thử đã được lên lịch; 62 ca đạt, 2 ca bị bỏ qua vì môi trường sandbox của nhà cung cấp không khả dụng.
- Đã kiểm tra: unit test cho quy tắc tính tiền, integration test với cơ sở dữ liệu và contract test cho định dạng thông điệp.
- Chưa kiểm tra: luồng đầu cuối với nhà cung cấp thanh toán thật và tình huống callback đến trễ khi có tải cao.
- Lỗi còn mở: không có lỗi nghiêm trọng đã biết trong phạm vi kiểm tra.
- Đánh giá: **Mức độ tin cậy trung bình** đối với luồng thanh toán. Bằng chứng cho logic nội bộ khá đầy đủ, nhưng tích hợp thực tế và hành vi callback khi tải cao chưa được xác minh.

Cách trình bày này cho phép người đọc hiểu vì sao 62 ca đạt chưa đủ để kết luận mức độ tin cậy cao. Nó cũng chỉ ra bước tiếp theo có giá trị nhất: khôi phục môi trường sandbox, chạy kiểm thử đầu cuối và kiểm tra callback trong điều kiện tải phù hợp.

Có thể dùng mẫu sau cho báo cáo thực tế:

~~~text
Phạm vi và phiên bản:
Rủi ro trọng yếu:
Môi trường và dữ liệu:
Các lớp kiểm thử đã thực hiện:
Kết quả: đạt / thất bại / bỏ qua / flaky
Độ bao phủ và cách đo:
Lỗi còn mở:
Giới hạn và giả định:
Mức độ tin cậy: Cao / Trung bình / Thấp
Cơ sở đánh giá:
Khuyến nghị và hành động tiếp theo:
~~~

## 6. Những cách diễn đạt cần tránh

Một số cách báo cáo dễ khiến người đọc hiểu sai bằng chứng:

- **“Không còn lỗi.”** Kiểm thử không thể chứng minh mọi lỗi đã được loại bỏ. Nên nói “Không phát hiện lỗi trong phạm vi và điều kiện đã kiểm tra”.
- **“Coverage 100%, vậy là an toàn.”** Hãy nêu rõ loại coverage, phạm vi đo và các rủi ro chưa được kiểm tra.
- **“Tất cả test đều pass.”** Cần nói thêm số ca đã chạy, số ca bị bỏ qua, ca flaky và các luồng quan trọng có nằm trong phạm vi hay không.
- **“Độ tin cậy 99%.”** Chỉ dùng xác suất khi có mô hình, dữ liệu và phương pháp hiệu chuẩn hỗ trợ con số đó. Nếu không, hãy dùng mức định tính kèm lý do.
- **“Đã kiểm thử đầy đủ.”** Cụm từ này quá rộng. Hãy mô tả yêu cầu, luồng, loại dữ liệu và điều kiện đã kiểm tra.
- **Bỏ qua giới hạn của môi trường.** Nếu dùng mock, dữ liệu giả hoặc sandbox, hãy nêu rõ để người đọc không hiểu nhầm đó là bằng chứng từ hệ thống thật.

Phân biệt rõ **thất bại**, **bỏ qua** và **chưa kiểm tra**. Một ca thất bại là bằng chứng có vấn đề cần điều tra; một ca bị bỏ qua không cung cấp bằng chứng về hành vi; một tình huống chưa kiểm tra là khoảng trống cần được đánh giá theo rủi ro.

## 7. Danh sách rà soát trước khi công bố kết quả

- [ ] Phạm vi, phiên bản và môi trường được ghi rõ.
- [ ] Các luồng có rủi ro cao được liên kết với yêu cầu và bằng chứng kiểm thử.
- [ ] Kết quả đạt, thất bại, bỏ qua và flaky được phân biệt.
- [ ] Loại coverage và cách tính được giải thích.
- [ ] Các mock, test double và tích hợp chưa xác minh được nêu rõ.
- [ ] Lỗi còn mở có mức độ ảnh hưởng và phương án xử lý.
- [ ] Mức độ tin cậy có lý do cụ thể và gắn với phạm vi.
- [ ] Khuyến nghị tiếp theo giúp giảm khoảng trống rủi ro lớn nhất.

## Kết luận

Kiểm thử làm giảm sự không chắc chắn bằng cách tạo ra bằng chứng có thể kiểm tra lại. Mức độ tin cậy chỉ có ý nghĩa khi gắn với một phạm vi cụ thể, rủi ro đã xác định, chất lượng bộ kiểm thử và những giới hạn còn tồn tại. Khi báo cáo cả điều đã biết lẫn điều chưa được xác minh, nhóm phát triển, kiểm thử và người ra quyết định có thể lựa chọn bước tiếp theo dựa trên rủi ro thực tế thay vì một con số dễ gây hiểu nhầm.
