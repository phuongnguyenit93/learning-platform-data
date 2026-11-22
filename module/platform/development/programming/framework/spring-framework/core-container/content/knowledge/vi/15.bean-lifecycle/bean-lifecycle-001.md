# Vòng đời bean Spring: các bước tạo đối tượng, tiêm phụ thuộc và khởi tạo

## 1. Mục tiêu và bức tranh tổng thể

Spring Core Container quản lý các đối tượng được khai báo thành **bean**: container biết cách tạo chúng, xác định những phụ thuộc cần cung cấp, thực hiện cấu hình, gọi các callback khởi tạo và (với những scope thích hợp) dọn dẹp khi kết thúc vòng đời.

Cần tách ba hoạt động rất dễ bị gọi chung là “khởi tạo”:

1. **Instantiation — tạo đối tượng:** tạo instance Java bằng constructor, factory method hoặc một cơ chế instantiation phù hợp.
2. **Dependency injection / property population — tiêm phụ thuộc và điền thuộc tính:** gắn những bean/value mà instance cần để hoạt động, thông qua constructor/factory method, setter, field hoặc property binding tùy cấu hình.
3. **Initialization — khởi tạo bean sau khi có dependency:** các bước Spring gọi sau khi điền dependency để kiểm tra cấu hình, chuẩn bị cấu trúc dữ liệu hoặc thực hiện callback như `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom `initMethod`.

Một bean **đã được Java tạo bằng constructor** chưa chắc đã **hoàn tất việc khởi tạo trong Spring**. Bean thường chỉ sẵn sàng cho code ứng dụng sử dụng sau khi Spring chạy xong các bước tạo, tiêm, callback và bean post-processing cần thiết.

Đây là quy trình **điển hình** cho bean thông thường; Spring có các điểm mở rộng như `FactoryBean`, `InstantiationAwareBeanPostProcessor`, proxy và custom scope có thể thay đổi một số thao tác cụ thể. Đừng xem sơ đồ rút gọn là một danh sách nội bộ bất biến cho mọi loại bean.

~~~text
Bean definition và metadata
          │
          ▼
Container xác định cần tạo bean
          │
          ▼
Giải quyết dependency dùng cho constructor/factory method
          │
          ▼
Tạo instance (constructor / factory method)
          │
          ▼
Tiêm dependency còn lại (field, setter, properties ...)
          │
          ▼
Các *Aware callback và xử lý tiền khởi tạo
          │
          ▼
@PostConstruct
          │
          ▼
InitializingBean.afterPropertiesSet()
          │
          ▼
Custom init method (nếu khai báo)
          │
          ▼
BeanPostProcessor sau khởi tạo (có thể trả proxy)
          │
          ▼
Bean đã sẵn sàng để ứng dụng lấy và sử dụng
          │
          ▼
Khi scope/container kết thúc: destroy callbacks, nếu được quản lý
~~~

**Điểm tinh tế:** `@PostConstruct` được xử lý bởi một `BeanPostProcessor` của Spring, vì vậy nó xảy ra **trong pha các post-processor trước khởi tạo**. Các custom `postProcessBeforeInitialization()` có thứ tự riêng; không nên khẳng định tất cả custom “before” callback luôn xảy ra trước `@PostConstruct`. Sơ đồ đặt `@PostConstruct` ở đúng vị trí tương đối với `afterPropertiesSet()` và custom init method, nhưng lược bỏ thứ tự giữa nhiều post-processor khác nhau.

## 2. Spring lấy thông tin để tạo bean ở đâu?

Spring không tự quản lý tất cả object trong JVM. Nó chỉ quản lý những bean được đăng ký qua bean definition hoặc cơ chế tương đương.

Một vài cách đăng ký thường gặp:

~~~java
@Component
class OrderRepository {
}

@Service
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Khi package được `@ComponentScan` quét và đăng ký, container có metadata để tạo `OrderRepository` và `OrderService`.

Cách cấu hình Java:

~~~java
@Configuration
class ShopConfig {
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

Các đoạn cấu hình ngắn ở trên là **minh họa**, không phải một chương trình Java standalone với đủ import và `main`; mã hoàn chỉnh có thể chạy nằm ở mục 7.

Các nguồn bean definition thường gặp gồm `@Component`/`@Service`/`@Repository`, các phương thức `@Bean`, cấu hình XML, đăng ký bean qua API hoặc thông qua framework tích hợp. Metadata có thể bao gồm bean name, class/factory, scope, constructor arguments, property values, lazy flag, điều kiện đăng ký, init/destroy methods và quan hệ phụ thuộc.

Ở giai đoạn `ApplicationContext.refresh()`, Spring xử lý metadata, áp dụng các `BeanFactoryPostProcessor`/**BeanDefinitionRegistryPostProcessor**, đăng ký `BeanPostProcessor`, rồi **thông thường pre-instantiate các singleton không lazy**. Vì thế khi một `AnnotationConfigApplicationContext` vừa được tạo, nhiều singleton có thể đã đi qua đủ lifecycle, dù ứng dụng chưa gọi `getBean()` lần nào.

Không nhầm:

- `BeanFactoryPostProcessor` tác động tới **bean definitions/container configuration trước khi phần lớn bean thông thường được khởi tạo**.
- `BeanPostProcessor` tác động tới **mỗi bean instance** trong các thời điểm thích hợp của quá trình tạo/khởi tạo.

Nếu bean không được đăng ký thành Spring bean, câu lệnh `new OrderService(...)` do ứng dụng tự gọi là tạo object Java bình thường; Spring không tự chạy dependency injection, callback hay proxy cho object đó.

## 3. Bước tạo đối tượng (instantiation)

### 3.1. Chọn constructor hoặc factory method

Spring trước tiên phải xác định cách có được instance.

- Với component class, Spring có thể gọi constructor của class sau khi resolve các constructor arguments.
- Với phương thức `@Bean`, Spring gọi factory method tương ứng; instance do method trả về trở thành bean được quản lý và tiếp tục trải qua các bước wiring/lifecycle.
- Với bean definition chuyên biệt hoặc `FactoryBean`, quy trình tạo object có thể khác; nên phân biệt **đối tượng factory** với **sản phẩm do factory cung cấp**.
- `InstantiationAwareBeanPostProcessor` có thể tham gia trước/sau khi tạo instance, thậm chí tạo proxy thay thế trong một số trường hợp.

Khi dùng constructor injection:

~~~java
@Service
class InvoiceService {
    private final InvoiceRepository repository;

    InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

Spring **phải tìm/chuẩn bị được `InvoiceRepository` trước khi gọi constructor `InvoiceService`**, bởi constructor cần argument đó. Với class chỉ có một constructor, Spring hiện đại có thể tự dùng constructor ấy mà không cần `@Autowired` trên constructor. Nếu class có nhiều constructor, việc chọn constructor phụ thuộc annotation và các quy tắc constructor resolution.

Tại thời điểm bắt đầu chạy body constructor, các argument đã được truyền vào, nhưng **field hoặc setter injection của chính bean đó có thể chưa diễn ra**. Đặc biệt, `@PostConstruct` vẫn chưa chạy, nên không được giả định đối tượng đã hoàn toàn initialized.

### 3.2. Phân biệt ba cấp “đối tượng đã có”

~~~text
Constructor được gọi        → Object Java đã được tạo
Dependency được điền        → Object đã có các tham chiếu/cấu hình
Init callbacks hoàn tất     → Bean đã được Spring khởi tạo xong
Post-processing hoàn tất    → Object Spring công bố cho người dùng có thể là proxy
~~~

Đây là lý do không nên cho `this` thoát ra khỏi constructor sang một thread khác, đăng ký callback bất đồng bộ giữ reference chưa hoàn thành, hoặc đưa instance vào một static registry khi container còn đang wiring. Người khác có thể dùng nó trước khi dependency/callback hoàn tất.

### 3.3. Constructor/factory method thất bại thì sao?

Nếu constructor ném exception hoặc dependency bắt buộc chưa tìm được, Spring không thể hoàn tất quá trình tạo bean. Ứng dụng có thể nhận `BeanCreationException` với nguyên nhân sâu hơn là `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException` hoặc exception do chính code nghiệp vụ ném ra. Khi singleton eager cần thiết không tạo được, quá trình refresh context thường thất bại.

## 4. Bước tiêm phụ thuộc (dependency injection)

Mục tiêu của DI là **cung cấp collaborator và configuration từ container**, thay vì để mỗi bean tự tạo/tra cứu những dependency đó. Spring chọn dependency theo type, bean name, qualifier, primary designation và các quy tắc autowiring liên quan.

### 4.1. Constructor injection

~~~java
@Service
class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Ưu điểm: dependency bắt buộc được nêu rõ; có thể khai báo `final`; dễ test bằng cách tự truyền fake/stub; giảm nguy cơ object tồn tại ở trạng thái chưa đủ dependency. Với dependency không thể thiếu, **constructor injection thường là lựa chọn ưu tiên**.

Thời điểm: Spring phải resolve dependency **trước** khi gọi constructor. Nếu các dependency là singleton, container thường lấy lại singleton hiện có hoặc tạo chúng trước. Nếu dependency là prototype, mỗi lần giải quyết bean prototype cho một yêu cầu sẽ cấp một instance phù hợp với scope ấy; injection một lần vào singleton vẫn giữ reference đó, không tự thay ở từng method call.

### 4.2. Setter injection

~~~java
@Component
class NotificationService {
    private EmailClient client;

    @Autowired
    public void setClient(EmailClient client) {
        this.client = client;
    }
}
~~~

Spring tạo `NotificationService` trước, rồi trong bước property population, cơ chế autowiring gọi setter với bean `EmailClient` đã resolve. Khi chạy setter, object đã tồn tại nhưng **chưa đến pha init hoàn chỉnh**.

Setter injection phù hợp với một số dependency cấu hình được hoặc khi cần khả năng thay đổi dependency, nhưng phải kiểm tra invariants: code dùng bean trước khi setter chạy có thể thấy field chưa có giá trị. Nếu không dùng constructor injection, `@PostConstruct` là vị trí hợp lý để xác nhận đã nhận đủ dependency bắt buộc.

### 4.3. Field injection

~~~java
@Component
class MailWorker {
    @Autowired
    private EmailClient emailClient;
}
~~~

Spring dùng post-processor như `AutowiredAnnotationBeanPostProcessor` để điền field sau khi tạo instance. Cách này ít code, nhưng làm dependency bớt rõ ràng, khó tạo object thuần trong unit test và không phù hợp để đảm bảo `final` dependency bằng constructor. Nên cân nhắc constructor injection trong code ứng dụng.

### 4.4. Injection của `@Bean` factory method

~~~java
@Bean
ReportService reportService(ReportRepository repository,
                            Clock clock) {
    return new ReportService(repository, clock);
}
~~~

Trong đoạn này, `repository` và `clock` là **tham số factory method**, Spring resolve chúng trước khi gọi method. Chúng tương tự constructor injection về điều kiện “có dependency trước khi tạo instance” nhưng hành động thực tế là gọi một phương thức factory để trả về object.

Không trộn lẫn hai khái niệm: tự gọi `new Config().reportService(...)` là code Java bình thường; Spring chỉ quản lý bean khi chính container tham gia thực thi bean definition.

### 4.5. Optional, collection, qualifier

Nếu có nhiều bean cùng interface, autowiring chỉ theo type có thể mơ hồ. Dùng `@Qualifier("beanName")`, `@Primary` hoặc tên tham số (khi metadata hỗ trợ) để làm rõ. Thiếu bean bắt buộc gây lỗi khởi tạo; với dependency thực sự optional có thể dùng `Optional<T>` hay `ObjectProvider<T>`. Với tập hợp nhiều bean, Spring hỗ trợ inject `List<T>`/`Map<String,T>` theo quy tắc tương ứng.

`ObjectProvider<T>` cho phép **lùi thời điểm resolve** dependency đến lúc gọi `getObject()`. Việc tiêm provider thành công chưa đảm bảo target mà provider sẽ yêu cầu sau này tồn tại trong mọi scope context; ví dụ request-scoped bean có thể không lấy được khi không có HTTP request đang hoạt động.

## 5. Các callback giữa DI và khởi tạo

Sau khi đã tạo bean và hoàn tất property population, Spring đưa bean qua các lifecycle extension points. Ba nhóm cần phân biệt:

| Điểm mở rộng | Vai trò và giới hạn |
| --- | --- |
| `BeanNameAware`, `BeanFactoryAware`, `ApplicationContextAware` | Cho bean nhận thông tin container khi cần; một số callback được xử lý qua infrastructure processor |
| `BeanPostProcessor.postProcessBeforeInitialization` | Quan sát/chỉnh bean trước các init callback chuẩn; `@PostConstruct` cũng do một processor quản lý |
| `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom `initMethod` | Khởi tạo state của **chính bean**, theo thứ tự này nếu ba callback là ba phương thức riêng |
| `BeanPostProcessor.postProcessAfterInitialization` | Có thể trả lại bean ban đầu hoặc một wrapper/proxy |

Ví dụ, bean muốn biết bean name có thể implement `BeanNameAware.setBeanName(String)`. Với Spring 6+, `@PostConstruct` dùng `jakarta.annotation.PostConstruct` và cần infrastructure xử lý annotation. Nó diễn ra trong pha before-initialization, nên không thể khẳng định **mọi custom** `postProcessBeforeInitialization` đều chạy trước `@PostConstruct`; thứ tự của những processor cụ thể có thể khác nhau.

`@Primary`, qualifier, scope và tên bean không tự quyết định thứ tự init methods trong **một bean**. Các callback nên xác thực cấu hình hoặc xây dựng state nhỏ gọn; tránh biến chúng thành nơi gọi `getBean()` tùy ý hay tác vụ nghiệp vụ dài. Sau bước after-initialization, tham chiếu Spring trả về có thể là proxy khác với raw target. Bài `BeanPostProcessor` trình bày sâu về thứ tự processor và proxy; bài về kết hợp callback có demo trace riêng.

## 6. Khi nào bean được xem là sẵn sàng?

Với bean thông thường, sau khi container hoàn tất initialization và post-processing, instance được trả cho người yêu cầu và/hoặc cache theo scope phù hợp. Những bean singleton không lazy thường đã sẵn sàng khi `ApplicationContext.refresh()` hoàn tất.

Ví dụ về thời điểm:

~~~text
T0: load bean definitions
T1: đăng ký BeanPostProcessor
T2: tạo singleton dependency D
T3: tạo singleton service S, resolve/inject D
T4: chạy init callbacks của S
T5: hoàn tất post-processing, có thể tạo proxy của S
T6: ApplicationContext.refresh() hoàn tất
T7: application code gọi getBean(S.class), lấy bean/proxy đã có
~~~

Với `@Lazy` singleton, quá trình tạo có thể chuyển đến lần đầu thực sự cần bean (nhưng có thể vẫn phải tạo sớm nếu một singleton eager khác phụ thuộc vào nó mà không có lazy proxy). Với `prototype`, quá trình tạo/DI/khởi tạo diễn ra **mỗi lần container phải tạo một prototype target mới**. Để dùng prototype theo từng lần thao tác trong singleton, cần `ObjectProvider` hoặc lookup tương tự.

**Sẵn sàng của từng bean không đồng nghĩa toàn ứng dụng đã sẵn sàng nhận lưu lượng**. Công việc phải chờ **tất cả singleton** đã được tạo có thể đặt tại `SmartInitializingSingleton.afterSingletonsInstantiated()`. Công việc cần toàn context refresh xong có thể phản ứng `ContextRefreshedEvent`; tác vụ có startup/shutdown lifecycle riêng có thể dùng `SmartLifecycle`.

Đặc biệt, không nên dùng `@PostConstruct` để khởi chạy công việc blocking dài hoặc thao tác phức tạp truy cập bean khác có nguy cơ deadlock trong lúc container giữ singleton creation lock. Hook này nên ngắn, chắc chắn, chủ yếu kiểm tra trạng thái/chuẩn bị dữ liệu cục bộ.

## 7. Ví dụ Java 17 chạy được: constructor → setter DI → init callbacks

Ví dụ dùng **Java 17**, **Maven** và **Spring Framework 6.2.19**. Nó tạo bean bằng Java configuration, inject dependency qua constructor/factory method và setter, sau đó chạy các callback theo thứ tự. Thêm phần hủy để nhìn thấy ranh giới lifecycle khi đóng context.

Cấu trúc tệp:

~~~text
spring-bean-lifecycle/
├── pom.xml
└── src/main/java/example/BeanLifecycleDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-bean-lifecycle</artifactId>
    <version>1.0.0</version>

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
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
~~~

Tệp `src/main/java/example/BeanLifecycleDemo.java`:

~~~java
package example;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanLifecycleDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ManagedJob job = context.getBean(ManagedJob.class);
            job.execute();
        } // context.close(): Spring hủy các singleton đủ điều kiện.
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Repository repository() {
            return new Repository("orders");
        }

        @Bean
        public Validator validator() {
            return new Validator();
        }

        @Bean(initMethod = "customInit",
              destroyMethod = "customDestroy")
        public ManagedJob managedJob(Repository repository) {
            return new ManagedJob(repository);
        }
    }

    public static final class Repository {
        private final String name;

        public Repository(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static final class Validator {
        public boolean accept(Repository repository) {
            return repository != null && !repository.name().isBlank();
        }
    }

    public static class ManagedJob
            implements BeanNameAware, InitializingBean, DisposableBean {

        private final Repository repository;
        private Validator validator;
        private String beanName;

        public ManagedJob(Repository repository) {
            this.repository = repository;
            System.out.println("1. Constructor: repository = " + repository.name());
        }

        @Autowired
        public void setValidator(Validator validator) {
            this.validator = validator;
            System.out.println("2. Setter injection: validator da co");
        }

        @Override
        public void setBeanName(String name) {
            this.beanName = name;
            System.out.println("3. BeanNameAware: " + name);
        }

        @PostConstruct
        public void postConstruct() {
            if (!validator.accept(repository)) {
                throw new IllegalStateException("Dependency chua hop le");
            }
            System.out.println("4. @PostConstruct: dependencies hop le");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("5. InitializingBean.afterPropertiesSet");
        }

        public void customInit() {
            System.out.println("6. @Bean initMethod");
        }

        public void execute() {
            if (!"managedJob".equals(beanName)) {
                throw new IllegalStateException("Sai bean name");
            }
            System.out.println("7. Business method");
        }

        @PreDestroy
        public void preDestroy() {
            System.out.println("8. @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("9. DisposableBean.destroy");
        }

        public void customDestroy() {
            System.out.println("10. @Bean destroyMethod");
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.BeanLifecycleDemo
~~~

Stdout do chương trình in (không tính log riêng do môi trường Maven tạo):

~~~text
1. Constructor: repository = orders
2. Setter injection: validator da co
3. BeanNameAware: managedJob
4. @PostConstruct: dependencies hop le
5. InitializingBean.afterPropertiesSet
6. @Bean initMethod
7. Business method
8. @PreDestroy
9. DisposableBean.destroy
10. @Bean destroyMethod
~~~

**Giải thích chính xác theo mã:**

- Bean `repository` được resolve để làm **argument của factory method** `managedJob(Repository repository)`; bên trong factory method, code gọi constructor `new ManagedJob(repository)` nên dòng 1 xuất hiện.
- Spring tạo object trước rồi xử lý `@Autowired` setter `setValidator`, nên dòng 2 xảy ra **trước** init callbacks.
- Sau property population, `BeanNameAware.setBeanName` được gọi, tạo dòng 3.
- Các callback init cho cùng bean chạy theo `@PostConstruct` → `afterPropertiesSet` → custom `initMethod`, tạo dòng 4, 5, 6.
- `context.getBean(ManagedJob.class)` trong `main` lấy singleton đã sẵn sàng, rồi ứng dụng gọi `execute()` tạo dòng 7.
- Khi kết thúc `try-with-resources`, context đóng và gọi `@PreDestroy` → `DisposableBean.destroy` → custom `destroyMethod`, tạo dòng 8, 9, 10.

Trong ví dụ này không có bean mang tên `managedJob` nào khác và không có custom `BeanPostProcessor` làm đổi hành vi. `@Autowired` và `@PostConstruct` được xử lý vì `AnnotationConfigApplicationContext` đăng ký các annotation processors tiêu chuẩn. Spring có thể dựng một vài infrastructure beans khác trước, nhưng chúng không in ra stdout nên không đổi thứ tự 10 dòng trên.

Tại sao `@Bean(initMethod = ...)` có tác dụng với một object đã được tạo bằng `new` trong factory method? Bởi **Spring gọi phương thức @Bean để lấy object**, sau đó **đưa object ấy qua quy trình lifecycle**. Trong khi đó, code người dùng tự gọi `new ManagedJob(...)` bên ngoài container sẽ không được Spring tự động inject setter hay chạy callback.

## 8. Tự quan sát BeanPostProcessor

Để thấy rõ **một điểm mở rộng khác** trong vòng đời, ứng dụng có thể đăng ký `BeanPostProcessor`. Đoạn sau là cấu hình minh họa; có thể đặt bên trong class `Config` của ví dụ, với các import tương ứng:

~~~java
@Bean
static BeanPostProcessor tracingProcessor() {
    return new BeanPostProcessor() {
        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {
            if ("managedJob".equals(beanName)) {
                System.out.println("BPP before init");
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {
            if ("managedJob".equals(beanName)) {
                System.out.println("BPP after init");
            }
            return bean;
        }
    };
}
~~~

Import: `org.springframework.beans.factory.config.BeanPostProcessor`. **Đừng áp dụng đoạn thêm này nếu đang đối chiếu stdout đúng 10 dòng ở mục 7** vì các dòng trace sẽ xuất hiện thêm. Đây là một phần mở rộng riêng biệt để quan sát lifecycle.

Khi khai báo post-processor bằng `@Bean`, nên sử dụng **static factory method** (như mẫu) và ít dependency để tránh khởi tạo sớm một số bean trước khi tất cả post-processors được đăng ký. Một BeanPostProcessor thường được gọi trên nhiều bean khác nhau, nên ví dụ lọc theo tên `managedJob`.

Dòng “BPP before init” không nên gắn cứng vị trí *trước* `@PostConstruct` khi chưa kiểm soát thứ tự của `CommonAnnotationBeanPostProcessor` và custom processor. Nó chắc chắn nằm trước các callback như `afterPropertiesSet` và custom init theo contract cơ bản; “BPP after init” nằm sau các callback init đó. `BeanPostProcessor` trả một object khác có thể thay thế/proxy bean mà client nhìn thấy; đừng dựa vào `bean == getBean(...)` nếu ứng dụng có proxy.

## 9. Singleton, prototype, lazy và ảnh hưởng đến các bước lifecycle

Scope và độ lazy ảnh hưởng đến **khi nào** các bước được thực hiện, không xóa đi ý nghĩa của instantiation/DI/init.

| Loại bean | Khi nào tạo thông thường? | DI và init diễn ra khi nào? | Khi đóng context |
| --- | --- | --- | --- |
| Singleton mặc định | Trong `refresh()`, nếu non-lazy | Một lần khi tạo singleton | Spring thực hiện destroy callback khi phù hợp |
| `@Lazy` singleton | Khi được yêu cầu lần đầu, trừ trường hợp bị kéo tạo sớm | Một lần khi thực sự được tạo | Nếu bean đã tạo và được quản lý, destroy khi context đóng |
| Prototype | Mỗi lần container giải quyết yêu cầu tạo prototype | Mỗi instance được tạo đều trải qua DI/init | Spring **không tự gọi** destroy callback cho từng prototype được trao |
| Request scope | Khi cần trong request hiện hành | Một lần cho target được scope tạo | Dọn dẹp theo vòng đời request và scope |
| Session scope | Khi cần trong session hiện hành | Một lần cho target được scope tạo | Dọn dẹp theo vòng đời session và scope |

Ví dụ singleton A có constructor nhận prototype B: **B được tạo lúc container cần dựng A**, chứ không chờ đến lần đầu gọi method trên A; các lần gọi A.method() sau đó không tự làm B khởi tạo lại. Nếu A cần một B mới cho mỗi thao tác, dùng provider/lookup theo nhu cầu hoặc cơ chế proxy với semantics phù hợp.

Nếu một prototype mới được tạo năm lần, các callback `@PostConstruct`/`afterPropertiesSet`/`initMethod` của nó cũng có thể được gọi năm lần tương ứng. Đừng sử dụng prototype làm resource owner rồi kỳ vọng container gọi `@PreDestroy` cho mỗi instance khi đóng ứng dụng.

## 10. Chú ý khi init method tương tác với AOP, transaction và thread

**Proxy/transaction:** Với Spring AOP proxy thông thường, init callback chạy trên target trước khi việc post-processing hoàn tất. Gọi `this.transactionalMethod()` từ `@PostConstruct` là self-invocation và không đi qua advice của proxy. Nếu cần chạy nghiệp vụ có transaction sau startup, hãy sử dụng collaborator được inject qua proxy và lifecycle hook đúng mốc.

**Thread và công việc nặng:** Khởi chạy một thread từ constructor hoặc callback init có thể công bố một bean chưa hoàn tất initialization. Ngoài ra, init callback trong quá trình tạo singleton có thể giữ creation lock; gọi nhiều bean khác, đợi tác vụ bất đồng bộ hoặc I/O không timeout có rủi ro circular dependency, deadlock và startup bị treo. Dành callback cho validation và cấu trúc dữ liệu cục bộ; công việc cần tất cả eager singletons nên cân nhắc `SmartInitializingSingleton`, event refresh hoặc `SmartLifecycle` tùy mục tiêu.

**Vòng phụ thuộc:** `A(B)` và `B(A)` qua constructor không có trật tự dựng hợp lệ. Chuyển bừa sang field/setter injection có thể chỉ che thiết kế coupling, và cấu hình cho phép circular references thay đổi theo môi trường. Hãy làm rõ hợp đồng phụ thuộc, tách nhiệm vụ hoặc dùng lazy lookup có chủ đích. Phần riêng về rủi ro trong init callbacks sẽ minh họa lock, timeouts và cách khởi động tác vụ nền an toàn.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `@PostConstruct` không chạy | Class được tạo bằng `new` ngoài Spring; annotation sai package; processor chưa đăng ký | Bảo đảm object là Spring bean; dùng `jakarta.annotation.PostConstruct` với Spring 6; kiểm tra context configuration |
| Setter `@Autowired` không được gọi | Bean không đi qua autowiring processor hoặc không do context phù hợp quản lý | Kiểm tra bean registration và annotation processors |
| `NullPointerException` trong constructor khi truy cập field `@Autowired` | Field injection chưa xảy ra | Chuyển dependency bắt buộc sang constructor |
| Bean chạy init hai lần trong quan sát | Có hai instance/contexts, proxy/lifecycle khác nhau, hoặc code tự gọi callback | Log bean name, context identity và điểm khởi tạo; không tự gọi init method |
| Không thể resolve dependency | Không có bean, nhiều candidate, sai qualifier/generic | Đọc cause của `UnsatisfiedDependencyException`/`NoUniqueBeanDefinitionException`; bổ sung bean hoặc qualifier |
| Bean không khởi tạo khi app start | `@Lazy`/prototype hoặc condition không đăng ký | Kiểm tra scope, lazy flag và có ai yêu cầu bean chưa |
| Bean được khởi tạo “quá sớm” | Singleton eager hoặc dependency của bean khác kéo tạo | Xem dependency graph và phạm vi `@Lazy` |
| `@Transactional` không hoạt động trong `@PostConstruct` | Init chạy trên target chưa qua AOP entry point | Chuyển logic tới thời điểm sau khi proxy sẵn sàng, gọi qua bean khác/proxy |
| Context start thất bại khi init | Callback ném exception, có I/O/validation không hợp lệ | Xem exception gốc trong `BeanCreationException`, kiểm tra các tham số và config |
| Prototype không chạy `@PreDestroy` khi đóng context | Spring không tự quản lý destroy phase của các prototype đã cấp | Quy ước bên nhận đóng resource |
| Thứ tự các bean độc lập khác dự kiến | Không có thứ tự tùy ý bảo đảm giữa các bean không có dependency | Đừng dựa vào order ngẫu nhiên; khai báo dependency thực hoặc dùng hook app lifecycle phù hợp |
| Test thuần `new` khác test Spring context | Unit test không có container wiring | Truyền collaborator thủ công hoặc chạy Spring test context khi cần test lifecycle |

**Khi debug, đặt log có kiểm soát ở constructor, setter, `@PostConstruct`, init callbacks và method nghiệp vụ**; phân biệt khi nào bean được tạo với khi nào request gọi `getBean()`. Trong bối cảnh AOP, có thể in cả class của object do context cung cấp để nhận biết proxy, nhưng đừng dựa vào tên class do proxy sinh ra làm contract API.

## 12. Checklist thực hành và bài tập

Trước khi coi một bean đã cấu hình đúng, tự kiểm tra:

1. Bean definition xuất phát từ component scanning, `@Bean`, XML hay đăng ký API nào? Object có thật do container quản lý không?
2. Bean scope và độ lazy là gì? Điều gì kích hoạt lần tạo instance đầu tiên?
3. Dependency bắt buộc đã có tại constructor/factory method chưa? Dependency nào chỉ được setter/field inject sau đó?
4. Có dùng field được inject trong constructor trước khi injection diễn ra không?
5. Init callback có chỉ kiểm tra/cấu hình state cục bộ, hay đang làm công việc nguy hiểm/quá nặng?
6. Nếu nhiều callback cùng tồn tại, đã hiểu thứ tự `@PostConstruct` → `afterPropertiesSet` → custom init chưa?
7. Bean có được thay bằng proxy sau init không? Có đang gọi AOP advice bên trong constructor/init/self-invocation không?
8. Đã xác định owner của resource và destroy mechanism tương ứng với scope chưa?
9. Khi lỗi, có đọc **root cause** của `BeanCreationException` để biết lỗi ở instantiation, DI hay initialization không?

### Bài 1 — Constructor và field injection

Một component có constructor gọi `emailSender.send()`, trong khi `emailSender` chỉ được đánh dấu `@Autowired` trên field. Lỗi có thể xảy ra ở đâu?

**Đáp án:** Constructor chạy trước field injection, nên `emailSender` có thể còn `null`. Nếu dependency bắt buộc, đưa `EmailSender` vào constructor argument.

### Bài 2 — Thứ tự init callbacks

Một bean có ba method khác nhau, lần lượt dùng `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và `@Bean(initMethod="prepare")`. Thứ tự gọi là gì?

**Đáp án:** `@PostConstruct` → `afterPropertiesSet()` → `prepare()`, giả sử bean tạo và điền dependency thành công.

### Bài 3 — Singleton và lần `getBean()` thứ hai

Một singleton non-lazy đã được Spring tạo lúc context refresh. Sau đó hai lần `getBean(MyService.class)` được gọi. Constructor, DI và init có chạy thêm hai lần không?

**Đáp án:** Không. Hai lần lookup thường nhận lại cùng singleton đã initialized; không tạo hay init thêm bean đó.

### Bài 4 — Prototype nhận từ singleton

`SingletonWorker` nhận một `PrototypeTask` qua constructor. Mỗi lần `worker.perform()` có tự inject một `PrototypeTask` mới không?

**Đáp án:** Không. Dependency được resolve một lần khi dựng `SingletonWorker`. Muốn tạo prototype mới mỗi thao tác, truy xuất theo nhu cầu bằng `ObjectProvider<PrototypeTask>` hoặc factory thích hợp.

### Bài 5 — Post-processor và @PostConstruct

Có thể chắc chắn mọi custom `BeanPostProcessor.postProcessBeforeInitialization` đều chạy trước `@PostConstruct` không?

**Đáp án:** Không. `@PostConstruct` được xử lý qua một BeanPostProcessor của Spring; thứ tự các post-processors ảnh hưởng vị trí tương đối. Chỉ nên dựa vào các contract/thứ tự được bảo đảm.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework — Customizing the Nature of a Bean (Lifecycle Callbacks)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Container Extension Points: BeanFactoryPostProcessor và BeanPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — Using @PostConstruct and @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
