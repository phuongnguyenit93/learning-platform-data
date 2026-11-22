# Khả năng lấy khóa phụ thuộc trình điều khiển và cơ sở dữ liệu

Khi chèn một bản ghi bằng Spring JDBC, ứng dụng thường cần biết `id` do cơ sở dữ liệu cấp để trả về cho API hoặc tạo bản ghi liên quan. Nhưng việc `INSERT` thành công **không đồng nghĩa** JDBC chắc chắn trả về khóa đã sinh. Kết quả phụ thuộc đồng thời vào cơ chế sinh giá trị của bảng, hệ quản trị cơ sở dữ liệu (DBMS), phiên bản JDBC driver, dạng câu SQL và cách ứng dụng yêu cầu lấy khóa.

Bài này tập trung vào **giới hạn và cách kiểm chứng khả năng lấy generated keys** trong `JdbcTemplate`, `KeyHolder` và `SimpleJdbcInsert`. Khóa sinh ở đây có thể là khóa chính kiểu số, UUID, hoặc một cột do `DEFAULT`/`IDENTITY`/sequence/trigger cấp giá trị. Không phải mọi giá trị do DB sinh đều được driver trả về như một generated key.

## 1. Phân biệt ba việc thường bị nhầm

1. **DB sinh khóa:** Ví dụ `orders.id` được cấp bởi cột identity. DB có thể tạo bản ghi hợp lệ mà ứng dụng không gửi `id`.
2. **Driver lấy được khóa:** Sau khi thực thi `INSERT`, JDBC driver phải hỗ trợ cơ chế thu nhận và trả kết quả qua `Statement.getGeneratedKeys()`. Hỗ trợ này khác nhau theo cặp DBMS + driver.
3. **Spring đọc được khóa:** Spring nhận kết quả từ driver rồi đưa vào `KeyHolder` hoặc trả về từ `SimpleJdbcInsert.executeAndReturnKey(...)`. Spring không thể tự tạo ra một khóa mà driver/SQL không trả về.

Ví dụ, `jdbcTemplate.update("INSERT ...", args...)` trả về **số hàng bị ảnh hưởng**, không phải `id` mới. Nếu phương thức trả `1`, đó chỉ là một hàng đã được cập nhật/chèn. Không dùng giá trị ấy làm khóa.

| Thành phần | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| Lược đồ DB | Xác định cột nào được sinh tự động | `IDENTITY`, sequence, `DEFAULT`, trigger, UUID; có thực sự sinh giá trị khi `INSERT` không? |
| DBMS | Quy định SQL và dữ liệu có thể trả về | Hỗ trợ `RETURNING`/`OUTPUT` hay cơ chế tương đương? |
| JDBC driver | Triển khai `prepareStatement`, `getGeneratedKeys` và ánh xạ kiểu | Có trả đúng cột, đúng số hàng, đúng kiểu cho thao tác này không? |
| Spring JDBC | Quản lý tài nguyên và bọc kết quả | Đã bật yêu cầu trả khóa và đọc `KeyHolder` đúng cách chưa? |

## 2. JDBC yêu cầu và trả khóa như thế nào?

JDBC hỗ trợ các cách tạo `PreparedStatement` có yêu cầu lấy generated keys:

~~~java
// Cách A: để driver quyết định khóa nào cần trả
PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO orders (description) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS);

// Cách B: chỉ rõ tên cột cần lấy (nếu driver hỗ trợ)
PreparedStatement psByName = connection.prepareStatement(
        "INSERT INTO orders (description) VALUES (?)",
        new String[] {"id"});
~~~

Đây là hai **phương án minh họa**, không phải hai biến cần khởi tạo cùng lúc trong một câu lệnh chèn. Thực thi `executeUpdate()` rồi đọc `ps.getGeneratedKeys()` trước khi đóng statement. `getGeneratedKeys()` trả một `ResultSet`, có thể không có hàng hoặc có một/nhiều cột tùy hành vi thực tế.

- `Statement.RETURN_GENERATED_KEYS`: thuận tiện khi driver tự nhận diện được cột sinh; không bảo đảm sẽ trả cột `id` trên mọi DB.
- Mảng tên cột `new String[] {"id"}`: yêu cầu rõ cột muốn trả; một số driver không hỗ trợ dạng này, hoặc có khác biệt về chữ hoa/chữ thường/schema.
- Mảng vị trí cột `int[]`: cũng là một biến thể JDBC, nhưng vị trí phải khớp định nghĩa cột mà driver chấp nhận.
- Không kích hoạt cơ chế generated keys khi tạo statement thì `getGeneratedKeys()` có thể rỗng dù `INSERT` thành công.

`DatabaseMetaData.supportsGetGeneratedKeys()` cho biết driver báo có hỗ trợ lấy generated keys. Theo hợp đồng JDBC, khi trả `true`, driver phải hỗ trợ việc trả khóa ít nhất cho một số câu `INSERT`. Tuy vậy, `true` **không phải bảo đảm** cho mọi bảng, mọi kiểu khóa, mọi cách truyền tên cột hoặc mọi batch. Trả `false` nghĩa là không nên dựa vào API generated keys chuẩn; DB vẫn có thể có cú pháp `RETURNING`/`OUTPUT` riêng.

Một driver có thể phát sinh `SQLFeatureNotSupportedException` khi sử dụng biến thể `prepareStatement` mà nó không triển khai. Còn khi statement chạy nhưng danh sách khóa rỗng, cần kiểm tra SQL, cột sinh, yêu cầu lấy khóa và cách driver trả kết quả.

## 3. Ví dụ JDBC độc lập để kiểm tra driver

Ví dụ sau là **chương trình Java 17+ hoàn chỉnh**, dùng JDBC chuẩn và H2 2.x làm DB thử nghiệm. File `GeneratedKeysProbe.java`:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class GeneratedKeysProbe {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:h2:mem:keys_demo;DB_CLOSE_DELAY=-1";

        try (Connection connection =
                     DriverManager.getConnection(url, "sa", "")) {
            try (Statement statement = connection.createStatement()) {
                statement.executeUpdate("""
                        CREATE TABLE orders (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            description VARCHAR(100) NOT NULL
                        )
                        """);
            }

            DatabaseMetaData metadata = connection.getMetaData();
            System.out.println("supportsGetGeneratedKeys="
                    + metadata.supportsGetGeneratedKeys());

            String sql = "INSERT INTO orders (description) VALUES (?)";
            try (PreparedStatement ps = connection.prepareStatement(
                    sql, new String[] {"ID"})) {
                ps.setString(1, "demo");
                int affected = ps.executeUpdate();

                try (ResultSet keys = ps.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException(
                                "INSERT succeeded but no key was returned");
                    }
                    long id = keys.getLong(1);
                    if (keys.wasNull()) {
                        throw new SQLException("Generated id is SQL NULL");
                    }

                    System.out.println("affected=" + affected);
                    System.out.println("id=" + id);
                }
            }
        }
    }
}
~~~

Biên dịch bằng JDK 17+:

~~~bash
javac GeneratedKeysProbe.java
~~~

Đặt driver `h2.jar` phiên bản 2.x trên classpath khi chạy (Java cần JDBC driver tương ứng):

~~~bash
# Linux/macOS
java -cp ".:h2.jar" GeneratedKeysProbe

# Windows PowerShell / cmd
java -cp ".;h2.jar" GeneratedKeysProbe
~~~

Với H2 2.x, database mới và bảng mới, kết quả dự kiến:

~~~text
supportsGetGeneratedKeys=true
affected=1
id=1
~~~

`id=1` đúng cho lần tạo bảng này; ứng dụng thật không nên giả định mọi khóa bắt đầu từ 1 hay tăng liên tục. Ví dụ đóng đủ `Connection`, `Statement` và `ResultSet` bằng try-with-resources, nên không rò rỉ tài nguyên JDBC. Đổi sang driver/DB khác có thể cần chỉnh URL, DDL, tên cột hoặc chính cách yêu cầu generated keys.

## 4. Lấy khóa bằng Spring JdbcTemplate và KeyHolder

Giả sử bảng `orders` có cột `id BIGINT` do DB sinh và cột `description`. Trong một ứng dụng đã cấu hình `DataSource` và Spring JDBC, lớp repository sau minh họa cách gửi đúng yêu cầu lấy khóa. Đây là **lớp Java hoàn chỉnh ở mức repository**: nó cần Spring JDBC, driver DB và bảng `orders` có sẵn; không phải chương trình `main` chạy độc lập.

~~~java
import java.sql.PreparedStatement;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

public final class OrderRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public long create(String description) {
        String sql = "INSERT INTO orders (description) VALUES (?)";
        KeyHolder keyHolder = new GeneratedKeyHolder();

        int affected = jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    sql, new String[] {"id"});
            ps.setString(1, description);
            return ps;
        }, keyHolder);

        if (affected != 1) {
            throw new IllegalStateException(
                    "Expected one inserted row, got " + affected);
        }

        Number key = keyHolder.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "Driver did not return a generated id");
        }
        return key.longValue();
    }
}
~~~

**Luồng thực hiện:** `JdbcTemplate` mượn kết nối từ `DataSource`, gọi callback tạo `PreparedStatement` với danh sách cột generated key, bind tham số `description`, chạy `INSERT`, lấy `getGeneratedKeys()` và đặt kết quả vào `GeneratedKeyHolder`. Nó đóng tài nguyên theo hợp đồng Spring. Nếu ứng dụng dùng transaction của Spring, kết nối gắn với transaction được quản lý phù hợp.

Lưu ý quan trọng:

- `KeyHolder` là **đầu ra**; chỉ tạo `new GeneratedKeyHolder()` mà quên yêu cầu khóa ở `prepareStatement` thì không có cơ sở để đòi driver trả `id`.
- `getKey()` chỉ thích hợp với **một hàng, một cột khóa kiểu số**. Nếu driver trả nhiều cột hoặc nhiều hàng, phương thức này có thể ném ngoại lệ; cần xem `getKeys()` hoặc `getKeyList()`.
- Không ép thẳng sang `Long` bằng cast: driver có thể trả `Integer`, `Long` hoặc một `Number` khác. `key.longValue()` phù hợp khi cột và miền giá trị thật sự cho phép biểu diễn dưới `long`; cần xử lý kiểu/độ chính xác riêng nếu dữ liệu lớn hơn.
- Nên có mỗi `KeyHolder` mới cho mỗi thao tác insert; không chia sẻ một đối tượng có trạng thái giữa các request đồng thời.
- Kiểm tra `affected` và khóa đều quan trọng. Không gộp hai thông tin này thành một.

Nếu driver chỉ hỗ trợ cờ chung, thay `new String[] {"id"}` bằng `Statement.RETURN_GENERATED_KEYS` sau khi **kiểm chứng trên cặp driver/DB thực tế**. Không thay đổi một cách mù quáng: có driver trả cột khác với khóa mong đợi khi dùng cờ chung.

## 5. Khi dùng SimpleJdbcInsert

`SimpleJdbcInsert` khai thác metadata của JDBC để giảm lượng SQL cấu hình. Có thể cấu hình tên bảng, cột đầu vào và cột khóa sinh:

~~~java
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.simple.SimpleJdbcInsert;

public final class SimpleOrderRepository {
    private final SimpleJdbcInsert insertOrder;

    public SimpleOrderRepository(DataSource dataSource) {
        this.insertOrder = new SimpleJdbcInsert(dataSource)
                .withTableName("orders")
                .usingColumns("description")
                .usingGeneratedKeyColumns("id");
    }

    public long create(String description) {
        Number id = insertOrder.executeAndReturnKey(
                Map.of("description", description));
        return id.longValue();
    }
}
~~~

Ở đây `usingGeneratedKeyColumns("id")` khai báo cột cần trả, còn `usingColumns("description")` giới hạn cột đưa vào `INSERT`. Không truyền `id` như một tham số tự sinh. Phương thức `executeAndReturnKey(...)` trả `Number` cho khóa số đơn; với nhiều cột hoặc khóa không phải số, dùng `executeAndReturnKeyHolder(...)` và đọc cấu trúc trong `KeyHolder`.

**Ranh giới của tiện ích:** metadata giúp Spring chọn cách xây dựng SQL/statement, nhưng vẫn phải dựa vào driver. Một driver báo metadata không đầy đủ hoặc hỗ trợ khác nhau giữa các biến thể lấy khóa có thể làm cho cùng một cấu hình `SimpleJdbcInsert` hoạt động trên DB A nhưng thất bại trên DB B. Khi cần kiểm soát chính xác SQL và tên cột, `JdbcTemplate` với `PreparedStatementCreator` thường dễ chẩn đoán hơn.

## 6. Cột và kiểu dữ liệu được trả về không luôn giống nhau

`GeneratedKeyHolder` lưu cấu trúc tổng quát là `List<Map<String, Object>>`: mỗi map tương ứng với bộ cột generated keys cho một hàng kết quả mà driver trả về. Với một hàng và nhiều cột:

~~~java
Map<String, Object> generated = keyHolder.getKeys();
if (generated == null || generated.isEmpty()) {
    throw new IllegalStateException("No generated columns returned");
}
System.out.println(generated);
~~~

Đoạn trên là **minh họa đọc kết quả của thao tác đã thực hiện**, giả định biến `keyHolder` được tạo/điền như phần trước; không phải chương trình `main` độc lập. Tên map có thể là `id`, `ID` hoặc tên/nhãn khác theo driver. Với `UUID`, giá trị có thể là `java.util.UUID`, `String` hoặc kiểu JDBC khác; kiểm tra kiểu thực tế trước khi chuyển đổi.

Chỉ số cột của `ResultSet` bắt đầu từ 1; `rs.getLong(1)` là **cột đầu tiên trong kết quả generated keys**, không nhất thiết tương ứng cột đầu tiên của bảng. Đừng phụ thuộc thứ tự của nhiều cột nếu chưa kiểm chứng. Khi gọi `getKey()` cho kết quả nhiều cột, lỗi là do **giả định sai về cấu trúc**, không nhất thiết do insert thất bại.

Một số trường hợp dễ thay đổi hành vi:

- Bảng dùng `IDENTITY`/auto increment: thường là trường hợp đơn giản nhất; vẫn cần kiểm tra driver và phương thức yêu cầu khóa.
- Bảng sinh khóa qua sequence hoặc trigger: cách lấy khóa tùy DB và có thể cần chỉ rõ cột hoặc SQL riêng.
- Giá trị `UUID` do DB sinh: không coi mặc định là một `Number`; dùng API đọc nhiều kiểu hoặc SQL trả về rõ cột.
- `INSERT` nhiều hàng/batch: driver có thể trả nhiều hàng khóa, ít hơn số hàng, hoặc không bảo đảm cách ghép khóa với đầu vào theo đúng mong đợi. Kiểm thử riêng thay vì lấy một giá trị duy nhất.

## 7. Khác biệt giữa các hệ cơ sở dữ liệu

Bảng dưới là **định hướng chọn chiến lược**, không phải lời hứa về mọi phiên bản driver:

| DBMS | Hướng cần kiểm chứng | Rủi ro cần nhớ |
| --- | --- | --- |
| PostgreSQL | `getGeneratedKeys()` qua JDBC; khi cần trả rõ giá trị, SQL `INSERT ... RETURNING id` | Cú pháp `RETURNING` là đặc thù của DB; driver và kiểu cột quyết định giá trị Java nhận |
| MySQL/MariaDB | `AUTO_INCREMENT` và driver JDBC thường hỗ trợ lấy generated keys | Không suy diễn từ `AUTO_INCREMENT` sang mọi dạng trigger/default/UUID; batch có thể khác |
| Oracle Database | Chỉ rõ tên cột generated key nếu driver chấp nhận; đối với yêu cầu phức tạp, cân nhắc cú pháp `RETURNING ... INTO` thích hợp | Một số Oracle JDBC driver/phiên bản trả `ROWID` khi chỉ dùng cờ `RETURN_GENERATED_KEYS` chung |
| SQL Server | Driver JDBC và cột `IDENTITY`; SQL `OUTPUT INSERTED.id` khi cần điều khiển rõ đầu ra | `OUTPUT` có ngữ nghĩa riêng và có ràng buộc với một số trigger/câu lệnh; cần kiểm thử |
| H2 (test) | Thử nghiệm `IDENTITY` và `getGeneratedKeys()` thuận tiện | H2 pass không chứng minh PostgreSQL/Oracle/MySQL/SQL Server production sẽ giống hệt |

Không nên liệt kê một DBMS là “hỗ trợ” rồi kết luận mọi phiên bản, mọi loại `INSERT` và mọi dạng key đều tương thích. Đơn vị cần xác nhận là **DBMS + phiên bản server + JDBC driver/version + schema + dạng SQL + số hàng**.

### Phương án SQL trả kết quả trực tiếp khi JDBC generated keys không phù hợp

Ví dụ **riêng PostgreSQL**:

~~~sql
INSERT INTO orders (description)
VALUES ('demo')
RETURNING id;
~~~

Trong Spring JDBC, nếu môi trường PostgreSQL hỗ trợ câu lệnh này, có thể lấy giá trị ngay từ result set của câu SQL:

~~~java
Long id = jdbcTemplate.queryForObject(
        "INSERT INTO orders (description) VALUES (?) RETURNING id",
        Long.class,
        "demo");
if (id == null) {
    throw new IllegalStateException("INSERT RETURNING returned null id");
}
~~~

Đây là **mảnh code dùng trong một DAO có `jdbcTemplate`**, không phải class Java độc lập; SQL `RETURNING` phải được driver thực thi như một câu lệnh trả result set. Không mang nguyên cú pháp sang MySQL/Oracle/SQL Server. Khi DB có dạng `RETURNING ... INTO` hoặc `OUTPUT INSERTED...`, phải viết theo đúng tài liệu DB và dùng API JDBC/Spring thích hợp.

Các hàm lấy “id cuối” theo connection có thể là cơ chế khác của một DBMS, nhưng thường gắn với phiên/kết nối cụ thể. Không thực hiện `INSERT` trên một kết nối trong pool rồi đọc giá trị theo phiên ở một kết nối bất kỳ. **Tuyệt đối không dùng `SELECT MAX(id)` để tìm khóa vừa chèn**: người dùng khác có thể insert đồng thời.

## 8. Kiểm tra năng lực thật trước khi phụ thuộc vào nó

Trong lớp có `JdbcTemplate`, có thể truy vấn metadata trên kết nối mà Spring cung cấp:

~~~java
import org.springframework.jdbc.core.ConnectionCallback;

Boolean supported = jdbcTemplate.execute(
        (ConnectionCallback<Boolean>) connection ->
                connection.getMetaData().supportsGetGeneratedKeys());
System.out.println("Driver reports generated keys: " + supported);
~~~

Đây là **đoạn code minh họa** trong môi trường đã có biến `jdbcTemplate`, không phải class tự chạy. Có thể lấy thêm `getDatabaseProductName()`, `getDatabaseProductVersion()`, `getDriverName()` và `getDriverVersion()` từ cùng `DatabaseMetaData` để ghi nhận cặp DB/driver đang thực sự sử dụng.

Một phép thử đáng tin cậy gồm:

1. Xác định cột sinh thật và schema (identity, sequence, default, trigger); ghi nhận DB/driver/version.
2. Kiểm tra `supportsGetGeneratedKeys()` để có tín hiệu ban đầu, **không coi nó là kiểm thử end-to-end**.
3. Trong database dùng để thử tích hợp, thực hiện một `INSERT` có dữ liệu biết trước với đúng SQL/`PreparedStatement` mà ứng dụng sẽ dùng.
4. Kiểm tra đồng thời số hàng ảnh hưởng, số hàng returned keys, số cột, tên cột, kiểu Java, tính khác `null` và giá trị đúng với bản ghi vừa chèn.
5. Thử từng nhánh cần dùng: single insert, batch/multi-row, khóa số hay UUID, trigger/default; nếu chạy nhiều DB/driver, dùng test matrix cho các cặp thực tế.
6. Tạo trường hợp thất bại có kiểm soát (ví dụ SQL sai hoặc insert vi phạm constraint) để xác minh ứng dụng không trả nhầm khóa cũ và không tự retry thiếu an toàn.

Ví dụ một integration test kỳ vọng đúng **một** khóa số thì nên assert: có đúng một hàng được chèn, `KeyHolder.getKey() != null`, kiểu/chuyển đổi hợp lệ, và đọc lại chính bản ghi với `id` trả về trên cùng transaction/test setup. Test pass với H2 chỉ xác nhận H2; test production compatibility nên chạy với chính DB/driver production hoặc môi trường tương đương.

## 9. Khi lấy khóa thất bại: chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `update(...)` trả `1`, `getKey()` là `null` hoặc key list rỗng | Không kích hoạt lấy khóa; DB không sinh cột mong đợi; driver không trả khóa | Kiểm tra DDL, callback `prepareStatement`, SQL, metadata và kết quả raw `getGeneratedKeys()` |
| `SQLFeatureNotSupportedException` | Driver thiếu biến thể `prepareStatement`/generated keys đã gọi | Kiểm tra driver version, thử cờ chung hoặc SQL trả kết quả đặc thù đã được kiểm thử |
| Nhận `ROWID`/cột khác `id` | Driver tự chọn cột không như ứng dụng giả định | Thử chỉ rõ tên cột; đọc metadata cột kết quả; với Oracle xem tài liệu driver |
| `getKey()` ném lỗi về nhiều cột/hàng | Dùng API dành cho một giá trị đối với kết quả phức tạp | Đọc `getKeys()` hoặc `getKeyList()` và kiểm tra cấu trúc thực tế |
| `ClassCastException`/sai kiểu số | Driver trả kiểu khác; dùng cast cụ thể | Đọc dưới dạng `Number` hoặc kiểu được driver trả; kiểm tra overflow/độ chính xác |
| Chạy ổn local nhưng sai production | Khác DB, driver, DDL, case tên cột, batch behavior | So sánh version + schema + SQL; bổ sung integration test cho production |
| Batch trả thiếu key hoặc thứ tự không rõ | Hạn chế cách driver trả generated keys của batch | Kiểm chứng số lượng/tương quan; cân nhắc insert từng hàng hoặc SQL riêng nếu bắt buộc đối chiếu chính xác |

**Lưu ý về transaction:** lấy được `id` không có nghĩa transaction đã commit. Transaction có thể rollback sau khi id được cấp; sequence/identity có thể tạo khoảng trống trong dãy khóa. Nếu insert thành công nhưng bước lấy khóa thất bại dưới chế độ autocommit, bản ghi **có thể đã tồn tại**; không tự lặp lại lệnh insert ngay vì sẽ tạo bản ghi trùng. Thiết kế transaction và xử lý lỗi có chủ đích.

## 10. Quy tắc lựa chọn trong dự án Spring JDBC

- **Chỉ có một id số, driver đã được xác minh hỗ trợ:** dùng `JdbcTemplate.update(PreparedStatementCreator, KeyHolder)` hoặc `SimpleJdbcInsert.executeAndReturnKey(...)`.
- **Muốn kiểm soát tên cột, SQL, kiểu trả về:** dùng `JdbcTemplate` với `prepareStatement(sql, new String[] {"id"})`; kiểm tra kết quả thực tế của driver.
- **Một row nhưng nhiều cột sinh hoặc khóa không phải số:** dùng `KeyHolder.getKeys()`/`executeAndReturnKeyHolder(...)`, kiểm tra tên/kiểu cột.
- **Batch cần ghép chính xác khóa với từng input:** chỉ dùng API batch generated keys sau khi đã kiểm chứng hành vi trên driver thật; nếu không, cân nhắc thay chiến lược insert.
- **Driver không đáp ứng yêu cầu JDBC standard nhưng DB có SQL trả kết quả:** dùng `RETURNING`/`OUTPUT` hoặc kỹ thuật chính thức của DB đó và đóng gói khác biệt trong repository.

Nguyên tắc then chốt: **khả năng DB sinh khóa, khả năng JDBC lấy khóa và khả năng Spring bọc khóa là ba điều khác nhau**. Hãy kiểm chứng chính biến thể SQL/driver/DB của ứng dụng, xử lý kết quả rỗng hoặc sai kiểu một cách tường minh, và giữ logic đặc thù DB trong tầng data access.

## Tài liệu tham khảo

- [Java SE — `DatabaseMetaData.supportsGetGeneratedKeys()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DatabaseMetaData.html): hợp đồng capability của JDBC.
- [Spring Framework — Retrieving Auto-generated Keys trong `JdbcTemplate`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): callback, `KeyHolder` và quy trình trả khóa.
- [Spring Framework — `SimpleJdbcInsert` và generated keys](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): `usingGeneratedKeyColumns`, `executeAndReturnKey`, `executeAndReturnKeyHolder`.
- [Spring Framework — `KeyHolder` API](https://docs.spring.io/spring-framework/docs/6.0.17/javadoc-api/org/springframework/jdbc/support/KeyHolder.html): `getKey`, `getKeys`, `getKeyList`.
- [Oracle JDBC — auto-generated keys](https://docs.oracle.com/en/database/oracle/oracle-database/18/jjdbc/JDBC-standards-support.html): lưu ý cách lấy cột khóa và `ROWID` theo driver.
