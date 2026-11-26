Câu 1: Ứng dụng cần lưu ảnh sản phẩm và nhật ký dạng tệp, tải từng đối tượng bằng HTTP theo khóa và không sửa ngẫu nhiên từng khối. Nên dùng loại lưu trữ nào?
A. Block volume gắn vào máy ảo theo thiết bị.
B. File share truy cập qua thư mục NFS/SMB.
C. Object storage dùng API theo khóa.
D. Ổ đĩa tạm gắn trực tiếp với máy chủ.
Đáp án đúng: C

Câu 2: Cơ sở dữ liệu giao dịch trên một máy ảo cần hệ thống tệp, truy cập ngẫu nhiên theo khối với độ trễ thấp. Nên chọn loại lưu trữ nào?
A. Block volume với IOPS và độ trễ phù hợp.
B. Object bucket truy cập bằng API theo khóa.
C. File share cho nhiều máy khách cùng truy cập.
D. Lớp archive tối ưu giữ dữ liệu lâu dài.
Đáp án đúng: A

Câu 3: Ba máy Linux cần cùng đọc và ghi một thư mục dùng chung với quyền POSIX và giao thức NFS. Giải pháp nào phù hợp nhất?
A. Object bucket tải tệp qua URL và REST API.
B. Block volume không có giao diện chia sẻ tệp.
C. Snapshot volume tạo bản chụp theo lịch.
D. Dịch vụ file share hỗ trợ NFS và POSIX.
Đáp án đúng: D

Câu 4: Hồ sơ PDF được đọc nhiều trong 30 ngày đầu, sau đó rất hiếm và chấp nhận phục hồi chậm. Biện pháp nào phù hợp để giảm chi phí lưu?
A. Tạo thêm bản sao ở lớp truy cập thường xuyên.
B. Dùng lifecycle chuyển sang lớp ít truy cập.
C. Giữ mọi đối tượng mãi ở lớp truy cập nóng.
D. Tăng số phiên bản lưu giữ không giới hạn.
Đáp án đúng: B

Câu 5: Một hóa đơn trong bucket bị ghi đè nhầm; cần lấy lại nội dung trước khi ghi đè mà không phục hồi từ backup. Nên bật cơ chế nào trước đó?
A. Mã hóa phía server cho toàn bộ bucket.
B. Sao chép trạng thái hiện tại sang vùng khác.
C. Bộ nhớ đệm để giảm lượt đọc đối tượng.
D. Versioning để giữ lại các phiên bản cũ.
Đáp án đúng: D

Câu 6: Cần phục vụ ảnh qua CDN nhưng chỉ danh tính của CDN được đọc dữ liệu ở bucket gốc, không cho người dùng truy cập trực tiếp. Nên cấu hình gì?
A. Giới hạn bucket bằng CORS của tên miền CDN.
B. Giới hạn bucket bằng DNS trỏ tới tên CDN.
C. Giới hạn bucket policy cho danh tính CDN.
D. Giới hạn bucket bằng chuyển hướng HTTPS CDN.
Đáp án đúng: C

Câu 7: Ứng dụng tải tệp từ máy khách lên object storage; yêu cầu ngăn nghe lén dữ liệu trên đường truyền. Cơ chế nào giải quyết trực tiếp?
A. Bắt buộc HTTPS/TLS khi tải dữ liệu lên.
B. Bật mã hóa bằng KMS cho đối tượng đã lưu.
C. Bật kiểm tra checksum trên từng đối tượng.
D. Tạo snapshot bucket sau mỗi lần tải lên.
Đáp án đúng: A

Câu 8: Bucket lưu hồ sơ nhân sự, tổ chức cần tự quản lý quyền dùng khóa, lịch xoay vòng và nhật ký thao tác khóa. Chọn cách mã hóa nào?
A. Mã hóa phía server bằng khóa do khách quản lý.
B. Mã hóa phía server bằng khóa mặc định hệ thống.
C. Mã hóa đường truyền HTTPS khi gửi đối tượng.
D. Mã hóa ổ đĩa cục bộ của máy tải tệp.
Đáp án đúng: A

Câu 9: Ứng dụng di động cần quyền tải đúng một ảnh lên bucket trong 5 phút, không được giữ thông tin xác thực dài hạn. Giải pháp nào phù hợp?
A. Nhúng access key của tài khoản lưu trữ vào app.
B. Cấp URL ký trước giới hạn thao tác, thời hạn.
C. Mở quyền ghi ẩn danh tạm thời trên toàn bucket.
D. Gắn file share SMB trực tiếp cho mọi điện thoại.
Đáp án đúng: B

Câu 10: Cơ sở dữ liệu trên máy ảo dùng block volume; cần quay lại trạng thái trước khi có lệnh xóa nhầm trong DB. Biện pháp nào hữu ích nhất?
A. Tăng IOPS để giảm thời gian ghi của volume.
B. Bật nhân bản đồng bộ cho volume hiện tại.
C. Tăng số volume gắn vào cùng một máy ảo.
D. Chụp snapshot định kỳ và thử phục hồi dữ liệu.
Đáp án đúng: D

Câu 11: Bucket sao chép đối tượng bất đồng bộ sang vùng địa lý khác. Nếu vùng nguồn lỗi ngay sau khi ghi thành công, dữ liệu mới có thể thế nào?
A. Luôn sẵn sàng tại đích vì sao chép đồng bộ.
B. Không thể đọc tại đích nếu chưa gắn CDN.
C. Chưa có ở đích vì quá trình sao chép còn trễ.
D. Luôn có ở đích nếu hai vùng dùng cùng lớp lưu trữ.
Đáp án đúng: C

Câu 12: Kế hoạch khôi phục dữ liệu yêu cầu RPO bằng 15 phút. Chỉ số này biểu thị điều gì?
A. Thời gian tối đa để dịch vụ hoạt động lại.
B. Mức mất dữ liệu tối đa cho phép theo thời gian.
C. Thời hạn bắt buộc giữ mọi bản sao lưu tệp.
D. Thời gian cần để chuyển DNS qua vùng dự phòng.
Đáp án đúng: B

Câu 13: Nhóm vận hành cân nhắc lớp archive cho tài liệu rất ít đọc và chấp nhận khôi phục trong vài giờ. Cần đánh giá tiêu chí nào trước khi chuyển lớp?
A. Chỉ so sánh giá lưu mỗi GB giữa các lớp.
B. Chỉ ưu tiên lớp không tính phí lấy dữ liệu.
C. So thời gian khôi phục, phí lấy và kỳ hạn giữ.
D. Chỉ xem số yêu cầu ghi tối đa trên một giây.
Đáp án đúng: C

Câu 14: Để tài khoản ứng dụng bị chiếm quyền không thể xóa cả dữ liệu đang chạy lẫn mọi bản sao lưu, thiết kế sao lưu nào phù hợp?
A. Giữ backup chung bucket và chung quyền ứng dụng.
B. Lưu bản sao bất biến với quyền xóa tách biệt.
C. Tăng tốc độ sao lưu nhưng dùng chung quyền xóa.
D. Đổi tên bucket thường xuyên và giữ nguyên quyền.
Đáp án đúng: B

Câu 15: Hai máy ảo dùng chung file storage qua NFS nhưng truy cập dữ liệu chậm. Trước khi nâng gói lưu trữ, nên kiểm tra nhóm chỉ số nào?
A. Thông lượng, IOPS, độ trễ và ngưỡng dịch vụ.
B. Số bản ghi DNS đang trỏ tới các máy khách.
C. Lượt truy cập CDN phục vụ website công khai.
D. Băng thông Internet từ máy ảo tới người dùng.
Đáp án đúng: A

Câu 16: Ứng dụng sao chép object giữa hai region và trả tệp về người dùng qua Internet. Khi ước tính chi phí ngoài dung lượng lưu, cần tính gì?
A. Chỉ phí lớp lưu trữ nóng ở vùng dữ liệu nguồn.
B. Chỉ giá IOPS trên volume của máy chủ chạy app.
C. Chỉ số lượng máy DNS triển khai ở mỗi region.
D. Phí truyền liên vùng, egress và số lần request.
Đáp án đúng: D
