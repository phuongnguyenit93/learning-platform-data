Bạn giải thích Spring Data JPA giải quyết những công việc nào trong tầng persistence và còn phụ thuộc vào JPA provider ra sao?
Bạn phân biệt Spring Data JPA, Jakarta Persistence và Hibernate theo trách nhiệm khi một repository thực hiện truy vấn như thế nào?
Bạn thiết kế ranh giới giữa controller, application service, domain model và repository để không đưa quy tắc nghiệp vụ vào tầng truy cập dữ liệu như thế nào?
Bạn lựa chọn khi nào dùng JpaRepository thay vì CrudRepository hoặc một repository interface chỉ công bố phương thức cần thiết như thế nào?
Bạn giải thích cách Spring Data tạo repository proxy và gắn phương thức truy vấn vào cơ chế thực thi của JPA như thế nào?
Bạn thiết kế một aggregate root và repository tương ứng khi dữ liệu quan hệ chứa nhiều bảng phụ thuộc như thế nào?
Bạn mô tả vai trò của @Entity, @Table và @Id khi ánh xạ một lớp Java vào bảng dữ liệu như thế nào?
Bạn phân biệt entity JPA với DTO hoặc object chỉ phục vụ biểu diễn dữ liệu ra sao?
Bạn xác định tiêu chí chọn kiểu khóa chính cho entity khi hệ thống cần tạo dữ liệu ở nhiều node như thế nào?
Bạn so sánh các chiến lược sinh ID như IDENTITY, SEQUENCE và UUID theo khả năng hỗ trợ database và hiệu quả ghi theo lô như thế nào?
Bạn thiết kế việc sử dụng sequence allocation để giảm round-trip nhưng vẫn bảo đảm quy tắc định danh như thế nào?
Bạn xử lý tình huống ID được gán từ trước khiến Spring Data JPA khó nhận biết entity mới hoặc đã tồn tại ra sao?
Bạn quyết định khi nào triển khai Persistable để tùy biến isNew thay vì dựa vào ID hoặc version field như thế nào?
Bạn lựa chọn @Column cho nullable, unique, length và precision khi hợp đồng dữ liệu yêu cầu chính xác về phạm vi giá trị như thế nào?
Bạn phân biệt ràng buộc được mô tả trong entity với constraint thực sự được database thực thi ra sao?
Bạn thiết kế mapping BigDecimal cho tiền tệ để tránh sai số và tràn precision ở database như thế nào?
Bạn chọn cách lưu Instant, LocalDateTime hoặc OffsetDateTime tùy ý nghĩa thời gian và khả năng của database như thế nào?
Bạn phân tích nguy cơ lưu ngày giờ thiếu timezone trong ứng dụng chạy đa khu vực và cách kiểm thử như thế nào?
Bạn giải thích vì sao @Enumerated(EnumType.STRING) thường dễ tiến hóa hơn ordinal và những rủi ro vẫn còn tồn tại ra sao?
Bạn xử lý tình huống cần đổi tên một giá trị enum đã được lưu trong database mà không làm hỏng dữ liệu cũ như thế nào?
Bạn quyết định dùng AttributeConverter khi một kiểu dữ liệu nghiệp vụ có định dạng lưu trữ riêng như thế nào?
Bạn thiết kế @Embeddable và @Embedded để tái sử dụng một nhóm trường như địa chỉ hoặc thông tin tiền tệ như thế nào?
Bạn phân biệt @EmbeddedId và @IdClass khi một entity có khóa chính ghép và đánh giá ảnh hưởng tới repository như thế nào?
Bạn xác định cách triển khai equals và hashCode cho entity có ID sinh sau persist mà không làm hỏng Set hoặc Map như thế nào?
Bạn phân tích tác động của Hibernate proxy và lazy initialization lên equals, hashCode và toString của entity như thế nào?
Bạn quyết định khi nào không nên dùng @Data hoặc tự động tạo toString cho một JPA entity có nhiều quan hệ như thế nào?
Bạn xây dựng ánh xạ @ManyToOne với khóa ngoại và xác định phía nào sở hữu quan hệ như thế nào?
Bạn phân biệt @OneToMany một chiều với quan hệ hai chiều về SQL sinh ra và khả năng quản lý aggregate ra sao?
Bạn giải thích vai trò của mappedBy trong một quan hệ hai chiều và cách đồng bộ trạng thái giữa hai phía như thế nào?
Bạn thiết kế helper method để thêm hoặc xóa phần tử khỏi một quan hệ hai chiều mà không tạo trạng thái in-memory mâu thuẫn ra sao?
Bạn phân biệt cascade PERSIST, MERGE và REMOVE khi thao tác trên aggregate chứa các entity con như thế nào?
Bạn xác định khi nào cascade REMOVE nguy hiểm đối với entity được chia sẻ giữa nhiều aggregate như thế nào?
Bạn giải thích orphanRemoval khác với cascade REMOVE trong tình huống xóa một phần tử khỏi collection như thế nào?
Bạn lựa chọn @ManyToMany trực tiếp hay một join entity riêng khi bảng liên kết có metadata nghiệp vụ như thế nào?
Bạn đánh giá tác động của List, Set và Map khi ánh xạ collection quan hệ và cần tránh ghi lại không cần thiết ra sao?
Bạn xử lý thứ tự hiển thị các phần tử quan hệ bằng @OrderBy hoặc @OrderColumn theo sự khác biệt nào về dữ liệu lưu trữ?
Bạn thiết kế mapping kế thừa JPA bằng SINGLE_TABLE, JOINED hoặc TABLE_PER_CLASS theo chi phí truy vấn và schema như thế nào?
Bạn phân biệt @MappedSuperclass với entity inheritance khi các lớp con cần dùng chung trường audit hoặc ID ra sao?
Bạn xác định cách ánh xạ một thuộc tính có dữ liệu lớn hoặc ít dùng để không khiến các truy vấn thường xuyên tải quá nhiều dữ liệu như thế nào?
Bạn xử lý dữ liệu JSON hoặc loại cột đặc thù database trong JPA mà không giả định mọi dialect hỗ trợ giống nhau ra sao?
Bạn quyết định chiến lược naming và mapping cho database schema đã tồn tại nhưng không tuân theo quy ước đặt tên Java như thế nào?
Bạn mô tả các trạng thái transient, managed, detached và removed của một entity trong JPA lifecycle như thế nào?
Bạn giải thích persistence context là gì và nó liên quan đến một transaction hoặc EntityManager ra sao?
Bạn phân biệt persist với merge theo trạng thái entity và đối tượng được trả về từ merge như thế nào?
Bạn xác định vì sao chỉnh sửa một managed entity có thể dẫn tới UPDATE khi transaction flush mà không gọi save lại như thế nào?
Bạn mô tả cơ chế dirty checking và ảnh hưởng của nó đến số câu lệnh SQL được sinh như thế nào?
Bạn phân biệt flush với commit và chỉ ra vì sao flush không đồng nghĩa dữ liệu đã được giao dịch khác nhìn thấy ra sao?
Bạn xử lý tình huống một truy vấn phát sinh SQL trước commit do cơ chế flush tự động như thế nào?
Bạn lựa chọn flush mode khi cần kiểm soát thời điểm đồng bộ thay đổi nhưng vẫn giữ tính nhất quán của truy vấn như thế nào?
Bạn giải thích ảnh hưởng của EntityManager.clear và detach đối với các entity đã được tải trong cùng transaction ra sao?
Bạn thiết kế cập nhật một detached entity để tránh ghi đè các trường bị thay đổi bởi transaction khác như thế nào?
Bạn phân tích vì sao saveAndFlush không phải công cụ thay thế ranh giới transaction hợp lý như thế nào?
Bạn quyết định khi nào cần gọi EntityManager.flush để phát hiện lỗi constraint sớm trong một workflow như thế nào?
Bạn giải thích cache cấp một của persistence context ảnh hưởng đến việc gọi findById hai lần trong cùng ngữ cảnh như thế nào?
Bạn phân biệt cache cấp một với cache cấp hai của provider theo phạm vi, thời gian sống và rủi ro dữ liệu cũ ra sao?
Bạn thiết kế test chứng minh cùng một entity trong persistence context được quản lý theo identity map như thế nào?
Bạn xác định khi nào entity lifecycle callbacks như @PrePersist và @PreUpdate nên được dùng thay vì logic nghiệp vụ ở service như thế nào?
Bạn phân tích rủi ro callback entity gọi dịch vụ ngoài hoặc truy vấn repository khi flush đang diễn ra ra sao?
Bạn quyết định cách tổ chức transaction ở tầng service khi một thao tác nghiệp vụ phải thay đổi nhiều aggregate như thế nào?
Bạn giải thích @Transactional ở service khác gì với transaction mặc định của một số phương thức repository được Spring Data JPA cung cấp ra sao?
Bạn phân biệt propagation REQUIRED, REQUIRES_NEW và MANDATORY qua tình huống ghi nghiệp vụ và audit log như thế nào?
Bạn nhận diện rủi ro khi đặt REQUIRES_NEW cho một thao tác ghi phụ mà transaction cha sau đó rollback như thế nào?
Bạn giải thích vì sao gọi phương thức @Transactional từ chính cùng một bean có thể bỏ qua proxy advice như thế nào?
Bạn xử lý tình huống transaction không hoạt động khi gọi phương thức private hoặc đối tượng không do Spring quản lý như thế nào?
Bạn xác định khi nào cần đánh dấu transaction readOnly và vì sao nó không thay thế kiểm soát quyền ghi ở database ra sao?
Bạn phân tích tác động của transaction kéo dài trong lúc gọi HTTP service bên ngoài đối với connection pool và khả năng khóa như thế nào?
Bạn lựa chọn isolation level khi nghiệp vụ không chấp nhận dirty read, non-repeatable read hoặc phantom read như thế nào?
Bạn giải thích vì sao việc khai báo isolation ở Spring không đủ bảo đảm hành vi giống nhau trên mọi hệ quản trị database ra sao?
Bạn thiết kế test đồng thời để quan sát lost update hoặc dữ liệu không lặp lại dưới isolation đang sử dụng như thế nào?
Bạn phân biệt rollback mặc định với cấu hình rollbackFor khi một checked exception xuất hiện trong service như thế nào?
Bạn xử lý tình huống exception đã bị catch nên transaction vẫn commit dù workflow thực tế thất bại như thế nào?
Bạn xác định các dấu hiệu khiến transaction ở trạng thái rollback-only nhưng code vẫn cố commit sau đó ra sao?
Bạn so sánh optimistic locking với pessimistic locking về số lần tranh chấp, độ trễ và khả năng scale như thế nào?
Bạn thiết kế @Version để phát hiện hai transaction cùng cập nhật một entity và quyết định cách phản hồi cho người dùng ra sao?
Bạn xử lý OptimisticLockException bằng retry có kiểm soát mà không phát lại các side effect không idempotent như thế nào?
Bạn giải thích khi nào nên dùng LockModeType.PESSIMISTIC_WRITE và ảnh hưởng tới contention hoặc deadlock ra sao?
Bạn kiểm tra một truy vấn khóa bi quan chỉ thực sự áp dụng trong transaction và hành vi timeout của database như thế nào?
Bạn thiết kế thứ tự truy cập các hàng dữ liệu để giảm nguy cơ deadlock giữa hai workflow cập nhật nhiều entity như thế nào?
Bạn so sánh khóa ở cấp database với cơ chế idempotency khi hai HTTP request cùng tạo một tài nguyên nghiệp vụ như thế nào?
Bạn xác định cách xử lý unique constraint violation khi hai transaction đều vượt qua bước kiểm tra tồn tại trước khi insert ra sao?
Bạn thiết kế chính sách retry cho transient database failure khác với lỗi validation hoặc constraint violation như thế nào?
Bạn phân tích một transaction bị rollback sau khi message đã gửi sang broker và chọn outbox pattern để bảo đảm nhất quán như thế nào?
Bạn giải thích cơ chế query derivation của Spring Data JPA và các hạn chế khi method name bắt đầu quá phức tạp như thế nào?
Bạn thiết kế một repository method lọc theo trạng thái, khoảng thời gian và sắp xếp mà vẫn dễ đọc như thế nào?
Bạn phân biệt query theo identifier bằng phương thức repository có sẵn với derived query theo thuộc tính tên id khác ra sao?
Bạn lựa chọn @Query JPQL khi cần join hoặc aggregation phức tạp mà method name không còn phù hợp như thế nào?
Bạn phân biệt JPQL với SQL native về đối tượng truy vấn, khả năng portable và cách ánh xạ kết quả ra sao?
Bạn giải thích cách JPQL tham chiếu entity name và property thay vì trực tiếp tên bảng và tên cột như thế nào?
Bạn thiết kế truy vấn JPQL dùng constructor expression để trả về DTO mà không tải toàn bộ entity như thế nào?
Bạn lựa chọn named parameters trong @Query để giảm nguy cơ nhầm thứ tự khi có nhiều điều kiện lọc ra sao?
Bạn xử lý điều kiện truy vấn tùy chọn mà không tạo một câu JPQL chứa quá nhiều nhánh OR gây kém hiệu quả như thế nào?
Bạn quyết định dùng nativeQuery khi cần cú pháp hoặc tính năng riêng của database và kiểm thử khả năng di chuyển ra sao?
Bạn ánh xạ kết quả native query tới interface projection hoặc DTO khi cột và alias không trùng thuộc tính Java như thế nào?
Bạn phân tích nguy cơ SQL injection khi nối trực tiếp sort field hoặc điều kiện do client gửi vào native SQL như thế nào?
Bạn xác định khi nào cần @Modifying cho một @Query thực hiện UPDATE hoặc DELETE và ranh giới transaction của nó ra sao?
Bạn giải thích bulk UPDATE hoặc DELETE qua JPQL ảnh hưởng thế nào đến persistence context chứa những entity đã được tải ra sao?
Bạn xử lý nhu cầu clear hoặc flush persistence context sau bulk operation để tránh đọc trạng thái cũ như thế nào?
Bạn phân biệt delete entity theo vòng đời JPA với bulk delete về callbacks, cascade và hiệu quả thực thi ra sao?
Bạn sử dụng Spring Data JPA Specifications để kết hợp các predicate tìm kiếm động theo cách nào?
Bạn thiết kế một Specification có thể tái sử dụng và kết hợp AND/OR mà không biến nó thành nơi chứa logic nghiệp vụ ra sao?
Bạn phân biệt Specification với Query by Example khi các bộ lọc cần range, join hoặc biểu thức phức tạp như thế nào?
Bạn kiểm tra tác động của join trong Specification tới số dòng dữ liệu và count query phục vụ phân trang như thế nào?
Bạn quyết định khi nào sử dụng Criteria API hoặc custom repository implementation thay vì cố mở rộng Specifications như thế nào?
Bạn mô tả cách truyền Pageable tới repository method và bảo vệ giới hạn kích thước trang từ phía client như thế nào?
Bạn phân biệt Page, Slice và List về dữ liệu trả về và chi phí count query như thế nào?
Bạn thiết kế sort có khóa phụ duy nhất để kết quả phân trang ổn định khi nhiều entity có cùng giá trị createdAt ra sao?
Bạn nhận biết nguy cơ mất hoặc lặp bản ghi giữa các trang khi dùng offset pagination trên bảng đang cập nhật liên tục như thế nào?
Bạn quyết định khi nào dùng keyset scrolling thay cho offset paging và cách lựa chọn bộ trường sắp xếp như thế nào?
Bạn phân tích rủi ro về số dòng kết quả và phân trang tại database khi dùng JOIN FETCH một collection, rồi đề xuất cách khắc phục như thế nào?
Bạn thiết kế truy vấn phân trang danh sách parent và tải collection cần thiết theo hai bước để tránh vấn đề fetch join như thế nào?
Bạn phân biệt interface-based projection, DTO projection và dynamic projection của Spring Data JPA theo khả năng tối ưu truy vấn ra sao?
Bạn lựa chọn projection thay vì trả entity khi API chỉ cần một số trường và không muốn lộ quan hệ nội bộ như thế nào?
Bạn đánh giá rủi ro nested projection kích hoạt join hoặc truy xuất thêm dữ liệu tùy cách store thực thi ra sao?
Bạn thiết kế kiểm thử kiểm tra một projection thực sự giảm số cột hoặc số truy vấn chứ không chỉ thay đổi kiểu trả về như thế nào?
Bạn sử dụng @EntityGraph trên repository method để khai báo những quan hệ cần tải cho một màn hình cụ thể như thế nào?
Bạn phân biệt FetchType.LAZY và FetchType.EAGER theo hợp đồng nạp dữ liệu và nguy cơ N+1 trong truy vấn như thế nào?
Bạn giải thích vì sao EAGER không bảo đảm luôn dùng một SQL JOIN và vẫn có thể gây nhiều câu lệnh phụ ra sao?
Bạn chẩn đoán N+1 khi lấy danh sách Order rồi truy cập Customer hoặc OrderLine của từng phần tử như thế nào?
Bạn lựa chọn JOIN FETCH, @EntityGraph, batch fetching hoặc DTO projection để khắc phục N+1 theo nhu cầu đọc ra sao?
Bạn phân tích rủi ro kết hợp nhiều collection fetch join trong cùng một truy vấn và ảnh hưởng tới số hàng kết quả như thế nào?
Bạn thiết kế một endpoint trả danh sách Order mà chỉ lấy thông tin tổng hợp thay vì nạp toàn bộ OrderLine như thế nào?
Bạn xử lý LazyInitializationException khi mã truy cập quan hệ sau khi persistence context đã đóng như thế nào?
Bạn đánh giá trade-off của Open Session in View và quyết định có nên tắt nó trong API service như thế nào?
Bạn giải thích vì sao serialize entity trực tiếp ra JSON có thể kích hoạt lazy loading hoặc vòng lặp quan hệ hai chiều ra sao?
Bạn thiết kế mapping entity sang DTO ở trong transaction đọc mà không gây thêm truy vấn ngoài dự kiến như thế nào?
Bạn xác định cách kiểm tra số câu SQL thực thi khi thay đổi fetch strategy để bảo đảm tối ưu hóa có tác dụng ra sao?
Bạn so sánh query cache, second-level cache và application cache về tính nhất quán dữ liệu và độ khó invalidation như thế nào?
Bạn thiết kế chính sách cache cho một danh mục ít thay đổi mà không trả dữ liệu cũ sau cập nhật như thế nào?
Bạn quyết định lúc nào dùng @BatchSize hoặc default batch fetch size của Hibernate và đánh giá giới hạn của chúng trong việc giảm N+1 ra sao?
Bạn đo tác động của fetch size và batch fetching tới memory footprint khi đọc tập dữ liệu lớn như thế nào?
Bạn phân biệt batching JDBC inserts với batching khi nạp các entity liên quan để tránh nhầm hai cơ chế tối ưu khác nhau ra sao?
Bạn quyết định khi nào bật JDBC batch writes và ảnh hưởng của IDENTITY ID generation đến batching như thế nào?
Bạn tổ chức persist một lô entity lớn với flush và clear định kỳ để tránh persistence context tăng bộ nhớ vô hạn như thế nào?
Bạn đánh giá tác động của saveAll trong Spring Data JPA đối với số SQL và transaction thay vì giả định nó luôn là một bulk SQL statement ra sao?
Bạn thiết kế upsert hoặc insert-if-absent theo khả năng của database mà không tạo race condition giữa các request như thế nào?
Bạn lựa chọn index cho một truy vấn JPQL có bộ lọc, join và sort dựa trên execution plan như thế nào?
Bạn phân tích vì sao count query hoặc sort trên nhiều cột có thể chậm dù trang dữ liệu trả về ít bản ghi ra sao?
Bạn dùng SQL logs, bind parameter logs và thống kê truy vấn một cách an toàn để chẩn đoán hiệu năng mà không lộ dữ liệu nhạy cảm như thế nào?
Bạn đọc execution plan để phân biệt full table scan, index seek và join tốn chi phí trong truy vấn do JPA sinh ra như thế nào?
Bạn kiểm tra N+1 và số lần truy cập database bằng metric hoặc test thay vì chỉ quan sát latency tổng thể như thế nào?
Bạn xác định ảnh hưởng của connection pool size và transaction duration tới throughput của một dịch vụ dùng Spring Data JPA ra sao?
Bạn chẩn đoán hiện tượng connection pool cạn khi ứng dụng có nhiều request đồng thời nhưng CPU của database chưa quá cao như thế nào?
Bạn thiết kế cách sử dụng repository trong tác vụ @Async để tránh chia sẻ EntityManager hoặc managed entity không an toàn giữa thread như thế nào?
Bạn giải thích ranh giới transaction của một scheduled job khi cần đọc và xử lý hàng nghìn entity theo lô ra sao?
Bạn phân tích rủi ro truyền managed entity qua message queue hoặc cache phân tán thay vì truyền identifier hoặc DTO như thế nào?
Bạn sử dụng @CreatedDate và @LastModifiedDate với Spring Data JPA auditing để ghi thời gian tạo và sửa như thế nào?
Bạn tổ chức @CreatedBy và @LastModifiedBy cùng AuditorAware khi request có user context hoặc batch job không có người dùng ra sao?
Bạn xác định các bước kích hoạt JPA auditing và cách kiểm tra nó thực sự chạy khi entity được lưu như thế nào?
Bạn kiểm thử giá trị createdDate không bị thay đổi trong lần update và lastModifiedDate phản ánh cập nhật phù hợp ra sao?
Bạn phân biệt JPA auditing với lịch sử thay đổi dữ liệu đầy đủ hoặc công cụ audit revisions như Hibernate Envers như thế nào?
Bạn xử lý một bulk update bỏ qua entity lifecycle callbacks để metadata audit vẫn phản ánh thay đổi theo quy định ra sao?
Bạn đánh giá cách quản lý clock và timezone để dữ liệu audit nhất quán giữa các instance ở nhiều khu vực như thế nào?
Bạn giải thích vì sao schema migration nên được quản lý bằng Flyway hoặc Liquibase thay vì dựa hoàn toàn vào ddl-auto ở production ra sao?
Bạn thiết kế migration thay đổi một cột từ nullable sang NOT NULL khi bảng đã có nhiều dữ liệu thiếu như thế nào?
Bạn chuẩn bị chiến lược expand-and-contract khi đổi tên cột mà nhiều phiên bản ứng dụng JPA cùng chạy trong lúc rollout ra sao?
Bạn kiểm tra ứng dụng JPA còn tương thích với database schema sau một migration bằng bài test nào?
Bạn lựa chọn khi nào dùng @DataJpaTest để kiểm thử repository và lưu ý về database nhúng hoặc cấu hình tự động của slice test như thế nào?
Bạn thiết kế repository integration test bằng Testcontainers để kiểm chứng dialect, constraint và query trên đúng loại database production ra sao?
Bạn phân biệt unit test service có mock repository với integration test repository dùng EntityManager thật theo loại lỗi có thể phát hiện như thế nào?
Bạn sử dụng TestEntityManager trong JPA slice test để chuẩn bị dữ liệu và xác minh trạng thái persistence context như thế nào?
Bạn giải thích vì sao flush và clear trong test giúp phát hiện lỗi mapping hoặc SQL mà cache cấp một có thể che khuất ra sao?
Bạn kiểm thử quan hệ cascade và orphanRemoval bằng cách reload dữ liệu từ database thay vì chỉ kiểm tra collection đang nằm trong bộ nhớ ra sao?
Bạn thiết kế test cho derived query, JPQL và native query với nhiều trường hợp null, dữ liệu Unicode và giá trị biên như thế nào?
Bạn xác minh một pageable query trả đúng số bản ghi và count khi join nhiều quan hệ bằng cách nào?
Bạn mô phỏng hai transaction cập nhật cùng một entity để kiểm tra optimistic locking và xử lý conflict như thế nào?
Bạn xây dựng integration test kiểm chứng rollback khi service cập nhật hai repository rồi ném exception ở bước cuối như thế nào?
Bạn kiểm thử ranh giới @Transactional khi gọi qua Spring proxy để tránh kết luận sai từ việc gọi trực tiếp phương thức nội bộ ra sao?
Bạn tổ chức dữ liệu fixture và cleanup để các bài test JPA không phụ thuộc thứ tự thực thi hoặc dữ liệu của test khác như thế nào?
Bạn xác minh query plan hoặc số câu SQL trong bài kiểm thử hiệu năng để phát hiện regression N+1 khi thay đổi entity mapping như thế nào?
Bạn kiểm tra khả năng bảo vệ thông tin tenant bằng điều kiện lọc ở mọi repository method và tránh vô tình trả dữ liệu chéo tenant ra sao?
Bạn thiết kế mô hình soft delete cho entity và xác định ảnh hưởng tới truy vấn, unique constraint và các quan hệ ra sao?
Bạn xử lý tình huống một endpoint chậm sau khi thêm @OneToMany EAGER bằng cách lần theo SQL, số hàng và persistence context như thế nào?
Bạn điều tra lỗi ObjectOptimisticLockingFailureException khi client gửi cập nhật dựa trên dữ liệu cũ theo các bước nào?
Bạn phân tích sự cố service báo transaction đã commit nhưng event downstream bị mất để đề xuất cơ chế lưu và phát sự kiện đáng tin cậy như thế nào?
Bạn trình bày thiết kế tầng Spring Data JPA cho hệ thống đơn hàng có transaction rõ ràng, truy vấn phân trang, projection, auditing và phòng tránh N+1 như thế nào?
