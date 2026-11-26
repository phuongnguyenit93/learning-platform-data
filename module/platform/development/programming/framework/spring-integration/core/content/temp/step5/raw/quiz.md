Câu 1. Trong Spring Integration, một `Message<T>` bao gồm những thành phần chính nào?
A. Payload kiểu T cùng một `MessageHandler` gọi trực tiếp.
B. Payload kiểu T cùng tập header chứa metadata của thông điệp.
C. Payload kiểu T cùng một `DataSource` cho việc lưu trạng thái.
D. Payload kiểu T cùng một `TaskExecutor` do sender cấp phát.
Đáp án đúng: B

Câu 2. Muốn tạo Message từ payload và thêm header `tenantId`, API nào thích hợp?
A. Dùng `MessageBuilder.withPayload(data).setHeader("tenantId", id).build()`.
B. Dùng `MessageHandler.withPayload(data).setHeader("tenantId", id)`.
C. Dùng `MessageHeaders.withPayload(data).setHeader("tenantId", id)`.
D. Dùng `MessageChannel.withPayload(data).setHeader("tenantId", id)`.
Đáp án đúng: A

Câu 3. Tại sao nên dùng header thay vì nhét correlation ID vào nội dung nghiệp vụ của message?
A. Header tự đảm bảo message được lưu bền vững qua mọi broker.
B. Header buộc mọi luồng phải xử lý message trong transaction.
C. Header tự kích hoạt retry khi payload có kiểu sai.
D. Header tách metadata định tuyến khỏi payload nghiệp vụ.
Đáp án đúng: D

Câu 4. Với `DirectChannel` không có executor, message được chuyển đến handler theo cách nào?
A. Phát cùng message đến từng subscriber theo cơ chế fan-out.
B. Gọi handler đồng bộ trong luồng thực thi của bên gửi.
C. Lưu message vào hàng đợi để poller lấy theo chu kỳ.
D. Luôn tạo thread mới từ executor pool để xử lý message.
Đáp án đúng: B

Câu 5. Hai handler subscribe vào cùng `DirectChannel`; mô hình phân phối mặc định gần với cách nào?
A. Lưu mỗi message thành hai bản riêng trong QueueChannel.
B. Phân phối một message cho một handler được chọn.
C. Đợi cả hai handler xác nhận rồi mới trả kết quả gửi.
D. Phát một message đến cả hai handler theo thứ tự đăng ký.
Đáp án đúng: B

Câu 6. Khi muốn cùng một event được chuyển đến nhiều subscriber, loại channel nào phù hợp?
A. Dùng `PublishSubscribeChannel` để fan-out các event.
B. Dùng `DirectChannel` để multicast đến mọi subscriber.
C. Dùng `PriorityChannel` để gửi song song đến các subscriber.
D. Dùng `QueueChannel` để tạo bản cho mỗi subscriber.
Đáp án đúng: A

Câu 7. Cần lưu message tạm trong bộ nhớ để consumer chủ động lấy bằng receive; chọn gì?
A. Dùng `QueueChannel` để consumer chủ động poll message.
B. Dùng `DirectChannel` vì nó có bộ đệm message tích hợp.
C. Dùng `PublishSubscribeChannel` vì nó cung cấp `receive()`.
D. Dùng `ExecutorChannel` vì nó giữ message đến khi poller đọc.
Đáp án đúng: A

Câu 8. Với `ExecutorChannel`, điều nào khác với `DirectChannel` về xử lý?
A. Message được cất trong database bởi executor của channel.
B. Việc gọi handler được giao cho `TaskExecutor` cấu hình.
C. Sender đợi xử lý xong trên cùng thread trong mọi trường hợp.
D. Channel gửi message theo cron thay cho lịch chạy executor.
Đáp án đúng: B

Câu 9. Trong Spring Integration, endpoint `Service Activator` thường thực hiện việc gì?
A. Tách collection thành nhiều message rồi đánh số sequence.
B. Chọn một output channel theo nội dung payload message.
C. Gọi service method khi message đến input channel.
D. Gom các message có cùng correlation ID thành kết quả.
Đáp án đúng: C

Câu 10. `@ServiceActivator(inputChannel="requests")` gắn vào method có mục đích gì?
A. Khai báo `requests` là nơi poll kết quả từ gateway.
B. Đăng ký method làm handler cho channel `requests`.
C. Biến method thành nguồn sinh message cho input adapter.
D. Đăng ký `requests` làm error channel của application.
Đáp án đúng: B

Câu 11. Trong một luồng, `Transformer` dùng cho nhiệm vụ nào?
A. Chờ đủ message trong group rồi phát kết quả tổng hợp.
B. Loại message không thỏa điều kiện mà không tạo output.
C. Chọn channel đích bằng ánh xạ theo mã trạng thái.
D. Chuyển payload hoặc message sang dạng dữ liệu mới.
Đáp án đúng: D

Câu 12. Muốn bỏ các order không hợp lệ ngay trong integration flow, pattern nào phù hợp?
A. Đặt `Router` với một channel output cố định cho mọi order.
B. Đặt `Filter` với predicate kiểm tra từng order.
C. Đặt `Aggregator` với release strategy trả về true.
D. Đặt `Bridge` để giữ nguyên message và bỏ validation.
Đáp án đúng: B

Câu 13. Với `Filter` có `discardChannel`, message bị predicate từ chối sẽ đi đâu?
A. Được tự động gửi vào channel chứa các exception.
B. Được chuyển tới channel discard đã cấu hình.
C. Được trả lại nguồn và thực thi lại pipeline đầu tiên.
D. Được gửi về reply channel bất kể headers ban đầu.
Đáp án đúng: B

Câu 14. Khi chọn luồng xử lý theo loại đơn hàng `VIP` hoặc `NORMAL`, nên dùng pattern nào?
A. Dùng `ServiceActivator` để tự tạo một QueueChannel mỗi order.
B. Dùng `Aggregator` để gộp các loại đơn thành một group.
C. Dùng `Router` chọn channel đích theo loại order.
D. Dùng `Transformer` để gửi cùng message đến mọi channel.
Đáp án đúng: C

Câu 15. Để phân rã một message có payload danh sách item thành từng message con, chọn gì?
A. Dùng `Gateway` để phát lại cùng danh sách nhiều lần.
B. Dùng `Aggregator` gom message từ các nguồn thành list.
C. Dùng `Splitter` để phát message cho từng item.
D. Dùng `Filter` trả về true để lấy từng phần tử của list.
Đáp án đúng: C

Câu 16. Sau khi `Splitter` tạo các phần, thông tin nào giúp `Aggregator` ghép đúng nhóm?
A. Header correlation ID cùng metadata sequence của message.
B. Header replyChannel cùng tên bean của channel adapter.
C. Header contentType cùng tên class Java của gateway.
D. Header priority cùng timestamp tạo bean ApplicationContext.
Đáp án đúng: A

Câu 17. Với `Aggregator`, chức năng của correlation strategy là gì?
A. Quyết định format JSON của kết quả sau khi merge.
B. Quyết định thông điệp nào bị loại bởi message filter.
C. Xác định tối đa bao nhiêu thread được xử lý song song.
D. Gom các message theo cùng một khóa correlation.
Đáp án đúng: D

Câu 18. Khi `Aggregator` biết đã nhận đủ các phần của một nhóm, thành phần nào quyết định phát kết quả?
A. `ReleaseStrategy` đánh giá điều kiện hoàn tất của nhóm.
B. `MessageSource` quyết định thời điểm poll các phần tử.
C. `ChannelInterceptor` tự chuyển group thành HTTP response.
D. `MessageBuilder` mở transaction để khóa tất cả channel.
Đáp án đúng: A

Câu 19. Vì sao `Aggregator` thường cần một `MessageGroupStore` trong luồng bất đồng bộ?
A. Chuyển từng message thành HTTP session của client gateway.
B. Quản lý số worker thread thay cho `TaskExecutor` của channel.
C. Giữ trạng thái các message của group đang chờ đủ dữ liệu.
D. Biến mọi channel thành broker có khả năng publish/subscribe.
Đáp án đúng: C

Câu 20. Cần nối hai channel mà giữ nguyên thông điệp, pattern nào thích hợp?
A. Dùng `Aggregator` chờ đủ message rồi mới nối channel.
B. Dùng `Transformer` tạo một payload khác cho channel đích.
C. Dùng `Filter` chỉ trả về true cho message được chuyển.
D. Dùng `Bridge` chuyển message giữa hai channel đã chọn.
Đáp án đúng: D

Câu 21. Trong giao tiếp request/reply, interface được gắn `@MessagingGateway` có tác dụng gì?
A. Cung cấp lời gọi Java để gửi request vào flow và lấy reply.
B. Thay mọi channel trong flow bằng Java method call đồng bộ.
C. Tạo REST controller làm cầu nối giữa client và MessageChannel.
D. Xử lý message theo lịch poller ngay khi gateway được tạo.
Đáp án đúng: A

Câu 22. Khi một gateway method cần nhận reply nhưng flow không trả lời, tham số nào hữu ích?
A. Cấu hình `replyTimeout` để giới hạn thời gian đợi phản hồi.
B. Cấu hình `defaultPayloadExpression` để hủy việc chờ reply.
C. Cấu hình `sendTimeout` để chuyển request thành fire-and-forget.
D. Cấu hình `errorChannel` để tự sinh reply thành công.
Đáp án đúng: A

Câu 23. Trong request/reply của Spring Integration, header nào chỉ đường gửi phản hồi về phía caller?
A. `errorChannel` lưu toàn bộ lịch sử response thành công.
B. `correlationId` chứa địa chỉ của reply gateway mặc định.
C. `sequenceSize` xác định địa chỉ channel nhận response.
D. `replyChannel` là channel để gửi kết quả về phía caller.
Đáp án đúng: D

Câu 24. Trong Java DSL, `IntegrationFlow.from("orders")` thường chỉ điều gì?
A. Đăng ký `orders` làm database transaction manager của flow.
B. Chuyển `orders` thành một gateway interface được sinh.
C. Định nghĩa đầu vào của integration flow từ channel `orders`.
D. Bật polling của channel `orders` trong một thread riêng.
Đáp án đúng: C

Câu 25. Trong Spring Integration Java DSL, cách nối transformer rồi handler phù hợp là gì?
A. Trong `MessageBuilder` dùng `.transform(...)` rồi `.handle(...)`.
B. Trong `MessageHeaders` dùng `.transform(...)` rồi `.handle(...)`.
C. Trong `IntegrationFlow` dùng `.transform(...)` rồi `.handle(...)`.
D. Trong `MessageChannel` dùng `.transform(...)` rồi `.handle(...)`.
Đáp án đúng: C

Câu 26. Một inbound channel adapter cần lấy dữ liệu từ nguồn định kỳ; thành phần nào kích hoạt đọc?
A. `Aggregator` kéo message từ nguồn theo lịch release strategy.
B. `Gateway` tự gọi nguồn định kỳ khi chưa có message reply.
C. `Router` quét nguồn khi không tìm thấy output channel.
D. `Poller` với trigger phù hợp để lấy message từ `MessageSource`.
Đáp án đúng: D

Câu 27. Với `Header Enricher`, một ứng dụng thường dùng nó để làm gì?
A. Chặn các message không có payload và đánh dấu lỗi validation.
B. Gộp các message có chung payload thành một group lưu trữ.
C. Thêm hoặc cập nhật metadata trên message trước bước xử lý.
D. Chuyển đồng thời một message sang nhiều nhánh xử lý khác.
Đáp án đúng: C

Câu 28. Muốn gửi message sang nhánh audit mà vẫn tiếp tục flow chính, dùng pattern nào?
A. Chèn `Router` để message chỉ đi qua channel giám sát.
B. Chèn `Filter` trả false rồi đợi phản hồi từ nhánh audit.
C. Chèn `Wire Tap` để chuyển message tới channel giám sát.
D. Chèn `Aggregator` để sao chép message cho nhánh audit.
Đáp án đúng: C

Câu 29. Khi một endpoint xử lý bất đồng bộ gặp exception, cơ chế nào thường chuyển lỗi qua flow?
A. Gửi message gốc về input channel mà không báo exception.
B. Phát `ErrorMessage` tới `errorChannel` khi được cấu hình.
C. Luôn ném exception trên thread của caller ban đầu.
D. Đổi exception thành `replyChannel` và coi như success.
Đáp án đúng: B

Câu 30. Muốn retry một `MessageHandler` khi lỗi tạm thời, thành phần nào phù hợp?
A. Gắn `@MessagingGateway` lên handler để tự retry request.
B. Gắn `MessageGroupStore` để phát lại mỗi message thất bại.
C. Gắn `HeaderEnricher` để tăng số lần thực hiện handler.
D. Gắn `RequestHandlerRetryAdvice` vào advice chain của handler.
Đáp án đúng: D

Câu 31. Để ngăn một message có id trùng làm lặp side effect, Spring Integration cung cấp gì?
A. Dùng `IdempotentReceiverInterceptor` với metadata selector.
B. Dùng `BridgeHandler` để phát hiện duplicate correlation ID.
C. Dùng `PublishSubscribeChannel` để bỏ các message lặp.
D. Dùng `MessageBuilder` để so sánh payload với tất cả message.
Đáp án đúng: A

Câu 32. Muốn kiểm thử một flow xử lý `orders` và trả kết quả trên output queue, cách nào phù hợp?
A. Gọi `IntegrationFlow.toString()` để xác nhận payload đã transform.
B. Chỉ kiểm tra annotation của gateway rồi bỏ qua luồng thực tế.
C. Chỉ mock `MessageBuilder` mà không chạy integration endpoint.
D. Gửi Message vào input channel và assert output từ `QueueChannel`.
Đáp án đúng: D
