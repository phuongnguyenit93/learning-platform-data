# Tách bài kiểm thử nhanh với bài cần hạ tầng

Một bộ kiểm thử Spring thường chứa nhiều loại test với chi phí và yêu cầu môi trường khác nhau. Có test chỉ gọi một method Java và hoàn tất trong vài mili giây; có test cần tạo `ApplicationContext`, khởi động PostgreSQL, kết nối Kafka hoặc chờ một consumer xử lý message. Nếu chạy tất cả test theo cùng một cách ở mọi lần build, nhóm phát triển sẽ phải chờ lâu ngay cả khi chỉ sửa một quy tắc nghiệp vụ nhỏ.

Tách bài kiểm thử nhanh khỏi bài cần hạ tầng giúp giữ phản hồi nhanh trong vòng lặp phát triển, đồng thời vẫn chạy các kiểm thử tích hợp có giá trị. Việc tách cần dựa trên phạm vi phụ thuộc và môi trường mà test yêu cầu, sau đó thể hiện rõ trong JUnit tags, Gradle/Maven tasks và các giai đoạn CI.

Mục tiêu không phải làm cho nhóm test chậm biến mất khỏi pipeline. Mục tiêu là biết test nào có thể chạy ngay, test nào cần dịch vụ bên ngoài, khi nào mỗi nhóm phải chạy và ai chịu trách nhiệm bảo đảm hạ tầng sẵn sàng.

## 1. Phân loại theo phạm vi và phụ thuộc

Một cách phân loại hữu ích là nhìn vào điều test thực sự cần để chứng minh hợp đồng.

| Nhóm | Phạm vi thường gặp | Hạ tầng cần có | Đặc điểm thực thi |
|---|---|---|---|
| Unit test | Một class hoặc một quy tắc nghiệp vụ | Không cần Spring context hay dịch vụ ngoài | Rất nhanh, chạy thường xuyên |
| Spring slice test | Một lát cắt MVC, JPA, JSON hoặc security | Spring test context; có thể dùng fake/mock hoặc DB nhúng | Nhanh đến trung bình |
| Integration test | Nhiều bean hoặc một ranh giới tích hợp | Database, broker, cache hoặc dịch vụ thật | Tốn thời gian khởi động và cleanup |
| End-to-end test | Luồng qua nhiều thành phần hoặc server đang chạy | Một stack ứng dụng và hạ tầng gần production | Chậm hơn, cần môi trường ổn định |

Ví dụ:

- `PriceCalculatorTest` kiểm tra cách tính giá thuần Java: unit test.
- `OrderControllerWebTest` dùng `@WebMvcTest` để kiểm tra binding, validation và response: Spring slice test.
- `OrderRepositoryIT` chạy query trên PostgreSQL Testcontainers: integration test.
- `OrderFlowIT` khởi động ứng dụng và database/broker rồi gửi HTTP request qua server thật: end-to-end hoặc full integration test, tùy phạm vi.

Không nên chỉ nhìn vào tên annotation để quyết định test nhanh hay chậm. `@SpringBootTest` có thể không dùng container nhưng vẫn tốn thời gian tạo context; một test với container dùng chung có thể chạy khá nhanh sau lần khởi động đầu. Hãy phân loại theo phụ thuộc, chi phí thực tế và rủi ro mà test bảo vệ.

## 2. Xác định ranh giới giữa test nhanh và test cần hạ tầng

Một số câu hỏi giúp xác định nhóm:

1. Test có cần Docker hoặc một dịch vụ chạy bên ngoài JVM không?
2. Test có cần đúng engine/protocol production như PostgreSQL, Kafka hay RabbitMQ không?
3. Test có cần mở HTTP port hoặc giao tiếp qua network thật không?
4. Test có cần migration, transaction, broker acknowledgement hoặc consumer bất đồng bộ không?
5. Nếu chạy test độc lập trên máy developer không có dịch vụ nền, test có thể hoạt động không?

Nếu câu trả lời cho các câu hỏi về hạ tầng là có, test thường thuộc nhóm integration hoặc end-to-end. Nếu test chỉ cần object Java, mock hoặc một Spring slice được kiểm soát, nó thường phù hợp với nhóm nhanh.

| Tình huống | Nhóm đề xuất | Lý do |
|---|---|---|
| Kiểm tra một hàm đổi trạng thái đơn hàng | Fast | Không phụ thuộc database hoặc Spring |
| Kiểm tra controller trả `400` khi DTO sai | Fast/slice | Mock MVC context có thể kiểm tra contract HTTP mà không cần server thật |
| Kiểm tra repository dùng PostgreSQL JSONB | Infrastructure | Cần đúng database engine |
| Kiểm tra Flyway migration trên PostgreSQL | Infrastructure | Cần schema và catalog của PostgreSQL |
| Kiểm tra publish/consume qua RabbitMQ | Infrastructure | Cần broker và protocol AMQP thật |
| Kiểm tra TLS, port hoặc connector server | Infrastructure/E2E | Cần HTTP transport hoặc server thật |
| Kiểm tra service gọi một interface gateway bằng Mockito | Fast | Chỉ kiểm tra logic điều phối, không kiểm tra transport |

Một test có thể được gắn nhiều tag, ví dụ `integration` và `database`. Điều đó cho phép pipeline chạy toàn bộ integration test hoặc chỉ nhóm database khi cần. Tag nên mô tả thuộc tính có ý nghĩa, không phải ghi lại mọi chi tiết triển khai.

## 3. Giữ unit test nhỏ và độc lập

Unit test nên chạy trực tiếp trên class đang kiểm tra, với dependency được truyền qua constructor. Không khởi động toàn bộ Spring context nếu mục tiêu chỉ là kiểm tra một phép tính hoặc quyết định nghiệp vụ.

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ShippingFeeCalculatorTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void waivesFeeForLargeOrders() {
        assertThat(calculator.calculate(250_000))
                .isZero();
    }
}

class ShippingFeeCalculator {

    int calculate(int orderTotal) {
        return orderTotal >= 200_000 ? 0 : 25_000;
    }
}
```

Test này không cần `@SpringBootTest`, database hoặc container. Nó có thể chạy trên mọi máy có JDK và test dependencies. Khi một unit test thất bại, phạm vi nguyên nhân nhỏ nên developer có thể tìm lỗi nhanh.

Mock nên được dùng ở ranh giới cần cô lập, chẳng hạn một HTTP gateway hoặc clock. Không mock mọi object trong test; nếu không, test có thể chỉ xác nhận cách mock được cấu hình mà không kiểm tra hành vi thực.

## 4. Spring slice test thường thuộc nhóm phản hồi nhanh

Spring Boot cung cấp các test slice để chỉ tạo phần context cần cho một lớp công việc:

| Annotation | Phạm vi thường dùng |
|---|---|
| `@WebMvcTest` | MVC controller, binding, validation, advice và web configuration liên quan |
| `@DataJpaTest` | JPA entity, repository và cấu hình persistence |
| `@JsonTest` | JSON serialization/deserialization |
| `@RestClientTest` | Thành phần Spring REST client và converter liên quan |
| `@WebFluxTest` | WebFlux controller và thành phần reactive web được chọn |

Slice test khởi động Spring nên thường chậm hơn unit test thuần JVM, nhưng vẫn nhẹ hơn việc khởi động toàn bộ ứng dụng cùng tất cả dịch vụ ngoài. Nếu một slice cần kiểm tra đúng database production, nó có thể chuyển sang nhóm integration bằng cách kết nối Testcontainers.

Ví dụ MVC slice:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", 999))
                .andExpect(status().isNotFound());
    }
}
```

Nếu controller cần service, cung cấp mock cho dependency đó. Không cần khởi động PostgreSQL chỉ để kiểm tra mapping một response nếu test không cần xác nhận truy vấn database.

## 5. Đánh dấu nhóm test bằng JUnit @Tag

JUnit Jupiter cung cấp `@Tag` để gắn nhãn cho test class hoặc method. Build tool có thể dùng tag để chọn nhóm test cần chạy.

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class OrderRepositoryIT {

    @Test
    void storesOrderInPostgres() {
        // Test cần PostgreSQL thật.
    }
}
```

Có thể gắn nhiều tag:

```java
@Tag("integration")
@Tag("database")
class OrderRepositoryIT {
    // ...
}
```

Hoặc tạo annotation riêng để quy ước được tái sử dụng:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.Tag;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Tag("integration")
public @interface IntegrationTest {
}
```

Sau đó dùng:

```java
@IntegrationTest
class OrderRepositoryIT {
    // ...
}
```

Annotation tổng hợp giúp thống nhất cách đánh dấu. Nếu một nhóm cần tag chi tiết hơn, vẫn có thể thêm `@Tag("database")` hoặc `@Tag("broker")` bên cạnh annotation đó.

Nên thống nhất một vocabulary ngắn, ví dụ:

| Tag | Ý nghĩa |
|---|---|
| `integration` | Cần một hoặc nhiều thành phần tích hợp thật |
| `database` | Cần database thật hoặc database engine cụ thể |
| `broker` | Cần message broker |
| `e2e` | Cần chạy qua nhiều thành phần hoặc server thật |
| `slow` | Có thời gian chạy dài theo quy ước của dự án |

Không cần gắn tag `fast` cho mọi unit test nếu mặc định build đã chọn tất cả test trừ integration/e2e. Dùng tag cho những nhóm cần lọc rõ ràng và duy trì quy ước nhất quán.

## 6. Tách Gradle task cho test nhanh và integration test

Với Gradle, có thể giữ tất cả test trong source set `test` nhưng tạo hai task `Test` khác nhau. Task mặc định loại trừ tag hạ tầng; task `integrationTest` chỉ chạy tag `integration`.

Ví dụ `build.gradle` dùng Groovy DSL:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration', 'e2e'
    }
}

tasks.register('integrationTest', Test) {
    description = 'Runs tests that require external infrastructure.'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration'
    }

    shouldRunAfter tasks.named('test')
}
```

Kết quả:

| Lệnh | Nhóm được chạy |
|---|---|
| `./gradlew test` | Unit và slice test; loại trừ `integration`, `e2e` |
| `./gradlew integrationTest` | Chỉ test có tag `integration` |
| `./gradlew test integrationTest` | Chạy cả hai task |

`shouldRunAfter` chỉ quy định thứ tự nếu cả hai task cùng được yêu cầu; nó không tự làm cho `integrationTest` chạy khi gọi `test`.

Nếu muốn `check` luôn bao gồm integration test, có thể thêm dependency:

```groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Hãy quyết định rõ điều này theo quy ước build. Nếu pipeline phản hồi nhanh gọi `check`, việc gắn integration test vào `check` sẽ khiến pipeline đó chạy cả hạ tầng. Một lựa chọn khác là để CI gọi `test` ở giai đoạn nhanh và gọi `integrationTest` ở giai đoạn có Docker.

### Khi nào nên tạo source set riêng?

Tách task theo tag thường đủ nếu test dùng chung test dependencies và conventions. Source set riêng như `integrationTest` hữu ích khi integration test cần dependency khác, test fixtures riêng, classpath hoặc resource riêng, hay lifecycle build riêng.

Không nên tạo source set riêng chỉ vì test chậm hơn vài giây. Nhiều cấu hình Gradle bổ sung sẽ làm build phức tạp và tăng công bảo trì. Bắt đầu bằng tag và task riêng; chỉ tách source set khi có nhu cầu classpath thực sự.

## 7. Tách Maven Surefire và Failsafe

Trong Maven, Surefire thường chạy unit test ở phase `test`. Failsafe được thiết kế để chạy integration test ở các phase `integration-test` và `verify`, giúp việc teardown và kiểm tra kết quả được thực hiện đúng lifecycle.

Có thể dùng JUnit `@Tag("integration")` và cấu hình plugin như sau:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
            <configuration>
                <excludedGroups>integration,e2e</excludedGroups>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.5.2</version>
            <configuration>
                <groups>integration</groups>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>integration-test</goal>
                        <goal>verify</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Surefire loại trừ tag integration/e2e. Failsafe chỉ chọn tag integration và chạy ở lifecycle tích hợp. Đặt tên lớp theo quy ước Failsafe như `OrderRepositoryIT` hoặc cấu hình `includes` nếu dự án dùng tên khác.

| Lệnh Maven | Kết quả |
|---|---|
| `./mvnw test` | Chạy unit/slice test qua Surefire |
| `./mvnw verify` | Chạy Surefire và integration test qua Failsafe, sau đó kiểm tra lifecycle |

Không nên gọi riêng goal `integration-test` như lệnh cuối cùng trong pipeline vì Failsafe được thiết kế để tổng hợp kết quả ở goal `verify`. Dùng `verify` để bảo đảm lỗi integration test làm build thất bại đúng cách.

## 8. Gắn tag cho Testcontainers test

Một test dùng PostgreSQL thật nên tự khai báo yêu cầu hạ tầng bằng tag và container lifecycle:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Tag("integration")
@Tag("database")
@SpringBootTest
@Testcontainers
class OrderRepositoryIT {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void persistsOrderInPostgres() {
        // Gọi repository/service và xác nhận dữ liệu thật.
    }
}
```

`@ServiceConnection` cần Spring Boot 3.1 trở lên và dependency `spring-boot-testcontainers`. Nếu dùng phiên bản Boot cũ hơn hoặc một container không được hỗ trợ, cấu hình `spring.datasource.*` bằng `@DynamicPropertySource`.

Test này không nên chạy trong task fast mặc định nếu môi trường developer hoặc CI nhanh không bảo đảm container runtime. Nhưng nó phải chạy trong integration stage có Docker hoặc runtime tương ứng.

Với `@DataJpaTest`, cần chú ý cấu hình thay database. Nếu muốn dùng container PostgreSQL thay cho embedded database, có thể khai báo:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
@Tag("integration")
class OrderRepositoryIT {
    // PostgreSQL container và repository assertions.
}
```

`replace = NONE` ngăn test slice thay `DataSource` đã cấu hình bằng embedded database. Nếu dùng `@ServiceConnection`, Spring Boot sẽ cung cấp connection details cho PostgreSQL container.

## 9. Chọn đúng mức Spring context

Không phải test cần database thật đều phải dùng `@SpringBootTest`. Chọn context nhỏ nhất vẫn kiểm tra được hợp đồng:

| Nhu cầu | Setup gợi ý |
|---|---|
| Kiểm tra repository với PostgreSQL | `@DataJpaTest` + PostgreSQL Testcontainers |
| Kiểm tra controller và database qua nhiều bean | `@SpringBootTest` hoặc slice phù hợp cùng database container |
| Kiểm tra publish/consume RabbitMQ | Spring context có `RabbitTemplate`/listener và RabbitMQ container |
| Kiểm tra toàn bộ HTTP server cùng DB/broker | `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng các container cần thiết |
| Kiểm tra service thuần với repository mock | Unit test, không cần context |

Context lớn thường tạo nhiều bean, chạy nhiều auto-configuration và tốn thời gian hơn. Dùng `@SpringBootTest` khi cần xác nhận wiring toàn ứng dụng; dùng slice khi chỉ một phần context đủ chứng minh hành vi.

Spring TestContext có thể cache context giữa các lớp test có cấu hình giống nhau. Điều này giúp giảm thời gian, nhưng container lifecycle phải sống đủ lâu cho context được tái sử dụng. Nếu container bị dừng trong khi context vẫn được cache, test sau có thể kết nối tới endpoint không còn tồn tại.

## 10. Chia giai đoạn trong CI

Một pipeline phổ biến có thể chạy các nhóm theo chi phí và mức độ phụ thuộc:

```text
Pull request
    |
    v
Compile + static checks
    |
    v
Fast tests (unit + slice)
    |
    +------> Feedback nhanh cho developer
    |
    v
Integration tests (database / broker containers)
    |
    v
End-to-end / deployment checks (nếu cần)
    |
    v
Merge / release
```

Ví dụ chính sách:

| Giai đoạn | Nhóm test | Mục tiêu |
|---|---|---|
| Mỗi commit hoặc pull request | Unit và slice test | Phát hiện lỗi nhanh với chi phí thấp |
| Pull request trước merge | Integration test thiết yếu | Xác nhận database/broker và các ranh giới quan trọng |
| Sau merge hoặc theo lịch | Bộ integration đầy đủ, E2E, test dài | Bao phủ luồng rộng và môi trường phức tạp |
| Trước release | Bộ kiểm thử phát hành | Xác nhận phiên bản có thể triển khai |

Đây là cách tổ chức tham khảo. Nếu một thay đổi tác động trực tiếp tới migration hoặc broker contract, integration test liên quan cần chạy trước khi merge, không chờ nightly. Có thể dùng path filter hoặc build matrix để chạy đúng nhóm test, nhưng phải bảo đảm mọi test quan trọng vẫn có một pipeline chịu trách nhiệm thực thi.

## 11. Ví dụ pipeline với Gradle

Với task đã khai báo ở phần trước, pipeline có thể gọi hai bước riêng:

```yaml
jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./gradlew test

  integration-tests:
    runs-on: ubuntu-latest
    needs: fast-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./gradlew integrationTest
```

Ví dụ dùng runner có container runtime sẵn. Testcontainers tự tạo database/broker trong job. Nếu runner hoặc organization policy yêu cầu cấu hình Docker riêng, hãy khai báo cấu hình đó theo nền tảng CI đang dùng.

Có thể chạy hai job song song nếu chúng độc lập và runner đủ tài nguyên. Nếu muốn chỉ chạy integration sau khi fast pass, dùng dependency `needs` như ví dụ. Chọn thứ tự dựa trên mục tiêu feedback và chi phí runner.

## 12. Ví dụ pipeline với Maven

Với Surefire/Failsafe đã cấu hình:

```yaml
jobs:
  fast-tests:
    steps:
      - run: ./mvnw test

  integration-tests:
    needs: fast-tests
    steps:
      - run: ./mvnw verify
```

`verify` chạy các phase trước đó, bao gồm `test`, rồi đến integration-test và verify của Failsafe. Vì vậy job integration cũng sẽ chạy unit/slice test nếu Surefire không bị skip. Nếu muốn tránh chạy lại test nhanh, có thể thiết kế Maven profile/lifecycle riêng, nhưng cần bảo đảm Failsafe vẫn được gọi qua `verify` và kết quả được tổng hợp.

Không nên dùng `-DskipTests` một cách chung chung để làm job integration chỉ chạy Failsafe nếu cờ đó cũng làm Failsafe bỏ qua test. Nếu cần bỏ qua Surefire, hãy dùng cấu hình hoặc property dành riêng cho plugin Surefire, rồi xác nhận Failsafe vẫn thực thi trong lifecycle.

## 13. Tránh biến test hạ tầng thành test bị bỏ qua

Một rủi ro khi tách test là tag `integration` bị loại khỏi mọi pipeline vì job có Docker không được cấu hình hoặc quá chậm. Điều này tạo cảm giác build xanh nhưng không còn xác nhận ranh giới quan trọng.

Hãy quy định rõ:

- Job nào chạy từng tag.
- Job nào cần Docker hoặc service container.
- Khi runtime không khả dụng, build phải báo lỗi cấu hình rõ ràng.
- Test nào được phép chạy nightly và test nào bắt buộc trước merge.
- Ai chịu trách nhiệm theo dõi lỗi integration test và flakiness.

Không dùng assumption hoặc `disabledWithoutDocker` để âm thầm bỏ qua integration test trong CI bắt buộc. Nếu developer local không có runtime, có thể cung cấp task fast riêng để họ vẫn nhận feedback nhanh; job integration trên CI cần runtime và phải chạy test.

## 14. Cách ly dữ liệu và tránh test phụ thuộc nhau

Chia task không tự động làm dữ liệu sạch. Nhiều integration test có thể dùng chung một PostgreSQL container hoặc Kafka broker. Nếu test dựa vào dữ liệu của test trước, kết quả sẽ phụ thuộc thứ tự hoặc mức parallelism.

Các cách cách ly thường dùng:

| Cách | Lợi ích | Lưu ý |
|---|---|---|
| Container riêng cho từng class hoặc method | Hạ tầng sạch theo lifecycle | Startup có thể chậm |
| Schema/database riêng | Cách ly dữ liệu trên cùng server | Cần quản lý tạo và xóa schema |
| Transaction rollback | Dọn row sau test | Không bao phủ công việc async hoặc transaction khác |
| Queue/topic riêng | Tránh đọc message của test khác | Cần xóa topology hoặc dùng tên duy nhất |
| Dữ liệu có key duy nhất | Giảm va chạm khi chạy song song | Vẫn cần cleanup nếu state tồn tại lâu |

Test phải tự chuẩn bị fixture và không dựa vào thứ tự thực thi. Với broker, producer gửi thành công không đồng nghĩa listener đã xử lý xong; hãy chờ điều kiện quan sát được bằng Awaitility, latch hoặc một cơ chế đồng bộ có timeout.

## 15. Kiểm soát thời gian chờ và flakiness

Test cần hạ tầng có nhiều nguồn dao động hơn unit test: pull image, startup database, readiness, network scheduling, consumer polling và transaction commit.

Để giảm flakiness:

- Dùng wait strategy thay cho `Thread.sleep(...)` để chờ container sẵn sàng.
- Đặt timeout hữu hạn cho connection, query, request và message consumption.
- Không dùng chung cổng cố định giữa test process.
- Không giả định thứ tự request/message khi test chạy song song.
- Dùng image version cố định.
- Giữ fixture nhỏ và tránh truy vấn dữ liệu không có index trong test.
- Thu thập container logs và test reports khi job thất bại.
- Chỉ retry test ở cấp pipeline khi có chính sách rõ ràng; retry không được che giấu lỗi sản phẩm.

Nếu một test thỉnh thoảng thất bại, hãy ghi lại thời gian, log, request/message và trạng thái container. Đừng gắn `@Disabled` hoặc loại tag chỉ để làm pipeline xanh.

## 16. Dùng thời gian chạy để quyết định nhóm

Tên nhóm không nên là một phán đoán cố định. Hãy đo thời gian thực thi trên CI và xem chi phí khởi tạo hạ tầng.

Một số chỉ số hữu ích:

| Chỉ số | Điều nó cho biết |
|---|---|
| Thời gian tổng của fast task | Độ trễ phản hồi trong vòng lặp developer |
| Thời gian startup Spring context | Chi phí auto-configuration và context cache |
| Thời gian pull/start container | Chi phí hạ tầng trong CI |
| Thời gian mỗi integration test | Test hoặc dịch vụ nào chiếm phần lớn thời gian |
| Tỷ lệ flaky/failure do môi trường | Độ tin cậy của pipeline |
| Tỷ lệ test được chạy trong PR | Mức độ bảo vệ trước merge |

Nếu một test được gắn `integration` nhưng không thực sự cần dịch vụ ngoài, hãy xem lại phạm vi của nó. Ngược lại, nếu test gắn `fast` nhưng cần Docker hoặc server thật, hãy sửa tag và pipeline thay vì chỉ tăng timeout.

## 17. Khi nào tách source set hoặc module riêng?

Tag và task riêng thường đủ. Tách source set hoặc module test riêng khi có một trong các nhu cầu:

- Integration test cần dependency mà fast test không cần.
- Test cần resource, fixture hoặc compiler configuration khác.
- Muốn quản lý lifecycle, reporting hoặc parallelism độc lập.
- Một module ứng dụng có hạ tầng riêng và không nên kéo dependency đó vào module khác.
- Build cần chạy integration suite như một artifact hoặc job độc lập.

Nếu chỉ cần chọn test theo tag, tạo thêm source set sẽ tăng cấu hình classpath, test fixtures và dependency management mà không đem lại nhiều giá trị. Hãy bắt đầu với tag; chỉ mở rộng khi cấu trúc build thực sự cần.

## 18. Checklist tổ chức nhóm test và CI

Trước khi đưa quy ước vào build, nhóm nên trả lời được:

- Test nào chạy trong task mặc định?
- Test nào cần Docker, database, broker hoặc server?
- JUnit tags nào được dùng và ý nghĩa của từng tag là gì?
- Gradle/Maven task nào chạy từng nhóm?
- Integration test nào bắt buộc trước merge?
- CI runner nào có container runtime và quyền pull image?
- Test có độc lập về dữ liệu và có thể chạy song song không?
- Container lifecycle có tương thích Spring context cache không?
- Timeout, readiness và log khi thất bại được quản lý ra sao?
- Thời gian fast feedback và tỷ lệ flaky được theo dõi ở đâu?

## 19. Quy trình triển khai

1. Liệt kê các test hiện có và ghi nhận phụ thuộc thật của từng nhóm.
2. Đánh dấu unit/slice test và integration/e2e test bằng JUnit `@Tag`.
3. Chọn một vocabulary tag ngắn và quy ước rõ ràng.
4. Tạo Gradle task hoặc Maven Surefire/Failsafe configuration để lọc tag.
5. Bảo đảm lệnh fast mặc định không cần hạ tầng ngoài.
6. Tạo CI job có container runtime để chạy integration test bắt buộc.
7. Đặt test dùng database/broker thật ở context nhỏ nhất có thể.
8. Cách ly dữ liệu, queue/topic và lifecycle giữa các test.
9. Thu thập báo cáo, log container và thời gian chạy.
10. Theo dõi flaky test và điều chỉnh nhóm dựa trên chi phí/rủi ro thực tế.

## 20. Tài liệu tham khảo

- [JUnit 5 User Guide — Tagging and Filtering](https://junit.org/junit5/docs/current/user-guide/#writing-tests-tagging-and-filtering): gắn tag và chọn nhóm test.
- [Gradle User Manual — Test Filtering](https://docs.gradle.org/current/userguide/java_testing.html#test_filtering): cấu hình test task và lựa chọn test.
- [Gradle User Manual — JVM Test Suite](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): tổ chức test suite trong Gradle.
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): chạy JUnit Jupiter và lọc tag.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): lifecycle cho integration test.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test slices và test support.
- [Testcontainers for Java](https://java.testcontainers.org/): quản lý database, broker và dịch vụ trong container cho integration test.

Tách test nhanh khỏi test cần hạ tầng giúp developer nhận phản hồi sớm mà vẫn giữ được bằng chứng tích hợp với database, broker và server thật. Hãy phân loại theo phụ thuộc thực tế, gắn tag nhất quán, tạo task riêng và bảo đảm CI có một giai đoạn chịu trách nhiệm chạy mọi test hạ tầng quan trọng trước khi thay đổi được chấp nhận.
