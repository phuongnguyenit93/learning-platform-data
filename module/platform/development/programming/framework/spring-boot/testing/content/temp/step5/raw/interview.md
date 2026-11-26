Bạn thiết kế chiến lược kiểm thử cho một dịch vụ Spring Boot mới dựa trên các rủi ro nghiệp vụ nào?
Bạn phân biệt mục tiêu của unit test, integration test, contract test và end-to-end test như thế nào?
Bạn lựa chọn tỷ lệ các lớp kiểm thử dựa trên chi phí thực thi và khả năng phát hiện lỗi ra sao?
Bạn xác định phần logic nào nên kiểm thử bằng JUnit thuần mà không khởi động Spring context?
Bạn đánh giá khi nào việc khởi động toàn bộ Spring Boot context là cần thiết cho một bài test?
Bạn phân biệt kiểm thử hành vi quan sát được với kiểm thử chi tiết triển khai nội bộ như thế nào?
Bạn chọn các trường hợp biên nào khi một service phải xử lý dữ liệu đầu vào không đáng tin?
Bạn xác định mức độ cô lập phù hợp giữa unit test và hạ tầng bên ngoài ra sao?
Bạn thiết kế test case cho một quy tắc nghiệp vụ có nhiều nhánh điều kiện như thế nào?
Bạn sử dụng phân vùng tương đương và giá trị biên để giảm số ca kiểm thử mà vẫn giữ độ phủ như thế nào?
Bạn phân biệt code coverage với khả năng phát hiện lỗi thực tế của bộ kiểm thử ra sao?
Bạn sử dụng mutation testing để đánh giá chất lượng assertion trong unit test như thế nào?
Bạn quyết định phần nào cần kiểm thử contract với dịch vụ bên ngoài thay vì chỉ dùng mock?
Bạn thiết kế dữ liệu test có thể đọc hiểu và ít phụ thuộc vào chi tiết database ra sao?
Bạn tổ chức test theo hành vi thay vì theo tên phương thức để giảm chi phí bảo trì như thế nào?
Bạn đánh giá rủi ro của việc để test phụ thuộc vào thứ tự chạy của test khác ra sao?
Bạn quản lý clock, random seed và UUID generator để test luôn có kết quả ổn định như thế nào?
Bạn thiết kế chiến lược kiểm thử các lỗi hiếm gặp mà production từng gặp như thế nào?
Bạn lựa chọn những bất biến nghiệp vụ quan trọng cần có regression test sau mỗi bản vá ra sao?
Bạn đo thời gian chạy, độ ổn định và mức phát hiện lỗi của test suite theo cách nào?
Bạn tổ chức test source set và dependency kiểm thử trong Maven hoặc Gradle cho dự án Spring Boot như thế nào?
Bạn phân biệt các nhiệm vụ của spring-boot-starter-test với việc tự chọn từng thư viện test ra sao?
Bạn giải thích vòng đời của một bài kiểm thử JUnit Jupiter từ khởi tạo đối tượng đến teardown như thế nào?
Bạn lựa chọn @BeforeEach và @BeforeAll để chuẩn bị dữ liệu theo phạm vi nào?
Bạn quản lý tài nguyên dùng chung trong @AfterEach và @AfterAll để test không rò trạng thái ra sao?
Bạn phân biệt lifecycle PER_METHOD và PER_CLASS khi chạy JUnit Jupiter như thế nào?
Bạn dùng @DisplayName và tên test để thể hiện một hành vi nghiệp vụ rõ ràng ra sao?
Bạn xây dựng assertion cho giá trị trả về, exception và thay đổi trạng thái như thế nào?
Bạn lựa chọn assertThrows để kiểm chứng loại exception và nội dung lỗi theo mức ổn định nào?
Bạn xử lý trường hợp kiểm thử exception nhưng code không chạy tới nhánh cần kiểm tra như thế nào?
Bạn dùng assertAll để báo cáo nhiều điều kiện không phụ thuộc cùng lúc như thế nào?
Bạn phân biệt assertEquals với so sánh theo thuộc tính hoặc recursive comparison của object như thế nào?
Bạn quyết định khi nào nên viết custom assertion thay vì lặp nhiều phép so sánh trong các test?
Bạn sử dụng @ParameterizedTest với @ValueSource hoặc @CsvSource cho nhóm dữ liệu nào?
Bạn xây dựng @MethodSource cho các trường hợp kiểm thử có cấu trúc phức tạp như thế nào?
Bạn thiết kế test dữ liệu Unicode, null, giá trị rỗng và chuỗi dài với parameterized tests ra sao?
Bạn sử dụng @Nested để tổ chức các trạng thái và điều kiện tiền đề mà không tạo phụ thuộc thứ tự như thế nào?
Bạn lựa chọn @Tag để phân tách slow tests và fast tests trong pipeline như thế nào?
Bạn dùng assumptions để bỏ qua ca test chỉ hợp lệ trên một môi trường xác định như thế nào?
Bạn phân biệt disabled test với test bị skip do assumption không thỏa điều kiện ra sao?
Bạn thiết kế dynamic tests khi tập dữ liệu được tạo trong runtime mà vẫn dễ chẩn đoán thất bại như thế nào?
Bạn đặt timeout cho một test JUnit để ngăn pipeline treo nhưng vẫn có bằng chứng lỗi ra sao?
Bạn đánh giá rủi ro khi chạy test song song với các biến static hoặc singleton có thể thay đổi như thế nào?
Bạn kiểm soát thứ tự thời gian trong test mà không phụ thuộc Thread.sleep như thế nào?
Bạn quyết định dùng temporary directory do JUnit quản lý để kiểm thử file I/O ra sao?
Bạn kiểm tra quá trình teardown thực sự giải phóng file handle và socket như thế nào?
Bạn đánh giá khi nào cần custom JUnit extension thay vì lặp setup logic giữa nhiều lớp test?
Bạn kết hợp reporting của JUnit với log và trace của ứng dụng để phân tích test thất bại ra sao?
Bạn thiết kế cách gom test failures theo nguyên nhân gốc thay vì chỉ nhìn số lượng test đỏ như thế nào?
Bạn phân biệt mock, stub, spy và fake khi thay thế một dependency trong unit test ra sao?
Bạn sử dụng @Mock và @InjectMocks để kiểm thử service thuần Java mà không khởi động Spring như thế nào?
Bạn lựa chọn constructor injection giúp test phụ thuộc được kiểm soát tốt hơn field injection ra sao?
Bạn dùng MockitoExtension trong JUnit Jupiter để quản lý mock lifecycle như thế nào?
Bạn xác định khi nào cần stub một phương thức bằng when/thenReturn và khi nào nên để mặc định?
Bạn phân biệt when(...).thenReturn(...) với doReturn(...).when(...) khi làm việc với spy như thế nào?
Bạn thiết kế stub cho các nhánh lỗi như timeout, exception và giá trị trả về bất thường ra sao?
Bạn dùng ArgumentCaptor để kiểm tra dữ liệu thực sự truyền cho một gateway như thế nào?
Bạn lựa chọn verify, never và times để kiểm chứng side effect mà không khóa chặt thứ tự nội bộ ra sao?
Bạn sử dụng InOrder khi thứ tự gọi hai dependency là yêu cầu nghiệp vụ thực sự như thế nào?
Bạn đánh giá rủi ro của verifyNoMoreInteractions khi implementation thay đổi nhưng hành vi không đổi ra sao?
Bạn xử lý strict stubbing phát hiện stub dư thừa trong một unit test như thế nào?
Bạn lựa chọn Answer hoặc callback giả lập trong Mockito để mô phỏng hành vi phụ thuộc vào input ra sao?
Bạn xác định tình huống một mock trả null mặc định làm test xanh giả tạo như thế nào?
Bạn xây dựng fake repository trong bộ nhớ khi cần hành vi lưu trữ thay vì hàng loạt Mockito stubs như thế nào?
Bạn phân biệt mock repository với dùng database thật khi kiểm tra transaction và SQL ra sao?
Bạn thiết kế cách tránh mock những value objects hoặc DTO thuần dữ liệu như thế nào?
Bạn đánh giá sự khác nhau giữa kiểm thử service method và kiểm thử qua public API của đối tượng ra sao?
Bạn làm thế nào để không lạm dụng partial mocking khiến test phụ thuộc quá sâu vào implementation?
Bạn kiểm thử service gọi external client trả Mono hoặc Flux mà không block trong production code như thế nào?
Bạn sử dụng StepVerifier để kiểm tra publisher do service sinh ra khi dependency được mock ra sao?
Bạn xác minh service không gọi lại một gateway khi validation thất bại như thế nào?
Bạn thiết kế unit test idempotency khi cùng request ID được xử lý nhiều lần ra sao?
Bạn mô phỏng hai lời gọi gateway liên tiếp trả kết quả khác nhau mà vẫn giữ test dễ hiểu như thế nào?
Bạn xử lý Mockito exception khi stubbing một phương thức final hoặc static trên bộ công cụ đang dùng như thế nào?
Bạn đánh giá khi nào mockStatic phù hợp và khi nào nên refactor dependency tĩnh thành interface dễ test?
Bạn kiểm tra một spy gọi phương thức thật gây tác dụng phụ ngoài ý muốn bằng cách nào?
Bạn lựa chọn tạo object thật trong unit test thay vì mock cả một chuỗi collaborators theo tiêu chí nào?
Bạn thiết kế assertion tránh chỉ verify mock mà không kiểm chứng kết quả nghiệp vụ ra sao?
Bạn giảm sự trùng lặp giữa nhiều unit test dùng cùng mock setup nhưng kiểm tra các kịch bản khác nhau như thế nào?
Bạn phân biệt việc dùng @Mock của Mockito với mock bean nằm trong Spring ApplicationContext như thế nào?
Bạn xác định trường hợp cần thay một bean trong Spring test bằng cơ chế Mockito bean override phù hợp phiên bản ra sao?
Bạn đánh giá tác động của việc thay bean bằng mock tới độ tin cậy của integration test như thế nào?
Vì sao một Spring context test thường tốn nhiều thời gian khởi động hơn unit test thuần Java?
Bạn mô tả vai trò của TestContext framework khi Spring chuẩn bị dependency injection cho test ra sao?
Bạn sử dụng @SpringBootTest để khởi tạo application context trong một bài kiểm thử tích hợp như thế nào?
Bạn phân biệt @SpringBootTest với @ContextConfiguration về phạm vi bootstrapping ra sao?
Bạn lựa chọn webEnvironment MOCK, RANDOM_PORT, DEFINED_PORT hoặc NONE dựa trên yêu cầu test nào?
Bạn xác định trường hợp RANDOM_PORT cần HTTP client thật để kiểm thử network stack như thế nào?
Bạn sử dụng @LocalServerPort để lấy địa chỉ server chạy ở random port theo điều kiện nào?
Bạn phân biệt MockMvc gọi qua mock servlet environment với gọi HTTP đến server thật như thế nào?
Bạn kiểm thử Spring Boot application startup thành công mà không kiểm tra quá nhiều implementation details ra sao?
Bạn sử dụng @ActiveProfiles để áp cấu hình test và tránh phụ thuộc profile của máy phát triển như thế nào?
Bạn quyết định dùng @TestPropertySource hoặc properties của @SpringBootTest cho override nào?
Bạn thiết kế @DynamicPropertySource để cấp host, port và credentials do Testcontainers tạo ra ra sao?
Bạn kiểm tra thứ tự ưu tiên của test properties khi cấu hình ở nhiều nguồn khác nhau như thế nào?
Bạn đánh giá khi nào nên dùng @Import cho bean cấu hình test thay vì component scan toàn bộ ra sao?
Bạn tạo @TestConfiguration để thay adapter bên ngoài bằng fake có kiểm soát như thế nào?
Bạn tránh để bean của @TestConfiguration lọt vào production application context như thế nào?
Bạn kiểm thử điều kiện @ConditionalOnProperty hoặc @Profile khi tính năng bật/tắt theo cấu hình ra sao?
Bạn thiết kế test xác nhận bean tùy chọn không tồn tại khi một dependency chưa được cấu hình như thế nào?
Bạn sử dụng ApplicationContextRunner để kiểm tra auto-configuration mà không khởi động cả ứng dụng ra sao?
Bạn dùng @DirtiesContext trong trường hợp nào và vì sao không nên lạm dụng?
Bạn xác định cách Spring cache và tái sử dụng Test ApplicationContext giữa các lớp test như thế nào?
Bạn đánh giá các khác biệt về profile, properties hoặc mock bean làm cache context bị phân mảnh ra sao?
Bạn kiểm tra tình huống test thay đổi singleton state khiến một test khác thất bại dù context được cache như thế nào?
Bạn thiết kế chiến lược reset dữ liệu giữa test mà không bắt buộc tạo lại toàn bộ context ra sao?
Bạn xử lý test thất bại do duplicate bean definition hoặc vòng lặp dependency khi startup ra sao?
Bạn phân biệt kiểm thử cấu hình runtime theo environment với kiểm thử behavior của service trong Spring context như thế nào?
Bạn quyết định tách các lớp test nhiều cấu hình thành bộ nhóm nào để giảm startup overhead ra sao?
Bạn sử dụng test slice trong Spring Boot để giới hạn bean được tạo theo tầng ứng dụng như thế nào?
Bạn giải thích mục tiêu của @WebMvcTest và ranh giới bean nó thường nạp vào context như thế nào?
Bạn xây dựng @WebMvcTest cho một controller có dependency service cần được mock ra sao?
Bạn xác định trường hợp @WebMvcTest thất bại vì thiếu bean filter, converter hoặc security config như thế nào?
Bạn kết hợp @AutoConfigureMockMvc với @SpringBootTest khi muốn kiểm thử nhiều tầng mà không mở port thật ra sao?
Bạn phân biệt @WebFluxTest với @WebMvcTest khi ứng dụng dùng reactive HTTP stack như thế nào?
Bạn sử dụng @JsonTest để kiểm tra Jackson serialization và deserialization có cấu hình phù hợp ra sao?
Bạn lựa chọn @DataJpaTest để kiểm tra repository, mapping và truy vấn thay vì service nghiệp vụ như thế nào?
Bạn xác định khi nào @JdbcTest phù hợp với JDBC template hoặc custom DAO ra sao?
Bạn quyết định có dùng @DataR2dbcTest khi persistence là reactive theo điều kiện nào?
Bạn lựa chọn @RestClientTest để kiểm tra client HTTP ở phạm vi slice như thế nào?
Bạn xác minh phạm vi auto-configuration thực sự được nạp trong một test slice cụ thể bằng cách nào?
Bạn sử dụng @Import để bổ sung một bean thực sự cần thiết vào slice mà không mở rộng quá nhiều context ra sao?
Bạn nhận biết sai lầm khi giả định @WebMvcTest tự động nạp mọi @Service và @Repository như thế nào?
Bạn phân biệt mock service trong controller slice với gọi database thật trong @SpringBootTest ra sao?
Trong những tình huống nào test slice có thể bỏ sót lỗi liên kết giữa các tầng ứng dụng?
Bạn tổ chức một số full-context integration tests để bù cho giới hạn của các slice tests ra sao?
Bạn thiết kế ma trận loại test và phạm vi bean để tránh có nhiều test trùng một hành vi ra sao?
Bạn xây dựng kiểm thử MVC controller dùng MockMvc mà không cần start embedded server như thế nào?
Bạn kiểm tra request mapping, path variable và query parameter trong một endpoint REST bằng MockMvc ra sao?
Bạn xác minh HTTP status, response headers và JSON body bằng assertion nào mà ít phụ thuộc thứ tự trường?
Bạn kiểm tra validation với @Valid và binding errors cho một request DTO như thế nào?
Bạn xử lý ca kiểm thử khi input JSON sai kiểu dữ liệu khiến deserialization thất bại ra sao?
Bạn thiết kế test phân biệt 400, 404, 409 và 500 theo exception handling của controller như thế nào?
Bạn sử dụng @ControllerAdvice để chuẩn hóa error response và kiểm thử các trường bắt buộc ra sao?
Bạn kiểm tra content negotiation qua Accept và Content-Type trong MVC endpoint như thế nào?
Bạn kiểm thử multipart upload với file rỗng, file lớn và MIME type không phù hợp như thế nào?
Bạn kiểm chứng endpoint download trả filename, media type và nội dung đúng ra sao?
Bạn xác minh một endpoint POST dùng idempotency key không tạo bản ghi trùng khi gọi lại như thế nào?
Bạn phân biệt MockMvc standalone setup với Spring context-based setup khi test controller ra sao?
Bạn sử dụng MockMvc request post processors để gắn user hoặc security context theo nhu cầu test như thế nào?
Bạn kiểm tra cấu hình servlet filter có ảnh hưởng tới request trong MockMvc test ra sao?
Bạn xác nhận CORS và preflight request theo cấu hình bảo mật hiện hành như thế nào?
Bạn kiểm tra cách controller trả lỗi khi JSON body vượt giới hạn được cấu hình ở tầng HTTP ra sao?
Bạn xây dựng kiểm thử phân trang và sắp xếp endpoint mà không phụ thuộc dữ liệu có sẵn trong máy phát triển như thế nào?
Bạn kiểm tra ETag, If-None-Match hoặc cache-control trong API theo hợp đồng nào?
Bạn xác minh endpoint tạo tài nguyên trả Location header nhất quán với ID mới ra sao?
Bạn kiểm thử @RequestParam mặc định và tham số bắt buộc khi client không gửi đủ dữ liệu như thế nào?
Bạn phân biệt assertion chỉ kiểm một JSON field với kiểm toàn bộ response contract khi nào?
Bạn dùng JSONPath để kiểm tra mảng kết quả và các phần tử không có thứ tự ổn định như thế nào?
Bạn kiểm thử controller có phương thức async và đòi hỏi async dispatch trong MockMvc ra sao?
Bạn đánh giá khi nào cần test HTTP bằng server thật để phát hiện khác biệt container, network hoặc serialization ra sao?
Bạn thiết kế kiểm thử WebFlux handler bằng WebTestClient theo kịch bản request/response như thế nào?
Bạn phân biệt WebTestClient bindToController, bindToApplicationContext và bindToServer ra sao?
Bạn lựa chọn @WebFluxTest cho một annotated controller thay vì full SpringBootTest dựa trên tiêu chí nào?
Bạn kiểm chứng status, headers và body của endpoint reactive mà không gọi block trong handler như thế nào?
Bạn xử lý kiểm thử một Flux streaming response khi số phần tử không xác định trước như thế nào?
Bạn sử dụng StepVerifier để xác minh thứ tự onNext, onError và onComplete của một publisher ra sao?
Bạn kiểm tra cancellation có dừng tác vụ upstream và giải phóng tài nguyên trong reactive pipeline như thế nào?
Bạn dùng virtual time trong StepVerifier để kiểm thử delay, retry và timeout mà không chờ thời gian thực ra sao?
Bạn phân biệt retry được kiểm thử bằng virtual time với retry cần xác minh qua network integration test ra sao?
Bạn kiểm tra Context propagation trong reactive flow khi chuyển scheduler như thế nào?
Bạn phát hiện blocking I/O trên event loop trong bài test bằng các công cụ hoặc dấu hiệu nào?
Bạn thiết kế test backpressure khi producer phát dữ liệu nhanh hơn subscriber yêu cầu ra sao?
Bạn kiểm chứng operator flatMap có concurrency limit không làm quá số lời gọi downstream mong đợi như thế nào?
Bạn kiểm thử WebFlux error mapping khi một Mono thất bại sau khi đã bắt đầu xử lý request ra sao?
Bạn kiểm tra một SSE endpoint phát event liên tục mà không khiến test chạy vô hạn như thế nào?
Bạn xác minh request bị hủy giữa chừng không tiếp tục phát dữ liệu nhạy cảm hoặc giữ connection ra sao?
Bạn mô phỏng timeout của WebClient dùng mock HTTP server thật để kiểm tra behavior như thế nào?
Bạn xác định khi nào cần TestPublisher để chủ động điều khiển tín hiệu của publisher trong unit test?
Bạn đánh giá rủi ro test reactive dùng block vô tội vạ và che giấu lỗi trong runtime như thế nào?
Bạn so sánh kiểm thử controller MVC và WebFlux khi cùng cung cấp một REST contract như thế nào?
Bạn xây dựng repository test với @DataJpaTest và kiểm tra mapping entity sang bảng dữ liệu ra sao?
Bạn sử dụng TestEntityManager hoặc EntityManager để thiết lập dữ liệu và kiểm tra hành vi JPA như thế nào?
Bạn phân biệt lưu entity trong persistence context với dữ liệu đã được flush xuống database như thế nào?
Bạn chủ động flush và clear persistence context để phát hiện lỗi SQL hoặc mapping trong test như thế nào?
Bạn thiết kế test cho unique constraint, foreign key và nullable columns trên database thật ra sao?
Bạn xác minh query repository với filter, pagination và sorting trong nhiều bộ dữ liệu như thế nào?
Bạn kiểm tra optimistic locking khi hai transaction đồng thời cập nhật cùng một entity như thế nào?
Bạn tạo tình huống deadlock hoặc lock timeout để kiểm thử chính sách retry ở tầng service ra sao?
Bạn phân biệt transaction được rollback sau @DataJpaTest với transaction trong production như thế nào?
Bạn xác định khi nào test chạy rollback mặc định làm che khuất lỗi xảy ra lúc commit ra sao?
Bạn thiết kế test cho @Transactional service khi một phương thức nội bộ cùng bean không đi qua proxy như thế nào?
Bạn kiểm tra lệnh gọi external service không bị giữ trong database transaction quá lâu bằng cơ chế nào?
Bạn chọn dùng PostgreSQL thật thay cho H2 để kiểm tra native SQL và dialect behavior khi nào?
Vì sao H2 compatibility mode không thể mô phỏng hoàn toàn hành vi PostgreSQL hoặc MySQL trong integration tests?
Bạn lựa chọn @AutoConfigureTestDatabase để kiểm soát có thay DataSource bằng embedded database hay không như thế nào?
Bạn cấu hình Flyway hoặc Liquibase migration trong integration test để dùng đúng schema production ra sao?
Bạn kiểm tra tính tương thích của migration khi database đã có dữ liệu cũ bằng cách nào?
Bạn thiết kế cách reset dữ liệu bằng transaction rollback, TRUNCATE hoặc container mới theo điều kiện nào?
Bạn đánh giá nguy cơ test chỉ chạy được nhờ thứ tự các migration hoặc trạng thái database có sẵn ra sao?
Bạn kiểm tra lỗi lazy loading chỉ xuất hiện khi entity đã detached khỏi persistence context như thế nào?
Bạn xây dựng test phòng ngừa N+1 query trong một endpoint truy xuất danh sách ra sao?
Bạn xác minh chính sách cache của JPA không làm test đọc dữ liệu cũ sau một update ra sao?
Bạn thiết kế kiểm thử R2DBC transaction và reactive repository không dựa trên giả định thread-bound transaction như thế nào?
Bạn kiểm tra cấu hình database pool bị cạn khi chạy nhiều integration test song song ra sao?
Bạn kiểm chứng idempotent insert khi hai worker cùng xử lý một event ID bằng database constraint như thế nào?
Bạn đánh giá dữ liệu test chứa timestamp theo timezone có thể sai ở database khác môi trường như thế nào?
Bạn dùng Testcontainers để kiểm thử với PostgreSQL, Redis hoặc message broker thực thay vì mock ra sao?
Bạn xác định trường hợp Testcontainers mang lại độ tin cậy cao hơn embedded database hoặc in-memory fake như thế nào?
Bạn thiết kế lifecycle container ở mức method, class hoặc test suite để cân bằng cô lập và tốc độ ra sao?
Bạn phân biệt Testcontainers @Container lifecycle với việc khởi động container thủ công như thế nào?
Bạn cấu hình JDBC URL và cổng được map động từ Testcontainers mà không hardcode localhost port ra sao?
Bạn sử dụng @DynamicPropertySource để truyền thông tin kết nối từ container tới Spring context như thế nào?
Bạn xác định khi nào dùng @ServiceConnection của Spring Boot tùy phiên bản để tự cấu hình connection details ra sao?
Bạn quản lý sự khác nhau giữa Testcontainers dùng JDBC và Testcontainers dùng R2DBC như thế nào?
Bạn chờ container thực sự sẵn sàng bằng health hoặc wait strategy thay vì sleep cố định ra sao?
Bạn kiểm tra container startup failure để phân biệt thiếu Docker daemon và lỗi cấu hình application như thế nào?
Bạn bảo đảm container và dữ liệu test không được chia sẻ ngoài ý muốn giữa các test chạy song song ra sao?
Bạn sử dụng network alias khi nhiều Testcontainers cần gọi trực tiếp nhau theo hostname nội bộ như thế nào?
Bạn đánh giá chi phí khởi động container Redis so với PostgreSQL trong test suite lớn như thế nào?
Bạn xử lý migrations và dữ liệu seed sau khi container database sẵn sàng như thế nào?
Bạn kiểm tra phiên bản container image được ghim để tránh thay đổi test không báo trước ra sao?
Bạn lựa chọn dùng image digest hoặc tag phiên bản cụ thể cho integration tests theo chính sách nào?
Bạn xác định khi nào bật reusable containers ở môi trường local nhưng không nên dùng trong CI cô lập ra sao?
Bạn xử lý vấn đề test CI không có quyền truy cập Docker socket bằng giải pháp nào?
Bạn cấu hình Testcontainers trên môi trường CI có network policy hoặc registry nội bộ như thế nào?
Bạn kiểm thử failover hoặc restart một container để đo khả năng reconnect của Spring Boot client ra sao?
Bạn đánh giá giới hạn của một container đơn lẻ khi muốn kiểm thử cluster hoặc high availability ra sao?
Bạn thiết kế bài test Redis cache TTL và eviction trong môi trường container thật như thế nào?
Bạn kiểm tra connection pool không rò rỉ khi test liên tục tạo và đóng Spring context ra sao?
Bạn thu thập container logs khi bài integration test thất bại để hỗ trợ chẩn đoán như thế nào?
Bạn lựa chọn phần nào phải chạy với hạ tầng thực trong CI và phần nào có thể để mock nhằm giữ thời gian hợp lý ra sao?
Bạn kiểm thử một @RabbitListener với RabbitMQ Testcontainer để xác minh routing và acknowledgment như thế nào?
Bạn kiểm tra một message được producer publish vào exchange phù hợp và consumer nhận đúng payload ra sao?
Bạn thiết kế test xử lý duplicate delivery khi consumer commit database nhưng chưa ack message như thế nào?
Bạn mô phỏng poison message để xác minh retry policy và dead-letter routing ra sao?
Bạn kiểm tra DLQ nhận được metadata lỗi cần thiết để replay mà không lộ secret như thế nào?
Bạn lựa chọn kỹ thuật chờ completion bất đồng bộ trong messaging test thay cho Thread.sleep ra sao?
Bạn kiểm thử Kafka producer và consumer với broker Testcontainer để xác minh serializer và key ra sao?
Bạn kiểm tra offset commit trong Kafka consumer khi downstream transaction thất bại như thế nào?
Bạn xác minh thứ tự xử lý theo partition key khi nhiều Kafka consumers chạy song song ra sao?
Bạn phân biệt test listener bằng mock broker client và test với broker thực về các lỗi có thể phát hiện như thế nào?
Bạn thiết kế integration test transactional outbox gồm database và broker để tìm lỗi publish lặp như thế nào?
Bạn xác định cách dọn queue, topic và consumer group giữa các lần test để tránh dữ liệu cũ ra sao?
Bạn mô phỏng broker mất kết nối giữa quá trình publish để kiểm tra retry và publisher confirmation như thế nào?
Bạn kiểm thử message schema versioning khi producer và consumer sử dụng hai phiên bản DTO ra sao?
Bạn kiểm tra Spring Integration flow có router và transformer mà không cần kết nối broker thật như thế nào?
Bạn sử dụng test channel hoặc message collector để quan sát kết quả của một IntegrationFlow ra sao?
Bạn kiểm thử gateway timeout và error channel khi handler downstream không phản hồi như thế nào?
Bạn đánh giá khi nào một integration test nên xác minh trạng thái cuối thay vì số lần listener được gọi ra sao?
Bạn kiểm tra tính idempotent của nghiệp vụ khi test gửi cùng message nhiều lần và song song ra sao?
Bạn thiết kế bài test cho scheduled job hoặc poller không phụ thuộc đồng hồ hệ thống như thế nào?
Bạn kiểm thử cache invalidation sau message processing mà không giả định xử lý bất đồng bộ tức thì như thế nào?
Bạn mô phỏng downstream broker chậm để tìm điểm nghẽn connection pool và thread executor ra sao?
Bạn dùng Spring Security Test để kiểm tra authentication và authorization trong MVC hoặc WebFlux như thế nào?
Bạn thiết kế test phân biệt 401 Unauthorized và 403 Forbidden cho API được bảo vệ ra sao?
Bạn sử dụng @WithMockUser trong trường hợp nào và hạn chế của việc giả lập security context là gì?
Bạn kiểm chứng role hierarchy hoặc method security bằng security test phù hợp như thế nào?
Bạn kiểm thử @PreAuthorize trên service khi lời gọi đi qua proxy thật của Spring ra sao?
Bạn xác định test nào cần JWT token thật được ký bởi issuer thử nghiệm thay vì mock principal?
Bạn xây dựng test OAuth2 resource server với claims khác nhau để kiểm tra mapping authorities như thế nào?
Bạn kiểm tra CSRF protection khi có endpoint thay đổi trạng thái trong ứng dụng dùng session như thế nào?
Bạn thiết kế test CORS cho preflight request và origin không được cho phép ra sao?
Bạn kiểm thử endpoint từ chối truy cập khi người dùng đoán ID tài nguyên thuộc tenant khác như thế nào?
Bạn xác minh dữ liệu nhiều tenant được lọc đúng ở repository và service thay vì chỉ controller ra sao?
Bạn thiết kế negative test cho endpoint Actuator nhạy cảm không được mở công khai ra sao?
Bạn kiểm tra authentication filter không bỏ qua URL có path encoding bất thường như thế nào?
Bạn đánh giá những nguy cơ khi test chỉ dùng @WithMockUser mà không kiểm tra token validation và filter chain ra sao?
Bạn kiểm thử WebFlux SecurityContext propagation qua reactive pipeline như thế nào?
Bạn xác minh secrets không xuất hiện trong lỗi API và log test khi xác thực thất bại ra sao?
Bạn kiểm thử policy giới hạn request rate với clock điều khiển được như thế nào?
Bạn kiểm tra mật khẩu được mã hóa thay vì lưu dạng rõ khi test workflow đăng ký tài khoản ra sao?
Bạn tổ chức security regression test sau khi cập nhật Spring Security hoặc filter configuration như thế nào?
Bạn kiểm thử endpoint health công khai nhưng endpoint quản trị ghi log level phải yêu cầu quyền như thế nào?
Bạn sử dụng @RestClientTest để kiểm tra DTO conversion, header và xử lý lỗi của HTTP client ra sao?
Bạn lựa chọn MockRestServiceServer cho RestClient hoặc RestTemplate trong trường hợp nào?
Bạn kiểm thử WebClient qua server HTTP giả lập khi cần xác minh kết nối và truyền request thực như thế nào?
Bạn dùng WireMock hoặc MockWebServer để mô phỏng upstream trả 429, timeout và 5xx ra sao?
Bạn thiết kế test Retry-After và exponential backoff mà không khiến CI phải chờ lâu như thế nào?
Bạn xác minh HTTP client không tự retry POST thiếu idempotency key sau lỗi kết nối ra sao?
Bạn kiểm tra circuit breaker chuyển trạng thái sau chuỗi lỗi bằng test nào?
Bạn mô phỏng upstream trả payload JSON sai schema để kiểm tra error handling của adapter như thế nào?
Bạn kiểm tra HTTP client không gửi Authorization header khi redirect sang origin khác như thế nào?
Bạn thiết kế consumer-driven contract tests để giảm lỗi thay đổi schema giữa các microservice ra sao?
Bạn phân biệt kiểm thử OpenAPI schema với kiểm thử hành vi nghiệp vụ thực của endpoint như thế nào?
Bạn xác định khi nào cần một end-to-end test chạy qua gateway, database và broker thay vì nhiều integration tests nhỏ?
Bạn xây dựng test cho workflow có side effects bên ngoài mà không gọi hệ thống thanh toán production ra sao?
Bạn tổ chức fake server để kiểm tra webhook signature, retry và duplicate webhook như thế nào?
Bạn kiểm tra trace ID và correlation ID được truyền giữa các thành phần trong một integration test ra sao?
Bạn đánh giá cách xác định số lượng external API calls tối đa mà một request được phép thực hiện như thế nào?
Bạn thiết kế cách kiểm thử graceful shutdown khi còn request hoặc message đang xử lý như thế nào?
Bạn quyết định tách load test khỏi JUnit suite thông thường dựa trên những yêu cầu đo hiệu năng nào?
Bạn đo startup time của Spring context và tổng thời gian test theo nhóm bằng phương pháp nào?
Bạn phân biệt nguyên nhân context cache miss với thời gian thật sự của test method như thế nào?
Bạn đánh giá tác động của @DirtiesContext lên thời gian CI khi nhiều test classes sử dụng chung cấu hình ra sao?
Bạn sắp xếp test suites để tận dụng context cache mà không tạo phụ thuộc giữa các test như thế nào?
Bạn hạn chế số tổ hợp @ActiveProfiles và test properties để giảm số context phải khởi tạo ra sao?
Bạn quyết định khi nào nên thay full-context tests bằng slice tests hoặc unit tests dựa trên thời gian nào?
Bạn tối ưu dữ liệu seed trong database integration tests để không phải insert hàng triệu bản ghi ra sao?
Bạn đánh giá việc dùng container chung ở cấp suite có thể giảm thời gian nhưng tăng nguy cơ rò trạng thái như thế nào?
Bạn lựa chọn mức song song của JUnit khi database pool và Docker resources có giới hạn ra sao?
Bạn kiểm soát random port và tên queue/topic để test chạy song song không xung đột như thế nào?
Bạn phát hiện flaky test bằng số lần rerun và bằng chứng lỗi theo điều kiện nào?
Bạn phân biệt test không ổn định do race condition với test phụ thuộc thời gian hoặc mạng như thế nào?
Bạn thiết kế retry test ở CI để thu thập bằng chứng mà không che giấu lỗi thật ra sao?
Bạn tạo báo cáo test theo JUnit XML và artifact logs để dễ đối chiếu test thất bại như thế nào?
Bạn cấu hình build tách unit, slice, integration và end-to-end suites để đưa vào những quality gates nào?
Bạn xác định các test nào phải chạy trên pull request và test nào chỉ chạy trước release theo rủi ro nào?
Bạn kiểm soát version JDK, Spring Boot, database image và Testcontainers trong CI để tránh sai khác ra sao?
Bạn đo hiệu quả build cache và dependency cache mà không tái sử dụng test outputs sai như thế nào?
Bạn xử lý tình huống CI runner không có đủ RAM để khởi động đồng thời PostgreSQL và Kafka containers ra sao?
Bạn thu thập test coverage và mutation score mà không dùng một con số duy nhất thay cho đánh giá chất lượng ra sao?
Bạn ngăn dữ liệu test hoặc credential dùng trong CI bị đưa vào log và artifact công khai như thế nào?
Bạn thiết kế cơ chế quarantine test lỗi ngẫu nhiên có thời hạn và trách nhiệm khắc phục ra sao?
Bạn đánh giá kết quả test trên nhiều JDK hoặc hệ điều hành khi thư viện có native dependencies như thế nào?
Bạn lập kế hoạch cải thiện test suite quá chậm nhưng vẫn giữ những kiểm tra hồi quy quan trọng như thế nào?
Nếu @SpringBootTest báo Failed to load ApplicationContext, bạn sẽ phân biệt lỗi cấu hình, bean và dependency như thế nào?
Nếu một unit test dùng Mockito chạy xanh nhưng endpoint thật trả sai status, bạn sẽ bổ sung lớp kiểm thử nào?
Nếu @WebMvcTest thất bại vì thiếu service bean, bạn sẽ chọn mock bean hoặc mở rộng slice theo tiêu chí nào?
Nếu test Maven chạy xanh trên máy cá nhân nhưng hỏng trên CI sạch, bạn sẽ kiểm tra cache, profile và biến môi trường ra sao?
Nếu @DataJpaTest chạy xanh với H2 nhưng lỗi SQL trên PostgreSQL production, bạn sẽ tái cấu trúc integration test như thế nào?
Nếu repository test vô tình trả kết quả từ persistence context mà SQL thực tế sai, bạn sẽ dùng flush và clear ra sao?
Nếu một bài test transactional rollback che mất lỗi xảy ra ở commit, bạn sẽ thay đổi cách thiết lập giao dịch như thế nào?
Nếu Testcontainers không khởi động được vì CI thiếu Docker socket, bạn sẽ phân biệt lỗi hạ tầng với lỗi ứng dụng ra sao?
Nếu hai integration tests song song cùng ghi vào một queue, bạn sẽ cô lập routing và dữ liệu như thế nào?
Nếu test Kafka listener đôi lúc thất bại vì consumer chưa subscribe xong, bạn sẽ đồng bộ điều kiện sẵn sàng ra sao?
Nếu một WebFlux test đôi khi treo khi StepVerifier chờ onComplete, bạn sẽ kiểm tra cancellation và timeout như thế nào?
Nếu Mockito verify thất bại vì thêm một lời gọi logging không liên quan, bạn sẽ cải thiện assertion như thế nào?
Nếu security test dùng @WithMockUser xanh nhưng JWT production bị từ chối, bạn sẽ kiểm tra bộ lọc token bằng cách nào?
Nếu context cache bị mất hiệu quả sau khi mỗi test khai báo properties khác nhau, bạn sẽ nhóm lại test configurations ra sao?
Nếu test chỉ thất bại khi chạy chung suite nhưng chạy riêng luôn xanh, bạn sẽ truy tìm shared state và thứ tự chạy như thế nào?
Nếu một service test phụ thuộc Thread.sleep nên lúc pass lúc fail, bạn sẽ thay bằng điều kiện quan sát được như thế nào?
Nếu container image được nâng version làm test fail dù code không đổi, bạn sẽ đối chiếu schema và image digest ra sao?
Nếu CI chạy quá chậm vì mỗi test class tạo một PostgreSQL container mới, bạn sẽ cân bằng lifecycle và isolation như thế nào?
Nếu một test kiểm thử duplicate event vẫn tạo hai bản ghi, bạn sẽ xác minh transaction và unique constraint như thế nào?
Nếu controller test trả HTTP 200 nhưng dữ liệu không commit xuống database, bạn sẽ bổ sung integration assertion gì?
Nếu test timeout tăng cao khi nhiều HTTP mock server cùng chạy, bạn sẽ phân tích thread, port và connection pool ra sao?
Nếu lỗi chỉ xuất hiện trên JDK mới và một plugin test đã cũ, bạn sẽ thu thập bằng chứng tương thích như thế nào?
Nếu bộ kiểm thử đạt coverage cao nhưng lỗi nghiệp vụ vẫn lọt production, bạn sẽ đánh giá mutation testing và test design ra sao?
Nếu integration test làm lộ API key vào log CI, bạn sẽ xử lý secret và sửa test fixture theo quy trình nào?
Bạn thiết kế runbook phục hồi pipeline Spring Boot Testing khi context khởi động lỗi, Testcontainers không kết nối và flaky tests tăng đồng thời như thế nào?
