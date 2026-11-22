# Đánh giá ánh xạ thủ công và ánh xạ dựa trên siêu dữ liệu trong JDBC

## 1. Bối cảnh và mục tiêu

Trong JDBC, `ResultSet` biểu diễn dữ liệu trả về từ câu lệnh SQL theo hàng và cột. Ứng dụng thường cần chuyển mỗi hàng thành một đối tượng Java có kiểu rõ ràng, chẳng hạn `CustomerRow`, để tầng nghiệp vụ không phụ thuộc trực tiếp vào `ResultSet`. Công việc này gọi là **ánh xạ bản ghi (record mapping)**.

Có hai cách tiếp cận phổ biến:

- **Ánh xạ thủ công:** lập trình viên đọc từng cột bằng `ResultSet.getXxx(...)`, xử lý `NULL`, chuyển kiểu và gọi constructor hoặc setter của đối tượng đích.
- **Ánh xạ dựa trên siêu dữ liệu:** chương trình đọc `ResultSetMetaData` để biết các cột đang xuất hiện, tên nhãn và kiểu SQL của chúng, rồi dùng quy tắc chung để tạo `Map`, đối tượng Java hoặc Java `record`.

Bài học thuộc chương **Ánh xạ bản ghi**, trong phạm vi **JDBC**: sử dụng driver, `DataSource`, `PreparedStatement`, `ResultSet` và các API Java chuẩn. Mục tiêu là biết cách xây dựng hai phương án, đánh giá tính đúng đắn, hiệu năng, khả năng bảo trì và chọn phương án phù hợp với truy vấn thực tế.

> **Phân biệt:** `ResultSetMetaData` mô tả **các cột trong kết quả của một truy vấn**. `DatabaseMetaData` mô tả khả năng của cơ sở dữ liệu và cấu trúc như bảng, khóa hay cột. Có metadata không đồng nghĩa JDBC tự biết cách tạo mọi đối tượng miền nghiệp vụ như một ORM.

## 2. Ví dụ dữ liệu và hợp đồng ánh xạ

Giả sử ứng dụng đọc khách hàng từ bảng sau (cú pháp DDL có thể cần điều chỉnh theo hệ quản trị cơ sở dữ liệu):

```sql
CREATE TABLE customers (
    id        BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    balance   DECIMAL(18, 2),
    joined_on DATE
);
```

Đối tượng dùng để hiển thị hoặc truyền dữ liệu:

```java
public record CustomerRow(
    long id,
    String name,
    BigDecimal balance,
    LocalDate joined
) {}
```

Trong tệp Java chứa record trên, cần import `java.math.BigDecimal` và `java.time.LocalDate`. Truy vấn sẽ khai báo alias tương ứng với tên thành phần của record:

```sql
SELECT id AS id,
       full_name AS name,
       balance AS balance,
       joined_on AS joined
FROM customers
WHERE id >= ?
ORDER BY id
```

**Hợp đồng ánh xạ:** `id` là số nguyên 64 bit không được `NULL`; `name` là chuỗi; `balance` là `BigDecimal` để giữ độ chính xác tiền tệ; `joined` là `LocalDate` hoặc `null`. Tên nhãn cột (alias) là giao diện giữa câu SQL và mã ánh xạ. Việc thay tên bảng hoặc tên cột vật lý không nhất thiết làm đổi record nếu alias được giữ ổn định.

## 3. Ánh xạ thủ công: rõ ràng và kiểm soát trực tiếp

Ví dụ dưới đây dùng Java 17+, `DataSource` để lấy kết nối, `PreparedStatement` để gán tham số an toàn và `try-with-resources` để đóng tài nguyên:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record CustomerRow(
        long id, String name, BigDecimal balance, LocalDate joined
    ) {}

    public List<CustomerRow> findFrom(long fromId) throws SQLException {
        String sql = """
                SELECT id AS id,
                       full_name AS name,
                       balance AS balance,
                       joined_on AS joined
                FROM customers
                WHERE id >= ?
                ORDER BY id
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, fromId);

            try (ResultSet rs = statement.executeQuery()) {
                List<CustomerRow> result = new ArrayList<>();
                while (rs.next()) {
                    result.add(mapCustomer(rs));
                }
                return result;
            }
        }
    }

    private static CustomerRow mapCustomer(ResultSet rs) throws SQLException {
        long id = rs.getLong("id");
        if (rs.wasNull()) {
            throw new SQLException("Cột id không được NULL");
        }

        Date joinedDate = rs.getDate("joined");
        LocalDate joined = joinedDate == null
                ? null
                : joinedDate.toLocalDate();

        return new CustomerRow(
                id,
                rs.getString("name"),
                rs.getBigDecimal("balance"),
                joined
        );
    }
}
```

Ở đây, mọi bước chuyển đổi đều nhìn thấy trong mã: `BIGINT` thành `long`, `DECIMAL` thành `BigDecimal`, `DATE` thành `LocalDate`. Dùng nhãn cột giúp phép ánh xạ ít phụ thuộc thứ tự cột trong `SELECT` hơn dùng chỉ số như `rs.getString(2)`.

**Điểm cần chú ý về `NULL`:**

- `getLong`, `getInt` và những getter kiểu nguyên thủy trả giá trị mặc định như `0` khi SQL là `NULL`; phải gọi `rs.wasNull()` ngay sau getter cần kiểm tra. Vì `id` được định nghĩa là khóa chính, việc nhận `NULL` phải gây lỗi thay vì âm thầm tạo một bản ghi có `id = 0`.
- `getString`, `getBigDecimal` và `getDate` có thể trả `null`. Phải quyết định rõ đối tượng đích chấp nhận `null`, từ chối hay áp dụng quy tắc mặc định.
- `getObject("joined", LocalDate.class)` có thể gọn hơn, nhưng khả năng chuyển trực tiếp từ SQL `DATE` phụ thuộc driver. `getDate(...)` rồi `toLocalDate()` là lựa chọn minh bạch cho ví dụ này.

Đối với nhiều truy vấn có cấu trúc ổn định, nên tách `mapCustomer(ResultSet)` thành hàm dùng lại hoặc triển khai giao diện `RowMapper<T>` do ứng dụng tự định nghĩa:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T map(ResultSet rs) throws SQLException;
}
```

JDBC chuẩn **không** cung cấp sẵn giao diện `RowMapper<T>` ở trên; đây là một abstraction do ứng dụng định nghĩa. Các framework có thể cung cấp giao diện tương tự với hợp đồng riêng.

## 4. Ánh xạ từ metadata: đọc cấu trúc kết quả khi chạy

Một truy vấn có thể thay đổi số cột, thứ tự cột hoặc alias. `ResultSetMetaData` cho phép chương trình quan sát chính xác kết quả đã được driver cung cấp:

```java
ResultSetMetaData meta = rs.getMetaData();
int count = meta.getColumnCount();

for (int i = 1; i <= count; i++) {
    String label = meta.getColumnLabel(i); // alias trong SELECT nếu có
    String name = meta.getColumnName(i);   // tên cột gốc nếu driver cung cấp
    int sqlType = meta.getColumnType(i);   // mã java.sql.Types
    String typeName = meta.getColumnTypeName(i);
    System.out.printf("%d: %s (%s, JDBC type %d)%n",
            i, label, typeName, sqlType);
}
```

Cần import `java.sql.ResultSetMetaData`. **Chỉ số cột JDBC bắt đầu từ 1.** Khi truy vấn dùng `AS name`, ưu tiên `getColumnLabel(i)` để ghép với tên thuộc tính Java. `getColumnName(i)` không thay thế đáng tin cậy cho alias, và chi tiết trả về có thể khác giữa các driver hoặc biểu thức SQL.

### 4.1. Trường hợp cấu trúc thực sự động: mỗi hàng thành một Map

Khi xây dựng màn hình báo cáo hoặc công cụ xem kết quả SQL có các cột không biết trước, có thể dùng metadata để ánh xạ sang `Map<String, Object>`:

```java
ResultSetMetaData meta = rs.getMetaData();
int columnCount = meta.getColumnCount();
List<Map<String, Object>> rows = new ArrayList<>();

while (rs.next()) {
    Map<String, Object> row = new LinkedHashMap<>();

    for (int i = 1; i <= columnCount; i++) {
        String label = meta.getColumnLabel(i);
        if (row.containsKey(label)) {
            throw new SQLException("Trùng nhãn cột: " + label);
        }
        row.put(label, rs.getObject(i));
    }
    rows.add(row);
}
```

Đoạn này cần import `java.sql.*` và `java.util.*`. `LinkedHashMap` giữ thứ tự cột theo kết quả truy vấn. **Ưu điểm** là thêm hay bớt cột không đòi hỏi sửa lớp Java. **Hạn chế** là consumer phải biết kiểu thực tế của mỗi giá trị, và `getObject(i)` có thể trả các kiểu Java khác nhau tùy SQL type và driver. Ngoài ra, các nhãn cột trùng nhau phải được xử lý có chủ đích, vì một `Map` không thể giữ hai giá trị cùng key.

### 4.2. Trường hợp record có kiểu xác định: tự động tìm cột theo tên

Có thể dùng metadata để tìm vị trí các nhãn cột và Java reflection để xây dựng record. Đây là ví dụ tối giản, có chủ đích **chỉ hỗ trợ** `long`, `Long`, `String`, `BigDecimal` và `LocalDate`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;
import java.math.BigDecimal;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class RecordResultSetMapper<T> {
    private final Constructor<T> constructor;
    private final RecordComponent[] components;

    public RecordResultSetMapper(Class<T> targetType) {
        if (!targetType.isRecord()) {
            throw new IllegalArgumentException("Kiểu đích phải là record");
        }

        components = targetType.getRecordComponents();
        Class<?>[] types = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);
        try {
            constructor = targetType.getDeclaredConstructor(types);
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(
                    "Không tìm thấy constructor của record", e);
        }
    }

    public List<T> mapAll(ResultSet rs) throws SQLException {
        ResultSetMetaData meta = rs.getMetaData();
        Map<String, Integer> indexByLabel = new HashMap<>();

        // Chuẩn bị ánh xạ cột một lần cho ResultSet.
        for (int column = 1; column <= meta.getColumnCount(); column++) {
            String label = meta.getColumnLabel(column);
            if (label == null || label.isBlank()) {
                throw new SQLException("Nhãn cột không hợp lệ ở vị trí " + column);
            }

            String key = label.toLowerCase(Locale.ROOT);
            if (indexByLabel.putIfAbsent(key, column) != null) {
                throw new SQLException("Trùng nhãn cột: " + label);
            }
        }

        int[] positions = new int[components.length];
        for (int i = 0; i < components.length; i++) {
            String key = components[i].getName().toLowerCase(Locale.ROOT);
            Integer column = indexByLabel.get(key);
            if (column == null) {
                throw new SQLException(
                        "Thiếu cột cho thành phần: " + components[i].getName());
            }
            positions[i] = column;
        }

        List<T> result = new ArrayList<>();
        while (rs.next()) {
            Object[] arguments = new Object[components.length];
            for (int i = 0; i < components.length; i++) {
                arguments[i] = readValue(
                        rs, positions[i], components[i].getType());
            }
            try {
                result.add(constructor.newInstance(arguments));
            } catch (ReflectiveOperationException | IllegalArgumentException e) {
                throw new SQLException("Không thể khởi tạo record", e);
            }
        }
        return result;
    }

    private static Object readValue(
            ResultSet rs, int column, Class<?> targetType
    ) throws SQLException {
        if (targetType == long.class || targetType == Long.class) {
            long value = rs.getLong(column);
            if (rs.wasNull()) {
                if (targetType == long.class) {
                    throw new SQLException("Cột tại vị trí " + column
                            + " là NULL nhưng record cần long");
                }
                return null;
            }
            return value;
        }
        if (targetType == String.class) {
            return rs.getString(column);
        }
        if (targetType == BigDecimal.class) {
            return rs.getBigDecimal(column);
        }
        if (targetType == LocalDate.class) {
            Date date = rs.getDate(column);
            return date == null ? null : date.toLocalDate();
        }
        throw new SQLException(
                "Kiểu Java chưa được hỗ trợ: " + targetType.getName());
    }
}
```

Trong phương thức `findFrom` của phần trước, có thể giữ nguyên câu SQL, cách tạo `PreparedStatement` và việc gán tham số, nhưng thay vòng `while` thủ công bằng:

```java
try (ResultSet rs = statement.executeQuery()) {
    return new RecordResultSetMapper<>(CustomerRow.class).mapAll(rs);
}
```

Điều kiện để đoạn trên hoạt động:

1. Record đích phải có constructor truy cập được, chẳng hạn `public record CustomerRow(...)` như ví dụ.
2. Mỗi thành phần record phải có một nhãn cột tương ứng; `id`, `name`, `balance`, `joined` khớp với các alias của truy vấn. Ví dụ chỉ chuẩn hóa **chữ hoa/chữ thường**; nó không tự chuyển `joined_on` thành `joinedOn`.
3. Mỗi kiểu Java phải có converter đã triển khai. Muốn hỗ trợ `UUID`, `enum`, `Integer`, `Boolean`, `Timestamp` hoặc kiểu riêng, phải mở rộng `readValue` và quy tắc `NULL`.
4. Constructor record có thể kiểm tra bất biến và ném lỗi; ví dụ bọc lỗi đó thành `SQLException` để người gọi nhận biết ánh xạ thất bại.

Đây là **mapper ví dụ phục vụ học tập**, chưa có hệ thống annotation/đổi tên trường, cache mapper, chuyển đổi kiểu linh hoạt, ánh xạ quan hệ lồng nhau hoặc chẩn đoán lỗi đầy đủ. Metadata chỉ cung cấp thông tin về kết quả SQL; quy tắc liên kết với kiểu miền vẫn phải do ứng dụng định nghĩa.

## 5. So sánh theo tiêu chí kỹ thuật

| Tiêu chí | Ánh xạ thủ công | Ánh xạ dựa trên metadata |
|---|---|---|
| **Khả năng đọc mã** | Nhìn rõ từng cột, kiểu và quy tắc chuyển đổi tại nơi sử dụng. | Mã truy vấn ngắn hơn; quy tắc chung nằm trong mapper và cần được tài liệu hóa. |
| **An toàn kiểu** | Kiểm soát trực tiếp getter và constructor; sai kiểu vẫn có thể phát sinh ở thời điểm chạy. | `Map<String,Object>` yếu về kiểu; mapper record có kiểu đích nhưng kiểm tra chuyển đổi thường xảy ra khi chạy. |
| **Thay đổi thứ tự cột** | An toàn khi đọc bằng alias; dễ lỗi nếu dựa vào chỉ số cố định. | Có thể tự tìm vị trí theo `getColumnLabel`, nên ít phụ thuộc thứ tự. |
| **Thêm/bớt cột** | Thường cần sửa mapper khi hợp đồng đối tượng thay đổi. | `Map` linh hoạt; mapper record vẫn yêu cầu đủ các thành phần bắt buộc. |
| **Quy tắc đặc biệt** | Dễ diễn đạt chuyển đổi, mặc định, kiểm tra miền và ánh xạ tổng hợp. | Cần converter, cấu hình tên trường, annotation hoặc quy ước bổ sung. |
| **Chi phí thực thi** | Getter và constructor trực tiếp; ít tầng trung gian. | Đọc metadata, tìm cột, đôi khi reflection và cấp phát cấu trúc hỗ trợ; mức ảnh hưởng phải đo. |
| **Phát hiện lỗi** | Có thể phát hiện rõ sai cột/kiểu tại đoạn ánh xạ cụ thể. | Có thể kiểm tra thiếu/trùng alias tập trung; lỗi chuyển đổi thường xuất hiện khi chạy. |
| **Mở rộng cho nhiều truy vấn** | Nhiều phép ánh xạ tương tự có thể lặp mã nếu không tái sử dụng. | Một mapper chung giảm mã lặp, nhưng tăng độ phức tạp của cơ chế chung. |

**Không phải lúc nào metadata cũng linh hoạt hơn về hợp đồng.** Mapper sang `Map` chấp nhận các tập cột thay đổi; mapper sang record vẫn cần đủ các cột tương ứng với thành phần của record. Cả hai phương án đều phụ thuộc vào dữ liệu và hợp đồng SQL thực tế.

## 6. Đánh giá hiệu năng có cơ sở

Một so sánh đúng cần xét ba loại chi phí:

1. **Chi phí truy vấn:** thời gian cơ sở dữ liệu thực thi SQL, truy cập dữ liệu, truyền dữ liệu qua mạng và tải dữ liệu qua driver. Đây có thể là phần chiếm ưu thế.
2. **Chi phí chuẩn bị ánh xạ:** đọc `ResultSetMetaData`, tạo bản đồ nhãn → chỉ số, truy xuất constructor và xác thực cột. Nên thực hiện **một lần cho mỗi `ResultSet`/cấu trúc truy vấn**, không lặp lại ở từng hàng.
3. **Chi phí mỗi hàng:** gọi getter, chuyển kiểu, tạo đối tượng, sử dụng reflection hay converter. Với rất nhiều hàng, chênh lệch nhỏ mỗi hàng có thể cộng dồn.

Ví dụ mapper record ở trên tạo bảng chỉ số một lần trước `while (rs.next())`; nó vẫn dùng reflection để gọi constructor cho từng hàng. Với đường xử lý rất nóng, có thể tái sử dụng mapper đã khởi tạo, chuẩn bị kế hoạch cột từ trước, hoặc chuyển sang mapper thủ công nếu phép đo chứng minh có lợi. Không nên đưa ra kết luận kiểu “nhanh hơn X lần” khi chưa có dữ liệu đo.

Cách đo đáng tin cậy:

- Dùng **cùng một truy vấn, driver, database, cấu hình fetch size, số lượng hàng và kiểu dữ liệu** cho hai phương án.
- Đo nhiều lần sau giai đoạn khởi động JVM; so sánh cả độ trễ, tốc độ hàng/giây, cấp phát bộ nhớ và GC. Nếu cần đánh giá riêng chi phí mapper, dùng benchmark có dữ liệu được kiểm soát, chẳng hạn JMH; cũng cần đo end-to-end khi chạy với database thực.
- Thử nhiều cỡ kết quả (ví dụ 100, 10.000, 100.000 hàng) và cả các giá trị `NULL`; không đưa kết luận từ một lần chạy.
- Cả hai ví dụ đang gom kết quả vào `List`, nên bộ nhớ tăng theo số hàng. Với kết quả lớn, cân nhắc xử lý từng hàng, phân trang hoặc cơ chế streaming có kiểm soát; đóng `ResultSet` và kết nối sau khi xử lý xong.
- Phân biệt lỗi do mapper với truy vấn SQL chậm, thiếu index, `N+1` query hoặc cấu hình driver không phù hợp. Đổi mapper không tự khắc phục những vấn đề đó.

## 7. Độ tin cậy, bảo mật và bảo trì

### 7.1. Xử lý lỗi để phát hiện sai hợp đồng sớm

Một mapper đủ tin cậy cần xác định trước phản ứng cho từng trường hợp:

| Tình huống | Xử lý khuyến nghị |
|---|---|
| Thiếu alias bắt buộc | Ném ngoại lệ nêu thành phần cần ánh xạ. |
| Hai cột cùng alias | Phát hiện trùng nhãn khi xây bảng chỉ số; không ghi đè âm thầm. |
| SQL `NULL` vào `long` hoặc `int` | Kiểm tra `wasNull()` và báo lỗi hoặc đổi mô hình sang wrapper nullable. |
| SQL `DECIMAL` dùng cho tiền | Ưu tiên `BigDecimal`; tránh tự chuyển sang `double` nếu cần chính xác thập phân. |
| Kiểu Java không được hỗ trợ | Báo lỗi rõ ràng, bổ sung converter có kiểm thử. |
| Alias đổi tên do sửa SQL | Duy trì alias ổn định hoặc sửa hợp đồng mapper và kiểm thử tương ứng. |
| Lỗi driver/SQL hoặc mất kết nối | Để `SQLException` lan truyền tới tầng quản lý lỗi hoặc bọc có nguyên nhân gốc. |

Không nên tự động chuyển mọi dữ liệu không hợp lệ về `null` hay giá trị mặc định để “đọc cho xong”: hành vi đó che giấu lỗi dữ liệu.

### 7.2. An toàn của SQL và metadata

`PreparedStatement` giúp gán **giá trị** vào dấu `?` an toàn; nó không tham số hóa được tên bảng, tên cột hoặc `ORDER BY` tùy ý. Nếu người dùng chọn các cột của báo cáo động, ứng dụng phải kiểm tra danh sách cột hoặc alias được phép trước khi dựng SQL. Metadata phản ánh kết quả được truy vấn; nó không xác định quyền truy cập dữ liệu hay bảo đảm một cột không nhạy cảm. Cũng cần giới hạn kiểu Java và đối tượng mà mapper reflection được phép tạo.

Khi báo lỗi, nên ghi tên truy vấn hoặc alias liên quan và nguyên nhân; tránh đưa giá trị nhạy cảm từ từng hàng vào log. Luồng giao dịch (`commit`, `rollback`, `autoCommit`) và vòng đời kết nối là trách nhiệm riêng của tầng gọi JDBC, bất kể chiến lược ánh xạ.

### 7.3. Kiểm thử phù hợp

Có thể tạo một tập dữ liệu kiểm thử nhỏ bằng cơ sở dữ liệu tương thích với driver đang sử dụng, rồi kiểm tra ít nhất các trường hợp:

1. Một hàng đầy đủ dữ liệu và nhiều hàng theo đúng thứ tự truy vấn.
2. `balance` hoặc `joined` là `NULL`; `id` bắt buộc không được `NULL`.
3. Đổi thứ tự cột trong `SELECT` nhưng giữ alias: hai mapper đọc theo alias vẫn phải cho kết quả như nhau.
4. Đổi một alias, bỏ một cột bắt buộc hoặc tạo hai alias trùng: metadata mapper phải báo lỗi rõ ràng.
5. Thử giá trị `DECIMAL` có phần thập phân và các ngày biên để phát hiện mất độ chính xác hoặc lệch chuyển đổi.
6. So sánh record thu được từ mapper thủ công và mapper metadata với cùng câu SQL và tập dữ liệu.

Kiểm thử tích hợp với driver thực quan trọng vì cách driver báo nhãn, hỗ trợ `getObject(..., Class)` và ánh xạ SQL type có thể khác nhau.

## 8. Chọn phương án trong dự án

**Ưu tiên ánh xạ thủ công khi** các truy vấn và mô hình dữ liệu ổn định, cần chuyển đổi nghiệp vụ đặc thù, muốn theo dõi luồng dữ liệu dễ dàng, hoặc có yêu cầu hiệu năng đã được đo cụ thể. Đặt phép ánh xạ trong một hàm riêng, dùng alias thay vì chỉ số cố định và tái sử dụng qua các truy vấn phù hợp.

**Ưu tiên metadata khi** xây báo cáo có projection thay đổi, công cụ xem dữ liệu chung, hoặc có nhiều record tuân theo một quy ước ánh xạ đơn giản. Với báo cáo động, `Map<String,Object>` hoặc một cấu trúc bảng thường phù hợp hơn record cố định; với record có schema rõ ràng, cần mapper có converter và kiểm tra hợp đồng.

**Kết hợp hai cách khi** phần lớn trường được ánh xạ theo quy ước, nhưng một số trường cần converter riêng (ví dụ mã trạng thái thành enum, timestamp thành kiểu thời gian của miền). Khi đó metadata có thể tìm cột và quản lý phần dùng chung, còn mapper chuyên biệt xử lý ngoại lệ. Tránh thiết kế một mapper reflection quá tổng quát chỉ để thay thế vài dòng getter rõ ràng.

### Tình huống tự đánh giá

Một ứng dụng có hai nhu cầu:

- API `GET /customers` luôn trả `id`, `name`, `balance`, `joined`, với quy tắc dữ liệu ổn định.
- Trang báo cáo cho phép người dùng chọn giữa hàng chục cột được cấp quyền, sắp xếp và xuất CSV.

Với API, mapper thủ công hoặc mapper record có kiểm tra kiểu là hợp lý; chọn theo khả năng bảo trì và phép đo thực tế. Với báo cáo, dùng allowlist để xây SQL và metadata để đọc các cột thực sự được chọn, sau đó xuất theo nhãn và thứ tự của kết quả. Cách này tránh phải tạo một lớp Java cho mọi tập hợp cột có thể có.

## 9. Ghi nhớ

- Ánh xạ thủ công mang lại sự minh bạch và kiểm soát kiểu dữ liệu; metadata giúp xử lý cấu trúc kết quả theo quy tắc chung.
- `ResultSetMetaData.getColumnLabel` thường là chìa khóa ghép cột SQL với thuộc tính Java; metadata không tự suy ra quy tắc miền.
- Luôn xử lý `NULL`, alias trùng/thiếu, kiểu không hỗ trợ và vòng đời `ResultSet`.
- Đọc metadata và tạo kế hoạch cột một lần, sau đó đo hiệu năng trong điều kiện đại diện trước khi tối ưu.
- Lựa chọn tốt nhất là phương án thể hiện rõ hợp đồng dữ liệu, dễ kiểm thử và đủ linh hoạt cho nhu cầu thay đổi thực tế.
