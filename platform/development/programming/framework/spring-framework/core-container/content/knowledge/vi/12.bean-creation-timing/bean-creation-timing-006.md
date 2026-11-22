# Thứ tự khởi tạo xuất phát từ đồ thị phụ thuộc trong Spring Core Container

## 1. Mục tiêu bài học

Trong Spring Framework, việc một bean được khởi tạo trước hay sau bean khác **chủ yếu được quyết định bởi quan hệ phụ thuộc**, chứ không phải thứ tự bạn đặt phương thức `@Bean`, thứ tự class trong `@Import`, vị trí `<bean>` trong XML hay giá trị `@Order` của bean. Một bean cần một dependency để hoàn tất constructor hoặc factory method phải đợi dependency ấy được giải quyết.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean
    CatalogRepository catalogRepository() {
        return new InMemoryCatalogRepository();
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
```

Đây là **minh họa**, cần các kiểu Java phù hợp. Nhìn vào chữ ký của các factory methods, Spring biết:

```text
catalogController -> catalogService -> catalogRepository
```

Mũi tên nghĩa là **bean bên trái cần bean bên phải**. Do đó khi phải tạo `catalogController`, Spring đảm bảo `catalogRepository` và `catalogService` được tạo/giải quyết đủ để truyền vào constructors/factory methods trước khi hoàn tất controller.

Nhưng nếu có thêm `metricsExporter` không liên quan ba bean này, **không thể kết luận** nó chắc chắn tạo trước hoặc sau `catalogRepository` chỉ vì method `metricsExporter()` viết ở dòng đầu của class.

Sau bài học, bạn có thể:

1. Vẽ và đọc **đồ thị phụ thuộc có hướng** từ constructors, setter/property injection, factory method parameters và metadata `depends-on`.
2. Phân biệt **thứ tự từng phần (partial order)** với một thứ tự toàn phần cố định.
3. Hiểu Spring tạo regular singleton không lazy trong `ApplicationContext.refresh()` nhưng vẫn giải quyết những dependencies trước.
4. Biết Spring có thể tạo một lazy bean sớm vì là dependency của eager bean.
5. Dùng `@Bean` method parameters và constructor injection để công khai quan hệ phụ thuộc.
6. Dùng `@DependsOn`/XML `depends-on` cho **ràng buộc khởi tạo không thể hiện qua reference trực tiếp**, và hiểu hệ quả đối với destruction order.
7. Phân biệt `@Order`, `Ordered` và `@Priority` dùng cho sorting/selection với bean startup order.
8. Phân biệt `@Import`/`@ImportResource`, XML file order và actual bean dependency order.
9. Nhận ra circular dependencies và chọn cách tái cấu trúc thích hợp.
10. Hiểu điểm mở rộng như `SmartInitializingSingleton`, `SmartLifecycle` và `ContextRefreshedEvent` không đồng nghĩa với constructor dependency ordering.
11. Chạy ví dụ **Java 17 + Spring Framework 6.2** có các assertions về thứ tự đúng hợp đồng nhưng không phụ thuộc thứ tự tình cờ của các beans độc lập.
12. Viết tests và debug các lỗi initialization/circular dependency trong ứng dụng thật.

**Tư tưởng chính:** Spring bảo đảm **A đã có dependency B cần thiết khi A được tạo**; Spring không bảo đảm **mọi bean độc lập có thứ tự startup theo một quy tắc mà bạn có thể dùng làm workflow nghiệp vụ**.

## 2. Đồ thị phụ thuộc là gì?

Mô hình hóa mỗi bean definition/bean instance cần tạo bằng một **đỉnh**. Một dependency từ bean A tới bean B được vẽ:

```text
A --> B
```

Nghĩa là “để khởi tạo A, container cần B”, không phải “A chắc chắn sẽ gọi B trong runtime”.

Cho các bean:

- `Controller` cần `Service`.
- `Service` cần `Repository` và `Clock`.
- `Repository` không cần `Service`.
- `MetricsExporter` độc lập với ba bean còn lại.

Đồ thị:

```text
                   Controller
                       |
                       v
                    Service
                    /     \
                   v       v
             Repository   Clock

             MetricsExporter
              (độc lập)
```

Spring biết các **ràng buộc**:

- Repository phải được tạo/giải quyết trước khi Service được hoàn tất.
- Clock phải được tạo/giải quyết trước khi Service được hoàn tất.
- Service phải được tạo/giải quyết trước khi Controller được hoàn tất.
- Theo tính bắc cầu, Repository và Clock cần sẵn sàng trước Controller.

Nhưng giữa **Repository và Clock** không có cạnh trực tiếp; cả hai có thể được tạo theo một trong các thứ tự hợp lệ. **MetricsExporter** cũng không có cạnh nối, nên không được giả định vị trí của nó trong một thứ tự toàn phần.

### 2.1. Thứ tự từng phần, không phải lịch trình cố định

Trong lý thuyết đồ thị, tập điều kiện “B trước A” như trên tạo **partial order** khi không có chu trình. Có nhiều **topological orders** hợp lệ:

```text
Repository, Clock, Service, Controller, MetricsExporter
Clock, Repository, MetricsExporter, Service, Controller
MetricsExporter, Clock, Repository, Service, Controller
```

Ba chuỗi chỉ là **những thứ tự có thể thỏa cùng constraints**, không phải cam kết Spring sẽ sử dụng chính một trong ba chuỗi này. Quyền ưu tiên ở đây là đáp ứng đúng dependencies và lifecycle; thời điểm chính xác giữa các node độc lập là chi tiết không nên dựa vào.

### 2.2. Thứ tự tạo instance khác thứ tự đăng ký definition

`BeanDefinition` là metadata về bean: class, factory method, scope, lazy, constructor args, properties, depends-on và các lựa chọn khác. Các definitions có thể được đăng ký trước khi instance nào được tạo.

```text
register definitions:
    Controller
    MetricsExporter
    Service
    Repository
    Clock

instantiate as needed:
    Repository / Clock -> Service -> Controller
    MetricsExporter (độc lập)
```

Nếu đọc danh sách bean definition names, bạn có thể thấy thứ tự đăng ký. **Đừng dùng thứ tự đó như thứ tự nghiệp vụ khởi tạo**.

## 3. Cách Spring quyết định thời điểm tạo bean

Một `ApplicationContext` thông thường làm nhiều bước khi `refresh()`:

```text
Tìm/đọc Java config, XML, component metadata
                    |
                    v
Đăng ký BeanDefinitions
                    |
                    v
Xử lý BeanFactoryPostProcessor / BeanPostProcessor
                    |
                    v
Pre-instantiate regular non-lazy singletons
                    |
                    +--> lấy bean A
                    |      |
                    |      +--> A cần bean B
                    |                |
                    |                +--> B cần bean C
                    |                |       |
                    |                |       v
                    |                |     tạo C
                    |                v
                    |              tạo B
                    v
                  tạo A
                    |
                    v
Kết thúc pre-instantiation / refresh
```

Đây là **mô hình khái niệm**. Spring có hạ tầng đặc biệt cho proxy, bean post-processors, `FactoryBean`, circular reference handling, scoped beans và Spring 6.2 background bootstrap; không diễn giải sơ đồ như thuật toán từng dòng cho mọi implementation.

### 3.1. Spring không chỉ tuân theo thứ tự khai báo methods

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Controller controller(Service service) {
        return new Controller(service);
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository);
    }

    @Bean
    Repository repository() {
        return new Repository();
    }
}
```

Nếu `controller` được yêu cầu, container vẫn phải giải quyết `Service` và `Repository` trước khi có thể gọi constructor/factory method với các arguments cần thiết, dù factory method `controller` được viết trước trong source.

### 3.2. Spring không cần một bean đã được tạo để biết dependency

Spring biết type/metadata của constructors, factory methods, `@Autowired` và XML references. Nó có thể resolve dependencies **lúc tạo bean**, dựa trên registry chứa các definitions.

Một Java bean implementation có thể được khai báo tại config khác, nhưng BeanFactory vẫn tìm được nếu tất cả definitions thuộc cùng context.

### 3.3. Bean được đánh lazy có thể xuất hiện trong thứ tự startup

```java
@Bean
@Lazy
Repository lazyRepository() {
    return new Repository();
}

@Bean
Service eagerService(Repository lazyRepository) {
    return new Service(lazyRepository);
}
```

Ở ví dụ minh họa này, nếu `eagerService` là singleton không lazy, Spring phải resolve `Repository` ngay trong startup. `@Lazy` trên definition của repository chỉ ngăn chủ động pre-instantiate độc lập, không ngăn nó được tạo như một dependency bắt buộc của bean eager.

## 4. Những kiểu cạnh dependency mà Spring nhận ra

Spring có thể hình thành dependency relationships qua nhiều cơ chế.

### 4.1. Constructor injection

```java
final class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

Nếu Spring tạo `OrderService` và constructor yêu cầu `OrderRepository`, repository phải có trước khi lời gọi constructor hoàn thành.

### 4.2. Tham số của @Bean factory method

```java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
```

BeanFactory phải resolve `OrderRepository` trước khi gọi `orderService(repository)`. Đây là cách diễn đạt rất phù hợp khi một class `@Configuration` tạo nhiều beans từ các modules khác nhau.

### 4.3. Setter/property injection

```java
final class TaskProcessor {
    private TaskRepository repository;

    public void setRepository(TaskRepository repository) {
        this.repository = repository;
    }
}
```

XML:

```xml
<bean id="taskProcessor" class="example.TaskProcessor">
    <property name="repository" ref="taskRepository"/>
</bean>
```

BeanFactory cần repository khi populate properties trước các bước initialization tương ứng. Ở setter injection, **raw object TaskProcessor có thể đã qua constructor trước khi repository được inject**. Vì vậy câu “dependency trước consumer” thường phải hiểu là **dependency phải được resolve trước khi consumer hoàn tất initialization**, không phải mọi constructor của mọi consumer đều bắt buộc chạy sau mọi constructor của dependencies, nhất là khi dùng setter/field injection hoặc circular-reference mechanisms.

### 4.4. @Autowired field

```java
@Component
class BillingFacade {
    @Autowired
    BillingService billingService;
}
```

Field injection cũng khiến container phải resolve `BillingService` trong giai đoạn population của `BillingFacade`. Tuy nhiên constructor của facade có thể chạy **trước** lúc field được inject. Đó là một lý do constructor injection thường giúp dependency graph minh bạch hơn và bảo đảm invariant sớm hơn.

### 4.5. @DependsOn / depends-on metadata

```java
@Bean
@DependsOn("schemaValidator")
DataAccessService dataAccessService() {
    return new DataAccessService();
}
```

Ở đây `dataAccessService` không nhận reference `schemaValidator` qua tham số, nhưng metadata nói phải khởi tạo `schemaValidator` trước khi tạo bean service. Đó là một **cạnh ordering explicit**.

### 4.6. Lookup động là cạnh phụ thuộc muộn

```java
final class Exporter {
    private final ObjectProvider<RemoteGateway> gateway;

    Exporter(ObjectProvider<RemoteGateway> gateway) {
        this.gateway = gateway;
    }

    void sendLater() {
        gateway.getObject().send();
    }
}
```

Đây là minh họa cần `ObjectProvider`/`RemoteGateway` phù hợp. Constructor `Exporter` có thể được tạo mà không cần instantiate gateway target ngay. Dependency được resolve **khi method gọi provider**, nên không phải cạnh “gateway target phải tạo trước constructor Exporter”.

## 5. Phân biệt dependency graph và import graph

`@Import` là cơ chế **ghép bean definitions/configuration classes**, không phải ràng buộc mọi bean trong config A đều được tạo trước mọi bean trong config B.

```java
@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class RootConfig {
}
```

Điều này đưa hai classes cấu hình vào pipeline, tạo metadata bean definitions trong cùng container. Nhưng thứ tự:

```java
@Import({RepositoryConfig.class, ServiceConfig.class})
```

không nên được dùng để nói “tất cả repositories sẽ hoàn tất trước tất cả services”. Nếu một bean service cần repository, hãy đặt constructor/factory method dependency. Nếu hai beans độc lập, không có ordering contract nghiệp vụ.

### Ví dụ đúng: ghép theo root, inject theo type

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {
    @Bean
    PurchaseRepository purchaseRepository() {
        return new InMemoryPurchaseRepository();
    }
}

@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    PurchaseService purchaseService(PurchaseRepository repository) {
        return new PurchaseService(repository);
    }
}

@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class RootConfig {
}
```

Đây là ví dụ minh họa, cần các Java classes/imports tương ứng. **Không phải** `ServiceConfig` phải constructor-inject `RepositoryConfig` rồi gọi `repositoryConfig.purchaseRepository()`; BeanFactory tự resolve `PurchaseRepository` đã được khai báo trong cùng context.

### XML imports cũng chỉ ghép metadata

```xml
<import resource="modules/services.xml"/>
<import resource="modules/repositories.xml"/>
```

Nếu `services.xml` chứa `<constructor-arg ref="purchaseRepository"/>`, Spring vẫn biết service cần repository. Thứ tự liệt kê files không biến thành thứ tự phải chạy business logic, và Spring không tạo hai BeanFactories tách biệt chỉ vì dùng hai XML.

## 6. `@DependsOn` thêm một cạnh vào đồ thị, không cấp object reference

Với constructor dependency, cạnh A→B nghĩa là A **cần instance B**. Với `@DependsOn("schemaValidator")` trên `reportService`, cạnh ấy chỉ có nghĩa BeanFactory phải **initialize schemaValidator trước reportService** dù reportService không nhận validator trong constructor:

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

Trong graph, hai dạng cạnh đều áp ràng buộc prerequisite → dependent khi tạo bean, nhưng chỉ **DI qua constructor/`@Bean` parameter** cấp collaborator object. Đừng dùng `@DependsOn` để lặp lại một dependency đã được biểu đạt rõ bằng parameter; dùng nó khi cần side effect khởi tạo riêng.

XML tương đương có `depends-on="schemaValidator"`; tên trong `@DependsOn` và XML là **bean name**, không phải tên Java class. Nếu dependent eager còn prerequisite `@Lazy`, cạnh này vẫn có thể làm prerequisite tạo trong refresh. Nếu hai bean có vòng A→B→A, đổi thứ tự `@Bean` methods hoặc thêm `@Order` không sửa được graph.

Ở đây vai trò của `@DependsOn` là **một dạng cạnh bổ sung khi suy ra partial order**. Bài riêng về `@DependsOn` đã giải thích metadata, nhiều prerequisites, XML/component scan và cách debug tên bean; bài này áp dụng chúng vào toàn bộ đồ thị dependency.

## 7. Destruction order: hướng ngược với initialization dependencies

Một thông tin dễ bỏ qua: `depends-on` không chỉ ảnh hưởng khởi tạo; với **singleton beans**, nó còn có thể chi phối **thứ tự hủy ngược**.

Giả sử A phụ thuộc B:

```text
Startup:
      B được initialize
      A được initialize

Shutdown:
      A được destroy
      B được destroy
```

Vì A có thể cần B để cleanup, container phải hủy A trước khi hủy B. Spring documentation xác nhận `depends-on` đối với singleton beans quy định dependent bean được destroy trước dependency.

### Ví dụ XML

```xml
<bean id="eventStore" class="example.EventStore"
      destroy-method="close"/>

<bean id="eventDispatcher" class="example.EventDispatcher"
      depends-on="eventStore"
      destroy-method="stop"/>
```

Nếu hai beans là managed singletons và context đóng bình thường, ordering relationship nhằm giữ `eventStore` sẵn trong lúc `eventDispatcher` shutdown.

### Giới hạn

- Ngữ nghĩa hủy phụ thuộc scope và lifecycle. Prototype beans không được BeanFactory quản lý toàn bộ destruction callbacks như singleton.
- Nếu chính destroy callback chạy I/O dài, bị treo hoặc lỗi, vẫn cần cơ chế quản lý tài nguyên, timeout và observability.
- Không dựa vào thứ tự destroy của hai beans hoàn toàn độc lập.
- Với custom scopes, proxy, parent-child contexts và external resources, phải kiểm tra hợp đồng lifecycle cụ thể.

**Đặc biệt:** `@DependsOn` hữu ích khi bạn thật sự cần thứ tự cả startup và cleanup của infrastructure beans; nhưng hãy nêu rõ lý do trong code review.

## 8. @Order KHÔNG điều khiển singleton startup order

Đây là lỗi hiểu phổ biến nhất trong chủ đề này.

`org.springframework.core.annotation.Order` dùng làm **ordering hint cho nhiều đối tượng/beans được sắp xếp**, ví dụ injection một `List<Handler>`, `Ordered` components, bean post-processors hoặc extension-point ordering theo hợp đồng. **Javadoc Spring ghi rõ giá trị @Order không quyết định thứ tự startup của singleton beans**; đó là một concern khác do dependency graph và `@DependsOn` ảnh hưởng.

Ví dụ:

```java
@Bean
@Order(20)
Notifier backupNotifier() {
    return new BasicNotifier("backup");
}

@Bean
@Order(10)
Notifier priorityNotifier() {
    return new BasicNotifier("priority");
}

@Bean
NotifierRegistry notifierRegistry(List<Notifier> notifiers) {
    return new NotifierRegistry(notifiers);
}
```

Nếu cả hai notifier beans được resolve vào `List<Notifier>`, Spring dùng `@Order` trên `@Bean` methods để sắp xếp **collection được inject**, nên `priority` đứng trước `backup`. Nhưng từ điều đó **không được suy ra** constructor của `priorityNotifier` đã chạy trước constructor của `backupNotifier`.

### @Order trên @Configuration class

Annotation `@Order` trên configuration classes có thể ảnh hưởng **thứ tự Spring đánh giá các configuration classes** trong pipeline tương ứng, nhưng không tự điều khiển thứ tự khởi tạo của mọi `@Bean` nằm bên trong chúng. Để ordering của beans, phải dựa trên dependency relations.

### @Primary không quyết định thứ tự tạo

`@Primary` giúp chọn bean khi injection point có nhiều candidates cùng type. Nó không có nghĩa bean primary sẽ luôn được construct trước bean khác.

### @Priority và Ordered cũng cần đọc đúng ngữ cảnh

`@Priority` và `Ordered` có thể ảnh hưởng việc lựa chọn/sắp xếp candidates trong các điểm mở rộng được thiết kế hỗ trợ chúng. Không coi các priority values là một lịch tạo tất cả singleton beans.

### Ví dụ đối chiếu

| Nhu cầu | Cơ chế đúng hơn |
| --- | --- |
| Service phải có repository khi xây constructor | Constructor injection / `@Bean` parameter |
| Client cần schema initializer được hoàn tất trước nhưng không giữ ref | `@DependsOn`/`depends-on` khi phù hợp |
| Pipeline nhận `List<Handler>` đúng thứ tự ưu tiên | `@Order`/`Ordered` hoặc ordering contract |
| Chọn một implementation mặc định trong nhiều candidates | `@Primary`/`@Qualifier` |
| Hoãn bean tốn kém cho tới first-use | `@Lazy`/`ObjectProvider` có chủ đích |
| Phối hợp start/stop listeners theo phase | `SmartLifecycle`/lifecycle coordinator |
| Chọn configuration classes nào được nạp | `@Import`/`ImportSelector` hoặc XML imports |

## 9. Thứ tự initialization và thứ tự *method execution* khác nhau

Giả sử `PaymentService` phụ thuộc `PaymentRepository`. Điều Spring bảo đảm là dependency được phân giải theo yêu cầu của bean creation, **không** phải tất cả những lời gọi method nghiệp vụ về sau đều có thứ tự cố định.

```java
PaymentService service = context.getBean(PaymentService.class);
service.pay(orderA);
service.pay(orderB);
```

Thứ tự hai lời gọi `pay` do **client code** điều phối, không được suy ra từ bean creation graph. Nếu có threads, events, reactive streams hoặc executors, runtime concurrency cần được thiết kế riêng.

### Constructor chạy xong chưa chắc bean đã initialized xong

Bean có thể còn trải qua:

- Dependency population/property injection.
- Aware callbacks.
- BeanPostProcessor hooks.
- `@PostConstruct`.
- `InitializingBean.afterPropertiesSet()`.
- Custom init methods.
- AOP proxy wrapping/exposure.

Với constructor injection, dependency được resolve trước constructor consumer. Với setter/field injection, constructor raw consumer có thể chạy trước injection rồi init callbacks mới diễn ra. Do đó “thứ tự khởi tạo” nên chỉ rõ bạn đang nói về **constructor start**, **constructor completion**, **property population** hay **bean fully initialized**.

## 10. Ví dụ hoàn chỉnh Java 17 + Spring Framework 6.2

Ví dụ runnable tập trung vào **những ràng buộc thứ tự thực sự**, không ép thứ tự giữa các beans độc lập.

Bốn cơ chế được chứng minh:

1. `Repository` là dependency trực tiếp của `OrderService`.
2. `AuditInitializer` không được truyền vào constructor service, nhưng `@DependsOn("auditInitializer")` buộc nó initialize trước service.
3. `OrderController` phụ thuộc service, nên service được initialize trước controller.
4. `OptionalReport` lazy không có eager consumer nên chưa được tạo lúc refresh.
5. Hai `AlertChannel` được sắp theo `@Order` **khi inject vào `List<AlertChannel>`**, không dùng ordering ấy để assert constructor startup sequence.

Tất cả output được tính bằng các **quan hệ chắc chắn đúng**, tránh in một startup log dựa vào thứ tự tạo các beans không liên quan.

### 10.1. Cây dự án

```text
bean-dependency-order/
├── pom.xml
└── src/main/java/
    └── demo/
        └── BeanOrderDemo.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-dependency-order</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. Mã Java đầy đủ

Tạo `src/main/java/demo/BeanOrderDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.annotation.Order;

public class BeanOrderDemo {

    public static final class Trace {
        private final List<String> events = new ArrayList<>();

        public void mark(String event) {
            events.add(event);
        }

        public boolean contains(String event) {
            return events.contains(event);
        }

        public boolean before(String first, String second) {
            int a = events.indexOf(first);
            int b = events.indexOf(second);
            return a >= 0 && b >= 0 && a < b;
        }
    }

    public interface Repository {
        String find(String sku);
    }

    public static final class MemoryRepository implements Repository {
        public MemoryRepository(Trace trace) {
            trace.mark("repository.ready");
        }

        @Override
        public String find(String sku) {
            return "item:" + sku;
        }
    }

    public static final class AuditInitializer {
        public AuditInitializer(Trace trace) {
            trace.mark("audit.ready");
        }
    }

    public static final class OrderService {
        private final Repository repository;

        public OrderService(Repository repository, Trace trace) {
            this.repository = repository;
            trace.mark("service.ready");
        }

        public Repository repository() {
            return repository;
        }

        public String order(String sku) {
            return repository.find(sku);
        }
    }

    public static final class OrderController {
        private final OrderService service;

        public OrderController(OrderService service, Trace trace) {
            this.service = service;
            trace.mark("controller.ready");
        }

        public String show(String sku) {
            return "view:" + service.order(sku);
        }
    }

    public static final class OptionalReport {
        public OptionalReport(Trace trace) {
            trace.mark("optional.ready");
        }
    }

    public interface AlertChannel {
        String label();
    }

    public static final class BasicAlertChannel implements AlertChannel {
        private final String value;

        public BasicAlertChannel(String value) {
            this.value = value;
        }

        @Override
        public String label() {
            return value;
        }
    }

    public static final class AlertCatalog {
        private final List<AlertChannel> channels;

        public AlertCatalog(List<AlertChannel> channels) {
            this.channels = List.copyOf(channels);
        }

        public String labels() {
            return String.join(",",
                    channels.stream().map(AlertChannel::label).toList());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public Repository repository(Trace trace) {
            return new MemoryRepository(trace);
        }

        @Bean
        public AuditInitializer auditInitializer(Trace trace) {
            return new AuditInitializer(trace);
        }

        @Bean
        @DependsOn("auditInitializer")
        public OrderService orderService(
                Repository repository, Trace trace) {
            return new OrderService(repository, trace);
        }

        @Bean
        public OrderController orderController(
                OrderService service, Trace trace) {
            return new OrderController(service, trace);
        }

        @Bean
        @Lazy
        public OptionalReport optionalReport(Trace trace) {
            return new OptionalReport(trace);
        }

        @Bean
        @Order(20)
        public AlertChannel backupAlertChannel() {
            return new BasicAlertChannel("backup");
        }

        @Bean
        @Order(10)
        public AlertChannel priorityAlertChannel() {
            return new BasicAlertChannel("priority");
        }

        @Bean
        public AlertCatalog alertCatalog(List<AlertChannel> channels) {
            return new AlertCatalog(channels);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Trace trace = context.getBean(Trace.class);
            OrderService service = context.getBean(OrderService.class);
            OrderController controller =
                    context.getBean(OrderController.class);
            AlertCatalog alerts = context.getBean(AlertCatalog.class);

            System.out.println("repository.before.service=" +
                    trace.before("repository.ready", "service.ready"));
            System.out.println("audit.before.service=" +
                    trace.before("audit.ready", "service.ready"));
            System.out.println("service.before.controller=" +
                    trace.before("service.ready", "controller.ready"));
            System.out.println("managed.repository.same=" +
                    (service.repository() == context.getBean(Repository.class)));
            System.out.println("controller=" +
                    controller.show("BK-7"));
            System.out.println("alerts=" + alerts.labels());
            System.out.println("optional.before.lookup=" +
                    trace.contains("optional.ready"));

            OptionalReport first =
                    context.getBean(OptionalReport.class);
            OptionalReport second =
                    context.getBean(OptionalReport.class);

            System.out.println("optional.after.lookup=" +
                    trace.contains("optional.ready"));
            System.out.println("optional.sameSingleton=" + (first == second));
        }
    }
}
```

### 10.4. Lệnh chạy

Cần Java 17+, Maven và dependencies trong cache hoặc truy cập Maven repository để tải lần đầu:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.BeanOrderDemo
```

### 10.5. Output dự kiến

Đây là các dòng **do chương trình in**, không tính các dòng Maven/Spring logs do môi trường cấu hình:

```text
repository.before.service=true
audit.before.service=true
service.before.controller=true
managed.repository.same=true
controller=view:item:BK-7
alerts=priority,backup
optional.before.lookup=false
optional.after.lookup=true
optional.sameSingleton=true
```

### 10.6. Giải thích output

**`repository.before.service=true`:** `orderService(Repository repository, Trace trace)` chỉ chạy khi Spring đã resolve repository singleton. `MemoryRepository` constructor đánh dấu `repository.ready` trước khi factory method tạo `OrderService` đánh dấu `service.ready`.

**`audit.before.service=true`:** `@DependsOn("auditInitializer")` bổ sung ordering edge, dù service constructor không nhận `AuditInitializer`. Spring phải tạo audit initializer trước order service.

**`service.before.controller=true`:** Controller yêu cầu `OrderService` ở factory method parameter. Spring hoàn tất tạo service trước khi factory method tạo controller đánh dấu `controller.ready`.

**`managed.repository.same=true`:** Service nhận managed Repository singleton qua BeanFactory resolution, không gọi trực tiếp `new MemoryRepository(...)` trong business code.

**`controller=view:item:BK-7`:** Controller sử dụng service và repository đã inject để tạo chuỗi. Thứ tự **sử dụng method runtime** do lời gọi `controller.show(...)` trong `main`, không phải do order annotations.

**`alerts=priority,backup`:** `@Order(10)` của `priorityAlertChannel` và `@Order(20)` của `backupAlertChannel` sắp xếp `List<AlertChannel>` injected vào `AlertCatalog`. Nó không chứng minh constructor priority channel chạy trước constructor backup channel.

**`optional.before.lookup=false`:** `OptionalReport` là lazy singleton, không có eager bean nào cần nó; constructor chưa đánh dấu sự kiện khi app refresh hoàn tất.

**`optional.after.lookup=true`:** Sau `context.getBean(OptionalReport.class)`, lazy bean được tạo và đánh dấu vào Trace.

**`optional.sameSingleton=true`:** Lazy không thay scope; hai tra cứu trong cùng context trả về cùng bean singleton.

### 10.7. Vì sao ví dụ không dựa vào thứ tự không được bảo đảm?

Ta không in toàn bộ `Trace.events` dưới dạng một thứ tự duy nhất. Nếu repository và audit initializer là hai prerequisites độc lập của service, không cần khẳng định ai được tạo trước ai. Hàm `trace.before(a,b)` chỉ kiểm tra những edges thực sự tồn tại. Đây là **phép kiểm đúng loại thuộc tính mà Spring cam kết**.

Chương trình cũng không dựa vào thứ tự các `@Bean` methods trong `AppConfig`, không cần component scan, không dùng static global mutable list, không có background threads và không gọi optional report trước khi đo laziness.

### 10.8. Tại sao @Configuration(proxyBeanMethods=false) vẫn đúng?

Tất cả dependencies trong demo được yêu cầu qua **tham số của `@Bean` methods**. Không có factory method nào gọi trực tiếp một `@Bean` method khác để tạo collaborator. Vì vậy không cần CGLIB interception của full configuration để bảo toàn singleton identity.

Nếu bạn đổi sang gọi `repository(trace())` như Java method trực tiếp trong `orderService()` khi `proxyBeanMethods=false`, bạn có thể tạo những Java objects ngoài BeanFactory và phá managed dependency identity. Đó không phải cách biểu diễn đồ thị dependencies.

## 11. Bài tập mở rộng project: minh họa @Order khác @DependsOn

Bạn có thể thử hai thay đổi riêng biệt để thấy chúng điều khiển những khía cạnh khác nhau.

### Thử A — Đảo @Order của các AlertChannel

Đổi:

```java
@Bean
@Order(5)
AlertChannel backupAlertChannel() {
    return new BasicAlertChannel("backup");
}

@Bean
@Order(50)
AlertChannel priorityAlertChannel() {
    return new BasicAlertChannel("priority");
}
```

Khi inject `List<AlertChannel>`, danh sách được sắp thành `backup,priority`. Nhưng **không** được suy luận Spring đã đảo construction order của hai singleton đó. Chỉ kiểm tra collection semantics.

### Thử B — Bỏ @DependsOn khỏi orderService

Bỏ:

```java
@DependsOn("auditInitializer")
```

Service vẫn có repository dependency, vì factory method nhận Repository. Nhưng **ràng buộc audit trước service không còn được khai báo**. Vì `auditInitializer` và `orderService` đều eager singletons độc lập ngoài các shared dependencies, startup có thể tình cờ vẫn đánh dấu audit trước service trong một build. **Không dùng một lần chạy như vậy để kết luận đảm bảo còn tồn tại.**

Test đúng là: khi bỏ annotation, **không còn hợp đồng** buộc audit initializer xong trước service. Nếu ứng dụng thực sự cần điều đó, giữ explicit dependency hoặc refactor để constructor service nhận collaborator cần thiết.

## 12. XML constructor-arg, property và depends-on

XML cũng xây dependency graph chung trong BeanFactory.

### Constructor dependency

```xml
<bean id="repository"
      class="example.InMemoryRepository"/>

<bean id="service"
      class="example.OrderService">
    <constructor-arg ref="repository"/>
</bean>

<bean id="controller"
      class="example.OrderController">
    <constructor-arg ref="service"/>
</bean>
```

Từ refs, có graph:

```text
controller -> service -> repository
```

Ngay cả khi ba `<bean>` được viết theo thứ tự controller, service, repository, Spring vẫn resolve refs để gọi constructors phù hợp. Các class ví dụ phải có constructor tương thích.

### Property dependency

```xml
<bean id="service" class="example.MutableService">
    <property name="repository" ref="repository"/>
</bean>
```

Spring tạo raw `MutableService` object rồi inject repository qua setter/property trước các init callbacks bình thường. Không nên hiểu rằng constructor của service nhất thiết chỉ bắt đầu **sau** constructor repository trong mọi setter injection scenario.

### Explicit depends-on

```xml
<bean id="eventStore" class="example.EventStore"/>

<bean id="dispatcher"
      class="example.Dispatcher"
      depends-on="eventStore"/>
```

Dù `Dispatcher` không có constructor/property reference đến `EventStore`, `depends-on` buộc store initialized trước dispatcher. Nếu singleton beans được destroy theo dependencies, dependent dispatcher được hủy trước event store.

### Một file XML hay nhiều file XML không làm đổi graph

`<import resource="repositories.xml"/>` và `<import resource="services.xml"/>` chỉ nhập bean definitions từ nhiều resources vào **cùng container**. Đồ thị DI vẫn thể hiện qua `ref` và explicit depends-on metadata. Không dựa vào vị trí imports làm thứ tự tạo tất cả beans trong từng file.

## 13. Dependency được tạo trước nhưng bean factory còn lifecycle

Khi nói “bean B phải được khởi tạo trước A”, có thể có nhiều dấu mốc:

- B constructor được gọi.
- B properties đã được populate.
- B đã chạy `@PostConstruct`.
- B đã chạy `InitializingBean.afterPropertiesSet()` hoặc custom init.
- B đã qua `BeanPostProcessor` và có thể được wrap thành proxy.
- A constructor/factory method nhận object phù hợp.
- A hoàn tất initialization.

### 13.1. Constructor injection và bean hoàn tất initialization

Với một non-circular constructor reference A(B), Spring thường resolve B thông qua BeanFactory trước khi có thể gọi constructor A. B được tạo và đi qua lifecycle thông thường để cung cấp reference phù hợp cho A.

### 13.2. Circular setter/field injection là trường hợp đặc biệt

Spring có thể hỗ trợ một số circular references bằng early singleton references khi được cấu hình cho phép. Trong những trường hợp đó, A có thể nhìn thấy reference tới bean B **đang trong quá trình tạo**, chưa hoàn toàn initialized. Vì vậy không thể phát biểu tuyệt đối rằng mọi dependency graph có cycle luôn có một topological initialization order.

### 13.3. BeanPostProcessor có thể trả proxy

A có thể nhận proxy cho B, không phải raw B object. Proxying không tự phá dependency contracts; nhưng các lazy-resolution proxies hoặc scoped proxies có thể trì hoãn việc tạo **target**. Hãy phân biệt “đã có proxy reference” với “target đã được construct”.

### 13.4. @PostConstruct không phải mốc mọi bean trong context đều xong

`@PostConstruct` của một bean được gọi trong lifecycle **của bean đó**. Nó không bảo đảm mọi bean không liên quan đã khởi tạo. Nếu callback cần nhìn thấy tất cả regular non-lazy singleton beans, xét `SmartInitializingSingleton` hoặc hook phù hợp thay vì dùng `@PostConstruct` ngẫu nhiên.

## 14. Circular dependencies và không tồn tại topological order

Nếu đồ thị có chu trình:

```text
A -> B -> C -> A
```

không có thứ tự nào thỏa cả “B trước A”, “C trước B” và “A trước C”. Đây là lý do constructor injection cycles thường dẫn đến lỗi creation như `BeanCurrentlyInCreationException` trong exception chain.

### 14.1. Ví dụ không giải được với constructors

```java
final class PaymentService {
    PaymentService(OrderService orders) {
    }
}

final class OrderService {
    OrderService(PaymentService payments) {
    }
}
```

Hai constructors yêu cầu bên kia đã tồn tại để tạo mình, không có điểm bắt đầu.

### 14.2. Đổi vị trí @Bean methods không sửa vòng

```java
@Bean
PaymentService paymentService(OrderService orders) {
    return new PaymentService(orders);
}

@Bean
OrderService orderService(PaymentService payments) {
    return new OrderService(payments);
}
```

Đảo hai methods không thay đổi graph A↔B.

### 14.3. @DependsOn vòng còn làm tình hình xấu hơn

```java
@Bean
@DependsOn("b")
A a() {
    return new A();
}

@Bean
@DependsOn("a")
B b() {
    return new B();
}
```

Nếu A phải được tạo sau B, B lại phải sau A, metadata ordering đã tự mâu thuẫn. Không khắc phục bằng cách thêm `@Order` vì `@Order` không phải startup ordering.

### 14.4. Cách refactor

Trước:

```text
OrderService <----> PaymentService
```

Sau:

```text
           CheckoutCoordinator
              /          \
             v            v
       OrderService    PaymentService
```

Hoặc trích `PaymentPolicy`/`SharedRules` để hai services phụ thuộc abstraction chung thay vì phụ thuộc ngược. Mục tiêu là dependency graph **không quay lại đỉnh đang được tạo**.

### 14.5. @Lazy và ObjectProvider có phá vòng không?

Một `@Lazy` injection point có thể cung cấp lazy-resolution proxy cho một cạnh và cho phép constructor tạo xong trong vài trường hợp. `ObjectProvider<T>` có thể trì hoãn lookup tới method khác. Nhưng quan hệ logic hai chiều vẫn có thể tồn tại và lỗi quay lại khi dereference quá sớm. Chúng **không thay thế** cho dependency inversion.

## 15. Scope ảnh hưởng khi nào các cạnh được thực thi

### Singleton không lazy

Bean singleton non-lazy thường được Spring `ApplicationContext` tạo trong refresh. Khi tạo một singleton eager, dependencies của nó được resolve. Đây là bối cảnh dễ thấy nhất cho startup ordering.

### Singleton lazy

```java
@Bean
@Lazy
ExpensiveRules expensiveRules() {
    return new ExpensiveRules();
}
```

Bean này có thể không xuất hiện trong pre-instantiation. Nhưng nếu eager consumer cần nó bằng constructor parameter, nó vẫn được tạo. Nếu chỉ được gọi qua provider/proxy lần đầu sau refresh, dependency creation xảy ra muộn hơn.

### Prototype

```java
@Bean
@Scope("prototype")
Worker worker() {
    return new Worker();
}
```

Bean prototype không được bulk pre-instantiated như singleton, nhưng có thể được tạo **trong startup** nếu eager singleton constructor cần một Worker để inject. Singleton giữ Worker đã inject; không tự nhận instance mới cho mỗi business invocation.

### Request/session scopes

Một scoped proxy có thể được inject vào singleton khi target request/session bean chưa tồn tại trong scope tương ứng. Dependency edge giữa singleton và **proxy** khác với việc khởi tạo target trong một request sau này. Đừng giả định request-scoped target phải hoàn tất lúc ApplicationContext refresh.

### @DependsOn với lazy và scope

`@DependsOn("x")` có thể làm một lazy singleton `x` được tạo sớm khi dependent eager singleton tạo. Còn cách destroy/shutdown bị chi phối bởi singleton lifecycle; không suy rộng nguyên vẹn sang prototype hoặc mọi custom scope.

## 16. SmartInitializingSingleton và thời điểm “sau các eager beans”

`org.springframework.beans.factory.SmartInitializingSingleton` có callback:

```java
@Override
public void afterSingletonsInstantiated() {
    // Logic ngắn sau pre-instantiation của regular non-lazy singletons.
}
```

Nếu một eager singleton thực thi interface này, callback chạy sau khi BeanFactory hoàn tất pre-instantiation các regular non-lazy singletons. Vì thế nó có thể phù hợp khi cần một bước khởi tạo sau các singletons thông thường, thay vì giả định thứ tự giữa những beans không có dependencies.

### Không phải tất cả beans đều đã tồn tại

- Lazy singleton chưa bị yêu cầu có thể chưa được tạo.
- Prototype bean chỉ tạo theo nhu cầu.
- Một số scoped targets cần request/session active.
- External services có thể chưa ready.
- Callback của lazy bean được tạo sau bootstrap thường không tự động được gọi muộn như một “hậu kiểm mọi singleton mới”.

### SmartInitializingSingleton khác SmartLifecycle

`SmartInitializingSingleton` phù hợp callback kết thúc pre-instantiation. `SmartLifecycle` hỗ trợ start/stop và phase ordering cho thành phần có lifecycle. Nếu application có consumer, listener, scheduler hay process dài hạn, dùng lifecycle abstraction phù hợp thay vì ép các bean constructors chạy theo lịch.

### ContextRefreshedEvent và Boot readiness

`ContextRefreshedEvent` được publish theo Spring Context refresh lifecycle sau những bước thích hợp; Spring Boot `ApplicationReadyEvent` ở một giai đoạn cao hơn của Boot startup. Không đồng nhất cả hai với “mọi dependency ngoài hệ thống đã healthy”.

## 17. @Order trong collection injection: hiểu đúng phạm vi

Giả sử một bean cần tất cả `Handler` implementations:

```java
@Bean
Pipeline pipeline(List<Handler> handlers) {
    return new Pipeline(handlers);
}
```

Spring có thể sắp `List<Handler>` dựa trên:

- `@Order` trên component classes.
- `@Order` trên `@Bean` methods.
- `Ordered` của object phù hợp.
- Các priority/ordering contracts khác tùy injection mechanism.

Nếu có:

```java
@Bean
@Order(50)
Handler standardHandler() {
    return new StandardHandler();
}

@Bean
@Order(5)
Handler urgentHandler() {
    return new UrgentHandler();
}
```

`Pipeline` thường nhận handlers theo thứ tự urgent trước standard. Nhưng câu đó chỉ nói về **vị trí các elements trong List**. Có thể Spring đã tạo standard bean trước, vì một dependency khác đòi nó sớm. Đừng kiểm thử `@Order` bằng constructor log order.

### Nếu cần stage execution ordering

Với `List<Handler>` đã được Spring sắp đúng, **Pipeline tự lặp List** để thực thi các stages. Đó mới là thứ tự thực thi nghiệp vụ có chủ đích. `@Order` không tự gọi methods của beans trong thứ tự nào cả.

## 18. Một bẫy khác: direct call giữa các @Bean methods

```java
@Configuration(proxyBeanMethods = false)
class UnsafeConfig {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

Với `proxyBeanMethods=false`, lời gọi `repository()` trong `service()` là **Java method call** bình thường, có thể tự tạo thêm Repository object khác ngoài managed bean `repository`. Khi đó bạn đã **bỏ qua** graph reference mà Spring cần biết.

Cách đúng:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository);
    }
}
```

Spring sẽ resolve và truyền managed Repository bean, từ đó có thể áp dụng ordering/dependency tracking/lifecycle đúng.

### Full @Configuration thì sao?

Với `@Configuration(proxyBeanMethods=true)` trong managed enhanced config, các inter-bean method calls có thể được CGLIB intercept để lấy Spring-managed bean. Nhưng việc coupling factory methods bằng direct calls vẫn khó refactor hơn method parameter injection. Trong lite mode hoặc gọi trên object `new Config()` tự tạo, CGLIB semantics không áp dụng như bạn mong đợi.

## 19. Background initialization trong Spring Framework 6.2

Spring Framework 6.2 bổ sung tùy chọn bootstrap background cho `@Bean` methods trong những trường hợp hỗ trợ, ví dụ `@Bean(bootstrap = Bean.Bootstrap.BACKGROUND)`.

Cơ chế này cho phép một số beans được khởi tạo nền trong startup thay vì mọi bean creation chạy tuần tự trên refresh thread. Đây là **lý do bổ sung để tránh suy luận thứ tự toàn phần** từ thứ tự lines trong source hoặc logs.

Những giới hạn khái niệm cần nhớ:

- Các dependency injection points không lazy cần instance thật **phải đợi** dependency đủ để sử dụng.
- Với background initialization, một số beans có thể bắt đầu construction song song khi không có dependency edge bắt buộc.
- BeanFactory/context orchestration vẫn cần đảm bảo contract startup tương ứng.
- Đừng assume mọi regular bean constructor chạy trên main thread.
- Các dependencies/proxies cần thread safety và lifecycle đúng.
- Khi background beans được truy cập từ `@PostConstruct` của bean khác hoặc từ custom infrastructure, phải xem semantics của bootstrap mode.

Ví dụ cú pháp minh họa:

```java
@Bean(bootstrap = Bean.Bootstrap.BACKGROUND)
RemoteMetadataClient remoteMetadataClient() {
    return new RemoteMetadataClient();
}
```

Trong Spring Framework, không phải cấu hình background nào cũng tự có executor phù hợp hoặc cho cùng kết quả trên mọi environment; cần đọc tài liệu/thiết lập phiên bản đúng trước khi áp dụng production. Ví dụ runnable chính **không bật background initialization**, nhằm giữ minh họa graph đơn giản.

**Điểm không thay đổi:** Tăng concurrency không xóa dependency edges; consumer không thể được dùng như đã hoàn tất nếu collaborator bắt buộc chưa sẵn sàng.

## 20. Cấu hình hạ tầng và early initialization

Một số beans không tuân một lịch khởi tạo ứng dụng đơn giản vì chúng tham gia **thiết lập chính BeanFactory**:

- `BeanDefinitionRegistryPostProcessor`.
- `BeanFactoryPostProcessor`.
- `BeanPostProcessor`.
- Các bean liên quan resource loading, proxies, property resolution.
- `FactoryBean` với product/factory semantics.

Những components này có thể được xử lý **trước pre-instantiation của regular application singletons**. Vì vậy không nên dùng chúng để “lấy mọi business bean sớm” bằng `getBean()`.

### BeanFactoryPostProcessor không phải nơi khởi tạo business graph

Một post-processor nên thao tác bean metadata theo hợp đồng. Gọi `getBean("billingService")` ở giai đoạn này có thể tạo billing service trước khi các BeanPostProcessors/AOP features đã đăng ký đầy đủ, gây cảnh báo “not eligible for processing” hoặc behavior khó đoán.

### Static @Bean dành cho infrastructure post-processors

Trong những tình huống Spring docs khuyến nghị, khai báo `static @Bean` khi định nghĩa `BeanFactoryPostProcessor` có thể tránh buộc `@Configuration` instance khởi tạo quá sớm. Đây là kỹ thuật lifecycle hạ tầng, không phải cách buộc hai business beans có ordering tùy ý.

### FactoryBean

Với `FactoryBean<T>`, có factory object và product bean. BeanFactory có thể cần inspect factory để xác định product type; một số factory/product có eager initialization semantics riêng. Vì vậy “definition registration order” và “product construction order” càng không nên bị coi là tương đương.

## 21. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Vì sao xảy ra? | Hướng xử lý |
| --- | --- | --- |
| Constructor B chạy trước A dù `@Bean a()` viết trước | A phụ thuộc B | Đây là expected DI behavior |
| Thứ tự startup đổi sau refactor | Một vài beans độc lập, không có ordering constraint | Không phụ thuộc thứ tự ngẫu nhiên; thêm dependency nếu thật sự cần |
| `@Order(1)` không làm bean khởi tạo trước | `@Order` không điều khiển singleton startup | Dùng dependency/`@DependsOn` theo đúng ý nghĩa |
| XML service khai báo trước repo nhưng vẫn chạy | `ref` trỏ repo; Spring resolve dependency | Đúng; đừng dùng XML line order để điều khiển |
| `@Import` thứ tự A,B khác startup beans | Import ghép config metadata, không phải startup schedule | Dùng `@Bean` method parameters |
| Bean `@Lazy` vẫn tạo trong refresh | Eager bean yêu cầu nó | Kiểm tra dependency graph |
| Bean prototype xuất hiện lúc startup | Eager singleton inject prototype | Không phải bulk prototype pre-instantiation |
| `@DependsOn` không truyền object vào constructor | Nó chỉ đặt ordering constraint | Dùng constructor param/ref cho instance dependency |
| Vòng `BeanCurrentlyInCreationException` | Constructor/metadata graph có cycle | Refactor dependency direction |
| Constructor của bean chạy trước setter dependency | Raw instance tạo trước property population | Đừng nhầm constructor-start với fully initialized |
| Handler order đúng nhưng constructor logs ngược | Collection sorting khác startup order | Test danh sách/selection, không test constructor order |
| Resource shutdown sớm hơn consumer | Thiếu/mô hình sai lifecycle dependency | Có explicit dependency và destroy callbacks phù hợp |
| `SmartInitializingSingleton` callback chạy khi lazy bean chưa tạo | Hook chỉ sau regular non-lazy pre-instantiation | Không giả định tất cả lazy/prototype beans đã có |
| Startup lâu vì dependency chain nặng | Eager bean kéo nhiều collaborators | Đo constructors/init, xem lazy/provider nếu phù hợp |
| Thời điểm khởi tạo khác trên prod | Profiles/conditions/scopes/post-processors/background bootstrap khác | Test đúng root context và runtime config |
| AOP không áp dụng với bean được tạo quá sớm | Bean bị khởi tạo trước BeanPostProcessor registration | Tránh early getBean trong infrastructure |
| @Bean trả duplicate object | Direct method call trong `proxyBeanMethods=false` | Dùng factory method parameter injection |
| @DependsOn tạo vòng mới | A depends B và B depends A | Bỏ cạnh ordering sai |
| Beans có cùng type gây ambiguity | Nhiều definitions sau import/scan | Qualifier/Primary đúng |
| Context refresh thành công nhưng external service lỗi | Instance initialized không chứng minh remote readiness | Health checks/timeout/retry và readiness policy |

### Quy trình điều tra

1. Xác định **bean name** đang báo lỗi và giai đoạn (definition parsing, creation, injection, initialization hay shutdown).
2. Tìm constructor và `@Bean` factory method signatures.
3. Vẽ tất cả dependency edges: constructor, property, `@Autowired`, refs, `@DependsOn`.
4. Xác định scope/lazy; tìm các eager beans kéo targets lên startup.
5. Tách các beans **có đường phụ thuộc** với **beans độc lập**.
6. Nếu có chu trình, tái cấu trúc graph thay vì đổi thứ tự khai báo.
7. Nếu chỉ cần sorting danh sách, dùng `@Order`/`Ordered` đúng điểm injection.
8. Xem sự khác nhau giữa constructor, init callback, SmartInitializingSingleton và lifecycle startup.
9. Với framework 6.2 background init/AOP/FactoryBean, xem các cơ chế exception và thread semantics.
10. Viết integration test dựa trên **ràng buộc phải giữ**; không assert toàn bộ log order.

## 22. Kiểm thử thứ tự bằng assertions đúng hợp đồng

Trong ví dụ mục 10, thay vì kiểm tra `Trace.events` chính xác là `[repository, audit, service, controller]`, ta kiểm tra các bất đẳng thức:

```java
if (!trace.before("repository.ready", "service.ready")) {
    throw new AssertionError("Repository must precede service");
}
if (!trace.before("audit.ready", "service.ready")) {
    throw new AssertionError("Audit must precede service");
}
if (!trace.before("service.ready", "controller.ready")) {
    throw new AssertionError("Service must precede controller");
}
```

Đây là các dòng **bổ sung bên trong `main` sau khi context được tạo**, dùng `Trace` từ project ví dụ. Chúng kiểm tra edges bắt buộc nhưng không áp đặt thứ tự giữa repository và audit.

### Nếu test muốn chắc chắn có bean definition

Có thể kiểm tra:

```java
boolean exists =
        context.getBeanFactory().containsBeanDefinition("orderService");
```

Đây là kiểm tra metadata. Nó không chứng minh orderService đã được tạo nếu bean lazy hoặc registration theo cơ chế khác.

### Kiểm tra singleton đã được tạo mà không gây creation

```java
boolean created =
        context.getBeanFactory().containsSingleton("optionalReport");
```

Với lazy `optionalReport` chưa bị yêu cầu, kết quả thường false. **Không gọi `getBean("optionalReport")` trước khi kiểm tra** nếu mục tiêu đo trạng thái trước first use.

### Kiểm tra lifecycle destruction

Nếu service và repository giữ resources, thêm destroy callbacks ghi marker rồi đóng ApplicationContext; assert rằng consumer được destroy trước dependency trong trường hợp dependency đã được đăng ký phù hợp. Không dùng direct `new` ngoài container trong test lifetime semantics.

### Vì sao không kiểm tra đúng toàn bộ thứ tự?

BeanFactory có thể thay đổi registration order, thêm infrastructure beans, thay đổi background initialization, refactor config hoặc beans độc lập được tạo theo thứ tự khác. Một test ép toàn bộ chuỗi constructor logs thường **flaky** và không kiểm chứng yêu cầu nghiệp vụ thực.

## 23. Bài tập có đáp án

### Bài 1 — Vẽ đồ thị

A nhận B và C trong constructor; B nhận D; C độc lập với D. Vẽ dependency graph và nêu constraints.

**Đáp án:**

```text
      A
     / \
    v   v
    B   C
    |
    v
    D
```

D cần được tạo/giải quyết trước B, B và C trước khi A constructor được gọi với references thích hợp. Không có ràng buộc trực tiếp về thứ tự C và D.

### Bài 2 — Hai thứ tự hợp lệ

Với graph ở bài 1, liệt kê hai linearizations hợp lệ.

**Đáp án:** `D,B,C,A` và `C,D,B,A` đều thỏa constraints. Đây là những thứ tự toán học có thể xảy ra, không phải cam kết Spring sẽ chọn chúng.

### Bài 3 — Đảo thứ tự @Bean

Factory method `@Bean Controller controller(Service s)` nằm trước `@Bean Service service(Repository r)` trong Java. Có làm Spring tạo Controller trước Service không?

**Đáp án:** Không, Spring phải resolve tham số `Service` trước khi gọi method factory tạo controller.

### Bài 4 — XML ref

`<bean id="service">` nằm trước `<bean id="repo">` trong XML, nhưng service constructor-arg `ref="repo"`. Có cần đổi thứ tự file để chạy?

**Đáp án:** Không. BeanFactory có thể resolve repo từ definitions đã đăng ký, independent of thẻ khai báo đứng trước/sau trong file.

### Bài 5 — @Order

Hai bean `Handler` có `@Order(1)` và `@Order(20)`. Có phải bean order 1 chắc chắn construct trước?

**Đáp án:** Không. `@Order` ảnh hưởng sorting trong những điểm hỗ trợ như `List<Handler>` injection, không bảo đảm singleton startup order.

### Bài 6 — @DependsOn

Bean `ReportService` không nhận `SchemaValidator` reference nhưng phải khởi tạo sau khi validator xong. Viết annotation.

**Đáp án:**

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

Tên `schemaValidator` phải khớp bean name thực sự.

### Bài 7 — Destruction

Nếu A singleton `depends-on="b"` và cả hai có destroy callbacks, ai thường được hủy trước?

**Đáp án:** A (dependent) được destroy trước B (dependency), để B còn sẵn trong quá trình A cleanup.

### Bài 8 — Lazy dependency

A eager singleton constructor cần B lazy singleton. Khi Spring refresh, B có thể được tạo không?

**Đáp án:** Có, thường là cần; A không thể hoàn thành constructor nếu thiếu B instance.

### Bài 9 — @DependsOn và lazy

A eager có `@DependsOn("b")`, B lazy. B có thể bị khởi tạo trước A không?

**Đáp án:** Có. Explicit ordering là một nguyên nhân dependency-driven creation, dù B lazy.

### Bài 10 — Setter injection

`new Consumer()` constructor chạy trước khi BeanFactory gọi `setRepository(...)`. Có vi phạm câu “dependency trước consumer” không?

**Đáp án:** Không. Với setter injection, raw object consumer có thể đã được construct; Spring resolve dependency để **populate property trước khi bean hoàn tất normal initialization**. Cần nói rõ mốc nào được so.

### Bài 11 — Multiple @Import

`@Import({ServiceConfig.class, RepoConfig.class})`, service factory nhận `Repository`. Có cần đảo thành RepoConfig trước không?

**Đáp án:** Không vì DI dependency graph mới quyết định Repo phải được resolve trước Service khi service creation cần repo.

### Bài 12 — Prototype

A eager singleton constructor nhận B prototype. B có thể được tạo trong startup không? A nhận B mới mỗi method call?

**Đáp án:** B được tạo để inject vào A khi A xây. A thường giữ instance đã nhận, không tự đổi mỗi call; dùng provider nếu cần prototype per-operation.

### Bài 13 — Vòng

A constructor cần B, B constructor cần C, C constructor cần A. Đảo thứ tự khai báo có giúp không?

**Đáp án:** Không. Directed cycle không có topological order hợp lệ; cần chỉnh kiến trúc/refactor dependency direction.

### Bài 14 — SmartInitializingSingleton

Callback `afterSingletonsInstantiated` có nghĩa mọi lazy bean đã tạo không?

**Đáp án:** Không. Nó gắn với cuối regular non-lazy singleton pre-instantiation; lazy bean không bị yêu cầu vẫn có thể chưa được tạo.

### Bài 15 — Method call runtime

Spring tạo A trước B theo một dependency edge. Có nghĩa khi request đến B luôn chạy business method sau A không?

**Đáp án:** Không. Runtime method execution do caller, threads, events và orchestration quyết định, không phải bean initialization ordering.

### Bài 16 — Dự đoán output ví dụ

Tại sao `repository.before.service` và `audit.before.service` đều true nhưng không assert `repository.before.audit`?

**Đáp án:** Repo là constructor dependency của service, audit là `@DependsOn` dependency của service. Giữa repo và audit không có edge buộc thứ tự tương đối.

### Bài 17 — Thay @Order

Nếu đổi `@Order(10)`/`@Order(20)` cho các `AlertChannel`, chuyện gì thay đổi rõ nhất?

**Đáp án:** Thứ tự các elements trong `List<AlertChannel>` mà `AlertCatalog` nhận. Không suy ra constructor startup order đổi.

### Bài 18 — One-direction design

Ứng dụng có `RepositoryService` và `BillingService` cần nhau ở constructors. Đề xuất refactor.

**Đáp án định hướng:** Xác định ai thực sự sở hữu business orchestration; đưa việc phối hợp vào bean thứ ba hoặc trích abstraction/policy chung. Giữ tầng repository không phụ thuộc ngược vào application service, làm dependency graph đi một chiều.

### Bài 19 — Test một phần thay vì toàn bộ order

Giả sử log startup tình cờ in `audit, repo, service, controller`. Khi refactor framework nó in `repo, audit, service, controller`. Có nên coi là regression?

**Đáp án:** Không nếu contract chỉ là audit trước service, repo trước service và service trước controller. Hai chuỗi đều hợp lệ.

### Bài 20 — @Bean bootstrap BACKGROUND

Nếu B được tạo trên background thread trong Spring Framework 6.2 và A constructor cần B thật, có được đưa A vào trạng thái initialized hoàn chỉnh trước khi B sẵn sàng không?

**Đáp án:** Không đối với non-lazy dependency instance bắt buộc theo hợp đồng; container cần chờ/resolve B phù hợp. Nhưng các independent beans có thể tiến hành đồng thời, nên càng không được assert một global constructor order.

## 24. Checklist review cấu hình Spring

- [ ] Đã vẽ các dependency edges thật từ constructors, setters, fields và factory method params.
- [ ] Có phân biệt bean definition registration order với instance creation order.
- [ ] Hiểu Spring bảo đảm constraints, không nhất thiết một global total order.
- [ ] Không đặt nghiệp vụ phụ thuộc vào thứ tự hai singleton độc lập được khởi tạo.
- [ ] `@Bean` methods dùng parameters để nhận collaborators thay vì direct-call trong lite mode.
- [ ] `@Import`/XML imports chỉ ghép definitions, không thay dependency graph.
- [ ] `@DependsOn` có reason rõ và bean names chính xác.
- [ ] Không thêm `@DependsOn` chỉ để lặp constructor dependencies.
- [ ] Có hiểu `@DependsOn` còn ảnh hưởng singleton destruction order.
- [ ] Không dùng `@Order` như điều khiển startup; chỉ sorting/selection đúng contract.
- [ ] Dependency graph không có constructor cycle.
- [ ] Eager/lazy settings phù hợp dependency chain và startup goals.
- [ ] Một lazy bean được eager consumer yêu cầu có thể vẫn bị tạo sớm.
- [ ] Setter/field injection được hiểu là population lifecycle, không nhầm constructor order.
- [ ] Scoped/lazy proxies và ObjectProvider được xem là deferred target resolution nếu thật sự dùng.
- [ ] Startup hooks/`SmartInitializingSingleton` không bị nhầm với runtime readiness.
- [ ] `SmartLifecycle` được dùng khi cần start/stop theo phase.
- [ ] BeanFactory post-processors không tùy tiện gọi business beans sớm.
- [ ] Nếu bật background bootstrap 6.2, đã xét concurrency và dependency waiting.
- [ ] Test assert từng edge bắt buộc, không assert order giữa node độc lập.
- [ ] Test startup, first-use lazy, destroy callbacks và cấu hình theo profile nếu quan trọng.
- [ ] Không dùng `getBean` để kiểm tra một lazy bean đã tạo chưa nếu không muốn gây creation.
- [ ] Không đưa business side effects nặng vào constructors chỉ để ép ordering.
- [ ] Startup health/readiness được thiết kế riêng với BeanFactory creation.

## Kết luận

**Thứ tự khởi tạo bean trong Spring xuất phát từ đồ thị phụ thuộc**, theo nghĩa container resolve những collaborators mà một bean cần để hoàn thành việc tạo và initialization. `@DependsOn` có thể thêm ordering edges cho những phụ thuộc không thể hiện qua constructor/property reference. Kết quả là một **thứ tự từng phần**: các dependency constraints được đảm bảo, còn thứ tự giữa các bean độc lập **không nên được coi là hợp đồng**.

Đặc biệt:

- `@Bean` declaration order, `@Import` order và XML source order **không thay thế dependency edges**.
- `@Order` điều khiển những ordering semantics như injected collections, **không** điều khiển singleton startup order.
- `@Lazy` và scope tác động *khi nào* target được cần; eager dependency vẫn có thể tạo lazy bean.
- Một cycle constructor A→B→A không thể sửa bằng việc đổi thứ tự khai báo.
- Cleanup singleton thường theo hướng ngược với dependency cần giữ; explicit `depends-on` có thể ảnh hưởng destruction order.

Hãy dùng constructor/factory method parameter injection để mô tả dependency thực, `@DependsOn` khi thật sự cần implicit initialization ordering, và lifecycle coordinator khi yêu cầu là **startup/shutdown workflow** chứ không chỉ tạo object. Khi kiểm thử, kiểm chứng các **ràng buộc bắt buộc** thay vì một chuỗi constructor logs tình cờ.

## Tài liệu chính thức

- [Spring Framework — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): initialization order, XML `depends-on`, destruction order của singleton.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): pre-instantiation, lazy dependency bị eager singleton yêu cầu.
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property dependency resolution.
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): `@Order`/`Ordered` tại injection collections khác với singleton startup order.
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, `@Bean` wiring, `@DependsOn` và Spring 6.2 background initialization.
- [Spring Framework 6.2 — @Order API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html): ordering priority vs singleton startup.
- [Spring Framework 6.2 — @DependsOn API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DependsOn.html): bean names và initialization/destruction order.
- [Spring Framework 6.2 — SmartInitializingSingleton API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback sau regular singleton pre-instantiation.
