# Quay về template cho batch hoặc thao tác chuyên biệt chưa được facade đáp ứng

## 1. Ý tưởng: JdbcClient là facade thuận tiện, không phải công cụ thay thế mọi API JDBC

`JdbcClient` trong Spring Framework là một **fluent facade** cho những thao tác SQL thường gặp. Ví dụ, code có thể biểu đạt truy vấn theo thứ tự tự nhiên: SQL → bind tham số → map kết quả → lấy danh sách hoặc một phần tử.

~~~java
List<ProductRow> rows = client.sql("""
        SELECT id, sku, price, stock, state
        FROM inventory
        WHERE state = :state
        ORDER BY id
        """)
        .param("state", "READY")
        .query((rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getBigDecimal("price"),
                rs.getInt("stock"),
                rs.getString("state")))
        .list();
~~~

Đoạn trên là **mã minh họa trong repository** đã có trường `JdbcClient client`, record `ProductRow` và import `List`. Với CRUD thông dụng, API này dễ đọc hơn việc viết nhiều đối tượng hỗ trợ quanh một `JdbcTemplate`.

Tuy nhiên, **không nên ép mọi yêu cầu JDBC vào fluent facade**. Khi thao tác cần batch phức tạp, quyền kiểm soát Statement/Connection, một cơ chế stored procedure đặc thù hoặc tối ưu hóa JDBC mà phiên bản JdbcClient đang dùng chưa hỗ trợ, hãy quay về **JdbcTemplate, NamedParameterJdbcTemplate, SimpleJdbcCall hoặc SimpleJdbcInsert**. Đây không phải “hạ cấp kiến trúc”: chính JdbcClient được xây trên các template JDBC; ta chỉ chọn mức API phù hợp với bài toán.

### Lưu ý phiên bản cực kỳ quan trọng

Không được viết câu tuyệt đối rằng “JdbcClient không hỗ trợ batch” cho mọi phiên bản:

- **Spring Framework 6.1, 6.2 và các bản API đầu của 7.0:** JdbcClient chủ yếu có fluent query/update; batch thông thường sử dụng `JdbcTemplate.batchUpdate(...)` hoặc `NamedParameterJdbcTemplate.batchUpdate(...)`. Ứng dụng ví dụ trong bài dùng **Spring Boot 3.3.5 / Spring Framework 6.1.x**, nên quay về template để batch.
- **Spring Framework 7.1:** API `JdbcClient.StatementSpec.batch()` với `BatchSpec.entry(...)/entries(...).update()` đã xuất hiện. Ở phiên bản này, nhiều batch đơn giản **có thể thực hiện bằng fluent facade**. Ta vẫn quay về template cho thao tác đặc biệt chưa được facade bao phủ hoặc khi cần khả năng kiểm soát cụ thể.
- **Mọi phiên bản:** cần xem chính Javadoc đúng version và driver đang chạy. Không copy API batch của 7.1 vào project Spring 6.1 rồi mong nó biên dịch.

**Hợp đồng học tập:** “quay về template” là **lựa chọn theo năng lực của API ở phiên bản hiện tại và yêu cầu nghiệp vụ**, không phải một quy tắc bất biến mãi mãi.

## 2. JdbcClient và các lớp bên dưới

JdbcClient hỗ trợ binding tham số theo vị trí hoặc theo tên và ủy quyền cho tầng JDBC template:

~~~text
Service / Transaction boundary
          |
          v
Repository
  |----------------------------|
  | JdbcClient                 |  query/update fluent API
  |----------------------------|
  | JdbcTemplate               |  batchUpdate, execute callbacks,
  |                            |  Statement/ResultSet control
  |----------------------------|
  | NamedParameterJdbcTemplate |  named-parameter batch,
  |                            |  SqlParameterSource, typed NULL
  |----------------------------|
  | SimpleJdbcInsert/Call      |  generated keys, stored procedures
  |----------------------------|
          |
          v
Spring JDBC transaction & resource management
          |
          v
DataSource -> JDBC driver -> Database
~~~

Các lớp ở các “tầng” này **cùng tồn tại trong một module**. Ta không cần viết lại toàn bộ repository để thay JdbcClient bằng JdbcTemplate. Một method có thể dùng JdbcClient để SELECT dễ đọc; một method khác dùng `JdbcTemplate.batchUpdate` để ghi nhiều dòng; một method chuyên biệt có thể dùng `ConnectionCallback` hoặc một `SimpleJdbcCall`.

Để giao dịch thống nhất, các delegate phải dùng **đúng DataSource mà transaction manager quản lý**. Ví dụ:

~~~java
public InventoryRepository(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
    this.namedJdbc = new NamedParameterJdbcTemplate(jdbc);
    this.client = JdbcClient.create(jdbc);
}
~~~

Đây là đoạn constructor minh họa: biến `jdbc` được Spring inject, `namedJdbc` và `client` cùng dùng lại JdbcTemplate đó. Lợi ích là cùng cấu hình DataSource, connection handling và các thiết lập template cần thiết. Không cần tạo DataSource hoặc connection pool thứ hai chỉ vì muốn dùng API khác.

### Chọn abstraction theo công việc

| Việc cần làm | API phù hợp | Lý do |
| --- | --- | --- |
| SELECT với named parameters và map DTO | JdbcClient | Fluent, ngắn, dễ đọc. |
| UPDATE/INSERT một lần với bind đơn giản | JdbcClient | `sql(...).param(...).update()` là đủ. |
| Batch trên Spring Framework 6.1/6.2 | `JdbcTemplate.batchUpdate` hoặc `NamedParameterJdbcTemplate.batchUpdate` | Facade ở những version này chưa có fluent batch. |
| Batch trên Spring Framework 7.1 | `JdbcClient.sql(...).batch()` **hoặc** template | Facade có batch mới; template vẫn dùng được, phù hợp nếu cần điều khiển thấp hơn. |
| Batch named parameters với typed NULL | `NamedParameterJdbcTemplate.batchUpdate` | `SqlParameterSource[]` cung cấp giá trị và metadata SQL type. |
| Batch nhiều lô với kích thước cố định | `JdbcTemplate.batchUpdate(sql, collection, batchSize, setter)` | Được tổ chức theo chunk, hữu ích với lượng phần tử lớn. |
| JDBC Connection metadata/vendor API | `JdbcTemplate.execute(ConnectionCallback<T>)` | Truy cập Connection trong vòng đời do Spring quản lý. |
| Tùy chỉnh PreparedStatement | `JdbcTemplate.execute(..., PreparedStatementCallback<T>)` | Có quyền dùng phương thức JDBC mức thấp trên statement. |
| Stored procedure có IN/OUT parameters | `SimpleJdbcCall` hoặc JdbcTemplate/CallableStatement | Chọn API mô tả OUT parameter và driver phù hợp. |
| INSERT lấy generated key, dùng metadata | `SimpleJdbcInsert` hoặc template với KeyHolder | Không cần tự xử lý phần lớn JDBC plumbing. |
| Tổng hợp nhiều hàng từ một ResultSet | RowMapper / ResultSetExtractor qua template hoặc facade | Tùy phạm vi và mức kiểm soát cần thiết. |

## 3. Batch thực chất là gì và khi nào nên dùng?

**JDBC batch** gom nhiều lần thực thi một PreparedStatement (hoặc nhiều SQL statements theo biến thể khác) thành nhóm để driver/database có cơ hội giảm round trip và xử lý hiệu quả hơn.

Ví dụ có ba dòng hàng cần thêm:

~~~sql
INSERT INTO inventory(id, sku, price, stock, state)
VALUES (?, ?, ?, ?, ?);
~~~

Chạy từng lệnh với `JdbcClient.sql(...).param(...).update()` ba lần là hoàn toàn hợp lệ, nhưng có thể tạo ba lần thực thi đơn lẻ. `JdbcTemplate.batchUpdate` cho phép giao một danh sách bộ giá trị cho cùng SQL, driver có thể dùng cơ chế JDBC batch. Điều đó **không** có nghĩa batch là một câu SQL multi-row duy nhất, cũng không bảo đảm tốc độ luôn nhanh hơn: kết quả phụ thuộc driver, database, kích thước batch, index, lock và network.

### 3.1. Batch không tự đồng nghĩa transaction

Có hai khái niệm độc lập:

- **Batching:** nhóm thao tác theo cơ chế JDBC để tăng hiệu quả.
- **Transaction:** quy định tập thao tác nào commit/rollback cùng nhau.

Nếu ứng dụng dùng batch bên ngoài một transaction nghiệp vụ, driver/connection có thể chạy với autoCommit và có khả năng để lại thay đổi từng phần khi lỗi. Nếu toàn bộ nhóm phải atomic, đặt `@Transactional` ở service và dùng template cùng DataSource/transaction manager.

Ngược lại, `@Transactional` không tự gom nhiều call `update()` đơn lẻ thành JDBC batch. Transaction có thể bảo đảm commit/rollback mà vẫn phát sinh nhiều round trip. Chỉ khi chọn API batch mới có yêu cầu batching tương ứng.

### 3.2. Giá trị trả về int[] không luôn là số bản ghi chính xác

Các overload `batchUpdate` thường trả `int[]` hoặc `int[][]`. Phần tử có thể là:

- Số dòng bị ảnh hưởng (ví dụ `1` khi một INSERT thành công).
- `Statement.SUCCESS_NO_INFO` (thường `-2`): driver báo thao tác thành công nhưng không cung cấp số dòng.
- `Statement.EXECUTE_FAILED` (thường `-3`) trong ngữ cảnh driver báo trạng thái thất bại theo JDBC; một lỗi batch cũng có thể ném exception.

Không viết code production bắt buộc mọi phần tử phải bằng `1` mà không hiểu driver hoặc yêu cầu nghiệp vụ. Trong trường hợp cần bảo đảm chính xác, kết hợp unique key, kiểm tra dữ liệu sau batch hoặc test integration với database đang dùng.

## 4. Ba lựa chọn batch trên template

### 4.1. JdbcTemplate + BatchPreparedStatementSetter

Phù hợp khi câu SQL dùng dấu `?` và cần kiểm soát setter JDBC cho mỗi phần tử:

~~~java
int[] affected = jdbc.batchUpdate("""
        UPDATE inventory SET stock = ? WHERE id = ?
        """, new BatchPreparedStatementSetter() {
    @Override
    public void setValues(PreparedStatement ps, int index)
            throws SQLException {
        StockAdjustment item = changes.get(index);
        ps.setInt(1, item.newStock());
        ps.setLong(2, item.id());
    }

    @Override
    public int getBatchSize() {
        return changes.size();
    }
});
~~~

Đây là **method-body minh họa**: cần biến `JdbcTemplate jdbc`, danh sách `changes` và record `StockAdjustment` do ứng dụng tự định nghĩa. `BatchPreparedStatementSetter` thuộc `org.springframework.jdbc.core`. Mỗi lần `setValues` chỉ bind tham số cho một phần tử, không tự gọi `executeUpdate()`; template điều phối batch.

Ưu điểm: kiểu JDBC rõ ràng, thứ tự placeholder chủ động, dễ dùng `setNull` khi cần. Nhược điểm: nhiều mã hơn named parameters; thứ tự các `?` phải khớp chính xác với thứ tự setter.

### 4.2. NamedParameterJdbcTemplate + SqlParameterSource[]

Khi SQL có nhiều tham số, cách theo tên dễ đọc hơn:

~~~java
SqlParameterSource[] batch = ids.stream()
        .map(id -> (SqlParameterSource) new MapSqlParameterSource()
                .addValue("id", id, Types.BIGINT)
                .addValue("state", "READY", Types.VARCHAR))
        .toArray(SqlParameterSource[]::new);

int[] updated = namedJdbc.batchUpdate(
        "UPDATE inventory SET state = :state WHERE id = :id",
        batch);
~~~

Đây là **đoạn minh họa** trong class có `NamedParameterJdbcTemplate namedJdbc`, `List<Long> ids` và các import `MapSqlParameterSource`, `SqlParameterSource`, `Types`. Một phần tử `SqlParameterSource` mô tả một lần thực thi SQL.

Ưu điểm: giảm nhầm tham số, có thể khai báo `java.sql.Types` và typed NULL. `SqlParameterSourceUtils.createBatch(...)` cũng giúp tạo batch từ các bean/Map có property trùng tên, nhưng khi cần SQL type đặc thù, hãy kiểm tra metadata được sinh và có thể tạo MapSqlParameterSource thủ công để rõ ràng.

### 4.3. Batch theo chunk kích thước giới hạn

Khi có hàng chục nghìn đối tượng, API sau giúp chia thành các nhóm:

~~~java
int[][] results = jdbc.batchUpdate(
        "UPDATE inventory SET stock = ? WHERE id = ?",
        changes,
        200,
        (ps, item) -> {
            ps.setInt(1, item.newStock());
            ps.setLong(2, item.id());
        });
~~~

Đây là **minh họa trong repository**, với `changes` là `Collection<StockAdjustment>`. Overload có kiểu `batchUpdate(String sql, Collection<T> batchArgs, int batchSize, ParameterizedPreparedStatementSetter<T> pss)` và trả `int[][]` vì có nhiều chunk. Mỗi chunk tối đa 200 mục; chunk cuối có thể nhỏ hơn. Điều này giảm kích thước một JDBC batch, nhưng nếu toàn bộ 50.000 dòng nằm trong **một @Transactional**, transaction vẫn kéo dài qua các chunk. Cần thiết kế ranh giới commit/rollback theo yêu cầu nhất quán và tải hệ thống, không coi chunk size là transaction size.

## 5. Ví dụ hoàn chỉnh: cùng một repository dùng JdbcClient và template

Ta sẽ xây ứng dụng console Java 21, Spring Boot 3.3.5 (Spring Framework 6.1.x) và H2. Phần đọc dùng **JdbcClient**, phần INSERT batch dùng **JdbcTemplate**, phần UPDATE batch theo tên dùng **NamedParameterJdbcTemplate**, phần đọc metadata dùng **ConnectionCallback**. Các API này dùng cùng JdbcTemplate do Spring Boot inject.

Bài toán: nhập 3 mặt hàng vào bảng inventory, đánh dấu sản phẩm #1 và #3 thành READY, đọc hàng READY qua fluent JdbcClient, sau đó thử một batch thất bại và quan sát rollback. Tất cả chỉ là demo trong bộ nhớ, không cần server database riêng.

### 5.1. Cấu trúc project

~~~text
jdbcclient-template-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/fallback/
    │   ├── FallbackApplication.java
    │   ├── StockItem.java
    │   ├── InventoryRepository.java
    │   └── InventoryService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'jdbcclient-template-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:fallbackdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    stock INTEGER NOT NULL,
    state VARCHAR(16) NOT NULL
);
~~~

Đây là bảng thử nghiệm có khóa chính id. Trong môi trường thực nên bổ sung CHECK cho price, stock, state khi phù hợp, xử lý SKU unique và lựa chọn precision/scale đúng nghiệp vụ. Ở demo, ID được chỉ định chủ động để stdout dễ dự đoán, không cần phụ thuộc generated keys.

### 5.2. Kiểu dữ liệu ứng dụng

Tệp `src/main/java/example/fallback/StockItem.java`:

~~~java
package example.fallback;

import java.math.BigDecimal;

public record StockItem(
        long id,
        String sku,
        BigDecimal price,
        int stock,
        String state) {
}
~~~

Record này dùng chung làm input của batch và DTO đọc từ database. Ở ứng dụng thật, nên cân nhắc tách input command khỏi read DTO, nhất là khi có field được database cấp hoặc cần validation riêng. Bản record trong demo không mặc nhiên validate giá dương/stock không âm.

### 5.3. Repository gồm cả facade và template

Tệp `src/main/java/example/fallback/InventoryRepository.java`:

~~~java
package example.fallback;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.List;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    private static final String INSERT_SQL = """
            INSERT INTO inventory(id, sku, price, stock, state)
            VALUES (?, ?, ?, ?, ?)
            """;

    private final JdbcTemplate jdbc;
    private final NamedParameterJdbcTemplate namedJdbc;
    private final JdbcClient client;

    public InventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        this.namedJdbc = new NamedParameterJdbcTemplate(jdbc);
        this.client = JdbcClient.create(jdbc);
    }

    public int[] insertBatch(List<StockItem> items) {
        return jdbc.batchUpdate(INSERT_SQL, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int index)
                    throws SQLException {
                StockItem item = items.get(index);
                ps.setLong(1, item.id());
                ps.setString(2, item.sku());
                ps.setBigDecimal(3, item.price());
                ps.setInt(4, item.stock());
                ps.setString(5, item.state());
            }

            @Override
            public int getBatchSize() {
                return items.size();
            }
        });
    }

    public int[] updateStateBatch(List<Long> ids, String state) {
        SqlParameterSource[] params = new SqlParameterSource[ids.size()];
        for (int index = 0; index < ids.size(); index++) {
            params[index] = new MapSqlParameterSource()
                    .addValue("id", ids.get(index), Types.BIGINT)
                    .addValue("state", state, Types.VARCHAR);
        }

        return namedJdbc.batchUpdate("""
                UPDATE inventory
                SET state = :state
                WHERE id = :id
                """, params);
    }

    public List<StockItem> findByState(String state) {
        return client.sql("""
                SELECT id, sku, price, stock, state
                FROM inventory
                WHERE state = :state
                ORDER BY id
                """)
                .param("state", state)
                .query((rs, rowNumber) -> new StockItem(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getBigDecimal("price"),
                        rs.getInt("stock"),
                        rs.getString("state")))
                .list();
    }

    public long countAll() {
        return client.sql("SELECT COUNT(*) FROM inventory")
                .query(Long.class)
                .single();
    }

    public String databaseName() {
        return jdbc.execute((ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
    }
}
~~~

**Đọc kỹ ba đường đi:**

1. **INSERT batch bằng JdbcTemplate.** `BatchPreparedStatementSetter` đưa các giá trị theo thứ tự vị trí; template chuẩn bị JDBC Statement, thực thi batch và cleanup. Callback setter không tự gọi `executeBatch()` hoặc `close()`. `int[]` là kết quả báo cáo từ JDBC driver.
2. **UPDATE batch bằng NamedParameterJdbcTemplate.** Mỗi ID có một `MapSqlParameterSource` với kiểu `BIGINT` và `VARCHAR`. Spring mở rộng tên `:id`, `:state` thành các bind vị trí và thực hiện batch.
3. **SELECT bằng JdbcClient.** API fluent thích hợp với truy vấn đọc đơn giản và RowMapper. Nó trả `List<StockItem>` đã đọc xong, không trả raw ResultSet.

Method `countAll()` minh họa truy vấn một scalar với facade. Method `databaseName()` cho thấy khi cần `DatabaseMetaData`, ta có thể quay về `JdbcTemplate.execute(ConnectionCallback<T>)` mà không tự mở raw Connection từ pool. Connection được template quản lý; callback không đóng Connection.

### 5.4. Service đảm bảo transaction cho batch

Tệp `src/main/java/example/fallback/InventoryService.java`:

~~~java
package example.fallback;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void createAndPromote() {
        List<StockItem> items = List.of(
                new StockItem(1L, "SKU-001",
                        new BigDecimal("12.50"), 3, "NEW"),
                new StockItem(2L, "SKU-002",
                        new BigDecimal("22.00"), 5, "NEW"),
                new StockItem(3L, "SKU-003",
                        new BigDecimal("30.00"), 1, "NEW"));

        int[] inserted = repository.insertBatch(items);
        if (inserted.length != items.size()) {
            throw new IllegalStateException("Batch INSERT thiếu kết quả");
        }

        int[] updated = repository.updateStateBatch(
                List.of(1L, 3L), "READY");
        if (updated.length != 2) {
            throw new IllegalStateException("Batch UPDATE thiếu kết quả");
        }
    }

    @Transactional
    public void demonstrateRollback() {
        repository.insertBatch(List.of(
                new StockItem(9L, "SKU-009",
                        new BigDecimal("9.00"), 2, "NEW"),
                new StockItem(10L, "SKU-010",
                        new BigDecimal("10.00"), 4, "NEW")));

        throw new IllegalStateException("Cố tình rollback");
    }
}
~~~

`@Transactional` đặt ở service, bao phủ các lời gọi repository dùng cả JdbcTemplate lẫn NamedParameterJdbcTemplate. Vì chúng cùng dùng một JdbcTemplate/DataSource, các SQL tham gia transaction Spring đang active. Nếu exception unchecked thoát khỏi service, Spring rollback theo quy tắc mặc định.

Đoạn kiểm tra `inserted.length` chỉ xác minh driver trả một mục kết quả cho mỗi phần tử; nó **không** chứng minh mọi hàng bị ảnh hưởng đúng một dòng. Trong production, điều kiện nghiệp vụ có thể cần kiểm tra thêm từng count và dữ liệu thực tế; nhớ rằng JDBC cho phép `SUCCESS_NO_INFO`. Trong demo H2 với khóa chính rõ ràng, các insert hợp lệ theo dữ liệu mẫu.

### 5.5. Runner và stdout

Tệp `src/main/java/example/fallback/FallbackApplication.java`:

~~~java
package example.fallback;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(FallbackApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            InventoryService service,
            InventoryRepository repository) {
        return args -> {
            service.createAndPromote();

            System.out.println("Database: " + repository.databaseName());

            List<StockItem> ready = repository.findByState("READY");
            System.out.println("READY: " + ready.size());
            for (StockItem item : ready) {
                System.out.printf(
                        "%d | %s | %s | %d | %s%n",
                        item.id(),
                        item.sku(),
                        item.price().toPlainString(),
                        item.stock(),
                        item.state());
            }

            try {
                service.demonstrateRollback();
            } catch (IllegalStateException expected) {
                System.out.println("Đã yêu cầu rollback");
            }

            System.out.println("Tổng sau rollback: "
                    + repository.countAll());
            System.out.println("NEW sau rollback: "
                    + repository.findByState("NEW").size());
        };
    }
}
~~~

Chạy với **JDK 21 và Gradle tương thích Java 21** (ví dụ Gradle 8.5), từ thư mục `jdbcclient-template-demo`:

~~~bash
gradle bootRun
~~~

Các dòng chương trình in ra (bỏ qua thông báo của Gradle/Spring):

~~~text
Database: H2
READY: 2
1 | SKU-001 | 12.50 | 3 | READY
3 | SKU-003 | 30.00 | 1 | READY
Đã yêu cầu rollback
Tổng sau rollback: 3
NEW sau rollback: 1
~~~

**Giải thích kết quả:** batch đầu tiên thêm ba dòng, UPDATE batch đổi state của #1 và #3 thành READY. JdbcClient tìm đúng hai dòng READY. Lần tiếp theo batch INSERT hai dòng #9 và #10, nhưng service ném `IllegalStateException`; Spring rollback transaction đó. Database còn ba dòng ban đầu, chỉ có #2 vẫn NEW.

Đây là kết quả dự kiến khi chương trình chạy trong một tiến trình mới với H2 trống và cấu hình đã nêu. Ví dụ có đầy đủ class/file và không cần cài database riêng. Các đoạn minh họa độc lập ngoài mục 5 **không** phải mã chạy cùng project trừ khi được tích hợp thêm.

## 6. Kiểm soát transaction khi kết hợp các API

Dùng JdbcClient cùng template **không làm transaction bị chia** nếu cả hai dùng cùng DataSource/transaction manager và được gọi qua một transaction Spring hợp lệ. Trong demo:

~~~text
CommandLineRunner
       |
       v
InventoryService.createAndPromote()
       |
       +-- @Transactional proxy mở transaction
       |
       +-- InventoryRepository.insertBatch()
       |      -> JdbcTemplate -> Connection trong transaction
       |
       +-- InventoryRepository.updateStateBatch()
       |      -> NamedParameterJdbcTemplate
       |      -> cùng JDBC transaction resource
       |
       +-- service kết thúc bình thường
              -> commit
~~~

Một số sai lầm có thể phá giả định này:

- **Pool khác nhau:** một JdbcTemplate trỏ DataSource A, một NamedParameterJdbcTemplate trỏ DataSource B. Hai pool có thể dùng cùng URL database mà vẫn là hai Connection/transaction độc lập.
- **Raw Connection:** mở `dataSource.getConnection()` trực tiếp từ pool gốc bên trong transaction có thể tạo Connection khác và auto-commit riêng. Khi cần API thấp, hãy dùng `JdbcTemplate.execute(ConnectionCallback<T>)` hoặc `DataSourceUtils` đúng cách.
- **Self-invocation:** với Spring proxy mode thường gặp, một method của service tự gọi method `@Transactional` khác trong cùng object có thể bỏ qua proxy.
- **Thread khác:** transaction JDBC đồng bộ thường gắn với luồng đang thực thi. `@Async`, executor hoặc thread mới không tự kế thừa transaction.
- **Bắt rồi nuốt exception:** nếu service bắt lỗi rồi trả thành công, transaction interceptor có thể commit dù một bước nghiệp vụ đã thất bại.
- **Propagation.REQUIRES_NEW:** transaction được chủ động tách ra sẽ commit/rollback riêng; không phải giải pháp để “bắt tất cả batch cùng rollback”.
- **Database khác:** transaction manager JDBC cục bộ không tự tạo distributed transaction trên nhiều database.

**Phân biệt atomicity và throughput:** batch tối ưu cách gửi thao tác SQL; transaction quyết định điểm commit và tính nhất quán. Cả hai cần được thiết kế, không thay thế nhau.

## 7. Spring Framework 7.1: JdbcClient đã có fluent batch

Ở phiên bản hỗ trợ API mới, bạn có thể viết một batch đơn giản **ngay trên facade**:

~~~java
int[] affected = client.sql("""
        INSERT INTO inventory(id, sku, price, stock, state)
        VALUES (:id, :sku, :price, :stock, :state)
        """)
        .batch()
        .entry(e -> e.param("id", 11L)
                .param("sku", "SKU-011")
                .param("price", new BigDecimal("11.00"))
                .param("stock", 2)
                .param("state", "NEW"))
        .entry(e -> e.param("id", 12L)
                .param("sku", "SKU-012")
                .param("price", new BigDecimal("12.00"))
                .param("stock", 1)
                .param("state", "NEW"))
        .update();
~~~

**Đây là ví dụ theo API Spring Framework 7.1, không phải code dùng được với Spring Boot 3.3.5 của mục 5.** Giả định class có trường `JdbcClient client` và import `BigDecimal`. `BatchSpec.entry(...)` mô tả từng lần bind, `update()` thực thi batch và trả `int[]`. API còn có `entries(...)` để truyền một danh sách parameter objects khi phù hợp.

Sự thay đổi này không làm kiến thức về template lỗi thời: JdbcTemplate và NamedParameterJdbcTemplate vẫn có các overload và callback phục vụ những thao tác khác như Statement control, Connection metadata, custom batch logic và stored procedure. Hãy cân nhắc ít nhất hai câu hỏi khi chọn API:

1. **Version hiện tại có hỗ trợ tính năng không?** Đọc Javadoc đúng version từ dependency tree, không đoán theo bài blog.
2. **Facade có đủ mức kiểm soát không?** Ngay cả khi hỗ trợ batch, một workflow cần các chi tiết JDBC đặc biệt vẫn có thể rõ và an toàn hơn với template.

Nếu nâng cấp project từ Spring 6.1 lên 7.1, không đổi dependency chỉ để thay một lời gọi batch cho đẹp. Đánh giá tương thích Spring Boot, Java baseline, driver, transaction, test và toàn bộ hệ thống trước khi quyết định nâng cấp.

## 8. Những thao tác chuyên biệt chưa phù hợp với fluent facade

### 8.1. ConnectionCallback: metadata và API cấp Connection

Khi cần biết tên database, đặc tính driver hoặc tạo SQL types đặc thù, dùng `JdbcTemplate.execute(ConnectionCallback<T>)`:

~~~java
String dbName = jdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
~~~

Đoạn này nằm trong repo có trường JdbcTemplate. Callback nhận Connection Spring quản lý, do đó được tham gia transaction nếu DataSource phù hợp. **Không gọi `connection.close()`, `commit()` hay `rollback()` trong callback**; đóng Statement/ResultSet do chính callback tạo, còn Spring release Connection. Cũng không trả Connection hoặc ResultSet ra ngoài callback.

### 8.2. PreparedStatementCallback cho thao tác trên statement

Nếu cần API JDBC nâng cao trên một statement (ví dụ đọc generated keys theo chế độ đặc biệt, lấy metadata của result set, sử dụng tùy chọn driver), `JdbcTemplate.execute(..., PreparedStatementCallback<T>)` cung cấp mức tiếp cận trực tiếp hơn. Phải phân biệt overload nhận `String sql` và các callback, và để Spring quản lý tài nguyên.

Ví dụ **chỉ minh họa callback trong một repository**, không phải file Java độc lập:

~~~java
String sql = "SELECT COUNT(*) FROM inventory";
Integer count = jdbc.execute(sql, ps -> {
    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new SQLException("COUNT không trả kết quả");
        }
        return rs.getInt(1);
    }
});
~~~

Với đúng bài toán COUNT(*), `queryForObject` hoặc JdbcClient vẫn tốt hơn: mẫu trên chỉ cho thấy callback khi thật sự cần thao tác trực tiếp trên PreparedStatement. Phải có import JDBC thích hợp và biến `JdbcTemplate jdbc`.

### 8.3. SimpleJdbcCall cho stored procedure

Khi có stored procedure chứa IN/OUT parameters hoặc metadata cần khai báo, `SimpleJdbcCall` là API Spring JDBC dành riêng cho use case này. Ví dụ cấu trúc sử dụng:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withProcedureName("recalculate_stock");

Map<String, Object> results =
        call.execute(Map.of("warehouse_id", 7L));
~~~

Đây là **ví dụ cấu trúc, không chạy được trên H2 demo**, vì chưa tạo stored procedure có tên này. Cần procedure thật, quyền EXECUTE, driver hỗ trợ metadata/parameter name và import `SimpleJdbcCall`, `Map`. Với database không trả metadata procedure đầy đủ, có thể cần `withoutProcedureColumnMetaDataAccess()` và `declareParameters(...)` một cách tường minh. Đừng cho rằng mọi vendor xử lý OUT parameter giống nhau.

### 8.4. SimpleJdbcInsert hoặc KeyHolder cho generated keys

Khi INSERT cần trả khóa tự sinh, `SimpleJdbcInsert` và template với `KeyHolder` có API phù hợp. Với JdbcClient phiên bản mới, xem overload `update(KeyHolder, ...)` ở API version thực tế. Đừng chỉ vì facade ngắn mà tự lấy Connection, chạy raw PreparedStatement và quên cleanup.

### 8.5. ResultSetExtractor và RowCallbackHandler

Khi cần tổng hợp nhiều hàng thành graph thay vì một DTO trên mỗi hàng, `ResultSetExtractor<T>` có thể thực hiện xử lý trực tiếp một ResultSet. Với xử lý từng hàng không giữ cả danh sách, `RowCallbackHandler` giúp xử lý streaming-style trong lúc ResultSet còn mở. Cần chú ý chi phí bộ nhớ và thời gian giữ Connection.

Một số overload/khả năng tùy version facade; khi mức kiểm soát chưa đủ, dùng template đúng nghĩa là chọn extension point đã có. Không trả một ResultSet hoặc stream gắn tài nguyên chưa đóng cho caller sau khi transaction kết thúc.

## 9. Cẩn thận với batch lớn, lỗi giữa batch và generated keys

### 9.1. Lựa chọn batch size theo tải

Batch quá nhỏ không giảm round trip đáng kể; quá lớn có thể gây áp lực bộ nhớ, lock lâu, timeout, giới hạn bind parameters hoặc packet size. Không có con số tối ưu chung. Có thể thử 100, 200, 500 hay 1.000 phần tử trong test rồi đo throughput, latency, memory và thời gian transaction trên driver/DB thật. Chunk theo kích thước không tự chia commit; muốn commit theo từng chunk phải thiết kế transaction boundary rõ ràng, biết đánh đổi atomicity.

### 9.2. Khả năng driver không hỗ trợ batch tối ưu

Spring JdbcTemplate có cơ chế fallback khi driver không hỗ trợ batching cho một số overload: nó có thể chạy từng update. Vì thế sử dụng batchUpdate không tự cam kết driver thực sự gửi batch hiệu quả. Kiểm tra DatabaseMetaData.supportsBatchUpdates(), driver version, datasource settings và đo kết quả thực tế. Một số driver có cờ optimization như rewrite batched statements; những cờ này phụ thuộc nhà cung cấp và không phải API Spring chung.

### 9.3. Exception và cập nhật từng phần

`DataAccessException` của Spring có thể bao bọc lỗi từ SQLException/BatchUpdateException. Tùy driver, thông tin update counts trước thời điểm lỗi có thể có hoặc không đầy đủ, và có thể đã có thay đổi trên database. Trong một transaction thực sự có rollback khi lỗi phù hợp thoát khỏi ranh giới, các thay đổi của transaction được hoàn tác theo tính chất database. Nếu không có transaction, không được giả định một batch lỗi sẽ rollback toàn bộ.

Không catch `DataAccessException` rồi trả thành công nếu dữ liệu đã ở trạng thái chưa xác định. Nếu nghiệp vụ cần retry, thiết kế key/idempotency, tránh tạo bản ghi trùng. Các ràng buộc UNIQUE, FK, CHECK của database vẫn phải được duy trì.

### 9.4. Generated keys theo batch

Lấy generated keys khi batch phụ thuộc API Spring và JDBC driver. Một số overload template nhận `KeyHolder`, nhưng thứ tự, số lượng khóa trả về và hỗ trợ driver có thể khác. Nếu nghiệp vụ cần ánh xạ chính xác khóa → phần tử đầu vào, phải test trực tiếp database/driver đích; không gán theo index chỉ dựa trên giả định. Trong ví dụ đầy đủ, ID được cung cấp rõ để tách trọng tâm **batch fallback** khỏi vấn đề generated keys.

### 9.5. Tính nhất quán và thứ tự thực thi

Batch thường gom nhiều lần thực thi SQL giống nhau, nhưng không nên dùng batch như thay thế cho việc thiết kế thứ tự nghiệp vụ, khóa đồng thời hoặc optimistic locking. Nếu update cùng ID nhiều lần trong một batch, kết quả cuối có thể phụ thuộc thứ tự, trigger và constraint. Với update cần tránh lost update, cân nhắc `WHERE id = ? AND version = ?` rồi xác nhận affected rows, kể cả khi dùng batch.

## 10. Chọn API bằng nguyên tắc tối giản có kiểm soát

Một repository dễ bảo trì không buộc phải “thuần” JdbcClient hoặc “thuần” JdbcTemplate. Có thể theo nguyên tắc:

1. **Mặc định JdbcClient** cho những truy vấn, update đơn lẻ có thể diễn đạt rõ trong phiên bản đang dùng.
2. **Dùng template khi công việc yêu cầu batch/callback/API đặc thù mà facade chưa đáp ứng hoặc không đủ kiểm soát.**
3. **Không tự mở raw Connection ngoài Spring transaction** chỉ để làm những việc template đã hỗ trợ.
4. **Tái sử dụng cùng DataSource/transaction configuration**, đặt transaction ở service.
5. **Cô lập chi tiết JDBC trong repository**; tầng nghiệp vụ gọi method có ý nghĩa như `insertBatch`, `promoteStateBatch`, `findReady`, không cần biết facade hay template.
6. **Kiểm thử hành vi và hiệu năng**, đừng đánh giá cách viết chỉ qua độ ngắn của code.
7. **Luôn kiểm tra version API**; batch trong JdbcClient 7.1 là ví dụ vì sao quy tắc không được đóng băng theo tài liệu cũ.

Một API public của repository có thể là:

~~~java
public interface StockStore {
    void insertMany(List<StockItem> items);
    void markReady(List<Long> ids);
    List<StockItem> findReady();
}
~~~

Đây là **interface minh họa**, giả định cùng package có record StockItem và import List. Implementation có quyền dùng các template khác nhau nhưng API tầng trên vẫn nhất quán. Nếu ứng dụng cần trả diagnostics (counts hoặc lỗi theo dòng), có thể dùng result object giàu thông tin hơn thay vì void.

## 11. Bảng quyết định khi đối mặt một tác vụ JDBC

| Tình huống | Hành động đề xuất | Kiểm chứng |
| --- | --- | --- |
| SELECT một danh sách theo status | JdbcClient fluent query | Mapping, ordering, empty result. |
| UPDATE một hàng theo ID | JdbcClient update | Affected rows, concurrency/version. |
| INSERT 500 dòng trên Spring 6.1 | JdbcTemplate.batchUpdate | Batch counts, transaction, driver support. |
| UPDATE hàng loạt theo named parameters | NamedParameterJdbcTemplate.batchUpdate | SqlParameterSource[], typed NULL, mapping key. |
| Batch đơn giản ở Spring 7.1 | Cân nhắc JdbcClient.batch() | Version và benchmark tương đương template. |
| Cần SQL ARRAY/vender metadata | ConnectionCallback / driver API | Resource cleanup, driver compatibility. |
| Cần stored procedure có OUT | SimpleJdbcCall | OUT mapping, metadata/permissions. |
| Cần generated keys số lượng lớn | Template/KeyHolder hoặc tính năng facade đúng version | Đủ khóa, map đúng đầu vào, rollback. |
| Cần xử lý 1 triệu dòng | Chunking/pagination/stream processing có lifecycle rõ | Pool, memory, lock, timeout. |
| Nhiều thao tác phải atomic | @Transactional tại service + cùng DataSource | Integration test rollback tất cả. |
| Nhiều DataSource | Thiết kế transaction manager cụ thể | Không giả định tự chia sẻ transaction. |

## 12. Kiểm thử và checklist thực hành

### Những test nên có

- **Happy path:** ba INSERT thành công; hai UPDATE thay đổi #1 và #3; JdbcClient trả hai READY đúng thứ tự.
- **Rollback:** INSERT batch hai hàng #9/#10 rồi ném RuntimeException; sau đó không tồn tại hai hàng mới.
- **Ràng buộc database:** batch có ID trùng hoặc stock vi phạm CHECK; quan sát exception, rollback và cách báo lỗi.
- **Empty input:** `insertBatch(List.of())`, `updateStateBatch(List.of(), ...)` nên có hành vi được định nghĩa; không tạo SQL `IN ()` hoặc tự giả định batch rỗng phát sinh một statement.
- **Affected rows:** UPDATE một ID không tồn tại có thể trả 0; code nghiệp vụ cần định nghĩa có xem là lỗi không.
- **Tài nguyên:** Statement/ResultSet/Connection được Spring quản lý; không leak, không trả JDBC handle ra ngoài.
- **Version matrix:** chạy compile test trên version Spring đang dùng; không gọi JdbcClient.batch() nếu dependency chưa tới 7.1.
- **Hiệu năng:** đo batch size và round trip trên database thật, không so số dòng demo H2 rồi kết luận production.
- **Concurrency:** optimistic locking/unique constraints vẫn hoạt động với batch.
- **Khả năng quan sát:** phân biệt lỗi mapping/binding, exception SQL, deadlock/timeout và lỗi nghiệp vụ; log thông tin cần thiết mà không làm lộ dữ liệu nhạy cảm.

### Những câu hỏi tự kiểm tra

1. Vì sao JdbcClient có thể dùng cùng transaction với JdbcTemplate?
2. Batch và transaction khác nhau ở điểm nào? Một batch có tự rollback tất cả khi lỗi không?
3. Vì sao nói “JdbcClient không hỗ trợ batch” là nhận định thiếu điều kiện phiên bản?
4. Ở Spring Boot 3.3.5, lựa chọn batch nào trong bài có thể chạy?
5. Khi nào dùng BatchPreparedStatementSetter, khi nào dùng SqlParameterSource[]?
6. Vì sao `int[]` trả về từ batchUpdate có thể chứa `SUCCESS_NO_INFO` thay vì số 1?
7. Nếu phải lấy Connection metadata, vì sao nên gọi JdbcTemplate.execute(ConnectionCallback) hơn tự lấy raw Connection từ pool?
8. Nếu thao tác cần stored procedure OUT parameter, lớp nào của Spring JDBC phù hợp hơn?
9. Vì sao chunk theo 200 phần tử không tự tạo 200 giao dịch độc lập?
10. Khi đổi Spring Framework lên 7.1, điều gì nên kiểm thử trước khi thay template batch bằng JdbcClient.batch()?

**Kết luận:** JdbcClient cải thiện khả năng đọc code cho SQL thông dụng, nhưng **không thay thế toàn bộ Spring JDBC**. Trên Spring 6.1/6.2, batch là lý do điển hình để dùng JdbcTemplate/NamedParameterJdbcTemplate; từ Spring 7.1 có thể dùng fluent batch cho trường hợp phù hợp. Những việc chuyên biệt khác vẫn cần template, callback hoặc SimpleJdbcCall/Insert. Hãy chọn API theo **version, mức kiểm soát, transaction/resource lifecycle và yêu cầu thực tế**, không theo mong muốn mọi thao tác phải dùng một facade duy nhất.

### Tài liệu tham khảo

- Spring Framework 6.2 — JdbcClient Javadoc (mô tả việc quay về template với batch): https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework 7.1 — JDBC Core (fluent JdbcClient batch): https://docs.spring.io/spring-framework/reference/7.1/data-access/jdbc/core.html
- Spring Framework — JdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — NamedParameterJdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework — SimpleJdbcCall Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html
