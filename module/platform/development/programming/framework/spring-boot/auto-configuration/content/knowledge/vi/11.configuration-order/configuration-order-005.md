# Thứ tự xử lý cấu hình khác với thứ tự khởi tạo bean

## 1. Mục tiêu của bài học

Trong Spring Boot Auto Configuration có hai câu hỏi **khác nhau**:

1. **Cấu hình nào được xử lý trước?** Spring đọc metadata và xử lý các lớp cấu hình để quyết định **bean definition nào** được đăng ký, trong đó có việc đánh giá `@ConditionalOnBean`, `@ConditionalOnMissingBean` và các điều kiện khác.
2. **Bean instance nào được khởi tạo trước?** Sau khi các definition đã có, container tạo đối tượng theo quan hệ phụ thuộc, phạm vi sống (scope), eager/lazy initialization và các ràng buộc như `@DependsOn`.

Điểm cốt lõi: **sắp xếp `@AutoConfiguration` bằng `before`/`after` không có nghĩa các bean của cấu hình trước sẽ được khởi tạo trước**. Tài liệu Spring Boot 3.3 nói rõ thứ tự áp dụng auto-configuration chỉ ảnh hưởng thứ tự **định nghĩa bean**; thứ tự **tạo bean** được quyết định bởi dependency và quan hệ `@DependsOn`.

Bài này giải thích hai trục thời gian, cách dùng đúng các annotation, ví dụ Java 17+ có test, các lỗi thường gặp và phương pháp chẩn đoán.

## 2. Phân biệt bốn khái niệm

| Khái niệm | Nội dung | Câu hỏi nó trả lời |
| --- | --- | --- |
| **Thứ tự xử lý configuration** | Thứ tự Spring Boot áp dụng các auto-configuration, phân tích `@Bean` và điều kiện, đưa definition vào container | “Đến thời điểm xét điều kiện, Spring đã **biết** những bean nào?” |
| **Đăng ký bean definition** | Tên, kiểu có thể xác định, factory method, scope, lazy flag, dependencies... được lưu trong BeanFactory | “Có một **mô tả để tạo bean** hay chưa?” |
| **Khởi tạo bean** | Container tạo instance, tiêm dependency và áp dụng lifecycle/post-processing phù hợp | “**Đối tượng thật** đã được tạo hay chưa?” |
| **Thứ tự thực thi logic sau khởi động** | Logic chạy sau context refresh, ví dụ `ApplicationRunner`, `CommandLineRunner` hoặc sự kiện ứng dụng sẵn sàng | “**Công việc nghiệp vụ** bắt đầu khi nào?” |

Một bean definition có thể **tồn tại** trong khi instance chưa được tạo, ví dụ bean `@Lazy`. Ngược lại, việc một bean được khởi tạo **không tự chứng minh** cấu hình chứa nó đã được xử lý trước cấu hình khác theo cách mà các điều kiện yêu cầu.

Cần dùng đúng từ:

- “`@ConditionalOnBean(MyType.class)` khớp” chủ yếu liên quan đến **bean definition/metadata đã được xử lý**, không có nghĩa instance `MyType` đã khởi tạo.
- “`@DependsOn("cache")` bảo đảm cache khởi tạo trước service” là một ràng buộc **khởi tạo bean**; nó không tự sắp xếp thứ tự các auto-configuration được đánh giá.
- “`@AutoConfiguration(after = X.class)`” cho Spring Boot biết một auto-configuration nên được **áp dụng sau X**; nó không tự tạo bean X hoặc buộc các instance trong X tạo xong trước.

## 3. Hai trục thời gian của một lần khởi động

Sơ đồ khái niệm, đã lược bớt các bước nội bộ của Spring:

```text
TRỤC A — XỬ LÝ CẤU HÌNH / BEAN DEFINITION
Đọc @Configuration, danh sách auto-configuration
    -> xác định thứ tự before/after
    -> đánh giá điều kiện theo metadata đã có
    -> đăng ký những bean definition phù hợp
    -> hoàn tất các bước xử lý definition liên quan

TRỤC B — TẠO / KHỞI TẠO INSTANCE
BeanFactory/BeanPostProcessor sẵn sàng cho giai đoạn tạo bean
    -> tạo các singleton không lazy theo nhu cầu và dependency
    -> resolve constructor / factory-method parameters
    -> áp dụng @DependsOn và lifecycle
    -> để các bean lazy hoặc scope phù hợp được tạo khi cần

SAU KHI CONTEXT ĐÃ REFRESH
Chạy cơ chế ứng dụng sau khởi động, ví dụ ApplicationRunner
```

Đây là sơ đồ **quy tắc tổng quát**, không phải lời khẳng định mọi hoạt động tạo bean đều xảy ra tại một điểm duy nhất: một số bean hạ tầng hoặc bean bị yêu cầu quá sớm có thể được tạo ngay trong lúc container vẫn xử lý cấu hình. Vì vậy cần tránh thiết kế phụ thuộc vào thứ tự khởi tạo “ngẫu nhiên” quan sát được.

Với singleton thông thường, `ApplicationContext` sẽ eager-create nhiều bean khi khởi động. Tuy nhiên:

- Bean `@Lazy` có definition trước nhưng có thể chưa có instance khi context refresh xong.
- Một bean `@Lazy` vẫn **bị tạo tại startup** nếu một singleton eager cần nó qua injection hoặc `@DependsOn`.
- Bean prototype được tạo khi yêu cầu, không phải eager-preinstantiate giống singleton thông thường.
- Quan hệ constructor/factory-method injection buộc các dependency cần thiết có sẵn trước khi tạo xong bean phụ thuộc.

## 4. Thứ tự **xử lý auto-configuration**: `before`, `after` và các điều kiện

### 4.1. Khi nào cần `after`?

Giả sử `StorageAutoConfiguration` khai báo bean `StorageClient`, còn `ReportAutoConfiguration` chỉ đăng ký `ReportService` nếu Spring đã có một bean `StorageClient`.

Mảnh mã minh họa, giả sử các kiểu `StorageClient` và `ReportService` được định nghĩa trong dự án:

```java
@AutoConfiguration
class StorageAutoConfiguration {

    @Bean
    StorageClient storageClient() {
        return new StorageClient();
    }
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(StorageClient.class)
    ReportService reportService() {
        return new ReportService();
    }
}
```

Ở đây `after = StorageAutoConfiguration.class` giải quyết **thứ tự xử lý definition**: khi đến điều kiện trên `reportService`, Spring có cơ hội nhìn thấy bean definition `StorageClient` đã đăng ký từ cấu hình trước. **Không có bảo đảm** instance `storageClient` đã được khởi tạo trước khi `ReportAutoConfiguration` được phân tích.

Một cách viết tương đương trong Spring Boot 3.3 là:

```java
@AutoConfigureAfter(StorageAutoConfiguration.class)
@AutoConfiguration
class ReportAutoConfiguration {
    // Các @Bean của cấu hình này
}
```

Các thuộc tính liên quan:

- `@AutoConfiguration(before = OtherAutoConfiguration.class)`: cấu hình hiện tại nên được áp dụng trước cấu hình kia.
- `@AutoConfiguration(after = OtherAutoConfiguration.class)`: cấu hình hiện tại nên được áp dụng sau cấu hình kia.
- `beforeName`, `afterName`: dùng tên đầy đủ của cấu hình khi không muốn tham chiếu trực tiếp class; hữu ích với auto-configuration tùy chọn trên classpath.
- `@AutoConfigureBefore`, `@AutoConfigureAfter`: các annotation chuyên biệt diễn đạt cùng kiểu ràng buộc thứ tự.

Các khai báo này dùng để sắp **auto-configuration**, không phải cơ chế tổng quát để điều khiển thứ tự mọi `@Configuration` hoặc mọi bean trong chương trình. Nếu có nhiều quy tắc before/after, Spring Boot sẽ tính toán thứ tự tương thích; tránh vòng ràng buộc.

### 4.2. `@AutoConfigureOrder` có vai trò gì?

`@AutoConfigureOrder` là biến thể order dành riêng cho các auto-configuration. Nó có thể dùng khi muốn ưu tiên tương đối giữa các cấu hình **không có quan hệ phụ thuộc trực tiếp**. Về cơ bản, giá trị order nhỏ có ưu tiên áp dụng sớm hơn. Nó **không** thay thế ràng buộc rõ ràng `after = ...` khi một điều kiện thật sự cần metadata của cấu hình khác.

```java
@AutoConfiguration
@AutoConfigureOrder(100)
class MetricsAutoConfiguration {
    // Khai báo bean definition
}
```

Đừng suy luận “mọi bean bên trong `MetricsAutoConfiguration` được tạo ở vị trí 100”. Thứ tự order ở đây áp dụng cho **auto-configuration**, không phải thời điểm gọi constructor của bean.

### 4.3. Vì sao `@ConditionalOnBean` và `@ConditionalOnMissingBean` nhạy với thứ tự?

Các điều kiện bean được đánh giá dựa trên **những bean definition đã được xử lý đến thời điểm đó**.

Giả sử cấu hình X cung cấp bean `Client` và cấu hình Y có:

```java
@Bean
@ConditionalOnBean(Client.class)
ClientMonitor monitor() {
    return new ClientMonitor();
}
```

Nếu Y được đánh giá trước khi Spring biết definition của `Client` từ X, điều kiện có thể **không khớp**. Khi thêm ràng buộc `@AutoConfiguration(after = X.class)` cho Y, Spring có thể đánh giá nó với definition của X đã có. Điều này khác hoàn toàn với yêu cầu “instance Client đã chạy constructor”.

Với `@ConditionalOnMissingBean(Client.class)`, thứ tự còn quan trọng hơn: nếu kiểm tra quá sớm, Spring có thể tạo bean mặc định dù một auto-configuration khác dự định khai báo `Client` sau đó. Vì vậy Spring Boot khuyến nghị dùng các điều kiện có/thiếu bean trong **auto-configuration** (được áp dụng sau bean definition do người dùng khai báo) và thiết lập thứ tự thích hợp giữa những auto-configuration có phụ thuộc.

Khi dùng điều kiện theo kiểu bean, hãy khai báo kiểu trả về `@Bean` đủ chính xác để Spring nhận diện kiểu **trước khi tạo instance**. Tránh ẩn kiểu đích sau `Object` hoặc một factory method không cho biết kiểu hữu ích.

## 5. Thứ tự **khởi tạo bean**: dependency, `@DependsOn`, `@Lazy`

### 5.1. Dependency injection tạo quan hệ thực sự

Nếu constructor/factory method của `ReportService` cần `StorageClient`:

```java
@Bean
ReportService reportService(StorageClient storageClient) {
    return new ReportService(storageClient);
}
```

Spring phải resolve `StorageClient` trước khi hoàn thành việc tạo `ReportService`. Đây là **quan hệ dependency**, hoạt động dù hai phương thức `@Bean` được khai báo ở thứ tự văn bản nào. `ReportService(StorageClient)` là constructor giả định của lớp ứng dụng; đoạn trên cần được đặt trong class cấu hình có các import thích hợp.

### 5.2. `@DependsOn` đặt thứ tự khởi tạo tường minh

Có trường hợp một bean cần hạ tầng khác đã khởi tạo nhưng không inject trực tiếp nó, chẳng hạn hạ tầng đăng ký driver/registry. Khi đó có thể dùng:

```java
@Bean
@DependsOn("auditInfrastructure")
AuditService auditService() {
    return new AuditService();
}
```

Ý nghĩa: trước khi tạo `auditService`, container phải khởi tạo bean tên `auditInfrastructure`. Nếu dependency được đặt là tên không tồn tại thì khởi tạo có thể thất bại. Với singleton, quan hệ này cũng ảnh hưởng thứ tự hủy bean theo chiều ngược lại, bảo đảm dependent được hủy trước dependency.

`@DependsOn` **không có nghĩa** “xử lý cấu hình chứa `auditInfrastructure` trước khi đánh giá điều kiện bean”. Nếu `@ConditionalOnBean` đã đánh giá sai do definition chưa có, thêm `@DependsOn` vào bean phía sau **không sửa được** điều kiện trước đó.

### 5.3. `@Lazy` tách rõ definition khỏi instance

```java
@Bean
@Lazy
LargeCache largeCache() {
    return new LargeCache();
}
```

Spring đã có definition `largeCache`, nhưng singleton này không buộc phải được tạo ngay khi context refresh. Khi mã gọi `getBean(LargeCache.class)` hoặc một eager singleton thực sự cần nó, instance có thể được tạo.

Đây là một cách rất rõ để thấy **đăng ký bean không đồng nghĩa khởi tạo bean**. Nhưng `@Lazy` cũng không làm điều kiện `@ConditionalOnBean(LargeCache.class)` từ chối: nếu kiểu bean đã được đăng ký và có thể nhận diện, điều kiện vẫn có thể khớp dù instance chưa tồn tại.

### 5.4. `@Order` không phải lệnh khởi tạo trước

`@Order`/`Ordered` thường phục vụ xếp thứ tự những thành phần được Spring **sắp xếp để sử dụng**, như danh sách các bean khi inject vào `List<Strategy>` hoặc các extension points có hỗ trợ ordering. Nó **không là cam kết** rằng singleton số 1 khởi tạo trước singleton số 2.

Vì vậy:

- Muốn **definition/configuration** sẵn sàng khi xét điều kiện: chọn `@AutoConfiguration(after/before)`.
- Muốn **bean A phải tạo trước B**: biểu diễn dependency trực tiếp qua constructor/factory parameters; dùng `@DependsOn` nếu không có tham chiếu inject tự nhiên.
- Muốn **trì hoãn** một instance: xem `@Lazy`, nhưng nhớ rằng dependency eager có thể kích hoạt nó.
- Muốn **thứ tự gọi các strategy**: sử dụng `@Order` hoặc giao thức sắp thứ tự của extension point liên quan.

## 6. Thực hành Java 17+ và Spring Boot 3.3: hai bài test phân biệt

Ví dụ sau dùng `ApplicationContextRunner` tạo các context độc lập, với hai phép kiểm tra bổ sung cho nhau:

1. **Ordering của auto-configuration:** bean definition của provider có sẵn nên `@ConditionalOnBean` khớp, dù provider `@Lazy` **chưa khởi tạo**.
2. **Ordering khi tạo instance:** `@DependsOn` buộc một hạ tầng `@Lazy` khởi tạo **trước** service eager.

Tạo tệp `src/test/java/example/order/ConfigurationOrderTests.java` trong dự án Java 17+ có Spring Boot 3.3.x, `spring-boot-starter-test`, JUnit Jupiter và AssertJ:

```java
package example.order;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigurationOrderTests {

    static final class SharedClient {}
    static final class FeatureMarker {}

    @AutoConfiguration
    static class ProviderAutoConfiguration {
        @Bean
        @Lazy
        SharedClient sharedClient() {
            return new SharedClient();
        }
    }

    @AutoConfiguration(after = ProviderAutoConfiguration.class)
    static class FeatureAutoConfiguration {
        @Bean
        @ConditionalOnBean(SharedClient.class)
        FeatureMarker featureMarker() {
            return new FeatureMarker();
        }
    }

    @Test
    void beanConditionSeesDefinitionBeforeInstanceExists() {
        new ApplicationContextRunner()
                // Cố tình liệt kê consumer trước provider:
                .withConfiguration(AutoConfigurations.of(
                        FeatureAutoConfiguration.class,
                        ProviderAutoConfiguration.class
                ))
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureMarker.class);

                    // Definition của bean lazy đã có.
                    assertThat(context.containsBeanDefinition("sharedClient"))
                            .isTrue();

                    // Nhưng instance vẫn chưa được tạo.
                    assertThat(context.getBeanFactory()
                            .containsSingleton("sharedClient")).isFalse();

                    // Khi lấy bean, instance mới được tạo.
                    context.getBean(SharedClient.class);
                    assertThat(context.getBeanFactory()
                            .containsSingleton("sharedClient")).isTrue();
                });
    }

    static final class Trace {
        final List<String> events = new ArrayList<>();
    }

    static final class Infrastructure {}
    static final class BusinessService {}

    @Configuration(proxyBeanMethods = false)
    static class InitializationConfiguration {
        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        @DependsOn("infrastructure")
        BusinessService businessService(Trace trace) {
            trace.events.add("businessService");
            return new BusinessService();
        }

        @Bean
        @Lazy
        Infrastructure infrastructure(Trace trace) {
            trace.events.add("infrastructure");
            return new Infrastructure();
        }
    }

    @Test
    void dependsOnInitializesLazyDependencyBeforeService() {
        new ApplicationContextRunner()
                .withUserConfiguration(InitializationConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(BusinessService.class);
                    assertThat(context).hasSingleBean(Infrastructure.class);
                    assertThat(context.getBean(Trace.class).events)
                            .containsExactly(
                                    "infrastructure",
                                    "businessService"
                            );
                });
    }
}
```

**Giải thích test 1:** `AutoConfigurations.of(...)` là cơ chế test đưa các auto-configuration vào runner. Dù truyền `FeatureAutoConfiguration` trước, ràng buộc `after = ProviderAutoConfiguration.class` yêu cầu Boot sắp xếp lại để condition có thể thấy definition `SharedClient`. Bean `sharedClient` vẫn `@Lazy` nên `containsSingleton("sharedClient")` ban đầu là `false`. Chỉ khi gọi `context.getBean(SharedClient.class)` nó mới trở thành `true`. Đây là bằng chứng trực tiếp rằng **condition dựa trên definition không cần bean instance có sẵn**.

**Giải thích test 2:** `BusinessService` là singleton eager, còn `Infrastructure` được đánh dấu `@Lazy`. Phương thức `businessService` lại có `@DependsOn("infrastructure")` nên container phải tạo hạ tầng trước khi tạo service. `Trace.events` ghi nhận đúng `infrastructure` rồi `businessService`. Nếu bỏ `@DependsOn`, bean hạ tầng lazy không nhất thiết được tạo cùng service; vì thế đây là test có ý nghĩa về ràng buộc lifecycle chứ không dựa vào thứ tự khai báo phương thức.

**Lệnh chạy** tại thư mục dự án có Gradle wrapper và `test` dùng JUnit Platform:

```bash
./gradlew test --tests example.order.ConfigurationOrderTests
```

Nếu dùng Maven với Surefire hỗ trợ JUnit 5:

```bash
./mvnw -Dtest=ConfigurationOrderTests test
```

**Kết quả kỳ vọng:** **hai test PASS**. Không ghi chuỗi stdout cố định vì đầu ra Gradle/Maven phụ thuộc phiên bản và cấu hình logging. Bài test dùng class lồng nhau để tự chứa ví dụ; trong thư viện production, auto-configuration thường là các top-level class và được khai báo trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Dùng `ApplicationContextRunner` thì không cần tạo file imports cho chính ví dụ test này.

## 7. Ví dụ chọn sai cơ chế và cách sửa

### Tình huống A: Điều kiện `@ConditionalOnBean` báo thiếu dù bean sẽ được khai báo

**Triệu chứng:** `MetricsAutoConfiguration` có `@ConditionalOnBean(StorageClient.class)` không đăng ký metrics, nhưng sau đó container lại có bean `StorageClient`.

**Nguyên nhân có thể:** auto-configuration tạo metrics được đánh giá khi definition `StorageClient` của cấu hình khác **chưa được xử lý**. Khi Spring đi qua điều kiện, nó không thể nhìn vào tương lai.

**Hướng xử lý:** xác định cấu hình thực sự khai báo `StorageClient`; đặt ràng buộc:

```java
@AutoConfiguration(after = StorageAutoConfiguration.class)
class MetricsAutoConfiguration {
    // @Bean @ConditionalOnBean(StorageClient.class) ...
}
```

Đoạn này không chạy độc lập; hãy đặt các type/import tương ứng vào dự án thật. Bổ sung test `ApplicationContextRunner` với cả hai auto-configuration để chứng minh điều kiện khớp ở thứ tự mong đợi. Đừng cố sửa lỗi này bằng `@DependsOn("storageClient")`, vì nó chỉ tác động lên **tạo instance sau khi bean definition đã được chấp nhận**.

### Tình huống B: Bean phải sử dụng hạ tầng đã sẵn sàng, nhưng chỉ thêm `@AutoConfiguration(after=...)`

**Triệu chứng:** một bean `ReportService` cần một registry đã chạy khởi tạo; cấu hình đăng ký registry được xử lý trước, nhưng thứ tự constructor/`@PostConstruct` vẫn không đáp ứng mong đợi.

**Nguyên nhân:** thứ tự định nghĩa không áp đặt thứ tự tạo instance.

**Hướng xử lý:** tốt nhất đưa registry thành dependency thật:

```java
@Bean
ReportService reportService(Registry registry) {
    return new ReportService(registry);
}
```

Nếu chỉ cần thứ tự lifecycle mà không phải injection, có thể dùng `@DependsOn("registry")`. Nếu mục tiêu là chờ **ứng dụng hoàn toàn sẵn sàng** để chạy tác vụ nghiệp vụ, xem cơ chế `ApplicationRunner`/`CommandLineRunner` hoặc sự kiện phù hợp thay vì gắn side effect vào constructor. Các snippet giả định type được định nghĩa trong ứng dụng.

### Tình huống C: Bean `@Lazy` xuất hiện trong condition nhưng chưa khởi tạo

**Triệu chứng:** `@ConditionalOnBean(ExpensiveClient.class)` khớp, trong khi chưa thấy log constructor `ExpensiveClient`.

**Đây thường là hành vi đúng:** điều kiện kiểm tra metadata của bean đã đăng ký. Bean lazy có definition nhưng chưa cần tạo instance. Nếu một eager singleton inject nó thì nó có thể sẽ được tạo lúc startup. Đừng sửa bằng cách ép eager chỉ để condition nhìn thấy bean.

## 8. Chẩn đoán và kiểm thử đúng lớp vấn đề

| Vấn đề đang điều tra | Bằng chứng nên xem | Công cụ hữu ích |
| --- | --- | --- |
| Vì sao một auto-configuration không được chọn? | Kết quả `ConditionEvaluationReport`, class condition, property/bean condition | Chạy với `--debug`; test `ApplicationContextRunner` |
| Bean có được **đăng ký** chưa? | Bean definition theo tên/kiểu | `containsBeanDefinition(...)`, `getBeanDefinitionNames()`, `getBeanNamesForType(...)` |
| Bean singleton đã **khởi tạo** chưa? | Instance trong singleton cache | `getBeanFactory().containsSingleton(...)` |
| Vì sao bean này tạo trước bean kia? | Dependency graph, `@DependsOn`, `@Lazy`, vòng đời | Trace trong constructor/factory method/`@PostConstruct` |
| Vì sao service chạy quá sớm hoặc quá muộn? | Thời điểm context ready, runner, lifecycle | `ApplicationRunner`, sự kiện ứng dụng, log theo timestamp |

Hướng debug có hệ thống:

1. **Xác định thứ gì cần thứ tự:** việc **nhận diện/đăng ký bean** hay việc **khởi tạo instance**. Nhiều lỗi bắt nguồn từ việc chọn sai loại thứ tự.
2. **Kiểm tra cấu hình khai báo bean và return type:** một `@Bean` trả về kiểu quá chung có thể khiến điều kiện theo kiểu cụ thể không nhận ra bean trên metadata.
3. **Kiểm tra `after`/`before` giữa auto-configuration:** chỉ thêm quan hệ cần thiết, tránh dựa vào tên lớp hay vị trí trong file như một hợp đồng thứ tự.
4. **Kiểm tra dependency khi tạo bean:** constructor parameters, `@DependsOn`, `@Lazy` và scope; xem có dependency vòng hay bean bị kéo lên eager bởi dependency khác không.
5. **Viết test đúng thời điểm:** trong một context chưa chủ động `getBean(...)`, kiểm tra bean definition và `containsSingleton(...)` riêng biệt. Nếu test gọi `getBean(...)` quá sớm, chính lệnh test sẽ thay đổi kết quả “đã khởi tạo hay chưa”.
6. **Quan sát report condition:** `ConditionEvaluationReport` cho biết vì sao một cấu hình được đưa vào/bỏ qua; report này không chứng minh thời điểm constructor chạy. Cần trace lifecycle nếu nghi ngờ thứ tự tạo instance.

Một lệnh Spring Boot thường dùng để bật báo cáo điều kiện:

```bash
java -jar app.jar --debug
```

Lệnh trên áp dụng với ứng dụng đã build được JAR thực thi tên `app.jar` và được chạy bằng Java phù hợp. Báo cáo có thể rất dài; tập trung vào auto-configuration đang điều tra. Không suy luận thứ tự khởi tạo bean chỉ từ thứ tự dòng in trong condition report.

## 9. Những hiểu lầm thường gặp

- **“`after = X` nghĩa là bean của X chạy constructor trước.”** Sai. Nó tác động đến **auto-configuration/definition order**.
- **“`@DependsOn` sẽ làm `@ConditionalOnBean` thấy bean.”** Sai. `@DependsOn` chỉ ảnh hưởng khi khởi tạo các definition đã đăng ký; nó không đảo ngược quyết định condition trước đó.
- **“Cứ khai báo `@Bean` ở đầu file là instance tạo trước.”** Không có hợp đồng tổng quát đảm bảo điều này. Hãy thể hiện dependency hoặc lifecycle rõ ràng.
- **“Có bean definition nghĩa là đã có bean instance.”** Sai, đặc biệt với `@Lazy`, prototype hoặc scope khác.
- **“`@Order(1)` buộc bean được tạo trước `@Order(2)`.”** Không. `@Order` là cơ chế sắp thứ tự sử dụng trong những ngữ cảnh hỗ trợ nó, không là ràng buộc startup instance.
- **“Nếu bean bị tạo sớm thì điều kiện sẽ biết được nó.”** Điều kiện bean của Spring Boot thường xét definition đã được xử lý; khởi tạo một bean sớm không sửa được thứ tự đăng ký definition.
- **“`@Lazy` đảm bảo không tạo ở startup.”** Không nếu một eager singleton hoặc `@DependsOn` cần bean lazy.
- **“`@AutoConfigureOrder` có thể thay dependency.”** Nó chỉ sắp thứ tự auto-configuration, không mô tả quan hệ cần instance sẵn sàng.
- **“Cần kết nối mạng ở constructor để chắc đã ready.”** Constructor được gọi trong giai đoạn tạo bean; các tác vụ cần ứng dụng sẵn sàng nên dùng lifecycle phù hợp và tránh side effect quá sớm.

## 10. Câu hỏi tự kiểm tra

1. `ConsumerAutoConfiguration` có `@ConditionalOnBean(StorageClient.class)`. Cần thấy definition do `StorageAutoConfiguration` cung cấp. Dùng annotation nào? **`@AutoConfiguration(after = StorageAutoConfiguration.class)`** (hoặc `@AutoConfigureAfter`). Đây là quan hệ thứ tự **xử lý cấu hình**.
2. `StorageClient` có `@Lazy` và definition đã được đăng ký. `@ConditionalOnBean(StorageClient.class)` có thể khớp không? **Có** nếu metadata đủ để nhận diện. Không cần instance đã được khởi tạo.
3. `AuditService` phải tạo sau bean tên `registry` nhưng không cần inject registry. Dùng gì? **`@DependsOn("registry")`** trên definition `AuditService`, với tên bean hợp lệ.
4. Có thể dùng `@Order(1)` để buộc constructor của `StorageClient` chạy trước constructor `ReportService` không? **Không.** Biểu diễn quan hệ dependency hoặc `@DependsOn`.
5. Cần truyền `StorageClient` vào `ReportService`. Có cần thêm `@DependsOn` không? **Thông thường không**, constructor/factory-method dependency đã ràng buộc việc resolve instance `StorageClient`.
6. `@AutoConfiguration(after = X.class)` có tự đảm bảo `X` được kích hoạt, hoặc bean của X chắc chắn tồn tại không? **Không**. X vẫn có thể bị điều kiện khác loại bỏ; after chỉ xác định thứ tự tương đối khi các cấu hình được xét.
7. Một test cần chứng minh bean chưa được khởi tạo. Có nên gọi `getBean()` trước khi kiểm tra `containsSingleton()` không? **Không**, vì chính `getBean()` có thể làm bean được tạo.

## 11. Tài liệu tham khảo

- [Spring Boot 3.3 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): các thuộc tính `before`, `after`, `beforeName`, `afterName`.
- [Spring Boot 3.3 — AutoConfigureBefore API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): giải thích chính thức về khác biệt giữa thứ tự bean definitions và thứ tự khởi tạo bean.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): thứ tự auto-config và cách điều kiện bean phụ thuộc những definitions đã được xử lý.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): singleton eager/lazy và trường hợp bean lazy vẫn được tạo vì dependency.
- [Spring Framework — Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): thứ tự tạo và hủy singleton theo dependency.
