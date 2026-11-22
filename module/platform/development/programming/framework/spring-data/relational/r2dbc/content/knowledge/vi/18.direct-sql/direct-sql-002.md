# Bind tham số có giá trị và bindNull

Khi dùng Spring Data Relational R2DBC, ứng dụng thường gửi SQL qua **DatabaseClient**. Các giá trị đầu vào được truyền vào câu SQL bằng bind parameter. Với tham số có giá trị, dùng **bind()**. Với tham số cần mang giá trị SQL **NULL**, dùng **bindNull()** và chỉ rõ kiểu Java tương ứng.

Hai thao tác này có mục đích khác nhau:

- **bind(name, value)** gắn một giá trị khác null vào placeholder.
- **bindNull(name, javaType)** gắn một giá trị SQL NULL có kiểu dữ liệu xác định vào placeholder.

R2DBC SPI không xem Java null là một giá trị thông thường có thể truyền vào bind(). Vì vậy, không nên gọi bind("nickname", null). Cần gọi bindNull("nickname", String.class).

Một điểm dễ nhầm hơn nữa: **bindNull chỉ gắn SQL NULL vào tham số; nó không tự biến điều kiện column = :parameter thành column IS NULL, cũng không tự bỏ điều kiện khỏi WHERE.** Muốn tìm cột có giá trị NULL, cần viết predicate IS NULL. Muốn bỏ qua một filter không được gửi, cần bỏ predicate đó khỏi câu SQL hoặc thiết kế biểu thức tùy chọn có chủ đích.

## 1. Bind parameter là gì?

Bind parameter là placeholder trong câu SQL. Ứng dụng cung cấp giá trị riêng cho placeholder thay vì nối dữ liệu đầu vào trực tiếp vào chuỗi SQL.

Ví dụ:

~~~sql
SELECT id, name
FROM customer
WHERE email = :email;
~~~

Trong Spring DatabaseClient, có thể bind giá trị như sau:

~~~java
Mono<CustomerSummary> customer =
    databaseClient.sql(
            "SELECT id, name FROM customer WHERE email = :email"
        )
        .bind("email", "an@example.com")
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .one();
~~~

Ở đây:

- :email là named parameter trong câu SQL của ứng dụng.
- bind("email", ...) gắn giá trị vào tham số có tên email.
- DatabaseClient xử lý việc chuyển named parameter thành bind marker mà R2DBC driver sử dụng.
- Driver thực hiện bind giá trị theo cơ chế và codec của database tương ứng.

Tên placeholder không phải là một phần dữ liệu. Giá trị email được bind riêng, nên ký tự đặc biệt trong email không thể làm thay đổi cấu trúc SQL như cách nối chuỗi trực tiếp.

## 2. bind() và bindNull() khác nhau thế nào?

| API | Dùng khi | Ví dụ |
|---|---|---|
| bind(String, Object) | Giá trị có thật và khác null | bind("name", "An") |
| bindNull(String, Class<?>) | Muốn bind SQL NULL | bindNull("nickname", String.class) |

Ví dụ một bảng có cột nickname cho phép NULL:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    nickname VARCHAR(100) NULL
);
~~~

Khi thêm khách hàng không có nickname:

~~~java
Mono<Void> insert =
    databaseClient.sql(
        "INSERT INTO customer (id, name, nickname) " +
        "VALUES (:id, :name, :nickname)"
    )
    .bind("id", 42L)
    .bind("name", "An")
    .bindNull("nickname", String.class)
    .then();
~~~

Tham số nickname được gửi dưới dạng SQL NULL. Cột database phải cho phép NULL; nếu cột có ràng buộc NOT NULL, database sẽ từ chối câu lệnh.

Với giá trị khác null, dùng bind:

~~~java
DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(
        "INSERT INTO customer (id, name, nickname) " +
        "VALUES (:id, :name, :nickname)"
    );

spec = spec.bind("id", 42L);
spec = spec.bind("name", "An");
spec = spec.bind("nickname", "Annie");
~~~

Các phương thức bind trả về một GenericExecuteSpec tiếp tục được dùng để cấu hình câu lệnh. Hãy giữ lại giá trị trả về khi nối hoặc gán lại spec.

## 3. Vì sao bind(null) không đúng?

Không nên viết:

~~~java
databaseClient.sql(
        "INSERT INTO customer (name, nickname) " +
        "VALUES (:name, :nickname)"
    )
    .bind("name", "An")
    .bind("nickname", null);
~~~

API bind thông thường yêu cầu giá trị khác null. R2DBC cần biết kiểu dữ liệu để mã hóa giá trị NULL theo database/driver, nên cung cấp API riêng bindNull.

Viết đúng:

~~~java
databaseClient.sql(
        "INSERT INTO customer (name, nickname) " +
        "VALUES (:name, :nickname)"
    )
    .bind("name", "An")
    .bindNull("nickname", String.class);
~~~

Việc một biến Java được đánh dấu @Nullable không thay đổi quy tắc của R2DBC. Annotation nullable giúp mô tả hợp đồng trong code và hỗ trợ công cụ phân tích; khi thực thi vẫn phải chọn bind() hoặc bindNull() đúng cách.

## 4. Kiểu Java trong bindNull có ý nghĩa gì?

Chữ ký của R2DBC SPI cho bind null yêu cầu kiểu Java, ví dụ:

~~~java
statement.bindNull(0, String.class);
~~~

Spring DatabaseClient cung cấp dạng named parameter:

~~~java
spec.bindNull("nickname", String.class);
~~~

Kiểu này giúp driver biết cần mã hóa SQL NULL theo kiểu dữ liệu nào. Một số kiểu thường gặp:

| Cột hoặc dữ liệu | Kiểu Java thường dùng |
|---|---|
| VARCHAR, CHAR, TEXT | String.class |
| BIGINT | Long.class |
| INTEGER | Integer.class |
| BOOLEAN | Boolean.class |
| DECIMAL, NUMERIC | BigDecimal.class |
| DATE | LocalDate.class |
| TIMESTAMP | LocalDateTime.class |
| TIMESTAMP WITH TIME ZONE | Thường là OffsetDateTime.class hoặc kiểu được driver hỗ trợ |
| UUID | UUID.class |

Kiểu Java cần tương thích với mapping và codec của R2DBC driver đang dùng. Với kiểu database đặc thù, có thể cần custom converter hoặc codec do driver cung cấp.

Không nên dùng Object.class cho mọi tham số null nếu đã biết kiểu cột. Kiểu quá chung có thể khiến driver không chọn được codec hoặc database không suy luận được kiểu SQL cần thiết.

Ví dụ:

~~~java
spec = spec.bindNull("ownerId", Long.class);
spec = spec.bindNull("createdAt", LocalDateTime.class);
spec = spec.bindNull("price", BigDecimal.class);
~~~

Lưu ý: bindNull nhận kiểu Java, không phải chuỗi tên kiểu SQL. Truyền Long.class, không truyền "BIGINT".

## 5. Bind giá trị và bindNull trong R2DBC SPI trực tiếp

Nếu dùng R2DBC SPI cấp thấp, Statement thường dùng chỉ số bind marker:

~~~java
Publisher<? extends Result> result =
    connection.createStatement(
            "INSERT INTO customer (name, nickname) VALUES ($1, $2)"
        )
        .bind(0, "An")
        .bindNull(1, String.class)
        .execute();
~~~

Trong ví dụ, chỉ số bind bắt đầu từ 0. Cú pháp $1, $2 là dạng marker của một số driver như PostgreSQL; driver khác có thể dùng dạng khác. Với SPI trực tiếp, cần tuân theo cú pháp marker và quy tắc bind của driver cụ thể.

Khi dùng DatabaseClient, ứng dụng thường viết named parameter như :name. Spring chuyển chúng sang dạng marker mà driver yêu cầu. Không nên nhầm cú pháp named parameter của Spring với cú pháp SQL marker gốc của mọi R2DBC driver.

## 6. bindNull không đồng nghĩa với IS NULL

Đây là điểm quan trọng nhất khi viết điều kiện WHERE.

Giả sử muốn tìm khách hàng có nickname là SQL NULL. Câu sau không đúng:

~~~sql
SELECT id, name
FROM customer
WHERE nickname = :nickname;
~~~

Nếu bind nickname bằng SQL NULL, biểu thức nickname = NULL không trở thành TRUE. Theo logic ba giá trị của SQL, phép so sánh với NULL cho kết quả UNKNOWN. Vì vậy, dòng có nickname NULL không được chọn bởi WHERE.

Muốn tìm các dòng có giá trị NULL, phải viết:

~~~sql
SELECT id, name
FROM customer
WHERE nickname IS NULL;
~~~

Tương tự:

- Dùng IS NOT NULL để tìm giá trị không null.
- Không dùng = NULL hoặc <> NULL để kiểm tra null.
- Bind một tham số null không thay thế được toán tử IS NULL.

### Khi nào vẫn cần bindNull trong một biểu thức WHERE?

Có trường hợp SQL dùng tham số null để biểu diễn “không áp dụng bộ lọc”:

~~~sql
SELECT id, name
FROM customer
WHERE (:status IS NULL OR status = :status);
~~~

Nếu status được bind bằng SQL NULL, nhánh :status IS NULL là TRUE và điều kiện không lọc theo status. Nếu bind một chuỗi như ACTIVE, nhánh đầu FALSE và truy vấn chỉ lấy dòng có status bằng ACTIVE.

Trong trường hợp này, bindNull("status", String.class) là hợp lệ vì mục đích là dùng null làm tín hiệu bỏ qua filter. Đây là semantics khác với yêu cầu “tìm dòng có status NULL”.

Một số database hoặc driver có thể cần thêm thông tin kiểu/cast để suy luận tham số null, nhất là khi placeholder chỉ xuất hiện trong biểu thức IS NULL. Nếu gặp lỗi suy luận kiểu, hãy kiểm tra SQL được gửi, kiểu bind và quy tắc database; có thể cần CAST phù hợp với database đích.

## 7. Phân biệt ba ý nghĩa: bỏ filter, tìm NULL và so sánh với giá trị

Một API tìm kiếm có thể cần ba trạng thái:

1. Không gửi filter: không áp dụng điều kiện status.
2. Yêu cầu status NULL: chỉ lấy dòng có cột status là SQL NULL.
3. Gửi status = ACTIVE: chỉ lấy dòng có status bằng ACTIVE.

Ba trạng thái này không nên bị gộp thành một biến Java nullable duy nhất nếu API cần phân biệt cả ba.

| Ý định | SQL nên tạo | Có cần bindNull? |
|---|---|---|
| Không lọc status | Không thêm predicate status | Không |
| Tìm status NULL | status IS NULL | Không |
| Tìm status khác NULL | status IS NOT NULL | Không |
| Tìm status bằng ACTIVE | status = :status | Không, dùng bind giá trị |
| Tham số null có nghĩa bỏ qua filter trong một SQL cố định | (:status IS NULL OR status = :status) | Có |

Ví dụ xây dựng predicate tường minh:

~~~java
List<String> predicates = new ArrayList<>();
Map<String, Object> parameters = new LinkedHashMap<>();

if (filter.statusMode() == StatusMode.IS_NULL) {
    predicates.add("c.status IS NULL");
} else if (filter.statusMode() == StatusMode.EQUALS) {
    predicates.add("c.status = :status");
    parameters.put("status", filter.status());
}
// StatusMode.ANY: không thêm predicate status.
~~~

Sau đó chỉ bind tham số cho những placeholder thực sự có trong SQL. Cách này phân biệt rõ absent, explicit null và một giá trị cụ thể.

## 8. Ví dụ bind tham số nullable trong DatabaseClient

Một helper nhỏ có thể chọn bind() hoặc bindNull() dựa trên giá trị:

~~~java
private DatabaseClient.GenericExecuteSpec bindNullable(
        DatabaseClient.GenericExecuteSpec spec,
        String name,
        Object value,
        Class<?> javaType) {

    if (value == null) {
        return spec.bindNull(name, javaType);
    }

    return spec.bind(name, value);
}
~~~

Sử dụng khi câu SQL đã có placeholder tương ứng:

~~~java
DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(
        "INSERT INTO customer (name, nickname, owner_id) " +
        "VALUES (:name, :nickname, :ownerId)"
    );

spec = spec.bind("name", "An");
spec = bindNullable(spec, "nickname", nickname, String.class);
spec = bindNullable(spec, "ownerId", ownerId, Long.class);

return spec.fetch().rowsUpdated();
~~~

Nếu nickname null, helper gọi bindNull("nickname", String.class). Nếu ownerId có giá trị, helper gọi bind thông thường. Cả hai placeholder vẫn tồn tại trong SQL; helper chỉ quyết định giá trị được bind.

Không dùng helper này để quyết định một filter có được đưa vào SQL hay không. Việc đó cần được quyết định ở bước xây dựng predicate. Nếu một placeholder không xuất hiện trong câu SQL, không nên bind nó.

## 9. bindNull khi INSERT và UPDATE

### INSERT một cột nullable

Khi muốn lưu SQL NULL vào cột:

~~~java
databaseClient.sql(
        "INSERT INTO customer (id, name, nickname) " +
        "VALUES (:id, :name, :nickname)"
    )
    .bind("id", 42L)
    .bind("name", "An")
    .bindNull("nickname", String.class)
    .fetch()
    .rowsUpdated();
~~~

### UPDATE một cột thành NULL

Khi người dùng xóa nickname và nghiệp vụ muốn lưu giá trị SQL NULL:

~~~java
databaseClient.sql(
        "UPDATE customer SET nickname = :nickname WHERE id = :id"
    )
    .bindNull("nickname", String.class)
    .bind("id", 42L)
    .fetch()
    .rowsUpdated();
~~~

Đây là một partial update có chủ đích: cột nickname được đặt thành NULL, các cột không xuất hiện trong SET không bị thay đổi bởi câu lệnh này.

Nếu API update dùng null với nghĩa “không thay đổi trường nickname”, thì không được bindNull. Hãy bỏ cột nickname khỏi SET. Nếu null có nghĩa “xóa giá trị hiện tại”, hãy dùng bindNull. Semantics phải được định nghĩa trong hợp đồng API.

## 10. bindNull với bộ lọc tùy chọn

Giả sử filter có trường status. Có hai cách triển khai phổ biến.

### Cách A: tạo SQL động và bỏ predicate khi filter absent

~~~java
String sql =
    "SELECT id, name FROM customer WHERE tenant_id = :tenantId";

if (status != null) {
    sql += " AND status = :status";
}

DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(sql)
        .bind("tenantId", tenantId);

if (status != null) {
    spec = spec.bind("status", status);
}
~~~

Absent thì không thêm predicate và cũng không bind tham số. Hãy xây dựng toàn bộ SQL trước khi gọi databaseClient.sql(sql) để placeholder và bind khớp nhau.

### Cách B: SQL cố định, null có nghĩa bỏ qua filter

~~~java
DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(
        "SELECT id, name FROM customer " +
        "WHERE tenant_id = :tenantId " +
        "AND (:status IS NULL OR status = :status)"
    )
    .bind("tenantId", tenantId);

if (status == null) {
    spec = spec.bindNull("status", String.class);
} else {
    spec = spec.bind("status", status);
}
~~~

Cách B dùng bindNull làm tín hiệu bỏ qua điều kiện. Cần xác nhận driver/database suy luận kiểu tham số null đúng cách. Với nhiều filter, SQL dạng (:p IS NULL OR column = :p) có thể khó tối ưu hơn các predicate động; hãy đo execution plan.

Nếu null có nghĩa tìm cột NULL, dùng predicate status IS NULL thay vì Cách B.

## 11. bindNull trong IN, LIKE và các phép so sánh

### IN

~~~sql
WHERE owner_id IN (:ownerId)
~~~

Nếu bind ownerId là NULL, điều kiện IN không trở thành một phép tìm kiếm owner_id NULL. Muốn lấy cả các dòng có owner_id NULL, phải viết rõ:

~~~sql
WHERE owner_id IN (:ownerIds)
   OR owner_id IS NULL
~~~

Danh sách có phần tử null cũng không thay thế được IS NULL; các phép so sánh trong IN tuân theo logic ba giá trị SQL. Cần xử lý riêng giá trị null trong danh sách nếu nghiệp vụ yêu cầu.

### LIKE

~~~sql
WHERE name LIKE :pattern
~~~

Bind null vào pattern không có nghĩa là tìm mọi tên hoặc chuỗi rỗng. Kết quả phép LIKE với NULL là UNKNOWN. Nếu không muốn áp dụng filter tên, hãy bỏ predicate hoặc dùng biểu thức bỏ qua filter có chủ đích. Nếu muốn tìm tên NULL, dùng name IS NULL.

### Khoảng thời gian và so sánh

~~~sql
WHERE created_at >= :createdFrom
~~~

Nếu createdFrom là NULL, điều kiện không trở thành “không giới hạn thời gian” một cách tự động. Nó không chọn được dòng theo phép so sánh. Hãy bỏ predicate hoặc viết logic nullable rõ ràng.

## 12. Named parameter và positional parameter

Spring DatabaseClient thường cho phép viết named parameter:

~~~java
databaseClient.sql(
        "SELECT id FROM customer WHERE email = :email"
    )
    .bind("email", email);
~~~

Named parameter giúp code dễ đọc vì liên kết giá trị với tên placeholder. Spring chuyển các placeholder này thành dạng marker mà driver sử dụng.

Ở R2DBC SPI trực tiếp, statement thường bind theo vị trí:

~~~java
statement
    .bind(0, email)
    .bindNull(1, String.class);
~~~

Chỉ số thường bắt đầu từ 0 trong API R2DBC. Cú pháp SQL marker và cách đánh số trong câu lệnh phụ thuộc driver.

Khi dùng SPI trực tiếp, phải bảo đảm:

- Số lượng marker phù hợp số lần bind.
- Chỉ số bind hợp lệ và không bị thiếu.
- Giá trị null dùng bindNull(index, javaType).
- Cú pháp marker phù hợp driver.

## 13. Bind tham số an toàn và SQL injection

Không nối dữ liệu người dùng vào câu SQL:

~~~java
String sql =
    "SELECT id FROM customer WHERE email = '" + email + "'";
~~~

Hãy bind giá trị:

~~~java
databaseClient.sql(
        "SELECT id FROM customer WHERE email = :email"
    )
    .bind("email", email);
~~~

Bind parameter bảo vệ cấu trúc SQL khỏi việc input bị diễn giải như cú pháp. Tuy nhiên, bind chỉ dùng cho giá trị, không dùng cho tên bảng, tên cột, toán tử hoặc hướng sắp xếp. Những thành phần SQL động đó phải được chọn từ whitelist do ứng dụng kiểm soát.

bindNull cũng giữ nguyên cấu trúc câu SQL: nó chỉ cung cấp một giá trị NULL đã định kiểu. Nó không phải cách nối chuỗi, không phải cơ chế bỏ predicate và cũng không phải cách kiểm tra quyền truy cập.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi bind(name, null) | API/driver từ chối giá trị null | Dùng bindNull(name, JavaType.class) |
| Dùng bindNull nhưng quên kiểu | Không có kiểu để chọn codec hoặc suy luận SQL | Chỉ rõ kiểu Java phù hợp |
| Truyền tên SQL type dạng String | Sai kiểu tham số API | Truyền String.class, Long.class... |
| Dùng column = :value với value null để tìm NULL | Không trả về các dòng NULL | Dùng column IS NULL |
| Nghĩ bindNull tự bỏ filter | Predicate vẫn được thực thi | Bỏ predicate hoặc viết biểu thức optional rõ ràng |
| Nghĩ null trong LIKE là wildcard | Điều kiện không khớp như mong đợi | Dùng pattern hợp lệ hoặc bỏ filter |
| Dùng null trong IN để tìm cột NULL | Không có semantics mong muốn | Thêm OR column IS NULL |
| Dùng primitive cho trường nullable | Không biểu diễn được null | Dùng wrapper như Long, Boolean |
| Bỏ qua kiểu dữ liệu driver không hỗ trợ | Lỗi codec hoặc conversion | Kiểm tra driver, converter và database type |
| Bind placeholder không có trong SQL | Lỗi cấu hình statement | Đồng bộ danh sách predicate và tham số |
| Có placeholder nhưng quên bind | Statement không thực thi được | Kiểm tra mọi nhánh tạo SQL |
| Dùng bind cho tên cột | Database coi đó là giá trị | Dùng whitelist identifier |

## 15. Kiểm thử bind giá trị và bindNull

Nên kiểm thử cả trường hợp có giá trị lẫn SQL NULL trên database và R2DBC driver thực tế.

Ví dụ bộ trường hợp cho cột nickname:

| Đầu vào | Cách bind | Kết quả mong đợi |
|---|---|---|
| Annie | bind("nickname", "Annie") | Lưu chuỗi Annie |
| null, muốn lưu NULL | bindNull("nickname", String.class) | Cột nickname là SQL NULL |
| null, muốn giữ nguyên khi update | Không thêm nickname vào SET | Giá trị cũ không đổi |
| null, muốn tìm dòng NULL | SQL nickname IS NULL | Chỉ lấy dòng nickname NULL |
| null, muốn bỏ qua filter | Bỏ predicate hoặc bindNull trong biểu thức optional | Không lọc theo nickname |

Ngoài kết quả dữ liệu, nên xác nhận:

- Cột có cho phép NULL hay không.
- Driver có codec cho kiểu Java được truyền vào bindNull không.
- Database có suy luận được kiểu tham số null trong biểu thức hay cần CAST.
- Mọi nhánh SQL đều bind đủ placeholder.
- Không có input nào được nối trực tiếp vào SQL.
- Hành vi absent và explicit null đúng với hợp đồng API.

Kiểm thử tích hợp giúp phát hiện khác biệt về kiểu dữ liệu, placeholder và null handling giữa các R2DBC driver. Một bài test chỉ chạy trên mock không thể chứng minh driver thực tế mã hóa SQL NULL đúng cách.

## 16. Quy trình chọn bind() hay bindNull()

Trước khi bind một giá trị, hãy trả lời lần lượt:

1. Placeholder có thực sự tồn tại trong câu SQL không?
2. Giá trị Java có null không?
3. Nếu null, nghiệp vụ muốn ghi SQL NULL, so sánh với NULL, hay bỏ qua filter?
4. Nếu muốn ghi hoặc truyền SQL NULL, kiểu Java tương ứng là gì?
5. Nếu muốn so sánh với NULL, câu SQL đã dùng IS NULL hoặc IS NOT NULL chưa?
6. Nếu muốn bỏ qua filter, predicate có được bỏ khỏi SQL hoặc có biểu thức optional đúng semantics không?
7. Driver và database có hỗ trợ kiểu bind đó không?

Quy tắc chọn API:

~~~text
Giá trị đầu vào
      |
      v
Có null không?
   /       \
 Không      Có
  |          |
  v          v
bind()    Nghiệp vụ muốn gì?
             |
      +------+------+
      |      |      |
    Lưu NULL Tìm NULL Bỏ filter
      |      |      |
      v      v      v
  bindNull  IS NULL Bỏ predicate
            (không
          cần bindNull)
~~~

## 17. Ghi nhớ

- bind(name, value) dành cho giá trị khác null.
- bindNull(name, javaType) dành cho tham số SQL NULL và phải chỉ rõ kiểu Java tương ứng.
- R2DBC SPI có Statement.bind(index, value) và Statement.bindNull(index, javaType); chỉ số bind thường bắt đầu từ 0.
- bindNull không tự thay = bằng IS NULL, không tự bỏ predicate và không tự tạo wildcard.
- Trong SQL, so sánh = NULL hoặc <> NULL không dùng để kiểm tra null; hãy dùng IS NULL hoặc IS NOT NULL.
- Phân biệt không gửi filter, gửi null để tìm SQL NULL và gửi một giá trị cụ thể.
- Khi update, null có thể mang nghĩa đặt cột thành NULL hoặc giữ nguyên cột; hợp đồng API phải nói rõ.
- Dùng đúng Java type để driver chọn codec và database xử lý kiểu dữ liệu.
- Không nối input vào SQL; bind parameter chỉ dành cho giá trị, còn identifier động phải qua whitelist.
- Kiểm thử null handling với đúng R2DBC driver và database mục tiêu.
