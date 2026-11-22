# Đọc kết quả dạng giá trị và mảng Object[]

Trong JPA, các truy vấn JPQL thường trả về entity, một thuộc tính, DTO projection hoặc một kiểu kết quả được khai báo rõ bằng `TypedQuery<T>`. Nhưng khi sử dụng **native SQL** thông qua `EntityManager.createNativeQuery(...)`, ứng dụng làm việc trực tiếp hơn với các cột do database/JDBC driver trả về. Nếu không khai báo mapping kết quả tường minh, một quy ước phổ biến là:

- **Chọn một cột:** mỗi hàng là một **giá trị scalar** như `String`, `Number`, `BigDecimal`, `Date`, `Timestamp` hoặc loại Java tương ứng do provider chuyển đổi.
- **Chọn nhiều cột:** mỗi hàng thường là một **`Object[]`**, các phần tử được sắp theo thứ tự cột trong danh sách `SELECT`.
- **Chọn entity và khai báo result mapping:** provider có thể trả entity hoặc kiểu DTO/mapping khác, không nhất thiết là `Object[]`.

Ví dụ:

```java
Query namesQuery = em.createNativeQuery(
    "SELECT title FROM books ORDER BY id"
);

List<?> names = namesQuery.getResultList();

Query rowsQuery = em.createNativeQuery(
    "SELECT id, title, price FROM books ORDER BY id"
);

List<?> rows = rowsQuery.getResultList();
```

Với `namesQuery`, mỗi phần tử thông thường là giá trị `title`. Với `rowsQuery`, mỗi phần tử thông thường là `Object[]` gồm ba cột `id`, `title`, `price`. Tuy nhiên, **kiểu Java cụ thể của mỗi cột và một số chi tiết hình dạng kết quả không được suy đoán tuyệt đối từ cú pháp SQL**. Chúng phụ thuộc mapping kết quả, JPA provider, JDBC driver, hệ quản trị database và kiểu SQL.

Bài học **“Đọc kết quả dạng giá trị và mảng Object[]”**, thuộc chương **Native SQL** trong chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào cách đọc dữ liệu một cách chính xác, an toàn và dễ bảo trì. Chúng ta sẽ so sánh scalar với `Object[]`, xử lý kiểu số/ngày/nullable, chuyển sang DTO, giới hạn các phép ép kiểu trực tiếp, dùng `@SqlResultSetMapping` khi cần mapping rõ, và kiểm thử trên database thật.

Các ví dụ sử dụng package `jakarta.persistence`. Với dự án JPA đời cũ, package tương ứng là `javax.persistence`.

## 1. Native SQL khác JPQL ở điểm nào?

JPQL thao tác với **entity model**:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b WHERE b.published = true",
    Book.class
).getResultList();
```

`Book` ở đây là tên entity, còn `published` là thuộc tính Java được ánh xạ.

Native SQL thao tác với **schema database**:

```java
Query query = em.createNativeQuery(
    "SELECT id, title, price FROM books WHERE published = true"
);

List<?> rows = query.getResultList();
```

Tên `books`, `id`, `title`, `price` và `published` là tên bảng/cột SQL thực tế. Query native được database hiểu theo dialect của nó.

| Tiêu chí | JPQL | Native SQL |
| --- | --- | --- |
| Tên trong truy vấn | Entity và thuộc tính ánh xạ | Bảng, cột, view, biểu thức SQL |
| Phụ thuộc dialect | JPA provider biên dịch | SQL của database cụ thể |
| Kết quả entity | Thường tự nhiên khi `SELECT b` | Cần chọn cột và mapping thích hợp |
| Kết quả một field | Kiểu field Java của mapping | Kiểu được provider/JDBC trả về |
| Kết quả nhiều field | `Object[]`, Tuple, DTO projection tùy query | Thường `Object[]` nếu không mapping tường minh |
| Type safety | `TypedQuery<T>` thường tiện hơn | `Query` không kiểu trong API native thông dụng |
| SQL nâng cao | Giới hạn bởi JPQL/Criteria | Dùng được các khả năng riêng của database |
| Rủi ro chuyển kiểu | Gắn với entity mapping | Cần chú ý kiểu JDBC/driver/dialect |

Native SQL hữu ích với các truy vấn sử dụng window functions, CTE, view, JSON operators, vendor functions hoặc biểu thức SQL không thuận tiện trong JPQL. Nhưng đổi lại, ứng dụng phải chịu trách nhiệm nhiều hơn về **định dạng kết quả và chuyển đổi dữ liệu**.

## 2. Schema và dữ liệu minh họa

Giả sử một bảng lưu sách:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL,
    category VARCHAR(60) NOT NULL,
    published BOOLEAN NOT NULL,
    published_at TIMESTAMP NULL
);
```

Dữ liệu:

| id | title | price | category | published | published_at |
| ---: | --- | ---: | --- | --- | --- |
| 101 | Java cơ bản | 150000.00 | JAVA | true | 2025-03-01 09:00:00 |
| 102 | JPA thực hành | 275000.50 | JAVA | true | 2025-04-10 14:30:00 |
| 103 | SQL nâng cao | 320000.00 | DATABASE | false | null |

Cú pháp `BOOLEAN` và `TIMESTAMP` cũng như cách sinh ID thay đổi theo database. Trong ví dụ, chỉ cần quan tâm bảng có những cột và kiểu tương ứng.

Một entity có thể tồn tại để JPA quản lý bảng:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false)
    private boolean published;

    private LocalDateTime publishedAt;

    protected Book() {}

    public Long getId() { return id; }

    public String getTitle() { return title; }

    public BigDecimal getPrice() { return price; }
}
```

Lưu ý entity có thể cần khai báo `@Column(name = "published_at")` nếu naming strategy không tự chuyển `publishedAt` thành `published_at`; ví dụ chỉ minh họa mối quan hệ giữa bảng và entity.

**Khi native query trả scalar hoặc Object[], không có nghĩa mỗi kết quả trở thành Book managed entity.** Chỉ query mapping entity phù hợp mới cung cấp các object entity theo vòng đời JPA.

## 3. Tạo native query bằng `EntityManager`

Lệnh phổ biến:

```java
Query query = em.createNativeQuery(
    "SELECT title FROM books WHERE published = true"
);
```

`createNativeQuery(String sql)` thường trả `Query` chứ không phải `TypedQuery<String>` như JPQL typed query. Vì vậy khi đọc kết quả, hãy cân nhắc dùng `List<?>` để không giả định sai kiểu khi chưa biết mapping cụ thể.

```java
List<?> results = query.getResultList();
```

Đối tượng `Query` hỗ trợ:

- `setParameter(...)` để bind tham số theo khả năng của provider/native query.
- `setFirstResult(...)` và `setMaxResults(...)` cho phân trang.
- `getResultList()` để lấy nhiều kết quả.
- `getSingleResult()` để nhận một kết quả với exception semantics tương ứng.
- `executeUpdate()` cho câu SQL thay đổi dữ liệu khi phù hợp và có transaction cần thiết.

**Lệnh `createNativeQuery(...)` chưa đồng nghĩa query đã chạy.** Việc thực thi xảy ra khi gọi các phương thức phù hợp như `getResultList()`, `getSingleResult()` hoặc `executeUpdate()`.

## 4. SELECT một cột: kết quả dạng giá trị scalar

Query chỉ chọn tên sách:

```java
Query query = em.createNativeQuery(
    "SELECT title FROM books ORDER BY id"
);

List<?> results = query.getResultList();

for (Object value : results) {
    String title = (String) value;
    System.out.println(title);
}
```

Kết quả thường gặp:

```text
Java cơ bản
JPA thực hành
SQL nâng cao
```

Khi query không có mapping đặc biệt, **mỗi phần tử của danh sách thường là một giá trị**, không phải một `Object[]` một phần tử.

Do đó, code sau có thể sai:

```java
// Sai khi provider trả mỗi hàng là String:
for (Object row : results) {
    Object[] columns = (Object[]) row;
}
```

Trên một provider trả `String` cho SELECT một cột, phép cast trên ném `ClassCastException`.

### Không đồng nhất kiểu SQL với kiểu Java một cách tuyệt đối

Với `VARCHAR`, nhiều provider/driver trả `String`. Nhưng với numeric, date/time, JSON, UUID, enum hoặc cột đặc biệt, Java type có thể phụ thuộc driver và mapping.

Nếu query đã được gắn `@SqlResultSetMapping` hoặc cấu hình scalar mapping riêng, hình dạng kết quả có thể khác cách đọc mặc định. Hãy xem **hợp đồng result mapping của chính query** trước khi cast.

### Query một cột dùng `List<?>`

Một cách viết thận trọng:

```java
List<?> values = em.createNativeQuery(
    "SELECT title FROM books ORDER BY id"
).getResultList();

for (Object value : values) {
    if (!(value instanceof String title)) {
        throw new IllegalStateException(
            "Unexpected title column type: " +
            (value == null ? "null" : value.getClass().getName())
        );
    }

    System.out.println(title);
}
```

Đoạn code sử dụng Java pattern matching for `instanceof`, phù hợp với Java 17. Nếu version Java thấp hơn, thay bằng kiểm tra `instanceof` và cast thủ công.

Kiểm tra kiểu explicit có lợi khi query nằm ở tầng repository với yêu cầu dữ liệu nghiêm ngặt; nó tạo lỗi rõ hơn thay vì để `ClassCastException` xuất hiện sâu trong business logic.

## 5. SELECT nhiều cột: mỗi hàng thường là `Object[]`

Query:

```java
Query query = em.createNativeQuery(
    "SELECT id, title, price FROM books ORDER BY id"
);

List<?> results = query.getResultList();
```

Một hàng thường có dạng:

```text
Object[] row
├── row[0] -> id
├── row[1] -> title
└── row[2] -> price
```

Code đọc:

```java
for (Object result : results) {
    Object[] row = (Object[]) result;

    Object idValue = row[0];
    Object titleValue = row[1];
    Object priceValue = row[2];

    System.out.println(
        idValue + " | " + titleValue + " | " + priceValue
    );
}
```

Thứ tự phần tử tương ứng với **thứ tự expression trong SELECT**:

```sql
SELECT id, title, price FROM books;
```

khác:

```sql
SELECT title, price, id FROM books;
```

Với query thứ hai:

```text
row[0] = title
row[1] = price
row[2] = id
```

**Object[] là cấu trúc theo vị trí, không phải Map<String, Object> theo tên cột.** Alias SQL có thể giúp tài liệu hóa hoặc cấu hình mapping, nhưng tự nó không biến mảng thành truy cập theo key.

### Bảng minh họa hình dạng kết quả

| SELECT | Hình dạng phổ biến khi không mapping tường minh |
| --- | --- |
| `SELECT title` | Một scalar mỗi hàng |
| `SELECT id` | Một numeric scalar mỗi hàng |
| `SELECT COUNT(*)` | Một numeric scalar |
| `SELECT id, title` | `Object[]` dài 2 |
| `SELECT id, title, price` | `Object[]` dài 3 |
| `SELECT id, COUNT(*) ... GROUP BY id` | `Object[]` dài 2 |
| `SELECT b.*` với nhiều cột | Thường `Object[]` nếu không khai báo result class/mapping |
| `SELECT b.*` và `Book.class` result class | Entity `Book` nếu mapping và cột phù hợp |
| Query có `@SqlResultSetMapping` | Theo mapping được khai báo, có thể không phải scalar/Object[] mặc định |

Khi nhận một array, phải hiểu rõ nó đại diện cho **một hàng** của query, không phải toàn bộ tập kết quả.

## 6. Hai tầng container dễ nhầm: List và Object[]

Kết quả native query nhiều cột thường có cấu trúc:

```text
List<?> results
   │
   ├── Object[] row 1
   │      ├── [0] id
   │      ├── [1] title
   │      └── [2] price
   │
   ├── Object[] row 2
   │      ├── [0] id
   │      ├── [1] title
   │      └── [2] price
   │
   └── Object[] row 3
          ├── [0] id
          ├── [1] title
          └── [2] price
```

Một cách đọc phổ biến:

```java
List<?> rows = em.createNativeQuery(
    "SELECT id, title, price FROM books"
).getResultList();

for (Object element : rows) {
    Object[] columns = (Object[]) element;

    System.out.println(columns.length); // Thường là 3.
}
```

Không nên viết:

```java
Object[] allRows = (Object[]) query.getResultList();
```

vì `getResultList()` trả một `List`, không phải một array chứa toàn bộ hàng.

Cũng không nên viết:

```java
List<Object[]> rows =
    (List<Object[]>) query.getResultList();
```

rồi coi đây là một phép xác thực runtime của kiểu phần tử. Do type erasure, việc cast List không kiểm tra từng phần tử. Nếu query thực tế trả scalar, lỗi sẽ xuất hiện khi lấy phần tử và cast sang `Object[]`.

Cách an toàn hơn trong code dùng chung cho nhiều provider là giữ `List<?>` và kiểm tra shape từng hàng trước khi chuyển đổi.

## 7. Kiểm tra kích thước và kiểu mảng trước khi đọc

Khi một repository dựa vào chính xác ba cột, hãy viết hợp đồng rõ:

```java
List<?> rawRows = em.createNativeQuery(
    "SELECT id, title, price FROM books ORDER BY id"
).getResultList();

for (Object rawRow : rawRows) {
    if (!(rawRow instanceof Object[] columns)) {
        throw new IllegalStateException(
            "Expected Object[] result for three-column query"
        );
    }

    if (columns.length != 3) {
        throw new IllegalStateException(
            "Expected 3 columns, got " + columns.length
        );
    }

    // Đọc và chuyển đổi từng cột ở đây.
}
```

Khi query bị đổi từ:

```sql
SELECT id, title, price FROM books
```

sang:

```sql
SELECT id, title, category, price FROM books
```

đoạn check mảng sẽ phát hiện hợp đồng shape đã thay đổi. Không kiểm tra, code cũ có thể lấy `columns[2]` (nay là category String) rồi cố cast sang BigDecimal, hoặc nguy hiểm hơn, dữ liệu bị gán nhầm vào field có cùng kiểu.

### Vì sao cast trực tiếp không đủ?

```java
Long id = (Long) columns[0];
BigDecimal price = (BigDecimal) columns[2];
```

Cả hai cast có thể thất bại do provider trả `BigInteger`, `Integer` hoặc kiểu `Number` khác cho ID, hoặc trả số với kiểu không đúng mong đợi cho cột giá. Cần phân biệt **vị trí cột đúng** và **kiểu Java mà provider thực sự trả**.

## 8. Kiểu số: đừng mặc định native BIGINT thành Java Long

Giả sử:

```sql
SELECT id FROM books;
```

Cột SQL `BIGINT` có thể được JDBC/provider thể hiện bằng `Long` trong nhiều hệ thống, nhưng native scalar mapping cũng có thể trả `BigInteger`, `BigDecimal` hoặc kiểu `Number` khác tùy provider/dialect/driver và biểu thức SQL.

Đây là anti-pattern phổ biến:

```java
Long id = (Long) query.getSingleResult();
```

Nếu runtime value là `BigInteger`, cast sẽ ném `ClassCastException` dù giá trị số nằm trong phạm vi Long.

Cách linh hoạt hơn:

```java
Object raw = query.getSingleResult();

if (!(raw instanceof Number number)) {
    throw new IllegalStateException("Expected numeric ID");
}

long id = number.longValue();
```

Cách này đọc được nhiều loại `Number`, nhưng `longValue()` có thể **làm mất phần thập phân hoặc tràn phạm vi** trong một số tình huống. Với khóa ID cần chính xác tuyệt đối, nên kiểm soát conversion.

### Chuyển sang long có kiểm tra phạm vi

```java
static long toLongExact(Object raw, String column) {
    if (!(raw instanceof Number number)) {
        throw new IllegalArgumentException(
            column + " must be numeric"
        );
    }

    if (number instanceof BigDecimal decimal) {
        return decimal.longValueExact();
    }

    if (number instanceof BigInteger integer) {
        return integer.longValueExact();
    }

    if (number instanceof Byte ||
        number instanceof Short ||
        number instanceof Integer ||
        number instanceof Long) {
        return number.longValue();
    }

    // Với Float/Double, không giả định tự động chính xác;
    // cần contract rõ hơn nếu query thực sự trả kiểu này.
    throw new IllegalArgumentException(
        "Unsupported numeric type for exact ID: " +
        number.getClass().getName()
    );
}
```

Nếu schema ID là BIGINT và driver trả Float/Double, đây là điều cần điều tra thay vì âm thầm truncate.

### Count và Sum cũng là Number

```java
Object rawCount = em.createNativeQuery(
    "SELECT COUNT(*) FROM books"
).getSingleResult();

long count = toLongExact(rawCount, "count");
```

Kết quả `COUNT(*)` phổ biến là kiểu số nguyên. Java type cụ thể có thể khác; vì vậy chuyển kiểu từ `Number` hoặc dùng result mapping rõ ràng sẽ bền hơn cast cứng sang `Long`.

## 9. `BigDecimal`, `DECIMAL` và số tiền

Đối với giá tiền, nên dùng kiểu chính xác như `BigDecimal` trong Java và `DECIMAL`/`NUMERIC` trong database.

Ví dụ:

```sql
SELECT price FROM books WHERE id = ?;
```

Một driver/provider thường trả `BigDecimal` cho cột `DECIMAL`. Nhưng để code rõ hợp đồng:

```java
Object rawPrice = em.createNativeQuery(
    "SELECT price FROM books WHERE id = ?"
).setParameter(1, 101L)
 .getSingleResult();

BigDecimal price;

if (rawPrice instanceof BigDecimal decimal) {
    price = decimal;
} else if (rawPrice instanceof BigInteger integer) {
    price = new BigDecimal(integer);
} else if (rawPrice instanceof Number number) {
    price = new BigDecimal(number.toString());
} else {
    throw new IllegalStateException("Unexpected price type");
}
```

Cần thận trọng: nếu `Number` thực tế là `Double` hoặc `Float`, độ chính xác đã có thể bị mất ở tầng JDBC/truy vấn trước khi chuyển thành BigDecimal; `new BigDecimal(number.toString())` không thể lấy lại phần chính xác đã mất.

Vì vậy, với dữ liệu tiền tệ:

- Khai báo `DECIMAL`/`NUMERIC` đủ precision và scale ở DB.
- Tránh cast cột tiền sang `FLOAT`/`DOUBLE` trong SQL.
- Cân nhắc `@ColumnResult(type = BigDecimal.class)` hoặc mapping provider thích hợp.
- Viết integration test xác minh các giá trị thập phân có phần lẻ và biên lớn.
- Không dùng `Double` để tính giá trị tiền nghiệp vụ.

### Chuyển đổi helper dùng lại

```java
static BigDecimal toDecimal(Object raw, String column) {
    if (raw instanceof BigDecimal decimal) {
        return decimal;
    }

    if (raw instanceof BigInteger integer) {
        return new BigDecimal(integer);
    }

    if (raw instanceof Byte ||
        raw instanceof Short ||
        raw instanceof Integer ||
        raw instanceof Long) {
        return BigDecimal.valueOf(((Number) raw).longValue());
    }

    throw new IllegalArgumentException(
        column + " requires an exact decimal-compatible value"
    );
}
```

Helper cố ý từ chối `Float`/`Double` để tránh che giấu lỗi precision trong tình huống tiền tệ. Với trường hợp thống kê khoa học chấp nhận số gần đúng, có thể có helper khác dùng `doubleValue()` theo contract của dữ liệu.

## 10. Một kết quả COUNT hoặc SUM qua `getSingleResult()`

Ví dụ đếm:

```java
Query query = em.createNativeQuery(
    "SELECT COUNT(*) FROM books WHERE published = ?"
);

query.setParameter(1, true);

Number total = (Number) query.getSingleResult();
long count = total.longValue();
```

Đây là mẫu ngắn gọn thường hợp lý cho COUNT phổ biến khi biết provider trả `Number`. Nếu cần bảo vệ khỏi overflow, dùng helper exact ở trên.

### SUM có thể trả null

```sql
SELECT SUM(price) FROM books WHERE category = 'DOES_NOT_EXIST';
```

Với tập không có hàng phù hợp, `SUM` thường trả `NULL` (trái với `COUNT` trả 0). Vì vậy:

```java
Object raw = em.createNativeQuery(
    "SELECT SUM(price) FROM books WHERE category = ?"
).setParameter(1, "DOES_NOT_EXIST")
 .getSingleResult();

BigDecimal total = raw == null
    ? BigDecimal.ZERO
    : toDecimal(raw, "totalPrice");
```

**Đừng viết `((Number) result).longValue()` cho mọi aggregate** vì có aggregate trả null, có aggregate cần phần thập phân, và có aggregate trả kiểu kết quả khác.

### `COALESCE` ở cấp SQL

Có thể dùng:

```sql
SELECT COALESCE(SUM(price), 0) FROM books;
```

Nhưng literal `0` có thể khiến kiểu kết quả phụ thuộc type coercion của database. Khi cần BigDecimal chính xác, có thể dùng SQL cast phù hợp dialect hoặc result mapping xác định kiểu đầu ra.

## 11. Khác biệt giữa một hàng và nhiều hàng

Hai phương thức đọc chính:

```java
List<?> rows = query.getResultList();
```

và:

```java
Object one = query.getSingleResult();
```

### `getResultList()`

- Trả danh sách các hàng/kết quả.
- Nếu không có hàng, thông thường là List rỗng.
- Với SELECT nhiều cột, mỗi phần tử thường là Object[].
- Với SELECT một cột, mỗi phần tử thường là scalar.

### `getSingleResult()`

- Trả **một kết quả** theo mapping của query.
- Nếu không có kết quả, ném `NoResultException`.
- Nếu có nhiều hơn một kết quả, ném `NonUniqueResultException`.
- Nếu SELECT nhiều cột, kết quả thường là **một `Object[]`**.
- Nếu SELECT một cột, kết quả thường là một scalar.

Ví dụ:

```java
Object raw = em.createNativeQuery(
    "SELECT id, title FROM books WHERE id = ?"
).setParameter(1, 101L)
 .getSingleResult();

Object[] columns = (Object[]) raw;
```

Khi chỉ cần một hàng nhưng không cần exception lúc không tìm thấy, có thể giới hạn query bằng `setMaxResults(1)` rồi đọc List rỗng/không rỗng:

```java
List<?> rows = em.createNativeQuery(
    "SELECT id, title FROM books WHERE published = ? " +
    "ORDER BY id"
).setParameter(1, true)
 .setMaxResults(1)
 .getResultList();

if (!rows.isEmpty()) {
    Object[] columns = (Object[]) rows.get(0);
}
```

Dùng `setMaxResults(1)` để giới hạn **ở cấp query**, không tải tất cả hàng rồi lấy `rows.get(0)` nếu chỉ muốn phần tử đầu.

### Cẩn trọng với ORDER BY

Nếu query không có `ORDER BY` và dùng `setMaxResults(1)`, “hàng đầu tiên” không có nghĩa ổn định theo yêu cầu nghiệp vụ. Thêm thứ tự rõ ràng, thường có một cột ID làm tiebreaker.

## 12. Cột null: row không null nhưng phần tử trong mảng có thể null

Giả sử:

```sql
SELECT id, title, published_at
FROM books
ORDER BY id;
```

`published_at` của Book #103 là null. Với kết quả dạng `Object[]`:

```java
Object[] row = (Object[]) raw;

Object idValue = row[0];       // Khác null nếu PK hợp lệ.
Object titleValue = row[1];    // Khác null theo schema.
Object publishedAt = row[2];   // Có thể null.
```

Không viết:

```java
Timestamp value = (Timestamp) row[2];
LocalDateTime dateTime = value.toLocalDateTime();
```

nếu cột cho phép null. Cần:

```java
Object value = row[2];

LocalDateTime publishedAt = null;

if (value instanceof Timestamp timestamp) {
    publishedAt = timestamp.toLocalDateTime();
} else if (value instanceof LocalDateTime dateTime) {
    publishedAt = dateTime;
} else if (value != null) {
    throw new IllegalStateException(
        "Unsupported timestamp result: " +
        value.getClass().getName()
    );
}
```

Sự khác nhau giữa `java.sql.Timestamp` và `java.time.LocalDateTime` phụ thuộc driver, JDBC mapping và provider. Không nên tự giả định native scalar date/time đã được chuyển về đúng Java type mà entity sử dụng.

### Outer join tạo nullable columns

Ngay cả cột `authors.name` là `NOT NULL`, khi query dùng `LEFT JOIN` với một Book không có Author, cột phía Author trong result set vẫn có thể null:

```sql
SELECT b.id, b.title, a.name
FROM books b
LEFT JOIN authors a ON a.id = b.author_id;
```

Do đó, nullability của một phần tử `Object[]` phụ thuộc **kết quả truy vấn**, không chỉ DDL của cột gốc.

## 13. Xử lý ngày/giờ, timestamp và múi giờ

Native SQL với `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` và các hàm thời gian có thể trả những kiểu Java khác nhau.

Ví dụ:

```sql
SELECT published_at FROM books WHERE id = ?;
```

Trong thực tế có thể gặp:

- `java.sql.Timestamp`.
- `java.time.LocalDateTime`.
- `java.sql.Date` cho SQL DATE.
- `java.time.LocalDate` ở các mapping hỗ trợ.
- `OffsetDateTime` hoặc kiểu khác với column/timezone đặc biệt.

Không trộn hai khái niệm:

- **LocalDateTime:** thời gian lịch địa phương, không tự mang một offset.
- **Instant/OffsetDateTime:** đại diện hoặc liên hệ tới mốc thời gian tuyệt đối/offset.
- **Timestamp của JDBC:** kiểu trung gian có semantics riêng tùy SQL column và driver.

### Ví dụ chuyển DATE

```java
static LocalDate toLocalDate(Object raw) {
    if (raw == null) {
        return null;
    }

    if (raw instanceof LocalDate date) {
        return date;
    }

    if (raw instanceof java.sql.Date sqlDate) {
        return sqlDate.toLocalDate();
    }

    throw new IllegalArgumentException(
        "Unexpected SQL DATE type: " + raw.getClass().getName()
    );
}
```

### Không tự cast timezone

Nếu SQL column có timezone semantics, cần biết database lưu gì và driver trả gì trước khi quyết định có chuyển `Timestamp` thành `Instant` hay `OffsetDateTime` không. Dùng một phép `atZone(ZoneId.systemDefault())` tùy tiện có thể làm thay đổi ý nghĩa thời điểm giữa các server.

Khuyến nghị: xác định timezone policy của ứng dụng, loại SQL column và conversion mapping cụ thể; viết integration test cho offset, DST và dữ liệu lịch sử khi nghiệp vụ phụ thuộc thời gian chính xác.

## 14. SQL Boolean cũng có thể không thành Java Boolean

Query:

```sql
SELECT published FROM books WHERE id = ?;
```

nhiều hệ thống trả `Boolean`. Nhưng database không có native boolean column hoặc SQL dùng `CASE WHEN ... THEN 1 ELSE 0 END` có thể khiến JDBC trả `Integer`, `Short` hoặc loại số khác.

Ví dụ:

```java
Object raw = em.createNativeQuery(
    "SELECT published FROM books WHERE id = ?"
).setParameter(1, 101L)
 .getSingleResult();
```

Không nên mặc định:

```java
Boolean published = (Boolean) raw;
```

trừ khi đã xác định contract trên DB/provider cụ thể.

Với một query trả numeric flag, phải đặt quy tắc mapping rõ:

```java
static boolean fromZeroOne(Object raw) {
    if (raw instanceof Boolean value) {
        return value;
    }

    if (raw instanceof Number number) {
        long n = number.longValue();
        if (n == 0L) return false;
        if (n == 1L) return true;
    }

    throw new IllegalArgumentException(
        "Expected boolean or numeric 0/1"
    );
}
```

Helper này chỉ phù hợp khi business/SQL contract nói rõ flag là boolean hoặc numeric 0/1. Không dùng cho mọi cột số. Nếu số có phần thập phân, cần kiểm tra chính xác thay vì `longValue()` để tránh biến `1.5` thành `1`; với mapping flag nghiêm ngặt, hãy ưu tiên SQL cast/mapping và test cụ thể.

## 15. Đọc Object[] bằng một hàm chuyển đổi trung tâm

Nếu business code rải rác:

```java
Long id = ((Number) row[0]).longValue();
String title = (String) row[1];
BigDecimal price = (BigDecimal) row[2];
```

ở nhiều controller và service, khi thay đổi query sẽ phải sửa rất nhiều nơi. Nên tập trung việc giải mã row tại repository hoặc mapper riêng.

Ví dụ DTO:

```java
public record BookRow(
    long id,
    String title,
    BigDecimal price
) {}
```

Mapper:

```java
public final class BookRowMapper {

    private BookRowMapper() {}

    public static BookRow from(Object raw) {
        if (!(raw instanceof Object[] row)) {
            throw new IllegalArgumentException(
                "Expected an Object[] row"
            );
        }

        if (row.length != 3) {
            throw new IllegalArgumentException(
                "Expected 3 columns, got " + row.length
            );
        }

        long id = toLongExact(row[0], "id");

        if (!(row[1] instanceof String title)) {
            throw new IllegalArgumentException(
                "title must be a String"
            );
        }

        BigDecimal price = toDecimal(row[2], "price");

        return new BookRow(id, title, price);
    }

    // toLongExact(...) và toDecimal(...)
    // là các helper ở các phần trước.
}
```

Repository:

```java
public List<BookRow> findBookRows(EntityManager em) {
    List<?> rawRows = em.createNativeQuery(
        "SELECT id, title, price FROM books ORDER BY id"
    ).getResultList();

    return rawRows.stream()
        .map(BookRowMapper::from)
        .toList();
}
```

Như vậy:

- Repository biết SQL và vị trí cột.
- Mapper biết kiểm tra/convert kiểu.
- DTO biểu diễn output đã kiểm soát.
- Tầng service/controller không phải biết `row[2]` là field nào.
- Khi thay đổi SELECT, lỗi shape dễ được phát hiện tại một chỗ.

**DTO giúp rời khỏi thế giới `Object[]` càng sớm càng tốt.** Đây là cách giảm độ mong manh của native SQL không mapping tường minh.

## 16. Vì sao record/DTO tốt hơn truyền `Object[]` qua các tầng?

Giả sử một service nhận:

```java
Object[] row
```

Không có cách nhìn signature để biết:

- `row[0]` là ID hay title?
- `row[2]` có được null không?
- ID trả Long hay BigInteger?
- Price dùng DECIMAL hay float?
- Thứ tự cột đã đổi chưa?
- Query dùng JOIN nào tạo hàng lặp?

Với DTO:

```java
public record BookRow(
    long id,
    String title,
    BigDecimal price
) {}
```

contract rõ hơn nhiều. Caller có thể viết:

```java
BookRow row = repository.findById(id);

System.out.println(row.title());
```

thay vì:

```java
Object[] row = repository.findById(id);

System.out.println((String) row[1]);
```

DTO còn hỗ trợ:

- Validation ở ranh giới dữ liệu.
- Serialization ổn định.
- Unit test mapper độc lập với business logic.
- Refactor field name.
- Chuyển kết quả cho API mà không kéo theo managed entity state.
- Không gây nhầm lẫn về dirty checking/cascade như khi đưa entity ra ngoài persistence context.

Tuy vậy, DTO chỉ giải quyết tính rõ ràng của kết quả Java; nó không tự kiểm soát SQL injection, transaction, null conversion hoặc query performance nếu repository viết sai.

## 17. Sử dụng `@SqlResultSetMapping` để mô tả kết quả rõ ràng hơn

Khi native query được dùng nhiều lần và có shape ổn định, JPA hỗ trợ `@SqlResultSetMapping`.

Có ba nhóm mapping kết quả quan trọng:

- `@EntityResult`: ánh xạ dữ liệu sang entity.
- `@ColumnResult`: ánh xạ cột scalar.
- `@ConstructorResult`: tạo object bằng constructor.

Ví dụ một DTO:

```java
public class BookReportRow {

    private final Long id;
    private final String title;
    private final BigDecimal price;

    public BookReportRow(
            Long id, String title, BigDecimal price) {
        this.id = id;
        this.title = title;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public BigDecimal getPrice() { return price; }
}
```

Khai báo mapping trên một entity được JPA scan, ví dụ `Book`:

```java
@SqlResultSetMapping(
    name = "BookReportMapping",
    classes = @ConstructorResult(
        targetClass = BookReportRow.class,
        columns = {
            @ColumnResult(name = "book_id", type = Long.class),
            @ColumnResult(name = "book_title", type = String.class),
            @ColumnResult(name = "book_price", type = BigDecimal.class)
        }
    )
)
@Entity
@Table(name = "books")
public class Book {
    // Các field entity như ví dụ trước.
}
```

Query:

```java
Query query = em.createNativeQuery(
    "SELECT id AS book_id, " +
    "title AS book_title, " +
    "price AS book_price " +
    "FROM books ORDER BY id",
    "BookReportMapping"
);

List<?> raw = query.getResultList();

List<BookReportRow> rows = raw.stream()
    .map(BookReportRow.class::cast)
    .toList();
```

Lúc này mỗi hàng theo mapping dự kiến là `BookReportRow`, không phải `Object[]`. Tên alias trong SQL phải khớp tên được `@ColumnResult` khai báo.

### Lưu ý với `@ConstructorResult`

- Constructor phải nhận các tham số theo **đúng thứ tự** và kiểu được mapping mô tả.
- `type = Long.class` yêu cầu provider thực hiện conversion tương ứng nếu hỗ trợ.
- Không nên nghĩ annotation có thể chuyển mọi giá trị SQL tùy ý thành mọi Java type.
- Mức hỗ trợ type conversion chi tiết có thể phụ thuộc provider/JDBC driver.
- Constructor projection DTO không tự khiến object thành managed entity.
- Nếu target class là entity, lifecycle result có thể có các quy tắc riêng; không nên dùng constructor mapping như cách thay thế việc trả entity managed theo thiết kế.

Ví dụ này giảm code `row[0]`/`row[1]`/`row[2]` nhưng cần kiểm thử ánh xạ thật với đúng provider.

## 18. `@ColumnResult` cho scalar có type mong muốn

Nếu query trả một số tổng hợp:

```sql
SELECT COUNT(*) AS total_books FROM books;
```

có thể định nghĩa mapping:

```java
@SqlResultSetMapping(
    name = "BookCountMapping",
    columns = @ColumnResult(
        name = "total_books",
        type = Long.class
    )
)
```

Và dùng:

```java
Query query = em.createNativeQuery(
    "SELECT COUNT(*) AS total_books FROM books",
    "BookCountMapping"
);

Object total = query.getSingleResult();
```

Ý định là để JPA provider trả scalar được chuyển về `Long` theo mapping đã khai báo. Tuy nhiên, vẫn cần xác nhận kiểu thực tế trên database/provider mục tiêu, vì dialect có thể ảnh hưởng conversion và một mapping không hợp lệ có thể phát lỗi runtime.

### Khi nào mapping tường minh đáng giá?

- Native query được sử dụng lâu dài trong production.
- Schema/SQL ổn định nhưng nhiều cột.
- Có số tiền, timestamp hoặc numeric types quan trọng.
- Muốn DTO thay vì `Object[]` trong business code.
- Cần tránh cast lặp đi lặp lại ở nhiều repository.
- Dự án có integration tests và kiểm soát được provider/version.

Với truy vấn rất ngắn dùng một lần, chuyển từ `Object[]` sang DTO bằng mapper rõ ràng đôi khi đơn giản hơn việc thêm annotation mapping. Không có một lựa chọn duy nhất cho mọi truy vấn.

## 19. Native result mapping sang entity khác scalar/Object[]

Nếu muốn native SQL trả entity `Book` được JPA quản lý, có overload:

```java
Query query = em.createNativeQuery(
    "SELECT id, title, price, category, " +
    "published, published_at " +
    "FROM books WHERE id = ?",
    Book.class
);

Book book = (Book) query
    .setParameter(1, 101L)
    .getSingleResult();
```

Trong trường hợp mapping phù hợp, result là Book entity, không phải Object[].

### Vì sao phải chọn đủ cột?

JPA provider cần các cột đủ để hydrate entity theo mapping, đặc biệt ID và các mapped fields cần thiết. Chọn thiếu cột hoặc alias không phù hợp có thể gây lỗi, giá trị không hợp lệ hoặc hành vi không portable.

Ví dụ:

```java
em.createNativeQuery(
    "SELECT id, title FROM books",
    Book.class
);
```

không nên coi là cách portable để tạo Book entity chỉ có một vài field. Nếu chỉ cần ID và title, hãy dùng **scalar/DTO projection**.

### Cẩn thận với first-level cache

Native query mapping sang managed entity vẫn chịu persistence context identity map. Nếu một Book cùng ID đã được managed trong context, provider phải tuân thủ lifecycle/identity semantics; không nên mặc định query native luôn ghi đè state managed hiện tại bằng mọi giá trị từ DB.

Muốn lấy dữ liệu mới nhất sau bulk SQL hoặc cập nhật từ ngoài, hãy xét `refresh()` hoặc context mới theo transaction/cache policy phù hợp.

## 20. SQL alias có vai trò gì với Object[]?

Query:

```sql
SELECT
    b.id AS book_id,
    b.title AS book_title,
    b.price AS book_price
FROM books b;
```

Nếu đọc theo `Object[]` thông thường:

```java
Object[] row = (Object[]) result;

Object id = row[0];
Object title = row[1];
Object price = row[2];
```

Alias `book_id`, `book_title`, `book_price` **không tạo API `row.get("book_id")`** vì array không có key.

Alias hữu ích khi:

- Truy vấn JOIN nhiều bảng có cột trùng tên.
- Dùng `@SqlResultSetMapping` để tham chiếu theo `@ColumnResult(name = "...")`.
- Muốn SQL dễ đọc và contract cột rõ ràng.
- Trả dữ liệu cho công cụ query/database.
- Cấu hình provider-specific mapping theo alias.

Nếu ứng dụng rất cần truy cập kết quả theo tên thay vì vị trí, hãy dùng mapping DTO, Tuple khi provider/API hỗ trợ phù hợp hoặc JDBC `ResultSet.getObject("alias")`; không tự giả định một native `Object[]` có metadata alias đi kèm.

## 21. SELECT * là rủi ro cho mapping bằng vị trí

Ví dụ không bền vững:

```java
List<?> rows = em.createNativeQuery(
    "SELECT * FROM books"
).getResultList();
```

Sau đó:

```java
Object[] row = (Object[]) rows.get(0);

Long id = ((Number) row[0]).longValue();
String title = (String) row[1];
```

Nếu schema đổi thứ tự cột hoặc thêm cột, cách dùng index có thể trở nên khó kiểm soát. Thứ tự `SELECT *` dựa trên schema/table expansion của database; khi code phụ thuộc số cột và vị trí, thay đổi schema có thể phá vỡ contract.

Tốt hơn:

```sql
SELECT id, title, price
FROM books
ORDER BY id;
```

Và dùng mapper kiểm tra shape.

**Đối với native result Object[] trong code production, nên liệt kê tường minh các cột và giữ thứ tự ổn định.**

Ngoài ra, chỉ chọn các cột ứng dụng thực sự cần giúp giảm IO và tránh vô tình trả dữ liệu nhạy cảm từ bảng lớn.

## 22. Truy vấn JOIN nhiều bảng và các tên cột trùng nhau

Giả sử có bảng `authors`:

```sql
CREATE TABLE authors (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
```

Sách có `author_id`. Query:

```sql
SELECT
    b.id AS book_id,
    b.title AS book_title,
    a.id AS author_id,
    a.name AS author_name
FROM books b
JOIN authors a ON a.id = b.author_id
ORDER BY b.id;
```

Một hàng thường có:

```text
row[0] = book_id
row[1] = book_title
row[2] = author_id
row[3] = author_name
```

Mapper:

```java
public record BookAuthorRow(
    long bookId,
    String bookTitle,
    long authorId,
    String authorName
) {}

static BookAuthorRow mapBookAuthor(Object raw) {
    if (!(raw instanceof Object[] row) || row.length != 4) {
        throw new IllegalArgumentException(
            "Expected a four-column BookAuthor row"
        );
    }

    return new BookAuthorRow(
        toLongExact(row[0], "bookId"),
        (String) row[1],
        toLongExact(row[2], "authorId"),
        (String) row[3]
    );
}
```

Các cast String ở đây dựa vào contract của hai cột `VARCHAR NOT NULL`. Nếu dùng LEFT JOIN và `author_name` có thể null, mapper cần cập nhật tương ứng.

### Phân biệt một Book với một row của JOIN

Nếu Book có nhiều Review:

```sql
SELECT b.id, b.title, r.id, r.rating
FROM books b
JOIN reviews r ON r.book_id = b.id;
```

một Book có 10 Review có thể xuất hiện trong 10 `Object[]` khác nhau. Đây là **số hàng SQL JOIN**, không đồng nghĩa 10 Book entities khác nhau.

Khi muốn một dòng trên mỗi Book, có thể dùng aggregation, `DISTINCT`, window function hoặc group đúng theo nghiệp vụ. Không gom `Object[]` thành entity bằng index rồi suy rằng result rows luôn unique theo Book ID.

## 23. Aggregate nhiều cột: GROUP BY trả `Object[]`

Ví dụ thống kê số sách và tổng giá theo category:

```sql
SELECT
    category,
    COUNT(*) AS book_count,
    SUM(price) AS total_price
FROM books
GROUP BY category
ORDER BY category;
```

Một kết quả:

```text
Object[] row
  [0] category     -> String
  [1] book_count   -> Number
  [2] total_price  -> Number/BigDecimal hoặc null trong tình huống khác
```

DTO:

```java
public record CategoryStats(
    String category,
    long bookCount,
    BigDecimal totalPrice
) {}
```

Mapper:

```java
static CategoryStats mapCategoryStats(Object raw) {
    if (!(raw instanceof Object[] row) || row.length != 3) {
        throw new IllegalArgumentException(
            "Expected 3-column category stats"
        );
    }

    if (!(row[0] instanceof String category)) {
        throw new IllegalArgumentException("Invalid category");
    }

    long bookCount = toLongExact(row[1], "bookCount");

    BigDecimal totalPrice = row[2] == null
        ? BigDecimal.ZERO
        : toDecimal(row[2], "totalPrice");

    return new CategoryStats(
        category,
        bookCount,
        totalPrice
    );
}
```

Query:

```java
List<?> rows = em.createNativeQuery(
    "SELECT category, COUNT(*) AS book_count, " +
    "SUM(price) AS total_price " +
    "FROM books GROUP BY category ORDER BY category"
).getResultList();

List<CategoryStats> stats = rows.stream()
    .map(MyMapper::mapCategoryStats)
    .toList();
```

`MyMapper` ở đây là tên class chứa các helper minh họa; thay bằng class thực tế của dự án.

Một SQL expression như `AVG(price)` có thể trả kiểu có scale khác với cột price. Vì vậy, numeric contract cần xét **biểu thức SQL đầu ra**, không chỉ DDL gốc.

## 24. Query không có kết quả, một hàng null, và aggregate null

Ba tình huống khác nhau:

**A. Không có hàng nào:**

```sql
SELECT id FROM books WHERE id = -1;
```

`getResultList()` trả List rỗng; `getSingleResult()` thường ném `NoResultException`.

**B. Có một hàng nhưng cột được chọn là null:**

```sql
SELECT published_at FROM books WHERE id = 103;
```

Có một hàng, scalar value có thể là null. Khi `getResultList()` được dùng, danh sách có thể chứa một phần tử null nếu mapping cho phép.

**C. Aggregate trả null trên tập rỗng:**

```sql
SELECT SUM(price) FROM books WHERE id < 0;
```

SQL aggregate `SUM` thường trả một hàng chứa null, không phải không có hàng. `getSingleResult()` có thể trả null trong tình huống này.

So sánh:

| Tình huống | Ý nghĩa |
| --- | --- |
| `getResultList().isEmpty()` | Không có result row |
| Một phần tử `null` trong List | Có result row nhưng scalar column null |
| `Object[]` có phần tử null | Có result row nhiều cột, một số cột null |
| `SUM(...) == null` | Aggregate không có giá trị để tổng hợp |
| `COUNT(...) == 0` | Có một scalar row đếm bằng 0 |

Không dùng `Optional.of(result)` nếu result có thể null; dùng `Optional.ofNullable(...)` theo contract. Và đừng gọi `row[2].toString()` khi cột SQL nullable.

## 25. Tham số native SQL: bind giá trị, không ghép chuỗi người dùng

Một ví dụ không an toàn:

```java
String sql =
    "SELECT id, title FROM books WHERE category = '" +
    userInput +
    "'";
```

Nếu `userInput` chứa các ký tự SQL đặc biệt, ứng dụng có thể bị SQL injection. Dùng parameter binding:

```java
Query query = em.createNativeQuery(
    "SELECT id, title FROM books WHERE category = ?"
);

query.setParameter(1, category);
List<?> rows = query.getResultList();
```

Ở ví dụ này, `1` là vị trí tham số đầu tiên theo API JPA dùng positional parameter. Trong native SQL, cách hỗ trợ positional/named parameters và cú pháp marker chi tiết có thể phụ thuộc phiên bản/provider; khi cần tính portable, kiểm tra contract JPA/provider và dùng positional binding phổ biến.

### Named parameter trong native SQL

Một số provider cho phép:

```java
Query query = em.createNativeQuery(
    "SELECT id FROM books WHERE category = :category"
);
query.setParameter("category", category);
```

Nhưng **named parameters trong native SQL không phải lựa chọn portable trên mọi JPA provider theo các quy tắc chuẩn cũ**; nhiều ứng dụng dùng nhờ extension của Hibernate hoặc môi trường cụ thể. Không tự giả định syntax này hoạt động giống JPQL trên mọi provider.

Nếu dự án hỗ trợ rõ named parameters với native SQL, có thể dùng theo tài liệu provider; nếu cần portable, dùng positional binding phù hợp.

### Không thể parameterize tên bảng/cột/ORDER BY tùy ý

`setParameter` bind **giá trị**, không bind các identifier SQL:

```java
// Không có nghĩa đặt cột muốn sort bằng parameter:
"SELECT id FROM books ORDER BY ?"
```

Giá trị bind không biến thành tên cột một cách portable. Với sort động, dùng whitelist:

```java
String orderBy = switch (sortField) {
    case "title" -> "title";
    case "price" -> "price";
    default -> "id";
};

String sql =
    "SELECT id, title, price FROM books ORDER BY " +
    orderBy +
    " ASC";
```

Ở đây `orderBy` chỉ đến từ tập constant do lập trình viên định nghĩa, không phải chuỗi SQL tùy ý từ request.

Tương tự, giới hạn page size và chỉ cho phép các cột/filter nghiệp vụ đã được phê duyệt.

## 26. Phân trang kết quả Object[] bằng JPA Query

Với một danh sách lớn:

```java
Query query = em.createNativeQuery(
    "SELECT id, title, price FROM books ORDER BY id"
);

List<?> rows = query
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

`setFirstResult` và `setMaxResults` áp dụng tại mức JPA Query. Provider sẽ thực hiện pagination phù hợp với database/dialect; không nên tự kết luận SQL chính xác là `LIMIT/OFFSET` trên mọi RDBMS.

Sau đó map từng hàng:

```java
List<BookRow> books = rows.stream()
    .map(BookRowMapper::from)
    .toList();
```

### Vì sao cần ORDER BY?

Nếu không có thứ tự, một trang kết quả không có thứ tự ổn định. Các thay đổi đồng thời cũng có thể làm offset pagination bị lặp/bỏ sót row.

Với quét batch lớn, keyset pagination thường thích hợp:

```sql
SELECT id, title, price
FROM books
WHERE id > ?
ORDER BY id;
```

và `setMaxResults(batchSize)`.

Khi kết thúc một batch, lấy ID cuối làm cursor tiếp theo. Nếu ID thay đổi hoặc filter không ổn định, vẫn cần chính sách consistency riêng; keyset không tự giải quyết mọi race condition.

### Đừng dùng List tất cả hàng nếu chỉ cần ít kết quả

```java
List<?> rows = query.getResultList();
Object first = rows.get(0);
```

không hiệu quả nếu query có hàng triệu bản ghi. Dùng `setMaxResults(1)`, điều kiện WHERE rõ và ORDER BY ổn định.

## 27. Query native và `getResultStream()`

Trong phiên bản JPA hỗ trợ, native `Query` có thể trả kết quả qua `getResultStream()`:

```java
try (Stream<?> stream = em.createNativeQuery(
        "SELECT id, title, price FROM books ORDER BY id"
    ).getResultStream()) {

    stream.map(BookRowMapper::from)
          .forEach(this::processBookRow);
}
```

Tuy nhiên:

- Stream **không bảo đảm** mọi provider đọc hàng từ JDBC cursor theo nhu cầu; triển khai mặc định có thể dựa trên `getResultList().stream()`.
- Nếu provider mở cursor/ResultSet, stream có thể giữ connection/statement.
- Dùng `try-with-resources` để đóng stream.
- Tiêu thụ stream **trong lúc transaction/persistence context còn phù hợp**; không trả stream ra ngoài rồi đóng EntityManager trước khi duyệt.
- Một Java `stream.limit(10)` không bảo đảm giảm số hàng SQL; dùng `setMaxResults(10)` ở cấp JPA Query.
- Với scalar và Object[], pipeline vẫn cần mapper và validation như khi đọc List.

Dù mỗi phần tử là DTO/array thay vì managed entity, vấn đề JDBC cursor và transaction vẫn cần được xử lý riêng.

## 28. Native SQL và flush trước khi đọc dữ liệu

JPA có persistence context chứa các entity được quản lý. Giả sử:

```java
Book book = em.find(Book.class, 101L);
book.changePrice(new BigDecimal("199000.00"));
```

sau đó chạy native SQL:

```java
Object price = em.createNativeQuery(
    "SELECT price FROM books WHERE id = ?"
).setParameter(1, 101L)
 .getSingleResult();
```

Giá trị ở Java object có thể đã thay đổi, nhưng SQL `UPDATE` có thể còn pending tới flush. Khi query chạy ở flush mode thích hợp, provider phải xét ngữ nghĩa đồng bộ. **Hành vi chi tiết native SQL và khả năng provider phân tích bảng/phụ thuộc query có thể khác nhau**.

Nếu nghiệp vụ bắt buộc native query quan sát thay đổi đã làm trong cùng transaction, một lựa chọn rõ ràng là flush tường minh trước query:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 101L);
book.changePrice(new BigDecimal("199000.00"));

em.flush();

Object rawPrice = em.createNativeQuery(
    "SELECT price FROM books WHERE id = ?"
).setParameter(1, 101L)
 .getSingleResult();

em.getTransaction().commit();
```

`flush()` không phải commit. SQL ghi có thể đã chạy nhưng transaction vẫn có thể rollback, và transaction khác không tự động đọc được dữ liệu chưa commit tùy isolation.

### Nếu native SQL UPDATE dữ liệu ngoài persistence context?

```java
em.createNativeQuery(
    "UPDATE books SET price = ? WHERE id = ?"
).setParameter(1, new BigDecimal("199000.00"))
 .setParameter(2, 101L)
 .executeUpdate();
```

Bulk native DML tác động database trực tiếp; Book đang managed trong context có thể giữ giá cũ. Việc native query trả scalar/Object[] không giúp provider tự đồng bộ managed state.

Khi trộn native bulk SQL với entity operations, cần xác định ranh giới `flush()`, `clear()`, `refresh()` hoặc context mới theo use case; không dùng các thao tác đó một cách tùy tiện khi còn pending changes.

## 29. Vì sao native Object[] không được dirty checking?

Một kết quả:

```java
Object[] row = (Object[]) query.getSingleResult();

row[1] = "Tên đã sửa";
```

chỉ là thay đổi phần tử trong một Java array. JPA **không quản lý `Object[]` như một entity** và không thực hiện dirty checking để cập nhật `books.title`.

Muốn cập nhật phải:

- Tải Book managed rồi gọi domain method, để dirty checking hoạt động.
- Hoặc dùng bulk JPQL/native SQL UPDATE trong transaction.
- Hoặc thực hiện một workflow chuyển DTO thành command và áp dụng lên managed entity.

Tương tự, một `BookRow` record được tạo từ Object[] cũng chỉ là DTO, không phải Book managed. Không gọi `em.merge(bookRow)` như thể đó là entity.

### Khác biệt với native entity result

```java
Book book = (Book) em.createNativeQuery(
    "SELECT id, title, price, category, " +
    "published, published_at FROM books WHERE id = ?",
    Book.class
).setParameter(1, id)
 .getSingleResult();
```

Nếu Book được provider quản lý theo context, các thay đổi persistent trên Book có thể được dirty checking đồng bộ.

Do đó, **kiểu result không chỉ ảnh hưởng cách cast; nó còn ảnh hưởng lifecycle và cách ứng dụng được phép sửa dữ liệu**.

## 30. Phân biệt Object[] với `Tuple` và `Map`

JPA có `Tuple` cho một số truy vấn, đặc biệt Criteria/JPQL, cho phép truy cập các phần tử qua alias/index theo query semantics. Nhưng:

```java
List<?> rows = em.createNativeQuery(
    "SELECT id, title FROM books"
).getResultList();
```

không mặc nhiên trả `Tuple`. Cũng không mặc nhiên trả `Map<String,Object>`, dù SQL có alias.

Nếu một provider có API native query trả Tuple/Map theo alias, đó có thể là extension rất tiện; cần kiểm tra đúng phương thức và phiên bản provider. **Không cast `Object[]` thành `Tuple` hoặc Map chỉ vì query có cột được đặt alias**.

So sánh:

| Cấu trúc | Truy cập | Type safety | Trường hợp dùng |
| --- | --- | --- | --- |
| Một scalar | Trực tiếp giá trị | Phụ thuộc kiểu runtime | SELECT một cột |
| `Object[]` | `row[index]` | Thấp; dễ lệch index | Native SELECT nhiều cột không mapping |
| `Tuple` | Alias/index theo API | Có thể rõ hơn | Criteria/JPQL hoặc provider native support |
| DTO/record | `row.title()` | Rõ sau mapping | Boundary repository/service |
| Entity | Getter + lifecycle JPA | Theo entity mapping | Khi cần managed state/association |
| `Map<String,Object>` | Key theo alias | Tùy extension | Provider-specific transformation |

Trong ứng dụng dài hạn, **DTO hoặc explicit result mapping** thường là ranh giới phù hợp hơn khi nhiều tầng cùng đọc kết quả.

## 31. Test integration trên database/provider thật

Một native query có thể chạy tốt trên H2 nhưng trả Java types khác khi dùng PostgreSQL, MySQL hoặc một driver mới. Vì vậy, test phải chú ý **giá trị lẫn kiểu runtime**.

Ví dụ JUnit:

```java
@Test
void readsThreeColumnsAsBookRow() {
    EntityManager em = emf.createEntityManager();

    try {
        List<?> rows = em.createNativeQuery(
            "SELECT id, title, price " +
            "FROM books WHERE id = ?"
        ).setParameter(1, existingBookId)
         .getResultList();

        assertEquals(1, rows.size());

        BookRow row = BookRowMapper.from(rows.get(0));

        assertEquals(existingBookId.longValue(), row.id());
        assertEquals("Java cơ bản", row.title());

        assertEquals(
            0,
            row.price().compareTo(
                new BigDecimal("150000.00")
            )
        );
    } finally {
        em.close();
    }
}
```

Test giả định fixture có `Book #existingBookId` với dữ liệu được seed trước đó. Dùng `BigDecimal.compareTo` để so sánh giá trị số mà không vô tình phụ thuộc scale như `equals()`.

Các test nên bao gồm:

| Test | Mục tiêu |
| --- | --- |
| SELECT một VARCHAR | Trả scalar String, không cast Object[] |
| SELECT ba cột | Object[] có đúng số cột/thứ tự |
| BIGINT ID | Conversion không phụ thuộc cứng `Long` |
| COUNT | Trả số và không tràn với dữ liệu phù hợp |
| SUM DECIMAL | Giữ phần thập phân |
| SUM tập rỗng | Xử lý null đúng |
| TIMESTAMP nullable | Null được giữ, không gọi method trên null |
| LEFT JOIN | Các cột phía phải có thể null |
| JOIN nhiều hàng | Không hiểu nhầm row count là entity count |
| Constructor mapping | Alias/kiểu/constructor khớp |
| Native entity mapping | Cột cần thiết đủ để hydrate entity |
| SQL parameter | Không ghép input vào SQL |
| Pagination | Số hàng/ORDER BY ổn định |
| Không có hàng | `getResultList()` rỗng, `getSingleResult()` exception |
| Native bulk DML | Context có thể stale, transaction rõ |

Nếu test có thể chạy song song, dùng fixture ID/unique key riêng để tránh test nọ thay đổi kết quả test kia.

### Test nên kiểm tra kiểu runtime khi đổi driver

Trong giai đoạn migration, có thể ghi log **kiểu dữ liệu**, không ghi giá trị nhạy cảm:

```java
for (Object raw : rows) {
    if (raw instanceof Object[] columns) {
        for (int i = 0; i < columns.length; i++) {
            Object value = columns[i];

            log.debug(
                "native result column {} Java type: {}",
                i,
                value == null
                    ? "null"
                    : value.getClass().getName()
            );
        }
    }
}
```

Mục đích là kiểm tra contract provider sau nâng cấp. Không biến log này thành giải pháp production chạy trên mọi hàng của query lớn, và không ghi dữ liệu tài chính/cá nhân nhạy cảm vào log.

## 32. Kiểm thử mapping khi schema thay đổi

Một thay đổi:

```sql
ALTER TABLE books ADD COLUMN isbn VARCHAR(20);
```

không nhất thiết ảnh hưởng query được liệt kê tường minh:

```sql
SELECT id, title, price FROM books;
```

Nhưng nếu code dùng `SELECT *`, số cột hoặc thứ tự cột có thể thay đổi tùy DB/schema. Vì vậy khi migration:

1. Xác định native queries phụ thuộc bảng đã thay.
2. Kiểm tra chúng có `SELECT *` không.
3. Xác nhận alias và thứ tự cột trong SELECT.
4. Chạy test mapper từ SQL tới DTO.
5. Kiểm tra kiểu của aggregate/expressions nếu thêm CAST hoặc hàm.
6. Kiểm tra các nullability mới và default values.
7. Kiểm tra native query dùng `@SqlResultSetMapping` còn khớp alias.
8. Nếu query trả entity, kiểm tra đủ mapped fields cần thiết.

Điểm dễ sai nhất là **SQL vẫn chạy nhưng ý nghĩa của một index trong `Object[]` đã đổi**. Một test giá trị chính xác theo fixture giúp phát hiện lỗi mà test “không có exception” có thể bỏ qua.

## 33. Lưu ý về hiệu năng và bộ nhớ

Khi gọi:

```java
List<?> rows = em.createNativeQuery(
    "SELECT id, title, price FROM books"
).getResultList();
```

provider có thể materialize toàn bộ hàng trong memory. Nếu bảng có hàng triệu bản ghi, số lượng `Object[]` và đối tượng scalar rất lớn, dù không có managed entities.

Vì vậy:

- Dùng `WHERE` để giảm tập kết quả.
- Dùng `setMaxResults`/pagination khi chỉ cần một trang.
- Chỉ chọn các cột cần thiết thay vì `SELECT *`.
- Dùng SQL aggregate để COUNT/SUM thay vì tải mọi hàng về Java.
- Cân nhắc phân trang theo ID khi quét batch.
- Không tạo một List DTO khổng lồ sau khi vừa materialize một List Object[] khổng lồ nếu không cần.
- Với stream/cursor, đo memory và connection lifecycle trên provider thật.
- Giữ transaction đủ ngắn cho workload, tránh giữ JDBC cursor quá lâu.

So sánh chi phí:

```text
SELECT * → nhiều cột → nhiều object / byte truyền

SELECT id, title
WHERE published = true
ORDER BY id
LIMIT theo cơ chế provider
→ dữ liệu ít hơn, mapper đơn giản hơn
```

**Object[] có thể nhẹ hơn entity managed**, nhưng nó không làm một truy vấn không giới hạn trở nên miễn phí về bộ nhớ.

## 34. Lỗi thường gặp và cách khắc phục

### Lỗi 1: Ép scalar thành Object[]

```java
Object[] row = (Object[]) em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, id)
 .getSingleResult();
```

Query một cột thường trả String. Đọc scalar phù hợp hoặc khai báo result mapping rõ ràng.

### Lỗi 2: Ép nhiều cột thành String

```java
String title = (String) em.createNativeQuery(
    "SELECT id, title FROM books WHERE id = ?"
).setParameter(1, id)
 .getSingleResult();
```

Query nhiều cột thường trả `Object[]`. Phải lấy đúng index `row[1]` và convert theo contract.

### Lỗi 3: Tưởng mọi BIGINT thành Long

```java
Long id = (Long) row[0];
```

Có thể gặp `BigInteger`/`BigDecimal` hoặc loại Number khác. Dùng mapping và helper exact.

### Lỗi 4: Dùng `longValue()` cho giá tiền

```java
long price = ((Number) row[2]).longValue();
```

Làm mất phần lẻ như `275000.50`. Dùng BigDecimal đúng precision/scale.

### Lỗi 5: Đọc sai thứ tự cột

```sql
SELECT title, id, price FROM books;
```

nhưng mapper vẫn đọc `row[0]` là ID. Cần cố định SELECT và test shape.

### Lỗi 6: Không kiểm tra array length

Query thêm cột khiến mapper lấy index cũ. Kiểm tra contract số cột và ánh xạ qua DTO.

### Lỗi 7: Không xử lý null

`row[2].toString()` ném `NullPointerException` khi cột nullable. Thiết kế nullable fields rõ.

### Lỗi 8: Dùng `SUM` như `COUNT`

`SUM` tập rỗng trả null, còn `COUNT` thường trả 0. Xử lý theo aggregate semantics.

### Lỗi 9: Tưởng SQL alias trở thành Map key

`Object[]` vẫn đọc bằng index; muốn alias mapping dùng `@SqlResultSetMapping` hoặc API khác hỗ trợ.

### Lỗi 10: `SELECT *` trên query sống lâu

Schema migration có thể đổi số/thứ tự cột. Liệt kê tường minh fields.

### Lỗi 11: Trả Object[] qua HTTP

Client/app layer không biết mỗi index là gì. Map thành DTO có tên field trước.

### Lỗi 12: Tưởng sửa Object[] sẽ UPDATE database

`Object[]` không managed. Cần entity managed hoặc SQL UPDATE riêng.

### Lỗi 13: Không giới hạn query lớn

`getResultList()` có thể tiêu tốn nhiều memory. Dùng SQL filter, pagination, batch.

### Lỗi 14: SQL injection từ string concatenation

Dùng parameter binding cho values; whitelist identifiers và dynamic ORDER BY.

### Lỗi 15: Trộn native SQL UPDATE và managed entity mà không xét context

Context có thể stale sau bulk SQL. Dùng ranh giới flush/refresh/clear phù hợp.

### Lỗi 16: Cho rằng native query giống nhau trên mọi database

Dialect, aggregate numeric, timestamp, boolean, JSON, UUID và named parameter support có thể khác. Test trên provider/driver production.

## 35. Bài tập thực hành

### Bài 1: Đọc một cột

```java
Object row = em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, 101L)
 .getSingleResult();
```

**Câu hỏi:** Hình dạng thông thường của `row` là gì?

**Đáp án:** Một scalar, thường `String`. Không cast mặc định sang `Object[]`.

### Bài 2: Đọc ba cột

```sql
SELECT id, title, price FROM books;
```

**Câu hỏi:** Với Object[] thông thường, giá nằm ở đâu?

**Đáp án:** `row[2]`. `row[0]` là ID, `row[1]` là title. Cần chuyển kiểu phù hợp.

### Bài 3: BIGINT

Runtime value của `row[0]` là `BigInteger` nhưng code dùng:

```java
Long id = (Long) row[0];
```

**Câu hỏi:** Vì sao sai và sửa thế nào?

**Đáp án:** BigInteger không phải Long; phép cast ném ClassCastException. Dùng Number conversion có kiểm tra phạm vi hoặc mapping result column thành Long theo provider hỗ trợ.

### Bài 4: COUNT

```java
Object count = em.createNativeQuery(
    "SELECT COUNT(*) FROM books"
).getSingleResult();
```

**Câu hỏi:** Có nên luôn cast sang Long?

**Đáp án:** Không. Numeric Java type phụ thuộc provider/driver. Xử lý như Number hoặc mapping tường minh, cân nhắc overflow.

### Bài 5: SUM tập rỗng

```sql
SELECT SUM(price) FROM books WHERE category = 'UNKNOWN';
```

**Câu hỏi:** Kết quả có thể là gì?

**Đáp án:** Một scalar null. Nếu cần 0, xử lý ở Java hoặc dùng COALESCE với type mapping rõ.

### Bài 6: Cột nullable

```sql
SELECT id, published_at FROM books ORDER BY id;
```

**Câu hỏi:** Vì sao `((Timestamp) row[1]).toLocalDateTime()` có thể lỗi?

**Đáp án:** `published_at` có thể null, hoặc type Java không phải Timestamp. Cần xử lý null và kiểu runtime.

### Bài 7: Đổi thứ tự SELECT

Query đổi từ:

```sql
SELECT id, title, price FROM books;
```

thành:

```sql
SELECT price, title, id FROM books;
```

**Câu hỏi:** Mapper cũ có an toàn không?

**Đáp án:** Không. Vị trí `Object[]` đã đổi. Cập nhật mapper và integration test; tốt hơn giữ contract SELECT ổn định.

### Bài 8: Native JOIN

```sql
SELECT b.id, b.title, a.name
FROM books b JOIN authors a ON a.id = b.author_id;
```

**Câu hỏi:** Một Book có thể tạo nhiều Object[] khi JOIN collection không?

**Đáp án:** Có. Mỗi row phản ánh một kết quả SQL join; không tự đồng nhất row count với số Book entities duy nhất.

### Bài 9: Mapping DTO

**Yêu cầu:** Viết DTO cho `SELECT id, title, price`.

**Đáp án gợi ý:** Dùng `record BookRow(long id, String title, BigDecimal price)`, mapper kiểm tra array length và Number conversion trước khi tạo DTO.

### Bài 10: SqlResultSetMapping

**Câu hỏi:** `@ConstructorResult` giúp loại bỏ vấn đề nào?

**Đáp án:** Nó cho phép provider ánh xạ các scalar columns theo alias và khai báo type vào constructor DTO, giảm code index/cast thủ công. Vẫn cần test kiểu và constructor trên DB/provider thực tế.

### Bài 11: Transaction và stale data

Service sửa Book managed, sau đó chạy native scalar SELECT nhưng chưa flush.

**Câu hỏi:** Có thể có sự khác biệt giữa getter của Book và kết quả SQL không?

**Đáp án:** Có thể, tùy transaction/flush mode/provider. Nếu cần native SELECT đọc thay đổi pending một cách rõ ràng trong transaction, cân nhắc flush tường minh phù hợp.

### Bài 12: Không có kết quả

`getSingleResult()` trên query tìm theo ID không tồn tại.

**Câu hỏi:** Vì sao không nên giả định trả null?

**Đáp án:** Theo ngữ nghĩa thông dụng của JPA, nó ném `NoResultException`. Dùng `getResultList()` và kiểm tra rỗng, hoặc API result-or-null phù hợp với phiên bản nếu có.

### Bài 13: SQL injection

```java
String sql = "SELECT id FROM books WHERE category='" + input + "'";
```

**Câu hỏi:** Cách sửa?

**Đáp án:** Dùng placeholder và `setParameter`. Nếu cần dynamic ORDER BY, whitelist tên cột do ứng dụng định nghĩa, không ghép trực tiếp input.

### Bài 14: SELECT *

**Câu hỏi:** Vì sao `SELECT *` khó bảo trì khi Java đọc Object[]?

**Đáp án:** Code phụ thuộc số/thứ tự cột của schema. Khi thêm hoặc di chuyển cột, index có thể thay đổi. Chỉ định SELECT fields và test mapper.

### Bài 15: Object[] không cập nhật DB

```java
Object[] row = (Object[]) query.getSingleResult();
row[1] = "Tên mới";
```

**Câu hỏi:** Có SQL UPDATE tự động không?

**Đáp án:** Không. Đây chỉ là Java array; dirty checking áp dụng cho managed entities, không áp dụng cho Object[] thông thường.

## 36. Checklist khi đọc kết quả native SQL

Trước khi sử dụng một native query trả scalar hoặc Object[], hãy kiểm tra:

1. **SELECT có đúng một cột hay nhiều cột?** Hình dạng kết quả dự kiến là gì?
2. **Query có result class hoặc `@SqlResultSetMapping` không?** Nếu có, theo contract đó thay vì mặc định scalar/Object[].
3. **Số cột và thứ tự có được liệt kê tường minh không?** Tránh `SELECT *`.
4. **Tên alias có rõ và ổn định không?** Đặc biệt khi dùng `@ColumnResult`.
5. **Có kiểm tra `Object[]` length trước khi truy cập index không?**
6. **Kiểu numeric thực tế là gì?** Long/Integer/BigInteger/BigDecimal?
7. **Có cần exact integer conversion không?** ID, COUNT và số lượng lớn?
8. **Có dùng BigDecimal cho tiền không?** Tránh làm tròn/truncate bất ngờ.
9. **Cột hoặc aggregate có thể null không?** SUM, LEFT JOIN, published_at?
10. **DATE/TIMESTAMP có timezone semantics nào?** Cần convert theo chính sách nào?
11. **Boolean được trả bằng Boolean hay numeric flag?** Mapping có rõ không?
12. **Query có thể trả nhiều hàng cho cùng entity vì JOIN không?**
13. **Có dùng `getResultList()` khi chấp nhận 0–n hàng và `getSingleResult()` khi cần đúng một không?**
14. **Không có kết quả được xử lý thế nào?** Rỗng/exception/null aggregate?
15. **Object[] có được map thành DTO ngay tại repository không?**
16. **Query có phân trang và ORDER BY ổn định không?**
17. **Có bind parameter thay vì ghép input trực tiếp vào SQL không?**
18. **Dynamic sort/identifier có whitelist không?**
19. **Native query có phụ thuộc kiểu/dialect riêng DB không?** Có test trên DB production tương đương không?
20. **Có trộn native DML với managed entities không?** Cần kiểm soát stale context?
21. **Nếu dùng stream, đã đóng stream và quản lý EntityManager/transaction chưa?**
22. **DTO/native result có bị hiểu nhầm là managed entity không?**
23. **Schema migration có làm thay đổi shape/type/alias không?**
24. **Integration test có assert giá trị và kiểu runtime quan trọng không?**
25. **SQL có chỉ đọc những cột cần thiết, không vô tình lộ dữ liệu nhạy cảm không?**

Một repository native SQL đáng tin cậy là repository có **hợp đồng result shape và type conversion rõ ràng**, chứ không chỉ là repository có SQL chạy thành công.

## Kết luận

Khi dùng `EntityManager.createNativeQuery(...)` mà không khai báo result mapping đặc biệt, **truy vấn một cột thường trả các giá trị scalar, còn truy vấn nhiều cột thường trả mỗi hàng dưới dạng `Object[]` theo thứ tự SELECT**. Đây là quy ước quan trọng để đọc kết quả, nhưng không nên suy đoán cứng kiểu Java của từng scalar từ kiểu SQL mà chưa xét provider/JDBC driver.

Đối với cột số, hãy phân biệt `Number`, `Long`, `BigInteger` và `BigDecimal`; với tiền, tránh conversion làm mất precision. Đối với cột thời gian và nullable field, cần xử lý `null` và loại Java thực tế. Với query có nhiều cột, kiểm tra số lượng phần tử, giữ SELECT order ổn định và **map Object[] thành DTO sớm** để business code không phải biết từng index.

Khi kết quả phức tạp hoặc cần contract ổn định, có thể dùng `@SqlResultSetMapping`, `@ColumnResult` và `@ConstructorResult`, hoặc khai báo result class để nhận entity khi thực sự cần managed state. Native scalar/DTO result không tham gia dirty checking chỉ vì nó mang dữ liệu từ bảng entity.

Cuối cùng, hãy kiểm thử với database/provider thực tế: **hình dạng kết quả, kiểu runtime, nullability và SQL dialect là một phần của hợp đồng dữ liệu**. Bốn câu hỏi quan trọng nhất là **“SQL chọn bao nhiêu cột? Mỗi hàng được JPA trả dưới hình dạng nào? Mỗi cột có kiểu/nullable ra sao? Tầng nào chịu trách nhiệm chuyển nó thành DTO có ý nghĩa?”**. Trả lời được chúng sẽ giúp bạn làm việc với native SQL trong JPA an toàn, chính xác và dễ bảo trì.
