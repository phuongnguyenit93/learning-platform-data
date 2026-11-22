# Default method và wrapper cho thuộc tính có thể null

## Mục tiêu

Spring Data JPA hỗ trợ interface projection để trả về một góc nhìn nhỏ của entity thay vì luôn tải toàn bộ entity. Projection có thể khai báo **default method** để tính thuộc tính hiển thị từ các getter khác, và có thể dùng **nullable wrapper** như `Optional<T>` cho thuộc tính có khả năng null.

Hai khả năng này giải quyết hai nhu cầu khác nhau:

- Default method tạo giá trị dẫn xuất trong Java, dựa trên những thuộc tính projection đã khai báo.
- Nullable wrapper biểu diễn an toàn trường hợp một thuộc tính nguồn không có giá trị.

Ví dụ projection `PersonSummary` có `getFirstName()`, `getLastName()` và `getNickname()`. Default method `getFullName()` ghép họ tên; getter `Optional<String> getNickname()` biểu diễn biệt danh có thể null; `getDisplayName()` chọn biệt danh nếu có, nếu không dùng họ tên.

## 1. Interface projection hoạt động thế nào?

Projection là kiểu trả về mô tả những thuộc tính mà caller cần đọc. Với interface projection, Spring Data tạo một proxy triển khai interface và lấy dữ liệu từ entity/query result.

Entity có thể chứa nhiều thuộc tính:

```java
@Entity
public class Person {
    @Id
    private Long id;
    private String firstName;
    private String lastName;
    private String nickname;
    private String email;
    private String address;
}
```

Nhưng một màn hình danh sách chỉ cần họ tên và biệt danh. Có thể định nghĩa projection:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();
    Optional<String> getNickname();
}
```

Spring Data có thể tạo projection từ query method:

```java
List<PersonSummary> findByLastName(String lastName);
```

Caller nhận `PersonSummary`, không cần phụ thuộc vào toàn bộ entity `Person`. Projection phù hợp khi tầng đọc chỉ cần một tập thuộc tính cụ thể, chẳng hạn danh sách, bảng tìm kiếm hoặc response view.

### Closed projection

Projection được xem là closed khi các accessor tương ứng với thuộc tính của target entity. Spring Data biết những property cần thiết và có thể tối ưu query để chỉ lấy phần dữ liệu cần dùng.

Trong ví dụ, `firstName`, `lastName` và `nickname` là các property của `Person`. Default method được giới thiệu ở phần tiếp theo chỉ gọi các accessor này, nên vẫn giữ được cách thiết kế projection đóng.

Projection không phải lúc nào cũng đồng nghĩa với một câu SQL chỉ chọn đúng ba cột trong mọi tình huống. Query tùy chỉnh, nested projection, provider và mapping có thể ảnh hưởng SQL cuối cùng. Bật SQL logging để xác nhận khi tối ưu hiệu năng.

## 2. Default method trong projection

Java interface cho phép khai báo method có phần thân bằng từ khóa `default`. Spring Data projection có thể dùng các method này để tính giá trị từ những accessor khác trong cùng interface.

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
```

`getFullName()` không cần một cột `fullName` trong database. Khi caller gọi method này, phần thân default method chạy trong Java và lấy dữ liệu qua `getFirstName()` cùng `getLastName()`.

### Quy tắc thiết kế default method

- Chỉ gọi các accessor đã khai báo trong projection để lấy dữ liệu cần tính.
- Giữ logic ngắn, xác định và dễ kiểm thử, ví dụ ghép tên, định dạng nhãn hoặc chọn giá trị thay thế.
- Không giả định projection proxy có thể truy cập trực tiếp field private của entity.
- Không đặt truy vấn database, thao tác ghi dữ liệu hoặc logic phụ thuộc hạ tầng trong default method.
- Nếu công thức quá phức tạp hoặc cần dịch vụ bên ngoài, chuyển logic sang service/mapper hoặc dùng DTO phù hợp.

Trong default method, `this` là projection proxy. Khi gọi `getFirstName()`, lời gọi được proxy xử lý và trả về giá trị thuộc tính đã lấy từ query.

### Default method không tạo cột hay biểu thức SQL

`getFullName()` được tính trong Java sau khi projection có dữ liệu. Nó không tự tạo cột `full_name` và cũng không tương đương một JPQL `concat(...)` chạy trong database.

Nếu cần sắp xếp hoặc lọc theo biểu thức tính toán ở database, hãy viết JPQL/SQL projection phù hợp, dùng query expression hoặc lưu một thuộc tính dẫn xuất theo thiết kế dữ liệu. Không thể dùng tên default method như thể nó là persistent property của entity trong derived query.

## 3. Kết hợp default method với Optional

Giả sử `nickname` có thể null. Projection có thể khai báo getter trả về `Optional<String>`:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();
    Optional<String> getNickname();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }

    default String getDisplayName() {
        return getNickname()
                .filter(value -> !value.isBlank())
                .orElseGet(this::getFullName);
    }
}
```

Khi property nguồn `nickname` là null, Spring Data trả `Optional.empty()`. Khi property có giá trị, getter trả Optional chứa giá trị đó. Default method `getDisplayName()` có thể xử lý cả hai trường hợp mà không cần kiểm tra null trực tiếp.

Ví dụ:

| firstName | lastName | nickname trong database | getNickname() | getDisplayName() |
| --- | --- | --- | --- | --- |
| An | Nguyen | An | `Optional[An]` | An |
| Binh | Nguyen | `NULL` | `Optional.empty()` | Binh Nguyen |
| Cuong | Nguyen | Cún | `Optional[Cún]` | Cún |

Trong ví dụ, biệt danh rỗng hoặc chỉ chứa khoảng trắng cũng được xem như không có biệt danh nhờ `filter`. Nếu nghiệp vụ coi chuỗi rỗng là dữ liệu có ý nghĩa, bỏ điều kiện filter.

### Các cách xử lý Optional

```java
String nickname = summary.getNickname().orElse("Chưa đặt biệt danh");

String displayName = summary.getNickname()
        .filter(value -> !value.isBlank())
        .orElseGet(summary::getFullName);

summary.getNickname().ifPresent(value -> log.info("Nickname: {}", value));
```

- `orElse(value)` trả giá trị mặc định khi Optional rỗng; biểu thức đối số được tính trước khi gọi.
- `orElseGet(supplier)` chỉ gọi supplier khi Optional rỗng.
- `map(function)` biến đổi giá trị nếu có.
- `ifPresent(action)` chạy hành động khi có giá trị.
- `orElseThrow()` hoặc `orElseThrow(supplier)` dùng khi thiếu giá trị là lỗi.

Không gọi `.get()` tùy tiện. Nếu giá trị có thể vắng mặt, hãy xử lý bằng `orElse`, `orElseGet`, `map`, `ifPresent` hoặc `orElseThrow` theo hợp đồng nghiệp vụ.

## 4. Những nullable wrapper được hỗ trợ

Spring Data Commons hỗ trợ một số wrapper cho getter trong projection. Nếu property nền null, getter trả wrapper rỗng; nếu property có giá trị, getter trả wrapper chứa giá trị.

| Wrapper | Kiểu getter |
| --- | --- |
| Java 8+ | `java.util.Optional<T>` |
| Guava | `com.google.common.base.Optional<T>` |
| Scala | `scala.Option<T>` |
| Vavr | `io.vavr.control.Option<T>` |

Java `Optional` thường là lựa chọn đơn giản nhất vì có sẵn trong JDK. Các wrapper còn lại cần thư viện tương ứng trên classpath và phiên bản Spring Data hỗ trợ.

### Dùng wrapper cho kiểu dữ liệu khác

Nếu thuộc tính số có thể null, có thể khai báo getter projection bằng kiểu boxed trong Optional:

```java
Optional<Integer> getAge();
Optional<BigDecimal> getCreditLimit();
```

Không dùng primitive như `int` để biểu diễn một giá trị có thể vắng mặt: primitive không có trạng thái null. `OptionalInt`, `OptionalLong` và `OptionalDouble` không nằm trong danh sách wrapper projection được hỗ trợ nêu trên; dùng `Optional<Integer>`, `Optional<Long>` hoặc `Optional<Double>` khi cần wrapper nullable.

### Wrapper chỉ nằm ở projection accessor

Entity vẫn có thể giữ thuộc tính persistent bình thường:

```java
@Column
private String nickname;
```

Projection mới khai báo:

```java
Optional<String> getNickname();
```

Không cần đổi field entity thành `Optional<String>`. Wrapper ở đây là hợp đồng đọc của projection; thuộc tính entity vẫn được JPA ánh xạ theo kiểu dữ liệu phù hợp với mapping.

## 5. Phân biệt Optional của thuộc tính và Optional của query

Hai trường hợp sau có ý nghĩa khác nhau:

```java
Optional<PersonSummary> findByEmail(String email);
```

Kiểu trả về của repository nói rằng **có thể không tìm thấy một PersonSummary** theo email. `Optional.empty()` nghĩa là query không tìm được hàng.

Trong khi đó:

```java
public interface PersonSummary {
    Optional<String> getNickname();
}
```

Getter projection nói rằng **một hàng Person đã tìm thấy nhưng property nickname của hàng đó có thể null**.

Ví dụ có thể nhận được `Optional<PersonSummary>` có giá trị, trong khi `summary.getNickname()` là `Optional.empty()`. Người đó tồn tại, chỉ là chưa có biệt danh.

Đừng dùng `Optional<List<PersonSummary>>` cho query nhiều kết quả. Repository trả `List<PersonSummary>` và dùng list rỗng khi không có hàng; Optional của thuộc tính vẫn có thể xuất hiện bên trong từng projection.

## 6. Default method so với @Value và SpEL

Spring Data projection cũng cho phép dùng `@Value` để tính thuộc tính bằng SpEL:

```java
public interface PersonSummary {
    String getFirstName();
    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
```

Đây là open projection vì biểu thức có thể truy cập target object. Spring Data không thể suy ra đầy đủ những thuộc tính nào sẽ được dùng trong biểu thức, nên có thể không tối ưu việc chọn cột như closed projection.

So sánh:

| Tiêu chí | Default method | `@Value` / SpEL |
| --- | --- | --- |
| Nguồn dữ liệu | Accessor của chính projection | Target object, method argument hoặc Spring bean theo biểu thức |
| Logic phù hợp | Tính toán đơn giản từ các getter đã khai báo | Biểu thức phức tạp hơn hoặc cần gọi bean |
| Loại projection | Có thể giữ closed projection | Là open projection |
| Độ an toàn refactor | Java compiler kiểm tra lời gọi method | Chuỗi SpEL cần được kiểm tra khi chạy |

Với phép tính đơn giản như ghép tên hoặc fallback từ Optional, default method thường dễ đọc và dễ refactor hơn. Dùng SpEL khi thật sự cần khả năng truy cập target hoặc bean.

## 7. Dùng default method với repository projection

Repository method có thể trả về interface projection trực tiếp:

```java
public interface PersonRepository extends JpaRepository<Person, Long> {
    List<PersonSummary> findByLastNameOrderByFirstNameAscIdAsc(String lastName);
}
```

Spring Data tạo projection cho từng hàng. Caller dùng getter gốc, nullable wrapper và default method như một object view:

```java
for (PersonSummary person : repository.findByLastNameOrderByFirstNameAscIdAsc("Nguyen")) {
    System.out.println(person.getDisplayName());
}
```

Query method có thể trả `Optional<PersonSummary>` nếu điều kiện bảo đảm tối đa một hàng, hoặc `List<PersonSummary>` nếu có nhiều người phù hợp. Đây là cardinality của query, độc lập với việc một getter bên trong projection có trả Optional hay không.

### Projection từ @Query

Interface projection cũng có thể dùng với `@Query`, miễn là query trả các alias/thuộc tính phù hợp với accessor:

```java
@Query("select p from Person p where p.lastName = :lastName")
List<PersonSummary> searchByLastName(@Param("lastName") String lastName);
```

Với interface projection, Spring Data ánh xạ thuộc tính trả về vào accessor theo tên property. Với native query hoặc phép chọn alias tùy chỉnh, cần đặt alias tương ứng và kiểm thử trên database thực tế.

## 8. Giới hạn và lưu ý thiết kế

1. **Default method chỉ nên dựa trên accessor của projection.** Đừng giả định có thể truy cập trực tiếp entity hoặc field private.
2. **Giá trị tính bằng default method được tạo trong Java.** Không dùng nó như property JPQL để filter hoặc sort trong database.
3. **Dùng wrapper cho property nullable.** Nếu backing value null, wrapper trả rỗng và caller phải xử lý.
4. **Không nhầm Optional của query với Optional của property.** Một cái biểu diễn hàng có thể không tồn tại; cái kia biểu diễn thuộc tính trong hàng có thể null.
5. **Giữ entity field theo kiểu persistent thông thường.** Dùng wrapper tại projection boundary thay vì đổi field JPA thành Optional.
6. **Không dùng Optional cho collection projection.** List rỗng đã thể hiện không có phần tử.
7. **Không dùng primitive cho thuộc tính có thể null.** Chọn boxed type hoặc nullable wrapper phù hợp.
8. **SpEL có thể làm projection thành open projection.** Dùng default method nếu chỉ cần ghép các accessor.
9. **Tránh logic nghiệp vụ phức tạp trong projection.** Đưa quy tắc phụ thuộc trạng thái, repository hoặc dịch vụ khác vào service/domain layer.
10. **Kiểm tra query thực tế.** Projection có thể giảm dữ liệu đọc nhưng nested association và query tùy chỉnh vẫn có thể tạo join hoặc tải thêm cột.

## 9. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ lưu ba người cùng họ Nguyen. Một người có nickname bằng tên, một người không có nickname và một người có nickname riêng. Repository trả interface projection; default method tạo full name và display name, còn `Optional<String>` biểu diễn nickname nullable.

### Cấu trúc dự án

```text
projection-default-method/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/projection/
        │   ├── ProjectionApplication.java
        │   ├── Person.java
        │   ├── PersonSummary.java
        │   └── PersonRepository.java
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
    <artifactId>projection-default-method</artifactId>
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
spring.datasource.url=jdbc:h2:mem:projectiondb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Person.java`

```java
package com.example.projection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String firstName;

    @Column(nullable = false, length = 80)
    private String lastName;

    @Column(length = 80)
    private String nickname;

    protected Person() {
    }

    public Person(String firstName, String lastName, String nickname) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.nickname = nickname;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getNickname() {
        return nickname;
    }
}
```

### `PersonSummary.java`

```java
package com.example.projection;

import java.util.Optional;

public interface PersonSummary {
    String getFirstName();

    String getLastName();

    Optional<String> getNickname();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }

    default String getDisplayName() {
        return getNickname()
                .filter(value -> !value.isBlank())
                .orElseGet(this::getFullName);
    }
}
```

### `PersonRepository.java`

```java
package com.example.projection;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository extends JpaRepository<Person, Long> {
    List<PersonSummary> findByLastNameOrderByFirstNameAscIdAsc(String lastName);
}
```

### `ProjectionApplication.java`

```java
package com.example.projection;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ProjectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProjectionApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PersonRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Person("An", "Nguyen", "An"),
                    new Person("Binh", "Nguyen", null),
                    new Person("Cuong", "Nguyen", "Cún")
            ));
            repository.flush();

            List<PersonSummary> people =
                    repository.findByLastNameOrderByFirstNameAscIdAsc("Nguyen");

            for (PersonSummary person : people) {
                String nickname = person.getNickname().orElse("(không có)");
                System.out.println(person.getFullName()
                        + " | nickname=" + nickname
                        + " | display=" + person.getDisplayName());
            }
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Stdout:

```text
An Nguyen | nickname=An | display=An
Binh Nguyen | nickname=(không có) | display=Binh Nguyen
Cuong Nguyen | nickname=Cún | display=Cún
```

Giải thích kết quả:

- `An` có nickname nên `getDisplayName()` trả nickname.
- `Binh` có nickname null nên `getNickname()` là `Optional.empty()`; default method dùng `getFullName()`.
- `Cuong` có nickname `Cún`, nên display name dùng giá trị đó.

Default method chạy trên projection proxy và gọi lại các accessor. Không cần thêm cột `fullName` hay `displayName` trong bảng `people`.

## 10. Kiểm thử projection và nullable wrapper

Integration test nên dùng database thử nghiệm để xác nhận Spring Data thật sự tạo projection và chuyển null thành wrapper rỗng:

```java
@DataJpaTest
class PersonRepositoryTest {
    @Autowired
    private PersonRepository repository;

    @Test
    void wrapsNullPropertyAndRunsDefaultMethods() {
        repository.saveAndFlush(new Person("Binh", "Nguyen", null));

        PersonSummary result = repository
                .findByLastNameOrderByFirstNameAscIdAsc("Nguyen")
                .get(0);

        assertThat(result.getNickname()).isEmpty();
        assertThat(result.getFullName()).isEqualTo("Binh Nguyen");
        assertThat(result.getDisplayName()).isEqualTo("Binh Nguyen");
    }
}
```

Đây là phần thân test cần đặt trong test source của dự án và bổ sung các import/assertion tương ứng; `spring-boot-starter-test` cần có trong test dependencies. Nên có thêm test cho nickname không null, chuỗi rỗng, chuỗi chỉ có khoảng trắng và query không có người phù hợp.

## 11. Lỗi thường gặp

1. **Trả null từ getter Optional:** nullable wrapper do Spring Data cung cấp nên trả `Optional.empty()` khi property null; caller không cần kiểm tra Optional null.
2. **Nhầm query không tìm thấy với property null:** repository `Optional<PersonSummary>` rỗng nghĩa là không có hàng; `getNickname()` rỗng nghĩa là hàng có tồn tại nhưng nickname null.
3. **Khai báo Optional trên field entity:** giữ field persistent là kiểu Java thông thường như `String`; khai báo wrapper ở projection getter.
4. **Dùng default method nhưng gọi field không có accessor:** default method nên dùng các getter của projection proxy.
5. **Dùng default method cho logic quá phức tạp:** chuyển logic sang service/mapper hoặc DTO.
6. **Dùng @Value khi chỉ cần ghép getter:** SpEL làm projection thành open projection và có thể giảm khả năng tối ưu chọn cột.
7. **Dùng primitive cho thuộc tính nullable:** chọn boxed type hoặc nullable wrapper.
8. **Khai báo Optional<List<T>>:** dùng List và xử lý list rỗng.
9. **Cho rằng default method có thể dùng trong WHERE/ORDER BY:** method này chạy ở Java, không phải persistent property hay JPQL expression.
10. **Không kiểm thử với null thật:** thêm integration test với dữ liệu SQL NULL để xác nhận wrapper và default method.

## 12. Nguyên tắc thực hành

- Dùng closed interface projection khi chỉ cần một tập thuộc tính của entity.
- Dùng default method cho giá trị dẫn xuất đơn giản từ accessor của projection.
- Dùng `Optional<T>` hoặc nullable wrapper được Spring Data hỗ trợ cho property có thể null.
- Giữ entity field theo kiểu persistent bình thường; wrapper là hợp đồng ở projection boundary.
- Phân biệt Optional của query với Optional của thuộc tính.
- Dùng `@Value`/SpEL khi cần target object hoặc bean, và cân nhắc tác động open projection.
- Đưa logic nghiệp vụ phức tạp vào service/domain layer.
- Kiểm thử cả giá trị null, có giá trị và chuỗi rỗng; xác nhận SQL khi tối ưu projection.

Điểm cốt lõi: **Default method tính giá trị dẫn xuất từ các accessor của projection ngay trong Java; nullable wrapper như `Optional<T>` biểu diễn property nguồn có thể null. Hai cơ chế kết hợp giúp projection gọn, an toàn với null và vẫn giữ rõ ranh giới giữa dữ liệu truy vấn với giá trị hiển thị.**