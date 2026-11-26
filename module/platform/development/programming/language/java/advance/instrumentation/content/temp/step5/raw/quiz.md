Câu 1. Khi cần chạy Java Agent từ lúc ứng dụng bắt đầu, tùy chọn JVM nào phù hợp?
A. Dùng -classpath:agent.jar để JVM gọi premain sớm
B. Dùng -agentlib:agent.jar để đọc manifest Java agent
C. Dùng -javaagent:agent.jar khi khởi động JVM
D. Dùng -Xbootclasspath:agent.jar để gọi agentmain
Đáp án đúng: C

Câu 2. Đối với Java Agent tải lúc startup, thuộc tính manifest nào chỉ ra entry class?
A. Premain-Class khai báo lớp có entrypoint premain
B. Main-Class khai báo lớp sẽ xử lý ClassFileTransformer
C. Agent-Class khai báo lớp premain cho startup agent
D. Automatic-Module-Name khai báo hàm premain của JAR
Đáp án đúng: A

Câu 3. Chữ ký entrypoint nào được Java Instrumentation hỗ trợ để nhận đối tượng Instrumentation?
A. public Instrumentation premain(String args, ClassLoader loader)
B. public static boolean premain(Instrumentation inst, String args)
C. public static void main(Instrumentation inst, String args)
D. public static void premain(String args, Instrumentation inst)
Đáp án đúng: D

Câu 4. Trong startup agent hợp lệ, premain thường được gọi ở thời điểm nào?
A. Sau khi main của ứng dụng trả về nhưng trước khi shutdown
B. premain chạy trước main, nhưng sau một số class JVM
C. Chỉ sau khi JVM đã nạp toàn bộ class của mọi module
D. Chỉ khi JIT phát hiện class của ứng dụng cần tối ưu
Đáp án đúng: B

Câu 5. Với cú pháp -javaagent:agent.jar=mode=trace, chuỗi nào được truyền đến tham số args của premain?
A. Tên file agent.jar cùng với manifest đầy đủ của nó
B. Giá trị mode=trace từ phần tùy chọn agent sau dấu bằng
C. Giá trị -javaagent:agent.jar gồm cả toàn bộ JVM option
D. Một danh sách mọi application argument truyền vào main
Đáp án đúng: B

Câu 6. Nếu JAR dùng với -javaagent thiếu Premain-Class hợp lệ, điều gì có thể xảy ra?
A. JVM tự tìm main của ứng dụng để gọi như premain
B. JVM chuyển sang Agent-Class để gọi agentmain mặc định
C. JVM bỏ agent rồi chạy ứng dụng không thông báo lỗi
D. JVM báo lỗi khởi tạo agent và không chạy ứng dụng
Đáp án đúng: D

Câu 7. Khi JVM cho phép nạp agent vào tiến trình đang chạy, manifest thường khai gì?
A. Premain-Class luôn tự thay Agent-Class lúc attach runtime
B. Main-Class trỏ tới hàm static transform trên class
C. Agent-Class trỏ tới lớp cung cấp agentmain của agent
D. Launcher-Agent-Class chỉ dùng để khai mọi dynamic attach
Đáp án đúng: C

Câu 8. Điểm khác biệt chính giữa premain và agentmain trong Java Agent là gì?
A. premain chạy sau GC; agentmain chạy trước parser của javac
B. premain cho startup; agentmain cho agent được nạp vào JVM đang chạy
C. premain dành cho native library; agentmain dành cho bytecode
D. premain xử lý method call; agentmain chỉ được đọc field
Đáp án đúng: B

Câu 9. Nếu công cụ attach định nạp agent vào một JVM đang chạy, điều kiện nào phải được xét?
A. Agent phải được biên dịch thành class file version thấp nhất
B. Quyền attach và chính sách nạp agent của JVM đích
C. Cả tiến trình JVM đích phải tắt kiểm tra class verifier
D. Tất cả thread của ứng dụng phải đang ở trạng thái WAITING
Đáp án đúng: B

Câu 10. Khả năng retransform được một JVM cung cấp nên xác minh thế nào trước khi dùng?
A. Gọi isRetransformClassesSupported() trước khi dùng
B. Chỉ kiểm tra JAR có Main-Class là AgentEntry hay không
C. Chỉ gọi isModifiableModule() cho module java.base
D. Chỉ kiểm tra lớp mục tiêu có phương thức main hay không
Đáp án đúng: A

Câu 11. Để đăng ký transformer tham gia retransformation khi được hỗ trợ, dùng gì?
A. addTransformer(transformer, false) để bật retransform mặc định
B. redefineClasses(transformer) để biến transformer thành listener
C. addTransformer(transformer, true) sau khi xác nhận khả năng JVM
D. appendToSystemClassLoaderSearch(transformer) để hook class load
Đáp án đúng: C

Câu 12. Khi ClassFileTransformer.transform trả null, ý nghĩa thông thường là gì?
A. Yêu cầu JVM xóa class đã được xác minh khỏi bộ nhớ
B. Buộc JVM nạp lại class bằng một ClassLoader mới
C. Không đổi bytecode tại bước transformer hiện tại
D. Dừng toàn bộ chuỗi transformer vì agent đã hoàn tất
Đáp án đúng: C

Câu 13. Khi transform class lúc load lần đầu, classBeingRedefined thường có giá trị nào?
A. null khi class chưa được định nghĩa lần đầu
B. Class<?> đã được gán cho class sau khi Java main chạy
C. Đối tượng Class<?> đại diện cho transformer đã đăng ký
D. ClassLoader object được ép sang kiểu Class<?> tại runtime
Đáp án đúng: A

Câu 14. Trong ClassFileTransformer, tên className thông thường dùng định dạng nào?
A. Tên nội bộ với dấu / như com/example/Service
B. Tên binary với dấu . như com.example.Service
C. Tên resource .java như com/example/Service.java
D. Tên module và version như com.example@Service:1
Đáp án đúng: A

Câu 15. Trong transform, classfileBuffer chứa dữ liệu gì?
A. Bytecode JIT máy native đã tối ưu trên CPU hiện tại
B. Nguồn Java đầy đủ trước khi javac phân tích cú pháp
C. Vùng heap chứa các instance của class đang được nạp
D. Bytecode class đầu vào của transformer hiện tại
Đáp án đúng: D

Câu 16. Nếu transformer tạo bytecode mới, cách trả kết quả nào phù hợp?
A. Trả mảng byte[] class file mới hợp lệ với thay đổi cần thiết
B. Trả đối tượng Class<?> đã nạp lại bằng ClassLoader mặc định
C. Thay đổi classfileBuffer tại chỗ rồi bắt buộc trả null
D. Trả danh sách phương thức JIT đã được inline trên JVM
Đáp án đúng: A

Câu 17. Vì sao nên tránh class loading phức tạp ngay trong transform?
A. Vì mọi class mới load sẽ buộc JVM chạy toàn bộ premain lại
B. Có thể gây tái nhập transformer, deadlock hoặc lỗi liên kết
C. Vì JVM luôn cấm tải class bằng bootstrap ClassLoader ở đây
D. Vì Java Agent tự động tắt việc kiểm tra verifier sau load
Đáp án đúng: B

Câu 18. Nếu transformer được gọi từ nhiều luồng, yêu cầu thiết kế nào phù hợp?
A. Giả định mọi lời gọi transform đều nằm trên một thread duy nhất
B. Lưu bộ đếm vào biến local static mà không cần đồng bộ
C. Bắt buộc chạy tất cả transform trong EDT của ứng dụng GUI
D. Đảm bảo state và cache của transformer an toàn đồng thời
Đáp án đúng: D

Câu 19. Để tránh biến đổi lặp chính bytecode mà agent đã instrument, cách nào hữu ích?
A. Luôn chèn cùng logging code mỗi lần transform chạy lại
B. Bỏ qua className và chỉ dựa vào tên method trong stacktrace
C. Phát hiện marker hoặc mẫu bytecode đã chèn trước khi sửa tiếp
D. Tự tăng classfile version sau mỗi lần transformer được gọi
Đáp án đúng: C

Câu 20. Thư viện nào thường hỗ trợ thao tác bytecode trong Java Agent?
A. ASM hoặc Byte Buddy để tạo và chỉnh bytecode JVM
B. javap hoặc jdeps để ghi các instruction mới vào .class
C. JavaCompiler hoặc jlink để gắn transformer lúc tải class
D. JFR hoặc JMX để sinh bytecode class thay thế lúc load
Đáp án đúng: A

Câu 21. Khi biến đổi method có control-flow phức tạp, yếu tố bytecode nào cần giữ hợp lệ?
A. Mã constant pool và mọi method descriptor đều phải xóa
B. Stack map frames và các ràng buộc của verifier JVM
C. Bộ đếm JVM breakpoint thay cho mọi StackMapTable
D. Tên class loader và module đủ để bỏ qua verifier
Đáp án đúng: B

Câu 22. Nếu transformer phát sinh class file sai định dạng, kết quả nào có thể xảy ra?
A. JVM luôn sửa mọi bytecode sai và vẫn chạy như cũ
B. javac tự biên dịch lại source trong cùng tiến trình
C. JVM có thể từ chối vì lỗi format hoặc verifier
D. Agent tự chuyển class sai thành hidden class hợp lệ
Đáp án đúng: C

Câu 23. Muốn xem những class hiện đã được JVM nạp, Instrumentation cung cấp gì?
A. addTransformer() trả về Class<?> của mọi class đã tải
B. isRedefineClassesSupported() liệt kê class đã tải
C. redefineModule() trả về class của module đang hoạt động
D. getAllLoadedClasses() trả về các Class<?> đã được tải
Đáp án đúng: D

Câu 24. Khi cần biết class nào có thể bị retransform, nên kết hợp bước nào?
A. Kiểm tra isModifiableClass trước retransformation
B. Chỉ dùng getObjectSize để xác nhận class có sửa được
C. Chỉ kiểm tra class có constructor public không tham số
D. Chỉ kiểm tra module có xuất package tới unnamed module
Đáp án đúng: A

Câu 25. retransformClasses(classes...) khác biến đổi ở lần load đầu ở điểm nào?
A. Áp transform lại lên class đã được JVM định nghĩa, nếu hỗ trợ
B. Đổi file .java trên disk rồi yêu cầu compiler chạy lại
C. Tạo ClassLoader con để định nghĩa class cùng tên mới
D. Chỉ chạy transform trên source chưa được JVM biên dịch
Đáp án đúng: A

Câu 26. Với class đã được nạp, ranh giới nào thường áp dụng khi retransform/redefine?
A. Có thể tự do đổi superclass của class đã được load
B. Không thể đổi cấu trúc field/method của class đã nạp
C. Có thể đổi mọi method descriptor mà không gây lỗi
D. Có thể xóa mọi interface đã khai mà không cần verifier
Đáp án đúng: B

Câu 27. Trong Instrumentation API, redefineClasses nhận loại đầu vào nào?
A. Các JavaFileObject chứa source mới để javac tự biên dịch
B. Các AnnotationMirror mô tả annotation cần thêm vào class
C. Các ClassDefinition chứa Class<?> và bytecode thay thế
D. Các ClassLoader khác nhau nhưng không cần bytecode
Đáp án đúng: C

Câu 28. Nếu JVM hỗ trợ redefineClasses, phương thức nào cho biết khả năng đó?
A. isRetransformClassesSupported() tự khẳng định redefine
B. isRedefineClassesSupported() trên Instrumentation
C. isNativeMethodPrefixSupported() bảo đảm redefine được
D. isModifiableModule() cho biết redefine bytecode hỗ trợ
Đáp án đúng: B

Câu 29. Sau khi redefine một method lúc nó đang thực thi trên stack, điều gì thường đúng?
A. Active frame lập tức đổi instruction pointer sang bytecode mới
B. Active frame chạy code cũ, lần gọi mới dùng code mới
C. JVM bắt buộc hủy mọi thread đang thực thi method đó
D. ClassLoader tự tạo class mới có tên khác cho mỗi active frame
Đáp án đúng: B

Câu 30. Khi có nhiều transformer đăng ký, class bytes được xử lý theo cách nào?
A. Mỗi transformer luôn nhìn cùng bytes cuối cùng sau tất cả hook
B. JVM chỉ chạy transformer mới đăng ký và bỏ các hook cũ
C. Output transformer trước trở thành input transformer tiếp theo
D. Các transformer chỉ chạy đồng thời rồi XOR output với nhau
Đáp án đúng: C

Câu 31. Nếu transformer được đăng ký không hỗ trợ retransformation, khi retransform class, hành vi nào phù hợp?
A. JVM buộc đăng ký lại transformer đó dưới chế độ hỗ trợ retransform
B. JVM tự xóa mọi biến đổi trước đó để có source bytes ban đầu
C. Các biến đổi đã áp trước đó được JVM tái dùng mà không gọi lại hook đó
D. JVM gọi lại transformer đó với Class<?> luôn là null
Đáp án đúng: C

Câu 32. Instrumentation.removeTransformer trả giá trị true thể hiện điều gì?
A. Các class trước đó đã được tự khôi phục bytecode gốc
B. JVM đã hủy toàn bộ object của transformer trong heap
C. Các method đã instrument được reset trước khi return
D. Transformer đã được gỡ khỏi danh sách đăng ký nếu có
Đáp án đúng: D

Câu 33. Với getObjectSize(obj), giá trị nên được hiểu theo cách nào?
A. Kích thước toàn bộ object graph được duyệt đệ quy từ obj
B. Số byte của classfile đang dùng để định nghĩa class object
C. Dung lượng heap của mọi instance cùng type với object
D. Ước lượng kích thước object, không tính graph tham chiếu
Đáp án đúng: D

Câu 34. Instrumentation.getInitiatedClasses(loader) trả thông tin nào?
A. Chỉ class được định nghĩa trực tiếp bằng defineClass của loader
B. Mọi class hiện đang nằm trên classpath của toàn ứng dụng
C. Các class mà ClassLoader chỉ định đã từng initiate việc tải
D. Các class vừa được JIT tối ưu hóa trong cùng ClassLoader
Đáp án đúng: C

Câu 35. Vì sao tên class giống nhau vẫn có thể đại diện hai type khác nhau?
A. Tên binary và defining ClassLoader cùng xác định type
B. JVM chỉ phân biệt type nhờ hashCode của các instance
C. Class identity của JVM chỉ dựa trên đường dẫn file .java
D. Mỗi class được định danh theo ThreadLocal tạo ra instance
Đáp án đúng: A

Câu 36. appendToBootstrapClassLoaderSearch(JarFile) phục vụ mục đích nào?
A. Đổi mọi loaded class về ClassLoader hệ thống lúc runtime
B. Nạp toàn bộ JAR và tự chạy premain cho mỗi class bên trong
C. Cấp quyền deep reflection mặc định cho module java.base
D. Thêm JAR vào phạm vi tìm class của bootstrap ClassLoader
Đáp án đúng: D

Câu 37. appendToSystemClassLoaderSearch(JarFile) tác động chủ yếu tới đâu?
A. Tạo class loader mới cho mỗi entry của JAR được append
B. Xóa cache bytecode của bootstrap ClassLoader ngay lập tức
C. Đặt toàn bộ package của JAR thành module java.base
D. Mở rộng đường tìm class của system ClassLoader bằng JAR
Đáp án đúng: D

Câu 38. Khi code agent cần deep reflection vào package của named module, API nào có thể trợ giúp nếu được cấu hình đúng?
A. Instrumentation.getAllLoadedClasses tự mở mọi package đã tải
B. Instrumentation.getObjectSize cho phép setAccessible trên private
C. Instrumentation.redefineModule mở package tới module đích được chỉ định
D. Instrumentation.removeTransformer cấp mọi quyền opens cho agent
Đáp án đúng: C

Câu 39. Khi instrument class trong named module có strong encapsulation, nhận định nào đúng?
A. Mọi named module mặc định mở private member cho mọi Java Agent
B. Cần reads/opens phù hợp; agent không bỏ qua module boundary
C. Agent được tải bằng -javaagent sẽ tự thay module-info.class
D. Chỉ cần có className thì mọi reflection đều hợp lệ
Đáp án đúng: B

Câu 40. Khi lọc class để biến đổi, quy tắc nào giảm rủi ro recursion và overhead?
A. Biến đổi mọi class java.base để tăng độ phủ của agent
B. Bỏ qua tên loader và biến đổi tất cả module giống nhau
C. Bỏ qua package agent và chỉ instrument nhóm class cần thiết
D. Đặt mọi class được tải vào cache có strong reference vô hạn
Đáp án đúng: C

Câu 41. Với class được nạp bởi nhiều custom ClassLoader, cache agent nên cân nhắc điều gì?
A. Dùng khóa định danh phù hợp loader và tránh giữ class/loader quá lâu
B. Chỉ dùng tên class để nhận diện nên mọi loader cùng một type
C. Gắn mọi class vào static HashMap có strong reference mãi mãi
D. Tự ép mọi loader về bootstrap loader trước khi cache dữ liệu
Đáp án đúng: A

Câu 42. Vì sao transformer cần hạn chế I/O đồng bộ trên hot path tải class?
A. Vì mọi lời gọi I/O đều làm bytecode tự mất StackMapTable
B. Có thể tăng latency khởi tạo và gây nghẽn khi class loading
C. Vì thao tác đọc file tự biến Java Agent thành native agent
D. Vì JVM không cho phép logging trong Java Agent ở runtime
Đáp án đúng: B

Câu 43. Để đánh giá chi phí instrument method, phép đo nào có giá trị nhất?
A. So số file Java trước và sau instrument rồi kết luận overhead
B. Chỉ đếm tổng số method được khai trong source code dự án
C. Chỉ so kích thước JAR của agent với JAR ứng dụng chính
D. So baseline và bản có agent trên cùng workload, đo latency/CPU
Đáp án đúng: D

Câu 44. Khi cần gắn agent vào ứng dụng production đang chạy, cách tiếp cận nào hợp lý?
A. Giả định mọi JVM đều bật dynamic attach mặc định mãi mãi
B. Tự tắt bytecode verification để agent có thể load mọi class
C. Đưa JAR agent vào classpath rồi gọi premain từ HTTP request
D. Xác nhận attach được phép và giới hạn quyền, rollout có kiểm soát
Đáp án đúng: D

Câu 45. Vì sao đo metrics trong transform() có thể làm nhiễu số liệu hiệu năng?
A. Metrics trong transform có thể tăng thời gian nạp class
B. Vì mọi metric tự sửa return value của method gốc
C. Vì Java Agent thay JIT compiler nên mọi metric đều bằng 0
D. Vì ghi metric buộc phải tạo một ClassLoader mới cho mỗi call
Đáp án đúng: A

Câu 46. Khi kiểm thử agent startup, cách kiểm chứng tối thiểu nào phù hợp?
A. Chỉ biên dịch agent.jar rồi coi tất cả class được instrument
B. Chạy app có/vắng -javaagent và so log, kết quả
C. Chỉ kiểm tra Premain-Class trong manifest mà bỏ chạy JVM
D. Chỉ chạy unit test business method không nạp Java Agent
Đáp án đúng: B

Câu 47. Khi muốn xác minh agent không phá hành vi ứng dụng, test nào nên có?
A. So kết quả và exception khi bật/tắt instrumentation
B. Chỉ kiểm tra class file có tăng kích thước sau transform
C. Chỉ kiểm tra tần suất log tại lúc JVM khởi động
D. Chỉ đếm số transformer đã gọi addTransformer
Đáp án đúng: A

Câu 48. Khi transformer có lỗi ở một class cụ thể, chiến lược kiểm soát phù hợp là gì?
A. Bỏ qua mọi lỗi mà không ghi nhận để tránh tăng overhead
B. Để agent thử lại vô hạn cho tới khi class load thành công
C. Tự biến class lỗi thành Object mà không thay đổi business logic
D. Ghi lỗi đủ ngữ cảnh, dùng chính sách fail hoặc bỏ qua
Đáp án đúng: D
