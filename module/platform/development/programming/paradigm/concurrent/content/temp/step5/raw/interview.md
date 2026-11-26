Bạn phân biệt concurrency và parallelism theo khả năng tiến triển của tác vụ và số tác vụ thực sự chạy cùng thời điểm như thế nào?
Bạn giải thích vì sao một hệ thống một lõi CPU vẫn có thể xử lý nhiều tác vụ theo mô hình concurrent ra sao?
Bạn đánh giá khi nào chia công việc thành nhiều tác vụ concurrent cải thiện khả năng đáp ứng nhưng không làm tăng tổng throughput như thế nào?
Bạn phân biệt workload CPU-bound với I/O-bound khi quyết định số lượng tác vụ thực thi đồng thời ra sao?
Bạn thiết kế sơ đồ phụ thuộc giữa các tác vụ để xác định phần có thể chạy đồng thời mà không vi phạm thứ tự xử lý như thế nào?
Bạn giải thích vai trò của scheduler trong việc quyết định tác vụ được chạy, tạm dừng hoặc tiếp tục như thế nào?
Bạn phân biệt preemptive scheduling với cooperative scheduling theo trách nhiệm nhường quyền thực thi của tác vụ ra sao?
Bạn đánh giá ảnh hưởng của context switching đến latency và throughput khi số thread lớn hơn nhiều số lõi CPU như thế nào?
Bạn phân biệt tiến trình, thread hệ điều hành và tác vụ logic theo phạm vi chia sẻ bộ nhớ và tài nguyên ra sao?
Bạn lựa chọn mô hình thread-per-request, event loop hoặc worker pool theo đặc điểm workload như thế nào?
Bạn giải thích vì sao concurrent program có thể cho kết quả khác nhau giữa các lần chạy dù cùng input ra sao?
Bạn phân biệt nondeterminism do scheduling với kết quả sai do vi phạm bất biến dữ liệu như thế nào?
Bạn thiết kế bất biến nghiệp vụ cho một chương trình concurrent để đánh giá tính đúng đắn độc lập với thứ tự chạy ra sao?
Bạn phân biệt safety property với liveness property trong việc kiểm chứng thuật toán concurrent như thế nào?
Bạn giải thích các khái niệm deadlock, livelock và starvation thông qua trạng thái tiến triển của tác vụ ra sao?
Bạn phân biệt fairness của scheduler hoặc lock với bảo đảm mọi tác vụ hoàn thành trong giới hạn thời gian như thế nào?
Bạn xác định critical path của một luồng công việc nhiều tác vụ và tác động của nó đến độ trễ tối thiểu ra sao?
Bạn phân tích vì sao tăng số lượng worker không thể giảm thời gian của phần xử lý bắt buộc phải tuần tự như thế nào?
Bạn vận dụng Amdahl's law để ước lượng giới hạn tăng tốc khi chỉ một phần bài toán có thể chạy song song như thế nào?
Bạn thiết kế cách phân chia một lô dữ liệu để giảm chi phí tạo tác vụ và gộp kết quả so với chạy tuần tự như thế nào?
Bạn phân biệt data parallelism với task parallelism trong hai bài toán xử lý mảng và gọi dịch vụ độc lập ra sao?
Bạn xác định rủi ro chia quá nhỏ một công việc khi chi phí scheduling lớn hơn phần tính toán được thực hiện như thế nào?
Bạn giải thích vì sao khả năng xử lý nhiều request đồng thời không đồng nghĩa với thread safety của mọi thành phần được dùng chung ra sao?
Bạn phân biệt concurrency ở mức ứng dụng với concurrency giữa nhiều tiến trình hoặc máy chủ trong hệ thống phân tán như thế nào?
Bạn mô tả shared mutable state là gì và vì sao nó làm tăng số thứ tự thực thi phải xem xét khi kiểm thử ra sao?
Bạn giải thích cơ chế lost update khi hai thread cùng thực hiện thao tác đọc rồi ghi trên một biến đếm như thế nào?
Bạn phân biệt data race với race condition ở cấp nghiệp vụ qua một ví dụ cập nhật số dư tài khoản ra sao?
Bạn xác định cách một chuỗi phép đọc và ghi riêng lẻ có thể tạo trạng thái không hợp lệ dù từng phép đều atomic như thế nào?
Bạn phân biệt atomicity, visibility và ordering khi phân tích tính đúng đắn của một phép cập nhật đồng thời ra sao?
Bạn giải thích mục tiêu của memory model trong việc quy định giá trị một thread có thể quan sát từ thread khác như thế nào?
Bạn phân tích vai trò của happens-before trong bảo đảm sự nhìn thấy dữ liệu sau khi một tác vụ công bố kết quả ra sao?
Bạn phân biệt thứ tự câu lệnh trong source code với thứ tự quan sát được giữa các thread do tối ưu compiler và CPU như thế nào?
Bạn giải thích vì sao một biến cờ dừng thiếu đồng bộ có thể không được thread làm việc quan sát kịp thời ra sao?
Bạn lựa chọn volatile, atomic variable hoặc lock khi cập nhật cờ trạng thái và dữ liệu liên quan theo những tiêu chí nào?
Bạn phân tích vì sao volatile bảo đảm một số quan hệ visibility nhưng không biến phép tăng bộ đếm thành atomic như thế nào?
Bạn thiết kế giao thức publication cho một đối tượng bất biến để thread khác không nhìn thấy trạng thái khởi tạo dở dang ra sao?
Bạn phân tích những bảo đảm dành cho final field khi một object được khởi tạo hoàn chỉnh và công bố an toàn giữa các thread ra sao?
Bạn xác định hậu quả của việc để tham chiếu this thoát ra trước khi constructor hoàn tất trong chương trình concurrent ra sao?
Bạn phân biệt thread confinement với synchronization khi thiết kế thành phần không chia sẻ trạng thái mutable như thế nào?
Bạn đánh giá lợi ích của dữ liệu bất biến trong việc giảm số điểm cần lock khi nhiều tác vụ đọc cùng trạng thái như thế nào?
Bạn thiết kế phép biến đổi dữ liệu bằng copy-on-write khi số lần đọc áp đảo số lần cập nhật ra sao?
Bạn phân tích rủi ro một đối tượng có field final nhưng lại chứa collection mutable được chia sẻ cho nhiều thread như thế nào?
Bạn lựa chọn defensive copy hoặc immutable collection để ngăn caller thay đổi dữ liệu đang được các tác vụ dùng chung ra sao?
Bạn phân tích giới hạn của một thread-safe collection khi một bất biến nghiệp vụ phụ thuộc nhiều thao tác đọc và ghi riêng biệt ra sao?
Bạn thiết kế phép chuyển trạng thái nhiều field sao cho consumer luôn nhìn thấy một snapshot nhất quán ra sao?
Bạn phân biệt safe publication với defensive copying khi dữ liệu cần được truyền giữa producer và consumer ra sao?
Bạn kiểm chứng quan hệ happens-before được tạo bởi thao tác submit task và lấy kết quả qua Future trong Java như thế nào?
Bạn đánh giá khi nào thread-local state hữu ích và khi nào nó tạo nguy cơ giữ dữ liệu qua nhiều request trong worker pool ra sao?
Bạn phân biệt synchronized block và synchronized method theo đối tượng monitor được dùng làm khóa như thế nào?
Bạn thiết kế một critical section chỉ bao quanh phần cập nhật trạng thái cần tính nguyên tử để giảm lock contention ra sao?
Bạn giải thích vì sao synchronized trên hai object khóa khác nhau không bảo vệ được cùng một invariant như thế nào?
Bạn lựa chọn khóa riêng tư thay vì dùng String interned hoặc object công khai làm monitor để tránh can thiệp từ code ngoài ra sao?
Bạn phân tích bốn điều kiện hình thành deadlock và cách phá ít nhất một điều kiện trong thiết kế lấy khóa như thế nào?
Bạn thiết kế quy ước thứ tự lấy nhiều lock để tránh deadlock khi chuyển tiền đồng thời giữa hai tài khoản ra sao?
Bạn xác định nguyên nhân deadlock từ thread dump có nhiều thread chờ monitor theo vòng như thế nào?
Bạn phân biệt lock contention bình thường với deadlock khi hệ thống có throughput giảm mạnh như thế nào?
Bạn giải thích vì sao gọi API blocking hoặc I/O không dự đoán được bên trong critical section có thể tăng tail latency ra sao?
Bạn lựa chọn ReentrantLock thay cho synchronized khi cần timeout, interruptible acquisition hoặc thử lấy khóa ra sao?
Bạn sử dụng tryLock với timeout để đưa ra chiến lược fallback khi tài nguyên đang bị tác vụ khác chiếm giữ như thế nào?
Bạn thiết kế mẫu try-finally khi dùng Lock để bảo đảm giải phóng khóa nếu code trong critical section phát sinh exception ra sao?
Bạn phân biệt tính reentrant của lock với khả năng nhiều thread cùng giữ lock tại một thời điểm ra sao?
Bạn đánh giá chi phí và lợi ích của fairness policy trên lock khi cần cân bằng throughput và thời gian chờ ra sao?
Bạn phân tích hiện tượng priority inversion khi tác vụ ưu tiên cao phải chờ tài nguyên do tác vụ ưu tiên thấp giữ như thế nào?
Bạn thiết kế cơ chế condition wait và signal không bị mất tín hiệu khi producer và consumer phối hợp như thế nào?
Bạn phân tích nguyên nhân phải kiểm tra lại điều kiện trong vòng lặp sau khi Condition.await hoặc Object.wait trả về ra sao?
Bạn phân biệt signal với signalAll theo số tác vụ được đánh thức và nguy cơ tranh chấp lại tài nguyên ra sao?
Bạn lựa chọn read-write lock khi tỷ lệ đọc cao nhưng vẫn cần tránh writer starvation như thế nào?
Bạn phân tích nguy cơ lock upgrade khi một thread đang giữ read lock rồi cố lấy write lock trong hệ thống như thế nào?
Bạn giải thích optimistic read của StampedLock giúp giảm contention trong trường hợp nào và cần kiểm chứng snapshot ra sao?
Bạn thiết kế cơ chế kiểm tra optimistic read thất bại để chuyển sang đường đọc có khóa mà vẫn đúng dữ liệu như thế nào?
Bạn phân biệt lock-based synchronization với transactional update khi một nghiệp vụ kéo dài qua nhiều dịch vụ ra sao?
Bạn đánh giá khi nào cần sharding trạng thái hoặc tách lock theo khóa để giảm contention thay vì dùng một global lock như thế nào?
Bạn giải thích ý nghĩa của lock convoy và cách một critical section kéo dài làm các tác vụ xếp hàng ra sao?
Bạn phân tích sự khác nhau giữa starvation và livelock khi nhiều thread liên tục thử lấy khóa nhưng không tiến triển như thế nào?
Bạn thiết kế backoff khi thử lại thao tác đồng thời để tránh nhiều tác vụ liên tục va chạm cùng tài nguyên ra sao?
Bạn xác định trường hợp lock-free algorithm có thể tăng throughput nhưng phức tạp hơn đáng kể so với thiết kế dùng mutex như thế nào?
Bạn giải thích ý nghĩa của compare-and-set trong việc cập nhật trạng thái khi giá trị hiện tại còn bằng giá trị kỳ vọng như thế nào?
Bạn mô tả một vòng lặp CAS cập nhật bộ đếm khi nhiều thread cùng tranh chấp giá trị ban đầu ra sao?
Bạn phân biệt AtomicInteger.incrementAndGet với cặp lời gọi get rồi set riêng lẻ về bảo đảm atomicity như thế nào?
Bạn sử dụng AtomicReference để thay toàn bộ immutable state bằng một phép cập nhật so sánh và hoán đổi ra sao?
Bạn phân tích giới hạn của AtomicInteger khi bất biến cần cập nhật đồng thời nhiều biến hoặc nhiều object như thế nào?
Bạn thiết kế một state holder bất biến cùng AtomicReference để bảo vệ nhiều trường liên quan trong một phép cập nhật ra sao?
Bạn giải thích vấn đề ABA khi giá trị bị thay đổi rồi quay lại giá trị cũ trước khi CAS tiếp theo xảy ra như thế nào?
Bạn lựa chọn AtomicStampedReference hoặc cơ chế versioning khi tính đúng đắn phụ thuộc việc phát hiện trạng thái đã từng đổi ra sao?
Bạn phân biệt lock-free với wait-free theo bảo đảm tiến triển của từng thread và toàn hệ thống như thế nào?
Bạn đánh giá ảnh hưởng của CAS contention cao đến số lần retry và chi phí CPU khi tải tăng như thế nào?
Bạn lựa chọn LongAdder thay cho AtomicLong cho bộ đếm thống kê có contention cao nhưng không cần snapshot tức thời chính xác như thế nào?
Bạn phân tích vì sao sum của LongAdder trong lúc có cập nhật đồng thời không tương đương một snapshot atomic như thế nào?
Bạn thiết kế cách lấy số liệu chính xác tại thời điểm chốt sổ thay vì chỉ đọc bộ đếm thống kê concurrent như thế nào?
Bạn phân biệt atomic operation trên một phần tử với tính nhất quán của toàn bộ cấu trúc concurrent collection như thế nào?
Bạn sử dụng computeIfAbsent của ConcurrentHashMap để khởi tạo dữ liệu theo key mà không gọi mapping function có side effect nguy hiểm ra sao?
Bạn giải thích tại sao get rồi put trên concurrent map không đảm bảo phép tạo giá trị nếu chưa tồn tại là atomic như thế nào?
Bạn thiết kế một cache concurrent tránh duplicate work khi nhiều request cùng yêu cầu cùng một key lần đầu ra sao?
Bạn phân biệt iterator weakly consistent của concurrent collection với một snapshot cố định tại một thời điểm ra sao?
Bạn đánh giá khi nào copy-on-write collection phù hợp cho cấu hình đọc nhiều và cập nhật rất ít như thế nào?
Bạn lựa chọn cấu trúc dữ liệu có partitioned state thay cho cấu trúc chia sẻ toàn cục để giảm số phép CAS bị tranh chấp ra sao?
Bạn mô tả mục tiêu của ExecutorService trong việc tách vòng đời thread khỏi vòng đời tác vụ nghiệp vụ như thế nào?
Bạn phân biệt Runnable và Callable khi tác vụ có kết quả hoặc checked exception như thế nào?
Bạn thiết kế cơ chế submit tác vụ và thu kết quả qua Future mà không chặn request thread quá thời gian cho phép ra sao?
Bạn phân biệt Future.get có timeout với việc tự động dừng tác vụ đang chạy sau timeout như thế nào?
Bạn giải thích vì sao Future.cancel(true) là yêu cầu hủy có thể gửi interrupt chứ không bảo đảm thread bị dừng tức thì ra sao?
Bạn thiết kế tác vụ blocking có thể phản hồi interruption và cleanup tài nguyên đúng cách như thế nào?
Bạn phân biệt thao tác ghi nhận interrupt status với việc nuốt InterruptedException rồi tiếp tục như chưa có sự cố ra sao?
Bạn phân tích tình huống tác vụ bị hủy nhưng backend I/O vẫn tiếp tục và cách thiết kế deadline xuyên suốt ra sao?
Bạn sử dụng CompletionService để nhận các kết quả theo thứ tự hoàn tất thay vì thứ tự submit như thế nào?
Bạn thiết kế việc gom kết quả từ nhiều Future độc lập khi một tác vụ lỗi mà các tác vụ khác vẫn có thể cung cấp dữ liệu như thế nào?
Bạn lựa chọn invokeAll, invokeAny hoặc một cơ chế kết hợp Future khi muốn all-success hay first-success ra sao?
Bạn giải thích vai trò của CompletableFuture trong biểu diễn tác vụ phụ thuộc nhau mà không phải chờ đồng bộ từng bước như thế nào?
Bạn phân biệt thenApply và thenCompose khi callback trả về giá trị trực tiếp hoặc tiếp tục một thao tác bất đồng bộ như thế nào?
Bạn thiết kế pipeline CompletableFuture có hai tác vụ độc lập được ghép kết quả bằng thenCombine ra sao?
Bạn phân biệt thenApply và thenApplyAsync theo nơi continuation có thể được thực thi và nguy cơ blocking thread gọi như thế nào?
Bạn lựa chọn executor tường minh cho các stage bất đồng bộ khi workload có tác vụ I/O blocking và CPU-bound như thế nào?
Bạn thiết kế xử lý ngoại lệ với handle, exceptionally hoặc whenComplete để không làm mất nguyên nhân lỗi ra sao?
Bạn phân biệt hành vi completeExceptionally với cancellation và timeout trong chuỗi CompletableFuture như thế nào?
Bạn đánh giá giới hạn của việc lan truyền cancellation qua một đồ thị CompletableFuture có nhiều nhánh phụ thuộc ra sao?
Bạn thiết kế việc áp một deadline chung cho nhiều lời gọi bất đồng bộ thay vì đặt timeout độc lập có thể vượt ngân sách thời gian ra sao?
Bạn giải thích vì sao blocking get hoặc join ngay trong continuation có thể gây thread starvation trên executor nhỏ như thế nào?
Bạn kiểm tra nguyên nhân thread pool starvation khi tác vụ trong pool lại chờ Future do chính pool đó phải thực thi như thế nào?
Bạn lựa chọn bounded thread pool cùng rejection policy để tránh queue tăng không giới hạn khi tải vượt capacity ra sao?
Bạn phân biệt backpressure tại hàng đợi tác vụ với throttling tại lớp tiếp nhận request theo tác động đến độ trễ ra sao?
Bạn đánh giá sự khác nhau giữa queue capacity, số worker và arrival rate khi xây dựng giới hạn tải cho hệ thống như thế nào?
Bạn áp dụng Little's law để liên hệ số công việc đang chờ, tốc độ hoàn thành và thời gian đáp ứng theo giả định nào?
Bạn lựa chọn Semaphore để chặn số tác vụ đồng thời gọi một backend có capacity hạn chế như thế nào?
Bạn thiết kế shutdown của ExecutorService có chờ hoàn tất, timeout và xử lý tác vụ chưa chạy ra sao?
Bạn xác định rủi ro dùng unbounded task queue khi request liên tục được nhận nhanh hơn khả năng xử lý của worker như thế nào?
Bạn phân biệt lập lịch fixed rate với fixed delay khi tác vụ định kỳ có thời gian thực thi thay đổi ra sao?
Bạn thiết kế retry cho tác vụ bất đồng bộ có backoff và giới hạn tổng thời gian mà không làm bùng nổ số request ra sao?
Bạn giải thích virtual thread giúp thay đổi chi phí quản lý thread theo tác vụ trong Java hiện đại như thế nào?
Bạn phân biệt virtual thread với platform thread theo cơ chế scheduling và quan hệ với thread của hệ điều hành ra sao?
Bạn giải thích vì sao virtual thread giúp tăng khả năng chịu nhiều tác vụ I/O blocking nhưng không làm CPU có thêm lõi như thế nào?
Bạn lựa chọn virtual thread per task thay cho thread pool cố định khi phần lớn tác vụ chờ network hoặc database như thế nào?
Bạn phân tích giới hạn của virtual thread khi một tác vụ thực hiện tính toán CPU-bound trong thời gian dài như thế nào?
Bạn thiết kế một service nhận nhiều request với virtual threads nhưng vẫn giới hạn số kết nối backend bằng Semaphore ra sao?
Bạn phân biệt cơ chế chặn tài nguyên thật bằng connection pool với giả định có nhiều virtual thread thì có thể tạo vô hạn truy vấn như thế nào?
Bạn đánh giá ảnh hưởng của ThreadLocal được dùng trong hàng nghìn virtual threads đến memory footprint và quản lý context ra sao?
Bạn thiết kế cách truyền request context an toàn cho virtual thread mà không dựa vào global mutable state như thế nào?
Bạn phân tích những tình huống native hoặc foreign-function calls có thể khiến virtual thread giữ carrier thread và cách chẩn đoán bằng JFR ra sao?
Bạn kiểm tra việc thay platform thread pool bằng virtual thread executor có làm thay đổi assumptions về thread identity như thế nào?
Bạn lựa chọn semaphore hoặc connection pool để giới hạn tài nguyên thay vì pooling virtual threads theo những nguyên tắc nào?
Bạn xác định cách đóng virtual-thread-per-task executor và quản lý lifetime của các tác vụ để tránh rò rỉ công việc ra sao?
Bạn đánh giá khi nào mô hình event-loop không chặn vẫn phù hợp hơn virtual threads theo kiến trúc framework hiện có như thế nào?
Bạn thiết kế benchmark so sánh virtual threads và platform thread pool khi đồng thời kiểm soát backend latency, pool kết nối và lượng request ra sao?
Bạn phân biệt throughput tăng nhờ concurrency với độ trễ backend vẫn không đổi khi chuyển ứng dụng sang virtual threads ra sao?
Bạn kiểm chứng thư viện blocking I/O hoạt động đúng với virtual threads và xác định các lời gọi native có thể giữ carrier thread như thế nào?
Bạn lựa chọn công cụ thread dump hoặc JFR event để chẩn đoán hàng nghìn virtual threads đang chờ cùng một tài nguyên như thế nào?
Bạn giải thích mục tiêu của structured concurrency trong việc gắn vòng đời các tác vụ con với một tác vụ cha theo phạm vi rõ ràng như thế nào?
Bạn phân biệt structured concurrency với việc submit tác vụ vào global executor rồi giữ Future ở nhiều tầng code như thế nào?
Bạn thiết kế một phạm vi xử lý request khởi chạy nhiều tác vụ con độc lập nhưng không để tác vụ sống lâu hơn request cha ra sao?
Bạn xác định cách truyền deadline từ tác vụ cha xuống tất cả tác vụ con để tránh cộng dồn timeout vượt SLA như thế nào?
Bạn phân biệt chính sách chờ tất cả tác vụ thành công với chính sách kết thúc khi có kết quả thành công đầu tiên như thế nào?
Bạn thiết kế chính sách xử lý khi một tác vụ con thất bại nhưng các tác vụ còn lại có thể bị hủy để tiết kiệm tài nguyên ra sao?
Bạn giải thích vì sao việc join và đóng phạm vi tác vụ cần rõ ràng để tránh orphan tasks trong hệ thống như thế nào?
Bạn phân tích tính chất cancellation propagation trong một cây tác vụ khi request từ client bị hủy như thế nào?
Bạn đánh giá nguy cơ tác vụ con không chịu dừng khi bị interrupt và tác động của nó đến việc kết thúc structured task scope ra sao?
Bạn thiết kế một giao diện tổng hợp lỗi từ nhiều tác vụ con mà vẫn giữ thông tin nguyên nhân riêng của từng tác vụ như thế nào?
Bạn lựa chọn cách quản lý context chung chỉ đọc cho các tác vụ con thay vì dùng biến static mutable như thế nào?
Bạn phân biệt structured concurrency ở mức thiết kế với trạng thái preview hoặc chuẩn hóa của API Java cụ thể trên JDK đang dùng như thế nào?
Bạn xây dựng phương án triển khai nguyên tắc structured concurrency bằng API được runtime hỗ trợ mà không phụ thuộc cú pháp preview đã đổi như thế nào?
Bạn kiểm chứng một request fan-out không để lại công việc chạy ngầm sau khi timeout hoặc exception bằng các ca kiểm thử nào?
Bạn phân tích mối quan hệ giữa structured concurrency, virtual threads và bảo đảm mỗi tác vụ con được quản lý theo vòng đời như thế nào?
Bạn đánh giá khi nào một công việc nền dài hạn cần được tách khỏi request scope thay vì buộc vào structured concurrency của request ra sao?
Bạn giải thích message passing giúp giảm phụ thuộc vào bộ nhớ mutable dùng chung giữa các tác vụ như thế nào?
Bạn phân biệt mô hình actor với nhiều thread cùng ghi vào một object có lock bảo vệ theo quyền sở hữu trạng thái ra sao?
Bạn thiết kế một actor quản lý số dư tài khoản chỉ cập nhật trạng thái khi nhận message hợp lệ như thế nào?
Bạn mô tả vai trò của mailbox và sự khác nhau giữa thứ tự gửi message với thứ tự xử lý được bảo đảm như thế nào?
Bạn lựa chọn bounded channel hoặc bounded mailbox để ngăn producer làm hệ thống cạn bộ nhớ như thế nào?
Bạn phân tích cách backpressure lan từ consumer chậm tới producer khi dùng channel có dung lượng hữu hạn ra sao?
Bạn thiết kế cơ chế gửi message có timeout và xử lý khi mailbox đầy mà không làm mất dữ liệu âm thầm như thế nào?
Bạn phân biệt at-most-once, at-least-once và exactly-once processing theo hệ quả khi có retry hoặc mất kết nối như thế nào?
Bạn thiết kế message handler idempotent để tránh cập nhật trùng khi một thông điệp được giao lại nhiều lần như thế nào?
Bạn lựa chọn correlation ID khi một request cần ghép phản hồi từ nhiều actor hoặc service độc lập ra sao?
Bạn phân tích nguy cơ deadlock logic khi hai actor chờ phản hồi đồng bộ của nhau mặc dù không dùng mutex như thế nào?
Bạn thiết kế message schema chứa version để nhiều consumer được nâng cấp ở thời điểm khác nhau vẫn xử lý an toàn ra sao?
Bạn phân biệt gửi object reference mutable trong cùng tiến trình với gửi bản sao dữ liệu bất biến qua message như thế nào?
Bạn đánh giá ảnh hưởng của serialization, copying và network latency đến chi phí message passing so với shared-memory concurrency ra sao?
Bạn thiết kế quy tắc giám sát mailbox length, processing lag và retry count để phát hiện consumer không theo kịp tải như thế nào?
Bạn lựa chọn cơ chế supervisor hoặc restart handler để phục hồi một actor thất bại mà không làm mất invariant trạng thái như thế nào?
Bạn giải thích tại sao message passing không tự động loại bỏ mọi race condition khi nhiều message tương tác với cùng hệ thống bên ngoài như thế nào?
Bạn phân biệt actor isolation với ranh giới transaction của database khi một message làm thay đổi nhiều bản ghi như thế nào?
Bạn thiết kế luồng công việc cần tổng hợp nhiều phản hồi message mà không giả định tất cả chúng đến theo thứ tự mong muốn ra sao?
Bạn lựa chọn immutable event hoặc command message để tách yêu cầu thay đổi trạng thái khỏi thông báo trạng thái đã thay đổi như thế nào?
Bạn xác định cách bảo toàn thứ tự xử lý theo entity key khi hệ thống có nhiều consumer và partition khác nhau ra sao?
Bạn thiết kế phép thử determinism cho message handler khi cùng tập message được phát lại theo thứ tự khác nhau ra sao?
Bạn giải thích vai trò của deterministic scheduling trong kiểm thử các trường hợp interleaving khó tái hiện như thế nào?
Bạn thiết kế stress test nhiều worker đồng thời cập nhật cùng tài nguyên để kiểm chứng invariant sau từng đợt xử lý ra sao?
Bạn lựa chọn CountDownLatch hoặc barrier để tạo điểm bắt đầu đồng thời cho test thay vì dùng Thread.sleep như thế nào?
Bạn phân tích hạn chế của một bài test concurrency chạy thành công hàng nghìn lần trong việc chứng minh không tồn tại race condition ra sao?
Bạn xây dựng test bằng timeout để phát hiện tác vụ không tiến triển nhưng vẫn phân biệt deadlock với backend thật sự chậm như thế nào?
Bạn xác định cách dùng thread dump, lock owner và blocked time để điều tra một lần service bị đứng như thế nào?
Bạn sử dụng JFR hoặc profiler để nhận diện lock contention, CPU saturation và tình trạng nhiều thread chờ I/O như thế nào?
Bạn phân biệt thời gian CPU, thời gian chạy trên đồng hồ và thời gian chờ trong một tác vụ concurrent khi đo latency như thế nào?
Bạn lựa chọn throughput, p95/p99 latency, queue depth và concurrency level làm chỉ số đánh giá hiệu năng theo mục tiêu nào?
Bạn thiết kế load test tăng dần arrival rate để tìm điểm queue bắt đầu tăng không kiểm soát như thế nào?
Bạn phân tích vì sao p99 latency có thể tăng nhanh dù CPU usage còn thấp khi hệ thống bị contention trên một lock như thế nào?
Bạn xác định cách đo queue wait time tách khỏi execution time để tìm bottleneck đúng nơi trong một worker pool ra sao?
Bạn đánh giá ảnh hưởng của false sharing khi nhiều thread cập nhật các biến độc lập nhưng nằm gần nhau trong cache line như thế nào?
Bạn thiết kế benchmark tránh warm-up bias, dead-code elimination và sai lệch do lịch chạy thread như thế nào?
Bạn phân tích vì sao chạy parallel stream cho khối lượng nhỏ thường không cải thiện hiệu năng sau khi tính chi phí chia tách và gộp kết quả ra sao?
Bạn lựa chọn cách cô lập workload CPU-bound khỏi các tác vụ blocking để giảm head-of-line blocking như thế nào?
Bạn giải thích rủi ro priority inversion trong hàng đợi tác vụ một mức ưu tiên và cách quản lý latency-sensitive jobs ra sao?
Bạn thiết kế circuit breaker, concurrency limit và bounded queue để bảo vệ dịch vụ khi dependency chậm đột ngột như thế nào?
Bạn phân biệt retry storm với tăng số request hợp lệ và đưa ra chính sách giới hạn retry đồng thời ra sao?
Bạn xác định cách shutdown an toàn hệ thống có producer, consumer và queue khi cần ngừng nhận việc nhưng xử lý nốt việc đang chạy ra sao?
Bạn thiết kế phương án graceful degradation khi một nhánh tính toán đồng thời không kịp deadline nhưng kết quả còn lại vẫn dùng được ra sao?
Bạn phân tích nguy cơ mất trạng thái interrupt hoặc cancellation khi code bắt mọi Exception rồi tiếp tục vòng lặp như thế nào?
Bạn xác định cách log correlation ID, task ID và thời điểm chuyển trạng thái để debug lỗi xảy ra không xác định giữa các thread ra sao?
Bạn lựa chọn công cụ phân tích race và phương pháp review memory ordering khi không thể tái hiện lỗi trực tiếp trên môi trường phát triển như thế nào?
Bạn thiết kế một chương trình concurrent dễ kiểm thử bằng cách tách logic thuần túy khỏi scheduler, clock và I/O như thế nào?
Một bộ đếm dùng volatile vẫn cho kết quả thiếu dưới tải đồng thời, bạn sẽ xác định race và chọn cơ chế cập nhật như thế nào?
Hai thread chuyển tiền đồng thời giữa hai tài khoản khiến hệ thống treo, bạn sẽ đọc thread dump và sửa thứ tự lấy khóa ra sao?
Một service tăng số lượng worker nhưng p99 latency xấu đi và queue tiếp tục dài ra, bạn sẽ tìm bottleneck cùng giới hạn tải như thế nào?
Một Future đã timeout nhưng lời gọi network nền vẫn chạy, bạn sẽ thiết kế cancellation và deadline end-to-end ra sao?
Một ứng dụng chuyển sang virtual threads nhưng database connection pool liên tục cạn, bạn sẽ bổ sung giới hạn đồng thời ở đâu và vì sao?
Một request fan-out để lại tác vụ con chạy sau khi client hủy, bạn sẽ tổ chức lại phạm vi và chiến lược hủy như thế nào?
Một actor nhận lại message sau retry khiến số dư bị trừ hai lần, bạn sẽ bảo đảm idempotency và lưu dấu xử lý ra sao?
Một bài stress test chỉ thất bại một lần trong nhiều nghìn lần chạy, bạn sẽ thu thập lịch thực thi và thu hẹp interleaving gây lỗi như thế nào?
Bạn xây dựng checklist review ứng dụng concurrent dựa trên invariants, shared state, happens-before, lock/CAS, cancellation, backpressure và khả năng quan sát như thế nào?
