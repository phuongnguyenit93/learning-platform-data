Câu 01. Trong Spring, `TaskExecutor` cung cấp thao tác cơ bản nào để giao một `Runnable`?
A. Gọi `invokeAll(Collection)` để thực thi task
B. Gọi `publishEvent(Runnable)` để thực thi task
C. Gọi `schedule(Runnable, Trigger)` để thực thi task
D. Gọi `execute(Runnable)` để executor xử lý task
Đáp án đúng: D

Câu 02. `ThreadPoolTaskExecutor` phù hợp khi cần hành vi nào khi chạy nhiều task?
A. Tạo thread riêng mỗi lần mà không giữ lại worker
B. Tái sử dụng các worker thread trong một pool
C. Thực hiện task trực tiếp trên thread gọi execute
D. Chỉ kích hoạt task khi cron trigger đến hạn
Đáp án đúng: B

Câu 03. Đặc điểm chính của `SimpleAsyncTaskExecutor` ở cấu hình thread nền tảng là gì?
A. Chạy task đồng bộ trên thread submit của service
B. Tái dùng các worker cốt lõi của ThreadPoolExecutor
C. Tạo thread mới cho từng task, không tái dùng pool
D. Xếp tác vụ vào hàng đợi của fixed worker pool
Đáp án đúng: C

Câu 04. Nếu muốn task chạy ngay trên thread của người gọi để đơn giản hóa test, dùng gì?
A. `SimpleAsyncTaskExecutor` thực thi Runnable trên caller thread
B. `VirtualThreadTaskExecutor` thực thi trên caller thread
C. `SyncTaskExecutor` thực thi Runnable trên caller thread
D. `ThreadPoolTaskExecutor` thực thi Runnable trên caller thread
Đáp án đúng: C

Câu 05. Với `ThreadPoolTaskExecutor` và queue rất lớn, vì sao `maxPoolSize` ít phát huy tác dụng?
A. Task có thể vào queue sau khi pool đạt core size
B. Task bị reject ngay khi worker đạt core pool size
C. Pool ưu tiên tăng đến max trước khi enqueue task
D. Core threads kết thúc khi queue chưa được lấy hết
Đáp án đúng: A

Câu 06. Trong `ThreadPoolTaskExecutor`, đặt `queueCapacity = 0` thường làm thay đổi gì?
A. Dùng handoff trực tiếp, không đệm task vào queue
B. Bỏ giới hạn max pool size và retry đến khi nhận
C. Tạo một hàng đợi vô hạn giữ task đang chờ
D. Gộp các Runnable vào một batch trước khi chạy
Đáp án đúng: A

Câu 07. Khi executor bão hòa, `CallerRunsPolicy` thường áp dụng điều gì?
A. Bỏ task vừa submit và tiếp tục chạy các task cũ
B. Loại task cũ nhất trong queue để nhận task mới
C. Đẩy task sang caller thread nếu executor còn hoạt động
D. Ném `RejectedExecutionException` tại thời điểm reject
Đáp án đúng: C

Câu 08. Nếu chọn `ThreadPoolExecutor.AbortPolicy`, task bị từ chối được phản ánh ra sao?
A. Ném `RejectedExecutionException` khi executor từ chối
B. Thực thi Runnable trên thread gửi task cho executor
C. Bỏ Runnable bị reject mà không thông báo cho caller
D. Loại task đợi lâu nhất trước khi thêm Runnable mới
Đáp án đúng: A

Câu 09. Để tránh ứng dụng giữ vô hạn task khi tốc độ đến vượt tốc độ xử lý, cách nào hợp lý?
A. Đặt task timeout dài để task chờ lâu hơn
B. Tăng queue thành vô hạn để tránh tín hiệu reject
C. Giữ pool core nhỏ rồi bỏ các metric hàng đợi
D. Giới hạn queue và xử lý rejection/backpressure
Đáp án đúng: D

Câu 10. `TaskDecorator` trong `ThreadPoolTaskExecutor` hữu ích chủ yếu để làm gì?
A. Bọc task tại executor để truyền MDC hoặc trace
B. Chuyển các tác vụ thành cron job trước khi submit
C. Giảm corePoolSize khi TaskExecutor đóng bean
D. Tăng kích thước queue khi lượng Runnable vượt đỉnh
Đáp án đúng: A

Câu 11. Khi `@Async` đổi thread, cách xử lý context lưu bằng `ThreadLocal` nào an toàn hơn?
A. Tin vào ThreadLocal của cha tự có ở thread worker
B. Đặt thêm `@Order` để MDC chuyển cùng listener
C. Truyền context qua wrapper hoặc decorator có kiểm soát
D. Tăng queueCapacity để request context sống xuyên thread
Đáp án đúng: C

Câu 12. Muốn Spring xử lý các method `@Async` qua cơ chế proxy, cần kích hoạt gì?
A. Dùng `@EnableAsync` trên lớp cấu hình tương ứng
B. Dùng `@EnableAspectJAutoProxy` mà không bật async
C. Dùng `@EnableScheduling` trên cấu hình executor
D. Dùng `@EnableTransactionManagement` để bật async
Đáp án đúng: A

Câu 13. Vì sao `this.sendEmail()` trong cùng bean thường không kích hoạt `@Async` trên method?
A. Bean sẽ tự chuyển lời gọi this sang BeanFactory
B. Self-invocation không đi qua Spring proxy xử lý async
C. Spring trì hoãn lời gọi this đến sau context refresh
D. Lời gọi nội bộ tự tạo task trên một pool riêng biệt
Đáp án đúng: B

Câu 14. Method `@Async` muốn caller kết hợp kết quả qua completion stages, kiểu trả về nào phù hợp?
A. `Result` để Spring tự bọc giá trị thành Future
B. `Optional<Result>` để proxy tự đổi thành async result
C. `ResponseEntity<Result>` để proxy đợi task hoàn thành
D. `CompletableFuture<Result>` trả kết quả từ async
Đáp án đúng: D

Câu 15. Nếu có nhiều executor bean, cách chỉ định bean `ioExecutor` cho method async là gì?
A. Đặt `@Order("ioExecutor")` trên method async
B. Đặt `@Scheduled("ioExecutor")` trên method async
C. Đặt `@Primary("ioExecutor")` trên method async
D. Đặt `@Async("ioExecutor")` để chọn executor theo tên
Đáp án đúng: D

Câu 16. Với Spring async qua proxy, việc gắn `@Async` lên private method thường gặp vấn đề nào?
A. Private method được thực thi qua TaskScheduler mặc định
B. Private method không được proxy-based advice intercept
C. Private method tự có transaction mới khi được gọi nội bộ
D. Private method sẽ tự được mở thành public lúc runtime
Đáp án đúng: B

Câu 17. Đối với `@Async` method trả `void`, exception không bắt nên được xử lý ở đâu?
A. Qua `CompletableFuture.exceptionally` ở caller thread
B. Qua `AsyncUncaughtExceptionHandler` đã được cấu hình
C. Qua `@ControllerAdvice` như exception của HTTP request
D. Qua `TaskScheduler.schedule` trên từng CompletableFuture
Đáp án đúng: B

Câu 18. Trong `CompletableFuture`, operator nào đọc cả kết quả thành công lẫn Throwable?
A. `thenRun(() -> ...)` chỉ xử lý hai trạng thái
B. `thenApply(value -> ...)` chỉ xử lý hai trạng thái
C. `handle((value, error) -> ...)` xử lý cả hai trạng thái
D. `thenAccept(value -> ...)` chỉ xử lý hai trạng thái
Đáp án đúng: C

Câu 19. Khi function của một stage trả tiếp `CompletableFuture<U>`, nên dùng gì để không lồng stage?
A. `thenAccept` nối stage rồi trả về giá trị U
B. `whenComplete` tạo Future<U> mới từ Future<U>
C. `thenCompose` nối và làm phẳng các Future
D. `thenApply` tự làm phẳng stage Future nhiều tầng
Đáp án đúng: C

Câu 20. Muốn chạy tiếp sau khi ba `CompletableFuture` đều hoàn tất, API nào phù hợp?
A. `CompletableFuture.anyOf(a, b, c)` đợi cả ba
B. `CompletableFuture.allOf(a, b, c)` đợi cả ba
C. `a.thenApply(fn)` đợi cả ba future kết thúc
D. `a.complete(value)` đợi cả ba future kết thúc
Đáp án đúng: B

Câu 21. Với `CompletableFuture` bị lỗi, API nào tạo kết quả dự phòng dựa trên exception?
A. `whenComplete((v,e) -> fallback)` đổi giá trị lỗi
B. `thenApply(value -> fallback)` phục hồi sau lỗi
C. `thenAccept(value -> fallback)` thay kết quả lỗi
D. `exceptionally(ex -> fallback)` phục hồi giá trị
Đáp án đúng: D

Câu 22. Khi gọi `future.orTimeout(2, SECONDS)` trên `CompletableFuture`, điều gì cần nhớ về công việc nền?
A. Future lỗi timeout nhưng tác vụ nền vẫn có thể chạy
B. Timeout hoàn thành Future với giá trị mặc định
C. Timeout đóng executor chứa các pending tasks
D. Timeout sẽ ngắt thread nền ngay khi đến hạn
Đáp án đúng: A

Câu 23. Muốn `ThreadPoolTaskExecutor` cố gắng hoàn tất task đang đợi khi context shutdown, đặt gì?
A. `setAllowCoreThreadTimeOut(true)` cho executor
B. `setPrestartAllCoreThreads(true)` cho executor
C. `setStrictEarlyShutdown(true)` cho executor
D. `setWaitForTasksToCompleteOnShutdown(true)` trên executor
Đáp án đúng: D

Câu 24. Đối với `Future` từ `ExecutorService.submit`, lời gọi `cancel(true)` trên task đang chạy có nghĩa gì?
A. Đóng executor và ngắt các task đang chạy
B. Đảm bảo task đã dừng và rollback giao dịch
C. Chỉ hủy kết quả Future sau khi task hoàn thành
D. Yêu cầu interrupt; tác vụ phải hợp tác để dừng
Đáp án đúng: D

Câu 25. Muốn Spring nhận các method `@Scheduled` trong bean, bật cấu hình nào?
A. `@EnableTransactionManagement` trên cấu hình
B. `@EnableScheduling` trên cấu hình ứng dụng
C. `@EnableAspectJAutoProxy` thay scheduler registration
D. `@EnableAsync` trên cấu hình application context
Đáp án đúng: B

Câu 26. `@Scheduled(fixedDelay = 5000)` quy định khoảng cách giữa hai lần chạy thế nào?
A. Đếm 5 giây từ khi lần chạy trước bắt đầu
B. Đợi 5 giây sau khi lần chạy trước kết thúc
C. Chạy vào giây thứ năm của mỗi phút theo cron
D. Chạy lại 5 lần nếu task trước trả lỗi
Đáp án đúng: B

Câu 27. `@Scheduled(fixedRate = 5000)` dùng mốc nào để lên lịch lặp?
A. Nhịp 5 giây theo thời điểm bắt đầu của lịch
B. Nhịp 5 giây tính từ khi event cuối được publish
C. Nhịp 5 giây tính từ lúc lần trước đã kết thúc
D. Nhịp 5 giây tính từ commit của transaction trước
Đáp án đúng: A

Câu 28. Trong `@Scheduled(cron = ...)`, thuộc tính nào chọn múi giờ tính cron?
A. `locale = "Asia/Ho_Chi_Minh"` định múi giờ cron
B. `zone = "Asia/Ho_Chi_Minh"` định múi giờ cron
C. `clock = "Asia/Ho_Chi_Minh"` định múi giờ cron
D. `timeZone = "Asia/Ho_Chi_Minh"` định múi giờ cron
Đáp án đúng: B

Câu 29. Đối với `@Scheduled(initialDelay = 10000, fixedDelay = 3000)`, điều gì đúng?
A. Task đợi khoảng 3 giây trước lần chạy đầu
B. Task chạy ngay rồi chỉ đợi 10 giây cho lần hai
C. Task chạy theo cron sau khi chờ 3 giây ban đầu
D. Task đợi khoảng 10 giây trước lần chạy đầu
Đáp án đúng: D

Câu 30. Muốn các scheduled job độc lập có worker pool, bean nào của Spring phù hợp?
A. `ApplicationEventPublisher` chạy cron job trên pool
B. `SyncTaskExecutor` chạy cron job trên pool
C. `ThreadPoolTaskScheduler` dùng pool thực thi lịch
D. `SimpleAsyncTaskExecutor` giữ cron scheduler pool
Đáp án đúng: C

Câu 31. Với nhiều scheduled job có tác vụ chờ I/O, cấu hình nào giúp các job khác vẫn được chạy?
A. Đặt `initialDelay` của các job bằng không
B. Giữ một scheduler thread cho các job I/O dài
C. Tăng `poolSize` của scheduler để có thêm worker
D. Đặt `fixedDelay` của các job trùng nhau
Đáp án đúng: C

Câu 32. Nếu cùng method có hai annotation `@Scheduled` và pool đủ thread, cần lưu ý gì?
A. Spring tự gộp cả hai trigger thành một lịch
B. Spring chỉ giữ annotation được khai báo trước
C. Spring chỉ đăng ký lịch thứ hai sau khi restart
D. Hai lịch độc lập có thể chạy trùng thời điểm
Đáp án đúng: D

Câu 33. Với `SimpleAsyncTaskScheduler` dựa vào virtual threads, loại lịch nào cần thận trọng khi task chặn lâu?
A. Fixed-delay chạy trên scheduler thread chung
B. Initial-delay tự bỏ chạy các fixed-delay dài
C. Fixed-rate chạy trực tiếp trong transaction caller
D. Cron tự đổi task blocking sang asynchronous API
Đáp án đúng: A

Câu 34. Spring cung cấp executor nào tạo virtual thread cho mỗi task trên JDK hỗ trợ?
A. `SyncTaskExecutor` tạo virtual thread trên mỗi lần gọi
B. `ConcurrentTaskScheduler` tạo virtual thread mỗi task
C. `ThreadPoolTaskExecutor` là virtual thread pool mặc định
D. `VirtualThreadTaskExecutor` tạo virtual thread mỗi task
Đáp án đúng: D

Câu 35. Virtual threads đặc biệt hữu ích khi loại workload nào chiếm phần lớn thời gian?
A. Task chỉ tính toán CPU nặng liên tục trên mỗi core
B. Task nắm synchronized monitor trong phần lớn thời gian
C. Task chờ I/O blocking với nhiều phiên đồng thời
D. Task cần thread pool số lượng nhỏ và cố định
Đáp án đúng: C

Câu 36. Vì sao virtual threads vẫn cần giới hạn concurrency khi gọi database?
A. Connection pool DB vẫn có giới hạn tài nguyên riêng
B. Executor tự mở rộng max connections trên database
C. Virtual threads cung cấp connection DB không giới hạn
D. Virtual threads tự giảm số transaction đang mở về một
Đáp án đúng: A

Câu 37. Với `@Async` và transaction theo `ThreadLocal`, kết luận nào chính xác?
A. Thread async không tự thừa hưởng transaction của caller
B. Thread async tự rollback transaction gốc khi method lỗi
C. Thread async nhận transaction nhờ dùng chung bean service
D. Thread async mặc định nối chung transaction JDBC của caller
Đáp án đúng: A

Câu 38. Singleton service có biến `int count` được nhiều task gọi `count++`; cách nào an toàn hơn?
A. Dùng `volatile int count` rồi vẫn gọi `count++` như cũ
B. Dùng `AtomicInteger.incrementAndGet()` để tăng atomic
C. Dùng `@Primary` trên service để tránh tranh chấp ghi
D. Dùng `@Order` trên method để tuần tự hóa các task
Đáp án đúng: B

Câu 39. Vì sao test @Async không nên chỉ dùng `Thread.sleep(50)` để chờ kết quả?
A. Giả định scheduler chạy task trong vài mili giây
B. Tăng sleep dài hơn để đảm bảo các máy chạy giống nhau
C. Đợi bằng Future hoặc latch kèm timeout rõ ràng
D. Đọc kết quả ngay vì @Async chạy cùng test thread
Đáp án đúng: C

Câu 40. Để kiểm soát sự cố quá tải executor trong production, tín hiệu nào nên theo dõi?
A. Chỉ thời gian khởi động JVM lúc deploy mới
B. Queue depth, active threads và số task bị reject
C. Chỉ tên bean được gắn `@Async` trong codebase
D. Chỉ số lượng class được Spring component scan
Đáp án đúng: B
