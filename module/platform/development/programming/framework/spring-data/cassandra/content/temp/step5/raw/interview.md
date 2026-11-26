Bạn giải thích Apache Cassandra phù hợp với kiểu workload nào và những yêu cầu nào khiến nó không phải lựa chọn tối ưu?
Bạn phân biệt kiến trúc phân tán ngang hàng của Cassandra với cơ sở dữ liệu quan hệ có primary-replica như thế nào?
Bạn mô tả vai trò của coordinator node khi ứng dụng Spring Boot thực hiện một truy vấn CQL ra sao?
Bạn giải thích token ring và việc phân phối partition giữa các node trong Cassandra như thế nào?
Bạn đánh giá ảnh hưởng của replication factor tới tính sẵn sàng, dung lượng và mức chịu lỗi ra sao?
Bạn phân biệt keyspace với table và chọn chiến lược tổ chức keyspace cho nhiều môi trường như thế nào?
Bạn mô tả vai trò của virtual nodes trong phân phối tải và vận hành Cassandra cluster ra sao?
Bạn phân biệt partition ownership với replica placement khi thiết kế cluster nhiều datacenter như thế nào?
Bạn giải thích gossip và failure detection đóng góp gì vào vận hành Cassandra?
Bạn đánh giá vì sao một client không nên chỉ phụ thuộc vào đúng một contact point khi kết nối cluster?
Bạn phân biệt write path qua commit log và memtable với dữ liệu bền vững trên SSTable như thế nào?
Bạn mô tả read path qua memtable, SSTables và các cấu trúc chỉ mục trong Cassandra ra sao?
Bạn giải thích vai trò của compaction và tác động của nó tới hiệu năng đọc, ghi và dung lượng như thế nào?
Bạn phân biệt partition key với clustering key trong primary key của bảng Cassandra ra sao?
Bạn xác định khi nào một bảng Cassandra cần composite partition key thay vì partition key đơn?
Bạn thiết kế khả năng chịu lỗi theo datacenter với chiến lược replication phù hợp như thế nào?
Bạn phân tích vì sao Cassandra ưu tiên thiết kế bảng từ truy vấn thay vì chuẩn hóa dữ liệu theo quan hệ?
Bạn phân biệt consistency level trong mỗi thao tác với khái niệm một transaction ACID toàn cục ra sao?
Bạn đánh giá lợi ích và hạn chế của eventual consistency cho một hệ thống cập nhật trạng thái liên tục như thế nào?
Bạn xác định yêu cầu nghiệp vụ nào đòi hỏi conditional write thay vì ghi đè thông thường?
Bạn lựa chọn Cassandra hay PostgreSQL cho một dịch vụ theo access pattern và yêu cầu transaction như thế nào?
Bạn đánh giá giới hạn của Cassandra với JOIN, aggregation và truy vấn phân tích phức tạp ra sao?
Bạn tổ chức các bảng đọc chuyên biệt khi cùng một thực thể có nhiều cách truy xuất như thế nào?
Bạn xây dựng sơ đồ truy vấn trước khi định nghĩa schema Cassandra trong một tính năng mới ra sao?
Bạn xác định access pattern theo tenant, user, thời gian và trạng thái trước khi chọn partition key như thế nào?
Bạn tính số lần round-trip dự kiến để trả lời một API khi dữ liệu phân tán trên nhiều partitions ra sao?
Bạn lựa chọn partition key để cân bằng phân phối dữ liệu và truy vấn theo đúng business key như thế nào?
Bạn đánh giá rủi ro chọn một giá trị có cardinality thấp làm partition key của bảng có lưu lượng lớn ra sao?
Bạn phân tích ảnh hưởng của partition key không đều tới hot partitions và hot nodes như thế nào?
Bạn thiết kế partition cho lịch sử sự kiện của người dùng khi số sự kiện tăng không giới hạn ra sao?
Bạn quyết định bucketing theo ngày, tháng hoặc số lượng bản ghi dựa trên kích thước partition như thế nào?
Bạn xử lý dữ liệu của một khách hàng cực lớn mà không tạo partition vượt quá giới hạn vận hành như thế nào?
Bạn đánh giá trade-off của time bucketing giữa giới hạn partition size và số partitions phải truy vấn ra sao?
Bạn thiết kế bảng dữ liệu thiết bị theo device ID và time bucket để hỗ trợ truy vấn khoảng thời gian như thế nào?
Bạn xác định clustering columns khi API cần trả các bản ghi mới nhất trước ra sao?
Bạn phân biệt thứ tự lưu trong partition theo clustering columns với thứ tự kết quả của truy vấn đa partition như thế nào?
Bạn lựa chọn CLUSTERING ORDER khi client thường xuyên lấy sự kiện gần nhất như thế nào?
Bạn đánh giá ảnh hưởng của thứ tự clustering key tới điều kiện range query trong CQL ra sao?
Bạn thiết kế khóa chính để tránh phải dùng ALLOW FILTERING cho truy vấn quan trọng như thế nào?
Trong những trường hợp nào ALLOW FILTERING khiến chi phí truy vấn trở nên khó dự đoán?
Bạn so sánh duplicate data giữa nhiều bảng với việc truy vấn linh hoạt của hệ quản trị quan hệ ra sao?
Bạn quản lý cập nhật đồng thời nhiều read models khi cùng một thực thể được nhân bản ở các bảng khác nhau như thế nào?
Bạn thiết kế quy trình đối soát khi một trong nhiều bảng denormalized không được cập nhật thành công ra sao?
Bạn quyết định tạo thêm bảng phục vụ truy vấn thay vì tiếp tục mở rộng secondary indexes theo những tiêu chí nào?
Bạn xác định tình huống Storage-Attached Indexing có thể hỗ trợ truy vấn mà không thay thế thiết kế partition key như thế nào?
Bạn kiểm tra khả năng hỗ trợ và giới hạn của SAI theo phiên bản Cassandra đang triển khai ra sao?
Bạn phân biệt secondary indexes, materialized views và bảng denormalized tự quản lý theo rủi ro vận hành như thế nào?
Bạn đánh giá các điều kiện bảo trì và tính nhất quán của materialized views trước khi sử dụng như thế nào?
Bạn xác định vì sao truy vấn theo một cột không thuộc primary key có thể tạo tải lớn trong cluster?
Bạn thiết kế API tìm kiếm nhiều điều kiện khi Cassandra không hỗ trợ truy vấn tùy ý như SQL như thế nào?
Bạn lựa chọn đưa dữ liệu sang search engine hoặc analytic store cho những truy vấn nào?
Bạn thiết kế dữ liệu nhiều tenant với tenant ID trong partition key để tránh truy cập nhầm và phân bố tải như thế nào?
Bạn đánh giá nguy cơ một tenant có lưu lượng quá lớn làm lệch phân phối dữ liệu trong bảng chung ra sao?
Bạn xác định cách hỗ trợ thay đổi query requirements mà không làm hỏng schema đang chạy như thế nào?
Bạn thiết kế bảng lookup theo một external ID khi API cần truy vấn một bản ghi bằng ID không phải partition key ra sao?
Bạn lựa chọn kích thước bản ghi và cấu trúc cột để tránh nhiều collections không giới hạn trong một row như thế nào?
Bạn so sánh list, set và map collections trong Cassandra theo ngữ nghĩa cập nhật và chi phí lưu trữ ra sao?
Bạn đánh giá nguy cơ tạo tombstones hoặc write amplification khi collections được cập nhật liên tục ra sao?
Bạn lựa chọn user-defined type thay vì nhiều cột phẳng trong mô hình sự kiện theo yêu cầu nào?
Bạn xác định tác động của frozen UDT hoặc frozen collection đối với cập nhật từng thành phần như thế nào?
Bạn sử dụng static columns cho dữ liệu chia sẻ giữa các rows trong một partition theo tình huống nào?
Bạn đánh giá khi nào counter columns thích hợp và những giới hạn của counter updates ra sao?
Bạn xây dựng mô hình time-series có thể xóa dữ liệu cũ bằng TTL mà không làm read path quá tải như thế nào?
Bạn thiết kế schema versioning khi producer và consumer dùng hai phiên bản Spring Boot cùng lúc ra sao?
Bạn phân biệt thay đổi thêm cột với thay đổi cấu trúc primary key trong kế hoạch migration như thế nào?
Bạn tổ chức migration sang bảng mới khi access pattern thay đổi đáng kể ra sao?
Bạn đo partition sizes và số rows mỗi partition để kiểm chứng schema đang hoạt động ra sao?
Bạn lựa chọn cách lấy mẫu real queries để đánh giá schema trước khi phát hành ra sao?
Bạn phân biệt dữ liệu vắng mặt, null và giá trị xóa trong Cassandra khi thiết kế contract nghiệp vụ như thế nào?
Bạn đánh giá ảnh hưởng của TTL khác nhau giữa các cột tới cách đọc một row như thế nào?
Bạn thiết kế chính sách giữ dữ liệu theo thời gian để hạn chế partition quá rộng ra sao?
Bạn xử lý late-arriving events trong bảng sắp theo timestamp để không mất bản ghi hợp lệ như thế nào?
Bạn xác định nguy cơ dùng timestamp do client cung cấp gây ghi đè dữ liệu mới hơn ra sao?
Bạn thiết kế khóa duy nhất nghiệp vụ khi Cassandra không cung cấp unique constraint tổng quát giống RDBMS như thế nào?
Bạn phân biệt tính duy nhất do primary key đảm bảo với yêu cầu uniqueness trên một thuộc tính khác ra sao?
Bạn lập kế hoạch backfill bảng mới từ dữ liệu cũ mà vẫn bảo toàn khả năng phục vụ của API như thế nào?
Bạn tổ chức schema review để chứng minh từng endpoint có đường truy vấn hiệu quả như thế nào?
Bạn lựa chọn spring-boot-starter-data-cassandra hoặc starter reactive theo stack của ứng dụng ra sao?
Bạn phân biệt Spring Data Cassandra với Java Driver for Apache Cassandra về vai trò như thế nào?
Bạn mô tả cách Spring Boot auto-configuration tạo CqlSession và các thành phần truy cập dữ liệu ra sao?
Bạn tổ chức contact points, local datacenter và keyspace trong cấu hình Spring Boot như thế nào?
Bạn kiểm tra local datacenter được cấu hình đúng với topology của Cassandra cluster bằng cách nào?
Bạn đánh giá nguy cơ client chọn sai datacenter khi application chạy ở nhiều vùng địa lý ra sao?
Bạn cấu hình authentication cho Cassandra bằng credential provider phù hợp mà không hardcode password như thế nào?
Bạn bảo vệ TLS giữa Spring Boot và Cassandra cluster và xác minh chứng chỉ như thế nào?
Bạn xử lý việc certificate rotation mà vẫn giữ kết nối client hoạt động ổn định ra sao?
Bạn lựa chọn cấu hình connect timeout, request timeout và retry policy cho Java Driver theo workload nào?
Bạn đánh giá rủi ro override quá nhiều cấu hình driver mặc định khi chưa có metrics như thế nào?
Bạn xác định cách theo dõi connection pools và session lifecycle của CqlSession như thế nào?
Bạn tổ chức nhiều CqlSession khi một ứng dụng cần truy cập nhiều keyspaces hoặc clusters theo tiêu chí nào?
Bạn tránh tạo mới CqlSession cho mỗi HTTP request bằng cấu trúc bean nào?
Bạn kiểm tra ứng dụng có khởi động được khi contact point đầu tiên không sẵn sàng nhưng cluster còn node khác như thế nào?
Bạn phân biệt lỗi keyspace không tồn tại với lỗi local datacenter hoặc credentials sai trong startup ra sao?
Bạn quản lý cấu hình riêng cho development, staging và production mà không thay đổi source code ra sao?
Trong những tình huống nào bạn cần tùy chỉnh Cassandra converter hoặc mapping context thay cho cấu hình mặc định?
Bạn thiết kế cách khởi tạo schema trong test nhưng tránh tự động thay đổi production schema như thế nào?
Bạn lựa chọn công cụ migration CQL có version tracking và quy trình rollout phù hợp như thế nào?
Bạn phân biệt cấu hình driver-level execution profile với cấu hình Spring Data repository như thế nào?
Bạn thiết kế execution profiles riêng cho truy vấn latency-sensitive và batch maintenance theo nhu cầu nào?
Bạn quản lý metrics Cassandra driver trong Micrometer mà không tạo cardinality quá cao như thế nào?
Bạn lựa chọn những cấu hình Cassandra client phải nhất quán giữa các replica Spring Boot theo nguyên tắc nào?
Bạn đánh giá ảnh hưởng của việc nâng Java driver hoặc Spring Data Cassandra lên compatibility của ứng dụng ra sao?
Bạn phân biệt cách truy cập Cassandra blocking với reactive về luồng thực thi và backpressure như thế nào?
Bạn xác định giới hạn khi bọc một API blocking bằng Mono mà không xử lý scheduler đúng như thế nào?
Bạn kiểm tra trường hợp ReactiveCassandraTemplate có giúp ích thực sự cho tải I/O của dịch vụ như thế nào?
Bạn ánh xạ một bảng Cassandra sang Java class bằng @Table và @PrimaryKey như thế nào?
Bạn chọn kiểu dữ liệu Java tương ứng với UUID, timestamp, decimal và blob trong CQL ra sao?
Bạn phân biệt @PrimaryKey với @PrimaryKeyClass và @PrimaryKeyColumn khi định nghĩa composite primary key như thế nào?
Bạn xây dựng khóa tổng hợp có nhiều partition columns và clustering columns với thứ tự chính xác ra sao?
Bạn xác định ảnh hưởng của ordinal trong @PrimaryKeyColumn tới cấu trúc khóa chính như thế nào?
Bạn phân biệt PrimaryKeyType.PARTITIONED và PrimaryKeyType.CLUSTERED trong mapping như thế nào?
Bạn thiết kế lớp khóa chính immutable để equality và hashCode không bị sai khi dùng repository ra sao?
Bạn kiểm tra entity được map đúng với tên table và column có quy tắc đặt tên khác Java field như thế nào?
Bạn sử dụng @Column khi tên cột trong CQL không phù hợp với Java naming conventions ra sao?
Bạn xử lý CQL identifiers phân biệt chữ hoa và dấu ngoặc kép khi ánh xạ entity như thế nào?
Bạn quản lý @Transient cho dữ liệu chỉ phục vụ tính toán không lưu vào Cassandra như thế nào?
Bạn đánh giá tác động của việc thêm một Java property nhưng chưa có column tương ứng trong schema như thế nào?
Bạn sử dụng @CassandraType khi cần điều khiển mapping của kiểu dữ liệu đặc biệt theo phiên bản hỗ trợ ra sao?
Bạn ánh xạ user-defined type bằng @UserDefinedType trong một entity Spring Data Cassandra như thế nào?
Bạn phân biệt UDT thông thường và frozen UDT trong giới hạn cập nhật và cấu trúc dữ liệu ra sao?
Bạn thiết kế custom converters cho một value object mà không làm lệch schema CQL như thế nào?
Bạn kiểm thử round-trip conversion từ entity sang row và ngược lại đối với UUID, enum và timestamp ra sao?
Bạn xác định cách ánh xạ nullable columns khi đọc kết quả chứa dữ liệu từ phiên bản schema cũ như thế nào?
Bạn đánh giá rủi ro chuyển đổi enum sang tên chuỗi nếu enum values bị đổi qua release như thế nào?
Bạn kiểm soát serialization của Set và Map để tránh phụ thuộc thứ tự không được bảo đảm như thế nào?
Bạn xử lý khóa chính bị thiếu thành phần trước khi đưa entity vào Cassandra repository ra sao?
Bạn xây dựng unit test cho composite key equality khi key chứa nhiều trường phân vùng và sắp xếp như thế nào?
Bạn phân biệt entity mapping cho collection columns với child entities trong quan hệ một-nhiều như thế nào?
Bạn thiết kế mapping cho một lịch sử trạng thái có nhiều rows cùng partition key và khác clustering key ra sao?
Bạn kiểm tra thao tác insert/update có vô tình ghi null làm tạo tombstones không ra sao?
Bạn đánh giá tác động của việc lưu object quá lớn trong một CQL row tới paging và network như thế nào?
Bạn chọn cách tách binary blob ra object storage khi giá trị cột trở nên quá lớn theo tiêu chí nào?
Bạn xử lý dữ liệu cũ khi thay tên column trong Java mapping mà CQL schema chưa được migration như thế nào?
Bạn thiết kế entity có trường audit createdAt và updatedAt mà không giả định timestamp Cassandra tương đương database-generated SQL timestamp ra sao?
Bạn quyết định sử dụng auditing annotations của Spring Data Cassandra ở những trường hợp nào?
Bạn kiểm thử auditing với user identity và clock điều khiển được để tránh test flaky như thế nào?
Bạn đánh giá rủi ro dùng chung một class cho API DTO, domain object và Cassandra row như thế nào?
Bạn giải thích vai trò của CassandraRepository và sự khác biệt với repository JPA như thế nào?
Bạn định nghĩa repository cho entity có composite primary key bằng generic ID type ra sao?
Bạn lựa chọn derived query methods khi các điều kiện WHERE phù hợp với partition và clustering keys như thế nào?
Bạn phát hiện derived query có thể tạo truy vấn không hợp lệ hoặc quét dữ liệu ngoài ý muốn bằng cách nào?
Bạn quyết định sử dụng @Query với CQL tường minh thay vì derived method name dựa trên yêu cầu nào?
Bạn dùng named parameters hoặc bind markers trong repository query để tránh nối chuỗi input trực tiếp như thế nào?
Bạn kiểm chứng repository method không chấp nhận filter trên cột không được hỗ trợ bởi schema như thế nào?
Bạn thiết kế repository interface chỉ expose những truy vấn được chuẩn bị theo access patterns như thế nào?
Bạn phân biệt findById cho full primary key với truy vấn dựa trên chỉ một phần composite key như thế nào?
Bạn xử lý kết quả lookup không tồn tại mà không giả định điều đó là lỗi kết nối như thế nào?
Bạn tổ chức projections để không phải đọc và truyền những cột không cần thiết như thế nào?
Bạn đánh giá rủi ro projection làm thiếu cột khóa bắt buộc trong mapping hoặc response như thế nào?
Bạn lựa chọn Slice, paging state hoặc kiểu kết quả phù hợp cho truy vấn danh sách Cassandra như thế nào?
Bạn phân biệt repository paging của Cassandra với Page chứa totalElements và phép đếm tổng thể như thế nào?
Bạn thiết kế repository trả dữ liệu theo clustering order để tránh sorting in-memory tốn tài nguyên ra sao?
Bạn đánh giá vì sao Pageable có sort tùy ý không bảo đảm Cassandra có thể thực thi hiệu quả như SQL?
Bạn kiểm soát kích thước page để giới hạn thời gian chờ, lượng dữ liệu và memory của API như thế nào?
Bạn phân biệt count query của Cassandra với ước tính tổng số bản ghi theo mô hình nghiệp vụ ra sao?
Bạn xử lý yêu cầu truy vấn theo nhiều filters không tương thích primary key bằng cách xây bảng read model như thế nào?
Bạn lựa chọn repository method cho lookup theo partition key thay vì dùng ALLOW FILTERING theo điều kiện nào?
Bạn tổ chức service layer quanh repository để việc thay schema không lan sang API controller ra sao?
Bạn đánh giá hạn chế của save khi Cassandra thực hiện upsert thay vì kiểm tra bản ghi tồn tại như RDBMS ra sao?
Bạn kiểm soát điều kiện tạo mới chỉ khi row chưa tồn tại thông qua CQL phù hợp như thế nào?
Bạn xử lý deleteById khi client retry và bản ghi có thể đã được xóa như thế nào?
Bạn xây dựng idempotency với primary key và conditional write khi cùng event được xử lý hai lần ra sao?
Bạn phân biệt CrudRepository với ReactiveCrudRepository trong hệ thống dùng Spring Data Cassandra như thế nào?
Bạn kiểm tra ReactiveCassandraRepository có được sử dụng trong reactive pipeline mà không gọi block ở event loop như thế nào?
Bạn thiết kế method trả Mono hoặc Flux cho các truy vấn phù hợp trong reactive repository ra sao?
Bạn kiểm soát concurrency khi nhiều reactive subscriptions cùng ghi vào một partition như thế nào?
Bạn đánh giá cách cancellation ảnh hưởng tới vòng đời request driver và các tác dụng phụ đã xảy ra như thế nào?
Bạn xử lý exception mapping của repository thành lỗi nghiệp vụ hoặc lỗi tạm thời phù hợp ra sao?
Bạn kiểm thử repository với Cassandra thật để phát hiện sai CQL mà mock repository không nhận ra như thế nào?
Bạn lựa chọn CassandraTemplate thay cho repository khi truy vấn yêu cầu tùy chọn thực thi đặc thù ra sao?
Bạn sử dụng CassandraTemplate để select một entity theo partition key như thế nào?
Bạn dùng CassandraTemplate cho insert, update và delete với criteria tương thích schema ra sao?
Bạn thiết kế Query hoặc Criteria để tránh tạo filter không được Cassandra hỗ trợ như thế nào?
Bạn phân biệt thao tác update từng cột với ghi lại toàn bộ entity trong CassandraTemplate như thế nào?
Bạn kiểm tra liệu thao tác update có vô tình thay đổi TTL hoặc tạo tombstones bằng cách nào?
Bạn lựa chọn truy vấn CQL trực tiếp qua CqlSession khi Spring Data template không biểu diễn đủ yêu cầu ra sao?
Bạn dùng prepared statements để truyền tham số CQL an toàn và giảm chi phí parse như thế nào?
Bạn xác định cách tái sử dụng prepared statement khi cùng truy vấn có nhiều giá trị bind khác nhau ra sao?
Bạn kiểm soát request-specific consistency level và timeout cho một truy vấn quan trọng như thế nào?
Bạn phân biệt cấu hình default consistency ở driver với consistency được chỉ định trên statement như thế nào?
Bạn thiết kế mapper đọc kết quả CQL thành DTO thay vì entity toàn bộ cột như thế nào?
Bạn dùng ReactiveCassandraTemplate khi yêu cầu streaming hoặc pipeline bất đồng bộ theo điều kiện nào?
Bạn xây dựng reactive flow phân trang mà không gom toàn bộ bảng vào bộ nhớ như thế nào?
Bạn xử lý việc hủy subscription trong lúc stream kết quả CQL còn nhiều pages như thế nào?
Bạn kiểm tra log và tracing khi một truy vấn qua CassandraTemplate mất nhiều thời gian như thế nào?
Bạn thiết kế custom repository implementation phối hợp repository cơ bản với template ra sao?
Bạn phân biệt thực thi nhiều CQL statements liên tiếp với một transaction SQL khi thiết kế nghiệp vụ ra sao?
Bạn lựa chọn logged hoặc unlogged BATCH theo số partition và yêu cầu atomicity như thế nào?
Bạn đánh giá vì sao dùng Cassandra BATCH cho hàng nghìn writes không tự động làm tăng throughput ra sao?
Bạn tổ chức ghi nhiều rows cùng partition mà vẫn tuân thủ giới hạn kích thước batch ra sao?
Bạn kiểm tra batch statement ảnh hưởng latency và coordinator load khi trải trên nhiều partitions như thế nào?
Bạn thiết kế xử lý lỗi giữa chừng khi gửi batch và client không chắc server đã hoàn tất như thế nào?
Bạn đánh giá tính nhất quán khi các thao tác update nhiều bảng denormalized xảy ra tuần tự ra sao?
Bạn giải thích write consistency level ONE, QUORUM và ALL thể hiện điều kiện thành công khác nhau như thế nào?
Bạn phân biệt LOCAL_QUORUM với QUORUM khi Cassandra được triển khai nhiều datacenter ra sao?
Bạn chọn read và write consistency levels dựa trên yêu cầu latency, khả năng sẵn sàng và freshness ra sao?
Bạn diễn giải điều kiện R + W lớn hơn replication factor trong bối cảnh các giới hạn thực tế của Cassandra như thế nào?
Bạn đánh giá vì sao một read QUORUM vẫn cần xem xét concurrent writes và repair khi xác định độ mới dữ liệu ra sao?
Bạn phân biệt write acknowledgment thành công với mọi replicas đã nhận cùng giá trị ngay lập tức như thế nào?
Bạn mô tả cơ chế hinted handoff hỗ trợ replica tạm mất kết nối và giới hạn của nó ra sao?
Bạn so sánh read repair và anti-entropy repair theo mục đích và thời điểm hoạt động trên phiên bản Cassandra nào?
Bạn thiết kế lịch repair định kỳ để tránh dữ liệu phân kỳ vượt quá thời gian cho phép như thế nào?
Bạn phân biệt commit log durability với consistency level của một write request như thế nào?
Bạn giải thích last-write-wins reconciliation và ảnh hưởng của write timestamps như thế nào?
Bạn xác định rủi ro đồng hồ hệ thống không đồng bộ làm dữ liệu cũ thắng dữ liệu mới ra sao?
Bạn lựa chọn dùng server-assigned hoặc client-supplied write timestamp theo chính sách nào?
Bạn đánh giá tác động của ghi đồng thời cùng primary key từ nhiều services khi không có transaction toàn cục như thế nào?
Bạn sử dụng IF NOT EXISTS hoặc IF condition để thực hiện lightweight transaction khi cần như thế nào?
Bạn phân biệt regular consistency với serial consistency trong lightweight transactions ra sao?
Bạn đánh giá chi phí latency và contention của lightweight transaction so với upsert thông thường như thế nào?
Bạn thiết kế thử nghiệm hai workers cùng tạo một business key để xác minh conditional insert ra sao?
Bạn xử lý CAS operation thất bại vì điều kiện không còn đúng như thế nào?
Bạn tránh dùng lightweight transactions trên partition cực nóng bằng cách điều chỉnh mô hình nghiệp vụ ra sao?
Bạn phân biệt batch atomicity với transaction isolation khi nghiệp vụ cập nhật nhiều rows như thế nào?
Bạn đánh giá khi nào nên thực hiện saga hoặc outbox ở tầng ứng dụng thay vì dựa vào Cassandra BATCH ra sao?
Bạn xác định ảnh hưởng của network partition khi read/write consistency chọn mức quá cao như thế nào?
Bạn xử lý UnavailableException khác với ReadTimeout và WriteTimeout từ driver như thế nào?
Bạn phân biệt retry an toàn của read với retry write có side effects khi không biết kết quả trước đó ra sao?
Bạn kiểm soát request idempotence flag của CQL statement để driver retry hoặc speculative execution phù hợp như thế nào?
Bạn đánh giá rủi ro speculative execution với statements không idempotent như thế nào?
Bạn kiểm tra read/write consistency thực tế được áp trong test thay vì chỉ dựa vào cấu hình như thế nào?
Bạn phân biệt TTL áp trên giá trị cột, TTL mặc định của bảng và TTL được chỉ định cho thao tác ghi như thế nào?
Bạn sử dụng TTL cho dữ liệu sự kiện theo thời hạn lưu trữ nghiệp vụ như thế nào?
Bạn xác định hậu quả của TTL hết hạn tạo tombstones đối với read path như thế nào?
Bạn đánh giá rủi ro thực hiện DELETE trên nhiều rows khiến tombstone count tăng cao ra sao?
Bạn thiết kế xóa dữ liệu bằng partition bucketing hoặc time-window strategy để kiểm soát tombstones như thế nào?
Bạn giải thích gc_grace_seconds liên quan tới tombstone purging và repair như thế nào?
Bạn đánh giá rủi ro xóa tombstones quá sớm dẫn đến dữ liệu bị hồi sinh khi replica cũ quay lại ra sao?
Bạn tổ chức quản trị vòng đời dữ liệu khi vừa dùng TTL vừa cần hỗ trợ GDPR deletion như thế nào?
Bạn xác định khi nào cần time-window compaction cho bảng dữ liệu time-series ra sao?
Bạn so sánh SizeTieredCompactionStrategy, LeveledCompactionStrategy và TimeWindowCompactionStrategy theo dạng tải nào?
Bạn kiểm tra write amplification và read amplification khi lựa chọn compaction strategy như thế nào?
Bạn giải thích paging state của Cassandra khác gì OFFSET trong truy vấn SQL như thế nào?
Bạn thiết kế API trả next-page cursor dựa trên paging state thay vì page number như thế nào?
Bạn sử dụng CassandraPageRequest hoặc cơ chế paging tương ứng để tiếp tục truy vấn như thế nào?
Bạn xác định những ràng buộc khi dùng paging state với CQL statement, parameters và page size đã thay đổi ra sao?
Bạn bảo vệ paging state token khỏi bị sửa hoặc sử dụng sai query context bằng cách nào?
Bạn xác định vì sao paging state không nên được coi là cursor bất biến trong một tập dữ liệu đang thay đổi?
Bạn phân biệt driver fetch size với số bản ghi ứng dụng muốn hiển thị trên mỗi trang như thế nào?
Bạn lựa chọn fetch size để tránh trang dữ liệu quá lớn khi mỗi row có payload lớn như thế nào?
Bạn thiết kế pagination trong cùng một partition theo clustering key và business constraints ra sao?
Bạn xử lý API muốn nhảy trực tiếp tới trang thứ 1000 khi Cassandra không hỗ trợ offset paging hiệu quả như thế nào?
Bạn đánh giá khi nào nên lưu resume token cho job đồng bộ lâu dài thay vì dựa hoàn toàn vào paging state ra sao?
Bạn kiểm thử paging qua nhiều partitions khi truy vấn hỗ trợ pattern đó theo schema như thế nào?
Bạn phân biệt paging state với token range scan khi thực hiện full-table migration ra sao?
Bạn tổ chức parallel token range scans cho batch processing mà không gây quá tải cluster ra sao?
Bạn xử lý dữ liệu được insert hoặc delete giữa hai lượt fetch page và giải thích consistency contract cho client như thế nào?
Bạn kiểm tra trường hợp page cuối có ít bản ghi hơn fetch size mà không coi là lỗi như thế nào?
Bạn thiết kế streaming Cassandra result với ReactiveCassandraTemplate để tôn trọng nhu cầu tiêu thụ của subscriber ra sao?
Bạn kiểm tra memory pressure khi driver prefetch pages nhanh hơn service xử lý như thế nào?
Bạn đo p95 và p99 latency cho truy vấn phân trang khi partition size tăng dần ra sao?
Bạn phân biệt vấn đề slow query do hot partition với vấn đề timeout do thiếu connection hoặc coordinator overload như thế nào?
Bạn thiết kế metrics theo partition size, tombstones scanned, read latency và write latency như thế nào?
Bạn sử dụng tracing hoặc driver request logs để tìm những coordinator nodes bị truy vấn chậm ra sao?
Bạn đánh giá ảnh hưởng của query size và batch size tới coordinator CPU và network traffic như thế nào?
Bạn giảm số lần full partition scans bằng việc thay đổi primary key hoặc tạo bảng truy vấn riêng ra sao?
Bạn xác định giới hạn khi thêm secondary index vào bảng có update rate rất cao như thế nào?
Bạn kiểm soát read amplification khi bảng có nhiều SSTables và tombstones như thế nào?
Bạn lựa chọn compaction strategy cho bảng có TTL ngắn và ghi dữ liệu theo thời gian ra sao?
Bạn theo dõi pending compactions để dự báo nguy cơ read latency tăng như thế nào?
Bạn giải thích ảnh hưởng của memtable flush, commit log và disk throughput tới write latency như thế nào?
Bạn đánh giá tác động của kích thước partition lớn lên streaming, repair và bootstrap node mới ra sao?
Bạn thiết kế shard/bucket để một customer cực lớn không tạo hotspot trong hệ thống nhiều tenant ra sao?
Bạn phân tích vì sao thêm replica không luôn giải quyết hot partition khi access pattern vẫn không đổi ra sao?
Bạn tối ưu prepared statements và query parameter binding để giảm overhead khi lượng request lớn như thế nào?
Bạn kiểm soát concurrent requests từ WebFlux hoặc thread pool khi Cassandra cluster chạm giới hạn throughput ra sao?
Bạn đánh giá lựa chọn rate limiting hoặc bulkhead nhằm bảo vệ Cassandra trước traffic spike như thế nào?
Bạn xác định khi nào nên trả 429 hoặc 503 thay vì tiếp tục gửi truy vấn vào cluster đang quá tải ra sao?
Bạn tổ chức retry budget và jitter để tránh nhiều ứng dụng cùng gây retry storm vào Cassandra ra sao?
Bạn phân biệt driver request timeout với timeout tổng thể của HTTP API như thế nào?
Bạn xác định cách dùng speculative execution chỉ với những CQL statements idempotent phù hợp như thế nào?
Bạn kiểm tra local-DC routing để giảm cross-region latency khi nhiều Cassandra datacenters hoạt động ra sao?
Bạn đánh giá tác động của thay đổi replication factor hoặc consistency level tới throughput và chi phí ra sao?
Bạn lựa chọn capacity test với dữ liệu giả lập kích thước partition thực tế thay vì chỉ nhiều rows nhỏ ra sao?
Bạn truy nguyên tombstone warnings trong log và metrics về đúng truy vấn hoặc thiết kế bảng bằng cách nào?
Bạn quản lý số lượng query variants để tránh prepared statement cache phình to như thế nào?
Bạn đánh giá khi nào cần cache ở application layer và cách xử lý staleness với Cassandra ra sao?
Bạn xác định điểm nghẽn ở application mapping/conversion khác với bottleneck phía Cassandra cluster như thế nào?
Bạn dùng metrics driver request throughput và in-flight requests để ước lượng connection pool pressure như thế nào?
Bạn lựa chọn cách scale application replicas mà không làm tăng đồng thời quá nhiều sessions tới cluster ra sao?
Bạn kiểm tra query latency khi một Cassandra node bị down để định lượng ảnh hưởng tới SLO như thế nào?
Bạn xây dựng dashboard so sánh read/write errors, timeouts, unavailable và retry counts như thế nào?
Bạn thiết kế alert khi disk utilization, compaction backlog hoặc tombstones vượt ngưỡng vận hành ra sao?
Bạn bảo vệ keyspace và table permissions bằng Cassandra roles và principle of least privilege như thế nào?
Bạn cấu hình TLS, authentication và network policy cho ứng dụng truy cập cluster trong production ra sao?
Bạn đánh giá rủi ro CQL injection khi truy vấn được ghép chuỗi từ input bên ngoài như thế nào?
Bạn sử dụng prepared statements hoặc repository bind parameters để ngăn CQL injection ra sao?
Bạn quản lý secret rotation của Cassandra credentials khi nhiều application instances còn kết nối cũ như thế nào?
Bạn kiểm tra multi-tenant authorization ở service layer trước khi hình thành partition key như thế nào?
Bạn tránh ghi thông tin cá nhân hoặc CQL bind values nhạy cảm trong logs và traces như thế nào?
Bạn thiết kế audit trail cho dữ liệu quan trọng khi Cassandra không tự cung cấp đầy đủ nghiệp vụ audit như thế nào?
Bạn phân biệt encryption in transit và encryption at rest trong kiến trúc Cassandra như thế nào?
Bạn triển khai schema migration theo hướng expand-contract khi nhiều phiên bản ứng dụng cùng chạy ra sao?
Bạn lựa chọn bước nào của quy trình deploy để tạo keyspace, thiết lập replication và migration bảng trước khi ứng dụng bắt đầu nhận traffic?
Bạn dùng Testcontainers Cassandra để kiểm thử CQL schema và repository thay vì mock như thế nào?
Bạn thiết kế test dữ liệu có composite primary key để phát hiện sai ordinal hoặc clustering order ra sao?
Bạn kiểm thử entity converter của UDT, collections, enum và timestamp trên Cassandra thực như thế nào?
Bạn kiểm chứng query derived repository không sinh ALLOW FILTERING ngoài ý muốn như thế nào?
Bạn mô phỏng TTL expiration trong integration test mà không làm test phụ thuộc thời gian thực quá lâu ra sao?
Bạn kiểm thử conditional write khi hai workers cạnh tranh cùng một primary key như thế nào?
Bạn kiểm chứng Cassandra BATCH không tạo giả định atomic transaction toàn cục trong integration tests ra sao?
Bạn kiểm thử paging state qua nhiều trang và xác minh không bỏ sót bản ghi trên tập dữ liệu ổn định như thế nào?
Bạn mô phỏng thêm/xóa dữ liệu trong lúc paging để đánh giá contract ổn định theo yêu cầu nào?
Bạn thiết kế test consistency level với cluster nhiều node thay vì tin vào một node Cassandra container ra sao?
Bạn đánh giá giới hạn của single-node Testcontainers đối với kiểm thử quorum, replication và failover như thế nào?
Bạn kiểm tra driver reconnect sau khi một Cassandra node hoặc connection bị mất bằng test nào?
Bạn tổ chức fixtures và cleanup cho test Cassandra mà không để dữ liệu test trước ảnh hưởng test sau ra sao?
Bạn thiết kế load test với partition hot và tombstone-heavy data để tìm bottleneck trước production như thế nào?
Bạn kiểm thử lỗi CQL invalid, unavailable và write timeout để xác minh error mapping của service như thế nào?
Bạn phân biệt unit test adapter Spring Data với integration test có Cassandra thực theo loại lỗi phát hiện như thế nào?
Bạn kiểm tra reactive repository cancellation và timeout trong test không block event loop như thế nào?
Bạn xác định quality gates cho migration schema, query latency và partition sizes trước release ra sao?
Nếu CassandraRepository.findById không tìm thấy bản ghi dù CQL truy vấn tay thấy dữ liệu, bạn sẽ kiểm tra composite key mapping như thế nào?
Nếu truy vấn chạy nhanh lúc dữ liệu ít nhưng timeout khi bảng lớn, bạn sẽ phân tích partition key và ALLOW FILTERING ra sao?
Nếu một tenant tạo partition cực lớn làm p99 latency tăng, bạn sẽ thiết kế bucketing và backfill thế nào?
Nếu hai API đọc cùng entity nhưng cần hai kiểu sort khác nhau, bạn sẽ xây dựng các bảng read model như thế nào?
Nếu reactive API bị nghẽn dù CPU thấp, bạn sẽ tìm vấn đề blocking I/O và driver concurrency ra sao?
Nếu Spring Boot khởi động thất bại do local datacenter cấu hình sai, bạn sẽ kiểm tra topology và driver settings như thế nào?
Nếu contact point đầu tiên bị down nhưng cluster còn khỏe, bạn sẽ kiểm tra kết nối và discovery của Java Driver ra sao?
Nếu CQL SELECT báo lỗi khi filter theo cột thông thường, bạn sẽ sửa schema hoặc query thế nào?
Nếu entity có khóa tổng hợp sai thứ tự clustering column, bạn sẽ kiểm chứng mapping và dữ liệu trên bảng ra sao?
Nếu repository save trả thành công nhưng read ngay sau đó ở consistency thấp không thấy dữ liệu, bạn sẽ điều tra consistency như thế nào?
Nếu một write timeout xảy ra nhưng dữ liệu thực tế đã được ghi, bạn sẽ quyết định retry an toàn ra sao?
Nếu lightweight transaction liên tục thất bại do contention, bạn sẽ phân tích partition hot và thiết kế lại luồng như thế nào?
Nếu dữ liệu đã xóa xuất hiện lại sau sự cố replica kéo dài, bạn sẽ kiểm tra tombstone grace và repair ra sao?
Nếu một bảng TTL ngắn xuất hiện hàng triệu tombstones, bạn sẽ đánh giá compaction và mô hình time buckets như thế nào?
Nếu Cassandra BATCH trên nhiều partitions làm latency tăng, bạn sẽ tách batch và giữ invariant nghiệp vụ như thế nào?
Nếu API pagination trả bản ghi trùng khi dữ liệu thay đổi giữa hai trang, bạn sẽ giải thích giới hạn paging state và sửa contract như thế nào?
Nếu client muốn nhảy tới trang 500 bằng offset, bạn sẽ thiết kế lại cursor pagination theo Cassandra như thế nào?
Nếu Java Driver báo ReadTimeout nhưng Cassandra cluster metrics không có CPU spike, bạn sẽ kiểm tra network và replica latency ra sao?
Nếu driver retry policy làm số writes tăng cao trong giờ cao điểm, bạn sẽ kiểm soát idempotency và retry budget thế nào?
Nếu ConsistencyLevel.ALL làm API mất khả năng phục vụ khi một replica down, bạn sẽ cân nhắc điều chỉnh theo yêu cầu nào?
Nếu cùng business key bị ghi hai lần từ hai consumers, bạn sẽ dùng conditional insert và idempotency để bảo vệ dữ liệu như thế nào?
Nếu một update ghi null làm mất dữ liệu ngoài ý muốn, bạn sẽ kiểm tra mapping và CQL statement trước khi sửa như thế nào?
Nếu UDT mapping hoạt động ở local nhưng lỗi trên cluster production, bạn sẽ so sánh schema versions và converters ra sao?
Nếu nhiều datacenters đọc ra giá trị khác nhau sau network partition, bạn sẽ phân tích consistency, timestamps và repair ra sao?
Nếu node bootstrap kéo dài do một số partitions quá lớn, bạn sẽ xây dựng kế hoạch tái phân bố dữ liệu như thế nào?
Nếu API tăng tải làm Cassandra pending compactions vượt ngưỡng, bạn sẽ điều chỉnh rate limit và capacity ra sao?
Nếu Spring Data Cassandra upgrade khiến repository query lỗi, bạn sẽ kiểm tra driver, dialect và mapping changes như thế nào?
Nếu secret Cassandra bị rotate khiến hàng loạt connection thất bại, bạn sẽ xử lý credential refresh và khôi phục ra sao?
Nếu hệ thống phát hiện CQL query ghi log chứa PII, bạn sẽ ngăn rò rỉ và chỉnh chính sách observability như thế nào?
Bạn xây dựng runbook khi Cassandra cluster bị partition, nhiều reads stale, repair backlog cao và API tiếp tục retry như thế nào?
