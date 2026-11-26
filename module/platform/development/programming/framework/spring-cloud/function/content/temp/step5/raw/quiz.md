Câu 1. Khi muốn tái sử dụng một phép biến đổi dữ liệu cho HTTP và message broker, nên tổ chức logic thế nào?
A. Đặt logic trong filter HTTP để dùng chung giữa các hệ thống.
B. Đặt logic trong listener rồi gọi listener qua HTTP nội bộ.
C. Đặt logic ở controller và gọi từ consumer message.
D. Đặt logic trong bean `Function` tách khỏi giao thức gọi.
Đáp án đúng: D

Câu 2. Một bean `Supplier<String>` trong Spring Cloud Function có hợp đồng nào?
A. `get(String)` nhận key rồi lấy dữ liệu theo key.
B. `apply(String)` nhận chuỗi rồi tạo một chuỗi mới.
C. `get()` sinh đầu ra mà không có tham số đầu vào.
D. `accept(String)` nhận dữ liệu và trả về chuỗi.
Đáp án đúng: C

Câu 3. Khai báo `Function<Order, Invoice>` thể hiện hợp đồng nghiệp vụ nào?
A. Nhận `Order`, xử lý side effect và trả `void` bằng `accept`.
B. Không nhận input và tạo `Invoice` khi gọi phương thức `get`.
C. Nhận một `Order` và tạo ra một `Invoice` khi gọi `apply`.
D. Nhận một `Invoice` và tạo ra một `Order` khi gọi `accept`.
Đáp án đúng: C

Câu 4. Khi chọn `Consumer<Event>`, đặc điểm nào phân biệt nó với `Function`?
A. Nó tạo sự kiện từ `get` mà không có bất kỳ đầu vào nào.
B. Nhận sự kiện qua `accept` và không trả dữ liệu.
C. Nó ánh xạ sự kiện qua `apply` và trả về một sự kiện khác.
D. Nó tự phản hồi HTTP response chứa dữ liệu từ handler.
Đáp án đúng: B

Câu 5. Cách đăng ký một `Function<String,String>` để Spring quản lý phù hợp là gì?
A. Khai báo method `@Bean` trả về `Function<String,String>`.
B. Khai báo một method `@EventListener` trả về `Function`.
C. Khai báo một method `@Scheduled` trả về `Function`.
D. Khai báo một method `@PostConstruct` trả về `Function`.
Đáp án đúng: A

Câu 6. `FunctionCatalog` của Spring Cloud Function được dùng trực tiếp để làm gì?
A. Tìm và lấy function đã đăng ký theo tên hoặc định nghĩa.
B. Quản lý offset consumer và xác nhận message từ broker.
C. Tìm bean chưa đăng ký bằng cách quét classpath theo tên.
D. Thiết lập cổng HTTP dành riêng cho từng function đã đăng ký.
Đáp án đúng: A

Câu 7. Khi ứng dụng có nhiều bean chức năng và muốn chọn một hàm mặc định, property nào phù hợp?
A. Dùng `spring.application.name` để xác định hàm mặc định.
B. Dùng `spring.cloud.function.definition` để xác định hàm.
C. Dùng `server.servlet.context-path` để chọn hàm trong catalog.
D. Dùng `spring.cloud.stream.bindings` như tên property duy nhất.
Đáp án đúng: B

Câu 8. Trong `spring.cloud.function.definition`, ký hiệu nào thể hiện composition hai function?
A. Dùng `normalize+enrich` để gọi hai function theo thứ tự.
B. Dùng `normalize,enrich` để nối kết quả giữa hai function.
C. Dùng `normalize|enrich` để nối hai function theo thứ tự.
D. Dùng `normalize:enrich` để khai báo pipeline function.
Đáp án đúng: C

Câu 9. Với chuỗi composition `trim|uppercase`, thứ tự xử lý là gì?
A. Chạy `trim` trước, rồi truyền kết quả cho `uppercase`.
B. Chạy hai hàm đồng thời và chỉ lấy output của `trim`.
C. Thực hiện `uppercase` trước rồi truyền vào `trim`.
D. Chọn một trong hai hàm dựa trên type của HTTP request.
Đáp án đúng: A

Câu 10. Hai function `Function<A,B>` và `Function<B,C>` có thể compose hợp lý vì sao?
A. Hai bean phải khai báo cùng một tên trong catalog.
B. Output loại `B` của hàm trước phù hợp input hàm sau.
C. Hai hàm phải dùng chung `Consumer` làm điểm kết thúc.
D. Đầu vào loại `A` phải trùng hoàn toàn đầu ra `C`.
Đáp án đúng: B

Câu 11. Khi compose `Supplier<T>` với một `Function<T,R>`, cấu trúc hợp lý là gì?
A. Đặt Supplier ở cuối pipeline để nhận output của Function.
B. Đặt Supplier ở giữa hai Consumer để xử lý output.
C. Đặt Supplier sau Router để bắt buộc nhận một Message.
D. Đặt Supplier ở đầu pipeline để cấp input cho Function.
Đáp án đúng: D

Câu 12. Trong composition kết thúc bằng `Consumer<T>`, điều gì xảy ra với output nghiệp vụ?
A. Consumer tạo thêm giá trị cho chặng sau bằng `get`.
B. Consumer trả về một `Mono<T>` theo hợp đồng `accept`.
C. Consumer chuyển dữ liệu sang bước kế bằng `apply`.
D. Consumer nhận dữ liệu cuối chuỗi và không trả giá trị.
Đáp án đúng: D

Câu 13. Muốn lấy một pipeline đã compose từ catalog, cách nào phù hợp?
A. Đăng ký HTTP controller cho mỗi bước để gọi qua localhost.
B. Lookup định nghĩa `validate|transform` trong catalog.
C. Tạo `Supplier` mới chứa danh sách tên function theo thứ tự.
D. Gọi một `Function` riêng rồi tự đổi tên bean lúc runtime.
Đáp án đúng: B

Câu 14. Vì sao khai báo generic type cụ thể cho `Function<Input,Output>` hữu ích?
A. Giúp framework xác định kiểu dữ liệu để chuyển đổi payload.
B. Chọn `String` làm kiểu trung gian cho mọi input và output.
C. Quy định kết nối RabbitMQ cần được mở trước HTTP request.
D. Tự cấu hình HTTP retry và transaction cho mọi adapter.
Đáp án đúng: A

Câu 15. Với `Function<Message<Order>, Message<Result>>`, vì sao sử dụng `Message`?
A. Để tránh phải định nghĩa kiểu dữ liệu của payload.
B. Để thay đổi consumer group chỉ qua method `apply`.
C. Để lưu message vào database trước khi xử lý function.
D. Để đọc hoặc tạo payload cùng header của thông điệp.
Đáp án đúng: D

Câu 16. Khi HTTP adapter nhận JSON cho `Function<Order,Receipt>`, điều kiện nào quan trọng?
A. Phải khởi động một Kafka binder trước khi parse body.
B. Phải đặt method HTTP là GET để parser nhận `Order`.
C. Phải đổi generic input thành `Object` để tránh lỗi.
D. Cần converter để tạo `Order` từ JSON body.
Đáp án đúng: D

Câu 17. Header `contentType` trong message thường ảnh hưởng đến việc gì?
A. Xác định Kafka partition cho mọi message đầu vào.
B. Chọn kiểu chuyển đổi payload tương ứng với content type.
C. Xác định tên function sẽ được gọi theo hash header.
D. Quyết định HTTP port của ứng dụng khi khởi động.
Đáp án đúng: B

Câu 18. Khi `FunctionCatalog` có các hàm tên khác nhau, làm sao gọi đúng hàm?
A. Lookup theo tên đăng ký hoặc tên composition phù hợp.
B. Tra tên class domain của input rồi tạo bean mới tự động.
C. Chọn bean có tên dài nhất để đảm bảo type tương thích.
D. Tra tên bean bằng HTTP path trước khi catalog khởi tạo.
Đáp án đúng: A

Câu 19. Thành phần nào đưa Spring Cloud Function ra HTTP endpoint?
A. Thêm adapter `spring-cloud-function-web` cho HTTP.
B. Thêm starter JDBC cùng Spring Data repository.
C. Thêm Spring Cloud Config Server làm HTTP facade.
D. Thêm Kafka driver để expose HTTP handler.
Đáp án đúng: A

Câu 20. Khi web adapter expose `Function<String,String>` tên `uppercase`, thao tác nào phù hợp?
A. Gửi HTTP DELETE để trả kết quả transform.
B. Gửi HTTP HEAD để framework đọc và chuyển đổi body.
C. Gửi HTTP TRACE để kích hoạt hàm từ tên function.
D. Gửi HTTP POST mang input tới endpoint function.
Đáp án đúng: D

Câu 21. Với `Supplier<String>` được expose qua web adapter, cách gọi thường phù hợp là gì?
A. Gửi HTTP PATCH để ghi payload thành một message mới.
B. Gửi HTTP POST có body `String` để kích hoạt `apply`.
C. Gửi HTTP PUT chứa dữ liệu đầu vào cho method `accept`.
D. Gửi HTTP GET tới endpoint Supplier để lấy giá trị.
Đáp án đúng: D

Câu 22. Khi expose `Consumer<Event>` qua adapter HTTP, cần lưu ý điều nào?
A. Consumer đòi response JSON `Event` để coi là xử lý xong.
B. Consumer tạo output từ dữ liệu cũ bằng phương thức `get`.
C. Xử lý input nhưng không có kết quả nghiệp vụ trả về.
D. Consumer chỉ chạy được khi HTTP method mang tên function.
Đáp án đúng: C

Câu 23. Muốn dùng function làm processor trên Kafka/RabbitMQ, thường cần bổ sung gì?
A. Thêm Spring Cloud Stream và binder của broker tương ứng.
B. Spring Cloud Config Server để tự đọc message từ broker.
C. Spring Data JPA để tạo consumer group trên từng queue.
D. Spring Boot Actuator để tự ánh xạ topic vào function.
Đáp án đúng: A

Câu 24. Trong Spring Cloud Stream, tên binding đầu vào của function `uppercase` theo quy ước là gì?
A. Dùng `uppercase-input` cho mọi phiên bản binder hiện đại.
B. Dùng `uppercase-inbound` do catalog tự đặt theo kiểu dữ liệu.
C. Dùng `uppercase-in-0` cho binding input đầu tiên của hàm.
D. Dùng `uppercase-out-0` để chỉ binding input của hàm.
Đáp án đúng: C

Câu 25. Khi một `Supplier` phát message định kỳ qua Spring Cloud Stream, thành phần nào quyết định lịch poll?
A. Cấu hình `FunctionCatalog.lookup` làm bộ lập lịch thời gian.
B. Dùng poller của Stream cho Supplier không reactive.
C. Cấu hình HTTP connection pool để thực hiện `get` định kỳ.
D. Dùng `@Scheduled` trên catalog để gọi Supplier theo chu kỳ.
Đáp án đúng: B

Câu 26. Với `Function<Flux<Order>,Flux<Result>>`, ý nghĩa kỹ thuật nào đúng?
A. Hàm tự gửi kết quả vào queue mà không cần bất kỳ adapter.
B. Hàm có thể bỏ subscribe do Flux tự sinh response HTTP.
C. Hàm nhận publisher dữ liệu và trả publisher kết quả.
D. Hàm chỉ nhận một `Order` rồi trả một `Result` trực tiếp.
Đáp án đúng: C

Câu 27. Lỗi xảy ra trong một function dùng với broker. Ai quyết định retry hoặc DLQ?
A. JSON converter cấu hình số lần retry trên consumer.
B. Chính lambda Java tự cấu hình dead-letter exchange.
C. Binder/adapter và cấu hình quyết định retry hoặc DLQ.
D. Chính `FunctionCatalog` quyết định requeue trên broker.
Đáp án đúng: C

Câu 28. Để triển khai cùng một `Function` lên môi trường serverless, hướng tiếp cận nào phù hợp?
A. Chuyển `Function` thành `Controller` gắn endpoint cố định.
B. Chuyển dữ liệu đầu vào qua JDBC trước mỗi invocation.
C. Tự đóng gói broker trong cùng process của từng invocation.
D. Dùng adapter serverless để gọi function từ catalog.
Đáp án đúng: D

Câu 29. Tại sao không nên dựa vào bộ nhớ JVM của function serverless để giữ trạng thái lâu dài?
A. Instance có thể bị thu hồi; trạng thái cần kho lưu bền vững.
B. Serverless adapter tự xóa các local variable ở mỗi dòng code.
C. FunctionCatalog chỉ cho phép chạy một invocation mỗi lúc.
D. JVM tự ghi bộ nhớ heap xuống object storage giữa mọi lần gọi.
Đáp án đúng: A

Câu 30. Một `Consumer<Event>` có thể nhận lại cùng sự kiện sau retry. Cách xử lý nào phù hợp?
A. Giả định mỗi message chỉ được broker giao đúng một lần.
B. Thiết kế idempotent theo event ID hoặc khóa nghiệp vụ.
C. Gắn hàm với một topic mới sau mỗi lần xử lý thất bại.
D. Tắt kiểm tra event ID để tránh chậm tốc độ tiêu thụ.
Đáp án đúng: B

Câu 31. Muốn unit test một `Function<Order,Receipt>` mà không phụ thuộc HTTP, nên làm gì?
A. Khởi động image serverless và kiểm tra log thay vì kết quả.
B. Tạo function và assert kết quả `apply` với input xác định.
C. Khởi chạy server web và gọi endpoint qua network mỗi lần.
D. Khởi tạo broker rồi consume topic để lấy kết quả tính toán.
Đáp án đúng: B

Câu 32. Để truy vết sự kiện qua HTTP adapter và broker adapter, nên lưu gì ở boundary?
A. Dùng HTTP port của service để thay correlation ID.
B. Ghi kích thước payload để nối trace giữa các hop.
C. Truyền correlation ID qua header và trace giữa các adapter.
D. Ghi tên bean function như một request ID dùng chung.
Đáp án đúng: C
