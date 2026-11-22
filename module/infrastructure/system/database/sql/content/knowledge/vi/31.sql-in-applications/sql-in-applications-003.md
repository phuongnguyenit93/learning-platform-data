# Ánh xạ cột kết quả, bí danh và kiểu dữ liệu ứng dụng

Một câu SQL có thể chạy đúng trong database nhưng ứng dụng vẫn đọc sai kết quả. Nguyên nhân thường nằm ở hợp đồng giữa cột kết quả SQL và kiểu dữ liệu chương trình: mapper tìm sai tên alias, hai bảng JOIN có cột trùng tên, SQL NULL bị đọc thành 0, NUMERIC bị ép sang double hoặc timestamp bị hiểu sai múi giờ.

Ví dụ:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    o.amount AS total_amount,
    c.name AS customer_name
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id;
~~~

Kết quả có bốn nhãn cột: `order_id`, `order_status`, `total_amount` và `customer_name`. Java có thể ánh xạ chúng vào một DTO:

~~~java
public record OrderView(
    long orderId,
    String orderStatus,
    BigDecimal totalAmount,
    String customerName
) {}
~~~

Tên cột vật lý, alias trong SELECT và thuộc tính Java là ba khái niệm riêng. Người thiết kế cần xác định rõ cách chuyển đổi giữa chúng.

Bài học thuộc module **Database SQL**, chương **SQL trong ứng dụng**, chủ đề **“Ánh xạ cột kết quả, bí danh và kiểu dữ liệu ứng dụng”**. Phần thực hành dùng PostgreSQL và Java/JDBC; các khác biệt quan trọng giữa driver và DBMS cũng được giải thích.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt tên cột vật lý, tên biểu thức, alias và column label trong ResultSet.
2. Đặt alias ổn định để ánh xạ SELECT vào DTO/record.
3. Hiểu `getColumnLabel` và `getColumnName` trong JDBC.
4. Tránh lỗi cột trùng tên khi JOIN, SELECT * và identifier có chữ hoa/chữ thường.
5. Đọc ResultSet theo label hoặc index đúng cách.
6. Chọn kiểu Java cho INTEGER, BIGINT, NUMERIC, BOOLEAN, DATE, TIMESTAMP, UUID, JSON, ARRAY và BINARY.
7. Xử lý SQL NULL bằng wrapper, `getObject` và `wasNull`.
8. Giữ độ chính xác dữ liệu tiền bằng `BigDecimal`.
9. Phân biệt TIMESTAMP không timezone và TIMESTAMP WITH TIME ZONE.
10. Ánh xạ aggregate, CASE, CAST, UNION và biểu thức tính toán.
11. Thiết kế mapper thủ công, DTO/record và ORM projection.
12. Dùng metadata để chẩn đoán nhãn và kiểu cột.
13. Phân biệt kiểu tham số PreparedStatement với kiểu cột đầu ra ResultSet.
14. Tránh lỗi mapping thường gặp trong ứng dụng nhiều DBMS/driver.

## 2. Hợp đồng kết quả giữa SQL và ứng dụng

Một SELECT trả dữ liệu và metadata cho mỗi cột. Metadata thường gồm:

- Column label: nhãn trong tập kết quả.
- Column name: tên cột mà driver báo cáo.
- SQL/JDBC type: kiểu dữ liệu.
- Precision/scale: độ chính xác và số chữ số thập phân.
- Nullability: thông tin cột có thể NULL hay không, nếu driver cung cấp.
- Column index: vị trí cột; JDBC đánh số từ 1.

Ví dụ:

~~~sql
SELECT
    id AS order_id,
    amount * 1.10 AS amount_with_tax,
    CURRENT_DATE AS report_date
FROM orders;
~~~

| Vị trí | Nguồn | Label | Ý nghĩa |
|---:|---|---|---|
| 1 | `id` | `order_id` | ID đơn hàng |
| 2 | Biểu thức tính toán | `amount_with_tax` | Tiền sau thuế |
| 3 | `CURRENT_DATE` | `report_date` | Ngày báo cáo |

### 2.1. Ba tầng tên

Với bảng:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(12,2)
);
~~~

và query:

~~~sql
SELECT
    id AS order_id,
    amount AS total_amount
FROM orders;
~~~

Ta có:

1. Tên vật lý: `orders.id` và `orders.amount`.
2. Alias/label: `order_id` và `total_amount`.
3. Thuộc tính Java: `orderId` và `totalAmount`.

Tên ba tầng không bắt buộc giống nhau. Một quy ước phổ biến là tên SQL snake_case, alias ổn định và Java camelCase.

### 2.2. Alias chỉ tồn tại trong kết quả query

~~~sql
SELECT amount AS total_amount
FROM orders;
~~~

không đổi tên cột vật lý `amount` trong bảng. Alias không phải migration và không thay đổi schema.

## 3. Đặt alias bằng AS

Dùng alias cho cột, biểu thức, hàm aggregate và CASE:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    o.amount AS order_amount,
    o.amount * 0.08 AS estimated_tax,
    o.amount * 1.08 AS amount_after_tax
FROM orders AS o;
~~~

Nếu không đặt alias cho expression, driver có thể báo một label tự sinh hoặc khó dùng. Mapper dựa vào label tự sinh thường dễ hỏng khi query được refactor.

### 3.1. Alias cho aggregate

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MAX(amount) AS largest_order
FROM orders
GROUP BY customer_id;
~~~

Nên đặt tên rõ cho COUNT, SUM, AVG, MAX. Không phụ thuộc vào nhãn mặc định của biểu thức.

### 3.2. Alias cho CASE

~~~sql
SELECT
    id AS order_id,
    CASE
        WHEN amount >= 200000 THEN 'HIGH'
        WHEN amount >= 100000 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_band
FROM orders;
~~~

Ứng dụng đọc `amount_band` như một cột kết quả. Các nhánh CASE cần có kiểu kết quả chung; nếu trộn kiểu dữ liệu, CAST tường minh để giữ contract.

### 3.3. Alias trong JOIN

~~~sql
SELECT
    o.id AS order_id,
    c.id AS customer_id,
    o.status AS order_status,
    c.name AS customer_name
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id;
~~~

Đặt alias duy nhất ngay trong query để mapper không nhầm `o.id` và `c.id`.

## 4. Column label và column name trong JDBC

JDBC ResultSetMetaData cung cấp hai phương thức:

- `getColumnLabel(index)` trả nhãn cột, thường là alias trong SELECT; nếu không có alias thì thường là tên cột.
- `getColumnName(index)` trả tên cột theo cách driver báo cáo. Với expression hoặc một số view, giá trị này không nhất thiết là alias mà mapper muốn dùng.

Ví dụ:

~~~sql
SELECT
    o.id AS order_id,
    o.amount * 1.08 AS gross_amount
FROM orders AS o;
~~~

~~~java
ResultSetMetaData md = rs.getMetaData();

for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.println(
        "label=" + md.getColumnLabel(i)
        + ", name=" + md.getColumnName(i)
    );
}
~~~

Mapper thủ công nên dùng **column label** đã được query đặt rõ:

~~~java
long id = rs.getLong("order_id");
BigDecimal gross = rs.getBigDecimal("gross_amount");
~~~

### 4.1. Đọc theo label hay index?

Theo label:

~~~java
String status = rs.getString("order_status");
~~~

Theo index:

~~~java
String status = rs.getString(2);
~~~

Dùng label dễ đọc và ít phụ thuộc thứ tự cột. Dùng index có thể phù hợp trong mapper sinh tự động hoặc query cố định, nhưng thêm một cột vào đầu SELECT có thể làm code đọc sai dữ liệu.

**Khuyến nghị:** mapper viết tay nên ưu tiên label duy nhất; chỉ dùng index khi thứ tự cột được quản lý chặt và có kiểm tra.

### 4.2. JDBC index bắt đầu từ 1

~~~java
rs.getObject(1); // cột đầu tiên
rs.getObject(0); // không hợp lệ trong JDBC
~~~

Đừng nhầm với Java List hoặc array, vốn bắt đầu từ index 0.

## 5. Chữ hoa/chữ thường và quoted identifier

PostgreSQL chuẩn hóa identifier không quote về chữ thường:

~~~sql
SELECT id AS OrderId
FROM orders;
~~~

Label không quote thường trở thành `orderid`. Nếu muốn giữ nguyên chữ hoa:

~~~sql
SELECT id AS "OrderId"
FROM orders;
~~~

thì phải quote và mapper phải dùng label đúng như driver trả về.

### 5.1. Quy ước dễ bảo trì

Một quy ước thường ít bất ngờ:

~~~sql
SELECT
    id AS order_id,
    created_at AS created_at
FROM orders;
~~~

Java:

~~~java
long orderId = rs.getLong("order_id");
LocalDateTime createdAt =
    rs.getObject("created_at", LocalDateTime.class);
~~~

Alias có khoảng trắng như `"Total Amount"` hoặc ký tự đặc biệt thường làm code mapper bất tiện. Chỉ dùng khi có yêu cầu rõ.

## 6. Tránh SELECT * trong contract ứng dụng

~~~sql
SELECT *
FROM orders;
~~~

`SELECT *` hữu ích khi khám phá dữ liệu, nhưng có rủi ro khi dùng làm contract lâu dài:

1. Thêm cột vào bảng làm metadata result thay đổi.
2. Đổi thứ tự cột có thể làm mapper theo index đọc sai.
3. JOIN nhiều bảng tạo nhãn trùng.
4. Cột mới có thể vô tình lộ dữ liệu nhạy cảm.
5. Ứng dụng phụ thuộc schema vật lý thay vì tập dữ liệu được thiết kế.

Nên liệt kê cột và alias:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    o.amount AS order_amount
FROM orders AS o;
~~~

SELECT * vẫn có chỗ dùng trong script nội bộ hoặc khi row type được kiểm soát, nhưng không nên là mặc định cho API/repository.

## 7. Cột trùng tên trong JOIN

Query:

~~~sql
SELECT *
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id;
~~~

có thể trả nhiều cột cùng label `id`, `created_at` hoặc `status`. Đọc `rs.getLong("id")` sẽ mơ hồ; cách driver xử lý label trùng có thể khiến mapper lấy nhầm cột.

Sửa:

~~~sql
SELECT
    o.id AS order_id,
    o.created_at AS order_created_at,
    c.id AS customer_id,
    c.created_at AS customer_created_at
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id;
~~~

Mỗi label nên duy nhất trong toàn result set.

### 7.1. Nested DTO không tự sinh từ alias

Nếu muốn:

~~~java
public record CustomerSummary(
    long customerId,
    String customerName,
    List<OrderSummary> orders
) {}
~~~

một JOIN thường trả một hàng cho mỗi đơn, lặp dữ liệu customer. Mapper cần gom các hàng theo customerId rồi xây danh sách orders. JDBC không tự tạo nested object chỉ vì alias có dấu chấm hoặc tên lồng nhau.

## 8. Bảng ánh xạ SQL sang Java

Kiểu Java phù hợp phụ thuộc SQL type, driver và DBMS. Bảng dưới là gợi ý phổ biến:

| SQL type | Java/JDBC thường dùng | Lưu ý |
|---|---|---|
| SMALLINT | Short / `getShort` | Số nguyên 16-bit |
| INTEGER | Integer / `getInt` | Số nguyên 32-bit |
| BIGINT | Long / `getLong` | Số nguyên 64-bit |
| NUMERIC, DECIMAL | BigDecimal / `getBigDecimal` | Giữ precision và scale |
| REAL | Float / `getFloat` | Số thực đơn |
| DOUBLE PRECISION | Double / `getDouble` | Số thực dấu phẩy động |
| BOOLEAN | Boolean / `getBoolean` | Cần xử lý NULL |
| CHAR, VARCHAR, TEXT | String / `getString` | Văn bản |
| DATE | LocalDate | Chỉ ngày |
| TIME | LocalTime | Giờ trong ngày |
| TIMESTAMP không timezone | LocalDateTime | Ngày giờ không gắn offset |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime (driver hỗ trợ) | Instant/offset |
| BINARY, VARBINARY | byte[] | Dữ liệu nhị phân |
| BLOB | Blob hoặc stream | Có thể rất lớn |
| CLOB | Clob hoặc Reader | Văn bản lớn |
| UUID | UUID (driver hỗ trợ) | Ví dụ PostgreSQL |
| JSON/JSONB | String hoặc driver-specific object | Parse bằng thư viện JSON |
| SQL ARRAY | java.sql.Array | Phụ thuộc kiểu phần tử/driver |
| ENUM | Thường String | Chuyển sang enum Java có kiểm soát |

Không coi bảng này là cam kết mọi driver trả cùng một class Java cho mọi DBMS. Khi dùng kiểu đặc thù, hãy kiểm tra metadata và tài liệu driver đang triển khai.

## 9. INTEGER, BIGINT và COUNT

Nếu SQL trả BIGINT, Java thường nên dùng long/Long:

~~~sql
SELECT id AS order_id
FROM orders;
~~~

~~~java
long orderId = rs.getLong("order_id");
~~~

PostgreSQL `COUNT(*)` trả BIGINT:

~~~sql
SELECT COUNT(*) AS order_count
FROM orders;
~~~

~~~java
long orderCount = rs.getLong("order_count");
~~~

Đừng map COUNT sang Integer chỉ vì dữ liệu hiện tại nhỏ. Chọn kiểu theo contract SQL và miền giá trị tối đa.

### 9.1. SUM có kiểu khác kiểu cột nguồn

Trong PostgreSQL, kiểu SUM phụ thuộc kiểu đầu vào; ví dụ SUM của INTEGER trả BIGINT, SUM của BIGINT trả NUMERIC. AVG cũng có quy tắc kiểu riêng.

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount
FROM orders;
~~~

Không suy đoán output type từ kiểu cột gốc. Dùng metadata hoặc CAST nếu ứng dụng yêu cầu kiểu cụ thể.

## 10. NUMERIC/DECIMAL và BigDecimal

Với tiền hoặc số cần độ chính xác thập phân, ưu tiên `BigDecimal`:

~~~sql
SELECT amount AS total_amount
FROM orders;
~~~

~~~java
BigDecimal amount = rs.getBigDecimal("total_amount");
~~~

Số thực dấu phẩy động như double biểu diễn nhị phân, không thể biểu diễn chính xác mọi phân số thập phân:

~~~java
double value = 0.1 + 0.2;
System.out.println(value); // gần 0.30000000000000004
~~~

Dùng BigDecimal từ chuỗi:

~~~java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
BigDecimal sum = a.add(b);
~~~

Tránh `new BigDecimal(0.1)` vì nó nhận giá trị nhị phân gần đúng của double.

### 10.1. Precision và scale

`NUMERIC(12,2)` cho tối đa 12 chữ số với 2 chữ số thập phân. Java BigDecimal giữ giá trị thập phân và scale theo driver.

Nếu cần chuẩn hóa scale:

~~~java
BigDecimal normalized =
    amount.setScale(2, RoundingMode.HALF_UP);
~~~

Chọn rounding mode theo quy tắc nghiệp vụ; đừng làm tròn ngầm trong mapper.

### 10.2. SUM trên tập rỗng

~~~sql
SELECT SUM(amount) AS total_amount
FROM orders
WHERE customer_id = -1;
~~~

Nếu không có đầu vào, PostgreSQL trả SUM là SQL NULL. Java `getBigDecimal` trả null. Nếu contract muốn 0:

~~~sql
SELECT COALESCE(SUM(amount), 0)::NUMERIC(14,2)
       AS total_amount
FROM orders
WHERE customer_id = -1;
~~~

NULL có thể mang nghĩa “không có dữ liệu”, khác với tổng tiền bằng 0; chỉ dùng COALESCE khi đúng nghiệp vụ.

## 11. SQL NULL và Java null

Primitive Java `int`, `long`, `boolean` không chứa null. JDBC getter primitive có thể trả giá trị mặc định khi SQL column NULL; cần kiểm tra.

~~~java
int raw = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : raw;
~~~

`wasNull()` phải được gọi ngay sau getter cần kiểm tra vì nó phản ánh giá trị cột vừa đọc gần nhất.

Với JDBC 4.2 và driver hỗ trợ, có thể dùng:

~~~java
Integer quantity =
    rs.getObject("quantity", Integer.class);

Boolean approved =
    rs.getObject("approved", Boolean.class);
~~~

Nếu SQL NULL, kết quả reference type có thể là Java null.

### 11.1. NULL khác 0, false và chuỗi rỗng

| Giá trị SQL | Java | Ý nghĩa |
|---|---|---|
| SQL NULL | null | Không có giá trị |
| INTEGER 0 | Integer 0 | Số 0 |
| BOOLEAN FALSE | Boolean false | Sai |
| VARCHAR `''` | String rỗng | Có chuỗi, độ dài 0 |
| VARCHAR `'0'` | String `"0"` | Một ký tự |

Không tự chuyển NULL thành 0, false, chuỗi rỗng hoặc một ngày giả nếu contract không quy định.

### 11.2. Optional

Có thể đóng gói nullable field:

~~~java
Optional<Integer> quantity =
    Optional.ofNullable(
        rs.getObject("quantity", Integer.class)
    );
~~~

Optional phù hợp với giá trị có thể vắng trong một số API; không nhất thiết phải thay mọi thuộc tính DTO bằng Optional.

## 12. BOOLEAN ba trạng thái

PostgreSQL BOOLEAN có TRUE, FALSE và NULL. Java primitive boolean chỉ có true/false.

~~~java
Boolean approved =
    rs.getObject("approved", Boolean.class);
~~~

Nếu dùng `getBoolean`:

~~~java
boolean raw = rs.getBoolean("approved");
Boolean approved = rs.wasNull() ? null : raw;
~~~

Đừng mặc định NULL = FALSE. Trong nghiệp vụ, NULL có thể nghĩa “chưa được xét”, FALSE có thể nghĩa “đã xét và từ chối”.

## 13. DATE, TIME và TIMESTAMP

### 13.1. DATE

~~~sql
SELECT order_date AS order_date
FROM orders;
~~~

Java:

~~~java
LocalDate orderDate =
    rs.getObject("order_date", LocalDate.class);
~~~

LocalDate biểu diễn ngày, không có giờ hay timezone.

### 13.2. TIME

~~~sql
SELECT TIME '09:30:00' AS opening_time;
~~~

Java có thể dùng `LocalTime`.

### 13.3. TIMESTAMP không timezone

PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` lưu ngày giờ không gắn offset:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00'
       AS local_created_at;
~~~

Java thường dùng `LocalDateTime`:

~~~java
LocalDateTime localCreatedAt =
    rs.getObject("local_created_at", LocalDateTime.class);
~~~

Không tự coi LocalDateTime là UTC. Nếu giá trị có ý nghĩa theo một vùng cụ thể, áp dụng ZoneId ở tầng domain.

### 13.4. TIMESTAMP WITH TIME ZONE

PostgreSQL `TIMESTAMPTZ` lưu một instant; cách hiển thị phụ thuộc timezone session. Với PostgreSQL JDBC hiện đại, có thể đọc bằng OffsetDateTime:

~~~java
OffsetDateTime createdAt =
    rs.getObject("created_at", OffsetDateTime.class);

Instant instant = createdAt.toInstant();
~~~

PostgreSQL không lưu nguyên tên vùng timezone ban đầu như `Asia/Ho_Chi_Minh` bên trong timestamptz. Nếu nghiệp vụ cần giữ vùng timezone do người dùng chọn, lưu ZoneId riêng.

### 13.5. Không nhầm LocalDateTime với instant

LocalDateTime là ngày giờ địa phương chưa có timezone. Một thời điểm tuyệt đối cần instant hoặc offset/timezone có quy tắc chuyển đổi. Mapping sai có thể làm lệch thời điểm thanh toán, lịch hẹn hoặc báo cáo.

### 13.6. java.sql.Timestamp

API/driver cũ có thể dùng:

~~~java
Timestamp timestamp = rs.getTimestamp("created_at");
LocalDateTime local = timestamp.toLocalDateTime();
~~~

Cần hiểu semantics của cột và timezone của driver/session. Không coi đoạn này là phép chuyển đổi phổ quát cho mọi TIMESTAMP/TIMESTAMPTZ.

## 14. UUID, JSON, ARRAY, ENUM và BINARY

### 14.1. UUID

PostgreSQL JDBC hiện đại có thể hỗ trợ:

~~~java
UUID customerId =
    rs.getObject("customer_id", UUID.class);
~~~

Nếu driver không hỗ trợ kiểu đích, đọc String rồi dùng `UUID.fromString` sau khi xác thực.

### 14.2. JSON/JSONB

Một cách dễ portable là CAST về text:

~~~sql
SELECT profile_json::TEXT AS profile_json
FROM customers;
~~~

Java:

~~~java
String json = rs.getString("profile_json");
CustomerProfile profile =
    objectMapper.readValue(json, CustomerProfile.class);
~~~

Cột SQL NULL khác JSON literal `null` trong payload. Driver PostgreSQL có thể cung cấp object đặc thù như PGobject; dùng kiểu đó làm ứng dụng phụ thuộc driver.

### 14.3. ARRAY

PostgreSQL ARRAY có thể đọc bằng `java.sql.Array`:

~~~java
Array sqlArray = rs.getArray("tags");
try {
    String[] tags = (String[]) sqlArray.getArray();
} finally {
    sqlArray.free();
}
~~~

Kiểu phần tử và mảng nhiều chiều cần kiểm tra driver. Giải phóng tài nguyên khi hoàn tất.

### 14.4. ENUM

Có thể đọc enum PostgreSQL dưới dạng String rồi chuyển:

~~~java
String rawStatus = rs.getString("status");
OrderStatus status = OrderStatus.valueOf(rawStatus);
~~~

Nếu database thêm enum value mà Java chưa biết, valueOf có thể ném exception. Dùng rollout tương thích hoặc mapper có nhánh UNKNOWN/OTHER nếu nghiệp vụ cho phép.

### 14.5. BINARY/BLOB/CLOB

- Dữ liệu nhỏ có thể đọc bằng `getBytes`.
- BLOB lớn nên cân nhắc stream/Blob.
- CLOB lớn nên cân nhắc Reader/Clob.

Không nạp payload nhiều MB vào byte[] hoặc String nếu không cần thiết; chú ý đóng tài nguyên và giới hạn bộ nhớ.

## 15. CAST để ổn định output type

Aggregate, CASE và biểu thức có thể trả kiểu khác kiểu cột nguồn. Nếu contract yêu cầu kiểu cụ thể, CAST tường minh:

~~~sql
SELECT
    COUNT(*)::BIGINT AS order_count,
    COALESCE(SUM(amount), 0)::NUMERIC(14,2)
        AS total_amount,
    AVG(amount)::NUMERIC(14,4)
        AS average_amount
FROM orders;
~~~

PostgreSQL dùng `::type`; cú pháp chuẩn SQL:

~~~sql
CAST(expression AS type)
~~~

Tên kiểu vẫn có thể khác giữa DBMS.

### 15.1. CASE

~~~sql
SELECT
    CASE
        WHEN amount > 100000 THEN 'HIGH'
        ELSE 'LOW'
    END AS amount_band
FROM orders;
~~~

Các nhánh phải có kiểu tương thích để DBMS xác định output type. CAST tường minh khi trộn numeric/text/NULL.

### 15.2. COALESCE

~~~sql
COALESCE(SUM(amount), 0) AS total_amount
~~~

đổi NULL thành 0. Kiểu kết quả được suy luận từ các đối số; nếu API cần NUMERIC(14,2), CAST rõ ràng.

### 15.3. UNION

~~~sql
SELECT id AS item_id, amount AS item_amount
FROM orders

UNION ALL

SELECT id, amount
FROM archived_orders;
~~~

Output labels thường lấy từ SELECT đầu tiên. Mọi SELECT cần cùng số cột và kiểu tương thích. Đổi alias ở SELECT đầu có thể làm mapper hỏng.

## 16. JDBC mapper cho DTO/record

Ví dụ:

~~~java
public record OrderView(
    long orderId,
    String status,
    BigDecimal amount
) {}

public static OrderView mapOrder(ResultSet rs)
        throws SQLException {
    return new OrderView(
        rs.getLong("order_id"),
        rs.getString("order_status"),
        rs.getBigDecimal("total_amount")
    );
}
~~~

SQL:

~~~sql
SELECT
    id AS order_id,
    status AS order_status,
    amount AS total_amount
FROM orders
WHERE id = ?;
~~~

Gọi:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            OrderView order = mapOrder(rs);
        }
    }
}
~~~

### 16.1. ResultSet là cursor

Sau executeQuery, cursor thường đứng trước hàng đầu. Gọi `rs.next()` để chuyển vào hàng đầu tiên. Nếu không có hàng, next trả false. Không đọc cột trước khi next thành công.

### 16.2. try-with-resources

Đóng ResultSet và PreparedStatement đúng lifecycle. Không trả ResultSet đã đóng ra tầng UI hoặc giữ cursor mở trong thời gian người dùng tương tác.

### 16.3. Danh sách rỗng khác null

Nếu query không có hàng, repository thường nên trả empty List thay vì null:

~~~java
List<OrderView> results = new ArrayList<>();
while (rs.next()) {
    results.add(mapOrder(rs));
}
return results;
~~~

Caller có thể duyệt danh sách mà không cần kiểm tra null.

## 17. Mapping kết quả JOIN

SQL:

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    o.amount AS order_amount,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.id = ?;
~~~

DTO:

~~~java
public record OrderCustomerView(
    long orderId,
    String orderStatus,
    BigDecimal orderAmount,
    long customerId,
    String customerName
) {}
~~~

Mapper:

~~~java
public static OrderCustomerView mapOrderCustomer(
        ResultSet rs
) throws SQLException {
    return new OrderCustomerView(
        rs.getLong("order_id"),
        rs.getString("order_status"),
        rs.getBigDecimal("order_amount"),
        rs.getLong("customer_id"),
        rs.getString("customer_name")
    );
}
~~~

### 17.1. LEFT JOIN tạo cột nullable

~~~sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.amount AS order_amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.id;
~~~

Khách chưa có đơn vẫn có một hàng kết quả, nhưng cột của order là SQL NULL. Map:

~~~java
Long orderId =
    rs.getObject("order_id", Long.class);
~~~

không dùng primitive long nếu cần phân biệt “không có đơn” với ID 0.

### 17.2. JOIN một-nhiều cần gom nhóm

Nếu một customer có nhiều orders, customer fields lặp trên nhiều hàng. Để tạo CustomerSummary với List<OrderSummary>, mapper cần group theo customerId bằng Map. JDBC không tự dựng nested DTO từ alias.

## 18. PreparedStatement input khác ResultSet output

PreparedStatement bind giá trị đầu vào:

~~~java
String sql = """
    SELECT
        id AS order_id,
        amount AS total_amount
    FROM orders
    WHERE customer_id = ?
      AND order_date >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setObject(2, startDate);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            BigDecimal amount =
                rs.getBigDecimal("total_amount");
        }
    }
}
~~~

- `setLong`, `setBigDecimal`, `setDate`, `setObject` thiết lập tham số.
- `getLong`, `getBigDecimal`, `getDate`, `getObject` đọc cột output.

Đây là hai chiều API khác nhau.

### 18.1. Bind SQL NULL

~~~java
ps.setNull(1, Types.INTEGER);
~~~

hoặc, khi driver hỗ trợ:

~~~java
ps.setObject(1, null, Types.INTEGER);
~~~

Cung cấp JDBC type khi bind NULL giúp driver/database suy luận đúng kiểu.

### 18.2. Placeholder không thay tên cột

~~~sql
SELECT ? FROM orders;
~~~

Placeholder đại diện **giá trị**, không đại diện identifier. Nếu truyền chuỗi `"amount"`, query thường trả chuỗi đó như một giá trị cho mỗi hàng, chứ không chọn cột amount.

Nếu cần chọn cột động, dùng allowlist identifier hợp lệ rồi xây query có kiểm soát; không nối input tùy ý.

## 19. Aggregate và DTO thống kê

~~~sql
SELECT
    customer_id AS customer_id,
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0) AS total_amount,
    AVG(amount) AS average_amount
FROM orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

~~~java
public record CustomerOrderStats(
    long customerId,
    long orderCount,
    BigDecimal totalAmount,
    BigDecimal averageAmount
) {}
~~~

~~~java
public static CustomerOrderStats mapStats(ResultSet rs)
        throws SQLException {
    return new CustomerOrderStats(
        rs.getLong("customer_id"),
        rs.getLong("order_count"),
        rs.getBigDecimal("total_amount"),
        rs.getBigDecimal("average_amount")
    );
}
~~~

COUNT(*) PostgreSQL trả BIGINT. SUM/AVG có kiểu riêng. Nếu amount nullable và toàn bộ giá trị trong nhóm là NULL, AVG có thể NULL; DTO cần nullable BigDecimal hoặc query có COALESCE theo nghiệp vụ.

### 19.1. COUNT và SUM trên tập rỗng

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM orders
WHERE customer_id = -1;
~~~

Không GROUP BY, PostgreSQL trả một hàng: COUNT bằng 0, SUM bằng NULL. Đây là hai ngữ nghĩa khác nhau.

## 20. Metadata để chẩn đoán

~~~java
ResultSetMetaData md = rs.getMetaData();

for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.printf(
        "%d label=%s name=%s type=%d typeName=%s "
        + "class=%s precision=%d scale=%d nullable=%d%n",
        i,
        md.getColumnLabel(i),
        md.getColumnName(i),
        md.getColumnType(i),
        md.getColumnTypeName(i),
        md.getColumnClassName(i),
        md.getPrecision(i),
        md.getScale(i),
        md.isNullable(i)
    );
}
~~~

Metadata giúp phát hiện:

- Alias sai chính tả hoặc khác chữ hoa/chữ thường.
- Label trùng.
- Kiểu SUM/AVG không như dự kiến.
- DECIMAL precision/scale.
- Cột nullable được map vào primitive.
- Kiểu vendor-specific do driver cung cấp.

`isNullable` có thể báo unknown với một số expression, view hoặc driver. Metadata hỗ trợ chẩn đoán, không thay thế contract query và test dữ liệu NULL thực tế.

## 21. DTO, Entity và ORM projection

- **Entity** thường mô tả đối tượng persistence có định danh và vòng đời gắn với bảng.
- **DTO/projection** mô tả hình dạng dữ liệu query cần trả về.
- Một DTO có thể chứa alias, aggregate, biểu thức và dữ liệu JOIN không tồn tại như một bảng vật lý.
- Không nên map một aggregate thiếu cột thành entity đầy đủ rồi giả định mọi thuộc tính entity hợp lệ.

Ví dụ entity:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "amount")
    private BigDecimal amount;
}
~~~

`@Column(name = "amount")` ánh xạ property entity tới cột vật lý. Nó không tự bảo đảm native query có alias `total_amount` sẽ map đúng property. Với native query, dùng constructor mapping, projection hoặc mapper rõ ràng theo framework.

### 21.1. Snake case sang camel case

Một số framework có cấu hình tự chuyển `order_id` sang `orderId`, nhưng JDBC thuần không tự làm việc này. Không dựa vào quy tắc ngầm nếu ứng dụng chưa cấu hình và kiểm thử.

### 21.2. Alias là API contract

Nếu mapper đang đọc `total_amount` và query đổi thành `revenue`, đó là thay đổi contract. Cần cập nhật mapper và consumer cùng lúc, hoặc tạo version/query mới nếu nhiều ứng dụng dùng chung.

Không chỉ alias mà cả kiểu, nullability và thứ tự semantics cũng là contract. Đổi LEFT JOIN thành INNER JOIN có thể thay đổi tập hàng và nullability dù alias không đổi.

## 22. Khác biệt driver/DBMS

JDBC thống nhất API đọc kết quả nhưng không loại bỏ khác biệt kiểu dữ liệu giữa database.

### 22.1. PostgreSQL

- NUMERIC → BigDecimal.
- BIGINT → Long.
- UUID được PostgreSQL JDBC hiện đại hỗ trợ dưới dạng UUID.
- JSON/JSONB có thể trả kiểu driver-specific; đọc text rồi parse thường dễ portable hơn.
- TIMESTAMPTZ có thể đọc OffsetDateTime với driver hiện đại.
- ARRAY dùng java.sql.Array; kiểu phần tử phụ thuộc driver.

### 22.2. MySQL/MariaDB

- DECIMAL nên đọc BigDecimal.
- BOOLEAN có thể được biểu diễn qua TINYINT(1) hoặc kiểu tương ứng theo driver/configuration.
- TIMESTAMP, DATETIME và timezone có semantics khác nhau; kiểm tra connector options.
- JSON có thể đọc String hoặc object đặc thù.
- Zero-date và cấu hình conversion có thể ảnh hưởng java.time.

### 22.3. SQL Server

- DECIMAL/NUMERIC map BigDecimal.
- UNIQUEIDENTIFIER có thể đọc qua UUID hoặc String tùy driver.
- DATETIME2 và DATETIMEOFFSET khác nhau; chọn kiểu Java đúng semantics.
- Một số kiểu như sql_variant hoặc hierarchyid cần hỗ trợ riêng.

### 22.4. Oracle

- NUMBER có thể map BigDecimal hoặc kiểu số khác tùy precision/scale/getter.
- Oracle DATE chứa cả ngày và thời gian, khác SQL DATE theo chuẩn.
- TIMESTAMP WITH TIME ZONE có API mapping riêng.
- CLOB/BLOB cần quản lý tài nguyên.
- REF CURSOR và object types có API driver riêng.

### 22.5. SQLite

SQLite có storage classes và type affinity linh hoạt. Kiểu khai báo trong bảng không đảm bảo mọi giá trị lưu trong cột đều có cùng biểu diễn nghiêm ngặt. Driver SQLite có thể map INTEGER/REAL/TEXT/BLOB theo quy tắc riêng. Xác định contract ở ứng dụng và test dữ liệu thật.

## 23. Ví dụ repository hoàn chỉnh

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public record OrderListItem(
    long orderId,
    String status,
    BigDecimal amount
) {}

public final class OrderRepository {

    public List<OrderListItem> findByCustomer(
            Connection connection,
            long customerId
    ) throws SQLException {

        String sql = """
            SELECT
                o.id AS order_id,
                o.status AS order_status,
                o.amount AS order_amount
            FROM orders AS o
            WHERE o.customer_id = ?
            ORDER BY o.id
            """;

        List<OrderListItem> result = new ArrayList<>();

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {

            ps.setLong(1, customerId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new OrderListItem(
                        rs.getLong("order_id"),
                        rs.getString("order_status"),
                        rs.getBigDecimal("order_amount")
                    ));
                }
            }
        }

        return result;
    }
}
~~~

Ví dụ thể hiện các nguyên tắc:

1. Chỉ SELECT các cột cần thiết.
2. Alias duy nhất, dễ đọc.
3. Bind parameter thay vì nối chuỗi.
4. NUMERIC đọc bằng BigDecimal.
5. Không có hàng thì trả empty list.
6. ResultSet/Statement được đóng tự động.
7. Không trả cursor ra tầng UI sau khi đóng statement.

## 24. Các lỗi mapping thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Column not found | Alias sai hoặc case khác | Kiểm tra getColumnLabel |
| Lấy nhầm cột JOIN | Label trùng | Alias duy nhất |
| Sai cột sau refactor | Dùng index cố định | Dùng label hoặc cập nhật mapper |
| NULL thành 0 | Primitive getter, thiếu wasNull | Wrapper/getObject |
| Sai tiền lẻ | Dùng double | BigDecimal |
| Tràn số | Dùng int cho BIGINT | Long |
| Timestamp lệch giờ | Nhầm local time với instant | LocalDateTime/OffsetDateTime/Instant đúng semantics |
| Unsupported conversion | Driver không hỗ trợ kiểu đích | Getter tương thích hoặc chuyển đổi rõ |
| JSON parse lỗi | SQL NULL và JSON null bị nhầm | Phân biệt hai trạng thái |
| Enum valueOf lỗi | DB có giá trị mới | Rollout tương thích/fallback |
| List null | Không có hàng | Trả empty list |
| Mapper hỏng sau đổi alias | Contract thay đổi | Cập nhật consumer/test |
| Entity thiếu field | Native query không trả đủ entity | Dùng DTO/projection |
| COUNT map Integer | COUNT là BIGINT | Long |
| SUM tập rỗng thành 0 ngoài ý muốn | COALESCE sai nghiệp vụ | Quy định NULL vs 0 |
| SELECT * lộ cột mới | Query phụ thuộc schema | Liệt kê cột tường minh |

## 25. Bài tập thực hành có lời giải

### Bài 1. Alias nào dùng trong JDBC?

~~~sql
SELECT id AS order_id FROM orders;
~~~

**Đáp án:** `rs.getLong("order_id")`. Alias là label của result set; cột vật lý vẫn là id.

### Bài 2. getColumnLabel hay getColumnName?

**Đáp án:** `getColumnLabel` phù hợp hơn để lấy alias mà mapper sử dụng. `getColumnName` báo tên cột theo driver.

### Bài 3. Hai cột id trong JOIN

~~~sql
SELECT o.id, c.id
FROM orders o
JOIN customers c ON c.id = o.customer_id;
~~~

**Đáp án:** đặt `o.id AS order_id` và `c.id AS customer_id`.

### Bài 4. JDBC column index bắt đầu từ đâu?

**Đáp án:** từ 1. `rs.getObject(1)` là cột đầu tiên.

### Bài 5. PostgreSQL BIGINT map kiểu nào?

**Đáp án:** long/Long; chọn wrapper nếu cột có thể NULL.

### Bài 6. COUNT(*) map Integer hay Long?

**Đáp án:** PostgreSQL COUNT trả BIGINT; dùng long/Long.

### Bài 7. Tiền NUMERIC map double hay BigDecimal?

**Đáp án:** BigDecimal để giữ độ chính xác thập phân.

### Bài 8. getInt đọc SQL NULL

**Đề:** quantity nullable, `getInt` trả 0. Làm sao phân biệt NULL?

**Đáp án:**

~~~java
int raw = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : raw;
~~~

Hoặc `getObject("quantity", Integer.class)` nếu driver hỗ trợ.

### Bài 9. NULL, 0 và chuỗi rỗng

**Đáp án:** là ba giá trị khác nhau; mapper không tự gộp chúng.

### Bài 10. SUM trên tập rỗng

**Đáp án:** PostgreSQL SUM trả NULL khi không có đầu vào; Java BigDecimal getter trả null. Dùng COALESCE chỉ khi contract yêu cầu 0.

### Bài 11. LEFT JOIN không có hàng con

**Đáp án:** cột phía bảng con là SQL NULL; dùng Long nullable thay vì primitive long nếu cần phân biệt.

### Bài 12. DATE map Java nào?

**Đáp án:** LocalDate.

### Bài 13. TIMESTAMP không timezone map Java nào?

**Đáp án:** LocalDateTime; không tự coi nó là UTC.

### Bài 14. PostgreSQL TIMESTAMPTZ map Java nào?

**Đáp án:** OffsetDateTime với PostgreSQL JDBC hiện đại; có thể chuyển sang Instant.

### Bài 15. Alias camelCase không quote

~~~sql
SELECT id AS OrderId FROM orders;
~~~

**Đáp án:** PostgreSQL chuẩn hóa identifier không quote thành chữ thường. Dùng `"OrderId"` nếu cần giữ case, hoặc ưu tiên order_id.

### Bài 16. CASE output

~~~sql
SELECT CASE WHEN amount > 100000
            THEN 'HIGH' ELSE 'LOW'
       END AS amount_band
FROM orders;
~~~

**Đáp án:** label là amount_band; đọc bằng getString.

### Bài 17. Aggregate có nên alias?

**Đáp án:** có. COUNT/SUM/AVG nên có label rõ và ổn định.

### Bài 18. JSONB đọc portable thế nào?

**Đáp án:** CAST sang TEXT, đọc String rồi parse bằng thư viện JSON; nếu dùng object đặc thù driver thì ứng dụng phụ thuộc driver.

### Bài 19. UUID PostgreSQL

**Đáp án:** có thể dùng `rs.getObject("customer_id", UUID.class)` với driver hiện đại; nếu không hỗ trợ, đọc String rồi parse.

### Bài 20. Đổi alias có ảnh hưởng mapper?

**Đáp án:** có. Đổi total_amount thành revenue là thay đổi contract với mapper đang tìm label cũ.

### Bài 21. SELECT * có rủi ro gì?

**Đáp án:** thay đổi schema có thể thêm cột, đổi thứ tự, lộ dữ liệu và tạo label trùng. Liệt kê cột rõ.

### Bài 22. Aggregate nên map vào Entity hay DTO?

**Đáp án:** thường dùng DTO/projection vì aggregate không phải entity đầy đủ.

### Bài 23. Placeholder có thay tên cột không?

**Đáp án:** không. Placeholder đại diện giá trị. Chọn identifier động bằng allowlist và query có kiểm soát.

### Bài 24. In metadata label và type

~~~java
ResultSetMetaData md = rs.getMetaData();
for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.println(
        i + " " + md.getColumnLabel(i)
        + " " + md.getColumnTypeName(i)
    );
}
~~~

**Đáp án:** lặp từ 1 đến columnCount; label lấy bằng getColumnLabel, tên kiểu SQL bằng getColumnTypeName.

### Bài 25. Chọn kiểu DTO

**Đề:** Output có order_id BIGINT, amount NUMERIC(12,2), order_date DATE, approved BOOLEAN nullable.

**Đáp án:**

~~~java
public record OrderProjection(
    Long orderId,
    BigDecimal amount,
    LocalDate orderDate,
    Boolean approved
) {}
~~~

Wrapper Long/Boolean thể hiện nullability; BigDecimal giữ độ chính xác; LocalDate chỉ biểu diễn ngày.

## 26. Checklist thiết kế mapping SQL → ứng dụng

Trước khi đưa query vào repository/service, hãy kiểm tra:

1. Mỗi cột có alias rõ ràng chưa?
2. Alias có duy nhất trong result set không?
3. Có phụ thuộc SELECT * hoặc expression label tự sinh không?
4. Mapper dùng label hay index? Contract có ổn định không?
5. Alias có phụ thuộc quoted identifier/case không?
6. JOIN có cột trùng tên không?
7. Kiểu COUNT/SUM/AVG/CASE/UNION đã được xác định chưa?
8. NUMERIC/DECIMAL có được đọc bằng BigDecimal không?
9. BIGINT có bị map vào int không?
10. Cột nullable có dùng wrapper/getObject/wasNull đúng không?
11. SQL NULL, JSON null, chuỗi rỗng và số 0 có phân biệt không?
12. DATE/TIME/TIMESTAMP có đúng semantics timezone không?
13. UUID/JSON/ARRAY/ENUM/BLOB có phụ thuộc driver nào?
14. Mapper xử lý đúng tập rỗng và LEFT JOIN NULL không?
15. DTO/projection có đúng hình dạng query không?
16. PreparedStatement bind đúng kiểu; NULL có JDBC type không?
17. Alias/type/nullability thay đổi có cập nhật consumer/test không?
18. Metadata có được kiểm tra khi driver trả kiểu bất thường?
19. ResultSet/Statement có đóng đúng lifecycle?
20. Đã test NULL, số lớn, timezone và dữ liệu biên?

## 27. Tổng kết

Ánh xạ cột kết quả là hợp đồng giữa SQL và ứng dụng. Một truy vấn đúng về dữ liệu vẫn có thể gây lỗi nếu label, kiểu, nullability hoặc semantics không khớp mapper.

- **Alias** xác định nhãn trong result set, không đổi tên cột vật lý. Dùng alias duy nhất, ổn định cho expression, aggregate và JOIN.
- **JDBC getColumnLabel** phù hợp để đọc alias; getColumnName không nên được coi là contract mapper. Column index bắt đầu từ 1.
- **Tránh SELECT *** cho API lâu dài; liệt kê cột để tránh thay đổi schema vô tình, duplicate labels và lộ dữ liệu.
- **Chọn Java type theo SQL type và miền giá trị:** BIGINT → Long, NUMERIC → BigDecimal, DATE → LocalDate, timestamp local → LocalDateTime, PostgreSQL timestamptz → OffsetDateTime với driver hiện đại.
- **Xử lý SQL NULL rõ ràng:** wrapper/getObject/wasNull; không đổi NULL thành 0 hoặc false nếu nghiệp vụ chưa quy định.
- **Driver matters:** UUID, JSON, ARRAY, BLOB và temporal types có khác biệt giữa DBMS/driver.
- **DTO/record/projection** mô tả hình dạng query; Entity thường phù hợp dữ liệu persistence đầy đủ hơn.
- **PreparedStatement input binding** khác ResultSet output mapping; placeholder dùng cho giá trị, không dùng để thay tên cột.
- Alias, kiểu và nullability là một phần API contract; thay đổi chúng cần cập nhật mapper và consumer.

Hãy thiết kế theo chuỗi **SELECT cột rõ ràng → alias duy nhất → kiểu SQL có chủ đích → mapper theo label → xử lý NULL, timezone và precision → DTO contract ổn định**, thay vì để driver tự suy đoán mọi thứ cho ứng dụng.
