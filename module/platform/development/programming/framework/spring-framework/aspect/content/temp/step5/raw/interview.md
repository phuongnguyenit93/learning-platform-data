Bạn giải thích Spring AOP tạo hành vi bổ sung cho một bean do ApplicationContext quản lý qua proxy như thế nào?
Bạn phân biệt một bean đích với bean proxy mà Spring trả về khi một aspect khớp phương thức như thế nào?
Bạn xác định điều kiện để một method invocation đi qua proxy Spring AOP thay vì gọi trực tiếp target như thế nào?
Bạn phân tích vì sao khai báo một lớp @Aspect chưa đủ để aspect tự động áp dụng nếu nó không được quản lý như Spring bean?
Bạn sẽ lựa chọn @Component hoặc khai báo @Bean để đăng ký một @Aspect vào ApplicationContext trong trường hợp nào?
Bạn giải thích vai trò của spring-boot-starter-aop đối với việc kích hoạt Spring AOP trong ứng dụng Spring Boot như thế nào?
Bạn mô tả tác dụng của @EnableAspectJAutoProxy khi Spring cấu hình xử lý các class @Aspect ra sao?
Bạn phân biệt cơ chế kích hoạt AOP do Spring Boot auto-configuration với cấu hình @EnableAspectJAutoProxy thủ công như thế nào?
Bạn sẽ chẩn đoán vì sao một @Aspect có trong source nhưng không xuất hiện dưới dạng bean trong ApplicationContext ra sao?
Bạn xác định cách giới hạn component scan để một @Aspect chỉ được áp dụng trong module hoặc context dự kiến như thế nào?
Bạn phân tích nguy cơ một cấu hình @ComponentScan quét nhầm aspect phục vụ thử nghiệm vào production ra sao?
Bạn sẽ kiểm tra các dependency AspectJ annotation support cần có trên classpath để Spring xử lý @Aspect như thế nào?
Bạn phân biệt việc Spring AOP sử dụng cú pháp @AspectJ với việc triển khai AspectJ compile-time weaving hoặc load-time weaving như thế nào?
Bạn giải thích vì sao @AspectJ annotation được Spring nhận diện không đồng nghĩa mọi join point của AspectJ đều được hỗ trợ như thế nào?
Bạn sẽ xác minh một @Aspect được bật trong ApplicationContext con nhưng không được áp dụng cho bean ở context cha ra sao?
Bạn phân tích ý nghĩa của việc @EnableAspectJAutoProxy áp dụng trong phạm vi ApplicationContext mà nó được khai báo như thế nào?
Bạn sẽ xác định tác động khi Spring MVC có DispatcherServlet context riêng và aspect được đăng ký ở context khác ra sao?
Bạn mô tả vai trò của BeanPostProcessor và auto-proxy creator trong vòng đời một bean Spring được advice như thế nào?
Bạn phân biệt bean definition, target object và đối tượng proxy nhận được sau khi Spring hoàn tất khởi tạo như thế nào?
Bạn sẽ kiểm tra một đối tượng do new trực tiếp tạo có nằm dưới phạm vi can thiệp của Spring AOP hay không như thế nào?
Bạn giải thích vì sao Spring AOP là lựa chọn phù hợp để can thiệp các lời gọi qua bean proxy thay vì mọi method call trong JVM như thế nào?
Bạn đánh giá rủi ro cấu hình quá nhiều aspect rộng khiến hầu hết Spring beans đều bị proxy ngoài ý muốn ra sao?
Bạn sẽ thiết kế một aspect có phạm vi hẹp cho lớp service thay vì áp dụng cho mọi bean trong container như thế nào?
Bạn phân tích tác động của thứ tự bean initialization tới khả năng một bean bị auto-proxy creator xử lý như thế nào?
Bạn sẽ điều tra cảnh báo một bean không đủ điều kiện được xử lý bởi tất cả BeanPostProcessor như thế nào?
Bạn phân biệt Spring AOP proxy với một wrapper tự tạo thủ công được lưu làm bean trong ApplicationContext ra sao?
Bạn sẽ kiểm tra nguyên nhân aspect có mặt nhưng pointcut không khớp bất kỳ phương thức nào trong ứng dụng như thế nào?
Bạn mô tả cách sử dụng annotation @Pointcut để đặt tên cho một biểu thức chọn method executions của Spring AOP ra sao?
Bạn phân biệt khai báo pointcut bằng @Pointcut với viết biểu thức trực tiếp trong @Before hoặc @Around như thế nào?
Bạn sẽ đặt tên các phương thức @Pointcut để tái sử dụng biểu thức qua nhiều advice rõ ràng ra sao?
Bạn giải thích cách designator execution khớp chữ ký phương thức trong các Spring beans như thế nào?
Bạn sẽ viết một biểu thức execution chỉ chọn các public methods của package service và các subpackage như thế nào?
Bạn phân biệt wildcard dấu sao và ký hiệu hai dấu chấm liên tiếp trong các mẫu chữ ký pointcut theo cú pháp Spring hỗ trợ ra sao?
Bạn phân tích vì sao biểu thức execution có thể không khớp method overload với kiểu tham số ngoài dự kiến như thế nào?
Bạn sẽ thiết kế pointcut cho những method có một tham số cụ thể thay vì khớp mọi số lượng tham số như thế nào?
Bạn giải thích designator within trong Spring AOP giới hạn các method thuộc một vùng kiểu hoặc package như thế nào?
Bạn phân biệt execution và within khi cần chọn method của Spring service có inheritance như thế nào?
Bạn sẽ quyết định khi nào kết hợp execution với within để tránh quét các getter hoặc utility methods không mong muốn ra sao?
Bạn mô tả cách designator bean chọn tên bean Spring chứ không chỉ kiểu class như thế nào?
Bạn sẽ viết pointcut bean theo wildcard cho một nhóm bean có quy ước tên thống nhất ra sao?
Bạn phân tích lợi ích của designator bean trong Spring AOP so với chỉ lọc theo package như thế nào?
Bạn sẽ kiểm tra tên bean thực tế trong container khi một pointcut bean không khớp như mong muốn ra sao?
Bạn phân biệt designator this với target trong Spring AOP khi bean đang được đại diện bởi proxy như thế nào?
Bạn sẽ đánh giá sự khác biệt khi pointcut this kiểm tra JDK dynamic proxy còn target kiểm tra implementation class ra sao?
Bạn giải thích designator args hoạt động theo kiểu tham số runtime của lời gọi được intercept như thế nào?
Bạn phân biệt điều kiện kiểu tham số trong execution với kiểu runtime trong args như thế nào?
Bạn sẽ thiết kế pointcut @annotation để chọn method được đánh dấu bằng một annotation nghiệp vụ như thế nào?
Bạn phân biệt @annotation và @within khi lọc Spring bean methods theo method annotation hoặc class annotation ra sao?
Bạn sẽ xác định khi nào @target phù hợp để kiểm tra annotation trên lớp target bean lúc runtime như thế nào?
Bạn phân tích sự khác nhau giữa @args và args khi muốn lọc lời gọi dựa trên annotation của đối tượng tham số ra sao?
Bạn sẽ lựa chọn giữa pointcut dựa trên annotation và pointcut dựa trên tên method để giảm rủi ro refactor như thế nào?
Bạn giải thích cách kết hợp các biểu thức pointcut bằng &&, || và ! trong @Aspect như thế nào?
Bạn sẽ giới hạn biểu thức pointcut để loại trừ chính class aspect hoặc các phương thức infrastructure như thế nào?
Bạn phân tích hậu quả khi đặt ! sai vị trí trong pointcut kết hợp OR khiến nhiều bean ngoài ý muốn bị advice ra sao?
Bạn sẽ tổ chức nhiều named pointcuts để giữ biểu thức dễ đọc và dễ kiểm thử như thế nào?
Bạn mô tả cách tham chiếu pointcut method khác trong cùng @Aspect hoặc qua tên đầy đủ từ aspect khác như thế nào?
Bạn sẽ xác minh pointcut package pattern có bao gồm các subpackage như mong muốn ra sao?
Bạn phân tích cách generics, bridge methods và method overload có thể ảnh hưởng việc khớp pointcut trên Spring proxy như thế nào?
Bạn sẽ xử lý khi interface method có annotation nhưng implementation method không có annotation mà pointcut cần đọc như thế nào?
Bạn phân biệt annotation đặt trên interface và annotation trên implementation khi dùng proxy JDK và CGLIB để tìm advice ra sao?
Bạn sẽ kiểm tra pointcut @annotation khớp chính xác method được Spring AOP thực thi trong một bean nhiều interface như thế nào?
Bạn giải thích vì sao Spring AOP hỗ trợ chủ yếu method execution join points thay vì mọi join point AspectJ như thế nào?
Bạn sẽ trả lời thế nào khi một biểu thức call được copy từ AspectJ không được Spring AOP hỗ trợ?
Bạn phân tích giới hạn của Spring AOP đối với get hoặc set field access join points như thế nào?
Bạn sẽ xác định cơ chế phù hợp nếu nghiệp vụ cần can thiệp constructor execution thay vì gọi method bean qua proxy như thế nào?
Bạn phân biệt phương thức static với phương thức instance của Spring bean khi đánh giá khả năng interception ra sao?
Bạn sẽ giải thích vì sao tạo đối tượng mới bằng constructor trực tiếp không làm Spring AOP intercept các lời gọi trên nó như thế nào?
Bạn xác định cách tránh đưa cú pháp pointcut AspectJ không được Spring AOP hỗ trợ vào @Aspect production ra sao?
Bạn phân tích ưu và nhược điểm của việc dùng pointcut rộng so với annotation marker có chủ đích trong Spring service như thế nào?
Bạn sẽ kiểm thử tên các method được một pointcut bắt trúng trước khi triển khai logic audit hoặc security ra sao?
Bạn mô tả vai trò của @Before advice khi một method của bean được gọi qua Spring AOP proxy như thế nào?
Bạn phân biệt @Before với @Around khi chỉ cần quan sát thông tin lời gọi mà không đổi flow thực thi ra sao?
Bạn sẽ sử dụng JoinPoint trong @Before để đọc tên method và danh sách tham số một cách an toàn như thế nào?
Bạn phân tích rủi ro ghi log toàn bộ JoinPoint.getArgs khi tham số chứa password hoặc dữ liệu cá nhân ra sao?
Bạn sẽ chọn giữa @AfterReturning và @After khi cần đo kết quả thành công của một Spring service như thế nào?
Bạn giải thích vai trò của thuộc tính returning trong @AfterReturning khi bind giá trị trả về của target method như thế nào?
Bạn sẽ xử lý method trả về void khi xây dựng logic @AfterReturning như thế nào?
Bạn phân tích giới hạn của @AfterReturning khi muốn thay đổi hẳn giá trị return mà target method cung cấp như thế nào?
Bạn sẽ chọn @Around nếu cần thay thế response từ target method và giữ đúng kiểu return như thế nào?
Bạn giải thích @AfterThrowing chạy khi lời gọi qua proxy kết thúc bằng exception như thế nào?
Bạn sẽ sử dụng thuộc tính throwing của @AfterThrowing để bind một nhóm exception cụ thể như thế nào?
Bạn phân biệt lỗi ném từ target method và lỗi ném từ advice khác trong việc quan sát bằng @AfterThrowing như thế nào?
Bạn phân tích vì sao một @AfterThrowing advice không tự động biến exception thành fallback result như thế nào?
Bạn sẽ thiết kế logging khi @AfterThrowing nhìn thấy exception mà không vô tình làm mất stack trace gốc ra sao?
Bạn giải thích @After tương đương hành vi hoàn tất sau method theo semantics finally trong Spring AOP như thế nào?
Bạn sẽ chọn @After để cleanup thông tin thread-local như thế nào khi cả đường thành công và đường lỗi đều có thể xảy ra?
Bạn phân tích rủi ro @After advice tự ném exception làm thay đổi exception hoặc kết quả target method như thế nào?
Bạn mô tả vai trò của @Around advice và ProceedingJoinPoint trong một method invocation Spring AOP ra sao?
Bạn phân biệt ProceedingJoinPoint với JoinPoint theo khả năng quyết định có tiếp tục gọi target hay không như thế nào?
Bạn giải thích điều gì xảy ra nếu một @Around advice không gọi proceed trong khi caller vẫn chờ kết quả như thế nào?
Bạn sẽ thiết kế @Around advice đo latency bằng thời gian trước và sau proceed thế nào để xử lý cả exception?
Bạn phân tích tác động khi @Around advice gọi proceed nhiều lần đối với một method có side effect như thế nào?
Bạn sẽ xác định khi nào một Spring @Around advice được phép retry target method và cần bảo vệ idempotency như thế nào?
Bạn giải thích cách ProceedingJoinPoint.proceed(Object[]) có thể truyền tham số thay thế cho lời gọi target như thế nào?
Bạn sẽ kiểm tra số lượng và kiểu tham số thay thế trước khi gọi proceed(Object[]) như thế nào?
Bạn phân tích nguy cơ chỉnh sửa trực tiếp argument mutable trong advice gây tác dụng phụ ngoài mong muốn ra sao?
Bạn sẽ thiết kế advice che dữ liệu nhạy cảm khỏi log mà không sửa dữ liệu truyền tới target method như thế nào?
Bạn phân biệt return value từ proceed với return value do advice tự tạo khi xây dựng một @Around advice như thế nào?
Bạn sẽ xử lý kiểu primitive hoặc void của target method khi một @Around advice muốn trả fallback như thế nào?
Bạn giải thích vì sao @Around advice nên khai báo kiểu trả về phù hợp với signature của những method được chọn như thế nào?
Bạn phân tích rủi ro @Around nuốt exception rồi trả null cho method đòi primitive return type ra sao?
Bạn sẽ dùng try, catch và finally bên trong @Around để phân loại lỗi và ghi metric như thế nào?
Bạn xác định khi nào một @Around advice có thể thay exception gốc bằng exception nghiệp vụ và hậu quả với caller ra sao?
Bạn phân tích việc advice ném exception checked không tương thích method signature có thể ảnh hưởng lời gọi như thế nào?
Bạn sẽ tổ chức một aspect audit không phụ thuộc vào implementation của từng Spring service như thế nào?
Bạn phân biệt auditing kỹ thuật qua advice với audit nghiệp vụ cần ghi nhận chính xác sự kiện commit như thế nào?
Bạn sẽ chọn advice nào cho yêu cầu đo số lần gọi method và số lần lỗi mà không sửa kết quả như thế nào?
Bạn đánh giá nguy cơ metric được ghi nhận hai lần khi hai aspects dùng pointcut trùng nhau như thế nào?
Bạn sẽ lựa chọn JoinPoint.getSignature và MethodSignature để lấy tên class, method và thông tin type như thế nào?
Bạn mô tả cách binding tham số vào advice từ pointcut args với tên biến nhất quán như thế nào?
Bạn sẽ sử dụng argNames khi Spring không xác định được tên tham số advice qua metadata như thế nào?
Bạn phân tích rủi ro Spring không bind được tham số @annotation nếu tên tham số trong biểu thức và advice không thống nhất ra sao?
Bạn sẽ thiết kế một custom annotation và aspect đọc metadata của annotation khi method bean được gọi như thế nào?
Bạn phân biệt annotation đặt trên method target với metadata có thể nhìn thấy qua proxy signature như thế nào?
Bạn sẽ xác định cách đọc annotation chính xác khi method đã bị bridge hoặc interface proxy hóa ra sao?
Bạn phân tích tại sao aspect có thể không được áp dụng khi method được gọi trong constructor của chính bean như thế nào?
Bạn sẽ xây dựng pointcut chỉ chọn method public thuộc Spring service nhưng loại trừ health và configuration methods ra sao?
Bạn xác định cách viết advice an toàn khi method trả một đối tượng mutable mà caller còn tiếp tục thay đổi như thế nào?
Bạn sẽ kiểm thử advice nhận đúng tham số và giá trị trả về với method bị overload như thế nào?
Bạn giải thích Spring AOP chọn JDK dynamic proxy khi target bean có interface trong những cấu hình nào?
Bạn phân biệt JDK dynamic proxy với CGLIB proxy theo kiểu đối tượng proxy được tạo và phương thức có thể gọi như thế nào?
Bạn sẽ kiểm tra Spring AOP đang sử dụng JDK proxy hay CGLIB cho một bean cụ thể bằng cách nào?
Bạn mô tả tác động của cấu hình proxyTargetClass=true khi bật @EnableAspectJAutoProxy như thế nào?
Bạn phân biệt spring.aop.proxy-target-class của Spring Boot với thuộc tính proxyTargetClass của @EnableAspectJAutoProxy ra sao?
Bạn sẽ xác định khi nào nên ép class-based proxy thay vì để Spring chọn cơ chế mặc định như thế nào?
Bạn phân tích nguy cơ inject theo implementation class khi bean thực tế là JDK dynamic proxy chỉ triển khai interface ra sao?
Bạn sẽ thiết kế dependency injection theo interface để tương thích với cả JDK proxy và CGLIB proxy như thế nào?
Bạn đánh giá tình huống ClassCastException xảy ra khi ép kiểu bean proxy sang target implementation ra sao?
Bạn sẽ giải thích giới hạn của CGLIB đối với final class và final method như thế nào?
Bạn phân tích vì sao private method không thể được override để advice theo cơ chế class-based proxy như thế nào?
Bạn sẽ kiểm tra tác động của visibility public, protected và package-private tới khả năng intercept theo loại proxy và phiên bản Spring ra sao?
Bạn mô tả vì sao method chỉ có trên implementation mà không khai báo trong interface có thể không truy cập được qua JDK proxy như thế nào?
Bạn phân biệt khả năng intercept method được gọi qua interface proxy và class proxy trong các tình huống nào?
Bạn sẽ đánh giá cấu hình Kotlin all-open khi Spring AOP phải tạo CGLIB proxy cho các class Kotlin ra sao?
Bạn phân tích rủi ro class hoặc method bị final do compiler khiến @Aspect không hoạt động như mong đợi như thế nào?
Bạn sẽ thiết kế kiểm thử xác minh method final không bị giả định là đã được advice theo chính sách bảo mật như thế nào?
Bạn giải thích lý do Spring AOP proxy không intercept method calls trên đối tượng không đi qua reference proxy như thế nào?
Bạn sẽ kiểm tra một bean được lấy qua ApplicationContext.getBean có thực sự là proxy hay không ra sao?
Bạn phân biệt getClass của proxy và target class khi dùng reflection hoặc annotation metadata như thế nào?
Bạn sẽ sử dụng AopUtils.isAopProxy và AopUtils.isJdkDynamicProxy để chẩn đoán trạng thái bean như thế nào?
Bạn phân biệt AopUtils.isCglibProxy với kiểm tra tên class chứa chuỗi CGLIB theo độ tin cậy như thế nào?
Bạn sẽ dùng AopUtils.getTargetClass để xác định class thực khi bean bị proxy như thế nào?
Bạn phân tích vì sao JDK dynamic proxy có thể gây khác biệt trong toString, equals và hashCode nếu code giả định target type ra sao?
Bạn sẽ kiểm tra metadata của advisor đang gắn với proxy bằng API Advised trong trường hợp được phép như thế nào?
Bạn mô tả tác động khi nhiều cơ chế tạo proxy cùng áp dụng lên một bean trong ApplicationContext như thế nào?
Bạn sẽ xác định cách tránh lạm dụng exposeProxy khi ứng dụng gặp self-invocation ra sao?
Bạn phân tích tác động của proxyTargetClass=true lên các AOP proxy khác cùng được auto-proxy creator quản lý như thế nào?
Bạn sẽ kiểm tra trường hợp bean được tạo bởi FactoryBean hoặc @Configuration có hành vi proxy khác dự kiến ra sao?
Bạn đánh giá tác động của proxy lên identity và reference của bean khi một component cache object từ quá sớm ra sao?
Bạn giải thích self-invocation làm lời gọi this.someMethod trong cùng bean bỏ qua Spring AOP proxy như thế nào?
Bạn phân biệt một external method invocation qua Spring proxy với internal invocation trong cùng target object ra sao?
Bạn sẽ mô tả tình huống @Around trên method service hoạt động khi controller gọi nhưng không hoạt động khi một method cùng service gọi nội bộ ra sao?
Bạn phân tích rủi ro self-invocation khiến logic logging, audit hoặc authorization dựa vào aspect bị bỏ qua như thế nào?
Bạn sẽ tái cấu trúc method cần advice sang bean khác để mọi lời gọi đi qua Spring proxy ra sao?
Bạn phân biệt tách bean theo trách nhiệm với tự inject proxy của chính bean để xử lý self-invocation như thế nào?
Bạn đánh giá nguy cơ circular dependency khi một bean cố inject chính proxy của nó ra sao?
Bạn sẽ xác định khi nào dùng AopContext.currentProxy trong một tình huống đặc biệt và những điều kiện cấu hình nào bắt buộc?
Bạn giải thích vai trò của exposeProxy=true khi một method muốn lấy Spring AOP proxy hiện tại như thế nào?
Bạn phân tích rủi ro phụ thuộc vào AopContext.currentProxy làm business code lệ thuộc hạ tầng proxy như thế nào?
Bạn sẽ kiểm thử trường hợp AopContext.currentProxy bị gọi ngoài phạm vi invocation đang qua proxy ra sao?
Bạn phân biệt gọi method thông qua this với gọi qua proxy lấy từ ApplicationContext trong một Bean như thế nào?
Bạn sẽ thiết kế test chứng minh @Before advice không chạy cho self-invocation nhưng chạy cho external invocation ra sao?
Bạn mô tả vì sao một method @PostConstruct gọi method được advice có thể bỏ qua proxy dù bean sau startup hoạt động đúng như thế nào?
Bạn phân tích tại sao tạo đối tượng bằng new trong service rồi gọi method có annotation aspect không được advice như thế nào?
Bạn sẽ xác định những entry points của bean cần được gọi thông qua proxy thay vì target reference ra sao?
Bạn giải thích vì sao AspectJ weaving có thể khác Spring AOP proxy trong việc xử lý self-invocation như thế nào?
Bạn sẽ lựa chọn refactoring thay vì chuyển ngay sang weaving khi một cơ chế Spring AOP không intercept được lời gọi ra sao?
Bạn phân tích giới hạn khi Spring AOP phải intercept constructor, field access hoặc lời gọi private methods ra sao?
Bạn sẽ kiểm tra method static được gọi qua class có bị logic Spring AOP advice áp dụng hay không như thế nào?
Bạn sẽ mô tả lý do Spring AOP thường không can thiệp trực tiếp vào lời gọi tới object bên ngoài ApplicationContext như thế nào?
Bạn phân biệt các trường hợp target method bị gọi bởi Spring framework và bởi chính target object đối với việc áp dụng proxy ra sao?
Bạn đánh giá nguy cơ giữ tham chiếu tới raw target thay vì Spring bean proxy trong một custom initialization code như thế nào?
Bạn sẽ chẩn đoán vì sao method annotated trong interface được thực thi nhưng advice không chạy khi bean bị tạo thủ công như thế nào?
Bạn giải thích @Order trên aspect ảnh hưởng thứ tự precedence khi nhiều Spring aspects khớp cùng method như thế nào?
Bạn phân biệt @Order với interface Ordered khi xác định độ ưu tiên advice trong Spring như thế nào?
Bạn sẽ dự đoán thứ tự bao bọc giữa hai @Around advices thuộc hai aspect có mức ưu tiên khác nhau ra sao?
Bạn mô tả thứ tự trước và sau proceed khi một @Around advice bao quanh một @Around advice khác như thế nào?
Bạn phân tích vì sao aspect có precedence cao hơn có thể chạy trước lúc vào nhưng chạy sau lúc thoát như thế nào?
Bạn sẽ thiết kế thứ tự logging và authorization aspects khi cả hai áp dụng trên cùng một service method ra sao?
Bạn đánh giá nên đặt metric aspect trước hay sau validation aspect theo ý nghĩa latency cần đo như thế nào?
Bạn sẽ xác định thứ tự @Before, @AfterReturning và @AfterThrowing khi chúng có khả năng cùng tác động tới lời gọi ra sao?
Bạn phân tích vì sao không nên dựa vào thứ tự khai báo advice trong source code của cùng một @Aspect như một contract ổn định ra sao?
Bạn sẽ tách những advices cần thứ tự rõ ràng sang nhiều aspect có @Order riêng như thế nào?
Bạn phân biệt thứ tự aspect precedence với thứ tự Spring BeanPostProcessor đăng ký advisor trong container ra sao?
Bạn sẽ kiểm tra chuỗi advisors của một proxy khi kết quả không đúng thứ tự mong đợi bằng cách nào?
Bạn mô tả cách một @Around advice có thể chặn @Before hoặc @AfterReturning ở lớp bên trong khi không gọi proceed ra sao?
Bạn đánh giá tác động nếu advice mức ưu tiên cao ném exception trước khi các advice khác được gọi ra sao?
Bạn sẽ thiết kế aspect kiểm tra quyền không bị bỏ qua bởi fallback của một @Around aspect khác như thế nào?
Bạn phân tích rủi ro advice ghi audit thành công trước khi transaction thật sự commit như thế nào?
Bạn sẽ xác định thứ tự giữa @Transactional và một @Aspect log để đo cả thời gian transaction hay chỉ thời gian nghiệp vụ ra sao?
Bạn phân biệt proxy do Spring transaction management tạo với proxy do @Aspect của ứng dụng tạo về khả năng kết hợp như thế nào?
Bạn sẽ kiểm tra thứ tự advice khi một service method đồng thời có @Transactional và custom @Around như thế nào?
Bạn phân tích trường hợp @Cacheable khiến target method không được gọi nhưng metric aspect vẫn chạy tùy thứ tự advice ra sao?
Bạn sẽ thiết kế đo cache hit và thời gian thực thi thực tế bằng cách chọn vị trí aspect phù hợp như thế nào?
Bạn mô tả ảnh hưởng của @Async đến thread đang thực thi một @Aspect đo latency như thế nào?
Bạn phân tích vì sao thời gian trả về Future từ @Async không luôn bằng thời gian công việc nền hoàn tất ra sao?
Bạn sẽ quyết định advice nào cần áp dụng ở ngoài hay trong cơ chế @Async để logging có ý nghĩa như thế nào?
Bạn giải thích vì sao Spring AOP advice đo thời gian method trả Mono có thể chỉ thấy thời gian tạo publisher chứ chưa phải thời gian thực thi I/O ra sao?
Bạn sẽ thiết kế aspect cho method trả Flux mà không nhầm thời điểm return với thời điểm stream hoàn tất như thế nào?
Bạn phân biệt đo synchronous method bằng proceed với đo kết quả subscription của Mono trong Spring WebFlux như thế nào?
Bạn sẽ xác định khi nào một @Around advice có thể decorate publisher bằng Reactor operators mà vẫn giữ contract trả về như thế nào?
Bạn phân tích rủi ro subscribe bên trong aspect khiến reactive pipeline bị chạy sớm hoặc bị thực thi nhiều lần ra sao?
Bạn sẽ bảo đảm aspect đo thời gian cho reactive result không giữ một ThreadLocal vượt qua vòng đời HTTP thread như thế nào?
Bạn giải thích vì sao security context trong reactive chain có thể nằm ở Reactor Context thay vì ThreadLocal mà aspect dùng như thế nào?
Bạn sẽ lựa chọn cách truyền correlation ID vào advice cho method thực thi qua @Async theo cơ chế nào?
Bạn phân tích rủi ro @Aspect dựa vào MDC ThreadLocal khi code đổi scheduler hoặc chạy bất đồng bộ ra sao?
Bạn sẽ thiết kế aspect cho CompletableFuture sao cho biết khi nào lời gọi ban đầu trả về và khi nào tác vụ thực sự hoàn tất ra sao?
Bạn phân biệt lỗi đồng bộ từ proceed với lỗi được Future hoặc Mono báo về sau khi method return như thế nào?
Bạn sẽ kiểm tra @AfterThrowing có quan sát được lỗi phát ra sau này từ một Flux hay không như thế nào?
Bạn đánh giá khi nào cần instrument Reactor pipeline thay vì chỉ thêm một Spring AOP advice cho reactive method ra sao?
Bạn sẽ thiết kế aspect chỉ bao phủ service methods cần kiểm toán thay vì mọi repository operation ra sao?
Bạn mô tả cách custom annotation kích hoạt một advice trong Spring khi method được gọi qua proxy như thế nào?
Bạn phân tích nguy cơ pointcut dùng execution quá rộng khiến các method infrastructure hoặc framework bị advice ngoài ý muốn ra sao?
Bạn sẽ tạo exclusion cho các method trong Aspect hoặc package instrumentation để tránh vòng lặp ghi log như thế nào?
Bạn sẽ xác định những bean được tạo bằng @Configuration và @Bean có cần advice hay không theo mục tiêu nghiệp vụ ra sao?
Bạn đánh giá rủi ro tự thêm aspect vào Spring Data repository proxies mà không phân biệt mục tiêu audit và metric ra sao?
Bạn sẽ phân biệt service bean proxy do Spring AOP tạo với dynamic proxy dùng để triển khai interface Spring Data Repository như thế nào?
Bạn mô tả cách một aspect khớp method trên repository proxy có thể tạo thêm tầng interception như thế nào?
Bạn sẽ kiểm tra behavior của pointcut @annotation khi annotation tồn tại trên repository interface nhưng implementation là proxy như thế nào?
Bạn phân tích vì sao một aspect bao phủ cả controller và service có thể ghi metric trùng cho một yêu cầu như thế nào?
Bạn sẽ thiết kế annotation cho audit rõ ràng để tránh advice chạy trên internal getter hoặc mapping method ra sao?
Bạn đánh giá cách bảo vệ tham số nhạy cảm khi aspect được áp dụng cho authentication service ra sao?
Bạn sẽ xác định khi nào không nên dùng aspect để triển khai authorization cốt lõi vì nguy cơ method không được proxy ra sao?
Bạn phân tích vì sao bảo mật phụ thuộc hoàn toàn vào pointcut pattern dễ bị bỏ qua khi refactor package hoặc method ra sao?
Bạn sẽ thiết kế các kiểm thử bắt buộc để xác nhận security-related Spring advice thực sự chạy ở entry points quan trọng ra sao?
Bạn mô tả cách một exception từ @Before advice ảnh hưởng transaction và HTTP response như thế nào?
Bạn sẽ kiểm tra một advice bị áp dụng hai lần khi bean có nhiều advisors hoặc proxy layers như thế nào?
Bạn phân tích nguy cơ aspect dùng state mutable trong singleton bean khi có nhiều request đồng thời ra sao?
Bạn sẽ thiết kế aspect stateless để không lưu argument hoặc request context vào field chung như thế nào?
Bạn đánh giá việc đọc toàn bộ tham số hoặc serialize response trong advice có thể tăng overhead và lộ dữ liệu như thế nào?
Bạn sẽ tối ưu việc tính metadata MethodSignature trong aspect được gọi với tần suất cao ra sao?
Bạn xác định cách tạo metric tags ổn định từ class và method mà không đưa tham số người dùng làm tag ra sao?
Bạn phân tích ảnh hưởng của advice ghi log đồng bộ trên đường request tới p99 latency như thế nào?
Bạn sẽ thiết kế aspect chỉ đo hoặc log theo sampling mà không làm thay đổi ngữ nghĩa target method như thế nào?
Bạn đánh giá sự khác biệt giữa audit có bảo đảm bền vững và log best-effort được thực hiện bởi một aspect như thế nào?
Bạn sẽ kiểm soát lỗi của hạ tầng telemetry trong advice để không làm hỏng business method ngoài ý muốn ra sao?
Bạn phân tích trường hợp advice gọi lại method cũng khớp pointcut gây chuỗi interception khó kiểm soát như thế nào?
Bạn sẽ xây dựng nguyên tắc không gọi business service từ aspect logging để tránh vòng phụ thuộc như thế nào?
Bạn giải thích vai trò của AopUtils và AopProxyUtils trong việc chẩn đoán Spring AOP proxy mà không cần sửa target ra sao?
Bạn sẽ lấy danh sách advisors từ một bean implements Advised để điều tra thứ tự thực thi như thế nào?
Bạn phân biệt advisor được tạo từ @Aspect với advisor của transaction hoặc cache khi xem chain của proxy ra sao?
Bạn sẽ kiểm tra AutoProxyCreator nào đang hoạt động nếu nhiều cấu hình AOP cùng có mặt trong ApplicationContext ra sao?
Bạn phân tích cách một BeanPostProcessor thêm proxy sau khởi tạo ảnh hưởng các listener hoặc bean khác giữ reference như thế nào?
Bạn sẽ xác định lý do một bean được tạo sớm không đủ điều kiện được auto-proxy như thế nào?
Bạn sẽ bật log chẩn đoán của Spring AOP để tìm lý do một pointcut không match mà không bật debug tràn lan như thế nào?
Bạn phân biệt một pointcut không khớp với một lời gọi bypass proxy bằng bằng chứng kiểm thử nào?
Bạn sẽ xác minh target bean tồn tại nhưng caller inject nhầm bean khác có cùng interface như thế nào?
Bạn phân tích cách @Primary và @Qualifier ảnh hưởng bean được inject và khả năng aspect được gọi ra sao?
Bạn sẽ kiểm tra bean name khi pointcut dùng bean pattern nhưng Spring bean có alias hoặc tên không mong đợi như thế nào?
Bạn mô tả cách một custom ProxyFactory có thể tạo proxy trong Spring nhưng không tự thay thế mọi bean tham chiếu tới target như thế nào?
Bạn sẽ so sánh cấu hình @Aspect với cách đăng ký Advisor programmatically khi cần kiểm soát phạm vi Spring bean ra sao?
Bạn đánh giá khi nào nên dùng @Aspect thay vì một MethodInterceptor đăng ký thủ công cho logic cắt ngang ứng dụng ra sao?
Bạn phân tích vì sao thêm Advisor trực tiếp vào một proxy có thể ảnh hưởng thứ tự advice đã được @Order xác định ra sao?
Bạn sẽ xác định khi nào bean target bị proxy nhiều lớp và cách kiểm tra proxy cuối cùng mà caller dùng ra sao?
Bạn sẽ quan sát phương thức nào thực sự được interceptor gọi khi proxy có interface và target implementation khác nhau như thế nào?
Bạn phân tích hậu quả của việc dùng class name từ proxy để tạo key cache hoặc audit thay vì target class như thế nào?
Bạn sẽ kiểm tra một library khác cấu hình proxyTargetClass có làm thay đổi proxy mode của aspect không như thế nào?
Bạn đánh giá rủi ro hai cấu hình @EnableAspectJAutoProxy khác nhau cùng tồn tại trong parent và child context ra sao?
Bạn sẽ thiết kế bộ test nhỏ tái hiện một lỗi Aspect trong ApplicationContext trước khi thay đổi logic production ra sao?
Bạn mô tả cách @SpringBootTest có thể kiểm tra một Spring bean thực sự đã được tạo proxy như thế nào?
Bạn sẽ dùng ApplicationContextRunner để kiểm tra điều kiện auto-configuration Spring AOP theo classpath và properties ra sao?
Bạn phân biệt unit test gọi trực tiếp new Service với integration test lấy service proxy từ ApplicationContext ra sao?
Bạn sẽ xác định vì sao mock một service làm @Aspect không chạy trong unit test dù production có proxy như thế nào?
Bạn đánh giá sự khác biệt khi dùng @MockBean hoặc mock replacement làm bean không còn giữ advisor chain như dự kiến ra sao?
Bạn sẽ thiết kế integration test kiểm tra @Before, @AfterReturning và @AfterThrowing trên ba nhánh thực thi ra sao?
Bạn kiểm thử @Around gọi proceed đúng một lần và giữ nguyên kết quả trả về bằng phương pháp nào?
Bạn sẽ kiểm thử một @Around advice có thể sửa tham số theo chủ đích nhưng không phá method signature như thế nào?
Bạn thiết kế test xác minh @After chạy kể cả khi target method ném exception ra sao?
Bạn sẽ kiểm tra binding annotation attribute vào advice hoạt động với method implementation ra sao?
Bạn xây dựng test cho execution pointcut có package và method overload để phát hiện method không khớp như thế nào?
Bạn sẽ kiểm thử pointcut bean chỉ áp dụng cho bean name mong muốn mà không ảnh hưởng bean cùng type như thế nào?
Bạn thiết kế test so sánh this và target pointcut khi đổi giữa JDK và CGLIB proxy ra sao?
Bạn sẽ kiểm tra JDK proxy của bean có interface và giới hạn inject theo implementation class như thế nào?
Bạn kiểm thử CGLIB proxy với final method để chứng minh giới hạn interception bằng cách nào?
Bạn sẽ thiết kế test cho method private, static hoặc constructor để xác nhận Spring AOP không được kỳ vọng intercept các trường hợp ấy ra sao?
Bạn xây dựng test self-invocation để so sánh một lời gọi external qua proxy và một lời gọi nội bộ qua this như thế nào?
Bạn sẽ kiểm thử giải pháp tách bean có sửa được lỗi self-invocation mà không tạo vòng dependency ra sao?
Bạn thiết kế test @PostConstruct gọi method được advice và so sánh hành vi sau startup như thế nào?
Bạn sẽ xác minh thứ tự thực thi giữa hai @Around aspects có @Order khác nhau bằng event trace ra sao?
Bạn kiểm thử advice security không bị fallback hoặc cache aspect khác bypass theo thứ tự advisors như thế nào?
Bạn sẽ tạo test so sánh @Transactional boundary trước và sau @Around tùy thứ tự advice ra sao?
Bạn đánh giá cách kiểm thử metric aspect đo thời gian thực tế của Mono hoặc Flux thay vì chỉ đo lúc tạo publisher như thế nào?
Bạn sẽ dùng StepVerifier kiểm tra một aspect decorate Mono không tạo subscription phụ và vẫn bảo toàn tín hiệu lỗi ra sao?
Bạn thiết kế test cho @AfterThrowing khi method trả Mono.error để phát hiện khác biệt giữa exception đồng bộ và tín hiệu reactive như thế nào?
Bạn sẽ kiểm tra @Async và custom aspect có giữ correlation context theo thread và completion như thế nào?
Bạn phân tích cách đo p95 latency trước và sau khi bật aspect logging dưới tải lớn như thế nào?
Bạn sẽ kiểm tra pointcut rộng không khiến số bean proxy tăng ngoài giới hạn chấp nhận được ra sao?
Bạn thiết kế test kiểm tra aspect singleton không rò rỉ request arguments giữa các thread như thế nào?
Bạn sẽ xây dựng kiểm thử chống lộ secret trong log khi advice nhận object chứa password hoặc token ra sao?
Bạn kiểm tra exception từ instrumentation advice không che khuất exception gốc của target bằng cách nào?
Bạn sẽ đặt tiêu chí nghiệm thu một custom @Aspect gồm đúng pointcut, đúng advice, thứ tự, bảo mật và hiệu năng ra sao?
Nếu @Aspect được khai báo nhưng không có effect khi gọi một service, bạn sẽ kiểm tra bean registration, pointcut và proxy theo thứ tự nào?
Nếu method có @annotation nhưng advice không chạy với JDK proxy, bạn sẽ kiểm tra nơi đặt annotation và method resolution như thế nào?
Nếu service tự gọi method có advice và logging bị thiếu, bạn sẽ phân biệt self-invocation với lỗi pointcut ra sao?
Nếu thay cấu hình sang CGLIB khiến một final method không được advice, bạn sẽ xử lý cấu trúc class như thế nào?
Nếu inject implementation class thất bại khi bật AOP, bạn sẽ kiểm tra JDK proxy và thiết kế injection ra sao?
Nếu @Around vô tình gọi proceed hai lần và tạo hai giao dịch, bạn sẽ sửa advice và bổ sung test nào?
Nếu @AfterReturning không bắt được một lỗi xuất hiện sau khi Mono được subscribe, bạn sẽ chọn cách quan sát reactive như thế nào?
Nếu method trả primitive nhưng một @Around advice trả null khi fallback, bạn sẽ sửa contract và xử lý lỗi ra sao?
Nếu @Transactional và custom aspect chạy sai thứ tự làm audit được ghi trước commit, bạn sẽ kiểm tra advisors và thiết kế audit như thế nào?
Nếu metric đếm một request hai lần do cùng pointcut áp dụng ở controller và service, bạn sẽ giới hạn pointcut ra sao?
Nếu aspect được đăng ký trong web ApplicationContext mà service bean nằm ở context cha, bạn sẽ điều chỉnh cấu hình như thế nào?
Nếu @Aspect lấy request ID từ MDC nhưng method chạy qua @Async bị mất context, bạn sẽ điều tra và sửa propagation ra sao?
Nếu một method bị chặn bởi @Cacheable nhưng audit advice vẫn chạy, bạn sẽ xác định thứ tự advisor và ý nghĩa audit như thế nào?
Nếu pointcut expression copy từ AspectJ dùng call hoặc field access và không hoạt động, bạn sẽ chọn cách xử lý trong phạm vi Spring AOP ra sao?
Nếu lời gọi từ @PostConstruct bỏ qua advice nhưng gọi từ controller lại chạy, bạn sẽ giải thích vòng đời bean và proxy như thế nào?
Nếu nhiều @Aspect có @Order khác nhau vẫn cho thứ tự khó hiểu, bạn sẽ đọc chain advisors và ghi trace thứ tự ra sao?
Nếu logging aspect làm tăng p99 latency đáng kể, bạn sẽ tối ưu pointcut, serialization và cơ chế ghi log như thế nào?
Nếu một aspect singleton giữ dữ liệu request trong field và làm lộ thông tin giữa các thread, bạn sẽ tái cấu trúc trạng thái như thế nào?
Nếu một Spring Data repository proxy bị áp thêm AOP proxy và phát sinh lỗi cast, bạn sẽ kiểm tra interface, proxy chain và injection ra sao?
Nếu một custom security advice không intercept được phương thức private trong service, bạn sẽ chuyển điểm kiểm tra quyền sang ranh giới nào?
Nếu cần đưa một @Aspect vào sản phẩm Spring Boot đang chạy, bạn sẽ thiết kế pointcut, proxy mode, ordering, tests và observability ra sao?
