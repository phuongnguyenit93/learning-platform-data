Câu 1. Webhook khác polling HTTP định kỳ ở điểm chính nào?
A. Provider POST tới URL đã đăng ký khi xảy ra sự kiện.
B. Consumer duy trì HTTP GET để lấy bản ghi mới.
C. Client tự gọi API để kiểm tra sự kiện mới theo chu kỳ.
D. Consumer tự đọc message bằng kết nối đến broker.
Đáp án đúng: A

Câu 2. Khi tạo subscription webhook, cặp thông tin nào thường cần cấu hình?
A. Tên message queue và số partition của broker.
B. Tên bảng database và chỉ mục dữ liệu provider.
C. URL callback và những loại sự kiện muốn nhận.
D. Địa chỉ máy chủ và tài khoản nội bộ provider.
Đáp án đúng: C

Câu 3. Payload webhook có event envelope; bộ trường nào phù hợp để mô tả sự kiện?
A. HTTP status, cache key, cookie và body response.
B. Event ID, event type, occurredAt và payload.
C. Database host, port, table name và transaction ID.
D. CPU load, thread ID, số kết nối và thời gian GC.
Đáp án đúng: B

Câu 4. Để nhận ra một sự kiện được provider gửi lại, receiver nên dùng gì?
A. Địa chỉ IP nguồn mà HTTP request đang sử dụng.
B. Thời điểm request đến server ở lần nhận hiện tại.
C. Định danh kết nối TCP của lượt gửi đến hiện tại.
D. Event ID ổn định qua các lượt gửi cùng sự kiện.
Đáp án đúng: D

Câu 5. Provider ký HMAC trực tiếp trên byte của HTTP body. Receiver phải xác minh ra sao?
A. Tính HMAC trên byte body gốc mà provider ký.
B. Chỉ dùng giá trị `eventId` thay cho toàn bộ body.
C. Chỉ lấy các query parameter để tính chữ ký HMAC.
D. Tạo JSON mới từ object rồi tính HMAC trên JSON đó.
Đáp án đúng: A

Câu 6. HMAC dùng thành phần nào để xác thực tính toàn vẹn thông điệp?
A. Chứng chỉ TLS tự sinh cho mỗi lần HTTP callback.
B. Khóa công khai của provider và chữ ký bất đối xứng.
C. Mã băm của payload không cần bí mật chia sẻ.
D. Hàm băm kết hợp khóa bí mật chia sẻ giữa hai bên.
Đáp án đúng: D

Câu 7. Khi so sánh chữ ký HMAC kỳ vọng với chữ ký nhận được, cách nào an toàn hơn?
A. So sánh byte tuần tự và dừng ở byte sai đầu tiên.
B. Dùng so sánh constant-time để giảm rò rỉ thời gian.
C. Giải mã chữ ký thành chuỗi rồi bỏ qua ký tự khác.
D. Chỉ so sánh một phần đầu của giá trị chữ ký.
Đáp án đúng: B

Câu 8. Receiver muốn giảm nguy cơ replay của request đã ký hợp lệ. Cách nào phù hợp?
A. Chấp nhận mọi timestamp khi chữ ký HMAC hợp lệ.
B. Kiểm tra timestamp theo cửa sổ thời gian cho phép.
C. Lưu trữ chữ ký ở header nhưng bỏ qua hạn sử dụng.
D. Chỉ dựa vào TLS mà không kiểm tra thời điểm nhận.
Đáp án đúng: B

Câu 9. Khi quay vòng shared secret của webhook, phương án nào giảm gián đoạn?
A. Tái dùng một khóa duy nhất mãi cho mọi provider.
B. Ngừng kiểm tra HMAC trong suốt quá trình đổi.
C. Chấp nhận có giới hạn cả khóa cũ và khóa mới.
D. Đổi khóa ngay mà không báo cho phía còn lại.
Đáp án đúng: C

Câu 10. Endpoint nhận webhook cần phản hồi nhanh nhưng xử lý sự kiện mất nhiều thời gian. Nên làm gì?
A. Lưu bền vào queue trước khi trả HTTP thành công.
B. Đợi toàn bộ bước nghiệp vụ hoàn tất rồi mới trả lời.
C. Thực hiện các lần retry của provider trong HTTP handler.
D. Trả thành công ngay trước khi lưu bất kỳ thông tin nào.
Đáp án đúng: A

Câu 11. Ý nghĩa thông thường của HTTP 2xx với webhook sender là gì?
A. Event đã được loại khỏi mọi queue của provider.
B. Receiver đã xử lý trọn mọi bước nghiệp vụ về sau.
C. Receiver báo đã tiếp nhận request theo giao thức.
D. Provider cam kết sẽ gửi lại request trong vài phút.
Đáp án đúng: C

Câu 12. Sender gửi webhook bị timeout và không nhận response. Suy luận nào đúng?
A. Receiver chắc chắn đã xóa toàn bộ dữ liệu của sự kiện.
B. Receiver có thể đã xử lý dù sender bị timeout.
C. Receiver bắt buộc phải gửi event mới có ID khác.
D. Receiver chắc chắn chưa đọc bất kỳ byte nào từ request.
Đáp án đúng: B

Câu 13. Với lỗi mạng tạm thời, lịch retry webhook nào phù hợp để tránh dồn tải?
A. Retry theo khoảng cố định giống nhau ở mọi sender.
B. Retry liên tục ngay lập tức với số lần không giới hạn.
C. Retry tất cả phản hồi 4xx liên tục đến khi nhận 2xx.
D. Retry giới hạn với exponential backoff và jitter.
Đáp án đúng: D

Câu 14. Khi webhook endpoint quá tải tạm thời, phản hồi nào giúp sender điều chỉnh retry?
A. HTTP 301 đến chính endpoint đang quá tải.
B. HTTP 200 rồi bỏ request để tránh nghẽn queue.
C. HTTP 400 kèm header xác thực không hợp lệ.
D. Trả 503 và `Retry-After` nếu sender hỗ trợ.
Đáp án đúng: D

Câu 15. Receiver có thể nhận trùng một event nhiều lần. Cách nào ngăn tác động nghiệp vụ lặp?
A. Tăng số worker để các bản sao được xử lý song song.
B. Gắn timestamp mới để mỗi lần giao lại là event khác.
C. Lưu event ID trong kho idempotency bền vững.
D. Xóa event ID sau mỗi lần chạy handler thành công.
Đáp án đúng: C

Câu 16. Receiver vừa lưu event ID vừa cập nhật số dư. Cách nào tránh trạng thái ghi dở?
A. Trả 200 trước, sau đó xử lý cả hai thao tác không đồng bộ.
B. Đặt hai thao tác ở các worker độc lập chạy song song.
C. Ghi dấu idempotency và cập nhật DB trong một transaction.
D. Lưu event ID vào cache rồi cập nhật DB khi có thời gian.
Đáp án đúng: C

Câu 17. Hai bản cập nhật cùng thực thể đến sai thứ tự. Receiver nên dựa vào đâu?
A. Thứ tự TCP packet của kết nối callback hiện tại.
B. Thời điểm worker được scheduler phân CPU.
C. Thứ tự key xuất hiện trong JSON request body.
D. Sequence hoặc version của thực thể trong payload.
Đáp án đúng: D

Câu 18. Hai worker xử lý đồng thời event cùng một thực thể. Cách nào ngăn ghi đè state mới?
A. Đọc trước state rồi luôn ghi lại không điều kiện.
B. Tăng queue prefetch để worker nhận nhiều event hơn.
C. Dùng kiểm tra version nguyên tử khi cập nhật state.
D. Đổi tên event ID để mỗi worker có giá trị riêng.
Đáp án đúng: C

Câu 19. Sự kiện webhook đến theo đợt tăng vọt. Queue trung gian giúp điều gì?
A. Bảo đảm mỗi event không bao giờ bị giao lại.
B. Bảo đảm mọi event được xử lý đúng thời gian thực.
C. Loại hẳn nhu cầu xác thực chữ ký trên request.
D. Đệm tải để worker xử lý theo năng lực sẵn có.
Đáp án đúng: D

Câu 20. Worker webhook bắt đầu gây quá tải database. Giải pháp backpressure nào phù hợp?
A. Giới hạn concurrency và dung lượng queue chờ.
B. Tăng vô hạn số worker để xử lý sự kiện thật nhanh.
C. Tắt mọi giới hạn số message đang xử lý song song.
D. Cho phép mỗi retry tạo bản sao event mới trong DB.
Đáp án đúng: A

Câu 21. Sự kiện lỗi liên tục sau số lần thử tối đa nên được xử lý thế nào?
A. Luôn đưa lại vào đầu queue xử lý chính không giới hạn.
B. Chuyển sang dead-letter queue để điều tra lỗi.
C. Bỏ log và xóa message vì retry đã hết số lần.
D. Thử lại ngay mà không lưu thông tin thất bại.
Đáp án đúng: B

Câu 22. Cần xử lý theo thứ tự từng đơn hàng khi có nhiều worker. Thiết kế nào hỗ trợ?
A. Partition theo order ID rồi xử lý tuần tự từng phần.
B. Phân tán event ngẫu nhiên vào mọi worker đang rảnh.
C. Chỉ dựa vào timestamp HTTP request trên mỗi node.
D. Chỉ tăng số lượng consumer trên cùng một queue.
Đáp án đúng: A

Câu 23. Trong Spring MVC, cách nào thường khai báo endpoint nhận POST webhook JSON?
A. Dùng `@PostMapping` và nhận payload bằng `@RequestBody`.
B. Dùng `@EventListener` và đọc URL từ Spring Context.
C. Dùng `@GetMapping` và đọc body từ query parameter.
D. Dùng `@Scheduled` và gọi URL provider theo chu kỳ.
Đáp án đúng: A

Câu 24. Spring MVC cần kiểm tra HMAC dựa trên body gốc. Kiểu tham số nào thuận tiện?
A. Nhận `@PathVariable String` làm nội dung đã được ký.
B. Nhận `@RequestParam Map` thay mọi byte trong body.
C. Dùng `@RequestBody byte[]` để lấy byte body gốc.
D. Nhận `@ModelAttribute` rồi serialize lại thành JSON.
Đáp án đúng: C

Câu 25. Khi đã lưu bền vững webhook để xử lý bất đồng bộ, HTTP status nào có thể phù hợp?
A. HTTP 500 vì worker chưa xử lý xong dữ liệu.
B. HTTP 202 để báo request đã được nhận xử lý.
C. HTTP 409 vì event đã được tiếp nhận vào queue.
D. HTTP 404 vì xử lý nghiệp vụ chưa bắt đầu thực hiện.
Đáp án đúng: B

Câu 26. Webhook có chữ ký HMAC hợp lệ có tự ngăn được replay hoàn toàn không?
A. Không; vẫn cần chống replay và xử lý idempotent.
B. Có, vì HMAC bảo đảm event ID tự động được tăng.
C. Có, vì TLS luôn đổi nội dung chữ ký HMAC ở mọi lần.
D. Có, vì HMAC sẽ thay đổi mỗi khi một request được gửi.
Đáp án đúng: A

Câu 27. Test bảo mật nào giúp xác minh receiver từ chối payload bị sửa?
A. Sửa một byte body nhưng giữ nguyên chữ ký cũ.
B. Gửi cùng body và chữ ký qua hai connection khác.
C. Đổi tên header log mà không gửi request mới.
D. Gửi request có body nguyên vẹn với chữ ký hợp lệ.
Đáp án đúng: A

Câu 28. Nên lưu khóa bí mật HMAC phục vụ webhook Spring ở đâu?
A. Trong URL callback để sender có thể nhận biết khóa.
B. Trong source code để các instance dùng cùng một khóa.
C. Trong response 2xx trả về để client lưu lại khóa.
D. Trong secret manager hoặc cấu hình được bảo vệ.
Đáp án đúng: D

Câu 29. Để phát hiện sự cố webhook bị tồn đọng, nên thu thập bộ metric nào?
A. Tên class xử lý, số annotation và độ dài URL.
B. Theo dõi pending, retry, lỗi và độ trễ xử lý.
C. Số endpoint HTTP public và số dependency Maven.
D. Tổng số file Java, package và số lần chạy Gradle.
Đáp án đúng: B

Câu 30. Để tra cứu xuyên suốt một lần giao webhook và xử lý queue, nên làm gì?
A. Chỉ ghi IP provider và bỏ toàn bộ correlation ID.
B. Chỉ đặt tên queue cố định cho tất cả các lượt gửi.
C. Gán một request ID mới nhưng không truyền cho worker.
D. Giữ event ID hoặc trace context qua các bước xử lý.
Đáp án đúng: D

Câu 31. Provider bổ sung field tùy chọn vào payload webhook. Receiver nên thiết kế schema thế nào?
A. Yêu cầu đổi URL callback sau mỗi field bổ sung.
B. Cho phép field không biết và giữ field cũ ổn định.
C. Từ chối mọi field mới vì payload phải luôn cố định.
D. Luôn parse bằng danh sách field đóng không thể mở rộng.
Đáp án đúng: B

Câu 32. Nhiều replica Spring cùng nhận retry của một event. Điều gì giúp chống xử lý trùng toàn cụm?
A. Chỉ dựa vào HTTP keep-alive giữa sender và receiver.
B. Mỗi replica lưu một tập event ID trong RAM riêng.
C. Dùng kho idempotency chia sẻ có ràng buộc duy nhất.
D. Định danh event bằng số lần khởi động của từng replica.
Đáp án đúng: C
