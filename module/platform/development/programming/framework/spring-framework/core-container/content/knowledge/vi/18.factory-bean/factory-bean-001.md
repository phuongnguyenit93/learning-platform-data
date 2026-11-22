# Phân biệt FactoryBean với BeanFactory trong Spring Core Container

## 1. Vì sao hai tên này dễ gây nhầm lẫn?

`BeanFactory` và `FactoryBean` có tên rất giống nhau, nhưng chúng thuộc **hai cấp độ khác nhau** của Spring IoC:

- **`BeanFactory`** là giao diện nền tảng của **container**. Nó quản lý việc tra cứu bean theo tên/kiểu, tạo đối tượng khi cần, áp dụng scope, dependencies và lifecycle thông qua implementation cụ thể.
- **`FactoryBean<T>`** là giao diện được **một bean đặc biệt** triển khai. Bean đó hoạt động như một factory tạo ra **sản phẩm T**. Khi ứng dụng gọi `getBean("tenFactory")`, Spring thông thường trả **sản phẩm do `FactoryBean.getObject()` tạo**, thay vì bản thân object factory.

Cách ghi nhớ:

```text
                  +---------------------------+
                  | BeanFactory (container)   |
                  | - bean definitions        |
                  | - dependency wiring       |
                  | - scopes/lifecycle        |
                  +---------------------------+
                              |
                   getBean("widget")
                              |
                              v
                     [WidgetFactory]
                    implements FactoryBean
                              |
                         getObject()
                              |
                              v
                         Widget
                        (product)

getBean("&widget") ------------------> WidgetFactory
                                         (factory itself)
```

Trong sơ đồ, container **chứa một bean definition cho `WidgetFactory`**; theo hợp đồng `FactoryBean`, tên `widget` bình thường **expose sản phẩm**. Nếu cần lấy lại đối tượng tạo sản phẩm để cấu hình/kiểm tra trực tiếp, Spring hỗ trợ tiền tố `&` trong bean name.

**Điểm khác biệt quan trọng nhất:** `BeanFactory` **quản lý nhiều bean**; một `FactoryBean` **là một bean đặc biệt tạo hoặc cung cấp một loại sản phẩm** bên trong BeanFactory.

## 2. So sánh trực diện

| Tiêu chí | `BeanFactory` | `FactoryBean<T>` |
| --- | --- | --- |
| Gói API | `org.springframework.beans.factory.BeanFactory` | `org.springframework.beans.factory.FactoryBean` |
| Vai trò | IoC container contract | Extension point tùy biến cách một bean/product được tạo |
| Ai triển khai thông thường? | Spring container, ví dụ `DefaultListableBeanFactory` | Developer/thư viện, ví dụ factory cho proxy, client, product |
| Đối tượng quản lý | Bean definitions và mọi bean mà container quản lý | Product của một factory cụ thể |
| API thường dùng | `getBean(...)`, `containsBean(...)`, `isSingleton(...)`, `getType(...)` | `getObject()`, `getObjectType()`, `isSingleton()` |
| Truy cập | Inject/nhận `ApplicationContext`, `BeanFactory` hoặc dùng interface con | Đăng ký một `FactoryBean` làm bean và lookup qua bean name |
| `getBean("x")` | Container resolve đối tượng mang tên `x` | Nếu `x` là FactoryBean, thường trả sản phẩm của nó |
| `getBean("&x")` | Container diễn giải `&` như factory dereference | Trả chính instance FactoryBean đứng sau `x` |
| Phạm vi (scope) | Container thực thi singleton/prototype/custom scope | Scope của factory và singleton-status của product là **hai quyết định riêng** |
| Lifecycle | Container điều khiển lifecycle các beans do nó sở hữu | Bản thân FactoryBean là bean được quản lý; product cần chú ý lifecycle riêng |
| Độ phổ biến trong business code | Có thể dùng nhưng thường ưu tiên constructor injection | Hữu ích với cơ chế tạo đối tượng phức tạp, đặc biệt code hạ tầng |

`BeanFactory` là **interface**, không phải một instance “factory bean” theo naming convention. `FactoryBean` cũng là **interface**, không phải một `BeanFactory` implementation.

## 3. BeanFactory: hợp đồng lõi của IoC container

Một số method tiêu biểu:

```java
Object getBean(String name);
<T> T getBean(String name, Class<T> requiredType);
<T> T getBean(Class<T> requiredType);
boolean containsBean(String name);
boolean isSingleton(String name);
boolean isPrototype(String name);
Class<?> getType(String name);
```

Đây là **trích đoạn chữ ký minh họa**, không phải code độc lập để biên dịch. Các overload và annotations khác đã được lược bớt.

Container có trách nhiệm chung:

1. Giữ bean definitions và biết phải tạo bean từ constructor hay factory method.
2. Resolve dependency graph; tạo bean phụ thuộc trước khi đưa vào bean cần dependency.
3. Áp dụng scope (singleton, prototype và custom/web scopes khi được đăng ký).
4. Thực thi `BeanPostProcessor`, init callbacks và destruction callbacks nếu lifecycle thuộc container.
5. Cung cấp API tra cứu object và thông tin kiểu/scope.

`ApplicationContext` mở rộng hệ thống BeanFactory với environment, resource loading, events, internationalization, nhiều lifecycle tiện ích. Trong các ứng dụng Spring, `AnnotationConfigApplicationContext` là một loại `ApplicationContext` dùng được các API của `BeanFactory`.

Ví dụ sử dụng:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(MyConfig.class)) {
    BeanFactory factory = context;
    PaymentService service = factory.getBean(PaymentService.class);
    service.process();
}
```

Đây là **mảnh ví dụ**, cần `MyConfig` và `PaymentService` thực sự tồn tại cùng import thích hợp. Nó thể hiện rằng biến kiểu `BeanFactory` là interface truy xuất container; nó không tự chỉ định bean nào là `FactoryBean`.

### BeanFactory khác DefaultListableBeanFactory

`BeanFactory` định nghĩa những thao tác client cần; `DefaultListableBeanFactory` là implementation thông dụng, có registry, bean definition metadata và các cơ chế tạo bean thực tế. `ConfigurableListableBeanFactory`, `ConfigurableBeanFactory`, `ListableBeanFactory` là những interface khác cung cấp thêm quyền cấu hình/liệt kê.

Không nên viết business code phụ thuộc trực tiếp vào `DefaultListableBeanFactory` để tự sửa registry khi constructor injection là đủ. Phân biệt **API container** với **implementation container** giúp unit test và module design đơn giản hơn.

## 4. FactoryBean<T>: một bean đưa ra product riêng

Interface đầy đủ có ba method trọng tâm:

```java
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
```

Đây là **chữ ký rút gọn minh họa** theo Spring Framework 6.2. Bản API thật có annotations, Javadoc và có thể thêm metadata.

### 4.1. getObject()

`getObject()` tạo, trả hoặc lấy từ cache sản phẩm của FactoryBean. Tùy `isSingleton()`, Spring có thể cache sản phẩm mà factory đã trả về. Không suy ra rằng mỗi lần gọi `BeanFactory.getBean("x")` đều trực tiếp gọi `FactoryBean.getObject()`.

Nếu `isSingleton()==true` và bean factory phù hợp caching, sau khi sản phẩm được tạo, các lần lookup cùng tên thông thường dùng sản phẩm đã cache.

Nếu `isSingleton()==false`, Spring không áp dụng singleton product cache đó; mỗi lần lookup thường yêu cầu `getObject()`. **FactoryBean phải tự bảo đảm hợp đồng tạo độc lập** nếu muốn hành vi prototype thật sự.

### 4.2. getObjectType()

`getObjectType()` thông báo kiểu sản phẩm, không phải kiểu của bản thân factory. Spring cần thông tin này cho type matching/autowiring mà không phải tạo product vô cớ.

```java
@Override
public Class<?> getObjectType() {
    return Widget.class;
}
```

Đây là mảnh method minh họa, giả định `Widget` là kiểu product. Method nên nhanh, tránh side effect và **không gọi `getObject()` chỉ để đoán product type**. Theo Javadoc, method có thể được gọi khi FactoryBean chưa hoàn tất initialization; đừng phụ thuộc state chỉ được thiết lập muộn trong init callbacks.

Nếu không biết type, `getObjectType()` được phép trả `null`, nhưng Spring không thể dùng type đó để resolve một số autowiring/type searches một cách tin cậy. Đây là lựa chọn bất đắc dĩ, không nên là giá trị mặc định khi product type đã được biết.

### 4.3. isSingleton()

`FactoryBean.isSingleton()` mô tả **product** có là singleton hay không; default là `true`.

```java
@Override
public boolean isSingleton() {
    return false; // Product không phải singleton.
}
```

Đừng đọc `isSingleton()` thành “FactoryBean object là singleton”: đối tượng factory được đăng ký bằng scope riêng (thường mặc định singleton). Hai lớp scope cần xét độc lập.

Khi trả `true`, FactoryBean phải cung cấp một sản phẩm có identity ổn định: các lần gọi `getObject()` theo hợp đồng không nên âm thầm tạo product khác nhau. Container có thể cache product nhưng implementation vẫn phải nhất quán nếu method bị dùng trực tiếp.

## 5. Quy tắc tên bean: & để lấy factory

Giả sử có một bean tên `widget`, được định nghĩa bởi class implement `FactoryBean<Widget>`:

```java
Object product = context.getBean("widget");
Object factory = context.getBean("&widget");
```

Diễn giải:

- `"widget"`: tên logical mà Spring công bố **sản phẩm**.
- `"&widget"`: tiền tố `BeanFactory.FACTORY_BEAN_PREFIX` giúp **dereference factory**, lấy chính bean implement `FactoryBean`.
- `"widget"` vẫn là bean name đăng ký trong registry. **Không** đăng ký một definition riêng mang tên `"&widget"`.
- `&` là cơ chế cú pháp của Spring BeanFactory, **không** phải Java address-of operator.
- Gọi `getBean("&ordinaryBean")` khi bean đó không implement `FactoryBean` sẽ gây lỗi như `BeanIsNotAFactoryException`.

Một cách an toàn khi cần type:

```java
Widget widget = context.getBean("widget", Widget.class);
WidgetFactory factory = context.getBean("&widget", WidgetFactory.class);
```

Đây là mảnh code yêu cầu bean names/types tương ứng đã đăng ký. Kiểu `WidgetFactory` chỉ tồn tại trong ví dụ mục 7.

### Tra cứu theo kiểu cũng bị ảnh hưởng

`getBean(Widget.class)` có thể resolve product của FactoryBean thông qua `getObjectType()` và metadata. Ngược lại, nếu muốn chính factory, nên chỉ rõ prefix `&` hoặc thiết kế wiring cho factory một cách tường minh. Không giả định Spring sẽ coi bản thân FactoryBean là một bean bình thường cho **mọi kiểu lookup** theo Java class của nó.

Đối với danh sách `getBeansOfType` hoặc một injection point, kết quả còn phụ thuộc type inference, tính unique của candidates và cách Spring xử lý FactoryBean instances. Dùng `&name` là cách biểu đạt rõ ràng nhất khi cần chính factory.

## 6. Hai lớp scope phải phân biệt

Đây là chỗ sai phổ biến nhất khi học FactoryBean. Có **hai câu hỏi riêng biệt**:

**Câu hỏi A: bản thân FactoryBean được tạo bao nhiêu lần?**

Nó là một bean do container quản lý. Nếu definition `@Bean("widget")` không có `@Scope`, Spring mặc định dùng **singleton scope cho factory**. Nếu khai báo factory prototype, mỗi lần BeanFactory cần tạo factory instance có thể nhận một factory mới.

**Câu hỏi B: sản phẩm do FactoryBean cung cấp có được cache không?**

`FactoryBean.isSingleton()` trả lời câu này. Với factory singleton:

| Scope của factory | `isSingleton()` của product | Thường quan sát được |
| --- | --- | --- |
| singleton | `true` | Cùng một factory, cùng một product cho nhiều lookup bình thường |
| singleton | `false` | Cùng factory, product không dùng singleton cache; có thể được tạo lại mỗi lookup |
| prototype | `true` | Mỗi lần truy xuất definition có thể tạo factory mới; không hiểu là một product singleton toàn container |
| prototype | `false` | Factory mới có thể tạo product mới theo lần lookup |

Bảng mô tả xu hướng để phân biệt hai chiều; đừng dùng nó thay cho việc kiểm tra bean definition, `FactoryBean` contract và chiến lược tạo/caching của implementation.

Nếu product trả về thuộc một custom scope như request/session, `isSingleton()==false` **không tự chứng minh mỗi lần đều là instance độc lập**. `SmartFactoryBean.isPrototype()` được thiết kế để mô tả rõ hơn việc trả independent objects. Vì vậy **“non-singleton” không luôn đồng nghĩa “prototype”** trong tất cả các kịch bản factory đặc biệt.

## 7. Ví dụ Java 17+ chạy được: hai factory, hai chiến lược product

Dự án tối thiểu với Spring Framework 6.2.x, không cần Spring Boot:

```text
factory-vs-beanfactory/
├── settings.gradle
├── build.gradle
└── src/main/java/FactoryDifferenceDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'factory-vs-beanfactory'
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
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'FactoryDifferenceDemo'
}
```

### src/main/java/FactoryDifferenceDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FactoryDifferenceDemo {

    public record Widget(int number) {
    }

    public static class WidgetFactory implements FactoryBean<Widget> {
        private final boolean productSingleton;
        private final AtomicInteger sequence = new AtomicInteger();
        private Widget sharedProduct;

        public WidgetFactory(boolean productSingleton) {
            this.productSingleton = productSingleton;
        }

        @Override
        public synchronized Widget getObject() {
            if (productSingleton) {
                if (sharedProduct == null) {
                    sharedProduct = new Widget(sequence.incrementAndGet());
                }
                return sharedProduct;
            }
            return new Widget(sequence.incrementAndGet());
        }

        @Override
        public Class<?> getObjectType() {
            return Widget.class;
        }

        @Override
        public boolean isSingleton() {
            return productSingleton;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        // Factory bean là singleton theo scope mặc định.
        // Product cũng được cung cấp theo singleton contract.
        @Bean("sharedWidget")
        public WidgetFactory sharedWidget() {
            return new WidgetFactory(true);
        }

        // Factory bean vẫn là singleton,
        // nhưng product được tạo mới khi tra cứu.
        @Bean("freshWidget")
        public WidgetFactory freshWidget() {
            return new WidgetFactory(false);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // ApplicationContext cũng cung cấp BeanFactory API.
            BeanFactory beanFactory = context;

            Widget shared1 =
                    beanFactory.getBean("sharedWidget", Widget.class);
            Widget shared2 =
                    beanFactory.getBean("sharedWidget", Widget.class);

            Widget fresh1 =
                    beanFactory.getBean("freshWidget", Widget.class);
            Widget fresh2 =
                    beanFactory.getBean("freshWidget", Widget.class);

            WidgetFactory factory1 =
                    beanFactory.getBean("&freshWidget", WidgetFactory.class);
            WidgetFactory factory2 =
                    beanFactory.getBean("&freshWidget", WidgetFactory.class);

            System.out.println("sharedSame=" + (shared1 == shared2));
            System.out.println("freshDifferent=" + (fresh1 != fresh2));
            System.out.println("sharedNumbers="
                    + shared1.number() + "," + shared2.number());
            System.out.println("freshNumbers="
                    + fresh1.number() + "," + fresh2.number());
            System.out.println("factorySame=" + (factory1 == factory2));
            System.out.println("factoryClass="
                    + factory1.getClass().getSimpleName());
            System.out.println("productClass="
                    + fresh1.getClass().getSimpleName());
            System.out.println("factorySingletonProduct="
                    + factory1.isSingleton());
            System.out.println("contextIsBeanFactory="
                    + (context instanceof BeanFactory));
        }
    }
}
```

Chạy với JDK 17+ và Gradle 8+:

```bash
gradle run --quiet
# Hoặc ./gradlew run --quiet nếu dự án đã có Gradle Wrapper.
```

**Các dòng chương trình tự in ra qua `System.out`:**

```text
sharedSame=true
freshDifferent=true
sharedNumbers=1,1
freshNumbers=1,2
factorySame=true
factoryClass=WidgetFactory
productClass=Widget
factorySingletonProduct=false
contextIsBeanFactory=true
```

Có thể có log framework tùy classpath/cấu hình; chúng không thay đổi các dòng `System.out` được liệt kê.

### Phân tích từng kết quả

1. Hai lần `getBean("sharedWidget")` trả **cùng một `Widget`**. Factory có `isSingleton()==true`, Spring có thể cache singleton product, còn chính factory cũng giữ identity của product trong `sharedProduct`.
2. Hai lần `getBean("freshWidget")` trả **hai `Widget` khác nhau**, vì FactoryBean báo `isSingleton()==false` và `getObject()` tạo product mới.
3. Sequence của mỗi factory độc lập. Vì thế product singleton có số `1` hai lần, còn non-singleton có số `1` rồi `2`.
4. Hai lần `getBean("&freshWidget")` trả **cùng một factory instance**: definition `freshWidget` có scope singleton mặc định.
5. Kiểu factory là `WidgetFactory`; kiểu product là `Widget`. Chúng là hai Java objects khác nhau.
6. `factorySingletonProduct=false` mô tả **product cache policy** của factory, dù chính `WidgetFactory` là singleton.
7. `contextIsBeanFactory=true` vì `ApplicationContext` mở rộng khả năng BeanFactory. `BeanFactory` không phải một `WidgetFactory`.

**Lưu ý của ví dụ:** `WidgetFactory.getObject()` được đồng bộ bằng `synchronized` để minh họa shared-product initialization an toàn khi bị gọi đồng thời. Mã vẫn thực hiện logic độc lập trong mỗi factory, không dùng static cache; ứng dụng thật cần chọn synchronization/caching phù hợp với tải và lifecycle.

## 8. @Bean factory method khác FactoryBean

Trong Java configuration, cú pháp `@Bean` trên một method thường đã tạo đủ bean:

```java
@Configuration(proxyBeanMethods = false)
class RegularConfig {
    @Bean
    Widget widget() {
        return new Widget(42);
    }
}
```

Đây là mảnh minh họa. `widget()` là **factory method** theo nghĩa thông thường: Spring gọi method để tạo bean kiểu `Widget`. Nó **không tự biến `RegularConfig` thành implementation của `FactoryBean<Widget>`**.

So sánh ba tình huống:

| Cách đăng ký | Object được container nhận từ definition | `getBean("widget")` |
| --- | --- | --- |
| `@Bean Widget widget()` | Bean `Widget` thông thường | Trả `Widget` |
| `@Bean WidgetFactory widget()` với `WidgetFactory implements FactoryBean<Widget>` | Bean `WidgetFactory` đặc biệt | Trả `Widget` là product; `&widget` trả factory |
| XML definition class implement `FactoryBean` | Bean implement FactoryBean | Trả product; `&widget` trả factory |

Một `@Bean` method có thể trả về một `FactoryBean` và khi đó Spring áp dụng dereference/product semantics. Điều làm nên `FactoryBean` không phải tên method chứa chữ “factory”, mà là **instance thực sự implement `org.springframework.beans.factory.FactoryBean`**.

### Khi nào dùng FactoryBean thay cho @Bean method?

Chọn factory method `@Bean` nếu việc tạo đối tượng dễ diễn đạt:

```java
@Bean
HttpClient httpClient() {
    return HttpClient.newHttpClient();
}
```

Mảnh minh họa giả định `java.net.http.HttpClient` trên Java 17+. Phương thức thông thường đã đủ.

Cân nhắc `FactoryBean` khi cần tích hợp một abstraction tạo đối tượng phức tạp vào **container type matching và lookup semantics**, ví dụ một proxy, dynamic client, object do nhà cung cấp bên ngoài xây dựng, hoặc một framework infrastructure muốn quản lý factory riêng với product. Trong business code đơn giản, `@Bean` method hoặc một factory service thuần Java thường rõ ràng hơn.

## 9. FactoryBean khác factory method và ObjectFactory<T>

Ba khái niệm đều có chữ “factory”:

**`@Bean` factory method:** Spring gọi phương thức cấu hình để tạo bean. Kết quả có thể là bean bình thường hoặc một `FactoryBean`.

**`FactoryBean<T>`:** hợp đồng đặc biệt được container hiểu; có `getObject()`, `getObjectType()` và `isSingleton()`. Bean name thông thường lộ ra product, `&name` lộ ra factory.

**`ObjectFactory<T>`:** interface rất nhỏ với `T getObject()`, thường dùng để yêu cầu một object theo nhu cầu, ví dụ được inject vào singleton để lấy prototype; bản thân object implement `ObjectFactory` không mặc định có cơ chế prefix `&`.

Mẫu inject từ container:

```java
@Service
class ReportRunner {
    private final ObjectProvider<ReportTask> tasks;

    ReportRunner(ObjectProvider<ReportTask> tasks) {
        this.tasks = tasks;
    }

    void run() {
        ReportTask task = tasks.getObject();
        task.execute();
    }
}
```

Đây là **mảnh minh họa**, cần imports và định nghĩa `ReportTask`, `@Service`, `ObjectProvider` tương ứng. `ObjectProvider` mở rộng khả năng lookup linh hoạt; nếu `ReportTask` có scope prototype, mỗi `getObject()` có thể tạo instance mới.

Không nhầm `ObjectProvider<T>` (client-side lookup hỗ trợ injection) với `FactoryBean<T>` (container-level extension thay đổi cách bean name công bố product).

## 10. Vòng đời của FactoryBean và product

Đây là một giới hạn dễ bị bỏ sót khi xây `FactoryBean` cung cấp socket, connection pool, HTTP client hoặc resource nặng.

### 10.1. FactoryBean object có lifecycle bình thường

Nếu factory là singleton do context quản lý, bản thân nó được tạo và khởi tạo theo bean lifecycle: dependency injection, init callbacks, BeanPostProcessors và destruction callbacks khi context đóng. Có thể dùng `DisposableBean` hoặc một custom destroy method trên **factory**.

### 10.2. Product không mặc nhiên có destruction lifecycle đầy đủ

Theo Javadoc của `FactoryBean`, container chịu trách nhiệm quản lý lifecycle của **FactoryBean instance**; product từ `getObject()` **không tự có cùng destruction lifecycle** chỉ vì được expose qua `getBean("name")`. Đặc biệt không được kỳ vọng Spring tự gọi `AutoCloseable.close()` của product khi context đóng.

Ví dụ factory quản lý product singleton cần close:

```java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.FactoryBean;

final class ClientFactory
        implements FactoryBean<ManagedClient>, DisposableBean {

    private ManagedClient client;

    @Override
    public synchronized ManagedClient getObject() {
        if (client == null) {
            client = new ManagedClient();
        }
        return client;
    }

    @Override
    public Class<?> getObjectType() {
        return ManagedClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() throws Exception {
        if (client != null) {
            client.close();
        }
    }
}
```

Đây là **mảnh class minh họa**, cần `ManagedClient implements AutoCloseable` với constructor phù hợp và không phải file Java hoàn chỉnh để chạy độc lập. Factory có trách nhiệm đóng product khi factory bị hủy. Nên viết cleanup idempotent và lưu ý thread safety, exception, ownership nếu product dùng chung.

Với `isSingleton()==false`, caller có thể nhận nhiều product khác nhau; nếu mỗi product mang tài nguyên cần close, phải thiết kế một trong các chiến lược rõ ràng: caller tự close sau mỗi việc, factory theo dõi để close có kiểm soát, hoặc tạo scoped resource có lifecycle hỗ trợ. Không thể chỉ viết `FactoryBean.destroy()` rồi giả định mọi product từng tạo đã được đóng.

### Product và BeanPostProcessor

Spring có thể áp dụng **một số post-processing** cho product trả về từ FactoryBean (đáng chú ý post-processing sau khởi tạo), nhưng điều đó **không tương đương** việc product được tạo như một bean definition thông thường với toàn bộ init và destroy callbacks. Không dựa vào việc `@PostConstruct` của product chắc chắn được gọi tự động chỉ vì class product có annotation. Nếu product cần initialization rõ ràng, làm trong factory hoặc thiết kế bean definition bình thường phù hợp.

## 11. getObjectType() và autowiring theo kiểu

Một container có thể phải trả lời “có bean kiểu `PaymentGateway` không?” **trước khi tạo product**. Do đó việc FactoryBean công bố đúng type là điều kiện cho wiring ổn định.

Implementation tốt:

```java
@Override
public Class<?> getObjectType() {
    return PaymentGateway.class;
}
```

Đây là mảnh minh họa. Factory trả về một object compatible với `PaymentGateway`. Lợi ích:

- `getBeanNamesForType(PaymentGateway.class)` có cơ sở tìm candidate.
- Constructor injection `PaymentGateway gateway` có thể được resolve khi chỉ có một bean phù hợp.
- Các IDE/tooling và các phép kiểm tra type có metadata đáng tin.

Implementation rủi ro:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Có side effect tạo product!
}
```

Đây là anti-pattern: type introspection có thể thực thi `getObject()` sớm, tạo resource/khởi động kết nối khi container còn xây dựng metadata hoặc trong lúc scanning. Điều này có thể kéo theo circular dependency và initialization không đúng thứ tự.

Nếu runtime type thực sự dynamic, hãy công bố một interface/supertype ổn định mà mọi product thỏa mãn; chỉ trả `null` khi contract thực sự không thể xác định type.

`FactoryBean.OBJECT_TYPE_ATTRIBUTE` còn cho phép khai báo kiểu product trên bean definition metadata trong một số trường hợp, để container tra cứu type mà không cần instantiate factory. Đây là chi tiết mở rộng dành cho infrastructure, không phải điều bắt buộc trong phần lớn custom FactoryBean.

## 12. Nếu getObject() ném exception hoặc trả null?

`FactoryBean.getObject()` khai báo `throws Exception`. Khi nó thất bại, lời gọi `BeanFactory.getBean("name")` thường được Spring chuyển thành một exception liên quan bean creation, mang cause của lỗi ở factory.

Một số tình huống:

- **Sai configuration:** constructor hoặc `getObject()` ném exception khi không thể tạo product.
- **Circular reference / factory chưa sẵn sàng:** implementation có thể ném `FactoryBeanNotInitializedException` để báo factory chưa thể tạo object.
- **Trả `null`:** contract cho phép trả `null` trong vài trường hợp; Spring có semantics nội bộ để biểu diễn null bean. Nhưng consumer bắt buộc non-null sẽ khó hoạt động. Với product thiết yếu, trả type/object rõ ràng và ném exception có ý nghĩa nếu không tạo được.
- **Thread safety:** nhiều concurrent lookups có thể chạm logic factory. Với shared product, bảo đảm đồng bộ; với prototype, tránh giữ mutable shared state không an toàn.
- **Cache và retry:** đừng đưa product hỏng vào shared cache rồi để mọi lần tra cứu sau nhận lại object không hợp lệ.

Khi product là remote client có thể không connect, đừng tạo kết nối trong `getObjectType()`. Nếu initialization có thể thất bại sau khi đã mở tài nguyên, cleanup trong `getObject()` với `try/finally` hoặc một helper rõ ràng để tránh leak trước khi return.

## 13. SmartFactoryBean: mở rộng singleton và eager-init metadata

Spring có interface `SmartFactoryBean<T> extends FactoryBean<T>`, cung cấp thêm thông tin cho container:

- `isPrototype()`: cho biết product có thực sự là **một instance độc lập** mỗi lần được tạo hay không.
- `isEagerInit()`: gợi ý factory và singleton product có cần được khởi tạo sớm trong vòng pre-instantiation hay không.

Đặc biệt:

```text
FactoryBean.isSingleton() == false
        không luôn suy ra
SmartFactoryBean.isPrototype() == true
```

Vì “không singleton” có thể là object gắn với một scope khác, vẫn được tái sử dụng trong một khoảng sống cụ thể. `SmartFactoryBean` chủ yếu cho infrastructure/collaborating frameworks; custom factories của ứng dụng thường dùng `FactoryBean` là đủ.

Một `FactoryBean` thông thường không nhất thiết tạo **product** trong startup eager singleton pass, ngay cả khi **factory** singleton được instantiate. Product thường được tạo theo nhu cầu; `SmartFactoryBean.isEagerInit()` có thể thay đổi điều đó.

## 14. Đặt cạnh BeanFactoryPostProcessor và BeanPostProcessor

Có một nhóm tên khác cũng dễ nhầm:

| Thành phần | Thao tác trên | Thời điểm |
| --- | --- | --- |
| `BeanFactory` | Container API cho bean graph | Xuyên suốt vòng đời |
| `FactoryBean<T>` | Tạo/expose product của một bean factory đặc biệt | Khi container cần product, theo cache/scope |
| `BeanFactoryPostProcessor` | BeanFactory và bean definition metadata | Trước vòng tạo singleton thông thường |
| `BeanDefinitionRegistryPostProcessor` | Registry bean definitions, có thể thêm definitions | Trước BFPP thường |
| `BeanPostProcessor` | Bean instances | Trong quá trình khởi tạo từng bean |

Một `FactoryBean` có thể đồng thời mang interface lifecycle nếu cần. Nhưng điều đó **không biến nó thành `BeanFactoryPostProcessor`**. Chữ “Factory” có trong tên không có nghĩa API cùng vị trí trong lifecycle.

Ví dụ dùng `BeanFactoryPostProcessor` để thay đổi scope metadata trước khi bean được tạo là extension point khác hẳn custom `FactoryBean` dùng để tạo client.

## 15. Dependency injection: lấy factory hay lấy product?

Giả sử bạn có:

```java
@Bean("gateway")
GatewayFactory gatewayFactory() {
    return new GatewayFactory();
}
```

Đây là mảnh minh họa, giả định `GatewayFactory implements FactoryBean<Gateway>`.

Consumer muốn **product** thường inject interface product:

```java
@Service
class PaymentService {
    private final Gateway gateway;

    PaymentService(Gateway gateway) {
        this.gateway = gateway;
    }
}
```

Nếu type matching xác định duy nhất product, Spring resolve dependency cho `Gateway`. Consumer business không cần biết factory thực hiện như thế nào.

Consumer muốn **factory** chỉ trong code hạ tầng có thể truy xuất qua `&gateway`:

```java
GatewayFactory factory =
        context.getBean("&gateway", GatewayFactory.class);
```

Hoặc kiến trúc có thể expose một bean facade/management interface riêng để không buộc consumer biết prefix Spring.

**Tránh injecting `BeanFactory` chỉ để lấy một dependency cố định.** Ví dụ:

```java
@Service
class FragilePaymentService {
    @Autowired
    BeanFactory container;

    void pay() {
        Gateway gateway = container.getBean("gateway", Gateway.class);
    }
}
```

Mảnh trên không phải chương trình hoàn chỉnh. Nó tạo coupling với bean name dạng chuỗi. Constructor injection với `Gateway` thường đơn giản, type-safe và dễ test hơn. Với nhu cầu lấy một prototype nhiều lần, cân nhắc `ObjectProvider<Gateway>`.

## 16. Kiểm thử FactoryBean và BeanFactory

### Kiểm thử factory như một Java class

Có thể test trực tiếp `WidgetFactory` trong ví dụ mục 7:

```java
WidgetFactory factory = new WidgetFactory(false);
Widget one = factory.getObject();
Widget two = factory.getObject();

assert one != two;
assert factory.getObjectType() == Widget.class;
assert !factory.isSingleton();
```

Đây là snippet minh họa, giả định các class lồng được import hoặc tham chiếu đầy đủ qua `FactoryDifferenceDemo`; dùng `-ea` nếu chạy Java `assert`. Unit test này xác minh **logic của FactoryBean**, nhưng **chưa** xác minh container dereference và product caching.

### Kiểm thử thông qua Spring container

Trong integration test, nên kiểm tra:

```java
Object product = context.getBean("sharedWidget");
Object underlyingFactory = context.getBean("&sharedWidget");

assert product instanceof Widget;
assert underlyingFactory instanceof WidgetFactory;
assert context.getBean("sharedWidget") == product;
```

Đây là snippet minh họa (biến `context` từ ví dụ chính). Nó chứng minh Spring hiểu hợp đồng FactoryBean. Kiểm tra lifecycle riêng nếu factory tạo resource có `close()`.

### Kịch bản tối thiểu cần xác minh

1. `getBean("x")` trả đúng product type.
2. `getBean("&x")` trả factory, không phải product.
3. `FactoryBean.getObjectType()` thông báo type đúng, không instantiate product chỉ để đo type.
4. `isSingleton=true` và `getObject()` thực sự cấp cùng product identity.
5. `isSingleton=false` và implementation thật sự cấp product mới nếu yêu cầu prototype.
6. Factory singleton hay prototype được tạo theo scope đã cấu hình.
7. Factory cleanup do Spring quản lý, product cleanup do chính factory/caller quản lý nếu cần.
8. Lỗi từ `getObject()` được báo ra đúng thay vì trả product hỏng.
9. Nếu nhiều product candidates cùng type, constructor injection phải có qualifier/name rõ ràng.

Trong JUnit 5, ưu tiên `assertSame`/`assertNotSame` khi so sánh identity. `equals` chỉ kiểm tra giá trị, không chứng minh hai object có cùng reference.

## 17. Lỗi thường gặp và cách sửa

| Lỗi/triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getBean("factoryName")` trả client thay vì factory class | FactoryBean được Spring dereference mặc định thành product | Gọi `getBean("&factoryName")` để lấy factory |
| `getBean("&regularBean")` báo `BeanIsNotAFactoryException` | Bean đích không implements `FactoryBean` | Bỏ `&` hoặc dùng đúng bean factory definition |
| Product được lấy nhiều lần vẫn cùng reference | `isSingleton()` mặc định `true`, container cache product | Override `isSingleton()` trả `false` khi product thực sự non-singleton |
| Product thay đổi dù factory trả `true` | Factory vi phạm singleton product contract | Giữ shared instance, bảo đảm thread-safe initialization |
| Hai lần `&name` cùng một factory nhưng product khác nhau | Factory scope singleton, `isSingleton=false` | Đây là trường hợp hoàn toàn hợp lệ, không phải bug |
| Inject product theo type không tìm ra bean | `getObjectType()` trả `null` hoặc type không đúng | Công bố type phù hợp, tránh khởi tạo product trong method này |
| Constructor/factory unexpectedly chạy khi xem type | `getObjectType()` gọi `getObject()` hoặc type inspection ép factory init | Bỏ side effect; thiết kế metadata sẵn có |
| `AutoCloseable.close()` của product không chạy lúc context close | Product không tự nhận đầy đủ destruction lifecycle | Factory cleanup/delegate hoặc caller quản lý tài nguyên |
| Tưởng `@Bean` method là `FactoryBean` | Nhầm method tạo bean với interface FactoryBean | Kiểm tra return object có implements interface không |
| Product không sẵn sàng lúc startup | FactoryBean thường tạo product on demand | Gọi đúng nơi cần; dùng SmartFactoryBean nếu thực sự cần eager semantics |
| Test product qua `new FactoryBean` nhưng pass integration giả | Không kiểm tra dereference/caching của Spring | Thêm test với ApplicationContext thật |
| Factory phụ thuộc quá nhiều business beans khi context bootstrap | Phát sinh early initialization/circular dependency | Giữ factory hạ tầng gọn, tránh side effect trong `getObjectType()` |

## 18. Khi nào nên tự viết FactoryBean?

FactoryBean hữu ích khi một loại product cần cách tạo khác hẳn định nghĩa bean thông thường, nhất là khi product:

- Là **dynamic proxy** hoặc object cần proxy configuration phức tạp.
- Được tạo bởi SDK/runtime đặc biệt, không có constructor/factory method phù hợp để đăng ký trực tiếp.
- Có kiểu interface ổn định nhưng implementation phải được build theo metadata runtime.
- Cần tùy biến cách Spring nhìn thấy object type, singleton-status hoặc lazy/eager product semantics.
- Là một thành phần hạ tầng cần được tái sử dụng từ nhiều bean definitions.

Nhưng nếu bài toán chỉ là **tạo một HttpClient có vài tham số cấu hình**, một `@Bean` factory method thường là giải pháp dễ bảo trì hơn. Nếu bài toán chỉ là **singleton muốn lấy prototype mới mỗi lần**, dùng `ObjectProvider<T>` hoặc method injection thay vì dựng một FactoryBean mới một cách không cần thiết.

Quyết định dựa trên **vai trò container integration** của FactoryBean, không chỉ vì nó có chữ “factory” trong tên.

## 19. Checklist thực hành

- Bean cần custom creation hay chỉ cần một `@Bean` method thông thường?
- Class có thực sự `implements FactoryBean<Product>` không?
- `getObjectType()` có trả type phù hợp, không side effect không?
- `isSingleton()` có đúng với identity product do `getObject()` cung cấp không?
- Factory bean definition scope là singleton hay prototype?
- Cần lấy product `"name"` hay factory `"&name"`?
- Factory có thể được Spring hỏi type trước khi init hoàn tất không?
- Product có tài nguyên cần close không và ai sở hữu lifecycle đó?
- Có concurrency khi nhiều thread tra cứu product không?
- Có cần `SmartFactoryBean.isEagerInit()` hoặc chỉ on-demand là đủ?
- Unit test của factory và integration test của container đã phân biệt chưa?

## 20. Tài liệu chính thức

- [Spring Framework Reference — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): ba method của FactoryBean và cú pháp `&beanName`.
- [Spring Framework 6.2 Javadoc — FactoryBean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html): hợp đồng `getObject`, `getObjectType`, `isSingleton` và lifecycle product/factory.
- [Spring Framework 6.2 Javadoc — BeanFactory](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/BeanFactory.html): container API, `FACTORY_BEAN_PREFIX`, lookup và scope queries.
- [Spring Framework 6.2 Javadoc — SmartFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html): metadata `isPrototype`, `isEagerInit`.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype và trách nhiệm lifecycle.

**Mô hình cần nhớ:** `BeanFactory` là **container**; `FactoryBean<T>` là **một bean factory đặc biệt nằm trong container**; `getBean("x")` trả **product** và `getBean("&x")` trả **factory**. Scope của factory, singleton-status của product và ownership của resource là ba điều phải đánh giá riêng.
