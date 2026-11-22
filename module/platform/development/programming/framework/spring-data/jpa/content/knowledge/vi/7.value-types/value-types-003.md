# Ghi đè ánh xạ bằng @AttributeOverride và @AssociationOverride

## Mục tiêu

`@Embeddable` cho phép tái sử dụng một nhóm thuộc tính trong nhiều entity; `@MappedSuperclass` cho phép nhiều entity kế thừa chung các mapping. Tuy nhiên, cùng một lớp có thể cần tên cột hoặc cách nối quan hệ khác nhau tùy nơi sử dụng. JPA cung cấp hai annotation để tùy chỉnh mapping tại nơi kế thừa hoặc nhúng:

- `@AttributeOverride` thay đổi mapping cột của một thuộc tính cơ bản (basic attribute), chẳng hạn `String`, `BigDecimal`, `LocalDate` hoặc một thuộc tính trong embeddable.
- `@AssociationOverride` thay đổi mapping của một quan hệ tới entity, chẳng hạn join column hoặc join table của `@ManyToOne`, `@OneToOne`, `@OneToMany` hay `@ManyToMany`.

Điểm quan trọng là override thay đổi cách JPA ánh xạ thuộc tính trong một ngữ cảnh cụ thể. Nó không đổi tên field Java, không thay đổi cấu trúc lớp dùng chung và cũng không tự migration schema production.

## 1. Vì sao cần override mapping?

Giả sử ứng dụng có embeddable địa chỉ:

```java
@Embeddable
public class Address {
    private String street;
    private String city;
    private String postalCode;
}
```

Một entity cần địa chỉ thanh toán, entity khác cần địa chỉ giao hàng. Nếu dùng cùng embeddable hai lần trong một bảng, mapping mặc định có thể tạo tên cột trùng nhau. Ứng dụng cần đặt tên riêng như `billing_street` và `shipping_street`.

Tương tự, một embeddable có quan hệ tới `Agent` có thể được nhúng vào nhiều entity. Mỗi entity có thể cần tên khóa ngoại khác nhau, chẳng hạn `assigned_agent_id` hoặc `reviewer_id`.

Override cho phép giữ một lớp reusable có ý nghĩa thống nhất, đồng thời định nghĩa tên cột và join phù hợp tại từng entity.

## 2. @AttributeOverride: ghi đè mapping của cột

`@AttributeOverride` có hai phần:

- `name`: tên thuộc tính Java cần ghi đè.
- `column`: annotation `@Column` mô tả mapping cột mới.

Ví dụ:

```java
@Embedded
@AttributeOverride(
    name = "street",
    column = @Column(name = "billing_street", nullable = false, length = 150)
)
private Address billingAddress;
```

Ở đây `name = "street"` tham chiếu tới thuộc tính `street` trong `Address`, không phải tên cột SQL. `column` chỉ định cột database mà thuộc tính đó sử dụng trong entity đang nhúng `Address`.

### Ghi đè nhiều thuộc tính

Khi cần thay đổi nhiều cột, dùng `@AttributeOverrides`:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street", nullable = false, length = 150)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city", nullable = false, length = 80)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "billing_postal_code", length = 16)
    )
})
private Address billingAddress;
```

Với một instance `Address` khác, khai báo một bộ override riêng:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(name = "street",
        column = @Column(name = "shipping_street", nullable = false, length = 150)),
    @AttributeOverride(name = "city",
        column = @Column(name = "shipping_city", nullable = false, length = 80)),
    @AttributeOverride(name = "postalCode",
        column = @Column(name = "shipping_postal_code", length = 16))
})
private Address shippingAddress;
```

Nhờ vậy, cả hai field đều dùng kiểu Java `Address`, nhưng lưu vào các cột khác nhau trong cùng bảng.

### Những thuộc tính @Column có thể ghi đè

Bạn có thể tùy chỉnh các thông tin thuộc mapping cột như:

- `name`: tên cột.
- `nullable`: cột có cho phép `NULL` hay không.
- `length`: độ dài cột kiểu chuỗi.
- `precision` và `scale`: độ chính xác và số chữ số thập phân cho kiểu số phù hợp.
- `unique`: khai báo unique trong schema do provider sinh.
- `columnDefinition`: định nghĩa kiểu cột cụ thể theo database, nếu thực sự cần phụ thuộc dialect.

Chỉ khai báo tên cột có thể khiến các thuộc tính khác quay về giá trị mặc định của annotation `@Column`. Nếu yêu cầu schema cần `nullable=false`, độ dài hoặc precision cụ thể, hãy ghi chúng tường minh trong override và xác minh migration/schema thực tế.

## 3. Override thuộc tính lồng nhau

Embeddable có thể chứa một embeddable khác. Khi override một thuộc tính nằm sâu bên trong, dùng đường dẫn thuộc tính phân cách bằng dấu chấm.

Ví dụ:

```java
@Embeddable
public class Coordinates {
    private Double latitude;
    private Double longitude;
}

@Embeddable
public class Address {
    private String street;

    @Embedded
    private Coordinates coordinates;
}
```

Khi nhúng `Address`, có thể ghi đè `latitude` và `longitude` như sau:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "coordinates.latitude",
        column = @Column(name = "delivery_latitude", precision = 10, scale = 7)
    ),
    @AttributeOverride(
        name = "coordinates.longitude",
        column = @Column(name = "delivery_longitude", precision = 10, scale = 7)
    )
})
private Address deliveryAddress;
```

Đường dẫn phải dùng tên thuộc tính Java theo đúng cấu trúc embeddable. Không dùng tên cột SQL ở phần `name`.

## 4. Override mapping kế thừa từ @MappedSuperclass

`@AttributeOverride` cũng dùng để thay đổi mapping của thuộc tính basic kế thừa từ `@MappedSuperclass`.

```java
@MappedSuperclass
public abstract class AuditedRecord {
    @Column(name = "created_at", nullable = false)
    protected Instant createdAt;
}

@Entity
@Table(name = "support_cases")
@AttributeOverride(
    name = "createdAt",
    column = @Column(name = "case_created_at", nullable = false)
)
public class SupportCase extends AuditedRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

`AuditedRecord` vẫn định nghĩa một thuộc tính `createdAt` dùng chung. Entity `SupportCase` lưu thuộc tính đó trong cột `case_created_at`. Một entity khác có thể giữ `created_at` hoặc khai báo override riêng.

Nếu cần override nhiều thuộc tính kế thừa, dùng `@AttributeOverrides` ở cấp entity. Đây là mapping của thuộc tính được kế thừa; không tạo một bảng riêng cho `@MappedSuperclass`.

## 5. @AssociationOverride: ghi đè mapping của quan hệ

`@AssociationOverride` dùng cho thuộc tính quan hệ tới entity được khai báo trong embeddable hoặc mapped superclass. Annotation này không thay thế `@AttributeOverride`: một annotation điều chỉnh association, annotation còn lại điều chỉnh basic attribute.

Các thuộc tính quan trọng:

- `name`: tên thuộc tính quan hệ cần ghi đè.
- `joinColumns`: một hoặc nhiều khóa ngoại đặt trong bảng của entity sở hữu quan hệ.
- `joinTable`: mapping của bảng nối, gồm join columns trỏ về entity sở hữu và inverse join columns trỏ về entity đích.

### Override join column của @ManyToOne

Embeddable có quan hệ tới `Agent`:

```java
@Embeddable
public class Assignment {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "agent_id")
    private Agent agent;

    private String note;
}
```

Khi `Assignment` được nhúng trong entity, đổi tên foreign key:

```java
@Embedded
@AssociationOverride(
    name = "agent",
    joinColumns = @JoinColumn(name = "assigned_agent_id")
)
private Assignment assignment;
```

`name = "agent"` là thuộc tính quan hệ trong `Assignment`. `joinColumns` đặt cột khóa ngoại `assigned_agent_id` trong bảng entity đang nhúng `Assignment`.

Nếu embeddable được nhúng vào một entity khác, entity đó có thể override cùng quan hệ thành `reviewer_id`. Mapping mặc định trong `Assignment` vẫn hữu ích khi không có override.

### Override join table

Với quan hệ dùng join table, khai báo `joinTable` thay cho `joinColumns`. Ví dụ embeddable khai báo tập reviewer:

```java
@Embeddable
public class ReviewGroup {
    @ManyToMany
    private Set<Agent> reviewers = new HashSet<>();
}
```

Entity nhúng có thể định nghĩa bảng nối riêng:

```java
@Embedded
@AssociationOverride(
    name = "reviewers",
    joinTable = @JoinTable(
        name = "case_reviewers",
        joinColumns = @JoinColumn(name = "case_id"),
        inverseJoinColumns = @JoinColumn(name = "reviewer_id")
    )
)
private ReviewGroup reviewGroup;
```

`joinColumns` trong `@JoinTable` là khóa ngoại trỏ về entity sở hữu; `inverseJoinColumns` trỏ về entity ở phía còn lại của quan hệ. `joinTable` và `joinColumns` ở cấp `@AssociationOverride` là hai cách mô tả mapping khác nhau; chọn theo loại association và cấu trúc schema mong muốn.

### Chọn joinColumns hay joinTable?

| Mapping quan hệ | Cấu trúc thường dùng | Override thường chọn |
| --- | --- | --- |
| `@ManyToOne` owning side | Foreign key trong bảng entity sở hữu | `joinColumns` |
| `@OneToOne` owning side | Foreign key trong bảng entity sở hữu hoặc join table theo mapping | `joinColumns` hoặc `joinTable` |
| `@ManyToMany` | Join table | `joinTable` |
| Unidirectional `@OneToMany` | Thường dùng join table; cũng có thể thiết kế bằng foreign key theo mapping phù hợp | `joinTable` hoặc cấu hình association tương ứng |

Quan hệ inverse side dùng `mappedBy` không sở hữu cột nối. Hãy đặt override tại nơi mapping được phép điều khiển association và kiểm tra phía owning side; không thể dùng override để biến một association inverse thành owning side theo ý muốn.

## 6. Override association kế thừa từ @MappedSuperclass

`@AssociationOverride` cũng có thể thay đổi mapping quan hệ được khai báo trong mapped superclass.

```java
@MappedSuperclass
public abstract class OwnedRecord {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id")
    protected Agent owner;
}

@Entity
@AssociationOverride(
    name = "owner",
    joinColumns = @JoinColumn(name = "reviewer_id")
)
public class Review extends OwnedRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

Entity `Review` kế thừa quan hệ `owner` nhưng lưu foreign key ở cột `reviewer_id`. Có thể dùng `@AssociationOverrides` nếu cần thay đổi nhiều quan hệ kế thừa.

## 7. Kết hợp AttributeOverride và AssociationOverride

Một embeddable có thể chứa cả basic attributes và associations. Khi nhúng, entity có thể cần đổi cả cột dữ liệu và join column. Hai loại override có thể đặt cùng vị trí trên field hoặc property được nhúng.

```java
@Entity
@Table(name = "support_cases")
public class SupportCase {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverride(
        name = "note",
        column = @Column(name = "assignment_note", length = 200)
    )
    @AssociationOverride(
        name = "agent",
        joinColumns = @JoinColumn(name = "assigned_agent_id")
    )
    private Assignment assignment;
}
```

Trong ví dụ này:

- `note` là basic attribute nên được điều chỉnh bằng `@AttributeOverride`.
- `agent` là quan hệ `@ManyToOne` nên được điều chỉnh bằng `@AssociationOverride`.
- `assignment` vẫn là một thuộc tính Java kiểu `Assignment`; chỉ mapping ở entity `SupportCase` được thay đổi.

Đây là cách giữ embeddable có thể tái sử dụng mà không phải tạo nhiều lớp gần giống nhau chỉ vì tên cột khác nhau.

## 8. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo một `SupportCase` có địa chỉ thanh toán, địa chỉ giao hàng và người phụ trách. Hai địa chỉ dùng cùng embeddable `Address` nhưng có các tên cột riêng. `Assignment` chứa quan hệ `ManyToOne` tới `Agent`; entity `SupportCase` override tên foreign key và tên cột ghi chú.

### Cấu trúc thư mục

```text
mapping-overrides/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/mappingoverrides/
        │   ├── MappingOverridesApplication.java
        │   ├── Address.java
        │   ├── Assignment.java
        │   ├── Agent.java
        │   ├── SupportCase.java
        │   ├── AgentRepository.java
        │   ├── SupportCaseRepository.java
        │   └── SupportCaseService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mapping-overrides</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:overrides;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`create-drop` chỉ dành cho database thử nghiệm trong bộ nhớ. Production nên quản lý schema bằng Flyway hoặc Liquibase.

### `Address.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(length = 150)
    private String street;

    @Column(length = 80)
    private String city;

    @Column(length = 16)
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
```

### `Agent.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "agents")
public class Agent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Agent() {
    }

    public Agent(String name) {
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

### `Assignment.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Embeddable
public class Assignment {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "agent_id")
    private Agent agent;

    @Column(length = 200)
    private String note;

    protected Assignment() {
    }

    public Assignment(Agent agent, String note) {
        this.agent = agent;
        this.note = note;
    }

    public Agent getAgent() {
        return agent;
    }

    public String getNote() {
        return note;
    }
}
```

### `SupportCase.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.AssociationOverride;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "support_cases")
public class SupportCase {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "street",
            column = @Column(name = "billing_street", nullable = false, length = 150)),
        @AttributeOverride(name = "city",
            column = @Column(name = "billing_city", nullable = false, length = 80)),
        @AttributeOverride(name = "postalCode",
            column = @Column(name = "billing_postal_code", length = 16))
    })
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "street",
            column = @Column(name = "shipping_street", nullable = false, length = 150)),
        @AttributeOverride(name = "city",
            column = @Column(name = "shipping_city", nullable = false, length = 80)),
        @AttributeOverride(name = "postalCode",
            column = @Column(name = "shipping_postal_code", length = 16))
    })
    private Address shippingAddress;

    @Embedded
    @AttributeOverride(name = "note",
        column = @Column(name = "assignment_note", length = 200))
    @AssociationOverride(name = "agent",
        joinColumns = @JoinColumn(name = "assigned_agent_id"))
    private Assignment assignment;

    protected SupportCase() {
    }

    public SupportCase(Address billingAddress, Address shippingAddress,
                       Assignment assignment) {
        this.billingAddress = billingAddress;
        this.shippingAddress = shippingAddress;
        this.assignment = assignment;
    }

    public Long getId() {
        return id;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public Assignment getAssignment() {
        return assignment;
    }
}
```

### `AgentRepository.java`

```java
package com.example.mappingoverrides;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AgentRepository extends JpaRepository<Agent, Long> {
}
```

### `SupportCaseRepository.java`

```java
package com.example.mappingoverrides;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SupportCaseRepository extends JpaRepository<SupportCase, Long> {
}
```

### `SupportCaseService.java`

```java
package com.example.mappingoverrides;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SupportCaseService {
    private final AgentRepository agentRepository;
    private final SupportCaseRepository caseRepository;

    public SupportCaseService(AgentRepository agentRepository,
                              SupportCaseRepository caseRepository) {
        this.agentRepository = agentRepository;
        this.caseRepository = caseRepository;
    }

    @Transactional
    public String createAndRead() {
        Agent agent = agentRepository.save(new Agent("Linh"));

        SupportCase supportCase = new SupportCase(
                new Address("12 Le Loi", "Ha Noi", "100000"),
                new Address("8 Tran Phu", "Da Nang", "550000"),
                new Assignment(agent, "Handle customer request"));

        SupportCase saved = caseRepository.save(supportCase);
        SupportCase loaded = caseRepository.findById(saved.getId()).orElseThrow();

        return "Billing city: " + loaded.getBillingAddress().getCity()
                + "\nShipping city: " + loaded.getShippingAddress().getCity()
                + "\nAssigned agent: " + loaded.getAssignment().getAgent().getName()
                + "\nAssignment note: " + loaded.getAssignment().getNote();
    }
}
```

### `MappingOverridesApplication.java`

```java
package com.example.mappingoverrides;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MappingOverridesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingOverridesApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(SupportCaseService service) {
        return args -> System.out.println(service.createAndRead());
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Billing city: Ha Noi
Shipping city: Da Nang
Assigned agent: Linh
Assignment note: Handle customer request
```

Trong bảng `support_cases`, các cột được ánh xạ theo tên đã override: `billing_street`, `billing_city`, `billing_postal_code`, `shipping_street`, `shipping_city`, `shipping_postal_code`, `assignment_note` và `assigned_agent_id`. Bảng `agents` chứa entity `Agent`; `assigned_agent_id` là khóa ngoại trỏ tới `agents.id`.

Ví dụ dùng `save()` và `findById()` trong cùng transaction để tập trung vào mapping. Hibernate có thể trả lại managed instance đã có trong persistence context; nếu muốn quan sát một lần đọc database mới, có thể flush rồi clear EntityManager trước khi tìm lại trong integration test.

## 9. Quy tắc đặt tên và giới hạn

- `name` trong override là tên thuộc tính Java, phân biệt chữ hoa/chữ thường; không phải tên cột database.
- Với thuộc tính lồng nhau, dùng đường dẫn phân tách bằng dấu chấm, ví dụ `location.coordinates.latitude`.
- Khi nhúng cùng một embeddable nhiều lần trong cùng entity, cần override các cột trùng để mapping không xung đột.
- `@AttributeOverride` chỉ dành cho basic attribute; không dùng nó để đổi join column của quan hệ.
- `@AssociationOverride` dành cho association; không dùng nó để đổi tên cột của một `String` hoặc `BigDecimal` thông thường.
- `@AssociationOverride` phải áp dụng vào association được khai báo trong embeddable hoặc mapped superclass; nó không phải công cụ đổi tùy ý quan hệ ở bất kỳ vị trí nào.
- Với association, phân biệt owning side và inverse side. Cột nối được quản lý bởi owning side.
- Nếu override một phần mapping, khai báo đầy đủ các thuộc tính cần có trong schema như nullability, length và constraint.

## 10. Thay đổi override và migration database

Annotation mapping là mô tả cho JPA provider. Thay đổi `@AttributeOverride` từ `billing_city` sang `invoice_city` không tự bảo đảm cột production được đổi tên hoặc dữ liệu được di chuyển an toàn. Tương tự, thay `assigned_agent_id` có thể cần đổi tên cột khóa ngoại và constraint.

Với database đang có dữ liệu:

1. Xác định schema hiện tại, khóa ngoại, index, constraint, dữ liệu và các ứng dụng đang dùng cột.
2. Viết migration có version để thêm cột mới hoặc đổi tên cột theo khả năng database.
3. Nếu cần rollout nhiều phiên bản, dùng giai đoạn tương thích: phiên bản cũ và mới phải có cách đọc/ghi không làm mất dữ liệu.
4. Backfill dữ liệu sang cột mới và kiểm tra số hàng, giá trị null, orphan foreign key và tính toàn vẹn.
5. Triển khai mapping mới sau khi schema tương thích đã sẵn sàng.
6. Chỉ loại bỏ cột cũ sau khi mọi phiên bản ứng dụng không còn đọc hoặc ghi nó.

Không dựa vào `spring.jpa.hibernate.ddl-auto=update` như một cơ chế migration production. Dùng Flyway, Liquibase hoặc quy trình migration có kiểm soát để version hóa thay đổi schema.

## 11. Lỗi thường gặp

1. **Dùng sai tên trong `name`:** viết tên cột SQL thay vì tên field/property Java. Kiểm tra tên thuộc tính trong embeddable hoặc mapped superclass.
2. **Hai embedded object sinh cột trùng nhau:** khai báo `@AttributeOverrides` riêng cho từng field nhúng.
3. **Dùng `@AttributeOverride` cho `@ManyToOne`:** chuyển sang `@AssociationOverride` với `joinColumns` hoặc `joinTable` phù hợp.
4. **Dùng `joinColumns` khi mapping cần join table:** xác định association owner và kiểu liên kết trước khi chọn thuộc tính override.
5. **Override sai đường dẫn nested:** kiểm tra từng tên property trong chuỗi, dùng dấu chấm cho embeddable lồng nhau.
6. **Kỳ vọng annotation tự sửa schema production:** tạo migration và kiểm tra schema sau triển khai.
7. **Quên override nullability hoặc length:** kiểm tra `@Column` trong override có giữ đúng các ràng buộc mong muốn không.
8. **Nhầm association inverse với owning side:** kiểm tra `mappedBy`; override phải điều khiển mapping ở phía sở hữu quan hệ.

## 12. Cách kiểm thử mapping

Kiểm thử mapping nên xác nhận cả schema lẫn hành vi đọc/ghi:

- Khởi tạo context JPA với database thử nghiệm và để Hibernate kiểm tra mapping.
- Lưu entity có hai embeddable cùng kiểu, sau đó truy vấn trực tiếp bảng để xác nhận mỗi field ghi vào đúng cột.
- Lưu entity có association được override, xác nhận foreign key nằm trong đúng cột và trỏ tới đúng hàng.
- Đọc lại entity trong persistence context mới để kiểm tra mapping hai chiều.
- Với nested path hoặc mapped superclass, kiểm tra từng thuộc tính đã override.
- Chạy migration trên bản sao dữ liệu có cấu trúc tương đương production trước khi phát hành.

Ví dụ integration test nên chạy qua transaction riêng hoặc clear persistence context trước khi đọc lại; nếu chỉ đọc cùng managed instance, test có thể không phát hiện sai mapping trong database.

## 13. Tóm tắt lựa chọn

| Nhu cầu | Annotation |
| --- | --- |
| Đổi tên hoặc thuộc tính cột của basic field trong embeddable | `@AttributeOverride` |
| Đổi nhiều cột basic cùng lúc | `@AttributeOverrides` |
| Đổi cột basic kế thừa từ mapped superclass | `@AttributeOverride` hoặc `@AttributeOverrides` trên entity con |
| Đổi foreign key của association trong embeddable | `@AssociationOverride(joinColumns = ...)` |
| Đổi bảng nối của association | `@AssociationOverride(joinTable = ...)` |
| Đổi nhiều association cùng lúc | `@AssociationOverrides` |
| Giữ cùng một embeddable nhưng tên cột khác nhau ở từng entity | Override tại từng nơi `@Embedded` |

Nguyên tắc cần nhớ: **AttributeOverride điều chỉnh cột của thuộc tính dữ liệu; AssociationOverride điều chỉnh cách nối quan hệ. `name` luôn tham chiếu thuộc tính Java trong mapping được nhúng hoặc kế thừa. Mọi thay đổi có ảnh hưởng schema production đều cần migration và kiểm thử dữ liệu.**