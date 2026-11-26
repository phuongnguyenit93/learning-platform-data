Continuous inspection trong pull request nhằm đạt mục tiêu nào?
A. Chỉ đo tốc độ triển khai của mỗi đợt release
B. Thay toàn bộ bài kiểm thử đã có trong CI
C. Phát hiện sớm suy giảm chất lượng ở mã mới
D. Chỉ tổng hợp lỗi sau khi phát hành production
Đáp án đúng: C

Quality Profile trong công cụ phân tích xác định thành phần nào?
A. Bộ quy tắc phân tích áp dụng cho dự án
B. Ngưỡng pass/fail của lần phân tích hiện tại
C. Lịch phân phối job cho các runner trong CI
D. Quyền merge code được cấp cho từng reviewer
Đáp án đúng: A

Quality Gate chịu trách nhiệm gì trong quy trình kiểm tra mã?
A. Áp đặt kiểu thụt lề cho mọi file nguồn
B. Chọn danh sách rule dùng cho ngôn ngữ Java
C. Lập lịch chạy scanner trên repository
D. Xét đạt hay không theo ngưỡng metric đã đặt
Đáp án đúng: D

Với dự án có nhiều nợ mã cũ, New Code giúp kiểm soát cải tiến ra sao?
A. Giữ mã mới đạt chuẩn và xử lý dần backlog
B. Đưa mọi lỗi cũ vào gate trước khi mở PR
C. Chỉ đo mã mới sau khi mã cũ hết issue
D. Bỏ quét mã cũ nếu CI có kiểm thử tự động
Đáp án đúng: A

Coverage đo theo báo cáo thực thi test phản ánh điều gì?
A. Tỷ lệ ca nghiệp vụ được khẳng định hoàn toàn đúng
B. Phần mã đã được thực thi theo phép đo đang dùng
C. Số lỗi tiềm ẩn được bộ test tự động phát hiện
D. Số phương thức có nhiều assertion trong mỗi test
Đáp án đúng: B

Coverage cao nhưng bug logic vẫn lọt, cách nào trực tiếp nâng khả năng phát hiện lỗi?
A. Đổi cách tính line coverage trong báo cáo
B. Nâng thời gian timeout để test chạy ổn định
C. Bật thêm cache dependency để CI nhanh hơn
D. Rà assertion và bổ sung các trường hợp biên
Đáp án đúng: D

Khi duplication tăng sau một PR, bước đánh giá phù hợp nhất là gì?
A. Tách mọi đoạn giống nhau thành utility ngay lập tức
B. Cho qua nếu mỗi file chỉ chứa một bản sao lặp
C. Xem ngữ nghĩa và khả năng dùng chung của đoạn lặp
D. Xóa một đoạn giống nhau rồi chạy lại bộ test
Đáp án đúng: C

Chỉ số complexity tăng mạnh trong một method, nên rà soát điểm nào?
A. Đổi tên biến để hạn chế độ sâu các biểu thức
B. Rà các nhánh điều kiện và trách nhiệm của method
C. Chuyển method sang file khác để giảm kích thước
D. Nâng ngưỡng cảnh báo trước khi phân tích luồng
Đáp án đúng: B

Để kết hợp kiểm tra chất lượng và coverage trong CI, cần làm gì?
A. Chạy scanner thay thế toàn bộ test của pipeline
B. Chỉ chạy scanner ở commit đầu tiên của dự án
C. Loại bỏ cấu hình build để quét không phụ thuộc
D. Chạy test phù hợp rồi cung cấp báo cáo coverage
Đáp án đúng: D

PR bị Quality Gate đánh trượt, bước xử lý ban đầu nên là gì?
A. Đếm số commit và số reviewer của nhánh đang xét
B. Xem điều kiện không đạt và các issue liên quan
C. Tắt rule vừa báo lỗi rồi chạy lại đến khi đạt
D. Đánh dấu đồng loạt các issue là false positive
Đáp án đúng: B

Nếu nghi một issue là false positive, cách triage đáng tin cậy là gì?
A. Chỉnh severity của toàn dự án để bỏ hiển thị issue
B. Đánh dấu ngay nếu lập trình viên không đồng tình
C. Vô hiệu hóa rule ấy trong mọi repository liên quan
D. Kiểm tra ngữ cảnh và ghi lý do trước khi đánh dấu
Đáp án đúng: D

Khi thiết lập ngưỡng cho Quality Gate, căn cứ nào hợp lý nhất?
A. Dùng số ngưỡng càng nhiều để dashboard trông đầy đủ
B. Dựa trên số commit thay vì chất lượng mã thay đổi
C. Chọn metric đo được và ngưỡng gắn với rủi ro
D. Sao chép ngưỡng từ dự án khác dù khác đặc tính
Đáp án đúng: C

Một rule sinh nhiều issue giống nhau, nên xếp thứ tự xử lý thế nào?
A. Sửa theo tên file vì mọi issue có tác động tương đương
B. Xem mức tác động và chi phí để ưu tiên theo rủi ro
C. Chỉ sửa issue tồn tại lâu nhất dù ít ảnh hưởng
D. Đóng cùng lúc vì các issue phát sinh từ một rule
Đáp án đúng: B

Tất cả test pass nhưng Quality Gate vẫn fail có thể nghĩa là gì?
A. Kiểm thử tự động đã bỏ qua mọi điều kiện trong gate
B. Kết quả phân tích chắc chắn trùng với lỗi runtime
C. Metric chất lượng chưa đạt dù các test đang pass
D. Pipeline đã âm thầm chỉnh mã trước khi chạy test
Đáp án đúng: C

Muốn so sánh xu hướng chất lượng qua các kỳ, nên giữ nhất quán điều gì?
A. Định nghĩa metric và phạm vi mã đang được đo
B. Chỉ đo số commit để suy ra số lỗi trung bình
C. Thay ngưỡng gate mỗi kỳ để duy trì trạng thái pass
D. Chỉ dùng số issue tổng dù phạm vi code thay đổi
Đáp án đúng: A

Khi triển khai kiểm tra liên tục cho nhiều repository, cách quản trị nào phù hợp?
A. Dùng cấu hình có phiên bản và kiểm soát thay đổi
B. Cho từng nhóm tùy ý tắt rule mà không cần ghi lại
C. Áp cùng ngưỡng cho mọi loại mã và quy trình build
D. Chỉ dùng một dashboard và bỏ phản hồi trên PR
Đáp án đúng: A
