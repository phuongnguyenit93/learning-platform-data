Một nhóm xây ứng dụng Spring Boot quản lý kho chỉ thêm thư viện spring-web mà không có web server runtime, khiến tiến trình không mở cổng HTTP và endpoint kiểm tra tồn không thể tiếp nhận request.
Một dịch vụ đặt hàng thêm starter web và thấy nhiều bean MVC tự xuất hiện, khiến đội phát triển không hiểu thành phần nào đến từ starter và thành phần nào do ứng dụng khai báo.
Một nhóm xây REST API tự thêm nhiều dependency Spring riêng lẻ, nhưng phiên bản không đồng bộ khiến ứng dụng lỗi khi khởi tạo JSON converter sau lần nâng cấp thư viện.
Một ứng dụng sử dụng parent POM Spring Boot nhưng đồng thời cố định phiên bản thư viện HTTP thấp hơn bộ dependency management, khiến lỗi liên kết phương thức chỉ xuất hiện khi chạy thật.
Một dự án Gradle chuyển sang Spring Boot plugin mới nhưng chưa thống nhất Java toolchain, khiến bản build thành công ở máy lập trình mà không chạy được trên JVM của máy chủ.
Một hệ thống kế toán thêm cả starter servlet và reactive do hai nhóm cùng chỉnh dependency, khiến cách Spring Boot xác định loại ứng dụng web khác dự kiến của nhóm tích hợp.
Một ứng dụng xử lý file chạy theo lịch không cần HTTP, nhưng vẫn kéo starter web vào bản triển khai nên khởi động web server và mở cổng mạng ngoài nhu cầu.
Một đội tạo dự án bằng Spring Initializr và thêm nhiều starter một lúc, nhưng không phân biệt dependency dùng lúc test với dependency runtime nên artifact chứa thư viện thử nghiệm.
Một dịch vụ gửi email sử dụng starter mail nhưng không cấu hình địa chỉ máy chủ, khiến lỗi chỉ xuất hiện khi chức năng gửi thư được gọi lần đầu.
Một nhóm tạo API Spring Boot nhưng thiếu starter validation, khiến các annotation ràng buộc dữ liệu đầu vào không được thực thi như bài kiểm thử của nhóm kỳ vọng.
Một dự án phân tích dữ liệu bổ sung starter JPA để dùng một tiện ích nhỏ, nhưng Spring Boot bắt đầu dò cấu hình DataSource dù ứng dụng chưa có cơ sở dữ liệu.
Một doanh nghiệp nâng version Spring Boot trong một dịch vụ còn dùng các API servlet cũ, khiến một số lớp và annotation không còn tương thích sau thay đổi hệ sinh thái.
Một nhóm muốn giảm kích thước ứng dụng nhưng xóa dependency bắc cầu tùy tiện, khiến bean được tạo trong môi trường IDE biến mất khi chạy bản jar tối giản.
Một dự án multi-module đặt class ứng dụng chính trong package chỉ chứa controller, khiến các component ở module nghiệp vụ không được tìm thấy trong quá trình component scan.
Một đội chuyển ứng dụng Spring Framework cũ sang Spring Boot nhưng giữ cả cấu hình XML và Java config, khiến một số bean được đăng ký trùng và startup báo xung đột.
Một dịch vụ thêm starter monitoring để quan sát hoạt động, nhưng số bean cùng các endpoint quản trị thay đổi khiến nhóm bảo mật phải đánh giá lại bề mặt truy cập.
Một ứng dụng dùng Maven profile dành cho production để loại thư viện phát triển, nhưng cách đóng gói lại vô tình bỏ cả driver database cần thiết lúc chạy.
Một nhóm chạy Spring Boot bằng lệnh của IDE thành công, nhưng artifact do pipeline CI tạo không chứa resource cấu hình nên ứng dụng không tìm thấy template email.
Một ứng dụng cần chạy trên container có ít bộ nhớ nhưng dùng toàn bộ starter từ nền tảng chung, khiến thời gian startup và memory footprint cao dù nghiệp vụ đơn giản.
Một nhóm thay đổi BOM quản lý phiên bản mà không sửa mã nguồn, khiến các starter kéo theo implementation mới và thời gian khởi động của dịch vụ tăng rõ rệt.
Một ứng dụng Spring Boot đặt class chính ở package không phải cha của các service, khiến controller vẫn được nạp theo import riêng nhưng service được inject lại không tồn tại.
Một nhóm khai báo @SpringBootApplication trong lớp dùng cho thử nghiệm, khiến khi chạy production các test helper bị component scan và xuất hiện bean giả không mong muốn.
Một dịch vụ khởi động bằng SpringApplication nhưng lập trình viên nghĩ method main chỉ gọi controller, khiến việc khởi tạo ApplicationContext và các bean được dùng chung bị bỏ qua trong sơ đồ hệ thống.
Một hệ thống quản lý sản phẩm có hai class đánh dấu cấu hình ứng dụng chính, khiến các cách chạy khác nhau trong IDE chọn tập component và cấu hình không giống nhau.
Một đội đưa @Component lên lớp tiện ích thuần không có state nhưng lớp lại phụ thuộc bean phức tạp, khiến lúc startup một chức năng không sử dụng vẫn làm ứng dụng thất bại.
Một ứng dụng chỉ cần xử lý lệnh CLI nhưng lại chạy theo kiểu web, khiến tiến trình không kết thúc sau khi tác vụ hoàn tất và lịch chạy trong hệ điều hành bị treo.
Một nhóm cố tạo thủ công ApplicationContext mới trong một service, khiến bean lấy từ context phụ có cấu hình và lifecycle khác bean do Spring Boot quản lý.
Một ứng dụng dùng @ComponentScan mở rộng tới package của thư viện thứ ba, khiến các cấu hình thử nghiệm của thư viện cũng được nạp và thay đổi cách chọn bean.
Một hệ thống có lớp @Configuration import module nghiệp vụ, nhưng đường import gây hai định nghĩa bean cùng tên và Spring Boot từ chối khởi tạo context.
Một service có bean phụ thuộc vào thông tin kết nối external API, nhưng constructor tự gọi API ngay khi Spring tạo bean nên lỗi mạng tạm thời chặn toàn bộ startup.
Một ứng dụng đăng ký CommandLineRunner để nạp dữ liệu mặc định, nhưng tác vụ này chạy ở mỗi lần khởi động và ghi trùng dữ liệu sau khi container được restart.
Một dịch vụ có hai ApplicationRunner cùng cần khởi tạo tham chiếu, nhưng thứ tự thực thi không được xác định theo phụ thuộc nghiệp vụ và job thứ hai đôi khi dùng dữ liệu cũ.
Một ứng dụng quản trị dùng startup event để mở kết nối tới hệ thống ngoài, nhưng một listener chặn lâu làm thời gian sẵn sàng nhận request tăng bất thường.
Một nhóm đặt logic xử lý đơn hàng vào constructor của controller, khiến lỗi dữ liệu ở một đơn cũ ngăn toàn bộ ứng dụng web khởi động.
Một hệ thống khởi động thành công nhưng không thấy thông báo ứng dụng đã sẵn sàng như mong đợi, khiến đội trực không phân biệt lỗi tạo context với lỗi ở các runner hậu khởi tạo.
Một ứng dụng bắt đầu nhận request trong lúc một tác vụ nạp cache vẫn chạy ngoài luồng, khiến khách truy vấn nhận dữ liệu thiếu dù Spring Boot đã báo startup hoàn tất.
Một nhóm đặt bean truy cập dữ liệu dưới @Repository nhưng exception từ JDBC vẫn bị xử lý không nhất quán giữa các đường gọi, khiến đội khó phân biệt lỗi nguồn và lỗi chuyển đổi.
Một ứng dụng định nghĩa service bằng @Service nhưng khai báo constructor có hai dependency cùng interface, khiến Spring không xác định được ứng viên phù hợp để inject.
Một controller tạo trực tiếp instance service bằng toán tử new thay vì dùng bean, khiến các dependency và cơ chế xử lý do container quản lý không được áp dụng cho instance đó.
Một hệ thống có hai bean PaymentGateway từ hai nhà cung cấp, nhưng việc thêm provider mới làm constructor injection trước đây hoạt động giờ báo không có bean duy nhất.
Một ứng dụng dùng @Qualifier theo tên bean cụ thể, nhưng sau lần refactor đổi tên phương thức tạo bean, đường tiêm dependency không còn khớp cấu hình.
Một nhóm gắn @Primary cho client mặc định nhằm phục vụ đa số request, nhưng một tác vụ kế toán vẫn cần provider khác và đang nhận nhầm client chính.
Một dịch vụ dùng field injection cho nhiều dependency, khiến các bài kiểm thử không tạo Spring context khó cung cấp mock và kiểm tra đơn vị nghiệp vụ.
Một lớp @Configuration có phương thức @Bean trả về interface tổng quát, nhưng cấu hình khác cần tiêm implementation cụ thể và không nhận thấy bean như kỳ vọng.
Một ứng dụng đăng ký bean kết nối bằng @Bean nhưng quên một property khởi tạo, khiến việc tiêm dependency thành công còn lỗi chỉ phát sinh khi gửi request đầu tiên.
Một dự án tạo hai bean cùng tên qua nhiều module khác nhau, khiến context không khởi động dù hai đối tượng thuộc các loại nghiệp vụ riêng biệt.
Một service chứa tham chiếu tới một bean optional nhưng constructor luôn yêu cầu bean này, khiến profile chỉ tắt chức năng phụ lại làm cả service không thể khởi tạo.
Một nhóm gắn @Lazy cho dependency nhằm giảm startup time, nhưng lỗi credentials chỉ xuất hiện khi khách đầu tiên gọi endpoint sử dụng client đó.
Một ứng dụng có vòng phụ thuộc giữa OrderService và PaymentService qua constructor, khiến quá trình tạo bean bị chặn ngay cả khi từng service biên dịch hợp lệ.
Một hệ thống dùng setter injection để tránh vòng dependency nhưng state chưa hoàn chỉnh trong giai đoạn khởi tạo, khiến callback lifecycle truy cập bean trước khi thuộc tính được gắn.
Một service được đánh dấu singleton và lưu mã khách hiện tại vào field, khiến request đồng thời có thể nhận thông tin của người dùng khác.
Một controller có bean prototype được tiêm trực tiếp vào singleton tại lúc tạo, khiến nhóm tưởng có instance mới mỗi request nhưng state được tái sử dụng lâu hơn mong đợi.
Một nhóm gắn @RequestScope cho bean chứa dữ liệu người gọi, nhưng truy cập bean đó từ tác vụ background không có HTTP request hiện hành và phát sinh lỗi scope.
Một ứng dụng lưu thông tin đăng nhập trong bean session scope, nhưng khi người dùng mở nhiều tab cùng phiên thông tin của thao tác trước ảnh hưởng câu hỏi ở tab sau.
Một service dùng bean singleton để chứa bộ đếm mutable không đồng bộ, khiến số lượt xử lý ghi nhận thấp hơn thực tế khi lượng request tăng.
Một ứng dụng đưa dữ liệu cấu hình bất biến vào bean prototype, khiến mỗi lần tra cứu lại tạo instance không cần thiết và làm việc theo dõi vòng đời phức tạp hơn.
Một nhóm kỳ vọng Spring sẽ tự gọi callback hủy của mọi prototype bean, nhưng tài nguyên được các instance này mở vẫn còn sau khi không còn được sử dụng.
Một service dùng lookup một dependency theo tên bean bằng ApplicationContext, nhưng sau khi tái cấu trúc đổi tên bean việc thực thi mới lỗi thay vì fail ở bước inject.
Một hệ thống cần một implementation ở production và một mock ở test, nhưng cả hai cấu hình cùng được import vào context và tạo ra sự mơ hồ khi lựa chọn bean.
Một ứng dụng gắn @PostConstruct để tải toàn bộ dữ liệu vào cache, khiến quá trình khởi tạo bean kéo dài đến mức readiness probe liên tục thất bại.
Một bean phát sự kiện dùng @PreDestroy để giải phóng kết nối, nhưng khi container bị dừng cưỡng bức không đủ thời gian cleanup nên một số message chưa gửi bị mất.
Một ứng dụng để hai bean phụ thuộc nhau qua callback init thay vì dependency khai báo, khiến thứ tự khởi tạo thực tế khác giả định và một bean đọc dữ liệu chưa sẵn sàng.
Một service tạo thread thủ công trong constructor rồi dùng các dependency được inject sau đó, khiến tác vụ nền đôi lúc bắt đầu với trạng thái chưa hoàn chỉnh.
Một nhóm dùng @EventListener cho sự kiện ứng dụng nhưng listener ghi dữ liệu chậm, khiến đường phát sự kiện trực tiếp bị kéo dài và ảnh hưởng request chính.
Một ứng dụng tạo singleton phụ thuộc tài nguyên I/O trong constructor, khiến lỗi DNS tạm thời lúc startup khiến cả API không khả dụng dù chức năng liên quan không được sử dụng.
Một hệ thống kỳ vọng giao dịch do @Transactional có hiệu lực khi một method trong bean tự gọi method khác của chính nó, nhưng lỗi ghi dữ liệu khiến rollback không diễn ra như dự kiến.
Một service xử lý sự kiện dùng @Async nhưng phương thức được gọi nội bộ trên cùng bean, khiến tác vụ tiếp tục chạy đồng bộ và kéo dài phản hồi API.
Một nhóm gắn annotation xử lý lỗi lên method của object được tạo bằng new bên ngoài Spring, khiến hành vi quanh lời gọi khác với method trên bean do container quản lý.
Một ứng dụng quản lý connection pool bằng bean nhưng đồng thời có một factory thủ công khởi tạo pool thứ hai, khiến hai tập kết nối tiêu tốn tài nguyên và khó quan sát.
Một hệ thống tái cấu trúc bean từ singleton thành request scope nhưng lại inject vào background scheduler, khiến ứng dụng khởi động được còn job theo lịch thất bại khi chạy.
Một dịch vụ được Spring Boot tự tạo DataSource theo starter JDBC, nhưng khi người dùng thêm một DataSource bean tùy biến các giá trị cấu hình pool mặc định không còn áp dụng như trước.
Một ứng dụng có thư viện web MVC trên classpath và Boot tự cấu hình message converter, nhưng converter tùy biến của dự án làm các API cũ trả JSON khác với hợp đồng.
Một nhóm thêm starter Actuator vào service, khiến các health indicator và endpoint có điều kiện xuất hiện mà đội bảo mật chưa đưa vào tài liệu cấu hình.
Một dịch vụ tự khai báo bean ObjectMapper để hỗ trợ kiểu ngày đặc biệt, nhưng bỏ qua các tùy biến khác của Spring Boot và phản hồi REST đổi định dạng không mong muốn.
Một hệ thống phát hiện auto-configuration cho caching không chạy khi không có CacheManager, nhưng đội phát triển nhầm việc thêm dependency với việc kích hoạt hoàn toàn tính năng cache.
Một ứng dụng thêm provider database mới vào classpath và cả hai auto-configuration phụ thuộc bean hiện có, khiến nhóm không xác định được vì sao provider cũ được chọn mặc định.
Một starter cung cấp bean HTTP client chỉ khi chưa có bean cùng loại, nhưng bean người dùng trả về interface khác khiến cấu hình mặc định vẫn tạo thêm client.
Một ứng dụng tự khai báo bean SecurityFilterChain, nhưng một starter nội bộ vẫn thêm filter khác khiến một số endpoint bị kiểm tra bảo mật nhiều lần.
Một hệ thống loại trừ auto-configuration DataSource để chạy ở chế độ offline, nhưng một component của module nghiệp vụ vẫn yêu cầu transaction manager và ngăn context khởi tạo.
Một nhóm dùng @ConditionalOnProperty cho tính năng gửi email, nhưng giá trị property ở staging khác production nên cùng artifact tạo tập bean không giống nhau.
Một ứng dụng được cấu hình @ConditionalOnMissingBean để tôn trọng bean tùy chỉnh, nhưng một thư viện đăng ký bean quá muộn khiến điều kiện không nhìn thấy như mong đợi.
Một dịch vụ không tìm thấy bean converter sau khi thêm starter, nhưng đội chỉ xem exception cuối mà không phân tích vì sao điều kiện auto-configuration không phù hợp.
Một nhóm bật debug mode để xem condition evaluation report, nhưng không nhận ra một cấu hình có classpath match vẫn có thể không tạo bean do điều kiện thiếu bean ở phương thức.
Một ứng dụng thay đổi property sau khi ApplicationContext đã refresh và kỳ vọng bean do auto-configuration quyết định được tạo lại ngay, nhưng chức năng vẫn giữ cấu hình cũ.
Một nhóm đặt @Configuration ở package được component scan và đồng thời import nó thủ công, khiến tập định nghĩa cấu hình được xử lý theo đường khác với dự tính ban đầu.
Một thư viện tự đăng ký auto-configuration qua metadata jar, nhưng bản shaded jar do đội đóng gói bỏ mất tệp imports khiến service sử dụng không có bean cần thiết.
Một ứng dụng chỉ chạy HTTP client nhưng dependency web server xuất hiện trên classpath, khiến Spring Boot tạo web application context và bind port không mong muốn.
Một dự án phân tích hoạt động bình thường với mặc định của Spring Boot, nhưng thêm cấu hình MVC tùy biến làm mất một số tính năng cấu hình tự động vốn đang dùng.
Một nhóm xem mọi bean trong context đều do Spring Boot cung cấp, khiến họ bỏ qua bean được đăng ký từ thư viện nội bộ khi điều tra lỗi kết nối.
Một ứng dụng dùng configuration class để tạo nhiều bean có phụ thuộc lẫn nhau, nhưng một bean bị loại bởi property khiến bean còn lại thất bại vì thiếu dependency.
Một doanh nghiệp có nhiều môi trường sử dụng chung application.yml, nhưng config profile production bị ghi sai tên và ứng dụng khởi động bằng credential của môi trường mặc định.
Một hệ thống cấu hình cổng HTTP từ biến môi trường, nhưng biến có định dạng không thể chuyển thành số khiến web server không thể bind port khi deploy container.
Một nhóm đặt password cho API đối tác trong application.properties được commit vào Git, khiến thông tin nhạy cảm xuất hiện trong lịch sử phiên bản dự án.
Một dịch vụ có cấu hình mặc định trong jar và file cấu hình bên ngoài, nhưng một giá trị ưu tiên cao từ biến môi trường làm timeout thực tế khác giá trị đội vận hành đang xem.
Một ứng dụng dùng @Value để đọc thuộc tính không tồn tại, khiến việc tạo bean lỗi startup dù tính năng dùng giá trị đó chỉ được gọi trong một luồng hiếm gặp.
Một nhóm chuyển nhiều @Value rời rạc thành @ConfigurationProperties, nhưng prefix trong file cấu hình không khớp và toàn bộ đối tượng nhận giá trị mặc định.
Một hệ thống khai báo thời gian chờ kết nối bằng chuỗi không có đơn vị, khiến cách binding Duration khác kỳ vọng giữa các nhóm phát triển đang dùng chung starter.
Một ứng dụng truyền địa chỉ server bên ngoài qua biến môi trường theo quy tắc relaxed binding, nhưng tên biến được viết sai nên cấu hình dự phòng bị sử dụng.
Một nhóm chỉ dùng một file cấu hình cho nhiều quốc gia, nhưng các trường ngày tháng và tiền tệ được parse theo giả định locale của môi trường máy chủ.
Một dịch vụ khai báo profile staging và production đồng thời để thử tích hợp, khiến hai tập bean được tạo cùng lúc và lỗi trùng implementation khi inject.
Một ứng dụng dùng @Profile để tắt adapter thanh toán thật trong test, nhưng bean cấu hình thủ công khác vẫn khởi tạo kết nối tới ngân hàng ở môi trường thử nghiệm.
Một nhóm thay đổi active profiles bằng tham số command line mà vẫn dùng image cũ, khiến điều kiện bean và endpoint được expose khác với phiên bản chạy trước.
Một hệ thống gắn secret vào Docker environment nhưng cấu hình log ở startup in ra toàn bộ các thuộc tính sau binding, khiến token nhạy cảm có nguy cơ bị lộ.
Một dịch vụ đọc danh sách endpoint từ @ConfigurationProperties, nhưng thứ tự dữ liệu trong YAML bị hiểu thành thứ tự ưu tiên cố định dù các địa chỉ có trạng thái khả dụng khác nhau.
Một nhóm thay đổi property cấu hình pool tại runtime qua ConfigMap, nhưng các kết nối đang tồn tại vẫn dùng giá trị đã binding lúc context khởi tạo.
Một ứng dụng lấy cấu hình từ nhiều nguồn và dùng tên property khác nhau chỉ bởi dấu gạch ngang, khiến nhóm hỗ trợ không biết nguồn nào có hiệu lực sau relaxed binding.
Một service có file YAML khai báo thuộc tính cho môi trường local, nhưng cấu trúc thụt lề sai khiến giá trị đọc ra không thuộc prefix mà bean đang chờ.
Một nhóm để profile mặc định kết nối tới database thật khi không khai báo môi trường, khiến bài kiểm thử integration vô tình thay đổi dữ liệu sản xuất.
Một ứng dụng dùng cấu hình tài nguyên từ filesystem với đường dẫn tương đối, nhưng khi chạy jar ở thư mục khác thì tệp template không còn được tìm thấy.
Một service lấy chứng chỉ TLS theo đường dẫn ngoài jar, nhưng khi triển khai lên Kubernetes container không có mount tương ứng và bean HTTP client không thể tạo.
Một hệ thống dùng server.port cố định trên cùng máy nhiều instance, khiến lần chạy thứ hai thất bại do cổng đã được chiếm bởi ứng dụng trước.
Một nhóm chạy Spring Boot từ IDE với thời gian khởi động ngắn, nhưng bản production cần đọc nhiều cấu hình bên ngoài khiến thời gian sẵn sàng lâu hơn giới hạn health check.
Một ứng dụng khởi tạo cache trong CommandLineRunner và đánh dấu ứng dụng ready trước khi cache được nạp xong từ tác vụ bất đồng bộ, khiến request đầu tiên nhận dữ liệu thiếu.
Một service thực hiện shutdown trong lúc còn request đang gửi dữ liệu, nhưng cấu hình của embedded web server không đủ thời gian xử lý các yêu cầu đang hoạt động.
Một ứng dụng có scheduler bắt đầu chạy ngay khi context được refresh, nhưng job truy vấn dữ liệu trước khi một bean nạp tham chiếu hoàn thành và lưu kết quả không nhất quán.
Một nhóm gắn listener ApplicationReadyEvent để cập nhật trạng thái bên ngoài, nhưng việc gọi API trong listener bị treo khiến thời gian startup được ghi nhận không như mong đợi.
Một hệ thống dùng DisposableBean đóng pool khi context kết thúc, nhưng một thread tự tạo ngoài container vẫn gửi yêu cầu dùng pool đã đóng và phát sinh lỗi sau shutdown.
Một ứng dụng chuyển từ ứng dụng web sang batch CLI, nhưng có bean non-daemon thread do thư viện ngoài tạo nên JVM không thoát dù SpringApplication đã hoàn tất công việc.
Một dịch vụ có bean chạy logic trong @PostConstruct làm lỗi ứng dụng nếu không kết nối được API bên thứ ba, khiến tính năng phụ làm hỏng cả dịch vụ chính.
Một hệ thống đổi ApplicationRunner từ kiểm tra dữ liệu sang sửa dữ liệu thật, khiến mỗi lần restart tự động sau lỗi cơ sở hạ tầng lại tái thực hiện thao tác ghi.
Một nhóm sử dụng event ApplicationFailedEvent để báo cáo sự cố startup, nhưng thông báo gửi đi không có nguyên nhân gốc của bean thất bại nên khó điều tra.
Một ứng dụng không được shutdown theo cách thông thường khi node bị kết thúc cưỡng bức, khiến callback @PreDestroy không có cơ hội ghi trạng thái cuối cùng của tiến trình.
Một hệ thống cần phục vụ request nhanh sau deploy nhưng một bean không cần cho đường HTTP chính vẫn khởi tạo nặng, khiến startup time tăng sau khi bổ sung chức năng báo cáo.
Một dự án Spring Boot được chạy thành công qua Gradle bootRun, nhưng tệp jar thường được copy lên server thiếu dependency runtime và không thể khởi động độc lập.
Một nhóm dùng plugin đóng gói executable jar nhưng cấu hình main class bị trỏ nhầm sang ứng dụng thử nghiệm, khiến container chạy tác vụ khác với API mong đợi.
Một dịch vụ chuyển từ executable jar sang WAR để dùng application server ngoài, nhưng bộ cấu hình bootstrap cho container servlet khác khiến endpoint không được đăng ký.
Một hệ thống tạo image container từ jar rồi quên expose và ánh xạ cổng đúng với server.port đang dùng, khiến ứng dụng healthy bên trong nhưng không truy cập được từ bên ngoài.
Một nhóm đặt tài nguyên tĩnh vào thư mục không được đưa vào jar, khiến trang quản trị hoạt động trên IDE nhưng trả 404 khi chạy bản release.
Một ứng dụng gửi email dựa trên template ở classpath nhưng thao tác đọc theo đường dẫn file thật, khiến chạy trong executable jar không tìm thấy resource.
Một dự án tạo Docker image cho Spring Boot nhưng chỉ chạy tốt trên kiến trúc CPU của máy build, khiến image không thể khởi chạy trên nhóm máy chủ khác.
Một hệ thống phân phối ứng dụng dưới dạng layered jar nhưng thứ tự COPY trong Dockerfile làm lớp dependency luôn bị build lại dù chỉ đổi business code.
Một nhóm chuyển app sang container không có quyền ghi thư mục làm việc, khiến tính năng xuất tệp tạm gặp lỗi khi được gọi dù Spring Boot vẫn khởi động bình thường.
Một dịch vụ chạy JVM với dung lượng heap vượt memory limit container, khiến tiến trình bị hệ điều hành dừng khi nhập dữ liệu lớn dù không có exception Java rõ ràng.
Một nhóm xây native image để giảm startup, nhưng các bean tích hợp thư viện dùng reflection thiếu metadata nên ứng dụng chạy JVM tốt còn bản native thất bại.
Một hệ thống deploy cùng artifact lên hai môi trường khác nhau nhưng dựa vào đường dẫn absolute hard-coded trong cấu hình, khiến chỉ môi trường có cấu trúc thư mục giống máy phát triển hoạt động.
Một ứng dụng chạy Java version mới trên máy chủ nhưng bản build dùng bytecode không tương thích với runtime thấp hơn của một cụm khác, khiến một số node lỗi khi rolling deployment.
Một nhóm triển khai nhiều instance trên một host nhưng lưu cùng một file log cố định trong thư mục cục bộ, khiến các tiến trình cạnh tranh quyền ghi và nội dung log bị trộn.
Một ứng dụng cần tải certificate khi startup từ thư mục mounted volume, nhưng volume chưa sẵn sàng lúc container khởi tạo khiến ứng dụng lặp restart liên tục.
Một dịch vụ REST đang trả phản hồi đúng nhưng log ở mức DEBUG ghi cả payload chứa thông tin cá nhân, khiến dữ liệu nhạy cảm xuất hiện trong hệ thống tập trung log.
Một nhóm dùng cấu hình logging.level toàn cục ở mức TRACE trong production để điều tra một lỗi nhỏ, khiến lượng log tăng đột biến và ảnh hưởng hiệu năng I/O.
Một ứng dụng sử dụng Logger từ thư viện phổ biến nhưng cấu hình backend logging bị thay đổi qua dependency, khiến định dạng JSON dự kiến không xuất hiện ở hệ thống thu thập.
Một service xử lý request đồng thời nhưng đặt mã đơn hàng vào MDC mà không dọn trong một đường lỗi, khiến log của request tiếp theo trên thread tái sử dụng mang mã đơn cũ.
Một nhóm chạy bước xử lý bất đồng bộ và kỳ vọng MDC từ HTTP request tự động xuất hiện trong task nền, khiến trace ID không được liên kết với log của tác vụ sau.
Một hệ thống thêm structured logging cho production nhưng format trường timestamp không đồng nhất giữa các ứng dụng, khiến dashboard sắp xếp sai thời điểm sự cố.
Một dịch vụ bắt exception ở controller rồi log cả stack trace tại ba tầng, khiến cùng lỗi nghiệp vụ một lần được đếm thành nhiều sự cố trong công cụ giám sát.
Một nhóm loại bỏ log startup mặc định để giảm chi phí, nhưng khi bean không thể tạo đội trực thiếu thông tin điều kiện cấu hình và nguyên nhân khởi động thất bại.
Một ứng dụng viết log của cả câu lệnh SQL và tham số ở production, khiến token và dữ liệu cá nhân được ghi vào hệ thống không có quyền bảo vệ tương ứng.
Một dịch vụ dùng log rotation theo kích thước nhưng container bị restart liên tục, khiến log cũ biến mất trước khi đội vận hành thu thập đủ dữ liệu chẩn đoán.
Một nhóm muốn bật debug riêng một package Spring khi có sự cố, nhưng cấu hình logging dùng sai tên logger khiến phần cần điều tra vẫn không xuất hiện.
Một API thành công nhưng không đưa request ID vào log, khiến khi người dùng báo lỗi giao dịch chậm đội hỗ trợ không liên kết được các bước xử lý của cùng request.
Một nhóm ghi log có thông tin người dùng trong đoạn message tự do mà không chuẩn hóa, khiến công cụ phân tích không tách được loại lỗi và ảnh hưởng từng tenant.
Một hệ thống đọc log từ stdout trong container nhưng thư viện thứ ba ghi trực tiếp ra file riêng, khiến sự cố của thành phần đó không có mặt trên dashboard tập trung.
Một dịch vụ thêm Spring Boot Actuator nhưng không cấu hình quyền truy cập endpoint quản trị, khiến người ngoài mạng nội bộ có thể thấy thông tin vận hành không phù hợp để công khai.
Một nhóm kiểm tra duy nhất endpoint health tổng thể và thấy DOWN do hệ thống email tùy chọn lỗi, khiến load balancer loại các instance dù API chính vẫn phục vụ request.
Một ứng dụng dùng cùng health endpoint phụ thuộc database cho cả liveness và readiness, khiến lúc database mất kết nối tạm thời nền tảng điều phối liên tục khởi động lại pod dù JVM vẫn sống.
Một đội vận hành bật endpoint metrics của Actuator nhưng không tạo dashboard độ trễ HTTP, khiến lỗi chậm dần vẫn bị che bởi tỷ lệ HTTP 200 cao.
Một API tích hợp ba dịch vụ ngoài nhưng chỉ đo thời gian request tổng, khiến đội hỗ trợ không biết đoạn chờ nằm ở database, HTTP client hay bước tính toán.
Một nhóm thêm Micrometer timer cho mỗi khách hàng bằng nhãn mã tài khoản, khiến cardinality metric tăng không kiểm soát khi số người dùng đạt hàng triệu.
Một ứng dụng có nhiều instance chạy sau load balancer nhưng metric chỉ được thu từ một node, khiến dashboard bỏ sót tỷ lệ lỗi xảy ra trên các node còn lại.
Một dịch vụ bị ngắt request liên tục sau deploy nhưng endpoint Actuator health vẫn UP, khiến đội trực nhầm mức sống của JVM với chất lượng toàn bộ API.
Một nhóm bật tracing cho ứng dụng web nhưng việc gửi request sang dịch vụ ngoài không mang trace context, khiến một giao dịch xuyên dịch vụ hiện thành nhiều trace rời rạc.
Một ứng dụng xử lý message từ broker sau HTTP request nhưng không truyền correlation ID, khiến khi lỗi ghi database xuất hiện đội khó nối thông điệp với yêu cầu người dùng ban đầu.
Một hệ thống ghi nhận JVM memory còn thấp nhưng không theo dõi thread pool và connection pool, khiến một lúc tải cao API hết kết nối trong khi heap vẫn ổn.
Một ứng dụng đặt đường dẫn metrics sau reverse proxy khác với cấu hình scrape, khiến hệ thống quan sát không thu được dữ liệu nhưng API vẫn chạy bình thường.
Một nhóm bật quá nhiều endpoint Actuator qua HTTP cho môi trường production, khiến thông tin mappings và environment có thể bị lộ nếu không áp dụng chính sách truy cập phù hợp.
Một dịch vụ sử dụng health indicator tự viết để gọi API đối tác với timeout dài, khiến việc kiểm tra sức khỏe của chính ứng dụng bị chậm và làm probe thất bại ngẫu nhiên.
Một hệ thống đo thời gian khởi động qua log thủ công nhưng không phân biệt thời gian chuẩn bị môi trường, tạo context và chạy runner, khiến tối ưu sai thành phần gây nghẽn.
Một nhóm lập trình test đơn vị cho OrderService nhưng luôn khởi động toàn bộ Spring context, khiến hàng nghìn bài test nhỏ chạy chậm và phụ thuộc database thật.
Một ứng dụng sử dụng @SpringBootTest để kiểm thử endpoint, nhưng cấu hình test không tạo được kết nối tới provider ngoài và suite thất bại trước khi kiểm tra nghiệp vụ.
Một nhóm dùng @WebMvcTest để kiểm tra controller nhưng service dependency không có trong slice context, khiến test lỗi khởi tạo dù ứng dụng đầy đủ chạy bình thường.
Một hệ thống dùng MockMvc kiểm tra HTTP 200 nhưng không assert nội dung JSON và header, khiến một thay đổi định dạng response không bị phát hiện trước khi phát hành.
Một nhóm chỉ kiểm thử controller bằng gọi method Java trực tiếp, khiến lỗi định tuyến URL và chuyển dữ liệu request thành DTO không xuất hiện trong suite.
Một ứng dụng dùng @DataJpaTest với database nhúng nhưng production là database khác, khiến truy vấn dựa trên cú pháp đặc thù chạy tốt ở test mà thất bại ngoài thực tế.
Một đội dùng @SpringBootTest với transaction rollback khi test kết thúc, nhưng thao tác gửi event tới dịch vụ ngoài vẫn xảy ra và để lại tác dụng phụ trong môi trường thử nghiệm.
Một hệ thống tích hợp cơ sở dữ liệu qua Testcontainers nhưng mỗi test class khởi tạo container mới, khiến thời gian chạy CI tăng mạnh và kết quả khó dự báo khi máy thiếu tài nguyên.
Một nhóm khai báo profile test nhưng chưa tắt runner nạp dữ liệu mặc định, khiến mỗi lần chạy suite thay đổi trạng thái dữ liệu fixture trước khi assertion bắt đầu.
Một ứng dụng tạo bean mock cho payment client ở test slice nhưng không kiểm tra cấu hình thực của client, khiến lỗi credentials chỉ được phát hiện sau deploy.
Một nhóm dùng @DynamicPropertySource để cấp URL database động nhưng một lớp test khác vẫn lấy URL từ file cấu hình cũ, khiến hai suite kiểm tra trên dữ liệu không giống nhau.
Một hệ thống test controller qua MockMvc nhưng chưa mô phỏng request có thông tin xác thực, khiến các rule phân quyền thực tế không được kiểm tra.
Một ứng dụng có cấu hình theo profile production và staging nhưng test chỉ chạy profile mặc định, khiến xung đột bean ở production không được phát hiện trước phát hành.
Một nhóm assert rằng ApplicationContext khởi động được rồi coi là kiểm thử đầy đủ, khiến lỗi xử lý JSON của đường API thật vẫn lọt qua kiểm tra.
Một dịch vụ dùng bean singleton lưu trạng thái request nhưng bộ test luôn gửi request tuần tự, khiến race condition khi người dùng truy cập đồng thời chỉ xuất hiện ở production.
Một nhóm kiểm thử shutdown bằng cách kết thúc JVM cưỡng bức, khiến không đánh giá được callback dọn tài nguyên của bean trong tình huống đóng ứng dụng bình thường.
Một hệ thống dùng @SpringBootTest với nhiều cấu hình mock khác nhau trên từng test, khiến số context phải tạo mới tăng đáng kể và bộ test chậm khi chạy CI.
Một ứng dụng muốn xác minh cấu hình override bean mặc định, nhưng suite chỉ dùng bean tự khai báo nên không kiểm tra nhánh auto-configuration back-off của môi trường consumer.
Một nhóm triển khai Java version mới nhưng suite test chỉ chạy trên JDK máy phát triển, khiến lỗi runtime ở hệ điều hành và Java runtime của server không được phát hiện.
Một hệ thống đưa các environment variable thật của CI vào test context, khiến bài kiểm thử phụ thuộc cấu hình máy chạy và kết quả thay đổi giữa các lần build.
Một dịch vụ dùng integration test gửi request HTTP tới cổng cố định, khiến hai job CI chạy song song tranh chấp cổng và một suite thất bại ngẫu nhiên.
Một nhóm test Actuator health nhưng không mô phỏng database mất kết nối, khiến chính sách readiness sai chỉ được phát hiện khi có sự cố production.
Một ứng dụng quan sát yêu cầu qua log nhưng không assert thông tin tương quan trong integration test, khiến sau lần refactor trace ID biến mất khỏi log mà không có cảnh báo.
Một đội dùng endpoint test để kiểm tra cấu hình theo môi trường, nhưng không ghi nhận các bean và giá trị property thực tế nên hai bản deploy cùng pass dù chạy provider khác nhau.
