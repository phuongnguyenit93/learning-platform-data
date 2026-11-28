# Testcontainers với Neo4j cùng phiên bản mục tiêu

## Mục tiêu bài học

Spring Data Neo4j (SDN) ánh xạ entity, relationship và repository lên Neo4j. Unit test có thể kiểm tra logic service hoặc mock repository, nhưng không chứng minh được Cypher thực sự chạy đúng trên server, mapping có tạo đúng graph hay transaction có rollback như mong đợi.

Testcontainers giúp khởi chạy một Neo4j server thật trong Docker khi chạy integration test. Điểm quan trọng của bài học này là chọn đúng image Neo4j tương ứng với môi trường mục tiêu. Nếu production dùng Neo4j 5.26.0 Community, integration test nên chạy cùng phiên bản và edition đó thay vì dùng tag chung như `neo4j:5` hoặc `latest`.

Bài học hướng dẫn cách pin phiên bản image, khai báo dependency Testcontainers, kết nối Spring Boot với container, viết integration test cho repository và Cypher, chuẩn bị schema/fixture, xử lý lifecycle container, và xác định giới hạn của kiểm thử một node so với môi trường production.

## 1. Vì sao cần Neo4j thật trong integration test?

Mock repository hữu ích khi kiểm tra một service có gọi đúng collaborator hay không. Tuy nhiên, mock không thực thi Cypher và không chạy mapping của SDN. Một test có thể xanh dù query sai cú pháp, tên property không khớp, relationship direction bị đảo hoặc constraint chưa được tạo.

Integration test với Neo4j thật có thể xác minh:

- SDN kết nối được bằng Neo4j Java Driver.
- `@Node`, `@Id`, `@Relationship` và `@RelationshipProperties` được ánh xạ đúng.
- Derived query và custom `@Query` thực thi đúng trên Cypher.
- `Neo4jTemplate` và `Neo4jClient` thao tác trên graph thật.
- Uniqueness constraint, index và migration hoạt động với phiên bản server mục tiêu.
- Transaction commit/rollback theo cấu hình.
- Các kiểu dữ liệu và conversion được Neo4j chấp nhận.

Testcontainers không thay thế unit test. Nên giữ unit test nhanh cho logic thuần Java, sau đó dùng một tập integration test có chọn lọc để kiểm chứng hợp đồng giữa ứng dụng và Neo4j.

## 2. Ba phiên bản cần phân biệt

Khi nói “dùng cùng phiên bản mục tiêu”, cần phân biệt ba thành phần:

| Thành phần | Ví dụ | Quyết định phiên bản |
|---|---|---|
| Neo4j server image | `neo4j:5.26.0-community` | Nên khớp chính xác phiên bản và edition production |
| Testcontainers Java | `2.0.5` hoặc release line đang dùng | Tương thích với Java, JUnit và Spring Boot của dự án |
| Neo4j Java Driver | Được Spring Boot/SDN dependency management quản lý | Chọn phiên bản driver tương thích với SDN và server |

Phiên bản Testcontainers không phải phiên bản Neo4j server. Việc nâng Testcontainers từ 2.0.4 lên 2.0.5 không có nghĩa container tự chuyển Neo4j sang phiên bản mới. Neo4j server version được quyết định bởi Docker image tag.

Tương tự, không đặt version của Neo4j Java Driver bằng version của server. Driver và server có chu kỳ phát hành riêng; hãy dùng dependency management của Spring Boot hoặc Spring Data Neo4j để chọn driver tương thích.

## 3. Pin chính xác Docker image của Neo4j

Giả sử production đang chạy Neo4j 5.26.0 Community. Test nên dùng tag cụ thể:

```text
neo4j:5.26.0-community
```

Tránh các tag thay đổi theo thời gian:

```text
neo4j:latest
neo4j:5
neo4j:5-community
```

Tag chỉ rõ major/minor nhưng không cố định patch. Khi image được cập nhật, cùng một test suite có thể chạy trên server version khác mà không có thay đổi source code.

Nếu production dùng Enterprise, hãy dùng image Enterprise tương ứng. Nếu production dùng plugin như APOC, cấu hình procedure, extension hoặc setting riêng, môi trường test cần cài và cấu hình cùng loại thành phần để kiểm tra hành vi liên quan.

Có thể dùng biến build hoặc system property làm một nguồn cấu hình:

```text
neo4j.test.image=neo4j:5.26.0-community
```

Trong CI, truyền cùng giá trị image đã được khai báo trong cấu hình triển khai. Khi production nâng version, thay đổi image test trong cùng pull request hoặc cùng release change để test và môi trường mục tiêu không lệch nhau.

Nếu yêu cầu tái lập tuyệt đối cả nội dung image, có thể pin image digest ngoài tag. Tag cụ thể giúp đọc được phiên bản; digest giúp cố định chính xác image artifact được kéo về.

## 4. Thêm dependency Testcontainers

Với Gradle và Testcontainers 2.x, có thể khai báo các module test cần thiết:

```groovy
dependencies {
    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "org.springframework.boot:spring-boot-testcontainers"

    testImplementation platform("org.testcontainers:testcontainers-bom:2.0.5")
    testImplementation "org.testcontainers:testcontainers-junit-jupiter"
    testImplementation "org.testcontainers:testcontainers-neo4j"
}
```

Nếu Spring Boot BOM của dự án đã quản lý phiên bản Testcontainers, ưu tiên dùng dependency management hiện có và không khai báo một BOM Testcontainers khác có version xung đột.

Với Maven, cách khai báo tương ứng:

Nếu không dùng Spring Boot dependency management để quản lý Testcontainers, import BOM của Testcontainers trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-neo4j</artifactId>
    <scope>test</scope>
</dependency>
```

Các ví dụ trên dùng Testcontainers 2.x. Với dự án vẫn dùng Testcontainers 1.x, artifact và package Java khác:

| Testcontainers 1.x | Testcontainers 2.x |
|---|---|
| `org.testcontainers:neo4j` | `org.testcontainers:testcontainers-neo4j` |
| `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| `org.testcontainers.containers.Neo4jContainer` | `org.testcontainers.neo4j.Neo4jContainer` |

Không trộn dependency 1.x với class package 2.x. Chọn một release line được Spring Boot và các dependency hiện tại hỗ trợ, sau đó dùng đúng tọa độ artifact và import của release line đó.

## 5. Khởi chạy Neo4jContainer bằng JUnit Jupiter

Với Testcontainers 2.x, Neo4j module cung cấp `Neo4jContainer`. Ví dụ dùng một container tĩnh cho toàn bộ test class:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class Neo4jContainerSmokeTest {

    @Container
    static final Neo4jContainer neo4j =
            new Neo4jContainer("neo4j:5.26.0-community")
                    .withAdminPassword("test-password");

    @Test
    void shouldStartNeo4j() {
        assertTrue(neo4j.isRunning());
        assertNotNull(neo4j.getBoltUrl());
    }
}
```

`@Testcontainers` kích hoạt JUnit extension. `@Container` đánh dấu container được extension quản lý. Field `static` có vòng đời theo test class; field instance thường được khởi động và dừng theo từng test method.

Dùng password riêng cho test. Không tái sử dụng thông tin xác thực production hoặc đưa secret thật vào source code.

Neo4j Testcontainers module dựa trên official Docker image của Neo4j và hỗ trợ các image Neo4j 5.x. Container cung cấp Bolt URL để ứng dụng hoặc Driver kết nối sau khi server sẵn sàng.

## 6. Kết nối Spring Boot bằng @ServiceConnection

Với phiên bản Spring Boot hỗ trợ service connection và Testcontainers Neo4j module tương ứng, `@ServiceConnection` giúp Spring Boot tự tạo `Neo4jConnectionDetails` từ container.

Ví dụ:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final Neo4jContainer neo4j =
            new Neo4jContainer("neo4j:5.26.0-community")
                    .withAdminPassword("test-password");

    // Autowire repository và thực hiện integration tests.
}
```

Cần có dependency `spring-boot-testcontainers` trong test scope. Service connection cung cấp connection details cho auto-configuration của Spring Boot; các connection details này được ưu tiên hơn cấu hình connection tương ứng trong application properties.

Đảm bảo version Spring Boot đang dùng có hỗ trợ Neo4j service connection và Testcontainers module version được chọn. Với phiên bản Boot cũ hoặc cấu hình không dùng service connection, có thể dùng `@DynamicPropertySource`.

## 7. Kết nối bằng @DynamicPropertySource

`@DynamicPropertySource` cho phép đưa Bolt URL và thông tin xác thực từ container vào Spring Environment:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    static final Neo4jContainer neo4j =
            new Neo4jContainer("neo4j:5.26.0-community")
                    .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username",
                () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
                neo4j::getAdminPassword);
    }
}
```

Các property này được Spring Boot Neo4j auto-configuration sử dụng để tạo Driver. Không ghi cứng Bolt port vì Testcontainers thường ánh xạ port ngẫu nhiên trên host; lấy URL trực tiếp từ container.

Dùng một trong hai cách kết nối: `@ServiceConnection` hoặc `@DynamicPropertySource`. Không cần cấu hình trùng lặp nếu service connection đã cung cấp đủ connection details.

## 8. Quản lý container theo vòng đời Spring context

JUnit extension dừng container sau khi test class kết thúc. Trong khi đó, Spring TestContext Framework có thể cache `ApplicationContext` và tái sử dụng cho test class khác. Nếu context còn giữ Driver kết nối tới container đã dừng, các test sau có thể lỗi kết nối.

Với test Spring Boot có context được cache, có thể quản lý container như Spring bean để vòng đời container đi cùng context:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.neo4j.Neo4jContainer;

@TestConfiguration(proxyBeanMethods = false)
class Neo4jTestContainerConfiguration {

    @Bean
    @ServiceConnection
    Neo4jContainer neo4jContainer() {
        return new Neo4jContainer("neo4j:5.26.0-community")
                .withAdminPassword("test-password");
    }
}
```

Import cấu hình vào test:

```java
@DataNeo4jTest
@Import(Neo4jTestContainerConfiguration.class)
class CustomerRepositoryTest {
    // Repository được cấu hình bởi test slice.
}
```

Khi container là Spring bean, Spring khởi tạo và start container trước các bean phụ thuộc vào nó, sau đó dừng container khi context bị đóng. Điều này phù hợp với test suite sử dụng chung cached context.

`@DataNeo4jTest` cung cấp repository, client, template và transaction manager; test slice này cũng có transaction imperative mặc định cho mỗi test method. Vì vậy, test đọc lại dữ liệu trong cùng test có thể vẫn đang ở transaction của test. Khi cần xác nhận commit hoặc rollback của một service qua ranh giới transaction thật, hãy dùng `@SpringBootTest` không gắn transaction cho test method hoặc chủ động điều khiển transaction trong test.

Không nên bật reusable container toàn cục chỉ để tăng tốc mà không hiểu trạng thái dữ liệu còn sót lại. Reuse container có thể làm test phụ thuộc thứ tự chạy nếu fixture không được dọn dẹp.

## 9. Viết integration test cho repository SDN

Giả sử có entity Customer:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;

    // Constructor, getter và setter được lược bỏ.
}
```

Repository:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

Integration test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;

@DataNeo4jTest
@Import(Neo4jTestContainerConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void shouldSaveAndFindCustomer() {
        Customer customer = new Customer();
        customer.setName("Alice");
        customer.setEmail("alice@example.test");

        Customer saved = customerRepository.save(customer);

        assertThat(saved.getId()).isNotNull();

        Optional<Customer> found =
                customerRepository.findByEmail("alice@example.test");

        assertThat(found)
                .isPresent()
                .get()
                .extracting(Customer::getName)
                .isEqualTo("Alice");
    }
}
```

Ví dụ này kiểm tra mapping và derived query trên Neo4j thật. Trong test thực tế, bảo đảm entity constructor và accessors phù hợp với mapping model của dự án.

`@DataNeo4jTest` phù hợp khi chỉ cần kiểm tra repository, mapping context và các thành phần data access. Dùng `@SpringBootTest` khi cần kiểm tra service, transaction boundary, security, configuration hoặc nhiều bean ứng dụng cùng hoạt động.

## 10. Kiểm tra relationship mapping

Với graph, chỉ xác nhận node được lưu là chưa đủ. Cần kiểm tra cả relationship type, direction, properties và dữ liệu node đích.

Ví dụ:

```java
import java.util.List;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Relationship(type = "ACTED_IN", direction = Relationship.Direction.INCOMING)
    private List<Person> actors;

    // Constructor, getter và setter được lược bỏ.
}
```

Một test nên:

1. Tạo Person và Movie.
2. Lưu Movie với danh sách actors theo mapping.
3. Đọc lại Movie từ repository.
4. Xác nhận actor được hydrate.
5. Dùng Cypher kiểm tra relationship type và hướng cạnh.
6. Xác nhận không tạo cạnh trùng sau khi cập nhật entity.

Nếu dùng `@RelationshipProperties`, hãy kiểm tra các property trên relationship cũng được lưu và đọc đúng. Các lỗi direction hoặc relationship type thường không thể phát hiện bằng mock repository.

## 11. Kiểm tra custom Cypher và Neo4jClient

Custom query có thể chạy đúng cú pháp nhưng trả về projection hoặc graph shape không đúng với mapping mong đợi. Integration test cần thực thi query trên phiên bản Neo4j mục tiêu.

Ví dụ repository:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    @Query("""
        MATCH (c:Customer {email: $email})
        RETURN c
        """)
    Optional<Customer> findCustomerByEmail(String email);
}
```

Test cần xác nhận:

- Query chạy thành công trên image Neo4j đã pin.
- Parameter được bind đúng.
- Result mapping trả đúng entity/projection.
- Trường hợp không có kết quả được xử lý đúng.
- Query có nhiều kết quả không bị ép vào kiểu trả về đơn ngoài ý muốn.

Với `Neo4jClient`, có thể kiểm tra trực tiếp graph:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;

@Autowired
Neo4jClient neo4jClient;

long countCustomers() {
    return neo4jClient.query(
                    "MATCH (c:Customer) RETURN count(c) AS total")
            .fetchAs(Long.class)
            .one()
            .orElse(0L);
}
```

Dùng client trong test để xác minh trạng thái database thực tế, đặc biệt khi repository mapping che giấu một số chi tiết của graph.

## 12. Chuẩn bị schema và migration trong test

Nếu ứng dụng cần uniqueness constraint, index hoặc schema migration, integration test nên tạo schema bằng cùng công cụ migration và cùng phiên bản Cypher được dùng khi triển khai.

Không chỉ tạo entity rồi kỳ vọng SDN tự tạo mọi constraint. SDN hiện đại không thay thế quy trình quản lý schema database bằng migration.

Một quy trình test có thể gồm:

1. Khởi động Neo4j container với đúng image.
2. Chạy migration schema.
3. Kiểm tra constraint/index đã tồn tại.
4. Nạp fixture.
5. Thực thi repository/service test.
6. Dọn dữ liệu test.

Ví dụ kiểm tra constraint:

```cypher
SHOW CONSTRAINTS;
```

Nếu migration dùng cú pháp chỉ có trong một phiên bản Neo4j mới hơn, test chạy trên image cũ sẽ phát hiện khác biệt. Đây là lý do cần pin image đúng version mục tiêu.

Giữ migration test tách biệt với test logic thông thường nếu chi phí khởi tạo schema lớn. Tuy nhiên, cần ít nhất một integration test chạy migration từ database trống để bảo đảm đường triển khai schema có thể tái lập.

## 13. Dữ liệu test và cách cô lập test

Các test không nên phụ thuộc dữ liệu do test khác tạo. Có thể cô lập bằng một trong các cách:

- Dọn graph trước mỗi test và tạo fixture riêng.
- Dùng database riêng cho test suite nếu server/edition hỗ trợ.
- Dùng namespace hoặc test run ID trong khóa dữ liệu.
- Tạo container riêng cho test class khi cần cấu hình khác biệt.

Ví dụ dọn dữ liệu trong database test:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(Neo4jTestContainerConfiguration.class)
class CustomerGraphIntegrationTest {

    @Autowired
    Neo4jClient neo4jClient;

    @BeforeEach
    void cleanGraph() {
        neo4jClient.query("MATCH (n) DETACH DELETE n").run();
    }
}
```

Lệnh trên xóa tất cả node và relationship trong database đang được client chọn. Nó không xóa schema constraint và index. Chỉ dùng trên database test cô lập, không chạy với connection production hoặc database dùng chung.

Nếu test suite chạy song song, một test dọn toàn bộ graph có thể xóa dữ liệu của test khác. Khi chạy song song, hãy dùng database/container riêng hoặc xóa theo namespace mà test sở hữu.

Không giả định mọi test tự rollback toàn bộ thao tác Neo4j. Hãy hiểu transaction semantics của test slice và xác minh dữ liệu được dọn đúng cách.

## 14. Test transaction rollback

Một integration test quan trọng là xác nhận các thay đổi graph được rollback khi service ném exception.

Ví dụ service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void createThenFail(Customer customer) {
        customerRepository.save(customer);
        throw new IllegalStateException("Simulated failure");
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(Neo4jTestContainerConfiguration.class)
class CustomerTransactionIntegrationTest {

    @Autowired
    CustomerService customerService;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void shouldRollbackGraphWriteWhenServiceFails() {
        Customer customer = new Customer();
        customer.setName("Temporary");
        customer.setEmail("temporary@example.test");

        assertThatThrownBy(() -> customerService.createThenFail(customer))
                .isInstanceOf(IllegalStateException.class);

        assertThat(customerRepository.findByEmail("temporary@example.test"))
                .isEmpty();
    }
}
```

Test cần gọi service qua Spring bean proxy, không tự tạo object bằng `new`. Đọc lại graph sau khi transaction kết thúc để xác nhận node không tồn tại.

Nếu test method hoặc test slice có transaction bao ngoài, cần chú ý transaction propagation và cách test framework quản lý transaction. Mục tiêu là kiểm tra rollback của service transaction thật, không chỉ quan sát trạng thái trong cùng transaction chưa commit.

## 15. Kiểm thử phiên bản và edition mục tiêu

Dùng cùng version tag là bước đầu. Cần kiểm tra các thuộc tính môi trường có thể làm thay đổi hành vi:

| Thuộc tính | Cần đồng bộ khi nào? |
|---|---|
| Neo4j major/minor/patch | Khi kiểm tra Cypher, index, constraint, driver compatibility và migration |
| Community/Enterprise | Khi dùng tính năng chỉ có ở Enterprise |
| APOC hoặc plugin khác | Khi query hoặc stored procedure phụ thuộc plugin |
| Neo4j configuration | Khi test phụ thuộc setting về procedure, memory hoặc transaction |
| Authentication/authorization | Khi test quyền truy cập, role hoặc database privilege |
| Database topology | Khi test cluster, routing, failover hoặc causal consistency |

Ví dụ dùng plugin APOC nếu production cần plugin này:

```java
new Neo4jContainer("neo4j:5.26.0-community")
        .withAdminPassword("test-password")
        .withPlugins("apoc");
```

Plugin phải tương thích với phiên bản Neo4j trong image. Không thêm plugin vào test nếu production không có và query không cần plugin, vì điều đó có thể che giấu dependency triển khai bị thiếu.

Với Enterprise Neo4j 5.x, cần dùng image Enterprise phù hợp và chấp nhận điều khoản license theo hướng dẫn Neo4j. Không dùng Enterprise image trong CI nếu pipeline chưa có cơ chế license acceptance hợp lệ.

Ví dụ container Enterprise 5.x cần cấu hình chấp nhận license theo hướng dẫn của Neo4j:

```java
new Neo4jContainer("neo4j:5.26.0-enterprise")
        .withEnv("NEO4J_ACCEPT_LICENSE_AGREEMENT", "yes")
        .withAdminPassword("test-password");
```

## 16. Testcontainers không tự mô phỏng cluster production

Một `Neo4jContainer` thông thường chạy một Neo4j server instance. Nó rất phù hợp cho repository, Cypher, mapping, constraint, transaction cơ bản và migration test.

Nó không tự mô phỏng đầy đủ:

- Neo4j cluster nhiều member.
- Routing và failover.
- Replication lag hoặc network partition.
- Causal consistency giữa các member.
- Load balancing và topology changes.
- Backup/restore hoặc vận hành production quy mô lớn.

Nếu ứng dụng phụ thuộc vào những đặc tính này, cần thêm một tầng kiểm thử với cluster hoặc môi trường staging tương ứng. Không kết luận cluster behavior đúng chỉ vì single-node Testcontainers test thành công.

## 17. Chạy trong CI

Testcontainers cần một container runtime tương thích, thường là Docker Engine hoặc môi trường Docker-compatible. Máy developer và CI runner phải có quyền truy cập Docker daemon.

Một pipeline cơ bản:

1. Cài JDK và build tool theo dự án.
2. Xác nhận Docker daemon sẵn sàng.
3. Chạy unit test.
4. Chạy integration test dùng Testcontainers.
5. Thu thập log container khi test thất bại.
6. Dọn container và volume theo lifecycle của Testcontainers.

Không dùng một Neo4j container đang chạy sẵn ở máy developer làm mặc định cho CI; mục tiêu là test có thể tự tạo môi trường sạch và tái lập.

Nếu CI chạy Docker-in-Docker hoặc remote Docker daemon, kiểm tra cấu hình network và port mapping. Testcontainers cung cấp Bolt URL và mapped port; không giả định container luôn truy cập được qua `localhost:7687`.

Có thể tăng timeout startup khi CI chậm, nhưng nên xác định nguyên nhân nếu container thường xuyên khởi động lâu. Tránh thêm `Thread.sleep` cố định để chờ database; dùng wait strategy và readiness do Testcontainers module cung cấp.

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Docker daemon không khả dụng | Docker chưa chạy hoặc CI không cấp socket | Kiểm tra container runtime và quyền truy cập |
| Neo4j container không khởi động | Sai tag, thiếu RAM, cấu hình không hợp lệ | Xem container logs và image |
| Connection refused | App kết nối trước khi Neo4j sẵn sàng hoặc dùng sai URL | Dùng container Bolt URL và readiness |
| Authentication failed | Username/password không khớp | Dùng thông tin từ container |
| Test chạy trên version khác production | Dùng tag `neo4j:5` hoặc `latest` | Pin full version tag |
| Service connection không được tạo | Thiếu `spring-boot-testcontainers` hoặc version không hỗ trợ | Kiểm tra Boot version và dependency |
| Không tìm thấy Neo4jContainer class | Import không khớp Testcontainers major | Kiểm tra package/artifact 1.x hay 2.x |
| Test sau thất bại do container đã dừng | JUnit extension dừng container trong khi context được cache | Quản lý container như Spring bean hoặc import container configuration |
| Test phụ thuộc thứ tự | Dữ liệu graph còn từ test trước | Dọn fixture hoặc dùng database/container riêng |
| Migration chạy được local nhưng lỗi trong CI | Image Neo4j local khác version CI | Dùng cùng image tag/digest |
| APOC procedure không tồn tại | Plugin không được cài trong container | Cấu hình plugin tương thích |
| Constraint test thất bại do dữ liệu cũ | Graph chưa được dọn hoặc fixture duplicate | Tạo database sạch và chuẩn hóa fixture |

## 19. Quy trình thiết lập Testcontainers có thể tái lập

Khi thêm Testcontainers vào module SDN:

1. Xác định Neo4j version, edition và plugin đang dùng ở môi trường mục tiêu.
2. Pin Docker image bằng full version tag hoặc digest.
3. Chọn Testcontainers major tương thích với Spring Boot, JUnit và Java.
4. Dùng đúng dependency artifact và package của major đã chọn.
5. Khởi tạo `Neo4jContainer` bằng password test riêng.
6. Kết nối Spring bằng `@ServiceConnection` hoặc `@DynamicPropertySource`.
7. Chọn `@DataNeo4jTest` cho repository/mapping hoặc `@SpringBootTest` cho toàn application flow.
8. Chạy migration schema trên database test sạch.
9. Tạo fixture và kiểm thử repository, relationship, Cypher, transaction.
10. Cô lập dữ liệu giữa các test.
11. Thu thập log container khi thất bại.
12. Chạy cùng image trong CI và cập nhật image test cùng lúc với thay đổi version production.

## 20. Tự kiểm tra

1. Vì sao mock repository không thay thế integration test với Neo4j thật?
2. Neo4j server image version khác Testcontainers library version như thế nào?
3. Vì sao nên pin full version tag thay vì dùng `neo4j:5` hoặc `latest`?
4. Vì sao không nên tự đặt Neo4j Java Driver version bằng server version?
5. Testcontainers 1.x và 2.x khác nhau ở dependency artifact và package nào?
6. `Neo4jContainer` cung cấp thông tin kết nối nào cho ứng dụng?
7. `@ServiceConnection` giúp Spring Boot kết nối đến container ra sao?
8. Khi nào dùng `@DynamicPropertySource`?
9. Vì sao container managed bởi Spring bean có thể phù hợp hơn JUnit static container với cached context?
10. Cần kiểm tra gì khi test relationship mapping?
11. Vì sao migration nên được chạy trên Neo4j image cùng phiên bản mục tiêu?
12. Làm thế nào cô lập dữ liệu giữa các integration test?
13. Vì sao cần gọi service qua Spring proxy khi test transaction rollback?
14. Testcontainers single-node không thể chứng minh những hành vi cluster nào?
15. Cần chuẩn bị gì để chạy Testcontainers ổn định trong CI?

Hãy cấu hình Testcontainers với đúng image Neo4j mà môi trường triển khai đang dùng. Viết một repository integration test lưu và đọc node Customer, một test xác minh relationship direction, một test chạy custom Cypher và một test kiểm tra rollback. Sau đó chạy migration schema trên container sạch, chạy lại toàn bộ test hai lần để kiểm tra tính độc lập dữ liệu, rồi xác nhận CI dùng cùng image tag với môi trường mục tiêu.

## Tài liệu tham khảo

- [Testcontainers for Java — Neo4j Module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Testcontainers — Neo4j Module](https://testcontainers.com/modules/neo4j/)
- [Spring Boot Reference — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot Reference 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Data Neo4j — Testing and configuration reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Spring Data Neo4j — With Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
