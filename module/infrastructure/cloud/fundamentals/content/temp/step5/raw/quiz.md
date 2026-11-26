Câu 1: Nhóm phát triển cần tự cài hệ điều hành, driver và phần mềm trên các máy ảo chạy trong cloud. Mô hình dịch vụ nào phù hợp nhất?
A. PaaS: triển khai mã lên môi trường được quản lý.
B. IaaS: cấp máy ảo để tự quản trị hệ điều hành.
C. SaaS: dùng ứng dụng hoàn chỉnh của nhà cung cấp.
D. FaaS: chạy hàm khi nhận một sự kiện đầu vào.
Đáp án đúng: B

Câu 2: Nhóm ứng dụng muốn đẩy mã nguồn lên cloud, sử dụng runtime và cơ chế triển khai có sẵn, không tự vá hệ điều hành máy chủ. Mô hình nào đáp ứng trực tiếp?
A. IaaS cấp máy ảo cho đội tự quản trị hệ điều hành.
B. SaaS cung cấp phần mềm hoàn chỉnh cho người dùng.
C. Máy chủ tại chỗ do đội nội bộ trực tiếp vận hành.
D. PaaS cung cấp runtime để triển khai ứng dụng.
Đáp án đúng: D

Câu 3: Doanh nghiệp cần email, lịch họp và soạn tài liệu trực tuyến ngay, không có kế hoạch tự phát triển phần mềm. Mô hình nào hợp lý nhất?
A. SaaS cung cấp ứng dụng cộng tác đã vận hành.
B. PaaS cung cấp runtime để tự xây ứng dụng email.
C. IaaS cho thuê máy ảo để tự cài máy chủ email.
D. FaaS chạy từng hàm để tự xây hộp thư.
Đáp án đúng: A

Câu 4: Một nhóm chạy máy ảo theo mô hình IaaS và nhận thông báo cần vá lỗ hổng trong guest OS. Bên nào chịu trách nhiệm thực hiện bản vá đó?
A. Khách hàng vận hành và cập nhật guest OS.
B. Nhà cung cấp cloud quản lý mọi guest OS.
C. Đội quản lý hypervisor tự vá guest OS.
D. Bên cung cấp DNS tự cập nhật guest OS.
Đáp án đúng: A

Câu 5: Ứng dụng cần tiếp tục phục vụ nếu một availability zone (AZ) gặp sự cố, nhưng dữ liệu phải ở cùng một region. Kiến trúc nào phù hợp nhất?
A. Đặt hai máy trong một AZ, thêm cân bằng tải.
B. Đặt hai máy trong một subnet, thêm snapshot.
C. Chạy máy ở nhiều AZ với một load balancer.
D. Đặt một máy trong một AZ, tăng CPU và RAM.
Đáp án đúng: C

Câu 6: Khi chọn region để triển khai ứng dụng phục vụ khách tại Việt Nam, tiêu chí nào liên quan nhất đến hiệu năng và yêu cầu pháp lý?
A. Giá máy ảo, số IP tĩnh và tên vùng khả dụng.
B. Độ trễ, vị trí dữ liệu và dịch vụ khả dụng.
C. Số subnet, kích thước CIDR và tên máy ảo.
D. TTL của DNS, kiểu endpoint và số nhóm IAM.
Đáp án đúng: B

Câu 7: Doanh nghiệp giữ cơ sở dữ liệu tại trung tâm dữ liệu riêng nhưng triển khai dịch vụ web trên public cloud, kết nối an toàn giữa hai nơi. Đây là mô hình nào?
A. Public cloud vì tất cả hệ thống ở một nhà cung cấp.
B. Private cloud vì mọi tải xử lý đều ở trung tâm dữ liệu.
C. Multi-cloud vì ứng dụng phải trải trên nhiều nhà cung cấp.
D. Hybrid cloud kết hợp hạ tầng tại chỗ và public cloud.
Đáp án đúng: D

Câu 8: Website bán hàng thường chỉ cần hai máy nhưng đôi lúc tải tăng gấp năm lần trong vài phút. Cách nào giúp điều chỉnh số máy theo nhu cầu?
A. Giữ số máy cố định ở mức tải cao nhất.
B. Chỉ nâng dung lượng ổ đĩa của máy hiện tại.
C. Auto Scaling điều chỉnh số máy theo tải.
D. Tăng CPU của một máy và không thay đổi số máy.
Đáp án đúng: C

Câu 9: Ứng dụng HTTP chạy trên ba máy ảo; cần phân phối yêu cầu mới và bỏ qua máy không vượt qua health check. Nên sử dụng thành phần nào?
A. NAT gateway cung cấp kết nối ra Internet.
B. DNS resolver phân giải tên nội bộ của VPC.
C. Object storage lưu tệp dùng chung cho máy.
D. Load balancer kiểm tra sức khỏe các backend.
Đáp án đúng: D

Câu 10: Một website lưu hàng triệu ảnh và video, truy cập qua URL, không cần gắn ổ đĩa vào máy ảo. Dịch vụ lưu trữ nào thích hợp nhất?
A. Object storage lưu dữ liệu dưới dạng đối tượng.
B. Block volume gắn vào một máy ảo để đọc ghi.
C. File share cung cấp thư mục chia sẻ qua NFS.
D. Local disk nằm trên máy chủ chạy ứng dụng.
Đáp án đúng: A

Câu 11: Nhóm phát triển muốn dùng cơ sở dữ liệu SQL nhưng giao việc vá engine và sao lưu tự động cho cloud. Nên chọn dịch vụ nào?
A. Máy ảo có DB tự cài và tự quản trị bản vá.
B. Block volume để cài DB do đội tự vận hành.
C. Managed SQL database tự vá và sao lưu.
D. Object storage để lưu các tệp truy vấn SQL.
Đáp án đúng: C

Câu 12: Sau thảm họa, doanh nghiệp chấp nhận mất tối đa dữ liệu phát sinh trong 10 phút. Chỉ số nào cần được giới hạn ở mức 10 phút?
A. RTO: thời gian đưa dịch vụ hoạt động trở lại.
B. RPO: mức mất dữ liệu tính theo thời gian.
C. SLA: mức độ sẵn sàng cam kết trong một kỳ.
D. MTTR: thời gian trung bình khắc phục sự cố.
Đáp án đúng: B

Câu 13: Một môi trường thử nghiệm chỉ cần hoạt động vài giờ mỗi ngày. Cách nào phù hợp nhất để tránh chi phí tính toán khi không sử dụng?
A. Dừng tài nguyên tính toán khi không sử dụng.
B. Mua trước công suất cố định cho cả năm.
C. Giữ máy ảo hoạt động liên tục cả ngày đêm.
D. Mở rộng thêm máy để tăng mức dự phòng.
Đáp án đúng: A

Câu 14: Ứng dụng xử lý ảnh mỗi khi tệp được tải lên, số lần tải lên thay đổi lớn và nhóm không muốn quản trị máy chủ. Lựa chọn tính toán nào phù hợp nhất?
A. Máy ảo luôn bật để liên tục kiểm tra bucket.
B. Máy chủ riêng chạy tác vụ theo lịch cố định.
C. Cluster VM tự vận hành các container dài hạn.
D. Hàm serverless xử lý sự kiện tải tệp.
Đáp án đúng: D

Câu 15: Nhân viên hỗ trợ cần xem log để chẩn đoán sự cố nhưng không được sửa hay xóa tài nguyên cloud. Nên cấp quyền như thế nào?
A. Quyền quản trị tài khoản trong toàn bộ môi trường.
B. Chỉ quyền đọc log theo vai trò được phân công.
C. Quyền chỉnh sửa cấu hình mọi dịch vụ đang chạy.
D. Khóa truy cập của quản trị viên cho nhân viên.
Đáp án đúng: B

Câu 16: Máy ảo ở subnet riêng cần tải bản vá từ Internet nhưng không được nhận kết nối trực tiếp từ bên ngoài. Nên định tuyến lưu lượng ra qua đâu?
A. Internet gateway gắn IP công khai cho mọi máy.
B. Load balancer nhận và chuyển lưu lượng inbound.
C. NAT gateway phục vụ kết nối ra từ subnet riêng.
D. Private DNS zone phân giải tên máy nội bộ.
Đáp án đúng: C
