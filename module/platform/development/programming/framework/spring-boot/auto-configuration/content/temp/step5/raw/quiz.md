Câu 1. Điều gì khiến Spring Boot chọn áp dụng auto-configuration cho ứng dụng?
A. Chỉ dựa vào tên package chứa Application chính
B. Chỉ dựa vào số bean đang được Spring tạo ra
C. Đánh giá condition theo classpath, bean và property hiện có
D. Dựa vào mọi dependency mà không kiểm tra condition
Đáp án đúng: C

Câu 2. @SpringBootApplication bao gồm cơ chế nào liên quan đến tự cấu hình?
A. Thay thế @Configuration bằng tất cả bean mặc định
B. Bỏ qua các condition trong mọi starter dependency
C. Vô hiệu việc khai báo @Bean trong cấu hình người dùng
D. Kích hoạt @EnableAutoConfiguration cho ứng dụng
Đáp án đúng: D

Câu 3. Khi muốn cấu hình chỉ hoạt động nếu thư viện JDBC có mặt, nên dùng gì?
A. @ConditionalOnClass với lớp đại diện thư viện JDBC
B. @ConditionalOnBean với tên DataSource chưa được tạo
C. @ConditionalOnProperty với tên package thư viện JDBC
D. @ConditionalOnResource với tên class Java cần kiểm tra
Đáp án đúng: A

Câu 4. Để auto-configuration chỉ áp dụng khi một lớp KHÔNG có trên classpath, nên dùng gì?
A. @ConditionalOnMissingBean chỉ rõ kiểu lớp chưa tạo bean
B. @ConditionalOnClass với lớp cần kiểm tra vắng mặt
C. @ConditionalOnMissingClass chỉ rõ tên lớp cần vắng mặt
D. @ConditionalOnProperty với giá trị tên lớp bị thiếu
Đáp án đúng: C

Câu 5. Tại sao bean mặc định thường được đặt dưới @ConditionalOnMissingBean?
A. Để xóa bean của ứng dụng sau khi startup hoàn tất
B. Để vô hiệu hóa việc bind property cho bean tùy chỉnh
C. Để ép Spring tạo thêm bean dù đã có cùng kiểu
D. Nhường chỗ khi ứng dụng đã có bean phù hợp về kiểu
Đáp án đúng: D

Câu 6. @ConditionalOnBean phù hợp khi nào trong auto-configuration?
A. Khi bean cần tạo chỉ phụ thuộc class có trên classpath
B. Khi bean cần tạo phụ thuộc key đã khai trong YAML
C. Khi bean cần tạo chỉ được kích hoạt ngoài web app
D. Khi bean cần tạo phụ thuộc sự tồn tại của bean khác
Đáp án đúng: D

Câu 7. Khi cần một bean duy nhất đủ điều kiện autowire, annotation nào phù hợp?
A. @ConditionalOnMissingBean theo tên mọi bean cùng kiểu
B. @ConditionalOnSingleCandidate theo kiểu bean được chọn
C. @ConditionalOnClass theo class của bean ưu tiên
D. @ConditionalOnProperty theo tên bean được đánh dấu
Đáp án đúng: B

Câu 8. @ConditionalOnProperty(prefix="app.cache", name="enabled", havingValue="true") kiểm tra gì?
A. Property app.cache.enabled không tồn tại trong Environment
B. Property app.cache.enabled có giá trị là true
C. Property enabled có bean cùng tên trong Spring context
D. Property app.cache có class tên enabled trên classpath
Đáp án đúng: B

Câu 9. Khi matchIfMissing=true trong @ConditionalOnProperty, điều gì thay đổi?
A. Điều kiện có thể khớp khi property được chỉ định vắng mặt
B. Điều kiện bỏ qua havingValue dù property có giá trị khác
C. Điều kiện bắt buộc property tồn tại ở file application.yml
D. Điều kiện chỉ khớp khi property đến từ biến môi trường
Đáp án đúng: A

Câu 10. Mặc định, @ConditionalOnProperty có havingValue chưa chỉ định thường khớp khi nào?
A. Property vắng mặt và được mặc định là true
B. Property hiện diện với giá trị khác false trong Environment
C. Property có mặt và giá trị bắt buộc là true
D. Property có mặt và giá trị bắt buộc rỗng
Đáp án đúng: B

Câu 11. Trong @ConditionalOnProperty, prefix giúp thực hiện việc gì?
A. Lấy tên Java package dùng tìm kiếm bean cho condition
B. Quy định thứ tự ưu tiên của các PropertySource
C. Gắn prefix vào tên bean do @Bean tạo ra
D. Ghép prefix với name thành tên property cần kiểm tra
Đáp án đúng: D

Câu 12. Khi cần điều kiện dựa trên sự tồn tại của file trên classpath, nên dùng gì?
A. @ConditionalOnClass với tên file được biên dịch
B. @ConditionalOnBean với nội dung resource làm tên
C. @ConditionalOnResource kiểm tra đường dẫn resource tồn tại
D. @ConditionalOnProperty với phần mở rộng của file
Đáp án đúng: C

Câu 13. @ConditionalOnWebApplication(type=SERVLET) nhằm giới hạn cấu hình cho đâu?
A. Application context thuộc loại web servlet
B. Application context thuộc loại web reactive
C. Application context thuộc loại non-web
D. Application context có WebClient nhưng non-web
Đáp án đúng: A

Câu 14. @ConditionalOnNotWebApplication thích hợp trong trường hợp nào?
A. Chỉ tạo cấu hình trong server chạy giao thức HTTP
B. Chỉ tạo cấu hình khi không có controller trong web app
C. Áp dụng cấu hình cho context không phải web application
D. Chỉ tạo cấu hình khi thiếu bean ServletWebServerFactory
Đáp án đúng: C

Câu 15. Khi muốn điều kiện phụ thuộc phiên bản runtime Java, nên dùng annotation nào?
A. @ConditionalOnClass với tên biến JAVA_HOME
B. @ConditionalOnProperty với tên JDK vendor
C. @ConditionalOnJava với phạm vi version phù hợp
D. @ConditionalOnResource với file chứa java.version
Đáp án đúng: C

Câu 16. Trong Spring Boot hiện đại, file nào liệt kê class auto-configuration tự viết?
A. META-INF/spring.factories chứa mọi @Component trong ứng dụng
B. META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
C. META-INF/services/javax.sql.DataSource chứa lớp cấu hình
D. META-INF/spring/application.yml chứa tên cấu hình Java
Đáp án đúng: B

Câu 17. Vai trò của @AutoConfiguration trên một lớp cấu hình là gì?
A. Đánh dấu lớp chỉ được kích hoạt bởi component scan
B. Đánh dấu lớp cấu hình chỉ chứa bean prototype
C. Đánh dấu lớp tham gia cơ chế auto-configuration
D. Đánh dấu lớp luôn thay thế cấu hình người dùng
Đáp án đúng: C

Câu 18. Vì sao không nên chỉ trông chờ component scan để đăng ký thư viện auto-config?
A. Component scan tự bảo đảm đọc mọi file imports
B. Component scan chỉ tìm lớp được đánh dấu @Bean
C. Cần liệt kê lớp cấu hình trong AutoConfiguration.imports
D. Auto-configuration chỉ tồn tại khi package cùng tên app
Đáp án đúng: C

Câu 19. Trong một starter tùy chỉnh, artifact starter thường đảm nhận điều gì?
A. Thực thi riêng mọi BeanFactoryPostProcessor cho ứng dụng
B. Tự cấu hình mọi bean ngay cả khi thiếu class cần thiết
C. Thay thế hoàn toàn module chứa logic auto-configuration
D. Gom các dependency cần thiết để sử dụng tính năng
Đáp án đúng: D

Câu 20. Sự khác nhau giữa starter và module auto-configuration thường là gì?
A. Starter gom dependency; auto-config khai báo bean có điều kiện
B. Starter khai báo condition; auto-config chỉ nạp library JAR
C. Starter chứa JobRepository; auto-config chỉ dùng Maven plugin
D. Starter chỉ dùng runtime; auto-config chỉ dùng khi compile
Đáp án đúng: A

Câu 21. Khi tạo bean cấu hình từ property có prefix rõ ràng, class nào phù hợp?
A. Class @ConfigurationProperties có các field cần bind
B. Class @Value chỉ khai báo một bean không có field
C. Class @PropertySource được dùng như DTO dữ liệu
D. Class @ImportResource dùng để lưu property đã bind
Đáp án đúng: A

Câu 22. Trong auto-configuration, cách bật bind class @ConfigurationProperties thích hợp là gì?
A. Dùng @ConditionalOnClass cho kiểu DTO cần bind
B. Dùng @AutoConfiguration(before=...) để bắt đầu bind
C. Dùng @EnableConfigurationProperties cho kiểu cấu hình
D. Dùng @ComponentScan cho package của thư viện model
Đáp án đúng: C

Câu 23. Nếu user đã cấu hình bean DataSource phù hợp, auto-config DataSource nên ra sao?
A. Lùi lại khi @ConditionalOnMissingBean không còn khớp
B. Tạo thêm bean mặc định rồi ghi đè bean do user tạo
C. Xóa định nghĩa bean người dùng trước khi vào context
D. Giữ bean mặc định và bỏ các property của người dùng
Đáp án đúng: A

Câu 24. Muốn kiểm thử riêng auto-configuration trong Spring Boot, công cụ nào phù hợp?
A. SpringApplication.run để mở full server cho mỗi assert
B. RestTemplate để thay thế BeanFactory trong test
C. TestRestTemplate để tạo lại auto-config imports
D. ApplicationContextRunner để chạy context tối giản
Đáp án đúng: D

Câu 25. ApplicationContextRunner.withPropertyValues(...) thường dùng nhằm mục đích gì?
A. Nạp các class vào classpath mà không tạo ClassLoader
B. Chạy các biến thể property để kiểm tra condition
C. Thay thế các bean đang tồn tại bằng proxy AOT
D. Buộc toàn bộ context dùng môi trường reactive web
Đáp án đúng: B

Câu 26. Trong ApplicationContextRunner, withUserConfiguration(...) dùng để kiểm tra gì?
A. Thay đổi classpath bằng danh sách dependency khác
B. Ảnh hưởng của cấu hình người dùng đến auto-config
C. Chỉ lấy thông số runtime của JVM để assert
D. Khởi tạo HTTP client để gọi actuator conditions
Đáp án đúng: B

Câu 27. Trong test auto-configuration, FilteredClassLoader giúp mô phỏng điều gì?
A. Ẩn lớp tùy chọn để thử điều kiện classpath khi thiếu
B. Thiếu PropertySource tùy chọn trong Environment
C. Thiếu request HTTP khi chưa vào servlet context
D. Thiếu BeanDefinition do bean được đánh dấu lazy
Đáp án đúng: A

Câu 28. Test nào xác thực đúng @ConditionalOnMissingBean hoạt động?
A. Bỏ user bean và assert context tạo hai bean cùng kiểu
B. Thêm user bean rồi kiểm tra bean mặc định lùi lại
C. Thêm classpath rồi assert mọi condition đều khớp
D. Thêm property rồi assert luôn có đúng hai bean
Đáp án đúng: B

Câu 29. Nếu muốn kiểm tra auto-config tạo bean khi classpath hợp lệ, nên assert gì?
A. Context bắt buộc không chứa các bean người dùng
B. Context bắt buộc mở cổng HTTP cho mọi cấu hình
C. Context có một bean dù condition property bị tắt
D. Context có bean dự kiến và khởi động không lỗi
Đáp án đúng: D

Câu 30. Khi bật cờ debug lúc khởi động Spring Boot, lợi ích liên quan auto-config là gì?
A. Hiển thị condition evaluation report để chẩn đoán
B. Buộc toàn bộ condition trở thành true trong context
C. Tự tải dependency mới khi một class bị thiếu
D. Bỏ cơ chế back-off cho mọi bean mặc định
Đáp án đúng: A

Câu 31. Endpoint Actuator nào giúp xem condition report khi đã được bật và cấp quyền?
A. Endpoint /actuator/beans chỉ hiển thị condition match
B. Endpoint /actuator/configprops chỉ hiển thị condition match
C. Endpoint /actuator/conditions của ứng dụng
D. Endpoint /actuator/health tự liệt kê cả negative match
Đáp án đúng: C

Câu 32. Trong condition report, negative match thường cho biết điều gì?
A. Bean đã khởi tạo nhưng bị hủy khi context đóng
B. Điều kiện không thỏa cùng nguyên nhân tương ứng
C. Bean bị gọi hai lần trong quá trình xử lý request
D. Một property đã được ghi đè bởi BeanFactoryPostProcessor
Đáp án đúng: B

Câu 33. Muốn loại trừ auto-configuration cụ thể ngay tại @SpringBootApplication, nên làm gì?
A. Dùng thuộc tính scanBasePackages với class cần loại
B. Dùng thuộc tính exclude với class auto-configuration
C. Dùng thuộc tính proxyBeanMethods=false trên toàn app
D. Dùng thuộc tính name với tên bean auto-config
Đáp án đúng: B

Câu 34. Khi không thể import class auto-config cần exclude ở source, phương án nào hợp lý?
A. Dùng @ConditionalOnMissingBean với tên của cả package
B. Dùng scanBasePackages để xóa class khỏi classpath
C. Dùng excludeName với tên class đầy đủ dạng String
D. Dùng @Import với bean name của lớp cần loại trừ
Đáp án đúng: C

Câu 35. Không sửa annotation code, muốn exclude auto-config bằng cấu hình thì dùng gì?
A. Property spring.autoconfigure.exclude với tên class đầy đủ
B. Property spring.main.lazy-initialization với tên Bean
C. Property spring.profiles.active với đường dẫn class JAR
D. Property management.endpoints.web.exposure.include
Đáp án đúng: A

Câu 36. Khi exclude một auto-configuration, hiệu lực chính là gì?
A. Xóa cả dependency chứa auto-configuration khỏi classpath
B. Gỡ mọi bean người dùng có cùng kiểu với default bean
C. Buộc các auto-configuration khác bỏ qua điều kiện
D. Chặn cấu hình tự động đó được áp dụng cho context
Đáp án đúng: D

Câu 37. @AutoConfiguration(after=SomeAutoConfiguration.class) chủ yếu ảnh hưởng điều gì?
A. Thứ tự thực thi mọi phương thức gọi trên bean ứng dụng
B. Thứ tự inject các tham số vào constructor của bean
C. Thứ tự startup của các thread trong TaskExecutor
D. Thứ tự xử lý các class auto-configuration với nhau
Đáp án đúng: D

Câu 38. Vì sao thứ tự auto-configuration không thay thế @DependsOn khi cần phụ thuộc init?
A. Thứ tự cấu hình bảo đảm singleton khởi tạo đúng trình tự
B. Thứ tự cấu hình không đồng nghĩa thứ tự khởi tạo bean
C. Thứ tự cấu hình chỉ hoạt động với các bean prototype
D. Thứ tự cấu hình tự thêm depends-on cho mọi bean
Đáp án đúng: B

Câu 39. Khi @ConditionalOnBean phụ thuộc bean từ một auto-config khác, cần lưu ý gì?
A. Đặt condition vào runner để chờ toàn bộ request xong
B. Đánh dấu bean phụ thuộc @Lazy để bỏ qua mọi condition
C. Bật override mặc định để condition quét classpath lại
D. Thứ tự xử lý để condition thấy bean đã định nghĩa
Đáp án đúng: D

Câu 40. Để condition về classpath không buộc tải trực tiếp class tùy chọn, nên làm gì?
A. Đặt điều kiện class ở cấu hình riêng trước khi nạp bean
B. Đặt type tham số class thiếu vào method @Bean không điều kiện
C. Tạo một bean @Primary để Spring tự bỏ qua class thiếu
D. Tắt condition classpath rồi xử lý lỗi bằng @PostConstruct
Đáp án đúng: A

Câu 41. Khi một auto-config tạo bean chỉ nếu property enabled, trường hợp enabled=false cần kiểm thử gì?
A. Context tạo bean nhưng chuyển scope thành prototype
B. Context ghi đè property thành true sau khi khởi động
C. Context không chứa bean đó và vẫn khởi động hợp lệ
D. Context tự tạo bean khác cùng tên rồi ném exception
Đáp án đúng: C

Câu 42. Khi dùng config property có tên dạng kebab-case, binding thường map sang kiểu nào?
A. Trường Java camelCase trong @ConfigurationProperties
B. Tên bean Java phải trùng nguyên chuỗi kebab-case
C. Tên class phải chứa dấu gạch ngang để Spring tìm thấy
D. Biến static không có setter trong mọi cấu hình bind
Đáp án đúng: A

Câu 43. Khi thuộc tính bắt buộc sai kiểu dữ liệu, triệu chứng khi bind có thể là gì?
A. Bean được khởi tạo với kiểu đúng do JVM tự chuyển
B. Classpath sẽ tự được thêm converter ở runtime
C. Condition report sẽ thay thế property lỗi bằng default
D. Lỗi binding hoặc validation khiến startup thất bại
Đáp án đúng: D

Câu 44. Để tránh việc auto-configuration tự ý ghi đè hành vi app, thiết kế nào phù hợp?
A. Buộc dùng bean mặc định bằng @Primary trên từng bean
B. Xóa tất cả property bên ngoài trong lúc khởi động
C. Cung cấp điểm tùy biến và để user bean được ưu tiên
D. Cho bean thư viện cùng tên để luôn ghi đè bean user
Đáp án đúng: C

Câu 45. Trong build native image, vì sao reflection của thư viện auto-config cần xem xét?
A. Native image tự hỗ trợ mọi class reflection lúc runtime
B. AOT có thể cần runtime hints cho reflection được sử dụng
C. Reflection chỉ ảnh hưởng JVM và không cần xét native
D. Reflection bắt buộc loại mọi @ConfigurationProperties
Đáp án đúng: B

Câu 46. Khi thư viện tạo proxy hoặc dùng resource trong native image, nên làm gì?
A. Buộc dùng @Primary thay cho mọi loại proxy runtime
B. Chỉ tăng heap trong JVM là đủ để hỗ trợ native
C. Chỉ thêm property spring.autoconfigure.exclude
D. Khai báo runtime hints tương ứng để hỗ trợ AOT
Đáp án đúng: D

Câu 47. Khi thử nghiệm tương thích auto-config qua nhiều phiên bản thư viện, trọng tâm là gì?
A. Chỉ đo số bean sau khi chạy cùng một classpath
B. Kiểm tra matrix classpath, property, bean và startup
C. Chỉ chạy unit test của business service không đổi
D. Chỉ đổi tên starter mà không cập nhật dependency
Đáp án đúng: B

Câu 48. Nếu auto-config bị loại bởi condition khi startup, bước chẩn đoán đầu tiên nào tốt?
A. Đọc condition report và kiểm tra classpath, property, bean
B. Tăng số lần retry khởi động để condition tự đổi
C. Tắt toàn bộ auto-config để xóa dữ liệu trong context
D. Đổi scope tất cả bean sang prototype để bỏ điều kiện
Đáp án đúng: A
