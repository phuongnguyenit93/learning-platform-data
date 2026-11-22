# Phân biệt tham chiếu bean với giá trị đơn giản — Spring Framework Core Container

## 1. Mục tiêu: xác định chính xác thứ được inject

Trong Spring IoC container, một constructor hoặc factory method có thể nhận nhiều tham số: một số tham số là **bean collaborator** do Spring đăng ký và quản lý; một số khác chỉ là **giá trị cấu hình đơn giản** như chuỗi, số, boolean hoặc thời gian chờ. Chúng đều được truyền vào một phương thức Java, nhưng **ý nghĩa và cơ chế phân giải khác nhau**.

Ví dụ `GreetingService` cần:

- `NameFormatter`: một **đối tượng bean** dùng chung để chuẩn hóa tên.
- `prefix`: chuỗi `"Xin chao"` từ cấu hình.
- `maxChars`: số nguyên `8` từ cấu hình, dùng để giới hạn độ dài tên.

`NameFormatter` là một **dependency tới bean**. `prefix` và `maxChars` là **giá trị**, không tự động trở thành Spring bean chỉ vì chúng xuất hiện trong constructor.

Sau bài này bạn có thể:

1. Phân biệt bean reference, bean name, literal value, external configuration value và bean instance.
2. Nhận biết constructor/factory-method argument nào nên do Spring resolve như bean, argument nào phải được cung cấp từ cấu hình hoặc dữ liệu Java.
3. Sử dụng `@Bean` factory method và `Environment.getRequiredProperty(...)` để truyền đúng collaborator cùng các giá trị `String`/`Integer`.
4. Giải thích `@Value`/property placeholders khác `@Qualifier`/bean lookup.
5. Phân biệt `BeanDefinitionBuilder.addPropertyValue(...)` với `addPropertyReference(...)` và cách `RuntimeBeanReference` được resolve thành object.
6. Xác minh metadata và wiring trên một ví dụ Spring Framework thuần, chạy được với Java 17+.
7. Xử lý lỗi thiếu bean, nhiều bean cùng kiểu, thiếu property, sai kiểu, sai setter, scope và những hiểu nhầm thường gặp.

**Phạm vi bài:** *phân biệt bean reference với simple/configuration value trong cơ chế dependency injection*. Spring Boot, Spring MVC, JPA và các framework ngoài Core Container không cần thiết.

## 2. Khái niệm theo đúng tầng abstraction

| Khái niệm | Ví dụ | Container hiểu thế nào |
| --- | --- | --- |
| Java type | `NameFormatter`, `String`, `int` | Kiểu của tham số/field, chưa tự nói đó là bean hay value |
| Bean name | `"nameFormatter"` | Khóa định danh bean trong registry |
| Bean reference | Bean object được cung cấp cho `NameFormatter formatter` | Một dependency tới đối tượng container quản lý |
| Literal value | `"manual"`, `8` | Dữ liệu trực tiếp được đưa vào constructor/setter |
| External configuration value | Property `greeting.prefix=Xin chao` | Được đọc từ `Environment` hoặc cơ chế value resolution |
| `RuntimeBeanReference` | Metadata trỏ tới bean tên `nameFormatter` | Chưa phải object; Spring resolve khi tạo bean |
| Bean instance | Object `UppercaseFormatter` thực tế | Object đã được tạo, có thể được chia sẻ theo scope |

**Chỉ có tên chưa phải một tham chiếu.** Hai đoạn sau không tương đương:

~~~java
.addPropertyValue("formatter", "nameFormatter")
.addPropertyReference("formatter", "nameFormatter")
~~~

Đây là các **snippet cấu hình**, không phải Java statements độc lập. Dòng đầu truyền literal `String` chứa chữ `nameFormatter` vào property; dòng sau yêu cầu Spring **tìm bean tên `nameFormatter` và inject object** vào property `formatter`. Nếu setter nhận `NameFormatter`, thông thường phải dùng dòng thứ hai.

### Một sơ đồ có hai đường vào khác nhau

~~~mermaid
flowchart LR
    E1["Environment: greeting.prefix"] -->|"String value"| S["greetingService: GreetingService"]
    E2["Environment: greeting.maxChars"] -->|"int value"| S
    B["nameFormatter: NameFormatter"] -->|"bean object"| S
    L["literal: manual"] -->|"String value"| M["manualGreeting: ManualGreeting"]
    B -->|"bean reference"| M
~~~

Sơ đồ dùng chiều mũi tên thể hiện **giá trị/object được cung cấp cho consumer**. Nếu biểu diễn dependency graph theo chiều **consumer → dependency**, cạnh bean tương ứng là `greetingService → nameFormatter` và `manualGreeting → nameFormatter`. Giá trị String/int không nhất thiết là node bean riêng.

## 3. Java constructor nhận bean và value vẫn là một constructor bình thường

Thiết kế Java không phụ thuộc Spring:

~~~java
public final class GreetingService {
    private final NameFormatter formatter; // collaborator
    private final String prefix;            // configuration value
    private final int maxChars;              // configuration value

    public GreetingService(
            NameFormatter formatter, String prefix, int maxChars) {
        this.formatter =
                java.util.Objects.requireNonNull(formatter);
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix required");
        }
        if (maxChars <= 0) {
            throw new IllegalArgumentException("maxChars must be positive");
        }
        this.prefix = prefix;
        this.maxChars = maxChars;
    }
}
~~~

**Snippet minh họa**, thiếu `NameFormatter` và một public class hợp lệ chứa code. Nó cho thấy:

- `formatter` là một **collaborator object**. Spring cần biết có bean nào thỏa kiểu `NameFormatter`.
- `prefix` là **String data**, phải đến từ cấu hình hoặc caller, không mặc nhiên là một bean theo tên.
- `maxChars` là **số nguyên**, cần được đọc/chuyển kiểu và validate.
- Constructor bảo vệ invariant: không null collaborator, prefix có nội dung, maxChars dương. Spring không thay thế validation domain do Java class tự định nghĩa.
- Những field `final` giữ các reference/value không bị gán lại; **không đồng nghĩa deep immutability** hoặc thread safety của collaborator mutable.

Java thuần có thể tạo object nếu tự cấp đủ tham số:

~~~java
NameFormatter formatter = new UppercaseFormatter();
GreetingService service =
        new GreetingService(formatter, "Hello", 12);
~~~

Đây là **manual dependency injection**, chưa dùng Spring. Container chỉ tự động hóa việc chọn/tạo bean và cung cấp các giá trị theo cấu hình mà bạn định nghĩa.

### Đừng gắn nhãn bean cho mọi tham số

Spring không nên được yêu cầu “autowire theo type” một `String` hay một `int` chỉ vì service constructor có chúng. Trong autowiring mặc định, các simple properties như primitive, `String` và `Class` không được tự động autowire như collaborator thông thường theo cùng cách. Để value có ý nghĩa rõ, hãy dùng `Environment`, `@Value`, giá trị literal tại composition root hoặc một configuration object được khai báo rõ ràng.

Có thể cố tình đăng ký một bean kiểu `String`, nhưng đó là quyết định cấu hình riêng, **không biến mọi String trong ứng dụng thành bean**. Tránh tạo hàng chục `@Bean String` vô danh gây nhầm lẫn giữa dữ liệu và service.

## 4. Cách JavaConfig truyền hai loại đầu vào đúng ranh giới

Một lớp cấu hình ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    NameFormatter nameFormatter() {
        return new UppercaseFormatter();
    }

    @Bean
    GreetingService greetingService(
            NameFormatter formatter, Environment env) {
        String prefix =
                env.getRequiredProperty("greeting.prefix");
        int maxChars =
                env.getRequiredProperty("greeting.maxChars", Integer.class);
        return new GreetingService(formatter, prefix, maxChars);
    }
}
~~~

**Đây là snippet minh họa**, ví dụ đầy đủ nằm ở mục 6. Cách đọc:

1. `@Bean nameFormatter()` tạo/đăng ký một managed bean `NameFormatter`.
2. `@Bean greetingService(NameFormatter formatter, Environment env)` có một collaborator theo type và một tham số `Environment` do Spring cung cấp.
3. Spring resolve bean `NameFormatter`, truyền đúng object vào method tạo service.
4. Factory method đọc hai configuration keys; `prefix` là String, còn `maxChars` được conversion thành `Integer` rồi unbox sang `int`.
5. Factory method tạo service với đầy đủ **bean reference + simple values**. Nếu required key thiếu/không chuyển được, việc tạo bean thất bại thay vì tự động điền null hoặc số không không phù hợp.
6. `@Configuration(proxyBeanMethods=false)` hợp lệ vì factory methods **không trực tiếp gọi lẫn nhau**; Spring thực hiện wiring qua tham số method.

**Không suy ra “`Environment` là simple value”.** `Environment` là abstraction Spring cung cấp vào factory method; những property đọc *từ nó* mới là simple values trong ví dụ. Nó không giống việc một `String` được ngẫu nhiên tìm như bean theo type.

### @Value là một cách khác để cung cấp simple value

Bạn có thể dùng:

~~~java
@Bean
GreetingService greetingService(
        NameFormatter formatter,
        @Value("${greeting.prefix}") String prefix,
        @Value("${greeting.maxChars}") int maxChars) {
    return new GreetingService(formatter, prefix, maxChars);
}
~~~

**Snippet thay thế**, cần import `org.springframework.beans.factory.annotation.Value`, các property sources và cơ chế placeholder resolution phù hợp. Ở đây `@Value("${greeting.prefix}")` có ý định resolve một **giá trị** từ config; `NameFormatter formatter` vẫn là một **bean dependency**. `@Value` còn có thể dùng biểu thức Spring Expression Language theo cấu hình, nhưng không cần trong bài học này.

So sánh:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `@Value("${greeting.prefix}") String prefix` | Resolve cấu hình thành String cho tham số |
| `@Value("${greeting.maxChars}") int maxChars` | Resolve rồi chuyển value sang int phù hợp |
| `@Qualifier("nameFormatter") NameFormatter formatter` | Chọn **bean candidate**, không đọc một property String |
| `environment.getRequiredProperty("greeting.prefix")` | Đọc property rõ ràng, fail nếu key bắt buộc thiếu |
| `@Bean NameFormatter nameFormatter()` | Đăng ký cách tạo **bean object** thay vì một value String |

Cảnh báo: biểu thức placeholder `${key}` cần property source và cấu hình resolution tương thích. Không mặc định việc thiếu key luôn được xử lý giống hệt `Environment.getRequiredProperty(...)` trong mọi kiểu context. Ví dụ runnable sẽ dùng `Environment` để quy tắc **bắt buộc có key** minh bạch.

## 5. BeanDefinition: value và reference nằm ở metadata như thế nào?

Spring có thể lưu cấu hình object không chỉ qua `@Bean` factory methods mà còn dưới dạng **BeanDefinition metadata**:

~~~java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(ManualGreeting.class)
        .addPropertyValue("label", "manual")
        .addPropertyReference("formatter", "nameFormatter")
        .getBeanDefinition();

context.registerBeanDefinition("manualGreeting", definition);
~~~

Đây là **snippet**; cần các class và context phù hợp ở mục 6. Hai thao tác làm hai việc khác nhau:

- `addPropertyValue("label", "manual")` lưu literal value. Khi bean `manualGreeting` được tạo, Spring tìm property `label` và gọi setter `setLabel(String)` với String `"manual"`.
- `addPropertyReference("formatter", "nameFormatter")` lưu một **RuntimeBeanReference** (hoặc metadata resolution tương ứng) tới bean name. Khi tạo bean, Spring resolve object `nameFormatter`, sau đó gọi `setFormatter(NameFormatter)`.

Setter phải phù hợp về **tên, khả năng ghi và kiểu đích**. Nếu `ManualGreeting` không có `setFormatter(NameFormatter)` hoặc bean name không tồn tại, Spring có thể không tạo được bean hợp lệ.

### Metadata giữ tên, runtime giữ object

Có thể kiểm tra:

~~~java
BeanDefinition stored = context.getBeanFactory()
        .getBeanDefinition("manualGreeting");
PropertyValue labelProperty =
        stored.getPropertyValues().getPropertyValue("label");
PropertyValue formatterProperty =
        stored.getPropertyValues().getPropertyValue("formatter");
RuntimeBeanReference ref =
        (RuntimeBeanReference) formatterProperty.getValue();

System.out.println(labelProperty.getValue()); // manual
System.out.println(ref.getBeanName());          // nameFormatter
~~~

**Snippet trích từ ví dụ đầy đủ**, cần imports cho `PropertyValue` và `RuntimeBeanReference`. Ở đây:

- `ref.getBeanName()` trả String **tên bean được tham chiếu**.
- Sau khi Spring khởi tạo `ManualGreeting`, `manual.formatter()` là **object của NameFormatter**.
- Việc chỉ nhìn bean definition không chứng minh setter đã chạy; dùng identity/behavior test để xác nhận instance thực tế.
- `RuntimeBeanReference` không phải service và không phải proxy để gọi method nghiệp vụ; nó là metadata cho container.

### Nếu dùng value nhầm chỗ thì sao?

~~~java
.addPropertyValue("formatter", "nameFormatter")
~~~

Đây là **sai ngữ nghĩa trong ví dụ**: người viết đang đưa String literal vào setter cần `NameFormatter`. Spring không mặc nhiên coi mọi String trông giống một bean name là lệnh truy xuất managed bean. Nếu bạn muốn **object**, hãy biểu đạt reference tường minh; nếu muốn **tên** để hiển thị/log, property nên có kiểu `String` và dùng value.

Đừng dựa vào một custom converter bí ẩn để giải quyết lỗi thiết kế này.

## 6. Dự án Spring Framework + Java 17+ chạy được

Dùng **Spring Framework 6.2.19**, JDK 17+ và Maven. Phiên bản cố định để ví dụ có thể tái lập; không hàm ý đó là bản Spring mới nhất. Không cần Spring Boot, HTTP server hay database.

Project:

~~~text
bean-reference-vs-value/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanReferenceVsValueDemo.java
~~~

### 6.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-reference-vs-value</artifactId>
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
                    <mainClass>demo.BeanReferenceVsValueDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven kéo theo các Spring dependencies cần thiết; `spring-context` không phải file JAR duy nhất có mặt trên classpath runtime. Nếu dùng `javac` trực tiếp, cần các Spring API JAR và transitive dependencies được Maven resolve.

### 6.2. File src/main/java/demo/BeanReferenceVsValueDemo.java

~~~java
package demo;

import java.util.Locale;
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

public final class BeanReferenceVsValueDemo {
    private BeanReferenceVsValueDemo() {}

    public interface NameFormatter {
        String normalize(String raw);
    }

    public static final class UppercaseFormatter implements NameFormatter {
        @Override
        public String normalize(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            return raw.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static final class GreetingService {
        private final NameFormatter formatter;
        private final String prefix;
        private final int maxChars;

        public GreetingService(
                NameFormatter formatter, String prefix, int maxChars) {
            this.formatter = Objects.requireNonNull(formatter);
            if (prefix == null || prefix.isBlank()) {
                throw new IllegalArgumentException("prefix required");
            }
            if (maxChars <= 0) {
                throw new IllegalArgumentException("maxChars must be positive");
            }
            this.prefix = prefix;
            this.maxChars = maxChars;
        }

        public NameFormatter formatter() {
            return formatter;
        }

        public String greet(String name) {
            String normalized = formatter.normalize(name);
            if (normalized.length() > maxChars) {
                throw new IllegalArgumentException("name too long");
            }
            return prefix + ", " + normalized + "!";
        }
    }

    public static final class ManualGreeting {
        private String label;
        private NameFormatter formatter;

        public ManualGreeting() {}

        public void setLabel(String label) {
            this.label = Objects.requireNonNull(label);
        }

        public void setFormatter(NameFormatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        public NameFormatter formatter() {
            return formatter;
        }

        public String greet(String rawName) {
            return label + ":" + formatter.normalize(rawName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public NameFormatter nameFormatter() {
            return new UppercaseFormatter();
        }

        @Bean
        public GreetingService greetingService(
                NameFormatter formatter, Environment env) {
            String prefix =
                    env.getRequiredProperty("greeting.prefix");
            int maxChars =
                    env.getRequiredProperty("greeting.maxChars", Integer.class);
            return new GreetingService(formatter, prefix, maxChars);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("lessonProperties",
                            Map.<String, Object>of(
                                    "greeting.prefix", "Xin chao",
                                    "greeting.maxChars", "8")));

            context.register(AppConfig.class);

            BeanDefinition manualDefinition = BeanDefinitionBuilder
                    .genericBeanDefinition(ManualGreeting.class)
                    .addPropertyValue("label", "manual")
                    .addPropertyReference("formatter", "nameFormatter")
                    .getBeanDefinition();

            context.registerBeanDefinition(
                    "manualGreeting", manualDefinition);
            context.refresh();

            NameFormatter formatter = context.getBean(NameFormatter.class);
            GreetingService service =
                    context.getBean(GreetingService.class);
            ManualGreeting manual = context.getBean(ManualGreeting.class);

            BeanDefinition actual = context.getBeanFactory()
                    .getBeanDefinition("manualGreeting");
            PropertyValue label = actual.getPropertyValues()
                    .getPropertyValue("label");
            PropertyValue propertyReference = actual.getPropertyValues()
                    .getPropertyValue("formatter");
            RuntimeBeanReference reference =
                    (RuntimeBeanReference) propertyReference.getValue();

            System.out.println("propertyPrefix=" +
                    context.getEnvironment().getProperty("greeting.prefix"));
            System.out.println("propertyMaxChars=" +
                    context.getEnvironment().getRequiredProperty(
                            "greeting.maxChars", Integer.class));
            System.out.println("literalMetadata=" + label.getValue());
            System.out.println("referenceMetadata=" +
                    reference.getBeanName());
            System.out.println("sameFormatter=" +
                    (service.formatter() == formatter
                     && manual.formatter() == formatter));
            System.out.println("serviceGreeting=" +
                    service.greet(" Lan "));
            System.out.println("manualGreeting=" +
                    manual.greet(" Lan "));
            System.out.println("manualSingleton=" +
                    (manual == context.getBean(ManualGreeting.class)));
        }
    }
}
~~~

**Phân tích các điểm then chốt:**

- `AppConfig` đăng ký bean `nameFormatter` và `greetingService`; factory method service nhận **NameFormatter object** cùng `Environment`.
- `MapPropertySource` dùng `Map.<String, Object>of(...)` (Java 17 hỗ trợ) để tạo hai property không nhạy cảm trong bộ nhớ. `addFirst(...)` ưu tiên dữ liệu demo trước những nguồn có key trùng, giúp kết quả tái lập được.
- Cấu hình factory đọc String `greeting.prefix` và chuyển `"8"` sang `Integer` để truyền vào constructor `int maxChars`. **Value không biến thành bean.**
- `ManualGreeting` có no-argument constructor cùng hai setter public để Spring có thể áp dụng property injection theo metadata.
- Bean `manualGreeting` được đăng ký **trước `refresh()`**, chứa một literal value và một bean reference có tên rõ ràng.
- Method `getPropertyValue("formatter")` trả metadata; cast sang `RuntimeBeanReference` được kiểm soát vì chính builder đặt `addPropertyReference(...)`.
- Ba nơi dùng formatter (context lookup, service field, manual field) trỏ cùng managed singleton trong context này.
- `GreetingService.greet(" Lan ")` chuẩn hóa thành `LAN` và in `Xin chao, LAN!`; `ManualGreeting.greet(...)` in `manual:LAN`.
- Khi rời `try (context)`, context được đóng. Demo không đăng ký callback hủy in stdout nên không có dòng shutdown tự phát.

### 6.3. Lệnh chạy Maven

Ở thư mục `bean-reference-vs-value`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Tám dòng stdout chính xác do phương thức main của ví dụ in khi chạy thành công:**

~~~text
propertyPrefix=Xin chao
propertyMaxChars=8
literalMetadata=manual
referenceMetadata=nameFormatter
sameFormatter=true
serviceGreeting=Xin chao, LAN!
manualGreeting=manual:LAN
manualSingleton=true
~~~

Các dòng thông tin JDK/Maven và log framework/build (nếu có) **không thuộc tám dòng do code demo tự in**. Không có random, phụ thuộc đồng hồ hoặc thứ tự iteration không ổn định trong những giá trị output trên.

### 6.4. Tự chạy bằng javac và java trên hai hệ điều hành

Vì source import Spring, trước tiên dùng Maven xuất classpath gồm các dependency:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanReferenceVsValueDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanReferenceVsValueDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanReferenceVsValueDemo.java
java -cp "out;$deps" demo.BeanReferenceVsValueDemo
~~~

Classpath entry separator là `:` trên Unix và `;` trên Windows. Hai cách chạy cùng class `demo.BeanReferenceVsValueDemo` và cho cùng tám dòng stdout ở mục 6.3.

## 7. Đọc kết quả: metadata khác object thực tế

| Dòng output | Điều được kiểm chứng |
| --- | --- |
| `propertyPrefix=Xin chao` | `Environment` cung cấp String từ property source |
| `propertyMaxChars=8` | Value cấu hình String đã được conversion sang kiểu số yêu cầu |
| `literalMetadata=manual` | `BeanDefinition` của ManualGreeting giữ literal value |
| `referenceMetadata=nameFormatter` | `RuntimeBeanReference` giữ **tên** bean đích |
| `sameFormatter=true` | Service và ManualGreeting thực tế giữ cùng bean formatter singleton |
| `serviceGreeting=Xin chao, LAN!` | Service kết hợp collaborator object với prefix/maxChars value |
| `manualGreeting=manual:LAN` | Setter nhận cả literal value và resolved bean object |
| `manualSingleton=true` | Cùng bean definition singleton trả lại cùng instance khi lookup |

**Không đồng nhất hai kiểm tra:** `referenceMetadata=nameFormatter` chỉ cho biết **metadata trỏ tới bean nào**; `sameFormatter=true` mới xác minh **object reference thực tế** sau wiring. Cả hai cần thiết khi debug dependency injection phức tạp.

**Đừng suy ra** reference luôn cùng identity ở mọi scope. Đây là singleton trong một context cụ thể. Prototype, scoped proxy hay các factory/proxy đặc biệt có thể thay đổi giả định về identity và thời điểm tạo.

## 8. @Qualifier chọn bean, @Value chọn dữ liệu

Có hai loại “chọn” khác nhau:

~~~java
@Qualifier("fastFormatter") NameFormatter formatter
~~~

Đó là một **injection point yêu cầu bean candidate** gắn với qualifier/tên `fastFormatter`. Nó không đọc property `fastFormatter` từ `Environment`.

~~~java
@Value("${greeting.prefix}") String prefix
~~~

Đó là một **injection point muốn giá trị cấu hình** ứng với key `greeting.prefix`, không tìm một Spring bean `String` tên prefix theo cùng quy tắc.

Nếu muốn nhiều beans cùng implement `NameFormatter`:

~~~java
@Bean("upperFormatter")
NameFormatter upperFormatter() {
    return new UppercaseFormatter();
}

@Bean("otherFormatter")
NameFormatter otherFormatter() {
    return new OtherFormatter();
}
~~~

**Đây là snippet minh họa, không chạy độc lập vì `OtherFormatter` chưa được định nghĩa.** Hai bean cùng type không sai; nhưng injection đơn trị `NameFormatter formatter` có thể bị mơ hồ nếu Spring không có cách chọn rõ. Sử dụng `@Qualifier` ở injection point, `@Primary` khi có một mặc định hợp lệ hoặc thiết kế lại để chỉ cần một candidate.

**Không sử dụng `@Qualifier` để sửa lỗi thiếu giá trị `greeting.prefix`.** Đó là lỗi property configuration, phải xem nguồn value. Và không dùng `@Value("${someBeanName}")` để thay cho dependency bean kiểu `NameFormatter` nếu mục đích là lấy managed object.

## 9. Các loại simple value và conversion thường gặp

Không phải chỉ có `String`:

| Giá trị cấu hình | Kiểu Java mong muốn | Kiểm tra |
| --- | --- | --- |
| `"Xin chao"` | `String` | Có rỗng/blank không? |
| `"8"` | `Integer`/`int` | Có chuyển kiểu và lớn hơn 0 không? |
| `"true"` | `Boolean`/`boolean` | Cú pháp hợp lệ và chính sách default |
| `"3000"` | `long` | Có ý nghĩa đơn vị ms rõ ràng không? |
| `"MAIL"` | Enum `Channel` nếu đã định nghĩa | Có đúng hằng enum không? |
| `"https://example.org"` | `URI` nếu conversion hỗ trợ | Có scheme/host hợp lệ không? |

Spring có các cơ chế property resolution và type conversion, nhưng **conversion thành công không đồng nghĩa giá trị đúng nghiệp vụ**. Ví dụ `maxChars=-5` vẫn có thể chuyển thành `int`; constructor phải từ chối vì vi phạm invariant.

Giá trị của `Environment` có thể đến từ:

- JVM system properties hoặc environment variables.
- `MapPropertySource`, file `.properties` được đăng ký bằng cơ chế phù hợp, hoặc các nguồn property do framework chủ quản thêm.
- Spring Boot có thêm cơ chế external configuration riêng, nhưng bài này chạy thuần Spring Framework; **không tự giả định file `application.properties` đã được nạp như Boot**.

**Thứ tự property sources quan trọng:** nguồn có độ ưu tiên cao hơn quyết định value nếu key trùng. Demo dùng `addFirst` để giữ kết quả ổn định, không phải quy định chung rằng mọi ứng dụng phải ưu tiên một map trong bộ nhớ.

### Missing value và optional value

Dùng `getRequiredProperty(key)` khi cấu hình bắt buộc phải có. Nếu thiếu key, container có thể thất bại khi tạo bean phụ thuộc — tốt hơn dùng chuỗi rỗng hoặc số 0 một cách âm thầm.

Khi một giá trị thực sự tùy chọn, có thể dùng default qua `Environment.getProperty(key, defaultValue)` hoặc property placeholder có fallback phù hợp. Default phải có ý nghĩa nghiệp vụ và được ghi rõ; **không dùng default để che cấu hình sai**.

Nếu secret là value (password/token), không hardcode hay in ra stdout/log. Secret không vì thế trở thành một Spring service bean; cơ chế lưu trữ, truyền và bảo vệ nó là vấn đề khác cần thiết kế riêng.

## 10. Scope, lifecycle và nơi nhận reference

| Cơ chế | Ảnh hưởng |
| --- | --- |
| Singleton mặc định | Các consumer cùng trỏ tới một bean definition thường dùng chung một object |
| Prototype | Mỗi lần Spring tạo/đáp ứng yêu cầu prototype có thể nhận instance mới |
| Prototype inject vào singleton | Thường được resolve một lần lúc singleton tạo, không tự đổi instance sau mỗi method call |
| `@Lazy` | Có thể trì hoãn instantiation; không xóa dependency logic |
| `ObjectProvider<NameFormatter>` | Cho phép truy xuất bean theo nhu cầu, phù hợp khi cần động |
| Alias bean | Một tên thay thế cho cùng bean, không tạo object độc lập chỉ vì alias |
| `new UppercaseFormatter()` ngoài container | Object Java bình thường, không tự nhận lifecycle như managed bean |

**Các giá trị cấu hình đơn giản thường được sao chép/đọc tại thời điểm khởi tạo.** Thay property source sau khi service singleton đã được tạo không tự động biến field `final String prefix` của service thành giá trị mới. Nếu muốn cập nhật runtime phải có cơ chế thiết kế rõ (reconfigure, tạo bean/context mới hoặc hợp đồng thay đổi phù hợp).

**Reference không giống value**, nhưng cả hai đều có thể dẫn đến vấn đề nếu được chia sẻ sai: singleton collaborator chứa state mutable phải thread-safe khi nhiều consumer gọi đồng thời; simple value cũng cần validation kiểu và giới hạn.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Không có bean `NameFormatter` tương thích hoặc tên reference sai | Đăng ký collaborator/kiểm tra bean name |
| `UnsatisfiedDependencyException` | Constructor/factory cần bean mà container không giải quyết được | Kiểm tra type, qualifier, scan và dependencies |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type nhưng không chọn được một | Dùng `@Qualifier`/`@Primary` hoặc thiết kế lại |
| `getRequiredProperty(...)` ném exception | Thiếu property key bắt buộc | Kiểm tra Environment, key và property sources |
| Property String không chuyển được sang int | Dữ liệu lỗi hoặc conversion không tương thích | Kiểm tra type/property value và validation |
| Bean được tạo nhưng constructor reject maxChars | Value có kiểu hợp lệ nhưng vi phạm invariant | Sửa giá trị cấu hình, không bỏ guard |
| `NotWritablePropertyException` | Setter JavaBean không tồn tại hoặc sai tên | Khai báo đúng `setFormatter(...)`/`setLabel(...)` |
| `addPropertyValue("formatter", "nameFormatter")` | Nhầm bean name String với object reference | Dùng `addPropertyReference(...)` |
| `@Value` nhận chuỗi placeholder chưa mong đợi | Nguồn property/resolver chưa được cấu hình phù hợp | Xem resolution của context, có key và syntax đúng |
| Context refresh PASS nhưng behavior sai | Bean/value được nối không đúng ý định hoặc logic lỗi | Kiểm tra identity và output, không chỉ startup |
| Bean singleton giữ cấu hình cũ | Thay property source sau khi singleton đã tạo | Có chiến lược refresh/reconfigure rõ |
| `javac` báo thiếu Spring API | Classpath không chứa Spring JAR và dependencies | Kiểm tra Maven pom, `-cp` hoặc file classpath |
| Dùng bean name làm password/config secret | Sai phân loại và bảo mật | Dùng nguồn value phù hợp, bảo vệ secrets |
| Reference tới một bean có lifecycle đã kết thúc | Sử dụng object sau khi context shutdown | Tôn trọng ownership/lifecycle context |

**Quy trình debug ngắn:** xác định tham số gây lỗi; hỏi đó là **giá trị** hay **collaborator bean**; kiểm tra key/property source hoặc type/name/qualifier tương ứng; đọc chain `Caused by`; xác minh metadata, sau đó kiểm tra object đã được nối trong runtime.

## 12. Hai tầng kiểm thử bổ trợ nhau

**Unit test Java thuần** xác minh logic không cần Spring:

~~~java
NameFormatter fake = name -> "TEST";
GreetingService service = new GreetingService(fake, "Hello", 10);
System.out.println(service.greet("anything")); // Hello, TEST!
~~~

Đây là **snippet**, có thể đặt trong method/class truy cập các kiểu của ví dụ; không phải một file runnable độc lập. Nó kiểm tra hành vi service và khả năng thay collaborator.

**Spring context smoke test** kiểm tra wiring thực:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("test", Map.<String, Object>of(
                    "greeting.prefix", "Test",
                    "greeting.maxChars", "10")));
    context.register(AppConfig.class);
    context.refresh();

    GreetingService service = context.getBean(GreetingService.class);
    NameFormatter formatter = context.getBean(NameFormatter.class);
    if (service.formatter() != formatter) {
        throw new IllegalStateException("wrong bean reference");
    }
}
~~~

Đây là **snippet trong ngữ cảnh có imports và các types đầy đủ**, không phải file thứ hai cần chạy. Kiểm tra dùng equality của reference với bean mong muốn. Với proxy/scope khác, cần điều chỉnh theo hợp đồng thực, không áp dụng identity test máy móc.

Các negative tests đáng thực hiện trong cấu hình riêng: thiếu property `greeting.prefix`, `greeting.maxChars=0`, thiếu bean `NameFormatter`, có hai formatter candidates không qualifier, hoặc dùng nhầm `addPropertyValue` thay reference. Khi một test cần lỗi, kiểm tra **loại lỗi/nguyên nhân** chứ không hardcode nguyên văn stack trace vì wrapper/message có thể thay đổi theo phiên bản.

Không dùng Java `assert` mặc định như điều kiện bắt buộc vì nó có thể bị tắt nếu JVM không có `-ea`; dùng assertion của test framework hoặc if/exception để fail rõ.

## 13. Bài tập có đáp án

**Bài 1.** Trong constructor `GreetingService(NameFormatter formatter, String prefix, int maxChars)`, tham số nào là bean collaborator?

**Đáp án:** `formatter`. Hai tham số còn lại là simple configuration values; chúng cần được cung cấp rõ ràng từ caller hoặc cơ chế cấu hình, không tự được resolve như một bean cùng tên.

**Bài 2.** Vì sao `@Qualifier("nameFormatter")` khác `@Value("${greeting.prefix}")`?

**Đáp án:** Qualifier ràng buộc việc **chọn bean candidate**; Value yêu cầu **resolve dữ liệu cấu hình** rồi truyền vào tham số. Không thay thế nhau.

**Bài 3.** `RuntimeBeanReference("nameFormatter")` có phải chính object `UppercaseFormatter` đang chạy không?

**Đáp án:** Không. Nó là metadata có tên đích. Container phải resolve khi wiring; object thật xuất hiện trong field của consumer.

**Bài 4.** Thêm một bean `String` tên `greeting.prefix` có tự làm factory method `Environment.getRequiredProperty("greeting.prefix")` đọc bean đó không?

**Đáp án:** Không. Property resolution đọc các **PropertySource**; bean registry là một cơ chế riêng. Muốn đọc value qua Environment, phải đăng ký property source đúng.

**Bài 5.** `addPropertyValue("formatter","nameFormatter")` có gửi object bean vào setter `setFormatter(NameFormatter)` không?

**Đáp án:** Không theo ngữ nghĩa định nghĩa trong bài. Đó là String literal; để inject bean object cần `addPropertyReference` hoặc cơ chế bean resolution phù hợp.

**Bài 6.** Property `greeting.maxChars` có giá trị `"-1"`. Chuyển thành Integer thành công thì cấu hình hợp lệ chưa?

**Đáp án:** Chưa. Constructor `GreetingService` cần maxChars dương và sẽ từ chối `-1`. Conversion và domain validation là hai bước khác nhau.

**Bài 7.** Vì sao `sameFormatter=true` trong demo?

**Đáp án:** Service và ManualGreeting cùng nhận bean singleton `nameFormatter` trong một context, và identity checks đối chiếu chính object đó. Không suy ra kết quả này cho mọi prototype hoặc scoped proxy.

**Bài 8.** Nếu môi trường đổi `greeting.prefix` sau khi singleton service đã tạo, field `prefix` có đổi ngay không?

**Đáp án:** Không tự động; field được truyền vào constructor lúc khởi tạo. Muốn thay runtime cần cơ chế cập nhật được thiết kế rõ ràng.

## 14. Checklist áp dụng

- [ ] Xác định mỗi constructor/factory argument là bean reference hay simple value.
- [ ] Không đánh đồng bean name String với managed bean object.
- [ ] Dùng factory method parameters cho collaborator và Environment/@Value cho data values.
- [ ] Không tự động autowire primitive/String như collaborator nếu chưa có chủ ý.
- [ ] Dùng `BeanDefinitionBuilder.addPropertyValue` cho literal.
- [ ] Dùng `addPropertyReference` cho tên bean cần resolve ra object.
- [ ] Phân biệt `RuntimeBeanReference` (metadata) với field đã inject (runtime).
- [ ] Cần setter/constructor phù hợp về tên, kiểu và khả năng ghi.
- [ ] Đăng ký bean definitions và property sources trước refresh trong demo.
- [ ] Dùng required value policy và validation hợp đồng cho dữ liệu cấu hình.
- [ ] Giải quyết nhiều bean candidates bằng qualifier/primary hợp lý.
- [ ] Kiểm tra scope/lifecycle nếu identity hoặc thời điểm tạo khác giả định.
- [ ] Không log secrets, không biến mọi value thành bean riêng.
- [ ] Chạy Java 17+ bằng Maven hoặc javac/java và đối chiếu đúng tám dòng stdout.
- [ ] Test riêng hành vi Java và wiring/configuration của Spring.

**Kết luận:** Một **bean reference** là quan hệ giữa các managed objects được Spring resolve theo tên/kiểu. Một **simple value** là dữ liệu được truyền vào bean, có thể là literal hoặc được resolve từ configuration. Mặc dù cả hai gặp nhau ở constructor/setter, chúng khác nhau ở **nguồn, metadata và cách container giải quyết**. Hiểu ranh giới này giúp DI rõ ràng, tránh nhầm chuỗi tên bean với collaborator và kiểm thử cấu hình chính xác.

### Tài liệu Spring chính thức

- [Dependency Injection and Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Using @Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html)
- [Using @Value](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/value-annotations.html)
- [Environment and PropertySource](https://docs.spring.io/spring-framework/reference/6.2/core/beans/environment.html)
