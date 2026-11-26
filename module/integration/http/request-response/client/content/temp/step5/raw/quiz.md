Câu 1. Client muốn gửi giá trị query `q` bằng `a&b`. Cách tạo URI nào giữ nguyên một giá trị?
A. Mã hóa thành `?q=a%26b` trong URI request.
B. Thay thành `?q=a/b` trong URI request.
C. Nối `?q=a&b` trực tiếp vào URI request.
D. Mã hóa thành `?q=a+b` trong URI request.
Đáp án đúng: A

Câu 2. Base URI là `https://api.example.com/v1/`. Tham chiếu tương đối `orders` được resolve thành gì?
A. `https://api.example.com/v1/orders`.
B. `https://api.example.com/v1?orders`.
C. `https://api.example.com/v1orders`.
D. `https://api.example.com/orders`.
Đáp án đúng: A

Câu 3. Theo HTTP, GET được coi là phương thức safe khi đáp ứng ý nghĩa nào?
A. Client gửi lại GET đúng một lần trên mỗi kết nối.
B. Client không yêu cầu thay đổi trạng thái tài nguyên.
C. Response không được có body hoặc header cache.
D. Server bảo đảm không ghi log hoặc sinh metric nào.
Đáp án đúng: B

Câu 4. Client gửi `POST /payments` rồi bị timeout. Nguy cơ nào phải tính đến?
A. Status chưa có nên server chắc chắn đã rollback.
B. Timeout xác nhận server chưa hề nhận request.
C. HTTP tự loại request trùng bằng connection ID.
D. Server có thể đã tạo thanh toán trước khi mất phản hồi.
Đáp án đúng: D

Câu 5. Vì sao gửi lại cùng PUT đến cùng URI thường được coi là idempotent?
A. PUT bắt buộc bỏ qua body của request thứ hai.
B. Mỗi lần PUT đều phải tạo thêm một tài nguyên mới.
C. Lặp cùng PUT có tác động dự định như gửi một lần.
D. PUT chỉ được gửi khi tài nguyên chưa từng tồn tại.
Đáp án đúng: C

Câu 6. Với HTTP PATCH, phát biểu nào đúng về tính idempotent?
A. PATCH luôn safe vì không tạo tài nguyên mới.
B. PATCH có thể idempotent tùy theo phép cập nhật.
C. PATCH luôn idempotent vì chỉ sửa một phần dữ liệu.
D. PATCH bắt buộc chỉ thay một trường trong mỗi lần.
Đáp án đúng: B

Câu 7. Khi HTTP client nhận status `204 No Content`, cần xử lý body như thế nào?
A. Yêu cầu server gửi body có trường `Location`.
B. Không kỳ vọng body nội dung trong response đó.
C. Đọc JSON body biểu diễn tài nguyên vừa được tạo.
D. Đọc error body để lấy mã lỗi của operation.
Đáp án đúng: B

Câu 8. HTTP `429 Too Many Requests` thường báo hiệu điều gì?
A. Server từ chối vì thông tin xác thực chưa hợp lệ.
B. Server từ chối vì kích thước request vượt giới hạn.
C. Server tạm thời không sẵn sàng xử lý yêu cầu.
D. Server đang giới hạn tốc độ request của client.
Đáp án đúng: D

Câu 9. Trong HTTP request có body, vai trò `Content-Type` và `Accept` khác nhau ra sao?
A. `Accept` mô tả body gửi; `Content-Type` mô tả response mong muốn.
B. `Content-Type` mã hóa URI; `Accept` cấu hình request timeout.
C. `Accept` giới hạn method; `Content-Type` giới hạn response status.
D. `Content-Type` mô tả body gửi; `Accept` mô tả response mong muốn.
Đáp án đúng: D

Câu 10. Thông thường, client nên hiểu `401` và `403` khác nhau thế nào?
A. `401` báo thiếu resource; `403` báo sai đường dẫn URL.
B. `401` là lỗi timeout; `403` là lỗi kết nối TCP.
C. `401` thiếu xác thực hợp lệ; `403` bị từ chối quyền.
D. `401` yêu cầu đổi method; `403` cho phép retry tự động.
Đáp án đúng: C

Câu 11. HTTP client truyền OAuth bearer access token bằng cách nào?
A. Gửi `Authorization: Bearer <token>` trong request.
B. Gửi `Content-Type: Bearer <token>` trong request.
C. Gửi `Cache-Control: Bearer <token>` trong request.
D. Gửi `Accept: Bearer <token>` trong request.
Đáp án đúng: A

Câu 12. Để nối trace giữa HTTP client và server theo W3C Trace Context, client làm gì?
A. Đặt trace ID vào header `Content-Length` của request.
B. Truyền ngữ cảnh trace qua HTTP header `traceparent`.
C. Đặt trace ID vào HTTP status của response.
D. Đặt trace ID vào header `Accept` của request.
Đáp án đúng: B

Câu 13. Thiết kế nào giúp JDK `HttpClient` tận dụng kết nối tốt hơn?
A. Đóng HttpClient trước khi tạo request mới.
B. Tạo một HttpClient mới cho từng lần retry.
C. Tạo một HttpClient mới sau mỗi response.
D. Tái sử dụng một HttpClient để gửi nhiều request.
Đáp án đúng: D

Câu 14. Trong JDK HttpClient, thiết lập timeout riêng cho `HttpRequest` bằng cách nào?
A. Gọi `HttpRequest.Builder.connectTimeout(...)`.
B. Gọi `HttpClient.Builder.readTimeout(...)`.
C. Gọi `HttpRequest.Builder.timeout(Duration)`.
D. Gọi `HttpResponse.Builder.timeout(...)`.
Đáp án đúng: C

Câu 15. Trong JDK HttpClient, `sendAsync(request, handler)` thường trả về kiểu gì?
A. Một `Stream<HttpResponse<T>>` đợi dữ liệu.
B. Một `HttpResponse<T>` hoàn tất đồng bộ.
C. Một `CompletableFuture<HttpResponse<T>>`.
D. Một `Publisher<HttpResponse<T>>` bất đồng bộ.
Đáp án đúng: C

Câu 16. Muốn kiểm soát chính sách tự đi theo HTTP redirect với JDK HttpClient, làm gì?
A. Dùng `timeout(...)` để cho phép mọi redirect.
B. Cấu hình `followRedirects(...)` trên HttpClient builder.
C. Dùng `Redirect.ALWAYS` mặc định ở mọi client.
D. Thêm `Location` vào request để bật redirect.
Đáp án đúng: B

Câu 17. Khi cấu hình HTTP client, connect timeout và request timeout khác nhau thế nào?
A. Cả hai chỉ giới hạn thời gian tra cứu DNS trước lúc gửi request.
B. Request timeout chỉ đặt trên server; connect timeout chỉ ở client.
C. Connect timeout giới hạn đọc body; request timeout giới hạn TCP handshake.
D. Connect timeout giới hạn lập kết nối; request timeout giới hạn request.
Đáp án đúng: D

Câu 18. Với JDK `HttpClient`, handler nào dùng để nhận response body dạng chuỗi?
A. Dùng `HttpRequest.Builder.body()` để nhận body.
B. Dùng `HttpClient.Builder.body()` để nhận body.
C. Dùng `BodyHandlers.ofString()` để nhận body.
D. Dùng `BodyPublishers.ofString()` để nhận body.
Đáp án đúng: C

Câu 19. Khi DNS lookup thất bại trước lúc có HTTP response, client Java thường nhận gì?
A. `HttpResponse` với status 302 cùng `Location`.
B. `HttpResponse` với status 204 và body trống.
C. `HttpResponse` với status 404 sau khi hoàn thành DNS.
D. Lỗi kết nối/tra cứu tên thay vì HTTP status hợp lệ.
Đáp án đúng: D

Câu 20. Provider có thể treo không phản hồi. HTTP client nên xử lý thế nào?
A. Đặt request timeout và báo lỗi có kiểm soát.
B. Bỏ request timeout và chỉ tăng số thread gửi.
C. Retry vô hạn đến khi provider phản hồi lại.
D. Vô hiệu hóa timeout nhưng mở thêm kết nối.
Đáp án đúng: A

Câu 21. Chính sách retry nào phù hợp nhất cho HTTP client gọi dịch vụ bên ngoài?
A. Retry GET khi lỗi tạm thời với số lần giới hạn.
B. Retry liên tục với response `400 Bad Request`.
C. Retry mọi `401` mà không sửa thông tin xác thực.
D. Retry mọi POST bất kể khả năng ghi dữ liệu trùng.
Đáp án đúng: A

Câu 22. Exponential backoff kèm jitter nhằm cải thiện điều gì khi retry?
A. Gửi tất cả retry cùng lúc khi server bị quá tải.
B. Giảm thời gian chờ sau mỗi lần server lỗi.
C. Tăng thời gian chờ và phân tán thời điểm thử lại.
D. Giữ khoảng chờ cố định cho toàn bộ client.
Đáp án đúng: C

Câu 23. Với server hỗ trợ idempotency key, khi retry POST tạo đơn hàng do mất response, cơ chế nào giảm tạo trùng?
A. Giữ idempotency key giống nhau giữa các lần retry.
B. Đổi idempotency key ở mỗi lần gửi lại POST.
C. Dùng timestamp mới thay cho cùng request ID.
D. Bỏ khóa request để server coi mỗi retry là mới.
Đáp án đúng: A

Câu 24. Header `Retry-After` trong response `429` thường dùng để chỉ điều gì?
A. Giới hạn thời gian client có thể đọc body.
B. Khoảng chờ hoặc thời điểm nên thử request lại.
C. Thời gian server đã xử lý request trước đó.
D. Thời gian hết hạn TLS của kết nối client.
Đáp án đúng: B

Câu 25. Với JDK `HttpClient` và `BodyHandlers.ofInputStream()`, khi chỉ đọc một phần body, client nên làm gì?
A. Bỏ tham chiếu `HttpResponse` rồi để GC thu hồi stream.
B. Đóng `InputStream` nếu không đọc tiếp để giải phóng tài nguyên.
C. Gửi request kế tiếp để client tự đóng stream đang mở.
D. Tăng request timeout để stream hiện tại tự được giải phóng.
Đáp án đúng: B

Câu 26. Đặc điểm nào đúng với Spring `WebClient`?
A. Hỗ trợ chuỗi xử lý HTTP theo kiểu reactive.
B. Luôn dùng một thread riêng cho mỗi response.
C. Bắt buộc gọi `.block()` trên mọi request.
D. Chỉ hỗ trợ GET, không gửi body với POST.
Đáp án đúng: A

Câu 27. Spring `RestClient` phù hợp nhất với kiểu lập trình nào?
A. HTTP server dùng công bố REST endpoint.
B. Reactive client chỉ trả về `Mono` và `Flux`.
C. HTTP client fluent với cách gọi đồng bộ.
D. API gRPC chạy trên HTTP/2 trong Spring.
Đáp án đúng: C

Câu 28. Với Spring `WebClient.retrieve()`, cách tùy chỉnh xử lý HTTP error là gì?
A. Gọi `.uri()` để đổi status lỗi thành `200`.
B. Gọi `.accept()` để bỏ qua mọi status lỗi.
C. Gọi `.bodyToMono()` để retry mọi response 5xx.
D. Gọi `.onStatus(...)` để ánh xạ response lỗi.
Đáp án đúng: D

Câu 29. Khi cần liên kết log HTTP client qua nhiều dịch vụ và phân tích độ trễ, bộ thông tin nào phù hợp nhất?
A. Ghi method, status, endpoint đã lọc và số kết nối pool.
B. Ghi method, trace ID, kích thước response và tên host.
C. Ghi status, độ trễ, kích thước response và địa chỉ IP.
D. Ghi method, status, độ trễ và trace ID phù hợp.
Đáp án đúng: D

Câu 30. Để kiểm thử timeout của HTTP client mà không phụ thuộc mạng thật, làm gì?
A. Giả lập server trả HTTP 408 ngay rồi kiểm tra xử lý status.
B. Giả lập server trả HTTP 504 ngay rồi kiểm tra retry.
C. Giả lập server phản hồi chậm rồi kiểm tra timeout.
D. Giả lập server ngắt kết nối ngay rồi kiểm tra lỗi I/O.
Đáp án đúng: C

Câu 31. Để quan sát retry gây tăng tải cho dịch vụ bên ngoài, bộ metrics nào hữu ích nhất?
A. Đo throughput và CPU client nhưng không thống kê retry.
B. Đo độ trễ, lỗi, timeout và số lượt retry.
C. Đo số kết nối pool và lượng request nhưng bỏ qua lỗi.
D. Đo tỷ lệ thành công và p95 latency nhưng bỏ số lần retry.
Đáp án đúng: B

Câu 32. Khi bắt `InterruptedException` từ `HttpClient.send(...)`, xử lý nào phù hợp?
A. Khôi phục cờ interrupt hoặc chuyển lỗi lên caller.
B. Chuyển lỗi thành response `200 OK` của server.
C. Nuốt lỗi và tự động retry vô hạn trong thread.
D. Xóa cờ interrupt rồi tiếp tục chạy như thường.
Đáp án đúng: A
