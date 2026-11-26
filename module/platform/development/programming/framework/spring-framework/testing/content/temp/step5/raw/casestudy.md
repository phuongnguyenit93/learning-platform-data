Một nhóm dùng SpringExtension cho kiểm thử OrderService; test JUnit 5 vẫn tự tạo service bằng tay nên dependency injection không hoạt động giống lúc bean chạy trong ApplicationContext.
Ứng dụng quản lý vé có test @SpringJUnitConfig cho service đặt ghế; file cấu hình chỉ nạp repository mà bỏ bean đồng bộ hóa khiến lỗi dependency xuất hiện trước mọi assertion.
Đội phát triển đổi tên package của @Configuration dùng trong @ContextConfiguration; test tích hợp tìm cấu hình mặc định khác và khởi tạo nhầm bean production.
Một bộ kiểm thử dùng @SpringJUnitWebConfig cho controller MVC; WebApplicationContext chưa có cấu hình servlet cần thiết nên hành vi filter khác lúc triển khai thật.
Nhóm tạo test với @ExtendWith(SpringExtension.class) nhưng không khai báo nguồn context phù hợp; autowired repository không thể được tạo và lỗi chỉ xuất hiện trên máy CI sạch.
Ứng dụng có SpringExtension và một extension khác cùng quản lý lifecycle; thứ tự callback làm dữ liệu test bị dọn trước khi assertion cuối chạy.
Đội tích hợp sử dụng TestContext Framework để nạp nhiều cấu hình XML cũ; một bean được định nghĩa trùng tên trong Java configuration khiến test chạy với implementation không dự kiến.
Nhóm cấu hình @ContextHierarchy cho ứng dụng có context cha và con; controller ở context con nhận service khác với bean đã được mock tại context cha.
Một hệ thống dùng ApplicationContextInitializer để thêm property trong test; initializer thực thi trước khi môi trường giả lập sẵn sàng nên DataSource đọc URL không phù hợp.
Đội phát triển dùng ContextCustomizer tùy biến trong một thư viện kiểm thử; khi thêm dependency, cấu hình context thay đổi nhưng bộ test vẫn giả định cache được chia sẻ như trước.
Ứng dụng có TestExecutionListener tùy chỉnh để tạo tenant mẫu; listener chạy sau một cơ chế chuẩn bị fixture khác nên dữ liệu tenant không còn tương ứng yêu cầu test.
Nhóm thêm một TestExecutionListener qua @TestExecutionListeners mà thay thế danh sách mặc định; cơ chế inject và transaction của TestContext không hoạt động như những testcase cũ.
Một dịch vụ định nghĩa test bean ở profile integration; các testcase dùng cấu hình chỉ phù hợp unit test nên bean giao tiếp mạng thật được khởi tạo ngoài ý định.
Đội sử dụng @Autowired ApplicationContext trong test để kiểm bean; test chỉ xác nhận bean tồn tại mà không phát hiện workflow gọi sai bean do @Qualifier.
Một hệ thống chạy JUnit 4 test cũ cạnh JUnit 5 SpringExtension; việc chuyển một class sang Jupiter làm callback setup khác và dữ liệu không được reset như mong đợi.
Nhóm đặt @TestInstance(PER_CLASS) cho class kiểm thử Spring; trường mutable lưu trạng thái request qua nhiều method làm kết quả phụ thuộc thứ tự thực thi.
Ứng dụng có @Nested test dùng cấu hình khác class ngoài; cách kế thừa cấu hình TestContext khiến một nhóm nested case nhận bean không đúng môi trường mong muốn.
Đội thay @NestedTestConfiguration để kiểm các profile độc lập; property từ class bao ngoài vẫn ảnh hưởng kết quả theo cách nhóm chưa đưa vào kế hoạch.
Một dịch vụ cần kiểm sự kiện ContextRefreshedEvent khi startup; test dùng lại ApplicationContext đã cache nên event không xảy ra trong testcase thứ hai.
Nhóm kiểm tra bean có @PostConstruct cập nhật cache; test kỳ vọng callback chạy mỗi test method nhưng Spring chỉ khởi tạo bean khi context được tạo.
Ứng dụng dùng @PreDestroy để giải phóng kết nối mô phỏng; context vẫn được cache đến cuối test suite nên bộ đo tài nguyên tưởng bean bị rò rỉ.
Đội kiểm tra ApplicationContext có nhiều BeanFactoryPostProcessor; thứ tự post-process làm bean test được tạo khác giữa cấu hình đầy đủ và cấu hình cắt gọn.
Một test service cần cùng proxy @Transactional như production; developer tự gọi new OrderService trong test nên phương thức chạy không có transaction interceptor.
Nhóm dùng ReflectionTestUtils sửa private field của bean singleton; giá trị không được khôi phục sau testcase và test khác thấy cấu hình giả.
Ứng dụng có bean phụ thuộc Clock; test thay giờ trực tiếp trên bean dùng chung và làm các testcase cùng context tính deadline khác nhau.
Đội viết test dựa vào ApplicationEventPublisher thật; context test thiếu listener cần thiết nên publish không tạo side effect mà test vẫn báo thành công.
Một class kiểm thử dùng SpringExtension và constructor injection; JUnit cũng có ParameterResolver cho kiểu trùng nên việc phân giải tham số test xảy ra xung đột.
Nhóm dùng @TestConstructor để autowire tham số constructor của test; một tham số chưa được Spring quản lý khiến test fail ngay khi JUnit tạo instance.
Ứng dụng cấu hình bean scope request trong ApplicationContext test; test gọi service ngoài web request và gặp lỗi không có scope đang hoạt động.
Đội xây bộ kiểm thử chạy cùng lúc ở nhiều JVM; mỗi JVM có TestContext cache riêng nên không thể dùng cache như cơ chế khóa tài nguyên chung.
Một dịch vụ có hàng trăm @SpringJUnitConfig test gần giống nhau; mỗi class thay một property inline khiến nhiều ApplicationContext được tạo và tổng thời gian CI tăng mạnh.
Nhóm dùng static singleton state bên trong bean test; Spring TestContext cache tái sử dụng bean giữa các method và bộ đếm cũ làm test sau sai kết quả.
Ứng dụng dùng @DirtiesContext sau mỗi test dù không thay đổi cấu hình; build pipeline liên tục tạo lại context và thời gian kiểm thử tăng nhiều lần.
Đội phát triển sửa trạng thái một singleton cache trong testcase đầu; testcase kế tiếp nhận lại context cache và dữ liệu cũ khiến kết quả tùy vào thứ tự.
Nhóm thêm @DirtiesContext chỉ ở một nested testcase; các testcase lân cận khởi tạo context lại theo thời điểm khác dự kiến và mất dữ liệu mock cấu hình trước đó.
Một module sử dụng @DirtiesContext(classMode=AFTER_CLASS) để dọn state; test method thứ hai trong cùng class vẫn bị ảnh hưởng bởi thay đổi của method đầu.
Ứng dụng có bean ghi file trong thư mục cố định khi context được tạo; cùng context cache chạy ở nhiều class và các file fixture bị ghi đè khó phát hiện.
Đội đổi max size của Spring TestContext context cache bằng system property; số cấu hình context lớn làm eviction liên tục và tăng thời gian khởi chạy database giả.
Nhóm chạy các test song song có cấu hình gần giống; một test đánh dấu context dirty khi test khác vẫn dùng cùng instance và gây lỗi ngẫu nhiên ở giữa assertion.
Một test dùng @DirtiesContext(methodMode=BEFORE_METHOD) để bảo đảm state mới; context khởi tạo lại quá muộn so với fixture do @BeforeAll dựng và gây dữ liệu thiếu.
Đội tạo test annotation tổng hợp chứa @ContextConfiguration; hai class dùng alias khác nhau được xem là cấu hình cache khác dù nội dung business giống nhau.
Ứng dụng lưu client HTTP trong singleton bean của cached context; một testcase đóng client trực tiếp và các test tiếp theo gặp lỗi connection closed.
Nhóm muốn reset mock giữa các testcase nhưng mock nằm trong context được cache; lịch sử invocation từ lần test trước làm verify times trả sai.
Đội đo số lần context được load và thấy nhiều lần không mong muốn; một @TestPropertySource nhỏ khác nhau khiến cache key thay đổi giữa các class.
Ứng dụng dùng cùng context cache nhưng mỗi class thay schema database bên ngoài Spring; context vẫn tồn tại và các repository giữ metadata không còn tương ứng schema.
Nhóm reset database bằng thao tác xóa tất cả bảng trong @AfterEach; một test chạy song song vẫn đang truy vấn và nhận lỗi dữ liệu bị mất.
Đội chuyển từ @DirtiesContext sang reset bean trạng thái riêng; các event listener cũng giữ bộ đệm riêng nên reset một bean không xóa toàn bộ ảnh hưởng của test trước.
Ứng dụng có TestContext cache tĩnh trong từng JVM; test được chia thành nhiều fork Maven nên team ngạc nhiên khi mỗi fork khởi động container và context riêng.
Nhóm muốn tái dùng context giữa hai cấu hình profile khác nhau; profile ảnh hưởng tập bean nên mỗi context dùng state riêng và chi phí khởi tạo cao hơn dự toán.
Một hệ thống có cấu hình property đến từ @DynamicPropertySource; các subclass dùng cùng method nguồn nhưng container kết nối khác khiến context cache dùng lại giá trị không phù hợp.
Đội test kết nối dịch vụ ngoài dùng cùng property URL ở nhiều class; URL thay đổi sau lần đầu khởi động nhưng cached context vẫn giữ client đã đọc địa chỉ cũ.
Nhóm viết TestExecutionListener dọn cache ứng dụng trước mỗi method; test sau vẫn bị ảnh hưởng bởi static state nằm ngoài ApplicationContext.
Ứng dụng dựng test data ngay trong @Bean factory method của context; vì caching, dữ liệu chỉ được tạo một lần trong khi mỗi testcase kỳ vọng fixture mới.
Đội tạo tài khoản admin khi context refresh; hai test class chia cache nhưng một class đã xóa tài khoản này và class sau thất bại khi xác thực.
Một bộ integration test sử dụng @ActiveProfiles("test") cho database; một class quên annotation và kết nối thẳng database cấu hình mặc định ngoài ý muốn.
Nhóm dùng @ActiveProfiles({"test","ci"}) trong một lớp kiểm thử; bean @Profile("ci") ghi dữ liệu ra dịch vụ thật mà test chỉ kỳ vọng mock nội bộ.
Ứng dụng đổi profile mặc định bằng biến môi trường của CI runner; test không gắn profile cụ thể nên chạy khác giữa máy cá nhân và pipeline.
Đội phát triển dùng ActiveProfilesResolver để chọn profile theo hệ điều hành; cùng mã test tải hai cấu hình SecurityFilterChain khác và tạo kết quả khó tái hiện.
Nhóm sử dụng @TestPropertySource với file properties trên classpath; file nằm trong resources chính thay vì test resources khiến URL endpoint production được dùng.
Ứng dụng cấu hình @TestPropertySource(properties=...) để ghi đè host; một property khác có ưu tiên cao hơn vẫn cung cấp URL thật và test thực hiện request ngoài dự kiến.
Đội chạy test trên Java khác nhau và dùng system property timezone; một testcase thay timezone toàn JVM nhưng không hoàn nguyên làm kiểm thử lịch chạy khác nhau.
Nhóm test business rule với giá trị @Value từ environment; property thay đổi trong lúc context cache đang dùng nhưng bean singleton vẫn giữ giá trị cũ.
Ứng dụng có default property ở nhiều PropertySource; test sửa một key nhưng quên cấu hình phụ thuộc, tạo tổ hợp giá trị không thể xuất hiện ở production.
Đội dùng @DynamicPropertySource để đăng ký port ngẫu nhiên của Testcontainers; property được lấy trước khi container thực sự sẵn sàng và repository kết nối sai địa chỉ.
Nhóm khởi động PostgreSQL Testcontainers một lần cho toàn suite; container bị dừng bởi testcase trước nhưng cached context còn DataSource trỏ vào port đã chết.
Ứng dụng dùng @DynamicPropertySource lấy thông tin service giả qua lambda; test đầu dừng service rồi test sau vẫn giữ lambda tham chiếu tới instance cũ.
Đội tạo DatabaseCleaner dùng tên schema qua property test; một profile khác chọn schema mặc định và cleanup xóa nhầm dữ liệu fixture của module khác.
Nhóm đặt @TestPropertySource riêng cho mỗi feature test; số lượng context cấu hình khác biệt tăng liên tục và CI gần hết thời gian chạy.
Một ứng dụng nạp cấu hình test qua @PropertySource trên @Configuration; nhà phát triển tưởng giá trị đó ưu tiên hơn @TestPropertySource và xác minh sai môi trường.
Đội thay clock trong test bằng property dynamic; bean dùng @ConfigurationProperties đã được bind trước nên thay property không làm thời gian trong service thay đổi.
Nhóm dùng placeholder trong @Sql script để tạo schema theo profile; đường phân giải property khác giữa test config và script khiến lệnh tạo bảng thất bại.
Ứng dụng cấu hình mật khẩu thử nghiệm bằng environment variable; khi CI không cấp secret, test dùng mật khẩu mặc định và báo kết nối lỗi khác với production.
Đội dùng @ActiveProfiles để bỏ qua bean gửi email; một test muốn kiểm chức năng gửi vẫn autowire mock khác thực tế, nên lỗi tích hợp không được phát hiện.
Nhóm chuẩn bị fixture theo ngôn ngữ vi_VN trong @BeforeEach; một lớp kiểm thử khác thay Locale mặc định toàn JVM khiến format số thập phân bị sai.
Ứng dụng dùng file cấu hình YAML cho test và properties cho production; khác biệt kiểu dữ liệu boolean/array khiến điều kiện bean hoạt động không giống nhau.
Đội sử dụng @Import để thêm một bean kiểm thử vào context; bean trùng qualifier với cấu hình chính khiến service nhận dependency không đúng loại.
Một nhóm kiểm thử service với @TestBean để thay implementation của PaymentGateway; tên field thay đổi sau refactor và bean bị override không phải bean mà service sử dụng.
Ứng dụng dùng @MockitoBean thay HTTP client; service có qualifier cho client chính nhưng mock được đăng ký theo type khác và lời gọi thực vẫn đi ra mạng.
Đội tạo hai @MockitoBean cùng type nhưng bean name khác nhau; một service inject bean theo tên cũ và tương tác không được mock như kỳ vọng.
Nhóm viết mock với stubbing ở một testcase nhưng mock được reset trước testcase kế tiếp; test thứ hai không còn dữ liệu giả dù hai case dùng chung cached context.
Ứng dụng dùng @MockitoSpyBean trên service có transaction proxy; method được spy không thể xác minh theo cách gọi trực tiếp và test nhầm rằng nghiệp vụ không chạy.
Đội thêm @TestBean vào một class kiểm thử để thay repository; một class khác dùng cấu hình giống nhưng thiếu override nên cache context khác và thời gian chạy tăng.
Nhóm ghi mock bean trong @Configuration test với @Primary; service lại dùng @Qualifier rõ ràng nên bean thật vẫn được gọi trong integration test.
Ứng dụng dùng mock chung cho nhiều API của cùng đối tác; một lần stub quá tổng quát che mất lỗi mapping request và contract thực với đối tác bị sai.
Đội thử thay Clock bean để cố định thời gian; một component tạo Clock.systemUTC trực tiếp ngoài Spring nên kết quả test vẫn phụ thuộc thời gian thật.
Nhóm replace bean xác thực bằng stub luôn cho phép truy cập; testcase MockMvc kiểm status 200 nhưng bỏ qua lỗi quyền ở SecurityFilterChain thật.
Ứng dụng có scoped proxy cho thông tin user; test mock target không đúng proxy khiến session state khác và người dùng A nhìn dữ liệu của B.
Đội dùng @MockitoSpyBean kiểm số lần repository gọi; các lần gọi gián tiếp từ listener hoặc callback tạo thêm invocation và test bị lỗi không tương ứng yêu cầu nghiệp vụ.
Nhóm dùng stub service trả kết quả bằng CompletableFuture đã hoàn tất; production timeout và thread rejection không thể được phát hiện qua bộ test đó.
Ứng dụng kiểm controller với bean thật nhưng mock PaymentGateway; bản test giả định mock không có side effect nên không phát hiện logic idempotency sai khi API đối tác retry.
Đội cấu hình bean replacement nhưng chưa thống nhất tên giữa các class; chỉ thay field name đã khiến TestContext cache tạo thêm ApplicationContext dù cấu hình chức năng giống.
Nhóm dùng mock để ném SQLException khi repository save; wrapper exception thực của Spring Data không được mô phỏng và exception handler xử lý sai loại lỗi.
Ứng dụng có bean event publisher được spy để kiểm event; verify pass ngay khi publish nhưng listener giao dịch chưa thực thi vì chưa commit.
Đội sử dụng mock RestClient cho API thông báo; mock không kiểm header tenant và HTTP integration test không phát hiện thông tin phân vùng bị bỏ.
Nhóm tạo fake DataSource cho phần lớn test và nhầm rằng đã kiểm được transaction; fake không hỗ trợ rollback và khóa như PostgreSQL thật.
Ứng dụng dùng @Transactional trên method test để rollback fixture; controller được gọi qua MockMvc và đội QA nhầm việc rollback của test với rollback ở môi trường request thật.
Đội kiểm transaction trong @SpringJUnitConfig với dữ liệu test; test method có @Transactional nhưng thiếu PlatformTransactionManager phù hợp và không tạo ranh giới như mong muốn.
Nhóm dùng @Commit trên một integration test tạo hóa đơn; dữ liệu còn trong database và testcase chạy sau bị vi phạm unique constraint.
Ứng dụng có @Rollback(false) trên class test; mỗi lần CI retry bộ test đều thêm dữ liệu và kết quả phụ thuộc bản ghi còn từ lượt trước.
Đội dùng @BeforeTransaction để xóa dữ liệu nền; một class chạy song song đang trong transaction khác nên bước dọn gây lỗi hoặc xóa fixture của test kia.
Nhóm dùng @AfterTransaction để kiểm trạng thái database sau commit; testcase mặc định rollback nên assertion không thể dựa vào dữ liệu đã được ghi bền vững.
Ứng dụng tạo dữ liệu trong @BeforeAll ngoài test-managed transaction; test method rollback không xóa dữ liệu này và suite tiếp theo gặp xung đột khóa.
Đội thiết lập @BeforeEach để tạo entity cho mỗi test; một method @Transactional riêng có propagation khác làm fixture được commit và không bị rollback với testcase.
Nhóm dùng AssertJ để kiểm DB trước khi transaction flush; ORM chưa gửi SQL nên unique constraint không được phát hiện dù test gần kết thúc.
Ứng dụng ghi Invoice rồi đọc lại trong cùng persistence context; entity được lấy từ cache khiến test không phát hiện mapping sai ở bước truy vấn SQL.
Đội dùng saveAndFlush để kích hoạt lỗi constraint; database thật chỉ kiểm một số ràng buộc tại commit và testcase kết luận sai khi chưa kết thúc transaction.
Nhóm test quy trình thanh toán có phương thức REQUIRES_NEW bên trong; dữ liệu được commit ở transaction con dù transaction test bên ngoài rollback sau assertion.
Ứng dụng phát ApplicationEvent và listener AFTER_COMMIT trong testcase @Transactional; listener không chạy vì test rollback theo mặc định và email giả không được ghi.
Đội cấu hình @Sql chạy trước testcase để tạo đơn; script dùng transaction mode tách biệt nên dữ liệu không được rollback cùng test và tích lũy qua nhiều lần.
Nhóm dùng @Sql để cleanup sau method; thứ tự script với các transaction test tạo tình huống dữ liệu bị xóa trước khi callback khác hoàn tất.
Ứng dụng bật @SqlMergeMode để kết hợp script class và method; dữ liệu chung bị tạo hai lần khi hai script cùng chèn tài khoản quản trị.
Đội dùng @SqlConfig để chọn transaction manager; trong dự án có nhiều DataSource, script setup ghi vào database khác repository đang đọc.
Nhóm chạy integration test với transaction test-managed và HTTP server chạy cổng thật; request được xử lý trên thread khác nên không chia sẻ transaction rollback của test.
Ứng dụng có test timeout preemptive của JUnit; method kiểm thử thực thi trên thread mới ngoài ranh giới transaction mà TestContext gắn với thread gốc.
Đội muốn kiểm optimistic locking bằng hai transaction độc lập; cả hai đoạn code đang nằm trong một transaction test và không tạo xung đột thực tế.
Nhóm chạy test deadlock với @Transactional và một thread; không có hai connection/transaction độc lập nên test không bao giờ tái hiện lỗi dưới tải.
Ứng dụng có event listener async ghi audit; test method rollback DB chính trong khi worker vẫn commit audit riêng và fixture bị rò qua các testcase sau.
Đội kiểm rollback trên H2 nhưng production là PostgreSQL; isolation, constraint và locking khác nhau khiến bộ test không phản ánh sự cố giao dịch thực.
Nhóm dùng @Transactional(readOnly=true) trên một test muốn kiểm thao tác update; câu lệnh save hành xử khác với transaction đọc và kết quả bị hiểu sai.
Ứng dụng dùng TestTransaction để kết thúc transaction giữa testcase; assertion trước và sau commit thấy dữ liệu khác nhưng nhóm chưa phân biệt persistence context với database thật.
Đội tạo fixture theo ID cố định trong test @Transactional; testcase khác chạy song song sử dụng cùng ID và chạm khóa dù cả hai đều có rollback.
Nhóm viết @Sql để reset sequence trước mỗi test; test chạy song song trên cùng database tạo trùng ID giữa hai tác vụ kiểm thử.
Ứng dụng dùng MockMvc với webApplicationContextSetup; một class chỉ dựng controller bằng standaloneSetup nên không chạy đầy đủ interceptor và filter như môi trường thật.
Đội kiểm POST /orders bằng MockMvc; test chỉ assert HTTP 201 mà không xác nhận header Location đang thiếu mã đơn.
Nhóm dùng MockMvc thực hiện GET /customers; query parameter chứa dấu tiếng Việt bị decode khác kỳ vọng nhưng bộ test chỉ dùng dữ liệu ASCII.
Ứng dụng kiểm request JSON qua MockMvc; test chỉ gửi Content-Type hợp lệ và chưa kiểm phản hồi khi client dùng content type không được hỗ trợ.
Đội kiểm validation bằng MockMvc; DTO có @NotNull và @Size nhưng test không gửi trường rỗng nên cấu hình Bean Validation sai không bị phát hiện.
Nhóm giả lập request với path variable có dấu cách và ký tự encode; controller nhận đường dẫn khác dự kiến khi chạy qua proxy thực.
Ứng dụng dùng MockMvc để kiểm phân trang đơn hàng; test không kiểm page=0, size vượt giới hạn và sort field sai nên API có thể gây truy vấn rất lớn.
Đội test handler @ControllerAdvice bằng MockMvc; exception bị mock service trả loại khác production nên status mapping lỗi chưa được kiểm.
Nhóm dùng MockMvc standaloneSetup cho controller; bộ xử lý exception toàn cục không được cấu hình và response lỗi khác WebApplicationContext thật.
Ứng dụng xác thực bằng Spring Security filter chain; testcase MockMvc không gắn filters nên endpoint bảo vệ trả 200 cho user không có quyền.
Đội dựng MockMvc với filter tùy biến nhưng thiếu filter xác thực trước nó; header user bị tin cậy trực tiếp và test không thấy lỗ hổng giả mạo.
Nhóm kiểm POST CSRF-protected bằng MockMvc; testcase gửi token hợp lệ cho mọi nhánh và không phát hiện request thiếu CSRF bị chấp nhận ngoài ý muốn.
Ứng dụng kiểm login session bằng MockMvc; mỗi request dùng session mới nên workflow giữ trạng thái giỏ hàng không được kiểm như trình duyệt thật.
Đội dùng MockMvc để xác minh cookie bảo mật; test chỉ kiểm tên cookie và bỏ qua SameSite, Secure và HttpOnly khiến rủi ro phiên truy cập không được phát hiện.
Nhóm kiểm CORS preflight bằng MockMvc; cấu hình standalone controller thiếu filter CORS và testcase cho kết quả khác deployment phía gateway.
Ứng dụng có controller trả ETag cho tài nguyên; test không gửi If-None-Match nên bug trả 200 thay vì 304 chưa được phát hiện.
Đội dùng MockMvc kiểm upload multipart file; file test chỉ 2 KB và không phát hiện xử lý quá giới hạn dung lượng khi khách tải file lớn.
Nhóm upload tập tin qua MockMvc với filename từ người dùng; tên file chứa đường dẫn đặc biệt làm service lưu sai vị trí nhưng testcase chỉ dùng tên an toàn.
Ứng dụng có endpoint tải PDF qua MockMvc; test chỉ xem status 200 nên không phát hiện Content-Disposition và filename UTF-8 sai.
Đội dùng MockMvc để kiểm webhook chữ ký HMAC; test tái tạo chuỗi JSON khác raw body nhưng không phát hiện lỗi canonicalization với payload thực.
Nhóm kiểm API sinh sự kiện sau khi lưu đơn; mock EventPublisher được verify nhưng listener AFTER_COMMIT và database update thực chưa từng chạy.
Ứng dụng dùng MockMvc kiểm response JSON; test so sánh một trường duy nhất và bỏ qua thuộc tính nhạy cảm bị serialize ngoài ý muốn.
Đội dùng JSONPath để assert danh sách Order; test chỉ kiểm phần tử đầu và không phát hiện bản ghi bị lặp do JOIN khi phân trang.
Nhóm test response lỗi qua MockMvc; cấu hình locale khác production làm message và định dạng số trả về thay đổi nhưng assertion quá cố định.
Ứng dụng có controller trả ResponseEntity<Void>; test chỉ so status và không phát hiện response chứa body cũ do filter thêm nội dung.
Đội kiểm SSE endpoint bằng MockMvc async support; testcase không chờ hoàn tất request bất đồng bộ và bỏ qua lỗi phát sinh sau khi controller trả.
Nhóm dùng MockMvc asyncDispatch với DeferredResult; test chỉ assert trạng thái trước async nên exception của worker không được ghi nhận.
Ứng dụng có endpoint streaming trả nhiều chunk; MockMvc không mô phỏng hoàn toàn mạng và backpressure thực nên bộ test chưa đánh giá trường hợp client đọc chậm.
Đội kiểm Spring MVC mapping theo HTTP method; testcase dùng GET và POST nhưng không kiểm PUT sai Content-Type, dẫn tới status không đúng hợp đồng.
Nhóm dùng @WebMvcTest để kiểm controller Spring Boot; bean thuộc tầng service không được nạp nên phải mock nhưng test nhầm đây là toàn bộ integration path.
Ứng dụng dùng MockMvc và cấu hình profile test bỏ filter rate-limit; endpoint chạy tốt trong test nhưng production trả 429 sớm hơn dự kiến.
Đội viết testcase MockMvc cho request có Accept application/json; client thực dùng Accept có nhiều media type và controller chọn converter khác.
Nhóm kiểm endpoint cập nhật theo If-Match; MockMvc test không gửi version header nên chức năng tránh ghi đè đồng thời không được xác nhận.
Ứng dụng chuyển từ MockMvc sang WebTestClient trên application context MVC; một số assertion phụ thuộc reactive publisher dù đường xử lý thực vẫn là servlet blocking.
Đội dùng WebTestClient.bindToApplicationContext cho WebFlux router; bean security filter không nằm trong context test nên endpoint trả dữ liệu không đúng mức quyền.
Nhóm tạo WebTestClient.bindToController trong test; WebFilter cấu hình ở application context thật không được chạy và lỗi CORS không được phát hiện.
Ứng dụng kiểm endpoint Flux bằng WebTestClient; test mong có đúng ba item nhưng luồng thực có thể tiếp tục vô hạn nên testcase treo.
Đội dùng WebTestClient để kiểm dữ liệu streaming; test gom toàn bộ response vào List nên không kiểm được backpressure và memory khi client đọc chậm.
Nhóm kiểm Mono trả về 404 khi không tìm thấy tài khoản; stub repository trả Mono.empty trong test nhưng repository thật có thể phát error vì mapping dữ liệu cũ.
Ứng dụng dùng WebTestClient.verify status 200 cho API reactive; test không đọc body nên lỗi serialization và thiếu field chỉ xuất hiện trên client thật.
Đội thiết lập responseTimeout rất ngắn cho WebTestClient; trên máy CI quá tải, request hợp lệ chưa xong và test thường xuyên thất bại ngẫu nhiên.
Nhóm chạy WebTestClient.bindToServer với RANDOM_PORT; server dùng thread khác và transaction test không rollback được những thay đổi phát sinh từ HTTP request.
Ứng dụng kiểm HTTP header của WebFlux endpoint; test bindToRouterFunction bỏ custom WebFilter ghi traceId nên header khác khi deployment.
Đội dùng WebTestClient kiểm luồng SSE; test chỉ lấy sự kiện đầu tiên và không phát hiện connection ngắt khi backend phát sự kiện thứ hai.
Nhóm kiểm WebSocket hoặc streaming response bằng WebTestClient đơn giản; testcase thiếu điều kiện disconnect và cleanup nên resource còn mở sau khi test hoàn tất.
Ứng dụng có endpoint trả Flux có retry; test chỉ kiểm kết quả cuối và không phát hiện cùng side effect bị thực hiện nhiều lần.
Đội dùng WebTestClient trên application context có codec tùy biến; bài test độc lập với bindToController dùng codec mặc định nên phản hồi dữ liệu lớn khác thực tế.
Nhóm muốn kiểm lỗi 413 khi payload quá lớn; WebTestClient test không cấu hình giới hạn codec giống production và không phát hiện lỗi nhận body.
Ứng dụng dùng WebTestClient truyền JWT test được tạo thủ công; test bypass bộ giải mã và điều kiện audience nên request không hợp lệ vẫn qua.
Đội kiểm endpoint reactive sử dụng boundedElastic cho I/O; test stub trả dữ liệu ngay nên không phát hiện nghẽn khi database blocking chậm.
Nhóm chạy WebTestClient với virtual time trong một test Reactor; scheduler thật từ một bean khác không theo thời gian giả và testcase bị treo.
Ứng dụng kiểm một API WebFlux dùng transaction reactive; test @Transactional blocking không bao phủ Reactor Context và dữ liệu sau test vẫn còn.
Đội kiểm timeout response của WebTestClient; server đã hủy response nhưng tác vụ ghi nền vẫn tiếp tục và tạo bản ghi ngoài ý muốn.
Nhóm chạy kiểm thử tầng dữ liệu với @JdbcTest; test giả định BeanFactory sẽ nạp cả service nghiệp vụ nhưng slice chỉ chứa thành phần JDBC.
Ứng dụng dùng @DataJpaTest của Spring Boot để kiểm repository; test thay DataSource bằng database embedded và không phản ánh SQL PostgreSQL production.
Đội dùng Testcontainers PostgreSQL cho kiểm thử JPA; migration Flyway chỉ chạy ở app production nên schema test không tương ứng bản đã triển khai.
Nhóm kiểm findByCustomerId của repository bằng một bản ghi; dữ liệu production chứa nhiều tenant trùng ID và query thiếu điều kiện tenant.
Ứng dụng dùng test entity mapping mà không flush trước assertion; unique constraint của database chưa được kiểm khi test kết thúc rollback.
Đội tạo test cho derived query với một trang dữ liệu; query count khi JOIN làm totalElements sai nhưng testcase không có trang thứ hai.
Nhóm dùng @Sql để đưa dữ liệu tiếng Việt vào database test; script đọc charset khác làm chuỗi được lưu sai và phương thức tìm kiếm trả rỗng.
Ứng dụng kiểm thứ tự giao dịch bằng SQL ORDER BY createdAt; fixture tạo timestamp khác nhau nên không phát hiện lỗi khi nhiều bản ghi cùng thời điểm.
Đội thử kiểm repository native query trên H2; production PostgreSQL dùng JSONB và window function có cú pháp khác nên API báo lỗi lúc chạy.
Nhóm dùng transaction test rollback để dọn dữ liệu; repository gửi domain event ra external queue không rollback cùng database và các test sau nhận message cũ.
Ứng dụng kiểm optimistic locking bằng save liên tiếp một entity; không tạo hai persistence context nên xung đột cập nhật song song không được tái hiện.
Đội dùng in-memory database để kiểm truy vấn có khóa hàng; H2 và PostgreSQL khác hành vi lock wait khi hai worker cập nhật cùng bản ghi.
Nhóm tạo test dữ liệu ở địa chỉ mặc định của database container; nhiều suite CI chạy song song cùng network alias và kết nối nhầm container của nhau.
Ứng dụng có repository dùng @Cacheable; test đọc cùng một ID hai lần và tưởng query chỉ chạy một lần do cache, nhưng cache từ testcase trước còn nguyên.
Đội chạy test migration tạo bảng mới; một class còn kết nối tới schema đã được migrate từ suite trước khiến test không tái hiện upgrade trên dữ liệu legacy.
Nhóm kiểm tối ưu N+1 bằng cách đếm số SQL; test chỉ có một Order nên sự tăng truy vấn theo từng child bị bỏ sót.
Ứng dụng dùng spy repository để đếm số save; nghiệp vụ có saveAll nhưng SQL phát nhiều INSERT/UPDATE hơn kỳ vọng và test không quan sát tầng database.
Đội dùng test fixture tự tạo ID trong bộ nhớ; database thật sinh ID sau insert khiến các association không được lưu đúng trong integration flow.
Nhóm kiểm audit @CreatedDate và @CreatedBy; test dùng user context cố định và không phát hiện tác vụ scheduler lưu bản ghi với actor null.
Ứng dụng có nhiều DataSource và transaction manager; @Sql setup nạp data vào database A nhưng repository test truy vấn database B.
Đội muốn kiểm cleanup sau transaction rollback; @AfterTransaction xác minh schema nhưng một listener async vẫn đang ghi dữ liệu sau khi test kết thúc.
Nhóm dùng fixture SQL với foreign key tắt để nhập nhanh; production bật ràng buộc nên thao tác xóa aggregate theo thứ tự sai gặp lỗi.
Ứng dụng kiểm truy vấn phân trang ở database test có 100 dòng; production có hàng triệu dòng và kế hoạch truy vấn không sử dụng index phù hợp.
Đội đánh giá saveAll cho hàng nghìn aggregate bằng unit test repository giả; chi phí flush, batch SQL và transaction thật chưa được đo.
Nhóm kiểm lỗi retry của transaction khi deadlock; test dùng một thread nên không thực sự có transaction cạnh tranh và chính sách retry không được thử.
Ứng dụng có service khởi tạo ScheduledTask khi context load; test chia context cache và tác vụ chạy nền thay đổi database trong lúc assertion.
Đội đặt MockMvc test sử dụng cùng session giữa nhiều method; session của khách cũ chứa quyền admin làm test user thường vượt kiểm tra.
Nhóm thực thi test song song với static mutable Clock; một test đặt thời gian hết hạn token và test khác nhận sai giờ hiện tại.
Ứng dụng dùng RandomPort test với một static baseUrl; test chạy song song ghi đè port khiến request được gửi vào instance server của class khác.
Đội tạo dữ liệu bằng Faker với seed ngẫu nhiên không cố định; lỗi xác thực chỉ xảy ra khi một tên hoặc email đặc biệt được sinh ra và khó tái hiện.
Nhóm sử dụng UUID ngẫu nhiên làm ID fixture rồi khẳng định order theo ID; kết quả danh sách thay đổi giữa các lần CI dù code business không đổi.
Ứng dụng tạo mock server bên ngoài Spring context; testcase fail giữa chừng không dừng server và các test sau không thể bind cùng cổng.
Đội dùng Testcontainers và shutdown container trong @AfterAll của một class; class khác còn dùng cached DataSource của cùng container và gặp connection refused.
Nhóm chạy nhiều integration test với cùng tenant test trong DB chia sẻ; cùng mã hóa đơn bị tạo hai lần và bộ test thất bại ngẫu nhiên.
Ứng dụng cho phép test sửa system property toàn JVM; khi JUnit chạy parallel, một test thay cấu hình SMTP làm test khác kết nối nhầm server.
Đội bật @DirtiesContext để xử lý lỗi rò rỉ fixture; nguyên nhân thật là static cache ngoài Spring nên context mới vẫn tiếp tục nhận state cũ.
Nhóm chạy Mockito mock với strict stubbing khác nhau giữa local và CI; một test phụ thuộc lời gọi thêm của framework nên bị báo unused stub không ổn định.
Ứng dụng đợi tác vụ @Async bằng Thread.sleep trong test; trên CI bị tải cao, callback chưa hoàn tất và assertion ngẫu nhiên thất bại.
Đội giả lập Clock để kiểm hạn token; business code dùng System.currentTimeMillis trực tiếp nên test không kiểm được thời gian ở luồng thật.
Nhóm muốn kiểm email listener sau commit; test chỉ verify ApplicationEventPublisher.publishEvent chứ không khởi động listener hoặc SMTP giả.
Ứng dụng thay bean gateway bằng mock phản hồi ngay; bài test bỏ qua lỗi timeout, circuit breaker và kết nối nên sự cố production không được phát hiện.
Đội dùng @TestPropertySource cho một mức quota rất thấp; test chạy cùng cached context nhưng một bean đã đọc quota lúc khởi tạo từ cấu hình khác.
Nhóm chạy test API REST với JSON fixture cũ; một trường DTO mới không có trong fixture và được gán mặc định, nên mapping dữ liệu bắt buộc không được xác minh.
Ứng dụng cần kiểm 401 và 403 với MockMvc; test chỉ dùng token admin hợp lệ và không phát hiện rule chặn user thường bị thiếu.
Đội kiểm lỗi race condition bằng hai thread và CountDownLatch; hai worker vẫn dùng chung một transaction test-managed và không thực sự cạnh tranh database.
Nhóm thêm test reactive với StepVerifier nhưng publisher không được subscribe trong testcase; thao tác ghi không xảy ra dù test mock gọi method đã thành công.
Ứng dụng phát message sau xử lý HTTP; integration test chỉ đo database nên không biết callback trả lỗi sau khi transaction chính đã commit.
Đội vận hành muốn phân loại test flaky do thread pool; CI chỉ lưu kết quả JUnit mà không lưu log executor queue hay correlation ID của request lỗi.
Nhóm đánh giá bộ test tích hợp mất quá lâu; phần lớn thời gian dùng để tạo ApplicationContext nhiều lần do profile và bean overrides khác nhau.
Ứng dụng có hàng trăm test dùng chung fixture trong database; một thay đổi constraint mới làm nhiều testcase fail vì fixture không biểu diễn dữ liệu hợp lệ.
Đội nâng Spring Framework và JUnit Jupiter trong cùng release; extension lifecycle và context key thay đổi làm một nhóm test cũ dùng sai state dù vẫn biên dịch.
Nhóm triển khai nhiều test suite chạy cùng lúc ở CI; một suite xóa thư mục file upload dùng chung và suite khác báo lỗi không tìm thấy attachment.
Ứng dụng có test kiểm format lỗi dựa trên ngôn ngữ máy phát triển; môi trường CI chạy English locale làm assertion message tiếng Việt thất bại.
Đội chuyển sang kiểm API qua WebTestClient từ server thật; response timing phụ thuộc network/port còn test cũ dựa vào MockMvc chạy trong context và không có cùng giới hạn.
Nhóm kiểm tra resource cleanup sau context shutdown; bộ test không thực sự đóng ApplicationContext vì cache nên connection leak không được phát hiện.
Ứng dụng bật test parallel execution để giảm thời gian CI; singleton cache, DatabaseCleaner và mock reset chưa thread-safe nên số test flaky tăng mạnh.
Đội viết testcase kiểm optimistic lock bằng một user duy nhất; tranh chấp giữa hai request thực tế không xuất hiện nên lỗi ghi đè dữ liệu tồn tại đến production.
Nhóm chỉ assert HTTP status của các controller; thông tin nhạy cảm bị serialize từ entity vào response mà bộ test không kiểm trường bị lộ.
Ứng dụng cần xác minh điều kiện rollback với external API; test có mock service luôn thành công nên dữ liệu lưu một phần khi external call lỗi chưa từng được kiểm.
Đội triển khai test database tự động rollback nhưng vẫn dùng filesystem thật; file PDF tạo trong transaction lỗi không được dọn và làm các test tiếp theo đọc tài liệu cũ.
Nhóm dùng cùng SMTP giả để kiểm gửi email qua Spring TestContext; một testcase không xóa mailbox nên số lượng mail mong đợi ở testcase sau bị lệch.
Ứng dụng có scheduled job chạy cùng lúc với MockMvc test; job cập nhật trạng thái trước assertion làm API trả dữ liệu không ổn định.
Đội triển khai suite kiểm thử contract giữa controller và client; MockMvc test chỉ dùng object Java nội bộ nên không phát hiện khác biệt serialization JSON thực.
Nhóm thử kiểm thay thế bean trong TestContext khi chạy AOT/native test; bean override dựa vào reflection không có metadata cần thiết làm test thất bại ở môi trường đóng gói khác.
Ứng dụng dùng @MockitoBean cho nhiều bean chung loại trong parent-child context; phạm vi override rộng hơn mục đích khiến bean ở context cha cũng bị thay và test bỏ qua một lớp tích hợp thật.
Đội muốn test listener @TransactionalEventListener(AFTER_ROLLBACK); exception bị catch bên trong transaction mà không đánh dấu rollback nên listener không chạy như assertion đang mong đợi.
Nhóm xây kiểm thử endpoint trả file lớn qua WebTestClient; test đọc toàn bộ body vào bộ nhớ và không phản ánh cách client production tiêu thụ stream.
Ứng dụng dùng context cache cho nhiều class test data isolation; chỉ một class dùng @DirtiesContext và lịch test order tạo kết quả khác khi class này chạy trước hoặc sau.
Đội phải xác minh việc mở rộng service sang nhiều tenant; test config nạp duy nhất tenant mặc định nên khả năng rò dữ liệu chéo tenant không được kiểm.
Nhóm dùng @Sql script có câu xóa dữ liệu toàn bảng; CI chạy các suite dùng chung database và một suite xóa fixture đang được suite khác kiểm.
Ứng dụng chạy transaction rollback trong testcase nhưng code production phát Kafka event; các message do test phát vẫn được broker nhận và consumer khác xử lý dữ liệu không tồn tại.
Đội lưu test report thành công sau mỗi build; một test chọn profile fake provider và không kiểm provider thật nên việc kết nối production bị hỏng mà pipeline vẫn xanh.
Nhóm muốn chắc chắn suite là deterministic; thời gian thật, dữ liệu random, context cache và executor async vẫn ảnh hưởng nhiều testcase không được kiểm soát.
