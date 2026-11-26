Bạn phân biệt đặc tả Java Virtual Machine với cách HotSpot hiện thực một JVM cụ thể dựa trên những ví dụ kỹ thuật nào?
Bạn giải thích các bước từ mã nguồn Java đến class file và quá trình thực thi trên JVM như thế nào?
Bạn phân biệt bytecode của JVM với mã máy dành cho một kiến trúc CPU cụ thể ra sao?
Bạn phân tích vai trò của magic number và version trong cấu trúc một Java class file như thế nào?
Bạn giải thích constant pool chứa những nhóm thông tin nào và chúng được dùng trong quá trình thực thi ra sao?
Bạn xác định cách JVM biểu diễn tên lớp, tên phương thức và method descriptor trong class file như thế nào?
Bạn phân biệt field descriptor với method descriptor và giải thích tác động của chúng đến việc liên kết lời gọi ra sao?
Bạn giải thích ý nghĩa của access flags đối với lớp, phương thức và trường trong quá trình JVM xử lý class file như thế nào?
Bạn phân tích mối quan hệ giữa bytecode của một phương thức, bảng biến cục bộ và operand stack ra sao?
Bạn dùng công cụ javap để kiểm tra một class file và suy ra hành vi của lệnh gọi phương thức như thế nào?
Bạn phân biệt các nhóm bytecode load, store, arithmetic, branch và return theo cách chúng tác động đến operand stack ra sao?
Bạn xác định trường hợp sử dụng các bytecode invokevirtual, invokespecial, invokestatic và invokeinterface dựa trên những quy tắc nào?
Bạn phân tích cách invokedynamic hỗ trợ liên kết lời gọi linh hoạt và những điểm cần phân biệt với lời gọi thông thường ra sao?
Bạn kiểm chứng Java compiler biến biểu thức lambda hoặc string concatenation thành bytecode theo những bước nào?
Bạn giải thích vai trò của bootstrap method và call site trong cơ chế invokedynamic như thế nào?
Bạn xác định cách kiểm tra thuộc tính Code, exception table và line number table của một phương thức trong class file ra sao?
Bạn phân biệt thông tin bắt buộc để chạy bytecode với metadata phục vụ debug hoặc reflection trong class file như thế nào?
Bạn phân tích lý do JVM cần bytecode verification trước khi tin cậy cấu trúc và kiểu dữ liệu của một phương thức ra sao?
Bạn giải thích vai trò của stack map frame trong việc hỗ trợ kiểm tra kiểu tại các điểm điều khiển của bytecode như thế nào?
Bạn xử lý tình huống class file được biên dịch bằng phiên bản Java mới hơn phiên bản runtime đang chạy như thế nào?
Bạn mô tả các giai đoạn loading, linking và initialization của một class trong JVM như thế nào?
Bạn phân biệt verification, preparation và resolution ở giai đoạn linking theo trách nhiệm của từng bước ra sao?
Bạn giải thích giá trị mặc định của static field được thiết lập khi preparation khác với giá trị từ static initializer như thế nào?
Bạn phân biệt những hành vi kích hoạt initialization của class với những hành vi chỉ truy cập metadata mà không khởi tạo lớp ra sao?
Bạn phân tích thứ tự initialization khi lớp con truy cập thành phần liên quan đến lớp cha như thế nào?
Bạn giải thích cách xử lý lỗi xảy ra trong static initializer và hậu quả đối với lần sử dụng class tiếp theo ra sao?
Bạn phân biệt class loading có tính lazy với việc chủ động preload class để giảm độ trễ request đầu tiên như thế nào?
Bạn giải thích vai trò của bootstrap, platform và application class loader trong Java hiện đại ra sao?
Bạn phân tích nguyên tắc parent delegation trong việc xác định class definition được nạp như thế nào?
Bạn đánh giá khi nào một custom class loader cần thay đổi chiến lược delegation và các rủi ro phát sinh ra sao?
Bạn phân tích lý do hai class có cùng binary name nhưng được định nghĩa bởi class loader khác nhau có thể không tương thích kiểu ra sao?
Bạn xử lý ClassCastException xuất hiện trong kiến trúc plugin khi tên class và source code có vẻ giống nhau ra sao?
Bạn phân biệt ClassNotFoundException với NoClassDefFoundError theo thời điểm lỗi và nguyên nhân có thể xảy ra như thế nào?
Bạn điều tra NoSuchMethodError sau khi nâng cấp thư viện dù quá trình compile đã thành công như thế nào?
Bạn phân tích cơ chế symbolic reference resolution và mối liên hệ với các lỗi linkage ở runtime ra sao?
Bạn giải thích cơ chế class unloading và những điều kiện khiến một class loader không thể được giải phóng như thế nào?
Bạn nhận diện class loader leak khi ứng dụng triển khai nóng nhiều lần hoặc tạo nhiều module plugin bằng dấu hiệu nào?
Bạn phân biệt tình huống nên dùng Class.forName, ClassLoader.loadClass và reflection theo tác động đến initialization như thế nào?
Bạn đánh giá việc sử dụng reflection hoặc MethodHandle tác động đến liên kết và tối ưu lời gọi phương thức ra sao?
Bạn phân tích cách module boundaries và quyền truy cập ảnh hưởng đến reflection và class loading trong runtime hiện đại như thế nào?
Bạn mô tả những thành phần được lưu trong JVM stack frame của mỗi lời gọi phương thức và vai trò của chúng ra sao?
Bạn phân biệt local variable array và operand stack trong frame khi thực hiện một chuỗi lệnh bytecode ra sao?
Bạn mô tả cách tham số và giá trị trả về đi qua frame khi gọi một phương thức Java như thế nào?
Bạn giải thích cách exception table hướng điều khiển đến handler khi một lệnh bytecode ném ngoại lệ như thế nào?
Bạn phân biệt Java stack, program counter và native method stack ở mức đặc tả JVM như thế nào?
Bạn xác định điều kiện gây StackOverflowError trong một chuỗi lời gọi đệ quy và cách thu thập bằng chứng ra sao?
Bạn đánh giá tác động của độ sâu lời gọi và kích thước frame lên nhu cầu bộ nhớ stack của một thread như thế nào?
Bạn phân tích sự khác nhau giữa interpreter, compiled execution và quá trình chuyển đổi giữa chúng trong HotSpot ra sao?
Bạn giải thích vai trò của return address và điểm tiếp tục thực thi khi phương thức kết thúc hoặc ném exception như thế nào?
Bạn phân biệt hành vi JVM khi truy cập phần tử mảng sai chỉ số với hành vi kiểm tra null reference ở thời điểm thực thi ra sao?
Bạn mô tả các vùng dữ liệu runtime được quy định trong JVM specification và phạm vi chia sẻ của chúng như thế nào?
Bạn phân biệt heap, JVM stack và method area dựa trên loại dữ liệu và vòng đời lưu trữ ra sao?
Bạn giải thích mối quan hệ giữa method area trong đặc tả JVM và Metaspace trong HotSpot ra sao?
Bạn so sánh cách quản lý metadata của PermGen trong HotSpot cũ và Metaspace trong HotSpot hiện đại như thế nào?
Bạn phân biệt heap memory, native memory và direct buffer memory khi điều tra tổng bộ nhớ của một tiến trình Java ra sao?
Bạn xác định vị trí logic của class metadata, static field và object instance mà không nhầm đặc tả với cách triển khai ra sao?
Bạn giải thích cách tạo đối tượng bằng bytecode new liên quan đến cấp phát bộ nhớ và gọi constructor như thế nào?
Bạn phân biệt object header, instance fields và alignment trong cách HotSpot bố trí object trên heap ra sao?
Bạn đánh giá tác động của compressed ordinary object pointers đến dung lượng heap và kích thước reference như thế nào?
Bạn kiểm chứng kích thước thực tế của một đối tượng Java khi có padding, alignment và reference fields bằng cách nào?
Bạn phân tích cách Thread Local Allocation Buffer hỗ trợ cấp phát đối tượng nhanh trong HotSpot như thế nào?
Bạn xác định khi nào một object có thể được cấp phát ngoài luồng cấp phát nhanh thông thường và ảnh hưởng đến hiệu năng ra sao?
Bạn giải thích khái niệm escape analysis và khả năng loại bỏ cấp phát qua scalar replacement như thế nào?
Bạn phân biệt giả định rằng mọi object đều cấp phát trên heap với những tối ưu thực tế có thể được JIT áp dụng ra sao?
Bạn đánh giá tác động của việc lưu giữ reference trong static collection đến tuổi thọ và khả năng thu gom object như thế nào?
Bạn thiết kế cách nhận diện heap retention do cache không giới hạn so với việc thực sự thiếu bộ nhớ cho dữ liệu hợp lệ ra sao?
Bạn phân biệt strong, soft, weak và phantom reference theo khả năng giữ đối tượng sống và mục đích sử dụng như thế nào?
Bạn giải thích cơ chế reachability và vai trò của GC roots trong việc xác định object còn sống ra sao?
Bạn xác định các loại GC roots thường gặp như thread stack, static reference và JNI handle bằng cách nào?
Bạn mô tả nguyên tắc tracing garbage collection từ tập GC roots đến các object reachable như thế nào?
Bạn phân tích sự khác biệt giữa marking, sweeping, compacting và copying theo nhu cầu bộ nhớ và thời gian dừng như thế nào?
Bạn phân tích tại sao các object tham chiếu vòng nhau vẫn có thể được một tracing garbage collector thu gom như thế nào?
Bạn phân biệt live set, allocation rate và promotion rate khi đánh giá áp lực garbage collection ra sao?
Bạn giải thích giả thuyết thế hệ trong quản lý bộ nhớ và khi nào nó có thể không phù hợp với một workload như thế nào?
Bạn đánh giá việc chọn kích thước heap dựa trên working set thay vì chỉ nhìn vào đỉnh sử dụng bộ nhớ như thế nào?
Bạn phân biệt minor GC, mixed collection và full GC trong ngữ cảnh các collector hỗ trợ những khái niệm đó ra sao?
Bạn phân tích cách bộ sưu tập object sống lâu có thể ảnh hưởng đến chi phí dọn dẹp và fragmentation như thế nào?
Bạn giải thích vai trò của remembered set và write barrier trong việc theo dõi tham chiếu giữa các vùng heap ra sao?
Bạn đánh giá đánh đổi giữa throughput, pause time và memory footprint khi chọn garbage collector như thế nào?
Bạn so sánh Serial GC, Parallel GC và G1 theo đặc điểm tải và mục tiêu vận hành ra sao?
Bạn giải thích cách G1 chia heap thành regions và đưa ra quyết định thu gom theo mục tiêu pause như thế nào?
Bạn phân tích tác động của humongous objects đối với việc quản lý region và áp lực bộ nhớ của G1 ra sao?
Bạn xác định các dấu hiệu cho thấy G1 không đạt mục tiêu pause do allocation rate hoặc remembered set quá lớn như thế nào?
Bạn so sánh mục tiêu thiết kế của ZGC và Shenandoah đối với ứng dụng cần độ trễ thấp ra sao?
Bạn đánh giá khả năng dùng collector hỗ trợ thu gom đồng thời khi workload có giới hạn CPU và heap nhỏ như thế nào?
Bạn giải thích vì sao một garbage collector có pause ngắn chưa chắc mang lại throughput tốt nhất như thế nào?
Bạn phân tích tác động của concurrent GC threads đến thời gian CPU sẵn có cho thread xử lý nghiệp vụ ra sao?
Bạn nhận diện tình trạng GC thrashing và phân biệt nó với tải CPU cao do mã nghiệp vụ như thế nào?
Bạn giải thích sự khác biệt giữa OutOfMemoryError do Java heap space, Metaspace và Direct buffer memory ra sao?
Bạn điều tra một OutOfMemoryError liên quan đến native allocation khi Java heap vẫn còn dung lượng trống như thế nào?
Bạn phân biệt tiến trình bị OOM killer của container kết thúc với trường hợp JVM tự ném OutOfMemoryError dựa trên bằng chứng nào?
Bạn thiết kế chính sách giới hạn Xmx, MaxMetaspaceSize và direct memory khi chạy trong container như thế nào?
Bạn giải thích tác dụng của -Xms, -Xmx và các tham số heap sizing lên việc khởi động và vận hành JVM như thế nào?
Bạn đánh giá lựa chọn cố định kích thước heap so với để JVM điều chỉnh theo giới hạn memory và tính chất workload ra sao?
Bạn phân tích tác động của container CPU quota đến số lượng GC threads và compiler threads được JVM lựa chọn như thế nào?
Bạn sử dụng GC logs để nhận diện tần suất, nguyên nhân và thời lượng pause theo những bước nào?
Bạn kết hợp GC logs với latency metrics để xác định pause thực sự gây chậm request như thế nào?
Bạn lựa chọn thời điểm chụp heap dump để điều tra tăng bộ nhớ mà không làm quá tải hệ thống production ra sao?
Bạn sử dụng dominator tree và retained size để tìm object giữ lại lượng bộ nhớ lớn như thế nào?
Bạn phân biệt shallow size với retained size khi đọc báo cáo heap dump ra sao?
Bạn phát hiện memory leak liên quan đến ThreadLocal khi thread pool giữ thread sống lâu qua những chỉ báo nào?
Bạn kiểm tra class loader retention và tăng Metaspace sau nhiều lần nạp plugin bằng cách nào?
Bạn sử dụng Native Memory Tracking để xác định nhóm tiêu thụ native memory trong HotSpot như thế nào?
Bạn phối hợp dữ liệu heap dump, thread dump và native memory để giải thích một tiến trình tăng RSS kéo dài ra sao?
Bạn phân tích vai trò của dữ liệu profiling trong quyết định tối ưu của JIT compiler và chi phí compile ban đầu ra sao?
Bạn mô tả mô hình tiered compilation và vai trò của các compiler tier trong HotSpot ra sao?
Bạn xác định các yếu tố khiến một phương thức được JIT compile sau nhiều lần thực thi như thế nào?
Bạn phân biệt method invocation counter và loop backedge trong việc phát hiện đoạn mã nóng ra sao?
Bạn giải thích cách method inlining có thể cải thiện hiệu năng và những đánh đổi với code cache như thế nào?
Bạn phân tích ảnh hưởng của polymorphic call site đến khả năng inline và tối ưu lời gọi ảo ra sao?
Bạn giải thích cơ chế speculative optimization và việc deoptimization khi giả định runtime không còn đúng như thế nào?
Bạn nhận diện một hiện tượng deoptimization lặp lại ảnh hưởng đến latency bằng những công cụ quan sát nào?
Bạn đánh giá tình huống benchmark chưa warm-up đầy đủ khiến kết quả chủ yếu đo interpreter hoặc quá trình compile như thế nào?
Bạn phân biệt on-stack replacement với biên dịch phương thức thông thường trong việc tăng tốc vòng lặp dài ra sao?
Bạn giải thích ảnh hưởng của escape analysis lên lock elimination và chi phí đồng bộ của một đối tượng như thế nào?
Bạn xác định những đặc điểm của đoạn mã xử lý dữ liệu có thể tạo cơ hội cho vectorization hoặc JVM intrinsic ra sao?
Bạn đánh giá tác động của reflection, dynamic proxy và invokedynamic lên khả năng tối ưu đường gọi nóng như thế nào?
Bạn kiểm tra trạng thái code cache và dấu hiệu compiler không thể tạo thêm mã máy tối ưu như thế nào?
Bạn nhận diện nguy cơ JIT loại bỏ công việc trong một vòng lặp benchmark tự đo bằng System.nanoTime như thế nào?
Bạn thiết kế một benchmark JMH để tránh dead-code elimination và constant folding làm sai kết quả như thế nào?
Bạn lựa chọn thời gian warm-up, số lần fork và cách tạo dữ liệu đầu vào trong JMH để kết quả đáng tin cậy ra sao?
Bạn phân biệt tối ưu trên microbenchmark với cải thiện hiệu năng end-to-end của ứng dụng theo những yếu tố nào?
Bạn giải thích mối liên hệ giữa Java threads và JVM runtime khi hệ điều hành lên lịch thực thi như thế nào?
Bạn phân biệt Java Memory Model với các quyết định bố trí đối tượng trên heap hoặc cache CPU như thế nào?
Bạn sử dụng quan hệ happens-before để suy luận việc một thread nhìn thấy cập nhật từ thread khác như thế nào?
Bạn giải thích cách volatile tạo ràng buộc về visibility và ordering mà không biến nhiều thao tác thành nguyên tử như thế nào?
Bạn phân tích tác động của synchronized đến monitor ownership, mutual exclusion và memory visibility ra sao?
Bạn phân biệt sự đồng bộ ở mức bytecode monitorenter/monitorexit với cơ chế synchronized method trong JVM như thế nào?
Bạn giải thích các trạng thái BLOCKED, WAITING và TIMED_WAITING trong thread dump dưới góc nhìn contention như thế nào?
Bạn sử dụng thread dump để phát hiện deadlock có vòng chờ monitor giữa nhiều thread như thế nào?
Bạn phân biệt deadlock, livelock và thread starvation dựa trên hành vi thực thi quan sát được ra sao?
Bạn phân tích lý do một biến đếm dùng toán tử ++ vẫn có race condition dù các thread đều thấy cùng một object như thế nào?
Bạn giải thích yêu cầu safe publication của object và ảnh hưởng của final fields trong Java Memory Model như thế nào?
Bạn đánh giá nguy cơ tham chiếu this thoát ra trước khi constructor hoàn thành đối với tính an toàn luồng ra sao?
Bạn phân biệt thread confinement và thread safety khi thiết kế đối tượng chia sẻ cho nhiều luồng như thế nào?
Bạn kiểm tra hiệu ứng false sharing giữa các biến được cập nhật bởi nhiều thread qua những phép đo nào?
Bạn đánh giá tác động của số lượng platform threads lên stack memory và chi phí context switching như thế nào?
Bạn so sánh cơ chế scheduling của virtual threads với platform threads trong các tình huống I/O blocking như thế nào?
Bạn giải thích hiện tượng pinning của virtual thread trong những trường hợp runtime hoặc native operation không thể unmount như thế nào?
Bạn dùng JFR hoặc thread dump để chẩn đoán virtual threads bị chặn hoặc pinning kéo dài ra sao?
Bạn phân tích ảnh hưởng của thread pool quá lớn đến CPU saturation và garbage collection trong một dịch vụ Java như thế nào?
Bạn xác định cách điều chỉnh ActiveProcessorCount hoặc giới hạn CPU để đánh giá quyết định cấu hình runtime ra sao?
Bạn giải thích vai trò của safepoint trong việc phối hợp thread khi JVM thực hiện các tác vụ quản lý runtime ra sao?
Bạn phân biệt safepoint pause với thời gian thực hiện garbage collection trong phân tích độ trễ như thế nào?
Bạn dùng Java Flight Recorder để thu thập sự kiện allocation, GC, lock contention và compilation khi chẩn đoán ứng dụng như thế nào?
Bạn phối hợp JFR và Java Mission Control để tìm các đoạn mã gây cấp phát quá nhiều đối tượng như thế nào?
Bạn so sánh sampling profiler với instrumentation profiler về overhead và loại câu hỏi hiệu năng có thể trả lời ra sao?
Bạn phân biệt CPU flame graph, allocation profile và blocking profile để chọn công cụ cho một sự cố cụ thể như thế nào?
Bạn xác định khi nào cần thu thập thread dump nhiều lần thay vì chỉ một thời điểm để đánh giá nghẽn luồng như thế nào?
Bạn phân tích cách các JVM flags thay đổi theo phiên bản có thể làm một bộ tham số tuning cũ trở nên không phù hợp ra sao?
Bạn thiết kế cách kiểm chứng hiệu quả của thay đổi GC hoặc JIT flags trong staging trước khi triển khai production như thế nào?
Một dịch vụ chậm vài giây ở request đầu nhưng nhanh sau đó, bạn sẽ phân biệt class loading, JIT warm-up và khởi tạo dependency như thế nào?
Một ứng dụng tăng RSS liên tục dù heap usage ổn định, bạn sẽ điều tra direct buffers, Metaspace và native allocations ra sao?
Một bản nâng cấp thư viện gây NoSuchMethodError ở production nhưng không xuất hiện khi build, bạn sẽ truy tìm xung đột class loading hoặc binary compatibility như thế nào?
Một tiến trình thường xuyên full GC dù heap đã tăng lớn, bạn sẽ phân tích live set, allocation rate và retained objects ra sao?
Một ứng dụng có pause GC thấp nhưng tail latency vẫn tăng cao, bạn sẽ kiểm tra safepoint, lock contention và CPU throttling như thế nào?
Một hệ thống chạy tốt ngoài container nhưng bị OOM killer trong Kubernetes, bạn sẽ đánh giá heap sizing và bộ nhớ ngoài heap ra sao?
Một benchmark JMH cho thấy cải thiện lớn nhưng throughput production không tăng, bạn sẽ xác định sai lệch về workload và bottleneck như thế nào?
Sau khi bật virtual threads, latency tăng dưới tải cao, bạn sẽ kiểm tra pinning, giới hạn backend và contention như thế nào?
Bạn xây dựng tiêu chí nghiệm thu một thay đổi cấu hình JVM từ GC logs, JFR, throughput, p99 latency và memory footprint như thế nào?
