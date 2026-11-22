# SimpleJdbcCall với procedure hoặc function

`SimpleJdbcCall` là API của **Spring JDBC** để gọi *stored procedure* hoặc *stored function* đã tồn tại trong cơ sở dữ liệu. Lớp này đóng gói phần lớn thao tác với JDBC `CallableStatement`: tạo chuỗi lệnh gọi, gán tham số `IN`, đăng ký tham số `OUT`/`INOUT`, thực thi và chuyển kết quả về Java. Nó đặc biệt hữu ích khi hệ thống đã đặt một phần xử lý dữ liệu vào stored routine và ứng dụng Spring cần gọi chúng qua một hợp đồng rõ ràng.

Mục tiêu của bài: phân biệt procedure và function; biết lúc nào dùng `withProcedureName(...).execute(...)` hoặc `withFunctionName(...).executeFunction(...)`; khai báo và đọc tham số đúng; hiểu cách phụ thuộc JDBC metadata, transaction, kiểu SQL và hệ quản trị cơ sở dữ liệu.

## 1. Hai loại stored routine và kết quả của chúng

**Stored procedure** là một routine phía database được gọi như một thao tác. Tùy hệ CSDL, procedure có thể đọc/ghi dữ liệu, trả tham số `OUT`/`INOUT`, tạo `ResultSet` hoặc thực hiện nhiều câu lệnh. Ví dụ: `reserve_stock(sku, quantity, OUT reserved)` giữ tồn kho và cho biết có cập nhật được bản ghi hay không.

**Stored function** là routine trả về một giá trị thông qua cơ chế `RETURN` của database. Ví dụ: `stock_left(sku)` trả số lượng tồn hiện tại. Quy định về SQL được phép dùng trong function, tính quyết định (*determinism*) và tác động giao dịch tùy DBMS.

| Tiêu chí | Procedure | Function |
| --- | --- | --- |
| Cách cấu hình `SimpleJdbcCall` | `withProcedureName("reserve_stock")` | `withFunctionName("stock_left")` |
| Cách thực thi điển hình | `execute(Map / SqlParameterSource / args)` | `executeFunction(Integer.class, inputs)` |
| Kết quả Java điển hình | `Map<String, Object>` chứa các giá trị `OUT`/`INOUT` và kết quả được ánh xạ | Giá trị trả về được ép/đọc theo `Class<T>` yêu cầu |
| Tham số | `IN`, `OUT`, `INOUT` theo hỗ trợ DBMS | Thường nhận `IN`; giá trị `RETURN` là kết quả chính |
| Khi cần một giá trị `OUT` | Có thể dùng `executeObject(T.class, ...)` cho procedure phù hợp | Dùng `executeFunction(T.class, ...)` |
| Kiểu lệnh JDBC | Tương đương `{call proc(?, ...)}` | Tương đương `{? = call func(?, ...)}` |

Đây là **khác biệt về hợp đồng gọi**, không phải cam kết procedure luôn ghi dữ liệu hay function luôn đọc dữ liệu. Khi thiết kế, hãy xem định nghĩa routine thực tế của database.

### Luồng xử lý bên trong

1. Lập cấu hình `SimpleJdbcCall`: datasource/`JdbcTemplate`, tên routine, schema/catalog nếu cần, danh sách tham số hoặc metadata.
2. `SimpleJdbcCall` được *compile* lúc `compile()` hoặc tự compile ở lần `execute(...)` đầu tiên: xây dựng call string và danh sách tham số cần gán/đăng ký. Đây là **compile cấu hình lệnh gọi**, không phải biên dịch SQL routine từ Java.
3. Spring dùng JDBC `CallableStatement` trên một `Connection` do `DataSource` quản lý, bind giá trị `IN` rồi thực thi.
4. Spring đọc `OUT`/`INOUT`, function return và các tập kết quả được khai báo để tạo `Map` hoặc một giá trị Java.

Sau khi được cấu hình và compile, đối tượng `SimpleJdbcCall` có thể tái sử dụng giữa nhiều lời gọi/luồng. Thông thường xây dựng nó một lần ở DAO/repository hoặc Spring bean; **không sửa cấu hình trong lúc đang được sử dụng**.

## 2. Các API cần nhớ

| API | Vai trò |
| --- | --- |
| `new SimpleJdbcCall(dataSource)` hoặc `new SimpleJdbcCall(jdbcTemplate)` | Tạo đối tượng gọi routine |
| `withProcedureName(name)` | Đánh dấu lời gọi là procedure |
| `withFunctionName(name)` | Đánh dấu lời gọi là function |
| `withSchemaName(name)` / `withCatalogName(name)` | Xác định namespace khi routine không được tìm bằng tên mặc định; ngữ nghĩa schema/catalog phụ thuộc driver |
| `declareParameters(...)` | Khai báo hợp đồng tham số phía Java |
| `withoutProcedureColumnMetaDataAccess()` | Không tự đọc metadata cột tham số, chỉ sử dụng khai báo thủ công |
| `execute(Map)` / `execute(SqlParameterSource)` | Gọi routine, nhận map chứa `OUT`/`INOUT`/kết quả đã khai báo |
| `executeFunction(T.class, ...)` | Gọi function và lấy giá trị `RETURN` kiểu `T` |
| `executeObject(T.class, ...)` | Tiện ích lấy một `OUT` duy nhất của procedure phù hợp |
| `returningResultSet(name, rowMapper)` | Khai báo ánh xạ một tập bản ghi do routine trả về |
| `withNamedBinding()` | Yêu cầu JDBC binding theo tên khi driver hỗ trợ; khác với việc dùng map để cung cấp tham số |

Các lớp tham số:

- `new SqlParameter("p_sku", Types.VARCHAR)` khai báo tham số đầu vào `IN`.
- `new SqlOutParameter("p_done", Types.INTEGER)` khai báo tham số đầu ra `OUT`.
- `new SqlInOutParameter("p_count", Types.INTEGER)` khai báo tham số vừa nhận vừa trả `INOUT`.
- `MapSqlParameterSource` truyền giá trị theo **tên tham số ứng dụng đã khai báo**, giúp hạn chế nhầm thứ tự. Với JDBC binding mặc định, Spring vẫn sắp tham số đúng vị trí để gọi driver.
- `Types.INTEGER`, `Types.VARCHAR`, `Types.DECIMAL`... là SQL type trong `java.sql.Types`, **không phải** các lớp Java `Integer`, `String`, `BigDecimal`. Kiểu khai báo phải khớp routine và JDBC driver.

**Lưu ý:** `SqlOutParameter` không được dùng làm nguồn giá trị đầu vào khi thực thi `SimpleJdbcCall`; đối với giá trị vừa vào vừa ra hãy dùng `SqlInOutParameter`.

## 3. Ví dụ Java 17+ chạy được với MySQL: một procedure và một function

Ví dụ sau có đúng **một procedure cập nhật tồn kho và trả `OUT`** và **một function đọc tồn kho và trả giá trị scalar**. Chọn MySQL 8.4 vì MySQL hỗ trợ rõ ràng `IN`/`OUT` cùng stored SQL function; cú pháp procedure/function thay đổi giữa các DBMS.

### 3.1. Dựng dữ liệu và routines

Tạo file `schema.sql`:

```sql
DROP PROCEDURE IF EXISTS reserve_stock;
DROP FUNCTION IF EXISTS stock_left;
DROP TABLE IF EXISTS inventory;

CREATE TABLE inventory (
    sku VARCHAR(32) PRIMARY KEY,
    available INT NOT NULL
);

INSERT INTO inventory (sku, available)
VALUES ('BOOK', 5);

DELIMITER //

CREATE PROCEDURE reserve_stock(
    IN p_sku VARCHAR(32),
    IN p_amount INT,
    OUT p_done INT
)
MODIFIES SQL DATA
BEGIN
    IF p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Quantity must be positive';
    END IF;

    UPDATE inventory
       SET available = available - p_amount
     WHERE sku = p_sku
       AND available >= p_amount;

    SET p_done = ROW_COUNT();
END//

CREATE FUNCTION stock_left(p_sku VARCHAR(32))
RETURNS INT
READS SQL DATA
BEGIN
    DECLARE v_available INT DEFAULT 0;

    SELECT COALESCE(MAX(available), 0)
      INTO v_available
      FROM inventory
     WHERE sku = p_sku;

    RETURN v_available;
END//

DELIMITER ;
```

Giải thích: procedure `reserve_stock` chỉ giảm số lượng khi còn đủ hàng; `ROW_COUNT()` được lấy ngay sau `UPDATE`. Vì `p_amount` phải dương và câu `UPDATE` tác động vào đúng SKU khóa chính, `p_done = 1` nghĩa là đã giữ được hàng, còn `0` nghĩa là chưa cập nhật hàng nào. Với lỗi SQL, nó ném lỗi thay vì trả một cờ thành công giả. Function `stock_left` đọc tồn kho, trả `0` nếu SKU không có bản ghi. Ví dụ này chưa mô hình hóa toàn bộ nghiệp vụ đặt hàng.

`DELIMITER //` là **lệnh của chương trình dòng lệnh `mysql`** để tránh dấu `;` bên trong `BEGIN ... END` kết thúc định nghĩa quá sớm; không phải câu SQL gửi nguyên xi qua JDBC. Trên một SQL migration tool, sử dụng cơ chế định nghĩa routine riêng của công cụ.

### 3.2. Cấu hình dự án

Tạo `settings.gradle`:

```groovy
rootProject.name = 'simple-jdbc-call-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.mysql:mysql-connector-j:9.4.0'
}

application {
    mainClass = 'SimpleJdbcCallDemo'
}
```

Sử dụng **JDK 17 trở lên** và Gradle tương thích Java 17. JDBC driver được tải bằng Gradle, nên có thể chạy qua `gradle run` mà không phải tự liệt kê từng JAR trên classpath. Ở hệ thống có Gradle Wrapper, dùng `./gradlew run` hoặc `gradlew.bat run` tương ứng.

### 3.3. Code Java hoàn chỉnh

Tạo `src/main/java/SimpleJdbcCallDemo.java`:

```java
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class SimpleJdbcCallDemo {
    private SimpleJdbcCallDemo() {
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("com.mysql.cj.jdbc.Driver");
        dataSource.setUrl(
            "jdbc:mysql://127.0.0.1:3307/simple_call_demo" +
            "?sslMode=DISABLED&allowPublicKeyRetrieval=true"
        );
        dataSource.setUsername("root");
        dataSource.setPassword("demo");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setResultsMapCaseInsensitive(true);

        SimpleJdbcCall reserveStock = new SimpleJdbcCall(jdbc)
            .withProcedureName("reserve_stock")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlParameter("p_sku", Types.VARCHAR),
                new SqlParameter("p_amount", Types.INTEGER),
                new SqlOutParameter("p_done", Types.INTEGER)
            );

        SimpleJdbcCall stockLeft = new SimpleJdbcCall(jdbc)
            .withFunctionName("stock_left")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlOutParameter("return_value", Types.INTEGER),
                new SqlParameter("p_sku", Types.VARCHAR)
            );

        System.out.println("Before: " + remaining(stockLeft, "BOOK"));

        int success = reserve(reserveStock, "BOOK", 2);
        System.out.println("Reserve 2: " + success);
        System.out.println("After reserve: " + remaining(stockLeft, "BOOK"));

        int insufficient = reserve(reserveStock, "BOOK", 10);
        System.out.println("Reserve 10: " + insufficient);
        System.out.println("After insufficient: " + remaining(stockLeft, "BOOK"));
    }

    private static int reserve(
        SimpleJdbcCall procedure,
        String sku,
        int quantity
    ) {
        MapSqlParameterSource input = new MapSqlParameterSource()
            .addValue("p_sku", sku)
            .addValue("p_amount", quantity);

        Map<String, Object> output = procedure.execute(input);
        Object raw = output.get("p_done");
        if (!(raw instanceof Number number)) {
            throw new IllegalStateException(
                "Expected numeric OUT parameter p_done, got: " + raw
            );
        }
        return number.intValue();
    }

    private static int remaining(SimpleJdbcCall function, String sku) {
        Integer value = function.executeFunction(
            Integer.class,
            new MapSqlParameterSource().addValue("p_sku", sku)
        );
        if (value == null) {
            throw new IllegalStateException(
                "Function stock_left unexpectedly returned NULL"
            );
        }
        return value;
    }
}
```

Trong bài này, `DriverManagerDataSource` phục vụ demo nhỏ: nó không phải connection pool dành cho hệ thống tải cao. Giá trị `root/demo` và `sslMode=DISABLED` chỉ dành cho **MySQL cục bộ dùng để học**, không dùng làm cấu hình triển khai thực tế.

Điểm quan trọng nhất của code:

1. Procedure nhận hai `IN` và một `OUT`; `execute(input)` trả map, sau đó đọc `p_done` như một số. **Không** gọi `executeFunction` cho procedure này.
2. Function có một đầu vào và một slot trả về. Trong chế độ khai báo thủ công, `SqlOutParameter("return_value", Types.INTEGER)` phải đứng **trước** các tham số đầu vào để ánh xạ vị trí JDBC `{? = call stock_left(?)}`. `executeFunction(Integer.class, input)` trả giá trị trực tiếp, không cần truy map.
3. `withoutProcedureColumnMetaDataAccess()` khiến Spring sử dụng đúng danh sách đã khai báo. Vì vậy tên/kiểu/vị trí của tham số trở thành hợp đồng cần giữ đồng bộ với định nghĩa SQL.
4. `setResultsMapCaseInsensitive(true)` giảm lỗi do driver/database thay đổi chữ hoa/chữ thường của tên tham số `OUT`. Việc dùng map ở đầu vào **không** có nghĩa driver đang dùng named binding; Spring có thể bind theo vị trí.
5. Cả hai đối tượng `SimpleJdbcCall` được tạo một lần rồi gọi lặp lại. Trong Spring thực tế nên đặt chúng trong bean/DAO, với `DataSource` do framework quản lý.

### 3.4. Chạy và đối chiếu kết quả

Dùng một MySQL 8.4 thử nghiệm. Ví dụ với Docker, tạo container cùng database `simple_call_demo`:

```bash
docker run --rm --name simplejdbc-mysql -d \
  -e MYSQL_ROOT_PASSWORD=demo \
  -e MYSQL_DATABASE=simple_call_demo \
  -p 3307:3306 mysql:8.4
```

Sau khi MySQL báo đã sẵn sàng, chạy script **một lần trước khi chạy Java**:

```bash
docker exec -i simplejdbc-mysql \
  mysql -uroot -pdemo simple_call_demo < schema.sql

gradle run --quiet
```

Trên Windows PowerShell, có thể chuyển nội dung file SQL qua pipe thay cho cú pháp `<` của Bash:

```powershell
Get-Content -Raw schema.sql |
    docker exec -i simplejdbc-mysql mysql -uroot -pdemo simple_call_demo

gradle run --quiet
```

Khi chạy với schema vừa tạo, **stdout của chương trình Java** là:

```text
Before: 5
Reserve 2: 1
After reserve: 3
Reserve 10: 0
After insufficient: 3
```

Lần đầu có 5 sản phẩm; giữ 2 thành công nên còn 3. Lần thứ hai yêu cầu 10 sản phẩm, `UPDATE` không tác động hàng nào nên `OUT p_done = 0` và số tồn vẫn bằng 3. Đây là kết quả của routine theo dữ liệu mẫu; trong nghiệp vụ thật cần xác định cách thể hiện “không đủ hàng” (kết quả 0, ngoại lệ domain hoặc trạng thái riêng).

Nếu chạy lại Java **mà không chạy lại `schema.sql`**, tồn kho đã bị thay đổi, nên stdout lần sau không còn giống ví dụ. Nếu script MySQL báo lỗi do quyền tạo function (đặc biệt khi bật binary log), hãy kiểm tra quyền `CREATE ROUTINE`/cấu hình MySQL ở môi trường thử nghiệm, thay vì sửa hợp đồng `SimpleJdbcCall` một cách tùy tiện.

## 4. Có thể để Spring tự đọc tham số từ metadata

Với driver/database hỗ trợ metadata đầy đủ, mã ngắn hơn:

```java
// Đặt trong DAO đã được truyền JdbcTemplate jdbc.
SimpleJdbcCall readStock = new SimpleJdbcCall(jdbc)
    .withFunctionName("stock_left");

Integer available = readStock.executeFunction(
    Integer.class,
    new MapSqlParameterSource().addValue("p_sku", "BOOK")
);
```

Đây là **đoạn trích minh họa đặt trong DAO**, không phải một file Java độc lập. Spring sẽ truy `DatabaseMetaData` do JDBC driver cung cấp để cố tìm routine và thứ tự/tên/kiểu tham số. Cách tự động này tiện khi metadata đáng tin cậy, quyền truy vấn metadata đầy đủ và routine không gây nhập nhằng.

Khi metadata không chính xác hoặc không thể truy cập:

- Dùng `withoutProcedureColumnMetaDataAccess().declareParameters(...)` để khai báo đúng toàn bộ tham số theo thứ tự của database.
- Nếu chỉ khai báo **một phần** tham số mà không tắt metadata, Spring có thể lấy phần còn lại từ driver. Vì vậy nên chọn rõ chiến lược và thử trên chính DB/driver triển khai.
- Với các routine cùng tên hoặc nhiều schema/catalog, chỉ rõ `withSchemaName`/`withCatalogName` nếu cần. Không mặc định mọi DB hiểu hai tên này giống nhau: ví dụ ở MySQL, tên database thường được driver thể hiện như *catalog*.
- Lỗi `Unable to determine the correct call signature`, sai vị trí `OUT`, sai tên hoặc `SQLException` từ JDBC thường cần kiểm tra **DDL của routine + metadata thực tế + thông tin tên/kiểu**, không suy luận từ mỗi dòng Java.
- `withNamedBinding()` yêu cầu driver hỗ trợ bind theo tên. Chỉ dùng khi đã xác minh driver/database; nhận `MapSqlParameterSource` không bắt buộc phải bật tùy chọn này.

## 5. Đọc kết quả `OUT`, `INOUT` và `ResultSet`

### Procedure có nhiều `OUT`

Giả sử database định nghĩa routine `read_profile(IN p_id, OUT p_name, OUT p_status)`, có thể khai báo:

```java
// Mã minh họa trong DAO; cần routine read_profile tương ứng trong DB.
SimpleJdbcCall readProfile = new SimpleJdbcCall(jdbc)
    .withProcedureName("read_profile")
    .withoutProcedureColumnMetaDataAccess()
    .declareParameters(
        new SqlParameter("p_id", Types.BIGINT),
        new SqlOutParameter("p_name", Types.VARCHAR),
        new SqlOutParameter("p_status", Types.VARCHAR)
    );

Map<String, Object> out = readProfile.execute(
    new MapSqlParameterSource().addValue("p_id", 42L)
);
String name = (String) out.get("p_name");
String status = (String) out.get("p_status");
```

Map trả về chứa các tham số đầu ra theo tên đã khai báo hoặc tên database cung cấp. Hãy đối chiếu kiểu và kiểm tra `null`; không giả định procedure luôn trả đủ giá trị nếu không tìm thấy bản ghi. Với **chỉ một OUT**, `executeObject(String.class, input)` có thể phù hợp để lấy giá trị trực tiếp.

### `INOUT` là giá trị đầu vào đồng thời là đầu ra

Nếu routine có tham số `INOUT p_counter INT`, dùng:

```java
// Mã minh họa; DB phải thực sự định nghĩa INOUT p_counter.
SimpleJdbcCall increment = new SimpleJdbcCall(jdbc)
    .withProcedureName("increment_counter")
    .withoutProcedureColumnMetaDataAccess()
    .declareParameters(
        new SqlInOutParameter("p_counter", Types.INTEGER)
    );

Map<String, Object> out = increment.execute(
    new MapSqlParameterSource().addValue("p_counter", 3)
);
Number updated = (Number) out.get("p_counter");
```

Đoạn này cần import `org.springframework.jdbc.core.SqlInOutParameter` và routine `increment_counter` tương ứng. Giá trị trả về phụ thuộc định nghĩa SQL; không tự cho rằng nó luôn là 4 nếu chưa biết routine xử lý thế nào.

### Routine trả về các dòng dữ liệu

Procedure có thể trả về một hoặc nhiều `ResultSet`. `returningResultSet(name, RowMapper)` giúp Spring ánh xạ từng hàng:

```java
// Giả sử procedure list_orders() phát sinh ResultSet gồm id, status.
record OrderRow(long id, String status) {}

SimpleJdbcCall listOrders = new SimpleJdbcCall(jdbc)
    .withProcedureName("list_orders")
    .returningResultSet(
        "orders",
        (rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getString("status")
        )
    );

Map<String, Object> out = listOrders.execute(Map.of());
@SuppressWarnings("unchecked")
List<OrderRow> rows = (List<OrderRow>) out.get("orders");
```

Đoạn trích này cần import `java.util.List`, `java.util.Map` và routine `list_orders` trả đúng cột. Cách nhận result set **khác nhau theo DBMS**:

- Với result set trả trực tiếp trong quá trình xử lý kết quả JDBC, tên `"orders"` là khóa trong map do Java tự đặt; với nhiều result set, thứ tự khai báo `returningResultSet` cần khớp thứ tự trả về.
- Với **REF CURSOR** ở các database hỗ trợ, có thể phải khai báo `OUT` đúng tên tham số cursor và SQL type thích hợp, ví dụ loại `Types.REF_CURSOR` khi driver hỗ trợ. Tên tham số không phải nhãn tùy ý.
- Việc ánh xạ bằng `RowMapper` chỉ xác định cách chuyển hàng thành object; nó không tự tạo routine hay xử lý vòng đời transaction thay ứng dụng.

## 6. Transaction, lỗi và ranh giới thành công

`SimpleJdbcCall` làm gọn thao tác JDBC, **không mở rộng phạm vi transaction một cách thần kỳ**. Nếu được gọi qua cùng `DataSource` trong một Spring `@Transactional` đang hoạt động, routine thông thường sử dụng connection thuộc transaction đó. Tuy nhiên, một số routine/DBMS có lệnh tự commit, DDL hoặc quy tắc transaction riêng; phải xem định nghĩa và DBMS cụ thể.

Ví dụ service Spring:

```java
// Mã minh họa phương thức service; reserveStock là SimpleJdbcCall
// đã cấu hình trong DAO và được gọi qua Spring-managed bean.
@Transactional
public void reserveOrFail(String sku, int quantity) {
    int affected = repository.reserve(sku, quantity);
    if (affected != 1) {
        throw new IllegalStateException("OUT_OF_STOCK");
    }
}
```

Nếu phát sinh `DataAccessException` hay ngoại lệ runtime thoát khỏi phương thức `@Transactional` và lời gọi đi **qua Spring proxy**, Spring thường đánh dấu rollback theo quy tắc mặc định. Nếu routine tự thực hiện `COMMIT`, kết quả và khả năng rollback của ứng dụng phải đánh giá riêng. `OUT p_done=1` chỉ là tín hiệu do SQL routine định nghĩa, không chứng minh các khâu ngoài database như thanh toán hoặc gửi event đã hoàn thành.

Không nên dùng procedure name lấy trực tiếp từ input người dùng: tên routine được ghép vào lệnh gọi, còn **giá trị** tham số mới là phần được JDBC bind an toàn. Hạn chế quyền database chỉ ở các routine cần gọi, cân nhắc `SQL SECURITY DEFINER/INVOKER` theo thiết kế quyền truy cập và không ghi log dữ liệu nhạy cảm trong input/output.

## 7. Khi nào nên dùng `SimpleJdbcCall`, khi nào cân nhắc cách khác?

Dùng `SimpleJdbcCall` khi database đã cung cấp procedure/function ổn định, cần xử lý `IN`/`OUT`/`INOUT` hoặc muốn tái sử dụng cấu hình lời gọi có kiểm soát. Nó cũng hữu ích khi sử dụng JDBC trực tiếp và không cần ORM/JPA cho chức năng đó.

Nếu chỉ gọi một SQL scalar function đơn giản và không cần hợp đồng `CallableStatement`, một số DBMS cũng cho phép:

```java
// Ví dụ theo MySQL, khi chỉ cần đọc một giá trị.
Integer available = jdbc.queryForObject(
    "SELECT stock_left(?)",
    Integer.class,
    "BOOK"
);
```

Cách này có thể đơn giản hơn nhưng phụ thuộc cú pháp SQL của DBMS. Procedure có `OUT` hoặc nhiều `ResultSet` thường phù hợp hơn với `SimpleJdbcCall`/`CallableStatement`. Với logic thuần Java, không cần đặt lên DB chỉ để có lý do gọi stored routine; cân nhắc portability, observability, versioning và khả năng kiểm thử trước khi đưa nghiệp vụ vào DB.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy routine | Sai tên, schema/catalog, chữ hoa/thường, quyền `EXECUTE` | Kiểm tra DDL, namespace theo driver, quyền user kết nối |
| `OUT` luôn `null` hoặc sai key | Tên `OUT` khác, function return không được đăng ký, routine không gán giá trị | Đọc đúng map key, kiểm tra DDL; bật case-insensitive map nếu cần |
| Báo thiếu/sai parameter | JDBC metadata không khớp, sai SQL type hoặc thứ tự | Khai báo tường minh và tắt metadata, ưu tiên đối chiếu routine thật |
| Gọi function như procedure | Dùng `withProcedureName` và chờ `RETURN` như function | Chọn `withFunctionName` + `executeFunction` |
| Gọi procedure như function | Procedure có `OUT` nhưng dùng `executeFunction` | Dùng `execute`, hoặc `executeObject` nếu đúng một `OUT` |
| Map có nhiều kết quả khó hiểu | Procedure trả nhiều OUT/result set/update count | Khai báo `returningResultSet`, thống nhất thứ tự và tên kết quả |
| Chạy từng lần cho kết quả khác | Routine sửa dữ liệu; dữ liệu đầu vào đã thay đổi | Reset fixture trước mỗi integration test, tách rõ stateful/readonly |
| Transaction không rollback như dự kiến | Gọi ngoài proxy, khác `DataSource`, exception đã bị nuốt hoặc routine/DB tự commit | Kiểm tra ranh giới transaction, DDL, quy tắc rollback và connection |
| Thời gian gọi lớn | Routine chạy chậm, khóa chờ, truy vấn bên trong tốn chi phí | Dùng EXPLAIN/monitoring phía DB, transaction timeout và log độ trễ phù hợp |

Checklist kiểm thử tích hợp tốt cần dùng **chính DB/driver mục tiêu** và xác nhận: thứ tự `IN`/`OUT`, giá trị `null`, case tên tham số, dữ liệu đủ/thiếu, nhiều lời gọi đồng thời, số hàng bị sửa, commit/rollback, lỗi routine và permission. Unit test giả lập `SimpleJdbcCall` không thay thế được kiểm tra JDBC driver cùng stored routine thực tế.

## 9. Ghi nhớ khi áp dụng

- **Procedure:** `withProcedureName(...)` → khai báo `IN/OUT/INOUT` đúng DDL → `execute(...)` → đọc output map hoặc result set đã ánh xạ.
- **Function:** `withFunctionName(...)` → khai báo input/return (nếu tắt metadata) → `executeFunction(ReturnType.class, ...)` → nhận giá trị.
- **Metadata:** tiện khi driver phản ánh chính xác; nếu không tin cậy, `withoutProcedureColumnMetaDataAccess().declareParameters(...)` buộc Java mô tả đầy đủ đúng thứ tự/kiểu.
- **Kết quả:** output SQL cần được diễn giải theo hợp đồng nghiệp vụ; `OUT = 1` hay function trả giá trị không tự chứng minh các hệ thống khác đã thành công.
- **Triển khai:** giữ routine có version/migration, dùng một `DataSource` nhất quán với transaction, quyền DB tối thiểu, test với đúng DBMS/driver và tái sử dụng `SimpleJdbcCall` đã cấu hình.

### Tài liệu tham khảo

- [Spring Framework — Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html)
- [Spring Framework — SimpleJdbcCall API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [MySQL 8.4 — CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL Connector/J — Using CallableStatements](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html)
