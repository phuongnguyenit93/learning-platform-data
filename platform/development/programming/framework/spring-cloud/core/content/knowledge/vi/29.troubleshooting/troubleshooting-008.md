# Bean mới không xuất hiện sau khi đổi ConditionalOnProperty

## 1. Nhận diện đúng vấn đề

Một tình huống thường gặp khi phát triển Spring Boot/Spring Cloud là thêm hoặc đổi một property, nhưng bean được đánh dấu `@ConditionalOnProperty` vẫn không xuất hiện trong `ApplicationContext`. Ví dụ, ứng dụng đặt `inventory.remote.enabled=true` để bật client gọi dịch vụ từ xa, nhưng khi inject `InventoryClient` thì Spring báo `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException`.

Trước khi sửa annotation, cần phân biệt ba tình huống:

1. **Bean definition không được đăng ký:** điều kiện không khớp nên Spring bỏ qua cấu hình hoặc phương thức `@Bean`.
2. **Bean definition có nhưng instance chưa được tạo:** bean có thể đang lazy, thuộc scope chưa được kích hoạt hoặc chưa có nơi yêu cầu nó.
3. **Bean có tồn tại nhưng injection thất bại:** có thể thiếu dependency, sai kiểu, có nhiều bean cùng kiểu hoặc một điều kiện khác loại bean khỏi context.

Đặc biệt, `@ConditionalOnProperty` được đánh giá khi Spring xử lý cấu hình để tạo bean definition. Thay đổi property trong `Environment` sau khi ứng dụng đã khởi động không khiến Spring tự chạy lại điều kiện đó. `@RefreshScope` cũng chỉ làm mới target của bean thuộc scope; nó không đăng ký lại bean definition và không chạy lại toàn bộ quá trình auto-configuration.

Sau bài học, người đọc có thể:

- Kiểm tra chính xác property mà điều kiện đang đọc.
- Hiểu `prefix`, `name`, `havingValue` và `matchIfMissing`.
- Đọc `ConditionEvaluationReport` để tìm lý do điều kiện không khớp.
- Phân biệt bean definition bị bỏ qua với bean chưa khởi tạo hoặc lỗi injection.
- Viết test cho từng giá trị property bằng `ApplicationContextRunner`.
- Thiết kế cờ tính năng thay đổi lúc chạy mà không kỳ vọng `@ConditionalOnProperty` tự đăng ký lại bean.

## 2. @ConditionalOnProperty kiểm tra điều gì?

`@ConditionalOnProperty` đọc giá trị từ Spring `Environment`. Nó có thể đặt trên lớp `@Configuration` hoặc trên một phương thức `@Bean`.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
class RemoteInventoryConfiguration {

    @Bean
    InventoryClient inventoryClient() {
        return new InventoryClient();
    }
}
```

Điều kiện trên kiểm tra property đầy đủ `inventory.remote.enabled`. Chỉ khi giá trị bằng `true`, Spring mới đưa cấu hình này vào quá trình đăng ký bean.

### 2.1. prefix và name

- `prefix` là phần đầu của property key. Dấu chấm cuối được tự thêm nếu cần.
- `name` là một hoặc nhiều phần tên còn lại của property.
- Dùng dạng kebab-case cho tên property, ví dụ `client-enabled`.
- Nếu khai báo nhiều phần tử trong `name`, tất cả property phải thỏa điều kiện thì condition mới khớp.

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = {"enabled", "client-enabled"},
        havingValue = "true"
)
```

Điều kiện này cần cả `inventory.remote.enabled=true` và `inventory.remote.client-enabled=true`.

### 2.2. havingValue mặc định không có nghĩa là chỉ nhận true

Đây là một nguyên nhân phổ biến khiến bean xuất hiện hoặc biến mất ngoài dự kiến. Nếu không khai báo `havingValue`, Spring chỉ yêu cầu property tồn tại và khác chuỗi `false`; nó không yêu cầu giá trị phải là `true`.

| Giá trị trong Environment | `havingValue` không khai báo | `havingValue="true"` | `havingValue="false"` |
| --- | --- | --- | --- |
| `true` | Khớp | Khớp | Không khớp |
| `false` | Không khớp | Không khớp | Khớp |
| `yes` hoặc `on` | Khớp | Không khớp | Không khớp |
| `custom` | Khớp | Không khớp | Không khớp |
| Không có property | Không khớp mặc định | Không khớp mặc định | Không khớp mặc định |

Nếu property là boolean feature flag, nên khai báo rõ `havingValue = "true"` để tránh giá trị bất kỳ khác `false` vô tình bật bean.

### 2.3. matchIfMissing

`matchIfMissing` quyết định condition có khớp khi property hoàn toàn không tồn tại trong `Environment` hay không. Mặc định là `false`.

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
```

Với cấu hình này, bean được đăng ký khi property là `true` hoặc không được khai báo. Nếu property hiện diện với giá trị `false`, condition không khớp.

Hãy chọn mặc định theo ý nghĩa sản phẩm:

- `matchIfMissing = false`: feature chỉ bật khi được cấu hình rõ ràng.
- `matchIfMissing = true`: feature bật mặc định nếu không có cấu hình ghi đè.

Đừng thay `matchIfMissing` chỉ để làm mất lỗi `NoSuchBeanDefinitionException`; việc đó có thể bật một integration mà môi trường hiện tại không mong muốn.

### 2.4. Không dùng @ConditionalOnProperty để kiểm tra collection

`@ConditionalOnProperty` không đáng tin cậy khi kiểm tra property collection/indexed. Ví dụ `inventory.targets[0]` có thể tồn tại nhưng condition kiểm tra `inventory.targets` lại không khớp như mong đợi.

Nếu cần quyết định dựa trên danh sách, hãy dùng một custom `Condition` đọc và kiểm tra cấu trúc property, hoặc dùng một property boolean riêng như `inventory.targets.enabled`.

Với Spring Boot từ 3.5, `@ConditionalOnBooleanProperty` là lựa chọn rõ nghĩa hơn cho property boolean: mặc định yêu cầu giá trị `true`, vẫn hỗ trợ `matchIfMissing`. Với baseline cũ hơn, dùng `@ConditionalOnProperty(havingValue = "true")`.

### 2.5. Đặt condition trên lớp hay trên phương thức @Bean

- Đặt trên lớp `@Configuration`: nếu condition không khớp, cấu hình đó không được xử lý và các phương thức `@Bean` bên trong không đăng ký bean.
- Đặt trên một phương thức `@Bean`: chỉ bean do phương thức đó cung cấp bị bỏ qua; các bean khác trong cùng lớp cấu hình vẫn có thể được đăng ký.

Nếu một lớp cấu hình chứa nhiều integration độc lập, đặt condition trên từng phương thức `@Bean` có thể giữ các bean không liên quan hoạt động. Nếu toàn bộ cấu hình chỉ có ý nghĩa khi feature bật, condition ở cấp lớp dễ diễn đạt hơn.

## 3. Condition được đánh giá lúc nào?

Spring xử lý cấu hình, đánh giá các điều kiện và đăng ký bean definition khi tạo `ApplicationContext`. Với cấu hình:

```java
@Configuration(proxyBeanMethods = false)
class InventoryConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "inventory.remote",
            name = "enabled",
            havingValue = "true"
    )
    InventoryClient inventoryClient() {
        return new InventoryClient();
    }
}
```

Nếu `inventory.remote.enabled=false` lúc context khởi động, bean definition `inventoryClient` không được đăng ký. Khi property đổi thành `true` sau đó, bean definition vẫn không tự xuất hiện.

### 3.1. Context refresh không chạy lại condition

Trong Spring Cloud, `ContextRefresher.refresh()` cập nhật Environment từ property source và kích hoạt các cơ chế refresh/rebind được hỗ trợ. `@RefreshScope` dùng proxy và cache target; khi refresh, cache target bị xóa để target mới được tạo ở lần gọi tiếp theo.

Luồng đó không tương đương với việc hủy và tạo lại toàn bộ `ApplicationContext`. Các lớp cấu hình đã được xử lý và các điều kiện `@ConditionalOnProperty` không tự được đánh giá lại để thêm hoặc gỡ bean definition.

Vì vậy, ví dụ sau không biến condition thành feature toggle động:

```java
@Configuration
@RefreshScope
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true"
)
class RemoteInventoryConfiguration {

    @Bean
    RemoteInventoryClient remoteInventoryClient() {
        return new RemoteInventoryClient();
    }
}
```

Đặt `@RefreshScope` trên lớp `@Configuration` không có nghĩa mọi bean được khai báo bên trong tự trở thành refresh-scoped, cũng không làm Spring đăng ký lại các phương thức `@Bean` khi property đổi.

### 3.2. Khi nào cần restart?

Nếu feature được chọn bằng `@ConditionalOnProperty` và cần thay đổi tập bean trong context, lựa chọn đơn giản, dễ dự đoán là khởi động lại process/context với cấu hình mới. Điều này thường phù hợp cho:

- Chọn implementation theo môi trường triển khai.
- Bật/tắt adapter tới hệ thống bên ngoài.
- Chọn database driver hoặc messaging provider.
- Cấu hình integration cần dependency hoặc lifecycle riêng.

Nếu cần chuyển trạng thái ngay khi ứng dụng đang chạy, hãy dùng một bean ổn định làm router/policy và để bean đó đọc feature flag có thể cập nhật. Không dùng condition để thay đổi topology bean động.

## 4. Quy trình chẩn đoán theo thứ tự

### Bước 1: Xác nhận bean có thực sự vắng mặt

Kiểm tra bean theo tên và kiểu trong `ApplicationContext`:

```java
String[] names = applicationContext.getBeanNamesForType(InventoryClient.class);
log.info("InventoryClient bean names: {}", Arrays.toString(names));
```

Nếu mảng rỗng, bean definition không được tìm thấy theo kiểu đó. Nếu có tên bean nhưng `getBean()` thất bại, điều kiện có thể đã khớp nhưng quá trình tạo instance hoặc dependency injection đang lỗi.

Có thể phân biệt thêm:

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| `NoSuchBeanDefinitionException` | Bean definition không được đăng ký hoặc lookup sai tên/kiểu |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng kiểu, cần qualifier hoặc primary |
| `UnsatisfiedDependencyException` | Bean cần inject không có hoặc dependency bên trong không tạo được |
| Bean name có trong context nhưng chưa có instance | Kiểm tra `@Lazy`, scope và nơi sử dụng |
| ApplicationContext khởi động thất bại | Đọc exception gốc và condition report; lỗi có thể xảy ra trước khi context sẵn sàng |

`getBeansOfType()` có thể khởi tạo các singleton lazy tùy trường hợp. Khi chỉ muốn xác nhận bean name, ưu tiên `getBeanNamesForType()` và xem bean definition thay vì vô tình kích hoạt toàn bộ bean.

### Bước 2: Đọc giá trị thực tế trong Environment

Đừng chỉ nhìn file `application.yml`. Giá trị có thể bị ghi đè bởi:

- Profile đang active.
- Environment variable.
- Java system property.
- Command-line argument.
- Config Data import hoặc remote configuration.
- Test property source.
- `@TestPropertySource` hoặc `@DynamicPropertySource`.

Có thể log giá trị đã resolve khi chẩn đoán:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class InventoryFeatureDiagnostics implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryFeatureDiagnostics.class);
    private final Environment environment;

    InventoryFeatureDiagnostics(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("inventory.remote.enabled={}",
                environment.getProperty("inventory.remote.enabled"));
    }
}
```

Chỉ log các feature flag không nhạy cảm. Không dump toàn bộ `Environment` hoặc in secret, password, token và thông tin kết nối ra log.

Nếu có Actuator, endpoint `env` có thể giúp xem property source và nguồn của giá trị. Endpoint này có thể tiết lộ thông tin nhạy cảm; chỉ expose trong môi trường quản trị, giới hạn role và bật sanitization phù hợp.

### Bước 3: So khớp key với annotation

Đối chiếu từng phần:

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true"
)
```

Với YAML:

```yaml
inventory:
  remote:
    enabled: true
```

Property đầy đủ là `inventory.remote.enabled`. Các lỗi thường gặp:

- Sai prefix, ví dụ `inventory.remotes` thay vì `inventory.remote`.
- Sai tên property, ví dụ `enable` thay vì `enabled`.
- Đặt property ở sai cấp YAML.
- Dùng `inventory.remote.enabled` nhưng annotation lại kiểm tra `inventory.client.enabled`.
- Khai báo nhiều `name` nhưng chỉ một property được đặt.

### Bước 4: Kiểm tra havingValue và matchIfMissing

Ghi rõ ba thông tin: property có tồn tại không, giá trị thực tế là gì, annotation mong đợi giá trị nào. Đặc biệt kiểm tra trường hợp property vắng mặt và giá trị mặc định.

Nếu muốn boolean true, ưu tiên:

```java
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Tránh dựa vào mặc định `havingValue` nếu property có thể nhận giá trị ngoài `true`/`false`.

### Bước 5: Kiểm tra profile và thứ tự nạp cấu hình

Xác nhận profile thực tế bằng `Environment.getActiveProfiles()` và kiểm tra file tương ứng như `application-dev.yml`, `application-test.yml` hoặc profile được kích hoạt từ deployment.

Với Config Data hoặc Config Server, xác nhận nguồn cấu hình đã được nạp trước khi bean definition được tạo. Một property chỉ xuất hiện sau một sự kiện refresh không thể quay ngược thời gian để làm condition đã chạy trước đó khớp.

### Bước 6: Kiểm tra vị trí cấu hình và component scan

Condition chỉ được xét nếu Spring thực sự phát hiện cấu hình hoặc phương thức `@Bean`:

- Lớp `@Configuration` có nằm trong component scan không?
- Có được import bằng `@Import` hoặc đăng ký qua auto-configuration không?
- Package của lớp ứng dụng chính có bao phủ package cấu hình không?
- Có profile hoặc condition khác trên lớp cha không?
- Phương thức `@Bean` có bị đặt trong cấu hình không được import?

Nếu cấu hình không được phát hiện, việc sửa `havingValue` không giải quyết được nguyên nhân.

### Bước 7: Kiểm tra condition khác và bean conflict

Một bean có thể chịu nhiều điều kiện: `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@Profile`, `@ConditionalOnWebApplication` hoặc custom `Condition`. Nếu một điều kiện không khớp, bean vẫn không được đăng ký dù `@ConditionalOnProperty` đúng.

Ngoài ra, `@ConditionalOnMissingBean` có thể khiến auto-configuration lùi lại khi đã có bean do người dùng cung cấp. Kiểm tra bean cùng kiểu, bean name, `@Primary` và `@Qualifier` trước khi kết luận property condition sai.

## 5. Dùng ConditionEvaluationReport để tìm điều kiện không khớp

Spring Boot tạo `ConditionEvaluationReport` để giải thích các quyết định auto-configuration. Đây là công cụ phù hợp khi bean đến từ starter hoặc auto-configuration.

### 5.1. Bật debug khi khởi động

Chạy ứng dụng với `--debug`:

```bash
java -jar inventory-service.jar --debug
```

Hoặc:

```bash
java -Ddebug=true -jar inventory-service.jar
```

Tìm phần condition report và tên cấu hình liên quan. Các mục negative match thường cho biết property nào thiếu hoặc không có giá trị mong đợi.

### 5.2. Dùng Actuator conditions endpoint

Nếu ứng dụng có Actuator, endpoint `conditions` hiển thị report dưới dạng JSON. Đường dẫn mặc định:

```text
/actuator/conditions
```

Endpoint Actuator không được expose qua HTTP chỉ vì dependency đã có. Có thể cấu hình rõ trong môi trường chẩn đoán:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - conditions
```

Endpoint này hữu ích để kiểm tra vì sao một auto-configuration được áp dụng hoặc bị bỏ qua. Hãy bảo vệ nó bằng authentication/authorization và chỉ expose ở management network phù hợp; condition report có thể tiết lộ tên class, package và cấu trúc nội bộ.

### 5.3. Đọc report đúng cách

Khi tìm thấy cấu hình liên quan, kiểm tra:

1. Tên auto-configuration hoặc configuration class.
2. Condition nào khớp và condition nào không khớp.
3. Property key được kiểm tra.
4. Giá trị mong đợi và giá trị được tìm thấy.
5. Có condition khác trên cùng cấu hình hoặc bean method không.

Nếu bean là user configuration không thuộc auto-configuration report, hãy kiểm tra `ApplicationContext`, package scan, `@Import` và property trực tiếp. Không phải mọi lớp cấu hình do ứng dụng viết đều xuất hiện trong report theo cách giống auto-configuration.

## 6. Ví dụ hoàn chỉnh: cấu hình bean có điều kiện

Giả sử ứng dụng chỉ tạo client gọi Inventory API khi feature flag bật.

### 6.1. Property

```yaml
inventory:
  remote:
    enabled: true
    base-url: https://inventory.internal
```

### 6.2. Configuration

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
@ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class RemoteInventoryConfiguration {

    @Bean
    InventoryClient inventoryClient(InventoryProperties properties) {
        return new InventoryClient(properties.getBaseUrl());
    }
}
```

Nếu property thiếu hoặc bằng `false`, `InventoryClient` không được đăng ký. Khi feature flag có giá trị `true` từ đầu, bean mới xuất hiện trong context.

### 6.3. Đừng nhầm binding với condition

`@ConfigurationProperties` bind property vào object Java. `@ConditionalOnProperty` kiểm tra `Environment` để quyết định có đăng ký cấu hình hay không. Hai cơ chế liên quan tới cùng nguồn property nhưng có nhiệm vụ khác nhau.

Ví dụ class properties:

```java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory.remote")
public class InventoryProperties {

    private boolean enabled;
    private URI baseUrl;

    // getters and setters
}
```

Nếu `InventoryProperties` có giá trị `enabled=true` sau khi bind, điều đó không có nghĩa một bean bị condition loại lúc khởi động sẽ tự xuất hiện. Việc bind object không tự chạy lại quá trình đăng ký bean definition.

## 7. Kiểm thử các nhánh condition bằng ApplicationContextRunner

`ApplicationContextRunner` tạo một context nhỏ cho mỗi test. Đây là cách tốt để xác nhận property nào làm bean được đăng ký, đồng thời xem `ConditionEvaluationReport` mà không cần chạy cả ứng dụng.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class RemoteInventoryConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(RemoteInventoryConfiguration.class);

    @Test
    void registersClientWhenPropertyIsTrue() {
        contextRunner
                .withPropertyValues("inventory.remote.enabled=true")
                .run(context -> assertThat(context)
                        .hasSingleBean(InventoryClient.class));
    }

    @Test
    void skipsClientWhenPropertyIsFalse() {
        contextRunner
                .withPropertyValues("inventory.remote.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(InventoryClient.class));
    }

    @Test
    void skipsClientWhenPropertyIsMissing() {
        contextRunner
                .run(context -> assertThat(context)
                        .doesNotHaveBean(InventoryClient.class));
    }
}
```

Trong project thật, hãy cung cấp đúng bean `InventoryProperties` hoặc bật `@EnableConfigurationProperties(InventoryProperties.class)` trong test configuration. Nếu chạy như auto-configuration test, dùng `withConfiguration(AutoConfigurations.of(...))` để đăng ký auto-configuration theo đúng cơ chế Spring Boot.

### 7.1. Kiểm tra matchIfMissing

Nếu annotation đặt `matchIfMissing = true`, thêm test xác nhận bean xuất hiện khi property không có:

```java
@Test
void registersClientWhenPropertyIsMissingAndMatchIfMissingIsTrue() {
    new ApplicationContextRunner()
            .withUserConfiguration(DefaultEnabledInventoryConfiguration.class)
            .run(context -> assertThat(context)
                    .hasSingleBean(InventoryClient.class));
}
```

Test cần dùng cấu hình có `matchIfMissing = true`. Không dùng cùng một context cho nhiều giá trị property rồi kỳ vọng condition chạy lại; mỗi lần `run` tạo một context mới.

### 7.2. Kiểm tra giá trị không phải true

Nếu annotation yêu cầu `havingValue = "true"`, thêm test với `yes`, `on` hoặc một chuỗi tùy ý để chứng minh các giá trị này không bật bean.

```java
@Test
void doesNotTreatArbitraryValueAsTrue() {
    contextRunner
            .withPropertyValues("inventory.remote.enabled=yes")
            .run(context -> assertThat(context)
                    .doesNotHaveBean(InventoryClient.class));
}
```

## 8. Khi cần đổi feature flag trong lúc ứng dụng đang chạy

Nếu yêu cầu nghiệp vụ là bật/tắt một hành vi ngay khi process đang chạy, hãy giữ bean definition ổn định và thay đổi quyết định bên trong bean. `@ConditionalOnProperty` phù hợp để quyết định có tạo integration lúc startup hay không; nó không phải runtime feature switch.

### 8.1. Dùng một policy bean refreshable

Ví dụ policy đọc property mỗi khi target được tạo:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class InventoryRoutingPolicy {

    @Value("${inventory.remote.enabled:false}")
    private boolean remoteEnabled;

    public boolean useRemoteClient() {
        return remoteEnabled;
    }
}
```

Service inject policy proxy và chọn implementation:

```java
@Service
public class InventoryService {

    private final InventoryRoutingPolicy routingPolicy;
    private final RemoteInventoryClient remoteClient;
    private final LocalInventoryClient localClient;

    public InventoryService(
            InventoryRoutingPolicy routingPolicy,
            RemoteInventoryClient remoteClient,
            LocalInventoryClient localClient) {
        this.routingPolicy = routingPolicy;
        this.remoteClient = remoteClient;
        this.localClient = localClient;
    }

    public Inventory find(String id) {
        if (routingPolicy.useRemoteClient()) {
            return remoteClient.find(id);
        }
        return localClient.find(id);
    }
}
```

Hai client được tạo ổn định trong context. Khi property đổi và refresh thành công, target của `InventoryRoutingPolicy` được tạo lại; lần gọi tiếp theo đọc giá trị mới. Không có bean definition nào được thêm hoặc xóa.

Mẫu này chỉ phù hợp khi cả hai implementation có thể tồn tại an toàn cùng lúc. Nếu một integration không thể khởi tạo khi feature tắt, hãy giữ integration sau một abstraction ổn định, hoặc dùng restart/redeploy để thay đổi topology bean.

### 8.2. Điều kiện để refresh policy

Đối với Spring Cloud Context:

1. `spring.cloud.refresh.enabled` phải được bật trong chế độ chạy hỗ trợ refresh.
2. Property source phải nhận được giá trị mới.
3. Ứng dụng phải gọi `ContextRefresher.refresh()` hoặc endpoint refresh đã được expose và bảo vệ.
4. `InventoryRoutingPolicy` phải được Spring quản lý và được inject qua proxy.

Refresh Scope không hỗ trợ Spring AOT transformations và native images. Trong các chế độ đó, dùng restart/redeploy hoặc cơ chế cấu hình động riêng phù hợp với runtime.

### 8.3. Khi cần thay đổi tập bean thực sự

Nếu một feature yêu cầu thêm hoặc gỡ bean, thay đổi datasource, message listener container hoặc kết nối có lifecycle riêng, hãy cân nhắc:

- Restart/redeploy instance với cấu hình mới.
- Tạo một abstraction/router ổn định và quản lý lifecycle của resource bên trong nó.
- Dùng plugin/module architecture có API đăng ký và gỡ module được thiết kế rõ ràng.

Không dùng `@ConditionalOnProperty` như cơ chế bật/tắt module động. Tự đăng ký hoặc xóa bean definition trong runtime đòi hỏi quản lý dependency, destruction callback, thread, connection và concurrency; chỉ nên làm khi có kiến trúc lifecycle cụ thể.

## 9. Các nguyên nhân khác khiến bean không được inject

Sau khi condition đã khớp, vẫn có thể gặp lỗi do:

| Nguyên nhân | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| Cấu hình không nằm trong component scan | Không thấy configuration hoặc bean | Kiểm tra package của `@SpringBootApplication`, `@Import` |
| Profile không active | `@Profile` trên configuration không khớp | Kiểm tra `spring.profiles.active` |
| Dependency thiếu | Bean method không thể tạo hoặc auto-configuration bị bỏ qua | Kiểm tra runtime classpath và `@ConditionalOnClass` |
| Bean bị `@ConditionalOnMissingBean` loại | Một bean cùng kiểu đã được đăng ký trước | Tìm bean cùng kiểu/name và thứ tự auto-configuration |
| Nhiều bean cùng interface | `NoUniqueBeanDefinitionException` | Dùng `@Qualifier` hoặc `@Primary` |
| Bean lazy | Definition có nhưng instance chưa được tạo | Kiểm tra `@Lazy` và điểm sử dụng |
| Scope không phù hợp | Bean chỉ tồn tại trong request/session hoặc custom scope | Kiểm tra scope và proxy |
| Dependency trong bean method lỗi | Context fail khi tạo bean | Đọc exception gốc và constructor dependency |
| Method `@Bean` không được gọi như kỳ vọng | Configuration proxy mode hoặc gọi trực tiếp method sai cách | Inject bean từ context, tránh tự gọi factory method |

## 10. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân ưu tiên kiểm tra | Hành động |
| --- | --- | --- |
| Property là `true` trong YAML nhưng condition không khớp | Giá trị ở Environment bị override hoặc key sai | Kiểm tra property source và key đầy đủ |
| Property không có nhưng bean mong muốn vẫn phải xuất hiện | `matchIfMissing` mặc định là false | Quyết định có nên đặt `matchIfMissing=true` |
| Property có giá trị `yes` mà bean được tạo | `havingValue` không khai báo | Dùng `havingValue="true"` hoặc `@ConditionalOnBooleanProperty` |
| Property đã đổi qua Config Server nhưng bean không xuất hiện | Condition chỉ được đánh giá lúc tạo context | Restart hoặc chuyển sang runtime policy bean |
| `@RefreshScope` đã refresh nhưng bean conditional vẫn thiếu | Refresh Scope chỉ xóa target cache | Không kỳ vọng refresh đăng ký lại bean definition |
| Condition đúng nhưng bean vẫn không inject được | Component scan, condition khác hoặc dependency lỗi | Đọc condition report và exception gốc |
| Bean name tồn tại nhưng chưa có instance | Lazy initialization hoặc scope | Kiểm tra `@Lazy`, scope và điểm gọi |
| Test lúc true pass, lúc false vẫn giữ bean | Dùng lại cùng context trong test | Mỗi trường hợp dùng một context mới |
| Condition kiểm tra danh sách không khớp | Property collection/indexed | Dùng custom `Condition` hoặc boolean flag riêng |

## 11. Checklist xử lý sự cố

1. Xác nhận bean đang thiếu là bean definition hay chỉ là instance chưa khởi tạo.
2. Đọc exception gốc thay vì chỉ nhìn lỗi injection cuối cùng.
3. In đúng property key từ `Environment`, không chỉ xem YAML.
4. Kiểm tra active profile và các property source có độ ưu tiên cao hơn.
5. Đối chiếu `prefix`, `name`, `havingValue` và `matchIfMissing`.
6. Nếu muốn boolean true, khai báo rõ `havingValue="true"`.
7. Kiểm tra mọi property trong `name` khi có nhiều tên.
8. Không dùng `@ConditionalOnProperty` để match collection/indexed property.
9. Bật `--debug` hoặc xem `/actuator/conditions` để đọc `ConditionEvaluationReport`.
10. Kiểm tra component scan, `@Import`, `@Profile`, classpath và condition khác.
11. Viết `ApplicationContextRunner` test cho true, false, missing và giá trị bất thường.
12. Nếu cần thay đổi hành vi runtime, dùng policy/strategy bean ổn định thay cho condition.
13. Nếu cần thay đổi tập bean, lên kế hoạch restart/redeploy hoặc lifecycle module rõ ràng.

## 12. Tài liệu tham khảo

- [Spring Boot 4.1 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): semantics của `prefix`, `name`, `havingValue`, `matchIfMissing` và giới hạn collection.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): property conditions, các condition annotation và kiểm thử bằng `ApplicationContextRunner`.
- [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html): `ConditionEvaluationReport`, `--debug` và Actuator `conditions` endpoint.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Refresh Scope, target cache và giới hạn Context Refresh.

`@ConditionalOnProperty` quyết định bean definition khi context được tạo. Nếu bean không xuất hiện, hãy kiểm tra property thực tế và condition report trước khi thay annotation. Nếu yêu cầu là đổi hành vi trong lúc chạy, hãy giữ bean ổn định và cập nhật policy; nếu yêu cầu là thay đổi cấu trúc bean, hãy tạo context mới hoặc triển khai lại với cấu hình mới.
