# Lỗi JDBC schema, thiếu quyền, duplicate key và cạn kết nối

Spring Session JDBC lưu HTTP session trong các bảng quan hệ dùng chung, thường là SPRING_SESSION và SPRING_SESSION_ATTRIBUTES. Khi ứng dụng không khởi động được repository, không tạo được session hoặc request bị treo lúc lưu phiên, nguyên nhân thường nằm ở schema/migration, quyền database, ràng buộc khóa hoặc connection pool. Cần đọc đúng SQLState, vendor error code và tên constraint để phân loại sự cố; chỉ nhìn exception ngoài cùng như DataAccessException thường chưa đủ.

Một lỗi ở session repository có thể ảnh hưởng tới hầu hết request vì SessionRepositoryFilter cần đọc hoặc lưu session trong vòng đời HTTP. Nếu mọi request đều cần session và database không truy cập được, lỗi có thể biểu hiện như người dùng liên tục bị đăng xuất, request trả 5xx, latency tăng hoặc toàn bộ pool bị chiếm. Bài này trình bày cách chẩn đoán theo từng nhóm lỗi, phục hồi an toàn và kiểm thử bằng database thực.

## 1. Spring Session JDBC lưu những gì?

Spring Session JDBC dùng repository như JdbcIndexedSessionRepository để ánh xạ session thành các hàng dữ liệu. Schema chuẩn thường có:

- SPRING_SESSION: metadata của session như khóa nội bộ, session ID, thời điểm tạo, lần truy cập cuối, khoảng không hoạt động và thời điểm hết hạn.
- SPRING_SESSION_ATTRIBUTES: các thuộc tính session được serialize, gắn với hàng session tương ứng.

Schema script chính xác phụ thuộc phiên bản Spring Session và hệ quản trị database. Các cột, kiểu dữ liệu, độ dài, tên constraint và index có thể thay đổi. Luôn lấy schema script tương ứng với phiên bản dependency và database đang triển khai; không tự tạo bảng dựa trên một ví dụ cũ.

Luồng đơn giản:

~~~mermaid
flowchart TD
    R[HTTP request] --> F[SessionRepositoryFilter]
    F --> J[JdbcIndexedSessionRepository]
    J --> P[Connection pool]
    P --> D[(Database)]
    D --> S[SPRING_SESSION]
    D --> A[SPRING_SESSION_ATTRIBUTES]
    S --> J
    A --> J
    J --> F
    F --> R
~~~

Session data là dữ liệu vận hành có vòng đời ngắn, nhưng vẫn cần schema ổn định, index phù hợp, quyền tối thiểu và khả năng kết nối. Khi repository lỗi, cần phân biệt lỗi tìm session, lỗi ghi session, lỗi cleanup và lỗi truy cập database dùng chung cho nghiệp vụ.

## 2. Triệu chứng và nhóm nguyên nhân

| Nhóm lỗi | Triệu chứng thường thấy | Bằng chứng cần lấy |
| --- | --- | --- |
| Schema thiếu hoặc sai | relation/table not found, invalid column, type mismatch | SQLState, câu SQL, schema hiện hành, migration version |
| Thiếu quyền | permission denied, not authorized, cannot insert/update/delete | DB user, role membership, quyền schema/table/sequence |
| Duplicate key | unique constraint violation, duplicate entry | Tên constraint, giá trị khóa, thao tác insert/update và request correlation |
| Cạn connection pool | connection timeout, pending borrowers, latency tăng | active/idle/pending/max pool, query/transaction duration |
| Database unavailable | connection refused, DNS/TLS/authentication failure | DB health, network, credentials, failover state |
| Lock contention | lock wait timeout, deadlock victim | transaction đang giữ lock, query plan, thời gian transaction |

Không nên xử lý mọi nhóm bằng cách tăng timeout hoặc tăng pool size. Schema sai cần migration; thiếu quyền cần grant đúng; duplicate key cần xác định constraint; pool exhaustion cần tìm nơi giữ connection hoặc tạo quá nhiều truy vấn.

## 3. Kiểm tra cấu hình Spring Boot JDBC session

Một cấu hình minh họa:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/sessiondb
    username: app_runtime
    password: injected-by-secret-manager
    hikari:
      maximum-pool-size: 20
      connection-timeout: 3000
  session:
    store-type: jdbc
    timeout: 30m
    jdbc:
      initialize-schema: never
      table-name: SPRING_SESSION
~~~

Property chính xác phụ thuộc phiên bản Spring Boot. Một số phiên bản tự suy luận store type khi dependency hiện diện; hãy kiểm tra configuration metadata và bean thực tế, không sao chép cấu hình từ phiên bản khác. table-name thường xác định tên bảng session chính; bảng attributes được repository quản lý theo naming convention/schema tương ứng của phiên bản.

Trong production, schema nên được tạo bằng migration có kiểm soát trước khi application node khởi động. initialize-schema: never minh họa việc ứng dụng không tự tạo schema. Không bật tự khởi tạo schema trên mọi instance trong production nếu nhiều node có thể khởi động cùng lúc hoặc role runtime không được cấp DDL.

## 4. Lỗi thiếu bảng hoặc sai schema

Các thông báo phổ biến:

- Table/relation SPRING_SESSION does not exist.
- Invalid object name hoặc table not found.
- Column not found, unknown column hoặc invalid identifier.
- Data truncation/type mismatch khi ghi attribute hoặc session ID.

Nguyên nhân thường gặp:

1. Migration chưa chạy hoặc chạy vào database/schema khác.
2. Ứng dụng dùng search_path/current schema khác với tài khoản migration.
3. Tên bảng khác chữ hoa/thường giữa DDL và cấu hình.
4. Schema script lấy từ phiên bản Spring Session khác.
5. Bảng attributes chưa được tạo dù bảng session đã có.
6. Migration một phần thất bại hoặc rollback không như dự kiến.

Quy trình chẩn đoán:

1. Ghi nhận JDBC URL đã loại bỏ thông tin nhạy cảm, database name và schema hiện hành.
2. Xác định đúng DB principal mà application runtime sử dụng.
3. Tra cứu metadata hệ quản trị để xác nhận hai bảng, cột, khóa và index.
4. So sánh schema thực tế với script đi kèm đúng phiên bản Spring Session.
5. Kiểm tra migration history và log triển khai.
6. Kiểm tra table-name và schema qualification mà repository đang dùng.

Không tạo bảng thủ công ngay trên production chỉ để làm request chạy lại. Trước hết xác định schema version và migration còn thiếu; nếu bảng được tạo sai cấu trúc, việc thêm một bảng mới có thể che lỗi và làm dữ liệu không tương thích.

## 5. Quản lý schema bằng Flyway hoặc Liquibase

Schema Spring Session là một phần của database contract. Nên quản lý nó bằng migration có version, review và kiểm thử trước khi deploy. Migration cần được chạy một lần bởi tài khoản triển khai có quyền DDL; application runtime dùng tài khoản ít quyền hơn.

Một quy trình triển khai:

1. Chọn đúng schema script Spring Session cho database và dependency version.
2. Chuyển script thành migration có version, giữ nguyên các constraint/index cần thiết.
3. Chạy migration trên database test/staging.
4. Khởi chạy ứng dụng đúng version và kiểm tra create, read, update, delete session.
5. Triển khai migration trước hoặc theo chiến lược expand/contract tương thích với rolling deployment.
6. Khởi động application node bằng runtime account chỉ có quyền DML cần thiết.
7. Theo dõi lỗi SQL sau deploy và có kế hoạch rollback/forward-fix.

Khi nâng Spring Session, so sánh schema script mới với schema hiện tại. Không giả định schema luôn bất biến giữa các phiên bản. Nếu cần thay đổi bảng, dùng migration tương thích với node cũ và mới trong giai đoạn rolling deployment.

## 6. Tên bảng, schema và chữ hoa/thường

Một số hệ quản trị chuẩn hóa identifier không đặt trong dấu quote; một số phân biệt chữ hoa/thường khi identifier được quote. Ví dụ migration tạo bảng có tên quoted lowercase, trong khi repository truy vấn tên uppercase, có thể dẫn tới table not found dù nhìn tên gần giống nhau.

Kiểm tra:

- Tên table thực tế trong database catalog.
- Schema/search_path/currentSchema trong JDBC URL.
- Cấu hình table-name của Spring Session.
- Cách migration quote identifier.
- Quyền trên đúng schema và đúng table.

Tránh đổi table name tùy tiện trong khi session đang được lưu. Nếu cần đổi, lập kế hoạch copy/migrate dữ liệu và triển khai đồng bộ. Tên bảng session và attributes phải khớp với repository convention.

## 7. Lỗi thiếu quyền database

Application runtime thường cần đọc, thêm, sửa và xóa session data. Tùy database và schema tùy chỉnh, quyền cần thiết thường gồm:

- SELECT trên bảng session và attributes.
- INSERT để tạo session và attribute row.
- UPDATE để cập nhật metadata/session attributes.
- DELETE để invalidate session, xóa attributes và cleanup.
- USAGE trên schema hoặc quyền tương đương để truy cập object.
- Quyền sequence nếu schema tùy chỉnh sử dụng sequence/identity cần quyền riêng.

Không cấp quyền CREATE, ALTER, DROP hoặc quyền quản trị database cho application runtime chỉ để khắc phục lỗi bảng chưa tồn tại. Những quyền DDL nên thuộc migration account riêng.

Ví dụ minh họa PostgreSQL, giả sử schema app_session và role app_runtime:

~~~sql
GRANT USAGE ON SCHEMA app_session TO app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app_session.spring_session,
         app_session.spring_session_attributes
TO app_runtime;
~~~

Tên bảng thực tế có thể uppercase hoặc được quote tùy migration. Điều chỉnh cú pháp theo catalog và naming của database. Nếu dùng schema chuẩn với bảng được tạo khác tên, grant ở trên không tự áp dụng.

Một số database yêu cầu quyền riêng cho sequence hoặc quyền connect database. Hãy xác minh bằng catalog/metadata và thực hiện grant tối thiểu cần thiết. Không cấp ALL PRIVILEGES trên toàn database khi chỉ cần quyền DML trên hai bảng session.

## 8. Phân biệt quyền runtime và quyền migration

Nên dùng hai danh tính database:

| Tài khoản | Công việc | Quyền |
| --- | --- | --- |
| migration_user | Tạo/đổi schema và index | DDL có kiểm soát trên schema session |
| app_runtime | Đọc/ghi/xóa session | SELECT, INSERT, UPDATE, DELETE và quyền truy cập schema cần thiết |

Điều này giúp giảm tác động nếu thông tin đăng nhập ứng dụng bị lộ. Nó cũng làm rõ lỗi permission: nếu migration thành công nhưng ứng dụng không chạy, kiểm tra runtime grant; nếu migration thất bại, kiểm tra migration principal và DDL.

Sau khi thay đổi grant, pool có thể còn connection cũ với role/session state cũ tùy database. Hãy xác minh bằng connection mới và một thao tác repository thực tế. Không chỉ dựa vào việc DBA xác nhận đã chạy GRANT.

## 9. Chẩn đoán duplicate key

Duplicate key nghĩa là thao tác ghi vi phạm một primary key hoặc unique constraint. Với schema Spring Session chuẩn, các khóa thường liên quan tới:

- Khóa nội bộ của row session.
- Session ID có unique constraint.
- Cặp khóa liên kết attribute row với session và tên attribute.

Tên cột và constraint cụ thể phải được xác nhận từ schema thực tế. Không kết luận mọi lỗi duplicate key đều là trùng session ID; duplicate có thể phát sinh ở bảng attributes hoặc do schema/index tùy chỉnh.

Thông tin cần thu thập:

1. SQLState và vendor error code.
2. Tên bảng và constraint bị vi phạm.
3. Thao tác repository đang thực hiện: tạo session, lưu session, cập nhật attribute hay cleanup.
4. Request correlation ID, application node và thời điểm.
5. Có retry, request lặp hoặc nhiều node cùng xử lý một session không.
6. Schema migration có tạo duplicate unique index hoặc cấu hình key sai không.

Spring có thể dịch lỗi JDBC thành DataIntegrityViolationException hoặc DuplicateKeyException tùy driver, exception translator và phiên bản. Luôn xem root cause để xác định constraint cụ thể.

## 10. Duplicate ở bảng session và bảng attributes

Nếu constraint trên SESSION_ID bị vi phạm, kiểm tra liệu cùng một ID có đang được insert nhiều lần hay không. Có thể do ID generator tùy chỉnh không đảm bảo duy nhất, request retry tạo lại cùng một session, stale row còn tồn tại sau quy trình rotation sai hoặc code custom gọi create/save không đúng contract.

Nếu constraint trên PRIMARY_ID bị vi phạm, kiểm tra generator khóa nội bộ, migration/schema và việc tạo row đồng thời. Với UUID đủ entropy, collision tự nhiên rất hiếm; nếu xảy ra thường xuyên, nghi ngờ ID generator bị cố định trong test, custom implementation lỗi hoặc dữ liệu bị copy/restore sai.

Nếu constraint trên attributes bị vi phạm, kiểm tra hai thao tác đồng thời cùng insert một attribute row, logic delete/insert khi cập nhật, transaction boundary và custom schema. Hai request có thể cùng cập nhật session; không tự giả định repository sẽ merge attributes. Kiểm thử concurrency trên đúng database và phiên bản Spring Session.

Không xóa row đang bị duplicate bằng tay trước khi biết row đó thuộc session nào và còn được sử dụng hay không. Xóa nhầm có thể làm người dùng khác mất phiên hoặc để lại attribute row mồ côi.

## 11. Retry duplicate key như thế nào?

Không retry mọi DuplicateKeyException một cách tự động. Duplicate key thường là lỗi dữ liệu/logic, không phải lỗi transient như network reset. Retry y nguyên cùng insert có thể lặp lại cùng lỗi.

Một quy trình an toàn:

1. Xác định constraint bị vi phạm.
2. Xác định thao tác có idempotent không và request trước có thể đã commit không.
3. Nếu là create session với ID được sinh mới, chỉ tạo lại theo semantics repository khi biết lần ghi trước chưa thành công và không tái sử dụng ID xung đột.
4. Nếu là update attribute, đọc lại trạng thái và xử lý version/concurrency theo nghiệp vụ.
5. Nếu commit outcome không rõ, kiểm tra trạng thái trước khi retry.
6. Ghi metric và giới hạn retry; không retry vô hạn trong request thread.

Đối với thao tác nghiệp vụ như thanh toán/đặt hàng được kích hoạt từ request có session, idempotency key phải nằm ở tầng nghiệp vụ/database. Session repository không thay thế idempotency của nghiệp vụ.

## 12. Duplicate key trong môi trường test

Test có thể tạo duplicate key giả do dùng ID cố định, chia sẻ database giữa test chạy song song hoặc không dọn dữ liệu sau mỗi test. Các cách phòng tránh:

- Dùng database/schema hoặc table prefix riêng cho từng test run.
- Sinh session ID test duy nhất; không mock generator trả cùng một ID cho nhiều test.
- Dọn session/attributes sau test bằng repository hoặc transaction phù hợp.
- Không chạy cleanup toàn bảng khi test khác đang dùng chung database.
- Chạy test concurrency có barrier rõ ràng để tái hiện race, không dựa vào sleep ngẫu nhiên.
- Kiểm tra unique constraint thực tế và không vô hiệu hóa constraint để test pass.

H2 hữu ích cho test nhanh nhưng có thể khác production về SQL dialect, identifier case, locking, isolation, unique constraint, schema privileges và connection behavior. Dùng Testcontainers hoặc database test cùng engine/version gần production để kiểm tra duplicate key và migration.

## 13. Cạn kết nối: connection pool exhaustion

Spring Session JDBC cần lấy connection để truy vấn hoặc lưu session. HikariCP giới hạn số connection tối đa. Khi mọi connection đều đang được sử dụng và request mới cần thêm connection, request phải chờ đến connectionTimeout. Nếu chờ quá lâu, ứng dụng có thể báo lỗi kiểu connection is not available, request latency tăng và thread pool dần bị chiếm.

Các nguyên nhân thường gặp:

- Pool quá nhỏ so với concurrency và thời gian giữ connection.
- Query chậm hoặc database quá tải.
- Transaction kéo dài hoặc giữ lock.
- Connection leak do code tự lấy connection mà không đóng.
- Deadlock/lock wait khiến connection bị giữ lâu.
- Nhiều application node cùng dùng pool lớn hơn khả năng DB.
- Session repository và business query dùng chung pool, khiến một luồng traffic chiếm hết connection của luồng còn lại.

Không tăng maximumPoolSize một cách mù quáng. Nếu database chỉ cho phép 100 connection và 8 application node mỗi node mở tối đa 30, tổng nhu cầu lý thuyết có thể vượt xa giới hạn database.

## 14. Đọc HikariCP metrics

Các chỉ số quan trọng:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| active | Số connection đang được mượn | Luôn sát maximumPoolSize |
| idle | Số connection đang rảnh | Bằng 0 trong thời gian dài |
| pending | Số thread đang chờ connection | Tăng liên tục |
| max | Giới hạn connection pool | Tổng pool các node vượt DB budget |
| connection acquisition time | Thời gian lấy connection | P95/P99 tăng mạnh |
| usage duration | Thời gian giữ connection | Cao bất thường so với query thực |

Nếu active bằng max, idle bằng 0 và pending tăng, pool đang bão hòa. Tiếp theo phải tìm lý do connection bị giữ: query chậm, lock wait, transaction kéo dài, leak hoặc pool sizing. Chỉ tăng connectionTimeout làm request chờ lâu hơn; không tạo thêm connection và có thể làm thread bị giữ lâu hơn.

HikariCP có thể xuất metric qua Micrometer/Actuator khi được cấu hình. Tên metric cụ thể phụ thuộc phiên bản và registry. Bật leak detection threshold chỉ để điều tra ở mức phù hợp; ngưỡng quá thấp có thể tạo cảnh báo giả cho query hợp lệ.

## 15. Ước lượng pool size cho nhiều application node

Pool size phải được tính trên tổng số node, không chỉ từng JVM:

~~~text
total_app_connections =
    number_of_nodes * maximum_pool_size_per_node

database_budget =
    max_connections
    - admin_reserve
    - migration_reserve
    - other_service_connections
~~~

Tổng connection tối đa của các application node phải nằm trong budget database, có dự phòng cho failover, job và thao tác quản trị. Nếu có nhiều datasource hoặc replica, tính riêng từng endpoint.

Ví dụ database có budget 120 connection cho ứng dụng, 6 node, mỗi node đặt pool max 15 thì tổng tối đa là 90; còn 30 connection dự phòng. Đây chỉ là phép tính minh họa, không phải khuyến nghị pool size phổ quát. Sizing thực tế phụ thuộc throughput, query latency, transaction duration và năng lực DB.

Little's Law có thể giúp ước lượng concurrency: số connection trung bình cần thiết gần bằng throughput nhân thời gian giữ connection. Đo bằng workload thật thay vì chỉ lấy số thread HTTP làm pool size.

## 16. Tách pool session và pool nghiệp vụ?

Nếu session repository có traffic cao hoặc độ trễ khác biệt với truy vấn nghiệp vụ, có thể cân nhắc datasource/pool riêng cho session. Điều này giảm nguy cơ session lookup chiếm toàn bộ pool business hoặc ngược lại. Tuy nhiên, hai pool cùng trỏ một database vẫn tiêu thụ chung giới hạn connection của database.

Trước khi tách pool:

- Xác định repository có hỗ trợ cấu hình datasource riêng trong phiên bản đang dùng.
- Tính tổng connection của mọi pool và mọi node.
- Tránh tăng tổng số connection vượt DB budget.
- Thiết lập timeout, metrics và alert riêng.
- Xác định hành vi khi pool session hết nhưng pool business còn, và ngược lại.

Tách pool không sửa được query chậm hoặc transaction giữ lock. Nó chỉ cô lập một phần tài nguyên và cần được đánh giá bằng tải thực.

## 17. Transaction, lock và connection leak

Session save/delete có thể diễn ra trong transaction hoặc qua các thao tác repository được quản lý transaction theo implementation. Business code cũng có thể giữ transaction lâu trong khi xử lý request. Nếu transaction mở quá lâu, connection bị giữ dù database không chạy query liên tục.

Các nguyên tắc:

- Giữ transaction ngắn và giới hạn vùng code cần atomicity.
- Không gọi API ngoài, chờ user hoặc xử lý file lớn trong khi giữ DB transaction.
- Kiểm tra query plan và index cho session lookup/expiry cleanup.
- Theo dõi lock wait và deadlock.
- Luôn đóng Connection/Statement/ResultSet khi code tự quản lý JDBC; ưu tiên JdbcTemplate hoặc transaction manager.
- Không giữ connection trong field singleton hoặc lưu connection vào session.

Nếu Hikari leak detection báo một connection bị giữ lâu, trace stack có thể chỉ ra nơi mượn connection. Nhưng một cảnh báo không luôn chứng minh leak; query/transaction hợp lệ cũng có thể vượt ngưỡng. Đối chiếu stack trace với DB activity và thời gian usage.

## 18. Cleanup job và session table tăng trưởng

Spring Session JDBC cần dọn session hết hạn để giới hạn kích thước bảng. Cleanup query có thể xóa theo EXPIRY_TIME hoặc cơ chế tương ứng phiên bản. Nếu cleanup không chạy, thiếu quyền DELETE hoặc index không phù hợp, bảng có thể tăng liên tục và làm lookup/cleanup chậm hơn.

Kiểm tra:

- Job cleanup có được kích hoạt theo cấu hình và phiên bản không.
- Runtime role có quyền DELETE trên cả hai bảng liên quan không.
- Index phục vụ expiry query có tồn tại theo schema script không.
- Cleanup có chạy theo batch và không tạo lock quá dài không.
- Session attributes có bị orphan nếu custom delete không cascade/không xóa bảng phụ không.

Không tự chạy DELETE toàn bảng trong giờ cao điểm. Dùng cleanup mechanism của repository hoặc batch đã kiểm thử. Nếu phải dọn thủ công, lọc đúng expiry time, giới hạn batch, đo lock/replication lag và có backup/approval theo quy trình vận hành.

## 19. Runbook xử lý lỗi schema

Khi nhận lỗi table/column not found:

1. Xác định application version, Spring Session version và DB engine/version.
2. Xác định database, schema, table-name và runtime DB user.
3. Đọc root SQL exception, SQLState và vendor code.
4. Kiểm tra migration history và catalog của đúng schema.
5. So sánh schema với script đúng version.
6. Nếu migration thiếu, chạy migration đã review bằng tài khoản triển khai.
7. Xác minh bằng một session create/read/update/delete từ ứng dụng.
8. Theo dõi lỗi sau khi mọi application node được cập nhật.

Nếu schema sai do migration trước, ưu tiên forward-fix có kiểm soát. Không xóa bảng session để tạo lại nếu đang có người dùng đăng nhập; thao tác đó sẽ invalidate toàn bộ phiên và có thể làm mất trạng thái người dùng.

## 20. Runbook xử lý permission denied

Khi database báo thiếu quyền:

1. Lấy principal thực tế từ connection của application, không suy từ secret file.
2. Xác định thao tác thất bại: SELECT, INSERT, UPDATE, DELETE hay DDL.
3. Kiểm tra quyền schema, table và sequence nếu có.
4. So sánh quyền runtime với quyền migration.
5. Cấp đúng quyền tối thiểu trên đúng object.
6. Tạo connection mới hoặc recycle pool theo quy trình nếu cần.
7. Kiểm thử đủ create, read, update, logout/delete và expiry cleanup.

Không giải quyết bằng cách cấp DBA/superuser cho application. Quyền quá rộng làm tăng blast radius khi credential bị lộ.

## 21. Runbook xử lý duplicate key

Khi gặp duplicate key:

1. Giữ nguyên root exception, SQLState, vendor code và constraint name.
2. Xác định bảng và cột/constraint bị vi phạm.
3. Phân biệt session ID, internal primary key và attribute key.
4. Kiểm tra request retry, concurrency, node ID và ID generator.
5. Xác minh migration không tạo constraint sai hoặc dữ liệu trùng từ import/restore.
6. Kiểm tra row liên quan bằng truy vấn read-only và bảo vệ dữ liệu nhạy cảm.
7. Chọn cách xử lý: sửa ID generation, xử lý concurrency, sửa migration hoặc khôi phục dữ liệu có kiểm soát.
8. Chỉ retry khi biết thao tác an toàn và trạng thái commit đã được xác định.

Không bắt exception rồi tiếp tục như session đã lưu. Nếu save thất bại, request có thể đã trả response nhưng session state chưa bền vững; cần xác định semantics và xử lý lỗi rõ ràng.

## 22. Runbook xử lý pool exhaustion

Khi Hikari connection timeout tăng:

1. Kiểm tra active, idle, pending và maximum pool size ở tất cả node.
2. Kiểm tra DB connection count và giới hạn max connections.
3. Xem query latency, lock wait, deadlock và transaction age.
4. Kiểm tra leak detection/connection usage stack nếu có.
5. Xác định pool bị chiếm bởi session operations hay business operations.
6. Giảm tải hoặc scale theo giới hạn database; không tăng pool tổng vượt budget.
7. Tối ưu query/index và rút ngắn transaction.
8. Chỉ thay đổi pool size/timeout sau khi đo lại concurrency và DB capacity.
9. Xác minh pending giảm và acquisition latency trở về ngưỡng.

Trong sự cố, có thể tạm giảm request rate hoặc tắt endpoint không thiết yếu để giải phóng tài nguyên. Không restart đồng loạt mọi node một cách tùy tiện; việc này có thể tạo connection storm khi toàn bộ pool cùng reconnect.

## 23. Kiểm thử bằng database thực

H2 hữu ích cho test nhanh nhưng có thể khác production về SQL dialect, identifier case, locking, isolation, unique constraint, schema privileges và connection behavior. Với lỗi vận hành JDBC, ưu tiên Testcontainers chạy đúng engine hoặc database staging tương đương.

Test matrix:

| Kịch bản | Cách tạo | Kết quả mong đợi |
| --- | --- | --- |
| Thiếu bảng | Không chạy migration | Startup/request báo lỗi schema rõ ràng |
| Sai schema/table | Trỏ datasource tới schema khác | Lỗi được phân loại đúng, không tạo bảng ngoài ý muốn |
| Thiếu SELECT | Runtime role không có quyền đọc | Repository báo permission error |
| Thiếu INSERT/UPDATE | Thu hồi quyền ghi | Save/create thất bại rõ ràng |
| Thiếu DELETE | Thu hồi quyền xóa | Logout/cleanup báo lỗi và có metric |
| Duplicate key | Tạo constraint violation có kiểm soát | Root constraint được nhận diện; không retry vô hạn |
| Pool exhaustion | Pool nhỏ và giữ connection có kiểm soát | Pending/timeout được quan sát và test có deadline |
| Lock contention | Transaction test giữ row/table lock | Latency/lock timeout được phân loại |
| Cleanup | Tạo session hết hạn | Repository không khôi phục; cleanup xóa dữ liệu theo policy |

Không chạy test phá quyền hoặc khóa bảng trên database production. Dùng database/container riêng cho test và đảm bảo test dọn tài nguyên sau khi hoàn tất.

## 24. Quan sát và cảnh báo

Nên có dashboard tách biệt giữa session repository và database:

Spring Session/application:

- Tỷ lệ session create/find/save/delete thành công và thất bại.
- Latency repository ở p50/p95/p99.
- Số lỗi DataAccessException, DuplicateKeyException và serialization.
- Số request tạo session mới bất thường sau repository failure.
- Node ID, application version và datasource name.

HikariCP:

- Active, idle, pending, max.
- Connection acquisition time và usage duration.
- Timeout count và leak detection events.

Database:

- Connection count và số connection còn khả dụng.
- Query latency, lock wait, deadlock và slow query.
- Kích thước bảng session/attributes và tốc độ tăng.
- Cleanup duration, rows deleted và index health.
- Migration version và schema drift.

Không log session ID, cookie hoặc serialized session payload. Khi cần correlation, dùng request ID và fingerprint không thể dùng lại làm credential.

## 25. Checklist phòng ngừa

- [ ] Schema lấy từ đúng phiên bản Spring Session và đúng DB dialect.
- [ ] Migration được quản lý/version hóa, chạy trước khi application cần bảng.
- [ ] Runtime role tách khỏi migration role và chỉ có quyền DML cần thiết.
- [ ] Datasource URL, schema, table-name và search_path nhất quán trên mọi node.
- [ ] Primary key, unique constraint và index đúng với schema script.
- [ ] Duplicate key được chẩn đoán theo constraint; không retry mù.
- [ ] Test ID generator không trả ID cố định giữa các request.
- [ ] Hikari active/idle/pending/max được theo dõi và cảnh báo.
- [ ] Tổng pool size của tất cả node nằm trong database connection budget.
- [ ] Query và transaction ngắn; không giữ connection qua công việc ngoài database.
- [ ] Cleanup session hết hạn có quyền DELETE, index và batch policy phù hợp.
- [ ] Integration test dùng database engine tương đương production.
- [ ] Log redaction không để lộ session ID hoặc attributes.

## 26. Kết luận

Lỗi JDBC của Spring Session cần được phân loại theo nguyên nhân gốc. Schema thiếu/sai cần migration đúng phiên bản; permission denied cần grant tối thiểu trên schema, bảng và sequence liên quan; duplicate key cần xác định constraint và thao tác gây xung đột; pool exhaustion cần đo connection usage, query, lock và tổng giới hạn kết nối trên mọi application node.

Spring Session nằm trên đường xử lý HTTP request nên một lỗi repository có thể lan rộng thành lỗi đăng nhập, mất trạng thái hoặc cạn thread. Vận hành ổn định cần schema có version, runtime account ít quyền, connection pool được sizing theo tổng node, cleanup có kiểm soát, retry an toàn và integration test trên database tương đương production. Khi xử lý sự cố, giữ lại root SQL error và bằng chứng metrics trước khi thay đổi schema, xóa dữ liệu hoặc tăng pool.
