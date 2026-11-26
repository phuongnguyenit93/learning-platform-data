Bạn giải thích concurrency khác parallelism trong một chương trình Java có nhiều tác vụ như thế nào?
Bạn phân biệt process với Thread về bộ nhớ chia sẻ, tài nguyên và phạm vi lỗi ra sao?
Bạn mô tả các trạng thái NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING và TERMINATED trong Thread.State như thế nào?
Bạn sẽ giải thích sự khác nhau giữa gọi Thread.start và gọi trực tiếp Thread.run như thế nào?
Bạn phân biệt Runnable với Callable về kiểu kết quả và cơ chế báo exception ra sao?
Bạn sẽ lựa chọn Runnable, Callable hoặc lambda khi xây tác vụ chạy song song theo yêu cầu nào?
Bạn mô tả thread scheduling của JVM và hệ điều hành ảnh hưởng thứ tự thực thi như thế nào?
Bạn phân tích vì sao thread priority không thể được dùng để bảo đảm thứ tự xử lý giữa các threads ra sao?
Bạn sẽ giải thích tại sao Thread.sleep không bảo đảm chính xác thời điểm thread được chạy lại như thế nào?
Bạn phân biệt Thread.sleep với Thread.yield về ý nghĩa và bảo đảm scheduling như thế nào?
Bạn sẽ xác định cách Thread.join phối hợp để thread gọi chờ một thread khác kết thúc ra sao?
Bạn mô tả Thread.isAlive giúp kiểm tra điều gì và vì sao không thay thế một cơ chế đồng bộ hóa ra sao?
Bạn phân biệt daemon thread với user thread về ảnh hưởng tới thời điểm JVM có thể kết thúc như thế nào?
Bạn sẽ cân nhắc dùng Thread.setDaemon cho tác vụ bảo trì khi có nguy cơ công việc chưa hoàn thành ra sao?
Bạn phân tích vì sao một thread có tên hữu ích giúp chẩn đoán sự cố mà không thay đổi tính đúng đắn đồng thời như thế nào?
Bạn sẽ đặt UncaughtExceptionHandler cho thread để ghi nhận lỗi không được xử lý theo chính sách nào?
Bạn phân biệt exception trong một Thread độc lập với exception từ Future của ExecutorService ra sao?
Bạn sẽ tổ chức vòng đời thread do ứng dụng tự tạo để không rò thread sau khi hoàn tất công việc như thế nào?
Bạn mô tả Thread.interrupt là tín hiệu hợp tác thay vì thao tác buộc dừng thread ngay lập tức như thế nào?
Bạn sẽ xử lý InterruptedException khi một tác vụ đang sleep hoặc wait mà có yêu cầu hủy ra sao?
Bạn phân tích vì sao bắt InterruptedException rồi bỏ qua hoàn toàn có thể khiến ứng dụng không shutdown được như thế nào?
Bạn sẽ xác định khi nào nên khôi phục interrupt flag qua Thread.currentThread().interrupt như thế nào?
Bạn phân biệt Thread.interrupted với isInterrupted về ảnh hưởng lên trạng thái interrupt flag ra sao?
Bạn sẽ thiết kế vòng lặp tính toán dài thường xuyên kiểm tra interruption mà không phụ thuộc sleep như thế nào?
Bạn mô tả Thread.onSpinWait có thể được dùng trong một vòng spin được thiết kế cẩn thận theo mục đích nào?
Bạn phân tích vì sao busy waiting vô hạn làm lãng phí CPU và có thể cản trở các tác vụ khác ra sao?
Bạn sẽ lựa chọn thread-per-request hay task scheduling qua executor khi số kết nối tăng cao như thế nào?
Bạn phân biệt ThreadLocal state với biến local nằm trên call stack khi nhiều lời gọi cùng thread ra sao?
Bạn sẽ đánh giá tác động của thread context class loader tới ứng dụng đa thread có module hoặc plugin như thế nào?
Bạn giải thích Java Memory Model (JMM) mô tả những bảo đảm nào về visibility và ordering giữa các threads?
Bạn phân biệt data race với race condition theo tác động tới tính đúng đắn như thế nào?
Bạn sẽ xác định tại sao một field được sửa bởi thread A chưa chắc được thread B nhìn thấy ngay ra sao?
Bạn mô tả happens-before relation cho phép suy luận tính hiển thị của các writes như thế nào?
Bạn phân biệt program order trong một thread với ordering mà các threads khác có thể quan sát như thế nào?
Bạn sẽ giải thích vì sao compiler và CPU có thể reorder memory operations mà vẫn giữ semantics được phép như thế nào?
Bạn mô tả monitor unlock và monitor lock tương ứng tạo happens-before edge trong trường hợp nào?
Bạn sẽ giải thích Thread.start tạo happens-before relation giữa actions trước start và actions của thread mới ra sao?
Bạn phân biệt Thread.join thành công với việc chỉ kiểm tra isAlive khi cần visibility sau khi thread kết thúc như thế nào?
Bạn sẽ xác định quan hệ happens-before của volatile write và volatile read cùng một biến như thế nào?
Bạn mô tả volatile field giải quyết vấn đề visibility và một phần ordering nhưng không tự cung cấp mutual exclusion ra sao?
Bạn phân tích vì sao thao tác tăng volatile int bằng phép cộng rồi gán vẫn có thể làm mất update như thế nào?
Bạn sẽ quyết định khi nào volatile boolean đủ cho shutdown flag và khi nào cần AtomicBoolean ra sao?
Bạn phân biệt atomicity của việc đọc/ghi một biến với atomicity của chuỗi nhiều thao tác trên state như thế nào?
Bạn sẽ minh họa lost update khi hai threads cùng thực hiện read-modify-write trên counter như thế nào?
Bạn phân tích vì sao kiểm tra rồi hành động trên hai fields độc lập có thể vi phạm invariant dù mỗi field đều volatile ra sao?
Bạn sẽ xác định cách synchronized bảo vệ đồng thời visibility và mutual exclusion cho một shared invariant như thế nào?
Bạn mô tả final field semantics hỗ trợ safe initialization của immutable object trong những điều kiện nào?
Bạn phân tích nguy cơ tham chiếu this thoát ra khỏi constructor làm hỏng kỳ vọng về final field visibility như thế nào?
Bạn sẽ thiết kế safe publication qua static initialization, volatile reference hoặc lock như thế nào?
Bạn phân biệt immutable object với một mutable object chỉ được công bố qua volatile reference về mức bảo vệ state ra sao?
Bạn sẽ đánh giá tại sao volatile reference tới HashMap không làm các thao tác cập nhật HashMap trở thành thread-safe như thế nào?
Bạn sẽ thiết kế thread confinement để loại bỏ shared mutable state không cần thiết theo cách nào?
Bạn mô tả ThreadLocal giúp mỗi thread giữ trạng thái độc lập nhưng không thay thế synchronization khi dữ liệu thực sự được chia sẻ ra sao?
Bạn phân tích nguy cơ ThreadLocal không được remove trên thread pool dẫn tới rò hoặc truyền nhầm dữ liệu giữa tasks như thế nào?
Bạn sẽ xác định khi nào dùng AtomicReference để công bố snapshot cấu hình mới thay vì sửa nhiều fields tại chỗ ra sao?
Bạn phân biệt stale read với torn read khi đánh giá vấn đề memory visibility theo đặc điểm type và JMM nào?
Bạn sẽ giải thích vì sao dùng Thread.sleep trong test không tạo một happens-before guarantee giữa producer và consumer như thế nào?
Bạn sẽ tạo phép thử visibility sai do không có synchronization rồi xác định vì sao kết quả không thể dự đoán ổn định ra sao?
Bạn phân tích vì sao chạy thành công hàng triệu lần không chứng minh một chương trình có data race là đúng ra sao?
Bạn sẽ dùng sơ đồ happens-before để xem xét một đoạn code có shared state mà không dựa vào trực giác về tốc độ threads như thế nào?
Bạn giải thích synchronized instance method dùng monitor nào để bảo vệ critical section như thế nào?
Bạn phân biệt synchronized static method với synchronized instance method về đối tượng monitor ra sao?
Bạn sẽ mô tả synchronized block khóa trên một object riêng thay vì this theo ảnh hưởng đến phạm vi lock như thế nào?
Bạn phân tích vì sao synchronized trên một String interned hoặc object public có thể gây lock coupling không mong muốn ra sao?
Bạn sẽ chọn private final lock object để giới hạn ai có thể tranh chấp monitor theo tiêu chí nào?
Bạn phân biệt mutual exclusion với điều kiện chờ một trạng thái nghiệp vụ trở thành hợp lệ như thế nào?
Bạn mô tả reentrancy của intrinsic monitor cho phép một thread vào lại synchronized method như thế nào?
Bạn sẽ giải thích vì sao synchronized có thể gây contention khi critical section bao gồm I/O chậm ra sao?
Bạn sẽ quyết định phần code nào cần nằm trong critical section để giữ invariant nhưng giảm lock duration như thế nào?
Bạn phân tích nguy cơ sử dụng hai locks bảo vệ các fields liên quan khiến không giữ được invariant xuyên suốt ra sao?
Bạn sẽ mô tả Object.wait giải phóng monitor của object đang được chờ theo cơ chế nào?
Bạn phân biệt Object.wait với Thread.sleep về việc release monitor khi chờ ra sao?
Bạn sẽ xác định điều kiện bắt buộc để gọi Object.wait, notify hoặc notifyAll mà không gặp IllegalMonitorStateException như thế nào?
Bạn giải thích vì sao wait phải nằm trong vòng while kiểm tra lại điều kiện thay vì chỉ dùng if như thế nào?
Bạn phân biệt spurious wakeup với việc condition trở thành true do thread khác thay đổi state ra sao?
Bạn sẽ dùng notifyAll thay notify khi nhiều nhóm threads chờ các điều kiện khác nhau theo lý do nào?
Bạn phân tích rủi ro lost notification khi chương trình chờ và phát tín hiệu mà không bảo vệ condition state đúng cách ra sao?
Bạn mô tả producer-consumer bounded buffer với wait/notifyAll giữ điều kiện đầy và rỗng như thế nào?
Bạn sẽ xử lý InterruptedException trong vòng wait mà không để dữ liệu chung ở trạng thái cập nhật dở như thế nào?
Bạn phân biệt monitor ownership với việc một thread đơn thuần giữ reference tới lock object như thế nào?
Bạn sẽ xác định tại sao một lời gọi synchronized đi vào BLOCKED khác thread WAITING vì Object.wait như thế nào?
Bạn phân tích deadlock khi hai threads lấy hai monitors theo thứ tự ngược nhau như thế nào?
Bạn sẽ áp dụng global lock ordering để tránh deadlock trong thao tác chuyển tiền giữa hai đối tượng như thế nào?
Bạn phân biệt deadlock với livelock và starvation theo triệu chứng hệ thống nào?
Bạn sẽ thiết kế locking policy không gọi callback do bên ngoài cung cấp khi đang giữ monitor như thế nào?
Bạn phân tích rủi ro gọi overridable method hoặc listener bên trong synchronized block khiến khóa bị giữ quá lâu ra sao?
Bạn sẽ đánh giá khi nào thread-safe wrapper có lock ngoài không đủ vì caller thực hiện nhiều thao tác phải atomic như thế nào?
Bạn sẽ kiểm thử một monitor-based queue với nhiều producer và consumer để phát hiện lost wakeup như thế nào?
Bạn sẽ đánh giá hạn chế của monitor khi muốn timeout, interruptibility và nhiều condition queues như thế nào?
Bạn phân biệt ReentrantLock với intrinsic synchronized về tryLock, fairness và interruptible acquisition như thế nào?
Bạn sẽ viết cơ chế lock/unlock an toàn bằng try/finally để không bỏ khóa khi exception xảy ra ra sao?
Bạn phân tích vì sao quên unlock trong nhánh lỗi có thể làm các threads khác chờ vô hạn như thế nào?
Bạn sẽ lựa chọn ReentrantLock.lockInterruptibly khi một thread cần hủy trong lúc chờ lock theo trường hợp nào?
Bạn phân biệt tryLock không chờ với tryLock có timeout về cách tránh deadlock và quản lý deadline ra sao?
Bạn sẽ giải thích fairness policy của ReentrantLock ảnh hưởng throughput và starvation như thế nào?
Bạn phân biệt lock fairness với thứ tự công việc thực sự hoàn thành trong executor ra sao?
Bạn mô tả Condition.await và Condition.signal yêu cầu giữ ReentrantLock liên quan như thế nào?
Bạn sẽ sử dụng hai Condition objects notEmpty và notFull cho bounded buffer theo cơ chế nào?
Bạn phân tích vì sao Condition.await cũng phải kiểm tra lại predicate trong vòng while khi được đánh thức ra sao?
Bạn sẽ chọn signalAll thay signal khi nhiều loại tác vụ chờ cùng Condition theo tiêu chí nào?
Bạn phân biệt ReentrantReadWriteLock readLock và writeLock theo khả năng cho phép nhiều readers như thế nào?
Bạn sẽ đánh giá trường hợp nhiều readers, ít writers khiến ReentrantReadWriteLock hiệu quả hơn synchronized ra sao?
Bạn phân tích nguy cơ writer starvation khi có quá nhiều đọc liên tục với read/write locks như thế nào?
Bạn sẽ xác định vì sao nâng cấp từ read lock sang write lock cần chiến lược cẩn thận để tránh deadlock như thế nào?
Bạn mô tả StampedLock optimistic read kết hợp validate stamp bảo đảm đọc nhất quán theo điều kiện nào?
Bạn sẽ thiết kế fallback sang read lock khi optimistic read của StampedLock không được validate như thế nào?
Bạn phân biệt StampedLock với ReentrantReadWriteLock ở khả năng reentrancy và thread ownership ra sao?
Bạn sẽ giải thích tại sao optimistic read không phù hợp khi đọc một cấu trúc mutable có thể bị thay đổi nguy hiểm ngoài synchronization như thế nào?
Bạn phân tích rủi ro quên unlockWrite hoặc unlockRead đúng stamp làm một tác vụ giữ lock quá lâu ra sao?
Bạn sẽ dùng try/finally cho StampedLock để đảm bảo giải phóng khóa với stamp chính xác như thế nào?
Bạn mô tả LockSupport.park và unpark phối hợp parking thread ở mức primitive như thế nào?
Bạn phân biệt LockSupport.unpark permit với Object.notify trong điều kiện tránh missed wakeup như thế nào?
Bạn sẽ xác định tác động của Thread.interrupt đối với một thread đang LockSupport.park như thế nào?
Bạn sẽ cân nhắc dùng Semaphore thay vì tự xây ReentrantLock khi cần giới hạn số tác vụ đồng thời ra sao?
Bạn phân tích vì sao Semaphore permits không đồng nghĩa mỗi thread chỉ có thể acquire đúng một permit như thế nào?
Bạn sẽ chọn lock striping để giảm contention cho một map dữ liệu lớn mà vẫn bảo đảm multi-key operations ra sao?
Bạn phân biệt coarse-grained locking với fine-grained locking về simplicity, throughput và khả năng deadlock như thế nào?
Bạn sẽ đo thời gian đợi ReentrantLock và thời gian giữ lock để xác định điểm nghẽn theo workload nào?
Bạn sẽ viết stress test phát hiện lock contention hoặc starvation mà không phụ thuộc kết quả scheduling ngẫu nhiên ra sao?
Bạn giải thích Compare-And-Set (CAS) xử lý read-modify-write mà không cần một monitor truyền thống như thế nào?
Bạn phân biệt AtomicInteger.incrementAndGet với thao tác tăng int thông thường về linearizability ra sao?
Bạn sẽ lựa chọn AtomicLong thay cho synchronized counter trong tình huống có workload nào?
Bạn mô tả AtomicReference.compareAndSet hỗ trợ thay đổi reference khi current value khớp expected ra sao?
Bạn sẽ thiết kế vòng lặp CAS cập nhật một immutable state snapshot mà không làm mất update như thế nào?
Bạn phân tích vì sao lambda truyền vào AtomicInteger.updateAndGet có thể được chạy lại và không được chứa side effects như thế nào?
Bạn sẽ giải thích ABA problem của CAS trên reference và tại sao equality đơn giản không đủ phát hiện thay đổi trung gian ra sao?
Bạn sẽ dùng AtomicStampedReference hoặc AtomicMarkableReference để giải quyết những biến thể state problem nào?
Bạn phân biệt AtomicBoolean với volatile boolean khi cần chuyển trạng thái có điều kiện như thế nào?
Bạn sẽ đánh giá LongAdder và AtomicLong khi nhiều threads cùng tăng một metric counter theo yêu cầu đọc nhất quán nào?
Bạn phân tích vì sao LongAdder.sum không cung cấp một snapshot atomic của tất cả updates đồng thời như thế nào?
Bạn sẽ dùng LongAccumulator cho phép gộp số liệu kết hợp theo hàm được lựa chọn mà không giả định thứ tự thực thi ra sao?
Bạn mô tả VarHandle hỗ trợ các chế độ get/set, volatile, acquire/release và compareAndSet khác nhau như thế nào?
Bạn sẽ phân biệt VarHandle.getAcquire với getVolatile theo yêu cầu ordering và tính di động ra sao?
Bạn sẽ xác định khi nào cần VarHandle.setRelease kết hợp getAcquire thay vì volatile ordering toàn phần ra sao?
Bạn phân tích vì sao một cấu trúc lock-free có thể vẫn không bảo đảm wait-freedom cho từng thread ra sao?
Bạn sẽ lựa chọn thread-safe collections thay vì tự xây lock-free linked list khi rủi ro bảo trì cao như thế nào?
Bạn mô tả ConcurrentHashMap hỗ trợ đọc/cập nhật đồng thời khác HashMap theo cơ chế bảo đảm nào?
Bạn sẽ dùng ConcurrentHashMap.putIfAbsent, computeIfAbsent và merge khi cần update có điều kiện ra sao?
Bạn phân tích vì sao function của ConcurrentHashMap.computeIfAbsent không nên gọi cập nhật đệ quy cùng map như thế nào?
Bạn sẽ thiết kế cập nhật hai keys trong ConcurrentHashMap khi phải giữ invariant toàn cục bằng giải pháp nào?
Bạn phân biệt ConcurrentHashMap iteration dạng weakly consistent với fail-fast iterator của collection thông thường như thế nào?
Bạn sẽ đánh giá CopyOnWriteArrayList khi workload đọc nhiều ghi ít và chấp nhận chi phí sao chép như thế nào?
Bạn phân tích vì sao iterator của CopyOnWriteArrayList thể hiện snapshot thay vì mọi thay đổi mới nhất ra sao?
Bạn sẽ chọn ConcurrentLinkedQueue hoặc LinkedBlockingQueue dựa trên nhu cầu bounded capacity và blocking consumption nào?
Bạn phân biệt ArrayBlockingQueue với LinkedBlockingQueue theo bộ nhớ, capacity và locking semantics ra sao?
Bạn sẽ dùng BlockingQueue.put và take để phối hợp producer-consumer mà không tự xử lý wait/notify như thế nào?
Bạn phân tích vì sao unbounded queue trong service có thể gây OutOfMemoryError khi producer nhanh hơn consumer ra sao?
Bạn sẽ sử dụng SynchronousQueue khi muốn handoff trực tiếp giữa producer và consumer theo tình huống nào?
Bạn sẽ chọn PriorityBlockingQueue khi cần ưu tiên nhưng vẫn kiểm tra giới hạn capacity và starvation như thế nào?
Bạn mô tả ThreadLocalRandom phục vụ sinh số ngẫu nhiên hiệu quả trong nhiều threads nhưng không dành cho mục đích mật mã như thế nào?
Bạn sẽ kiểm tra thread safety của một object graph dùng concurrent collection nhưng các values bên trong vẫn mutable ra sao?
Bạn giải thích Executor và ExecutorService tách việc gửi task khỏi cơ chế quản lý threads như thế nào?
Bạn phân biệt execute với submit về cách nhận exception và theo dõi kết quả task ra sao?
Bạn sẽ lựa chọn newFixedThreadPool, newCachedThreadPool hay newSingleThreadExecutor theo workload và rủi ro nào?
Bạn phân tích vì sao Executors.newFixedThreadPool dùng queue không giới hạn có thể làm bộ nhớ tăng khi load đột biến như thế nào?
Bạn sẽ cấu hình ThreadPoolExecutor với corePoolSize, maximumPoolSize và bounded BlockingQueue theo mục tiêu nào?
Bạn mô tả ThreadPoolExecutor lựa chọn tạo thread mới, xếp queue hoặc reject khi tải tăng như thế nào?
Bạn sẽ đánh giá sự tương tác giữa queue capacity và maximumPoolSize để tránh hiểu sai ngưỡng mở rộng pool ra sao?
Bạn phân biệt CPU-bound với I/O-bound tasks khi chọn kích thước pool và cách đo thông lượng như thế nào?
Bạn sẽ thiết kế ThreadFactory để đặt tên thread, daemon policy và UncaughtExceptionHandler ra sao?
Bạn phân tích vì sao đặt tất cả executor threads là daemon có thể làm mất công việc khi JVM thoát ra sao?
Bạn sẽ lựa chọn AbortPolicy, CallerRunsPolicy hoặc custom RejectedExecutionHandler khi overload theo mục tiêu nào?
Bạn mô tả CallerRunsPolicy tạo feedback pressure lên thread gửi task và những giới hạn của nó như thế nào?
Bạn sẽ phân biệt rejection của ExecutorService với exception xảy ra bên trong task đã chấp nhận ra sao?
Bạn sẽ quyết định dùng execute cho fire-and-forget khi vẫn cần thu thập lỗi và lifecycle task như thế nào?
Bạn giải thích Future.get khác Future.isDone về blocking, result và exception delivery như thế nào?
Bạn sẽ dùng Future.get với timeout để giới hạn thời gian chờ mà không giả định task tự dừng ra sao?
Bạn phân biệt Future.cancel(false) với cancel(true) theo tín hiệu interrupt và bảo đảm hủy tác vụ như thế nào?
Bạn phân tích tại sao task không hợp tác với interrupt có thể tiếp tục chạy sau khi Future đã đánh dấu cancelled ra sao?
Bạn sẽ viết Callable hỗ trợ interruption trong thao tác lặp hoặc blocking call như thế nào?
Bạn mô tả ExecutionException bọc lỗi của Callable khi caller lấy kết quả Future như thế nào?
Bạn phân biệt CancellationException với TimeoutException và ExecutionException ở tầng gọi task như thế nào?
Bạn sẽ sử dụng ExecutorCompletionService để nhận kết quả tasks theo thứ tự hoàn thành thay vì thứ tự gửi ra sao?
Bạn phân biệt ExecutorService.invokeAll với invokeAny theo cách chờ và hủy các tác vụ còn lại ra sao?
Bạn sẽ quản lý ScheduledExecutorService cho tác vụ định kỳ mà không tạo timer threads thủ công như thế nào?
Bạn phân biệt scheduleAtFixedRate với scheduleWithFixedDelay khi một lần thực thi kéo dài hơn dự kiến ra sao?
Bạn phân tích vì sao một periodic task ném exception có thể khiến các lần chạy tiếp theo bị hủy trong ScheduledExecutorService như thế nào?
Bạn sẽ thiết kế graceful shutdown bằng shutdown, awaitTermination và shutdownNow theo các giai đoạn nào?
Bạn phân biệt shutdownNow trả các tasks chưa bắt đầu với việc thực sự dừng toàn bộ tasks đang chạy như thế nào?
Bạn sẽ xử lý InterruptedException khi chính thread gọi awaitTermination bị yêu cầu hủy theo cách nào?
Bạn phân tích rủi ro một ExecutorService không shutdown khiến JVM tiếp tục sống sau khi main kết thúc ra sao?
Bạn sẽ theo dõi activeCount, queue size, completedTaskCount và rejection count của ThreadPoolExecutor để chẩn đoán overload như thế nào?
Bạn sẽ xác định khi nào nên tách CPU pool và blocking I/O pool để tránh starvation giữa các loại tasks ra sao?
Bạn sẽ thiết kế task submission có deadline hoặc admission control trước khi queue đầy để hệ thống fail-fast như thế nào?
Bạn phân tích vì sao nộp task rồi gọi Future.get ngay trên cùng single-thread executor có thể dẫn tới thread starvation deadlock ra sao?
Bạn sẽ đánh giá khi nào shared ForkJoinPool.commonPool phù hợp hoặc gây tranh chấp tài nguyên giữa các components như thế nào?
Bạn giải thích CountDownLatch phối hợp nhiều threads chờ một sự kiện hoàn tất như thế nào?
Bạn phân biệt CountDownLatch với CyclicBarrier ở khả năng tái sử dụng qua nhiều chu kỳ ra sao?
Bạn sẽ thiết kế test hai threads bắt đầu cùng thời điểm bằng CountDownLatch thay vì Thread.sleep như thế nào?
Bạn mô tả CyclicBarrier barrier action và kết quả khi một thành viên bị interruption như thế nào?
Bạn sẽ xác định cách BrokenBarrierException lan đến các threads khác khi một barrier bị phá như thế nào?
Bạn phân biệt Phaser với CyclicBarrier theo khả năng đăng ký và rời nhóm tham gia động như thế nào?
Bạn sẽ sử dụng Phaser khi một pipeline có nhiều giai đoạn và số workers thay đổi theo quá trình ra sao?
Bạn phân tích rủi ro một worker không arrive khiến các threads khác chờ Phaser vô hạn như thế nào?
Bạn sẽ dùng Semaphore để giới hạn số calls đồng thời tới một external resource theo capacity nào?
Bạn phân biệt Semaphore.acquire với tryAcquire có timeout khi hệ thống cần đáp ứng deadline ra sao?
Bạn mô tả Exchanger cho phép hai threads trao đổi dữ liệu tại một điểm đồng bộ hóa như thế nào?
Bạn sẽ quyết định khi nào dùng BlockingQueue thay Exchanger để tránh coupling hai tasks chờ nhau ra sao?
Bạn phân tích vì sao CompletableFuture không tự cung cấp backpressure khi một producer tạo quá nhiều asynchronous tasks ra sao?
Bạn sẽ kết hợp bounded queue hoặc Semaphore với executor khi số requests vượt năng lực xử lý như thế nào?
Bạn mô tả ForkJoinPool sử dụng work-stealing cho các tác vụ chia để trị như thế nào?
Bạn phân biệt RecursiveTask với RecursiveAction trong Fork/Join framework về kết quả trả về ra sao?
Bạn sẽ xác định kích thước bài toán để fork tasks thay vì xử lý trực tiếp theo threshold nào?
Bạn phân tích vì sao chia task quá nhỏ gây overhead lớn hơn lợi ích song song như thế nào?
Bạn sẽ thiết kế ForkJoinTask không giữ locks hoặc thực hiện blocking I/O không được quản lý theo cách nào?
Bạn sẽ đánh giá ForkJoinPool.ManagedBlocker khi công việc buộc blocking trong Fork/Join pool theo nhu cầu nào?
Bạn phân biệt parallelStream dùng common pool với stream tuần tự theo khả năng kiểm soát resources ra sao?
Bạn sẽ xem xét ordering và associativity khi parallel reduction trên Java Streams như thế nào?
Bạn phân tích vì sao side effects trên mutable ArrayList trong parallel stream có thể tạo data race như thế nào?
Bạn sẽ kiểm tra performance thực tế trước khi dùng parallel stream cho công việc nhỏ hoặc I/O-bound như thế nào?
Bạn giải thích CompletableFuture vừa biểu diễn kết quả tương lai vừa hỗ trợ xây pipeline bất đồng bộ như thế nào?
Bạn phân biệt CompletableFuture.supplyAsync với runAsync theo giá trị kết quả của task ra sao?
Bạn sẽ xác định executor nào được dùng khi gọi supplyAsync không truyền executor tường minh như thế nào?
Bạn phân biệt thenApply với thenCompose khi một callback trả giá trị thường hoặc trả CompletableFuture như thế nào?
Bạn mô tả thenCombine kết hợp hai kết quả độc lập khác thenCompose theo dependency graph ra sao?
Bạn sẽ lựa chọn thenAccept, thenRun hoặc thenApply khi bước tiếp theo có và không có output như thế nào?
Bạn phân biệt thenApply với thenApplyAsync về khả năng thực thi inline hoặc được lên lịch bởi executor như thế nào?
Bạn phân tích vì sao callback thenApply có thể chạy trên thread hoàn tất stage trước đó và gây chậm I/O thread như thế nào?
Bạn sẽ thiết kế pipeline CompletableFuture không block trong callback bằng join hoặc get theo cách nào?
Bạn mô tả CompletableFuture.allOf chờ nhiều stages nhưng không tự tạo danh sách kết quả typed như thế nào?
Bạn phân biệt allOf với anyOf theo thời điểm hoàn tất và nhu cầu hủy các tác vụ còn lại ra sao?
Bạn sẽ xử lý lỗi theo nhánh bằng exceptionally mà không che mất nguyên nhân thất bại cần ghi nhận như thế nào?
Bạn phân biệt handle với whenComplete về khả năng biến đổi kết quả hoặc chỉ quan sát outcome ra sao?
Bạn sẽ xác định propagation của exception qua nhiều stages trước khi có handler tương ứng như thế nào?
Bạn phân tích vì sao một exceptionally trả fallback tùy tiện có thể biến lỗi nghiệp vụ thành thành công giả ra sao?
Bạn sẽ sử dụng CompletableFuture.orTimeout để giới hạn thời gian chờ stage theo tình huống nào?
Bạn phân biệt completeOnTimeout với orTimeout khi lựa chọn fallback hay exceptional completion ra sao?
Bạn sẽ xác định vì sao orTimeout không đồng nghĩa underlying network call hoặc task đã bị dừng như thế nào?
Bạn mô tả CompletableFuture.cancel tương tác với completion state nhưng không bảo đảm interrupt task đang chạy như thế nào?
Bạn sẽ thiết kế deadline và cancellation token riêng khi cần hủy tác vụ thực bên dưới CompletableFuture ra sao?
Bạn phân biệt CompletableFuture.get với join ở exception types và interruptibility của việc chờ ra sao?
Bạn sẽ xử lý CompletionException để giữ nguyên root cause khi một stage thất bại như thế nào?
Bạn phân tích vì sao tạo hàng nghìn supplyAsync tasks vào common pool có thể ảnh hưởng tasks của module khác ra sao?
Bạn sẽ cung cấp dedicated executor cho pipeline có blocking I/O thay vì dựa vào common pool theo tiêu chí nào?
Bạn mô tả complete, completeExceptionally và obtrudeValue khác nhau về semantics hoàn tất của CompletableFuture như thế nào?
Bạn sẽ xác định rủi ro nhiều threads cạnh tranh hoàn thành cùng một CompletableFuture theo cơ chế thắng một lần ra sao?
Bạn phân biệt dependent stages với independent futures khi dựng DAG xử lý dữ liệu như thế nào?
Bạn sẽ thiết kế timeout tổng cho pipeline gồm nhiều stages mà không tạo timeout riêng làm vượt deadline ban đầu như thế nào?
Bạn phân tích vì sao dùng thenCompose mà callback tạo tác vụ không giới hạn có thể làm mất kiểm soát concurrency ra sao?
Bạn sẽ kiểm thử pipeline CompletableFuture với stage hoàn thành trước, sau và đồng thời callback registration như thế nào?
Bạn sẽ ghi nhận completion latency và exceptions của mỗi stage mà không dùng một shared mutable metrics object không an toàn ra sao?
Bạn giải thích virtual threads thay đổi mô hình quản lý blocking tasks trong Java từ JDK 21 như thế nào?
Bạn phân biệt virtual thread với platform thread theo chi phí quản lý và ánh xạ tới các carrier threads ra sao?
Bạn sẽ tạo virtual thread bằng Thread.ofVirtual khi triển khai một tác vụ ngắn theo API phù hợp như thế nào?
Bạn mô tả Thread.startVirtualThread cho phép chạy Runnable bằng virtual thread mới như thế nào?
Bạn sẽ sử dụng Executors.newVirtualThreadPerTaskExecutor để phục vụ nhiều blocking requests theo cách nào?
Bạn phân tích vì sao không nên pool virtual threads như một số lượng cố định nhỏ của platform threads ra sao?
Bạn sẽ giải thích tại sao virtual threads cải thiện scalability của blocking I/O nhưng không làm phép tính CPU-bound nhanh hơn như thế nào?
Bạn phân biệt khả năng chạy đồng thời nhiều virtual threads với số cores thực thi song song CPU instructions ra sao?
Bạn sẽ xác định khi nào giới hạn kết nối database bằng Semaphore vẫn cần thiết dù mỗi request có một virtual thread ra sao?
Bạn phân tích rủi ro tạo quá nhiều tasks không giới hạn dù virtual threads rẻ hơn platform threads như thế nào?
Bạn mô tả pinning xảy ra khi virtual thread không thể unmount khỏi carrier ở những tình huống phụ thuộc JDK nào?
Bạn sẽ kiểm tra JFR events hoặc thread diagnostics để tìm pinning trên phiên bản JDK đang dùng như thế nào?
Bạn phân biệt tác động của synchronized blocking đối với virtual threads trên JDK 21 với những cải tiến ở các JDK mới hơn như thế nào?
Bạn sẽ quyết định khi nào thay synchronized bằng ReentrantLock vì nhu cầu tránh pinning trên JDK cụ thể ra sao?
Bạn phân tích vì sao giữ monitor khi gọi blocking I/O trong virtual thread cần được đánh giá theo runtime version như thế nào?
Bạn sẽ kiểm tra ThreadLocal data trên hàng triệu virtual threads để tránh memory overhead theo mỗi task như thế nào?
Bạn phân biệt InheritableThreadLocal với ThreadLocal theo điều kiện chia sẻ ngữ cảnh và nguy cơ rò dữ liệu ra sao?
Bạn sẽ đánh giá ScopedValue trên JDK hỗ trợ tính năng này theo semantics phạm vi để truyền context như thế nào?
Bạn phân tích tại sao thread identity không nên là key định danh lâu dài của một business request trong hệ thống virtual threads ra sao?
Bạn sẽ thiết kế tracing context propagation không phụ thuộc assumptions một carrier thread luôn chạy cùng request như thế nào?
Bạn phân biệt thread dump virtual threads với thread dump platform threads khi điều tra số lượng lớn tác vụ chờ I/O ra sao?
Bạn sẽ lựa chọn Thread.ofPlatform hoặc Thread.ofVirtual cho một long-lived scheduler hay một blocking handler theo tiêu chí nào?
Bạn phân tích vì sao một virtual thread bị deadlock do lấy locks sai vẫn là lỗi correctness dù thread nhẹ ra sao?
Bạn sẽ kiểm tra giới hạn file descriptors và remote rate limit khi triển khai virtual-thread-per-request service ra sao?
Bạn sẽ tạo test benchmark so sánh platform thread pool với virtual threads dưới workload có blocking I/O ra sao?
Bạn phân biệt structured concurrency API ở bản JDK preview với các API virtual thread ổn định khi thiết kế thư viện dùng nhiều JDK versions như thế nào?
Bạn sẽ xem xét StructuredTaskScope trên đúng bản JDK hỗ trợ để quản lý lifetime của các tác vụ con theo nguyên tắc nào?
Bạn phân tích vì sao không nên giả định virtual thread được tự động interrupt khi request nghiệp vụ kết thúc ra sao?
Bạn sẽ thiết kế graceful shutdown phối hợp hủy tasks đang chạy trên virtual threads mà không giữ ứng dụng treo ra sao?
Bạn phân biệt deadlock, livelock, starvation và priority inversion theo dấu hiệu trên thread dump như thế nào?
Bạn sẽ xác định nguyên nhân deadlock do locks ở nhiều services Java objects bằng cách dựng wait-for graph ra sao?
Bạn mô tả ThreadMXBean.findDeadlockedThreads hỗ trợ điều tra loại deadlock nào trong JVM như thế nào?
Bạn sẽ dùng Thread.getAllStackTraces hoặc thread dump để tìm threads bị BLOCKED, WAITING và TIMED_WAITING ra sao?
Bạn phân tích vì sao trạng thái RUNNABLE trong Java thread dump không luôn đồng nghĩa CPU đang được sử dụng liên tục như thế nào?
Bạn sẽ đánh giá thread contention bằng Java Flight Recorder (JFR) thay vì chỉ suy luận từ throughput như thế nào?
Bạn mô tả một race condition có thể không xuất hiện khi debug vì breakpoint làm thay đổi scheduling như thế nào?
Bạn sẽ kiểm thử shared counter có lost updates bằng stress test nhiều threads nhưng tránh khẳng định test lặp nhiều lần là chứng minh an toàn ra sao?
Bạn sẽ thiết kế unit test dùng CountDownLatch tạo điểm bắt đầu chung để tăng khả năng lộ race mà không dựa vào sleep như thế nào?
Bạn phân tích vì sao test đồng thời phụ thuộc fixed delays dễ flaky ở máy CI có CPU không ổn định như thế nào?
Bạn sẽ sử dụng JUnit và await có timeout để bảo đảm test không treo vô hạn khi có deadlock như thế nào?
Bạn phân biệt concurrency stress testing với JCStress litmus tests của Java Memory Model theo loại vấn đề nào?
Bạn sẽ chọn JCStress để kiểm tra các outcome được phép của một data race dưới JMM ra sao?
Bạn mô tả vì sao benchmark JMH cần warm-up và đo riêng overhead synchronization để tránh kết luận sai như thế nào?
Bạn sẽ phân biệt lỗi data race với lỗi performance do lock contention trong kết quả benchmark như thế nào?
Bạn sẽ dùng AtomicInteger hoặc synchronized làm baseline khi đo hiệu quả tối ưu của concurrent counter ra sao?
Bạn phân tích tại sao một cấu trúc lock-free có throughput tốt vẫn có thể gặp starvation ở một thread cụ thể ra sao?
Bạn sẽ xác định giới hạn resources như queue size, active threads và rejected tasks trong load test ExecutorService như thế nào?
Bạn mô tả cách đo p95/p99 task queue waiting time để đánh giá tác động của backpressure ra sao?
Bạn sẽ thiết kế test interruption cho một Callable bị cancel khi đang chờ BlockingQueue.take như thế nào?
Bạn phân tích vì sao kiểm tra Future.isCancelled không chứng minh task đã đóng socket hoặc transaction ra sao?
Bạn sẽ xây dựng test ExecutorService.shutdownNow và xác minh cleanup tài nguyên trong task ra sao?
Bạn sẽ giả lập executor saturated để xác minh RejectedExecutionHandler không làm mất dữ liệu quan trọng như thế nào?
Bạn phân tích vì sao thread leaks sau mỗi test làm test suite chậm hoặc không thể kết thúc JVM ra sao?
Bạn sẽ dùng timeout tổng cho integration test CompletableFuture để phát hiện completion bị bỏ quên như thế nào?
Bạn sẽ thiết kế negative tests cho exceptional completion, cancellation và callback chạy đồng thời ra sao?
Bạn phân tích vì sao kiểm thử tính đúng đắn của concurrent map cần xác định invariant chứ không chỉ không ném exception ra sao?
Bạn sẽ chẩn đoán OutOfMemoryError khi producer nhanh hơn consumer qua queue metrics và heap dump như thế nào?
Bạn sẽ xác định dấu hiệu virtual thread pinning hoặc carrier starvation qua JFR trên JDK tương ứng ra sao?
Bạn phân tích vì sao tăng số worker threads có thể làm performance tệ hơn do context switching hoặc lock contention như thế nào?
Bạn sẽ lập checklist review một Java concurrent component về visibility, atomicity, lock ordering, cancellation, bounded resources và tests như thế nào?
Nếu hai threads tăng chung biến int rồi kết quả thấp hơn dự kiến, bạn sẽ xác định race condition và chọn cách sửa theo throughput nào?
Nếu một worker không nhận shutdown flag do cache/visibility, bạn sẽ áp dụng volatile hoặc synchronization như thế nào?
Nếu hai threads đều giữ một lock và chờ lock còn lại, bạn sẽ tìm cycle và áp dụng global lock ordering ra sao?
Nếu consumer bị treo dù producer đã notify, bạn sẽ kiểm tra monitor ownership, condition predicate và lost notification như thế nào?
Nếu một ReentrantLock không được nhả khi handler ném exception, bạn sẽ thiết kế try/finally thế nào?
Nếu optimistic read của StampedLock nhận dữ liệu không nhất quán, bạn sẽ kiểm tra validate và fallback read lock ra sao?
Nếu AtomicReference cập nhật sai khi giá trị bị thay A sang B rồi về A, bạn sẽ phân tích ABA problem như thế nào?
Nếu nhiều threads cùng computeIfAbsent một cache nhưng mapping function có side effects, bạn sẽ thiết kế lại initialization ra sao?
Nếu HashMap được chia sẻ giữa nhiều threads và đôi lúc trả dữ liệu sai, bạn sẽ xác định cần concurrent collection hoặc synchronized invariant như thế nào?
Nếu hàng nghìn requests được nộp vào fixed pool có unbounded queue làm heap tăng, bạn sẽ thiết kế bounded ThreadPoolExecutor ra sao?
Nếu một task trong single-thread ExecutorService đợi Future từ task khác cùng executor, bạn sẽ tìm starvation deadlock như thế nào?
Nếu ScheduledExecutorService ngừng chạy task định kỳ sau một exception, bạn sẽ tìm nguyên nhân và thiết kế error handling ra sao?
Nếu Future.cancel(true) đã trả về nhưng tác vụ vẫn chạy, bạn sẽ kiểm tra interrupt handling và resource cleanup như thế nào?
Nếu CompletableFuture.orTimeout trả lỗi nhưng HTTP request vẫn tiếp tục, bạn sẽ gắn cancellation vào underlying task như thế nào?
Nếu pipeline thenApply chạy CPU nặng ngay trên I/O completion thread, bạn sẽ tách executor hoặc asynchronous stage như thế nào?
Nếu nhiều CompletableFuture cùng fail mà kết quả allOf che nguyên nhân chính, bạn sẽ thu thập diagnostics cho từng task ra sao?
Nếu virtual-thread-per-request tạo quá nhiều kết nối DB cùng lúc, bạn sẽ giới hạn permits với Semaphore như thế nào?
Nếu ứng dụng trên JDK 21 có virtual thread pinning khi giữ monitor và chờ I/O, bạn sẽ chẩn đoán JFR và điều chỉnh locking ra sao?
Nếu ThreadLocal chứa dữ liệu người dùng không được remove sau task trong pooled threads, bạn sẽ xử lý isolation và cleanup như thế nào?
Nếu một stress test chỉ lỗi khi chạy đủ lâu nhưng không tái hiện dưới debugger, bạn sẽ dùng JCStress và các điểm đồng bộ thử nghiệm ra sao?
Nếu thread dump cho thấy hàng trăm threads WAITING ở BlockingQueue.take, bạn sẽ phân biệt chờ hợp lệ với starvation hoặc mất producer ra sao?
Nếu một CompletableFuture pipeline không hoàn tất vì một stage bị bỏ quên, bạn sẽ thiết kế deadlines và logging state transitions ra sao?
Nếu một concurrent collection bảo vệ từng operation nhưng nghiệp vụ cần cập nhật hai keys atomically, bạn sẽ thiết kế critical section ra sao?
Nếu CPU cao nhưng throughput thấp sau khi tăng pool size, bạn sẽ phân tích contention, context switching và queue metrics như thế nào?
Nếu cần thiết kế Java service thuần JDK xử lý tác vụ đồng thời, bạn sẽ chọn Thread, locks, atomic, ExecutorService, CompletableFuture, virtual threads và các quy tắc kiểm thử ra sao?
