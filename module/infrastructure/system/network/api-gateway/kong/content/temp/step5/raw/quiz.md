Câu 1. Trong Kong Gateway, đối tượng Service thường mô tả điều gì?
A. Điều kiện chọn request từ client theo đường dẫn.
B. Backend mà gateway sẽ chuyển tiếp request đến.
C. Danh tính người dùng hoặc ứng dụng gọi API.
D. Quy tắc giới hạn lưu lượng của từng consumer.
Đáp án đúng: B

Câu 2. Trong Kong Gateway, Route có chức năng chính nào?
A. Cấu hình danh sách Target của một Upstream.
B. Route khớp request rồi chọn Service để định tuyến.
C. Lưu credential xác thực cho người gọi API.
D. Ghi nhật ký mọi request vào database riêng.
Đáp án đúng: B

Câu 3. Khi cần cân bằng nhiều backend dưới một hostname logic, đối tượng nào phù hợp?
A. Consumer đại diện nhóm Target phía sau Service.
B. Route đại diện danh sách server backend vật lý.
C. Credential đại diện các địa chỉ backend vật lý.
D. Upstream đại diện các Target phía sau Service.
Đáp án đúng: D

Câu 4. Đối tượng Target của một Upstream trong Kong mô tả điều gì?
A. Target gồm địa chỉ backend và trọng số cân bằng.
B. Điều kiện path và method của request đầu vào.
C. Định danh consumer và credential đăng nhập.
D. Cấu hình plugin chạy riêng cho mọi endpoint.
Đáp án đúng: A

Câu 5. Trong Kong, Consumer biểu diễn đối tượng nào?
A. Consumer là danh tính client sử dụng API gateway.
B. Server backend nhận request từ gateway nội bộ.
C. Quy tắc dùng để khớp host và path của request.
D. Nhóm máy chủ mà Upstream phân phối lưu lượng.
Đáp án đúng: A

Câu 6. Kong Plugin có thể được áp dụng với phạm vi cấu hình nào?
A. Chỉ toàn cục cho toàn bộ request gateway nhận.
B. Chỉ cho Target đang hoạt động trong Upstream.
C. Chỉ cho một node trong cụm cơ sở dữ liệu Kong.
D. Plugin gắn toàn cục hoặc Service/Route/Consumer.
Đáp án đúng: D

Câu 7. Khi bật `strip_path` trên Route khớp tiền tố `/api`, tác động chính là gì?
A. Loại phần path khớp trước khi chuyển tới Service.
B. Giữ nguyên toàn bộ path và thêm tiền tố `/api`.
C. Loại header Host trước khi gọi đến backend.
D. Đổi HTTP method thành GET khi chuyển tiếp request.
Đáp án đúng: A

Câu 8. Khi bật `preserve_host` trên Route, Kong thường xử lý Host header thế nào?
A. Đổi Host thành tên Consumer đang xác thực.
B. Chuyển Host gốc khi proxy đến upstream.
C. Loại Host để backend tự suy ra từ path.
D. Đổi Host thành ID của Route vừa khớp request.
Đáp án đúng: B

Câu 9. Nếu Route chỉ khớp method `GET`, request `POST` cùng path sẽ ra sao?
A. Vẫn khớp Route vì path đã được cấu hình.
B. Không khớp Route đó vì HTTP method khác.
C. Được đổi thành GET trước khi vào backend.
D. Được coi là request từ Consumer mới.
Đáp án đúng: B

Câu 10. Để tránh gửi request đến backend đã hỏng, Upstream có thể dùng cơ chế nào?
A. Route tự xóa Target khi thấy lỗi HTTP 404.
B. Consumer tự chuyển Target sang trạng thái idle.
C. Plugin CORS kiểm tra kết nối tới từng Target.
D. Health check đánh dấu Target khỏe hoặc lỗi.
Đáp án đúng: D

Câu 11. Khác biệt chính giữa active và passive health checks là gì?
A. Active chờ request; passive gửi probe theo lịch.
B. Active gửi probe; passive quan sát traffic thật.
C. Active chỉ dùng TCP; passive chỉ dùng chứng chỉ.
D. Active thay đổi Route; passive thay đổi Consumer.
Đáp án đúng: B

Câu 12. Target có trọng số bằng 0 trong Upstream thường mang ý nghĩa gì?
A. Nhận toàn bộ lưu lượng thay vì các Target khác.
B. Bắt buộc nhận health check nhưng chặn mọi log.
C. Xóa mọi Route dùng chung với Upstream đó.
D. Không nhận lưu lượng mới qua cơ chế cân bằng.
Đáp án đúng: D

Câu 13. Khi hai Target khỏe có weight 3 và 1, cách hiểu phù hợp là gì?
A. Target đầu chỉ nhận request có header đặc biệt.
B. Target đầu dự kiến nhận lưu lượng nhiều hơn.
C. Target thứ hai luôn nhận request trước Target đầu.
D. Target đầu phải có ba Consumer mới được chọn.
Đáp án đúng: B

Câu 14. Trong cấu hình Service, tham số timeout hỗ trợ điều gì?
A. Giới hạn thời gian sống credential của Consumer.
B. Giới hạn thời gian cấu hình lưu trong decK.
C. Giới hạn thời gian máy khách được giữ API key.
D. Đặt timeout kết nối, gửi và đọc từ backend.
Đáp án đúng: D

Câu 15. Key Authentication Plugin thường kiểm tra thông tin nào?
A. Địa chỉ Target thuộc Upstream đang hoạt động.
B. Kiểm tra API key từ client tại vị trí cấu hình.
C. Checksum của tệp declarative config của decK.
D. Phân vùng dữ liệu trong database của backend.
Đáp án đúng: B

Câu 16. Sau khi bật key-auth, credential thường được liên kết với đối tượng nào?
A. Upstream chứa các server backend được cân bằng.
B. Route chứa danh sách path và HTTP method.
C. Consumer được định danh để áp dụng chính sách.
D. Target chứa địa chỉ hostname của backend.
Đáp án đúng: C

Câu 17. JWT Plugin của Kong chủ yếu thực hiện việc gì khi nhận token?
A. Tự cấp OAuth access token từ refresh token.
B. Thay JWT thành API key trước khi gửi upstream.
C. Xác minh JWT theo thông tin khóa và quy tắc.
D. Lưu mọi JWT đã dùng vào database của backend.
Đáp án đúng: C

Câu 18. Khi kết hợp ACL Plugin với xác thực, nhóm ACL thường áp dụng cho ai?
A. Consumer đã được xác thực và gán nhóm phù hợp.
B. Target đã được health check và gán nhóm phù hợp.
C. Route đã được khai báo path và method phù hợp.
D. Upstream được gán nhiều endpoint backend khác.
Đáp án đúng: A

Câu 19. Khi request vượt giới hạn do Rate Limiting Plugin, mã HTTP thường gặp là gì?
A. HTTP 401 biểu thị thiếu quyền đối với backend.
B. HTTP 301 biểu thị chuyển hướng sang Target khác.
C. HTTP 429 khi request vượt ngưỡng quota.
D. HTTP 204 biểu thị hoàn tất mà không có nội dung.
Đáp án đúng: C

Câu 20. Trong nhiều Kong node, rate-limit policy `local` cần lưu ý điều gì?
A. Bộ đếm luôn được đồng bộ cho toàn bộ Kong cluster.
B. Bộ đếm luôn được lưu trực tiếp trong request header.
C. Bộ đếm theo từng node nên tổng hạn mức có thể lệch.
D. Bộ đếm được chia sẻ qua DNS của toàn bộ upstream.
Đáp án đúng: C

Câu 21. Trong triển khai nhiều Kong node, vì sao policy đếm giới hạn qua Redis hữu ích?
A. Tự động chuyển tất cả Target sang HTTP/2 khi có tải.
B. Thay thế mọi Plugin xác thực chạy trước backend.
C. Loại bỏ nhu cầu quan sát latency và HTTP status.
D. Chia sẻ bộ đếm giúp kiểm soát quota giữa các node.
Đáp án đúng: D

Câu 22. CORS Plugin của Kong chủ yếu giải quyết nhu cầu nào?
A. Áp dụng OAuth scope cho token của mọi client backend.
B. Đặt timeout cho TCP connection đến từng Target.
C. Đặt chính sách cross-origin cho trình duyệt.
D. Đảm bảo request chỉ được xử lý ở đúng một node.
Đáp án đúng: C

Câu 23. Request Transformer Plugin thường dùng để thay đổi thành phần nào?
A. Trọng số và địa chỉ Target của mỗi Upstream.
B. Quyền quản trị của tài khoản dùng Admin API.
C. Thứ tự các node trong cụm database gateway.
D. Thêm hoặc sửa header, query và body request.
Đáp án đúng: D

Câu 24. IP Restriction Plugin của Kong phù hợp với trường hợp nào?
A. Giới hạn số request theo Consumer và phút.
B. Xác thực JWT bằng chữ ký bất đối xứng.
C. Cho phép hoặc chặn địa chỉ IP và dải CIDR.
D. Xóa thông tin đăng nhập khỏi mọi request.
Đáp án đúng: C

Câu 25. Khi định tuyến TLS dựa trên SNI, SNI được gửi tại giai đoạn nào?
A. SNI nằm trong TLS handshake, trước HTTP request.
B. Sau khi gateway đã chuyển xong response.
C. Sau khi backend đọc hết request body.
D. Khi decK cập nhật cấu hình trong Admin API.
Đáp án đúng: A

Câu 26. Vì sao cần giới hạn truy cập vào Kong Admin API?
A. Admin API chỉ hiển thị dữ liệu metric đã ẩn danh.
B. Admin API chỉ cho phép ping các Target bị lỗi.
C. Admin API có quyền sửa cấu hình gateway, plugin.
D. Admin API chỉ trả thông tin công khai của Consumer.
Đáp án đúng: C

Câu 27. Với Kong DB-less mode, cấu hình gateway thường lấy từ đâu?
A. Toàn bộ changeset Liquibase lưu trong PostgreSQL.
B. Đọc tệp cấu hình khai báo, không dùng database.
C. Credential tự sinh từ mỗi request đầu vào của client.
D. Thông tin Target được lấy từ DNS mà không cần cấu hình.
Đáp án đúng: B

Câu 28. Lệnh `deck gateway dump` được dùng chủ yếu để làm gì?
A. Xuất cấu hình gateway ra tệp dạng khai báo.
B. So sánh cấu hình tệp với gateway mà không thay đổi.
C. Áp dụng cấu hình tệp vào gateway qua Admin API.
D. Xóa toàn bộ plugin không có trong tệp khai báo.
Đáp án đúng: A

Câu 29. Trước khi áp cấu hình, `deck gateway diff` hỗ trợ việc nào?
A. Ghi cấu hình từ gateway thành tệp cấu hình mới.
B. Đối chiếu cấu hình mong muốn với gateway hiện tại.
C. Tự khởi động lại mọi instance đang chạy.
D. Chuyển mô hình database sang chế độ DB-less.
Đáp án đúng: B

Câu 30. Khi cần áp dụng trạng thái declarative qua decK, lệnh nào phù hợp?
A. `deck gateway dump` áp dụng thay đổi theo tệp.
B. `deck gateway sync` đồng bộ cấu hình theo tệp.
C. `deck gateway diff` tự thực thi toàn bộ thay đổi.
D. `deck file validate` cập nhật plugin và Route.
Đáp án đúng: B

Câu 31. Khi quản lý Kong config bằng Git và decK, lợi ích chính là gì?
A. Theo dõi thay đổi cấu hình để review và tái lập.
B. Loại bỏ nhu cầu dùng thông tin bí mật bảo mật.
C. Đảm bảo mọi request không bao giờ bị timeout.
D. Cho phép mọi người chỉnh Admin API không kiểm soát.
Đáp án đúng: A

Câu 32. Kong Ingress Controller trong Kubernetes có nhiệm vụ chủ yếu nào?
A. Tự chạy câu lệnh SQL trên backend của từng Service.
B. Thay Kubernetes API server quản lý mọi tài nguyên.
C. Chạy ứng dụng API thay cho container backend thực.
D. Dùng tài nguyên Kubernetes để cấu hình Kong.
Đáp án đúng: D

Câu 33. Trong Kubernetes, tài nguyên Ingress thường mô tả điều gì cho gateway?
A. Credential của từng Consumer để xác thực.
B. Trạng thái của từng Target ở mỗi datacenter.
C. Chính sách sao lưu database của gateway.
D. Ánh xạ host hoặc path tới Kubernetes Service.
Đáp án đúng: D

Câu 34. Với Kong Ingress Controller, tài nguyên `KongPlugin` dùng vào việc gì?
A. Chỉ định pod mặc định giữ vai trò leader.
B. Định nghĩa mật khẩu đăng nhập Kubernetes API.
C. Khai báo plugin gắn với các tài nguyên của Kong.
D. Quản lý số bản sao ReplicaSet của backend.
Đáp án đúng: C

Câu 35. Trong Kubernetes Gateway API, `HTTPRoute` thường biểu diễn điều gì?
A. Định danh của người dùng và API key đã cấp.
B. Thiết lập tài nguyên lưu trữ cho ingress pod.
C. Định tuyến HTTP theo match tới backend tham chiếu.
D. Chỉ số CPU và bộ nhớ của gateway cluster.
Đáp án đúng: C

Câu 36. Để Prometheus thu thập số liệu Kong, loại plugin nào thường dùng?
A. Prometheus Plugin cung cấp metric để scrape.
B. Key Authentication Plugin xuất metric về TCP.
C. Request Transformer Plugin tự thu thập CPU.
D. ACL Plugin ghi metric dưới dạng database log.
Đáp án đúng: A

Câu 37. Correlation ID Plugin giúp điều tra request bằng cách nào?
A. Gắn ID để lần theo cùng request trong các log.
B. Chỉ cho phép request của một Consumer mỗi lần.
C. Đồng bộ token JWT giữa các Kong node đang chạy.
D. Tự tạo Route khi request có Host chưa khai báo.
Đáp án đúng: A

Câu 38. Khi tỷ lệ HTTP 502/503 tăng đột biến, nhóm dữ liệu nào nên kiểm tra?
A. Chỉ số lần decK chạy mà không xem backend.
B. Số lượng Consumer chưa được tạo credential.
C. Chỉ tổng số Route mà không xem mã lỗi.
D. Kiểm tra sức khỏe Target, latency và error log.
Đáp án đúng: D

Câu 39. Trong kiến trúc hybrid của Kong, control plane có vai trò nào?
A. Quản lý cấu hình rồi phân phối đến các data plane.
B. Nhận toàn bộ request công khai thay các data plane.
C. Chạy mọi ứng dụng backend và lưu dữ liệu nghiệp vụ.
D. Thay thế hoàn toàn cơ chế TLS ở mọi data plane.
Đáp án đúng: A

Câu 40. Nếu kết nối control plane tạm gián đoạn trong hybrid mode, data plane thường có thể làm gì?
A. Tự ngắt mọi Route cho đến lúc đồng bộ xong.
B. Xóa tất cả Target vì không còn điều phối.
C. Tiếp tục proxy bằng cấu hình đã nhận trước đó.
D. Tạo Consumer mới từ request không xác thực.
Đáp án đúng: C
