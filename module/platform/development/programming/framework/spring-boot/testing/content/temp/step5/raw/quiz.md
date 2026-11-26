Câu 1. Muốn kiểm thử logic tính phí của service mà không khởi tạo Spring context, cách nào phù hợp?
A. Dùng `@SpringBootTest` để tải toàn bộ context và database.
B. Dùng `@WebMvcTest` để tải controller và MVC infrastructure.
C. Tạo service với Mockito mock dependency rồi chạy JUnit.
D. Dùng `@DataJpaTest` để tải repository và JPA configuration.
Đáp án đúng: C

Câu 2. Trong JUnit Jupiter, annotation nào đánh dấu một phương thức kiểm thử thông thường?
A. Dùng `@BeforeEach` để tạo test method có assertion.
B. Dùng `@AfterEach` để tạo test method sau teardown.
C. Dùng `@Test` để đánh dấu test method cần thực thi.
D. Dùng `@TestFactory` để chạy test method trực tiếp.
Đáp án đúng: C

Câu 3. Khi unit test dùng `@ExtendWith(MockitoExtension.class)`, extension hỗ trợ gì?
A. Khởi động Spring context rồi tìm các bean repository.
B. Tự tạo PostgreSQL container cho mọi phương thức test.
C. Thay HTTP client thật bằng một mock server từ xa.
D. Khởi tạo field `@Mock` và `@InjectMocks` của test.
Đáp án đúng: D

Câu 4. Trong Mockito, `when(client.fetch(id)).thenReturn(value)` thực hiện điều gì?
A. Xác minh lời gọi dependency đã thực sự diễn ra một lần.
B. Bắt buộc Spring tạo bean thật rồi đọc kết quả từ DB.
C. Định nghĩa kết quả giả lập của một lời gọi dependency.
D. Thiết lập HTTP status của response MVC trong test.
Đáp án đúng: C

Câu 5. Lệnh `verify(gateway, times(1)).charge(...)` trong Mockito kiểm tra gì?
A. Kết quả của lời gọi mock đã được commit vào database.
B. Đối tượng mock được gọi đúng một lần với tham số khớp.
C. Giao dịch bên trong mock đã được rollback sau khi test.
D. Đối tượng mock được gọi ở một thread khác với test.
Đáp án đúng: B

Câu 6. Muốn chạy cùng một bài test JUnit với nhiều bộ input và expected output, dùng gì?
A. Kết hợp `@AfterEach` với assertion của input đầu tiên.
B. Kết hợp `@TestInstance` với một lần chạy test method.
C. Kết hợp `@BeforeAll` với một dữ liệu mặc định duy nhất.
D. Dùng `@ParameterizedTest` cùng dữ liệu từ `@CsvSource`.
Đáp án đúng: D

Câu 7. Với JUnit `assertThrows`, giá trị trả về cho phép kiểm tra điều gì?
A. Spring ApplicationContext được hủy sau khi assertion hoàn tất.
B. Exception được ném để xác nhận thêm thông điệp hoặc cause.
C. Mockito mock được tự động reset trước mỗi lần gọi method.
D. HTTP response được nạp lại để kiểm tra JSON body theo schema.
Đáp án đúng: B

Câu 8. `@SpringBootTest` thường được chọn khi cần kiểm thử điều gì?
A. Chỉ khởi tạo MVC controller và mọi collaborator đều bị mock.
B. Nạp context Spring rộng hơn so với các test slice.
C. Chỉ kiểm tra việc serialize JSON mà không tải service.
D. Chỉ chạy Mockito test mà không tải bất kỳ bean Spring nào.
Đáp án đúng: B

Câu 9. Với `@SpringBootTest` trong ứng dụng web, `webEnvironment` mặc định là gì?
A. Chế độ `NONE`, không tạo web application context.
B. Chế độ `DEFINED_PORT`, mở port khai báo trong cấu hình.
C. `MOCK`: tạo web context nhưng không mở HTTP port.
D. Chế độ `RANDOM_PORT`, mở cổng HTTP ngẫu nhiên khi test.
Đáp án đúng: C

Câu 10. Khi dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, có gì khác biệt?
A. Chỉ `MockMvc` được tạo, ứng dụng không mở socket HTTP.
B. Mở web server thực trên port ngẫu nhiên để kiểm thử.
C. Mọi bean khác controller đều bị loại khỏi context test.
D. Spring Data repository bị thay bằng các Mockito mock.
Đáp án đúng: B

Câu 11. `@WebMvcTest(OrderController.class)` phù hợp nhất để kiểm tra điều gì?
A. Consumer offset khi Kafka broker nhận được một message.
B. Chất lượng serialize payload của mọi service trong context.
C. Transaction commit thật của repository trong PostgreSQL.
D. Mapping, validation và response của Spring MVC controller.
Đáp án đúng: D

Câu 12. Trong `@WebMvcTest`, controller phụ thuộc một service không nằm trong slice. Nên làm gì?
A. Thêm Mockito mock bean của service vào test context.
B. Chuyển toàn bộ repository sang embedded database để chạy.
C. Để Spring tự tạo service từ tên field trong controller.
D. Đổi kiểu service thành Java record để bỏ injection.
Đáp án đúng: A

Câu 13. Ưu điểm kỹ thuật của `MockMvc` trong MVC test là gì?
A. Chạy MVC dispatching với request giả, không mở TCP port.
B. Chỉ kiểm thử persistence context mà không tạo request.
C. Chỉ gọi trực tiếp controller method và bỏ mọi MVC filter.
D. Gửi HTTP thật đến server đang chạy ở một port cố định.
Đáp án đúng: A

Câu 14. `@WebFluxTest` chủ yếu dùng để cô lập phần nào khi kiểm thử?
A. Kafka listener container và message routing trên broker.
B. JPA persistence context và SQL transaction thật.
C. Toàn bộ servlet stack MVC cùng HikariCP pool thật.
D. Controller và hạ tầng xử lý web reactive của ứng dụng.
Đáp án đúng: D

Câu 15. `WebTestClient` hỗ trợ kiểm thử một HTTP endpoint theo cách nào?
A. Gửi HTTP request và assert status, header, response body.
B. Chỉ xác minh dependency mock qua `Mockito.verify`.
C. Chỉ theo dõi độ dài `Flux` mà không tạo HTTP request.
D. Chỉ gọi repository qua `EntityManager` rồi so SQL rows.
Đáp án đúng: A

Câu 16. `@DataJpaTest` thường hỗ trợ kịch bản kiểm thử nào?
A. Khởi động mọi Kafka listener cùng broker thật của CI.
B. Chạy trọn ứng dụng cùng web server trên random port.
C. Test JPA repository có rollback transaction mặc định.
D. Khởi động mọi REST controller cùng external HTTP clients.
Đáp án đúng: C

Câu 17. Khi kiểm thử ràng buộc unique của JPA, tại sao đôi khi cần gọi `flush()`?
A. Để Spring vô hiệu hóa transaction rollback của test.
B. Để tất cả cache entry được xóa trước khi truy vấn.
C. Buộc SQL chạy trước khi assert lỗi ràng buộc.
D. Để Mockito chuyển mock repository thành JPA thật.
Đáp án đúng: C

Câu 18. Trong test slice JPA, `@AutoConfigureTestDatabase(replace = NONE)` có mục đích gì?
A. Giữ DataSource cấu hình thay vì thay bằng DB nhúng.
B. Ngăn transaction rollback để dữ liệu luôn tồn tại sau test.
C. Ép tất cả repository được mock dù có database test.
D. Tạo mặc định một PostgreSQL container trước khi test chạy.
Đáp án đúng: A

Câu 19. `@JsonTest` giúp tập trung kiểm thử hành vi nào?
A. Kiểm tra serialize và deserialize dữ liệu JSON.
B. Phân phối message broker và retry của listener đang chạy.
C. Routing HTTP request qua controller và Spring Security.
D. Transaction rollback trong Spring Data repository.
Đáp án đúng: A

Câu 20. Khi kiểm thử HTTP client dùng RestClient/RestTemplate, `@RestClientTest` giúp gì?
A. Tự commit transaction database khi remote trả HTTP 200.
B. Mở web server ứng dụng đầy đủ trên port được định nghĩa.
C. Chạy message listener ở background trong toàn bộ context.
D. Kiểm thử client HTTP với server giả lập trong test.
Đáp án đúng: D

Câu 21. Với `@WithMockUser` trong Spring Security test, điều gì được mô phỏng?
A. Luồng xác thực OAuth2 thật qua identity provider từ xa.
B. Một phiên Redis thật được dùng làm HTTP session của user.
C. Chữ ký JWT thật do authorization server phát hành.
D. Một authentication trong security context của bài test.
Đáp án đúng: D

Câu 22. Nếu CSRF đang được bật, MockMvc test một POST có xác thực thường cần gì?
A. Tắt toàn bộ security filter trong suốt suite test.
B. Chỉ dùng `@WithMockUser` rồi CSRF sẽ tự được sinh.
C. Thêm CSRF token hợp lệ, ví dụ `with(csrf())`.
D. Chỉ thêm header Authorization mà bỏ kiểm tra CSRF.
Đáp án đúng: C

Câu 23. Muốn chạy toàn bộ Spring context nhưng vẫn test MVC qua MockMvc, nên cấu hình gì?
A. Phối hợp Mockito extension và `@WebFluxTest` trên một test.
B. Phối hợp `@JsonTest` và `@RestClientTest` trên một test.
C. Phối hợp `@WebMvcTest` và `@DataJpaTest` trên một test.
D. Phối hợp `@SpringBootTest` và `@AutoConfigureMockMvc`.
Đáp án đúng: D

Câu 24. Vì sao Testcontainers PostgreSQL có thể phát hiện lỗi mà H2 test không thấy?
A. Nó thay JPA repository bằng mock nên test chạy nhanh.
B. Nó tự bỏ qua schema migration để giảm thời gian boot.
C. Nó chỉ chạy SQL parser mà không mở database engine.
D. Nó kiểm tra SQL và hành vi trên PostgreSQL thực tế.
Đáp án đúng: D

Câu 25. Trong Spring Boot test, `@ServiceConnection` với container được hỗ trợ có ích gì?
A. Để Mockito tự mock toàn bộ client truy cập container.
B. Để Boot tạo connection details từ container thử nghiệm.
C. Để container tự ghi dữ liệu vào mọi repository của app.
D. Để Testcontainers tự thay tất cả `@SpringBootTest`.
Đáp án đúng: B

Câu 26. `@DynamicPropertySource` thường được dùng với Testcontainers để làm gì?
A. Cập nhật file `application.yml` khi container kết thúc.
B. Tự tạo Docker image cho từng test method đang chạy.
C. Đăng ký property động từ host hoặc port của container.
D. Chuyển mọi property thành bean `@ConfigurationProperties`.
Đáp án đúng: C

Câu 27. Trong JUnit 5 Testcontainers, `static @Container` thường có vòng đời nào?
A. Dùng chung container cho các test method trong một class.
B. Container được chia sẻ giữa mọi test class trong toàn CI.
C. Container được tạo mới trước mỗi test method của class.
D. Container chỉ chạy sau `@AfterAll` khi suite kết thúc.
Đáp án đúng: A

Câu 28. Muốn kiểm thử `@RabbitListener` nhận và xác nhận message thật, nên chọn cách nào?
A. Chỉ mock `RabbitTemplate` và bỏ phần listener container.
B. Dùng broker test để xác minh message, ack và side effect.
C. Chỉ assert annotation hiện diện mà không gửi message nào.
D. Chỉ đọc cấu hình queue rồi coi listener đã tiêu thụ đúng.
Đáp án đúng: B

Câu 29. Muốn kiểm thử `@KafkaListener` xử lý event thực tế, cần xác minh gì?
A. Publish vào test broker rồi kiểm tra side effect listener.
B. Chỉ kiểm tra method có annotation `@KafkaListener`.
C. Chỉ stub service xử lý rồi coi broker đã commit offset.
D. Chỉ gửi mock HTTP request, không khởi động Kafka broker.
Đáp án đúng: A

Câu 30. Khi kiểm thử xử lý message bất đồng bộ, cách assert nào ổn định hơn?
A. Dùng Awaitility chờ điều kiện trong giới hạn timeout.
B. Tăng thời gian sleep vô hạn cho mọi test trong CI.
C. Đọc kết quả ngay sau publish và không kiểm tra tiến trình.
D. Đợi đúng 100 ms rồi mặc định consumer đã hoàn thành.
Đáp án đúng: A

Câu 31. Để test DB và broker không ảnh hưởng lẫn nhau khi chạy song song, nên làm gì?
A. Thay transaction rollback bằng một connection pool lớn.
B. Dọn dữ liệu, cô lập khóa và namespace theo từng test.
C. Dùng chung message key và database row cho mọi test.
D. Để trạng thái từ test trước tồn tại cho test kế tiếp.
Đáp án đúng: B

Câu 32. Vì sao lạm dụng `@DirtiesContext` có thể làm suite Spring Boot test chậm?
A. Nó tự tắt Testcontainers để giảm tốc độ kết nối DB.
B. Nó làm mất lợi ích context cache và buộc khởi tạo lại.
C. Nó vô hiệu hóa toàn bộ parallel execution của JUnit.
D. Nó khiến mọi mock trả dữ liệu cũ khi chuyển test class.
Đáp án đúng: B
