Câu 1. Nợ kỹ thuật trong thiết kế phần mềm được hiểu chính xác nhất là gì?
A. Mọi chi phí hạ tầng phải trả theo tháng
B. Số lượng lỗi mà nhóm chưa báo cáo với khách hàng
C. Phần ngân sách đã dùng cho thư viện bên thứ ba
D. Chi phí thay đổi tăng do giải pháp khó duy trì
Đáp án đúng: D

Câu 2. Trong phép ẩn dụ nợ kỹ thuật, “lãi” của khoản nợ thể hiện qua điều gì?
A. Chi phí đầu tư phần cứng ban đầu của sản phẩm
B. Công sức phát sinh mỗi lần sửa hoặc mở rộng
C. Số dòng code đã được kiểm thử ở lần phát hành
D. Thời gian trả phí đăng ký công cụ phân tích
Đáp án đúng: B

Câu 3. Đội chủ động chọn giải pháp tạm để kịp thử nghiệm thị trường; cách quản trị nào phù hợp?
A. Ghi rõ đánh đổi, hạn xử lý và người sở hữu
B. Coi mọi lựa chọn tạm là lỗi phải xóa trước release
C. Ẩn quyết định vì sau này có thể không cần sửa
D. Dùng giải pháp tạm cho mọi module để đồng nhất
Đáp án đúng: A

Câu 4. Một hàm dài có nhiều nhánh có luôn là nợ kỹ thuật cần ưu tiên cao không?
A. Có, vì số dòng code quyết định toàn bộ rủi ro
B. Không; cần xem tác động, tần suất đổi và độ khó
C. Có, vì hàm dài luôn gây lỗi khi chạy production
D. Không; chỉ nợ kiến trúc mới có chi phí đáng kể
Đáp án đúng: B

Câu 5. Khi tìm “điểm nóng” (hotspot) trong codebase, tín hiệu kết hợp nào hữu ích?
A. Dung lượng file lớn nhưng không có lịch sử thay đổi
B. Số lần build thành công và số lượng file cấu hình
C. Thay đổi thường xuyên cùng độ phức tạp cao
D. Những class có tên dài và nhiều dòng import
Đáp án đúng: C

Câu 6. Vì sao thiếu test hồi quy ở vùng thường xuyên sửa có thể là khoản nợ?
A. Tăng chi phí xác nhận và rủi ro phát sinh lỗi
B. Làm mỗi class buộc phải có nhiều constructor
C. Khiến mọi thao tác đọc dữ liệu thành bất đồng bộ
D. Làm bộ biên dịch tự động bỏ qua logic nghiệp vụ
Đáp án đúng: A

Câu 7. Hai khoản nợ: A gây lỗi giao dịch hằng tuần, B chỉ làm chậm module hiếm sửa. Nên ưu tiên thế nào?
A. Xử lý B trước vì ít ai biết logic của nó
B. Ưu tiên khoản có số dòng code cần sửa ít hơn
C. Xử lý cả hai bằng một lần viết lại toàn hệ thống
D. Ưu tiên A theo tác động và tần suất phát sinh
Đáp án đúng: D

Câu 8. Một nhóm muốn nâng chất lượng module nhưng chưa có test bao phủ; bước an toàn ban đầu nào hợp lý?
A. Xóa module cũ rồi yêu cầu người dùng kiểm thử
B. Đổi toàn bộ tên class và package để dễ quản lý
C. Viết characterization tests ghi lại hành vi hiện tại
D. Chuyển module sang microservice trước khi có test
Đáp án đúng: C

Câu 9. Khác biệt trọng tâm của refactoring so với thêm tính năng là gì?
A. Cải thiện cấu trúc mà giữ hành vi quan sát được
B. Luôn thay đổi kết quả API theo yêu cầu người dùng
C. Loại bỏ mọi dependency ngoài mà không cần kiểm thử
D. Bắt buộc di chuyển dữ liệu sang database mới
Đáp án đúng: A

Câu 10. Một refactor lớn ảnh hưởng nhiều luồng nghiệp vụ; cách nào giảm rủi ro khi triển khai?
A. Thực hiện một commit duy nhất để dễ duyệt mã
B. Bỏ test integration để giảm thời gian pipeline
C. Đổi tất cả interface cùng lúc rồi mới chạy build
D. Chia thay đổi nhỏ, chạy test và kiểm tra hồi quy
Đáp án đúng: D

Câu 11. Để tránh tái phát nợ kỹ thuật sau khi xử lý một module, cơ chế nào hữu ích?
A. Chỉ đo số lượng file còn lại của module
B. Đặt quality gate và quy ước review phù hợp
C. Đưa toàn bộ code vào một class tiện truy cập
D. Khóa cứng mọi thay đổi ở module trong sáu tháng
Đáp án đúng: B

Câu 12. Một workaround khẩn cấp đã phát hành; thông tin nào nên lưu để có thể trả nợ đúng lúc?
A. Lý do, phạm vi, rủi ro và điều kiện tháo gỡ
B. Chỉ tên người viết workaround ở lần đầu
C. Chỉ đường dẫn tệp mà không cần mô tả đánh đổi
D. Chỉ ngày phát hành mà không có kế hoạch theo dõi
Đáp án đúng: A

Câu 13. Schema có nhiều cột chứa dữ liệu trùng khiến cập nhật dễ lệch nhau; loại nợ đáng chú ý là gì?
A. Nợ ở cách đặt tên phương thức kiểm thử
B. Nợ phát sinh từ mã Java không có interface
C. Nợ mô hình dữ liệu và quy tắc đồng bộ
D. Nợ giao diện người dùng không có responsive layout
Đáp án đúng: C

Câu 14. Khi một module domain import trực tiếp nhiều chi tiết framework, khó thay công nghệ, nợ nằm ở đâu?
A. Chỉ ở tốc độ network của môi trường triển khai
B. Phụ thuộc kiến trúc làm giảm khả năng thay đổi
C. Chỉ ở tên bảng SQL dùng để lưu cấu hình
D. Chỉ ở việc thiếu mô tả trên màn hình quản trị
Đáp án đúng: B

Câu 15. Một chỉ số nào hữu ích để đo xem việc giảm nợ có cải thiện hiệu quả thay đổi?
A. Số file tăng thêm trong repository mỗi ngày
B. Số comment mới nằm trên từng lớp đã sửa
C. Số giờ mở IDE trung bình mỗi lập trình viên
D. Thời gian hoàn thành thay đổi sau cải tiến
Đáp án đúng: D

Câu 16. Thư viện nền tảng cũ hết hỗ trợ và có lỗ hổng; nên đánh giá khoản nợ theo tiêu chí nào?
A. Chỉ độ dài tên của dependency trong build
B. Rủi ro bảo mật, ảnh hưởng và chi phí nâng cấp
C. Chỉ số lần thư viện được import trong test
D. Chỉ mức độ quen thuộc với cú pháp API cũ
Đáp án đúng: B

Câu 17. Tại sao coverage đạt 90% chưa chứng minh đã trả hết nợ kiểm thử?
A. Coverage không phản ánh đầy đủ chất lượng assertion
B. Coverage luôn bằng tỷ lệ lỗi đã sửa thành công
C. Coverage chỉ có thể đo trên lớp giao diện web
D. Coverage bảo đảm mọi nhánh lỗi đã được kiểm thử
Đáp án đúng: A

Câu 18. Nhóm đã refactor, nhưng thời gian sửa lỗi không đổi; bước đánh giá nào hợp lý?
A. Coi dự án đã thành công chỉ vì class ngắn hơn
B. Chỉ đánh giá bằng tổng số dòng code đã xóa
C. So lại baseline và nguyên nhân cản trở hiện tại
D. Bỏ chỉ số vận hành vì không liên quan đến thiết kế
Đáp án đúng: C

Câu 19. Một khoản nợ nhỏ nhưng nằm trên đường xử lý thanh toán nhạy cảm nên được xem xét ra sao?
A. Chỉ dựa vào kích thước của phần mã cần thay
B. Chỉ trả khi hệ thống đã ngừng thêm tính năng
C. Tự động hoãn đến cuối năm vì code có ít dòng
D. Ưu tiên theo rủi ro dù kích thước mã nhỏ
Đáp án đúng: D

Câu 20. Viết lại toàn bộ hệ thống để loại nợ có thể gây hại vì sao?
A. Luôn mất mọi dữ liệu kể cả khi đã backup
B. Không thể triển khai cải tiến theo từng giai đoạn
C. Tăng rủi ro đổi hành vi và làm mất hiểu biết cũ
D. Bắt buộc chuyển toàn bộ ứng dụng sang ngôn ngữ khác
Đáp án đúng: C

Câu 21. Một interface nội bộ có quá nhiều consumer khiến sửa nhỏ phải đổi hàng loạt module; dấu hiệu nợ nào?
A. Thiếu tối ưu kích thước artifact khi build
B. Liên kết chặt và ranh giới module không ổn định
C. Thiếu theme màu cho các màn hình quản trị
D. Bộ test có quá nhiều dữ liệu đầu vào hợp lệ
Đáp án đúng: B

Câu 22. Backlog nợ kỹ thuật minh bạch nên ghi nhận điều gì cho từng mục?
A. Chỉ lời phàn nàn chung là code khó đọc
B. Chỉ tên nhánh Git chứa phần code có vấn đề
C. Chỉ số lượng câu lệnh SQL trong module đó
D. Tác động, độ ưu tiên, người chịu trách nhiệm
Đáp án đúng: D

Câu 23. Khi chọn giữa trả nợ và triển khai tính năng mới, thông tin nào cần cân nhắc?
A. Chỉ sở thích kỹ thuật của người viết code
B. Chỉ số lượng thư viện sẽ được cập nhật
C. Chi phí trì hoãn, giá trị và rủi ro tương ứng
D. Chỉ số lượng comment trong yêu cầu nghiệp vụ
Đáp án đúng: C

Câu 24. Sau khi trả nợ ở module thường thay đổi, cách chứng minh tác dụng tốt nhất là gì?
A. So sánh lead time, lỗi và công sức trước–sau
B. Chỉ đếm số method bị đổi tên thành ngắn hơn
C. Chỉ kiểm tra phiên bản Java vẫn biên dịch được
D. Chỉ thu thập cảm nhận tích cực của một người
Đáp án đúng: A
