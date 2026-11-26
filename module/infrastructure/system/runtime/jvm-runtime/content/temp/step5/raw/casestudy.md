Một ứng dụng Java khởi động thất bại sau khi thư viện dùng chung được nâng phiên bản, log báo NoClassDefFoundError dù class vẫn tồn tại trong JAR; nhóm phát triển cần phân tích classpath và quá trình nạp lớp.
Một dịch vụ chỉ gặp ExceptionInInitializerError ở lần gọi đầu tiên sau deploy, các lần gọi sau báo NoClassDefFoundError; đội vận hành cần xác định lỗi trong static initializer và trạng thái class sau lần khởi tạo thất bại.
Một máy chủ ứng dụng redeploy nhiều lần nhưng Metaspace tăng sau mỗi lần, heap dump cho thấy classloader của phiên bản cũ vẫn được giữ bởi thread nền; nhóm SRE cần điều tra classloader leak.
Ứng dụng Java mới chạy trên JVM cũ và dừng ngay khi nạp class với UnsupportedClassVersionError; đội nền tảng cần đối chiếu bytecode target, JDK build và runtime thực tế.
Một thư viện dùng reflection truy cập package nội bộ của JDK, sau nâng cấp Java ứng dụng gặp InaccessibleObjectException; nhóm phát triển cần đánh giá module boundaries và mức tương thích với JDK mới.
API có thời gian phản hồi cao trong vài phút đầu sau restart rồi nhanh dần khi chạy lâu, nhóm vận hành nghi ngờ database dù CPU và I/O ổn định; đội SRE cần phân tích class loading, interpreter và JIT warmup.
Một JVM báo CodeCache gần đầy, biên dịch JIT bị hạn chế và hiệu năng giảm sau nhiều giờ; nhóm runtime cần đánh giá code cache, compiled methods và hoạt động deoptimization.
Một phương thức từng được JIT tối ưu nhưng đột nhiên chạy chậm sau khi traffic chuyển sang nhiều kiểu implementation, log cho thấy deoptimization lặp lại; nhóm phát triển cần phân tích tính đa hình và profile của call site.
Một ứng dụng trong container đặt Xmx gần bằng memory limit, sau khi cộng Metaspace, thread stacks và direct buffers pod bị OOMKilled dù heap chưa đạt ngưỡng; đội SRE cần lập ngân sách tổng bộ nhớ tiến trình.
Dashboard heap usage ổn định nhưng RSS của JVM tăng liên tục theo thời gian, nhóm vận hành nghi rò rỉ object Java; đội runtime cần phân biệt heap với native memory và vùng bộ nhớ ngoài heap.
Một dịch vụ nạp và hủy hàng nghìn class động theo tenant, Metaspace tăng dù heap sau GC vẫn thấp; nhóm phát triển cần kiểm tra vòng đời classloader và khả năng unload class.
Ứng dụng xử lý network dùng direct ByteBuffer, heap dump không cho thấy object lớn nhưng tiến trình bị OutOfMemoryError: Direct buffer memory; đội SRE cần điều tra native/direct memory và vòng đời buffer.
Ứng dụng dùng G1 GC có pause tăng đột biến khi xử lý batch với nhiều object lớn, log ghi nhận humongous allocation; nhóm SRE cần xác định kích thước object, vùng humongous và tác động tới chu kỳ thu gom.
Một dịch vụ đặt mục tiêu latency thấp dùng ZGC nhưng bộ nhớ tiêu thụ tăng sau khi tải đột biến, nhóm vận hành cho rằng collector bị rò rỉ; đội runtime cần đánh giá headroom, concurrent GC và đặc điểm collector.
JVM báo GC overhead limit exceeded khi xử lý một lô dữ liệu lớn, heap liên tục được thu gom nhưng rất ít bộ nhớ được giải phóng; nhóm phát triển cần xác định retained objects và allocation pressure.
Ứng dụng có tỷ lệ promotion cao sau minor collections, Old Generation nhanh đầy và Full GC xuất hiện dù request rate không đổi; nhóm SRE cần phân tích tuổi thọ object và promotion behavior.
Một ứng dụng dùng WeakHashMap để lưu metadata nhưng value giữ tham chiếu ngược tới key, entry không được giải phóng như kỳ vọng; nhóm Java cần phân tích reachability và cấu trúc tham chiếu.
JVM thoát với Java heap space và tự động tạo heap dump nhưng file dump không xuất hiện do thư mục đích không đủ quyền và dung lượng; đội vận hành cần kiểm tra cấu hình dump và filesystem.
Một dịch vụ báo OutOfMemoryError: Metaspace sau nhiều lần tải plugin, heap còn nhiều dung lượng và số classloader tăng theo mỗi phiên; nhóm runtime cần phân biệt giới hạn Metaspace với heap exhaustion.
Một tiến trình Java báo Unable to create new native thread trong giờ cao điểm dù heap còn trống, thread dump cho thấy số worker tăng không giới hạn; nhóm vận hành cần xác định thread leak và giới hạn PID của container.
Pod bị Kubernetes OOMKilled mà không có OutOfMemoryError trong application log, heap usage trước đó thấp hơn Xmx; đội SRE cần đối chiếu cgroup memory, native allocation và sự kiện kernel.
Một JVM dùng GC log để điều tra pause dài nhưng log bị rotate sai và ghi đè dữ liệu cũ trước khi sự cố được phân tích; nhóm vận hành cần thiết kế đường dẫn, rotation và thời gian lưu GC log.
GC log của hai node có timestamp và timezone khác nhau, nhóm trực không thể ghép pause với đợt tăng latency trên hệ thống phân tán; đội SRE cần chuẩn hóa mốc thời gian và clock synchronization.
Một ứng dụng ghi nhận tổng thời gian GC tăng, nhóm phát triển kết luận cần đổi collector nhưng chưa tách young, mixed và full collections; đội runtime cần phân tích log theo loại sự kiện và mục tiêu pause.
Heap dump của production có kích thước hàng chục gigabyte, quá trình tạo dump làm ứng dụng ngừng đáp ứng trong giờ cao điểm; nhóm SRE cần đánh giá tác động, thời điểm và phương án thu thập an toàn.
Một heap dump được chuyển lên kho chia sẻ để phân tích nhưng có thể chứa token, dữ liệu khách hàng và nội dung request; nhóm bảo mật cần xác định quyền truy cập, mã hóa và thời hạn lưu artifact.
Nhóm phân tích heap dump thấy một danh sách lớn trong dominator tree và cho rằng đó là leak, nhưng retained size của object thấp hơn dự kiến; đội Java cần phân biệt shallow size, retained size và đường tham chiếu.
Một heap dump cho thấy nhiều object giữ lại sau khi request kết thúc, nhóm phát triển chưa xác định được chủ sở hữu; đội runtime cần dùng GC roots để lần theo static field, thread và cache reference.
Một ứng dụng tăng heap sau mỗi đợt xử lý nhưng giảm mạnh sau Full GC, dashboard chỉ ghi nhận đỉnh heap và báo động leak; nhóm SRE cần so sánh live set sau GC qua nhiều chu kỳ.
Thread dump cho thấy hai thread BLOCKED chờ khóa của nhau, API thanh toán không phản hồi dù CPU thấp; nhóm phát triển cần xác định deadlock và chuỗi monitor ownership.
Một dịch vụ có hàng trăm thread BLOCKED trên cùng synchronized method, throughput giảm mạnh nhưng không có deadlock; đội SRE cần phân tích lock contention và vùng đồng bộ quá rộng.
Thread dump ghi nhận nhiều thread RUNNABLE nhưng CPU process thấp, stack trace chủ yếu chờ đọc socket; nhóm vận hành cần phân biệt trạng thái RUNNABLE của JVM với thread thực sự tiêu thụ CPU.
Một thread pool có toàn bộ worker đang chờ phản hồi từ dịch vụ bên ngoài, queue tiếp tục tăng và request mới hết timeout; nhóm phát triển cần đánh giá pool exhaustion, timeout và bulkhead.
Ứng dụng dùng ForkJoinPool.commonPool cho tác vụ blocking I/O, một số worker bị giữ lâu và các tác vụ CPU-bound không được chạy; đội Java cần đánh giá việc trộn blocking và work stealing.
Một hệ thống dùng ThreadLocal để lưu context request, worker thread được tái sử dụng nhưng giá trị cũ không được remove sau request; nhóm phát triển cần điều tra giữ object và rò rỉ dữ liệu giữa các request.
Một ứng dụng tạo thread nền với context classloader trỏ tới web application cũ, sau redeploy classloader không được giải phóng; đội runtime cần phân tích thread context classloader và vòng đời thread.
Ứng dụng shutdown trong Kubernetes nhưng worker threads không xử lý interrupt, JVM chờ vô hạn và pod bị SIGKILL sau termination grace period; nhóm vận hành cần đánh giá interruption và graceful shutdown.
Một dịch vụ dùng native library trong nhiều thread, thread dump cho thấy các luồng chờ native call không có Java frame hữu ích; nhóm SRE cần kết hợp thread dump với native stack và dữ liệu hệ điều hành.
Ứng dụng Java mới dùng virtual threads cho mỗi request nhưng một số tác vụ giữ monitor hoặc gọi native code lâu, làm carrier threads bị pin; nhóm phát triển cần điều tra pinning và cấu trúc đồng bộ.
Một dịch vụ có số lượng virtual threads rất lớn, dashboard thread count truyền thống tăng mạnh và nhóm vận hành cho rằng đã cạn native threads; đội runtime cần phân biệt virtual threads với platform threads và carrier threads.
Một JVM có thời gian dừng dài không giải thích được bằng GC pause, log safepoint cho thấy VM operation khác giữ ứng dụng tại safepoint; nhóm SRE cần phân biệt GC pause với safepoint synchronization.
Một nhóm lấy thread dump khi hệ thống đang quá tải nhưng chỉ thu một snapshot, không xác định được thread nào bị kẹt lâu hay trạng thái thay đổi; đội vận hành cần so sánh nhiều dump có khoảng thời gian rõ ràng.
Java Flight Recorder được bật liên tục nhưng file recording bị ghi đè trước khi đội trực tải về, sự kiện trước incident không còn; nhóm SRE cần cấu hình dump-on-exit, max age và max size phù hợp.
Một nhóm bật JFR với profile settings trong thời gian dài, overhead CPU tăng trên ứng dụng latency-sensitive; đội runtime cần đánh giá event selection, stack depth và chu kỳ ghi.
JFR recording có dữ liệu allocation và lock contention nhưng nhóm phát triển chỉ xem tổng CPU sample, bỏ qua event theo thời gian; đội Java cần chọn event và phân tích timeline phù hợp câu hỏi điều tra.
Một bản JFR được thu khi tải thấp nên không tái hiện allocation hotspot xuất hiện vào giờ cao điểm; nhóm SRE cần xác định thời điểm, thời lượng và điều kiện workload của recording.
JFR cho thấy allocation rate cao trong một đoạn xử lý JSON, nhưng heap dump chụp sau Full GC không còn các object ngắn hạn; nhóm phát triển cần kết hợp allocation profiling với phân tích heap.
Một recording JFR bị thiếu event class loading vì cấu hình custom settings tắt nhóm event đó; đội runtime cần kiểm tra recording settings trước khi kết luận không có hoạt động nạp lớp.
Một dịch vụ lưu JFR recordings và heap dumps trên cùng volume với dữ liệu ứng dụng, khi dump lớn làm đầy đĩa và service không thể ghi file nghiệp vụ; nhóm vận hành cần tách dung lượng và giới hạn artifact.
Ứng dụng có nhiều file descriptor mở lâu dài, số socket tăng theo thời gian dù thread count ổn định; nhóm SRE cần phân tích vòng đời resource, stream và connection.
Một service Java tạo native resource qua JNI nhưng chỉ giải phóng khi GC chạy, tải thấp khiến file handle và bộ nhớ native tăng; nhóm phát triển cần đánh giá explicit close và Cleaner lifecycle.
Một ứng dụng khởi động nhanh trên JDK mới nhưng tăng latency sau khi thay đổi GC mặc định giữa các phiên bản; nhóm nền tảng cần so sánh collector, flags và workload thay vì giả định runtime tương đương.
Một JVM có CPU cao nhưng GC time thấp, JFR cho thấy phần lớn sample nằm trong method ứng dụng và compiled code; nhóm phát triển cần xác định hotspot, lock và thuật toán gây tải.
Một hệ thống gặp latency spike định kỳ đúng lúc GC concurrent cycle bắt đầu, nhóm trực chỉ nhìn tổng CPU và bỏ qua allocation rate; đội SRE cần tương quan GC log, JFR và latency timeline.
Một service có shutdown hook thực hiện flush queue nhưng hook chờ một executor đã bị dừng trước đó, JVM không thoát trong thời hạn triển khai; nhóm vận hành cần xác định thứ tự shutdown hook và lifecycle của executor.
Một pod Java bị kết thúc khi rollout, cấu hình JVM không nhận đúng container memory limit nên heap được đặt quá lớn và process bị OOMKilled; đội nền tảng cần xác minh container awareness và runtime flags.
Một nhóm thay đổi Xss để giảm bộ nhớ khi có nhiều threads, sau triển khai ứng dụng gặp StackOverflowError trong một số luồng đệ quy sâu; đội Java cần cân đối stack size với độ sâu call stack.
Một ứng dụng có StackOverflowError chỉ ở một nhánh xử lý dữ liệu lồng sâu, heap còn trống và GC bình thường; nhóm phát triển cần phân tích đệ quy, kích thước stack và đường gọi.
Một dịch vụ chạy trong container có giới hạn CPU thấp, JIT compilation và GC cùng tranh CPU với request threads khiến startup kéo dài; nhóm SRE cần đánh giá CPU quota và warmup strategy.
Một hệ thống cần tối ưu throughput nhưng đội vận hành chỉnh pause target rất thấp, collector tiêu tốn nhiều CPU và tổng thời gian xử lý tăng; nhóm runtime cần xác định tradeoff giữa latency, throughput và footprint.
Một JVM nhận tải tăng đột ngột, allocation rate vượt tốc độ thu gom và old generation nhanh đầy dù heap ban đầu được cấp lớn; nhóm SRE cần phân tích tốc độ cấp phát, live set và khả năng mở rộng heap.
Một ứng dụng phát sinh classloader leak, thread leak và direct buffer leak đồng thời nhưng nhóm điều tra chỉ lấy heap dump; đội runtime cần chọn phối hợp GC log, thread dump, native memory tracking và JFR.
Một nhóm nâng cấp JDK và bật GC logging mới, parser nội bộ vẫn mong định dạng cũ nên dashboard pause time hiển thị sai; nhóm nền tảng cần cập nhật pipeline phân tích log theo phiên bản.
Một ứng dụng có lỗi hiệu năng chỉ xuất hiện sau vài ngày, heap dump và thread dump đơn lẻ không ghi nhận lịch sử; nhóm SRE cần lập kế hoạch thu JFR liên tục với giới hạn dung lượng và quy trình lưu giữ.
