# Kiểm tra ánh xạ kiểu số, thời gian, enum và giá trị null

Một entity có thể được lưu thành công nhưng khi đọc lại lại khác giá trị ban đầu: `BigDecimal` mất scale, timestamp lệch múi giờ, enum đổi ý nghĩa sau khi thêm một phần tử, hoặc `null` biến thành giá trị mặc định do field dùng primitive. Những lỗi này thường không xuất hiện trong unit test chỉ tạo object Java rồi assert getter. Chúng chỉ lộ ra khi giá trị đi qua toàn bộ chuỗi **Java type → Hibernate mapping → JDBC type → database column → JDBC result → Java type**.

Vì vậy, kiểm thử mapping cần tập trung vào **round trip qua database thật hoặc database tương thích dialect**, không chỉ kiểm tra annotation hay trạng thái object trong bộ nhớ.

Bài này xây dựng một phương pháp kiểm thử có hệ thống cho bốn nhóm thường gây lỗi:

- **Kiểu số:** integer range, `BigDecimal`, precision/scale, rounding, floating point.
- **Thời gian:** `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime`, timezone, DST và độ chính xác fractional seconds.
- **Enum:** `ORDINAL`, `STRING`, `AttributeConverter`, thay đổi enum theo thời gian.
- **Null:** primitive/wrapper, SQL `NULL`, default, nullable constraints, converter và SQL three-valued logic.

~~~text
Java value
    |
    v
JPA attribute / Hibernate mapping
    |
    v
JDBC type + driver
    |
    v
Database column + dialect
    |
    v
Stored value
    |
    v
JDBC ResultSet
    |
    v
Hibernate hydration / conversion
    |
    v
Java value after reload
~~~

**Nguyên tắc cốt lõi:** Một test mapping có giá trị phải ghi dữ liệu, flush, kết thúc hoặc làm sạch Persistence Context, rồi đọc lại từ database theo đúng transaction và dialect cần kiểm chứng. Chỉ khi so sánh giá trị sau round trip bạn mới biết mapping thực tế bảo toàn được điều gì.

> **Phạm vi:** Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA, JDBC và SQL database là bối cảnh minh họa. Kiểu SQL cụ thể, timezone behavior, precision và cách driver chuyển đổi có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle và H2. Các ví dụ SQL dùng PostgreSQL khi cần cú pháp cụ thể; phải điều chỉnh cho DBMS của dự án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế test kiểm tra round-trip cho numeric, temporal, enum và nullable fields.
2. Phân biệt Java type, JPA mapping, JDBC type và physical database column.
3. Kiểm tra `precision`, `scale`, overflow, rounding và floating-point behavior.
4. Phát hiện sai lệch timezone, DST, timestamp precision và các phép chuyển đổi thời gian.
5. Đánh giá rủi ro của enum `ORDINAL` và `STRING` khi schema/domain thay đổi.
6. Kiểm tra `AttributeConverter` và mapping custom.
7. Phân biệt Java `null`, SQL `NULL`, default value và database constraints.
8. Viết integration tests không bị first-level cache che khuất kết quả.
9. Chọn database test đủ gần production để kiểm tra dialect/driver behavior.
10. Tổ chức boundary tests, migration tests và regression tests cho mapping.

## 2. Vì sao unit test Java chưa đủ?

Một unit test:

~~~java
Product product = new Product();
product.setPrice(new BigDecimal("12.30"));

assertEquals(new BigDecimal("12.30"), product.getPrice());
~~~

chỉ chứng minh setter/getter giữ object đã gán. Nó không kiểm tra:

- Hibernate bind `BigDecimal` thành JDBC `DECIMAL` hay kiểu khác.
- Database column có scale 2 hay scale 0.
- Database có làm tròn hoặc từ chối giá trị vượt precision.
- Driver trả `BigDecimal` có scale như thế nào.
- Converter có được áp dụng đúng.
- Giá trị `null` có được lưu thành SQL NULL.
- Timestamp có bị normalize theo timezone/session settings.

Một test mapping cần đưa dữ liệu qua persistence layer:

~~~java
entityManager.persist(product);
entityManager.flush();
entityManager.clear();

Product reloaded = entityManager.find(Product.class, product.getId());
assertEquals(expected, reloaded.getPrice());
~~~

`flush()` buộc pending SQL được thực thi; `clear()` buộc lần load sau không dùng managed object cũ trong first-level cache. Để kiểm tra commit durability hoặc behavior giữa transactions, cần transaction boundary và EntityManager mới theo cách riêng ở các phần sau.

## 3. Ma trận Java type → JDBC → SQL type

Không nên chỉ nhìn Java field và đoán database type. Một ma trận mapping hữu ích:

| Java type | JDBC/SQL thường gặp | Điểm cần test |
|---|---|---|
| `Integer` | INTEGER | Range và NULL |
| `Long` | BIGINT | Overflow và NULL |
| `BigInteger` | NUMERIC/DECIMAL tùy provider | Precision lớn |
| `BigDecimal` | DECIMAL/NUMERIC | Precision, scale, rounding |
| `Float` / `Double` | REAL/DOUBLE | Sai số biểu diễn |
| `Boolean` | BOOLEAN hoặc dạng DB tương ứng | Dialect và NULL |
| `LocalDate` | DATE | Calendar date |
| `LocalTime` | TIME | Fractional precision |
| `LocalDateTime` | TIMESTAMP | Không chứa zone/offset |
| `Instant` | Timestamp representation theo provider/dialect | UTC và precision |
| `OffsetDateTime` | TIMESTAMP WITH TIME ZONE hoặc normalized form | Offset/instant semantics |
| Enum | INTEGER hoặc VARCHAR | Stability khi đổi enum |
| Nullable wrapper | SQL type tương ứng | SQL NULL round trip |

Bảng là hướng dẫn tổng quát, không phải hợp đồng giống nhau trên mọi Hibernate dialect và JDBC driver. Hãy kiểm tra schema thật bằng migration/DDL hoặc database metadata.

## 4. Một entity dành cho mapping tests

Có thể tạo một entity riêng để tập trung vào các kiểu dữ liệu:

~~~java
@Entity
@Table(name = "mapping_probe")
public class MappingProbe {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "quantity")
    private Integer quantity;

    @Column(name = "amount", precision = 19, scale = 4)
    private BigDecimal amount;

    @Column(name = "ratio")
    private Double ratio;

    @Column(name = "business_date")
    private LocalDate businessDate;

    @Column(name = "local_timestamp")
    private LocalDateTime localTimestamp;

    @Column(name = "occurred_at")
    private Instant occurredAt;

    @Column(name = "expires_at")
    private OffsetDateTime expiresAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 30)
    private ProbeStatus status;

    @Column(name = "optional_note")
    private String optionalNote;

    // Constructors, getters and setters.
}
~~~

Enum:

~~~java
public enum ProbeStatus {
    NEW,
    PROCESSING,
    COMPLETED
}
~~~

Entity này phục vụ **integration testing**, không nhất thiết là một domain entity production. Trong hệ thống thực, mapping test nên tập trung vào entity thật hoặc mapping module thực tế để test bảo vệ đúng schema đang triển khai.

## 5. Kiểm tra schema vật lý, không chỉ annotation

Ví dụ annotation:

~~~java
@Column(precision = 19, scale = 4)
private BigDecimal amount;
~~~

có thể ảnh hưởng DDL Hibernate generate, nhưng khi production dùng Flyway/Liquibase hoặc schema được DBA quản lý, annotation không tự thay đổi cột đang tồn tại.

Schema ví dụ PostgreSQL:

~~~sql
CREATE TABLE mapping_probe (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    quantity INTEGER,
    amount NUMERIC(19, 4),
    ratio DOUBLE PRECISION,
    business_date DATE,
    local_timestamp TIMESTAMP,
    occurred_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(30),
    optional_note VARCHAR(200)
);
~~~

Trong test, xác nhận:

- Migration đã tạo đúng type.
- Precision/scale đúng.
- Nullability đúng.
- Default đúng.
- Enum column length đủ.
- Timestamp column có semantics đúng.
- Index/constraints không vô tình thay đổi mapping behavior.

Không dùng `ddl-auto=create` làm bằng chứng migration production đúng nếu production chạy schema migrations độc lập.

## 6. @Column precision và scale có nghĩa gì?

Với decimal:

~~~java
@Column(precision = 19, scale = 4)
private BigDecimal amount;
~~~

- `precision`: tổng số chữ số có nghĩa được lưu.
- `scale`: số chữ số ở bên phải dấu thập phân.
- Với `NUMERIC(19,4)`, tối đa 19 digits tổng cộng, trong đó 4 digits sau dấu thập phân.
- Phần nguyên tối đa 15 digits trong mô hình decimal chuẩn.

Ví dụ hợp lệ về mặt giới hạn decimal:

~~~text
123456789012345.6789
~~~

Ví dụ vượt precision hoặc scale có thể bị database từ chối hoặc làm tròn tùy DBMS/configuration. Không được giả định mọi DB đều xử lý giống nhau.

## 7. BigDecimal scale là một phần cần kiểm tra

Java:

~~~java
BigDecimal a = new BigDecimal("12.3");
BigDecimal b = new BigDecimal("12.30");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b));    // 0
~~~

`equals()` so sánh cả numerical value và scale; `compareTo()` so sánh numerical value.

Database `NUMERIC(19,4)` có thể trả giá trị với scale 4, ví dụ `12.3000`, dù ứng dụng ghi `12.3`. Khi test:

- Nếu business yêu cầu numerical equality, dùng `compareTo() == 0` hoặc AssertJ comparator phù hợp.
- Nếu business yêu cầu canonical scale, kiểm tra `scale()` riêng.
- Nếu format tiền tệ phải đúng 2 chữ số, quy định rounding/normalization ở domain boundary.
- Không ép scale bằng `stripTrailingZeros()` nếu downstream contract cần scale cố định.

Test round-trip:

~~~java
BigDecimal expected = new BigDecimal("12.3456");

entityManager.persist(probe);
entityManager.flush();
entityManager.clear();

MappingProbe reloaded =
    entityManager.find(MappingProbe.class, probeId);

assertEquals(0, expected.compareTo(reloaded.getAmount()));
~~~

Nếu cần scale chính xác:

~~~java
assertEquals(4, reloaded.getAmount().scale());
~~~

Hãy xác nhận scale behavior trên database/driver thực tế; provider có thể normalize representation.

## 8. Kiểm tra precision boundary

Với `NUMERIC(19,4)`, test các giá trị:

| Giá trị | Mục đích |
|---|---|
| `0` | Zero |
| `0.0001` | Nhỏ nhất theo scale 4 |
| `999999999999999.9999` | Giá trị dương sát giới hạn |
| `-999999999999999.9999` | Giới hạn âm |
| `123.4500` | Scale đúng |
| `123.45678` | Scale vượt 4 |
| `1000000000000000.0000` | Precision vượt giới hạn |
| `null` | Nullable mapping |

Test nên ghi rõ expected behavior cho từng DBMS: **round, truncate hay reject**. Đối với tiền và dữ liệu tài chính, không dựa vào implicit database rounding để thực thi business rule; normalize bằng `setScale(scale, RoundingMode)` trước khi persist.

Ví dụ:

~~~java
BigDecimal normalized = input.setScale(
    4,
    RoundingMode.HALF_UP
);
~~~

Nếu vượt integer precision, validation/domain code nên phát lỗi có ý nghĩa trước khi DB trả exception.

## 9. Không dùng double cho tiền tệ

Ví dụ:

~~~java
double total = 0.1 + 0.2;
System.out.println(total); // thường in 0.30000000000000004
~~~

Floating point theo IEEE 754 biểu diễn nhị phân; nhiều decimal fractions không thể biểu diễn chính xác.

Với số tiền:

~~~java
BigDecimal total =
    new BigDecimal("0.10")
        .add(new BigDecimal("0.20"));
~~~

Không khởi tạo bằng `new BigDecimal(0.1)` nếu muốn giữ decimal literal chính xác. Dùng String, `BigDecimal.valueOf()` với ý thức rõ semantics hoặc parse từ input decimal.

Kiểm thử `Double` vẫn cần nếu domain thật sự dùng measurement/scientific values: dùng tolerance hợp lý thay vì `equals()` exact cho phép tính floating-point.

## 10. Integer range và overflow

Java types có giới hạn:

| Type | Min | Max |
|---|---:|---:|
| `Byte` | -128 | 127 |
| `Short` | -32,768 | 32,767 |
| `Integer` | -2,147,483,648 | 2,147,483,647 |
| `Long` | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

Nếu DB column là BIGINT nhưng Java field là Integer, giá trị lớn hơn `Integer.MAX_VALUE` không thể round-trip an toàn.

Ngược lại, Java Long map vào DB INTEGER cũng có nguy cơ overflow/truncation/rejection.

Boundary tests nên kiểm tra:

- Min/max Java value.
- Min/max DB column.
- Giá trị ngay dưới/ở/trên boundary.
- Null nếu wrapper.
- Dữ liệu legacy vượt range sau khi thay mapping.

Không chỉ test một số nhỏ như 1 hoặc 42; các giá trị đó không phát hiện sai type width.

## 11. Kiểm tra BigInteger và NUMERIC

`BigInteger` phù hợp với số nguyên rất lớn, nhưng DB column phải đủ precision:

~~~java
@Column(precision = 38, scale = 0)
private BigInteger externalSequence;
~~~

Database có giới hạn precision riêng. Một DB có thể hỗ trợ NUMERIC precision lớn hơn DB khác. JDBC driver/provider cũng quyết định Java representation khi đọc.

Nếu dữ liệu vượt BIGINT nhưng vẫn cần sort/compare trong SQL, dùng `NUMERIC/DECIMAL` có precision phù hợp và kiểm tra query operators/index behavior.

## 12. Boolean mapping và NULL

~~~java
@Column(name = "enabled")
private Boolean enabled;
~~~

`Boolean` có thể mang `true`, `false` hoặc `null`. Ngược lại:

~~~java
private boolean enabled;
~~~

primitive chỉ có true/false; nếu SQL column NULL được hydrate vào primitive, behavior có thể dẫn tới lỗi hoặc giá trị không thể biểu diễn theo mapping/provider. Không thiết kế nullable DB column cho primitive field.

Kiểm tra:

- `true` round trip.
- `false` round trip.
- `null` round trip nếu column nullable.
- Default khi INSERT bỏ column.
- Database check constraint.
- Dialect có native BOOLEAN hay biểu diễn khác.

Không dùng `@Column(nullable=false)` làm thay database NOT NULL constraint nếu schema được quản lý riêng.

## 13. Kiểm thử Java null và SQL NULL

Với wrapper:

~~~java
@Column(name = "quantity")
private Integer quantity;
~~~

Round-trip null:

~~~java
probe.setQuantity(null);

entityManager.persist(probe);
entityManager.flush();
entityManager.clear();

MappingProbe reloaded =
    entityManager.find(MappingProbe.class, probe.getId());

assertNull(reloaded.getQuantity());
~~~

Để chứng minh database thật lưu NULL, có thể query scalar:

~~~java
Object raw = entityManager.createNativeQuery(
    "select quantity from mapping_probe where id = :id"
)
.setParameter("id", probe.getId())
.getSingleResult();

assertNull(raw);
~~~

Native query phải dùng physical column/table names và được điều chỉnh theo DB. Nếu chỉ assert field Java sau persist mà không clear context, bạn chưa chứng minh JDBC/database round trip.

## 14. NULL khác default value

Các trạng thái khác nhau:

- Application truyền `null`.
- Application không gán field.
- Java field primitive mặc định 0/false.
- Database column có `DEFAULT`.
- INSERT bỏ qua column.
- INSERT bind SQL NULL.
- Database trigger thay giá trị.
- Entity callback/auditing gán giá trị trước persist.

Ví dụ:

~~~sql
CREATE TABLE invoice (
    id BIGINT PRIMARY KEY,
    retry_count INTEGER DEFAULT 0
);
~~~

Nếu Hibernate INSERT `retry_count = NULL` rõ ràng, database default thường **không được áp dụng**. Default thường chỉ áp dụng khi column bị bỏ khỏi INSERT hoặc dùng cú pháp `DEFAULT`, tùy DB.

Đừng giả định `null` nghĩa là “hãy dùng DB default”. Kiểm tra SQL generated và schema default.

## 15. @Column(nullable=false) không phải runtime null guard

~~~java
@Column(nullable = false)
private String name;
~~~

`nullable=false` chủ yếu là mapping/DDL metadata và có thể tham gia validation tùy integration. Nó không phải bảo đảm mọi đường ghi đều bị từ chối trước SQL.

Để enforce dữ liệu, schema nên có:

~~~sql
name VARCHAR(200) NOT NULL
~~~

Cần test:

1. Persist entity với `name=null`.
2. Flush.
3. Xác định lỗi đến từ Bean Validation, Hibernate, JDBC hay DB constraint.
4. Kiểm tra transaction rollback.
5. Đọc lại bằng transaction mới nếu cần.

Đừng chỉ assert “có exception” mà không xác định constraint layer nào chịu trách nhiệm nếu điều đó quan trọng với API/error handling.

## 16. SQL three-valued logic

SQL có ba kết quả logic: TRUE, FALSE và UNKNOWN.

~~~sql
NULL = 5          -- UNKNOWN
NULL <> 5         -- UNKNOWN
NULL IS NULL      -- TRUE
NULL IS NOT NULL  -- FALSE
~~~

Vì vậy:

~~~sql
WHERE status <> 'DELETED'
~~~

không trả các rows có `status IS NULL`. `WHERE` chỉ giữ rows có predicate TRUE; FALSE và UNKNOWN đều bị loại.

Test mapping nullable cần kiểm tra cả **round-trip null** lẫn **query semantics với null**, vì hai vấn đề khác nhau.

## 17. IS NULL và parameter = NULL không tương đương

Sai khi muốn tìm rows NULL:

~~~sql
WHERE optional_note = NULL
~~~

Đúng:

~~~sql
WHERE optional_note IS NULL
~~~

Trong JPQL:

~~~java
select p from MappingProbe p
where p.optionalNote is null
~~~

Nếu dùng parameter, phải xử lý nhánh null rõ ràng:

~~~java
if (note == null) {
    // Query IS NULL
} else {
    // Query = :note
}
~~~

Không mặc định `column = :parameter` với parameter null sẽ hoạt động như `IS NULL`.

## 18. Primitive, wrapper và Optional

| Java declaration | Có biểu diễn NULL? | Thường dùng |
|---|---|---|
| `int` | Không | Giá trị bắt buộc, có default primitive |
| `Integer` | Có | Nullable numeric |
| `boolean` | Không | Giá trị bắt buộc |
| `Boolean` | Có | Tri-state nếu domain cần |
| `long` | Không | ID/value bắt buộc |
| `Long` | Có | Nullable numeric/reference |
| `Optional<T>` field entity | Không nên dùng như mapping mặc định | Optional ở API/service boundary |

Không dùng `Optional` field trong entity để thay wrapper một cách tùy tiện. JPA entity mapping thông thường phù hợp với nullable reference field; dùng `Optional<T>` ở return types/service APIs khi phù hợp.

## 19. AttributeConverter là gì?

`AttributeConverter<X,Y>` chuyển Java domain type X sang basic database representation Y:

~~~java
@Converter
public class CurrencyCodeConverter
        implements AttributeConverter<CurrencyCode, String> {

    @Override
    public String convertToDatabaseColumn(CurrencyCode value) {
        return value == null ? null : value.code();
    }

    @Override
    public CurrencyCode convertToEntityAttribute(String value) {
        return value == null ? null : new CurrencyCode(value);
    }
}
~~~

Entity:

~~~java
@Convert(converter = CurrencyCodeConverter.class)
@Column(name = "currency_code", length = 3)
private CurrencyCode currency;
~~~

Test cần kiểm tra cả hai chiều:

- Domain object → database code.
- Database code → domain object.
- Null input.
- Unknown/invalid code.
- Legacy code.
- Case/whitespace normalization nếu converter có làm.

## 20. Null behavior của AttributeConverter

JPA provider không nhất thiết gọi converter cho attribute null; theo contract của JPA, null values được xử lý như null trong database representation thay vì bắt buộc đi qua conversion logic. Vì vậy converter không nên dựa vào việc nhận null để tạo default business value.

Một converter nên xử lý null an toàn dù provider không gọi converter trong trường hợp đó:

~~~java
@Override
public String convertToDatabaseColumn(CurrencyCode value) {
    if (value == null) {
        return null;
    }
    return value.code();
}
~~~

Test round-trip null ở mức EntityManager/DB, không chỉ gọi trực tiếp converter method.

Nếu muốn default currency, đặt default tại domain factory/service hoặc schema policy rõ ràng; không dựa vào một giả định rằng converter sẽ biến null thành giá trị mặc định trong mọi provider.

## 21. Converter và enum mapping

Không kết hợp `@Enumerated` với `@Convert` trên cùng attribute theo cách mâu thuẫn. Nếu enum được lưu bằng converter thành code ổn định, converter là cơ chế ánh xạ chính.

Ví dụ:

~~~java
public enum OrderState {
    PENDING("P"),
    PAID("S"),
    CANCELLED("X");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderState fromCode(String code) {
        return Arrays.stream(values())
            .filter(v -> v.code.equals(code))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown state: " + code)
            );
    }
}
~~~

~~~java
@Converter
public class OrderStateConverter
        implements AttributeConverter<OrderState, String> {

    @Override
    public String convertToDatabaseColumn(OrderState value) {
        return value == null ? null : value.code();
    }

    @Override
    public OrderState convertToEntityAttribute(String code) {
        return code == null ? null : OrderState.fromCode(code);
    }
}
~~~

Converter này cho phép đổi Java enum constant name mà không nhất thiết đổi DB code, nhưng code values vẫn là schema contract cần migration/test.

## 22. EnumType.ORDINAL có rủi ro khi reorder

~~~java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
~~~

Giá trị lưu là vị trí enum bắt đầu từ 0:

~~~java
enum OrderStatus {
    NEW, PAID, SHIPPED
}
~~~

| Enum | Ordinal |
|---|---:|
| NEW | 0 |
| PAID | 1 |
| SHIPPED | 2 |

Nếu sau này chèn `CANCELLED` vào giữa:

~~~java
enum OrderStatus {
    NEW, PAID, CANCELLED, SHIPPED
}
~~~

`SHIPPED` chuyển ordinal từ 2 thành 3. Dữ liệu cũ lưu 2 sẽ được đọc thành CANCELLED. Đây là lỗi dữ liệu nghiêm trọng mà test chỉ round-trip enum hiện tại có thể không phát hiện.

**Không reorder hoặc chèn enum constants giữa các giá trị đang lưu khi dùng ORDINAL** nếu không có migration được kiểm soát.

## 23. EnumType.STRING ổn định hơn ordinal nhưng vẫn có contract

~~~java
@Enumerated(EnumType.STRING)
@Column(length = 30)
private OrderStatus status;
~~~

DB lưu tên constant, ví dụ `SHIPPED`.

Ưu điểm:

- Reorder enum constants không đổi dữ liệu.
- Thêm constant mới không làm ordinal cũ đổi ý nghĩa.
- Dễ đọc trong SQL/admin tools.

Rủi ro:

- Rename `SHIPPED` thành `DISPATCHED` cần migration.
- Xóa constant còn dữ liệu cũ có thể gây lỗi hydration.
- Column length phải đủ.
- Case/collation phải nhất quán.
- Consumer/reporting ngoài ứng dụng cũng phụ thuộc chuỗi này.

`STRING` thường dễ bảo trì hơn `ORDINAL`, nhưng không tự làm enum schema bất biến.

## 24. Kiểm thử enum round trip

~~~java
@Test
void enumStringRoundTrips() {
    probe.setStatus(ProbeStatus.PROCESSING);

    entityManager.persist(probe);
    entityManager.flush();
    entityManager.clear();

    MappingProbe reloaded =
        entityManager.find(MappingProbe.class, probe.getId());

    assertEquals(
        ProbeStatus.PROCESSING,
        reloaded.getStatus()
    );
}
~~~

Ngoài round-trip, kiểm tra database value:

~~~sql
SELECT status
FROM mapping_probe
WHERE id = ?;
~~~

Với `EnumType.STRING`, expected value là đúng constant name (trừ converter/custom mapping). Với `ORDINAL`, expected numeric index. Đối chiếu SQL giúp phát hiện mapping annotation không như dự định.

## 25. Kiểm thử enum migration và dữ liệu legacy

Một test có thể chèn trực tiếp code cũ:

~~~sql
INSERT INTO mapping_probe(id, status)
VALUES (9001, 'LEGACY_PENDING');
~~~

Sau đó load entity và xác định behavior mong muốn:

- Converter map legacy code sang state hiện tại.
- Migration chuyển code cũ sang code mới.
- Unknown code bị từ chối với exception có ý nghĩa.
- Unknown code được giữ trong một representation mở nếu domain cần forward compatibility.

Không để một enum converter ném exception khó hiểu trong production mà không có migration/runbook cho dữ liệu cũ.

## 26. Enum column length và collation

Với STRING mapping:

~~~java
@Column(length = 30)
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

Nếu enum constant dài hơn column length, insert có thể bị reject/truncate tùy database/configuration.

Kiểm tra:

- Giá trị dài nhất.
- Case sensitivity.
- Column collation.
- Check constraint cho tập giá trị hợp lệ.
- Schema migration khi thêm constant.
- Hệ thống downstream có parse cùng values không.

Một check constraint PostgreSQL:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_status
CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED'));
~~~

Khi thêm enum state, migration phải cập nhật constraint trước khi application ghi giá trị mới.

## 27. LocalDate ánh xạ DATE

`LocalDate` biểu diễn ngày lịch, không có giờ hoặc timezone:

~~~java
@Column(name = "business_date")
private LocalDate businessDate;
~~~

Ví dụ:

~~~java
LocalDate expected = LocalDate.of(2026, 11, 15);
~~~

Database DATE chỉ lưu year-month-day. Round-trip test:

~~~java
assertEquals(expected, reloaded.getBusinessDate());
~~~

Không chuyển `LocalDate` thành `Instant` bằng timezone mặc định rồi mong giá trị giữ nguyên. Một ngày lịch ở Tokyo và một ngày lịch ở New York là khái niệm calendar date, không phải cùng một instant.

Test leap day, cuối tháng/năm và date boundary nếu domain có quy tắc lịch.

## 28. LocalTime ánh xạ TIME

`LocalTime` biểu diễn giờ trong ngày, không chứa ngày hoặc timezone:

~~~java
@Column(name = "opening_time")
private LocalTime openingTime;
~~~

Kiểm thử:

- Giờ nguyên.
- Có nanoseconds/fractional seconds.
- `LocalTime.MIDNIGHT`.
- Giá trị gần cuối ngày.
- Database TIME precision.
- Driver truncate/round fractional seconds.

Một số DB có TIME WITH TIME ZONE, nhưng Java `LocalTime` không mang offset; không dùng nó để lưu một thời điểm tuyệt đối.

## 29. LocalDateTime không chứa timezone

~~~java
@Column(name = "local_timestamp")
private LocalDateTime localTimestamp;
~~~

`LocalDateTime` chỉ là date + time trên lịch, ví dụ `2026-11-15T09:30`. Nó **không nói** đó là UTC, Asia/Ho_Chi_Minh hay America/New_York.

Dùng nó khi domain thật sự là local wall-clock time, ví dụ lịch mở cửa tại một địa điểm, giờ hẹn gắn với một timezone được quản lý riêng.

Không dùng LocalDateTime để biểu diễn event timestamp toàn hệ thống nếu cần một instant duy nhất giữa nhiều services. Khi đó cân nhắc `Instant` và quy ước UTC.

## 30. Instant biểu diễn một thời điểm trên timeline

~~~java
@Column(name = "occurred_at")
private Instant occurredAt;
~~~

`Instant` là số thời gian trên UTC timeline, không mang zone ID hay local offset.

Test nên so sánh:

~~~java
assertEquals(expectedInstant, reloaded.getOccurredAt());
~~~

Nhưng database timestamp có precision hữu hạn. Nếu DB chỉ giữ microseconds, một Instant có nanoseconds có thể được làm tròn/truncate. Vì vậy expected phải được normalize theo precision đã chọn, hoặc test riêng quy tắc rounding của DB/driver.

Không assert nanosecond equality nếu physical column không thể lưu chính xác đến nanosecond.

## 31. OffsetDateTime và TIMESTAMP WITH TIME ZONE

~~~java
@Column(name = "expires_at")
private OffsetDateTime expiresAt;
~~~

`OffsetDateTime` có local date-time và UTC offset, ví dụ `2026-11-15T09:00+07:00`.

Tuy nhiên database `TIMESTAMP WITH TIME ZONE` không phải lúc nào cũng lưu nguyên văn tên timezone hoặc offset gốc. PostgreSQL `timestamptz` lưu instant và hiển thị theo session timezone; nó không giữ `Asia/Ho_Chi_Minh` như một zone identity.

Vì vậy hãy quyết định test điều gì:

- Cùng **instant** sau round trip?
- Cùng **offset** ban đầu?
- Cùng local wall-clock representation?
- Cùng named ZoneId?

Nếu cần giữ zone ID như `Asia/Ho_Chi_Minh`, lưu thêm zone ID riêng. Đừng suy luận nó từ OffsetDateTime sau khi DB normalize.

## 32. ZonedDateTime và ZoneId

`ZonedDateTime` mang local date-time, offset và `ZoneId`, ví dụ `Europe/Paris`. Hibernate có các chiến lược lưu trữ timezone tùy dialect/configuration, chẳng hạn lưu native timezone type nếu DB hỗ trợ hoặc normalize về UTC.

Behavior cụ thể phụ thuộc Hibernate version và setting `hibernate.timezone.default_storage`/dialect support.

Nếu business cần tái hiện lịch địa phương trong tương lai (ví dụ cuộc họp hàng tuần lúc 09:00 tại một thành phố), chỉ lưu instant là chưa đủ. Thường cần lưu:

- Local date/time hoặc recurrence rule.
- Zone ID như `Europe/Paris`.
- Policy xử lý DST gaps/overlaps.
- Instant đã resolve cho một lần occurrence nếu cần audit.

Kiểm thử `ZonedDateTime` bằng exact object equality chỉ khi mapping được thiết kế để bảo toàn zone semantics đó; nếu DB chỉ lưu instant, test instant equality và zone ID column riêng.

## 33. Timezone của JVM, JDBC và database

Có nhiều timezone độc lập:

1. JVM default timezone.
2. Hibernate JDBC timezone configuration.
3. JDBC driver connection/session timezone.
4. Database server/session timezone.
5. Timezone của người dùng/business location.
6. Zone ID được lưu trong dữ liệu (nếu có).

Một test chạy laptop UTC có thể pass nhưng production container dùng timezone khác và trả timestamp lệch.

Đặt timezone test rõ ràng và kiểm tra cả cấu hình JDBC/database. Ví dụ Hibernate có thể cấu hình JDBC timezone:

~~~properties
hibernate.jdbc.time_zone=UTC
~~~

Property này ảnh hưởng cách Hibernate bind/extract một số temporal values qua JDBC. Nó không biến LocalDateTime thành Instant và không tự lưu ZoneId.

## 34. PostgreSQL timestamp semantics

PostgreSQL phân biệt:

- `timestamp without time zone`: local date-time, không có timezone.
- `timestamp with time zone` (`timestamptz`): biểu diễn instant; input có offset được quy đổi, output theo session timezone.

Ví dụ:

~~~sql
CREATE TABLE time_probe (
    local_value TIMESTAMP,
    instant_value TIMESTAMPTZ
);
~~~

Hai cột không tương đương. Khi insert `2026-11-15 09:00:00+07`, `timestamptz` biểu diễn cùng instant với `2026-11-15 02:00:00Z`; `timestamp` không giữ offset đó như một phần của giá trị.

Test cần set session timezone rõ hoặc so sánh normalized instants, tránh assert chuỗi render theo timezone session mà không chủ đích.

## 35. DST gaps và overlaps

Timezone có thể chuyển đồng hồ theo Daylight Saving Time. Một local time có thể:

- Không tồn tại (gap): đồng hồ nhảy từ 01:59 lên 03:00, nên 02:30 không có.
- Xuất hiện hai lần (overlap): đồng hồ lùi, 01:30 có hai instants khác nhau.

Ví dụ ZoneId:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 3, 29, 2, 30);
List<ZoneOffset> offsets =
    zone.getRules().getValidOffsets(local);
~~~

Ở một gap, list có thể rỗng. Ở overlap, có thể có hai offsets.

Không test timezone bằng fixed offset `+07:00` rồi kết luận đã test DST. Nếu ứng dụng có lịch theo vùng DST, thêm test cho gap/overlap và quy tắc business khi resolve.

## 36. Fractional seconds precision

Java `Instant` có nanoseconds; database columns thường có precision thấp hơn.

Ví dụ PostgreSQL:

~~~sql
occurred_at TIMESTAMP(6) WITH TIME ZONE
~~~

lưu microsecond precision. Một value có nanoseconds dư có thể được normalize khi ghi.

Tạo helper cho precision mà schema cam kết:

~~~java
static Instant toMicros(Instant value) {
    return value.truncatedTo(ChronoUnit.MICROS);
}
~~~

Đây là truncation helper minh họa. Nếu DB rounds thay vì truncates, helper phải khớp policy được chọn. Không âm thầm truncate trong test nếu production contract yêu cầu round; hãy test behavior thực tế.

## 37. Kiểm thử temporal boundary

Một bộ giá trị hữu ích:

- Epoch và thời điểm trước/sau epoch.
- Midnight.
- Cuối ngày `23:59:59...`.
- Leap day.
- Cuối tháng và cuối năm.
- Fractional seconds ở mức 0/3/6/9 digits.
- Offset dương và âm.
- Cùng instant với hai offsets khác nhau.
- DST gap/overlap cho các ZoneIds liên quan.
- Date/time gần database supported range.

Không dùng `Instant.now()` rồi assert exact value nếu precision bị mất hoặc thời gian thực thi thay đổi. Dùng fixed clock/value hoặc normalize rõ.

## 38. Clock injection giúp test ổn định

Không gọi `Instant.now()` rải rác trong domain/service nếu cần test thời gian chính xác. Inject `Clock`:

~~~java
@Configuration
class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Trong test:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-15T02:00:00Z"),
    ZoneOffset.UTC
);
~~~

Service dùng `Instant.now(clock)`. Điều này giúp test persisted timestamps deterministic và dễ kiểm tra boundary conditions.

`Clock` kiểm soát thời gian Java; nó không tự kiểm soát `CURRENT_TIMESTAMP` được database đánh giá. Nếu mapping/query phụ thuộc DB clock, cần cấu hình DB/test hoặc kiểm tra trong khoảng tolerance.

## 39. Null và temporal values

Temporal fields thường nullable:

~~~java
@Column(name = "cancelled_at")
private Instant cancelledAt;
~~~

Ý nghĩa có thể là:

- Chưa bị hủy.
- Không áp dụng.
- Chưa biết thời điểm.
- Dữ liệu legacy chưa có.

Không dùng một timestamp giả như `1970-01-01` thay null trừ khi domain quy định rõ sentinel. Query phải dùng:

~~~java
where p.cancelledAt is null
~~~

Nếu business cần phân biệt “chưa biết” với “không áp dụng”, một nullable timestamp có thể không đủ; dùng trạng thái rõ hoặc embedded value object phù hợp.

## 40. Null trong BigDecimal và enum

`BigDecimal amount = null` khác `BigDecimal.ZERO`. `OrderStatus status = null` khác `OrderStatus.NEW`.

Đừng tự gán default ở entity constructor nếu null có nghĩa nghiệp vụ khác. Ngược lại, nếu field bắt buộc, enforce bằng:

- Domain validation.
- Bean Validation như `@NotNull`.
- Database `NOT NULL`.
- Tests chứng minh từng layer.

Nếu dùng enum status nullable để biểu diễn “chưa khởi tạo”, hãy định nghĩa rõ. Với workflow state machine, thường trạng thái ban đầu explicit an toàn hơn null.

## 41. Bean Validation và database constraints

~~~java
@NotNull
@Column(nullable = false)
private BigDecimal amount;
~~~

Hai annotations có vai trò khác nhau:

- `@NotNull`: Bean Validation, nếu validation integration được bật và lifecycle validation xảy ra.
- `@Column(nullable=false)`: ORM schema/mapping metadata.
- Database `NOT NULL`: enforcement cuối tại DB cho mọi writer.

Một native SQL/JDBC writer có thể bypass Bean Validation. Vì vậy test cần xác định nơi nào đảm bảo invariant.

Với decimal:

~~~java
@Digits(integer = 15, fraction = 4)
private BigDecimal amount;
~~~

`@Digits` kiểm tra giới hạn digits theo Bean Validation; DB precision/scale vẫn phải phù hợp. Rounding policy là quyết định domain riêng.

## 42. DDL generation và schema migration

Trong dự án production, schema thường được quản lý bằng Flyway/Liquibase. Mapping annotation không nhất thiết tạo hoặc sửa cột.

Một test migration nên:

1. Khởi tạo database trống đúng engine/version.
2. Chạy tất cả migrations.
3. Boot Hibernate với schema validation phù hợp.
4. Kiểm tra columns/types/precision/scale/nullability/defaults/constraints.
5. Chạy round-trip tests.
6. Kiểm tra migration upgrade từ schema cũ có dữ liệu.
7. Xác nhận enum values cũ vẫn được đọc sau deployment.

`hibernate.hbm2ddl.auto=validate` có thể phát hiện một số mismatch mapping/schema, nhưng không thay test dữ liệu và không xác minh toàn bộ semantics của conversion.

## 43. Vì sao H2 không luôn đủ?

H2 hữu ích cho test nhanh, nhưng khác PostgreSQL/MySQL/SQL Server/Oracle ở:

- SQL types và DDL.
- Decimal rounding/overflow behavior.
- Timestamp/timezone semantics.
- Enum/boolean representation.
- Identifier generation.
- Collation/case sensitivity.
- JSON/native functions.
- Constraint enforcement.
- JDBC driver conversion.

Nếu bug chỉ xuất hiện trên production DB, một test suite chỉ chạy H2 có thể bỏ lỡ nó.

Dùng Testcontainers hoặc database instance cùng engine/version gần production cho những mapping phụ thuộc dialect. H2 vẫn có thể dùng cho unit/integration tests không phụ thuộc DB-specific semantics.

## 44. Testcontainers cho database thật

Ví dụ PostgreSQL Testcontainers (API phụ thuộc version):

~~~java
@Testcontainers
@DataJpaTest
class MappingProbePostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // Configure datasource to use container,
    // run migrations, then exercise EntityManager.
}
~~~

Trong Spring Boot, wiring datasource có thể dùng `@DynamicPropertySource` hoặc `@ServiceConnection` tùy Spring Boot/Testcontainers version.

Quan trọng:

- Container version nên gần production.
- Dùng migration thật.
- Kiểm tra driver version.
- Không dùng schema auto-generated thay migration nếu production migration là source of truth.
- Đóng container/clean state đúng lifecycle.
- Tách test theo dialect nếu ứng dụng hỗ trợ nhiều DBMS.

## 45. Test round-trip qua flush và clear

Một pattern cơ bản:

~~~java
@Test
void persistsAndReloadsMappingValues() {
    MappingProbe probe = new MappingProbe();
    probe.setAmount(new BigDecimal("123.4500"));
    probe.setBusinessDate(LocalDate.of(2026, 11, 15));
    probe.setStatus(ProbeStatus.PROCESSING);

    entityManager.persist(probe);
    entityManager.flush();

    Long id = probe.getId();
    entityManager.clear();

    MappingProbe reloaded =
        entityManager.find(MappingProbe.class, id);

    assertEquals(
        0,
        new BigDecimal("123.4500")
            .compareTo(reloaded.getAmount())
    );
    assertEquals(
        LocalDate.of(2026, 11, 15),
        reloaded.getBusinessDate()
    );
    assertEquals(
        ProbeStatus.PROCESSING,
        reloaded.getStatus()
    );
}
~~~

Điểm quan trọng là lấy ID trước clear và load lại sau clear. Nếu dùng generated ID, bảo đảm ID đã được cấp tại thời điểm đó; IDENTITY có thể yêu cầu INSERT sớm.

## 46. Flush/clear chưa chứng minh commit

`flush()` gửi SQL trong transaction, `clear()` detach entity. Test method của Spring có thể vẫn chạy trong một transaction rồi rollback cuối test.

Nếu cần kiểm tra **commit thật và đọc từ transaction mới**:

- Không để outer test transaction bao trùm service commit một cách vô tình.
- Dùng `TransactionTemplate` để commit fixture/scenario có chủ đích.
- Kết thúc EntityManager cũ.
- Mở transaction/EntityManager mới để đọc.
- Có thể dùng `@Commit` hoặc test không transactional tùy framework, nhưng phải hiểu cleanup.

Test rollback riêng cũng quan trọng: flush thành công rồi rollback phải không để lại row đã commit.

## 47. First-level cache có thể làm test sai

Ví dụ sai:

~~~java
entityManager.persist(probe);
entityManager.flush();

MappingProbe same =
    entityManager.find(MappingProbe.class, probe.getId());

assertSame(probe, same);
~~~

Test này chỉ chứng minh identity map hoạt động. Nó không chứng minh database đã lưu và đọc lại đúng.

Để kiểm tra mapping:

~~~java
entityManager.flush();
entityManager.clear();

MappingProbe reloaded =
    entityManager.find(MappingProbe.class, id);
~~~

Nếu L2 cache/query cache bật, có thể cần disable trong test hoặc clear cache có chủ đích để chắc chắn đang kiểm tra database round trip. Tuy nhiên test cache riêng cũng cần được giữ nếu cache là một phần production architecture.

## 48. Test raw JDBC representation

Khi cần xác nhận JDBC/database value, dùng `JdbcTemplate` hoặc native query:

~~~java
Map<String, Object> row = jdbcTemplate.queryForMap(
    "select amount, status, business_date from mapping_probe where id = ?",
    id
);
~~~

Assertions có thể kiểm tra:

- JDBC driver trả `BigDecimal`/date/timestamp class nào.
- Enum stored code đúng.
- SQL NULL được trả như Java null.
- Timestamp/offset representation theo DB session.
- Precision sau khi DB lưu.

Không viết test phụ thuộc implementation class không ổn định nếu contract chỉ yêu cầu value. Nếu cần kiểm tra raw type, pin DB/driver versions và ghi rõ đó là driver-specific test.

## 49. Parameterized boundary tests

JUnit parameterized test có thể kiểm tra nhiều values:

~~~java
@ParameterizedTest
@ValueSource(strings = {
    "0.0000",
    "1.0000",
    "999999999999999.9999",
    "-999999999999999.9999"
})
void decimalValuesRoundTrip(String text) {
    BigDecimal value = new BigDecimal(text);
    // Persist, flush, clear, reload, assert.
}
~~~

Thêm các cases vượt boundary riêng với expected failure/rounding theo database. Đừng trộn valid và invalid cases vào một test mà không xác định transaction cleanup giữa mỗi invocation.

## 50. Property-based testing cho mapping

Với decimal hoặc timestamp, property-based tests có thể sinh nhiều values trong miền hỗ trợ:

- Decimal nằm trong precision/scale.
- Integer nằm trong DB range.
- Instants được normalize theo precision column.
- Enum values thuộc tập được hỗ trợ.
- Null được đưa vào theo tỷ lệ có chủ đích.

Property mong muốn có thể là:

~~~text
decode(encode(value)) == normalize(value)
~~~

Trong đó `normalize()` thể hiện semantics đã chọn, ví dụ truncate Instant tới microseconds hoặc chuẩn hóa BigDecimal scale. Không dùng property `roundTrip(value) == value` nếu database contract không bảo toàn nguyên dạng.

Với DB integration tests, giới hạn số examples hợp lý để suite chạy ổn định; chạy fuzz/property tests sâu hơn trong pipeline riêng nếu cần.

## 51. Kiểm tra timezone test không phụ thuộc máy chạy

Cấu hình JVM test:

~~~text
-Duser.timezone=UTC
~~~

Có thể giúp giảm biến động của tests, nhưng không thay thế kiểm tra database session timezone và JDBC configuration.

Tạo tests với:

- JVM UTC.
- DB session timezone UTC.
- Một timezone khác có DST nếu domain sử dụng.
- Offset khác nhau nhưng cùng instant.
- LocalDateTime không gắn timezone.

Nếu test cần xác nhận application hoạt động dưới JVM timezone khác, chạy forked test process với timezone riêng hoặc cấu hình test profile rõ ràng. Không thay timezone global trong parallel tests vì có thể ảnh hưởng threads khác.

## 52. Migration test khi đổi kiểu cột

Ví dụ thay `status` từ integer ordinal sang varchar string. Đây là **data migration**, không phải chỉ đổi annotation.

Quy trình:

1. Xác định mapping ordinal cũ và enum order cũ.
2. Viết migration chuyển numeric values thành code/name đúng.
3. Kiểm tra các giá trị ngoài tập đã biết.
4. Deploy theo chiến lược tương thích giữa application versions nếu rolling deployment.
5. Chuyển mapping code sang STRING/converter đúng thời điểm.
6. Test rollback/forward migration strategy.
7. Không xóa cột legacy trước khi mọi instances đã chuyển.

Test migration cần dùng một database chứa **dữ liệu phiên bản cũ**, không chỉ tạo schema mới từ đầu.

## 53. Logging SQL và bind parameters

Hibernate 6 có logger thường dùng:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Dùng để xem:

- Column types/placeholder positions qua SQL.
- INSERT có bind null hay bỏ cột.
- Decimal/timestamp values được bind như thế nào.
- Enum đang lưu ordinal/string/custom code.
- Generated SQL có cast hoặc dialect syntax gì.

Bind logs có thể lộ PII, financial amounts hoặc nội dung riêng tư. Chỉ bật trong test với dữ liệu giả, hoặc có redaction/access/retention controls rõ ràng. Không bật TRACE toàn production như một biện pháp mặc định.

## 54. Test DB constraints và exception translation

Khi persist value vượt precision hoặc NULL vào NOT NULL column, lỗi có thể xuất hiện:

- Lúc Bean Validation trước SQL.
- Lúc Hibernate flush.
- Tại JDBC `executeUpdate`.
- Khi database kiểm tra constraint.
- Tại transaction commit trong một số deferred constraints.

Test nên xác nhận:

- Exception class/wrapped cause ở tầng ứng dụng.
- Constraint name nếu cần phân loại.
- Transaction rollback.
- Không để persistence context tiếp tục sử dụng sau exception khi nó không còn an toàn.
- API trả error code phù hợp, không lộ raw SQL/DB internals.

Không assert toàn bộ message DB nếu message khác nhau giữa driver versions; ưu tiên exception type/constraint metadata ổn định.

## 55. Default value cần test riêng

Ví dụ:

~~~sql
CREATE TABLE probe (
    id BIGINT PRIMARY KEY,
    retry_count INTEGER NOT NULL DEFAULT 0
);
~~~

Ba thao tác khác nhau:

1. INSERT bỏ cột `retry_count` → DB default có thể áp dụng.
2. INSERT `retry_count = 0` → lưu 0.
3. INSERT `retry_count = NULL` → lỗi vì NOT NULL, không tự dùng default.

Hibernate có thể phát INSERT gồm tất cả mapped columns. `@DynamicInsert` (Hibernate-specific) có thể khiến null-valued fields bị bỏ khỏi INSERT trong một số mappings, cho phép DB defaults hoạt động, nhưng thay đổi SQL shape và cần kiểm tra kỹ.

Không dùng default DB làm business default mà không test generated SQL và schema thực tế.

## 56. Boolean converter và legacy representations

Một DB legacy có thể lưu boolean dưới dạng `Y/N`:

~~~java
@Converter
public class YesNoConverter
        implements AttributeConverter<Boolean, String> {

    @Override
    public String convertToDatabaseColumn(Boolean value) {
        if (value == null) return null;
        return value ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String value) {
        if (value == null) return null;
        return switch (value) {
            case "Y" -> true;
            case "N" -> false;
            default -> throw new IllegalArgumentException(
                "Unknown flag: " + value
            );
        };
    }
}
~~~

Test các giá trị `Y`, `N`, NULL và invalid legacy code. Nếu converter chỉ nhận `Y/N` nhưng DB có `y`, `n`, khoảng trắng hoặc giá trị cũ khác, cần quyết định normalize hay reject rõ ràng.

Converter không thay DB CHECK constraint nếu dữ liệu có thể được ghi bởi nhiều ứng dụng.

## 57. Schema precision và scale có thể khác giữa test và production

Ví dụ H2 tự tạo schema từ annotation có thể khác PostgreSQL migration thật. Khi test `NUMERIC(19,4)`:

- Dùng migration production.
- Kiểm tra metadata column.
- Ghi giá trị boundary.
- Đọc raw JDBC value.
- Xác nhận DB rounding/error.
- So sánh behavior giữa driver versions nếu cần.

Đừng chỉ assert Hibernate `SessionFactory` boot thành công; schema validation không bảo đảm mọi numeric edge cases được xử lý như business mong muốn.

## 58. Test các mapping custom theo hai chiều

Một `AttributeConverter` có thể round-trip một chiều nhưng fail chiều ngược:

- DB code không còn tồn tại trong enum.
- String bị trim/lowercase không nhất quán.
- Null bị đổi thành default ngoài ý muốn.
- Decimal text parse theo locale.
- Date format phụ thuộc JVM locale.
- Custom binary/JSON representation đổi version.

Test converter trực tiếp cho logic pure, sau đó test converter tích hợp qua EntityManager/JDBC để xác nhận Hibernate thật sự áp dụng nó.

Đặc biệt với numeric string, dùng `BigDecimal(String)` và locale cố định; không parse `"1,25"` bằng default locale không kiểm soát.

## 59. Checklist mapping test theo kiểu dữ liệu

| Nhóm | Boundary cases | Kiểm tra sau reload |
|---|---|---|
| Integer | Min, max, outside range | Giá trị exact hoặc expected DB error |
| BigDecimal | Precision max, scale max, rounding | Numerical value và scale |
| Float/Double | 0.1, 0.2, large/small values | Tolerance/precision |
| Boolean | true, false, null | SQL type/value |
| LocalDate | Leap day, month/year boundary | Calendar date |
| LocalTime | Midnight, fractional seconds | Precision |
| LocalDateTime | Boundary/fractional precision | Local fields, no assumed zone |
| Instant | Epoch, offsets, nanoseconds | Same instant after normalization |
| OffsetDateTime | Same instant, different offsets | Instant vs offset contract |
| ZonedDateTime | DST gap/overlap | Instant and ZoneId storage |
| Enum | Every constant, renamed/legacy values | DB representation |
| Nullable | Null and non-null | SQL NULL after fresh load |
| Default | Omitted column vs explicit NULL | Actual DB default behavior |

## 60. Quy trình điều tra một mapping sai

Khi test phát hiện giá trị sau reload khác expected:

1. **Xác nhận expected semantics.** Có cần giữ exact scale, offset, ZoneId, enum name hay chỉ numerical/instant equality?
2. **Đọc schema.** Column type, precision/scale, nullability, default, collation, constraints.
3. **Xem generated SQL.** Column có bị bỏ, bind null hay cast không?
4. **Xem JDBC bind/extract.** Driver nhận/trả kiểu nào?
5. **Query raw DB value.** Không dựa vào entity object duy nhất.
6. **Kiểm tra timezone/session config.** JVM, Hibernate JDBC timezone, DB session.
7. **Kiểm tra converter/enum mapping.** ORDINAL/STRING/code và dữ liệu legacy.
8. **Clear context và cache có chủ đích.** Tránh first-level/L2 cache che SQL.
9. **Chạy trên production-like DB.** Xác nhận dialect/driver.
10. **Thêm regression test.** Test đúng boundary đã gây lỗi.

Không sửa mapping chỉ để làm test pass nếu chưa xác định domain contract cần bảo toàn giá trị nào.

## 61. Bài tập thực hành

1. Tạo entity có `Integer`, `Long`, `BigInteger`, `BigDecimal(19,4)`; test min/max và overflow.
2. Persist `BigDecimal("12.3")`, reload và so sánh `equals`, `compareTo`, `scale`.
3. Ghi decimal có 5 chữ số fraction vào `NUMERIC(19,4)` trên production-like DB; xác định DB round/reject.
4. So sánh `double 0.1 + 0.2` với BigDecimal và viết assertions phù hợp.
5. Test `LocalDate` vào DATE với leap day.
6. Test `Instant` nanoseconds vào timestamp precision microseconds; định nghĩa normalization.
7. Lưu cùng instant bằng hai OffsetDateTimes khác nhau; kiểm tra database và quyết định có cần lưu offset gốc không.
8. Tạo test DST gap/overlap cho ZoneId mà sản phẩm hỗ trợ.
9. Dùng enum ORDINAL, chèn một constant ở giữa và mô phỏng dữ liệu cũ bị đọc sai.
10. Chuyển enum sang STRING hoặc converter code ổn định; viết migration test.
11. Test nullable Integer/Boolean/Instant và query `IS NULL`.
12. So sánh INSERT bỏ column, INSERT NULL và INSERT explicit default.
13. Viết AttributeConverter cho Y/N; test null và unknown legacy value.
14. Chạy cùng mapping tests trên H2 và PostgreSQL Testcontainers; giải thích khác biệt.
15. Viết test flush-clear-reload và test transaction commit mới.
16. Kiểm tra SQL generated/bind values bằng logging trên fake data.
17. Tạo migration cũ với ordinal enum và test upgrade sang string.
18. Kiểm tra Bean Validation `@NotNull` và DB `NOT NULL` ở hai đường ORM/JDBC.

## 62. Sơ đồ chiến lược kiểm thử

~~~mermaid
flowchart TD
    A["Chọn field Java và domain contract"] --> B["Kiểm tra JPA/Hibernate mapping"]
    B --> C["Kiểm tra schema migration + column type"]
    C --> D["Tạo boundary/null/legacy test values"]
    D --> E["Persist qua EntityManager"]
    E --> F["Flush"]
    F --> G["Clear/đóng persistence context"]
    G --> H["Reload từ transaction/context mới"]
    H --> I{"Value có khớp contract?"}
    I -- "Có" --> J["Test raw JDBC + DB constraints"]
    I -- "Không" --> K["Inspect SQL, bind, converter, dialect"]
    K --> L["Sửa mapping/migration/domain normalization"]
    L --> E
    J --> M["Chạy trên production-like DB"]
    M --> N["Lưu regression tests"]
~~~

## 63. Tổng kết

**Kiểm thử ánh xạ kiểu dữ liệu là kiểm thử hợp đồng giữa Java, Hibernate, JDBC và database.** Một annotation đúng cú pháp chưa đủ chứng minh giá trị được lưu và đọc lại đúng.

- Với **số**, kiểm tra range, `BigDecimal` precision/scale, rounding và floating-point semantics.
- Với **thời gian**, xác định rõ local date/time hay instant; kiểm tra timezone, offset, ZoneId, DST và fractional precision.
- Với **enum**, tránh ordinal nếu enum có thể reorder; `STRING` hoặc converter code ổn định vẫn cần migration khi contract thay đổi.
- Với **null**, phân biệt primitive/wrapper, SQL NULL, default, Bean Validation và database constraints.
- Với **integration tests**, persist → flush → clear → reload; nếu cần chứng minh commit, dùng transaction/EntityManager mới.
- Với **dialect**, chạy tests trên database và JDBC driver gần production; H2 không thay thế được mọi DB-specific behavior.
- Với **regression**, lưu các boundary và legacy cases để migration/nâng cấp Hibernate không âm thầm đổi dữ liệu.

Hãy bắt đầu bằng việc viết rõ domain muốn bảo toàn **giá trị số, scale, instant, offset, zone, enum code hay null semantics nào**. Sau đó thiết kế test round-trip và schema constraints tương ứng. Khi hợp đồng được xác định rõ, các lỗi mapping mới có thể được phát hiện trước khi dữ liệu production bị biến đổi.
