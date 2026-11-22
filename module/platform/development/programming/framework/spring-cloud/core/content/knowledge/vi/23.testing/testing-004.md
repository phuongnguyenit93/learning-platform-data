# Kiểm thử cấu hình mặc định và bean tùy biến thay thế

Bài học thuộc chương **Kiểm thử** của module **SPRING_CLOUD_CORE**. Spring Boot và Spring Cloud thường tạo bean mặc định bằng auto-configuration. Khi ứng dụng cung cấp bean riêng, auto-configuration có thể lùi lại nhờ điều kiện `@ConditionalOnMissingBean`. Cần kiểm thử cả hai nhánh: không có bean tùy biến thì default xuất hiện; có bean tùy biến đúng contract thì default không được tạo và consumer nhận đúng implementation của ứng dụng.

`ApplicationContextRunner` là công cụ phù hợp để kiểm thử các điều kiện này trong một Spring ApplicationContext nhỏ, nhanh và độc lập. Nó cho phép nạp auto-configuration, thêm user configuration, thay đổi property, mô phỏng classpath thiếu dependency và kiểm tra bean thực tế. Sau đó, `@SpringBootTest` có thể xác minh cấu hình hoạt động trong ứng dụng đầy đủ. Bài học cũng phân biệt custom bean production với mock hoặc bean override chỉ tồn tại trong test, vì hai cách này kiểm tra những hành vi khác nhau.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vì sao cần kiểm thử cả default bean và custom bean.
2. Phân biệt auto-configuration với user configuration trong test context.
3. Kiểm thử `@ConditionalOnMissingBean` bằng `ApplicationContextRunner`.
4. Xác minh default được tạo khi không có custom bean.
5. Xác minh custom bean đúng contract làm default back off.
6. Kiểm tra bean type, bean name, số lượng bean và implementation thực tế.
7. Kiểm thử condition theo property và optional class.
8. Đọc `ConditionEvaluationReport` khi kết quả không như mong đợi.
9. Dùng `@TestConfiguration` và `@Import` để bổ sung bean trong `@SpringBootTest`.
10. Phân biệt `@MockitoBean` với custom bean thay thế trong ứng dụng.
11. Hiểu vai trò của `@Primary`, `@Qualifier` và bean overriding trong test.
12. Kiểm thử tùy biến Spring Cloud LoadBalancer trong đúng service-specific context.
13. Xây dựng test matrix cho default, custom, disabled condition và dependency không có.
14. Tránh các test chỉ xác nhận context khởi động mà không kiểm tra implementation thực tế.

## 2. Vì sao phải kiểm thử cả hai nhánh?

Một auto-configuration thường cung cấp default để ứng dụng dùng ngay sau khi thêm starter. Khi người dùng cần hành vi khác, họ có thể cung cấp bean riêng theo extension point mà thư viện công bố.

Ví dụ:

~~~java
@AutoConfiguration
public class InventoryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(InventoryClient.class)
    DefaultInventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }
}
~~~

Bean mặc định chỉ được tạo khi context chưa có bean phù hợp với `InventoryClient`. Vì vậy có hai hành vi cần kiểm chứng:

- **Không có custom bean:** Spring tạo một `DefaultInventoryClient` và consumer có thể inject nó qua contract `InventoryClient`.
- **Có custom bean:** Spring dùng implementation do ứng dụng cung cấp; bean mặc định không được đăng ký.

Nếu chỉ kiểm tra trường hợp đầu, test không phát hiện được lỗi condition khiến default vẫn xuất hiện khi ứng dụng đã cung cấp implementation riêng. Nếu chỉ kiểm tra trường hợp custom, test không phát hiện việc thư viện vô tình bỏ mất default trong cấu hình tiêu chuẩn.

~~~mermaid
flowchart TD
    A["Khởi tạo test ApplicationContext"] --> B["Nạp auto-configuration"]
    B --> C{"Có bean InventoryClient do user cung cấp?"}
    C -->|Không| D["@ConditionalOnMissingBean khớp"]
    D --> E["Tạo DefaultInventoryClient"]
    C -->|Có| F["Condition không khớp"]
    F --> G["Default back off"]
    E --> H["Kiểm tra bean và hành vi"]
    G --> H
    H --> I["Test PASS khi đúng implementation được dùng"]
~~~

## 3. Tạo ví dụ auto-configuration có thể kiểm thử

Để minh họa, tạo một contract cho client gọi dịch vụ inventory:

~~~java
public interface InventoryClient {

    InventoryItem findById(String itemId);
}
~~~

Model trả về trong các ví dụ là một record đơn giản:

~~~java
public record InventoryItem(String id, String source) {
}
~~~

Implementation mặc định:

~~~java
public class DefaultInventoryClient implements InventoryClient {

    @Override
    public InventoryItem findById(String itemId) {
        return new InventoryItem(itemId, "default");
    }
}
~~~

Implementation tùy biến của ứng dụng:

~~~java
public class CustomInventoryClient implements InventoryClient {

    @Override
    public InventoryItem findById(String itemId) {
        return new InventoryItem(itemId, "custom");
    }
}
~~~

Auto-configuration:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class InventoryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(InventoryClient.class)
    DefaultInventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }
}
~~~

Chú ý ba điểm:

1. Bean method trả về kiểu cụ thể `DefaultInventoryClient` để Spring có đầy đủ type metadata.
2. Condition kiểm tra contract `InventoryClient`, không kiểm tra tên bean.
3. Custom implementation phải implement `InventoryClient` để đáp ứng đúng điều kiện.

Trong dự án thật, auto-configuration thường còn có condition về classpath, property hoặc discovery provider. Hãy giữ ví dụ test đồng bộ với condition trong code thực tế.

## 4. Chuẩn bị ApplicationContextRunner

### 4.1. Dependency kiểm thử

Với Maven, dependency test thường là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và các tiện ích kiểm thử Spring Boot. Nếu bài test dùng Mockito hoặc các integration của Spring TestContext, kiểm tra chúng đã có trong test classpath.

Auto-configuration test thường không cần khởi chạy web server hoặc toàn bộ ứng dụng. Dùng context runner giúp test nhanh và chỉ nạp đúng cấu hình đang được kiểm tra.

### 4.2. Khai báo runner dùng chung

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    InventoryAutoConfiguration.class
                            )
                    );
}
~~~

`AutoConfigurations.of(...)` yêu cầu runner nạp auto-configuration đang được kiểm thử. Đây là điểm quan trọng: nếu chỉ tạo một context bình thường mà không nạp auto-configuration, test có thể không chạy bean method mà bạn muốn xác minh.

Mỗi lần gọi `run(...)` tạo một context cho test case đó rồi đóng context sau khi callback hoàn tất. Có thể thêm user configuration hoặc property riêng cho từng test mà không làm nhiễm trạng thái giữa các case.

## 5. Kiểm thử default bean được tạo

Khi không có bean `InventoryClient` do ứng dụng cung cấp, điều kiện `@ConditionalOnMissingBean` phải khớp.

~~~java
@Test
void createsDefaultClientWhenNoCustomBeanExists() {
    contextRunner.run(context -> {
        assertThat(context).hasSingleBean(InventoryClient.class);
        assertThat(context).hasSingleBean(DefaultInventoryClient.class);

        InventoryClient client = context.getBean(InventoryClient.class);
        assertThat(client).isInstanceOf(DefaultInventoryClient.class);

        assertThat(client.findById("item-42").source())
                .isEqualTo("default");
    });
}
~~~

Test kiểm tra nhiều lớp:

- Contract `InventoryClient` có đúng một bean.
- Implementation mặc định có mặt.
- Bean được inject qua contract thực sự là `DefaultInventoryClient`.
- Hành vi của implementation đúng với default.

Không chỉ assert `hasBean("inventoryClient")`. Tên bean có thể thay đổi trong quá trình refactor; contract và behavior thường là bằng chứng quan trọng hơn.

Nếu record `InventoryItem` trong dự án không có accessor `source()`, thay assertion bằng field hoặc method thực tế của model. Mục đích là xác minh kết quả đến từ default implementation.

## 6. Kiểm thử custom bean làm default back off

### 6.1. Khai báo user configuration

Trong test, tạo cấu hình cung cấp implementation tùy biến:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
static class CustomInventoryConfiguration {

    @Bean
    CustomInventoryClient customInventoryClient() {
        return new CustomInventoryClient();
    }
}
~~~

Method trả về concrete type `CustomInventoryClient`, còn bean vẫn assignable với contract `InventoryClient`.

### 6.2. Nạp custom configuration cùng auto-configuration

~~~java
@Test
void customClientReplacesDefaultClient() {
    contextRunner
            .withUserConfiguration(CustomInventoryConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(CustomInventoryClient.class);
                assertThat(context).doesNotHaveBean(DefaultInventoryClient.class);

                InventoryClient client = context.getBean(InventoryClient.class);
                assertThat(client).isInstanceOf(CustomInventoryClient.class);

                assertThat(client.findById("item-42").source())
                        .isEqualTo("custom");
            });
}
~~~

Test này chứng minh:
1. User configuration đã được nạp.
2. Custom bean đúng contract đã có trong context.
3. Condition trên default bean không còn khớp.
4. Default implementation không được tạo.
5. Consumer inject contract nhận đúng custom implementation.

Spring Boot thiết kế auto-configuration để được nạp sau user-defined bean definitions. Vì thế, `ApplicationContextRunner` kết hợp `withUserConfiguration` phù hợp để kiểm tra hành vi back-off.

### 6.3. Kiểm tra số lượng bean theo contract

Assertion `hasSingleBean(InventoryClient.class)` rất hữu ích. Nếu default và custom cùng xuất hiện, test thất bại ngay cả khi `@Primary` khiến một implementation được inject.

Đây là khác biệt quan trọng: mục tiêu của back-off là default không được đăng ký khi custom bean thỏa condition đã tồn tại. Chỉ kiểm tra bean được inject có thể bỏ sót default vẫn còn trong context.

## 7. Kiểm thử bean không đúng contract

Một custom bean không implement contract được condition kiểm tra sẽ không làm default back off.

Ví dụ một bean khác type:

~~~java
public class InventoryClientAdapter {
    // Không implements InventoryClient.
}
~~~

Test có thể nạp bean này:

~~~java
@Test
void unrelatedBeanDoesNotReplaceDefault() {
    contextRunner
            .withBean(InventoryClientAdapter.class, InventoryClientAdapter::new)
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(DefaultInventoryClient.class);
                assertThat(context.getBean(InventoryClient.class))
                        .isInstanceOf(DefaultInventoryClient.class);
            });
}
~~~

Kết quả mong đợi là default vẫn được tạo vì condition kiểm tra `InventoryClient`, còn `InventoryClientAdapter` không phải implementation của contract đó.

Tình huống này giúp phát hiện lỗi phổ biến: ứng dụng đã khai báo một bean có tên hoặc chức năng gần giống nhưng không đúng type mà auto-configuration đang tìm.

## 8. Kiểm thử theo property

Auto-configuration thường có cả điều kiện property và missing-bean condition.

Ví dụ:

~~~java
@AutoConfiguration
public class InventoryPropertyAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.inventory",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    @ConditionalOnMissingBean(InventoryClient.class)
    DefaultInventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }
}
~~~

Vì đây là biến thể auto-configuration có thêm property condition, tạo runner riêng để các test sau thực sự nạp đúng class:

~~~java
private final ApplicationContextRunner propertyContextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                InventoryPropertyAutoConfiguration.class
                        )
                );
~~~

Với cấu hình này, default được tạo khi:
- `app.inventory.enabled` bằng `true`; hoặc property chưa được khai báo vì `matchIfMissing=true`.
- Chưa có bean phù hợp với `InventoryClient`.

Kiểm thử property tắt:

~~~java
@Test
void doesNotCreateDefaultWhenInventoryIsDisabled() {
    propertyContextRunner
            .withPropertyValues("app.inventory.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(InventoryClient.class);
                assertThat(context).doesNotHaveBean(DefaultInventoryClient.class);
            });
}
~~~

Kiểm thử property bật:

~~~java
@Test
void createsDefaultWhenInventoryIsEnabled() {
    propertyContextRunner
            .withPropertyValues("app.inventory.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(DefaultInventoryClient.class);
            });
}
~~~

Kiểm thử custom bean khi property tắt:

~~~java
@Test
void customBeanCanExistWhenDefaultFeatureIsDisabled() {
    propertyContextRunner
            .withPropertyValues("app.inventory.enabled=false")
            .withUserConfiguration(CustomInventoryConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(InventoryClient.class);
                assertThat(context).hasSingleBean(CustomInventoryClient.class);
                assertThat(context).doesNotHaveBean(DefaultInventoryClient.class);
            });
}
~~~

Test thứ hai xác minh hai cơ chế độc lập: property ngăn default auto-configuration tạo bean, còn user configuration vẫn có thể cung cấp bean của ứng dụng. Nếu nghiệp vụ yêu cầu property tắt phải cấm mọi implementation, cần thêm condition hoặc validation tương ứng; `@ConditionalOnProperty` trên default bean tự nó không cấm user configuration.

## 9. Kiểm thử optional dependency và classpath condition

Một số auto-configuration chỉ hoạt động khi thư viện/provider có mặt trên classpath. Ví dụ cấu hình cần SDK tùy chọn:

~~~java
@AutoConfiguration
public class OptionalInventoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(InventorySdk.class)
    static class SdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(InventoryClient.class)
        DefaultInventoryClient inventoryClient() {
            return new DefaultInventoryClient();
        }
    }
}
~~~

Đặt class tham chiếu SDK trong nested configuration giúp cô lập dependency tùy chọn. Khi SDK không có trên classpath, nested configuration không được áp dụng.

Dùng `FilteredClassLoader` để mô phỏng tình huống thiếu SDK:

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void skipsSdkConfigurationWhenSdkIsMissing() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(
                            OptionalInventoryAutoConfiguration.class
                    )
            )
            .withClassLoader(
                    new FilteredClassLoader(InventorySdk.class)
            )
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(InventoryClient.class);
            });
}
~~~

Test này đặc biệt hữu ích cho starter có nhiều integration như Eureka, Consul hoặc Zookeeper. Mỗi provider có thể chỉ được kích hoạt khi class tương ứng có trên classpath và các condition khác cùng thỏa mãn.

## 10. Đọc ConditionEvaluationReport trong test

Khi test không tạo default hoặc custom bean không làm default back off, hãy đọc condition report thay vì đoán.

Có thể gắn listener vào runner:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .withConfiguration(
                        AutoConfigurations.of(
                                InventoryAutoConfiguration.class
                        )
                );
~~~

Report giúp nhận diện:
- Condition classpath có khớp hay không.
- Bean condition tìm thấy bean nào.
- Property condition đọc được giá trị gì.
- Auto-configuration nào được áp dụng.
- Bean method nào bị bỏ qua.

Ví dụ, nếu report nói condition tìm thấy bean `InventoryClient`, default đã back off theo đúng thiết kế. Nếu report nói thiếu `InventorySdk`, hãy kiểm tra dependency test classpath thay vì thay condition.

Trong ứng dụng đầy đủ, có thể dùng Actuator `/actuator/conditions` nếu endpoint đã được expose và bảo vệ. Tuy nhiên, với auto-configuration unit/context test, report trực tiếp từ runner thường nhanh và chính xác hơn.

## 11. Kiểm thử với @SpringBootTest và @TestConfiguration

`ApplicationContextRunner` tập trung kiểm tra auto-configuration. Sau khi test đó PASS, có thể thêm integration test để xác minh cấu hình custom được dùng trong ứng dụng đầy đủ.

### 11.1. Import test configuration

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(InventoryOverrideIntegrationTest.CustomConfiguration.class)
class InventoryOverrideIntegrationTest {

    @Autowired
    InventoryClient inventoryClient;

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void applicationUsesCustomInventoryClient() {
        assertThat(inventoryClient)
                .isInstanceOf(CustomInventoryClient.class);

        assertThat(applicationContext.getBeansOfType(InventoryClient.class))
                .hasSize(1);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class CustomConfiguration {

        @Bean
        CustomInventoryClient customInventoryClient() {
            return new CustomInventoryClient();
        }
    }
}
~~~

`@TestConfiguration` khai báo bean bổ sung cho test mà không thay thế cấu hình ứng dụng chính. Dùng `@Import` để nạp cấu hình test một cách tường minh.

### 11.2. Khi nào cần test này?

Dùng `@SpringBootTest` khi muốn xác minh:
- Component thực tế inject đúng custom bean.
- Các auto-configuration khác trong ứng dụng không tạo thêm implementation cùng contract.
- Profile và property của ứng dụng không làm thay đổi kết quả dự kiến.
- Custom bean hoạt động với các dependency, proxy và lifecycle thật.

Không cần dùng `@SpringBootTest` cho mọi tổ hợp condition. Context đầy đủ khởi động chậm hơn và làm test phụ thuộc nhiều cấu hình ngoài phạm vi cần kiểm tra.

## 12. Phân biệt custom bean với mock bean trong test

Một điểm dễ nhầm là dùng mock để thay dependency trong test rồi kết luận auto-configuration back off đúng.

### 12.1. @MockitoBean dùng để thay dependency của test

Trong Spring Framework hiện đại, `@MockitoBean` có thể thay bean trong test ApplicationContext bằng Mockito mock:

~~~java
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class InventoryServiceTests {

    @MockitoBean
    InventoryRepository inventoryRepository;

    @Autowired
    InventoryService inventoryService;

    @Test
    void returnsItemFromRepository() {
        given(inventoryRepository.findById("item-42"))
                .willReturn(Optional.of(new InventoryItem("item-42", "test")));

        InventoryItem item = inventoryService.findById("item-42");

        assertThat(item.id()).isEqualTo("item-42");
        then(inventoryRepository).should().findById("item-42");
    }
}
~~~

Các import Mockito dùng trong ví dụ:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
~~~

Test này kiểm tra logic của `InventoryService` khi repository được thay bằng mock. Nó không chứng minh auto-configuration của `InventoryClient` đã back off theo custom production bean.

`@MockitoBean` thường dùng chiến lược replace-or-create: nếu bean phù hợp có mặt thì thay; nếu chưa có thì tạo mock. Có thể dùng `enforceOverride=true` khi muốn test thất bại nếu bean mục tiêu không tồn tại.

Mock thay thế được đăng ký trực tiếp trong test context và bỏ qua một phần bean post-processing thông thường. Nếu bean gốc được bọc bởi AOP như transaction, retry hoặc method security, mock không tự giữ các advice đó. Khi cần xác minh proxy/AOP, hãy test bean thật hoặc cân nhắc spy/wrap theo đúng semantics của Spring TestContext.

### 12.2. Custom bean production là một implementation thật

Khi kiểm tra auto-configuration back-off, hãy cung cấp một implementation thật trong user configuration:

~~~java
@Bean
CustomInventoryClient customInventoryClient() {
    return new CustomInventoryClient();
}
~~~

Implementation này phải implement contract mà condition đang kiểm tra. Khi context khởi động, default auto-configuration phải không tạo bean mặc định.

### 12.3. So sánh

| Công cụ | Mục đích | Có chứng minh default back off? |
| --- | --- | --- |
| `ApplicationContextRunner` + user configuration | Kiểm tra condition và bean graph độc lập. | Có, nếu assert cả custom bean và việc default vắng mặt. |
| `@TestConfiguration` | Bổ sung bean thật cho test context. | Có thể, khi test auto-configuration cùng cấu hình này. |
| `@MockitoBean` | Thay dependency bằng mock để kiểm tra logic consumer. | Không tự chứng minh production auto-configuration back off. |
| `@Primary` | Chọn bean ưu tiên khi có nhiều candidate. | Không; default có thể vẫn tồn tại. |
| Bean-definition overriding | Thay definition trùng identifier trong container/test. | Không; không kiểm tra đúng contract extension point. |

Các phiên bản cũ có thể dùng `@MockBean` của Spring Boot. Hãy chọn annotation bean override theo Spring Boot/Spring Framework version của dự án. Không chuyển test từ `@MockBean` sang `@MockitoBean` mà chưa kiểm tra dependency tương thích.

## 13. @Primary không phải thay thế default

Giả sử context có hai bean:

- `DefaultInventoryClient` do auto-configuration tạo.
- `CustomInventoryClient` do ứng dụng tạo.

Nếu custom bean được đánh dấu `@Primary`, injection theo type có thể chọn custom bean. Tuy nhiên, default vẫn tồn tại trong context.

Điều này có thể làm test đơn giản pass:

~~~java
@Autowired
InventoryClient inventoryClient;

@Test
void injectsPrimaryBean() {
    assertThat(inventoryClient)
            .isInstanceOf(CustomInventoryClient.class);
}
~~~

Nhưng test này không xác minh back-off. Nên bổ sung:

~~~java
assertThat(applicationContext)
        .hasSingleBean(InventoryClient.class);

assertThat(applicationContext)
        .doesNotHaveBean(DefaultInventoryClient.class);
~~~

Dùng `@Primary` khi thật sự cần nhiều bean cùng contract và muốn chọn một candidate mặc định cho injection. Dùng custom bean đúng extension point khi muốn auto-configuration bỏ qua default.

## 14. Kiểm thử Spring Cloud LoadBalancer

Spring Cloud LoadBalancer là ví dụ thực tế về default bean và custom bean thay thế. Mỗi service ID có child ApplicationContext riêng. Vì vậy, custom `ReactorLoadBalancer` hoặc `ServiceInstanceListSupplier` phải được đăng ký trong context của service cần tùy biến.

### 14.1. Các hành vi cần kiểm tra

Với một service ID như `inventory-service`, test nên xác minh:

1. Khi không có custom supplier, LoadBalancer dùng supplier mặc định dựa trên DiscoveryClient nếu provider và condition phù hợp.
2. Khi cấu hình riêng bằng `@LoadBalancerClient` cung cấp supplier tùy chỉnh, default supplier tương ứng back off.
3. Cấu hình cho `inventory-service` không vô tình áp dụng cho service ID khác.
4. Request qua WebClient/RestClient thực sự được chuyển đến instance do supplier trả về.
5. Danh sách instance rỗng và lỗi discovery được xử lý đúng.

### 14.2. Cấu hình theo service ID

Ví dụ khai báo client riêng:

~~~java
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerTestConfiguration.class
)
class InventoryLoadBalancerTestSetup {
}
~~~

Cấu hình custom supplier:

~~~java
public class InventoryLoadBalancerTestConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Đây là ví dụ supplier dựa trên DiscoveryClient và zone preference. Với test cần dữ liệu xác định, có thể thay discovery source bằng fixture hoặc test provider cung cấp danh sách instance tĩnh.

Không đặt cấu hình dành riêng cho LoadBalancer client vào component scan toàn cục nếu điều đó làm bean custom xuất hiện trong mọi service child context.

### 14.3. Test context con thay vì chỉ root context

Bean LoadBalancer theo service ID được tạo trong child context. Một test chỉ kiểm tra `applicationContext.getBeansOfType(...)` ở root context có thể không nhìn thấy bean tùy chỉnh đó.

Trong integration test, hãy khởi tạo client với service ID cần kiểm tra, yêu cầu LoadBalancer context tương ứng được tạo, rồi xác minh:
- Supplier/LoadBalancer được resolve từ đúng child context.
- Service ID khác vẫn dùng cấu hình của nó.
- Request thực tế đi tới một trong các instance do supplier cung cấp.

Tài liệu Spring Cloud LoadBalancer mô tả child context riêng cho từng service ID và cơ chế cấu hình qua `@LoadBalancerClient`. Test phải phản ánh ranh giới context này.

## 15. Ma trận kiểm thử đề xuất

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| T1 | Không có custom bean. | Default được tạo và implement đúng contract. |
| T2 | Có một custom bean đúng contract. | Custom bean được dùng, default không tồn tại. |
| T3 | Có bean khác type. | Default vẫn được tạo. |
| T4 | Có hai custom bean cùng contract. | Default back off; injection cần qualifier/primary nếu consumer yêu cầu một candidate. |
| T5 | Property bật. | Bean được tạo theo condition. |
| T6 | Property tắt. | Bean mặc định bị loại theo condition. |
| T7 | Property tắt nhưng có custom user bean. | Custom bean vẫn tồn tại nếu condition chỉ áp dụng lên default bean. |
| T8 | Optional class có trên classpath. | Nested auto-configuration được áp dụng. |
| T9 | Optional class bị FilteredClassLoader loại bỏ. | Cấu hình phụ thuộc class không được nạp. |
| T10 | Custom bean khai báo trong @TestConfiguration. | Test context dùng custom bean và default back off. |
| T11 | Dependency được thay bằng @MockitoBean. | Consumer được test với mock; không suy luận back-off từ test này. |
| T12 | Chỉ đánh dấu custom bean @Primary. | Injection chọn primary nhưng default vẫn tồn tại nếu condition không back off. |
| T13 | LoadBalancer custom supplier theo service ID. | Bean được resolve trong child context đúng service. |
| T14 | Service ID khác không có custom configuration. | Cấu hình default của service khác không bị ảnh hưởng. |
| T15 | Condition report có logging listener. | Lý do match/back-off có thể được đọc khi test thất bại. |

Không nhất thiết mỗi test class phải chứa tất cả trường hợp. Tách nhóm test theo auto-configuration, property và integration boundary để dễ đọc và chạy nhanh.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Default vẫn được tạo dù có custom bean. | Custom bean không implement contract condition kiểm tra. | Kiểm tra type của bean và target type trong `@ConditionalOnMissingBean`. |
| Custom bean không xuất hiện trong test. | Chưa nạp user configuration hoặc thiếu condition dependency. | Dùng `withUserConfiguration` và đọc report. |
| Test chỉ thấy một bean được inject nhưng default vẫn tồn tại. | Custom bean được đánh dấu `@Primary`. | Assert `hasSingleBean` và `doesNotHaveBean(DefaultType.class)`. |
| Condition không nhận ra custom bean. | Return type method quá tổng quát hoặc bean definition được đăng ký sai thời điểm. | Khai báo concrete return type và dùng user configuration với runner. |
| Test runner không tạo default. | Auto-configuration chưa được nạp hoặc class condition không khớp. | Kiểm tra `AutoConfigurations.of`, classpath và report. |
| Test optional dependency vẫn khởi tạo class SDK. | Class optional bị tham chiếu từ cấu hình ngoài vùng condition. | Cô lập trong nested configuration có `@ConditionalOnClass`. |
| Test custom bean fail do nhiều candidate. | Có nhiều bean cùng contract và injection không rõ ràng. | Dùng qualifier/primary khi thiết kế cần nhiều bean; nếu test back-off, assert default vắng mặt. |
| @MockitoBean không thay đúng bean. | Có nhiều candidate hoặc qualifier/name không khớp. | Chỉ rõ qualifier hoặc bean name; dùng enforceOverride nếu cần xác nhận bean tồn tại. |
| @SpringBootTest khởi động quá chậm. | Dùng context đầy đủ cho mọi tổ hợp condition. | Chuyển condition matrix sang `ApplicationContextRunner`. |
| Test LoadBalancer không thấy custom supplier. | Đang kiểm tra root context thay vì child context theo service ID. | Tạo client context và xác minh bean trong child context. |
| Test LoadBalancer pass nhưng request vẫn sai instance. | Chỉ kiểm tra bean tồn tại, chưa kiểm tra request thực tế. | Dùng test server/fixture và assert destination/response. |
| Test phụ thuộc thứ tự chạy. | Chia sẻ mutable singleton, mock hoặc external registry giữa test. | Tạo context cô lập, reset mock và dùng fixture riêng. |
| Test pass nhưng production dùng default. | Test configuration có custom bean nhưng cấu hình production không được import/scan. | Thêm integration test với cấu hình ứng dụng thật và xác minh bean wiring. |

## 17. Nguyên tắc xây dựng test bền vững

1. **Kiểm tra cả default và custom path.** Hai nhánh đều là hành vi công khai của auto-configuration.
2. **Assert theo contract và implementation.** Kiểm tra type, số lượng bean, default absence và kết quả hành vi.
3. **Dùng ApplicationContextRunner cho condition matrix.** Giữ mỗi test nhỏ, có cấu hình đầu vào rõ ràng.
4. **Nạp auto-configuration tường minh.** Không để test vô tình bỏ qua class đang cần kiểm tra.
5. **Dùng user configuration cho custom bean.** Đây là cách kiểm tra back-off theo cơ chế production.
6. **Tách mock khỏi custom implementation.** Mock giúp cô lập consumer; custom bean kiểm tra extension point.
7. **Không dựa vào @Primary để chứng minh back-off.** Primary chỉ quyết định candidate được inject.
8. **Đọc condition report khi thất bại.** Kiểm tra điều kiện theo type/name, property và classpath.
9. **Test context con đúng phạm vi.** Với LoadBalancer, xác định rõ service ID và child context.
10. **Giữ dependency test tối thiểu.** Chỉ thêm provider hoặc test server khi test thực sự cần hành vi đó.
11. **Tránh assertion theo chi tiết không ổn định.** Không phụ thuộc thứ tự bean hoặc tên tự sinh nếu không phải contract.
12. **Đối chiếu version.** Annotation bean override và API test có thể khác giữa Spring Boot/Spring Framework release train.

## 18. Checklist hoàn thành

- [ ] Giải thích được lý do phải test cả default và custom bean.
- [ ] Tạo được auto-configuration dùng `@ConditionalOnMissingBean`.
- [ ] Khởi tạo `ApplicationContextRunner` và nạp auto-configuration.
- [ ] Xác minh default được tạo khi không có custom bean.
- [ ] Xác minh custom bean đúng contract làm default back off.
- [ ] Assert số lượng bean theo contract và implementation cụ thể.
- [ ] Test bean không đúng contract không làm default back off.
- [ ] Test property enabled/disabled.
- [ ] Test optional dependency bằng `FilteredClassLoader`.
- [ ] Đọc ConditionEvaluationReport khi test thất bại.
- [ ] Dùng `@TestConfiguration` và `@Import` trong integration test khi cần.
- [ ] Phân biệt `@MockitoBean` với custom bean production.
- [ ] Hiểu `@Primary` không loại bean mặc định.
- [ ] Test LoadBalancer trong child context theo service ID.
- [ ] Có test matrix cho default, custom, property, classpath và context scope.
- [ ] Kiểm tra hành vi thực tế, không chỉ kiểm tra context khởi động.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `@ConditionalOnMissingBean`, thứ tự bean definition và phần Testing your Auto-configuration với `ApplicationContextRunner`.
- [Spring Framework – Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): `@TestBean`, `@MockitoBean`, `@MockitoSpyBean` và các chiến lược replace/wrap.
- [Spring Framework – @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring/reference/testing/annotations/integration-spring/annotation-mockitobean.html): cách chọn bean theo type/name, qualifier và lưu ý AOP proxy.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): child context theo service ID, custom LoadBalancer và ServiceInstanceListSupplier.
- [Spring – Client-Side Load-Balancing with Spring Cloud LoadBalancer](https://spring.io/guides/gs/spring-cloud-loadbalancer/): ví dụ cung cấp ServiceInstanceListSupplier tùy chỉnh để kiểm thử lựa chọn instance.

API test và bean override thay đổi theo Spring Boot/Spring Framework version. Hãy kiểm tra BOM của dự án, chạy test với đúng dependency set và xác minh cả default path lẫn custom path trước khi nâng cấp hoặc phát hành starter.
