# Chọn phiên bản, storage engine và cấu hình giống môi trường mục tiêu

Một bài kiểm thử MySQL chỉ đáng tin khi database dùng để kiểm thử có những đặc tính quan trọng tương đương môi trường mà ứng dụng sẽ chạy. Một test suite có thể xanh trên máy developer nhưng lỗi trên production vì khác phiên bản MySQL, storage engine, collation, SQL mode, transaction isolation, plugin hoặc cấu hình tài nguyên.

Mục tiêu không phải lúc nào cũng sao chép toàn bộ production. Cần xác định những yếu tố có thể làm thay đổi kết quả SQL, tính nhất quán, hiệu năng hoặc khả năng kết nối, sau đó dựng môi trường kiểm thử đủ gần với mục tiêu. Khi điều tra một lỗi cụ thể, nên tái tạo cả phiên bản patch, engine, cấu hình và đặc điểm dữ liệu đã tạo ra lỗi đó.

## 1. Vì sao môi trường MySQL tương đồng lại quan trọng?

Các môi trường khác nhau có thể cho kết quả khác dù chạy cùng một câu SQL:

- Phiên bản MySQL mới có thể thay đổi cú pháp được hỗ trợ, default SQL mode, optimizer hoặc hành vi của một tính năng.
- `InnoDB` và `MyISAM` có hành vi khác nhau về transaction, locking, crash recovery và foreign key.
- Collation khác nhau có thể làm phép so sánh chuỗi, `ORDER BY` và unique index cho kết quả khác.
- `ONLY_FULL_GROUP_BY` hoặc strict SQL mode có thể khiến truy vấn hay dữ liệu bị từ chối.
- Time zone session khác nhau có thể làm `TIMESTAMP` hiển thị hoặc được diễn giải khác.
- Transaction isolation và cấu hình durability có thể ảnh hưởng concurrency, deadlock và kết quả khi crash.
- Cấu hình memory, disk và connection pool khác nhau có thể che giấu timeout hoặc làm thay đổi execution plan.

Ví dụ, test dùng H2 trong memory có thể chấp nhận một kiểu SQL hoặc biểu thức mà MySQL không hỗ trợ. Ngay cả khi dùng MySQL trong container, test với tag `mysql:latest` có thể chạy trên phiên bản mới hơn production và thay đổi theo thời gian. Vì vậy, test database phải được pin theo phiên bản cụ thể và cấu hình có thể tái lập.

## 2. Những lớp cần đối chiếu

Hãy kiểm tra môi trường theo từng lớp, từ server đến schema và dữ liệu:

| Lớp | Thông tin cần đối chiếu | Vì sao ảnh hưởng đến test |
|---|---|---|
| Server binary | MySQL version, patch, edition/distribution, OS, CPU architecture | Xác định tính năng, bug fix, optimizer và khả năng tương thích. |
| Storage engine | Engine mặc định và engine thực tế của từng bảng | Quyết định transaction, locking, foreign key, crash recovery và index. |
| Schema | Data type, charset, collation, index, constraint, partition | Quyết định cách lưu, so sánh, kiểm tra và truy vấn dữ liệu. |
| Session | `sql_mode`, `time_zone`, isolation level, character set | Có thể khác giữa các connection trong cùng server. |
| Server configuration | Buffer pool, redo/binlog, max connections, temporary table, optimizer | Ảnh hưởng tải, durability, execution plan và giới hạn. |
| Plugin/security | Authentication plugin, component, UDF, TLS, account/grants | Ảnh hưởng đăng nhập, quyền và các tính năng phụ thuộc plugin. |
| Topology | Binary log, GTID, replication, Group Replication, Router | Cần thiết cho test failover, replication và read/write routing. |
| Runtime resources | CPU, RAM, disk type/latency, filesystem, container limits | Ảnh hưởng latency, concurrency và hành vi khi thiếu tài nguyên. |
| Data shape | Row count, cardinality, phân bố dữ liệu, dữ liệu biên | Ảnh hưởng optimizer, index selectivity và đường chạy nghiệp vụ. |

Không phải test nào cũng cần replication hoặc production-scale data. Hãy lập danh sách parity theo mục tiêu kiểm thử thay vì mặc định mọi test phải dựng nguyên một production cluster.

## 3. Chọn đúng phiên bản MySQL

### Pin cả phiên bản patch

Ghi lại phiên bản chính xác trên môi trường mục tiêu:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@version_compile_os AS compile_os,
    @@version_compile_machine AS compile_machine;
```

Ví dụ, nếu production đang chạy MySQL `8.4.x`, test trước khi phát hành nên dùng đúng patch version production đang chạy hoặc patch version đích đã được phê duyệt. Khi điều tra lỗi, ưu tiên tái tạo đúng patch version xảy ra lỗi. Không dùng tag `latest` cho test cần tính tái lập.

Tag container nên được pin cụ thể:

```text
mysql:8.4.4
```

Tag trên chỉ là ví dụ minh họa. Hãy thay bằng patch version thực tế của môi trường mục tiêu. Nếu cần kiểm thử đường nâng cấp, tạo thêm job chạy phiên bản nguồn và phiên bản đích để so sánh; không thay thế test trên phiên bản production hiện tại bằng một phiên bản ngẫu nhiên mới hơn.

### Phiên bản patch, minor và major

- **Patch release** thường chứa bug fix và security fix trong cùng dòng phát hành. Một số thay đổi vẫn có thể ảnh hưởng hành vi, nên cần kiểm tra đúng patch khi tái hiện sự cố.
- **Minor release** trong các dòng MySQL hiện đại có thể bổ sung tính năng, thay đổi optimizer hoặc default; kiểm tra release notes và compatibility.
- **Major release** có thể thay đổi định dạng nội bộ, data dictionary, plugin, cú pháp hoặc quy trình upgrade; cần kiểm thử nâng cấp riêng.

Không suy ra tương thích chỉ từ việc hai server đều hiển thị `8.x`. Ghi lại version đầy đủ, distribution và kiến trúc hệ điều hành.

### Kiểm thử ma trận phiên bản

Một dự án có thể cần nhiều loại job:

| Job | Phiên bản database | Mục đích |
|---|---|---|
| Pull request | Phiên bản patch chuẩn của dự án | Phản hồi nhanh và ổn định cho thay đổi code. |
| Compatibility | Phiên bản tối thiểu được hỗ trợ | Phát hiện dùng tính năng hoặc cú pháp quá mới. |
| Pre-release | Phiên bản đích dự kiến triển khai | Kiểm tra trước khi nâng cấp production. |
| Upgrade test | Phiên bản source rồi nâng lên target | Xác nhận dữ liệu và ứng dụng hoạt động sau upgrade. |
| Incident reproduction | Đúng patch/version đã xảy ra lỗi | Tái tạo và xác nhận bản sửa lỗi. |

Ma trận cần có giới hạn hợp lý. Không nhất thiết chạy mọi tổ hợp version × OS × engine × config ở mọi pull request; có thể chạy smoke test nhanh cho từng commit và kiểm thử sâu theo lịch hoặc trước release.

## 4. Kiểm tra storage engine

Storage engine quyết định cách MySQL lưu và xử lý dữ liệu của từng bảng. Cùng một server có thể có nhiều bảng dùng engine khác nhau, vì vậy không chỉ kiểm tra engine mặc định.

Liệt kê engine được server hỗ trợ:

```sql
SHOW ENGINES;
```

Xem engine mặc định:

```sql
SHOW VARIABLES LIKE 'default_storage_engine';
```

Kiểm kê engine của các bảng:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
      'mysql', 'sys', 'performance_schema', 'information_schema'
  )
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

Với ứng dụng giao dịch thông thường, `InnoDB` là lựa chọn phổ biến và là engine mặc định trong MySQL hiện đại. InnoDB hỗ trợ transaction, row-level locking, foreign key, crash recovery và MVCC. Nếu production dùng InnoDB, test cho nghiệp vụ giao dịch cũng cần InnoDB để kiểm tra đúng commit/rollback, deadlock và constraint.

Một số khác biệt quan trọng:

| Engine | Đặc điểm | Điều cần kiểm thử |
|---|---|---|
| `InnoDB` | Transactional, MVCC, row-level locking, foreign key và crash recovery | Isolation, deadlock, rollback, foreign key, redo/undo và durability. |
| `MyISAM` | Không hỗ trợ transaction hoặc foreign key; locking ở mức table | Không dùng test InnoDB để suy ra hành vi MyISAM. Kiểm tra table lock và hậu quả khi lỗi. |
| `MEMORY` | Dữ liệu nằm trong memory và mất khi server restart; hỗ trợ kiểu index riêng | Kiểm tra giới hạn kích thước, kiểu dữ liệu và vòng đời dữ liệu. |
| `NDB` | Engine phân tán của MySQL Cluster, có kiến trúc và giới hạn riêng | Cần môi trường NDB thực tế; InnoDB container không thể thay thế. |

Nếu test dùng bảng tạm hoặc bảng staging với engine khác production, ghi rõ lý do. Không dựa vào `default_storage_engine` để kết luận tất cả bảng đều dùng cùng engine.

Kiểm tra DDL của bảng trọng yếu:

```sql
SHOW CREATE TABLE appdb.orders;
SHOW CREATE TABLE appdb.order_items;
```

DDL là nơi xác nhận engine, charset, collation, index, constraint, partition và default thực tế. Đối chiếu DDL trên test với production hoặc migration dự kiến.

## 5. Thu thập cấu hình MySQL ở cấp server và session

Một số biến có cả global và session scope. Kết nối quản trị có thể thấy giá trị global, trong khi ứng dụng chạy với session value khác do driver hoặc connection initialization.

Xem biến global:

```sql
SHOW GLOBAL VARIABLES;
```

Xem biến của connection hiện tại:

```sql
SHOW SESSION VARIABLES;
```

Không cần lưu toàn bộ hàng nghìn biến cho mọi test. Hãy lọc các nhóm ảnh hưởng trực tiếp đến ứng dụng:

```sql
SHOW GLOBAL VARIABLES LIKE 'character_set%';
SHOW GLOBAL VARIABLES LIKE 'collation%';
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW GLOBAL VARIABLES LIKE 'time_zone';
SHOW GLOBAL VARIABLES LIKE 'transaction_isolation';
SHOW GLOBAL VARIABLES LIKE 'default_storage_engine';
SHOW GLOBAL VARIABLES LIKE 'lower_case_table_names';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'optimizer_switch';
```

Kiểm tra session của chính connection ứng dụng:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.character_set_client AS client_charset,
    @@SESSION.character_set_connection AS connection_charset,
    @@SESSION.character_set_results AS result_charset,
    @@SESSION.collation_connection AS connection_collation;

-- MySQL 8.0+: transaction_isolation
SHOW SESSION VARIABLES LIKE 'transaction_isolation';
-- MySQL 5.7: tx_isolation
SHOW SESSION VARIABLES LIKE 'tx_isolation';
```

Tên biến và scope có thể thay đổi theo phiên bản. Nếu một biến không tồn tại trên bản MySQL đang dùng, kiểm tra `SHOW VARIABLES LIKE 'pattern'` và tài liệu đúng phiên bản; không để một truy vấn kiểm kê dùng chung làm test thất bại chỉ vì biến đã đổi tên hoặc bị loại bỏ.

## 6. Những cấu hình dễ làm test khác production

### Character set và collation

Kiểm tra server defaults:

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
```

Kiểm tra database, table và column vì chúng có thể ghi đè default server:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'appdb';

SELECT
    TABLE_NAME,
    TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_TYPE = 'BASE TABLE';
```

Collation ảnh hưởng `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY` và unique key. Test cần dữ liệu có dấu, hoa/thường, ký tự Unicode và giá trị gần trùng nhau để phát hiện khác biệt. Đừng chỉ xác nhận charset là `utf8mb4`; hai collation `utf8mb4` khác nhau vẫn có thể cho kết quả so sánh khác.

### SQL mode

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

`STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `NO_ZERO_DATE` và các mode khác có thể làm thay đổi việc chấp nhận dữ liệu hoặc câu truy vấn. Test phải khởi tạo session giống ứng dụng, không chỉ kiểm tra global value. Khi connection pool khởi tạo session bằng lệnh riêng, hãy xác nhận những lệnh đó chạy trên mọi connection mới.

### Time zone

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

Kiểm thử `TIMESTAMP` và `DATETIME` với timezone đúng. `TIMESTAMP` được chuyển đổi giữa session timezone và UTC; `DATETIME` giữ giá trị lịch mà không tự chuyển timezone. Nếu ứng dụng dùng tên vùng như `Asia/Ho_Chi_Minh`, cần timezone tables tương ứng.

### Transaction isolation và durability

Kiểm tra isolation level và các thiết lập durability liên quan workload:

```sql
SHOW GLOBAL VARIABLES LIKE 'transaction_isolation';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
```

Isolation level ảnh hưởng snapshot visibility, locking và concurrency. `innodb_flush_log_at_trx_commit` cùng `sync_binlog` ảnh hưởng cách MySQL flush redo/binlog và độ bền dữ liệu khi mất điện/crash. Một test chạy trên cấu hình durability yếu có thể không phát hiện vấn đề xảy ra trên production, hoặc ngược lại có latency rất khác.

Không thay các biến durability để làm test nhanh hơn rồi dùng kết quả đó làm bằng chứng cho production. Nếu cần test hiệu năng với cấu hình nhẹ, phân biệt rõ test logic và test durability/performance.

### Tên file và tên bảng

`lower_case_table_names` ảnh hưởng cách MySQL lưu và so sánh tên database/table. Giá trị mặc định và giới hạn thay đổi phụ thuộc hệ điều hành/filesystem; biến này cần được thiết lập trước khi khởi tạo data directory và không thể tùy tiện đổi trên một instance đã có dữ liệu.

Nếu developer dùng Windows hoặc macOS nhưng production dùng Linux, tên bảng khác chữ hoa/thường có thể chạy ở máy developer nhưng lỗi ở production. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'lower_case_table_names';
```

Nên dùng tên schema/table nhất quán về chữ thường và không dựa vào hành vi không phân biệt hoa/thường của một hệ điều hành.

### Optimizer và tài nguyên

Các biến như `optimizer_switch`, `innodb_buffer_pool_size`, `tmp_table_size`, `max_connections` và `max_allowed_packet` có thể làm khác execution plan hoặc giới hạn xử lý. Không nhất thiết mọi giá trị phải giống tuyệt đối nếu máy test nhỏ hơn production, nhưng phải biết khác biệt nào có thể ảnh hưởng kết quả đang kiểm tra.

Với test hiệu năng, cần gần giống cả CPU, RAM, storage latency, filesystem, container limits và kích thước dữ liệu. Container MySQL chạy trên laptop không thể đại diện chính xác cho storage production nếu ổ đĩa, cache và giới hạn CPU khác xa.

## 7. Dựng MySQL test bằng Docker với tag cố định

Docker giúp dựng database nhanh và cô lập khỏi MySQL cài trên máy developer. Ví dụ `compose.yaml`:

```yaml
services:
  mysql-test:
    image: mysql:${MYSQL_IMAGE_TAG}
    container_name: mysql-test
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: appdb
      MYSQL_USER: app_test
      MYSQL_PASSWORD: ${MYSQL_TEST_PASSWORD}
    ports:
      - "3307:3306"
    volumes:
      - mysql-test-data:/var/lib/mysql
      - ./mysql-test.cnf:/etc/mysql/conf.d/zz-test.cnf:ro
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 5s
      timeout: 3s
      retries: 20

volumes:
  mysql-test-data:
```

File `.env` dùng cho môi trường local, không commit secret thật:

```dotenv
MYSQL_IMAGE_TAG=8.4.4
MYSQL_ROOT_PASSWORD=local-root-password
MYSQL_TEST_PASSWORD=local-test-password
```

Thay `8.4.4` bằng patch version mục tiêu đã xác nhận. Nếu muốn reset dữ liệu test, xóa volume bằng quy trình dành riêng cho môi trường local; lệnh xóa volume sẽ xóa toàn bộ dữ liệu trong volume đó. Không dùng project name, volume hoặc credential của production cho cấu hình thử nghiệm.

File `mysql-test.cnf` có thể chứa các cấu hình phù hợp với test target:

```ini
[mysqld]
default_storage_engine = InnoDB
character_set_server = utf8mb4
collation_server = utf8mb4_0900_ai_ci
default-time-zone = '+00:00'
max_connections = 100
```

Các giá trị trong ví dụ phải được thay bằng cấu hình mục tiêu. Đặc biệt, `lower_case_table_names` cần được quyết định trước khi data directory được khởi tạo và phải phù hợp nền tảng; không thêm hoặc thay giá trị này trên volume đã được tạo mà chưa dựng lại môi trường. Với MySQL khác phiên bản, collation có thể không tồn tại; kiểm tra trước khi khởi động.

Khởi động và kiểm tra:

```bash
docker compose up -d
docker compose ps
docker compose logs mysql-test
```

Kết nối vào cổng host `3307`, sau đó chạy các truy vấn inventory ở các phần trên. Pin image tag giúp tái lập version; để kiểm soát chặt hơn trong pipeline, có thể pin image digest sau khi đã xác nhận image được phê duyệt.

## 8. Dùng Testcontainers trong integration test Java

Với ứng dụng Spring Boot, Testcontainers có thể khởi động MySQL thật trong thời gian test và cung cấp JDBC URL động. Điều này giảm phụ thuộc vào database cài sẵn trên máy developer.

Ví dụ với JUnit 5 và Testcontainers 1.x API:

```java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIT {

    @Container
    static final MySQLContainer<?> MYSQL =
            new MySQLContainer<>("mysql:8.4.4")
                    .withDatabaseName("appdb")
                    .withUsername("app_test")
                    .withPassword("test-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
    }

    @Test
    void savesAndReadsCustomer() {
        // Gọi repository thật và xác nhận dữ liệu trên MySQL container.
    }
}
```

Tag `mysql:8.4.4` là ví dụ; thay bằng đúng patch version mục tiêu. Cần thêm Testcontainers JUnit Jupiter và MySQL module phù hợp vào test dependencies. Package import của `MySQLContainer` thay đổi giữa các major version Testcontainers; dùng API/import theo phiên bản dependency đã khóa trong dự án.

Testcontainers mặc định tạo instance mới theo vòng đời test class/container. Nếu dùng reusable container hoặc chia sẻ container để tăng tốc, cần tránh để dữ liệu test của case trước ảnh hưởng case sau. Dùng schema/database riêng, transaction rollback hoặc cleanup rõ ràng. Không bật reuse một cách ngầm định trong CI nếu cần môi trường sạch và có thể tái lập.

### Cấu hình MySQL container giống mục tiêu

Có thể gắn file cấu hình MySQL hoặc tham số server phù hợp với API Testcontainers của phiên bản đang dùng. Sau khi container sẵn sàng, xác minh bằng SQL thay vì giả định cấu hình đã được áp dụng. Ví dụ:

```java
try (Connection connection = DriverManager.getConnection(
        MYSQL.getJdbcUrl(), MYSQL.getUsername(), MYSQL.getPassword());
     Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery("SELECT VERSION(), @@sql_mode, @@time_zone")) {

    if (rs.next()) {
        System.out.println("version=" + rs.getString(1));
        System.out.println("sql_mode=" + rs.getString(2));
        System.out.println("time_zone=" + rs.getString(3));
    }
}
```

Trong test thật, nên assert version/config mong đợi thay vì chỉ in ra console. Không log credential hoặc URL chứa password.

## 9. Dữ liệu test phải giống cả cấu trúc lẫn phân bố

Một database trống có thể kiểm tra migration tạo bảng, nhưng không đại diện cho truy vấn trên production có hàng triệu bản ghi. Query plan phụ thuộc cardinality, histogram, độ chọn lọc và phân bố dữ liệu.

Một bộ dữ liệu test có giá trị nên bao gồm:

- Quy mô gần với mục tiêu đối với test hiệu năng; ít nhất phải đủ lớn để bộc lộ đường quét/index đang kiểm tra.
- Phân bố khóa và dữ liệu lệch (skew), chẳng hạn một customer có nhiều order hơn hẳn các customer khác.
- Giá trị null, rỗng, tối thiểu/tối đa và dữ liệu Unicode.
- Các nhóm có trùng hoa/thường hoặc dấu nếu collation ảnh hưởng.
- Bản ghi có quan hệ parent-child, foreign key và các trạng thái nghiệp vụ hiếm.
- Dữ liệu tạo ra contention trên hàng nóng khi kiểm thử concurrency.
- Dữ liệu thời gian ở ranh giới ngày, timezone và daylight-saving nếu nghiệp vụ có dùng vùng thời gian.

Không sao chép dữ liệu production có thông tin cá nhân hoặc bí mật vào môi trường test nếu chưa có quy trình bảo vệ phù hợp. Có thể dùng synthetic data hoặc dữ liệu đã masking nhưng phải giữ đặc điểm phân bố, quan hệ và cardinality cần cho bài test.

Sau khi nạp dữ liệu lớn, cập nhật statistics phù hợp và chạy truy vấn đại diện. `ANALYZE TABLE` có thể cập nhật thống kê optimizer; hãy dùng theo kế hoạch và so sánh với production nếu cần tái hiện execution plan.

## 10. Kiểm thử engine và cấu hình theo mục tiêu

Không phải test nào cũng cần giống production ở mọi khía cạnh. Hãy liên hệ parity với loại kiểm thử:

| Loại kiểm thử | Điều cần giống production nhất |
|---|---|
| Unit test logic không truy cập DB | Có thể dùng mock/fake; không cần MySQL nếu SQL không nằm trong phạm vi test. |
| Repository/integration test | MySQL version, engine, schema, collation, SQL mode, timezone và Connector/J. |
| Transaction/concurrency test | InnoDB, isolation level, lock behavior, connection count và dữ liệu tranh chấp. |
| Migration test | Phiên bản source/target, engine, DDL, collation, dữ liệu hiện hữu và quyền migration. |
| Replication/failover test | Binary log, GTID, topology, server ID/UUID, Router và network behavior. |
| Performance test | Version, optimizer settings, data size/distribution, CPU, RAM, storage latency và concurrency. |
| Backup/restore test | Phiên bản công cụ, engine, encryption/keyring, binary log/GTID metadata và storage. |

H2 hoặc mock vẫn có thể hữu ích cho unit test nhanh. Nhưng nếu test xác nhận SQL MySQL, kiểu dữ liệu MySQL, lock hoặc migration thì phải có ít nhất một integration test chạy trên MySQL thật.

## 11. Tạo báo cáo parity tự động

Có thể lưu kết quả inventory của source/target thành artifact của pipeline rồi so sánh các giá trị quan trọng. Ví dụ script SQL thu thập cấu hình:

```sql
SELECT 'version' AS item, VERSION() AS value
UNION ALL
SELECT 'version_comment', @@version_comment
UNION ALL
SELECT 'default_storage_engine', @@GLOBAL.default_storage_engine
UNION ALL
SELECT 'character_set_server', @@GLOBAL.character_set_server
UNION ALL
SELECT 'collation_server', @@GLOBAL.collation_server
UNION ALL
SELECT 'sql_mode', @@GLOBAL.sql_mode
UNION ALL
SELECT 'time_zone', @@GLOBAL.time_zone
UNION ALL
SELECT 'lower_case_table_names', CAST(@@GLOBAL.lower_case_table_names AS CHAR);
```

Truy vấn này chỉ là phần inventory nhỏ; các biến không có trên một phiên bản cũ có thể khiến cả truy vấn lỗi. Trong pipeline đa phiên bản, dùng các truy vấn theo capability hoặc đọc `SHOW VARIABLES` rồi lọc ở client để tránh giả định mọi biến luôn tồn tại.

Một báo cáo parity nên phân loại sai khác:

- **Must match**: sai khác làm kết quả kiểm thử không còn đáng tin, như version mục tiêu, storage engine của bảng giao dịch, collation quan trọng hoặc SQL mode ứng dụng.
- **Must be documented**: sai khác có thể chấp nhận nhưng cần ghi rõ, như RAM/CPU nhỏ hơn trong unit integration environment.
- **Not required for this test**: thành phần không nằm trong phạm vi, ví dụ không dựng replication trong test CRUD đơn giản.

Không chỉ so sánh chuỗi cấu hình. Hãy xác minh hiệu lực bằng hành vi: thử transaction rollback, kiểm tra foreign key, so sánh chuỗi theo collation, đọc `TIMESTAMP` theo session timezone và chạy truy vấn có execution plan quan trọng.

## 12. Những sai lệch thường gây false confidence

| Sai lệch | Vì sao test vẫn có thể xanh | Cách cải thiện |
|---|---|---|
| Dùng `mysql:latest` | Developer và CI có thể chạy version khác nhau ở các thời điểm khác nhau. | Pin tag patch hoặc digest. |
| Dùng H2 thay MySQL | H2 có cú pháp, kiểu dữ liệu và locking khác. | Dùng MySQL container cho integration test liên quan SQL. |
| Chỉ so sánh server default | Table/column/session có thể override server value. | Kiểm tra DDL và session thực của connection ứng dụng. |
| Chỉ kiểm tra default engine | Bảng hiện hữu có thể dùng engine khác. | Kiểm kê `INFORMATION_SCHEMA.TABLES.ENGINE`. |
| Dữ liệu test quá nhỏ | Optimizer chọn plan khác và không bộc lộ vấn đề scale. | Dùng dữ liệu đại diện về cardinality và skew cho performance test. |
| Máy test quá mạnh hoặc storage khác | Latency và contention production không tái hiện. | Ghi rõ giới hạn tài nguyên; dùng benchmark trên hạ tầng gần mục tiêu. |
| SQL mode session không giống | Test chạy bằng admin connection nhưng ứng dụng có mode khác. | Kiểm tra session qua chính pool/driver của ứng dụng. |
| Khác `lower_case_table_names` | Tên table có thể hoạt động trên máy developer nhưng lỗi trên Linux. | Chuẩn hóa tên và dựng test phù hợp nền tảng mục tiêu. |
| Không kiểm tra plugin/authentication | Test dùng user đơn giản nhưng production connector không đăng nhập được. | Kiểm tra driver, auth plugin, TLS và grants thực tế. |
| Dùng cùng database cho mọi test | Dữ liệu còn lại làm test phụ thuộc thứ tự chạy. | Tạo schema/container sạch hoặc cleanup có kiểm soát. |

## 13. Checklist trước khi chấp nhận một test environment

- [ ] Đã ghi MySQL version đầy đủ, patch, distribution và platform.
- [ ] Image/container hoặc package được pin; không dùng `latest` cho test tái lập.
- [ ] Engine mặc định và engine từng bảng quan trọng khớp mục tiêu.
- [ ] DDL, charset, collation, index và constraint đã được đối chiếu.
- [ ] `sql_mode`, timezone, transaction isolation và session initialization khớp ứng dụng.
- [ ] `lower_case_table_names` phù hợp nền tảng và được quyết định trước khi tạo data directory.
- [ ] Plugin, authentication, TLS, user/grants và Connector/J được kiểm tra.
- [ ] Cấu hình durability, binary log và GTID phù hợp loại test cần chạy.
- [ ] Dữ liệu test có cardinality, skew và giá trị biên phù hợp mục tiêu.
- [ ] CPU, RAM, disk và container limits được ghi nhận cho test hiệu năng.
- [ ] Test chạy trên database sạch hoặc có cleanup độc lập, không phụ thuộc thứ tự.
- [ ] Pipeline lưu báo cáo version/config và phát hiện sai khác quan trọng.

Môi trường kiểm thử tốt không chỉ có cùng tên sản phẩm MySQL. Nó phải tái tạo đúng các yếu tố có thể ảnh hưởng đến hành vi đang kiểm tra: phiên bản, engine, schema, session, cấu hình và dữ liệu. Hãy pin phiên bản, kiểm kê engine thực tế, xác minh session của ứng dụng và ghi rõ những khác biệt được chấp nhận. Khi đó, kết quả test mới đủ tin cậy để phát hiện lỗi trước khi triển khai lên môi trường mục tiêu.
