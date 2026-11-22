# Mở rộng hệ thống

## MySQL Router, proxy kết nối và ranh giới với connection pool

Khi ứng dụng cần kết nối đến MySQL có nhiều node, primary có thể thay đổi sau failover và số lượng connection tăng theo số instance ứng dụng. Kết nối trực tiếp đến địa chỉ một database khiến ứng dụng phải tự biết node nào đang nhận ghi, node nào phục vụ đọc và cách kết nối lại khi topology thay đổi. MySQL Router tạo một điểm kết nối ổn định ở phía trước các MySQL Server, theo dõi topology được hỗ trợ và định tuyến connection đến node phù hợp.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài này mở rộng kiến thức vận hành sang tầng kết nối: đặt Router trước MySQL, phối hợp với connection pool của ứng dụng, hiểu connection sharing, phân luồng đọc/ghi và xây dựng quy trình reconnect khi failover.

Điểm cần nắm là có nhiều lớp quản lý connection. Connection pool trong ứng dụng quản lý các kết nối JDBC mà code mượn/trả. MySQL Router nhận các kết nối từ ứng dụng và định tuyến đến server; từ Router 8.4, connection sharing có thể tái sử dụng server connection khi session đủ điều kiện. Các lớp này có mục tiêu và giới hạn khác nhau, vì vậy phải cấu hình và đo lường riêng.

### 1. Kiến trúc kết nối nhiều lớp

Luồng phổ biến khi dùng Router và pool:

~~~mermaid
flowchart LR
    A[Application instances] --> B[Application connection pool]
    B --> C[Router service / load balancer]
    C --> D1[MySQL Router A]
    C --> D2[MySQL Router B]
    D1 --> E[Metadata cache and routing]
    D2 --> E
    E --> F[Primary]
    E --> G[Secondary 1]
    E --> H[Secondary 2]
~~~

Mỗi tầng có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Không nên kỳ vọng |
|---|---|---|
| JDBC/DataSource | Tạo connection logic, giới hạn số connection được mượn, quản lý vòng đời và timeout phía ứng dụng | Tự biết primary mới nếu URL trỏ thẳng vào một node |
| Application connection pool | Tái sử dụng connection, giới hạn concurrency, thu hồi connection và hỗ trợ kiểm tra sức khỏe | Tự sửa một transaction đã mất kết nối hoặc tự bảo đảm replica đã bắt kịp |
| MySQL Router | Lắng nghe endpoint, chọn destination, chuyển tiếp MySQL protocol, theo dõi metadata topology và hỗ trợ một số chế độ chia sẻ/routing | Thay thế transaction manager, business retry hoặc validation của ứng dụng |
| MySQL Server | Thực thi SQL, transaction, khóa, replication và lưu trữ dữ liệu | Tự chuyển connection đang chạy từ primary cũ sang primary mới mà không làm client nhận lỗi |
| Load balancer/service discovery | Cung cấp địa chỉ ổn định đến một hoặc nhiều Router | Hiểu ngữ nghĩa transaction MySQL nếu chỉ hoạt động ở tầng TCP |

Ví dụ, HikariCP giữ một nhóm connection JDBC đến Router. Router nhận các kết nối đó và chọn node MySQL theo routing service. Khi một server lỗi, các connection hiện tại có thể bị ngắt; pool phải loại connection hỏng và ứng dụng phải mở connection mới qua cùng endpoint Router.

### 2. MySQL Router làm gì?

MySQL Router là middleware nhẹ nằm giữa ứng dụng và MySQL Server. Nó hỗ trợ connection routing, tích hợp với InnoDB Cluster và các topology được hỗ trợ, read/write splitting trong các phiên bản phù hợp, TLS và connection sharing.

Router có thể:

- Cung cấp endpoint ổn định cho ứng dụng.
- Định tuyến connection đến primary hoặc secondary dựa trên metadata cache.
- Chọn server theo routing strategy như first-available hoặc round-robin.
- Theo dõi trạng thái topology của InnoDB Cluster để cập nhật destination.
- Ngắt client khi backend connection bị lỗi và cho phép ứng dụng kết nối lại.
- Với Router 8.4 và cấu hình phù hợp, chia sẻ/tái sử dụng một số server connection nhàn rỗi.
- Trong read/write splitting, phân loại statement và chuyển traffic đến read-write hoặc read-only destination.

Router không phải là một MySQL Server độc lập lưu dữ liệu. Ứng dụng kết nối đến Router nhưng câu SQL vẫn được thực thi trên MySQL backend. Router không thay thế quyền, constraint, transaction, replication hay backup của server.

### 3. Connection routing theo connection

Chế độ routing cơ bản chọn backend khi client tạo kết nối. Router chuyển tiếp các packet MySQL giữa client và server. Trong kiểu routing cơ bản, Router không cần phân tích từng câu SQL để quyết định destination; connection đã chọn được gắn với backend trong suốt phiên.

Một ví dụ routing đơn giản:

~~~ini
[routing:primary_service]
bind_address = 127.0.0.1
bind_port = 7001
destinations = db-primary.example.net:3306
routing_strategy = first-available

[routing:read_service]
bind_address = 127.0.0.1
bind_port = 7002
destinations = db-replica-1.example.net:3306,db-replica-2.example.net:3306
routing_strategy = round-robin
~~~

Đây là cấu hình minh họa cho danh sách destination tĩnh. Trong môi trường InnoDB Cluster, nên dùng metadata cache và cấu hình được tạo bởi quá trình bootstrap để Router hiểu vai trò primary/secondary và topology. Không dùng danh sách IP tĩnh thay cho metadata-aware routing nếu mục tiêu là theo kịp failover của cluster.

Một số routing strategy thường gặp:

| Strategy | Hành vi tổng quát | Trường hợp phù hợp |
|---|---|---|
| first-available | Chọn destination khả dụng đầu tiên; khi lỗi có thể thử destination kế tiếp | Endpoint cần một node ưu tiên |
| round-robin | Phân phối các kết nối mới lần lượt qua destination khả dụng | Chia tải connection giữa các replica |
| round-robin-with-fallback | Ưu tiên nhóm destination theo vai trò; có thể fallback theo cấu hình khi nhóm ưu tiên không có node phù hợp | Read-only routing có fallback được thiết kế |
| next-available | Chuyển sang destination tiếp theo và có thể loại node được đánh dấu unreachable cho đến khi Router khởi động lại | Danh sách destination tĩnh cần hành vi bỏ qua node lỗi |

Strategy áp dụng cho kết nối mới. Đừng hiểu round-robin là Router chia từng câu SELECT trong một connection qua nhiều replica. Nếu muốn phân loại statement đọc/ghi trong một session, cần cấu hình read/write splitting phù hợp.

### 4. Metadata cache và InnoDB Cluster

Khi dùng InnoDB Cluster, MySQL Router có thể được bootstrap từ một thành viên của cluster. Quá trình bootstrap đọc metadata, tạo cấu hình routing và thiết lập tài khoản cần cho Router truy cập metadata. Router duy trì metadata cache để biết thành viên nào đang là primary, secondary hoặc không khả dụng.

Quy trình khái quát:

1. Tạo và kiểm tra InnoDB Cluster bằng MySQL Shell AdminAPI.
2. Tạo tài khoản bootstrap/router với quyền đúng theo hướng dẫn phiên bản.
3. Chạy bootstrap trên host sẽ chạy Router.
4. Kiểm tra file cấu hình được tạo, thư mục runtime, log và keyring.
5. Khởi động Router và xác minh các endpoint được mở.
6. Kết nối qua Router, đọc hostname/port để xác nhận backend thực tế.

Ví dụ lệnh bootstrap trên Linux:

~~~bash
mysqlrouter --bootstrap router_admin@db-seed.example.net:3306 \
  --directory /var/lib/mysqlrouter
~~~

Lệnh minh họa dùng tài khoản và host thay thế. Cung cấp mật khẩu qua prompt hoặc cơ chế bí mật được quản lý; không ghi mật khẩu trực tiếp vào command history. Quyền bootstrap phải theo đúng tài liệu Router tương ứng với phiên bản và topology.

Không chỉnh sửa tùy tiện các phần cấu hình do bootstrap tạo ra. Khi cần thay đổi routing, đọc toàn bộ section liên quan và giữ nguyên metadata cache, dynamic state, keyring cùng đường dẫn được sinh tự động.

### 5. Endpoint read-write và read-only

Một triển khai InnoDB Cluster thường cung cấp endpoint cho:

- Read-write: kết nối đến primary hiện tại.
- Read-only: kết nối đến secondary phù hợp.

Các cổng 6446 và 6447 thường được dùng làm mặc định trong cấu hình bootstrap phổ biến, nhưng có thể thay đổi. Ứng dụng phải lấy port từ cấu hình triển khai thay vì hard-code giả định.

Ví dụ cấu hình được bootstrap sinh ra thường có dạng:

~~~ini
[routing:bootstrap_rw]
bind_address = 127.0.0.1
bind_port = 6446
destinations = metadata-cache://myCluster/?role=PRIMARY
routing_strategy = first-available
protocol = classic

[routing:bootstrap_ro]
bind_address = 127.0.0.1
bind_port = 6447
destinations = metadata-cache://myCluster/?role=SECONDARY
routing_strategy = round-robin-with-fallback
protocol = classic
~~~

Đây là đoạn trích minh họa, không phải file cấu hình đầy đủ. Tên cluster, metadata cache section, credentials và các tùy chọn khác phải khớp với cấu hình do bootstrap tạo.

Ứng dụng có thể dùng hai DataSource:

- DataSource ghi trỏ đến endpoint read-write.
- DataSource đọc báo cáo trỏ đến endpoint read-only.

Chỉ tách pool khi nghiệp vụ và consistency cho phép. Đọc ngay sau ghi, đọc trạng thái thanh toán, kiểm tra tồn kho hoặc xác nhận một transaction vừa commit thường cần primary để tránh đọc dữ liệu replica chưa áp dụng.

### 6. Read/write splitting trong MySQL Router 8.4

MySQL Router 8.4 có chế độ read/write splitting theo statement. Chế độ này khác với việc chọn một endpoint read-only hoặc read-write cho toàn bộ connection. Trong một session, Router có thể sử dụng read-write destination cho statement ghi và read-only destination cho statement đọc.

Để bật read/write splitting, cấu hình Router cần các điều kiện chính:

- access_mode được đặt là auto.
- connection_sharing được bật.
- protocol là classic.
- destinations dùng metadata cache với role PRIMARY_AND_SECONDARY.

Đoạn cấu hình minh họa:

~~~ini
[routing:read_write_split]
bind_address = 127.0.0.1
bind_port = 6450
destinations = metadata-cache://myCluster/?role=PRIMARY_AND_SECONDARY
routing_strategy = round-robin
protocol = classic
access_mode = auto
connection_sharing = 1
~~~

Các thiết lập này cần được kết hợp với section metadata cache và cấu hình connection pool phù hợp. Hãy kiểm tra phiên bản Router đang cài; không áp dụng đoạn cấu hình 8.4 vào phiên bản cũ nếu tính năng chưa được hỗ trợ.

Có thể đặt access mode theo session:

~~~sql
ROUTER SET access_mode = 'auto';
ROUTER SET wait_for_my_writes = 1;
~~~

Các giá trị access_mode:

| Giá trị | Ý nghĩa |
|---|---|
| read_write | Toàn bộ traffic session được gửi đến read-write server |
| read_only | Toàn bộ traffic session được gửi đến read-only server |
| auto | Router phân loại statement và chọn read-only hoặc read-write destination |

Một session có thể sử dụng cả hai destination. Vì vậy, không nên suy luận rằng một connection JDBC đến endpoint read/write split chỉ có duy nhất một backend connection trong toàn bộ vòng đời.

### 7. Router phân loại statement như thế nào?

Router 8.4 có danh sách statement được xem là read-only hoặc read-write. Đây là bộ phân loại theo cú pháp và loại statement được hỗ trợ, không phải phân tích đầy đủ ý nghĩa nghiệp vụ của mọi stored procedure hoặc function.

Ví dụ một số statement read-only:

- SELECT.
- DO, VALUES, TABLE.
- WITH không theo sau bởi UPDATE hoặc DELETE.
- EXPLAIN, DESCRIBE, DESC trong các trường hợp được hỗ trợ.
- HELP, USE, CHECKSUM và parenthesized query expression.

Một statement bắt đầu như SELECT vẫn có thể cần read-write server nếu chứa:

- GET_LOCK().
- FOR UPDATE hoặc FOR SHARE.
- LOCK IN SHARE MODE.
- Function hoặc cú pháp có thể ghi dữ liệu.

Một số statement được xem là read-write:

- DDL và các thao tác thay đổi schema.
- INSERT, UPDATE, DELETE, REPLACE, CALL và các dạng load/import được hỗ trợ.
- START TRANSACTION, COMMIT, ROLLBACK, SAVEPOINT và XA.
- Một số lệnh quản trị, account management, SET SESSION và SHOW CREATE.

Các statement không thuộc hai nhóm phân loại có thể không được hỗ trợ khi access_mode=auto. Đặc biệt, CALL được định tuyến read-write kể cả khi procedure chỉ đọc. Một SELECT gọi function có side effect cũng có thể bị chuyển đến read-write hoặc thất bại nếu cố định read-only.

Nếu cần đảm bảo một truy vấn chạy trên primary, đặt session ở read_write hoặc dùng endpoint read-write riêng. Không dựa vào từ khóa SELECT để suy luận chắc chắn rằng câu lệnh không ghi.

### 8. Read-after-write và replication lag

Một replica có thể chưa áp dụng transaction vừa commit trên primary. Nếu ứng dụng ghi qua primary rồi lập tức đọc qua secondary, kết quả có thể cũ hơn.

Có ba cách xử lý phổ biến:

1. Gửi cả write và read cần tính nhất quán đến read-write endpoint.
2. Giữ một transaction/session ở chế độ read_write cho toàn bộ luồng nghiệp vụ.
3. Dùng wait_for_my_writes của Router 8.4 khi read/write splitting được cấu hình và hành vi này phù hợp.

Ví dụ:

~~~sql
ROUTER SET access_mode = 'auto';
ROUTER SET wait_for_my_writes = 1;
ROUTER SET wait_for_my_writes_timeout = 2;
~~~

Khi bật wait_for_my_writes, Router có thể chờ read-only destination áp dụng transaction cuối cùng do session ghi. Nếu quá timeout, Router có thể fallback truy vấn sang read-write destination theo cấu hình. Trong Router 8.4, wait_for_my_writes_timeout mặc định là 1 giây; giới hạn tối đa và hành vi cần được kiểm tra theo phiên bản. Đo latency thực tế trước khi thay đổi timeout.

Đây không phải cam kết mọi read đều có consistency tuyến tính trong mọi tình huống. Kiểm thử với replication mode, topology, lỗi node và tải thật. Với nghiệp vụ tài chính hoặc tồn kho, chọn primary nếu không thể chấp nhận stale read.

### 9. Application connection pool và Router connection sharing

Đây là hai pool ở hai ranh giới khác nhau.

| Thuộc tính | Application pool | Router connection sharing |
|---|---|---|
| Vị trí | Trong process ứng dụng hoặc application server | Bên trong MySQL Router |
| Đối tượng được quản lý | JDBC connection logic/physical client connection đến Router | Backend connection từ Router đến MySQL Server |
| Mục tiêu | Giảm chi phí mở kết nối, giới hạn số connection ứng dụng, tái sử dụng connection | Giảm số server connection nhàn rỗi và cho phép server connection được tái sử dụng giữa client session đủ điều kiện |
| API ứng dụng nhìn thấy | DataSource.getConnection()/Connection.close() | Không có API JDBC riêng; được cấu hình ở Router |
| Phạm vi trạng thái | Transaction và session state của JDBC connection | Trạng thái protocol/session mà Router theo dõi và khả năng share backend |
| Điều kiện giới hạn | Pool size, timeout, validation, leak detection | Classic protocol, trạng thái session, transaction, prepared statement và các feature được hỗ trợ |

Trong Router 8.4, connection sharing bị tắt mặc định theo cấu hình option. Khi bật, Router có thể đưa backend connection nhàn rỗi vào pool để client session khác sử dụng. Router theo dõi statement và SQL state để giữ trạng thái session; nếu không thể chia sẻ an toàn, backend connection không được đưa vào pool.

Connection sharing không đồng nghĩa mỗi câu SQL tùy ý có thể chạy trên bất kỳ server session nào. Router phải bảo toàn trạng thái của session và có danh sách feature ngăn việc đưa connection về pool. Cần kiểm thử các lệnh mà ứng dụng đang dùng trước khi bật.

Các option điều khiển connection sharing trong Router 8.4:

| Option | Mặc định được tài liệu hóa | Vai trò |
|---|---:|---|
| connection_sharing | 0 | Bật/tắt khả năng chia sẻ backend connection |
| connection_sharing_delay | 1 giây | Thời gian chờ trước khi backend connection nhàn rỗi đủ điều kiện được đưa vào pool |
| max_idle_server_connections | 0 | Số backend connection nhàn rỗi tối đa được giữ lại để tái sử dụng |
| idle_timeout | 5 giây | Thời gian giữ một backend connection nhàn rỗi trong pool trước khi đóng |

Các giá trị và section cấu hình có thể thay đổi theo phiên bản; bootstrap có thể sinh cấu hình khác với mặc định chung. Ví dụ read/write split được bootstrap có thể đặt max_idle_server_connections lớn hơn 0. Xem cấu hình thực tế và đo số backend connection trước khi tinh chỉnh.

Với connection pool phía ứng dụng, vòng đời có thể diễn ra như sau:

1. HikariCP cấp một JDBC connection; TCP client-to-Router được mở.
2. Router gắn session với backend MySQL và chuyển tiếp statement.
3. Code gọi Connection.close(); HikariCP thu hồi connection logic nhưng thường vẫn giữ TCP connection đến Router ở trạng thái idle.
4. Nếu connection sharing được bật, sau connection_sharing_delay Router có thể đưa backend connection nhàn rỗi vào pool nếu session không bị pin bởi transaction hoặc feature không hỗ trợ.
5. Khi ứng dụng dùng lại JDBC connection và gửi statement, Router gắn session với backend connection phù hợp, đồng thời bảo toàn trạng thái mà nó theo dõi.

Do đó, close của HikariCP không đồng nghĩa TCP client connection đã đóng. Router sharing có thể tái sử dụng backend dù application pool vẫn giữ client connection; tuy nhiên, trạng thái như temporary table hoặc prepared statement có thể khiến backend không được chia sẻ cho đến khi client reset/đóng session.

### 10. Giới hạn của connection sharing

Trong Router 8.4, connection sharing chỉ hỗ trợ classic protocol. Nó không được hỗ trợ trong một số cấu hình TLS như PASSTHROUGH hoặc tổ hợp server-ssl-mode=AS_CLIENT với client-ssl-mode=PREFERRED. Đọc đúng ma trận tương thích của phiên bản Router đang chạy.

Các câu lệnh/phần trạng thái sau có thể ngăn backend connection được đưa vào pool chia sẻ cho đến khi client đóng hoặc reset connection:

- User variables.
- Temporary tables.
- Prepared statements.
- GET_LOCK() và các named lock liên quan.
- SQL_CALC_FOUND_ROWS.
- LOCK TABLES.
- Transaction đang mở.

Một số statement như GET DIAGNOSTICS và LAST_INSERT_ID() không được hỗ trợ trong connection sharing ngoài transaction theo giới hạn được tài liệu hóa.

Ý nghĩa vận hành:

- Không giả định một temporary table tồn tại an toàn sau khi backend connection được share.
- Không dựa vào user variable để truyền dữ liệu giữa các statement nếu session có thể được chia sẻ.
- Đóng/reset prepared statement theo vòng đời JDBC.
- Giữ transaction ngắn và commit/rollback trước khi connection idle.
- Dùng session state theo cách Router hỗ trợ và kiểm thử trên phiên bản thực tế.

Nếu ứng dụng thường xuyên dùng temporary table, user variables hoặc prepared statement theo cách làm connection bị pin, connection sharing có thể giảm lợi ích. Đo tỷ lệ backend connection thực sự được tái sử dụng thay vì chỉ bật option rồi giả định số connection sẽ giảm.

### 11. Phối hợp với HikariCP hoặc pool JDBC

Ứng dụng Java nên dùng DataSource/pool có vòng đời dài. Ví dụ cấu hình minh họa:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:mysql://router.service.internal:6446/appdb");
config.setUsername("app_user");
config.setPassword(secret);
config.setMaximumPoolSize(20);
config.setConnectionTimeout(3000);
config.setValidationTimeout(1000);
config.setMaxLifetime(1500000);
config.setKeepaliveTime(120000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Các con số trên chỉ để minh họa. Chọn maxLifetime ngắn hơn giới hạn tuổi connection do Router, load balancer, firewall hoặc MySQL áp dụng. Keepalive phải phù hợp với maxLifetime và yêu cầu của phiên bản pool. Không copy các giá trị này vào production mà chưa đo.

Ứng dụng phải đóng ResultSet, Statement và Connection đúng cách:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT order_id, total_amount FROM orders WHERE order_id = ?")) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
~~~

Trong pool, Connection.close() thường trả connection logic về pool; socket đến Router có thể vẫn mở. Vì vậy, Router vẫn có thể nhìn thấy client connection đang tồn tại dù request đã kết thúc. Nếu Router connection sharing được bật, nó có thể quản lý backend connection nhàn rỗi theo quy tắc sharing của nó.

Luôn kết thúc transaction trước khi trả connection. Đóng connection trong khi transaction chưa commit/rollback không phải chiến lược cleanup. Pool có thể rollback khi thu hồi, nhưng ứng dụng phải sở hữu quyết định transaction.

### 12. Tách pool đọc và ghi

Nếu dùng endpoint riêng, tạo hai DataSource có cấu hình độc lập:

~~~java
HikariConfig writeConfig = new HikariConfig();
writeConfig.setJdbcUrl("jdbc:mysql://router.service.internal:6446/appdb");
writeConfig.setUsername("app_user");
writeConfig.setPassword(secret);
writeConfig.setMaximumPoolSize(20);

HikariConfig readConfig = new HikariConfig();
readConfig.setJdbcUrl("jdbc:mysql://router.service.internal:6447/appdb");
readConfig.setUsername("app_read_user");
readConfig.setPassword(readSecret);
readConfig.setMaximumPoolSize(30);
~~~

Ví dụ này minh họa endpoint phổ biến read-write và read-only. Tên port, credentials và pool size phụ thuộc triển khai. Có thể dùng cùng tài khoản nếu quyền được thiết kế phù hợp, nhưng tách user đọc/ghi giúp áp dụng least privilege.

Không định tuyến read/write chỉ bằng tên method repository như get/find/save mà không kiểm soát transaction. Một method tên find có thể gọi stored function có side effect; một method update có thể cần đọc dữ liệu nhất quán trên primary. Tạo chính sách routing ở tầng service/repository có hiểu biết nghiệp vụ và test bằng backend thực tế.

Nếu dùng một endpoint read/write split của Router 8.4, cần kiểm thử cách driver, pool và Router phối hợp với session settings. Các tùy chọn ROUTER SET là session state; khi connection được tái sử dụng, ứng dụng phải biết trạng thái nào được reset và cách thiết lập lại cho mỗi đơn vị công việc.

Router 8.4 đặt lại các tùy chọn session của Router về giá trị ban đầu khi client gửi change_user hoặc reset_connection. Không giả định mọi JDBC pool đều gửi các lệnh này ở mỗi lần trả connection; kiểm tra hành vi của pool/driver đang dùng và thiết lập access_mode theo từng luồng nghiệp vụ một cách rõ ràng.

### 13. Ngân sách connection qua nhiều tầng

Đặt maximum pool size cho từng process mà không tính số replica ứng dụng có thể vượt max_connections của MySQL.

Ước lượng số client connection đến Router:

~~~text
Application client connections
  = sum(application instances x pool maximum size)
    + background workers
    + migration jobs
    + admin/monitoring clients
~~~

Ước lượng backend connection trên mỗi MySQL node:

~~~text
Backend connections on node
  = active Router backend sessions
    + idle Router server connections
    + direct application/admin connections
    + replication and system sessions
~~~

Khi connection sharing có hiệu quả, số backend connection có thể thấp hơn số client connection. Nhưng các session đang transaction, dùng temporary table, user variable hoặc prepared statement có thể không được share. Vì vậy, không lập ngân sách theo tỷ lệ giảm giả định.

Các giới hạn cần phân biệt:

| Giới hạn | Áp dụng ở đâu | Ý nghĩa |
|---|---|---|
| Pool maximumPoolSize | Mỗi DataSource trong mỗi process | Số connection logic tối đa ứng dụng có thể mượn |
| Router max_total_connections | Toàn bộ Router instance | Tổng số client connection Router chấp nhận |
| Router max_connections | Một routing destination/route theo cấu hình | Giới hạn connection được gán cho destination |
| Router max_idle_server_connections | Connection pool phía server của Router | Số backend connection nhàn rỗi giữ lại để tái sử dụng |
| MySQL max_connections | Mỗi MySQL Server | Tổng số client connection server cho phép |
| MySQL max_user_connections | Mỗi tài khoản MySQL | Giới hạn connection theo user nếu được cấu hình |

Giữ headroom cho DBA, health check, backup, migration, replication và xử lý sự cố. Một node không nên hoạt động sát max_connections trong điều kiện bình thường.

### 14. Router là một tầng cần HA

Nếu chỉ có một Router, Router trở thành điểm lỗi đơn. Triển khai production thường chạy nhiều Router instance ở các host/failure domain khác nhau và cung cấp một service address bằng load balancer, DNS/service discovery hoặc cơ chế mạng phù hợp.

Thiết kế cần trả lời:

- Bao nhiêu Router instance cần thiết để chịu lỗi một host?
- Load balancer kiểm tra Router bằng TCP hay endpoint health chuyên dụng?
- Ứng dụng pool kết nối đến một service address hay danh sách Router?
- Khi Router restart, connection hiện tại được xử lý thế nào?
- Cấu hình và metadata cache được cập nhật đồng bộ ra sao?
- Router logs, REST API và cảnh báo được thu thập ở đâu?

Không để health check chỉ kiểm tra process còn sống. Router có thể chạy nhưng không kết nối được metadata server hoặc không có backend phù hợp. Health check nên phản ánh trạng thái cần thiết cho luồng ứng dụng, đồng thời tránh tạo tải lớn bằng cách mở connection mới liên tục.

### 15. Failover và reconnect

Router hỗ trợ định tuyến connection mới đến server khả dụng. Khi backend connection hiện tại bị ngắt, Router có thể trả connection error cho client. Ứng dụng phải retry việc tạo connection; Router sẽ chọn backend mới theo topology và routing strategy.

Không giả định Router tự chuyển một session đang chạy sang primary mới mà không làm ứng dụng nhận lỗi. Connection đang mở gắn với backend cũ; transaction chưa hoàn tất có thể rollback hoặc có kết quả không xác định nếu mất kết nối đúng lúc commit.

Quy trình reconnect ở ứng dụng:

1. Bắt lỗi connection-fatal từ driver.
2. Đánh dấu connection không còn dùng được và trả/loại bỏ theo pool implementation.
3. Mượn connection mới từ pool, qua Router endpoint.
4. Nếu thao tác có thể retry an toàn, chạy lại toàn bộ đơn vị công việc với backoff và giới hạn số lần.
5. Nếu lỗi xảy ra trong lúc COMMIT, đối soát kết quả bằng business key/idempotency key trước khi retry.
6. Ghi log correlation ID, SQLState, vendor error code và số lần reconnect.

Không retry vô hạn hoặc retry mọi SQLException. Lỗi duplicate key, validation hoặc quyền thường không được sửa bằng reconnect. Với thao tác ghi, idempotency key giúp tránh tạo hai giao dịch khi client không biết commit đã thành công hay chưa.

### 16. TLS và ranh giới bảo mật

Khi có Router, đường truyền có ít nhất hai chặng:

1. Ứng dụng đến Router.
2. Router đến MySQL Server.

Thiết lập TLS cho chặng client-router không tự động chứng minh chặng router-server cũng được mã hóa và xác minh certificate. Cấu hình client_ssl_mode và server_ssl_mode theo chính sách bảo mật; dùng CA/certificate phù hợp và xác minh identity khi yêu cầu.

Không dùng PASSTHROUGH nếu cần Router giải mã/kiểm tra các tính năng yêu cầu protocol termination hoặc connection sharing. Một số tổ hợp TLS mode không tương thích với connection sharing; kiểm tra ma trận của phiên bản Router.

Các nguyên tắc:

- Bind Router vào địa chỉ mạng nội bộ hoặc localhost khi kiến trúc cho phép.
- Chỉ mở port Router cho application subnet cần truy cập.
- Dùng tài khoản ứng dụng có quyền tối thiểu.
- Tách tài khoản metadata/bootstrap và tài khoản ứng dụng.
- Bảo vệ keyring, file cấu hình, log và secret.
- Không ghi password trong JDBC URL hoặc shell history.
- Kiểm thử certificate expiry, hostname verification và rotate certificate.

### 17. Quan sát Router và backend

Khi ứng dụng kết nối qua Router, truy vấn thông tin backend để xác minh routing:

~~~sql
SELECT
  @@hostname AS backend_host,
  @@port AS backend_port,
  @@server_uuid AS server_uuid,
  @@read_only AS read_only,
  @@super_read_only AS super_read_only;
~~~

Đối chiếu kết quả trên endpoint read-write và read-only. Nếu topology thay đổi, tạo connection mới và kiểm tra lại backend.

Các tín hiệu cần theo dõi:

| Tầng | Metric/log | Dấu hiệu cần điều tra |
|---|---|---|
| Ứng dụng pool | active, idle, pending, acquisition latency, timeout, leak | Pool cạn, request chờ lấy connection |
| Router | client connections, backend connections, route errors, connect retries, logs | Backend unavailable, metadata cache lỗi, quá giới hạn connection |
| MySQL | Threads_connected, Threads_running, max_used_connections, connection errors | Connection tăng bất thường hoặc server chạm giới hạn |
| Replication | applier status, lag, queue, transaction apply time | Read-after-write chậm hoặc replica không theo kịp |
| Network | TCP reset, timeout, packet loss, TLS errors | Connection chập chờn giữa app, Router và backend |

Trên MySQL, kiểm tra:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW VARIABLES LIKE 'max_connections';
SHOW PROCESSLIST;
~~~

Kết hợp Router log và REST API nếu đã bật/cấu hình. Bảo vệ endpoint quản trị Router và không phơi bày nó ra mạng công cộng. Khi debug connection sharing, Router 8.4 có tính năng ROUTER SET TRACE; tính năng này cần cấu hình tương thích và có thể tạo log/trace nhạy cảm, chỉ bật có thời hạn trên môi trường kiểm thử hoặc theo runbook.

### 18. Phân biệt MySQL Router, ProxySQL và TCP load balancer

Các công cụ proxy có phạm vi khác nhau:

| Thành phần | Điểm mạnh | Điều cần kiểm tra |
|---|---|---|
| MySQL Router | Tích hợp metadata InnoDB Cluster, routing theo role, HA connection routing, connection sharing và read/write splitting trong Router 8.4 | Giới hạn statement/session state, protocol, TLS mode và version |
| ProxySQL | Proxy MySQL có query rules, hostgroup, connection pooling/multiplexing và các tính năng quản trị traffic phong phú | Cấu hình rule, transaction/session pinning, compatibility và vận hành riêng |
| TCP load balancer | Cung cấp virtual IP/service endpoint, health check TCP và phân phối kết nối | Không hiểu đầy đủ SQL semantics hoặc metadata MySQL nếu chỉ làm L4 |
| DNS round-robin | Đơn giản để phân phối endpoint | DNS cache, failover delay, health awareness và connection đang mở |

Không chọn proxy chỉ dựa trên số lượng connection có thể nhận. Xác định cần routing theo role, routing theo statement, multiplexing, query rules, caching, TLS termination hay tích hợp InnoDB Cluster. Sau đó test session state, transaction, prepared statement và failover.

### 19. Kiểm thử triển khai

Một kế hoạch kiểm thử cần có cả routing, pool và failure:

1. Kết nối qua read-write endpoint và xác minh backend là primary.
2. Kết nối qua read-only endpoint và xác minh backend có read_only/super_read_only phù hợp.
3. Chạy SELECT, DML, DDL, CALL, SELECT FOR UPDATE và câu có function side effect để xác nhận routing.
4. Kiểm thử transaction nhiều statement để xác nhận không chuyển backend giữa transaction.
5. Ghi trên primary rồi đọc qua read-only; đo replication lag và thử wait_for_my_writes nếu dùng.
6. Bật connection sharing trong staging; thử user variable, temporary table, prepared statement, named lock, transaction và reset connection.
7. Tạo tải với nhiều application instance; đo client connection ở Router và backend connection ở MySQL.
8. Dừng một secondary, kiểm tra Router loại destination và tiếp tục phục vụ connection mới.
9. Thực hiện switchover/failover có kiểm soát; xác minh connection hiện tại lỗi như dự kiến và connection mới đến primary mới.
10. Làm gián đoạn Router instance; xác minh load balancer chuyển sang Router còn khỏe và pool reconnect.
11. Kiểm thử TLS, certificate rotation và quyền tài khoản.
12. Chạy lại test sau khi nâng cấp MySQL Server, Router, Connector/J hoặc connection pool.

Không thực hiện kill primary hoặc gây mất mạng trên production chỉ để thử failover. Dùng staging có topology tương tự và có quy trình khôi phục.

### 20. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng không kết nối được Router | Sai bind address/port, firewall hoặc Router chưa chạy | Kiểm tra service, listener, log và network path |
| Router không tìm thấy primary | Metadata cache không truy cập được hoặc cluster không có primary | Kiểm tra cluster status, metadata account và Router logs |
| Connection mới vào primary cũ | Router chưa cập nhật metadata hoặc ứng dụng còn kết nối trực tiếp | Kiểm tra topology, metadata cache và JDBC URL |
| Connection hiện tại lỗi sau failover | Backend session cũ bị ngắt | Evict connection hỏng, reconnect qua Router và retry an toàn |
| Read query trả dữ liệu cũ | Replica lag hoặc read/write splitting | Đọc primary hoặc dùng wait_for_my_writes theo chính sách |
| SELECT FOR UPDATE thất bại trên replica | Statement cần read-write server | Dùng read-write endpoint/session |
| Số connection trên MySQL vẫn cao | Pool app giữ client connection, Router sharing không bật hoặc session bị pin | Đo từng tầng và kiểm tra feature ngăn sharing |
| Router báo connection sharing không hoạt động | Protocol/TLS mode không hỗ trợ hoặc session state ngăn share | Kiểm tra classic protocol, TLS options và statements đã chạy |
| Router chạm max_total_connections | Quá nhiều app pool/client hoặc leak ở ứng dụng | Tính tổng pool size, giới hạn concurrency và mở rộng Router |
| MySQL chạm max_connections | Backend session vượt ngân sách | Đo Router backend/idle pool, hạ pool size hợp lý hoặc tăng capacity có đánh giá |
| Request chờ pool lâu | App pool hết connection do truy vấn chậm hoặc transaction dài | Tối ưu truy vấn, giảm hold time và kiểm tra pool metrics |
| TLS handshake lỗi | Certificate, CA, hostname hoặc mode giữa hai chặng không khớp | Kiểm tra TLS client-router và router-server riêng |
| Stored procedure không được chia read/write như mong đợi | CALL được phân loại read-write | Dùng endpoint/mode phù hợp và không giả định Router đọc thân procedure |

### 21. Checklist thiết kế production

- [ ] Đã xác định topology: standalone, InnoDB Cluster hay replica topology khác.
- [ ] Router được bootstrap và tương thích với phiên bản MySQL Server.
- [ ] Có nhiều Router instance hoặc một kế hoạch HA cho Router.
- [ ] Ứng dụng kết nối đến Router service, không phụ thuộc IP primary cố định.
- [ ] Read-write/read-only endpoint được phân biệt và kiểm thử.
- [ ] Read/write splitting chỉ bật khi Router version, classic protocol và connection sharing đáp ứng điều kiện.
- [ ] Đã xác định session state nào ngăn connection sharing.
- [ ] Application pool size được tính theo số process/replica và số DataSource.
- [ ] Router max_total_connections, route max_connections và backend idle pool được tính riêng.
- [ ] MySQL max_connections còn headroom cho replication, DBA, backup và vận hành.
- [ ] Transaction ngắn; ResultSet/Statement/Connection được đóng; session state được reset.
- [ ] Retry có giới hạn, backoff và idempotency cho thao tác ghi.
- [ ] Read-after-write có chính sách nhất quán rõ ràng.
- [ ] TLS được cấu hình riêng cho client-router và router-server.
- [ ] Router logs, REST API, pool metrics và MySQL metrics được giám sát.
- [ ] Đã thử failover, Router restart, backend outage và pool reconnect trên staging.
- [ ] Runbook chỉ rõ cách xác minh backend thực tế và khôi phục sau lỗi.

### 22. Bài tập thực hành

Một ứng dụng Java có 8 replica, mỗi replica chạy hai HikariDataSource: write pool tối đa 20 connection và read pool tối đa 30 connection. Cả hai kết nối đến hai endpoint Router. InnoDB Cluster có một primary và hai secondary. Sau khi bật Router 8.4 connection sharing và read/write splitting, số connection trên primary vẫn cao; một số request đọc ngay sau khi ghi nhận được dữ liệu cũ. Khi primary failover, một số request đang chạy bị Communications link failure.

1. Tính số client connection tối đa mà các application pool có thể mở đến Router.
2. Giải thích vì sao số backend connection không nhất thiết bằng số client connection.
3. Nêu các session feature có thể ngăn Router đưa backend connection vào connection pool.
4. Vì sao một request đọc ngay sau ghi có thể thấy replica chưa cập nhật?
5. Thiết kế chính sách read_write, read_only và wait_for_my_writes cho các luồng nghiệp vụ khác nhau.
6. Những loại lỗi nào có thể retry và vì sao COMMIT bị mất kết nối cần idempotency key?
7. Bạn sẽ theo dõi metric nào ở HikariCP, Router và MySQL để tìm nguyên nhân connection cao?
8. Lập test plan cho primary failover, Router outage và TLS.

### 23. Nguyên tắc vận hành

Hãy xem application pool, MySQL Router và MySQL Server là các tầng có ngân sách connection và trạng thái riêng. Application pool giảm chi phí kết nối từ process; Router định tuyến theo topology và có thể chia sẻ backend connection khi phiên bản/cấu hình/session cho phép; MySQL Server vẫn chịu giới hạn connection và concurrency cuối cùng. Chọn read-write/read-only theo yêu cầu consistency, giữ transaction ngắn, kiểm soát session state, cấu hình TLS cho cả hai chặng và xây dựng reconnect/idempotency ở ứng dụng. Đo connection ở từng tầng trước khi thay đổi pool size hoặc bật thêm cơ chế sharing.

### Tài liệu tham khảo

- MySQL Router 8.4 — Connection Routing: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-general-features-connection-routing.html
- MySQL Router 8.4 — Connection Sharing and Reuse: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-general-features-connection-sharing.html
- MySQL Router 8.4 — Read/Write Splitting Configuration: https://dev.mysql.com/doc/mysql-router/8.4/en/router-read-write-splitting-configuration.html
- MySQL Router 8.4 — Read/Write Splitting Statements: https://dev.mysql.com/doc/mysql-router/8.4/en/router-read-write-splitting-statements.html
- MySQL Router 8.4 — Application Considerations: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-general-using-developing.html
- MySQL Router 8.4 — Configuration File Options: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-conf-options.html
