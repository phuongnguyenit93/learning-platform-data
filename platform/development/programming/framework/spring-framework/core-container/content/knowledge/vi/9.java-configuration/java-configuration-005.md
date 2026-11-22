# Phương thức @Bean static và thời điểm container phát hiện kiểu trong Spring Core Container

## 1. Vấn đề thực tế và mục tiêu

Trong Java configuration của Spring, phương thức mang `@Bean` thông thường là **instance method**. Tuy nhiên, Spring cũng hỗ trợ **static `@Bean` method**:

```java
@Configuration
class ApplicationConfig {
    @Bean
    static ServiceSettings serviceSettings() {
        return new ServiceSettings();
    }
}
```

Đây là snippet cấu trúc; `ServiceSettings` là class ví dụ cần được định nghĩa trong dự án, và phải import `@Configuration`, `@Bean`. Tại sao đôi khi cần `static`, nhất là với `BeanFactoryPostProcessor` và `BeanPostProcessor`? Và vì sao **kiểu trả về được khai báo** trên method có thể quyết định container có phát hiện được một bean đặc biệt **trước lúc khởi tạo instance** hay không?

Sau bài này, bạn sẽ:

1. Phân biệt **phát hiện bean definition**, **dự đoán kiểu bean**, **tạo bean instance** và **xử lý bean trong vòng đời context**.
2. Giải thích vì sao một static `@Bean` có thể được gọi **không cần tạo instance class `@Configuration`**.
3. Biết khi nào Spring khuyến nghị static `@Bean` cho `BeanFactoryPostProcessor` (BFPP) và `BeanPostProcessor` (BPP), và hậu quả khi dùng instance method cho các bean đặc biệt đó.
4. Giải thích tại sao factory method cần khai báo return type đủ cụ thể, nhất là các kiểu `BeanPostProcessor`, `BeanFactoryPostProcessor` hoặc `FactoryBean<T>`.
5. Hiểu rằng **static không đồng nghĩa eager**, **static không đồng nghĩa singleton toàn JVM**, và lời gọi trực tiếp static factory method **không được Spring chặn**.
6. Viết, chạy và kiểm chứng ví dụ Spring Framework 6.2 / Java 17+ cho thấy container nhận diện metadata, tạo processor sớm và tạo object nghiệp vụ sau.

## 2. Tách bốn mốc trong vòng đời container

Khi đọc `@Bean`, tránh gộp mọi thứ thành “Spring thấy bean”. Có ít nhất bốn sự kiện khác nhau:

| Mốc | Spring cần làm gì? | Có nhất thiết tạo target object chưa? |
| --- | --- | --- |
| **1. Nhận diện cấu hình** | Xử lý class `@Configuration`, `@Bean`, `@Import` hoặc cơ chế đăng ký khác. | Chưa. |
| **2. Đăng ký định nghĩa bean** | Tạo `BeanDefinition` chứa tên, factory method, scope, dữ liệu hỗ trợ dự đoán type. | Chưa. |
| **3. Dự đoán kiểu bean** | Xác định bean có phải `BeanFactoryPostProcessor`, `BeanPostProcessor`, loại bean cần autowire... | Thường có thể dựa metadata/return type; đôi khi không xác định được sớm. |
| **4. Khởi tạo instance** | Gọi static/instance factory method, inject dependency, thực hiện init callback/post-processing. | Có, lúc target thực sự được yêu cầu. |

Ví dụ:

```java
@Bean
static Formatter formatter() {
    return new Formatter();
}
```

Khi cấu hình được phân tích, Spring biết có một bean do `formatter` tạo ra và return type khai báo là `Formatter`. Điều đó **không yêu cầu `formatter()` chạy ngay khi đọc annotation**. Nếu đây là singleton non-lazy thông thường, Spring thường tạo instance trong giai đoạn pre-instantiation ở cuối refresh; nếu `@Lazy` thì có thể muộn hơn.

Sơ đồ tổng quát:

```text
Đăng ký @Configuration
         |
         v
ConfigurationClassPostProcessor phân tích @Bean
         |
         v
BeanDefinition có factory method + return type
         |
         +--> early type inspection
         |       +--> bean là BFPP / BPP?
         |       +--> resolve dependency bằng type?
         |
         v
Container quyết định thời điểm instantiate
         |
         +--> gọi static factory trực tiếp
         |       (không cần instance @Configuration)
         |
         +--> hoặc gọi instance factory trên bean @Configuration
                 (cần instance configuration phù hợp)
         |
         v
Áp dụng lifecycle / BeanPostProcessor / scope
```

Điểm chính: **Spring có thể cần biết type sớm hơn nhiều so với lúc tạo instance**, đặc biệt khi nhận diện processor tham gia khởi động container.

## 3. Cách một @Bean thông thường được gọi

Xét instance factory method:

```java
@Configuration
class JavaConfig {
    @Bean
    MessageCatalog messageCatalog() {
        return new MessageCatalog("hello");
    }
}
```

`MessageCatalog` là class ví dụ. Spring đăng ký method này làm nguồn tạo bean và thường cần một instance `JavaConfig` để gọi `messageCatalog()`.

Ngược lại:

```java
@Configuration
class JavaConfig {
    @Bean
    static MessageCatalog messageCatalog() {
        return new MessageCatalog("hello");
    }
}
```

Đây là **static factory method**; Spring có thể gọi `JavaConfig.messageCatalog()` mà không cần tạo instance `JavaConfig` chỉ để thực hiện factory method đó.

Một số chi tiết quan trọng:

- Cả hai vẫn tạo **Spring bean**, có tên, scope và lifecycle do container quản lý.
- Cả hai có thể được Spring nhận diện ở **giai đoạn bean definition**, trước khi method chạy.
- `static` chỉ nói về **cách gọi phương thức Java** và sự phụ thuộc vào instance class cấu hình; không thay đổi scope mặc định.
- Static method có thể nhận **tham số được Spring inject** như các `@Bean` factory method khác. Với BFPP/BPP, vẫn nên hạn chế dependencies để tránh kéo theo bean nghiệp vụ quá sớm.
- Một static `@Bean` method không được CGLIB override, nên không thể nhận semantics chặn lời gọi trực tiếp của các instance `@Bean` methods trong full `@Configuration`.

## 4. BeanFactoryPostProcessor cần được tạo sớm

`BeanFactoryPostProcessor` là extension point để đọc hoặc thay đổi **metadata của bean definitions** trước khi container tạo phần lớn bean ứng dụng.

```java
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;

public final class DefinitionInspector implements BeanFactoryPostProcessor {
    @Override
    public void postProcessBeanFactory(
            org.springframework.beans.factory.config.ConfigurableListableBeanFactory factory) {
        System.out.println(factory.containsBeanDefinition("myService"));
    }
}
```

Đây là class `DefinitionInspector` có thể biên dịch với dependency `spring-beans` trên classpath. Nội dung callback chỉ quan sát một tên bean, không tạo bean service.

Vì BFPP cần chạy ở **pha rất sớm**, Spring phải tìm được nó **trước khi các singleton nghiệp vụ thông thường được tạo**. Nếu khai báo BFPP bằng instance `@Bean`:

```java
@Configuration
class InfrastructureConfig {
    @Bean
    BeanFactoryPostProcessor definitionInspector() {
        return beanFactory -> {
            // Can thiệp vào BeanDefinition tại startup.
        };
    }
}
```

thì để tạo BFPP, Spring có thể phải **khởi tạo `InfrastructureConfig` sớm** trước khi mọi cơ chế annotation injection/lifecycle đã hoàn tất. Điều này có thể ảnh hưởng tới `@Autowired`, `@Value`, `@PostConstruct` nằm ngay trên configuration class đó hoặc các dependency của nó.

**Cách thường nên dùng:**

```java
@Configuration
class InfrastructureConfig {
    @Bean
    static BeanFactoryPostProcessor definitionInspector() {
        return beanFactory -> {
            // Can thiệp vào BeanDefinition tại startup.
        };
    }
}
```

Factory method ở đây **static**, nên Spring có thể tạo BFPP mà không cần dựng instance `InfrastructureConfig`. Cách viết này đặc biệt hữu ích khi configuration còn có những factory methods nghiệp vụ sẽ được xử lý ở giai đoạn bình thường.

Javadoc `@Bean` của Spring 6.2 nêu rõ nên khai báo static cho các `@Bean` trả về `BeanFactoryPostProcessor`; cấu hình không static có thể có thông báo INFO về rủi ro lifecycle.

### 4.1. Vì sao không đọc @Autowired trong constructor của @Configuration quá sớm?

Một cách viết kém an toàn là để constructor hoặc field của configuration chứa dependency vào bean nghiệp vụ, rồi factory method BFPP cần instance configuration để chạy.

```java
@Configuration
class RiskyConfig {
    @Autowired
    private SomeApplicationService service;

    @Bean
    BeanFactoryPostProcessor earlyProcessor() {
        return factory -> {
            // Dễ kích hoạt vòng phụ thuộc/khởi tạo quá sớm.
        };
    }
}
```

Đây là snippet minh họa: `SomeApplicationService` là kiểu giả định. Vấn đề không chỉ là annotation `@Autowired` có hay không; **giai đoạn** tạo `RiskyConfig` có thể quá sớm so với thời điểm annotation processor sẵn sàng. Static BFPP method giảm nhu cầu tạo configuration instance sớm.

Tuy vậy, nếu static factory method lại khai báo một tham số dependency là service nghiệp vụ nặng, việc giải quyết tham số đó vẫn có thể tạo service sớm. `static` không bảo vệ tự động khỏi mọi initialization side effect.

## 5. BeanPostProcessor cũng cần được nhận diện trước các bean thông thường

`BeanPostProcessor` (BPP) xử lý **bean instances** trong lifecycle: ví dụ kiểm tra marker, inject/lifecycle metadata hoặc wrap object bằng proxy.

Một BPP cần được đăng ký **trước khi những bean mà nó phải xử lý được tạo**. Vì vậy Spring phải có cơ chế **phát hiện bean nào là BPP dựa trên metadata type**.

Một khai báo phù hợp:

```java
@Configuration
class ProcessingConfig {
    @Bean
    static BeanPostProcessor auditProcessor() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String name) {
                return bean;
            }
        };
    }
}
```

Đoạn này cần import `org.springframework.beans.factory.config.BeanPostProcessor`, `Bean` và `Configuration`. Static factory tránh phải tạo instance configuration quá sớm.

**Hai nguyên tắc quan trọng, theo Spring 6.2 Javadoc:**

1. **Trả về kiểu thể hiện rõ tính chất BPP**: interface `BeanPostProcessor` hoặc implementation cụ thể của nó, không giấu sau `Object` hoặc interface không có quan hệ type phù hợp.
2. **Đánh dấu factory method là `static`**, lý tưởng **không có application-bean dependencies**, để tránh kéo các bean khác vào pha đăng ký post-processor.

Nếu BPP được tạo quá muộn, những bean đã được khởi tạo trước đó có thể **không còn cơ hội được xử lý bởi toàn bộ post-processors**, nhất là auto-proxying. Spring có thể cảnh báo kiểu “not eligible for getting processed by all BeanPostProcessors”.

### 5.1. Khai báo return type sai làm mất cơ hội phát hiện sớm

Ví dụ phản diện:

```java
@Bean
static Object auditProcessor() {
    return new MyAuditBeanPostProcessor();
}
```

`MyAuditBeanPostProcessor` là một implementation giả định của `BeanPostProcessor`. Vì declared return type chỉ là `Object`, container **không thể luôn xác định trước lúc tạo instance** rằng bean này là BPP. Spring có một số kỹ thuật dự đoán type bổ sung, nhưng không được phụ thuộc vào suy đoán tình cờ để hạ tầng quan trọng hoạt động đúng pha.

Nên viết:

```java
@Bean
static BeanPostProcessor auditProcessor() {
    return new MyAuditBeanPostProcessor();
}
```

hoặc khai báo chính class `MyAuditBeanPostProcessor` nếu kiểu public cụ thể phù hợp.

Với BFPP cũng vậy: khai báo kiểu `BeanFactoryPostProcessor` hoặc implementation cụ thể trong method signature. Một factory method trả kiểu `Object` rồi thực tế tạo BFPP sẽ khiến thông tin type sớm không rõ ràng.

### 5.2. @Bean static và BeanPostProcessor không phải bắt buộc tuyệt đối với mọi bean

Ví dụ một object đơn giản:

```java
@Bean
static Clock clock() {
    return Clock.systemUTC();
}
```

Đoạn này hợp lệ khi import `java.time.Clock`, nhưng dùng `static` không đem lại lợi ích lifecycle tương tự BFPP/BPP. Phần lớn bean nghiệp vụ có thể khai báo bằng instance `@Bean` với tham số injection. **Không cần chuyển mọi `@Bean` thành static**.

## 6. Ví dụ hoàn chỉnh Java 17+: quan sát type sớm và instance muộn

Chúng ta dùng **Spring Framework 6.2.9** với `AnnotationConfigApplicationContext`, không cần Spring Boot hay server. Ví dụ có:

- Một **static `@Bean BeanFactoryPostProcessor`** in kết quả quan sát ở pha xử lý metadata.
- Một **static `@Bean BeanPostProcessor`** theo dõi bean nghiệp vụ sau initialization.
- Một **static `@Bean Catalog`** là bean thông thường.
- Một **instance `@Bean Gateway`** nhận `Catalog` qua factory method parameter.
- Một constructor trên `Config` đếm số lần configuration instance được tạo.
- Một lời gọi Java trực tiếp tới static factory để minh họa nó **không phải lookup container**.

### 6.1. Cấu trúc dự án

```text
static-bean-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── StaticBeanDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'static-bean-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.StaticBeanDemo'
}
```

**`src/main/java/demo/StaticBeanDemo.java`**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class StaticBeanDemo {

    public static final class Catalog {
        private final String value;

        public Catalog(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public static final class Gateway {
        private final Catalog catalog;

        public Gateway(Catalog catalog) {
            this.catalog = catalog;
        }

        public String message() {
            return catalog.value() + "-gateway";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        private static final AtomicInteger CREATED = new AtomicInteger();
        private static final AtomicInteger GATEWAYS_SEEN =
                new AtomicInteger();

        public Config() {
            CREATED.incrementAndGet();
        }

        // BFPP phải được nhận diện và tạo ở pha metadata.
        @Bean
        static BeanFactoryPostProcessor earlyInspector() {
            return factory -> {
                System.out.println("early:config-count="
                        + CREATED.get());
                System.out.println("early:catalog-definition="
                        + factory.containsBeanDefinition("catalog"));
                System.out.println("early:catalog-type="
                        + factory.getType("catalog").getSimpleName());
                System.out.println("early:catalog-instantiated="
                        + factory.containsSingleton("catalog"));
            };
        }

        // Return type giúp Spring nhận diện BPP trước khi tạo Gateway.
        @Bean
        static BeanPostProcessor observer() {
            return new BeanPostProcessor() {
                @Override
                public Object postProcessAfterInitialization(
                        Object bean, String beanName) {
                    if ("gateway".equals(beanName)) {
                        GATEWAYS_SEEN.incrementAndGet();
                    }
                    return bean;
                }
            };
        }

        // Đối tượng bình thường cũng có thể được tạo từ static @Bean.
        @Bean
        static Catalog catalog() {
            return new Catalog("demo");
        }

        // Factory method instance; dependency được inject qua tham số.
        @Bean
        Gateway gateway(Catalog catalog) {
            return new Gateway(catalog);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Catalog first = context.getBean(Catalog.class);
            Catalog second = context.getBean(Catalog.class);
            Gateway gateway = context.getBean(Gateway.class);

            System.out.println("context-ready");
            System.out.println("config-count=" + Config.CREATED.get());
            System.out.println("gateway=" + gateway.message());
            System.out.println("bpp-saw-gateway="
                    + (Config.GATEWAYS_SEEN.get() == 1));
            System.out.println("managed-catalog-same=" + (first == second));

            Catalog direct = Config.catalog();
            System.out.println("direct-call-is-managed=" + (direct == first));
        }
    }
}
```

Chương trình đặt `Config` dưới dạng static nested class để Spring có thể đăng ký nó rõ ràng. `Config.CREATED` được tăng chỉ khi **instance Config** được tạo; gọi static factory `earlyInspector()`, `observer()` hoặc `catalog()` không tự tăng biến đếm.

### 6.2. Chạy

Từ thư mục `static-bean-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, có thể dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Lệnh `javac StaticBeanDemo.java` đơn lẻ không đủ nếu chưa tự cung cấp Spring jars lên classpath; tác vụ Gradle sẽ xử lý dependencies và classpath.

**Các dòng `System.out.println` của chương trình:**

```text
early:config-count=0
early:catalog-definition=true
early:catalog-type=Catalog
early:catalog-instantiated=false
context-ready
config-count=1
gateway=demo-gateway
bpp-saw-gateway=true
managed-catalog-same=true
direct-call-is-managed=false
```

Chương trình không có thread tạo log riêng; log Gradle hoặc logging framework có thể xuất hiện tùy cấu hình môi trường nhưng không thuộc mười dòng trên.

### 6.3. Giải thích các dòng output

**`early:config-count=0`.** Container tạo `earlyInspector` từ **static `@Bean`** mà không cần khởi tạo instance `Config`. Vì BFPP chạy ở pha sớm, số lần constructor `Config()` được gọi vẫn bằng 0.

**`early:catalog-definition=true`.** Metadata của `@Bean Catalog catalog()` đã được đăng ký như bean definition khi BFPP quan sát registry. **Đăng ký definition không đồng nghĩa target đã được khởi tạo.**

**`early:catalog-type=Catalog`.** Spring có thể dự đoán bean type từ chữ ký static factory method `static Catalog catalog()`. Phương thức `getType("catalog")` trả kiểu dự kiến mà **không cần gọi chính factory method để tạo Catalog**.

**`early:catalog-instantiated=false`.** Trong thời điểm đó `catalog` chưa tồn tại trong singleton cache. Điều này tách rõ **type visibility** với **instance availability**.

**`config-count=1`.** Trong quá trình refresh, container tạo `Config` để gọi factory method instance `gateway(Catalog)`. Static `@Bean` methods đã có thể phục vụ nhu cầu sớm mà không kéo theo instance cấu hình.

**`bpp-saw-gateway=true`.** BeanPostProcessor `observer` đã được tạo/đăng ký trước khi bean `gateway` hoàn tất initialization, nên callback `postProcessAfterInitialization` nhận `gateway` đúng một lần trong ví dụ.

**`managed-catalog-same=true`.** `catalog` là bean singleton mặc định; hai lần `getBean` trả cùng instance trong context.

**`direct-call-is-managed=false`.** Lệnh `Config.catalog()` là **lời gọi static Java trực tiếp**, tạo đối tượng mới không qua Spring container. Static `@Bean` methods không được CGLIB intercept; chỉ lời gọi từ bean factory mới chịu quản lý scope và lifecycle.

> Kết quả minh họa đúng hai trục riêng: **đã biết bean type** không có nghĩa **đã tạo object**, và **static factory method** không có nghĩa kết quả của mọi lời gọi Java tới method ấy đều được container quản lý.

## 7. Tại sao return type phải “lộ” đúng kiểu cho Spring?

Xét factory method:

```java
@Bean
static Object earlyProcessor() {
    return new MySpecialBeanPostProcessor();
}
```

`MySpecialBeanPostProcessor` là class ví dụ implement `BeanPostProcessor`. Container nhìn vào metadata và biết chắc return type tối thiểu chỉ là `Object`. Trước khi instance thực sự tồn tại, Spring có thể **chưa biết** đó là một BPP cần đăng ký trước những bean khác.

Đổi chữ ký:

```java
@Bean
static BeanPostProcessor earlyProcessor() {
    return new MySpecialBeanPostProcessor();
}
```

thì container có bằng chứng từ khai báo rằng bean thuộc loại `BeanPostProcessor`. Khi Spring tìm BPPs sớm, bean definition dễ được nhận diện đúng thời điểm hơn.

**Quy tắc này áp dụng rộng hơn BPP/BFPP:**

```java
@Bean
PaymentGateway gateway() {
    return new DefaultPaymentGateway();
}
```

Nếu code inject `PaymentGateway` ở các bean khác, declared type đã đủ. Nhưng nếu code inject `DefaultPaymentGateway` trước khi bean được tạo và method chỉ khai báo `PaymentGateway`, Spring có thể chưa xác định được concrete type trong quá trình **type prediction**. Một số ứng viên chỉ trở nên rõ khi singleton thực sự đã tạo xong; kết quả autowiring có thể phụ thuộc thời điểm và thứ tự khởi tạo.

Vì vậy, Spring khuyên khai báo factory method return type **cụ thể ít nhất tới mức các injection point thật sự cần**. Không nhất thiết luôn khai báo concrete class nếu hệ thống nhất quán dùng interface; nhưng tránh `Object` cho bean quan trọng và tránh cố ý che loại extension point cần container tìm sớm.

### 7.1. Trường hợp FactoryBean<T> khác với factory method @Bean

Hai tên gần nhau dễ nhầm:

- **`@Bean` factory method:** phương thức tạo object Spring bean.
- **`FactoryBean<T>`:** một interface đặc biệt mà implementation tạo **product object** khi container truy xuất bean; muốn lấy chính factory thường dùng tiền tố `&` trong bean name.

Giả sử:

```java
@Bean
FactoryBean<MyClient> myClientFactoryBean() {
    return new MyClientFactoryBean();
}
```

Đây là snippet cấu trúc, giả định `MyClientFactoryBean implements FactoryBean<MyClient>` và `MyClient` là class nghiệp vụ.

Container có thể dùng thông tin generic `FactoryBean<MyClient>` và `getObjectType()` của factory để suy ra type của **product bean**. Nếu return type của `@Bean` chỉ là `FactoryBean` raw type hoặc `Object`, type prediction có thể khó hơn. Trong một số trường hợp, việc xác định object type của `FactoryBean` còn phụ thuộc metadata/cách triển khai `getObjectType()`, và Spring có thể phải phân biệt lookup không eager (`allowEagerInit=false`) với lookup được phép tạo factory.

**Điểm cần nhớ:** đây là lớp dự đoán type bổ sung, không phải vì `@Bean static` nên mọi product type tự động luôn được xác định sớm.

## 8. static không tự làm bean thành eager hay singleton JVM

Ba phát biểu dưới đây đều sai:

1. “Phương thức `@Bean static` sẽ chạy ngay khi class được load.”
2. “Một static `@Bean` luôn chỉ được gọi một lần trong cả JVM.”
3. “Một static `@Bean` không thể tạo prototype.”

### 8.1. Bean definition khác với class initialization

Java có thể tải class và xử lý static initializer theo quy tắc JVM, còn Spring có vòng đời bean riêng. `@Bean static` không có nghĩa Spring gọi method đó ở thời điểm JVM load class.

Một static initializer:

```java
static {
    System.out.println("java-class-init");
}
```

là cơ chế Java, hoàn toàn khác với việc Spring gọi method mang `@Bean` khi khởi tạo bean. Đừng dùng static initializer để gián tiếp thay thế BeanFactory lifecycle logic.

### 8.2. Scope vẫn do bean definition quyết định

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
static TaskToken taskToken() {
    return new TaskToken();
}
```

Đây là snippet minh họa: `TaskToken` là class ví dụ, cần import `Scope` và `ConfigurableBeanFactory`. Container có thể gọi static factory **mỗi lần cần một prototype mới**. Ngược lại, một static `@Bean` singleton chỉ được container tạo theo chính sách singleton của **một context**, không phải biến static toàn JVM.

**Quan trọng:** nếu code ngoài Spring gọi thẳng `Config.taskToken()` thì lời gọi Java đó không tuân theo bean-scope lookup; nó thực thi factory method trực tiếp.

### 8.3. @Lazy vẫn có ý nghĩa đối với singleton

```java
@Bean
@Lazy
static HeavyClient heavyClient() {
    return new HeavyClient();
}
```

`HeavyClient` là kiểu minh họa. Với singleton lazy, container có thể trì hoãn thực thi method đến khi bean được yêu cầu. Việc method là static không tự buộc bean tạo ở refresh. Nếu một eager bean khác phụ thuộc vào `HeavyClient`, Spring vẫn có thể cần tạo client sớm để hoàn thành dependency.

BFPP/BPP là **trường hợp đặc biệt** cần khởi tạo sớm để can thiệp lifecycle; chúng không giống các singleton nghiệp vụ thông thường.

## 9. static @Bean có được inter-bean method interception không?

Trong full `@Configuration(proxyBeanMethods=true)`, Spring có thể dùng CGLIB subclass để chặn các lời gọi **instance** `@Bean` methods giữa chúng, bảo đảm semantics truy xuất bean qua container cho các lời gọi đó.

Nhưng **Java static methods không thể override bởi subclass**, nên static `@Bean` methods **không được chặn**, kể cả khi class cấu hình bật `proxyBeanMethods=true`.

Ví dụ:

```java
@Configuration
class CatalogConfig {
    @Bean
    static Catalog catalog() {
        return new Catalog("demo");
    }

    @Bean
    Gateway gateway() {
        return new Gateway(catalog()); // Lời gọi Java trực tiếp.
    }
}
```

`Catalog`/`Gateway` là hai class từ ví dụ chạy được ở mục 6. Method `gateway()` gọi static `catalog()` và có thể tạo object mới, **không lấy singleton bean đã được quản lý**. Việc bật enhancement cho instance methods của `CatalogConfig` không sửa được tính chất static của `catalog()`.

**Cách đúng để ghép bean:**

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean
    static Catalog catalog() {
        return new Catalog("demo");
    }

    @Bean
    Gateway gateway(Catalog catalog) {
        return new Gateway(catalog);
    }
}
```

Spring resolve `Catalog` trong tham số theo bean definition và scope. Cách này hoạt động rõ ràng cả với static và instance `@Bean`, giảm sự phụ thuộc vào proxy/configuration enhancement.

### 9.1. @Configuration(proxyBeanMethods=false) và @Component lite mode

Khi `@Configuration(proxyBeanMethods=false)`, ngay cả lời gọi **instance** giữa các `@Bean` methods cũng có semantics Java thông thường, thay vì chặn qua CGLIB như full mode.

Các phương thức `@Bean` đặt trong class `@Component` (không phải full `@Configuration`) cũng thường được xử lý theo **lite mode** và không nhận interception của full configuration. Vì vậy thói quen dùng **factory method parameters** tốt hơn dựa vào việc gọi trực tiếp method khác.

### 9.2. Không lẫn static @Bean với static field giữ state

`@Bean static Catalog catalog()` là **static method**. Nó không nhất thiết có static field chứa singleton `Catalog`. Spring có thể quản lý nhiều `ApplicationContext` trong một JVM và tạo một singleton `catalog` khác nhau cho từng context; nếu sử dụng static field mutable để cache object toàn cục thì đó là cơ chế riêng, dễ tạo rò rỉ trạng thái/test contamination.

## 10. Hai lỗi startup thường liên quan return type và pha early initialization

### 10.1. BPP giấu dưới Object

```java
@Bean
static Object metricsBean() {
    return new MetricsBeanPostProcessor();
}
```

Nếu `MetricsBeanPostProcessor` implement `BeanPostProcessor` nhưng method chỉ khai báo `Object`, quá trình Spring tìm kiếm BPP theo type có thể bỏ sót bean trước khi nó được instantiate.

**Sửa:**

```java
@Bean
static BeanPostProcessor metricsBean() {
    return new MetricsBeanPostProcessor();
}
```

Đây là snippets minh họa; implementation cần được định nghĩa. Spring docs khuyên khai báo return type là implementation cụ thể hoặc interface `BeanPostProcessor` ít nhất, để early type detection hoạt động tin cậy.

### 10.2. Non-static @Bean tạo BPP làm @Configuration khởi tạo quá sớm

```java
@Configuration
class RiskyConfig {
    @Autowired
    SomeApplicationService service;

    @Bean
    BeanPostProcessor processor() {
        return new CustomProcessor();
    }
}
```

`SomeApplicationService` và `CustomProcessor` là kiểu minh họa. Để tạo BPP qua instance method, Spring phải tạo `RiskyConfig` trước; điều đó có thể kéo theo application service sớm. Bean này có thể **không nhận đầy đủ các post-processor** và Spring có thể ghi WARN rằng bean “not eligible for getting processed by all BeanPostProcessors”.

**Sửa:**

```java
@Configuration
class SaferConfig {
    @Bean
    static BeanPostProcessor processor() {
        return new CustomProcessor();
    }
}
```

Và không inject application beans nặng vào chính processor nếu không cần thiết.

**Không hiểu sai:** biến method thành static không bảo đảm mọi cấu hình sai lập tức được sửa. Nếu custom processor vẫn chủ động `getBean("service")` trong constructor/khởi tạo thì có thể tạo service quá sớm.

## 11. Phát hiện kiểu sớm khác “tạo trước” và “tiêm trước”

Để dự đoán chính xác, cần phân biệt ba API/khả năng:

- `BeanFactory.getType(beanName)`: cố gắng tìm type của bean sẽ trả về khi lookup, có thể dựa metadata, factory method hoặc cơ chế `FactoryBean`. Một số type không đoán chắc được trước khi instance tồn tại.
- `BeanFactory.containsBeanDefinition(beanName)`: cho biết có definition được đăng ký trực tiếp trong bean factory hiện tại, **không nói instance đã tạo**.
- `SingletonBeanRegistry.containsSingleton(beanName)`: kiểm tra cache singleton hiện tại, **không phải kiểm tra bean definition**.

Trong ví dụ chạy được, kết quả đầu startup:

```text
early:catalog-definition=true
early:catalog-type=Catalog
early:catalog-instantiated=false
```

hoàn toàn không mâu thuẫn. Spring biết cách tạo `Catalog` và dự đoán kiểu của nó, nhưng chưa tạo instance. Nếu có một injection point cần `Catalog` trong phase sớm, việc resolve dependency có thể kích hoạt tạo bean và làm trạng thái thứ ba đổi sang true.

### 11.1. Return type quá tổng quát

Giả sử:

```java
@Bean
PaymentProcessor paymentProcessor() {
    return new StripePaymentProcessor();
}
```

`PaymentProcessor` và `StripePaymentProcessor` là kiểu nghiệp vụ giả định. Metadata bảo đảm bean ít nhất đáp ứng interface `PaymentProcessor`. Trước khi factory method chạy, container không phải lúc nào cũng biết concrete implementation để match injection point yêu cầu `StripePaymentProcessor`.

Nếu Spring buộc xác định trước singleton được tạo, một component inject concrete type có thể không được chọn. Ngược lại, khi singleton đã được instantiate, type thực tế có thể được biết và dẫn đến kết quả matching khác. Vì vậy:

- Nếu consumer chỉ cần interface, inject `PaymentProcessor` và method trả interface là rõ ràng.
- Nếu thật sự cần concrete type, cân nhắc return type là `StripePaymentProcessor`, cùng với thiết kế API và proxying hợp lệ.
- Với extension points của Spring, bắt buộc để lộ interface/cụ thể thích hợp (ví dụ `BeanPostProcessor`), không dùng `Object`.

### 11.2. Không “probe” bean bằng getBean() sớm chỉ để biết type

Một BFPP không nên gọi `getBean()` của bean nghiệp vụ chỉ để xem class hay thuộc tính. Làm vậy có thể kích hoạt instantiation quá sớm, trước khi đầy đủ BPP/advisors được đăng ký, gây hành vi sai hoặc proxy bị bỏ lỡ.

Ưu tiên đọc `BeanDefinition`, `getType()` và thông tin metadata; nếu cần xác định FactoryBean product type, cân nhắc đúng API và tác dụng phụ của eager initialization.

## 12. Khai báo post-processor rõ ràng trong dự án thực

Đối với BFPP:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    static BeanFactoryPostProcessor definitionPolicy() {
        return beanFactory -> {
            // Chỉnh metadata đã đăng ký, nếu thật sự cần.
        };
    }
}
```

Đối với BPP:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    static BeanPostProcessor decoratorProcessor() {
        return new MyDecoratorPostProcessor();
    }
}
```

`MyDecoratorPostProcessor` là class minh họa cần implement `BeanPostProcessor`. Hai ví dụ là các cấu hình độc lập; trong code thật có thể đặt chung nếu tên methods khác nhau và imports đúng.

**Checklist hạ tầng:**

1. Phương thức trả type cụ thể hoặc ít nhất `BeanFactoryPostProcessor`/`BeanPostProcessor`.
2. Phương thức nên `static` để tránh tạo instance `@Configuration` sớm.
3. Hạn chế tối đa tham số là bean nghiệp vụ.
4. Nếu processor cần property/source thông thường, xem nó có thể dùng metadata/`Environment`/giá trị cấu hình sớm và an toàn hay không; đừng buộc client/network/service khởi tạo trước chu trình BPP hoàn tất.
5. Nếu processor tạo proxy, kiểm tra bean nào thực sự đủ điều kiện nhận proxy và thứ tự các post-processor liên quan.
6. Viết integration test tạo context nhỏ và quan sát bean definition, type prediction, callback và thứ tự sự kiện quan trọng.

### Khi nào không nên viết post-processor tùy chỉnh?

Hầu hết ứng dụng không cần tự tạo BFPP/BPP. Spring đã có nhiều hạ tầng sẵn cho property placeholders, autowiring, lifecycle, transaction, caching, async và validation. Chỉ viết processor mới khi bạn có yêu cầu can thiệp vào metadata hoặc bean instance mà không thể diễn đạt bằng cấu hình sẵn, và bạn hiểu lifecycle để tránh early-instantiation bugs.

## 13. Thực hành biến thể từ ví dụ

### 13.1. Đổi static Catalog sang instance @Bean

Trong `StaticBeanDemo.Config`, thay:

```java
@Bean
static Catalog catalog() {
    return new Catalog("demo");
}
```

bằng:

```java
@Bean
Catalog catalog() {
    return new Catalog("demo");
}
```

BFPP `earlyInspector` vẫn được tạo từ static method và có thể nhận diện kiểu trả về của `catalog` dựa vào metadata configuration/factory method khi Spring đã phân tích cấu hình. Tuy nhiên, việc **tạo Catalog** giờ cần instance `Config`, còn trước đó không cần instance đó. Đây là khác biệt về **phương thức instantiate**, không phải quy tắc scope.

Không gắn kỳ vọng cứng rằng mọi cách probe type trên một instance factory ở mọi biến thể đều hoàn toàn không tạo configuration instance: kết quả có thể phụ thuộc hạ tầng dự đoán method/type, cách factory bean được định nghĩa và thời điểm truy vấn.

### 13.2. Đổi return type của BPP thành Object

Thay `static BeanPostProcessor observer()` thành `static Object observer()`. Về Java, method vẫn trả instance implementing BPP, nhưng Spring có thể không phát hiện bean này như `BeanPostProcessor` trong lượt tìm kiếm **trước** initialization, khiến `bpp-saw-gateway` không còn là bằng chứng được bảo đảm.

Thí nghiệm này chỉ để thấy tác dụng của type metadata; **không dùng kiểu Object trong ứng dụng thật** nếu muốn Spring tự nhận diện processor.

### 13.3. Đổi static BFPP thành instance BFPP

Thay `static BeanFactoryPostProcessor earlyInspector()` bằng instance method. Vì Spring phải gọi method trên `Config`, việc này có thể làm `Config.CREATED` tăng lên trước callback BFPP, khiến `early:config-count` không còn là 0 và sinh lifecycle warning. Đây là minh họa tại sao khuyến nghị static tồn tại; không coi việc thay đổi output là “Spring bug”.

### 13.4. Biến Catalog thành prototype

Thêm `@Scope("prototype")` vào static `@Bean Catalog catalog()`. Khi ấy mỗi lần `context.getBean(Catalog.class)` thông thường tạo instance mới, dù method vẫn static. `managed-catalog-same` sẽ trở thành false. Với `Gateway` singleton, catalog được inject trong `gateway(Catalog)` vẫn là **một instance cụ thể** tại thời điểm tạo Gateway; nó không tự thay đổi theo từng lần gọi `message()`.

### 13.5. Gọi trực tiếp Catalog factory method

Trong `main` đã có:

```java
Catalog direct = Config.catalog();
System.out.println(direct == context.getBean(Catalog.class));
```

Kết quả false trong cấu hình demo vì lời gọi trực tiếp tạo object mới. Đó là **Java call**, không phải Spring bean lookup. Với các phương thức static trả singleton cache tự viết thì Java call có thể tình cờ trả cùng object, nhưng chuyện đó do code factory quyết định và **không** được container bảo đảm.

## 14. Những nhầm lẫn thường gặp

### Sai lầm 1: “static @Bean được tạo ngay lúc startup class”

`static` cho phép gọi method không cần instance class cấu hình. Thời điểm **Spring gọi method** vẫn do bean lifecycle/scope/early-infrastructure quyết định; chỉ riêng static không tạo eager behavior.

### Sai lầm 2: “Static @Bean chỉ có một singleton trên toàn JVM”

Scope singleton thuộc về **mỗi ApplicationContext**, không phải static Java class. Hai context khác nhau có thể gọi cùng static factory và nhận hai bean singleton khác nhau. Khi tự tạo object bằng static method call còn có thể nhận instance hoàn toàn nằm ngoài context.

### Sai lầm 3: “Mọi @Bean nên static để tăng tốc”

Static không tự tối ưu mọi application bean. Instance `@Bean` với constructor/factory-method injection thường đủ rõ. Lợi ích rõ nhất của static là **tránh khởi tạo sớm configuration class khi phải tạo infrastructure bean BFPP/BPP**.

### Sai lầm 4: “Tôi trả Object vẫn ổn vì runtime object là BeanPostProcessor”

Container cần phát hiện BPP **trước khi** runtime object tồn tại. Declared return type quá rộng có thể khiến bean đặc biệt không được đăng ký vào hệ xử lý đúng pha.

### Sai lầm 5: “Có return type đúng thì bean đã được tạo”

Bean definition và type prediction không đồng nghĩa đã instantiate singleton. Dùng `containsSingleton` hoặc quan sát factory/callback để phân biệt thời điểm.

### Sai lầm 6: “Static @Bean hưởng interception nhờ @Configuration”

Static method không được override; direct call tới static factory thực hiện Java bình thường. Chỉ lời gọi do Spring bean factory điều phối mới tuân theo bean scope/lifecycle.

### Sai lầm 7: “Non-static BFPP không thể chạy”

Nó **có thể** chạy nhưng tạo configuration bean sớm và có nguy cơ gây lỗi lifecycle. Spring khuyến nghị static để tránh rủi ro, không phải vì Java cấm instance factory method trả BFPP.

### Sai lầm 8: “Static BPP có dependency vào application service vẫn an toàn”

Factory có thể không cần instance `@Configuration`, nhưng khi Spring resolve tham số dependency, service vẫn có thể bị kéo vào pha sớm. Ưu tiên processor không kéo theo những bean cần proxy/lifecycle processing.

### Sai lầm 9: “Dùng getType() thì chắc chắn không bao giờ có side effect”

Trong trường hợp phổ biến, return type đủ cụ thể giúp Spring dự đoán type qua metadata. Nhưng FactoryBean, proxy, custom factory metadata hoặc lựa chọn eager-init có thể làm kết quả phức tạp hơn. Đừng biến `getType()` thành lời cam kết tuyệt đối rằng không có bean nào bị tạo.

### Sai lầm 10: “Spring nhìn chữ static là biết bean là BFPP/BPP”

Không. Để biết loại bean đặc biệt, Spring cần **thông tin type** phù hợp và bean definition được đăng ký đúng pha. `static` giải quyết **khả năng gọi factory không cần configuration instance**, còn **return type** giải quyết **khả năng nhận diện bean theo kiểu**. Hai thuộc tính phục vụ hai nhu cầu khác nhau.

## 15. Cách debug trong ứng dụng thật

Khi BPP không hoạt động hoặc có cảnh báo bean không đủ điều kiện auto-proxy, kiểm tra:

- Method `@Bean` có khai báo **static** hay Spring buộc tạo configuration instance sớm?
- Return type trên method có **đủ cụ thể** (BFPP/BPP/implementation) để nhận diện trước instantiation?
- Processor có field/constructor/factory parameters yêu cầu **bean nghiệp vụ** không?
- Bean nghiệp vụ có bị yêu cầu bằng `getBean()` trong BFPP hoặc constructor configuration/BPP không?
- Có processor nào được đăng ký rất muộn, sau khi service đã tạo không?
- Cấu hình có đang chạy ở `AnnotationConfigApplicationContext`, web child context hay Spring Boot context nào khác?
- Có tạo bean thủ công bằng `new` hoặc gọi static factory trực tiếp thay vì lấy từ container không?

Kiểm tra bean definition/type khi context đã được nạp:

```java
ConfigurableListableBeanFactory factory = context.getBeanFactory();

System.out.println(factory.containsBeanDefinition("catalog"));
System.out.println(factory.getType("catalog"));
System.out.println(factory.containsSingleton("catalog"));
```

Đây là snippet cần import `org.springframework.beans.factory.config.ConfigurableListableBeanFactory` và biến `context` từ ví dụ. Để quan sát **trước instantiation**, đặt nó trong BFPP giống demo; chạy sau `refresh()` thường thấy bean singleton đã được tạo.

Nếu Spring ghi thông báo rằng một bean không đủ điều kiện được **mọi** BeanPostProcessor xử lý, xem những component nào buộc phải tạo sớm và loại bỏ dependency/call path đó. Không nên tắt toàn bộ auto-proxying hay che log để giải quyết triệu chứng.

## 16. Kiểm thử hành vi sớm mà không suy đoán thứ tự ngoài hợp đồng

Một test integration có thể dựng `AnnotationConfigApplicationContext` chỉ với cấu hình hạ tầng cần kiểm tra, rồi sử dụng recorder/counter:

1. BFPP ghi số lần configuration instance được tạo **khi callback chạy**; với static factory không cần config instance, nó có thể là 0 trong fixture đơn giản.
2. BFPP xem bean definition và `getType()` khi bean đích chưa được tạo.
3. BPP ghi các tên bean đã nhận tại `postProcessAfterInitialization`.
4. Sau `refresh()`, test kiểm tra bean singleton và dependency injection.
5. Một lời gọi trực tiếp static factory method được so với `context.getBean(...)` để chứng minh khác biệt.

Ví dụ kiểm tra trong chương trình chính:

```java
if (Config.GATEWAYS_SEEN.get() != 1) {
    throw new AssertionError("Gateway was not observed by BPP");
}
```

Đoạn trên dùng `Config` của `StaticBeanDemo`, chỉ hợp lệ khi đặt trong outer class/nơi có quyền đọc field theo luật Java. Điều kiện này bảo vệ kỳ vọng quan trọng là bean mục tiêu được BPP nhận. Khi test production, nên dùng JUnit assertions và fixture tách biệt, tránh phụ thuộc những log chưa được bảo đảm ổn định bởi Spring.

**Cảnh báo về experiment:** nếu đổi BFPP/BPP của fixture từ static sang instance hoặc đổi declared return type thành `Object`, đừng tiếp tục áp nguyên output gốc như chuẩn tuyệt đối. Mục đích của biến thể là quan sát **khác biệt lifecycle**, không tìm cách làm nó vẫn giống hệt bản đúng.

## 17. Câu hỏi tự luyện và đáp án

**Câu 1.** Static `@Bean` trả `Catalog` có bắt buộc tạo Catalog trước mọi bean khác không?

**Đáp:** Không. Static chỉ cho phép factory method chạy mà không cần instance cấu hình. Thời điểm tạo Catalog phụ thuộc scope, lazy và dependency.

**Câu 2.** Vì sao BFPP `@Bean` thường nên static?

**Đáp:** BFPP được container tìm và tạo rất sớm. Static factory có thể được gọi mà không khởi tạo configuration class sớm, nhờ đó tránh một số xung đột với annotation injection/lifecycle.

**Câu 3.** Vì sao BPP factory method không nên khai báo return type `Object`?

**Đáp:** Container cần phát hiện BPP theo type trước khi tạo bean bình thường. Return type quá rộng có thể khiến type prediction không nhận ra nó là BPP.

**Câu 4.** Static `@Bean` có phải static singleton toàn JVM không?

**Đáp:** Không. Spring scope mặc định singleton thuộc về mỗi context. Direct Java method invocation vẫn có thể tạo object độc lập.

**Câu 5.** Lời gọi `Config.catalog()` và `context.getBean(Catalog.class)` khác nhau thế nào?

**Đáp:** Lời gọi đầu là Java static call thông thường, không áp dụng Spring scope/lifecycle. Lời gọi thứ hai lấy bean do container quản lý.

**Câu 6.** Trong demo, vì sao `early:catalog-type=Catalog` và `early:catalog-instantiated=false` cùng đúng?

**Đáp:** Container đã có definition với return type xác định được nhưng chưa chạy factory để tạo singleton target.

**Câu 7.** Return type `PaymentGateway` trả về implementation `StripePaymentGateway` có vấn đề gì?

**Đáp:** Không vấn đề nếu consumers chỉ cần `PaymentGateway`. Nếu một consumer yêu cầu concrete implementation ngay ở pha type matching sớm, container có thể chưa nhận diện type đó trước khi instance được tạo.

**Câu 8.** Đổi static BFPP sang non-static có luôn ném exception không?

**Đáp:** Không nhất thiết. Nhưng có thể buộc tạo configuration instance sớm và phát sinh INFO/warning hoặc lifecycle side effect; dùng static theo khuyến nghị Spring.

**Câu 9.** BPP static method nhận dependency `MyService` qua tham số có hoàn toàn tránh early bean creation không?

**Đáp:** Không. Spring có thể phải khởi tạo `MyService` để cung cấp tham số, gây đúng rủi ro mà static định tránh. Hạn chế application dependencies cho early processors.

**Câu 10.** Phân biệt `BeanFactoryPostProcessor` và `BeanPostProcessor`?

**Đáp:** BFPP xử lý bean definition/metadata trước khi tạo phần lớn bean ứng dụng. BPP xử lý bean instance trong quá trình initialization và có thể wrap/proxy instance.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — @Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html): static BFPP/BPP factory methods, type visibility, full/lite mode, scoping và lifecycle.
- [Spring Framework 6.2 — BeanPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html): giai đoạn đăng ký BPP, khuyến nghị static factory.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): BFPP/BPP, phát hiện type sớm, warning về early initialization.
- [Spring Framework — Using @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): return type của factory method và type prediction.
- [Spring Framework — Using @Configuration Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html): full configuration, inter-bean calls và proxy semantics.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definitions, factory method và `BeanFactory.getType`.

**Điểm cốt lõi:** `static @Bean` giúp Spring tạo một bean **không phải instantiate class `@Configuration` trước**, đặc biệt quan trọng cho **BFPP/BPP cần được tạo rất sớm**. **Declared return type** giúp container **nhận diện bean theo kiểu trước lúc nó được tạo**. Cả hai yếu tố bổ sung nhau: static giải quyết thời điểm gọi factory, return type giải quyết khả năng tìm đúng extension point. Không yếu tố nào tự biến mọi bean thành eager hoặc singleton toàn JVM.
