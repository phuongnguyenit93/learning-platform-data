Câu 1. Spring Boot bổ sung giá trị chính nào so với cấu hình Spring Framework thủ công?
A. Thay toàn bộ IoC container bằng một hệ thống quản lý bean mới
B. Bắt buộc khai báo từng servlet và bean qua XML khi khởi động
C. Cung cấp starter và auto-configuration theo điều kiện ứng dụng
D. Thay cơ chế dependency injection bằng truy cập bean tĩnh
Đáp án đúng: C

Câu 2. @SpringBootApplication kết hợp chủ yếu những annotation nào?
A. @Service, @Repository và @Controller cho tất cả lớp ứng dụng
B. @SpringBootConfiguration, @EnableAutoConfiguration và @ComponentScan
C. @ConfigurationProperties, @Profile và @PropertySource
D. @EnableScheduling, @EnableCaching và @EnableAsync
Đáp án đúng: B

Câu 3. Một Spring Boot starter chủ yếu được dùng để làm gì?
A. Gom các dependency cho cùng một nhóm tính năng
B. Chạy thay SpringApplication khi bắt đầu ứng dụng
C. Khởi tạo mọi bean dù thiếu điều kiện classpath
D. Lưu tham số runtime từ các biến môi trường
Đáp án đúng: A

Câu 4. Với spring-boot-starter-web, thành phần nào thường có trên classpath?
A. Spring WebFlux cùng Netty được buộc dùng mặc định
B. Spring Batch cùng JobRepository tạo tự động
C. Spring Security cùng mọi luật phân quyền mặc định
D. Spring MVC cùng web servlet stack được cấu hình
Đáp án đúng: D

Câu 5. SpringApplication.run(...) thường trả về đối tượng kiểu nào?
A. ApplicationRunner chứa các tham số dòng lệnh
B. Trả về ConfigurableApplicationContext đã tạo
C. BeanDefinitionRegistry chứa mọi cấu hình đã tìm
D. EnvironmentPostProcessor chứa property nguồn
Đáp án đúng: B

Câu 6. Vì sao class @SpringBootApplication thường đặt tại package gốc dự án?
A. Giúp JVM tự tìm mọi class không cần cơ chế quét
B. Để component scan bao phủ các subpackage của dự án
C. Làm cấu hình user luôn thắng mọi property ngoài file
D. Bảo đảm @Bean chỉ được gọi ở package gốc
Đáp án đúng: B

Câu 7. Trong Spring Boot, phạm vi quét component mặc định thường bắt đầu ở đâu?
A. Package chứa @SpringBootApplication và các nhánh con
B. Toàn bộ dependency JAR của ứng dụng không cần cấu hình
C. Chỉ package của lớp @ConfigurationProperties đầu tiên
D. Chỉ các package được khai trong file application.yml
Đáp án đúng: A

Câu 8. Khác biệt chính của @Bean so với @Component khi đăng ký bean là gì?
A. @Bean chỉ áp dụng cho interface; @Component dùng cho method
B. @Bean đánh dấu factory method; @Component đánh dấu class
C. @Bean buộc tạo prototype; @Component buộc tạo request scope
D. @Bean tự bật auto-config; @Component tự tắt component scan
Đáp án đúng: B

Câu 9. @Service trong Spring thường biểu thị ý nghĩa gì?
A. Stereotype @Controller chuyên nhận HTTP request từ client
B. Stereotype @Component dành cho lớp xử lý nghiệp vụ
C. Annotation cấu hình dữ liệu của Environment property
D. Annotation thay thế @Transactional trên mọi method
Đáp án đúng: B

Câu 10. @Repository trên lớp persistence có thêm lợi ích nào khi được hỗ trợ?
A. Tự tạo REST endpoint cho tất cả câu truy vấn của repository
B. Tự mở transaction mới trước mỗi lần đọc EntityManager
C. Cho phép cơ chế dịch exception của tầng truy cập dữ liệu
D. Tự thay thế DataSource bằng connection pool mặc định
Đáp án đúng: C

Câu 11. Trong cơ chế IoC của Spring, ai chịu trách nhiệm quản lý bean và dependency?
A. Từng controller tự tạo dependency bằng từ khóa new
B. ApplicationContext tạo bean và inject dependency
C. JVM tự gắn dependency theo tên class khi chạy
D. Build tool quyết định inject bean vào từng constructor
Đáp án đúng: B

Câu 12. Vì sao constructor injection thường được ưu tiên cho dependency bắt buộc?
A. Tự tránh hoàn toàn mọi chu trình dependency giữa các bean
B. Cho phép container thay đổi field final sau khi khởi tạo
C. Giúp bean truy cập ApplicationContext trong mọi method
D. Giúp biểu diễn dependency rõ ràng và dễ viết unit test
Đáp án đúng: D

Câu 13. Khi bean phụ thuộc một dịch vụ tùy chọn có thể không tồn tại, cách nào phù hợp?
A. Inject ObjectProvider để lấy bean khi thực sự cần
B. Đánh dấu dependency là @Primary dù bean chưa có
C. Dùng @Qualifier với tên class không nằm trong context
D. Dùng @Bean(initMethod=...) để tìm bean lúc compile
Đáp án đúng: A

Câu 14. Với class chỉ có một constructor, Spring xử lý @Autowired như thế nào?
A. Phải gắn @Autowired trên từng parameter constructor
B. Chỉ inject khi constructor được khai báo không tham số
C. Chỉ inject bằng field nếu không tìm thấy @Autowired
D. Có thể inject constructor đó dù không ghi @Autowired
Đáp án đúng: D

Câu 15. Khi context có nhiều bean cùng interface, @Qualifier dùng để làm gì?
A. Đặt bean được chọn vào scope singleton vĩnh viễn
B. Chuyển nhiều bean thành danh sách dependency mặc định
C. Chọn bean cụ thể cần inject theo qualifier hoặc tên
D. Buộc auto-configuration tạo bean mới có cùng interface
Đáp án đúng: C

Câu 16. Khi một bean có @Primary trong số nhiều bean cùng kiểu, ý nghĩa nào đúng?
A. Loại bỏ toàn bộ bean khác khỏi application context
B. Ưu tiên bean đó khi autowire một ứng viên cùng kiểu
C. Đảm bảo bean đó được khởi tạo trước mọi singleton
D. Bắt buộc inject bean đó dù có @Qualifier cụ thể khác
Đáp án đúng: B

Câu 17. Scope mặc định của bean do Spring quản lý thường là gì?
A. Singleton cho từng bean definition trong container
B. Prototype tạo đối tượng mới cho mỗi lần gọi method
C. Request tạo đối tượng riêng cho mỗi HTTP request
D. Session tạo đối tượng riêng cho mỗi phiên người dùng
Đáp án đúng: A

Câu 18. Với bean scope prototype, container thường làm gì khi lấy bean nhiều lần?
A. Dùng đúng một instance cho toàn bộ ApplicationContext
B. Lưu một instance cho mỗi người dùng đăng nhập
C. Tạo lại instance chỉ khi context khởi động lại
D. Tạo instance mới cho mỗi lần container được yêu cầu
Đáp án đúng: D

Câu 19. @PostConstruct thường được dùng ở giai đoạn nào của bean?
A. Trước khi constructor được gọi để đăng ký bean
B. Sau khi dependency được inject để khởi tạo tài nguyên
C. Sau khi ApplicationContext đóng để hủy tài nguyên
D. Sau khi từng HTTP request hoàn tất để dọn dữ liệu
Đáp án đúng: B

Câu 20. Với @PreDestroy trên bean singleton được container quản lý, callback thường chạy lúc nào?
A. Trước khi constructor bean chạy lần đầu trong context
B. Ngay sau mỗi lần method nghiệp vụ của bean hoàn tất
C. Khi bean bị hủy trong quá trình đóng application context
D. Ngay khi một người dùng gửi request cuối cùng
Đáp án đúng: C

Câu 21. ApplicationRunner và CommandLineRunner thường chạy vào thời điểm nào?
A. Sau khởi tạo context, trước ApplicationReadyEvent
B. Trước khi bean definition bắt đầu được đăng ký
C. Ngay khi JVM tải class chứa @SpringBootApplication
D. Sau khi ApplicationContext đã đóng hoàn toàn
Đáp án đúng: A

Câu 22. ApplicationReadyEvent thông báo trạng thái nào của ứng dụng?
A. Spring mới bắt đầu đọc các bean definitions của ứng dụng
B. ApplicationContext chuẩn bị được tạo nhưng chưa refresh
C. Graceful shutdown đã ngừng nhận mọi request mới
D. Ứng dụng đã khởi động xong và có thể nhận yêu cầu
Đáp án đúng: D

Câu 23. File application.yml hoặc application.properties thường giữ vai trò gì?
A. Lưu trực tiếp các bean instance đã tạo trong heap
B. Biên dịch class @Configuration thành bytecode Java
C. Cung cấp cấu hình ngoài code cho ứng dụng khi chạy
D. Thay đổi logic business của controller sau khi đóng gói
Đáp án đúng: C

Câu 24. Khi inject một property đơn lẻ vào bean, cú pháp nào phù hợp?
A. @Value với placeholder như ${app.timeout}
B. @Qualifier với tên key như ${app.timeout}
C. @Primary với chuỗi tên property mong muốn
D. @ComponentScan với prefix cấu hình cần đọc
Đáp án đúng: A

Câu 25. Khi có nhóm cấu hình cùng prefix, phương án type-safe nào phù hợp?
A. Dùng @ConfigurationProperties để bind vào một class
B. Dùng @PostConstruct trên từng field để đọc file
C. Dùng @DependsOn để chuyển mọi YAML thành POJO
D. Dùng @Repository để ánh xạ các property thành entity
Đáp án đúng: A

Câu 26. Để tải thêm application-dev.yml khi profile dev được kích hoạt, cần làm gì?
A. Đổi tên @SpringBootApplication thành DevApplication
B. Thêm @Primary vào tất cả bean của cấu hình dev
C. Kích hoạt profile dev qua cấu hình hoặc biến môi trường
D. Đặt giá trị dev trong logging.level.root của ứng dụng
Đáp án đúng: C

Câu 27. @Profile("test") trên một bean definition có tác dụng gì?
A. Tự đổi classpath của JVM sang dependency cho test
B. Chỉ chạy method @PostConstruct ở chế độ test
C. Tự thay mọi bean cùng tên khi mở Spring Boot Test
D. Đăng ký bean khi profile test đang được kích hoạt
Đáp án đúng: D

Câu 28. Nếu environment variable và application.properties cùng cấu hình một key, giá trị nào thường ưu tiên?
A. Giá trị trong application.properties vì file luôn ưu tiên hơn
B. Dùng giá trị biến môi trường theo thứ tự ưu tiên
C. Giá trị nào có tên key dài hơn sau khi relaxed binding
D. Giá trị của bean được tạo sớm hơn khi startup
Đáp án đúng: B

Câu 29. Khi truyền --server.port=9090 lúc chạy ứng dụng, điều gì thường xảy ra?
A. Server port bị bỏ qua vì phải dùng biến môi trường
B. Giá trị trong file luôn ghi đè tham số command line
C. Tham số command-line ưu tiên hơn giá trị ở file
D. Port chỉ thay đổi sau khi ApplicationContext refresh lần hai
Đáp án đúng: C

Câu 30. Placeholder ${service.timeout:5000} trong cấu hình có ý nghĩa nào?
A. Dùng giá trị 5000 nếu service.timeout không tồn tại
B. Đọc property service.timeout và buộc nó bằng 5000
C. Tạo một bean có tên service.timeout trong context
D. Gán port 5000 cho server dù có property tương ứng
Đáp án đúng: A

Câu 31. Cách phù hợp để quản lý mật khẩu database ở môi trường production là gì?
A. Đưa mật khẩu vào source code của @Configuration class
B. Ghi mật khẩu ra log startup để kiểm tra kết nối
C. Gắn mật khẩu cố định trong artifact JAR phát hành
D. Dùng secret manager hoặc cấu hình bảo mật riêng
Đáp án đúng: D

Câu 32. Với Spring Boot starter thông dụng, lựa chọn logging mặc định thường là gì?
A. Java Util Logging API với Log4j2 làm backend mặc định
B. Log4j 1.x làm backend bắt buộc cho mọi starter
C. SLF4J API với Logback làm backend logging
D. System.out.println là framework logging duy nhất
Đáp án đúng: C

Câu 33. Muốn đặt log mức DEBUG cho package com.acme.orders, property nào phù hợp?
A. logging.pattern.com.acme.orders=DEBUG
B. spring.profiles.com.acme.orders=DEBUG
C. logging.level.com.acme.orders=DEBUG
D. management.level.com.acme.orders=DEBUG
Đáp án đúng: C

Câu 34. Khi log request có thông tin cá nhân, cách nào an toàn hơn?
A. Che PII và gắn correlation ID khi ghi log request
B. Ghi đầy đủ Authorization header cho mỗi request
C. Đẩy nguyên payload người dùng vào mọi error trace
D. Chuyển tất cả mật khẩu thành message DEBUG
Đáp án đúng: A

Câu 35. Thêm spring-boot-starter-actuator chủ yếu hỗ trợ việc gì?
A. Thay thế web controller bằng giao diện quản trị
B. Cung cấp endpoint theo dõi và quản lý ứng dụng
C. Tự chạy test JUnit sau mỗi lần health check
D. Tự thay đổi thread pool khi CPU vượt ngưỡng
Đáp án đúng: B

Câu 36. Endpoint Actuator nào thường được dùng để kiểm tra health ứng dụng?
A. /actuator/beans dùng để gửi thông tin sức khỏe
B. /actuator/loggers chỉ dùng để kiểm tra DB uptime
C. Dùng /actuator/health để xem tình trạng ứng dụng
D. /actuator/env tự tính trạng thái health của server
Đáp án đúng: C

Câu 37. Khi cần khảo sát metric runtime qua Actuator, endpoint nào có liên quan?
A. /actuator/metrics nếu được bật và expose phù hợp
B. /actuator/conditions khi cần danh sách counter JVM
C. /actuator/mappings khi cần biểu đồ heap memory
D. /actuator/configprops khi muốn đo thời gian HTTP
Đáp án đúng: A

Câu 38. Khi bật Actuator trên môi trường thật, nguyên tắc bảo mật nào phù hợp?
A. Mở mọi endpoint quản lý ra Internet để dễ debug
B. Cấp quyền ghi cấu hình cho tất cả HTTP client
C. Cho mọi endpoint in secret để chẩn đoán khi lỗi
D. Giới hạn endpoint expose và kiểm tra quyền truy cập
Đáp án đúng: D

Câu 39. Ứng dụng Spring Boot dùng embedded servlet server có lợi thế nào?
A. Buộc cài Tomcat riêng trước khi chạy mọi JAR ứng dụng
B. Chạy executable JAR với servlet server nhúng
C. Không cần kết nối mạng khi controller xử lý HTTP request
D. Tự loại toàn bộ dependency servlet ở thời điểm runtime
Đáp án đúng: B

Câu 40. Với dự án Maven Spring Boot, plugin nào giúp repackage thành executable JAR?
A. maven-clean-plugin với phase clean trên artifact
B. maven-compiler-plugin với option source đã khai báo
C. Dùng spring-boot-maven-plugin cùng goal repackage
D. maven-surefire-plugin với mọi test được bỏ qua
Đáp án đúng: C

Câu 41. Khi đã có executable JAR Spring Boot, lệnh chạy thông thường là gì?
A. mvn test app.jar để khởi chạy server ứng dụng
B. jar cf app.jar để thực thi class SpringApplication
C. javac app.jar để nạp ApplicationContext runtime
D. java -jar app.jar trong môi trường đã có Java phù hợp
Đáp án đúng: D

Câu 42. Trong ứng dụng Spring Boot, @SpringBootTest thường dùng cho kiểm thử nào?
A. Unit test thuần của một method mà không dùng context
B. Test riêng mapping controller và bỏ toàn bộ context
C. Test chỉ kiểm tra ký tự trong file application.yml
D. Integration test dựng Spring application context
Đáp án đúng: D

Câu 43. @WebMvcTest(SomeController.class) thường phù hợp với mục tiêu nào?
A. Khởi tạo đầy đủ tất cả service và database bean
B. Kiểm tra slice Spring MVC và controller đã chọn
C. Chạy tất cả scheduled jobs để kiểm tra nghiệp vụ
D. Kiểm tra transaction JPA và mọi repository thật
Đáp án đúng: B

Câu 44. MockMvc hỗ trợ kiểm tra điều gì trong Spring MVC test?
A. Tạo HTTP connection thật tới cổng server trên mạng
B. Chạy kiểm thử repository bằng EntityManager riêng
C. Dựng embedded Kafka để cấp message cho controller
D. Giả lập MVC request mà không mở HTTP server thật
Đáp án đúng: D

Câu 45. Khi viết unit test cho service có Repository dependency, cách nào nhẹ hơn?
A. Chạy @SpringBootTest đầy đủ cho mọi nhánh logic service
B. Khởi tạo database thật cho từng assert về xử lý chuỗi
C. Chạy toàn bộ ứng dụng trên cổng ngẫu nhiên để mock bean
D. Khởi tạo service với mocked repository, không cần context
Đáp án đúng: D

Câu 46. @DataJpaTest trong Spring Boot tập trung vào loại kiểm thử nào?
A. Slice JPA để kiểm tra repository và mapping entity
B. Slice MVC để kiểm tra mapping từ URL đến controller
C. Slice HTTP client để kiểm tra response của provider
D. Slice web security để kiểm tra filter của request
Đáp án đúng: A

Câu 47. Khi cần kích hoạt profile test riêng trong Spring integration test, nên dùng gì?
A. @Profile("test") trên từng method assert của JUnit
B. @Qualifier("test") trên lớp @SpringBootApplication
C. @ActiveProfiles("test") trên lớp kiểm thử Spring
D. @Primary trên file application-test.yml của dự án
Đáp án đúng: C

Câu 48. Trong HTTP integration test chạy ứng dụng qua cổng ngẫu nhiên, cấu hình nào phù hợp?
A. @SpringBootTest(webEnvironment=RANDOM_PORT) để khởi động server
B. @WebMvcTest với server.port cố định từ application.yml
C. @DataJpaTest để tự mở endpoint MVC ở cổng ngẫu nhiên
D. @SpringBootTest(webEnvironment=MOCK) để mở cổng thật
Đáp án đúng: A
