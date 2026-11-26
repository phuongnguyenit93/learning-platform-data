Câu 1: Subnet 10.24.32.0/20 trong một VPC/VNet bao gồm địa chỉ nào sau đây?
A. 10.24.31.254
B. 10.24.48.1
C. 10.24.47.254
D. 10.25.32.1
Đáp án đúng: C

Câu 2: Một ứng dụng có tầng web nhận truy cập Internet, tầng API và cơ sở dữ liệu chỉ phục vụ nội bộ. Sơ đồ subnet và quy tắc truy cập nào phù hợp nhất?
A. Cả ba ở subnet công khai; DNS quyết định máy nào được truy cập.
B. Web ở subnet công khai; API và DB ở subnet riêng, chỉ mở luồng cần thiết.
C. DB ở subnet công khai; web và API riêng, chỉ mở luồng cần thiết.
D. Cả ba ở một subnet; mở toàn bộ lưu lượng nội bộ giữa các tầng.
Đáp án đúng: B

Câu 3: Bảng định tuyến có 10.8.0.0/16 qua VPN và 0.0.0.0/0 qua Internet gateway. Gói đến 10.8.5.12 sẽ ưu tiên tuyến nào?
A. Tuyến 0.0.0.0/0 vì bao phủ mọi địa chỉ.
B. Tuyến được khai báo trước trong bảng.
C. Tuyến có next hop gần máy nguồn hơn.
D. Tuyến 10.8.0.0/16 vì khớp cụ thể hơn.
Đáp án đúng: D

Câu 4: Máy chủ không có IP công khai trong subnet riêng cần tải bản vá từ Internet nhưng không nhận kết nối đến tự phát. Tuyến mặc định của subnet nên đi qua thành phần nào?
A. Internet gateway kết nối trực tiếp với subnet.
B. NAT gateway hỗ trợ lưu lượng khởi tạo từ trong.
C. Cân bằng tải công khai đứng trước máy chủ.
D. DNS resolver cung cấp địa chỉ bên ngoài.
Đáp án đúng: B

Câu 5: Một tường lửa cấp máy ảo hoạt động theo cơ chế stateful đã cho phép kết nối TCP/443 từ máy khách. Ở chính tường lửa đó, gói phản hồi được xử lý ra sao?
A. Được cho phép theo trạng thái kết nối đã ghi.
B. Phải mở thủ công dải cổng tạm ở chiều ra.
C. Phải mở thêm quy tắc ra cho từng IP khách.
D. Chỉ được cho phép nếu ACL subnet cũng stateful.
Đáp án đúng: A

Câu 6: VPC trên cloud và mạng văn phòng đều dùng 10.40.0.0/16; đường hầm VPN đã lên nhưng định tuyến giữa hai phía bị nhập nhằng. Nên sửa gì trước?
A. Tăng MTU của đường hầm và giữ nguyên hai dải.
B. Mở toàn bộ cổng giữa hai phía trên tường lửa.
C. Thay DNS công cộng cho các tên máy nội bộ.
D. Điều chỉnh CIDR để hai phía không bị chồng lấn.
Đáp án đúng: D

Câu 7: Dịch vụ api.internal chỉ có IP riêng và tên này chỉ cần phân giải từ các mạng ảo đã liên kết. Cấu hình DNS nào thích hợp nhất?
A. Dùng private DNS zone liên kết với mạng ảo.
B. Tạo public DNS zone trỏ đến các IP riêng.
C. Ghi địa chỉ dịch vụ vào hosts trên từng máy.
D. Cấp IP công khai cho từng máy chạy dịch vụ.
Đáp án đúng: A

Câu 8: Bộ cân bằng tải có hai backend và health check phát hiện một backend không khỏe. Khi backend còn lại khỏe, hành vi phù hợp là gì?
A. Tiếp tục chia đều yêu cầu cho cả hai backend.
B. Chuyển yêu cầu mới chỉ đến backend bị lỗi.
C. Chỉ chuyển yêu cầu mới đến backend còn khỏe.
D. Dừng mọi yêu cầu cho đến khi cả hai khỏe.
Đáp án đúng: C

Câu 9: Ứng dụng truy cập DB qua IP riêng bị timeout. Muốn biết các gói đến cổng TCP/5432 tại giao diện DB có bị chặn ở lớp mạng hay không, nên xem dữ liệu nào?
A. Nhật ký health check của load balancer tầng web.
B. Nhật ký truy vấn của DNS resolver nội bộ.
C. Chỉ số lưu lượng của NAT gateway phía ứng dụng.
D. Flow log ghi lưu lượng tới giao diện mạng DB.
Đáp án đúng: D

Câu 10: Cùng một tên miền HTTPS cần chuyển /api/* đến nhóm API và /static/* đến nhóm web tĩnh. Cơ chế nào đáp ứng trực tiếp yêu cầu?
A. Cân bằng tải TCP theo cổng đích.
B. Cân bằng tải HTTP theo đường dẫn.
C. Phân giải DNS xoay vòng giữa máy chủ.
D. Định tuyến IP theo địa chỉ của client.
Đáp án đúng: B

Câu 11: VPC A peering với VPC B, và B peering với C. Không có router trung gian hoặc chức năng chuyển tiếp bổ sung. Mạng A có mặc định truy cập C qua B không?
A. Có, peering tự chuyển tiếp qua mạng B.
B. Có, miễn là ba dải CIDR không chồng lấn.
C. Không, peering không tự bắc cầu tuyến qua B.
D. Không, vì peering chỉ cho phép truy vấn DNS.
Đáp án đúng: C

Câu 12: Kết nối VPN hybrid cần để cloud tự học các dải mạng mới do router tại chỗ quảng bá. Cơ chế định tuyến nào phù hợp nếu hai đầu hỗ trợ?
A. Trao đổi thông tin tuyến động bằng BGP.
B. Đồng bộ bảng định tuyến qua bản ghi DNS.
C. Tạo NAT gateway ở mỗi subnet trong cloud.
D. Đặt một tuyến mặc định cố định ra Internet.
Đáp án đúng: A

Câu 13: Chỉ các máy tầng ứng dụng cần truy cập PostgreSQL cổng TCP/5432 trong subnet DB. Quy tắc inbound nào tuân nguyên tắc quyền tối thiểu?
A. Cho nhóm máy ứng dụng vào DB bằng TCP/5432.
B. Cho phép nhóm máy web vào DB trên TCP/5432.
C. Cho phép subnet quản trị vào DB trên TCP/5432.
D. Cho phép mọi máy nội bộ vào DB trên TCP/5432.
Đáp án đúng: A

Câu 14: Văn phòng đã kết nối VPN với cloud. Máy trạm cần phân giải db.cloud.internal trong private DNS zone của cloud mà không công bố ra Internet. Giải pháp phù hợp là gì?
A. Tạo bản ghi công khai trỏ tới IP của dịch vụ.
B. Phân phối tệp hosts cho toàn bộ máy trạm.
C. Chuyển tiếp có điều kiện tới inbound DNS resolver.
D. Chuyển DNS qua NAT gateway đang dùng cho egress.
Đáp án đúng: C

Câu 15: Máy trong subnet riêng đọc nhiều dữ liệu từ dịch vụ lưu trữ đối tượng cùng cloud qua NAT. Muốn giảm lưu lượng đi qua NAT mà vẫn dùng đường kết nối riêng, nên chọn gì nếu dịch vụ hỗ trợ?
A. Tăng thêm NAT gateway cho từng subnet.
B. Dùng private/gateway endpoint tới dịch vụ.
C. Gắn IP công khai vào máy và bỏ subnet riêng.
D. Chuyển đường truy cập về văn phòng qua VPN.
Đáp án đúng: B

Câu 16: Sau khi thiết lập VPN hybrid, kết nối TCP bắt tay thành công và gói nhỏ đi qua, nhưng truyền tải dữ liệu lớn thường đứng. Cần kiểm tra yếu tố nào trước?
A. Tăng timeout cho phiên TCP ở ứng dụng.
B. Tăng băng thông dự phòng của đường VPN.
C. Thêm một tuyến tĩnh tới mạng đích qua VPN.
D. Kiểm tra MTU/MSS và Path MTU Discovery.
Đáp án đúng: D
