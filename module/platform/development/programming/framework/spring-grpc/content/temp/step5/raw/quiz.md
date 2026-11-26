Câu 1. Trong kiến trúc gRPC Java thông dụng, RPC thường chạy trên giao thức và định dạng nào?
A. HTTP/1.1 kết hợp XML làm định dạng bắt buộc.
B. HTTP/2 kết hợp Protocol Buffers để mã hóa message.
C. WebSocket kết hợp Java Serialization làm định dạng chuẩn.
D. AMQP kết hợp JSON Schema làm hợp đồng RPC mặc định.
Đáp án đúng: B

Câu 2. Trong file `.proto` dùng cú pháp Proto3, khai báo nào đặt phiên bản cú pháp?
A. Khai báo `syntax = "proto3";` trong file `.proto`.
B. Viết `version = "protobuf3";` ở đầu message.
C. Viết `language = "java";` trên từng service.
D. Viết `proto = 3;` bên trong mọi method RPC.
Đáp án đúng: A

Câu 3. Khi đổi tên một field Protobuf nhưng giữ ý nghĩa và tag number, điều nào quan trọng cho wire format?
A. Field tag number định danh giá trị trên wire.
B. Tên field Java là định danh mã hóa trên wire.
C. Namespace Java là thành phần bắt buộc của wire tag.
D. Thứ tự field trong file quyết định việc giải mã.
Đáp án đúng: A

Câu 4. Đã xóa field tag 4 khỏi message `.proto`; biện pháp nào tránh dùng lại tag sai?
A. Đổi toàn bộ tag hiện tại thành chuỗi bắt đầu từ 1.
B. Đặt `deprecated = true` trên service chứa message.
C. Khai báo `reserved 4;` trong message tương ứng.
D. Giữ tag 4 cho field mới với tên Java khác.
Đáp án đúng: C

Câu 5. Trong Proto3, `oneof` phù hợp để mô tả yêu cầu có nhiều biến thể loại trừ nhau như thế nào?
A. Chuyển các trường trong nhóm thành metadata của RPC.
B. Nhóm có tối đa một field được đặt tại một thời điểm.
C. Tạo danh sách chứa đồng thời mọi trường trong nhóm.
D. Yêu cầu client luôn cung cấp đủ các trường của nhóm.
Đáp án đúng: B

Câu 6. Field Protobuf `repeated string tags = 3;` biểu diễn dữ liệu nào?
A. Một chuỗi chỉ được phép xuất hiện đúng ba lần.
B. Một danh sách có thể chứa nhiều giá trị chuỗi.
C. Một chuỗi sẽ bị lặp lại ba lần khi sinh Java.
D. Một map từ số nguyên sang giá trị chuỗi duy nhất.
Đáp án đúng: B

Câu 7. Cần biết client có thực sự gửi field scalar `priority` trong Proto3; thiết kế nào phù hợp?
A. Dùng `repeated int32 priority = 2;` để đo presence.
B. Dùng `int32 priority = 2;` và coi số 0 là đã gửi.
C. Dùng `optional int32 priority = 2;` để biết presence.
D. Đổi tên field thành `hasPriority` để có hàm presence.
Đáp án đúng: C

Câu 8. Muốn từ `.proto` sinh message Java và client/server stub gRPC, cần các thành phần nào?
A. Dùng Spring MVC annotation processor thay plugin gRPC.
B. Dùng `protoc` cùng Java generator và plugin gRPC Java.
C. Dùng Jackson schema generator để tạo Java gRPC stub.
D. Dùng Java compiler trực tiếp để biên dịch file `.proto`.
Đáp án đúng: B

Câu 9. Khai báo nào mô tả unary RPC hợp lệ trong service Protobuf?
A. `service GetBook (BookRequest) returns BookReply;`.
B. `rpc GetBook (stream BookRequest) returns (stream BookReply);`.
C. `method GetBook: BookRequest -> BookReply;`.
D. `rpc GetBook (BookRequest) returns (BookReply);`.
Đáp án đúng: D

Câu 10. Một unary RPC có dạng trao đổi nào khi hoàn thành thành công?
A. Luồng request message và một response message.
B. Một request message và luồng response liên tục.
C. Một request message và một response message.
D. Luồng request message và luồng response message.
Đáp án đúng: C

Câu 11. Khi server gửi nhiều `BookReply` cho một `BookRequest`, method `.proto` nào phù hợp?
A. `rpc ListBooks (BookRequest) returns (BookReply);`.
B. `rpc ListBooks (stream BookRequest) returns (stream BookReply);`.
C. `rpc ListBooks (stream BookRequest) returns (BookReply);`.
D. `rpc ListBooks (BookRequest) returns (stream BookReply);`.
Đáp án đúng: D

Câu 12. RPC tải nhiều `Chunk` từ client và trả một `UploadSummary` phù hợp với khai báo nào?
A. `rpc Upload (Chunk) returns (UploadSummary);`.
B. `rpc Upload (stream Chunk) returns (UploadSummary);`.
C. `rpc Upload (Chunk) returns (stream UploadSummary);`.
D. `rpc Upload (stream Chunk) returns (stream UploadSummary);`.
Đáp án đúng: B

Câu 13. Ứng dụng chat hai chiều cần client/server phát nhiều message độc lập; khai báo nào đúng?
A. `rpc Chat (ClientMsg) returns (ServerMsg);`.
B. `rpc Chat (stream ClientMsg) returns (ServerMsg);`.
C. `rpc Chat (ClientMsg) returns (stream ServerMsg);`.
D. `rpc Chat (stream ClientMsg) returns (stream ServerMsg);`.
Đáp án đúng: D

Câu 14. Trong Java gRPC server, lớp implementation thường kế thừa thành phần nào từ mã được sinh?
A. Generated `BookServiceGrpc.BookServiceImplBase` để override RPC.
B. Generated `BookServiceGrpc.BookServiceStub` để nhận incoming RPC.
C. Generated `BookServiceGrpc.BookServiceBlockingStub` để override RPC.
D. Generated `BookServiceGrpc.BookServiceFutureStub` để bind RPC.
Đáp án đúng: A

Câu 15. Trong dự án Spring gRPC đã cấu hình server, tích hợp implementation server nên làm gì?
A. Tạo một `@RestController` riêng cho từng Protobuf message.
B. Đưa blocking client stub vào registry server như service.
C. Khai báo `RowMapper` để bind Protobuf schema thành service.
D. Đăng ký bean `BindableService` với Spring context.
Đáp án đúng: D

Câu 16. Với unary RPC thành công, cách kết thúc `responseObserver` trong server handler nào phù hợp?
A. Gọi `onNext(reply)` rồi `onError(null)` để complete.
B. Gọi `onCompleted()` trước rồi mới `onNext(reply)`.
C. Gọi `onError(null)` rồi `onNext(reply)` khi không lỗi.
D. Gọi `onNext(reply)` rồi `onCompleted()` cho response.
Đáp án đúng: D

Câu 17. Khi server gặp request không hợp lệ, cách trả gRPC status nào đúng?
A. Gọi `onError(Status.INVALID_ARGUMENT.asRuntimeException())`.
B. Gọi `onError(Status.OK.asRuntimeException())` cho lỗi input.
C. Gọi `onNext(null)` để gRPC tự suy luận lỗi validation.
D. Gọi `onCompleted()` rồi ghi HTTP status 400 trong body.
Đáp án đúng: A

Câu 18. Client Java cần gọi unary RPC đồng bộ để nhận `BookReply`, cách nào phù hợp?
A. Dùng generated server `ImplBase` rồi gọi trực tiếp RPC.
B. Dùng generated async stub và gọi `.block()` của Reactor.
C. Gọi unary RPC bằng generated blocking stub của Java.
D. Dùng `MBeanServer` lấy client stub theo service name.
Đáp án đúng: C

Câu 19. Khi nhiều RPC cùng dùng một backend, cách quản lý `ManagedChannel` nào hợp lý?
A. Đóng channel ngay trước khi gọi RPC để giải phóng socket.
B. Chia sẻ một `StreamObserver` request cho mọi unary RPC.
C. Tạo channel mỗi RPC rồi không shutdown.
D. Tái sử dụng channel, đóng khi ứng dụng ngừng.
Đáp án đúng: D

Câu 20. Để giới hạn thời gian chờ riêng cho lời gọi RPC trên client stub, cách nào phù hợp?
A. Dùng `stub.withCompression(timeout)` để giới hạn thời gian.
B. Dùng `Metadata.Key.of(timeout)` để đặt thời gian chờ.
C. Dùng `stub.withDeadlineAfter(timeout, unit)` cho lời gọi.
D. Dùng `channel.shutdownNow()` ngay trước khi gọi RPC.
Đáp án đúng: C

Câu 21. Khi RPC vượt deadline phía client, gRPC thường báo status nào?
A. `DEADLINE_EXCEEDED` khi hết thời hạn của RPC.
B. `ALREADY_EXISTS` khi resource đã tồn tại.
C. `FAILED_PRECONDITION` khi server chặn thao tác.
D. `INVALID_ARGUMENT` khi một message không hợp lệ.
Đáp án đúng: A

Câu 22. RPC bị hủy ở client trong lúc server vẫn xử lý; logic server cần quan tâm điều gì?
A. Gửi thêm response trước khi thực hiện kiểm tra cancellation.
B. Kiểm tra cancellation của gRPC Context để dừng việc.
C. Giả định server luôn chạy xong vì client không thể hủy RPC.
D. Đổi cancellation thành status OK để client nhận response.
Đáp án đúng: B

Câu 23. Backend gRPC bị ngắt kết nối tạm thời; status nào thường phản ánh lỗi khả dụng dịch vụ?
A. `OUT_OF_RANGE` cho tham số vượt giới hạn hợp lệ.
B. `UNAVAILABLE` khi mất kết nối hoặc backend gián đoạn.
C. `NOT_FOUND` cho thiếu đối tượng theo identifier.
D. `INVALID_ARGUMENT` cho lỗi cú pháp nội dung request.
Đáp án đúng: B

Câu 24. Server xác thực được danh tính nhưng client thiếu quyền gọi method; status nào thích hợp?
A. `UNAUTHENTICATED` cho client đã đăng nhập hợp lệ.
B. `CANCELLED` cho server từ chối quyền theo ACL.
C. `DEADLINE_EXCEEDED` cho client thiếu role truy cập.
D. `PERMISSION_DENIED` cho yêu cầu không đủ quyền.
Đáp án đúng: D

Câu 25. Client muốn gửi trace ID dạng chuỗi trong gRPC metadata; API nào phù hợp?
A. Tạo `Metadata.Key` dùng `ASCII_STRING_MARSHALLER`.
B. Dùng `Status` description làm metadata request cố định.
C. Tạo `Metadata.Key` với `BINARY_BYTE_MARSHALLER` cho ASCII key.
D. Đưa trace ID vào field number 0 của Protobuf message.
Đáp án đúng: A

Câu 26. Muốn gửi metadata dạng bytes qua gRPC, tên key phải tuân theo quy tắc nào?
A. Key binary metadata có hậu tố `-bin` theo quy ước.
B. Key binary metadata bắt đầu bằng tiền tố `grpc-ascii-`.
C. Key binary metadata không được chứa dấu nối trong tên.
D. Key binary metadata phải chứa tên đầy đủ Java service.
Đáp án đúng: A

Câu 27. Cần đọc credential từ metadata trước khi chạy method RPC trên server, thành phần nào phù hợp?
A. Dùng `ClientInterceptor` trên server để nhận HTTP response.
B. Dùng `RowMapper` chuyển metadata thành entity và bind RPC.
C. Dùng `ServerInterceptor` để kiểm tra call trước handler.
D. Dùng `StreamObserver.onNext()` để thay mọi bước xác thực.
Đáp án đúng: C

Câu 28. Muốn gắn authorization header cho nhiều lời gọi từ Java client, cách nào phù hợp?
A. Đặt bearer token vào `Status.OK` của response observer.
B. Ghi authorization vào `ObjectName` của server MBean.
C. Dùng `ClientInterceptor` đính kèm metadata cho RPC.
D. Gắn metadata qua `ServerInterceptor` bên client nhận response.
Đáp án đúng: C

Câu 29. Khi triển khai gRPC production, TLS chủ yếu giải quyết vấn đề gì?
A. Tự cấp quyền truy cập mọi RPC sau khi bắt tay HTTP/2.
B. Làm Protobuf message không thể bị đọc bởi ứng dụng server.
C. Bảo đảm RPC không thể lặp khi kết nối mạng bị gián đoạn.
D. Mã hóa kết nối và xác minh certificate của server.
Đáp án đúng: D

Câu 30. Với mTLS giữa hai service gRPC, cơ chế xác thực nào đúng?
A. Client và server xác minh certificate của nhau.
B. Server xác minh client bằng tên DNS không cần certificate.
C. Server kiểm tra mật khẩu client còn client bỏ xác minh server.
D. Client gửi API key trong protobuf rồi bỏ TLS cho transport.
Đáp án đúng: A

Câu 31. Ứng dụng muốn retry unary RPC có side effect, cần thiết kế gì để hạn chế ghi lặp?
A. Chỉ thêm deadline dài để bảo đảm retry sẽ không phát sinh.
B. Retry mọi status với cùng payload vì gRPC tự rollback side effect.
C. Đặt idempotency key hoặc cơ chế deduplication cho thao tác ghi.
D. Đổi unary RPC sang server-streaming để không thể ghi trùng.
Đáp án đúng: C

Câu 32. Muốn kiểm thử lỗi status, deadline và response thực từ gRPC service trong Spring, cách nào đáng tin cậy?
A. Kiểm tra file `.proto` mà không chạy implementation RPC.
B. Dùng generated stub gọi test server và assert status.
C. Mock generated DTO rồi suy ra interceptor server hoạt động.
D. Gọi HTTP JSON endpoint và coi như đã kiểm tra HTTP/2 gRPC.
Đáp án đúng: B
