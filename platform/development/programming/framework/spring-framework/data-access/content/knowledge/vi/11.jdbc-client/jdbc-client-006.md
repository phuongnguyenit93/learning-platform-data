# JdbcClient: single(), optional(), list() và hợp đồng số lượng kết quả

## Mục tiêu học tập

Một truy vấn JDBC có thể trả **0 dòng**, **1 dòng** hoặc **nhiều dòng**. Không phải API nào cũng coi ba tình huống đó như nhau. Khi dùng `JdbcClient` của Spring Framework, bạn thường kết thúc câu lệnh bằng một trong ba phương thức:

- `list()`: nhận tập kết quả **0..N dòng** dưới dạng `List<T>`.
- `optional()`: nhận **0 hoặc 1** kết quả được ánh xạ thành `Optional<T>`; **nhiều hơn 1 dòng là lỗi**.
- `single()`: yêu cầu **đúng 1** kết quả ánh xạ **không null**; thiếu dòng, thừa dòng hoặc giá trị ánh xạ null có các ngoại lệ tương ứng trong Spring Framework 6.2.

Đây là **hợp đồng số lượng kết quả** (*result cardinality contract*): code thể hiện trước điều nó coi là hợp lệ, rồi Spring kiểm tra kết quả truy vấn thực tế.

Sau bài này, bạn có thể:

1. Viết câu truy vấn với `JdbcClient.sql(...).param(...).query(...).single()/optional()/list()`.
2. Chọn API đúng cho một record bắt buộc có, một record có thể vắng mặt, hoặc một tập record.
3. Giải thích chính xác hành vi khi SQL trả 0, 1 hoặc 2+ dòng, thay vì lầm tưởng `optional()` lấy dòng đầu hoặc `single()` trả null khi không tìm thấy.
4. Phân biệt **không có dòng** với **có một dòng nhưng giá trị cột SQL là NULL**; hiểu điểm đặc biệt của Spring Framework 6.2.
5. Dùng `RowMapper<T>` hoặc `query(Class<T>)` phù hợp, xử lý ngoại lệ `EmptyResultDataAccessException`, `IncorrectResultSizeDataAccessException`, và `TypeMismatchDataAccessException`.
6. Chạy ví dụ **Java 17+, Spring JDBC 6.2 và H2** để kiểm tra được từng trường hợp bằng kết quả xác định.
7. Thiết kế repository phản ánh rõ nghĩa nghiệp vụ, bảo vệ tính duy nhất bằng ràng buộc dữ liệu và tránh các lỗi hiệu năng/bảo mật thường gặp.

**Phạm vi:** Tập trung vào bộ ba `single()`, `optional()`, `list()` của **Spring Framework `JdbcClient`**. Không nhầm chúng với các phương thức `Optional`/`List` trong Java Collections hay API repository của Spring Data.

## 1. JdbcClient đứng ở đâu trong Spring JDBC?

`JdbcClient` được giới thiệu từ **Spring Framework 6.1**. Nó cung cấp API dạng fluent cho các tác vụ JDBC phổ biến, thống nhất cách gọi positional parameters (`?`) và named parameters (`:id`). Bên dưới, `JdbcClient` tận dụng `JdbcTemplate` và `NamedParameterJdbcTemplate`; nó **không phải ORM** và không thay thế mapping entity/lazy-loading của JPA.

Một chuỗi gọi thông dụng:

```java
Customer customer = client.sql("""
        SELECT id, email, nickname
        FROM customers
        WHERE id = :id
        """)
    .param("id", 42L)
    .query(CUSTOMER_MAPPER)
    .single();
```

Đây là **đoạn trích minh họa**, giả định `client`, kiểu `Customer` và `CUSTOMER_MAPPER` tồn tại, cũng như bảng `customers`. Phần 8 cung cấp chương trình Java đầy đủ.

Giải thích theo thứ tự:

1. `sql(...)` xác định cấu trúc câu truy vấn.
2. `param("id", 42L)` bind giá trị 42 vào tham số có tên `:id`; không nối dữ liệu vào chuỗi SQL.
3. `query(CUSTOMER_MAPPER)` chỉ định ánh xạ một hàng `ResultSet` thành một `Customer`.
4. `single()` thực thi/giải quyết truy vấn và yêu cầu một kết quả hợp lệ theo hợp đồng.

Bản thân `query(RowMapper<T>)` trả về một **`JdbcClient.MappedQuerySpec<T>`** để bạn chọn cách giải quyết. Đừng nghĩ rằng gọi `query(mapper)` đã trả ngay một `List<Customer>` như `JdbcTemplate.query(...)`; bước kết thúc bằng `list()`, `single()` hoặc `optional()` là điểm khác biệt của API fluent.

`JdbcClient.create(dataSource)` tạo client từ nguồn JDBC; cũng có `JdbcClient.create(jdbcTemplate)` để dùng lại cấu hình template hiện có. Trong ứng dụng Spring, `JdbcClient` có thể được khai báo thành bean rồi tiêm vào repository bằng constructor.

## 2. Bảng quyết định: 0, 1 và nhiều kết quả

Giả định `query(RowMapper<T>)` ánh xạ mỗi hàng thành một đối tượng **không null**:

| Số dòng SQL | `list()` | `optional()` | `single()` |
| --- | --- | --- | --- |
| 0 | `List<T>` rỗng | `Optional.empty()` | Ném `EmptyResultDataAccessException` |
| 1 | Danh sách có 1 phần tử | `Optional.of(value)` | Trả một `T` |
| 2 trở lên | Danh sách có N phần tử | Ném `IncorrectResultSizeDataAccessException` | Ném `IncorrectResultSizeDataAccessException` |

Có hai điểm người mới học cần chú ý:

- **`optional()` không phải “lấy một dòng nếu có, còn nhiều dòng thì lấy tùy ý”.** Nó cũng yêu cầu **tối đa 1 dòng**. Nếu query thực sự trả hai hàng, `optional()` ném ngoại lệ.
- **`single()` không phải “trả object hoặc null”.** Khi không có dòng, nó ném ngoại lệ. Đặc biệt với Spring Framework **6.2**, một hàng được mapper trả **null** cũng không được chấp nhận bởi `single()`.

Trong bảng này, “số dòng SQL” chính xác hơn là “số phần tử mà ánh xạ truy vấn thu được”; với `RowMapper` thông thường, mỗi dòng tạo một phần tử. `list()` giữ thứ tự dòng do DB trả về, nhưng **muốn thứ tự ổn định, SQL phải có `ORDER BY`**.

### 2.1. Quy tắc chọn nhanh

| Câu hỏi nghiệp vụ | Lựa chọn thường đúng |
| --- | --- |
| Tìm khách hàng theo ID và khách hàng **bắt buộc** tồn tại ở bước này | `single()` |
| Tìm khách hàng theo ID nhưng “không tìm thấy” là trạng thái bình thường | `optional()` |
| Tìm toàn bộ khách hàng theo từ khóa, có thể không ai phù hợp | `list()` |
| Tìm toàn bộ đơn hàng của tài khoản, 0..N đơn | `list()` |
| Đếm đơn hàng bằng `SELECT COUNT(*)` không có `GROUP BY` | `query(Long.class).single()` |
| Tìm theo email duy nhất nhưng có thể chưa đăng ký | `optional()`, kèm ràng buộc UNIQUE ở DB |
| Tìm theo trạng thái OPEN (thường nhiều bản ghi) | `list()`, không dùng `single()` |
| Cần biết trang kết quả còn dòng tiếp theo hay không | `list()` cùng `LIMIT`/cách lấy `size+1` phù hợp |
| Muốn kiểm tra dữ liệu sai vì có 2 bản ghi với khóa lẽ ra duy nhất | `single()/optional()` báo lỗi, nhưng cần **UNIQUE constraint** để chặn sai từ gốc |

Chọn phương thức theo **ý nghĩa và invariant** của use case, không theo dự đoán “dữ liệu thử nghiệm hiện đang có 1 dòng”.

## 3. single(): yêu cầu một kết quả bắt buộc

### 3.1. Ví dụ tìm khách hàng theo ID

```java
Customer found = client.sql("""
        SELECT id, email, nickname
        FROM customers
        WHERE id = :id
        """)
    .param("id", 2L)
    .query(CUSTOMER_MAPPER)
    .single();
```

Trong đoạn này:

- `id` là khóa chính, nên database bảo đảm **tối đa một dòng**.
- `single()` bổ sung kỳ vọng rằng **phải có một dòng**.
- Nếu ID 2 tồn tại và mapper trả đối tượng `Customer`, biến `found` chứa đối tượng đó.
- Nếu ID không tồn tại, `single()` ném `EmptyResultDataAccessException`.

Hai điều kiện “tối đa một” và “ít nhất một” đến từ hai nơi khác nhau: **primary key** bảo vệ tính duy nhất, còn **`single()`** thực thi hợp đồng repository khi đọc.

### 3.2. Trường hợp thiếu dòng

```java
try {
    Customer required = client.sql(
            "SELECT id, email, nickname FROM customers WHERE id = :id")
        .param("id", 999L)
        .query(CUSTOMER_MAPPER)
        .single();
} catch (EmptyResultDataAccessException ex) {
    // ID 999 không có row trong tập kết quả.
    // Quyết định chuyển thành lỗi domain / HTTP 404 tùy ngữ cảnh.
}
```

Đoạn trích không độc lập; cần import `org.springframework.dao.EmptyResultDataAccessException` và các biến của repository. Lưu ý: `EmptyResultDataAccessException` là subtype của `IncorrectResultSizeDataAccessException`; nếu catch cả hai, catch trường hợp cụ thể trước.

Một repository có API `requireById(id)` hoặc `getRequired(id)` là nơi thích hợp cho `single()`. Nếu người dùng nhập một ID tùy ý và đối tượng có thể chưa từng tồn tại, `optional()` thường phản ánh nghiệp vụ tốt hơn.

### 3.3. Trường hợp có hai dòng

Giả sử query:

```sql
SELECT id, email, nickname
FROM customers
WHERE nickname IS NOT NULL;
```

có hai khách hàng với nickname không null. Gọi `single()` ném `IncorrectResultSizeDataAccessException` vì expected size = 1, actual size = 2. Đây **không phải** SQL syntax error; đó là kết quả hợp lệ về SQL nhưng không đáp ứng hợp đồng số lượng.

**Đừng “sửa” bằng `LIMIT 1` một cách tùy tiện.** Nếu nghiệp vụ cần tính duy nhất, `LIMIT 1` chỉ che giấu dòng trùng và có thể khiến ứng dụng chọn một kết quả không xác định. Cần xem filter/ràng buộc database, hoặc dùng `list()` nếu thực chất có thể có nhiều khách hàng.

### 3.4. Một kết quả phải là non-null từ Spring Framework 6.2

Một chi tiết dễ bỏ sót: `single()` của `JdbcClient.MappedQuerySpec<T>` trong **Spring Framework 6.2** sử dụng quy tắc required **non-null** result. Nếu truy vấn SQL trả **đúng một dòng**, nhưng mapper trả `null` (ví dụ đọc một cột `nickname` đang SQL NULL bằng `query(String.class)`), `single()` ném **`TypeMismatchDataAccessException`**.

Ví dụ minh họa:

```java
String nickname = client.sql(
        "SELECT nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query(String.class)
    .single();
```

Nếu khách hàng ID 2 tồn tại nhưng nickname là SQL NULL, kết quả `String` được map thành `null`; trong Spring 6.2, `single()` **không được trả null** và sẽ báo ngoại lệ. Điều này **khác** `JdbcTemplate.queryForObject(...)`, một số overload của nó có thể trả `null` cho SQL NULL ở một hàng hợp lệ.

Không nên mặc định hành vi này cho mọi phiên bản Spring cũ: Spring Framework 6.2 thực thi nghiêm ngặt hơn yêu cầu non-null được thiết kế ban đầu. Với code cũ dựa vào `single()` trả null, cần rà soát khi nâng cấp.

### 3.5. Khi nào single() rất phù hợp?

- Truy vấn bằng primary key hoặc unique key và nghiệp vụ đòi hỏi record phải tồn tại.
- Aggregate scalar `SELECT COUNT(*) ...` không có `GROUP BY`: luôn có **một dòng**, kể cả count 0.
- Một phép tính SQL được thiết kế chắc chắn trả một giá trị scalar **không NULL**, có invariant rõ ràng.
- Luồng nghiệp vụ đã xác minh ID và quy định việc record biến mất là lỗi cần báo.

Dù dùng `single()`, dữ liệu vẫn có thể thay đổi bởi transaction khác giữa các bước. Nếu cần bảo đảm nhất quán cập nhật, phải áp dụng transaction/locking hoặc optimistic locking tương ứng. `single()` là kiểm tra kết quả truy vấn, **không phải cơ chế khóa giao dịch**.

## 4. optional(): có thể không có, nhưng không được có hai

### 4.1. Tìm theo ID có thể vắng mặt

```java
Optional<Customer> maybe = client.sql(
        "SELECT id, email, nickname FROM customers WHERE id = :id")
    .param("id", 999L)
    .query(CUSTOMER_MAPPER)
    .optional();

if (maybe.isPresent()) {
    System.out.println(maybe.get().email());
} else {
    System.out.println("Không tìm thấy");
}
```

Đây là đoạn trích, giả định có `client`, `Customer`, `CUSTOMER_MAPPER` và import `java.util.Optional`.

Với 0 dòng: `Optional.empty()`. Với 1 dòng và mapper tạo một `Customer` không null: `Optional.of(customer)`. Với nhiều dòng: vẫn ném `IncorrectResultSizeDataAccessException`. Không có đường nhánh hợp lệ để `optional()` lặng lẽ lấy dòng đầu của kết quả nhiều dòng.

Trong repository, có thể trả `Optional<Customer> findById(long id)` cho service. Service quyết định trường hợp `empty` là 404, bỏ qua thao tác, mời đăng ký, v.v. Đừng ném lỗi quá sớm nếu vắng mặt là trạng thái được phép.

### 4.2. optional() và SQL NULL: một sắc thái rất quan trọng

Xem hai tình huống khác nhau:

- **A:** SQL không trả dòng nào.
- **B:** SQL trả đúng một dòng có **cột nickname = NULL**, và mapper scalar trả Java `null`.

Với kiểu ánh xạ scalar qua `query(String.class).optional()`, cả hai có thể cho **`Optional.empty()`**. Lý do: `Optional` của Java không chứa `null`; giá trị null được biểu diễn là không có giá trị. Vì vậy **`Optional.empty()` trong trường hợp scalar không luôn chứng minh SQL không có dòng**.

Ví dụ:

```java
Optional<String> nickname = client.sql(
        "SELECT nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query(String.class)
    .optional();
```

Nếu ID 2 tồn tại nhưng cột nickname là SQL NULL, `nickname.isEmpty()` trả true. Hành vi tương tự có thể xảy ra khi không tồn tại ID 2.

**Cách giữ được ranh giới row-vs-column:** Ánh xạ cả hàng sang một đối tượng **không null**, và cho phép thuộc tính bên trong đối tượng nullable:

```java
record Customer(long id, String email, String nickname) {}

Optional<Customer> customer = client.sql(
        "SELECT id, email, nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query((rs, rowNum) -> new Customer(
            rs.getLong("id"),
            rs.getString("email"),
            rs.getString("nickname")))
    .optional();
```

Khi row tồn tại, mapper luôn tạo đối tượng `Customer`, dù `nickname() == null`; do đó `customer.isPresent()` là true. Nếu thật sự không có row, `Optional.empty()`. Đây là cách phù hợp khi nghiệp vụ cần phân biệt **entity tồn tại** và **một thuộc tính của entity đang thiếu**.

Nếu nullable scalar là trường hợp quan trọng, có thể tạo wrapper record `NullableValue<T>` hoặc một record domain phù hợp để biểu diễn row tồn tại cùng value null, thay vì dựa vào `Optional<String>`.

### 4.3. Optional không phải lệnh bắt mọi lỗi

`optional()` không tự nuốt lỗi:

- 2+ dòng → `IncorrectResultSizeDataAccessException`.
- SQL sai, thiếu quyền, lỗi constraint, driver/connection failure → subtype phù hợp của `DataAccessException`.
- Mapper ném exception vì cột không tồn tại hoặc kiểu dữ liệu không phù hợp → vẫn có lỗi.

Do đó đừng wrap toàn bộ lời gọi vào `catch (DataAccessException ex) { return Optional.empty(); }`. Nó làm mất khả năng phân biệt dữ liệu không tồn tại với hỏng database và có thể che sự cố bảo mật/đồng bộ.

### 4.4. Optional trong service

Repository chỉ cần biểu đạt dữ liệu:

```java
public Optional<Customer> findByEmail(String email) {
    return client.sql("""
            SELECT id, email, nickname
            FROM customers
            WHERE email = :email
            """)
        .param("email", email)
        .query(CUSTOMER_MAPPER)
        .optional();
}
```

Đây là trích đoạn của một repository có `client` và `CUSTOMER_MAPPER`; không phải file độc lập. Để hợp đồng “0 hoặc 1 dòng” có ý nghĩa, nên có ràng buộc `UNIQUE` cho email và quy tắc normalization/collation rõ ràng. Nếu database cho phép nhiều email trùng và query trả hai dòng, `optional()` báo lỗi — đó là tín hiệu bất nhất cần sửa.

Đừng dùng `Optional` làm trường dữ liệu nullable của entity một cách máy móc; cân nhắc ranh giới service/API, serialization và model của dự án.

## 5. list(): tập kết quả 0..N dòng

### 5.1. Lấy danh sách và xử lý kết quả rỗng

```java
List<Customer> customers = client.sql("""
        SELECT id, email, nickname
        FROM customers
        ORDER BY id
        """)
    .query(CUSTOMER_MAPPER)
    .list();
```

- 0 dòng → một `List` rỗng, không phải ngoại lệ do thiếu dòng.
- 1 dòng → danh sách có 1 phần tử.
- N dòng → danh sách có N phần tử.
- `list()` không tự bỏ bản ghi trùng nếu câu SQL trả hai hàng trùng hoặc mapper tạo hai object bằng nhau.
- Danh sách giữ thứ tự kết quả SQL thực tế; muốn thứ tự dự đoán được, cần `ORDER BY`.

Với màn hình search, API đọc nhiều bản ghi hoặc một nhóm chi tiết của tài khoản, `list()` là lựa chọn phổ biến. Nếu không có kết quả, trả list rỗng thường đơn giản hơn việc ném not-found cho cả một thao tác tìm kiếm.

### 5.2. list() không kiểm tra hợp đồng “chính xác một”

Có thể dùng `list()` để tìm theo ID:

```java
List<Customer> rows = client.sql(
        "SELECT id, email, nickname FROM customers WHERE id = :id")
    .param("id", 2L)
    .query(CUSTOMER_MAPPER)
    .list();
```

Nhưng nếu bạn viết `rows.get(0)` ngay sau đó, query không trả dòng sẽ gây `IndexOutOfBoundsException` ở Java, không diễn đạt đúng lỗi dữ liệu. Nếu viết `rows.stream().findFirst()`, bạn lại có thể bỏ qua trường hợp nhiều dòng mà nghiệp vụ cần coi là lỗi.

Khi use case yêu cầu 0/1 hoặc đúng 1, dùng `optional()` hoặc `single()` để hợp đồng hiển thị trực tiếp trong code.

### 5.3. SQL trả nhiều dòng vẫn nên giới hạn khi cần

`list()` trả **danh sách đã được giải quyết** (*pre-resolved/detached list*) và có thể tiêu thụ bộ nhớ lớn. Nó không tự phân trang. Ví dụ:

```java
List<Customer> page = client.sql("""
        SELECT id, email, nickname
        FROM customers
        ORDER BY id
        LIMIT :size OFFSET :offset
        """)
    .param("size", 20)
    .param("offset", 40L)
    .query(CUSTOMER_MAPPER)
    .list();
```

Đây là trích đoạn phụ thuộc SQL dialect hỗ trợ `LIMIT/OFFSET`. Size/offset phải được validate, tính toán an toàn và SQL phải có sort tường minh. Nếu bảng rất lớn, cân nhắc keyset pagination hoặc cơ chế stream có đóng tài nguyên đúng. `JdbcClient.MappedQuerySpec.stream()` cung cấp stream cần đóng sau khi dùng; `list()` không phải stream lazy.

### 5.4. RowMapper có thể trả null: list không tạo hợp đồng non-null

`list()` trả các giá trị do mapper tạo. Nếu một `RowMapper` có chủ đích trả null ở một số dòng (ví dụ đọc cột nullable), list có thể có các phần tử null, tùy API mapping. Điều đó rất khác với một danh sách các entity không null nhưng có nullable fields.

Hãy lựa chọn mapper sao cho hợp đồng trả về rõ ràng:

- Truy vấn **entity** → tạo object không null cho mỗi row.
- Truy vấn **nullable scalar** → xét model biểu diễn cột NULL, wrapper record hoặc API phù hợp.
- Truy vấn **không-null scalar** → bảo đảm SQL column/expression và mapping không null.

Đừng mặc định `list().size()` là số dòng nghiệp vụ duy nhất khi JOIN tạo duplicate; sửa SQL `DISTINCT`/`EXISTS`/aggregation theo bản chất use case.

## 6. single(), optional(), list() khác với API cùng tên khác ra sao?

### 6.1. Không nhầm JdbcClient với JdbcTemplate

| Mục đích | Spring `JdbcClient` | Spring `JdbcTemplate` |
| --- | --- | --- |
| Query nhiều row | `.query(mapper).list()` | `.query(sql, mapper, args...)` |
| Query đúng một mapped object | `.query(mapper).single()` | `.queryForObject(sql, mapper, args...)` |
| Query 0/1 mapped object | `.query(mapper).optional()` | Có thể `query` 0/1 rồi chuyển `Optional` hoặc bắt riêng ngoại lệ theo hợp đồng |
| Scalar một cột | `.query(Long.class).single()` | `.queryForObject(sql, Long.class, args...)` |
| Ghi dữ liệu | `.sql(sql).param(...).update()` | `.update(sql, args...)` |

`JdbcClient` là facade để dùng các API JDBC cốt lõi trong một chuỗi fluent. Nó **không khiến SQL trả kết quả khác**; khác biệt nằm ở hợp đồng giải quyết/biểu diễn số dòng.

Điểm cần chú ý về nullable scalar: `JdbcTemplate.queryForObject(...)` có thể trả Java null khi cột SQL NULL, trong khi `JdbcClient.query(Class<T>).single()` của Spring Framework 6.2 yêu cầu **kết quả không null**. Đọc contract của API cụ thể, không suy luận chỉ từ tên “single”.

### 6.2. Không nhầm với Spring Data Repository

`CrudRepository.findById(id)` và `Optional` của Spring Data JDBC/JPA là các API repository khác, với quy trình mapping/persistence khác. Bài này nói về **Spring Framework `org.springframework.jdbc.core.simple.JdbcClient`**, không phải các phương thức tự sinh từ `JpaRepository`/`CrudRepository`.

Cùng cách dùng từ “optional” không đảm bảo giống nhau về SQL được tạo, mapping null hoặc transaction management.

### 6.3. Các lựa chọn khác của JdbcClient

Ngoài bộ ba đang học, `MappedQuerySpec` còn có `set()` (tập giữ thứ tự theo contract) và `stream()` (luồng được giải quyết lười, cần đóng tài nguyên). Với `query()` không truyền mapper, `ResultQuerySpec` có các phương thức như `listOfRows()`, `singleRow()`, `singleColumn()`, `singleValue()` hoặc `optionalValue()` (các tên/capabilities có thể khác theo version). Chúng không đồng nhất với `MappedQuerySpec<T>.list()/single()/optional()` và có kiểu trả về khác.

Khi chỉ cần đọc entity/scalar thông thường, `query(RowMapper<T>)` hoặc `query(Class<T>)` rồi chọn bộ ba ở trên là hướng học tập trực tiếp nhất.

## 7. Các tình huống biên quan trọng

### 7.1. COUNT(*) trả một dòng ngay cả khi không có match

```java
Long count = client.sql("""
        SELECT COUNT(*)
        FROM customers
        WHERE id > :id
        """)
    .param("id", 999L)
    .query(Long.class)
    .single();
```

Không có khách hàng id lớn hơn 999 → `COUNT(*)` (không có `GROUP BY`) trả **một dòng** với giá trị 0, nên `single()` trả 0. Nó không ném `EmptyResultDataAccessException`.

Ngược lại, một `SELECT email WHERE id = 999` trả **0 dòng**, nên `single()` ném ngoại lệ và `optional()` trả empty.

Với `COUNT(*) ... GROUP BY status`, có thể có **0 hoặc nhiều nhóm**; không được áp dụng quy tắc “luôn một dòng” cho mọi truy vấn aggregate. Chọn `list()` khi cần đọc nhiều nhóm.

### 7.2. LEFT JOIN có thể nhân số dòng

Giả sử một khách hàng có ba đơn hàng:

```sql
SELECT c.id, c.email
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = :id;
```

Dù `c.id` là primary key, JOIN 1–N có thể trả **ba dòng** cho cùng khách hàng. Nếu dùng `single()`/`optional()`, Spring ném lỗi số lượng. Không sửa bằng cách lấy dòng đầu một cách mù quáng; cân nhắc bỏ JOIN nếu không cần dữ liệu order, dùng `EXISTS`, truy vấn riêng hoặc `DISTINCT`/aggregation thích hợp.

Điều này cho thấy **cardinality của kết quả SQL** khác với tính duy nhất của entity gốc. Phải thiết kế câu query để một row tương ứng một kết quả nghiệp vụ cần ánh xạ.

### 7.3. Không dùng LIMIT 1 để giấu dữ liệu trùng

```sql
SELECT id, email, nickname
FROM customers
WHERE email = :email
LIMIT 1;
```

Câu trên có thể giúp query trả tối đa một dòng, nhưng nếu email bị trùng, lỗi vẫn tồn tại. Nếu yêu cầu chỉ một khách hàng cho một email, hãy tạo `UNIQUE` constraint/index phù hợp với quy tắc chuẩn hóa email và test dữ liệu.

Nếu nhu cầu là “lấy bản ghi mới nhất”, `ORDER BY created_at DESC, id DESC LIMIT 1` có thể là một hợp đồng **hợp lệ** vì use case thật sự chỉ cần một bản ghi. Khi tập dữ liệu không có dòng, `optional()` diễn đạt tốt hơn; khi bắt buộc phải có, `single()` phù hợp. Điều cốt lõi là **LIMIT 1 có chủ đích**, không phải biện pháp che duplicate ngoài ý muốn.

### 7.4. Phân biệt missing, SQL NULL và lỗi database

Có ba nhóm trạng thái rất khác nhau:

1. **Không có row**: `optional()` → empty; `single()` → `EmptyResultDataAccessException`.
2. **Có row, một cột nullable đang NULL**: mapper trả object có field null → row vẫn tồn tại; mapper scalar trả null → `optional()` có thể empty, `single()` Spring 6.2 báo `TypeMismatchDataAccessException`.
3. **Không thể thực thi SQL**: lỗi syntax, connection, quyền, column mapping... → subtype của `DataAccessException` hoặc exception tương ứng; không được biến thành “không có row” một cách im lặng.

Đây là lý do API repository nên chọn kiểu trả về phù hợp bản chất dữ liệu, và code không nên catch tất cả `DataAccessException` rồi trả `Optional.empty()`.

## 8. Ví dụ chạy được: Java 17, Spring JdbcClient 6.2 và H2

Chương trình dưới đây dùng database H2 có **ba khách hàng**, trong đó một người có nickname SQL NULL. Nó kiểm tra cả:

- `list()` với 0 hoặc 3 dòng;
- `single()` với 1, 0, >1 dòng;
- `optional()` với 1, 0, >1 dòng;
- `query(String.class).optional()` khi một cột SQL NULL;
- `query(String.class).single()` khi một cột SQL NULL trong Spring 6.2;
- `COUNT(*)` bằng 0 mà vẫn có một dòng kết quả.

Chương trình chạy độc lập bằng **Java 17+**, Spring Framework **6.2.12**, H2 **2.3.232** và Gradle. Không cần Spring Boot hay database server khác.

### 8.1. Tạo cấu trúc dự án

```text
jdbc-client-cardinality/
├── build.gradle
└── src/main/java/example/JdbcClientCardinalityDemo.java
```

### 8.2. Nội dung build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.JdbcClientCardinalityDemo'
}
```

`spring-jdbc` chứa `JdbcClient`, `JdbcTemplate` và `DriverManagerDataSource`; Spring tự kéo các transitive dependencies tương ứng. H2 chạy trong bộ nhớ và được nạp qua JDBC driver khi thực thi.

### 8.3. Source Java hoàn chỉnh

Tạo `src/main/java/example/JdbcClientCardinalityDemo.java`:

```java
package example;

import java.util.List;
import java.util.Optional;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.dao.TypeMismatchDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcClientCardinalityDemo {

    record Customer(long id, String email, String nickname) {}

    private static final String BASE_SELECT =
            "SELECT id, email, nickname FROM customers";

    private static final RowMapper<Customer> CUSTOMER_MAPPER =
            (rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("nickname"));

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:cardinality_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate setup = new JdbcTemplate(ds);
        JdbcClient client = JdbcClient.create(ds);

        setup.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    nickname VARCHAR(100)
                )
                """);

        // SQL tĩnh tạo fixture: đây không phải SQL ghép từ user input.
        setup.execute("""
                INSERT INTO customers (id, email, nickname) VALUES
                    (1, 'ana@example.test', 'Ann'),
                    (2, 'bao@example.test', NULL),
                    (3, 'chi@example.test', 'Chi')
                """);

        // list(): truy vấn có ba dòng.
        List<Customer> all = client.sql(BASE_SELECT + " ORDER BY id")
                .query(CUSTOMER_MAPPER)
                .list();
        System.out.println("listSize=" + all.size());
        System.out.println(
                "listIds=" + all.stream().map(Customer::id).toList());

        // list(): không có dòng vẫn trả danh sách rỗng.
        List<Customer> noRows = client.sql(
                BASE_SELECT + " WHERE id > :id ORDER BY id")
                .param("id", 99L)
                .query(CUSTOMER_MAPPER)
                .list();
        System.out.println("listEmpty=" + noRows.isEmpty());

        // single(): đúng một row, mapper tạo đối tượng không null.
        Customer required = client.sql(
                BASE_SELECT + " WHERE id = :id")
                .param("id", 2L)
                .query(CUSTOMER_MAPPER)
                .single();
        System.out.println("single=" + required);

        // optional(): 0 row khác với 1 row.
        Optional<Customer> present = client.sql(
                BASE_SELECT + " WHERE id = :id")
                .param("id", 1L)
                .query(CUSTOMER_MAPPER)
                .optional();
        System.out.println(
                "optionalPresent=" +
                present.map(Customer::email).orElse("<none>"));

        Optional<Customer> missing = client.sql(
                BASE_SELECT + " WHERE id = :id")
                .param("id", 99L)
                .query(CUSTOMER_MAPPER)
                .optional();
        System.out.println("optionalMissing=" + missing.isEmpty());

        // single(): không có row là lỗi cardinality.
        try {
            client.sql(BASE_SELECT + " WHERE id = :id")
                    .param("id", 99L)
                    .query(CUSTOMER_MAPPER)
                    .single();
        } catch (EmptyResultDataAccessException ex) {
            System.out.println(
                    "singleMissing=EmptyResultDataAccessException");
        }

        // Cả optional() lẫn single() đều từ chối kết quả 2+ row.
        try {
            client.sql(BASE_SELECT + " WHERE id >= :id ORDER BY id")
                    .param("id", 2L)
                    .query(CUSTOMER_MAPPER)
                    .optional();
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println(
                    "optionalMultiple=IncorrectResultSizeDataAccessException");
        }

        try {
            client.sql(BASE_SELECT + " WHERE id >= :id ORDER BY id")
                    .param("id", 2L)
                    .query(CUSTOMER_MAPPER)
                    .single();
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println(
                    "singleMultiple=IncorrectResultSizeDataAccessException");
        }

        // Một row có nickname SQL NULL: scalar optional là empty.
        Optional<String> nullableNickname = client.sql(
                "SELECT nickname FROM customers WHERE id = :id")
                .param("id", 2L)
                .query(String.class)
                .optional();
        System.out.println(
                "nullScalarOptionalEmpty=" + nullableNickname.isEmpty());

        // Với Spring 6.2, scalar single() không chấp nhận null.
        try {
            client.sql(
                    "SELECT nickname FROM customers WHERE id = :id")
                    .param("id", 2L)
                    .query(String.class)
                    .single();
        } catch (TypeMismatchDataAccessException ex) {
            System.out.println(
                    "nullScalarSingle=TypeMismatchDataAccessException");
        }

        // COUNT(*) không GROUP BY vẫn trả một row chứa 0.
        Long countZero = client.sql("""
                SELECT COUNT(*) FROM customers WHERE id > :id
                """)
                .param("id", 99L)
                .query(Long.class)
                .single();
        System.out.println("countZero=" + countZero);
    }
}
```

Chương trình cố ý dùng `JdbcTemplate` cho DDL/fixture, sau đó dùng `JdbcClient` để minh họa kết quả truy vấn; cả hai kết nối cùng `DataSource` H2.

`Customer` là Java record; `nickname` có thể null nhưng `Customer` **vẫn là một đối tượng không null**. `CUSTOMER_MAPPER` tạo một `Customer` cho mỗi row của `ResultSet`. Không gọi `rs.next()` trong mapper, vì Spring đã chuyển con trỏ đến dòng hiện tại trước khi gọi `RowMapper`.

`DriverManagerDataSource` thích hợp cho demo, nhưng không phải connection pool dành cho production. `DB_CLOSE_DELAY=-1` giữ H2 memory database tồn tại qua nhiều connection trong cùng JVM; dữ liệu không tồn tại sau khi tiến trình kết thúc.

### 8.4. Lệnh chạy và đầu ra

Từ thư mục có `build.gradle`, chạy:

```bash
gradle run
```

Nếu có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). Gradle có thể in thêm log build; các dòng do chương trình **`System.out.println`** tạo ra, theo thứ tự, là:

```text
listSize=3
listIds=[1, 2, 3]
listEmpty=true
single=Customer[id=2, email=bao@example.test, nickname=null]
optionalPresent=ana@example.test
optionalMissing=true
singleMissing=EmptyResultDataAccessException
optionalMultiple=IncorrectResultSizeDataAccessException
singleMultiple=IncorrectResultSizeDataAccessException
nullScalarOptionalEmpty=true
nullScalarSingle=TypeMismatchDataAccessException
countZero=0
```

Diễn giải từng bước:

1. Ba dòng đã insert có ID 1, 2, 3. `ORDER BY id` bảo đảm `listIds=[1, 2, 3]`.
2. `WHERE id > 99` không khớp; `list()` vẫn trả empty list.
3. `single()` với `id=2` trả object `Customer` chứa nickname null. Hợp đồng **non-null mapped object** vẫn được đáp ứng.
4. `optional()` với `id=1` chứa object có email Ana; với `id=99` trả empty.
5. `single()` với `id=99` báo `EmptyResultDataAccessException`.
6. `WHERE id >= 2` có hai dòng 2 và 3; `optional()` và `single()` đều từ chối, ném `IncorrectResultSizeDataAccessException`.
7. `query(String.class)` đọc **một cột nickname** của ID 2, chính cột này SQL NULL. `optional()` trả empty nên `nullScalarOptionalEmpty=true`.
8. Cũng với một scalar NULL, `single()` trong Spring 6.2 ném `TypeMismatchDataAccessException`.
9. `COUNT(*)` khi không có match trả một dòng 0, nên `single()` nhận `Long 0` bình thường.

**Kiểm chứng quan trọng:** Không diễn giải dòng `nullScalarOptionalEmpty=true` là “khách hàng ID 2 không tồn tại”. ID 2 tồn tại, chỉ có thuộc tính nickname của họ là NULL.

### 8.5. Một số bài tập sửa chương trình

- Thay `id=99` trong lời gọi `optional()` bằng `id=3`; dự đoán email được trả.
- Sửa truy vấn `WHERE id >= 2` thành `WHERE id > 2`; khi ấy chỉ có một dòng ID 3, nên `single()` và `optional()` đều hợp lệ.
- Đổi query scalar từ `nickname` sang `email` cho ID 2; `single()` sẽ trả `bao@example.test` vì cột email `NOT NULL`.
- Thêm một khách hàng có nickname NULL, rồi dùng `.query(CUSTOMER_MAPPER).list()`; danh sách có thêm object không null với field nullable.
- Tạo một query `GROUP BY nickname` và xem kết quả có 0, 1 hay nhiều nhóm; chọn `list()` nếu muốn đọc mọi nhóm.

Không cần sửa phần khai báo `@Bean` vì chương trình demo này tạo client thủ công. Trong ứng dụng Spring production, bạn có thể khai báo `JdbcClient` bằng configuration để tiêm vào repository.

## 9. Thiết kế repository với hợp đồng rõ nghĩa

### 9.1. API nên nói rõ “có bắt buộc tồn tại không”

Một repository hợp lý:

```java
public final class CustomerRepository {
    private final JdbcClient jdbc;

    public CustomerRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Customer requireById(long id) {
        return jdbc.sql("""
                SELECT id, email, nickname
                FROM customers
                WHERE id = :id
                """)
            .param("id", id)
            .query(CUSTOMER_MAPPER)
            .single();
    }

    public Optional<Customer> findById(long id) {
        return jdbc.sql("""
                SELECT id, email, nickname
                FROM customers
                WHERE id = :id
                """)
            .param("id", id)
            .query(CUSTOMER_MAPPER)
            .optional();
    }

    public List<Customer> findByEmailPrefix(String prefix) {
        return jdbc.sql("""
                SELECT id, email, nickname
                FROM customers
                WHERE email LIKE :pattern
                ORDER BY id
                """)
            .param("pattern", prefix + "%")
            .query(CUSTOMER_MAPPER)
            .list();
    }
}
```

Đây là **đoạn trích mang tính thiết kế**, không phải file Java biên dịch độc lập vì `Customer`/`CUSTOMER_MAPPER` và các import được định nghĩa ở nơi khác. Với `LIKE`, việc bind tránh SQL injection tại vị trí giá trị nhưng không tự escape các ký tự wildcard `%`, `_` trong prefix; nếu cần tìm prefix **literal**, hãy escape pattern phù hợp DBMS/`ESCAPE` clause.

Ở đây:

- `requireById` nói rõ thiếu record là lỗi.
- `findById` nói rõ thiếu record là trạng thái bình thường.
- `findByEmailPrefix` nói rõ có thể trả nhiều record; cần `ORDER BY` và phân trang khi dataset lớn.

Chú ý `Optional<Customer>` không đảm bảo không có data corruption — database uniqueness constraint mới là lớp bảo vệ gốc.

### 9.2. Chính sách ngoại lệ nên thuộc tầng nghiệp vụ

Service có thể chuyển `EmptyResultDataAccessException` thành `CustomerNotFound` hoặc HTTP 404 theo context. Nếu `CustomerRepository.findById` trả `Optional.empty()`, service có thể dùng `orElseThrow(...)` khi một use case riêng yêu cầu tồn tại.

Không nên đặt mọi hành vi vào chung một method rồi để controller đoán trạng thái theo `null`. Hãy dùng tên method/return type và exception có chủ đích, tránh làm mất tín hiệu lỗi DB.

### 9.3. Một truy vấn đúng cardinality còn phải đúng quyền truy cập

Ví dụ khi có nhiều tenant:

```java
Optional<Customer> candidate = jdbc.sql("""
        SELECT id, email, nickname
        FROM customers
        WHERE tenant_id = :tenantId AND id = :id
        """)
    .param("tenantId", verifiedTenantId)
    .param("id", customerId)
    .query(CUSTOMER_MAPPER)
    .optional();
```

Đây là đoạn trích với `verifiedTenantId` được hệ thống phân quyền xác định, và giả định bảng chứa cột `tenant_id`. Hệ thống phải xác minh người gọi được phép truy cập tenant đó; `optional()` chỉ kiểm tra **số dòng sau lọc** chứ không tự làm authorization. Đừng để `COUNT(*)` hoặc log lỗi tiết lộ thông tin tenant khác.

## 10. Những lỗi dễ gặp và cách xử lý

| Hiện tượng | Nguyên nhân/ý nghĩa có thể | Hướng xử lý |
| --- | --- | --- |
| `single()` không thấy dòng | 0 kết quả, ném `EmptyResultDataAccessException` | Chuyển thành domain not found hoặc chọn `optional()` nếu vắng mặt hợp lệ |
| `optional()` ném lỗi dù “tùy chọn” | SQL trả từ 2 dòng trở lên | Kiểm tra WHERE/JOIN/UNIQUE, không lấy dòng đầu vô điều kiện |
| `single()` ném `IncorrectResultSizeDataAccessException` | SQL trả 2+ dòng | Sửa query/invariant, hoặc chọn `list()` khi thật sự cần nhiều |
| `single()` ném `TypeMismatchDataAccessException` khi scalar | Một hàng trả SQL NULL trong Spring Framework 6.2 | Dùng wrapper row object hoặc thay đổi hợp đồng nullable |
| `optional()` scalar empty dù row tồn tại | Mapper của một cột nullable trả null | Dùng non-null row wrapper để phân biệt row và field |
| `list()` trả rỗng | SQL không có hàng thỏa điều kiện | Trả collection rỗng hoặc xử lý theo giao diện |
| `list()` trả quá nhiều | Query không có LIMIT/filter đủ hẹp | Phân trang/stream, tránh tải tất cả vào memory |
| `COUNT(*)` bằng 0 mà `single()` không lỗi | Aggregate không GROUP BY vẫn trả một dòng | Đây là hành vi đúng |
| `single()` lỗi với JOIN dù PK unique | JOIN 1–N nhân nhiều dòng | Thiết kế query trả đúng một entity, dùng EXISTS/tách query khi cần |
| Nối user input vào SQL thay vì bind | SQL injection hoặc sai escaping | Dùng `:name`/`?` và `param(...)` |
| Query không có ORDER BY nhưng list thay đổi thứ tự | DB không cam kết thứ tự nếu thiếu ORDER BY | Thêm sort tường minh, có khóa phụ duy nhất khi phân trang |
| Catch mọi `DataAccessException` rồi trả empty | Che lỗi DB/driver/query/permission | Chỉ xử lý tình huống lỗi có nghĩa nghiệp vụ |
| Đánh đồng JdbcClient với JPA repository | Hai framework khác tầng abstraction | Đọc đúng contract API và source code tương ứng |
| Test H2 chạy nhưng SQL production lỗi | SQL dialect/driver/schema khác | Integration test trên DBMS production |

## 11. Kiểm thử một hợp đồng cardinality

Đối với repository trả `single()` hoặc `optional()`, hãy tạo test cho ít nhất ba dữ liệu giả lập:

1. **0 row**: `single()` phải ném missing exception; `optional()` trả empty; `list()` rỗng.
2. **1 row**: cả ba trả kết quả tương ứng, nếu mapper không-null.
3. **2 rows**: `single()`/`optional()` phải báo lỗi; `list()` trả hai phần tử.

Sau đó thêm test **SQL NULL**:

- Một record có trường nullable null, ánh xạ entity/record **không null**; `optional()` vẫn phải present.
- Một truy vấn scalar nullable trả một `null`; `optional()` empty, `single()` (Spring 6.2) lỗi null result.
- Một truy vấn `COUNT(*)` không có `GROUP BY` với 0 bản ghi phù hợp; `single()` bằng 0.

Thêm kiểm tra **JOIN** và **unique constraint** cho các endpoint quan trọng: nếu query có thể nhân row, phải sửa ngay từ SQL hoặc thiết kế DTO phù hợp.

Một số test không nên phụ thuộc vào tên class con cụ thể của mọi SQLException do các JDBC driver khác nhau chuyển dịch; chỉ assert kiểu exception đúng ngữ nghĩa mà Spring công bố và dùng đúng phiên bản thư viện trong project.

## 12. Câu hỏi tự kiểm tra

1. Truy vấn có 0 dòng. `list()`, `optional()`, `single()` lần lượt cho kết quả gì?
2. Với đúng một dòng đã map thành một object `Customer`, ba phương thức trả kiểu gì?
3. `optional()` có “lấy dòng đầu” khi SQL trả hai dòng không?
4. Vì sao `single()` hợp với `requireById` còn `optional()` hợp với `findById`?
5. Một `LEFT JOIN` từ customers sang orders có thể khiến `single()` lỗi dù `customers.id` là PK bằng cách nào?
6. Khi nào `LIMIT 1` là hợp đồng hợp lệ và khi nào nó che lỗi duplicate?
7. Tại sao `SELECT COUNT(*)` không có `GROUP BY` và không có match vẫn không làm `single()` báo empty?
8. Trong Spring 6.2, nếu SQL trả một dòng nhưng `RowMapper` trả null, `single()` làm gì?
9. Nếu cột nickname NULL nhưng record `Customer` vẫn được tạo, `optional<Customer>` có present không?
10. Vì sao `query(String.class).optional()` empty **không chứng minh** query không có dòng?
11. `list()` có tự phân trang, loại trùng và đảm bảo thứ tự không?
12. Tại sao không nên catch toàn bộ `DataAccessException` để trả `Optional.empty()`?

**Ghi nhớ:** Với `JdbcClient`, **`list()` = 0..N**, **`optional()` = 0..1**, **`single()` = đúng 1 kết quả không-null** trong Spring Framework 6.2. Cardinality là hợp đồng của use case; dữ liệu SQL, mapper và kiểu trả về phải cùng tuân theo hợp đồng. Đặc biệt phải phân biệt **không có row** với **row có cột SQL NULL**.

### Tài liệu chính thức

- Spring Framework 6.2 — [JDBC Core: Unified JdbcClient Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html).
- Spring Framework 6.2 — [JdbcClient API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html).
- Spring Framework 6.2 — [JdbcClient.MappedQuerySpec API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html).
- Spring Framework 6.2 — [DataAccessUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/support/DataAccessUtils.html).
- Java SE 17 — [Optional API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).
