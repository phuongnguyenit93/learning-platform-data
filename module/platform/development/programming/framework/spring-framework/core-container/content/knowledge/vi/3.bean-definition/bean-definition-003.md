# Tên bean, bí danh và quy ước đặt tên trong Spring Core Container

## 1. Bean name dùng để nhận diện điều gì?

Trong Spring Framework, **bean** là đối tượng được IoC container quản lý dựa trên một đăng ký/cấu hình thích hợp. Mỗi đăng ký bean có một **tên chính (primary bean name)**, và có thể có thêm **bí danh (aliases)** để cùng tra cứu một bean ấy bằng các tên khác nhau.

Hãy phân biệt các thứ thường bị gọi chung là “tên”:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Java class | `TextFormatter`, `GreetingService` | Kiểu dữ liệu; có thể có nhiều bean cùng class |
| Bean name chính | `textFormatter` | Tên được dùng để đăng ký một bean definition |
| Bean alias | `mainFormatter`, `legacyFormatter` | Tên thay thế trỏ đến bean đã đăng ký; **không phải bean mới** |
| Tên phương thức `@Bean` | `textFormatter()` | Thông thường sinh tên mặc định nếu không chỉ định tên khác |
| Tên từ component scan | `orderHandler` | Tên sinh ra cho class `@Component` được scan |
| Qualifier | `@Qualifier("mainFormatter")` | Thông tin hỗ trợ **lựa chọn candidate** khi inject dependency; không phải lệnh tạo bean |

**Quy tắc quan trọng:** Các tên dùng làm định danh bean phải được quản lý nhất quán trong phạm vi container. Hai **bean definitions khác nhau** không được giả định sẽ cùng tồn tại độc lập dưới một tên chính. Nếu cùng tên xuất hiện trong cấu hình, hành vi có thể là conflict, bị chặn hoặc có cơ chế override theo môi trường/setting; **không được dựa vào “cấu hình khai báo sau sẽ luôn thắng”**.

Bí danh không tăng số lượng bean definitions và cũng không bắt singleton tạo thêm instance. Khi bean có scope `singleton`, `getBean("textFormatter")` và `getBean("mainFormatter")` cho cùng bean, nghĩa là cùng reference trong một context.

**Mục tiêu của bài:** biết cách đặt tên tường minh, đọc tên mặc định, tạo alias, dùng API quan sát/tra cứu, tránh tên va chạm và viết quy ước nhất quán trong dự án Spring Core Container không dùng Spring Boot.

## 2. Quy ước đặt tên: tên phản ánh vai trò, không phản ánh cú pháp

Tài liệu Spring khuyến nghị quy ước giống **tên biến instance trong Java**: bắt đầu bằng chữ thường, dùng **lowerCamelCase** và thể hiện vai trò.

| Tên bean | Đánh giá | Lý do |
| --- | --- | --- |
| `orderService` | Tốt | Ngắn, thể hiện trách nhiệm và dễ truy tìm |
| `paymentClient` | Tốt | Nhìn tên đoán được thành phần tích hợp |
| `primaryDataSource` | Tốt khi cần phân biệt | Cho biết đây là data source nào |
| `userRepository` | Tốt | Trùng ngôn ngữ nghiệp vụ rõ ràng |
| `bean1` / `obj` | Nên tránh | Không nói trách nhiệm hay hợp đồng |
| `serviceImpl` | Thường nên tránh | Tên mô tả kỹ thuật, ít thông tin về vai trò |
| `UserService` | Có thể tồn tại nhưng không nhất quán | Chữ cái đầu viết hoa không theo convention mặc định thông thường |
| `my-awesome-service` | Có thể là tên bean hợp lệ trong bối cảnh phù hợp | Dấu gạch ngang làm cú pháp reference phức tạp; không phải lựa chọn mặc định cho Java config |

Tên bean **không phải Java identifier**, nên không nên lẫn quy định cú pháp biến Java với khả năng chấp nhận tên của container. Tuy nhiên, việc dùng **lowerCamelCase ASCII**, tên ổn định và có nghĩa sẽ thuận lợi cho `@Qualifier`, cấu hình, log, bean name matching và code review.

**Tên phản ánh vai trò** chứ không buộc phải phản ánh implementation: `notificationSender` thường dễ giữ ổn định hơn `smtpNotificationSenderV2Impl` khi implementation thay đổi. Nếu thực sự có nhiều implementation đồng thời, hãy dùng tên phân biệt rõ (`emailNotificationSender`, `smsNotificationSender`) và một cơ chế chọn candidate nhất quán.

Không tạo alias chỉ để có nhiều tên “cho tiện”. Mỗi alias là một định danh công khai có thể trở thành dependency của cấu hình khác, khiến việc đổi tên về sau khó hơn.

## 3. Tên mặc định của `@Bean`, tên chỉ định và alias

Trong Java configuration, mặc định thông dụng là **lấy tên phương thức `@Bean`**:

~~~java
// Đoạn cú pháp minh họa, chưa phải file độc lập.
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    GreetingService greetingService(TextFormatter formatter) {
        return new GreetingService(formatter);
    }
}
~~~

Nếu dùng cơ chế sinh tên mặc định thông thường, bean trên có tên **`greetingService`**. Từ Spring Framework 7.0, có thể tùy biến `ConfigurationBeanNameGenerator`; do đó khi dự án chủ động thay đổi naming strategy, **đừng tuyệt đối hóa** quy tắc method name cho mọi tình huống.

### Đặt tên chính tường minh

~~~java
@Bean("auditRecorder")
AuditRecorder audit() {
    return new AuditRecorder();
}
~~~

Bean được đăng ký với tên chính **`auditRecorder`**, **không phải `audit`** chỉ vì phương thức Java có tên `audit()`. `@Bean("auditRecorder")` tương đương `@Bean(name = "auditRecorder")`.

### Một tên chính và nhiều alias

~~~java
@Bean(name = {"textFormatter", "mainFormatter", "legacyFormatter"})
TextFormatter textFormatter() {
    return new PlainTextFormatter();
}
~~~

Tên đầu tiên là tên đăng ký chính; các tên còn lại là **aliases cho cùng một bean**. Ở scope singleton mặc định, tra cứu bằng cả ba tên cho cùng đối tượng đã được quản lý.

**Alias khác bean riêng:** Ba tên trong array **không** tương đương với ba `@Bean` methods hay ba bean definitions. Nếu bạn muốn ba instance có scope/metadata khác nhau thì phải cấu hình các registrations thích hợp, không chỉ thêm alias.

Thực tế nên đặt tên tường minh khi có liên kết từ hệ khác, nhiều implementation cùng type, hoặc khi tên bean là một phần của hợp đồng cấu hình. Còn nếu mọi dependency được resolve theo type và không có yêu cầu định danh công khai, tên mặc định rõ ràng thường đã đủ.

## 4. Tên mặc định khi `@Component` được phát hiện bởi scanning

Spring có thể tự tìm và đăng ký các class mang stereotype như `@Component`, `@Service`, `@Repository`, `@Controller` **khi chúng nằm trong phạm vi component scan phù hợp**.

Với naming generator mặc định phổ biến `AnnotationBeanNameGenerator`:

| Class được scan | Tên bean mặc định | Tại sao |
| --- | --- | --- |
| `OrderHandler` | `orderHandler` | Viết thường chữ đầu của tên class |
| `PaymentClient` | `paymentClient` | Theo JavaBeans decapitalize |
| `URLParser` | `URLParser` | **Hai ký tự đầu viết hoa** nên Spring giữ nguyên chữ hoa theo quy tắc `Introspector.decapitalize` |
| `XMLGateway` | `XMLGateway` | Trường hợp chữ viết tắt tương tự |

Đây là **quy tắc mặc định**, không phải lời hứa với những project đã thay bean name generator. Khi class đã có tên định danh tường minh như:

~~~java
@Component("outboundGateway")
public class GatewayClient {
    // ...
}
~~~

bean sẽ sử dụng tên được chỉ định (nếu class được scan/đăng ký đúng). Việc thêm `@Component` **một mình** vào class không tự thêm bean vào mọi context: phải có `@ComponentScan`, `context.scan(...)` hoặc cơ chế cấu hình tương đương.

**Tránh bất ngờ với acronym:** Nếu team thường đặt class như `URLParser`, đừng suy luận chắc chắn tên sẽ là `uRLParser`. Chỉ định `@Component("urlParser")` nếu muốn một tên dễ đọc, ổn định và đúng naming convention của nhóm.

Trong Spring Framework 7, một số naming strategy có thể được tùy biến để sử dụng **fully qualified bean names**, nhất là khi nhiều component có cùng simple class name. Không tự ý chuyển toàn dự án sang một strategy khác nếu cấu hình cũ đang tham chiếu bean bằng tên.

## 5. Demo hoàn chỉnh Java 17: tên chính, alias và component names

Demo là **Spring Framework thuần**, không cần Spring Boot, HTTP hay database. Nó thực thi cùng lúc:
- `@Bean` có nhiều tên;
- `@Bean` có tên mặc định;
- `@Bean` có tên tường minh khác tên method;
- tên mặc định `@Component` sau khi scan;
- tra cứu theo tên, theo type và phép so reference;
- kiểm tra alias **không có bean definition riêng**.

### 5.1. Chuẩn bị Maven

Yêu cầu **JDK 17+**, **Maven 3.9+** và repository Maven Central/mirror cho lần tải thư viện đầu. Dùng Spring Framework **7.0.9** để khóa bản trong bài thực hành.

~~~text
bean-names-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── BeanNamesDemo.java
                └── scanned/
                    ├── OrderHandler.java
                    └── URLParser.java
~~~

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-names-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <configuration>
                    <mainClass>demo.BeanNamesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven kéo các dependencies cần thiết của `spring-context`, gồm nền bean factory và annotation configuration. Không dùng `javac` trần khi chưa thiết lập classpath cho những JAR Spring; `mvn compile` sử dụng `javac` và dependency classpath qua Maven.

### 5.2. Tệp `src/main/java/demo/BeanNamesDemo.java`

~~~java
package demo;

import java.util.Arrays;

import demo.scanned.OrderHandler;
import demo.scanned.URLParser;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

public final class BeanNamesDemo {
    private BeanNamesDemo() {
    }

    interface TextFormatter {
        String format(String name);
    }

    static final class PlainTextFormatter implements TextFormatter {
        @Override
        public String format(String name) {
            return "Hello, " + name + "!";
        }
    }

    static final class GreetingService {
        private final TextFormatter formatter;

        GreetingService(TextFormatter formatter) {
            this.formatter = formatter;
        }

        String greet(String name) {
            return formatter.format(name);
        }
    }

    static final class AuditRecorder {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackages = "demo.scanned")
    public static class AppConfig {

        @Bean(name = {
                "textFormatter", "mainFormatter", "legacyFormatter"
        })
        public TextFormatter textFormatter() {
            return new PlainTextFormatter();
        }

        @Bean
        public GreetingService greetingService(TextFormatter formatter) {
            return new GreetingService(formatter);
        }

        @Bean("auditRecorder")
        public AuditRecorder audit() {
            return new AuditRecorder();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            TextFormatter first =
                    context.getBean("textFormatter", TextFormatter.class);
            TextFormatter aliasA =
                    context.getBean("mainFormatter", TextFormatter.class);
            TextFormatter aliasB =
                    context.getBean("legacyFormatter", TextFormatter.class);

            String[] aliases = context.getAliases("textFormatter");
            Arrays.sort(aliases); // Đầu ra ổn định, không dựa vào thứ tự đăng ký.

            System.out.println("primary.exists="
                    + context.containsBeanDefinition("textFormatter"));
            System.out.println("alias.main.exists="
                    + context.containsBean("mainFormatter"));
            System.out.println("alias.legacy.exists="
                    + context.containsBean("legacyFormatter"));
            System.out.println("alias.hasDefinition="
                    + context.containsBeanDefinition("mainFormatter"));
            System.out.println("alias.list=" + String.join(",", aliases));
            System.out.println("aliases.sameInstance="
                    + (first == aliasA && first == aliasB));

            System.out.println("method.defaultName="
                    + context.containsBean("greetingService"));
            System.out.println("explicit.name="
                    + context.containsBean("auditRecorder"));
            System.out.println("old.method.name.isBean="
                    + context.containsBean("audit"));

            GreetingService greeting =
                    context.getBean(GreetingService.class);
            System.out.println("service.message=" + greeting.greet("Lan"));

            OrderHandler order = context.getBean(
                    "orderHandler", OrderHandler.class);
            URLParser url = context.getBean("URLParser", URLParser.class);

            System.out.println("component.camelCase="
                    + context.containsBean("orderHandler"));
            System.out.println("component.acronym="
                    + context.containsBean("URLParser"));
            System.out.println("component.classes="
                    + order.getClass().getSimpleName() + ","
                    + url.getClass().getSimpleName());
        }
    }
}
~~~

### 5.3. Tệp `src/main/java/demo/scanned/OrderHandler.java`

~~~java
package demo.scanned;

import org.springframework.stereotype.Component;

@Component
public class OrderHandler {
}
~~~

### 5.4. Tệp `src/main/java/demo/scanned/URLParser.java`

~~~java
package demo.scanned;

import org.springframework.stereotype.Component;

@Component
public class URLParser {
}
~~~

Hai class có `@Component` nằm đúng package được `@ComponentScan` chỉ định. Tên `URLParser` được giữ nguyên theo quy tắc default JavaBeans decapitalize; class `OrderHandler` thành `orderHandler`.

**Tại sao chương trình không có tên gây nhiễu?** Bean `textFormatter`, `greetingService`, `auditRecorder` khai báo bằng `@Bean` trong `AppConfig`, còn `OrderHandler` và `URLParser` là hai component từ scan package riêng. Chúng không trùng tên; các bean Spring nội bộ có thể được đăng ký thêm nhưng không ảnh hưởng các phép kiểm tra cụ thể này.

## 6. Lệnh chạy và expected stdout

Mở terminal tại thư mục `bean-names-demo` (chứa `pom.xml`):

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Ba lệnh đầu kiểm tra phiên bản môi trường, **không có output chung cố định**. Lệnh cuối biên dịch bằng Maven Compiler Plugin (release 17), sau đó chạy `demo.BeanNamesDemo`.

**13 dòng stdout do `System.out.println` trong chương trình tạo ra**, không tính các dòng do Java/Maven/logging backend có thể xuất thêm:

~~~text
primary.exists=true
alias.main.exists=true
alias.legacy.exists=true
alias.hasDefinition=false
alias.list=legacyFormatter,mainFormatter
aliases.sameInstance=true
method.defaultName=true
explicit.name=true
old.method.name.isBean=false
service.message=Hello, Lan!
component.camelCase=true
component.acronym=true
component.classes=OrderHandler,URLParser
~~~

### Giải thích các dòng quan trọng

1. `primary.exists=true` cho thấy `textFormatter` là tên của một bean definition đã được đăng ký.
2. Hai dòng `alias.*.exists=true` cho thấy tra cứu alias có hiệu lực trong context.
3. `alias.hasDefinition=false` là bằng chứng **alias không tự sở hữu bean definition thứ hai**.
4. `alias.list=...` là kết quả `getAliases("textFormatter")` được **sắp xếp** bằng `Arrays.sort` để có đầu ra ổn định.
5. `aliases.sameInstance=true` chứng minh ba tên trả **cùng object** trong singleton scope mặc định.
6. `method.defaultName=true` minh họa method `greetingService()` tạo bean với tên mặc định trong cấu hình này.
7. `explicit.name=true`, `old.method.name.isBean=false` chứng minh `@Bean("auditRecorder")` ghi đè tên mặc định `audit`; Spring không tự tạo alias `audit`.
8. `component.camelCase` và `component.acronym` chứng minh hai trường hợp tên bean component-scan mặc định.
9. `component.classes` xác nhận lookup theo tên **và** expected Java type đều trả đúng.

**Lưu ý về thời điểm tạo:** `containsBeanDefinition` kiểm tra metadata, không bắt buộc gọi constructor của bean. `getBean` trả bean instance; trong `ApplicationContext`, singleton không lazy thường đã được tạo trong lúc refresh. Alias không tạo thêm instance kể cả khi các tên được lookup nhiều lần.

## 7. Các API nên dùng để tra cứu và chẩn đoán

| API/biểu thức | Trả lời câu hỏi | Điểm cần tránh |
| --- | --- | --- |
| `context.containsBean("name")` | Container có nhận biết bean qua tên/alias đó không? | Không phân biệt tên chính và alias |
| `context.containsBeanDefinition("name")` | Có **bean definition cục bộ** được đăng ký dưới đúng tên đó không? | Với alias, thường `false`; không phải bằng chứng bean không truy cập được |
| `context.getBean("name")` | Tra bean theo tên, nhận `Object` | Phải cast hoặc chọn overload theo type |
| `context.getBean("name", Type.class)` | Tra theo tên và kiểm tra type | Sai type có thể ném exception |
| `context.getBean(Type.class)` | Tìm bean theo type | Có thể mơ hồ nếu nhiều candidate |
| `context.getAliases("name")` | Lấy các tên alias cho bean | Đừng giả định thứ tự aliases dùng làm business rule |
| `context.getBeanNamesForType(Type.class)` | Danh sách bean names tương thích type | Không dùng để khẳng định có bao nhiêu aliases |
| `context.getBeanDefinitionNames()` | Các tên bean definitions đã đăng ký | Có thể gồm bean framework nội bộ; không hardcode số lượng/thứ tự |

Trong ví dụ, `containsBean("mainFormatter")` là `true` còn `containsBeanDefinition("mainFormatter")` là `false`. **Hai kết quả hoàn toàn không mâu thuẫn**: cái đầu hỏi khả năng tra cứu theo alias, cái sau hỏi có definition dưới tên đó hay không.

`getBean(Type.class)` và `@Qualifier` giải quyết câu hỏi **cần bean nào** theo type/metadata; alias chỉ là một dạng tên dùng để tham chiếu. Đừng dùng alias để thay thế thiết kế rõ ràng của các dependency khi hệ thống có nhiều bean cùng interface.

### Lấy theo tên hay inject theo constructor?

Ưu tiên **constructor injection** ở service, với dependency type rõ ràng; dùng `@Qualifier` hoặc `@Primary` khi có nhiều candidate thích hợp. Tra `context.getBean("name")` hữu ích cho bootstrap, công cụ quản trị hay bài học về bean naming, nhưng rải lệnh đó khắp business code dễ biến thành **service locator** khó kiểm thử.

Alias có thể hữu ích cho chuyển tên từ một cấu hình cũ sang tên mới mà không nhân đôi bean, nhưng một alias quá rộng hoặc thiếu quy tắc dễ gây nhầm lẫn khi debug.

## 8. Alias ngoài method `@Bean`: XML và registration

Cấu hình XML vẫn có thể định nghĩa alias mà **không** tạo bean thứ hai:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="paymentClient" class="demo.PaymentClient"/>
    <alias name="paymentClient" alias="legacyPaymentClient"/>
</beans>
~~~

Đây là **snippet XML minh họa cú pháp**, không phải file dùng trực tiếp trong project mục 5. Nó giả định class `demo.PaymentClient` có constructor phù hợp. Sau khi XML được nạp, `legacyPaymentClient` là bí danh của bean `paymentClient`, chứ không tạo một bean definition mới.

Trong cấu hình programmatic, một `BeanDefinitionRegistry` phù hợp có thể cung cấp `registerAlias("beanName", "aliasName")` và các thao tác registry khác. Đây là API cấu hình nâng cao; chỉ đăng ký/đổi alias trong giai đoạn bootstrap phù hợp, **không** coi registry của context đã refresh như một bảng đổi tên tùy ý trong lúc ứng dụng phục vụ request.

**Phân biệt alias với tên khác cho một bean khác:** Nếu đăng ký hai bean definitions `primaryPaymentClient` và `backupPaymentClient` (cùng Java type), chúng có thể có hai instance riêng. Nếu thêm alias `legacyPaymentClient` cho `primaryPaymentClient`, alias ấy **không** biến backup thành cùng object.

## 9. Trùng tên, nhiều bean cùng type và cách chọn dependency

Có hai loại vấn đề khác nhau:

### A. Nhiều definitions muốn dùng **cùng tên**

Ví dụ hai `@Bean("paymentClient")` ở các nguồn cấu hình khác nhau. Với application context/bean factory cấu hình ngăn override, container có thể từ chối startup hoặc báo lỗi bean-definition-overriding. Trong cấu hình cho phép override, một registration có thể thay thế registration trước — nhưng việc phụ thuộc vào thứ tự nạp cấu hình rất dễ gây lỗi.

**Giải pháp tốt hơn:** đặt tên riêng có ý nghĩa, xóa trùng nguồn cấu hình, kiểm tra package scan và tập cấu hình import. Không dùng alias để che giấu hai bean definitions mâu thuẫn.

### B. Nhiều definitions **khác tên** nhưng cùng interface/type

Ví dụ có bean `stripePaymentClient` và `bankPaymentClient`, đều implement `PaymentClient`. Hai tên hoàn toàn hợp lệ, nhưng inject chỉ một `PaymentClient` theo type có thể bị mơ hồ.

Bạn có thể quy định lựa chọn bằng:
- `@Qualifier("stripePaymentClient")` tại điểm inject;
- `@Primary` trên candidate mặc định phù hợp;
- tham số factory method được cấu hình rõ, hoặc lựa chọn chủ động theo tên tại composition root;
- nếu cần cả hai, inject một collection/map of beans phù hợp và xử lý minh bạch.

**Lưu ý:** `@Qualifier` dùng metadata chọn candidate, không tự tạo bean hay alias mới. **`@Primary` cũng không đổi bean name chính**, chỉ ảnh hưởng thứ tự ưu tiên lựa chọn trong điều kiện resolve thích hợp.

Trong một ứng dụng, bạn có thể dùng **hai beans khác nhau cùng Java class** nhưng hai names, scopes hoặc dependency sets khác nhau. Vì vậy số tên, số definitions, số instances và số Java classes **không phải lúc nào cũng bằng nhau**.

## 10. Khi nào nên dùng alias và quy ước đặt tên ổn định?

### Tình huống alias hợp lý

- **Chuyển đổi tên bean:** một module cũ yêu cầu `legacyFormatter` trong khi module mới gọi `textFormatter`. Alias giữ tương thích trong giai đoạn chuyển đổi.
- **Tên địa phương theo subsystem:** một datasource dùng chung có thể được tham chiếu theo tên riêng từng subsystem mà vẫn là một bean thực.
- **Cấu hình tích hợp bên ngoài:** một framework extension point yêu cầu bean với tên đã được quy định; bạn có thể khai báo tên tường minh hoặc alias một bean hiện có khi phù hợp.

### Tình huống không nên thêm alias

- Chỉ để tránh chọn rõ implementation khi có nhiều beans cùng type.
- Để tạo cảm giác có nhiều instances hoặc nhiều cấu hình khác nhau.
- Để che việc hai class/component scan mặc định va chạm tên.
- Để “tạo một bean thử nghiệm mới” nhưng chỉ thêm alias của bean production.

### Quy ước đội nhóm đề xuất

1. Mặc định **lowerCamelCase**, đặt theo vai trò nghiệp vụ.
2. Nếu contract/cấu hình ngoài tham chiếu bean bằng tên, hãy **khai báo tên tường minh** để tránh bất ngờ khi đổi tên class/method.
3. Nếu dùng tên mặc định, ghi nhận naming generator thực tế của project, nhất là các class viết tắt kiểu `URLParser`.
4. Chỉ thêm alias khi có nhu cầu tương thích hoặc tích hợp cụ thể; ghi lại alias nào là legacy và kế hoạch bỏ nó.
5. Không trộn lẫn các quy tắc đặt tên của Java class, file, Maven artifact và bean registration.
6. Tránh đổi tên chính/alias tùy tiện sau khi ứng dụng đã cấu hình xong hoặc trong runtime; cân nhắc ảnh hưởng tới injection và external references.
7. Tại code review, kiểm tra `@ComponentScan`, `@Bean`, `@Qualifier` và danh sách bean names khi xảy ra conflict.

## 11. Bài tập Java 17 để tự kiểm chứng

Hãy thực hiện **từng thay đổi độc lập** trên bản sao và khôi phục source gốc trước khi so expected stdout ở mục 6.

1. **Bỏ một alias:** xóa `"legacyFormatter"` khỏi array `@Bean(name=...)`. Dự đoán `containsBean("legacyFormatter")` và `getAliases("textFormatter")`.
2. **Đổi tên chính:** đổi `"textFormatter"` thành `"primaryFormatter"` và vẫn giữ `"mainFormatter"`; xác định phải sửa những lệnh lookup nào.
3. **Đổi method nhưng giữ tên bean:** đổi tên Java method `textFormatter()` thành `createFormatter()` nhưng giữ `@Bean(name=...)`. Bean name có thay đổi không?
4. **Đặt tên component tường minh:** đổi `@Component` của `URLParser` thành `@Component("urlParser")`, sửa code lookup, giải thích thay đổi default acronym behavior.
5. **Đổi package scan:** thay `@ComponentScan(basePackages="demo.scanned")` bằng package không chứa hai component; dự đoán `getBean("orderHandler", OrderHandler.class)` có thành công không.
6. **Tạo bean thứ hai cùng type:** thêm `@Bean("backupFormatter") TextFormatter ...` rồi gọi `getBean(TextFormatter.class)`. Quan sát ambiguity khi không có chính sách chọn; thực nghiệm `@Primary` hoặc `@Qualifier`.
7. **Kiểm tra alias/definition:** in `getBeanDefinitionNames()` và `getAliases("textFormatter")`. Vì sao không được coi aliases là additional bean definitions?
8. **So identity:** dùng `==` giữa hai lần `getBean` qua alias; giải thích kết quả nếu bean đổi sang scope prototype (lúc đó mỗi lookup có thể tạo instance mới).
9. **Hai contexts:** khởi tạo hai context cùng `AppConfig`, so `getBean("textFormatter")` của hai contexts. Vì sao singleton không có nghĩa chia sẻ object trên toàn JVM?
10. **Khắc phục va chạm:** tạo thêm một component class có cùng simple name `OrderHandler` trong package khác, cho cả hai vào cùng scan; xem vấn đề naming generator và chọn cách đặt tên tường minh phù hợp.

### Checklist hoàn thành bài

- [ ] Phân biệt bean name chính, alias, Java class name và method name.
- [ ] Nêu được quy ước lowerCamelCase và ngoại lệ `URLParser`.
- [ ] Đọc đúng `@Bean(name={"primary","aliasA","aliasB"})`.
- [ ] Giải thích vì sao alias không tạo thêm bean definition hoặc singleton instance.
- [ ] Phân biệt `containsBean` với `containsBeanDefinition`.
- [ ] Dùng được `getAliases`, `getBean(name,Type.class)` và lookup theo type.
- [ ] Biết xử lý nhiều bean cùng type bằng `@Qualifier`/`@Primary`, không nhầm với tên trùng.
- [ ] Dự đoán chính xác 13 dòng stdout Java17 của chương trình nguyên bản.

## 12. Tóm tắt và tài liệu chính thức

**Ghi nhớ:** Bean name là định danh trong IoC container, còn alias là **tên phụ dẫn tới cùng đăng ký**. Một `@Bean` có thể công khai nhiều tên mà **không** tạo thêm definitions; component scan dùng một quy tắc sinh tên mặc định có thể khác trường hợp viết tắt hoa. Đặt tên có nghĩa, nhất quán sẽ giảm lỗi wiring và xung đột khi dự án lớn lên.

Tài liệu chính thức:
- [Spring – Bean Overview: Naming Beans and Aliasing](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring – Using @Bean: Customizing Bean Naming and Aliasing](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring – Fine-tuning Annotation-based Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Kết luận:** Khi nhìn một cấu hình Spring, hãy hỏi **bean definition có tên chính gì, aliases nào, type nào và scope nào** trước khi suy luận số object được tạo. Hiểu rõ những lớp nhận diện ấy là nền tảng để dùng `@Bean`, component scanning, `@Qualifier` và debug Core Container chính xác.