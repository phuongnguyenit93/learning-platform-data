# Phân biệt thứ tự auto-configuration với `@Order`, `Ordered` và `@DependsOn` trong Spring Boot

## 1. Vì sao có nhiều khái niệm “thứ tự”?

Trong Spring Boot, câu “A phải chạy trước B” chưa đủ rõ. A và B là **hai lớp auto-configuration**, **hai bean được đưa vào một danh sách**, hay **hai bean đang được khởi tạo**? Mỗi câu hỏi dùng một cơ chế khác nhau:

1. **Thứ tự xử lý auto-configuration**: Spring Boot cần biết cấu hình nào được **áp dụng, đăng ký bean definition và đánh giá điều kiện** trước cấu hình nào. Dùng `@AutoConfiguration(before = ..., after = ...)`, `beforeName`/`afterName`, `@AutoConfigureBefore`/`@AutoConfigureAfter`; trong một số trường hợp dùng `@AutoConfigureOrder`.
2. **Thứ tự ưu tiên trong một danh sách hoặc điểm mở rộng**: Spring cần biết bean/callback nào nên đứng trước khi nó **sắp xếp các ứng viên**. Dùng `@Order` hoặc interface `Ordered`, tùy API tiếp nhận bean.
3. **Thứ tự khởi tạo/hủy bean có quan hệ phụ thuộc**: Spring cần bảo đảm bean A tồn tại và khởi tạo xong trước khi tạo bean B. Dùng dependency injection (ưu tiên khi B thực sự cần A) hoặc `@DependsOn("beanName")` cho phụ thuộc khởi tạo có chủ ý.

Ba thứ tự này **không tương đương** và không thể thay thế nhau bằng cách tăng/giảm một số `order`.

### Bảng quyết định

| Cần kiểm soát | Công cụ phù hợp | Ảnh hưởng trực tiếp | Không bảo đảm |
| --- | --- | --- | --- |
| Auto-configuration A được áp dụng trước/sau B | `@AutoConfiguration(before/after)`; `@AutoConfigureBefore`/`@AutoConfigureAfter` | Thứ tự xử lý cấu hình, đăng ký **bean definitions** và đánh giá điều kiện liên quan | Thứ tự tạo **instance** bean hay chạy nghiệp vụ |
| Ưu tiên tương đối giữa các auto-config không có quan hệ cụ thể | `@AutoConfigureOrder` | Thứ tự áp dụng auto-configuration | Lifecycle của bean |
| `List<Handler>` được sắp theo thứ tự ưu tiên | `@Order` trên class/`@Bean`, hoặc `Ordered#getOrder()` | Vị trí ứng viên trong collection/điểm mở rộng có hỗ trợ ordering | Thứ tự khởi tạo singleton |
| `ApplicationRunner`/`CommandLineRunner` chạy theo thứ tự | `@Order` hoặc `Ordered` trên runner | Thứ tự **gọi callback runner** khi Boot thực thi runners | Bean được khởi tạo theo đúng thứ tự đó |
| Bean B chỉ khởi tạo sau bean A | Constructor/`@Bean` parameter dependency, hoặc `@DependsOn("a")` | Quan hệ khởi tạo A trước B; với singleton, còn ảnh hưởng thứ tự hủy | Thứ tự xử lý auto-configuration hay vị trí bean trong `List` |

**Câu hỏi then chốt:** đang nói đến **đăng ký bean definition**, **sắp xếp đối tượng**, hay **khởi tạo bean instance**?

## 2. Thứ tự auto-configuration: ưu tiên lúc *định nghĩa* bean

### 2.1. `@AutoConfiguration(after = ...)` và `before = ...`

Giả sử thư viện có hai auto-configuration:

- `CoreAutoConfiguration` đăng ký bean `CorePort`.
- `FeatureAutoConfiguration` chỉ đăng ký `OptionalAdapter` khi đã có bean `CorePort`.

```java
@AutoConfiguration
public class CoreAutoConfiguration {

    @Bean
    public CorePort corePort() {
        return new CorePort("core");
    }
}
```

```java
@AutoConfiguration(after = CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(CorePort.class)
    public OptionalAdapter optionalAdapter(CorePort corePort) {
        return new OptionalAdapter("connected:" + corePort.id());
    }
}
```

Hai đoạn trên minh họa cấu trúc, giả định `CorePort` và `OptionalAdapter` đã được định nghĩa. Annotation `after` nói rằng **khi các auto-configuration candidate được Spring Boot xử lý**, `CoreAutoConfiguration` cần được áp dụng trước `FeatureAutoConfiguration`. Nhờ vậy, khi `@ConditionalOnBean(CorePort.class)` được đánh giá, bean definition của `CorePort` đã có cơ hội được đăng ký.

Cần hiểu ba điểm:

- `after` là **quan hệ thứ tự áp dụng cấu hình**, không có nghĩa `corePort()` luôn được **gọi tạo instance** trước mọi bean của `FeatureAutoConfiguration`.
- `@ConditionalOnBean` và `@ConditionalOnMissingBean` đặc biệt nhạy với **những bean definition đã được xử lý đến thời điểm kiểm tra**. Vì vậy, thứ tự auto-configuration có thể quyết định việc condition match hay không.
- `after` **không tự tạo dependency**. Nếu B thật sự cần object A khi khởi tạo, hãy khai báo A là tham số constructor/`@Bean` của B, như `optionalAdapter(CorePort corePort)` ở trên.

Cách khác tương đương về mục đích:

```java
@AutoConfiguration
@AutoConfigureAfter(CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // ...
}
```

Muốn đặt cấu hình A trước B, có thể viết `@AutoConfiguration(before = FeatureAutoConfiguration.class)` trên A. Trong trường hợp tham chiếu bằng tên lớp để tránh phụ thuộc compile-time, dùng `beforeName`/`afterName`:

```java
@AutoConfiguration(
    afterName = "com.example.vendor.VendorAutoConfiguration"
)
public class CustomAutoConfiguration {
    // ...
}
```

Đây là **ví dụ API**, không phải chương trình độc lập: tên class được thay theo thư viện thực tế. Dùng phiên bản `Name` khi không muốn import trực tiếp class của auto-configuration tùy chọn.

### 2.2. `@AutoConfigureOrder` khác `@Order` ở đâu?

Spring Boot còn có `@AutoConfigureOrder` cho các auto-configuration cần ưu tiên tương đối mà **không có quan hệ trước/sau rõ ràng với một class cụ thể**:

```java
@AutoConfiguration
@AutoConfigureOrder(-100)
public class EarlyInfrastructureAutoConfiguration {
    // ...
}
```

Số nhỏ hơn nghĩa là mức ưu tiên cao hơn. Tuy nhiên, `@AutoConfigureOrder` chỉ điều khiển **thứ tự các auto-configuration candidate**, và không cam kết thứ tự tạo singleton.

`@Order` là annotation tổng quát của Spring Framework. Nó có thể ảnh hưởng đến thứ tự xử lý một số `@Configuration` thông thường, nhưng **không phải công cụ chuẩn để biểu diễn phụ thuộc giữa hai Spring Boot auto-configuration**. Trong starter, ưu tiên:

- Có quan hệ A trước/sau B rõ ràng → `@AutoConfiguration(before/after)`.
- Có nhu cầu ưu tiên auto-configuration mà không tham chiếu cụ thể → `@AutoConfigureOrder`.
- Muốn sắp xếp nhiều bean cùng interface khi sử dụng → `@Order`/`Ordered` trên **bean liên quan**, không đặt `@Order` lên auto-configuration rồi kỳ vọng các `@Bean` bên trong được sắp thứ tự tương ứng.

### 2.3. Thứ tự trong file `AutoConfiguration.imports` không phải hợp đồng lifecycle

Một starter Spring Boot 3.x khai báo auto-configurations qua:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng ghi tên lớp đầy đủ. Spring Boot thu thập, lọc và sắp các candidate dựa trên metadata auto-configuration, bao gồm quan hệ `before`/`after`. **Đừng dựa vào việc đổi vị trí hai dòng trong imports để quy định bean nào khởi tạo trước**.

Thứ tự auto-configuration còn không quyết định thời điểm một `@Bean` được gọi: Spring có thể tạo bean theo graph phụ thuộc và các quy tắc lifecycle. Đây là ranh giới thiết kế quan trọng của Spring Boot.

## 3. `@Order`: thứ tự ưu tiên khi *sắp xếp* các bean/callback

### 3.1. Annotation khai báo số thứ tự

`@Order` thuộc `org.springframework.core.annotation.Order`:

```java
public interface Handler {
    String name();
}

@Order(10)
public class AuditHandler implements Handler {
    @Override
    public String name() {
        return "audit";
    }
}

@Order(30)
public class ReportHandler implements Handler {
    @Override
    public String name() {
        return "report";
    }
}
```

Đây là đoạn minh họa gồm các type độc lập, không phải toàn bộ ứng dụng. Khi các bean `Handler` được Spring sắp xếp cho một `List<Handler>`, `AuditHandler` thường đứng trước `ReportHandler` bởi `10 < 30`.

Có thể đặt annotation ngay trên phương thức `@Bean` nếu không sở hữu class hoặc muốn sắp riêng từng bean definition:

```java
@Bean
@Order(10)
Handler auditHandler() {
    return () -> "audit";
}

@Bean
@Order(30)
Handler reportHandler() {
    return () -> "report";
}
```

Hai phương thức được giả định nằm trong một class `@Configuration` và có interface `Handler` như ở trên. Với collection injection hoặc `ObjectProvider.orderedStream()`, Spring đọc metadata thứ tự của ứng viên.

**Lưu ý:** `@Order(10)` không có nghĩa bean đó chắc chắn được tạo ở vị trí thứ 10 hoặc khởi tạo trước bean `@Order(30)`. Nó nói về **priority trong phép sắp xếp phù hợp**. Collection do người dùng tạo thủ công bằng `new ArrayList<>()` cũng không tự sắp lại chỉ vì phần tử có annotation.

### 3.2. `Ordered`: đối tượng tự cung cấp thứ tự

`Ordered` thuộc `org.springframework.core.Ordered`. Thay vì số được khai báo tĩnh trên annotation, object trả về số qua `getOrder()`:

```java
public final class DynamicHandler implements Handler, Ordered {

    private final int priority;

    public DynamicHandler(int priority) {
        this.priority = priority;
    }

    @Override
    public String name() {
        return "dynamic";
    }

    @Override
    public int getOrder() {
        return priority;
    }
}
```

Đoạn này yêu cầu import `Ordered` và interface `Handler` đã khai báo. Bean `new DynamicHandler(-10)` được ưu tiên trước bean `@Order(10)` trong một phép sắp phù hợp.

Cả `@Order` và `Ordered` đều dùng quy ước **số nhỏ ưu tiên cao**; có thể dùng `Ordered.HIGHEST_PRECEDENCE`/`Ordered.LOWEST_PRECEDENCE` khi cần biên giới. `Ordered` hữu ích khi giá trị được tính ở runtime hoặc class đã tham gia vào một API Spring có hợp đồng ordering. `@Order` thường đủ khi giá trị cố định.

Cần phân biệt interface `PriorityOrdered`: nó là chuyên biệt của `Ordered` và được một số thuật toán sorting của Spring xử lý như một nhóm ưu tiên riêng. Không giả định tất cả extension point xử lý hoàn toàn giống nhau; hãy kiểm tra hợp đồng của nơi tiêu thụ bean.

### 3.3. Thứ tự handler không đồng nghĩa thứ tự khởi tạo

Giả sử Spring đã khởi tạo hai bean `audit` và `report`, sau đó một service tiêm:

```java
public Pipeline(List<Handler> handlers) {
    this.handlers = handlers;
}
```

Tại injection point có hỗ trợ thứ tự, Spring sắp các bean theo `@Order` hoặc `Ordered`. Còn thứ tự khởi tạo `audit`/`report` phụ thuộc **graph dependency**; `@Order` không ép Spring tạo audit trước report.

Với `ApplicationRunner` và `CommandLineRunner`, Spring Boot cũng hỗ trợ `Ordered`/`@Order` để sắp **thứ tự thực thi callback** sau khi context đã được khởi động. Điều này vẫn khác thời điểm tạo **instance** runner.

## 4. `@DependsOn`: phụ thuộc *khởi tạo* bean theo tên

### 4.1. Khi nào cần?

`@DependsOn` thuộc `org.springframework.context.annotation.DependsOn`. Nó yêu cầu bean mang annotation **phải đợi những bean được nêu tên khởi tạo trước**:

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {

    @Bean("worker")
    @DependsOn("initializer")
    public Worker worker() {
        return new Worker();
    }

    @Bean("initializer")
    public Initializer initializer() {
        return new Initializer();
    }
}
```

Đây là đoạn minh họa; `Worker`/`Initializer` chưa được định nghĩa tại đây. Dù phương thức `worker()` đứng trước `initializer()` trong mã nguồn, `@DependsOn("initializer")` buộc Spring tạo/khởi tạo bean tên `initializer` trước khi khởi tạo `worker`.

Annotation nhận **tên bean**, không phải tên lớp hay tên package. Nếu bean được khai báo `@Bean("initializer")`, giá trị trong `@DependsOn("initializer")` phải trùng. Có thể nêu nhiều dependency: `@DependsOn({"cache", "schemaInitializer"})`.

### 4.2. Khi nên dùng constructor injection thay vì `@DependsOn`?

Nếu `Worker` thật sự cần object `Initializer` để làm việc, khai báo dependency trực tiếp sẽ rõ ràng và an toàn hơn:

```java
@Bean
public Worker worker(Initializer initializer) {
    return new Worker(initializer);
}
```

Cách này buộc Spring giải quyết `Initializer` trước khi gọi factory method tạo `Worker`, đồng thời truyền dependency thật sự và được compiler hỗ trợ kiểm tra kiểu.

`@DependsOn` hữu ích khi có **phụ thuộc khởi tạo mà không cần truyền đối tượng**, chẳng hạn một bean yêu cầu một bean khác đã thực hiện bước khởi tạo phụ trợ. Nhưng tránh biến nó thành cơ chế điều phối workflow dài hạn: tác vụ tốn thời gian, migration, job có retry hoặc tương tác hệ thống ngoài thường cần lifecycle/orchestration có chủ đích riêng.

### 4.3. Ảnh hưởng vòng đời và giới hạn

- Với bean singleton, `@DependsOn` còn khiến các dependency singleton được chỉ định được hủy **sau** bean phụ thuộc, bảo vệ quan hệ kết thúc vòng đời.
- Với prototype hoặc bean được tạo qua đường đi khác, không nên suy diễn một **lịch hủy toàn cục** tương tự singleton.
- `@DependsOn` không quy định **thứ tự đăng ký auto-configuration**, không làm condition `@ConditionalOnBean` tự match nếu bean definition chưa có, và không sắp xếp `List<Handler>`.
- Nếu khai báo dependency vòng tròn A depends on B, B depends on A, ứng dụng có thể lỗi khởi động. Thay vì tạo vòng, thiết kế lại quan hệ.
- `@DependsOn` không tự “chờ hệ thống ngoài ready”. Bean đã khởi tạo không đồng nghĩa database, message broker hoặc một remote service đã sẵn sàng nghiệp vụ.

## 5. Chương trình Spring Boot 3.3.5 / Java 17+ minh họa cả ba lớp thứ tự

Ví dụ bên dưới cho thấy **một lần chạy** ba hiện tượng khác nhau:

1. `FeatureAutoConfiguration` được sắp **sau** `CoreAutoConfiguration` để `@ConditionalOnBean(CorePort.class)` thấy bean definition phù hợp.
2. Các `Handler` được xếp theo `Ordered` và `@Order` khi gọi `orderedStream()`.
3. `@DependsOn("setup")` buộc bean `setup` khởi tạo trước `job`, dù phương thức `job` được viết trước trong mã.

### 5.1. Cấu trúc tệp

```text
order-layers-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/
    │       │   ├── CorePort.java
    │       │   └── OptionalAdapter.java
    │       ├── app/
    │       │   └── DemoApplication.java
    │       └── autoconfigure/
    │           ├── CoreAutoConfiguration.java
    │           └── FeatureAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>order-layers-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. `src/main/java/demo/api/CorePort.java`

```java
package demo.api;

public record CorePort(String id) {
}
```

### 5.4. `src/main/java/demo/api/OptionalAdapter.java`

```java
package demo.api;

public record OptionalAdapter(String source) {
}
```

### 5.5. `src/main/java/demo/autoconfigure/CoreAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.CorePort;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CoreAutoConfiguration {

    @Bean
    public CorePort corePort() {
        return new CorePort("core");
    }
}
```

### 5.6. `src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.CorePort;
import demo.api.OptionalAdapter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CoreAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(CorePort.class)
    public OptionalAdapter optionalAdapter(CorePort corePort) {
        return new OptionalAdapter("connected:" + corePort.id());
    }
}
```

Ở đây có **hai quan hệ khác nhau**:

- `after = CoreAutoConfiguration.class` bảo đảm cấu hình cung cấp `corePort` được xử lý trước, để điều kiện `@ConditionalOnBean` của `optionalAdapter` thấy **bean definition** đã có.
- Tham số `CorePort corePort` của phương thức `@Bean` tạo ra **phụ thuộc instance thực sự**: Spring phải giải quyết một `CorePort` trước khi gọi factory method `optionalAdapter()`.

Nếu bỏ tham số nhưng giữ `after`, thứ tự xử lý auto-configuration vẫn có tác dụng, song không có **dependency injection edge** tương ứng khi tạo instance.

### 5.7. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.CoreAutoConfiguration
```

Chủ ý liệt kê `FeatureAutoConfiguration` **trước** `CoreAutoConfiguration` trong file để minh họa rằng `@AutoConfiguration(after = ...)` là metadata sắp xếp **candidate**. Hai lớp được nạp qua imports thay vì quét component, đúng cách tổ chức auto-configuration trong Spring Boot 3.x.

### 5.8. `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.OptionalAdapter;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@SpringBootApplication
public class DemoApplication {

    private static final List<String> INIT_EVENTS =
            new CopyOnWriteArrayList<>();

    public interface Handler {
        String name();
    }

    public record WeightedHandler(String name, int priority)
            implements Handler, Ordered {

        @Override
        public int getOrder() {
            return priority;
        }
    }

    @Bean
    @Order(30)
    public Handler lastHandler() {
        return () -> "last";
    }

    @Bean
    @Order(10)
    public Handler firstHandler() {
        return () -> "first";
    }

    @Bean
    public Handler dynamicHandler() {
        return new WeightedHandler("dynamic", -10);
    }

    @Bean("job")
    @DependsOn("setup")
    public String job() {
        INIT_EVENTS.add("job");
        return "job";
    }

    @Bean("setup")
    public String setup() {
        INIT_EVENTS.add("setup");
        return "setup";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            OptionalAdapter adapter =
                    context.getBean(OptionalAdapter.class);

            String handlerOrder =
                    context.getBeanProvider(Handler.class)
                            .orderedStream()
                            .map(Handler::name)
                            .collect(Collectors.joining(" > "));

            System.out.println("adapter=" + adapter.source());
            System.out.println("handlers=" + handlerOrder);
            System.out.println("init="
                    + String.join(" > ", INIT_EVENTS));
        }
    }
}
```

**Điều đáng chú ý trong mã:**

- `@Order(30)`/`@Order(10)` nằm **trên từng `@Bean`**, vì ta đang sắp từng `Handler` chứ không muốn điều khiển thứ tự auto-configuration.
- `WeightedHandler` triển khai `Ordered` và trả `-10` tại runtime. `orderedStream()` sẽ sắp **-10, 10, 30**.
- Phương thức `job()` được viết **trước** `setup()`. `@DependsOn("setup")` bảo đảm `setup` khởi tạo xong trước `job`. Danh sách `INIT_EVENTS` chỉ ghi nhận hai bean này để output rõ ràng.
- Các lớp `demo.autoconfigure` là sibling package của `demo.app`, không nằm trong package component scan mặc định của `DemoApplication`. Boot tiếp nhận chúng qua `AutoConfiguration.imports`.

### 5.9. Chạy chương trình

Yêu cầu **JDK 17+**, **Maven 3.6+** và khả năng tải Maven dependencies khi build lần đầu. Từ thư mục `order-layers-demo`:

```bash
mvn -q -DskipTests package
java -jar target/order-layers-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

**Các dòng do chương trình tự in ra:**

```text
adapter=connected:core
handlers=dynamic > first > last
init=setup > job
```

Kết quả giải thích theo từng dòng:

1. `adapter=connected:core`: `CorePort` được đăng ký làm bean definition trước khi condition của `FeatureAutoConfiguration` được đánh giá; adapter cũng nhận instance `CorePort` qua dependency injection.
2. `handlers=dynamic > first > last`: khi gọi `ObjectProvider.orderedStream()`, bean `dynamic` có `getOrder() = -10`, rồi `first` có `@Order(10)`, cuối cùng `last` có `@Order(30)`.
3. `init=setup > job`: quan hệ `@DependsOn("setup")` buộc khởi tạo `setup` trước `job`. Dòng này **không bắt nguồn** từ số `@Order`.

Ví dụ không nhằm khẳng định thứ tự khởi tạo **tất cả** các singleton trong Spring Boot. Chỉ quan hệ `setup -> job` được ràng buộc ở mức bean initialization; các bean không liên quan có thể được tạo vào thời điểm khác.

## 6. Những trường hợp dễ nhầm lẫn

### 6.1. “Gắn `@Order(1)` lên auto-configuration để condition thấy bean trước”

Điều này không diễn đạt đúng hợp đồng thứ tự của Spring Boot auto-configuration. Dùng `@AutoConfiguration(before = .../after = ...)` hoặc `@AutoConfigureBefore`/`@AutoConfigureAfter` và đặt `@ConditionalOnBean` trong auto-configuration phù hợp.

Nếu muốn ưu tiên tương đối giữa các auto-configuration không cần chỉ rõ quan hệ class, dùng `@AutoConfigureOrder`. Không suy ra rằng `@Order(1)` trên một class `@Configuration` sẽ khiến mọi `@Bean` của nó được tạo trước.

### 6.2. “`@AutoConfiguration(after = A.class)` bảo đảm bean A được khởi tạo trước bean B”

Không. Nó bảo đảm **cấu hình A được áp dụng trước cấu hình B** trong quá trình auto-configuration sorting. Nếu B cần A ở runtime, khai báo:

```java
@Bean
public B b(A a) {
    return new B(a);
}
```

Đoạn này mang tính minh họa và giả định hai type `A`/`B` tồn tại. Spring tạo/giải quyết bean A trước khi gọi `b(a)`. Nếu chỉ cần một phụ thuộc khởi tạo không truyền object, cân nhắc `@DependsOn("a")`.

### 6.3. “`@DependsOn` có thể sửa `@ConditionalOnBean` không match”

Không. `@ConditionalOnBean` xét **bean definitions đã được xử lý** khi condition được đánh giá. `@DependsOn` tác động đến **quá trình khởi tạo instance**, diễn ra ở giai đoạn khác. Nếu auto-configuration phụ thuộc bean definition của một auto-configuration khác, xử lý thứ tự bằng `after`/`before`.

### 6.4. “`@Order` luôn bắt tất cả callback hoặc thành phần chạy trước”

Không có một global scheduler chung cho mọi annotation `@Order`. Nó chỉ có ý nghĩa ở **những cơ chế thực sự sắp xếp theo order**, chẳng hạn injection một collection các bean phù hợp, ordering các `ApplicationRunner`/`CommandLineRunner`, hay một số extension point cụ thể. Với các API riêng như servlet filters, interceptors, event listeners, advice, security chains..., cần kiểm tra **hợp đồng thứ tự của API đó**, không suy đoán chỉ từ annotation.

### 6.5. “Số `@Order` càng lớn thì càng chạy sớm”

Ngược lại: trong quy ước Spring `Ordered`, số **nhỏ hơn có độ ưu tiên cao hơn**. Ví dụ `-10` ưu tiên trước `10`, rồi `30`. Không dựa vào thứ tự nếu nhiều bean có cùng giá trị order và bài toán yêu cầu thứ tự tuyệt đối; hãy khai báo giá trị phân biệt hoặc quan hệ dependency thực sự.

### 6.6. “`@Order` và `@Primary` là một”

Không. `@Primary` ưu tiên chọn bean khi có nhiều ứng viên **cho một injection point đơn**; `@Order` và `Ordered` sắp thứ tự các ứng viên trong **collection hoặc quy trình có hỗ trợ sorting**. `@Primary` không phải công cụ thay thế cho một chain handler có thứ tự.

### 6.7. “Đổi thứ tự các `@Bean` trong mã nguồn là đủ”

Không nên dựa vào thứ tự khai báo phương thức để bảo đảm một quan hệ khởi tạo. Nếu bean B thực sự phụ thuộc A, hãy thể hiện graph qua constructor injection, tham số `@Bean` hoặc `@DependsOn`. Cách này ổn định hơn trước các thay đổi như refactor method, tách `@Configuration` hay thêm bean mới.

### 6.8. “`@DependsOn` làm cho hai bean bắt đầu chạy job theo thứ tự”

Annotation này bảo đảm **khởi tạo bean**, không mặc nhiên gọi method nghiệp vụ và không thay thế scheduling. Nếu cả hai bean là runner, dùng chính hợp đồng ordering của runner cho thứ tự callback, và thiết kế rõ dependency/lifecycle nếu còn quan hệ khởi tạo cần thiết.

## 7. Cách kiểm tra và chẩn đoán thực tế

**Bước 1 — xác định loại thứ tự đang lỗi.** Hỏi: bean definition có thiếu khiến `@ConditionalOnBean` thất bại, danh sách handler bị xếp sai, hay một bean khởi tạo quá sớm? Mỗi loại cần công cụ khác.

**Bước 2 — xem Condition Evaluation Report.** Chạy Spring Boot với `--debug` để xem các condition match hoặc không match. Nếu `FeatureAutoConfiguration` không tạo bean, kiểm tra candidate có được nạp qua `AutoConfiguration.imports`, bean definition dependency có tồn tại, và metadata `before`/`after` có đúng không. Log có thể khác nhau theo phiên bản Boot.

**Bước 3 — kiểm tra tập hợp đã được sắp.** Với `List<Handler>` được Spring inject hoặc `ObjectProvider.orderedStream()`, in tên và order thực tế của từng bean. Nếu tự lấy từ `Map` hoặc tự tạo danh sách không được Spring sắp, không giả định annotation tự tác động lên collection đó. Kiểm tra bean method đã có `@Order` riêng chưa.

**Bước 4 — quan sát lifecycle đúng chỗ.** Thêm log trong constructor/`@PostConstruct` hoặc factory method để thấy lúc tạo bean; tránh dùng thứ tự xuất hiện của tên bean trong debugger làm bằng chứng. Nếu lỗi “A chưa sẵn sàng khi tạo B”, bổ sung dependency thực sự hoặc `@DependsOn` đúng tên. Nếu A là hệ thống ngoài, kiểm tra readiness riêng.

**Bước 5 — viết test cho từng lớp hành vi.**

- Với auto-configuration, dùng `ApplicationContextRunner` kết hợp `AutoConfigurations.of(...)` để kiểm tra có/không có bean sau điều kiện; test cả trường hợp người dùng cung cấp bean thay thế. Việc này quan sát **kết quả đăng ký bean**, không suy luận từ startup log.
- Với `@Order`/`Ordered`, assert danh sách được Spring inject hoặc `orderedStream()` cho đúng thứ tự.
- Với `@DependsOn`, tạo một log sự kiện khởi tạo trong các bean và assert `setup` xuất hiện trước `job`.
- Nếu thứ tự các auto-configuration ảnh hưởng condition, kiểm tra trong một test context thực sự dùng auto-configuration sorting; đừng chỉ `new` hai class hay import theo cách bỏ qua đường đi của Spring Boot.

## 8. Quy tắc nhớ nhanh và bài tập

Có thể ghi nhớ bằng ba động từ:

- **Apply** auto-configuration: `@AutoConfiguration(before/after)` / `@AutoConfigureOrder`.
- **Sort** các thành phần: `@Order` / `Ordered`.
- **Initialize** các bean phụ thuộc: injection / `@DependsOn`.

**Bài tập 1.** Auto-config B có `@ConditionalOnBean(CacheManager.class)`, còn auto-config A cung cấp `CacheManager`. Nên chọn gì? **`@AutoConfiguration(after = A.class)` trên B**, đồng thời biểu diễn dependency runtime bằng injection nếu bean của B cần object A.

**Bài tập 2.** Ba handler xử lý một chain theo thứ tự Audit → Security → Response. Nên chọn gì? **`@Order` hoặc `Ordered`** trên các handler, và xác nhận nơi tiêu thụ thực sự tôn trọng ordering.

**Bài tập 3.** Bean `reportWriter` cần bean `fileSystemInitializer` hoàn tất khởi tạo trước nhưng không gọi API của nó. Nên chọn gì? **`@DependsOn("fileSystemInitializer")`** (hoặc thiết kế dependency rõ ràng hơn nếu có quan hệ object thật).

**Bài tập 4.** Một `CommandLineRunner` có `@Order(1)`. Có bảo đảm singleton của runner ấy khởi tạo trước singleton mang `@Order(2)` không? **Không.** Giá trị order ảnh hưởng **thứ tự gọi runner callback**; khởi tạo singleton được quyết định bởi graph bean dependency.

**Bài tập 5.** Một starter có bean filter, service và repository. Muốn filter có độ ưu tiên cao khi một hệ thống web sắp filter, có nên dùng `@AutoConfiguration(before = ...)` để ép callback filter chạy trước? **Không.** Phải điều khiển thứ tự thông qua **cơ chế ordering/filter registration tương ứng**; thứ tự áp dụng auto-configuration không phải thứ tự thực thi filter.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `@AutoConfiguration(before/after)`, `@AutoConfigureOrder`, `AutoConfiguration.imports` và phân biệt thứ tự định nghĩa/khởi tạo bean.
- [Spring Boot 3.3 — `@AutoConfiguration` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): các thuộc tính `before`, `after`, `beforeName`, `afterName`.
- [Spring Framework — Using `@Autowired`, Ordering of collection injection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): `@Order`/`Ordered` đối với collection injection và lưu ý khác biệt với singleton startup order.
- [Spring Framework 6.1 — `Ordered` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html): quy ước số order nhỏ có ưu tiên cao.
- [Spring Framework — `@DependsOn` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html): quan hệ phụ thuộc khởi tạo và hủy bean.
