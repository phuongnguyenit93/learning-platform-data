Câu 1. Trong Spring Modulith, trao đổi sự kiện nghiệp vụ giữa các module đem lại lợi ích chính nào?
A. Sự kiện buộc các module chia sẻ entity và repository dữ liệu.
B. Publisher không cần phụ thuộc trực tiếp service của module nhận.
C. Module phát sự kiện tự có REST client tới các module nhận.
D. Mọi lời gọi giữa module được bảo đảm chạy trong cùng transaction.
Đáp án đúng: B

Câu 2. Service Spring muốn phát `OrderCompleted` cho các module khác, dùng API nào phù hợp?
A. Gọi `KafkaTemplate.send(...)` để phát event trong cùng context.
B. Gọi `TransactionTemplate.execute(...)` để phát domain event.
C. Gọi `ApplicationEventPublisher.publishEvent(orderCompleted)`.
D. Gọi `ApplicationContext.start()` để phát domain event.
Đáp án đúng: C

Câu 3. Thiết kế payload sự kiện `OrderCompleted` nào phù hợp hơn để giữ ranh giới module?
A. Truyền nguyên entity JPA đang được quản lý cùng session.
B. Truyền service bean của module phát làm dữ liệu sự kiện.
C. Truyền repository nội bộ để listener truy vấn trong publisher.
D. Dùng dữ liệu nghiệp vụ ổn định như orderId và eventId.
Đáp án đúng: D

Câu 4. Module khác muốn nhận sự kiện `OrderCompleted` bằng cơ chế Spring cơ bản; nên dùng gì?
A. Gắn `@EventListener` vào method nhận `OrderCompleted`.
B. Đánh dấu method nhận `OrderCompleted` bằng `@Scheduled`.
C. Đánh dấu method nhận `OrderCompleted` bằng `@RequestMapping`.
D. Đánh dấu method nhận `OrderCompleted` bằng `@InitBinder`.
Đáp án đúng: A

Câu 5. Với multicaster mặc định không cấu hình executor, `@EventListener` thông thường chạy thế nào?
A. Listener được gọi đồng bộ trong thread đang phát sự kiện.
B. Listener chạy sau commit của transaction ngay cả khi không cấu hình.
C. Listener được đặt vào broker và một thread khác tự lấy ra.
D. Listener được kích hoạt định kỳ bởi scheduler của Modulith.
Đáp án đúng: A

Câu 6. Service `@Transactional` gọi `publishEvent(...)`; khi nào `@EventListener` đồng bộ mặc định chạy?
A. Sau khi service trả kết quả và Spring đóng ApplicationContext.
B. Sau commit nhờ Spring tự đổi mọi listener thành after-commit.
C. Khi Event Publication Registry chạy job phục hồi các publication.
D. Listener chạy ngay khi publish, có thể trước commit của transaction.
Đáp án đúng: D

Câu 7. Một `@EventListener` đồng bộ ném RuntimeException không được bắt trong service `@Transactional`; rủi ro gì?
A. Exception truyền về publisher và có thể làm rollback transaction.
B. Transaction gốc đã commit trước khi exception từ listener phát ra.
C. Listener tự retry vô hạn mà service không quan sát được lỗi.
D. Exception được đổi thành một event mới rồi publisher vẫn thành công.
Đáp án đúng: A

Câu 8. Nếu muốn listener mặc định chạy sau khi transaction phát sự kiện commit, annotation nào phù hợp?
A. Dùng `@TransactionalEventListener`, mặc định là `AFTER_COMMIT`.
B. Dùng `@Order` để trì hoãn listener đến sau database commit.
C. Dùng `@Async` thay thế việc quan sát trạng thái commit.
D. Dùng `@EventListener` rồi đặt `@Transactional(readOnly=true)`.
Đáp án đúng: A

Câu 9. `@TransactionalEventListener` mặc định gặp event được phát mà không có transaction; kết quả gì?
A. Listener đưa event vào queue chờ transaction kế tiếp.
B. Listener tự tạo transaction mới rồi bắt đầu xử lý event.
C. Listener không chạy khi `fallbackExecution` vẫn là false.
D. Listener gọi ngay như `@EventListener` bất kể cấu hình.
Đáp án đúng: C

Câu 10. Khi đặt `fallbackExecution=true` trên `@TransactionalEventListener`, tác động nào đáng chú ý?
A. Bắt buộc listener chạy trong transaction `REQUIRES_NEW`.
B. Xử lý event cả khi lúc publish không có transaction.
C. Hoãn event đến sau commit của transaction tiếp theo.
D. Biến event chưa xử lý thành message Kafka được lưu bền.
Đáp án đúng: B

Câu 11. Để validate trạng thái trước khi transaction nguồn commit, pha nào của `@TransactionalEventListener` phù hợp?
A. Chọn `TransactionPhase.AFTER_COMPLETION` cho listener.
B. Chọn `TransactionPhase.BEFORE_COMMIT` cho listener.
C. Chọn `TransactionPhase.AFTER_COMMIT` cho listener.
D. Chọn `TransactionPhase.AFTER_ROLLBACK` cho listener.
Đáp án đúng: B

Câu 12. Muốn chạy logic bù trừ khi transaction phát sự kiện bị rollback, pha nào phù hợp?
A. Chọn `TransactionPhase.BEFORE_COMMIT` cho listener.
B. Chọn `TransactionPhase.AFTER_COMMIT` cho listener.
C. Chọn `TransactionPhase.AFTER_ROLLBACK` cho listener.
D. Chọn `TransactionPhase.AFTER_COMPLETION` để chỉ bắt rollback.
Đáp án đúng: C

Câu 13. Một listener cần chạy sau khi transaction kết thúc, kể cả commit hay rollback; chọn pha gì?
A. Chọn `TransactionPhase.AFTER_ROLLBACK` để nhận cả commit.
B. Chọn `TransactionPhase.BEFORE_COMMIT` cho mọi kết thúc.
C. Chọn `TransactionPhase.AFTER_COMPLETION` cho listener.
D. Chọn `TransactionPhase.AFTER_COMMIT` để nhận cả rollback.
Đáp án đúng: C

Câu 14. Trong Spring Modulith, `@ApplicationModuleListener` kết hợp các hành vi quan trọng nào?
A. Nhận event lúc publish, chạy đồng bộ và khóa module nguồn.
B. Nhận event trước commit, chạy đồng bộ và dùng transaction cũ.
C. Nhận event sau rollback, chạy async và bỏ qua transaction.
D. Nhận event sau commit, chạy async và dùng transaction mới.
Đáp án đúng: D

Câu 15. Vì sao module `Shipping` nên nhận `OrderCompleted` qua listener thay vì service `Order` gọi trực tiếp?
A. Module Order phụ thuộc event contract thay vì API Shipping.
B. Module Order phải biết implementation Shipping để tạo event.
C. Module Shipping và Order sẽ tự chia sẻ một database transaction.
D. Module Shipping có thể sửa trực tiếp aggregate của Order.
Đáp án đúng: A

Câu 16. Listener sau commit cần ghi thêm bản ghi DB độc lập; cấu hình giao dịch nào phù hợp?
A. Dùng `SUPPORTS` để tiếp tục commit của transaction đã xong.
B. Dùng `MANDATORY` để gắn vào transaction nguồn đã kết thúc.
C. Mở transaction `REQUIRES_NEW` cho phần ghi của listener.
D. Dùng `NOT_SUPPORTED` để đảm bảo mọi update được commit.
Đáp án đúng: C

Câu 17. Listener sau commit xử lý bất đồng bộ bị lỗi; điều nào đúng về transaction của publisher?
A. Commit đã hoàn tất nên lỗi listener không rollback publisher.
B. Publisher đợi listener retry thành công rồi mới commit dữ liệu.
C. Transaction publisher tự rollback ngay khi listener retry thất bại.
D. Spring chuyển transaction publisher sang trạng thái rollback-only.
Đáp án đúng: A

Câu 18. Event Publication Registry của Spring Modulith giúp giải quyết nhu cầu nào?
A. Tự khóa tất cả module cho tới khi listener xác nhận thành công.
B. Ghi nhận các lần giao event tới listener để theo dõi kết quả.
C. Lưu toàn bộ entity domain như một kho dữ liệu thay repository.
D. Thay ApplicationEventPublisher bằng giao thức Kafka cho mọi event.
Đáp án đúng: B

Câu 19. Muốn giữ các publication qua lần restart ứng dụng, nên chọn cách lưu registry nào?
A. Đưa `@Async` vào publisher để event được ghi xuống database.
B. Dùng repository lưu bền như JDBC hoặc JPA cho registry.
C. Chỉ dùng bộ nhớ heap của publisher và giữ application event.
D. Chọn singleton listener bean để hệ thống tự lưu các publication.
Đáp án đúng: B

Câu 20. Trong cơ chế registry, một publication được đánh dấu hoàn tất khi nào?
A. Ngay lúc transaction nguồn commit dù listener còn đang lỗi.
B. Ngay lúc `publishEvent()` được gọi dù listener chưa chạy.
C. Khi event được serialize mà chưa tới listener đích.
D. Sau khi listener xử lý và registry ghi nhận completion.
Đáp án đúng: D

Câu 21. Nếu transactional event listener ném exception và registry đang hoạt động, trạng thái publication thường là gì?
A. Vẫn còn chưa hoàn tất để có thể phục hồi hoặc xử lý lại.
B. Được đánh dấu hoàn tất vì service publisher đã commit.
C. Được xóa khỏi registry như thể listener chưa từng tồn tại.
D. Chuyển sang trạng thái đã hủy và không thể retry lại.
Đáp án đúng: A

Câu 22. Sau khi ứng dụng khởi động lại, nên xử lý publication chưa hoàn tất theo hướng nào?
A. Gửi lại transaction gốc của publisher như một lệnh SQL mới.
B. Xóa registry trước khi khởi động các module nhận sự kiện.
C. Tự coi các publication cũ thành công vì đã qua thời điểm commit.
D. Resubmit publication chưa hoàn tất và quan sát lần thử lại.
Đáp án đúng: D

Câu 23. Vì sao listener dùng registry và replay vẫn cần thiết kế idempotent?
A. Listener được bỏ qua vĩnh viễn khi cùng payload xuất hiện lần nữa.
B. Registry đảm bảo database update và completion là một XA commit.
C. Event có thể đến lại nếu completion chưa kịp được ghi.
D. Mỗi event được broker đánh số toàn cục nên không thể phát trùng.
Đáp án đúng: C

Câu 24. Một event có hai transactional listeners; registry hữu ích nhất theo dõi việc giao thế nào?
A. Tạo hai transaction publisher riêng trước khi commit đơn hàng.
B. Đánh dấu cả hai thành công khi listener đầu tiên hoàn tất.
C. Theo dõi completion cho từng listener đích của publication.
D. Gán một offset Kafka chung cho tất cả listener của event.
Đáp án đúng: C

Câu 25. Đâu là phạm vi chủ yếu của persistent publication registry, khi không có adapter bổ sung?
A. Tự bảo đảm durability cho mọi `@EventListener` đồng bộ.
B. Theo dõi delivery cho các transactional listener được hỗ trợ.
C. Tự cung cấp truyền event qua mạng giữa nhiều microservice.
D. Tự lưu kết quả business của từng service trong event payload.
Đáp án đúng: B

Câu 26. Một event được publish trong transaction cuối cùng rollback; listener mặc định AFTER_COMMIT sẽ thế nào?
A. Listener AFTER_COMMIT không chạy khi transaction rollback.
B. Được chuyển thành event AFTER_ROLLBACK mà không cần annotation.
C. Chạy với transaction nguồn được tự khởi tạo lại bởi listener.
D. Vẫn chạy vì `publishEvent()` đã được gọi trước lúc rollback.
Đáp án đúng: A

Câu 27. Ứng dụng cần đưa event sang microservice khác; giới hạn nào của `ApplicationEventPublisher` cần nhớ?
A. Event local mặc định có offset để microservice khác đọc lại.
B. Publisher tự tạo consumer group để các service cùng nhận event.
C. Publisher tự triển khai network transport giữa các application.
D. Application event chủ yếu chạy trong Spring context hiện tại.
Đáp án đúng: D

Câu 28. Muốn công bố một số domain event qua broker bên ngoài mà vẫn phát event nội bộ, chọn hướng nào?
A. Thay toàn bộ listener bằng `@Scheduled` để poll bean phát.
B. Chọn `ApplicationEventPublisher` làm Kafka producer trực tiếp.
C. Đặt `@TransactionalEventListener` để tự mở Kafka connection.
D. Dùng event externalization với adapter broker được cấu hình.
Đáp án đúng: D

Câu 29. Khi giám sát khả năng giao event đáng tin cậy, bộ tín hiệu nào hữu ích?
A. Đo tốc độ publish nhưng bỏ qua backlog và lỗi listener.
B. Theo dõi publication tồn đọng, tuổi tồn đọng và lỗi listener.
C. Đo số module đã tạo mà không kiểm tra registry health.
D. Đo số event class nhưng không quan sát listener failure.
Đáp án đúng: B

Câu 30. Để kiểm tra việc một service phát đúng domain event trong module test, công cụ nào phù hợp?
A. Dùng `ApplicationModules.verify()` để đếm event đã phát.
B. Dùng `@ApplicationModuleTest` để lấy danh sách event đã phát.
C. Dùng `PublishedEvents` của Modulith để assert event đã phát.
D. Dùng `EventPublicationRegistry` để tự assert toàn bộ payload.
Đáp án đúng: C

Câu 31. Muốn integration test tập trung vào phạm vi một application module của Modulith, dùng gì?
A. Đặt `@TransactionalEventListener` trên class test thay test context.
B. Đánh dấu test bằng `@ApplicationModuleTest` cho module được chọn.
C. Chỉ tạo Mockito mock cho module và không khởi động context.
D. Đặt `@ComponentScan` toàn ứng dụng để coi như module test.
Đáp án đúng: B

Câu 32. Cần test luồng listener bất đồng bộ và chờ một event được phát; công cụ nào hữu ích?
A. Dùng `PublishedEvents` để tự động chờ listener hoàn tất.
B. Dùng `@EventListener` trong test và sleep cố định để chờ.
C. Dùng `@ApplicationModuleTest` để bật chờ event theo thời gian.
D. Dùng `Scenario` của Modulith để publish và chờ event phù hợp.
Đáp án đúng: D
