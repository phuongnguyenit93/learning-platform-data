# Giá trị cấu hình và tham chiếu giữa các bean — Spring Framework Core Container

## 1. Mục tiêu: giá trị và tham chiếu không phải một khái niệm

Khi tạo một bean trong Spring, đôi khi bạn cần truyền **dữ liệu cấu hình** như tên kênh, URL, số lần thử, tiền tố thông báo hoặc timeout. Lúc khác, bạn cần nối bean ấy với **một bean khác** do Spring quản lý. Hai nhu cầu này có thể cùng xuất hiện ở constructor, factory method hoặc setter, nhưng phải phân biệt rõ:

- **Configuration value:** dữ liệu String, số, boolean, enum, URI hoặc một value object phù hợp. Nó có thể là literal hoặc được lấy từ `Environment`/property source.
- **Bean reference:** yêu cầu Spring lấy **object bean** theo tên hoặc phân giải một dependency tương thích kiểu để truyền cho bean hiện tại.
- **Bean name:** chuỗi định danh một bean trong registry. Bản thân chuỗi tên **không tự trở thành object reference** nếu chỉ truyền vào một property String.
- **BeanDefinition:** metadata cho biết cách Spring tạo và cấu hình bean, trong đó có thể chứa **literal value** và **RuntimeBeanReference** trước khi object thực sự được lắp ghép.

Sau bài, bạn có thể:

1. Phân biệt value, reference, bean name, bean definition và managed object.
2. Sử dụng `@Bean`, constructor injection và `Environment.getRequiredProperty(...)`.
3. Đăng ký definition bằng `BeanDefinitionBuilder.addPropertyValue(...)` và `addPropertyReference(...)`.
4. Quan sát metadata `RuntimeBeanReference` trước khi đối chiếu object thực tế đã được inject.
5. Biết vai trò của `@Value`, `@PropertySource`, constructor arguments, property conversion và thứ tự property sources.
6. Xử lý các lỗi thiếu key, thiếu bean, sai setter/type và nhiều ứng viên.
7. Chạy chương trình Spring Framework **Java 17+** độc lập, đối chiếu Maven/`javac`/`java` và stdout.

**Phạm vi:** tập trung vào cách Spring Core Container cung cấp **giá trị cấu hình** và **tham chiếu giữa bean**. Không cần Spring Boot, MVC, database hoặc hệ thống cấu hình phân tán.

## 2. Một đồ thị nhỏ có hai loại cạnh

Ứng dụng gửi thông báo có hai thành phần:

- `MessageGateway` cần **giá trị** `notify.channel = MAIL`.
- `NotificationService` cần **bean object** `MessageGateway` và **giá trị** `notify.prefix = Xin chao`.
- `ManualSender` cần giá trị `label = manual` cùng tham chiếu tới bean `messageGateway`.

~~~mermaid
flowchart LR
    E1["Environment: notify.channel=MAIL"] -->|"String value"| G["Bean: messageGateway"]
    E2["Environment: notify.prefix=Xin chao"] -->|"String value"| N["Bean: notificationService"]
    G -->|"Bean object"| N
    V["BeanDefinition: label=manual"] -->|"Literal"| M["Bean: manualSender"]
    G -->|"Bean reference"| M
~~~

| Đầu vào | Spring/Java thực hiện | Kết quả |
| --- | --- | --- |
| Chuỗi literal `"manual"` | Gán vào property kiểu `String` | Một giá trị, không phải bean |
| `Environment.getRequiredProperty("notify.prefix")` | Tìm key trong property sources | String `"Xin chao"` |
| Tham số `MessageGateway gateway` ở `@Bean` | Giải quyết bean candidate phù hợp | Managed object `MessageGateway` |
| `addPropertyReference("gateway", "messageGateway")` | Tra registry, resolve reference | Object bean để gọi setter |
| `RuntimeBeanReference.getBeanName()` | Đọc metadata | Tên bean đích, không phải chính object |

**Lưu ý ngữ nghĩa:** cả `"MAIL"` và `"messageGateway"` có thể được viết dưới dạng chuỗi trong cấu hình, nhưng chuỗi thứ nhất là dữ liệu nghiệp vụ; chuỗi thứ hai dùng làm **địa chỉ reference** khi đặt vào API `addPropertyReference`.

## 3. Truyền value và bean object bằng @Bean factory methods

JavaConfig có thể viết:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    MessageGateway messageGateway(Environment environment) {
        return new MessageGateway(
                environment.getRequiredProperty("notify.channel"));
    }

    @Bean
    NotificationService notificationService(
            MessageGateway gateway, Environment environment) {
        String prefix =
                environment.getRequiredProperty("notify.prefix");
        return new NotificationService(gateway, prefix);
    }
}
~~~

**Đây là snippet minh họa**, chưa có import/định nghĩa các kiểu. File Java hoàn chỉnh ở mục 5.

- Tham số `Environment` là khả năng Spring có thể cung cấp khi gọi factory method; bạn dùng nó đọc dữ liệu từ property sources.
- Tham số `MessageGateway gateway` là **dependency đối tượng**, cần bean instance phù hợp trong container.
- `NotificationService` nhận cả `gateway` (object) và `prefix` (String) qua constructor; nó không cần trực tiếp biết property key hay gọi container.
- `@Configuration(proxyBeanMethods = false)` phù hợp khi các `@Bean` methods không gọi trực tiếp nhau. Nếu tự gọi `messageGateway(env)` bên trong method khác, đó là lời gọi Java bình thường có thể tạo object ngoài bean singleton đúng ý định.

### Có bắt buộc mọi giá trị đều xuất phát từ Environment không?

Không. Một cấu hình đơn giản có thể chứa:

~~~java
@Bean
MessageGateway messageGateway() {
    return new MessageGateway("MAIL");
}
~~~

Chữ `"MAIL"` là literal value hợp lệ. Nhưng nếu kênh khác nhau giữa môi trường, dùng `Environment` hoặc nguồn cấu hình bên ngoài giúp không phải sửa code factory mỗi lần deployment.

Một value thuần như `"MAIL"` không cần đăng ký thành một bean riêng, trừ khi bạn có **value object/hợp đồng quản lý** thực sự có ích.

## 4. BeanDefinitionBuilder: phân biệt property value và property reference

Cùng ý tưởng có thể biểu đạt bằng metadata programmatically:

~~~java
BeanDefinition senderDefinition = BeanDefinitionBuilder
        .genericBeanDefinition(ManualSender.class)
        .addPropertyValue("label", "manual")
        .addPropertyReference("gateway", "messageGateway")
        .getBeanDefinition();

context.registerBeanDefinition("manualSender", senderDefinition);
~~~

**Snippet**, cần `ManualSender` có no-argument constructor và hai setter phù hợp. Nó chưa phải tệp Java độc lập.

Hai builder methods không tương đương:

- `addPropertyValue("label", "manual")` lưu literal, để container gán value cho setter `setLabel(String)`.
- `addPropertyReference("gateway", "messageGateway")` lưu thông tin **tham chiếu tới bean**; khi tạo `manualSender`, Spring resolve bean theo tên và gán object vào setter `setGateway(MessageGateway)`.

Một sai lầm thường gặp:

~~~java
.addPropertyValue("gateway", "messageGateway")
~~~

Đây **không** là cách đúng để yêu cầu Spring inject managed `MessageGateway`. Nó đang cung cấp String literal cho property cần object kiểu `MessageGateway`; hệ thống conversion thông thường không tự biến tên bean bất kỳ thành reference mong muốn. Hãy dùng `addPropertyReference(...)`.

### RuntimeBeanReference là metadata, không phải object bean

Có thể đọc lại:

~~~java
BeanDefinition definition =
        context.getBeanFactory().getBeanDefinition("manualSender");
PropertyValue reference =
        definition.getPropertyValues().getPropertyValue("gateway");

RuntimeBeanReference ref =
        (RuntimeBeanReference) reference.getValue();
System.out.println(ref.getBeanName()); // messageGateway
~~~

Đây là đoạn minh họa cần import `PropertyValue` và `RuntimeBeanReference`; ví dụ đầy đủ ở phần sau có các import đó.

Khi Spring **chưa gán property**, definition có thể giữ metadata `RuntimeBeanReference`. Sau khi tạo instance, `manualSender.gateway()` phải là **object** thật. Để chắc chắn wiring đúng, kiểm tra cả definition lẫn identity/runtime behavior.

### Setter injection khác constructor injection

Mã builder ở đây cố ý dùng setters để thấy rõ `addPropertyValue` và `addPropertyReference`. Setter injection phù hợp khi property cần thiết có hợp đồng cấu hình rõ; tuy nhiên, **constructor injection thường thích hợp hơn với dependency bắt buộc**, vì instance được tạo đã có collaborator cần thiết. Bạn cũng có thể mô tả constructor args trong builder:

~~~java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(AlertWorker.class)
        .addConstructorArgValue("batch")
        .addConstructorArgReference("messageGateway")
        .getBeanDefinition();
~~~

Đây là **snippet minh họa không độc lập**: `AlertWorker` chưa được định nghĩa, và cần constructor tương thích như `AlertWorker(String mode, MessageGateway gateway)`. Về ngữ nghĩa, `addConstructorArgValue` đưa literal; `addConstructorArgReference` yêu cầu resolve một bean object.

## 5. Project Java 17+ runnable với @Bean và BeanDefinitionBuilder

Dùng **Spring Framework 6.2.19**, JDK 17+ và Maven. Phiên bản được ghim cho ví dụ, **không khẳng định là bản Spring mới nhất**. Không cần Spring Boot, web server hoặc database.

~~~text
bean-values-references-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanValuesReferencesDemo.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-values-references-demo</artifactId>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.BeanValuesReferencesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Module `spring-context` kéo theo Spring dependencies liên quan. Khi chạy `javac` trực tiếp, cần classpath đủ các JAR đó; không thể chỉ đưa file nguồn Java cho compiler rồi chờ nó tự tìm Spring.

### 5.2. BeanValuesReferencesDemo.java

Tạo file `src/main/java/demo/BeanValuesReferencesDemo.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;

import org.springframework.beans.PropertyValue;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.RuntimeBeanReference;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public final class BeanValuesReferencesDemo {
    private BeanValuesReferencesDemo() {}

    public static final class MessageGateway {
        private final String channel;

        public MessageGateway(String channel) {
            this.channel = Objects.requireNonNull(channel);
        }

        public String channel() {
            return channel;
        }
    }

    public static final class NotificationService {
        private final MessageGateway gateway;
        private final String prefix;

        public NotificationService(MessageGateway gateway, String prefix) {
            this.gateway = Objects.requireNonNull(gateway);
            this.prefix = Objects.requireNonNull(prefix);
        }

        public MessageGateway gateway() {
            return gateway;
        }

        public String notification(String name) {
            return prefix + " " + name + " (" + gateway.channel() + ")";
        }
    }

    public static final class ManualSender {
        private String label;
        private MessageGateway gateway;

        public ManualSender() {}

        public void setLabel(String label) {
            this.label = Objects.requireNonNull(label);
        }

        public void setGateway(MessageGateway gateway) {
            this.gateway = Objects.requireNonNull(gateway);
        }

        public MessageGateway gateway() {
            return gateway;
        }

        public String send(String name) {
            return label + ":" + gateway.channel() + ":" + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public MessageGateway messageGateway(Environment env) {
            return new MessageGateway(
                    env.getRequiredProperty("notify.channel"));
        }

        @Bean
        public NotificationService notificationService(
                MessageGateway gateway, Environment env) {
            return new NotificationService(gateway,
                    env.getRequiredProperty("notify.prefix"));
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("lessonProperties",
                            Map.<String, Object>of(
                                    "notify.channel", "MAIL",
                                    "notify.prefix", "Xin chao")));

            context.register(AppConfig.class);

            BeanDefinition senderDefinition = BeanDefinitionBuilder
                    .genericBeanDefinition(ManualSender.class)
                    .addPropertyValue("label", "manual")
                    .addPropertyReference("gateway", "messageGateway")
                    .getBeanDefinition();

            context.registerBeanDefinition("manualSender", senderDefinition);
            context.refresh();

            MessageGateway gateway = context.getBean(MessageGateway.class);
            NotificationService service =
                    context.getBean(NotificationService.class);
            ManualSender manual = context.getBean(ManualSender.class);

            BeanDefinition stored =
                    context.getBeanFactory()
                            .getBeanDefinition("manualSender");
            PropertyValue label =
                    stored.getPropertyValues().getPropertyValue("label");
            PropertyValue gatewayReference =
                    stored.getPropertyValues().getPropertyValue("gateway");
            RuntimeBeanReference ref =
                    (RuntimeBeanReference) gatewayReference.getValue();

            System.out.println("propertyPrefix=" +
                    context.getEnvironment().getProperty("notify.prefix"));
            System.out.println("gatewayChannel=" + gateway.channel());
            System.out.println("literalValue=" + label.getValue());
            System.out.println("referenceBean=" + ref.getBeanName());
            System.out.println("sameGateway=" +
                    (service.gateway() == gateway
                     && manual.gateway() == gateway));
            System.out.println("notification=" +
                    service.notification("Lan"));
            System.out.println("manualSend=" + manual.send("Lan"));
            System.out.println("senderSingleton=" +
                    (manual == context.getBean(ManualSender.class)));
        }
    }
}
~~~

**Tính tự chứa của ví dụ:** một public top-level class khớp tên tệp, nested types phù hợp. `Map.<String, Object>of(...)` tạo property source với kiểu map phù hợp; Java 17 hỗ trợ. Các bean definitions và nguồn property được đăng ký **trước `refresh()`**.

`MessageGateway` được cấu hình từ value `"MAIL"`; `NotificationService` lấy một reference và một value; `ManualSender` nhận một literal qua `setLabel` và một bean object qua `setGateway`. Chương trình đối chiếu metadata và runtime để không nhầm hai tầng này.

### 5.3. Chạy bằng Maven

Trong thư mục `bean-values-references-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng tám dòng stdout do phương thức main in khi chạy thành công:**

~~~text
propertyPrefix=Xin chao
gatewayChannel=MAIL
literalValue=manual
referenceBean=messageGateway
sameGateway=true
notification=Xin chao Lan (MAIL)
manualSend=manual:MAIL:Lan
senderSingleton=true
~~~

Các dòng phiên bản JDK/Maven và log Maven có thể xuất hiện tùy máy, **không** thuộc tám dòng do code demo in. Ví dụ không dùng random, đồng hồ hoặc thứ tự iteration để quyết định output.

### 5.4. Biên dịch và chạy trực tiếp bằng javac/java

Tạo classpath dependency bằng Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanValuesReferencesDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanValuesReferencesDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanValuesReferencesDemo.java
java -cp "out;$deps" demo.BeanValuesReferencesDemo
~~~

Dấu phân tách classpath là `:` trên Unix, `;` trên Windows. Chạy `javac` mà thiếu Spring JAR dẫn tới lỗi compile kiểu `package org.springframework... does not exist`, không phải bằng chứng cấu hình bean sai.

## 6. Diễn giải tám dòng output

| Output | Kết luận |
| --- | --- |
| `propertyPrefix=Xin chao` | `Environment` đã cung cấp String từ property source |
| `gatewayChannel=MAIL` | Bean Gateway được tạo bằng giá trị `notify.channel` |
| `literalValue=manual` | BeanDefinition lưu literal property value |
| `referenceBean=messageGateway` | BeanDefinition lưu tên bean đích qua `RuntimeBeanReference` |
| `sameGateway=true` | Hai consumer thực tế được nối tới **cùng object bean singleton** |
| `notification=Xin chao Lan (MAIL)` | Service kết hợp data value và bean collaborator |
| `manualSend=manual:MAIL:Lan` | Setter cho value và reference đã được áp dụng |
| `senderSingleton=true` | Cùng bean name/type trong một context cho cùng instance singleton |

Nếu chỉ nhìn `referenceBean=messageGateway`, ta mới biết **metadata định hướng tới bean nào**; `sameGateway=true` mới kiểm chứng collaborator object ở runtime. BeanDefinition không đồng nghĩa bean instance.

## 7. Environment, property sources và thứ tự ưu tiên

Spring `Environment` tập hợp nhiều nguồn property như system properties, environment variables hoặc property sources mà ứng dụng đăng ký. Việc **nguồn nào thắng khi trùng key** là một phần của chính sách cấu hình.

Trong chương trình, mã:

~~~java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource("lessonProperties",
                Map.<String, Object>of(
                        "notify.channel", "MAIL",
                        "notify.prefix", "Xin chao")));
~~~

đặt dữ liệu demo lên đầu danh sách, nên nếu máy chạy có key trùng trong nguồn khác, hai giá trị trong bộ nhớ vẫn được ưu tiên. Đây là **quyết định phục vụ tính tái lập**, không có nghĩa ứng dụng thật luôn nên ghi đè mọi cấu hình triển khai.

### Đưa properties ra file

Một ứng dụng khác có thể dùng `src/main/resources/app.properties`:

~~~properties
notify.channel=MAIL
notify.prefix=Xin chao
~~~

Và đăng ký resource:

~~~java
@Configuration
@PropertySource("classpath:app.properties")
class AppConfig {
    // Những factory methods @Bean cần thiết.
}
~~~

**Đây là minh họa, không phải phiên bản thứ hai của file runnable.** Muốn chạy phải tạo file properties và viết config đầy đủ. `@PropertySource` cần nguồn resource tồn tại; không phải chỉ có annotation là dữ liệu tự xuất hiện.

### @Value thay thế Environment trong một số điểm injection

Một cách biểu đạt khác:

~~~java
@Bean
NotificationService notificationService(
        MessageGateway gateway,
        @Value("${notify.prefix}") String prefix) {
    return new NotificationService(gateway, prefix);
}
~~~

Đoạn này chỉ minh họa cú pháp và cần context cấu hình placeholder resolution phù hợp. `@Value` có thể inject value từ property placeholder hoặc biểu thức theo môi trường Spring. Trong bài runnable, dùng `Environment.getRequiredProperty` để **thiếu key bắt buộc thì lỗi rõ ràng**, không phụ thuộc việc placeholder chưa được giải quyết có thể được xử lý khác nhau theo cấu hình.

Không cần biến toàn bộ property thành `@Bean String` chỉ để dùng trong một factory method.

## 8. Bean reference theo tên và injection theo kiểu

Có hai phong cách cấu hình khác nhau:

- `@Bean NotificationService notificationService(MessageGateway gateway, ...)`: yêu cầu một candidate theo **type** và quy tắc autowiring.
- `addPropertyReference("gateway", "messageGateway")`: reference được chỉ ra **theo tên bean** trong metadata.

Khi có **hai bean cùng type** như `messageGatewayA` và `messageGatewayB`, injection theo kiểu đơn trị có thể không chọn được một ứng viên. Spring có các cơ chế:

- `@Qualifier("messageGatewayA")` khi điểm injection yêu cầu một bean cụ thể.
- `@Primary` khi cần một ứng viên mặc định có lý do rõ ràng.
- Tên bean tại composition root như `context.getBean("messageGatewayA", MessageGateway.class)`.
- Injection collection hoặc `ObjectProvider<MessageGateway>` khi thực sự cần nhiều candidates hoặc truy xuất linh hoạt.

Không diễn giải “hai bean cùng kiểu” là lỗi Java; vấn đề là **điểm injection cần một đối tượng mà Spring chưa chọn được**.

Nếu metadata reference chỉ tới một bean không tồn tại, Spring sẽ thất bại khi tạo object cần reference đó. Nó **không tự dùng String bean name làm giá trị** thay thế.

## 9. Value conversion và kiểm tra dữ liệu cấu hình

Không phải mọi configuration value đều là String trong object cuối cùng. Ví dụ:

~~~java
int retries =
        environment.getRequiredProperty("notify.retries", Integer.class);
~~~

Đây là snippet hợp lệ trong method có biến `Environment environment` và key được cung cấp. Spring có thể chuyển value dạng số sang kiểu `Integer` nhờ conversion phù hợp; nếu thiếu key hoặc không convert được, thường ném exception. **Conversion thành công không chứng minh dữ liệu phù hợp nghiệp vụ.**

Các quy tắc quan trọng:

- **Required value**: fail fast khi thiếu; không âm thầm dùng giá trị mặc định che lỗi triển khai.
- **Optional value**: chỉ dùng default khi hợp đồng cho phép thiếu cấu hình.
- **Validation**: kiểm tra timeout > 0, tên kênh không rỗng, địa chỉ hợp lệ, số lần thử trong giới hạn; làm rõ exception ở ranh giới cấu hình.
- **Type clarity**: property String tên bean không tự trở thành reference; hãy dùng đúng API.
- **Secrets**: tránh ghi token/password vào README thực tế, mã nguồn hoặc stdout. Dùng nguồn cấu hình bí mật được quản lý phù hợp.
- **Runtime changes**: việc cập nhật property source sau khi singleton đã tạo không tự tái inject/rebuild các object đó; cần cơ chế cấu hình động có chủ đích nếu muốn thay đổi runtime.

Đối với `BeanDefinitionBuilder.addPropertyValue`, Spring còn có thể dùng type conversion khi gán setter; nhưng không được kỳ vọng nó suy ra dependency object từ chuỗi tên bean khi người lập trình chưa tạo reference.

## 10. Scope và vòng đời liên quan tới tham chiếu

| Trường hợp | Điều xảy ra thường thấy |
| --- | --- |
| Gateway singleton mặc định | Service và ManualSender trong demo cùng nhận một object |
| Gateway prototype | Mỗi lần container tạo/cung cấp prototype theo yêu cầu có thể là instance khác |
| Prototype inject trực tiếp vào singleton | Thông thường resolve **một lần khi singleton được tạo**, không tự tạo object mới mỗi method call |
| Bean lazy | Có thể hoãn khởi tạo bean; logic dependency vẫn tồn tại |
| Reference tới alias | Alias dẫn tới bean được đặt tên tương ứng; không tự tạo definition mới |
| Bean tạo bằng new ngoài container | Không tự nhận DI/lifecycle của Spring |
| Context đã close | Không dùng context như một nguồn lấy bean mới |

Nếu service thực sự muốn mỗi lần gọi một Gateway mới, phải thiết kế provider/lookup theo scope thích hợp, **không chỉ đổi Gateway thành prototype và giữ trường reference mãi trong singleton**.

Vòng constructor/factory dependency A→B→A là dấu hiệu vấn đề kiến trúc; chuyển reference từ type sang String bean name không tự giải quyết chu trình.

## 11. Các lỗi thường gặp

| Lỗi/triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| `getRequiredProperty(...)` thất bại | Thiếu required key hoặc property source không được nạp | Kiểm tra key, thứ tự source, profile |
| Property sai định dạng | Không convert được tới kiểu setter/constructor | Kiểm tra type/converter và validation |
| `NoSuchBeanDefinitionException` | Bean name trong reference chưa được đăng ký | Kiểm tra `messageGateway` và registration |
| `UnsatisfiedDependencyException` | Factory/constructor cần bean mà Spring không cung cấp | Kiểm tra kiểu, qualifier, scan, config |
| `NoUniqueBeanDefinitionException` | Nhiều candidates cùng type, không rõ lựa chọn | Dùng qualifier/primary hoặc sửa wiring |
| `NotWritablePropertyException` | Programmatic property thiếu setter đúng tên/kiểu | Kiểm tra JavaBean getter/setter và public accessibility |
| Truyền `addPropertyValue("gateway","messageGateway")` | Nhầm chuỗi tên với bean reference | Dùng `addPropertyReference` |
| Trông như setter không chạy | Chưa tạo instance, bean lazy hoặc tên property sai | Lấy bean/đọc lỗi tạo bean, kiểm tra setters |
| `@Value` không resolve property như dự định | Thiếu property source/configurer phù hợp | Kiểm tra Environment và placeholder resolution |
| Programmatic registration sau refresh | Metadata không được xử lý đúng thời điểm mong muốn | Đăng ký trước `refresh()` |
| Runtime value mới không có tác dụng | Singleton đã tạo với value cũ | Dùng cơ chế reconfiguration được hỗ trợ |
| `package org.springframework... does not exist` | Classpath Maven/`javac` thiếu Spring | Kiểm tra pom và classpath |
| Bean mutable singleton có hành vi đua luồng | Nhiều caller chia sẻ một instance | Thiết kế thread-safe/scope phù hợp |

Cách debug: tách **lớp cấu hình (metadata)** khỏi **lớp đối tượng (runtime)**. Hỏi *property này là value hay reference?*, kiểm tra đúng key/bean name, xem type/setter, lần theo `Caused by` rồi đối chiếu object thực tế.

## 12. Kiểm thử đúng mục tiêu

**Unit test không cần Spring:** tạo Gateway và NotificationService bằng constructor:

~~~java
MessageGateway gateway = new MessageGateway("TEST");
NotificationService service = new NotificationService(gateway, "Hello");
System.out.println(service.notification("An")); // Hello An (TEST)
~~~

Đoạn này là snippet trong method/class có quyền truy cập nested types, không phải file độc lập. Nó kiểm tra logic Java mà không xác nhận bean registration.

**Integration test cấu hình:** tạo Context như ví dụ chính, rồi:

- Xác nhận metadata label literal và gateway RuntimeBeanReference đúng.
- Kiểm tra `service.gateway() == context.getBean(MessageGateway.class)`.
- Kiểm tra `manual.gateway()` cũng là object mong muốn.
- Test trường hợp thiếu `notify.prefix` hoặc thiếu bean `messageGateway` trong **cấu hình test riêng**; không phá demo happy path rồi so stdout cũ.
- Test property conversion/validation cho những key bắt buộc.

Đừng dùng Java `assert` như bảo đảm runtime bắt buộc vì mặc định có thể bị tắt khi thiếu `-ea`. Dùng exception hoặc test assertions thực sự được chạy.

## 13. Câu hỏi tự kiểm tra

**1.** Vì sao `addPropertyValue("gateway", "messageGateway")` không giống `addPropertyReference("gateway", "messageGateway")`?

**Trả lời:** Một cái chỉ cung cấp literal String, cái kia yêu cầu container resolve managed bean theo tên và inject object.

**2.** Vì sao tham số `MessageGateway gateway` của `@Bean notificationService(...)` là bean reference dù không có chữ `ref`?

**Trả lời:** Spring resolve tham số factory method theo kiểu/quy tắc autowiring rồi truyền bean object phù hợp.

**3.** `RuntimeBeanReference.getBeanName()` trả gì và khác object thật thế nào?

**Trả lời:** Trả tên bean đích, ở đây `"messageGateway"`. Field của `ManualSender` sau khi được tạo là object `MessageGateway`, không phải chuỗi tên.

**4.** Giá trị `notify.prefix` có cần trở thành bean String không?

**Trả lời:** Không. Factory method có thể đọc value trực tiếp từ Environment và truyền vào constructor; tạo value object/bean riêng chỉ khi có lý do thiết kế.

**5.** Vì sao ví dụ dùng `MapPropertySource.addFirst`?

**Trả lời:** Để dữ liệu trong bộ nhớ có ưu tiên cao, giúp output tái lập khi máy có property trùng tên. Ứng dụng thật cần thiết kế chính sách ưu tiên theo môi trường.

**6.** Nếu Gateway chuyển sang prototype, `sameGateway=true` còn chắc chắn không?

**Trả lời:** Không. Scope quyết định cách cấp phát instance; các injection/lookup có thể nhận những instance khác nhau.

**7.** Vì sao không gọi trực tiếp factory method `messageGateway(...)` từ method `notificationService(...)` khi đặt `proxyBeanMethods=false`?

**Trả lời:** Đó là lời gọi Java bình thường và có thể tạo object không phải managed bean được mong đợi; dùng tham số để Spring resolve.

## 14. Checklist vận dụng

- [ ] Xác định mỗi đầu vào là **value** hay **bean reference**.
- [ ] Đặt rõ tên bean và tên property, không nhầm bean name với dữ liệu.
- [ ] Dùng Environment/PropertySource cho externalized values phù hợp.
- [ ] Dùng `getRequiredProperty` cho thông số bắt buộc và validate domain.
- [ ] Dùng `@Bean` method parameters cho collaborator managed.
- [ ] Dùng `addPropertyValue` cho literal, `addPropertyReference` cho object bean.
- [ ] Đảm bảo setter/constructor nhận đúng kiểu và bean được đăng ký.
- [ ] Đăng ký programmatic definitions trước context refresh.
- [ ] Kiểm tra `RuntimeBeanReference` trong metadata và object identity sau wiring.
- [ ] Xử lý thiếu bean/nhiều bean bằng đăng ký và qualifier/primary đúng ý định.
- [ ] Đánh giá scope singleton/prototype/lazy và ảnh hưởng identity.
- [ ] Chạy Java 17+ và so **đúng tám dòng stdout**.
- [ ] Dùng classpath Spring đầy đủ cho `javac`/`java`.
- [ ] Không log secrets, không lấy default che cấu hình thiếu và không bỏ qua lỗi wiring.

**Ghi nhớ:** configuration value trả lời **“đưa dữ liệu gì vào bean?”**, còn bean reference trả lời **“nối bean này với object managed nào?”**. BeanDefinition giữ hai loại thông tin khác nhau; container chuyển đổi value và phân giải reference khi tạo object. Việc nhìn đúng ranh giới **metadata ↔ instance** giúp cấu hình Spring rõ ràng, an toàn và dễ kiểm thử.

### Tài liệu tham khảo chính thức

- [Spring Dependency Injection: Properties and Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
- [Spring Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring BeanDefinition API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)
