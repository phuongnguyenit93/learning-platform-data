# @DataNeo4jTest và phạm vi cấu hình được nạp

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích `@DataNeo4jTest` là một test slice chuyên cho Spring Data Neo4j (SDN).
- Biết những auto-configuration, entity, repository và bean nào được nạp mặc định.
- Phân biệt cấu hình Neo4j được tự động tạo với database Neo4j mà test phải tự cung cấp.
- Bổ sung service, converter, test bean và `@ConfigurationProperties` khi test cần chúng.
- Chọn giữa `@DataNeo4jTest` và `@SpringBootTest` theo phạm vi cần kiểm thử.
- Cấu hình test với Neo4j Testcontainers hoặc test harness.
- Hiểu transaction rollback mặc định và giới hạn khi kiểm thử reactive repository.

## 1. @DataNeo4jTest dùng để làm gì?

`@DataNeo4jTest` là annotation kiểm thử theo lát cắt (test slice) của Spring Boot dành cho các thành phần truy cập Neo4j. Nó tạo một Spring `ApplicationContext` đã được giới hạn vào phần data access cần thiết để kiểm tra mapping, repository và truy vấn.

Một bài test thường cần các thành phần:

- Entity được ánh xạ bằng `@Node` và `@RelationshipProperties`.
- Spring Data Neo4j repositories.
- `Neo4jClient` để chạy Cypher trực tiếp.
- `Neo4jTemplate` hoặc `ReactiveNeo4jTemplate`.
- Driver và transaction infrastructure tương ứng.

`@DataNeo4jTest` giúp Spring Boot tự cấu hình các thành phần Neo4j liên quan, đồng thời giới hạn component scanning để test khởi động nhanh và tập trung vào data layer.

Ví dụ tối thiểu:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;

@DataNeo4jTest
class MovieRepositoryTest {

    @Autowired
    MovieRepository movieRepository;

}
```

Với JUnit Jupiter, không cần thêm `@ExtendWith(SpringExtension.class)` vì annotation đã tích hợp Spring Test extension. Với JUnit 4, cần dùng `@RunWith(SpringRunner.class)`.

## 2. Chú ý package annotation theo Spring Boot version

Package của `@DataNeo4jTest` đã thay đổi trong quá trình modularization của Spring Boot 4. Cần import đúng package theo phiên bản Boot của dự án.

| Spring Boot | Package của annotation | Module chứa annotation |
| --- | --- | --- |
| Boot 3.x | `org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest` | `spring-boot-test-autoconfigure`, thường được kéo vào qua `spring-boot-starter-test` |
| Boot 4.x | `org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest` | `spring-boot-data-neo4j-test` |

Ví dụ dependency test với Spring Boot 3:

```gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Với Spring Boot 4, thêm module test Neo4j cùng các thư viện test thông thường:

```gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-data-neo4j-test")
}
```

Các ví dụ Java trong bài dùng package Boot 4 để thống nhất với cấu trúc module hiện tại. Nếu dự án dùng Boot 3, thay import `org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest` bằng `org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest`. Các phiên bản Spring Boot nên được quản lý đồng bộ bằng Spring Boot dependency management hoặc BOM.

## 3. Những cấu hình nào được nạp?

`@DataNeo4jTest` tìm cấu hình ứng dụng chính (`@SpringBootConfiguration`, thường là class có `@SpringBootApplication`) theo package của test rồi áp dụng bộ lọc test slice. Nó chỉ bật auto-configuration phù hợp với kiểm thử Neo4j.

Nhóm hạ tầng chính gồm:

| Thành phần | Vai trò |
| --- | --- |
| Neo4j Driver auto-configuration | Tạo Driver từ connection details hoặc `spring.neo4j.*` properties |
| SDN data auto-configuration | Tạo mapping context, conversions, client và template |
| Repository auto-configuration | Phát hiện và đăng ký Neo4j repositories |
| Reactive Neo4j auto-configuration | Cung cấp reactive client/template/repository khi reactive dependencies phù hợp hiện diện |
| Transaction auto-configuration | Cấu hình transaction infrastructure liên quan |
| Test service connection integration (nếu có module) | Nhận connection details từ Testcontainers `@ServiceConnection` |

Danh sách class auto-configuration cụ thể có khác biệt giữa Boot 3 và Boot 4 do tên package và cấu trúc module thay đổi. Ví dụ, Boot 3.5 sử dụng các lớp như `Neo4jAutoConfiguration`, `Neo4jDataAutoConfiguration`, `Neo4jRepositoriesAutoConfiguration` và các reactive variant. Boot 4 chuyển chúng sang các package `org.springframework.boot.neo4j.autoconfigure` và `org.springframework.boot.data.neo4j.autoconfigure`.

Điều quan trọng là hiểu nhóm chức năng được bật, thay vì phụ thuộc vào tên class nội bộ của một phiên bản Boot cụ thể.

## 4. Component scanning được giới hạn ra sao?

Mặc định, test slice quét các thành phần thuộc Neo4j data layer:

- Node entity có `@Node`.
- Relationship properties có `@RelationshipProperties`.
- Các interface repository được SDN hỗ trợ và nằm trong phạm vi package scan.
- Những cấu hình auto-configuration liên quan đến Neo4j.

Các bean ứng dụng thông thường như `@Component`, `@Service`, `@Controller` và các class `@ConfigurationProperties` không được component scan như trong ứng dụng đầy đủ.

Ví dụ:

```java
@Service
public class MovieService {

    private final MovieRepository movieRepository;

    public MovieService(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }
}
```

Nếu chỉ dùng `@DataNeo4jTest`, `MovieService` không tự động xuất hiện trong context chỉ vì nó có `@Service`. Repository mà service phụ thuộc vẫn được tạo, nhưng service cần được import rõ ràng nếu test muốn kiểm tra nó.

Tương tự, một bean cấu hình riêng:

```java
@Configuration
public class MovieSearchConfiguration {
    // Các bean cấu hình cho ứng dụng
}
```

không nên được kỳ vọng sẽ tự động nạp toàn bộ như khi dùng `@SpringBootTest`. Hãy bổ sung đúng cấu hình cần thiết bằng `@Import` hoặc `@TestConfiguration`.

## 5. Bổ sung service và cấu hình cần thiết bằng @Import

Nếu muốn kiểm thử service cùng repository trong phạm vi slice, có thể import service trực tiếp:

```java
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
import org.springframework.context.annotation.Import;

@DataNeo4jTest
@Import(MovieService.class)
class MovieServiceTest {

    @Autowired
    MovieService movieService;

    @Autowired
    MovieRepository movieRepository;

}
```

`@Import` đưa đúng class cần thiết vào test context. Các dependency constructor của service, chẳng hạn repository đã được slice tạo, sẽ được inject bình thường.

Nếu cần bean chỉ dùng trong test, có thể khai báo `@TestConfiguration`:

```java
import java.time.Clock;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class MovieTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}
```

Sau đó import cấu hình:

```java
@DataNeo4jTest
@Import({
    MovieService.class,
    MovieTestConfiguration.class
})
class MovieServiceTest {
    // Tests
}
```

Cách này giúp test context có service và test bean cần thiết mà không phải bật toàn bộ component scan của ứng dụng.

## 6. Bổ sung @ConfigurationProperties

Nếu service hoặc converter cần một class cấu hình có `@ConfigurationProperties`, hãy đăng ký class đó bằng `@EnableConfigurationProperties`:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.movie")
public record MovieProperties(
    int maximumRecommendations,
    boolean includeUnreleased
) {
}
```

Trong test:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;

@DataNeo4jTest(properties = {
    "app.movie.maximum-recommendations=5",
    "app.movie.include-unreleased=false"
})
@EnableConfigurationProperties(MovieProperties.class)
class MovieRepositoryTest {

    @Autowired
    MovieProperties movieProperties;

}
```

`@EnableConfigurationProperties` đăng ký class properties cụ thể. Nếu không khai báo, không nên giả định `@ConfigurationProperties` sẽ được phát hiện tự động trong test slice.

Có thể dùng thuộc tính `properties` của `@DataNeo4jTest` để thêm giá trị vào Spring Environment của riêng test. Với bộ cấu hình dài hoặc dùng chung, có thể đặt trong file `application-test.properties` và kích hoạt profile test nếu cấu trúc ứng dụng yêu cầu.

## 7. Điều chỉnh phạm vi bằng các thuộc tính của annotation

Ngoài `properties`, annotation có một số thuộc tính để tinh chỉnh test slice:

| Thuộc tính | Mục đích |
| --- | --- |
| `includeFilters` | Thêm các loại bean vốn bị bộ lọc slice loại khỏi component scan |
| `excludeFilters` | Loại thêm bean khỏi phạm vi scan |
| `useDefaultFilters` | Điều khiển việc dùng bộ lọc mặc định của component scanning |
| `excludeAutoConfiguration` | Loại một hoặc nhiều auto-configuration khỏi test |
| `properties` | Thêm property trực tiếp vào Environment của test |

Có thể dùng `excludeAutoConfiguration` để loại một auto-configuration cụ thể theo class thực tế của phiên bản Boot đang dùng. Chỉ làm vậy khi biết rõ bean nào không cần và không làm mất hạ tầng mà repository đang phụ thuộc. Nếu test thiếu bean do component scan bị giới hạn, ưu tiên `@Import` hoặc `@EnableConfigurationProperties` trước khi thay đổi bộ lọc toàn cục.

## 8. @DataNeo4jTest không tạo Neo4j database

Một điểm rất dễ nhầm: test slice tạo Spring infrastructure, nhưng **không tự khởi động hoặc provision Neo4j database** và không tự tạo URI, username hay password kết nối.

Ứng dụng vẫn cần một database có thể kết nối được. Có thể chọn:

- Neo4j Testcontainers: chạy Neo4j trong Docker, phù hợp với integration test gần môi trường thật.
- Neo4j test harness: khởi chạy Neo4j embedded trong cùng JVM, tiện cho kiểm thử một số extension hoặc procedure; hiệu năng và timing không đại diện chính xác cho server production.
- Một Neo4j server test đã được cấp sẵn: cấu hình URI và credential riêng cho môi trường test.

Không trỏ test vào database phát triển hoặc production dùng chung. Các test ghi dữ liệu có thể tạo, cập nhật hoặc xóa node và relationship.

### 8.1. Cấu hình bằng Spring Boot Service Connection và Testcontainers

Với Spring Boot hỗ trợ `@ServiceConnection`, có thể để Boot lấy connection details từ Neo4j container. Cần thêm module Testcontainers của Spring Boot và module Neo4j của Testcontainers.

Ví dụ với Testcontainers 2.x và Spring-managed container:

```gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-neo4j")
}
```

Ví dụ test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.testcontainers.neo4j.Neo4jContainer;

@DataNeo4jTest
@Import(MovieRepositoryTest.Neo4jContainerConfiguration.class)
class MovieRepositoryTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class Neo4jContainerConfiguration {

        @Bean
        @ServiceConnection
        Neo4jContainer neo4jContainer() {
            return new Neo4jContainer("neo4j:5")
                .withAdminPassword("test-password");
        }
    }

    @Autowired
    MovieRepository movieRepository;

    @Test
    void savesAndFindsMovie() {
        Movie saved = movieRepository.save(
            new Movie("Dune")
        );

        assertThat(movieRepository.findById(saved.getId()))
            .isPresent()
            .get()
            .extracting(Movie::getTitle)
            .isEqualTo("Dune");
    }
}
```

`@ServiceConnection` tạo connection details mà Neo4j auto-configuration có thể sử dụng. Vì container được khai báo như Spring bean, Spring quản lý việc khởi động và dừng container cùng ApplicationContext; điều này phù hợp với cơ chế cache context giữa nhiều test class. Test không cần tự ghi URI và password vào property nếu connection factory nhận được service connection đó.

Package của `Neo4jContainer` phụ thuộc major version Testcontainers. Ví dụ trên dùng Testcontainers 2.x; Testcontainers 1.x dùng package cũ `org.testcontainers.containers.Neo4jContainer` và artifact tương ứng. Hãy giữ các module Testcontainers cùng major version.

### 8.2. Cấu hình bằng DynamicPropertySource

Nếu không dùng `@ServiceConnection`, có thể đăng ký connection properties động:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void neo4jProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
    registry.add("spring.neo4j.authentication.username", () -> "neo4j");
    registry.add(
        "spring.neo4j.authentication.password",
        neo4j::getAdminPassword
    );
}
```

Các property được thêm trước khi Spring tạo Driver. Tên property phải khớp cấu hình Spring Boot đang dùng. Nếu test dùng một database có tên riêng, có thể bổ sung `spring.neo4j.database`.

Nếu quản lý container bằng JUnit Testcontainers extension, hãy chú ý vòng đời container và việc Spring cache ApplicationContext giữa các test class. Không để context được tái sử dụng giữ Driver trỏ tới container đã bị dừng. Có thể quản lý container theo vòng đời Spring context hoặc cấu hình test context phù hợp.

## 9. Ví dụ entity, repository và test slice

Entity đơn giản:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    protected Movie() {
    }

    public Movie(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Repository:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository
        extends Neo4jRepository<Movie, Long> {

    Optional<Movie> findByTitle(String title);
}
```

Test slice:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;

@DataNeo4jTest
class MovieRepositoryTest {

    @Autowired
    MovieRepository movieRepository;

    @Test
    void savesAndFindsMovieByTitle() {
        movieRepository.save(new Movie("Dune"));

        assertThat(movieRepository.findByTitle("Dune"))
            .isPresent()
            .get()
            .extracting(Movie::getTitle)
            .isEqualTo("Dune");
    }
}
```

Test này kiểm tra mapping entity, lưu node và derived query trên database thật. Trong ví dụ thực tế, thêm Testcontainers, test harness hoặc cấu hình Neo4j test server trước khi chạy.

Dùng `@GeneratedValue` trong ví dụ để SDN quản lý ID. Nếu entity dùng business ID do ứng dụng gán, cần thiết kế `@Version` theo quy tắc optimistic locking của SDN; không bỏ qua yêu cầu version chỉ để làm ví dụ test ngắn hơn.

## 10. Các bean có thể inject trong test slice

Các bean phổ biến mà test Neo4j có thể sử dụng:

| Bean | Khi nào dùng |
| --- | --- |
| Repository interface | Kiểm tra CRUD, derived query, custom `@Query` |
| `Neo4jClient` | Chạy Cypher trực tiếp và kiểm tra kết quả thấp hơn tầng repository |
| `Neo4jTemplate` | Kiểm tra mapping và thao tác entity qua template |
| `Neo4jMappingContext` | Kiểm tra metadata entity hoặc cấu hình mapping chuyên biệt |
| `Neo4jTransactionManager` | Kiểm tra transaction imperative |
| Reactive client/template/repository | Kiểm thử reactive data access nếu dependencies và auto-configuration phù hợp |

Không cần tự khai báo các bean này nếu auto-configuration đã cung cấp chúng. Nếu một bean không được tạo, kiểm tra dependency trên classpath, property kết nối, package scan và các điều kiện của auto-configuration trước khi thêm bean thủ công.

## 11. Transaction mặc định của @DataNeo4jTest

`@DataNeo4jTest` có `@Transactional` ở cấp annotation. Với imperative test, mỗi test method chạy trong test-managed transaction và mặc định rollback khi kết thúc.

Điều này giúp test độc lập:

1. Test tạo node và relationship.
2. Repository đọc lại dữ liệu trong cùng transaction.
3. Assertion kiểm tra kết quả.
4. Spring rollback transaction sau test.
5. Test kế tiếp không nhìn thấy thay đổi đã rollback.

Không cần xóa dữ liệu trong `@AfterEach` nếu toàn bộ thao tác ghi tham gia đúng test transaction. Tuy nhiên, nếu test dùng Driver/session riêng, transaction thủ công hoặc gọi tới hệ thống ngoài transaction manager, thay đổi có thể không rollback cùng test transaction.

Có thể tắt transaction mặc định cho test cần xác minh commit thật hoặc chạy quy trình nhiều transaction:

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@DataNeo4jTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalMovieRepositoryTest {
}
```

Khi đã tắt test transaction, test cần tự quản lý dữ liệu: dùng database/container riêng, dọn dữ liệu theo khóa test hoặc tạo database mới cho từng nhóm test. Không dựa vào rollback mặc định nữa.

## 12. Lưu ý riêng khi kiểm thử reactive access

SDN có imperative và reactive programming model. Tuy nhiên, transaction test được áp dụng ngầm bởi `@DataNeo4jTest` là imperative transaction. Nó không tự bao bọc publisher reactive để rollback các thao tác reactive.

Với reactive repository:

- Không giả định `@Transactional` ở cấp test sẽ rollback các thao tác reactive.
- Tắt imperative test transaction bằng `@Transactional(propagation = Propagation.NOT_SUPPORTED)`.
- Nếu cần xác minh reactive transaction, dùng `TransactionalOperator` hoặc service reactive có `@Transactional` với return type `Mono`/`Flux` và reactive transaction manager đúng.
- Kiểm tra context có `ReactiveNeo4jTransactionManager` hay chưa. Không giả định chỉ cần có reactive repository là reactive transaction manager cũng tự động được tạo; nếu thiếu, khai báo bean này và tạo `TransactionalOperator` từ nó.
- Subscribe publisher trong test bằng `StepVerifier`; không gọi `block()` để thay thế kiểm thử reactive pipeline.

Ví dụ test không có imperative test transaction:

```java
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@DataNeo4jTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ReactiveMovieRepositoryTest {
    // Inject reactive repository and verify with StepVerifier.
}
```

Nếu test cần kiểm tra một nhóm thao tác reactive cùng rollback, có thể dùng `TransactionalOperator`:

Ví dụ sau giả định test đã inject `reactiveMovieRepository` và `transactionalOperator`, đồng thời có một `movie` chưa được lưu:

```java
import reactor.core.publisher.Mono;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.test.StepVerifier;

Mono<Void> work = reactiveMovieRepository.save(movie)
    .then(Mono.error(new IllegalStateException("force rollback")));

StepVerifier.create(transactionalOperator.transactional(work))
    .expectError(IllegalStateException.class)
    .verify();
```

Sau khi publisher kết thúc, dùng reactive repository đọc lại dữ liệu để xác nhận transaction đã rollback. Test phải được cấu hình reactive transaction manager phù hợp; không dùng imperative `Neo4jTransactionManager` để thay thế.

## 13. Khi nào cần @SpringBootTest thay cho @DataNeo4jTest?

Chọn annotation theo phạm vi muốn xác minh:

| Nhu cầu | Annotation phù hợp |
| --- | --- |
| Mapping node/relationship, repository CRUD và query | `@DataNeo4jTest` |
| Repository kết hợp với `Neo4jClient` hoặc template | `@DataNeo4jTest` |
| Service nghiệp vụ có thể import riêng vào test slice | `@DataNeo4jTest` + `@Import` |
| Controller, security, web filter và HTTP endpoint | `@SpringBootTest` hoặc `@WebMvcTest`/`@WebFluxTest` kết hợp cấu hình phù hợp |
| Kiểm tra toàn bộ application context và wiring giữa nhiều module | `@SpringBootTest` |
| Kiểm tra cấu hình production gần như nguyên vẹn cùng database thật | `@SpringBootTest` + Testcontainers |

`@SpringBootTest` tạo context rộng hơn, thường bao gồm component scan của ứng dụng và các auto-configuration liên quan đến toàn bộ application. Nó phù hợp với integration test ở cấp ứng dụng nhưng thời gian khởi động và số dependency cần chuẩn bị thường lớn hơn.

Nếu chỉ cần kiểm tra repository, dùng full context có thể làm test chậm và khiến lỗi của web, security hoặc một service không liên quan che khuất lỗi data layer.

## 14. Kiểm tra chính phạm vi context được nạp

Khi không chắc một bean có được đưa vào slice hay không, có thể kiểm tra trực tiếp ApplicationContext:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;

@DataNeo4jTest
class Neo4jSliceScopeTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void loadsRepositoryButNotRegularServiceByDefault() {
        assertThat(applicationContext.getBeansOfType(MovieRepository.class))
            .isNotEmpty();

        assertThat(applicationContext.getBeansOfType(MovieService.class))
            .isEmpty();
    }
}
```

Đoạn test minh họa hành vi mặc định khi `MovieService` không được import và không có filter bổ sung. Nếu class service được import bởi một cấu hình khác, assertion thứ hai cần phản ánh cấu hình thực tế.

Có thể dùng cách tương tự để xác minh converter, configuration properties hoặc bean test đã được import đúng chưa. Đây là cách chẩn đoán trực tiếp khi test fail với lỗi `NoSuchBeanDefinitionException`.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không import được `DataNeo4jTest` | Dùng package của Boot 3 trong dự án Boot 4 hoặc thiếu module test | Kiểm tra Boot version và dependency |
| Repository không được inject | Repository nằm ngoài package scan hoặc không được bật | Đặt test dưới package gốc phù hợp hoặc cấu hình repository scan |
| Service không được inject | `@Service` thông thường bị slice filter loại | Dùng `@Import(Service.class)` |
| Converter hoặc custom config không có | Cấu hình không thuộc phạm vi mặc định | Import cấu hình cần thiết |
| `@ConfigurationProperties` bean bị thiếu | Test slice không tự scan properties class | Dùng `@EnableConfigurationProperties` |
| Test context khởi động nhưng không kết nối được Neo4j | Chưa cấu hình URI/credential hoặc database chưa chạy | Dùng Testcontainers, harness hoặc server test |
| Nghĩ test slice tạo embedded database | Nhầm test infrastructure với database runtime | Cung cấp database riêng |
| Dữ liệu test còn lại sau khi chạy | Thao tác ghi không tham gia test transaction hoặc đã tắt rollback | Kiểm tra transaction manager và cleanup |
| Reactive test không rollback | Test transaction mặc định là imperative | Dùng NOT_SUPPORTED và TransactionalOperator |
| Test context tải quá nhiều bean | Dùng `@SpringBootTest` cho bài test repository đơn giản | Dùng `@DataNeo4jTest` |
| Context giữ connection tới container đã dừng | Container lifecycle ngắn hơn Spring context cache | Quản lý container theo context hoặc điều chỉnh cache/lifecycle |
| Test chạy được riêng nhưng fail cả suite | Dữ liệu dùng chung hoặc test phụ thuộc thứ tự | Cô lập database và loại bỏ shared mutable state |

## 16. Quy trình chọn và cấu hình test slice

Khi tạo test cho một tính năng SDN, có thể đi theo trình tự:

1. Xác định chỉ cần test mapping/repository hay cần toàn bộ application context.
2. Chọn `@DataNeo4jTest` nếu phạm vi chính là Neo4j data layer.
3. Kiểm tra package annotation và module test theo Spring Boot version.
4. Đặt test trong package có thể tìm thấy `@SpringBootConfiguration` của ứng dụng.
5. Xác nhận repository và entity thuộc package scan.
6. Bổ sung service/configuration bằng `@Import`; bổ sung properties bằng `@EnableConfigurationProperties`.
7. Cấp Neo4j test database riêng qua Testcontainers, test harness hoặc server test.
8. Kiểm tra test imperative có rollback đúng không.
9. Nếu dùng reactive, tắt imperative test transaction và thiết lập reactive transaction test riêng.
10. Chỉ chuyển sang `@SpringBootTest` khi test cần xác minh wiring hoặc hành vi ở cấp ứng dụng.

## 17. Câu hỏi tự kiểm tra

1. `@DataNeo4jTest` là test slice hay full application context?
2. Annotation tự động quét những loại entity nào?
3. Vì sao một class `@Service` không được inject mặc định?
4. Làm thế nào import một service vào test slice?
5. Làm thế nào đăng ký `@ConfigurationProperties` trong test?
6. Package của `@DataNeo4jTest` khác nhau thế nào giữa Boot 3 và Boot 4?
7. Những nhóm auto-configuration Neo4j nào được bật trong slice?
8. Vì sao test context không đồng nghĩa Neo4j database đã được khởi động?
9. Testcontainers `@ServiceConnection` giúp cấu hình kết nối thế nào?
10. Vì sao imperative test transaction rollback khi test kết thúc?
11. Vì sao rollback mặc định không áp dụng cho reactive access?
12. Khi nào nên chọn `@SpringBootTest` thay vì `@DataNeo4jTest`?
13. Làm thế nào xác minh một bean có thực sự nằm trong ApplicationContext?
14. Vì sao cần cô lập database khi chạy test song song?

## Tài liệu tham khảo

- [Spring Boot 3.5 – DataNeo4jTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/neo4j/DataNeo4jTest.html)
- [Spring Boot 4.0 – DataNeo4jTest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/neo4j/test/autoconfigure/DataNeo4jTest.html)
- [Spring Boot 3.5 – Test Slices và auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 4.0 – Test Slices và auto-configuration](https://docs.spring.io/spring-boot/4.0/appendix/test-auto-configuration/slices.html)
- [Spring Data Neo4j – Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot – Testcontainers và Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

## Kết luận

`@DataNeo4jTest` tạo một test slice tập trung vào SDN: nó nạp auto-configuration liên quan đến Neo4j, quét entity và repository, đồng thời cung cấp client, template và transaction infrastructure phù hợp. Các service, component và `@ConfigurationProperties` thông thường không tự động được đưa vào context; hãy import hoặc bật đúng class mà test cần.

Test slice không khởi động hoặc provision Neo4j database. Hãy cấp một Neo4j test database riêng bằng Testcontainers, test harness hoặc server test và cấu hình connection details trước khi Spring tạo Driver. Với imperative access, test transaction mặc định rollback khi kết thúc; với reactive access, cần tắt imperative test transaction và quản lý reactive transaction bằng `TransactionalOperator` khi cần kiểm tra atomicity.

Chọn `@DataNeo4jTest` cho mapping và repository, mở rộng context có chủ đích khi cần service hoặc converter, và dùng `@SpringBootTest` cho các kiểm thử cần toàn bộ ứng dụng. Hiểu rõ ranh giới cấu hình giúp test nhanh hơn, dễ chẩn đoán hơn và phản ánh đúng thành phần mà bài test muốn xác minh.
