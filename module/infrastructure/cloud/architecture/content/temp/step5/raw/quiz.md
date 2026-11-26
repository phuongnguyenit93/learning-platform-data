Câu 1: Hệ thống đặt vé yêu cầu RTO tối đa 30 phút và RPO tối đa 5 phút. Phương án dự phòng nào đáp ứng đồng thời cả hai?
A. Sao lưu dữ liệu mỗi giờ, phục hồi hoàn toàn dịch vụ trong 20 phút.
B. Sao chép dữ liệu trễ tối đa 5 phút, phục hồi trong 30 phút.
C. Sao chép dữ liệu trễ tối đa 5 phút, phục hồi trong 2 giờ.
D. Sao lưu dữ liệu mỗi ngày, phục hồi dịch vụ trong 5 phút.
Đáp án đúng: B

Câu 2: Ứng dụng có ba tầng: cân bằng tải nhận Internet, xử lý nghiệp vụ và cơ sở dữ liệu chỉ được truy cập nội bộ. Bố trí subnet nào phù hợp?
A. Đặt cân bằng tải và máy chủ CSDL ở subnet công khai; xử lý ở subnet riêng.
B. Đặt cân bằng tải ở subnet riêng; xử lý và CSDL ở subnet công khai.
C. Đặt cân bằng tải và xử lý ở subnet công khai; CSDL ở subnet riêng.
D. Đặt cân bằng tải ở subnet công khai; xử lý và CSDL ở subnet riêng.
Đáp án đúng: D

Câu 3: Doanh nghiệp cần kết nối nhanh mạng tại văn phòng với VPC trên cloud qua Internet, có mã hóa đường truyền và không thuê kênh riêng. Nên chọn gì?
A. Thiết lập VPC peering giữa văn phòng và VPC trên cloud.
B. Thiết lập VPN site-to-site để nối mạng văn phòng với VPC.
C. Thiết lập NAT gateway giữa văn phòng và VPC trên cloud.
D. Thiết lập private endpoint giữa văn phòng và VPC trên cloud.
Đáp án đúng: B

Câu 4: API web không lưu trạng thái phiên trên máy, lưu lượng tăng gấp mười trong 15 phút mỗi tối. Cách thiết kế compute nào phù hợp về mở rộng và chi phí?
A. Duy trì số máy chủ cố định theo lưu lượng cao nhất cả ngày.
B. Dùng một máy chủ cấu hình lớn rồi nâng cấp khi tải tăng.
C. Đặt nhiều bản sao sau cân bằng tải và tự động tăng giảm số bản sao.
D. Tăng cấu hình cơ sở dữ liệu vào buổi tối để giảm tải API.
Đáp án đúng: C

Câu 5: Đặt hàng phải trả phản hồi nhanh dù dịch vụ gửi email có lúc chậm hoặc ngắt kết nối. Thiết kế nào giảm phụ thuộc mà vẫn giữ tác vụ gửi email?
A. Đưa email vào hàng đợi bền vững; worker thử lại và chống gửi trùng.
B. Gọi email đồng bộ trong luồng đặt hàng, tăng timeout khi gửi chậm.
C. Đưa email vào bộ nhớ tiến trình; worker gửi dần khi có tài nguyên rảnh.
D. Đưa email vào hàng đợi; worker xác nhận xong ngay khi vừa nhận.
Đáp án đúng: A

Câu 6: Khi chuyển tiền giữa hai tài khoản, hệ thống không được trừ tiền ở tài khoản nguồn nếu cộng tiền ở tài khoản đích thất bại. Cách lưu dữ liệu nào phù hợp nhất?
A. Ghi từng số dư vào cache rồi đồng bộ xuống CSDL theo lô.
B. Ghi hai số dư bằng hai transaction độc lập nối tiếp nhau.
C. Ghi hai số dư trong cùng một giao dịch ACID và rollback khi lỗi.
D. Ghi hai số dư vào hai kho dữ liệu rồi đồng bộ qua queue.
Đáp án đúng: C

Câu 7: Dịch vụ giao dịch phải tiếp tục hoạt động nếu một Availability Zone (AZ) ngừng hoàn toàn. Phương án triển khai nào đáp ứng yêu cầu này?
A. Đặt nhiều máy web và CSDL trong một AZ, bổ sung bản sao ổ đĩa.
B. Đặt web trên hai AZ, nhưng CSDL chính và bản sao cùng nằm trong một AZ.
C. Đặt web trong một AZ, còn CSDL chính và phụ ở hai AZ.
D. Đặt web trên hai AZ, CSDL có chuyển đổi dự phòng tự động liên AZ.
Đáp án đúng: D

Câu 8: Trang sản phẩm dùng cache để giảm độ trễ, nhưng giá bán cần cập nhật ngay sau khi quản trị viên lưu thay đổi. Cách quản lý cache phù hợp nhất?
A. Vô hiệu hóa cache giá ngay sau khi lưu thay đổi thành công vào CSDL.
B. Tăng TTL cache giá lên một ngày sau khi lưu thay đổi vào CSDL.
C. Chỉ làm mới cache giá khi có lần khởi động lại ứng dụng.
D. Cập nhật cache giá trước, ghi CSDL theo lô sau nhiều giờ.
Đáp án đúng: A

Câu 9: Dịch vụ xử lý ảnh cần đọc ảnh từ bucket nguồn và ghi ảnh thu nhỏ sang bucket đích. Cấp quyền nào tuân thủ nguyên tắc đặc quyền tối thiểu?
A. Cho phép đọc và ghi trên cả bucket nguồn lẫn bucket đích.
B. Cho phép đọc mọi bucket và ghi vào riêng bucket đích.
C. Cho phép đọc riêng bucket nguồn và ghi vào mọi bucket.
D. Cho phép đọc riêng bucket nguồn và ghi riêng bucket đích.
Đáp án đúng: D

Câu 10: Ứng dụng container phải xoay vòng mật khẩu CSDL định kỳ mà không build lại image; đội bảo mật muốn giới hạn quyền đọc và kiểm toán truy cập. Phương án nào phù hợp?
A. Lưu secret trong file mã hóa kèm image, thay khi phát hành image.
B. Lưu secret trong kho riêng có IAM, ứng dụng nạp lại khi đổi.
C. Lưu secret trong biến build của image, thay khi build phiên bản.
D. Lưu secret trong mã nguồn private, thay khi phát hành image.
Đáp án đúng: B

Câu 11: Hệ thống microservice vi phạm SLO độ trễ p95 nhưng metric tổng CPU vẫn bình thường. Bộ tín hiệu nào giúp xác định dịch vụ gây chậm qua một request?
A. Kết hợp metric độ trễ, log theo request ID và trace xuyên dịch vụ.
B. Kết hợp metric CPU, log theo tên máy và thống kê lỗi theo ngày.
C. Kết hợp metric lưu trữ, log ở gateway và kiểm tra DNS định kỳ.
D. Kết hợp metric traffic, log triển khai và biểu đồ chi phí theo giờ.
Đáp án đúng: A

Câu 12: Khi triển khai phiên bản mới của cổng thanh toán, nhóm muốn kiểm chứng trên một phần lưu lượng và tự quay lui nếu tỷ lệ lỗi tăng. Cách phát hành nào phù hợp?
A. Đẩy bản mới tới toàn bộ máy, kiểm tra lỗi khi quá trình kết thúc.
B. Triển khai vào giờ ít tải, chỉ quay lui sau khi có báo cáo thủ công.
C. Chuyển một ít lưu lượng sang bản mới, đo lỗi và rollback tự động.
D. Dừng hoàn toàn bản cũ, rồi chuyển tất cả lưu lượng sang bản mới.
Đáp án đúng: C

Câu 13: Các môi trường dev, staging và production thường lệch cấu hình mạng sau thao tác thủ công. Cách quản lý nào giúp giảm cấu hình trôi dạt lâu dài?
A. Quản lý hạ tầng bằng IaC có review thay đổi và áp dụng tự động.
B. Ghi nhật ký các thao tác trên console và lặp lại thủ công theo checklist.
C. Sao chép image máy production để tạo máy ở môi trường còn lại.
D. Lưu tài liệu cấu hình và sửa thủ công mỗi khi có khác biệt.
Đáp án đúng: A

Câu 14: Tác vụ tổng hợp báo cáo chỉ chạy hai giờ mỗi đêm; ban ngày gần như không dùng compute. Thiết kế nào tối ưu chi phí mà vẫn đáp ứng lịch chạy?
A. Giữ cụm compute chạy 24/7 và mua cam kết dài hạn để giảm giá.
B. Giữ máy chạy 24/7 và điều chỉnh kích thước mỗi tháng một lần.
C. Giữ máy lớn chạy 24/7 để sẵn tài nguyên khi job bắt đầu.
D. Lập lịch chạy job trên compute theo nhu cầu rồi dừng khi hoàn tất.
Đáp án đúng: D

Câu 15: Trong buổi đánh giá Well-Architected, nhóm thấy tăng replica cải thiện độ trễ nhưng chi phí tăng. Quyết định nào cân bằng tốt hiệu năng và chi phí?
A. Chọn số replica theo tải cực đại, chấp nhận chi phí duy trì tăng dài hạn.
B. Chọn số replica theo ngân sách, chấp nhận vi phạm SLO giờ cao điểm.
C. Chọn ngưỡng autoscaling từ thử tải và SLO, theo dõi chi phí thực tế.
D. Chọn số replica theo tải trung bình, giữ cấu hình cố định cả tháng.
Đáp án đúng: C

Câu 16: Hóa đơn dạng ảnh được truy cập nhiều trong tháng đầu, sau đó rất ít nhưng phải lưu bảy năm và có thể khôi phục trong một ngày. Kiến trúc lưu trữ nào hợp lý?
A. Giữ toàn bộ ảnh ở đĩa block tốc độ cao trong suốt bảy năm.
B. Giữ ảnh trên object storage, dùng lifecycle sang lớp khôi phục trong ngày.
C. Giữ toàn bộ ảnh ở cache của máy ứng dụng trong suốt bảy năm.
D. Giữ toàn bộ ảnh ở CSDL giao dịch lớp nóng trong suốt bảy năm.
Đáp án đúng: B
