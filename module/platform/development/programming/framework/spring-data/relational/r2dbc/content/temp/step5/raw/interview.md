Bạn giải thích Spring Data R2DBC giải quyết vấn đề gì khi ứng dụng Spring Boot cần truy cập cơ sở dữ liệu quan hệ theo mô hình reactive?
Bạn phân biệt R2DBC với JDBC về cách chờ I/O, sử dụng thread và mô hình lập trình như thế nào?
Bạn sẽ lựa chọn R2DBC thay JDBC theo những đặc điểm workload và mục tiêu throughput nào?
Bạn phân tích vì sao non-blocking database access không đồng nghĩa mọi câu SQL đều chạy nhanh hơn như thế nào?
Bạn mô tả vai trò của R2DBC SPI, driver và Spring Data R2DBC trong một lời gọi truy cập dữ liệu ra sao?
Bạn phân biệt Spring Data R2DBC với JPA và Hibernate về persistence context, lazy loading và quản lý entity như thế nào?
Bạn sẽ xác định những giới hạn khi chuyển ứng dụng JPA sang Spring Data R2DBC ra sao?
Bạn giải thích vì sao repository reactive không tự biến một JDBC driver thành non-blocking như thế nào?
Bạn sẽ quyết định khi nào giữ một phần truy cập JDBC riêng thay vì chuyển toàn bộ code sang R2DBC như thế nào?
Bạn phân tích sự khác nhau giữa khả năng xử lý đồng thời của ứng dụng và khả năng xử lý truy vấn của database như thế nào?
Bạn sẽ thiết kế ranh giới giữa business logic và reactive data adapter để giảm phụ thuộc vào R2DBC ra sao?
Bạn mô tả vòng đời một truy vấn SQL từ HTTP request qua WebFlux, service, repository đến database như thế nào?
Bạn giải thích vì sao blocking call trong reactive event loop làm giảm lợi ích của R2DBC ra sao?
Bạn sẽ đánh giá ảnh hưởng của network latency đối với việc chọn truy cập database non-blocking như thế nào?
Bạn phân biệt nguồn dữ liệu phản hồi theo luồng với kết quả được tập hợp hết vào memory trước khi trả cho người dùng như thế nào?
Bạn xác định những tác vụ tính toán CPU nặng cần xử lý khác tác vụ chờ I/O database như thế nào?
Bạn sẽ lựa chọn khi nào một ứng dụng Spring MVC dùng R2DBC có lợi và khi nào cần WebFlux như thế nào?
Bạn phân tích những yếu tố nào quyết định mức độ khó khi debug một chuỗi truy cập dữ liệu reactive ra sao?
Bạn sẽ xác định chỉ tiêu latency, concurrency và resource usage để đo lợi ích khi chuyển từ JDBC sang R2DBC như thế nào?
Bạn phân biệt non-blocking tại API với non-blocking thực tế của driver và thao tác phụ trợ như thế nào?
Bạn mô tả vai trò của ConnectionFactory trong R2DBC và sự khác biệt với JDBC DataSource như thế nào?
Bạn sẽ cấu hình kết nối R2DBC cho một ứng dụng Spring Boot theo môi trường bằng cách nào?
Bạn phân biệt R2DBC connection URL với JDBC URL và xác định các tham số tương ứng như thế nào?
Bạn giải thích R2DBC driver tương thích với loại database và phiên bản server ảnh hưởng triển khai ra sao?
Bạn sẽ lựa chọn dependency Spring Data R2DBC và driver PostgreSQL hoặc MySQL phù hợp theo phiên bản nào?
Bạn phân tích rủi ro kéo theo nhiều driver R2DBC hoặc cấu hình không phù hợp khiến auto-configuration chọn sai như thế nào?
Bạn xác định cách kiểm tra ConnectionFactory được Spring Boot khởi tạo đúng từ cấu hình như thế nào?
Bạn sẽ quản lý username, password và TLS cho kết nối R2DBC mà không lưu secret trong repository ra sao?
Bạn phân biệt cấu hình connection tới database với cấu hình schema hoặc tenant của từng request như thế nào?
Bạn sẽ thiết kế startup validation để phát hiện cấu hình thiếu mà không chạy query nặng như thế nào?
Bạn đánh giá khi nào nên fail-fast nếu không kết nối được database và khi nào ứng dụng có thể khởi động ở chế độ giảm chức năng ra sao?
Bạn phân tích ảnh hưởng của DNS, failover và thay đổi endpoint database tới ConnectionFactory như thế nào?
Bạn sẽ thiết kế môi trường local để kiểm tra R2DBC mà không dùng thông tin truy cập production như thế nào?
Bạn phân biệt configuration properties của Spring Boot với cấu hình native của một R2DBC driver như thế nào?
Bạn sẽ lựa chọn giới hạn timeout kết nối, xác thực và truy vấn dựa trên SLA của ứng dụng ra sao?
Bạn giải thích tại sao cấu hình auto-configuration R2DBC không có nghĩa mọi công cụ JDBC migration tự chạy cùng ConnectionFactory như thế nào?
Bạn sẽ tổ chức việc chạy Flyway hoặc Liquibase với nguồn kết nối phù hợp trước khi ứng dụng reactive nhận traffic ra sao?
Bạn phân tích rủi ro schema migration còn đang chạy trong khi ứng dụng phiên bản mới đã thực thi SQL như thế nào?
Bạn xác định cách kiểm tra connection và database dialect đã được ứng dụng nhận diện đúng ra sao?
Bạn sẽ thiết kế cách tách database account chỉ đọc khỏi account có quyền ghi hoặc quản trị schema như thế nào?
Bạn giải thích vai trò của @Table trong ánh xạ entity Spring Data R2DBC với bảng quan hệ như thế nào?
Bạn mô tả cách @Id xác định primary key của một entity và ảnh hưởng tới insert hay update ra sao?
Bạn phân biệt @Column với tên field Java khi ánh xạ những cột có quy ước tên khác nhau như thế nào?
Bạn sẽ lựa chọn kiểu dữ liệu Java cho ID, thời gian và số tiền để khớp schema database ra sao?
Bạn phân tích hệ quả của việc dùng số thực để biểu diễn dữ liệu tiền tệ khi lưu qua R2DBC như thế nào?
Bạn sẽ thiết kế entity tách khỏi DTO để tránh lộ column nhạy cảm trong response như thế nào?
Bạn đánh giá ảnh hưởng của việc entity có trường null nhưng database column đặt NOT NULL như thế nào?
Bạn sẽ xử lý schema evolution khi bảng mới thêm column chưa có trong entity cũ ra sao?
Bạn phân tích nguy cơ đổi tên column khi nhiều phiên bản ứng dụng cùng chạy trên một database như thế nào?
Bạn sẽ xây dựng quy ước field naming để truy vấn tùy chỉnh và mapping entity không bị lệch như thế nào?
Bạn phân biệt data class bất biến với mutable entity khi Spring Data R2DBC cần tạo object từ hàng dữ liệu như thế nào?
Bạn sẽ xác định khi nào cần constructor mapping hoặc custom converter cho một value object ra sao?
Bạn mô tả vai trò của R2dbcCustomConversions khi database type không ánh xạ trực tiếp sang kiểu Java như thế nào?
Bạn sẽ kiểm thử cách ánh xạ JSON, enum hoặc array theo khả năng của từng R2DBC driver như thế nào?
Bạn phân tích rủi ro một kiểu dữ liệu do driver trả về khác kỳ vọng của converter ra sao?
Bạn sẽ quản lý timezone khi lưu và đọc timestamp với database ở múi giờ khác như thế nào?
Bạn phân biệt giá trị DEFAULT của database với giá trị default được gán trong entity Java ra sao?
Bạn sẽ kiểm tra việc database tạo ID và cách Spring Data đọc lại ID sau insert như thế nào?
Bạn giải thích vì sao entity R2DBC không có cơ chế dirty checking giống JPA khi sửa một field như thế nào?
Bạn sẽ thiết kế cập nhật có chọn lọc một column mà không ghi đè những field không được tải từ database ra sao?
Bạn phân tích tác hại của việc đọc entity cũ rồi lưu lại toàn bộ khi người dùng khác đã sửa một column như thế nào?
Bạn sẽ dùng @Version để triển khai optimistic locking trong Spring Data R2DBC theo những điều kiện nào?
Bạn phân biệt version phục vụ optimistic locking với trường version nghiệp vụ hoặc schema như thế nào?
Bạn sẽ thiết kế xử lý OptimisticLockingFailureException để tránh mất dữ liệu khi hai request cùng cập nhật ra sao?
Bạn đánh giá khi nào cho phép tự động retry một optimistic conflict và khi nào trả trạng thái conflict cho client như thế nào?
Bạn xác định cách ánh xạ metadata tạo và cập nhật thời gian bằng auditing mà không nhầm clock của ứng dụng ra sao?
Bạn sẽ cấu hình @CreatedDate, @LastModifiedDate và @EnableR2dbcAuditing theo nhu cầu nào?
Bạn phân tích ảnh hưởng của before-convert callback khi sinh ID hoặc chuẩn hóa entity trước khi lưu như thế nào?
Bạn sẽ sử dụng BeforeConvertCallback và BeforeSaveCallback cho những trách nhiệm khác nhau như thế nào?
Bạn đánh giá rủi ro callback thực hiện lời gọi I/O phụ hoặc thay đổi dữ liệu ngoài transaction như thế nào?
Bạn sẽ thiết kế mapping cho một quan hệ một-nhiều mà không giả định R2DBC tự động tải toàn bộ object graph ra sao?
Bạn phân biệt lưu foreign key trong entity với ánh xạ relationship theo JPA @OneToMany như thế nào?
Bạn sẽ tổ chức aggregate khi cần truy vấn cả parent và children từ nhiều bảng bằng những chiến lược nào?
Bạn phân tích tradeoff giữa thao tác join SQL và nhiều repository calls khi mapping dữ liệu liên quan như thế nào?
Bạn sẽ kiểm soát vấn đề N+1 queries nếu một Flux các entity kéo theo truy vấn con cho từng phần tử ra sao?
Bạn xác định cách tránh cascade save tự động không được hỗ trợ như trong JPA khi lưu một aggregate ra sao?
Bạn sẽ thiết kế xóa dữ liệu phụ thuộc bằng SQL và transaction để không để lại orphan records như thế nào?
Bạn giải thích ReactiveCrudRepository hỗ trợ thao tác nào khi làm việc với entity R2DBC như thế nào?
Bạn phân biệt R2dbcRepository với ReactiveCrudRepository theo các khả năng được expose và cách sử dụng như thế nào?
Bạn sẽ tạo repository interface cho bảng người dùng có khóa chính UUID theo nguyên tắc nào?
Bạn mô tả cách Spring Data khởi tạo implementation cho repository interface trong ApplicationContext như thế nào?
Bạn phân biệt findById trả Mono với findAll trả Flux theo số phần tử và thời điểm thực thi ra sao?
Bạn sẽ xử lý Mono.empty từ repository khi bản ghi không tồn tại mà không coi đó là lỗi database như thế nào?
Bạn đánh giá ảnh hưởng của findAll không có giới hạn trên bảng có hàng triệu bản ghi ra sao?
Bạn sẽ thiết kế repository method truy vấn theo email mà không đưa input trực tiếp vào chuỗi SQL như thế nào?
Bạn phân tích cơ chế derived query từ tên method và giới hạn khi query phức tạp như thế nào?
Bạn sẽ quyết định khi nào dùng @Query thay vì derived query để kiểm soát SQL rõ ràng ra sao?
Bạn mô tả cách @Query binding tham số đảm bảo điều kiện truy vấn không phụ thuộc vào phép nối chuỗi input như thế nào?
Bạn phân tích ảnh hưởng của ORDER BY và LIMIT/OFFSET tới truy vấn phân trang reactive như thế nào?
Bạn sẽ thiết kế sorting ổn định khi nhiều bản ghi cùng giá trị trên column chính ra sao?
Bạn phân biệt Page với Slice hoặc Flux được giới hạn kết quả về chi phí query COUNT như thế nào?
Bạn sẽ lựa chọn keyset pagination trong một bảng lớn theo tiêu chí nào?
Bạn đánh giá rủi ro query trả về một lượng lớn row rồi mới filter bằng Flux.filter như thế nào?
Bạn sẽ đưa điều kiện lọc xuống SQL thay vì xử lý trong JVM theo nguyên tắc nào?
Bạn xác định khi nào query cần index và cách kiểm tra execution plan như thế nào?
Bạn sẽ thiết kế repository method chỉ lấy những column cần thiết bằng projection DTO ra sao?
Bạn phân biệt interface projection và DTO projection trong các endpoint chỉ yêu cầu vài field như thế nào?
Bạn phân tích rủi ro một projection không đủ field nhưng lại được lưu thành entity hoàn chỉnh ra sao?
Bạn sẽ tổ chức custom repository để hỗ trợ truy vấn phức tạp không phù hợp với method name như thế nào?
Bạn xác định cách thực hiện update hoặc delete có điều kiện mà không phải đọc toàn bộ entity ra sao?
Bạn sẽ kiểm tra row count sau update để phân biệt không tìm thấy bản ghi với cập nhật thành công như thế nào?
Bạn phân biệt SQL UPDATE chỉ sửa một column với repository.save khi có xử lý concurrent updates ra sao?
Bạn sẽ thiết kế repository API xử lý soft delete trong khi các truy vấn bình thường không trả dữ liệu đã xóa ra sao?
Bạn phân tích nguy cơ một method truy vấn quên lọc tenantId khi có nhiều khách hàng dùng chung bảng ra sao?
Bạn sẽ kiểm thử method repository không lộ bản ghi của tenant khác dù ID hợp lệ ra sao?
Bạn đánh giá việc repository trả Flux có giúp tiết kiệm memory khi mapping row liên tục như thế nào?
Bạn sẽ lựa chọn hình thức truy vấn tổng hợp SQL thay vì lấy toàn bộ row về client để tính toán như thế nào?
Bạn mô tả vai trò của R2dbcEntityTemplate trong việc thao tác dữ liệu quan hệ theo entity như thế nào?
Bạn phân biệt R2dbcEntityTemplate với R2dbcRepository theo mức điều khiển câu truy vấn và ánh xạ như thế nào?
Bạn sẽ lựa chọn R2dbcEntityTemplate cho một update động với số field thay đổi theo request ra sao?
Bạn giải thích các thao tác insert, select, update và delete của template hỗ trợ xây dựng data adapter như thế nào?
Bạn sẽ thiết kế một query dựa trên Criteria và Query để lọc theo nhiều điều kiện tùy chọn ra sao?
Bạn phân tích ưu nhược điểm của Criteria API so với raw SQL khi số predicate tăng như thế nào?
Bạn sẽ xác định cách chỉ rõ table hoặc entity class để template không thao tác nhầm bảng ra sao?
Bạn phân biệt R2dbcEntityOperations với một implementation cụ thể R2dbcEntityTemplate trong thiết kế dependency như thế nào?
Bạn sẽ dùng Update object để thay đổi có chủ đích một số column trong template như thế nào?
Bạn phân tích vì sao cập nhật từng field bằng template có thể an toàn hơn save cả entity thiếu field như thế nào?
Bạn sẽ thiết kế điều kiện update kèm version để bảo vệ concurrent writes mà không load toàn bộ entity ra sao?
Bạn phân biệt một template query trả entity với query trả scalar aggregation như thế nào?
Bạn xác định khi nào dùng DatabaseClient thay vì R2dbcEntityTemplate để thực thi SQL có nhiều join ra sao?
Bạn mô tả cách DatabaseClient quản lý statement binding và ánh xạ kết quả SQL như thế nào?
Bạn sẽ sử dụng parameter binding trong DatabaseClient để ngăn SQL injection như thế nào?
Bạn phân tích cách R2DBC database dialect ảnh hưởng placeholder và cú pháp SQL giữa các hệ quản trị ra sao?
Bạn sẽ giới hạn tên column dùng trong dynamic ORDER BY bằng allowlist như thế nào?
Bạn đánh giá rủi ro nối trực tiếp tên bảng hoặc field từ input người dùng vào câu SQL như thế nào?
Bạn sẽ map một kết quả join nhiều bảng thành DTO thay vì entity bằng cơ chế nào?
Bạn giải thích vì sao R2DBC không tự xây dựng toàn bộ object graph từ các row join như ORM JPA như thế nào?
Bạn sẽ thiết kế SQL cập nhật nhiều bản ghi theo một điều kiện và trả về số row bị ảnh hưởng ra sao?
Bạn phân tích khi nào nên dùng CTE hoặc subquery thay vì thực hiện nhiều truy vấn R2DBC riêng lẻ như thế nào?
Bạn sẽ tối ưu một query với nhiều điều kiện bằng EXPLAIN hoặc EXPLAIN ANALYZE theo database đang dùng như thế nào?
Bạn xác định chiến lược giữ SQL trong repository hoặc data adapter để vẫn dễ review và kiểm thử ra sao?
Bạn sẽ thiết kế cách ánh xạ SQL NULL sang Optional hoặc field nullable trong DTO như thế nào?
Bạn phân tích rủi ro query aggregate trả NULL thay vì số 0 và cách mapping kết quả ra sao?
Bạn sẽ kết hợp template với DatabaseClient trong cùng một service mà vẫn giữ transaction boundary rõ ràng ra sao?
Bạn xác định phương thức nào cần trả Mono số bản ghi bị sửa thay vì trả entity sau một update như thế nào?
Bạn sẽ kiểm thử câu SQL tùy chỉnh có chỉ mục và điều kiện lọc phù hợp với dữ liệu production ra sao?
Bạn giải thích transaction của R2DBC hoạt động thế nào khi kết nối được quản lý trong chuỗi reactive như thế nào?
Bạn phân biệt R2dbcTransactionManager với DataSourceTransactionManager dùng JDBC như thế nào?
Bạn sẽ xác định vị trí đặt @Transactional để nhiều repository calls cùng tham gia một reactive transaction ra sao?
Bạn giải thích vì sao transaction reactive gắn với Reactor Context thay vì chỉ dựa trên ThreadLocal như thế nào?
Bạn sẽ thiết kế một service tạo đơn hàng và dòng hàng trong cùng R2DBC transaction như thế nào?
Bạn phân tích điều gì xảy ra nếu một thao tác trong transaction gọi subscribe riêng thay vì compose vào publisher gốc ra sao?
Bạn sẽ bảo đảm toàn bộ các thao tác nằm trong một reactive chain được trả về từ method @Transactional như thế nào?
Bạn phân biệt transaction bao quanh Mono và Flux với transaction bao quanh code Java tạo publisher nhưng chưa subscribe ra sao?
Bạn sẽ áp dụng TransactionalOperator cho một pipeline khi không muốn dùng annotation @Transactional như thế nào?
Bạn mô tả cách TransactionalOperator giữ transaction context qua nhiều operators như thế nào?
Bạn phân tích rủi ro tự gọi method @Transactional trong cùng một Spring bean khiến AOP proxy không có hiệu lực ra sao?
Bạn sẽ xác định rollback behavior khi một Mono trong chuỗi trả error signal như thế nào?
Bạn phân biệt onErrorResume bên trong transaction với để lỗi truyền ra ngoài dẫn tới rollback như thế nào?
Bạn phân tích nguy cơ biến lỗi thành kết quả fallback thành công khiến transaction được commit ngoài mong đợi như thế nào?
Bạn sẽ lựa chọn nơi đặt onErrorResume để vừa rollback đúng vừa trả response nghiệp vụ phù hợp như thế nào?
Bạn giải thích tác động của cancellation từ subscriber tới quá trình commit hoặc rollback transaction như thế nào?
Bạn sẽ thiết kế kiểm thử hủy subscription giữa chừng để đánh giá dữ liệu đã được commit hay chưa ra sao?
Bạn phân biệt database transaction đã commit với một Mono chỉ phát ra tín hiệu onComplete cho caller ra sao?
Bạn sẽ xử lý tình huống client timeout nhưng server database có thể đã commit transaction như thế nào?
Bạn xác định cách thiết kế idempotency key khi caller retry thao tác tạo dữ liệu sau timeout như thế nào?
Bạn phân tích rủi ro dùng retryWhen bọc cả transaction khi trong transaction có lời gọi dịch vụ ngoài như thế nào?
Bạn sẽ quyết định khi nào retry toàn transaction vì deadlock hoặc serialization conflict ra sao?
Bạn đánh giá cách giới hạn số lần retry và áp dụng jitter khi nhiều transaction tranh chấp cùng bản ghi ra sao?
Bạn phân biệt isolation level của database với tính an toàn khi nhiều publisher cùng dùng một transaction như thế nào?
Bạn sẽ thiết kế một reactive transaction có nhiều bước tuần tự bằng then, flatMap hoặc concatMap ra sao?
Bạn phân tích rủi ro dùng flatMap concurrency lớn để chạy nhiều SQL statements trên cùng một transactional connection như thế nào?
Bạn sẽ quyết định khi nào cần giữ thứ tự statement để bảo đảm foreign key constraints ra sao?
Bạn phân biệt việc mở nhiều transaction ngắn với một transaction kéo dài qua hàng nghìn row như thế nào?
Bạn sẽ xử lý optimistic locking thông qua @Version phối hợp transaction trong trường hợp nào?
Bạn đánh giá ảnh hưởng của transaction timeout tới kết nối đang thực thi truy vấn chậm như thế nào?
Bạn sẽ đảm bảo không dùng blocking JDBC trong reactive transaction khi phải cập nhật hai nguồn dữ liệu ra sao?
Bạn giải thích vì sao R2DBC transaction không tự cung cấp distributed transaction giữa hai database hoặc message broker như thế nào?
Bạn sẽ thiết kế transactional outbox để phát sự kiện sau khi ghi dữ liệu mà không mất thông điệp như thế nào?
Bạn phân tích khi nào cần saga hoặc compensation thay vì cố mở một transaction xuyên nhiều service như thế nào?
Bạn xác định cách theo dõi transaction commit failures khác query execution failures trong logs như thế nào?
Bạn sẽ kiểm thử rollback của nhiều thao tác R2DBC khi một bước ném exception như thế nào?
Bạn giải thích Mono và Flux mô tả các kết quả R2DBC theo số lượng row và thời điểm thực thi như thế nào?
Bạn phân biệt publisher cold với việc query được thực thi ngay khi repository method được gọi ra sao?
Bạn mô tả subscribe tác động thế nào đến thời điểm tạo statement, lấy connection và chạy SQL như thế nào?
Bạn sẽ đánh giá rủi ro subscribe cùng một cold publisher hai lần khiến cùng một thao tác INSERT được thực thi lại ra sao?
Bạn phân tích vì sao một Flux không phải lúc nào cũng đồng nghĩa database trả từng row mà không buffer như thế nào?
Bạn sẽ thiết kế pipeline lấy nhiều bản ghi và xử lý theo luồng mà không collectList toàn bộ như thế nào?
Bạn phân biệt map với flatMap khi bước xử lý kế tiếp phải gọi một repository reactive khác như thế nào?
Bạn sẽ lựa chọn concatMap thay flatMap để giữ thứ tự thao tác ghi trong trường hợp nào?
Bạn phân tích tác động của flatMap concurrency tới số connection đang dùng và tải database như thế nào?
Bạn sẽ sử dụng limitRate hoặc kiểm soát concurrency khi downstream xử lý chậm như thế nào?
Bạn đánh giá giới hạn của Reactive Streams backpressure khi SQL server đã tạo ra lượng dữ liệu lớn trước khi consumer nhận ra sao?
Bạn sẽ xử lý request hủy giữa một Flux dài để giải phóng connection và cursor như thế nào?
Bạn phân biệt onErrorMap, onErrorResume và doOnError khi phân loại lỗi R2DBC ra sao?
Bạn sẽ xác định lỗi do vi phạm unique constraint khác lỗi database connection timeout như thế nào?
Bạn phân tích nguy cơ onErrorContinue làm mất thông tin một bản ghi thất bại trong pipeline ghi dữ liệu ra sao?
Bạn sẽ sử dụng retryWhen cho truy vấn đọc có thể retry theo loại lỗi nào?
Bạn đánh giá vì sao retry thao tác ghi phải xem xét idempotency và trạng thái commit chưa xác định ra sao?
Bạn sẽ phối hợp timeout của Reactor với statement timeout của driver và deadline HTTP như thế nào?
Bạn phân biệt timeout của WebFlux request với thời gian chờ lấy connection từ pool ra sao?
Bạn sẽ xác định cách truyền trace context qua Reactor Context khi pipeline chuyển scheduler ra sao?
Bạn phân tích vì sao publishOn và subscribeOn không nên được dùng tùy tiện để che một call blocking trong code reactive ra sao?
Bạn sẽ dùng boundedElastic khi phải tương tác tạm thời với thư viện blocking theo những điều kiện nào?
Bạn phân biệt non-blocking execution với chạy song song trên nhiều thread như thế nào?
Bạn sẽ xác định khi nào xử lý CPU-heavy nên chuyển khỏi event loop trước khi trả tiếp kết quả database ra sao?
Bạn đánh giá memory pressure khi một Flux có nguồn phát nhanh nhưng consumer downstream xử lý chậm như thế nào?
Bạn sẽ thiết kế phản hồi WebFlux streaming JSON theo điều kiện hợp đồng API và khả năng hủy kết nối như thế nào?
Bạn phân tích vì sao trả Flux từ controller chưa chắc tốt hơn trả page kích thước giới hạn ra sao?
Bạn sẽ chọn response HTTP 404 cho Mono.empty trong một WebFlux controller như thế nào?
Bạn phân biệt validation failure với database error khi chuyển tín hiệu reactive thành HTTP status ra sao?
Bạn sẽ thiết kế WebFlux handler giữ transaction ở service layer thay vì mở transaction xuyên thời gian truyền response ra sao?
Bạn đánh giá rủi ro giữ connection database tới khi client tiêu thụ xong streaming response như thế nào?
Bạn sẽ xây dựng ranh giới lấy dữ liệu và trả dữ liệu để không giữ transaction lâu hơn cần thiết như thế nào?
Bạn phân tích khi nào query cursor hỗ trợ streaming tốt và khi nào cần phân trang rõ ràng như thế nào?
Bạn sẽ định nghĩa chính sách pagination và upper bound cho kết quả một API reactive ra sao?
Bạn giải thích cách R2DBC connection pool ảnh hưởng throughput của ứng dụng non-blocking như thế nào?
Bạn phân biệt ConnectionFactory trực tiếp với ConnectionPool được cung cấp bởi r2dbc-pool như thế nào?
Bạn sẽ cấu hình initial size, max size và max idle time của connection pool theo đặc điểm tải ra sao?
Bạn xác định cách đặt max acquire time để request không xếp hàng chờ connection quá lâu như thế nào?
Bạn phân tích hiện tượng pool saturation khi request rate tăng dù CPU ứng dụng vẫn thấp ra sao?
Bạn sẽ đo số connection active, idle và pending acquires để xác định nút thắt ở đâu như thế nào?
Bạn đánh giá tác động của pool quá lớn lên số kết nối tối đa mà database cho phép như thế nào?
Bạn sẽ phân bổ pool size giữa nhiều replica mà không vượt quá max_connections của database ra sao?
Bạn giải thích vì sao non-blocking không làm tăng số query mà database có thể thực thi đồng thời vô hạn như thế nào?
Bạn xác định nguyên nhân connection leak khi một Flux không hoàn tất hoặc một custom driver client không được giải phóng đúng như thế nào?
Bạn sẽ kiểm tra statement result được consume hoặc cancel đúng cách khi dùng DatabaseClient ra sao?
Bạn phân tích rủi ro giữ transaction mở trong lúc chờ HTTP call khiến connection bị chiếm lâu như thế nào?
Bạn sẽ thiết kế timeout từng tầng gồm pool acquire, statement execution và API deadline ra sao?
Bạn phân biệt connection validation query với health check của Spring Boot Actuator về chi phí và tần suất như thế nào?
Bạn sẽ cấu hình readiness để tránh Pod nhận traffic khi database bắt buộc chưa thể phục vụ ra sao?
Bạn đánh giá nguy cơ liveness phụ thuộc database gây restart hàng loạt trong một outage ngắn như thế nào?
Bạn sẽ xác định khi nào dùng TLS cho connection và cách xác minh server certificate ra sao?
Bạn phân tích tác động của database failover tới connection đang mở trong pool như thế nào?
Bạn sẽ thiết kế cơ chế loại bỏ connection hỏng và tạo connection mới sau failover ra sao?
Bạn xác định chính sách retry khi connection vừa bị đóng trong lúc SQL write có thể đã commit như thế nào?
Bạn sẽ kiểm tra pool không bị cạn trong test tải có nhiều request bị cancel ra sao?
Bạn phân tích rủi ro tạo ConnectionPool mới theo mỗi request thay vì chia sẻ bean do Spring quản lý ra sao?
Bạn sẽ thiết kế client và pool lifecycle để ứng dụng shutdown đóng kết nối an toàn như thế nào?
Bạn đánh giá vì sao tăng max pool size không giải quyết được truy vấn thiếu index hoặc lock contention ra sao?
Bạn sẽ phân tích quan hệ giữa số pending acquire và p99 latency khi database quá tải như thế nào?
Bạn sẽ lập phương án backpressure hoặc load shedding khi pending connection requests vượt giới hạn như thế nào?
Bạn xác định cách phân biệt pool saturation với deadlock database bằng metrics và logs như thế nào?
Bạn sẽ thiết kế test đo độ trễ lấy connection riêng với thời gian thực thi SQL như thế nào?
Bạn phân tích nhu cầu đặt pool riêng khi một loại workload query dài gây nghẽn các request quan trọng ra sao?
Bạn giải thích vai trò của database indexes trong tối ưu SQL dù ứng dụng dùng R2DBC non-blocking như thế nào?
Bạn sẽ phân tích EXPLAIN của một query R2dbcEntityTemplate để tìm full table scan ra sao?
Bạn phân biệt query latency do network round trip với latency do database thực thi câu SQL như thế nào?
Bạn sẽ chọn composite index cho query có cả WHERE và ORDER BY dựa trên nguyên tắc nào?
Bạn đánh giá tác động của COUNT(*) trên bảng lớn khi API yêu cầu tổng trang như thế nào?
Bạn sẽ thiết kế keyset pagination để giảm chi phí OFFSET sâu trên bảng có hàng triệu row ra sao?
Bạn phân tích rủi ro gọi một query cho mỗi phần tử của Flux làm xuất hiện vấn đề N+1 như thế nào?
Bạn sẽ dùng SQL JOIN hoặc batch lookup để giảm số round trips khi đọc dữ liệu liên quan như thế nào?
Bạn xác định khi nào dùng native SQL aggregate thay vì gom Flux rồi tính toán trong ứng dụng như thế nào?
Bạn phân tích ảnh hưởng của việc thiếu LIMIT trong endpoint tìm kiếm lên database và JVM heap như thế nào?
Bạn sẽ đánh giá hiệu năng bulk insert khi dùng từng repository.save so với SQL batch nếu driver hỗ trợ như thế nào?
Bạn xác định giới hạn batch size phù hợp để không làm transaction giữ connection và lock quá lâu ra sao?
Bạn phân tích tác động của lock wait và deadlock lên reactive request latency ra sao?
Bạn sẽ thiết kế chiến lược retry deadlock có giới hạn mà không nhân đôi side effects như thế nào?
Bạn mô tả cách đọc query execution plan và index stats từ hệ quản trị đang dùng để xác định bottleneck ra sao?
Bạn sẽ kiểm tra các truy vấn bị ảnh hưởng sau khi migrate schema nhưng code cũ vẫn còn chạy như thế nào?
Bạn phân tích vai trò của SQL constraints trong giữ dữ liệu đúng khi nhiều application instances cập nhật đồng thời như thế nào?
Bạn sẽ dùng UNIQUE constraint và idempotency key để chống ghi trùng qua retry như thế nào?
Bạn đánh giá khi nào optimistic locking có lợi hơn việc khóa row bi quan như thế nào?
Bạn sẽ xác định transaction isolation phù hợp khi hai request cùng đọc số dư rồi cập nhật như thế nào?
Bạn phân tích cách connection pool và query timeout cần được điều chỉnh đồng bộ với số replica như thế nào?
Bạn sẽ thiết kế benchmark R2DBC và JDBC trên cùng SQL, dữ liệu và môi trường để tránh kết luận sai lệch ra sao?
Bạn giải thích bảo mật SQL injection khác với bảo mật credential kết nối database ở những điểm nào?
Bạn sẽ sử dụng bind parameters để tránh đưa input trực tiếp vào SQL theo cách nào?
Bạn phân tích rủi ro dynamic table name hoặc sort field được lấy từ request mà không có allowlist ra sao?
Bạn sẽ thiết kế authorization kiểm soát tenant trước khi truy vấn repository như thế nào?
Bạn đánh giá rủi ro một truy vấn update không có điều kiện tenantId làm thay đổi dữ liệu người dùng khác ra sao?
Bạn sẽ tạo các phương thức truy cập dữ liệu nhận tenant context một cách rõ ràng thay vì tin tưởng field do client gửi ra sao?
Bạn phân biệt database-level row security với việc filter tenant trong application SQL như thế nào?
Bạn phân tích vì sao Reactor Context hoặc security context có thể mất khi code tự subscribe hoặc đổi scheduler sai cách ra sao?
Bạn sẽ kiểm tra request của hai tenant chạy đồng thời không làm lẫn context hoặc query parameters như thế nào?
Bạn xác định cách bảo vệ PII trong logging SQL và bind parameters khi điều tra lỗi ra sao?
Bạn sẽ quản lý việc xoay vòng database password mà không gây downtime lớn như thế nào?
Bạn đánh giá vì sao application account không nên có quyền thay đổi schema trong production như thế nào?
Bạn sẽ tách quyền migration tool và quyền runtime R2DBC connection theo nguyên tắc nào?
Bạn phân tích rủi ro trả raw database exception cho HTTP client khi nó chứa tên bảng và cột nhạy cảm ra sao?
Bạn sẽ chuẩn hóa error response cho unique violation, timeout và unavailable database như thế nào?
Bạn xác định khi nào rate limiting hoặc bulkhead cần thiết để bảo vệ connection pool database ra sao?
Bạn sẽ thiết kế cơ chế từ chối yêu cầu thay vì để hàng đợi connection tăng vô hạn như thế nào?
Bạn phân tích nguy cơ retry storm khi nhiều service cùng gặp database failover như thế nào?
Bạn sẽ lựa chọn các metrics R2DBC pool, query duration và error rate để đưa lên dashboard như thế nào?
Bạn giải thích Micrometer có thể giúp quan sát thời gian chờ pool và thời gian thực thi repository như thế nào?
Bạn sẽ dùng Spring Boot Actuator health groups để phân biệt readiness và liveness của một ứng dụng reactive ra sao?
Bạn phân tích vì sao log một truy vấn chậm phải tránh ghi nguyên văn thông tin nhạy cảm từ bind values như thế nào?
Bạn sẽ thiết kế tracing từ WebFlux handler qua service tới statement execution như thế nào?
Bạn đánh giá vị trí bắt đầu và kết thúc span khi một cold publisher chỉ chạy tại subscription như thế nào?
Bạn sẽ gắn correlation ID hoặc trace ID vào log của một pipeline R2DBC qua nhiều operators ra sao?
Bạn phân tích nguy cơ gắn userId hoặc query parameter vào metric labels làm cardinality tăng như thế nào?
Bạn sẽ xây dựng alert khi pending acquire tăng trong khi active connections đã đạt max như thế nào?
Bạn xác định cách nhận diện database deadlock tăng thông qua loại exception và telemetry ra sao?
Bạn sẽ lập runbook phân biệt query chậm, lỗi pool, authentication failure và database outage như thế nào?
Bạn phân tích cách lập kế hoạch rolling deployment khi schema migration phải tương thích cả code cũ và code mới như thế nào?
Bạn sẽ thiết kế canary rollout với metric so sánh latency và error rate trước sau chuyển sang R2DBC ra sao?
Bạn đánh giá kế hoạch rollback khi phiên bản mới sử dụng SQL hoặc mapping không tương thích với schema cũ như thế nào?
Bạn sẽ xác định tiêu chí capacity planning gồm số replica, connection pool, CPU database và query concurrency ra sao?
Bạn phân tích vì sao tỷ lệ lỗi thấp nhưng p99 latency vẫn có thể tăng mạnh khi pool chờ quá lâu như thế nào?
Bạn sẽ thiết kế log và metric để phân biệt một Flux bị cancel với Flux kết thúc bình thường như thế nào?
Bạn xác định những dấu hiệu cho thấy publisher không được subscribe nên câu SQL dự kiến chưa chạy ra sao?
Bạn sẽ kiểm thử unit service dùng ReactiveCrudRepository bằng mock Mono và Flux như thế nào?
Bạn phân biệt unit test cho business mapping với integration test chạy driver và database thật ra sao?
Bạn sẽ dùng StepVerifier để kiểm tra một Mono tìm được entity rồi hoàn thành như thế nào?
Bạn thiết kế StepVerifier test cho trường hợp repository trả Mono.empty và downstream xử lý không tồn tại ra sao?
Bạn sẽ dùng StepVerifier để xác minh exception từ unique constraint được map thành lỗi nghiệp vụ phù hợp như thế nào?
Bạn phân tích khi nào sử dụng StepVerifier.withVirtualTime để test retry/backoff mà không phụ thuộc thời gian thực ra sao?
Bạn sẽ thiết kế test đảm bảo một cold Mono insert chỉ thực hiện đúng số lần subscription dự kiến như thế nào?
Bạn xác định cách phát hiện một nhánh dùng block gây chặn event loop trong kiểm thử WebFlux ra sao?
Bạn sẽ dùng WebTestClient kiểm tra response của controller reactive khi database trả dữ liệu trống ra sao?
Bạn phân tích ưu điểm của Testcontainers PostgreSQL hoặc MySQL khi cần kiểm chứng driver R2DBC thực tế như thế nào?
Bạn sẽ cấu hình schema migration và seed dữ liệu test trước khi chạy repository integration tests như thế nào?
Bạn xác định cách cô lập transaction và cleanup dữ liệu để các test không phụ thuộc thứ tự ra sao?
Bạn thiết kế test R2dbcEntityTemplate với Criteria và Query có nhiều điều kiện tùy chọn như thế nào?
Bạn sẽ kiểm tra DatabaseClient bind parameters không làm thay đổi cú pháp SQL khi input có ký tự đặc biệt ra sao?
Bạn kiểm thử ánh xạ @Table, @Id, @Column và converter cho entity với kiểu dữ liệu không phổ biến như thế nào?
Bạn sẽ xây dựng test @Version ngăn lost update khi hai request đọc cùng một entity ra sao?
Bạn thiết kế integration test transaction tạo parent rồi child nhưng lỗi ở bước thứ hai để xác minh rollback như thế nào?
Bạn sẽ kiểm tra TransactionalOperator giữ transaction context khi pipeline có flatMap và then như thế nào?
Bạn phân tích cách test việc tự subscribe bên trong service có thể khiến thao tác thoát khỏi transaction ra sao?
Bạn sẽ xây dựng test onErrorResume đặt sai vị trí khiến transaction commit ngoài mong muốn như thế nào?
Bạn thiết kế test cancellation giữa Flux dài để kiểm tra pool trả connection đúng cách như thế nào?
Bạn sẽ kiểm thử max pool size và thời gian chờ acquire bằng tải đồng thời có kiểm soát ra sao?
Bạn phân tích cách dùng load test để phân biệt nghẽn database với nghẽn event loop trong ứng dụng như thế nào?
Bạn sẽ tạo kịch bản database restart hoặc failover để kiểm chứng connection pool phục hồi ra sao?
Bạn thiết kế integration test timeout SQL và kiểm tra retry không lặp thao tác ghi thiếu idempotency như thế nào?
Bạn sẽ kiểm thử multi-tenant queries không đọc hoặc sửa row của tenant khác ra sao?
Bạn xác định cách đo và kiểm thử số database round trips để phát hiện N+1 queries như thế nào?
Bạn sẽ xây dựng performance test truy vấn phân trang sâu với và không có composite index như thế nào?
Bạn phân tích cách so sánh throughput của pipeline flatMap concurrency thấp và cao mà vẫn kiểm tra tính đúng dữ liệu ra sao?
Bạn sẽ kiểm thử xử lý các lỗi DataIntegrityViolationException và transient connection failure riêng biệt như thế nào?
Bạn đánh giá khi nào cần chaos test database outage trong một khoảng ngắn để kiểm tra readiness và retry như thế nào?
Bạn sẽ đặt tiêu chí nghiệm thu trước production cho schema, mapping, transaction, pool, timeout, bảo mật và observability ra sao?
Nếu WebFlux API chậm dù CPU ứng dụng thấp và pending connections tăng, bạn sẽ khoanh vùng connection pool như thế nào?
Nếu repository.findAll phát ra hàng triệu rows khiến memory tăng, bạn sẽ thiết kế pagination và streaming ra sao?
Nếu một Mono ghi dữ liệu không thực thi dù method đã được gọi, bạn sẽ kiểm tra subscription và reactive chain như thế nào?
Nếu một thao tác INSERT chạy hai lần sau khi controller retry publisher, bạn sẽ thiết kế idempotency và vị trí retry ra sao?
Nếu transaction tạo đơn hàng nhưng bản ghi chi tiết không được rollback, bạn sẽ kiểm tra Reactor Context và cách compose publisher như thế nào?
Nếu một method @Transactional tự gọi method khác trong cùng bean mà transaction không có hiệu lực, bạn sẽ sửa thiết kế ra sao?
Nếu một nhánh onErrorResume trả kết quả thành công sau lỗi SQL, bạn sẽ xác minh transaction commit hay rollback như thế nào?
Nếu một truy vấn update ghi đè cột vừa được người khác thay đổi, bạn sẽ bổ sung @Version hoặc điều kiện update ra sao?
Nếu chuyển từ JDBC sang R2DBC mà truy vấn vẫn chậm, bạn sẽ phân tích execution plan và round trips như thế nào?
Nếu có lỗi unique constraint sau nhiều request đồng thời tạo cùng tài khoản, bạn sẽ đảm bảo API phản hồi nhất quán ra sao?
Nếu database failover làm kết nối trong pool bị lỗi, bạn sẽ điều chỉnh recovery, timeout và retry như thế nào?
Nếu một Flux bị client cancel giữa chừng mà connection không trở về pool, bạn sẽ điều tra resource lifecycle ra sao?
Nếu transaction kéo dài vì gọi HTTP bên ngoài trong lúc giữ connection, bạn sẽ thiết kế lại ranh giới giao dịch như thế nào?
Nếu hệ thống cần phát sự kiện ngay sau khi ghi database nhưng message broker bị lỗi, bạn sẽ áp dụng outbox hoặc phương án khác ra sao?
Nếu nhiều tenant dùng chung bảng và một custom SQL thiếu tenant filter, bạn sẽ sửa thiết kế và thêm test bảo vệ ra sao?
Nếu cần xây dựng tầng dữ liệu reactive Spring Boot mới, bạn sẽ chọn driver, ConnectionFactory, repository, R2dbcEntityTemplate, transaction, WebFlux và kiểm thử theo các bước nào?
