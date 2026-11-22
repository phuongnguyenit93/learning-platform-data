# Kiểm thử PropertySourceLocator với nguồn dữ liệu kiểm soát được

`PropertySourceLocator` là extension point của Spring Cloud Context dùng để tìm thêm `PropertySource` từ nguồn bên ngoài trong luồng bootstrap legacy. Locator nhận `Environment` đang được chuẩn bị và trả về nguồn property phù hợp, chẳng hạn cấu hình theo tên ứng dụng hoặc profile. Khi kiểm thử locator, điều quan trọng là kiểm soát dữ liệu đầu vào để mỗi lần chạy đều cho cùng một kết quả, không phụ thuộc Config Server, database hay mạng bên ngoài.

Bài học thuộc chương **Kiểm thử** của module **SPRING_CLOUD_CORE**. Ta sẽ xây một locator nhỏ đọc dữ liệu từ repository giả lập trong bộ nhớ, kiểm tra cách nó chọn dữ liệu theo application/profile, xác minh property source được trả về, kiểm tra thứ tự ưu tiên và viết integration test cho bootstrap context. Cuối bài sẽ phân biệt cách kiểm thử locator legacy với Spring Boot Config Data.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích hợp đồng của `PropertySourceLocator.locate(Environment)`.
- Phân biệt locator, repository cung cấp dữ liệu và `PropertySource` được trả về.
- Tạo `MockEnvironment` với application name và active profiles xác định.
- Dùng `TestPropertyValues` để cấp property đầu vào cho unit test.
- Viết fake repository trong bộ nhớ thay cho gọi HTTP hoặc database.
- Kiểm tra tên, nội dung và kiểu giá trị trong `MapPropertySource`.
- Kiểm tra trường hợp không có dữ liệu, dữ liệu lỗi và profile khác nhau.
- Xác minh thứ tự ưu tiên khi property source được thêm vào `Environment`.
- Đăng ký locator trong bootstrap context để chạy integration test.
- Hiểu vì sao locator có thể được gọi nhiều lần khi profile được kích hoạt.
- Phân biệt bootstrap legacy với Config Data dùng `spring.config.import`.
- Tránh test phụ thuộc vào số lần gọi, thời gian hoặc trạng thái chia sẻ giữa các test.

## 2. PropertySourceLocator làm nhiệm vụ gì?

`PropertySourceLocator` thuộc Spring Cloud Context và có hợp đồng chính:

~~~java
public interface PropertySourceLocator {

    PropertySource<?> locate(Environment environment);
}
~~~

Locator nhận `Environment` của application context đang được chuẩn bị. Environment đã có các property source thông thường của Spring Boot, vì vậy locator có thể đọc thông tin như:

- `spring.application.name` để chọn cấu hình theo ứng dụng.
- Active profiles để chọn cấu hình theo môi trường.
- Region, tenant hoặc label do ứng dụng định nghĩa.

Locator trả về một `PropertySource<?>`, ví dụ `MapPropertySource` chứa các cặp key/value. Spring Cloud bootstrap xử lý các locator, kết hợp các nguồn được tìm thấy và thêm chúng vào Environment của ứng dụng.

~~~mermaid
flowchart TD
    A[Bootstrap prepares Environment] --> B[PropertySourceLocator]
    B --> C[Read application and profiles]
    C --> D[Controlled repository or external source]
    D --> E[PropertySource result]
    E --> F[Bootstrap combines located sources]
    F --> G[Insert into application Environment]
    G --> H[Application resolves properties]
~~~

Có ba trách nhiệm cần tách biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| `PropertySourceLocator` | Đọc Environment, quyết định cần lấy dữ liệu nào và trả PropertySource |
| Repository/client | Lấy dữ liệu từ file, database, HTTP API, secret store hoặc nguồn khác |
| `PropertySource` | Công bố key/value để Spring Environment tra cứu |

Một unit test tốt có thể kiểm tra locator mà không cần chạy bootstrap context hoặc khởi động dịch vụ bên ngoài.

## 3. Phân biệt bootstrap legacy và Config Data hiện đại

Đây là ranh giới quan trọng khi chọn cách kiểm thử.

### 3.1. PropertySourceLocator thuộc bootstrap legacy

Spring Cloud Context cho phép thêm locator vào bootstrap context thông qua cấu hình `BootstrapConfiguration` được khai báo trong `META-INF/spring.factories`. Bootstrap context là context cha, chuẩn bị các property source trước khi application context chính hoàn tất khởi tạo.

Ví dụ metadata:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.example.bootstrap.CustomPropertySourceLocator
~~~

Để kích hoạt bootstrap legacy, ứng dụng thường thêm `spring-cloud-starter-bootstrap` hoặc bật bootstrap bằng property hệ thống/môi trường theo tài liệu của phiên bản đang dùng.

### 3.2. Config Data là cơ chế mặc định cho Config Server

Spring Boot 2.4 giới thiệu Config Data. Spring Cloud Config Client hiện dùng cơ chế này làm cách kết nối mặc định:

~~~properties
spring.config.import=optional:configserver:
~~~

Với luồng Config Data, Spring Boot sử dụng `ConfigDataLocationResolver` và `ConfigDataLoader` để nạp cấu hình. Một test nhắm vào luồng này nên kiểm tra Config Data integration, chẳng hạn bằng HTTP server giả lập trả response của Config Server. Nó không phải bài test trực tiếp cho `PropertySourceLocator`.

### 3.3. Chọn đúng test theo extension point

| Mục tiêu | Cơ chế cần kiểm thử |
| --- | --- |
| Custom source được nạp qua bootstrap context | `PropertySourceLocator` |
| Config Server được nạp bằng `spring.config.import` | Config Data resolver/loader của Config Client |
| Logic chọn app/profile và tạo map key/value | Unit test locator với `MockEnvironment` |
| Locator được đăng ký và property xuất hiện trong application context | Bootstrap integration test |
| HTTP response của Config Server được parse đúng | Test client/Config Data với HTTP server giả lập |

Không dùng kết quả unit test của locator để kết luận Config Data loader hoạt động đúng, và cũng không cần khởi động Config Server thật chỉ để kiểm tra một locator trả về map.

## 4. Thiết kế nguồn dữ liệu kiểm soát được

Giả sử mỗi ứng dụng có một bộ cấu hình riêng theo profile:

| Application | Profile | Property | Value |
| --- | --- | --- | --- |
| `orders-service` | `test` | `feature.checkout.enabled` | `true` |
| `orders-service` | `test` | `limits.pool-size` | `12` |
| `orders-service` | `production` | `feature.checkout.enabled` | `false` |
| `catalog-service` | `test` | `catalog.cache.enabled` | `true` |

Test cần trả về đúng bộ dữ liệu dựa trên Environment. Ta có thể tạo một repository interface nhỏ:

~~~java
import java.util.List;
import java.util.Map;

public interface ControlledConfigRepository {

    Map<String, Object> load(String application, List<String> profiles);
}
~~~

Trong production, implementation có thể đọc database hoặc API. Trong unit test, thay bằng một lambda hoặc fake repository sử dụng map bất biến.

### 4.1. Fake repository trong bộ nhớ

~~~java
import java.util.List;
import java.util.Map;

public final class InMemoryConfigRepository
        implements ControlledConfigRepository {

    private final Map<String, Map<String, Object>> fixtures;

    public InMemoryConfigRepository(
            Map<String, Map<String, Object>> fixtures) {
        this.fixtures = Map.copyOf(fixtures);
    }

    @Override
    public Map<String, Object> load(
            String application, List<String> profiles) {

        String key = application + ":" + String.join(",", profiles);
        return fixtures.getOrDefault(key, Map.of());
    }
}
~~~

Fixture dùng key có cấu trúc rõ ràng, nên test không phải dựa vào thời gian, biến môi trường của máy phát triển hoặc dịch vụ đang chạy.

Ví dụ tạo repository:

~~~java
Map<String, Map<String, Object>> fixtures = Map.of(
        "orders-service:test",
        Map.of(
                "feature.checkout.enabled", true,
                "limits.pool-size", 12),
        "orders-service:production",
        Map.of("feature.checkout.enabled", false),
        "catalog-service:test",
        Map.of("catalog.cache.enabled", true));

ControlledConfigRepository repository =
        new InMemoryConfigRepository(fixtures);
~~~

Nếu locator hỗ trợ nhiều profile, quy ước thứ tự profile cần được xác định rõ. Ví dụ, profile được xét theo thứ tự trong Environment và profile đứng sau có thể ghi đè key của profile đứng trước. Test nên ghi rõ quy ước đó bằng fixture riêng.

## 5. Viết locator có thể kiểm thử

Implementation dưới đây chỉ làm ba việc: đọc application name, đọc active profiles và yêu cầu repository cung cấp map. Nó không tạo HTTP client hoặc mở kết nối mạng trong phương thức `locate`.

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

public final class ControlledPropertySourceLocator
        implements PropertySourceLocator {

    private final ControlledConfigRepository repository;

    public ControlledPropertySourceLocator(
            ControlledConfigRepository repository) {
        this.repository = repository;
    }

    @Override
    public PropertySource<?> locate(Environment environment) {
        String application = environment.getProperty(
                "spring.application.name", "application");

        String[] activeProfiles = environment.getActiveProfiles();
        List<String> profiles = activeProfiles.length == 0
                ? List.of("default")
                : Arrays.asList(activeProfiles);

        Map<String, Object> values =
                repository.load(application, profiles);

        if (values == null || values.isEmpty()) {
            return null;
        }

        Map<String, Object> snapshot =
                Collections.unmodifiableMap(new LinkedHashMap<>(values));

        String sourceName = "controlled:"
                + application + ":" + String.join(",", profiles);

        return new MapPropertySource(sourceName, snapshot);
    }
}
~~~

Có một số quyết định có chủ đích:

- Tên ứng dụng có fallback để locator vẫn có thể xử lý môi trường chưa khai báo application name.
- Không có active profile thì dùng profile mặc định đã được quy ước là `default` trong ví dụ.
- Map được copy trước khi trả về, tránh test hoặc repository sửa map gốc sau khi locator đã tạo property source.
- Tên property source có application/profile để dễ đọc log và chẩn đoán.
- Không có dữ liệu thì trả `null` để bootstrap bỏ qua locator đó. Nếu nghiệp vụ cần phân biệt “không có cấu hình” và “cấu hình rỗng”, hãy định nghĩa hợp đồng rõ ràng và test cả hai trường hợp.

Tên fallback profile trong ví dụ là quy ước của repository. Trong một ứng dụng thật, hãy quyết định dùng `Environment.getDefaultProfiles()` hay quy tắc riêng của hệ thống, rồi áp dụng thống nhất cho locator và test.

## 6. Unit test với MockEnvironment

`MockEnvironment` cho phép tạo Environment kiểm soát được mà không cần khởi tạo Spring Boot application context. `TestPropertyValues` là tiện ích để thêm các property key/value vào Environment trong test.

### 6.1. Kiểm tra locator chọn đúng application và profile

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.core.env.PropertySource;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class ControlledPropertySourceLocatorTests {

    @Test
    void locatesPropertiesForApplicationAndProfile() {
        Map<String, Map<String, Object>> fixtures = Map.of(
                "orders-service:test",
                Map.of(
                        "feature.checkout.enabled", true,
                        "limits.pool-size", 12));

        ControlledConfigRepository repository =
                new InMemoryConfigRepository(fixtures);
        ControlledPropertySourceLocator locator =
                new ControlledPropertySourceLocator(repository);

        MockEnvironment environment = new MockEnvironment();
        TestPropertyValues.of(
                "spring.application.name=orders-service")
                .applyTo(environment);
        environment.setActiveProfiles("test");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source).isNotNull();
        assertThat(source.getName())
                .isEqualTo("controlled:orders-service:test");
        assertThat(source.getProperty("feature.checkout.enabled"))
                .isEqualTo(true);
        assertThat(source.getProperty("limits.pool-size"))
                .isEqualTo(12);
    }
}
~~~

Test này kiểm tra hợp đồng chính của locator: application name và profile trong Environment quyết định fixture nào được trả về. Nó không cần chạy Config Server hoặc database.

### 6.2. Kiểm tra hai ứng dụng không dùng chung dữ liệu

Đặt method test này trong cùng test class ở phần 6.1. Mỗi test tự tạo fixture để không phụ thuộc trạng thái của test khác.

~~~java
@Test
void returnsDifferentPropertiesForDifferentApplications() {
    Map<String, Map<String, Object>> fixtures = Map.of(
            "orders-service:test",
            Map.of("feature.enabled", true),
            "catalog-service:test",
            Map.of("feature.enabled", false));

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(
                    new InMemoryConfigRepository(fixtures));

    MockEnvironment ordersEnvironment = new MockEnvironment();
    ordersEnvironment.setProperty(
            "spring.application.name", "orders-service");
    ordersEnvironment.setActiveProfiles("test");

    MockEnvironment catalogEnvironment = new MockEnvironment();
    catalogEnvironment.setProperty(
            "spring.application.name", "catalog-service");
    catalogEnvironment.setActiveProfiles("test");

    PropertySource<?> orders = locator.locate(ordersEnvironment);
    PropertySource<?> catalog = locator.locate(catalogEnvironment);

    assertThat(orders.getProperty("feature.enabled")).isEqualTo(true);
    assertThat(catalog.getProperty("feature.enabled")).isEqualTo(false);
}
~~~

Test này giúp phát hiện lỗi dùng nhầm cache key chỉ theo profile hoặc chỉ theo application. Nếu repository cache kết quả, cache key cần bao gồm mọi yếu tố làm thay đổi cấu hình, chẳng hạn application, profile, tenant và label.

### 6.3. Kiểm tra profile khác nhau

Đây cũng là một method độc lập trong cùng test class:

~~~java
@Test
void loadsProfileSpecificValues() {
    Map<String, Map<String, Object>> fixtures = Map.of(
            "orders-service:test",
            Map.of("feature.checkout.enabled", true),
            "orders-service:production",
            Map.of("feature.checkout.enabled", false));

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(
                    new InMemoryConfigRepository(fixtures));

    MockEnvironment testEnvironment = new MockEnvironment();
    testEnvironment.setProperty(
            "spring.application.name", "orders-service");
    testEnvironment.setActiveProfiles("test");

    MockEnvironment productionEnvironment = new MockEnvironment();
    productionEnvironment.setProperty(
            "spring.application.name", "orders-service");
    productionEnvironment.setActiveProfiles("production");

    assertThat(locator.locate(testEnvironment)
            .getProperty("feature.checkout.enabled")).isEqualTo(true);
    assertThat(locator.locate(productionEnvironment)
            .getProperty("feature.checkout.enabled")).isEqualTo(false);
}
~~~

Không dùng profile thật của máy chạy test. Luôn đặt profile trực tiếp trên MockEnvironment để test không bị ảnh hưởng bởi biến môi trường hoặc tham số JVM.

## 7. Kiểm tra trường hợp không có dữ liệu và lỗi nguồn

Một locator cần có hành vi xác định khi repository không có cấu hình hoặc gặp lỗi. Không nên để test chỉ kiểm tra trường hợp thành công.

### 7.1. Không có cấu hình cho ứng dụng

~~~java
@Test
void returnsNullWhenRepositoryHasNoMatchingConfiguration() {
    ControlledConfigRepository repository =
            (application, profiles) -> Map.of();

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment environment = new MockEnvironment();
    environment.setProperty(
            "spring.application.name", "unknown-service");
    environment.setActiveProfiles("test");

    assertThat(locator.locate(environment)).isNull();
}
~~~

Nếu chính sách của ứng dụng yêu cầu không tìm thấy cấu hình là lỗi khởi động, locator hoặc repository nên ném exception có ý nghĩa. Không nên âm thầm trả map rỗng khi việc thiếu cấu hình khiến ứng dụng chạy sai hoặc không an toàn.

### 7.2. Nguồn dữ liệu gặp lỗi

Đặt method này trong test class và giữ static import của AssertJ ở đầu file:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void propagatesRepositoryFailure() {
    ControlledConfigRepository repository =
            (application, profiles) -> {
                throw new IllegalStateException("controlled repository failure");
            };

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment environment = new MockEnvironment();
    environment.setProperty(
            "spring.application.name", "orders-service");

    assertThatThrownBy(() -> locator.locate(environment))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("controlled repository failure");
}
~~~

Nếu implementation production chuyển lỗi thành exception riêng, test exception type và mã lỗi của ứng dụng đó. Chỉ kiểm tra exception quá chung có thể khiến lỗi timeout, lỗi xác thực và dữ liệu không hợp lệ bị đánh đồng.

### 7.3. Phân biệt không có dữ liệu với dữ liệu rỗng

Hai tình huống này có thể mang ý nghĩa nghiệp vụ khác nhau:

| Tình huống | Ý nghĩa có thể có | Hành vi đề xuất |
| --- | --- | --- |
| Repository không tìm thấy ứng dụng/profile | Chưa có cấu hình hoặc sai định danh | Trả `null` nếu nguồn là optional; ném lỗi nếu bắt buộc |
| Repository tìm thấy cấu hình nhưng map rỗng | Cấu hình rỗng được lưu có chủ đích | Giữ một kết quả rỗng hoặc biểu diễn riêng theo hợp đồng |
| Repository không truy cập được | Lỗi hạ tầng hoặc xác thực | Ném lỗi có nguyên nhân rõ ràng, không giả thành dữ liệu rỗng |

Test phải thể hiện chính sách đã chọn. Nếu không, một thay đổi từ “repository unavailable” sang “return empty map” có thể làm ứng dụng khởi động với giá trị mặc định ngoài ý muốn.

## 8. Kiểm tra nội dung và thứ tự ưu tiên PropertySource

`PropertySourceLocator` chỉ trả về một property source; bootstrap process mới chịu trách nhiệm thêm nguồn đó vào Environment. Khi kiểm tra locator riêng, ta có thể thêm property source thủ công để xác minh quy tắc tra cứu của Spring.

### 8.1. Property source đứng trước có độ ưu tiên cao hơn

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

@Test
void firstPropertySourceWinsWhenKeysOverlap() {
    MockEnvironment environment = new MockEnvironment();

    environment.getPropertySources().addLast(
            new MapPropertySource(
                    "local",
                    Map.of("feature.mode", "local")));

    environment.getPropertySources().addFirst(
            new MapPropertySource(
                    "controlled-remote",
                    Map.of("feature.mode", "remote")));

    assertThat(environment.getProperty("feature.mode"))
            .isEqualTo("remote");
}
~~~

`addFirst` đưa property source lên đầu danh sách, vì vậy key trùng được đọc từ nguồn đó trước. `addLast` đặt nguồn ở cuối, chỉ được dùng khi các nguồn trước không cung cấp key.

Đây là test quy tắc của `MutablePropertySources`. Nó chưa chứng minh bootstrap legacy thực tế chèn nguồn vào vị trí nào; muốn xác minh thứ tự bootstrap, hãy chạy integration test với bootstrap context.

### 8.2. Kiểm tra source name và key trùng

Tên property source cần ổn định và duy nhất trong phạm vi context. Spring quản lý các nguồn theo tên; nếu nhiều locator dùng cùng một tên, một nguồn có thể bị thay thế hoặc bị xử lý khác với điều người viết test mong đợi.

Nên kiểm tra:

- Source name có bao gồm namespace của nguồn, application hoặc tenant cần thiết không.
- Hai locator độc lập có tạo tên trùng nhau không.
- Khi hai source cùng cung cấp một key, source nào được ưu tiên.
- Khi một source bị bỏ khỏi Environment, giá trị có trở về nguồn thấp hơn như mong muốn không.

Không kiểm tra thứ tự bằng cách so sánh toàn bộ danh sách property source của một Spring Boot context nếu test không thực sự cần hợp đồng đó. Các property source hệ thống có thể thay đổi theo phiên bản và môi trường.

### 8.3. Nhiều locator và thứ tự

Bootstrap process sắp xếp các locator theo order trước khi thu thập property source. Nếu ứng dụng có nhiều locator, hãy dùng `@Order` hoặc `Ordered` để khai báo thứ tự có chủ đích, sau đó viết integration test cho key trùng giữa hai nguồn.

~~~java
import org.springframework.core.annotation.Order;

@Order(10)
public class TenantPropertySourceLocator
        implements PropertySourceLocator {
    // locate(...)
}
~~~

Không dựa vào thứ tự tình cờ của component scan hoặc thứ tự khởi tạo bean. Khi hai nguồn cùng sở hữu một key, thứ tự phải là một phần của thiết kế và test.

## 9. Integration test với bootstrap context

Unit test gọi trực tiếp `locate` không xác minh rằng locator được phát hiện trong bootstrap context. Để kiểm tra đường đi đầy đủ, cần đăng ký một cấu hình test-only và xác nhận property xuất hiện trong Environment của application context.

### 9.1. Thêm bootstrap starter trong test runtime

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
    <scope>test</scope>
</dependency>
~~~

Dependency này chỉ cần thiết khi test chủ đích dùng bootstrap legacy. Quản lý version bằng Spring Cloud BOM tương thích với Spring Boot của dự án.

### 9.2. Đăng ký test bootstrap configuration

Tạo file:

~~~text
src/test/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.example.testbootstrap.TestPropertySourceLocatorConfiguration
~~~

Đặt class bootstrap test ở package `com.example.testbootstrap`, ngoài phạm vi component scan của ứng dụng. Ví dụ, ứng dụng chính có thể nằm trong `com.example.application`. Tài liệu Spring Cloud cảnh báo không để cấu hình bootstrap bị component scan nhầm vào application context chính.

### 9.3. Locator fixture cho integration test

~~~java
package com.example.testbootstrap;

import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

@Configuration(proxyBeanMethods = false)
public class TestPropertySourceLocatorConfiguration
        implements PropertySourceLocator {

    @Override
    public PropertySource<?> locate(Environment environment) {
        return new MapPropertySource(
                "test-controlled-source",
                Map.of(
                        "test.remote.feature", "enabled",
                        "test.remote.limit", 17));
    }
}
~~~

Fixture trả về dữ liệu cố định, không gọi HTTP hoặc database. Trong test thực tế, có thể inject repository fake vào locator nếu cần kiểm tra lựa chọn theo application/profile.

### 9.4. Kiểm tra property trong application context

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PropertySourceLocatorBootstrapIntegrationTests {

    @Autowired
    private Environment environment;

    @Test
    void exposesLocatedPropertiesToApplicationEnvironment() {
        assertThat(environment.getProperty("test.remote.feature"))
                .isEqualTo("enabled");
        assertThat(environment.getProperty("test.remote.limit", Integer.class))
                .isEqualTo(17);
    }
}
~~~

Test này đi qua bootstrap discovery, tạo property source và chuyển giá trị sang application Environment. Nếu unit test pass nhưng integration test fail, hãy kiểm tra dependency bootstrap, file metadata, package scan, thứ tự khởi tạo và điều kiện kích hoạt bootstrap.

## 10. Locator có thể được gọi nhiều lần

Từ Spring Cloud 2022.0.3, `PropertySourceLocators` có thể được gọi hai lần:

1. Lần đầu lấy cấu hình chưa gắn active profiles. Cấu hình đó có thể kích hoạt thêm profile thông qua `spring.profiles.active`.
2. Sau khi application context chính bắt đầu, locator được gọi lại với các active profiles để lấy thêm cấu hình dành riêng cho profile.

Vì vậy:

- Unit test trực tiếp `locate(environment)` chỉ kiểm tra một trạng thái Environment tại một thời điểm.
- Integration test không nên mặc định locator chỉ chạy đúng một lần.
- Không dùng bộ đếm static hoặc side effect không idempotent để quyết định dữ liệu.
- Không tạo resource dùng một lần ở lần gọi đầu nếu lần gọi sau cần dùng lại.
- Nếu có cache, cache key phải bao gồm profile và mọi yếu tố khác ảnh hưởng kết quả.

### 10.1. Test từng giai đoạn profile riêng

Có thể mô phỏng hai trạng thái bằng hai MockEnvironment:

~~~java
@Test
void supportsDefaultAndProfileSpecificLookups() {
    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment initialEnvironment = new MockEnvironment();
    initialEnvironment.setProperty(
            "spring.application.name", "orders-service");

    MockEnvironment profileEnvironment = new MockEnvironment();
    profileEnvironment.setProperty(
            "spring.application.name", "orders-service");
    profileEnvironment.setActiveProfiles("production");

    PropertySource<?> initial =
            locator.locate(initialEnvironment);
    PropertySource<?> production =
            locator.locate(profileEnvironment);

    assertThat(initial.getProperty("feature.checkout.enabled"))
            .isEqualTo(true);
    assertThat(production.getProperty("feature.checkout.enabled"))
            .isEqualTo(false);
}
~~~

Ví dụ giả định repository có fixture cho profile mặc định và `production`. Trong integration test, hãy kiểm tra giá trị cuối cùng trong Environment và không khóa test vào số lần gọi nội bộ.

## 11. Test tính bất biến và tránh rò rỉ trạng thái

Property source có thể tồn tại lâu hơn lần gọi locator. Nếu map bên trong bị sửa sau khi trả về, giá trị mà ứng dụng đọc có thể thay đổi ngoài dự kiến.

### 11.1. Kiểm tra snapshot không đổi theo map gốc

~~~java
@Test
void returnedPropertySourceUsesASnapshotOfRepositoryData() {
    Map<String, Object> sourceData = new LinkedHashMap<>();
    sourceData.put("feature.mode", "initial");

    ControlledConfigRepository repository =
            (application, profiles) -> sourceData;

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment environment = new MockEnvironment();
    PropertySource<?> source = locator.locate(environment);

    sourceData.put("feature.mode", "changed");

    assertThat(source.getProperty("feature.mode"))
            .isEqualTo("initial");
}
~~~

Test này chỉ đúng khi locator copy dữ liệu trước khi tạo `MapPropertySource`, như implementation ở phần 5.

### 11.2. Tránh static mutable fixture

Không chia sẻ một map mutable giữa các test. Nếu test A sửa fixture và test B chạy sau, kết quả phụ thuộc thứ tự test hoặc chạy song song.

Ưu tiên:

- Tạo fake repository mới trong từng test.
- Dùng `Map.of(...)` cho fixture bất biến.
- Không lưu active profile hoặc application name trong static field.
- Không dùng một singleton fake repository có state thay đổi giữa test.
- Nếu dùng Mockito, reset hoặc tạo mock mới trong mỗi test.

### 11.3. Không giữ tài nguyên đã đóng trong PropertySource

Một PropertySource có thể còn được truy cập sau khi bootstrap context hoàn tất. Không nên để PropertySource phụ thuộc vào HTTP client hoặc database connection mà locator đóng ngay khi kết thúc bootstrap. Nếu property source cần truy vấn dữ liệu động, quản lý lifecycle client theo cách phù hợp hoặc lưu snapshot dữ liệu đã nạp vào nguồn bất biến.

## 12. Kiểm thử repository/client mà không phụ thuộc dịch vụ thật

Nếu repository gọi HTTP hoặc database, hãy tách test thành hai lớp:

| Lớp test | Đối tượng | Công cụ phù hợp |
| --- | --- | --- |
| Unit test locator | Chọn app/profile và tạo PropertySource | `MockEnvironment`, fake repository |
| Unit test repository adapter | Parse response, map key/value, xử lý lỗi | Mock HTTP client, stub DAO |
| Integration test adapter | Request/response HTTP thật trong process test | MockWebServer hoặc HTTP server giả lập |
| Bootstrap integration | Locator được phát hiện và property vào Environment | `spring-cloud-starter-bootstrap` test scope |

Không nên để unit test locator gọi Config Server hoặc database thật. Những phụ thuộc đó làm test chậm, khó tái lập và dễ fail do môi trường.

### 12.1. Kiểm tra HTTP adapter

Nếu repository dùng HTTP, test adapter riêng với server giả lập:

- Trả response có key/value xác định.
- Trả HTTP 404 khi application/profile không tồn tại.
- Trả HTTP 401/403 khi credentials sai.
- Trả HTTP 500 hoặc timeout để xác minh lỗi hạ tầng.
- Trả payload không hợp lệ để xác minh lỗi parse.

Sau đó dùng fake adapter trong unit test locator. Như vậy, test locator không cần biết HTTP status code hoặc JSON schema của dịch vụ bên ngoài.

### 12.2. Kiểm tra dữ liệu nhạy cảm

Nếu locator đọc secret, test chỉ dùng giá trị giả. Không đưa credential thật vào fixture, assertion message hoặc log. Không in toàn bộ `PropertySource` ra console vì nó có thể chứa mật khẩu, token hoặc khóa.

## 13. Những điều cần kiểm tra trong test suite

| Nhóm | Ca kiểm thử |
| --- | --- |
| Định tuyến dữ liệu | Đúng application name, profile, tenant hoặc label |
| Kiểu dữ liệu | Boolean, number, list hoặc chuỗi được giữ đúng kiểu |
| Dữ liệu trống | Không tìm thấy source và source rỗng được xử lý theo hợp đồng |
| Lỗi | Timeout, xác thực, parse lỗi và repository exception |
| Property source | Source name ổn định, key/value đúng, snapshot không bị mutate |
| Precedence | Key trùng được giải quyết theo thứ tự dự kiến |
| Profiles | Default profile và từng active profile trả về cấu hình phù hợp |
| Bootstrap | Locator được đăng ký từ test metadata và property xuất hiện trong Environment |
| Nhiều locator | Thứ tự locator rõ ràng, key trùng có kết quả xác định |
| Lặp lời gọi | Không phụ thuộc số lần gọi cố định và không tạo side effect trùng |
| Isolation | Test chạy độc lập và chạy song song không làm thay đổi fixture của nhau |

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Unit test không tìm thấy property | Locator trả `null`, fixture key sai hoặc profile không khớp | Kiểm tra application name, active profiles và repository key |
| Property source đúng nhưng Environment trả giá trị khác | Có property source khác ưu tiên cao hơn | In tên và thứ tự nguồn liên quan trong test |
| Integration test không thấy bootstrap source | Thiếu bootstrap starter hoặc metadata sai | Kiểm tra test runtime dependency và key `BootstrapConfiguration` |
| Locator chạy hai lần | Spring Cloud từ 2022.0.3 hỗ trợ fetch trước và sau profile activation | Không assert số lần gọi; assert kết quả cuối cùng |
| Test pass riêng nhưng fail khi chạy cả suite | Fixture mutable hoặc context cache chia sẻ trạng thái | Tạo fake mới theo test và loại bỏ static mutable data |
| Dữ liệu profile production xuất hiện trong test | Test kế thừa profile từ JVM/CI | Đặt active profile tường minh trên MockEnvironment |
| Remote value không ghi đè local value | Property source được chèn sai vị trí hoặc quyền override khác cấu hình | Kiểm tra bootstrap ordering và override policy |
| Config Server import không gọi locator | Ứng dụng đang dùng Config Data thay cho bootstrap legacy | Kiểm thử Config Data resolver/loader và `spring.config.import` |
| PropertySource đọc lỗi sau bootstrap | Client/resource đã bị đóng nhưng source vẫn dùng lại | Trả snapshot dữ liệu hoặc quản lý resource theo lifecycle phù hợp |

### 14.1. Quy trình chẩn đoán

1. Gọi locator trực tiếp với MockEnvironment có application name và profile xác định.
2. Kiểm tra PropertySource trả về có null hay không.
3. Kiểm tra source name và các key/value.
4. Thêm source vào MockEnvironment để xác minh precedence.
5. Nếu unit test pass, kiểm tra metadata bootstrap và test dependency.
6. Xác minh ứng dụng đang dùng bootstrap legacy hay Config Data.
7. Kiểm tra log bootstrap, active profiles và property source ordering.
8. Chạy lại test độc lập để phát hiện fixture hoặc cache dùng chung.

## 15. Bài tập thực hành

### Bài 1 — Locator với fixture xác định

Viết một repository giả lập có cấu hình cho hai application và hai profile. Viết locator chọn đúng fixture dựa trên Environment.

### Bài 2 — Unit test với MockEnvironment

Viết test cho application name, active profile, property source name và hai giá trị có kiểu Boolean/Integer. Thêm test không có dữ liệu.

### Bài 3 — Kiểm tra precedence

Tạo local property source và locator property source cùng chứa key `feature.mode`. Thêm chúng theo hai thứ tự khác nhau và xác minh giá trị Environment trả về.

### Bài 4 — Bootstrap integration

Đăng ký test bootstrap configuration trong `src/test/resources/META-INF/spring.factories`. Dùng `spring-cloud-starter-bootstrap` trong test runtime và xác minh property xuất hiện trong application Environment.

### Bài 5 — Profile activation hai giai đoạn

Tạo fixture default và production. Kiểm tra locator với Environment chưa có active profile và Environment có profile production. Integration test chỉ xác nhận giá trị cuối cùng, không giả định số lần locator được gọi.

### Bài 6 — Phân biệt Config Data

Viết ghi chú hoặc test riêng mô tả cách kiểm thử `spring.config.import=optional:configserver:`. Xác định phần nào thuộc Config Data resolver/loader và phần nào thuộc PropertySourceLocator legacy.

**Tiêu chí hoàn thành:** bạn có thể kiểm thử locator với dữ liệu hoàn toàn kiểm soát được, xác minh application/profile và precedence, xử lý dữ liệu trống/lỗi, và chứng minh bootstrap context nạp đúng property source.

## 16. Tổng kết

`PropertySourceLocator` là extension point của bootstrap legacy: nó nhận `Environment` và trả về `PropertySource<?>`. Cách kiểm thử đơn giản và ổn định là tạo `MockEnvironment`, đặt application name/active profiles, rồi dùng fake repository trong bộ nhớ để trả map cố định. Unit test kiểm tra lựa chọn dữ liệu, source name, key/value, trường hợp trống và lỗi mà không cần gọi dịch vụ bên ngoài.

Để kiểm tra thứ tự ưu tiên, hãy xác minh cách `MutablePropertySources` giải quyết key trùng và sau đó chạy bootstrap integration test để kiểm tra nguồn thực tế được chèn vào Environment. Đăng ký locator legacy qua `BootstrapConfiguration` trong `spring.factories`; test runtime cần bật bootstrap. Từ Spring Cloud 2022.0.3, locator có thể được gọi trước và sau khi profile được kích hoạt, vì vậy test phải tập trung vào kết quả cấu hình thay vì một số lần gọi cố định.

Spring Cloud Config hiện dùng Config Data qua `spring.config.import` làm cách mặc định. Khi ứng dụng dùng luồng đó, hãy kiểm thử Config Data resolver/loader. Chỉ kiểm thử `PropertySourceLocator` khi ứng dụng thực sự dùng bootstrap extension legacy hoặc có custom locator được đăng ký trong bootstrap context.

## Tài liệu tham khảo

- [Spring Cloud Commons 5.0.4 — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, custom `PropertySourceLocator`, đăng ký qua `spring.factories`, precedence và việc locator được gọi hai lần từ Spring Cloud 2022.0.3.
- [Spring Cloud Config 5.0.6 — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data qua `spring.config.import` và cách bật config-first bootstrap legacy.
- [Spring Boot 4.1.2 — Test Utilities](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html): `MockEnvironment` và `TestPropertyValues` để kiểm soát property trong test.
- [PropertySourceBootstrapConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/bootstrap/config/PropertySourceBootstrapConfiguration.java): cách bootstrap thu thập locator, sắp xếp và chèn property source.
- [ContextRefresherTests source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/test/java/org/springframework/cloud/context/refresh/ContextRefresherTests.java): ví dụ test Spring Cloud dùng `PropertySourceLocator` và dữ liệu map.

Hãy kiểm tra release train Spring Cloud và Spring Boot BOM của dự án. Bootstrap legacy, Config Data và các API kiểm thử có thể khác nhau giữa các thế hệ phiên bản.
