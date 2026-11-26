Câu 1: Một image đã qua kiểm thử ở staging; nhóm muốn triển khai đúng cùng bộ byte sang production, tránh tag bị trỏ sang bản khác. Nên tham chiếu artifact thế nào?
A. Build lại image từ cùng Git commit khi phát hành.
B. Kéo image theo tag latest trên môi trường đích.
C. Triển khai image theo đúng digest đã kiểm thử.
D. Gắn tag production mới rồi build lại image.
Đáp án đúng: C

Câu 2: Cùng một ứng dụng cần endpoint API khác nhau giữa staging và production nhưng phải dùng chung image đã build. Nên đặt cấu hình ở đâu?
A. Cấp cấu hình môi trường khi khởi chạy ứng dụng.
B. Ghi endpoint riêng vào source trước mỗi lần build.
C. Đóng endpoint vào image ở bước đóng gói artifact.
D. Sửa file bên trong container sau khi nó chạy.
Đáp án đúng: A

Câu 3: Ứng dụng triển khai qua CI/CD cần mật khẩu DB ở production và đội bảo mật không cho lưu trong Git hay image. Phương án nào an toàn nhất?
A. Dùng IAM lấy secret khi chạy từ secret manager.
B. Mã hóa secret rồi commit cùng source của ứng dụng.
C. Đưa secret vào build argument khi tạo container.
D. Gắn mật khẩu vào tên artifact trong registry.
Đáp án đúng: A

Câu 4: Một pod vừa khởi chạy nhưng đang nạp dữ liệu khởi tạo; tiến trình vẫn sống, chưa thể nhận request. Probe nào nên chưa đạt để tránh chuyển traffic vào pod?
A. Startup probe xác nhận quá trình boot đã xong.
B. Readiness probe kiểm tra pod có thể nhận request.
C. Liveness probe kiểm tra tiến trình còn sống.
D. TCP probe chỉ xác nhận cổng đang lắng nghe.
Đáp án đúng: B

Câu 5: Khi thay phiên bản API, các kết nối đang xử lý cần hoàn thành thay vì bị cắt ngang lúc instance ngừng. Cách phối hợp nào phù hợp?
A. Xóa instance ngay khi scheduler tạo pod thay thế.
B. Giữ instance trong load balancer đến khi hết timeout.
C. Tăng liveness timeout để không phải xóa instance.
D. Ngừng nhận request mới rồi drain trước khi dừng.
Đáp án đúng: D

Câu 6: Dịch vụ đang chạy bốn replica và cần luôn có ít nhất bốn pod Ready trong rolling update; cluster còn đủ tài nguyên dự phòng. Cấu hình nào phù hợp?
A. Bỏ readiness probe để pod mới được tính ngay.
B. Đặt maxUnavailable=0, maxSurge ít nhất một.
C. Giữ tất cả pod cũ cho đến khi pipeline kết thúc.
D. Tăng retry client thay cho kiểm soát số pod.
Đáp án đúng: B

Câu 7: Phiên bản mới có nguy cơ tăng lỗi thanh toán. Nhóm muốn cho 5% traffic dùng bản mới trước khi mở rộng và dừng nếu lỗi tăng. Chọn chiến lược nào?
A. Recreate toàn bộ pod rồi kiểm tra lỗi sau đó.
B. Rolling thay từng pod theo thứ tự ngẫu nhiên.
C. Canary chia ít traffic, đo metric rồi mở rộng.
D. Blue-green chuyển toàn bộ traffic ngay khi sẵn sàng.
Đáp án đúng: C

Câu 8: Ứng dụng cần triển khai bản mới lên bộ server độc lập và chuyển toàn bộ traffic bằng một thao tác định tuyến, giữ bộ cũ để quay lại. Cách nào phù hợp?
A. Recreate dừng bộ cũ trước khi triển khai bản mới.
B. Canary đưa một phần người dùng sang bản mới.
C. Rolling thay từng server trong cùng backend pool.
D. Blue-green dùng hai môi trường, chuyển traffic.
Đáp án đúng: D

Câu 9: Cần đổi tên cột DB nhưng hai phiên bản ứng dụng sẽ chạy đồng thời vài giờ trong rolling rollout. Quy trình migration nào giảm rủi ro nhất?
A. Xóa ngay cột cũ rồi deploy toàn bộ bản mới.
B. Thêm cột, backfill/dual-write, bỏ cột cũ sau.
C. Đổi cột bằng thao tác thủ công giữa hai lần deploy.
D. Chỉ sửa ORM mapping mà giữ schema không đổi.
Đáp án đúng: B

Câu 10: Trong rolling deployment, client cũ vẫn gọi API khi server mới được đưa vào phục vụ. Yêu cầu nào quan trọng nhất đối với hợp đồng API?
A. Buộc client nâng bản trước mỗi lần đổi server.
B. Thay toàn bộ endpoint và chỉ giữ bản server mới.
C. Chấp nhận ngắt tạm các request từ client cũ.
D. Giữ API tương thích ngược khi hai bản cùng chạy.
Đáp án đúng: D

Câu 11: Release vừa lỗi sau khi migration đã xóa dữ liệu của một cột; nhóm muốn rollback container. Nhận định nào đúng về an toàn dữ liệu?
A. Đổi tag image sẽ tự phục hồi toàn bộ cột bị xóa.
B. Revert Git commit sẽ hoàn nguyên dữ liệu đã mất.
C. Restart DB sẽ tự dựng lại schema cũ và dữ liệu.
D. Rollback code không khôi phục dữ liệu đã bị xóa.
Đáp án đúng: D

Câu 12: Một nhóm muốn CI tự kiểm thử artifact và chỉ CD triển khai lên production sau khi qua gate, có thể truy vết bản đã phát hành. Pipeline nên tổ chức thế nào?
A. Build/test, lưu artifact rồi duyệt trước prod.
B. Build lại trong production để có cấu hình riêng.
C. Chạy apply production rồi chạy kiểm thử sau đó.
D. Chỉ kiểm tra Git branch trước khi đổi tag latest.
Đáp án đúng: A

Câu 13: Sau khi triển khai xong, orchestrator báo tất cả pod Ready nhưng khách hàng vẫn gặp lỗi đặt hàng. Cần bổ sung xác minh phát hành nào?
A. Smoke test nghiệp vụ, theo dõi tỷ lệ lỗi.
B. Chỉ kiểm tra hash của image trong registry.
C. Chỉ xác nhận build log không có lỗi compile.
D. Chỉ tăng số pod theo CPU của máy chủ.
Đáp án đúng: A

Câu 14: Một pipeline production cần chặn phát hành chưa được phê duyệt mà vẫn tự động hóa phần còn lại. Kiểm soát nào đúng nhất?
A. Cho phép mọi commit tự apply rồi gửi báo cáo sau.
B. Tắt pipeline khi có thay đổi cấu hình môi trường.
C. Gate phê duyệt trước bước triển khai production.
D. Giới hạn người đọc log nhưng giữ deploy tự động.
Đáp án đúng: C

Câu 15: Tính năng mới đã được deploy nhưng chưa muốn cho mọi khách hàng sử dụng; cần bật dần mà không build lại image. Cách nào hợp lý?
A. Tạo branch mới rồi deploy riêng cho từng user.
B. Giảm số replica của ứng dụng trong production.
C. Dùng feature flag bật tính năng theo nhóm.
D. Đổi tag image theo mỗi nhóm khách hàng.
Đáp án đúng: C

Câu 16: Canary làm tỷ lệ HTTP 5xx vượt ngưỡng sau triển khai. Pipeline cần phản ứng thế nào để hạn chế ảnh hưởng?
A. Đợi hết lịch phát hành rồi mới đánh giá lỗi.
B. Dừng rollout và trả traffic về bản ổn định.
C. Tăng request timeout để che tỷ lệ lỗi tạm thời.
D. Tắt cảnh báo và tiếp tục tăng canary traffic.
Đáp án đúng: B
