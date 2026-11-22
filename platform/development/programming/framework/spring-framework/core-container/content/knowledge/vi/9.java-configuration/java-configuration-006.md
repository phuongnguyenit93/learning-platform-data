# Chế độ đầy đủ của `@Configuration` và lớp tăng cường CGLIB trong Spring Framework

## 1. Vấn đề: gọi phương thức `@Bean` có phải luôn tạo object mới?

Hãy xem một lớp cấu hình Java:

```java
@Configuration
class ApplicationConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Vehicle car() {
        return new Vehicle(engine());
    }

    @Bean
    Vehicle truck() {
        return new Vehicle(engine());
    }
}
```

Đây là **đoạn minh họa**; `Engine` và `Vehicle` là class ứng dụng chưa khai báo. Trong Java thông thường, hai lời gọi `engine()` bên trong `car()` và `truck()` sẽ chạy thân method hai lần và tạo hai object `new Engine()` khác nhau. Nhưng khi `ApplicationConfig` được Spring xử lý như một lớp `@Configuration` **đầy đủ (full mode)**, các lời gọi qua lại giữa phương thức `@Bean` được can thiệp: Spring có thể chuyển hướng sang BeanFactory, nhờ đó cả `car` và `truck` cùng nhận **bean `engine` singleton**.

Cơ chế đó là **CGLIB enhancement**: Spring tạo một lớp con runtime của configuration class rồi chặn các lời gọi phù hợp tới `@Bean` methods. Đây là hành vi được bật mặc định bởi:

```java
@Configuration(proxyBeanMethods = true)
```

Thông thường chỉ cần viết `@Configuration` vì `proxyBeanMethods` mặc định là `true`.

Tuy nhiên, khi đổi sang:

```java
@Configuration(proxyBeanMethods = false)
```

Spring **không tăng cường các `@Bean` methods để chặn lời gọi trực tiếp**. Lời gọi `engine()` từ `car()` là lời gọi Java thông thường, có thể tạo thêm object **không phải** singleton bean `engine` do container đăng ký. Cả hai chế độ đều cho phép Spring xử lý `@Bean` và đăng ký các beans; khác biệt nằm ở **ngữ nghĩa của lời gọi method Java**, không phải ở việc `@Bean` có còn hoạt động hay không.

Bài học tập trung vào:

- Full `@Configuration`, lớp con CGLIB được sinh động và việc gọi giữa các `@Bean` methods;
- cơ chế singleton/scope, vòng đời và AOP khi tham chiếu bean qua phương thức;
- giới hạn của full mode (class/method `final`, `private`, `static`), so với lite mode;
- lựa chọn `proxyBeanMethods=false` và dependency injection qua tham số `@Bean`;
- cách không nhầm configuration enhancement với Spring AOP proxy;
- ví dụ Java 17+ thực chạy với Spring Context, phân tích stdout, lỗi thường gặp và bài tập.

## 2. `@Configuration` là nguồn bean definitions

`@Configuration` thuộc package `org.springframework.context.annotation`. Nó đánh dấu một class chứa thông tin cấu hình Java, thường thông qua các method gắn `@Bean`:

```java
@Configuration
public class BillingConfiguration {

    @Bean
    PaymentClient paymentClient() {
        return new PaymentClient("local");
    }
}
```

Đoạn này minh họa, chưa chạy độc lập khi thiếu class `PaymentClient`. Spring cần biết đến `BillingConfiguration` qua đăng ký trực tiếp, component scan, `@Import` hoặc cơ chế cấu hình khác. Bản thân sự xuất hiện của annotation trong source không tự khởi động container.

Khi cấu hình được xử lý, Spring đăng ký **bean definitions** từ `@Bean` methods. Sau đó container tạo object khi cần theo scope, dependency, lazy flag và quá trình refresh. Mặc định scope của một `@Bean` là **singleton trong một BeanFactory**.

Điểm khác biệt cần phân biệt:

1. Spring gọi factory method `@Bean` khi tạo managed bean.
2. Code ứng dụng **tự gọi** method `@Bean` trên một configuration object.

Trong full mode, lời gọi loại 2 trên **đối tượng configuration đã được Spring tăng cường và quản lý** có thể được chuyển thành lookup container; trong lite mode lời gọi ấy vẫn là Java bình thường. Đây chính là lý do tồn tại `proxyBeanMethods`.

## 3. Full mode hoạt động như thế nào?

### 3.1. Lớp con được tăng cường

Giả sử class cấu hình tên `DemoConfig`. Khi xử lý full mode, Spring có thể sinh một kiểu runtime có quan hệ kế thừa tương tự:

```text
                DemoConfig
                    ^
                    |
          DemoConfig$$SpringCGLIB$$...
                    |
                    v
        Configuration bean trong Spring
```

Tên class được sinh là **chi tiết triển khai**, không nên hard-code, parse hoặc dùng như API. Spring sử dụng CGLIB được đóng gói trong module `spring-core` (namespace `org.springframework.cglib`), không cần khai báo một dependency CGLIB riêng trong ví dụ Spring Context thông thường.

Để hình dung cơ chế, mã giả **không phải mã nguồn Spring thật**:

```java
// Mã giả giải thích ý tưởng, KHÔNG chạy độc lập.
@Override
Engine engine() {
    if (thisCallIsBeingUsedByBeanFactoryToCreateEngine()) {
        return super.engine(); // Factory body thật tạo bean.
    }
    return beanFactory.getBean("engine", Engine.class);
}
```

Mục đích của interceptor là phân biệt **lời gọi được BeanFactory dùng để tạo bean** với **lời gọi tham chiếu bean đã được quản lý**. Nếu mọi lời gọi đều đơn giản tự quay lại BeanFactory mà không có phân biệt, việc factory đang tạo chính bean đó có thể dẫn đến đệ quy. Cơ chế thực tế còn xử lý scoping, trạng thái bean, type metadata và những tình huống đặc thù khác.

### 3.2. Luồng tạo singleton và inter-bean call

```text
Spring đăng ký:
  "engine" -> DemoConfig.engine()
  "car"    -> DemoConfig.car()
  "truck"  -> DemoConfig.truck()

Khi Spring tạo "car":
  BeanFactory gọi factory car()
    |
    v
  Car factory gọi engine()
    |
    v
  CGLIB interceptor kiểm tra "engine"
    |
    +-- Đã có managed singleton? -> dùng bean đã có
    |
    +-- Chưa có? -> yêu cầu BeanFactory tạo/lấy "engine"
    |
    v
  car nhận tham chiếu Engine do Spring quản lý

Khi Spring tạo "truck":
  truck factory gọi engine()
    |
    v
  CGLIB redirect tới cùng singleton "engine"
```

Đây là sơ đồ **ngữ nghĩa với singleton mặc định**, không mô tả máy trạng thái nội bộ đầy đủ. Kết quả quan trọng là `car.engine() == truck.engine()` **và** cả hai bằng `context.getBean(Engine.class)` khi cấu hình phù hợp.

### 3.3. Full mode không phải caching chung mọi lời gọi

CGLIB enhancement tôn trọng **bean scope** và container semantics, không đơn giản cache mọi giá trị method Java.

- `singleton`: với các reference thông thường, cùng managed instance được tái sử dụng trong một container.
- `prototype`: BeanFactory tạo instance theo mỗi lần resolve; một inter-bean call có thể nhận một prototype mới.
- web/custom scope: kết quả phụ thuộc scope đang active và khả năng sử dụng bean trong ngữ cảnh đó.
- nếu BeanFactory tạo proxy AOP hay scoped proxy cho bean, cross-method lookup có thể nhận **reference do container công bố**, không nhất thiết raw object được tạo trực tiếp bằng `new` trong factory.

Vì thế đừng hiểu full mode là “mọi `@Bean` method chỉ chạy đúng một lần” trong mọi scope. Phát biểu đó chỉ tương ứng với tình huống singleton bình thường và không có nguyên nhân khác kích hoạt factory theo cơ chế riêng.

## 4. Các lời gọi cần và không cần được chặn

| Tình huống | Full `@Configuration` (`proxyBeanMethods=true`) | `proxyBeanMethods=false` / lite |
| --- | --- | --- |
| BeanFactory gọi method để tạo bean | Method chạy để tạo managed instance | Method chạy để tạo managed instance |
| `car()` gọi `engine()` trong cùng config | Inter-bean call được chặn nếu method đủ điều kiện; trả reference theo BeanFactory | Lời gọi Java thường; có thể `new Engine()` thêm |
| `context.getBean("engine")` | Trả managed bean theo scope | Trả managed bean theo scope |
| `config.engine()` trên configuration bean được Spring quản lý | Có thể được chặn và trả bean từ container | Chạy method Java thường |
| `new Config().engine()` ngoài Spring | Không có interceptor do container tạo | Chạy Java thường |
| Bean được khai báo bằng `@Bean` có singleton scope | Có | Có |
| Constructor/method parameter injection | Có | Có |
| Lớp configuration có thể `final` | Không ở full mode vì cần subclass | Có thể, nếu không còn các ràng buộc khác |
| Interception qua `static @Bean` method | Không áp dụng kiểu virtual override | Không áp dụng |
| Có lớp con CGLIB vì bean method interception | Có | Không cần vì mục đích này |

**Đừng nói `proxyBeanMethods=false` tắt Spring bean management.** Nó chỉ tắt **proxying của `@Bean` methods** tại configuration class. Bean definitions, dependency resolution và lifecycle vẫn do Spring quản lý như thông thường.

### 4.1. Lời gọi từ config khác

Nếu một bean được truy xuất thông qua **managed instance của full configuration class**, lời gọi `@Bean` method có thể được interceptor chuyển thành lookup container ngay cả khi code gọi từ nơi khác. Tuy nhiên, truyền trực tiếp dependency vào method `@Bean` hoặc constructor vẫn dễ theo dõi và ít ràng buộc hơn giữa các configuration classes.

Không lấy configuration bean làm **service locator** rồi gọi `config.someBean()` khắp ứng dụng: điều đó làm business code phụ thuộc vào class cấu hình và proxy mode.

### 4.2. Khi self-invocation khác Spring AOP

Một hiểu nhầm rất thường gặp: “Spring AOP proxy không intercept self-invocation; tại sao `car()` gọi `engine()` lại được chặn?”

Hai cơ chế không giống nhau:

- **CGLIB enhancement của full `@Configuration`**: Spring tạo subclass của configuration class để chặn các `@Bean` method calls, bao gồm inter-bean calls xảy ra trong configuration code phù hợp.
- **Spring AOP** với `@Transactional`, `@Cacheable`, v.v.: thường là một proxy khác bao quanh target bean. Khi method của target gọi một method khác trên chính target qua `this`, self-invocation thông thường không đi qua AOP proxy.

Không thể suy ra ngữ nghĩa Spring AOP từ cơ chế `@Bean` interception. Full configuration không tự bật transaction, caching hoặc HTTP handling.

## 5. Cấu hình lite: khi nào và vì sao dùng `proxyBeanMethods=false`?

Từ Spring Framework 5.2, `@Configuration` cung cấp tùy chọn:

```java
@Configuration(proxyBeanMethods = false)
public class SimpleConfiguration {
    @Bean
    Formatter formatter() {
        return new Formatter();
    }
}
```

Trong cấu hình này, Spring vẫn phát hiện method `formatter()` và có thể tạo singleton bean `formatter`. Nhưng phương thức **không được override để thực thi inter-bean interception**.

Khi các factory methods **độc lập** và không dùng lời gọi Java `someBean()` sang method `@Bean` khác, proxying mang lại ít giá trị. Tắt interception:

- bỏ nhu cầu tạo CGLIB subclass cho mục đích chặn `@Bean` methods;
- loại bỏ những giới hạn subclassing tương ứng đối với configuration class/method;
- có thể giảm một phần chi phí cấu hình ban đầu, nhưng **không bảo đảm** mọi ứng dụng sẽ startup nhanh hơn đáng kể;
- làm semantics của lời gọi Java rõ ràng: gọi method nghĩa là chạy method body.

Một ví dụ nên dùng:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Vehicle car(Engine engine) {
        return new Vehicle(engine);
    }

    @Bean
    Vehicle truck(Engine engine) {
        return new Vehicle(engine);
    }
}
```

Đây là **đoạn minh họa** cần class `Engine`/`Vehicle`. BeanFactory **resolve `Engine` làm tham số** trước khi gọi `car(...)`/`truck(...)`, nên cả hai có thể nhận cùng singleton được quản lý mà không cần tự gọi `engine()` qua CGLIB.

### 5.1. Lite mode không chỉ có `@Configuration(proxyBeanMethods=false)`

Theo quy ước Spring, `@Bean` methods khai báo trong các class **không đánh dấu `@Configuration` đầy đủ**, ví dụ một class `@Component`, cũng có semantics “lite” khi được xử lý. Những method này là factory methods được container sử dụng; inter-bean calls **không** được bảo đảm chuyển qua container.

```java
@Component
class UtilityFactories {

    @Bean
    Formatter formatter() {
        return new Formatter();
    }

    @Bean
    Printer printer() {
        return new Printer(formatter()); // Plain Java call.
    }
}
```

Đây là mã **minh họa**, cần `Formatter`/`Printer` và scanning. Để tránh object ngoài managed lifecycle, viết `printer(Formatter formatter)` rồi tạo `new Printer(formatter)`.

Khi một class chứa `@Bean` methods vừa mang `@Component` vừa `@Configuration`, semantics liên quan configuration processing cần xác định theo annotations thực tế; đừng chỉ nhìn tên class để suy luận.

## 6. Ràng buộc của full mode và CGLIB

CGLIB tăng cường bằng cách sinh subclass và override methods phù hợp. Những quy tắc Java về inheritance/override vì vậy rất quan trọng.

### 6.1. Configuration class không được `final` trong full mode

Ví dụ sai:

```java
@Configuration
public final class FinalConfig {
    @Bean
    Engine engine() {
        return new Engine();
    }
}
```

Đây là **ví dụ lỗi cấu hình**, không phải file chạy độc lập. Java `final` chặn kế thừa nên Spring không thể sinh lớp con phục vụ CGLIB enhancement. Trong full mode, configuration class phải có khả năng subclass. Có thể đổi class không `final` hoặc dùng `@Configuration(proxyBeanMethods=false)` nếu không cần inter-bean interception.

### 6.2. `@Bean` method trong full mode phải override được

Ví dụ không phù hợp:

```java
@Configuration
class InvalidConfig {

    @Bean
    private Engine engine() {
        return new Engine();
    }

    @Bean
    public final Vehicle car() {
        return new Vehicle(engine());
    }
}
```

Đây là **ví dụ lỗi**, không nên copy vào dự án chạy. Method `private` không thể override; method `final` không thể override. Full-mode `@Bean` methods cần đáp ứng ràng buộc để Spring có thể intercept. Dùng access modifier phù hợp và bỏ `final`, hoặc chuyển sang cấu hình lite với các method factory độc lập.

### 6.3. Static `@Bean` methods là trường hợp riêng

`static` methods thuộc class, không có virtual dispatch theo instance như instance methods; CGLIB không thể override theo cách tương tự. Spring hỗ trợ static `@Bean` factory methods cho những trường hợp hợp lệ, đặc biệt một số bean hạ tầng cần được khai báo static để khởi tạo đúng giai đoạn.

**Không giả định gọi `staticBeanMethod()` từ code Java sẽ được full configuration interceptor trả managed singleton.** Nếu bean khác cần dependency do static method tạo, truyền nó vào tham số method factory của bean tiêu thụ.

Một static `@Bean` method phù hợp khi cần đăng ký hạ tầng kiểu `BeanFactoryPostProcessor` trong các kịch bản nhất định, nhưng không có nghĩa mọi factory method nên static.

### 6.4. `private` constructors và Java modules

Tạo subclass động cũng chịu ảnh hưởng visibility, class loader và **Java Platform Module System** khi module path được sử dụng. Đừng gộp mọi `InaccessibleObjectException` vào lỗi “thiếu bean”. Nếu JPMS chặn reflection/enhancement, xem `exports`/`opens` cần thiết cho Spring.

Spring hỗ trợ nhiều kiểu constructor injection vào configuration class, nên **không bắt buộc phải có constructor public no-arg** chỉ để làm full `@Configuration`. Trường hợp có constructor dependency cần được container phân giải như các bean khác.

### 6.5. Tránh dựa vào nội bộ của CGLIB

Không lấy chuỗi `$$SpringCGLIB$$` từ class name để quyết định nghiệp vụ; tên class tăng cường có thể khác giữa phiên bản hoặc hoàn cảnh. Không dùng Java reflection bằng tên method sinh nội bộ. Hãy kiểm tra behavior qua managed bean identity, scopes và dependency contract.

## 7. Ví dụ Java 17+ hoàn chỉnh: ba kiểu configuration

Ví dụ dùng **Spring Framework 6.2.19**, chỉ cần `spring-context`. Chúng ta tạo **ba ApplicationContext riêng**:

1. **FULL**: `@Configuration` mặc định, `@Bean` methods gọi qua lại; tất cả tham chiếu Engine về cùng singleton.
2. **LITE_DIRECT**: `proxyBeanMethods=false` nhưng vẫn gọi `engine()` trực tiếp; tạo thêm Engine ngoài bean factory.
3. **LITE_PARAMETER**: `proxyBeanMethods=false` và truyền `Engine` qua tham số factory methods; trở lại dùng chung singleton managed bean.

### 7.1. Sơ đồ file

```text
spring-config-cglib-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ConfigurationModesDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-config-cglib-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'ConfigurationModesDemo'
}
```

Dùng JDK 17+ và phiên bản Gradle tương thích JDK. Không cần khai báo `cglib` riêng; CGLIB được đóng gói lại bên trong `spring-core` là dependency của Spring Context.

### 7.2. Mã Java hoàn chỉnh

Lưu file `src/main/java/ConfigurationModesDemo.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ConfigurationModesDemo {

    public static final class Engine {
        private static int constructions;

        public Engine() {
            constructions++;
        }

        public static void resetCount() {
            constructions = 0;
        }

        public static int created() {
            return constructions;
        }
    }

    public record Vehicle(Engine engine) {
    }

    // Full configuration: @Configuration có proxyBeanMethods = true.
    @Configuration
    public static class FullConfig {

        @Bean
        public Engine engine() {
            return new Engine();
        }

        @Bean
        public Vehicle car() {
            return new Vehicle(engine());
        }

        @Bean
        public Vehicle truck() {
            return new Vehicle(engine());
        }
    }

    // Lite: các method gọi nhau như Java thông thường.
    @Configuration(proxyBeanMethods = false)
    public static class LiteDirectConfig {

        @Bean
        public Engine engine() {
            return new Engine();
        }

        @Bean
        public Vehicle car() {
            return new Vehicle(engine());
        }

        @Bean
        public Vehicle truck() {
            return new Vehicle(engine());
        }
    }

    // Lite nhưng dùng Spring DI tại tham số @Bean.
    @Configuration(proxyBeanMethods = false)
    public static class LiteParameterConfig {

        @Bean
        public Engine engine() {
            return new Engine();
        }

        @Bean
        public Vehicle car(Engine engine) {
            return new Vehicle(engine);
        }

        @Bean
        public Vehicle truck(Engine engine) {
            return new Vehicle(engine);
        }
    }

    private static void inspect(
            String label, Class<?> configurationClass) {

        Engine.resetCount();
        try (var context =
                new AnnotationConfigApplicationContext(configurationClass)) {
            Engine managed = context.getBean(Engine.class);
            Vehicle car = context.getBean("car", Vehicle.class);
            Vehicle truck = context.getBean("truck", Vehicle.class);

            System.out.println("== " + label + " ==");
            System.out.println("managed==car: " +
                    (managed == car.engine()));
            System.out.println("managed==truck: " +
                    (managed == truck.engine()));
            System.out.println("car==truck: " +
                    (car.engine() == truck.engine()));
            System.out.println("enginesCreated: " + Engine.created());
        }
    }

    public static void main(String[] args) {
        inspect("FULL", FullConfig.class);
        inspect("LITE_DIRECT", LiteDirectConfig.class);
        inspect("LITE_PARAMETER", LiteParameterConfig.class);
    }
}
```

Đây là một file Java hợp lệ: chỉ `ConfigurationModesDemo` là top-level public class; ba configuration classes, `Engine` và record `Vehicle` là nested public static classes. Các method `@Bean` có tên `engine`, `car`, `truck` và được đăng ký riêng trong từng context.

`Engine.constructions` là counter phục vụ học tập; ví dụ chạy một thread duy nhất. Trong hệ thống concurrent, counter thật nên dùng công cụ thread-safe nếu cần đo số lần tạo object. Ta reset counter **trước khi tạo mỗi context**; mỗi lần `inspect` đóng context cũ trước khi bắt đầu lượt mới.

### 7.3. Lệnh chạy

Từ thư mục gốc dự án:

```bash
gradle run --quiet
```

Nếu sử dụng Gradle Wrapper:

```bash
./gradlew run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Các dòng do chương trình in:

```text
== FULL ==
managed==car: true
managed==truck: true
car==truck: true
enginesCreated: 1
== LITE_DIRECT ==
managed==car: false
managed==truck: false
car==truck: false
enginesCreated: 3
== LITE_PARAMETER ==
managed==car: true
managed==truck: true
car==truck: true
enginesCreated: 1
```

Đây là stdout từ `System.out.println`. Nếu môi trường cấu hình thêm logging, Gradle có thể hiển thị output khác không thuộc những dòng trên.

### 7.4. Vì sao FULL tạo đúng một Engine?

`FullConfig` mang `@Configuration` mặc định, nên Spring xử lý nó ở full mode, tăng cường bằng CGLIB. Với singleton `engine`:

- BeanFactory tạo managed `engine` một lần.
- `car()` gọi `engine()` qua đối tượng cấu hình đã tăng cường; interceptor trả reference managed bean.
- `truck()` cũng nhận cùng managed reference.
- `getBean(Engine.class)` trả cùng bean đó.

Vì vậy cả ba phép so sánh identity `==` là `true` và constructor `new Engine()` chạy đúng **một lần trong context FULL**.

### 7.5. Vì sao LITE_DIRECT tạo ba Engine?

`LiteDirectConfig` tắt interception. Container vẫn tạo một managed singleton `engine`, nhưng:

- `car()` thực hiện lời gọi Java `engine()` bình thường → một Engine mới **không phải managed singleton `engine`**.
- `truck()` gọi Java `engine()` bình thường → một Engine khác.
- BeanFactory vẫn giữ singleton `engine` riêng theo bean definition, vì `engine` được khai báo là `@Bean` và không lazy.

Tổng cộng có **ba Engine objects** được tạo trong context này. Car, truck và managed bean giữ ba references khác nhau nên cả ba phép `==` đều `false`.

Đáng chú ý: hai `Vehicle` vẫn là **Spring beans** vì được BeanFactory tạo từ các `@Bean` factory methods. Chỉ có các `Engine` được tạo bởi direct Java calls bên trong hai factory methods là các object riêng, không phải chính instance singleton `engine` từ BeanFactory.

### 7.6. Vì sao LITE_PARAMETER chỉ tạo một Engine?

`LiteParameterConfig` không dùng inter-bean direct call. Spring resolve dependency `Engine` trước khi gọi `car(Engine engine)` và `truck(Engine engine)`, truyền cùng managed singleton. Không cần tạo subclass CGLIB cho việc chặn `@Bean` methods. Do đó behavior sử dụng bean giống FULL trong ví dụ, mà phương pháp khai báo quan hệ phụ thuộc vẫn rõ ràng.

Đây là khuyến nghị chính trong ứng dụng hiện đại: **nếu đã chọn `proxyBeanMethods=false`, hãy truyền bean dependency qua tham số `@Bean` thay vì gọi method `@Bean` trực tiếp.**

### 7.7. Vì sao ví dụ dùng ba context?

Mỗi context đăng ký bean names `engine`/`car`/`truck` riêng; nếu trộn cả ba configs vào một context, sẽ xuất hiện tên trùng và semantics khác. Tách context cho phép so sánh đúng một biến: interception và cách diễn đạt dependency.

Cả ba context đều có singleton scopes. Ví dụ cố tình không dùng prototype vì khi đó số object mới theo scope sẽ làm so sánh kém rõ.

## 8. Tham số `@Bean` hay inter-bean call: chọn cách nào?

| Tiêu chí | Full `@Configuration` + gọi trực tiếp | `proxyBeanMethods=false` + tham số |
| --- | --- | --- |
| Cách viết | `return new Car(engine());` | `Car car(Engine engine) { return new Car(engine); }` |
| Ai resolve bean dependency | CGLIB interceptor chuyển qua BeanFactory | BeanFactory resolve method argument |
| Cần CGLIB enhancement cho config | Có | Không |
| Hạn chế `final` với config | Có | Không do bean method interception |
| Đọc dependency từ chữ ký | Không rõ bằng tham số | Rất rõ |
| Dùng được trong lite mode | Không có đảm bảo singleton/managed lookup với direct calls | Có |
| Di chuyển factory method sang config khác | Có thể cần đổi cách gọi | Thường ít coupling hơn |
| AOP/scoped bean semantics | BeanFactory bảo đảm theo lookup | BeanFactory bảo đảm khi resolve argument |
| Khả năng sai do tự gọi method | Nếu full thực sự được xử lý đúng, được bảo vệ | Nếu luôn dùng tham số, tránh vấn đề |

Không có quy tắc “full mode luôn xấu” hoặc “lite mode luôn tốt”: full mode có giá trị khi một cấu hình cố ý dùng inter-bean references qua các method Java. Khi không cần đặc tính đó, lite mode với method-parameter injection thường đơn giản hơn và tránh hạn chế subclassing.

### 8.1. Một số lưu ý với `@Bean` method trên config khác

Với hai configuration classes, gọi qua `otherConfig.engine()` có thể phụ thuộc việc `otherConfig` là enhanced managed bean hay chỉ là Java object thường. Thay vì wire chính configuration class vào service hoặc một configuration khác, truyền `Engine` trực tiếp vào factory method tiêu thụ.

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfig {

    @Bean
    FeatureService featureService(Engine engine) {
        return new FeatureService(engine);
    }
}
```

Đoạn trên **chỉ minh họa**: cần định nghĩa `FeatureService` và có bean kiểu `Engine` trong context.

## 9. Scope, `@Lazy` và các trường hợp không thể chỉ đếm constructor

### 9.1. Prototype: tạo mới là đúng thiết kế

Nếu `engine` có `@Scope("prototype")`, mỗi lần container thực hiện lookup prototype thông thường sẽ tạo instance mới. Full `@Configuration` khi inter-bean call thông qua BeanFactory cũng phải tôn trọng prototype scope; mục tiêu không phải luôn giữ một object cho mọi caller.

Trong khi đó, một singleton `Car` nhận prototype `Engine` qua factory method parameter thường giữ **một prototype đã resolve lúc tạo Car**. Muốn tạo Engine mới theo từng business operation, thiết kế `Car` nhận `ObjectProvider<Engine>` và gọi `getObject()` khi cần.

### 9.2. Lazy: trì hoãn tạo bean

`@Lazy` trên bean definition có thể ngăn pre-instantiate singleton không bắt buộc ở lúc context refresh. Nhưng nếu một singleton khác đang khởi tạo cần bean ấy, nó vẫn có thể phải được tạo. Full mode chặn inter-bean reference qua BeanFactory không có nghĩa mọi bean luôn eager; lite mode không có nghĩa mọi bean luôn lazy.

### 9.3. Proxy AOP và lifecycle

Khi BeanFactory áp dụng `BeanPostProcessor` để tạo AOP proxy, container có thể công bố một reference proxy thay vì raw instance. Inter-bean lookup qua full config giữ semantics của BeanFactory, điều này quan trọng cho những beans có transaction/security/caching aspects được cấu hình phù hợp.

Không nên gọi `new Service()` hoặc direct lite `@Bean` method rồi tự nhận object là cùng managed bean; các object tạo ngoài container không tự được inject/proxy/khởi tạo/hủy theo cùng managed lifecycle.

### 9.4. `FactoryBean` là một cơ chế khác

Spring có interface `FactoryBean<T>` dùng để tạo object do container quản lý theo quy tắc factory-specific. Một `@Bean` method trả `FactoryBean` có ngữ nghĩa lookup/production đặc biệt. Điều đó không đồng nghĩa CGLIB enhancement chỉ đơn giản cache raw return value. Nếu làm việc với `FactoryBean`, cần học riêng sự phân biệt factory bean và object do factory tạo.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `@Configuration` class là `final` và context báo lỗi | Full mode cần subclass CGLIB | Bỏ `final` hoặc dùng `proxyBeanMethods=false` khi không cần interception |
| `@Bean` method là `private`/`final` | Không override được trong full mode | Dùng method overridable hoặc lite mode với independent factory methods |
| Hai beans dùng hai đối tượng dependency khác nhau dù mong singleton | Lite config đang gọi trực tiếp `otherBean()` | Đổi sang method parameter injection |
| `getBean(Engine.class)` khác object tạo từ `new Config().engine()` | Configuration instance được tạo ngoài Spring | Chỉ lookup managed bean qua container hoặc injection |
| `@Configuration(proxyBeanMethods=false)` bị hiểu là tắt `@Bean` | Nhầm interception với bean definition processing | Spring vẫn đăng ký `@Bean` methods; chỉ không chặn direct calls |
| Full mode vẫn thấy nhiều objects | Target scope prototype hoặc code tự tạo ngoài container | Kiểm tra bean scope, lookup và call sites trước khi kết luận CGLIB hỏng |
| Bean singleton có method chạy nhiều lần vì gọi thủ công | Dùng lite method như factory Java | Không gọi direct method khi muốn container-managed reference |
| Thay bằng full mode để chữa mọi vấn đề DI | Sai dependency graph/thiếu bean/qualifier | Sửa cấu hình DI; proxyBeanMethods không tạo dependency còn thiếu |
| Spring AOP `@Transactional` không chạy khi self-call | AOP proxy self-invocation khác config CGLIB enhancement | Thiết kế lời gọi qua proxy/interface/service boundaries phù hợp |
| `@Bean` static method không bị CGLIB chặn | Static method không phải virtual method | Dùng BeanFactory/injection để lấy bean |
| Java JPMS báo lỗi reflection/enhancement | Module/package chưa mở đúng | Kiểm tra `opens`/`exports` trong module descriptor |
| Unit test `new AppConfig().car()` cho kết quả khác integration test | Unit test đang gọi config như Java object | Dùng `AnnotationConfigApplicationContext` cho test Spring semantics |
| Circular bean dependency xuất hiện | Bean A cần B trong lúc B cần A | Refactor dependency graph; không chỉ đổi proxy mode |
| CGLIB được thêm thủ công nhưng vẫn lỗi | Hạn chế class/method hoặc semantics config, không phải thiếu JAR | Dùng CGLIB Spring đóng gói; kiểm tra đúng lỗi và code |
| Startup chậm | Nhiều nguyên nhân khác (scanning, bean creation, network, post-processors) | Đo profile cụ thể, không hứa `proxyBeanMethods=false` tự chữa mọi thứ |

### 10.1. Kiểm tra đúng configuration object

Nếu cần xác minh full enhancement, tạo context thật và inspect behavior:

```java
try (var context =
        new AnnotationConfigApplicationContext(FullConfig.class)) {
    Engine engine = context.getBean(Engine.class);
    Vehicle car = context.getBean("car", Vehicle.class);
    System.out.println(engine == car.engine());
}
```

Đây là **trích đoạn minh họa** dùng `FullConfig`, `Engine` và `Vehicle` của mục 7. Nó phải được chạy trong code có access tới các class ấy; `AnnotationConfigApplicationContext` là tên đúng từ `org.springframework.context.annotation`.

Đừng quyết định có enhance hay không chỉ qua tên class runtime; **bean identity và scope** mới phản ánh behavior bạn cần.

### 10.2. Checklist debug khi object bị tạo dư

1. Xác nhận `@Configuration` đã được Spring xử lý trong context thực hay chưa.
2. Kiểm tra `proxyBeanMethods` mặc định `true` hay đã tắt.
3. Tìm nơi gọi `otherBean()` trực tiếp; thay bằng tham số method nếu có thể.
4. Xác định target scope là singleton, prototype hay custom.
5. Kiểm tra object có được tạo bởi `new` ngoài BeanFactory không.
6. Kiểm tra các beans có tên trùng hoặc cùng type khiến chọn sai ứng viên không.
7. Nếu có AOP, phân biệt proxy reference và raw target.
8. Thử trên context nhỏ để tái hiện identity như mục 7.
9. Không dùng log constructor đơn lẻ để kết luận về lifetime nếu có `FactoryBean`/proxies.
10. Khi chọn lite mode, đảm bảo không còn inter-bean direct calls cần container semantics.

## 11. Bài tập kiểm tra kiến thức

### Bài 1 — Dự đoán số Engine

Với `FullConfig` ở mục 7, `engine` là singleton, hai factory methods gọi `engine()` trực tiếp. Bao nhiêu Engine được tạo?

**Đáp án:** một managed Engine trong bối cảnh ví dụ; hai inter-bean references được chặn và quay về BeanFactory.

### Bài 2 — Tắt interception

Đổi `FullConfig` thành `@Configuration(proxyBeanMethods=false)` mà không đổi method bodies. Kết quả ba phép so sánh identity thế nào?

**Đáp án:** trong ví dụ, đều `false`. Có một managed Engine singleton và hai Engine do direct calls tạo ra trong `car()` và `truck()`.

### Bài 3 — Không dùng proxy nhưng vẫn chia sẻ singleton

Muốn giữ `proxyBeanMethods=false`, làm sao để `car`/`truck` nhận cùng managed `engine`?

**Đáp án:** dùng `@Bean Vehicle car(Engine engine)` và `@Bean Vehicle truck(Engine engine)` rồi truyền tham số vào constructor; Spring phân giải argument từ BeanFactory.

### Bài 4 — `final class`

Tại sao `@Configuration final class AppConfig` không hợp lệ trong full mode?

**Đáp án:** CGLIB cần sinh subclass để override các `@Bean` methods. `final` chặn kế thừa.

### Bài 5 — Singleton và prototype

`@Bean @Scope("prototype") Engine engine()` trong full config. Mỗi lookup thông thường có phải đều trả một Engine duy nhất như singleton?

**Đáp án:** không; container tôn trọng scope. CGLIB inter-bean lookup không biến prototype thành singleton.

### Bài 6 — Direct method gọi từ Java `new`

`new FullConfig().engine()` có tự đi qua BeanFactory không?

**Đáp án:** không. Đây là một instance được tạo ngoài container và không phải CGLIB-enhanced configuration bean được quản lý.

### Bài 7 — So sánh với `@Transactional` self-invocation

Lý do `car()` gọi `engine()` có thể được chặn trong full config có chứng minh `@Transactional` trên một method service luôn được kích hoạt khi service method này gọi service method khác qua `this`?

**Đáp án:** không. Hai cơ chế khác nhau; self-invocation qua target thường bypass Spring AOP proxy.

### Bài 8 — Tình huống thư viện

Ứng dụng có ba independent factory methods không gọi qua lại, chỉ nhận tham số được Spring resolve. Có nhất thiết bật `proxyBeanMethods=true` không?

**Đáp án:** không. `@Configuration(proxyBeanMethods=false)` là lựa chọn hợp lý khi không cần inter-bean calls; các `@Bean` methods vẫn tạo managed beans.

### Bài 9 — Một bean cần prototype mới mỗi lần sử dụng

Nếu một singleton `JobRunner` cần `JobTask` prototype mỗi lần chạy, chỉ truyền `JobTask` làm tham số `@Bean JobRunner runner(JobTask task)` có đủ không?

**Đáp án:** chưa; injection trực tiếp vào singleton chỉ resolve một task khi runner được tạo. Dùng `ObjectProvider<JobTask>` hoặc factory phù hợp rồi lookup mỗi lần cần.

### Bài 10 — Kiểm tra lỗi đúng tầng

Một `@Bean` method không thể resolve tham số `Repository`. Đổi `proxyBeanMethods=true` sang `false` có giải quyết chắc chắn không?

**Đáp án:** không. Đó là lỗi thiếu dependency hoặc candidate resolution; cần đăng ký repository, sửa qualifier/scan/condition, chứ không chỉ đổi cách chặn method.

## 12. Checklist thiết kế

Trước khi chọn full hay lite configuration:

- Các `@Bean` methods **có thật sự tự gọi lẫn nhau** và cần lookup theo BeanFactory semantics không?
- Nếu có, có thể thay bằng **method parameter injection** để giảm coupling không?
- Bean đang dùng singleton hay scope khác? Có cơ chế `@Lazy`, prototype, scoped proxy, AOP nào ảnh hưởng identity không?
- Có cần class `final`, record hoặc những thành viên không override được không? Nếu có, tránh full-mode interception và kiểm tra cấu hình phù hợp.
- Có đang gọi method `@Bean` trên `new Config()` ngoài Spring không?
- Có đang phân biệt đủ **managed singleton instance** với những raw object được tạo bằng direct Java call không?
- Với Spring AOP, đã kiểm tra self-invocation theo proxy AOP riêng, không dùng CGLIB config làm suy luận thay thế chưa?
- Context test đã xác nhận identity, lifecycle và bean registration thực tế chưa?

## 13. Tóm tắt

**Full `@Configuration`** có `proxyBeanMethods=true` mặc định. Spring tăng cường configuration class bằng **CGLIB subclass** để các lời gọi giữa `@Bean` methods phù hợp được chuyển về BeanFactory, nhờ đó giữ singleton/scope/AOP semantics của managed beans. Nó cần class/method có thể được subclass/override; không áp dụng interception tương tự cho static factory methods.

**Lite mode** với `@Configuration(proxyBeanMethods=false)` vẫn đăng ký và quản lý `@Bean`, nhưng lời gọi Java `otherBean()` không được chặn, nên có thể tạo object ngoài managed bean mà caller mong đợi. Cách làm rõ ràng và tương thích cả hai mode là dùng **factory-method parameter injection**: `@Bean Car car(Engine engine)`.

Khi cần inter-bean direct calls trong full configuration, dùng cơ chế đó có chủ đích. Khi các factory methods độc lập hoặc đã khai báo tham số phụ thuộc, lite mode thường đơn giản và dễ bảo trì hơn. Dù chọn chế độ nào, hãy kiểm chứng behavior bằng Spring context thật thay vì chỉ gọi Java method trên cấu hình tự `new`.

### Tài liệu chính thức

- [Spring Framework 6.2 — Using the `@Configuration` Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html).
- [Spring Framework 6.2 — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework 6.2 — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework 6.2 — `Configuration` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Configuration.html).
- [Spring Framework 6.2 — `Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html).
