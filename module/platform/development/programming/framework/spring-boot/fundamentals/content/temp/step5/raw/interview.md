Bạn giải thích Spring Boot giải quyết những khó khăn nào khi xây dựng ứng dụng dựa trên Spring Framework?
Bạn phân biệt vai trò của Spring Framework và Spring Boot trong một dự án Java như thế nào?
Bạn so sánh cách khởi tạo ứng dụng Spring Boot với cách cấu hình một ứng dụng Spring truyền thống ra sao?
Bạn mô tả các thành phần cơ bản của một dự án Spring Boot vừa được tạo từ Spring Initializr như thế nào?
Bạn đánh giá khi nào nên chọn Spring Boot thay vì một chương trình Java độc lập không dùng container ra sao?
Bạn xác định những tiêu chí để chọn phiên bản Spring Boot và JDK cho một dự án mới như thế nào?
Bạn phân biệt nhu cầu phát triển ứng dụng web và ứng dụng chạy tác vụ nền khi chọn dependency như thế nào?
Bạn giải thích mối quan hệ giữa Spring Boot, IoC container và các đối tượng nghiệp vụ trong ứng dụng ra sao?
Bạn mô tả luồng thực thi từ phương thức main đến khi ứng dụng Spring Boot sẵn sàng nhận request như thế nào?
Bạn xác định ranh giới trách nhiệm giữa cấu hình framework và logic nghiệp vụ khi tổ chức dự án như thế nào?
Bạn so sánh mô hình ứng dụng đóng gói độc lập với mô hình triển khai trên application server bên ngoài ra sao?
Bạn sẽ giải thích vì sao Spring Boot phù hợp với phát triển dịch vụ độc lập nhưng không tự giải quyết mọi vấn đề phân tán như thế nào?
Bạn phân biệt quy ước cấu hình mặc định với yêu cầu phải khai báo rõ thành phần nghiệp vụ trong Spring Boot ra sao?
Bạn sẽ trình bày các bước dựng một ứng dụng Spring Boot tối thiểu từ dependency đến chạy thử như thế nào?
Bạn xác định cách kiểm tra dự án được tạo có tương thích với hệ thống build hiện tại ra sao?
Bạn phân tích các tác động khi nâng cấp phiên bản Spring Boot đối với API, dependency và cấu hình như thế nào?
Bạn sẽ lập kế hoạch kiểm tra khả năng tương thích của thư viện bên thứ ba trước khi nâng cấp Spring Boot ra sao?
Bạn giải thích mục đích của Spring Boot starter trong việc đơn giản hóa quản lý dependency như thế nào?
Bạn phân biệt starter dependency với thư viện chứa implementation thực tế như thế nào?
Bạn mô tả thành phần thường được đưa vào ứng dụng khi chọn spring-boot-starter-web ra sao?
Bạn giải thích vai trò của spring-boot-starter-test trong quy trình xây dựng và kiểm thử như thế nào?
Bạn lựa chọn starter cho web, validation, data access và actuator dựa trên nhu cầu nào?
Bạn phân biệt dependency trực tiếp với transitive dependency khi xem cây phụ thuộc của dự án ra sao?
Bạn sẽ chẩn đoán xung đột phiên bản thư viện trong dependency tree bằng cách nào?
Bạn giải thích vai trò của dependency management khi không khai báo phiên bản riêng cho từng dependency như thế nào?
Bạn phân biệt sử dụng Spring Boot parent POM với nhập dependency BOM trong dự án Maven như thế nào?
Bạn đánh giá khi nào cần override phiên bản một thư viện đã được Spring Boot quản lý ra sao?
Bạn sẽ tổ chức dependency theo tầng nghiệp vụ để không đưa vào classpath các starter không cần thiết như thế nào?
Bạn giải thích vì sao thêm một starter có thể thay đổi hành vi khởi động dù mã ứng dụng không đổi như thế nào?
Bạn phân biệt compile classpath, runtime classpath và test classpath trong kiểm tra lỗi như thế nào?
Bạn sử dụng Maven hoặc Gradle để xem dependency graph và phát hiện thư viện bị kéo vào không mong muốn ra sao?
Bạn sẽ kiểm tra việc đóng gói thư viện cần thiết vào executable jar khi gặp ClassNotFoundException như thế nào?
Bạn đánh giá các rủi ro khi một dự án chứa đồng thời nhiều framework logging hoặc web stack như thế nào?
Bạn mô tả mô hình Inversion of Control và ý nghĩa của việc container quản lý khởi tạo đối tượng như thế nào?
Bạn giải thích Dependency Injection giúp giảm sự phụ thuộc trực tiếp giữa các lớp Java ra sao?
Bạn phân biệt khởi tạo bằng từ khóa new với nhận dependency qua Spring container như thế nào?
Bạn mô tả ApplicationContext có trách nhiệm gì trong việc đăng ký, cung cấp và quản lý bean ra sao?
Bạn phân biệt BeanFactory và ApplicationContext về các tính năng quản lý bean như thế nào?
Bạn giải thích một Spring bean khác đối tượng Java thông thường ở những đặc điểm nào?
Bạn sẽ lựa chọn các thành phần cần được container quản lý thay vì tạo đối tượng thủ công theo tiêu chí nào?
Bạn phân biệt bean definition với bean instance trong vòng đời khởi tạo ApplicationContext như thế nào?
Bạn giải thích cách container xác định bean phù hợp khi một lớp yêu cầu dependency theo interface ra sao?
Bạn mô tả điều gì xảy ra khi không có bean nào thỏa mãn một dependency bắt buộc như thế nào?
Bạn phân tích nguyên nhân lỗi khi nhiều bean cùng triển khai một interface được inject mà không chỉ định rõ ra sao?
Bạn sẽ chọn constructor injection thay cho field injection dựa trên khả năng kiểm thử và bất biến như thế nào?
Bạn phân biệt constructor injection, setter injection và field injection theo ràng buộc dependency ra sao?
Bạn thiết kế một service có các dependency bắt buộc và tùy chọn bằng phương án inject nào?
Bạn giải thích vì sao constructor injection có thể giúp phát hiện thiếu dependency sớm hơn ra sao?
Bạn sẽ dùng @Qualifier để chọn đúng implementation trong ứng dụng có nhiều bean cùng type như thế nào?
Bạn phân biệt vai trò của @Primary và @Qualifier khi giải quyết sự mơ hồ bean ra sao?
Bạn phân tích rủi ro khi một bean bị đổi tên nhưng các điểm inject vẫn phụ thuộc vào bean name như thế nào?
Bạn xác định khi nào có thể dùng ObjectProvider cho một dependency tùy chọn hoặc được tạo theo nhu cầu như thế nào?
Bạn giải thích tác động của @Lazy đến thời điểm khởi tạo bean và việc phát hiện lỗi ra sao?
Bạn phân biệt lazy initialization ở một bean với bật lazy initialization cho toàn bộ ứng dụng như thế nào?
Bạn sẽ xử lý một vòng phụ thuộc giữa hai service bằng cách thay đổi thiết kế thay vì che lỗi như thế nào?
Bạn giải thích vì sao circular dependency thường là dấu hiệu cần xem lại trách nhiệm của các service ra sao?
Bạn mô tả việc inject dependency vào một đối tượng không do Spring quản lý có thể gặp vấn đề gì?
Bạn xác định cách viết unit test cho service dùng constructor injection mà không cần khởi động Spring container ra sao?
Bạn phân biệt @Component, @Service và @Repository theo mục đích tổ chức và hành vi framework như thế nào?
Bạn giải thích vai trò của @Controller và @RestController trong phân tách tầng web với tầng nghiệp vụ ra sao?
Bạn sẽ đặt @ComponentScan trong cấu trúc package nào để tránh thiếu hoặc nạp thừa bean như thế nào?
Bạn phân tích vì sao một lớp có @Service nhưng không được tạo bean khi nằm ngoài phạm vi scan ra sao?
Bạn phân biệt @Component và @Bean khi đăng ký đối tượng vào ApplicationContext như thế nào?
Bạn xác định khi nào cần khai báo @Bean cho một lớp thư viện bên ngoài không thể sửa mã nguồn như thế nào?
Bạn giải thích @Configuration hỗ trợ tổ chức các định nghĩa bean có quan hệ với nhau như thế nào?
Bạn phân tích sự khác biệt giữa gọi trực tiếp phương thức @Bean và lấy bean thông qua container ra sao?
Bạn sẽ tránh tạo nhiều instance không mong muốn khi các phương thức cấu hình tham chiếu lẫn nhau như thế nào?
Bạn giải thích bean scope singleton có ý nghĩa gì trong phạm vi một Spring ApplicationContext như thế nào?
Bạn phân biệt singleton bean với singleton pattern tự cài đặt trong mã Java ra sao?
Bạn so sánh prototype scope với singleton scope về thời điểm tạo và trách nhiệm hủy đối tượng ra sao?
Bạn sẽ xử lý nhu cầu một singleton cần lấy instance prototype mới cho mỗi lần sử dụng như thế nào?
Bạn đánh giá khi nào nên dùng request scope hoặc session scope trong ứng dụng web Spring như thế nào?
Bạn phân tích rủi ro chia sẻ mutable state trong singleton service khi nhiều HTTP request chạy đồng thời ra sao?
Bạn xác định cách giữ dữ liệu theo request mà không đặt nó trong field của singleton bean như thế nào?
Bạn phân biệt thread safety của bean với việc bean có được Spring quản lý hay không như thế nào?
Bạn sẽ thiết kế service không giữ trạng thái chia sẻ để đơn giản hóa xử lý concurrent requests ra sao?
Bạn giải thích vì sao Spring container không tự động làm cho mọi bean trở nên thread-safe như thế nào?
Bạn mô tả auto-configuration trong Spring Boot dựa trên những thông tin nào để tạo bean mặc định như thế nào?
Bạn phân biệt auto-configuration với component scanning và Java configuration do ứng dụng viết ra sao?
Bạn giải thích vai trò của @SpringBootApplication trong việc kết hợp cấu hình, scan và auto-configuration như thế nào?
Bạn phân tích cách một starter đưa thêm class vào classpath và tác động tới cấu hình tự động ra sao?
Bạn giải thích ý nghĩa của @ConditionalOnClass khi phụ thuộc một thư viện tùy chọn như thế nào?
Bạn phân biệt @ConditionalOnBean và @ConditionalOnMissingBean khi ứng dụng cung cấp bean riêng ra sao?
Bạn mô tả cơ chế auto-configuration back-off khi một bean do người dùng định nghĩa đã tồn tại như thế nào?
Bạn sẽ quyết định khi nào nên thay thế một bean mặc định và khi nào nên giữ cấu hình tự động ra sao?
Bạn phân tích nguyên nhân DataSource được tạo hoặc không được tạo dựa trên dependency và properties như thế nào?
Bạn giải thích @ConditionalOnProperty có thể bật tắt tính năng theo cấu hình như thế nào?
Bạn sẽ dùng cấu hình exclude auto-configuration khi một starter mang tới thành phần không cần thiết ra sao?
Bạn phân biệt loại trừ một auto-configuration với override một bean đơn lẻ trong tình huống nào?
Bạn xác định cách xem condition evaluation report khi auto-configuration không hoạt động như mong đợi ra sao?
Bạn sử dụng debug startup để xác định một auto-configuration match hoặc không match điều kiện như thế nào?
Bạn phân biệt lỗi thiếu bean do không scan với lỗi bean bị điều kiện auto-configuration loại bỏ ra sao?
Bạn sẽ chẩn đoán lỗi nhiều bean cùng type khi auto-configuration và bean ứng dụng cùng xuất hiện ra sao?
Bạn phân tích vì sao thêm dependency database vào ứng dụng có thể làm thay đổi yêu cầu cấu hình tại startup như thế nào?
Bạn giải thích khái niệm Environment và PropertySource trong cơ chế cấu hình Spring Boot như thế nào?
Bạn phân biệt application.properties và application.yml về tổ chức cấu hình và khả năng bảo trì ra sao?
Bạn sẽ phân chia các cấu hình chung và cấu hình theo môi trường trong dự án Spring Boot như thế nào?
Bạn giải thích vai trò của Spring profiles khi chạy ứng dụng trên máy cá nhân, staging và production như thế nào?
Bạn lựa chọn cách kích hoạt profile từ command line, biến môi trường hoặc cấu hình deployment ra sao?
Bạn phân tích thứ tự ưu tiên giữa cấu hình trong file, biến môi trường và command-line arguments như thế nào?
Bạn sẽ chẩn đoán một property bị giá trị từ nguồn khác ghi đè mà người phát triển không nhận ra ra sao?
Bạn giải thích tác động của việc đặt sai tên hoặc sai cấp indentation trong YAML cấu hình như thế nào?
Bạn phân biệt @Value với @ConfigurationProperties khi bind một nhóm thuộc tính liên quan ra sao?
Bạn thiết kế lớp @ConfigurationProperties thể hiện cấu hình nhiều trường có ràng buộc như thế nào?
Bạn giải thích cơ chế relaxed binding giúp ánh xạ tên thuộc tính từ biến môi trường vào Java field ra sao?
Bạn sẽ áp dụng validation cho timeout, giới hạn kết nối và endpoint ở lớp cấu hình như thế nào?
Bạn xác định khi nào thiếu property phải làm ứng dụng fail-fast và khi nào nên dùng giá trị mặc định ra sao?
Bạn phân biệt property không tồn tại với property có giá trị rỗng khi xử lý cấu hình bắt buộc như thế nào?
Bạn sẽ lưu trữ database password hoặc API key bên ngoài mã nguồn và repository như thế nào?
Bạn thiết kế phương án truyền secret qua môi trường triển khai mà không lộ chúng trong log ra sao?
Bạn phân tích rủi ro dùng profile làm ranh giới bảo mật thay vì kiểm soát quyền và secret thực tế như thế nào?
Bạn giải thích cách spring.config.import được dùng để bổ sung nguồn cấu hình như thế nào?
Bạn phân biệt cấu hình cố định ở build time và cấu hình cung cấp tại runtime khi đóng gói ứng dụng ra sao?
Bạn sẽ xác định nguồn gốc một cấu hình đang được sử dụng khi hai profile cùng được kích hoạt ra sao?
Bạn phân tích trường hợp cấu hình của một profile ngoài ý muốn làm thay đổi kết nối database như thế nào?
Bạn lựa chọn cách kiểm soát thay đổi cấu hình giữa các môi trường để tránh drift như thế nào?
Bạn mô tả cách truyền cấu hình vào container triển khai mà vẫn dùng cùng một artifact như thế nào?
Bạn giải thích cách SpringApplication.run khởi tạo và trả về ApplicationContext như thế nào?
Bạn mô tả vai trò của ApplicationRunner và CommandLineRunner sau khi ứng dụng khởi tạo như thế nào?
Bạn phân biệt tham số dòng lệnh được xử lý qua ApplicationArguments với dữ liệu cấu hình Environment ra sao?
Bạn sẽ chọn ApplicationRunner hay CommandLineRunner khi cần tác vụ kiểm tra dữ liệu lúc startup ra sao?
Bạn phân tích nguy cơ đặt công việc chạy lâu trong runner làm chậm thời điểm ứng dụng sẵn sàng như thế nào?
Bạn giải thích các giai đoạn chuẩn bị Environment, đăng ký bean và refresh ApplicationContext như thế nào?
Bạn phân biệt ApplicationStartedEvent và ApplicationReadyEvent về thời điểm quan sát vòng đời như thế nào?
Bạn sẽ xác định ứng dụng đã thực sự sẵn sàng phục vụ traffic bằng tín hiệu nào?
Bạn giải thích vai trò của @PostConstruct trong việc khởi tạo trạng thái của bean như thế nào?
Bạn phân biệt @PostConstruct, InitializingBean và phương thức initMethod khi khởi tạo bean ra sao?
Bạn phân tích rủi ro gọi hệ thống bên ngoài hoặc chạy truy vấn nặng trong callback khởi tạo bean như thế nào?
Bạn giải thích cách @PreDestroy hoặc destroyMethod được gọi khi ApplicationContext đóng bình thường như thế nào?
Bạn mô tả vai trò của SmartLifecycle khi một thành phần cần start và stop theo thứ tự ra sao?
Bạn sẽ tổ chức việc đóng kết nối và giải phóng tài nguyên khi ứng dụng nhận tín hiệu dừng như thế nào?
Bạn phân biệt graceful shutdown với việc tiến trình bị kill đột ngột về cơ hội dọn dẹp tài nguyên ra sao?
Bạn sẽ cấu hình graceful shutdown cho web server và xác định timeout phù hợp như thế nào?
Bạn phân tích điều gì xảy ra với request đang xử lý khi ứng dụng chuẩn bị shutdown như thế nào?
Bạn xác định cách xử lý một background task còn chạy lúc ApplicationContext bắt đầu đóng ra sao?
Bạn sẽ thiết kế một bean có tài nguyên riêng mà không làm rò rỉ thread hoặc connection khi ứng dụng dừng ra sao?
Bạn giải thích thứ tự khởi tạo và hủy các bean phụ thuộc có ảnh hưởng thế nào tới tính an toàn của ứng dụng?
Bạn sẽ chẩn đoán vì sao một bean được tạo thành công nhưng phương thức khởi tạo làm startup thất bại ra sao?
Bạn phân biệt quy trình dừng ứng dụng trong IDE với quy trình dừng có kiểm soát trên server như thế nào?
Bạn mô tả cách khởi chạy Spring Boot từ IDE, Maven hoặc Gradle khác nhau ở những điểm nào?
Bạn phân biệt chạy trực tiếp từ mã nguồn và chạy executable jar bằng java -jar ra sao?
Bạn sẽ kiểm tra application port và context path khi ứng dụng web không truy cập được như thế nào?
Bạn phân tích nguyên nhân lỗi port already in use và các lựa chọn xử lý phù hợp ra sao?
Bạn giải thích vai trò của embedded web server trong một ứng dụng Spring Boot như thế nào?
Bạn so sánh triển khai web server nhúng với đóng gói WAR cho môi trường servlet container bên ngoài ra sao?
Bạn mô tả mục đích của spring-boot-maven-plugin hoặc Spring Boot Gradle plugin trong quy trình build ra sao?
Bạn giải thích cách repackage tạo executable jar từ artifact Java thông thường như thế nào?
Bạn phân biệt executable jar của Spring Boot với một jar thư viện không chứa cơ chế launch ứng dụng ra sao?
Bạn sẽ chẩn đoán lỗi NoClassDefFoundError khi chỉ xảy ra sau khi đóng gói artifact như thế nào?
Bạn xác định cách kiểm tra file cấu hình bên ngoài được nạp khi chạy cùng executable jar ra sao?
Bạn thiết kế quy trình build một lần và chạy trên nhiều môi trường bằng cách truyền cấu hình lúc triển khai như thế nào?
Bạn giải thích ý nghĩa của lớp ứng dụng chính và cấu trúc package đối với component scan sau khi đóng gói ra sao?
Bạn sẽ so sánh việc chạy ứng dụng từ container image với chạy jar trên máy chủ về cấu hình và vận hành ra sao?
Bạn đánh giá sự khác biệt giữa lệnh chạy local và entrypoint trong container khi xử lý JVM options như thế nào?
Bạn xác định cách truyền heap limit và các biến cấu hình cho ứng dụng trong container như thế nào?
Bạn mô tả các bước kiểm tra artifact và phiên bản Java phù hợp trước khi deploy như thế nào?
Bạn sẽ quản lý các dependency và tài nguyên build để artifact có thể được tạo lại nhất quán ra sao?
Bạn giải thích vai trò của logging facade như SLF4J trong cách ứng dụng ghi log ra sao?
Bạn phân biệt SLF4J API với logging implementation như Logback trong ứng dụng Spring Boot như thế nào?
Bạn xác định cách đặt log level phù hợp cho root logger và các package ứng dụng như thế nào?
Bạn giải thích sự khác biệt giữa TRACE, DEBUG, INFO, WARN và ERROR trong bối cảnh vận hành ra sao?
Bạn sẽ thiết kế log ở controller, service và repository để tránh ghi trùng cùng một sự kiện như thế nào?
Bạn phân tích vì sao không nên ghi password, token hoặc dữ liệu cá nhân nguyên văn vào log như thế nào?
Bạn sử dụng placeholder trong câu lệnh logging để tránh xây dựng chuỗi không cần thiết như thế nào?
Bạn phân biệt log có cấu trúc với log văn bản tự do khi xây dựng khả năng tìm kiếm sự cố ra sao?
Bạn sẽ gắn request ID hoặc correlation ID vào log để lần theo một yêu cầu qua nhiều tầng như thế nào?
Bạn đánh giá cách sử dụng MDC trong ứng dụng có xử lý bất đồng bộ và nhiều thread như thế nào?
Bạn giải thích vì sao tăng log level lên DEBUG trong production có thể gây áp lực I/O và lộ thông tin như thế nào?
Bạn xác định cách cấu hình log theo profile mà không thay đổi mã nguồn ra sao?
Bạn sẽ phân biệt lỗi được trả về cho client với thông tin stack trace chỉ nên ghi trong log như thế nào?
Bạn thiết kế cơ chế xử lý exception tập trung để log lỗi và trả response nhất quán như thế nào?
Bạn phân tích cách tránh việc nhiều tầng cùng log một exception làm nhiễu quá trình điều tra như thế nào?
Bạn giải thích Spring Boot Actuator hỗ trợ giám sát những khía cạnh nào của ứng dụng như thế nào?
Bạn phân biệt health endpoint, info endpoint và metrics endpoint về mục tiêu sử dụng ra sao?
Bạn sẽ lựa chọn những actuator endpoints cần bật trong development và production theo tiêu chí nào?
Bạn phân tích rủi ro bảo mật khi công khai toàn bộ actuator endpoints qua Internet như thế nào?
Bạn giải thích readiness probe khác liveness probe trong quản lý vòng đời một instance như thế nào?
Bạn sẽ thiết kế health indicator cho dependency ngoài mà không khiến ứng dụng bị restart không cần thiết ra sao?
Bạn phân tích vì sao liveness không nên phụ thuộc vào một dịch vụ hạ nguồn tạm thời lỗi như thế nào?
Bạn mô tả vai trò của Micrometer trong việc thu thập các chỉ số từ ứng dụng Spring Boot như thế nào?
Bạn xác định các metric cơ bản như request latency, error rate, JVM heap và thread count được dùng ra sao?
Bạn sẽ phân biệt một ứng dụng còn sống với một ứng dụng có thể đáp ứng request trong SLA như thế nào?
Bạn thiết kế dashboard và cảnh báo dựa trên tỷ lệ lỗi cùng độ trễ thay vì chỉ kiểm tra HTTP 200 như thế nào?
Bạn phân biệt metrics, logs và traces khi điều tra một yêu cầu chậm như thế nào?
Bạn lựa chọn cách đặt tag cho metric để không tạo cardinality quá cao ra sao?
Bạn đánh giá ảnh hưởng của việc bật quá nhiều phép đo quan sát đến hiệu năng ứng dụng như thế nào?
Bạn sẽ dùng startup metrics hoặc thời gian khởi tạo bean để tìm nguyên nhân ứng dụng khởi động chậm ra sao?
Bạn phân biệt unit test với integration test trong một dự án Spring Boot như thế nào?
Bạn mô tả vai trò của @SpringBootTest khi cần kiểm tra tích hợp toàn bộ ApplicationContext ra sao?
Bạn sẽ chọn kiểm thử thuần Java thay vì @SpringBootTest cho một service đơn giản trong tình huống nào?
Bạn phân tích vì sao khởi động toàn bộ Spring context trong mọi unit test làm bộ test chậm như thế nào?
Bạn giải thích lợi ích của test slices khi chỉ cần kiểm tra tầng web hoặc tầng persistence như thế nào?
Bạn sẽ dùng @WebMvcTest và MockMvc để kiểm thử controller mà không khởi động web server thật ra sao?
Bạn phân biệt kiểm thử qua MockMvc với gọi HTTP thật tới một ứng dụng chạy trên random port như thế nào?
Bạn lựa chọn @DataJpaTest khi cần xác minh repository và ánh xạ dữ liệu ra sao?
Bạn sẽ sử dụng mock hoặc fake dependency khi kiểm thử một service có kết nối mạng bên ngoài như thế nào?
Bạn xác định những tình huống cần dùng Testcontainers thay vì cơ sở dữ liệu in-memory trong integration test như thế nào?
Bạn giải thích @ActiveProfiles giúp tách cấu hình kiểm thử khỏi production như thế nào?
Bạn sẽ dùng @TestPropertySource hoặc dynamic properties để ghi đè cấu hình trong test ra sao?
Bạn phân tích nguy cơ test pass trong môi trường development nhưng fail trong CI do khác profile hoặc biến môi trường như thế nào?
Bạn mô tả cách xác minh một bean có được nạp hoặc không nạp theo điều kiện cấu hình trong test như thế nào?
Bạn kiểm tra ứng dụng thất bại có chủ đích khi thiếu một cấu hình bắt buộc bằng phương pháp nào?
Bạn sẽ viết test cho một service nhận dependency qua constructor injection như thế nào?
Bạn phân biệt kiểm thử hành vi bean với việc kiểm thử chi tiết cấu hình nội bộ của Spring Boot ra sao?
Bạn xác định cách kiểm tra request validation, exception handler và response status tại tầng web ra sao?
Bạn sẽ thiết kế dữ liệu test độc lập để không phụ thuộc thứ tự chạy giữa các test ra sao?
Bạn phân tích vì sao chia sẻ ApplicationContext có thể tăng tốc test nhưng cũng gây rò rỉ trạng thái giữa test như thế nào?
Bạn mô tả cách kiểm tra một thay đổi dependency không làm xuất hiện bean auto-configured ngoài ý muốn ra sao?
Bạn xây dựng bộ kiểm tra build, test và chạy thử artifact trước khi đưa ứng dụng lên production như thế nào?
Bạn xác định tiêu chí nghiệm thu cho startup, shutdown, health, logging và cấu hình môi trường như thế nào?
Nếu @Service không được inject vì Spring không tìm thấy bean, bạn sẽ kiểm tra package scan và dependency như thế nào?
Nếu hai implementation cùng một interface gây lỗi NoUniqueBeanDefinitionException, bạn sẽ xử lý bằng thiết kế nào?
Nếu ứng dụng chạy được trong IDE nhưng lỗi thiếu thư viện khi chạy java -jar, bạn sẽ kiểm tra quá trình đóng gói như thế nào?
Nếu production dùng sai database dù application.yml đã có cấu hình đúng, bạn sẽ truy tìm property source ưu tiên như thế nào?
Nếu thêm một starter khiến Spring Boot tự động tạo DataSource ngoài ý muốn, bạn sẽ xác định và tắt cấu hình ra sao?
Nếu một @ConfigurationProperties không bind được biến môi trường, bạn sẽ kiểm tra cách đặt tên và validation thế nào?
Nếu startup chậm vì một bean gọi API bên ngoài trong @PostConstruct, bạn sẽ cải thiện vòng đời khởi tạo như thế nào?
Nếu ứng dụng báo healthy nhưng nhiều request timeout, bạn sẽ kết hợp metrics, logs và traces để tìm nguyên nhân ra sao?
Nếu một singleton service giữ dữ liệu của request trước trong field, bạn sẽ thay đổi thiết kế để an toàn đồng thời như thế nào?
Nếu actuator endpoints bị truy cập từ bên ngoài, bạn sẽ giới hạn exposure và quyền truy cập bằng cách nào?
Nếu integration test chỉ lỗi ở CI nhưng chạy tốt trên máy cá nhân, bạn sẽ phân tích profile, thời gian và dependency ra sao?
Nếu một instance bị dừng lúc đang phục vụ request, bạn sẽ thiết kế graceful shutdown và kiểm tra hành vi như thế nào?
Nếu cần triển khai cùng artifact lên development, staging và production, bạn sẽ quản lý config, secret và profile ra sao?
Nếu phải xây dựng dự án Spring Boot từ đầu để đưa lên production, bạn sẽ tổ chức starter, bean, DI, cấu hình, đóng gói, logging, quan sát và kiểm thử như thế nào?
