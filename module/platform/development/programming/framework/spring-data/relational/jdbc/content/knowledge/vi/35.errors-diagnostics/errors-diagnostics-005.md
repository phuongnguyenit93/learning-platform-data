# Lỗi constructor, alias cột, null và kiểu dữ liệu

Khi Spring Data JDBC đọc một hàng từ database, framework phải thực hiện hai việc: tạo instance của domain type và chuyển từng giá trị trong ResultSet vào thuộc tính tương ứng. Lỗi ở một trong hai bước thường xuất hiện dưới dạng MappingException, lỗi chuyển đổi kiểu, lỗi không tìm thấy cột hoặc giá trị không đúng như mong đợi.

Bốn nhóm nguyên nhân thường gặp:

- **Constructor:** Spring Data không xác định được constructor/factory phù hợp hoặc không tìm được tên tham số.
- **Alias cột:** kết quả SQL không cung cấp tên cột mà mapping metadata mong đợi, đặc biệt khi JOIN nhiều bảng.
- **Null:** database trả NULL nhưng model hoặc constructor không biểu diễn được giá trị đó.
- **Kiểu dữ liệu:** Java type, SQL type, JDBC driver và converter không thống nhất.

Bài học này giải thích cách Spring Data JDBC tạo object, cách ánh xạ tên cột, cách xử lý nullability và type conversion, cách dùng custom converter, và quy trình khoanh vùng lỗi bằng integration test.

## 1. Spring Data JDBC đọc một hàng như thế nào?

Với repository query hoặc custom query trả về entity, Spring Data JDBC dùng MappingJdbcConverter và RowMapper của nó để chuyển dữ liệu database thành domain object.

Quy trình khái quát:

~~~text
SQL query
    |
    v
ResultSet từ JDBC driver
    |
    v
Đọc column labels và values
    |
    v
Mapping metadata + naming strategy
    |
    +---- Chọn constructor/factory
    |
    +---- Chuyển đổi Java/JDBC types
    |
    +---- Gán các thuộc tính còn lại
    |
    v
Domain object
~~~

Mapping metadata lấy thông tin từ class, field và annotation như @Table, @Column, @Id, @Embedded, @MappedCollection và @PersistenceCreator.

Spring Data JDBC mặc định ánh xạ field của object. Nó không dùng JavaBean getter/setter như một số ORM để khám phá toàn bộ property metadata. Setter, wither hoặc field access có thể được dùng để gán giá trị sau khi object được tạo.

Điều này có nghĩa một class compile được chưa chắc đã có thể được materialize từ ResultSet. Constructor, tên tham số, field mapping và dữ liệu SQL phải khớp nhau.

## 2. Quy tắc chọn constructor

Spring Data tự xác định constructor hoặc factory method dùng để tạo entity. Quy tắc tổng quát:

1. Nếu có một static factory method được đánh dấu @PersistenceCreator, factory đó được dùng.
2. Nếu class chỉ có một constructor, constructor đó được dùng.
3. Nếu có nhiều constructor và đúng một constructor được đánh dấu @PersistenceCreator, constructor đó được dùng.
4. Nếu type là Java record, canonical constructor được dùng.
5. Nếu không có lựa chọn phù hợp ở trên nhưng có no-argument constructor, constructor không tham số được dùng; các constructor khác bị bỏ qua.

Ví dụ entity bất biến:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderCode;
    private final String status;

    public PurchaseOrder(
            Long id,
            String orderCode,
            String status
    ) {
        this.id = id;
        this.orderCode = orderCode;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Trong ví dụ này, constructor có ba tham số cần được Spring Data ánh xạ với các property tương ứng. Nếu tên tham số không được giữ trong bytecode, framework có thể không biết tham số nào ứng với property nào.

### 2.1. Giữ tên tham số trong bytecode

Tên tham số constructor cần có trong class file hoặc được cung cấp bằng @ConstructorProperties.

Với javac, có thể bật compiler flag:

~~~text
-parameters
~~~

Maven compiler plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Cấu hình này hữu ích khi Spring Data cần khám phá tên tham số constructor theo reflection. Kiểm tra cấu hình compiler của module chứa entity, không chỉ module test.

### 2.2. Chọn constructor rõ ràng bằng @PersistenceCreator

Nếu class có nhiều constructor, đánh dấu constructor dùng để persistence:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderCode;
    private final String status;

    public PurchaseOrder(Long id, String orderCode, String status) {
        this.id = id;
        this.orderCode = orderCode;
        this.status = status;
    }

    @PersistenceCreator
    public PurchaseOrder(Long id, String orderCode) {
        this(id, orderCode, "DRAFT");
    }
}
~~~

Ví dụ trên chỉ hợp lý nếu constructor được chọn có thể nhận đủ dữ liệu cần thiết cho model. Nếu query trả về một constructor property nhưng không có column tương ứng, object có thể không được tạo.

Không dùng @PersistenceCreator để che giấu việc SQL thiếu dữ liệu bắt buộc. Hãy đảm bảo query thực sự trả về tất cả constructor properties cần thiết.

### 2.3. Java record

Record có canonical constructor được Spring Data nhận diện:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderCode,
        String status
) {
}
~~~

Record phù hợp với mô hình immutable. Tên component của record trở thành tên tham số constructor và property, vì vậy vẫn cần đối chiếu với mapping metadata và column labels của query.

## 3. Lỗi constructor thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| MappingException khi đọc entity | Không tìm được constructor parameter tương ứng | Kiểm tra constructor và tên tham số |
| Constructor nhận null ngoài dự kiến | Query thiếu cột hoặc cột trả NULL | Kiểm tra ResultSet column labels và dữ liệu |
| Không thể materialize immutable entity | Thiếu constructor parameter name metadata | Bật -parameters hoặc @ConstructorProperties |
| Framework chọn constructor không mong muốn | Có nhiều constructor nhưng không đánh dấu rõ | Dùng @PersistenceCreator |
| Constructor property không có trong query | SELECT bỏ cột cần thiết | Bổ sung cột hoặc dùng DTO phù hợp |
| Transient field trong constructor | Field không được persistence mapping | Không đưa transient property vào persistence constructor |

### 3.1. Constructor parameter phải tương ứng với property

Ví dụ sai:

~~~java
public PurchaseOrder(Long id, String code, String status) {
    this.id = id;
    this.orderCode = code;
    this.status = status;
}
~~~

Nếu parameter name được giữ là code nhưng property tên orderCode, Spring Data không thể tự giả định chúng là một property nếu không có metadata/conversion phù hợp.

Cách sửa đơn giản là đặt tên tham số trùng với property:

~~~java
public PurchaseOrder(Long id, String orderCode, String status) {
    this.id = id;
    this.orderCode = orderCode;
    this.status = status;
}
~~~

Nếu phải dùng tên khác, kiểm tra khả năng dùng annotation hoặc factory method thích hợp trong phiên bản Spring Data đang chạy.

### 3.2. @Transient không phù hợp với persistence constructor

Thuộc tính @Transient không được đọc/ghi như cột database. Nếu constructor yêu cầu tham số tương ứng với thuộc tính transient, MappingJdbcConverter không có giá trị persistent để truyền vào.

Đưa giá trị dẫn xuất vào method/factory sau khi materialize hoặc xử lý trong callback phù hợp thay vì yêu cầu nó như constructor parameter bắt buộc.

## 4. Naming strategy và tên cột

Theo convention, Spring Data JDBC ánh xạ class và property sang tên bảng/cột theo snake_case.

Ví dụ:

| Java property | Tên cột theo convention |
|---|---|
| orderCode | order_code |
| createdAt | created_at |
| customerId | customer_id |
| shippingAddress | shipping_address |

Có thể thay đổi tên cột bằng @Column:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("external_order_ref")
    private String orderCode;
}
~~~

Trong trường hợp này, property orderCode được ánh xạ với cột external_order_ref.

### 4.1. Chú ý identifier được quote

Spring Data JDBC mặc định có thể quote table/column identifiers được tạo từ mapping metadata. Với nhiều database, identifier được quote có thể phân biệt chữ hoa/thường.

Ví dụ:

~~~sql
SELECT order_code
FROM purchase_orders;
~~~

và:

~~~sql
SELECT order_code AS "orderCode"
FROM purchase_orders;
~~~

có thể tạo ra column labels khác nhau tùy database và cách quote.

Hãy dùng tên đơn giản, nhất quán theo naming strategy. Nếu cần tên đặc biệt, xác định rõ @Column và SQL alias, rồi kiểm thử trên database thật.

## 5. Alias cột trong @Query

Custom @Query dùng RowMapper mặc định tương tự query do Spring Data JDBC tạo. Vì vậy, câu SELECT phải trả về đúng định dạng mà mapper mong đợi.

Ví dụ entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    private String status;
}
~~~

Query:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT
            id,
            order_code,
            status
        FROM purchase_orders
        WHERE order_code = :orderCode
        """)
    Optional<PurchaseOrder> findByOrderCode(
            @Param("orderCode") String orderCode
    );
}
~~~

Với custom query trả về entity:

- Các cột cần cho constructor phải có trong kết quả.
- Các property được gán sau qua setter, wither hoặc field access có thể không bắt buộc phải có trong SELECT.
- Property không có column tương ứng sẽ không được gán.
- Root, embedded entity và one-to-one relationship có thể được populate từ query.
- Collection quan hệ như List, Set, Map và array entity được tải bằng query riêng do Spring Data JDBC tạo.

Không nên giả định một câu JOIN tùy ý sẽ tự dựng toàn bộ aggregate graph giống một ORM eager fetch.

## 6. Alias cho JOIN và quan hệ one-to-one

Khi JOIN nhiều bảng, tên cột trùng nhau là nguồn lỗi phổ biến.

Ví dụ:

~~~sql
SELECT *
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Cả hai bảng có thể chứa cột id, status, created_at hoặc name. Kết quả có column label trùng nhau khiến mapper không phân biệt được giá trị thuộc property nào.

Hãy liệt kê cột và đặt alias rõ ràng:

~~~sql
SELECT
    o.id AS id,
    o.order_code AS order_code,
    o.status AS status,
    c.id AS customer_id,
    c.display_name AS customer_display_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = :id;
~~~

Nếu aggregate có một quan hệ one-to-one tên customer và property bên trong là displayName, Spring Data JDBC yêu cầu cột quan hệ được đặt prefix bằng tên property quan hệ và dấu gạch dưới, ví dụ customer_display_name.

Tên alias cần khớp mapping metadata mà converter mong đợi. Nếu entity dùng @Column, hãy kiểm tra column name thực tế trong mapping.

### 6.1. Không dùng SELECT * trong query mapping entity

SELECT * dễ gây:

- Cột trùng tên giữa các bảng.
- Thay đổi schema làm kết quả query thay đổi ngoài ý muốn.
- Cột thừa không cần thiết.
- Alias không ổn định.
- Constructor parameter nhận nhầm hoặc thiếu dữ liệu.

Với query mapping entity, hãy khai báo rõ danh sách cột và alias. Với query báo cáo, ưu tiên DTO/read model riêng thay vì ép kết quả JOIN thành aggregate root.

## 7. Lỗi alias thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Constructor không được tạo | Alias không khớp constructor property | Đặt alias theo property/mapping metadata |
| Một field luôn null | SELECT thiếu cột hoặc alias sai | Kiểm tra column label thực tế |
| Property nhận giá trị từ bảng khác | JOIN trả cột trùng tên | Đặt alias riêng cho từng cột |
| One-to-one object không được populate | Thiếu prefix quan hệ | Dùng relationship_property |
| Query chạy trong DB console nhưng repository lỗi | SQL chạy được nhưng result shape không khớp RowMapper | Kiểm tra ResultSet metadata và mapping |
| Chỉ lỗi trên database production | Identifier quoting/case khác H2 | Test với database/driver production |

## 8. SQL NULL và Java nullability

Database có thể trả NULL cho một cột. Java model phải có cách biểu diễn giá trị đó.

Với thuộc tính có thể NULL, nên dùng boxed type:

~~~java
private Integer retryCount;
private Boolean active;
private BigDecimal discount;
private Instant processedAt;
~~~

Primitive không thể biểu diễn null:

~~~java
private int retryCount;
private boolean active;
~~~

Nếu cột retry_count hoặc active cho phép NULL, primitive có thể làm mất khác biệt giữa “không có giá trị” và giá trị mặc định như 0 hoặc false, hoặc khiến bước mapping không thể hoàn tất theo kiểu dữ liệu yêu cầu.

Quy tắc thực tế:

- Cột NOT NULL và có default nghiệp vụ rõ ràng: primitive có thể phù hợp.
- Cột nullable: dùng wrapper/reference type.
- Constructor parameter có thể nhận NULL: dùng kiểu reference tương ứng.
- Giá trị bắt buộc: enforce NOT NULL ở database và validate ở domain/application layer.

### 8.1. Không nhầm NULL với 0, false hoặc chuỗi rỗng

| Database value | Java reference type | Primitive |
|---|---|---|
| NULL | null | Không thể biểu diễn trực tiếp |
| 0 | Integer.valueOf(0) | 0 |
| FALSE | Boolean.FALSE | false |
| '' | Chuỗi rỗng | Không áp dụng |

Không tự thay NULL bằng 0 chỉ để mapping chạy được. Hãy quyết định semantics nghiệp vụ trước.

### 8.2. Embedded object có toàn bộ cột NULL

Với @Embedded, nếu tất cả cột của embedded object đều NULL, mặc định Spring Data JDBC có thể đặt toàn bộ property embedded thành null theo cấu hình onEmpty.

Nếu muốn tạo embedded object rỗng với các property null, có thể dùng chế độ USE_EMPTY.

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL)
    private ContactDetails contactDetails;
}
~~~

Hãy test riêng hai trường hợp:

- Tất cả cột embedded đều NULL.
- Chỉ một vài cột embedded NULL.

Điều này tránh nhầm “không có contact details” với “có contact details nhưng chưa điền đủ”.

## 9. Kiểu Java và SQL cần tương thích

Spring Data JDBC hỗ trợ các kiểu thông dụng như primitive/boxed types, enum, String, một số kiểu ngày giờ Java và các kiểu mà JDBC driver chấp nhận. Database và driver cụ thể vẫn quyết định một số conversion.

Ví dụ:

| Java type | SQL type thường dùng | Lưu ý |
|---|---|---|
| Long | BIGINT | Kiểm tra range |
| Integer | INTEGER | Tránh overflow |
| BigDecimal | DECIMAL/NUMERIC | Phù hợp số tiền và precision |
| Boolean | BOOLEAN hoặc kiểu tương ứng của DB | Có thể cần converter nếu schema dùng CHAR |
| String | VARCHAR/TEXT | Kiểm tra length/encoding |
| LocalDate | DATE | Chỉ lưu ngày |
| LocalDateTime | TIMESTAMP | Không mang timezone |
| Instant | Kiểm tra converter/driver/dialect | Biểu diễn thời điểm tuyệt đối |
| Enum | VARCHAR | Spring Data mặc định ghi tên enum |
| UUID | UUID hoặc kiểu vendor | Phụ thuộc database/driver |

Đừng giả định một kiểu Java được ánh xạ giống nhau trên mọi database. Kiểm tra DDL, JDBC metadata và driver đang dùng.

### 9.1. BigDecimal và precision/scale

Với tiền:

~~~sql
unit_price NUMERIC(15, 2) NOT NULL
~~~

Java:

~~~java
private BigDecimal unitPrice;
~~~

Nếu database có scale 2 nhưng ứng dụng ghi giá trị có nhiều chữ số thập phân, database có thể làm tròn, từ chối hoặc chuyển đổi theo dialect. Hãy xác định rounding policy ở nghiệp vụ và test giá trị biên.

Không dùng double cho tiền nếu cần decimal precision ổn định.

### 9.2. Enum được lưu theo tên

Spring Data JDBC mặc định map enum bằng tên:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Database lưu các giá trị tương ứng như DRAFT, CONFIRMED, CANCELLED.

Nếu đổi tên enum trong Java nhưng dữ liệu cũ vẫn chứa tên cũ, mapping có thể thất bại. Nếu schema cần mã ổn định độc lập với tên enum, dùng custom converter để lưu một code rõ ràng.

### 9.3. Ngày giờ và timezone

Không coi LocalDateTime là thời điểm UTC. LocalDateTime không chứa timezone hoặc offset.

Với thời điểm cần so sánh giữa nhiều server, chọn kiểu có semantics rõ như Instant và kiểm tra converter/driver/database. Với lịch làm việc địa phương, LocalDate hoặc LocalDateTime có thể phù hợp hơn nếu timezone được quản lý riêng.

Test nên bao gồm:

- Giá trị UTC.
- Giá trị có offset.
- Giá trị gần thời điểm chuyển DST nếu ứng dụng dùng timezone địa phương.
- NULL.
- Độ chính xác phần giây mà database thực sự lưu.

## 10. Dùng custom converter khi kiểu mặc định không đủ

Spring Data JDBC cho phép đăng ký Spring Converter để chuyển một property giữa Java type và database type.

Ví dụ database lưu boolean dưới dạng ký tự T/F.

Writing converter:

~~~java
@WritingConverter
public class BooleanToStringConverter
        implements Converter<Boolean, String> {

    @Override
    public String convert(Boolean source) {
        return Boolean.TRUE.equals(source) ? "T" : "F";
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class StringToBooleanConverter
        implements Converter<String, Boolean> {

    @Override
    public Boolean convert(String source) {
        return source != null && source.equalsIgnoreCase("T");
    }
}
~~~

Vì Boolean và String đều là simple type, Spring Data cần biết converter dùng cho chiều đọc hay chiều ghi. Dùng @ReadingConverter và @WritingConverter để khai báo hướng rõ ràng.

### 10.1. Đăng ký converter

Với cấu hình Spring Data JDBC tùy chỉnh:

~~~java
@Configuration
public class JdbcMappingConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new BooleanToStringConverter(),
                new StringToBooleanConverter()
        );
    }
}
~~~

Nếu dùng Spring Boot để bootstrap Spring Data JDBC, có thể đăng ký bean JdbcCustomConversions theo cấu hình Boot hỗ trợ.

Với phiên bản Spring Data JDBC hiện hành, không nên override jdbcCustomConversions() một cách tùy tiện vì có thể bỏ sót converter được dialect cung cấp. Ưu tiên userConverters() hoặc cấu hình bean theo hướng dẫn đúng phiên bản.

### 10.2. Converter chỉ áp dụng ở property level

Custom converters của Spring Data Relational hiện xử lý chuyển đổi một property Java thành một giá trị database và ngược lại. Không dùng một converter property-level để biến một object phức tạp thành nhiều cột tùy ý.

Nếu value object cần nhiều cột, cân nhắc @Embedded hoặc mapping rõ ràng khác.

### 10.3. JdbcValue khi cần chỉ định JDBC type

Khi driver không suy luận được kiểu bind hoặc cần chỉ định SQL type cụ thể, custom write converter có thể trả JdbcValue chứa giá trị và JDBCType.

Ví dụ này hữu ích với database-specific type, NULL parameter hoặc kiểu mà driver không thể suy luận ổn định.

## 11. Phân biệt lỗi Spring Data mapping và lỗi RowMapper tự viết

Hai đường đọc dữ liệu có converter khác nhau:

~~~text
Repository / @Query trả về domain entity
        |
        v
MappingJdbcConverter + RowMapper Spring Data
        |
        v
Constructor + @Column + CustomConversions

JdbcTemplate.query(..., RowMapper tự viết)
        |
        v
ResultSet
        |
        v
Code mapping do ứng dụng viết
~~~

Nếu dùng JdbcTemplate:

~~~java
List<OrderSummary> summaries = jdbcTemplate.query(
        """
        SELECT id, order_code, status
        FROM purchase_orders
        WHERE status = ?
        """,
        (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("order_code"),
                rs.getString("status")
        ),
        "OPEN"
);
~~~

Ở đây, ứng dụng tự quyết định cách gọi getLong, getString và cách xử lý NULL. MappingJdbcConverter, @PersistenceCreator và custom conversions của Spring Data JDBC không tự áp dụng cho RowMapper này.

Nếu cột nullable, dùng getObject với wrapper type hoặc kiểm tra wasNull():

~~~java
int raw = rs.getInt("retry_count");
Integer retryCount = rs.wasNull() ? null : raw;
~~~

Không giả định lỗi trong RowMapper là lỗi của Spring Data repository. Hãy xác định chính xác đường đọc đang chạy.

## 12. Custom RowMapper cho @Query

Spring Data JDBC cho phép khai báo RowMapper hoặc ResultSetExtractor tùy chỉnh cho custom query.

Ví dụ:

~~~java
@Query(
    value = """
        SELECT id, order_code, status
        FROM purchase_orders
        WHERE status = :status
        """,
    rowMapperRef = "orderSummaryRowMapper"
)
List<OrderSummary> findSummaries(@Param("status") String status);
~~~

Bean:

~~~java
@Bean
RowMapper<OrderSummary> orderSummaryRowMapper() {
    return (rs, rowNum) -> new OrderSummary(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status")
    );
}
~~~

Khi dùng custom RowMapper hoặc ResultSetExtractor, mapping do ứng dụng kiểm soát. Spring Data JDBC không chạy Entity Callbacks và Lifecycle Events cho result mapping đó, vì custom mapper có thể phát sinh callback/event riêng nếu cần.

Đây là một lựa chọn tốt cho DTO/read model hoặc query JOIN phức tạp mà không cần materialize aggregate.

## 13. Chẩn đoán bằng ResultSet metadata

Khi nghi ngờ alias hoặc kiểu dữ liệu, kiểm tra column labels mà JDBC driver thực sự trả về.

~~~java
jdbcTemplate.query(
        """
        SELECT
            o.id AS order_id,
            o.order_code AS order_code,
            c.display_name AS customer_name
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = ?
        """,
        rs -> {
            ResultSetMetaData metadata = rs.getMetaData();

            for (int i = 1; i <= metadata.getColumnCount(); i++) {
                log.info(
                        "label={}, type={}, typeName={}, nullable={}",
                        metadata.getColumnLabel(i),
                        metadata.getColumnType(i),
                        metadata.getColumnTypeName(i),
                        metadata.isNullable(i)
                );
            }
        },
        orderId
);
~~~

Kiểm tra columnLabel thay vì chỉ columnName vì alias có thể thay đổi nhãn mà mapper nhìn thấy.

Khi query chạy trong database console nhưng Spring Data JDBC lỗi, ResultSet metadata là một trong những bằng chứng hữu ích nhất.

## 14. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| MappingException khi tạo entity | Constructor không phù hợp hoặc thiếu parameter name | Kiểm tra constructor, @PersistenceCreator và -parameters |
| No column found / property luôn null | Alias hoặc @Column không khớp | In ResultSet column labels |
| JOIN trả sai dữ liệu | Cột trùng tên giữa nhiều bảng | Bỏ SELECT *, đặt alias riêng |
| Primitive nhận giá trị mặc định | SQL NULL không được biểu diễn trong model | Dùng wrapper hoặc NOT NULL |
| ConverterNotFoundException | Thiếu converter cho Java/SQL type | Kiểm tra JdbcCustomConversions |
| Enum mapping thất bại | Giá trị database không khớp tên enum | Kiểm tra dữ liệu cũ và converter |
| Numeric overflow | SQL range lớn hơn/khác Java type | Dùng Long/BigDecimal và kiểm tra precision |
| Timestamp lệch | Timezone hoặc precision không thống nhất | Kiểm tra DB type, driver và Java time type |
| Query entity thiếu child | Custom @Query không dựng collection relationship theo JOIN | Kiểm tra query mapping; dùng DTO hoặc query riêng |
| H2 chạy, production lỗi | Khác biệt dialect/driver/type | Integration test trên database thật |

## 15. Kiểm thử constructor và alias

Dùng @DataJdbcTest để xác nhận mapping qua repository với schema kiểm thử.

Ví dụ entity immutable:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private final Long id;

    @Column("order_code")
    private final String orderCode;

    private final String status;

    @PersistenceCreator
    public PurchaseOrder(Long id, String orderCode, String status) {
        this.id = id;
        this.orderCode = orderCode;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Test nên kiểm tra:

- Repository đọc được entity từ bảng thật.
- Custom @Query trả đủ constructor columns.
- Alias khớp column mapping.
- Cột nullable trả null đúng cách.
- JOIN alias không bị trùng.
- Một test cố ý bỏ constructor column để xác nhận lỗi mapping được phát hiện.

Đừng chỉ test một query derived đơn giản nếu production sử dụng nhiều custom JOIN query.

## 16. Kiểm thử null và type conversion

Một ma trận test nhỏ có thể bao gồm:

| Dữ liệu database | Model mong đợi |
|---|---|
| retry_count = NULL | Integer null |
| retry_count = 0 | Integer 0 |
| active = TRUE | Boolean true |
| amount = 123.45 | BigDecimal tương ứng |
| status = CONFIRMED | Enum CONFIRMED |
| created_at = NULL | Instant/LocalDateTime null nếu property nullable |
| enum code không hợp lệ | Lỗi mapping hoặc converter xử lý theo policy |

Với custom converter, test cả hai chiều:

1. Java object được ghi xuống database theo representation mong đợi.
2. Giá trị database được đọc lại thành Java object đúng.

Có thể truy vấn raw column bằng JdbcTemplate để xác nhận representation, sau đó đọc qua repository để xác nhận converter chiều đọc.

## 17. Cách đọc lỗi và log

Khi mapping thất bại, đọc exception chain từ ngoài vào trong:

- Lớp ngoài có thể là DataAccessException.
- Cause bên trong có thể là MappingException hoặc ConversionException.
- Root cause có thể là SQLException từ JDBC driver.

Ghi lại:

- SQL thực tế.
- Parameter type và giá trị an toàn để log.
- ResultSet column labels.
- Java property/constructor parameter bị lỗi.
- Database type từ metadata.
- Driver name/version.
- Spring Data Relational version.

Không log dữ liệu nhạy cảm hoặc toàn bộ row production chỉ để chẩn đoán mapping. Dùng test fixture nhỏ có dữ liệu đại diện.

## 18. Quy trình xử lý lỗi mapping

**Bước 1 — Xác định đường đọc.** Repository generated query, custom @Query hay JdbcTemplate RowMapper?

**Bước 2 — Xác định target type.** Aggregate root, embedded entity, one-to-one property hay DTO?

**Bước 3 — Kiểm tra constructor.** Constructor nào được chọn? Parameter names có trong bytecode không?

**Bước 4 — Kiểm tra query result shape.** Các constructor columns có đủ không? Alias có trùng không?

**Bước 5 — Đối chiếu mapping metadata.** @Column, naming strategy, @Embedded và quan hệ one-to-one.

**Bước 6 — Kiểm tra nullability.** Cột có thể NULL không? Java property có biểu diễn null không?

**Bước 7 — Kiểm tra Java/SQL type.** JDBC driver trả type nào? Có cần custom converter không?

**Bước 8 — Kiểm tra database thật.** Chạy test với engine/driver production.

**Bước 9 — Viết regression test.** Lưu fixture gây lỗi và xác nhận mapping sau khi sửa.

~~~text
Mapping error
     |
     v
Repository @Query hay JdbcTemplate?
     |
     +---- Spring Data mapping
     |          |
     |          v
     |     Constructor / parameter names
     |          |
     |          v
     |     Column labels / @Column / alias
     |          |
     |          v
     |     Nullability / Java-SQL conversion
     |
     +---- Custom RowMapper
                |
                v
           ResultSet getters
                |
                v
           wasNull / JDBC type / converter
                |
                v
         Reproduce on target database
                |
                v
           Add regression test
~~~

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Có nhiều constructor nhưng không đánh dấu | Framework chọn sai hoặc báo lỗi | Dùng @PersistenceCreator |
| Không bật -parameters | Constructor argument name không được khám phá | Bật compiler parameter metadata |
| SELECT * trong JOIN | Column labels trùng và mapping không ổn định | Chọn cột và alias tường minh |
| Đặt alias tùy ý | Mapper không tìm thấy property | Theo naming strategy và @Column |
| Dùng primitive cho cột nullable | Mất phân biệt NULL với giá trị mặc định | Dùng wrapper type |
| Dùng enum name như mã dữ liệu bất biến | Đổi tên enum làm dữ liệu cũ không map được | Dùng code ổn định và converter |
| Dùng double cho tiền | Sai số thập phân | Dùng BigDecimal |
| Dùng LocalDateTime như UTC | Timestamp sai khi nhiều timezone | Chọn kiểu thời gian và quy ước timezone rõ |
| Override jdbcCustomConversions tùy tiện | Có thể bỏ converter do dialect cung cấp | Dùng userConverters hoặc bean phù hợp |
| Nghĩ @Query JOIN tự dựng toàn bộ collection | Aggregate thiếu child | Dùng DTO hoặc query riêng cho collection |
| Test chỉ trên H2 | Bỏ sót khác biệt driver/database | Test trên database production-compatible |
| Dùng RowMapper rồi mong MappingJdbcConverter chạy | Custom mapping không áp dụng converter Spring Data | Viết mapping/conversion trong RowMapper |

## 20. Bài tập tự suy luận

**Tình huống A — Constructor thiếu tham số**

Một record có id, orderCode và status, nhưng custom @Query chỉ SELECT id và order_code. Vì sao mapping thất bại?

**Gợi ý:** Canonical constructor cần đủ component values. Bổ sung status hoặc dùng DTO/constructor phù hợp.

**Tình huống B — Constructor name không tìm thấy**

Một immutable entity có constructor parameter tên code nhưng property là orderCode. Nên kiểm tra gì?

**Gợi ý:** Parameter name phải khớp property mapping. Đổi tên tham số hoặc cấu hình constructor/factory phù hợp.

**Tình huống C — Alias JOIN trùng**

Hai bảng đều có cột id và name. SELECT * trả về dữ liệu khó map. Cần làm gì?

**Gợi ý:** Liệt kê từng cột, alias rõ ràng và dùng prefix cho property one-to-one.

**Tình huống D — Nullable count**

Database cho phép retry_count NULL nhưng Java entity dùng int. Có nên đổi NULL thành 0 trong SQL không?

**Gợi ý:** Chỉ khi nghiệp vụ định nghĩa hai giá trị tương đương. Nếu NULL mang nghĩa riêng, dùng Integer.

**Tình huống E — Boolean lưu T/F**

Database legacy lưu T/F trong VARCHAR nhưng entity dùng Boolean. Cần gì?

**Gợi ý:** Đăng ký WritingConverter và ReadingConverter để định nghĩa hai chiều chuyển đổi.

**Tình huống F — Custom RowMapper**

JdbcTemplate RowMapper đọc một cột nullable bằng getInt. Kết quả trả 0 dù database chứa NULL. Vì sao?

**Gợi ý:** getInt trả 0 cho SQL NULL. Gọi wasNull hoặc dùng getObject với Integer.

## 21. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| MappingJdbcConverter | Chuyển ResultSet/Row thành domain object |
| @PersistenceCreator | Chọn constructor hoặc factory dùng cho persistence |
| -parameters | Giữ tên tham số constructor trong bytecode |
| Java record | Dùng canonical constructor |
| @Column | Ánh xạ property với tên cột cụ thể |
| NamingStrategy | Quy định tên bảng/cột theo convention |
| SQL alias | Cung cấp column label đúng cho custom query |
| @Embedded | Ánh xạ value object vào các cột cùng bảng |
| Wrapper type | Biểu diễn SQL NULL |
| BigDecimal | Biểu diễn số decimal chính xác |
| @ReadingConverter | Chuyển database value thành Java value |
| @WritingConverter | Chuyển Java value thành database value |
| JdbcCustomConversions | Đăng ký converter cho Spring Data JDBC |
| JdbcValue | Gắn JDBCType rõ ràng với giá trị ghi |
| RowMapper | Tự chuyển ResultSet thành DTO/entity |
| Integration test | Xác nhận mapping trên database/driver thực tế |

**Lỗi constructor, alias, null và kiểu dữ liệu đều bắt nguồn từ việc object model không khớp với dữ liệu mà JDBC trả về.** Hãy kiểm tra constructor và parameter names trước, sau đó xác nhận column labels/alias, nullability và type conversion. Dùng @Column và @PersistenceCreator khi cần metadata tường minh, custom converters cho kiểu đặc thù, và integration test trên database mục tiêu để khóa lại hành vi mapping.

## Tài liệu tham khảo

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): naming strategy, constructor mapping, supported types, @Column, @Embedded và custom converters.
- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): constructor detection, @PersistenceCreator, records và parameter name discovery.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): custom @Query, RowMapper expectations, required constructor columns, relationship aliases và custom RowMapper.
- [Spring Data Relational — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): @ReadingConverter, @WritingConverter, userConverters và JdbcValue.

