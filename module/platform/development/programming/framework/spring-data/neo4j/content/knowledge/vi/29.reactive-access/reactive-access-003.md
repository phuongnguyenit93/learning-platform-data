# Cấu hình AbstractReactiveNeo4jConfig và @EnableReactiveNeo4jRepositories

Spring Data Neo4j (SDN) cung cấp hai mô hình truy cập dữ liệu: imperative và reactive. Ở mô hình reactive, repository trả về `Mono<T>` hoặc `Flux<T>`, client và template cũng phát hành Reactor publisher, còn transaction được quản lý bởi `ReactiveNeo4jTransactionManager`. Để các thành phần này hoạt động cùng nhau, ứng dụng cần cấu hình đúng Neo4j Driver, mapping context, reactive client, reactive template và cơ chế quét repository.

Khi không dùng Spring Boot, lớp `AbstractReactiveNeo4jConfig` gom phần lớn cấu hình nền tảng vào một Java configuration class. Annotation `@EnableReactiveNeo4jRepositories` kích hoạt việc phát hiện và tạo reactive repository. Hai thành phần có vai trò khác nhau: lớp cấu hình cung cấp hạ tầng truy cập Neo4j; annotation xác định nơi tìm repository và những bean hạ tầng mà repository sẽ sử dụng.

## 1. Các thành phần trong cấu hình reactive

Một cấu hình SDN reactive thường gồm các thành phần sau:

| Thành phần | Vai trò |
|---|---|
| `Driver` | Kết nối tới Neo4j qua Bolt; là đầu vào cho client và transaction manager |
| `ReactiveNeo4jClient` | Thực thi Cypher theo reactive API và tham gia reactive transaction của Spring |
| `Neo4jMappingContext` | Quản lý metadata của entity, node, relationship và mapping property |
| `Neo4jConversions` | Cung cấp các quy tắc chuyển đổi giữa kiểu Java và kiểu Neo4j |
| `ReactiveNeo4jTemplate` | API reactive mức thấp hơn repository để đọc, ghi và ánh xạ entity |
| `ReactiveNeo4jTransactionManager` | Kết nối transaction context của Spring với transaction của Neo4j Driver |
| `@EnableReactiveNeo4jRepositories` | Quét package và tạo proxy cho các reactive repository interface |

`AbstractReactiveNeo4jConfig` cung cấp các bean hạ tầng chính. Lớp con phải cung cấp `Driver` bằng cách override `driver()`. Các bean `ReactiveNeo4jClient`, `ReactiveNeo4jTemplate`, `Neo4jMappingContext` và reactive transaction manager được xây dựng dựa trên Driver và các cấu hình liên quan.

Không có kiểu `ReactiveDriver` riêng cần tạo cho SDN. Cấu hình vẫn trả về `org.neo4j.driver.Driver`; reactive client sử dụng API reactive của Neo4j Java Driver ở phía dưới.

## 2. Khi nào dùng AbstractReactiveNeo4jConfig?

`AbstractReactiveNeo4jConfig` là lớp cấu hình Java dành cho ứng dụng Spring sử dụng SDN reactive, đặc biệt khi không dùng Spring Boot auto-configuration. API này có từ Spring Data Neo4j 6.0 và giúp tránh phải tự tạo, kết nối thủ công từng bean của SDN.

Lớp cấu hình cung cấp các điểm mở rộng quan trọng:

- `driver()`: bắt buộc override để trả về Neo4j Java Driver.
- `getMappingBasePackages()`: chọn package chứa entity được ánh xạ; mặc định là package của lớp cấu hình cụ thể.
- `reactiveDatabaseSelectionProvider()`: chọn database; mặc định dùng database mặc định của Neo4j.
- `neo4jConversions()`: có thể override nếu ứng dụng cần custom conversion.
- `cypherDslConfiguration()`: có thể override khi cần cấu hình Cypher DSL.

Các bean như `reactiveNeo4jClient`, `reactiveNeo4jTemplate`, `neo4jMappingContext` và `reactiveTransactionManager` đã được cung cấp. Không cần tự khai báo lại nếu chỉ dùng cấu hình mặc định.

## 3. Cấu hình reactive tối thiểu không dùng Spring Boot

Giả sử entity nằm trong package `com.example.catalog.domain`, repository nằm trong `com.example.catalog.repository`. Có thể tạo lớp cấu hình như sau:

Entity dùng trong ví dụ:

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

    public Long getId() { return id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

Repository reactive:

```java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Flux;

public interface PersonRepository
        extends ReactiveNeo4jRepository<Person, Long> {

    Flux<Person> findByNameContaining(String text);
}
```

```java
import java.util.Collection;
import java.util.Collections;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.AbstractReactiveNeo4jConfig;
import org.springframework.data.neo4j.repository.config.EnableReactiveNeo4jRepositories;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import com.example.catalog.domain.Person;
import com.example.catalog.repository.PersonRepository;

@Configuration
@EnableReactiveNeo4jRepositories(
    basePackageClasses = PersonRepository.class
)
@EnableTransactionManagement
public class ReactiveNeo4jConfiguration extends AbstractReactiveNeo4jConfig {

    @Bean
    @Override
    public Driver driver() {
        return GraphDatabase.driver(
            "bolt://localhost:7687",
            AuthTokens.basic("neo4j", "replace-with-secret")
        );
    }

    @Override
    protected Collection<String> getMappingBasePackages() {
        return Collections.singletonList(
            Person.class.getPackage().getName()
        );
    }
}
```

Trong ví dụ:

1. `driver()` tạo Driver để SDN sử dụng. Đây là bean dùng chung trong application context; không tạo Driver mới cho từng request.
2. `@EnableReactiveNeo4jRepositories` kích hoạt reactive repository scanning tại package của `PersonRepository`.
3. `getMappingBasePackages()` chỉ rõ package chứa entity để SDN xây dựng mapping metadata.
4. `@EnableTransactionManagement` bật xử lý annotation transaction của Spring. `AbstractReactiveNeo4jConfig` cung cấp reactive transaction manager cho các thao tác Neo4j.

Đây là cấu hình minh họa. Trong ứng dụng thật, URI, username và password cần lấy từ cấu hình môi trường hoặc secret manager; không commit thông tin xác thực vào source code.

## 4. Phân biệt repository scanning và entity mapping scanning

Hai phạm vi quét có mục đích khác nhau:

- `@EnableReactiveNeo4jRepositories` tìm interface repository để tạo proxy.
- `getMappingBasePackages()` tìm entity được ánh xạ như các lớp có `@Node`.

Ví dụ, nếu repository ở `com.example.catalog.repository` còn entity ở `com.example.catalog.domain`, cấu hình cần bao phủ cả hai package theo đúng cơ chế:

```text
com.example.catalog
├── domain
│   ├── Person.java          (@Node)
│   └── Movie.java           (@Node)
└── repository
    ├── PersonRepository.java
    └── MovieRepository.java
```

Có thể dùng package cha chung cho mapping nếu các entity đều nằm dưới package đó:

```java
@Override
protected Collection<String> getMappingBasePackages() {
    return Collections.singletonList("com.example.catalog.domain");
}
```

Nếu entity nằm ở nhiều package không có package cha phù hợp, trả về danh sách các package cần quét. Không giả định rằng việc quét repository tự động bao phủ mọi package entity.

## 5. Chỉ định package cho @EnableReactiveNeo4jRepositories

`@EnableReactiveNeo4jRepositories` có từ Spring Data Neo4j 6.0 và hỗ trợ nhiều cách chọn package:

### basePackages

```java
@EnableReactiveNeo4jRepositories(
    basePackages = {
        "com.example.catalog.repository",
        "com.example.identity.repository"
    }
)
```

Đây là cách khai báo package dưới dạng chuỗi. Khi refactor hoặc đổi tên package, chuỗi không được compiler kiểm tra nên cần chú ý cập nhật.

### basePackageClasses

```java
@EnableReactiveNeo4jRepositories(
    basePackageClasses = {
        PersonRepository.class,
        AccountRepository.class
    }
)
```

Đây là cách type-safe. Spring quét package chứa mỗi class được chỉ định. Có thể dùng một marker interface hoặc class rỗng chuyên để đánh dấu package nếu không muốn phụ thuộc vào repository cụ thể.

### Không khai báo package

```java
@EnableReactiveNeo4jRepositories
```

Nếu không truyền `value`, `basePackages` hoặc `basePackageClasses`, Spring quét package của lớp cấu hình được đánh dấu. Cách này thuận tiện khi repository interface nằm cùng package hoặc package con của configuration class.

`value` là alias của `basePackages`. Chỉ chọn một trong `value` hoặc `basePackages`; dùng `basePackageClasses` nếu muốn chỉ định package theo kiểu Java.

## 6. Các thuộc tính quan trọng của @EnableReactiveNeo4jRepositories

Ngoài package scanning, annotation cho phép chỉ định các bean mà repository được tạo ra sẽ sử dụng:

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---|---|
| `neo4jTemplateRef` | `reactiveNeo4jTemplate` | Tên bean `ReactiveNeo4jTemplate` |
| `neo4jMappingContextRef` | `neo4jMappingContext` | Tên bean `Neo4jMappingContext` |
| `transactionManagerRef` | `reactiveTransactionManager` | Tên bean reactive transaction manager |
| `repositoryFactoryBeanClass` | `ReactiveNeo4jRepositoryFactoryBean` | Factory tạo repository proxy |
| `repositoryBaseClass` | `DefaultRepositoryBaseClass` | Lớp nền tùy chỉnh cho repository proxy |
| `repositoryImplementationPostfix` | `Impl` | Hậu tố tìm custom repository implementation |
| `considerNestedRepositories` | `false` | Có quét repository interface lồng bên trong class hay không |
| `includeFilters`, `excludeFilters` | Rỗng | Bộ lọc repository interface được quét hoặc loại trừ |
| `namedQueriesLocation` | Theo mặc định của SDN | Vị trí file named queries |

Thông thường không cần đổi các tham chiếu bean mặc định khi dùng `AbstractReactiveNeo4jConfig`. Chỉ cấu hình `neo4jTemplateRef`, `neo4jMappingContextRef` hoặc `transactionManagerRef` khi ứng dụng có nhiều bộ hạ tầng Neo4j hoặc tự đặt tên bean khác.

Ví dụ dùng transaction manager có tên riêng:

```java
@EnableReactiveNeo4jRepositories(
    basePackageClasses = PersonRepository.class,
    transactionManagerRef = "catalogReactiveTransactionManager"
)
```

Khi đổi tên bean, bảo đảm bean được tham chiếu có đúng kiểu reactive tương ứng. Không trỏ repository reactive tới `Neo4jTransactionManager` imperative.

## 7. Reactive database selection

`AbstractReactiveNeo4jConfig` cung cấp `ReactiveDatabaseSelectionProvider`. Mặc định, provider để Neo4j chọn database mặc định. Nếu ứng dụng sử dụng một database cụ thể, override bean này:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;

@Bean
@Override
protected ReactiveDatabaseSelectionProvider reactiveDatabaseSelectionProvider() {
    return ReactiveDatabaseSelectionProvider
        .createStaticDatabaseSelectionProvider("catalog");
}
```

Provider reactive trả về `Mono<DatabaseSelection>`. Nếu muốn chọn database theo tenant hoặc theo ngữ cảnh request, có thể triển khai provider trả về lựa chọn database bất đồng bộ. Không gọi `block()` để lấy database name bên trong provider.

Khi cấu hình client và transaction manager thủ công, hãy dùng cùng một `ReactiveDatabaseSelectionProvider` cho cả hai. `AbstractReactiveNeo4jConfig` đã nối provider vào `ReactiveNeo4jClient` và `ReactiveNeo4jTransactionManager` theo cách này.

Database phải được tạo và cấp quyền trước. SDN chỉ chọn database để truy vấn; nó không tự tạo database mới.

## 8. Repository reactive phải dùng đúng interface

Sau khi bật `@EnableReactiveNeo4jRepositories`, repository interface cần kế thừa `ReactiveNeo4jRepository`:

```java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Flux;

public interface PersonRepository
        extends ReactiveNeo4jRepository<Person, Long> {

    Flux<Person> findByNameContaining(String text);
}
```

Các phương thức CRUD reactive trả về `Mono` hoặc `Flux`. Không dùng `Neo4jRepository` imperative nếu muốn repository hoạt động theo reactive API.

Một service có thể tiếp tục composition trên publisher:

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class PersonService {
    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    public Mono<Person> findById(Long id) {
        return repository.findById(id);
    }
}
```

Không gọi `.block()` hoặc `.subscribe()` trong repository/service chỉ để ép luồng reactive thành imperative. Hãy trả `Mono` hoặc `Flux` cho controller WebFlux hoặc thành phần ở biên ứng dụng để tiếp tục xử lý và quản lý subscription.

## 9. Cấu hình reactive transaction

`AbstractReactiveNeo4jConfig` cung cấp bean `reactiveTransactionManager`. Khi bật `@EnableTransactionManagement`, method service có thể dùng `@Transactional` với reactive return type:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonRegistrationService {
    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonRegistrationService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Person> register(Person person) {
        return personRepository.save(person)
            .flatMap(saved -> auditRepository.recordCreated(saved.getId())
                .thenReturn(saved));
    }
}
```

Ví dụ giả định `AuditRepository.recordCreated(...)` cũng trả về publisher reactive và dùng cùng reactive transaction manager. Các thao tác trong cùng Reactor chain có thể tham gia cùng transaction. Transaction reactive gắn với Reactor Context, không dựa trên thread-local như transaction imperative.

Với reactive transaction, công việc thực sự được thực thi khi publisher được subscribe. Spring quản lý transaction trong quá trình subscription của `Mono` hoặc `Flux` được method trả về. Vì vậy, method được proxy quản lý cần trả publisher để Spring giữ transaction cho toàn bộ quá trình thực thi.

Contract tối thiểu của thành phần ghi audit trong ví dụ:

```java
import reactor.core.publisher.Mono;

public interface AuditRepository {
    Mono<Void> recordCreated(Long personId);
}
```

Không tách một phần công việc ra ngoài chain bằng `subscribe()` rồi mong nó vẫn nằm trong transaction của method. Nếu một publisher không được nối vào chuỗi được trả về, Spring không thể bảo đảm nó được hoàn tất trong cùng ranh giới transaction.

## 10. Dùng Spring Boot hay AbstractReactiveNeo4jConfig?

Hai cách cấu hình phục vụ những môi trường khác nhau:

| Môi trường | Cách cấu hình |
|---|---|
| Spring context không dùng Boot | Kế thừa `AbstractReactiveNeo4jConfig`, override `driver()` và bật `@EnableReactiveNeo4jRepositories` |
| Spring Boot với `spring-boot-starter-data-neo4j` và Project Reactor | Dùng auto-configuration; reactive style được phát hiện khi Reactor có trên classpath và mặc định quét các auto-configuration packages |
| Spring Boot cần đổi package repository | Dùng `@EnableReactiveNeo4jRepositories` với `basePackages` hoặc `basePackageClasses` theo nhu cầu |
| Spring Boot cần reactive transaction | Khai báo `ReactiveNeo4jTransactionManager` bean nếu chưa có; Boot không tự auto-config reactive transaction manager |

Trong Spring Boot, Driver thường được cấu hình từ `spring.neo4j.*` properties. Khi tự khai báo `Driver` hoặc `AbstractReactiveNeo4jConfig`, cần hiểu rằng bean tự định nghĩa có thể thay thế hoặc xung đột với bean auto-configured. Không vừa dùng toàn bộ `AbstractReactiveNeo4jConfig` vừa khai báo lại client/template/transaction manager cùng tên mà không có lý do rõ ràng.

Ví dụ bổ sung reactive transaction manager trong Spring Boot:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveTransactionConfiguration {

    @Bean
    public ReactiveNeo4jTransactionManager reactiveTransactionManager(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider) {
        return new ReactiveNeo4jTransactionManager(
            driver,
            databaseSelectionProvider
        );
    }
}
```

Nếu ứng dụng chỉ dùng repository reactive nhưng không cần transaction nhiều thao tác, các thao tác repository riêng lẻ vẫn có thể thực thi theo cơ chế của chúng. Khi cần `@Transactional` bao quanh nhiều thao tác reactive, phải có reactive transaction manager tương ứng.

## 11. Tách cấu hình imperative và reactive

SDN có hai bộ repository infrastructure:

- `@EnableNeo4jRepositories` tạo repository imperative, thường kế thừa `Neo4jRepository` và trả về entity hoặc collection thông thường.
- `@EnableReactiveNeo4jRepositories` tạo repository reactive, thường kế thừa `ReactiveNeo4jRepository` và trả về `Mono`/`Flux`.

Hai kiểu repository có factory và transaction manager khác nhau. Nếu một ứng dụng cố ý hỗ trợ cả hai, nên phân tách package để mỗi annotation quét đúng interface của nó. Tránh để hai cấu hình quét trùng repository package vì có thể gây đăng ký bean không mong muốn hoặc repository được tạo bởi infrastructure không phù hợp.

Ví dụ tổ chức package:

```text
com.example.catalog
├── domain
│   └── Person.java
├── repository
│   ├── imperative
│   │   └── PersonRepository.java
│   └── reactive
│       └── ReactivePersonRepository.java
└── config
    ├── ImperativeNeo4jConfiguration.java
    └── ReactiveNeo4jConfiguration.java
```

Nếu ứng dụng chỉ dùng reactive, không cần bật imperative repository infrastructure. Tránh trộn lời gọi imperative và reactive trong cùng một luồng request chỉ vì cả hai cùng dùng Neo4j Driver.

## 12. Mapping context và custom conversion

`AbstractReactiveNeo4jConfig` tạo `Neo4jMappingContext` dựa trên `Neo4jConversions`. Mapping context dùng package mapping để tìm các entity và xây dựng metadata cho node/relationship.

Nếu ứng dụng cần converter tùy chỉnh, có thể override `neo4jConversions()` hoặc đăng ký theo cơ chế conversion của SDN. Hãy bảo đảm custom converter được sử dụng thống nhất bởi reactive client, template và repository thông qua mapping context tương ứng.

Khi có nhiều `Neo4jMappingContext` hoặc `ReactiveNeo4jTemplate`, có thể chỉ định bean phù hợp bằng `neo4jMappingContextRef` và `neo4jTemplateRef` trong `@EnableReactiveNeo4jRepositories`. Việc này hữu ích khi một application context truy cập nhiều graph hoặc dùng nhiều cấu hình mapping độc lập.

## 13. Vòng đời Driver và cấu hình kết nối

`Driver` là đối tượng hạ tầng dùng chung, được tạo một lần trong Spring application context. Không tạo Driver trong mỗi repository method hoặc mỗi lần subscribe vào `Mono`/`Flux`.

Khi tạo Driver thủ công:

- Dùng URI Bolt đúng môi trường, ví dụ `bolt://localhost:7687` cho kết nối local.
- Dùng `neo4j+s://` hoặc scheme phù hợp khi kết nối môi trường yêu cầu TLS.
- Đặt username/password trong secret hoặc biến môi trường.
- Cấu hình connection pool, timeout và trust theo yêu cầu triển khai.
- Để Spring quản lý bean lifecycle và đóng Driver khi application context dừng.

Khi dùng Spring Boot, có thể để auto-configuration tạo Driver và đặt URI/credential trong `spring.neo4j.*`. Không tạo thêm Driver thứ hai nếu không có nhu cầu tách cluster hoặc cấu hình kết nối.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có reactive repository bean | Thiếu `@EnableReactiveNeo4jRepositories` hoặc package scan sai | Chọn `basePackages`/`basePackageClasses` đúng package |
| Repository interface không được tạo proxy | Interface kế thừa `Neo4jRepository` thay vì `ReactiveNeo4jRepository` | Dùng reactive repository base interface |
| Không tìm thấy entity mapping | `getMappingBasePackages()` không bao phủ package có `@Node` | Bổ sung package entity vào mapping base packages |
| Không inject được `ReactiveNeo4jTemplate` | Chưa dùng `AbstractReactiveNeo4jConfig` hoặc thiếu bean tương ứng | Kiểm tra cấu hình reactive và tên bean `reactiveNeo4jTemplate` |
| `@Transactional` không tạo reactive transaction | Thiếu `ReactiveNeo4jTransactionManager` hoặc annotation transaction management | Cấu hình reactive manager và bật transaction management phù hợp |
| Repository dùng nhầm transaction manager | `transactionManagerRef` trỏ tới bean imperative | Trỏ tới `ReactiveNeo4jTransactionManager` |
| Query chạy trên database mặc định thay vì database mong muốn | Chưa cấu hình `ReactiveDatabaseSelectionProvider` | Override provider và dùng chung với reactive transaction manager |
| Có nhiều bean Driver hoặc template gây xung đột | Kết hợp Boot auto-configuration với cấu hình thủ công không nhất quán | Chọn một hướng cấu hình và đặt tên/refs rõ ràng |
| Reactive flow không chạy | Publisher chưa được subscribe ở biên ứng dụng | Trả `Mono`/`Flux` cho WebFlux hoặc consumer phù hợp |
| Transaction kết thúc trước khi thao tác hoàn tất | Gọi `subscribe()` nội bộ hoặc tách publisher khỏi chain | Nối toàn bộ thao tác vào publisher được trả về |
| Thread bị chặn trong WebFlux | Gọi `.block()` hoặc API imperative trên event-loop | Dùng reactive repository/client/template xuyên suốt |

## 15. Quy trình cấu hình

1. Xác định ứng dụng dùng Spring Boot hay Spring context thuần.
2. Nếu không dùng Boot, tạo class kế thừa `AbstractReactiveNeo4jConfig`.
3. Override `driver()` và tạo một Driver bean dùng chung.
4. Chọn package entity qua `getMappingBasePackages()`.
5. Dùng `@EnableReactiveNeo4jRepositories` để chỉ định package repository.
6. Nếu cần database cụ thể, cấu hình `ReactiveDatabaseSelectionProvider`.
7. Dùng `ReactiveNeo4jRepository` cho repository reactive.
8. Bảo đảm `ReactiveNeo4jTransactionManager` được cấu hình nếu dùng `@Transactional` reactive.
9. Kiểm tra bean `ReactiveNeo4jClient`, `ReactiveNeo4jTemplate`, mapping context và repository được tạo đúng.
10. Viết integration test xác nhận truy vấn reactive, mapping và transaction hoạt động.

## 16. Tự kiểm tra

1. `AbstractReactiveNeo4jConfig` cung cấp những bean hạ tầng SDN reactive nào?
2. Vì sao lớp cấu hình phải override `driver()`?
3. Khác biệt giữa `getMappingBasePackages()` và `@EnableReactiveNeo4jRepositories(basePackages = ...)` là gì?
4. Khi không truyền package vào `@EnableReactiveNeo4jRepositories`, Spring sẽ quét ở đâu?
5. Vì sao `basePackageClasses` thường an toàn hơn tên package dạng chuỗi?
6. `neo4jTemplateRef` và `transactionManagerRef` dùng để làm gì?
7. Khi nào cần override `reactiveDatabaseSelectionProvider()`?
8. Vì sao repository reactive phải kế thừa `ReactiveNeo4jRepository`?
9. Spring Boot có tự cấu hình `ReactiveNeo4jTransactionManager` không?
10. Vì sao không nên để imperative và reactive repository infrastructure quét cùng một package khi không có chủ đích?

## Tài liệu tham khảo

- [Spring Data Neo4j — FAQ: Reactive infrastructure configuration](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — AbstractReactiveNeo4jConfig API](https://docs.spring.io/spring-data/data-neo4j/reference/api/java/org/springframework/data/neo4j/config/AbstractReactiveNeo4jConfig.html)
- [Spring Data Neo4j — EnableReactiveNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableReactiveNeo4jRepositories.html)
- [Spring Data Neo4j — ReactiveDatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveDatabaseSelectionProvider.html)
- [Spring Boot — Working with Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html)
