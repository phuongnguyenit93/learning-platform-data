Câu 1. Khả năng nào của RSocket phù hợp với trao đổi bất đồng bộ qua một kết nối lâu dài?
A. Mọi phản hồi đều phải là một HTTP response JSON.
B. Nhiều luồng trao đổi hai chiều chia sẻ một kết nối.
C. Mọi request đều phải đi qua một message broker.
D. Nhiều request phải mở một kết nối HTTP riêng.
Đáp án đúng: B

Câu 2. RSocket có thể truyền các frame của giao thức qua cặp transport nào?
A. Qua HTTP REST truyền thống hoặc qua gRPC unary.
B. Qua AMQP queue hoặc qua MQTT topic của broker.
C. Qua UDP datagram hoặc qua HTTP long polling.
D. Qua kết nối TCP hoặc WebSocket giữa hai phía.
Đáp án đúng: D

Câu 3. Mô hình RSocket `request-response` tương ứng với kiểu trao đổi nào?
A. Hai phía cùng gửi các luồng dữ liệu độc lập.
B. Một yêu cầu nhận một kết quả hoặc tín hiệu lỗi.
C. Một yêu cầu nhận nhiều phần tử trên luồng trả về.
D. Một yêu cầu được gửi mà không cần kết quả trả về.
Đáp án đúng: B

Câu 4. Trong RSocket, `fire-and-forget` diễn tả yêu cầu nào?
A. Bên gửi luôn chờ một payload phản hồi từ server.
B. Bên gửi không yêu cầu phản hồi ứng dụng cho request.
C. Bên gửi luôn nhận luồng nhiều payload từ server.
D. Bên gửi mở đồng thời luồng input và output.
Đáp án đúng: B

Câu 5. Với RSocket `request-stream`, kết quả trả về có dạng nào?
A. Một request khởi tạo luồng payload từ client.
B. Một request nhận đúng một payload kết quả.
C. Không có response payload theo loại interaction.
D. Một request có thể nhận nhiều payload từ peer.
Đáp án đúng: D

Câu 6. Điểm khác biệt chính của RSocket `request-channel` so với `request-stream` là gì?
A. Channel hỗ trợ luồng dữ liệu ở cả hai chiều.
B. Chỉ channel hỗ trợ truyền qua kết nối TCP.
C. Stream bắt buộc gửi dữ liệu qua một queue.
D. Channel chỉ phản hồi đúng một message duy nhất.
Đáp án đúng: A

Câu 7. RSocket phân biệt nhiều interaction chạy chung một kết nối bằng thông tin nào?
A. Tên queue được ánh xạ cho từng interaction.
B. Địa chỉ IP nguồn được đổi ở mỗi lần gửi.
C. HTTP path được gắn vào từng response frame.
D. Stream ID trong frame của các luồng tương ứng.
Đáp án đúng: D

Câu 8. Trong RSocket, frame `SETUP` dùng để truyền thông tin nào khi khởi tạo kết nối?
A. Số lần retry của mọi request trong ứng dụng.
B. Các MIME type cho dữ liệu và metadata payload.
C. Toàn bộ message sẽ truyền trong suốt phiên.
D. Danh sách tất cả route mà server sẽ thực thi.
Đáp án đúng: B

Câu 9. Trong một luồng trả dữ liệu RSocket, `REQUEST_N` giúp thực hiện điều gì?
A. Thông báo số phần tử bổ sung mà bên nhận sẵn sàng nhận.
B. Yêu cầu peer tạo lại kết nối TCP vừa bị lỗi.
C. Chỉ định số lần gửi lại các payload đã bị lỗi.
D. Yêu cầu peer hủy mọi stream thuộc một connection.
Đáp án đúng: A

Câu 10. Khi client không còn cần dữ liệu của stream RSocket, hành động giao thức nào thích hợp?
A. Gửi `RESUME` để bỏ qua mọi payload còn lại.
B. Gửi `SETUP` mới trên cùng stream đang chạy.
C. Gửi `REQUEST_N` với giá trị âm để thoát.
D. Gửi tín hiệu `CANCEL` cho stream cần dừng.
Đáp án đúng: D

Câu 11. Frame RSocket `KEEPALIVE` thường được dùng nhằm mục đích gì?
A. Xác thực quyền truy cập của từng route đang chạy.
B. Thăm dò khả năng sống của kết nối với peer.
C. Giới hạn số phần tử gửi trong request-channel.
D. Cam kết tất cả message đã được xử lý nghiệp vụ.
Đáp án đúng: B

Câu 12. Vai trò của metadata so với data trong một RSocket payload là gì?
A. Metadata mang ngữ cảnh; data mang nội dung ứng dụng.
B. Metadata lưu trạng thái TCP; data lưu thông tin stream ID.
C. Metadata luôn chứa body, còn data là transport header.
D. Metadata chỉ có ở frame lỗi; data chỉ có ở frame SETUP.
Đáp án đúng: A

Câu 13. Vì sao ứng dụng RSocket có thể dùng composite metadata?
A. Để chuyển message từ TCP sang giao thức AMQP.
B. Để đóng gói nhiều kết nối TCP vào một kết nối mới.
C. Để gắn nhiều mục metadata có MIME type riêng biệt.
D. Để thay mọi luồng data bằng metadata mặc định.
Đáp án đúng: C

Câu 14. Khi Spring RSocket sử dụng route, thông tin định tuyến thường nằm ở đâu?
A. Trong tên host được cấu hình của server.
B. Trong TLS certificate của kết nối client.
C. Trong HTTP status code của gói dữ liệu RSocket.
D. Trong routing metadata đi kèm request payload.
Đáp án đúng: D

Câu 15. Trong Reactor, `Mono<T>` biểu diễn kết quả có đặc điểm nào?
A. Luôn có nhiều phần tử đến liên tục theo thời gian.
B. Bắt buộc chứa đúng một phần tử không bao giờ lỗi.
C. Có tối đa một phần tử hoặc tín hiệu kết thúc.
D. Chỉ biểu diễn stream hai chiều qua WebSocket.
Đáp án đúng: C

Câu 16. Trong Reactor, `Flux<T>` phù hợp để mô hình hóa điều gì?
A. Kết quả đồng bộ chỉ có một giá trị Java.
B. Thông tin metadata không chứa payload nào.
C. Luồng có thể phát nhiều phần tử theo thời gian.
D. Một phần tử duy nhất rồi kết thúc request.
Đáp án đúng: C

Câu 17. Annotation nào trong Spring RSocket thường ánh xạ route đến handler?
A. `@MessageMapping` để gắn route với phương thức.
B. `@Scheduled` để nhận payload từ RSocket peer.
C. `@GetMapping` để ánh xạ RSocket stream ID.
D. `@Entity` để ánh xạ channel vào database.
Đáp án đúng: A

Câu 18. Để chọn route đến handler RSocket khi dùng Spring, client thường gọi gì?
A. `RSocketRequester.path("orders.get")`.
B. `RSocketRequester.headers("orders.get")`.
C. `RSocketRequester.route("orders.get")`.
D. `RSocketRequester.queue("orders.get")`.
Đáp án đúng: C

Câu 19. Khi một Spring RSocket route trả về một giá trị đơn, client chọn phương thức nào?
A. Chọn `.send()` để nhận object trả về từ server.
B. Chọn `.metadata()` để nhận object dữ liệu.
C. Chọn `.retrieveFlux(...)` cho một kết quả đơn.
D. Chọn `.retrieveMono(...)` cho kết quả một phần tử.
Đáp án đúng: D

Câu 20. Client Spring RSocket cần nhận nhiều item từ route `prices.stream`. Cách nào phù hợp?
A. Dùng `.send()` để lấy danh sách các item trả về.
B. Dùng `.retrieveMono()` rồi yêu cầu stream liên tục.
C. Dùng `.retrieveFlux(...)` để nhận luồng các item.
D. Dùng `.connectTcp()` sau mỗi item được gửi.
Đáp án đúng: C

Câu 21. Với Spring `RSocketRequester`, thao tác nào hợp với fire-and-forget?
A. Gọi `.route(...)` mà không phát dữ liệu nào.
B. Gọi `.send()` để gửi request không lấy response.
C. Gọi `.retrieveFlux(...)` để chờ phản hồi liên tục.
D. Gọi `.retrieveMono(...)` để chờ một phản hồi.
Đáp án đúng: B

Câu 22. Khi client muốn gửi một Flux và nhận một Flux trong RSocket, interaction nào phù hợp?
A. `fire-and-forget` không có phản hồi ứng dụng.
B. `request-channel` với luồng vào và luồng ra.
C. `request-response` với một payload request duy nhất.
D. `request-stream` chỉ có một payload đầu vào.
Đáp án đúng: B

Câu 23. Để mở kết nối RSocket TCP từ client Spring, `RSocketRequester.Builder` thường có lựa chọn nào?
A. Gọi `.tcp(host, port)` để kết nối tới server.
B. Gọi `.retrieveMono()` để chọn địa chỉ TCP.
C. Gọi `.route(host, port)` để thiết lập kết nối.
D. Gọi `.websocket(uri)` để chọn kết nối TCP.
Đáp án đúng: A

Câu 24. Trong RSocket streaming, backpressure giải quyết vấn đề nào?
A. Thay thế hoàn toàn nhu cầu có connection timeout.
B. Bắt client gửi một request HTTP cho mỗi item.
C. Bắt server gửi mọi payload trước khi client nhận.
D. Giúp bên nhận điều tiết lượng item được cấp.
Đáp án đúng: D

Câu 25. Khi upstream nhanh hơn downstream, cách áp dụng backpressure nào phù hợp?
A. Giới hạn nhu cầu và dùng bộ đệm có kiểm soát.
B. Buffer không giới hạn để giữ toàn bộ payload.
C. Cho phép producer gửi liên tục không điều tiết.
D. Bỏ mọi tín hiệu request(n) từ downstream.
Đáp án đúng: A

Câu 26. Khi RSocket connection rơi trong lúc xử lý giao dịch, ứng dụng nên lưu ý điều gì?
A. Ứng dụng luôn có thể coi yêu cầu chưa được nhận.
B. RSocket tự động rollback cả giao dịch database.
C. Không thể suy ra chắc chắn tác vụ đã hoàn tất hay chưa.
D. Broker luôn xóa các request chưa có response.
Đáp án đúng: C

Câu 27. Nếu dùng bearer token cho RSocket, cách đưa thông tin xác thực nào phù hợp?
A. Gửi token qua metadata xác thực được định nghĩa.
B. Dùng HTTP status code thay cho token truy cập.
C. Chèn token vào stream ID của từng message.
D. Đặt token vào một TCP port mới cho mỗi request.
Đáp án đúng: A

Câu 28. Muốn bảo vệ dữ liệu RSocket trên đường truyền TCP qua mạng, nên áp dụng gì?
A. Sử dụng TLS và xác thực danh tính peer phù hợp.
B. Chỉ thay tên route để che đường dẫn server.
C. Dùng session ID thay cho cơ chế mã hóa kênh.
D. Chuyển toàn bộ payload thành base64 trong client.
Đáp án đúng: A

Câu 29. Một route RSocket trả về dữ liệu nhạy cảm. Server nên đặt kiểm tra quyền tại đâu?
A. Chỉ dựa vào tên route không công khai cho client.
B. Cho phép truy cập nếu kết nối được giữ đủ lâu.
C. Thực thi kiểm tra quyền trên route hoặc handler.
D. Kiểm tra quyền một lần ở trình duyệt phía client.
Đáp án đúng: C

Câu 30. Khi bật tính năng RSocket resume, nhận định nào đúng về khả năng phục hồi?
A. Resume luôn hoạt động dù hai peer không hỗ trợ.
B. Resume cần hỗ trợ thương lượng và dữ liệu đệm phù hợp.
C. Resume thay thế được timeout và retry ở ứng dụng.
D. Resume bảo đảm side effect chỉ chạy một lần tuyệt đối.
Đáp án đúng: B

Câu 31. Để giám sát RSocket realtime, bộ thông tin nào hữu ích nhất?
A. Tên source file, số dependency và tổng số class.
B. Chỉ số endpoint REST và thời gian build ứng dụng.
C. Độ trễ route, số lỗi, hủy stream và tái kết nối.
D. Chỉ địa chỉ IP của broker và tên bảng database.
Đáp án đúng: C

Câu 32. Khi kiểm thử Flux trả kết quả RSocket, cách nào xác minh nhu cầu và hủy luồng?
A. Chỉ thử kết nối TCP mà bỏ qua tín hiệu stream.
B. Kiểm tra số route bằng một lần gọi `.toString()`.
C. Đọc mọi giá trị trước rồi chỉ xác nhận số lượng.
D. Dùng StepVerifier yêu cầu item rồi thử cancel.
Đáp án đúng: D
