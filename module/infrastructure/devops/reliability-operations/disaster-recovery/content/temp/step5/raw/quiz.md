Câu 1: Cổng thanh toán chấp nhận mất tối đa 10 phút giao dịch khi xảy ra thảm họa. Mục tiêu nào diễn đạt giới hạn mất dữ liệu đó?
A. RTO 10 phút: thời hạn đưa dịch vụ hoạt động lại.
B. MTTR 10 phút: thời gian khắc phục sự cố trung bình.
C. RPO 10 phút: khoảng dữ liệu có thể bị mất.
D. SLA 10 phút: tổng downtime cho phép trong kỳ.
Đáp án đúng: C

Câu 2: Dịch vụ đặt hàng phải hoạt động lại trong 30 phút sau sự cố, dù vẫn chấp nhận mất 5 phút dữ liệu. Mốc 30 phút thuộc mục tiêu nào?
A. RTO: giới hạn thời gian phục hồi dịch vụ.
B. RPO: giới hạn độ cũ dữ liệu có thể mất.
C. MTTD: thời gian trung bình nhận biết lỗi.
D. Backup window: thời lượng dành cho sao lưu.
Đáp án đúng: A

Câu 3: Doanh nghiệp có 20 dịch vụ và cần xếp thứ tự khôi phục sau mất cả trung tâm dữ liệu. Phương pháp nào xét cả tác động kinh doanh lẫn phụ thuộc?
A. Chỉ xếp theo chi phí vận hành của từng dịch vụ.
B. Chỉ xếp theo lượng dữ liệu lưu của từng dịch vụ.
C. Chỉ xếp theo thời gian hoàn thành backup gần nhất.
D. Dùng BIA đánh giá tác động và quan hệ phụ thuộc.
Đáp án đúng: D

Câu 4: Một bảng dữ liệu bị xóa nhầm và thao tác xóa lập tức lan sang vùng replica. Vì sao replication không thể tự thay thế backup?
A. Replica luôn giữ đủ mọi phiên bản dữ liệu cũ.
B. Replica chỉ có thể đọc, không thể ghi dữ liệu.
C. Replica luôn phục hồi được mọi bản ghi đã xóa.
D. Lệnh xóa hoặc dữ liệu lỗi có thể lan sang replica.
Đáp án đúng: D

Câu 5: Kẻ tấn công chiếm quyền ứng dụng và cố xóa mọi bản sao lưu bằng cùng thông tin xác thực. Biện pháp nào tăng khả năng cứu dữ liệu?
A. Tăng tần suất backup nhưng giữ nguyên quyền xóa.
B. Giữ backup bất biến, tách quyền quản trị xóa.
C. Sao chép thêm dữ liệu vào ổ đĩa đang vận hành.
D. Chuyển backup sang cùng tài khoản với ứng dụng.
Đáp án đúng: B

Câu 6: DB giao dịch bị xóa bảng lúc 14:07; cần quay về 14:06 thay vì snapshot lúc 00:00. Cơ chế nào đáp ứng được nếu đã chuẩn bị đầy đủ?
A. Snapshot hằng ngày không có transaction log.
B. Replica đồng bộ tự động theo lệnh xóa bảng.
C. PITR từ backup và transaction log được lưu.
D. Khởi động lại database trên máy chủ mới.
Đáp án đúng: C

Câu 7: DB đang ghi nhiều giao dịch; cần backup có thể restore ở trạng thái nhất quán ứng dụng trên nhiều volume. Cách thực hiện nào phù hợp?
A. Tạm dừng ghi DB, snapshot nhất quán và giữ log.
B. Chụp tuần tự từng volume trong lúc ghi liên tục.
C. Chỉ sao chép tệp đang mở bằng đồng bộ thư mục.
D. Tăng số bản snapshot mà không điều phối giao dịch.
Đáp án đúng: A

Câu 8: Vùng dự phòng chỉ giữ hạ tầng lõi và bản sao dữ liệu; khi thảm họa mới triển khai đủ lớp ứng dụng. Đây là chiến lược nào?
A. Pilot light: giữ lõi, mở rộng khi có sự cố.
B. Warm standby: ứng dụng chạy thu nhỏ sẵn.
C. Active-active: cả hai vùng nhận traffic thực.
D. Backup/restore: chỉ lưu backup, chưa giữ lõi.
Đáp án đúng: A

Câu 9: Một vùng DR luôn chạy bản ứng dụng quy mô nhỏ cùng bản sao dữ liệu; khi failover sẽ tăng công suất để nhận tải chính. Tên chiến lược phù hợp?
A. Pilot light: chỉ duy trì phần lõi tối thiểu.
B. Active-active: hai vùng cùng nhận tải sản xuất.
C. Backup/restore: chỉ khởi dựng sau khi lỗi.
D. Warm standby: chạy ứng dụng với công suất giảm.
Đáp án đúng: D

Câu 10: Runbook dự kiến bật giao diện web trước khi IAM và cơ sở dữ liệu phục hồi, dẫn tới health check liên tục thất bại. Nên cải tiến gì?
A. Tăng CPU frontend để vượt qua kiểm tra sức khỏe.
B. Chuyển giao diện sang AZ khác nhưng giữ thứ tự.
C. Giảm tần suất kiểm tra kết nối tới DB.
D. Lập dependency graph và phục hồi dịch vụ nền trước.
Đáp án đúng: D

Câu 11: Hai vùng mất kết nối mạng; nếu cùng nhận ghi giao dịch sẽ sinh split-brain. Cơ chế nào bảo vệ tính nhất quán khi failover?
A. Giảm DNS TTL để cả hai vùng cùng nhận write.
B. Giữ cả hai writer rồi đối soát thủ công sau đó.
C. Dùng fencing hoặc lease để chỉ một writer hợp lệ.
D. Tăng số read replica để bù trễ liên vùng.
Đáp án đúng: C

Câu 12: Sau sáu giờ chạy tại DR, vùng chính đã hoạt động trở lại. Trước khi failback lưu lượng ghi, nhóm cần làm gì?
A. Chuyển DNS về vùng chính ngay khi máy chủ khởi động.
B. Đồng bộ ngược, đối soát dữ liệu rồi chuyển ghi.
C. Xóa vùng DR trước khi tạo tài nguyên chính.
D. Bật hai vùng cùng ghi để tránh mất dịch vụ.
Đáp án đúng: B

Câu 13: Kế hoạch yêu cầu RTO 45 phút và RPO 5 phút, nhưng nhóm mới chỉ viết runbook. Hoạt động nào kiểm chứng hai mục tiêu thực tế?
A. Diễn tập khôi phục, đo thời gian và đối soát dữ liệu.
B. Chỉ đọc runbook trong buổi họp với quản trị viên.
C. Chỉ xác nhận các tác vụ backup chạy thành công.
D. Chỉ quan sát dashboard replication không thử phục hồi.
Đáp án đúng: A

Câu 14: Đã đổi bản ghi DNS khi failover và đặt TTL mới 30 giây nhưng một số client vẫn truy cập endpoint cũ nhiều phút. Giải thích nào phù hợp?
A. TTL mới buộc resolver lập tức hủy mọi cache cũ.
B. DB replica còn trễ nên DNS giữ địa chỉ nguồn.
C. Resolver có cache cũ hoặc kết nối vẫn còn mở.
D. Load balancer ngăn DNS phân giải bản ghi mới.
Đáp án đúng: C

Câu 15: Backup job báo thành công, nhưng đội vận hành chưa chắc ứng dụng khởi động được từ bản sao. Kiểm tra nào có giá trị nhất?
A. So kích thước và số tệp backup với lịch cũ.
B. Restore thử, đối soát dữ liệu và nghiệp vụ.
C. Chỉ xác nhận checksum của tệp backup nguồn.
D. Chỉ xem thời gian hoàn thành của backup job.
Đáp án đúng: B

Câu 16: Nhân sự trực ca thường xuyên thay đổi; khi thảm họa cần thao tác DR có thể lặp lại và phân rõ người quyết định. Runbook nên chứa gì?
A. Danh sách máy chủ và dung lượng từng bản sao.
B. Có điều kiện, vai trò, các bước và kiểm tra.
C. Danh sách lịch backup và thời hạn lưu dữ liệu.
D. Các đường dẫn dashboard và biểu đồ gần đây.
Đáp án đúng: B
