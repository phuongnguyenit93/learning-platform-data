Câu 1. SSE thường phù hợp nhất với kiểu trao đổi dữ liệu nào?
A. Server đẩy sự kiện một chiều tới client qua HTTP
B. Client và server cùng gửi dữ liệu hai chiều liên tục
C. Client gửi nhiều request nối tiếp trên một RPC stream
D. Server nhận luồng message từ client rồi trả một response
Đáp án đúng: A

Câu 2. Trong trình duyệt, EventSource mặc định thiết lập kết nối SSE bằng phương thức nào?
A. Gửi HTTP POST kèm body đăng ký sự kiện
B. Gửi HTTP GET tới URL của nguồn sự kiện
C. Gửi HTTP PUT để tạo một stream phản hồi
D. Gửi HTTP PATCH để kích hoạt luồng dữ liệu
Đáp án đúng: B

Câu 3. Khi server trả về luồng SSE, Content-Type nào đúng?
A. application/json cho từng khối sự kiện liên tiếp
B. application/octet-stream cho từng sự kiện mới
C. application/x-ndjson cho dòng dữ liệu SSE
D. text/event-stream cho nội dung phát sự kiện
Đáp án đúng: D

Câu 4. SSE theo chuẩn HTML sử dụng cách mã hóa nội dung stream nào?
A. Dữ liệu event-stream được giải mã theo UTF-8
B. Mỗi client tự chọn bảng mã theo Accept-Charset
C. Payload mặc định được mã hóa theo UTF-16
D. Payload bắt buộc phải nén và mã hóa Base64
Đáp án đúng: A

Câu 5. Trong định dạng SSE, dòng bắt đầu bằng data: có tác dụng gì?
A. Chỉ định tên sự kiện để chọn event listener
B. Đặt định danh cho event sắp được phát đi
C. Đặt khoảng thời gian chờ giữa các lần reconnect
D. Cung cấp dữ liệu payload cho sự kiện hiện tại
Đáp án đúng: D

Câu 6. Điều kiện nào thường khiến một SSE event được phát đến listener?
A. Gặp dòng id: với giá trị khác định danh trước
B. Gặp dòng event: với tên sự kiện hợp lệ
C. Gặp một dòng data: mà chưa có ký tự xuống dòng
D. Gặp dòng trống kết thúc khối sự kiện hiện tại
Đáp án đúng: D

Câu 7. Nhiều dòng data: liên tiếp trong cùng một SSE event được diễn giải thế nào?
A. Chỉ lấy giá trị của dòng data: xuất hiện đầu tiên
B. Chỉ lấy giá trị của dòng data: xuất hiện cuối cùng
C. Ghép giá trị các dòng với ký tự xuống dòng ở giữa
D. Phát mỗi dòng data: thành một event riêng biệt
Đáp án đúng: C

Câu 8. Trường event: trong một khối SSE ảnh hưởng gì đến phía trình duyệt?
A. Đặt thời gian giữ kết nối HTTP đang được mở
B. Đặt định danh sự kiện để khôi phục khi kết nối lại
C. Đặt mã lỗi HTTP cho từng thông điệp được gửi
D. Đặt tên loại sự kiện để chọn listener tương ứng
Đáp án đúng: D

Câu 9. Trường id: trong SSE thường phục vụ mục đích gì?
A. Đặt lại khoảng chờ kết nối cho trình duyệt
B. Chọn tên callback xử lý một sự kiện tùy biến
C. Đặt ID của kết nối TCP đang phục vụ client
D. Lưu ID event cuối để hỗ trợ kết nối lại
Đáp án đúng: D

Câu 10. Trường retry: hợp lệ trong SSE định nghĩa giá trị nào?
A. Số lần tối đa server phát lại cùng một event
B. Số mili giây chờ trước một lần kết nối lại
C. Số giây dành cho mỗi lần xử lý một message
D. Số event cần đợi trước khi gửi dữ liệu mới
Đáp án đúng: B

Câu 11. Trong event-stream, dòng bắt đầu bằng dấu hai chấm đơn có ý nghĩa gì?
A. Dòng comment không phát thành sự kiện ứng dụng
B. Là trường báo lỗi để trình duyệt ngắt kết nối
C. Là cách phát một event có tên mặc định là colon
D. Là dòng thông báo đổi định danh event hiện tại
Đáp án đúng: A

Câu 12. Khi EventSource tự kết nối lại sau khi đã nhận id, thông tin nào thường được gửi?
A. Header If-None-Match mang ID của từng event
B. Header Content-Range mang chỉ số event đã lưu
C. Header Last-Event-ID mang định danh đã lưu
D. Header Authorization mang ID sự kiện cuối
Đáp án đúng: C

Câu 13. Khi mạng bị ngắt tạm thời, EventSource thường có hành vi nào?
A. Tự chuyển thành WebSocket để giữ phiên dữ liệu
B. Tự thử kết nối lại theo thời gian chờ retry
C. Tự tạo yêu cầu POST cho tất cả event đã mất
D. Tự bảo đảm replay dù server không lưu event
Đáp án đúng: B

Câu 14. Cách nào chủ động ngừng EventSource và chặn tự reconnect?
A. Gọi preventDefault() trên sự kiện message cuối
B. Đổi readyState thành CLOSED trực tiếp từ JavaScript
C. Gọi close() trên đối tượng EventSource đang mở
D. Gửi một event: close từ server mà không đóng stream
Đáp án đúng: C

Câu 15. Với SSE event không có tên tùy chỉnh, trình duyệt thường xử lý bằng cách nào?
A. Chuyển tới listener kiểu message mặc định
B. Chuyển sự kiện tới listener kiểu open mặc định
C. Chuyển sự kiện tới listener kiểu error mặc định
D. Chuyển sự kiện tới listener kiểu retry mặc định
Đáp án đúng: A

Câu 16. Để nhận sự kiện SSE có event: stock, cách nào phù hợp trong JavaScript?
A. Gán onmessage để nhận riêng những event có tên stock
B. Đăng ký addEventListener('open', handler) trên EventSource
C. Gán onerror để xử lý các event có tên stock
D. Đăng ký addEventListener('stock', handler)
Đáp án đúng: D

Câu 17. Trong EventSource, readyState bằng 1 biểu thị trạng thái nào?
A. OPEN, kết nối đang tiếp nhận sự kiện
B. CONNECTING, đang bắt đầu hoặc kết nối lại
C. CLOSED, đối tượng đã ngừng mở kết nối
D. RETRYING, đã dùng hết số lần kết nối lại
Đáp án đúng: A

Câu 18. Khi kết nối SSE gặp lỗi, event nào thường được thông báo cho JavaScript?
A. EventSource phát sự kiện retry cho listener
B. EventSource phát sự kiện error cho listener
C. EventSource phát sự kiện timeout cho listener
D. EventSource phát sự kiện disconnect cho listener
Đáp án đúng: B

Câu 19. Để khôi phục các event bị mất sau reconnect, server cần làm gì?
A. Chỉ gửi header Last-Event-ID trong response mới
B. Lưu event theo ID và phát tiếp từ vị trí cuối
C. Chỉ tăng timeout của kết nối HTTP ban đầu
D. Chỉ bật cache công khai cho mọi response SSE
Đáp án đúng: B

Câu 20. Vì sao trường id: tự nó chưa bảo đảm delivery exactly-once cho SSE?
A. EventSource xóa mọi định danh ngay khi có reconnect
B. Browser luôn xử lý một ID trước khi cho server gửi tiếp
C. Replay và chống trùng còn cần logic ở server/client
D. HTTP bảo đảm không có dữ liệu trùng khi nối lại
Đáp án đúng: C

Câu 21. Khi không có sự kiện nghiệp vụ trong thời gian dài, server có thể làm gì để giữ kết nối SSE?
A. Gửi request GET từ server về phía trình duyệt
B. Gửi dòng comment heartbeat và flush định kỳ
C. Đổi Content-Type của luồng sang application/json
D. Gửi mã HTTP 204 sau mỗi nhịp heartbeat
Đáp án đúng: B

Câu 22. Để client nhận event ngay thay vì đợi cuối response, server nên làm gì?
A. Flush response ngay sau khi ghi mỗi event
B. Gom dữ liệu đến lúc kết nối HTTP đóng hẳn
C. Đặt Content-Length cố định cho toàn bộ stream
D. Chỉ gửi event sau khi tích đủ một trang dữ liệu
Đáp án đúng: A

Câu 23. Khi proxy reverse tự gom nhiều chunk SSE, triệu chứng thường gặp là gì?
A. Client tự đổi phương thức request thành HTTP POST
B. Client thấy sự kiện trễ và đến thành từng đợt
C. Client nhận được mọi sự kiện trước khi server phát
D. Client tự thêm trường retry vào mỗi sự kiện
Đáp án đúng: B

Câu 24. Biện pháp nào thường dùng khi Nginx đang buffer response SSE?
A. Tăng kích thước response body trước mỗi lần flush
B. Đặt Content-Type thành application/octet-stream
C. Bật cache response động trên tất cả proxy trung gian
D. Tắt buffering cho stream trong cấu hình Nginx
Đáp án đúng: D

Câu 25. Khi idle timeout của proxy ngắn hơn thời gian không có event, nên xử lý thế nào?
A. Gửi heartbeat định kỳ và cấu hình timeout hợp lý
B. Giữ im luồng để trình duyệt tự chuyển sang HTTP POST
C. Tăng retry lên vài giờ để ngăn proxy đóng stream
D. Đổi mọi event thành phản hồi HTTP 304 Not Modified
Đáp án đúng: A

Câu 26. Trên HTTP/1.1, mở nhiều EventSource cùng origin có thể gặp vấn đề gì?
A. Mọi EventSource tự động chia sẻ một response chung
B. Chạm giới hạn kết nối đồng thời của trình duyệt
C. Trình duyệt bắt buộc đóng tất cả lời gọi GET khác
D. Mỗi EventSource phải dùng một cổng TCP công khai
Đáp án đúng: B

Câu 27. HTTP/2 có thể cải thiện nhiều kết nối SSE nhờ cơ chế nào?
A. Thay các dòng data: bằng frame WebSocket nhị phân
B. Buộc client nhận mọi event theo cùng một thứ tự
C. Đa kênh nhiều stream HTTP trên một kết nối TCP
D. Loại bỏ toàn bộ giới hạn timeout ở tầng proxy
Đáp án đúng: C

Câu 28. API EventSource gốc của trình duyệt có giới hạn nào với request header?
A. Không cung cấp tùy chọn đặt header tùy ý trực tiếp
B. Luôn cho phép gắn Authorization khi tạo EventSource
C. Tự động gửi bearer token nằm trong localStorage
D. Cho phép mọi header CORS mà không cần preflight
Đáp án đúng: A

Câu 29. Khi dùng cookie với SSE cross-origin, cấu hình trình duyệt nào liên quan?
A. Khởi tạo EventSource với mode: 'no-cors'
B. Khởi tạo EventSource với headers: {Cookie: ...}
C. Khởi tạo EventSource với withCredentials: true
D. Khởi tạo EventSource với method: 'POST'
Đáp án đúng: C

Câu 30. Với SSE cross-origin có credentials, server cần trả header nào đúng?
A. Wildcard origin cùng Access-Control-Allow-Credentials: true
B. Access-Control-Allow-Origin: * rồi bỏ xác minh credential
C. Origin cụ thể và Access-Control-Allow-Credentials: true
D. Chỉ Access-Control-Allow-Headers mà không cần origin
Đáp án đúng: C

Câu 31. Vì sao không nên đặt access token dài hạn trong query của URL SSE?
A. Query string bị trình duyệt tự động đổi sang HTTP body
B. EventSource không hỗ trợ bất kỳ query parameter nào
C. Proxy bắt buộc xóa tất cả query parameter trước khi gọi
D. URL có thể lọt vào log, lịch sử hoặc hệ thống giám sát
Đáp án đúng: D

Câu 32. Khi client đăng ký stream cho dữ liệu của một tài khoản, server cần kiểm tra điều gì?
A. Chỉ tên sự kiện đã khai báo trong JavaScript client
B. Chỉ kích thước dòng data: cuối cùng client đã nhận
C. Chỉ phiên bản HTTP dùng để mở kết nối stream
D. Xác thực và kiểm tra quyền truy cập dữ liệu của tài khoản
Đáp án đúng: D

Câu 33. Trong Spring MVC, kiểu nào thường đại diện một phản hồi SSE kéo dài?
A. ResponseEntity<String> để trả toàn bộ body cùng lúc
B. DeferredResult<Integer> để giữ một mã trạng thái
C. SseEmitter để phát event qua HTTP bất đồng bộ
D. HttpSession để ghi các event mới vào cookie
Đáp án đúng: C

Câu 34. Với Spring MVC SseEmitter, cách nào gửi event có id và tên riêng?
A. Dùng complete() rồi trả response body cho từng event
B. Gọi send(SseEmitter.event().id(...).name(...).data(...))
C. Dùng setStatus(...) để ghi id vào HTTP status code
D. Dùng onCompletion(...) để phát payload ra event-stream
Đáp án đúng: B

Câu 35. Callback onCompletion của SseEmitter nên thường được dùng để làm gì?
A. Tự thêm id: vào mọi event còn trong hàng đợi
B. Tự đổi phương thức HTTP request từ GET sang POST
C. Dọn tài nguyên đăng ký sau khi stream kết thúc
D. Gửi lại tất cả sự kiện đã phát đến client
Đáp án đúng: C

Câu 36. Nếu SseEmitter hết thời gian chờ, xử lý nào phù hợp phía server?
A. Theo dõi onTimeout để dọn tài nguyên của stream
B. Chỉ tăng kích thước buffer mà không ghi nhận timeout
C. Gọi send() vô hạn để giữ connection dù đã lỗi
D. Đợi client gửi event kết thúc qua cùng response SSE
Đáp án đúng: A

Câu 37. Với Spring WebFlux, kiểu trả về nào phù hợp cho endpoint SSE?
A. Mono<List<T>> để giữ đến khi đủ mọi sự kiện
B. Flux<ServerSentEvent<T>> để phát các event dần
C. ResponseEntity<byte[]> để chứa toàn bộ stream
D. CompletableFuture<T> để trả một kết quả cuối
Đáp án đúng: B

Câu 38. Trong Spring WebFlux, ServerSentEvent.builder hỗ trợ đặt gì?
A. Số cổng TCP cố định cho mọi EventSource đang mở
B. Dữ liệu cookie xác thực cho mọi trình duyệt
C. Các trường id, event và data của một SSE event
D. Chính sách cache của load balancer cho mỗi request
Đáp án đúng: C

Câu 39. Backpressure giữa browser EventSource và server SSE cần hiểu thế nào?
A. EventSource luôn gửi request(1) trước mỗi event
B. Giao thức SSE có frame ACK riêng cho mỗi message
C. Server luôn nhận tín hiệu tốc độ xử lý JavaScript
D. EventSource không có tín hiệu yêu cầu mỗi event
Đáp án đúng: D

Câu 40. Dùng WebFlux với publisher phản ứng có lợi gì cho quản lý tải?
A. Điều tiết nguồn phát trong pipeline có backpressure
B. Tự bảo đảm trình duyệt đọc kịp dù mạng đã chậm
C. Tự lưu vĩnh viễn event dù không có storage bên ngoài
D. Tự chuyển SSE thành kết nối song công WebSocket
Đáp án đúng: A

Câu 41. Khi một client SSE đọc chậm kéo dài, server nên ưu tiên biện pháp nào?
A. Tăng queue vô hạn để không bao giờ mất sự kiện
B. Giới hạn queue mỗi client và ngắt khi quá tải
C. Gửi event càng nhanh càng tốt bất kể buffer đã đầy
D. Bỏ các kiểm tra quyền trên kết nối đang chậm
Đáp án đúng: B

Câu 42. Khi hàng nghìn client mất mạng rồi cùng reconnect, điều gì giúp giảm quá tải?
A. Buộc mọi client reconnect đồng loạt cùng thời điểm
B. Sao chép mọi event sang từng server bằng thread riêng
C. Vô hiệu hóa giới hạn kết nối ở tất cả backend
D. Giới hạn tải và phân tán các lần reconnect
Đáp án đúng: D

Câu 43. Trong triển khai SSE đa instance, broker pub/sub thường đóng vai trò nào?
A. Lưu cookie của tất cả trình duyệt trong HTTP response
B. Thay thế xác thực cho mọi client của từng instance
C. Phân phối event tới các instance đang giữ client
D. Tự tăng số stream HTTP/2 mà browser hỗ trợ
Đáp án đúng: C

Câu 44. Tại sao chỉ sử dụng sticky session thường chưa đủ cho khôi phục SSE?
A. Sticky session luôn đảm bảo mất dữ liệu bằng không
B. Sticky session tự ghi Last-Event-ID vào database
C. Cần nguồn replay chung nếu client đổi sang node khác
D. Sticky session thay cơ chế xác nhận ACK của SSE
Đáp án đúng: C

Câu 45. Khi dùng load balancer cho SSE, cấu hình nào cần chú ý?
A. Timeout và buffering phù hợp cho response dài hạn
B. Chỉ phân phối request khi response đã kết thúc
C. Đặt cache công khai trên mọi stream theo user
D. Chặn tất cả request GET để tránh chiếm kết nối
Đáp án đúng: A

Câu 46. Integration test cho SSE reconnect nên xác minh kịch bản nào?
A. Ngắt stream rồi kiểm tra replay với Last-Event-ID
B. Chỉ kiểm tra trả HTTP 200 rồi đóng ngay response
C. Chỉ kiểm tra đúng Content-Type mà bỏ qua nội dung
D. Chỉ kiểm tra startup log trước khi mở EventSource
Đáp án đúng: A

Câu 47. Để phát hiện rò rỉ tài nguyên SSE khi client rời trang, test nên kiểm tra gì?
A. Số event phát ra luôn bằng số lần client mở trang
B. Mọi event cũ phải nằm mãi trong bộ nhớ của instance
C. Mọi client luôn giữ một socket đến khi server restart
D. Subscription và tài nguyên được dọn sau disconnect
Đáp án đúng: D

Câu 48. Khi server muốn EventSource ngừng tự reconnect, HTTP status nào phù hợp?
A. 200 OK để báo client ngừng kết nối lại
B. 204 No Content để báo client ngừng kết nối lại
C. 202 Accepted để báo client ngừng kết nối lại
D. 304 Not Modified để báo client ngừng kết nối lại
Đáp án đúng: B
