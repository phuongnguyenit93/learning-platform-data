Mục tiêu trung tâm của ATDD là gì?
A. Thống nhất hành vi qua ví dụ chấp nhận
B. Định hình mã nguồn bằng biểu đồ lớp
C. Đo độ phủ unit test của từng module
D. Đưa ra kế hoạch tối ưu thời gian chạy
Đáp án đúng: A

Khi nào nên thống nhất tiêu chí chấp nhận?
A. Trước khi hiện thực tính năng
B. Sau vòng code review cuối cùng
C. Khi chuẩn bị triển khai production
D. Sau khi tester chạy regression
Đáp án đúng: A

Ai nên cùng thảo luận các ví dụ ATDD?
A. Kiến trúc sư, DBA và đội vận hành
B. Chỉ tester và người quản lý kiểm thử
C. Chỉ developer và người quản lý repo
D. Nghiệp vụ, người viết code và tester
Đáp án đúng: D

Đầu ra có giá trị nhất của buổi ATDD là gì?
A. Các script SQL sẵn để triển khai
B. Các ví dụ phản ánh quy tắc chung
C. Sơ đồ package theo mẫu chuẩn
D. Bộ chỉ số hiệu năng ban đầu
Đáp án đúng: B

Ví dụ chấp nhận cho phí giao hàng cần gì?
A. Danh sách method nội bộ được gọi
B. Thiết kế bảng lưu giá theo từng vùng
C. Điều kiện đầu vào và phí phải tính
D. Thứ tự các controller trong luồng gọi
Đáp án đúng: C

Khi 'khách hàng đủ điều kiện' còn mơ hồ, làm gì?
A. Chọn điều kiện phổ biến rồi code
B. Đưa nguyên cụm từ vào step regex
C. Giao tester tự đoán mức điều kiện
D. Hỏi ví dụ cụ thể và phản ví dụ
Đáp án đúng: D

Given trong kịch bản Gherkin nói về gì?
A. Sự kiện người dùng vừa thực hiện
B. Kết quả nghiệp vụ phải quan sát
C. Lỗi mà bước triển khai đã phát sinh
D. Bối cảnh có trước hành động chính
Đáp án đúng: D

When trong Gherkin thường chỉ điều gì?
A. Điều kiện dữ liệu trước thao tác
B. Hành động kích hoạt hành vi
C. Kết quả đã được xác minh xong
D. Cách nạp driver của bộ kiểm thử
Đáp án đúng: B

Then nên mô tả phần nào của kịch bản?
A. Chi tiết gọi từng method private
B. Kết quả quan sát theo quy tắc
C. Tên class xử lý request hiện tại
D. Số lần repository được mock gọi
Đáp án đúng: B

Vai trò của Gherkin đối với ATDD là gì?
A. Công cụ duy nhất để nghiệm thu ứng dụng
B. Lớp bắt buộc thay thế unit test trong Java
C. Ngôn ngữ xác định toàn bộ thiết kế database
D. Cách diễn đạt ví dụ, không phải điều kiện bắt buộc
Đáp án đúng: D

Hai bên hiểu một quy tắc theo hai cách thì nên làm gì?
A. Đối chiếu ví dụ và chốt kết quả
B. Viết hai nhánh code rồi benchmark
C. Để QA quyết định sau khi phát hành
D. Dựa vào mặc định của thư viện hiện có
Đáp án đúng: A

Acceptance test ưu tiên kiểm chứng mức nào?
A. Số nhánh trong từng phương thức Java
B. Thứ tự gọi của các hàm helper
C. Hành vi hoàn chỉnh người dùng cần
D. Kết cấu từng đối tượng mock được tạo
Đáp án đúng: C

Test chấp nhận đỏ trước khi code có ích gì?
A. Cho biết tiêu chí chưa được đáp ứng
B. Chứng minh sản phẩm lỗi trên production
C. Xác nhận thiết kế class cuối cùng đã tốt
D. Cho thấy hạ tầng đang bị quá tải
Đáp án đúng: A

Scenario dễ trao đổi với nghiệp vụ cần gì?
A. Danh sách request HTTP theo thời gian
B. Tên package chứa step definition
C. Ngôn ngữ miền và kết quả cụ thể
D. Tên selector CSS của từng button
Đáp án đúng: C

Khi nào nên dùng Scenario Outline?
A. Nhiều quy trình nghiệp vụ không liên quan
B. Cùng quy tắc với nhiều bộ giá trị
C. Một bước cần khởi tạo nhiều service
D. Mỗi ví dụ cần luồng chạy hoàn toàn khác
Đáp án đúng: B

Examples trong Scenario Outline mô tả gì?
A. Các method private cần mock riêng
B. Bộ dữ liệu biến thể của cùng quy tắc
C. Danh sách runner trong pipeline CI
D. Các class implement interface
Đáp án đúng: B

Step definition có vai trò chính nào?
A. Chứa toàn bộ logic tính toán của sản phẩm
B. Thay thế service nghiệp vụ khi chạy production
C. Nối bước nghiệp vụ với thao tác test
D. Chỉnh kết quả để mọi scenario đều xanh
Đáp án đúng: C

Bước Given lặp lại ở nhiều scenario nên làm gì?
A. Sao chép toàn bộ setup vào từng file
B. Đổi câu mô tả theo tên method Java
C. Tái sử dụng bước rõ nghĩa và độc lập
D. Viết một regex khớp mọi câu nghiệp vụ
Đáp án đúng: C

Muốn test không vỡ khi đổi UI, nên assert gì?
A. Vị trí pixel chính xác của button
B. Thứ tự class CSS của các phần tử
C. Số request tải ảnh trên trình duyệt
D. Kết quả nghiệp vụ qua ranh giới ổn định
Đáp án đúng: D

Kịch bản UI đầu cuối quá chậm nên ưu tiên gì?
A. Chọn mức kiểm thử đủ xác minh hành vi
B. Đưa mọi assertion xuống method private
C. Bỏ kiểm chứng kết quả cuối cùng
D. Tăng sleep cố định cho tất cả bước
Đáp án đúng: A

Scenario có nhiều chi tiết click và nhập gây khó hiểu nên làm gì?
A. Thêm nhiều bước kỹ thuật giải thích
B. Gom thành bước có ý nghĩa nghiệp vụ
C. Đổi toàn bộ step sang tên Java method
D. Ẩn mọi assertion trong một hàm setup
Đáp án đúng: B

Acceptance test độc lập cần bảo đảm gì?
A. Các kịch bản dùng chung user được sửa
B. Toàn bộ scenario chạy theo thứ tự cố định
C. Chỉ thực thi những ca đã thành công
D. Trạng thái không phụ thuộc thứ tự chạy
Đáp án đúng: D

Ví dụ âm tính nào kiểm tra quyền truy cập?
A. Chủ tài khoản xem hồ sơ của chính mình
B. Người không đủ quyền không sửa được hồ sơ
C. Admin cập nhật hồ sơ đúng dữ liệu
D. Người dùng mở màn hình đăng nhập
Đáp án đúng: B

Test xanh nhưng nghiệp vụ nói sai yêu cầu, nên làm gì?
A. Tăng coverage trên các method private
B. Rà lại tính đúng đủ của ví dụ chấp nhận
C. Chạy thêm luồng CPU để phát hiện sai
D. Đổi màu báo cáo CI để dễ theo dõi
Đáp án đúng: B

Nên tự động hóa acceptance test nào trước?
A. Các yêu cầu chưa rõ cách đánh giá
B. Toàn bộ thao tác UI đang đổi mỗi ngày
C. Ví dụ quan trọng đã thống nhất và ổn định
D. Các nhận xét chủ quan chưa có tiêu chí
Đáp án đúng: C

Khi nào một quy tắc ATDD đủ rõ để code?
A. Có ví dụ đúng và sai được cùng chấp nhận
B. Đã chọn xong tên mọi class controller
C. Tài liệu đạt đủ số dòng theo khuôn mẫu
D. Test có thể chạy dù thiếu expected result
Đáp án đúng: A

Với giới hạn số lượng, bộ ví dụ nên có gì?
A. Chỉ một ca hợp lệ giữa khoảng
B. Chỉ dữ liệu đã xảy ra trên production
C. Ca dưới, đúng và trên ngưỡng
D. Chỉ ca không có đầu vào hợp lệ
Đáp án đúng: C

Tester phát hiện ca bị bỏ sót, nhóm nên làm gì?
A. Chuyển lỗi tới sprint sau mà không bàn
B. Sửa test cho khớp code hiện tại
C. Để tester tự đặt quy tắc mới
D. Cùng cập nhật quy tắc và ví dụ liên quan
Đáp án đúng: D

Ngôn ngữ của scenario nên theo chuẩn nào?
A. Tên interface nằm trong source code
B. Cú pháp SQL dùng ở tầng persistence
C. Mã định danh của button trên trang
D. Thuật ngữ nghiệp vụ các bên cùng hiểu
Đáp án đúng: D

Step definition khó bảo trì thường do đâu?
A. Sử dụng dữ liệu tách riêng mỗi scenario
B. Tái sử dụng tên bước theo ngôn ngữ miền
C. Phụ thuộc chặt vào DOM và mã nội bộ
D. Tập trung assertion vào kết quả nghiệp vụ
Đáp án đúng: C

Nguyên nhân flaky test ATDD nên kiểm soát trước là gì?
A. Dữ liệu, timing và phụ thuộc bên ngoài
B. Thứ tự tên package của các file Java
C. Số comment ở mỗi step definition
D. Thời gian build của module không dùng
Đáp án đúng: A

Thông báo thất bại có ích cho ATDD cần gì?
A. Chỉ stack trace không kèm giá trị kỳ vọng
B. Chỉ màu đỏ và tên job vừa thực hiện
C. Bối cảnh và sai lệch so với kết quả mong đợi
D. Danh sách tên host của tất cả dịch vụ
Đáp án đúng: C

Vì sao không nên tự động hóa mọi ví dụ qua UI?
A. Unit test không thể phát hiện lỗi nghiệp vụ
B. Giao diện luôn che giấu mọi dữ liệu đầu ra
C. Mọi kịch bản UI đều bị framework từ chối
D. Phản hồi chậm và dễ phụ thuộc giao diện
Đáp án đúng: D

Nghiệp vụ xác nhận tính năng đạt yêu cầu thế nào?
A. Đối chiếu hành vi với ví dụ đã chốt
B. Chỉ kiểm tra tên class và số dòng
C. Chỉ đếm lượng test được viết trong sprint
D. Chỉ xem danh sách framework đang dùng
Đáp án đúng: A

ATDD khác unit-level TDD quan trọng nhất ở đâu?
A. Bắt buộc dùng ngôn ngữ lập trình khác
B. ATDD không được chạy kiểm thử tự động
C. Mức hành vi và vai trò cùng thống nhất
D. TDD chỉ áp dụng sau khi đã phát hành
Đáp án đúng: C

Definition of Done theo ATDD nên bao gồm gì?
A. Đủ số step definition đặt ra từ đầu
B. Tiêu chí chấp nhận chạy đúng trên hệ thống
C. Không thay đổi mã kể từ lần test xanh
D. Mọi scenario phải thao tác qua UI
Đáp án đúng: B

Nếu hiệu năng là tiêu chí chấp nhận, nhóm cần gì?
A. Chuyển sang loại yêu cầu không cần test
B. Thống nhất ngưỡng và điều kiện đo
C. Chỉ assert mã HTTP thành công
D. Dùng cảm nhận chủ quan trong demo
Đáp án đúng: B

Acceptance test có thay toàn bộ exploratory test không?
A. Có, vì mọi ca đều viết được bằng Gherkin
B. Có, nếu suite có nhiều hơn trăm scenario
C. Không, vì acceptance test không tự động
D. Không, thăm dò tìm rủi ro chưa mô tả
Đáp án đúng: D

Vì sao đưa acceptance test vào CI?
A. Phát hiện sớm sai lệch khỏi ví dụ đã thống nhất
B. Thay thế việc review code của các thành viên
C. Tự quyết định quy tắc nghiệp vụ phát sinh mới
D. Bảo đảm sản phẩm không bao giờ có lỗi
Đáp án đúng: A

Khi quy tắc được đổi giữa sprint, nhóm ATDD nên làm gì?
A. Sửa đặc tả và test theo thống nhất mới
B. Chỉ sửa assertion để test tiếp tục xanh
C. Đợi phát hành xong mới hỏi về quy tắc
D. Giữ nguyên test cũ vì đã được duyệt
Đáp án đúng: A
