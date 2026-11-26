Câu 1. Mục đích chính của service mesh trong hệ thống nhiều microservice là gì?
A. Chuyển mọi quy tắc nghiệp vụ sang cùng một cụm proxy.
B. Quản trị giao tiếp qua proxy, giảm logic tại từng app.
C. Thay cơ sở dữ liệu riêng của từng dịch vụ bằng một kho.
D. Buộc tất cả dịch vụ dùng chung một giao thức lưu trữ.
Đáp án đúng: B

Câu 2. Control plane trong mô hình service mesh thường đảm nhiệm vai trò nào?
A. Chuyển tiếp tất cả gói dữ liệu của mọi request dịch vụ.
B. Lưu nội dung request của từng dịch vụ để chạy nghiệp vụ.
C. Phản hồi HTTP thay cho mọi instance ứng dụng backend.
D. Phân phối cấu hình, endpoint và chính sách đến proxy.
Đáp án đúng: D

Câu 3. Data plane trong service mesh thường xử lý công việc nào?
A. Proxy xử lý kết nối và chuyển lưu lượng giữa các dịch vụ.
B. Xây dựng chính sách toàn cụm rồi lưu vào Git.
C. Cấp phát Pod và lên lịch workload trên các node.
D. Thay mỗi chương trình ứng dụng bằng một controller.
Đáp án đúng: A

Câu 4. Trong kiến trúc sidecar, proxy thường được triển khai ở vị trí nào?
A. Chỉ tại node điều khiển Kubernetes API server.
B. Proxy nằm cùng Pod Kubernetes với container ứng dụng.
C. Chỉ trên máy chủ database ngoài Kubernetes.
D. Trong từng trình duyệt của người dùng cuối.
Đáp án đúng: B

Câu 5. Điểm đánh đổi của mô hình sidecar-per-Pod thường là gì?
A. Giảm toàn bộ số kết nối cần thiết giữa các dịch vụ.
B. Loại bỏ hoàn toàn độ trễ của lưu lượng nội bộ.
C. Buộc ứng dụng tự xử lý mọi bước bắt tay TLS.
D. Tăng chi phí CPU, RAM và vận hành theo số lượng Pod.
Đáp án đúng: D

Câu 6. Một kiến trúc mesh sidecar-less với proxy dùng chung cấp node có lợi ích gì?
A. Buộc mọi Pod phải tích hợp thư viện proxy theo ngôn ngữ.
B. Loại bỏ hoàn toàn nhu cầu kiểm soát danh tính workload.
C. Thay kube-proxy bằng hệ thống lưu trữ dữ liệu phân tán.
D. Giảm số proxy riêng phải chạy trong mỗi Pod ứng dụng ở cluster.
Đáp án đúng: D

Câu 7. Phân biệt API gateway với service mesh theo phạm vi sử dụng điển hình nào?
A. Gateway chỉ xử lý TCP; mesh chỉ xử lý truy vấn SQL.
B. Gateway tập trung tại biên; mesh tập trung giữa dịch vụ.
C. Gateway thay database; mesh thay mọi controller Kubernetes.
D. Gateway chạy trong client; mesh chỉ chạy trong browser.
Đáp án đúng: B

Câu 8. Service discovery giúp proxy của mesh thích ứng khi Pod thay đổi ra sao?
A. Cập nhật endpoint khi Pod thay đổi để điều hướng request đúng đích.
B. Khóa vĩnh viễn địa chỉ IP đầu tiên của mỗi service.
C. Chỉ truy cập Pod khi endpoint được nhập tay từng ngày.
D. Luôn gửi request qua một DNS server công cộng cố định.
Đáp án đúng: A

Câu 9. Khi tích hợp Kubernetes, control plane mesh thường lấy thông tin endpoint từ đâu?
A. Lấy endpoint qua Service và EndpointSlice trong Kubernetes.
B. Các tệp hosts được ghi trong laptop của người dùng.
C. Các DNS record công cộng duy nhất của domain công ty.
D. Các thư mục log access của trình duyệt người dùng.
Đáp án đúng: A

Câu 10. Định tuyến HTTP theo path hoặc header là ví dụ điển hình của chức năng nào?
A. Phân phối theo địa chỉ MAC ở tầng liên kết L2.
B. Điều phối lưu lượng L7 nhờ header và path HTTP.
C. Điều phối theo subnet mà không đọc yêu cầu HTTP.
D. Định tuyến dựa trên sector của ổ đĩa lưu trữ.
Đáp án đúng: B

Câu 11. Nếu chỉ biết địa chỉ IP và cổng TCP, proxy đang dùng tín hiệu định tuyến nào?
A. Cookie phiên của HTTP response ở tầng L7.
B. Thông tin mạng và transport ở mức L3/L4 của kết nối TCP.
C. Trường `user_id` trong JSON request body.
D. Nhật ký truy vấn SQL của ứng dụng phía sau.
Đáp án đúng: B

Câu 12. Khi phát hành v2 cho 10% request, tính năng mesh nào phù hợp nhất?
A. Health check ép mọi request sang bản v2 ngay.
B. Mirror mọi response sang cơ sở dữ liệu dự phòng.
C. Giới hạn toàn bộ ingress chỉ còn 10 kết nối.
D. Chia request theo trọng số giữa các phiên bản.
Đáp án đúng: D

Câu 13. Khi dùng request mirroring để thử nghiệm bản mới, kết quả bản sao thường ra sao?
A. Response hai backend tự gộp thành một payload mới.
B. Gateway luôn chờ bản shadow commit rồi mới trả lời.
C. Shadow nhận bản sao; client dùng response backend chính.
D. Trình duyệt nhận đồng thời hai HTTP response hợp lệ.
Đáp án đúng: C

Câu 14. Chính sách timeout trong service mesh giúp tránh tình huống nào?
A. Request được gửi lại nhiều lần do client retry.
B. Request bị từ chối vì không có quyền workload.
C. Đặt hạn chờ khi upstream chậm để request không treo quá lâu.
D. Request bị phân bổ sang nhiều zone địa lý khác.
Đáp án đúng: C

Câu 15. Với HTTP POST tạo đơn hàng, vì sao cần cân nhắc trước khi bật retry tự động?
A. Retry luôn đổi POST thành GET để tránh gửi dữ liệu.
B. Retry có thể tạo đơn lặp nếu thao tác không idempotent.
C. Retry chỉ dùng được khi service không có timeout.
D. Retry bắt buộc cấp lại chứng chỉ mTLS cho từng lần.
Đáp án đúng: B

Câu 16. Exponential backoff có jitter trong retry policy chủ yếu giúp gì?
A. Giãn retry tới upstream để tránh các đợt gọi đồng loạt.
B. Ép mọi retry chạy cùng lúc để giảm thời gian xử lý.
C. Ngăn mọi response lỗi từ upstream được ghi log.
D. Chuyển retry của HTTP thành rollback transaction SQL.
Đáp án đúng: A

Câu 17. Circuit breaker trong mesh có thể bảo vệ upstream bằng cách nào?
A. Gửi thêm request đến upstream lỗi để kiểm tra sớm.
B. Đổi mọi HTTP status thành 200 khi backend quá tải.
C. Hạn chế request mới khi upstream lỗi hoặc quá tải.
D. Xóa mọi route khi một Pod trả về timeout đầu tiên.
Đáp án đúng: C

Câu 18. Outlier detection trong cân bằng tải thường có tác dụng gì?
A. Tự tạo Pod mới thay cho Kubernetes Horizontal Autoscaler.
B. Tạm loại endpoint có nhiều lỗi khỏi tập phục vụ request.
C. Chuyển toàn bộ traffic sang một endpoint bất kể sức khỏe.
D. Bỏ qua dữ liệu lỗi và giữ nguyên mọi endpoint đang hỏng.
Đáp án đúng: B

Câu 19. Giới hạn connection pool trên proxy tới upstream thường được dùng để làm gì?
A. Khống chế số kết nối đồng thời để tránh cạn tài nguyên.
B. Thay thuật toán băm partition key của database backend.
C. Giữ cookie đăng nhập của mọi client trong proxy gateway.
D. Buộc dịch vụ chỉ dùng một endpoint khi cân bằng tải.
Đáp án đúng: A

Câu 20. Thuật toán cân bằng `least request` hướng tới lựa chọn nào?
A. Ưu tiên endpoint hiện có ít request đang xử lý hơn.
B. Ưu tiên endpoint có đường dẫn URL ngắn nhất.
C. Ưu tiên endpoint vừa phát sinh nhiều HTTP 500 nhất.
D. Ưu tiên endpoint nhận request từ cùng IP người dùng.
Đáp án đúng: A

Câu 21. Định tuyến theo locality trong mesh thường tận dụng thông tin nào?
A. Checksum binary ứng dụng để chọn phiên bản gần nhất.
B. Tên nhánh Git chứa cấu hình deployment hiện tại.
C. Địa chỉ email của nhóm sở hữu dịch vụ backend.
D. Ưu tiên endpoint cùng zone hoặc region khi phù hợp.
Đáp án đúng: D

Câu 22. Lợi ích cốt lõi của mutual TLS (mTLS) giữa workload trong mesh là gì?
A. Cho phép mọi client truy cập mà không cần phân quyền.
B. Xác thực hai phía và mã hóa đường truyền giữa dịch vụ.
C. Thay chữ ký số chứng chỉ bằng HTTP header tự khai.
D. Đảm bảo nội dung request đáp ứng mọi quy tắc nghiệp vụ.
Đáp án đúng: B

Câu 23. Chứng chỉ workload dùng trong mesh mTLS thường đại diện cho danh tính nào?
A. Danh tính cá nhân đã đăng nhập trình duyệt vào website.
B. Tên bảng dữ liệu mà application đang thực hiện truy vấn.
C. Địa chỉ email của người viết mã trong Git repository.
D. Danh tính workload hoặc service của hạ tầng mesh, không phải user cuối.
Đáp án đúng: D

Câu 24. Cơ chế tự động cấp và luân chuyển chứng chỉ trong mesh nhằm giảm rủi ro gì?
A. Database bị phân mảnh do các yêu cầu ghi đồng thời.
B. HTTP route đổi trọng số ngoài lịch phát hành ứng dụng.
C. Tracing bị thiếu span khi Pod khởi động nhiều lần.
D. Tránh chứng chỉ hết hạn và thay khóa theo chu kỳ.
Đáp án đúng: D

Câu 25. Với chính sách mTLS ở chế độ strict, lưu lượng plaintext tới workload sẽ ra sao?
A. Từ chối kết nối không thiết lập được mTLS hợp lệ.
B. Được chấp nhận và gắn nhãn chưa xác thực trong log.
C. Được tự mã hóa bằng cách thêm một HTTP header mới.
D. Được chuyển tới backend không mã hóa mà không cảnh báo.
Đáp án đúng: A

Câu 26. Trong giai đoạn chuyển đổi sang mTLS, chế độ permissive thường hỗ trợ điều gì?
A. Bắt buộc mọi workload dùng mTLS ngay trong lần đầu.
B. Ngắt tất cả kết nối cũ trước khi cấp chứng chỉ mới.
C. Chỉ cho lưu lượng plaintext khi client là trình duyệt.
D. Tạm chấp nhận cả kết nối mTLS và plaintext.
Đáp án đúng: D

Câu 27. Chính sách authorization dựa trên service identity phù hợp với mục tiêu nào?
A. Cho toàn bộ request qua nếu địa chỉ Pod chưa từng thay.
B. Luôn tin request chỉ vì nó đã đi qua mạng Kubernetes.
C. Chỉ cho workload được cấp phép gọi tới endpoint bảo vệ.
D. Cho mọi tài khoản người dùng cuối quyền truy cập database.
Đáp án đúng: C

Câu 28. Mặc định deny và chỉ cấp allow rõ ràng trong mesh mang ý nghĩa nào?
A. Cho request lạ truy cập nếu chưa tạo luật từ chối riêng.
B. Chỉ chặn traffic qua Internet, bỏ qua kết nối nội bộ.
C. Mọi service gọi nhau được vì đều thuộc một namespace.
D. Chặn mặc định; chỉ cho request được cấp phép.
Đáp án đúng: D

Câu 29. Vì sao authorization ở mesh không thay thế kiểm tra quyền nghiệp vụ trong ứng dụng?
A. Mesh tự kiểm tra mọi vai trò của người dùng trong database.
B. Mesh chỉ có thể xem được thông tin ở tầng vật lý L1.
C. Mesh tự cập nhật bảng quyền chi tiết cho từng đơn hàng.
D. Mesh không biết đủ quy tắc quyền trên từng tài nguyên.
Đáp án đúng: D

Câu 30. Để quản lý egress từ microservice ra dịch vụ ngoài cluster, mesh có thể hỗ trợ gì?
A. Buộc mọi HTTP request đến Internet bỏ qua proxy.
B. Chuyển mọi tên miền công cộng thành địa chỉ loopback.
C. Áp dụng chính sách outbound và kiểm soát điểm đến.
D. Vô hiệu hóa cơ chế xác thực TLS của dịch vụ bên ngoài.
Đáp án đúng: C

Câu 31. Fault injection với delay hoặc abort có ích trong hoạt động nào?
A. Thử khả năng phục hồi khi mô phỏng lỗi và độ trễ.
B. Giảm mọi lỗi upstream bằng cách sửa HTTP status.
C. Đảm bảo database đồng bộ sau mọi network partition.
D. Tự cân bằng CPU của tất cả Pod trong Kubernetes.
Đáp án đúng: A

Câu 32. Khi đánh giá chất lượng gọi dịch vụ qua mesh, nhóm metric nào hữu ích nhất?
A. Số nhánh Git, kích thước image và số lượng file.
B. Số commit theo ngày và lượng mã đã thay đổi.
C. Request rate, error rate và latency của dịch vụ.
D. Số lượng nhãn Pod mà không xét request thành công.
Đáp án đúng: C

Câu 33. Distributed tracing trong mesh cần điều kiện nào để nối các span xuyên dịch vụ?
A. Vô hiệu hóa mọi HTTP header khi qua proxy sidecar.
B. Tạo mỗi span bằng một trace ID độc lập ngẫu nhiên.
C. Truyền trace context nhất quán giữa các request qua nhiều dịch vụ.
D. Chỉ thu thập metric CPU mà không cần request ID.
Đáp án đúng: C

Câu 34. Sampling trong hệ thống tracing thường dùng để cân bằng điều gì?
A. Giảm latency bằng cách xóa mọi retry trên proxy.
B. Giảm chi phí thu thập nhưng vẫn giữ một phần dấu vết để phân tích.
C. Tăng tính nhất quán database bằng cách khóa ghi.
D. Giảm quyền workload bằng cách tắt chứng chỉ mTLS.
Đáp án đúng: B

Câu 35. Access log của proxy khác số liệu metric tổng hợp ở khía cạnh nào?
A. Log chỉ thể hiện CPU; metric chỉ thể hiện SQL schema.
B. Log luôn thay distributed tracing trên mọi dịch vụ.
C. Log theo request; metric thể hiện xu hướng tổng hợp.
D. Log tự phát hiện và sửa lỗi mạng mà không cần người.
Đáp án đúng: C

Câu 36. Nếu request có HTTP 503 tăng, bước kiểm tra ban đầu nào phù hợp?
A. Chỉ tăng timeout đến giá trị vô hạn cho mọi request.
B. Tắt toàn bộ authorization để xác định người dùng.
C. Xem endpoint khỏe, route, mTLS và lỗi upstream.
D. Xóa cấu hình control plane rồi khởi động lại tất cả.
Đáp án đúng: C

Câu 37. Khi control plane tạm mất kết nối, data plane thường có thể làm gì?
A. Tiếp tục proxy bằng cấu hình hợp lệ đã nhận.
B. Ngắt mọi kết nối hiện có dù proxy vẫn khỏe.
C. Xóa endpoint từ bộ nhớ trước mỗi lần nhận request.
D. Tự tạo lại toàn bộ control plane trên node client.
Đáp án đúng: A

Câu 38. Cơ chế tự động chèn sidecar proxy vào Pod Kubernetes thường tác động lúc nào?
A. Khi Pod đã chạy nhiều giờ và tự đổi container image.
B. Admission webhook thêm sidecar vào Pod lúc tạo.
C. Khi kubelet tự sửa DNS record của backend trong Pod.
D. Khi control plane xóa tất cả Service trên namespace.
Đáp án đúng: B

Câu 39. Kubernetes NetworkPolicy và mesh authorization thường khác nhau ở điểm nào?
A. NetworkPolicy lọc L3/L4; mesh xét identity và L7.
B. NetworkPolicy thay mTLS và mesh chỉ lọc CPU của Pod.
C. NetworkPolicy quản lý JWT còn mesh chỉ quản lý DNS.
D. NetworkPolicy thay mọi RBAC nghiệp vụ của ứng dụng.
Đáp án đúng: A

Câu 40. Khi nào bổ sung service mesh có thể chưa đáng so với chi phí vận hành?
A. Khi có nhiều nhóm cần mTLS và quản trị lưu lượng thống nhất.
B. Khi giao tiếp nội bộ cần phân quyền theo danh tính workload.
C. Khi hệ ít dịch vụ, nhu cầu policy và quan sát còn đơn giản.
D. Khi lượng microservice lớn, liên tục canary và đánh giá lỗi.
Đáp án đúng: C
