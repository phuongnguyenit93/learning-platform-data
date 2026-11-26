Bạn giải thích Spring Data JDBC hiện thực hóa repository cho cơ sở dữ liệu quan hệ mà không cần persistence context như JPA như thế nào?
Bạn phân biệt Spring Data JDBC với Spring JDBC và Spring Data JPA về mapping, lifecycle và cách phát sinh SQL ra sao?
Bạn đánh giá những đặc điểm nào của ứng dụng hoặc mô hình domain khiến Spring Data JDBC phù hợp hơn ORM có lazy loading?
Bạn mô tả cách tư duy Domain-Driven Design định hướng việc thiết kế aggregate root trong Spring Data JDBC ra sao?
Bạn phân biệt aggregate root, entity con và value object dựa trên ranh giới nhất quán nghiệp vụ như thế nào?
Bạn thiết kế một aggregate Order chứa OrderLine để thay đổi danh sách mặt hàng trong một transaction như thế nào?
Bạn dựa trên những invariant và nhu cầu cập nhật nào để quyết định một đối tượng nên là aggregate riêng thay vì entity con?
Bạn giải thích vì sao không nên mô hình hóa mọi khóa ngoại thành quan hệ đối tượng có thể điều hướng giữa các aggregate như thế nào?
Bạn lựa chọn cách tham chiếu giữa hai aggregate bằng ID hoặc AggregateReference để giữ ranh giới sở hữu dữ liệu ra sao?
Bạn phân tích rủi ro tạo vòng tham chiếu giữa các entity khi Spring Data JDBC phải lưu toàn bộ aggregate như thế nào?
Bạn thiết kế quy tắc bất biến của aggregate sao cho chỉ aggregate root có quyền thay đổi các entity thuộc sở hữu của nó như thế nào?
Bạn phân biệt việc nạp một aggregate từ database với việc tùy ý truy cập các bảng quan hệ không thuộc aggregate đó như thế nào?
Bạn quyết định khi nào cần read model riêng hoặc query DTO cho màn hình tổng hợp dữ liệu từ nhiều aggregate như thế nào?
Bạn đánh giá kích thước aggregate ảnh hưởng đến số thao tác SQL, contention và chi phí lưu trữ như thế nào?
Bạn xác định dấu hiệu aggregate quá lớn khi một thay đổi nhỏ liên tục tác động tới nhiều hàng phụ thuộc ra sao?
Bạn thiết kế ranh giới transaction khi một use case cần thay đổi hai aggregate độc lập nhưng vẫn cần xử lý lỗi nhất quán như thế nào?
Bạn phân biệt quan hệ tham chiếu bằng khóa ngoại ở database với ownership trong mô hình aggregate của Spring Data JDBC ra sao?
Bạn đánh giá sự đánh đổi giữa tính đơn giản của Spring Data JDBC và khả năng tối ưu dữ liệu quan hệ phức tạp của SQL tùy chỉnh như thế nào?
Bạn tổ chức tầng service, repository và aggregate để các quy tắc nghiệp vụ không phụ thuộc API của framework ra sao?
Bạn giải thích vai trò của Spring Data Commons trong hệ thống repository Spring Data JDBC như thế nào?
Bạn ánh xạ một aggregate root vào bảng bằng @Table và xác định quy ước tên bảng khi schema đã tồn tại như thế nào?
Bạn sử dụng @Id để xác định khóa định danh của root và xử lý kiểu dữ liệu ID phù hợp với database ra sao?
Bạn so sánh sinh khóa chính bằng identity, sequence hoặc ID được cấp từ ứng dụng và ảnh hưởng đến quá trình insert như thế nào?
Bạn phân biệt trạng thái entity mới với entity đã tồn tại dựa trên ID hoặc version khi repository quyết định insert hay update như thế nào?
Bạn thiết kế cách dùng Persistable.isNew cho aggregate có identifier được tạo trước khi gọi save như thế nào?
Bạn phân tích lỗi lưu aggregate có ID được cấp trước nhưng framework coi là bản ghi đã tồn tại thay vì bản ghi mới ra sao?
Bạn sử dụng @Column để ánh xạ property Java tới tên cột legacy và kiểm tra mapping khi đổi tên field như thế nào?
Bạn lựa chọn kiểu Java cho Decimal, số tiền và thời gian để bảo toàn precision hoặc timezone của dữ liệu quan hệ như thế nào?
Bạn quyết định khi nào một property được đánh dấu @Transient thay vì lưu trực tiếp vào bảng như thế nào?
Bạn thiết kế immutable aggregate root bằng constructor hoặc factory method để dữ liệu đọc lên luôn thỏa điều kiện khởi tạo như thế nào?
Bạn phân biệt constructor binding với setter-based population khi persistence layer tái tạo aggregate từ kết quả SQL ra sao?
Bạn xử lý việc thêm một property bắt buộc vào constructor khi database cũ còn các hàng chưa có giá trị tương ứng như thế nào?
Bạn đánh giá sự phù hợp của Java record làm value object trong một aggregate Spring Data JDBC như thế nào?
Bạn thiết kế một value object Address được nhúng vào bảng của aggregate root bằng @Embedded như thế nào?
Bạn phân biệt các chế độ onEmpty của @Embedded khi toàn bộ cột nhúng có giá trị null và domain cần phân biệt object vắng mặt ra sao?
Bạn tổ chức prefix cột cho nhiều value object cùng kiểu được nhúng trong một aggregate để tránh xung đột như thế nào?
Bạn phân tích khi nào một value object nên được lưu bằng nhiều cột và khi nào nên dùng custom conversion thành một cột như thế nào?
Bạn sử dụng custom converters để ánh xạ enum hoặc domain-specific identifier sang JDBC column type như thế nào?
Bạn xác định cách đăng ký JdbcCustomConversions và kiểm tra chiều đọc/ghi của converter cho kiểu dữ liệu riêng như thế nào?
Bạn kiểm thử round-trip mapping của một value object để tránh sai khác giữa dữ liệu được lưu và dữ liệu đọc lại như thế nào?
Bạn đánh giá rủi ro converter thực hiện I/O bên ngoài hoặc chứa logic nghiệp vụ khi framework đang ánh xạ một bản ghi như thế nào?
Bạn phân biệt tham chiếu ID đơn thuần với AggregateReference khi mô hình hóa quan hệ giữa Order và Customer ra sao?
Bạn thiết kế cách kiểm tra Customer tồn tại trước khi gán reference mà không biến hai aggregate thành cùng một đơn vị lưu trữ như thế nào?
Bạn xác định khi nào cần database foreign key để bổ sung tính toàn vẹn cho tham chiếu giữa các aggregate ra sao?
Bạn mô tả cách @MappedCollection ánh xạ collection entity con vào một bảng phụ thuộc aggregate root như thế nào?
Bạn giải thích vai trò của idColumn và keyColumn trong @MappedCollection đối với quan hệ parent-child và collection có thứ tự như thế nào?
Bạn phân biệt mapping List, Set và Map entity con theo nhu cầu định danh, thứ tự và ngữ nghĩa collection như thế nào?
Bạn thiết kế khóa cho bảng OrderLine khi mỗi phần tử cần có ID riêng và phải thuộc duy nhất một aggregate như thế nào?
Bạn xác định cách xử lý orphan child khi phần tử bị xóa khỏi collection của aggregate và root được lưu lại ra sao?
Bạn phân tích vì sao mô hình collection thuộc sở hữu aggregate khác với join table có dữ liệu được chia sẻ giữa nhiều root như thế nào?
Bạn lựa chọn cách mô hình hóa quan hệ one-to-one phụ thuộc root bằng một entity con hoặc embedded value object như thế nào?
Bạn xử lý tình huống entity con cần được truy vấn độc lập rất thường xuyên mà vẫn giữ ranh giới aggregate rõ ràng ra sao?
Bạn quyết định khi nào cấu trúc nhiều lớp entity con gây chi phí đọc và ghi không phù hợp cho Spring Data JDBC như thế nào?
Bạn thiết kế migration từ mô hình có quan hệ hai chiều trong JPA sang aggregate một chiều trong Spring Data JDBC như thế nào?
Bạn phân biệt lưu aggregate bằng JdbcAggregateTemplate với gọi trực tiếp repository theo mức độ kiểm soát operation ra sao?
Bạn mô tả các bước Spring Data JDBC thực hiện khi save một aggregate root mới có nhiều entity con như thế nào?
Bạn giải thích vì sao Spring Data JDBC không theo dõi dirty changes của managed entity giữa các lời gọi repository như JPA ra sao?
Bạn thiết kế workflow sửa một aggregate theo chuỗi load, thay đổi trạng thái, save và xác nhận kết quả như thế nào?
Bạn phân tích cách Spring Data JDBC thường thay thế hoặc ghi lại các hàng con thuộc aggregate khi save một root đã tồn tại như thế nào?
Bạn xác định chi phí khi lưu lại aggregate chứa collection lớn dù chỉ một phần tử con thay đổi như thế nào?
Bạn lựa chọn thao tác save toàn aggregate hay SQL cập nhật mục tiêu khi nghiệp vụ cần thay đổi thường xuyên một child record ra sao?
Bạn giải thích vì sao can thiệp SQL trực tiếp vào bảng con có thể phá vỡ các invariant mà aggregate root quản lý như thế nào?
Bạn thiết kế phép thử kiểm tra những hàng con được delete hoặc insert khi repository lưu lại aggregate đã chỉnh sửa collection ra sao?
Bạn phân biệt insert với update ở cấp aggregate khi version hoặc identifier khiến framework xác định trạng thái tồn tại như thế nào?
Bạn xử lý dữ liệu con bị trùng identifier hoặc trùng thứ tự collection khi insert lại các hàng phụ thuộc ra sao?
Bạn xác định thời điểm ID mới được gán cho root hoặc child sau insert và cách tránh dùng giá trị cũ trong entity bất biến như thế nào?
Bạn kiểm tra object trả về từ save để sử dụng đúng aggregate có ID, version hoặc dữ liệu được framework cập nhật như thế nào?
Bạn phân tích khi nào delete một aggregate có thể xóa các hàng con do aggregate sở hữu và cần kiểm tra foreign key constraints ra sao?
Bạn thiết kế thao tác xóa một aggregate có reference tới aggregate khác để không xóa nhầm dữ liệu thuộc sở hữu của bên kia như thế nào?
Bạn phân biệt deleteById với xóa aggregate đã tải về theo ảnh hưởng tới lifecycle callbacks và các điều kiện nghiệp vụ như thế nào?
Bạn tổ chức lưu lại aggregate sau một command xử lý nghiệp vụ mà không truyền entity con qua nhiều tầng ứng dụng như thế nào?
Bạn quyết định khi nào định nghĩa repository method chỉ đọc để tránh vô tình cấp quyền save hoặc delete cho một thành phần ra sao?
Bạn mô tả cách Spring Data JDBC materialize aggregate từ các hàng quan hệ và quản lý các entity con như thế nào?
Bạn so sánh số câu SQL khi đọc aggregate có nhiều collection với chiến lược dùng query DTO chỉ lấy trường cần thiết ra sao?
Bạn giải thích vì sao Spring Data JDBC không mặc định cung cấp lazy loading trong suốt vòng đời object như JPA ra sao?
Bạn xác định cách chẩn đoán tình huống đọc danh sách aggregate gây quá nhiều query khi mỗi root có nhiều entity con như thế nào?
Bạn đánh giá khả năng sử dụng cơ chế single-query loading ở những phiên bản và kiểu aggregate được hỗ trợ thay vì coi nó luôn bật ra sao?
Bạn thiết kế truy vấn read model bằng JdbcTemplate hoặc NamedParameterJdbcTemplate khi cần join nhiều bảng cho báo cáo như thế nào?
Bạn phân biệt read projection dùng SQL join với thao tác ghi lại aggregate để không thay đổi ranh giới ownership ra sao?
Bạn xác định trường hợp nào nên dùng CQRS read model riêng để giảm chi phí tải đầy đủ aggregate cho API danh sách như thế nào?
Bạn lựa chọn CrudRepository, ListCrudRepository hoặc PagingAndSortingRepository theo những phương thức thực tế mà application cần ra sao?
Bạn giải thích Spring Data JDBC tạo repository implementation và gắn SQL statements với domain mapping như thế nào?
Bạn tổ chức base repository interface cùng @NoRepositoryBean để tránh framework cố tạo bean cho interface trừu tượng như thế nào?
Bạn thiết kế derived query method lọc theo trạng thái và thời gian mà vẫn dễ đọc và không phụ thuộc tên cột vật lý như thế nào?
Bạn xác định hạn chế của derived queries trong Spring Data JDBC đối với điều kiện cần join qua nhiều aggregate như thế nào?
Bạn phân biệt truy vấn theo thuộc tính trực tiếp của aggregate root với truy vấn theo collection con và khi nào cần SQL tùy chỉnh như thế nào?
Bạn thiết kế phương thức findBy... trả Optional để phân biệt không tìm thấy và kết quả tồn tại mà không che lỗi truy vấn ra sao?
Bạn giải thích khi nào một query method trả List, Stream hoặc Page và những chi phí hoặc giới hạn truy cập dữ liệu ra sao?
Bạn lựa chọn truy vấn count hoặc exists thay vì load toàn bộ aggregate chỉ để biết số lượng hay kiểm tra sự tồn tại như thế nào?
Bạn thiết kế phân trang và sắp xếp bằng Pageable, PageRequest và Sort cho màn hình danh sách aggregate như thế nào?
Bạn phân biệt Page và Slice theo nhu cầu tổng số phần tử và chi phí count query trên bảng lớn ra sao?
Bạn phân tích rủi ro thiếu thứ tự xác định khi phân trang dữ liệu có nhiều hàng cùng giá trị createdAt như thế nào?
Bạn quyết định khi nào cần keyset-based pagination hoặc custom SQL thay vì offset paging với chỉ số trang lớn như thế nào?
Bạn thiết kế chính sách giới hạn page size và các trường sort được phép để không cho client tạo query quá đắt như thế nào?
Bạn kiểm tra query do repository tạo ra bằng SQL logs hoặc trace khi một derived query không trả đúng dữ liệu ra sao?
Bạn lựa chọn @Query với SQL tường minh thay vì derived query khi điều kiện lọc hoặc phép join phức tạp như thế nào?
Bạn phân biệt @Query trong Spring Data JDBC với JPQL của JPA về cú pháp và thực thể được truy vấn như thế nào?
Bạn thiết kế native SQL query có named parameters để tránh nối input người dùng vào SQL string như thế nào?
Bạn sử dụng @Query để lấy aggregate root và đánh giá các điều kiện cần thiết để entity mapping hoặc child loading vẫn đúng như thế nào?
Bạn phân biệt mapped entity result với DTO hoặc interface projection khi một custom SELECT chỉ lấy một phần cột như thế nào?
Bạn thiết kế một repository method trả DTO cho báo cáo kết hợp Order và Customer mà không khởi tạo toàn bộ aggregate như thế nào?
Bạn sử dụng RowMapper tùy biến khi kết quả SQL có cấu trúc không ánh xạ trực tiếp vào domain object ra sao?
Bạn phân tích tác động của column aliases lên việc mapping kết quả SQL vào property hoặc projection như thế nào?
Bạn lựa chọn sử dụng NamedParameterJdbcTemplate trong custom repository fragment khi cần SQL động có danh sách tham số như thế nào?
Bạn thiết kế một custom repository fragment phục vụ tìm kiếm nhiều điều kiện tùy chọn mà không xây tên method quá dài như thế nào?
Bạn xác định cách mở rộng repository bằng custom implementation nhưng vẫn giữ logic transaction và mapping nhất quán như thế nào?
Bạn phân biệt truy vấn SQL phục vụ reporting với command cập nhật aggregate để không sử dụng cùng một API tùy ý như thế nào?
Bạn sử dụng @Modifying cùng @Query trong trường hợp nào và xử lý kết quả số hàng bị ảnh hưởng ra sao?
Bạn xác định những rủi ro khi dùng SQL UPDATE trực tiếp mà bỏ qua optimistic locking và lifecycle callbacks của aggregate như thế nào?
Bạn thiết kế một custom SQL update có điều kiện version để giữ bảo đảm kiểm soát cạnh tranh như thế nào?
Bạn xử lý câu lệnh SQL không cập nhật hàng nào bằng cách phân biệt bản ghi vắng mặt, version conflict và điều kiện nghiệp vụ sai ra sao?
Bạn lựa chọn phương thức batch update bằng JDBC khi cần xử lý tập dữ liệu lớn và không cần reconstitute toàn bộ aggregate như thế nào?
Bạn đánh giá vì sao gọi saveAll không đồng nghĩa mọi thao tác được gộp thành một SQL batch tối ưu trên mọi driver như thế nào?
Bạn thiết kế kiểm thử SQL tùy chỉnh có join, grouping và pagination để xác minh dữ liệu trả về khớp hợp đồng nghiệp vụ như thế nào?
Bạn xác định mức độ phụ thuộc của custom SQL vào dialect khi ứng dụng phải hỗ trợ PostgreSQL và MySQL như thế nào?
Bạn giải thích vai trò của RelationalMappingContext và metadata mapping trong việc xác định bảng, cột và các entity con như thế nào?
Bạn quyết định khi nào cần NamingStrategy tùy biến vì tên bảng và cột của hệ thống cũ không theo quy ước mặc định như thế nào?
Bạn xử lý khóa chính tổng hợp hoặc lược đồ legacy không phù hợp với mapping mặc định của Spring Data JDBC bằng thiết kế nào?
Bạn giải thích transaction boundary của Spring Data JDBC nên được đặt ở tầng service hay repository theo từng use case như thế nào?
Bạn thiết kế một @Transactional service method thay đổi hai repository và bảo đảm rollback khi có lỗi ở bước cuối như thế nào?
Bạn phân biệt transaction do Spring TransactionManager điều phối với không gian lưu trạng thái entity được quản lý bởi JPA như thế nào?
Bạn chọn DataSourceTransactionManager hoặc JdbcTransactionManager phù hợp khi ứng dụng dùng DataSource và JDBC như thế nào?
Bạn giải thích tác động của transaction propagation REQUIRED, REQUIRES_NEW và MANDATORY trong một workflow ghi nhiều aggregate ra sao?
Bạn phân tích rủi ro một transaction REQUIRES_NEW commit thành công nhưng transaction nghiệp vụ bao ngoài sau đó rollback như thế nào?
Bạn xử lý lỗi self-invocation khiến @Transactional không được áp dụng khi một phương thức gọi phương thức khác trên cùng bean như thế nào?
Bạn kiểm tra rollback rules đối với checked exception và runtime exception trong service dùng Spring Data JDBC ra sao?
Bạn thiết kế cách phản hồi khi một exception đã bị catch nhưng transaction thực tế cần được rollback để tránh lưu trạng thái dở dang như thế nào?
Bạn lựa chọn transaction isolation phù hợp để giảm non-repeatable read hoặc phantom read theo mức bảo đảm của database như thế nào?
Bạn phân biệt write atomicity của một SQL statement với tính nguyên tử của nhiều câu SQL dùng để lưu một aggregate như thế nào?
Bạn giải thích vì sao việc lưu root và nhiều child records cần transaction nhất quán để tránh tình trạng aggregate được ghi một phần ra sao?
Bạn phân tích ảnh hưởng của một transaction dài có lời gọi HTTP bên ngoài đối với connection pool và khóa database như thế nào?
Bạn đánh giá khi nào nên kết thúc transaction trước khi phát một thông điệp ra broker và cách tránh mất event như thế nào?
Bạn thiết kế outbox pattern với Spring Data JDBC để liên kết cập nhật aggregate và tạo event record trong cùng transaction như thế nào?
Bạn phân biệt event được công bố trong tiến trình qua callback với event đã được broker nhận bền vững trong kiến trúc tích hợp như thế nào?
Bạn xác định cách xử lý deadlock hoặc transient connection error mà không phát lại side effect không idempotent như thế nào?
Bạn xây dựng retry policy cho lỗi transaction có thể phục hồi nhưng không retry vô hạn lỗi constraint hoặc validation ra sao?
Bạn giải thích cách @Version hỗ trợ optimistic locking khi hai request đồng thời thay đổi cùng aggregate root như thế nào?
Bạn thiết kế test đồng thời để một request lưu thành công và request còn lại nhận lỗi version conflict như thế nào?
Bạn phân biệt sử dụng @Version với kiểm tra version thủ công trong custom SQL update theo khả năng tự động bảo vệ ra sao?
Bạn phân tích vì sao optimistic locking không thay thế unique constraint khi hai request cùng tạo một bản ghi mới như thế nào?
Bạn xác định cách truyền version từ API tới service để ngăn một update dựa trên dữ liệu đã lỗi thời như thế nào?
Bạn xử lý OptimisticLockingFailureException bằng cách trả conflict hay đọc lại và merge theo quy tắc nghiệp vụ như thế nào?
Bạn thiết kế idempotent command để retry khi xảy ra version conflict mà không tạo thêm invoice hoặc payment ngoài ý muốn như thế nào?
Bạn phân biệt optimistic locking với SELECT FOR UPDATE hoặc khóa bi quan ở database theo mức contention và khả năng retry ra sao?
Bạn quyết định khi nào cần SQL locking tùy biến vì Spring Data JDBC không cung cấp lifecycle quản lý entity như JPA ra sao?
Bạn xây dựng custom SQL dùng SELECT FOR UPDATE bên trong transaction để bảo vệ một workflow tranh chấp cao như thế nào?
Bạn xử lý tình huống nhiều request lấy khóa ở thứ tự khác nhau dẫn tới deadlock bằng chiến lược nào?
Bạn phân tích tác động của optimistic locking trên root khi nhiều thay đổi xảy ra ở các entity con thuộc cùng aggregate như thế nào?
Bạn thiết kế một command cập nhật phần tử con để bảo toàn invariant và version của aggregate root như thế nào?
Bạn phân biệt optimistic locking tại aggregate root với concurrency control cho các bảng đọc độc lập hoặc read model như thế nào?
Bạn giải thích vai trò của @CreatedDate và @LastModifiedDate khi bật auditing trên aggregate Spring Data JDBC như thế nào?
Bạn cấu hình @EnableJdbcAuditing và AuditorAware để ghi nhận createdBy hoặc lastModifiedBy cho những lệnh save hợp lệ ra sao?
Bạn quyết định nguồn actor nào được dùng trong auditing khi tác vụ được thực thi bởi batch job hoặc background worker không có user đăng nhập như thế nào?
Bạn phân biệt annotation auditing với một bảng audit log bất biến cần lưu toàn bộ lịch sử sửa đổi ra sao?
Bạn xử lý việc chuyển từ entity có mutable audit fields sang immutable aggregate mà vẫn cập nhật metadata khi save như thế nào?
Bạn xác định thời điểm callback BeforeConvert có thể hỗ trợ chuẩn bị ID trước khi chuyển aggregate thành các SQL statements như thế nào?
Bạn phân biệt BeforeSave và AfterSave callbacks về mục đích và trạng thái aggregate tại mỗi mốc như thế nào?
Bạn thiết kế một EntityCallback xử lý dữ liệu kỹ thuật nhưng không gọi API bên ngoài trong transaction đang lưu aggregate như thế nào?
Bạn phân tích vì sao một callback sửa nội dung nghiệp vụ không được kiểm soát có thể vi phạm invariant của aggregate ra sao?
Bạn so sánh lifecycle callbacks đồng bộ với sự kiện domain được công bố qua @DomainEvents về yêu cầu quan sát và side effect như thế nào?
Bạn xác định giới hạn của @DomainEvents và @AfterDomainEventPublication khi không phải mọi thao tác SQL tùy chỉnh đều đi qua repository save như thế nào?
Bạn thiết kế cơ chế phát sự kiện đáng tin cậy khi transaction rollback nhưng listener đã tạo side effect bên ngoài như thế nào?
Bạn kiểm thử auditing và callbacks bằng cách lưu rồi đọc lại dữ liệu thực thay vì chỉ kiểm tra object đang ở bộ nhớ như thế nào?
Bạn thiết kế migration thêm bảng entity con cho một aggregate đã tồn tại và bảo đảm tương thích trong rolling deployment ra sao?
Bạn sử dụng Flyway hoặc Liquibase để quản lý schema thay vì phụ thuộc vào mapping annotations tự tạo bảng ở production như thế nào?
Bạn chuẩn bị migration đổi tên cột trên dữ liệu lớn với chiến lược expand-and-contract giữa nhiều phiên bản ứng dụng như thế nào?
Bạn kiểm tra foreign keys, unique constraints và index trong database có khớp ranh giới aggregate và truy vấn phổ biến như thế nào?
Bạn thiết kế index cho các câu SQL lọc theo tenant, trạng thái và thời gian để tránh full table scan không cần thiết như thế nào?
Bạn sử dụng explain plan và SQL query logs để kiểm tra một truy vấn Spring Data JDBC đang chậm vì join hoặc sort như thế nào?
Bạn phân biệt bottleneck do connection pool cạn với bottleneck do thiếu index hoặc do lưu aggregate quá lớn như thế nào?
Bạn đánh giá chi phí delete/reinsert child rows khi save aggregate qua metric SQL và dữ liệu có quy mô đại diện ra sao?
Bạn lựa chọn kích thước connection pool và transaction timeout dựa trên đặc điểm workload đọc và ghi trong Spring Data JDBC như thế nào?
Bạn phân tích vì sao không nên truyền aggregate sang thread khác rồi giả định transaction hiện tại vẫn được duy trì như thế nào?
Bạn thiết kế batch import dữ liệu theo nhiều transaction nhỏ để tránh giữ quá nhiều hàng bị khóa hoặc tốn connection lâu như thế nào?
Bạn so sánh Spring Data JDBC blocking repositories với Spring Data R2DBC reactive repositories khi xây dựng API WebFlux ra sao?
Bạn xử lý thư viện JDBC blocking trong một pipeline reactive mà không giữ Netty event-loop thread như thế nào?
Bạn xác định khi nào thay repository JDBC bằng repository R2DBC cần thay cả transaction và driver semantics như thế nào?
Bạn thiết kế kiểm thử repository dùng @DataJdbcTest để xác minh mapping aggregate và các SQL queries mà không khởi chạy toàn bộ web server như thế nào?
Bạn lựa chọn Testcontainers với cùng engine database production để phát hiện lỗi dialect, constraints và transaction khác H2 như thế nào?
Bạn thiết kế fixture gồm root với collection con và value object nhúng để kiểm tra đầy đủ round-trip load/save như thế nào?
Bạn kiểm thử thay đổi collection con rồi save lại aggregate để xác minh các hàng con bị xóa, thêm và giữ đúng thứ tự như thế nào?
Bạn xác minh optimistic locking trong hai transaction độc lập bằng test có điều khiển đồng bộ thay vì chỉ chạy lần lượt như thế nào?
Bạn kiểm thử một transaction ghi root thành công nhưng insert child thất bại để bảo đảm database không còn dữ liệu dở dang như thế nào?
Bạn kiểm tra auditing, callback và domain event khi save root với ID mới rồi cập nhật cùng aggregate như thế nào?
Bạn thiết kế test cho SQL @Query có named parameters, paging và projection dùng dữ liệu null hoặc ký tự Unicode như thế nào?
Bạn xác định các thử nghiệm nào bắt buộc dùng database thật thay vì mock repository để kiểm tra constraint và generated keys ra sao?
Bạn dùng @Sql hoặc migration test setup để chuẩn bị dữ liệu chuẩn mà không để test phụ thuộc vào thứ tự thực thi như thế nào?
Bạn phân biệt unit test invariant trong aggregate với integration test persistence để phát hiện hai nhóm lỗi khác nhau ra sao?
Bạn đánh giá tác động của rollback mặc định trong integration test khi muốn kiểm chứng commit hoặc callback sau transaction như thế nào?
Bạn thiết kế bài benchmark so sánh save một aggregate nhỏ với aggregate chứa hàng nghìn children để đánh giá giới hạn mô hình như thế nào?
Bạn điều tra sự cố sau khi thay đổi @MappedCollection khiến repository nạp được root nhưng không nạp đúng danh sách con qua những bước nào?
Bạn chẩn đoán lỗi duplicate key khi hai service instances cùng tạo aggregate mang cùng business identifier bằng những dữ liệu nào?
Bạn xử lý trường hợp update aggregate từ request cũ làm mất một thay đổi child record của request khác bằng chiến lược versioning như thế nào?
Bạn phân tích một sự cố production khi thời gian save tăng theo số lượng phần tử con và đề xuất thay đổi aggregate boundary hoặc SQL theo tiêu chí nào?
Bạn đề xuất thiết kế Spring Data JDBC cho một hệ thống đơn hàng có aggregate rõ ràng, mapping quan hệ, SQL read model, optimistic locking, auditing và kiểm thử transaction như thế nào?
