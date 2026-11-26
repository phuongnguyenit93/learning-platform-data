Câu 1: Báo cáo chi phí sử dụng ghi 80 triệu đồng, nhưng số tiền phải trả trên hóa đơn là 86 triệu. Cách đối soát nào xác định đúng phần chênh lệch?
A. So sánh số lượng tài nguyên theo từng tag đã ghi trên hai kỳ hóa đơn.
B. So sánh số máy ảo đang chạy ở thời điểm cuối của mỗi kỳ.
C. Đối chiếu dòng thuế, tín dụng, phí hỗ trợ với chi phí sử dụng.
D. Đối chiếu số vùng triển khai và loại máy giữa hai kỳ hóa đơn.
Đáp án đúng: C

Câu 2: Nhiều tài nguyên mới không có tag dự án nên báo cáo chi phí theo nhóm thiếu dữ liệu. Biện pháp nào xử lý từ gốc?
A. Dựa trên tên tài nguyên để tự đoán dự án vào cuối tháng.
B. Gộp chi phí chưa có tag vào nhóm đang có ngân sách lớn nhất trong kỳ.
C. Lập bảng tính phân bổ các tài nguyên thủ công vào cuối tháng.
D. Bắt buộc tag dự án khi tạo tài nguyên và theo dõi phần thiếu tag.
Đáp án đúng: D

Câu 3: Hai ứng dụng A và B dùng chung NAT gateway. Khi cần phân bổ phần phí truyền dữ liệu, cách nào có cơ sở nhất?
A. Phân bổ theo lưu lượng thực tế của từng ứng dụng qua gateway.
B. Chia đều chi phí hằng tháng, không xét lưu lượng qua gateway.
C. Dồn toàn bộ chi phí cho ứng dụng được triển khai sớm hơn.
D. Dồn chi phí cho ứng dụng có ngân sách được cấp lớn hơn.
Đáp án đúng: A

Câu 4: Ngày 20, chi phí thực tế đạt 72% ngân sách tháng, nhưng dự báo cuối tháng là 115%. Hành động nào hợp lý?
A. Chỉ gửi cảnh báo khi chi phí thực tế đạt 100% ngân sách.
B. Nâng ngân sách tự động để chỉ số tiêu dùng không vượt ngưỡng.
C. Cảnh báo nguy cơ vượt ngân sách, kiểm tra nguồn tăng chi phí.
D. Chờ hóa đơn chốt cuối tháng rồi mới phân tích lý do vượt.
Đáp án đúng: C

Câu 5: Dữ liệu hai năm cho thấy tải cửa hàng trực tuyến tăng mạnh mỗi dịp lễ; tháng tới có chiến dịch marketing. Dự báo nào hữu ích?
A. Lấy chi phí ngày gần nhất nhân với số ngày tháng tiếp theo.
B. Dùng lịch sử mùa vụ và kế hoạch chiến dịch để dự báo nhu cầu.
C. Giữ dự báo bằng đúng hạn mức ngân sách đã duyệt cho tháng.
D. Lấy trung bình toàn bộ tháng trước rồi bỏ qua ngày cao điểm.
Đáp án đúng: B

Câu 6: Chi phí lưu trữ của một nhóm tăng gấp ba sau lần phát hành, dù lưu lượng khách hàng không đổi. Bước điều tra đầu tiên là gì?
A. Tăng ngân sách lưu trữ để cảnh báo không tiếp tục kích hoạt.
B. Tắt các bucket mới trong nhóm để loại ngay phần chi phí tăng.
C. Đổi toàn bộ dữ liệu sang lớp lưu trữ lạnh trong ngày phát hiện.
D. Phân rã phí theo bucket, loại phí và mức dùng so với trước.
Đáp án đúng: D

Câu 7: Một VM có CPU trung bình 12% nhưng CPU p99 là 90%, RAM p95 là 78% và độ trễ tăng giờ cao điểm. Quyết định rightsizing nào phù hợp?
A. Thu nhỏ VM theo CPU trung bình để giảm phí ngay, rồi đánh giá sau.
B. Thử kích thước khác theo tải đỉnh, RAM và SLO trước khi đổi.
C. Tắt VM ngoài giờ cao điểm để tối ưu lượng CPU sử dụng.
D. Tăng thêm VM cùng loại để phân tán đỉnh CPU trên nhiều máy.
Đáp án đúng: B

Câu 8: Một volume không gắn với VM nào trong 45 ngày nhưng vẫn tính phí. Cách xử lý nào cân bằng tiết kiệm và rủi ro mất dữ liệu?
A. Xác minh chủ sở hữu và nhu cầu, sao lưu cần thiết rồi mới xóa.
B. Xóa ngay volume vì không còn gắn với máy chủ chạy thực tế.
C. Giữ nguyên volume và tăng ngưỡng cảnh báo chi phí lưu trữ.
D. Sao chép volume sang vùng khác để hạn chế nguy cơ bị mất.
Đáp án đúng: A

Câu 9: Nhóm có phần tải compute chạy ổn định 24/7 trong 18 tháng, và phần tăng tải khó dự báo. Chiến lược mua compute nào có hiệu quả?
A. Dùng toàn bộ on-demand kể cả tải nền để tránh cam kết.
B. Cam kết toàn bộ công suất giờ cao điểm rồi để phần dư chạy nhàn rỗi.
C. Cam kết cho tải nền ổn định, dùng on-demand cho tải biến động.
D. Dùng spot cho toàn bộ tải nền và bỏ cấu hình chịu gián đoạn.
Đáp án đúng: C

Câu 10: Đội dữ liệu chạy batch chuyển đổi ảnh; tác vụ có checkpoint và có thể chạy lại khi bị ngắt. Mô hình compute nào nên xem xét?
A. Chạy máy on-demand cố định cả tháng để luôn có công suất.
B. Dùng spot cho batch và cấu hình tiếp tục từ checkpoint.
C. Mua cam kết công suất đỉnh dù tác vụ chỉ chạy mỗi tuần.
D. Dùng máy chuyên dụng riêng và vô hiệu cơ chế retry job.
Đáp án đúng: B

Câu 11: Sản phẩm mới chưa có lịch sử tải và số lượt yêu cầu biến động lớn. Kế hoạch mua năng lực compute ban đầu nào phù hợp?
A. Mua cam kết dài hạn theo công suất dự báo cao nhất.
B. Mua spot cho mọi thành phần kể cả giao dịch thời gian thực.
C. Giữ máy cố định theo cấu hình cao nhất của môi trường test.
D. Bắt đầu on-demand, đo tải nền rồi cân nhắc mua cam kết.
Đáp án đúng: D

Câu 12: Log bảo mật được đọc thường xuyên trong 14 ngày đầu, sau đó hiếm truy cập nhưng phải lưu 24 tháng. Lựa chọn lưu trữ nào hợp lý?
A. Duy trì lớp nóng 24 tháng để không phát sinh phí truy xuất.
B. Chuyển hết sang lớp archive từ ngày đầu để tối thiểu tiền lưu.
C. Tạo lifecycle từ lớp nóng sang lớp rẻ theo nhu cầu truy xuất.
D. Tải log về máy chủ xử lý, sau đó dừng lưu trong object storage.
Đáp án đúng: C

Câu 13: Chi phí truyền dữ liệu liên vùng tăng sau khi tách dịch vụ. Biện pháp nào nên đánh giá đầu tiên để tránh giảm chi phí sai cách?
A. Giảm TTL DNS của các dịch vụ liên vùng để ép kết nối chuyển lại.
B. Buộc truyền qua Internet công cộng để tránh các khoản phí nội vùng.
C. Tăng kích thước các VM để giảm số yêu cầu giữa các vùng.
D. Đo luồng truyền liên vùng và cân nhắc đặt gần dịch vụ phụ thuộc.
Đáp án đúng: D

Câu 14: Chi phí cloud giảm 10%, nhưng số đơn hoàn tất giảm 30% và thời gian xử lý tăng. Chỉ số nào phản ánh giá trị tốt hơn tổng chi phí?
A. Chi phí trên mỗi đơn thành công, kèm chỉ số độ trễ dịch vụ.
B. Tổng số VM giảm trong tháng, kèm thay đổi kích thước máy.
C. Tổng mức chi cloud so với tháng trước, không xét số đơn xử lý.
D. Số nhóm dự án được gắn tag, kèm tỷ lệ tài nguyên có tag.
Đáp án đúng: A

Câu 15: Doanh nghiệp đã trả trước cam kết compute nhưng nhiều giờ năng lực mua trước không được dùng. Phân tích nào phát hiện lãng phí thực?
A. Đo tỷ lệ sử dụng cam kết và so sánh với mức tải nền.
B. Đo phần trăm giờ VM chạy của toàn hệ thống theo mỗi vùng.
C. Đo số lần triển khai phần mềm trên từng máy trong tháng.
D. Đo tỷ lệ tăng ngân sách đã phê duyệt từ đầu mỗi quý.
Đáp án đúng: A

Câu 16: Đề xuất tiết kiệm bằng cách giảm replica làm chi phí giảm, nhưng p95 latency vượt SLO. Nhóm FinOps nên quyết định thế nào?
A. Giữ nguyên thay đổi để tiết kiệm dù độ trễ tăng khi tải cao.
B. Đảm bảo lại SLO, rồi tối ưu chi phí trên mỗi đơn thành công.
C. Tăng ngân sách để hệ thống tiếp tục chạy với độ trễ hiện tại.
D. Dừng theo dõi SLO vì ngân sách là ưu tiên của kỳ đánh giá.
Đáp án đúng: B
