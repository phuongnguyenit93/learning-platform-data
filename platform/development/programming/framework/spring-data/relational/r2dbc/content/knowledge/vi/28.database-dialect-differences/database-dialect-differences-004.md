# SQL Server: phân trang, kiểu dữ liệu và kết quả sinh ra

Khi dùng Spring Data R2DBC với Microsoft SQL Server, cần hiểu ba điểm riêng của hệ quản trị này: cú pháp phân trang, cách SQL Server biểu diễn kiểu dữ liệu và cách lấy lại giá trị được database sinh ra sau thao tác ghi. Những khác biệt này ảnh hưởng trực tiếp đến SQL, entity mapping, converter và hành vi của R2DBC driver.

Spring Data R2DBC cung cấp abstraction như repository, `R2dbcEntityTemplate` và `DatabaseClient`, nhưng SQL cuối cùng vẫn phải phù hợp với SQL Server và driver đang sử dụng, thường là R2DBC SQL Server driver (`r2dbc-mssql`). Phiên bản Spring Data, Spring Framework và driver có thể khác nhau về dialect, bind marker, codec và hỗ trợ generated values. Vì vậy, hãy kiểm tra dependency thực tế và chạy integration test trên SQL Server mục tiêu.

## 1. Kết nối và dialect SQL Server

Một R2DBC URL cho SQL Server thường có dạng:

```yaml
spring:
  r2dbc:
    url: r2dbc:mssql://sqlserver-host:1433/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Tên host, database, credentials, encryption và các tùy chọn TLS cần được cấu hình theo môi trường triển khai và phiên bản driver. Không hard-code mật khẩu trong source hoặc file cấu hình được commit.

Trong ứng dụng dùng nhiều database, tạo `ConnectionFactory`, `DatabaseClient`, `R2dbcEntityTemplate` và `R2dbcTransactionManager` tương ứng với SQL Server. Không dùng nhầm template của PostgreSQL/MySQL chỉ vì entity Java giống nhau. Dialect SQL Server chịu trách nhiệm tạo các phần SQL đặc thù mà Spring Data hỗ trợ, chẳng hạn giới hạn kết quả và bind marker.

`DatabaseClient` có thể dùng named parameter dạng `:name`; Spring chuyển chúng thành marker mà dialect/driver hiểu. Khi gọi R2DBC SPI trực tiếp qua `Connection.createStatement`, phải dùng cú pháp marker theo tài liệu của driver SQL Server. Không sao chép marker `$1` của PostgreSQL sang SQL Server hoặc giả định mọi driver đều dùng dấu `?`.

## 2. Phân trang bằng OFFSET và FETCH NEXT

SQL Server hỗ trợ phân trang theo offset bằng cú pháp `ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` từ SQL Server 2012. Câu lệnh phải có `ORDER BY`; `OFFSET/FETCH` không thể dùng như một giới hạn tùy ý nếu không xác định thứ tự hàng.

Ví dụ lấy trang đầu tiên gồm 20 đơn hàng mới nhất:

```sql
SELECT id, order_number, status, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
ORDER BY created_at DESC, id DESC
OFFSET 0 ROWS
FETCH NEXT 20 ROWS ONLY;
```

`created_at DESC` sắp xếp theo thời gian mới nhất. `id DESC` là tie-breaker để thứ tự vẫn xác định khi nhiều đơn hàng có cùng thời điểm. Nếu chỉ sắp xếp theo `created_at`, các hàng có timestamp giống nhau có thể đổi vị trí giữa những lần truy vấn.

Ví dụ trang thứ ba, mỗi trang 20 hàng:

```sql
SELECT id, order_number, status, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
ORDER BY created_at DESC, id DESC
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
```

`OFFSET` là số hàng bỏ qua trước khi bắt đầu trả kết quả. `FETCH NEXT` là số hàng tối đa của trang. Cần xác thực page size lớn hơn 0 và offset không âm trước khi thực thi.

### 2.1 Tính offset an toàn

Với page number bắt đầu từ 0, công thức là:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Không nên tính bằng `int` nếu dữ liệu có thể có nhiều trang. Dùng `long` và kiểm tra tràn số:

```java
long offset = Math.multiplyExact((long) pageNumber, pageSize);

if (pageNumber < 0 || pageSize <= 0) {
    throw new IllegalArgumentException("Invalid page request");
}
```

Trong code thực tế, kiểm tra giá trị trước khi tính offset để tránh đầu vào âm; `Math.multiplyExact` giúp phát hiện phép nhân vượt giới hạn `long`.

### 2.2 Dùng R2dbcEntityTemplate

Khi truy vấn entity và muốn tận dụng metadata mapping, có thể tạo `Query` với `Sort`, `offset` và `limit`:

```java
public Flux<PurchaseOrder> findOrderPage(
        UUID tenantId, int pageNumber, int pageSize) {

    if (pageNumber < 0 || pageSize <= 0) {
        return Flux.error(new IllegalArgumentException("Invalid page request"));
    }

    long offset = Math.multiplyExact((long) pageNumber, pageSize);

    Query query = Query.query(
            Criteria.where("tenantId").is(tenantId))
        .sort(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")))
        .offset(offset)
        .limit(pageSize);

    return ordersTemplate.select(query, PurchaseOrder.class);
}
```

Tên thuộc tính trong `Criteria` và `Sort` thường được Spring Data mapping sang tên cột theo metadata entity. Ví dụ `createdAt` có thể được ánh xạ thành `created_at` nếu naming strategy hoặc `@Column` quy định như vậy. Kiểm tra SQL được tạo trên phiên bản Spring Data đang dùng và xác nhận SQL Server dialect chuyển limit/offset thành cú pháp hợp lệ.

`R2dbcEntityTemplate.select(...)` trả về `Flux`, kể cả khi một trang có giới hạn số hàng. Nếu cần một object chứa nội dung trang và tổng số bản ghi, service có thể chạy thêm truy vấn count rồi ghép kết quả vào DTO riêng.

### 2.3 Dùng DatabaseClient với SQL tường minh

Khi cần SQL Server-specific query hoặc projection, `DatabaseClient` cho phép viết trực tiếp:

```java
Flux<OrderSummary> findPage(
        UUID tenantId, long offset, int pageSize) {

    return databaseClient.sql("""
            SELECT id, order_number, status, created_at
            FROM dbo.purchase_order
            WHERE tenant_id = :tenantId
            ORDER BY created_at DESC, id DESC
            OFFSET :offset ROWS
            FETCH NEXT :pageSize ROWS ONLY
            """)
        .bind("tenantId", tenantId)
        .bind("offset", offset)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_number", String.class),
            row.get("status", String.class),
            row.get("created_at", LocalDateTime.class)))
        .all();
}
```

Đoạn code minh họa named parameter của Spring `DatabaseClient`. Giá trị `offset` và `pageSize` được bind, còn tên bảng, tên cột và thứ tự sort được viết cố định. Trước khi gọi, service vẫn phải xác thực `offset >= 0` và `pageSize` trong giới hạn được ứng dụng cho phép.

Nếu dùng `DatabaseClient` được tạo thủ công từ `ConnectionFactory`, hãy bảo đảm cấu hình dialect phù hợp với SQL Server. Khi bind kiểu số hoặc thời gian, kiểu Java phải tương thích với codec của driver và kiểu cột.

## 3. Vì sao ORDER BY phải ổn định?

Phân trang offset dựa trên vị trí của hàng trong thứ tự kết quả. Nếu thứ tự không duy nhất, database có quyền trả các hàng đồng hạng theo thứ tự khác nhau ở những lần thực thi khác nhau.

Ví dụ không ổn định:

```sql
SELECT id, created_at
FROM dbo.purchase_order
ORDER BY created_at DESC
OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY;
```

Nếu nhiều hàng có cùng `created_at`, một hàng có thể xuất hiện ở trang trước trong lần gọi đầu và trang sau trong lần gọi tiếp theo. Hãy thêm khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

Một thứ tự ổn định giúp phân trang có thể lặp lại khi dữ liệu không đổi. Nó không ngăn dữ liệu mới được chèn hoặc bị xóa giữa hai lần request. Nếu dữ liệu thay đổi, offset của các trang sau có thể dịch chuyển và dẫn đến lặp hoặc bỏ sót hàng.

## 4. TOP và ROW_NUMBER trong SQL Server

`TOP` phù hợp khi chỉ cần lấy N hàng đầu theo một thứ tự:

```sql
SELECT TOP (20) id, order_number, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
ORDER BY created_at DESC, id DESC;
```

`TOP` không tự thay thế phân trang nhiều trang. Với trang đầu, `TOP` thường đơn giản. Với trang tiếp theo, dùng `OFFSET/FETCH` hoặc keyset pagination.

Trên hệ thống cũ hoặc khi cần biểu diễn thứ hạng trong CTE, có thể dùng `ROW_NUMBER()`:

```sql
WITH ranked_orders AS (
    SELECT
        id,
        order_number,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, id DESC
        ) AS row_number
    FROM dbo.purchase_order
    WHERE tenant_id = @tenantId
)
SELECT id, order_number, created_at
FROM ranked_orders
WHERE row_number BETWEEN @firstRow AND @lastRow
ORDER BY row_number;
```

`ROW_NUMBER()` đánh số hàng theo thứ tự trong `OVER`. Cần dùng cùng một thứ tự ổn định ở cửa sổ và kết quả cuối. CTE không bảo đảm thứ tự nếu câu `SELECT` bên ngoài không có `ORDER BY`.

## 5. Keyset pagination cho tập dữ liệu lớn

Offset pagination phải bỏ qua các hàng trước offset. Khi offset lớn, database có thể phải đọc/sắp xếp một lượng hàng đáng kể trước khi trả trang, ngay cả khi caller chỉ cần vài chục hàng cuối. Keyset pagination (seek pagination) dùng giá trị của hàng cuối trang trước để tìm tiếp, thường hiệu quả hơn trên bảng lớn có index phù hợp.

Giả sử kết quả được sắp xếp giảm dần theo `created_at` và `id`. Trang tiếp theo dùng cặp giá trị cuối trang trước:

```sql
SELECT TOP (@pageSize)
    id, order_number, created_at
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
  AND (
       created_at < @lastCreatedAt
       OR (created_at = @lastCreatedAt AND id < @lastId)
  )
ORDER BY created_at DESC, id DESC;
```

Điều kiện so sánh là phép so sánh từ điển trên cặp `(created_at, id)`. Với thứ tự giảm dần, trang kế tiếp có timestamp nhỏ hơn, hoặc timestamp bằng nhau nhưng ID nhỏ hơn.

Trang đầu không có cursor nên dùng câu query riêng không có điều kiện `lastCreatedAt/lastId`. Có thể đóng gói cursor trong response, chẳng hạn `nextCreatedAt` và `nextId`, rồi yêu cầu client gửi lại ở request sau.

### 5.1 Điều kiện để keyset hoạt động đúng

- Thứ tự sort phải xác định và kết thúc bằng một cột hoặc nhóm cột duy nhất.
- Các giá trị cursor phải được lấy từ hàng cuối cùng thực sự trả về.
- Điều kiện seek phải khớp hướng `ASC`/`DESC` của từng cột.
- Cần xử lý rõ cột nullable vì phép so sánh với `NULL` không cho kết quả true/false thông thường.
- Index nên hỗ trợ các cột lọc và thứ tự, ví dụ `(tenant_id, created_at DESC, id DESC)` nếu phù hợp workload.
- Cursor cần được kiểm tra và có thể ký/mã hóa nếu client không được phép tự thay đổi phạm vi truy vấn.

Keyset pagination không phù hợp nếu người dùng cần nhảy trực tiếp đến một số trang tùy ý mà không có cursor. Nó đặc biệt hữu ích cho feed, lịch sử, danh sách mới nhất và các luồng cuộn liên tục.

### 5.2 Xử lý cột sort có thể NULL

Nếu `created_at` có thể null, điều kiện `created_at < :lastCreatedAt` không bao gồm các hàng null. Hãy chọn một trong các cách:

- Đặt cột sort là `NOT NULL` nếu nghiệp vụ cho phép.
- Thêm một khóa sort phụ thể hiện nhóm null/non-null và đưa nhóm đó vào cursor.
- Chuẩn hóa biểu thức sort bằng `CASE`/giá trị thay thế, đồng thời dùng cùng biểu thức trong `ORDER BY` và điều kiện seek.

Không bỏ qua null behavior vì điều đó có thể khiến một số hàng không bao giờ xuất hiện trong các trang tiếp theo.

## 6. Tổng số hàng và đối tượng Page

Một trang thường cần cả dữ liệu hiện tại và tổng số hàng phù hợp. SQL Server có thể dùng `COUNT_BIG(*)` để đếm số lượng lớn hơn giới hạn của kiểu `int`:

```sql
SELECT COUNT_BIG(*)
FROM dbo.purchase_order
WHERE tenant_id = @tenantId
  AND status = @status;
```

`COUNT(*)` trả về `int` trong SQL Server; `COUNT_BIG(*)` trả về `bigint`. Với bảng lớn hoặc tổng số có thể vượt giới hạn `int`, ưu tiên `COUNT_BIG` và map về `Long`.

Một cách đơn giản là chạy hai query:

1. Query page với `ORDER BY/OFFSET/FETCH`.
2. Query count với cùng điều kiện `WHERE`.

Sau đó ghép kết quả thành DTO riêng, ví dụ `PageResult<T>` chứa `items`, `pageSize`, `offset` và `totalElements`. Reactive repository thường dùng `Flux`/`Mono`; không nên ép một API reactive phải trả `Page<T>` nếu việc đó khiến code phải block để lấy count.

Có thể ghép hai publisher bằng `Mono.zip` nếu mỗi query trả một giá trị tổng hợp:

```java
Mono<PageResult<OrderSummary>> loadPage(
        UUID tenantId, long offset, int pageSize) {

    Mono<List<OrderSummary>> items = findPage(tenantId, offset, pageSize)
        .collectList();

    Mono<Long> total = countOrders(tenantId);

    return Mono.zip(items, total)
        .map(tuple -> new PageResult<>(
            tuple.getT1(), offset, pageSize, tuple.getT2()));
}
```

`PageResult` và `countOrders` là abstraction của ứng dụng. Nếu hai query chạy độc lập dưới `READ_COMMITTED`, dữ liệu có thể thay đổi giữa lúc lấy page và count, khiến `items` và `totalElements` không phản ánh cùng một snapshot. Nếu cần snapshot nhất quán, hãy xác định transaction isolation và cấu hình database phù hợp, hoặc chấp nhận count mang tính gần đúng/được cập nhật riêng.

Một truy vấn có thể dùng `COUNT_BIG(*) OVER()` để trả tổng số cùng từng hàng trang. Tuy nhiên, nếu trang rỗng thì không có hàng để mang `total_count`; vì vậy cần cân nhắc cách xử lý trang vượt cuối. Window count cũng không thay thế việc xác định thứ tự ổn định.

## 7. Các kiểu số trong SQL Server

SQL Server có nhiều kiểu số với miền giá trị và độ chính xác khác nhau. Bảng sau đưa ra lựa chọn Java thường gặp; codec cụ thể cần được xác nhận với phiên bản R2DBC driver:

| Kiểu SQL Server | Kiểu Java thường dùng | Lưu ý |
|---|---|---|
| `bit` | `Boolean` | Có thể nhận `NULL` nếu cột nullable; dùng wrapper thay primitive khi cần null. |
| `tinyint` | `Short` hoặc `Integer` | SQL Server `tinyint` là unsigned 0–255; `byte` Java signed không biểu diễn đủ miền. Kiểm tra codec driver. |
| `smallint` | `Short` | Số nguyên 16-bit có dấu. |
| `int` | `Integer` | Số nguyên 32-bit. |
| `bigint` | `Long` | Số nguyên 64-bit. |
| `decimal(p,s)` / `numeric(p,s)` | `BigDecimal` | SQL Server hỗ trợ precision tối đa 38; chọn scale theo nghiệp vụ. |
| `smallmoney` / `money` | `BigDecimal` | Có scale cố định; với tiền tệ nghiệp vụ thường ưu tiên `decimal`. |
| `real` | `Float` | Số dấu phẩy động độ chính xác đơn. |
| `float` | `Double` | Độ chính xác phụ thuộc precision; không dùng cho tính tiền cần chính xác thập phân. |

### 7.1 Decimal và tiền tệ

`decimal(p,s)`/`numeric(p,s)` phù hợp cho giá trị cần độ chính xác thập phân. SQL Server cho phép precision tối đa 38 chữ số. Ví dụ:

```sql
amount DECIMAL(19, 4) NOT NULL
```

Trong đó `19` là tổng số chữ số và `4` là số chữ số sau dấu thập phân. Java `BigDecimal` phù hợp để giữ giá trị thập phân, nhưng ứng dụng vẫn cần thống nhất scale, rounding mode và giới hạn nghiệp vụ trước khi ghi.

Không nên dùng `float`/`double` cho tiền tệ hoặc số dư. Cũng không nên chọn `money` chỉ vì tên kiểu có vẻ phù hợp; `decimal(p,s)` thường giúp kiểm soát precision/scale rõ ràng hơn và dễ đồng bộ giữa các hệ quản trị.

### 7.2 NULL và primitive Java

Nếu cột `bit`, `int`, `bigint` hoặc `decimal` cho phép `NULL`, hãy dùng `Boolean`, `Integer`, `Long`, `BigDecimal` hoặc kiểu tham chiếu tương ứng. Primitive Java không biểu diễn được trạng thái null. Không tự đổi null thành 0/false nếu nghiệp vụ cần phân biệt “chưa biết” với giá trị bằng 0.

## 8. Chuỗi Unicode và kiểu văn bản

SQL Server phân biệt nhóm kiểu chuỗi không Unicode và Unicode:

| Kiểu SQL | Ý nghĩa | Gợi ý |
|---|---|---|
| `char(n)` | Chuỗi độ dài cố định, không Unicode | Mã ngắn có độ dài cố định khi phù hợp. |
| `varchar(n)` | Chuỗi biến độ dài, không Unicode theo code page/collation | Chọn khi dữ liệu và collation cho phép. |
| `nchar(n)` | Chuỗi độ dài cố định Unicode | Dữ liệu Unicode độ dài cố định. |
| `nvarchar(n)` | Chuỗi biến độ dài Unicode | Thường phù hợp tên, địa chỉ và văn bản đa ngôn ngữ. |
| `varchar(max)` | Văn bản dài không Unicode | Dùng khi cần nội dung dài và không cần giới hạn nhỏ. |
| `nvarchar(max)` | Văn bản dài Unicode | Dùng cho nội dung Unicode lớn. |

Trong Java, các kiểu này thường được biểu diễn bằng `String`. Với tiếng Việt hoặc dữ liệu đa ngôn ngữ, `nvarchar`/`nvarchar(max)` thường là lựa chọn an toàn nếu không có lý do rõ ràng để dùng `varchar` cùng collation/code page tương ứng.

SQL Server có quy tắc collation ảnh hưởng so sánh, sắp xếp, phân biệt hoa thường và dấu. Một truy vấn so sánh chuỗi có thể có kết quả khác khi database hoặc cột dùng collation khác nhau. Không giả định `String.equals()` trong Java và phép so sánh SQL có semantics giống hệt nhau.

Với `nvarchar(n)`, tham số `n` biểu diễn số cặp byte/code unit theo quy tắc SQL Server, không đơn giản là số ký tự hiển thị cho mọi ký tự Unicode bổ sung. Cần chọn độ dài cột dựa trên giới hạn nghiệp vụ và kiểm tra dữ liệu thực tế. Với `varchar(max)`/`nvarchar(max)`, cần cân nhắc kích thước payload, bộ nhớ và hiệu năng index.

## 9. Kiểu UUID và dữ liệu nhị phân

SQL Server dùng `uniqueidentifier` để lưu GUID. Trong Java, kiểu `UUID` là biểu diễn tự nhiên:

```sql
id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY
```

R2DBC driver cần hỗ trợ codec giữa `uniqueidentifier` và `UUID`. Nếu dùng driver/phiên bản không hỗ trợ trực tiếp, cần converter hoặc biểu diễn chuỗi có quy ước nhất quán. Không tự chuyển byte order của UUID nếu chưa hiểu định dạng mà driver/database sử dụng.

Các kiểu `binary(n)`, `varbinary(n)` và `varbinary(max)` thường ánh xạ vào `byte[]` hoặc kiểu binary do driver cung cấp. Dữ liệu lớn có thể cần streaming hoặc lưu ngoài database thay vì tải toàn bộ vào một mảng byte.

SQL Server `rowversion` là giá trị nhị phân 8 byte được database tự sinh mỗi khi hàng được insert/update. Tên cũ `timestamp` là synonym của `rowversion`; nó **không phải ngày giờ**. Có thể đọc nó như dữ liệu nhị phân (`byte[]` hoặc kiểu driver hỗ trợ) và dùng làm token concurrency nếu code xử lý đúng semantics.

## 10. Ngày giờ: date, time, datetime2 và datetimeoffset

SQL Server có nhiều kiểu ngày giờ; chọn sai kiểu có thể làm mất precision hoặc múi giờ:

| Kiểu SQL Server | Ý nghĩa | Kiểu Java thường dùng |
|---|---|---|
| `date` | Ngày lịch, không có giờ | `LocalDate` |
| `time(p)` | Giờ trong ngày, precision 0–7 | `LocalTime` |
| `datetime2(p)` | Ngày và giờ, không chứa offset | `LocalDateTime` |
| `datetimeoffset(p)` | Ngày giờ kèm UTC offset | `OffsetDateTime` |
| `datetime` | Kiểu ngày giờ cũ, precision thấp hơn | `LocalDateTime` |
| `smalldatetime` | Ngày giờ với độ chính xác đến phút | `LocalDateTime` |

`datetime2` thường được ưu tiên hơn `datetime` cho dữ liệu ngày giờ mới vì có miền ngày rộng hơn và precision cao hơn. `datetime` có bước làm tròn xấp xỉ 1/300 giây, nên giá trị có thể được làm tròn về các phần mili giây gần nhất. `datetime2(7)` hỗ trợ độ chính xác đến 100 nanosecond theo độ chính xác của SQL Server.

`datetime2` không lưu múi giờ. Nếu ứng dụng dùng `Instant`, hãy thống nhất quy ước lưu UTC và chuyển đổi rõ ràng qua `OffsetDateTime`/`LocalDateTime` theo driver. `datetimeoffset` lưu ngày giờ cùng offset, phù hợp khi cần giữ offset tại thời điểm ghi; nó không lưu tên vùng múi giờ như `Asia/Ho_Chi_Minh` hay quy tắc DST của vùng đó.

Ví dụ schema:

```sql
CREATE TABLE dbo.audit_entry (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    occurred_at DATETIMEOFFSET(7) NOT NULL,
    business_date DATE NOT NULL,
    local_time TIME(7) NULL
);
```

Java entity có thể dùng `OffsetDateTime`, `LocalDate` và `LocalTime` tương ứng. Khả năng codec cụ thể vẫn cần kiểm tra với R2DBC SQL Server driver. Không dựa vào chuyển đổi ngầm giữa `Instant`, `LocalDateTime` và `OffsetDateTime` nếu quy ước timezone chưa được định nghĩa.

## 11. Các kiểu SQL Server đặc thù

Một số kiểu khác cần chú ý:

| Kiểu | Mục đích | Lưu ý mapping |
|---|---|---|
| `xml` | Lưu tài liệu XML | Có thể cần `String`, `Clob` hoặc codec riêng tùy driver. |
| `sql_variant` | Lưu giá trị thuộc nhiều kiểu SQL | Khó ánh xạ thành một kiểu Java cố định; nên tránh trong domain model nếu có thể. |
| `geometry` / `geography` | Dữ liệu không gian | Thường cần thư viện/codec spatial tương ứng. |
| `hierarchyid` | Cấu trúc phân cấp | Kiểu vendor-specific, cần mapping riêng. |
| `table`-valued parameter | Truyền tập dữ liệu như tham số thủ tục | Khả năng hỗ trợ phụ thuộc driver và API; không đồng nhất với bind một `List` thông thường. |
| `rowversion` | Token phiên bản nhị phân tự sinh | Không phải timestamp thời gian; không tự ghi giá trị vào cột. |

Với kiểu đặc thù, kiểm tra driver có Java type/codec tương ứng không. Nếu không, cân nhắc converter sang kiểu đơn giản, dùng SQL projection hoặc tách kiểu vendor-specific ở adapter persistence thay vì để domain model phụ thuộc trực tiếp vào lớp driver.

## 12. IDENTITY: khóa tự tăng trong SQL Server

SQL Server thường tạo khóa số tự tăng bằng thuộc tính `IDENTITY(seed, increment)`:

```sql
CREATE TABLE dbo.customer (
    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    email NVARCHAR(320) NOT NULL,
    display_name NVARCHAR(200) NOT NULL
);
```

Khi insert, ứng dụng không truyền cột `id`; database tự tạo giá trị:

```sql
INSERT INTO dbo.customer (email, display_name)
VALUES (N'an@example.com', N'An');
```

Với Spring Data R2DBC, entity có thể khai báo:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String email;
    private String displayName;
}
```

Khi entity được nhận diện là mới và `id` chưa có giá trị, thao tác insert có thể yêu cầu database sinh ID. Hãy sử dụng entity được phát ra từ `save`:

```java
return customerRepository.save(customer)
    .map(saved -> saved.getId());
```

Điều này đặc biệt quan trọng với entity immutable: `save` có thể trả về một instance mới chứa generated ID. Không giả định object đầu vào luôn được mutate tại chỗ.

ID `IDENTITY` không bảo đảm liên tục không có khoảng trống. Rollback, lỗi insert, cache identity hoặc thao tác đồng thời có thể làm dãy ID bị khuyết. Không dùng ID tự tăng để suy ra số lượng bản ghi hoặc thứ tự thời gian chính xác.

## 13. Lấy giá trị sinh ra bằng OUTPUT INSERTED

SQL Server hỗ trợ `OUTPUT INSERTED.<column>` để trả về giá trị của hàng sau thao tác `INSERT` hoặc `UPDATE`:

```sql
INSERT INTO dbo.customer (email, display_name)
OUTPUT INSERTED.id, INSERTED.created_at
VALUES (@P0, @P1);
```

`OUTPUT INSERTED.id` trả về ID do `IDENTITY` sinh ra. Có thể yêu cầu thêm cột có default constraint hoặc computed column nếu database/driver hỗ trợ trả về cột đó.

Với `DatabaseClient`, có thể viết SQL tường minh và map hàng được trả về:

```java
Mono<CreatedCustomer> insertCustomer(String email, String name) {
    return databaseClient.sql("""
            INSERT INTO dbo.customer (email, display_name)
            OUTPUT INSERTED.id, INSERTED.created_at
            VALUES (:email, :displayName)
            """)
        .bind("email", email)
        .bind("displayName", name)
        .map((row, metadata) -> new CreatedCustomer(
            row.get("id", Long.class),
            row.get("created_at", LocalDateTime.class)))
        .one();
}
```

Ví dụ minh họa named parameter của Spring `DatabaseClient`; không hard-code `@P0`/`@P1` vào câu SQL khi đang dùng named parameter. Framework/dialect chuyển placeholder sang dạng driver cần. Khi viết SQL trực tiếp ở tầng SPI, dùng marker đúng theo phiên bản R2DBC SQL Server driver.

### 13.1 OUTPUT với trigger

SQL Server có một giới hạn quan trọng: `OUTPUT` không có `INTO` không được dùng trên bảng có trigger đang bật cho thao tác DML tương ứng. Khi bảng có trigger, có thể cần ghi kết quả `OUTPUT` vào table variable rồi select lại:

```sql
DECLARE @inserted TABLE (
    id BIGINT,
    created_at DATETIME2(7)
);

INSERT INTO dbo.customer (email, display_name)
OUTPUT INSERTED.id, INSERTED.created_at
INTO @inserted (id, created_at)
VALUES (@P0, @P1);

SELECT id, created_at FROM @inserted;
```

Ngoài ra, giá trị trong `OUTPUT INSERTED` phản ánh hàng sau DML nhưng trước khi AFTER trigger thực thi. Nếu trigger tiếp tục thay đổi hàng và ứng dụng cần giá trị cuối cùng sau trigger, hãy truy vấn lại hàng trong cùng transaction hoặc dùng cách thiết kế phù hợp với trigger.

### 13.2 Generated values qua Spring Data và driver

`R2dbcEntityTemplate` và repository có thể dùng khả năng generated-value của dialect/driver để lấy ID khi insert. Việc tự động trả về cột nào và cách triển khai phụ thuộc phiên bản Spring Data R2DBC cùng driver SQL Server.

Khi cần cột sinh ra ngoài ID, hoặc khi driver/dialect không trả về đúng cột, hãy kiểm tra hỗ trợ `Statement.returnGeneratedValues(...)` và SQL Server `OUTPUT`. Không giả định API generated values hoạt động giống PostgreSQL `RETURNING`; đó là cú pháp khác nhau.

## 14. SCOPE_IDENTITY và các cách lấy ID khác

Một cách cũ để lấy identity trong cùng SQL scope là:

```sql
INSERT INTO dbo.customer (email, display_name)
VALUES (@P0, @P1);

SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS id;
```

`SCOPE_IDENTITY()` trả identity cuối cùng được tạo trong cùng scope. Nó an toàn hơn `@@IDENTITY` trong tình huống trigger tạo một identity khác, vì `@@IDENTITY` có thể trả giá trị do trigger sinh ra. `IDENT_CURRENT('table')` không giới hạn theo session và có thể trả ID của một session khác, vì vậy không dùng để lấy ID của insert vừa thực hiện.

Với R2DBC, nếu dùng `SCOPE_IDENTITY()`, hai câu lệnh phải được thực thi trong đúng connection và scope phù hợp. Dùng một statement batch hoặc transaction/connection được quản lý rõ ràng; không gửi hai query độc lập qua hai lần acquire connection rồi giả định chúng cùng scope.

`OUTPUT INSERTED.id` thường thể hiện ý định rõ hơn vì trả generated value trực tiếp từ câu DML. Tuy nhiên, trigger và driver support có thể ảnh hưởng cách dùng, như đã nêu ở phần trên.

## 15. SEQUENCE và default constraint

SQL Server cũng hỗ trợ sequence độc lập với bảng:

```sql
CREATE SEQUENCE dbo.order_number_seq
    AS BIGINT
    START WITH 1000
    INCREMENT BY 1;

CREATE TABLE dbo.purchase_order (
    id BIGINT NOT NULL PRIMARY KEY
        DEFAULT NEXT VALUE FOR dbo.order_number_seq,
    order_number NVARCHAR(40) NOT NULL
);
```

Ứng dụng có thể bỏ qua cột `id` khi insert để default constraint lấy giá trị từ sequence. Hoặc có thể gọi `NEXT VALUE FOR` để lấy số trước khi insert nếu nghiệp vụ cần biết mã trước khi tạo hàng.

Sequence không thuộc transaction theo cách rollback giá trị đã cấp. Nếu transaction rollback, giá trị sequence đã lấy vẫn có thể bị tiêu thụ và tạo khoảng trống. Tương tự identity, không giả định số thứ tự liên tục.

Sequence phù hợp khi nhiều bảng cần dùng chung một dãy số hoặc khi muốn tách bộ cấp số khỏi một bảng cụ thể. `IDENTITY` đơn giản hơn khi mỗi bảng có khóa tự tăng riêng.

## 16. DEFAULT, computed column và giá trị do database sinh

Ngoài identity, SQL Server có thể sinh giá trị bằng default constraint, computed column hoặc trigger:

```sql
CREATE TABLE dbo.purchase_order (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    order_number NVARCHAR(40) NOT NULL,
    created_at DATETIME2(7) NOT NULL
        CONSTRAINT DF_purchase_order_created_at
        DEFAULT SYSUTCDATETIME(),
    normalized_number AS UPPER(order_number) PERSISTED
);
```

- `created_at` được gán bởi default constraint khi insert không truyền giá trị.
- `normalized_number` là computed column, database tính từ `order_number`.
- `id` được sinh từ identity.

Nếu ứng dụng cần trả các giá trị này ngay sau insert, dùng generated values/`OUTPUT` nếu driver và dialect hỗ trợ. Nếu không, truy vấn lại theo khóa vừa nhận được trong cùng transaction. Đừng tự tính lại `normalized_number` trong Java rồi giả định nó luôn giống collation/function SQL Server.

`SYSUTCDATETIME()` trả thời gian UTC dạng `datetime2`; nếu cần lưu offset, schema và cách chuyển đổi cần được thiết kế rõ. `GETDATE()` trả thời gian local của SQL Server host dưới dạng `datetime`; không dùng lẫn hai hàm nếu hệ thống cần một quy ước thời gian nhất quán.

## 17. rowversion và optimistic concurrency

SQL Server `rowversion` là token nhị phân tự tăng ở cấp database khi hàng được insert/update. Nó hữu ích để phát hiện dữ liệu đã thay đổi kể từ lúc đọc:

```sql
CREATE TABLE dbo.inventory (
    product_id BIGINT PRIMARY KEY,
    available INT NOT NULL,
    row_version ROWVERSION NOT NULL
);
```

Khi đọc, ứng dụng giữ `row_version`. Khi cập nhật, dùng giá trị đó trong predicate:

```sql
UPDATE dbo.inventory
SET available = :available
OUTPUT INSERTED.row_version
WHERE product_id = :productId
  AND row_version = :expectedVersion;
```

Nếu không có hàng nào được cập nhật, version đã thay đổi hoặc hàng không còn phù hợp. Service có thể trả conflict, đọc lại trạng thái mới hoặc retry theo quy tắc nghiệp vụ.

`rowversion` không phải thời gian và không thể dùng để hiển thị “lúc nào cập nhật”. Nó cũng không phải số phiên bản riêng biệt bắt đầu từ 1 cho từng hàng; đây là giá trị nhị phân được quản lý ở phạm vi database. Không tự truyền giá trị vào cột rowversion khi insert/update.

Spring Data `@Version` thường được dùng với thuộc tính version mà Spring Data có thể tăng/so sánh theo mapping được hỗ trợ. Không giả định `byte[]` map trực tiếp vào SQL Server `rowversion` sẽ tự hoạt động như `@Version` ở mọi phiên bản. Nếu muốn dùng native rowversion, hãy kiểm tra khả năng driver/mapping hoặc tự viết câu SQL có predicate `row_version = :expectedVersion` và kiểm tra `rowsUpdated()`.

## 18. Mapping entity và generated ID trong Spring Data R2DBC

Ví dụ entity dùng `IDENTITY`:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("created_at")
    private LocalDateTime createdAt;
}
```

Khi tạo entity mới, để `id` ở trạng thái new theo cơ chế nhận diện entity của Spring Data. Sau khi save, lấy ID từ entity được trả về:

```java
return orderRepository.save(newOrder)
    .flatMap(saved -> orderLineRepository.saveAll(
            createLines(saved.getId(), request.lines()))
        .thenReturn(saved));
```

Không bỏ qua entity trả về từ `save`, nhất là với entity immutable hoặc khi ID được database sinh. Spring Data có thể tạo instance mới chứa ID, version hoặc giá trị được mapping lại.

Nếu dùng ID do ứng dụng cấp trước, cơ chế xác định entity mới/cũ có thể khác. Có thể cần `Persistable` hoặc chiến lược newness phù hợp để Spring Data chọn insert thay vì update. Hãy kiểm tra quy tắc nhận diện entity của phiên bản Spring Data Relational đang dùng.

## 19. SQL Server identifier, schema và từ khóa

SQL Server thường dùng schema `dbo` nếu không chỉ định schema khác. Có thể ghi rõ tên bảng:

```sql
SELECT id, order_number
FROM dbo.purchase_order;
```

Tên bảng/cột trùng từ khóa hoặc chứa ký tự đặc biệt có thể cần delimiter `[...]`:

```sql
SELECT [order], [status]
FROM dbo.[order];
```

Tuy nhiên, nên tránh đặt tên bảng/cột trùng từ khóa như `order`, `user`, `key` nếu có thể. Dùng tên domain rõ ràng như `purchase_order` sẽ giảm nhu cầu quote identifier.

Với Spring Data, `@Table` và `@Column` cùng dialect giúp mapping identifier. Với SQL viết tay trong `DatabaseClient`, phải dùng đúng schema và delimiter. Không nối identifier do người dùng gửi vào SQL; nếu cần sort field động, dùng allowlist các cột được phép.

## 20. Bind marker và kiểu tham số của SQL Server R2DBC

Khi dùng Spring `DatabaseClient`, có thể viết named parameter:

```java
databaseClient.sql("SELECT id FROM dbo.customer WHERE email = :email")
    .bind("email", email)
    .map((row, metadata) -> row.get("id", Long.class))
    .one();
```

Spring chuyển named parameter thành bind marker phù hợp với dialect/driver. Khi gọi R2DBC SPI trực tiếp, driver SQL Server có quy tắc marker riêng; cần theo tài liệu phiên bản driver. Không copy cú pháp `$1` từ PostgreSQL hoặc `?` từ driver khác.

Kiểu Java truyền vào bind phải phù hợp codec. Ví dụ `UUID` cho `uniqueidentifier`, `BigDecimal` cho `decimal`, `OffsetDateTime` cho `datetimeoffset`, `LocalDateTime` cho `datetime2` nếu driver hỗ trợ mapping đó. Với null, dùng `bindNull(name, JavaType.class)` để cung cấp kiểu rõ ràng.

Không thể bind tên bảng/cột như một giá trị. Nếu query có `ORDER BY` động, hãy chọn identifier từ allowlist:

```java
String orderColumn = switch (sortField) {
    case "createdAt" -> "created_at";
    case "orderNumber" -> "order_number";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};
```

Sau đó chỉ ghép `orderColumn` đã được chọn từ code vào phần SQL cố định. Giá trị filter, offset và page size vẫn phải bind.

## 21. Index hỗ trợ phân trang

Một query phân trang có thể chậm nếu database phải sort nhiều hàng hoặc bỏ qua offset lớn. Index nên phản ánh điều kiện lọc và thứ tự:

```sql
CREATE INDEX IX_purchase_order_tenant_created_id
ON dbo.purchase_order (tenant_id, created_at DESC, id DESC)
INCLUDE (order_number, status);
```

Index trên là ví dụ cho query lọc theo `tenant_id` và sắp xếp theo `created_at DESC, id DESC`. `INCLUDE` có thể giúp query lấy thêm cột mà không phải lookup bảng cho từng hàng, nhưng tăng kích thước index và chi phí ghi. Chỉ thêm cột include khi query plan và workload chứng minh có lợi.

Với keyset pagination, index có thứ tự phù hợp với các cột seek thường giúp database tìm điểm bắt đầu hiệu quả hơn. Với offset pagination, index vẫn giúp sort/filter nhưng database có thể cần đọc qua các hàng bị bỏ qua.

Kiểm tra execution plan, logical reads và thời gian truy vấn trên dữ liệu gần thực tế. Không tạo index chỉ dựa trên một ví dụ SQL mà không xem workload cập nhật và các query khác.

## 22. Các lưu ý về phiên bản và hỗ trợ driver

Khi triển khai SQL Server với Spring Data R2DBC, cần xác minh các điểm sau trên phiên bản thực tế:

- Spring Data Relational có SQL Server dialect tương ứng và dialect đó hỗ trợ các thao tác đang dùng.
- R2DBC SQL Server driver hỗ trợ kiểu dữ liệu Java cần thiết, bao gồm `UUID`, `BigDecimal`, temporal type và binary.
- `R2dbcEntityTemplate` tạo phân trang bằng `OFFSET/FETCH` đúng phiên bản SQL Server.
- `DatabaseClient` chuyển named parameter thành bind marker phù hợp.
- Driver hỗ trợ generated values theo cách Spring Data yêu cầu, hoặc ứng dụng dùng `OUTPUT INSERTED` tường minh.
- Bảng có trigger có ảnh hưởng đến cách dùng `OUTPUT` không.
- Mapping `rowversion` và optimistic concurrency được hỗ trợ hay cần SQL tường minh.
- Kiểu `datetime2`/`datetimeoffset` được đọc/ghi với precision và timezone mong muốn.

Không nên coi một ví dụ chạy được trên H2 là bằng chứng SQL Server hoạt động giống hệt. SQL Server có cú pháp, kiểu dữ liệu và hành vi generated values riêng; integration test phải chạy trên SQL Server hoặc môi trường tương đương với production.

## 23. Kiểm thử phân trang và generated values

Nên kiểm tra các trường hợp sau:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Trang đầu | Trả đúng số hàng, đúng thứ tự và không có hàng ngoài tenant/filter. |
| Trang tiếp theo | Không lặp hàng khi dữ liệu không thay đổi. |
| Nhiều hàng cùng timestamp | Tie-breaker ID tạo thứ tự ổn định. |
| Offset lớn | Đo hiệu năng và so sánh với keyset pagination. |
| Page size/offset không hợp lệ | Service từ chối trước khi chạy SQL. |
| Tổng số hàng lớn | `COUNT_BIG(*)` map đúng sang `Long`. |
| Insert identity | Entity trả về có ID được sinh. |
| Default/computed column | Giá trị được trả về hoặc truy vấn lại đúng cách. |
| Bảng có trigger | `OUTPUT` không bị lỗi; giá trị sau trigger được xử lý đúng nếu cần. |
| rowversion | Cập nhật với version cũ thành công hoặc bị conflict đúng mong đợi. |
| Unicode | Tên tiếng Việt và ký tự bổ sung được lưu/đọc không mất dữ liệu. |
| datetimeoffset | Offset được bảo toàn theo quy ước của ứng dụng. |
| decimal | Precision/scale và rounding đúng quy tắc nghiệp vụ. |

Với generated values, kiểm tra cả trường hợp insert thành công và insert rollback. Identity/sequence có thể có khoảng trống sau rollback; test không nên yêu cầu ID liên tiếp.

## 24. Quy trình lựa chọn cách phân trang và lấy generated value

Khi xây dựng query SQL Server, hãy quyết định theo thứ tự:

1. Dữ liệu có cần nhảy đến trang bất kỳ hay chỉ cần đi tiếp từ trang trước?
2. Với trang bất kỳ, dùng `ORDER BY` ổn định cùng `OFFSET/FETCH`; với tập lớn và duyệt tuần tự, cân nhắc keyset pagination.
3. Xác định page size tối đa và tính offset bằng `long` có kiểm tra tràn số.
4. Chọn `R2dbcEntityTemplate` khi cần entity mapping; chọn `DatabaseClient` khi cần SQL/projection đặc thù.
5. Chọn kiểu cột theo miền giá trị, precision, Unicode, nullability và semantics thời gian.
6. Với ID tự tăng, dùng `IDENTITY` hoặc `SEQUENCE` theo nhu cầu; không giả định dãy ID liên tục.
7. Dùng generated-value support của dialect/driver hoặc `OUTPUT INSERTED` để nhận ID/default/computed value.
8. Xử lý giới hạn `OUTPUT` khi bảng có trigger và nhớ rằng output có thể phản ánh trạng thái trước AFTER trigger.
9. Với optimistic concurrency, phân biệt numeric `@Version` của Spring Data với SQL Server `rowversion` nhị phân.
10. Kiểm thử trên đúng SQL Server và R2DBC driver, bao gồm kiểu dữ liệu, paging, trigger và transaction.

SQL Server có cú pháp phân trang `OFFSET/FETCH`, `TOP` và `ROW_NUMBER`; với dữ liệu lớn, keyset pagination có thể giảm chi phí bỏ qua hàng. Các kiểu `datetime2`, `datetimeoffset`, `nvarchar`, `uniqueidentifier`, `decimal` và `rowversion` cần được ánh xạ theo đúng semantics thay vì chỉ dựa vào tên Java. Với giá trị sinh ra, `IDENTITY`, `SEQUENCE`, default constraint và `OUTPUT INSERTED` là các cơ chế quan trọng; Spring Data R2DBC có thể tích hợp generated values thông qua dialect/driver nhưng phải xác minh theo phiên bản. Thiết kế query có thứ tự ổn định, chọn kiểu cột rõ ràng và kiểm thử trên SQL Server thực tế sẽ giúp phân trang và persistence hoạt động dự đoán được.
