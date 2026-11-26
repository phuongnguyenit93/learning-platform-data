Câu 1: Ứng dụng cũ không thể chạy hai phiên bản đồng thời, đội chấp nhận gián đoạn ngắn. Chọn cách triển khai nào?
A. Rolling Update duy trì pod cũ khi khởi chạy pod mới.
B. Recreate dừng phiên bản cũ trước khi chạy bản mới.
C. Blue-Green giữ hai môi trường để chuyển lưu lượng.
D. Canary cho bản mới nhận một phần yêu cầu song song.
Đáp án đúng: B

Câu 2: Có đủ tài nguyên duy trì hai môi trường; cần đổi lưu lượng nhanh sau khi kiểm chứng bản mới. Chọn chiến lược nào?
A. Recreate thay toàn bộ instance rồi nhận lại traffic.
B. Rolling Update lần lượt thay pod trong cùng cụm.
C. Canary tăng dần tỷ trọng yêu cầu qua nhiều bước.
D. Blue-Green chuyển traffic giữa hai môi trường.
Đáp án đúng: D

Câu 3: Deployment có sáu replica, Rolling Update đặt `maxSurge: 1`, `maxUnavailable: 0`. Điều nào được phép?
A. Số pod khả dụng có thể giảm xuống năm khi thay bản.
B. Bắt buộc tạo đủ sáu pod mới cùng một lượt.
C. Có thể có thêm một pod vượt số replica mong muốn.
D. Mọi pod cũ bị xóa hết trước khi tạo pod mới.
Đáp án đúng: C

Câu 4: Cụm không đủ chỗ chạy thêm pod; Rolling Update đặt `maxSurge: 0`, `maxUnavailable: 1`. Đánh đổi nào dự kiến?
A. Luôn phải có hai phiên bản với số pod bằng nhau.
B. Cần thêm node trước khi quá trình có thể bắt đầu.
C. Có thể thiếu tạm một pod khả dụng khi cập nhật.
D. Pod mới bắt buộc nhận toàn bộ traffic ngay lập tức.
Đáp án đúng: C

Câu 5: Đội muốn thử bản mới bằng 5% yêu cầu thực và tăng dần nếu đạt ngưỡng chất lượng. Chiến lược nào phù hợp?
A. Recreate dừng toàn bộ pod cũ trước khi phục vụ bản mới.
B. Canary đưa một phần nhỏ traffic sang bản mới trước.
C. Blue-Green chuyển toàn bộ traffic trong một lần.
D. Rolling Update chỉ thay pod tuần tự theo lô.
Đáp án đúng: B

Câu 6: Pod mới khởi động nhưng phải tải cache trong 40 giây. Cơ chế nào ngăn gửi request quá sớm?
A. Liveness probe quyết định khi nào restart pod lỗi.
B. Readiness probe chỉ cho route khi ứng dụng sẵn sàng.
C. Startup probe tự đặt tỷ lệ traffic sang pod mới.
D. Termination grace period giữ pod sau khi tắt.
Đáp án đúng: B

Câu 7: Blue-Green vừa chuyển LB sang Green, tỷ lệ lỗi tăng; Blue còn khỏe, schema tương thích. Rollback nhanh bằng cách nào?
A. Rebuild Green từ nhánh main rồi triển khai đè.
B. Tắt toàn bộ LB trong khi tạo lại cluster Blue.
C. Xóa Blue để tránh ghi dữ liệu trùng giữa hai bản.
D. Chuyển định tuyến về Blue và xác minh dịch vụ.
Đáp án đúng: D

Câu 8: Tại sao Recreate có nguy cơ tạo khoảng gián đoạn phục vụ cho ứng dụng web?
A. Pod cũ bị dừng trước khi bản mới sẵn sàng xử lý.
B. Pod mới luôn chạy song song với toàn bộ pod cũ.
C. Ingress bắt buộc chia 5% yêu cầu cho bản mới.
D. Mọi lần deploy đều phải nhân đôi số node.
Đáp án đúng: A

Câu 9: Canary đang nhận 10% yêu cầu; tỷ lệ 5xx vượt ngưỡng rollback được thống nhất. Nên làm gì?
A. Tăng ngay canary lên 50% để xác nhận sự cố.
B. Dừng mở rộng và trả lưu lượng về bản ổn định.
C. Tắt cảnh báo rồi chờ quá trình rollout kết thúc.
D. Khôi phục toàn bộ DB dù migration không liên quan.
Đáp án đúng: B

Câu 10: Canary nhận 5% traffic nhưng tỷ lệ lỗi trung bình cả hệ thống không đổi. Cách phát hiện hồi quy nào phù hợp?
A. So error rate và latency tách riêng theo phiên bản.
B. Chỉ xem trạng thái Deployment sau khi rollout xong.
C. Chỉ so CPU trung bình toàn cụm trước và sau deploy.
D. Chỉ đọc số lần restart của bản ổn định.
Đáp án đúng: A

Câu 11: Phiên bản mới dùng cột DB mới nhưng cần rollback ứng dụng cũ. Kế hoạch schema nào an toàn?
A. Thêm cột tương thích, chuyển dần rồi mới loại cột cũ.
B. Xóa cột cũ trước khi triển khai phiên bản mới.
C. Đổi tên cột ngay rồi rollback bằng khôi phục toàn DB.
D. Dừng database trong suốt thời gian hai bản cùng chạy.
Đáp án đúng: A

Câu 12: Hai Deployment cùng được một Kubernetes Service chọn không bảo đảm chia request 90/10. Cần cơ chế nào?
A. Chỉ chia số replica theo tỷ lệ 9:1 để chắc chắn 90/10.
B. Chỉ bật liveness probe ở cả hai Deployment.
C. Dùng ingress, gateway hay service mesh có trọng số.
D. Gán cùng nhãn `version: canary` cho tất cả pod.
Đáp án đúng: C

Câu 13: Blue-Green đổi tuyến khi còn nhiều kết nối WebSocket tới môi trường Blue. Cách giảm ngắt phiên?
A. Tắt Blue ngay sau khi đổi route và xóa pod cũ.
B. Chỉ tăng thời gian startup của môi trường Green.
C. Giữ toàn bộ state phiên trong bộ nhớ pod Blue.
D. Drain kết nối cũ và bảo đảm state phiên tương thích.
Đáp án đúng: D

Câu 14: Kubernetes báo rollout hoàn tất nhưng khách vẫn không thanh toán được. Cách xác nhận bản phát hành khỏe?
A. Chỉ kiểm tra `kubectl rollout status` báo thành công.
B. Chỉ kiểm tra pod Ready và không có lần restart.
C. Chỉ kiểm tra image digest khớp artifact đã duyệt.
D. Kiểm giao dịch thật/synthetic, lỗi và độ trễ.
Đáp án đúng: D

Câu 15: Rolling Update đặt `maxUnavailable: 0` nhưng pod mới không qua readiness probe. Điều gì có thể xảy ra?
A. Kubernetes xóa mọi pod cũ để tránh rollout bị kẹt.
B. Service định tuyến mọi request sang pod chưa Ready.
C. Rollout bị kẹt, pod cũ khả dụng vẫn được duy trì.
D. Deployment tự rollback revision cũ ngay khi probe lỗi.
Đáp án đúng: C

Câu 16: Canary chỉ nhận ba request trong năm phút và chưa lỗi. Trước khi mở lên 100%, cần làm gì?
A. Quan sát đủ mẫu đại diện và xác minh chất lượng đạt ngưỡng.
B. Mở ngay 100% vì ba request chưa lỗi, xem đó là đủ bằng chứng.
C. Tắt canary vì ít request chứng tỏ bản mới hỏng.
D. Bỏ metric theo bản, chỉ xem CPU trung bình của cụm.
Đáp án đúng: A
