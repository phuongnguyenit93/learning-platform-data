# `@DependsOn` và lý do `@Order` không quyết định thứ tự tạo mọi bean — Spring Boot 3.3

## 1. Mục tiêu

Khi Spring Boot khởi động, Spring IoC container đăng ký **BeanDefinition**, giải quyết phụ thuộc và khởi tạo các singleton thông thường trong `ApplicationContext.refresh()`. Hai annotation rất dễ bị dùng nhầm:

- **`@DependsOn`**: khai báo **bean hiện tại phụ thuộc vào việc một hay nhiều bean khác đã được khởi tạo xong**. Dependency được chỉ định theo **tên bean**. Với các singleton được container quản lý, quan hệ này còn ảnh hưởng thứ tự hủy khi context đóng.
- **`@Order`**: khai báo **độ ưu tiên** cho các cơ chế **sắp xếp** của Spring, chẳng hạn inject `List<Handler>`, thực thi nhiều runners hoặc gọi một số callback. Nó **không** bảo đảm một singleton có số order nhỏ sẽ được **tạo trước tất cả** singleton có số lớn.

Bài này giúp bạn phân biệt **thứ tự đăng ký bean definitions**, **thứ tự tạo instance**, **thứ tự gọi tác vụ** và **thứ tự hủy**; dùng đúng DI, `@DependsOn`, `@Order`, `@Lazy` và hiểu giới hạn của chúng. Ví dụ thực hành sử dụng **Java 21 và Spring Boot 3.3.13**.

## 2. Vì sao không có một thứ tự khởi tạo toàn cục?

Một mô hình startup đơn giản:

```text
SpringApplication.run(...)
  |
  +-- Tạo và chuẩn bị ApplicationContext
  +-- Nạp primary sources
  +-- refresh()
  |     +-- Xử lý @Configuration/@ComponentScan/@Bean
  |     +-- Đăng ký BeanDefinition
  |     +-- Giải quyết dependency graph
  |     +-- Tạo các singleton non-lazy thông thường
  |     |     +-- constructor/factory method
  |     |     +-- inject dependencies
  |     |     +-- BeanPostProcessor và init callbacks
  |     +-- Hoàn tất refresh
  |
  +-- ApplicationStartedEvent
  +-- ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
```

Sơ đồ là mô hình khái niệm, không liệt kê mọi callback của Spring. Có bean `@Lazy`, scope `prototype`, request hoặc bean chỉ được tạo khi được yêu cầu; các bean này không nhất thiết được khởi tạo trong refresh.

Nếu bean B cần A thông qua constructor, Spring phải giải quyết phụ thuộc A trước khi hoàn tất việc tạo B:

```java
@Component
class BillingService {
    private final PaymentGateway gateway;

    BillingService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Đoạn này là **minh họa**: cần khai báo interface `PaymentGateway` và một implementation bean. Constructor injection diễn đạt dependency thật. Thường **không cần** thêm `@DependsOn` khi quan hệ đã được mô tả như vậy.

Tuy nhiên, nếu C không liên quan đến A hoặc B, không có cam kết tổng quát rằng C phải được tạo trước hay sau chúng. Thứ tự quan sát trong một lần chạy có thể chịu tác động từ việc đăng ký definitions và implementation của container; đừng xây logic nghiệp vụ dựa trên thứ tự tình cờ.

| Loại thứ tự | Điều cần hỏi | Cơ chế phù hợp |
| --- | --- | --- |
| Đăng ký definitions | Spring tìm thấy những class/configuration nào? | `@ComponentScan`, `@Import`, `@Configuration`, `@Bean` |
| Tạo và init instance | Bean B cần bean A hoàn tất initialization trước? | Constructor DI và dependency graph; `@DependsOn` cho quan hệ gián tiếp |
| Sắp xếp khi sử dụng | Có nhiều strategy beans trong `List<Strategy>`: ai được đặt trước? | `@Order`, `Ordered` |
| Gọi các startup tasks | Runner nào được Boot gọi trước? | `@Order` hoặc `Ordered` trên runners |
| Hủy beans | Bean nào cần được destroy trước dependency của nó? | Dependency graph; `@DependsOn` ở singleton |
| Start/stop lifecycle component | Phần tử `SmartLifecycle` nào start/stop theo phase? | `SmartLifecycle.getPhase()` và dependencies |

## 3. `@DependsOn`: ý nghĩa và phạm vi

### 3.1. Ngữ nghĩa chính

Ví dụ:

```java
@Component("cacheBootstrap")
class CacheBootstrap {
}

@Component
@DependsOn("cacheBootstrap")
class ReportService {
}
```

Đây là **đoạn minh họa Spring**, cần imports cho `@Component` và `@DependsOn` nếu dùng. Khi container chuẩn bị tạo `reportService`, nó bảo đảm bean **tên chính xác** `cacheBootstrap` được khởi tạo trước. Tên bean có phân biệt chữ hoa, chữ thường; không được nhầm bean name với tên class hay package.

Có thể liệt kê nhiều dependencies:

```java
@DependsOn({"schemaCheck", "cacheBootstrap"})
```

Khi tạo bean được gắn annotation, Spring sẽ khởi tạo các bean được liệt kê trước nó. Điều này **không bảo đảm mọi bean không liên quan đều có thứ tự cố định**, và không nên suy luận thứ tự toàn cục từ một annotation.

### 3.2. Khi nào đáng dùng?

`@DependsOn` hữu ích khi một bean cần **side effect khởi tạo** của bean khác mà không có object dependency trực tiếp rõ ràng, ví dụ:

- Một bean hạ tầng đăng ký tài nguyên hoặc plugin nội bộ **đồng bộ** trong init callback.
- Một bean cần một bước kiểm tra cấu hình hoặc schema được bean khác thực hiện xong trước khi nó initialize.
- Một hệ thống legacy có quan hệ startup gián tiếp chưa chuyển đổi được sang interface/constructor injection.

Không nên coi đây là công cụ bắt buộc cho các service gọi nhau. Nếu `ReportService` thực sự cần gọi phương thức của `CacheBootstrap`, hãy inject qua constructor; ràng buộc type rõ hơn, dễ kiểm thử hơn và tránh phụ thuộc vào chuỗi tên bean.

### 3.3. Thứ tự hủy với singleton

Đối với **singleton** được Spring quản lý, `@DependsOn` thường thiết lập cả quan hệ hủy đảo chiều:

```text
Khởi tạo:  cacheBootstrap init --> reportService init
Hủy:        reportService destroy --> cacheBootstrap destroy
```

Điều này có ý nghĩa khi callback `@PreDestroy` của bean phụ thuộc còn cần tài nguyên mà bean kia cung cấp. Spring không quản lý trọn vòng đời hủy của **prototype** như đối với singleton; đừng áp dụng kết luận hủy này cho mọi scope.

### 3.4. Đặt annotation ở đâu?

`@DependsOn` được hỗ trợ trên class được Spring đăng ký thông qua **component scan** hoặc trên **phương thức `@Bean`**. Metadata phải được dùng bởi đúng cơ chế đăng ký. Nếu class được đăng ký bằng một cơ chế khác như XML, annotation trên class không nhất thiết được áp dụng; với XML dùng khai báo `depends-on` của bean definition tương ứng.

Ví dụ dạng `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class InfraConfiguration {

    @Bean("schemaCheck")
    SchemaCheck schemaCheck() {
        return new SchemaCheck();
    }

    @Bean
    @DependsOn("schemaCheck")
    ReportJob reportJob() {
        return new ReportJob();
    }
}
```

**Đây là đoạn minh họa không độc lập**: cần tự định nghĩa `SchemaCheck`, `ReportJob` và imports `@Configuration`, `@Bean`, `@DependsOn`. Khi Spring tạo `reportJob`, bean `schemaCheck` phải được initialized trước.

Nếu `SchemaCheck` chỉ khởi chạy background thread rồi trả về, `@DependsOn` **không đợi** thread hoàn thành. Nó bảo đảm việc **initialization callback của bean** đã hoàn tất, không phải mọi dịch vụ bên ngoài hoặc tác vụ bất đồng bộ đã ready. Đối với schema migration thực, dùng công cụ quản lý migration và readiness/timeout phù hợp.

## 4. `@Order`: chọn thứ tự khi framework cần sắp xếp

`@Order` thuộc `org.springframework.core.annotation`. Số càng **nhỏ** thì ưu tiên càng **cao** trong các cơ chế ordering hỗ trợ annotation này. Ví dụ:

```java
@Component
@Order(10)
class FastHandler implements Handler {
    @Override
    public String name() {
        return "fast";
    }
}

@Component
@Order(20)
class SlowHandler implements Handler {
    @Override
    public String name() {
        return "slow";
    }
}
```

**Đoạn trên cần interface `Handler` và imports** nếu chạy riêng; ở mục 5 có dự án hoàn chỉnh. Khi Spring inject `List<Handler>`, thứ tự thường là `[FastHandler, SlowHandler]` theo metadata của những bean đáp ứng interface.

Nhưng **thứ tự các phần tử trong danh sách không chứng minh thứ tự gọi constructor hay `@PostConstruct`**. Framework có thể resolve/tạo các bean trước khi sắp danh sách. Hai hành vi là hai hợp đồng khác nhau.

### 4.1. Các tình huống `@Order` hữu ích

- Collection injection: `List<Strategy>`, `Strategy[]` hoặc các injection point có hỗ trợ ordering.
- Nhiều `ApplicationRunner` và `CommandLineRunner`: Boot sắp xếp các runner để xác định **thứ tự gọi `run(...)`**, không xác định constructor của mọi bean.
- Một số event listeners, interceptors, handlers, infrastructure components có cơ chế ordering riêng.
- Annotation trên phương thức `@Bean` để tác động thứ tự của bean instance được đưa vào collection khi framework hỗ trợ.

Nếu hai phần tử có cùng order value, đừng giả định thứ tự giữa chúng được xác định bởi tên class. `@Order` có thể đi cùng `Ordered`, nhưng phải xét contract của điểm mở rộng cụ thể.

### 4.2. Sai lầm điển hình

```java
@Component
@Order(1)
class A {
}

@Component
@Order(2)
class B {
}
```

Không thể kết luận `A` luôn được init trước `B` chỉ từ hai annotation. Không có dependency nào được khai báo giữa A và B.

Nếu B cần A hoàn tất initialization, hãy biểu diễn quan hệ bằng DI hoặc `@DependsOn("a")` khi thực sự là phụ thuộc vào side effect. Nếu chỉ cần dùng A trước B **khi xử lý một danh sách strategies**, thì `@Order` phù hợp.

## 5. Ví dụ hoàn chỉnh chạy được — Java 21, Spring Boot 3.3.13

Dự án non-web sau quan sát **hai hợp đồng khác nhau**:

1. `InvoiceService` có `@DependsOn("startupCache")`: cache phải initialize trước invoice. Với singleton, invoice được destroy trước cache.
2. `List<TaskHandler>` được inject theo `@Order`: runner in `[fast, slow]`. Ta **không kết luận** về thứ tự constructor của hai handler.

### 5.1. Cấu trúc tệp

```text
bean-order-demo/
├── pom.xml
└── src/main/java/com/example/ordering/
    ├── BeanOrderApplication.java
    ├── StartupCache.java
    ├── InvoiceService.java
    ├── TaskHandler.java
    ├── FastTaskHandler.java
    └── SlowTaskHandler.java
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
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
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

Spring Boot 3.3 hỗ trợ Java 21 và yêu cầu tối thiểu Java 17. `spring-boot-starter` đáp ứng chương trình CLI; không cần web server. Import `jakarta.annotation.PostConstruct` và `jakarta.annotation.PreDestroy` thuộc namespace Jakarta dùng với Spring Framework 6.

### 5.3. Bean hạ tầng: `StartupCache.java`

**Tệp `src/main/java/com/example/ordering/StartupCache.java`:**

```java
package com.example.ordering;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component("startupCache")
public class StartupCache {

    @PostConstruct
    public void init() {
        System.out.println("CACHE init");
    }

    @PreDestroy
    public void destroy() {
        System.out.println("CACHE destroy");
    }
}
```

`@Component("startupCache")` chọn bean name tường minh. `@PostConstruct` được gọi khi bean initialize; `@PreDestroy` chạy khi singleton được Spring hủy trong lúc đóng context.

### 5.4. Bean phụ thuộc: `InvoiceService.java`

**Tệp `src/main/java/com/example/ordering/InvoiceService.java`:**

```java
package com.example.ordering;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.DependsOn;
import org.springframework.stereotype.Component;

@Component
@DependsOn("startupCache")
public class InvoiceService {

    @PostConstruct
    public void init() {
        System.out.println("INVOICE init");
    }

    @PreDestroy
    public void destroy() {
        System.out.println("INVOICE destroy");
    }
}
```

Demo cố ý không inject đối tượng `StartupCache` để thể hiện dependency vào **side effect initialization**. Trong ứng dụng thật, nếu `InvoiceService` sử dụng API của cache, nên inject cache qua constructor. Với quan hệ `@DependsOn`, `CACHE init` **phải có trước** `INVOICE init`; khi đóng context, `INVOICE destroy` **phải có trước** `CACHE destroy`.

### 5.5. Các handler và `@Order`

**Tệp `src/main/java/com/example/ordering/TaskHandler.java`:**

```java
package com.example.ordering;

public interface TaskHandler {
    String name();
}
```

**Tệp `src/main/java/com/example/ordering/FastTaskHandler.java`:**

```java
package com.example.ordering;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class FastTaskHandler implements TaskHandler {
    @Override
    public String name() {
        return "fast";
    }
}
```

**Tệp `src/main/java/com/example/ordering/SlowTaskHandler.java`:**

```java
package com.example.ordering;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class SlowTaskHandler implements TaskHandler {
    @Override
    public String name() {
        return "slow";
    }
}
```

Hai classes độc lập trong dependency graph. `@Order` giúp Spring sắp các implementation khi inject collection, nhưng **không** đặt quan hệ khởi tạo giữa chúng.

### 5.6. Lớp main và runner

**Tệp `src/main/java/com/example/ordering/BeanOrderApplication.java`:**

```java
package com.example.ordering;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanOrderApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(BeanOrderApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Đóng context sau khi runner chạy, để quan sát callback destroy.
        try (ConfigurableApplicationContext context = app.run(args)) {
            // Spring Boot đã gọi ApplicationRunner trong app.run(args).
        }
    }

    @Bean
    ApplicationRunner showHandlerOrder(List<TaskHandler> handlers) {
        return args -> {
            List<String> names = handlers.stream()
                    .map(TaskHandler::name)
                    .toList();
            System.out.println("ORDERED handlers: " + names);
        };
    }
}
```

Chú ý:

- `@SpringBootApplication` ở `com.example.ordering` nên component scan tìm thấy các classes trong cùng package.
- `List<TaskHandler>` là injection point cho collection; Spring sắp phần tử theo `@Order`.
- `ApplicationRunner` chạy **sau refresh** và trước `ApplicationReadyEvent`; nó không ép thứ tự tạo mọi component.
- `try-with-resources` gọi `ConfigurableApplicationContext.close()` khi `run(...)` trả về, giúp demo quan sát rõ `@PreDestroy` mà không phải tắt ứng dụng bằng kill cưỡng bức.

### 5.7. Chạy và đối chiếu output

Yêu cầu JDK 21, Maven và các dependencies Maven khả dụng. Trong thư mục `bean-order-demo`:

```bash
java -version
mvn -version
mvn package
java -jar target/bean-order-demo-0.0.1-SNAPSHOT.jar
```

Năm dòng do chương trình in, **bỏ qua banner và log của Boot**, là:

```text
CACHE init
INVOICE init
ORDERED handlers: [fast, slow]
INVOICE destroy
CACHE destroy
```

Các dòng log framework có thể xen giữa; khối trên trình bày **chỉ những dòng của ví dụ**. Lý giải:

- `CACHE init` trước `INVOICE init`: do `@DependsOn("startupCache")`.
- `ORDERED handlers: [fast, slow]`: do sorting của `List<TaskHandler>` dựa trên `@Order(10)` và `@Order(20)`.
- `INVOICE destroy` trước `CACHE destroy`: do quan hệ dependency giữa singleton khi context đóng.
- Code không ghi log constructors của handlers, vì output danh sách đã sắp **không nói lên thứ tự tạo** hai objects.

Khi xem console, đừng nhầm log đã sorted của collection với log lifecycle. Hai vấn đề có quan hệ hoàn toàn khác nhau.

## 6. Vòng đời khác và giới hạn của hai annotation

### 6.1. `@PostConstruct` / `@PreDestroy`

`@PostConstruct` chạy khi dependency injection và các bước chuẩn bị cần thiết của bean đã thực hiện; `@PreDestroy` chạy khi container hủy bean được quản lý phù hợp. Chúng không tự có thứ tự toàn ứng dụng. Thứ tự tương đối giữa **các bean** đến từ dependency graph hoặc contract lifecycle riêng.

Spring Boot 3/Spring Framework 6 dùng `jakarta.annotation.PostConstruct` và `jakarta.annotation.PreDestroy`; import `javax.annotation` cũ có thể không tương thích nếu không có thư viện legacy riêng.

### 6.2. `@Lazy` và scope

- `@Lazy` có thể trì hoãn tạo singleton cho đến lúc được yêu cầu.
- Nếu một bean singleton **eager** có `@DependsOn("lazyDependency")`, Spring cần tạo `lazyDependency` trước khi tạo bean eager.
- Nếu chính bean có `@DependsOn` cũng lazy và chưa ai yêu cầu, annotation không tự khiến bean đó được khởi tạo tại startup.
- Bean `prototype` được tạo theo yêu cầu; Spring không tự quản lý callback destroy của prototype giống singleton.

Do đó cần tách “**khi nào bean được yêu cầu**” khỏi “**thứ tự các dependencies khi đang tạo bean**”.

### 6.3. `SmartLifecycle` và thứ tự start/stop

Một số component, ví dụ message consumers, cần được **start/stop** sau khi đối tượng đã tạo. `SmartLifecycle.getPhase()` có cơ chế riêng để điều phối start/stop theo phase; đó là một chuyện khác với thứ tự constructor hoặc `@PostConstruct`. Đừng cho rằng `@Order` trên component là cách điều khiển mọi pha `SmartLifecycle`.

### 6.4. Runners và listeners có thứ tự riêng

Nếu cần chạy các startup tasks theo một trình tự, `ApplicationRunner`/`CommandLineRunner` hỗ trợ `@Order` hoặc `Ordered` để Boot sắp thứ tự **gọi `run(...)`** của các runner beans. Thứ tự này vẫn không cho biết những singleton chứa runner được **khởi tạo lúc nào** so với các bean khác.

Một số event listeners có thể dùng `@Order` để sắp callback cho cùng một event. Thứ tự listener không thể khiến `ApplicationReadyEvent` phát trước `ApplicationStartedEvent`.

## 7. Các lỗi và hiểu lầm thường gặp

| Tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Gắn `@Order(1)` lên bean để “init trước” bean mang `@Order(2)` | `@Order` không thiết lập quan hệ startup toàn cục | Sử dụng DI hoặc `@DependsOn` khi có phụ thuộc thật |
| `@DependsOn("StartupCache")` nhưng bean name là `startupCache` | Tên bean không khớp, có phân biệt hoa/thường | Kiểm tra tên bean được đăng ký, sửa annotation |
| Gắn `@DependsOn` lên class không được quét/đăng ký qua component scan | Metadata có thể không được áp dụng | Đặt trên `@Bean` method hoặc cơ chế definition tương ứng |
| A phụ thuộc B, B phụ thuộc A | Circular dependency, khởi tạo không thể hoàn tất | Tách trách nhiệm, loại bỏ quan hệ vòng |
| Dùng `@DependsOn` để đợi database/remote service ready | Chỉ bảo đảm bean đã initialized, không đợi mọi hệ thống ngoài | Dùng migration, readiness, timeout và health checks thực tế |
| Init method của A khởi chạy task async rồi trả về | B có thể được khởi tạo khi task chưa hoàn tất | Chờ completion đúng chỗ hoặc phối hợp startup hợp lý |
| `@Lazy` không khởi tạo tại startup | Bean chưa được yêu cầu | Kiểm tra mức lazy/eager và dependency graph |
| Hai beans có cùng `@Order` | Chưa xác định rõ thứ tự tương đối | Chọn order values khác nhau nếu cần |
| `@PreDestroy` không in log | Context bị kill hoặc không đóng như dự tính | Đóng context trong test/demo, xem scope và shutdown mode |
| Test khẳng định thứ tự log ngẫu nhiên | Log tình cờ không chứng minh contract của container | Test dependency relationship hoặc sorted collection đúng mục tiêu |

### 7.1. Cấu hình vòng phụ thuộc

```java
@Component("a")
@DependsOn("b")
class A {
}

@Component("b")
@DependsOn("a")
class B {
}
```

Đây là **mẫu cấu hình lỗi**, chỉ dùng để phân tích. Spring có thể phát hiện circular dependency và ném exception khi cố khởi tạo. Không giải quyết bằng cách vô hiệu hóa kiểm tra vòng; hãy thiết kế lại quan hệ.

### 7.2. Chỉ thiết lập thứ tự cục bộ, không áp đặt toàn hệ thống

Nếu B có `@DependsOn("a")` còn C không liên quan:

```text
A --> B      (B phải khởi tạo sau A)
C            (độc lập)
```

Các thứ tự A-B-C, A-C-B hoặc C-A-B đều có thể thỏa quan hệ A trước B. **Không thể suy ra vị trí của C**. Muốn có thêm ràng buộc thì phải có dependency thực sự để mô tả.

### 7.3. Phân biệt test về init order và test về priority

Với `@DependsOn`, kiểm tra tại initialization callback của B rằng công việc init **đồng bộ** của A đã hoàn tất. Với `@Order`, kiểm tra `List<Handler>` đã inject hoặc thứ tự gọi runners có đúng thứ tự mong muốn. Đây là hai assertion khác nhau; đừng dùng một cái để chứng minh cái còn lại.

## 8. Cách chọn trong dự án

**Tình huống 1 — `PaymentService` phải gọi `PaymentGateway`:** constructor injection. Type-safe và testable; không cần `@DependsOn` dư thừa.

**Tình huống 2 — `ReportService` phụ thuộc side effect init của `SchemaRegistrar`:** cân nhắc `@DependsOn("schemaRegistrar")`, nếu không có object dependency thực tế và công việc init là đồng bộ. Hãy mô tả rõ lý do phụ thuộc.

**Tình huống 3 — 5 strategies xử lý cùng interface cần ưu tiên theo business rule:** `@Order` + inject `List<Strategy>` rồi lặp. Không dùng annotation này để ra lệnh khởi tạo toàn bộ singleton theo danh sách.

**Tình huống 4 — hai runners cần chạy tác vụ A rồi B trước ready:** dùng `ApplicationRunner`/`CommandLineRunner` với `@Order` trên chính runners, hoặc thiết kế dependency thực phù hợp. Boot gọi runners sau refresh, trước ready.

**Tình huống 5 — message consumer và provider cần start/stop theo phase:** dùng `SmartLifecycle` và dependency phù hợp. `@Order` không tự quản lý các phase này.

## 9. Bài tập tự kiểm tra

1. Nêu khác biệt giữa thứ tự đăng ký definition, thứ tự tạo instance và thứ tự sắp xếp `List<Handler>`.
2. Trong demo, vì sao `CACHE init` chắc chắn trước `INVOICE init`? Vì sao hủy lại theo chiều đảo?
3. Vì sao `[fast, slow]` **không chứng minh** `FastTaskHandler` được tạo trước `SlowTaskHandler`?
4. Bỏ `@DependsOn("startupCache")`, chạy lại. Nếu thứ tự log vẫn giống cũ, điều gì **không** còn được bảo đảm?
5. Đổi `@Order(10)` của `FastTaskHandler` thành `@Order(30)`. Dự đoán và xác minh `List<TaskHandler>` khi runner chạy.
6. Đổi `InvoiceService` sang constructor nhận `StartupCache` thật sự. Có cần giữ `@DependsOn` không?
7. Đổi bean name thành `cacheBootstrap` nhưng vẫn để `@DependsOn("startupCache")`. Vì sao startup có thể thất bại?
8. Thêm `@Lazy` vào `StartupCache`, giữ `InvoiceService` eager. Điều gì xảy ra khi invoice khởi tạo?
9. Nếu cả hai đều lazy và không bean nào được yêu cầu, có bảo đảm hai init callbacks chạy lúc startup không?
10. Với `@DependsOn({"a","b"})` trên C, có thể khẳng định A luôn init trước B không?
11. Viết hai `ApplicationRunner` có `@Order(10)` và `@Order(20)`. Phân biệt thứ tự **gọi runner** với thứ tự **tạo runner bean**.
12. Vì sao `@DependsOn` không bảo đảm một background thread của A đã hoàn thành khi B initialize?
13. Khi chạy demo, tại sao cần đóng `ConfigurableApplicationContext` để quan sát `@PreDestroy`?
14. Khi nào `SmartLifecycle.getPhase()` thích hợp hơn `@Order` hoặc `@DependsOn`?

**Tiêu chí đạt:** chạy được demo, giải thích đúng năm dòng output, chọn DI/`@DependsOn`/`@Order` theo mục đích thật, và không suy luận từ thứ tự tạo bean ngẫu nhiên.

## 10. Tài liệu chính thức

- Spring Framework 6.1 — `@Order` và singleton startup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/annotation/Order.html
- Spring Framework 6.1 — `@DependsOn` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html
- Spring Framework — Using depends-on: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html
- Spring Framework — Bean scopes và prototype: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Java Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Boot 3.3 — SpringApplication và runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
