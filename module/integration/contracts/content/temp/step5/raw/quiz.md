Câu 1. Trong tích hợp giữa các dịch vụ, hợp đồng (contract) cần mô tả điều gì?
A. Cấu hình nội bộ và biến môi trường của từng dịch vụ.
B. Định dạng dữ liệu, hành vi và lỗi ở ranh giới dịch vụ.
C. Cấu trúc bảng và chỉ mục trong database của provider.
D. Thuật toán thực thi và chiến lược cache trong provider.
Đáp án đúng: B

Câu 2. OpenAPI chủ yếu mô tả khía cạnh nào của HTTP API?
A. Luồng message giữa các topic theo thời gian.
B. Quy tắc tương thích giữa schema Avro trong registry.
C. Cơ chế retry và delivery tag trong queue consumer.
D. Đường dẫn, operation, tham số và response của API.
Đáp án đúng: D

Câu 3. Trong OpenAPI, `requestBody.required: true` có ý nghĩa gì?
A. Request phải có body theo khai báo của operation.
B. Mọi property trong body đều bắt buộc có mặt.
C. Body phải chứa ít nhất một trường có kiểu string.
D. Response bắt buộc trả body với mọi HTTP status.
Đáp án đúng: A

Câu 4. Một response HTTP `404` trong OpenAPI nên được khai báo ở đâu?
A. Trong `parameters` với trường `name` bằng `404`.
B. Trong `requestBody` để yêu cầu mã lỗi từ client.
C. Trong `responses` của operation dưới mã `404`.
D. Trong `servers` để chọn endpoint xử lý mã lỗi.
Đáp án đúng: C

Câu 5. `required: [email]` trong object schema OpenAPI có nghĩa gì?
A. Property `email` phải có mặt trong object hợp lệ.
B. Property `email` mặc định không được có giá trị `null`.
C. Property `email` được đảm bảo duy nhất trong hệ thống.
D. Property `email` không được sửa sau khi tạo object.
Đáp án đúng: A

Câu 6. Client bỏ qua các JSON field không biết. Thay đổi response nào thường tương thích?
A. Xóa một property đang được client đọc trực tiếp.
B. Đổi kiểu property `amount` từ number sang object.
C. Đổi tên property `id` thành `orderId` không alias.
D. Thêm field `note` tùy chọn vào response JSON.
Đáp án đúng: D

Câu 7. Provider muốn thay đổi HTTP API; thay đổi nào dễ phá vỡ consumer hiện hữu?
A. Bổ sung một response example vào tài liệu OpenAPI.
B. Thêm response header tùy chọn và giữ header cũ.
C. Đổi một field bắt buộc từ `string` sang `object`.
D. Thêm mô tả cho parameter mà không đổi schema.
Đáp án đúng: C

Câu 8. Khi client retry `POST` do timeout, cách nào giúp tránh tạo đơn hàng trùng?
A. Cho phép đổi request ID ngẫu nhiên ở mỗi lần retry.
B. Dùng idempotency key nhất quán ở các lần retry.
C. Chuyển toàn bộ các request `POST` thành `GET`.
D. Bỏ request body khi client thực hiện retry.
Đáp án đúng: B

Câu 9. Thiết kế response lỗi ổn định nên chứa thông tin gì để consumer xử lý?
A. Tên method Java và stack trace đầy đủ của service.
B. Đường dẫn tệp cấu hình và tên node đang chạy.
C. Mã lỗi ổn định để máy đọc và mô tả ngữ cảnh.
D. Chi tiết câu lệnh SQL và dữ liệu bảng liên quan.
Đáp án đúng: C

Câu 10. Trong consumer-driven contract testing, ai xác định interaction được kỳ vọng?
A. Consumer định nghĩa kỳ vọng để provider kiểm chứng.
B. Provider tự sinh mọi kỳ vọng từ bảng dữ liệu.
C. Broker tạo kỳ vọng dựa trên độ trễ message.
D. API gateway chọn kỳ vọng theo đường dẫn HTTP.
Đáp án đúng: A

Câu 11. Một bộ contract test đã PASS nhưng workflow nhiều dịch vụ vẫn lỗi. Kết luận nào đúng?
A. Contract test bảo đảm mọi workflow liên dịch vụ chạy tốt.
B. Contract test thay thế được toàn bộ integration test.
C. Contract test kiểm giao diện, chưa bảo đảm cả workflow.
D. Contract test chỉ xác nhận cú pháp của tài liệu OpenAPI.
Đáp án đúng: C

Câu 12. AsyncAPI phù hợp nhất để mô tả điều gì?
A. Các bảng, view và index của cơ sở dữ liệu.
B. Channel, message và operation cho hệ thống bất đồng bộ.
C. Các phương thức public của Java class trong ứng dụng.
D. Đường dẫn file và biến môi trường của container.
Đáp án đúng: B

Câu 13. Trong event-driven integration, trường nào giúp phát hiện message được gửi lặp?
A. Timestamp được format theo múi giờ của producer.
B. Tên exchange mà message đi qua ở broker.
C. Số kết nối TCP đang mở tới message broker.
D. Event ID ổn định cho cùng một sự kiện logic.
Đáp án đúng: D

Câu 14. Sự kiện `OrderPlaced` khác lệnh `PlaceOrder` về ngữ nghĩa ở điểm nào?
A. Sự kiện luôn yêu cầu xử lý đồng bộ trong HTTP API.
B. Sự kiện ghi nhận việc đã xảy ra trong miền nghiệp vụ.
C. Sự kiện được gửi để yêu cầu tạo đơn hàng ở provider.
D. Sự kiện không thể chứa dữ liệu đơn hàng hoặc thời gian.
Đáp án đúng: B

Câu 15. Consumer nhận message theo cơ chế at-least-once cần chuẩn bị điều gì?
A. Message chỉ có thể được giao một lần duy nhất.
B. Producer không cần định danh sự kiện đã publish.
C. Broker bảo đảm side effect thực thi đúng một lần.
D. Message có thể đến lặp, cần xử lý idempotent.
Đáp án đúng: D

Câu 16. Khi nâng cấp schema sự kiện cho nhiều consumer, chiến lược phù hợp là gì?
A. Giữ tương thích và chuyển đổi theo từng phiên bản.
B. Thay tất cả field names trước khi triển khai consumer.
C. Ngừng gửi toàn bộ message cho tới khi nâng cấp.
D. Đổi message format bất kỳ nếu đã tăng version.
Đáp án đúng: A

Câu 17. Trong Avro, việc đọc dữ liệu bằng schema mới so với schema đã ghi dựa vào đâu?
A. Chỉ reader schema, không xét định dạng đã ghi.
B. Quy tắc phân giải giữa writer schema và reader schema.
C. Chỉ tên topic nơi producer xuất bản bản ghi.
D. Quy tắc routing key giữa exchange và queue.
Đáp án đúng: B

Câu 18. Reader schema Avro thêm field `locale` có `default`, còn writer cũ thiếu field. Khi đọc sẽ thế nào?
A. Avro luôn báo lỗi vì hai schema khác số lượng field.
B. Avro lấy giá trị `locale` từ tên record của writer.
C. Reader có thể dùng giá trị mặc định cho `locale`.
D. Reader bắt buộc ghi lại toàn bộ dữ liệu cũ trước.
Đáp án đúng: C

Câu 19. Tình huống nào dễ làm Avro reader cũ không đọc được dữ liệu từ writer mới?
A. Writer xóa field reader cũ yêu cầu mà thiếu default.
B. Writer thêm field nhưng reader cũ không dùng đến field đó.
C. Writer giữ nguyên field và cập nhật tài liệu mô tả.
D. Writer thay đổi thứ tự field nhưng giữ nguyên tên.
Đáp án đúng: A

Câu 20. Avro binary serialization có đặc điểm nào sau đây?
A. Mọi giá trị đều mang tên field trong byte stream.
B. Consumer luôn cần HTTP URL của provider để giải mã.
C. Dữ liệu được lưu thành JSON object thuần văn bản.
D. Giải mã cần biết schema tương ứng với dữ liệu.
Đáp án đúng: D

Câu 21. Trong Protobuf, field number như `id = 1` có vai trò gì khi mã hóa?
A. Quy định vị trí field trong JSON document bắt buộc.
B. Tag số dùng định danh field trong Protobuf wire format.
C. Xác định số phiên bản của gRPC service hiện tại.
D. Đặt thứ tự thực thi resolver khi service nhận RPC.
Đáp án đúng: B

Câu 22. Với Protobuf binary, thêm field mới mang tag chưa dùng thường ảnh hưởng client cũ thế nào?
A. Client cũ có thể bỏ qua field lạ khi giải mã.
B. Client cũ bắt buộc phải đổi số tag của field cũ.
C. Client cũ tự tạo RPC mới từ field chưa biết.
D. Client cũ sẽ đổi tất cả giá trị scalar sang string.
Đáp án đúng: A

Câu 23. Khi xóa field trong schema Protobuf, nên xử lý tag number cũ như thế nào?
A. Dùng lại tag cho một field có kiểu khác ở version mới.
B. Đổi tag của tất cả field còn lại cho liền số.
C. Đánh dấu tag cũ là `reserved` để tránh tái sử dụng.
D. Chuyển tag cũ sang message khác trong cùng service.
Đáp án đúng: C

Câu 24. Trong `proto3`, khai báo `optional int32 age = 1` hỗ trợ điều gì?
A. Phân biệt vắng mặt và giá trị mặc định của field.
B. Bảo đảm `age` luôn hiện diện trong mọi message.
C. Làm `age` trở thành khóa định danh duy nhất.
D. Cho phép `age` mang nhiều số nguyên theo mảng.
Đáp án đúng: A

Câu 25. Trong Protobuf service definition, `rpc GetUser(GetUserRequest) returns (GetUserResponse)` mô tả gì?
A. Bảng dữ liệu mà server ghi trước khi xử lý RPC.
B. Topic và key để producer phát event bất đồng bộ.
C. HTTP status code cho response khi có lỗi.
D. Tên RPC và kiểu message dùng làm request, response.
Đáp án đúng: D

Câu 26. Với RPC có timeout, `deadline` phía caller thể hiện điều gì?
A. Thời gian chạy tối đa của toàn bộ cụm dịch vụ.
B. Lịch ghi log yêu cầu của server trong phiên.
C. Thời điểm giới hạn mà caller chấp nhận chờ.
D. Chu kỳ làm mới schema trong hệ thống registry.
Đáp án đúng: C

Câu 27. Tại sao retry RPC tạo thanh toán có thể gây lỗi nghiệp vụ?
A. Mọi RPC đều được đảm bảo exactly-once bởi HTTP/2.
B. Một lệnh không idempotent có thể bị thực thi lặp.
C. Protobuf từ chối message giống nhau trong cùng phút.
D. gRPC bắt buộc tăng version khi client thử lại.
Đáp án đúng: B

Câu 28. Theo Semantic Versioning, thay đổi phá vỡ contract công khai thường tăng phần nào?
A. Bản PATCH vì thay đổi chỉ liên quan triển khai.
B. Bản MINOR vì provider đã thêm validation mới.
C. Build metadata vì client không cần nâng cấp.
D. Bản MAJOR vì consumer có thể cần thích ứng.
Đáp án đúng: D

Câu 29. Một field API đã deprecated nhưng client còn dùng. Cách tiến hóa phù hợp?
A. Xóa ngay field và giữ nguyên đường dẫn tài liệu.
B. Thay nghĩa field nhưng không thông báo cho client.
C. Công bố hạn ngừng dùng và lộ trình chuyển đổi.
D. Chỉ thay tên field trong SDK rồi deploy production.
Đáp án đúng: C

Câu 30. Schema Registry trong hệ thống message thường phục vụ việc gì?
A. Lưu schema theo phiên bản và kiểm tra tương thích.
B. Chọn queue đích theo độ ưu tiên của consumer.
C. Thay thế broker để truyền dữ liệu giữa các service.
D. Tự triển khai toàn bộ provider mỗi khi đổi schema.
Đáp án đúng: A

Câu 31. Trong CI, gate nào phát hiện sớm thay đổi contract không tương thích?
A. Chỉ kiểm tra tỷ lệ dòng code được unit test.
B. Chạy schema diff và xác minh contract của provider.
C. Chỉ kiểm tra container image có build thành công.
D. Chỉ chạy benchmark CPU trên một ứng dụng riêng.
Đáp án đúng: B

Câu 32. Một chính sách BACKWARD compatibility của Schema Registry thường yêu cầu điều gì?
A. Schema cũ phải đọc được mọi bản ghi do writer mới tạo.
B. Producer mới chỉ được ghi vào queue được đánh số cao.
C. Consumer cũ phải thực thi mọi thao tác RPC được thêm.
D. Schema mới phải đọc được dữ liệu do writer cũ tạo.
Đáp án đúng: D
