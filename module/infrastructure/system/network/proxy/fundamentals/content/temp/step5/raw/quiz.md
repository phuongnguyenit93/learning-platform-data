Câu 01. Forward proxy thường được đặt ở đâu trong đường đi của request?
A. Giữa client và Internet để thay client gọi server đích.
B. Trước nhóm backend, thay server tiếp nhận request từ client.
C. Ngay trong database, thay backend xử lý các truy vấn SQL.
D. Trong bộ cân bằng tải, thay DNS phân giải tên miền public.
Đáp án đúng: A

Câu 02. Reverse proxy thường đại diện cho phía nào trong kiến trúc web?
A. Phía database, cung cấp transaction cho nhiều ứng dụng.
B. Phía client, áp chính sách truy cập Internet theo người dùng.
C. Phía DNS, phát hành bản ghi địa chỉ cho từng browser.
D. Phía server, nhận request rồi chuyển tới backend phù hợp.
Đáp án đúng: D

Câu 03. Một explicit HTTP proxy thường yêu cầu client cấu hình gì?
A. Khóa TLS riêng của mọi website mà client định kết nối.
B. Port của từng service backend đang đứng sau reverse proxy.
C. Địa chỉ proxy mà client sẽ gửi request cần chuyển tiếp.
D. Địa chỉ IP backend nội bộ thay cho DNS của tên miền public.
Đáp án đúng: C

Câu 04. Transparent proxy khác explicit proxy chủ yếu ở điểm nào?
A. Traffic chỉ được chuyển nếu client chỉ định proxy trong browser.
B. Traffic được mã hóa TLS từ đầu tới cuối bởi proxy mặc định.
C. Traffic chỉ đi tới backend khi request có header Proxy-Authorization.
D. Traffic được chuyển qua proxy mà client không chủ động khai báo.
Đáp án đúng: D

Câu 05. Với HTTPS qua HTTP forward proxy bằng CONNECT, hành vi cơ bản là gì?
A. Proxy buộc client gửi toàn bộ TLS payload trong URI.
B. Proxy tự giải mã mọi HTTPS body khi client gọi CONNECT.
C. Proxy đổi HTTPS thành HTTP rồi trả chứng chỉ của đích.
D. Proxy tạo TCP tunnel để client trao đổi TLS với đích.
Đáp án đúng: D

Câu 06. Một proxy TCP layer 4 thông thường có thể định tuyến theo thông tin nào?
A. Địa chỉ IP và cổng kết nối, không cần đọc HTTP path.
B. JWT claim của người dùng trong header Authorization.
C. Cookie ứng dụng dùng xác định trang tài nguyên đang gọi.
D. HTTP path và query được phân tích từ request GET.
Đáp án đúng: A

Câu 07. Muốn chuyển /api/orders đến orders service và /api/users đến users service, cần gì?
A. Proxy TCP chỉ quan sát cổng đích mà không phân tích HTTP.
B. DNS resolver phân tích URI để chuyển riêng từng HTTP path.
C. Proxy HTTP có khả năng khớp route theo đường dẫn request.
D. Firewall chỉ kiểm tra TCP handshake ở đầu mỗi kết nối.
Đáp án đúng: C

Câu 08. Đặt reverse proxy ở rìa hệ thống có lợi ích kiến trúc nào?
A. Tập trung xử lý giao dịch phân tán thay cho ứng dụng.
B. Tập trung logic tính giá đơn hàng thay cho từng backend.
C. Tập trung ghi dữ liệu nghiệp vụ vào database của mọi service.
D. Tập trung TLS, kiểm soát truy cập và routing vào backend.
Đáp án đúng: D

Câu 09. Trong TLS handshake, SNI có vai trò nào tại reverse proxy?
A. Chỉ tên máy chủ cần chọn certificate trước khi đọc HTTP.
B. Cho biết access token đã được browser xác thực thành công.
C. Cho biết khóa cache chính xác của body từng response.
D. Cho biết giá trị path để proxy định tuyến theo route REST.
Đáp án đúng: A

Câu 10. Header Host trong HTTP thường được reverse proxy sử dụng thế nào?
A. Đối chiếu khóa bí mật của client để xác thực JWT.
B. Đối chiếu trạng thái ổ đĩa để chọn instance ít tải.
C. Đối chiếu cổng TCP nguồn để xác định quyền người dùng.
D. Dùng Host để chọn virtual host hay upstream route.
Đáp án đúng: D

Câu 11. Vì sao backend không nên tin mọi X-Forwarded-For từ Internet?
A. Header đó luôn được kernel TCP kiểm tra tính xác thực.
B. Client có thể giả X-Forwarded-For nếu proxy không lọc header.
C. Header đó luôn được TLS ký độc lập với request gốc.
D. Header đó chỉ chứa địa chỉ IP của proxy gần backend nhất.
Đáp án đúng: B

Câu 12. Khi có nhiều proxy nối tiếp, cách xác định IP client nào đáng tin hơn?
A. Chọn IP cuối cùng và xem đó luôn là người dùng cuối.
B. Chỉ tin các hop proxy đã cấu hình và xử lý chuỗi IP đúng.
C. Chọn IP riêng đầu tiên, bỏ qua các hop còn lại trong chuỗi.
D. Chọn IP đầu tiên trong header do bất kỳ client nào gửi.
Đáp án đúng: B

Câu 13. Header X-Forwarded-Proto thường chuyển tiếp thông tin gì?
A. Scheme gốc như https để backend dựng URL và redirect.
B. Phiên bản TLS mà browser đang dùng trong handshake.
C. Chuỗi các địa chỉ IP từng đi qua của request hiện tại.
D. Phương thức HTTP ban đầu như GET, POST hoặc DELETE.
Đáp án đúng: A

Câu 14. Header Forwarded chuẩn HTTP hỗ trợ nhóm tham số nào?
A. Thông tin for, by, host và proto qua các proxy trung gian.
B. Thông tin Retry-After, RateLimit và các mã trạng thái HTTP.
C. Thông tin ETag, Vary, Age và Cache-Control của response.
D. Thông tin Cookie, Set-Cookie, SameSite và HttpOnly của user.
Đáp án đúng: A

Câu 15. PROXY protocol hữu ích khi proxy TCP cần làm gì?
A. Chuyển chứng chỉ client thành HTTP Authorization header.
B. Truyền địa chỉ nguồn gốc tới backend có hỗ trợ giao thức.
C. Mã hóa lại mọi frame TCP trước khi gửi đến máy chủ đích.
D. Thay TCP payload bằng JSON có thể xử lý tại reverse proxy.
Đáp án đúng: B

Câu 16. Trong HTTP/1.1, proxy cần chú ý nhóm header hop-by-hop nào?
A. Host và Content-Type dùng mô tả request gửi upstream.
B. Connection cùng những trường được liệt kê trong đó.
C. Accept và User-Agent dùng thể hiện đặc điểm của client.
D. ETag và Last-Modified dùng kiểm tra cache có điều kiện.
Đáp án đúng: B

Câu 17. Header Via trên request/response giúp thể hiện điều gì?
A. Những certificate được dùng qua các TLS handshake.
B. Những tài nguyên đã được client đọc từ browser cache.
C. Những proxy trung gian đã chuyển tiếp thông điệp HTTP.
D. Những tài khoản đã qua bước kiểm tra quyền tại proxy.
Đáp án đúng: C

Câu 18. TLS termination tại reverse proxy có nghĩa cơ bản nào?
A. Proxy chuyển mọi request HTTPS thành TCP không có kiểm soát.
B. Proxy kết thúc TLS từ client rồi xử lý request phía trong.
C. Proxy tự cấp chứng chỉ mới cho từng backend không cần cấu hình.
D. Proxy luôn giữ TLS end-to-end mà không nhìn thấy HTTP.
Đáp án đúng: B

Câu 19. Nếu muốn mã hóa cả đoạn proxy đến backend sau TLS termination, cần gì?
A. Chỉ bật HTTPS từ client tới proxy là đủ mã hóa toàn tuyến.
B. Thêm X-Forwarded-Proto: https để mã hóa lưu lượng nội bộ.
C. Bật nén gzip cho body để tránh lộ dữ liệu trên đường truyền.
D. Thiết lập TLS riêng từ proxy tới upstream và xác minh đích.
Đáp án đúng: D

Câu 20. Khi proxy dùng mTLS để gọi backend, certificate phía proxy làm gì?
A. Đảm bảo các HTTP header đã được ứng dụng ký bằng JWT.
B. Chứng minh danh tính proxy với upstream qua certificate.
C. Thay thế chứng chỉ server để backend không phải chứng minh gì.
D. Buộc tất cả request có quyền ghi mọi tài nguyên nghiệp vụ.
Đáp án đúng: B

Câu 21. Vì sao proxy cần xác minh chứng chỉ TLS của upstream?
A. Để bỏ qua bước kiểm tra token đăng nhập tại ứng dụng.
B. Tránh kết nối nhầm máy chủ hoặc bị giả mạo giữa đường.
C. Để tự bảo đảm HTTP response không có lỗi nghiệp vụ.
D. Để chọn backend có CPU thấp nhất trước khi gửi request.
Đáp án đúng: B

Câu 22. Round-robin khi cân bằng tải qua reverse proxy thường hoạt động thế nào?
A. Luôn chọn upstream có ít kết nối còn đang hoạt động nhất.
B. Luôn chọn upstream có độ trễ quan sát được nhỏ nhất.
C. Chọn upstream theo hash của cookie để giữ sticky session.
D. Phân phối request lần lượt tới các backend khả dụng.
Đáp án đúng: D

Câu 23. Least-connections balancing ưu tiên upstream có đặc điểm nào?
A. Địa chỉ IP đứng đầu trong danh sách được DNS trả về.
B. Số yêu cầu từ hôm qua ít hơn theo lịch sử access log.
C. Thời gian khởi động gần nhất trong các instance backend.
D. Chọn upstream có ít kết nối hoạt động theo bộ đếm hiện tại.
Đáp án đúng: D

Câu 24. Một health check chủ động tại proxy thường thực hiện gì?
A. Gửi probe định kỳ tới backend để kiểm tra khả năng phục vụ.
B. Chỉ kiểm tra DNS một lần khi process proxy khởi động.
C. Chỉ đánh giá tuổi của TLS certificate trước mỗi deploy.
D. Chỉ dựa vào lỗi từ request người dùng mà không gửi probe.
Đáp án đúng: A

Câu 25. Passive health check khác active health check chủ yếu ở đâu?
A. Gửi probe đều đặn đến endpoint readiness của upstream.
B. Dựa vào lỗi của request thực tế thay vì chỉ gửi probe định kỳ.
C. Đánh giá tiến trình backend bằng cách đọc trực tiếp bộ nhớ.
D. Phát hiện lỗi chỉ từ thay đổi DNS trước khi có request.
Đáp án đúng: B

Câu 26. Khi toàn bộ upstream của một route không khỏe, phản hồi nào phù hợp?
A. 409 Conflict để biểu thị xung đột phiên bản của tài nguyên.
B. 401 Unauthorized để buộc client gửi lại access token.
C. 503 Service Unavailable để báo không có backend phục vụ.
D. 404 Not Found để nói rằng URI chưa tồn tại trên hệ thống.
Đáp án đúng: C

Câu 27. Sticky session trong load balancing có nhược điểm nào?
A. Giúp mọi backend tự trở thành stateless mà không cần store.
B. Loại bỏ nhu cầu health check cho các instance trong pool.
C. Có thể gây mất cân bằng tải giữa các backend cùng pool.
D. Luôn giữ trạng thái phiên còn nguyên khi instance đó hỏng.
Đáp án đúng: C

Câu 28. Khi cache response tại reverse proxy, cache key cần xét gì?
A. Chỉ IP client vì response không thay đổi giữa các endpoint.
B. Host, path, query cùng các biến thể theo header cần thiết.
C. Chỉ địa chỉ IP upstream vì mọi URI ở đó chung dữ liệu.
D. Chỉ dung lượng response vì body cùng kích thước là tương đương.
Đáp án đúng: B

Câu 29. Tác dụng của Vary: Accept-Encoding đối với shared proxy cache là gì?
A. Đặt TTL bắt buộc cho response dựa trên độ dài header.
B. Gộp mọi response gzip và identity thành cùng một cache entry.
C. Phân biệt response theo giá trị Accept-Encoding của request.
D. Xóa mọi cache entry khi client chuyển sang dùng HTTP/2.
Đáp án đúng: C

Câu 30. Vì sao không nên shared-cache response cá nhân hóa tùy tiện?
A. Response cá nhân hóa luôn không có header Content-Type.
B. Response cá nhân hóa không thể có ETag hay Last-Modified.
C. Dữ liệu riêng có thể bị trả nhầm cho người dùng khác.
D. Dữ liệu riêng luôn bị TLS biến thành response không lưu được.
Đáp án đúng: C

Câu 31. Cache-Control: no-cache và no-store khác nhau theo cách nào?
A. no-cache cần revalidate, còn no-store không cho lưu response.
B. no-cache cấm lưu; no-store cho dùng lại đến hết max-age.
C. no-cache chỉ cho browser; no-store chỉ cho shared proxy.
D. no-cache bắt dùng HTTPS; no-store yêu cầu HTTP/1.1.
Đáp án đúng: A

Câu 32. Với cache TTL đồng loạt hết hạn, proxy có thể gặp vấn đề gì?
A. Đường TLS giữa proxy và backend tự ngắt ở thời điểm TTL.
B. Nhiều request cùng miss và dồn tải tái tạo về backend.
C. Toàn bộ HTTP request được proxy tự chuyển thành TCP tunnel.
D. Header Host bị xóa trên mọi request khi entry hết hạn.
Đáp án đúng: B

Câu 33. Nếu proxy trả 502 Bad Gateway, giả thuyết nào phù hợp nhất?
A. Upstream gửi phản hồi lỗi định dạng hoặc reset.
B. Proxy đã xác thực user nhưng từ chối quyền tài nguyên.
C. Proxy thấy cache hợp lệ nên không phải gọi upstream.
D. Proxy chặn client vì vượt hạn mức request theo phút.
Đáp án đúng: A

Câu 34. Mã 504 Gateway Timeout thường gợi ý tình huống nào?
A. Proxy không tìm thấy route tương ứng với host và path.
B. Client gửi request sai cú pháp header hoặc nội dung.
C. Proxy không nhận phản hồi upstream trong thời hạn chờ cấu hình.
D. Client chưa cung cấp chứng chỉ mTLS theo chính sách.
Đáp án đúng: C

Câu 35. Phân biệt connect timeout với read timeout của proxy như thế nào?
A. Connect chờ ghi log; read chờ load cấu hình DNS.
B. Connect chờ xử lý SQL; read chờ client nhận cache hit.
C. Connect chờ thiết lập TCP; read chờ upstream gửi dữ liệu.
D. Connect chờ xác thực JWT; read chờ tra cứu route.
Đáp án đúng: C

Câu 36. Khi proxy cân nhắc retry POST sau lỗi mạng, điều gì quan trọng?
A. Request có thể đã ghi thành công; retry cần idempotency.
B. Lỗi mạng luôn đồng nghĩa backend chưa từng nhận request.
C. Proxy tự rollback transaction nghiệp vụ sau mọi lần retry.
D. POST luôn idempotent nên có thể retry không giới hạn.
Đáp án đúng: A

Câu 37. Với WebSocket qua HTTP/1.1 reverse proxy, cần lưu ý gì?
A. Xử lý đúng Upgrade handshake và giữ kết nối hai chiều.
B. Chuyển toàn bộ WebSocket frame thành HTTP GET riêng biệt.
C. Buộc proxy cache mỗi frame như một response HTTP độc lập.
D. Đóng upstream sau 101 Switching Protocols thành công.
Đáp án đúng: A

Câu 38. Với Server-Sent Events qua reverse proxy, cấu hình nào đáng xem xét?
A. Buộc đổi SSE sang WebSocket trước khi phục vụ client.
B. Luôn gom hết event rồi trả một body khi request kết thúc.
C. Tránh buffering làm chậm các event truyền trực tiếp.
D. Bật cache chung mọi stream theo IP của upstream.
Đáp án đúng: C

Câu 39. Nếu thời gian phản hồi qua proxy cao nhưng backend xử lý nhanh, nên kiểm tra gì?
A. Chỉ thời gian biên dịch mã nguồn của ứng dụng backend.
B. Chỉ bộ nhớ browser mà không kiểm tra các chặng mạng.
C. Chỉ số lượng bảng trong database của dịch vụ backend.
D. Kiểm tra độ trễ DNS, TCP, TLS, queue và buffering tại proxy.
Đáp án đúng: D

Câu 40. Biện pháp nào giảm nguy cơ forward proxy bị lạm dụng như open proxy?
A. Cho mọi địa chỉ Internet dùng proxy để dễ chia sẻ băng thông.
B. Cho phép CONNECT đến mọi cổng mà không xác minh chính sách.
C. Tắt access log để không lưu dấu truy cập của các client.
D. Xác thực, áp ACL đích và hạn chế client được phép sử dụng.
Đáp án đúng: D
