Một ứng dụng Java tạo process con bằng ProcessBuilder để chạy công cụ chuyển đổi tệp; process con bị treo nhưng luồng gọi waitFor() chặn vô thời hạn, làm cạn thread phục vụ request dù CPU của máy chủ thấp.
Một service Linux tạo process worker bằng fork() rồi gọi execve(); nhóm vận hành tưởng exec tạo PID mới, trong khi PID được giữ nguyên và chỉ image chương trình của process bị thay thế.
Tiến trình cha tạo nhiều process con ngắn hạn nhưng không gọi wait() hoặc waitpid(); bảng process tích lũy zombie và giới hạn PID dần bị ảnh hưởng dù các process con đã kết thúc.
Một daemon cha thoát trước khi worker kết thúc; worker trở thành orphan và được tiến trình init hoặc subreaper nhận nuôi, khiến nhóm nhầm rằng process đã biến mất khỏi hệ thống.
Một service nhận SIGTERM để dừng nhưng handler chỉ đặt cờ dừng ở thread chính; worker tiếp tục chạy và process không thoát trước thời hạn orchestrator gửi SIGKILL.
Ứng dụng Java khởi chạy process ngoài để gọi script; khi ứng dụng bị dừng, process con vẫn sống và tiếp tục giữ file hoặc cổng mạng do vòng đời process con không được quản lý.
Một tiến trình Linux có nhiều thread nhưng đội trực dùng kill với PID lấy từ thread list; nhóm không hiểu quan hệ TGID/TID và gửi tín hiệu không như mong đợi.
Service chạy trong container có PID namespace riêng; PID thấy trong container khác PID trên host nên đội vận hành gửi signal nhầm tiến trình khi không đối chiếu namespace.
Một chương trình Java dùng thread pool cố định nhưng mỗi tác vụ gọi dịch vụ bên ngoài và chờ I/O lâu; tất cả worker bị chiếm, queue request tăng dù CPU còn nhàn.
Nhóm tăng số thread của web server lên vài nghìn để xử lý đồng thời; context switching, stack memory và contention tăng khiến latency xấu hơn cấu hình ít thread.
Một ứng dụng CPU-bound tạo nhiều thread hơn số lõi CPU; các thread tranh CPU và liên tục chuyển ngữ cảnh, nhưng throughput không tăng theo số thread.
Máy chủ có 32 lõi nhưng một thread xử lý hàng đợi nóng bị khóa trên một core; CPU tổng thể chỉ 10% trong khi một lõi đạt 100% và request chậm.
Tiến trình có nhiều thread runnable nhưng ít thời gian CPU vì các process khác có mức ưu tiên cao hơn; nhóm nhầm starvation do scheduler với deadlock.
Một thread ưu tiên thấp giữ mutex trong khi thread ưu tiên cao chờ mutex và thread ưu tiên trung bình liên tục chạy; hệ thống thời gian thực gặp priority inversion và trễ deadline.
Windows service có thread bị treo khi chờ một mutex; Task Manager chỉ cho thấy process đang chạy và đội trực cần dùng Wait Chain hoặc Process Explorer để xác định quan hệ chờ.
Trên Linux, process hiển thị trạng thái D trong ps khi storage chậm; tín hiệu kết thúc thông thường không làm thread rời uninterruptible sleep cho tới khi lời gọi I/O trong kernel hoàn tất.
Một dịch vụ có thời gian phản hồi tăng sau khi thêm nhiều thread; perf và pidstat cho thấy context switch cùng CPU migrations tăng mạnh dù lượng request giữ nguyên.
Nhóm đo CPU usage ở cấp process và kết luận ứng dụng nhàn rỗi; một thread duy nhất bão hòa một core nhưng tổng mức dùng CPU vẫn thấp trên máy nhiều lõi.
Một ứng dụng đa luồng tăng biến đếm chung bằng phép đọc rồi ghi thông thường; hai thread cập nhật đồng thời gây race condition, làm mất increment và khiến số giao dịch hoàn tất thấp hơn số request.
Nhóm đổi biến đếm dùng chung thành volatile trong Java và cho rằng thao tác ++ đã thread-safe; nhiều thread vẫn ghi đè cập nhật vì volatile không làm phép đọc-sửa-ghi trở thành atomic.
Một service dùng AtomicLong cho counter trên mọi request; khi tải rất cao, nhiều core tranh chấp cùng cache line và thao tác atomic trở thành điểm nóng hiệu năng.
Ứng dụng dùng nhiều atomic counter nằm sát nhau trong bộ nhớ; các thread cập nhật biến khác nhau nhưng false sharing làm cache line liên tục chuyển giữa core và throughput giảm.
Hai thread cùng truy cập HashMap không đồng bộ trong lúc một thread resize; cấu trúc dữ liệu bị hỏng hoặc trả kết quả bất thường do data race.
Một ứng dụng Java khóa toàn bộ xử lý đơn hàng bằng synchronized trên một object dùng chung; thời gian giữ lock dài khiến các request độc lập phải xếp hàng.
Nhóm dùng ReentrantLock nhưng một nhánh exception không unlock trong finally; các thread sau chờ vô thời hạn dù thread giữ lock đã kết thúc phần xử lý nghiệp vụ.
Một thread giữ lock A rồi chờ lock B, thread khác giữ B rồi chờ A; hai thread deadlock và thread dump cho thấy vòng chờ monitor không có tiến triển.
Ứng dụng dùng synchronized lồng nhau trong callback; callback gọi ngược sang component khác đang giữ khóa theo thứ tự ngược, tạo deadlock khó tái hiện.
Một thread gọi Future.get() trong khi task cần chạy trên cùng thread pool để hoàn tất; toàn bộ worker bị chặn chờ task chưa có thread thực thi.
Ứng dụng dùng CountDownLatch với số đếm khởi tạo lớn hơn số worker thực tế; một nhánh lỗi không gọi countDown và thread chính chờ mãi.
Nhóm dùng Semaphore để giới hạn số kết nối database nhưng một nhánh exception không release permit; permit cạn dần và request mới bị chặn dù connection đã được đóng.
Ứng dụng dùng ReadWriteLock cho dữ liệu cấu hình; writer cập nhật liên tục khiến reader bị đói và request đọc có latency cao bất thường.
Một thread liên tục thử lock rồi nhả ngay khi thất bại; nhiều thread lặp lại hành động tương tự mà không có tiến triển, tạo livelock và tiêu tốn CPU.
Ứng dụng dùng wait() trên object nhưng gọi notify() mà không giữ đúng monitor; chương trình ném IllegalMonitorStateException và cơ chế phối hợp producer-consumer bị lỗi.
Một thread chờ condition bằng if thay vì while; spurious wakeup hoặc trạng thái bị thread khác thay đổi khiến nó tiếp tục xử lý dù điều kiện chưa đúng.
Producer-consumer dùng queue không giới hạn; khi consumer chậm hơn producer, bộ nhớ tăng liên tục và cuối cùng JVM bị OOM dù thread không deadlock.
Hai process dùng pipe như một kênh IPC để trao đổi dữ liệu; reader đóng đầu đọc nhưng writer tiếp tục ghi và nhận SIGPIPE hoặc EPIPE, làm tác vụ bị kết thúc ngoài dự kiến.
Ứng dụng dùng Unix domain socket để giao tiếp process cùng máy nhưng quyền file socket quá rộng; process không thuộc nhóm được phép vẫn có thể kết nối tới dịch vụ nội bộ.
Hai process dùng shared memory để trao đổi trạng thái nhưng không dùng semaphore hoặc cơ chế đồng bộ; reader thấy cấu trúc đang được writer cập nhật và đọc dữ liệu nửa chừng.
Service Java giao tiếp với process native qua stdin/stdout; log debug cũng ghi vào stdout làm lẫn với giao thức dữ liệu và parser phía Java đọc sai frame.
Đội vận hành điều tra CPU cao trên Linux chỉ dùng top theo process; cần chuyển sang pidstat, top -H và perf để xác định thread cụ thể đang tiêu thụ CPU.
Một process Java có CPU thấp nhưng nhiều thread ở trạng thái BLOCKED; jstack cho thấy hàng trăm thread chờ cùng monitor và vấn đề nằm ở lock contention thay vì thiếu CPU.
Đội vận hành dùng jstack nhưng chỉ xem thread RUNNABLE; nhiều thread RUNNABLE thực chất đang chờ native I/O hoặc bị kẹt trong lời gọi thư viện, cần kết hợp stack và OS metrics.
Windows service có CPU cao nhưng Task Manager chỉ hiển thị tổng process; nhóm cần dùng Process Explorer, Performance Monitor hoặc ETW/WPA để xác định thread và call stack nóng.
Một ứng dụng Windows có thread bị treo chờ COM call; Wait Chain Traversal chỉ ra chuỗi phụ thuộc nhưng nhóm lại chỉ tăng số thread khiến số lượng waiter nhiều hơn.
Java thread pool có active count thấp nhưng queue length tăng; đội phát triển chỉ nhìn CPU và kết luận server còn dư năng lực trong khi worker bị block ở database hoặc network.
Ứng dụng Java dùng synchronized trong đường xử lý request; Java Flight Recorder cho thấy monitor contention và thời gian blocked tăng sau khi một critical section bổ sung thao tác I/O.
Nhóm chuyển một số tác vụ sang virtual threads nhưng vẫn dùng thư viện native hoặc synchronized dài hạn; khi pinning xảy ra, carrier threads bị chiếm và concurrency kỳ vọng không đạt.
Ứng dụng tạo virtual thread cho mỗi request nhưng dùng một connection pool nhỏ; các virtual thread chờ connection và số lượng thread lớn không làm tăng throughput của database.
Một service Java dùng ForkJoinPool chung cho cả CPU-bound task và blocking I/O; tác vụ I/O chiếm worker khiến các phép tính song song khác bị đình trệ.
Một ứng dụng sử dụng CompletableFuture rồi gọi join() trong thread xử lý request; chuỗi phụ thuộc tạo blocking và làm giảm hiệu quả của mô hình bất đồng bộ.
Thread pool dùng hàng đợi unbounded để tránh từ chối request; khi downstream chậm, backlog tăng cho tới khi heap cạn và tiến trình bị OOM.
ExecutorService bị shutdown nhưng ứng dụng không chờ awaitTermination; process thoát khi tác vụ quan trọng chưa hoàn tất hoặc tác vụ bị interrupt giữa chừng.
Nhóm dùng ThreadLocal lưu context request nhưng thread pool tái sử dụng worker; giá trị của request trước còn sót và bị đọc trong request kế tiếp.
Ứng dụng dùng InheritableThreadLocal để truyền context nhưng thread được tạo từ pool trước khi request đến; context không được kế thừa như mong đợi và trace hoặc security context bị thiếu.
Một thread bị interrupt khi đang sleep nhưng code bắt InterruptedException rồi bỏ qua; cơ chế hủy tác vụ không hoạt động và shutdown phải chờ worker hoàn tất ngoài ý muốn.
Service dùng wait/notify cho hàng đợi công việc; notify đánh thức một thread không phù hợp trong khi các worker khác tiếp tục chờ và throughput giảm dưới tải.
Một ứng dụng có lock contention tăng sau khi thêm cache; cache hit cao nhưng cập nhật một cấu trúc đồng bộ toàn cục làm nhiều request chờ nhau.
Nhóm dùng ConcurrentHashMap nhưng vẫn khóa toàn bộ map quanh mỗi thao tác; lợi ích đồng thời của cấu trúc bị vô hiệu hóa và contention vẫn cao.
Một hệ thống dùng AtomicReference để cập nhật cấu hình nhưng vòng compareAndSet retry không giới hạn khi nhiều thread ghi đồng thời; CPU tăng do contention và retry.
Process Java trên Linux bị giới hạn bởi cgroup CPU quota; thread dump cho thấy nhiều thread RUNNABLE nhưng cgroup throttling khiến chúng không nhận đủ thời gian CPU.
Ứng dụng Windows có nhiều thread nhưng process affinity mask giới hạn vào hai logical processor; tổng CPU toàn máy thấp trong khi hai processor được phép chạy luôn bão hòa.
Service trên máy NUMA có thread chạy ở node CPU khác với node chứa memory; truy cập remote memory tăng latency khi nhóm thay đổi affinity mà không xét locality.
Một tiến trình Linux tạo quá nhiều thread và chạm giới hạn số task của cgroup pids.max; pthread_create thất bại dù hệ thống còn RAM và CPU.
Ứng dụng Windows tạo quá nhiều handle và thread; tiến trình chạm giới hạn tài nguyên hoặc commit charge trong khi nhóm chỉ kiểm tra dung lượng ổ đĩa.
Đội vận hành so sánh số thread giữa Linux và Windows như cùng một đại lượng; cách biểu diễn process, kernel thread và user thread khác nhau khiến kết luận về tải không chính xác.
