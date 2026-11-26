Câu 01. Trong Spring Cloud Gateway, một route HTTP thường được mô tả bằng nhóm thông tin nào?
A. Route ID, URI đích, predicates và danh sách filters
B. Route ID, servlet context, view name và session
C. Route ID, bean controller, interceptor và serializer
D. Route ID, tên queue, message listener và consumer
Đáp án đúng: A

Câu 02. Khi muốn route các đường dẫn `/api/orders/**` đến service đơn hàng, predicate nào phù hợp?
A. Host predicate với mẫu `/api/orders/**` cho request
B. Method predicate với mẫu `/api/orders/**` cho request
C. Query predicate với mẫu `/api/orders/**` cho request
D. Path predicate với mẫu `/api/orders/**` cho request
Đáp án đúng: D

Câu 03. Muốn route xử lý request `POST` thay vì `GET`, loại predicate nào phù hợp?
A. Host predicate kiểm phương thức HTTP của request
B. Cookie predicate kiểm phương thức HTTP của request
C. Path predicate kiểm phương thức HTTP của request
D. Method predicate so khớp HTTP method yêu cầu
Đáp án đúng: D

Câu 04. Khi một route có cả Path và Method predicate, điều kiện match được áp dụng thế nào?
A. Request bỏ qua Method nếu đã match Path trước
B. Request chỉ cần trùng một predicate trong route
C. Request thỏa đồng thời các predicate của route
D. Request được chọn theo predicate cấu hình ở cuối
Đáp án đúng: C

Câu 05. Khi hai route đều match một request, yếu tố nào giúp kiểm soát route nào được xét trước?
A. Giá trị order của route, số thấp có ưu tiên cao
B. Timeout kết nối tới backend, giá trị nhỏ ưu tiên
C. Độ dài route ID, ID ngắn sẽ được chọn trước
D. Thứ tự khởi tạo các bean service phía backend
Đáp án đúng: A

Câu 06. Muốn route theo hostname `api.example.com`, predicate nào nên chọn?
A. Host predicate so khớp hostname của request
B. Method predicate so khớp hostname của request
C. RemoteAddr predicate so khớp hostname của request
D. Path predicate so khớp hostname của request
Đáp án đúng: A

Câu 07. Một route chỉ nhận request có header `X-Tenant` đúng mẫu; nên dùng predicate nào?
A. Cookie predicate kiểm tên header và biểu thức giá trị
B. Query predicate kiểm tên header và biểu thức giá trị
C. Path predicate kiểm tên header và biểu thức giá trị
D. Header predicate kiểm tên header và biểu thức giá trị
Đáp án đúng: D

Câu 08. Muốn route khi query parameter `version` có giá trị `v2`, predicate nào phù hợp?
A. Header predicate so khớp tham số và giá trị query
B. Path predicate so khớp tham số và giá trị query
C. Query predicate so khớp tham số và giá trị query
D. Host predicate so khớp tham số và giá trị query
Đáp án đúng: C

Câu 09. Trong cấu hình Gateway, khác biệt chính giữa predicate và filter là gì?
A. Predicate quyết định URI; filter khởi tạo TCP listener
B. Predicate tạo token; filter quyết định bean controller
C. Predicate sửa header; filter chọn route từ registry
D. Predicate chọn route; filter can thiệp request/response
Đáp án đúng: D

Câu 10. Nếu mọi route cần thêm một correlation header, nên đặt logic ở đâu?
A. GlobalFilter xử lý request thuộc nhiều route của gateway
B. DiscoveryClient tạo header cho mỗi service instance
C. GatewayFilter gắn riêng cho một route không cấu hình lại
D. RoutePredicateFactory sửa header trước khi tìm route
Đáp án đúng: A

Câu 11. Với hai filter có thứ tự khác nhau, quy tắc thực thi pre/post trong Gateway là gì?
A. Filter ưu tiên cao chạy pre sau và post trước
B. Filter ưu tiên thấp chạy pre sau và post sau
C. Filter ưu tiên thấp chạy pre trước và post trước
D. Filter ưu tiên cao chạy pre trước và post sau
Đáp án đúng: D

Câu 12. Muốn bổ sung header `X-Correlation-Id` vào request gửi xuống backend, chọn filter nào?
A. RemoveRequestHeader thêm một header vào request đi tiếp
B. AddRequestHeader thêm một header vào request đi tiếp
C. SetResponseHeader thêm một header vào request đi tiếp
D. AddResponseHeader thêm một header vào request đi tiếp
Đáp án đúng: B

Câu 13. Muốn thay giá trị header request `X-Env` thay vì cộng thêm giá trị, chọn filter nào?
A. RemoveResponseHeader loại bỏ header response
B. AddRequestHeader nối giá trị vào header request
C. AddResponseHeader đặt lại giá trị header response
D. SetRequestHeader đặt lại giá trị header request
Đáp án đúng: D

Câu 14. Trước khi chuyển request tới backend, cần bỏ header `X-Internal-Debug`; filter nào đúng?
A. RemoveRequestHeader loại header khỏi request gửi đi
B. RemoveResponseHeader loại header khỏi request gửi đi
C. AddRequestHeader loại header khỏi request gửi đi
D. RewriteResponseHeader loại header khỏi request gửi đi
Đáp án đúng: A

Câu 15. Backend nhận `/orders/42`, còn public API là `/api/v1/orders/42`; filter nào bỏ hai segment đầu?
A. SetPath với số segment đầu là 2
B. RewriteResponseHeader với số segment là 2
C. StripPrefix với số segment là 2
D. PrefixPath với số segment là 2
Đáp án đúng: C

Câu 16. Muốn đổi `/legacy/items/42` thành `/v2/items/42` theo biểu thức chính quy, nên dùng gì?
A. AddRequestParameter với regex và replacement của path
B. RewriteResponseHeader với regex và replacement của path
C. RewritePath filter với regex và replacement của path
D. SetResponseHeader với regex và replacement của path
Đáp án đúng: C

Câu 17. Khi backend yêu cầu prefix `/internal` trước đường dẫn hiện tại, filter nào phù hợp?
A. StripPrefix thêm `/internal` trước request path
B. PrefixPath thêm `/internal` trước request path
C. RemoveRequestHeader thêm `/internal` trước path
D. AddResponseHeader thêm `/internal` trước path
Đáp án đúng: B

Câu 18. Muốn thêm header `X-Gateway-Version` vào response trả client, nên dùng filter nào?
A. RemoveRequestHeader tác động đến response đi về client
B. AddResponseHeader tác động đến response đi về client
C. SetPath tác động đến response đi về client
D. AddRequestHeader tác động đến response đi về client
Đáp án đúng: B

Câu 19. Trong URI route `lb://catalog-service`, phần `lb` biểu thị cơ chế nào?
A. Chỉ định codec JSON của upstream thông qua service ID
B. Chỉ định file certificate của backend bằng local bundle
C. Chọn instance backend thông qua Spring Cloud LoadBalancer
D. Chọn database pool từ tên instance trong URI route
Đáp án đúng: C

Câu 20. Muốn tự tạo routes dựa trên các service được DiscoveryClient biết đến, cần cơ chế nào?
A. LoadBalancer Health Indicator để sinh response body
B. GlobalFilter của Security để tự khai báo controller
C. HttpClient response decoder để tự đăng ký endpoint
D. DiscoveryClient Route Definition Locator để sinh route
Đáp án đúng: D

Câu 21. API Gateway cần xác minh Bearer JWT được gửi tới route protected; tích hợp nào phù hợp?
A. Gateway Retry filter đọc JWT thay cho xác thực token
B. Spring Security OAuth2 Resource Server kiểm JWT hợp lệ
C. RequestRateLimiter filter kiểm chữ ký JWT thay backend
D. Spring Security OAuth2 Client thay producer để ký JWT
Đáp án đúng: B

Câu 22. JWT hợp lệ nhưng thiếu quyền `orders:write`; gateway nên xử lý authorization thế nào?
A. Kiểm authority/scope yêu cầu trước khi chuyển upstream
B. Để RequestRateLimiter quyết định đủ quyền cho route
C. Dùng Route predicate Path thay việc kiểm scope token
D. Kiểm token còn hạn rồi chấp nhận bỏ qua authority
Đáp án đúng: A

Câu 23. Khi gateway đăng nhập OAuth2 và cần chuyển access token cho downstream, filter nào liên quan?
A. SecureHeaders chuyển access token OAuth2 tới dịch vụ đích
B. Retry chuyển access token OAuth2 tới dịch vụ đích
C. SaveSession chuyển access token OAuth2 tới dịch vụ đích
D. TokenRelay chuyển access token OAuth2 tới dịch vụ đích
Đáp án đúng: D

Câu 24. Gateway nhận `X-Forwarded-Host` từ client internet chưa qua proxy tin cậy; nguy cơ nào cần tránh?
A. Header giả làm circuit breaker tăng timeout kết nối
B. Header giả có thể khiến hệ thống dùng hostname sai
C. Header giả thay đổi số Redis tokens của gateway
D. Header giả khiến TLS certificate tự được thay mới
Đáp án đúng: B

Câu 25. Dịch vụ cần giới hạn số request trên từng người dùng; filter nào phù hợp?
A. RequestRateLimiter dùng key để áp chính sách quota
B. TokenRelay dùng key để áp chính sách quota
C. CircuitBreaker dùng key để áp chính sách quota
D. RewritePath dùng key để áp chính sách quota
Đáp án đúng: A

Câu 26. Để tránh nhiều user cùng chia sẻ một quota, `KeyResolver` nên trả về thông tin gì?
A. Định danh chung của route được chọn cho request
B. Định danh người dùng đã xác thực của request
C. Tên service instance vừa được LoadBalancer chọn
D. Địa chỉ backend cố định ghi trong cấu hình route
Đáp án đúng: B

Câu 27. Trong RedisRateLimiter của Gateway, `replenishRate` thường quyết định điều gì?
A. Số request chuyển tới backend trong một TCP packet
B. Tốc độ nạp token vào bucket theo đơn vị thời gian
C. Số lần filter retry khi backend trả về HTTP 503
D. Số token lớn nhất bucket giữ tại cùng một thời điểm
Đáp án đúng: B

Câu 28. Trong RedisRateLimiter, `burstCapacity` chủ yếu ảnh hưởng gì?
A. Dung lượng tối đa của bucket dành cho request bùng nổ
B. Số lần thử lại trong filter Retry cho một HTTP request
C. Số token được nạp mới sau mỗi giây theo cấu hình
D. Số route dự phòng được LoadBalancer duy trì trong cache
Đáp án đúng: A

Câu 29. Khi RequestRateLimiter từ chối một request do vượt giới hạn, status HTTP mặc định nào thường trả về?
A. HTTP 429 Too Many Requests cho yêu cầu bị giới hạn
B. HTTP 401 Unauthorized cho yêu cầu bị giới hạn
C. HTTP 502 Bad Gateway cho yêu cầu bị giới hạn
D. HTTP 504 Gateway Timeout cho yêu cầu bị giới hạn
Đáp án đúng: A

Câu 30. Một upstream liên tục trả lỗi làm các lần gọi tiếp theo cũng tốn tài nguyên; filter nào giúp ngắt tạm?
A. RewritePath đổi URI khi breaker đang mở
B. AddRequestHeader tăng timeout khi breaker đang mở
C. Retry tăng số lần gọi khi breaker đang mở
D. CircuitBreaker ngừng gọi khi trạng thái breaker đang mở
Đáp án đúng: D

Câu 31. Khi CircuitBreaker mở và cần phản hồi dự phòng tại handler nội bộ, route nên cấu hình gì?
A. Predicate `Host` để tự tạo handler nội bộ mới
B. Fallback URI dạng `forward:/fallback` cho filter
C. URI dạng `lb:/fallback` để gọi handler nội bộ
D. Header `Location` để Gateway đổi thành fallback
Đáp án đúng: B

Câu 32. Request GET bị lỗi 503 tạm thời từ upstream; filter nào cho thử gửi lại có kiểm soát?
A. Retry filter cho status 503 với số lần thử giới hạn
B. CircuitBreaker filter gửi lại ngay cả khi đang mở
C. StripPrefix filter thử lại khi path bị rút ngắn
D. SecureHeaders filter thử lại khi response thiếu header
Đáp án đúng: A

Câu 33. Vì sao cấu hình retry với POST tạo đơn hàng có rủi ro nếu chưa có idempotency?
A. Request lặp làm TLS certificate hết hạn khi nhận
B. Request lặp khiến route tự đổi method thành GET
C. Request lặp có thể tạo đơn hàng trùng ở backend
D. Request lặp sẽ khiến Header predicate thành false
Đáp án đúng: C

Câu 34. Khi upstream đang chậm, cấu hình retry có backoff và giới hạn số lần nhằm giảm rủi ro gì?
A. Giảm số route cần khai báo trong RouteDefinition
B. Giảm lượng request dồn dập khuếch đại tải lên upstream
C. Giảm yêu cầu giải mã JWT cho mỗi lượt client kết nối
D. Giảm nhu cầu cấu hình SSL certificate ở gateway
Đáp án đúng: B

Câu 35. Muốn public endpoint gateway dùng HTTPS, thành phần nào cần được cấu hình?
A. HTTP route predicate với URI backend `http://`
B. RequestRateLimiter có Redis key với thời hạn dài
C. TLS listener với certificate/key phù hợp tại gateway
D. Backend Retry filter có số lần thử phù hợp
Đáp án đúng: C

Câu 36. Gateway kết nối tới backend bằng HTTPS, cần kiểm soát riêng yếu tố nào?
A. Xác minh số lượng GatewayFilter trên cùng route
B. Xác minh cache của RedisRateLimiter cho backend
C. Xác minh chứng chỉ và trust của upstream TLS
D. Xác minh session cookie SameSite từ client trình duyệt
Đáp án đúng: C

Câu 37. Gateway nhận CORS preflight từ trình duyệt; điều kiện cần bảo đảm là gì?
A. CircuitBreaker filter bỏ qua kiểm tra preflight
B. CORS policy cho phép origin, method và header cần dùng
C. Retry filter chuyển preflight thành một POST upstream
D. RewritePath filter cấp access token cho trình duyệt
Đáp án đúng: B

Câu 38. Muốn từ chối request body vượt ngưỡng dung lượng tại gateway, nên chọn filter nào?
A. RequestRateLimiter giới hạn kích thước body đầu vào
B. SecureHeaders filter giới hạn kích thước body đầu vào
C. RewriteResponseHeader giới hạn kích thước body đầu vào
D. RequestSize filter giới hạn kích thước body đầu vào
Đáp án đúng: D

Câu 39. Khi xác định route nào có tỷ lệ HTTP 5xx và latency cao, cần xem loại dữ liệu nào?
A. Chỉ Redis memory metrics không có HTTP status
B. Chỉ số class trong image mà service được build
C. Gateway request metrics gắn route ID và HTTP status
D. Chỉ JVM heap metrics không có thông tin route ID
Đáp án đúng: C

Câu 40. Để truy vết một request đi qua Gateway tới các microservices, phương án nào phù hợp?
A. Chỉ thu metrics CPU ở Gateway, bỏ dấu vết upstream
B. Ghi mỗi service một trace không giữ parent context
C. Truyền trace context và liên kết span giữa các chặng
D. Thay trace ID bằng route ID dùng chung cho request
Đáp án đúng: C
