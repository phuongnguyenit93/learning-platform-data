Bạn giải thích Spring Core Container chịu trách nhiệm gì trong việc tạo, cấu hình và liên kết các đối tượng của ứng dụng?
Bạn phân biệt Inversion of Control trong Spring với việc tự khởi tạo dependency bằng từ khóa new như thế nào?
Bạn mô tả Dependency Injection làm thay đổi trách nhiệm xây dựng object graph của một service ra sao?
Bạn sẽ xác định ranh giới giữa domain object và Spring-managed bean theo tiêu chí nào?
Bạn phân tích lợi ích của việc phụ thuộc interface thay vì implementation cụ thể khi cấu hình bean trong Spring như thế nào?
Bạn sẽ thiết kế một service có nhiều dependency mà vẫn dễ kiểm thử độc lập với ApplicationContext ra sao?
Bạn phân biệt việc container quản lý lifecycle với việc container trực tiếp thực hiện logic nghiệp vụ như thế nào?
Bạn giải thích vì sao Spring bean không nhất thiết phải là singleton và điều đó ảnh hưởng thiết kế ra sao?
Bạn mô tả sự khác nhau giữa bean definition và bean instance trong Spring IoC container như thế nào?
Bạn sẽ xác định khi nào cần đăng ký một object thành bean thay vì giữ nó là object cục bộ trong method ra sao?
Bạn phân tích hậu quả của việc một service tự lấy dependency từ static singleton thay vì nhận qua DI như thế nào?
Bạn sẽ giải thích cách constructor injection làm các dependency bắt buộc hiển lộ trong thiết kế lớp ra sao?
Bạn phân biệt dependency bắt buộc và dependency tùy chọn khi xây dựng object graph như thế nào?
Bạn sẽ kiểm tra sự phụ thuộc vào Spring Framework đã lan từ lớp infrastructure sang domain layer như thế nào?
Bạn đánh giá nguy cơ một bean giữ quá nhiều trách nhiệm vì được inject vào nhiều module không liên quan ra sao?
Bạn sẽ xác định module boundaries cho bean configuration khi ứng dụng có nhiều bounded context như thế nào?
Bạn phân tích vì sao việc ứng dụng khởi động thành công chưa bảo đảm mọi dependency được kết nối đúng về nghiệp vụ ra sao?
Bạn sẽ lựa chọn chiến lược lắp ráp dependency để thay thế implementation theo môi trường mà không sửa service như thế nào?
Bạn giải thích vì sao một Spring bean có thể được tạo bởi factory method thay vì constructor trực tiếp như thế nào?
Bạn sẽ mô tả những dấu hiệu object graph có vòng phụ thuộc hoặc thiết kế thiếu ranh giới như thế nào?
Bạn giải thích BeanFactory cung cấp khả năng cốt lõi gì cho việc quản lý bean trong Spring?
Bạn phân biệt BeanFactory và ApplicationContext về dịch vụ container và thời điểm khởi tạo bean như thế nào?
Bạn mô tả DefaultListableBeanFactory có vai trò gì trong đăng ký và phân giải bean definitions như thế nào?
Bạn phân tích ảnh hưởng của việc BeanFactory khởi tạo bean theo nhu cầu so với ApplicationContext thường pre-instantiate singleton ra sao?
Bạn sẽ chọn ApplicationContext thay vì dùng BeanFactory trực tiếp cho ứng dụng thông thường vì những nhu cầu nào?
Bạn giải thích GenericApplicationContext hỗ trợ xây dựng hoặc đăng ký cấu hình bean bằng cách nào?
Bạn sẽ xác định khi nào AnnotationConfigApplicationContext phù hợp để khởi động một context độc lập ra sao?
Bạn phân biệt ClassPathXmlApplicationContext với AnnotationConfigApplicationContext theo nguồn bean definitions như thế nào?
Bạn mô tả vai trò của ConfigurableApplicationContext khi cần refresh hoặc close container ra sao?
Bạn sẽ phân biệt BeanFactory.getBean với dependency injection vào constructor về coupling và khả năng kiểm thử như thế nào?
Bạn phân tích nguy cơ gọi getBean trong logic nghiệp vụ làm xuất hiện Service Locator pattern như thế nào?
Bạn sẽ xác định cách dùng ApplicationContext.getBeansOfType để chẩn đoán các implementation thực tế được đăng ký ra sao?
Bạn phân biệt tên bean, alias và type khi tra cứu một bean trong context như thế nào?
Bạn sẽ kiểm tra một bean bị đăng ký hai tên nhưng lại chỉ có một instance trong container như thế nào?
Bạn phân tích cách child ApplicationContext nhìn thấy beans từ parent nhưng parent không nhìn thấy child beans như thế nào?
Bạn sẽ thiết kế parent-child context khi cần chia sẻ infrastructure beans nhưng cô lập các bean ứng dụng ra sao?
Bạn phân biệt override tên bean trong child context với lựa chọn bean theo type trong context hierarchy như thế nào?
Bạn sẽ điều tra một service inject nhầm bean từ parent context trong khi child context có cấu hình khác như thế nào?
Bạn giải thích vì sao Spring bean scopes phụ thuộc vào BeanFactory quản lý chúng như thế nào?
Bạn sẽ xác định lúc nào bean được tạo khi có eager singleton, lazy singleton và prototype như thế nào?
Bạn phân tích tác động của bean creation exception lên quá trình refresh ApplicationContext như thế nào?
Bạn sẽ kiểm tra các bean đã được tạo thành công trước khi ApplicationContext.refresh gặp lỗi ra sao?
Bạn phân biệt sự kiện context refreshed với việc mọi tác vụ bất đồng bộ của ứng dụng đã sẵn sàng như thế nào?
Bạn mô tả cách ApplicationContext.close kích hoạt quy trình giải phóng các singleton beans ra sao?
Bạn sẽ đánh giá rủi ro giữ tham chiếu đến bean từ một ApplicationContext đã bị đóng như thế nào?
Bạn phân biệt context refresh trong ứng dụng độc lập với việc thay đổi giá trị property tại runtime như thế nào?
Bạn sẽ xác định điểm nào trong vòng đời context phù hợp để bắt đầu xử lý dữ liệu cần tất cả bean sẵn sàng ra sao?
Bạn mô tả cách Spring xử lý bean definitions từ nhiều nguồn cấu hình thành một object graph như thế nào?
Bạn giải thích vai trò của @Configuration khi gom các phương thức tạo bean trong Spring như thế nào?
Bạn phân biệt một @Configuration class với một @Component class có @Bean methods về khả năng proxy hóa lời gọi giữa bean methods ra sao?
Bạn mô tả @Bean method được Spring dùng để tạo bean instance và gắn lifecycle như thế nào?
Bạn sẽ thiết kế @Bean factory method nhận dependency qua tham số thay vì gọi ApplicationContext.getBean ra sao?
Bạn giải thích @Bean name và aliases ảnh hưởng thế nào đến việc phân giải dependency như thế nào?
Bạn sẽ quyết định khi nào dùng @Bean thay vì @Component cho thư viện bên thứ ba không thể sửa source ra sao?
Bạn phân tích rủi ro gọi trực tiếp @Bean method trong một lite configuration class và vô tình tạo object không do container quản lý như thế nào?
Bạn sẽ giải thích tác dụng của proxyBeanMethods trên @Configuration khi một @Bean method gọi @Bean method khác như thế nào?
Bạn phân biệt inter-bean method calls của full @Configuration với cách inject tham số vào @Bean method như thế nào?
Bạn đánh giá khi nào đặt proxyBeanMethods=false có thể giảm chi phí cấu hình mà không đổi ngữ nghĩa như thế nào?
Bạn sẽ kiểm tra hai đường gọi một @Bean method có trả cùng managed singleton instance theo cấu hình thực tế ra sao?
Bạn phân tích rủi ro dùng @Bean method có side effects không idempotent khi container cần tạo lại bean ra sao?
Bạn xác định cách áp dụng @DependsOn khi thứ tự khởi tạo thật sự phụ thuộc vào tài nguyên bên ngoài như thế nào?
Bạn phân biệt @DependsOn với constructor injection trong việc biểu diễn dependency thực sự như thế nào?
Bạn sẽ thiết kế cấu hình bean phân tách rõ data source, repository và service trong một module ra sao?
Bạn giải thích vai trò của @Import khi chia nhỏ Java configuration thành nhiều cấu hình có thể tái sử dụng như thế nào?
Bạn phân biệt @Import một configuration class với quét class bằng @ComponentScan về phạm vi đăng ký như thế nào?
Bạn sẽ chọn @ImportSelector khi cần chọn bean configurations dựa trên thông tin cấu hình theo cách nào?
Bạn phân tích khi nào ImportBeanDefinitionRegistrar hữu ích cho việc đăng ký bean definitions động như thế nào?
Bạn sẽ kiểm soát các bean được tạo qua ImportBeanDefinitionRegistrar để tránh đè tên ngoài ý muốn ra sao?
Bạn giải thích @Profile tác động thế nào tới việc đăng ký một bean trong các môi trường khác nhau như thế nào?
Bạn sẽ phân biệt @Profile trên @Configuration class và trên @Bean method theo phạm vi áp dụng ra sao?
Bạn thiết kế triển khai interface StorageClient bằng các beans khác nhau cho dev và production như thế nào?
Bạn phân tích rủi ro không có bean nào được đăng ký khi active profiles không khớp cấu hình ra sao?
Bạn sẽ xác định phương án kiểm thử những tổ hợp active profiles mà hệ thống thật có thể dùng ra sao?
Bạn phân biệt @Conditional với @Profile về cơ chế điều kiện đăng ký bean như thế nào?
Bạn sẽ xây dựng một custom Condition kiểm tra Environment trước khi đăng ký bean theo nguyên tắc nào?
Bạn giải thích vì sao @Conditional được đánh giá trong giai đoạn xử lý bean definitions chứ không phải sau mỗi lời gọi method như thế nào?
Bạn sẽ điều tra việc một @Bean không xuất hiện trong context do điều kiện @Conditional bị đánh giá false ra sao?
Bạn phân tích tác động của bean definitions trùng tên khi nhiều @Configuration modules được import vào cùng context như thế nào?
Bạn sẽ đặt quy ước tên và namespace configuration để tránh override ngoài ý muốn khi module mở rộng ra sao?
Bạn mô tả @ComponentScan phát hiện các stereotype-annotated classes để đăng ký bean definitions như thế nào?
Bạn phân biệt @Component, @Service, @Repository và @Controller về vai trò stereotype trong Spring như thế nào?
Bạn sẽ xác định basePackages cho @ComponentScan để không quét nhầm toàn bộ thư viện và modules phụ trợ ra sao?
Bạn phân tích rủi ro quét quá rộng khiến các bean chỉ dành cho test được tạo trên production như thế nào?
Bạn sẽ giới hạn component scan bằng includeFilters và excludeFilters trong trường hợp nào?
Bạn giải thích cách một custom annotation meta-annotated với @Component có thể trở thành Spring stereotype như thế nào?
Bạn sẽ thiết kế stereotype annotation nội bộ có tên rõ ràng mà vẫn được component scan phát hiện như thế nào?
Bạn phân biệt bean name mặc định do BeanNameGenerator tạo với tên khai báo rõ trong @Component như thế nào?
Bạn sẽ xác định nguyên nhân hai class trùng simple name dẫn đến bean name collision khi component scan ra sao?
Bạn phân tích vì sao một class nằm ngoài component scan không tự thành bean dù có @Service ra sao?
Bạn sẽ kiểm tra package root của class @Configuration quyết định vùng scan mặc định như thế nào?
Bạn phân biệt scan classpath để tìm bean definitions với khởi tạo bean instances ở bước sau như thế nào?
Bạn sẽ lựa chọn cấu hình explicit @Bean cho một component cần kiểm soát constructor arguments thay vì component scan ra sao?
Bạn đánh giá ảnh hưởng của component scan tới startup time khi classpath chứa hàng nghìn classes như thế nào?
Bạn sẽ xác định phương pháp giảm component scanning ngoài ý muốn khi xây dựng thư viện Spring dùng chung ra sao?
Bạn phân tích rủi ro một class được đăng ký qua @ComponentScan đồng thời được tạo qua @Bean method khác tên như thế nào?
Bạn sẽ kiểm tra xem hai bean cùng class có phải cùng instance hay hai object độc lập khi chúng được đăng ký khác cách như thế nào?
Bạn giải thích cơ chế autowiring theo type của Spring khi một constructor có nhiều dependency như thế nào?
Bạn phân biệt constructor injection, setter injection và field injection trong thiết kế Spring-managed beans như thế nào?
Bạn sẽ chọn constructor injection để bảo đảm tính bất biến và khả năng unit test theo cách nào?
Bạn phân tích rủi ro field injection che giấu dependencies và làm khó tạo object trực tiếp trong unit test như thế nào?
Bạn giải thích vì sao một constructor duy nhất thường được Spring dùng để injection mà không cần ghi @Autowired như thế nào?
Bạn sẽ xử lý class có nhiều constructors để Spring chọn đúng constructor theo cấu hình nào?
Bạn phân biệt @Autowired(required=false) với Optional trong biểu diễn một dependency tùy chọn như thế nào?
Bạn sẽ sử dụng ObjectProvider để trì hoãn việc lấy dependency cho đến thời điểm cần dùng ra sao?
Bạn phân biệt ObjectProvider.getObject, getIfAvailable và getIfUnique về phản ứng khi thiếu hoặc thừa bean như thế nào?
Bạn phân tích rủi ro dùng ObjectProvider để che giấu một kiến trúc phụ thuộc vòng thay vì sửa thiết kế như thế nào?
Bạn sẽ lựa chọn @Lazy trên dependency injection point khi bean đích khởi tạo tốn tài nguyên như thế nào?
Bạn phân biệt @Lazy trên bean definition với @Lazy trên injection point theo thời điểm tạo object ra sao?
Bạn sẽ xác định sự khác nhau giữa provider abstraction và trực tiếp inject singleton reference trong một service như thế nào?
Bạn giải thích vì sao Spring ném NoSuchBeanDefinitionException khi một dependency bắt buộc không được đăng ký ra sao?
Bạn sẽ điều tra NoUniqueBeanDefinitionException khi hai implementations cùng thỏa type injection như thế nào?
Bạn phân biệt @Primary và @Qualifier trong việc lựa chọn bean giữa nhiều candidates ra sao?
Bạn sẽ tổ chức @Qualifier để service chọn đúng implementation mà không phụ thuộc tên class cụ thể như thế nào?
Bạn giải thích vì sao bean name đôi khi được dùng như một tín hiệu phân giải dependency khi có nhiều candidates như thế nào?
Bạn sẽ phân tích sự khác biệt giữa @Qualifier trên bean producer và @Qualifier trên injection point như thế nào?
Bạn xác định khi nào cần custom qualifier annotation để tránh sử dụng chuỗi tên bean dễ sai như thế nào?
Bạn sẽ thiết kế inject Map<String, PaymentHandler> để đăng ký một tập implementation theo tên bean ra sao?
Bạn phân biệt inject List<Service> và inject từng bean riêng khi xây dựng một pipeline có nhiều handlers như thế nào?
Bạn sẽ xác định thứ tự xử lý các beans trong List bằng @Order hoặc Ordered như thế nào?
Bạn phân tích ảnh hưởng của @Priority và @Order tới việc chọn hoặc sắp xếp nhiều dependency như thế nào?
Bạn sẽ inject các implementation phân biệt bằng generic type như Repository<Customer> và Repository<Order> theo cách nào?
Bạn mô tả cách generic type thông tin có thể tham gia làm qualifier cho autowiring trong Spring như thế nào?
Bạn sẽ so sánh @Resource injection theo tên với @Autowired injection theo type trong một module có nhiều bean ra sao?
Bạn phân biệt @Inject và @Autowired về nguồn annotation và hành vi tùy chọn trong ứng dụng Spring như thế nào?
Bạn sẽ xác định khi nào dependency được truyền qua constructor @Bean method thay vì qua field của @Configuration class như thế nào?
Bạn phân tích rủi ro một optional dependency không có nhưng code vẫn giả định luôn tồn tại trong runtime ra sao?
Bạn sẽ lựa chọn cơ chế kiểm tra một tập beans phải có ít nhất một implementation trước khi app nhận traffic như thế nào?
Bạn giải thích vì sao constructor circular dependency thường dẫn đến lỗi tạo bean trong Spring như thế nào?
Bạn mô tả chu trình hai beans A và B cùng inject constructor của nhau và hậu quả khi khởi tạo như thế nào?
Bạn sẽ tái cấu trúc object graph để loại bỏ circular dependency mà không dựa vào việc bật circular references ra sao?
Bạn phân biệt circular dependency qua constructor với một số trường hợp setter/field injection có thể được container xử lý như thế nào?
Bạn sẽ đánh giá rủi ro cố bật allowCircularReferences để tránh sửa thiết kế dependency như thế nào?
Bạn phân tích khi nào @Lazy proxy làm đứt vòng tạo object nhưng chỉ che giấu vấn đề kiến trúc ra sao?
Bạn sẽ xác định một chuỗi phụ thuộc dài không có vòng nhưng vẫn khiến startup tốn nhiều thời gian như thế nào?
Bạn sẽ tìm nguyên nhân của BeanCurrentlyInCreationException khi lỗi phát sinh trong lúc khởi tạo object graph ra sao?
Bạn phân biệt circular dependency trong bean graph với vòng gọi method hợp lệ xảy ra khi chạy nghiệp vụ như thế nào?
Bạn sẽ thiết kế service và coordinator để tránh hai modules inject chéo trực tiếp lẫn nhau như thế nào?
Bạn giải thích singleton scope trong Spring được xác định theo một bean definition trong một container như thế nào?
Bạn phân biệt Spring singleton với singleton pattern toàn JVM khi có nhiều ApplicationContext như thế nào?
Bạn sẽ quyết định khi nào singleton bean nên stateless để an toàn trong ứng dụng xử lý nhiều request như thế nào?
Bạn phân tích nguy cơ giữ request data trong field mutable của singleton service như thế nào?
Bạn mô tả prototype scope khiến container tạo instance mới theo từng lần request bean như thế nào?
Bạn phân biệt prototype được inject một lần vào singleton với prototype được lấy thông qua provider ở runtime như thế nào?
Bạn sẽ lựa chọn ObjectProvider hoặc method injection để singleton sử dụng nhiều prototype instances theo thời điểm như thế nào?
Bạn giải thích @Lookup có thể hỗ trợ method injection từ singleton sang prototype thông qua container như thế nào?
Bạn phân tích giới hạn của @Lookup khi bean hoặc method không phù hợp cho runtime subclass generation ra sao?
Bạn sẽ xác định prototype lifecycle khác singleton lifecycle ở giai đoạn destroy như thế nào?
Bạn phân tích vì sao container thường không tự gọi destruction callbacks cho prototype beans sau khi client đã nhận chúng như thế nào?
Bạn sẽ thiết kế cách đóng tài nguyên thuộc prototype bean để không rò rỉ connection hoặc file handle ra sao?
Bạn mô tả request scope khác session scope theo thời hạn sống của bean trong web-aware ApplicationContext như thế nào?
Bạn phân biệt application scope trong môi trường web với singleton scope trong một Spring container như thế nào?
Bạn sẽ lựa chọn request-scoped bean cho dữ liệu ngữ cảnh request thay vì singleton mutable field trong trường hợp nào?
Bạn giải thích vì sao inject trực tiếp request-scoped bean vào singleton thường cần scoped proxy hoặc provider như thế nào?
Bạn sẽ cấu hình @Scope với ScopedProxyMode.TARGET_CLASS hoặc INTERFACES tùy loại bean như thế nào?
Bạn phân biệt scoped proxy và target bean về việc tham chiếu và xác định instance theo request như thế nào?
Bạn sẽ kiểm tra lỗi không có request context khi truy cập request-scoped bean từ thread chạy nền như thế nào?
Bạn phân tích rủi ro session-scoped bean chứa lượng dữ liệu lớn khiến memory tăng theo số phiên như thế nào?
Bạn sẽ quyết định khi nào không nên giữ dữ liệu phiên trên một instance do yêu cầu chạy nhiều replica ra sao?
Bạn giải thích cách custom Scope interface có thể quản lý bean theo vòng đời nghiệp vụ riêng như thế nào?
Bạn sẽ thiết kế một scope cho workflow ngắn hạn với quy trình cleanup và hủy bean rõ ràng như thế nào?
Bạn phân biệt scope availability với bản thân bean definition khi một scope chỉ được đăng ký trong web context ra sao?
Bạn sẽ chẩn đoán lỗi No Scope registered for scope name khi bean scope chưa được khai báo ra sao?
Bạn phân tích việc scope proxy có thể che giấu lỗi truy cập context không tồn tại tới tận runtime như thế nào?
Bạn sẽ kiểm thử hai lần lấy prototype bean tạo object khác nhau trong khi singleton bean vẫn giữ cùng một reference như thế nào?
Bạn mô tả các giai đoạn khởi tạo một singleton bean từ instantiate, populate properties đến initialize như thế nào?
Bạn giải thích mục đích của BeanPostProcessor trước và sau initialization trong vòng đời bean như thế nào?
Bạn phân biệt việc khởi tạo constructor với việc thực thi @PostConstruct khi dependency injection đã hoàn tất ra sao?
Bạn sẽ chọn constructor, @PostConstruct hay ApplicationReadyEvent cho một tác vụ khởi tạo cần các điều kiện khác nhau như thế nào?
Bạn giải thích InitializingBean.afterPropertiesSet được Spring gọi vào giai đoạn nào như thế nào?
Bạn phân biệt @PostConstruct, InitializingBean và initMethod trên @Bean về khả năng tái sử dụng và coupling như thế nào?
Bạn sẽ xác định thứ tự thực thi các initialization callbacks khi một bean khai báo nhiều cơ chế như thế nào?
Bạn phân tích rủi ro @PostConstruct thực hiện network I/O dài khiến ApplicationContext khởi động chậm ra sao?
Bạn sẽ thiết kế khởi tạo resource idempotent để tránh thất bại khi ApplicationContext được tạo lại trong test như thế nào?
Bạn mô tả DisposableBean.destroy tham gia quy trình hủy một singleton bean như thế nào?
Bạn phân biệt @PreDestroy, DisposableBean và destroyMethod của @Bean khi giải phóng tài nguyên như thế nào?
Bạn sẽ xác định thứ tự thực thi destruction callbacks nếu một bean khai báo nhiều cơ chế cleanup ra sao?
Bạn phân tích trường hợp destruction callback không được gọi cho prototype hoặc khi JVM bị kill như thế nào?
Bạn sẽ thiết kế đóng connection pool an toàn khi ApplicationContext.close được gọi trong quá trình shutdown ra sao?
Bạn giải thích vai trò của Lifecycle và SmartLifecycle đối với các beans cần start hoặc stop có kiểm soát như thế nào?
Bạn sẽ dùng phase của SmartLifecycle để điều phối thứ tự start và stop giữa nhiều infrastructure beans ra sao?
Bạn phân biệt SmartLifecycle.isAutoStartup với một @PostConstruct method thực thi ngay khi khởi tạo như thế nào?
Bạn sẽ chẩn đoán tình huống SmartLifecycle component đã được tạo bean nhưng chưa chuyển sang trạng thái running ra sao?
Bạn phân tích nguy cơ một SmartLifecycle.stop callback không thông báo hoàn tất khiến quá trình shutdown bị kéo dài như thế nào?
Bạn sẽ xác định nơi triển khai cleanup tốt hơn giữa @PreDestroy và SmartLifecycle cho một background consumer ra sao?
Bạn giải thích vì sao việc dùng @DependsOn ảnh hưởng thứ tự tạo và hủy singleton beans như thế nào?
Bạn sẽ tổ chức tài nguyên database, message client và worker bean để chúng đóng theo thứ tự phụ thuộc hợp lý ra sao?
Bạn phân tích tác động của lazy bean tới lifecycle callbacks khi bean chưa từng được khởi tạo trước shutdown ra sao?
Bạn sẽ thiết kế kiểm thử integration bảo đảm bean khởi tạo và dọn dẹp tài nguyên đúng thứ tự như thế nào?
Bạn giải thích FactoryBean khác một bean factory method được đánh dấu @Bean như thế nào?
Bạn phân biệt FactoryBean và BeanFactory về mục đích và trách nhiệm của chúng ra sao?
Bạn mô tả cách FactoryBean.getObject tạo hoặc cung cấp product object khi được tra cứu qua Spring container như thế nào?
Bạn giải thích ý nghĩa của FactoryBean.getObjectType trong phân giải bean theo type như thế nào?
Bạn sẽ xác định hành vi FactoryBean.isSingleton ảnh hưởng caching của product object như thế nào?
Bạn phân biệt singleton scope của FactoryBean instance với tính singleton của object mà FactoryBean tạo ra như thế nào?
Bạn mô tả cách tra cứu tên bean bình thường và ký hiệu & trước tên bean để lấy FactoryBean instance như thế nào?
Bạn sẽ kiểm tra getBean với tên sản phẩm khác getBean với &name khi debug FactoryBean ra sao?
Bạn phân tích lỗi có thể xảy ra nếu getObjectType trả null khiến autowiring theo type khó xác định bean như thế nào?
Bạn sẽ thiết kế FactoryBean cho một client cần khởi tạo nhiều bước mà không làm lộ chi tiết đó sang service ra sao?
Bạn phân biệt FactoryBean tạo object từ thư viện ngoài với cấu hình @Bean trực tiếp theo tiêu chí nào?
Bạn đánh giá khi nào FactoryBean khiến hành vi tạo bean khó hiểu hơn lợi ích mà nó mang lại ra sao?
Bạn sẽ xác định lifecycle và tài nguyên của product object do FactoryBean trả về cần được quản lý như thế nào?
Bạn phân tích rủi ro FactoryBean giữ state mutable dùng chung giữa những lượt tạo product objects như thế nào?
Bạn sẽ kiểm thử một FactoryBean có tạo đúng product type và singleton behavior khi context được refresh như thế nào?
Bạn giải thích BeanFactoryPostProcessor can thiệp vào bước nào của quá trình chuẩn bị bean definitions như thế nào?
Bạn phân biệt BeanFactoryPostProcessor với BeanPostProcessor theo đối tượng và thời điểm xử lý như thế nào?
Bạn sẽ chọn BeanFactoryPostProcessor để thay đổi một property trong BeanDefinition trước khi object được tạo ra sao?
Bạn phân tích rủi ro BeanFactoryPostProcessor gọi getBean quá sớm khiến một số bean bỏ qua hậu xử lý như thế nào?
Bạn mô tả PropertySourcesPlaceholderConfigurer tham gia việc phân giải placeholder trong bean definitions như thế nào?
Bạn phân biệt placeholder resolution trong cấu hình bean với @Value được inject lúc tạo bean như thế nào?
Bạn sẽ sử dụng BeanDefinitionRegistryPostProcessor khi cần đăng ký thêm definitions trước quá trình khởi tạo ra sao?
Bạn phân biệt BeanDefinitionRegistryPostProcessor và BeanFactoryPostProcessor về khả năng thao tác registry như thế nào?
Bạn sẽ thiết kế một post-processor đăng ký nhiều strategy beans dựa trên metadata cấu hình như thế nào?
Bạn đánh giá nguy cơ BeanDefinitionRegistryPostProcessor đăng ký nhầm tên làm override bean của module khác ra sao?
Bạn mô tả BeanPostProcessor.postProcessBeforeInitialization có thể sửa hoặc trả đối tượng khác theo contract nào?
Bạn phân tích vì sao BeanPostProcessor.postProcessAfterInitialization có thể trả về proxy thay vì raw target như thế nào?
Bạn sẽ xác định khi nào dùng BeanPostProcessor thay vì sửa từng @Bean factory method ra sao?
Bạn đánh giá rủi ro BeanPostProcessor xử lý cả infrastructure beans và gây vòng tạo object như thế nào?
Bạn sẽ thiết kế BeanPostProcessor kiểm tra một marker annotation mà không thực thi side effects trên mọi bean như thế nào?
Bạn phân biệt annotation processing của AutowiredAnnotationBeanPostProcessor với việc @Autowired chỉ là metadata như thế nào?
Bạn giải thích CommonAnnotationBeanPostProcessor hỗ trợ các lifecycle annotations liên quan như thế nào?
Bạn sẽ xác định lý do một @PostConstruct không chạy khi bean không đi qua lifecycle của container như thế nào?
Bạn phân tích nguyên nhân một bean không đủ điều kiện xử lý bởi tất cả BeanPostProcessors khi được khởi tạo sớm ra sao?
Bạn sẽ dùng PriorityOrdered và Ordered để kiểm soát thứ tự post-processors khi thực sự cần như thế nào?
Bạn phân biệt thứ tự post-processor với @Order dùng để sắp xếp danh sách dependency beans như thế nào?
Bạn sẽ kiểm tra một BeanPostProcessor được đăng ký programmatically có thứ tự xử lý khác bean auto-detected ra sao?
Bạn phân tích cách SmartInstantiationAwareBeanPostProcessor ảnh hưởng constructor selection hoặc early bean references như thế nào?
Bạn sẽ xác định khi nào việc dùng điểm mở rộng cấp thấp như SmartInstantiationAwareBeanPostProcessor là không cần thiết ra sao?
Bạn phân biệt đăng ký BeanDefinition programmatically với đăng ký singleton instance đã tạo sẵn như thế nào?
Bạn sẽ thiết kế một bean registrar kiểm tra name collision trước khi đưa definitions vào container ra sao?
Bạn phân tích rủi ro gắn state runtime vào BeanDefinition metadata làm container khó tái cấu hình như thế nào?
Bạn mô tả Environment trong ApplicationContext tập hợp và phân giải PropertySource như thế nào?
Bạn phân biệt Environment.getProperty với inject @Value và bind @ConfigurationProperties về mục tiêu sử dụng như thế nào?
Bạn sẽ chọn @Value cho một cấu hình đơn giản nhưng chuyển sang @ConfigurationProperties khi có nhóm thuộc tính ra sao?
Bạn phân tích thứ tự ưu tiên của nhiều PropertySource ảnh hưởng giá trị property được inject như thế nào?
Bạn sẽ xác định một property bị override từ biến môi trường thay vì file cấu hình bằng phương pháp nào?
Bạn đánh giá rủi ro giữ secret trong source code của @Configuration hoặc default value trong annotation ra sao?
Bạn sẽ dùng @Profile và Environment để tổ chức cấu hình bean theo môi trường mà tránh nhân bản code ra sao?
Bạn phân biệt PropertySource của Spring với cơ chế resource loading qua ResourceLoader như thế nào?
Bạn giải thích ApplicationContext cung cấp MessageSource để hỗ trợ thông điệp đa ngôn ngữ như thế nào?
Bạn sẽ thiết kế bean đọc resource từ classpath mà không giả định ứng dụng luôn chạy từ thư mục source như thế nào?
Bạn phân biệt ClassPathResource và FileSystemResource khi đóng gói ứng dụng dưới dạng jar như thế nào?
Bạn sẽ sử dụng ResourceLoader để tạo abstraction đọc file cấu hình từ nhiều nguồn ra sao?
Bạn phân tích nguy cơ giữ InputStream mở khi bean đọc resource trong quá trình initialization như thế nào?
Bạn mô tả cơ chế publishEvent và ApplicationListener trong ApplicationContext giúp các beans trao đổi sự kiện như thế nào?
Bạn phân biệt ApplicationEventPublisher với gọi trực tiếp một bean dependency trong thiết kế loose coupling như thế nào?
Bạn sẽ quyết định khi nào dùng @EventListener để phản ứng một sự kiện ứng dụng thay vì inject trực tiếp collaborator ra sao?
Bạn phân tích tác động của một ApplicationListener chạy đồng bộ và ném exception trong quá trình publishEvent như thế nào?
Bạn sẽ lựa chọn ApplicationEventMulticaster phù hợp khi cần listeners chạy bất đồng bộ theo yêu cầu nào?
Bạn phân biệt ContextRefreshedEvent và ContextClosedEvent về thời điểm tài nguyên của container sẵn sàng như thế nào?
Bạn sẽ đánh giá nguy cơ event listener chạy trong lúc context chưa hoàn tất một giai đoạn lifecycle như thế nào?
Bạn sẽ thiết kế event payload tránh chứa reference mutable tới bean hoặc dữ liệu nhạy cảm như thế nào?
Bạn phân tích vì sao Spring application events trong cùng process không tự bảo đảm độ bền như một message broker như thế nào?
Bạn sẽ kiểm thử event listener được đăng ký đúng bean và nhận đúng sự kiện từ ApplicationContext như thế nào?
Bạn giải thích cách @ContextConfiguration giúp Spring TestContext tạo môi trường dependency injection cho integration test như thế nào?
Bạn phân biệt unit test tạo object trực tiếp bằng constructor với test cần ApplicationContext thật như thế nào?
Bạn sẽ sử dụng AnnotationConfigApplicationContext trong test nhỏ để kiểm tra đúng dependency graph như thế nào?
Bạn phân tích khi nào @SpringBootTest là quá nặng nếu chỉ cần kiểm tra wiring của vài Spring Core beans ra sao?
Bạn sẽ lựa chọn @ActiveProfiles để kiểm tra nhiều biến thể cấu hình bean trong test ra sao?
Bạn giải thích vì sao việc cache ApplicationContext giữa các test có thể khiến singleton mutable state rò rỉ như thế nào?
Bạn sẽ dùng @DirtiesContext khi nào và đánh giá chi phí khởi tạo lại context ra sao?
Bạn phân biệt mock dependency ở constructor injection với việc thay một bean trong integration test context như thế nào?
Bạn sẽ thiết kế cấu hình test độc lập để không đọc credential hoặc kết nối production khi tạo ApplicationContext ra sao?
Bạn phân tích cách kiểm thử NoUniqueBeanDefinitionException với hai implementations không có @Primary hoặc @Qualifier ra sao?
Bạn sẽ kiểm tra ObjectProvider trả đúng hành vi khi không có bean hoặc có nhiều beans cùng type như thế nào?
Bạn thiết kế test xác minh @Lazy bean không được khởi tạo cho tới khi thật sự được yêu cầu ra sao?
Bạn sẽ kiểm thử prototype bean được tạo mới cho mỗi lần lookup qua provider như thế nào?
Bạn phân tích cách kiểm thử request-scoped proxy trong test có request context và không có request context ra sao?
Bạn sẽ kiểm tra @PostConstruct, InitializingBean và initMethod được gọi theo thứ tự mong đợi bằng event log như thế nào?
Bạn thiết kế test bảo đảm @PreDestroy và destroyMethod chạy khi đóng ApplicationContext như thế nào?
Bạn sẽ kiểm tra thứ tự start và stop của hai SmartLifecycle beans có phase khác nhau ra sao?
Bạn sẽ viết test cho FactoryBean.getObjectType, isSingleton và cú pháp &beanName như thế nào?
Bạn phân tích cách kiểm thử BeanFactoryPostProcessor thay đổi definition trước lúc singleton được instantiate ra sao?
Bạn sẽ kiểm tra BeanPostProcessor chỉ bao phủ bean được đánh dấu marker annotation theo chủ đích như thế nào?
Bạn thiết kế test custom scope bảo đảm bean được tạo, tái sử dụng và hủy đúng vòng đời như thế nào?
Bạn sẽ xác minh @ComponentScan không đăng ký nhầm bean từ package ngoài phạm vi quy định ra sao?
Bạn đánh giá cách test parent-child ApplicationContext khi hai context có bean cùng tên nhưng khác instance như thế nào?
Bạn sẽ chẩn đoán lỗi ApplicationContext không khởi động bằng exception chain và các bean definitions liên quan ra sao?
Bạn phân biệt lỗi UnsatisfiedDependencyException với lỗi phát sinh trong constructor của một bean như thế nào?
Bạn sẽ tìm nguồn NoSuchBeanDefinitionException khi component scan có vẻ đã cấu hình đúng ra sao?
Bạn phân tích cách xác định một bean bị loại bởi @Profile hoặc @Conditional khi dependency được inject bị thiếu như thế nào?
Bạn sẽ xác định nguyên nhân một bean được tạo hai lần dù tưởng nó là singleton bằng cách kiểm tra scope và definitions ra sao?
Bạn đánh giá tác động của việc ép eager initialization trên một bean chỉ cần cho một tính năng ít được gọi như thế nào?
Bạn sẽ đo startup cost của từng bean hoặc nhóm beans trước khi thay đổi thành lazy loading ra sao?
Bạn phân tích nguyên nhân startup deadlock nếu constructor của các beans cùng chờ một tài nguyên chưa được khởi tạo như thế nào?
Bạn sẽ thiết kế runbook điều tra bean creation failure sau khi nâng cấp phiên bản Spring Framework ra sao?
Bạn phân biệt một dependency cycle thực sự với việc một post-processor vô tình gọi getBean trong giai đoạn quá sớm như thế nào?
Bạn sẽ xác định vì sao một bean có @PostConstruct không chạy khi instance được tạo thủ công thay vì từ container ra sao?
Bạn phân tích khi nào Spring container giữ reference tới một bean quá lâu khiến tài nguyên không được giải phóng như thế nào?
Bạn sẽ kiểm tra memory leak do singleton chứa cache hoặc collection tăng liên tục trong môi trường nhiều request ra sao?
Bạn sẽ thiết kế phương án migrate từ XML bean definitions sang Java configuration mà vẫn kiểm tra hành vi tương đương như thế nào?
Bạn đánh giá rủi ro thay tên bean hoặc thay qualifier khi refactor module cấu hình đã được dùng rộng rãi như thế nào?
Bạn sẽ kiểm tra bean override policy để không một thư viện vô tình thay implementation quan trọng như thế nào?
Bạn phân tích khi nào chia ApplicationContext thành nhiều module làm việc quản lý lifecycle trở nên phức tạp như thế nào?
Nếu một service báo NoUniqueBeanDefinitionException khi bổ sung implementation mới, bạn sẽ xử lý @Primary, @Qualifier và thiết kế API DI ra sao?
Nếu hai beans phụ thuộc constructor lẫn nhau và context không khởi động, bạn sẽ thiết kế lại object graph như thế nào?
Nếu một prototype được inject vào singleton nhưng luôn trả lại cùng instance, bạn sẽ kiểm tra thời điểm injection và sửa cách lấy bean như thế nào?
Nếu một request-scoped bean bị truy cập từ background thread và báo không có request context, bạn sẽ điều chỉnh ranh giới scope ra sao?
Nếu method @Bean bị gọi trực tiếp trong một lite configuration làm tạo object thứ hai, bạn sẽ chẩn đoán và sửa wiring như thế nào?
Nếu một singleton sử dụng field để lưu userId giữa các request, bạn sẽ sửa thiết kế bean và scope theo hướng nào?
Nếu ApplicationContext.refresh thất bại do database client khởi tạo lâu, bạn sẽ tách initialization và readiness như thế nào?
Nếu @Profile không khớp khiến production không có StorageClient bean, bạn sẽ đặt validation và fallback cấu hình ra sao?
Nếu BeanPostProcessor làm một bean bị khởi tạo quá sớm và mất proxy cần thiết, bạn sẽ kiểm tra thứ tự đăng ký và dependencies như thế nào?
Nếu FactoryBean trả đúng product nhưng autowiring theo type không tìm thấy, bạn sẽ kiểm tra getObjectType và lifecycle như thế nào?
Nếu một bean sử dụng @PostConstruct để thực hiện tác vụ dài khiến startup chậm, bạn sẽ đổi điểm khởi chạy sang cơ chế nào?
Nếu ứng dụng shutdown nhưng connection pool không đóng, bạn sẽ kiểm tra destruction callbacks và bean lifecycle như thế nào?
Nếu hai ApplicationContext cùng tạo singleton của một class và chia sẻ trạng thái không mong muốn qua static field, bạn sẽ cô lập state như thế nào?
Nếu một package mới bị @ComponentScan quét nhầm tạo bean trùng tên, bạn sẽ giới hạn scanning và xác minh definitions ra sao?
Nếu @Autowired không chọn đúng implementation dù có qualifier, bạn sẽ điều tra bean names, metadata và generic types như thế nào?
Nếu listener xử lý ApplicationEvent ném exception làm yêu cầu nghiệp vụ thất bại, bạn sẽ thay đổi cách phát và xử lý sự kiện ra sao?
Nếu prototype bean giữ tài nguyên nhưng destruction callback không chạy, bạn sẽ thiết kế ownership và cleanup như thế nào?
Nếu một custom scope trả cùng object cho hai workflow độc lập, bạn sẽ kiểm tra scope context và cache key ra sao?
Nếu @Configuration(proxyBeanMethods=false) làm object graph khác dự kiến, bạn sẽ thay thế inter-bean calls bằng cách inject nào?
Nếu cần thiết kế Spring Core Container cho một ứng dụng nhiều module, bạn sẽ tổ chức bean definitions, DI, scopes, lifecycle, FactoryBean và kiểm thử như thế nào?
