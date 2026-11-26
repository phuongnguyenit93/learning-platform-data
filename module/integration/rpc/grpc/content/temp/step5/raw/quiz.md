Câu 1. Trong tệp .proto, khai báo nào mô tả các phương thức RPC do server cung cấp?
A. service khai báo danh sách phương thức RPC
B. message mô tả các trường của dữ liệu truyền
C. package xác định không gian tên của schema
D. enum định nghĩa các giá trị ký hiệu của kiểu
Đáp án đúng: A

Câu 2. Trong Protobuf, field number của một trường chủ yếu có vai trò nào?
A. Chọn bảng mã ký tự cho trường văn bản
B. Đặt giới hạn độ dài của giá trị chuỗi
C. Ấn định vị trí trường khi hiển thị giao diện
D. Nhận diện trường khi mã hóa dữ liệu nhị phân
Đáp án đúng: D

Câu 3. Thay đổi nào thường tương thích với client cũ khi mở rộng message Protobuf?
A. Dùng lại số tag cũ cho trường mang nghĩa mới
B. Thêm trường tùy chọn với số tag chưa từng dùng
C. Đổi số tag của một trường đang được dùng
D. Đổi kiểu của một trường từ int32 sang string
Đáp án đúng: B

Câu 4. Tại sao nên dùng reserved cho số tag của trường đã xóa trong .proto?
A. Để tránh tái sử dụng nhầm số tag đã bỏ
B. Để server tự xóa dữ liệu lịch sử của trường
C. Để giữ nguyên giá trị mặc định khi đọc
D. Để bắt client cũ nâng cấp trước mọi lời gọi
Đáp án đúng: A

Câu 5. Ý nghĩa của oneof trong khai báo message Protobuf là gì?
A. Tối đa một trường trong nhóm được đặt tại một lúc
B. Các trường trong nhóm tự động thành danh sách
C. Mỗi trường trong nhóm dùng một kết nối RPC
D. Mọi trường trong nhóm luôn phải được đặt cùng lúc
Đáp án đúng: A

Câu 6. Từ khóa repeated trong Protobuf cho phép điều gì?
A. Khai báo một trường có thể đổi kiểu
B. Khai báo một trường chứa nhiều phần tử
C. Khai báo một trường chỉ có một giá trị bắt buộc
D. Khai báo một trường có giá trị cố định
Đáp án đúng: B

Câu 7. Tại sao khai báo optional hữu ích cho trường scalar trong proto3?
A. Nó bắt buộc phía gửi cấp giá trị ngay cả khi bằng không
B. Nó làm trường có thể nhận nhiều phần tử
C. Nó cho phép tái dùng số tag khi đổi kiểu
D. Nó cho biết trường vắng hay mang giá trị mặc định
Đáp án đúng: D

Câu 8. Đặt java_multiple_files = true ảnh hưởng thế nào khi sinh mã Java?
A. Mọi message được gộp vào một lớp Java duy nhất
B. Các kiểu cấp cao được sinh thành tệp Java riêng
C. Mỗi trường của message sinh ra một tệp Java
D. Chỉ phần client stub được sinh ra bằng Java
Đáp án đúng: B

Câu 9. Khi dùng protoc và plugin grpc-java, phân công nào phù hợp nhất?
A. protoc sinh message Java, plugin sinh stub RPC
B. protoc chỉ kiểm tra schema, plugin sinh cả hai
C. protoc sinh cả stub lẫn message, plugin chỉ xác thực
D. protoc sinh stub RPC, plugin sinh message Java
Đáp án đúng: A

Câu 10. Đặc trưng của RPC kiểu unary trong gRPC là gì?
A. Một request nhận đúng một response
B. Một luồng request nhận một response
C. Hai phía cùng gửi luồng thông điệp
D. Một request nhận một luồng các response
Đáp án đúng: A

Câu 11. Với server-streaming RPC, hình thức trao đổi nào là đúng?
A. Một request và đúng một response đơn lẻ
B. Nhiều request theo luồng và một response
C. Một request và nhiều response theo luồng
D. Hai luồng request và response độc lập
Đáp án đúng: C

Câu 12. Trong client-streaming RPC, luồng trao đổi nào là đúng?
A. Hai phía cùng gửi nhiều message độc lập
B. Client gửi nhiều message rồi nhận một response
C. Client gửi một message và nhận một response
D. Server gửi nhiều response cho một request duy nhất
Đáp án đúng: B

Câu 13. Đặc trưng của bidirectional-streaming RPC là gì?
A. Mỗi phía chỉ được gửi một thông điệp
B. Client phải đóng luồng sau từng response
C. Hai phía có thể gửi thông điệp độc lập
D. Server đợi client kết thúc mới được gửi
Đáp án đúng: C

Câu 14. gRPC bảo đảm thứ tự thông điệp trong streaming theo phạm vi nào?
A. Theo timestamp được ghi trong payload
B. Giữa mọi RPC chạy trên cùng một channel
C. Trong từng luồng của một RPC cụ thể
D. Theo thứ tự mở kết nối TCP của client
Đáp án đúng: C

Câu 15. Với unary RPC trong gRPC Java, blocking stub thường hoạt động thế nào?
A. Gửi request rồi mở một server socket mới
B. Gửi request rồi đăng ký callback cho response sau đó
C. Gửi request và trả ngay một StreamObserver
D. Gửi request rồi chờ response trước khi trả về
Đáp án đúng: D

Câu 16. Trong gRPC Java, async stub thường dùng thành phần nào xử lý luồng message?
A. Iterator để kéo lần lượt mọi response
B. Runnable để nhận từng message qua callback
C. StreamObserver để xử lý các sự kiện luồng
D. Future được dùng cho tất cả các RPC có streaming
Đáp án đúng: C

Câu 17. Cách sử dụng ManagedChannel hợp lý trong ứng dụng Java là gì?
A. Tái dùng channel cho nhiều RPC rồi đóng khi dừng
B. Đóng channel ngay sau khi mở kết nối
C. Đặt channel trong payload của mỗi request
D. Tạo mới channel trước mỗi message của cùng một stream
Đáp án đúng: A

Câu 18. HTTP/2 giúp gRPC chạy nhiều RPC đồng thời trên một kết nối nhờ gì?
A. Chuyển mọi RPC về xử lý tuần tự trên mạng
B. Buộc từng RPC chiếm riêng một kết nối TCP
C. Gộp tất cả message thành một stream chung
D. Ghép nhiều stream độc lập trên một kết nối
Đáp án đúng: D

Câu 19. HTTP/2 flow control tác động trực tiếp đến điều gì?
A. Thứ tự định tuyến request tới các backend
B. Số lần retry do client được thực hiện
C. Lượng dữ liệu gửi theo cửa sổ phía nhận
D. Danh sách chứng chỉ TLS được tin cậy
Đáp án đúng: C

Câu 20. Trong gRPC Java streaming, onReady hữu ích nhất để làm gì?
A. Đổi trạng thái lỗi thành phản hồi thành công
B. Chuyển kênh plaintext sang kết nối TLS
C. Xác định thời điểm deadline được gia hạn
D. Điều tiết gửi khi luồng sẵn sàng ghi dữ liệu
Đáp án đúng: D

Câu 21. Deadline của một RPC trong gRPC dùng để giới hạn điều gì?
A. Thời hạn hiệu lực của chứng chỉ TLS
B. Khoảng thời gian cho phép RPC hoàn tất
C. Khoảng cách giữa hai lần health check
D. Tuổi thọ của channel dùng gọi dịch vụ
Đáp án đúng: B

Câu 22. Khi dịch vụ A gọi tiếp B trong cùng một yêu cầu, nên xử lý deadline ra sao?
A. Đặt deadline mới dài hơn cho mọi lần gọi
B. Tạo timeout riêng không liên quan lời gọi gốc
C. Chuyển phần thời gian còn lại xuống lời gọi B
D. Bỏ giới hạn deadline ở các lời gọi tiếp
Đáp án đúng: C

Câu 23. Tình huống nào phản ánh chính xác lỗi DEADLINE_EXCEEDED?
A. Backend tạm thời không thể nhận kết nối
B. Request thiếu một điều kiện nghiệp vụ
C. Client chủ động hủy RPC trước khi hoàn tất
D. RPC chưa hoàn tất khi thời hạn đã hết
Đáp án đúng: D

Câu 24. Tình huống nào thường phù hợp nhất với status UNAVAILABLE?
A. Xử lý chậm và vượt qua thời gian deadline
B. Request thiếu trường bắt buộc theo nghiệp vụ
C. Người dùng yêu cầu hủy lời gọi đang chạy
D. Không kết nối được đến dịch vụ tạm thời
Đáp án đúng: D

Câu 25. Trong giao thức gRPC trên HTTP/2, grpc-status thường nằm ở đâu?
A. Trong metadata của request từ client
B. Trong SETTINGS frame mở đầu kết nối
C. Trong trailing headers ở cuối phản hồi
D. Trong DATA frame đầu tiên của request từ client
Đáp án đúng: C

Câu 26. Nên truyền token xác thực giữa client và server gRPC bằng cơ chế nào?
A. Đưa token vào trường grpc-status cuối lời gọi
B. Gửi token qua phần SETTINGS của HTTP/2
C. Ghi token vào tùy chọn keepalive của channel
D. Gửi token trong metadata đầu của RPC
Đáp án đúng: D

Câu 27. Khi handler Java muốn trả lỗi gRPC chuẩn, thao tác nào phù hợp?
A. Gửi message rồi ghi lỗi vào GOAWAY
B. Gọi onError với Status thích hợp
C. Đánh dấu lỗi trong payload và trả OK
D. Trả về null và tự ngắt kết nối TCP
Đáp án đúng: B

Câu 28. Vai trò điển hình của interceptor trong gRPC là gì?
A. Xử lý nghiệp vụ bên trong service handler
B. Áp dụng logging, tracing hoặc xác thực
C. Phát sinh mã Java từ khai báo message và service
D. Phân giải địa chỉ backend của channel
Đáp án đúng: B

Câu 29. Khi retry RPC tạo giao dịch, biện pháp nào giúp tránh nhân đôi tác dụng?
A. Dùng idempotency key để loại thao tác lặp
B. Tạo một channel mới trước mỗi lần thực hiện retry
C. Tăng kích thước gói tin của mỗi lần thử
D. Đổi mọi lỗi ứng dụng thành UNAVAILABLE
Đáp án đúng: A

Câu 30. Lợi ích chính của exponential backoff kèm jitter khi retry là gì?
A. Giãn các lần thử và giảm retry đồng loạt
B. Giữ mọi khoảng đợi bằng nhau cho các lần
C. Gửi lại ngay lập tức sau mọi lần lỗi
D. Gửi nhiều RPC bản sao cùng một thời điểm
Đáp án đúng: A

Câu 31. Vì sao deadline cần được xét trong chính sách retry của gRPC?
A. Retry có thể tắt multiplexing của HTTP/2
B. Retry có thể đổi số tag của Protobuf
C. Mỗi lần thử làm TLS phải cấp chứng chỉ mới
D. Mỗi lần thử tiêu hao thời gian deadline còn lại
Đáp án đúng: D

Câu 32. Chính sách round_robin trong client-side load balancing có mục tiêu nào?
A. Nhân bản mọi RPC tới tất cả backend cùng lúc
B. Chọn backend dựa trên số tag của message
C. Chuyển toàn bộ RPC về backend đầu tiên trong danh sách
D. Phân phối RPC trên các backend đã được phân giải
Đáp án đúng: D

Câu 33. Name resolver trong hệ thống gRPC cung cấp thông tin nào cho channel?
A. Các lớp Java được sinh từ file proto
B. Các địa chỉ backend tương ứng tên đích
C. Danh sách trường message của mỗi RPC
D. Chứng chỉ của từng người dùng ứng dụng
Đáp án đúng: B

Câu 34. Khi dùng health checking cùng cân bằng tải, mục tiêu nào là đúng?
A. Tránh gửi RPC tới backend không phục vụ
B. Gửi lại RPC vừa thất bại cho backend
C. Khởi động lại backend sau mỗi lần lỗi
D. Tăng tải đến backend có độ trễ thấp
Đáp án đúng: A

Câu 35. Sử dụng TLS cho kết nối gRPC giải quyết nhu cầu chính nào?
A. Kiểm tra điều kiện nghiệp vụ trong payload
B. Mã hóa đường truyền và xác thực server
C. Tự động retry khi kết nối bị gián đoạn
D. Đảm bảo mọi thao tác RPC đều có tính idempotent
Đáp án đúng: B

Câu 36. Điểm khác biệt chính của mutual TLS (mTLS) là gì?
A. Chỉ client xác thực chứng chỉ phía server khi bắt tay
B. Payload Protobuf được nén ở cả hai phía
C. Cả client và server xác thực bằng chứng chỉ
D. Server chỉ dựa vào API key trong metadata
Đáp án đúng: C

Câu 37. Đối chiếu hostname của server khi xác minh TLS chủ yếu dựa vào mục nào?
A. Subject Alternative Name chứa DNS đích
B. Extended Key Usage quy định mục đích dùng khóa
C. Serial Number của chứng chỉ server
D. Common Name của tổ chức phát hành
Đáp án đúng: A

Câu 38. Cách bật kết nối TLS đúng phía gRPC Java client là gì?
A. Chỉ bật nén Protobuf trên kết nối TCP
B. Dùng ServerCredentials gắn trực tiếp vào stub
C. Tạo channel với TLS ChannelCredentials
D. Tạo channel plaintext kèm metadata OK
Đáp án đúng: C

Câu 39. Muốn kiểm thử client và handler gRPC Java mà không mở cổng TCP, cách nào hợp lý?
A. Chỉ giả lập stub rồi bỏ qua server
B. Chỉ xác nhận phần code Java được sinh ra từ proto
C. Dùng in-process server và channel để gọi
D. Chỉ kiểm tra serialize của các message
Đáp án đúng: C

Câu 40. Trong integration test, handler cố ý xử lý chậm; cách kiểm tra deadline nào đúng?
A. Chỉ so sánh lớp được sinh từ file proto
B. Đặt deadline ngắn và kiểm tra DEADLINE_EXCEEDED
C. Tắt deadline và đợi đến khi mọi lời gọi đều kết thúc
D. Đổi channel sang plaintext rồi so lỗi
Đáp án đúng: B
