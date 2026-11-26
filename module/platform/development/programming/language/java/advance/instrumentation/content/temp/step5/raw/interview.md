Bạn giải thích Java Instrumentation API cho phép quan sát hoặc biến đổi hành vi chương trình ở những thời điểm nào trong vòng đời JVM?
Bạn phân biệt Java Agent với thư viện logging thông thường về cách tích hợp vào ứng dụng đang chạy như thế nào?
Bạn sẽ mô tả vai trò của java.lang.instrument.Instrumentation đối với một Java Agent ra sao?
Bạn phân biệt compile-time weaving, load-time instrumentation và retransformation lúc chạy theo điểm can thiệp nào?
Bạn giải thích Java Agent khác Java Virtual Machine Tool Interface (JVMTI) về cấp độ API và phạm vi sử dụng như thế nào?
Bạn sẽ lựa chọn instrumentation thay vì AOP proxy khi muốn quan sát phương thức của thư viện bên thứ ba theo tiêu chí nào?
Bạn phân biệt việc biến đổi bytecode với dynamic proxy về khả năng áp dụng cho class không do ứng dụng tạo như thế nào?
Bạn phân tích tại sao agent có thể ảnh hưởng đến tính đúng đắn của code dù không sửa source files ra sao?
Bạn sẽ xác định khi nào nên dùng Java Flight Recorder thay cho việc chèn advice vào mọi method như thế nào?
Bạn phân biệt tracing bằng sampling với chèn bộ đếm vào mỗi invocation về overhead và độ đầy đủ dữ liệu như thế nào?
Bạn sẽ chọn phạm vi các classes cần instrument dựa trên yêu cầu quan sát và rủi ro tương thích như thế nào?
Bạn phân tích vì sao instrument cả JDK internal classes dễ làm tăng rủi ro recursion hoặc incompatibility ra sao?
Bạn sẽ tách phần transformer logic, telemetry exporter và config loader trong kiến trúc một agent ra sao?
Bạn mô tả cách JVM gọi premain trước application main khi có tùy chọn -javaagent như thế nào?
Bạn phân biệt premain(String, Instrumentation) và premain chỉ nhận agent arguments theo khả năng truy cập Instrumentation ra sao?
Bạn sẽ đóng gói agent JAR với manifest có thuộc tính Premain-Class đúng như thế nào?
Bạn phân biệt Main-Class và Premain-Class trong một JAR có thể chạy như tool hoặc làm agent ra sao?
Bạn sẽ xử lý chuỗi cấu hình truyền sau dấu bằng của -javaagent mà không làm lộ token qua process arguments như thế nào?
Bạn phân tích hậu quả khi premain ném exception trước khi application khởi động hoàn toàn như thế nào?
Bạn sẽ kiểm tra lỗi agent JAR không được JVM nhận do sai manifest hoặc entry method signature như thế nào?
Bạn mô tả cách nhiều -javaagent options ảnh hưởng thứ tự khởi tạo và registration transformer như thế nào?
Bạn sẽ xác định rủi ro chạy hai agents cùng biến đổi một class nếu không có quy tắc phối hợp ra sao?
Bạn phân biệt agentmain(String, Instrumentation) với premain theo thời điểm agent được nạp như thế nào?
Bạn sẽ cấu hình manifest Agent-Class để JVM biết entry point khi nạp agent động như thế nào?
Bạn sẽ thiết kế agent dùng chung initialization logic cho premain và agentmain mà không đăng ký transformer hai lần ra sao?
Bạn phân tích vì sao runtime attach sau khi class đã load thường cần một chiến lược khác với startup instrumentation như thế nào?
Bạn sẽ lựa chọn hỗ trợ dynamic attach hay yêu cầu startup -javaagent dựa trên chính sách vận hành nào?
Bạn phân biệt Java Agent đóng gói các helper dependencies qua shading với sử dụng classpath có sẵn của ứng dụng như thế nào?
Bạn sẽ quyết định có cần relocation package trong agent JAR để tránh xung đột dependencies theo tiêu chí nào?
Bạn phân tích nguy cơ premain gọi backend mạng đồng bộ làm tăng startup latency hoặc thất bại khởi động ra sao?
Bạn mô tả Instrumentation.addTransformer đăng ký một ClassFileTransformer để JVM gọi ở những tình huống nào?
Bạn phân biệt các tham số className, loader và ProtectionDomain của ClassFileTransformer.transform theo thông tin cung cấp ra sao?
Bạn sẽ chuyển className dạng dấu gạch chéo của JVM thành tên Java để so khớp package mà không nhầm nested classes như thế nào?
Bạn giải thích vì sao tham số loader trong transform có thể là null đối với lớp từ bootstrap loader như thế nào?
Bạn sẽ nhận biết lần load đầu và lần retransformation qua classBeingRedefined trong callback như thế nào?
Bạn phân biệt transform có tham số Module với overload cũ theo khả năng xác định nguồn module của class ra sao?
Bạn sẽ xác định cách transformer viết cho JDK cũ tương thích overload transform mới theo API contract như thế nào?
Bạn mô tả classfileBuffer là đầu vào bytecode và quy tắc trả null khi không cần thay đổi như thế nào?
Bạn phân biệt trả byte array mới với trả null từ transform theo kết quả JVM sử dụng ra sao?
Bạn sẽ lọc những classes cần instrument theo module, class loader và binary name như thế nào?
Bạn phân tích rủi ro matcher theo tiền tố package quá rộng khiến chính thư viện agent cũng bị instrument ra sao?
Bạn sẽ loại trừ classes do instrumentation library tự sinh để không kích hoạt vòng lặp transformer như thế nào?
Bạn mô tả thứ tự các ClassFileTransformer được đăng ký có thể ảnh hưởng đầu vào của transformer kế tiếp như thế nào?
Bạn sẽ phân tích cách transformers có và không hỗ trợ retransformation phối hợp khi một class được biến đổi nhiều lần ra sao?
Bạn sẽ xác định vì sao không thể mặc định mỗi class chỉ nhận một lần callback transform suốt đời JVM như thế nào?
Bạn phân tích rủi ro biến đổi một method nhiều lần làm xuất hiện advice hoặc logging lặp ra sao?
Bạn sẽ áp dụng nguyên tắc idempotent transformation khi nhận lại class bytes đã có instrumentation như thế nào?
Bạn phân biệt disable future transforms với việc hoàn tác bytecode của class đã load trước đó ra sao?
Bạn sẽ sử dụng Instrumentation.removeTransformer khi thay đổi cấu hình agent theo điều kiện nào?
Bạn phân tích vì sao removeTransformer không tự đảm bảo các lớp đã biến đổi trở về nguyên trạng ra sao?
Bạn sẽ xử lý IllegalClassFormatException hoặc bytecode không hợp lệ trong callback mà không gây cascade failures như thế nào?
Bạn sẽ tổ chức logging khi transform lỗi mà không giữ nguyên toàn bộ class bytes trong memory ra sao?
Bạn phân tích rủi ro gọi logger hoặc class loader từ transformer gây circular class loading như thế nào?
Bạn sẽ kiểm tra hiện tượng deadlock do transform giữ global lock rồi tải thêm class của framework ra sao?
Bạn mô tả vì sao ClassFileTransformer cần thread-safe khi JVM load classes trên nhiều threads đồng thời như thế nào?
Bạn sẽ xác định dữ liệu nào được cache theo class loader identity để không nhầm classes có cùng tên ra sao?
Bạn phân biệt lỗi class verification sau transform với lỗi exception do chính transformer ném ra như thế nào?
Bạn sẽ thiết kế timeout hoặc giới hạn công việc biến đổi để class loading không bị chặn bởi I/O remote ra sao?
Bạn phân tích rủi ro transformer mở file hoặc tạo network connection trên mỗi class load gây bottleneck ra sao?
Bạn sẽ chọn cách đo transform count và failure count mà không tự kích hoạt instrumentation của metrics exporter như thế nào?
Bạn giải thích Instrumentation.isRetransformClassesSupported phản ánh khả năng retransformation ở runtime như thế nào?
Bạn sẽ xác định ý nghĩa của Can-Retransform-Classes trong agent manifest trước khi gọi addTransformer với cờ true ra sao?
Bạn phân biệt addTransformer(transformer, true) với addTransformer(transformer) theo callback nào được phép trong retransformation?
Bạn mô tả Instrumentation.retransformClasses được dùng để cập nhật các class đã load trong điều kiện nào?
Bạn sẽ kiểm tra Instrumentation.isModifiableClass trước khi chọn danh sách classes cần retransform như thế nào?
Bạn phân biệt Instrumentation.getAllLoadedClasses với getInitiatedClasses(ClassLoader) khi khảo sát class visibility như thế nào?
Bạn sẽ xác định tại sao class đã load vẫn có thể không modifiable ở JVM đang dùng như thế nào?
Bạn phân tích vì sao retransform một tập classes lớn có thể gây CPU spikes hoặc stop-the-world effects ra sao?
Bạn sẽ tổ chức retransformation theo batches và điều kiện dừng để hạn chế gián đoạn runtime như thế nào?
Bạn mô tả vai trò của retransformation-capable transformers khi JVM tính lại class bytes ra sao?
Bạn phân biệt hành vi transformer không hỗ trợ retransformation với transformer hỗ trợ khi JVM thực hiện retransformClasses như thế nào?
Bạn sẽ đánh giá vì sao output từng được tạo bởi retransformation-incapable transformer có thể được tái áp dụng mà không gọi lại nó ra sao?
Bạn sẽ xác định cách phối hợp nhiều Java Agents khi một agent gọi retransformation sau khi agent khác đã instrument class như thế nào?
Bạn phân tích rủi ro lưu bản class bytes nguồn không chính xác dẫn tới rollback áp dụng nhầm biến đổi ra sao?
Bạn mô tả Instrumentation.redefineClasses và ClassDefinition cho phép cung cấp lớp bytes mới trực tiếp như thế nào?
Bạn phân biệt redefineClasses với retransformClasses về nguồn bytes và cách dùng registered transformers ra sao?
Bạn sẽ kiểm tra Instrumentation.isRedefineClassesSupported và Can-Redefine-Classes trước khi yêu cầu redefinition như thế nào?
Bạn sẽ xác định hạn chế của JVM khi redefineClasses muốn thêm field, xóa method hoặc đổi superclass ra sao?
Bạn phân tích tại sao một class được redefine không làm mọi instance hiện có khởi tạo lại từ đầu như thế nào?
Bạn sẽ đánh giá hành vi method đang chạy khi runtime thay đổi implementation bằng redefinition ra sao?
Bạn phân biệt UnmodifiableClassException và UnsupportedOperationException trong các lỗi thay đổi bytecode lúc chạy như thế nào?
Bạn sẽ thiết kế cơ chế báo lỗi khi một class thuộc nhóm JVM không hỗ trợ redefine hoặc retransform như thế nào?
Bạn phân tích vì sao array classes và primitive classes cần được xử lý khác regular modifiable classes ra sao?
Bạn sẽ lựa chọn restart JVM, redefineClasses hay retransformClasses dựa trên loại thay đổi và khả năng rollback nào?
Bạn sẽ phân tích tác động của retransformation đối với JIT compilation và warm-up của hot methods như thế nào?
Bạn sẽ thiết kế feature flag tắt logic advice đã chèn mà không bắt buộc biến đổi lại mọi lớp như thế nào?
Bạn phân tích vì sao transformer đăng ký sau khi class đã load không tự động tác động lên các methods đang chạy ra sao?
Bạn sẽ kiểm thử nhiều lần retransform một class để xác minh method behavior không bị nhân đôi như thế nào?
Bạn sẽ xây dựng cơ chế audit mọi yêu cầu redefinition trong production nhằm truy vết phiên bản agent và class ra sao?
Bạn giải thích class identity gồm binary name và defining ClassLoader ảnh hưởng instrumentation như thế nào?
Bạn phân biệt bootstrap, platform và application class loaders trong các tình huống agent gặp lớp như thế nào?
Bạn sẽ xử lý hai classes cùng binary name nhưng thuộc các class loaders khác nhau theo cache key nào?
Bạn phân tích nguy cơ lưu class metadata bằng static Map giữ strong references tới application ClassLoader ra sao?
Bạn sẽ thiết kế weak references và cache eviction để tránh ClassLoader leaks khi ứng dụng được redeploy như thế nào?
Bạn mô tả appendToBootstrapClassLoaderSearch nhận JarFile và mở rộng nơi tìm helper classes ra sao?
Bạn phân biệt appendToBootstrapClassLoaderSearch với appendToSystemClassLoaderSearch về nơi class helpers có thể được tìm thấy như thế nào?
Bạn sẽ quyết định khi nào cần bootstrap helper injection cho advice trong các classes do JDK nạp ra sao?
Bạn phân tích nguy cơ helper class cùng tên được định nghĩa bởi hai loaders khiến ClassCastException hoặc LinkageError như thế nào?
Bạn sẽ nhận diện conflict do shading khi agent và ứng dụng có các phiên bản dependency khác nhau như thế nào?
Bạn phân biệt class loader delegation với module readability trong quá trình advice tham chiếu runtime helpers ra sao?
Bạn sẽ kiểm tra class thuộc named module hay unnamed module từ tham số Module trong transform như thế nào?
Bạn mô tả Instrumentation.redefineModule điều chỉnh module reads, exports hoặc opens theo giới hạn nào?
Bạn sẽ kiểm tra Instrumentation.isModifiableModule trước khi cập nhật module graph như thế nào?
Bạn phân biệt exports cho public access với opens cho deep reflection khi chạy instrumentation như thế nào?
Bạn phân tích rủi ro mở quá rộng những JDK internals bằng redefineModule làm thay đổi security boundary ra sao?
Bạn sẽ xác định tối thiểu những package cần mở khi agent instrument class thuộc một named module như thế nào?
Bạn sẽ chẩn đoán IllegalAccessError khi bytecode sau transform gọi helper class từ module không đọc được như thế nào?
Bạn phân biệt IllegalAccessException do reflection với IllegalAccessError ở linkage theo nguyên nhân nào?
Bạn sẽ thiết kế agent hoạt động trong ứng dụng classpath mode và Java Platform Module System (JPMS) như thế nào?
Bạn phân tích vì sao generated helper type của Byte Buddy có thể gặp module access constraints khác target class như thế nào?
Bạn sẽ lựa chọn vị trí inject helper vào class loader hoặc bootstrap search path theo compatibility nào?
Bạn mô tả thread context class loader khác defining class loader như thế nào trong một ứng dụng plugin architecture?
Bạn sẽ tránh dùng Class.forName với context loader sai khi advice resolve helper class ra sao?
Bạn phân tích vì sao className giống nhau trong web application containers không đồng nghĩa bytecode hoặc method signatures giống nhau ra sao?
Bạn sẽ xây dựng test isolation với hai class loaders độc lập để đảm bảo transformer không trộn state ra sao?
Bạn giải thích ASM được sử dụng trong ClassFileTransformer để phân tích và thay đổi bytecode theo quy trình nào?
Bạn phân biệt ASM ClassVisitor và Tree API theo khả năng biến đổi cấu trúc class như thế nào?
Bạn sẽ lựa chọn MethodVisitor hoặc AdviceAdapter khi cần chèn logic vào method entry và exit ra sao?
Bạn sẽ xử lý instrumentation của constructor so với method thông thường để không dùng đối tượng trước khi được khởi tạo như thế nào?
Bạn phân biệt các vị trí instrument method <init> và <clinit> theo tác động tới initialization ra sao?
Bạn sẽ kiểm tra method descriptor và access flags trước khi đặt advice lên phương thức theo điều kiện nào?
Bạn mô tả ClassWriter.COMPUTE_MAXS giúp tính lại yêu cầu operand stack và local variables như thế nào?
Bạn phân biệt ClassWriter.COMPUTE_FRAMES với COMPUTE_MAXS khi bytecode mới thay đổi control flow ra sao?
Bạn phân tích vì sao giải quyết common superclass sai khi tính frames có thể gây VerifyError trong custom class loader ra sao?
Bạn sẽ xác minh StackMapTable sau khi ASM sửa branching instructions theo tiêu chí nào?
Bạn sẽ sử dụng CheckClassAdapter để phát hiện lỗi cấu trúc bytecode trước khi JVM nạp class như thế nào?
Bạn phân biệt ClassNotFoundException khi resolve helper với VerifyError do bytecode sai kiểu operand stack ra sao?
Bạn sẽ dùng javap -c và javap -v để so sánh method body trước/sau instrumentation ra sao?
Bạn mô tả Byte Buddy AgentBuilder hỗ trợ chọn types và đăng ký transformer theo mô hình nào?
Bạn phân biệt dùng Byte Buddy Advice với MethodDelegation theo vị trí chèn code và helper dependencies ra sao?
Bạn sẽ thiết kế Advice xử lý normal exit và exceptional exit mà không thay đổi exception của business method như thế nào?
Bạn phân tích vì sao advice ghi metrics ở method exit phải được thực thi cả khi method ném exception ra sao?
Bạn sẽ tránh instrumentation làm thay đổi return values hoặc modify arguments ngoài mục tiêu quan sát như thế nào?
Bạn phân biệt rebase, redefine và retransform của thư viện bytecode với những giới hạn JVM thực tế như thế nào?
Bạn sẽ xác định cách loại trừ synthetic classes, bridge methods hoặc agent helpers trong type/method matcher ra sao?
Bạn phân tích nguy cơ instrument cả framework proxy và target method khiến cùng request được ghi telemetry hai lần như thế nào?
Bạn sẽ đo duration của CompletionStage theo thời gian hoàn tất tác vụ thay vì chỉ thời gian method tạo stage như thế nào?
Bạn phân biệt timing của synchronous method và reactive Publisher khi code chạy sau thời điểm gọi method như thế nào?
Bạn sẽ chọn điểm instrument JDBC, HTTP client và message broker để tránh tạo trùng spans theo yêu cầu nào?
Bạn phân tích rủi ro ASM làm sai line number attributes khiến stack trace hoặc profiler khó đối chiếu source ra sao?
Bạn sẽ xác nhận output class file version tương thích với JDK mục tiêu khi thêm ASM transformations như thế nào?
Bạn sẽ đánh giá khi nào sử dụng Javassist thay cho ASM hoặc Byte Buddy trong một Java Agent ra sao?
Bạn giải thích Attach API hỗ trợ Java Agent được nạp vào một JVM đang chạy trong những điều kiện nào?
Bạn sẽ mô tả vai trò của com.sun.tools.attach.VirtualMachine trong việc kết nối tới tiến trình mục tiêu như thế nào?
Bạn phân biệt VirtualMachine.attach với loadAgent theo các bước của dynamic attach ra sao?
Bạn sẽ kiểm tra chính sách JVM và quyền hệ điều hành trước khi attach vào một process production như thế nào?
Bạn phân tích vì sao một JDK có thể hạn chế hoặc cảnh báo dynamic agent loading trong các phiên bản mới ra sao?
Bạn sẽ đánh giá trường hợp self-attach không được phép dù user có quyền truy cập tiến trình như thế nào?
Bạn sẽ quyết định sử dụng startup -javaagent thay cho dynamic attach khi production policy không cho nạp mã mới ra sao?
Bạn phân biệt policy về quyền attach với quyền truy cập telemetry endpoint sau khi agent đã chạy như thế nào?
Bạn sẽ kiểm tra provenance, checksum và phiên bản agent JAR trước khi triển khai lên production như thế nào?
Bạn phân tích rủi ro Java Agent không tin cậy có thể thực thi mã với quyền của ứng dụng đang chạy như thế nào?
Bạn sẽ giới hạn secrets hoặc credentials mà agent nhận qua arguments, environment và exporter configuration như thế nào?
Bạn phân tích nguy cơ chèn header Authorization hoặc SQL parameters nhạy cảm vào telemetry spans ra sao?
Bạn sẽ xây dựng quy tắc redaction trước khi xuất dữ liệu thu được từ instrumented methods như thế nào?
Bạn phân biệt authentication của backend telemetry với authorization để thay đổi cấu hình agent theo ranh giới nào?
Bạn sẽ kiểm soát quyền trigger retransformation hoặc redefinition trong ứng dụng production như thế nào?
Bạn phân tích rủi ro thay đổi agent config từ một nguồn chưa tin cậy khiến matcher instrument class ngoài ý muốn ra sao?
Bạn sẽ kiểm thử agent không vô hiệu hóa security checks hoặc nuốt exceptions trong code ứng dụng như thế nào?
Bạn mô tả threat model của bytecode-generated helper khác gì một thư viện Java thông thường như thế nào?
Bạn sẽ xác định cách audit phát hiện agent ngoài allowlist khi kiểm tra JVM startup arguments hoặc thông tin runtime ra sao?
Bạn phân tích nguy cơ mở module internals chỉ vì muốn xử lý một annotation riêng của framework ra sao?
Bạn sẽ lên kế hoạch rollback khi một bản agent mới gây lỗi linkage ngay sau startup như thế nào?
Bạn sẽ thiết kế replay protection hoặc sampling policy khi telemetry event được gửi lại nhiều lần từ queue như thế nào?
Bạn giải thích Instrumentation.getObjectSize cung cấp ước lượng shallow size của object như thế nào?
Bạn phân biệt shallow object size với retained size của object graph khi phân tích memory usage ra sao?
Bạn sẽ xác định vì sao getObjectSize có thể phụ thuộc layout và JVM implementation như thế nào?
Bạn mô tả cách đo startup overhead của premain và ClassFileTransformer trên ứng dụng có nhiều classes ra sao?
Bạn phân biệt throughput overhead và tail latency overhead của một agent đang chạy ổn định như thế nào?
Bạn sẽ xây dựng benchmark so sánh workload không agent với workload có agent theo phương pháp nào?
Bạn phân tích nguy cơ advice tạo object mới trên hot path dẫn tới GC pressure và p99 latency cao ra sao?
Bạn sẽ phân biệt chi phí ghi timestamp trong method advice với chi phí xuất Span qua network như thế nào?
Bạn sẽ dùng JMH để đánh giá overhead nhưng kiểm soát JIT warm-up và dead-code elimination như thế nào?
Bạn mô tả cách JFR giúp xác định class loading và CPU hotspots liên quan agent ra sao?
Bạn sẽ lựa chọn sampling hoặc adaptive instrumentation khi QPS quá lớn theo tiêu chí nào?
Bạn phân tích rủi ro exporter gửi telemetry đồng bộ làm block business thread khi downstream outage ra sao?
Bạn sẽ thiết kế bounded queue và backpressure policy để agent không tạo memory growth vô hạn như thế nào?
Bạn phân biệt drop telemetry với backpressure làm chậm ứng dụng theo yêu cầu SLO nào?
Bạn sẽ dùng Micrometer đo transform duration, class count và runtime advice overhead theo metric categories nào?
Bạn phân tích vì sao đặt user ID hoặc raw URL chứa token vào metrics labels tạo cardinality cao và rủi ro riêng tư ra sao?
Bạn sẽ thiết kế thread-safe metrics counters trong transformer mà không giữ global lock lâu như thế nào?
Bạn phân biệt ThreadLocal context propagation trong platform threads với khả năng dùng virtual threads theo yêu cầu nào?
Bạn sẽ kiểm tra ThreadLocal cleanup khi advice gặp exception hoặc thread pool tái sử dụng worker như thế nào?
Bạn phân tích vì sao một agent giữ ClassLoader strong references làm metaspace usage tăng sau mỗi redeploy ra sao?
Bạn sẽ tìm ClassLoader leak qua heap dump hoặc JFR trong môi trường test có nhiều lần reload như thế nào?
Bạn sẽ đo safepoint hoặc JIT deoptimization impact khi retransformation hàng loạt như thế nào?
Bạn phân tích vì sao latency trung bình không đủ để nhận ra agent làm tăng GC pause và p99 ra sao?
Bạn sẽ tổ chức canary rollout với feature flags để so sánh SLO của hai nhóm workload tương đương như thế nào?
Bạn sẽ tránh telemetry recursion khi agent instrument cả exporter, logger hoặc HTTP transport của chính nó ra sao?
Bạn sẽ thiết kế điều kiện tự giảm mức instrumentation khi overhead vượt ngưỡng nhưng vẫn không ảnh hưởng business semantics ra sao?
Bạn phân biệt unit test transformer với integration test chạy forked JVM có -javaagent theo mục tiêu xác minh nào?
Bạn sẽ kiểm tra Premain-Class, Agent-Class và capability manifest flags từ JAR artifact sau đóng gói như thế nào?
Bạn phân tích vì sao gọi trực tiếp ClassFileTransformer.transform trong unit test chưa chứng minh JVM thực sự load agent ra sao?
Bạn sẽ dùng Mockito để giả lập Instrumentation trong unit test registration logic nhưng cần integration tests nào để xác minh VM behavior?
Bạn sẽ tạo test cho class không thuộc matcher để kiểm tra transformer giữ nguyên bytecode như thế nào?
Bạn sẽ xác nhận bytecode sau transform bằng CheckClassAdapter hoặc load class trong JVM thử nghiệm ra sao?
Bạn sẽ so sánh return values, thrown exceptions và side effects trước/sau advice trong regression test như thế nào?
Bạn phân tích vì sao kiểm thử happy-path chưa đủ chứng minh advice không nuốt exception hoặc thay đổi finally blocks ra sao?
Bạn sẽ kiểm tra agent không instrument cùng method hai lần sau nhiều lần retransformation như thế nào?
Bạn sẽ kiểm thử hai class loaders nạp cùng class name nhưng transformer phải lưu state riêng theo cách nào?
Bạn sẽ xác minh transformer không gây recursion khi nó phải load helper class trong quá trình transform ra sao?
Bạn sẽ kiểm tra loader null cho bootstrap class và đường đi của helper resolution trong một forked JVM ra sao?
Bạn phân biệt điều kiện skip test khi retransformation không được hỗ trợ với lỗi thực thi của agent ra sao?
Bạn sẽ thử retransformClasses trên classes đã load để xác nhận transformer capable được gọi theo hợp đồng nào?
Bạn sẽ tạo test negative cho class không modifiable nhưng vẫn bảo đảm agent không crash cả JVM như thế nào?
Bạn sẽ kiểm thử redefineClasses đổi method body hợp lệ và xử lý attempt thay đổi field schema như thế nào?
Bạn phân tích vì sao removeTransformer test phải kiểm tra future transforms và không giả định rollback classes đã biến đổi ra sao?
Bạn sẽ kiểm thử nhiều agents với thứ tự transformer khác nhau nhằm phát hiện output bytecode phụ thuộc không chủ đích như thế nào?
Bạn sẽ dùng JPMS module test để phát hiện lỗi module opens hoặc helper readability khi chạy instrumentation ra sao?
Bạn sẽ xây dựng CI matrix JDK versions để phát hiện class file format và dynamic attach policy khác nhau ra sao?
Bạn phân tích vì sao test performance agent phải tách thời gian JVM startup khỏi thời gian steady-state như thế nào?
Bạn sẽ kiểm tra application vẫn hoàn thành request khi telemetry exporter bị timeout hoặc disconnected như thế nào?
Bạn sẽ xác minh không có password, API token hay PII trong logs và spans của test instrumentation ra sao?
Bạn sẽ chạy test trên constructors, static initializers và synchronized methods để phát hiện VerifyError hoặc deadlock ra sao?
Bạn sẽ dùng heap profiling để phát hiện các ClassLoader không được GC do agent caches như thế nào?
Bạn sẽ kiểm tra release agent JAR có đúng dependencies được shading và không có duplicate class conflicts ra sao?
Bạn sẽ thiết kế smoke test trong container có JVM options giống production để thử -javaagent startup như thế nào?
Bạn sẽ xác nhận agentmain xử lý dynamic attach riêng mà không nhầm với luồng premain startup ra sao?
Bạn sẽ xây dựng checklist release đánh giá manifest, bytecode correctness, performance, security và rollback như thế nào?
Nếu JVM báo thiếu Premain-Class dù agent JAR chứa premain, bạn sẽ kiểm tra manifest build output như thế nào?
Nếu premain đã chạy nhưng một target class không có advice, bạn sẽ kiểm tra matcher, class loader và thời điểm class load ra sao?
Nếu agent được attach sau startup nhưng không instrument được những classes cũ, bạn sẽ kiểm tra retransformClasses và khả năng VM ra sao?
Nếu ClassFileTransformer.transform nhận loader null và helper không resolve, bạn sẽ thiết kế bootstrap helper injection như thế nào?
Nếu bytecode mới làm JVM ném VerifyError, bạn sẽ kiểm tra StackMapTable, method descriptors và control flow như thế nào?
Nếu constructor instrumented làm xuất hiện lỗi verifier liên quan this chưa khởi tạo, bạn sẽ thay đổi vị trí advice ra sao?
Nếu method ném exception nhưng advice thay đổi exception type, bạn sẽ kiểm tra exceptional exit logic như thế nào?
Nếu runtime có hai lần ghi metrics cho cùng một request do proxy và target method cùng được instrument, bạn sẽ thay đổi instrumentation point ra sao?
Nếu mỗi lần retransform lại tăng số timer calls trong method, bạn sẽ thiết kế cơ chế tránh double instrumentation như thế nào?
Nếu redefineClasses từ chối thêm field mới, bạn sẽ phân biệt giới hạn class schema của JVM với bytecode không hợp lệ ra sao?
Nếu hai web applications có cùng binary name nhưng khác class loaders bị lẫn metadata, bạn sẽ sửa cache keys ra sao?
Nếu agent inject helper từ classpath sai gây LinkageError, bạn sẽ kiểm tra shading, loader và module graph như thế nào?
Nếu JVM mới từ chối dynamic attach vốn từng hoạt động, bạn sẽ kiểm tra attach policy và phương án startup agent ra sao?
Nếu startup latency tăng mạnh khi bật agent, bạn sẽ tách thời gian premain, transform và helper initialization như thế nào?
Nếu p99 request latency tăng dù CPU trung bình thấp, bạn sẽ điều tra GC pressure, lock contention và exporter blocking ra sao?
Nếu agent giữ class loaders sau nhiều lần redeploy, bạn sẽ kiểm tra caches, listeners và cleanup threads như thế nào?
Nếu remote collector ngừng đáp ứng khiến worker threads bị chặn, bạn sẽ thiết kế bounded asynchronous export và fail-open telemetry ra sao?
Nếu một advice ghi Authorization header vào tracing spans, bạn sẽ thiết kế redaction và regression tests như thế nào?
Nếu unit test ASM transformer PASS nhưng JVM thật báo IllegalAccessError, bạn sẽ bổ sung test helper visibility và JPMS như thế nào?
Nếu triển khai Java Agent production có startup và optional attach, bạn sẽ thiết kế entry points, ClassFileTransformer, retransform, loaders, QA và SLO guardrails như thế nào?
