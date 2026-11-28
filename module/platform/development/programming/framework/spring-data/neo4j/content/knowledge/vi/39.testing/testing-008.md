# Kiểm thử ID, version, kiểu dữ liệu và converter

Kiểm thử mapping của Spring Data Neo4j (SDN) cần xác nhận dữ liệu đi qua cả hai chiều: từ entity Java xuống property/node trong Neo4j và từ graph trở lại đúng kiểu Java. Một bài test chỉ kiểm tra object sau khi gọi constructor không chứng minh được ID đã được sinh, version đã tăng, temporal type được lưu đúng hay custom converter đã được đăng ký.

Trong module `SPRING_DATA_NEO4J`, hãy dùng integration test với Neo4j thật để kiểm tra các hợp đồng persistence quan trọng. `@DataNeo4jTest` cung cấp repository, client, template và transaction infrastructure; Testcontainers hoặc Neo4j Test Harness cung cấp database để thực thi mapping thực tế. Các test nên kiểm tra ID, version, giá trị đọc lại và biểu diễn property trong graph khi kiểu lưu trữ có thể khác kiểu Java.

## 1. Những gì cần được kiểm thử

Một bộ test mapping nên bao phủ ít nhất bốn nhóm:

| Nhóm | Điều cần xác minh | Ví dụ |
|---|---|---|
| ID | ID được sinh hoặc giữ đúng theo chiến lược đã khai báo | `@GeneratedValue`, business ID, `UUIDStringGenerator` |
| Version | Version khởi tạo, tăng sau update và từ chối snapshot cũ | `@Version Long`, `OptimisticLockingFailureException` |
| Kiểu dữ liệu | Kiểu Java được chuyển thành property Neo4j phù hợp và đọc lại đúng | `LocalDate`, `ZonedDateTime`, enum, `BigDecimal` |
| Converter | Giá trị custom được mã hóa khi ghi và giải mã khi đọc | `Money` thành chuỗi hoặc kiểu native khác |

Nên tách test theo trách nhiệm. Unit test kiểm tra logic encode/decode thuần của converter; integration test kiểm tra converter được Spring đăng ký và thực sự được SDN dùng khi `save()`/đọc entity. Test optimistic locking phải tạo hai snapshot độc lập để kiểm tra xung đột version.

## 2. Chọn môi trường kiểm thử Neo4j

`@DataNeo4jTest` là test slice của Spring Boot. Nó tự cấu hình transaction manager, `Neo4jClient`, `Neo4jTemplate` và các repository được khai báo; đồng thời tích hợp JUnit Jupiter. Annotation này không tự khởi chạy database và cũng không tự cung cấp URI/credential. Test cần kết nối tới một Neo4j instance riêng.

Hai lựa chọn phổ biến:

| Môi trường | Phù hợp khi | Giới hạn cần nhớ |
|---|---|---|
| Neo4j Test Harness | Test mapping nhanh trong cùng JVM, procedure hoặc plugin | Thời gian và hiệu năng không đại diện đầy đủ cho server triển khai thật |
| Neo4j Testcontainers | Test repository, transaction và mapping trên Neo4j server trong container | Cần Docker và thời gian khởi động container |

Testcontainers thường phù hợp với integration test chạy trong CI vì dùng Neo4j server thực tế. Hãy pin image version tương thích với phiên bản Neo4j mà ứng dụng hỗ trợ; tránh dùng tag `latest` để kết quả test không thay đổi bất ngờ.

### Cấu hình Testcontainers với @DataNeo4jTest

Các dependency test cần có Spring Boot Starter Test và module Testcontainers Neo4j. Ví dụ Maven:

Ví dụ giả định version Testcontainers được quản lý bởi BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>${testcontainers.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-neo4j</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ lớp test kết nối tới Neo4j 5:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@DataNeo4jTest
@Testcontainers
class PersonRepositoryTest {

    private static final String PASSWORD = "test-password";

    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword(PASSWORD);

    @Autowired
    PersonRepository people;

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", () -> PASSWORD);
    }

    // Inject repository/client và đặt các test tại đây.
}
```

`@Container` static giữ một Neo4j container cho toàn bộ test class; `@DynamicPropertySource` đưa Bolt URL và thông tin xác thực vào Spring context trước khi tạo driver. Nếu project dùng Testcontainers BOM, để BOM quản lý version của các module thay vì khai báo version rời rạc.

`@DataNeo4jTest` mặc định có `@Transactional` cho test. Transaction test thường được rollback sau mỗi method, giúp cô lập dữ liệu. Tuy nhiên, đây là transaction imperative; khi kiểm thử reactive transaction, cần dùng `TransactionalOperator` hoặc service reactive phù hợp. Khi cần kiểm thử hai lần save ở hai transaction đã commit riêng, hãy tắt test-managed transaction cho method đó bằng `@Transactional(propagation = Propagation.NOT_SUPPORTED)` và để các repository operation chạy trong transaction riêng.

## 3. Kiểm thử ID được sinh tự động

Với generated ID, entity thường khai báo `@Id` cùng `@GeneratedValue`. Kiểu `Long` dùng Neo4j internal ID; kiểu `String` dùng `elementId` trong Neo4j 5. Có thể dùng `UUIDStringGenerator` nếu muốn ID surrogate do ứng dụng sinh.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Person() {
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {
}
```

Test kiểm tra ID sau save và khả năng tải lại entity:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

// Đặt trong PersonRepositoryTest ở phần cấu hình Testcontainers phía trên.
@Test
void generatedIdIsAssignedAndCanLoadEntity() {
    Person saved = people.save(new Person("An Nguyen"));

    assertThat(saved.getId()).isNotNull();

    Person loaded = people.findById(saved.getId()).orElseThrow();
    assertThat(loaded.getId()).isEqualTo(saved.getId());
    assertThat(loaded.getName()).isEqualTo("An Nguyen");
}
```

Không assert ID phải bằng một con số cụ thể. Internal ID được database cấp và phụ thuộc dữ liệu đã tạo/xóa trước đó. Hãy kiểm tra ID khác `null`, giữ ổn định khi đọc lại và trỏ đúng entity. Nếu ứng dụng cần định danh công khai bền vững, cân nhắc UUID hoặc business key thay vì đưa Neo4j internal ID ra API.

## 4. Kiểm thử business ID cùng @Version

Business ID đã có giá trị ngay khi tạo object. Vì vậy SDN không thể dựa vào `id == null` để phân biệt entity mới và entity đã lưu. Với entity dùng business ID, `@Version` là bắt buộc để SDN xác định trạng thái mới/đã tồn tại và thực hiện optimistic locking.

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    private String customerNumber;

    @Version
    private Long version;

    private String name;

    protected Customer() {
    }

    public Customer(String customerNumber, String name) {
        this.customerNumber = customerNumber;
        this.name = name;
    }

    public String getCustomerNumber() {
        return customerNumber;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        this.name = name;
    }
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {
}
```

Test xác minh version được quản lý bởi SDN:

```java
@Autowired
CustomerRepository customers;

@Test
void assignedIdUsesVersionToTrackNewAndUpdatedState() {
    Customer customer = new Customer("CUS-1001", "An Nguyen");
    assertThat(customer.getVersion()).isNull();

    Customer created = customers.save(customer);
    assertThat(created.getCustomerNumber()).isEqualTo("CUS-1001");
    assertThat(created.getVersion()).isZero();

    created.rename("An Tran");
    Customer updated = customers.save(created);

    assertThat(updated.getVersion()).isEqualTo(1L);
    assertThat(customers.findById("CUS-1001").orElseThrow().getName())
        .isEqualTo("An Tran");
}
```

Với entity mới, để version ở `null`; sau lần save đầu tiên SDN khởi tạo version ở `0`. Mỗi lần cập nhật thành công, version tăng tự động. Không tự gán `version = 0` trong constructor và không tự tăng version trong business code.

Nếu bỏ `@Version` khỏi entity dùng business ID, SDN luôn xem object là mới. Khi save object có business ID đã tồn tại, SDN có thể đi theo đường tạo mới thay vì cập nhật node hiện tại. Hãy kiểm thử cả số node theo business key và uniqueness constraint của database nếu domain yêu cầu khóa duy nhất.

## 5. Kiểm thử optimistic locking với hai snapshot

Optimistic locking ngăn một object cũ ghi đè thay đổi đã được lưu bởi transaction khác. Test cần tải cùng một entity hai lần để có hai snapshot mang cùng version ban đầu, lưu snapshot thứ nhất, sau đó thử lưu snapshot thứ hai.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void staleSnapshotCannotOverwriteNewerVersion() {
    Customer created = customers.save(
        new Customer("CUS-2001", "Original")
    );

    Customer firstSnapshot = customers.findById("CUS-2001").orElseThrow();
    Customer staleSnapshot = customers.findById("CUS-2001").orElseThrow();

    assertThat(firstSnapshot.getVersion()).isEqualTo(created.getVersion());
    assertThat(staleSnapshot.getVersion()).isEqualTo(created.getVersion());

    firstSnapshot.rename("Updated by first request");
    Customer saved = customers.save(firstSnapshot);
    assertThat(saved.getVersion()).isEqualTo(1L);

    staleSnapshot.rename("Updated by stale request");
    assertThatThrownBy(() -> customers.save(staleSnapshot))
        .isInstanceOf(OptimisticLockingFailureException.class);

    Customer current = customers.findById("CUS-2001").orElseThrow();
    assertThat(current.getName()).isEqualTo("Updated by first request");
    assertThat(current.getVersion()).isEqualTo(1L);
}
```

`Propagation.NOT_SUPPORTED` tắt transaction test-managed bao quanh toàn bộ method. Các thao tác repository có thể chạy trong transaction riêng, giúp lần save đầu commit trước khi snapshot cũ được lưu. Nếu để toàn bộ test trong một transaction, test vẫn hữu ích để kiểm tra điều kiện version trong cùng transaction, nhưng không mô phỏng đầy đủ hai request độc lập đã commit.

Khi nhận `OptimisticLockingFailureException`, ứng dụng nên tải entity mới, đánh giá lại thay đổi và chỉ retry nếu nghiệp vụ cho phép. Không retry mù quáng cùng object cũ vì version của object đó vẫn lỗi thời.

## 6. Kiểm thử kiểu dữ liệu native

SDN hỗ trợ nhiều kiểu Java và chuyển chúng thành kiểu property Neo4j. Một số kiểu ánh xạ trực tiếp sang native Cypher type; một số kiểu được lưu dưới dạng String. Test nên kiểm tra cả giá trị sau khi hydrate và kiểu biểu diễn lưu trữ nếu ứng dụng phụ thuộc vào kiểu đó trong Cypher.

| Kiểu Java | Kiểu Neo4j thường dùng | Lưu ý khi kiểm thử |
|---|---|---|
| `Boolean`, `Integer`, `Long`, `Double`, `String` | Boolean, Integer, Float, String | Ánh xạ trực tiếp |
| `LocalDate` | Date | Kiểm tra ngày sau khi đọc lại |
| `LocalTime`, `OffsetTime` | LocalTime, Time | Phân biệt local time và time có offset |
| `LocalDateTime` | LocalDateTime | Không chứa timezone |
| `ZonedDateTime`, `Instant` | DateTime | Kiểm tra instant và zone/offset theo yêu cầu domain |
| `Duration`, `Period` | Duration | Kiểm tra đơn vị và giá trị sau chuyển đổi |
| Enum | String | Giá trị lưu mặc định là `enum.name()` |
| `BigDecimal`, `BigInteger` | String | Không phải numeric property để dùng phép toán số học trực tiếp |
| `UUID`, `URI`, `URL` | String | Kiểm tra format chuỗi được lưu |
| `java.util.Date` | String ISO-8601 UTC | Múi giờ được chuẩn hóa UTC |
| `Point` | Point | Kiểm tra CRS và thứ tự tọa độ |

Ví dụ entity có nhiều kiểu dữ liệu:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZonedDateTime;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("TypeSample")
public class TypeSample {

    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private LocalDate issuedOn;
    private ZonedDateTime createdAt;
    private PaymentStatus status;
    private BigDecimal amount;

    protected TypeSample() {
    }

    public TypeSample(
        String code,
        LocalDate issuedOn,
        ZonedDateTime createdAt,
        PaymentStatus status,
        BigDecimal amount
    ) {
        this.code = code;
        this.issuedOn = issuedOn;
        this.createdAt = createdAt;
        this.status = status;
        this.amount = amount;
    }

    public Long getId() { return id; }
    public LocalDate getIssuedOn() { return issuedOn; }
    public ZonedDateTime getCreatedAt() { return createdAt; }
    public PaymentStatus getStatus() { return status; }
    public BigDecimal getAmount() { return amount; }
}
```

```java
public enum PaymentStatus {
    PENDING,
    PAID,
    REFUNDED
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface TypeSampleRepository
        extends Neo4jRepository<TypeSample, Long> {
}
```

Trong lớp test, inject repository và client:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;

@Autowired
TypeSampleRepository samples;

@Autowired
Neo4jClient neo4jClient;
```

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;

@Test
void nativeAndConvertedTypesRoundTrip() {
    LocalDate issuedOn = LocalDate.of(2026, 3, 15);
    ZonedDateTime createdAt = ZonedDateTime.parse(
        "2026-03-15T10:30:00+07:00[Asia/Ho_Chi_Minh]"
    );
    BigDecimal amount = new BigDecimal("1250.50");

    TypeSample saved = samples.save(new TypeSample(
        "TYPE-001", issuedOn, createdAt, PaymentStatus.PAID, amount
    ));

    TypeSample loaded = samples.findById(saved.getId()).orElseThrow();
    assertThat(loaded.getIssuedOn()).isEqualTo(issuedOn);
    assertThat(loaded.getCreatedAt()).isEqualTo(createdAt);
    assertThat(loaded.getStatus()).isEqualTo(PaymentStatus.PAID);
    assertThat(loaded.getAmount()).isEqualByComparingTo(amount);

    String storedStatus = neo4jClient.query("""
            MATCH (s:TypeSample {code: $code})
            RETURN s.status AS value
            """)
        .bind("TYPE-001").to("code")
        .fetchAs(String.class)
        .one()
        .orElseThrow();

    String storedAmount = neo4jClient.query("""
            MATCH (s:TypeSample {code: $code})
            RETURN s.amount AS value
            """)
        .bind("TYPE-001").to("code")
        .fetchAs(String.class)
        .one()
        .orElseThrow();

    assertThat(storedStatus).isEqualTo("PAID");
    assertThat(storedAmount).isEqualTo("1250.50");
}
```

Đoạn test giả định đã inject `TypeSampleRepository samples` và `Neo4jClient neo4jClient`. So sánh `BigDecimal` bằng `isEqualByComparingTo` khi kiểm tra giá trị số; nếu scale là một phần của hợp đồng domain, kiểm tra thêm `scale()` hoặc chuỗi lưu trữ như ví dụ.

### Những trường hợp cần chú ý

- Enum được lưu bằng tên constant. Đổi tên `PAID` thành `SETTLED` có thể làm dữ liệu cũ không deserialize được; xem đó là thay đổi schema dữ liệu và có migration phù hợp.
- `BigDecimal`/`BigInteger` được lưu thành String theo conversion mặc định. Nếu cần phép toán số học trong Cypher, hãy lưu thêm minor units dạng integer hoặc thiết kế property numeric rõ ràng.
- `java.util.Date` được chuẩn hóa về UTC khi lưu dạng ISO-8601 String. Nếu nghiệp vụ cần timezone gốc, dùng `ZonedDateTime` hoặc lưu zone riêng.
- Giá trị `null` trong Neo4j tương đương property không tồn tại; khi ghi `null`, property cũ có thể bị loại bỏ. Hãy test riêng trường hợp xóa property nếu logic phụ thuộc vào nó.
- Neo4j property không phải nơi lưu trực tiếp một POJO lồng nhau tùy ý. Dùng node/relationship, `@CompositeProperty` cho map phù hợp hoặc custom converter.

## 7. Kiểm thử custom converter hai chiều

Khi domain có value object riêng, ví dụ `Money`, SDN cần biết cách chuyển nó thành kiểu Neo4j Driver hỗ trợ và cách dựng lại object khi đọc. Với property entity, converter phải có cả hai chiều `Money -> Value` và `Value -> Money`. Nếu converter chỉ phục vụ tham số của custom query, chiều ghi sang `Value` có thể là đủ.

Ví dụ value object lưu tiền theo minor units để tránh lỗi số thực:

```java
public record Money(long minorUnits, String currency) {

    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("minorUnits must not be negative");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("currency must be an ISO code");
        }
    }
}
```

Converter mã hóa `Money` thành một String Neo4j Driver `Value` theo định dạng `CURRENCY:minorUnits`:

```java
import java.util.Set;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.core.convert.converter.GenericConverter;

public class MoneyConverter implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
            new ConvertiblePair(Money.class, Value.class),
            new ConvertiblePair(Value.class, Money.class)
        );
    }

    @Override
    public Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType
    ) {
        if (Money.class.isAssignableFrom(sourceType.getType())) {
            Money money = (Money) source;
            return Values.value(money.currency() + ":" + money.minorUnits());
        }

        if (Value.class.isAssignableFrom(sourceType.getType())) {
            String encoded = ((Value) source).asString();
            String[] parts = encoded.split(":", 2);
            if (parts.length != 2) {
                throw new IllegalArgumentException("Invalid Money value: " + encoded);
            }
            return new Money(Long.parseLong(parts[1]), parts[0]);
        }

        throw new IllegalArgumentException(
            "Unsupported conversion from " + sourceType.getType()
        );
    }
}
```

Đăng ký converter trong `Neo4jConversions`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration(proxyBeanMethods = false)
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions(List.of(new MoneyConverter()));
    }
}
```

SDN sử dụng bean `Neo4jConversions` này thay cho bộ converter mặc định nội bộ đơn thuần. Nếu ứng dụng có nhiều converter, đăng ký chúng trong cùng collection. Không mong đợi một class `Converter` tự được quét và đăng ký chỉ vì nó có `@Component`; custom conversion cần được đưa vào `Neo4jConversions`.

Entity và repository dùng value object:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Invoice")
public class Invoice {

    @Id
    @GeneratedValue
    private Long id;

    private String number;
    private Money total;

    protected Invoice() {
    }

    public Invoice(String number, Money total) {
        this.number = number;
        this.total = total;
    }

    public Long getId() { return id; }
    public Money getTotal() { return total; }
}
```

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface InvoiceRepository extends Neo4jRepository<Invoice, Long> {
}
```

Integration test phải import configuration chứa converter nếu nó không được component scan trong test context:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.neo4j.core.Neo4jClient;

@DataNeo4jTest
@Import(Neo4jConversionConfiguration.class)
class InvoiceConversionTest {

    @Autowired
    InvoiceRepository invoices;

    @Autowired
    Neo4jClient neo4jClient;

    @Test
    void customValueObjectIsWrittenAndReadBack() {
        Invoice saved = invoices.save(
            new Invoice("INV-1001", new Money(125000, "VND"))
        );

        Invoice loaded = invoices.findById(saved.getId()).orElseThrow();
        assertThat(loaded.getTotal()).isEqualTo(new Money(125000, "VND"));

        String rawValue = neo4jClient.query("""
                MATCH (i:Invoice {number: $number})
                RETURN i.total AS total
                """)
            .bind("INV-1001").to("number")
            .fetchAs(String.class)
            .one()
            .orElseThrow();

        assertThat(rawValue).isEqualTo("VND:125000");
    }
}
```

Test này xác minh ba điều độc lập: converter được Spring đăng ký, SDN dùng converter khi ghi entity và SDN dùng chiều ngược lại khi hydrate entity. Đọc raw property qua `Neo4jClient` giúp xác nhận hợp đồng lưu trữ, không chỉ xác nhận object sau khi converter đã chuyển ngược.

## 8. Converter toàn cục và converter theo thuộc tính

SDN có hai cách chính để áp dụng custom conversion:

| Cách | Phạm vi | Khi nào dùng |
|---|---|---|
| `Neo4jConversions` với `GenericConverter` | Mọi property/parameter có kiểu nguồn tương ứng | Một value object được dùng nhất quán ở nhiều entity |
| `@ConvertWith` | Một property cụ thể của node hoặc relationship properties | Cùng kiểu Java nhưng mỗi field có cách lưu khác nhau |

Với `@ConvertWith`, converter triển khai `Neo4jPersistentPropertyConverter` và được tham chiếu qua annotation hoặc Spring bean. Cách này hữu ích khi một kiểu Java cần nhiều representation tùy field. Hãy viết integration test cho từng field được annotate, đặc biệt nếu converter có logic phụ thuộc property hoặc metadata.

Nếu dùng converter cho query method nhưng không lưu entity property, kiểm thử riêng việc bind tham số của `@Query`. Một converter một chiều sang Neo4j `Value` có thể đủ cho trường hợp đó; đừng kết luận rằng mapping entity hai chiều đã hoạt động nếu chưa test đọc lại.

## 9. Kiểm thử property không hỗ trợ và dữ liệu null

Không phải mọi Java object đều có thể trở thành Neo4j property. Các property node/relationship phải là kiểu dữ liệu mà Neo4j hỗ trợ, chẳng hạn scalar, temporal, point hoặc list hợp lệ. Một POJO lồng nhau, map tùy ý hay cấu trúc object phức tạp cần được mô hình hóa rõ.

| Dữ liệu Java | Cách lưu phù hợp |
|---|---|
| Một domain object có identity và quan hệ riêng | Tách thành `@Node` và nối bằng `@Relationship` |
| Map cần trải phẳng thành nhiều property | Cân nhắc `@CompositeProperty` |
| Value object cần mã hóa thành một property | Dùng custom converter |
| Collection scalar hợp lệ | Lưu thành list property và kiểm tra kiểu phần tử |
| Giá trị `null` | Property không tồn tại trong graph |

Ví dụ test kiểm tra property null không được lưu:

```java
Boolean propertyIsAbsent = neo4jClient.query("""
        MATCH (i:Invoice {number: $number})
        RETURN i.optionalNote IS NULL AS absent
        """)
    .bind("INV-1001").to("number")
    .fetchAs(Boolean.class)
    .one()
    .orElseThrow();

assertThat(propertyIsAbsent).isTrue();
```

Trong Cypher, truy cập một property không tồn tại trả `null`; điều này cũng khiến `IS NULL` đúng. Nếu cần phân biệt property không tồn tại với một trạng thái nghiệp vụ riêng, hãy dùng một giá trị domain tường minh thay vì dựa vào null.

Không chỉ kiểm thử đường ghi thành công. Với converter, hãy thêm test cho dữ liệu malformed, currency không hợp lệ, chuỗi không parse được và giá trị ngoài miền hợp lệ. Lỗi nên xuất hiện rõ ràng trong quá trình conversion thay vì âm thầm tạo một object sai.

## 10. Kiểm thử độc lập converter và integration mapping

Unit test converter nhanh, không cần khởi động Neo4j:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.neo4j.driver.Value;
import org.springframework.core.convert.TypeDescriptor;

class MoneyConverterTest {

    private final MoneyConverter converter = new MoneyConverter();

    @Test
    void convertsMoneyToDriverValueAndBack() {
        Money original = new Money(125000, "VND");

        Value encoded = (Value) converter.convert(
            original,
            TypeDescriptor.valueOf(Money.class),
            TypeDescriptor.valueOf(Value.class)
        );

        Money decoded = (Money) converter.convert(
            encoded,
            TypeDescriptor.valueOf(Value.class),
            TypeDescriptor.valueOf(Money.class)
        );

        assertThat(encoded.asString()).isEqualTo("VND:125000");
        assertThat(decoded).isEqualTo(original);
    }
}
```

Unit test xác minh logic encode/decode, nhưng chưa chứng minh Spring đã đăng ký converter. Integration test với `@DataNeo4jTest` ở phần trước xác minh `Neo4jConversions`, entity converter và database cùng hoạt động.

## 11. Các lỗi thường gặp khi kiểm thử

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Generated ID vẫn `null` sau save | Entity không dùng `@GeneratedValue`, sai ID type/strategy hoặc test không đọc entity trả về | Kiểm tra annotation, dùng entity từ kết quả `save()` và xác minh repository mapping |
| ID thay đổi hoặc test phụ thuộc số cụ thể | Test giả định internal ID có giá trị cố định | Chỉ kiểm tra khác null, đọc lại được và giữ đúng entity |
| Business ID tạo thêm node thay vì update | Thiếu `@Version` | Thêm `@Version Long`, để null khi tạo object mới |
| Version không tăng | Code tự gán version, mapping sai hoặc test không đọc entity sau save | Để SDN quản lý version và kiểm tra kết quả save/readback |
| Stale save không ném exception trong test | Hai lần save vẫn nằm trong một snapshot/transaction không phù hợp hoặc không tạo hai object độc lập | Tải entity hai lần và dùng transaction boundary riêng khi kiểm thử concurrency |
| `@DataNeo4jTest` không kết nối được DB | Test slice không tự tạo database/URI | Dùng Testcontainers hoặc Test Harness và cấu hình `@DynamicPropertySource` |
| Converter không được gọi | Chưa đăng ký trong `Neo4jConversions` hoặc test context không import config | Đăng ký bean và `@Import` configuration trong test |
| Converter ghi được nhưng đọc lỗi | Chỉ cài chiều `CustomType -> Value` | Đăng ký cả `Value -> CustomType` cho entity property |
| Enum cũ không deserialize được | Enum constant bị đổi tên sau khi dữ liệu đã lưu | Giữ tên tương thích hoặc migration dữ liệu trước khi deploy |
| `BigDecimal` không dùng được trong phép toán Cypher | Mặc định được lưu thành String | Lưu minor units dạng integer hoặc converter sang numeric type phù hợp |
| Date lệch timezone | Dùng `java.util.Date` và kỳ vọng giữ timezone gốc | Dùng `ZonedDateTime` hoặc lưu zone riêng |
| Property null vẫn xuất hiện trong assertion | Nhầm null với một property có giá trị | Kiểm tra `IS NULL` hoặc `keys(node)` để xác minh property absence |
| Test pass nhưng production mapping khác | Test dùng Neo4j/Testcontainers version khác môi trường triển khai | Pin Neo4j image tương thích và chạy integration test trên phiên bản mục tiêu |

## 12. Checklist cho một test mapping đáng tin cậy

- [ ] Database test được tạo riêng, không kết nối nhầm database dùng chung.
- [ ] Phiên bản Neo4j container tương thích với môi trường triển khai.
- [ ] Generated ID được kiểm tra sau `save()` và sau `findById()`.
- [ ] Business ID được kiểm tra cùng `@Version Long`.
- [ ] Version khởi tạo ở `0`, tăng sau update và không bị code tự sửa.
- [ ] Hai snapshot độc lập được dùng để kiểm tra optimistic locking.
- [ ] Các kiểu temporal, enum, decimal và UUID được round-trip.
- [ ] Kiểu property lưu thực tế được kiểm tra khi có khác biệt với kiểu Java.
- [ ] Custom converter được unit test và integration test qua `Neo4jConversions`.
- [ ] Converter hai chiều được kiểm tra nếu dùng cho entity property.
- [ ] Trường hợp null, malformed input và unsupported type được kiểm tra.
- [ ] Test transaction/cleanup không để dữ liệu rò rỉ giữa các test.

## 13. Tự kiểm tra

1. Vì sao test ID generated chỉ nên kiểm tra ID khác null và tải lại được, thay vì assert một con số cụ thể?
2. Khi dùng business ID, vì sao `@Version` cần thiết để SDN phân biệt entity mới và entity đã tồn tại?
3. Kiểu dữ liệu Java nào được SDN dùng làm version và ai chịu trách nhiệm tăng version?
4. Làm thế nào để tạo hai snapshot có cùng version và chứng minh snapshot cũ bị từ chối?
5. Vì sao `@DataNeo4jTest` cần Testcontainers hoặc Test Harness để có database thật?
6. `@DataNeo4jTest` có transaction mặc định nào và điều đó ảnh hưởng ra sao đến test optimistic locking?
7. Enum và `BigDecimal` được lưu dưới dạng gì theo conversion mặc định?
8. Vì sao `BigDecimal` lưu dưới dạng String có thể không phù hợp cho phép toán số học Cypher?
9. Khi nào custom converter phải hỗ trợ cả `Money -> Value` và `Value -> Money`?
10. `Neo4jConversions` và `@ConvertWith` khác nhau về phạm vi áp dụng như thế nào?
11. Vì sao unit test converter không đủ để chứng minh converter đã được Spring Data Neo4j đăng ký?
12. Neo4j biểu diễn property null như thế nào và test cần kiểm tra ra sao?

Một bộ test mapping tốt xác minh hợp đồng hai chiều giữa entity Java và graph. Hãy kiểm tra generated ID và business ID riêng, dùng `@Version Long` để kiểm tra cập nhật và stale snapshot, kiểm tra cả kiểu Java lẫn property Neo4j được lưu, rồi test custom converter ở cả mức unit và integration. `@DataNeo4jTest` kết hợp Neo4j Testcontainers cung cấp nền tảng thực tế để xác nhận repository, mapping context, conversion service và transaction infrastructure hoạt động cùng nhau.

## Tài liệu tham khảo

- [Spring Data Neo4j — Testing with Spring Boot and `@DataNeo4jTest`](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Neo4j — Conversions and supported Java types](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Spring Data Neo4j — Metadata-based mapping, IDs and optimistic locking](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j — `Neo4jConversions` API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/Neo4jConversions.html)
- [Neo4j Java Driver Manual — Type mapping](https://neo4j.com/docs/java-manual/current/data-types/)
- [Testcontainers — Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
