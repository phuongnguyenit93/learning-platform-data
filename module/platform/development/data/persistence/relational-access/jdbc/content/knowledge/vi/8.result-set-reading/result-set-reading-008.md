# Xử lý cột thiếu, sai nhãn và chuyển đổi kiểu không hợp lệ khi đọc ResultSet

Trong JDBC (*Java Database Connectivity*), `ResultSet` đại diện cho kết quả của câu truy vấn SQL. Sau khi gọi `executeQuery()`, ứng dụng thường dùng `result.next()` và các getter như `getLong()`, `getString()`, `getBigDecimal()` hoặc `getObject()` để chuyển từng hàng dữ liệu quan hệ thành đối tượng Java.

Công việc này dễ gặp ba nhóm sự cố: **cột cần đọc không có trong kết quả**, **tên/nhãn được dùng trong getter không khớp với nhãn cột thực tế**, và **kiểu dữ liệu SQL không thể chuyển an toàn sang kiểu Java mà getter yêu cầu**. Những lỗi này cần được phân biệt vì chúng xảy ra ở những bước khác nhau và có cách sửa khác nhau.

Bài thuộc chương **Đọc ResultSet**, tập trung vào cách kiểm tra cấu trúc kết quả, ánh xạ đúng nhãn cột, xử lý `NULL` và chuyển đổi kiểu có kiểm soát. Các ví dụ dùng Java 17+ và JDBC thuần để chỉ ra trực tiếp API làm việc với cơ sở dữ liệu quan hệ.

## 1. Ba loại vấn đề, ba vị trí phát sinh

Giả sử ứng dụng cần lấy một hóa đơn:

```sql
SELECT
    i.id AS invoice_id,
    c.display_name AS customer_name,
    i.total_amount AS total_amount
FROM invoices AS i
JOIN customers AS c ON c.id = i.customer_id
WHERE i.id = ?
```

Một hàng kết quả có ba **nhãn**: `invoice_id`, `customer_name` và `total_amount`. Những lỗi sau nhìn bề ngoài đều là “không đọc được dữ liệu” nhưng không giống nhau:

| Tình huống | Ví dụ | Điểm có thể phát sinh lỗi | Bản chất |
|---|---|---|---|
| Tên cột **không tồn tại trong bảng** | SQL viết `i.total` nhưng bảng chỉ có `total_amount` | `executeQuery()` hoặc khi server xử lý SQL | Câu SQL/schema không khớp |
| Cột có trong SQL nhưng **không nằm trong projection** | SQL không `SELECT` `i.status`, mapper gọi `getString("status")` | Getter hoặc `findColumn()` | Mapper yêu cầu cột không có trong `ResultSet` |
| **Sai nhãn/alias** | SQL dùng `AS invoice_id`, mapper gọi `getLong("id")` | Getter hoặc `findColumn()` | Tên Java dùng không khớp `columnLabel` |
| **Trùng nhãn** | `SELECT i.id, c.id ...`, rồi `getLong("id")` | Có thể không ném lỗi | Kết quả ánh xạ mơ hồ, có nguy cơ đọc nhầm cột |
| **Không tương thích kiểu** | `getInt("status")` khi dữ liệu là `"PAID"` | Getter đang chuyển đổi dữ liệu | Kiểu Java được yêu cầu không phù hợp |
| **Giá trị SQL NULL** | `getInt("discount_pct")` trên giá trị `NULL` | Có thể **không** ném lỗi | Getter primitive có thể trả `0`; cần `wasNull()` |

Một cột SQL có giá trị `NULL` **vẫn tồn tại trong kết quả**. “Thiếu cột” và “cột có giá trị NULL” là hai vấn đề khác nhau. Tương tự, một truy vấn trả **0 hàng** không có nghĩa là thiếu cột: metadata về các cột vẫn có thể được đọc.

## 2. Cột trong bảng, tên cột và nhãn cột là ba khái niệm

### 2.1. Getter theo chỉ số hoặc theo nhãn

`ResultSet` cung cấp hai cách truy cập:

```java
long idByIndex = result.getLong(1);             // Vị trí cột thứ nhất
long idByLabel = result.getLong("invoice_id");  // Nhãn SQL của cột
```

**Chỉ số cột trong JDBC bắt đầu từ 1**, theo thứ tự các biểu thức xuất hiện trong `SELECT`. Chỉ số 0 không hợp lệ. Với getter theo chuỗi, tham số biểu thị **column label**. Khi SQL dùng `AS`, nhãn thường là alias đã đặt:

```sql
SELECT id AS invoice_id, total_amount AS amount
FROM invoices
```

Khi đó nên dùng:

```java
result.getLong("invoice_id");
result.getBigDecimal("amount");
```

Nếu không có `AS`, nhãn thường theo tên cột; nhưng với biểu thức tổng hợp, hàm hoặc cách đặt alias đặc thù, nhãn mặc định có thể khó dự đoán. **Đặt alias rõ ràng** cho những giá trị mà mapper sẽ đọc là cách thiết kế dễ bảo trì.

### 2.2. getColumnLabel() khác getColumnName()

`ResultSetMetaData` mô tả cấu trúc kết quả:

- `getColumnCount()`: số cột trong projection.
- `getColumnLabel(i)`: nhãn dành để hiển thị và truy cập theo label, thường là alias `AS`.
- `getColumnName(i)`: tên cột cơ sở khi driver có thể cung cấp; ý nghĩa cụ thể phụ thuộc biểu thức và driver.
- `getColumnType(i)`: mã kiểu SQL từ `java.sql.Types`.
- `getColumnTypeName(i)`: tên kiểu do database/driver báo cáo.
- `isNullable(i)`: mức thông tin về khả năng NULL; driver có thể trả `columnNullableUnknown`.
- `getPrecision(i)` / `getScale(i)`: thông tin có ích cho kiểu số khi driver cung cấp.

Một ví dụ ngắn:

```java
ResultSetMetaData meta = result.getMetaData();

for (int i = 1; i <= meta.getColumnCount(); i++) {
    System.out.printf(
            "%d: label=%s, name=%s, type=%s (%d)%n",
            i,
            meta.getColumnLabel(i),
            meta.getColumnName(i),
            meta.getColumnTypeName(i),
            meta.getColumnType(i));
}
```

Đoạn này giả định biến `result` là `ResultSet` đang mở và đã import `java.sql.ResultSetMetaData`. Không cần đọc từng hàng để biết nhãn cột. Tuy vậy, metadata là **thông tin do driver báo cáo**, không phải một hợp đồng hoàn toàn đồng nhất cho mọi biểu thức SQL và mọi hệ quản trị.

Đặc biệt, khi truy vấn:

```sql
SELECT total_amount * 1.1 AS adjusted_total
FROM invoices
```

nhãn nên được xác định bằng `getColumnLabel()` và đọc bằng `getBigDecimal("adjusted_total")` khi kiểu thực tế phù hợp. Đừng dự đoán `getColumnName()` sẽ trả tên nào cho biểu thức tính toán.

### 2.3. Trùng nhãn làm kết quả không rõ nghĩa

Truy vấn sau chứa hai cột cùng nhãn `id`:

```sql
SELECT i.id, c.id
FROM invoices AS i
JOIN customers AS c ON c.id = i.customer_id
```

Nếu gọi `result.getLong("id")`, JDBC có thể chọn cột khớp đầu tiên theo quy tắc tìm kiếm nhãn. Chương trình **không nhất thiết nhận SQLException**, mà có thể âm thầm lấy nhầm ID.

Đặt alias riêng:

```sql
SELECT
    i.id AS invoice_id,
    c.id AS customer_id
FROM invoices AS i
JOIN customers AS c ON c.id = i.customer_id
```

Khi cần bảo vệ hợp đồng mapper, hãy kiểm tra các nhãn bắt buộc **có mặt đúng một lần**. Với dữ liệu quan trọng, lỗi “đọc nhầm một cột cũng có kiểu BIGINT” có thể nguy hiểm hơn ngoại lệ xuất hiện ngay.

## 3. Dùng findColumn() để xác định cột được trả về

`ResultSet.findColumn(String columnLabel)` trả chỉ số **1-based** của cột khớp nhãn, hoặc ném `SQLException` nếu không tìm được.

```java
int idIndex = result.findColumn("invoice_id");
int amountIndex = result.findColumn("total_amount");

long id = result.getLong(idIndex);
BigDecimal amount = result.getBigDecimal(amountIndex);
```

Đoạn trên giả định `result` đã ở một hàng dữ liệu và đã import `java.math.BigDecimal`. `findColumn()` hữu ích để kiểm tra nhanh sự tồn tại của nhãn. Tuy nhiên:

- Với **nhãn bị trùng**, `findColumn()` không phải công cụ kiểm tra tính duy nhất.
- Nếu cùng một nhãn được tìm nhiều lần trong vòng lặp hàng lớn, ứng dụng có thể lấy chỉ số một lần rồi tái sử dụng; không cần tìm lặp lại.
- Về mặt SQL, alias có thể được database chuẩn hóa chữ hoa/chữ thường tùy cách trích dẫn. Nên sử dụng alias nhất quán, đơn giản như `snake_case`, tránh phụ thuộc những khác biệt driver hoặc quy tắc viết hoa.
- Khi kết quả không có hàng, vẫn có thể phân tích projection bằng `getMetaData()`; không cần đợi `next()` trả `true` mới kiểm tra sự tồn tại của các nhãn.

## 4. Thiết kế mapper đọc dữ liệu có kiểm tra hợp đồng

Hãy thiết kế mapper cho truy vấn hóa đơn. Trong ví dụ sau, `invoice_id`, `customer_name`, `total_amount` và `issued_on` là cột **bắt buộc**; `discount_pct` là cột có thể chứa SQL `NULL`. Mọi cột bắt buộc đều phải xuất hiện đúng một lần.

Cú pháp SQL minh họa:

```sql
SELECT
    i.id AS invoice_id,
    c.display_name AS customer_name,
    i.total_amount AS total_amount,
    i.discount_pct AS discount_pct,
    i.issued_on AS issued_on
FROM invoices AS i
JOIN customers AS c ON c.id = i.customer_id
WHERE i.id = ?
```

DAO Java:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class InvoiceReader {
    public record Invoice(
            long id,
            String customerName,
            BigDecimal totalAmount,
            Integer discountPercent,
            LocalDate issuedOn) {}

    private final DataSource dataSource;

    public InvoiceReader(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<Invoice> findById(long id) throws SQLException {
        String sql = """
                SELECT
                    i.id AS invoice_id,
                    c.display_name AS customer_name,
                    i.total_amount AS total_amount,
                    i.discount_pct AS discount_pct,
                    i.issued_on AS issued_on
                FROM invoices AS i
                JOIN customers AS c ON c.id = i.customer_id
                WHERE i.id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet rows = statement.executeQuery()) {
                // Kiểm tra projection ngay cả khi không có dòng trả về.
                Map<String, Integer> columns = columnIndexes(rows.getMetaData());
                int idColumn = required(columns, "invoice_id");
                int nameColumn = required(columns, "customer_name");
                int totalColumn = required(columns, "total_amount");
                int discountColumn = required(columns, "discount_pct");
                int issuedColumn = required(columns, "issued_on");

                if (!rows.next()) {
                    return Optional.empty();
                }

                long invoiceId = rows.getLong(idColumn);
                if (rows.wasNull()) {
                    throw new SQLException("invoice_id không được NULL");
                }

                String customerName = rows.getString(nameColumn);
                if (customerName == null) {
                    throw new SQLException("customer_name không được NULL");
                }

                BigDecimal total = rows.getBigDecimal(totalColumn);
                if (total == null) {
                    throw new SQLException("total_amount không được NULL");
                }

                int rawDiscount = rows.getInt(discountColumn);
                Integer discount = rows.wasNull() ? null : rawDiscount;

                // Cần driver JDBC 4.2 hỗ trợ ánh xạ DATE -> LocalDate.
                LocalDate issuedOn = rows.getObject(
                        issuedColumn, LocalDate.class);
                if (issuedOn == null) {
                    throw new SQLException("issued_on không được NULL");
                }

                return Optional.of(new Invoice(
                        invoiceId, customerName, total, discount, issuedOn));
            }
        }
    }

    private static Map<String, Integer> columnIndexes(
            ResultSetMetaData meta) throws SQLException {

        Map<String, Integer> indexes = new HashMap<>();

        for (int column = 1; column <= meta.getColumnCount(); column++) {
            String label = meta.getColumnLabel(column);
            if (label == null || label.isBlank()) {
                throw new SQLException("Cột " + column + " không có nhãn hợp lệ");
            }

            // Hợp đồng của ví dụ này dùng alias snake_case không phân biệt hoa.
            String key = label.toLowerCase(Locale.ROOT);
            Integer first = indexes.putIfAbsent(key, column);
            if (first != null) {
                throw new SQLException(
                        "Trùng nhãn '" + label
                        + "' ở cột " + first + " và " + column);
            }
        }
        return indexes;
    }

    private static int required(
            Map<String, Integer> indexes, String label) throws SQLException {

        Integer index = indexes.get(label.toLowerCase(Locale.ROOT));
        if (index == null) {
            throw new SQLException("Projection thiếu cột bắt buộc: " + label);
        }
        return index;
    }
}
```

Điểm đáng chú ý trong ví dụ:

1. **SQL chọn cột tường minh, không dùng `SELECT *`.** Alias là một phần của hợp đồng giữa câu truy vấn và mapper.
2. **Đọc metadata trước khi đọc hàng.** Nếu đổi alias hoặc bỏ cột trong projection, lỗi được báo ngay cả khi truy vấn trả 0 hàng.
3. **Kiểm tra nhãn trùng.** Bảng ánh xạ không chấp nhận hai cột có nhãn bằng nhau khi chuẩn hóa theo quy ước của ứng dụng.
4. **Dùng chỉ số đã xác định.** Khi đã kiểm tra projection, mapper đọc từ những vị trí cố định của cùng `ResultSet`.
5. **Phân biệt `NULL` với giá trị hợp lệ.** `getLong()` và `getInt()` cần `wasNull()` để phát hiện SQL NULL; `getString()`, `getBigDecimal()` và `getObject()` có thể trả `null`.
6. **Không thay một kiểu bất kỳ thành chuỗi rồi tự parse.** Truy vấn và getter cùng thể hiện ý nghĩa số, ngày và văn bản.

Đây là cách viết **nghiêm ngặt** thích hợp khi dữ liệu bắt buộc phải đúng hợp đồng. Trong hệ thống có số lượng truy vấn lớn, có thể trích cơ chế kiểm tra metadata thành helper tái sử dụng; không cần sao chép tất cả logic cho từng DAO. Việc kiểm tra trùng alias cũng là **chính sách rõ ràng của ứng dụng**, chứ không phải điều JDBC tự động bắt buộc.

**Lưu ý:** Ví dụ giả định driver hỗ trợ `ResultSet.getObject(columnIndex, LocalDate.class)`. Nếu không, với cột `DATE` có thể sử dụng `java.sql.Date date = rows.getDate(issuedColumn)` và `date.toLocalDate()` sau khi kiểm tra `date != null`. Chọn cách chuyển đổi theo kiểu cột và phiên bản driver, không tự động thử đủ mọi kiểu bằng một vòng lặp `catch`.

## 5. Cột thiếu và cột tùy chọn phải xử lý khác nhau

### 5.1. Cột bắt buộc bị thiếu: báo lỗi, không âm thầm cho mặc định

Nếu hợp đồng yêu cầu `invoice_id` mà SQL đã bị đổi thành:

```sql
SELECT i.id AS id, i.total_amount AS total_amount
FROM invoices AS i
```

mapper cần báo **thiếu `invoice_id`**, không nên tự suy đoán `id` có cùng ý nghĩa. Một ngoại lệ chứa tên label bị thiếu sẽ giúp phát hiện thay đổi SQL/schema ngay ở môi trường kiểm thử.

Đừng chữa lỗi bằng cách này:

```java
try {
    return rows.getLong("invoice_id");
} catch (SQLException error) {
    return 0L; // Nguy hiểm: biến lỗi hợp đồng thành ID giả.
}
```

`SQLException` không chỉ có nghĩa “cột bị thiếu”; nó có thể là lỗi kết nối, lỗi driver hoặc chuyển đổi kiểu. Bắt **mọi** `SQLException` rồi trả mặc định sẽ che mất nguyên nhân thực tế.

### 5.2. Cột thực sự tùy chọn: kiểm tra metadata trước

Trong một số giai đoạn triển khai, cột mới có thể chỉ xuất hiện trong những phiên bản projection nhất định. Nếu ứng dụng **cố ý hỗ trợ** cả hai dạng, hãy xác định rõ chính sách:

```java
// indexes đã được lập từ ResultSetMetaData theo ví dụ trên.
Integer noteColumn = indexes.get("note");

String note = null;
if (noteColumn != null) {
    note = rows.getString(noteColumn);
}
```

Nếu `noteColumn == null`, cột **không có trong projection**. Nếu `noteColumn != null` nhưng `getString()` trả `null`, cột có mặt và giá trị SQL là `NULL`. Hai trường hợp có thể cùng quy về `null` trong model **chỉ khi nghiệp vụ chấp nhận**. Nếu cần phân biệt rõ ba trạng thái “không có cột / có cột nhưng NULL / có giá trị”, model cần biểu diễn chúng riêng.

Một số nhóm chọn luôn xuất cột tùy chọn dưới cùng một alias, kể cả khi chưa có giá trị:

```sql
SELECT
    i.id AS invoice_id,
    CAST(NULL AS VARCHAR(500)) AS note
FROM invoices AS i
```

Cú pháp `CAST` và kiểu độ dài có thể thay đổi theo hệ quản trị, nhưng ý tưởng là **giữ projection ổn định** để mapper không phải xử lý nhiều phiên bản nhãn. Chỉ dùng mẫu này khi logic nghiệp vụ thực sự yêu cầu và biết rõ kiểu SQL phù hợp.

### 5.3. Cột có mặt nhưng LEFT JOIN trả NULL

`LEFT JOIN` có thể trả cột từ bảng bên phải bằng `NULL` khi không tìm được hàng liên quan. Điều đó không phải thiếu cột và thường cũng không phải lỗi SQL. Ví dụ `getString("customer_name") == null` có thể có nghĩa khách hàng chưa có dữ liệu liên quan. Phân biệt trạng thái ấy ở mô hình nghiệp vụ thay vì mặc định coi `NULL` là lỗi cho mọi truy vấn.

## 6. Nhận biết chuyển đổi kiểu không hợp lệ

Getter JDBC có thể yêu cầu driver chuyển giá trị SQL thành kiểu Java được chọn. Một số chuyển đổi được chuẩn hỗ trợ; một số phụ thuộc driver hoặc bị từ chối. Dữ liệu không hợp lệ có thể gây `SQLException` hoặc lớp con như `SQLDataException`, nhưng không nên suy luận loại ngoại lệ cụ thể luôn giống nhau.

| Kiểu SQL/giá trị | Getter không phù hợp | Nguy cơ | Cách đọc rõ nghĩa hơn |
|---|---|---|---|
| `VARCHAR = 'PAID'` | `getInt("status")` | Không thể chuyển chuỗi chữ thành số nguyên | `getString("status")`, ánh xạ enum ở tầng Java |
| `DECIMAL(12,2) = 99.95` | `getInt("amount")` | Mất phần thập phân, làm tròn hoặc lỗi tùy driver | `getBigDecimal("amount")` |
| `BIGINT` vượt giới hạn `int` | `getInt("id")` | Tràn phạm vi hoặc báo lỗi, tùy chuyển đổi | `getLong("id")` nếu schema dùng BIGINT |
| `TIMESTAMP` | `getDate("created_at")` | Mất phần giờ/phút/giây | Getter thời gian phù hợp với ý nghĩa cột |
| `VARCHAR` chứa ngày theo định dạng không chuẩn | `getDate("date_text")` | Parse/chuyển đổi không hợp lệ | Lưu `DATE` thật hoặc parse văn bản có quy tắc |
| `BLOB` lớn | `getBytes("payload")` | Có thể cấp phát mảng lớn trong heap | `getBinaryStream("payload")` nếu driver hỗ trợ |
| Kiểu JSON/UUID riêng của DB | `getObject(..., SomeClass.class)` không được driver hỗ trợ | Lỗi chuyển đổi hoặc unsupported feature | Dùng mapping/API theo tài liệu driver |

**Không có quy tắc JDBC rằng getter sai kiểu luôn ném lỗi.** Driver/database có thể chấp nhận ép kiểu ngầm, có thể trả kết quả đã được làm tròn, hoặc báo lỗi. Trường hợp nguy hiểm là **chuyển đổi thành công nhưng làm sai ý nghĩa dữ liệu**.

### 6.1. Dùng BigDecimal thay vì đọc tiền bằng double hoặc int

`BigDecimal` giữ số thập phân phù hợp các cột `DECIMAL`/`NUMERIC`:

```java
BigDecimal amount = rows.getBigDecimal("total_amount");
if (amount == null) {
    throw new SQLException("total_amount là SQL NULL");
}
System.out.println(amount.toPlainString());
```

Không dùng `getDouble()` chỉ vì dễ tính toán nếu ứng dụng cần giá trị tiền chính xác theo thập phân. Đồng thời, `BigDecimal` không thay thế kiểm tra `precision/scale` ở DB và quy tắc làm tròn nghiệp vụ.

### 6.2. Dùng kiểu thời gian phù hợp

Với JDBC 4.2 và driver hỗ trợ, đọc:

```java
LocalDate issuedOn =
        rows.getObject("issued_on", LocalDate.class);

LocalDateTime reviewedAt =
        rows.getObject("reviewed_at", LocalDateTime.class);

OffsetDateTime eventTime =
        rows.getObject("event_time", OffsetDateTime.class);
```

Đoạn rút gọn giả định đã import `java.time.LocalDate`, `LocalDateTime` và `OffsetDateTime`, đồng thời các cột có kiểu SQL phù hợp (như `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`). **Không phải mọi driver hỗ trợ tất cả chuyển đổi trên mọi kiểu cột.** Kiểu `LocalDateTime` không mang timezone; `OffsetDateTime` mang offset. Chọn dựa trên ý nghĩa dữ liệu và kiểm thử với môi trường thực tế.

Nếu ứng dụng đọc cột thời gian thành `String` rồi tự chuyển, cần chỉ rõ định dạng và timezone. Đừng phụ thuộc chuỗi ngày giờ do driver tự định dạng vì biểu diễn có thể thay đổi theo DB và cấu hình.

### 6.3. Chuyển đổi enum và số nguyên có quy tắc

Nếu database lưu `VARCHAR` như `PAID`, `DRAFT` hoặc `CANCELED`, trước hết lấy chuỗi và ánh xạ rõ ràng:

```java
enum InvoiceStatus {
    DRAFT, PAID, CANCELED
}

String raw = rows.getString("status");
if (raw == null) {
    throw new SQLException("status là SQL NULL");
}
final InvoiceStatus status;
try {
    status = InvoiceStatus.valueOf(raw);
} catch (IllegalArgumentException unknown) {
    throw new SQLException("Giá trị status ngoài tập cho phép", unknown);
}
```

Mã không đưa dữ liệu đầu vào vào thông điệp lỗi, tránh vô tình log một giá trị nhạy cảm. Nếu database có mã trạng thái theo quy ước khác tên enum Java, nên dùng bảng ánh xạ rõ ràng thay vì dựa trên `valueOf()`.

Với cột số có miền hợp lệ riêng (ví dụ phần trăm 0–100), việc `getInt()` thành công vẫn chưa bảo đảm đúng nghiệp vụ. Kiểm tra miền giá trị sau khi đọc, tách lỗi **chuyển kiểu kỹ thuật** khỏi lỗi **ràng buộc miền dữ liệu**.

## 7. SQL NULL và wasNull(): lỗi âm thầm thường gặp

Getter trả kiểu nguyên thủy như `getInt()`, `getLong()`, `getBoolean()` không thể trả Java `null`. Khi giá trị SQL là `NULL`, getter có thể trả `0` hoặc `false`; gọi `wasNull()` để biết giá trị vừa đọc có phải `NULL` hay không.

```java
int discount = rows.getInt("discount_pct");
Integer discountOrNull = rows.wasNull() ? null : discount;

boolean approved = rows.getBoolean("approved");
Boolean approvedOrNull = rows.wasNull() ? null : approved;
```

**`wasNull()` chỉ nói về giá trị được đọc bởi getter gần nhất.** Vì thế, phải kiểm tra **ngay sau getter cần xét**, trước khi gọi getter khác:

```java
// Đúng: mỗi getter primitive được kiểm tra ngay lập tức.
long accountId = rows.getLong("account_id");
boolean accountIdNull = rows.wasNull();

int points = rows.getInt("points");
boolean pointsNull = rows.wasNull();
```

Không làm như sau:

```java
long accountId = rows.getLong("account_id");
String name = rows.getString("name");
boolean accountIdNull = rows.wasNull(); // Sai mục tiêu: xét name.
```

Getter trả đối tượng như `getString()`, `getBigDecimal()` hoặc `getDate()` thường trả `null` khi SQL NULL, nên có thể kiểm tra trực tiếp kết quả. `getObject(column, Integer.class)` là một lựa chọn tiện cho kiểu wrapper **nếu driver hỗ trợ chuyển đổi đó**, nhưng không cần ép mọi truy vấn phải dùng getter dạng tổng quát.

Tránh chuyển SQL NULL thành giá trị mặc định như `0` hoặc `""` nếu hợp đồng nghiệp vụ cần phân biệt; làm vậy khiến dữ liệu thực sự bị thiếu mất dấu vết trong model.

## 8. Khi nào lỗi nằm ở SQL, khi nào lỗi nằm ở mapper?

Quá trình đọc dữ liệu có thể chia thành các điểm kiểm tra:

```text
SQL query / SELECT projection
          |
          v
PreparedStatement.executeQuery()
          |
          +-- SQL tham chiếu cột không tồn tại ở database?
          |       -> SQLException khi thực thi truy vấn
          |
          v
ResultSetMetaData / column labels
          |
          +-- Thiếu alias / nhãn bị trùng?
          |       -> Lỗi hợp đồng mapper; báo sớm bằng kiểm tra metadata
          |
          v
ResultSet.next()
          |
          +-- false -> Không có hàng; projection vẫn có thể hợp lệ
          |
          v
getXxx() / getObject()
          |
          +-- Chuyển đổi kiểu không hợp lệ?
          |       -> SQLException hoặc kết quả có thể mất ngữ nghĩa
          |
          +-- SQL NULL?
                  -> Kiểm tra bằng wasNull() hoặc so sánh null
```

Khi gặp lỗi, cần sửa đúng điểm phát sinh:

- **Sai schema hoặc câu SQL**: rà soát tên cột vật lý, migration, database mà ứng dụng đang kết nối và cú pháp `SELECT`.
- **Sai alias**: thống nhất projection và mapper; thay đổi alias là thay đổi hợp đồng đọc dữ liệu.
- **Trùng alias**: đặt nhãn riêng rõ ý nghĩa thay vì chỉ đổi cách gọi getter.
- **Sai kiểu dữ liệu**: điều chỉnh getter cho đúng schema hoặc sửa schema/migration nếu kiểu cột không đáp ứng nghiệp vụ.
- **NULL không được dự kiến**: kiểm tra nguyên nhân dữ liệu; dùng constraint ở DB và kiểm tra ở Java theo hợp đồng.
- **Truy vấn không trả hàng**: xử lý `Optional.empty()`/“không tìm thấy” tùy API, không gộp vào lỗi thiếu cột.

Một thay đổi database đôi khi làm mã Java tiếp tục chạy nhưng trả dữ liệu sai: ví dụ một cột đổi từ `DECIMAL` sang văn bản và driver vẫn cho phép chuyển chuỗi số; hoặc hai cột cùng nhãn khiến mapper chọn giá trị thứ nhất. Vì vậy, **kiểm tra kiểu và nhãn ở mức hợp đồng** quan trọng hơn việc chỉ chạy thử một hàng dữ liệu.

## 9. Thu thập thông tin lỗi mà không làm lộ dữ liệu

Khi bắt `SQLException`, nên ghi nhận tối thiểu **vị trí thao tác**, **SQLState**, **mã lỗi của nhà cung cấp** và stack trace:

```java
try {
    return invoiceReader.findById(invoiceId);
} catch (SQLException error) {
    logger.error(
            "Không đọc được invoice; SQLState={}, vendorCode={}",
            error.getSQLState(),
            error.getErrorCode(),
            error);
    throw error;
}
```

Đoạn minh họa giả định `invoiceReader`, `invoiceId` và `logger` được cung cấp bởi ứng dụng; logger chấp nhận đối tượng `Throwable` để giữ stack trace. Không ghi mật khẩu, token, dữ liệu cột nhạy cảm hoặc toàn bộ tham số của câu SQL vào log.

Một số trường hợp cần đọc thêm `SQLException.getNextException()`, `getCause()` hoặc `getSuppressed()` (ví dụ lỗi khi đóng `ResultSet`). Những thông tin đó bổ sung ngữ cảnh cho lỗi chính; **không nên** chỉ log `error.getMessage()` rồi bỏ cấu trúc ngoại lệ.

Khi điều tra sai alias trong môi trường thử nghiệm, có thể ghi **metadata của projection** thay vì dữ liệu hàng:

```java
ResultSetMetaData meta = rows.getMetaData();
for (int i = 1; i <= meta.getColumnCount(); i++) {
    logger.debug(
            "Column #{}: label={}, sqlType={}",
            i,
            meta.getColumnLabel(i),
            meta.getColumnTypeName(i));
}
```

Việc log này cần kiểm soát mức log; nhãn cột cũng có thể tiết lộ chi tiết schema. Trên production, ưu tiên thông báo thiếu nhãn/tên truy vấn định danh nội bộ thay vì dump mọi thông tin không cần thiết.

## 10. Kiểm thử tích hợp cho trường hợp sai projection và sai kiểu

Tạo dữ liệu thử nghiệm gồm nhiều trạng thái: hàng đầy đủ, hàng có cột nullable, hàng không tồn tại và dữ liệu nằm ở biên của phạm vi số. Các kiểm thử quan trọng nên chạy trên **driver và loại database thực tế** vì phép chuyển kiểu ngầm và chi tiết thông báo lỗi khác nhau giữa các hệ quản trị.

| Kịch bản | Kết quả cần kiểm chứng |
|---|---|
| SQL trả đủ alias bắt buộc và một hàng hợp lệ | Ánh xạ ra model với đúng ID, tên, tiền, ngày |
| SQL trả 0 hàng nhưng projection đúng | Trả `Optional.empty()`, không báo thiếu cột |
| Mapper yêu cầu `invoice_id` nhưng SQL chỉ có `id` | Báo thiếu nhãn cần thiết |
| Projection có hai cột cùng nhãn `id` | Bộ kiểm tra metadata phát hiện trùng, không đọc nhầm |
| SQL tham chiếu cột bảng không tồn tại | Truy vấn thất bại ở tầng thực thi SQL |
| `discount_pct` bằng SQL `NULL` | Model chứa Java `null`, không đồng nhất thành `0` |
| `discount_pct` bằng `0` thật | Model chứa `0`, khác `NULL` |
| Giá trị `DECIMAL` có phần thập phân | `getBigDecimal()` đọc lại đúng giá trị |
| Dữ liệu văn bản `"PAID"` được đọc bằng getter số | Phát hiện lỗi kiểu hoặc kiểm tra trước, không chấp nhận chuyển đổi sai |
| `BIGINT` sát/vượt giới hạn `int` | Đọc bằng `getLong()` và kiểm tra miền giá trị |
| `DATE` được ánh xạ sang `LocalDate` | Kết quả đúng theo driver, không bị đổi ngày |
| Rename alias trong SQL | Test hợp đồng mapper thất bại rõ ràng |

**Đừng cố ý dựa vào một lỗi chuyển đổi để kiểm tra bảo mật.** Cách driver xử lý getter sai kiểu là vấn đề tương thích dữ liệu; bảo vệ SQL injection thuộc về `PreparedStatement` và kiểm soát cấu trúc SQL, còn kiểm soát giá trị thuộc về schema/validation.

## 11. Bài tập vận dụng

**Tình huống 1 — Thiếu cột.** Truy vấn chỉ chọn `id` và `name`, nhưng mapper gọi `getString("email")`. Vì sao việc bảng gốc **có** cột `email` không làm getter hoạt động? Hãy chỉ ra nơi cần sửa.

*Gợi ý:* `ResultSet` chỉ chứa projection của `SELECT`, không tự mang mọi cột từ bảng.

**Tình huống 2 — Sai nhãn.** SQL dùng `SELECT total_amount AS amount`, mapper gọi `getBigDecimal("total_amount")`. Hãy đề xuất hai cách sửa, trong đó một cách giữ nguyên alias phục vụ API.

*Gợi ý:* Đồng bộ getter với `amount` hoặc giữ một alias tên `total_amount` theo hợp đồng.

**Tình huống 3 — Hai cột có cùng tên.** `SELECT a.id, b.id FROM ...` trả hai số hợp lệ. Vì sao `getLong("id")` có thể trả sai ID mà không báo lỗi? Viết lại phần `SELECT` cho rõ nghĩa.

**Tình huống 4 — SQL NULL.** Cột `approved` là `BOOLEAN NULLABLE`. `getBoolean("approved")` trả `false`. Làm sao phân biệt `false` thật với `NULL`, và nên kiểm tra ở thời điểm nào?

**Tình huống 5 — Giá tiền.** `getInt("price")` chạy thành công với giá `18.75` trên một driver. Vì sao vẫn sai về mặt hợp đồng dữ liệu? Đề xuất getter và kiểu Java thay thế.

**Tình huống 6 — Không có hàng.** Một truy vấn sai alias nhưng luôn trả 0 hàng trong môi trường test. Nếu mapper chỉ xác minh alias sau `rows.next()`, vấn đề gì bị bỏ sót?

*Gợi ý:* Dùng `getMetaData()` trước khi duyệt hàng để kiểm tra projection.

**Tình huống 7 — DATE/TIMESTAMP.** Một driver không hỗ trợ `getObject(column, LocalDate.class)` cho kiểu cột đang dùng. Hãy giải thích vì sao cần xác định kiểu SQL thật và một phương án thay thế khi cột là `DATE`.

**Ghi nhớ:** Đọc `ResultSet` đúng nghĩa gồm **ba kiểm tra riêng**: projection có đủ cột/nhãn cần thiết; mỗi nhãn ánh xạ đến **đúng cột**; và getter chuyển dữ liệu sang **đúng kiểu Java, có xét SQL NULL**. Khi không đạt, hãy phát hiện sớm bằng metadata và ánh xạ tường minh, thay vì bắt mọi `SQLException` rồi tự đặt giá trị mặc định.

