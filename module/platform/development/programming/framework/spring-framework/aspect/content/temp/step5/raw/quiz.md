Câu 1. Một lớp có @Aspect nhưng không được đăng ký thành bean Spring sẽ có kết quả gì?
A. Spring tự quét mọi lớp @Aspect ngoài ApplicationContext
B. Advice của lớp đó không được Spring áp dụng qua proxy
C. Proxy sẽ tự sinh khi gọi constructor của lớp Aspect
D. Advice chỉ chạy với bean có cùng tên class với Aspect
Đáp án đúng: B

Câu 2. Trong cấu hình Spring thuần dùng AspectJ annotation, @EnableAspectJAutoProxy có tác dụng gì?
A. Thay cơ chế proxy bằng bytecode weaving khi biên dịch
B. Tạo pointcut tự động cho mọi public method của bean
C. Đăng ký mọi @Aspect trong classpath thành bean độc lập
D. Bật xử lý aspect thành proxy cho bean do Spring quản lý
Đáp án đúng: D

Câu 3. Khi ứng dụng Spring Boot có starter AOP phù hợp, nhận định nào đúng?
A. Mọi lần gọi nội bộ this.method đều được intercept
B. AspectJ weaving luôn bắt buộc khi khai báo @Aspect
C. Starter AOP có thể bật proxy qua auto-configuration
D. Mọi lớp khởi tạo với new đều thành Spring proxy
Đáp án đúng: C

Câu 4. Muốn @Aspect được quét qua component scanning, cấu hình nào phù hợp?
A. Đặt @Component cho lớp @Aspect trong vùng được scan
B. Chỉ khai @Pointcut mà không cần bean aspect trong context
C. Dùng @Autowired trên advice để tự đăng ký cả lớp aspect
D. Đặt @Primary lên target bean để Spring quét aspect
Đáp án đúng: A

Câu 5. Khi một method target sắp chạy qua Spring proxy, @Before advice làm gì?
A. Thực thi trước method target khi pointcut khớp
B. Chỉ chạy khi method target đã return bình thường
C. Chạy sau khi target phát ra một exception phù hợp
D. Bao quanh target và tự quyết định có gọi proceed
Đáp án đúng: A

Câu 6. Khi muốn ghi log kết quả sau lời gọi thành công, advice nào phù hợp?
A. @AfterThrowing chạy khi method trả về một kết quả
B. @After chạy riêng khi method trả kết quả hợp lệ
C. @Before có thể nhận trực tiếp return value đã tạo
D. @AfterReturning chạy khi target trả về bình thường
Đáp án đúng: D

Câu 7. Khi method target ném exception ra ngoài, advice chuyên xử lý trường hợp này là gì?
A. @AfterReturning với tham số returning trỏ tới lỗi
B. @Before với tham số throwing để nhận exception
C. @AfterThrowing với pointcut và điều kiện lỗi phù hợp
D. @Around mà không gọi proceed vẫn thấy lỗi từ target
Đáp án đúng: C

Câu 8. Trong Spring AOP, @After advice thường chạy ở trường hợp nào?
A. Chỉ sau lời gọi thành công có giá trị trả về
B. Chỉ khi method bị chặn bởi security interceptor
C. Trước khi phần body của target method được gọi
D. Sau khi method kết thúc, kể cả ném exception
Đáp án đúng: D

Câu 9. Điều nào khiến @Around phù hợp để đo thời lượng method qua proxy?
A. Nhận return value mà không thể chạy code trước
B. Đo trước và sau proceed trong cùng advice
C. Tự làm bytecode weaving vào body target method
D. Chỉ phát sự kiện khi bean vừa khởi tạo trong context
Đáp án đúng: B

Câu 10. Với @Around advice, lệnh nào gọi tiếp chuỗi interceptor rồi tới method đích?
A. JoinPoint.getArgs() tự thực thi lại method target
B. MethodSignature.getMethod() tự gọi lại Java method
C. ProceedingJoinPoint.proceed() gọi tiếp chuỗi advice
D. AspectJExpressionPointcut.matches() chạy phần body
Đáp án đúng: C

Câu 11. Nếu @Around trả kết quả mà không gọi proceed(), điều gì xảy ra?
A. Spring buộc thực thi target sau khi advice trả về
B. Proxy luôn tự gọi proceed() một lần lúc kết thúc
C. Chỉ @Before advice được bỏ qua, target vẫn chạy
D. Lời gọi target bên dưới có thể bị bỏ qua
Đáp án đúng: D

Câu 12. Để thay đổi kết quả trả về từ lời gọi được advice, hướng nào phù hợp?
A. @Around có thể thay giá trị trả về từ proceed()
B. @AfterReturning tự thay mọi giá trị bằng đối số returning
C. @Before đọc ReturnValue trước khi body được thực thi
D. @AfterThrowing gán kết quả mới dù không có exception
Đáp án đúng: A

Câu 13. Muốn đọc tham số đầu vào method khi advice chạy, API nào thường dùng?
A. JoinPoint.getArgs() trả mảng đối số tại join point
B. JoinPoint.getTarget() trả mảng argument của request
C. MethodSignature.getReturnType() trả các input argument
D. ProceedingJoinPoint.proceed() chỉ để đọc danh sách argument
Đáp án đúng: A

Câu 14. Tham số ProceedingJoinPoint phù hợp nhất với advice nào trong Spring AOP?
A. @Before vì có thể thay body của method gốc
B. @AfterThrowing vì có thể gọi lại method khi lỗi
C. @AfterReturning vì có thể điều khiển return type
D. @Around vì có thể chủ động gọi proceed()
Đáp án đúng: D

Câu 15. Pointcut execution(* com.acme.service..*(..)) tập trung khớp điều gì?
A. Các lần đọc field được khai báo trong service package
B. Các lời gọi constructor tạo lớp bên ngoài Spring context
C. Các lần thực thi method thuộc các type trong service package
D. Các dòng code tạo annotation trong package service
Đáp án đúng: C

Câu 16. Trong Spring AOP, within(com.acme.service..*) thường dùng để chọn gì?
A. Bean mang tên service bất kể class ở package nào
B. Khớp method trong những type thuộc package đã chọn
C. Chỉ những method có annotation @Service trực tiếp
D. Các target object đang ở trong một HTTP request scope
Đáp án đúng: B

Câu 17. Muốn advice chỉ method có annotation @Audited, pointcut nào phù hợp?
A. @within(com.acme.Audited) cho từng method mang annotation
B. @annotation(com.acme.Audited) trên method thực thi
C. args(com.acme.Audited) cho method có annotation
D. target(com.acme.Audited) cho annotation trên method
Đáp án đúng: B

Câu 18. Designator bean(paymentService) có ý nghĩa gì trong Spring AOP?
A. Khớp mọi method trả object có class PaymentService
B. Chỉ khớp method mang annotation @Bean với giá trị đó
C. Khớp join point của bean có tên paymentService
D. Khớp mọi constructor tạo biến có tên paymentService
Đáp án đúng: C

Câu 19. Khi viết args(java.lang.String) trong pointcut Spring AOP, mục tiêu là gì?
A. Khớp theo kiểu trả về của method target
B. Khớp theo kiểu tham số tại lời gọi method
C. Khớp theo type của proxy chứa method
D. Khớp bean name được đặt theo kiểu String
Đáp án đúng: B

Câu 20. Điểm khác nhau giữa this(T) và target(T) trong Spring AOP là gì?
A. this xét proxy, còn target xét object đích
B. this luôn xét target; target xét interface của proxy
C. Cả hai chỉ xét kiểu trả về của method target
D. Cả hai chỉ dùng để chọn constructor join point
Đáp án đúng: A

Câu 21. Giới hạn join point cốt lõi của Spring AOP proxy-based là gì?
A. Chủ yếu hỗ trợ method execution trên Spring bean
B. Can thiệp mọi field access trong object thuộc classpath
C. Can thiệp constructor call của mọi class Java trong JVM
D. Can thiệp static initializer mà không cần cấu hình khác
Đáp án đúng: A

Câu 22. Một pointcut AspectJ nhắm field get/set không kích hoạt như kỳ vọng khi chỉ bật Spring AOP vì sao?
A. Spring AOP chỉ cho phép pointcut khai báo bằng annotation
B. Proxy Spring không chặn trực tiếp field get/set
C. Mọi field access phải khai báo @Transactional mới khớp
D. Pointcut chỉ hoạt động khi field chứa giá trị null
Đáp án đúng: B

Câu 23. Khi proxyTargetClass=false và bean triển khai interface, Spring AOP thường chọn proxy nào?
A. CGLIB subclass proxy dù không có cấu hình bổ sung
B. JDK dynamic proxy dựa trên interface của bean
C. ByteBuddy agent weaving vào class tại thời điểm load
D. AspectJ compile-time woven type thay cho Spring bean
Đáp án đúng: B

Câu 24. Khi cấu hình @EnableAspectJAutoProxy(proxyTargetClass=true), tác động dự kiến là gì?
A. Buộc advice chỉ được khai báo trên interface public
B. Tắt việc tạo proxy đối với bean có interface
C. Ưu tiên proxy dựa trên subclass của target bằng CGLIB
D. Bật aspect weaving cho constructor của target class
Đáp án đúng: C

Câu 25. Nếu một bean dùng JDK dynamic proxy, kiểu khai báo dependency nào an toàn hơn?
A. Inject qua concrete class dù proxy không kế thừa class
B. Inject qua interface mà proxy thực thi
C. Ép proxy thành class gốc trước khi gọi public method
D. Inject class gốc và bỏ qua ApplicationContext để lấy bean
Đáp án đúng: B

Câu 26. Khi cast JDK dynamic proxy của một bean sang class triển khai cụ thể, chuyện gì dễ xảy ra?
A. Cast thành công vì proxy kế thừa class triển khai
B. JDK proxy không kế thừa class target nên cast lỗi
C. Proxy tự chuyển sang CGLIB mỗi khi bị ép kiểu
D. Spring tạo thêm bản sao class mới khi chạy cast
Đáp án đúng: B

Câu 27. Với target class là final nhưng có interface, cơ chế nào vẫn có thể dùng để advice method interface?
A. CGLIB subclass proxy override method của final class
B. AspectJ weaving luôn được Spring tự bật cho target
C. Proxy class-based tạo subclass dù class được đánh final
D. JDK proxy trên interface, nếu bean được cấu hình phù hợp
Đáp án đúng: D

Câu 28. Vì sao CGLIB class-based proxy gặp hạn chế với final class?
A. Final class không cho phép implement bất kỳ interface
B. Final class làm mọi method thành static khi chạy
C. Final class không cho phép tạo subclass để proxy
D. Final class ngăn Spring đọc annotation của bean
Đáp án đúng: C

Câu 29. Khi class-based proxy gặp một final method, điều gì cần lưu ý?
A. Advice vẫn luôn chạy vì proxy trực tiếp sửa bytecode
B. Final method chỉ bị bỏ qua với JDK dynamic proxy
C. Spring tự bỏ final modifier khi bean được đăng ký
D. CGLIB không thể override final method để áp advice
Đáp án đúng: D

Câu 30. Một private method của target có được Spring AOP proxy intercept trực tiếp không?
A. Có nếu method private có annotation @Before trực tiếp
B. Không; private method không được proxy override
C. Có nếu @EnableAspectJAutoProxy được đặt trên cùng class
D. Có khi @Pointcut dùng execution(private * *(..))
Đáp án đúng: B

Câu 31. Tình huống nào đảm bảo lời gọi đi qua Spring AOP proxy để advice có cơ hội chạy?
A. Một bean khác gọi public method qua bean proxy lấy từ Spring
B. Target trực tiếp dùng this.someMethod() trong class
C. Constructor của target gọi method cùng instance khi tạo
D. Static method trong target tự gọi method không qua bean
Đáp án đúng: A

Câu 32. Khi method A của target gọi this.methodB(), dù methodB khớp pointcut, điều gì thường xảy ra?
A. Spring tạo một JDK proxy tạm để intercept methodB
B. Advice B chạy do proxy được giữ trong field this
C. CGLIB luôn intercept self invocation nhờ subclass
D. Lời gọi nội bộ bỏ qua proxy nên advice B không chạy
Đáp án đúng: D

Câu 33. Để xử lý self-invocation không được intercept, cách thiết kế nào thường tốt?
A. Đổi this.methodB() thành super.methodB() trong cùng class
B. Thêm @Component trên methodB để tạo proxy riêng
C. Dùng final cho methodB để Spring nhận diện điểm cắt
D. Tách method cần advice sang bean khác và gọi qua proxy
Đáp án đúng: D

Câu 34. Nếu muốn dùng AopContext.currentProxy() từ target, yêu cầu nào quan trọng?
A. Chỉ cần có @Aspect trên class target là lấy được proxy
B. Chỉ cần bật component scan mà không cần proxy invocation
C. Cần exposeProxy=true và lời gọi đang đi qua AOP proxy
D. Bất kỳ constructor nào đều có thể lấy proxy trước startup
Đáp án đúng: C

Câu 35. Vì sao advice quanh method @PostConstruct không nên được giả định sẽ chạy?
A. Initialization thường xảy ra trên target trước khi proxy sẵn sàng
B. Method @PostConstruct luôn là static và không có proxy
C. Spring AOP tự bỏ qua toàn bộ bean được inject trong constructor
D. @PostConstruct buộc transaction manager chưa được đăng ký
Đáp án đúng: A

Câu 36. Khi tạo object bằng new thay vì lấy bean từ ApplicationContext, điều gì xảy ra với advice Spring AOP?
A. Object luôn được CGLIB tự phát hiện và chuyển thành bean
B. Aspect bean tự đăng ký object vào mọi ApplicationContext
C. Object đó không tự nhận proxy do Spring quản lý
D. Mọi method của object vẫn được weave như AspectJ
Đáp án đúng: C

Câu 37. Nếu lớp @Aspect nằm ngoài vùng component scan và không được @Bean đăng ký, xử lý nào phù hợp?
A. Chỉ đặt @Pointcut static để Spring tự phát hiện advice
B. Đổi advice thành private để Spring tự quét classpath
C. Đăng ký aspect bean vào context có AOP infrastructure
D. Gắn @Order lên class aspect để kích hoạt component scan
Đáp án đúng: C

Câu 38. Giữa hai aspect có @Order(1) và @Order(5), advice vào method thường có quan hệ nào?
A. Aspect order 5 luôn chạy trước vì có giá trị lớn hơn
B. Hai aspect luôn có thứ tự ngẫu nhiên dù có @Order
C. @Order chỉ sắp xếp constructor, không tác động advice
D. Aspect order 1 có precedence cao hơn khi đi vào chain
Đáp án đúng: D

Câu 39. Với hai @Around advice có precedence khác nhau, thứ tự kết thúc thường thế nào?
A. Advice vào trước luôn thoát trước dù có proceed()
B. Tất cả advice kết thúc theo thứ tự khai báo trong class
C. @Around không tham gia tính precedence giữa các aspect
D. Advice vào trước thoát sau do các lời gọi lồng nhau
Đáp án đúng: D

Câu 40. Khi một aspect định nghĩa nhiều @Before advice cùng khớp và cùng precedence, giả định nào không an toàn?
A. Dựa vào thứ tự khai báo source code để quyết định thứ tự chạy
B. Dùng @Order giữa các aspect khác nhau để xác định precedence
C. Tách thứ tự bắt buộc sang một advice duy nhất
D. Viết test xác minh các callback quan trọng khi có nhiều aspect
Đáp án đúng: A

Câu 41. Muốn @AfterThrowing nhận exception bằng tên tham số ex, cần cấu hình gì?
A. Khai báo returning="ex" để nhận exception từ method
B. Truyền ex qua JoinPoint.getArgs() trước khi target chạy
C. Khai báo throwing="ex" khớp tham số advice có thể bind
D. Đổi @AfterThrowing thành @AfterReturning để bind exception
Đáp án đúng: C

Câu 42. Nếu method target bắt và xử lý exception nội bộ rồi trả bình thường, @AfterThrowing sẽ ra sao?
A. Không chạy khi exception đã được method xử lý
B. Luôn chạy khi có một catch block bên trong method
C. Chạy trước @Before khi lời gọi đi qua interface
D. Tự đọc error log để suy ra exception đã bị xử lý
Đáp án đúng: A

Câu 43. Trong @AfterReturning(returning="result"), tham số result dùng để làm gì?
A. Đổi giá trị trả về qua việc gán lại biến advice parameter
B. Bind giá trị return khi target kết thúc bình thường
C. Bắt exception đã được method target chuyển thành log
D. Thay arguments của method trước khi proceed()
Đáp án đúng: B

Câu 44. Với @After advice, trường hợp nào sẽ kích hoạt callback này?
A. Khi lời gọi proxy kết thúc thành công hoặc lỗi
B. Chỉ lời gọi qua proxy trả về giá trị không null
C. Chỉ method thực thi dưới @Transactional commit thành công
D. Chỉ method không có @Around advice trong chain
Đáp án đúng: A

Câu 45. Khi muốn xử lý exception trong @Around nhưng vẫn giữ semantics lỗi cho caller, làm gì?
A. Bắt mọi exception và trả null để proxy luôn hoàn tất thành công
B. Gọi proceed lần hai trong mọi lỗi mà không xem side effect
C. Chuyển exception thành @AfterReturning để caller nhận nguyên lỗi
D. Ghi nhận lỗi rồi ném lại exception nếu không có chính sách phục hồi
Đáp án đúng: D

Câu 46. Để kiểm chứng object lấy từ Spring đã được AOP proxy, API nào phù hợp?
A. bean.getClass().getName() luôn kết thúc bằng Proxy
B. ApplicationContext.getBeanNamesForType() trả loại proxy
C. AopUtils.isAopProxy(bean) để kiểm tra object proxy
D. BeanFactory.containsBean() xác nhận bean được advice
Đáp án đúng: C

Câu 47. Khi kiểm thử một @Before advice trên service, cách gọi nào thực sự kiểm chứng wiring Spring AOP?
A. Gọi bean lấy từ Spring context và xác nhận advice được thực thi
B. new service rồi gọi method và coi advice luôn chạy
C. Chỉ tạo instance của aspect rồi gọi advice method trực tiếp
D. Mock toàn bộ ApplicationContext và kiểm tra @Aspect có tồn tại
Đáp án đúng: A

Câu 48. Nếu một pointcut khớp quá rộng khiến latency tăng, hướng kiểm soát nào phù hợp?
A. Chỉ tăng @Order để loại bỏ overhead của mọi advice
B. Thu hẹp expression và đo overhead trên lời gọi qua proxy
C. Đổi mọi bean thành prototype để proxy bỏ qua pointcut
D. Chỉ dùng CGLIB để advice không còn chi phí interception
Đáp án đúng: B
