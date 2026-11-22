# Chọn mức kiểm thử cấu hình: đối tượng, Binder, ApplicationContextRunner và ứng dụng đầy đủ

## 1. Mục tiêu của bài học

Khi dùng Spring Boot Externalized Configuration, một ứng dụng có thể nhận các thuộc tính từ **application.yml**, **application.properties**, file theo profile, biến môi trường, JVM system properties, tham số CLI, Config Data imports và các PropertySource khác. Các thuộc tính này được tra cứu, chuyển đổi kiểu, liên kết với **@ConfigurationProperties**, kiểm tra hợp lệ và cuối cùng ảnh hưởng đến cách các bean được tạo.

Một bài kiểm thử cấu hình có thể nhắm vào nhiều vấn đề khác nhau:

- Một record cấu hình có từ chối giá trị âm, tên rỗng hoặc cấu trúc vô lý không?
- Spring Boot Binder có chuyển **5s** thành **Duration** và ánh xạ **read-timeout** sang **readTimeout** đúng không?
- Khi cấu hình sai, một bean **@Validated @ConfigurationProperties** có làm ApplicationContext thất bại không?
- **@ConditionalOnProperty** có tạo hoặc bỏ bean theo feature flag đúng không?
- Khi bật profile prod, import file ngoài hoặc truyền CLI, ứng dụng hoàn chỉnh có nhận giá trị đúng không?
- Một **EnvironmentPostProcessor** đăng ký bằng spring.factories có thực sự được gọi trong quá trình bootstrap không?
- Một datasource hoặc HTTP client có thật sự nhận cấu hình sau auto-configuration và khởi động được không?

Các câu hỏi này **không nên được kiểm thử bằng đúng một kỹ thuật**. Nếu chỉ kiểm tra bất biến của một record, khởi động toàn ứng dụng là quá nặng. Nếu muốn chứng minh một EnvironmentPostProcessor được SpringApplication khám phá qua classpath, một unit test gọi trực tiếp class đó lại chưa đủ.

Bài này xây dựng chiến lược kiểm thử theo bốn mức:

1. **Kiểm thử đối tượng thuần Java**: nhanh nhất, kiểm tra constructor, default/invariant và Bean Validation được gọi tường minh.
2. **Kiểm thử Spring Boot Binder**: kiểm tra chuyển property names, cấu trúc và kiểu dữ liệu thành object; không cần khởi động ApplicationContext.
3. **ApplicationContextRunner**: kiểm tra vòng đời đăng ký configuration-properties bean, validation tích hợp, conditional auto-configuration và tác động của các property lên một context nhỏ.
4. **Kiểm thử ứng dụng đầy đủ**: khởi động bằng SpringApplication/@SpringBootTest để kiểm tra cấu hình, profile, Config Data, extension bootstrap và tích hợp runtime trong bối cảnh gần thực tế.

Mục tiêu không phải chọn mức “mạnh nhất” cho mọi case. Mục tiêu là **dùng mức thấp nhất vẫn chứng minh được hành vi đang được yêu cầu**, sau đó bổ sung một số test tích hợp có giá trị ở những ranh giới thực sự cần thiết.

Các ví dụ tập trung vào Spring Boot 3.x, Java 17+, JUnit Jupiter và AssertJ. Với Spring Boot 4.x, hãy đối chiếu package/API của module test và các extension point tương ứng trong phiên bản dự án trước khi sao chép nguyên snippet.

---

## 2. So sánh bốn mức kiểm thử

| Mức | Khởi tạo gì? | Có kiểm tra Binder? | Có kiểm tra Spring bean lifecycle? | Có kiểm tra app bootstrap thực? | Trường hợp nên dùng |
| --- | --- | --- | --- | --- | --- |
| Đối tượng | Java object và validator nếu cần | Không | Không | Không | Invariant, default, defensive copy, logic validation độc lập |
| Binder | Binder + ConfigurationPropertySource thử nghiệm | Có | Không | Không | Relaxed binding, nested, Duration, List/Map, lỗi chuyển kiểu |
| ApplicationContextRunner | ApplicationContext nhỏ theo test config | Có khi bean được đăng ký đúng | Có | Không đầy đủ | @ConfigurationProperties, @Validated, @ConditionalOnProperty, auto-configuration cục bộ |
| Ứng dụng đầy đủ | SpringApplication/ApplicationContext của ứng dụng | Có | Có | Có | Profile, Config Data imports, EPP discovery, wiring toàn hệ thống, hạ tầng tích hợp |

**Quy tắc chọn mức:** Một bài test chỉ được coi là chứng minh đúng điều gì đó khi cơ chế liên quan **thực sự được kích hoạt** trong test.

Ví dụ, trực tiếp gọi **new GatewayProperties(...)** không chứng minh YAML được nạp hay bean được validate tự động. Gọi **binder.bind(...)** không chứng minh Spring biết đăng ký bean cấu hình. Tạo ApplicationContextRunner với thuộc tính thủ công không chứng minh file application-prod.yml của ứng dụng được nạp theo đúng thứ tự. Ngược lại, @SpringBootTest không cần thiết cho việc kiểm tra **Duration.isPositive()** hoặc một constructor có ném IllegalArgumentException không.

### 2.1. Phạm vi chứng minh khác thời gian chạy

Một phép kiểm thử nặng hơn có thể bao trùm nhiều thành phần, nhưng khi thất bại thường khó tìm nguyên nhân hơn:

~~~text
Object test
  -> Bản thân Java object có đúng?

Binder test
  -> Nguồn thuộc tính có được chuyển thành object đúng?

ApplicationContextRunner
  -> Bean/auto-configuration có được đăng ký, bind và validate đúng?

Full Spring Boot application
  -> Toàn bộ bootstrap, Config Data và wiring có vận hành đúng?
~~~

Không nên xem bốn mức là các bài test trùng nhau phải viết đủ cho từng trường. Chọn **một mức làm nơi kiểm tra chi tiết**, các mức cao hơn chỉ xác nhận những mối ghép quan trọng.

---

## 3. Một mô hình cấu hình dùng xuyên suốt

Giả sử ứng dụng có một gateway với timeout, pool connection và danh sách endpoint:

~~~yaml
app:
  gateway:
    timeout: 5s
    pool:
      max-connections: 24
      enabled: true
    endpoints:
      - host: primary.example.test
        port: 8080
      - host: backup.example.test
        port: 8081
~~~

Mô hình Java:

~~~java
package example.config;

import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        @NotNull Duration timeout,
        @Valid @NotNull Pool pool,
        @NotEmpty List<@NotNull @Valid Endpoint> endpoints
) {
    public record Pool(
            @Min(1) int maxConnections,
            boolean enabled
    ) {}

    public record Endpoint(
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Các property quan trọng:

| Property canonical | Java component | Kiểu |
| --- | --- | --- |
| app.gateway.timeout | GatewayProperties.timeout | Duration |
| app.gateway.pool.max-connections | Pool.maxConnections | int |
| app.gateway.pool.enabled | Pool.enabled | boolean |
| app.gateway.endpoints[0].host | Endpoint.host | String |
| app.gateway.endpoints[0].port | Endpoint.port | int |

**@Validated** cho phép Spring Boot tích hợp validation khi cấu hình được bind thành bean. **@Valid** trên pool và các phần tử Endpoint cho phép kiểm tra xuyên vào object con. **@NotNull** đảm bảo pool tồn tại; chỉ @Valid không bắt buộc một tham chiếu khác null.

### 3.1. Đăng ký GatewayProperties khi chạy ứng dụng

Ví dụ:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

GatewayProperties phải nằm trong package được scan, hoặc được đăng ký qua **@EnableConfigurationProperties(GatewayProperties.class)**.

### 3.2. Dependency thường dùng

Với Maven:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Starter test thường cung cấp JUnit Jupiter, AssertJ và các hỗ trợ kiểm thử Spring Boot. Starter validation cung cấp tích hợp Jakarta Bean Validation và provider phù hợp.

**Không có validation provider** thì chỉ gắn annotation ràng buộc trong mã nguồn không bảo đảm mọi cơ chế kiểm tra sẽ tự chạy ở runtime.

---

## 4. Mức 1: kiểm thử đối tượng thuần Java

Ở mức này, test tạo class/record bằng **new**. Không khởi động Spring và không đọc application.yml.

Phù hợp nhất để kiểm tra:

- Constructor invariant, chẳng hạn maxConnections phải dương.
- Hàm tính default hoặc chuẩn hóa giá trị.
- Defensive copy của List/Map.
- Logic tương quan giữa nhiều field.
- Phương thức convenience được xây trên cấu hình.
- Bean Validation được **gọi trực tiếp** bằng Jakarta Validator.

### 4.1. Ví dụ constructor invariant

Một record nhỏ:

~~~java
import java.time.Duration;

public record RetrySettings(
        int maxAttempts,
        Duration backoff
) {
    public RetrySettings {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be >= 1"
            );
        }
        if (backoff == null ||
                backoff.isZero() ||
                backoff.isNegative()) {
            throw new IllegalArgumentException(
                    "backoff must be positive"
            );
        }
    }
}
~~~

Unit test:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class RetrySettingsTest {

    @Test
    void acceptsValidValues() {
        RetrySettings settings =
                new RetrySettings(3, Duration.ofMillis(250));

        assertThat(settings.maxAttempts()).isEqualTo(3);
        assertThat(settings.backoff())
                .isEqualTo(Duration.ofMillis(250));
    }

    @Test
    void rejectsInvalidAttemptCount() {
        assertThatThrownBy(() ->
                new RetrySettings(0, Duration.ofSeconds(1)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsNegativeBackoff() {
        assertThatThrownBy(() ->
                new RetrySettings(2, Duration.ofSeconds(-1)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Những test này nhanh, lỗi rõ, không phụ thuộc bean registration, profile, file hay network.

**Giới hạn:** Chúng không chứng minh Spring Boot có chuyển được **250ms** sang Duration, hay đường dẫn **app.retry.backoff** có được tìm đúng không.

### 4.2. Kiểm thử immutable snapshot

Nếu object cấu hình giữ List:

~~~java
import java.util.List;

public record ClientSettings(List<String> hosts) {

    public ClientSettings {
        hosts = hosts == null
                ? List.of()
                : List.copyOf(hosts);
    }
}
~~~

Test:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class ClientSettingsTest {

    @Test
    void protectsAgainstExternalMutation() {
        List<String> original = new ArrayList<>();
        original.add("alpha.example.test");

        ClientSettings settings = new ClientSettings(original);

        original.add("beta.example.test");

        assertThat(settings.hosts())
                .containsExactly("alpha.example.test");

        assertThatThrownBy(() ->
                settings.hosts().add("gamma.example.test"))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

Đây là test chính xác cho **defensive copy**, nhưng không kiểm thử việc Binder chuyển một YAML list thành Java List.

### 4.3. Test Bean Validation tường minh

Nếu muốn kiểm tra các constraint của GatewayProperties mà **không khởi động Spring**, có thể sử dụng Jakarta Validator:

~~~java
import java.time.Duration;
import java.util.List;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayConstraintsTest {

    @Test
    void findsInvalidNestedEndpoint() {
        try (var factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            var gateway = new GatewayProperties(
                    Duration.ofSeconds(5),
                    new GatewayProperties.Pool(10, true),
                    List.of(
                        new GatewayProperties.Endpoint("", 0)
                    )
            );

            var violations = validator.validate(gateway);

            assertThat(violations).isNotEmpty();
            assertThat(violations.stream()
                    .map(v -> v.getPropertyPath().toString()))
                    .anyMatch(path -> path.contains("host"))
                    .anyMatch(path -> path.contains("port"));
        }
    }
}
~~~

Ở đây **validator.validate(...)** được gọi trực tiếp, không có @ConfigurationProperties binder. Nó chứng minh các constraint và @Valid mô tả đúng object graph, nhưng chưa chứng minh Spring Boot tự kích hoạt validation lúc startup.

### 4.4. @Valid không đồng nghĩa @NotNull

Một tham chiếu:

~~~java
@Valid Pool pool
~~~

được cascade nếu pool có object, nhưng không tự cấm pool=null. Nếu pool bắt buộc, dùng:

~~~java
@Valid @NotNull Pool pool
~~~

Trong unit test với Validator, nên có một case tạo GatewayProperties có **pool=null**, sau đó kiểm tra @NotNull báo lỗi. Nếu chỉ kiểm tra Pool.maxConnections=0 mà không kiểm tra null, có thể bỏ sót một nhánh cấu hình vắng mặt.

### 4.5. Khi không nên dùng mức 1

Không dùng riêng test object để kết luận:

- Tên **max-connections** bind đúng vào **maxConnections**.
- application-prod.yml được nạp theo đúng profile.
- Biến môi trường **APP_GATEWAY_TIMEOUT** thắng application.yml.
- Bean cấu hình được scan thành công.
- @ConditionalOnProperty tạo bean đúng.
- EnvironmentPostProcessor được discovery qua spring.factories.

Mọi hành vi ấy nằm ngoài phạm vi một object thuần Java.

---

## 5. Mức 2: kiểm thử Binder trực tiếp

**Binder** là thành phần Spring Boot chuyển các property có cấu trúc thành object đích. Kiểm thử trực tiếp Binder phù hợp khi câu hỏi chính là **“Tên và giá trị nguồn có được liên kết đúng vào kiểu Java không?”**

Mức này không cần ApplicationContext. Có thể dựng một nguồn cấu hình thử nghiệm bằng **MapConfigurationPropertySource**.

### 5.1. Test binding một record có nested object và Duration

~~~java
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayBinderTest {

    @Test
    void bindsNestedRecordAndDuration() {
        Map<String, Object> values = Map.of(
            "app.gateway.timeout", "5s",
            "app.gateway.pool.max-connections", "24",
            "app.gateway.pool.enabled", "true",
            "app.gateway.endpoints[0].host", "primary.example.test",
            "app.gateway.endpoints[0].port", "8080"
        );

        Binder binder = new Binder(
            new MapConfigurationPropertySource(values)
        );

        GatewayProperties gateway = binder
            .bind("app.gateway", GatewayProperties.class)
            .orElseThrow(() ->
                new IllegalStateException("Gateway not bound"));

        assertThat(gateway.timeout())
            .isEqualTo(Duration.ofSeconds(5));
        assertThat(gateway.pool().maxConnections())
            .isEqualTo(24);
        assertThat(gateway.pool().enabled()).isTrue();
        assertThat(gateway.endpoints())
            .hasSize(1);
        assertThat(gateway.endpoints().get(0).host())
            .isEqualTo("primary.example.test");
    }
}
~~~

Mức Binder đã kiểm tra:

- Prefix **app.gateway**.
- Nested property **pool.max-connections**.
- Chỉ số danh sách **endpoints[0]**.
- Type conversion **"5s" → Duration**.
- Type conversion từ chuỗi sang int/boolean.
- Constructor binding của record trong bối cảnh binder hỗ trợ.

Nó không kiểm tra class đã được scan, bean có được inject hay validation integration có tự chạy không.

### 5.2. Đọc BindResult đúng cách

~~~java
var result = binder.bind(
        "app.gateway",
        GatewayProperties.class
);

if (!result.isBound()) {
    throw new IllegalStateException(
        "No configuration under app.gateway"
    );
}

GatewayProperties gateway = result.get();
~~~

**isBound()** trả lời có kết quả binding không. Nó không phải một phép kiểm tra Bean Validation.

### 5.3. Test khi prefix vắng mặt

~~~java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
            Map.of("unrelated.value", "example")
        )
);

var result = binder.bind(
        "app.gateway",
        GatewayProperties.class
);

assertThat(result.isBound()).isFalse();
~~~

Đây là một case độc lập với “field bên trong prefix thiếu”. Một object vẫn có thể được bind dù một số field null hoặc nhận default; khi ấy **isBound()** vẫn có thể true.

### 5.4. Test lỗi chuyển đổi kiểu

~~~java
Map<String, Object> values = Map.of(
        "app.gateway.timeout", "not-a-duration",
        "app.gateway.pool.max-connections", "20"
);

Binder binder = new Binder(
        new MapConfigurationPropertySource(values)
);

assertThatThrownBy(() ->
        binder.bind("app.gateway", GatewayProperties.class))
        .isInstanceOf(
            org.springframework.boot.context.properties.bind.BindException.class
        );
~~~

Case này kiểm tra lỗi conversion/bind. Nó không chứng minh @Min(1) hoặc @NotBlank tự được validate.

### 5.5. Test relaxed binding

Ví dụ Java field **maxConnections** thường tương ứng property canonical:

~~~text
app.gateway.pool.max-connections
~~~

Có thể viết các ca thử riêng với tên theo từng nguồn được hỗ trợ, chẳng hạn:

~~~text
app.gateway.pool.max-connections
app.gateway.pool.maxConnections
app.gateway.pool.max_connections
~~~

Mức Binder giúp quan sát khả năng giải quyết những biến thể này đối với **ConfigurationPropertySource thử nghiệm**.

**Quan trọng:** Một MapConfigurationPropertySource không giống hoàn toàn OS environment variable. Muốn chứng minh phép đổi canonical thành tên env thực tế, cần mô phỏng đúng PropertySource của env hoặc chạy một test cấp tiến trình với env var thật.

### 5.6. List với Bindable

Khi không muốn tạo wrapper record:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.bind.Bindable;

List<GatewayProperties.Endpoint> endpoints = binder
        .bind(
            "app.gateway.endpoints",
            Bindable.listOf(GatewayProperties.Endpoint.class)
        )
        .orElse(List.of());
~~~

**Bindable.listOf(Endpoint.class)** giữ thông tin kiểu phần tử. Dùng **List.class** trực tiếp có thể làm mất thông tin cần thiết để binder tạo từng Endpoint.

### 5.7. Map với Bindable

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;

Map<String, String> labels = binder
    .bind(
        "app.gateway.labels",
        Bindable.mapOf(String.class, String.class)
    )
    .orElse(Map.of());
~~~

Nhờ MapConfigurationPropertySource, bạn có thể cung cấp:

~~~text
app.gateway.labels.owner=platform
app.gateway.labels.region=asia
~~~

để xác nhận key/value trong Map được bind đúng. Với Map key chứa dấu chấm hoặc ký tự đặc biệt, cần các case riêng về bracket notation.

### 5.8. Có tự validate @Validated không?

Khi gọi **new Binder(new MapConfigurationPropertySource(...))**, đừng mặc định rằng toàn bộ validation integration của @ConfigurationProperties đã được cài đặt.

Annotation **@Validated** có trên record không đồng nghĩa một Binder thủ công sẽ tự gọi Jakarta Validator theo cùng vòng đời tạo bean cấu hình.

Nếu test chỉ muốn xác nhận chuyển đổi và cấu trúc, Binder là đủ. Nếu muốn kiểm tra constraint, có thể:

1. Bind object qua Binder.
2. Gọi **validator.validate(object)** một cách tường minh.
3. Hoặc chuyển sang ApplicationContextRunner để kiểm tra Spring Boot tích hợp validation với bean thật.

Không ghi một test Binder thành “validation khởi động của ứng dụng đã hoạt động” nếu chưa bật đường validation.

### 5.9. Phạm vi nguồn của MapConfigurationPropertySource

MapConfigurationPropertySource chứa các key do test truyền vào. Nó **không tự tải** application.yml, application-prod.yml, spring.config.import, OS env và CLI.

Vì vậy:

~~~java
new Binder(new MapConfigurationPropertySource(values))
~~~

phù hợp cho một bài test đơn vị binding, nhưng không chứng minh thứ tự ưu tiên của toàn bộ Spring Environment.

---

## 6. Mức 3: ApplicationContextRunner

**ApplicationContextRunner** nằm trong hệ thống kiểm thử của Spring Boot. Nó tạo một ApplicationContext tương đối nhỏ, cho phép cung cấp cấu hình, đăng ký class cấu hình/auto-configuration, chạy context và assert bean, condition hoặc lỗi khởi tạo.

Đây là lựa chọn đặc biệt hữu ích khi câu hỏi chính là:

- Spring Boot có đăng ký @ConfigurationProperties bean không?
- Bean có bind đúng khi dùng @EnableConfigurationProperties không?
- @Validated có làm context fail khi nested property sai không?
- @ConditionalOnProperty có tạo bean theo flag không?
- Auto-configuration của một thư viện có hành xử đúng dưới nhiều tổ hợp property không?

### 6.1. Cấu hình một runner nhỏ

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GatewayProperties.class)
class GatewayTestConfiguration {
}
~~~

Runner:

~~~java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GatewayPropertiesContextTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(GatewayTestConfiguration.class);
}
~~~

**withUserConfiguration** chỉ định cấu hình cần đăng ký cho context thử nghiệm. **withPropertyValues** đưa các property thử nghiệm vào Environment của runner.

### 6.2. Test bind thành công

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesContextTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(GatewayTestConfiguration.class);

    @Test
    void createsBoundGatewayBean() {
        runner.withPropertyValues(
            "app.gateway.timeout=5s",
            "app.gateway.pool.max-connections=24",
            "app.gateway.pool.enabled=true",
            "app.gateway.endpoints[0].host=primary.example.test",
            "app.gateway.endpoints[0].port=8080"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                .hasSingleBean(GatewayProperties.class);

            GatewayProperties gateway =
                context.getBean(GatewayProperties.class);

            assertThat(gateway.timeout())
                .isEqualTo(Duration.ofSeconds(5));
            assertThat(gateway.pool().maxConnections())
                .isEqualTo(24);
        });
    }
}
~~~

Test này chứng minh nhiều hơn Binder test:

- Spring tạo một context.
- @EnableConfigurationProperties đăng ký đúng bean.
- Bean nhận dữ liệu qua cơ chế integration của Spring Boot.
- Bean được tìm thấy trong ApplicationContext.

Nhưng context này không phải toàn ứng dụng với mọi auto-configuration, file profile, server và dependency thật.

### 6.3. Test validation thất bại

Với GatewayProperties có @Validated, @Valid, @Min và @NotEmpty:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void rejectsInvalidNestedEndpoint() {
    runner.withPropertyValues(
        "app.gateway.timeout=5s",
        "app.gateway.pool.max-connections=24",
        "app.gateway.pool.enabled=true",
        "app.gateway.endpoints[0].host=",
        "app.gateway.endpoints[0].port=0"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Nếu test application không tự cung cấp Validator, cần thêm **ValidationAutoConfiguration** và dependency validator phù hợp để test đường validation thực sự. Một thiết lập có chủ đích:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;

private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(ValidationAutoConfiguration.class)
        )
        .withUserConfiguration(GatewayTestConfiguration.class);
~~~

Việc có starter validation trên classpath giúp validator provider khả dụng. Cần giữ đồng bộ cấu hình test với phiên bản Spring Boot của dự án.

**Không chỉ assert context fail rồi kết luận constraint cụ thể hoạt động.** Context có thể fail do thiếu bean, lỗi import hoặc một class không tạo được. Khi test nhắm vào validation, nên kiểm tra nguyên nhân lỗi liên quan đường dẫn/constraint, nhưng tránh phụ thuộc nguyên văn toàn bộ thông báo lỗi vốn thay đổi giữa các phiên bản.

### 6.4. Test tình huống vắng mặt

Một case quan trọng:

~~~java
@Test
void rejectsMissingRequiredPool() {
    runner.withPropertyValues(
        "app.gateway.timeout=5s",
        "app.gateway.endpoints[0].host=primary.example.test",
        "app.gateway.endpoints[0].port=8080"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Vì **pool** có @NotNull, nếu binder không cung cấp default object, validator cần phát hiện nhánh bắt buộc bị thiếu.

Case này khác việc pool có object nhưng maxConnections=0. Cả hai nên được kiểm tra khi hợp đồng cấu hình yêu cầu.

### 6.5. Test @ConditionalOnProperty

Một auto-configuration ví dụ:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditWriter auditWriter() {
        return new AuditWriter();
    }

    static class AuditWriter {}
}
~~~

Test:

~~~java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withUserConfiguration(AuditConfiguration.class);

@Test
void enablesAuditWhenFlagIsTrue() {
    runner.withPropertyValues("app.audit.enabled=true")
        .run(context ->
            assertThat(context)
                .hasSingleBean(AuditConfiguration.AuditWriter.class));
}

@Test
void omitsAuditWhenFlagIsFalse() {
    runner.withPropertyValues("app.audit.enabled=false")
        .run(context ->
            assertThat(context)
                .doesNotHaveBean(AuditConfiguration.AuditWriter.class));
}
~~~

Case này không cần toàn bộ DemoApplication. Nó tập trung đúng **điều kiện tạo bean**.

### 6.6. Test auto-configuration thay vì user configuration

Khi kiểm tra một auto-configuration do thư viện cung cấp, có thể dùng:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;

new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
    )
    .withPropertyValues("my.feature.enabled=true")
    .run(context -> {
        // Assert bean và condition cụ thể.
    });
~~~

Điểm khác với @SpringBootTest: runner chỉ nạp những cấu hình được chỉ định cùng dependency liên quan, nên dễ cô lập nguyên nhân fail.

### 6.7. Context được đóng sau callback

ApplicationContextRunner quản lý vòng đời context của test. Đừng giữ bean hoặc context trong static field để sử dụng sau callback, vì context có thể đã đóng.

Nếu test cần assert một object nhận dữ liệu từ bean, hãy kiểm tra ngay trong callback.

### 6.8. Có cần @DirtiesContext?

Với ApplicationContextRunner, mỗi lần **run** tạo một context thử nghiệm riêng và được đóng sau callback. Thường không cần @DirtiesContext. Annotation này dành cho Spring TestContext cache trong những bài test khác và có chi phí riêng.

### 6.9. Giới hạn của ApplicationContextRunner

Runner thường không chủ động thực hiện toàn bộ bootstrap của một SpringApplication theo cùng cách ứng dụng thật. Đừng suy ra những điều sau chỉ từ withPropertyValues:

- application-prod.yml được nạp theo đúng Config Data lifecycle.
- spring.config.import từ classpath được xử lý.
- EnvironmentPostProcessor trong spring.factories được discover ở đúng thời điểm.
- Startup event, logging và tất cả listener đã chạy.
- Auto-configuration toàn ứng dụng được tải theo đúng classpath production.
- Web server hoặc datasource production thực sự khởi động.

Nếu đây là nội dung cần chứng minh, chọn mức 4 hoặc dựng một integration test có SpringApplication phù hợp.

---

## 7. Mức 4: khởi động ứng dụng đầy đủ

Với **@SpringBootTest**, Spring Boot test có thể khởi động ApplicationContext của ứng dụng, nạp Config Data theo flow phù hợp, thực hiện auto-configuration và wiring thực tế. Nếu chọn webEnvironment RANDOM_PORT, một web server cũng có thể khởi động.

Dùng mức này khi cần kiểm tra:

- Tổ hợp application.yml và application-prod.yml.
- Config Data import hoặc external config location.
- Hành vi bootstrap và discovery của EnvironmentPostProcessor.
- Nhiều auto-configuration tương tác.
- Bean nghiệp vụ sử dụng @ConfigurationProperties đúng.
- Cấu hình kết nối hạ tầng (nếu đó là mục đích của test).
- Một luồng chạy thật của chức năng phụ thuộc cấu hình.

### 7.1. Một @SpringBootTest nhỏ

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "app.gateway.timeout=7s",
        "app.gateway.pool.max-connections=30",
        "app.gateway.pool.enabled=true",
        "app.gateway.endpoints[0].host=test.example.test",
        "app.gateway.endpoints[0].port=9090"
    }
)
class GatewayApplicationTest {

    @Autowired
    private GatewayProperties gateway;

    @Test
    void wiresConfigurationIntoApplication() {
        assertThat(gateway.timeout())
            .isEqualTo(Duration.ofSeconds(7));
        assertThat(gateway.pool().maxConnections())
            .isEqualTo(30);
    }
}
~~~

Test này yêu cầu dự án có một @SpringBootConfiguration/@SpringBootApplication phù hợp và registration của GatewayProperties. Nó có thể nạp nhiều bean hơn mức cần thiết nếu ứng dụng lớn, nên không dùng mặc định cho từng trường config đơn giản.

### 7.2. Profile-specific configuration

Ví dụ:

~~~yaml
# application.yml
app:
  gateway:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 12s
~~~

Một test:

~~~java
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("prod")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProductionConfigTest {
    // Assert property cuối hoặc bean thực nhận timeout 12s.
}
~~~

Trong bài test thực, cần cung cấp các field bắt buộc khác của GatewayProperties, qua file test hoặc những nguồn hợp lệ. Không nên đưa một profile production thật với secret/network dependencies vào test mà không có thiết kế cô lập.

### 7.3. @ActiveProfiles và withPropertyValues không giống nhau

**@ActiveProfiles("prod")** trong @SpringBootTest tham gia cơ chế test bootstrap với active profiles.

Ngược lại, một ApplicationContextRunner chỉ được gọi:

~~~java
runner.withPropertyValues("spring.profiles.active=prod")
~~~

không nên được xem là bằng chứng rằng toàn bộ quá trình Config Data đã nạp application-prod.yml giống SpringApplication thật. Runner không tự nhiên có toàn bộ bootstrap pipeline.

### 7.4. Config Data imports

Nếu muốn xác minh:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway.yml"
~~~

thì test phải kiểm soát file/location trong môi trường khởi động và xem giá trị cuối mà bean nhận. Đây là một bài kiểm thử tích hợp liên quan Config Data, không phải test của MapConfigurationPropertySource thuần.

Các path tương đối có thể phụ thuộc working directory của test runner. Để test ổn định, nên dùng thư mục tạm hoặc một test resource được cấu hình rõ, thay vì dựa vào file tình cờ có trên máy phát triển.

### 7.5. EnvironmentPostProcessor discovery

Nếu ứng dụng có processor đăng ký trong **META-INF/spring.factories**, một unit test gọi:

~~~java
processor.postProcessEnvironment(environment, application);
~~~

chỉ chứng minh logic callback.

Để chứng minh file spring.factories đúng, cần một test khởi động SpringApplication và kiểm tra PropertySource đã xuất hiện. Một bài @SpringBootTest trong môi trường thích hợp có thể kiểm tra discovery đó, nhưng khi cần giảm các bean không liên quan, có thể dùng một ứng dụng thử tối giản khởi động qua SpringApplication.

### 7.6. Không phải mọi test mức 4 đều cần HTTP server

Chọn webEnvironment tùy mục đích:

| WebEnvironment | Khi nào phù hợp |
| --- | --- |
| NONE | Kiểm tra bootstrap/config bean, không cần web layer |
| MOCK | Kiểm tra web context giả lập mà không mở real port |
| RANDOM_PORT | Kiểm tra web server thực và HTTP interaction |
| DEFINED_PORT | Chỉ khi có lý do rõ về port cố định; dễ xung đột môi trường |

Nếu chỉ cần kiểm tra PropertySource hoặc @ConfigurationProperties trong toàn ứng dụng, **NONE** thường đủ. Chạy RANDOM_PORT mà không có test HTTP là chi phí không cần thiết.

### 7.7. Khi cần database hoặc service ngoài

Không phải cứ @SpringBootTest là phải kết nối DB production. Nếu mục tiêu là kiểm tra hạ tầng tích hợp, dùng môi trường test được kiểm soát (container, embedded service hoặc stub thích hợp) và tránh sử dụng credential thật.

Nếu test chỉ nhằm xác nhận một timeout được bind đúng, mock/stub các dependency nặng hoặc đưa test xuống mức thấp hơn thay vì khởi động đầy đủ cả hệ thống.

---

## 8. Chọn mức kiểm thử bằng câu hỏi quyết định

Có thể chọn theo thứ tự:

~~~text
Có cần Spring hay property binding không?
    |
    +-- Không --> Test đối tượng thuần Java
    |
    +-- Có
         |
         +-- Chỉ cần tên property, cấu trúc và conversion?
         |      |
         |      +-- Có --> Binder test
         |
         +-- Cần tạo bean, @Validated hoặc conditional?
         |      |
         |      +-- Có --> ApplicationContextRunner
         |
         +-- Cần Config Data/profile/import/EPP discovery
                hoặc wiring toàn ứng dụng?
                |
                +-- Có --> @SpringBootTest / SpringApplication
~~~

Khi một case có thể được test ở hai mức, ưu tiên mức **thấp hơn** cho kiểm tra chi tiết. Mức cao hơn chỉ nên kiểm tra một vài luồng đại diện, tập trung vào những cơ chế mà mức thấp không bao phủ.

### 8.1. Một ví dụ lựa chọn

Giả sử lỗi production là giá trị **app.gateway.timeout=5s** được bind thành Duration sai. Mức phù hợp để tái hiện lỗi conversion là **Binder**. Một test @SpringBootTest có thể cho biết ứng dụng thất bại, nhưng chứa rất nhiều yếu tố không liên quan.

Nếu lỗi là **application-prod.yml không được nạp** thì Binder Map test không mô phỏng đúng nguyên nhân. Lúc đó cần test SpringApplication/Config Data.

Nếu lỗi là **feature flag không tạo bean** thì ApplicationContextRunner cho nhiều giá trị true/false/absent thường hiệu quả nhất.

---

## 9. Phân biệt bốn câu hỏi “cấu hình hợp lệ”

Câu nói “cấu hình hợp lệ” có thể mang nhiều nghĩa:

**Hợp lệ về logic object** — ví dụ maxConnections ít nhất 1, timeout dương, List không rỗng.

**Hợp lệ về binding** — tên property đúng, dữ liệu chuyển thành kiểu Java, nested path đúng cấp.

**Hợp lệ về Spring context** — class được đăng ký, bean được tạo, validation được kích hoạt, bean condition hợp lệ.

**Hợp lệ về triển khai** — profile, file ngoài, env vars, CLI, hạ tầng và startup behavior thực sự khớp môi trường mục tiêu.

Đây là lý do bốn mức test bổ sung cho nhau. Một record constructor không thể chứng minh Spring đã nạp profile. Một @SpringBootTest thành công cũng không đảm bảo mọi đường nhánh cấu hình hiếm gặp đã được kiểm tra nếu các trường hợp edge chưa xuất hiện trong test.

---

## 10. Một ma trận kiểm thử thực tế cho GatewayProperties

Thay vì viết mọi test ở mức 4, phân bổ như sau:

| Tình huống | Mức chính | Vì sao |
| --- | --- | --- |
| Timeout phải dương theo invariant Java | Đối tượng | Không cần Spring |
| Defensive copy của List endpoint | Đối tượng | Thuộc hợp đồng Java |
| **5s** chuyển thành Duration | Binder | Conversion |
| **max-connections** sang maxConnections | Binder | Relaxed binding |
| endpoints[0].port chuyển thành int | Binder | Collection index + conversion |
| Giá trị "abc" cho port gây lỗi | Binder | Conversion failure |
| @NotBlank trên Endpoint.host khiến context fail | ApplicationContextRunner | Validation tích hợp |
| @NotNull trên Pool khi vắng toàn nhánh | ApplicationContextRunner | Validation + bean binding |
| app.audit.enabled=false không tạo AuditWriter | ApplicationContextRunner | Conditional bean |
| application-prod.yml ghi đè application.yml | Full application | Config Data + profile |
| EPP thực sự được discovery từ spring.factories | Full application | Bootstrap discovery |
| Client kết nối được tới mock server thực | Full application/integration | Runtime integration |
| Secret config không bị in vào log | Test security chuyên biệt | Không chỉ thuộc Binder |

Ma trận này làm rõ mục tiêu của từng bài, tránh tình huống một suite hàng trăm @SpringBootTest chỉ để xác nhận vài String.

---

## 11. Kiểm thử default: chọn đúng tầng

Giá trị mặc định có thể đến từ nhiều nơi:

1. Field initializer trong JavaBean.
2. Compact constructor hoặc constructor invariant của record.
3. **@DefaultValue** của constructor binding.
4. application.yml nền.
5. Default properties được SpringApplication cung cấp.
6. Low-priority PropertySource của thư viện.
7. Fallback sau một lời gọi Binder không bound.

Mỗi loại có phạm vi test khác nhau.

### 11.1. Default trong Java object

~~~java
public record RetrySettings(int attempts) {
    public RetrySettings {
        if (attempts < 1) {
            attempts = 3;
        }
    }
}
~~~

Test thuần Java đủ để kiểm tra logic này. Tuy nhiên, hãy cân nhắc rằng biến đổi một giá trị không hợp lệ thành default có thể che lỗi cấu hình; với thiết lập bắt buộc, ném lỗi/validation thường thích hợp hơn.

### 11.2. Default từ application.yml

Nếu muốn xác minh một giá trị thấp từ application.yml được dùng khi prod không khai báo, cần test có Config Data startup phù hợp. Binder Map test không tự biết file nền của ứng dụng.

### 11.3. Default từ PropertySource do EPP thêm

Có hai câu hỏi độc lập:

- EPP có đặt source và giá trị mặc định như dự kiến không? → Unit test processor với StandardEnvironment.
- SpringApplication có khám phá EPP, thứ tự nguồn có đúng không? → Integration test.

### 11.4. Default không đồng nghĩa thiếu property

Nếu một record có @DefaultValue hoặc constructor tự thay null bằng giá trị hợp lệ, Bean Validation có thể thấy dữ liệu sau default. Một @NotNull trên trường đã được default sẽ không chứng minh operator thực sự khai báo thuộc tính.

Khi một giá trị bắt buộc từ deployment, đừng cung cấp default hợp lệ giả chỉ để test startup pass.

---

## 12. Test null, empty, sai kiểu và sai ràng buộc

Bốn trạng thái cần các case riêng:

| Input | Ví dụ | Lỗi cần xem |
| --- | --- | --- |
| Không khai báo | Không có app.gateway.pool | Binding/default/@NotNull |
| Khai báo rỗng | app.gateway.endpoints=[] | @NotEmpty hoặc chính sách collection |
| Sai kiểu | app.gateway.timeout=abc | Conversion |
| Đúng kiểu nhưng không hợp lệ | app.gateway.pool.max-connections=0 | @Min(1) |

Nếu tất cả test chỉ dùng một YAML “hợp lệ”, rất nhiều lỗi có thể bị bỏ sót.

### 12.1. Thiếu toàn bộ nhánh nested

Một bean có:

~~~java
@Valid @NotNull Pool pool
~~~

Cần test thiếu **app.gateway.pool.*** để chắc chắn chương trình từ chối khi pool bắt buộc.

### 12.2. Nhánh tồn tại nhưng trường con thiếu

Với Pool có maxConnections dùng int, khi property vắng mặt giá trị primitive có thể là 0 trong một số binding paths. @Min(1) phát hiện 0 nếu validation tới được Pool.

Nếu cần phân biệt “vắng mặt” và “được khai báo bằng 0”, dùng Integer với @NotNull và @Min thay vì primitive.

### 12.3. List có phần tử lỗi

Giả sử List chứa:

~~~properties
app.gateway.endpoints[0].host=primary.example.test
app.gateway.endpoints[0].port=8080
app.gateway.endpoints[1].host=
app.gateway.endpoints[1].port=0
~~~

Mức Binder giúp khẳng định có hai Endpoint và conversion hoạt động với 8080/0. Mức ApplicationContextRunner kiểm tra @Valid cascade đến Endpoint thứ hai, từ đó @NotBlank/@Min báo lỗi.

### 12.4. @Valid không làm collection tự khác null

Nếu List là null, @Valid trên element không tự tạo List. Dùng @NotEmpty hoặc @NotNull trên container theo hợp đồng. Nếu phần tử null cũng không được phép, dùng @NotNull trên container element.

---

## 13. Test relaxed binding theo nguồn

Spring Boot có cơ chế relaxed binding cho @ConfigurationProperties. Nhưng cần phân biệt việc đưa một key vào MapConfigurationPropertySource với việc cung cấp **OS environment variable thực**.

Ví dụ:

~~~text
Canonical: app.gateway.pool.max-connections
Java:      maxConnections
Env:       APP_GATEWAY_POOL_MAXCONNECTIONS
~~~

Quy tắc chuyển từ canonical sang env thông thường:

1. Dấu chấm thành dấu gạch dưới.
2. Bỏ dấu gạch ngang.
3. Chuyển chữ thành chữ hoa.

Không tự đổi thành **APP_GATEWAY_POOL_MAX_CONNECTIONS** chỉ vì camelCase có chữ C viết hoa.

### 13.1. Binder Map test chứng minh gì?

Nếu Map chứa:

~~~text
app.gateway.pool.maxConnections=24
~~~

Binder test có thể giúp xác nhận binder nhận diện biến thể tên trong nguồn thử nghiệm.

### 13.2. Test env var thực sự cần gì?

Muốn chứng minh ứng dụng đọc một biến môi trường, cần môi trường thử nghiệm dùng đúng semantics của environment variable, ví dụ một test tiến trình con có env vars được cấp trước khi JVM khởi động, hoặc một PropertySource mô phỏng đúng cách Spring xử lý tên môi trường.

**withPropertyValues("APP_GATEWAY_POOL_MAXCONNECTIONS=24") không phải bằng chứng tương đương OS env**, vì nó cung cấp một test property, không nhất thiết đưa nó vào PropertySource kiểu system environment.

### 13.3. Không chỉnh process environment bằng reflection tùy tiện

Các hack thay đổi System.getenv() bằng reflection có thể lỗi trên JVM hiện đại và gây ảnh hưởng các test khác. Với tích hợp env var thật, ưu tiên process-level test hoặc cơ chế được framework hỗ trợ.

---

## 14. Test thứ tự ưu tiên PropertySource

Giả sử cùng một property có giá trị khác nhau:

~~~text
application.yml             -> 5s
application-prod.yml        -> 8s
OS env                      -> 10s
JVM system property         -> 12s
Command-line argument       -> 15s
~~~

Trong flow tiêu chuẩn, CLI thường có ưu tiên cao hơn nhiều nguồn Config Data và env/system properties; nhưng thực tế còn có những nguồn test và extension có thể được đưa lên vị trí ưu tiên hơn.

### 14.1. Khi chỉ cần kiểm tra lựa chọn giữa hai nguồn

Một Binder test có thể được dựng với hai ConfigurationPropertySource đã sắp thứ tự, nếu muốn kiểm tra thuật toán của một module tự tạo Binder. Cần nhớ thứ tự nguồn bạn truyền chính là hợp đồng test, không phải toàn bộ Spring Boot precedence.

### 14.2. Khi cần xác minh Boot precedence

Dùng integration test với SpringApplication và những nguồn thật hoặc cơ chế test tái hiện rõ chúng. Kiểm tra giá trị cuối từ bean cấu hình, đồng thời ghi nhận nguồn nào cấp property khi cần chẩn đoán.

### 14.3. Test property overrides có độ ưu tiên riêng

Trong @SpringBootTest, giá trị truyền qua annotation test hoặc dynamic test property có thể có độ ưu tiên cao, phù hợp để cô lập test. Nhưng chính điều này có thể che giá trị từ application.yml.

Vì vậy một test @SpringBootTest(properties = "app.gateway.timeout=7s") **không phải bằng chứng** rằng application-prod.yml chứa 7s. Nó chỉ chứng minh test override được áp dụng.

---

## 15. Kiểm thử Config Data và profile

Các vấn đề về Config Data nên được kiểm tra ở mức startup phù hợp:

- Default profile so với active profile.
- application.yml và application-prod.yml.
- spring.config.import và các file được import.
- Optional file location và file bắt buộc.
- Đường dẫn ngoài JAR.
- Profile groups và on-profile activation.
- Thứ tự override giữa location groups.
- Nguồn có cùng property nhưng khác độ ưu tiên.

### 15.1. Không dùng test Binder thuần để kết luận về profile

Binder từ Map không đọc profile tự động. Nếu test nhận Duration đúng từ một Map, điều đó không chứng minh config file của profile prod được SpringApplication nạp.

### 15.2. Test file location không nên lệ thuộc máy phát triển

Đừng viết test trỏ tới:

~~~text
C:\Users\dev\local-config\application-prod.yml
~~~

hoặc file thật ngoài repository rồi giả định CI cũng có nó. Dùng resource thử nghiệm, thư mục tạm hoặc cấu hình test-controlled và đường dẫn được truyền rõ ràng.

### 15.3. Test cả trường hợp file vắng mặt

Nếu config import có optional: và file thiếu, startup có thể tiếp tục theo chính sách. Nếu không optional và file bắt buộc thiếu, startup có thể thất bại. Đây là hành vi của **Config Data/bootstrap**, nên kiểm tra bằng SpringApplication-level test thay vì new Binder(Map).

---

## 16. Test EnvironmentPostProcessor và thứ tự bootstrap

EnvironmentPostProcessor thường đăng ký trong **META-INF/spring.factories**, được chạy trong quá trình chuẩn bị Environment trước context refresh.

Có hai loại test cần tách biệt.

### 16.1. Unit test processor

~~~java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

StandardEnvironment env = new StandardEnvironment();

env.getPropertySources().addFirst(
    new MapPropertySource(
        "testOverride",
        Map.of("company.http.timeout", "12s")
    )
);

processor.postProcessEnvironment(
    env,
    new SpringApplication(Object.class)
);

assertThat(env.getProperty("company.http.timeout"))
    .isEqualTo("12s");
~~~

Case này xác minh processor không che override do nguồn khác cung cấp, nếu processor có chính sách default priority thấp.

### 16.2. Integration test discovery

Một SpringApplication thực phải khởi động rồi xác nhận source custom được thêm. Nó kiểm tra được:

- Path của spring.factories.
- Key đăng ký đúng phiên bản.
- Class implementation có trên runtime classpath.
- Factory tạo processor thành công.
- Order so với Config Data trong flow thực.

### 16.3. Khác biệt Boot 3 và Boot 4

Khi migrate, interface EnvironmentPostProcessor thay package giữa dòng Boot 3 và Boot 4. Test discovery đặc biệt có giá trị vì import compile được chưa chắc file spring.factories đúng key.

### 16.4. Không dùng Runner cục bộ thay cho test discovery

ApplicationContextRunner được thiết kế để kiểm thử context/auto-configuration nhỏ. Nó không mặc định tái hiện chính xác mọi listener và discovery bước bootstrap của SpringApplication. Vì thế test EPP bằng cách chỉ thêm .withPropertyValues(...) không chứng minh discovery.

---

## 17. Kiểm thử @ConditionalOnProperty và các trường hợp cạnh

Nếu cấu hình điều khiển bean bằng:

~~~java
@ConditionalOnProperty(
    prefix = "app.audit",
    name = "enabled",
    havingValue = "true"
)
~~~

nên kiểm tra ít nhất:

| Giá trị app.audit.enabled | Kỳ vọng trong ví dụ |
| --- | --- |
| true | Bean có mặt |
| false | Bean vắng |
| Không khai báo | Bean vắng nếu matchIfMissing mặc định false |
| Chuỗi khác "true" | Không khớp havingValue="true" |

Mức ApplicationContextRunner phù hợp vì có thể dựng nhiều context nhỏ với mỗi tổ hợp.

### 17.1. Những gì cần assert

Không chỉ kiểm tra Environment có property. Cần assert bean có hoặc không có, vì đối tượng đang được test là **quy tắc tạo bean**.

### 17.2. Khi feature flag tương tác với bean khác

Nếu bean AuditWriter đòi một dependency chỉ có ở production, test mức Runner có thể cung cấp một stub bean bằng cấu hình nhỏ, thay vì khởi động toàn ứng dụng.

Khi lỗi nằm ở wiring toàn hệ thống hoặc auto-configuration của nhiều subsystem, bổ sung một bài full integration.

---

## 18. Kiểm thử validation ở hai tầng

Có hai điều khác nhau:

1. **Constraint metadata đúng**: Jakarta Validator phát hiện @NotBlank, @Min, @Valid trên một object được tạo trực tiếp.
2. **Spring Boot thực thi validation khi bind bean**: context không khởi động hoặc bean không được tạo khi property vi phạm.

### 18.1. Kiểm tra constraint metadata

Dùng unit test với Validator để xác nhận các ràng buộc, đặc biệt nested List/Map và trường hợp null.

### 18.2. Kiểm tra validation integration

Dùng ApplicationContextRunner để bind từ property values, đăng ký @ConfigurationProperties và kiểm tra context fail khi dữ liệu sai.

Một test unit với Validator pass **không chứng minh** bean có @Validated, đã được scan và provider có mặt trong context thật.

### 18.3. Không coi conversion failure là validation

Nếu **max-connections=many** và Java đích là int, Binder có thể fail trước Jakarta Validation. Test sai kiểu nên được đặt trong nhóm conversion, không gộp với @Min(1).

### 18.4. Tránh mặc định mọi nested object đều được validate

Với nhiều cấp, cần @Valid ở những ranh giới tương ứng. Một object con null không bị @Valid tự cấm; thêm @NotNull nếu bắt buộc. Test thiếu nhánh và test object con có field sai là hai case riêng.

---

## 19. Test cấu hình khi phụ thuộc hạ tầng ngoài

Một cấu hình datasource hoặc HTTP client có hai cấp kiểm chứng.

**Cấp cấu hình:** URL, port, timeout, pool size được bind đúng vào Java object hoặc bean factory.

**Cấp kết nối:** client có thực sự kết nối được đến một endpoint, có đúng TLS/authentication, timeout thực thi đúng hay không.

Một Binder test có thể xác nhận timeout=3s, nhưng không thể chứng minh một HTTP client sẽ hủy request chậm sau ba giây. Một test kết nối tích hợp cần fake server, controlled latency hoặc hạ tầng thử nghiệm tương ứng.

### 19.1. Không dùng production infrastructure

Test phải không phụ thuộc database production, token thật hoặc dịch vụ ngoài thiếu kiểm soát. Nếu cần database, dùng container/embedded database phù hợp và cấp thông tin qua môi trường test.

### 19.2. Dynamic properties cho resource khởi động ở test

Với @SpringBootTest, Spring hỗ trợ **@DynamicPropertySource** để đăng ký property mà giá trị chỉ biết khi test setup chạy, ví dụ port do container hoặc mock server cấp.

Ví dụ ý tưởng:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "app.external.base-url",
        () -> testServerBaseUrl()
    );
}
~~~

Trong code thật, **testServerBaseUrl()** phải đến từ một server/container đã được test tạo và quản lý. Đoạn này minh họa điểm kết nối API, không phải một helper có sẵn của Spring.

### 19.3. Nguồn thử nghiệm có thể che nguồn thật

Một @DynamicPropertySource override có thể khiến bean chạy đúng trong test, nhưng không chứng minh tên env var của deployment production được viết đúng. Khi kiểm tra env var naming hoặc Config Data precedence, tránh để dynamic property vô tình che mất thứ cần kiểm tra.

---

## 20. Chi phí và tốc độ: cân nhắc thực tế

Chi phí test phụ thuộc số bean, classpath, I/O và hạ tầng, không có con số cố định. Tuy nhiên, thứ tự tương đối thường là:

~~~text
Nhanh và cô lập
    |
    v
Plain Java / Bean Validation unit test
    |
    v
Binder + MapConfigurationPropertySource
    |
    v
ApplicationContextRunner
    |
    v
Full @SpringBootTest / server / containers
    |
    v
Nặng hơn, kiểm tra nhiều thành phần hơn
~~~

Một ApplicationContextRunner không nhất thiết luôn nhanh hơn mọi bài @SpringBootTest nhỏ, nhưng nó chủ động giới hạn phạm vi hơn. Với dự án lớn, kiểm thử toàn bộ context lặp lại cho từng property có thể làm CI chậm đáng kể.

### 20.1. TestContext cache

Spring TestContext có khả năng cache context giữa những test có cấu hình phù hợp. Một số thay đổi như profile, property overrides, test configuration và dynamic property có thể khiến cache key khác nhau.

Vì vậy viết hàng chục @SpringBootTest với những tổ hợp property khác nhau có thể tạo nhiều context và làm tăng thời gian chạy.

### 20.2. @DirtiesContext không phải giải pháp mặc định

Dùng @DirtiesContext khi test thật sự làm context trở nên không thể tái sử dụng an toàn. Nếu lạm dụng, bạn có thể làm mất lợi ích caching và che các vấn đề về mutable shared state trong test.

### 20.3. Tránh sleep hoặc network call không cần thiết

Một test cấu hình chỉ cần so sánh Duration không nên chạy HTTP request chậm hoặc Thread.sleep. Nếu cần kiểm tra timeout runtime, đó là một test hành vi khác có hạ tầng kiểm soát thời gian và kết quả rõ ràng.

---

## 21. Cách đặt tên test theo hành vi

Tên test nên mô tả hành vi mà mức đó có thể chứng minh.

Ví dụ tốt:

~~~text
shouldRejectNegativeBackoff
shouldBindKebabCaseIntoCamelCaseRecordComponent
shouldConvertDurationFromPropertyValue
shouldRejectInvalidNestedEndpointAtContextStartup
shouldCreateAuditWriterOnlyWhenEnabled
shouldLoadProdConfigDataBeforeCreatingClient
shouldDiscoverPlatformEnvironmentPostProcessor
~~~

Ví dụ tên thiếu chính xác:

~~~text
shouldVerifyAllConfiguration
shouldGuaranteeProductionIsCorrect
shouldTestEverythingAboutProfiles
~~~

Một test chỉ chạy trong local JVM không thể chứng minh tất cả hành vi production. Tên rõ ràng giúp reviewers hiểu giới hạn thực.

---

## 22. Một chiến lược test được khuyến nghị cho dự án vừa

Với một nhóm GatewayProperties có vài field, có thể phân bổ:

- **Object tests:** vài case cho invariant và defensive copy, chỉ nếu class thực sự có logic.
- **Binder tests:** một happy path nested có Duration/List, một case tên key/kiểu sai.
- **ApplicationContextRunner:** một case bean hợp lệ, một case nested validation fail, các case feature flag nếu có.
- **Full application:** một hoặc một vài case đại diện cho profile/import/bootstrap và wiring với client thực.

Không cần test mọi tổ hợp ở cả bốn mức.

### 22.1. Khi nào bỏ qua mức 1?

Nếu GatewayProperties chỉ là record dữ liệu không có constructor logic và mọi constraint đã được test ở mức ApplicationContextRunner, có thể không cần một unit test riêng chỉ assert record accessor trả lại tham số truyền vào.

Đừng tạo test vô nghĩa để đủ “bốn loại”.

### 22.2. Khi nào bỏ qua mức 2?

Nếu chỉ có vài String đơn giản, không có collection, conversion hay naming đặc biệt, ApplicationContextRunner happy path có thể đã đủ. Không bắt buộc phải viết riêng Binder test cho mọi field.

### 22.3. Khi nào cần tăng mức 4?

Nếu dự án có nhiều Spring profile, Config Data imports phức tạp, custom EnvironmentPostProcessor hoặc auto-configuration quan trọng, mức full integration có thể phải được đầu tư nhiều hơn.

Phân bổ theo rủi ro, không theo một tỷ lệ test cố định.

---

## 23. Ma trận rủi ro quyết định ưu tiên

| Rủi ro | Triệu chứng production | Test đáng ưu tiên |
| --- | --- | --- |
| Sai kiểu Duration/DataSize | Startup fail hoặc timeout sai | Binder |
| Sai nested prefix | Field null dù file có giá trị | Binder |
| Thiếu @Valid | Config sai mà bean vẫn tạo | ApplicationContextRunner |
| Thiếu @ConfigurationPropertiesScan | Không inject được bean | Runner hoặc full app |
| Conditional bean sai | Feature tắt mà bean vẫn chạy | ApplicationContextRunner |
| Profile precedence sai | Prod dùng default của dev | Full app |
| EPP spring.factories sai | Defaults không được nạp | Full app |
| List bị thay khi đổi profile | Thiếu endpoints | Full app có Config Data |
| Env var tên sai | Deployment không override | Process/env integration |
| Secret bị lộ qua log | Rủi ro bảo mật | Test bảo mật/logging có chủ đích |
| HTTP timeout không hiệu lực | Request treo | Integration runtime |
| Context khởi động quá nặng | CI chậm, flaky | Hạ mức test có thể cô lập |

Ưu tiên test theo **nguồn gây lỗi**, không theo nơi lỗi được phát hiện. Một lỗi báo trong log startup không nhất thiết cần @SpringBootTest để tái hiện nếu root cause là conversion có thể kiểm tra bằng Binder.

---

## 24. Test success và failure có giá trị như nhau

Đừng chỉ viết một happy path YAML đẹp. Với cấu hình quan trọng, hãy có cả:

~~~text
VALID:     giá trị hợp lệ -> bean được tạo, object có dữ liệu đúng
MISSING:   thiếu trường bắt buộc -> lỗi có ý nghĩa
INVALID:   đúng kiểu nhưng sai constraint -> validation fail
MALFORMED: không chuyển được kiểu -> conversion fail
OVERRIDE:  nguồn ưu tiên cao -> giá trị cuối đúng
DISABLED:  feature flag false -> bean không được tạo
~~~

Mỗi mục có thể được gán đúng tầng:

- VALID/MISSING/INVALID liên quan bean → ApplicationContextRunner.
- MALFORMED liên quan conversion → Binder.
- OVERRIDE theo Config Data profile → Full application.
- DISABLED theo @ConditionalOnProperty → ApplicationContextRunner.

---

## 25. Kiểm thử Map và List cần thêm trường hợp riêng

### 25.1. List indexing

~~~properties
app.gateway.endpoints[0].host=alpha.example.test
app.gateway.endpoints[0].port=8080
app.gateway.endpoints[1].host=beta.example.test
app.gateway.endpoints[1].port=8081
~~~

Binder test có thể kiểm tra đúng thứ tự hai Endpoint.

### 25.2. List replacement qua nhiều nguồn

Nếu application.yml chứa hai endpoint nhưng application-prod.yml chứa một endpoint, Spring Boot thường chọn List từ nguồn ưu tiên cao thay vì tự nối chúng.

Muốn kiểm tra behavior đó từ các file thật, dùng integration test Config Data. Không suy luận từ một Binder Map chỉ chứa dữ liệu sau khi đã tự merge thủ công.

### 25.3. Map key động

Với Map<String, Region> có key chứa dấu chấm, bracket notation có thể cần thiết:

~~~yaml
app:
  regions:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

Binder test có thể kiểm tra kết quả Map giữ key **tenant.eu**, trong khi integration test kiểm tra YAML loader và Config Data hiểu tài liệu đúng.

### 25.4. Immutable collections

Nếu record dùng List.copyOf/Map.copyOf, unit test object là nơi tốt nhất kiểm tra service không thể mutate collection sau khi được tạo. Không cần khởi động Spring chỉ để gọi List.add rồi kỳ vọng UnsupportedOperationException.

---

## 26. Khi có custom Converter

Một dự án có thể dùng kiểu miền nghiệp vụ:

~~~java
public record RegionId(String value) {}
~~~

và muốn chuyển property String thành RegionId thông qua converter riêng.

Có hai vấn đề khác nhau:

1. Logic converter có đúng không? → Unit test converter thuần Java.
2. Converter có được Spring Boot đăng ký và Binder thực sự dùng trong application không? → ApplicationContextRunner hoặc integration test với conversion service/registration phù hợp.

Một test tự gọi **converter.convert("asia")** không chứng minh binder đã biết converter ấy. Ngược lại, một binder được tạo thủ công với conversion service khác ứng dụng không chứng minh runtime dùng cùng converter.

### 26.1. @ConfigurationPropertiesBinding

Spring Boot có cơ chế đăng ký converter dùng cho @ConfigurationProperties ở một số phiên bản. Nếu code cần custom conversion, hãy xác minh chính **cơ chế đăng ký** trong context chứ không chỉ kết quả của phương thức convert.

### 26.2. Converter không nên có side effect

Conversion của một property nên nhanh và có thể dự đoán. Không dùng một converter để gọi database hoặc HTTP từ giai đoạn khởi tạo config. Test những converter có phụ thuộc ngoài thường trở nên flaky vì trộn nhiều trách nhiệm.

---

## 27. Kiểm thử cấu hình YAML và .properties

### 27.1. Khác biệt kiểm thử nguồn

Binder Map test nhận key đã được làm phẳng:

~~~text
app.gateway.pool.max-connections=24
~~~

Nó không kiểm tra YAML parser có đọc đúng:

~~~yaml
app:
  gateway:
    pool:
      max-connections: 24
~~~

Nếu lỗi liên quan thụt lề, document separator hoặc profile activation, dùng test có loader/Config Data thật.

### 27.2. YAML sai cấp

YAML sai:

~~~yaml
app:
  gateway:
    max-connections: 24
~~~

đường dẫn là **app.gateway.max-connections**, không phải **app.gateway.pool.max-connections**.

Binder test có thể phơi ra lỗi nếu cung cấp đúng key sai đó, nhưng không chứng minh file gốc có cấu trúc như vậy trừ khi parser được chạy.

### 27.3. Multi-document YAML

Các tài liệu phân cách bằng **---** có thể có quy tắc activation riêng. Nếu mục tiêu là kiểm tra khi nào document được chọn, cần test Config Data với profile tương ứng, không phải chỉ đơn giản ghép Map từ nhiều document.

---

## 28. Kiểm thử biến môi trường và JVM options

Một số nguồn có cú pháp khác nhau:

~~~bash
APP_GATEWAY_TIMEOUT=8s java -jar demo.jar
~~~

~~~bash
java -Dapp.gateway.timeout=8s -jar demo.jar
~~~

~~~bash
java -jar demo.jar --app.gateway.timeout=8s
~~~

Đây là OS environment variable, JVM system property và command-line argument — ba nguồn khác nhau.

### 28.1. Một test dùng withPropertyValues không chứng minh cả ba

ApplicationContextRunner với:

~~~java
.withPropertyValues("app.gateway.timeout=8s")
~~~

chứng minh runner đã cấp một property. Nó không chứng minh shell, JVM -D hoặc CLI parser đang được sử dụng.

### 28.2. Khi cần kiểm tra startup CLI

Dùng SpringApplication.run với arguments trong một integration test được cô lập, hoặc khởi động tiến trình con có chính xác CLI options mong muốn. Không dùng System.setProperty lộn xộn mà không khôi phục trạng thái.

### 28.3. Test System properties phải dọn dẹp

Nếu buộc phải dùng System.setProperty, lưu giá trị trước khi test và restore trong finally hoặc extension phù hợp. System properties là trạng thái JVM toàn cục; nếu để rò rỉ, test chạy song song có thể ảnh hưởng nhau.

### 28.4. Test OS env thực

Muốn test tên UPPER_UNDERSCORE ở mức hệ điều hành, một test chạy tiến trình JVM con với biến môi trường được cấp trước khi start thường đáng tin cậy hơn việc hack trực tiếp System.getenv.

---

## 29. Kiểm thử cấu hình với security và secret

Một điểm quan trọng khi test:

**Không bao giờ dùng secret production trong test fixtures.** Nếu cần kiểm tra username/password/Token, dùng chuỗi giả không có quyền truy cập thật.

Ví dụ:

~~~properties
app.external.api-key=dummy-test-key
~~~

Không log toàn bộ @ConfigurationProperties record khi nó chứa dữ liệu nhạy cảm; record.toString() có thể bao gồm giá trị component.

### 29.1. Kiểm tra redaction là một bài riêng

Nếu yêu cầu vận hành là lỗi cấu hình không được để lộ token trong log, cần một test log capture hoặc test API/Actuator phù hợp. Binder test thông thường không tự chứng minh dữ liệu sẽ được che.

### 29.2. Không đẩy secret qua PropertySource trước khi cần

Một test EPP có thể dùng một key giả để kiểm tra nguồn được thêm. Không cần nạp Secret Manager hoặc token thật chỉ để chứng minh map precedence.

---

## 30. Tránh false confidence từ @SpringBootTest

Một @SpringBootTest xanh không có nghĩa:

- Tất cả profile đã được kiểm tra.
- Mọi dạng biến môi trường đều bind chính xác.
- Mỗi custom converter hoạt động với mọi input.
- Các secret luôn được redacted.
- Mọi constructor invariant đều đã được kiểm tra.
- Một List từ nguồn khác sẽ merge đúng như mong muốn.

Test chỉ chứng minh những input và hành vi mà nó thực sự thực thi.

### 30.1. Kiểm tra kết quả cuối, không chỉ startup

Nếu @SpringBootTest chỉ assert context không lỗi, một property sai có thể vẫn được thay bằng default hợp lệ. Đối với giá trị quan trọng, hãy assert **bean cấu hình thực nhận giá trị nào**.

### 30.2. Không dùng @SpringBootTest để kiểm tra từng phép toán nhỏ

Điều đó làm tăng thời gian CI và khó debug. Những phép toán thuần nên có unit test, còn hành vi binder nên có test Binder.

---

## 31. Tránh false confidence từ Binder test

Một Binder test xanh không chứng minh:

- Bean được scan/enable.
- @Validated thật sự chạy khi startup.
- PropertySource precedence trong ứng dụng giống test Map.
- Config Data import file ngoài hoạt động.
- EPP đăng ký qua spring.factories hoạt động.
- App không có xung đột bean hoặc auto-configuration khác.
- Runtime HTTP client áp dụng đúng timeout.

Nếu rủi ro nằm ở lifecycle hoặc integration, phải bổ sung test mức 3/4.

---

## 32. Tránh false confidence từ Object test

Một constructor được test thuần Java có thể đúng, nhưng Spring Boot vẫn không tạo được object do:

- Tên property không khớp.
- Nested path sai.
- Field type không có converter.
- Constructor binding không tương thích cách đăng ký bean.
- Annotation @ConfigurationPropertiesScan vắng.
- Validator provider thiếu.
- Profile/Config Data chưa nạp.

Object test chỉ kiểm tra những gì nằm trong Java object và những dependency được test gọi trực tiếp.

---

## 33. Khi nào nên dùng ApplicationContextRunner thay vì full app?

Dùng Runner khi code cần chứng minh behavior Spring context nhưng **không phụ thuộc toàn bộ ứng dụng**.

Ví dụ một module auto-configuration bật datasource client tùy property:

~~~java
@ConditionalOnProperty(
    prefix = "feature.client",
    name = "enabled",
    havingValue = "true"
)
~~~

Với runner có thể thử:

~~~text
feature.client.enabled=true
feature.client.enabled=false
feature.client.enabled absent
~~~

và assert số bean. Không cần khởi động web server, JPA, message broker hoặc data source của các module khác.

Nếu một auto-configuration phụ thuộc một bean hạ tầng, cung cấp stub/mock bean theo contract test hoặc kiểm tra condition report ở đúng context. Không kéo toàn bộ ứng dụng vào chỉ để thoả mãn một dependency có thể cô lập.

### 33.1. Khi nào Runner chưa đủ?

Nếu lỗi xuất hiện chỉ khi các auto-configuration của ứng dụng tương tác, hoặc trong bootstrap Config Data/EPP, full app test vẫn cần thiết. Runner và @SpringBootTest bổ sung cho nhau.

---

## 34. Cách tổ chức test suite trong repository

Một cách phân nhóm:

~~~text
src/test/java/
  example/config/
    RetrySettingsTest.java
    GatewayConstraintsTest.java
    GatewayBinderTest.java
    GatewayPropertiesContextTest.java
  example/autoconfigure/
    AuditAutoConfigurationTest.java
  example/integration/
    ProductionConfigDataTest.java
    EnvironmentProcessorDiscoveryTest.java
    GatewayApplicationTest.java
~~~

Tên thư mục chỉ minh họa. Mục tiêu là cho người đọc biết test đang kiểm tra logic object, binder, context hay integration.

### 34.1. Chạy test nhanh trong mỗi thay đổi nhỏ

Các test object/Binder/Runner có thể được chạy trong vòng lặp phát triển nhanh. Những test full app hoặc container có thể được tổ chức thành một nhóm integration suite theo cách build/CI của dự án.

Nhưng đừng trì hoãn test tích hợp quá lâu nếu thay đổi liên quan trực tiếp Config Data, profile hoặc một extension bootstrap quan trọng. Khi rủi ro nằm ở hệ thống tích hợp, test phù hợp nên chạy trước release.

### 34.2. Không để test phụ thuộc vào thứ tự

Mỗi bài test phải tự tạo dữ liệu và context cần thiết. Không dựa vào test A set System properties rồi test B vô tình được lợi từ đó. Cách này rất dễ thất bại khi CI chạy song song.

---

## 35. Kiểm thử lỗi startup sao cho rõ nguyên nhân

Khi test mong muốn ApplicationContext fail:

~~~java
runner.withPropertyValues(
    "app.gateway.timeout=5s",
    "app.gateway.pool.max-connections=0",
    "app.gateway.endpoints[0].host=alpha.example.test",
    "app.gateway.endpoints[0].port=8080"
).run(context -> {
    assertThat(context).hasFailed();
});
~~~

Chỉ kiểm tra hasFailed là bước đầu. Để tăng ý nghĩa, cần biết failure do constraint @Min(1) của pool chứ không do thiếu một bean không liên quan.

Có thể kiểm tra **context.getStartupFailure()** và cause chain, nhưng kiểu exception/message cụ thể có thể thay đổi theo phiên bản Spring Boot.

### 35.1. Không phụ thuộc toàn bộ chuỗi log

Tránh assert nguyên văn nhiều dòng của báo lỗi như khoảng trắng, thứ tự field và thông điệp nội bộ. Tập trung vào dấu hiệu đáng tin cậy: loại lỗi binding/validation, property path và constraint khi chúng được biểu diễn ổn định.

### 35.2. Một test lỗi chỉ nên có một nguyên nhân chính

Nếu test muốn kiểm tra pool.maxConnections=0, hãy cung cấp endpoint và timeout hợp lệ. Nếu thiếu cả endpoint và timeout, context có thể fail vì nguyên nhân khác nên bài test không còn đáng tin.

---

## 36. Từng bước viết bộ test tối thiểu cho một nhóm config mới

Giả sử vừa thêm:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        Duration timeout,
        int maxRetries
) {}
~~~

Có thể thực hiện:

**Bước A — xác định hợp đồng dữ liệu:** timeout phải dương, maxRetries trong khoảng hợp lệ, có hay không default, tên canonical là gì.

**Bước B — nếu có invariant Java:** viết unit test constructor/validation thuần, không cần context.

**Bước C — nếu có conversion quan trọng:** viết Binder test từ **app.notification.timeout=250ms** và **app.notification.max-retries=3**.

**Bước D — nếu có @Validated hoặc conditional bean:** viết ApplicationContextRunner test cho một case valid và một invalid.

**Bước E — nếu cấu hình phụ thuộc profile, import hoặc bootstrap:** viết một full app integration test chứng minh nguồn cuối cùng và bean sử dụng đúng.

**Bước F — khi sửa lỗi production:** chọn đúng mức tái hiện nguyên nhân, đồng thời bảo toàn integration test đại diện nếu bug phát sinh tại ranh giới nhiều thành phần.

Đó là một chiến lược hiệu quả hơn việc mặc định tạo @SpringBootTest cho từng field.

---

## 37. Bài thực hành 1: chọn mức thấp nhất

Hãy chọn một trong bốn mức cho từng câu hỏi:

1. **List.copyOf** có bảo vệ component record khỏi bị sửa?
2. Chuỗi **"5s"** có được bind vào Duration đúng?
3. @NotBlank trong object con có làm context fail khi @Valid được khai báo?
4. File application-prod.yml có được nạp khi bật profile prod?
5. @ConditionalOnProperty chỉ đăng ký bean khi flag true?
6. spring.factories có khám phá EnvironmentPostProcessor trong JAR không?

Đáp án gợi ý:

~~~text
1 -> Đối tượng
2 -> Binder
3 -> ApplicationContextRunner
4 -> Ứng dụng đầy đủ / SpringApplication Config Data
5 -> ApplicationContextRunner
6 -> Ứng dụng đầy đủ / SpringApplication discovery
~~~

Không nên trả lời “@SpringBootTest cho cả sáu” chỉ vì nó có thể bao trùm nhiều hơn. Điều đó làm test suite nặng mà không giúp khoanh vùng tốt hơn.

## 38. Bài thực hành 2: Binder hay Validator?

Cho record:

~~~java
public record RetrySettings(
        @Min(1) int attempts,
        Duration backoff
) {}
~~~

Với property:

~~~properties
retry.attempts=0
retry.backoff=3s
~~~

Một Binder test có thể xác nhận **attempts=0** và **backoff=PT3S** được bind thành công về mặt kiểu, trừ khi có constructor invariant hoặc handler đặc biệt. Nhưng điều đó **chưa đủ** để chứng minh @Min(1) được thực thi.

Cần kiểm tra @Min(1) bằng Jakarta Validator trực tiếp hoặc ApplicationContextRunner với bean @ConfigurationProperties được @Validated và validation provider.

**Ý chính:** Binding và validation là hai cơ chế khác nhau.

## 39. Bài thực hành 3: ContextRunner hay full application?

Một module có:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "feature.export",
    name = "enabled",
    havingValue = "true"
)
ExportService exportService() { ... }
~~~

Mục tiêu: khi flag false bean không xuất hiện.

**Chọn ApplicationContextRunner.** Nó cho phép đưa false vào context nhỏ và kiểm tra bean không tồn tại.

Nếu câu hỏi trở thành: “Trong môi trường prod, file import từ vị trí bên ngoài đã đặt feature.export.enabled=true nên ứng dụng thực tạo ExportService?” thì chọn **full SpringApplication** vì cần xác minh Config Data và runtime wiring.

## 40. Bài thực hành 4: kiểm tra nguồn env thật

Dev viết:

~~~java
runner.withPropertyValues(
    "APP_GATEWAY_POOL_MAXCONNECTIONS=20"
)
~~~

rồi kết luận hệ điều hành sẽ chuyển tên env đó đúng.

Kết luận này chưa đủ cơ sở, vì withPropertyValues không nhất thiết đại diện cho OS environment PropertySource. Cần một test có system environment semantics phù hợp hoặc chạy JVM con với env var thật.

Đồng thời phải biết canonical key là:

~~~text
app.gateway.pool.max-connections
~~~

và tên env chuẩn là:

~~~text
APP_GATEWAY_POOL_MAXCONNECTIONS
~~~

## 41. Bài thực hành 5: missing, invalid và override

Cho một cấu hình:

~~~yaml
app:
  pool:
    max-connections: 20
~~~

Tạo ba case:

1. Không có app.pool.*.
2. app.pool.max-connections=0.
3. File nền có 20 nhưng profile prod có 40.

Đề xuất:

- Case 1: Binder nếu chỉ xem kết quả thiếu, hoặc Runner nếu xem bean @NotNull/@Min có fail.
- Case 2: Runner nếu mục tiêu là @Validated phát hiện @Min(1).
- Case 3: Full application nếu muốn chứng minh Config Data profile precedence.

Cần mô tả mục tiêu trước khi chọn kỹ thuật; cùng input có thể được test ở những tầng khác nhau vì câu hỏi cần chứng minh khác nhau.

## 42. Bài thực hành 6: đọc lỗi từ context

Một runner test có:

~~~properties
app.gateway.pool.max-connections=0
app.gateway.timeout=abc
~~~

Nó fail. Bạn có thể kết luận @Min(1) hoạt động không?

**Không.** Giá trị timeout=abc đã có thể gây lỗi conversion trước validation.

Sửa timeout thành **5s**, giữ pool.max-connections=0 và cung cấp những field bắt buộc khác hợp lệ. Khi đó test mới tập trung vào validation của pool.

## 43. Bài thực hành 7: tối ưu một test suite chậm

Một dự án có 60 @SpringBootTest riêng, mỗi test chỉ kiểm tra một giá trị Duration, int hoặc feature flag.

Hướng refactor hợp lý:

- Chuyển những case chỉ liên quan conversion sang Binder test.
- Chuyển conditional bean và @Validated startup sang ApplicationContextRunner.
- Giữ một số @SpringBootTest đại diện cho profile, import, discovery và wiring thực.
- Không bỏ hết integration tests; chỉ bỏ những phần lặp mà mức thấp đã chứng minh.
- Đo lại thời gian CI sau khi thay đổi; không giả định mọi dự án có cùng tốc độ.

Mục tiêu là **giảm chi phí mà vẫn giữ đúng ranh giới rủi ro**.

---

## 44. Checklist trước khi viết một bài test cấu hình

- [ ] Câu hỏi test cần chứng minh là gì, và cơ chế nào chịu trách nhiệm?
- [ ] Có cần khởi động Spring không, hay Java object đủ?
- [ ] Có cần Binder chuyển tên/kiểu property không?
- [ ] Có cần @ConfigurationProperties bean registration và @Validated không?
- [ ] Có cần @ConditionalOnProperty hoặc auto-configuration không?
- [ ] Có cần Config Data, profile, import hoặc EPP discovery không?
- [ ] Có cần HTTP server, datasource hoặc service ngoài thật không?
- [ ] Property được dùng trong test có thuộc đúng nguồn cần kiểm tra không?
- [ ] Test có vô tình override nguồn đang muốn kiểm tra không?
- [ ] Có case valid, missing, malformed và invalid phù hợp không?
- [ ] Các object con/List/Map có được kiểm tra đúng cấp không?
- [ ] Có secret thật trong fixture hoặc log không?
- [ ] Test có dùng static mutable state, System properties hoặc fixed port dễ gây flaky không?
- [ ] Test failure có khoanh vùng một nguyên nhân chính không?
- [ ] Có đang khởi động toàn ứng dụng cho một phép kiểm tra có thể làm ở Binder không?
- [ ] Nếu dùng full app, có lý do cụ thể về bootstrap/wiring/infrastructure không?

Một bài test tốt không nhất thiết nhiều dòng. Nó cần **phạm vi đúng, dữ liệu có chủ đích và kết luận không vượt quá những gì đã thực thi**.

## 45. Tổng kết

Bốn mức kiểm thử cấu hình phục vụ bốn câu hỏi khác nhau:

**Đối tượng thuần Java:** Các default, invariant, defensive copy và constraint được gọi tường minh có đúng không? Không kiểm tra YAML, Binder hay Spring context.

**Binder trực tiếp:** Một tập property được chuyển thành record/JavaBean, nested object, List/Map, Duration và kiểu số đúng không? Không tự chứng minh bean lifecycle, Config Data imports hoặc @Validated startup.

**ApplicationContextRunner:** Một context nhỏ có đăng ký, bind và validate @ConfigurationProperties đúng không? Conditional bean hoặc một auto-configuration cục bộ có tạo bean đúng khi property thay đổi không? Không mặc định mô phỏng toàn bộ SpringApplication bootstrap.

**Ứng dụng đầy đủ:** Profile, Config Data, EnvironmentPostProcessor, auto-configuration, dependency wiring và runtime integration có thực sự hoạt động với môi trường thử nghiệm được kiểm soát không? Chi phí cao hơn nhưng cần thiết cho những ranh giới không thể chứng minh ở mức thấp.

Quy tắc lựa chọn là **“mức thấp nhất chứng minh đủ hành vi cần kiểm tra”**, không phải “dùng mức mạnh nhất cho chắc chắn”. Một dự án Spring Boot có test suite hiệu quả khi kết hợp unit tests dễ chẩn đoán, Binder tests chuẩn xác, ApplicationContextRunner cho validation/conditions và một tập integration tests chọn lọc cho bootstrap cùng những thành phần phụ thuộc thật.
