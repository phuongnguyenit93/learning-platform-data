# Vòng đời hạ tầng ngoài so với context cache

Kiểm thử tích hợp thường cần nhiều thành phần ngoài Spring application context: PostgreSQL, Redis, Kafka, message broker, HTTP mock server, file server hoặc một dịch vụ chạy trong Docker. Những thành phần này có vòng đời riêng. Trong khi đó, Spring Test có thể giữ và tái sử dụng `ApplicationContext` giữa nhiều test class để giảm thời gian khởi động.

Hai cơ chế này không tự động đồng bộ với nhau. Một context được cache có thể tiếp tục giữ datasource, WebClient hoặc client khác trỏ đến một container đã bị dừng. Test tiếp theo có thể thất bại dù context khởi tạo thành công trước đó. Ngược lại, nếu mỗi test class khởi động một container mới trong khi Spring tái sử dụng context cũ, context có thể vẫn trỏ đến địa chỉ của container trước.

Muốn test tích hợp ổn định, cần thiết kế rõ ai sở hữu từng tài nguyên, tài nguyên sống trong bao lâu, khi nào context được tạo/đóng và thứ tự cleanup. Nguyên tắc quan trọng là vòng đời của dependency phải bao phủ toàn bộ thời gian context đang sử dụng dependency đó.

## 1. Spring TestContext cache hoạt động như thế nào?

Spring TestContext Framework quản lý việc tạo và tái sử dụng application context cho các test dùng Spring. Khi hai test có cấu hình tương đương, Spring có thể dùng chung context đã tạo thay vì khởi động lại toàn bộ bean cho mỗi class.

Ví dụ:

```java
@SpringBootTest
class OrderServiceIntegrationTest {
    // Dùng ApplicationContext của ứng dụng.
}

@SpringBootTest
class InventoryRepositoryIntegrationTest {
    // Có thể tái sử dụng cùng cấu hình ApplicationContext.
}
```

Việc cache không dựa đơn giản vào tên class. Spring xây dựng khóa context từ các yếu tố cấu hình như:

- Configuration classes và context initializer.
- Context loader và parent context.
- Active profiles.
- Test property sources và inline properties.
- Context customizers, bao gồm các thành phần do Spring Boot test và dynamic property source đăng ký.
- Các thành phần cấu hình khác tham gia vào việc dựng context.

Nếu khóa cấu hình phù hợp, context có thể được tái sử dụng giữa test class. Cache là một cấu trúc trong tiến trình test, không phải một registry toàn cục dùng chung giữa các JVM. Mặc định cache có giới hạn kích thước và có thể loại context ít được dùng khi vượt giới hạn.

Điều cần nhớ là Spring cache `ApplicationContext`, chứ không tự quản lý mọi tiến trình bên ngoài mà test đã khởi động. Container Docker, mock HTTP server, file tạm hoặc process phụ chỉ được quản lý theo vòng đời mà test, JUnit extension hoặc Spring bean đã cấu hình.

## 2. Hai vòng đời độc lập

Một test tích hợp thường có ít nhất hai nhóm tài nguyên:

**Tài nguyên thuộc Spring context** gồm datasource bean, `WebClient`, `RestClient`, repository, service, executor và các bean có lifecycle callback. Khi context được tạo, các bean được khởi tạo và có thể kết nối tới hạ tầng ngoài. Khi context đóng, Spring gọi các callback hủy bean phù hợp.

**Hạ tầng ngoài context** gồm container database, Redis, Kafka, WireMock server, MockWebServer, process phụ hoặc tài nguyên do test tự tạo. Chúng có thể sống theo test method, test class, cả test suite hoặc được quản lý bởi Spring context.

Ví dụ một cấu hình có thể tạo ra tình huống nguy hiểm:

```text
Test class A bắt đầu
    |
    +--> Khởi động PostgreSQL container A
    |
    +--> Spring tạo ApplicationContext C
    |       |
    |       +--> DataSource giữ URL của container A
    |
    +--> Test class A kết thúc
            |
            +--> JUnit dừng container A

Test class B bắt đầu
    |
    +--> Spring tái sử dụng ApplicationContext C từ cache
            |
            +--> DataSource vẫn trỏ tới container A đã dừng
```

Context cache không tự biết container A đã bị dừng. Khi class B truy vấn database, connection có thể thất bại vì endpoint cũ không còn hoạt động.

Quy tắc thiết kế:

```text
Lifetime của external dependency >= Lifetime của mọi ApplicationContext đang dùng nó
```

Nếu dependency phải dừng sớm hơn, cần đóng/evict context trước khi dependency dừng hoặc cấu hình lại context để nó kết nối tới dependency mới.

## 3. Vòng đời container với Testcontainers JUnit 5

Testcontainers cung cấp JUnit Jupiter extension để quản lý container qua annotation `@Testcontainers` và `@Container`.

```java
@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Với JUnit Jupiter Testcontainers extension:

- Container được đánh dấu `static @Container` được khởi động một lần cho các test method của class và dừng sau class đó.
- Container được đánh dấu `@Container` trên instance field được khởi động và dừng cho từng test method.
- Extension quản lý việc start/stop theo vòng đời JUnit của class hoặc method.

Mẫu này phù hợp khi context và container chỉ được sử dụng trong phạm vi test class đó, hoặc khi context được bảo đảm không được tái sử dụng sau khi container dừng. Tuy nhiên, Spring TestContext cache có thể giữ context lâu hơn một class. Vì vậy không nên mặc định rằng `static @Container` có vòng đời đủ dài cho mọi context cache.

Đặc biệt cẩn thận khi nhiều test class kế thừa cùng một base class có `@DynamicPropertySource`. Context có thể được tái sử dụng trong khi extension dừng container theo ranh giới class. Nếu class tiếp theo cần cùng context, datasource có thể giữ endpoint của container đã dừng.

## 4. Dùng container singleton sống xuyên suốt test suite

Nếu nhiều test class dùng chung một database, một cách phổ biến là quản lý container ở phạm vi suite/JVM. Container được khởi động một lần và không để JUnit extension dừng sau mỗi class.

Ví dụ base class:

```java
abstract class PostgresIntegrationTestBase {

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
```

Các test class kế thừa base class:

```java
@SpringBootTest
class OrderRepositoryIntegrationTest extends PostgresIntegrationTestBase {
}

@SpringBootTest
class InventoryRepositoryIntegrationTest extends PostgresIntegrationTestBase {
}
```

Trong mẫu này không gắn `@Container` và không dùng `@Testcontainers` để extension dừng container sau mỗi class. Container được khởi động thủ công ở static initializer và tiếp tục sống trong suốt vòng đời class loader/JVM test. Testcontainers vẫn có cơ chế dọn container khi tiến trình kết thúc; nếu dự án cần lifecycle teardown tường minh, có thể quản lý việc stop ở cấp suite phù hợp.

Ưu điểm là endpoint database ổn định trong toàn bộ thời gian context cache được sử dụng. Nhược điểm là dữ liệu và trạng thái database cũng được chia sẻ giữa các class. Cần cô lập dữ liệu test bằng id duy nhất, transaction/cleanup phù hợp, schema riêng hoặc truncate có kiểm soát.

Không nên để mỗi test class xóa toàn bộ database nếu các test khác có thể chạy song song. Dùng namespace riêng hoặc fixture có khóa riêng để tránh xung đột.

## 5. Để Spring quản lý container như một bean

Một cách khác là đặt container trong Spring `ApplicationContext` để vòng đời của nó gắn với vòng đời context. Khi context được tạo, container bean được khởi tạo; khi context đóng, Spring hủy bean và gọi stop.

Với Spring Boot 3.1 trở lên, có thể dùng `@ServiceConnection` để Spring Boot nhận diện thông tin kết nối từ Testcontainers:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class DatabaseContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Import cấu hình trong integration test:

```java
@SpringBootTest
@Import(DatabaseContainerConfiguration.class)
class OrderRepositoryIntegrationTest {
}
```

Spring Boot tạo connection details từ container và dùng chúng cho auto-configuration phù hợp. Container là bean nên được quản lý cùng context. Khi Spring đóng context, bean container được hủy và container dừng. Nếu context được cache và tái sử dụng, container cũng tiếp tục sống cùng context.

Để dùng `@ServiceConnection`, dự án cần dependency hỗ trợ Spring Boot Testcontainers, thường là:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

Và dependency Testcontainers cho loại dịch vụ tương ứng. Phiên bản các dependency nên được quản lý bằng Spring Boot dependency management hoặc BOM tương thích.

### Quản lý bean bằng init/destroy method

Nếu không dùng `@ServiceConnection`, có thể khai báo lifecycle bean thủ công:

```java
@TestConfiguration(proxyBeanMethods = false)
class ExternalServiceConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    GenericContainer<?> redisContainer() {
        return new GenericContainer<>(DockerImageName.parse("redis:7-alpine"))
                .withExposedPorts(6379);
    }
}
```

Sau đó đăng ký các property kết nối phù hợp bằng một cơ chế cấu hình được kiểm soát. Với các container hỗ trợ service connection, `@ServiceConnection` thường giúp tránh tự viết URL, port và credential.

Không khai báo đồng thời nhiều cơ chế sở hữu cùng một container, chẳng hạn vừa để Spring bean gọi `stop()` vừa để JUnit extension quản lý stop. Mỗi tài nguyên nên có một chủ sở hữu lifecycle rõ ràng.

## 6. DynamicPropertySource và giá trị cấu hình trong context

`@DynamicPropertySource` cho phép đăng ký property lấy từ tài nguyên được khởi động trong test, thường là URL và credential của container:

```java
@DynamicPropertySource
static void redisProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", redis::getHost);
    registry.add("spring.data.redis.port", redis::getFirstMappedPort);
}
```

Supplier được đăng ký cho property, giúp lấy giá trị từ container đang chạy khi property được resolve. Các dynamic properties có độ ưu tiên cao trong Environment so với nhiều nguồn cấu hình test thông thường.

Tuy vậy, dynamic property không phải cơ chế tự động khởi động hoặc giữ sống container. Nó chỉ cung cấp giá trị cấu hình. Nếu container dừng, URL và port không còn dùng được dù property vẫn có thể trả về chuỗi cũ.

Spring TestContext cache cũng không xem mọi giá trị runtime mà supplier có thể trả về như một context key độc lập. Nếu cùng một phương thức `@DynamicPropertySource` được kế thừa nhưng container phía sau thay đổi giữa các test class, context cũ có thể được tái sử dụng với bean đã tạo từ cấu hình trước đó.

Spring khuyến nghị dùng `@DirtiesContext` nếu các dynamic properties thay đổi giữa các subclass theo cách đòi hỏi context mới. Tuy nhiên, giải pháp bền vững hơn thường là giữ cùng một container trong toàn bộ thời gian context dùng nó, hoặc để Spring quản lý container bean.

### Không thay đổi endpoint trong khi context còn sống

Ví dụ không an toàn:

```text
Class A:
  container A -> jdbc:postgresql://host:portA/db
  context C tạo DataSource trỏ portA

Class A kết thúc:
  container A dừng

Class B:
  container B -> jdbc:postgresql://host:portB/db
  context C được tái sử dụng
  DataSource trong C vẫn trỏ portA
```

Ngay cả khi supplier dynamic property trả portB ở lần resolve tiếp theo, bean `DataSource` đã được tạo trong context có thể không được dựng lại. Không dùng dynamic property như cơ chế đổi endpoint cho bean singleton đang hoạt động.

## 7. `@DirtiesContext` làm gì và không làm gì?

`@DirtiesContext` đánh dấu một `ApplicationContext` đã bị thay đổi hoặc không còn an toàn để tái sử dụng. Spring sẽ đóng context và loại nó khỏi cache theo mode được chọn. Test sau đó cần một context mới.

Ví dụ:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestThatChangesApplicationContextState {
}
```

Các mode có thể áp dụng ở mức method hoặc class, trước hoặc sau test tùy mục tiêu. Dùng annotation này khi test thay đổi trạng thái singleton bean, cấu hình context hoặc một trạng thái khiến context không còn phù hợp với test khác.

`@DirtiesContext` không phải công cụ dọn mọi tài nguyên bên ngoài. Nó đóng context và gọi lifecycle callback của bean trong context. Một container được JUnit extension quản lý, một WireMock server được tạo thủ công trong static field hoặc một process test tự mở có thể vẫn chạy nếu không có cơ chế cleanup riêng.

Nếu container là bean trong context, việc đóng context sẽ gọi destroy method của bean và dừng container. Nếu container do JUnit extension quản lý, extension vẫn sở hữu việc stop. Hai trường hợp này cần được phân biệt.

Không nên gắn `@DirtiesContext` vào mọi test để né lỗi lifecycle. Việc đóng và dựng lại context có thể tốn nhiều thời gian, đồng thời che giấu việc một tài nguyên ngoài đang bị quản lý sai vòng đời.

## 8. Vòng đời của mock HTTP server và process ngoài

Nguyên tắc tương tự áp dụng cho WireMock, MockWebServer hoặc một dịch vụ giả khác.

Nếu client bean được tạo trong Spring context với base URL của WireMock server, server phải sống ít nhất trong toàn bộ thời gian context sử dụng client đó.

Ví dụ server do test class quản lý:

```java
@SpringBootTest
class PaymentClientIntegrationTest {

    static WireMockServer wireMock = new WireMockServer(options().dynamicPort());

    @BeforeAll
    static void startServer() {
        wireMock.start();
    }

    @AfterAll
    static void stopServer() {
        wireMock.stop();
    }

    @DynamicPropertySource
    static void paymentProperties(DynamicPropertyRegistry registry) {
        registry.add("payment.base-url", wireMock::baseUrl);
    }
}
```

Mẫu này có thể phù hợp khi context không được dùng sau khi server dừng. Nhưng nếu context cache tái sử dụng client bean ở class khác, base URL có thể trỏ đến server đã tắt. Với server dùng chung nhiều class, hãy quản lý server ở phạm vi suite hoặc như bean của context.

Nếu server chỉ phục vụ một test method và client không được cache cùng endpoint, tạo và dừng server trong method hoặc JUnit extension là hợp lý. Cần bảo đảm các bean đang sử dụng server đã ngừng hoạt động trước khi server bị dừng.

## 9. Thứ tự cleanup và shutdown

Khi test kết thúc, cleanup cần tuân theo quan hệ phụ thuộc. Client và pool kết nối nên ngừng sử dụng tài nguyên trước khi tài nguyên đó bị dừng.

Thứ tự khái quát:

```text
Ngừng nhận test request mới
        |
        v
Chờ tác vụ async đang dùng dependency hoàn tất
        |
        v
Đóng ApplicationContext / client / connection pool
        |
        v
Dừng external service hoặc container
        |
        v
Dọn dữ liệu, file tạm và network resource còn lại
```

Thứ tự cụ thể phụ thuộc ai sở hữu tài nguyên. Khi container là bean của context, Spring thực hiện hủy bean theo lifecycle của context. Khi container là suite-scoped resource, context có thể được đóng ở cuối suite trước khi container dừng. Tránh dừng database trong khi connection pool của context vẫn có thể cấp connection.

Với executor, hãy ngừng submit tác vụ mới và chờ công việc đang chạy trước khi đóng database hoặc broker mà tác vụ sử dụng. Nếu dừng broker trước, tác vụ async có thể thất bại trong cleanup và làm test sau nhận trạng thái không xác định.

## 10. Cô lập dữ liệu khi hạ tầng được chia sẻ

Giữ container sống lâu giúp giảm thời gian khởi động nhưng khiến nhiều test dùng chung một dịch vụ. Hạ tầng được chia sẻ cần chiến lược cô lập dữ liệu rõ ràng.

Các lựa chọn thường gặp:

- Dùng id duy nhất cho mỗi test, ví dụ UUID trong tên order hoặc message key.
- Tạo schema hoặc database riêng theo test class nếu database hỗ trợ.
- Dùng topic, queue hoặc consumer group riêng cho từng nhóm test.
- Dọn đúng các record do test tạo thay vì truncate toàn bộ bảng đang được test khác dùng.
- Reset mock server expectation sau mỗi test method.
- Dùng namespace riêng trong Redis key để tránh đụng dữ liệu.

`@Transactional` có thể rollback dữ liệu do test thread tạo, nhưng không tự rollback transaction của worker thread, message consumer hoặc tác vụ `@Async`. Khi tác vụ chạy trên thread khác, transaction thường độc lập. Dùng commit boundary và cleanup rõ ràng cho dữ liệu do worker tạo.

Nếu nhiều test chạy song song, không dựa vào thứ tự thực thi để dọn dữ liệu. Mỗi test cần sở hữu namespace hoặc dữ liệu riêng. Shared container không đồng nghĩa shared test state.

## 11. Parallel test và tài nguyên dùng chung

Khi bật JUnit parallel execution, nhiều test có thể cùng truy cập một container hoặc server giả. Điều đó hợp lệ nếu dịch vụ hỗ trợ truy cập đồng thời và test cô lập dữ liệu. Nhưng có thể xảy ra các lỗi như:

- Một test reset database trong lúc test khác đang đọc.
- Một test gọi `wireMock.resetAll()` xóa stub của test khác.
- Hai test cùng tiêu thụ response từ một hàng đợi MockWebServer.
- Một test dừng container dùng chung trong khi test khác còn chạy.
- Các test dùng cùng một file hoặc port cố định.

Với tài nguyên dùng chung, lifecycle phải do một owner duy nhất quản lý. Test method không được tự dừng tài nguyên suite-scoped. Nếu một server mock có stateful expectation, cân nhắc instance riêng cho mỗi test hoặc cô lập stub theo path/header.

Khi cần tuần tự hóa một nhóm test chia sẻ trạng thái, có thể dùng JUnit `@ResourceLock` hoặc cấu hình execution phù hợp. Đây là biện pháp bảo vệ khi không thể cô lập tài nguyên; không nên dùng khóa toàn cục để che mọi xung đột dữ liệu.

## 12. So sánh các chiến lược sở hữu hạ tầng

| Chiến lược | Vòng đời hạ tầng | Vòng đời context | Phù hợp khi | Rủi ro chính |
|---|---|---|---|---|
| JUnit instance `@Container` | Mỗi test method | Có thể được cache lâu hơn method | Test không giữ client/context phụ thuộc container qua method. | Context tái sử dụng có thể trỏ container đã dừng. |
| JUnit static `@Container` | Một test class | Có thể được cache qua nhiều class | Test class độc lập, context không được dùng sau class. | Container dừng trước khi cached context hết vòng đời. |
| Singleton container ở suite | Cả test suite/JVM | Context có thể được cache trong suite | Nhiều class dùng cùng dịch vụ và endpoint ổn định. | Dữ liệu chia sẻ, cần cô lập và cleanup. |
| Container là Spring bean | Vòng đời của context | Container và context cùng lifecycle | Client bean trong context phụ thuộc container. | Context bị đóng thì container dừng; phải tránh context mới phụ thuộc bean cũ. |
| Server mock trong test method | Một test method | Client được tạo/dùng trong method | Unit/integration test nhỏ không cache client phụ thuộc server. | Không phù hợp với bean singleton giữ URL server theo class. |

Không có một chiến lược duy nhất cho mọi test. Chọn theo ranh giới sở hữu và thời gian sử dụng thực tế. Nếu context cache giữ một client singleton, hạ tầng mà client gọi cần tồn tại ít nhất đến khi context bị đóng.

## 13. Ví dụ chọn chiến lược theo tình huống

### Một test class dùng database riêng

Nếu class chỉ dùng context với container của chính nó và không chia sẻ context với test khác, `static @Container` có thể đủ. Đảm bảo context không được tái sử dụng sau khi container dừng; nếu cấu hình context được chia sẻ, cần điều chỉnh lifecycle hoặc đánh dấu context dirty có chủ đích.

### Nhiều class cùng dùng một database

Dùng singleton container hoặc container bean do Spring quản lý. Hai lựa chọn này giúp endpoint ổn định khi Spring tái sử dụng context. Cần tạo dữ liệu độc lập cho từng test.

### Mỗi class cần một database có cấu hình khác nhau

Dùng context key khác nhau bằng configuration/property/profile phù hợp để Spring tạo context riêng, đồng thời quản lý container theo cùng phạm vi. Nếu dynamic property thay đổi nhưng cache key không thay đổi tương ứng, dùng context riêng hoặc `@DirtiesContext` theo đúng nhu cầu.

### Mock HTTP server chỉ phục vụ một test

Khởi động server trong test method, tạo HTTP client dùng URL của server rồi gửi request. Sau khi response được xác minh và client không còn công việc nền, dừng server. Không đưa URL động của server method-scoped vào singleton bean trong context được cache lâu dài.

## 14. Cấu hình context cache và chẩn đoán lỗi

Spring TestContext cache có thể được quan sát qua log debug của package `org.springframework.test.context.cache`. Log cho biết số lần hit/miss và kích thước cache, hữu ích khi điều tra vì sao context được tái sử dụng hoặc dựng lại.

Kích thước cache mặc định có thể được điều chỉnh bằng system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Tăng kích thước cache có thể giảm số lần dựng lại context trong suite lớn, nhưng không sửa được lỗi container bị dừng sớm. Nếu một context giữ kết nối tới endpoint cũ, tăng cache size có thể khiến context lỗi được giữ lâu hơn.

Khi gặp lỗi connection refused hoặc datasource không kết nối được trong test suite, hãy xác định:

1. Context được tạo lần đầu ở test class nào?
2. Bean client/datasource đã lưu URL hoặc port nào?
3. Container/server đó do JUnit, Spring hay code test quản lý?
4. Tài nguyên đã bị dừng ở callback nào?
5. Test class sau có tái sử dụng cùng context cache key không?
6. Dynamic property source có trả endpoint khác với endpoint bean đã sử dụng lúc khởi tạo không?

Kiểm tra các mốc start/stop và context cache thường tìm ra nguyên nhân nhanh hơn việc tăng timeout hoặc thêm `Thread.sleep`.

## 15. Những lỗi thiết kế thường gặp

### Container dừng sau class nhưng context vẫn được cache

Đây là lỗi phổ biến nhất khi dùng static `@Container` cùng Spring context cache. Giải pháp là kéo dài vòng đời container, chuyển container thành bean của context hoặc đảm bảo context được đóng trước khi container dừng và không được tái sử dụng.

### Dùng `@DirtiesContext` như cleanup chung

`@DirtiesContext` chỉ quản lý context. Nó không tự dừng process hoặc tài nguyên do JUnit/code test quản lý. Mỗi tài nguyên cần owner và cleanup riêng.

### Thay đổi DynamicPropertySource nhưng giữ bean cũ

Dynamic property supplier không tự tạo lại `DataSource`, `WebClient` hoặc bean singleton đã khởi tạo. Khi endpoint thay đổi, cần context mới hoặc thiết kế bean có cơ chế refresh rõ ràng.

### Quản lý cùng container bằng nhiều cơ chế

Không để JUnit extension và Spring bean cùng stop một container. Chọn một owner duy nhất để tránh stop sớm hoặc cleanup trùng.

### Dùng shared database nhưng không cô lập dữ liệu

Một test có thể đọc dữ liệu do test khác tạo hoặc xóa dữ liệu mà test khác đang cần. Dùng id/schema/topic riêng và cleanup theo phạm vi sở hữu.

### Đóng hạ tầng trước tác vụ async

Worker có thể vẫn dùng database hoặc broker khi test kết thúc. Hãy chờ worker hoàn tất hoặc hủy có kiểm soát trước khi dừng dependency.

### Dùng `Thread.sleep` để chờ container sẵn sàng

Container start API và wait strategy của Testcontainers đã cung cấp cơ chế chờ readiness. Dùng readiness check và điều kiện kết nối thực tế thay vì sleep một khoảng cố định.

## 16. Checklist quản lý vòng đời

- [ ] Xác định tài nguyên nào thuộc Spring context và tài nguyên nào do JUnit/test quản lý.
- [ ] Xác định context có thể được tái sử dụng qua những test class nào.
- [ ] Bảo đảm database, broker hoặc mock server sống lâu hơn mọi context đang phụ thuộc vào nó.
- [ ] Nếu dùng `@Container` theo class/method, kiểm tra context cache không vượt quá vòng đời container.
- [ ] Với hạ tầng dùng chung nhiều class, cân nhắc singleton container hoặc Spring-managed container bean.
- [ ] Nếu dùng `@DynamicPropertySource`, giữ endpoint ổn định trong vòng đời context đã khởi tạo từ nó.
- [ ] Dùng `@DirtiesContext` khi context thật sự cần bị loại khỏi cache, không coi đó là cleanup cho mọi tài nguyên.
- [ ] Mỗi tài nguyên có một owner chịu trách nhiệm start/stop.
- [ ] Cleanup context/client trước khi dừng external dependency mà chúng đang sử dụng.
- [ ] Cô lập database, queue, cache và mock server state giữa các test.
- [ ] Khi chạy song song, không để test này dừng hoặc reset tài nguyên test khác đang dùng.
- [ ] Dùng readiness check thay cho `Thread.sleep` để chờ hạ tầng sẵn sàng.

Spring TestContext cache tối ưu thời gian bằng cách giữ lại application context; Testcontainers và các mock server lại có vòng đời do JUnit, Spring bean hoặc test code quản lý. Khi hai vòng đời không khớp, context có thể giữ client trỏ đến một dependency đã dừng. Thiết kế owner rõ ràng, giữ hạ tầng sống đủ lâu, quản lý dynamic property nhất quán và cô lập dữ liệu sẽ giúp test tích hợp chạy ổn định cả khi context được cache lẫn khi suite chạy song song.
