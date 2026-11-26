Bạn sẽ mô tả các thành phần chính của JVM từ class loader, runtime data areas đến execution engine và native interface như thế nào?
Bạn sẽ phân biệt JVM, JRE và JDK theo vai trò trong quá trình phát triển và chạy ứng dụng Java ra sao?
Bạn sẽ giải thích quá trình một file .class được nạp, kiểm tra, liên kết và khởi tạo trước khi thực thi như thế nào?
Bạn sẽ phân biệt loading, linking và initialization trong vòng đời của một class như thế nào?
Bạn sẽ mô tả các bước verification, preparation và resolution trong giai đoạn linking ra sao?
Bạn sẽ giải thích bytecode verifier kiểm tra những điều kiện an toàn nào trước khi JVM thực thi class như thế nào?
Bạn sẽ phân biệt class loader bootstrap, platform và application cùng cơ chế delegation ra sao?
Bạn sẽ phân tích parent delegation giúp tránh nạp trùng các class nền tảng nhưng có thể được tùy biến trong trường hợp nào như thế nào?
Bạn sẽ xác định nguyên nhân hai class cùng tên nhưng được nạp bởi hai class loader khác nhau không tương thích kiểu như thế nào?
Bạn sẽ giải thích quan hệ giữa class identity, class loader và lỗi ClassCastException khó hiểu ra sao?
Bạn sẽ phân biệt ClassNotFoundException với NoClassDefFoundError khi class không thể được tìm thấy hoặc khởi tạo như thế nào?
Bạn sẽ điều tra lỗi ExceptionInInitializerError và trạng thái class sau khi static initializer thất bại ra sao?
Bạn sẽ xác định class loader leak trong ứng dụng có plugin hoặc hot redeploy bằng những dấu hiệu nào?
Bạn sẽ giải thích điều kiện để class loader và các class do nó nạp có thể được garbage collect như thế nào?
Bạn sẽ mô tả vai trò của bytecode, interpreter và JIT compiler trong quá trình thực thi một phương thức Java ra sao?
Bạn sẽ phân biệt interpreter, C1 và C2 compiler trong các JVM HotSpot hiện đại như thế nào?
Bạn sẽ giải thích tiered compilation giúp cân bằng thời gian khởi động và hiệu năng chạy lâu dài ra sao?
Bạn sẽ xác định vì sao hiệu năng ứng dụng có thể cải thiện sau một khoảng warm-up và cách đo tránh sai lệch như thế nào?
Bạn sẽ giải thích method inlining giúp JIT tối ưu lời gọi hàm và các giới hạn của quyết định inline ra sao?
Bạn sẽ mô tả speculative optimization và deoptimization khi giả định về kiểu hoặc nhánh thực thi không còn đúng như thế nào?
Bạn sẽ giải thích escape analysis và scalar replacement có thể giảm cấp phát object như thế nào?
Bạn sẽ xác định dấu hiệu JIT compilation hoặc code cache gây ảnh hưởng đến hiệu năng ứng dụng bằng công cụ nào?
Bạn sẽ phân biệt Java bytecode với machine code được JIT sinh ra khi điều tra hiệu năng như thế nào?
Bạn sẽ mô tả vai trò của invokedynamic và method handle trong các cơ chế gọi động của Java ra sao?
Bạn sẽ giải thích safepoint và vì sao một số thao tác JVM cần các thread đạt trạng thái an toàn trước khi tiếp tục như thế nào?
Bạn sẽ phân biệt heap, Java thread stack, metaspace, code cache và direct memory trong mô hình bộ nhớ JVM ra sao?
Bạn sẽ giải thích object allocation trên heap và mối liên hệ giữa object header, field và alignment như thế nào?
Bạn sẽ phân biệt stack frame, local variables, operand stack và return information khi một phương thức được gọi ra sao?
Bạn sẽ xác định điều gì xảy ra khi thread stack vượt giới hạn và phân biệt StackOverflowError với OutOfMemoryError như thế nào?
Bạn sẽ giải thích metaspace lưu metadata của class và khác PermGen ở các phiên bản Java hiện đại ra sao?
Bạn sẽ đánh giá nguy cơ metaspace tăng liên tục khi ứng dụng tạo class hoặc class loader mới như thế nào?
Bạn sẽ phân biệt heap memory với direct buffer và native memory khi tổng RAM process cao hơn Xmx ra sao?
Bạn sẽ giải thích compressed ordinary object pointers ảnh hưởng đến cách tham chiếu object và giới hạn heap như thế nào?
Bạn sẽ mô tả quá trình cấp phát object nhanh qua TLAB và trường hợp JVM cần cơ chế cấp phát khác ra sao?
Bạn sẽ giải thích generational hypothesis và cách young generation, old generation tận dụng vòng đời object như thế nào?
Bạn sẽ phân biệt Eden, Survivor spaces và old generation trong một collector phân thế hệ ra sao?
Bạn sẽ mô tả reachability và garbage collection roots quyết định object còn sống như thế nào?
Bạn sẽ phân biệt strong, soft, weak và phantom references theo hành vi thu hồi object ra sao?
Bạn sẽ giải thích finalization đã bị deprecated và những rủi ro của việc dựa vào finalizer để giải phóng tài nguyên như thế nào?
Bạn sẽ phân biệt minor, major và full GC theo ngữ cảnh collector thay vì coi đây là thuật ngữ có ý nghĩa giống nhau ở mọi JVM như thế nào?
Bạn sẽ so sánh Serial, Parallel, G1, ZGC và Shenandoah theo mục tiêu throughput, latency và quy mô heap ra sao?
Bạn sẽ lựa chọn garbage collector cho dịch vụ cần p99 latency thấp dựa trên đặc điểm workload và giới hạn tài nguyên nào?
Bạn sẽ giải thích G1 chia heap thành region và dùng remembered set để thu thập các vùng phù hợp như thế nào?
Bạn sẽ phân biệt concurrent marking với stop-the-world evacuation trong hoạt động của G1 ra sao?
Bạn sẽ giải thích ZGC hoặc Shenandoah giảm thời gian pause bằng cách thực hiện nhiều công việc đồng thời với ứng dụng như thế nào?
Bạn sẽ đánh giá trade-off giữa GC throughput, pause time, CPU overhead và dung lượng heap như thế nào?
Bạn sẽ đọc GC log để xác định thời điểm pause, nguyên nhân kích hoạt và lượng bộ nhớ thu hồi ra sao?
Bạn sẽ phân biệt allocation rate cao với memory leak khi heap usage tăng trong lúc tải tăng như thế nào?
Bạn sẽ nhận diện dấu hiệu promotion failure, humongous allocation hoặc evacuation failure trong GC log ra sao?
Bạn sẽ xác định khi nào cần điều chỉnh heap size hoặc GC tuning thay vì thay đổi collector như thế nào?
Bạn sẽ giải thích explicit System.gc có thể ảnh hưởng đến độ trễ và vì sao không nên dùng như cơ chế quản lý bộ nhớ ra sao?
Bạn sẽ mô tả cách JVM tạo và lập lịch Java platform threads so với virtual threads như thế nào?
Bạn sẽ phân biệt Java thread với native OS thread trong các phiên bản Java trước và sau virtual threads ra sao?
Bạn sẽ giải thích virtual threads giúp mở rộng ứng dụng nhiều tác vụ I/O chờ đợi nhưng không làm CPU-bound code chạy nhanh hơn như thế nào?
Bạn sẽ phân tích pinning của virtual thread khi sử dụng synchronized hoặc native call theo phiên bản JDK và cách phát hiện ra sao?
Bạn sẽ phân biệt synchronized, ReentrantLock và atomic operations về cơ chế phối hợp truy cập dữ liệu như thế nào?
Bạn sẽ giải thích Java Memory Model, happens-before và visibility khi nhiều thread chia sẻ trạng thái ra sao?
Bạn sẽ xác định nguyên nhân deadlock, livelock và starvation từ thread dump như thế nào?
Bạn sẽ đọc thread dump để phân biệt RUNNABLE, BLOCKED, WAITING và TIMED_WAITING theo ngữ cảnh thực tế ra sao?
Bạn sẽ tìm thread giữ monitor hoặc chờ lock lâu trong thread dump và xác định chuỗi phụ thuộc như thế nào?
Bạn sẽ phân biệt thread leak với thread pool có số lượng worker lớn theo tải bằng những chỉ số nào?
Bạn sẽ đánh giá tác động của thread pool queue, rejection policy và kích thước pool đến độ trễ ứng dụng ra sao?
Bạn sẽ giải thích native memory và direct byte buffer có thể gây OutOfMemoryError dù heap còn nhiều như thế nào?
Bạn sẽ phân biệt các dạng OutOfMemoryError như Java heap space, Metaspace, Direct buffer memory và unable to create native thread ra sao?
Bạn sẽ sử dụng Native Memory Tracking hoặc công cụ hệ điều hành để tìm vùng native memory tăng bất thường như thế nào?
Bạn sẽ xác định nguy cơ file descriptor, socket hoặc native handle bị rò rỉ trong một JVM process bằng công cụ nào?
Bạn sẽ thiết kế cách quản lý tài nguyên ngoài heap như socket, file và direct buffer để bảo đảm đóng đúng vòng đời ra sao?
Bạn sẽ giải thích JNI hoặc thư viện native có thể làm JVM crash dù bytecode Java không có lỗi như thế nào?
Bạn sẽ đọc fatal error log và hs_err file để xác định thread, native frame và vị trí JVM crash ra sao?
Bạn sẽ dùng jcmd, jstack, jmap và jstat cho các mục tiêu chẩn đoán khác nhau như thế nào?
Bạn sẽ lựa chọn thời điểm và cách lấy heap dump để điều tra memory leak mà giảm ảnh hưởng đến production ra sao?
Bạn sẽ phân tích dominator tree, retained size và GC roots trong heap dump để tìm object giữ bộ nhớ như thế nào?
Bạn sẽ phân biệt heap dump histogram với heap dump đầy đủ khi cần khoanh vùng loại object tăng bất thường ra sao?
Bạn sẽ sử dụng Java Flight Recorder để thu thập CPU, allocation, lock contention và GC events như thế nào?
Bạn sẽ lựa chọn cấu hình JFR mặc định hoặc profile theo workload để cân bằng chi tiết dữ liệu và overhead ra sao?
Bạn sẽ kết hợp JFR, thread dump và GC log để xác định nguyên nhân p99 latency tăng trong một dịch vụ Java như thế nào?
Bạn sẽ sử dụng JFR hoặc profiler để phân biệt CPU-bound, lock contention và thời gian chờ I/O ra sao?
Bạn sẽ đánh giá chi phí và rủi ro khi bật profiling liên tục trong production bằng phép thử nào?
Bạn sẽ giải thích container awareness giúp JVM nhận diện CPU và memory limits trong môi trường Kubernetes như thế nào?
Bạn sẽ xác định cấu hình heap phù hợp với memory limit của container khi cần chừa chỗ cho metaspace, thread stacks và native memory ra sao?
Bạn sẽ điều tra vì sao container bị OOMKilled dù JVM chưa ghi nhận Java heap OutOfMemoryError như thế nào?
Bạn sẽ phân biệt CPU quota throttling với JVM thread contention khi ứng dụng chậm trong container ra sao?
Nếu heap usage tăng sau mỗi lần deploy nhưng GC không thu hồi được bộ nhớ, bạn sẽ kết hợp heap dump và class loader statistics để tìm nguyên nhân như thế nào?
Nếu p99 latency tăng đột biến trùng với GC pause, bạn sẽ đọc GC log và JFR để xác định nguyên nhân gốc ra sao?
Nếu CPU cao nhưng throughput thấp, bạn sẽ dùng thread dump, JFR và compilation data để phân biệt busy loop, lock contention và JIT behavior như thế nào?
Nếu JVM báo unable to create native thread, bạn sẽ kiểm tra thread count, process limits, stack size và container PID limits ra sao?
Nếu heap còn trống nhưng process RSS tiếp tục tăng, bạn sẽ điều tra direct buffers, metaspace, thread stacks và native allocations như thế nào?
Nếu ứng dụng bị deadlock sau một lần phát hành, bạn sẽ lấy và phân tích thread dump để tìm vòng chờ lock như thế nào?
Nếu một phương thức chạy chậm ở lần gọi đầu nhưng nhanh hơn sau đó, bạn sẽ thiết kế phép đo để kiểm chứng tác động của JIT warm-up ra sao?
Nếu ứng dụng Java chạy tốt trên máy phát triển nhưng bị OOMKilled trong Kubernetes, bạn sẽ đối chiếu JVM flags, container limits và native memory như thế nào?
