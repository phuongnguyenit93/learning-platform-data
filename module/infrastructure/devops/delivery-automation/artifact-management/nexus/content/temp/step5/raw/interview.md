Trong Sonatype Nexus Repository, hosted, proxy và group repository khác nhau về mục đích và luồng dữ liệu như thế nào, và bạn sẽ phối hợp chúng ra sao cho một nhóm vừa dùng thư viện bên ngoài vừa phát hành artifact nội bộ?
Bạn sẽ tổ chức các repository Maven dành cho snapshot và release như thế nào để quản lý vòng đời phiên bản và ngăn việc vô tình thay đổi một bản phát hành đã được sử dụng?
Khi đưa Nexus vào quy trình npm, bạn sẽ cấu hình nơi cài đặt dependency và nơi publish package nội bộ như thế nào để các package có scope được phân giải đúng nguồn?
Bạn sẽ thiết kế đường truy cập và cơ chế xác thực cho Docker registry trên Nexus ra sao để pipeline có thể push image còn các môi trường triển khai chỉ pull những image được phép?
Nếu một group repository chứa nhiều nguồn có package trùng tên và phiên bản, bạn sẽ xác định thứ tự ưu tiên và kiểm tra kết quả phân giải như thế nào để tránh lấy nhầm artifact?
Bạn sẽ tích hợp Nexus với pipeline CI/CD như thế nào để chỉ công bố artifact sau khi kiểm thử đạt, lưu được liên hệ với lần build và cho phép triển khai lại đúng phiên bản đã phát hành?
Khi một proxy repository vẫn trả kết quả cũ hoặc không tìm thấy dependency vừa xuất hiện ở upstream, bạn sẽ điều tra cơ chế cache, kết nối và cấu hình proxy theo trình tự nào?
Bạn sẽ thiết kế quyền truy cập, tài khoản dịch vụ và cách quản lý thông tin xác thực trên Nexus như thế nào để tách quyền đọc, quyền publish và quyền quản trị giữa các nhóm?
Nếu nhóm bảo mật nghi ngờ một package tải từ repository đã bị thay thế hoặc can thiệp, bạn sẽ thu thập và kiểm chứng những bằng chứng nào từ Nexus và quy trình build để đánh giá độ tin cậy của artifact?
Bạn sẽ xây dựng chính sách cleanup và lưu giữ cho Maven snapshot, npm package và Docker image như thế nào để kiểm soát dung lượng mà vẫn giữ đủ phiên bản cho rollback và kiểm toán?
Một pipeline có thể tải dependency nhưng bị lỗi 403 khi publish lên Nexus; bạn sẽ khoanh vùng nguyên nhân qua repository đích, quyền, thông tin xác thực và log như thế nào?
Bạn sẽ lập và diễn tập kế hoạch sao lưu, khôi phục Nexus Repository như thế nào để bảo toàn cả metadata, blob store và cấu hình, đồng thời xác nhận các pipeline có thể hoạt động lại sau sự cố?
