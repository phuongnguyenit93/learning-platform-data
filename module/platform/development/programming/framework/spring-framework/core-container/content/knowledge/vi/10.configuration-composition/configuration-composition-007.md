# Đăng ký định nghĩa bằng ImportBeanDefinitionRegistrar trong Spring Core Container

## 1. Mục tiêu và phạm vi

Trong Spring Framework, đa số bean được khai báo bằng `@Component`/`@Service`, phương thức `@Bean` trong một class `@Configuration`, hoặc cấu hình XML. Nhưng thư viện hạ tầng, starter, module tích hợp và các annotation kiểu `@Enable...` đôi khi cần **tự tạo bean definitions một cách có điều kiện và có cấu hình** ngay trong lúc Spring xử lý cấu hình Java.

Interface **`ImportBeanDefinitionRegistrar`** là một điểm mở rộng dành cho việc đó. Một class triển khai registrar có thể được đưa vào cấu hình thông qua `@Import`. Spring gọi registrar trong quá trình phân tích configuration classes và trao cho nó:

- `AnnotationMetadata`: metadata annotation của class đang import registrar.
- `BeanDefinitionRegistry`: registry của container hiện tại, dùng để kiểm tra và thêm bean definitions.
- Trong overload ba tham số, một `BeanNameGenerator` được Spring dùng cho những imported beans.

Registrar chỉ định nghĩa **bean cần được Spring tạo như thế nào**; nó không nên tự chạy nghiệp vụ, tự dựng toàn bộ ApplicationContext, hoặc coi `registerBeanDefinition` là một lệnh khởi tạo instance ngay lập tức.

Sau bài học, bạn có thể:

1. Hiểu vị trí của `ImportBeanDefinitionRegistrar` trong quy trình `@Configuration` + `@Import`.
2. Biết lúc nào chọn registrar thay cho `@Bean`, `@ComponentScan`, `ImportSelector` hoặc `BeanDefinitionRegistryPostProcessor`.
3. Triển khai hai overload `registerBeanDefinitions(...)` đúng mục đích.
4. Đọc giá trị annotation tùy chỉnh qua `AnnotationMetadata`.
5. Dựng `BeanDefinition` với `BeanDefinitionBuilder`; đăng ký bằng `BeanDefinitionRegistry.registerBeanDefinition`.
6. Kiểm soát bean names, xung đột, constructor arguments, role, scope, qualifier và dependency injection.
7. Chạy ví dụ Java 17/Spring Framework có custom `@EnableGreetings` tạo hai bean, được inject vào bean `@Bean` thông thường.
8. Kiểm thử sự khác biệt giữa **bean definition được đăng ký** và **instance do BeanFactory tạo**.
9. Nhận biết giới hạn lifecycle/early initialization, đặc biệt việc không đăng ký `BeanDefinitionRegistryPostProcessor` từ registrar.
10. Thiết kế registrar gọn, deterministic và có hành vi lỗi rõ ràng.

**Thông điệp trung tâm:** Registrar là **hạ tầng đăng ký metadata vào IoC container**, không phải một Service Locator hay factory nghiệp vụ. Hãy để Spring quản lý việc khởi tạo, dependency resolution và lifecycle sau khi definition được thêm.

## 2. BeanDefinition là gì? Registrar thay đổi phần nào?

Một Spring bean không nhất thiết xuất phát từ một lời gọi `new` trong code của bạn. Container xử lý **bean definitions**, trong đó có thể chứa:

- Tên hoặc tham chiếu tới bean class.
- Constructor arguments hoặc property values.
- Scope (`singleton`, `prototype` hoặc scope đã đăng ký).
- Lazy initialization flag.
- Qualifiers và lựa chọn autowire candidates.
- Init/destroy callbacks và metadata về nguồn gốc/role.
- Factory method hoặc supplier nếu sử dụng phương thức tạo nâng cao.

Ví dụ Java config thông thường:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    EmailClient emailClient() {
        return new EmailClient();
    }
}
```

Spring đọc `@Bean` và xây definition cho `emailClient`. Registrar đi vào **tầng thấp hơn**: bạn tự quyết định definition nào cần xuất hiện, với tên gì và metadata nào, mà không cần viết một phương thức `@Bean` cố định cho mỗi trường hợp.

Luồng khái niệm:

```text
@Configuration AppConfig
       |
       | có @Import(MyRegistrar.class)
       v
ConfigurationClassPostProcessor phân tích Java config
       |
       v
MyRegistrar.registerBeanDefinitions(...)
       |
       | AnnotationMetadata + BeanDefinitionRegistry
       v
Tạo BeanDefinition metadata
       |
       | registry.registerBeanDefinition(beanName, definition)
       v
BeanFactory có thêm definition
       |
       | resolve dependencies / scopes / lifecycle
       v
Bean instance được container tạo theo nhu cầu
```

**Điểm rất dễ nhầm:** `registerBeanDefinition("x", def)` **không đồng nghĩa** với `new X()` ngay tại thời điểm gọi. Việc tạo instance thường diễn ra sau đó, khi container pre-instantiate singleton không lazy hoặc khi ứng dụng thực sự yêu cầu bean theo scope/lifecycle.

Registrar được gọi **trong giai đoạn xử lý configuration**, nên cần tập trung vào quyết định metadata. Các thao tác như chạy migrations, gọi remote API, mở connection pool hay xử lý hóa đơn không thuộc trách nhiệm ở đây.

## 3. Interface và những API liên quan

Interface nằm trong:

```java
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
```

Hai phương thức được quan tâm:

```java
// Chữ ký minh họa, bỏ qua generic imports đầy đủ:
default void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry) {
}

default void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry,
        BeanNameGenerator importBeanNameGenerator) {
    registerBeanDefinitions(importingClassMetadata, registry);
}
```

Trong Spring 6.2, hai method là **default methods**; overload ba tham số mặc định **ủy quyền** cho overload hai tham số. Vì vậy, chỉ cần override phương thức hai tham số cho trường hợp thông thường.

### 3.1. AnnotationMetadata

`org.springframework.core.type.AnnotationMetadata` biểu diễn metadata của **class được import**, không phải instance của class đó. Bạn có thể đọc annotation hiện diện trực tiếp hoặc meta-present qua các API thích hợp.

Ví dụ:

```java
Map<String, Object> values =
        importingClassMetadata.getAnnotationAttributes(
                EnableGreetings.class.getName());
```

Ở đây `EnableGreetings` là custom annotation; ví dụ đầy đủ ở mục 7. Method trả `null` nếu không tìm thấy annotation theo chính sách truy vấn đó. Không cố cast `null` hoặc tin rằng mọi nơi import registrar đều mang annotation mong muốn.

**Ưu điểm:** Có thể ra quyết định đăng ký bean từ metadata mà không cần khởi tạo đối tượng configuration class, không chạy constructor hay business code của class ấy.

### 3.2. BeanDefinitionRegistry

`org.springframework.beans.factory.support.BeanDefinitionRegistry` là API để:

- `registerBeanDefinition(String, BeanDefinition)`: đăng ký definition với tên cụ thể.
- `containsBeanDefinition(String)`: xem registry đã có definition mang tên đó.
- `getBeanDefinition(String)`: xem definition đã đăng ký.
- `getBeanDefinitionNames()`: lấy các tên definitions hiện có.
- Một số thao tác registry khác trong những tình huống hạ tầng phù hợp.

API còn tham gia cơ chế alias; nếu dùng tên tạo động, kiểm tra cả khả năng tên trùng alias hoặc một definition khác trong cùng registry khi thiết kế collision policy.

Đừng coi registry giống `ApplicationContext` để gọi `getBean` và chạy use case. Nó chủ yếu thao tác metadata trong giai đoạn bootstrap.

### 3.3. BeanDefinitionBuilder

`org.springframework.beans.factory.support.BeanDefinitionBuilder` giúp tạo definition tương đối an toàn và dễ đọc:

```java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(GreetingHandler.class)
                .addConstructorArgValue("email")
                .getBeanDefinition();
registry.registerBeanDefinition("greeting.email", definition);
```

Đây là **đoạn minh họa** cần có `GreetingHandler`, `registry` và các imports tương ứng. Chúng ta không tự gọi `new GreetingHandler("email")`; Spring sẽ dùng definition để gọi constructor khi tạo bean.

Có thể chọn `RootBeanDefinition` trực tiếp cho trường hợp cần kiểm soát metadata sâu hơn:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(GreetingHandler.class);
definition.getConstructorArgumentValues()
        .addGenericArgumentValue("email");
registry.registerBeanDefinition("greeting.email", definition);
```

Hai ví dụ thể hiện hai cách tạo definition cho cùng ý tưởng; không đặt cả hai cạnh nhau trong cùng registrar để đăng ký trùng tên.

## 4. Registrar được kích hoạt bằng @Import

Một registrar cần được **Spring configuration processing biết đến**. Cách phổ biến nhất:

```java
@Configuration(proxyBeanMethods = false)
@Import(GreetingRegistrar.class)
public class AppConfig {
}
```

Spring phân tích `AppConfig`, thấy `@Import` trỏ tới class implement `ImportBeanDefinitionRegistrar` và gọi method đăng ký definitions. Đây không phải component scan và cũng không phải một lời gọi do developer phải thực thi thủ công.

### 4.1. Dùng trực tiếp @Import

```java
@Import(GreetingRegistrar.class)
class AppConfig {
}
```

Phù hợp để thử nghiệm hoặc khi việc import registrar là chi tiết hạ tầng mà cấu hình ứng dụng được phép nhìn thấy.

### 4.2. Tạo custom @Enable annotation

Một thư viện thường muốn API đẹp hơn:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(GreetingRegistrar.class)
public @interface EnableGreetings {
    String[] value();
}
```

Sau đó người dùng viết:

```java
@Configuration(proxyBeanMethods = false)
@EnableGreetings({"email", "sms"})
class AppConfig {
}
```

Spring nhận diện `@Import` nằm trên **meta-annotation `@EnableGreetings`**, gọi registrar và cho registrar đọc danh sách channels từ metadata của `AppConfig`. Không cần người dùng tự gọi BeanFactory hoặc viết N phương thức `@Bean`.

Cách ghép `@Enable...` này rất phù hợp cho một feature có cấu hình nhỏ nhưng cần đăng ký số lượng beans thay đổi theo annotation.

### 4.3. @Import không phải là khởi tạo registrar như một business bean

Framework tạo và sử dụng registrar trong luồng xử lý configuration. Bạn không nên giả định registrar là singleton service nghiệp vụ có cùng lifecycle với bean ứng dụng bình thường, hoặc đưa side effects vào constructor của nó.

Registrar cũng có thể được **ImportSelector trả về**; đây là trường hợp cấu hình nâng cao, nhưng điểm cốt lõi không đổi: Spring gọi registrar khi xử lý class configuration phù hợp.

## 5. Thứ tự xử lý: vì sao registrar không nên tự lấy bean ngay?

Một lộ trình điển hình khi `AnnotationConfigApplicationContext` refresh:

```text
register(AppConfig.class)
        |
        v
refresh()
        |
        v
ConfigurationClassPostProcessor
        |
        v
Phân tích @Configuration, @Import, @Bean, component metadata
        |
        v
Gọi ImportBeanDefinitionRegistrar
        |
        v
Registry có thêm bean definitions
        |
        v
BeanFactoryPostProcessor / BeanPostProcessor theo lifecycle
        |
        v
Pre-instantiate non-lazy singletons
        |
        v
Dependency injection, initialization và post-processing
        |
        v
Context sẵn sàng cho application code
```

Sơ đồ chỉ diễn tả **thứ tự khái niệm**, không phải mô tả toàn bộ thuật toán nội bộ. Những post-processors nhất định tham gia rất sớm; không nên dựa vào chi tiết thứ tự của mọi definition nếu không có hợp đồng API.

Ở thời điểm registrar được gọi:

- Nhiều bean definitions có thể đã tồn tại; nhiều beans vẫn **chưa được tạo**.
- Những quyết định như tên bean, constructor values, scope, candidate metadata nên được ghi vào definition.
- Việc resolve `@Autowired` hay gọi business method có thể chưa an toàn.
- Không cố lấy một bean để hỏi giá trị cấu hình nếu có thể đọc từ `AnnotationMetadata` hoặc `Environment`.
- Không tạo `AnnotationConfigApplicationContext` phụ từ registrar chỉ để instantiate đối tượng.

Đặc biệt, **Javadoc Spring cảnh báo** rằng không đăng ký các bean types thuộc `BeanDefinitionRegistryPostProcessor` thông qua `ImportBeanDefinitionRegistrar` do ràng buộc lifecycle của configuration class processing. Nếu cần một registry post-processor đúng nghĩa, hãy sử dụng điểm mở rộng/đường đăng ký tương ứng, không lách bằng một registrar đăng ký post-processor của chính nó.

## 6. Lúc nào nên chọn registrar?

| Nhu cầu | Công cụ ưu tiên cân nhắc | Lý do |
| --- | --- | --- |
| Một bean cố định, được dựng qua Java | `@Bean` | Rõ kiểu và dependency |
| Class ứng dụng có stereotype | `@Component`/`@Service` + component scan | Ít boilerplate |
| Chia Java configuration thành module | `@Import(Config.class)` | Composition trực tiếp |
| Chọn một/tập configuration classes có điều kiện | `ImportSelector` | Quyết định những classes nào được import |
| Tạo nhiều bean definitions phụ thuộc annotation metadata | `ImportBeanDefinitionRegistrar` | Đăng ký definitions linh hoạt |
| Thay đổi/duyệt definitions ở giai đoạn BeanFactory post-process | `BeanDefinitionRegistryPostProcessor`/`BeanFactoryPostProcessor` | Điểm mở rộng riêng, cần hiểu ordering/lifecycle |
| Chọn tên, scope, constructor arguments một cách programmatic trong context | `BeanDefinitionRegistry` hoặc `GenericApplicationContext.registerBean` | Đăng ký bằng API, không nhất thiết cần @Import |
| Nhập XML vào Java config | `@ImportResource` | Đọc bean definitions từ XML |
| Runtime chọn một strategy cụ thể | Registry/factory nghiệp vụ hoặc qualifier | Không phải lý do tự động dùng registrar |

**Registrar đáng dùng khi số lượng hoặc metadata bean phụ thuộc vào annotation/configuration** mà một số ít phương thức `@Bean` không mô tả gọn. Nó là extension point mức framework/infrastructure; tránh thêm nó chỉ vì muốn code “linh hoạt hơn” khi ứng dụng chỉ cần một bean đơn giản.

### Khi không nên dùng

Không nên dùng registrar chỉ để đăng ký:

```java
@Bean
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
```

nếu không có nhu cầu điều kiện/tên/metadata động. `@Bean` rõ ràng hơn, compile-time type references dễ thấy, ít phụ thuộc framework internals và ít rủi ro registration conflict.

Không dùng registrar làm nơi gửi email, migrate dữ liệu hoặc tạo network connection khi Spring đang xử lý configuration definitions.

## 7. Dự án runnable Java 17: custom @EnableGreetings đăng ký hai bean

Ví dụ chạy với **JDK 17 + Spring Framework 6.2.x**, không cần Spring Boot. Mục tiêu là nhìn thấy từ đầu đến cuối:

1. `@EnableGreetings({"email", "sms"})` chứa cấu hình feature.
2. `@Import(GreetingRegistrar.class)` meta-present giúp Spring gọi registrar.
3. Registrar đọc `AnnotationMetadata` và đăng ký hai bean definitions với tên `greeting.email`, `greeting.sms`.
4. `@Bean GreetingDashboard` được Spring tiêm `GreetingHandler` với `@Qualifier("greeting.email")`; điều đó chứng minh definition do registrar tạo tham gia dependency resolution bình thường.
5. `getBeanNamesForType` và `getBeanDefinition` xác minh đúng definitions, names và roles.
6. Không component scan và không `@Bean` cho từng `GreetingHandler`; việc tạo chúng hoàn toàn do registrar đăng ký metadata.

### 7.1. Cấu trúc thư mục

```text
registrar-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        └── RegistrarDemo.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>registrar-demo</artifactId>
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

### 7.3. Toàn bộ file RegistrarDemo.java

Tạo `src/main/java/demo/RegistrarDemo.java`:

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class RegistrarDemo {

    // Service object được quản lý bởi Spring sau khi registrar
    // đăng ký BeanDefinition tương ứng.
    public static final class GreetingHandler {
        private final String channel;

        public GreetingHandler(String channel) {
            this.channel = channel;
        }

        public String greet(String name) {
            return channel + ":Hello, " + name;
        }
    }

    public static final class GreetingDashboard {
        private final GreetingHandler email;

        public GreetingDashboard(GreetingHandler email) {
            this.email = email;
        }

        public String headline(String name) {
            return "dashboard=" + email.greet(name);
        }
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Import(GreetingRegistrar.class)
    public @interface EnableGreetings {
        String[] value();
    }

    public static final class GreetingRegistrar
            implements ImportBeanDefinitionRegistrar {

        @Override
        public void registerBeanDefinitions(
                AnnotationMetadata importingClassMetadata,
                BeanDefinitionRegistry registry) {

            Map<String, Object> attributes =
                    importingClassMetadata.getAnnotationAttributes(
                            EnableGreetings.class.getName());

            if (attributes == null) {
                throw new IllegalStateException(
                        "@EnableGreetings is required");
            }

            String[] channels = (String[]) attributes.get("value");
            Set<String> seen = new HashSet<>();

            for (String channel : channels) {
                if (channel == null ||
                        !channel.matches("[a-z][a-z0-9-]*")) {
                    throw new IllegalArgumentException(
                            "Invalid channel: " + channel);
                }

                if (!seen.add(channel)) {
                    throw new IllegalArgumentException(
                            "Duplicate channel: " + channel);
                }

                String beanName = "greeting." + channel;
                if (registry.containsBeanDefinition(beanName) ||
                        registry.isAlias(beanName)) {
                    throw new IllegalStateException(
                            "Bean name already used: " + beanName);
                }

                BeanDefinition definition = BeanDefinitionBuilder
                        .genericBeanDefinition(GreetingHandler.class)
                        .addConstructorArgValue(channel)
                        .getBeanDefinition();

                definition.setRole(BeanDefinition.ROLE_APPLICATION);
                registry.registerBeanDefinition(beanName, definition);
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableGreetings({"email", "sms"})
    public static class AppConfig {

        @Bean
        public GreetingDashboard greetingDashboard(
                @Qualifier("greeting.email") GreetingHandler email) {
            return new GreetingDashboard(email);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            String[] beanNames =
                    context.getBeanNamesForType(GreetingHandler.class);
            Arrays.sort(beanNames);

            System.out.println("handlers=" + Arrays.toString(beanNames));
            System.out.println("email=" +
                    context.getBean("greeting.email",
                                    GreetingHandler.class).greet("Lan"));
            System.out.println("sms=" +
                    context.getBean("greeting.sms",
                                    GreetingHandler.class).greet("Lan"));
            System.out.println(
                    context.getBean(GreetingDashboard.class).headline("Mai"));
            System.out.println("roleIsApplication=" +
                    (context.getBeanDefinition("greeting.email").getRole()
                            == BeanDefinition.ROLE_APPLICATION));
        }
    }
}
```

### 7.4. Chạy chương trình

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RegistrarDemo
```

Output **do chương trình in ra** (không tính logging của Maven/Spring nếu môi trường có cấu hình khác):

```text
handlers=[greeting.email, greeting.sms]
email=email:Hello, Lan
sms=sms:Hello, Lan
dashboard=email:Hello, Mai
roleIsApplication=true
```

### 7.5. Vì sao output như trên?

**`handlers=[greeting.email, greeting.sms]`:** Registrar đăng ký hai bean definitions có class `GreetingHandler`. Spring đã tạo/đã có thể phân giải chúng theo type. `getBeanNamesForType(GreetingHandler.class)` trả về tên chính của các bean ứng viên theo type, còn `Arrays.sort` bảo đảm thứ tự hiển thị độc lập thứ tự nội bộ của registry.

**`email=email:Hello, Lan`** và **`sms=sms:Hello, Lan`:** Mỗi `BeanDefinition` có constructor argument là chuỗi channel tương ứng. BeanFactory gọi `GreetingHandler(String)` để tạo instance khi cần, không phải registrar tạo sẵn object. Cả hai beans có class giống nhau nhưng constructor state khác nhau.

**`dashboard=email:Hello, Mai`:** `GreetingDashboard` được tạo bởi Java `@Bean`. Tham số `@Qualifier("greeting.email") GreetingHandler` được Spring resolve tới bean registrar đã đăng ký. Vì vậy một bean Java config bình thường có thể phụ thuộc vào bean được đăng ký programmatically.

**`roleIsApplication=true`:** Registrar đặt `BeanDefinition.ROLE_APPLICATION` cho definition `greeting.email`; truy vấn lại metadata xác nhận giá trị này. Role chủ yếu là hint phân loại cho các công cụ/container, **không** phải quy tắc bắt buộc về singleton, injection hoặc mức độ ưu tiên của bean.

### 7.6. Tại sao dùng public static nested classes?

Mọi class trong ví dụ nằm trong một Java file để tiện sao chép. `GreetingHandler`, `GreetingDashboard` và `GreetingRegistrar` đều là **public static nested classes**, nên không cần một instance `RegistrarDemo` bên ngoài khi được Spring tạo.

`GreetingHandler` có public constructor nhận `String channel`; `BeanDefinitionBuilder.addConstructorArgValue(channel)` cung cấp đúng giá trị cho constructor đó. Nếu đổi thành non-static inner class, Spring còn cần một outer instance và mẫu bean definition sẽ không còn đơn giản như ví dụ.

### 7.7. Vì sao không cần Spring Boot?

`AnnotationConfigApplicationContext`, `@Import`, `ImportBeanDefinitionRegistrar`, `BeanDefinitionRegistry` và `BeanDefinitionBuilder` đều là API của Spring Framework. Dependency `spring-context` kéo theo các module core/beans cần thiết, nên ví dụ này chạy như một console application thông thường.

Nếu sau này đặt một custom `@EnableGreetings` trong Spring Boot application, cơ chế registrar vẫn thuộc nền tảng Spring Framework; Boot không phải điều kiện bắt buộc để registrars hoạt động.

## 8. Đọc AnnotationMetadata đúng và an toàn

Registrar thường được nhập qua một composed annotation có attributes như:

```java
@EnableGreetings({"email", "sms"})
class AppConfig {
}
```

Trong registrar:

```java
Map<String, Object> attributes =
        importingClassMetadata.getAnnotationAttributes(
                EnableGreetings.class.getName());

if (attributes == null) {
    throw new IllegalStateException("Missing @EnableGreetings");
}
String[] channels = (String[]) attributes.get("value");
```

Đây là mã trích từ ví dụ đầy đủ. `importingClassMetadata` đại diện cho class cấu hình đã khai báo annotation. Với `@EnableGreetings` trong ví dụ, `value` khai báo là `String[]`, nên có thể cast sang `String[]`.

### Sai lầm: đọc metadata của registrar thay vì class import

`GreetingRegistrar.class.getAnnotation(EnableGreetings.class)` sẽ không cho bạn danh sách channels trong `AppConfig`, vì annotation `@EnableGreetings` nằm trên **AppConfig**, không nằm trên registrar. Spring trao cho registrar metadata của **importing configuration class** chính để giải quyết vấn đề này.

### Khi annotation được meta-annotated thêm nhiều tầng

Nếu custom annotation kết hợp thêm các meta-annotations hoặc alias, hãy dùng các API annotation metadata/merged annotations của Spring đúng mục đích thay vì chỉ duyệt Java reflection trực tiếp. Mục tiêu là đọc metadata cấu hình **không cần instantiate class cấu hình**.

### Validation trước khi đăng ký

Các giá trị từ annotation có thể dẫn đến bean names, class names, constructor args hoặc số lượng definitions. Nên kiểm tra:

- Giá trị rỗng/null/không hợp lệ.
- Giá trị lặp hoặc trùng tên sau khi chuẩn hóa.
- Quy tắc bean naming và những ký tự bị cấm bởi **hợp đồng ứng dụng**.
- Số lượng bean sẽ tạo, tránh vô tình hàng nghìn definitions từ một danh sách quá lớn.
- Các điều kiện feature flags có deterministic và đủ thông tin ở giai đoạn bootstrap không.

Ví dụ `channel.matches("[a-z][a-z0-9-]*")` là **quy ước riêng của demo**, không phải giới hạn tên bean toàn cục do Spring áp đặt.

## 9. BeanDefinitionBuilder và metadata của definition

Một builder có thể thiết lập nhiều thuộc tính:

```java
BeanDefinitionBuilder builder =
        BeanDefinitionBuilder.genericBeanDefinition(Worker.class)
                .addConstructorArgValue("batch")
                .setScope("prototype")
                .setLazyInit(true);

BeanDefinition definition = builder.getBeanDefinition();
definition.setRole(BeanDefinition.ROLE_SUPPORT);
registry.registerBeanDefinition("worker.batch", definition);
```

Đây là **đoạn minh họa** cần class `Worker` có constructor thích hợp. Có thể dùng `BeanDefinition.SCOPE_PROTOTYPE` hay `ConfigurableBeanFactory.SCOPE_PROTOTYPE` khi muốn tránh chuỗi scope. Cần cân nhắc:

- `setScope("prototype")`: bean factory tạo instance mới theo mỗi lượt phân giải prototype.
- `setLazyInit(true)`: có ý nghĩa đặc biệt với singleton; prototype vốn thường được tạo khi được yêu cầu.
- `ROLE_SUPPORT`: hint vai trò, không phải component scanning annotation.
- `addConstructorArgValue(...)`: lưu giá trị constructor để Spring giải quyết khi tạo instance.

### 9.1. Đừng nhầm BeanDefinition với bean instance

Có definition:

```java
registry.registerBeanDefinition("worker.batch", definition);
```

không có nghĩa `new Worker("batch")` đã chạy. Trong singleton non-lazy bình thường, container có thể instantiate ở giai đoạn refresh; trong prototype, instance xuất hiện khi được yêu cầu.

Nếu bạn truyền object thật vào builder qua `addConstructorArgValue`, object đó là argument value; không phải container tự biến object ấy thành một bean có lifecycle độc lập.

### 9.2. Property values

Nếu class đích có setter phù hợp:

```java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ExampleClient.class)
                .addPropertyValue("endpoint", "http://localhost")
                .getBeanDefinition();
registry.registerBeanDefinition("exampleClient", definition);
```

Đây là minh họa; `ExampleClient` cần method `setEndpoint(String)`. `addPropertyValue` tạo metadata cho property injection; bean vẫn được Spring tạo về sau.

### 9.3. Dependency tới bean khác

Để tham chiếu một bean có tên đã biết, có thể dùng `RuntimeBeanReference`:

```java
import org.springframework.beans.factory.config.RuntimeBeanReference;

BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(ReportService.class)
        .addConstructorArgValue(
                new RuntimeBeanReference("reportRepository"))
        .getBeanDefinition();

registry.registerBeanDefinition("reportService", definition);
```

Đây là minh họa cần `ReportService(ReportRepository)` và bean `reportRepository` tồn tại. `RuntimeBeanReference` không phải chuỗi tên được truyền làm giá trị constructor; nó là metadata để Spring phân giải **bean reference** vào lúc tạo bean.

Nếu phụ thuộc có thể được biểu diễn bằng constructor autowiring thông thường, bạn cũng có thể để Spring tự giải quyết theo kiểu, nhưng hãy kiểm tra API, mode và metadata phù hợp. Đừng tự gọi `BeanFactory.getBean` từ registrar để đưa object vào definition sớm.

### 9.4. Role và autowire-candidate

`BeanDefinition.ROLE_APPLICATION`, `ROLE_SUPPORT` và `ROLE_INFRASTRUCTURE` là các hints cho vai trò bean. Chúng không tự cho biết bean có được autowire hay không; autowire eligibility chịu các metadata và quy tắc dependency khác.

Nếu registrar tạo helper bean không được phép trở thành ứng viên injection thông thường, có thể cân nhắc `definition.setAutowireCandidate(false)`. Khi đó phải bảo đảm không làm hỏng dependency thật sự cần bean helper. Không đánh dấu `ROLE_INFRASTRUCTURE` rồi nghĩ Spring tự tắt autowiring.

## 10. Hai overload của registerBeanDefinitions

### 10.1. Overload hai tham số

```java
@Override
public void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry) {
    // Đọc metadata rồi đăng ký bean definitions.
}
```

Đây là lựa chọn đơn giản nhất và là cách ví dụ chạy đầy đủ sử dụng. Nó phù hợp khi bạn **tự đặt tên rõ ràng** như `greeting.email`, không cần được truyền BeanNameGenerator của framework.

### 10.2. Overload ba tham số

```java
@Override
public void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry,
        BeanNameGenerator importBeanNameGenerator) {
    // Có thể dùng chiến lược đặt tên dành cho imported beans.
}
```

Tham số `importBeanNameGenerator` được cung cấp để registrar có thể tôn trọng naming strategy khi tạo các definitions theo cấu trúc framework. Nếu override overload ba tham số, Spring sẽ gọi trực tiếp implementation này; không phải tự gọi overload hai tham số trừ khi bạn muốn.

**Lưu ý:** Tên dành cho imported beans có default và có thể được tùy chỉnh bởi cấu hình `ConfigurationClassPostProcessor`. Không tự khẳng định rằng mọi registrar phải dùng `AnnotationBeanNameGenerator` cho mọi bean hoặc BeanNameGenerator sẽ tự chọn tên nếu bạn đã chủ động xây tên nghiệp vụ như `greeting.email`.

### Tránh override rỗng hoặc nhầm overload

Vì cả hai phương thức là default trong Spring Framework 6.2, bạn cần **override ít nhất một phương thức có ý nghĩa**. Nếu triển khai interface nhưng không override bất kỳ method nào, registrar sẽ không tạo definition nào — điều đó có thể biên dịch mà làm người dùng tưởng tính năng đã bật.

Đừng viết code trong overload hai tham số rồi override thêm overload ba tham số rỗng: phương thức ba tham số của bạn có thể chặn default delegation và khiến logic đăng ký không được chạy.

## 11. Đảm bảo bean names không va chạm

Registrar tạo tên programmatically nên phải xác định **collision policy** trước khi đăng ký.

Mẫu bảo thủ:

```java
String name = "greeting." + channel;

if (registry.containsBeanDefinition(name) || registry.isAlias(name)) {
    throw new IllegalStateException(
            "Bean name already used: " + name);
}

registry.registerBeanDefinition(name, definition);
```

**Phạm vi kiểm tra:** `containsBeanDefinition` xem definition đã hiện diện trong registry **tại thời điểm đó**. Một bean name khác có thể được đăng ký ở giai đoạn sau; vì vậy collision policy của registrar cần phối hợp với chính sách overriding của container và integration tests. Kiểm tra trước không phải bảo đảm chống mọi xung đột tương lai.

### Tự override bean definition có sẵn?

Một số BeanFactories có thể cho phép overriding. Nhưng registry-level customization không nên dựa vào “đăng ký cuối cùng sẽ thắng”, vì thứ tự và chính sách override có thể khác giữa môi trường/Boot config và phiên bản.

Nếu muốn extension point có khả năng người dùng override:

- Định nghĩa bean name cố định hoặc contract rõ ràng.
- Tài liệu hóa lúc nào registrar bỏ qua một definition đã tồn tại, lúc nào phải báo lỗi.
- Đảm bảo hành vi deterministic dưới các cách import config khác nhau.
- Integration test với trường hợp người dùng có custom bean cùng tên.
- Không âm thầm thay bean business-critical bằng implementation khác mà không có cảnh báo.

**Ví dụ đang dùng chính sách fail fast** khi có definition/alias trùng tên. Đây là lựa chọn có chủ đích của thư viện demo, không phải quy tắc bắt buộc cho mọi registrar.

## 12. Nhiều configuration classes cùng import registrar

Giả sử nhiều class cùng mang `@EnableGreetings` hoặc cùng import registrar qua nhiều tuyến:

```java
@Configuration
@EnableGreetings({"email"})
class EmailConfig {
}

@Configuration
@EnableGreetings({"sms"})
class SmsConfig {
}
```

Tình huống này cần **test cụ thể** về cách Spring xử lý imports, deduplication và metadata trong application context sử dụng thực tế. Không thiết kế thư viện dựa trên giả định “registrar chắc chắn được gọi đúng một lần cho toàn bộ JVM”.

Nếu registrar có thể được gọi nhiều lần:

- Đừng dùng static mutable counter để quyết định bean names.
- Xác định cùng bean name với cùng config được coi là idempotent hay lỗi.
- Khi mỗi importing class có thuộc tính khác nhau, logic nên xử lý từng tập metadata theo cơ chế framework hoặc chọn một cấu hình tổng hợp rõ ràng.
- Nếu hai nguồn đăng ký cùng tên, phải có collision policy nhất quán.
- Không dựa vào thứ tự import làm business priority.

Trong ví dụ đầy đủ chỉ có **một `AppConfig`** mang `@EnableGreetings({"email","sms"})`. Điều đó giúp output dễ kiểm chứng và tránh giả định chưa được kiểm thử về nhiều import chains.

## 13. Aware interfaces, constructor injection và Environment

Registrar có thể cần cấu hình môi trường hoặc resource loader **ở thời điểm xử lý definition**. Javadoc Spring cho phép registrar implement một số `Aware` interfaces:

- `EnvironmentAware`.
- `BeanFactoryAware`.
- `BeanClassLoaderAware`.
- `ResourceLoaderAware`.

Spring gọi các callback phù hợp **trước khi** chạy `registerBeanDefinitions(...)`. Ngoài ra, registrar có thể có **một constructor** với một hoặc nhiều tham số thuộc các kiểu được hỗ trợ:

- `Environment`.
- `BeanFactory`.
- `ClassLoader`.
- `ResourceLoader`.

### Ví dụ đọc Environment

```java
// Đoạn minh họa bên trong registrar, không phải project độc lập.
final class FeatureRegistrar
        implements ImportBeanDefinitionRegistrar, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {
        boolean enabled = environment.getProperty(
                "features.reporting.enabled", Boolean.class, false);
        if (!enabled) {
            return;
        }

        BeanDefinition definition = BeanDefinitionBuilder
                .genericBeanDefinition(ReportAdapter.class)
                .getBeanDefinition();
        registry.registerBeanDefinition("reportAdapter", definition);
    }
}
```

Đây là ví dụ yêu cầu `ReportAdapter` và imports liên quan. Đọc `Environment` tại giai đoạn configuration có thể hợp lý nếu kết quả **ổn định cho lần khởi tạo context** và không đòi tạo các bean nghiệp vụ trước.

### Không dùng BeanFactoryAware để chạy business logic

Việc registrar được trao `BeanFactory` không có nghĩa mọi bean đã khởi tạo. Tránh gọi `getBean` từ registrar để mở kết nối, chạy migration hoặc kích hoạt workflow. Nếu thực sự cần trao dependency cho bean tạo về sau, sử dụng constructor arguments, references, qualifiers hoặc BeanFactory resolution sau này.

### ClassLoader và ResourceLoader

Có thể dùng khi bạn cần đọc metadata/resource phục vụ quyết định đăng ký. Cần thận trọng với class loading động và AOT/native image. Nếu danh sách class đến từ nguồn không tin cậy, validate allowlist và đừng cho phép registration class tùy ý chỉ từ cấu hình người dùng.

## 14. So sánh ImportBeanDefinitionRegistrar với BeanDefinitionRegistryPostProcessor

Tên hai extension points rất giống nhau, nhưng chúng xuất hiện ở **ngữ cảnh và thời điểm khác**.

| Tiêu chí | `ImportBeanDefinitionRegistrar` | `BeanDefinitionRegistryPostProcessor` |
| --- | --- | --- |
| Cách tham gia điển hình | `@Import(Registrar.class)` hoặc `ImportSelector` | Bean post-processor mức BeanFactory/registry |
| Input quan trọng | `AnnotationMetadata` của importing class + registry | `BeanDefinitionRegistry` trong callback post-processing |
| Trọng tâm | Thêm definitions dựa trên imported configuration metadata | Kiểm tra/điều chỉnh/đăng ký definitions ở post-process phase |
| Nhu cầu @Enable annotation | Rất phù hợp | Không phải giao diện chính cho composed @Enable |
| Có thể thêm bean definitions | Có | Có, theo lifecycle tương ứng |
| Được đăng ký bằng registrar làm post-processor mới | **Không nên/không được theo Javadoc** | Phải đưa vào đúng đường lifecycle, không vòng qua registrar |

Quan trọng nhất: Javadoc của `ImportBeanDefinitionRegistrar` ghi rõ **`BeanDefinitionRegistryPostProcessor` types may not be registered here**, do lifecycle constraints khi Spring xử lý `@Configuration` classes. Đừng phớt lờ cảnh báo này hoặc dùng đăng ký trực tiếp qua registrar để thay một post-processor hạ tầng đặc biệt.

Nếu bạn cần mutate các definitions đã được nhiều nguồn đăng ký hoặc chạy theo ordering của post-processors, hãy tìm hiểu riêng `BeanDefinitionRegistryPostProcessor`. Nếu mục tiêu là thực thi API `@EnableFeature` dựa trên annotation attributes để thêm beans, registrar thường là lựa chọn trực diện hơn.

## 15. Quan hệ với @ImportSelector và DeferredImportSelector

`@Import` có thể xử lý:

- Class `@Configuration` bình thường.
- Class component phù hợp.
- Class implement `ImportSelector`.
- Class implement `ImportBeanDefinitionRegistrar`.

`ImportSelector` trả về **tên class** được import, ví dụ các configuration classes tùy điều kiện. Nó không trực tiếp gọi `registry.registerBeanDefinition(...)` trong interface chính. Registrar thì **tự tạo bean definitions** dựa trên metadata.

Ví dụ ý tưởng:

```java
// Minh họa API, không phải ví dụ runnable.
public class MySelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[]{SpecificConfig.class.getName()};
    }
}
```

`DeferredImportSelector` còn có thời điểm xử lý/trình tự khác, thường hữu ích cho tập cấu hình chọn sau một số bước phân tích configuration; trong Spring Boot, nhiều cơ chế auto-configuration có tổ chức phức tạp hơn sử dụng các extension points tương ứng.

Đừng hoán đổi selector và registrar một cách cơ học. Chọn theo **loại đầu ra cần tạo**:

- Chọn configuration classes: selector.
- Đăng ký definitions tùy metadata: registrar.
- Khai báo 1–2 beans cố định: `@Bean` thường đủ.

Một `ImportSelector` cũng có thể trả tên registrar class để Spring tiếp tục xử lý theo pipeline import. Đó là trường hợp thư viện thực sự cần chọn registrar theo điều kiện.

## 16. Thực hành với scopes và lazy beans

Registrar có thể tạo nhiều definitions với scopes khác nhau. Nhưng đó chỉ là metadata, không phải hành vi của Java constructor.

### Singleton (mặc định)

```java
BeanDefinition def =
        BeanDefinitionBuilder.genericBeanDefinition(Worker.class)
                .getBeanDefinition();
registry.registerBeanDefinition("worker", def);
```

Nếu không đổi scope, default là singleton. Trong một ApplicationContext, `context.getBean("worker")` nhiều lần thường trả cùng object.

### Prototype

```java
BeanDefinition def = BeanDefinitionBuilder
        .genericBeanDefinition(Worker.class)
        .setScope("prototype")
        .getBeanDefinition();
registry.registerBeanDefinition("worker", def);
```

BeanFactory có thể tạo instance mới mỗi lần nó phân giải prototype. Nếu singleton inject prototype một lần vào constructor, singleton thường giữ instance đó; muốn lấy prototype mỗi job, dùng `ObjectProvider<Worker>` hoặc factory chuyên dụng.

### Lazy singleton

```java
BeanDefinition def = BeanDefinitionBuilder
        .genericBeanDefinition(Worker.class)
        .setLazyInit(true)
        .getBeanDefinition();
registry.registerBeanDefinition("worker", def);
```

Lazy singleton có thể chưa được tạo trong pre-instantiation phase; nhưng một dependency eager khác có thể yêu cầu nó sớm. Đừng nhầm `setLazyInit(true)` với “definition sẽ chưa tồn tại trong registry”: definition có sẵn; **instance** mới có thể bị trì hoãn.

**Lưu ý:** `BeanDefinitionBuilder` thay đổi metadata. Đừng gọi `new Worker()` trong registrar rồi tự giữ object trong static map; điều đó bỏ qua IoC semantics mong muốn.

## 17. Tên bean, qualifiers và số lượng ứng viên

Giả sử registrar đăng ký hai bean cùng class:

```text
greeting.email -> GreetingHandler("email")
greeting.sms   -> GreetingHandler("sms")
```

Một injection point:

```java
GreetingDashboard(GreetingHandler handler) {
    this.handler = handler;
}
```

có thể nhập nhằng nếu Spring không có ứng viên thắng theo quy tắc lựa chọn. Nhưng:

```java
GreetingDashboard(
        @Qualifier("greeting.email") GreetingHandler handler) {
    this.handler = handler;
}
```

yêu cầu bean cụ thể. Trong dự án ví dụ, qualifier được đặt ngay trên tham số `@Bean` method để minh họa cách chọn.

Nếu mục tiêu là sử dụng **tất cả** handlers, một bean khác có thể nhận `List<GreetingHandler>` hoặc `Map<String, GreetingHandler>` qua dependency injection. Khi cần thứ tự, cấu hình metadata `@Order`/`Ordered` hoặc policy tương đương và kiểm thử. Không mong registrar “đăng ký trước” nghĩa là thứ tự nghiệp vụ chắc chắn được bảo toàn.

### Bean role không giải quyết ambiguity

`definition.setRole(BeanDefinition.ROLE_INFRASTRUCTURE)` chỉ đánh dấu vai trò infrastructure. Nó không tự đánh dấu primary hoặc tạo qualifier. Muốn chọn ứng viên đơn lẻ, phải dùng metadata/logic selection phù hợp như `@Primary`, qualifier, autowire candidate flag hoặc interface cụ thể.

### Aliases không phải definitions mới

BeanDefinitionRegistry/BeanFactory hỗ trợ tên và aliases theo hợp đồng. Nếu cần tương thích tên cũ, có thể đăng ký alias phù hợp, nhưng **alias không tăng số lượng bean definitions**. Nhiều tên cho một bean khác với hai definitions có cùng class.

## 18. Kiểm thử registrar có hiệu lực thật sự

Một lỗi dễ mắc là chỉ test:

```java
new GreetingRegistrar();
```

Lệnh này không có `AnnotationMetadata` thực tế, không có `BeanDefinitionRegistry` của context và không chạy Spring configuration processing. Nó không chứng minh `@EnableGreetings` có hiệu lực.

### Test mức context

Trong chương trình `RegistrarDemo`, có thể thêm:

```java
// Đoạn bổ sung bên trong try có context.
if (!context.containsBeanDefinition("greeting.email")) {
    throw new AssertionError("Registrar did not register email");
}
if (!context.containsBeanDefinition("greeting.sms")) {
    throw new AssertionError("Registrar did not register sms");
}
if (context.getBeanNamesForType(GreetingHandler.class).length != 2) {
    throw new AssertionError("Unexpected GreetingHandler bean count");
}
if (!"email:Hello, Lan".equals(
        context.getBean("greeting.email", GreetingHandler.class).greet("Lan"))) {
    throw new AssertionError("Wrong constructor argument");
}
```

Các assertions không in thêm stdout khi đúng. Chúng kiểm tra các tầng:

1. Registrar thực sự được Spring gọi thông qua `@Import`.
2. Bean definitions được ghi vào registry.
3. BeanFactory tạo đúng instances theo type.
4. Constructor argument của từng bean được dùng như mong muốn.

### Test trường hợp xấu

Nên thêm các kịch bản riêng:

| Cấu hình | Kết quả nên kiểm tra |
| --- | --- |
| `@EnableGreetings({"email","sms"})` | Hai definitions và inject theo qualifier được |
| `@EnableGreetings({"email","email"})` | Fail fast, báo duplicate channel theo chính sách demo |
| `@EnableGreetings({"Email"})` | Fail fast theo regex lowercase của demo |
| Bean name `greeting.email` đã tồn tại trước khi registrar chạy | Không âm thầm override; kiểm tra lỗi hoặc policy đã thiết kế |
| Không import registrar và không khai báo handler | Không có bean handler |
| Chỉ import registrar trực tiếp nhưng không có `@EnableGreetings` | Báo lỗi rõ vì thiếu metadata |
| Bean class có constructor không tương thích arguments | Bean creation thất bại đúng gốc lỗi |
| Singleton vs prototype | Identity và lifecycle theo scope |
| Nhiều import chains | Số definitions và collision/idempotency đúng hợp đồng |

Trong integration test, dùng `AnnotationConfigApplicationContext` với những configuration classes được thiết kế riêng cho case cần test. Đừng sửa BeanFactory của một context đang phục vụ request để mô phỏng bootstrap nếu bài test chỉ cần xây một context mới.

### Test registrar ở cấp thấp

Có thể kiểm tra logic đăng ký metadata với registry giả/`DefaultListableBeanFactory`, nhưng vì custom annotations và `@Import` được Spring xử lý ở mức configuration class, **integration test với context thật** là cách tốt nhất để xác minh dây chuyền đầy đủ.

## 19. Cảnh báo về AOT, native image và động hóa quá mức

Khi dùng Spring AOT/native image, hành vi đăng ký bean definitions phải phù hợp với cách Spring phân tích cấu hình ở build-time và runtime. Việc quyết định bean class hoặc cấu trúc bean dựa trên dữ liệu runtime không được biết lúc build có thể đòi hỏi thiết kế AOT/hints/tùy chỉnh thích hợp.

Một registrar deterministic dựa trên constant annotation attributes như `@EnableGreetings({"email","sms"})` thường đơn giản hơn để phân tích so với việc:

- Tải class name từ mạng khi ứng dụng khởi động.
- Scan ngẫu nhiên mọi package theo dữ liệu bên ngoài.
- Thay đổi danh sách beans theo một kết quả API call runtime không kiểm soát.
- Sinh tên bean không ổn định từ thời gian hoặc random.
- Phụ thuộc dynamic proxy/reflection mà không cung cấp hints cần thiết cho native image.

**Đừng coi `ImportBeanDefinitionRegistrar` tự động bảo đảm tính tương thích native.** Nếu mục tiêu bao gồm Spring AOT, cần kiểm thử build/runtime tương ứng và xem tài liệu AOT của framework đúng phiên bản.

## 20. Hiệu năng và bảo mật khi registrar thêm nhiều definitions

Một registrar chạy sớm. Dù nó chỉ đăng ký metadata, việc tạo số lượng lớn beans ở refresh có thể ảnh hưởng bộ nhớ, startup và dependency graph.

Nên:

- Giữ thao tác trong registrar **nhanh và deterministic**.
- Giới hạn số lượng definitions theo yêu cầu rõ ràng.
- Không tải external data hoặc mạng từ registrar để quyết định dynamic beans, trừ khi đã có một hợp đồng bootstrap rất đặc biệt và được kiểm soát.
- Dùng tên có namespace/prefix rõ, ví dụ `greeting.email` thay vì `handler` quá chung.
- Validate annotation attributes, class names, resource paths và bean naming trước khi ghi registry.
- Không cho phép giá trị không tin cậy quyết định class tùy ý được instantiate nếu không có allowlist/kiểm soát.
- Tách logic cấu hình khỏi business side effects và kiểm tra lifecycle.
- Khi tạo beans chứa secrets/resources, để BeanFactory quản lý constructor injection và cleanup; không đẩy dữ liệu nhạy cảm vào bean names hoặc logs.

Có thể log số definitions được đăng ký ở mức phù hợp trong dev/test, nhưng tránh log toàn bộ configuration values nhạy cảm.

## 21. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Registrar không được gọi | Class cấu hình mang `@Import`/`@Enable...` chưa được Spring đăng ký | Kiểm tra root `@Configuration`, `@Import` và bootstrap context |
| Registrar được gọi nhưng không có bean | Override sai overload/rỗng; metadata null; không thực hiện `registerBeanDefinition` | Debug đúng interface method và registry |
| `getAnnotationAttributes(...)` trả null | Annotation nằm trên class khác, import trực tiếp registrar, hoặc tên annotation sai | Dùng metadata của importing class, validate và báo lỗi |
| `NoSuchBeanDefinitionException` | Bean name/type chưa đăng ký hoặc injection cần bean khác | Kiểm tra `containsBeanDefinition`, names, exposed types và qualifiers |
| `NoUniqueBeanDefinitionException` | Registrar tạo nhiều beans cùng type, injection yêu cầu một | Dùng qualifier/primary/collection đúng ý định |
| `BeanCreationException` / constructor mismatch | Constructor args không khớp bean class hoặc dependency thiếu | Sửa `BeanDefinitionBuilder` arguments và constructor |
| Bean name collision | Multiple registrars/configs tạo cùng tên | Fail fast hoặc policy override có tài liệu/test rõ |
| Registrar chạy lặp gây lỗi | Duplicate imports hoặc nhiều feature annotation khác nhau | Xác định idempotency/deduplication và kiểm thử import chains |
| Bean chưa khởi tạo khi registrar gọi | Registrar hoạt động ở definition phase | Không gọi business bean từ registrar; dùng lifecycle phù hợp |
| Bean role infrastructure nhưng vẫn autowire | Role không điều khiển candidate selection | Dùng autowire candidate/qualifier đúng cơ chế |
| `@Bean` Java không thấy handler | Registrar không được imported vào context hoặc tên qualifier sai | Tạo integration test với cấu hình thật |
| Trùng bean definition mặc dù đã check | Definition khác được đăng ký sau pre-check | Phối hợp với override policy và kiểm thử |
| Native image thiếu bean hoặc reflection metadata | Registration không phù hợp AOT/runtime metadata | Đánh giá AOT hints, deterministic registration và native tests |
| Register `BeanDefinitionRegistryPostProcessor` từ registrar bị lỗi lifecycle | Sai extension point | Dùng cơ chế đăng ký post-processor đúng vòng đời |
| Test pass chỉ khi component scan rộng | Registrar bị bỏ quên; scanner tình cờ tạo bean thay thế | Thu hẹp test context, xác minh bean definition source và names |

### Trình tự debug thực dụng

1. Xác nhận configuration class có trong `ApplicationContext`.
2. Xác nhận `@Import(Registrar.class)` tồn tại trực tiếp hoặc meta-present trên custom enable annotation.
3. Xác nhận đúng overload `registerBeanDefinitions(...)` được override và thực thi.
4. Kiểm tra `AnnotationMetadata` cho annotation keys/values dự kiến.
5. Kiểm tra tên định tạo, collision và điều kiện bỏ qua/fail fast.
6. Xem `BeanDefinition` có đúng class, scope, constructor args và role không.
7. Phân biệt **definition có** với **instance đã tạo**.
8. Test `getBean(...)` và injection theo type/qualifier trong context thật.
9. Đọc nguyên nhân gốc của BeanCreation/UnsatisfiedDependency exception.
10. Khi có vấn đề AOT/Boot, kiểm tra extension point và lifecycle của framework đúng phiên bản.

## 22. Bài tập có đáp án định hướng

### Bài 1 — Khi nào dùng registrar?

Bạn chỉ cần tạo `InvoiceService` với hai dependency cố định. Có cần `ImportBeanDefinitionRegistrar` không?

**Đáp án:** Thường không. `@Bean InvoiceService invoiceService(Repository r, Policy p)` hoặc `@Service`/constructor injection rõ và ít boilerplate hơn. Registrar hợp lý khi cần metadata registration động theo cấu hình/annotation.

### Bài 2 — @Import ở đâu?

Một class `AppConfig` muốn bật `GreetingRegistrar`. Có thể viết:

```java
@Configuration(proxyBeanMethods = false)
@Import(GreetingRegistrar.class)
class AppConfig { }
```

Nếu registrar của ví dụ chính đọc `@EnableGreetings`, đoạn này chạy đúng không?

**Đáp án:** Spring có thể import registrar, nhưng vì `AppConfig` không mang `@EnableGreetings`, logic demo sẽ phát hiện `attributes == null` và fail fast. Muốn ví dụ đó hoạt động, dùng `@EnableGreetings({"email","sms"})` hoặc đổi hợp đồng registrar để hỗ trợ import trực tiếp.

### Bài 3 — Tạo definition hay tạo instance?

`registry.registerBeanDefinition("x", def)` đã gọi constructor của bean class chưa?

**Đáp án:** Không mặc định. Registrar đăng ký metadata; BeanFactory tạo instance sau đó theo scope, eager/lazy initialization và dependency resolution.

### Bài 4 — Bean names

Với annotation `@EnableGreetings({"email","sms"})`, registrar demo tạo những bean names nào?

**Đáp án:** `greeting.email` và `greeting.sms`. Cả hai cùng class `GreetingHandler`, nhưng constructor arguments khác. Đó là hai bean definitions, không phải aliases.

### Bài 5 — Đọc AnnotationMetadata

Tại sao không dùng `GreetingRegistrar.class.getAnnotation(EnableGreetings.class)` để lấy channels?

**Đáp án:** Vì annotation được đặt trên importing configuration class `AppConfig`. Spring cung cấp `AnnotationMetadata` của class đó cho registrar. Metadata registrar class không phải nguồn cấu hình cần đọc.

### Bài 6 — Constructor injection

Để đăng ký bean `Worker` có constructor `Worker(String name)`, lựa chọn nào đúng về ý tưởng?

```java
BeanDefinition def = BeanDefinitionBuilder
        .genericBeanDefinition(Worker.class)
        .addConstructorArgValue("batch")
        .getBeanDefinition();
registry.registerBeanDefinition("worker.batch", def);
```

**Đáp án:** Hợp lý; đây là metadata constructor argument. `Worker` phải có constructor tương thích. Còn type `BeanDefinition` và registry phải thuộc Spring API.

### Bài 7 — Bean alias hay bean thứ hai?

Nếu `registerBeanDefinition("greeting.email", def)` rồi tạo thêm một alias `legacyGreeting` trỏ về `greeting.email`, bạn có hai definitions không?

**Đáp án:** Không. Alias chỉ là tên khác của cùng definition; số definitions vẫn là một. Nếu đăng ký **một definition thứ hai** dưới `greeting.legacy` thì mới có thêm bean definition.

### Bài 8 — BeanDefinitionRegistryPostProcessor

Có thể từ một registrar đăng ký bean implement `BeanDefinitionRegistryPostProcessor` để nó chạy như một post-processor mới không?

**Đáp án:** Không nên làm vậy; Javadoc registrar cảnh báo không đăng ký types này từ registrar do lifecycle constraints trong configuration processing. Chọn extension point/post-processor registration đúng.

### Bài 9 — Chọn implementation trong Java @Bean

Có hai `GreetingHandler` bean, `greeting.email` và `greeting.sms`. Một Java bean chỉ muốn email. Viết factory parameter như thế nào?

```java
@Bean
GreetingDashboard dashboard(
        @Qualifier("greeting.email") GreetingHandler handler) {
    return new GreetingDashboard(handler);
}
```

**Đáp án:** Dùng `@Qualifier("greeting.email")` để xác định ứng viên. Nếu chỉ ghi `GreetingHandler handler`, Spring có thể gặp nhập nhằng do có hai candidates cùng type.

### Bài 10 — Validation

Nếu `@EnableGreetings({"email","Email"})` trong demo, kết quả nên là gì?

**Đáp án:** Registrar validate regex `[a-z][a-z0-9-]*`, nên `Email` bị từ chối (chữ hoa). Đây là convention của demo, không phải luật tên bean bắt buộc của Spring.

### Bài 11 — Aware/constructor injection của registrar

Registrar cần `Environment` để quyết định bật một feature. Có cần tạo một Spring business bean chỉ để đọc một property không?

**Đáp án:** Không. Có thể dùng `EnvironmentAware` hoặc constructor có tham số `Environment` thuộc danh sách supported types cho registrar. Lấy giá trị ổn định rồi đăng ký definitions; tránh khởi tạo business bean sớm.

### Bài 12 — Thiết kế @EnableFeature

Bạn muốn annotation `@EnableDataAdapters({"mysql","postgres"})` tạo một bean adapter cho mỗi tên. Hãy nêu các thành phần chính.

**Đáp án định hướng:**

1. Khai báo `@interface EnableDataAdapters` với `@Target(TYPE)`, `@Retention(RUNTIME)` và `@Import(DataAdapterRegistrar.class)`.
2. Registrar đọc mảng names từ `AnnotationMetadata` của importing class.
3. Validate danh sách và tạo tên ổn định như `adapter.mysql`/`adapter.postgres`.
4. Tạo `BeanDefinition` mỗi adapter bằng builder, constructor args/metadata phù hợp.
5. Kiểm tra collision policy rồi `registerBeanDefinition` từng entry.
6. Viết integration test tạo `AnnotationConfigApplicationContext` để xác minh definitions, injection, wrong values và duplicate names.
7. Nếu adapter dùng DB thật, tránh kết nối ngay trong registrar; để BeanFactory và lifecycle phù hợp quản lý.

## 23. Checklist trước khi đưa registrar vào thư viện

- [ ] Có lý do thật sự phải tạo bean definitions động; `@Bean`/component scan không còn diễn đạt gọn hơn.
- [ ] Registrar được kết nối vào Spring configuration qua `@Import` trực tiếp hoặc custom `@Enable...`.
- [ ] Đã chọn đúng overload `registerBeanDefinitions` và không override làm mất default delegation ngoài ý định.
- [ ] Không instantiate class cấu hình hoặc business service để đọc annotation values; dùng `AnnotationMetadata`.
- [ ] Annotation attributes được validate trước khi đăng ký.
- [ ] Bean names deterministic, có namespace và collision policy rõ.
- [ ] `BeanDefinition` mô tả đúng class, constructor values, scope, role, autowire candidate và qualifiers nếu cần.
- [ ] Không dùng role metadata như thay thế `@Primary`/`@Qualifier`.
- [ ] Không tự khởi tạo resource, gọi external services hay tạo context con trong registrar.
- [ ] Không cố đăng ký `BeanDefinitionRegistryPostProcessor` từ registrar.
- [ ] Có test cho một/nhiều beans, duplicate names, invalid values và missing annotation.
- [ ] Test Spring context thật chứng minh type/qualifier injection hoạt động.
- [ ] Hiểu sự khác nhau giữa definition registration và instance creation.
- [ ] Với Spring AOT/native, đã đánh giá tính deterministic và metadata reflection/proxy cần thiết.
- [ ] Có tài liệu về cách ứng dụng bật/tắt module và tên public bean mà nó cung cấp.

## Tổng kết

`ImportBeanDefinitionRegistrar` là extension point cho **lớp hạ tầng cần đăng ký BeanDefinition theo metadata của configuration class**. Nó kết hợp với `@Import`, thường được đóng gói thành custom annotation kiểu `@Enable...`. Registrar đọc `AnnotationMetadata`, dựng definitions với `BeanDefinitionBuilder`/`RootBeanDefinition` và thêm chúng qua `BeanDefinitionRegistry`. Việc quản lý instance, scope, dependency injection và lifecycle **vẫn thuộc Spring BeanFactory**.

Hãy sử dụng registrar để diễn đạt **cấu trúc bean động ở startup** — không để chạy nghiệp vụ. Thiết kế tốt phải có tên bean ổn định, validate metadata, kiểm tra xung đột, không đụng vào những bean chưa khởi tạo và có integration tests chứng minh behavior. Đối với bean cố định, chọn `@Bean` hoặc stereotype thường đơn giản và bền vững hơn.

## Tài liệu chính thức

- [Spring Framework 6.2 — ImportBeanDefinitionRegistrar API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html): hợp đồng registrar, các overload, Aware/constructor injection và cảnh báo về `BeanDefinitionRegistryPostProcessor`.
- [Spring Framework 6.2 — @Import API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Import.html): các loại imports được Spring hỗ trợ.
- [Spring Framework 6.2 — BeanDefinitionRegistry API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistry.html): đăng ký và kiểm tra definitions.
- [Spring Framework 6.2 — BeanDefinitionBuilder API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionBuilder.html): xây definitions với constructor args, scope và property values.
- [Spring Framework 6.2 — AnnotationMetadata API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/type/AnnotationMetadata.html): đọc annotation data không cần tạo instance.
- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): `@Configuration`, `@Bean`, `@Import` và composition.
