# Đọc điều kiện ở cấp class trước khi phân tích từng phương thức @Bean trong Spring Boot Auto Configuration

## 1. Vì sao phải đọc từ class xuống từng bean method?

Một auto-configuration có thể khai báo nhiều bean, nhưng không phải bean nào cũng phù hợp với mọi ứng dụng. Ví dụ thư viện cung cấp client lõi, metrics tùy chọn và một adapter chỉ hoạt động khi có thư viện JDBC:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "acme.client", name = "enabled",
                       havingValue = "true")
class AcmeClientAutoConfiguration {

    @Bean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }

    @Bean
    @ConditionalOnProperty(prefix = "acme.client.metrics",
                           name = "enabled", havingValue = "true")
    AcmeMetrics acmeMetrics() {
        return new AcmeMetrics();
    }
}
~~~

Khi đọc mã, hãy bắt đầu từ **class-level conditions** (điều kiện cấp class), sau đó mới đi vào từng phương thức `@Bean`:

1. Class này có phải auto-configuration ứng viên và có được Spring Boot nạp không?
2. Những điều kiện gắn ở cấp class có cho phép cấu hình tham gia không?
3. Class có import cấu hình con, registrar hoặc component scan nào không?
4. Mỗi phương thức `@Bean` có điều kiện riêng nào?
5. Nếu một method được đăng ký, các tham số của nó cần bean nào và return type cụ thể là gì?

Cách đọc này giúp phân biệt **cổng điều kiện chung** với **điều kiện riêng của từng bean**. Một điều kiện cấp class thường tác động tới phạm vi cấu hình rộng hơn; điều kiện ở method chỉ kiểm soát bean do method đó khai báo.

Tuy nhiên, đừng hiểu “đọc class trước” thành “mọi condition cấp class đều được đánh giá trước mọi condition cấp method”. Spring có nhiều giai đoạn đánh giá khác nhau. Đặc biệt, điều kiện kiểm tra classpath và điều kiện kiểm tra bean registry không nhất thiết chạy cùng một giai đoạn.

## 2. Auto-configuration class là gì?

`@AutoConfiguration` là annotation chuyên biệt của Spring Boot, được meta-annotate bằng `@Configuration`. Vì vậy auto-configuration vẫn là một nguồn khai báo bean theo cơ chế Java Configuration của Spring, đồng thời tuân theo quy tắc phát hiện và sắp thứ tự riêng của Boot.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
~~~

Đoạn code trên minh họa class có thể cung cấp bean. Để được Boot tự phát hiện khi đóng gói thành JAR, class phải có tên trong file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung file, mỗi class một dòng:

~~~text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
~~~

Nếu class không được import, chỉ có `@AutoConfiguration` trên source chưa đủ để bảo đảm nó được áp dụng. Ngược lại, class đã là ứng viên vẫn có thể bị điều kiện loại khỏi quá trình cấu hình.

**Đọc đầu class trước:** ghi lại `@AutoConfiguration`, mọi annotation `@Conditional...`, `@Import`, `@EnableConfigurationProperties` và thuộc tính `before/after`. Những metadata này định hình phạm vi, phụ thuộc và thứ tự xử lý trước khi ta đánh giá từng bean method.

## 3. Hai phạm vi điều kiện: class-level và method-level

Spring Framework cho phép `@Conditional` xuất hiện ở cấp type hoặc cấp method. Các annotation Boot như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và `@ConditionalOnMissingBean` đều được xây dựng trên cơ chế này.

| Vị trí annotation | Phạm vi kiểm soát | Câu hỏi khi đọc |
| --- | --- | --- |
| Trên `@Configuration` / `@AutoConfiguration` | Phạm vi cấu hình class, gồm các khai báo gắn với cấu hình đó | Cấu hình tổng thể có đủ điều kiện tham gia không? |
| Trên một phương thức `@Bean` | Chỉ bean definition do phương thức đó cung cấp | Bean cụ thể này có đủ điều kiện được đăng ký không? |
| Trên nested `@Configuration` | Nhóm bean được gom vào cấu hình con | Nhóm tính năng tùy chọn này có thể được bật độc lập không? |

Ví dụ một class có điều kiện chung và hai method có điều kiện riêng:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "acme", name = "enabled",
                       havingValue = "true")
class AcmeAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Bean
    @ConditionalOnProperty(prefix = "acme", name = "metrics-enabled",
                           havingValue = "true")
    MetricsService metricsService() {
        return new MetricsService();
    }
}
~~~

Để `CoreService` hoặc `MetricsService` được cung cấp qua cấu hình này, điều kiện cấp class phải cho phép cấu hình tham gia. Ngoài ra:
- `CoreService` không có điều kiện riêng nên chỉ phụ thuộc điều kiện cấp class và các điều kiện/metadata khác của nó.
- `MetricsService` còn phải thỏa điều kiện `acme.metrics-enabled=true`.
- Nếu class-level condition không khớp, method-level condition không thể tự “mở lại” cấu hình đã bị loại.

Theo hợp đồng của Spring `@Conditional`, condition ở cấp `@Configuration` áp dụng cho các phương thức `@Bean`, `@Import` và `@ComponentScan` liên quan tới class đó. Các condition cùng áp dụng lên một phần tử phải thỏa theo logic **AND**: chỉ cần một condition không khớp thì phần tử không đủ điều kiện đăng ký. Nếu muốn hai nhánh độc lập, thường nên tách thành các nested configuration hoặc auto-configuration class riêng.

## 4. Đừng nhầm phạm vi với giai đoạn đánh giá condition

Spring Framework định nghĩa hai giai đoạn trong `ConfigurationCondition`:

| Giai đoạn | Ý nghĩa | Điều gì đã có? |
| --- | --- | --- |
| `PARSE_CONFIGURATION` | Đánh giá khi parser đang xử lý class cấu hình | Spring đang quyết định có tiếp tục phân tích class, imports và cấu trúc cấu hình không |
| `REGISTER_BEAN` | Đánh giá khi đăng ký một bean definition thông thường | Các configuration class đã được phân tích; bean definitions được xử lý trước đó có thể được kiểm tra |

Một số nhóm condition thường gặp:

- **Classpath conditions** như `@ConditionalOnClass` / `@ConditionalOnMissingClass`: dùng để quyết định cấu hình có phù hợp với thư viện có trên classpath hay không. Ở cấp class, Boot có thể đọc metadata annotation bằng ASM để kiểm tra mà không phải nạp class tùy chọn vào JVM.
- **Bean conditions** như `@ConditionalOnBean` / `@ConditionalOnMissingBean`: cần nhìn vào bean definitions đã được xử lý đến thời điểm đánh giá. Chúng nhạy với thứ tự đăng ký nên phải đọc cùng metadata auto-configuration và thứ tự before/after.
- **Property conditions** như `@ConditionalOnProperty`: kiểm tra `Environment`; có thể dùng ở class để bật/tắt toàn bộ cấu hình hoặc ở method để bật/tắt một bean.
- **Web/resource conditions**: kiểm tra loại application context hoặc resource có tồn tại; thường dùng để giới hạn nhóm tính năng.

Không được suy luận rằng mọi annotation bắt đầu bằng `@ConditionalOn` đều có cùng phase. Khi viết custom condition, nếu phải quyết định lúc parse class hay lúc đăng ký bean, hãy triển khai `ConfigurationCondition` và chọn phase có chủ đích.

### Lưu ý riêng về bean conditions ở class-level

`@ConditionalOnBean` và `@ConditionalOnMissingBean` có thể xuất hiện ở class hoặc method. Khi đặt ở cấp class, điều kiện áp dụng ở phạm vi cấu hình class và ảnh hưởng tới việc đăng ký cấu hình đó; khi đặt trên một method, nó kiểm soát riêng bean method ấy. Boot lưu ý các bean conditions không đơn giản là một cổng parse class sớm: configuration class vẫn được xử lý theo lifecycle cấu hình, còn bean condition được đánh giá ở giai đoạn đăng ký bean.

Vì các condition này phụ thuộc những bean definitions đã được xử lý, Boot khuyến nghị đặt chúng trong **auto-configuration**, vốn được áp dụng sau các bean definitions do người dùng khai báo. Khi chỉ một bean cần prerequisite, đặt điều kiện trên chính method `@Bean` thường làm ý đồ rõ ràng hơn và tránh ràng buộc các bean anh em không liên quan.

## 5. Đọc class-level conditions trước: classpath, property, profile và web context

### 5.1. @ConditionalOnClass và @ConditionalOnMissingClass

Hai annotation này kiểm tra sự hiện diện/vắng mặt của class trên classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
class VendorAutoConfiguration {

    @Bean
    VendorAdapter vendorAdapter() {
        return new VendorAdapter();
    }
}
~~~

Nếu class `com.vendor.sdk.VendorClient` không có trên classpath, cấu hình không phù hợp. Thuộc tính `name` dùng tên class dạng chuỗi, phù hợp khi muốn tránh tham chiếu trực tiếp type tùy chọn trong annotation.

**Bẫy khi đặt condition ở method:** nếu method `@Bean` có return type hoặc signature tham chiếu trực tiếp class tùy chọn, JVM có thể phải nạp/resolve type đó trước khi method-level condition có cơ hội loại bean. Để bảo vệ thư viện tùy chọn, hãy cô lập các method có signature phụ thuộc class đó trong một nested configuration có class condition:

~~~java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
    static class VendorClientConfiguration {

        @Bean
        VendorAdapter vendorAdapter(com.vendor.sdk.VendorClient client) {
            return new VendorAdapter(client);
        }
    }
}
~~~

Đây là mẫu tổ chức code: dependency SDK vẫn cần ở compile classpath khi biên dịch module chứa method signature, nhưng có thể không hiện diện ở runtime. Nested configuration giúp phần tham chiếu SDK được tách khỏi class auto-configuration luôn được nạp. Nếu condition là một meta-annotation tự tạo, Boot yêu cầu dùng `name` khi tham chiếu class tùy chọn trong composed annotation.

### 5.2. @ConditionalOnProperty và @Profile

Dùng property condition khi cấu hình đến từ `application.yml` hoặc nguồn thuộc `Environment`:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "acme.client", name = "enabled",
                       havingValue = "true")
class AcmeClientAutoConfiguration {
    // Các bean dùng chung khi client được bật
}
~~~

Nếu chỉ metrics là tùy chọn, chuyển condition xuống method metrics thay vì tắt cả client. `@Profile("production")` cũng là một condition cấp class hoặc method để giới hạn cấu hình theo profile đang hoạt động.

### 5.3. @ConditionalOnWebApplication

Một thư viện có cả tích hợp servlet và phần lõi có thể tách:

~~~java
@AutoConfiguration
class AcmeAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnWebApplication(type =
            ConditionalOnWebApplication.Type.SERVLET)
    static class ServletConfiguration {

        @Bean
        ServletAdapter servletAdapter() {
            return new ServletAdapter();
        }
    }
}
~~~

Kết quả là bean lõi không nhất thiết phụ thuộc web context; chỉ nhóm adapter servlet yêu cầu ứng dụng servlet. Các type `CoreService` và `ServletAdapter` trong đoạn minh họa phải được định nghĩa trong project.

## 6. Đọc từng @Bean method: điều kiện riêng, return type và dependency

Sau khi hiểu class-level scope, đọc từng method theo bốn điểm:

1. Tên bean (mặc định thường là tên method, trừ khi `@Bean(name=...)` chỉ định).
2. Return type (type metadata Spring nhìn thấy khi phân tích bean).
3. Annotation condition ngay trên method.
4. Tham số method (dependency cần có để tạo bean).

Ví dụ:

~~~java
@Bean
@ConditionalOnBean(DataSource.class)
@ConditionalOnMissingBean(ReportRepository.class)
JdbcReportRepository reportRepository(DataSource dataSource) {
    return new JdbcReportRepository(dataSource);
}
~~~

Diễn giải:
- Chỉ đăng ký bean nếu một bean `DataSource` phù hợp đã được đăng ký và được condition nhìn thấy.
- Đồng thời chưa có bean `ReportRepository` phù hợp.
- Phương thức nhận `DataSource` để khởi tạo repository.
- Hai condition trên method cùng phải khớp.

`@ConditionalOnBean` kiểm tra **bean trong BeanFactory**, không phải chỉ class trên classpath. Có class `DataSource` trong JDK hoặc dependency không có nghĩa đã có bean `DataSource`. Nếu method cần bean đó, condition và tham số injection nên thể hiện cùng một prerequisite.

### Return type là một phần của condition metadata

Khi `@ConditionalOnMissingBean` không chỉ rõ type/name, target type của condition trên method mặc định dựa vào **return type** của method:

~~~java
@Bean
@ConditionalOnMissingBean
DefaultReportFormatter reportFormatter() {
    return new DefaultReportFormatter();
}
~~~

Return type cụ thể `DefaultReportFormatter` giúp Spring biết nhiều thông tin type hơn trong lúc đánh giá condition. Tránh khai báo quá chung:

~~~java
@Bean
@ConditionalOnMissingBean
Object reportFormatter() {
    return new DefaultReportFormatter();
}
~~~

Ở dạng thứ hai, metadata chỉ bộc lộ `Object`, làm condition không có đủ thông tin type như mong đợi. Boot khuyến nghị cung cấp return type giàu thông tin nhất có thể, đặc biệt với bean conditions.

## 7. Ví dụ tổng hợp: class condition và method conditions hoạt động cùng nhau

Ví dụ sau minh họa ba lớp quyết định:

- Class-level: toàn bộ auto-configuration chỉ áp dụng khi `acme.library.enabled=true`.
- Method-level property: metrics chỉ được đăng ký khi `acme.library.metrics.enabled=true`.
- Method-level bean conditions: publisher chỉ được tạo khi đã có `AuditStore`; formatter mặc định chỉ được tạo khi người dùng chưa cung cấp `Formatter`.

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.library",
        name = "enabled",
        havingValue = "true"
)
class LibraryAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.library.metrics",
            name = "enabled",
            havingValue = "true"
    )
    MetricsService metricsService() {
        return new MetricsService();
    }

    @Bean
    @ConditionalOnBean(AuditStore.class)
    AuditPublisher auditPublisher(AuditStore store) {
        return new AuditPublisher(store);
    }

    @Bean
    @ConditionalOnMissingBean(Formatter.class)
    DefaultFormatter defaultFormatter() {
        return new DefaultFormatter();
    }
}
~~~

Các class `CoreService`, `MetricsService`, `AuditStore`, `AuditPublisher`, `Formatter` và `DefaultFormatter` là type của ứng dụng/thư viện; chúng được định nghĩa đầy đủ trong file test ở mục 9. Ví dụ này tập trung vào cấu trúc condition, không phải một source file độc lập để biên dịch riêng.

Bảng kết quả:

| Cấu hình | CoreService | MetricsService | AuditPublisher | DefaultFormatter |
| --- | --- | --- | --- | --- |
| `acme.library.enabled=false` | Không | Không | Không | Không |
| `enabled=true`, metrics thiếu/tắt, không có AuditStore | Có | Không | Không | Có |
| `enabled=true`, metrics=true, có AuditStore, chưa có Formatter | Có | Có | Có | Có |
| `enabled=true`, user cung cấp AuditStore và Formatter | Có | Tùy property metrics | Có | Không (back off) |

Đây là cách phân tích từ ngoài vào trong: class-level condition trước, sau đó mới đánh giá các method riêng. Không kết luận rằng tất cả method cùng trạng thái chỉ vì một property ở cấp method đang tắt.

## 8. Thứ tự đăng ký bean definitions và vì sao bean conditions nhạy với thứ tự

`@ConditionalOnBean` và `@ConditionalOnMissingBean` dựa trên bean definitions đã được xử lý đến thời điểm condition chạy. Do đó:
- Bean do người dùng khai báo thường đã được đăng ký trước auto-configuration, giúp người dùng override default.
- Nếu một auto-configuration phụ thuộc bean do auto-configuration khác tạo, cần sắp thứ tự bằng `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureAfter` khi phù hợp.
- Không nên đặt bean conditions vào một configuration thông thường được component-scan nếu nó có thể được xử lý trước bean mà condition đang chờ.
- Class có trên classpath không thay thế cho bean definition đã đăng ký.
- Bean definition đã đăng ký không đồng nghĩa instance đã khởi tạo xong.

Ví dụ:

~~~java
@AutoConfiguration
class StorageAutoConfiguration {

    @Bean
    StorageClient storageClient() {
        return new StorageClient();
    }
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class SearchAutoConfiguration {

    @Bean
    @ConditionalOnBean(StorageClient.class)
    SearchIndexer searchIndexer(StorageClient storage) {
        return new SearchIndexer(storage);
    }
}
~~~

`after` đảm bảo metadata ordering: Search auto-configuration được xử lý sau Storage auto-configuration. Nó không tự tạo `StorageClient` nếu cấu hình storage không tham gia hoặc bean bị condition khác loại bỏ. Nó cũng không điều khiển thứ tự khởi tạo instance; việc tạo instance phụ thuộc injection và lifecycle của container.

## 9. Kiểm thử runnable với ApplicationContextRunner

Kiểm thử auto-configuration cần bao phủ các tổ hợp class-level và method-level condition. `ApplicationContextRunner` cho phép tạo context độc lập, gắn property và user configuration để xác nhận bean nào được đăng ký.

Tạo file `src/test/java/com/example/demo/ConditionScopeTest.java` trong project Java 17+ dùng Spring Boot 3.3 và dependency `spring-boot-starter-test`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionScopeTest {

    static final class CoreService {
    }

    static final class MetricsService {
    }

    interface AuditStore {
        String name();
    }

    static final class MemoryAuditStore implements AuditStore {
        @Override
        public String name() {
            return "memory";
        }
    }

    static final class AuditPublisher {
        private final AuditStore store;

        AuditPublisher(AuditStore store) {
            this.store = store;
        }

        String destination() {
            return store.name();
        }
    }

    interface Formatter {
        String format();
    }

    static final class DefaultFormatter implements Formatter {
        @Override
        public String format() {
            return "default";
        }
    }

    static final class CustomFormatter implements Formatter {
        @Override
        public String format() {
            return "custom";
        }
    }

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "acme.library",
            name = "enabled",
            havingValue = "true"
    )
    static class LibraryAutoConfiguration {

        @Bean
        CoreService coreService() {
            return new CoreService();
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.library.metrics",
                name = "enabled",
                havingValue = "true"
        )
        MetricsService metricsService() {
            return new MetricsService();
        }

        @Bean
        @ConditionalOnBean(AuditStore.class)
        AuditPublisher auditPublisher(AuditStore store) {
            return new AuditPublisher(store);
        }

        @Bean
        @ConditionalOnMissingBean(Formatter.class)
        DefaultFormatter defaultFormatter() {
            return new DefaultFormatter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserExtensions {

        @Bean
        AuditStore auditStore() {
            return new MemoryAuditStore();
        }

        @Bean
        CustomFormatter customFormatter() {
            return new CustomFormatter();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(LibraryAutoConfiguration.class));

    @Test
    void classConditionDisablesAllLibraryBeans() {
        runner.withPropertyValues(
                "acme.library.enabled=false",
                "acme.library.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CoreService.class);
                    assertThat(context).doesNotHaveBean(MetricsService.class);
                    assertThat(context).doesNotHaveBean(AuditPublisher.class);
                    assertThat(context).doesNotHaveBean(DefaultFormatter.class);
                });
    }

    @Test
    void methodConditionsOnlyDisableTheirOwnBeans() {
        runner.withPropertyValues("acme.library.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).doesNotHaveBean(MetricsService.class);
                    assertThat(context).doesNotHaveBean(AuditPublisher.class);
                    assertThat(context).hasSingleBean(DefaultFormatter.class);
                });
    }

    @Test
    void userBeansSatisfyConditionsAndReplaceDefault() {
        runner.withPropertyValues(
                "acme.library.enabled=true",
                "acme.library.metrics.enabled=true")
                .withUserConfiguration(UserExtensions.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).hasSingleBean(MetricsService.class);
                    assertThat(context).hasSingleBean(AuditStore.class);
                    assertThat(context).hasSingleBean(AuditPublisher.class);
                    assertThat(context.getBean(AuditPublisher.class).destination())
                            .isEqualTo("memory");
                    assertThat(context).hasSingleBean(CustomFormatter.class);
                    assertThat(context).doesNotHaveBean(DefaultFormatter.class);
                    assertThat(context.getBean(Formatter.class).format())
                            .isEqualTo("custom");
                });
    }
}
~~~

Chạy bằng Gradle wrapper trong project đã có dependency test:

~~~bash
./gradlew test --tests "com.example.demo.ConditionScopeTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.ConditionScopeTest"
~~~

**Kết quả kỳ vọng:** 3 test PASS. Các assertion kiểm tra bean trong context, không dựa vào stdout cụ thể.

- Test 1: class condition không khớp nên bean của LibraryAutoConfiguration không được đăng ký.
- Test 2: class condition khớp; method-level conditions riêng không khớp thì bean lõi và default formatter vẫn được đăng ký.
- Test 3: property metrics bật, user config cung cấp AuditStore và Formatter; publisher được tạo, formatter mặc định back off và custom formatter được dùng.

`AutoConfigurations.of(...)` đưa auto-configuration vào runner. `withUserConfiguration(...)` mô phỏng bean do ứng dụng khai báo; Spring Boot xử lý chúng trước auto-configuration, phù hợp để kiểm thử `@ConditionalOnBean` và `@ConditionalOnMissingBean`.

## 10. Đọc Condition Evaluation Report để hiểu vì sao bean bị bỏ qua

Khi một bean không xuất hiện, đừng đoán chỉ từ source. Bật `--debug` khi chạy ứng dụng hoặc đặt `debug=true` để Spring Boot in **Condition Evaluation Report**.

Trong test có thể thêm listener:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .run(context -> {
            // assertions cho context
        });
~~~

Đoạn trên là snippet chẩn đoán để thêm vào runner; cần import đúng class và chạy trong test có logging được cấu hình.

Report thường phân biệt:
- **Positive matches:** condition đã khớp, cấu hình/bean đủ điều kiện.
- **Negative matches:** condition không khớp và lý do.
- **Unconditional classes:** cấu hình không có điều kiện tương ứng.

Với ứng dụng có Spring Boot Actuator và endpoint được expose phù hợp, `/actuator/conditions` cung cấp thông tin condition evaluation. Hãy kiểm tra cấu hình bảo mật/exposure của môi trường trước khi dùng endpoint.

### Checklist debug theo thứ tự

1. Auto-configuration có trong `AutoConfiguration.imports` không?
2. Class-level condition nào đang áp dụng và điều kiện nào không khớp?
3. Class-level imports hoặc nested configuration nào đang được đưa vào?
4. Bean method có condition riêng không? Condition có kiểm tra property, classpath hay bean type?
5. Nếu là `@ConditionalOnBean`, prerequisite đã được đăng ký **trước thời điểm đánh giá** chưa?
6. Return type method có đủ thông tin type không?
7. Nếu bean có nhiều candidate, consumer có bị ambiguity hoặc cần `@Primary`/`@Qualifier` không?
8. Nếu class tùy chọn không có trên classpath, có đang bị tham chiếu trong signature của một method bên ngoài nested config được bảo vệ không?

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Class có `@ConditionalOnProperty` false nhưng một method có property true, nên bean method vẫn chạy | Điều kiện method không thể mở lại cấu hình đã bị class-level condition loại |
| Condition class-level và method-level là cùng một phạm vi | Class-level áp dụng cho cấu hình rộng; method-level áp dụng một bean |
| Mọi condition đều chạy trước khi Spring đọc các method | Phase phụ thuộc loại condition; classpath condition và bean condition có thời điểm khác nhau |
| Có class `AuditStore` trên classpath là `@ConditionalOnBean(AuditStore.class)` khớp | Phải có bean definition phù hợp trong BeanFactory |
| Method có `@ConditionalOnMissingBean` không chỉ rõ type thì Spring tự đoán theo tham số | Target mặc định dựa trên return type method; hãy khai báo return type cụ thể |
| Method condition false làm mọi bean anh em biến mất | Chỉ bean method đó bị condition riêng chặn; class condition mới có phạm vi rộng |
| Thêm `@DependsOn` sẽ làm `@ConditionalOnBean` trước đó khớp | `@DependsOn` liên quan thứ tự khởi tạo instance, không hồi tố đăng ký bean definition |
| Dùng method-level `@ConditionalOnClass` để bảo vệ return type tùy chọn luôn an toàn | JVM có thể phải resolve method signature trước khi condition chạy; cô lập trong nested configuration |
| `@ConditionalOnExpression` tham chiếu bean luôn an toàn | Bean có thể bị khởi tạo rất sớm và bỏ lỡ post-processing; tránh tham chiếu bean trong expression |
| Thấy context khởi động thành công nghĩa là mọi bean mong đợi đã có | Bean có thể bị condition loại mà context vẫn khởi động; test phải assert sự hiện diện/vắng mặt của bean |

## 12. Nguyên tắc thiết kế và cách review auto-configuration

Khi review một auto-configuration, dùng trình tự sau:

- **Đầu class:** xác nhận annotation `@AutoConfiguration`, tên trong imports, class-level conditions, `@Import`, nested configurations, properties và before/after metadata.
- **Phân loại điều kiện:** condition kiểm tra classpath, environment, web context hay bean registry? Đừng suy ra phase chỉ từ tên annotation.
- **Mỗi @Bean:** ghi tên bean, return type, method-level condition và dependency tham số.
- **Điều kiện chung:** chỉ đặt ở class nếu toàn bộ cấu hình thật sự chia sẻ cùng requirement.
- **Điều kiện riêng:** đặt ở method hoặc nested configuration để tính năng tùy chọn không vô tình chặn bean lõi.
- **Optional dependency:** dùng class condition và nested configuration để cách ly type không luôn có trên runtime classpath.
- **Bean condition:** đặt trong auto-configuration; kiểm tra thứ tự với auto-configuration upstream nếu cần bean do cấu hình khác cung cấp.
- **Override:** dùng `@ConditionalOnMissingBean` để default back off khi người dùng có bean phù hợp.
- **Return type:** khai báo kiểu cụ thể nhất có thể, nhất là với condition dựa trên bean type.
- **Test matrix:** kiểm tra class condition true/false, method condition true/false, prerequisite bean có/không, user override và classpath optional có/không.

Một sơ đồ tư duy rút gọn:

~~~mermaid
flowchart TD
    A["Đọc @AutoConfiguration và imports"] --> B["Đọc class-level conditions"]
    B --> C{"Cấu hình được áp dụng?"}
    C -->|"Không"| X["Không có bean từ cấu hình này"]
    C -->|"Có"| D["Đọc từng phương thức @Bean"]
    D --> E["Kiểm tra method-level conditions"]
    E --> F{"Method khớp?"}
    F -->|"Không"| Y["Bỏ qua bean method này"]
    F -->|"Có"| G["Đăng ký bean definition"]
    G --> H["Giải quyết dependency và khởi tạo theo lifecycle"]
~~~

Sơ đồ là hướng dẫn đọc và phân tích. Trong thực tế các condition được đánh giá ở phase phù hợp; không phải tất cả đều là một phép kiểm tra tuyến tính duy nhất trước khi Spring đọc mọi method.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, class conditions, bean conditions, imports, thứ tự auto-configuration và `ApplicationContextRunner`.
- [Spring Framework 6.1 — `@Conditional` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/context/annotation/Conditional.html): phạm vi TYPE/METHOD và semantics của condition trên `@Configuration`.
- [Spring Framework 6.1 — `ConfigurationCondition.ConfigurationPhase` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): `PARSE_CONFIGURATION` và `REGISTER_BEAN`.
- [Spring Boot 3.3.13 — `@ConditionalOnBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): yêu cầu bean đã có trong BeanFactory.
- [Spring Boot 3.3.13 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): đăng ký default theo bean absence.
