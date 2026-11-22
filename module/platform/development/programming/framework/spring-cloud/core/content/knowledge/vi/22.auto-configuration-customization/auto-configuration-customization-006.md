# Thứ tự định nghĩa cấu hình và thứ tự khởi tạo bean

Trong Spring, việc một lớp cấu hình được xử lý trước không có nghĩa bean do lớp đó khai báo sẽ được tạo trước. Tương tự, một bean xuất hiện trước trong file Java hoặc được gắn `@Order(1)` không mặc nhiên được khởi tạo trước các singleton khác.

Để tùy biến auto-configuration và kiểm soát vòng đời ứng dụng chính xác, cần phân biệt ba khái niệm:

1. **Thứ tự xử lý lớp cấu hình:** Spring đọc, phân tích và xử lý các nguồn cấu hình như `@Configuration`, `@Import`, component scan và auto-configuration.
2. **Thứ tự đăng ký BeanDefinition:** container ghi nhận metadata mô tả bean, gồm tên, kiểu, scope, factory method, điều kiện và dependency.
3. **Thứ tự khởi tạo bean:** container tạo object, inject dependency, chạy callback khởi tạo và đưa instance vào trạng thái sẵn sàng.

Ba giai đoạn có liên hệ nhưng không đồng nhất. `@Order` trên lớp cấu hình có thể ảnh hưởng thứ tự xử lý cấu hình; thứ tự auto-configuration ảnh hưởng thứ tự định nghĩa bean; còn việc tạo singleton chủ yếu tuân theo dependency graph và các quan hệ `@DependsOn`.

Bài học thuộc chương **Tùy biến tự động cấu hình** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào cách Spring xử lý cấu hình Java, auto-configuration của Spring Boot, các extension point của container và cách kiểm thử thứ tự khởi tạo mà không dựa vào thứ tự khai báo tình cờ.

## 1. Ba thứ tự cần phân biệt

Một ứng dụng Spring Boot khởi động qua nhiều giai đoạn. Có thể mô tả khái quát:

~~~mermaid
flowchart TD
    A["Tạo ApplicationContext và Environment"] --> B["Đăng ký nguồn cấu hình ban đầu"]
    B --> C["ConfigurationClassPostProcessor phân tích cấu hình"]
    C --> D["Đăng ký BeanDefinition"]
    D --> E["BeanFactoryPostProcessor chỉnh metadata"]
    E --> F["Đăng ký và áp dụng BeanPostProcessor"]
    F --> G["Tạo các singleton không lazy"]
    G --> H["Inject dependency và chạy init callbacks"]
    H --> I["SmartInitializingSingleton / ContextRefreshedEvent"]
    I --> J["ApplicationContext sẵn sàng"]
~~~

Sơ đồ là trình tự khái quát. Một số thành phần hạ tầng được tạo sớm để xử lý chính các giai đoạn này; không phải mọi bean đều đi qua một đường tuyến tính giống nhau.

| Khái niệm | Đối tượng được sắp xếp | Cơ chế thường gặp | Kết quả |
| --- | --- | --- | --- |
| Xử lý cấu hình | Configuration class | `@Order`, `@Import`, auto-configuration ordering | Thứ tự phân tích/áp dụng nguồn cấu hình |
| Đăng ký bean definition | Metadata của bean | Configuration processing, component scan, imports, conditions | BeanDefinition xuất hiện trong BeanFactory |
| Tạo bean instance | Object được quản lý | Constructor/method dependency, `@DependsOn`, lazy/eager | Thứ tự khởi tạo theo dependency graph |
| Thứ tự trong collection injection | Các bean cùng kiểu được inject vào List/array | `@Order`, `Ordered`, registration order | Thứ tự phần tử được inject |
| Xử lý bean sau khởi tạo | BeanPostProcessor | `Ordered`, `PriorityOrdered`, thứ tự đăng ký | Thứ tự callback xử lý instance |

Sai lầm thường gặp là dùng một annotation để điều khiển một giai đoạn khác. Ví dụ, thêm `@Order(1)` vào configuration class không buộc mọi bean của class đó khởi tạo trước các bean ở configuration class khác.

## 2. Spring xử lý lớp cấu hình như thế nào?

Spring hỗ trợ nhiều nguồn định nghĩa bean: component scan, XML, Java configuration, imports và auto-configuration. Với Java configuration, `@Configuration` đánh dấu một lớp làm nguồn định nghĩa bean; các method `@Bean` mô tả factory method tạo instance.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new JdbcCatalogRepository();
    }

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }
}
~~~

Khi ApplicationContext xử lý cấu hình này, Spring phân tích class và đăng ký các BeanDefinition tương ứng. Việc đăng ký metadata chưa nhất thiết tạo ngay `CatalogRepository` hay `CatalogService`.

Một bước quan trọng là `ConfigurationClassPostProcessor`. Đây là một `BeanDefinitionRegistryPostProcessor` được Spring dùng để xử lý các cấu hình annotation, bao gồm `@Configuration`, `@Bean`, `@Import`, `@ComponentScan` và các cấu trúc liên quan. Nó chạy trong giai đoạn xử lý registry, trước khi container bắt đầu khởi tạo các bean ứng dụng thông thường.

### 2.1. Đăng ký BeanDefinition không phải tạo object

BeanDefinition chứa metadata như:
- Bean name và bean class hoặc factory method.
- Scope, ví dụ singleton, prototype hoặc scope tùy chỉnh.
- Constructor arguments và property values.
- Các dependency được khai báo.
- Lazy-init, primary, qualifiers và các thuộc tính liên quan.
- Các điều kiện hoặc thông tin nguồn tạo bean.

Có thể hình dung:

~~~text
Configuration class
      |
      | parse @Bean methods
      v
BeanDefinitionRegistry
      |
      +-- catalogRepository : BeanDefinition
      |
      +-- catalogService    : BeanDefinition
      |
      v
BeanFactory creates objects later
~~~

Trong ví dụ, Spring có thể đăng ký định nghĩa của `catalogService` trước hoặc sau định nghĩa của `catalogRepository` tùy quá trình xử lý cấu hình. Khi tạo `catalogService`, Spring vẫn phải giải quyết dependency `CatalogRepository` trước khi hoàn tất bean service.

Vì thế, thứ tự metadata xuất hiện và thứ tự instance được tạo là hai vấn đề riêng.

### 2.2. Nguồn cấu hình có thể đến từ nhiều nơi

Một ApplicationContext có thể nhận cấu hình từ:
- Class được chỉ định trực tiếp khi tạo context.
- `@Import` từ một configuration class khác.
- `@ComponentScan` tìm các component trong package.
- Auto-configuration do Spring Boot nạp.
- BeanDefinition đăng ký bằng API lập trình.
- XML hoặc các nguồn cấu hình khác được tích hợp.

Không nên phụ thuộc vào thứ tự tình cờ của file system, thứ tự quét package hoặc cách một IDE liệt kê class. Nếu có quan hệ cần thiết, hãy khai báo bằng cơ chế thể hiện đúng quan hệ đó.

## 3. Thứ tự xử lý các configuration class

Spring Framework cho phép dùng `@Order` trên configuration class để ảnh hưởng thứ tự đánh giá trong tập cấu hình được xử lý khi khởi động.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration
@Order(10)
public class SharedInfrastructureConfiguration {
    // Các bean hạ tầng dùng chung.
}

@Configuration
@Order(20)
public class ApplicationFeatureConfiguration {
    // Các bean của chức năng ứng dụng.
}
~~~

Hai class trong ví dụ được đặt ở hai file Java riêng. Annotation `@Order` trên class cấu hình chỉ sắp xếp việc đánh giá cấu hình; nó không tạo ra quan hệ dependency giữa các bean.

Giá trị nhỏ hơn có độ ưu tiên cao hơn trong cơ chế sắp xếp. Tuy nhiên, `@Order` ở đây chỉ ảnh hưởng thứ tự xử lý configuration class trong tập cấu hình tương ứng. Nó không điều khiển thứ tự khởi tạo các bean được khai báo bên trong.

### 3.1. @Order trên configuration class không áp dụng cho các @Bean method

Ví dụ:

~~~java
@Configuration
@Order(1)
public class FirstConfiguration {

    @Bean
    AlphaService alphaService() {
        return new AlphaService();
    }

    @Bean
    BetaService betaService() {
        return new BetaService();
    }
}

@Configuration
@Order(2)
public class SecondConfiguration {

    @Bean
    GammaService gammaService() {
        return new GammaService();
    }
}
~~~

`FirstConfiguration` được ưu tiên xử lý trước `SecondConfiguration` trong tập cấu hình có áp dụng order. Nhưng điều đó không tạo ra hợp đồng rằng `AlphaService` và `BetaService` luôn được khởi tạo trước `GammaService`.

Thứ tự tạo object vẫn được quyết định bởi dependency, `@DependsOn`, lazy/eager và quy trình khởi tạo singleton của container.

### 3.2. @Import thể hiện quan hệ cấu hình rõ ràng

Có thể tách cấu hình thành các class nhỏ và kết hợp bằng `@Import`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration
@Import({
        PersistenceConfiguration.class,
        MessagingConfiguration.class,
        CatalogFeatureConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

`@Import` giúp khai báo rõ các nguồn cấu hình cần được đưa vào context. Không nên dùng thứ tự trong mảng import như một cách điều khiển thứ tự khởi tạo bean. Nếu `CatalogFeatureConfiguration` cần một bean persistence, hãy thể hiện dependency trong factory method hoặc qua `@DependsOn` khi dependency chỉ mang tính phụ thuộc khởi tạo gián tiếp.

## 4. Thứ tự auto-configuration trong Spring Boot

Spring Boot tự động đưa các lớp cấu hình phù hợp vào ApplicationContext dựa trên classpath, property, bean hiện có và các điều kiện khác. Auto-configuration không phải một danh sách bean được tạo tuần tự theo tên class.

Một auto-configuration có thể khai báo quan hệ trước/sau với auto-configuration khác để bảo đảm các điều kiện và định nghĩa bean được đánh giá trong thứ tự mong muốn.

Các cơ chế thường gặp:

| Annotation | Ý nghĩa |
| --- | --- |
| `@AutoConfigureBefore` | Yêu cầu auto-configuration hiện tại được áp dụng trước class được chỉ định |
| `@AutoConfigureAfter` | Yêu cầu auto-configuration hiện tại được áp dụng sau class được chỉ định |
| `@AutoConfigureOrder` | Sắp xếp auto-configuration không có quan hệ trực tiếp với nhau |
| `@AutoConfiguration(before=...)` | Khai báo thứ tự trước ngay trên annotation auto-configuration |
| `@AutoConfiguration(after=...)` | Khai báo thứ tự sau ngay trên annotation auto-configuration |

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass(CatalogClient.class)
public class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient() {
        return new CatalogClient();
    }
}
~~~

Ví dụ minh họa một auto-configuration cần được xử lý sau cấu hình DataSource. Việc đặt `after` giúp thứ tự áp dụng các auto-configuration rõ ràng hơn, đặc biệt khi điều kiện phụ thuộc vào BeanDefinition đã được đăng ký.

### 4.1. Auto-configuration ordering chỉ điều khiển định nghĩa bean

Spring Boot xác định rõ: thứ tự áp dụng auto-configuration ảnh hưởng thứ tự các bean definition được đăng ký. Thứ tự các bean instance được tạo sau đó vẫn do dependency và `@DependsOn` quyết định.

Ví dụ, `CatalogClientAutoConfiguration` được áp dụng sau `DataSourceAutoConfiguration` không có nghĩa mọi bean do DataSource auto-configuration tạo ra đều được khởi tạo trước mọi bean catalog.

Nếu `CatalogClient` cần DataSource, hãy khai báo dependency:

~~~java
@Bean
CatalogClient catalogClient(DataSource dataSource) {
    return new CatalogClient(dataSource);
}
~~~

Container sẽ tạo dependency cần thiết trước khi hoàn tất `CatalogClient`.

### 4.2. @AutoConfigureOrder dùng khi hai auto-configuration độc lập

Nếu hai auto-configuration không nên phụ thuộc trực tiếp vào class của nhau, có thể dùng `@AutoConfigureOrder`:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
@AutoConfigureOrder(100)
class CommonMetricsAutoConfiguration {
}

@AutoConfiguration
@AutoConfigureOrder(200)
class OptionalMetricsAutoConfiguration {
}
~~~

Cách này sắp xếp thứ tự áp dụng trong tập auto-configuration. Nó không phải cơ chế điều khiển lifecycle của các bean được khai báo.

Nếu có quan hệ trực tiếp như “cấu hình B cần được áp dụng sau cấu hình A”, ưu tiên `after` hoặc `@AutoConfigureAfter` để thể hiện ý nghĩa dễ đọc hơn một con số order rời rạc.

### 4.3. Cách Spring Boot tìm auto-configuration

Các auto-configuration được công bố theo cơ chế imports của Spring Boot. Với cấu trúc hiện đại, thư viện thường khai báo class trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng chứa tên đầy đủ của một auto-configuration class. Các class này không nên được phát hiện bằng component scan thông thường; Spring Boot nạp chúng qua cơ chế auto-configuration.

Cơ chế imports file này được dùng trong các phiên bản Spring Boot hiện đại từ 2.7. Với dự án Spring Boot cũ hơn, auto-configuration thường được đăng ký qua khóa `EnableAutoConfiguration` trong `META-INF/spring.factories`. Khi nâng cấp thư viện, hãy dùng cơ chế đăng ký phù hợp với dải phiên bản Boot mà thư viện hỗ trợ.

Annotation `@AutoConfiguration` cũng thuộc thế hệ Spring Boot 2.7 trở lên. Với Boot cũ hơn, class auto-configuration thường dùng `@Configuration` kết hợp các annotation ordering/condition có sẵn trong phiên bản đó, rồi đăng ký qua `spring.factories`. Hãy kiểm tra API thực tế của BOM mục tiêu trước khi dùng ví dụ.

Khi viết thư viện Spring Boot:
- Đặt auto-configuration trong package chuyên biệt.
- Đăng ký class qua imports file.
- Dùng `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` khi phù hợp.
- Dùng before/after để sắp xếp định nghĩa với auto-configuration liên quan.
- Không bật component scan rộng từ auto-configuration để tìm các class tùy ý.
- Không dùng auto-configuration ordering như một thay thế cho dependency injection.

## 5. Điều kiện cấu hình và thứ tự đánh giá

Các annotation điều kiện như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và `@ConditionalOnMissingBean` quyết định cấu hình hoặc bean definition có được đăng ký hay không.

Thứ tự áp dụng auto-configuration có thể ảnh hưởng kết quả của điều kiện dựa trên bean hiện có. Ví dụ, một auto-configuration tạo bean mặc định bằng `@ConditionalOnMissingBean` cần được áp dụng sau các cấu hình có cơ hội cung cấp bean tùy chỉnh.

Ví dụ:

~~~java
@AutoConfiguration
public class DefaultCatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient defaultCatalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

Ứng dụng có thể cung cấp bean riêng:

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new CustomCatalogClient();
    }
}
~~~

Khi cấu hình tùy chỉnh được đăng ký và điều kiện nhìn thấy BeanDefinition tương ứng, bean mặc định có thể được bỏ qua. Nếu một auto-configuration phụ thuộc vào một auto-configuration khác, hãy khai báo quan hệ ordering thay vì dựa vào tên class hoặc thứ tự file.

Lưu ý: điều kiện được đánh giá trong giai đoạn xử lý cấu hình/đăng ký definition. Nó không đợi bean instance được tạo rồi mới quyết định. Đây là lý do cần phân biệt metadata đã đăng ký với object runtime.

## 6. Thứ tự khởi tạo bean do dependency graph quyết định

Khi Spring tạo một bean, container phải giải quyết dependency trước khi hoàn tất bean phụ thuộc. Đây là cơ chế chính để bảo đảm thứ tự khởi tạo.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new JdbcCatalogRepository();
    }

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }

    @Bean
    CatalogController catalogController(CatalogService service) {
        return new CatalogController(service);
    }
}
~~~

Dependency graph:

~~~mermaid
flowchart LR
    A["CatalogRepository"] --> B["CatalogService"]
    B --> C["CatalogController"]
~~~

Để tạo `CatalogController`, Spring cần `CatalogService`. Để tạo `CatalogService`, Spring cần `CatalogRepository`. Do đó, repository phải được tạo và cấu hình trước service; service phải sẵn sàng trước controller.

Thứ tự này tồn tại vì quan hệ dependency được khai báo qua tham số factory method. Không cần `@Order` hoặc `@DependsOn` để mô tả lại cùng một dependency.

### 6.1. Constructor injection làm dependency rõ ràng

Ví dụ component:

~~~java
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@Repository
public class CatalogRepository {
}

@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }
}
~~~

Khi tạo `CatalogService`, Spring phải cung cấp `CatalogRepository` trước. Constructor injection làm dependency bắt buộc hiển thị ngay tại điểm tạo object, dễ đọc và dễ kiểm thử.

Với dependency thực sự cần thiết, constructor injection thường tốt hơn việc dựa vào thứ tự khởi tạo ngầm hoặc gọi `getBean()` thủ công.

### 6.2. Không có dependency thì không nên giả định thứ tự

Nếu hai singleton độc lập, không có dependency trực tiếp và không có `@DependsOn`, ứng dụng không nên dựa vào thứ tự tạo tình cờ giữa chúng.

Một phiên bản framework, một component scan khác hoặc một auto-configuration mới có thể làm thứ tự đăng ký definition thay đổi. Nếu logic nghiệp vụ yêu cầu A phải hoàn tất trước B, hãy biểu diễn quan hệ đó bằng dependency hoặc callback lifecycle phù hợp.

## 7. Khi nào cần @DependsOn?

`@DependsOn` dùng khi có một quan hệ phụ thuộc khởi tạo gián tiếp mà constructor/method injection không thể hiện được.

Ví dụ, một bean cần được tạo sau khi schema initializer đã chạy, dù nó không cần giữ reference tới initializer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration(proxyBeanMethods = false)
public class SearchConfiguration {

    @Bean
    SchemaInitializer schemaInitializer() {
        return new SchemaInitializer();
    }

    @Bean
    @DependsOn("schemaInitializer")
    SearchIndex searchIndex() {
        return new SearchIndex();
    }
}
~~~

Spring tạo `schemaInitializer` trước khi tạo `searchIndex`. Không cần inject `SchemaInitializer` vào constructor của `SearchIndex` nếu bean này không cần sử dụng object đó.

### 7.1. @DependsOn cũng ảnh hưởng thứ tự hủy singleton

Với singleton, quan hệ `depends-on` còn ảnh hưởng thứ tự destruction. Bean phụ thuộc được hủy trước bean mà nó phụ thuộc vào.

Nếu `searchIndex` depends on `schemaInitializer`, khi context đóng, Spring hủy `searchIndex` trước rồi mới hủy `schemaInitializer`. Điều này hữu ích khi bean phụ thuộc cần giải phóng tài nguyên trước khi thành phần nền tảng bị đóng.

### 7.2. Không dùng @DependsOn thay constructor injection

Nếu bean B thực sự cần bean A để hoạt động, hãy inject A:

~~~java
@Bean
CatalogService catalogService(CatalogRepository repository) {
    return new CatalogService(repository);
}
~~~

Không nên chỉ viết:

~~~java
@Bean
@DependsOn("catalogRepository")
CatalogService catalogService() {
    return new CatalogService();
}
~~~

trong khi service vẫn cần repository nhưng không có cách truy cập repository rõ ràng. `@DependsOn` chỉ bảo đảm thứ tự khởi tạo, không tự inject dependency và không thay thế dependency graph.

### 7.3. Tránh chuỗi @DependsOn dài

Một cấu hình có nhiều bean phụ thuộc nhau bằng `@DependsOn` có thể khó bảo trì:

~~~java
@Bean
@DependsOn({"databaseReady", "messageBrokerReady", "cacheReady"})
OrderProcessor orderProcessor() {
    return new OrderProcessor();
}
~~~

Nếu OrderProcessor cần các thành phần đó, hãy inject trực tiếp qua constructor. Dùng `@DependsOn` cho side effect hoặc thứ tự khởi tạo gián tiếp, không biến nó thành hệ thống dependency injection thứ hai.

## 8. @Order không điều khiển singleton startup order

`@Order` thường được hiểu nhầm là annotation “khởi tạo trước”. Tài liệu Spring Framework phân biệt rõ:

- `@Order` có thể sắp xếp bean khi inject vào array hoặc collection.
- `@Order` trên configuration class ảnh hưởng thứ tự xử lý configuration class.
- `@Order` không điều khiển thứ tự khởi tạo singleton.
- Thứ tự khởi tạo singleton dựa trên dependency relationships và `@DependsOn`.

Ví dụ sắp xếp collection:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

public interface StartupTask {
    void execute();
}

@Component
@Order(10)
class ValidateConfigurationTask implements StartupTask {
    @Override
    public void execute() {
        // Validate cấu hình.
    }
}

@Component
@Order(20)
class WarmupCacheTask implements StartupTask {
    @Override
    public void execute() {
        // Warm up cache.
    }
}
~~~

Một bean điều phối nhận danh sách:

~~~java
import java.util.List;
import org.springframework.stereotype.Component;

@Component
class StartupTaskRunner {

    private final List<StartupTask> tasks;

    StartupTaskRunner(List<StartupTask> tasks) {
        this.tasks = tasks;
    }

    void runTasks() {
        tasks.forEach(StartupTask::execute);
    }
}
~~~

Danh sách `tasks` được sắp xếp theo order của các bean. Nhưng điều đó không có nghĩa `ValidateConfigurationTask` instance đã được khởi tạo trước mọi bean khác trong ApplicationContext.

Nếu cần chạy các tác vụ tuần tự, hãy gọi chúng theo thứ tự trong một coordinator như ví dụ, hoặc dùng lifecycle hook phù hợp. Không dựa vào thứ tự singleton được tạo để thực thi logic nghiệp vụ.

### 8.1. Giá trị order nhỏ hơn có ưu tiên cao hơn

Với `Ordered` và `@Order`, giá trị số nhỏ hơn có độ ưu tiên cao hơn. Nếu không chỉ định, thứ tự mặc định là `Ordered.LOWEST_PRECEDENCE`.

Ví dụ:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

interface EventHandler {
}

@Order(0)
@Component
class FirstHandler implements EventHandler {
}

@Order(100)
@Component
class LaterHandler implements EventHandler {
}
~~~

Khi các bean được inject vào collection có hỗ trợ order, `FirstHandler` đứng trước `LaterHandler`. Không suy ra chúng đã được khởi tạo theo thứ tự đó.

Nếu các bean không khai báo `@Order` hoặc `Ordered`, thứ tự phần tử thường theo thứ tự đăng ký BeanDefinition tương ứng trong container. Đây vẫn là thứ tự collection injection, không phải hợp đồng về thời điểm khởi tạo singleton.

### 8.2. @Primary cũng không phải ordering

`@Primary` giúp Spring chọn một bean khi có nhiều ứng viên cùng kiểu tại một injection point đơn. Nó không điều khiển thời điểm khởi tạo bean và cũng không sắp xếp collection.

| Annotation | Trách nhiệm |
| --- | --- |
| `@Order` | Sắp xếp ưu tiên tại injection point hỗ trợ ordering |
| `@Primary` | Chọn ứng viên ưu tiên khi cần một bean |
| `@Qualifier` | Thu hẹp tập ứng viên theo qualifier |
| `@DependsOn` | Ép khởi tạo bean được chỉ định trước bean hiện tại |
| Constructor/method injection | Khai báo dependency trực tiếp |

## 9. @Lazy và thời điểm tạo singleton

Mặc định, ApplicationContext thường tạo trước các singleton không lazy trong quá trình refresh context. Điều này giúp phát hiện sớm lỗi cấu hình, dependency hoặc kết nối môi trường.

Có thể trì hoãn bean bằng `@Lazy`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class ReportingConfiguration {

    @Bean
    @Lazy
    ExpensiveReportGenerator reportGenerator() {
        return new ExpensiveReportGenerator();
    }
}
~~~

Bean này được tạo khi lần đầu được yêu cầu, thay vì được pre-instantiate cùng các singleton eager khác.

### 9.1. Lazy bean là dependency của eager singleton

Nếu một bean lazy là dependency của một singleton không lazy, Spring vẫn phải tạo lazy bean để inject dependency cho singleton đó trong startup.

~~~java
@Bean
@Lazy
ReportRepository reportRepository() {
    return new ReportRepository();
}

@Bean
ReportService reportService(ReportRepository repository) {
    return new ReportService(repository);
}
~~~

Trong ví dụ, `reportService` là singleton eager và cần `reportRepository`. Do đó repository được tạo trong lúc context khởi động dù method khai báo `@Lazy`.

### 9.2. @Lazy ở injection point

Có thể đặt `@Lazy` tại injection point để inject proxy trì hoãn việc lấy bean thật cho tới khi sử dụng:

~~~java
@Service
public class AdminService {

    private final HeavyAnalyticsService analyticsService;

    public AdminService(@Lazy HeavyAnalyticsService analyticsService) {
        this.analyticsService = analyticsService;
    }
}
~~~

Cách này hữu ích khi dependency chỉ được sử dụng trong một số đường xử lý. Tuy nhiên, proxy lazy không giải quyết dependency cycle về mặt thiết kế và không nên được dùng để che một đồ thị dependency không lành mạnh.

## 10. Vòng đời bean và thứ tự callback

Sau khi container quyết định tạo bean, một singleton thường đi qua các bước chính:

1. Khởi tạo instance (constructor hoặc factory method).
2. Inject dependency và property.
3. Gọi các callback Aware phù hợp.
4. Chạy BeanPostProcessor trước initialization.
5. Gọi `@PostConstruct`.
6. Gọi `InitializingBean.afterPropertiesSet()` nếu bean triển khai interface.
7. Gọi custom init method nếu khai báo.
8. Chạy BeanPostProcessor sau initialization.
9. Đưa bean đã hoàn tất vào container để sử dụng.

Các callback này thuộc vòng đời của từng bean. `@PostConstruct` trên bean A không có nghĩa mọi singleton khác trong context đã được tạo.

### 10.1. @PostConstruct không phải hook sau tất cả singleton

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class CacheInitializer {

    @PostConstruct
    void initialize() {
        // Khởi tạo trạng thái nội bộ của bean này.
    }
}
~~~

`@PostConstruct` phù hợp để xác thực trạng thái bean hoặc chuẩn bị cấu trúc dữ liệu nội bộ sau khi dependency đã được inject. Không nên dùng nó để giả định mọi bean khác đã khởi tạo xong hoặc để gọi tùy tiện các bean khác qua ApplicationContext.

### 10.2. SmartInitializingSingleton chạy sau singleton thông thường

Nếu cần callback sau khi các singleton eager thông thường đã được tạo, có thể triển khai `SmartInitializingSingleton`:

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class StartupSummary implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Các singleton thông thường đã được pre-instantiate.
        // Có thể tổng hợp trạng thái khởi tạo tại đây.
    }
}
~~~

Callback này phù hợp để tổng hợp hoặc kiểm tra trạng thái sau giai đoạn singleton pre-instantiation. Nó không thay thế `@DependsOn` cho một dependency cần có trước khi tạo bean.

### 10.3. ContextRefreshedEvent là mốc context đã refresh

Có thể lắng nghe sự kiện:

~~~java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationReadyForContextListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        // Context tương ứng đã hoàn thành giai đoạn refresh.
    }
}
~~~

Ứng dụng có thể nhận nhiều ContextRefreshedEvent nếu có context hierarchy hoặc refresh context theo cách đặc biệt. Nếu chỉ quan tâm ứng dụng Boot đã sẵn sàng nhận traffic, hãy xem xét ApplicationReadyEvent và readiness state thay vì coi mọi ContextRefreshedEvent là một lần startup duy nhất.

## 11. BeanFactoryPostProcessor và BeanPostProcessor có thứ tự riêng

Hai extension point này thường xuất hiện khi tùy biến auto-configuration. Chúng hoạt động ở các giai đoạn khác nhau.

| Extension point | Đối tượng tác động | Thời điểm |
| --- | --- | --- |
| BeanDefinitionRegistryPostProcessor | Registry và BeanDefinition | Trước các BeanFactoryPostProcessor thông thường |
| BeanFactoryPostProcessor | BeanDefinition/configuration metadata | Sau khi definition được đăng ký, trước khi tạo bean ứng dụng thông thường |
| BeanPostProcessor | Bean instance | Trong quá trình tạo và khởi tạo từng bean |

### 11.1. BeanFactoryPostProcessor thay đổi metadata

Ví dụ một post-processor có thể đọc hoặc sửa BeanDefinition trước khi container tạo các bean ứng dụng:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.core.Ordered;

public class CatalogDefinitionPostProcessor
        implements BeanFactoryPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {

        if (beanFactory.containsBeanDefinition("catalogClient")) {
            // Đọc hoặc điều chỉnh BeanDefinition nếu thật sự cần.
        }
    }
}
~~~

Spring có thể sắp xếp các post-processor triển khai `PriorityOrdered` và `Ordered`. Đây là thứ tự thực thi extension point, không phải thứ tự khởi tạo các bean nghiệp vụ.

Không nên gọi `beanFactory.getBean(...)` để lấy bean ứng dụng từ trong BeanFactoryPostProcessor. Làm vậy có thể tạo bean quá sớm, trước khi toàn bộ post-processor được đăng ký và áp dụng, dẫn tới bỏ qua một phần xử lý chuẩn.

### 11.2. Đăng ký post-processor qua @Bean nên dùng static

Nếu một method `@Bean` trả về `BeanFactoryPostProcessor`, nên khai báo method là static:

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogPostProcessorConfiguration {

    @Bean
    static CatalogDefinitionPostProcessor catalogDefinitionPostProcessor() {
        return new CatalogDefinitionPostProcessor();
    }
}
~~~

Lý do: container phải tạo BeanFactoryPostProcessor rất sớm để xử lý metadata. Nếu phải khởi tạo configuration class chứa method đó quá sớm, một số annotation injection/lifecycle trên configuration class có thể chưa được xử lý đầy đủ.

Quy tắc tương tự cần được cân nhắc với BeanPostProcessor được khai báo qua `@Bean`; các processor và dependency trực tiếp của chúng thường được khởi tạo sớm. Hãy tránh để chúng phụ thuộc vào bean ứng dụng thông thường.

### 11.3. BeanPostProcessor xử lý instance

Ví dụ:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanPostProcessor;

public class CatalogTracingPostProcessor implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName) throws BeansException {
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean,
            String beanName) throws BeansException {
        return bean;
    }
}
~~~

BeanPostProcessor có thể bọc bean bằng proxy, bổ sung behavior hoặc xử lý annotation. Thứ tự giữa nhiều processor ảnh hưởng cách chúng biến đổi instance, nhưng không có nghĩa bean nghiệp vụ tương ứng được khởi tạo trước hay sau các bean khác.

## 12. @Configuration full mode và lite mode

Một chi tiết liên quan tới định nghĩa bean là cách Spring xử lý lời gọi giữa các method `@Bean`.

Với `@Configuration` mặc định, Spring dùng enhanced configuration class để bảo đảm lời gọi method `@Bean` nội bộ được điều phối qua container. Điều này giúp giữ semantics scope và singleton.

~~~java
@Configuration
public class FullConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new CatalogRepository();
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService(catalogRepository());
    }
}
~~~

Trong full mode, lời gọi `catalogRepository()` được intercept để lấy bean từ container thay vì tạo một object singleton thứ hai.

Nếu dùng:

~~~java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new CatalogRepository();
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService(catalogRepository());
    }
}
~~~

các method `@Bean` chạy theo lite mode. Lời gọi Java trực tiếp `catalogRepository()` không được intercept; nó có thể tạo object mới thay vì lấy singleton từ container.

Trong lite mode, hãy dùng tham số method:

~~~java
@Configuration(proxyBeanMethods = false)
public class RecommendedConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new CatalogRepository();
    }

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }
}
~~~

Tham số factory method thể hiện dependency rõ ràng và hoạt động nhất quán ở cả full/lite configuration.

## 13. Circular dependency không phải công cụ điều khiển thứ tự

Nếu A cần B và B cũng cần A qua constructor, Spring không thể tạo bean nào trước để hoàn tất constructor còn lại. Đây là circular dependency.

~~~mermaid
flowchart LR
    A["Bean A"] --> B["Bean B"]
    B --> A
~~~

Ví dụ không nên:

~~~java
@Component
class OrderService {
    OrderService(PaymentService paymentService) {
    }
}

@Component
class PaymentService {
    PaymentService(OrderService orderService) {
    }
}
~~~

Constructor cycle thường làm quá trình tạo bean thất bại. Một số dạng circular reference qua setter/field có thể được giải quyết trong một số điều kiện singleton, nhưng phụ thuộc cơ chế proxy và cấu hình container; không nên dựa vào đó như một thiết kế bình thường.

Spring Boot hiện đại mặc định không khuyến khích circular references và có thể từ chối chúng. Hãy phá vòng phụ thuộc bằng cách:
- Tách trách nhiệm sang một service thứ ba.
- Đưa phần logic dùng chung vào một abstraction độc lập.
- Dùng event để giảm coupling nếu tương tác không cần đồng bộ.
- Dùng `ObjectProvider` hoặc lazy lookup khi có lý do kiến trúc rõ ràng.
- Đảo chiều dependency qua interface phù hợp.

Không dùng `@DependsOn` để che circular dependency. Nó có thể tạo thêm ràng buộc thứ tự nhưng không giải quyết vòng phụ thuộc logic.

## 14. Ví dụ thực hành: schema phải sẵn sàng trước index

Giả sử ứng dụng tạo một search index cần database schema đã được chuẩn bị. Đây là quan hệ khởi tạo gián tiếp vì `SearchIndex` không cần giữ reference tới `SchemaInitializer`.

Cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration(proxyBeanMethods = false)
public class SearchInfrastructureConfiguration {

    @Bean
    SchemaInitializer schemaInitializer() {
        return new SchemaInitializer();
    }

    @Bean
    @DependsOn("schemaInitializer")
    SearchIndex searchIndex() {
        return new SearchIndex();
    }

    @Bean
    SearchService searchService(SearchIndex searchIndex) {
        return new SearchService(searchIndex);
    }
}
~~~

Dependency/ordering:
- `schemaInitializer` phải được khởi tạo trước `searchIndex` do `@DependsOn`.
- `searchService` cần `searchIndex`, nên dependency injection bảo đảm index có trước service.
- Không cần `@Order` trên configuration class hoặc bean method.

Nếu `SearchService` thực sự cần gọi `SchemaInitializer`, hãy inject dependency đó thay vì chỉ dùng `@DependsOn`.

### 14.1. Test thứ tự khởi tạo

Một test đơn giản có thể ghi nhận thời điểm factory method chạy:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

class BeanStartupOrderTests {

    static final List<String> events = new ArrayList<>();

    static class SchemaInitializer {
    }

    static class SearchIndex {
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {

        @Bean
        SchemaInitializer schemaInitializer() {
            events.add("schema");
            return new SchemaInitializer();
        }

        @Bean
        @DependsOn("schemaInitializer")
        SearchIndex searchIndex() {
            events.add("index");
            return new SearchIndex();
        }
    }

    @Test
    void initializesSchemaBeforeSearchIndex() {
        events.clear();

        try (var context =
                     new AnnotationConfigApplicationContext(TestConfiguration.class)) {

            assertThat(events.indexOf("schema"))
                    .isLessThan(events.indexOf("index"));
        }
    }
}
~~~

Test xác nhận đúng quan hệ đã khai báo. Trong test suite chạy song song, nên tránh dùng một static mutable list chung hoặc thay bằng event recorder riêng cho mỗi context.

### 14.2. Test @Order không quyết định startup

Có thể viết một test khác cho hai bean độc lập để kiểm tra thứ tự collection injection thay vì thứ tự constructor được gọi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

class OrderInjectionTests {

    interface EventHandler {
    }

    static class FirstHandler implements EventHandler {
    }

    static class SecondHandler implements EventHandler {
    }

    @Configuration(proxyBeanMethods = false)
    static class HandlerConfiguration {

        @Bean
        @Order(20)
        EventHandler secondHandler() {
            return new SecondHandler();
        }

        @Bean
        @Order(10)
        EventHandler firstHandler() {
            return new FirstHandler();
        }
    }

    @Test
    void ordersCollectionInjectionWithoutDefiningStartupOrder() {
        try (var context =
                     new AnnotationConfigApplicationContext(HandlerConfiguration.class)) {

            List<EventHandler> handlers = context.getBeanProvider(EventHandler.class)
                    .orderedStream()
                    .collect(Collectors.toList());

            assertThat(handlers)
                    .extracting(Object::getClass)
                    .containsExactly(FirstHandler.class, SecondHandler.class);
        }
    }
}
~~~

Test này kiểm tra thứ tự phần tử trong collection injection. Nó không kiểm tra và cũng không xác lập thứ tự khởi tạo singleton `FirstHandler` và `SecondHandler`.

## 15. Cách chẩn đoán thứ tự trong ứng dụng thật

Khi startup không theo kỳ vọng, nên quan sát từng giai đoạn thay vì thêm annotation ngẫu nhiên.

### 15.1. Kiểm tra cấu hình đã được nạp

Xác minh:
- Configuration class có được import hoặc component scan không?
- Auto-configuration có nằm trong imports file không?
- Điều kiện classpath/property/bean có thỏa mãn không?
- BeanDefinition có được đăng ký không?
- Có cấu hình exclude hoặc override không?

Với Spring Boot, có thể dùng điều kiện report khi chạy ứng dụng ở chế độ debug để xem auto-configuration nào được match hoặc không match. Điều này giúp xác định vấn đề ở giai đoạn áp dụng cấu hình.

### 15.2. Kiểm tra dependency graph

Nếu bean đã được đăng ký nhưng khởi tạo không đúng:
- Xem constructor/factory method parameters.
- Xác minh bean name trong `@DependsOn`.
- Kiểm tra scope và lazy-init.
- Tìm vòng phụ thuộc.
- Kiểm tra BeanFactoryPostProcessor có gọi getBean quá sớm không.
- Kiểm tra BeanPostProcessor có phụ thuộc bean nghiệp vụ không.

### 15.3. Ghi log lifecycle có chủ đích

Có thể log trong constructor, factory method, `@PostConstruct` hoặc lifecycle callback để thấy thời điểm thực tế. Chỉ dùng log như công cụ quan sát; không biến thứ tự log của các bean độc lập thành hợp đồng kiến trúc.

Một bean khởi tạo nhanh có thể xuất hiện trước bean khác trong một lần chạy, nhưng kết quả có thể đổi khi thêm dependency hoặc auto-configuration mới.

## 16. Những nhầm lẫn thường gặp

| Nhận định | Thực tế |
| --- | --- |
| Configuration class có @Order(1) thì mọi bean của nó tạo trước | @Order chỉ ảnh hưởng thứ tự xử lý configuration class |
| Method @Bean khai báo đầu file sẽ chạy trước | Không có hợp đồng khởi tạo dựa trên thứ tự dòng code |
| @Order trên bean điều khiển singleton startup | @Order chủ yếu sắp xếp ưu tiên ở injection point hỗ trợ ordering |
| @Primary khiến bean được tạo trước | @Primary chỉ chọn candidate tại injection point đơn |
| @DependsOn thay thế constructor injection | @DependsOn chỉ ép thứ tự khởi tạo, không truyền dependency |
| AutoConfigureAfter khiến bean của cấu hình trước được tạo trước | Nó sắp xếp việc áp dụng auto-configuration/định nghĩa bean |
| @Lazy luôn trì hoãn bean tới lần dùng đầu tiên | Nếu eager singleton cần bean lazy, bean đó vẫn được tạo lúc startup |
| @PostConstruct chạy sau khi mọi bean đã tạo | Nó chạy trong lifecycle của từng bean |
| ContextRefreshedEvent và ApplicationReadyEvent giống nhau | Chúng là các mốc lifecycle khác nhau |
| Circular dependency có thể giải quyết bằng @DependsOn | @DependsOn không phá được vòng phụ thuộc logic |

## 17. Nguyên tắc tùy biến auto-configuration

Khi xây dựng hoặc mở rộng auto-configuration trong Spring Cloud/Spring Boot:

- Dùng `@AutoConfigureBefore`/`@AutoConfigureAfter` khi cần sắp xếp định nghĩa với auto-configuration khác.
- Dùng `@AutoConfigureOrder` cho các auto-configuration độc lập cần thứ tự tương đối.
- Dùng `@ConditionalOnMissingBean` để cho phép ứng dụng thay thế bean mặc định.
- Dùng constructor hoặc method injection để thể hiện dependency trực tiếp.
- Dùng `@DependsOn` cho phụ thuộc khởi tạo gián tiếp.
- Dùng `@Lazy` để trì hoãn khởi tạo khi có lý do rõ ràng.
- Dùng `@Order` cho thứ tự collection injection hoặc extension point có hỗ trợ ordering.
- Dùng BeanFactoryPostProcessor để chỉnh metadata, BeanPostProcessor để xử lý instance.
- Khai báo static factory method khi đăng ký post-processor qua `@Bean`.
- Tránh circular dependency và gọi getBean quá sớm.
- Kiểm thử điều kiện auto-configuration, dependency graph và lifecycle riêng biệt.

## 18. Checklist khi gặp vấn đề về thứ tự

- [ ] Đã xác định đang nói về thứ tự xử lý configuration, đăng ký BeanDefinition hay tạo instance?
- [ ] Configuration class đã được import/scan/nạp qua cơ chế đúng chưa?
- [ ] Auto-configuration imports file có khai báo class không?
- [ ] Điều kiện `@ConditionalOn...` có match không?
- [ ] Đã dùng before/after cho thứ tự auto-configuration cần thiết chưa?
- [ ] Bean có dependency trực tiếp nên được khai báo qua constructor/method không?
- [ ] Có phụ thuộc side effect cần `@DependsOn` không?
- [ ] Bean lazy có bị eager singleton khác kéo vào startup không?
- [ ] Có nhầm `@Order` với startup ordering không?
- [ ] BeanFactoryPostProcessor/BeanPostProcessor có bị tạo quá sớm hoặc phụ thuộc bean không phù hợp không?
- [ ] Có circular dependency không?
- [ ] Test đang xác nhận đúng loại thứ tự cần thiết không?

## Ghi nhớ

Spring xử lý cấu hình và đăng ký BeanDefinition trước khi tạo phần lớn bean ứng dụng. `@Order` trên configuration class ảnh hưởng thứ tự xử lý cấu hình; thứ tự auto-configuration ảnh hưởng thứ tự định nghĩa bean. **Thứ tự khởi tạo singleton được quyết định bởi dependency graph và `@DependsOn`**, còn `@Order` chủ yếu sắp xếp bean tại injection point hỗ trợ ordering. Hãy dùng dependency injection cho quan hệ trực tiếp, `@DependsOn` cho phụ thuộc khởi tạo gián tiếp, `@Lazy` cho trì hoãn có chủ đích và các lifecycle callback đúng giai đoạn để tránh phụ thuộc vào thứ tự tình cờ.

## Tài liệu tham khảo

- Spring Framework – Using @Autowired and ordering at injection points: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html
- Spring Framework – Composing Java-based Configurations: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework – Using depends-on: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html
- Spring Framework – Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework – Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework – Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot – Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

