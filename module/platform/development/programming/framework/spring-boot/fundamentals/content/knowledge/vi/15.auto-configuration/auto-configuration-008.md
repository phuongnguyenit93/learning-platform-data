# Thứ tự auto-configuration và khác biệt với thứ tự tạo bean

Spring Boot có thể tự động nạp nhiều lớp cấu hình từ các starter và thư viện. Khi một ứng dụng thêm web, database, security hoặc thư viện tích hợp, nhiều auto-configuration cùng tham gia xây dựng application context. Có lúc một cấu hình cần được xử lý trước cấu hình khác để điều kiện như `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` nhìn thấy đúng bean definition.

Spring Boot cung cấp các cơ chế như `@AutoConfiguration(before = ...)`, `@AutoConfiguration(after = ...)` và `@AutoConfigureOrder` để sắp xếp **thứ tự xử lý các lớp auto-configuration**. Cần phân biệt điều này với **thứ tự tạo instance bean**. Auto-configuration được xử lý trước không có nghĩa constructor của mọi bean trong cấu hình đó chắc chắn chạy trước mọi bean ở cấu hình khác.

Thứ tự tạo bean được quyết định chủ yếu bởi quan hệ dependency, scope, lazy initialization và các chỉ thị lifecycle như `@DependsOn`. Còn `@Order` thường điều khiển thứ tự các bean trong collection hoặc một số cơ chế xử lý có hỗ trợ ordering; nó không phải công cụ tổng quát để điều khiển thời điểm singleton được khởi tạo.

## 1. Auto-configuration là gì trong quá trình khởi động?

Ứng dụng Spring Boot thường có lớp main:

~~~java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Khi khởi động, Spring Boot tìm các auto-configuration đã được thư viện công bố, đánh giá các điều kiện và nhập những cấu hình phù hợp vào application context.

Trong Spring Boot 3.x, thư viện auto-configuration thường công bố class qua file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ file trong một JAR:

~~~text
com.example.cache.CacheAutoConfiguration
com.example.metrics.MetricsAutoConfiguration
com.example.audit.AuditAutoConfiguration
~~~

Các lớp này được đưa vào quá trình xử lý configuration. Chúng có thể khai báo bean mặc định, cấu hình tích hợp và điều kiện để chỉ kích hoạt khi classpath, property hoặc bean phù hợp.

Quá trình khái quát:

~~~text
SpringApplication.run(...)
        |
        v
Đọc Environment và chuẩn bị BeanFactory
        |
        v
Phân tích cấu hình ứng dụng
        |
        v
Tìm các auto-configuration candidates
        |
        v
Lọc candidates theo exclusions và conditions
        |
        v
Sắp xếp thứ tự xử lý auto-configuration
        |
        v
Đăng ký các bean definitions
        |
        v
Khởi tạo singleton theo dependency/lifecycle
        |
        v
Context refresh hoàn tất
~~~

Đây là các giai đoạn ở mức khái niệm; bên trong Spring có nhiều bước xử lý configuration class, bean definition và post-processor. Điều cần nhớ là **auto-configuration là quá trình chọn và đăng ký cấu hình/bean definition**, còn việc tạo instance là giai đoạn quản lý bean tiếp theo.

## 2. Vì sao auto-configuration cần thứ tự?

Giả sử một thư viện cung cấp cấu hình database mặc định, còn thư viện khác cung cấp một bean dùng `DataSource` nếu có:

~~~text
DataSourceAutoConfiguration
        |
        | đăng ký bean definition DataSource
        v
DatabaseMetricsAutoConfiguration
        |
        | @ConditionalOnBean(DataSource.class)
        v
DatabaseMetrics bean definition
~~~

Nếu cấu hình metrics được xử lý trước khi cấu hình DataSource đăng ký bean definition, điều kiện `@ConditionalOnBean(DataSource.class)` có thể chưa nhìn thấy bean mà nó cần. Cấu hình metrics có thể bị bỏ qua dù ứng dụng cuối cùng sẽ có DataSource.

Vì vậy, auto-configuration ordering có thể được dùng để đảm bảo **cấu hình cung cấp bean nền tảng được xử lý trước cấu hình phụ thuộc vào bean đó**.

Điều này đặc biệt quan trọng với các điều kiện:

- `@ConditionalOnBean`: chỉ kích hoạt khi bean phù hợp đã có trong registry ở thời điểm condition được đánh giá.
- `@ConditionalOnMissingBean`: chỉ cung cấp bean mặc định nếu chưa có bean phù hợp.
- Các điều kiện/selector phụ thuộc vào những cấu hình đã được xử lý trước đó.

Thứ tự auto-configuration giúp các điều kiện nhìn thấy bean definition đúng thời điểm. Nó không phải cơ chế yêu cầu tạo object hoặc chạy method theo thứ tự nghiệp vụ.

## 3. @AutoConfiguration(before = ...) và after = ...

Với Spring Boot 3.x, lớp auto-configuration thường dùng `@AutoConfiguration`:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class DatabaseMetricsAutoConfiguration {
    // Cấu hình cần được xử lý sau DataSourceAutoConfiguration.
}
~~~

Thuộc tính `after` thể hiện cấu hình này nên được xử lý sau lớp được chỉ định. Tương tự, `before` thể hiện cấu hình này nên được xử lý trước lớp được chỉ định.

Ví dụ:

~~~java
@AutoConfiguration(before = MetricsAutoConfiguration.class)
public class EarlyMetricsDefaultsAutoConfiguration {
}
~~~

Hai thuộc tính có ý nghĩa tương đối:

| Thuộc tính | Ý nghĩa |
|---|---|
| `before` | Đặt auto-configuration hiện tại trước class được chỉ định |
| `beforeName` | Giống `before` nhưng tham chiếu bằng tên class dạng chuỗi |
| `after` | Đặt auto-configuration hiện tại sau class được chỉ định |
| `afterName` | Giống `after` nhưng tham chiếu bằng tên class dạng chuỗi |

Dùng class literal khi dependency có mặt trực tiếp và không gây vấn đề class loading. Dùng tên class dạng chuỗi khi muốn tránh phụ thuộc compile-time vào một class tùy chọn hoặc thư viện có thể không hiện diện.

### 3.1. Ví dụ cấu hình phụ thuộc DataSource

Giả sử thư viện metrics cần cung cấp bean khi ứng dụng có `DataSource`:

~~~java
package com.example.metrics.autoconfigure;

import javax.sql.DataSource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class DatabaseMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    DatabaseMetrics databaseMetrics(DataSource dataSource) {
        return new DatabaseMetrics(dataSource);
    }
}
~~~

`DataSource` thuộc Java SE/JDBC package `javax.sql` và vẫn dùng namespace này trên JDK hiện đại; không đổi thành `jakarta.sql`.

Ý nghĩa:

1. `DataSourceAutoConfiguration` được xử lý trước.
2. Bean definition DataSource có cơ hội được đăng ký.
3. Condition `@ConditionalOnBean(DataSource.class)` được đánh giá ở cấu hình metrics.
4. Nếu có bean phù hợp, phương thức `databaseMetrics` được đăng ký.
5. Khi bean metrics được tạo, Spring inject DataSource qua tham số phương thức.

Ví dụ giả định các class `DatabaseMetrics` và các dependency cần thiết được cung cấp. Thứ tự `after` không tự tạo DataSource; nếu cấu hình datasource bị exclude hoặc điều kiện của nó không thỏa, metrics vẫn không có bean để dùng.

### 3.2. before và after chỉ tạo quan hệ tương đối

Nếu A khai báo `before = B`, điều đó chỉ nói A nên được xử lý trước B. Nó không xác định vị trí tuyệt đối của A so với mọi auto-configuration khác.

~~~text
A  --->  B
     (A trước B)

C không được ràng buộc với A/B:
    C có thể đứng ở vị trí khác tùy các quan hệ ordering còn lại.
~~~

Khi nhiều cấu hình có các quan hệ trước/sau, Spring Boot xây dựng thứ tự phù hợp từ những ràng buộc đã khai báo. Không nên tạo quá nhiều quan hệ chéo hoặc chu trình ordering; thiết kế tốt thường chỉ cần mô tả dependency trực tiếp có ý nghĩa.

## 4. @AutoConfigureOrder dùng khi nào?

`@AutoConfigureOrder` cung cấp một giá trị thứ tự tổng quát cho auto-configuration:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
import org.springframework.core.Ordered;

@AutoConfigureOrder(Ordered.HIGHEST_PRECEDENCE)
@AutoConfiguration
public class CoreDefaultsAutoConfiguration {
}
~~~

Giá trị order thấp hơn có mức ưu tiên đứng trước giá trị cao hơn theo quy ước ordering của Spring. `Ordered.HIGHEST_PRECEDENCE` biểu thị ưu tiên rất cao; `Ordered.LOWEST_PRECEDENCE` biểu thị ưu tiên thấp nhất.

`@AutoConfigureOrder` hữu ích khi cần một gợi ý thứ tự tổng quát giữa các auto-configuration không có quan hệ class cụ thể. Tuy nhiên, nếu mục tiêu là “cấu hình X cần chạy sau cấu hình Y”, quan hệ `after`/`before` thường dễ đọc và diễn đạt chính xác hơn.

Trong code Spring Boot 3.x, `@AutoConfiguration(before = ..., after = ...)` thường là cách trực tiếp để khai báo các quan hệ ordering cụ thể. `@AutoConfigureOrder` vẫn là một công cụ ordering, nhưng không nên dùng nó như một con số tùy tiện để ép thứ tự khởi tạo bean.

### Không nhầm với @Order

`@AutoConfigureOrder` và `@Order` có tên gần nhau nhưng phạm vi ý nghĩa khác:

| Annotation | Đối tượng sắp xếp | Mục tiêu |
|---|---|---|
| `@AutoConfigureOrder` | Auto-configuration classes | Thứ tự xử lý các auto-configuration |
| `@Order` | Bean/đối tượng trong các cơ chế hỗ trợ ordering | Thứ tự ưu tiên khi inject collection hoặc xử lý danh sách |

Đặt `@Order(1)` trên service không có nghĩa service đó sẽ được tạo trước mọi service có `@Order(2)`.

## 5. Auto-configuration ordering ảnh hưởng đến đăng ký bean definition

Một auto-configuration class thường chứa các phương thức `@Bean`:

~~~java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SearchClient searchClient() {
        return new SearchClient();
    }
}
~~~

Khi configuration class được xử lý, Spring đọc các phương thức cấu hình và đăng ký bean definitions vào BeanFactory. Ở giai đoạn này, container biết rằng bean có tên/kiểu nào có thể được tạo, nhưng instance của bean chưa nhất thiết đã được khởi tạo.

Điều này cho phép một cấu hình sau đó dùng điều kiện như `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` để xem xét các bean definitions đã được đăng ký.

Ví dụ:

~~~java
@AutoConfiguration
public class SearchMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(SearchClient.class)
    SearchMetrics searchMetrics(SearchClient client) {
        return new SearchMetrics(client);
    }
}
~~~

Nếu `SearchAutoConfiguration` được sắp xếp trước `SearchMetricsAutoConfiguration`, điều kiện có thể nhìn thấy definition của `SearchClient`. Nhưng **việc đăng ký definition SearchClient không đồng nghĩa constructor SearchClient đã chạy ngay lúc đó**.

Đây là khác biệt nền tảng:

- **Đăng ký bean definition:** container ghi nhận cách tạo bean, tên, scope, điều kiện và metadata.
- **Tạo bean instance:** container thực thi constructor/factory method, inject dependency và callbacks.

Auto-configuration order chủ yếu điều phối bước đầu tiên.

## 6. Thứ tự tạo bean được quyết định như thế nào?

Sau khi các bean definitions đã được đăng ký, Spring tạo instance theo nhu cầu và lifecycle.

Những yếu tố quan trọng:

1. **Dependency graph:** nếu bean B cần bean A qua constructor hoặc property injection, A phải được phân giải trước khi B hoàn tất khởi tạo.
2. **Scope:** singleton, prototype, request và các scope khác có thời điểm tạo khác nhau.
3. **Lazy initialization:** bean lazy có thể chưa được tạo cho đến khi được yêu cầu.
4. **@DependsOn:** khai báo phụ thuộc khởi tạo theo tên bean khi không có dependency injection trực tiếp.
5. **Các callback/lifecycle contract:** Spring gọi initialization và destruction callbacks theo quy trình của bean.

Ví dụ dependency thông thường:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new OrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

Khi Spring tạo `OrderService`, nó cần `OrderRepository` để truyền vào factory method. Vì vậy repository được phân giải và khởi tạo trước service. Không cần dùng `@DependsOn` hay ordering annotation cho quan hệ đã được thể hiện bằng dependency injection.

~~~text
Yêu cầu tạo OrderService
          |
          v
 Cần OrderRepository
          |
          v
 Tạo OrderRepository
          |
          v
 Truyền repository vào factory method
          |
          v
 Tạo OrderService
~~~

Quan hệ này thể hiện dependency thực sự, nên Spring có thể quản lý đúng thứ tự và phát hiện nhiều trường hợp circular dependency.

## 7. @DependsOn dùng khi cần thứ tự khởi tạo tường minh

Đôi khi một bean phụ thuộc vào **side effect khởi tạo** của bean khác nhưng không cần inject instance đó. Ví dụ một bean khởi tạo thư mục dữ liệu hoặc đăng ký một tài nguyên dùng chung trước khi bean khác bắt đầu:

~~~java
@Configuration(proxyBeanMethods = false)
class StartupConfiguration {

    @Bean
    DataDirectoryInitializer dataDirectoryInitializer() {
        return new DataDirectoryInitializer();
    }

    @Bean
    @DependsOn("dataDirectoryInitializer")
    FileCatalog fileCatalog() {
        return new FileCatalog();
    }
}
~~~

`@DependsOn("dataDirectoryInitializer")` yêu cầu bean `dataDirectoryInitializer` được khởi tạo trước bean `fileCatalog`. Khi các singleton này được hủy theo lifecycle của container, bean được phụ thuộc sẽ được hủy theo thứ tự ngược lại, để bean phụ thuộc được hủy trước bean mà nó cần.

`@DependsOn` có thể đặt trên class component hoặc phương thức `@Bean`. Nó nhận tên bean, nên cần bảo đảm tên được chỉ định đúng.

### Khi nào không nên dùng @DependsOn?

Nếu bean B đã inject bean A:

~~~java
@Bean
FileCatalog fileCatalog(DataDirectoryInitializer initializer) {
    return new FileCatalog(initializer);
}
~~~

thì dependency injection đã biểu diễn quan hệ phụ thuộc. Thêm `@DependsOn` thường là dư thừa.

Không dùng `@DependsOn` để sắp xếp tất cả service theo thứ tự tùy ý hoặc để che giấu một dependency chưa được thiết kế rõ. Nếu B thực sự cần A, hãy inject A. Nếu chỉ cần side effect khởi tạo, hãy xem xét liệu side effect đó có nên được mô hình hóa thành một dependency/lifecycle contract rõ ràng hay không.

## 8. @Order không điều khiển thứ tự tạo singleton

`@Order` thường được dùng khi Spring cần sắp xếp một tập đối tượng. Ví dụ, nhiều handler cùng triển khai một interface:

~~~java
public interface RequestHandler {
    void handle(Request request);
}
~~~

~~~java
@Component
@Order(10)
class AuthenticationHandler implements RequestHandler {
    public void handle(Request request) {
        // Xác thực.
    }
}
~~~

~~~java
@Component
@Order(20)
class AuthorizationHandler implements RequestHandler {
    public void handle(Request request) {
        // Phân quyền.
    }
}
~~~

Một bean sử dụng collection:

~~~java
@Component
class RequestPipeline {
    private final List<RequestHandler> handlers;

    RequestPipeline(List<RequestHandler> handlers) {
        this.handlers = handlers;
    }

    void process(Request request) {
        handlers.forEach(handler -> handler.handle(request));
    }
}
~~~

Spring sắp xếp các phần tử trong collection theo order phù hợp. `AuthenticationHandler` có order 10 đứng trước `AuthorizationHandler` có order 20 trong danh sách. Nhưng điều đó **không chứng minh constructor của AuthenticationHandler đã chạy trước constructor AuthorizationHandler**.

`@Order` có thể ảnh hưởng đến:

- Thứ tự phần tử trong injected arrays/lists.
- Thứ tự các bean trong `ObjectProvider.orderedStream()`.
- Những extension point của Spring có quy định sử dụng `Ordered` hoặc `@Order`.
- Một số chuỗi xử lý đặc thù như interceptor, resolver hoặc post-processor khi API đó hỗ trợ ordering.

Nó không phải quy tắc chung cho việc khởi tạo singleton. Nếu cần bean A được tạo trước bean B, hãy biểu diễn dependency hoặc dùng `@DependsOn` khi phù hợp.

## 9. @AutoConfiguration, @Order và @DependsOn: so sánh nhanh

| Cơ chế | Sắp xếp cái gì? | Có điều khiển thời điểm tạo instance bean? |
|---|---|---|
| `@AutoConfiguration(before/after)` | Thứ tự xử lý auto-configuration classes | Không |
| `@AutoConfigureOrder` | Ưu tiên xử lý auto-configuration classes | Không |
| `@Order` / `Ordered` | Thứ tự trong collection hoặc extension point hỗ trợ ordering | Không phải cơ chế tổng quát |
| Constructor/bean method dependency | Quan hệ phụ thuộc giữa bean | Có: dependency được phân giải trước bean cần nó |
| `@DependsOn` | Thứ tự khởi tạo theo tên bean | Có: bean được chỉ định phải khởi tạo trước bean phụ thuộc |
| `@Lazy` | Thời điểm bean được yêu cầu/khởi tạo | Có ảnh hưởng đến thời điểm, không phải thứ tự ưu tiên |

Một ví dụ dễ nhớ:

~~~text
AutoConfiguration A before B
    -> đăng ký cấu hình/bean definitions theo thứ tự A rồi B

Bean X cần Bean Y qua constructor
    -> tạo/phân giải Y trước khi hoàn tất X

Bean M @Order(1), Bean N @Order(2)
    -> M đứng trước N trong collection có ordering
    -> không kết luận M được khởi tạo trước N
~~~

## 10. Vì sao không nên dùng auto-configuration order để sửa lỗi thứ tự khởi tạo?

Giả sử một bean cần database đã được mở kết nối:

~~~java
@Bean
DatabaseReportService databaseReportService() {
    return new DatabaseReportService();
}
~~~

Nếu constructor của `DatabaseReportService` tự truy cập một bean khác bằng cách tra cứu toàn cục, dựa vào một side effect hoặc tự mở connection, chỉ thêm:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
~~~

không phải cách diễn đạt dependency tốt. Nó chỉ sắp xếp lớp cấu hình, không đảm bảo instance hoặc side effect của tất cả bean liên quan đã hoàn tất theo ý muốn.

Hãy inject dependency:

~~~java
@Bean
DatabaseReportService databaseReportService(DataSource dataSource) {
    return new DatabaseReportService(dataSource);
}
~~~

Nếu cần khởi tạo schema hoặc dữ liệu nền trước khi service sử dụng, biểu diễn dependency vào một initializer hoặc dùng cơ chế database initialization của Spring Boot. Đừng dựa vào thứ tự import như một cách thay thế cho lifecycle.

## 11. Thứ tự của auto-configuration không phải thứ tự tuyệt đối của toàn ứng dụng

Auto-configuration ordering có phạm vi là các cấu hình được đưa vào quy trình auto-configuration. Nó không phải cơ chế sắp xếp tất cả class `@Configuration` trong dự án, cũng không phải thứ tự toàn cục giữa mọi bean do component scan, `@Import` hoặc người dùng đăng ký.

Một số giới hạn:

- Quan hệ `before`/`after` chỉ ràng buộc các auto-configuration class liên quan.
- Cấu hình có thể bị loại bởi `exclude` hoặc condition không thỏa.
- Một auto-configuration có thể đăng ký nhiều bean, nhưng từng bean có dependency graph riêng.
- Bean lazy có thể chưa được tạo trong giai đoạn startup.
- Prototype được tạo khi container được yêu cầu, không theo lịch khởi tạo singleton.
- Một bean có thể được tạo sớm vì một condition tham chiếu trực tiếp tới bean instance; đó là vấn đề khác với auto-configuration order.

Vì vậy, nếu muốn kiểm soát thời điểm bean được tạo, hãy bắt đầu từ scope và dependency graph, không bắt đầu bằng cách tăng/giảm một giá trị order của auto-configuration.

## 12. Ví dụ thư viện tự cung cấp auto-configuration có ordering

Giả sử thư viện cung cấp cache mặc định và cấu hình cache cần chạy sau cấu hình cache manager nền tảng:

~~~java
package com.example.cache.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.cache.CacheAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CacheAutoConfiguration.class)
public class CustomCacheDefaultsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheKeyGenerator.class)
    CacheKeyGenerator cacheKeyGenerator() {
        return new DefaultCacheKeyGenerator();
    }
}
~~~

Thư viện đăng ký class trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

~~~text
com.example.cache.autoconfigure.CustomCacheDefaultsAutoConfiguration
~~~

`after = CacheAutoConfiguration.class` cho biết cấu hình mặc định này nên được xử lý sau cấu hình cache của Boot. `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp `CacheKeyGenerator` riêng; nếu đã có bean phù hợp, bean mặc định không được đăng ký.

Trong thư viện thật, nên kiểm tra API cache và auto-configuration của phiên bản Boot đang dùng; ví dụ trên minh họa cách diễn đạt quan hệ ordering và back-off, không phải yêu cầu mọi ứng dụng phải import cache auto-configuration thủ công.

### 12.1. Vì sao auto-configuration của thư viện nên dùng @AutoConfiguration?

`@AutoConfiguration` được thiết kế cho các lớp cấu hình tự động của Boot, đồng thời đặt `proxyBeanMethods = false`. Thư viện thường công bố chúng qua file `AutoConfiguration.imports` để Boot có thể khám phá, sắp xếp và áp dụng điều kiện.

Không nên đặt các lớp auto-configuration của thư viện vào component scan rộng của ứng dụng như component thông thường. Làm như vậy có thể khiến chúng được xử lý ngoài cơ chế khám phá/ordering auto-configuration mà thư viện mong đợi.

## 13. Chẩn đoán khi condition không nhìn thấy bean

Một tình huống thường gặp:

~~~java
@AutoConfiguration
class PartnerMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(PartnerClient.class)
    PartnerMetrics partnerMetrics(PartnerClient client) {
        return new PartnerMetrics(client);
    }
}
~~~

Bean `PartnerClient` tồn tại trong một cấu hình khác, nhưng `PartnerMetrics` không được đăng ký. Có thể điều tra:

1. Cấu hình cung cấp `PartnerClient` có được nạp không?
2. Auto-configuration đó có bị exclude hoặc condition không thỏa không?
3. Bean definition `PartnerClient` đã được đăng ký trước khi condition metrics được đánh giá chưa?
4. Hai auto-configuration có quan hệ ordering đúng chưa?
5. `PartnerClient` có đúng kiểu hoặc qualifier mà condition đang tìm không?
6. Có nhầm giữa bean definition và bean instance không?

Nếu hai class đều là auto-configuration, khai báo `after`/`before` có thể giải quyết vấn đề thứ tự xử lý. Nếu bean do ứng dụng cung cấp qua component scan, hãy xem thời điểm component scan/configuration processing và liệu điều kiện có được đặt ở đúng nơi. Không nên thêm ordering annotation tùy tiện trước khi xác định nguồn bean definition.

### Condition Evaluation Report

Có thể bật:

~~~properties
debug=true
~~~

hoặc chạy với `--debug` để xem báo cáo điều kiện của Spring Boot. Báo cáo thường cho biết auto-configuration nào match, không match hoặc bị exclude, cùng lý do liên quan đến classpath, property hay bean.

Báo cáo điều kiện giúp xác nhận cấu hình có được chọn không. Nó không phải log thứ tự constructor của mọi bean và không thay thế việc quan sát lifecycle nếu đang điều tra thứ tự tạo instance.

### Theo dõi bean creation

Có thể tăng mức log cho container trong môi trường phát triển:

~~~properties
logging.level.org.springframework.beans.factory.support=DEBUG
~~~

Mức log cụ thể và thông điệp thay đổi theo phiên bản Spring. Dùng log để xem bean nào được tạo và dependency nào được phân giải; không bật log quá chi tiết ở production nếu chưa đánh giá lượng log và thông tin nội bộ được ghi ra.

## 14. Những quan niệm dễ nhầm

| Quan niệm | Cách hiểu chính xác |
|---|---|
| “Auto-configuration A chạy trước B nên mọi bean của A được tạo trước bean của B.” | A được xử lý/đăng ký trước B; instance creation có lifecycle và dependency riêng. |
| “@Order(1) khiến singleton được tạo đầu tiên.” | `@Order` chủ yếu sắp xếp collection/extension point hỗ trợ ordering. |
| “@DependsOn và @AutoConfigureAfter giống nhau.” | `@DependsOn` điều khiển thứ tự khởi tạo bean; `after` điều khiển thứ tự xử lý auto-configuration. |
| “Đổi thứ tự @Import sẽ đảm bảo constructor chạy theo thứ tự đó.” | Thứ tự import không thay thế dependency graph hoặc lifecycle contract. |
| “@ConditionalOnBean luôn thấy mọi bean trong ứng dụng.” | Điều kiện chỉ đánh giá theo registry/metadata tại thời điểm nó được xử lý; ordering có thể quan trọng. |
| “@AutoConfigureOrder điều khiển thứ tự của tất cả @Configuration.” | Nó dành cho ordering auto-configuration, không phải thứ tự toàn bộ cấu hình ứng dụng. |
| “Bean definition được đăng ký nghĩa là instance đã tồn tại.” | Definition mô tả cách tạo bean; instance có thể chỉ được tạo sau đó hoặc khi được yêu cầu. |

## 15. Cách chọn đúng cơ chế

Khi gặp yêu cầu “A phải chạy trước B”, trước tiên hãy xác định “chạy” đang nói đến giai đoạn nào:

| Yêu cầu thực tế | Cơ chế nên xem xét |
|---|---|
| Auto-configuration A cần được xử lý trước B để condition nhìn thấy bean definitions | `@AutoConfiguration(before/after)` hoặc `@AutoConfigureOrder` |
| Bean B cần bean A để hoạt động | Constructor injection hoặc tham số `@Bean` |
| Bean B cần side effect khởi tạo của A trước khi được tạo | `@DependsOn` nếu dependency không thể thể hiện bằng injection |
| Cần thứ tự xử lý danh sách handler/plugin | `@Order`, `Ordered` và collection injection |
| Cần bean chỉ tạo khi được sử dụng | `@Lazy` hoặc lookup theo nhu cầu |
| Cần công việc chạy sau khi tất cả singleton đã được khởi tạo | `SmartInitializingSingleton` hoặc lifecycle/event phù hợp |
| Cần chạy tác vụ khi ứng dụng Boot đã sẵn sàng | `ApplicationRunner`, `CommandLineRunner` hoặc `ApplicationReadyEvent` |

Ví dụ, nếu một startup task cần dùng nhiều singleton đã được tạo, `SmartInitializingSingleton` có thể phù hợp:

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
class StartupVerifier implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Kiểm tra các singleton đã được tạo.
    }
}
~~~

Nếu công việc cần chờ ứng dụng Boot sẵn sàng nhận request, `ApplicationReadyEvent` hoặc runner có thể phù hợp hơn. Những lifecycle hook này giải quyết mốc thời gian ở cấp ứng dụng; không nên thay chúng bằng `@AutoConfigureAfter`.

## 16. Nguyên tắc thiết kế

1. Dùng `@AutoConfiguration(before/after)` để mô tả quan hệ giữa các auto-configuration, đặc biệt khi condition phụ thuộc bean definition của cấu hình khác.
2. Dùng `@AutoConfigureOrder` cho gợi ý ordering tổng quát khi không có một class cụ thể để tham chiếu; tránh lạm dụng các giá trị số.
3. Dùng constructor injection hoặc tham số phương thức `@Bean` để thể hiện dependency thực sự và để Spring tự tạo bean theo dependency graph.
4. Dùng `@DependsOn` khi cần thứ tự khởi tạo theo tên cho một quan hệ side effect không thể biểu diễn bằng injection.
5. Dùng `@Order` cho danh sách/extension point có hỗ trợ ordering, không dùng nó để điều khiển singleton startup.
6. Phân biệt bean definition với bean instance: condition thường làm việc với cấu hình/metadata đã đăng ký; constructor và initialization callback chạy khi instance được tạo.
7. Kiểm tra condition report và log bean creation khi có vấn đề; đừng thay đổi order trước khi biết cấu hình nào đang được đánh giá và bean nào chưa được đăng ký.

Thứ tự auto-configuration trả lời câu hỏi **cấu hình tự động nào được xử lý trước để đăng ký bean definitions và đánh giá conditions**. Thứ tự tạo bean trả lời câu hỏi **instance nào phải được tạo trước để dependency và lifecycle của instance khác được đáp ứng**. Dùng đúng cơ chế cho từng câu hỏi giúp Spring Boot cấu hình các module theo đúng điều kiện mà vẫn giữ vòng đời bean rõ ràng, dễ dự đoán.
