# Giới hạn `final`, `private` và `static` khi Spring chặn lời gọi `@Bean`

## 1. Bài toán: vì sao có phương thức `@Bean` bị chặn, có phương thức không?

Trong Spring Java Configuration, annotation `@Bean` đánh dấu một factory method để Spring IoC Container đăng ký và quản lý object trả về. Tuy nhiên, không phải mọi **lời gọi Java trực tiếp** tới method được gắn `@Bean` đều có cùng ngữ nghĩa như một lệnh tra cứu bean từ container. Sự khác biệt nằm ở chế độ xử lý class cấu hình và ở khả năng **override method bằng CGLIB**.

Ví dụ:

```java
@Configuration
class AppConfig {
    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine());
    }
}
```

Đây là mã **minh họa**, chưa phải chương trình độc lập vì chưa định nghĩa `Engine`/`Car` và các import. Khi `AppConfig` được Spring đăng ký ở **full configuration mode** (mặc định `proxyBeanMethods = true`), lời gọi `engine()` từ `car()` trên instance được Spring tăng cường thường được chuyển về `BeanFactory`. Nếu `engine` là singleton, `Car` nhận reference của bean `engine` đã được container quản lý.

Nhưng có ba nhóm ràng buộc quan trọng:

- **`final`**: Java không cho subclass kế thừa class `final` hoặc override method `final`.
- **`private`**: method `private` không được override bằng method của subclass.
- **`static`**: method thuộc class, không tham gia virtual dispatch/override trên instance; vì vậy lời gọi trực tiếp `static @Bean` method **không được interceptor CGLIB chuyển sang BeanFactory**.

Điều này **không đồng nghĩa** `@Bean` với `static` luôn sai: static `@Bean` là một trường hợp được Spring hỗ trợ, đặc biệt hữu ích để tạo sớm một số post-processor. Còn `final` và `private` trên instance `@Bean` method là ràng buộc đáng chú ý ở **full `@Configuration`**, không nên bê nguyên các quy tắc đó sang **lite mode**.

Mục tiêu bài học:

1. Hiểu rõ full vs. lite configuration và lý do có CGLIB.
2. Phân biệt hạn chế ở **class** và ở **instance factory method**.
3. Giải thích được vì sao static `@Bean` hợp lệ nhưng không có inter-bean call interception.
4. Sử dụng `proxyBeanMethods = false` và factory-method parameter injection đúng cách.
5. Hiểu khi nào cần static `@Bean` cho `BeanFactoryPostProcessor`/`BeanPostProcessor`.
6. Chạy ví dụ Java 17+ đối chiếu identity/số instance để nhận diện lỗi cấu hình.

## 2. Full và lite khác nhau ở khả năng override

Spring đăng ký và quản lý beans từ `@Bean` ở cả hai mode. Full mode (`@Configuration` mặc định) dùng subclass CGLIB để chặn instance factory methods phù hợp trên configuration bean đã được enhance; lite mode (`proxyBeanMethods=false`) để direct method call chạy theo nghĩa Java.

### 2.1. Full mode cần instance method override được

```java
@Configuration
class FullConfig {
    @Bean Engine engine() { return new Engine(); }
    @Bean Car car() { return new Car(engine()); }
}
```

Đoạn minh họa cần kiểu `Engine` và `Car`. Khi Spring gọi `car()` qua enhanced configuration, `engine()` có thể được chuyển sang BeanFactory để lấy singleton. Để làm vậy CGLIB phải subclass configuration và override method.

### 2.2. Lite mode cho phép Java direct call

Nếu đổi annotation thành `@Configuration(proxyBeanMethods=false)`, `engine()` trong `car()` chạy trực tiếp và có thể tạo object khác managed `engine`. Chuyển sang `car(Engine engine)` để Spring resolve dependency từ BeanFactory.

### 2.3. Bảng giới hạn

| Thành phần | Full | Lite |
| --- | --- | --- |
| Configuration class `final` | Không hợp lệ vì cần subclass | Có thể dùng |
| Instance `@Bean` method `private`/`final` | Không hợp lệ vì cần override | Có thể dùng nếu Spring có thể gọi method |
| Static `@Bean` | Hợp lệ, không có interception | Hợp lệ, không có interception |
| Tham số của `@Bean` | Spring resolve | Spring resolve |

`proxyBeanMethods=false` không tắt DI, lifecycle hay singleton management của các bean được container thực sự tạo. Các mục sau giải thích **vì sao từng modifier Java làm thay đổi khả năng interception**.

## 3. `final`: cấm kế thừa và cấm override

Java `final` áp dụng cho class hoặc instance method:

- `final class A`: không class nào kế thừa `A`.
- `final void action()`: subclass không thể override `action()`.
- `final` trên field/biến cục bộ có nghĩa khác và **không phải** ràng buộc trực tiếp của CGLIB method interception.

### 3.1. Class `@Configuration` không được `final` trong full mode

Ví dụ **cố ý sai** với full mode:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public final class InvalidFinalConfig {
    @Bean
    String serviceName() {
        return "billing";
    }
}
```

Đây là nội dung minh họa cho file `InvalidFinalConfig.java`, có thể biên dịch về mặt Java nhưng **không phù hợp cho full Spring configuration processing**. Khi Spring cần tạo subclass của `InvalidFinalConfig`, modifier `final` ngăn kế thừa; context có thể thất bại trong giai đoạn xác minh/xử lý configuration class, trước khi caller lấy được bean.

Không giải quyết vấn đề bằng cách tự viết subclass hoặc đưa annotation lên một class khác rồi trông đợi class final vẫn được enhance. Có hai hướng hợp lệ:

1. Bỏ `final` khỏi configuration class nếu thực sự cần inter-bean calls theo full mode.
2. Chuyển sang `@Configuration(proxyBeanMethods = false)` **nếu các factory methods độc lập** hoặc dependency được nhận qua tham số.

Ví dụ lite hợp lệ về nguyên tắc:

```java
@Configuration(proxyBeanMethods = false)
public final class FinalLiteConfig {
    @Bean
    String serviceName() {
        return "billing";
    }
}
```

Đây là mã minh họa cho file `FinalLiteConfig.java`, phải có import `@Configuration` và `@Bean` khi tách ra file riêng. Bean `serviceName` vẫn do Spring quản lý; modifier `final` chỉ có ý nghĩa là class không được subclass.

### 3.2. Instance method `@Bean` không được `final` trong full mode

Ví dụ **cố ý sai**:

```java
@Configuration
class InvalidFinalMethodConfig {
    @Bean
    public final Engine engine() {
        return new Engine();
    }
}
```

Class `InvalidFinalMethodConfig` không `final` nhưng method `engine()` không thể override. Vì full mode muốn chặn lời gọi method đó, Spring coi đây là cấu hình không hợp lệ. Lỗi thường được báo trong quá trình xử lý bean definitions, ví dụ “`@Bean method ... must not be private or final`” hoặc thông điệp tương đương theo phiên bản.

**Không dựa vào Java compiler để phát hiện lỗi này.** Cú pháp Java cho phép một method vừa có annotation vừa `final`; điều vi phạm là hợp đồng **Spring full configuration processing**. Hãy test tạo `AnnotationConfigApplicationContext` thay vì chỉ chạy `javac`.

### 3.3. `final` trên class nghiệp vụ được trả về từ `@Bean` thì sao?

Ví dụ:

```java
public final class PricingRules {
    public int fee() {
        return 5;
    }
}

@Configuration
class ValidConfig {
    @Bean
    PricingRules pricingRules() {
        return new PricingRules();
    }
}
```

Đây là hai **trích đoạn minh họa**, tương ứng file Java riêng. Config `ValidConfig` không `final` và factory method có thể override. **Class `PricingRules` được tạo làm bean có thể `final`** mà không cản **CGLIB enhancement của configuration class**: Spring đang tăng cường class `ValidConfig`, không nhất thiết phải subclass `PricingRules`.

Cần phân biệt với một nhu cầu **Spring AOP class-based proxy** trên chính `PricingRules`: target class `final` có thể gây hạn chế proxy AOP vì không subclass được. Hai chủ đề liên quan cơ chế proxy nhưng **không phải cùng một đối tượng cần được subclass**.

### 3.4. Java records và Kotlin

Java record là class có tính `final`, nên **không dùng record làm full `@Configuration` class cần CGLIB subclass**. Với `@Configuration(proxyBeanMethods=false)`, các hạn chế subclassing này không còn là lý do từ bean method interception; vẫn cần bảo đảm framework có thể xây dựng configuration object đúng cách.

Trong Kotlin, classes và methods mặc định final; plugin Kotlin Spring/`all-open` thường được sử dụng để mở những classes/annotations cần proxy. Nhưng đừng áp dụng mẹo Kotlin để che một dependency graph sai; lựa chọn lite mode và method-parameter injection vẫn hữu ích.

## 4. `private`: method tồn tại nhưng subclass không override được

Một method `private` chỉ truy cập được trong phạm vi khai báo theo quy tắc Java, không được kế thừa như một virtual method có thể override. Do đó:

```java
@Configuration
class InvalidPrivateConfig {
    @Bean
    private Engine engine() {
        return new Engine();
    }
}
```

Đây là ví dụ **cố ý sai** trong full mode. Vì `engine()` là private instance method, CGLIB subclass không thể override để chặn những lời gọi theo ngữ nghĩa container. Spring full configuration validation không chấp nhận factory method dạng này.

Không nên “chữa” bằng cách chỉ thêm `@Autowired` trên method, bật bean definition overriding hoặc tăng phạm vi component scan: vấn đề nằm ở **khả năng override của method**, không phải việc container tìm thấy dependency.

### 4.1. `private` trong lite mode

Khi `proxyBeanMethods=false`, Spring không cần subclass để chặn các `@Bean` method calls. Vì vậy Spring cho phép factory methods lite sử dụng các access modifiers linh hoạt hơn, bao gồm `private` trong điều kiện phương thức có thể được gọi bằng reflection tương ứng.

```java
@Configuration(proxyBeanMethods = false)
class LitePrivateConfig {

    @Bean
    private Engine engine() {
        return new Engine();
    }

    @Bean
    Car car(Engine engine) {
        return new Car(engine);
    }
}
```

Đây là **mã minh họa**, cần các class `Engine`/`Car`. Spring có thể gọi `engine()` như một factory method để đăng ký bean, còn `car(Engine engine)` nhận chính bean đó nhờ **dependency resolution tại tham số**. Không cần gọi `engine()` từ `car()` nên không cần CGLIB inter-bean interception.

**Cẩn trọng:** nếu module Java chạy theo JPMS với `module-info.java`, việc Spring truy cập reflective private factory method có thể bị giới hạn bởi module openness; cần cấu hình `opens` đúng chỗ. Ví dụ đơn giản dùng classpath thông thường nên không áp dụng module descriptor.

### 4.2. `private @Bean` không đồng nghĩa “bean riêng tư”

`private` là modifier của method Java, **không phải bean visibility**. Một bean được Spring đăng ký từ private factory method ở lite mode vẫn có thể được lookup từ cùng `ApplicationContext` nếu bean definition hợp lệ và scope cho phép:

```java
Engine engine = context.getBean(Engine.class);
```

Đây là đoạn minh họa với biến `context` đã khởi tạo. Method private không khiến bean bị giấu khỏi container hay biến thành private dependency theo Java access control.

### 4.3. Package-private và protected trong full mode

Một instance `@Bean` method không bắt buộc phải là `public` để được chặn trong full mode. Các method package-private hoặc `protected` **có thể được override theo luật Java** nếu chúng không `final` và không bị những ràng buộc visibility khác của JVM/JPMS chặn. Nhiều ví dụ Spring JavaConfig sử dụng method package-private:

```java
@Configuration
class ValidPackagePrivateConfig {
    @Bean
    Engine engine() {
        return new Engine();
    }
}
```

Ở đây method `engine()` không khai báo `public` nhưng cũng không `private` hoặc `final`; điều này khác với hai ví dụ lỗi ở trên.

Để giảm rủi ro reflection/visibility trong môi trường phức tạp, các phương thức factory hạ tầng có thể được để package-private hoặc public có chủ đích. Không thay mọi method bằng public chỉ vì Spring CGLIB nếu không cần.

## 5. `static`: hợp lệ để tạo bean, nhưng không có interception

### 5.1. Vì sao CGLIB không chặn static method?

Java phân giải method `static` theo class, không theo virtual dispatch của instance. CGLIB chặn inter-bean calls của full `@Configuration` bằng **subclassing và method overriding**; một static method không thể override như instance method.

Ví dụ:

```java
@Configuration
class StaticBeanConfig {

    @Bean
    static Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine()); // Trực tiếp gọi static method Java.
    }
}
```

Đây là mã minh họa. Spring đăng ký **bean `engine`** từ static factory method. Tuy nhiên, lời gọi `engine()` từ `car()` là **static Java call** trực tiếp: thực thi `new Engine()` một lần nữa, có thể tạo một object **ngoài** managed singleton `engine`.

Vì vậy:

- `context.getBean(Engine.class)` trả bean `engine` được container quản lý.
- `context.getBean(Car.class).engine()` có thể trỏ tới một object `Engine` **khác** tạo từ lời gọi static trong `car()`.
- Điều đó xảy ra ngay cả khi `StaticBeanConfig` dùng **full `@Configuration`**.
- Chỉ vì `@Bean` được viết trên static method **không có nghĩa** factory method không được Spring quản lý; sự khác nhau nằm giữa **BeanFactory invocation** và **lời gọi Java trực tiếp**.

### 5.2. Static `@Bean` không có ý nghĩa là singleton “toàn JVM”

Từ khóa Java `static` trong `static @Bean` chỉ định method thuộc class, **không phải scope của bean**. Scope mặc định `singleton` của Spring vẫn là **một instance trên mỗi BeanFactory/container**:

- Hai `ApplicationContext` độc lập có thể có hai singleton instances tương ứng.
- `@Scope("prototype")` trên static `@Bean` vẫn có thể yêu cầu tạo object mới theo scope khi container resolve.
- Một lời gọi Java trực tiếp đến static method luôn chạy method body theo semantics Java; không được container tự đổi thành lookup.

Đừng dùng biến static để giữ “singleton toàn hệ thống” rồi lẫn với Spring singleton. Trong đa ứng dụng/context hoặc test chạy song song, static state có thể làm dữ liệu rò giữa tests và gây lỗi khó tái hiện.

### 5.3. Cách sửa inter-bean reference tới static `@Bean`

Thay:

```java
@Bean
Car car() {
    return new Car(engine()); // Direct static method call.
}
```

bằng:

```java
@Bean
Car car(Engine engine) {
    return new Car(engine);   // BeanFactory cung cấp Engine.
}
```

Hai đoạn trên là phương án **minh họa**, dùng cùng class `Car`/`Engine` của ví dụ. Spring phân giải tham số `Engine` từ container trước khi gọi `car(...)`; cách này bảo toàn scope/managed reference phù hợp và không phụ thuộc method static có được chặn hay không.

Đây là quy tắc thực hành đáng nhớ: **truyền dependency qua tham số `@Bean`** có tính ổn định cao hơn trong full mode, lite mode và khi dependency được sản sinh bởi một static factory method.

## 6. Vì sao một số post-processor dùng `static @Bean`?

### 6.1. `BeanFactoryPostProcessor` tham gia rất sớm

`BeanFactoryPostProcessor` (BFPP) xử lý metadata trước khi phần lớn singleton được tạo. Nếu BFPP do một **instance `@Bean` method** tạo, BeanFactory phải khởi tạo configuration object sớm để gọi method, có thể xảy ra trước khi injection/lifecycle của chính config object hoàn tất. Static method tránh yêu cầu ấy:

```java
@Configuration
class InfraConfig {
    @Bean
    static PropertySourcesPlaceholderConfigurer placeholders() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
```

Đây là cú pháp minh họa, cần import `org.springframework.context.support.PropertySourcesPlaceholderConfigurer`. Spring khuyến nghị static factory cho BFPP khi phù hợp vì thời điểm khởi tạo đặc biệt.

### 6.2. `BeanPostProcessor` cũng cần sẵn sàng sớm

`BeanPostProcessor` (BPP) xử lý bean **instances** trước/sau khởi tạo, có thể wrap proxy hoặc áp dụng lifecycle callbacks. Non-static factory tạo BPP có nguy cơ khởi tạo config hoặc dependencies quá sớm; static factory có thể tránh một phần nguy cơ:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfiguration {
    @Bean
    static BeanPostProcessor auditPostProcessor() {
        return new BeanPostProcessor() {};
    }
}
```

Ví dụ cần import `org.springframework.beans.factory.config.BeanPostProcessor`; processor rỗng chỉ minh họa declaration, **không** ghi audit. Một BPP thực phải triển khai callback và kiểm soát thứ tự; bài về static `@Bean` và early type discovery trình bày sâu quá trình này.

### 6.3. Đánh đổi và giới hạn

Static factory **không** được CGLIB chặn khi gọi trực tiếp, không truy cập instance state của config và không biến bean thành singleton toàn JVM. Phương thức vẫn có thể nhận dependencies được Spring resolve; chính các dependencies đó có thể kéo theo khởi tạo sớm ngoài dự kiến. Vì vậy không nên đặt `static` hàng loạt, đặc biệt với bean nghiệp vụ thường.

## 7. Ví dụ chạy được Java 17+: full, lite và static

Ví dụ tạo **bốn `ApplicationContext` độc lập**, mỗi context so sánh một `Part` bean do container quản lý với `Part` mà một `Product` nhận:

1. **FULL**: instance method có thể override, inter-bean call được CGLIB chặn.
2. **LITE_DIRECT**: configuration class `final`, factory method `private`/`final`, direct call chạy như Java thường.
3. **LITE_PARAMETER**: configuration class `final` nhưng factory parameter nhận managed dependency; không có object dư.
4. **STATIC_DIRECT**: static `@Bean` hợp lệ trong full configuration nhưng direct static call không bị CGLIB chặn.

Các class được đăng ký lần lượt trong **những context khác nhau** nên không có xung đột bean names. Ví dụ dùng JDK 17+ và Spring Framework 6.2.19.

### 7.1. Cấu trúc

```text
bean-method-modifiers-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── BeanMethodModifiersDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'bean-method-modifiers-demo'
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
    mainClass = 'BeanMethodModifiersDemo'
}
```

Không khai báo CGLIB riêng: Spring Core bao gồm phiên bản CGLIB được repackaged. Dùng một bản Gradle tương thích với JDK 17+.

### 7.2. File Java đầy đủ

Tạo `src/main/java/BeanMethodModifiersDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class BeanMethodModifiersDemo {

    private static final AtomicInteger CREATED = new AtomicInteger();

    public record Part(int id) {
        public Part() {
            this(CREATED.incrementAndGet());
        }
    }

    public record Product(Part part) {
    }

    // Full mode: các instance @Bean methods đều override được.
    @Configuration
    public static class FullConfig {

        @Bean
        public Part part() {
            return new Part();
        }

        @Bean
        public Product product() {
            return new Product(part());
        }
    }

    // Lite: final configuration class và private/final factory methods.
    @Configuration(proxyBeanMethods = false)
    public static final class LiteDirectConfig {

        @Bean
        private Part part() {
            return new Part();
        }

        @Bean
        public final Product product() {
            return new Product(part());
        }
    }

    // Lite: các modifier giữ nguyên, nhưng dùng method parameter DI.
    @Configuration(proxyBeanMethods = false)
    public static final class LiteParameterConfig {

        @Bean
        private Part part() {
            return new Part();
        }

        @Bean
        public final Product product(Part part) {
            return new Product(part);
        }
    }

    // Full configuration nhưng static @Bean không được override.
    @Configuration
    public static class StaticDirectConfig {

        @Bean
        public static Part part() {
            return new Part();
        }

        @Bean
        public Product product() {
            return new Product(part());
        }
    }

    private static void inspect(
            String label, Class<?> configurationClass) {

        CREATED.set(0);

        try (var context =
                     new AnnotationConfigApplicationContext(configurationClass)) {

            Part managed = context.getBean(Part.class);
            Product product = context.getBean(Product.class);

            System.out.println("== " + label + " ==");
            System.out.println("samePart = " + (managed == product.part()));
            System.out.println("instances = " + CREATED.get());
        }
    }

    public static void main(String[] args) {
        inspect("FULL", FullConfig.class);
        inspect("LITE_DIRECT", LiteDirectConfig.class);
        inspect("LITE_PARAMETER", LiteParameterConfig.class);
        inspect("STATIC_DIRECT", StaticDirectConfig.class);
    }
}
```

Các class `FullConfig` và `StaticDirectConfig` không `final`; các instance `@Bean` methods có thể override. Hai class lite được đánh dấu `final` và cố ý có private/final methods để minh họa các ràng buộc về CGLIB **không còn áp dụng cho interception** khi `proxyBeanMethods=false`.

`AtomicInteger` chỉ làm bộ đếm số lần constructor `new Part()` được gọi. `CREATED.set(0)` chạy trước khi tạo mỗi context, và trong mỗi context main tạo/đọc beans trên một luồng. Điều này giúp kết quả đếm ổn định; không dùng bộ đếm toàn cục kiểu này làm state nghiệp vụ.

### 7.3. Chạy và stdout

Trong thư mục dự án:

```bash
gradle run --quiet
```

Nếu dùng Gradle Wrapper trên Linux/macOS:

```bash
./gradlew run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Các dòng `System.out.println` mà chương trình in:

```text
== FULL ==
samePart = true
instances = 1
== LITE_DIRECT ==
samePart = false
instances = 2
== LITE_PARAMETER ==
samePart = true
instances = 1
== STATIC_DIRECT ==
samePart = false
instances = 2
```

Output này nói về chương trình đơn giản ở trên, với singleton mặc định và không có component/factory nào khác tạo `Part`. Gradle hoặc hệ thống logging có thể phát sinh thêm dòng không thuộc `System.out.println` của chương trình.

### 7.4. Giải thích từng trường hợp

**FULL:** Spring enhancement có thể chặn `product() -> part()`. Vì `part` là singleton managed bean, `product.part()` và `context.getBean(Part.class)` là cùng object. Chỉ một lần tạo `Part`.

**LITE_DIRECT:** `LiteDirectConfig` là class `final`, method `part()` là `private`, method `product()` là `final`. Chúng được BeanFactory gọi như factory methods trong lite mode; khi `product()` gọi `part()` thì đó là Java call thông thường. Context cũng tạo managed singleton `part` riêng. Tổng hai object, identity `false`.

**LITE_PARAMETER:** Không cần intercept `part()`; BeanFactory phân giải tham số `Part part` cho `product(Part part)`. Factory nhận managed singleton `part` và giữ reference đó, tổng một object dù config class vẫn `final` và factory methods private/final.

**STATIC_DIRECT:** `StaticDirectConfig.part()` được đăng ký như một static factory method; container tạo một managed singleton. Nhưng trong `product()`, lời gọi `part()` là static Java call không được CGLIB override, tạo một object khác. Tổng hai object, identity `false`. Việc configuration class không `final` cũng không thay đổi hạn chế static dispatch.

### 7.5. Tại sao ví dụ không đưa những cấu hình sai vào `main`?

Các ví dụ ở phần 8 cố ý vi phạm full configuration constraints. Nếu đăng ký chúng cùng với các cấu hình hợp lệ, context có thể thất bại ngay ở giai đoạn parsing/enhancement, không tạo được stdout dùng để so sánh. Tách trường hợp lỗi ra thành minh họa riêng giúp người học thấy **lỗi khởi động** khác **lỗi identity do direct calls**.

## 8. Các ví dụ cấu hình cố ý sai trong full mode

Không đặt các snippets ở mục này vào chương trình hoàn chỉnh mục 7. Chúng là các **đầu vào có chủ đích để kiểm tra thông báo lỗi Spring**, không phải cấu hình nên triển khai.

### 8.1. `final @Configuration` class

```java
@Configuration
final class BadFinalConfiguration {
    @Bean
    Part part() {
        return new Part();
    }
}
```

Khi xử lý full mode, Spring cần tạo CGLIB subclass nhưng class `BadFinalConfiguration` không thể được kế thừa. Hướng khắc phục: bỏ `final` hoặc chọn lite mode với DI qua tham số.

### 8.2. `final` instance `@Bean` method

```java
@Configuration
class BadFinalMethodConfiguration {
    @Bean
    final Part part() {
        return new Part();
    }
}
```

Method `part()` là `final` nên không thể được subclass override. Dù chỉ có một bean definition, đây vẫn là vấn đề tại configuration validation của full mode; không phụ thuộc vào việc hiện tại đã có inter-bean call hay chưa.

### 8.3. `private` instance `@Bean` method

```java
@Configuration
class BadPrivateMethodConfiguration {
    @Bean
    private Part part() {
        return new Part();
    }
}
```

Spring full mode không thể override một private instance method để cung cấp bean lookup semantics. Nếu chuyển sang lite, có thể dùng factory method private, nhưng hãy chú ý reflective access/JPMS và tránh direct calls khi muốn reference managed bean.

### 8.4. Có phải static `@Bean` tự báo lỗi như final/private?

**Không.** Spring hỗ trợ static factory methods trong configuration classes, kể cả full configuration. Điều cần hiểu là **static calls không được intercept**. Do đó lỗi thường biểu hiện ở **số instance/identity/lifecycle không như kỳ vọng**, chứ không phải vì cú pháp `static @Bean` bị Spring cấm.

| Khai báo | Full `@Configuration` | Lite mode |
| --- | --- | --- |
| `final class Config` | Không hợp lệ vì cần subclass | Có thể |
| `@Bean final T bean()` (instance) | Không hợp lệ vì không override được | Có thể |
| `@Bean private T bean()` (instance) | Không hợp lệ vì không override được | Có thể |
| `@Bean static T bean()` | Hợp lệ, nhưng direct call không intercept | Hợp lệ, direct call Java thường |
| `@Bean T bean()` (package-private, overridable) | Hợp lệ khi visibility/khả năng override phù hợp | Hợp lệ |
| `@Bean T bean(Dependency dependency)` | Spring resolve tham số | Spring resolve tham số |

## 9. Những nhầm lẫn cần tránh

### 9.1. “Nếu `@Bean` method là private thì bean cũng private”

Sai. Modifier `private` điều khiển khả năng truy cập Java method; nó không tạo một “bean private” trong Spring. Nếu method được Spring chấp nhận (ví dụ lite configuration trên classpath phù hợp), bean có tên và scope như các beans khác và có thể được lookup từ container.

### 9.2. “Static `@Bean` = Spring singleton toàn ứng dụng”

Sai. Java `static` và Spring `singleton` thuộc hai khái niệm khác nhau. Singleton của Spring thường gắn với **một container**, trong khi static method là method của Java class. Một Spring singleton bean được tạo từ static factory method vẫn có thể khác giữa hai contexts.

### 9.3. “Chuyển sang lite mode thì Spring không làm DI”

Sai. Lite mode vẫn đăng ký `@Bean` và phân giải các tham số của factory methods. Dùng `@Bean Product product(Part part)` để nhận dependency từ BeanFactory thay vì tự gọi `part()`.

### 9.4. “Chỉ cần `new Config()` là nhận được interception”

Sai. Một object do `new Config()` bên ngoài Spring là Java object bình thường; không phải configuration instance do Spring tăng cường. Nếu tự gọi `new Config().product()`, bạn không được bảo đảm Spring-managed singleton semantics. Tương tự, static direct calls không thể được intercepted chỉ vì được viết trong một class mang `@Configuration`.

### 9.5. “Mọi method `final` của configuration class đều bị cấm”

Không chính xác. Quy tắc full mode tập trung vào **instance `@Bean` factory methods cần override**; một helper Java method khác không có `@Bean` không phải đối tượng chặn inter-bean references theo cùng quy tắc. Dù vậy, thiết kế full configuration class nên tránh những thủ thuật inheritance/phân quyền truy cập gây khó hiểu.

### 9.6. “CGLIB enhancement của `@Configuration` chính là Spring AOP”

Không hoàn toàn. Hai cơ chế đều có thể dùng CGLIB subclassing, nhưng mục tiêu khác:

- Full configuration enhancement can thiệp vào **lời gọi `@Bean` methods** để giữ BeanFactory semantics.
- Spring AOP can thiệp vào **lời gọi tới business bean** qua proxy cho các concern như transaction, caching, security khi được cấu hình.

Trong proxy-based AOP, **self-invocation** trên target thường bypass proxy. Không suy diễn quy tắc AOP self-invocation từ ví dụ full `@Configuration`.

### 9.7. “Static factory method không nhận được dependency”

Không đúng. Spring vẫn có thể resolve các tham số của static `@Bean` method theo khả năng BeanFactory, ví dụ `@Bean static Service service(Repository repository)` khi Repository bean phù hợp tồn tại. Dù vậy, với BFPP/BPP cần khởi tạo sớm, dependencies quá phức tạp có thể làm nhiều beans khác bị tạo sớm, gây ảnh hưởng post-processing.

### 9.8. “Bỏ `final` là luôn hết lỗi”

Không nhất thiết. Một class không final vẫn có thể gặp lỗi nếu các `@Bean` instance methods private/final, bean candidates thiếu, vòng phụ thuộc không giải quyết được, module reflection bị giới hạn, hoặc factory method tự ném exception. Hãy phân biệt lỗi enhancement/validation với lỗi autowiring/bean creation.

## 10. Phân biệt lỗi validation, lỗi DI và lỗi lifecycle

| Hiện tượng | Có thể do | Hướng điều tra |
| --- | --- | --- |
| Context fail sớm khi xử lý config full | Config class final hoặc instance `@Bean` method private/final | Kiểm tra `proxyBeanMethods`, access modifiers, nested class |
| Context refresh thành công nhưng số object tăng | Lite direct calls, static direct calls, hoặc bean scope prototype | Dò caller `otherBean()`, so với managed `getBean(...)` |
| `BeanCreationException` ở bean khác | Factory method logic lỗi, dependency thiếu hoặc vòng phụ thuộc | Đọc root cause, xem chữ ký `@Bean` và DI graph |
| `UnsatisfiedDependencyException` | Không có hoặc không chọn được dependency | Kiểm tra bean definitions, types, qualifiers, profiles |
| Một object không được AOP/lifecycle xử lý | Nó được tạo bằng direct Java call ngoài BeanFactory | Chuyển sang container lookup/parameter injection |
| Không thấy `@Value`/`@Autowired` trên config | Một BFPP/BPP non-static ép config khởi tạo quá sớm | Cân nhắc static factory cho post-processor |
| JPMS `InaccessibleObjectException` | Module chưa mở package cần reflection/enhancement | Kiểm tra module descriptor và `opens` |
| Test với `new Config()` không khớp ứng dụng | Không có Spring-enhanced managed configuration instance | Dùng `AnnotationConfigApplicationContext` trong integration test |

### 10.1. Cách kiểm tra nhanh bằng context thật

Khi có class `FullConfig` và `Product`/`Part` từ mục 7:

```java
try (var context =
        new AnnotationConfigApplicationContext(FullConfig.class)) {
    Part managed = context.getBean(Part.class);
    Product product = context.getBean(Product.class);
    System.out.println(managed == product.part());
}
```

Đây là đoạn **minh họa** sử dụng các class của chương trình đầy đủ; nó không tự chạy như một file `.java` riêng. Với full mode và singleton, kết quả là `true`. Thử đổi configuration sang lite direct rồi lặp phép kiểm tra để nhìn thấy `false`.

**Lưu ý:** quan sát tên class kiểu `$$SpringCGLIB$$...` chỉ là kiểm tra chi tiết triển khai. Không viết logic nghiệp vụ dựa vào các phần tên class sinh động; test behavior theo bean identity, scope và semantics DI.

## 11. Bài tập có đáp án

### Bài 1 — Configuration class final

Cho `@Configuration final class FinalConfig` với một instance `@Bean` method thường. Nó có phù hợp full mode không?

**Đáp án:** Không, vì full mode cần tạo CGLIB subclass. Có thể bỏ `final` hoặc dùng `@Configuration(proxyBeanMethods=false)` với factory methods độc lập/DI đúng cách.

### Bài 2 — Method private

Một method `@Bean private Part part()` có thể được subclass override trong full mode không?

**Đáp án:** Không; private instance methods không overridable. Trong lite mode, factory method có thể private và được container gọi qua reflection khi môi trường cho phép.

### Bài 3 — Method final

Lớp `@Configuration` không final nhưng method `@Bean final Product product()`. Spring full mode có hợp lệ không?

**Đáp án:** Không; restriction áp dụng ở cả factory method. Không sửa bằng cách chỉ bỏ final ở class nếu method vẫn final.

### Bài 4 — Static factory

`@Configuration` có `@Bean static Part part()`, một `@Bean Product product()` gọi `part()` trực tiếp. Có phải lời gọi đó được interceptor CGLIB trả managed singleton không?

**Đáp án:** Không. Static call là lời gọi Java bình thường. Muốn managed Part, khai báo `@Bean Product product(Part part)`.

### Bài 5 — Static và vòng đời sớm

Vì sao `@Bean static PropertySourcesPlaceholderConfigurer placeholders()` thường được khuyến nghị?

**Đáp án:** Vì factory tạo BFPP có thể được gọi sớm **mà không phải instantiate enclosing configuration class**, giảm nguy cơ những injection/lifecycle annotations trên config chưa được xử lý đầy đủ.

### Bài 6 — Hai context

Hai `ApplicationContext` riêng đều đăng ký singleton bean từ `@Bean static Part part()`. Có bắt buộc trả đúng một instance Part chia sẻ toàn JVM không?

**Đáp án:** Không. Singleton Spring là theo container; static chỉ là thuộc tính của method. Nếu code tự thêm static cache riêng thì đó là logic khác, không phải mặc định của Spring.

### Bài 7 — Lite class final nhưng injection đúng

`@Configuration(proxyBeanMethods=false) final class Config` có `@Bean private Part part()` và `@Bean final Product product(Part part)`. Cần CGLIB enhancement để chia sẻ Part singleton không?

**Đáp án:** Không. BeanFactory resolve tham số từ container. Hành vi được kiểm chứng trong trường hợp `LITE_PARAMETER` ở mục 7.

### Bài 8 — Scope prototype

Nếu bean `Part` có scope prototype, có chắc `FULL` sẽ chỉ tạo một instance không?

**Đáp án:** Không. Full inter-bean call bảo toàn **scope semantics** của container, và prototype không chia sẻ một instance duy nhất như singleton. Ví dụ đếm ở mục 7 dành cho singleton mặc định.

### Bài 9 — Đổi proxy mode để chữa lỗi thiếu bean

Một factory method cần `Repository` nhưng context không có bean kiểu đó. Bật `proxyBeanMethods=true` có tự tạo Repository không?

**Đáp án:** Không. Đây là lỗi dependency resolution, cần đăng ký bean hoặc sửa qualifier/configuration; enhancement không tạo một dependency chưa được định nghĩa.

### Bài 10 — Full configuration và `@Transactional`

Nếu `@Bean` inter-bean call được CGLIB chặn thì `this.transfer()` trên một Spring AOP service có tự động bật transaction không?

**Đáp án:** Không thể suy ra như vậy. CGLIB configuration enhancement và AOP proxying là hai cơ chế khác nhau; self-invocation của AOP target thường bypass proxy.

## 12. Checklist trước khi chọn modifier và proxy mode

- Class có phải một **full `@Configuration`** không? `proxyBeanMethods` có đang là `true` mặc định không?
- Full config class có `final` không? Nested config có được khai báo `static` khi cần không?
- Các **instance `@Bean` factory methods** có `private` hay `final` không?
- Có static `@Bean` method nào được **gọi trực tiếp** ở một `@Bean` method khác không?
- Nếu cần managed dependency, đã dùng **factory-method parameters** thay vì direct calls chưa?
- Có BFPP/BPP cần khởi tạo sớm không, và method tạo nó có nên `static` không?
- Bean scope có phải singleton không? Có prototype, request, session, lazy hoặc AOP proxy cần xét không?
- Có object nào được tự `new` ngoài BeanFactory nhưng lại được giả định là managed bean không?
- Đã tạo một Spring context thật để kiểm tra registration/identity/lifecycle chưa?
- Nếu dùng Java modules, package có được mở phù hợp cho reflection/proxy không?

## 13. Tóm tắt

**Giới hạn của full `@Configuration` đến từ cách chặn inter-bean method calls bằng CGLIB subclass**: class `final` không thể subclass, instance method `final` hoặc `private` không thể override. Vì thế những khai báo này không phù hợp ở full mode. `@Configuration(proxyBeanMethods=false)` bỏ nhu cầu interception đó, nên có thể dùng class/method với các modifier ấy trong lite mode, miễn method là một factory hợp lệ và container có khả năng gọi nó.

**`static @Bean` hợp lệ trong Spring**, nhưng lời gọi trực tiếp đến static method không được interceptor chặn ở bất kỳ chế độ nào. Nó đặc biệt hữu ích để tạo sớm các bean hạ tầng như `BeanFactoryPostProcessor` và `BeanPostProcessor` mà không phải instantiate configuration class. Mặt trái là direct static calls có thể tạo object ngoài managed singleton.

**Cách viết ít phụ thuộc proxy mode nhất** là biểu diễn dependency qua tham số factory method:

```java
@Bean
Product product(Part part) {
    return new Product(part);
}
```

Khi đó Spring resolve `Part` từ BeanFactory, dù bean `part` được tạo bằng instance factory method hay static factory method, và dù configuration class sử dụng full hay lite mode.

### Tài liệu chính thức

- [Spring Framework 6.2 — `@Bean` Javadoc: Full mode, Lite mode và static post-processors](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html).
- [Spring Framework 6.2 — `@Configuration` Javadoc: `proxyBeanMethods` và các ràng buộc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Configuration.html).
- [Spring Framework Reference — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework Reference — Using `@Bean`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework Reference — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
