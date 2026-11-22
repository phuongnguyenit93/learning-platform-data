# Thứ tự khi kết hợp nhiều cơ chế khởi tạo bean trong Spring Framework

## 1. Vấn đề cần giải quyết

Trong Spring Core Container, một bean có thể đồng thời sử dụng **constructor**, dependency injection, các giao diện `Aware`, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, phương thức khởi tạo riêng (`init-method`/`@Bean(initMethod = ...)`), và `BeanPostProcessor`. Mỗi cơ chế tham gia ở một điểm khác nhau trong quá trình tạo bean.

Câu hỏi trọng tâm là: **khi cùng một bean khai báo nhiều cơ chế khởi tạo, Spring gọi chúng theo thứ tự nào, tại sao thứ tự đó quan trọng, và cơ chế nào có thể làm thay đổi luồng chuẩn?**

Với một bean được Spring quản lý và ba cơ chế callback khởi tạo thông dụng có **ba tên phương thức khác nhau**, Spring cam kết thứ tự:

1. Phương thức đánh dấu **`@PostConstruct`**.
2. **`InitializingBean.afterPropertiesSet()`**.
3. Phương thức khởi tạo tùy chỉnh, ví dụ **`@Bean(initMethod = "customInit")`** hoặc `init-method` trong XML.

Thứ tự này được công bố trong Spring Framework Reference, phần **Combining Lifecycle Mechanisms**. Đây là **thứ tự các callback khởi tạo bên trong cùng một bean**, không phải một lời hứa rằng mọi bean trong ứng dụng được tạo theo thứ tự khai báo class, `@Bean` hay thứ tự trong source code.

## 2. Dòng đời khởi tạo một bean: nhìn toàn cảnh

Đối với một bean thông thường được container tạo và hoàn tất không có vòng phụ thuộc phức tạp, sơ đồ đơn giản hóa như sau:

```text
Đăng ký bean definition; xử lý cấu hình BeanFactory
                  |
                  v
          Khởi tạo instance
        (constructor/factory method)
                  |
                  v
      Gắn dependencies/properties
      (ví dụ @Autowired, setter)
                  |
                  v
         BeanNameAware /
      BeanClassLoaderAware /
         BeanFactoryAware
                  |
                  v
 BeanPostProcessor.beforeInitialization
    (trong chuỗi này có xử lý
     @PostConstruct thông qua
     annotation post-processor)
                  |
                  v
  InitializingBean.afterPropertiesSet()
                  |
                  v
        Custom init-method
                  |
                  v
 BeanPostProcessor.afterInitialization
         (có thể bọc AOP proxy)
                  |
                  v
          Bean sẵn sàng dùng
```

Sơ đồ mô tả **điểm móc chuẩn của Spring**, không khẳng định mọi triển khai `BeanPostProcessor` đều chạy trước `@PostConstruct`. `@PostConstruct` **được chính một post-processor xử lý trong giai đoạn before-initialization**. Vì vậy khi thêm nhiều processor, thứ tự chi tiết phải xét `PriorityOrdered`, `Ordered` và quy tắc đăng ký của chúng.

Các giai đoạn có ý nghĩa khác nhau:

| Giai đoạn | Spring đang làm gì? | Bean có thể dựa vào điều gì? |
| --- | --- | --- |
| Instantiate | Gọi constructor hoặc factory method | Các tham số constructor; chưa được phép giả định mọi field/setter injection đã xong |
| Populate properties | Chèn dependencies/giá trị cấu hình | Dependencies đã được resolve theo wiring bình thường |
| Aware callbacks | Cung cấp một số metadata/hạ tầng container | Ví dụ bean name hoặc `BeanFactory` |
| Before-initialization processors | Kiểm tra, trang trí, kích hoạt annotation lifecycle | `@PostConstruct` có thể chạy tại đây |
| `afterPropertiesSet` | Callback của `InitializingBean` | Các dependencies cần thiết đã được đặt |
| Custom init method | Callback có tên được cấu hình | Callback trước đó trên cùng bean đã hoàn tất thành công |
| After-initialization processors | Hoàn thiện bean, có thể trả wrapper/proxy | Instance cuối cùng được expose có thể là proxy |

**Không đồng nhất “khởi tạo đối tượng Java” với “bean đã sẵn sàng”.** Constructor chạy trước khi Spring hoàn thành toàn bộ dependency injection và lifecycle callbacks. Một bean có thể đã có instance mà các callback khởi tạo chưa chạy xong.

## 3. Ba cơ chế khởi tạo có thể kết hợp

Trọng tâm của bài là **quan sát thứ tự** khi một bean bật đồng thời ba callbacks với tên khác nhau. Khác nhau ở nơi khai báo và cách gắn với Spring:

| Callback | Nơi khai báo | Điều Spring cần biết |
| --- | --- | --- |
| `@PostConstruct void prepare()` | Method trên bean class, `jakarta.annotation.PostConstruct` | Annotation processor hỗ trợ Jakarta; method không tham số |
| `InitializingBean.afterPropertiesSet()` | Bean class implement interface Spring | `afterPropertiesSet()` là hợp đồng interface; class phụ thuộc API Spring |
| `@Bean(initMethod = "warmUp")` | Method đăng ký bean trong Java configuration | Bean instance có method `warmUp()` phù hợp, không tham số |

Đối với bean có đầy đủ ba hooks, hãy dự đoán trace `postConstruct → afterPropertiesSet → customInit`. Đó là thứ tự của **ba phương thức phân biệt** được Spring bảo đảm; thứ tự khai báo trong file Java hoặc `@Order` không sắp xếp lại ba callbacks. Nếu cấu hình cùng một tên method ở nhiều cơ chế, Spring có logic tránh gọi lặp phương thức đó; đừng dựa vào khai báo trùng để chạy nhiều lần.

`@Bean(initMethod = "warmUp")` cũng có thể được khai báo tương đương qua XML `init-method="warmUp"`, nhưng chỉ cần chọn một con đường đăng ký bean trong thí nghiệm. Để hiểu chi tiết cú pháp và đánh đổi coupling, xem bài `InitializingBean`/`initMethod`; mục tiếp theo cung cấp project Gradle độc lập để quan sát trace thực tế, bao gồm before/after processor.

## 4. Chương trình Java 17+ hoàn chỉnh quan sát chính xác thứ tự

Tạo dự án Gradle nhỏ để thực nghiệm trực tiếp với Spring Framework 6.2.x. Dự án này không cần Spring Boot.

```text
bean-init-order/
├── settings.gradle
├── build.gradle
└── src/main/java/BeanInitOrderDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'bean-init-order'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'BeanInitOrderDemo'
}
```

`jakarta.annotation-api` được khai báo tường minh để bảo đảm `@PostConstruct` và `@PreDestroy` có trên compile/runtime classpath. Ví dụ dùng Java 17, Gradle 8+ và mạng để tải dependencies nếu chúng chưa được cache.

### src/main/java/BeanInitOrderDemo.java

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class BeanInitOrderDemo {

    public static final class Helper {
    }

    public static class ManagedTask
            implements BeanNameAware, InitializingBean, DisposableBean {

        private Helper helper;

        public ManagedTask() {
            System.out.println("01 constructor");
        }

        @Autowired
        public void setHelper(Helper helper) {
            this.helper = helper;
            System.out.println("02 dependency injection");
        }

        @Override
        public void setBeanName(String name) {
            System.out.println("03 BeanNameAware: " + name);
        }

        @PostConstruct
        public void postConstruct() {
            if (helper == null) {
                throw new IllegalStateException("helper not injected");
            }
            System.out.println("04 @PostConstruct");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("05 afterPropertiesSet");
        }

        public void customInit() {
            System.out.println("06 customInit");
        }

        @PreDestroy
        public void preDestroy() {
            System.out.println("08 @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("09 DisposableBean.destroy");
        }

        public void customDestroy() {
            System.out.println("10 customDestroy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public Helper helper() {
            return new Helper();
        }

        @Bean(initMethod = "customInit",
              destroyMethod = "customDestroy")
        public ManagedTask managedTask() {
            return new ManagedTask();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ManagedTask task = context.getBean(ManagedTask.class);
            System.out.println("07 bean ready: " + (task != null));
        }
    }
}
```

Chạy tại thư mục dự án:

```bash
gradle run --quiet
# Nếu đã tạo Gradle Wrapper thì cũng có thể:
# ./gradlew run --quiet
```

Các dòng do chương trình in bằng `System.out`, theo thứ tự:

```text
01 constructor
02 dependency injection
03 BeanNameAware: managedTask
04 @PostConstruct
05 afterPropertiesSet
06 customInit
07 bean ready: true
08 @PreDestroy
09 DisposableBean.destroy
10 customDestroy
```

Thư viện logging có thể phát thêm thông tin môi trường tùy cấu hình; các dòng trên là output mà **logic chương trình** chủ động in.

### Vì sao thứ tự này ổn định?

- `new ManagedTask()` chạy trong `@Bean` factory method, tạo đối tượng và in `01`.
- Spring xử lý `@Autowired` trên setter `setHelper` khi populate properties, trước các lifecycle init callbacks; in `02`.
- `BeanNameAware.setBeanName` được container gọi sau property population, trước initialization callbacks; in `03`. Tên bean từ method `@Bean managedTask()` là `managedTask`.
- `CommonAnnotationBeanPostProcessor` nhận diện `@PostConstruct` trong chuỗi before-initialization processors, in `04`.
- `InitializingBean.afterPropertiesSet` được gọi sau đó, in `05`.
- `initMethod = "customInit"` kích hoạt method tùy chỉnh, in `06`.
- `getBean` sau khi context đã refresh nhận bean đã khởi tạo; in `07`.
- Khi `try-with-resources` đóng context, Spring gọi destruction callbacks của **singleton** do nó quản lý theo thứ tự `@PreDestroy` → `DisposableBean.destroy` → custom destroy, in `08` tới `10`.

Bean `Helper` không tự in gì, nên ví dụ tập trung vào một bean cần quan sát. Việc Spring resolve `Helper` trước lúc gọi setter không làm thay đổi thứ tự mà bài học đo lường.

## 5. Vì sao không nên bỏ qua các bước trước @PostConstruct?

Cùng một bean có thể nhận dependency qua constructor, field hoặc setter. Với setter/field injection, Spring gọi constructor trước, sau đó mới populate properties. Vì vậy:

```java
@Component
class BadExample {
    @Autowired
    private DataSource dataSource;

    BadExample() {
        // dataSource thường vẫn null ở thời điểm này.
        // Không gọi dataSource.getConnection() tại đây.
    }

    @PostConstruct
    void initialize() {
        // Dependency injection bình thường đã hoàn thành.
        // Kiểm tra cấu hình rồi mới mở/kết nối tài nguyên nếu cần.
    }
}
```

Đây là **anti-example minh họa**, chưa chứa các import/bean definition cần thiết. Phần bình luận trong constructor mô tả field injection thường gặp, không phải quy tắc áp dụng cho constructor injection.

Nếu dependency được yêu cầu trong constructor, hãy **constructor-inject** dependency đó:

```java
@Component
class BetterExample {
    private final DataSource dataSource;

    BetterExample(DataSource dataSource) {
        this.dataSource = dataSource;
    }
}
```

Spring cung cấp tham số constructor khi tạo bean. Điều này giúp class xác lập invariant sớm, ít trạng thái nửa khởi tạo; nhưng không nên gọi phương thức tùy ý trên bean khác trong constructor nếu phụ thuộc ngược hoặc proxy lifecycle còn chưa sẵn sàng.

Trong `@PostConstruct`, các dependency bình thường đã được cung cấp, nhưng **không đảm bảo toàn bộ context đã refresh** hoặc các singleton không liên quan đã hoàn thành initialization. Nếu cần một sự kiện sau khi mọi singleton non-lazy đã được tạo, xem `SmartInitializingSingleton` ở mục 9.

## 6. BeanPostProcessor nằm ở đâu so với @PostConstruct?

`BeanPostProcessor` định nghĩa hai hook:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
```

Đây là **chữ ký API minh họa**; Spring thực tế định nghĩa chúng trên interface `BeanPostProcessor`.

Ở mức pipeline, Spring làm tương đương:

```java
// MÃ GIẢ minh họa thứ tự, không phải source chạy độc lập.
Object bean = instantiateAndPopulate();
invokeAwareInterfaces(bean);
bean = applyBeanPostProcessorsBeforeInitialization(bean);
invokeInitializingBean(bean);
invokeCustomInitMethod(bean);
bean = applyBeanPostProcessorsAfterInitialization(bean);
return bean;
```

**Chi tiết mấu chốt:** `@PostConstruct` không chạy trong một bước tách biệt đứng bên ngoài mọi `BeanPostProcessor`. Spring dùng `CommonAnnotationBeanPostProcessor` (kế thừa từ `InitDestroyAnnotationBeanPostProcessor`) để chạy method được annotate trong **before-initialization processing**.

Vì vậy một user-defined `BeanPostProcessor.postProcessBeforeInitialization` có thể quan sát bean **trước hoặc sau `@PostConstruct`**, tùy thứ tự processor. Đừng ghi một thứ tự cứng kiểu “mọi before-processor → `@PostConstruct`”. Điều Spring bảo đảm khi kết hợp ba callback là `@PostConstruct` trước `afterPropertiesSet` rồi trước custom init, với những tên method khác nhau.

`postProcessAfterInitialization` chạy sau các init callback ở pipeline thông thường và có thể trả về proxy. Một proxy AOP được tạo tại đây có thể thay đổi đối tượng được client nhận qua `getBean`, nhưng không làm callback `@PostConstruct` của target chạy lại.

### Ví dụ processor riêng chỉ để quan sát

```java
import org.springframework.beans.factory.config.BeanPostProcessor;

class TraceProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if ("managedTask".equals(beanName)) {
            System.out.println("before-init processor");
        }
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if ("managedTask".equals(beanName)) {
            System.out.println("after-init processor");
        }
        return bean;
    }
}
```

Class là **mảnh minh họa độc lập**, chưa được đăng ký vào ví dụ mục 4. Nếu tích hợp nó, output sẽ thêm các dòng và thứ tự của dòng `before-init processor` so với `@PostConstruct` phụ thuộc order giữa các post-processors; không được coi output mục 4 còn giữ nguyên.

Khi cần can thiệp chính xác thứ tự processor, tìm hiểu `PriorityOrdered`, `Ordered` và `@Order` đối với **các bean processor**, cùng quy tắc register programmatically. Đăng ký processor quá muộn sẽ không tác động tới các bean đã được tạo.

## 7. Khi cả ba cơ chế khai báo cùng một method

Spring Reference nói rõ: nếu nhiều cơ chế init cùng **tham chiếu cùng một method name**, Spring không gọi method đó lặp lại chỉ để thỏa từng khai báo. Thí dụ:

```java
public class SharedInit {
    @PostConstruct
    public void initialize() {
        System.out.println("initialize");
    }
}

@Configuration
class SharedInitConfig {
    @Bean(initMethod = "initialize")
    SharedInit sharedInit() {
        return new SharedInit();
    }
}
```

Đây là mảnh minh họa cần import tương ứng. Mục tiêu là làm rõ *cùng method `initialize`* được đánh dấu `@PostConstruct` và đồng thời cấu hình `initMethod = "initialize"`; Spring nhận diện và tránh gọi method hai lần khi callback trùng nhau.

Đừng dùng trùng method name để suy luận rằng mọi callback đều chạy hai lần. Nếu muốn đo lường thứ tự, đặt tên **khác nhau** như `postConstruct`, `afterPropertiesSet` và `customInit` ở mục 4.

Trong trường hợp chỉ gọi một method từ method khác do lập trình viên tự viết, đó là **lời gọi Java bình thường** và có thể làm logic lặp lại. Hành vi tránh gọi trùng nói trên chỉ nói về xử lý lifecycle callbacks của container.

## 8. Thứ tự hủy khi kết hợp nhiều cơ chế

Tuy đề bài trọng tâm là khởi tạo, không nên nhầm trình tự đối xứng khi đóng bean. Với **singleton được container quản lý**, có ba callback hủy mang tên khác nhau:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method, ví dụ `@Bean(destroyMethod = "customDestroy")`.

Đó là thứ tự trong chương trình mục 4. Callback hủy được gọi khi context đóng bình thường (hoặc trong một số tình huống container phá hủy bean). Không nên suy ra rằng **mọi scope** đều được Spring quản lý destruction giống singleton.

| Scope | Init callback | Destruction callback |
| --- | --- | --- |
| `singleton` | Chạy khi container tạo bean | Spring quản lý khi context đóng hoặc bean được hủy |
| `prototype` | Chạy mỗi lần Spring tạo bean mới | Spring **không tự quản lý** destruction của prototype sau khi trao cho caller |
| `request` / `session` | Chạy khi tạo instance trong scope đang hoạt động | Phụ thuộc lifecycle scope trong web-aware context |
| Custom scope | Phụ thuộc cách triển khai scope | Phải xem scope đó có chạy destruction callback không |

Đối với prototype có `AutoCloseable`/socket/file stream, caller cần chủ động cleanup (ví dụ `try-with-resources`), bất kể callback init của prototype đã chạy.

Đối với `@Bean`, Spring còn có khả năng **suy đoán destroy method** như `close` hoặc `shutdown` khi phù hợp. Nếu yêu cầu kiểm soát chính xác, cấu hình tên tường minh hoặc tắt inference theo quy tắc API thay vì đoán Spring có gọi một phương thức nào đó hay không.

## 9. Phân biệt init callback với tín hiệu context đã sẵn sàng

Ba callback `@PostConstruct`, `afterPropertiesSet` và custom init diễn ra khi **từng bean** được khởi tạo. Chúng không có nghĩa toàn bộ ứng dụng đã khởi động.

### SmartInitializingSingleton

`SmartInitializingSingleton.afterSingletonsInstantiated()` được gọi khi container đã hoàn tất giai đoạn **pre-instantiation các singleton thường (non-lazy)**. Phù hợp khi một bean cần thao tác sau khi các singleton thông thường đã được dựng, ví dụ rà soát registry.

```java
import org.springframework.beans.factory.SmartInitializingSingleton;

class RegistryVerifier implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Chạy sau vòng pre-instantiation singleton thông thường.
        // Không đồng nghĩa prototype/lazy bean đã được tạo.
    }
}
```

Class trên là mảnh minh họa; phải đăng ký nó làm bean. Không dùng callback này như lời hứa rằng mọi lazy singleton, prototype, request bean đã có instance. Đây cũng không phải callback chạy lại mỗi lần tạo prototype.

### ContextRefreshedEvent

`ContextRefreshedEvent` được phát sau khi `ApplicationContext` đã hoàn tất lần refresh tương ứng. Nó nằm ở **cấp context**, có thể xuất hiện ở những lần refresh tiếp theo tùy loại context, và trong phân cấp context có thể cần lọc event source.

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

class ReadyListener {
    @EventListener
    public void onReady(ContextRefreshedEvent event) {
        // Xử lý mốc refresh của context nếu thực sự cần.
    }
}
```

Đây là mảnh minh họa chưa đăng ký bean. Đừng chuyển toàn bộ init logic trong `@PostConstruct` sang event chỉ để tránh hiểu thứ tự; sự kiện cấp context phục vụ mục tiêu khác. Spring Boot có thêm runner/availability events, nhưng đó là **đời sống ứng dụng Spring Boot**, nằm ngoài hợp đồng init callback của Spring Core.

### Lifecycle / SmartLifecycle

`Lifecycle.start/stop` và `SmartLifecycle` dành cho các component cần bật/tắt dịch vụ (consumer, listener, worker loop). Chúng không thay thế `@PostConstruct` khi chỉ cần kiểm tra cấu hình. Việc tự động khởi động của `SmartLifecycle` và pha `phase` là chủ đề **orchestration**; không trộn nó vào thứ tự ba init callbacks của một bean.

## 10. @DependsOn và @Order không sắp xếp ba callback khởi tạo

Hai annotation thường bị dùng nhầm để cố “sửa thứ tự”:

- `@DependsOn("databaseClient")` đặt quan hệ phụ thuộc giữa **các bean**: trước khi khởi tạo bean phụ thuộc, container cần tạo và khởi tạo bean được phụ thuộc. Nó **không** đổi thứ tự `@PostConstruct` → `afterPropertiesSet` → custom init bên trong mỗi bean.
- `@Order`/`Ordered` ảnh hưởng thứ tự ở các cơ chế Spring có hỗ trợ ordering (ví dụ một số tập hợp bean, processors), **không** mặc định bảo đảm thứ tự tạo mọi bean singleton bất kể quan hệ phụ thuộc.

Ví dụ sơ đồ:

```text
DatabaseClient:
    constructor -> inject -> @PostConstruct -> afterPropertiesSet -> init

OrderService (@DependsOn("databaseClient")):
    constructor -> inject -> @PostConstruct -> afterPropertiesSet -> init
```

`@DependsOn` ảnh hưởng **bean nào phải hoàn tất trước**, còn trật tự **các callback bên trong bean** vẫn giữ nguyên.

Nếu muốn bảo đảm một bean chạy sau bean khác vì cần dùng API của dependency, thông thường constructor injection đã biểu đạt mối quan hệ phù hợp. `@DependsOn` hữu ích khi dependency không biểu hiện trực tiếp qua injection nhưng vẫn có ràng buộc initialization. Tránh dùng annotation này để che lỗi circular dependency hoặc tạo coupling không rõ ràng.

## 11. Trình tự có thể thay đổi ở đâu?

### Bean do factory method tạo

Một `@Bean` method tạo instance bằng `new` **vẫn được Spring áp dụng injection, Aware và các init callbacks** sau khi phương thức trả về. Ví dụ mục 4 chứng minh điều đó. Nhưng **logic bạn tự gọi trong thân factory method** chạy trước khi method trả về và không thể tự động bị Spring dời đến giai đoạn `@PostConstruct`.

Nếu bạn viết:

```java
@Bean(initMethod = "customInit")
ManagedTask managedTask() {
    ManagedTask task = new ManagedTask();
    task.customInit(); // Caller gọi thủ công ngay trong factory method.
    return task;
}
```

Đây là **anti-example** không được ghép vào chương trình chính. Với cấu hình này, `customInit` được gọi thủ công trước khi Spring hoàn tất injection, rồi container còn có thể gọi callback init được cấu hình sau đó. Không nhầm đó là cơ chế “Spring tự chạy init hai lần”. Hãy để callback lifecycle do container quản lý.

### BeanPostProcessor tạo proxy hoặc thay reference

`postProcessAfterInitialization` có thể trả một object khác (thường proxy AOP) so với instance nguyên thủy. Vì vậy:

- Callback init thường chạy trên target, trước khi proxy cuối cùng được trao.
- Nếu bạn kiểm tra class runtime từ `getBean()`, có thể thấy proxy type.
- Không gọi các method nghiệp vụ phụ thuộc advice trong `@PostConstruct` rồi kỳ vọng advice chạy như lời gọi qua bean proxy.
- Tránh publish `this` ra thread/global registry trong constructor hoặc init callback, vì object có thể chưa hoàn tất lifecycle và chưa qua proxy.

### Early bean creation và circular dependency

`BeanPostProcessor` được đăng ký sớm; nếu cấu hình processor tạo dependency khác quá sớm, bean đó có thể không được mọi processor xử lý đầy đủ, dẫn đến cảnh báo về auto-proxying. Circular dependencies cũng gây hành vi khác biệt hoặc lỗi khi container không thể resolve. Ưu tiên sửa cấu trúc dependency; không dựa vào thứ tự khai báo để “may mắn chạy”.

### @Lazy và prototype

- Singleton `@Lazy` có callback init khi thực sự được tạo, **không bắt buộc tại thời điểm context refresh**.
- Prototype có callback init mỗi lần container tạo instance, nhưng destruction không được tự gọi như singleton.
- Dependency injection có thể kéo một lazy bean vào sớm nếu bean khác cần nó ngay.
- `@PostConstruct` không chạy lại mỗi lần gọi method nghiệp vụ; callback gắn với **lần tạo bean instance**.

## 12. Lỗi thường gặp và cách sửa

| Triệu chứng | Hiểu nhầm/nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@PostConstruct` không chạy | Tạo instance bằng `new` ngoài Spring; thiếu Jakarta annotation processing; sai namespace | Đăng ký bean đúng container; dùng `jakarta.annotation.PostConstruct` trong Spring 6+, có annotation API và processor |
| `NullPointerException` trong constructor | Đọc field được `@Autowired` nhưng injection chưa chạy | Dùng constructor injection hoặc dời logic sang callback init |
| Custom init chạy “sớm” hoặc hai lần | Dev gọi thủ công trong `@Bean` method, đồng thời cấu hình `initMethod` | Chỉ cấu hình một điểm gọi lifecycle, bỏ lời gọi thủ công |
| Kết quả before-processor và `@PostConstruct` khác kỳ vọng | `@PostConstruct` vốn được thực thi qua một before-initialization processor | Kiểm tra thứ tự đăng ký/`Ordered` của post-processors |
| `afterPropertiesSet` chạy trước custom init | Hành vi đúng theo hợp đồng Spring, dù trong file khai báo custom init trước | Xây method init sao cho tuân theo thứ tự Spring |
| Bean lazy chưa chạy init lúc startup | Chưa ai yêu cầu tạo bean đó | Kiểm tra `@Lazy` và thời điểm `getBean`/dependency resolution |
| Prototype không chạy `@PreDestroy` khi context đóng | Spring không theo dõi destruction của từng prototype | Caller tự cleanup |
| Logic init gọi method có `@Transactional` nhưng không có transaction | Method gọi nội bộ trước proxy AOP cuối cùng hoàn tất | Chuyển công việc qua service đã sẵn sàng sau context startup; thiết kế giao dịch tường minh |
| Mong `@Order` sắp xếp thứ tự khởi tạo singleton | `@Order` không phải dependency graph | Dùng dependency injection hoặc `@DependsOn` |
| Dùng `SmartInitializingSingleton` rồi đòi cả lazy/prototype đã có | Callback chỉ sau vòng pre-instantiation các singleton bình thường | Xác định lại cột mốc readiness phù hợp |
| Gọi network/DB trong init làm toàn context không khởi động | Exception thoát khỏi callback khiến Spring không hoàn tất bean creation | Kiểm tra cấu hình, tách kiểm chứng và retry/health phù hợp; không nuốt lỗi bắt buộc |

## 13. Hướng dẫn thiết kế thực tế

**Chỉ dùng một init mechanism cho một trách nhiệm khi có thể.** Ví dụ: giữ `@PostConstruct` để xác thực state đã inject, còn method nghiệp vụ riêng `startPolling()` để bắt đầu worker đúng giai đoạn application-ready. Nếu bắt buộc phối hợp nhiều cơ chế (thường khi tích hợp thư viện cũ), gán mỗi callback một trách nhiệm rõ ràng và ghi nhận thứ tự để người bảo trì không phụ thuộc ngẫu nhiên vào implementation detail.

Một mẫu phân công dễ kiểm soát:

1. **Constructor**: lập bất biến của đối tượng từ constructor arguments; không publish `this`.
2. **Dependency injection**: container cung cấp bean/cấu hình.
3. **`@PostConstruct`**: validate config đã đủ, chuẩn bị state cục bộ.
4. **`afterPropertiesSet`** (nếu interface đã là hợp đồng thư viện): kiểm tra/bảo đảm trạng thái riêng mà interface cam kết.
5. **Custom init** (nếu cần): thực thi bước tích hợp legacy còn lại.
6. **After-initialization**: để post-processors/proxy hoàn thành.
7. **Context-level readiness**: chạy công việc đòi hỏi toàn context ở đúng mốc, không giả định init của một bean có nghĩa mọi bean đã sẵn sàng.
8. **Destruction**: quản lý shutdown/cleanup ở scope thực sự hỗ trợ, xác định rõ ownership của tài nguyên.

Lưu ý các callback init có thể ném exception. Nếu exception không được xử lý, container có thể thất bại khi tạo bean và hủy các singleton đã hoàn thành trước đó. Không nên gắn side effect không thể đảo ngược vào callback init khi chưa có cách rollback/bù trừ và xử lý khởi động lại.

## 14. Tự kiểm chứng bài học

Có thể thay đổi chương trình mục 4 rồi kiểm tra một lần thay đổi:

1. **Bỏ `@PostConstruct`**: output không còn `04 @PostConstruct`; `afterPropertiesSet` và custom init vẫn chạy theo thứ tự riêng.
2. **Bỏ `implements InitializingBean`** và method override: không còn `05 afterPropertiesSet`; custom init vẫn chạy.
3. **Bỏ `initMethod = "customInit"`**: Spring không tự gọi method tùy chỉnh, trừ khi code của bạn gọi thủ công ở nơi khác.
4. **Đổi `@Bean` thành prototype scope**: mỗi lần lấy instance đều có chuỗi init; khi đóng context, không tự mong Spring gọi destruction cho prototype đó.
5. **Thêm `@Lazy` cho singleton**: quan sát rằng các callback có thể lùi tới khi bean thực sự được yêu cầu.
6. **Thêm một custom BeanPostProcessor**: ghi log before/after; đối chiếu vị trí tương đối và hiểu `@PostConstruct` nằm trong before-chain.
7. **Cho `customInit()` ném exception**: context khởi tạo thất bại; bean không được công bố là khởi tạo thành công.

Khi viết test JUnit, nên kiểm tra **danh sách sự kiện** thay vì chỉ nhìn log. Ví dụ dùng `List<String> events` theo dependency test để ghi `"postConstruct"`, `"afterPropertiesSet"`, `"customInit"`, rồi assert chính xác thứ tự. Đối với test có nhiều thread, không dùng danh sách thường chia sẻ mà không đồng bộ.

## 15. Ghi nhớ những ranh giới quan trọng

| Câu hỏi | Câu trả lời chính xác |
| --- | --- |
| Ba callback khởi tạo khác tên chạy theo thứ tự nào? | `@PostConstruct` → `afterPropertiesSet()` → custom `initMethod` |
| Constructor ở đâu? | Trước property injection và trước ba callback init |
| `@Autowired` chạy trước `@PostConstruct`? | Có trong vòng đời injection bình thường của bean được container quản lý |
| `BeanNameAware` ở đâu? | Sau populate properties và trước chuỗi initialization callbacks thông thường |
| Mọi `postProcessBeforeInitialization` đều trước `@PostConstruct`? | **Không**; `@PostConstruct` được một post-processor kích hoạt trong before-chain |
| AOP proxy đã hoàn chỉnh khi chạy `@PostConstruct`? | Thông thường chưa; post-processors có thể proxy sau init |
| Cùng init method khai báo ở nhiều cơ chế sẽ bị gọi trùng? | Spring nhận diện và tránh duplicate lifecycle invocation cho method trùng |
| Các bean khác nhau được tạo theo thứ tự dòng trong `@Configuration`? | Không có bảo đảm tổng quát; phụ thuộc quan hệ wiring, lazy/eager, custom processors |
| Thứ tự hủy của ba callback khác tên? | `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method |
| Prototype có được tự hủy lúc đóng context? | Không; caller chịu trách nhiệm lifecycle sau khi nhận prototype |

## 16. Nguồn tham khảo chính thức

- Spring Framework Reference — [Lifecycle Callbacks / Combining Lifecycle Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): thứ tự `@PostConstruct`, `afterPropertiesSet`, custom init, và thứ tự ba callback hủy.
- Spring Framework Reference — [Container Extension Points: BeanPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): before/after initialization, processor ordering, early instantiation và proxying.
- Spring Framework Reference — [Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): annotation processors được đăng ký bởi `AnnotationConfigApplicationContext`.
- Spring Framework Reference — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): callback init của prototype, giới hạn destruction và singleton dependencies.
- Maven Central — [spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18): phiên bản dependency dùng trong chương trình Java 17.

Khi dùng đồng thời nhiều cơ chế trên **cùng một bean**, chỉ cần nhớ trục chuẩn **`@PostConstruct` → `afterPropertiesSet()` → custom init**; mọi phân tích sâu hơn phải xem thêm thời điểm injection, thứ tự `BeanPostProcessor`, scope của bean và thời điểm ứng dụng/context thực sự sẵn sàng.
