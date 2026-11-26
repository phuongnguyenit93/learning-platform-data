Câu 1. Trong Java, Thread.start() khác Thread.run() gọi trực tiếp ở điểm nào?
A. start() gọi run() ngay trên luồng đang thực thi lệnh
B. start() tạo luồng mới để chạy run() theo lịch JVM
C. run() tự tạo luồng mới rồi gọi lại hàm start()
D. run() luôn chạy song song với luồng gọi phương thức
Đáp án đúng: B

Câu 2. Khi Thread.join() trả về bình thường, Java Memory Model bảo đảm điều gì?
A. Luồng gọi join() được quyền truy cập field private của thread
B. Hành động của luồng kết thúc happens-before bước sau join()
C. Các thao tác của hai luồng tự động trở thành một transaction
D. Thread được join phải có cùng monitor với thread gọi join
Đáp án đúng: B

Câu 3. Khi gọi worker.interrupt() trên một Thread đang chạy, ý nghĩa chính là gì?
A. Buộc JVM dừng thread ngay kể cả khi đang giữ monitor
B. Tự giải phóng tất cả ReentrantLock mà thread đang giữ
C. Gửi yêu cầu ngắt để luồng xử lý theo cơ chế interrupt
D. Lập tức ném InterruptedException trên luồng gọi interrupt
Đáp án đúng: C

Câu 4. Với Thread.interrupted() được gọi trong luồng hiện tại, phát biểu nào đúng?
A. Chỉ đọc cờ interrupted của Thread được truyền như đối số
B. Đọc cờ của luồng khác nhưng không thay đổi trạng thái
C. Đọc và xóa cờ interrupted của chính luồng đang gọi
D. Đặt cờ interrupted thành true trước khi trả về kết quả
Đáp án đúng: C

Câu 5. Khi một thread đang giữ monitor trong synchronized rồi Thread.sleep(), điều gì xảy ra?
A. sleep() tạm nhả monitor và lấy lại sau khi thức dậy
B. sleep() buộc mọi thread khác rời khỏi monitor đang chờ
C. sleep() chuyển quyền giữ monitor tới thread có priority cao
D. Thread ngủ nhưng vẫn giữ monitor đã khóa trước đó
Đáp án đúng: D

Câu 6. Khi JVM chỉ còn các daemon thread đang chạy, khả năng nào phù hợp?
A. JVM phải đợi mọi daemon thread kết thúc trước khi thoát
B. JVM có thể kết thúc dù các daemon thread chưa hoàn thành
C. JVM chuyển daemon thread thành user thread trước khi thoát
D. JVM tự gọi join() cho mỗi daemon thread còn hoạt động
Đáp án đúng: B

Câu 7. Hai luồng cùng thực hiện count++ trên int field thường có rủi ro gì?
A. Phép cộng int tự bảo đảm atomicity cho mọi phép increment
B. Bộ gom rác tự khóa count trước khi increment được chạy
C. Thread scheduler bảo đảm hai lần increment luôn tuần tự
D. Read-modify-write không nguyên tử, có thể mất cập nhật
Đáp án đúng: D

Câu 8. Khi gọi synchronized(lock) trong hai thread với cùng object lock, điều gì được bảo đảm?
A. Mỗi thời điểm chỉ một thread giữ monitor của object đó
B. Hai thread được thực thi vùng critical section đồng thời
C. Chỉ thread đầu tiên mới được phép vào vùng synchronized
D. JVM tạo hai monitor độc lập dù cả hai dùng cùng object
Đáp án đúng: A

Câu 9. Một lần unlock monitor trong synchronized có quan hệ nào với lock tiếp theo trên cùng monitor?
A. Unlock happens-before lần lock tiếp theo của monitor đó
B. Unlock chỉ có nghĩa ghi dữ liệu vào file trước khi lock lại
C. Hai lần lock không có quan hệ bộ nhớ nếu khác thread
D. Unlock bắt buộc kích hoạt gọi notifyAll trên monitor đó
Đáp án đúng: A

Câu 10. Ghi vào volatile flag rồi một luồng khác đọc thấy giá trị mới cung cấp điều gì?
A. Mọi thao tác compound trên các field khác trở thành atomic
B. Các thread bị ép chạy trên một CPU core duy nhất
C. Volatile write happens-before lần volatile read phù hợp
D. Không còn cần đồng bộ cho bất kỳ collection shared nào
Đáp án đúng: C

Câu 11. Nếu int counter được khai volatile, hai thread cùng chạy counter++ có vấn đề nào?
A. counter++ được JVM chuyển thành một CAS nguyên tử
B. Vẫn có thể mất cập nhật vì increment gồm nhiều bước
C. volatile tự cấm thread khác đọc counter khi đang cộng
D. Mỗi thread tự có một bản counter rồi JVM gộp khi kết thúc
Đáp án đúng: B

Câu 12. Bảo đảm đặc biệt của final instance field trong JMM dựa trên điều kiện nào?
A. Mọi field của object đều cần khai volatile cùng lúc
B. Object được tạo đúng, không để this thoát khỏi constructor
C. Constructor phải là synchronized để JVM công bố object
D. Object bắt buộc được tạo từ enum hoặc record mới có bảo đảm
Đáp án đúng: B

Câu 13. Ở double-checked locking tạo singleton bằng lazy initialization, field instance nên khai thế nào?
A. Dùng transient để compiler cấm đọc object chưa hoàn tất
B. Dùng final cho field được gán lại trong method getInstance
C. Khai volatile để tránh công bố object chưa khởi tạo đủ
D. Dùng static nhưng không cần bảo đảm visibility với thread khác
Đáp án đúng: C

Câu 14. Khi thread gọi lock.wait() trong khối synchronized(lock), monitor được xử lý thế nào?
A. wait() nhả monitor của lock rồi giành lại trước khi trả về
B. wait() giữ nguyên monitor trong suốt thời gian chờ điều kiện
C. wait() nhả tất cả các monitor mà thread đang nắm giữ
D. wait() chỉ đánh dấu interrupted mà không tạm dừng thread
Đáp án đúng: A

Câu 15. Vì sao gọi Object.wait() nên nằm trong vòng while kiểm tra điều kiện?
A. wait() luôn thức dậy trước khi luồng khác thay đổi shared state
B. Vòng while khiến JVM tự phát notify cho các thread khác
C. Do wakeup giả hoặc predicate đổi khi giành lại lock
D. Vòng while cho phép gọi wait() ngoài synchronized block
Đáp án đúng: C

Câu 16. Khi nhiều thread chờ các điều kiện khác nhau trên cùng monitor, notifyAll() có tác dụng gì?
A. Cho phép mọi thread chờ chạy ngay khi vẫn giữ monitor đó
B. Chỉ đánh thức thread chờ lâu nhất theo thứ tự FIFO
C. Tạo thêm monitor mới để mỗi thread tiếp tục riêng biệt
D. notifyAll đánh thức waiter và buộc tranh lại monitor
Đáp án đúng: D

Câu 17. Trong ReentrantLock, Condition.await() có tác dụng chính nào?
A. Giữ lock liên tục trong lúc chờ để bảo vệ shared state
B. Tự tăng permit của Semaphore sau mỗi lần signal
C. Tạm nhả mọi lock khác mà thread đang nắm giữ
D. await tạm nhả lock của Condition rồi lấy lại khi tỉnh
Đáp án đúng: D

Câu 18. Khi code gọi lock.lock(), vì sao nên unlock trong finally?
A. Bảo đảm nhả lock cả khi phần xử lý bên trong ném exception
B. Cho phép JVM biến ReentrantLock thành monitor static
C. Để lock không thể bị thread khác lấy trước khi finally
D. Để catch block tự động rollback mọi cập nhật shared data
Đáp án đúng: A

Câu 19. Nếu cần tránh chờ lock vô hạn, ReentrantLock cung cấp lựa chọn nào?
A. lock() tự động timeout theo giá trị của Thread.sleep
B. tryLock(timeout, unit) có thể hết hạn hoặc bị ngắt
C. unlock() đăng ký timeout cho lần gọi lock tiếp theo
D. newCondition() luôn tự giới hạn thời gian chờ lock
Đáp án đúng: B

Câu 20. Hai luồng lấy lock A rồi B và B rồi A có thể gây ra sự cố gì?
A. Visibility error vì cả hai lock đều phải là volatile
B. Starvation bất khả tránh dù không có tranh chấp lock
C. Atomicity luôn được bảo đảm vì mỗi thread giữ một lock
D. Deadlock vòng chờ; nên thống nhất thứ tự lấy lock
Đáp án đúng: D

Câu 21. Với AtomicInteger, incrementAndGet() có điểm khác count++ thông thường gì?
A. Cập nhật một lần chỉ khi đang giữ synchronized monitor
B. Tăng bằng hai lần read và write không đồng bộ
C. Chỉ đọc giá trị hiện tại mà không thực hiện increment
D. Cập nhật nguyên tử và trả về giá trị sau khi tăng
Đáp án đúng: D

Câu 22. AtomicInteger.compareAndSet(expected, update) trả true khi nào?
A. CAS ghi khi giá trị hiện tại bằng expected, trả true
B. Tự thử lại vô hạn cho tới khi giá trị bằng update
C. Giá trị mới update lớn hơn expected ở mọi thời điểm
D. Giá trị current khác expected nhưng vẫn có thể ghi
Đáp án đúng: A

Câu 23. Nếu trạng thái đổi A→B→A trước khi CAS, nguy cơ nào có thể bị bỏ sót?
A. Deadlock; Thread.sleep trước CAS tự xử lý an toàn
B. ABA; dùng AtomicStampedReference để giữ version
C. Livelock; LongAdder.sum tự loại bỏ mọi thay đổi trung gian
D. Lost wakeup; Condition.signal luôn sửa được lỗi CAS
Đáp án đúng: B

Câu 24. Với bộ đếm cập nhật tranh chấp cao, LongAdder có đặc tính nào đáng nhớ?
A. Tăng throughput; sum() không phải snapshot nguyên tử
B. sum() luôn tuyến tính hóa đồng bộ cùng mọi increment
C. LongAdder.getAndIncrement trả về giá trị trước khi tăng
D. Mọi cell của LongAdder được cập nhật bằng synchronized
Đáp án đúng: A

Câu 25. ConcurrentHashMap.computeIfAbsent(key, fn) giúp gì khi nhiều thread cùng thêm key?
A. Mọi lời gọi fn được chạy đồng thời cho cùng key vắng mặt
B. Map cho phép null value để báo hàm tính chưa xong
C. Thao tác tính và gắn value cho key được thực hiện nguyên tử
D. Không cần tránh việc fn sửa đệ quy cùng map đang tính
Đáp án đúng: C

Câu 26. Với Collections.synchronizedList(list), khi dùng Iterator cần chú ý điều gì?
A. Iterator tự giữ lock wrapper suốt vòng for-each mà không cần làm gì
B. Bao iterator traversal trong synchronized trên wrapper list
C. Chỉ gọi list.size() trước vòng lặp là đủ tránh race
D. Iterator dùng snapshot bất biến như CopyOnWriteArrayList
Đáp án đúng: B

Câu 27. Trong tình huống đọc rất nhiều và ghi hiếm, đặc điểm nào hợp với CopyOnWriteArrayList?
A. Iterator khóa toàn bộ list cho đến khi duyệt xong
B. Mọi lần add sửa trực tiếp mảng mà iterator đang dùng
C. Iterator dùng snapshot; sửa thường tạo mảng mới
D. Một lệnh set giữ chung backing array cho mọi snapshot
Đáp án đúng: C

Câu 28. Khi BlockingQueue đầy và thread gọi put(element), hành vi thường là gì?
A. put() lập tức trả false mà không block như offer
B. put() tự mở rộng mọi queue bất kể giới hạn dung lượng
C. put() ghi đè phần tử đầu tiên nếu queue đã đầy
D. put() chờ có chỗ trống hoặc bị interrupt trong lúc đợi
Đáp án đúng: D

Câu 29. Semaphore(3) có thể được dùng để giới hạn điều gì?
A. Đảm bảo đúng ba Java thread tồn tại trong cả JVM
B. Đảm bảo ba task chạy trên ba CPU core tách biệt
C. Tạo một monitor riêng cho mỗi một permit đã cấp
D. Tối đa ba permit được cấp đồng thời cho các tác vụ
Đáp án đúng: D

Câu 30. Khi CountDownLatch(2) được dùng làm điểm chờ, await() trả về bình thường khi nào?
A. Có hai thread gọi await đồng thời dù không countDown
B. Thread gọi await được interrupt trong khi đang chờ
C. await() trả về sau khi countDown làm bộ đếm về 0
D. Bộ đếm được reset tự động sau lần đếm đầu tiên
Đáp án đúng: C

Câu 31. CyclicBarrier khác CountDownLatch ở đặc điểm nào nổi bật?
A. Barrier chỉ hỗ trợ một lần count xuống 0 rồi không reset
B. Barrier có thể tái dùng cho nhiều vòng khi đủ số parties
C. Barrier bắt buộc từng task gọi countDown thay cho await
D. Barrier không có khả năng báo lỗi khi một party bị interrupt
Đáp án đúng: B

Câu 32. ThreadLocal dùng trong thread pool có rủi ro nào nếu quên remove() sau task?
A. Dữ liệu có thể còn trên worker thread được tái sử dụng
B. ThreadLocal tự chuyển dữ liệu sang mọi worker sau mỗi task
C. Executor tự đóng ThreadLocal trước mọi lần lấy task mới
D. Mỗi lần submit tạo một thread mới nên không còn dữ liệu
Đáp án đúng: A

Câu 33. Với ExecutorService.submit(Callable<T>), cách quan sát lỗi task nào phù hợp?
A. submit() ném lại exception của task ngay trên thread gọi submit
B. Future.get() có thể ném ExecutionException chứa lỗi từ task
C. Future.isDone() tự ném exception gốc khi task kết thúc
D. Callable.call() tự gọi uncaughtExceptionHandler của thread submit
Đáp án đúng: B

Câu 34. Khi gọi Future.get() mà tác vụ chưa hoàn thành, chuyện gì thường xảy ra?
A. get() trả null ngay nếu Future chưa hoàn thành thực thi
B. get() hủy tác vụ sau một lần polling không tìm thấy kết quả
C. get() tự chuyển mọi Runnable thành CompletableFuture đã xong
D. Thread gọi get() chờ kết quả hoặc bị interrupt khi đang đợi
Đáp án đúng: D

Câu 35. ExecutorService.shutdown() thông thường có ý nghĩa nào?
A. Ngừng nhận task mới và tiếp tục xử lý task đã nhận
B. Ngắt tất cả worker đang chạy và xóa mọi task khỏi queue
C. Trả về danh sách mọi task chưa bắt đầu thực thi
D. Dừng thread gọi shutdown cho tới khi các task kết thúc
Đáp án đúng: A

Câu 36. ExecutorService.shutdownNow() được mô tả chính xác nhất thế nào?
A. Bảo đảm mọi task đang chạy dừng ngay và resource được giải phóng
B. Đợi task hoàn tất rồi mới ngăn submit task tiếp theo
C. Thử ngắt task đang chạy và trả về những task còn chờ
D. Bắt buộc trả null nếu task queue đã có nhiều phần tử
Đáp án đúng: C

Câu 37. Nếu gọi Future.cancel(true) trên task đang chạy, nhận định nào phù hợp?
A. cancel(true) có thể ngắt; task phải hợp tác để dừng
B. JVM chắc chắn giết thread ngay dù task giữ monitor
C. Bắt buộc thread task phải trả về một kết quả mặc định
D. cancel(true) chỉ gắn cờ Future, không yêu cầu ngắt task
Đáp án đúng: A

Câu 38. Trong ThreadPoolExecutor có queue giới hạn và đạt ngưỡng bão hòa, tình huống nào có thể xảy ra?
A. RejectedExecutionHandler được gọi khi không thể nhận thêm task
B. Executor tự mở thêm thread vượt maximumPoolSize không giới hạn
C. Queue bị mở rộng vô hạn dù là ArrayBlockingQueue cố định
D. Executor tự chờ shutdown trước khi xử lý task bị từ chối
Đáp án đúng: A

Câu 39. ThreadPoolExecutor.CallerRunsPolicy xử lý task bị từ chối như thế nào khi executor còn chạy?
A. Executor bỏ qua task bị từ chối và ghi lại warning mặc định
B. Tạo virtual thread cho task dù cấu hình pool thread nền
C. Task được đưa về đầu queue bất kể queue đã đầy
D. Task chạy ở thread gọi execute, tạo backpressure
Đáp án đúng: D

Câu 40. CompletableFuture.supplyAsync(supplier) không truyền Executor thường dùng executor nào?
A. Dùng ExecutorService mới có đúng một thread cho từng call
B. Thông thường dùng ForkJoinPool.commonPool làm executor mặc định
C. Dùng thread đang gọi như đường chạy đồng bộ mặc định
D. Dùng Executor của mỗi đối tượng CompletableFuture đầu tiên
Đáp án đúng: B

Câu 41. Khi callback trả về CompletableFuture<U>, muốn nối chuỗi mà không lồng future nên chọn gì?
A. thenApply để tự flatten CompletableFuture<U> thành U
B. thenAccept để trả lại CompletableFuture<U> cho caller
C. thenCompose để làm phẳng stage bất đồng bộ kế tiếp
D. whenComplete để thay thế mọi result bằng giá trị U
Đáp án đúng: C

Câu 42. Với hai CompletableFuture độc lập, thenCombine thường cho phép điều gì?
A. Ghép hai kết quả sau khi cả hai stage hoàn thành bình thường
B. Bắt buộc future thứ hai chỉ bắt đầu sau future thứ nhất
C. Chạy một trong hai stage và hủy stage còn lại lập tức
D. Tự lấy kết quả future hoàn thành trước mà bỏ future khác
Đáp án đúng: A

Câu 43. Khi stage trong CompletableFuture hoàn thành ngoại lệ, exceptionally(fn) dùng thế nào?
A. Luôn ném lại exception mà không cho tạo fallback
B. exceptionally cung cấp fallback khi stage thất bại
C. Hủy CompletableFuture cha ngay cả khi đã hoàn tất đúng
D. Biến checked exception thành thread interrupt mặc định
Đáp án đúng: B

Câu 44. CompletableFuture.allOf(f1, f2) trả về dạng kết quả nào khi thành công?
A. CompletableFuture<List<T>> chứa mọi kết quả theo thứ tự
B. Future<T> chỉ chứa kết quả của stage hoàn thành sau cùng
C. Trả CompletableFuture<Void>; lấy result từ future riêng
D. Stream<T> phát kết quả ngay sau từng future hoàn thành
Đáp án đúng: C

Câu 45. Khi dùng CompletableFuture.orTimeout(timeout, unit), timeout có hiệu ứng nào?
A. Tự gửi interrupt tới mọi worker đang chạy task gốc
B. Trả một giá trị mặc định cùng kiểu T khi quá hạn
C. Hủy executor dùng chung và tất cả task đang chờ
D. Chưa xong sẽ hoàn tất lỗi với TimeoutException
Đáp án đúng: D

Câu 46. Virtual thread trong JDK hiện đại phù hợp nhất cho nhóm công việc nào?
A. Nhiều tác vụ blocking I/O cần số lượng thread lớn
B. Tăng tốc tính toán CPU-bound nhờ ưu tiên mọi virtual thread
C. Thay thế khóa dữ liệu vì virtual thread không thể bị race
D. Bảo đảm mọi request đều được xử lý bởi một OS thread riêng
Đáp án đúng: A

Câu 47. Executors.newVirtualThreadPerTaskExecutor() thực hiện đặc điểm nào?
A. Tạo một pool cố định virtual thread rồi tái sử dụng thread
B. Tạo platform thread mới cho mỗi task và tránh virtual thread
C. Tạo một virtual thread phục vụ đồng thời tất cả các task
D. Tạo virtual thread mới cho mỗi task được executor nhận
Đáp án đúng: D

Câu 48. Để kiểm thử race condition giữa hai tác vụ, cách tiếp cận nào có ích?
A. Chỉ chạy test một luồng rồi kết luận không có race
B. Giảm số iteration để lịch chạy không làm test chập chờn
C. Dùng latch căn lúc chạy, lặp test và kiểm tra invariant
D. Dựa vào Thread.sleep cố định để chứng minh thread-safe
Đáp án đúng: C
