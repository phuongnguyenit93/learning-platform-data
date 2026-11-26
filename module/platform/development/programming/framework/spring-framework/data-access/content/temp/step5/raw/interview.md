Bạn giải thích vai trò của Spring Framework Data Access trong việc tách logic truy cập SQL khỏi logic nghiệp vụ như thế nào?
Bạn phân biệt lập trình JDBC thuần với sử dụng Spring JDBC về quản lý tài nguyên và xử lý ngoại lệ ra sao?
Bạn xác định khi nào JdbcTemplate phù hợp hơn một ORM đầy đủ như JPA theo đặc điểm truy vấn nào?
Bạn so sánh cách kiểm soát câu SQL trong Spring JDBC với cách sinh SQL tự động của ORM như thế nào?
Bạn đánh giá những yêu cầu nào nên dùng JdbcClient thay vì tự viết DAO bằng JDBC thuần?
Bạn phân biệt truy cập dữ liệu đồng bộ qua JDBC với truy cập reactive qua R2DBC về luồng thực thi như thế nào?
Bạn xác định ranh giới giữa data access adapter, domain service và application service trong thiết kế phân lớp ra sao?
Bạn thiết kế API cho repository hoặc DAO để business layer không phụ thuộc vào ResultSet và SQLException như thế nào?
Bạn đánh giá nguy cơ đưa SQL trực tiếp vào controller thay vì một data access component chuyên trách ra sao?
Bạn phân biệt tính đúng của câu SQL với tính đúng của mapping từ result set sang business object như thế nào?
Bạn mô tả luồng từ một HTTP request qua transaction boundary đến DataSource và database như thế nào?
Bạn lựa chọn SQL viết tay cho báo cáo nhiều bảng thay vì dùng ORM theo tiêu chí hiệu năng và khả năng kiểm soát nào?
Bạn phân biệt connection pool, JDBC driver và database server về trách nhiệm trong một thao tác truy vấn ra sao?
Bạn xác định những lỗi phổ biến của JDBC thủ công mà JdbcTemplate giúp giảm thiểu như thế nào?
Bạn đánh giá tác động của nhiều data access implementations cùng truy cập một schema lên tính nhất quán nghiệp vụ ra sao?
Bạn lựa chọn DTO chuyên biệt cho query result thay vì dùng chung domain entity với persistence object khi nào?
Bạn thiết kế contract của DAO để phân biệt bản ghi không tồn tại với database tạm không khả dụng như thế nào?
Bạn phân tích khi nào một lời gọi database có thể gây side effect dù phương thức Java được đặt tên là get ra sao?
Bạn xác định vai trò của repository abstraction và DataSource trong một hệ thống có nhiều module Spring như thế nào?
Bạn thiết kế cơ chế thay database backend mà thay đổi ít nhất đối với lớp nghiệp vụ ra sao?
Bạn giải thích DataSource cung cấp khả năng lấy JDBC Connection và khác DriverManager ở những điểm nào?
Bạn phân biệt javax.sql.DataSource với đối tượng Connection trong vòng đời một JDBC request như thế nào?
Bạn lựa chọn cấu hình DataSource theo URL, driver, credentials và pool settings dựa trên môi trường nào?
Bạn xác định cách Spring Boot tự cấu hình DataSource khi có starter JDBC và driver phù hợp ra sao?
Bạn kiểm tra DataSource bean thực tế do auto-configuration tạo ra khi ứng dụng có nhiều database drivers như thế nào?
Bạn đánh giá khi nào cần tự khai báo DataSource bean thay cho cấu hình mặc định của Spring Boot ra sao?
Bạn phân biệt connection factory dựa trên pool với SimpleDriverDataSource hoặc DriverManagerDataSource khi kiểm thử như thế nào?
Bạn giải thích tại sao DriverManagerDataSource không phù hợp với tải production có nhiều truy vấn đồng thời?
Bạn thiết kế HikariCP connection pool để phù hợp với số ứng dụng replicas và giới hạn kết nối của database ra sao?
Bạn lựa chọn maximumPoolSize theo throughput, thời gian giữ connection và ngân sách database connections như thế nào?
Bạn phân biệt minimumIdle với maximumPoolSize trong việc cân bằng tài nguyên và độ trễ lấy connection như thế nào?
Bạn kiểm soát connectionTimeout trong pool sao cho request không chờ lâu hơn HTTP timeout như thế nào?
Bạn đánh giá hậu quả của việc đặt maxLifetime dài hơn giới hạn session timeout phía database hoặc proxy ra sao?
Bạn lựa chọn idleTimeout và keepaliveTime phù hợp với hạ tầng mạng và database như thế nào?
Bạn phân biệt validation của connection trong pool với health check của toàn bộ database như thế nào?
Bạn phân tích khi nào một connection có thể bị đóng từ phía server dù pool vẫn nghĩ nó hợp lệ ra sao?
Bạn kiểm tra connection leak qua pool metrics và stack trace leak detection trong một ứng dụng Spring như thế nào?
Bạn thiết kế cơ chế graceful shutdown để pool trả hoặc đóng connections còn đang sử dụng ra sao?
Bạn đánh giá tác động của tạo nhiều DataSource pools không cần thiết trong một service lên database capacity như thế nào?
Bạn quản lý password database bằng secret manager mà không ghi credentials trong repository hoặc logs như thế nào?
Bạn thiết kế rotation credentials cho DataSource khi pool đang duy trì các connections xác thực bằng secret cũ ra sao?
Bạn xác định những khác biệt giữa TCP connect timeout, pool acquisition timeout và JDBC query timeout như thế nào?
Bạn kiểm tra nguyên nhân pool exhausted khác với database query chậm qua những số liệu nào?
Bạn phân biệt eager connection acquisition và lazy acquisition khi một transaction chưa thật sự thực hiện SQL ra sao?
Bạn sử dụng LazyConnectionDataSourceProxy để trì hoãn lấy connection theo yêu cầu nào?
Bạn đánh giá khi nào TransactionAwareDataSourceProxy hữu ích cho code JDBC không tích hợp trực tiếp với Spring transaction ra sao?
Bạn thiết kế AbstractRoutingDataSource để chọn database theo tenant hoặc read/write context như thế nào?
Bạn kiểm soát thời điểm routing key được quyết định để tránh đổi database giữa chừng trong transaction ra sao?
Bạn đánh giá giới hạn của thread-local routing context khi nghiệp vụ chuyển qua thread khác hoặc @Async ra sao?
Bạn quản lý DataSource khác nhau cho giao dịch và báo cáo mà tránh dùng nhầm database đọc chỉ phục vụ replica như thế nào?
Bạn xác định khi nào cần tách read replica cho truy vấn và hệ quả của replication lag lên dữ liệu ra sao?
Bạn giải thích DataSourceUtils.getConnection khác gì gọi trực tiếp DataSource.getConnection khi có Spring transaction?
Bạn phân tích vì sao Connection đang gắn với transaction không nên bị đóng thủ công trước khi transaction kết thúc ra sao?
Bạn sử dụng DataSourceUtils.releaseConnection để bảo vệ kết nối do Spring quản lý theo cách nào?
Bạn phân biệt JDBC resource cleanup cho Connection, Statement và ResultSet khi dùng JDBC thuần với JdbcTemplate ra sao?
Bạn mô tả cách JdbcTemplate đảm nhận việc tạo, thực thi và giải phóng JDBC resources sau một truy vấn như thế nào?
Bạn đánh giá rủi ro giữ Connection trong field của singleton bean dùng cho nhiều requests đồng thời ra sao?
Bạn lựa chọn quản lý scope của Connection theo transaction hoặc operation để tránh leak như thế nào?
Bạn phân tích connection autoCommit mặc định ảnh hưởng tới các lệnh SQL ngoài @Transactional ra sao?
Bạn xác định sự khác nhau giữa Connection.setReadOnly và cam kết database chỉ cho phép đọc như thế nào?
Bạn kiểm tra việc transaction manager đặt isolation level và khôi phục trạng thái connection sau khi trả pool ra sao?
Bạn đánh giá rủi ro gọi commit hoặc rollback trực tiếp trên Connection đang được Spring transaction quản lý như thế nào?
Bạn thiết kế một DAO legacy dùng Connection thủ công để vẫn tham gia transaction hiện tại bằng cách nào?
Bạn xác định vì sao một connection trả về pool không đồng nghĩa socket kết nối vật lý đã được đóng ra sao?
Bạn lựa chọn thời gian sống connection khi database nằm sau load balancer hoặc connection proxy theo ràng buộc nào?
Bạn kiểm tra một long-running query giữ connection quá lâu và khiến requests khác phải xếp hàng như thế nào?
Bạn giới hạn số truy vấn chạy đồng thời để không làm cạn connection pool và database workers ra sao?
Bạn phân biệt datasource health status với khả năng thực thi một business query cụ thể như thế nào?
Bạn kiểm soát mức độ logging JDBC connection details để không làm lộ username hoặc network topology ra sao?
Bạn đánh giá trường hợp app có một DataSource bean nhưng hai transaction managers tranh quyền quản lý như thế nào?
Bạn kiểm thử recovery của pooled connections sau khi database restart mà không restart Spring application ra sao?
Bạn giải thích JdbcTemplate nhận DataSource và thực hiện SQL với kết quả được chuyển đổi như thế nào?
Bạn phân biệt JdbcTemplate.query, queryForObject, queryForList và update theo kiểu kết quả mong đợi ra sao?
Bạn lựa chọn JdbcTemplate.queryForObject khi truy vấn có thể không trả bản ghi bằng cách xử lý nào?
Bạn giải thích EmptyResultDataAccessException và IncorrectResultSizeDataAccessException phản ánh những hợp đồng dữ liệu nào?
Bạn thiết kế DAO trả Optional thay vì ném ngoại lệ khi không tìm thấy một bản ghi theo business semantics nào?
Bạn sử dụng RowMapper để chuyển một hàng trong ResultSet thành Java object như thế nào?
Bạn phân biệt RowMapper với ResultSetExtractor khi cần gom nhiều hàng thành một aggregate ra sao?
Bạn sử dụng RowCallbackHandler khi cần xử lý tuần tự các hàng mà không tích lũy toàn bộ kết quả như thế nào?
Bạn lựa chọn ResultSetExtractor thay vì RowMapper để ánh xạ quan hệ one-to-many từ kết quả JOIN theo tiêu chí nào?
Bạn thiết kế RowMapper không phụ thuộc thứ tự cột trong SELECT mà dùng column labels như thế nào?
Bạn thiết kế SQL column aliases để tránh nhầm các cột id trùng tên trong kết quả JOIN ra sao?
Bạn phân biệt ResultSet.getObject với các getter kiểu cụ thể khi xử lý NULL và driver-specific conversions ra sao?
Bạn kiểm tra wasNull khi đọc cột số nguyên có thể NULL bằng JDBC getter nguyên thủy như thế nào?
Bạn ánh xạ timestamp hoặc date column sang Instant, LocalDate và OffsetDateTime theo yêu cầu timezone nào?
Bạn đánh giá rủi ro dùng LocalDateTime cho cột lưu thời điểm tuyệt đối mà không thống nhất timezone ra sao?
Bạn thiết kế RowMapper dùng BigDecimal cho tiền để tránh sai số số thực như thế nào?
Bạn quản lý enum conversion khi giá trị lưu trong database không khớp tên Java enum như thế nào?
Bạn sử dụng BeanPropertyRowMapper cho DTO có tên cột khớp tên property theo điều kiện nào?
Bạn đánh giá giới hạn của BeanPropertyRowMapper khi model immutable hoặc cần chuyển đổi dữ liệu phức tạp ra sao?
Bạn lựa chọn DataClassRowMapper cho kiểu dữ liệu có constructor phù hợp và kiểm chứng mapping như thế nào?
Bạn thiết kế mapper riêng cho query có JSON column hoặc custom SQL type thay vì mapping tự động ra sao?
Bạn kiểm thử mapping khi một cột vừa được thêm và dữ liệu cũ vẫn chứa NULL như thế nào?
Bạn kiểm soát việc đọc dữ liệu BLOB hoặc CLOB lớn tránh đẩy toàn bộ payload vào heap như thế nào?
Bạn phân biệt truy vấn COUNT(*) với một query trả nhiều rows rồi đếm ở ứng dụng như thế nào?
Bạn chọn queryForList<Map<String,Object>> hay typed DTO theo yêu cầu type safety nào?
Bạn xử lý duplicate column names khi nhận kết quả dưới dạng Map mà không mất giá trị như thế nào?
Bạn đánh giá rủi ro RowMapper gọi thêm DAO queries cho mỗi hàng gây N+1 query pattern ra sao?
Bạn thiết kế mapping result set gồm nhiều bảng để tránh N+1 queries và không tạo entities trùng như thế nào?
Bạn xác định cách viết integration test bảo đảm mapping không bị lệch khi schema migration đổi tên cột ra sao?
Bạn dùng JdbcTemplate.update để thực thi INSERT, UPDATE và DELETE với bind parameters như thế nào?
Bạn phân biệt số rows affected với việc business transaction hoàn tất chính xác về mặt nghiệp vụ ra sao?
Bạn kiểm tra update trả 0 rows khi có điều kiện version để phân biệt stale write với ID không tồn tại ra sao?
Bạn sử dụng PreparedStatementSetter hoặc PreparedStatementCreator khi thao tác cần tùy chỉnh JDBC statement ra sao?
Bạn kiểm soát các SQL parameter types khi giá trị null làm driver không suy ra được kiểu dữ liệu như thế nào?
Vì sao bind parameters của PreparedStatement giúp tách dữ liệu đầu vào khỏi cú pháp SQL?
Bạn đánh giá rủi ro tự nối input vào câu SQL cho WHERE clause, LIKE pattern hoặc IN list như thế nào?
Bạn sử dụng JdbcTemplate.execute cho một thao tác JDBC đặc biệt theo trường hợp nào?
Bạn xác định khi nào callback trực tiếp trên Connection vẫn cần thiết nhưng phải tuân thủ Spring resource management ra sao?
Bạn quản lý queryTimeout và fetchSize của JdbcTemplate theo workload mà không làm ảnh hưởng mọi truy vấn ra sao?
Bạn phân biệt fetchSize hint ở JDBC driver với giới hạn số records trả về trong response như thế nào?
Bạn thiết kế xử lý truy vấn nhiều triệu rows mà không giữ toàn bộ List trong heap như thế nào?
Bạn đánh giá tác động của server-side cursors và autoCommit tới streaming ResultSet theo từng JDBC driver ra sao?
Vì sao RowCallbackHandler không bảo đảm streaming thực sự khi JDBC driver vẫn buffer toàn bộ ResultSet?
Bạn tổ chức cleanup khi RowCallbackHandler ném exception trong lúc xử lý nhiều records như thế nào?
Bạn phân biệt getGeneratedKeys với việc SELECT lại theo business key sau INSERT như thế nào?
Bạn sử dụng GeneratedKeyHolder để lấy primary key được database sinh trong một INSERT như thế nào?
Bạn kiểm tra database driver hỗ trợ RETURN_GENERATED_KEYS và số cột key trả về như thế nào?
Bạn lựa chọn SimpleJdbcInsert khi muốn giảm SQL boilerplate và vẫn kiểm soát cột insert như thế nào?
Bạn đánh giá rủi ro dựa hoàn toàn vào metadata của database khi dùng SimpleJdbcInsert trong schema phức tạp ra sao?
Bạn thiết kế update có optimistic locking bằng điều kiện WHERE id và version như thế nào?
Bạn phân biệt khóa lạc quan bằng version với khóa bi quan SELECT FOR UPDATE theo đặc điểm cạnh tranh nào?
Bạn kiểm soát idempotency cho INSERT khi HTTP client retry sau timeout mà database có thể đã commit như thế nào?
Bạn xác định khi nào dùng UPSERT database-specific và cần kiểm tra semantics của ON CONFLICT hoặc MERGE ra sao?
Bạn thiết kế DAO cho thao tác lưu nhiều bản ghi liên quan mà không tự mở transaction trong từng method như thế nào?
Bạn lựa chọn NamedParameterJdbcTemplate để tăng tính rõ ràng của truy vấn có nhiều parameters ra sao?
Bạn so sánh dấu hỏi vị trí của JdbcTemplate với named parameters trong SQL dài về độ dễ bảo trì như thế nào?
Bạn sử dụng MapSqlParameterSource hoặc BeanPropertySqlParameterSource để bind parameters theo tình huống nào?
Bạn thiết kế named parameter query với nhiều điều kiện optional mà không tạo SQL injection như thế nào?
Bạn xử lý named parameter dùng trong IN (:ids) khi danh sách phần tử rỗng hoặc quá lớn ra sao?
Bạn đánh giá giới hạn số bind variables của driver/database khi NamedParameterJdbcTemplate mở rộng danh sách IN như thế nào?
Bạn quyết định khi nào cần temporary table hoặc batch lookup thay vì IN list cực dài theo tiêu chí nào?
Bạn kiểm tra tên parameter bị viết sai trong SQL để không trả kết quả không mong đợi ra sao?
Bạn phân biệt NamedParameterJdbcTemplate và JdbcTemplate về connection management và exception translation như thế nào?
Bạn lựa chọn fluent JdbcClient thay cho JdbcTemplate hoặc NamedParameterJdbcTemplate theo phiên bản Spring Framework nào?
Bạn mô tả cách JdbcClient xây dựng SQL, bind parameters và lấy kết quả qua fluent API như thế nào?
Bạn so sánh JdbcClient.sql(...).param(...) với named parameters khi method có nhiều tham số ra sao?
Bạn phân biệt JdbcClient.query(...).single(), optional() và list() theo số rows trả về và API contract nào?
Bạn lựa chọn JdbcClient.query(RowMapper) khi mapping cần logic riêng thay vì mapper tạo tự động ra sao?
Bạn sử dụng JdbcClient.update() để thực hiện mutation và đọc affected row count như thế nào?
Bạn đánh giá giới hạn của JdbcClient khi cần batch updates hoặc gọi stored procedures và chọn API bổ sung nào?
Bạn phân biệt việc JdbcClient cung cấp fluent facade với JdbcTemplate thực hiện công việc JDBC nền tảng ra sao?
Bạn đánh giá tác động của thêm JdbcClient vào dự án đang sử dụng NamedParameterJdbcTemplate lâu năm như thế nào?
Bạn thiết kế API DAO thống nhất khi một số thao tác dùng JdbcClient và những thao tác khác dùng JdbcTemplate ra sao?
Bạn kiểm chứng cách bind null, enum và temporal types qua JdbcClient đúng với database schema như thế nào?
Bạn quản lý named và positional parameters trong JdbcClient mà tránh trộn ngữ nghĩa gây sai SQL như thế nào?
Bạn thiết kế test cho JdbcClient query trả một hàng, không hàng và nhiều hàng để bảo đảm hợp đồng ra sao?
Bạn đánh giá lợi ích và giới hạn của JdbcClient cho SQL động với filter và sort được whitelist như thế nào?
Bạn phân biệt SQL được truyền vào JdbcClient với câu lệnh đã được JDBC driver chuẩn bị khi thực thi ra sao?
Bạn lựa chọn logging SQL template và parameter metadata thay vì raw parameter values để bảo vệ thông tin nhạy cảm như thế nào?
Bạn xây dựng mapper tái sử dụng giữa JdbcTemplate, NamedParameterJdbcTemplate và JdbcClient bằng cách nào?
Bạn thiết kế adapter cho cùng một use case để có thể chuyển từ JdbcTemplate sang JdbcClient mà không đổi domain interface ra sao?
Bạn kiểm tra compatibility khi nâng Spring Framework lên phiên bản có JdbcClient trong ứng dụng như thế nào?
Bạn xác định các giới hạn của fluent API khi cần streaming dữ liệu lớn hoặc JDBC vendor extensions như thế nào?
Bạn phân biệt câu SQL cố định và dynamic SQL khi xây API tìm kiếm với filter tùy chọn như thế nào?
Bạn thiết kế dynamic WHERE conditions bằng whitelist các trường có thể lọc mà không nối trực tiếp tên cột từ user ra sao?
Bạn đánh giá nguy cơ SQL injection khi ORDER BY dùng input không thể bind thành identifier như thế nào?
Bạn kiểm soát search term chứa dấu phần trăm hoặc gạch dưới khi truy vấn LIKE và cần literal matching như thế nào?
Bạn thiết kế pagination bằng LIMIT/OFFSET và nêu những giới hạn khi bảng có hàng triệu rows ra sao?
Bạn lựa chọn keyset pagination thay vì offset dựa trên tính ổn định của sort keys và nhu cầu duyệt trang như thế nào?
Bạn kiểm tra truy vấn phân trang có stable tiebreaker để không mất hoặc lặp bản ghi giữa các trang như thế nào?
Bạn đánh giá tác động của transaction isolation và dữ liệu cập nhật đồng thời đến kết quả phân trang ra sao?
Bạn sử dụng database indexes cho WHERE, JOIN và ORDER BY dựa trên execution plan như thế nào?
Bạn đọc EXPLAIN hoặc EXPLAIN ANALYZE để phân biệt full table scan với index seek như thế nào?
Bạn nhận diện tác động của N+1 queries ở service gọi JdbcTemplate trong một vòng lặp như thế nào?
Bạn tổ chức truy vấn JOIN hoặc batch read để trả dữ liệu con mà không tạo N+1 queries ra sao?
Bạn lựa chọn materialized view hoặc query chuyên biệt cho báo cáo phức tạp theo yêu cầu freshness nào?
Bạn đánh giá ảnh hưởng của SELECT * tới network traffic, mapping và khả năng tương thích schema ra sao?
Bạn xử lý query plan thay đổi sau khi dữ liệu tăng hoặc statistics cũ dẫn tới latency bất thường như thế nào?
Bạn kiểm tra các kiểu SQL boolean, UUID và JSON giữa PostgreSQL, MySQL và database test khác nhau ra sao?
Bạn quản lý dialect differences khi câu SQL dùng RETURNING, UPSERT hoặc pagination vendor-specific như thế nào?
Bạn lựa chọn chuẩn hóa SQL đa database hay chấp nhận tối ưu riêng cho một vendor theo mục tiêu nào?
Bạn thiết kế schema migration và DAO release theo chiến lược expand-contract để chạy nhiều phiên bản ứng dụng như thế nào?
Bạn kiểm soát quyền DDL và DML của account ứng dụng để không thể thay đổi schema ngoài quy trình như thế nào?
Bạn quản lý SQL files hoặc named SQL constants cho truy vấn lớn để code review dễ dàng ra sao?
Bạn phân biệt dùng JdbcTemplate.batchUpdate với gọi update nhiều lần trong vòng lặp về round trips và throughput như thế nào?
Bạn chọn BatchPreparedStatementSetter để bind nhiều hàng vào cùng một câu SQL như thế nào?
Bạn sử dụng List<Object[]> hoặc SqlParameterSource[] với batchUpdate theo đặc điểm API nào?
Bạn thiết kế batch INSERT có generated keys và xác minh khả năng hỗ trợ theo database driver ra sao?
Bạn phân biệt batch update counts với kết quả thành công nghiệp vụ khi JDBC trả SUCCESS_NO_INFO hoặc EXECUTE_FAILED như thế nào?
Bạn đánh giá khi nào driver thực hiện batch thực sự và khi nào rewrite câu INSERT để tăng throughput ra sao?
Bạn lựa chọn batch size theo giới hạn packet, bind parameters, memory và database latency như thế nào?
Bạn xử lý partial failure của batch khi một row vi phạm unique constraint bằng chiến lược nào?
Bạn xác định hành vi của batch khi đang ở transaction và một statement lỗi theo database nào?
Bạn kiểm tra khả năng rollback toàn bộ batch hay chỉ một phần khi chạy ngoài transaction như thế nào?
Bạn phân biệt atomic transaction bao quanh batch với bản thân JDBC batch về bảo đảm dữ liệu ra sao?
Bạn thiết kế idempotent batch import để chạy lại sau timeout mà không tạo bản ghi trùng ra sao?
Bạn tổ chức batch upsert cho dữ liệu đồng bộ từ hệ thống ngoài theo khóa nghiệp vụ nào?
Bạn đánh giá ảnh hưởng của lock contention khi batch update nhiều hàng cùng một bảng hot như thế nào?
Bạn lựa chọn sort order của batch writes để giảm nguy cơ deadlock giữa nhiều workers ra sao?
Bạn kiểm soát kích thước transaction khi batch cập nhật hàng triệu rows để không giữ lock quá lâu như thế nào?
Bạn thiết kế checkpoint hoặc partition công việc cho job batch chạy nhiều phút để có thể resume ra sao?
Bạn phân biệt retry một batch lỗi do deadlock với retry một batch lỗi do dữ liệu không hợp lệ như thế nào?
Bạn theo dõi batch duration, rows affected, error count và commit latency để tối ưu như thế nào?
Bạn kiểm thử batch update trên database thật để phát hiện khác biệt driver về update counts và generated keys ra sao?
Bạn giải thích mục đích sử dụng stored procedure hoặc database function khi ứng dụng Spring đã có service layer như thế nào?
Bạn phân biệt CallableStatement với PreparedStatement khi gọi procedure có OUT parameters như thế nào?
Bạn sử dụng JdbcTemplate.call hoặc CallableStatementCreator để gọi stored procedure ra sao?
Bạn so sánh SimpleJdbcCall với CallableStatement thuần về khai báo tham số và sử dụng metadata của procedure ra sao?
Bạn thiết kế SimpleJdbcCall với schema, catalog và procedure name khi database có nhiều namespaces ra sao?
Bạn quyết định có sử dụng metadata tự động hay khai báo SqlParameter tường minh cho SimpleJdbcCall theo điều kiện nào?
Bạn phân biệt IN, OUT và INOUT parameters trong lời gọi stored procedure từ Spring JDBC ra sao?
Bạn map giá trị OUT parameters thành DTO có kiểu dữ liệu đúng như thế nào?
Bạn xử lý stored procedure trả nhiều result sets thông qua JdbcTemplate hoặc SimpleJdbcCall ra sao?
Bạn xác định giới hạn hỗ trợ REF CURSOR hoặc vendor-specific SQL types ở các JDBC drivers như thế nào?
Bạn thiết kế RowMapper cho result set từ procedure khi các cột không giống entity table như thế nào?
Bạn đánh giá rủi ro procedure commit transaction nội bộ làm phá vỡ kỳ vọng @Transactional ra sao?
Bạn xác định stored procedure có chạy cùng connection và transaction với các JdbcTemplate operations khác không bằng cách nào?
Bạn phân biệt database function trả scalar value với stored procedure thực hiện mutation khi chọn API gọi như thế nào?
Bạn xử lý lỗi permission denied khi application user có quyền SELECT nhưng không có EXECUTE trên procedure ra sao?
Bạn kiểm tra hiệu năng và thời gian chờ của stored procedure nhiều bước theo database metrics nào?
Bạn quản lý versioning procedure signature khi hai phiên bản Spring application cùng chạy như thế nào?
Bạn thiết kế integration test gọi stored procedure thật để phát hiện lỗi schema hoặc parameter mapping ra sao?
Bạn quyết định chuyển logic từ stored procedure sang application service để giảm phụ thuộc database vendor theo những tiêu chí nào?
Bạn giải thích Spring dịch SQLException thành DataAccessException bằng cơ chế nào?
Bạn phân biệt checked SQLException của JDBC với unchecked DataAccessException của Spring về ảnh hưởng tới service layer như thế nào?
Bạn phân loại transient và non-transient data access failures khi thiết kế chính sách retry ra sao?
Bạn xác định cách SQLExceptionTranslator dựa trên SQL state, vendor error code hoặc exception subtype tùy môi trường ra sao?
Bạn phân biệt DuplicateKeyException với DataIntegrityViolationException về mức cụ thể của lỗi như thế nào?
Bạn xử lý EmptyResultDataAccessException khác với DataAccessResourceFailureException theo hợp đồng API nào?
Bạn phân biệt nguyên nhân QueryTimeoutException do SQL chậm, lock wait hoặc sự cố hạ tầng bằng các tín hiệu nào?
Bạn phân biệt CannotGetJdbcConnectionException với CannotAcquireLockException khi triage lỗi production ra sao?
Bạn thiết kế exception mapping từ Spring DataAccessException sang domain error mà không lộ câu SQL hoặc dữ liệu nhạy cảm như thế nào?
Bạn xác định nhóm lỗi nào có thể được retry an toàn với idempotent read operation như thế nào?
Bạn kiểm soát retry write khi request timeout nhưng database có thể đã commit trước khi client nhận phản hồi ra sao?
Bạn phân biệt optimistic locking conflict với lỗi database connection transient về HTTP response và hướng xử lý như thế nào?
Bạn sử dụng custom SQLExceptionTranslator khi database vendor có mã lỗi đặc biệt theo tiêu chí nào?
Bạn kiểm thử Spring JDBC exception translation với lỗi unique constraint, FK violation và timeout trên database thực như thế nào?
Bạn đánh giá tác động của việc nuốt DataAccessException rồi trả danh sách rỗng lên tính đúng nghiệp vụ ra sao?
Bạn thiết kế logging exception giữ stack trace và correlation ID nhưng che bind parameters nhạy cảm như thế nào?
Bạn phân biệt lỗi cú pháp SQL không thể retry với deadlock có thể retry theo điều kiện nào?
Bạn xác định điều kiện một exception phải được ném lại để @Transactional rollback thay vì biến thành trạng thái thành công ra sao?
Bạn tổ chức alert theo nhóm lỗi connection, timeout, deadlock và constraint violation bằng metrics nào?
Bạn xử lý lỗi database tài nguyên tạm không sẵn sàng bằng timeout, circuit breaker và failover policy như thế nào?
Bạn giải thích transaction boundary giúp nhiều thao tác JDBC commit hoặc rollback cùng nhau ra sao?
Bạn phân biệt @Transactional của Spring với autoCommit trên Connection khi một DAO chạy ngoài transaction như thế nào?
Bạn xác định ai nên đặt @Transactional giữa controller, application service và repository dựa trên nghiệp vụ nào?
Bạn phân biệt transaction propagation REQUIRED và REQUIRES_NEW khi hai service methods cùng ghi database như thế nào?
Bạn đánh giá hệ quả của REQUIRES_NEW đối với connection pool khi phương thức bên ngoài đã giữ một connection ra sao?
Bạn phân biệt propagation SUPPORTS và MANDATORY khi một thao tác chỉ hợp lệ trong transaction như thế nào?
Bạn quyết định dùng NOT_SUPPORTED khi cần chạy thao tác không thuộc transaction hiện tại theo trường hợp nào?
Bạn giải thích propagation NESTED dựa trên JDBC savepoints và những giới hạn cần kiểm tra như thế nào?
Bạn phân biệt NESTED với REQUIRES_NEW về rollback từng phần và connection usage ra sao?
Bạn thiết kế thao tác sử dụng TransactionTemplate để kiểm soát rõ transaction boundaries theo trường hợp nào?
Bạn so sánh khai báo @Transactional với lập trình trực tiếp qua PlatformTransactionManager về khả năng composition như thế nào?
Bạn xác định khi nào DataSourceTransactionManager phù hợp cho JDBC và JdbcTransactionManager bổ sung điều gì?
Bạn kiểm tra transaction manager đang được chọn khi ứng dụng đồng thời có JDBC và JPA infrastructure ra sao?
Bạn đánh giá rủi ro dùng sai transaction manager khiến JdbcTemplate operation không tham gia cùng transaction như thế nào?
Bạn mô tả vai trò của TransactionSynchronizationManager đối với kết nối gắn với thread thực thi như thế nào?
Bạn kiểm tra Connection được JdbcTemplate lấy có thuộc transaction hiện tại bằng phương pháp nào?
Bạn phân biệt readOnly=true ở @Transactional với bảo đảm truy vấn không thể ghi dữ liệu do database cưỡng chế như thế nào?
Bạn lựa chọn transaction isolation READ_COMMITTED, REPEATABLE_READ hoặc SERIALIZABLE dựa trên anomaly cần tránh như thế nào?
Bạn phân biệt dirty read, non-repeatable read và phantom read bằng những tình huống truy cập JDBC nào?
Bạn xác định default isolation của database có ảnh hưởng tới @Transactional(isolation=DEFAULT) như thế nào?
Bạn thiết kế xử lý lost update bằng optimistic locking khi hai request cùng cập nhật một row ra sao?
Bạn đánh giá tác động của SELECT FOR UPDATE lên lock wait, throughput và nguy cơ deadlock như thế nào?
Bạn quyết định dùng timeout của @Transactional khác JDBC statement timeout theo mục tiêu nào?
Bạn kiểm tra transaction timeout có được thực thi đúng khi truy vấn đang chờ lock của database như thế nào?
Vì sao quy tắc rollback mặc định của Spring khác nhau giữa RuntimeException và checked exception?
Bạn sử dụng rollbackFor hoặc noRollbackFor khi business exception cần chính sách riêng như thế nào?
Bạn đánh giá rủi ro bắt exception trong @Transactional rồi không rethrow khiến transaction commit dữ liệu dở dang ra sao?
Bạn phân biệt rollback-only marker với explicit rollback khi các tầng service xử lý exception như thế nào?
Bạn chẩn đoán UnexpectedRollbackException khi transaction bên trong đánh dấu rollback-only nhưng outer method trả thành công ra sao?
Vì sao self-invocation có thể khiến lời gọi @Transactional không đi qua transaction interceptor ở Spring proxy mode?
Bạn kiểm tra một private method hoặc phương thức không qua Spring proxy có thực sự khởi tạo transaction không ra sao?
Bạn thiết kế truyền transaction context khi xử lý qua @Async hoặc một thread khác mà không giả định thread-local tự lan truyền như thế nào?
Bạn đánh giá giới hạn của @Transactional khi service còn gọi HTTP API hoặc message broker ngoài database như thế nào?
Bạn lựa chọn transactional outbox khi cần ghi database và phát event có độ tin cậy cao theo điều kiện nào?
Bạn kiểm soát side effects bên ngoài sau commit để rollback không gửi sự kiện sai trạng thái như thế nào?
Bạn thiết kế lệnh đọc nhiều bảng cần snapshot nhất quán mà không giữ transaction quá lâu ra sao?
Bạn xác định phạm vi transaction phù hợp cho batch job ghi hàng chục nghìn rows để giảm lock contention như thế nào?
Bạn kiểm thử transaction rollback qua nhiều JdbcTemplate operations dùng cùng DataSource như thế nào?
Bạn phân biệt failure khi commit với timeout trước commit và cách retry dựa trên khả năng xác định kết quả như thế nào?
Bạn thiết kế service cập nhật tồn kho và lịch sử thay đổi trong cùng transaction để bảo toàn invariant như thế nào?
Bạn lựa chọn kiểm soát transaction xuyên nhiều DataSources khi một local JDBC transaction không bao phủ cả hai như thế nào?
Bạn đánh giá rủi ro cho rằng hai @Transactional services với hai DataSources tự động commit nguyên tử như thế nào?
Bạn quản lý transaction synchronization callback khi cache invalidation chỉ nên xảy ra sau commit ra sao?
Bạn kiểm tra database connection được trả về pool và transaction context được dọn sau exception như thế nào?
Bạn thiết kế DataSource credentials với quyền SELECT, INSERT, UPDATE hoặc EXECUTE đúng theo least privilege ra sao?
Bạn kiểm soát input người dùng làm dynamic SQL bằng identifier whitelist và bind variables như thế nào?
Bạn phân biệt ngăn SQL injection bằng prepared statement với validation nghiệp vụ của dữ liệu đầu vào ra sao?
Bạn xử lý ORDER BY theo tên cột tùy chọn mà không đưa thẳng input user vào SQL string như thế nào?
Bạn đánh giá nguy cơ log full SQL cùng bind values chứa mật khẩu, token hoặc thông tin cá nhân ra sao?
Bạn thiết kế audit trail cho các thao tác update quan trọng mà không phụ thuộc hoàn toàn vào application logs như thế nào?
Bạn phân biệt database-level row security với tenant filter trong DAO theo mức phòng vệ nào?
Bạn kiểm thử điều kiện WHERE tenant_id có mặt trong mọi truy vấn đọc hoặc cập nhật nhiều tenant ra sao?
Bạn ngăn client sửa bản ghi tenant khác dù biết chính xác primary key bằng kiểm soát nào?
Bạn quản lý TLS certificate truststore cho database connections và kiểm tra hostname verification như thế nào?
Bạn xử lý việc database credentials bị rotate trong khi pool đang dùng các phiên kết nối cũ ra sao?
Bạn xác định khi nào có thể cấp account read-only cho báo cáo và account ghi riêng cho nghiệp vụ ra sao?
Bạn phân biệt secret encryption at rest trong cấu hình với encryption in transit trên JDBC connection như thế nào?
Bạn thiết kế dữ liệu test không chứa PII production trong SQL fixtures và query logs ra sao?
Bạn kiểm soát truy vấn xuất dữ liệu hàng loạt để tránh một API client đọc toàn bộ bảng nhạy cảm như thế nào?
Bạn đánh giá rủi ro cho phép gọi stored procedure đặc quyền từ một endpoint công khai ra sao?
Bạn lựa chọn cơ chế phân quyền database cho migration tool khác với user chạy ứng dụng như thế nào?
Bạn kiểm tra SQL error response không tiết lộ schema, table names hoặc internal network addresses như thế nào?
Bạn xác định khi nào masking dữ liệu ở application là không đủ nếu cùng credential vẫn có quyền SELECT cột nhạy cảm ra sao?
Bạn tổ chức review những thay đổi SQL quan trọng cùng các chính sách phân quyền khi phát hành như thế nào?
Bạn đánh giá nguy cơ multi-tenant routing context bị rò rỉ sang request kế tiếp do ThreadLocal không được dọn ra sao?
Bạn thiết kế unit test RowMapper với ResultSet mock nhưng vẫn bảo đảm kiểm thử SQL thật ở tầng integration ra sao?
Bạn phân biệt unit test DAO mock JdbcTemplate với integration test sử dụng database thật về loại lỗi phát hiện như thế nào?
Bạn dùng @JdbcTest của Spring Boot để kiểm thử JDBC components trong một application context gọn như thế nào?
Bạn xác định những auto-configuration và beans nào cần được bổ sung khi @JdbcTest không nạp đủ DAO phụ thuộc ra sao?
Bạn thiết kế EmbeddedDatabaseBuilder cho test nhanh và nêu giới hạn tương thích SQL dialect như thế nào?
Bạn lựa chọn H2 database hay Testcontainers database đúng vendor theo độ quan trọng của query semantics nào?
Bạn dùng Testcontainers PostgreSQL hoặc MySQL để kiểm thử SQL, connection và transaction thật như thế nào?
Bạn quản lý schema migrations trong integration test để phiên bản bảng phù hợp với production ra sao?
Bạn sử dụng @Sql để chuẩn bị dữ liệu và dọn database cho từng test mà không phụ thuộc thứ tự chạy như thế nào?
Bạn đánh giá hành vi rollback của @Transactional test khi code ứng dụng dùng REQUIRES_NEW ra sao?
Bạn kiểm thử JdbcTemplate.queryForObject với zero, one và multiple rows để phát hiện hợp đồng sai như thế nào?
Bạn kiểm thử RowMapper với cột NULL, alias và timestamp để tránh lỗi âm thầm như thế nào?
Bạn kiểm tra mapping DTO immutable hoặc Java record qua RowMapper trong test theo database driver nào?
Bạn thiết kế test chứng minh NamedParameterJdbcTemplate mở rộng IN list đúng và xử lý danh sách rỗng như thế nào?
Bạn kiểm thử JdbcClient parameter binding và query().optional() khi không có dữ liệu ra sao?
Bạn dùng integration test xác minh generated keys được trả đúng khi driver có hỗ trợ như thế nào?
Bạn kiểm thử batchUpdate khi một phần batch vi phạm constraint để hiểu semantics rollback và update counts ra sao?
Bạn kiểm thử stored procedure với IN/OUT parameters và nhiều result sets trên database thật như thế nào?
Bạn xác minh SimpleJdbcCall không phụ thuộc metadata sai ở môi trường production bằng bài test nào?
Bạn thiết kế test cho transaction rollback qua hai DAO cùng DataSource nhưng khác JdbcTemplate instances như thế nào?
Bạn mô phỏng deadlock giữa hai transactions để kiểm tra exception translation và retry policy như thế nào?
Bạn kiểm chứng version-based optimistic locking ngăn lost update khi hai clients cập nhật cùng row ra sao?
Bạn kiểm thử nested transaction với savepoints trên driver có hỗ trợ và xác minh rollback từng phần như thế nào?
Bạn đánh giá khi nào test dựa trên H2 có thể bỏ lọt lỗi isolation level hoặc transaction locking của PostgreSQL ra sao?
Bạn kiểm tra DAO xử lý lỗi connection refused, acquisition timeout và query timeout bằng fault injection như thế nào?
Bạn xác minh pool connections không bị leak sau khi RowMapper hoặc callback ném exception ra sao?
Bạn chạy load test với pool nhỏ để phát hiện hàng đợi chờ connection và timeout ứng dụng như thế nào?
Bạn tổ chức integration tests chạy song song mà không làm dữ liệu hoặc sequence ID của test này ảnh hưởng test khác ra sao?
Bạn lựa chọn quality gates bao gồm SQL correctness, performance, transaction semantics và resource cleanup trước release như thế nào?
Bạn sử dụng Micrometer metrics hoặc pool metrics để theo dõi active, idle và pending connections ra sao?
Bạn phân biệt JDBC query latency, pool wait time và network latency khi phân tích p99 của API như thế nào?
Bạn kiểm tra database slow query logs cùng application tracing để tìm truy vấn gây nghẽn như thế nào?
Bạn thiết kế tags cho SQL metrics theo operation hoặc query name thay vì raw parameterized query chứa PII ra sao?
Bạn xác định lúc nào connection pool mở quá lớn khiến database context switching tăng thay vì throughput tốt hơn?
Bạn đánh giá ảnh hưởng của lock contention tới query timeout ngay cả khi CPU database thấp như thế nào?
Bạn theo dõi số lần deadlock, rollback, constraint violation và retry để phát hiện bất thường ra sao?
Bạn tổ chức tracing từ application service tới JdbcTemplate DAO mà không log toàn bộ bind parameter values như thế nào?
Bạn lựa chọn kích thước fetch size và streaming strategy để tránh memory spike ở batch exports như thế nào?
Bạn đánh giá overhead tạo RowMapper objects hoặc conversion quá phức tạp trong hot path ra sao?
Bạn thiết kế capacity planning cho database khi số Spring Boot replicas tăng gấp đôi và mỗi replica có pool riêng như thế nào?
Bạn kiểm tra tác động của transaction giữ connection trong lúc chờ HTTP downstream lâu như thế nào?
Bạn quyết định khi nào tách thao tác network khỏi transaction để giảm thời gian giữ database locks ra sao?
Bạn xây dựng dashboard phân biệt lỗi pool exhaustion với lỗi database not responding như thế nào?
Bạn thiết kế backpressure hoặc rate limiting khi database bắt đầu từ chối nhiều connections ra sao?
Bạn kiểm soát retry storm sau khi database failover mà các application replicas đồng thời thử kết nối lại như thế nào?
Bạn xác định SLO cho data access operation và tỷ lệ lỗi chấp nhận được dựa trên criticality như thế nào?
Bạn đánh giá tác động của statement caching hoặc prepared statement caching trong driver đối với hiệu năng ra sao?
Bạn thiết kế tối ưu một SQL join chậm dựa trên query plan, selectivity và indexes như thế nào?
Bạn lựa chọn read replica routing khi một truy vấn báo cáo có thể chấp nhận lag nhưng truy vấn thanh toán thì không ra sao?
Bạn lựa chọn đọc từ primary để bảo đảm read-after-write khi read replica có replication lag dựa trên yêu cầu nào?
Bạn xây dựng runbook cho database failover và cách xác nhận ứng dụng Spring đã kết nối lại an toàn ra sao?
Nếu Spring Boot không khởi động được do DataSource bean thiếu driver, bạn sẽ kiểm tra dependencies và JDBC URL như thế nào?
Nếu pool báo connection timeout trong khi database CPU thấp, bạn sẽ phân tích active connections và lock waits ra sao?
Nếu app mở nhiều JDBC connections hơn giới hạn database khi scale pods, bạn sẽ điều chỉnh pool budget như thế nào?
Nếu một query chạy nhanh trong SQL console nhưng timeout qua JdbcTemplate, bạn sẽ kiểm tra transaction, parameters và pool wait như thế nào?
Nếu JdbcTemplate.queryForObject ném EmptyResultDataAccessException khi ID không tồn tại, bạn sẽ định nghĩa DAO contract ra sao?
Nếu RowMapper trả sai giá trị cho hai cột cùng tên sau JOIN, bạn sẽ chỉnh SQL aliases và mapping như thế nào?
Nếu cột nullable số nguyên bị ánh xạ thành 0 trong Java, bạn sẽ kiểm tra JDBC getters và wasNull ra sao?
Nếu timestamps trả sai lệch vài giờ giữa database và API, bạn sẽ rà JDBC driver, timezone và data types như thế nào?
Nếu dữ liệu BigDecimal bị mất precision sau mapping, bạn sẽ kiểm tra SQL types và Java conversion ra sao?
Nếu NamedParameterJdbcTemplate tạo SQL lỗi với danh sách IN rỗng, bạn sẽ thay đổi query hoặc API contract như thế nào?
Nếu sort field từ client bị nối trực tiếp vào SQL, bạn sẽ thiết kế whitelist identifiers để chặn injection ra sao?
Nếu JdbcClient.query().single() gặp nhiều hơn một row, bạn sẽ kiểm tra uniqueness invariant và xử lý exception như thế nào?
Nếu batchUpdate báo partial success trước lỗi unique constraint, bạn sẽ xác định transaction outcome và replay an toàn ra sao?
Nếu generated keys không được trả theo thứ tự dự kiến trong batch, bạn sẽ kiểm tra khả năng driver và thiết kế lại ID mapping ra sao?
Nếu SimpleJdbcCall không tìm thấy procedure trong schema production, bạn sẽ kiểm tra catalog, metadata và quyền EXECUTE như thế nào?
Nếu stored procedure có lệnh COMMIT nội bộ làm @Transactional không rollback được như mong muốn, bạn sẽ điều tra và điều chỉnh ranh giới ra sao?
Nếu cùng một transaction hai DAO dùng DataSources khác nhau, bạn sẽ xác minh phạm vi atomicity và thiết kế phục hồi như thế nào?
Nếu @Transactional không rollback khi một checked exception xảy ra, bạn sẽ xem xét rollback rules như thế nào?
Nếu @Transactional bị bỏ qua do self-invocation, bạn sẽ phát hiện bằng test và thay đổi cách gọi như thế nào?
Nếu @Transactional(readOnly=true) được gắn vào thao tác UPDATE mà dữ liệu vẫn thay đổi, bạn sẽ kiểm tra hành vi của transaction manager, driver và database ra sao?
Nếu REQUIRES_NEW gây cạn pool khi tải cao, bạn sẽ kiểm tra số connections cần dùng và thiết kế giao dịch như thế nào?
Nếu hai workers cập nhật cùng inventory row làm lost update, bạn sẽ áp dụng version checking hoặc locking ra sao?
Nếu database deadlock xuất hiện sau batch update, bạn sẽ thay đổi lock order, batch size và retry policy như thế nào?
Nếu statement bị timeout nhưng write có thể đã commit, bạn sẽ bảo vệ idempotency trước khi retry ra sao?
Nếu dữ liệu được cập nhật trong database nhưng cache vẫn cũ, bạn sẽ phối hợp commit và cache invalidation như thế nào?
Nếu DataAccessException bị bắt rồi trả empty list, bạn sẽ sửa error handling để không che giấu outage ra sao?
Nếu connection credentials được rotate khiến pool giữ phiên xác thực cũ, bạn sẽ làm mới connections an toàn như thế nào?
Nếu SQL chạy qua read replica chưa thấy dữ liệu vừa ghi, bạn sẽ giải thích replication lag và read routing ra sao?
Nếu Testcontainers test xanh nhưng production lỗi vì schema migration chưa chạy, bạn sẽ bổ sung deployment gate và compatibility checks như thế nào?
Nếu batch export tiêu thụ quá nhiều RAM dù dùng RowCallbackHandler, bạn sẽ kiểm tra driver buffering và fetchSize ra sao?
Bạn xây dựng runbook khi pool exhaustion, slow queries, deadlocks và retry storm cùng xảy ra trong giờ cao điểm như thế nào?
