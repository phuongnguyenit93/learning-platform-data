# Yêu cầu cột khóa cụ thể và kiểm tra hỗ trợ của driver trong JDBC

Trong chương **CRUD và khóa sinh**, sau khi thực hiện `INSERT`, ứng dụng Java thường cần biết khóa của bản ghi vừa tạo để ghi bảng con, trả về API hoặc tiếp tục một giao dịch. Ví dụ, sau khi tạo khách hàng, dịch vụ cần `customer_id` do cơ sở dữ liệu sinh ra thay vì tự tính mã bằng `MAX(id) + 1`.

JDBC hỗ trợ lấy khóa sinh qua `Statement.getGeneratedKeys()`. Một điểm dễ bỏ qua là **cách yêu cầu khóa ngay lúc tạo `Statement`**: ứng dụng có thể yêu cầu chung bằng `Statement.RETURN_GENERATED_KEYS` hoặc chỉ định **tên cột**/**vị trí cột** cần nhận về. Tuy nhiên, khả năng hoạt động thực tế phụ thuộc cả **driver JDBC**, **kiểu khóa sinh**, **cơ sở dữ liệu** và **câu SQL**.

Bài này hướng dẫn chọn overload của `Connection.prepareStatement(...)`, sử dụng `DatabaseMetaData.supportsGetGeneratedKeys()`, đọc `ResultSet` trả khóa và xử lý những tình huống driver không hỗ trợ đầy đủ. Những kỹ thuật này nằm trong quy trình CRUD tham số hóa với `DataSource`, `PreparedStatement` và quản lý kết nối/transaction của JDBC.

## 1. Khóa sinh là gì và vì sao phải yêu cầu đúng?

**Khóa sinh** (*generated key*) là giá trị được cơ sở dữ liệu hoặc cơ chế của driver tạo/thu nhận khi thực thi thao tác ghi, thường là cột khóa chính kiểu `IDENTITY`, `AUTO_INCREMENT` hoặc cột được cấp giá trị qua sequence/default. Cách tạo khóa, khả năng trả lại giá trị và kiểu SQL tương ứng là đặc thù của hệ quản trị.

Giả sử có bảng minh họa:

```sql
CREATE TABLE customer (
    id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

Cú pháp `GENERATED ALWAYS AS IDENTITY` phù hợp với một số hệ cơ sở dữ liệu theo chuẩn SQL; khi dùng MySQL, SQLite hoặc phiên bản DB khác, cần đổi phần khai báo khóa tự sinh theo cú pháp tương ứng.

Luồng mong muốn:

```text
Java: INSERT INTO customer (email) VALUES (?)
  └─ PreparedStatement.executeUpdate()
       └─ Database sinh customer.id
            └─ PreparedStatement.getGeneratedKeys()
                 └─ ResultSet chứa khóa mà driver trả lại
                      └─ Java sử dụng id cho bước tiếp theo
```

Không nên lấy khóa bằng `SELECT MAX(id)` hoặc giả định khóa mới luôn bằng khóa cũ cộng một: nhiều transaction có thể ghi đồng thời, sequence có thể bỏ qua giá trị và khóa không nhất thiết liên tục.

## 2. Ba cách yêu cầu cột khóa khi tạo `PreparedStatement`

### Cách 1: Yêu cầu khóa được sinh nói chung

```java
String sql = "INSERT INTO customer (email) VALUES (?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    statement.setString(1, "mai@example.com");
    statement.executeUpdate();
    try (ResultSet keys = statement.getGeneratedKeys()) {
        // Đọc những khóa mà driver quyết định trả về.
    }
}
```

`RETURN_GENERATED_KEYS` báo cho driver biết ứng dụng muốn nhận khóa sinh. Nó **không chỉ rõ cột nào**. Trên nhiều hệ thống, driver trả cột khóa chính tự tăng; nhưng không nên mặc định mọi driver đều trả cùng số cột, thứ tự và tên cột.

### Cách 2: Yêu cầu theo **tên cột** — ưu tiên khi biết tên khóa

```java
String sql = "INSERT INTO customer (email) VALUES (?)";

try (PreparedStatement statement = connection.prepareStatement(
        sql, new String[] {"id"})) {
    statement.setString(1, "mai@example.com");
    statement.executeUpdate();
    try (ResultSet keys = statement.getGeneratedKeys()) {
        // Driver được yêu cầu trả cột id.
    }
}
```

Overload `prepareStatement(String sql, String[] columnNames)` chỉ định tên các cột ứng dụng muốn nhận sau `INSERT`. Đây là lựa chọn dễ đọc và ít phụ thuộc vào thứ tự cột vật lý khi schema thay đổi.

Nếu DB tạo cả `id` và một mã công khai như `public_code`, có thể thử:

```java
PreparedStatement statement = connection.prepareStatement(
        sql, new String[] {"id", "public_code"});
```

**Điều kiện:** Cột `public_code` phải thực sự tồn tại và có giá trị do cơ sở dữ liệu cung cấp; đồng thời driver phải hỗ trợ trả các cột được yêu cầu. Không phải driver nào cũng hỗ trợ danh sách nhiều cột hay trả chúng theo nhãn/thứ tự mong đợi. Cần kiểm tra kết quả trên DB thực.

### Cách 3: Yêu cầu theo **chỉ số cột**

```java
try (PreparedStatement statement = connection.prepareStatement(
        sql, new int[] {1})) {
    statement.setString(1, "mai@example.com");
    statement.executeUpdate();
    try (ResultSet keys = statement.getGeneratedKeys()) {
        // Yêu cầu cột ở vị trí 1 của bảng đích.
    }
}
```

Overload `prepareStatement(String sql, int[] columnIndexes)` chỉ định vị trí cột cần trả về, **không phải** vị trí dấu `?` trong câu SQL. Chỉ số được đánh từ **1**. Ví dụ bảng `customer(id, email)` có cột `id` ở vị trí 1, dù dấu `?` duy nhất là giá trị của `email`.

Nếu đổi thứ tự cột khi phát triển schema, cách dùng chỉ số có thể trỏ sang cột khác. Vì vậy, khi driver hỗ trợ cả hai, **yêu cầu bằng tên cột thường dễ bảo trì hơn**.

| Cách tạo statement | Mức chỉ định | Khi nào dùng |
| --- | --- | --- |
| `prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)` | Đề nghị driver trả khóa sinh mặc định | Khi chỉ cần khóa identity phổ biến và hành vi đã kiểm chứng |
| `prepareStatement(sql, new String[] {"id"})` | Yêu cầu cột tên `id` | Khi muốn rõ ràng về cột khóa cần đọc |
| `prepareStatement(sql, new int[] {1})` | Yêu cầu cột ở vị trí 1 | Khi driver hỗ trợ cách này và schema đã được kiểm soát |

JDBC còn có `Statement.executeUpdate(sql, Statement.RETURN_GENERATED_KEYS)` và các overload nhận tên/vị trí cột tương tự. Với ứng dụng CRUD nhận dữ liệu đầu vào, nên dùng `PreparedStatement` và tham số `?` để tránh ghép giá trị người dùng vào SQL.

## 3. Kiểm tra khả năng hỗ trợ từ `DatabaseMetaData`

Trước khi dựa vào việc lấy khóa sinh, có thể kiểm tra:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public static boolean supportsGeneratedKeys(DataSource dataSource)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData metaData = connection.getMetaData();
        return metaData.supportsGetGeneratedKeys();
    }
}
```

- `true`: driver khai báo hỗ trợ khả năng lấy khóa sinh.
- `false`: không nên dựa vào `getGeneratedKeys()` cho luồng nghiệp vụ này; tìm cơ chế khác được DB hỗ trợ.
- Lệnh có thể ném `SQLException` nếu không lấy được metadata hoặc kết nối gặp lỗi.

**Giới hạn của phép kiểm tra:** `supportsGetGeneratedKeys()` chỉ nói về tính năng **nói chung**; nó không chứng minh rằng driver hỗ trợ mọi overload `columnNames`/`columnIndexes`, mọi kiểu khóa, nhiều cột hoặc câu `INSERT` cụ thể. Ngay cả khi trả `true`, driver vẫn có thể báo `SQLFeatureNotSupportedException` hoặc trả kết quả không như mong muốn cho trường hợp cụ thể. Do đó, cần kiểm tra thêm bằng một thao tác ghi/đọc thực tế trong môi trường thử nghiệm.

Để phục vụ chẩn đoán, có thể ghi nhận thông tin driver:

```java
DatabaseMetaData meta = connection.getMetaData();
System.out.println(meta.getDriverName());
System.out.println(meta.getDriverVersion());
System.out.println(meta.getDatabaseProductName());
System.out.println(meta.getDatabaseProductVersion());
```

Những thông tin này hữu ích khi hành vi khác nhau giữa môi trường phát triển, kiểm thử và production.

## 4. Ví dụ hoàn chỉnh: tạo khách hàng và nhận đúng cột `id`

Ví dụ sau dùng `DataSource` để quản lý kết nối, `PreparedStatement` để truyền `email` theo tham số, và yêu cầu **cột `id` bằng tên**:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long createCustomer(String email) throws SQLException {
        String sql = "INSERT INTO customer (email) VALUES (?)";

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();
            if (!meta.supportsGetGeneratedKeys()) {
                throw new SQLFeatureNotSupportedException(
                        "Driver không hỗ trợ lấy khóa sinh");
            }

            try (PreparedStatement statement =
                    connection.prepareStatement(sql, new String[] {"id"})) {
                statement.setString(1, email);

                int affectedRows = statement.executeUpdate();
                if (affectedRows != 1) {
                    throw new SQLException(
                            "INSERT cần ảnh hưởng đúng một dòng: " + affectedRows);
                }

                try (ResultSet keys = statement.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException(
                                "INSERT đã chạy nhưng driver không trả khóa id");
                    }

                    long generatedId = keys.getLong(1);
                    if (keys.wasNull()) {
                        throw new SQLException("Khóa id trả về là NULL");
                    }
                    return generatedId;
                }
            }
        }
    }
}
```

Ví dụ giả định **khóa `id` là `BIGINT`, driver hỗ trợ yêu cầu cột bằng tên và cột khóa duy nhất được trả ở vị trí 1 của `ResultSet`**. Cách đọc `getLong(1)` tránh phụ thuộc vào việc driver đặt nhãn cột là `id` hay một tên chung, nhưng vẫn phải kiểm chứng chính xác cấu trúc kết quả; driver có thể không giữ nguyên thứ tự yêu cầu. Nếu khóa là `UUID` hoặc `DECIMAL` có phạm vi lớn hơn `long`, hãy dùng kiểu đọc phù hợp, ví dụ `getObject`, và kiểm tra ánh xạ với driver.

**Lưu ý transaction:** Ví dụ đơn giản dùng chế độ `autoCommit` mặc định của kết nối. Nếu `executeUpdate()` thành công nhưng `getGeneratedKeys()` không trả khóa, bản ghi **có thể đã được commit**; gọi lại thao tác ngay có thể gây trùng dữ liệu. Khi việc tạo bản ghi và nhận khóa phải là một đơn vị công việc, hãy tổ chức chúng trong transaction do tầng nghiệp vụ sở hữu, chỉ `commit` sau khi kiểm tra khóa và `rollback` khi thất bại; không thay đổi bừa bãi chế độ transaction của một kết nối đang được quản lý từ bên ngoài.

Nếu ứng dụng tạo thêm đơn hàng hoặc bảng con dựa trên `generatedId`, các bước ghi liên quan nên cùng transaction để tránh trạng thái chỉ tạo được bản ghi cha.

## 5. Đọc và xác nhận cấu trúc `ResultSet` chứa khóa

`getGeneratedKeys()` trả một `ResultSet`. Đừng giả định chỉ cần gọi `getLong(1)` là luôn đúng:

1. Kiểm tra `keys.next()` trước khi lấy giá trị. `ResultSet` có thể rỗng.
2. Xác nhận số lượng cột và kiểu dữ liệu thực tế bằng `ResultSetMetaData` khi driver mới hoặc yêu cầu nhiều cột.
3. Nếu chỉ cần một khóa `id`, đọc cột đúng bằng chỉ số/nhãn đã kiểm chứng; kiểm tra `wasNull()` khi dùng getter kiểu nguyên thủy.
4. Đóng `ResultSet` trước khi đóng `PreparedStatement`; `try-with-resources` xử lý được thứ tự này.

Có thể in metadata trong quá trình kiểm thử:

```java
import java.sql.ResultSetMetaData;

try (ResultSet keys = statement.getGeneratedKeys()) {
    ResultSetMetaData metadata = keys.getMetaData();
    int columns = metadata.getColumnCount();

    for (int i = 1; i <= columns; i++) {
        System.out.printf(
                "Cột %d: label=%s, type=%s%n",
                i,
                metadata.getColumnLabel(i),
                metadata.getColumnTypeName(i));
    }

    while (keys.next()) {
        for (int i = 1; i <= columns; i++) {
            System.out.printf("%s = %s%n",
                    metadata.getColumnLabel(i), keys.getObject(i));
        }
    }
}
```

Đây là mã chẩn đoán sử dụng `statement` sau khi thực thi `INSERT`, phù hợp cho môi trường phát triển. Trong production, tránh ghi khóa hoặc dữ liệu nhạy cảm ra log khi không có nhu cầu rõ ràng.

Khi yêu cầu hai cột, chẳng hạn `{"id", "public_code"}`, phải kiểm tra:

- Driver có thật sự trả cả hai cột hay chỉ trả khóa identity mặc định?
- Nhãn cột và thứ tự trả về có giống danh sách yêu cầu không?
- Có nhiều dòng được trả trong một thao tác không, và thứ tự dòng có liên hệ rõ với các dòng `INSERT` không?

Nếu chưa có hợp đồng driver cụ thể, không nên ánh xạ nhiều cột chỉ dựa vào thứ tự mình **mong đợi**.

## 6. Khi driver không hỗ trợ đầy đủ: xử lý thế nào?

Các trường hợp cần phân biệt:

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `supportsGetGeneratedKeys() == false` | Driver không công bố hỗ trợ tính năng | Dùng giải pháp riêng của DB hoặc nâng cấp driver sau khi kiểm chứng |
| `prepareStatement(sql, new String[]{"id"})` ném `SQLFeatureNotSupportedException` | Driver không hỗ trợ overload chỉ định tên cột | Kiểm tra `RETURN_GENERATED_KEYS` hoặc `columnIndexes` trên driver đó; chọn cách đã thử thành công |
| `getGeneratedKeys()` ném `SQLException` | Lỗi driver, cách gọi không hợp lệ hoặc DB không hỗ trợ tình huống | Xem `SQLState`, mã lỗi vendor và tài liệu driver |
| `getGeneratedKeys()` trả `ResultSet` rỗng | Không yêu cầu khóa, câu SQL không tạo khóa, hoặc driver không trả | Kiểm tra cách chuẩn bị statement, cấu trúc bảng và thao tác `INSERT` |
| Nhận một khóa nhưng ứng dụng yêu cầu hai cột | Driver chỉ trả subset hoặc áp dụng cơ chế khác | Kiểm tra metadata; thay đổi phương án đọc, không đoán cột thiếu |
| Nhận sai kiểu hoặc sai nhãn | Khóa DB khác kiểu Java hoặc nhãn do driver đặt | Xem `ResultSetMetaData` và ánh xạ kiểu thực tế |

Để phân biệt lỗi tính năng với lỗi SQL khác, có thể bắt riêng `SQLFeatureNotSupportedException`:

```java
try (PreparedStatement statement =
        connection.prepareStatement(sql, new String[] {"id"})) {
    // Bind tham số, executeUpdate(), getGeneratedKeys()...
} catch (SQLFeatureNotSupportedException unsupported) {
    // Chuyển sang giải pháp đã xác minh là hợp lệ với DB/driver hiện tại.
    throw unsupported;
}
```

Đoạn ví dụ minh họa bắt lỗi và **chủ động trả lỗi lên tầng gọi**; một nhánh fallback chỉ an toàn khi đã biết thao tác `INSERT` chưa được thực thi. Nếu lỗi xảy ra **sau** khi `INSERT` đã ghi dữ liệu, không được chạy lại `INSERT` một cách mù quáng. Nên chuẩn bị transaction thích hợp để kiểm soát tình huống này.

Một số DB hỗ trợ cú pháp riêng để trả dữ liệu vừa ghi, ví dụ với PostgreSQL:

```sql
INSERT INTO customer (email)
VALUES (?)
RETURNING id
```

Với cú pháp này, có thể dùng `PreparedStatement.executeQuery()` để đọc `id` trực tiếp từ `ResultSet` nếu driver/DB hỗ trợ. Đây là **SQL đặc thù hệ quản trị**, không phải cú pháp có thể dùng nguyên xi với mọi DB. Chỉ nên chọn sau khi xác nhận loại DB và chiến lược tương thích của dự án.

## 7. Các điểm cần lưu ý trong CRUD, batch và transaction

### Một lần `INSERT`, một dòng

Với thao tác tạo một bản ghi bằng `INSERT` thông thường, kết quả mong đợi là **một dòng bị ảnh hưởng và một khóa**. Tuy nhiên, không thể suy ra số khóa được trả chỉ từ `executeUpdate()` mà không kiểm tra `ResultSet`. Khóa có thể được tạo bằng sequence, trigger hoặc dạng mặc định khác nhau tùy DB.

### `INSERT` nhiều dòng và batching

`PreparedStatement.addBatch()`/`executeBatch()` giúp giảm lượt giao tiếp với DB. Tuy nhiên, JDBC không bảo đảm mọi driver đều trả đầy đủ generated keys theo **thứ tự ánh xạ từng đầu vào** khi chạy batch hoặc câu `INSERT` nhiều dòng. Một số driver yêu cầu tùy chọn kết nối hoặc có giới hạn tính năng.

Nếu cần ghép chính xác từng đối tượng Java với khóa mới:

- Thử nghiệm hành vi `executeBatch()` và `getGeneratedKeys()` trên đúng phiên bản DB/driver.
- Kiểm tra số lượng khóa, kiểu khóa và thứ tự, cả khi một phần batch lỗi.
- Nếu driver không bảo đảm ánh xạ, dùng thao tác `INSERT` riêng lẻ trong transaction hoặc một cơ chế trả khóa đặc thù DB đã kiểm chứng.

### Transaction và tính đồng thời

Lấy khóa từ `getGeneratedKeys()` của **chính statement vừa thực thi** thường tránh được cách truy vấn khóa toàn cục thiếu an toàn khi có các kết nối khác đang ghi. Dù vậy, ứng dụng vẫn phải xử lý transaction đúng cách: `commit` chỉ khi tất cả thao tác liên quan thành công, `rollback` khi thất bại. Không tái sử dụng `PreparedStatement`/`ResultSet` đã đóng và không chia sẻ kết nối JDBC giữa các luồng nếu tầng quản lý kết nối không bảo đảm.

### Tên cột do ứng dụng chỉ định

`String[] columnNames` là **tên định danh cột**, không phải tham số `?` hay nơi chứa giá trị người dùng. Chỉ truyền các tên cột do ứng dụng kiểm soát, chú ý quy tắc chữ hoa/chữ thường và tên cột có dấu nháy của DB. Dữ liệu nghiệp vụ như `email` vẫn phải đi qua `statement.setString(...)`.

## 8. Bài thực hành có kiểm chứng

Giả sử ứng dụng có bảng `customer` và cột `id` tự sinh như trong ví dụ. Thực hiện lần lượt:

1. Kiểm tra `connection.getMetaData().supportsGetGeneratedKeys()`; ghi lại tên và phiên bản driver nếu cần chẩn đoán.
2. Chèn khách hàng bằng `prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)`, đọc khóa và xác minh bản ghi bằng `SELECT id, email FROM customer WHERE id = ?`.
3. Lặp lại với `prepareStatement(sql, new String[]{"id"})`; so sánh số cột, nhãn và kiểu từ `getGeneratedKeys().getMetaData()`.
4. Lặp lại với `prepareStatement(sql, new int[]{1})`, rồi kiểm tra xem driver có hỗ trợ và trả đúng `id` hay không.
5. Thử một tên cột không tồn tại trong môi trường test để quan sát thời điểm và loại lỗi. Không lặp lại lệnh `INSERT` nếu chưa biết thao tác trước đã thành công hay chưa.
6. Nếu cần tạo nhiều bản ghi, thử `executeBatch()` với generated keys; chỉ sử dụng kết quả cho ánh xạ nghiệp vụ sau khi đã xác minh số lượng và thứ tự trên driver thực tế.

**Câu hỏi tự kiểm tra:** Vì sao `supportsGetGeneratedKeys() == true` vẫn chưa đủ để kết luận `new String[]{"id", "public_code"}` chắc chắn hoạt động? Vì sao một lỗi đọc khóa sau khi `INSERT` thành công không thể luôn xử lý bằng cách chạy lại `INSERT`?

## 9. Tóm tắt lựa chọn trong dự án

- **Muốn lấy khóa sinh mặc định:** dùng `Statement.RETURN_GENERATED_KEYS` khi đã biết driver trả khóa phù hợp.
- **Muốn chỉ rõ cột:** ưu tiên `prepareStatement(sql, new String[]{"id"})` nếu driver hỗ trợ; dùng `int[] columnIndexes` khi có lý do rõ ràng và schema được kiểm soát.
- **Muốn biết driver có hỗ trợ:** kiểm tra `DatabaseMetaData.supportsGetGeneratedKeys()`, sau đó thử toàn bộ đường `prepareStatement → executeUpdate → getGeneratedKeys`.
- **Muốn đúng với dữ liệu thật:** kiểm tra `ResultSet` có dòng, số cột, thứ tự/nhãn và kiểu khóa; không suy đoán từ tên overload.
- **Muốn an toàn với transaction và concurrency:** lấy khóa ngay từ statement đã ghi, dùng SQL tham số hóa, xử lý lỗi trước khi commit và tránh chạy lại `INSERT` không kiểm soát.

**Ghi nhớ:** `getGeneratedKeys()` là API JDBC chuẩn để nhận khóa được sinh, nhưng **khả năng chỉ định cột và cấu trúc kết quả phụ thuộc driver**. Chỉ yêu cầu đúng cột vẫn chưa đủ; phải kiểm tra hỗ trợ, đọc kết quả có kiểm chứng và thiết kế transaction phù hợp với hành vi của DB thực tế.
