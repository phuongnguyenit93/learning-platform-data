Câu 1. Nhóm có đủ development, testing, staging và production. Vai trò nào phù hợp nhất cho staging trong luồng phát hành?
A. Thay production chạy kiểm thử tải với dữ liệu khách hàng thật.
B. Xác minh bản phát hành và quy trình deploy trước production.
C. Lưu bản build chưa kiểm thử để developer chạy thủ công.
D. Chia sẻ môi trường phát triển cho nhiều nhánh cùng lúc.
Đáp án đúng: B

Câu 2. Một ứng dụng staging bị lộ quyền truy cập, nhưng không được ảnh hưởng cơ sở dữ liệu production. Thiết kế nào có tác dụng trực tiếp?
A. Tách tên schema nhưng dùng cùng tài khoản quản trị database.
B. Ẩn connection string trong CI log của mọi môi trường.
C. Giữ chung database rồi giới hạn truy cập bằng tên branch.
D. Tách mạng, tài khoản và dữ liệu theo ranh giới môi trường.
Đáp án đúng: D

Câu 3. Staging cần đại diện cho production dù ngân sách không cho phép số lượng node bằng nhau. Nên ưu tiên điều gì?
A. Giữ tương đồng runtime, dependency và đường triển khai.
B. Giảm xác thực và phân quyền ở staging để pipeline chạy nhẹ hơn.
C. Chạy mã từ nhánh khác để thử nhiều biến thể độc lập.
D. Chuyển toàn bộ integration test sang production thật.
Đáp án đúng: A

Câu 4. Một gói ứng dụng đã qua kiểm thử trên staging. Cách nào đảm bảo production nhận đúng các byte đã kiểm chứng?
A. Build lại từ Git tag bằng runner dành cho production.
B. Đóng gói lại cùng version với file cấu hình production.
C. Biên dịch lại từ commit đã kiểm thử trên runner khác.
D. Promote artifact đã kiểm thử theo digest không đổi.
Đáp án đúng: D

Câu 5. Dịch vụ cần truy cập kho dữ liệu ở testing và production với mức quyền khác nhau. Chính sách secret nào phù hợp?
A. Dùng chung một secret rồi giới hạn nơi hiển thị trong log.
B. Cấp secret riêng từng môi trường với quyền tối thiểu.
C. Chép secret production vào testing để so hành vi truy cập.
D. Ghi credential trong cấu hình Git nhưng mã hóa base64.
Đáp án đúng: B

Câu 6. Đội QA cần dữ liệu giống thực tế để kiểm thử chức năng tìm kiếm. Cách quản lý dữ liệu nào hạn chế rò rỉ thông tin cá nhân?
A. Khôi phục trực tiếp backup production vào database dùng chung.
B. Cho developer dùng bản sao production tải về qua VPN.
C. Chỉ ẩn trường nhạy cảm trên UI mà giữ nguyên database.
D. Dùng dữ liệu giả lập hoặc đã khử định danh có kiểm soát.
Đáp án đúng: D

Câu 7. Mỗi merge request cần URL độc lập để reviewer kiểm thử giao diện, không ảnh hưởng staging chung. Thiết kế nào thích hợp?
A. Cho từng MR dùng cùng database và endpoint production.
B. Để reviewer tự khởi tạo máy chủ rồi bàn giao thủ công.
C. Tạo preview environment theo MR và tự hủy khi đóng MR.
D. Dùng staging cố định, lần lượt ghi đè bằng các nhánh MR.
Đáp án đúng: C

Câu 8. Các preview environment bị bỏ quên làm hóa đơn cloud tăng. Biện pháp nào vừa giảm chi phí vừa giữ truy vết sở hữu?
A. Chỉ tắt logging trên preview để không tốn dung lượng.
B. Giảm quyền xem báo cáo chi phí của đội phát triển.
C. Áp TTL tự dọn, gắn nhãn chủ sở hữu và giới hạn quota.
D. Cho preview tồn tại vô hạn để không cần tạo lại lần sau.
Đáp án đúng: C

Câu 9. Một kỹ sư chỉnh security group production bằng tay làm lệch Terraform. Bước nào phát hiện và xử lý drift đúng quy trình?
A. Ghi chú thay đổi trong wiki mà không cập nhật khai báo IaC.
B. Áp lại toàn bộ môi trường từ đầu mà không đánh giá thay đổi.
C. Chỉ xem lịch sử Git vì thay đổi thủ công không sửa repo.
D. So trạng thái thực với IaC bằng plan và review cách đồng bộ.
Đáp án đúng: D

Câu 10. Nhóm triển khai production phải kiểm soát ai phê duyệt thay đổi và cấu hình nào đã được áp dụng. Cách tổ chức nào phù hợp?
A. Cho mọi kỹ sư thao tác trực tiếp rồi ghi chú sau release.
B. Bỏ gate nếu pipeline build thành công trên nhánh chính.
C. Dùng phê duyệt có phân quyền, lưu plan và nhật ký triển khai.
D. Để reviewer duyệt commit rồi deploy không lưu lại nhật ký thực thi.
Đáp án đúng: C

Câu 11. Các môi trường dùng chung một source code nhưng có URL dịch vụ phụ trợ và feature flag khác nhau. Nên quản lý cấu hình ra sao?
A. Thay source code trước mỗi lần build tương ứng môi trường.
B. Dùng cấu hình có phiên bản với tham số riêng theo môi trường.
C. Chỉ thay giá trị trong container chạy mà không lưu thay đổi.
D. Dùng một file cấu hình cố định cho mọi giai đoạn phát hành.
Đáp án đúng: B

Câu 12. Ứng dụng được rolling deploy nên bản cũ và bản mới cùng tồn tại khi thay schema database. Cách migration nào an toàn hơn?
A. Xóa ngay cột cũ trước khi đưa bản ứng dụng mới lên.
B. Đổi tên tất cả cột trong một bước khi traffic còn chạy.
C. Áp dụng expand–contract giữ tương thích trong giai đoạn chuyển.
D. Chỉ chạy migration ở production và bỏ kiểm thử tương thích trên staging.
Đáp án đúng: C

Câu 13. Hai bộ integration test cùng thao tác queue và dữ liệu dùng chung nên thường thất bại ngẫu nhiên. Hướng khắc phục nào hiệu quả?
A. Cô lập namespace, dữ liệu và tài nguyên cho mỗi bộ test.
B. Chạy mọi bộ test trong production để tăng độ tin cậy.
C. Dùng chung queue nhưng tăng số lần retry đến khi qua.
D. Ghi đè dữ liệu test sau mỗi job mà không tách phiên chạy.
Đáp án đúng: A

Câu 14. Đội có backup database hằng ngày nhưng chưa từng phục hồi khi gặp sự cố. Cách nào đánh giá khả năng khôi phục thực tế?
A. Định kỳ restore vào môi trường cô lập và đo RPO/RTO.
B. Chỉ kiểm tra job backup báo success trên dashboard.
C. Chỉ gia hạn thời gian lưu snapshot qua từng quý.
D. Thử phục hồi trực tiếp lên production đang có traffic.
Đáp án đúng: A

Câu 15. Staging đang tốn chi phí gần bằng production dù tải thấp. Cách giảm chi phí nào vẫn giữ giá trị kiểm chứng?
A. Loại bỏ xác thực để tối ưu chi phí môi trường staging.
B. Giữ đường deploy và cấu hình chính, thu nhỏ năng lực xử lý.
C. Thay database bằng file giả lập dù đang thử migration.
D. Tắt toàn bộ telemetry và TLS để giảm mức dùng tài nguyên.
Đáp án đúng: B

Câu 16. Preview environment chỉ phục vụ review một merge request và cần gọi dịch vụ bên ngoài. Cách cấp quyền nào phù hợp?
A. Cấp credential ngắn hạn, giới hạn phạm vi vào tài nguyên thử.
B. Chép secret production vào preview để kết quả giống thật.
C. Đưa token dùng chung vào manifest để reviewer tự triển khai preview.
D. Cấp tài khoản quản trị production cho mọi preview job.
Đáp án đúng: A
