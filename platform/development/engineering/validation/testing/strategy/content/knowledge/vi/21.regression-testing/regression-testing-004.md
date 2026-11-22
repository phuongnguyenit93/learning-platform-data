# Ưu tiên ca theo rủi ro, vùng thay đổi và lịch sử lỗi

**Chương:** Hồi quy  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Một bộ kiểm thử hồi quy có thể chứa hàng trăm hoặc hàng nghìn ca. Khi sản phẩm thay đổi, nhóm thường không có đủ thời gian và tài nguyên để chạy toàn bộ bộ kiểm thử ở mọi commit hoặc mọi bản dựng. Nếu chỉ chọn những ca chạy nhanh, nhóm có thể bỏ qua các luồng quan trọng. Nếu chạy mọi ca theo thứ tự cố định, lỗi nghiêm trọng có thể chỉ được phát hiện sau thời gian chờ dài.

Ưu tiên ca kiểm thử là cách chọn và sắp xếp các ca dựa trên bằng chứng về rủi ro. Ba nguồn thông tin đặc biệt hữu ích là **rủi ro nghiệp vụ**, **vùng thay đổi của phần mềm** và **lịch sử lỗi**. Rủi ro cho biết điều gì sẽ gây hậu quả lớn nếu hỏng; vùng thay đổi cho biết thành phần hoặc hành vi nào có khả năng bị ảnh hưởng bởi lần sửa hiện tại; lịch sử lỗi cho biết những điểm yếu nào từng xuất hiện và có thể tái diễn.

Ưu tiên tốt cần trả lời hai câu hỏi khác nhau: ca nào cần được chọn vào tập kiểm thử của lần chạy này, và trong tập đã chọn thì ca nào nên chạy trước. Chọn đúng phạm vi giúp tiết kiệm tài nguyên; sắp xếp đúng thứ tự giúp phát hiện lỗi quan trọng sớm hơn. Hai quyết định có liên quan nhưng không giống nhau.

Sau bài học, người học có thể:

- Phân biệt lựa chọn ca kiểm thử với sắp xếp thứ tự thực thi.
- Đánh giá rủi ro của chức năng, luồng nghiệp vụ và thành phần kỹ thuật.
- Xác định vùng thay đổi và mối liên hệ giữa thay đổi với ca kiểm thử.
- Dùng lịch sử lỗi để nhận diện khu vực dễ phát sinh lỗi và kiểm tra hồi quy.
- Xây dựng tiêu chí, thang điểm và quy tắc ưu tiên có thể giải thích.
- Chọn tập kiểm thử phù hợp với thời gian, tài nguyên và mức rủi ro.
- Theo dõi hiệu quả của chiến lược và cập nhật khi sản phẩm thay đổi.

## 1. Vì sao cần ưu tiên ca kiểm thử hồi quy?

Kiểm thử hồi quy xác minh rằng thay đổi mới không làm hỏng hành vi đã hoạt động trước đó. Một thay đổi nhỏ vẫn có thể ảnh hưởng đến thành phần dùng chung, hợp đồng API, cấu hình, dữ liệu hoặc luồng nghiệp vụ ở nơi khác.

Trong thực tế, bộ kiểm thử có thể vượt quá giới hạn thời gian của pipeline. Một số ca cần môi trường tích hợp, dữ liệu lớn hoặc dịch vụ ngoài. Một số ca chỉ chạy được theo lịch vì chi phí cao. Nếu không có chiến lược ưu tiên, nhóm thường gặp một trong các vấn đề:

- Chạy toàn bộ suite quá lâu, làm chậm phản hồi và phát hành.
- Chỉ chạy smoke test quá nhỏ, bỏ sót lỗi trong vùng thay đổi.
- Chạy cùng một nhóm test theo thứ tự cố định dù rủi ro của từng lần thay đổi khác nhau.
- Không đưa các ca từng phát hiện lỗi nghiêm trọng vào bộ hồi quy bắt buộc.
- Dành nhiều thời gian cho test ít giá trị trong khi các luồng có tác động lớn chưa được kiểm tra.
- Không biết vì sao một ca được chọn hoặc bị bỏ qua.

Ưu tiên không nhằm giảm kiểm thử một cách tùy tiện. Mục tiêu là dùng nguồn lực sẵn có để tạo bằng chứng có giá trị cao nhất cho thay đổi đang xét, đồng thời bảo đảm các rủi ro bắt buộc vẫn được kiểm tra.

## 2. Phân biệt lựa chọn và sắp xếp thứ tự

Hai hoạt động thường được gọi chung là test prioritization nhưng giải quyết hai vấn đề khác nhau.

### 2.1. Lựa chọn ca kiểm thử (test selection)

Lựa chọn xác định tập ca nào sẽ được thực thi trong một lần chạy. Ví dụ, một thay đổi chỉ liên quan đến tính phí vận chuyển có thể kích hoạt các ca về tính phí, tạo đơn, tổng tiền, hoàn tiền và các thành phần dùng chung liên quan.

Lựa chọn cần trả lời:

- Ca nào kiểm tra trực tiếp vùng thay đổi?
- Ca nào kiểm tra thành phần phụ thuộc hoặc hành vi có thể bị ảnh hưởng gián tiếp?
- Ca nào bảo vệ rủi ro nghiệp vụ nghiêm trọng?
- Ca nào là bắt buộc theo chính sách hoặc cam kết?
- Ca nào có thể hoãn sang bộ kiểm thử mở rộng mà không tạo rủi ro không chấp nhận được?

### 2.2. Sắp xếp thứ tự ca kiểm thử (test ordering/prioritization)

Sắp xếp thứ tự quyết định ca nào chạy trước trong tập đã chọn. Ví dụ, nếu chỉ có 15 phút trước khi tạo bản dựng ứng viên, nhóm có thể chạy trước các ca kiểm tra đăng nhập, tạo đơn, thanh toán và quyền truy cập; các ca ít quan trọng hơn chạy sau.

Sắp xếp thứ tự cần trả lời:

- Ca nào có khả năng phát hiện lỗi sớm?
- Ca nào bảo vệ hậu quả nghiêm trọng?
- Ca nào chạy nhanh và cung cấp tín hiệu đáng tin cậy?
- Ca nào cần dữ liệu hoặc môi trường đang sẵn sàng?
- Có phụ thuộc thứ tự hoặc tài nguyên khiến một số ca không thể chạy song song không?

### 2.3. Ví dụ phân biệt

Giả sử thay đổi mã tính chiết khấu:

- **Lựa chọn:** chọn unit test tính chiết khấu, integration test lưu tổng tiền, API test tạo đơn, E2E thanh toán và các ca hoàn tiền có dùng lại tổng tiền.
- **Sắp xếp:** chạy unit test tính chiết khấu trước vì nhanh và kiểm tra trực tiếp; tiếp theo là integration/API test; sau đó chạy E2E thanh toán và hoàn tiền.

Một ca có thể không được chọn vào tập chạy nhanh nhưng vẫn có thứ tự ưu tiên cao trong bộ kiểm thử mở rộng. Vì vậy, cần ghi nhận riêng tiêu chí chọn và tiêu chí sắp xếp.

## 3. Ba nguồn thông tin chính để ưu tiên

### 3.1. Rủi ro nghiệp vụ và kỹ thuật

Rủi ro phản ánh khả năng xảy ra lỗi và hậu quả nếu lỗi xuất hiện. Một chức năng có tần suất sử dụng thấp vẫn có thể có rủi ro cao nếu liên quan đến tiền, dữ liệu nhạy cảm, phân quyền hoặc nghĩa vụ pháp lý.

Các yếu tố thường xem xét:

- Mức độ nghiêm trọng của hậu quả.
- Khả năng hoặc tần suất xảy ra lỗi.
- Số lượng người dùng, giao dịch hoặc hệ thống bị ảnh hưởng.
- Khả năng phát hiện lỗi trước khi đến người dùng.
- Độ phức tạp và mức độ thay đổi của thành phần.
- Mức phụ thuộc và số ranh giới tích hợp.
- Khả năng khôi phục hoặc giảm thiểu khi lỗi xảy ra.

### 3.2. Vùng thay đổi (change scope/impact)

Vùng thay đổi là phần mã, cấu hình, dữ liệu, hợp đồng hoặc hành vi bị tác động bởi một commit, pull request, migration hay bản phát hành. Thay đổi trực tiếp có thể ảnh hưởng đến các thành phần gọi nó, thành phần nó gọi, dữ liệu dùng chung và luồng nghiệp vụ đi qua.

Thông tin có thể dùng:

- Danh sách file, package, module hoặc service được sửa.
- Đường đi gọi hàm và đồ thị phụ thuộc.
- API, event schema, database schema hoặc cấu hình thay đổi.
- Yêu cầu, user story và tiêu chí chấp nhận liên quan.
- Thành phần tiêu thụ hoặc cung cấp hợp đồng bị thay đổi.
- Kiến thức của người phát triển và reviewer về phạm vi ảnh hưởng.

Chỉ nhìn file diff là chưa đủ. Một thay đổi trong thư viện dùng chung có thể ảnh hưởng đến nhiều module dù chỉ một file được sửa. Ngược lại, một file có thể chứa nhiều chức năng độc lập nên không phải mọi test của file đều liên quan.

### 3.3. Lịch sử lỗi (defect history)

Lịch sử lỗi cho biết những loại lỗi, thành phần và điều kiện nào từng gây sự cố. Thông tin hữu ích gồm:

- Lỗi đã xuất hiện ở module hoặc luồng nào.
- Mức độ nghiêm trọng và phạm vi ảnh hưởng.
- Tần suất tái diễn hoặc số lần phát hiện trong các phiên bản.
- Lỗi được phát hiện ở tầng nào: unit, integration, system, UAT hay production.
- Nguyên nhân gốc và điều kiện kích hoạt.
- Ca kiểm thử nào đã phát hiện hoặc đáng lẽ có thể phát hiện.
- Thay đổi nào thường đi kèm lỗi.

Lịch sử lỗi không phải dự báo chắc chắn. Một module có nhiều lỗi được ghi nhận có thể đơn giản là được kiểm thử nhiều hơn. Cần xem xét mức độ quan sát, quy mô, độ phức tạp và số lần thay đổi khi so sánh.

## 4. Đánh giá rủi ro để xác định mức ưu tiên

Rủi ro cần được đánh giá theo tác động của lỗi đối với sản phẩm và người dùng. Có thể dùng thang định tính hoặc bán định lượng để giúp nhóm thảo luận nhất quán.

### 4.1. Mức độ nghiêm trọng (impact/severity)

Ví dụ một thang 1–5:

| Điểm | Mức độ | Ví dụ tác động |
|---:|---|---|
| 1 | Rất thấp | Lỗi hiển thị nhỏ, có cách khắc phục đơn giản, không ảnh hưởng dữ liệu |
| 2 | Thấp | Một chức năng phụ bị ảnh hưởng, phạm vi người dùng hẹp |
| 3 | Trung bình | Một luồng nghiệp vụ bị gián đoạn nhưng có phương án thay thế |
| 4 | Cao | Ảnh hưởng luồng chính, dữ liệu hoặc nhiều người dùng; khôi phục tốn công |
| 5 | Rất cao | Rủi ro tài chính, bảo mật, mất dữ liệu, an toàn hoặc vi phạm nghĩa vụ nghiêm trọng |

Thang điểm phải được điều chỉnh theo miền nghiệp vụ. Với hệ thống thanh toán, sai lệch nhỏ về số tiền có thể nghiêm trọng hơn một lỗi giao diện lớn ở trang giới thiệu.

### 4.2. Khả năng xảy ra (likelihood)

Đánh giá khả năng lỗi dựa trên:

- Độ phức tạp của logic và số nhánh.
- Tần suất thay đổi của thành phần.
- Số lượng phụ thuộc và ranh giới tích hợp.
- Độ trưởng thành của implementation.
- Số lần lỗi tương tự từng xảy ra.
- Mức biến thiên của dữ liệu và tải.
- Bằng chứng từ giám sát và sự cố thực tế.

Không nên đánh đồng “đã từng xảy ra nhiều” với xác suất trong tương lai nếu điều kiện đã thay đổi. Sau khi nguyên nhân được sửa triệt để, mức khả năng có thể giảm; tuy nhiên, ca hồi quy vẫn có thể cần giữ để bảo vệ thay đổi sau này.

### 4.3. Mức phơi nhiễm (exposure)

Mức phơi nhiễm phản ánh số lượng hoặc tỷ lệ người dùng, giao dịch, tenant hay hệ thống có thể chịu ảnh hưởng. Một lỗi có hậu quả vừa phải nhưng xuất hiện ở mọi giao dịch có thể cần ưu tiên cao hơn lỗi nghiêm trọng nhưng chỉ ảnh hưởng một cấu hình hiếm.

### 4.4. Khả năng phát hiện và phục hồi

Một lỗi dễ phát hiện qua giám sát và có thể tự phục hồi có thể có mức rủi ro vận hành khác với lỗi âm thầm làm sai dữ liệu. Hãy xem xét:

- Có test, cảnh báo hoặc đối soát phát hiện lỗi không?
- Người dùng có nhận biết sai lệch không?
- Có thể rollback hoặc khôi phục dữ liệu không?
- Lỗi có thể lan sang hệ thống phụ thuộc trước khi phát hiện không?

### 4.5. Điểm rủi ro tham khảo

Một mô hình đơn giản có thể dùng:

\[
R = I \times L \times E
\]

Trong đó:

- (I): mức độ tác động.
- (L): khả năng xảy ra.
- (E): mức phơi nhiễm.

Mỗi yếu tố có thể chấm từ 1 đến 5, nên điểm tham khảo nằm trong khoảng 1–125. Nhóm có thể đặt ngưỡng để phân loại thấp, trung bình, cao và rất cao.

Điểm số chỉ hỗ trợ so sánh, không phải xác suất toán học chính xác. Một rủi ro bảo mật hoặc nghĩa vụ bắt buộc không được hạ ưu tiên chỉ vì điểm tổng thấp. Cần có quy tắc ưu tiên bắt buộc cho các rủi ro nghiêm trọng, bên cạnh điểm số.

## 5. Phân tích vùng thay đổi và tác động

Để chọn ca phù hợp với một thay đổi cụ thể, cần xây dựng đường liên hệ từ thay đổi đến hành vi có thể bị ảnh hưởng.

### 5.1. Bắt đầu từ mô tả thay đổi

Đọc mục tiêu thay đổi, yêu cầu và tiêu chí chấp nhận. Xác định:

- Hành vi nào được thêm, sửa hoặc loại bỏ?
- Dữ liệu đầu vào hoặc đầu ra có thay đổi không?
- Có thay đổi hợp đồng API, event hoặc schema không?
- Có thay đổi quyền, cấu hình, timeout hoặc cơ chế bảo mật không?
- Có migration, cập nhật thư viện hoặc thay đổi hạ tầng không?

Mô tả thay đổi bằng ngôn ngữ nghiệp vụ giúp tránh chỉ chọn test dựa trên tên file.

### 5.2. Xác định thành phần bị tác động trực tiếp

Từ diff, xác định package, class, service, endpoint, bảng dữ liệu hoặc cấu hình được sửa. Liên kết chúng với test tương ứng thông qua tên module, tag, metadata hoặc traceability matrix.

Ví dụ, thay đổi `DiscountCalculator` có thể liên quan trực tiếp đến unit test tính chiết khấu. Nếu thay đổi cách lưu tổng tiền, cần thêm integration test cho persistence và API test cho kết quả trả về.

### 5.3. Mở rộng đến phụ thuộc và consumer

Thay đổi có thể ảnh hưởng gián tiếp đến:

- Thành phần gọi API hoặc phương thức đã thay đổi.
- Thành phần được gọi bởi logic đã thay đổi.
- Consumer của event hoặc message schema.
- Bảng dữ liệu, index, constraint và báo cáo sử dụng dữ liệu.
- Cache, hàng đợi, tác vụ nền và quy trình đối soát.
- Luồng người dùng đi qua nhiều service.

Đồ thị phụ thuộc, sơ đồ kiến trúc và danh sách consumer giúp mở rộng phạm vi có căn cứ. Nếu không có bản đồ đầy đủ, cần kết hợp tìm kiếm mã nguồn, trao đổi với người sở hữu và kiểm thử ở tầng tích hợp.

### 5.4. Xác định mức tác động

Có thể phân loại test theo quan hệ với thay đổi:

| Mức liên quan | Ý nghĩa | Ví dụ |
|---|---|---|
| Trực tiếp | Kiểm tra hành vi hoặc thành phần được sửa | Unit test cho hàm vừa thay đổi |
| Phụ thuộc gần | Kiểm tra thành phần gọi hoặc được gọi bởi phần thay đổi | API test gọi service đã cập nhật |
| Liên quan dữ liệu/hợp đồng | Kiểm tra schema, persistence hoặc consumer | Integration test đọc/ghi bảng đã migration |
| Liên quan luồng nghiệp vụ | Kiểm tra hành trình có đi qua phần thay đổi | E2E tạo và thanh toán đơn hàng |
| Không liên quan rõ ràng | Chưa có bằng chứng về mối liên hệ | Test báo cáo độc lập với thay đổi |

“Không liên quan rõ ràng” không có nghĩa là không có rủi ro. Một thay đổi thư viện hoặc thành phần dùng chung có thể có phạm vi rộng hơn diff trực tiếp.

### 5.5. Phân tích tác động khi thiếu traceability

Nếu test không được liên kết với yêu cầu hoặc thành phần, nhóm có thể dùng:

- Tìm kiếm tham chiếu đến API, class, event hoặc bảng đã đổi.
- Phân tích đồ thị gọi và phụ thuộc của build.
- Tìm tag hoặc tên suite có liên quan.
- Xem lịch sử thay đổi và lỗi ở module.
- Hỏi reviewer hoặc chủ sở hữu thành phần.
- Chạy một tập smoke/integration rộng hơn để giảm rủi ro chưa biết.

Đây là cơ sở để xây dựng traceability tốt hơn về sau. Không nên giả định công cụ phân tích diff luôn xác định đầy đủ tác động nghiệp vụ.

## 6. Sử dụng lịch sử lỗi để ưu tiên

Lịch sử lỗi giúp nhận diện những khu vực có xu hướng phát sinh lỗi và những điều kiện từng bị bỏ sót.

### 6.1. Thu thập dữ liệu lỗi

Các trường thông tin hữu ích:

- Mã lỗi và phiên bản phát hiện.
- Module, service, file hoặc luồng nghiệp vụ liên quan.
- Mức độ nghiêm trọng và số người dùng bị ảnh hưởng.
- Nguyên nhân gốc và điều kiện kích hoạt.
- Tầng phát hiện: unit, integration, system, UAT hay production.
- Thay đổi gây lỗi và thay đổi sửa lỗi.
- Ca kiểm thử đã phát hiện hoặc được bổ sung sau sự cố.
- Số lần tái diễn và trạng thái khắc phục.

Chuẩn hóa tên module, nhóm lỗi và mức nghiêm trọng trước khi thống kê. Gộp các bản ghi trùng khi cùng một sự cố được báo cáo ở nhiều hệ thống, nhưng giữ số lần xảy ra riêng nếu đang phân tích tần suất ảnh hưởng.

### 6.2. Tìm xu hướng theo thành phần và loại lỗi

Nhóm có thể xem:

- Module có số lỗi nghiêm trọng cao.
- Thành phần có lỗi tái diễn sau nhiều lần sửa.
- Khu vực thường phát hiện lỗi muộn ở UAT hoặc production.
- Loại lỗi xuất hiện nhiều: phân quyền, làm tròn, đồng bộ, migration, timeout, null hoặc xử lý sự kiện lặp.
- Ranh giới tích hợp thường xuyên thay đổi hoặc gây lỗi.

Số lượng thô cần được đặt trong bối cảnh. Một module lớn có nhiều thay đổi có thể có nhiều lỗi hơn module nhỏ. Nếu có dữ liệu, hãy xem số lỗi theo số thay đổi, quy mô hoặc mức độ sử dụng.

### 6.3. Giữ ca hồi quy gắn với lỗi lịch sử

Khi lỗi được sửa, cần bổ sung ca tái hiện điều kiện đã gây lỗi. Nếu nguyên nhân có thể ảnh hưởng nhiều tình huống, thêm các biến thể lân cận phù hợp.

Ví dụ, lỗi tính tiền do làm tròn ở đơn hàng nhiều dòng có thể dẫn đến:

- Ca với một dòng hàng và giá trị nguyên.
- Ca với nhiều dòng hàng tạo phần thập phân.
- Ca ở ngay dưới, đúng tại và ngay trên ranh giới làm tròn.
- Ca có thuế và chiết khấu theo thứ tự nghiệp vụ.
- Ca xác minh tổng tiền lưu trữ và payload gửi sang cổng thanh toán.

Không nhất thiết mọi biến thể đều cần E2E. Có thể kiểm tra chi tiết bằng unit test và giữ một luồng tích hợp đại diện.

### 6.4. Đánh giá độ mới và tính liên quan của lịch sử

Lỗi cũ có thể ít liên quan nếu kiến trúc hoặc quy tắc đã thay đổi. Ngược lại, một lỗi xảy ra lâu trước nhưng nguyên nhân nền tảng vẫn tồn tại có thể vẫn quan trọng.

Hãy đánh giá:

- Nguyên nhân đã được loại bỏ hay chỉ giảm triệu chứng?
- Thành phần hoặc thư viện còn được sử dụng không?
- Quy trình hoặc cấu hình đã thay đổi chưa?
- Lỗi có liên quan đến vùng thay đổi hiện tại không?
- Test hồi quy hiện tại còn chạy và kiểm tra đúng điều kiện không?

Không nên tự động giảm điểm của lỗi chỉ vì nó đã cũ. Cần dựa vào trạng thái nguyên nhân và bối cảnh hiện tại.

## 7. Kết hợp ba nguồn thành tiêu chí ưu tiên

Rủi ro, vùng thay đổi và lịch sử lỗi bổ sung cho nhau:

- Rủi ro cho biết hậu quả nếu hành vi hỏng.
- Vùng thay đổi cho biết khả năng lần sửa hiện tại ảnh hưởng đến hành vi nào.
- Lịch sử lỗi cho biết nơi nào từng thất bại và điều kiện nào dễ bị bỏ sót.

Một ca có thể được ưu tiên cao khi nó kiểm tra luồng có hậu quả lớn, đi qua thành phần vừa thay đổi và đã từng có lỗi tương tự.

### 7.1. Ma trận tiêu chí

| Tiêu chí | Câu hỏi đánh giá | Nguồn bằng chứng |
|---|---|---|
| Rủi ro nghiệp vụ | Hành vi hỏng gây hậu quả lớn đến đâu? | Phân tích tác động, yêu cầu, chủ sở hữu nghiệp vụ |
| Liên quan thay đổi | Test có kiểm tra trực tiếp hoặc gián tiếp vùng thay đổi không? | Diff, đồ thị phụ thuộc, traceability |
| Lịch sử lỗi | Thành phần hoặc điều kiện có từng gây lỗi nghiêm trọng/tái diễn không? | Bug tracker, incident review, lịch sử sửa lỗi |
| Khả năng phát hiện | Test có thể phát hiện lỗi sớm và rõ ràng không? | Kết quả thực thi, chất lượng oracle |
| Chi phí thực thi | Thời gian và tài nguyên cần bao nhiêu? | Thời gian chạy, chi phí môi trường |
| Độ tin cậy | Test có ổn định và có thể tái lập không? | Tỷ lệ flaky, dữ liệu và môi trường |

### 7.2. Điểm ưu tiên tham khảo

Có thể xây dựng điểm tham khảo như sau:

\[
P = w_rR + w_cC + w_hH + w_dD - w_tT - w_fF
\]

Trong đó:

- (R): mức rủi ro nghiệp vụ.
- (C): mức liên quan đến vùng thay đổi.
- (H): mức liên quan đến lịch sử lỗi.
- (D): khả năng phát hiện lỗi có giá trị.
- (T): chi phí hoặc thời gian chạy đã chuẩn hóa.
- (F): mức thiếu ổn định đã chuẩn hóa.
- (w): trọng số do nhóm thống nhất.

Đây là mô hình hỗ trợ xếp hạng, không phải công thức chuẩn bắt buộc. Nhóm có thể dùng thang 1–5 cho từng tiêu chí, xác định trọng số theo mục tiêu và kiểm tra kết quả với các quyết định thực tế. Cần tránh tạo ra cảm giác chính xác giả từ các con số chủ quan.

### 7.3. Dùng quy tắc bắt buộc bên cạnh điểm số

Một số ca không được loại khỏi lần chạy chỉ vì điểm tổng thấp:

- Kiểm tra bảo mật hoặc quyền truy cập bắt buộc.
- Kiểm tra dữ liệu và giao dịch có hậu quả nghiêm trọng.
- Ca xác minh migration hoặc tương thích dữ liệu quan trọng.
- Ca smoke xác nhận hệ thống có thể khởi động và thực hiện nhiệm vụ tối thiểu.
- Ca được yêu cầu bởi hợp đồng, quy định hoặc quy trình phát hành.

Hãy xác định danh sách bắt buộc riêng, sau đó dùng điểm ưu tiên để chọn và sắp xếp phần còn lại.

## 8. Chọn tập kiểm thử theo ngân sách thời gian

Khi có giới hạn thời gian, nhóm cần chọn một tập test có giá trị cao trong ngân sách. Đây là bài toán tối ưu thực tế: mỗi test có chi phí chạy, rủi ro được kiểm tra và mức độ trùng lặp bao phủ.

### 8.1. Phân tầng bộ hồi quy

Một cách tổ chức phổ biến:

| Nhóm | Phạm vi | Thời điểm chạy |
|---|---|---|
| Smoke | Khả năng khởi động và một số luồng tối thiểu | Sau build/deploy hoặc mỗi commit quan trọng |
| Fast regression | Unit, API và integration test nhanh cho vùng thay đổi | Mỗi pull request hoặc commit |
| Risk-focused regression | Ca có rủi ro cao, phụ thuộc gần và lịch sử lỗi liên quan | Trước merge hoặc trước release candidate |
| Full regression | Bộ kiểm thử rộng trên nhiều luồng, vai trò và cấu hình | Theo lịch hoặc trước phát hành lớn |
| Specialized | Hiệu năng, bảo mật, phục hồi, tương thích hoặc tải | Theo kế hoạch và rủi ro riêng |

Tên nhóm có thể khác giữa các tổ chức. Điều quan trọng là tiêu chí vào từng nhóm và thời điểm chạy được công bố.

### 8.2. Chọn test theo vùng tác động

Với mỗi thay đổi:

1. Liệt kê thành phần và hành vi trực tiếp bị sửa.
2. Xác định consumer, dependency và dữ liệu liên quan.
3. Tìm test gắn với các thành phần hoặc yêu cầu đó.
4. Bổ sung ca rủi ro cao và ca có lịch sử lỗi liên quan.
5. Giữ các ca bắt buộc của bộ smoke hoặc release gate.
6. Đánh giá khoảng trống chưa có test hoặc chưa có liên kết rõ.

Nếu phạm vi thay đổi không rõ hoặc chạm thành phần dùng chung, mở rộng tập test thay vì giả định tác động hẹp.

### 8.3. Tránh chọn quá nhiều ca trùng lặp

Nhiều test có thể kiểm tra cùng một hành vi ở cùng tầng và cùng dữ liệu. Trùng lặp không phải lúc nào cũng xấu: cùng một quy tắc có thể cần được xác minh ở unit và E2E vì hai tầng chứng minh điều khác nhau. Nhưng nhiều test gần như giống nhau, có cùng oracle và không bổ sung rủi ro mới sẽ làm tăng chi phí.

Hãy xem xét mức bao phủ yêu cầu, rủi ro và thành phần để chọn tập đại diện. Không nên loại bỏ test chỉ vì cùng tên tính năng nếu chúng kiểm tra vai trò, trạng thái hoặc ranh giới khác nhau.

### 8.4. Xử lý giới hạn thời gian

Nếu pipeline chỉ có một khoảng thời gian cố định:

- Chạy các ca bắt buộc trước.
- Chạy ca trực tiếp vùng thay đổi và rủi ro cao tiếp theo.
- Ưu tiên ca phát hiện lỗi sớm với chi phí hợp lý.
- Chạy các ca dài hoặc môi trường đắt tiền sau đó hoặc theo lịch.
- Ghi rõ ca chưa chạy và rủi ro còn lại.

Không được báo cáo toàn bộ hồi quy đạt nếu chỉ một phần suite đã chạy. Báo cáo cần nêu tập được chọn, lý do chọn và phạm vi chưa xác minh.

## 9. Sắp xếp thứ tự thực thi

Sau khi chọn tập test, nhóm có thể sắp xếp để phát hiện lỗi quan trọng sớm.

### 9.1. Các yếu tố sắp xếp

- Mức rủi ro của hành vi được kiểm tra.
- Mức liên quan trực tiếp đến thay đổi.
- Lịch sử phát hiện lỗi của test.
- Khả năng phát hiện lỗi nghiêm trọng.
- Thời gian chạy.
- Độ ổn định và tỷ lệ flaky.
- Phụ thuộc dữ liệu hoặc môi trường.
- Khả năng chạy song song an toàn.

Một test chạy nhanh và có khả năng phát hiện lỗi cao thường nên chạy sớm. Tuy nhiên, không nên đẩy mọi test dài xuống cuối nếu chúng bảo vệ rủi ro bắt buộc.

### 9.2. Ưu tiên theo khả năng phát hiện lỗi sớm

Một chỉ số đơn giản có thể xem xét là:

\[
\text{Hiệu quả phát hiện tham khảo} = \frac{\text{Mức giá trị phát hiện lỗi}}{\text{Thời gian chạy}}
\]

Chỉ số này có thể giúp xếp thứ tự trong một nhóm test tương đương. Nó không nên thay thế mức rủi ro: test 1 phút phát hiện lỗi giao diện nhỏ không nhất thiết phải chạy trước test 4 phút bảo vệ dữ liệu thanh toán.

### 9.3. Giữ các phụ thuộc thứ tự hợp lệ

Nếu test cần dữ liệu được tạo bởi fixture hoặc môi trường cụ thể, hãy khai báo phụ thuộc rõ. Tốt hơn, mỗi test nên tự chuẩn bị dữ liệu để có thể chạy độc lập. Không nên dùng thứ tự ưu tiên để che giấu phụ thuộc ngầm giữa các test.

### 9.4. Chạy song song có kiểm soát

Có thể chạy song song các test độc lập để rút ngắn thời gian. Trước khi tăng mức song song, kiểm tra:

- Dữ liệu và tài khoản có được cô lập không?
- Test có ghi vào cùng tài nguyên không?
- Phụ thuộc ngoài có quota hoặc giới hạn tốc độ không?
- Runner có đủ CPU, bộ nhớ và kết nối không?
- Kết quả có giữ được thứ tự và thông tin tương quan không?

Một bộ test chạy song song nhanh hơn nhưng flaky hơn có thể làm giảm giá trị của tín hiệu. Cần cân bằng tốc độ và độ tin cậy.

## 10. Ví dụ: ưu tiên hồi quy cho thay đổi tính phí đơn hàng

Giả sử một pull request thay đổi cách tính phí vận chuyển và áp dụng chiết khấu theo khu vực. Hệ thống có các chức năng tạo đơn, thanh toán, hủy, hoàn tiền và báo cáo doanh thu.

### 10.1. Xác định vùng thay đổi

Thay đổi tác động trực tiếp đến:

- Hàm tính phí vận chuyển.
- Quy tắc áp dụng chiết khấu theo khu vực.
- Tổng tiền đơn hàng được lưu.

Tác động gián tiếp có thể gồm:

- API xem trước đơn hàng.
- Payload gửi cổng thanh toán.
- Hủy đơn và hoàn tiền.
- Báo cáo doanh thu dùng tổng tiền đã lưu.

### 10.2. Xem xét rủi ro và lịch sử lỗi

Giả sử lịch sử cho thấy từng có lỗi làm tròn khi đơn hàng có nhiều dòng và lỗi áp dụng sai khu vực khi địa chỉ thiếu mã vùng. Tổng tiền sai có thể ảnh hưởng trực tiếp đến giao dịch và hoàn tiền nên mức tác động cao.

### 10.3. Chọn các ca

| Ca kiểm thử | Rủi ro | Liên quan thay đổi | Lịch sử lỗi | Chi phí | Quyết định |
|---|---|---|---|---|---|
| Unit tính phí theo khu vực | Cao | Trực tiếp | Có lỗi tương tự | Thấp | Bắt buộc, chạy sớm |
| Unit giá trị biên và làm tròn | Cao | Trực tiếp | Có lỗi tương tự | Thấp | Bắt buộc, chạy sớm |
| Integration lưu tổng tiền | Cao | Trực tiếp | Từng có sai lệch dữ liệu | Trung bình | Chọn |
| API xem trước đơn hàng | Cao | Gần | Có liên quan | Trung bình | Chọn |
| E2E tạo đơn và thanh toán | Rất cao | Luồng liên quan | Có sự cố tổng tiền | Cao | Chọn vào risk-focused suite |
| E2E hoàn tiền | Cao | Gián tiếp | Có liên quan tổng tiền | Cao | Chọn nếu thay đổi ảnh hưởng dữ liệu hoàn tiền; nếu chưa rõ, rà soát thêm |
| Báo cáo doanh thu hàng tháng | Trung bình | Dữ liệu liên quan | Chưa có lỗi gần đây | Cao | Đưa vào full regression hoặc kiểm tra dữ liệu theo phạm vi |
| Thay đổi ảnh đại diện người dùng | Thấp | Không liên quan rõ | Không liên quan | Thấp | Không chọn cho tập tác động hẹp |

### 10.4. Sắp xếp thực thi

Một thứ tự khả thi:

1. Unit test công thức và giá trị biên.
2. Integration test lưu/đọc lại tổng tiền.
3. API test xem trước và tạo đơn.
4. E2E tạo đơn và thanh toán sandbox.
5. E2E hủy/hoàn tiền nếu vùng thay đổi có ảnh hưởng đến quy tắc hoàn tiền.
6. Kiểm tra báo cáo doanh thu trong bộ hồi quy mở rộng.

Nếu unit test thất bại, nhóm nhận tín hiệu sớm và có thể dừng một số test phụ thuộc. Nếu unit test đạt nhưng integration thất bại, điều tra mapping hoặc persistence. E2E cung cấp bằng chứng về luồng tích hợp.

### 10.5. Ghi nhận phần chưa chạy

Nếu giới hạn thời gian khiến báo cáo doanh thu chưa được kiểm tra, cần ghi rõ lý do và rủi ro còn lại. Chủ sở hữu phát hành quyết định liệu kiểm tra đó phải hoàn tất trước release hay có thể chạy ở giai đoạn tiếp theo.

## 11. Ví dụ mô hình hóa điểm ưu tiên

Giả sử nhóm dùng thang 1–5 và trọng số tham khảo:

- Rủi ro nghiệp vụ (R): 35%.
- Liên quan thay đổi (C): 30%.
- Lịch sử lỗi (H): 20%.
- Khả năng phát hiện (D): 15%.

Điểm cơ sở:

\[
P = 0.35R + 0.30C + 0.20H + 0.15D
\]

Sau đó, nhóm có thể dùng thời gian chạy và độ ổn định như tiêu chí phụ để sắp xếp trong các ca có điểm gần nhau. Không nên trừ điểm rủi ro cao chỉ vì test tốn thời gian; thay vào đó, đưa ca đó vào lịch chạy phù hợp hoặc tìm cách giảm chi phí.

Ví dụ minh họa:

| Ca | R | C | H | D | Điểm P |
|---|---:|---:|---:|---:|---:|
| Unit tính phí khu vực | 5 | 5 | 4 | 5 | 4,80 |
| Integration tổng tiền | 5 | 5 | 5 | 4 | 4,85 |
| E2E tạo đơn thanh toán | 5 | 4 | 4 | 5 | 4,50 |
| Báo cáo doanh thu | 3 | 3 | 2 | 3 | 2,80 |
| Ảnh đại diện | 1 | 1 | 1 | 2 | 1,15 |

Điểm số giúp nhóm thảo luận, nhưng không tự quyết định tập chạy. Ví dụ, integration tổng tiền có điểm cao nhất nhưng cần môi trường sẵn sàng; unit test có thể chạy trước để cung cấp phản hồi sớm. Ngoài ra, một ca bảo mật bắt buộc vẫn phải chạy dù điểm số thấp hơn.

## 12. Cải thiện dữ liệu và khả năng truy vết

Ưu tiên chỉ tốt khi dữ liệu đầu vào đủ tin cậy. Nếu không biết test nào kiểm tra yêu cầu hoặc thành phần nào, việc chọn dựa trên vùng thay đổi sẽ thiếu chính xác.

### 12.1. Liên kết test với yêu cầu, rủi ro và thành phần

Mỗi test quan trọng nên có metadata hoặc liên kết thể hiện:

- Yêu cầu hoặc hành vi được kiểm tra.
- Module, service, API, event hoặc dữ liệu liên quan.
- Rủi ro được bảo vệ.
- Lỗi lịch sử hoặc sự cố đã dẫn đến test.
- Tầng kiểm thử và môi trường cần thiết.
- Thời gian chạy và mức ổn định.
- Chủ sở hữu và lịch rà soát.

Liên kết này giúp truy từ diff đến test, từ lỗi đến test hồi quy và từ test thất bại đến rủi ro nghiệp vụ.

### 12.2. Gắn tag có quy ước

Ví dụ tag:

```text
area:pricing
service:order
risk:financial
change:shipping-fee
history:defect-142
level:integration
runtime:medium
```

Tag cần được chuẩn hóa, tránh tên tự do quá nhiều hoặc tag lỗi thời. Không nên dùng tag làm bản sao của toàn bộ metadata nếu hệ thống quản lý test đã có trường tương ứng.

### 12.3. Duy trì bản đồ phụ thuộc

Đồ thị phụ thuộc có thể đến từ kiến trúc, module build, API catalog, event catalog hoặc phân tích mã. Cần cập nhật khi module mới được thêm, API đổi hoặc service được tách/gộp.

### 12.4. Quản lý chất lượng dữ liệu lỗi

Ghi rõ nguyên nhân đã xác minh hay giả thuyết, phân biệt lỗi trùng, giữ liên kết đến incident và cập nhật khi có kết quả điều tra mới. Lịch sử không chính xác có thể làm điểm ưu tiên sai lệch.

## 13. Đánh giá hiệu quả của chiến lược ưu tiên

Sau khi áp dụng, nhóm cần kiểm tra xem các ca được ưu tiên có thực sự giúp phát hiện lỗi quan trọng sớm hơn và giảm thời gian phản hồi hay không.

Các chỉ số có thể theo dõi:

- **Thời gian phát hiện lỗi:** từ khi thay đổi được đưa vào đến khi test phát hiện sai lệch.
- **Tỷ lệ lỗi phát hiện trước phát hành:** số lỗi được phát hiện ở pipeline so với lỗi phát hiện muộn.
- **Tỷ lệ lỗi nghiêm trọng được phát hiện trong tập ưu tiên:** mức bảo vệ của bộ test nhanh đối với rủi ro cao.
- **Thời gian chạy tập ưu tiên:** thời gian hoàn tất nhóm test được chọn cho pull request hoặc release candidate.
- **Tỷ lệ test được chọn có liên quan:** mức test thực sự liên quan đến vùng thay đổi hoặc rủi ro đã xác định.
- **Tỷ lệ bỏ sót theo lịch sử:** lỗi mới có nguyên nhân tương tự lỗi cũ nhưng không được test ưu tiên phát hiện.
- **Tỷ lệ flaky trong tập ưu tiên:** độ tin cậy của các tín hiệu chặn phát hành.
- **Tỷ lệ test bắt buộc được thực thi:** mức tuân thủ chính sách.

Không nên tối ưu chỉ số bằng cách giảm phạm vi kiểm thử một cách thiếu kiểm soát. Ví dụ, giảm thời gian pipeline bằng cách bỏ hết E2E có thể làm tăng lỗi lọt. Cần đọc chỉ số cùng hậu quả và bối cảnh thay đổi.

### 13.1. Phân tích lỗi lọt sau phát hành

Khi có lỗi production, hãy xem:

- Lỗi có thuộc vùng thay đổi hoặc phụ thuộc liên quan không?
- Có test tương ứng nhưng không được chọn không?
- Test được chọn nhưng assertion không phát hiện không?
- Dữ liệu hoặc môi trường không tái hiện được điều kiện không?
- Lịch sử lỗi đã có tín hiệu nhưng chưa được dùng trong ưu tiên không?
- Trọng số hoặc quy tắc có cần điều chỉnh không?

Kết quả phân tích cần cập nhật cả bộ test và quy tắc ưu tiên, không chỉ thêm một ca mới.

### 13.2. Rà soát định kỳ

Định kỳ xem lại:

- Test không còn liên quan đến tính năng hiện tại.
- Test trùng lặp hoặc chi phí cao nhưng ít giá trị.
- Test có tỷ lệ flaky cao.
- Test mới từ lỗi nghiêm trọng.
- Thành phần dùng chung vừa thay đổi.
- Rủi ro nghiệp vụ hoặc quy định mới.

Trọng số và ngưỡng điểm cũng cần được rà soát khi mục tiêu phát hành, kiến trúc hoặc mức rủi ro thay đổi.

## 14. Những sai lầm thường gặp

### 14.1. Chỉ ưu tiên theo thời gian chạy

Test nhanh không nhất thiết có giá trị cao. Hãy kết hợp thời gian với rủi ro, thay đổi và khả năng phát hiện.

### 14.2. Chỉ chọn test theo file diff

Thay đổi trong thành phần dùng chung có thể ảnh hưởng nhiều service và luồng nghiệp vụ. Cần mở rộng qua dependency, consumer, dữ liệu và hợp đồng.

### 14.3. Chỉ dựa vào số lỗi lịch sử

Số lỗi thô bị ảnh hưởng bởi quy mô và mức độ kiểm thử. Cần xem mức nghiêm trọng, số lần thay đổi, nguyên nhân và điều kiện còn tồn tại.

### 14.4. Dùng điểm số như quyết định tuyệt đối

Điểm ưu tiên chỉ hỗ trợ thảo luận. Cần có quy tắc bắt buộc cho rủi ro nghiêm trọng, yêu cầu tuân thủ và kiểm tra phát hành.

### 14.5. Nhầm lựa chọn với sắp xếp

Chạy test theo thứ tự ưu tiên không thay thế việc xác định tập test cần chạy. Ngược lại, chọn đúng tập nhưng chạy ca quan trọng quá muộn có thể làm chậm phát hiện lỗi.

### 14.6. Giả định mọi tác động đều biết được từ diff

Diff không thể hiện đầy đủ thay đổi về cấu hình, dữ liệu, hành vi runtime hoặc tác động nghiệp vụ. Cần kết hợp yêu cầu, kiến trúc, lịch sử và hiểu biết của người sở hữu.

### 14.7. Không ghi lại ca đã bỏ qua

Nếu báo cáo chỉ hiển thị các ca đã chạy, người đọc có thể hiểu nhầm rằng toàn bộ hồi quy đã đạt. Ghi rõ phạm vi, lý do hoãn và rủi ro còn lại.

### 14.8. Không cập nhật ưu tiên sau sự cố

Một lỗi production là bằng chứng mới về rủi ro. Nếu không cập nhật test và quy tắc ưu tiên, nhóm có thể lặp lại cùng khoảng trống.

## 15. Quy trình áp dụng cho một lần thay đổi

Nhóm có thể áp dụng trình tự sau cho mỗi pull request hoặc bản phát hành:

1. **Đọc mục tiêu thay đổi:** hiểu hành vi, yêu cầu và tiêu chí chấp nhận.
2. **Lập vùng tác động:** xác định module, API, dữ liệu, cấu hình, consumer và luồng liên quan.
3. **Đánh giá rủi ro:** xác định hậu quả, khả năng xảy ra, mức phơi nhiễm và khả năng phát hiện.
4. **Tra cứu lịch sử lỗi:** tìm lỗi nghiêm trọng, lỗi tái diễn và điều kiện từng bị bỏ sót.
5. **Tập hợp ca ứng viên:** liên kết test với vùng tác động, yêu cầu, rủi ro và lỗi.
6. **Áp dụng quy tắc bắt buộc:** giữ các ca smoke, bảo mật, dữ liệu và release gate cần thiết.
7. **Chọn tập theo ngân sách:** cân nhắc độ bao phủ, trùng lặp, thời gian và độ tin cậy.
8. **Sắp xếp thực thi:** chạy ca có giá trị phát hiện cao và rủi ro trực tiếp trước, đồng thời tôn trọng phụ thuộc.
9. **Theo dõi kết quả:** phân loại lỗi sản phẩm, test, môi trường và ca bị chặn.
10. **Ghi phạm vi chưa kiểm tra:** nêu lý do và rủi ro còn lại.
11. **Cập nhật sau phát hành:** dùng lỗi mới và dữ liệu thực thi để điều chỉnh test và ưu tiên.

## 16. Danh sách rà soát ưu tiên ca hồi quy

Trước khi xác nhận tập hồi quy cho một thay đổi, hãy kiểm tra:

- [ ] Mục tiêu và phạm vi thay đổi được hiểu rõ.
- [ ] Thành phần trực tiếp, phụ thuộc, consumer và dữ liệu liên quan đã được xem xét.
- [ ] Rủi ro nghiệp vụ và kỹ thuật được đánh giá theo hậu quả và khả năng xảy ra.
- [ ] Lịch sử lỗi nghiêm trọng, tái diễn và lỗi lọt đã được tra cứu.
- [ ] Ca kiểm thử được liên kết với yêu cầu, rủi ro hoặc thành phần.
- [ ] Ca bắt buộc được giữ lại bất kể điểm số.
- [ ] Tập được chọn phù hợp với ngân sách thời gian và môi trường.
- [ ] Ca quan trọng được sắp xếp chạy sớm.
- [ ] Phụ thuộc thứ tự, dữ liệu dùng chung và khả năng chạy song song được kiểm soát.
- [ ] Test flaky hoặc lỗi thời được nhận diện và xử lý.
- [ ] Báo cáo phân biệt ca đã chạy, bị bỏ qua, bị chặn và chưa có bằng chứng.
- [ ] Rủi ro còn lại được ghi nhận và có người quyết định.
- [ ] Kết quả sau phát hành được dùng để cập nhật ưu tiên.

## 17. Kết luận

Ưu tiên ca kiểm thử hồi quy cần kết hợp rủi ro, vùng thay đổi và lịch sử lỗi. Rủi ro cho biết hậu quả cần bảo vệ; phân tích thay đổi xác định các hành vi có thể bị ảnh hưởng; lịch sử lỗi giúp nhận diện những điểm yếu và điều kiện từng bị bỏ sót. Khi kết hợp ba nguồn này, nhóm có cơ sở để chọn tập kiểm thử phù hợp và sắp xếp thứ tự thực thi nhằm phát hiện lỗi quan trọng sớm.

Điểm số có thể hỗ trợ so sánh nhưng không thay thế phán đoán kỹ thuật, quy tắc bắt buộc hoặc trách nhiệm chấp nhận rủi ro. Một chiến lược tốt cần minh bạch lý do chọn và bỏ qua test, theo dõi độ ổn định và thời gian chạy, đồng thời cập nhật sau mỗi thay đổi và sự cố. Nhờ đó, bộ hồi quy tạo ra bằng chứng tập trung vào rủi ro thực tế mà vẫn sử dụng hiệu quả thời gian và tài nguyên.
