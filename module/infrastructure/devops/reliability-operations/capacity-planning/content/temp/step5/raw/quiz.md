Câu 1. Traffic API có đỉnh gấp ba mức trung bình ngày và dự kiến tăng trưởng 20%. Cơ sở nào hợp lý nhất để lập kế hoạch năng lực?
A. Dùng tải trung bình ngày tăng 20% làm mốc cấp máy chủ thường trực.
B. Giữ công suất hiện có vì đa số thời gian vẫn còn CPU rảnh.
C. Dùng đỉnh dự báo có tăng trưởng, kiểm tra SLO và headroom.
D. Chọn mức p50 của các giờ làm việc để loại tải đột biến.
Đáp án đúng: C

Câu 2. Một instance xử lý bền vững 200 request/s trong SLO. Cần phục vụ 600 request/s ngay cả khi hỏng một instance; số instance tối thiểu là bao nhiêu?
A. 4 instance, để ba instance còn lại phục vụ đủ tải.
B. 3 instance, vì tổng công suất khi đủ máy là 600.
C. 5 instance, vì phải dự phòng hai máy hỏng cùng một thời điểm.
D. 6 instance, vì cần giữ dự phòng ba máy ngay cả khi tải ổn định.
Đáp án đúng: A

Câu 3. Theo định luật Little, hệ thống nhận trung bình 80 request/s và thời gian phản hồi trung bình 0,25 giây ở trạng thái ổn định. Số request đồng thời trung bình là bao nhiêu?
A. 80 request, bằng số request nhận trong một giây.
B. 320 request, tính bằng 80 chia cho 0,25.
C. 200 request, tính bằng 80 nhân với 2,5.
D. 20 request, tính bằng 80 request/s nhân với 0,25 giây.
Đáp án đúng: D

Câu 4. API stateless đạt CPU 95% và p99 latency tăng khi nhiều người truy cập; DB và mạng còn dư. Hành động nào nhắm đúng nút thắt?
A. Tăng replica ứng dụng và kiểm tra phân phối tải qua pod.
B. Mở rộng pool kết nối DB để mỗi pod gửi thêm truy vấn song song.
C. Tăng timeout client để request có thêm thời gian xử lý.
D. Tăng độ sâu hàng đợi vào API mà không thêm CPU.
Đáp án đúng: A

Câu 5. CPU API thấp nhưng truy vấn p99 cao, database IOPS gần trần và I/O wait tăng. Hướng điều tra nào nên ưu tiên?
A. Rà slow query, chỉ mục và giới hạn I/O của database.
B. Thêm API replica để dồn truy vấn qua nhiều kết nối database.
C. Tăng thread pool API dù DB đang chờ đọc ghi đĩa.
D. Nâng timeout API để giảm số request bị trả lỗi.
Đáp án đúng: A

Câu 6. Trong soak test với lưu lượng ổn định, RSS của pod tăng dần tới OOMKilled sau nhiều giờ. Hướng xử lý nào phù hợp?
A. Tăng memory limit ngay rồi ngừng mọi bài soak test.
B. Profile bộ nhớ, xác định leak rồi chạy lại bài soak test.
C. Thêm replicas rồi bỏ theo dõi lượng nhớ mỗi process.
D. Giảm tần suất health probe để pod không bị khởi động.
Đáp án đúng: B

Câu 7. Queue nhận liên tục 900 message/s và worker xử lý bền vững 700 message/s, không mất message. Backlog tăng hoặc giảm thế nào?
A. Giảm 200 message mỗi giây khi tải không đổi.
B. Giữ nguyên số message vì worker chạy liên tục.
C. Tăng 200 message mỗi giây do lượng nhận vượt lượng xử lý.
D. Tăng 900 message mỗi giây vì đó là lượng nhận vào.
Đáp án đúng: C

Câu 8. Pod Kubernetes đặt CPU request 500m và CPU limit 1000m. Nhận định nào đúng về hai giá trị này?
A. Scheduler dùng CPU limit để xếp pod; request chỉ phục vụ giám sát tải.
B. Scheduler dùng request để xếp pod; limit giới hạn CPU lúc chạy.
C. Scheduler dùng CPU thực đo để xếp pod; request bị bỏ qua.
D. HPA chỉ dựa vào CPU limit; request không tác động kết quả.
Đáp án đúng: B

Câu 9. HPA dựa trên CPU utilization so với CPU request. Nếu request quá thấp so với mức dùng thông thường, hiện tượng nào có thể xảy ra?
A. Utilization báo cao khiến HPA mở rộng replica sớm.
B. Utilization báo thấp khiến HPA thu nhỏ replica sớm.
C. HPA bỏ qua request và chỉ tính theo CPU limit.
D. Scheduler tự nâng request khi lưu lượng đạt đỉnh.
Đáp án đúng: A

Câu 10. HPA đã tăng replica nhưng pod mới Pending do node thiếu CPU allocatable; quota không chặn. Cần tăng năng lực ở lớp nào?
A. Tăng maxReplicas của HPA để tạo thêm nhiều pod chờ được lập lịch.
B. Nâng CPU limit của pod để node có thêm CPU rảnh.
C. Bổ sung node bằng cluster autoscaler hoặc mở rộng cụm.
D. Giảm readiness probe để Scheduler xếp pod sớm hơn.
Đáp án đúng: C

Câu 11. Load test giữ 100 virtual user; khi ứng dụng chậm, mỗi user gửi ít request nên tải chào vào giảm. Thiết kế thử nghiệm nào phát hiện quá tải tốt hơn?
A. Giữ closed-loop và tăng timeout HTTP client để mô phỏng mạng chậm.
B. Dùng open-loop theo arrival rate và đo p99 cùng tỷ lệ lỗi.
C. Chỉ đo throughput thành công, bỏ các request timeout.
D. Giảm số virtual user để request hoàn tất nhanh hơn.
Đáp án đúng: B

Câu 12. Hai AZ active-active chia đều traffic; hệ thống phải chịu mất một AZ ở giờ cao điểm mà vẫn đạt SLO. Cần thiết kế theo điều kiện nào?
A. Tổng năng lực hai AZ đủ đỉnh khi chúng cùng hoạt động.
B. Năng lực AZ còn lại đủ đỉnh tải theo giới hạn SLO.
C. Mỗi AZ chỉ cần đủ mức tải trung bình của ngày.
D. Tổng CPU request ngang mức CPU đã dùng khi bình thường.
Đáp án đúng: B

Câu 13. Dịch vụ cloud có tải nền ổn định và đỉnh ngắn một đến hai giờ mỗi ngày. Kế hoạch nào giữ SLO với chi phí hợp lý?
A. Mua và chạy công suất cố định theo đỉnh cao nhất.
B. Dùng toàn bộ spot instance cho cả thành phần tối quan trọng.
C. Giảm công suất nền dưới nhu cầu rồi phụ thuộc vào retry.
D. Giữ capacity nền theo tải thường trực, autoscale cho các đỉnh.
Đáp án đúng: D

Câu 14. Throughput database giảm, CPU còn dư nhưng số transaction chờ lock tăng mạnh. Biện pháp nào nhắm đúng nút thắt?
A. Tăng pool kết nối để cho nhiều giao dịch cùng đợi và tranh chấp khóa.
B. Nhân bản nhiều API pod để đẩy thêm truy vấn tới DB.
C. Giảm tranh chấp khóa bằng tối ưu giao dịch và truy vấn.
D. Chỉ nâng CPU quota cho DB mà không xem wait event.
Đáp án đúng: C

Câu 15. Pod Kubernetes yêu cầu CPU 2000m nhưng p95 usage 300m, không throttling và SLO còn dư. Để giảm lãng phí node, nên làm gì?
A. Giữ request 2000m, đồng thời tăng số node để dự phòng cho tải thấp.
B. Đặt CPU limit 300m ngay vì đó là mức dùng ở p95.
C. Tắt HPA nhằm tránh thêm replica vào giờ cao điểm.
D. Rightsize request theo tải kiểm chứng, chừa biên an toàn.
Đáp án đúng: D

Câu 16. Traffic tăng 30% sau launch, p99 vẫn đạt SLO nhưng cluster gần node quota khi cao điểm. Bước lập kế hoạch tiếp theo là gì?
A. Giữ dự báo cũ vì độ trễ chưa vượt ngưỡng SLO.
B. Giảm lượng log phát sinh để CPU hiện có được phân bổ cho request.
C. Chỉ tăng maxReplicas dù node quota vẫn giữ nguyên.
D. Cập nhật dự báo, kiểm thử giới hạn và kế hoạch quota.
Đáp án đúng: D
