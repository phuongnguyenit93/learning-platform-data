Khi nguồn lực kiểm thử có hạn, nhóm nên ưu tiên khu vực nào trước?
A. Luồng có tác động lớn và nguy cơ lỗi cao
B. Luồng có ít người dùng và ít thay đổi nhất
C. Chỉ phần có nhiều file Java và ít yêu cầu
D. Chỉ màn hình dễ tự động hóa trong thời gian ngắn
Đáp án đúng: A

Trong một chiến lược kiểu testing pyramid, phân bổ nào thường hợp lý?
A. Đa số E2E, rất ít unit và integration
B. Chỉ integration, bỏ unit và các luồng E2E
C. Mỗi cấp độ có đúng số bài như nhau
D. Nhiều unit, có integration và E2E chọn lọc
Đáp án đúng: D

Để đánh giá rủi ro kiểm thử của một chức năng, cặp yếu tố nào hữu ích?
A. Số dòng code và số commit trên nhánh
B. Khả năng phát sinh lỗi và mức tác động
C. Tên người review và tên framework được dùng
D. Số phương thức public và độ dài file test
Đáp án đúng: B

Sau một lỗi quan trọng lọt ra production, hành động cải tiến nào phù hợp?
A. Chỉ tăng timeout cho toàn bộ bộ test hiện có
B. Bỏ kiểm thử API để tập trung vào E2E
C. Chờ sự cố tương tự xuất hiện trước khi cập nhật
D. Thêm ca hồi quy ở tầng kiểm thử thích hợp
Đáp án đúng: D

Khi thiết kế dữ liệu kiểm thử gần thực tế, nguyên tắc nào cần giữ?
A. Dùng tài khoản khách hàng thật cho mọi job CI
B. Sao chép nguyên database production tới laptop
C. Dùng dữ liệu đại diện và ẩn thông tin nhạy cảm
D. Dùng duy nhất một bản ghi mẫu cho mọi tình huống
Đáp án đúng: C

Để giảm chênh lệch giữa môi trường kiểm thử và CI, cách quản trị nào phù hợp?
A. Thay phiên bản dependency tùy mỗi lần chạy
B. Ghi cấu hình riêng vào máy cá nhân của tester
C. Lưu cấu hình version để tái tạo môi trường
D. Chỉ giữ một môi trường chung không thể reset
Đáp án đúng: C

Với ngân sách automation hạn chế, loại test nào nên được ưu tiên?
A. Ca lặp lại thường xuyên, ổn định và rủi ro cao
B. Ca chỉ chạy một lần rồi không cần kiểm tra lại
C. Ca phụ thuộc nhận xét chủ quan không có tiêu chí
D. Ca chưa xác định được đầu ra nào là đúng
Đáp án đúng: A

Vì sao exploratory testing vẫn có giá trị bên cạnh script tự động?
A. Tự bảo đảm mọi chức năng đều có đủ coverage
B. Khám phá hành vi bất ngờ ngoài kịch bản đã có
C. Thay thế toàn bộ kiểm chứng kết quả nghiệp vụ
D. Loại bỏ nhu cầu thu thập bằng chứng khi có lỗi
Đáp án đúng: B

Một tiêu chí phát hành dựa trên bằng chứng nên xét điều gì?
A. Chỉ số commit được tạo trong ngày phát hành
B. Chỉ số lượng test tồn tại trong repository
C. Chỉ tốc độ chạy xong bộ unit test trên CI
D. Lỗi còn mở và trạng thái luồng trọng yếu
Đáp án đúng: D

Khi số test pass tăng nhưng lỗi lọt production cũng tăng, nhóm nên làm gì?
A. Chỉ tăng số lượng test đến khi vượt ngưỡng
B. Phân tích lỗi lọt để chỉnh phạm vi kiểm thử
C. Bỏ theo dõi lỗi sau phát hành vì đã có CI
D. Giữ nguyên chiến lược vì số test pass đã tăng
Đáp án đúng: B

Vì sao chỉ dựa vào line coverage để quyết định phát hành là thiếu?
A. Vì coverage chỉ đo tốc độ thực thi của CI
B. Vì coverage luôn bỏ sót mọi câu lệnh có điều kiện
C. Vì mã được thực thi chưa chắc được kiểm chứng
D. Vì coverage chỉ áp dụng cho bài E2E trên browser
Đáp án đúng: C

Khi nhiều bài test flaky, chiến lược xử lý nào hợp lý?
A. Cho phép green nếu mọi lỗi đều pass khi retry
B. Xóa ngay mọi test có kết quả không ổn định
C. Theo dõi lỗi ngẫu nhiên và sửa nguyên nhân gốc
D. Giảm số assertion ở mọi bài đến khi không còn fail
Đáp án đúng: C

Traceability giữa yêu cầu và kiểm thử giúp nhóm thực hiện điều gì?
A. Phát hiện yêu cầu quan trọng còn thiếu kịch bản
B. Thay mọi review yêu cầu bằng kiểm tra mã tự động
C. Buộc mọi requirement có đúng một bài unit test
D. Loại bỏ các ca regression khi thay đổi chức năng
Đáp án đúng: A

Một chức năng vừa đúng nghiệp vụ nhưng có rủi ro tải cao, chiến lược cần bổ sung gì?
A. Chỉ thêm snapshot UI để phát hiện khác màu
B. Chỉ chạy thêm unit test cho getter trong DTO
C. Bỏ qua kiểm tra vì yêu cầu chức năng đã pass
D. Kiểm tra hiệu năng dưới tải đại diện
Đáp án đúng: D

Khi thời hạn gấp và không thể chạy toàn bộ regression, cách chọn tập test nào hợp lý?
A. Chọn ngẫu nhiên các bài có tên ngắn nhất
B. Ưu tiên vùng thay đổi, phụ thuộc và rủi ro cao
C. Chỉ chạy các bài đã pass ở bản build trước
D. Chạy chỉ một bài E2E dù không liên quan thay đổi
Đáp án đúng: B

Sau mỗi đợt phát hành, nguồn bằng chứng nào giúp cải tiến chiến lược test?
A. Đối chiếu sự cố, lỗi lọt và hiệu quả test
B. Chỉ xem tổng số file test mà không đối chiếu lỗi
C. Chỉ ghi nhận thời điểm build bắt đầu chạy CI
D. Chỉ xem số người viết test trong tháng vừa rồi
Đáp án đúng: A
