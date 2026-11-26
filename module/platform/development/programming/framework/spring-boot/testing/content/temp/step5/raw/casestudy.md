Một dịch vụ Spring Boot tính tổng tiền đơn hàng bằng Java thuần, nhưng unit test JUnit chỉ kiểm tra trường hợp có sản phẩm mà bỏ qua giỏ hàng rỗng và giá âm do dữ liệu lỗi.
Nhóm phát triển viết unit test cho quy tắc áp mã giảm giá, nhưng mỗi lần chạy lại lấy ngày hiện tại từ đồng hồ hệ thống nên kết quả thay đổi đúng thời điểm hết hiệu lực.
Một lớp tính phí vận chuyển nhận tỷ giá qua HTTP client, nhưng unit test vẫn gọi dịch vụ thật khiến bài test thất bại khi đối tác giới hạn số lần truy cập.
Đội dùng Mockito mock repository khi kiểm thử service tạo đơn, nhưng cấu hình stub trả một entity không phản ánh trường hợp database từ chối khóa duy nhất.
Một unit test Mockito xác nhận phương thức lưu được gọi một lần, nhưng không phát hiện giá trị trạng thái đơn bị tính sai trước khi truyền vào repository.
Nhóm xây test cho service đặt hàng có nhiều nhánh lỗi, nhưng mock phụ thuộc được cấu hình quá rộng nên cả trường hợp thiếu quyền vẫn được coi là thành công.
Ứng dụng dùng Mockito spy cho service chứa lời gọi ghi tiền thật, khiến một bài test dự kiến chỉ kiểm tra đối số lại vô tình thực hiện side effect trong môi trường test.
Một lớp xử lý hạn thanh toán dùng static clock trong mã nghiệp vụ, làm JUnit test phụ thuộc thời điểm chạy và thường lỗi khi CI đặt timezone khác laptop.
Nhóm kiểm thử một phép tính BigDecimal bằng so sánh theo độ chính xác không phù hợp, khiến khoản tiền tương đương nhưng khác scale được đánh giá sai.
Service lập hóa đơn trả danh sách các dòng đã sắp xếp, nhưng unit test kiểm tra bằng tập hợp không có thứ tự nên không phát hiện thay đổi ngoài ý muốn ở thứ tự dòng.
Đội lập trình viết test parameterized cho mã trạng thái giao dịch nhưng chỉ dùng các giá trị enum hợp lệ, bỏ sót dữ liệu cũ từ đối tác chứa mã không nhận biết.
Ứng dụng validate địa chỉ người dùng theo nhiều quốc gia, nhưng unit test chỉ đưa dữ liệu tiếng Anh không dấu nên lỗi Unicode và mã bưu chính ở thị trường khác lọt qua.
Một service Spring Boot ném exception tùy biến khi số dư không đủ, nhưng unit test chỉ khẳng định có exception mà không xét mã lỗi nghiệp vụ khách cần nhận.
Nhóm kiểm thử logic retry bằng Mockito verification nhưng không mô phỏng lỗi tạm thời xảy ra ở lần gọi thứ hai, làm sai lệch chính sách số lần thử thực tế.
Một service gọi hai adapter độc lập trong cùng thao tác, nhưng unit test chỉ xác nhận cả hai adapter được gọi mà không nhận ra thứ tự thực hiện làm lộ dữ liệu chưa hợp lệ.
Nhóm tạo fixture hóa đơn chung cho nhiều JUnit test và một test sửa trực tiếp object fixture, khiến các test khác thất bại tùy thứ tự chạy.
Một test chạy độc lập thành công nhưng thất bại khi cả suite chạy song song do các test chia sẻ singleton chứa counter không được reset.
Ứng dụng dùng ThreadLocal để lưu thông tin người yêu cầu, nhưng unit test không xóa ngữ cảnh sau mỗi lần chạy nên test tiếp theo bị coi là cùng người dùng.
Nhóm chuyển JUnit test sang chạy song song, nhưng file tạm được tạo cùng tên cho mọi test và một test xóa file của test khác trước lúc assert.
Một unit test Mockito mock cả lớp DTO và value object đơn giản, khiến test chỉ xác nhận tương tác mà không phát hiện lỗi mapping các trường quan trọng.
Đội thêm tính năng kiểm tra trùng mã đơn, nhưng mock repository mặc định trả dữ liệu rỗng và test không có tình huống tồn tại mã đã dùng.
Một lớp chuyển đổi tiền tệ được kiểm thử với số nguyên, nhưng production dùng số lẻ có nhiều chữ số thập phân và quy tắc làm tròn chưa được xác nhận.
Một test service truyền callback bất đồng bộ tới adapter, nhưng assert được thực hiện trước khi callback chạy nên bài test đôi lúc PASS dù không có kết quả.
Nhóm sử dụng ArgumentCaptor trong unit test để kiểm tra message publish, nhưng chỉ kiểm tra loại event mà không xét correlation ID và tenant ID trong payload.
Ứng dụng có quy tắc nghiệp vụ dựa trên cấu hình feature flag, nhưng unit test sử dụng giá trị mặc định và không thử trường hợp bật tính năng ở production.
Một bộ test Spring Boot gọi @WebMvcTest cho controller đặt hàng, nhưng controller tự tiêm một service ngoài MVC slice nên ApplicationContext không khởi tạo được.
Nhóm dùng @WebMvcTest chỉ để kiểm tra mã HTTP 200 của endpoint tạo tài khoản, nhưng JSON trả về có trường thông tin nhạy cảm mà test không xác minh.
Một controller Spring MVC nhận dữ liệu qua @Valid, nhưng MockMvc test gửi payload hợp lệ duy nhất nên không phát hiện phản hồi thiếu thông tin lỗi cho dữ liệu sai.
Ứng dụng trả HTTP 400 khi request body lỗi cú pháp, nhưng bài test MockMvc chỉ kiểm tra exception trong service và không phát hiện lỗi được ánh xạ thành HTTP 500.
Nhóm viết @WebMvcTest cho endpoint tìm kiếm có tham số phân trang, nhưng chỉ dùng page=0 nên không nhận ra lỗi biên khi offset vượt giới hạn.
Một endpoint Spring MVC trả tệp CSV với tên tiếng Việt, nhưng MockMvc test không xác minh Content-Disposition và người dùng tải xuống tệp có tên sai encoding.
Đội kiểm thử controller REST bằng MockMvc và stub service trả object, nhưng không assert Content-Type nên một bản thay đổi converter trả dữ liệu dưới định dạng ngoài hợp đồng.
Ứng dụng cần trả HTTP 201 kèm Location khi tạo tài nguyên, nhưng test chỉ kiểm tra body và không phát hiện thiếu header cho client tích hợp.
Một controller có hai route gần giống nhau cho phiên bản API cũ và mới, nhưng bài test chỉ gọi một route nên thay đổi mapping làm endpoint cũ trả 404.
Nhóm thêm bộ lọc request ID vào servlet filter chain, nhưng @WebMvcTest không nạp filter như môi trường thật và bài test bỏ sót trường hợp thiếu correlation ID.
Một bộ MockMvc test chạy với Spring Security filter bị tắt cho tiện, khiến endpoint sửa đơn vẫn PASS khi request không có quyền truy cập.
Ứng dụng xử lý chuyển hướng từ HTTP sang HTTPS trong hệ thống proxy, nhưng MockMvc test không gửi các forwarded headers nên URL sinh ra khác môi trường triển khai.
Nhóm dùng MockMvc kiểm tra phản hồi nén và cache headers của endpoint nội dung tĩnh, nhưng cấu hình test không có lớp xử lý tương ứng từ ứng dụng hoàn chỉnh.
Một controller nhận dữ liệu multipart lớn nhưng bài test chỉ gửi file vài byte, khiến giới hạn kích thước upload và mã lỗi không được xác minh.
Ứng dụng trả ProblemDetail cho lỗi nghiệp vụ, nhưng test vẫn kỳ vọng cấu trúc JSON lỗi cũ và không giúp nhóm phân biệt thay đổi hợp đồng với lỗi bất ngờ.
Một API yêu cầu idempotency key trong header, nhưng @WebMvcTest chỉ assert service được gọi và không kiểm tra request thiếu key có bị từ chối đúng hay không.
Nhóm dùng @WebMvcTest với mock phụ thuộc repository để kiểm tra transaction ghi dữ liệu, nhưng slice không khởi chạy tầng persistence nên không tái hiện được rollback.
Một endpoint nhận hai query param có thể xuất hiện nhiều lần, nhưng MockMvc test chỉ kiểm tra một giá trị nên lỗi binding danh sách được đưa lên production.
Ứng dụng sử dụng custom Jackson serializer cho trường tiền tệ, nhưng slice test thay cấu hình JSON mặc định nên response trong test khác cấu hình ứng dụng thực tế.
Một controller giới hạn dữ liệu theo tenant trong service, nhưng @WebMvcTest mock service luôn trả danh sách đúng và không phát hiện nhánh thiếu tenant từ request.
Nhóm kiểm thử một endpoint Spring WebFlux bằng @WebFluxTest, nhưng router function được đăng ký ở cấu hình ngoài slice khiến WebTestClient nhận 404 dù endpoint chạy trên ứng dụng đầy đủ.
Ứng dụng WebFlux trả Flux sự kiện liên tục, nhưng WebTestClient test chờ body hoàn tất nên luôn timeout thay vì kiểm chứng được các phần tử đầu.
Một handler reactive trả Mono thành công khi dữ liệu hợp lệ, nhưng WebTestClient test không thử luồng lỗi nên mapping của exception thành HTTP status bị sai.
Nhóm dùng @WebFluxTest cho WebFlux controller nhưng mock một service trả null thay vì Mono, khiến lỗi chỉ xuất hiện khi publisher được subscribe trong kiểm thử.
Một endpoint WebFlux dùng backpressure khi client nhận dữ liệu chậm, nhưng test chỉ gọi một request nhỏ và không phát hiện buffer tăng khi có nhiều subscriber.
Đội lập trình viết StepVerifier cho một Flux có retry, nhưng dùng giả định thứ tự sự kiện không được đảm bảo và test thất bại ngẫu nhiên trên CI.
Một service reactive có lệnh ghi dữ liệu chỉ thực thi khi subscribe, nhưng unit test tạo Mono rồi không kích hoạt luồng, vẫn cho rằng đã kiểm tra thao tác lưu.
Nhóm kiểm thử timeout của WebClient bằng thời gian ngủ thực trên thread, khiến suite mất nhiều phút và không ổn định khi runner CI thiếu CPU.
Ứng dụng WebFlux truyền Reactor Context chứa tenant ID, nhưng test không cung cấp context tương ứng và chỉ lỗi khi endpoint dùng kiểm tra phân quyền theo luồng.
Một reactive pipeline gọi thư viện JDBC chặn thread, nhưng WebTestClient test chạy trên ít request nên không phát hiện nghẽn event loop trong giờ cao điểm.
Nhóm mock WebClient bằng chuỗi mock fluent API để kiểm thử HTTP adapter, nhưng một thay đổi nhỏ trong cách xây request làm hàng chục test hỏng dù hợp đồng HTTP không đổi.
Một API WebFlux streaming bị client hủy giữa chừng, nhưng test không kiểm tra hành vi hủy và tài nguyên phía sau tiếp tục xử lý dữ liệu không còn người nhận.
Ứng dụng sử dụng Spring Security cho WebFlux, nhưng test dùng cấu hình bảo mật MVC nên kiểm chứng sai thứ tự filter trong luồng reactive.
Đội dùng StepVerifier kiểm tra một Mono có tác động phụ với timeout ảo, nhưng tác vụ được đặt lên scheduler thực khiến test không điều khiển được thời gian như kỳ vọng.
Nhóm tạo test slice @DataJpaTest để xác minh repository lưu đơn, nhưng H2 trong test chấp nhận SQL khác PostgreSQL production nên lỗi chỉ xuất hiện sau deploy.
Một JPA repository dùng native query với toán tử riêng PostgreSQL, nhưng @DataJpaTest chạy trên database nhúng nên test không phản ánh hành vi production.
Ứng dụng cấu hình @DataJpaTest tự rollback sau mỗi test, nhưng nhóm muốn xác minh logic xử lý sau commit và bài test không quan sát được tác vụ này.
Một test repository tạo dữ liệu bằng @Sql nhưng không dọn bảng theo phạm vi phù hợp, khiến test tiếp theo nhận thêm đơn hàng cũ và assert sai số lượng.
Nhóm kiểm thử optimistic locking bằng hai transaction nhưng đều chạy tuần tự trong cùng persistence context, nên không tái hiện được tranh chấp khi cập nhật đồng thời.
Ứng dụng dùng lazy association trong entity, nhưng @DataJpaTest luôn mở transaction khi assert nên không phát hiện lỗi LazyInitializationException ở tầng API thật.
Một repository xóa dữ liệu liên kết qua cascade, nhưng test chỉ đếm entity chính nên bản ghi phụ vẫn còn và làm sai báo cáo sau nhiều tháng.
Nhóm dùng SQL migration Flyway để tạo index, nhưng bài test repository tạo schema tự động thay vì migration thật và không phát hiện index bị thiếu trong production.
Ứng dụng tích hợp Liquibase thay đổi kiểu dữ liệu cột ở bản mới, nhưng @DataJpaTest không kiểm tra nâng cấp từ schema cũ nên lỗi migrate chỉ xuất hiện trên dữ liệu thật.
Một bài test truy vấn JPA chỉ đưa vào vài dòng mẫu và không quan sát số SQL thực thi, khiến N+1 query xuất hiện khi production trả danh sách hàng nghìn đơn.
Nhóm kiểm tra unique constraint bằng entity validation trước khi lưu, nhưng test không flush dữ liệu xuống database nên ràng buộc SQL chưa thực sự được kiểm chứng.
Ứng dụng dùng soft delete cho khách hàng, nhưng test repository chỉ đọc dữ liệu sau khi xóa mà không thử truy vấn có filter dành cho báo cáo pháp lý.
Nhóm có hai datasource trong Spring Boot, nhưng @DataJpaTest nạp nhầm datasource chính nên repository của kho không được thử trên cấu hình kết nối đúng.
Một service cần phân biệt transaction read-only với ghi, nhưng test repository không xác nhận cách xử lý khi database replica từ chối lệnh cập nhật.
Đội kiểm thử dữ liệu có timestamp nhưng JVM và PostgreSQL chạy múi giờ khác; bài test chỉ PASS khi developer dùng cùng timezone với database local.
Ứng dụng dùng JSONB của PostgreSQL để lưu metadata, nhưng database trong @DataJpaTest không có kiểu tương ứng và test không mô phỏng được truy vấn sản xuất.
Nhóm viết @JdbcTest cho truy vấn JDBC đơn giản, nhưng lại kỳ vọng auto-config JPA repository cũng có trong context và test lỗi vì bean không tồn tại.
Một batch writer dùng JdbcTemplate ghi nhiều bản ghi cùng transaction, nhưng bài test chỉ xác nhận câu SQL đầu tiên thành công và bỏ qua trạng thái khi dòng giữa batch lỗi.
Đội kiểm thử repository R2DBC trên PostgreSQL với test JPA truyền thống, khiến hành vi transaction reactive và đường truy cập connection không được bao phủ.
Ứng dụng Spring Boot cần tự cấp khóa định danh theo sequence, nhưng test chạy H2 với chiến lược ID khác production nên hành vi flush và thứ tự insert bị sai.
Nhóm tạo @SpringBootTest cho một hàm xử lý giá đơn giản, khiến mỗi unit test khởi tạo hàng trăm bean và thời gian chạy CI tăng mạnh.
Một integration test dùng @SpringBootTest mặc định rồi kỳ vọng ứng dụng mở cổng HTTP thực, trong khi test client thử kết nối cổng ngẫu nhiên chưa được khởi tạo.
Đội cấu hình @SpringBootTest với RANDOM_PORT cho test API, nhưng test hard-code cổng 8080 và đôi lúc gọi nhầm một service còn chạy trên máy dev.
Ứng dụng khởi động đầy đủ qua @SpringBootTest nhưng cần Kafka và PostgreSQL; CI không cung cấp hạ tầng nên context thất bại trước khi bài test thực thi.
Nhóm dùng @SpringBootTest với cấu hình mock bean khác nhau giữa nhiều lớp, khiến Spring tạo thêm nhiều ApplicationContext riêng và suite chậm đi rõ rệt.
Một suite dùng @DirtiesContext ở tất cả các test để tránh nhiễm trạng thái, làm Spring Boot phải khởi tạo lại context hàng trăm lần và kéo dài pipeline nhiều chục phút.
Nhóm thay đổi property bằng @TestPropertySource ở từng test case thay vì dùng cấu hình chung, khiến context cache bị phân mảnh dù mã nghiệp vụ giống nhau.
Một integration test bật profile production để dùng cấu hình tương tự thực tế, nhưng vô tình khởi tạo scheduler gửi thông báo đến hệ thống bên ngoài.
Ứng dụng @SpringBootTest thực thi @Scheduled job khi context bắt đầu, làm dữ liệu test bị thay đổi trước khi bước xác minh chạy và kết quả không ổn định.
Đội chạy nhiều @SpringBootTest song song trong một JVM và cùng thay đổi cấu hình global static, khiến các test fail ngẫu nhiên do trạng thái chia sẻ.
Một bài test dùng @SpringBootTest với transaction trên thread test nhưng request HTTP chạy trên thread server riêng, khiến dữ liệu được tạo qua API không rollback như kỳ vọng.
Nhóm khởi tạo dữ liệu bằng @BeforeAll dùng chung instance test và sau đó thay đổi qua các test, gây phụ thuộc thứ tự khi JUnit chạy riêng từng phương thức.
Ứng dụng dùng @SpringBootTest kiểm tra cấu hình @ConfigurationProperties nhưng môi trường CI có biến môi trường trùng tên nên giá trị bị ghi đè ngoài ý muốn.
Một integration test sửa system property khi chạy rồi quên khôi phục, khiến test của module khác dùng cấu hình giả và chỉ lỗi khi cả suite chạy.
Đội sử dụng một cơ sở dữ liệu test dùng chung cho nhiều class @SpringBootTest, nhưng dữ liệu từ class trước tồn tại sau commit và làm những assert ở class sau thất bại.
Ứng dụng chạy SpringApplication từ một package test không đúng cấu trúc, nên @SpringBootTest không tìm được cấu hình chính dù service production vẫn khởi động được.
Nhóm nâng Spring Boot làm một auto-configuration bị thay đổi, nhưng integration test chỉ mock toàn bộ phụ thuộc và không phát hiện bean runtime bị mất.
Một test xác nhận serialization trong @SpringBootTest bằng object mapper mặc định thay vì bean trong ApplicationContext, làm kết quả JSON test khác response API thực tế.
Đội chỉ assert context loads trong @SpringBootTest, nhưng không thử request, transaction hay event listener nào nên phần lớn lỗi tích hợp vẫn lọt qua CI.
Một tổ chức muốn chạy contract test dùng full context nhưng mỗi job khởi tạo Kubernetes client thật, làm pipeline yêu cầu quyền cluster không cần thiết cho nội dung test.
Nhóm dùng Testcontainers PostgreSQL để kiểm tra repository, nhưng CI runner không có Docker daemon nên mọi test phụ thuộc container bị bỏ qua trên đường phát hành.
Một @SpringBootTest dùng Testcontainers với PostgreSQL thật, nhưng cấu hình datasource của ứng dụng vẫn trỏ tới H2 test nên bài test PASS mà không chạm container.
Đội dùng @ServiceConnection để nối PostgreSQL container vào Spring Boot, nhưng có nhiều bean kết nối cùng loại và test không rõ datasource nào đang được cấu hình.
Một suite Testcontainers tạo container PostgreSQL mới cho mọi test method, làm thời gian khởi động và cấp cổng tăng khiến CI vượt timeout.
Nhóm dùng PostgreSQL container tái sử dụng giữa nhiều suite nhưng một test thay đổi schema không phục hồi, khiến test sau thất bại dù chạy độc lập PASS.
Đội thiết lập DynamicPropertySource cho Kafka bootstrap servers, nhưng container broker được khởi tạo sau khi property đã được dùng nên consumer test không kết nối được.
Một test Testcontainers bật reusable containers trên máy cá nhân, nhưng CI chạy container mới và phát hiện dữ liệu nền khác với môi trường local.
Nhóm nâng image PostgreSQL trong Testcontainers theo tag không bất biến và migration Flyway mới chỉ thất bại sau khi registry cập nhật image.
Ứng dụng phụ thuộc Redis và PostgreSQL, nhưng test chỉ chạy PostgreSQL container còn cache mock trả hit, nên không phát hiện lỗi serialization của Redis production.
Một test container RabbitMQ tự động khai báo queue khác cấu hình production, khiến bài test listener thành công nhưng routing key trong deployment mới không còn khớp.
Đội thử Kafka producer với container broker nhưng không cấu hình số partition giống môi trường thật, làm lỗi thứ tự sự kiện theo accountId không được phát hiện.
Nhóm chạy nhiều Testcontainers cùng lúc trên runner ít RAM, khiến container bị kill ngẫu nhiên và báo lỗi kết nối khó phân biệt với lỗi ứng dụng.
Một test dùng container cơ sở dữ liệu và gọi API ngoài thật cho bước xác minh thanh toán, khiến mức cô lập của bài test bị phá khi đối tác gặp sự cố.
Ứng dụng dùng một image database nội bộ không có quyền truy cập từ runner CI, khiến suite Testcontainers PASS ở laptop có cache image và FAIL trên runner sạch.
Nhóm cấu hình registry mirror cho Testcontainers ở một môi trường nhưng không giữ bản hash image, khiến kết quả test có thể chạy trên các biến thể image khác nhau.
Một test tạo dữ liệu mẫu khi PostgreSQL chưa hoàn thành khởi động, khiến lần chạy đầu thất bại do kết nối chưa sẵn sàng nhưng lần chạy lại thường thành công.
Đội dùng Testcontainers để khởi động một service phụ trợ có health check chậm, nhưng test chạy trước khi service thực sự sẵn sàng xử lý API nghiệp vụ.
Nhóm kiểm thử Flyway migration trên database mới tạo nhưng không thử nâng cấp từ schema của phiên bản trước, khiến deployment thật bị lỗi khi dữ liệu cũ tồn tại.
Một integration test dùng container database thật nhưng tự tạo bảng bằng Hibernate thay vì migration, nên ràng buộc và index do Flyway định nghĩa không được kiểm tra.
Đội chạy Testcontainers trên Windows và Linux với cấu hình file mount khác nhau, khiến các file init SQL được nạp ở một máy nhưng bị bỏ qua trên máy còn lại.
Một suite dùng container Kafka với topic tự tạo nhưng không dọn state giữa các test, khiến consumer test sau đọc lại event của lần chạy trước.
Nhóm triển khai test chạy trong CI song song và chia sẻ tên network/container cố định, gây xung đột cổng và lẫn dữ liệu giữa hai pipeline.
Ứng dụng xuất dữ liệu vào object storage tương thích S3, nhưng integration test chỉ mock client nên không phát hiện lỗi quyền truy cập và tên bucket ở hạ tầng thật.
Đội dùng Testcontainers cho PostgreSQL và Redis nhưng không đo thời gian khởi động; phần lớn thời lượng CI dành cho dựng hạ tầng thay vì thực thi test.
Nhóm tạo bài test REST client bằng server giả lập nhưng mock trả HTTP 200 cho mọi yêu cầu, làm lỗi mapping response 409 và 429 của đối tác không được phát hiện.
Một dịch vụ dùng WebClient kết nối tới API thanh toán, nhưng integration test không mô phỏng read timeout sau khi server đã chấp nhận request nên bỏ sót nguy cơ retry trùng.
Đội dùng @RestClientTest để kiểm tra JSON mapping cho outbound client, nhưng lại kỳ vọng toàn bộ service nghiệp vụ được auto-config trong slice nên test lỗi context.
Nhóm cập nhật hợp đồng API đối tác để thêm giá trị enum, nhưng bài test contract chỉ kiểm tra một payload tĩnh của phiên bản cũ và consumer mới lỗi khi triển khai.
Ứng dụng có HTTP client thêm OAuth token qua interceptor, nhưng test mock client gọi trực tiếp mapper nên không phát hiện token không được gắn lên request thật.
Đội kiểm tra webhook endpoint bằng dữ liệu JSON đã parse sẵn, nhưng không kiểm chứng HMAC trên raw body và bỏ qua trường hợp proxy thay đổi biểu diễn nội dung.
Một hệ thống gọi REST API qua proxy nội bộ, nhưng test trên laptop dùng kết nối trực tiếp nên không phát hiện timeout và header khác ở môi trường production.
Nhóm phát hành endpoint mới nhưng consumer contract test vẫn kiểm tra thứ tự các trường JSON, gây thất bại dù client hợp lệ không phụ thuộc thứ tự đó.
Ứng dụng chuyển từ HTTP client đồng bộ sang reactive, nhưng bài test cũ chỉ xác nhận phương thức trả publisher mà không kiểm tra request có thật sự được subscribe.
Đội dùng server mock cho API bên ngoài nhưng không xác nhận số lần gọi, khiến chính sách retry vô tình nhân ba lưu lượng vẫn vượt qua kiểm thử.
Nhóm tích hợp sử dụng idempotency key cho POST, nhưng bài test hai lần gọi chỉ kiểm tra mã HTTP chứ không xác minh database và downstream side effect.
Một dịch vụ nhận các API response có trường ngày giờ theo offset, nhưng test contract chỉ dùng UTC và không phát hiện lệch ngày khi đổi múi giờ.
Ứng dụng nhận lỗi kết nối DNS trong môi trường staging, nhưng test adapter chỉ ném HTTP 500 từ mock server nên nhánh xử lý ngoại lệ mạng không được bao phủ.
Nhóm dùng MockRestServiceServer với RestClient nhưng test kỳ vọng cấu hình bean khác bản production, khiến các interceptor, base URL và timeout không được kiểm chứng.
Đội muốn đảm bảo tương thích ngược của public REST API nhưng không lưu các ví dụ request từ mobile version cũ; bản mới từ chối payload vẫn đang được khách sử dụng.
Ứng dụng có hệ thống phân trang REST theo cursor, nhưng test chỉ đưa một trang kết quả nên không phát hiện mất bản ghi khi dữ liệu nguồn thay đổi trong lúc đọc.
Nhóm dùng @JsonTest để kiểm tra serialize DTO nhưng không thử custom Jackson module cho tiền tệ trong context production, gây khác biệt số chữ số thập phân khi trả JSON.
Một RabbitMQ listener trong Spring Boot dùng auto ACK và ghi database, nhưng test chỉ xác nhận handler được gọi mà không thử trường hợp database thất bại trước commit.
Nhóm kiểm thử @RabbitListener bằng cách gọi trực tiếp method Java, nên không phát hiện lỗi queue binding, message converter và acknowledge mode trong cấu hình broker.
Ứng dụng xử lý redelivery từ RabbitMQ khi mất ACK, nhưng test không đưa cùng message ID hai lần nên duplicate side effect trong kế toán lọt tới production.
Đội dùng Testcontainers RabbitMQ để kiểm tra DLQ nhưng chỉ xác nhận message lỗi được ném exception, không xác minh bản tin có đến dead-letter exchange mong muốn.
Nhóm kiểm thử retry của listener nhưng message có schema hỏng luôn được mock thành DTO hợp lệ, khiến lỗi xảy ra trước handler không được kiểm chứng.
Ứng dụng Kafka consumer ghi PostgreSQL rồi commit offset, nhưng test không mô phỏng crash giữa hai bước nên nguy cơ xử lý lại message bị bỏ qua.
Một test @KafkaListener chạy với một partition, nhưng production có nhiều partition và key thay đổi khiến thứ tự event trên cùng orderId không còn được bảo đảm.
Nhóm kiểm thử Kafka producer với mock KafkaTemplate trả thành công, nhưng không phát hiện lỗi broker trả thông tin xác nhận bất đồng bộ sau khi publish.
Ứng dụng cập nhật topic schema Kafka theo phiên bản mới, nhưng test consumer không thử event lịch sử đang tồn trong topic nên lỗi deserialization chỉ phát sinh sau deploy.
Một bài test messaging tạo container broker và publish event thành công, nhưng không đồng bộ với thời điểm listener xử lý nên assert database thất bại ngẫu nhiên.
Đội viết test chờ message bằng Thread.sleep cố định, khiến runner CI chậm gây test fail còn máy dev mạnh thì PASS.
Nhóm kiểm thử DLQ replay sau khi sửa dữ liệu nhưng không xác minh khóa idempotency, khiến bản tin lỗi được xử lý lần hai và gây trùng hóa đơn.
Ứng dụng phát DomainEvent sau transaction commit, nhưng integration test dùng transaction test bao ngoài chưa commit và cho rằng listener không hoạt động.
Nhóm dùng Spring Integration aggregator ghép phản hồi nhưng test luôn cung cấp đủ message, nên không phát hiện group bị giữ mãi khi thiếu một nhánh.
Đội thử một IntegrationFlow bằng gọi service activator trực tiếp, không kiểm tra router, transformer và errorChannel vốn xử lý message trong production.
Ứng dụng truyền correlation ID qua Kafka và RabbitMQ nhưng test chỉ xác nhận payload, khiến trace context thất lạc sau khi đi qua broker.
Một service nhận duplicate webhook rồi publish message, nhưng test không kiểm chứng số lần downstream nhận lệnh nên hệ thống phát cùng event hai lần.
Đội kiểm thử consumer concurrency tăng lên tám thread nhưng sử dụng repository giả lập thread-safe; trên production database gặp lost update chưa được mô phỏng.
Nhóm muốn kiểm tra xử lý lỗi transient của broker nhưng test chỉ tắt container hoàn toàn và bỏ qua trường hợp connection bị reset trong lúc ACK.
Ứng dụng dùng Spring Security để bảo vệ endpoint chuyển tiền, nhưng MockMvc test chỉ gửi người dùng có role ADMIN và không kiểm tra người dùng thiếu quyền.
Một controller có @PreAuthorize dựa trên tenantId, nhưng bài test @WithMockUser không tạo đủ thông tin tenant và test bị pass sai vì service bị mock quá rộng.
Đội kiểm tra CSRF trên endpoint dùng session authentication, nhưng test luôn tắt filter bảo mật nên request thiếu CSRF token vẫn được đánh giá thành công.
Ứng dụng API dùng JWT scopes cho thao tác ghi, nhưng test chỉ xác thực token còn hạn mà không phân biệt token chỉ có quyền đọc.
Nhóm kiểm thử OAuth2 resource server bằng một JWT giả có chữ ký hợp lệ nhưng không thử token sai audience, khiến API chấp nhận token cấp cho ứng dụng khác.
Một endpoint WebFlux có rule authorizeExchange theo đường dẫn, nhưng bài test chỉ dùng security test setup của MVC nên thiếu bao phủ với WebFilterChain thực.
Đội triển khai method security để chặn xem dữ liệu khách khác, nhưng test gọi trực tiếp class không qua Spring proxy nên không xác minh được annotation bảo vệ.
Ứng dụng giới hạn hiển thị hồ sơ theo chủ tài khoản ở tầng repository, nhưng controller test dùng mock trả đúng dữ liệu và bỏ qua trường hợp truy cập ID người khác.
Nhóm kiểm thử các endpoint công khai và quản trị bằng một token quyền cao; những URL Actuator nhạy cảm có thể bị người dùng thường truy cập mà CI không phát hiện.
Một service sử dụng @WithMockUser cho test đơn giản, nhưng logic production phụ thuộc custom AuthenticationPrincipal nên test không phản ánh danh tính thực khi đăng nhập.
Đội test đăng nhập form chỉ kiểm tra HTTP 302 chuyển hướng, không xác minh session fixation hoặc cookie flags mà cổng đăng nhập yêu cầu.
Ứng dụng có cơ chế lock account sau nhiều lần đăng nhập sai, nhưng test không kiểm tra hai request đồng thời nên người dùng có thể vượt giới hạn thử.
Nhóm kiểm tra CORS bằng request từ một origin hợp lệ duy nhất, khiến cấu hình cho phép wildcard kèm credentials bị bỏ qua trong bài test.
Đội thử logout trên API session-based nhưng test không xác minh session cũ bị vô hiệu, khiến token phiên vẫn sử dụng được sau khi người dùng đăng xuất.
Một hệ thống có mTLS ở gateway nhưng test chỉ gửi header X-Client-Cert tự tạo, làm ứng dụng tin dữ liệu có thể bị giả mạo nếu gateway cấu hình sai.
Nhóm cho phép chạy test bảo mật với @TestConfiguration thay thế bean phân quyền, nhưng cấu hình này vô tình được dùng chung trong các integration test khác.
Ứng dụng phân quyền theo nhóm đã cập nhật sau đăng nhập, nhưng test không mô phỏng quyền thay đổi trong một phiên đang mở nên dữ liệu cũ còn được xem.
Đội dùng container PostgreSQL để kiểm tra row-level security nhưng chạy test bằng tài khoản superuser, khiến quy tắc chặn theo tenant bị bỏ qua.
Một API trả lỗi bảo mật với nội dung chi tiết gồm username nội bộ, nhưng MockMvc test chỉ kiểm tra HTTP 403 và không phát hiện rò rỉ thông tin.
Nhóm kiểm thử webhook HMAC với timestamp gần hiện tại nhưng không thử phát lại chữ ký cũ, khiến bản tin bị thu thập trước đó vẫn được chấp nhận.
Đội phát triển chạy toàn bộ test unit và integration trong cùng module mà không phân loại, khiến mỗi thay đổi nhỏ phải chờ container nặng và làm tốc độ phản hồi CI chậm.
Một pipeline Maven chỉ chạy pha test mặc định với Surefire, trong khi các lớp kiểm thử tích hợp đặt tên đuôi IT không được thực thi trước khi phát hành.
Nhóm Gradle sử dụng test filtering theo package nhưng các test bảo mật mới đặt sai package nên pipeline xanh dù chưa chạy các bài kiểm tra quan trọng.
Đội bật JUnit parallel execution để rút thời gian nhưng các test dùng chung cổng HTTP giả lập cố định, làm suite thất bại khi hai class mở server cùng lúc.
Một bài test dùng port mặc định cho mock REST server, khiến runner CI có dịch vụ khác chiếm cổng và test fail ngẫu nhiên không liên quan mã nguồn.
Nhóm đặt thứ tự test bằng tên phương thức để tái sử dụng dữ liệu, làm việc chạy riêng một bài test bằng IDE không có dữ liệu tiền đề và thất bại.
Ứng dụng lưu file fixture vào thư mục src/test/resources rồi test sửa trực tiếp nội dung, khiến workspace sau khi test khác nguồn ban đầu và kết quả build không tái lập.
Đội dùng snapshot assertion cho JSON response chứa thời gian hiện tại và UUID, khiến mỗi lần CI chạy snapshot thay đổi và sinh nhiều bản cập nhật vô nghĩa.
Nhóm tạo dữ liệu test theo số ngẫu nhiên không lưu seed; khi gặp lỗi chỉ xuất hiện một lần trên CI, đội không tái hiện được input đã gây lỗi.
Ứng dụng có test benchmark chạy cùng unit suite trên shared runner, khiến kết quả thời gian phụ thuộc tải CPU của pipeline khác và gây cảnh báo sai về hiệu năng.
Nhóm đặt timeout JUnit quá chặt cho bài test tích hợp container, khiến cùng chức năng PASS trên laptop nhưng fail khi CI cần kéo image lần đầu.
Đội dùng @DirtiesContext để sửa lỗi nhiễm trạng thái mà không tìm nguồn gây nhiễm, làm context cache mất hiệu quả và tăng thời gian pipeline nhiều lần.
Ứng dụng có các test dùng cùng MockWebServer nhưng một test chưa đọc hết response cũ, khiến request tiếp theo trong suite nhận nhầm dữ liệu phản hồi.
Nhóm tắt test không ổn định bằng annotation disabled và quên đặt thời hạn rà soát, khiến một tính năng quan trọng không được kiểm tra trong các bản phát hành sau.
Đội phát triển dùng retry test ở cấp CI để che các lỗi flaky, làm pipeline báo xanh sau lần chạy thứ ba mà không lưu bằng chứng race condition.
Một suite chỉ đo code coverage theo dòng, nhưng các nhánh rollback và phân quyền sai chưa từng được thử dù báo cáo coverage đạt mục tiêu.
Nhóm kiểm tra mutation testing cho logic tính phí nhưng một số test chỉ assert object khác null, khiến nhiều thay đổi sai nghiệp vụ không bị test phát hiện.
Ứng dụng chạy test profile production để đảm bảo tương thích cấu hình nhưng CI vô tình truy cập endpoint email thật và gửi thông báo đến khách hàng.
Đội thiết lập environment variable bí mật cho integration tests nhưng log debug của test in toàn bộ cấu hình kết nối, gây nguy cơ lộ credential trong artifact pipeline.
Nhóm dùng container image theo tag latest cho test database, khiến pipeline sau một tháng chạy với phiên bản khác mà không có thay đổi dependency của ứng dụng.
Một pipeline chạy unit test trước integration test nhưng dựng lại artifact sau khi kiểm thử, khiến file được triển khai không chắc là bản đã vượt qua bộ test.
Đội phát hành Java 21 nhưng CI runner dùng JDK 17 cho test, khiến một phần test bị bỏ qua do không khởi tạo được module và lỗi runtime chỉ xảy ra sau deploy.
Nhóm so sánh thời lượng test qua hai phiên bản Spring Boot nhưng runner có số CPU khác nhau, khiến đánh giá hiệu quả context cache không đáng tin.
Ứng dụng có test chạy trên Windows và Linux nhưng fixture dùng line ending cố định, khiến kiểm tra file CSV sai checksum trên một nền tảng.
Một pipeline test chạy với timezone UTC trong khi ứng dụng vận hành ở múi giờ địa phương, làm các quy tắc ngày đóng sổ không được kiểm chứng đúng thời điểm chuyển ngày.
Nhóm xây pipeline phân luồng fast tests và slow tests nhưng không duy trì danh sách theo thực tế, khiến nhiều @SpringBootTest nặng vẫn chạy ở nhánh nhanh.
Một bộ kiểm thử smoke chỉ xác minh ứng dụng khởi động và endpoint health UP, nhưng broker và database tích hợp không hoạt động nên lệnh nghiệp vụ vẫn thất bại.
Đội thử recovery sau khi broker restart khi queue rỗng, nhưng chưa mô phỏng message unacked đang xử lý nên quy trình production phát sinh duplicate không có trong test.
Nhóm chạy Testcontainers trên CI với tài nguyên nhỏ nhưng không quan sát heap và thời gian khởi động, khiến job thi thoảng bị OOMKilled mà không đủ dữ liệu chẩn đoán.
Một suite test bao gồm cả @WebMvcTest và @SpringBootTest nhưng mỗi class dùng properties khác nhau; số ApplicationContext cần khởi tạo tăng nhanh sau mỗi lần thêm test.
Đội muốn kiểm tra concurrency của job xử lý đơn hàng, nhưng fixture chỉ có một orderId và test chạy tuần tự nên lost update khi nhiều khách cùng đặt không được phát hiện.
Một test load của endpoint WebFlux chỉ dùng client đọc rất nhanh, nên không đánh giá được hành vi khi client chậm làm backpressure và buffer tăng ở production.
Nhóm kiểm thử cơ chế shutdown an toàn trên Spring Boot bằng cách dừng process sau khi không còn request, nhưng không mô phỏng trường hợp response đang streaming.
Ứng dụng có tính năng gửi sự kiện qua outbox, nhưng bài integration test chỉ kiểm tra row outbox được lưu mà không xác minh worker có publish và cập nhật trạng thái thành công.
Đội xây contract test cho hệ thống thanh toán nhưng chạy từ cùng dữ liệu mẫu tự viết với producer, làm thay đổi sai hợp đồng có thể được hai bên chấp nhận mà vẫn thất bại khi dùng client cũ.
Một bản nâng Spring Boot và thư viện test làm annotation mock bean thay đổi, nhưng bộ test không rà lại những mock bị thay thế nên một số bean production thật được khởi tạo ngoài ý muốn.
Nhóm kiểm thử lớp mã hóa dữ liệu với payload nhỏ nhưng không thử giới hạn kích thước lớn ở môi trường container, khiến lỗi bộ nhớ chỉ xuất hiện khi khách tải tệp thực.
Trong một dự án microservice, từng service có test riêng đều PASS nhưng quy trình end-to-end tạo đơn, trừ tồn và gửi email không được kiểm thử khi một bước tạm thất bại.
Đội đánh giá test suite là ổn định vì tất cả test PASS một lần, nhưng không chạy lặp trong chế độ ngẫu nhiên và không nhận ra phụ thuộc thứ tự giữa các class.
Một doanh nghiệp muốn rút thời gian CI bằng cách chạy đồng thời các bài test database, nhưng nhiều suite chia sẻ cùng schema và cleanup của suite này xóa dữ liệu suite khác.
Nhóm gửi sự kiện test tới Kafka chung với môi trường staging mà không tách consumer group và topic, khiến dữ liệu kiểm thử đôi lúc được service thật xử lý.
Đội bật Spring Boot context cache ở JUnit nhưng một extension thay đổi system property giữa các class mà không khôi phục, khiến context được tái sử dụng với cấu hình không còn đúng.
Ứng dụng dùng migration database chạy khi context khởi động, nhưng test fixture được nạp từ bản schema cũ khiến lỗi chỉ xuất hiện sau khi nâng Spring Boot và Flyway.
Nhóm xây bộ test regression API từ log production nhưng chưa ẩn dữ liệu khách hàng, làm thông tin cá nhân đi vào repository test và pipeline CI.
Đội cần kiểm chứng build phát hành sau đổi cấu hình bảo mật nhưng chỉ chạy suite unit mock, không có integration test qua security filter chain thực tế.
Một service mới thêm adapter Redis mà test chỉ dùng fake in-memory map, nên khác biệt TTL, serialization và lỗi reconnect của Redis thật chưa được phát hiện.
Nhóm xây test phát thông báo sau transaction commit nhưng khi chạy @Transactional test không có commit thật, khiến kỳ vọng callback bất đồng bộ không khớp hành vi production.
Một test dùng SpringBootTest để kiểm tra transaction rollback nhưng lại gửi request HTTP lên RANDOM_PORT; test kết thúc và rollback thread test trong khi thread server đã commit.
Một hệ thống kiểm thử các bản ghi có tenantId mà luôn dùng tài khoản quản trị, khiến lỗi đọc chéo tenant không xuất hiện khi chạy bằng tài khoản người dùng thông thường.
Đội xây test đánh giá kết quả API sau nâng version nhưng chỉ assert HTTP status, bỏ qua header deprecation và trường bắt buộc trong response nên phá vỡ client cũ mà không báo đỏ.
Một ứng dụng Spring Boot có endpoint admin chỉ mở trên management port, nhưng test bảo mật chạy duy nhất với port ứng dụng nên không phát hiện chính sách bảo vệ quản trị khác biệt.
Nhóm QA đánh dấu test thành công khi mock broker nhận message nhưng không kiểm tra consumer downstream, khiến quy trình xử lý đơn hàng bị báo hoàn tất sớm.
Một đội vận hành CI phân tích nhiều test fail do runner Windows không truy cập được Docker daemon, nhưng báo cáo gộp chung với lỗi assert nghiệp vụ nên không xác định được môi trường gây lỗi.
