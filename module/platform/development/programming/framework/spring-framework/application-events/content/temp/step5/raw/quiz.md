Câu 01. Trong cùng ApplicationContext, `ApplicationEventPublisher` được dùng chủ yếu để làm gì?
A. Đưa message lên broker trước khi listener nội bộ nhận
B. Tạo transaction độc lập trước khi gọi mỗi event listener
C. Đăng ký các listener thay cho bước tạo Spring bean
D. Phát event đến các listener phù hợp trong cùng context
Đáp án đúng: D

Câu 02. Khi gọi `publishEvent(orderPlaced)` với POJO không kế thừa `ApplicationEvent`, Spring làm gì?
A. Giữ POJO đến lần `refresh()` tiếp theo rồi mới phát
B. Bọc POJO trong `PayloadApplicationEvent` rồi phát đi
C. Chỉ chấp nhận event kế thừa `ApplicationEvent`
D. Chuyển POJO thành `ContextRefreshedEvent` trước khi phát
Đáp án đúng: B

Câu 03. Một lớp event kế thừa `ApplicationEvent` cần khởi tạo phần nguồn sự kiện thế nào?
A. Gọi `super(source)` ở constructor của custom event
B. Gọi `publishEvent(source)` ở constructor custom event
C. Gọi `setSource(source)` sau khi đã tạo event bean
D. Gọi `onApplicationEvent(source)` khi new event
Đáp án đúng: A

Câu 04. Bean chỉ cần phát event nên inject interface nào để giảm coupling với context?
A. Inject `ApplicationEventPublisher` để chỉ dùng API phát
B. Inject `ApplicationEvent` để gọi publish từ event
C. Inject `ApplicationEventMulticaster` để dùng context API
D. Inject `ApplicationListener` để dùng API phát sự kiện
Đáp án đúng: A

Câu 05. Muốn nhận event POJO `OrderPlaced` bằng annotation, bean nên khai báo gì?
A. Method nhận `OrderPlaced` và đánh dấu `@Transactional`
B. Method nhận `OrderPlaced` và đánh dấu `@EventListenerFactory`
C. Method trả `OrderPlaced` và đánh dấu `@EventPublisher`
D. Method nhận `OrderPlaced` và đánh dấu `@EventListener`
Đáp án đúng: D

Câu 06. Khi implement `ApplicationListener<StockLowEvent>`, method nào xử lý event?
A. `publishEvent(StockLowEvent event)` nhận event
B. `handleEvent(StockLowEvent event)` nhận event
C. `onApplicationEvent(StockLowEvent event)` nhận event
D. `afterCompletion(StockLowEvent event)` nhận event
Đáp án đúng: C

Câu 07. Một `ApplicationListener<T>` được tạo thành Spring bean sẽ được sử dụng ra sao?
A. Chỉ nhận event nếu bean còn gắn thêm `@EnableAsync`
B. Chỉ nhận `ContextRefreshedEvent` dù đã khai báo T
C. Chỉ được gọi khi publisher inject trực tiếp bean ấy
D. Context phát hiện bean và đăng ký nó làm listener
Đáp án đúng: D

Câu 08. Khi hai listener cùng tương thích với kiểu event được publish, hành vi mặc định là gì?
A. Spring chọn một listener theo group name giống broker
B. Cả hai có thể được gọi để xử lý cùng một event
C. Chỉ listener đăng ký sớm nhất được nhận event
D. Listener đầu nhận event, listener sau nhận payload khác
Đáp án đúng: B

Câu 09. Với cơ chế event mặc định chưa cấu hình executor, listener chạy trên thread nào?
A. Listener chạy trên thread pool do Spring khởi tạo
B. Listener chạy ngay trên thread gọi `publishEvent`
C. Listener chạy riêng sau khi thread publisher hoàn tất
D. Listener chạy trên thread của DB transaction manager
Đáp án đúng: B

Câu 10. Với listener đồng bộ ném RuntimeException và không có ErrorHandler, điều gì thường xảy ra?
A. Exception chỉ xuất hiện sau khi context đã đóng
B. Exception bị nuốt trước khi publisher nhận được lỗi
C. Lỗi có thể truyền ngược tới nơi gọi `publishEvent`
D. Exception được chuyển đến dead-letter queue của Spring
Đáp án đúng: C

Câu 11. Một listener đồng bộ lại gọi `publishEvent` cho event khác; lệnh phát lồng nhau diễn ra thế nào?
A. Event mới có thể chạy ngay trên call stack hiện tại
B. Event mới chỉ đến listener nếu transaction đã commit
C. Event mới chỉ chạy sau khi application context refresh
D. Event mới mặc định xếp hàng để worker khác xử lý sau
Đáp án đúng: A

Câu 12. Cần ưu tiên listener A trước B trong dispatch đồng bộ; annotation nào hỗ trợ?
A. Áp dụng `@Order` để định thứ tự các listener tương ứng
B. Áp dụng `@Async` để định thứ tự các listener tương ứng
C. Áp dụng `@Primary` để định thứ tự các listener tương ứng
D. Áp dụng `@DependsOn` để định thứ tự các listener tương ứng
Đáp án đúng: A

Câu 13. Muốn tùy biến bộ phân phối ApplicationContext event, bean nên có tên nào?
A. Bean `applicationListenerFactory` do context nhận diện
B. Bean `applicationEventScheduler` do context nhận diện
C. Bean tên `applicationEventMulticaster` để phân phối event
D. Bean `applicationEventPublisher` do context nhận diện
Đáp án đúng: C

Câu 14. Để multicaster chạy các listener có hỗ trợ async qua executor, nên cấu hình gì?
A. Gắn `TransactionManager` cho `ApplicationEventPublisher`
B. Gắn `TaskScheduler` cho `ApplicationEventPublisher`
C. Gắn `Executor` cho `ApplicationListener` của từng event
D. Gắn `TaskExecutor` cho `SimpleApplicationEventMulticaster`
Đáp án đúng: D

Câu 15. Muốn method `@EventListener` có `@Async` được xử lý bất đồng bộ, cần bật gì?
A. Bật `@EnableScheduling` để listener chạy qua scheduler
B. Bật `@EnableAsync` để kích hoạt async proxy cho method
C. Bật `@EnableTransactionManagement` để listener sang thread
D. Bật `@EnableAspectJAutoProxy` thay cho cơ chế async
Đáp án đúng: B

Câu 16. Vì sao context transaction thread-bound thường không sẵn trên thread chạy `@Async` listener?
A. Transaction context được serialize theo event payload mặc định
B. Thread async nhận lại transaction context của publisher
C. Thread xử lý async khác thread đang giữ transaction context
D. Publisher tự tạo JDBC transaction mới ở thread listener
Đáp án đúng: C

Câu 17. Một `@Async @EventListener` void ném exception; bên publish có nhận exception đồng bộ không?
A. Lỗi mặc định rollback transaction đang chạy của publisher
B. Lỗi ở thread async, không ném trực tiếp về publisher
C. Lỗi truyền ngay qua `publishEvent` trên thread ban đầu
D. Lỗi biến thành `ContextClosedEvent` ở publisher thread
Đáp án đúng: B

Câu 18. Với `@EventListener` đồng bộ trả về một object khác `void`, Spring xử lý kết quả thế nào?
A. Kết quả được lưu vào cache của ApplicationContext
B. Kết quả chỉ chuyển thành return value của `publishEvent`
C. Kết quả bị bỏ qua nếu event ban đầu không extends Event
D. Spring có thể phát return value như một event mới
Đáp án đúng: D

Câu 19. Vì sao nên dùng `void` cho `@Async @EventListener` thay vì dựa vào event từ return value?
A. Async listener trả `ApplicationEventPublisher` khi phát event
B. Async listener chỉ phát return value khi có `@Order`
C. Async listener publish các giá trị trả về sau commit
D. Async listener không hỗ trợ publish event qua return value
Đáp án đúng: D

Câu 20. Cấu hình `@EventListener(condition = "#root.args[0].approved")` có mục đích gì?
A. Chuyển listener thành async khi approved bằng true
B. Chỉ publish event nếu transaction đang commit
C. Chỉ gọi listener nếu điều kiện SpEL trả về true
D. Chỉ định kiểu event được deserialize từ message broker
Đáp án đúng: C

Câu 21. Muốn một listener không tham số nhận cả `OrderPlaced` và `OrderCancelled`, nên làm gì?
A. Khai báo hai event class trong `@EventListener`
B. Đặt `@Transactional` cho method để nhận hai kiểu event
C. Đặt `@Primary` để Spring chọn cả hai event type
D. Đổi tên bean listener thành hai tên khác nhau
Đáp án đúng: A

Câu 22. `ContextRefreshedEvent` có ý nghĩa nào trong vòng đời Spring context?
A. Được phát trước mỗi transaction commit trong context
B. Được phát sau mỗi HTTP request thành công của servlet
C. Được phát sau khi ApplicationContext khởi tạo hoặc refresh
D. Được phát mỗi lần một bean `@PostConstruct` hoàn tất
Đáp án đúng: C

Câu 23. Muốn thực hiện cleanup khi ApplicationContext đóng, nên lắng nghe event nào?
A. `ContextStartedEvent` phát khi context bắt đầu đóng
B. `ContextStoppedEvent` phát khi `publishEvent` kết thúc
C. `ContextClosedEvent` phát khi context đang được đóng
D. `ContextRefreshedEvent` phát khi JVM chuẩn bị dừng
Đáp án đúng: C

Câu 24. `ContextStartedEvent` thường được kích hoạt bởi thao tác nào?
A. Gọi `start()` trên ConfigurableApplicationContext
B. Gọi `refresh()` trên ConfigurableApplicationContext
C. Gọi `close()` trên ConfigurableApplicationContext
D. Gọi `stop()` trên ConfigurableApplicationContext
Đáp án đúng: A

Câu 25. `ContextStoppedEvent` thường xuất hiện khi nào?
A. Khi gọi `refresh()` trên ConfigurableApplicationContext
B. Khi gọi `publishEvent()` lần đầu sau khi context tạo
C. Khi gọi `stop()` trên ConfigurableApplicationContext
D. Khi gọi `start()` trên ConfigurableApplicationContext
Đáp án đúng: C

Câu 26. Khi có parent và child ApplicationContext, event publish từ child có thể đi tới đâu?
A. Event từ child chỉ xử lý ở root và bỏ listener của child
B. Event từ child chỉ đến parent khi có `@Async`
C. Event từ child mặc định phát xuống các sibling context
D. Event được chuyển tiếp từ child lên parent context
Đáp án đúng: D

Câu 27. Với `@TransactionalEventListener` không chỉ định phase, listener chạy ở pha nào?
A. Trước transaction bắt đầu do mặc định là `BEFORE_BEGIN`
B. Trước commit dữ liệu do mặc định là `BEFORE_COMMIT`
C. Sau rollback transaction do mặc định là `AFTER_ROLLBACK`
D. Sau commit thành công do mặc định là `AFTER_COMMIT`
Đáp án đúng: D

Câu 28. `@TransactionalEventListener(phase = BEFORE_COMMIT)` cho phép gì?
A. Chạy listener sau khi transaction kết thúc bất kể kết quả
B. Chạy listener trước khi transaction thực hiện commit
C. Chạy listener sau khi publisher gọi event ngoài transaction
D. Chạy listener sau khi transaction rollback thành công
Đáp án đúng: B

Câu 29. Muốn chỉ xử lý event khi transaction rollback, chọn phase nào?
A. `TransactionPhase.AFTER_COMPLETION` riêng cho rollback
B. `TransactionPhase.AFTER_COMMIT` cho lần rollback
C. `TransactionPhase.AFTER_ROLLBACK` cho lần rollback
D. `TransactionPhase.BEFORE_COMMIT` cho lần rollback
Đáp án đúng: C

Câu 30. Phase nào phù hợp để quan sát sự kết thúc transaction dù commit hay rollback?
A. `TransactionPhase.AFTER_COMMIT` nhận cả hai kết quả
B. `TransactionPhase.AFTER_COMPLETION` nhận cả hai kết quả
C. `TransactionPhase.BEFORE_COMMIT` nhận cả hai kết quả
D. `TransactionPhase.AFTER_ROLLBACK` nhận cả hai kết quả
Đáp án đúng: B

Câu 31. Nếu publish event ngoài transaction, `@TransactionalEventListener` mặc định sẽ thế nào?
A. Tạo transaction mới để listener chạy pha AFTER_COMMIT
B. Listener bị bỏ qua nếu không có transaction đang hoạt động
C. Đưa event vào hàng đợi đợi một transaction kế tiếp
D. Chạy listener như `@EventListener` ngay trên publisher
Đáp án đúng: B

Câu 32. Muốn `@TransactionalEventListener` vẫn xử lý event khi không có transaction, đặt gì?
A. Đặt `fallbackExecution = true` cho transactional listener
B. Đặt `propagation = REQUIRED` cho annotation listener
C. Đặt `readOnly = true` cho transactional listener
D. Đặt `requiresNew = true` cho annotation event listener
Đáp án đúng: A

Câu 33. Một service `@Transactional` publish event và commit sau đó; listener mặc định nào đợi commit?
A. `@EventListener` mặc định đợi AFTER_COMMIT
B. `ApplicationListener` mặc định đợi AFTER_COMMIT
C. `@Async` mặc định đợi AFTER_COMMIT
D. `@TransactionalEventListener` chờ commit thành công
Đáp án đúng: D

Câu 34. Một `@EventListener` thông thường được gọi khi service publish trong transaction; nó chạy khi nào?
A. Chạy đồng bộ lúc publish, không chờ transaction commit
B. Chỉ chạy sau AFTER_COMPLETION kể cả rollback
C. Chỉ chạy nếu listener được gắn @Transactional
D. Chỉ chạy ở AFTER_COMMIT vì có transaction mở
Đáp án đúng: A

Câu 35. Transaction bị rollback trước khi commit; listener `AFTER_COMMIT` nhận event ra sao?
A. Listener AFTER_COMMIT tự mở lại transaction bị rollback
B. Không gọi listener AFTER_COMMIT khi transaction rollback
C. Listener AFTER_COMMIT chạy nhưng đổi event thành lỗi
D. Listener AFTER_COMMIT chạy ngay khi rollback bắt đầu
Đáp án đúng: B

Câu 36. Một listener AFTER_COMMIT cần ghi DB bền vững sau khi commit gốc; nên làm gì?
A. Ghi tiếp trên transaction cũ vì chưa flush dữ liệu
B. Gắn `@Order` thấp hơn để transaction cũ commit lần nữa
C. Chỉ gọi `publishEvent` thêm lần nữa để DB tự commit
D. Dùng transaction `REQUIRES_NEW` cho thao tác ghi độc lập
Đáp án đúng: D

Câu 37. Nếu listener `BEFORE_COMMIT` đồng bộ ném exception, transaction có thể bị ảnh hưởng thế nào?
A. Commit có thể bị hủy và transaction được rollback
B. Exception chỉ đi vào async handler, không ảnh hưởng TX
C. Transaction chuyển thẳng sang AFTER_COMMIT
D. Commit đã hoàn tất nên exception không đổi trạng thái
Đáp án đúng: A

Câu 38. Muốn xử lý lỗi listener của `SimpleApplicationEventMulticaster` tập trung, dùng gì?
A. Cấu hình `PropertySourcesPlaceholderConfigurer` để nhận lỗi
B. Cấu hình `ErrorHandler` cho multicaster để nhận exception
C. Cấu hình `AuditorAware` cho multicaster để nhận exception
D. Cấu hình `TransactionSynchronization` làm error listener
Đáp án đúng: B

Câu 39. Khi yêu cầu giao event cho service ở tiến trình khác, hạn chế của Spring application event là gì?
A. Nó nhân bản event tới các service qua network
B. Nó ghi event thành Kafka record khi app shutdown
C. Event chỉ lưu chuyển trong tiến trình ứng dụng đang chạy
D. Nó đồng bộ retry và offset cho các service khác
Đáp án đúng: C

Câu 40. Để phát message ra broker đáng tin cậy cùng thay đổi DB, mẫu thiết kế nào phù hợp?
A. Transactional outbox: lưu event cùng transaction DB
B. Chỉ bắt exception của publisher rồi retry trong memory
C. Gọi broker trước khi commit và bỏ qua kết quả publish
D. Chỉ publish internal event ở listener AFTER_COMMIT
Đáp án đúng: A
