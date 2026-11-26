Process là gì và hệ điều hành quản lý tài nguyên của một process khác với chương trình đang lưu trên đĩa như thế nào?
Bạn phân biệt process, thread và program theo không gian địa chỉ, trạng thái thực thi và quyền sở hữu tài nguyên như thế nào?
Bạn mô tả các trạng thái chính trong vòng đời process và những sự kiện khiến process chuyển giữa các trạng thái đó như thế nào?
Bạn giải thích vai trò của process ID, parent process ID và process control block trong quản lý process như thế nào?
Bạn phân biệt tạo process bằng fork và thay thế chương trình bằng exec trên Linux qua một luồng khởi chạy như thế nào?
Bạn mô tả cách process cha thu nhận trạng thái kết thúc của process con và hậu quả khi không gọi wait hoặc waitpid như thế nào?
Bạn phân biệt zombie process và orphan process, nêu cách nhận diện và xử lý từng trường hợp như thế nào?
Bạn giải thích copy-on-write giúp giảm chi phí tạo process con sau fork như thế nào và khi nào cơ chế này phát sinh sao chép thực tế?
Bạn phân biệt handle và process ID trên Windows khi quản lý vòng đời process như thế nào?
Bạn phân tích các nguyên nhân khiến một process kết thúc bất thường và cách phân biệt exit code, signal hoặc exception như thế nào?
Bạn xác định process nào đang giữ tài nguyên hoặc tạo nhiều process con bất thường trên Linux và Windows bằng cách nào?
Bạn đánh giá tác động của giới hạn số process, file descriptor hoặc handle đến khả năng hoạt động của ứng dụng như thế nào?
Bạn phân biệt user mode và kernel mode khi process thực hiện system call như thế nào?
Bạn giải thích không gian địa chỉ ảo của process và vai trò của page table trong ánh xạ bộ nhớ như thế nào?
Bạn phân biệt heap, stack, data segment và memory-mapped region trong không gian địa chỉ process như thế nào?
Bạn giải thích vì sao hai process có thể dùng cùng một địa chỉ ảo nhưng ánh xạ tới các vùng bộ nhớ vật lý khác nhau như thế nào?
Bạn mô tả cơ chế bảo vệ bộ nhớ giữa các process và hậu quả khi một process truy cập vùng nhớ không được phép ra sao?
Bạn phân tích ảnh hưởng của page fault, swapping và memory pressure đến thời gian phản hồi của ứng dụng như thế nào?
Bạn phân biệt resident set size, virtual memory size và committed memory trên Windows khi điều tra process sử dụng bộ nhớ ra sao?
Bạn xác định dấu hiệu memory leak ở cấp process và phân biệt với việc hệ điều hành sử dụng RAM làm cache như thế nào?
Bạn giải thích thread chia sẻ những tài nguyên nào trong cùng process và mỗi thread sở hữu những trạng thái riêng nào?
Bạn phân biệt user-level thread và kernel-level thread về khả năng lập lịch, chi phí và hành vi khi một thread bị block như thế nào?
Bạn mô tả các trạng thái của thread và cách thread chuyển giữa running, runnable, blocked hoặc waiting như thế nào?
Bạn giải thích mối quan hệ giữa Java thread và native operating-system thread trong mô hình JVM truyền thống như thế nào?
Bạn phân biệt platform thread và virtual thread của Java về cách ánh xạ tới thread hệ điều hành như thế nào?
Bạn đánh giá khi nào virtual thread có lợi cho workload I/O-bound và khi nào không cải thiện workload CPU-bound như thế nào?
Bạn giải thích tình huống virtual thread bị pin vào carrier thread và cách nhận diện hoặc giảm hiện tượng này như thế nào?
Bạn mô tả vai trò của thread control block và stack riêng của từng thread trong quá trình thực thi như thế nào?
Bạn xác định những dữ liệu chia sẻ giữa các thread có thể gây race condition và cách phát hiện chúng như thế nào?
Bạn phân biệt concurrency và parallelism qua ví dụ ứng dụng chạy trên một lõi và nhiều lõi CPU như thế nào?
Bạn giải thích vai trò của scheduler trong việc lựa chọn thread tiếp theo được cấp CPU như thế nào?
Bạn phân biệt preemptive scheduling với cooperative scheduling về quyền thu hồi CPU và ảnh hưởng đến tính đáp ứng như thế nào?
Bạn so sánh các thuật toán scheduling như round-robin, priority scheduling và multilevel feedback queue theo workload như thế nào?
Bạn giải thích time slice hoặc quantum ảnh hưởng đến fairness và số lần context switch như thế nào?
Bạn phân biệt CPU-bound và I/O-bound thread khi đánh giá cách scheduler phân bổ thời gian CPU như thế nào?
Bạn phân tích tác động của thread priority và priority inversion đến khả năng đáp ứng của tác vụ quan trọng như thế nào?
Bạn giải thích CPU affinity và NUMA locality ảnh hưởng đến hiệu năng thread trên máy nhiều socket như thế nào?
Bạn nhận diện tình trạng một thread bị starvation dù CPU tổng thể vẫn còn khả năng xử lý như thế nào?
Bạn phân biệt context switch giữa hai thread cùng process với context switch giữa hai process về trạng thái cần lưu và khôi phục như thế nào?
Bạn mô tả các bước chính của context switch và lý do thao tác này có chi phí dù không thực hiện công việc nghiệp vụ như thế nào?
Bạn đánh giá những yếu tố làm context switch tăng cao và ảnh hưởng của chúng đến throughput hoặc tail latency như thế nào?
Bạn phân biệt voluntary context switch và involuntary context switch khi phân tích hành vi một process như thế nào?
Bạn xác định khi nào thread bị chờ CPU, chờ I/O hoặc chờ lock từ metric và công cụ hệ điều hành như thế nào?
Bạn giải thích false sharing và cache-line contention có thể làm giảm hiệu năng khi nhiều thread cập nhật dữ liệu gần nhau như thế nào?
Bạn phân biệt mutex và semaphore theo quyền sở hữu lock, số lượng permit và mục đích đồng bộ như thế nào?
Bạn lựa chọn mutex, binary semaphore hoặc counting semaphore cho một bài toán giới hạn số worker truy cập tài nguyên như thế nào?
Bạn giải thích condition variable phối hợp với mutex để chờ một điều kiện thay đổi như thế nào?
Bạn phân biệt monitor, intrinsic lock và explicit lock trong mô hình đồng bộ của Java như thế nào?
Bạn giải thích atomic operation và compare-and-swap (CAS) hỗ trợ cập nhật dữ liệu đồng thời mà không dùng mutex như thế nào?
Bạn đánh giá giới hạn của CAS khi có contention cao hoặc gặp vấn đề ABA như thế nào?
Bạn phân biệt atomicity, visibility và ordering trong đồng bộ bộ nhớ giữa các thread như thế nào?
Bạn giải thích memory barrier và memory model bảo đảm quan hệ happens-before giữa các thao tác như thế nào?
Bạn xác định khi nào volatile trong Java đủ để bảo đảm visibility và khi nào vẫn cần synchronized hoặc atomic class như thế nào?
Bạn lựa chọn AtomicInteger, LongAdder hoặc synchronized counter dựa trên tần suất cập nhật và kiểu truy vấn như thế nào?
Bạn phân biệt read-write lock và mutex thông thường khi workload có nhiều thao tác đọc và ít thao tác ghi như thế nào?
Bạn đánh giá khi nào lock-free hoặc wait-free algorithm phù hợp và những chi phí về độ phức tạp cần cân nhắc ra sao?
Bạn giải thích semaphore có thể giới hạn số kết nối đồng thời tới database hoặc dịch vụ bên ngoài như thế nào?
Bạn nhận diện race condition trong thao tác kiểm tra rồi cập nhật một biến chia sẻ và thiết kế cách khắc phục ra sao?
Bạn mô tả bốn điều kiện cần của deadlock và cách chúng cùng xuất hiện trong một hệ thống đa luồng như thế nào?
Bạn phân biệt deadlock, livelock và starvation qua biểu hiện quan sát được của các thread như thế nào?
Bạn xây dựng thứ tự lấy lock nhất quán để ngăn chu trình chờ và giảm nguy cơ deadlock như thế nào?
Bạn phát hiện deadlock từ thread dump hoặc wait-for graph bằng cách xác định chuỗi thread và lock đang chờ như thế nào?
Bạn xử lý tình huống hai thread giữ hai lock khác nhau rồi chờ lock của nhau mà không thể tiến triển như thế nào?
Bạn phân biệt timeout-based lock acquisition với thử lock không chờ trong cách phòng tránh deadlock như thế nào?
Bạn đánh giá rủi ro priority inversion và áp dụng priority inheritance hoặc thiết kế lại vùng critical section ra sao?
Bạn xác định critical section nào cần khóa và giảm thời gian giữ lock để hạn chế contention như thế nào?
Bạn phân tích vì sao nested lock hoặc gọi callback khi đang giữ lock có thể gây deadlock khó tái hiện như thế nào?
Bạn phân biệt process synchronization với thread synchronization khi dữ liệu được chia sẻ giữa các process như thế nào?
Bạn lựa chọn pipe, named pipe, Unix domain socket hoặc TCP socket cho giao tiếp liên tiến trình dựa trên phạm vi và đặc tính dữ liệu ra sao?
Bạn mô tả cơ chế message queue giúp các process trao đổi thông điệp mà không cần chia sẻ cùng không gian địa chỉ như thế nào?
Bạn so sánh shared memory với message passing về tốc độ, độ phức tạp đồng bộ và khả năng cách ly như thế nào?
Bạn thiết kế vùng shared memory để nhiều process truy cập mà không đọc dữ liệu chưa hoàn tất ghi như thế nào?
Bạn giải thích vai trò của semaphore hoặc mutex liên tiến trình khi đồng bộ truy cập shared memory như thế nào?
Bạn xử lý tình huống process giữ lock trong shared memory rồi bị crash để tránh các process khác chờ vô hạn ra sao?
Bạn lựa chọn cơ chế IPC phù hợp khi cần truyền dữ liệu lớn giữa các process trên cùng máy như thế nào?
Bạn đánh giá tác động của serialization, copy dữ liệu và context switch đến hiệu năng message passing như thế nào?
Bạn phân biệt signal với IPC truyền dữ liệu và xác định những tình huống signal phù hợp để điều khiển process ra sao?
Bạn xử lý signal an toàn khi chương trình cần dọn dẹp tài nguyên hoặc kết thúc process như thế nào?
Bạn giải thích sự khác nhau giữa graceful shutdown và forced termination đối với process đang giữ file hoặc transaction như thế nào?
Bạn sử dụng ps, top, pidstat hoặc /proc để kiểm tra trạng thái, CPU, memory và thread của một process Linux như thế nào?
Bạn dùng ps -L, top -H hoặc taskset để xem thread và affinity của process Linux ra sao?
Bạn phân tích các trường trong /proc/<pid>/status, /proc/<pid>/task và /proc/<pid>/wchan để điều tra thread bị block như thế nào?
Bạn sử dụng strace để xác định process đang chờ system call, file I/O hoặc network I/O nào như thế nào?
Bạn kết hợp perf stat, perf top hoặc perf record để xác định CPU hotspot và chi phí context switch trên Linux như thế nào?
Bạn kiểm tra giới hạn file descriptor, thread hoặc process bằng ulimit và các thông tin trong /proc ra sao?
Bạn phân biệt process ở trạng thái D, S, R và Z trong Linux khi điều tra ứng dụng không phản hồi như thế nào?
Bạn dùng pstack, gdb hoặc công cụ tương đương để lấy stack của các thread trong process Linux khi nào?
Bạn sử dụng Get-Process, Task Manager hoặc Process Explorer để tìm process và thread tiêu thụ tài nguyên trên Windows như thế nào?
Bạn phân biệt handle count, thread count, private bytes và working set khi chẩn đoán process Windows như thế nào?
Bạn sử dụng Wait Chain Traversal hoặc Resource Monitor để tìm chuỗi chờ và deadlock trên Windows như thế nào?
Bạn lựa chọn Process Monitor, Windows Performance Recorder hoặc Windows Performance Analyzer để phân tích hoạt động process/thread như thế nào?
Bạn kiểm tra thread đang chờ kernel object hoặc I/O trên Windows bằng công cụ nào và diễn giải kết quả ra sao?
Bạn phân biệt crash dump, hang dump và live thread snapshot khi điều tra một process Windows như thế nào?
Bạn so sánh cách Linux và Windows biểu diễn process, thread, handle và cơ chế đồng bộ trong chẩn đoán thực tế như thế nào?
Bạn lựa chọn công cụ quan sát phù hợp khi process tăng CPU, tăng thread count hoặc bị treo nhưng không crash như thế nào?
Bạn sử dụng jstack hoặc jcmd Thread.print để lấy thread dump của ứng dụng Java và xác định trạng thái từng thread như thế nào?
Bạn đọc thread dump Java để phân biệt RUNNABLE, BLOCKED, WAITING và TIMED_WAITING trong bối cảnh vận hành như thế nào?
Bạn nhận diện deadlock trong thread dump Java bằng thông tin monitor, ownable synchronizer và chuỗi lock như thế nào?
Bạn phân biệt thread đang ở trạng thái RUNNABLE nhưng thực tế chờ I/O với thread đang tiêu thụ CPU bằng cách đối chiếu công cụ nào?
Bạn liên kết Java thread ID trong thread dump với native thread ID và số liệu CPU của hệ điều hành như thế nào?
Bạn sử dụng Java Flight Recorder để xác định lock contention, thread park và socket wait, rồi đối chiếu công cụ hệ điều hành để đánh giá context switch như thế nào?
Bạn đánh giá ảnh hưởng của thread pool quá nhỏ hoặc quá lớn đến queueing, context switch và độ trễ ứng dụng Java như thế nào?
Bạn lựa chọn kích thước thread pool cho tác vụ CPU-bound và I/O-bound dựa trên tài nguyên và giới hạn downstream ra sao?
Bạn phát hiện thread pool starvation khi worker bị chặn chờ tác vụ khác trong cùng pool bằng những dấu hiệu nào?
Bạn thiết kế timeout, cancellation và shutdown cho ExecutorService để tránh thread bị giữ vô thời hạn như thế nào?
Bạn phân biệt synchronized, ReentrantLock, Semaphore và BlockingQueue trong việc phối hợp các worker Java như thế nào?
Bạn xác định nguyên nhân latency tăng sau khi tăng số worker dù CPU vẫn chưa đạt 100 phần trăm như thế nào?
Bạn kiểm tra tác động của virtual thread, carrier thread và pinning lên hiệu năng ứng dụng Java bằng công cụ nào?
Bạn lựa chọn cách giới hạn concurrency khi dùng virtual thread để không tạo quá nhiều kết nối database hoặc request tới downstream như thế nào?
Bạn thiết kế bài kiểm thử tải để đo throughput, p95/p99 latency, context switch và lock contention trước và sau khi thay đổi số thread như thế nào?
Bạn xây dựng quy trình điều tra end-to-end khi ứng dụng Java bị treo, bao gồm thread dump, OS metrics, lock graph và kiểm tra tài nguyên như thế nào?
