Bạn giải thích Spring TestContext Framework hỗ trợ kiểm thử ứng dụng Spring bằng những cơ chế nào ngoài các assertion của JUnit?
Bạn phân biệt unit test thuần Java với integration test nạp ApplicationContext theo phạm vi phụ thuộc và loại lỗi có thể phát hiện như thế nào?
Bạn xác định khi nào nên nạp Spring ApplicationContext trong bài test và khi nào nên khởi tạo trực tiếp class cần kiểm thử ra sao?
Bạn mô tả vai trò của TestContextManager trong việc phối hợp vòng đời kiểm thử và các TestExecutionListener như thế nào?
Bạn giải thích SpringExtension kết nối JUnit Jupiter với Spring TestContext Framework qua các callback và parameter resolution như thế nào?
Bạn lựa chọn @ExtendWith(SpringExtension.class) hay các composed annotations của Spring khi xây dựng một lớp integration test ra sao?
Bạn phân biệt @SpringJUnitConfig với việc kết hợp @ExtendWith và @ContextConfiguration theo khả năng khai báo cấu hình như thế nào?
Bạn thiết kế một test dùng @ContextConfiguration để nạp đúng các bean cần thiết mà không khởi tạo toàn bộ ứng dụng như thế nào?
Bạn so sánh nạp cấu hình bằng các @Configuration classes với nạp XML configuration trong Spring TestContext theo trường hợp sử dụng ra sao?
Bạn giải thích vai trò của ContextLoader khi TestContext tạo và chuẩn bị ApplicationContext từ metadata của test như thế nào?
Bạn xác định trường hợp nào cần ApplicationContextInitializer để thay đổi môi trường trước khi context được refresh như thế nào?
Bạn đánh giá rủi ro một initializer thêm state phụ thuộc thời gian khiến hai bài test dùng chung context không còn độc lập ra sao?
Bạn mô tả cách SpringExtension cung cấp ApplicationContext hoặc bean cho test instance thông qua dependency injection như thế nào?
Bạn phân biệt field injection và constructor injection trong test class theo khả năng phát hiện lỗi cấu hình và tính dễ đọc như thế nào?
Bạn sử dụng @TestConstructor để điều chỉnh chế độ autowire constructor của test theo phiên bản Spring đang chạy như thế nào?
Bạn giải thích cách SpringExtension phối hợp với JUnit parameter resolver khi một test method cần bean được inject như thế nào?
Bạn xác định nguyên nhân một test class không inject được bean vì cấu hình context hoặc qualifier sai bằng các bước nào?
Bạn thiết kế quy tắc đặt tên và cấu trúc test packages để nhận đúng configuration classes mà không bị nạp cấu hình ngoài ý định ra sao?
Bạn phân biệt kiểm thử bean wiring với kiểm thử nghiệp vụ của service và xác định assertion phù hợp cho từng mục tiêu như thế nào?
Bạn lựa chọn cách xây dựng một fixture configuration tối thiểu để test Spring component độc lập với database hoặc HTTP server như thế nào?
Bạn giải thích test instance lifecycle của JUnit và lifecycle của singleton bean trong ApplicationContext không đồng nhất như thế nào?
Bạn phân tích vì sao tạo test instance mới cho mỗi method không ngăn được state của một singleton bean bị giữ lại giữa các test ra sao?
Bạn thiết kế test cho bean có trạng thái mutable để phát hiện trường hợp test trước làm thay đổi kết quả test sau như thế nào?
Bạn kiểm tra Spring context có thực sự chỉ nạp các bean dự kiến bằng cách quan sát bean definitions hoặc dependency graph như thế nào?
Bạn phân biệt Spring TestContext với Spring Boot test auto-configuration để không nhầm các tiện ích riêng của Boot thành API lõi của Framework ra sao?
Bạn mô tả cách ApplicationContext được tạo, lưu cache và tái sử dụng qua nhiều test classes trong cùng một JVM như thế nào?
Bạn giải thích mục tiêu của TestContext context caching và những chi phí startup được tiết kiệm khi nhiều test dùng chung cấu hình ra sao?
Bạn xác định những thành phần metadata nào tham gia tạo cache key của ApplicationContext và vì sao profile hoặc property khác sẽ làm mất cache hit như thế nào?
Bạn phân tích tác động của @ContextConfiguration với các configuration classes khác nhau tới số lượng context được nạp ra sao?
Bạn giải thích cách @ActiveProfiles ảnh hưởng tới context cache key khi hai lớp test khai báo profile khác nhau như thế nào?
Bạn đánh giá vì sao thêm một @DynamicPropertySource hoặc bean override có thể làm context không được chia sẻ như dự kiến ra sao?
Bạn thiết kế một bộ test có nhiều test classes dùng cùng cấu hình để tăng tỷ lệ cache hit mà vẫn giữ dữ liệu độc lập như thế nào?
Bạn phân biệt reuse context với reuse trạng thái database và vì sao context caching không đồng nghĩa mọi tài nguyên được tự reset ra sao?
Bạn sử dụng @DirtiesContext khi một bài test làm thay đổi ApplicationContext theo cách không thể khôi phục an toàn như thế nào?
Bạn so sánh các lựa chọn thời điểm dirty context trước hoặc sau method/class khi cần cô lập một bài test phá trạng thái context ra sao?
Bạn phân tích tác động của lạm dụng @DirtiesContext tới thời gian chạy và độ ổn định của toàn bộ test suite như thế nào?
Bạn lựa chọn reset state của một bean hoặc database thay vì đánh dấu dirty toàn bộ context trong tình huống nào?
Bạn xác định vì sao fork JVM hoặc chạy test process riêng có thể khiến static context cache không còn được chia sẻ như thế nào?
Bạn đánh giá tác động của giới hạn cache size và cơ chế eviction khi dự án tạo nhiều cấu hình context khác nhau ra sao?
Bạn sử dụng log thống kê context cache để xác định nguyên nhân integration tests liên tục khởi tạo context mới như thế nào?
Bạn thiết kế chiến lược tối ưu thời gian test bằng cách giảm biến thể cấu hình mà không làm giảm phạm vi kiểm thử như thế nào?
Bạn phân biệt việc context bị đóng do @DirtiesContext với việc một test tự đóng bean hoặc connection làm ảnh hưởng các test dùng cache ra sao?
Bạn xác định rủi ro chạy các test sử dụng context chung song song trong khi một test đánh dấu @DirtiesContext như thế nào?
Bạn thiết kế quy tắc sử dụng @DirtiesContext trong test suite chạy parallel để tránh context bị thu hồi khi test khác còn đang dùng như thế nào?
Bạn giải thích @ContextHierarchy hỗ trợ nạp parent-child contexts trong kiểm thử ứng dụng có nhiều tầng như thế nào?
Bạn kiểm tra việc invalidation một phần context hierarchy ảnh hưởng tới những test có cấu hình parent giống nhau ra sao?
Bạn lựa chọn khai báo @NestedTestConfiguration khi nested JUnit test classes cần kế thừa hoặc tách biệt metadata cấu hình như thế nào?
Bạn phân tích sự khác nhau giữa configuration inheritance và context cache reuse khi test classes kế thừa base class như thế nào?
Bạn mô tả vai trò của @ActiveProfiles trong việc chọn bean và cấu hình dành riêng cho môi trường kiểm thử ra sao?
Bạn thiết kế cấu hình profile test tránh vô tình dùng SMTP server, database hoặc endpoint của production như thế nào?
Bạn phân biệt @TestPropertySource và cấu hình property trong @ContextConfiguration theo mục đích và thời điểm áp dụng ra sao?
Bạn lựa chọn cách đặt inline properties hoặc file properties dành cho test để giảm cấu hình lặp nhưng vẫn dễ truy vết như thế nào?
Bạn xác định độ ưu tiên của test properties khi cùng một key xuất hiện trong nhiều property sources bằng phương pháp kiểm chứng nào?
Bạn sử dụng @DynamicPropertySource khi container database cung cấp port hoặc URL động trong runtime như thế nào?
Bạn phân tích lý do @DynamicPropertySource thường dùng static method và ảnh hưởng đến vòng đời tạo ApplicationContext ra sao?
Bạn thiết kế test với Testcontainers và @DynamicPropertySource để bean DataSource nhận đúng địa chỉ database được cấp động như thế nào?
Bạn xử lý trường hợp dynamic property giữ lại giá trị từ container đã dừng khi context được dùng lại giữa các bài test ra sao?
Bạn phân biệt thiết lập System properties toàn JVM với thêm test property sources riêng cho context theo khả năng cô lập ra sao?
Bạn thiết kế một kiểm thử xác minh bean được tạo từ đúng profile và cấu hình fallback khi biến môi trường thiếu như thế nào?
Bạn đánh giá nguy cơ thay đổi system timezone hoặc locale giữa các test chạy song song và cách cô lập các yếu tố này ra sao?
Bạn kiểm tra một bean dùng @Value có nhận đúng test property khi property placeholder được resolve tại lúc khởi tạo bean như thế nào?
Bạn thiết kế test cho nhiều profile kết hợp để phát hiện bean definitions bị trùng hoặc điều kiện @Profile không khớp ra sao?
Bạn xác định cách thay đổi feature flag theo từng test mà không ép tạo ApplicationContext mới cho mọi test method như thế nào?
Bạn đánh giá khi nào nên đưa thay đổi cấu hình vào đối tượng tham số của service thay vì cấu hình lại context cho từng dữ liệu thử nghiệm như thế nào?
Bạn giải thích TestExecutionListener tham gia vào những mốc vòng đời test để chuẩn bị dependency injection, transaction và cleanup như thế nào?
Bạn phân biệt callback trước test class, chuẩn bị test instance, trước test method và sau test method trong TestContext lifecycle ra sao?
Bạn tổ chức custom TestExecutionListener khi cần chuẩn bị dữ liệu dùng chung cho một nhóm integration tests theo nguyên tắc nào?
Bạn xác định vì sao khai báo @TestExecutionListeners không đúng merge mode có thể làm mất các listener mặc định cần cho dependency injection như thế nào?
Bạn so sánh merge với replace các default TestExecutionListeners về tính tương thích của một cấu hình test tùy biến như thế nào?
Bạn đánh giá rủi ro custom listener sửa ApplicationContext hoặc global state trước khi các listener khác hoạt động ra sao?
Bạn thiết kế custom listener có cleanup đối xứng sau test khi setup thất bại giữa chừng như thế nào?
Bạn chẩn đoán một bean trong test không được inject vì default DependencyInjectionTestExecutionListener không hoạt động bằng cách nào?
Bạn phân biệt vai trò của DependencyInjectionTestExecutionListener với TransactionalTestExecutionListener trong một integration test như thế nào?
Bạn kiểm tra thứ tự các TestExecutionListeners khi một listener dùng dữ liệu phải được chuẩn bị bởi listener khác ra sao?
Bạn lựa chọn cách viết JUnit extension riêng hay TestExecutionListener khi logic chỉ dành cho Spring context hoặc cần hoạt động ở JUnit độc lập như thế nào?
Bạn thiết kế cách thu thập diagnostic information khi context startup thất bại trước khi test method được gọi như thế nào?
Bạn phân tích vì sao lỗi BeanCreationException có thể đến từ cấu hình test thay vì từ code đang được kiểm thử như thế nào?
Bạn xác định những trường hợp nào một integration test bị fail do bean không liên quan trong ApplicationContext và cách thu gọn scope ra sao?
Bạn giải thích test-managed transaction của Spring TestContext Framework khác application-managed transaction theo vị trí tạo và rollback như thế nào?
Bạn mô tả tác dụng của @Transactional trên test method hoặc test class khi có PlatformTransactionManager phù hợp như thế nào?
Bạn phân biệt rollback mặc định của transactional test với hành vi commit transaction trong request production ra sao?
Bạn sử dụng @Commit hoặc @Rollback(false) khi một bài test thực sự cần quan sát dữ liệu đã commit như thế nào?
Bạn đánh giá vì sao chỉ dựa vào test-managed rollback có thể che lấp lỗi constraint xuất hiện lúc transaction flush hoặc commit ra sao?
Bạn thiết kế test gọi EntityManager.flush hoặc JDBC update để phát hiện vi phạm database constraint ngay trong phạm vi kiểm thử như thế nào?
Bạn phân biệt test transaction bao quanh test method với transaction được mở riêng bên trong service có propagation REQUIRES_NEW như thế nào?
Bạn phân tích hệ quả khi service mở REQUIRES_NEW rồi commit thành công nhưng test bao ngoài bị rollback sau method như thế nào?
Bạn xác định những propagation modes nào khiến test-managed transaction không được bắt đầu và cách kiểm tra cấu hình đó ra sao?
Bạn giải thích vì sao transaction ở test thread không tự truyền vào thread của một tác vụ @Async trong code được kiểm thử như thế nào?
Bạn phân tích nguy cơ dùng preemptive timeout chạy test body ở thread khác khiến cập nhật database không nằm trong test-managed transaction như thế nào?
Bạn lựa chọn loại timeout cho integration test có transaction nhằm tránh để test tạo dữ liệu ngoài ý muốn mà rollback không thu hồi được như thế nào?
Bạn sử dụng TestTransaction để kết thúc, bắt đầu hoặc kiểm tra trạng thái test-managed transaction trong một kịch bản cần commit như thế nào?
Bạn thiết kế test verify dữ liệu chỉ được đọc thấy sau commit khi service phụ thuộc isolation của database như thế nào?
Bạn xác định khi nào dùng @BeforeTransaction để chuẩn bị hoặc xác minh dữ liệu ngoài phạm vi transaction kiểm thử ra sao?
Bạn phân biệt @BeforeEach của JUnit với @BeforeTransaction của Spring theo vị trí tương đối so với test-managed transaction như thế nào?
Bạn tổ chức assertions bằng @AfterTransaction khi cần kiểm tra trạng thái database thực sự đã commit hoặc rollback như thế nào?
Bạn xử lý test ghi dữ liệu ở @BeforeAll nhưng test methods dùng rollback để tránh trạng thái nền tồn tại xuyên suốt suite ra sao?
Bạn thiết kế kịch bản test xử lý exception từ service nhưng test transaction vẫn bị đánh dấu rollback-only như thế nào?
Bạn phân tích vì sao giả định mọi @Transactional method sẽ rollback cùng test có thể sai khi code tự tạo thread hoặc dùng transaction manager khác ra sao?
Bạn sử dụng @Sql để chạy script chuẩn bị dữ liệu trước một test và đảm bảo dữ liệu có tính xác định như thế nào?
Bạn phân biệt @Sql scripts chạy theo test transaction và @SqlConfig với transactionMode ISOLATED theo ảnh hưởng tới việc rollback ra sao?
Bạn lựa chọn @Sql cho fixture dữ liệu đơn giản hay builder/service setup cho dữ liệu cần bảo đảm invariant nghiệp vụ như thế nào?
Bạn kiểm tra thứ tự thực thi @Sql và @BeforeEach để tránh assertion dựa trên dữ liệu chưa được chuẩn bị ra sao?
Bạn thiết kế cleanup dữ liệu tạo bởi external worker hoặc HTTP server test khi dữ liệu không thuộc transaction của test thread như thế nào?
Bạn đánh giá rủi ro dùng chung database và truncate tables khi các integration tests đang chạy song song như thế nào?
Bạn xác định trường hợp nào nên dùng database schema riêng, transaction rollback hoặc container riêng để cô lập test data như thế nào?
Bạn giải thích MockMvc cho phép kiểm thử Spring MVC request processing mà không cần khởi động một HTTP server thực như thế nào?
Bạn phân biệt MockMvc với việc mock trực tiếp controller method theo khả năng kiểm tra handler mapping, validation và response conversion ra sao?
Bạn so sánh MockMvcBuilders.standaloneSetup với webAppContextSetup theo mức độ tải Spring configuration và thành phần MVC được sử dụng như thế nào?
Bạn thiết kế một MockMvc standalone test cho controller có @ControllerAdvice và custom argument resolver như thế nào?
Bạn xác định khi nào cần webAppContextSetup để kiểm tra filter chain, message converters và MVC configuration thực tế ra sao?
Bạn sử dụng @WebAppConfiguration với @ContextConfiguration khi cần WebApplicationContext phục vụ MockMvc test thuần Spring Framework như thế nào?
Bạn thiết kế request bằng mockMvc.perform với HTTP method, path variables, query params và JSON body có Content-Type rõ ràng như thế nào?
Bạn phân biệt Content-Type và Accept trong một MockMvc request khi kiểm thử HTTP content negotiation như thế nào?
Bạn kiểm tra HTTP status, response headers và JSON payload bằng ResultMatchers để bảo vệ API contract ra sao?
Bạn thiết kế assertions kiểm tra error response từ @ControllerAdvice khi request có validation error như thế nào?
Bạn phân biệt lỗi binding dữ liệu request với lỗi Bean Validation khi xây dựng các ca kiểm thử controller ra sao?
Bạn xác định cách kiểm tra field-level validation errors mà không phụ thuộc vào toàn bộ nội dung message bản địa hóa như thế nào?
Bạn sử dụng jsonPath hoặc deserialize response thành DTO khi cần kiểm tra một trường lồng trong JSON như thế nào?
Bạn so sánh assert một vài trường bắt buộc với so sánh toàn bộ JSON theo rủi ro test quá chặt vào chi tiết biểu diễn ra sao?
Bạn thiết kế test xác minh controller trả đúng status code khi service báo không tìm thấy dữ liệu hoặc xung đột phiên bản như thế nào?
Bạn kiểm tra endpoint phân trang với sort, page size và metadata tổng số phần tử bằng MockMvc như thế nào?
Bạn xác định cách kiểm thử filter hoặc interceptor sửa request context trước khi controller được gọi như thế nào?
Bạn đánh giá vì sao standaloneSetup có thể bỏ sót security filter hoặc web configuration khiến test pass nhưng production fail ra sao?
Bạn lựa chọn cách đăng ký Spring Security filter chain trong test nếu endpoint bắt buộc phải qua xác thực và phân quyền như thế nào?
Bạn thiết kế test ngăn request chưa xác thực truy cập một resource nhạy cảm qua tầng MVC như thế nào?
Bạn kiểm tra HTTP response khi controller trả redirect, file download hoặc streaming content theo các assertion phù hợp như thế nào?
Bạn sử dụng asyncDispatch của MockMvc để kiểm tra endpoint Spring MVC trả kết quả bất đồng bộ như thế nào?
Bạn phân biệt việc MockMvc báo request bắt đầu async với kết quả cuối cùng của tác vụ khi test DeferredResult hoặc Callable như thế nào?
Bạn thiết kế kiểm thử timeout của một MVC async request mà không dùng Thread.sleep để chờ kết quả như thế nào?
Bạn xác định khi nào cần kiểm tra session, cookie và CSRF trong MockMvc test thay vì chỉ assert JSON body như thế nào?
Bạn dùng MockMvcResultHandlers để lưu bằng chứng chẩn đoán request/response lúc test thất bại mà không in thông tin nhạy cảm ra sao?
Bạn giải thích WebTestClient khác MockMvc ở abstraction kiểm thử và khả năng sử dụng với reactive WebFlux như thế nào?
Bạn phân biệt bindToController, bindToRouterFunction, bindToApplicationContext và bindToServer của WebTestClient theo phạm vi kiểm thử như thế nào?
Bạn xác định lúc nào dùng WebTestClient.bindToServer để kiểm tra HTTP stack thực thay vì bindToApplicationContext ra sao?
Bạn thiết kế WebTestClient test cho WebFlux controller với request JSON và assertions status, headers, body như thế nào?
Bạn phân biệt WebTestClient kết nối thử WebFlux với MockMvcWebTestClient dùng API WebTestClient để kiểm thử Spring MVC như thế nào?
Bạn quyết định khi nào dùng MockMvcWebTestClient thay cho MockMvc mà vẫn muốn kiểm tra servlet-side model hoặc exception handling như thế nào?
Bạn thiết kế kiểm thử functional endpoint WebFlux dùng RouterFunction thông qua WebTestClient như thế nào?
Bạn xác định cách kiểm thử response chứa nhiều phần tử JSON mà không phụ thuộc thứ tự khi contract không yêu cầu ordering như thế nào?
Bạn kiểm tra lỗi reactive pipeline chuyển thành HTTP 4xx hoặc 5xx theo exception handler của WebFlux bằng cách nào?
Bạn thiết kế test streaming response kiểu Server-Sent Events với WebTestClient và kiểm soát thời gian chờ như thế nào?
Bạn sử dụng returnResult cùng StepVerifier khi cần xác minh luồng phản hồi bất đồng bộ nhiều sự kiện như thế nào?
Bạn phân biệt kiểm thử backpressure hoặc cancellation của Publisher với chỉ kiểm tra status và body sau một HTTP exchange ra sao?
Bạn đánh giá ảnh hưởng của responseTimeout khi test reactive stream có thể chưa kết thúc trong thời gian ngắn như thế nào?
Bạn kiểm thử endpoint WebFlux sử dụng SecurityWebFilterChain mà không giả định servlet filters được áp dụng như thế nào?
Bạn kiểm tra request headers, cookies và path variables được WebTestClient gửi theo đúng HTTP contract ra sao?
Bạn quyết định khi nào dùng mock server binding để test nhanh và khi nào cần chạy server thật để bắt lỗi network hoặc serialization ra sao?
Bạn so sánh WebTestClient và MockMvc về test runtime, mức độ mô phỏng và độ phù hợp với blocking MVC hoặc reactive WebFlux như thế nào?
Bạn thiết kế chiến lược dùng chung HTTP contract assertions giữa controller unit tests và integration tests khi lớp HTTP thay đổi như thế nào?
Bạn phân biệt test một repository bằng mock với test dùng DataSource thật theo các lỗi SQL, mapping và transaction có thể phát hiện ra sao?
Bạn sử dụng @Transactional và @Sql để chuẩn bị dữ liệu cho repository integration test nhưng vẫn bảo đảm không phụ thuộc dữ liệu từ test trước như thế nào?
Bạn lựa chọn H2 hay Testcontainers chạy cùng loại database production khi cần xác minh index, dialect và constraint ra sao?
Bạn thiết kế test với Testcontainers và @DynamicPropertySource để kiểm tra service cùng repository kết nối đúng database khởi tạo động như thế nào?
Bạn xác định vì sao test pass trên embedded database nhưng fail trên production database do khác biệt SQL dialect hoặc isolation như thế nào?
Bạn sử dụng JdbcTemplate để xác minh dữ liệu đã thực sự được ghi xuống database thay vì chỉ kiểm tra entity còn trong persistence context như thế nào?
Bạn thiết kế test xác minh transaction rollback qua nhiều repository khi service phát sinh exception ở thao tác cuối ra sao?
Bạn kiểm thử transaction có propagation REQUIRES_NEW mà không cho rằng mọi thay đổi sẽ bị rollback theo transaction ngoài của test như thế nào?
Bạn tổ chức fixture test cho aggregate có quan hệ cha-con và kiểm tra cascade hoặc orphan removal bằng thao tác reload như thế nào?
Bạn thiết kế integration test kiểm chứng optimistic locking bằng hai transaction độc lập và một xung đột version thực như thế nào?
Bạn xác định khi nào nên kiểm tra số lượng SQL phát ra hoặc execution plan để bắt lỗi N+1 mà mock repository không thấy được như thế nào?
Bạn đánh giá cách quản lý migration scripts khi chạy integration tests trên schema thay đổi liên tục như thế nào?
Bạn phân biệt khởi tạo schema bằng migration thật với dùng cơ chế auto-create tables trong test theo khả năng phát hiện lỗi rollout ra sao?
Bạn thiết kế test tránh trùng khóa và dữ liệu ngẫu nhiên không tái lập khi nhiều test cùng dùng một database container như thế nào?
Bạn xác định quy tắc cleanup khi test chạy trên một database cố định có dữ liệu dùng chung với nhà phát triển khác như thế nào?
Bạn lựa chọn test transaction rollback hay cleanup bằng SQL khi ứng dụng tạo dữ liệu từ một thread hoặc process ngoài test như thế nào?
Bạn phân tích khi nào việc reset toàn bộ context để làm sạch database là lựa chọn quá đắt so với cleanup dữ liệu như thế nào?
Bạn sử dụng bean override của Spring TestContext để thay một dependency gọi API ngoài bằng fake hoặc mock trong integration test như thế nào?
Bạn phân biệt fake, stub, mock và spy theo mục tiêu kiểm thử và rủi ro kiểm tra quá nhiều lời gọi nội bộ ra sao?
Bạn lựa chọn @TestBean, @MockitoBean hoặc @MockitoSpyBean theo phiên bản Spring Framework và khả năng hỗ trợ của dự án như thế nào?
Bạn giải thích vì sao bean override trong test có thể làm thay đổi context cache key và giảm reuse giữa các lớp test ra sao?
Bạn thiết kế cách đặt tên hoặc qualifier khi cần thay đúng một bean trong nhiều implementation của cùng interface như thế nào?
Bạn kiểm tra một @MockitoBean thay đúng bean được inject vào service thay vì tạo bean mới không được sử dụng như thế nào?
Bạn phân tích rủi ro mock một repository trong integration test khiến các mapping và transaction thực không được kiểm chứng ra sao?
Bạn quyết định khi nào nên dùng fake implementation tự viết thay vì Mockito để mô phỏng service bên ngoài có state phức tạp như thế nào?
Bạn thiết kế reset mock interactions giữa test methods khi ApplicationContext được cache nhưng bean mock được tái sử dụng như thế nào?
Bạn xác định nguyên nhân test trở nên phụ thuộc thứ tự do spy hoặc mutable fake còn giữ state từ lần chạy trước như thế nào?
Bạn kiểm tra hành vi retry của service bằng stub có thể trả lỗi nhiều lần rồi trả thành công theo kịch bản xác định như thế nào?
Bạn phân biệt verify số lần gọi mock với assert kết quả nghiệp vụ quan sát được để tránh test dễ vỡ khi refactor ra sao?
Bạn thiết kế test đảm bảo adapter HTTP bên ngoài không gọi mạng thật bằng MockRestServiceServer hoặc một fake transport như thế nào?
Bạn quyết định khi nào cần một mock HTTP server thực để kiểm tra cả request serialization và timeout thay vì mock client interface như thế nào?
Bạn phân tích tác động của việc thay bean bằng mock trên các lifecycle callbacks hoặc scheduled tasks khi context khởi động như thế nào?
Bạn xác định cách ngăn scheduled job tự chạy trong lúc test mà không thay đổi hành vi kiểm thử của service chính như thế nào?
Bạn thiết kế kiểm thử service có @Async hoặc application event listener bằng synchronization primitives thay vì Thread.sleep như thế nào?
Bạn lựa chọn CountDownLatch, CompletableFuture hoặc công cụ chờ có điều kiện để kiểm tra kết quả bất đồng bộ một cách xác định ra sao?
Bạn phân biệt flaky test do race condition với test thất bại vì dữ liệu đầu vào không được cố định theo triệu chứng nào?
Bạn kiểm tra một bài test chỉ fail khi chạy cả suite nhưng pass khi chạy riêng bằng cách lần theo global state, cache và thứ tự chạy như thế nào?
Bạn xây dựng quy tắc test không phụ thuộc đồng hồ hệ thống bằng Clock được inject hoặc thời điểm được kiểm soát ra sao?
Bạn đánh giá vì sao random port, UUID hoặc thời gian hiện tại nên được ghi nhận rõ trong thông báo lỗi để có thể tái hiện test như thế nào?
Bạn thiết kế kiểm thử có thể chạy song song mà không dùng chung mutable singleton hoặc cùng một danh tính tài nguyên bên ngoài như thế nào?
Bạn phân tích hậu quả của việc thay đổi static fields hoặc System properties trong một test khi test khác chạy đồng thời như thế nào?
Bạn xác định khi nào nên tắt test parallelism hoặc tách execution pool thay vì cố chạy mọi integration test đồng thời ra sao?
Bạn kiểm tra resource leak sau test như JDBC connection, file handle, HTTP server hoặc background thread bằng phương pháp nào?
Bạn thiết kế cleanup của Testcontainers hoặc mock server khi test thất bại trong setup để không làm kẹt các bài test sau như thế nào?
Bạn xác định cách đo context startup time, cache hit rate và test duration để ưu tiên cải thiện bộ test chậm như thế nào?
Bạn phân tích vì sao tối ưu một test bằng cách mock quá nhiều thành phần có thể làm mất khả năng phát hiện lỗi tích hợp quan trọng ra sao?
Bạn thiết kế chiến lược phân tầng unit, slice và integration tests cho ứng dụng Spring mà vẫn giữ các hợp đồng quan trọng được kiểm tra như thế nào?
Bạn đề xuất cách tổ chức bộ test Spring có SpringExtension, context caching, cấu hình profile, MockMvc/WebTestClient, giao dịch dữ liệu và bean overrides để chạy ổn định trong CI như thế nào?
