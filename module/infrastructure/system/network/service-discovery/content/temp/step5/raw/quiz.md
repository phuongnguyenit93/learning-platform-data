Câu 1. Service discovery giải quyết nhu cầu chính nào trong hệ phân tán?
A. Ghi lại payload hiện tại của mọi request
B. Đánh số transaction của từng service call
C. Tìm endpoint hiện tại từ tên dịch vụ logic
D. Lưu cấu hình tĩnh của từng tiến trình chạy
Đáp án đúng: C

Câu 2. Vì sao hard-code IP của mỗi instance không phù hợp hệ thống tự co giãn?
A. IP instance chỉ dùng được cho một request
B. IP instance thay đổi khi scale và thay thế
C. IP instance luôn trùng với port của service
D. IP instance chỉ hợp lệ khi không có DNS
Đáp án đúng: B

Câu 3. Trong client-side discovery, thành phần nào chọn endpoint cần gọi?
A. Gateway chọn instance từ danh sách discovery
B. DNS authoritative chọn instance theo RTT
C. Client chọn instance từ danh sách discovery
D. Database chọn instance từ bảng transaction
Đáp án đúng: C

Câu 4. Trong server-side discovery, thành phần nào thường chọn instance đích?
A. Ứng dụng client tự chọn backend từ registry
B. Proxy hoặc load balancer trước các backend
C. DNS resolver tự mở TCP tới mỗi backend
D. Service registry tự xử lý logic của backend
Đáp án đúng: B

Câu 5. Bản ghi DNS A hỗ trợ service discovery theo cách nào?
A. Ánh xạ service tới khóa bí mật của host
B. Ánh xạ service tới health check script
C. Ánh xạ tên host tới một địa chỉ IPv6
D. Ánh xạ tên host tới một địa chỉ IPv4
Đáp án đúng: D

Câu 6. DNS SRV có thể giúp client tìm thông tin gì cho dịch vụ?
A. Đích, cổng, độ ưu tiên và trọng số
B. Đích, subnet mask, gateway và DNS TTL
C. Đích, session ID, latency và HTTP code
D. Đích, checksum, thời hạn và khóa TLS
Đáp án đúng: A

Câu 7. DNS TTL tác động thế nào đến việc đổi endpoint của dịch vụ?
A. Cache có thể giữ IP cũ tới khi TTL hết
B. Cache chuyển IP cũ thành IP mới trong TCP
C. Cache ngừng phân giải khi endpoint được thêm
D. Cache tự xóa IP cũ khi instance ngừng chạy
Đáp án đúng: A

Câu 8. Nhược điểm nào có thể có khi dùng DNS nhiều bản ghi A để cân bằng tải?
A. Client bắt buộc chia tải theo lượng RAM
B. Client phải duyệt mọi endpoint trong cache
C. Client cache có thể làm phân phối tải lệch
D. Client luôn hỏi DNS trước mọi TCP packet
Đáp án đúng: C

Câu 9. DNS trả NXDOMAIN sau khi service mới bị xóa rồi tạo lại; vì sao client còn thấy lỗi?
A. Proxy retry tự chuyển DNS sang IP cố định
B. TCP retransmission luôn giữ kết quả NXDOMAIN
C. Negative caching có thể giữ kết quả NXDOMAIN
D. UDP checksum tự lưu tên không tìm được
Đáp án đúng: C

Câu 10. Service registry thường lưu loại thông tin nào cho instance?
A. Service ID, khóa chính của bảng nghiệp vụ
B. Service ID, câu SQL và kết quả transaction
C. Service ID, code nhị phân của mọi container
D. Service ID, endpoint và metadata instance
Đáp án đúng: D

Câu 11. Health check của service discovery giúp giảm rủi ro nào?
A. Trả endpoint chưa sẵn sàng nhận request
B. Trả endpoint có tên service dài hơn dự kiến
C. Trả endpoint khác version ứng dụng hiện tại
D. Trả endpoint đang dùng thuật toán nén khác
Đáp án đúng: A

Câu 12. Điểm khác nhau chủ yếu giữa readiness và liveness trong Kubernetes là gì?
A. Readiness tạo Service, liveness tạo NetworkPolicy
B. Readiness điều khiển restart, liveness hỗ trợ nhận traffic
C. Readiness cấp phát IP, liveness ghi các bản ghi DNS
D. Readiness điều khiển nhận traffic, liveness hỗ trợ restart
Đáp án đúng: D

Câu 13. Instance tự đăng ký với registry khi khởi động mang lại lợi ích nào?
A. Registry cập nhật database khi instance truy vấn
B. Đăng ký endpoint mới khi instance khởi động
C. Registry phân tích SQL khi instance xuất hiện
D. Registry tự cấp quyền mạng khi instance đăng ký
Đáp án đúng: B

Câu 14. Khi một instance được dừng có kiểm soát, thao tác discovery nào phù hợp?
A. Đổi TTL DNS của mọi dịch vụ về bằng 0
B. Xóa toàn bộ registry trước khi dừng instance
C. Giữ endpoint hoạt động sau khi đóng socket
D. Hủy đăng ký hoặc đánh dấu không sẵn sàng
Đáp án đúng: D

Câu 15. Lease hoặc heartbeat giúp registry phát hiện vấn đề nào?
A. Instance có thể tăng số thread ứng dụng
B. Instance mất liên lạc mà không kịp deregister
C. Instance đã trả HTTP response có mã 304
D. Instance cần giảm dung lượng log trên đĩa
Đáp án đúng: B

Câu 16. Consul catalog thường cung cấp chức năng nào?
A. Lưu và truy vấn các service đã đăng ký
B. Lưu và truy vấn toàn bộ HTTP access log
C. Lưu và truy vấn image của container build
D. Lưu và truy vấn schema của database chính
Đáp án đúng: A

Câu 17. Tra cứu `payment.service.consul` trong mô hình Consul DNS nhằm mục đích gì?
A. Phân giải tên service thành địa chỉ endpoint
B. Phân giải tên service thành bản ghi trong Git
C. Phân giải tên service thành phiên bản image
D. Phân giải tên service thành quyền của ACL token
Đáp án đúng: A

Câu 18. Trong Consul, service health check thất bại kéo dài thường ảnh hưởng gì?
A. Instance được thêm port TCP phụ để dự phòng
B. Instance được chuyển thành bản ghi DNS MX
C. Instance bị loại khỏi tập endpoint healthy
D. Instance bị nhân đôi thành nhiều endpoint mới
Đáp án đúng: C

Câu 19. Sự khác nhau giữa Consul KV và Consul service catalog là gì?
A. KV định tuyến request, catalog cấp phát CPU cho pod
B. KV lưu cặp khóa–giá trị, catalog quản lý service
C. KV phát TLS certificate, catalog thực thi SQL DDL
D. KV quản lý endpoint, catalog lưu mã nguồn build
Đáp án đúng: B

Câu 20. Trong Netflix Eureka, ứng dụng service thường sử dụng cơ chế nào?
A. Client đăng ký instance với database replica
B. Client đăng ký instance với node load balancer
C. Client đăng ký instance với DNS root server
D. Client đăng ký instance với Eureka server
Đáp án đúng: D

Câu 21. Heartbeat của Eureka client chủ yếu có mục đích gì?
A. Đổi HTTP port của instance theo từng phút
B. Gia hạn lease cho instance đã đăng ký
C. Gửi lại payload đã thất bại của request
D. Tính lại DNS TTL cho instance đã đăng ký
Đáp án đúng: B

Câu 22. Cơ chế self-preservation của Eureka chủ yếu nhằm tránh điều gì?
A. Evict hàng loạt instance khi mạng có vấn đề
B. Chạy health check hàng loạt sau mỗi request
C. Khởi động hàng loạt instance khi CPU tăng
D. Thay đổi hàng loạt endpoint khi image mới
Đáp án đúng: A

Câu 23. Điểm cần lưu ý khi chọn Eureka trong sự cố network partition là gì?
A. Registry tự chuyển client sang DNS authoritative
B. Registry có thể còn endpoint tạm thời cũ
C. Registry luôn trả thông tin tuyến tính mới nhất
D. Registry bắt buộc dừng mọi phản hồi discovery
Đáp án đúng: B

Câu 24. Eureka client thường giảm số lượt gọi server bằng cơ chế nào?
A. Cache DNS root hints rồi bỏ qua registry
B. Cache session SQL và tạo index định kỳ
C. Cache packet TCP và phát lại định kỳ
D. Cache registry cục bộ và làm mới định kỳ
Đáp án đúng: D

Câu 25. Kubernetes Service loại ClusterIP cung cấp gì cho ứng dụng nội bộ?
A. Một địa chỉ Pod cố định cho từng lần rolling update
B. Một địa chỉ Service ổn định để gọi trong cluster
C. Một địa chỉ IP public dành riêng cho từng Pod
D. Một địa chỉ node vật lý cố định cho mỗi container
Đáp án đúng: B

Câu 26. Trong Kubernetes, EndpointSlice biểu diễn thông tin nào?
A. Các truy vấn DNS đã cache trên mỗi node
B. Các giao dịch mạng giữa Pod và database
C. Các phiên đăng nhập vào Kubernetes API
D. Các endpoint backend gắn với một Service
Đáp án đúng: D

Câu 27. Service có selector thông thường chọn backend thế nào?
A. Qua phiên bản image ghi trong Deployment YAML
B. Qua UID của namespace chứa Service object
C. Qua thứ tự tạo Pod trong kubelet trên node
D. Qua nhãn của Pod khớp với selector Service
Đáp án đúng: D

Câu 28. Trong Kubernetes, tên DNS `api.team.svc.cluster.local` chỉ ra điều gì?
A. Service api thuộc namespace team trong cluster
B. Pod api thuộc namespace svc trong cluster team
C. Node api thuộc domain team do cloud quản lý
D. Ingress api thuộc namespace cluster nội bộ
Đáp án đúng: A

Câu 29. Khi readiness của Pod chuyển sang false, kết quả thông thường đối với traffic Service là gì?
A. Pod bắt buộc bị xóa bởi kubelet ngay lập tức
B. Pod tự thay DNS record thành tên Pod mới
C. Pod không còn là endpoint sẵn sàng để nhận traffic
D. Pod tự chuyển sang NodePort để nhận traffic khác
Đáp án đúng: C

Câu 30. Headless Service trong Kubernetes có đặc điểm DNS nào?
A. DNS có thể trả địa chỉ Pod thay vì virtual IP
B. Luôn trả IP node thay cho địa chỉ của các Pod
C. Luôn trả hostname public của Ingress controller
D. Luôn trả một virtual IP cân bằng tải duy nhất
Đáp án đúng: A

Câu 31. Client-side load balancing cần dữ liệu nào từ discovery?
A. Toàn bộ cấu hình SQL để chọn khi gọi
B. Toàn bộ mã nguồn backend để chọn khi gọi
C. Danh sách endpoint khả dụng để chọn khi gọi
D. Toàn bộ packet capture để chọn khi gọi
Đáp án đúng: C

Câu 32. Reverse proxy làm server-side load balancing sẽ đảm nhiệm công việc nào?
A. Chọn DNS TTL và đăng ký Pod với Eureka
B. Chọn database schema và tối ưu SQL query
C. Chọn port client và cấp IP cho container
D. Chọn backend và chuyển tiếp request client
Đáp án đúng: D

Câu 33. Cân bằng tải theo round-robin có hạn chế nào khi các request không đồng đều?
A. Không thể đổi endpoint sau khi backend mất kết nối
B. Không phản ánh chi phí xử lý khác nhau của request
C. Không hỗ trợ request chạy trên một giao thức TCP
D. Không thể dùng với nhiều endpoint cùng một service
Đáp án đúng: B

Câu 34. Sticky session có thể gây rủi ro gì khi instance bị thay thế?
A. Registry bắt buộc đăng ký lại mọi service khác
B. Trạng thái phiên trên instance cũ có thể mất
C. DNS không còn phân giải được các tên máy chủ
D. TCP không cho phép giữ nhiều socket đồng thời
Đáp án đúng: B

Câu 35. Khi endpoint ngừng phản hồi, retry thiếu timeout có thể gây vấn đề gì?
A. Request tự hạ mức mã hóa TLS khi bị timeout
B. Request luôn thất bại tức thì không tốn tài nguyên
C. Request treo lâu và tích tụ tài nguyên phía gọi
D. Request tự chuyển sang trạng thái nhất quán mạnh
Đáp án đúng: C

Câu 36. Circuit breaker giúp client ứng phó backend lỗi lặp lại thế nào?
A. Tạo replica mới bằng cách gọi Kubernetes API
B. Buộc tăng số retry lên nhiều lần khi backend lỗi
C. Tạm ngừng gọi backend lỗi theo trạng thái breaker
D. Chuyển backend lỗi sang một hostname DNS khác
Đáp án đúng: C

Câu 37. Exponential backoff kết hợp jitter cải thiện retry ở điểm nào?
A. Giãn và phân tán thời điểm retry của các client
B. Đảm bảo mỗi retry được phục vụ trong cùng một RTT
C. Giữ mọi retry gửi đồng thời để tăng throughput
D. Thay đổi endpoint bằng cách mã hóa hostname
Đáp án đúng: A

Câu 38. Chọn TTL cache discovery quá dài có đánh đổi nào?
A. Giảm lượt lookup nhưng giữ endpoint cũ lâu
B. Tăng lượt lookup nhưng luôn giữ endpoint mới
C. Tăng số bản ghi DNS nhưng giảm độ trễ mạng
D. Giảm số instance nhưng tăng tính tuyến tính
Đáp án đúng: A

Câu 39. Watcher thông báo registry thay đổi mang lợi ích nào so với chỉ polling chậm?
A. Client ngừng cần health check ở tất cả các backend
B. Client luôn bỏ được cơ chế cân bằng tải phía ứng dụng
C. Client nhận thay đổi endpoint nhanh hơn khi có sự kiện
D. Client tự thực hiện TLS handshake thay cho backend
Đáp án đúng: C

Câu 40. Khi DNS endpoint mới đã cập nhật, vì sao một số client vẫn gọi IP cũ?
A. Router cố định luôn giữ mọi TCP connection
B. Registry buộc client gọi endpoint đầu tiên mãi
C. Firewall luôn thay bản ghi DNS bằng bản ghi cũ
D. Resolver hoặc ứng dụng còn cache bản ghi cũ
Đáp án đúng: D

Câu 41. Đối với API service registry, biện pháp bảo mật nền tảng nào phù hợp?
A. Dùng chung token quản trị giữa mọi ứng dụng
B. Tắt ghi audit log cho các thay đổi endpoint
C. Cho phép ghi registry từ mọi nguồn chưa xác thực
D. Áp dụng xác thực và phân quyền theo service
Đáp án đúng: D

Câu 42. Khi dùng Consul ACL, thực hành nào phù hợp để cấp quyền đọc discovery?
A. Token ghi service catalog cho mọi ứng dụng
B. Token chỉ có quyền đọc các service cần thiết
C. Token trống rồi tắt xác thực ở môi trường thật
D. Token quản trị toàn cluster cho mọi service
Đáp án đúng: B

Câu 43. Trong thiết kế đa vùng, điều nào giúp duy trì discovery khi một zone lỗi?
A. Buộc mọi lookup đi qua một Pod đơn vùng duy nhất
B. Chỉ cấu hình DNS TTL mà không có instance dự phòng
C. Có registry dự phòng trải trên nhiều zone
D. Đặt toàn bộ registry trên một VM trong cùng zone
Đáp án đúng: C

Câu 44. Khi client không kết nối được dịch vụ, chuỗi kiểm tra nào hợp lý đầu tiên?
A. Xem DNS, endpoint healthy và port đích
B. Bỏ health check để mọi instance được nhận request
C. Tắt TLS để bỏ qua lỗi phân giải tên service
D. Xóa mọi registry record rồi khởi động lại toàn bộ
Đáp án đúng: A
