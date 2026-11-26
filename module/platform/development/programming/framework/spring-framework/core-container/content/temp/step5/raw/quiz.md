Câu 1. Khi dùng Spring IoC Container, trách nhiệm nào thường được chuyển từ mã ứng dụng sang container?
A. Quản lý transaction SQL cho mọi đối tượng Java
B. Biên dịch bytecode của toàn bộ class trong dự án
C. Tạo và nối các bean theo cấu hình dependency
D. Tự tạo REST endpoint cho mỗi interface service
Đáp án đúng: C

Câu 2. Điểm mạnh của constructor injection với dependency bắt buộc là gì?
A. Bean có thể thay dependency bất kỳ lúc nào sau khởi tạo
B. Mọi vòng phụ thuộc constructor sẽ được container giải quyết
C. Không cần khai báo bean cho loại dependency được truyền
D. Phụ thuộc được xác lập khi tạo object và dễ kiểm thử
Đáp án đúng: D

Câu 3. ApplicationContext mở rộng khả năng của BeanFactory chủ yếu ở điểm nào?
A. Bổ sung event, resource và hỗ trợ cấu hình ứng dụng
B. Chỉ cho phép tạo bean bằng XML thay vì annotation
C. Dùng một cơ chế DI riêng không liên quan BeanFactory
D. Chỉ tạo bean prototype và cấm đăng ký singleton
Đáp án đúng: A

Câu 4. Với ApplicationContext được refresh bình thường, bean singleton không @Lazy thường được xử lý thế nào?
A. Chỉ được tạo ở lần getBean đầu tiên trong mọi cấu hình
B. Được khởi tạo sớm trong quá trình context refresh
C. Được tạo lại một lần cho mỗi lần tiêm dependency
D. Chỉ được tạo sau khi ApplicationContext đã close
Đáp án đúng: B

Câu 5. Nếu getBean theo một interface có hai bean cùng kiểu và không có cách phân giải, điều gì dễ xảy ra?
A. Container luôn chọn bean có tên ngắn nhất
B. Container mặc định chọn bean có thứ tự scan trước
C. Container tạo instance thứ ba để thay thế hai bean
D. Container báo lỗi vì tìm thấy nhiều ứng viên bean
Đáp án đúng: D

Câu 6. @ComponentScan thường giúp ApplicationContext làm gì?
A. Tạo bean chỉ từ các phương thức @Bean được gọi trực tiếp
B. Đọc và chạy tất cả script SQL dưới thư mục package
C. Tìm và đăng ký các lớp component trong vùng quét
D. Bật scan toàn classpath bất kể base package đã cấu hình
Đáp án đúng: C

Câu 7. Khi cần tạo bean cho một thư viện không thể sửa source, lựa chọn nào phù hợp?
A. Thêm @Component lên lớp thư viện lúc runtime
B. Đăng ký mọi class của thư viện bằng @Autowired
C. Tạo một @Qualifier ở interface thư viện là đủ
D. Khai báo @Bean trong một lớp cấu hình Spring
Đáp án đúng: D

Câu 8. Với @Configuration(proxyBeanMethods=true), gọi một @Bean method từ @Bean method khác có đặc điểm gì?
A. Lời gọi sẽ tạo object mới ở mọi lần dù bean singleton
B. Lời gọi được quản lý để lấy bean từ container
C. Lời gọi sẽ tạo proxy JDK của mọi giá trị trả về
D. Lời gọi chỉ hợp lệ nếu mỗi @Bean dùng scope prototype
Đáp án đúng: B

Câu 9. Annotation @Import trên lớp cấu hình Spring thường dùng để làm gì?
A. Đặt tên alias cho toàn bộ bean trong ApplicationContext
B. Bật dependency injection cho class nằm ngoài JVM
C. Đưa cấu hình hoặc component được chỉ định vào context
D. Thay component scanning bằng tìm mọi file jar
Đáp án đúng: C

Câu 10. Khi có nhiều bean cùng kiểu và một bean được @Primary, điều nào đúng?
A. Bean @Primary bị loại khỏi mọi collection injection
B. Bean @Primary luôn được tạo sau bean cùng kiểu
C. Bean @Primary được ưu tiên cho injection một giá trị
D. Bean @Primary thay tên của mọi bean còn lại
Đáp án đúng: C

Câu 11. Khi muốn chọn chính xác bean được đánh dấu một qualifier giữa nhiều bean cùng kiểu, nên dùng gì?
A. @Qualifier với giá trị phù hợp tại injection point
B. @Primary trên class nhận dependency để chọn field
C. @Lazy trên interface để chọn bean ít được dùng
D. @DependsOn trên field để loại tất cả bean khác
Đáp án đúng: A

Câu 12. Một class chỉ có một constructor phù hợp, Spring thường xử lý injection thế nào?
A. Bắt buộc gắn @Autowired trên từng tham số constructor
B. Chỉ autowire constructor không tham số sau khi component scan
C. Có thể autowire constructor đó dù không có @Autowired
D. Cấm constructor injection nếu class có @Component
Đáp án đúng: C

Câu 13. Khi dependency có thể không tồn tại và service vẫn hoạt động, kiểu tham số nào phù hợp?
A. T bắt buộc rồi bỏ qua lỗi thiếu bean lúc context refresh
B. List<T> với điều kiện phải có ít nhất hai bean
C. Supplier<T> tự tìm mọi implementation trong classpath
D. Optional<T> cho constructor parameter tùy chọn
Đáp án đúng: D

Câu 14. Khi inject List<PaymentHandler>, Spring thường cung cấp gì nếu có nhiều bean phù hợp?
A. Bean PaymentHandler duy nhất được đánh dấu @Primary
B. Danh sách tên class Java nhưng không có object thực
C. Một proxy đại diện bean đầu tiên tìm thấy khi scan
D. Collection các bean PaymentHandler khả dụng trong context
Đáp án đúng: D

Câu 15. Khi inject Map<String, Formatter> vào Spring bean, key thường biểu diễn gì?
A. Tên package của từng implementation Formatter
B. Đường dẫn classfile chứa implementation trong jar
C. Tên bean tương ứng với mỗi Formatter trong container
D. Thứ tự ưu tiên của bean dưới dạng chuỗi số
Đáp án đúng: C

Câu 16. Khi @Value sử dụng placeholder app.mode với mặc định dev, tác dụng nào phù hợp?
A. Tạo profile dev mới rồi kích hoạt trong context
B. Đọc property app.mode với giá trị mặc định dev
C. Đổi tên bean thành app.mode khi container refresh
D. Thêm giá trị mode vào dependency graph dưới dạng type
Đáp án đúng: B

Câu 17. Environment của Spring thường hữu ích cho tác vụ nào?
A. Tạo bean proxy mới cho mọi method trong class
B. Chọn SQL dialect cho từng @Repository method
C. Thay thế BeanFactory để chạy lệnh lifecycle
D. Đọc property và kiểm tra active profiles
Đáp án đúng: D

Câu 18. @PropertySource trên lớp @Configuration thường được dùng để làm gì?
A. Bổ sung nguồn property vào Environment của context
B. Định nghĩa transaction scope cho các bean mới tạo
C. Tạo alias cho tất cả property bean lúc khởi động
D. Bật @ComponentScan trong package của file properties
Đáp án đúng: A

Câu 19. Với @Profile("prod") trên một @Bean method, bean đó được đăng ký khi nào?
A. Khi profile prod đang hoạt động trong context
B. Khi tên package của method chứa chuỗi prod
C. Khi bean được gọi lần đầu dù profile không active
D. Khi tất cả bean khác đã tạo xong trong context
Đáp án đúng: A

Câu 20. Nếu @Bean không chỉ rõ tên trong một phương thức cấu hình, tên mặc định thường là gì?
A. Tên class cấu hình chứa phương thức @Bean
B. Tên phương thức được khai báo @Bean
C. Tên package đầu tiên được component scan
D. Tên kiểu trả về viết thường của đối tượng
Đáp án đúng: B

Câu 21. Trong core container, @Conditional trên @Bean thường điều khiển điều gì?
A. Tự động retry method @Bean nếu constructor báo lỗi
B. Đăng ký bean tùy vào kết quả của một Condition
C. Thay đổi scope của bean giữa singleton và prototype
D. Chạy body của bean method sau mỗi HTTP request
Đáp án đúng: B

Câu 22. Khi muốn component scan ngoài package mặc định của cấu hình, nên làm gì?
A. Đặt @Primary lên package cần Spring quét thêm
B. Chỉ khai @Lazy trên lớp cần phát hiện từ xa
C. Chỉ định basePackages hoặc basePackageClasses phù hợp
D. Đổi tên BeanFactory để container tìm mọi package
Đáp án đúng: C

Câu 23. @Lazy gắn lên singleton bean thường tác động thế nào?
A. Hoãn tạo bean đến khi cần, nếu không bị yêu cầu sớm
B. Chuyển singleton thành prototype sau lần truy xuất đầu
C. Bỏ qua mọi callback init và destroy của bean
D. Cho phép bean tồn tại dù dependency bắt buộc bị thiếu
Đáp án đúng: A

Câu 24. Scope singleton trong Spring thường mang ý nghĩa gì?
A. Một instance dùng chung giữa mọi ApplicationContext trong JVM
B. Một instance mới cho từng thread sử dụng bean
C. Một instance mới cho mỗi lần gọi getBean trong context
D. Một instance cho mỗi bean definition trong container
Đáp án đúng: D

Câu 25. Scope prototype thường tạo bean theo cách nào?
A. Dùng chung một instance trong mọi context từ classpath
B. Tạo instance mới mỗi lần container được yêu cầu bean
C. Tạo instance theo từng HTTP session đang hoạt động
D. Tạo instance một lần rồi đóng ngay khi @Autowired
Đáp án đúng: B

Câu 26. Một prototype bean được inject trực tiếp vào constructor singleton thường ra sao?
A. Spring tự thay prototype mới vào field ở mỗi lời gọi method
B. Singleton được chuyển thành prototype sau khi injection
C. Dependency được resolve lúc tạo singleton và giữ tham chiếu đó
D. Mỗi lần đọc field đều chạy BeanFactory.getBean tự động
Đáp án đúng: C

Câu 27. Muốn singleton lấy prototype mới theo nhu cầu, cách nào phù hợp?
A. Inject một prototype field rồi đọc lại nhiều lần
B. Inject ObjectProvider<T> rồi gọi getObject khi cần
C. Đánh dấu prototype bằng @Primary để tự tạo mới
D. Đặt @DependsOn trên singleton để refresh dependency
Đáp án đúng: B

Câu 28. Với bean scope request dùng ngoài request đang active, lỗi nào có thể gặp?
A. Container tự đổi request bean thành singleton
B. Mọi request bean sẽ được giữ cho tới JVM shutdown
C. Spring tạo HTTP request giả từ ApplicationContext
D. Không có request scope hiện hành để resolve bean
Đáp án đúng: D

Câu 29. Khi singleton cần dùng bean request-scoped, phương án nào thường thích hợp?
A. Inject scoped proxy hoặc provider để lấy theo request
B. Chuyển mọi request bean thành singleton mặc định
C. Tạo bean request trực tiếp bằng new trong constructor
D. Đưa @PostConstruct lên request bean để lưu toàn cục
Đáp án đúng: A

Câu 30. Khi prototype bean được tạo bởi Spring, ai thường chịu trách nhiệm gọi cleanup sau sử dụng?
A. Client giữ bean tự quản lý phần hủy sau khi dùng
B. Container tự gọi @PreDestroy cho mọi prototype lúc close
C. BeanFactory mặc định giữ và hủy mọi prototype đã cấp
D. Spring gộp prototype vào singleton để hủy một lần
Đáp án đúng: A

Câu 31. Muốn bổ sung một custom scope trong Spring, thao tác nào cần thiết?
A. Khai báo enum scope và để Spring tự quét classpath
B. Đặt @Primary lên scope class rồi để factory tự phát hiện
C. Chỉ đổi beanName thành tên scope trong mọi @Bean method
D. Đăng ký Scope implementation với bean factory
Đáp án đúng: D

Câu 32. @PostConstruct trên bean thông thường được gọi ở giai đoạn nào?
A. Sau inject dependency và trước khi bean sẵn sàng sử dụng
B. Trước khi Spring gọi constructor của bean trong container
C. Chỉ sau khi ApplicationContext đóng và bean đã bị hủy
D. Trước mọi BeanPostProcessor postProcessBeforeInitialization
Đáp án đúng: A

Câu 33. Với singleton được container quản lý, @PreDestroy thường được gọi khi nào?
A. Khi container đóng và thực hiện quy trình hủy bean
B. Mỗi lần bean được inject vào một dependency mới
C. Ngay trước mỗi lần method public được gọi
D. Sau mỗi lần ApplicationContext.getBean hoàn thành
Đáp án đúng: A

Câu 34. InitializingBean.afterPropertiesSet() dùng cho việc gì?
A. Thực thi callback ngay trước constructor bean
B. Thực thi callback khởi tạo sau khi property được set
C. Tự thay thế tên bean sau khi context refresh
D. Chạy callback hủy sau khi đóng ApplicationContext
Đáp án đúng: B

Câu 35. DisposableBean.destroy() thường tham gia bước nào của vòng đời bean?
A. Callback hủy đối với bean thuộc vòng đời do container quản lý
B. Tạo bean mới khi một dependency không tìm thấy
C. Chuyển bean từ singleton sang prototype khi lấy ra
D. Đăng ký bean definition trước khi component scan
Đáp án đúng: A

Câu 36. Khi có @PostConstruct, afterPropertiesSet và custom init method, thứ tự thường là gì?
A. Custom init method, @PostConstruct rồi afterPropertiesSet
B. afterPropertiesSet, custom init method rồi @PostConstruct
C. @PostConstruct, custom init method rồi afterPropertiesSet
D. @PostConstruct, afterPropertiesSet rồi custom init method
Đáp án đúng: D

Câu 37. @DependsOn("cacheConfig") giúp kiểm soát hành vi nào khi tạo bean?
A. Yêu cầu bean cacheConfig được khởi tạo trước bean phụ thuộc
B. Bắt buộc bean cacheConfig luôn là dependency của constructor
C. Tạo lại cacheConfig mỗi khi bean phụ thuộc được gọi
D. Thay @Autowired khi có nhiều bean cùng type cacheConfig
Đáp án đúng: A

Câu 38. Nếu bean A và B phụ thuộc constructor trực tiếp lẫn nhau, kết quả thường là gì?
A. Container tự tạo đầy đủ hai object không cần proxy
B. Lỗi circular dependency trong quá trình tạo bean
C. Spring tự dùng một constructor rỗng dù không tồn tại
D. Hai bean tự động chuyển thành prototype để tách vòng
Đáp án đúng: B

Câu 39. Khi gặp vòng phụ thuộc constructor A↔B, hướng thiết kế nào nên ưu tiên?
A. Bật @Primary trên cả hai bean để loại bỏ vòng
B. Tách trách nhiệm hoặc tái cấu trúc dependency graph
C. Thêm @DependsOn ngược chiều để cho phép vòng
D. Tăng số lượt component scan đến khi hết vòng
Đáp án đúng: B

Câu 40. BeanPostProcessor được dùng để can thiệp chủ yếu ở thời điểm nào?
A. Trước hoặc sau initialization của từng bean instance
B. Trước khi tất cả bean definitions được nạp vào factory
C. Trong lúc Java compiler tạo bytecode cho @Component
D. Khi context đóng để hủy schema của mọi bean
Đáp án đúng: A

Câu 41. BeanFactoryPostProcessor khác BeanPostProcessor ở đặc điểm nào?
A. Luôn nhận bean instance sau khi init method hoàn tất
B. Chỉ làm việc với prototype bean khi gọi getBean
C. Xử lý bean definition trước khi các bean thường được tạo
D. Chỉ hoạt động khi Java reflection bị tắt
Đáp án đúng: C

Câu 42. BeanDefinitionRegistryPostProcessor phù hợp với tác vụ nào?
A. Thay đổi return value của bean method lúc runtime
B. Xóa bean instance đang hoạt động sau khi init
C. Tạo lại toàn bộ ApplicationContext cho mỗi HTTP request
D. Bổ sung bean definition vào registry ở giai đoạn cấu hình
Đáp án đúng: D

Câu 43. Một class triển khai FactoryBean<T> có nhiệm vụ chính nào?
A. Tự quản lý vòng đời của ApplicationContext cấp cha
B. Tự tìm mọi component cùng package mà không scan
C. Chỉ cho phép tạo object trong scope prototype
D. Tạo object thông qua getObject cho bean được đăng ký
Đáp án đúng: D

Câu 44. Trong Spring, getBean("reportFactory") và getBean("&reportFactory") khác nhau thế nào?
A. Tên thường lấy FactoryBean, thêm & lấy product object
B. Cả hai trả một object giống nhau ở mọi cấu hình
C. Tên thường lấy product, thêm & lấy chính FactoryBean
D. Ký tự & làm Spring tạo thêm scope mới cho factory
Đáp án đúng: C

Câu 45. FactoryBean.getObjectType() hỗ trợ container giải quyết nhu cầu gì?
A. Biết loại SQL transaction cần mở khi getObject chạy
B. Nhận biết kiểu của object sản phẩm do factory cung cấp
C. Chọn ApplicationContext cha để đăng ký bean lần nữa
D. Xác định package cần scan khi tải file cấu hình
Đáp án đúng: B

Câu 46. SmartInitializingSingleton.afterSingletonsInstantiated() phù hợp để chạy lúc nào?
A. Trước khi bất kỳ bean definition nào được đăng ký
B. Ngay sau constructor của mỗi prototype bean
C. Sau khi pre-instantiate các singleton thường hoàn tất
D. Chỉ khi ApplicationContext đóng để giải phóng bean
Đáp án đúng: C

Câu 47. ApplicationEventPublisher giúp bean trong ApplicationContext làm gì?
A. Thay constructor injection bằng Java event sourcing
B. Tạo BeanFactory khác để chứa event handler
C. Phát sự kiện để các listener trong context nhận xử lý
D. Ép tất cả listener chạy bất đồng bộ mặc định
Đáp án đúng: C

Câu 48. BeanNameAware.setBeanName() được dùng khi bean cần biết thông tin nào?
A. Tên profile đang active lúc AppContext shutdown
B. Tên bean được container gán cho instance đó
C. Tên package sẽ được dùng cho component scanning
D. Tên parent ApplicationContext tạo root bean
Đáp án đúng: B
