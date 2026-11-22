# Tham số danh sách cho IN và giới hạn số tham số của cơ sở dữ liệu

## 1. Mục tiêu bài học

Trong Spring JDBC, cú pháp `WHERE id IN (:ids)` rất tiện khi cần lọc theo **một danh sách ID thay đổi độ dài**. Nhưng `:ids` không phải một tham số đơn kỳ diệu mà mọi DBMS tự hiểu là cả một tập giá trị: `NamedParameterJdbcTemplate` thường **mở rộng danh sách thành nhiều JDBC bind placeholders**.

Ví dụ, ba ID tạo ra câu SQL thực tế tương đương `WHERE id IN (?, ?, ?)`, rồi Spring bind ba giá trị theo đúng thứ tự. Nếu danh sách dài tới hàng nghìn/phần triệu giá trị, câu SQL lớn lên, có thể chạm giới hạn số phần tử của `IN`, số bind parameters của câu lệnh, kích thước SQL và chi phí thực thi.

Bài học giúp bạn:

1. Hiểu cơ chế mở rộng `List`/`Iterable` của `NamedParameterJdbcTemplate` và cách nó khác `JdbcTemplate` thường.
2. Truyền danh sách vào `IN (:ids)` an toàn bằng `MapSqlParameterSource` hoặc `Map.of(...)`.
3. Xử lý **danh sách rỗng**, ID lặp, phần tử `null`, thứ tự kết quả, danh sách bị sửa trong lúc truy vấn và `NOT IN` có `NULL`.
4. Tách biệt **giới hạn số biểu thức của một IN list** với **giới hạn tham số bind của toàn SQL statement**, tính cả điều kiện khác và những lần dùng lại cùng danh sách.
5. Chọn chính sách **giới hạn request, dedupe, chunk thành nhiều câu SQL, batch theo ID**, và biết khi nào phải chuyển sang **bảng tạm, bảng staging, SQL array/`ANY`, table-valued parameters hoặc join với dữ liệu đã có trong DB**.
6. Chạy ví dụ Java 17+ với Spring Boot, H2, `NamedParameterJdbcTemplate`, migration/seed SQL và kiểm thử các trường hợp biên.

**Thông điệp cốt lõi:** named parameter giúp quản lý bind an toàn; **nó không xóa giới hạn của database**. Cần thiết kế kích thước đầu vào, cách chia truy vấn và ngữ nghĩa kết quả ngay từ hợp đồng repository.

## 2. Vì sao một placeholder JDBC không tự đại diện cho nhiều phần tử?

Với JDBC thuần, dấu `?` trong một `PreparedStatement` đại diện **một vị trí tham số** trong cú pháp SQL:

```sql
SELECT id, sku FROM products WHERE id = ?;
```

Nếu cần ba ID với cú pháp `IN`, bạn thường phải có ba chỗ bind:

```sql
SELECT id, sku FROM products WHERE id IN (?, ?, ?);
```

Không thể mặc định viết `IN (?)` rồi gọi `statement.setObject(1, List.of(1L, 2L, 3L))` và mong database tự trải `List` Java thành ba giá trị. Driver có thể không hỗ trợ kiểu `List`, hoặc có cơ chế array riêng nhưng **array SQL** là một kiểu dữ liệu và cách so sánh **khác** `IN (?, ?, ?)`.

Spring `NamedParameterJdbcTemplate` cung cấp lớp tiện ích:

```sql
SELECT id, sku FROM products WHERE id IN (:ids);
```

Code truyền `ids = List.of(1L, 2L, 3L)`. Spring nhận danh sách, tạo một phiên bản SQL có đủ placeholders rồi bind từng giá trị. Lập trình viên không phải tự nối ba dấu `?` hay giá trị ID vào SQL.

### 2.1. Minh họa cách mở rộng

Câu SQL ứng dụng viết:

```sql
SELECT id, sku
FROM products
WHERE id IN (:ids)
  AND active = :active;
```

Tham số ứng dụng:

```text
ids    = [3, 1, 4]
active = true
```

Hình dạng SQL được chuyển thành (minh họa, không phải log thực thi):

```sql
SELECT id, sku
FROM products
WHERE id IN (?, ?, ?)
  AND active = ?;
```

Tổng số vị trí bind là **4**, không phải 2: ba vị trí cho `ids` và một cho `active`. Nếu `ids` có 500 phần tử, câu truy vấn tương ứng có **501 vị trí bind**.

Điều này quan trọng với pool statement cache, kích thước SQL, thời gian parse và giới hạn của engine. Tên `:ids` là cú pháp của lớp Spring; không phải database nào cũng nhận nguyên văn `:ids` qua JDBC.

### 2.2. NamedParameterJdbcTemplate khác JdbcTemplate

| Cách truy vấn | `List` đầu vào | Hành vi chính |
| --- | --- | --- |
| `NamedParameterJdbcTemplate` với `IN (:ids)` | `List<Long>` | Spring tạo đủ `?` theo số phần tử |
| `JdbcTemplate` với `IN (?, ?, ?)` | Ba giá trị rời | Người viết SQL đã chỉ định đủ placeholders |
| `JdbcTemplate` với `IN (?)` và một `List<Long>` | Một Java List tại một tham số | **Không** được tự động xem là ba bind values cho IN |
| PostgreSQL `= ANY (?)` với JDBC `Array` | Một SQL array | Cơ chế database-specific; **không** phải Spring list expansion |
| SQL Server table-valued parameter (TVP) | Một tham số có kiểu bảng | Cơ chế riêng của SQL Server/driver và schema type |

Đừng nhầm `List` được mở rộng sang **nhiều tham số** với một **SQL array parameter**. Hai cách có giới hạn, cách tối ưu và độ tương thích DB khác nhau.

## 3. Cú pháp cơ bản với NamedParameterJdbcTemplate

### 3.1. Dùng Map.of cho truy vấn đơn giản

```java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

// namedJdbc là bean NamedParameterJdbcTemplate đã được inject.
List<Long> ids = List.of(1L, 3L, 4L);

List<String> skus = namedJdbc.query(
        """
        SELECT sku
        FROM products
        WHERE id IN (:ids)
        ORDER BY id
        """,
        Map.of("ids", ids),
        (rs, rowNum) -> rs.getString("sku")
);
```

Đây là fragment Java trong method có `namedJdbc` được cung cấp bởi Spring; để chạy cần bảng `products` như ở mục 7. `ORDER BY id` nhằm có thứ tự DB xác định theo ID, **không** bảo toàn thứ tự của `ids` do caller gửi.

`List.of(...)` là danh sách bất biến và không cho phần tử null. Tránh dùng một `ArrayList` có thể bị thread khác sửa trong lúc statement đang chuẩn bị/bind; tốt nhất sao chép input vào collection riêng trước khi query, kèm validation.

### 3.2. Dùng MapSqlParameterSource cho nhiều tham số

```java
import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
        .addValue("ids", List.of(1L, 3L))
        .addValue("active", true);

List<String> skus = namedJdbc.query(
        """
        SELECT sku
        FROM products
        WHERE id IN (:ids)
          AND active = :active
        ORDER BY id
        """,
        params,
        (rs, rowNum) -> rs.getString("sku")
);
```

`MapSqlParameterSource` phù hợp khi muốn đọc rõ tham số, đăng ký `java.sql.Types` (đặc biệt với giá trị `null`), và mở rộng về sau. Một tập ID ở `ids` được bind theo thứ tự các phần tử; `active` là bind riêng.

**Chú ý:** tên tham số do code quyết định (`ids`, `active`), còn các giá trị do caller đưa vào phải được bind, không lắp trực tiếp vào chuỗi SQL.

### 3.3. SQL injection: bind giá trị chứ không bind cú pháp

Sai:

```java
// Sai: nối các giá trị tùy ý vào SQL.
String sql = "SELECT * FROM products WHERE sku IN ("
        + rawUserInput + ")";
```

Đúng:

```java
var params = new MapSqlParameterSource(
        "skus",
        List.of("BOOK", "PEN")
);

namedJdbc.query(
        "SELECT id, sku FROM products WHERE sku IN (:skus)",
        params,
        (rs, rowNum) -> rs.getString("sku")
);
```

Spring mở rộng danh sách thành placeholders rồi bind **dữ liệu**, không diễn giải SKU thành từ khóa SQL. Nhưng nếu caller muốn chọn tên cột/table hoặc biểu thức `ORDER BY`, đó là **cú pháp SQL** không thể an toàn hóa bằng một bind placeholder; phải dùng whitelist mã nguồn cố định.

## 4. Các trường hợp biên cần xử lý trước khi gọi DB

### 4.1. Danh sách rỗng: IN () không phải cách viết portable

Nếu `ids = []`, một số DBMS báo lỗi với `WHERE id IN ()`. Tài liệu Spring cũng không cam kết rằng truyền list rỗng vào `IN (:ids)` sẽ có cùng ngữ nghĩa ở mọi driver/dialect. **Không dựa vào việc Spring tự tạo SQL hợp lệ cho empty list.**

Với truy vấn tìm sản phẩm có ID thuộc danh sách, semantics thông thường là **không có ID → kết quả rỗng**:

```java
public List<Product> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of(); // không cần chạm database
    }
    // Tiếp tục query IN (:ids) với danh sách không rỗng.
}
```

Đây là fragment mô tả, `Product` là kiểu đã khai báo trong ứng dụng. Khi dùng `Collection` ngoài, kiểm tra `ids != null` trước `isEmpty()` hoặc từ chối null với thông điệp rõ.

Nếu nghiệp vụ là “không chọn bộ lọc” ⇒ **trả tất cả bản ghi**, đừng tự gán semantics này chỉ vì list rỗng. Định nghĩa hai trạng thái riêng, chẳng hạn `filterAbsent` (không áp dụng điều kiện) và `ids=[]` (lọc ra không kết quả). Nhập nhằng giữa hai trường hợp có thể gây lộ dữ liệu hoặc trả khối lượng dữ liệu rất lớn.

### 4.2. NOT IN với danh sách rỗng

`NOT IN (:ids)` không thể chỉ thay `ids=[]` bằng `IN ()` và hy vọng có kết quả “tất cả”. Đặc biệt nguy hiểm nếu chỉ dùng chung branch rỗng cho cả IN và NOT IN.

Quy tắc nghiệp vụ thường gặp:

- `x IN emptySet` luôn false ⇒ không bản ghi.
- `x NOT IN emptySet` luôn true ⇒ không cần điều kiện loại trừ, **nhưng vẫn phải giữ các điều kiện phân quyền/tenant khác**.

Đây là ngữ nghĩa ở cấp tập hợp. Việc biến nó thành SQL thực thi phải được làm rõ trong ứng dụng, không để dialect quyết định.

### 4.3. Giá trị NULL bên trong danh sách

Với SQL ba giá trị logic, biểu thức:

```sql
SELECT id
FROM products
WHERE id IN (1, NULL);
```

không có nghĩa `id = 1 OR id IS NULL`. Nếu `id` bằng NULL, so sánh với NULL không true; nếu `id` không bằng 1, kết quả có thể UNKNOWN và bị `WHERE` loại. Đặc biệt:

```sql
SELECT id
FROM products
WHERE id NOT IN (1, NULL);
```

có thể **không trả hàng nào** dù nhiều ID khác 1, vì phần tử NULL khiến phép so sánh không cho TRUE như bạn tưởng. Vì vậy, với danh sách khóa chính hoặc khóa ngoại NOT NULL, **từ chối phần tử Java null** từ đầu. Nếu thực sự cần bao gồm giá trị NULL của cột, thêm điều kiện `OR column IS NULL` có chủ đích và đặt ngoặc đúng.

`MapSqlParameterSource` có thể đăng ký SQL type rõ khi bind scalar null:

```java
params.addValue("deletedBefore", null, java.sql.Types.TIMESTAMP);
```

Nhưng không dùng một “phần tử NULL trong IN list” như cách biểu diễn tập hợp có chứa SQL NULL.

### 4.4. ID trùng nhau

`IN (3, 1, 3)` có ý nghĩa membership giống `IN (3, 1)` đối với các ID bình thường; query sẽ không tự trả hai bản sao của hàng id=3 chỉ vì input chứa ID 3 hai lần.

Nếu API cần trả danh sách đối tượng **mỗi ID một lần**, hãy dedupe bằng `LinkedHashSet` để vừa giảm số placeholders vừa giữ thứ tự ID xuất hiện đầu tiên. Nếu nghiệp vụ cần giữ bản sao/trọng số của input, đó là một yêu cầu khác và `IN` đơn thuần không có semantics “multiset” hoặc “trả kết quả lặp theo số lần ID xuất hiện”.

### 4.5. Thứ tự input không tạo thứ tự SQL

Ví dụ `ids = [3, 1]` không buộc SQL trả `[3, 1]`. `WHERE id IN (:ids)` chỉ chọn membership; không bảo đảm thứ tự của `ResultSet`. Có thể:

- Để DB trả theo một `ORDER BY` nhất quán (ví dụ `ORDER BY created_at DESC, id DESC`); hoặc
- Dùng kết quả map theo ID rồi dựng `List` theo thứ tự input đã dedupe nếu hợp đồng API yêu cầu thứ tự lựa chọn của caller.

Ví dụ chạy được mục 7 minh họa phương án thứ hai.

### 4.6. Kết quả có thể thiếu ID hoặc bị điều kiện khác loại

Nếu input chứa `[1, 2, 999]` nhưng ID 999 không có, query trả tối đa hai sản phẩm. Nếu có điều kiện `AND active = true`, sản phẩm inactive cũng không xuất hiện.

Repository cần công bố rõ một trong hai hợp đồng:

- **Lọc**: trả những bản ghi thực sự tồn tại và thỏa điều kiện; ID thiếu bị bỏ.
- **Bắt buộc đủ**: thiếu bất kỳ ID nào thì báo lỗi nghiệp vụ, có thể trả danh sách ID thiếu (nếu caller được phép biết), kiểm tra tính nhất quán phù hợp.

Đừng tự suy luận “thiếu nghĩa là database bị lỗi” hoặc tự tạo bản ghi giả để bù cho số lượng input.

## 5. Hai loại giới hạn thường bị nhầm lẫn

### 5.1. Giới hạn số biểu thức trong một IN list

Một DBMS có thể giới hạn **số phần tử/bộ biểu thức của một danh sách IN cụ thể**. Ví dụ tài liệu **Oracle Database 19c** quy định tối đa **1.000 biểu thức** trong một `expression_list` của `IN`. Nếu vượt quá sẽ gặp lỗi `ORA-01795`.

Nhưng giới hạn này **không bất biến qua các phiên bản Oracle**: tài liệu Oracle Database **26ai** mô tả giới hạn tới **65.535 biểu thức** trong `expression_list`. Vì vậy, câu “Oracle luôn chỉ cho 1.000 giá trị” là quá tổng quát. Cần kiểm tra **đúng version** đang chạy và cấu trúc `IN` (một cột hay tuple nhiều cột).

Ngay cả khi database cho phép danh sách rất dài, điều đó không bảo đảm hiệu năng tốt: query dài hơn, parse/plan tốn tài nguyên, khả năng cache plan giảm và có thể chọn execution plan không phù hợp.

### 5.2. Giới hạn số bind parameters của cả statement

Một giới hạn khác áp dụng cho **tổng số tham số được bind trong câu lệnh đã mở rộng**, gồm:

- Từng phần tử của danh sách `:ids`.
- Các scalar khác như `:tenantId`, `:active`, `:startAt`, `:endAt`.
- Phần tử trong **mọi** danh sách khác `:statuses`, `:regions`.
- Số lần xuất hiện của cùng một named parameter list nếu query dùng lặp lại nó.

Ví dụ:

```sql
SELECT id, sku
FROM products
WHERE (id IN (:ids) OR backup_id IN (:ids))
  AND tenant_id = :tenantId
  AND active = :active;
```

Với `ids` gồm 400 ID, có **2 × 400 + 2 = 802 bind positions**, không phải 402. Mỗi lần xuất hiện của `:ids` vẫn cần nhóm placeholders trong SQL được thực thi. Không chỉ đếm độ dài của một list rồi kết luận statement không thể vượt giới hạn.

Một hệ thống có thể không vượt giới hạn **một IN list**, nhưng vẫn vượt giới hạn **tổng bind parameters** khi có nhiều điều kiện.

### 5.3. Bảng tham khảo giới hạn, phải kiểm tra theo DBMS và phiên bản

| Nền tảng | Con số tham khảo | Giới hạn thuộc loại nào? | Lưu ý |
| --- | --- | --- | --- |
| **Oracle Database 19c** | **1.000** | Số biểu thức trong `IN expression_list` | Lỗi điển hình `ORA-01795`; không phải giới hạn “tổng JDBC bind” |
| **Oracle Database 26ai** | **65.535** | Số biểu thức trong `IN expression_list` theo tài liệu phiên bản đó | Không áp đặt con số mới cho hệ Oracle 19c/21c |
| **SQL Server** | **2.100** | Giới hạn tham số thường gặp ở giao thức/procedure/statement | Phải trừ các tham số khác; không phải một giới hạn IN riêng 2.100 phần tử |
| **PostgreSQL pgJDBC extended query protocol** | **65.535** | Bind parameters của một statement trong extended query protocol | Không có nghĩa nên gửi `IN` gồm 65 nghìn phần tử; driver/protocol và cách query quan trọng |
| **SQLite trước 3.32.0** | **999** mặc định | Số thứ tự host parameter tối đa | Có thể tùy biến khi compile/cấu hình |
| **SQLite 3.32.0+** | **32.766** mặc định | Số thứ tự host parameter tối đa | Có thể giảm bằng cấu hình runtime/build |
| **H2 và các DBMS khác** | Tùy phiên bản/cấu hình | Tham số, SQL length, optimizer và tài nguyên | Không lấy con số H2 làm giới hạn production |

**Nguồn kiểm tra:** Spring JDBC [Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html), [Oracle 19c IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html), [Oracle 26ai IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/IN-Condition.html), [Microsoft SQL Server capacity](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server), [pgJDBC](https://jdbc.postgresql.org/documentation/use/) và [SQLite limits](https://www.sqlite.org/limits.html).

Các con số trong bảng là **mốc kỹ thuật**, không phải kích thước batch đề xuất. Spring nhắc rằng JDBC standard không cam kết có thể sử dụng hơn 100 giá trị cho một `IN` list một cách portable. Nếu xây thư viện chạy trên nhiều dialect, hãy chọn policy được **kiểm thử cho từng DB/driver**, không tự suy từ con số cao nhất trên mạng.

### 5.4. Công thức tính budget tham số

Với mỗi SQL statement, có thể mô hình hóa:

```text
P = tổng số vị trí bind của các list sau khi mở rộng
    + số bind của các scalar
    + số bind khác (tuples, LIMIT/OFFSET nếu bind, ...)
```

Nếu một danh sách dài `N` được dùng `R` lần và có `S` scalar:

```text
P = R × N + S
```

Ví dụ `:ids` xuất hiện hai lần và còn ba scalar; budget theo statement là 2.000: `N` phải thỏa `2N + 3 ≤ 2000`, tức `N ≤ 998` (lấy phần nguyên). Nhưng nếu DB còn giới hạn 1.000 phần tử trên **một** `IN`, giới hạn thực là `min(998, 1000) = 998`.

Khi chỉ một lần xuất hiện `IN (:ids)`, một scalar `:active` và policy giả định tối đa **2.100** bind positions, batch có thể lên tới `2.099` về mặt số vị trí bind; tuy nhiên nếu chạy Oracle 19c với `IN` tối đa 1.000 thì batch vẫn không được vượt 1.000. Trong production nên để thêm **biên an toàn** và dựa trên workload thật.

Công thức tổng quát cho một danh sách lặp `R ≥ 1` lần:

```text
batchSize <= min(
    perInExpressionLimit,
    floor((statementParameterLimit - fixedParameters) / R),
    operationalBatchPolicy
)
```

Nếu `statementParameterLimit - fixedParameters ≤ 0` hoặc giá trị tính được nhỏ hơn 1, không thể chạy dạng query hiện tại: hãy sửa cấu trúc SQL hoặc chuyển chiến lược (bảng tạm, array, TVP...). Cần đếm tuple `(a,b)` như **hai bind values cho mỗi tuple**, và kiểm tra thêm giới hạn số tuple của dialect nếu có.

## 6. Khi danh sách lớn: các chiến lược và trade-off

### 6.1. Cách đơn giản: giới hạn số ID trong request

Nếu use case chỉ nên lấy vài chục/vài trăm bản ghi, định nghĩa giới hạn đầu vào và trả lỗi validation khi vượt, thay vì âm thầm tạo câu SQL cực dài. Cân nhắc thêm:

- Dedupe ID trước khi đo kích thước truy vấn thực.
- Đặt giới hạn request body tổng và tổng số ID được chấp nhận để ngăn resource exhaustion.
- Kiểm soát quyền/tenant cho **từng ID**, không chỉ vì ID có trong list mà được phép đọc.
- Hạn chế số bản ghi/bytes tối đa trả về, không chỉ số bind parameters.

Đây là một **business/API limit**, khác với giới hạn kỹ thuật của database. Một engine có thể hỗ trợ 65 nghìn placeholders nhưng API chỉ cho 500 ID để bảo vệ p99 latency.

### 6.2. Chia thành nhiều statement (chunking)

Nếu cần đọc một danh sách vừa lớn, chia ID thành các nhóm đủ nhỏ và chạy nhiều câu SQL độc lập:

```text
ids = [1..1200]
maxPerStatement = 500

statement 1: id IN (:ids) với 500 ID (+ các scalar)
statement 2: id IN (:ids) với 500 ID (+ các scalar)
statement 3: id IN (:ids) với 200 ID (+ các scalar)
```

Đây là **ba SQL statements**, mỗi statement không vượt 500 phần tử `IN`. Với SQL có một tham số `active` nữa, tổng bind positions lần lượt là 501, 501 và 201.

Ưu điểm: dễ thực hiện với `NamedParameterJdbcTemplate`, không cần đặc quyền tạo bảng tạm hay extension DB, có thể quản lý kết quả dễ. Nhược điểm:

- Nhiều lần round trip và parse/bind; latency có thể cao hơn một query.
- Mỗi batch riêng có thể thấy trạng thái dữ liệu khác nhau khi có ghi đồng thời; nếu cần snapshot nhất quán phải chọn transaction/isolation thích hợp.
- Kết quả phải được gom/dedupe và sắp theo hợp đồng của caller nếu cần; không được giả định DB trả đúng thứ tự input.
- Với thao tác `UPDATE/DELETE`, nhiều batch riêng có nguy cơ **partial success** khi batch sau lỗi nếu không dùng transaction bao quanh hoặc cơ chế bù trừ phù hợp.

**Không** nhầm chunking thành việc ghép các phần trong cùng một SQL:

```sql
-- Hai IN list chỉ giải quyết hạn mức số biểu thức của từng list.
-- Tổng số bind vẫn là tổng mọi dấu ? trong một SQL.
WHERE id IN (:idsPart1) OR id IN (:idsPart2)
```

Nếu giới hạn gặp phải là **tổng bind parameters của statement**, ghép bằng `OR` trong cùng statement **không** giải quyết. Chunking phải thật sự tạo **nhiều statements** (hoặc chuyển kiểu dữ liệu khác).

### 6.3. Truy vấn qua bảng tạm hoặc bảng staging

Khi có hàng chục nghìn ID và cần join phức tạp, hướng thường hiệu quả hơn là:

1. Tạo hoặc cấp bảng staging/temp có cột ID và tùy chọn `request_key`.
2. Nạp ID bằng `batchUpdate`/bulk-load, có ràng buộc/dedupe phù hợp.
3. Truy vấn `JOIN staging_ids ON staging_ids.id = products.id`.
4. Dọn dữ liệu và tài nguyên theo transaction/session phù hợp.

Ví dụ SQL khái niệm (cú pháp tạo bảng tạm và lifecycle phụ thuộc DBMS):

```sql
SELECT p.id, p.sku
FROM products p
JOIN staging_ids s ON s.id = p.id
WHERE s.request_key = :requestKey
  AND p.active = :active;
```

Ưu điểm là có thể xử lý tập ID lớn mà không tạo `IN` nghìn dấu `?`. Chi phí là thêm vòng đời bảng staging, giao dịch nạp ID, chỉ mục, quyền truy cập, dọn dữ liệu khi process lỗi và kiểm soát đồng thời. Với connection pool, **bảng tạm gắn với session** không tự chuyển sang connection khác: việc nạp và truy vấn phải dùng đúng connection/transaction theo cách DBMS vận hành. Tránh để dữ liệu request A tồn dư rồi bị request B đọc được qua connection tái sử dụng.

Nếu ID **đã nằm ở một bảng khác trong DB**, ưu tiên `JOIN` hoặc `EXISTS` trực tiếp thay vì tải ID lên Java rồi truyền ngược trở lại bằng list khổng lồ:

```sql
SELECT p.id, p.sku
FROM products p
WHERE EXISTS (
    SELECT 1
    FROM permitted_products ap
    WHERE ap.product_id = p.id
      AND ap.user_id = :userId
);
```

`permitted_products` chỉ là bảng minh họa có quan hệ quyền truy cập. Cách này còn giúp database tối ưu join/index.

### 6.4. PostgreSQL: SQL array và ANY thay cho IN mở rộng

PostgreSQL hỗ trợ so sánh một giá trị với một SQL array:

```sql
SELECT id, sku
FROM products
WHERE id = ANY (?);
```

Khi bind **một giá trị JDBC `Array` kiểu `bigint[]`** vào dấu `?`, toàn bộ tập ID đi qua **một bind position** (không bị `NamedParameterJdbcTemplate` mở rộng thành N vị trí). Nhưng đây là giải pháp **PostgreSQL-specific** và cần driver hỗ trợ `java.sql.Array`, kiểm soát lifetime, timeout và kích thước dữ liệu.

Ví dụ fragment **chỉ chạy với PostgreSQL, không dùng cho ứng dụng H2 ở mục 7**:

```java
List<Product> products = jdbcTemplate.execute(
        (org.springframework.jdbc.core.ConnectionCallback<List<Product>>)
        connection -> {
            java.sql.Array sqlArray = connection.createArrayOf(
                    "int8",
                    ids.toArray(Long[]::new)
            );
            try {
                try (var statement = connection.prepareStatement(
                        """
                        SELECT id, sku, active
                        FROM products
                        WHERE id = ANY (?)
                          AND active = ?
                        """
                )) {
                    statement.setArray(1, sqlArray);
                    statement.setBoolean(2, true);

                    try (var rs = statement.executeQuery()) {
                        List<Product> result = new java.util.ArrayList<>();
                        while (rs.next()) {
                            result.add(new Product(
                                    rs.getLong("id"),
                                    rs.getString("sku"),
                                    rs.getBoolean("active")
                            ));
                        }
                        return result;
                    }
                }
            } finally {
                sqlArray.free();
            }
        }
);
```

`ids` là `List<Long>` đã được validate và `jdbcTemplate` là bean `JdbcTemplate`, `Product` là record ở mục 7. Callback của `JdbcTemplate` giúp giữ connection trong scope callback và dịch `SQLException`; `PreparedStatement`, `ResultSet` được đóng bằng try-with-resources, `sqlArray.free()` chạy sau truy vấn. Không dùng `IN (?)` với một `Array` mà tưởng là cùng ngữ nghĩa; PostgreSQL sử dụng `= ANY (?)`.

Một SQL array rất lớn vẫn có chi phí tạo/serialize/parse, memory và kế hoạch truy vấn; một bind position **không có nghĩa** không có giới hạn kích thước payload. Tùy workload, `UNNEST(...)` + join hoặc bảng tạm có index/statistics có thể tốt hơn.

### 6.5. SQL Server: table-valued parameters

SQL Server hỗ trợ **table-valued parameters (TVP)** cho việc gửi một tập hàng có schema tới stored procedure/statement theo driver tương ứng. TVP thường hợp lý khi một request cần truyền hàng nghìn khóa hoặc bản ghi gồm nhiều cột. Đây **không** phải `List<Long>` tự động được `NamedParameterJdbcTemplate` hiểu là TVP; bạn phải định nghĩa type SQL Server và dùng API Microsoft JDBC driver hoặc một tầng access tương thích.

Tính toán tổng parameters theo statement vẫn cần xem xét, nhưng TVP là một cấu trúc bảng được truyền như một tham số có kiểu, thay vì mở rộng thành hàng nghìn scalar placeholders. Cần đo execution plan, cardinality estimation, TVP schema, index chiến lược và quyền trên user-defined table type.

### 6.6. List của tuple nhiều cột

Spring cho phép danh sách kiểu `List<Object[]>` để mở rộng điều kiện tuple khi DBMS hỗ trợ:

```sql
SELECT id, tenant_id
FROM products
WHERE (tenant_id, id) IN (:pairs);
```

Fragment tạo dữ liệu:

```java
List<Object[]> pairs = new ArrayList<>();
pairs.add(new Object[] {7L, 100L});
pairs.add(new Object[] {7L, 101L});

var params = new MapSqlParameterSource("pairs", pairs);
```

Hình dạng SQL sau mở rộng tương đương:

```sql
WHERE (tenant_id, id) IN ((?, ?), (?, ?));
```

Với 400 cặp 2 cột, bạn có thể cần **800 bind values**, không phải 400. Đồng thời cú pháp row-value comparison và hạn mức expression-list của các DBMS khác nhau. Khi số cặp rất lớn, staging table có hai cột và join theo khóa ghép thường có semantics, index và hiệu năng dễ quản lý hơn.

**Quan trọng về bảo mật:** nếu tenant ID được lấy từ session/authorization, đừng để client gửi cặp `(tenantId, id)` rồi coi đó là bằng chứng đã được cấp quyền. Tenant context phải được xác định ở server và kiểm tra lại trong truy vấn.

## 7. Ví dụ chạy được: Spring Boot + Java 17 + H2

Ứng dụng sau thể hiện toàn bộ flow:

- Input có thể chứa ID lặp, ID không tồn tại, ID inactive.
- Trả `List<Product>` trong **thứ tự ID duy nhất xuất hiện lần đầu** ở request.
- Không truy vấn khi input rỗng.
- Không chấp nhận `null` hoặc ID không dương.
- Dedupe để giảm placeholders, giới hạn 5.000 ID **phân biệt** trong một request.
- Chia mỗi SQL thành tối đa 500 ID; mỗi query còn có một scalar `:active`, nên nhiều nhất 501 bind positions cho truy vấn này.
- Không dùng `ORDER BY` để ép thứ tự input trong SQL; gom kết quả theo ID rồi dựng lại ở Java.

Đây là ví dụ để học **ngữ nghĩa và cách quản trị giới hạn**. Con số 500 không phải recommendation duy nhất cho mọi DB; ứng dụng thật cần chọn từ giới hạn engine/driver, số scalar còn lại và benchmark.

### 7.1. Cấu trúc dự án

```text
named-in-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/inlist/
    │   │   ├── Product.java
    │   │   ├── ProductJdbcRepository.java
    │   │   └── NamedInApplication.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/inlist/
        └── ProductJdbcRepositoryTest.java
```

### 7.2. Gradle build

`settings.gradle`:

```groovy
rootProject.name = 'named-in-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.x cung cấp `JdbcTemplate` và `NamedParameterJdbcTemplate` khi datasource được cấu hình. H2 chỉ là database học tập để tái lập ví dụ mà không phải cài server; kiểm tra giới hạn thực tế phải chạy integration test trên production-like DBMS.

### 7.3. SQL schema và dữ liệu cố định

`src/main/resources/schema.sql`:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO products (id, sku, active)
VALUES
    (1, 'BOOK', TRUE),
    (2, 'PEN', FALSE),
    (3, 'NOTE', TRUE),
    (4, 'BAG', TRUE);
```

Với schema này, `id` là PK, nên câu truy vấn theo `id IN (...)` không trả một sản phẩm nhiều lần. Nếu repository JOIN thêm bảng con một-nhiều, tính duy nhất của kết quả SQL có thể thay đổi và cần mapping/dedupe riêng, không nên mù quáng tái sử dụng giả định này.

`src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:named_in_demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
```

Spring khởi động datasource H2, chạy `schema.sql` và `data.sql`. Dữ liệu là ephemeral trong JVM, không cần mật khẩu production.

### 7.4. Kiểu dữ liệu trả về

`src/main/java/demo/inlist/Product.java`:

```java
package demo.inlist;

public record Product(long id, String sku, boolean active) {}
```

Record Java 17 đại diện kết quả của một hàng, tránh expose `ResultSet` hoặc `Map<String,Object>` trực tiếp lên các tầng khác.

### 7.5. Repository có dedupe, input cap, chunk và restore order

`src/main/java/demo/inlist/ProductJdbcRepository.java`:

```java
package demo.inlist;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductJdbcRepository {
    // Policy cho truy vấn trong bài: 500 IDs + 1 scalar (:active).
    private static final int MAX_IDS_PER_QUERY = 500;
    private static final int MAX_UNIQUE_IDS_PER_REQUEST = 5_000;

    private static final String SQL = """
            SELECT id, sku, active
            FROM products
            WHERE id IN (:ids)
              AND active = :active
            """;

    private static final RowMapper<Product> PRODUCT_ROW =
            (rs, rowNum) -> new Product(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getBoolean("active")
            );

    private final NamedParameterJdbcTemplate jdbc;

    public ProductJdbcRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Product> findActiveInRequestedOrder(
            Collection<Long> inputIds
    ) {
        Objects.requireNonNull(inputIds, "inputIds");

        // Dedupe theo thứ tự xuất hiện, kiểm tra ID từ caller.
        LinkedHashSet<Long> unique = new LinkedHashSet<>();
        for (Long id : inputIds) {
            if (id == null || id <= 0) {
                throw new IllegalArgumentException(
                        "Every product ID must be positive and non-null"
                );
            }

            unique.add(id);
            if (unique.size() > MAX_UNIQUE_IDS_PER_REQUEST) {
                throw new IllegalArgumentException(
                        "Too many distinct product IDs"
                );
            }
        }

        // Phải short-circuit trước IN (:ids) khi list rỗng.
        if (unique.isEmpty()) {
            return List.of();
        }

        List<Long> orderedIds = new ArrayList<>(unique);
        Map<Long, Product> foundById = new HashMap<>();

        // Đây là nhiều SQL statements, không phải nhiều IN trong 1 SQL.
        for (int start = 0;
             start < orderedIds.size();
             start += MAX_IDS_PER_QUERY) {

            int end = Math.min(
                    start + MAX_IDS_PER_QUERY,
                    orderedIds.size()
            );
            List<Long> batch = orderedIds.subList(start, end);

            var parameters = new MapSqlParameterSource()
                    .addValue("ids", batch)
                    .addValue("active", true);

            List<Product> rows = jdbc.query(
                    SQL,
                    parameters,
                    PRODUCT_ROW
            );

            for (Product product : rows) {
                foundById.put(product.id(), product);
            }
        }

        // SQL IN không bảo toàn thứ tự input.
        return orderedIds.stream()
                .map(foundById::get)
                .filter(Objects::nonNull)
                .toList();
    }
}
```

**Đọc kỹ bảy lựa chọn thiết kế:**

1. **Validation:** `inputIds` không được null; từng ID phải khác null và dương. Phần tử null không được phép lẫn vào `IN`, tránh ba-valued logic và lỗi mapping mơ hồ.
2. **Dedupe ổn định:** `LinkedHashSet` loại ID lặp nhưng giữ thứ tự xuất hiện đầu. Với `[3, 1, 3, 999, 2]` tạo `[3, 1, 999, 2]`.
3. **Max request size:** 5.000 ID phân biệt là policy minh họa, không phải hard limit của H2 hay bất kỳ DBMS nào. Nếu có yêu cầu giới hạn **số phần tử đầu vào kể cả trùng**, cần áp dụng thêm limit trước vòng lặp để chặn request cực lớn chứa hàng triệu bản sao.
4. **Empty input:** trả danh sách rỗng và không gửi SQL có `IN ()`. Đây là hợp đồng lọc membership, không dùng cho một endpoint định nghĩa “thiếu filter thì trả tất cả”.
5. **Chunk:** mỗi lần gọi `jdbc.query(...)` dùng nhiều nhất 500 ID và một scalar `active`; với SQL này nhiều nhất 501 JDBC bind values mỗi statement. Không có query nào gồm toàn bộ 5.000 IDs.
6. **Mapping:** `RowMapper<Product>` ánh xạ một hàng thành object. Vì `id` là PRIMARY KEY và không có JOIN nhân hàng, `Map.put(product.id(), product)` không làm mất bản ghi hợp lệ khác; nếu schema/query đổi, phải kiểm tra lại giả định.
7. **Thứ tự:** kết quả từ DB có thể khác thứ tự requested IDs. `orderedIds.stream()` dựng lại kết quả theo input, bỏ ID không tồn tại hoặc inactive. Kết quả trả về `List` không được sửa qua `Stream.toList()` trong Java 17.

**Lưu ý về tính đồng thời:** khi chạy nhiều câu SELECT theo chunk, database có thể đổi giữa các chunk. Nếu use case đòi một snapshot, dùng transaction read-only + isolation phù hợp DBMS và đo chi phí giữ snapshot; nếu không, công bố rằng danh sách được lấy qua nhiều câu truy vấn và có thể phản ánh dữ liệu cập nhật. Đừng bọc transaction qua HTTP chậm chỉ để gom kết quả.

### 7.6. Ứng dụng in ví dụ ra console

`src/main/java/demo/inlist/NamedInApplication.java`:

```java
package demo.inlist;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NamedInApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedInApplication.class, args);
    }

    @Bean
    CommandLineRunner runExample(ProductJdbcRepository products) {
        return args -> {
            var requested = List.of(3L, 1L, 3L, 999L, 2L);
            var selected =
                    products.findActiveInRequestedOrder(requested);

            System.out.println(
                    "ids=" + selected.stream().map(Product::id).toList()
            );
            System.out.println(
                    "skus=" + selected.stream().map(Product::sku).toList()
            );
            System.out.println(
                    "empty="
                    + products.findActiveInRequestedOrder(List.of()).size()
            );
        };
    }
}
```

Chạy trên một dự án Gradle có wrapper:

```bash
./gradlew bootRun
```

Trên Windows dùng `.\gradlew.bat bootRun` (PowerShell). Nếu chưa có wrapper, tạo bằng Gradle được cài trước hoặc chạy `gradle bootRun`. Java code và thư mục phải khớp với package/tên tệp ở trên.

Sau các log khởi động Spring Boot, đúng ba dòng `System.out.println` của demo là:

```text
ids=[3, 1]
skus=[NOTE, BOOK]
empty=0
```

Giải thích: 3 và 1 có tồn tại và active; 3 bị lặp trong request nhưng chỉ trả một lần; ID 999 không tồn tại; 2 tồn tại nhưng inactive; danh sách rỗng không chạy query.

## 8. Kiểm thử bằng JUnit 5

Tệp `src/test/java/demo/inlist/ProductJdbcRepositoryTest.java`:

```java
package demo.inlist;

import java.util.Arrays;
import java.util.List;
import java.util.stream.LongStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class ProductJdbcRepositoryTest {

    @Autowired
    ProductJdbcRepository repository;

    @Test
    void deduplicatesAndPreservesRequestedOrder() {
        List<Product> products =
                repository.findActiveInRequestedOrder(
                        List.of(3L, 1L, 3L, 4L, 1L)
                );
        assertEquals(
                List.of(3L, 1L, 4L),
                products.stream().map(Product::id).toList()
        );
    }

    @Test
    void dropsMissingAndInactiveRows() {
        List<Product> products =
                repository.findActiveInRequestedOrder(
                        List.of(999L, 2L, 1L)
                );
        assertEquals(1, products.size());
        assertEquals("BOOK", products.get(0).sku());
    }

    @Test
    void emptyListReturnsEmptyResult() {
        assertTrue(
                repository.findActiveInRequestedOrder(List.of()).isEmpty()
        );
    }

    @Test
    void rejectsNullOrNonPositiveElements() {
        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findActiveInRequestedOrder(
                        Arrays.asList(1L, null)
                )
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findActiveInRequestedOrder(
                        List.of(0L)
                )
        );
    }

    @Test
    void readsAcrossThreeChunks() {
        List<Long> ids = LongStream.rangeClosed(1, 1_200)
                .boxed()
                .toList();

        List<Product> products =
                repository.findActiveInRequestedOrder(ids);

        assertEquals(
                List.of(1L, 3L, 4L),
                products.stream().map(Product::id).toList()
        );
    }

    @Test
    void capsDistinctRequestIds() {
        List<Long> ids = LongStream.rangeClosed(1, 5_001)
                .boxed()
                .toList();

        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findActiveInRequestedOrder(ids)
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Sáu test kiểm tra behavior của contract. Test `readsAcrossThreeChunks` gửi 1.200 ID thành **ba statement** với 500 + 500 + 200 phần tử `IN` (và một tham số `active` mỗi statement). Việc DB chỉ có bốn sản phẩm không ảnh hưởng tới chia chunk; test xác minh kết quả gộp không mất ID 1/3/4.

**Giới hạn kiểm thử:** H2 không chứng minh giới hạn Oracle 19c hay SQL Server thực tế. Để kiểm tra vendor constraints, chạy integration test cùng query và kích thước biên trên **DBMS/driver đúng phiên bản** dùng ở production (Testcontainers nếu phù hợp), đo CPU, thời gian chuẩn bị statement, số round trips và số rows trả về.

## 9. Đếm bind parameters đúng khi có nhiều điều kiện

Giả sử repository xây câu SQL:

```sql
SELECT p.id, p.sku
FROM products p
WHERE p.tenant_id = :tenantId
  AND p.status IN (:statuses)
  AND p.id IN (:ids)
  AND p.created_at >= :fromDate
  AND p.created_at < :toDate;
```

Nếu `ids = 600`, `statuses = 4`, và có ba scalar `tenantId`, `fromDate`, `toDate`, statement dùng `600 + 4 + 3 = 607` vị trí bind. Nếu toàn câu SQL còn một điều kiện `p.parent_id IN (:ids)`, thành `1207` vị trí.

Đếm theo **số placeholder sau expansion**, không chỉ số named parameter **khác tên**. Nếu vendor limit = 999 trong cấu hình thực tế, việc `ids` có 600 ID vẫn có thể vượt khi dùng hai lần.

Một helper tính budget có thể được kiểm tra bằng Java thuần:

```java
public final class BindBudget {
    private BindBudget() {}

    public static int maxListItems(
            int perInExpressionLimit,
            int statementParamLimit,
            int fixedParamCount,
            int occurrences,
            int operationalLimit
    ) {
        if (perInExpressionLimit < 1
                || statementParamLimit < 1
                || fixedParamCount < 0
                || occurrences < 1
                || operationalLimit < 1) {
            throw new IllegalArgumentException("Invalid limits");
        }
        int free = statementParamLimit - fixedParamCount;
        int byTotal = free / occurrences;
        int maximum = Math.min(
                Math.min(perInExpressionLimit, byTotal),
                operationalLimit
        );
        if (maximum < 1) {
            throw new IllegalArgumentException("No bind budget remains");
        }
        return maximum;
    }

    public static void main(String[] args) {
        System.out.println(maxListItems(1000, 2000, 3, 2, 500));
        System.out.println(maxListItems(1000, 2100, 1, 1, 500));
    }
}
```

Đây là class Java độc lập (file `BindBudget.java`), chạy với Java 17:

```bash
javac BindBudget.java
java BindBudget
```

Stdout chính xác:

```text
500
500
```

Ví dụ đầu: tổng budget còn `2000 - 3 = 1997`, list xuất hiện hai lần, nên `floor(1997/2)=998`, áp `perInExpressionLimit=1000` và `operationalLimit=500` => 500. Ví dụ hai: `(2100 - 1)/1 = 2099`, nhưng còn `min(1000, 500)` => 500.

**Giới hạn của helper:** nó giả định mỗi phần tử list sử dụng **một bind position cho mỗi occurrence**; với `List<Object[]>` gồm tuple 2 hoặc 3 cột phải nhân số vị trí bind trên một tuple. Khi có nhiều list khác nhau, phải trừ riêng số bind của các list còn lại và scalar. Đây là công thức thiết kế, không phải API tự động hỏi database để xác định giới hạn.

## 10. Những nguy cơ thường xuất hiện ở production

### 10.1. Hơn giới hạn database: lỗi xuất hiện ở tầng nào?

Tùy DBMS/driver, lỗi có thể phát sinh khi chuẩn bị câu SQL, parse, bind hoặc execute. Spring JDBC thường chuyển `SQLException` thành họ `DataAccessException`, nhưng loại cụ thể và message phụ thuộc translator/vendor.

Không bắt mọi `DataAccessException` rồi trả dữ liệu rỗng: làm vậy che giấu một lỗi kỹ thuật nghiêm trọng thành “không có sản phẩm”. Khi biết input quá dài, **validate/chunk trước**, test với version production, và chuyển lỗi ngoài dự kiến thành response an toàn mà vẫn log nguyên nhân nội bộ.

### 10.2. N+1 và quá nhiều round trips khi chunk quá nhỏ

Nếu một request có 5.000 ID và chunk 10, bạn tạo 500 câu SQL, có thể làm độ trễ cao. Chunk 500 tạo 10 câu SQL; vẫn cần đo query time/plan, network và mức song song DB.

Tăng chunk size không luôn nhanh: câu SQL rất dài có thể tốn parse và plan cache, đặc biệt nếu mỗi request có độ dài list rất khác nhau. Có thể bucket kích thước list theo policy đã kiểm thử hoặc chuyển sang bảng staging/array cho tập lớn.

Không chạy quá nhiều chunk song song một cách vô hạn: mỗi truy vấn chiếm connection và tăng tải DB. Cân nhắc concurrency limit và pool capacity nếu cần parallelism.

### 10.3. Prepared-statement cache và SQL shape

`WHERE id IN (?, ?)` và `WHERE id IN (?, ?, ?)` là hai SQL text khác nhau. Số lượng biến thể quá lớn khiến driver/server statement cache kém hiệu quả; giảm số shapes hoặc dùng array/table approach có thể giúp, nhưng phải đo. Không tối ưu bằng cách lắp trực tiếp ID thành literal vì điều đó phá khả năng bind và tăng rủi ro injection.

### 10.4. Transaction và tính nhất quán qua nhiều chunk

Một danh sách cần trả snapshot đồng nhất tại một thời điểm có thể không đạt được nếu các chunk chạy trong các transaction khác nhau hoặc dưới isolation mặc định cho phép snapshot thay đổi. Với reporting/financial workflow cần nhất quán, xác định rõ ràng semantics:

- Nếu chỉ cần kết quả “gần thời điểm hiện tại”, nhiều SELECT độc lập có thể đủ.
- Nếu phải đồng nhất, dùng transaction và isolation/snapshot phù hợp, hoặc nạp tập ID vào staging rồi một join; kiểm tra lock/snapshot retention của DB.
- Với nhiều `UPDATE/DELETE` theo chunk và yêu cầu tất cả hoặc không gì, dùng transaction ở **service/use-case boundary**; nếu tác vụ quá lớn, cân nhắc job idempotent/checkpoint thay vì một transaction khổng lồ.

Không mở transaction rồi chờ HTTP chậm giữa các batch; việc này giữ connection/lock không cần thiết và không cải thiện tính nguyên tử với remote service.

### 10.5. Authorization và multi-tenant

Nếu frontend gửi `ids=[...]`, server không thể xem list đó là danh sách các bản ghi người dùng đã được phép xem. Query vẫn cần điều kiện `tenant_id = :tenantId` hoặc quyền truy cập ràng buộc theo user/group, với tenant ID xác thực từ server.

Dedupe và chunk phải duy trì mọi filter này **trong từng statement**, không được quên filter ở batch sau. Tổng bind count phải cộng tham số tenant/quyền. Việc ID không được trả về có thể do không tồn tại, inactive hoặc thiếu quyền; error response phải tôn trọng chính sách không lộ tồn tại dữ liệu.

### 10.6. Cache/memory và request body

Ngay cả khi DB hỗ trợ 65.535 parameters, HTTP request chứa hàng chục nghìn ID có chi phí parse JSON, validation, cấp phát bộ nhớ, logging và caching. Đặt request size, rate limit và maximum distinct IDs phù hợp; tránh log nguyên list ID nếu chứa thông tin nhạy cảm. Thay bằng số lượng ID, request ID, thời gian xử lý và metric batch count.

### 10.7. Query plan cho IN dài

Với cột `id` có B-tree index hoặc PRIMARY KEY, engine có thể tối ưu `IN` nhỏ hiệu quả; với list rất dài và tỷ lệ match lớn, index probes có thể không còn rẻ hơn scan/join. Statistics, skew, selectivity và optimizer khác nhau giữa DBMS. Dùng execution plan và số liệu thật, không quyết định chỉ từ số lượng placeholders.

Trong PostgreSQL, có thể so sánh `EXPLAIN (ANALYZE, BUFFERS)` giữa `IN`, `= ANY(array)` và join temp table trên môi trường test. Chỉ chạy `EXPLAIN ANALYZE` với thao tác ghi nếu hiểu nó **thực sự thực thi** statement; dùng transaction rollback/test DB thích hợp.

## 11. Phân biệt batchUpdate với chunk IN

Có hai bài toán khác nhau:

**A. Một câu SQL lấy/tác động nhiều ID:**

```sql
SELECT id, sku FROM products WHERE id IN (:ids);
```

Ở đây `ids` là **một list được expand thành nhiều bind positions trong một statement**. Giới hạn statement và IN list áp dụng trực tiếp.

**B. Chạy cùng một câu SQL nhiều lần với các bind khác nhau:**

```sql
UPDATE products SET active = :active WHERE id = :id;
```

`NamedParameterJdbcTemplate.batchUpdate(...)` nhận **một nhóm bộ tham số** cho nhiều lần thực thi câu SQL tương ứng. Mỗi execution chỉ có các bind của **một bản ghi**, không biến `:id` thành một danh sách IN. Đây là JDBC batch execution, thường tối ưu round-trip ghi dữ liệu.

Dùng `batchUpdate` **không** tự sửa lỗi một statement có `IN (:ids)` chứa 20.000 phần tử; nếu SQL của từng item trong batch vẫn expand 20.000 giá trị, giới hạn từng statement vẫn còn.

Với update nhiều IDs, có thể chọn batchUpdate từng ID, chunk `UPDATE ... WHERE id IN (...)`, hoặc nạp staging rồi `UPDATE ... FROM`/`MERGE` theo dialect. Chọn theo atomicity, tốc độ và khóa DB.

## 12. Bảng quyết định chọn chiến lược

| Quy mô/nhu cầu | Lựa chọn ưu tiên để đánh giá | Vì sao |
| --- | --- | --- |
| 0 ID, semantics lọc membership | Trả rỗng trước query | Không tạo `IN ()` |
| Vài ID đến vài trăm ID | `NamedParameterJdbcTemplate` + `IN (:ids)` | Đơn giản, bind an toàn |
| Nhiều ID vừa phải, dưới request cap | Dedupe + chunk thành nhiều statement | Tránh chạm limit từng statement |
| Nhiều chục nghìn ID, query lặp hoặc join phức tạp | Staging/temp table + join | Không tạo cực nhiều placeholders |
| PostgreSQL, list lớn, đọc membership | SQL array + `= ANY (?)` hoặc `UNNEST` | Một array bind, nhưng vẫn phải benchmark |
| SQL Server, danh sách/bảng dữ liệu lớn | TVP hoặc temp table | Có cấu trúc table-valued, tránh hàng nghìn scalar bind |
| ID đã ở bảng khác trong DB | `JOIN` / `EXISTS` | Không vòng dữ liệu qua ứng dụng |
| Nhiều cặp khóa ghép | Tuple list nhỏ hoặc staging hai cột | Mỗi tuple cần nhiều bind, giới hạn theo dialect |
| Cần kết quả đúng thứ tự ID input | Map theo PK rồi reorder | `IN` không hứa thứ tự |
| Cần atomic update qua nhiều batch | Transaction/use-case hoặc staging-based update | Tránh partial success |

Một số trường hợp cần **kết hợp**: request cap + dedupe + chunk + quan sát metrics, hoặc staging + transaction + TTL cleanup. Không có kích thước tối ưu chung cho mọi engine.

## 13. Checklist kiểm tra trước khi merge

- Đầu vào `ids` có thể rỗng không? Nếu có, semantics và branch rõ ràng chưa?
- Có từ chối hoặc xử lý `null` đúng SQL three-valued logic chưa, đặc biệt với `NOT IN`?
- ID lặp có được dedupe phù hợp với hợp đồng đầu ra không?
- Query cần giữ thứ tự input hay sort do DB? Đã có logic rõ thay vì tin vào thứ tự của `IN` chưa?
- Mọi dữ liệu đầu vào có được bind thành value thay vì nối trực tiếp thành literal SQL không?
- Tổng bind positions đã bao gồm **mọi** list, scalar, tuple và repeated named parameter chưa?
- Đã xác minh hạn mức của **DBMS đúng phiên bản và driver** đang dùng, không dựa vào con số cho hệ khác chưa?
- Batch size có nhỏ hơn cả giới hạn IN list, tổng parameters và ngưỡng vận hành không?
- Chunking có thật sự chạy nhiều statements, thay vì ghép nhiều `IN` trong một SQL rồi vượt tổng bind budget không?
- Có request cap, timeout, rate limit, memory và logging policy cho danh sách lớn không?
- Có filter tenant/authorization **trong mọi batch** không?
- Với multi-statement read/update, đã xác định isolation, atomicity và retry/idempotency phù hợp chưa?
- Đã đo execution plan, p95/p99, số round trips, SQL parse và connection usage khi số ID tăng chưa?
- Đã có integration tests cho 0/1/n ID, duplicate, NULL, ID thiếu, inactive, ranh giới batch và DB version thật chưa?

## 14. Bài tập tự kiểm tra

**Bài 1 — mở rộng tham số.** Với `ids = [10, 20, 30]`, `statuses = ["OPEN", "PAID"]` và một `tenantId`, câu SQL `WHERE id IN (:ids) AND status IN (:statuses) AND tenant_id = :tenantId` có bao nhiêu bind positions? Viết dạng placeholders tương đương.

**Bài 2 — giới hạn tổng.** Một hệ có policy tổng 2.000 bind positions, query có hai lần `IN (:ids)` và bốn scalar. Nếu giới hạn mỗi `IN` là 1.000, kích thước list lý thuyết tối đa là bao nhiêu? Nếu policy vận hành chọn tối đa 500 thì sao?

**Bài 3 — xử lý rỗng.** API `POST /products/filter` nhận `ids=[]`. Thiết kế hai hợp đồng khác nhau: (a) rỗng nghĩa là không có sản phẩm; (b) vắng filter nghĩa là lấy tất cả. Chỉ ra vì sao phải phân biệt `ids: []` với thuộc tính `ids` không xuất hiện.

**Bài 4 — NULL.** Vì sao `WHERE sku NOT IN ('BOOK', NULL)` có thể không trả sản phẩm `PEN`? Hãy thiết kế validation ngăn null và nếu muốn bao gồm cột NULL, viết điều kiện có `IS NULL` rõ ràng.

**Bài 5 — chunk.** Danh sách 1.200 ID, chunk 500, một scalar active mỗi SQL. Có bao nhiêu statement, bao nhiêu vị trí bind ở từng statement? Nếu chỉ viết `id IN (:p1) OR id IN (:p2) OR id IN (:p3)` trong **một** SQL, tổng parameters là bao nhiêu?

**Bài 6 — lựa chọn giải pháp.** 50.000 ID cần join với hai bảng trong PostgreSQL, còn 50.000 ID khác cần truyền tới SQL Server. Liệt kê ưu/nhược của chunk, array/ANY, bảng staging và TVP (nơi hỗ trợ), đặc biệt về round trips, optimizer, transaction, cleanup và driver.

**Gợi ý đáp án:** (1) `3+2+1=6` bind; (2) `floor((2000-4)/2)=998`, policy 500 ⇒ 500; (3) explicit empty ⇒ kết quả rỗng, omitted filter chỉ trả tất cả nếu contract cho phép và vẫn có phân quyền/phân trang; (4) ba-valued logic, reject null element, dùng điều kiện thêm `OR sku IS NULL` có chủ đích; (5) ba statements với 501, 501, 201; ghép một SQL vẫn có 1.203 binds; (6) cần benchmark trên DBMS/driver cụ thể, không dùng một con số hay pattern cho mọi engine.

## 15. Kết luận

`NamedParameterJdbcTemplate` giúp viết câu SQL dễ đọc và truyền danh sách an toàn bằng `IN (:ids)`, nhưng về cơ chế nó **mở rộng danh sách thành nhiều placeholders**. Vì vậy:

- **Ít ID:** dùng named list đơn giản.
- **Không ID:** short-circuit theo semantics đã định.
- **Nhiều ID:** giới hạn request, validate/dedupe, tính tổng bind budget, chia thành nhiều statements hoặc dùng một cấu trúc dữ liệu database-native phù hợp.
- **Tập rất lớn:** ưu tiên phép join với bảng/staging hoặc array/TVP có kiểm thử, thay vì tạo SQL chứa vô số placeholders.
- **Kết quả đúng:** nhớ `IN` không bảo đảm thứ tự và không nhân bản hàng theo số lần ID xuất hiện; kiểm soát missing rows, tenant filter, isolation và rollback theo hợp đồng nghiệp vụ.

Thiết kế tốt không chỉ tránh lỗi “too many parameters”. Nó giữ SQL bind an toàn, giới hạn tài nguyên, trả kết quả dễ dự đoán và cho phép chuyển đổi chiến lược khi dữ liệu tăng lên.

## 16. Tài liệu tham khảo

- Spring Framework — [Passing in Lists of Values for IN Clause](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html).
- Spring Framework — [NamedParameterJdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html).
- Spring Framework — [MapSqlParameterSource Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html).
- Oracle Database 19c — [IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html), giới hạn expression-list theo version.
- Oracle Database 26ai — [IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/IN-Condition.html), giới hạn mới theo version.
- Microsoft SQL Server — [Maximum Capacity Specifications](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server); [Using table-valued parameters](https://learn.microsoft.com/en-us/sql/connect/jdbc/using-table-valued-parameters).
- pgJDBC — [Initializing the Driver / use documentation](https://jdbc.postgresql.org/documentation/use/), extended protocol bind limits.
- SQLite — [Limits in SQLite](https://www.sqlite.org/limits.html), host parameter number and configurable limits.
- PostgreSQL — [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html), [Array Comparisons](https://www.postgresql.org/docs/current/functions-comparisons.html).
