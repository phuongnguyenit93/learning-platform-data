# Khởi tạo/reset session state, SQL mode và timezone khi tái sử dụng kết nối

Một kết nối vật lý tới MySQL đại diện cho một session có trạng thái riêng. Khi ứng dụng dùng connection pool, nhiều request có thể lần lượt mượn cùng một kết nối vật lý. Các thiết lập như `sql_mode`, `time_zone`, isolation level, user variable, temporary table và một số session setting khác có thể còn tồn tại sau khi request trước trả connection về pool. Nếu không khởi tạo và reset có chủ đích, request sau có thể chạy với môi trường SQL khác dự kiến, gây lỗi dữ liệu, sai thời gian hoặc rò rỉ trạng thái giữa các request.

Bài học này thuộc chương **Spring Boot và JPA** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, ứng dụng Java cần quản lý đúng vòng đời session khi kết nối được tái sử dụng. Trọng tâm là phân biệt cấu hình server, trạng thái session và cấu hình ORM; hiểu thời điểm HikariCP chạy init SQL; đồng thời chọn cách reset phù hợp trước khi connection phục vụ request tiếp theo.

## 1. Connection pool tái sử dụng session như thế nào?

Khi Spring Boot dùng HikariCP, ứng dụng thường gọi `DataSource.getConnection()`. Pool trả về một logical connection gắn với một physical connection đang mở tới MySQL. Khi ứng dụng gọi `Connection.close()`, logical connection được trả lại pool; TCP connection thường vẫn mở để request khác sử dụng.

~~~text
Request A
   |
   | borrow
   v
HikariCP ---- physical connection #12 ---- MySQL session #12
   |                                          |
   | Request A: SET SESSION time_zone ...    |
   | Request A: query / transaction           |
   |                                          |
   | close logical connection                 |
   v                                          |
Pool giữ physical connection ----------------+
   |
   | borrow lại cùng connection
   v
Request B có thể nhận session #12
   |
   | session variables vẫn còn nếu chưa reset
   v
Request B
~~~

Pool có thể quản lý và khôi phục một số trạng thái JDBC mà nó theo dõi, ví dụ auto-commit, read-only, isolation level, catalog hoặc schema tùy pool. Tuy nhiên, không nên giả định pool tự hiểu và khôi phục mọi câu lệnh SQL `SET SESSION` mà ứng dụng đã chạy.

Ví dụ, request A thực hiện:

~~~sql
SET SESSION time_zone = '+07:00';
SET SESSION sql_mode = '';
SET @tenant_id = 42;
~~~

Sau đó request A gọi `close()`. Nếu pool giữ lại physical connection và không reset các biến SQL này, request B có thể nhận đúng session đó với timezone, sql_mode và user variable đã bị thay đổi.

**Nguyên tắc:** trạng thái MySQL gắn với physical session. Việc đóng logical connection của pool không đồng nghĩa MySQL session đã bị đóng hoặc reset.

## 2. Phân biệt GLOBAL, SESSION và cấu hình theo transaction

MySQL có nhiều phạm vi cấu hình:

| Phạm vi | Tác động | Ví dụ |
|---|---|---|
| GLOBAL | Giá trị mặc định cho các session mới; không tự thay đổi session đang mở | `SET GLOBAL sql_mode = ...` |
| SESSION | Chỉ thay đổi session hiện tại | `SET SESSION time_zone = '+00:00'` |
| Transaction | Một số thiết lập chỉ áp dụng cho transaction kế tiếp | `SET TRANSACTION ISOLATION LEVEL READ COMMITTED` |
| Server configuration | Thiết lập được nạp khi server khởi động; có thể quản lý bằng option file hoặc cơ chế persist | `sql_mode`, timezone mặc định |

Kiểm tra cả giá trị global và session:

~~~sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode,
  @@GLOBAL.time_zone AS global_time_zone,
  @@SESSION.time_zone AS session_time_zone,
  @@SESSION.autocommit AS session_autocommit,
  @@SESSION.transaction_isolation AS session_isolation;
~~~

`SET GLOBAL` thay đổi giá trị mặc định cho kết nối mới, nhưng các session hiện hữu tiếp tục giữ giá trị session của chúng. Vì vậy, đổi global trong lúc ứng dụng đang chạy không đảm bảo toàn bộ connection pool lập tức dùng cấu hình mới.

Với hệ thống cần cấu hình ổn định, nên định nghĩa giá trị global trong cấu hình server hoặc dùng cơ chế persist phù hợp phiên bản. Ví dụ MySQL 8.0 hỗ trợ `SET PERSIST` cho các biến cho phép persist. Sau đó, các session cần được tạo mới hoặc được cập nhật/reset theo quy trình rõ ràng.

Không dùng `SET GLOBAL` cho từng request. Một request không nên thay đổi cấu hình mặc định của mọi kết nối mới trong hệ thống.

## 3. Những loại session state cần quản lý

Một session MySQL có thể giữ nhiều loại trạng thái:

| Trạng thái | Ví dụ | Rủi ro khi connection được tái sử dụng |
|---|---|---|
| System variable cấp SESSION | `sql_mode`, `time_zone`, `group_concat_max_len` | Câu SQL của request sau có thể chạy với quy tắc khác |
| Transaction setting | `autocommit`, isolation level | Thay đổi ranh giới commit hoặc mức nhìn thấy dữ liệu |
| User variable | `@tenant_id`, `@batch_id` | Request sau có thể đọc nhầm giá trị của request trước |
| Temporary table | `CREATE TEMPORARY TABLE ...` | Bảng tạm có thể còn tồn tại trong session |
| Named lock | `GET_LOCK()` | Khóa có thể tiếp tục được giữ sau khi request kết thúc |
| Prepared statement phía server | Statement được tạo bằng SQL `PREPARE` | Tốn tài nguyên hoặc xung đột tên nếu không giải phóng |
| Transaction đang mở | DML chưa commit/rollback | Giữ khóa, undo và làm request khác bị ảnh hưởng |
| Charset/collation session | `SET NAMES`, `character_set_results` | So sánh hoặc truyền dữ liệu có thể khác dự kiến |
| Foreign/unique checks | `foreign_key_checks`, `unique_checks` | Có thể làm mất lớp kiểm tra dữ liệu nếu không bật lại |

Không phải mọi trạng thái đều được reset bởi một lệnh SQL đơn giản. Cần biết ứng dụng đang thay đổi những gì và chọn một chính sách quản lý có thể kiểm chứng.

## 4. SQL mode: bảo đảm quy tắc thực thi nhất quán

`sql_mode` điều khiển cách MySQL xử lý nhiều trường hợp như dữ liệu ngoài miền, ngày không hợp lệ, phép chia cho 0, GROUP BY và một số cú pháp tương thích.

Kiểm tra giá trị:

~~~sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
~~~

Một session có thể bị thay đổi bởi:

~~~sql
SET SESSION sql_mode = '';
~~~

Câu lệnh này làm session hiện tại dùng tập SQL mode rỗng. Với một connection pool, nếu request không khôi phục trạng thái, request sau có thể không còn strict mode hoặc các quy tắc mà ứng dụng kỳ vọng.

Để trả session về giá trị global hiện tại:

~~~sql
SET SESSION sql_mode = DEFAULT;
~~~

`DEFAULT` ở đây lấy giá trị mặc định từ GLOBAL cho session. Cần bảo đảm global sql_mode đã được cấu hình đúng; reset về một global value sai vẫn tạo ra session sai.

### Chọn SQL mode có chủ đích

Không sao chép một chuỗi mode từ môi trường khác rồi ghi đè toàn bộ cấu hình. Trước khi đặt giá trị, ghi nhận mode hiện tại và xác định các mode cần duy trì, ví dụ:

- `STRICT_TRANS_TABLES`: từ chối hoặc báo lỗi cho nhiều trường hợp dữ liệu không hợp lệ thay vì âm thầm ép kiểu.
- `ONLY_FULL_GROUP_BY`: kiểm tra các cột trong SELECT khi dùng GROUP BY.
- `ERROR_FOR_DIVISION_BY_ZERO`: kiểm soát phép chia cho 0 theo chế độ đã cấu hình.
- `NO_ENGINE_SUBSTITUTION`: không âm thầm thay storage engine khi engine yêu cầu không có sẵn.

Danh sách và mặc định có thể khác theo phiên bản MySQL. Hãy kiểm tra tài liệu phiên bản mục tiêu, cấu hình global và test ứng dụng trước khi thay đổi. Không tắt strict mode chỉ để một batch import lỗi tiếp tục chạy; hãy xử lý dữ liệu sai ở nguồn.

### Cấu hình ở server hay ở session?

Nếu tất cả ứng dụng cần cùng SQL mode, đặt ở cấp server để mọi session mới có một mặc định thống nhất. Nếu một ứng dụng có yêu cầu khác, có thể đặt SESSION khi khởi tạo connection hoặc trước transaction, nhưng phải bảo đảm request khác không nhận session ở trạng thái khác.

Khi thay đổi global sql_mode, session đang mở trong pool vẫn có thể giữ mode cũ. Cần drain/evict connection hoặc chủ động reset session theo kế hoạch triển khai.

## 5. Timezone: phân biệt server, session và JVM

Timezone có ít nhất ba lớp độc lập:

1. **MySQL server timezone:** giá trị `@@GLOBAL.time_zone`; `SYSTEM` có nghĩa MySQL sử dụng timezone hệ thống.
2. **MySQL session timezone:** giá trị `@@SESSION.time_zone`; ảnh hưởng các biểu thức thời gian và chuyển đổi TIMESTAMP trong session.
3. **JVM/Hibernate timezone:** timezone Java dùng khi chuyển đổi và bind/extract giá trị thời gian qua JDBC.

Kiểm tra:

~~~sql
SELECT
  @@GLOBAL.time_zone AS global_time_zone,
  @@SESSION.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone,
  NOW() AS session_now,
  UTC_TIMESTAMP() AS utc_now;
~~~

Đặt session timezone về UTC bằng offset cố định:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

Offset `+00:00` không phụ thuộc timezone tables của MySQL. Nếu đặt tên timezone như `Asia/Ho_Chi_Minh`, server cần có timezone tables được nạp. Nếu thiếu bảng timezone, MySQL có thể báo lỗi khi dùng tên vùng.

### TIMESTAMP và DATETIME khác nhau

- **TIMESTAMP:** MySQL chuyển đổi giá trị từ timezone session sang UTC khi lưu và từ UTC về timezone session khi đọc. Cùng một giá trị lưu trữ có thể hiển thị khác nhau ở session timezone khác nhau.
- **DATETIME:** lưu giá trị ngày/giờ theo lịch như được cung cấp, không tự chuyển đổi theo timezone session khi lưu/đọc.

Vì vậy, nếu một cột TIMESTAMP được ghi bởi session `+07:00` và đọc bởi session `+00:00`, phần hiển thị giờ có thể khác nhưng nó đại diện cùng một thời điểm. Với DATETIME, giờ được lưu như giá trị lịch; ứng dụng phải tự thống nhất ý nghĩa timezone.

`NOW()` và `CURRENT_TIMESTAMP` phản ánh timezone session. `UTC_TIMESTAMP()` trả về thời gian UTC. Đừng thay thế một hàm bằng hàm kia mà không xem xét ý nghĩa nghiệp vụ.

### Connector/J và Hibernate

Với Connector/J 8.0.23 trở lên, có thể cấu hình timezone kết nối và yêu cầu driver đồng bộ session timezone:

~~~text
jdbc:mysql://db.example.internal:3306/appdb?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
~~~

- `connectionTimeZone=UTC` đặt timezone mà Connector/J dùng cho chuyển đổi thời gian.
- `forceConnectionTimeZoneToSession=true` yêu cầu driver đặt timezone đó cho MySQL session.
- Nếu chỉ đặt `connectionTimeZone` mà không bật force, không nên mặc định rằng `@@SESSION.time_zone` đã đổi theo.

Với Hibernate, có thể cấu hình timezone JDBC:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
~~~

Thiết lập Hibernate điều khiển cách Hibernate bind/extract các giá trị thời gian qua JDBC. Nó không thay thế việc kiểm tra `@@SESSION.time_zone` của MySQL. Hai lớp nên được cấu hình nhất quán khi ứng dụng cần xử lý thời gian theo UTC.

Nếu dùng phiên bản Connector/J cũ, thuộc tính timezone và hành vi có thể khác. Kiểm tra tài liệu đúng phiên bản driver; không dựa vào ví dụ URL của một phiên bản mới cho driver cũ.

## 6. HikariCP: connectionInitSql chạy khi nào?

Spring Boot thường dùng HikariCP khi Hikari có trên classpath và được chọn làm pool. HikariCP có thuộc tính `connectionInitSql`, Spring Boot bind qua `spring.datasource.hikari.connection-init-sql`.

Thuộc tính này chạy SQL sau khi Hikari tạo một physical connection mới, trước khi connection được đưa vào pool. Nó **không phải callback chạy mỗi lần ứng dụng mượn lại connection**.

Ví dụ cấu hình một trạng thái ban đầu:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.example.internal:3306/appdb
    username: app_user
    password: ${DB_PASSWORD}
    hikari:
      connection-init-sql: "SET SESSION time_zone = '+00:00', SESSION sql_mode = DEFAULT"
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
~~~

Ví dụ này thiết lập timezone UTC và lấy SQL mode session từ global mặc định khi physical connection mới được tạo. Mật khẩu lấy từ biến môi trường hoặc secret manager, không ghi trực tiếp vào repository.

Nếu ứng dụng chỉ cần một bộ session defaults thống nhất, đây là cách khởi tạo hữu ích. Tuy nhiên, nếu code sau đó chạy `SET SESSION sql_mode = ''` hoặc đổi timezone trên connection, lần mượn tiếp theo có thể vẫn thấy giá trị đã bị đổi. `connectionInitSql` không chạy lại chỉ vì logical connection được trả về rồi mượn lần nữa.

HikariCP theo dõi và khôi phục một số thuộc tính JDBC mà nó quản lý. Không dựa vào điều đó để kết luận các câu lệnh SQL thay đổi arbitrary MySQL session variables cũng được khôi phục.

## 7. Đặt session defaults trước transaction trong Spring

Nếu một transaction cần chắc chắn có SQL mode và timezone cụ thể, có thể thiết lập chúng trên transaction-bound connection trước khi chạy repository query. `JdbcTemplate` phải dùng cùng DataSource và transaction manager với JPA để thao tác tham gia đúng transaction.

Ví dụ:

~~~java
@Service
public class OrderService {
    private final JdbcTemplate jdbcTemplate;
    private final OrderRepository orderRepository;

    public OrderService(
            JdbcTemplate jdbcTemplate,
            OrderRepository orderRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(CreateOrderRequest request) {
        jdbcTemplate.execute(
            "SET SESSION time_zone = '+00:00'"
        );
        jdbcTemplate.execute(
            "SET SESSION sql_mode = DEFAULT"
        );

        // Chỉ sau khi đặt session defaults mới gọi repository.
        Order order = new Order();
        order.setCustomerId(request.customerId());
        order.setCreatedAt(Instant.now());

        return orderRepository.save(order);
    }
}
~~~

Trong cấu hình này, `JdbcTemplate` và JPA cần chia sẻ cùng DataSource, và transaction manager phải cho phép JDBC access tham gia transaction JPA. Nếu dùng hai DataSource hoặc hai transaction manager khác nhau, lệnh SET có thể chạy trên connection khác với connection mà Hibernate dùng.

Đặt session defaults ở đầu transaction giúp request không phụ thuộc vào giá trị còn sót lại từ lần mượn trước. Tuy nhiên, mọi luồng truy cập database cần tuân thủ cùng chính sách; query chạy ngoài transaction hoặc tác vụ nền cũng phải được xử lý.

Nếu mỗi request cần một giá trị timezone hoặc SQL mode khác nhau, cần thiết kế cơ chế cleanup trước khi trả connection. Không nên để request tự ý đổi session state rồi dựa vào việc request sau sẽ tự sửa.

## 8. Reset state trước khi trả connection về pool

Có ba chiến lược thường dùng:

### Chiến lược A: Giữ session state cố định

Đây là phương án đơn giản nhất. Cấu hình một bộ giá trị thống nhất cho toàn bộ connection pool và không thay đổi chúng theo request. Ví dụ mọi session đều dùng UTC và cùng SQL mode.

- Đặt global defaults tại server.
- Dùng Connector/J hoặc Hikari connection init SQL để xác lập trạng thái ban đầu.
- Không chạy các lệnh SET SESSION tùy tiện trong business code.
- Nếu cần transaction isolation khác, dùng transaction configuration của Spring thay vì tự thay đổi session variable kéo dài.

### Chiến lược B: Khôi phục các biến đã biết

Nếu code có thay đổi một tập nhỏ session variables, hãy khôi phục chúng về giá trị chuẩn trước khi connection được trả về pool:

~~~sql
SET SESSION sql_mode = DEFAULT;
SET SESSION time_zone = '+00:00';
SET SESSION foreign_key_checks = DEFAULT;
SET SESSION unique_checks = DEFAULT;
~~~

Với user variables, đặt lại rõ ràng:

~~~sql
SET @tenant_id = NULL;
SET @request_id = NULL;
~~~

Temporary table phải được drop nếu còn tồn tại; named lock cần được release; transaction phải commit hoặc rollback. Lệnh reset phải chạy trên đúng physical session trước khi connection được trả cho pool.

Không chỉ reset `sql_mode` và `time_zone` rồi cho rằng session đã sạch. Hãy lập danh sách mọi loại state mà ứng dụng tạo ra và có test xác nhận.

### Chiến lược C: Reset toàn bộ session hoặc loại bỏ physical connection

MySQL protocol có lệnh `COM_RESET_CONNECTION` để reset trạng thái session mà không cần đóng TCP connection. Cơ chế này có thể rollback transaction đang mở, reset session variables về global defaults, xóa user variables và temporary tables, giải phóng trạng thái session và prepared statement phía server.

Đây là lệnh ở mức giao thức; không gửi chuỗi SQL `RESET CONNECTION` như một câu SQL thông thường. Chỉ dùng tính năng reset session nếu phiên bản driver/pool hỗ trợ và tài liệu xác nhận cách tích hợp. Sau reset, các thiết lập cần thiết như timezone hoặc session defaults phải được áp dụng lại theo chính sách của pool.

Nếu không có cơ chế reset được hỗ trợ, pool có thể loại bỏ physical connection và tạo connection mới. Cách này tốn chi phí kết nối và xác thực, nhưng loại bỏ được session cũ. Không tự đóng socket bên dưới connection pool; dùng API eviction/invalidation do pool cung cấp.

### Thời điểm reset

Trình tự an toàn:

1. Kết thúc công việc của request.
2. Commit hoặc rollback transaction.
3. Xóa/khôi phục session state đã thay đổi.
4. Nếu cleanup thất bại, đánh dấu connection không còn tin cậy và loại khỏi pool.
5. Trả connection về pool sau khi cleanup hoàn tất.

Không trả connection về pool trước khi cleanup xong. Nếu transaction đang mở, rollback trước; nếu connection đã mất, không cố dùng nó để reset state mà hãy để pool loại bỏ.

## 9. Transaction isolation và autocommit

`autocommit` và transaction isolation có ảnh hưởng lớn đến cách request nhìn thấy dữ liệu.

Kiểm tra:

~~~sql
SELECT
  @@SESSION.autocommit,
  @@SESSION.transaction_isolation;
~~~

Nếu request đặt:

~~~sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
~~~

thì thiết lập SESSION này có thể tồn tại cho các transaction sau trên cùng session. Nếu một request khác cần REPEATABLE READ, nó có thể vô tình kế thừa mức isolation thấp hơn.

Với Spring, ưu tiên khai báo isolation tại ranh giới transaction:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void readReport() {
    // Query dùng transaction có isolation đã khai báo.
}
~~~

Spring transaction manager quản lý trạng thái JDBC isolation và khôi phục trạng thái được nó theo dõi khi kết thúc transaction. Không trộn nhiều cơ chế đặt isolation nếu không có lý do rõ ràng.

MySQL cũng có cú pháp đặt isolation cho transaction kế tiếp:

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
~~~

Không nhầm cú pháp này với `SET SESSION TRANSACTION ISOLATION LEVEL ...`, vốn thay đổi mặc định isolation cho các transaction tiếp theo của session.

Khi dùng pool, luôn bảo đảm transaction được commit/rollback trước khi close logical connection. Không giả định pool có thể tự sửa một transaction đang mở mà không gây tác động đến request khác.

## 10. Kiểm thử session leakage trong môi trường thử nghiệm

Một test đơn giản có thể phát hiện session state bị rò rỉ qua pool. Dùng pool có một physical connection để lần mượn sau có khả năng nhận lại đúng session:

1. Mượn connection A.
2. Đọc `CONNECTION_ID()`, `@@SESSION.time_zone` và `@@SESSION.sql_mode`.
3. Đổi timezone hoặc SQL mode.
4. Đặt một user variable.
5. Close logical connection A.
6. Mượn connection B.
7. Đọc lại các giá trị và so sánh.

Các truy vấn kiểm tra:

~~~sql
SELECT
  CONNECTION_ID() AS connection_id,
  @@SESSION.time_zone AS session_time_zone,
  @@SESSION.sql_mode AS session_sql_mode,
  @tenant_id AS tenant_id;
~~~

Nếu connection ID giống nhau và giá trị session vẫn mang thay đổi của request trước, pool đã tái sử dụng session chưa được cleanup. Nếu connection ID khác, test chưa chứng minh state được reset; nó chỉ nhận được physical connection khác. Có thể cấu hình pool thử nghiệm với `maximumPoolSize=1` và chạy tuần tự để làm test dễ tái lập.

Viết integration test với MySQL thật hoặc Testcontainers thay vì chỉ mock DataSource. Mock không thể xác minh hành vi session của server, timezone conversion, SQL mode hoặc protocol reset.

### Các tình huống nên đưa vào test

- Request A đổi `time_zone`, request B phải thấy UTC.
- Request A đổi `sql_mode`, request B phải thấy mode chuẩn.
- Request A đặt user variable, request B không được đọc thấy giá trị đó.
- Request A tạo temporary table, request B không được dùng lại bảng đó nếu chính sách yêu cầu cleanup.
- Request A lấy named lock, request B không bị khóa bởi lock còn sót.
- Request A rollback sau lỗi, request B không nhìn thấy transaction chưa kết thúc.
- Server restart hoặc connection timeout xảy ra, pool tạo connection mới và áp dụng lại init defaults.

## 11. Quan sát và xử lý lỗi vận hành

Khi phát hiện request chạy sai timezone hoặc SQL mode, hãy lấy thông tin ngay trên connection gây lỗi:

~~~sql
SELECT
  CONNECTION_ID(),
  @@GLOBAL.sql_mode,
  @@SESSION.sql_mode,
  @@GLOBAL.time_zone,
  @@SESSION.time_zone,
  @@SESSION.autocommit,
  @@SESSION.transaction_isolation;
~~~

Trong ứng dụng, ghi nhận pool name, request correlation ID, transaction boundary và cấu hình driver. Không ghi password, access token hoặc dữ liệu cá nhân nhạy cảm vào log.

Các dấu hiệu phổ biến:

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Một số request có giờ lệch | Session timezone khác nhau giữa connection | Log `CONNECTION_ID()`, `@@SESSION.time_zone` |
| Một số request không báo lỗi dữ liệu như mong đợi | SQL mode bị thay đổi hoặc strict mode bị tắt | So sánh GLOBAL và SESSION sql_mode |
| Request sau thấy user variable cũ | Session được tái sử dụng mà không cleanup | Kiểm tra `@variable` trên cùng connection |
| Query bị ảnh hưởng bởi temporary table cũ | Temporary table tồn tại trong session | Kiểm tra lifecycle và reset session |
| Transaction giữ khóa lâu | Connection được trả về pool khi transaction chưa kết thúc | Kiểm tra autocommit, rollback và transaction manager |
| Lỗi chỉ xuất hiện khi tải cao | Nhiều request luân phiên qua một tập connection có state khác nhau | Chạy integration test với pool nhỏ và log connection ID |
| Sau deploy chỉ một số connection dùng config mới | Connection cũ trong pool giữ session defaults trước deploy | Drain/evict pool và tạo connection mới |

Sau khi đổi global defaults hoặc URL properties, cân nhắc drain pool để các physical connections cũ được đóng và tạo lại. Thực hiện theo rolling deployment để tránh đồng loạt mất toàn bộ kết nối ứng dụng.

## 12. Checklist cấu hình Spring Boot/JPA

**Cấu hình server và driver**

- [ ] Xác định global sql_mode và timezone trên MySQL.
- [ ] Chọn một timezone chuẩn, thường là UTC cho session ứng dụng.
- [ ] Kiểm tra phiên bản Connector/J trước khi dùng connectionTimeZone và forceConnectionTimeZoneToSession.
- [ ] Đồng bộ timezone giữa Connector/J và Hibernate.
- [ ] Không dùng SET GLOBAL trong business request.

**Cấu hình pool**

- [ ] Hiểu connectionInitSql chỉ chạy khi physical connection mới được tạo.
- [ ] Không giả định init SQL chạy mỗi lần borrow.
- [ ] Ghi rõ session defaults cần thiết.
- [ ] Có cách cleanup/reset nếu ứng dụng thay đổi session state.
- [ ] Evict connection nếu cleanup thất bại hoặc session không còn tin cậy.

**Transaction và code**

- [ ] Dùng cùng DataSource/transaction manager cho JdbcTemplate và JPA khi cần cùng transaction.
- [ ] Đặt session defaults trước truy vấn repository đầu tiên.
- [ ] Ưu tiên transaction isolation do Spring quản lý.
- [ ] Commit/rollback trước khi trả connection.
- [ ] Không dùng user variable hoặc temporary table mà không có lifecycle rõ.

**Kiểm thử**

- [ ] Test với MySQL thật và connection pool.
- [ ] Mô phỏng nhiều request tuần tự trên cùng physical connection.
- [ ] Xác minh SQL mode, timezone, autocommit và isolation.
- [ ] Test temporary table, user variable, named lock nếu ứng dụng dùng.
- [ ] Test reconnect, server restart và drain pool sau thay đổi cấu hình.

## 13. Ghi nhớ

- Một logical connection đóng trong pool thường chỉ được trả về pool; MySQL session vật lý có thể vẫn tồn tại.
- SESSION variables, user variables, temporary tables và named locks có vòng đời theo session.
- GLOBAL defaults không tự cập nhật các session đã mở.
- HikariCP `connectionInitSql` chạy khi tạo physical connection, không chạy mỗi lần borrow.
- Connector/J `connectionTimeZone`, `forceConnectionTimeZoneToSession` và Hibernate `hibernate.jdbc.time_zone` phục vụ các lớp timezone khác nhau.
- TIMESTAMP chuyển đổi theo session timezone; DATETIME lưu giá trị lịch mà không tự chuyển đổi.
- Dùng `SET SESSION ... = DEFAULT` để khôi phục biến đã biết về global default; reset các user variables và tài nguyên session khác theo đúng lifecycle.
- `COM_RESET_CONNECTION` là cơ chế giao thức; chỉ dùng qua driver/pool hỗ trợ, không gửi như SQL thông thường.
- Kết thúc transaction và cleanup trước khi trả connection về pool.
- Kiểm thử session leakage với MySQL thật, pool nhỏ và CONNECTION_ID().

Quản lý session state tốt giúp mọi request nhận được một môi trường SQL dự đoán được dù connection được tái sử dụng nhiều lần. Hãy xác định state nào là mặc định của cả pool, state nào thuộc một transaction và state nào phải được cleanup; sau đó kiểm chứng bằng integration test trên chính MySQL và pool mà ứng dụng triển khai.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: SET Syntax for Variable Assignment](https://dev.mysql.com/doc/refman/8.0/en/set-variable.html)
- [MySQL 8.0 Reference Manual: Server System Variables — sql_mode and time_zone](https://dev.mysql.com/doc/refman/8.0/en/server-system-variables.html)
- [MySQL 8.0 Reference Manual: TIMESTAMP and DATETIME](https://dev.mysql.com/doc/refman/8.0/en/datetime.html)
- [MySQL 8.0 Reference Manual: COM_RESET_CONNECTION](https://dev.mysql.com/doc/dev/mysql-server/latest/page_protocol_com_reset_connection.html)
- [MySQL Connector/J Developer Guide: Connection Time Zone](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-datetime-types-processing.html)
- [HikariCP Configuration: connectionInitSql](https://github.com/brettwooldridge/HikariCP#gear-configuration-knobs-baby)
- [Spring Boot Reference: Configure a DataSource](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Hibernate ORM User Guide: JDBC Time Zone](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#basic-temporal)

