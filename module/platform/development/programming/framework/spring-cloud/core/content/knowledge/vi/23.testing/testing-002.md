# Kiểm thử auto-configuration bằng ApplicationContextRunner

> **Chương:** Kiểm thử  
> **Module:** SPRING_CLOUD_CORE

Auto-configuration thường có nhiều nhánh điều kiện: thư viện có thể có hoặc không có trên classpath, bean phụ thuộc có thể đã được ứng dụng cung cấp, property có thể bật/tắt một capability và bean mặc định có thể phải lùi lại khi người dùng tùy biến. Chỉ kiểm thử ứng dụng khởi động thành công chưa đủ để chứng minh mọi nhánh đều hoạt động đúng.

Spring Boot cung cấp **ApplicationContextRunner** để kiểm thử auto-configuration trong một ApplicationContext nhỏ, có thể cấu hình chính xác classpath, property và bean đầu vào. Test chạy nhanh, cô lập và cho phép kiểm tra trực tiếp bean nào được tạo, bean nào bị bỏ qua, cũng như lý do condition không match. Đây là công cụ phù hợp để phát triển starter và các tích hợp trong **SPRING_CLOUD_CORE**.

Bài này xây dựng một ví dụ Catalog xuyên suốt: chỉ kích hoạt adapter khi SDK có trên classpath và có bean SDK, tạo implementation mặc định nếu ứng dụng chưa cung cấp CatalogClient, rồi tạo health indicator khi contract client tồn tại. Các test bao phủ nhánh thành công, nhánh fallback, thiếu class, thiếu bean và cấu hình property.

## 1. Vì sao cần ApplicationContextRunner?

Một auto-configuration có thể đúng ở môi trường phát triển nhưng sai trong một ứng dụng khác vì classpath, bean registry và property khác nhau.

Ví dụ, module catalog có thể có các quy tắc:

- Chỉ tích hợp SDK nếu class CatalogSdk tồn tại.
- Chỉ tạo adapter nếu context đã có bean CatalogSdk.
- Chỉ tạo default CatalogClient nếu ứng dụng chưa cung cấp implementation.
- Chỉ tạo CatalogHealthIndicator khi có bean CatalogClient.

Nếu chỉ chạy một test khởi động ứng dụng với đầy đủ dependency, ta mới kiểm tra được một nhánh. ApplicationContextRunner cho phép tạo nhiều context với các đầu vào khác nhau để kiểm tra từng nhánh condition.

### 1.1. ApplicationContextRunner làm gì?

Runner tạo một ApplicationContext cho từng lần gọi run. Test có thể cấu hình:

| API | Mục đích |
| --- | --- |
| withConfiguration(AutoConfigurations.of(...)) | Import các auto-configuration cần kiểm thử |
| withUserConfiguration(...) | Đăng ký cấu hình do ứng dụng hoặc test cung cấp |
| withBean(...) | Thêm bean fixture vào context |
| withPropertyValues(...) | Đặt property cho lần chạy test |
| withClassLoader(...) | Thay classloader, thường dùng để giả lập class tùy chọn không có |
| withInitializer(...) | Tùy chỉnh context trước khi refresh |
| run(context -> ...) | Chạy context và thực hiện assertion |

Mỗi lần gọi run tạo một context riêng và runner quản lý việc đóng context sau callback. Vì vậy, test không phải tự giữ context hoặc tự gọi close.

### 1.2. Những gì runner không tự làm

ApplicationContextRunner không tự khởi chạy toàn bộ ứng dụng như SpringApplication.run. Nó không tự quét mọi package của ứng dụng, không tự tải tất cả cấu hình production và không mở embedded web server.

Đó là chủ đích: test chỉ import cấu hình liên quan để nhánh điều kiện dễ quan sát. Nếu cần kiểm thử servlet context hoặc reactive web context, hãy dùng runner chuyên biệt ở phần sau.

## 2. Dependency kiểm thử

Thông thường, module auto-configuration cần dependency Spring Boot phù hợp và test source cần Spring Boot Test.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-autoconfigure</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-test-autoconfigure</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong ứng dụng dùng spring-boot-starter-test, nhiều test dependency đã được kéo vào sẵn. Với thư viện auto-configuration, có thể khai báo các artifact test riêng để tránh đưa dependency không cần thiết vào runtime.

Luôn dùng dependency management/BOM tương thích với Spring Boot release mà module hỗ trợ. Không tự ghép các phiên bản spring-boot-test và spring-boot-autoconfigure khác release.

## 3. Chuẩn bị auto-configuration cần kiểm thử

Ta dùng một ví dụ module Catalog có SDK tùy chọn. Các kiểu sau là contract hoặc fixture của ví dụ:

- CatalogSdk: kiểu từ thư viện SDK của nhà cung cấp.
- CatalogClient: interface mà ứng dụng sử dụng.
- SdkCatalogClient: adapter mặc định kết nối SDK.
- CatalogHealthIndicator: health indicator dựa trên client.
- CatalogClientProperties: cấu hình timeout của client.

### 3.1. Auto-configuration có điều kiện classpath và bean

Đặt các method tham chiếu SDK trong nested configuration để class tùy chọn không bị tải khi SDK không có:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.catalog.CatalogSdk")
    @ConditionalOnBean(type = "com.vendor.catalog.CatalogSdk")
    static class SdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(
                CatalogSdk sdk,
                CatalogClientProperties properties) {
            return new SdkCatalogClient(sdk, properties);
        }
    }
}
~~~

Có ba điều kiện khác nhau:

1. ConditionalOnClass xác nhận SDK class có trên runtime classpath.
2. ConditionalOnBean xác nhận context đã có bean SDK.
3. ConditionalOnMissingBean bảo đảm ứng dụng có thể thay implementation mặc định của CatalogClient.

Nested configuration bảo vệ phần method signature có tham chiếu trực tiếp đến SDK. Thuộc tính type dùng tên class dạng chuỗi để condition bean không cần tham chiếu class SDK ở outer configuration.

### 3.2. Auto-configuration phụ thuộc CatalogClient

Health indicator chỉ có ý nghĩa khi client contract tồn tại. Đặt nó trong auto-configuration được sắp xếp sau cấu hình tạo client:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CatalogSdkAutoConfiguration.class)
@ConditionalOnBean(CatalogClient.class)
public class CatalogHealthAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogHealthIndicator.class)
    CatalogHealthIndicator catalogHealthIndicator(CatalogClient client) {
        return new CatalogHealthIndicator(client);
    }
}
~~~

AutoConfiguration(after = ...) giúp health auto-configuration được xử lý sau cấu hình Catalog SDK. Điều kiện bean vẫn được đánh giá dựa trên bean definitions có sẵn tại thời điểm đó; khai báo thứ tự không tự tạo ra CatalogClient.

Nếu ứng dụng cung cấp CatalogClient riêng, health auto-configuration vẫn có thể hoạt động mà không cần SDK. Đây là một nhánh cần được kiểm thử riêng.

### 3.3. Đăng ký auto-configuration trong thư viện

Trong Spring Boot 3, thư viện thường liệt kê auto-configuration trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung ví dụ:

~~~text
com.example.catalog.CatalogSdkAutoConfiguration
com.example.catalog.CatalogHealthAutoConfiguration
~~~

Khi dùng ApplicationContextRunner, test có thể import trực tiếp class qua AutoConfigurations.of(...). Cách này giúp kiểm thử condition mà không phụ thuộc vào metadata đóng gói. Tuy nhiên, thư viện vẫn cần test riêng để xác nhận imports file được đóng gói đúng.

## 4. Tạo ApplicationContextRunner cơ bản

Một runner tối thiểu:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CatalogSdkAutoConfiguration.class,
                            CatalogHealthAutoConfiguration.class));
}
~~~

AutoConfigurations.of(...) đánh dấu các class là auto-configuration để runner xử lý theo cơ chế sắp xếp của Spring Boot. Nếu chỉ dùng withUserConfiguration(...), cấu hình sẽ được đưa vào như cấu hình người dùng; điều đó có thể làm thứ tự condition khác với tình huống auto-configuration thực tế.

Một test chạy context:

~~~java
@Test
void contextStarts() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
    });
}
~~~

run nhận callback với một AssertableApplicationContext. Có thể kiểm tra trạng thái startup, bean theo kiểu hoặc tên, giá trị property đã bind và exception nếu context không khởi động thành công.

Không nên dừng ở assertion hasNotFailed(). Một context khởi động thành công vẫn có thể thiếu bean mà module phải cung cấp.

## 5. Kiểm thử default bean và user override

### 5.1. Nhánh có SDK class và SDK bean

Khi class SDK có mặt và context có bean CatalogSdk, auto-configuration có thể tạo SdkCatalogClient. Health auto-configuration cũng có thể tạo indicator.

~~~java
@Test
void createsDefaultClientWhenSdkAndSdkBeanExist() {
    contextRunner
            .withBean(CatalogSdk.class, FakeCatalogSdk::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context.getBean(CatalogClient.class))
                        .isInstanceOf(SdkCatalogClient.class);
                assertThat(context)
                        .hasSingleBean(CatalogHealthIndicator.class);
            });
}
~~~

withBean đăng ký fixture trước khi context được refresh. FakeCatalogSdk là test fixture phù hợp với API của SDK; trong dự án thật có thể dùng fake implementation, mock hoặc factory tạo SDK test.

### 5.2. Nhánh ứng dụng cung cấp implementation riêng

Khi người dùng đã đăng ký CatalogClient, default bean phải lùi lại:

~~~java
@Configuration(proxyBeanMethods = false)
static class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new CachedCatalogClient();
    }
}

@Test
void backsOffWhenApplicationProvidesClient() {
    contextRunner
            .withBean(CatalogSdk.class, FakeCatalogSdk::new)
            .withUserConfiguration(CustomCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context.getBean(CatalogClient.class))
                        .isInstanceOf(CachedCatalogClient.class);
                assertThat(context)
                        .hasSingleBean(CatalogHealthIndicator.class);
            });
}
~~~

Test này xác nhận hợp đồng mở rộng của starter: bean mặc định chỉ được tạo khi chưa có bean phù hợp. Ứng dụng có thể thay implementation mà không phải exclude toàn bộ auto-configuration.

Nếu cần kiểm tra đúng instance được dùng, có thể tạo object tùy chỉnh trước rồi đăng ký bằng supplier và assertion isSameAs. Điều đó hữu ích khi bean mang state hoặc mock có expectation riêng.

## 6. Kiểm thử điều kiện classpath bằng FilteredClassLoader

Một dependency tùy chọn có thể có trên classpath của test nhưng vắng mặt trong ứng dụng người dùng. FilteredClassLoader giả lập trường hợp class không thể được nhìn thấy từ ApplicationContext.

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void doesNotCreateSdkIntegrationWhenSdkClassIsMissing() {
    contextRunner
            .withClassLoader(new FilteredClassLoader(CatalogSdk.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(CatalogClient.class);
                assertThat(context)
                        .doesNotHaveBean(CatalogHealthIndicator.class);
            });
}
~~~

Test này đặc biệt có giá trị khi auto-configuration có dependency tùy chọn. Nếu code tham chiếu SDK class ở outer configuration, method signature hoặc annotation theo cách không được bảo vệ, test có thể phát hiện lỗi tải class.

FilteredClassLoader chỉ ảnh hưởng classloader của context đang kiểm thử. Nó không gỡ JAR khỏi build hoặc thay đổi classpath của tiến trình test.

### 6.1. Phân biệt thiếu class và thiếu bean

Hai tình huống thường bị nhầm:

- **Thiếu class:** SDK không có trên runtime classpath; ConditionalOnClass không match.
- **Thiếu bean:** SDK class có mặt nhưng không có bean CatalogSdk; ConditionalOnBean không match.

Có thể kiểm tra nhánh thiếu bean bằng một test riêng:

~~~java
@Test
void doesNotCreateClientWhenSdkBeanIsMissing() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).doesNotHaveBean(CatalogClient.class);
        assertThat(context).doesNotHaveBean(CatalogHealthIndicator.class);
    });
}
~~~

Nếu bỏ test này, một implementation có thể vô tình giả định classpath presence đồng nghĩa bean đã tồn tại. Test phân biệt hai điều kiện làm hợp đồng của auto-configuration rõ ràng hơn.

## 7. Kiểm thử bean phụ thuộc bằng ConditionalOnBean

CatalogHealthAutoConfiguration chỉ tạo health indicator khi có bean CatalogClient. Có thể kiểm tra trực tiếp khi không import auto-configuration tạo client:

~~~java
@Test
void doesNotCreateHealthIndicatorWithoutClient() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    CatalogHealthAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(CatalogHealthIndicator.class);
            });
}
~~~

Đồng thời, kiểm tra nhánh có client do người dùng cung cấp mà không có SDK:

~~~java
@Test
void createsHealthIndicatorForUserProvidedClientWithoutSdk() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    CatalogHealthAutoConfiguration.class))
            .withUserConfiguration(CustomCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context)
                        .hasSingleBean(CatalogHealthIndicator.class);
            });
}
~~~

Test thứ hai xác nhận health auto-configuration phụ thuộc contract CatalogClient, không phụ thuộc cách client được tạo. Đây là lợi ích của việc phụ thuộc interface thay vì implementation SDK cụ thể.

## 8. Kiểm thử property và ConfigurationProperties

Auto-configuration thường có nhánh điều kiện theo property hoặc bind property vào object cấu hình. withPropertyValues giúp đặt giá trị riêng cho từng test.

Giả sử module có properties:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private Duration timeout = Duration.ofSeconds(2);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Vì CatalogSdkAutoConfiguration dùng EnableConfigurationProperties(CatalogClientProperties.class), runner có thể xác nhận binding:

~~~java
@Test
void bindsCatalogClientProperties() {
    contextRunner
            .withPropertyValues(
                    "catalog.client.timeout=750ms")
            .run(context -> {
                assertThat(context).hasNotFailed();

                CatalogClientProperties properties =
                        context.getBean(CatalogClientProperties.class);

                assertThat(properties.getTimeout())
                        .isEqualTo(Duration.ofMillis(750));
            });
}
~~~

Nếu auto-configuration có ConditionalOnProperty, hãy viết ít nhất hai test: property bật và property tắt. Kiểm tra bean có hoặc không có trong context thay vì chỉ kiểm tra giá trị Environment.

Ví dụ condition:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CatalogMetricsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "catalog.client",
            name = "metrics-enabled",
            havingValue = "true")
    CatalogMetrics catalogMetrics() {
        return new CatalogMetrics();
    }
}
~~~

Runner riêng cho auto-configuration này:

~~~java
private final ApplicationContextRunner metricsRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogMetricsAutoConfiguration.class));
~~~

Phần test bật:

~~~java
@Test
void createsMetricsWhenEnabled() {
    metricsRunner
            .withPropertyValues("catalog.client.metrics-enabled=true")
            .run(context ->
                    assertThat(context).hasSingleBean(CatalogMetrics.class));
}
~~~

Test khi property được đặt thành false:

~~~java
@Test
void doesNotCreateMetricsWhenDisabled() {
    metricsRunner
            .withPropertyValues("catalog.client.metrics-enabled=false")
            .run(context ->
                    assertThat(context).doesNotHaveBean(CatalogMetrics.class));
}
~~~

Test khi property không được khai báo:

~~~java
@Test
void doesNotCreateMetricsWhenPropertyIsMissing() {
    metricsRunner.run(context ->
            assertThat(context).doesNotHaveBean(CatalogMetrics.class));
}
~~~

Test riêng cho trường hợp property không được khai báo ở trên xác nhận default behavior. Giữ ba trường hợp bật, tắt và không khai báo thành các test độc lập để biết chính xác nhánh nào bị lỗi.

## 9. Kiểm thử thứ tự auto-configuration

Khi auto-configuration B dùng ConditionalOnBean để phụ thuộc bean do auto-configuration A tạo, thứ tự import rất quan trọng.

Trong ví dụ Catalog:

- CatalogSdkAutoConfiguration tạo default CatalogClient nếu điều kiện match.
- CatalogHealthAutoConfiguration được khai báo after Catalog SDK configuration.
- Health indicator chỉ được tạo nếu contract CatalogClient có trong context.

ApplicationContextRunner kết hợp AutoConfigurations.of(...) giúp kiểm tra luồng auto-configuration theo cơ chế sắp xếp của Spring Boot. Không nên thay test này bằng một cấu hình test thông thường khai báo sẵn cả hai bean, vì như vậy không còn kiểm tra ordering và condition thực tế.

Nếu một condition không match ngoài dự kiến:

1. Xác nhận auto-configuration được import.
2. Kiểm tra ordering metadata.
3. Xác nhận bean phụ thuộc được đăng ký trước thời điểm condition đánh giá.
4. Kiểm tra type/bean name mà condition đang tìm.
5. Dùng Condition Evaluation Report để xem positive/negative match.

AutoConfigureAfter chỉ điều chỉnh thứ tự tương đối. Nó không bảo đảm dependency bean tồn tại và không thay thế test cho nhánh thiếu bean.

## 10. Web và reactive auto-configuration runner

ApplicationContextRunner phù hợp với auto-configuration không cần web environment. Nếu cấu hình phụ thuộc loại ApplicationContext hoặc web-specific bean, hãy dùng runner tương ứng:

| Runner | Môi trường |
| --- | --- |
| ApplicationContextRunner | ApplicationContext thông thường |
| WebApplicationContextRunner | Servlet web application context |
| ReactiveWebApplicationContextRunner | Reactive web application context |

Ví dụ với servlet:

~~~java
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;

private final WebApplicationContextRunner webRunner =
        new WebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogWebAutoConfiguration.class));
~~~

Ví dụ với reactive:

~~~java
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;

private final ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        CatalogReactiveAutoConfiguration.class));
~~~

Các runner này vẫn hỗ trợ cấu hình property, user configuration, bean và classloader tương tự. Chúng giúp kiểm tra condition phụ thuộc web application type mà không cần mở cổng HTTP thật.

Nếu mục tiêu là kiểm thử endpoint HTTP, filter chain, serialization hoặc request routing, hãy kết hợp với WebMvcTest, WebFluxTest, MockMvc, WebTestClient hoặc integration test phù hợp. Runner kiểm tra việc cấu hình bean được tạo; nó không thay thế kiểm thử giao thức HTTP.

## 11. Đọc lỗi khi context không khởi động

Trong callback run, context có thể không refresh thành công vì bean thiếu dependency, cấu hình sai hoặc lỗi khởi tạo. Runner vẫn cho phép kiểm tra startup failure.

Ví dụ:

~~~java
@Test
void reportsStartupFailureForInvalidConfiguration() {
    contextRunner
            .withPropertyValues("catalog.client.timeout=not-a-duration")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

Không chỉ assertion hasFailed() rồi kết thúc. Khi điều tra lỗi, hãy kiểm tra exception cause để xác định lỗi binding, thiếu dependency hay lỗi tạo bean.

Với các test kỳ vọng context khởi động thành công, dùng hasNotFailed() ở đầu callback để làm nguyên nhân thất bại hiển thị rõ. Sau đó kiểm tra bean và property cụ thể.

### 11.1. Condition Evaluation Report

Khi bean không xuất hiện, có thể xem Condition Evaluation Report của context để biết condition nào match hoặc không match. Đây là thông tin hữu ích khi nhiều auto-configuration cùng điều kiện hóa bean.

Không nên phụ thuộc vào các class nội bộ của Spring Boot nếu test chỉ cần xác nhận hành vi công khai. Ưu tiên assertion bean có/không có; chỉ đọc report khi cần chẩn đoán nguyên nhân.

## 12. Ma trận kiểm thử cho ví dụ Catalog

Một bộ test tốt phải kiểm tra các nhánh điều kiện độc lập:

| SDK class | SDK bean | Custom CatalogClient | Kết quả mong đợi |
| --- | --- | --- | --- |
| Có | Có | Không | Tạo default client và health indicator |
| Có | Có | Có | Dùng custom client; default client lùi lại |
| Có | Không | Không | Không tạo client và health indicator |
| Không | Không | Không | Bỏ qua SDK integration |
| Không | Không | Có | Giữ custom client; health indicator vẫn có thể được tạo |
| Có | Có | Không, property metrics tắt | Client tồn tại; metrics bean không được tạo |

Bên cạnh ma trận trên, hãy kiểm tra properties binding, thứ tự auto-configuration, lỗi cấu hình và điều kiện theo profile nếu module có hỗ trợ.

Một bộ test không cần assert mọi bean trong toàn ứng dụng. Hãy tập trung vào contract của auto-configuration: bean nào được cung cấp, điều kiện nào làm nó xuất hiện và ứng dụng có thể thay thế nó ra sao.

## 13. Lỗi thường gặp và cách tránh

1. **Chỉ test context khởi động thành công:** thêm assertion bean có/không có theo từng nhánh condition.
2. **Không test khi optional class vắng mặt:** dùng FilteredClassLoader để phát hiện lỗi tải class.
3. **Nhầm class có trên classpath với bean đã tồn tại:** viết test riêng cho class có nhưng bean SDK không có.
4. **Dùng withUserConfiguration thay cho AutoConfigurations:** import auto-config qua AutoConfigurations.of để kiểm tra đúng thứ tự.
5. **Không test user override:** xác nhận default bean lùi lại khi ứng dụng cung cấp implementation riêng.
6. **Không test property thiếu và property tắt:** kiểm tra cả default behavior và các giá trị tường minh.
7. **Test nhiều condition trong một case duy nhất:** tách case để biết điều kiện nào gây lỗi.
8. **Dùng ApplicationContextRunner cho web-specific condition:** chọn WebApplicationContextRunner hoặc ReactiveWebApplicationContextRunner.
9. **Chỉ assert context failed:** đọc startup failure và nguyên nhân gốc.
10. **Test dựa vào implementation nội bộ:** ưu tiên kiểm tra bean và hành vi công khai.
11. **Quên test auto-configuration imports metadata:** runner import class trực tiếp không chứng minh file imports được đóng gói đúng.
12. **Không kiểm tra ordering:** dùng auto-configuration thật và khai báo before/after phù hợp.

## 14. Quy trình viết test cho auto-configuration

Khi bổ sung một auto-configuration vào module Spring Cloud, có thể thực hiện:

1. Liệt kê từng condition: classpath, bean, missing bean, property và web application type.
2. Tạo runner với AutoConfigurations.of(...) cho đúng các auto-configuration cần kiểm tra.
3. Viết test nhánh mặc định khi đủ dependency.
4. Viết test nhánh thiếu class bằng FilteredClassLoader.
5. Viết test nhánh class có nhưng bean không có.
6. Viết test user bean override để xác nhận missing-bean condition.
7. Viết test property bật, tắt và không khai báo.
8. Viết test bean phụ thuộc để xác nhận ConditionalOnBean và ordering.
9. Dùng runner web tương ứng nếu auto-configuration phụ thuộc servlet/reactive context.
10. Kiểm tra startup failure và Condition Evaluation Report khi cần chẩn đoán.
11. Test riêng metadata đăng ký auto-configuration trong artifact.
12. Bổ sung integration test khi cần xác nhận kết nối thật, protocol hoặc behavior ngoài ApplicationContext.

**Điểm ghi nhớ:** ApplicationContextRunner giúp kiểm thử auto-configuration trong một context nhỏ với classpath, property và bean đầu vào có kiểm soát. Kết hợp AutoConfigurations.of, withBean, withUserConfiguration, withPropertyValues và FilteredClassLoader để kiểm tra các nhánh condition, default bean và user override. Dùng runner web khi cấu hình phụ thuộc web context, còn các luồng HTTP hoặc kết nối registry thật cần integration test riêng. Bộ test tốt chứng minh auto-configuration hoạt động đúng khi dependency có mặt, khi thiếu và khi ứng dụng muốn tùy biến trong **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing)
- [Spring Boot API — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot API — FilteredClassLoader](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot API — WebApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html)
