# Đăng ký Neo4jClient, Neo4jTemplate và Neo4jTransactionManager

Bài học này thuộc chương **Cấu hình và kiến trúc** của module **SPRING_DATA_NEO4J**. Khi xây dựng tầng dữ liệu đồ thị, ứng dụng thường cần nhiều cách làm việc với cùng một Neo4j database: chạy Cypher trực tiếp, ánh xạ node và relationship thành entity, và quản lý transaction theo cơ chế của Spring. Spring Data Neo4j cung cấp `Neo4jClient`, `Neo4jTemplate` và `Neo4jTransactionManager` cho ba nhu cầu này.

Ba thành phần cần được cấu hình nhất quán. Chúng phải sử dụng cùng `Driver` và cùng cách chọn database để repository, template, client và `@Transactional` có thể tham gia cùng một transaction. Với cấu hình Java thuần, `AbstractNeo4jConfig` đã cung cấp phần lớn hạ tầng này. Với Spring Boot, starter thường tự động đăng ký các bean cần thiết dựa trên cấu hình ứng dụng.

## 1. Vai trò của từng thành phần

Trước khi đăng ký bean, cần phân biệt trách nhiệm của từng lớp:

| Thành phần | Trách nhiệm | Khi nào sử dụng |
|---|---|---|
| `Driver` | Quản lý kết nối tới máy chủ Neo4j, connection pool và phiên làm việc | Thành phần nền tảng được các lớp còn lại dùng chung |
| `Neo4jClient` | Thực thi Cypher và ánh xạ kết quả theo cách do ứng dụng chỉ định | Truy vấn tùy biến, thủ tục Cypher hoặc kết quả không phù hợp với entity chuẩn |
| `Neo4jTemplate` | Cung cấp thao tác persistence và ánh xạ entity dựa trên mapping context | Lưu, tìm, đếm và thao tác với node entity mà không cần tạo repository riêng |
| `Neo4jTransactionManager` | Kết nối transaction native của Neo4j với cơ chế transaction của Spring | Dùng `@Transactional` hoặc `TransactionTemplate` cho thao tác Neo4j |

`Neo4jClient` làm việc gần với Cypher và Java Driver hơn. Ứng dụng thường tự viết câu truy vấn, bind tham số và quyết định cách đọc từng cột trong record. `Neo4jTemplate` làm việc ở mức domain model: nó sử dụng mapping metadata để chuyển đổi giữa entity Java và cấu trúc đồ thị. Repository của Spring Data Neo4j cũng dựa trên hạ tầng template và transaction đã được đăng ký.

`Neo4jTransactionManager` triển khai `PlatformTransactionManager`. Spring sử dụng nó để mở, commit hoặc rollback transaction Neo4j khi chạy trong phạm vi quản lý transaction. Nó không phải connection pool và cũng không thay thế `Driver`.

## 2. Đăng ký hạ tầng bằng AbstractNeo4jConfig

Trong ứng dụng imperative không dùng Spring Boot, cách cấu hình Java phổ biến là mở rộng `AbstractNeo4jConfig`. Lớp cơ sở này tạo các thành phần như mapping context, conversions, `Neo4jClient`, `Neo4jTemplate` và transaction manager. Ứng dụng cần cung cấp `Driver` để các bean đó kết nối tới Neo4j.

Ví dụ cấu hình:

```java
import java.net.URI;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.AbstractNeo4jConfig;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.graph.repository",
    neo4jTemplateRef = "neo4jTemplate",
    transactionManagerRef = "transactionManager"
)
public class Neo4jConfiguration extends AbstractNeo4jConfig {

    @Value("${app.neo4j.uri}")
    private URI uri;

    @Value("${app.neo4j.username}")
    private String username;

    @Value("${app.neo4j.password}")
    private String password;

    @Bean(destroyMethod = "close")
    @Override
    public Driver driver() {
        return GraphDatabase.driver(
            uri,
            AuthTokens.basic(username, password)
        );
    }
}
```

Đặt thông tin kết nối bên ngoài mã nguồn, chẳng hạn trong cấu hình môi trường:

```yaml
app:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    username: ${NEO4J_USERNAME:neo4j}
    password: ${NEO4J_PASSWORD}
```

Trong ví dụ này:

- `@Configuration` đưa lớp vào Spring application context.
- `@EnableNeo4jRepositories` chỉ định package chứa repository. Hai thuộc tính `neo4jTemplateRef` và `transactionManagerRef` liên kết repository với đúng bean được đăng ký.
- `driver()` cung cấp một `Driver` dùng chung. `destroyMethod = "close"` yêu cầu Spring đóng driver khi application context dừng.
- `AbstractNeo4jConfig` đăng ký các bean hạ tầng còn lại dựa trên driver và mapping context.

Không tạo `Driver` mới trong từng service hoặc mỗi lần gọi repository. Driver được thiết kế để dùng chung trong ứng dụng; nó quản lý connection pool và nên tồn tại theo vòng đời application context.

### Chọn database đích

Nếu máy chủ chỉ dùng database mặc định, provider được cung cấp bởi `AbstractNeo4jConfig` có thể đáp ứng. Khi cần chỉ định một database cụ thể, có thể override `databaseSelectionProvider()`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Bean
@Override
protected DatabaseSelectionProvider databaseSelectionProvider() {
    return () -> DatabaseSelection.byName("customer-graph");
}
```

Database `customer-graph` phải được tạo trước và tài khoản kết nối phải có quyền truy cập. Provider này được `AbstractNeo4jConfig` dùng để cấu hình client và transaction manager. Nếu tự tạo các bean thay thế, hãy truyền cùng một provider vào cả hai thành phần để tránh việc truy vấn và transaction nhắm tới hai database khác nhau.

## 3. Những bean được đăng ký trong application context

Khi mở rộng `AbstractNeo4jConfig`, ứng dụng không cần tự khởi tạo từng thành phần trong ví dụ cơ bản. Các bean chính được cung cấp như sau:

| Tên bean | Kiểu bean được công bố | Vai trò |
|---|---|---|
| `driver` | `Driver` | Kết nối tới Neo4j; do ứng dụng cung cấp |
| `neo4jClient` | `Neo4jClient` | Thực thi Cypher và ánh xạ record |
| `neo4jTemplate` | `Neo4jOperations` (triển khai bởi `Neo4jTemplate`) | Thao tác với entity và graph mapping |
| `transactionManager` | `PlatformTransactionManager` (triển khai bởi `Neo4jTransactionManager`) | Quản lý transaction Neo4j |
| `neo4jMappingContext` | `Neo4jMappingContext` | Metadata ánh xạ entity |
| `neo4jConversions` | `Neo4jConversions` | Chuyển đổi kiểu dữ liệu tùy chỉnh |
| `databaseSelectionProvider` | `DatabaseSelectionProvider` | Chọn database cho thao tác |

Method `neo4jTemplate(...)` trong cấu hình nền công bố abstraction `Neo4jOperations`; bean được tạo là `Neo4jTemplate`. Vì vậy, có thể inject `Neo4jOperations` để phụ thuộc vào contract chung và không gắn service với implementation cụ thể.

Tương tự, method `transactionManager(...)` công bố kiểu `PlatformTransactionManager`, trong khi implementation được tạo cho Neo4j là `Neo4jTransactionManager`. Ứng dụng service thường chỉ cần phụ thuộc vào abstraction `PlatformTransactionManager` nếu tạo `TransactionTemplate` thủ công.

Các tên bean mặc định có ý nghĩa đối với `@EnableNeo4jRepositories`: repository mặc định tìm `neo4jTemplate` và `transactionManager`. Nếu đổi tên một bean, hãy cập nhật `neo4jTemplateRef` hoặc `transactionManagerRef` tương ứng.

## 4. Cấu hình bằng Spring Boot

Với Spring Boot, dependency `spring-boot-starter-data-neo4j` kích hoạt auto-configuration cho Neo4j Driver và Spring Data Neo4j. Phần lớn ứng dụng chỉ cần cung cấp thuộc tính kết nối:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE:neo4j}
```

Spring Boot tạo các bean cần thiết cho driver, client, template, mapping và transaction manager theo phiên bản dependency đang sử dụng. Các repository có thể được phát hiện theo package cấu hình của ứng dụng; nếu muốn chỉ định package riêng, dùng `@EnableNeo4jRepositories` với các tham số phù hợp.

Trong ứng dụng đã dùng auto-configuration, tránh khai báo thêm một bộ `Driver`, `Neo4jClient`, `Neo4jTemplate` và transaction manager trùng vai trò. Nếu cần tùy biến, hãy kiểm tra điều kiện auto-configuration của phiên bản Spring Boot đang dùng và chỉ thay thế bean cần thay đổi. Không kết hợp tùy tiện một `Neo4jClient` từ driver này với transaction manager của driver khác.

## 5. Sử dụng Neo4jClient cho Cypher tùy biến

`Neo4jClient` phù hợp khi cần kiểm soát câu Cypher hoặc ánh xạ kết quả theo cấu trúc riêng. Ví dụ, tìm tên khách hàng bằng thuộc tính ID:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public class CustomerLookupService {

    private final Neo4jClient neo4jClient;

    public CustomerLookupService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<String> findName(String customerId) {
        return neo4jClient.query("""
                MATCH (c:Customer {id: $id})
                RETURN c.name AS name
                """)
            .bind(customerId).to("id")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) -> record.get("name").asString())
            .one();
    }
}
```

Ứng dụng bind tham số bằng `.bind(...).to(...)`, tránh ghép trực tiếp dữ liệu đầu vào vào chuỗi Cypher. `fetchAs(String.class)` khai báo kiểu kết quả mong muốn và `mappedBy(...)` chuyển giá trị trong record thành kiểu Java. Phương thức `one()` trả về `Optional` vì truy vấn có thể không tìm thấy node.

Với truy vấn ghi không cần trả entity, có thể dùng `run()`:

```java
neo4jClient.query("""
        MATCH (c:Customer {id: $id})
        SET c.name = $name
        """)
    .bind(customerId).to("id")
    .bind(newName).to("name")
    .run();
```

`Neo4jClient` không tự động biến mọi kết quả Cypher thành domain entity như template. Khi cần map kết quả phức tạp, hãy khai báo mapper phù hợp hoặc cân nhắc dùng `Neo4jTemplate` hay repository.

## 6. Sử dụng Neo4jTemplate cho thao tác entity

`Neo4jTemplate` cung cấp thao tác persistence cấp cao và sử dụng mapping metadata của Spring Data Neo4j. Khi inject qua interface `Neo4jOperations`, service có thể lưu entity, tìm theo ID hoặc đếm số entity:

```java
import java.util.Optional;

import com.example.graph.domain.Customer;
import org.springframework.data.neo4j.core.Neo4jOperations;
import org.springframework.stereotype.Service;

@Service
public class CustomerGraphService {

    private final Neo4jOperations neo4jTemplate;

    public CustomerGraphService(Neo4jOperations neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public Customer save(Customer customer) {
        return neo4jTemplate.save(customer);
    }

    public Optional<Customer> findById(String id) {
        return neo4jTemplate.findById(id, Customer.class);
    }

    public long countCustomers() {
        return neo4jTemplate.count(Customer.class);
    }
}
```

Kiểu ID trong `findById` phải khớp với thuộc tính `@Id` của entity `Customer`. Template phù hợp khi cần thao tác entity nhưng không muốn tạo một repository chỉ cho một vài thao tác cơ bản. Repository vẫn là lựa chọn tốt khi cần API truy cập dữ liệu theo domain rõ ràng, derived query hoặc các phương thức `@Query` được tổ chức theo aggregate.

## 7. Quản lý transaction với Neo4jTransactionManager

`Neo4jTransactionManager` kết nối transaction native của Neo4j với Spring transaction abstraction. Khi method service được đánh dấu `@Transactional`, Spring mở transaction trước khi chạy method và commit khi method kết thúc bình thường. Nếu có lỗi phù hợp với quy tắc rollback, transaction được rollback.

Ví dụ phối hợp repository và client trong cùng một service:

```java
import com.example.graph.repository.CustomerRepository;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final Neo4jClient neo4jClient;

    public CustomerService(
            CustomerRepository customerRepository,
            Neo4jClient neo4jClient) {
        this.customerRepository = customerRepository;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void renameCustomer(String id, String newName) {
        customerRepository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Customer not found"));

        neo4jClient.query("""
                MATCH (c:Customer {id: $id})
                SET c.name = $name
                """)
            .bind(id).to("id")
            .bind(newName).to("name")
            .run();
    }
}
```

Lệnh đọc qua repository và lệnh ghi qua `Neo4jClient` có thể tham gia cùng transaction Spring quản lý khi chúng dùng chung driver, database selection và transaction manager đã cấu hình. Nếu truy vấn ghi thất bại và lỗi làm transaction rollback, thay đổi trong transaction đó sẽ được hoàn tác.

`@Transactional` hoạt động qua proxy của Spring. Lời gọi phải đi qua proxy để transaction được mở; một method gọi method khác trong cùng object (self-invocation) hoặc gọi method private không tự động tạo thêm transaction chỉ vì method đích có annotation. Với luồng nội bộ cần kiểm soát rõ ràng, có thể dùng `TransactionTemplate`.

### Dùng TransactionTemplate

`TransactionTemplate` hữu ích khi cần xác định ranh giới transaction trong một đoạn code hoặc trong method không được gọi qua proxy:

```java
import org.springframework.stereotype.Service;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class CustomerMaintenanceService {

    private final TransactionTemplate transactionTemplate;
    private final Neo4jClient neo4jClient;

    public CustomerMaintenanceService(
            PlatformTransactionManager transactionManager,
            Neo4jClient neo4jClient) {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.neo4jClient = neo4jClient;
    }

    public void deactivateCustomer(String id) {
        transactionTemplate.executeWithoutResult(status -> {
            neo4jClient.query("""
                    MATCH (c:Customer {id: $id})
                    SET c.active = false
                    """)
                .bind(id).to("id")
                .run();
        });
    }
}
```

Nếu application có nhiều `PlatformTransactionManager`, cần inject đúng manager bằng `@Qualifier` hoặc cấu hình rõ tên bean. Khi đó, `@Transactional(transactionManager = "...")` cũng cần trỏ tới đúng bean. Repository có thể khai báo `transactionManagerRef` trong `@EnableNeo4jRepositories` để sử dụng transaction manager dành cho Neo4j.

## 8. Đảm bảo client và transaction manager dùng cùng cấu hình

Một lỗi cấu hình thường gặp là `Neo4jClient` và `Neo4jTransactionManager` sử dụng các `Driver` hoặc `DatabaseSelectionProvider` khác nhau. Khi đó, một câu truy vấn có thể không tham gia transaction đang mở, hoặc truy vấn và transaction có thể nhắm tới database khác nhau.

Khi tự quản lý các bean thay thế (trong một cấu hình riêng, không khai báo trùng với bean kế thừa từ `AbstractNeo4jConfig`), hãy truyền cùng các dependency:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Neo4jClient neo4jClient(
        Driver driver,
        DatabaseSelectionProvider databaseSelectionProvider) {
    return Neo4jClient.create(driver, databaseSelectionProvider);
}

@Bean
public PlatformTransactionManager transactionManager(
        Driver driver,
        DatabaseSelectionProvider databaseSelectionProvider) {
    return new Neo4jTransactionManager(driver, databaseSelectionProvider);
}
```

Đoạn cấu hình này minh họa hai thành phần phải dùng cùng `Driver` và provider. Trong ứng dụng đã mở rộng `AbstractNeo4jConfig`, không cần khai báo lại hai bean này nếu không có yêu cầu tùy biến; cấu hình nền đã tạo chúng và truyền chung các dependency phù hợp. Nếu tự quản lý `Neo4jTemplate`, cần bảo đảm nó sử dụng `Neo4jClient` và `Neo4jMappingContext` tương ứng với cùng bộ hạ tầng.

Neo4j hỗ trợ nhiều database. Nếu một transaction đang nhắm tới database A, các thao tác client tham gia transaction đó cũng phải dùng cùng lựa chọn database. Không thay đổi database selection tùy tiện giữa chừng trong cùng một transaction.

## 9. Khi ứng dụng có nhiều nguồn dữ liệu

Một ứng dụng có thể vừa dùng Neo4j vừa dùng một cơ sở dữ liệu quan hệ. Mỗi loại tài nguyên cần transaction manager phù hợp. Ví dụ, `JpaTransactionManager` quản lý transaction JPA, còn `Neo4jTransactionManager` quản lý transaction Neo4j.

Việc đặt hai annotation hoặc gọi hai repository trong cùng một method không tự động tạo một distributed transaction bao trùm cả hai hệ thống. Neo4j Java Driver transaction do `Neo4jTransactionManager` quản lý là transaction native của Neo4j; không giả định rằng nó tự tham gia một XA/JTA transaction cùng database quan hệ. Nếu nghiệp vụ cần phối hợp nhiều nguồn dữ liệu, hãy thiết kế cơ chế điều phối phù hợp, thường là pattern outbox/saga với xử lý bù và retry. Một local transaction manager không thể rollback tài nguyên do manager khác kiểm soát.

Khi có nhiều transaction manager:

- Đặt tên bean rõ ràng và dùng `@Qualifier` khi inject.
- Chỉ định manager trong `@Transactional(transactionManager = "neo4jTransactionManager")` nếu bean Neo4j mang tên đó.
- Cấu hình `transactionManagerRef` của `@EnableNeo4jRepositories` khớp tên bean thực tế.
- Xác định ranh giới nhất quán dữ liệu giữa Neo4j và database quan hệ; cân nhắc phát sự kiện sau commit hoặc dùng outbox khi cần đồng bộ bất đồng bộ.

## 10. Kiểm tra cấu hình

Sau khi cấu hình, có thể kiểm tra application context và hành vi transaction bằng integration test với Neo4j test harness hoặc Testcontainers.

Các điểm cần xác minh:

1. Application context khởi động thành công và chỉ có một bean `Driver` được dùng cho bộ hạ tầng Neo4j dự kiến.
2. Có bean `Neo4jClient`, `Neo4jOperations`/`Neo4jTemplate` và `PlatformTransactionManager` triển khai bởi `Neo4jTransactionManager`.
3. Repository được phát hiện đúng package và sử dụng đúng `neo4jTemplateRef` cùng `transactionManagerRef`.
4. Một truy vấn `Neo4jClient` bind tham số thành công và trả về kiểu dữ liệu mong muốn.
5. `Neo4jTemplate.save(...)` và `findById(...)` ánh xạ entity đúng với mapping context.
6. Một service method `@Transactional` có thể kết hợp repository với `Neo4jClient` trong cùng transaction.
7. Khi cố ý phát sinh lỗi sau thao tác ghi trong transaction, dữ liệu được rollback theo mong đợi.
8. Khi application context đóng, driver được đóng đúng vòng đời.

Không chỉ kiểm tra bean tồn tại. Một cấu hình có thể khởi động thành công nhưng vẫn sai nếu repository tham chiếu nhầm template, client sử dụng database khác hoặc transaction manager không quản lý đúng driver.

## 11. Phạm vi imperative và reactive

Bài học này tập trung vào API imperative: `Neo4jClient`, `Neo4jTemplate` và `Neo4jTransactionManager`. Nếu ứng dụng sử dụng reactive stack, cần dùng các thành phần tương ứng như `ReactiveNeo4jClient`, `ReactiveNeo4jTemplate` và `ReactiveNeo4jTransactionManager`, đồng thời giữ transaction trong cùng reactive pipeline. Không trộn API imperative với reactive transaction manager trong một luồng xử lý và kỳ vọng chúng tự chia sẻ transaction.

## 12. Nguyên tắc cấu hình

- Dùng một `Driver` singleton dùng chung trong application context và đóng nó khi ứng dụng dừng.
- Để `AbstractNeo4jConfig` hoặc Spring Boot auto-configuration tạo client, template và transaction manager trong cấu hình thông thường.
- Dùng `Neo4jClient` khi cần Cypher tùy biến và ánh xạ record có chủ đích.
- Dùng `Neo4jTemplate` khi cần thao tác entity dựa trên mapping metadata mà không cần repository riêng.
- Dùng `Neo4jTransactionManager` thông qua `@Transactional` hoặc `TransactionTemplate` để quản lý transaction Neo4j.
- Giữ cùng `Driver` và `DatabaseSelectionProvider` giữa client và transaction manager.
- Khi có nhiều transaction manager, chỉ rõ bean được sử dụng ở service và repository.
- Không xem transaction Neo4j là distributed transaction bao trùm các hệ thống khác.

Khi ba thành phần được đăng ký đúng và dùng chung cấu hình kết nối, ứng dụng có thể phối hợp truy vấn Cypher, thao tác entity và transaction trong cùng một kiến trúc dữ liệu. Điều đó giúp tầng persistence giữ được ranh giới rõ ràng mà vẫn hỗ trợ cả repository, template và truy vấn tùy biến.

## Tài liệu tham khảo

- [Spring Data Neo4j – AbstractNeo4jConfig API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/config/AbstractNeo4jConfig.html)
- [Spring Data Neo4j – Neo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Data Neo4j – FAQ and configuration examples](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – EnableNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableNeo4jRepositories.html)
