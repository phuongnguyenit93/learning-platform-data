# Dữ liệu biên, ký tự Unicode, null và quan hệ không hợp lệ

Trong nhóm **Dữ liệu kiểm thử** của module **Spring Boot - testing**, một test chỉ chạy với dữ liệu “bình thường” như `quantity=5`, `name="Book"` và một ID đã tồn tại sẽ khó bắt được lỗi ở ranh giới. Lỗi thực tế thường xuất hiện tại **giá trị min/max**, giá trị **ngay ngoài ngưỡng**, chuỗi Unicode có nhiều cách biểu diễn, trường JSON **thiếu/null/blank**, hoặc một **quan hệ tham chiếu đến bản ghi không tồn tại**. Những ca này liên quan đồng thời đến Jackson, Bean Validation, Java, SQL, transaction và response contract.

Ví dụ: API tạo đơn hàng nhận `customerId`, `label`, `note` và `quantity`. Ứng dụng yêu cầu:

- `customerId` bắt buộc và phải trỏ tới một khách hàng tồn tại.
- `label` bắt buộc, không được chỉ toàn khoảng trắng và dài **tối đa 24 đơn vị UTF-16 theo Bean Validation**.
- `note` là tùy chọn, có thể `null`, nhưng nếu có thì dài tối đa 100 đơn vị UTF-16.
- `quantity` là số nguyên bắt buộc, thuộc **[1, 100]**.
- SQL phải có **foreign key** để không chấp nhận một `customerId` mồ côi, ngay cả khi kiểm tra ở service bị bỏ qua hoặc có race condition.
- HTTP response không được làm mất/dổi ký tự Unicode ngoài ý muốn; lỗi input phải trả mã ổn định và không lộ SQL exception hoặc dữ liệu nhạy cảm.

Bài học kết hợp **bảng trường hợp kiểm thử**, **JUnit 5**, **Spring Boot 3.5 / Spring Framework 6.2**, **Java 17**, **Jackson 2**, **Bean Validation**, **MockMvc**, **JdbcTemplate** và **H2**. Các ví dụ có đủ source files để chạy trong project Gradle đã cấu hình Spring Boot; có chương trình Java SE độc lập với lệnh `javac/java` và stdout chính xác.

## 1. Dữ liệu biên là gì và vì sao phải kiểm thử?

Giá trị biên là dữ liệu nằm **ngay tại hoặc sát giới hạn** của một rule. Với `quantity` từ 1 đến 100:

| Giá trị | Ý nghĩa | Kỳ vọng |
| ---: | --- | --- |
| `null` | Thiếu giá trị bắt buộc | 400 / không ghi DB |
| `0` | Ngay dưới min | 400 / không ghi DB |
| `1` | Đúng min | Được nhận |
| `2` | Vừa trên min | Được nhận |
| `50` | Giữa miền hợp lệ | Được nhận |
| `99` | Vừa dưới max | Được nhận |
| `100` | Đúng max | Được nhận |
| `101` | Ngay trên max | 400 / không ghi DB |
| `"abc"` | Sai kiểu JSON | 400 / parse error |
| `2147483648` | Ngoài miền `Integer` | 400 / parse error trong cấu hình strict thông dụng |

Đây là **boundary value analysis** (BVA). Thay vì chọn ngẫu nhiên nhiều số cùng loại, cần chủ động kiểm tra **min−1, min, min+1, max−1, max, max+1** cùng null/type mismatch. Với rule phức tạp, bổ sung **equivalence partitioning**: nhóm hợp lệ, quá nhỏ, quá lớn, sai kiểu, bị thiếu, và dữ liệu bị database từ chối.

**Một ngưỡng có thể tồn tại ở nhiều tầng**:

```text
Client JSON
  |
  v
Jackson deserialization
  |
  v
Bean Validation (@NotNull/@Min/@Max/@Size)
  |
  v
Service business rules
  |
  v
JdbcTemplate (parameterized SQL)
  |
  v
Database (NOT NULL / CHECK / UNIQUE / FOREIGN KEY)
```

Test phải nói rõ **lớp bảo vệ nào** đang được xác minh. Một response HTTP 400 chứng minh request bị từ chối, nhưng **không tự chứng minh CHECK constraint trong database tồn tại**. Một test ném `DataIntegrityViolationException` khi chạy JDBC trực tiếp chứng minh DB có từ chối dữ liệu, nhưng không tự chứng minh controller chuyển nó thành error JSON an toàn.

## 2. Thiết kế test matrix trước khi viết code

Với DTO tạo đơn hàng, nên có một matrix như sau:

| Nhóm | Input | Kỳ vọng ở HTTP | Kỳ vọng ở DB |
| --- | --- | --- | --- |
| Happy path | Customer có thật, label hợp lệ, quantity 1 | 201 + dữ liệu khớp | 1 order |
| Biên số | Quantity 100 | 201 | 1 order |
| Ngoài biên | Quantity 0 hoặc 101 | 400 | Không thêm row |
| Null số | `"quantity":null` | 400 | Không thêm row |
| Thiếu số | Không có key `quantity` | 400 | Không thêm row |
| Unicode | `"Cà phê 😀 é"` | 201 + round-trip đúng | Giá trị giữ nguyên theo policy |
| Label chỉ có khoảng trắng | `"label":"   "` | 400 | Không thêm row |
| Label null | `"label":null` | 400 | Không thêm row |
| Label quá dài | 13 emoji `😀` với limit 24 UTF-16 units | 400 | Không thêm row |
| Label sát ngưỡng | 12 emoji `😀` | 201 | 1 order |
| Note null | `"note":null` | 201 | SQL NULL |
| Note thiếu | Không có key `note` | 201 nếu contract cho phép | SQL NULL |
| Note quá dài | 101 ký tự ASCII | 400 | Không thêm row |
| Quan hệ sai | `customerId=999` chưa tồn tại | 422 trong policy ví dụ | Không thêm order |
| Bỏ qua validation service | JDBC INSERT với FK sai | Không thuộc HTTP test | DB ném DataIntegrityViolationException |
| Dữ liệu SQL lỗi | `quantity=0` qua JDBC trực tiếp | Không thuộc HTTP test | DB CHECK chặn |
| JSON malformed | JSON bị thiếu dấu ngoặc hoặc sai kiểu | 400 với mã an toàn | Không thêm row |

Con số 400/422/409 là **hợp đồng của ứng dụng minh họa**, không phải quy tắc chung cho mọi REST API. Một hệ thống khác có thể chọn 400 cho foreign key reference không hợp lệ; cần test theo API contract được công bố, thay vì đoán response code của framework.

**Nguyên tắc kiểm tra:** có cả *positive assertions* (các trường hợp hợp lệ được nhận) và *negative assertions* (các trường hợp không hợp lệ bị từ chối). Chỉ viết negative tests rất dễ “xanh giả” nếu endpoint trả lỗi cho mọi request; chỉ viết happy-path tests bỏ sót lỗ hổng validation.

## 3. Phân biệt missing, null, empty, blank và zero

Một request JSON có thể mang nhiều trạng thái khác nhau:

```json
{}
```

```json
{"quantity": null}
```

```json
{"quantity": 0}
```

```json
{"label": ""}
```

```json
{"label": "   "}
```

**Không coi chúng tương đương**:

- **Missing:** JSON object **không có key**. Với record constructor của Jackson và reference type `Integer`, một trường missing thường được điền `null` trong cấu hình mặc định. Nếu API cần phân biệt missing và explicit null, phải thiết kế presence-aware DTO/custom deserialization, không suy ra từ Java object sau bind.
- **Explicit null:** key có mặt với JSON value `null`. Sau bind vào `Integer` thường thành Java `null`.
- **Zero:** là một số hợp lệ về mặt kiểu, nhưng bị `@Min(1)` từ chối theo nghiệp vụ.
- **Empty string `""`:** có độ dài 0, `@NotBlank` từ chối.
- **Blank string `"   "`:** có độ dài lớn hơn 0 nhưng không có ký tự nhìn thấy theo bộ quy tắc blank của validator; `@NotBlank` từ chối.
- **Whitespace Unicode:** không phải mọi code point nhìn như khoảng trắng đều có cùng semantics với `String.trim()`, `String.isBlank()` hoặc thư viện validation. Đặc biệt **NBSP U+00A0** và các ký tự zero-width cần test riêng nếu policy yêu cầu cấm.

**Đừng dùng primitive `int quantity` nếu cần phân biệt null với zero.** Trong nhiều cấu hình Jackson, JSON null/missing cho primitive có thể trở thành mặc định `0`, gây mất thông tin. Dùng `Integer` kết hợp `@NotNull` và `@Min`/`@Max` để contract rõ hơn.

Một lưu ý về database: `VARCHAR NOT NULL` từ chối SQL NULL nhưng **không tự chặn empty string hoặc chuỗi toàn spaces** trong nhiều engine. Bean Validation và CHECK constraint có phạm vi khác nhau; không nhầm `NOT NULL` với `NOT BLANK`.

## 4. Unicode: code unit, code point và grapheme cluster

Java `String` là chuỗi **UTF-16 code units**. Phần lớn chữ tiếng Việt trong dạng dựng sẵn như `"ế"` có thể chiếm một `char`, nhưng emoji ngoài BMP thường cần **hai code units** (surrogate pair). Một ký tự người dùng nhìn thấy còn có thể được cấu thành từ **nhiều Unicode code points** như chữ + dấu kết hợp hoặc chuỗi emoji dùng zero-width joiner.

| Ví dụ | Biểu diễn | `String.length()` | `codePointCount(...)` | Người dùng có thể nhìn thấy |
| --- | --- | ---: | ---: | --- |
| `"A"` | U+0041 | 1 | 1 | 1 ký tự |
| `"😀"` | U+1F600 | 2 | 1 | 1 emoji |
| `"é"` | U+00E9 (dựng sẵn) | 1 | 1 | 1 chữ |
| `"e\u0301"` | U+0065 + U+0301 (dấu kết hợp) | 2 | 2 | 1 chữ |
| `"🇻🇳"` | Hai regional-indicator code points | 4 | 2 | 1 flag emoji |

**Lưu ý:** cột “người dùng nhìn thấy” là mô tả trực quan; cách grapheme cluster được phân đoạn còn phụ thuộc chuẩn Unicode và bộ render. Không dùng `length()` hay `codePointCount` như thuật toán đếm grapheme đầy đủ.

### @Size đếm cái gì?

Theo cách triển khai Bean Validation phổ biến (Hibernate Validator cho `CharSequence`), `@Size(max = 24)` kiểm tra **độ dài theo `CharSequence.length()`**, tức số **UTF-16 code units** với Java `String`:

- `"😀".repeat(12)` có `length() = 24` → nằm tại ngưỡng max 24.
- `"😀".repeat(13)` có `length() = 26` → vượt max 24.
- `"e\u0301"` có độ dài 2, dù trông gần giống `"é"` có độ dài 1.

Điều này quan trọng khi UX nói “tối đa 24 ký tự”: quy định cần rõ là **UTF-16 units**, Unicode code points, grapheme clusters hay bytes UTF-8. Nếu nghiệp vụ yêu cầu 24 *ký tự người dùng nhìn thấy*, chỉ `@Size(max=24)` **không đủ**; cần custom validator sử dụng thuật toán grapheme thích hợp và test các chuỗi có combining marks/ZWJ.

**Giới hạn database cũng có thể khác:** một DB có thể tính `VARCHAR(n)` theo code points/characters thay vì Java UTF-16 code units. H2, PostgreSQL, MySQL có khác biệt về collation, normalization, byte length và character length. Test H2 xanh **không chứng minh** PostgreSQL sẽ so sánh/giới hạn tương tự. Với contract nhạy cảm về Unicode, hãy kiểm tra engine production qua Testcontainers.

## 5. Unicode normalization: NFC và NFD

Hai chuỗi trông giống nhau có thể **khác nhau ở cấp code points**:

```java
String composed = "é";      // U+00E9
String decomposed = "e\u0301"; // U+0065 + U+0301
boolean rawEqual = composed.equals(decomposed);  // false
```

Nếu nghiệp vụ cần so sánh tương đương chuẩn Unicode, có thể dùng `java.text.Normalizer`:

```java
String left = Normalizer.normalize(
        composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
boolean normalizedEqual = left.equals(right);     // true
```

Đây là **snippet Java**, không phải chương trình độc lập; phần demo hoàn chỉnh ở mục 13 sẽ có các imports, lệnh chạy và stdout xác định.

**Không normalize vô điều kiện:** hợp đồng có thể yêu cầu giữ nguyên input để ký số, audit hoặc round-trip chính xác. Với tên tìm kiếm/người dùng, có thể cần normalization ở một boundary được công bố. Hãy chọn rõ một trong hai chính sách:

- **Giữ nguyên byte/sequence từ JSON → Java → DB → JSON** (sau khi UTF-8 decode/encode), test round-trip bằng `String.equals`.
- **Chuẩn hóa NFC trước khi lưu/so sánh**, test kết quả NFC ổn định và cân nhắc uniqueness/collation của database.

Không dùng `toLowerCase()` theo default locale để làm chuẩn hóa định danh; Unicode case folding, locale và confusables là vấn đề riêng, đặc biệt với tài khoản/username/email.

## 6. Xác định “quan hệ không hợp lệ”

Một Order có `customerId` trỏ tới Customer là một **quan hệ tham chiếu**. Trong SQL, cần foreign key:

```text
customers
  id (PRIMARY KEY)
  email (UNIQUE)
      |
      | 1-to-many
      v
purchase_orders
  id (PRIMARY KEY)
  customer_id (FOREIGN KEY -> customers.id)
  label, note, quantity
```

Các ca quan hệ nên kiểm tra:

1. **Khóa cha không tồn tại:** `customer_id=999` → không được tạo Order mồ côi.
2. **Khóa cha null:** cột `customer_id NOT NULL` → không được thêm.
3. **Xóa cha khi con còn tham chiếu:** với FK mặc định không cascade, DELETE parent phải bị chặn.
4. **Khóa cha vừa bị xóa bởi transaction khác:** service kiểm tra “có tồn tại” rồi INSERT có thể gặp **race**; FK trong DB vẫn là phòng tuyến quyết định.
5. **Gán sai chủ sở hữu:** một Order hợp lệ về FK nhưng thuộc Customer khác vẫn có thể vi phạm authorization; FK **không** giải quyết quyền truy cập.
6. **Nhiều quan hệ trùng:** nếu domain yêu cầu uniqueness trên pair, cần UNIQUE/composite key hoặc policy riêng; FK không tự cấm hai Order cùng customer.
7. **Cạnh/cycle trong graph:** nếu model là cây hoặc DAG, DB FK đơn giản không tự cấm vòng; cần validation, constraints hoặc transaction logic phù hợp và test riêng.

Một service-level check như `customerStore.existsById(id)` giúp đưa lỗi business dễ hiểu (422), nhưng **không thay thế foreign key**: giữa SELECT và INSERT có thể phát sinh concurrent delete. Việc có cả hai lớp tạo “defense in depth”.

## 7. Ví dụ Spring Boot 3.5/Java 17 hoàn chỉnh

Ta sẽ dùng **Spring MVC + Bean Validation + JDBC + H2**. Không cần JPA để chứng minh foreign key, null và CHECK constraint; `JdbcTemplate` giúp nhìn rõ SQL side effects.

Cấu trúc files:

```text
src/
├── main/java/example/testing/boundaries/
│   ├── BoundaryApplication.java
│   ├── CreateOrderRequest.java
│   ├── OrderView.java
│   ├── CustomerStore.java
│   ├── OrderStore.java
│   ├── OrderService.java
│   ├── OrderController.java
│   ├── ErrorAdvice.java
│   └── UnicodeBoundaryDemo.java
└── test/
    ├── java/example/testing/boundaries/
    │   ├── OrderHttpContractTest.java
    │   └── UnicodeBoundaryTest.java
    └── resources/schema.sql
```

**Phạm vi test**: `OrderHttpContractTest` khởi động Spring Boot test context với MockMvc **đồng bộ** và H2 nhúng, transaction được rollback sau mỗi method. Đây **không phải** HTTP qua cổng thật và không phải Testcontainers production DB. Nó chứng minh validation/JSON/JDBC/SQL schema trong môi trường nêu rõ.

### 7.1. Gradle dependencies

Trong project Gradle đã có Spring Boot plugin, repositories và Java toolchain 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn này **bổ sung vào `build.gradle` có sẵn**, không phải toàn bộ Gradle build từ đầu. Spring Boot 3.5 quản lý các versions của Spring Framework, Jakarta Validation, Hibernate Validator, Jackson và H2 qua BOM. Khi dùng Boot 4.x, kiểm tra lại packages/modules và behavior version hiện hành.

Nếu project có Flyway/Liquibase và `schema.sql` cùng tạo bảng, tránh khởi tạo chồng chéo. Nếu chạy trên database không nhúng, Spring SQL initializer có thể cần `spring.sql.init.mode=always` hoặc dùng migration phù hợp.

### 7.2. Spring Boot application: BoundaryApplication.java

Tạo `src/main/java/example/testing/boundaries/BoundaryApplication.java`:

```java
package example.testing.boundaries;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

Package thống nhất cho controller/service/repository. Trong test, Boot tìm class `@SpringBootApplication` này để dựng context. Khi chạy `main()` ngoài test, cần cấu hình database/migrations production; H2 ở `testRuntimeOnly` không tự xuất hiện ở runtime production.

### 7.3. schema.sql: constraints thật ở database

Tạo `src/test/resources/schema.sql`:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    label VARCHAR(24) NOT NULL,
    note VARCHAR(100),
    quantity INTEGER NOT NULL CHECK (
        quantity >= 1 AND quantity <= 100
    ),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

H2 2.x hỗ trợ cú pháp identity, CHECK và FOREIGN KEY này trong cấu hình test thông dụng.

**Ý nghĩa các constraint:**

- `customers.id PRIMARY KEY`: một khách hàng có ID duy nhất.
- `email UNIQUE NOT NULL`: không cho email null/trùng theo collation của engine; các quy tắc email thực cần validation riêng.
- `purchase_orders.customer_id NOT NULL + FOREIGN KEY`: order bắt buộc tham chiếu một customer tồn tại.
- `quantity INTEGER NOT NULL CHECK 1..100`: DB tự từ chối quantity null, 0, 101 dù bypass controller.
- `label VARCHAR(24) NOT NULL`: chặn null và một phần tình huống quá dài ở DB; **không tự chặn blank**.
- `note VARCHAR(100)`: cho phép SQL NULL; Jackson/validation phải quyết định cách nhận missing/null ở HTTP.

**Không khai báo `ON DELETE CASCADE`:** vì vậy H2 chặn xóa Customer đang được Order tham chiếu. Nếu hợp đồng của bạn muốn cascade, cần thay DDL và test kết quả xóa con rõ ràng; không dựa vào giả định database tự chọn hành vi.

## 8. Source files: request DTO, response và repository

### 8.1. CreateOrderRequest.java

Tạo `src/main/java/example/testing/boundaries/CreateOrderRequest.java`:

```java
package example.testing.boundaries;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotNull Long customerId,

        @NotBlank
        @Size(max = 24)
        String label,

        @Size(max = 100)
        String note,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity) {
}
```

**Các annotation có vai trò khác nhau:**

- `@NotNull` bắt trường có giá trị, không kiểm tra ID tồn tại trong database.
- `@NotBlank` từ chối null, empty và chuỗi blank cho `CharSequence`; không phải một bộ lọc mọi Unicode invisible code point.
- `@Size` của `CharSequence` mặc định **cho phép null**. Nếu field là required, phối hợp `@NotNull`/`@NotBlank`.
- `@Min/@Max` kiểm tra miền số; để kiểm tra null phải có `@NotNull`.
- `Integer` thay vì `int` giữ được trạng thái null từ Jackson binding.

Với cách này, `note=null` được cho phép **một cách có chủ đích**. Không tự biến null thành chuỗi `"null"` hay một chuỗi rỗng khi lưu.

### 8.2. OrderView.java

Tạo `src/main/java/example/testing/boundaries/OrderView.java`:

```java
package example.testing.boundaries;

public record OrderView(
        Long id,
        Long customerId,
        String label,
        String note,
        Integer quantity) {
}
```

Đây là response DTO riêng. Nếu sau này một SQL entity có internal metadata, không nên trả thẳng nó trong HTTP response. `note=null` sẽ được Jackson serialize thành JSON `null` trong cấu hình mặc định của Boot 3.5, trừ khi ứng dụng tùy chỉnh null inclusion. Test sẽ làm rõ response contract cụ thể của ví dụ.

### 8.3. CustomerStore.java

Tạo `src/main/java/example/testing/boundaries/CustomerStore.java`:

```java
package example.testing.boundaries;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerStore {
    private final JdbcTemplate jdbc;

    public CustomerStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean existsById(long id) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customers WHERE id = ?",
                Integer.class, id);
        return count != null && count > 0;
    }
}
```

Dùng SQL parameter `?` thay vì ghép input vào query string. `COUNT(*)` là đọc dữ liệu thật trong DB connection/transaction đang chạy, nhưng vẫn có race giữa việc check và insert; foreign key phải tiếp tục bảo vệ.

### 8.4. OrderStore.java

Tạo `src/main/java/example/testing/boundaries/OrderStore.java`:

```java
package example.testing.boundaries;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcInsert;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {
    private final JdbcTemplate jdbc;
    private final SimpleJdbcInsert inserter;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        this.inserter = new SimpleJdbcInsert(jdbc)
                .withTableName("purchase_orders")
                .usingColumns(
                        "customer_id", "label",
                        "note", "quantity")
                .usingGeneratedKeyColumns("id");
    }

    public long insert(CreateOrderRequest input) {
        Number key = inserter.executeAndReturnKey(
                new MapSqlParameterSource()
                        .addValue("customer_id", input.customerId())
                        .addValue("label", input.label())
                        .addValue("note", input.note())
                        .addValue("quantity", input.quantity()));
        return key.longValue();
    }

    public OrderView findById(long id) {
        return jdbc.queryForObject(
                """
                SELECT id, customer_id, label, note, quantity
                FROM purchase_orders
                WHERE id = ?
                """,
                (rs, rowNum) -> new OrderView(
                        rs.getLong("id"),
                        rs.getLong("customer_id"),
                        rs.getString("label"),
                        rs.getString("note"),
                        rs.getInt("quantity")),
                id);
    }

    public int countForCustomer(long customerId) {
        Integer count = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM purchase_orders
                WHERE customer_id = ?
                """,
                Integer.class, customerId);
        return count == null ? 0 : count;
    }
}
```

`SimpleJdbcInsert` tạo prepared INSERT và trả generated identity key. `MapSqlParameterSource` hỗ trợ giá trị null của `note`. `findById` đọc **row đã lưu trong database** thay vì lặp lại object input, giúp test nhận ra lỗi encoding/mapping.

Với `JdbcTemplate` và H2, SQL constraint violation thường được Spring dịch thành `DataIntegrityViolationException`; code production có thể translate theo constraint name/SQL state được kiểm soát. **Không giả định mọi constraint failure có cùng HTTP status hoặc exception subclass trên mọi driver/database**.

## 9. Source files: service, controller và error mapping

### 9.1. OrderService.java

Tạo `src/main/java/example/testing/boundaries/OrderService.java`:

```java
package example.testing.boundaries;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final CustomerStore customers;
    private final OrderStore orders;

    public OrderService(
            CustomerStore customers, OrderStore orders) {
        this.customers = customers;
        this.orders = orders;
    }

    @Transactional
    public OrderView create(CreateOrderRequest input) {
        if (!customers.existsById(input.customerId())) {
            throw new CustomerNotFoundException();
        }

        long id = orders.insert(input);
        return orders.findById(id);
    }
}

final class CustomerNotFoundException
        extends RuntimeException {
    CustomerNotFoundException() {
        super("Unknown customer");
    }
}
```

Service kiểm tra customer tồn tại để trả lỗi business dễ hiểu. Tuy nhiên, **SELECT rồi INSERT không phải một phép toán atomic về relation** nếu transaction khác xóa customer trong khoảng giữa; foreign key vẫn là lớp phòng vệ cuối.

`@Transactional` đặt trên Spring-managed service bảo đảm các bước check/insert/read thuộc một application transaction (nếu được gọi qua proxy và manager được cấu hình). Trong MockMvc test đồng bộ có `@Transactional` trên JUnit method, service với propagation mặc định `REQUIRED` tham gia **test transaction** và rollback cuối method.

**Không gọi `new OrderService(...)` trong HTTP test** rồi kết luận AOP/DB transaction đang được kiểm thử; cần lấy bean từ Spring context khi muốn test proxy thực.

### 9.2. OrderController.java

Tạo `src/main/java/example/testing/boundaries/OrderController.java`:

```java
package example.testing.boundaries;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest input) {
        OrderView created = service.create(input);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }
}
```

`@Valid` kích hoạt Bean Validation cho request body khi MVC bind thành record. Nếu vi phạm `@NotNull`, `@NotBlank`, `@Min`, `@Max` hoặc `@Size`, Spring MVC thường ném `MethodArgumentNotValidException` để advice xử lý.

**Không quên `spring-boot-starter-validation`:** nếu thiếu provider Jakarta Validation, annotation có thể không được áp dụng như bạn tưởng. Test HTTP invalid cases là cách phát hiện cấu hình validation không hoạt động.

### 9.3. ErrorAdvice.java

Tạo `src/main/java/example/testing/boundaries/ErrorAdvice.java`:

```java
package example.testing.boundaries;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorBody invalidFields(
            MethodArgumentNotValidException exception) {
        return new ErrorBody("INVALID_ORDER");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorBody malformedJson(
            HttpMessageNotReadableException exception) {
        return new ErrorBody("MALFORMED_JSON");
    }

    @ExceptionHandler(CustomerNotFoundException.class)
    @ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
    public ErrorBody unknownCustomer(
            CustomerNotFoundException exception) {
        return new ErrorBody("CUSTOMER_NOT_FOUND");
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    public ErrorBody dataConstraintViolation(
            DataIntegrityViolationException exception) {
        return new ErrorBody("DATA_CONSTRAINT_VIOLATION");
    }

    public record ErrorBody(String code) {
    }
}
```

**Vì sao không trả `exception.getMessage()`?** JDBC/validation exceptions có thể chứa dữ liệu người dùng, SQL statement, tên constraint, connection properties hoặc stacktrace. Ví dụ trả các **mã lỗi public cố định**. Với ứng dụng thật, cần error taxonomy, correlation ID, logging/masking, permission và i18n phù hợp.

422 cho customer không tồn tại và 409 cho DB constraint là **policy minh họa**. Có hệ thống chọn 400/404/409 theo semantic khác. Quan trọng là chọn policy rõ và test nhất quán, không coi “foreign key always means HTTP 409” là luật của Spring.

**Phân biệt lỗi JSON:**

- `{"quantity":null}` → Jackson có thể bind được record với `quantity=null`; Bean Validation trả `INVALID_ORDER`.
- `{"quantity":"not-a-number"}` → Jackson không thể bind `Integer` theo cấu hình phù hợp; `HttpMessageNotReadableException` → `MALFORMED_JSON`.
- JSON syntax sai → cũng `MALFORMED_JSON`.
- Customer ID hợp lệ về kiểu nhưng **không tồn tại** → `CUSTOMER_NOT_FOUND`.
- DB constraint vi phạm do bypass service hoặc race → `DATA_CONSTRAINT_VIOLATION` khi đến HTTP boundary.

## 10. Bộ test HTTP/SQL hoàn chỉnh với MockMvc

Tạo `src/test/java/example/testing/boundaries/OrderHttpContractTest.java`:

```java
package example.testing.boundaries;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@Transactional
class OrderHttpContractTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ObjectMapper mapper;

    @BeforeEach
    void seedCustomer() {
        jdbc.update(
                "INSERT INTO customers(id,email) VALUES (?,?)",
                1L, "fixture@example.test");
    }

    private ResultActions postOrder(
            CreateOrderRequest input) throws Exception {
        return mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input)));
    }

    private ResultActions postRaw(String json)
            throws Exception {
        return mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json));
    }

    private int countOrders() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders",
                Integer.class);
        return count == null ? 0 : count;
    }

    @Test
    void quantityMinimumAndMaximumAreAccepted()
            throws Exception {
        postOrder(new CreateOrderRequest(
                1L, "minimum", null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.quantity").value(1));

        postOrder(new CreateOrderRequest(
                1L, "maximum", "note", 100))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.quantity").value(100));

        assertEquals(2, countOrders());
    }

    @Test
    void invalidQuantityNearBoundariesIsRejected()
            throws Exception {
        postOrder(new CreateOrderRequest(
                1L, "zero", null, 0))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        postOrder(new CreateOrderRequest(
                1L, "too-many", null, 101))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }

    @Test
    void explicitNullAndMissingQuantityAreRejected()
            throws Exception {
        postRaw("""
                {
                  "customerId":1,
                  "label":"null quantity",
                  "note":null,
                  "quantity":null
                }
                """)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        postRaw("""
                {
                  "customerId":1,
                  "label":"missing quantity",
                  "note":null
                }
                """)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }

    @Test
    void blankEmptyAndNullLabelsAreRejected()
            throws Exception {
        for (String value : List.of("", "   ", "\t")) {
            postOrder(new CreateOrderRequest(
                    1L, value, null, 1))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code")
                            .value("INVALID_ORDER"));
        }

        postOrder(new CreateOrderRequest(
                1L, null, null, 1))
                .andExpect(status().isBadRequest());

        assertEquals(0, countOrders());
    }

    @Test
    void unicodeRoundTripsThroughJsonAndJdbc()
            throws Exception {
        String label = "Cà phê 😀 e\u0301";

        String json = postOrder(new CreateOrderRequest(
                1L, label, "Ghi chú Việt", 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.label").value(label))
                .andExpect(jsonPath("$.note")
                        .value("Ghi chú Việt"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode body = mapper.readTree(json);
        Long id = body.path("id").longValue();
        assertTrue(id > 0L);

        String fromDb = jdbc.queryForObject(
                "SELECT label FROM purchase_orders WHERE id = ?",
                String.class, id);

        assertEquals(label, fromDb);
        assertEquals(1, countOrders());
    }

    @Test
    void emojiBoundaryUsesUtf16Units()
            throws Exception {
        String exactly24Units = "😀".repeat(12);
        String tooLong26Units = "😀".repeat(13);

        assertEquals(24, exactly24Units.length());
        assertEquals(26, tooLong26Units.length());

        postOrder(new CreateOrderRequest(
                1L, exactly24Units, null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.label")
                        .value(exactly24Units));

        postOrder(new CreateOrderRequest(
                1L, tooLong26Units, null, 1))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(1, countOrders());
    }

    @Test
    void nullNoteIsAcceptedAndStoredAsSqlNull()
            throws Exception {
        String json = postOrder(new CreateOrderRequest(
                1L, "nullable note", null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.note").value(nullValue()))
                .andReturn()
                .getResponse()
                .getContentAsString();

        long id = mapper.readTree(json).path("id").asLong();

        String fromDb = jdbc.queryForObject(
                "SELECT note FROM purchase_orders WHERE id = ?",
                String.class, id);

        assertEquals(null, fromDb);
    }

    @Test
    void missingOptionalNoteAlsoMapsToNull()
            throws Exception {
        String json = postRaw("""
                {"customerId":1,"label":"note omitted",
                 "quantity":1}
                """)
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.note").value(nullValue()))
                .andReturn()
                .getResponse()
                .getContentAsString();

        long id = mapper.readTree(json).path("id").asLong();
        String note = jdbc.queryForObject(
                "SELECT note FROM purchase_orders WHERE id = ?",
                String.class, id);

        assertEquals(null, note);
    }

    @Test
    void noteBeyondMaxLengthIsRejected()
            throws Exception {
        postOrder(new CreateOrderRequest(
                1L, "note overflow", "x".repeat(101), 1))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }

    @Test
    void nonexistentCustomerIsAControlledBusinessError()
            throws Exception {
        postOrder(new CreateOrderRequest(
                999L, "orphan", null, 1))
                .andExpect(status().is(422))
                .andExpect(jsonPath("$.code")
                        .value("CUSTOMER_NOT_FOUND"));

        assertEquals(0, countOrders());
    }

    @Test
    void foreignKeyRejectsOrphanEvenWithoutServiceCheck() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        """
                        INSERT INTO purchase_orders
                            (customer_id, label, note, quantity)
                        VALUES (?, ?, ?, ?)
                        """,
                        999L, "orphan", null, 1));

        assertEquals(0, countOrders());
    }

    @Test
    void referencedCustomerCannotBeDeleted() {
        jdbc.update(
                """
                INSERT INTO purchase_orders
                    (customer_id, label, note, quantity)
                VALUES (?, ?, ?, ?)
                """,
                1L, "linked", null, 1);

        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "DELETE FROM customers WHERE id = ?",
                        1L));

        assertEquals(1, countOrders());
    }

    @Test
    void checkConstraintRejectsInvalidQuantityDirectly() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        """
                        INSERT INTO purchase_orders
                            (customer_id, label, note, quantity)
                        VALUES (?, ?, ?, ?)
                        """,
                        1L, "wrong quantity", null, 0));

        assertEquals(0, countOrders());
    }

    @Test
    void malformedJsonReturnsSafeErrorCode()
            throws Exception {
        postRaw("""
                {"customerId":1,"label":"broken",
                 "quantity":
                """)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_JSON"));

        assertEquals(0, countOrders());
    }

    @Test
    void apostrophesAndSqlMetacharactersAreData()
            throws Exception {
        String label = "O'Reilly; --";

        postOrder(new CreateOrderRequest(
                1L, label, null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.label").value(label));

        assertEquals(1, countOrders());
    }

    @Test
    void requiredCustomerIdCannotBeNull()
            throws Exception {
        postOrder(new CreateOrderRequest(
                null, "no parent", null, 1))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }
}
```

Đây là **16 test methods** trong một class JUnit. Không mock `JdbcTemplate`, `OrderStore` hay `OrderService`; mọi request chạy qua Spring MVC + Jackson + Bean Validation + service + JDBC và H2 thật trong test. Vì `MockMvc` chạy controller **đồng bộ** trên test thread và test được đánh dấu `@Transactional`, mỗi method tự rollback dữ liệu được tạo trong transaction ấy.

**Một số chi tiết về assertions:**

- `status().isCreated()` chứng minh request hợp lệ thực sự được xử lý; `jsonPath("$.label").value(label)` chứng minh response giữ nguyên Unicode theo chính sách hiện tại.
- `countOrders()` kiểm tra SQL row count để loại khả năng HTTP 400 nhưng database vẫn bị ghi.
- Test `unicodeRoundTripsThroughJsonAndJdbc` đọc **lại từ database** thay vì chỉ so response với input.
- Test `nullNote...` kiểm tra cả JSON `null` và SQL `NULL`. Nếu ứng dụng chuyển sang omit null fields bằng `@JsonInclude(NON_NULL)`, phải sửa contract và test phù hợp, không lặng lẽ bỏ assertion.
- Test với 12/13 emoji dựa vào `@Size(max=24)` và `String.length()`, không tuyên bố đó là 24 grapheme clusters.
- Test foreign key/check constraint chạy JDBC **trực tiếp** nhằm chứng minh DB tự từ chối input; test business error 422 xác minh service-level validation khác.
- Test xóa parent xác nhận **không có ON DELETE CASCADE** theo schema; nếu production chọn cascade, ca test phải phản ánh policy đó.
- Chuỗi `O'Reilly; --` phải được lưu **như dữ liệu** vì JDBC dùng parameters, không bị hiểu là câu SQL. Đây chỉ là một regression check, không thay thế review toàn bộ query-building code.

**Quan trọng:** `@Transactional` trên JUnit test với MockMvc **đồng bộ** không giống test HTTP thật qua `RANDOM_PORT`. Trong HTTP thật, server xử lý request ở thread/transaction riêng; việc ghi DB có thể **commit và không bị rollback** bởi transaction của test client. Nếu chuyển các test này sang HTTP socket thật, phải quản lý cleanup theo database riêng/transaction độc lập.

## 11. Unit test Unicode và các trường hợp không cần Spring context

Một vài thuộc tính có thể kiểm tra bằng Java/JUnit thuần, nhanh hơn nhiều so với khởi động Spring.

Tạo `src/test/java/example/testing/boundaries/UnicodeBoundaryTest.java`:

```java
package example.testing.boundaries;

import java.text.Normalizer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UnicodeBoundaryTest {

    @Test
    void emojiLengthDiffersFromCodePointCount() {
        String emoji = "😀";
        assertEquals(2, emoji.length());
        assertEquals(
                1,
                emoji.codePointCount(0, emoji.length()));
    }

    @Test
    void canonicallyEquivalentStringsAreNotRawEqual() {
        String nfcLike = "é";
        String nfdLike = "e\u0301";

        assertFalse(nfcLike.equals(nfdLike));

        assertEquals(
                Normalizer.normalize(
                        nfcLike, Normalizer.Form.NFC),
                Normalizer.normalize(
                        nfdLike, Normalizer.Form.NFC));
    }

    @Test
    void blankAndEmptyAreDifferentProperties() {
        assertTrue("".isEmpty());
        assertTrue("".isBlank());

        assertFalse("   ".isEmpty());
        assertTrue("   ".isBlank());
    }
}
```

Ba test này minh họa Java `String`/`Normalizer`; **không chứng minh** Jackson, Bean Validation hoặc DB có cùng policy. Những behavior đó được kiểm tra ở `OrderHttpContractTest`. Tránh gom tất cả logic vào `@SpringBootTest` nếu Java thuần đã đủ để kiểm tra một thuật toán.

## 12. Chạy các test và phạm vi kết quả

Từ root project có Gradle wrapper:

```bash
./gradlew test --tests example.testing.boundaries.UnicodeBoundaryTest
./gradlew test --tests example.testing.boundaries.OrderHttpContractTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.boundaries.UnicodeBoundaryTest"
.\gradlew.bat test --tests "example.testing.boundaries.OrderHttpContractTest"
```

**Kỳ vọng trong môi trường được cấu hình đúng:**

- `UnicodeBoundaryTest`: **3 JUnit methods** kiểm tra UTF-16, Unicode normalization và blank/empty.
- `OrderHttpContractTest`: **16 JUnit methods** kiểm tra các case HTTP + JDBC + H2.
- Tổng cộng **19 test methods**, nếu test class và schema đúng như các files đã cung cấp.

Đầu ra console Gradle/JUnit phụ thuộc phiên bản và cấu hình reporter; không có chuỗi stdout duy nhất cho `gradlew test`. Để xem failure chính xác, đọc test report do Gradle tạo ra và stacktrace của test method tương ứng.

**Đây là MockMvc + H2 integration test**, không phải API test qua port thật. Nếu chuyển sang `@SpringBootTest(webEnvironment = RANDOM_PORT)` thì test-managed `@Transactional` không rollback các transaction server; cần chiến lược database isolation/cleanup riêng. Với PostgreSQL/MySQL production, chạy thêm Testcontainers tests cho dialect, encoding, constraints và collation.

## 13. Chương trình Java 17 độc lập: UnicodeBoundaryDemo.java

Tạo `src/main/java/example/testing/boundaries/UnicodeBoundaryDemo.java`:

```java
package example.testing.boundaries;

import java.text.Normalizer;

public class UnicodeBoundaryDemo {
    public static void main(String[] args) {
        String emoji = "😀";
        String composed = "é";
        String decomposed = "e\u0301";

        System.out.println(
                "emoji.utf16=" + emoji.length());
        System.out.println(
                "emoji.codePoints="
                        + emoji.codePointCount(
                                0, emoji.length()));
        System.out.println(
                "sameRaw=" + composed.equals(decomposed));
        System.out.println(
                "sameNFC=" + Normalizer.normalize(
                        composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));
        System.out.println(
                "blank=" + " \t\n".isBlank());
    }
}
```

Chạy bằng **JDK 17+** mà không cần Spring, Gradle, JDBC hoặc JUnit:

```bash
javac -encoding UTF-8 -d out src/main/java/example/testing/boundaries/UnicodeBoundaryDemo.java
java -cp out example.testing.boundaries.UnicodeBoundaryDemo
```

Stdout **chính xác** nếu file được lưu bằng UTF-8 và JDK đọc nguồn đúng encoding:

```text
emoji.utf16=2
emoji.codePoints=1
sameRaw=false
sameNFC=true
blank=true
```

**Vì sao in output như vậy?** Emoji `😀` nằm ngoài Basic Multilingual Plane và có hai surrogate code units, nhưng là một code point. `"é"` (U+00E9) khác `"e\u0301"` (U+0065 + combining acute accent) trong raw Java `String.equals`; sau NFC normalization chúng tương đương. Chuỗi chỉ chứa dấu cách, tab và newline được `String.isBlank()` xem là blank.

**Giới hạn:** demo không kiểm chứng cách JDBC driver lưu text hay cách H2 so sánh Unicode. Muốn chứng minh round-trip qua database, phải chạy `unicodeRoundTripsThroughJsonAndJdbc`. Muốn chứng minh cách người dùng nhận diện grapheme cluster, cần thuật toán segmentation có chủ đích và test emoji combining/ZWJ tương ứng.

## 14. Bài kiểm thử nâng cao: bảng quyết định và property-based tests

Khi miền input lớn, không thể viết một test cho mọi chuỗi hoặc ID. Cần kết hợp **boundary cases** được lựa chọn thủ công và **property-based testing** hoặc fuzzing có giới hạn.

### 14.1. Bảng quyết định cho một request

Đặt ba biến:

- `Q`: quantity trong [1,100]?
- `L`: label không blank và length ≤24?
- `C`: customerId tồn tại?

| Q | L | C | Kỳ vọng |
| --- | --- | --- | --- |
| true | true | true | 201 + một row |
| false | true | true | 400; DB không đổi |
| true | false | true | 400; DB không đổi |
| true | true | false | 422; DB không đổi |
| false | false | false | 400; validation chặn trước service |

**Không nhất thiết kiểm tra toàn bộ 2³ tổ hợp** khi các điều kiện độc lập và cost cao; có thể dùng pairwise/decision coverage, nhưng phải giữ những case có tương tác quan trọng. Nếu nhiều constraint cùng fail, API có thể trả một error chung hoặc danh sách field errors; test theo contract, không dựa vào thứ tự lỗi validator không bảo đảm.

### 14.2. Property-based invariants

Một số thuộc tính có thể phát biểu độc lập với input cụ thể:

1. Với mọi `quantity` hợp lệ, DB ghi đúng số đó và response trả lại giá trị ấy.
2. Với mọi `quantity < 1` hoặc `quantity > 100`, không có row mới.
3. Với mọi `label` Unicode hợp lệ theo policy, JSON/DB round-trip **không đổi** hoặc được normalize theo chính sách công bố.
4. Với mọi `customerId` không tồn tại, không được có Order mồ côi.
5. Với mọi input bị reject, không có side effect DB.
6. Không có quan hệ child → parent “dangling” sau các transaction thành công.

Có thể dùng một thư viện như jqwik/QuickTheories để tạo dữ liệu, nhưng cần kiểm soát **seed**, replay/shrinking, thời gian test, kích thước input và database cleanup. **Không dùng random không có seed** làm test flaky khó tái hiện.

### 14.3. Unicode adversarial cases

Các case nên cân nhắc theo contract:

- Chữ Việt dạng dựng sẵn và decomposed: `"á"` vs `"a\u0301"`.
- Emoji ngoài BMP: `😀`.
- Emoji với skin tone modifier, ZWJ sequence: một hình nhìn thấy nhiều code points.
- Zero-width joiner U+200D, zero-width space U+200B.
- NBSP U+00A0, thin spaces, line breaks, tab.
- Cặp surrogate không hợp lệ (nếu input đi qua Java layer không được UTF-8 decoder/JSON serializer kiểm soát).
- Chuỗi chứa dấu nháy đơn, dấu ngoặc, `&`, `<`, `>` và ký tự escape.
- Chuỗi rất dài để kiểm tra giới hạn request body/validation/performance.

Khi test một Unicode case, hãy ghi rõ **nguyên tắc mong đợi** (được nhận, normalize, reject, hoặc preserve). Không ép tất cả ký tự lạ thành “không hợp lệ”; nhiều ngôn ngữ hợp pháp cần combining marks và symbols.

## 15. Quan hệ không hợp lệ vượt ngoài foreign key

Trong ví dụ Order → Customer, FK bảo đảm existence của parent nhưng không giải quyết mọi invariant:

**Sai quyền sở hữu:** user A gửi `customerId` của user B. FK vẫn hợp lệ vì customer tồn tại; ứng dụng phải xác minh principal/ownership/authorization trước khi tạo Order. Test HTTP cần chạy nhiều security principals và chứng minh 403/404 theo policy, không chỉ test 422 vì thiếu parent.

**Cạnh mồ côi trong join table:** với many-to-many, hai FK độc lập cần chặn relation to missing parent ở cả hai đầu. Một UNIQUE trên pair có thể cần để chặn duplicate relationship.

**Cycle không hợp lệ:** với hierarchical tree, một node trỏ tới parent của chính nó hoặc tạo vòng A→B→A có thể là lỗi logic dù mọi FK hợp lệ. Cần cycle detection/database recursive constraints hoặc transaction logic; test cả self-loop, two-node cycle, multi-hop cycle.

**Cardinality:** nếu một child chỉ được có một active parent, cần uniqueness/partial index hoặc business rule. Một FK chỉ xác nhận parent tồn tại chứ không bảo đảm “đúng một active assignment”.

**Race condition:** service check `existsById` có thể pass, parent bị delete ở transaction khác rồi INSERT fail. FK vẫn bảo vệ integrity; error mapping của service/controller phải biến DB exception thành error ổn định. Test concurrency cần database engine/transaction isolation phù hợp và đồng bộ chủ động, không dựa vào `Thread.sleep`.

**Soft delete:** parent row còn tồn tại nhưng bị đánh dấu `deleted=true`; FK vẫn cho phép reference. Test business rule phải chặn order thuộc customer đã bị vô hiệu hóa. DB FK không biết khái niệm active/inactive nếu schema không có constraint phù hợp.

**Không nâng phạm vi của test quá mức:** ví dụ hiện tại chứng minh FK existence/no cascade trên H2; nó không tự chứng minh authorization, soft delete, graph cycles hay concurrency semantics production.

## 16. Các lớp lỗi và tránh xanh giả

| Tầng | Triệu chứng | Test nên viết |
| --- | --- | --- |
| Jackson | Số quá lớn, sai kiểu, JSON syntax lỗi | `HttpMessageNotReadableException` → error body an toàn |
| Bean Validation | 0, 101, null, blank, string quá dài | HTTP 400 và DB không thay đổi |
| Business service | ID khách hàng không tồn tại | HTTP 422 policy + không insert |
| JDBC | Dữ liệu có quote/semicolon/Unicode | Prepared statements và round-trip đúng |
| Database | CHECK/NOT NULL/FK/UNIQUE vi phạm | Direct SQL → `DataIntegrityViolationException` hoặc lỗi DB tương ứng |
| Transaction | Service fail sau một bước write | Rollback/commit assertions ngoài transaction phù hợp |
| HTTP serialization | Input Unicode bị đổi, null bị omit | JSON body + DB read-back |
| Security | ID hợp lệ nhưng thuộc user khác | Role/owner policy tests riêng |

**Mỗi test fail phải chẩn đoán được tầng nào sai.** Đừng chỉ `assertThrows(Exception.class, ...)` vì nó sẽ pass cả khi kết nối database lỗi hoặc code ném exception không liên quan. Dùng expected exception class và kiểm tra dữ liệu còn lại; với JDBC engine khác, kiểm tra root cause/SQLSTATE/constraint name nếu contract cần phân biệt.

**Tránh assert chính xác message của H2/Jackson:** wording có thể đổi theo phiên bản/locale và đôi khi chứa dữ liệu nội bộ. Ở HTTP boundary, kiểm tra public error code; ở repository layer, kiểm tra exception type hoặc constraint behavior, không đóng cứng full exception string.

## 17. H2 so với database production và Testcontainers

H2 giúp phản hồi nhanh, nhưng không đại diện cho mọi quy tắc:

- **Unicode length:** Java `@Size`, H2 `VARCHAR(n)` và PostgreSQL `character varying(n)` có thể tính độ dài khác nhau đối với surrogate/grapheme.
- **Collation/case sensitivity:** so sánh `"é"` và `"e\u0301"` có thể khác theo collation, normalization, engine và index.
- **NULL semantics:** `UNIQUE`/multiple NULLs, null ordering và constraint rules có khác biệt theo engine.
- **Foreign keys:** deferrable constraints, ON DELETE CASCADE/RESTRICT, isolation behavior và deadlocks có thể khác.
- **Data types:** UUID, JSONB, time zone, decimal precision, arrays, enum, generated columns cần thử trên engine thật.
- **Concurrent transactions:** lock/isolation và visibility của H2 khác PostgreSQL/MySQL.

Với Spring Boot 3.5, một test tích hợp database production-like có thể dùng Testcontainers và `@ServiceConnection`, đồng thời ngăn database auto-replacement khi dùng data slice. Với test full application, cần thiết lập container lifecycle và connection details phù hợp; chỉ nên trỏ tới một **ephemeral test DB**.

Ví dụ **snippet định hướng**, không phải class đầy đủ:

```java
@Testcontainers
@SpringBootTest
class PostgreSqlBoundaryTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Để chạy snippet này cần Testcontainers PostgreSQL, Spring Boot testcontainers module, PostgreSQL driver, schema/migrations, các imports và test methods. **Không coi đây là file chạy độc lập**; bài chính đã có bộ H2 hoàn chỉnh. Khi dùng container, kiểm tra compatibility Boot/Testcontainers version, Docker availability, SSL/network và cleanup; test schema phải khớp production migration chứ không chỉ test fixture tự viết.

## 18. Các lỗi phổ biến khi kiểm thử dữ liệu biên

**1. Chỉ test giá trị giữa miền.** `quantity=50` không chứng minh min/max; thêm 0/1/100/101.

**2. Dùng primitive `int` cho field cần phát hiện JSON null.** Missing/null có thể bị ép thành 0; dùng `Integer + @NotNull`.

**3. Dùng `@Size` để cấm null.** `@Size` cho phép null; phối hợp `@NotBlank` hoặc `@NotNull`.

**4. Dùng `@NotNull` để cấm `""` hoặc `"   "`.** Nó chỉ cấm null; dùng `@NotBlank` cho string bắt buộc có nội dung.

**5. Coi một emoji = một Java `char`.** Nhiều emoji cần surrogate pairs; `String.length()` đo UTF-16 units.

**6. Coi code point = grapheme.** Một chữ có dấu hoặc emoji ZWJ có thể nhiều code points nhưng nhìn như một ký tự.

**7. Bỏ qua NFC/NFD.** Hai chuỗi trông giống nhau có thể khác `equals` và khác unique index behavior. Chọn normalization policy.

**8. Test Unicode chỉ qua controller response.** JSON có thể đúng nhưng DB lưu sai; kiểm tra JDBC read-back khi cần.

**9. Nghĩ `NOT NULL` cấm blank.** Không; SQL không tự hiểu “có chữ nhìn thấy”.

**10. Kiểm tra customer tồn tại ở service nhưng không có FK.** Có race hoặc code khác bypass service; DB phải bảo vệ integrity.

**11. Test FK chỉ qua HTTP 422.** Có thể service chặn trước DB; cần direct JDBC test để chứng minh FK thật.

**12. Giả định FK bảo vệ authorization.** Customer thuộc người khác vẫn tồn tại; cần kiểm tra ownership/role riêng.

**13. Tạo invalid relation nhưng chỉ assert exception.** Kiểm tra không còn orphan row/DB không đổi.

**14. Dùng `JdbcTemplate` với SQL string concatenation.** Có thể dẫn tới injection/escaping bug; dùng placeholders/bind params.

**15. Assert SQL exception message chính xác.** Driver/version/locale khác nhau; public API trả code ổn định.

**16. Dùng `@Transactional` test qua HTTP thật và tin rollback xóa server writes.** HTTP server thread có transaction riêng; phải cleanup committed rows.

**17. Cho nhiều tests dùng cùng seed/key và phụ thuộc thứ tự chạy.** Test isolation/rollback/unique fixtures phải rõ.

**18. Dùng H2 để tuyên bố PostgreSQL collation/constraint behavior đúng.** Cần test production-like engine nếu behavior phụ thuộc dialect.

**19. Dùng random data không kiểm soát seed.** Failure khó tái hiện; dùng deterministic fixtures và property-based test với replay.

**20. Giả định mọi invisible Unicode đều bị @NotBlank chặn.** Cần custom rule theo Unicode policy và tests riêng.

## 19. Checklist QA trước khi chốt

**Test data matrix:**

- Đã có min−1, min, min+1, max−1, max, max+1 chưa?
- Có test null/missing/zero/empty/blank cho fields đúng loại?
- Các optional fields thực sự cho phép null hay phải vắng mặt?
- Có test sai kiểu JSON, JSON syntax lỗi và số vượt miền kiểu?
- Một invalid request có để lại side effects DB không?

**Unicode:**

- Có chữ Việt có dấu, emoji ngoài BMP và combining sequence?
- Có phân biệt UTF-16 code units, code points, grapheme clusters?
- Chuỗi ở đúng/quá `@Size(max=n)` đã được kiểm tra?
- Có xác định rõ preserve hay normalize NFC/NFD?
- Có test round-trip qua Jackson và DB, không chỉ Java String?
- Engine/collation production có được test riêng nếu đây là rủi ro quan trọng?

**Quan hệ và database:**

- DB có `FOREIGN KEY`, `NOT NULL`, `CHECK` và các UNIQUE cần thiết?
- Có test quan hệ sai bằng **bypass service** để chứng minh FK?
- Có test delete parent, cascade/restrict theo contract?
- Có test parent tồn tại nhưng **không được phép tham chiếu** theo authorization?
- Có test quan hệ trùng, cycle, soft delete nếu domain yêu cầu?
- Có kiểm tra SQL query được parameterize và transaction cleanup đúng?

**Chất lượng test:**

- Positive tests chứng minh endpoint xử lý request hợp lệ?
- Negative tests kiểm tra cả status/error code và DB không đổi?
- Có dùng đúng test slice/integration level cho ranh giới cần chứng minh?
- Source files, Gradle dependencies và schema có nhất quán?
- Có tránh log token/PII thật trong test fixtures?
- Có tách được lỗi Jackson, validation, service và DB từ failure?
- Kết luận có giới hạn đúng phạm vi test H2/MockMvc hay không?

**Kết luận:** kiểm thử dữ liệu biên tốt không chỉ thêm vài con số 0 và 100. Bạn cần một **matrix có chủ đích** bao gồm số ở/sát ngưỡng, JSON null/missing, text blank, Unicode với UTF-16/normalization, và các quan hệ sai. Bean Validation bảo vệ request boundary; service bảo vệ business policy; **database FK/CHECK/NOT NULL** là lớp cuối không thể bỏ. Test HTTP/JSON và direct JDBC cùng nhau giúp chứng minh lỗi bị chặn đúng tầng, không để lại dữ liệu mồ côi và không làm hỏng Unicode khi round-trip.

## 20. Tài liệu tham khảo

- [Spring Framework — Testing Spring MVC with MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm tra request/response, status và JSON body.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, rollback và database test boundaries.
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): semantics `@NotNull`, `@NotBlank`, `@Size`, `@Min` và `@Max`.
- [Java SE 17 — String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length()`, `codePointCount()`, `isBlank()`.
- [Java SE 17 — Normalizer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization NFC/NFD.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `SimpleJdbcInsert` và database errors.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, test isolation, propagation.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html): embedded database và `schema.sql`.
