Một dịch vụ thanh toán khai báo lớp @Aspect để ghi thời gian xử lý nhưng không đăng ký lớp đó thành Spring bean, khiến mọi lời gọi qua PaymentService đều thiếu thông tin đo đạc.
Một ứng dụng Spring Framework thuần có bean @Aspect và pointcut hợp lệ, nhưng cấu hình ApplicationContext chưa bật xử lý aspect nên advice không chạy sau khi khởi động.
Một nhóm tách aspect kiểm toán sang package mới ngoài phạm vi component scan, khiến các endpoint vẫn hoạt động nhưng log kiểm toán biến mất từ bản triển khai gần nhất.
Một dịch vụ bật spring-boot-starter-aop ở module phát triển nhưng không có dependency đó trong artifact production, khiến hành vi aspect chỉ xuất hiện khi chạy thử trên máy lập trình.
Một hệ thống có hai ApplicationContext cha và con, nhưng bean @Aspect được đăng ký trong context không quản lý OrderService khiến advice không áp dụng cho bean cần theo dõi.
Một ứng dụng chỉ import cấu hình aspect trong profile staging, khiến sau khi deploy production các lời gọi nghiệp vụ không được kiểm tra quy tắc log như kế hoạch.
Một nhóm khai báo aspect bằng @Bean trong cấu hình có điều kiện, nhưng điều kiện không thỏa ở Kubernetes nên không có proxy dù nghiệp vụ vẫn khởi tạo bình thường.
Một dịch vụ thêm @EnableAspectJAutoProxy vào một cấu hình không được Spring import, khiến người phát triển thấy annotation trong repository nhưng không có advisor nào được kích hoạt.
Một hệ thống có bean aspect được tạo trong một ApplicationContext riêng phục vụ job nền, nhưng API controller ở context khác không nhận được advice giám sát chung.
Một ứng dụng sử dụng cấu hình XML cho phần xử lý cũ và annotation config cho phần mới, khiến chỉ các bean được quản lý bởi context có hỗ trợ aspect nhận logic kiểm toán.
Một nhóm bật xử lý proxy-based AOP ở Spring Boot nhưng lại kỳ vọng aspect tự chạy trên object do một thư viện tạo bằng lệnh new bên ngoài container.
Một dịch vụ tạo WorkerService bằng phương thức factory thủ công ngoài Spring, khiến các method của worker không đi qua aspect giới hạn truy cập dù lớp có annotation nghiệp vụ.
Một ứng dụng khởi tạo một đối tượng service ngay trong controller thay vì inject Spring bean, khiến aspect kiểm tra quyền không quan sát các lời gọi tới đối tượng mới.
Một hệ thống khai báo @Aspect ở một module dùng chung nhưng cấu hình component scan chỉ quét module web, khiến các method service không có interceptor mong đợi.
Một nhóm triển khai hai bean của cùng lớp @Aspect với cấu hình khác nhau, khiến một lời gọi nghiệp vụ bị ghi hai bản log và tính thời gian hai lần.
Một ứng dụng vô tình bật cả một cấu hình import aspect và một bean @Component của cùng lớp, khiến số advisor áp dụng lên một service không như nhóm dự kiến.
Một nhóm muốn chỉ bật aspect thống kê cho workload production, nhưng @Profile được gắn lên cấu hình khác với bean aspect nên quy tắc vẫn áp dụng ở môi trường test.
Một dịch vụ khởi tạo bean trong BeanFactoryPostProcessor và gọi method sớm, khiến những lời gọi ở giai đoạn tạo bean không được advice giống các lời gọi sau khi context sẵn sàng.
Một hệ thống gọi nghiệp vụ ngay trong constructor của Spring bean, khiến advice dựa trên proxy chưa thể quan sát thao tác xảy ra lúc object đang khởi tạo.
Một ứng dụng gọi method quan trọng trong @PostConstruct rồi chờ aspect đo latency, nhưng báo cáo khởi động thiếu khoảng thời gian của lời gọi ban đầu.
Một nhóm gắn @Aspect lên class có dependency vòng với service được advice, khiến ApplicationContext gặp vấn đề tạo bean hoặc hành vi khởi tạo khác kỳ vọng.
Một dịch vụ muốn kiểm soát mọi lời gọi @Service nhưng một bean phụ trợ do framework tạo sớm không được proxy, khiến đường khởi tạo của nó không xuất hiện trong số liệu aspect.
Một ứng dụng bật aspect sau khi một module đã giữ tham chiếu trực tiếp đến target object, khiến lời gọi từ tham chiếu cũ không quan sát cùng advice như lời gọi qua proxy.
Một nhóm dùng BeanPostProcessor tự viết để thay bean sau giai đoạn tạo proxy, khiến OrderService ở context cuối không còn là object được advisor của Spring AOP bọc.
Một dịch vụ đóng gói aspect vào thư viện dùng chung nhưng các ứng dụng import cấu hình khác nhau, khiến cùng annotation nghiệp vụ cho kết quả intercept không thống nhất.
Một ứng dụng có PaymentServiceImpl implements PaymentService và dùng JDK dynamic proxy, nhưng component khác inject trực tiếp PaymentServiceImpl khiến quá trình wiring thất bại sau bật aspect.
Một nhóm ép Spring dùng class-based proxy để dễ inject lớp triển khai, nhưng lớp service được khai báo final nên proxy không thể tạo theo cơ chế đã chọn.
Một hệ thống sử dụng interface-based proxy cho BillingService, nhưng một module kỳ vọng bean có type cụ thể BillingServiceImpl và không tìm thấy bean thích hợp khi chạy.
Một dịch vụ có phương thức nội bộ không thuộc interface và dùng JDK proxy, khiến lời gọi đến phương thức này qua kiểu interface không thể đi theo API mà nhóm thiết kế kỳ vọng.
Một nhóm chuyển cấu hình proxyTargetClass giữa các environment, khiến cùng service lúc là JDK proxy lúc là CGLIB proxy và một đoạn kiểm tra kiểu runtime hoạt động khác nhau.
Một ứng dụng dùng CGLIB cho service có method final chứa nghiệp vụ tính giá, khiến aspect log được các method khác nhưng không đo được method tính giá đó.
Một dịch vụ khai báo method private để xác thực quyền và gắn annotation custom, nhưng aspect Spring AOP không chạy khi nội bộ class gọi method private này.
Một nhóm viết class-based proxy cho một class Kotlin vẫn final mặc định, khiến ApplicationContext không tạo được proxy cho service cần áp dụng advice.
Một hệ thống dùng Java record làm loại service bất biến và muốn CGLIB tạo proxy để thêm kiểm toán, khiến lựa chọn class-based proxy không tương thích với kiểu target này.
Một ứng dụng thêm một public method vào class triển khai nhưng không bổ sung vào interface, khiến consumer chỉ inject qua interface không thể gọi method mới qua JDK proxy.
Một nhóm cố lấy bean qua tên class gốc rồi kiểm tra equals theo class chính xác, khiến bước kiểm tra kiểu thất bại sau khi Spring trả proxy thay cho target.
Một dịch vụ serialize Spring bean proxied trực tiếp sang JSON trong endpoint debug, khiến cấu trúc runtime của proxy bị xử lý khác với DTO mà nhóm vận hành mong đợi.
Một nhóm dùng getClass để lấy annotation nghiệp vụ từ bean đã proxied, nhưng kết quả phụ thuộc kiểu JDK hoặc CGLIB proxy nên việc tìm metadata không nhất quán.
Một ứng dụng lưu tham chiếu bean vào trường kiểu implementation class, nhưng khi framework chọn JDK dynamic proxy bean không thể gán cho trường đó dù interface vẫn hợp lệ.
Một dịch vụ gắn aspect giới hạn truy cập lên phương thức chỉ có trong interface, nhưng nhóm thử nghiệm gọi trực tiếp target object không qua Spring proxy và không thấy advice.
Một nhóm tưởng class-based proxy sẽ intercept được mọi method, nhưng một method final xử lý số dư vẫn không xuất hiện trong log dù các lời gọi public khác được ghi nhận.
Một hệ thống có package-private method được gọi qua một kiểu proxy không phù hợp, khiến nhóm hỗ trợ cần xác định chính xác method nào được Spring AOP intercept.
Một ứng dụng bật proxy class-based trên service thuộc package có ràng buộc module Java, khiến việc tạo subclass proxy gặp giới hạn truy cập runtime trong môi trường production.
Một nhóm thêm aspect trên default method của interface rồi nâng phiên bản cấu hình proxy, khiến hành vi quan sát ở đường gọi qua interface và lớp triển khai cần được kiểm chứng lại.
Một dịch vụ vừa dùng Spring AOP vừa có một framework khác tự tạo proxy cho cùng bean, khiến thứ tự bọc proxy và kiểu bean cuối khác với giai đoạn trước nâng cấp.
Một nhóm kiểm tra bean có phải proxy bằng so sánh tên class với tên triển khai, khiến dashboard chẩn đoán nhầm một JDK proxy thành service không được đăng ký.
Một hệ thống dùng một interface cho nhiều implementation nhưng pointcut chỉ đặt theo implementation cụ thể, khiến một số bean có cùng hợp đồng không được intercept.
Một dịch vụ chuyển một class utility từ bean do Spring quản lý sang static helper, khiến pointcut Spring AOP không còn thấy các lời gọi kiểm tra nghiệp vụ trong helper.
Một ứng dụng tạo bean thủ công bằng new trong test thay vì lấy từ ApplicationContext, khiến unit test bỏ qua advice trong khi chạy production có proxy.
Một nhóm bật aspect cho một service được gọi từ Controller, nhưng khi service gọi chính method khác trong cùng class bằng this thì advice của method thứ hai không chạy.
Một dịch vụ ghi log nhờ @Around trên processPayment, nhưng một phương thức processBatch trong cùng bean gọi processPayment nội bộ khiến log chỉ hiện khi gọi từ bean khác.
Một hệ thống có method public kiểm tra hạn mức gọi từ hai nơi, nhưng lời gọi tự thân bên trong bean không đi qua proxy nên aspect xác thực không được áp dụng nhất quán.
Một ứng dụng chuyển logic từ hai bean sang một bean để giảm phụ thuộc, khiến đường gọi vốn đi qua proxy thành self-invocation và advice phân quyền không còn kích hoạt.
Một nhóm viết method helper được annotation theo dõi latency nhưng gọi helper trực tiếp từ method khác trong cùng object, khiến số liệu chỉ phản ánh lời gọi vào method ngoài.
Một dịch vụ thử gọi annotated method bằng this trong callback khởi tạo và kỳ vọng advice chạy, nhưng cả ngữ cảnh self-invocation lẫn thời điểm lifecycle làm kết quả khác dự kiến.
Một ứng dụng có method lấy dữ liệu gọi method ghi audit cùng bean, nhưng @Around trên method audit không xuất hiện trong trace khi call path không đi qua proxy.
Một nhóm refactor service thành hàm private cho nghiệp vụ chính, khiến annotation được chuyển vào method private và pointcut không còn điểm thực thi method qua Spring proxy.
Một hệ thống chạy method @Scheduled trong một bean có aspect đo đạc, nhưng một nhánh gọi self-invoked method trong lịch nền nên metric theo method con không được phát ra.
Một dịch vụ nhận lời gọi từ một bean khác qua interface proxy nhưng lại gọi method cùng class bên trong, khiến lần theo dõi advice chỉ thấy lớp entry mà thiếu bước xử lý con.
Một ứng dụng có aspect @Before kiểm tra quyền trên changeBalance, nhưng controller gọi service thông qua một tham chiếu target không được Spring quản lý khiến kiểm tra bị bỏ qua.
Một nhóm dùng AopContext.currentProxy trong code đã từng chạy với proxy exposure, nhưng một environment bỏ cấu hình exposeProxy khiến đường gọi này phát lỗi runtime.
Một dịch vụ có self-invocation được thiết kế lại qua một bean phối hợp, nhưng một đường xử lý cũ vẫn gọi trực tiếp target khiến dữ liệu kiểm toán giữa hai luồng không tương đồng.
Một ứng dụng kỳ vọng proxy Spring AOP sẽ can thiệp lệnh gọi constructor tạo invoice, khiến aspect không quan sát được sự kiện khởi tạo object dù method save sau đó được intercept.
Một nhóm muốn dùng advice Spring trên thay đổi trực tiếp một field trong entity, nhưng các biến đổi property không diễn ra qua lời gọi method của Spring-managed proxy.
Một dịch vụ dùng reflection gọi một private method của target rồi trông chờ Spring advice bảo vệ method, khiến thao tác bỏ qua ranh giới proxy mà controller bình thường sử dụng.
Một hệ thống dựa vào aspect để theo dõi lời gọi static method kiểm tra giá, nhưng method không phải lời gọi qua bean proxy nên không xuất hiện trong trace ứng dụng.
Một ứng dụng tạo service bằng Spring nhưng gọi phương thức của đối tượng con được tạo bên trong service, khiến aspect chỉ bao phủ Spring bean chứ không tự theo mọi object được tạo ra.
Một nhóm đưa annotation kiểm toán vào hàm extension Kotlin không thuộc bean Spring, khiến pointcut được viết cho method service không quan sát được lời gọi extension.
Một dịch vụ dùng aspect cho @Async method nhưng một nơi gọi method async qua self-invocation, khiến cả logic đo đạc và hành vi scheduling qua proxy đều khác với đường gọi từ bean khác.
Một hệ thống sử dụng controller advice và Spring AOP aspect cùng tên, khiến nhóm vận hành nhầm cơ chế bắt lỗi HTTP với method advice chạy tại service proxy.
Một nhóm cấu hình pointcut execution chỉ vào package com.shop.service nhưng service mới nằm trong com.shop.application, khiến yêu cầu mới không có audit dù class mang annotation @Service.
Một dịch vụ muốn aspect chỉ chạy trên public methods của bean OrderService, nhưng expression execution quá rộng khiến mọi method public của nhiều bean khác cũng bị ghi log.
Một ứng dụng đặt pointcut theo tên method save nhưng nhiều repository và service có cùng tên, khiến việc lưu log bị nhân nhiều lần ở những tầng không cần đo.
Một nhóm dùng pointcut within theo package có subpackage mới, nhưng biểu thức đang dùng không bao phủ cây package như người viết dự kiến nên advice bỏ sót xử lý mới.
Một hệ thống giới hạn pointcut bằng annotation @TrackLatency, nhưng annotation thực tế được đặt ở class thay vì method khiến @annotation không khớp những lời gọi cần đo.
Một ứng dụng dùng @within để nhận diện lớp có annotation nhưng một số method ở bean triển khai kế thừa từ class khác, khiến phạm vi intercept khác giả định của nhóm phát triển.
Một dịch vụ dùng @target cho annotation runtime trên class nhưng annotation không có retention phù hợp, khiến pointcut không nhận diện bean như thiết kế.
Một nhóm viết pointcut theo args nhận kiểu tham số runtime, nhưng API truyền subclass ở production và tập method khớp khác với điều kiện khai báo tĩnh.
Một ứng dụng so sánh this với target trong pointcut nhưng đang dùng JDK proxy, khiến quy tắc dựa trên kiểu interface và kiểu implementation cho kết quả không giống nhau.
Một dịch vụ dùng bean() pointcut theo tên bean Spring, nhưng sau khi thay tên @Bean trong cấu hình lời gọi không còn được advice dù class không thay đổi.
Một nhóm đặt pointcut bean(*Service) để lọc Spring beans nhưng các service được đăng ký bằng tên tùy biến, khiến phạm vi log khác tên class mà đội phát triển nhìn thấy.
Một hệ thống dùng @annotation(RequiresAudit) để ghi sự kiện nhưng annotation xuất hiện trên interface method trong một module, khiến việc nhận diện annotation giữa các kiểu proxy cần kiểm tra kỹ.
Một ứng dụng dùng execution bao phủ mọi method nhận String, khiến log chứa cả token bảo mật vì pointcut không lọc đúng service và method nghiệp vụ.
Một nhóm dùng pointcut chỉ theo tên get* cho API tra cứu nhưng một method getInvoice vừa cập nhật trạng thái đã đọc, khiến advice được kích hoạt trên thao tác có tác dụng phụ.
Một hệ thống dùng biểu thức phủ định pointcut để loại bean health check, nhưng tên bean đổi sau refactor khiến endpoint readiness cũng bị aspect theo dõi và tăng độ trễ.
Một dịch vụ phân biệt read/write theo package bằng pointcut, nhưng nghiệp vụ mới đặt ở package chung khiến advice phân quyền chỉ áp dụng một phần.
Một nhóm copy biểu thức pointcut từ AspectJ weaving có join point field access vào Spring AOP, khiến advice không thể khớp các thay đổi field dù class được Spring quản lý.
Một ứng dụng viết pointcut theo constructor execution và chờ kiểm soát mọi object nghiệp vụ, khiến các lần tạo entity không được advice dù service method hoạt động bình thường.
Một nhóm cố dùng cflow expression trong Spring AOP để lọc method theo chuỗi gọi, nhưng context khởi động không chấp nhận biểu thức như giả định khi chuyển từ AspectJ weaving.
Một hệ thống dùng @Pointcut đặt trong một lớp cấu hình riêng nhưng tên method được đổi, khiến các advice tham chiếu biểu thức cũ và aspect không khởi tạo đúng.
Một dịch vụ có pointcut đặt theo annotation nội bộ trong một dependency tùy chọn, nhưng production không có annotation class đó nên ApplicationContext lỗi khi đọc metadata.
Một nhóm áp dụng aspect vào package controllers và services cùng lúc, khiến một request qua controller rồi service tạo hai event đo latency và báo cáo đếm lặp.
Một ứng dụng lọc pointcut theo kết quả return type của method, nhưng method trả interface còn giá trị thật là implementation khác khiến biểu thức execution không khớp như nhóm kỳ vọng.
Một hệ thống dùng tham số annotation để ghi mã nghiệp vụ trong advice, nhưng pointcut chưa bind biến tương ứng khiến bean aspect lỗi lúc tạo advisor.
Một dịch vụ đổi tên tham số Java trong method được intercept nhưng aspect phụ thuộc vào binding args theo tên, khiến lúc nâng cấp thiếu thông tin bắt buộc.
Một nhóm đặt @Before trên pointcut xử lý tài khoản nhưng một method overload mới có danh sách tham số khác, khiến một nhánh không nhận advice như báo cáo dự kiến.
Một ứng dụng ghi audit bằng @Before nhưng sau đó service ném exception, khiến bản audit đã ghi không cho biết thao tác nghiệp vụ thực tế có thất bại hay không.
Một dịch vụ kiểm tra quyền bằng @Before nhưng cần thông tin do service tính ở cuối method, khiến advice không có dữ liệu cần thiết để xác minh kết quả.
Một nhóm gắn @AfterReturning để thu thập response nhưng service trả void cho nhiều thao tác, khiến số liệu không thể lấy kết quả nghiệp vụ như endpoint có DTO.
Một hệ thống ghi @AfterReturning cho method trả Order nhưng một nhánh trả subtype nhạy cảm, khiến aspect log toàn bộ payload và vi phạm chính sách che thông tin.
Một ứng dụng gắn @AfterThrowing vào method đổi điểm nhưng exception được bắt ngay bên trong service rồi trả giá trị lỗi, khiến advice không quan sát được lần xử lý thất bại.
Một dịch vụ dùng @AfterThrowing để báo lỗi database nhưng controller retry ở tầng ngoài, khiến cùng request sinh nhiều cảnh báo từ các lần gọi service khác nhau.
Một nhóm muốn advice @After chạy chỉ khi nghiệp vụ thành công, nhưng khi service ném exception event kiểm toán vẫn xuất hiện vì semantics của loại advice đã chọn.
Một hệ thống ghi trạng thái thành công bằng @After trên service, nhưng method trả lỗi giữa chừng và phần ghi log tạo cảm giác đơn đã được xử lý.
Một ứng dụng dùng @Around để đo latency nhưng một nhánh thoát sớm không gọi proceed, khiến method nghiệp vụ không thực thi dù controller nhận response từ advice.
Một nhóm triển khai @Around có logic gọi proceed hai lần khi gặp trạng thái đặc biệt, khiến một method tạo giao dịch được thực thi lặp lại ngoài ý muốn.
Một dịch vụ dùng @Around để thay kết quả trả về nhưng giá trị mới không phù hợp return type của method, khiến request chỉ lỗi sau khi advice trả về.
Một ứng dụng có @Around trả giá trị null cho method khai báo kiểu primitive, khiến proxy trả về gây lỗi runtime ở nhánh có điều kiện hiếm gặp.
Một nhóm ghi @Around bắt mọi Throwable rồi trả DTO mặc định, khiến lỗi truy cập database bị che và hệ thống giám sát thấy nhiều HTTP 200 giả.
Một dịch vụ có @Around dùng finally để đóng tài nguyên nhưng callback phụ ném lỗi, khiến exception gốc của method bị che bởi lỗi cleanup trong advice.
Một hệ thống dùng @Around để lưu thời gian đo, nhưng method trả CompletableFuture và advice chỉ đo thời gian trả future chứ không phản ánh khi tác vụ bất đồng bộ hoàn tất.
Một ứng dụng dùng @Around trên method trả Mono, nhưng metric được dừng ngay lúc publisher được tạo nên latency ghi nhận không bao gồm thực thi SQL sau subscribe.
Một nhóm dùng @AfterReturning để log đối tượng Mono của WebFlux service, khiến log chỉ có thông tin publisher và không biết kết quả dữ liệu thực tế khi subscription hoàn tất.
Một dịch vụ đặt @AfterThrowing trên reactive method trả Flux, nhưng lỗi xảy ra thành tín hiệu onError sau khi method trả publisher nên advice không nhận như lỗi ném đồng bộ.
Một hệ thống có @Around thay đổi args của method Spring bean nhưng một nhánh không duy trì tương quan giữa tham số tenant và token, khiến dữ liệu được xử lý dưới ngữ cảnh sai.
Một ứng dụng có aspect kiểm tra quyền và aspect ghi audit cùng áp dụng lên chuyển tiền, nhưng @Order chưa được thống nhất nên audit đôi lúc được ghi trước khi quyền được xác minh.
Một nhóm thêm @Order cho aspect đo latency và aspect retry, nhưng metric đo cả các lần thử lại ở môi trường này và chỉ đo một lần ở môi trường khác do thứ tự advisor thay đổi.
Một hệ thống dùng hai aspect @Around bao ngoài method tạo đơn, nhưng người vận hành tưởng thứ tự log lúc vào cũng là thứ tự lúc thoát nên báo cáo diễn giải sai chuỗi xử lý.
Một ứng dụng gắn cùng giá trị @Order cho hai aspect biến đổi header, khiến nhóm phát triển kỳ vọng thứ tự cố định mà không có quy tắc ưu tiên rõ ràng.
Một nhóm đặt hai @Before trong cùng một @Aspect và dùng thứ tự xuất hiện trong file Java để suy ra thứ tự gọi, khiến bài test kiểm toán không ổn định.
Một dịch vụ gắn @AfterThrowing và @AfterReturning trong cùng aspect lên method thanh toán, nhưng bộ giám sát ghép event theo thứ tự không phù hợp với đường thành công và đường lỗi.
Một hệ thống có aspect timing cùng với interceptor giao dịch của Spring, nhưng đoạn đo kết thúc trước khi commit nên metric không phản ánh toàn bộ thời gian hoàn tất giao dịch.
Một ứng dụng dùng aspect ghi audit trong @AfterReturning của method @Transactional, nhưng audit thông báo thành công trước khi transaction thật sự được commit nên đối soát bị lệch.
Một nhóm gắn aspect retry quanh method @Transactional, nhưng chưa xác định advisor nào bao ngoài nên việc thử lại có thể diễn ra với ranh giới giao dịch khác mong đợi.
Một dịch vụ dùng @Cacheable trên method tính giá cùng với aspect ghi log, nhưng một số lần cache hit không tạo log theo thời điểm mà nhóm nghiệp vụ kỳ vọng.
Một ứng dụng dùng aspect kiểm tra quyền và @Cacheable trên cùng method đọc hồ sơ, nhưng cấu hình advisor làm cache có thể được truy cập trước khi logic bảo vệ theo khía cạnh hoạt động.
Một nhóm thêm aspect để che dữ liệu nhạy cảm ở kết quả method @Cacheable, nhưng không xác định dữ liệu được cache trước hay sau khi che nên response giữa các request không nhất quán.
Một hệ thống dùng @Async trên method gửi email đồng thời @Around đo thời gian, nhưng metric đôi khi chỉ đo thao tác trả về Task handle thay vì thời gian gửi email.
Một ứng dụng lưu tenant ID vào ThreadLocal trong aspect trước method @Async, nhưng đoạn xử lý chạy ở thread pool khác không nhận được ngữ cảnh tenant mong đợi.
Một nhóm dùng MDC trong @Before và xóa bằng @After, nhưng khi nhiều aspect cùng thay MDC thứ tự cleanup làm trace ID ở log cuối request bị sai.
Một dịch vụ dùng aspect đo thời gian trên method trả CompletionStage, nhưng lời gọi hoàn thành lỗi sau khi proxy đã trả nên advice đồng bộ không ghi được latency thực.
Một hệ thống có aspect audit cùng @Retryable trên một service, nhưng chưa phân biệt event theo mỗi attempt với event theo request gốc nên số lần giao dịch bị đếm gấp.
Một nhóm áp dụng @Validated và aspect custom để kiểm tra tham số, nhưng thứ tự method validation với aspect ghi lỗi làm log chứa tham số chưa được làm sạch.
Một dịch vụ sử dụng method security do Spring quản lý và custom @Aspect kiểm quyền bổ sung, nhưng hai advisor trả loại lỗi khác nhau nên cùng yêu cầu bị từ chối không nhất quán.
Một ứng dụng dùng @Transactional và @Around trả giá trị fallback khi method ném exception, khiến nhóm vận hành không biết việc nuốt lỗi của advice ảnh hưởng quyết định rollback ra sao.
Một nhóm thêm aspect tính thời gian cho mọi repository interface, nhưng cùng request qua service và repository bị ghi nhiều span lồng nhau khiến dashboard đếm một giao dịch nhiều lần.
Một hệ thống có aspect che thông tin trong logger cùng interceptor tracing, nhưng thứ tự bọc proxy làm một vài request bị ghi payload gốc trước khi được ẩn.
Một ứng dụng đặt aspect @Around để gắn request ID vào ThreadLocal, nhưng một đường thực thi mới không có cleanup khi lỗi nên request kế tiếp trên cùng thread nhận sai định danh.
Một nhóm viết aspect chung cho cả phương thức gửi email và update database, nhưng sử dụng cùng retry policy trong advice khiến thao tác có tác dụng phụ bị lặp ngoài dự kiến.
Một dịch vụ dùng Spring AOP để kiểm soát transaction duration nhưng nghiệp vụ gọi callback sau khi method trả, khiến lời gọi callback không nằm trong vùng đo của advice.
Một ứng dụng có aspect timeout riêng và @Transactional trên method ghi đơn, nhưng việc advice ném lỗi sau khi backend đã commit khiến client hiểu nhầm thao tác chưa thực hiện.
Một nhóm nâng Spring Boot và thay đổi cách bật class-based proxy, khiến thứ tự advisor bảo mật và cache trong service cần được so sánh lại với bản trước nâng cấp.
Một hệ thống chạy các method @Scheduled qua Spring proxy và áp aspect ghi metric, nhưng test chỉ gọi trực tiếp target nên không phản ánh sự phối hợp giữa scheduler và advisor.
Một ứng dụng có bean aspect singleton chứa trường mutable requestStartTime, khiến hai request đồng thời cập nhật cùng trường và metric latency nhận thời gian của request khác.
Một nhóm xây aspect giới hạn số request bằng biến đếm trong instance @Aspect, nhưng nhiều replica Spring Boot giữ các bộ đếm riêng nên giới hạn toàn hệ thống bị vượt.
Một dịch vụ dùng @Around để lưu đối tượng JoinPoint vào một danh sách trong singleton aspect, khiến dữ liệu tham số của người dùng còn tồn tại trong heap sau request.
Một hệ thống ghi lại mọi argument từ JoinPoint.getArgs trong aspect truy vết, khiến token xác thực và thông tin thanh toán xuất hiện trên log tập trung ngoài chính sách bảo mật.
Một ứng dụng tạo tag metric từ giá trị method argument chứa customerId, khiến số chuỗi quan sát tăng mạnh khi aspect được áp cho mọi khách hàng.
Một nhóm dùng aspect log cả kết quả return của repository, nhưng response entity lớn làm tăng CPU serialize và độ trễ của endpoint danh sách.
Một dịch vụ có pointcut quá rộng tới hàng nghìn method Spring bean, khiến startup tạo nhiều proxy và thời gian khởi động tăng sau khi bật tính năng quan sát.
Một ứng dụng ghi log ở @Before cho từng lần gọi getter của Spring bean, khiến lượng log tăng gấp nhiều lần so với request thực và hệ thống lưu log bị quá tải.
Một nhóm để @Around tạo bộ formatter mới cho mỗi lời gọi method, khiến chi phí advice chiếm tỷ lệ đáng kể khi method nghiệp vụ chỉ thực hiện phép tính rất ngắn.
Một hệ thống dùng synchronized trong method advice bao quanh mọi thanh toán, khiến nhiều request qua cùng singleton aspect bị tuần tự hóa dù các service xử lý độc lập.
Một ứng dụng phát metric tại @AfterReturning nhưng registry metrics tạm chậm, khiến advice làm tăng latency của chính method đang được theo dõi.
Một nhóm sử dụng aspect kiểm tra feature flag từ API ngoài cho mỗi lời gọi bean, khiến dependency ngoài chậm kéo theo mọi endpoint vốn xử lý tại máy.
Một dịch vụ dùng pointcut theo cả controllers và services, khiến cùng request sinh nhiều audit records và khó xác định event nào là kết quả cuối cùng.
Một hệ thống triển khai aspect để thay đổi các tham số method trước xử lý, nhưng thao tác đó làm hỏng object dùng chung với nhánh async khác trong cùng request.
Một ứng dụng dùng aspect để gắn địa chỉ IP caller từ RequestContextHolder, nhưng method được gọi từ job nền không có HTTP request nên advice gặp lỗi tại runtime.
Một nhóm viết aspect kiểm quyền dựa trên SecurityContextHolder, nhưng task scheduler và HTTP request đi qua cùng service nên đường scheduler không có principal như giả định.
Một dịch vụ chạy WebFlux với aspect lấy thông tin người dùng từ ThreadLocal, khiến sau đổi scheduler giá trị không phản ánh Reactor Context của request đang xử lý.
Một ứng dụng dùng @Around cho method reactive và đặt logic thống kê trong finally của advice, khiến sự kiện hoàn tất được ghi ngay lúc trả publisher thay vì sau khi stream kết thúc.
Một nhóm xây aspect cập nhật MDC trên WebFlux method trả Flux, nhưng nhiều subscriber chạy khác thread khiến trace ID của từng tín hiệu không tương ứng request gốc.
Một hệ thống dùng @AfterThrowing để giám sát lỗi reactive transaction, nhưng tín hiệu onError xảy ra sau khi method trả nên dashboard không ghi các rollback được phát ra trong pipeline.
Một dịch vụ có @Around ghi log kết quả Mono bằng toString, khiến nội dung nghiệp vụ chỉ có khi subscribe không hiện trong log như đội hỗ trợ mong đợi.
Một nhóm đặt pointcut cho method controller WebFlux nhưng muốn đánh giá thời gian response streaming, khiến khoảng đo của Spring AOP không bao gồm việc truyền các phần tử Flux cho client.
Một ứng dụng dùng aspect ghi kết quả CompletableFuture sau khi method trả, khiến event ghi nhận trạng thái thành công trước khi future thất bại trên worker thread.
Một hệ thống có aspect nhận exception ném đồng bộ, nhưng một service mới chuyển sang trả Mono.error nên cùng cảnh báo lỗi không còn xuất hiện như bản đồng bộ.
Một dịch vụ dùng @Aspect để kiểm tra dữ liệu đầu vào trước khi controller service gọi Mono, nhưng dữ liệu chỉ được tạo từ publisher sau subscribe nên advice chưa có giá trị thực để kiểm.
Một nhóm dùng aspect để ghi kết quả method trả HttpEntity, nhưng đường reactive trả publisher của HttpEntity khiến cách đo response và serialization khác ứng dụng MVC trước đó.
Một ứng dụng có aspect kiểm tra quyền lưu tài liệu, nhưng endpoint streaming thực thi việc lưu muộn sau subscribe nên thời điểm audit khác với lúc client bắt đầu yêu cầu.
Một hệ thống sử dụng Spring proxy cho bean scope prototype nhưng aspect giữ state theo lần xử lý trong một field static, khiến nhiều bean instance vẫn chia sẻ trạng thái không an toàn.
Một dịch vụ dùng request-scoped bean có proxy riêng cùng aspect giám sát, khiến một lời gọi qua chuỗi proxy lồng nhau khó được quy về đúng target khi debug.
Một nhóm khai báo aspect cho bean @Lazy nhưng gọi method từ bean trong lúc startup, khiến lần tạo proxy và thời điểm target được khởi tạo cần được điều tra khi xảy ra lỗi.
Một ứng dụng tiêm ObjectProvider<Service> rồi gọi method trực tiếp trên object từ provider, nhưng một đường xử lý khác tự dựng target nên cùng nghiệp vụ có số advice khác nhau.
Một hệ thống dùng FactoryBean trả về service cần kiểm toán, nhưng đối tượng thực được tạo theo lifecycle đặc biệt và nhóm cần xác nhận bean cuối có qua cơ chế proxy hay không.
Một dịch vụ có custom BeanPostProcessor bọc bean bằng proxy khác sau Spring AOP, khiến công cụ introspection thấy nhiều lớp proxy và tên target không còn hiển nhiên.
Một nhóm dùng scoped proxy cho tenant service nhưng aspect dựa vào bean name để chọn policy, khiến tên bean trung gian thay đổi cách pointcut bean() khớp.
Một ứng dụng dùng bean method trả interface trong @Configuration, nhưng runtime target có annotation trên class triển khai khiến một pointcut dựa trên annotation cần được kiểm chứng.
Một hệ thống đổi bean scope từ singleton sang request, khiến aspect quản lý bộ đếm bằng field singleton không còn đo đúng số method call trên từng request.
Một dịch vụ kết hợp @Primary với nhiều bean cùng interface, nhưng aspect gắn theo tên bean của triển khai cũ nên bean được inject thực tế không nhận advice.
Một nhóm bật AOP trong Spring test context khác production, khiến kết quả test dựa trên JDK proxy trong khi ứng dụng thật dùng CGLIB với phạm vi intercept khác.
Một ứng dụng chỉ khởi tạo aspect bằng constructor trực tiếp trong unit test và gọi method advice, khiến test pass dù pointcut không khớp bất kỳ Spring bean nào khi deploy.
Một nhóm dùng Mockito mock thay toàn bộ PaymentService trong @SpringBootTest, khiến lời gọi test không đi qua method implementation thực và kết quả kiểm advice bị hiểu nhầm.
Một dịch vụ kiểm thử @Around bằng cách mock ProceedingJoinPoint, nhưng chưa xác minh proxy của Spring thực sự được tạo cho OrderService trong ApplicationContext.
Một hệ thống dùng @WebMvcTest chỉ load controller và mock service, khiến aspect thuộc service package không được tạo và bài test không thể xác nhận kiểm toán production.
Một ứng dụng dùng @SpringBootTest nhưng đặt profile tắt aspect hiệu năng, khiến suite báo thành công mà không thực thi advice cần kiểm tra cho môi trường vận hành.
Một nhóm kiểm tra AopUtils.isAopProxy trên bean được inject nhưng không phân biệt JDK với CGLIB proxy, khiến kết luận về khả năng gọi method implementation thiếu căn cứ.
Một dịch vụ dùng AopUtils.getTargetClass để xác định bean đã được bọc, nhưng test chỉ so tên class và không xác minh advisor kiểm toán có nằm trong proxy.
Một hệ thống đọc danh sách advisors từ bean implement Advised khi debug, nhưng một đường code giả định mọi bean đều cast được sang Advised và gây lỗi với bean không proxied.
Một nhóm kiểm thử self-invocation chỉ bằng gọi method từ một Spring bean khác, khiến tình huống method tự gọi trong cùng target chưa được mô phỏng.
Một ứng dụng có method final quan trọng nhưng integration test chỉ gọi public method không final, khiến giới hạn CGLIB proxy không bị phát hiện trước release.
Một dịch vụ test @AfterThrowing chỉ với exception ném trực tiếp, nhưng production bắt rồi biến lỗi thành giá trị return nên cảnh báo thiếu ở một nhánh nghiệp vụ.
Một nhóm kiểm tra @AfterReturning với service trả DTO bình thường nhưng không thử trường hợp trả null, khiến logic advice log response phát lỗi ở production.
Một hệ thống có nhiều aspect dùng @Order nhưng test chỉ assert số lần gọi, khiến thứ tự thực tế giữa xác thực, transaction và audit vẫn chưa được xác nhận.
Một ứng dụng test aspect @Around bằng mock service trả thành công, nhưng không ép exception từ proceed nên đường cleanup và báo lỗi chưa được kiểm thử.
Một nhóm refactor pointcut execution để bỏ qua các getter, nhưng không có test xác minh các method overload nên một method nghiệp vụ mới không nhận audit.
Một dịch vụ kiểm tra aspect ở context chạy ứng dụng nhưng chưa kiểm tra context của scheduled worker, khiến cùng @Aspect có mặt ở API mà vắng ở tác vụ nền.
Một hệ thống muốn đo tác động hiệu năng của aspect nhưng benchmark chỉ gọi target trực tiếp, khiến chi phí proxy/advice không xuất hiện trong số liệu trước và sau.
Một nhóm dùng @EnableAspectJAutoProxy trong test configuration nhưng production dùng cấu hình Boot, khiến sự khác biệt proxyTargetClass làm một số wiring thất bại chỉ khi phát hành.
Một ứng dụng kiểm thử thông tin metadata annotation trên implementation method nhưng gọi qua JDK proxy trong production, khiến pointcut phải được xác minh trên dạng method thực tế.
Một nhóm dùng AspectJ pointcut expression mới mà không chạy ApplicationContext test, khiến lỗi parse biểu thức chỉ bộc lộ khi hệ thống bắt đầu tạo advisor.
Một dịch vụ có hai bean cùng tên ở hai context, nhưng test chỉ load một context nên khác biệt phạm vi của bean() pointcut không được phát hiện.
Một ứng dụng nâng Spring Framework và phát hiện service bị bọc nhiều proxy hơn, nhưng test chưa xác minh số advisor và metric latency bị ghi nhân đôi.
Một hệ thống dùng aspect audit cho phương thức tạo đơn và lưu log ngoài database nghiệp vụ, nhưng khi transaction rollback log đã lưu khiến quy trình kiểm toán hiểu nhầm kết quả.
Một nhóm quản lý aspect bằng cấu hình riêng cho từng microservice, nhưng bản sao cấu hình của service B còn pointcut tham chiếu package service A và ghi log sai phạm vi.
Một ứng dụng đưa annotation @TrackLatency lên method interface rồi thay bằng annotation trên implementation trong release mới, khiến advice không được kiểm tra lại trên cả hai kiểu proxy.
Một dịch vụ đưa logic bắt lỗi vào @Around để chuẩn hóa exception, nhưng không phân biệt lỗi nghiệp vụ với lỗi hạ tầng khiến HTTP response và alert sai loại.
Một hệ thống yêu cầu không log số thẻ từ method thanh toán, nhưng aspect dùng JoinPoint.getArgs chung cho mọi method nên dữ liệu thô vẫn đi vào audit trail.
Một nhóm thêm aspect đếm số request dựa trên method signature nhưng các overload được gom theo cùng tên, khiến metric cho hai hành vi nghiệp vụ khó phân biệt.
Một ứng dụng dùng @annotation để chọn method cần đo nhưng aspect lấy orderId từ JoinPoint.getArgs làm tag metric, khiến số chuỗi tăng theo từng đơn hàng.
Một nhóm muốn chỉ dùng proxy Spring AOP mà mang nguyên pointcut từ AspectJ compile-time weaving, khiến người triển khai kỳ vọng cả field access và constructor call đều được giám sát.
Một hệ thống chuyển một service từ bean Spring sang object được framework plugin tự tạo, khiến lời gọi plugin không qua proxy dù tên class vẫn khớp execution pointcut.
Một dịch vụ debug bằng cách gọi thẳng instance target lấy từ proxy thay vì bean được Spring trả về, khiến advice không chạy và các số liệu log có vẻ mâu thuẫn.
Một nhóm sửa một bean tự đăng ký bằng BeanDefinitionRegistry nhưng chưa kiểm chứng post-processing AOP, khiến service khởi tạo thành công mà không được gắn advisor cần thiết.
Một ứng dụng chạy native image và sử dụng CGLIB proxy cho một service có cấu hình AOT không tương thích, khiến bản native startup lỗi dù chạy JVM bình thường.
Một hệ thống cần bật tắt aspect theo cấu hình runtime, nhưng bean aspect được tạo lúc khởi động nên đội vận hành không thấy pointcut thay đổi chỉ bằng sửa property.
Một nhóm thay đổi @Order sau khi deploy bằng cách sửa một file config, nhưng Spring advisors đã khởi tạo và thứ tự thực thi không đổi như kỳ vọng tại runtime.
Một ứng dụng có aspect xử lý khắp service layer nhưng không ghi tên bean, proxy type và method được match khi debug, khiến việc điều tra lời gọi không được intercept rất tốn thời gian.
Một dịch vụ thêm aspect giới hạn số lần xử lý một event, nhưng event được gửi từ cả Spring bean và object không do Spring quản lý nên hai đường có hành vi khác nhau.
Một hệ thống dùng custom annotation để xác định method cần kiểm toán nhưng annotation thiếu RUNTIME retention, khiến pointcut @annotation không nhận được metadata khi bean chạy.
Một ứng dụng khai báo pointcut nhắm vào protected helper của class-based proxy nhưng caller chỉ sử dụng phương thức public tự gọi nội bộ, khiến helper không được intercept như mong đợi.
Một nhóm dùng aspect @Around để trì hoãn lời gọi tài nguyên ngoài, nhưng method vẫn giữ lock ở tầng gọi và advice kéo dài thời gian chiếm lock dưới tải.
Một dịch vụ có aspect tracing cùng một filter HTTP ghi span, nhưng không xác định ranh giới đo tại controller hay service proxy khiến cùng request tạo dấu thời gian trùng.
Một hệ thống muốn áp aspect phân quyền cho method setter trên entity do ORM tạo, nhưng entity không phải Spring-managed service proxy nên annotation không tạo lớp bảo vệ thực tế.
