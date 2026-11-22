# Kiểu lớp, hàm khởi tạo và phương thức nhà máy khi định nghĩa bean trong Spring

## 1. Một bean được tạo từ những thông tin nào?

Trong Spring Core Container, **bean definition** là metadata cho biết container phải tạo và quản lý một bean như thế nào. Một bean definition thường gắn với **lớp triển khai**, **cách tạo đối tượng**, **các dependency/đối số cần cung cấp**, **scope** và **cấu hình vòng đời**. Bài này tập trung vào ba cách xác định *cơ chế tạo*:

1. **Bean class + constructor:** Spring trực tiếp gọi constructor của một class, đồng thời giải quyết những tham số constructor cần inject.
2. **Static factory method:** Spring gọi một phương thức `static` có nhiệm vụ trả về object cần đăng ký làm bean.
3. **Instance factory method:** Spring gọi một phương thức trên **một object factory đã có** để tạo object cần đăng ký làm bean.

Với Java configuration, `@Bean` thường là cách biểu diễn factory method trực quan. Với bean definition kiểu XML, có các thuộc tính `class`, `factory-method` và `factory-bean` diễn đạt những đường tạo tương ứng. Chọn đúng cơ chế giúp quản lý cách tạo, cấu hình và vòng đời object mà không rải `new` vào nhiều lớp nghiệp vụ.

~~~text
                    Bean definition / cấu hình
                              |
         +--------------------+--------------------+
         |                    |                    |
       class              static factory       instance factory
         |                    |                    |
    constructor()       SomeFactory.create()   factoryBean.create()
         |                    |                    |
         +--------------------+--------------------+
                              |
                        bean instance
                              |
                scope / dependency / lifecycle
~~~

Sơ đồ thể hiện **ba con đường tạo bean**, không có nghĩa mỗi bean phải dùng cả ba. Spring vẫn có thể áp dụng post-processors, proxy và lifecycle callbacks tùy những tính năng đã được cấu hình.

## 2. Phân biệt bean class, Java object và bean definition

Ví dụ class thuần Java:

~~~java
public final class GreetingService {
    private final Formatter formatter;

    public GreetingService(Formatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

Đây là **đoạn minh họa** chưa độc lập vì interface `Formatter` không được định nghĩa ở đây; ví dụ runnable đầy đủ nằm ở mục 6.

- **Bean class** là kiểu class mà Spring có thể dùng để tạo object, như `GreetingService`. Nó không tự trở thành bean chỉ vì class có mặt trên classpath.
- **Bean definition** là thông tin đăng ký với container để Spring biết tạo object đó bằng constructor hay factory và cách nối các dependency.
- **Bean instance** là object thực tế mà `getBean(...)` trả về. Object runtime có thể là proxy nếu kích hoạt một số cơ chế mở rộng.
- **Bean name** là định danh đăng ký, ví dụ `greetingService`; **bean type** là kiểu Java dùng cho kiểm tra và autowiring. Tên bean và tên class không nhất thiết giống nhau.

`new GreetingService(formatter)` tự tạo object Java, nhưng object đó **không tự trở thành Spring-managed bean** nếu bạn không đăng ký instance hoặc định nghĩa tương ứng vào container.

Bean metadata cũng có thể chứa `scope`, `lazy-init`, `init-method`, `destroy-method` hoặc nguồn cấu hình tương đương. Những thông tin đó **không thay thế** constructor/factory method mà bổ sung ngữ cảnh container quản lý object.

## 3. Cách 1 — Spring tạo trực tiếp bằng constructor

### 3.1. Constructor injection

Giả sử đã có bean `Formatter` và bean definition cho `GreetingService`. Với một constructor:

~~~java
public GreetingService(Formatter formatter) {
    this.formatter = java.util.Objects.requireNonNull(formatter);
}
~~~

Spring có thể giải quyết tham số kiểu `Formatter` rồi tạo `GreetingService` bằng constructor đó. Trong một class có **chỉ một constructor**, từ Spring Framework 4.3 trở đi thường không cần gắn `@Autowired` lên constructor để constructor injection hoạt động.

Có thể tạo bean definition bằng nhiều đường:

- `@Component` + component scanning: Spring phát hiện class và tạo bean từ constructor thích hợp.
- `AnnotationConfigApplicationContext.register(GreetingService.class)`: đăng ký class rõ ràng trước khi refresh; không cần dựa vào việc quét package.
- XML `<bean class="...">` với cấu hình constructor arguments.
- API `BeanDefinitionRegistry` và `RootBeanDefinition`/`BeanDefinitionBuilder` ở tầng thấp.

**Quan trọng:** constructor injection là việc **cung cấp dependency cho constructor**. Nó có thể được dùng dù không có Spring; Spring chỉ đảm nhiệm khâu chọn/cấp argument và gọi constructor thay composition root thủ công.

### 3.2. Constructor mặc định và nhiều constructor

Một class không nhất thiết phải có constructor không tham số. Spring có thể gọi constructor có tham số khi có cách xác định constructor và giải quyết dependency phù hợp. Tuy nhiên:

- Nếu class có **nhiều constructor**, quy tắc chọn có thể cần `@Autowired`, cấu hình bean definition rõ ràng hoặc một phương án thiết kế dễ hiểu hơn.
- Nếu thiếu bean dependency, hoặc tồn tại nhiều ứng viên mà không phân giải được, Spring có thể báo lỗi ngay khi tạo bean.
- Nếu constructor ném exception, bean creation thất bại và thường được bọc trong chuỗi lỗi liên quan tới `BeanCreationException`.
- Constructor `private`, class `abstract`, kiểu không thể khởi tạo và quyền truy cập có những quy tắc/giới hạn riêng; đừng suy rằng mọi class đều được container tạo như nhau.
- `@Autowired(required = false)` hoặc các overload constructor không nên trở thành cách che dependency bắt buộc; một constructor rõ ràng thường dễ bảo trì hơn.

**Không trộn trách nhiệm:** constructor nên thiết lập invariant và nhận dependency; tránh thực hiện I/O phức tạp hoặc tác dụng phụ kéo dài trong bước khởi tạo bean. Một singleton eager có thể được khởi tạo khi context refresh, trước cả khi method nghiệp vụ được gọi.

### 3.3. XML bean definition dựa trên constructor

Đoạn XML **minh họa cấu trúc**, với `demo.GreetingService` và `demo.Formatter` giả định là kiểu hợp lệ trong một project khác:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="formatter" class="demo.SimpleFormatter"/>

    <bean id="greetingService" class="demo.GreetingService">
        <constructor-arg ref="formatter"/>
    </bean>
</beans>
~~~

`class` ở đây chỉ class được Spring tạo; `constructor-arg ref` biểu thị dependency là bean `formatter`. XML không phải lựa chọn bắt buộc: `@Configuration`, `@Bean` hoặc component registration có thể thể hiện cùng ý đồ bằng Java.

## 4. Cách 2 — static factory method

Đôi khi một class cần được tạo qua phương thức `static` thay vì gọi constructor trực tiếp. Những tình huống phổ biến:

- Class có constructor ẩn và public static factory, ví dụ `SomeClient.create(config)`.
- Phương thức tạo cần chọn một trong nhiều implementation nhưng trả về một contract ổn định.
- Ta muốn dùng factory API của thư viện mà không đổi mã thư viện.

Ví dụ Java thuần:

~~~java
public final class Formatter {
    private final String prefix;

    private Formatter(String prefix) {
        this.prefix = prefix;
    }

    public static Formatter of(String prefix) {
        return new Formatter(prefix);
    }

    public String format(String name) {
        return prefix + " " + name;
    }
}
~~~

Đây là **đoạn minh họa**. Với cách tạo thông thường của mã Java, gọi `Formatter.of("Hello")` thay vì `new Formatter("Hello")`. Nếu dùng XML bean definition tương ứng:

~~~xml
<bean id="formatter"
      class="demo.Formatter"
      factory-method="of">
    <constructor-arg value="Hello"/>
</bean>
~~~

Ở cấu hình này, `class` là **class chứa static factory method**, `factory-method` là tên phương thức tạo, và `constructor-arg` có thể được dùng để truyền argument cho phương thức factory. Object trả về mới là bean được quản lý theo bean definition này.

### Static `@Bean` trong Java configuration

Spring cho phép khai báo phương thức `@Bean` dạng `static`:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    public static Formatter formatter() {
        return Formatter.of("Hello");
    }
}
~~~

Đây là **ví dụ minh họa** dùng `Formatter` ở đoạn trên; trong chương trình runnable mục 6 sẽ có phiên bản đầy đủ. Phương thức `@Bean static` thuộc class cấu hình, không cần một instance `AppConfig` để được gọi như phương thức Java. Spring vẫn đăng ký object **được trả về** thành bean.

**Đừng nhầm hai việc:**

1. **Factory method của bean definition XML:** dùng `class + factory-method` chỉ tới static method của class tạo.
2. **Static method có `@Bean`:** Spring đọc annotation trong `@Configuration` và sử dụng phương thức đó làm bean factory method.

Chúng thể hiện ý tưởng factory nhưng là **hai kiểu khai báo cấu hình** khác nhau. Một `@Bean` method có thể trực tiếp gọi static factory method của thư viện, như `return Formatter.of("Hello")`.

## 5. Cách 3 — instance factory method

Thay vì phương thức static, ta có một object factory đã được tạo:

~~~java
public final class FormatterFactory {
    private final String prefix;

    public FormatterFactory(String prefix) {
        this.prefix = prefix;
    }

    public Formatter createFormatter() {
        return Formatter.of(prefix);
    }
}
~~~

Đoạn này **minh họa**, giả định `Formatter` đã có. Lúc này phương thức tạo phụ thuộc vào **trạng thái/configuration của factory instance**.

Ví dụ XML:

~~~xml
<bean id="formatterFactory" class="demo.FormatterFactory">
    <constructor-arg value="Hello"/>
</bean>

<bean id="formatter"
      factory-bean="formatterFactory"
      factory-method="createFormatter"/>
~~~

Ý nghĩa:

1. Spring tạo `formatterFactory` như một bean riêng.
2. Khi cần `formatter`, Spring gọi phương thức `createFormatter()` **trên bean factory đó**.
3. Object mà factory trả về được quản lý dưới bean name `formatter`.

Trong lối khai báo instance factory này, **`factory-bean` trỏ tới *tên bean chứa factory instance***, khác với `class` của static factory. Không nên viết `factory-bean="demo.FormatterFactory"` nếu không có bean mang tên chuỗi đó.

### Instance method có `@Bean`

Trong Java configuration, cách thường gặp hơn là:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    Formatter formatter() {
        return Formatter.of("Hello");
    }
}
~~~

Method `formatter()` là **instance factory method của class cấu hình**. Spring quản lý việc gọi nó và đăng ký object trả về. Đây không giống việc ta tự gắn tên phương thức trong XML, nhưng cùng đóng vai trò tạo bean.

Một `@Bean` method cũng có thể nhận dependency là parameter:

~~~java
@Bean
GreetingService greetingService(Formatter formatter) {
    return new GreetingService(formatter);
}
~~~

Spring giải quyết bean `Formatter` rồi truyền vào **tham số factory method**. Cách này cũng là dependency injection, dù việc gọi constructor diễn ra bên trong thân `@Bean`.

### So sánh ba cách

| Cách tạo bean | Cấu hình xác định gì? | Ai chạy lệnh tạo? |
| --- | --- | --- |
| Constructor trực tiếp | Bean class + constructor arguments | Container chọn/gọi constructor |
| Static factory | Class có static method + method/arguments | Container gọi static factory |
| Instance factory | Factory bean có sẵn + instance method/arguments | Container lấy factory bean, gọi method |
| `@Bean` Java method | Phương thức trong configuration, có thể static hoặc instance | Container gọi `@Bean` method, quản lý giá trị trả về |

Không có cơ chế nào “đúng” cho mọi bean. **Hãy chọn cách tạo đơn giản nhất phù hợp API class cần sử dụng.**

## 6. Chương trình Spring Framework 6.2 / Java 17 chạy hoàn chỉnh

Ví dụ duy nhất này cố ý sử dụng **cả ba con đường** trong một context:

- `GreetingService` được Spring tạo trực tiếp qua **constructor**.
- `Phrase` được cung cấp qua **static `@Bean` factory method**.
- `GreetingFormatter` được cung cấp qua **instance `@Bean` factory method**, bên trong có gọi một static factory Java bình thường.

Không có Spring Boot, web server, database hoặc AOP. Lệnh chạy dùng Maven để tải `spring-context`.

### 6.1. Cấu trúc thư mục

~~~text
bean-creation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanCreationDemo.java
~~~

Tạo file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>bean-creation-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.BeanCreationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File Java đầy đủ

Tạo `src/main/java/demo/BeanCreationDemo.java`:

~~~java
package demo;

import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanCreationDemo {
    private BeanCreationDemo() {
    }

    public record Phrase(String prefix) {
        public Phrase {
            Objects.requireNonNull(prefix, "prefix");
            if (prefix.isBlank()) {
                throw new IllegalArgumentException("prefix must not be blank");
            }
        }
    }

    public static final class GreetingFormatter {
        private final Phrase phrase;

        private GreetingFormatter(Phrase phrase) {
            this.phrase = Objects.requireNonNull(phrase, "phrase");
        }

        // Static factory của Java: constructor ẩn với bên gọi.
        public static GreetingFormatter create(Phrase phrase) {
            return new GreetingFormatter(phrase);
        }

        public String format(String name) {
            Objects.requireNonNull(name, "name");
            return phrase.prefix() + " " + name;
        }
    }

    public static final class GreetingService {
        private final GreetingFormatter formatter;

        // Chỉ một constructor: Spring có thể inject dependency này.
        public GreetingService(GreetingFormatter formatter) {
            this.formatter = Objects.requireNonNull(formatter, "formatter");
        }

        public String greet(String name) {
            return formatter.format(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        // @Bean static factory method.
        @Bean
        public static Phrase phrase() {
            return new Phrase("Hello");
        }

        // @Bean instance factory method, có tham số được Spring inject.
        @Bean
        public GreetingFormatter greetingFormatter(Phrase phrase) {
            return GreetingFormatter.create(phrase);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Đăng ký class thông thường để Spring tạo qua constructor.
            context.register(AppConfig.class, GreetingService.class);
            context.refresh();

            GreetingService service = context.getBean(GreetingService.class);
            System.out.println("MESSAGE " + service.greet("Lan"));
            System.out.println("PHRASE "
                    + context.getBean(Phrase.class).prefix());
            System.out.println("FACTORY "
                    + context.getBean(GreetingFormatter.class).format("Mai"));
            System.out.println("SINGLETON "
                    + (service == context.getBean(GreetingService.class)));
        }
    }
}
~~~

### 6.3. Lệnh chạy và stdout

Từ thư mục `bean-creation-demo` có `pom.xml`, yêu cầu JDK 17+ và Maven:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Các dòng stdout do `BeanCreationDemo` in chính xác theo thứ tự:**

~~~text
MESSAGE Hello Lan
PHRASE Hello
FACTORY Hello Mai
SINGLETON true
~~~

`mvn -version` và Maven/plugin có thể in thêm thông tin môi trường hoặc log. Bốn dòng trên là những dòng do `System.out.println` trong code demo tạo ra; không cam kết toàn bộ terminal luôn chỉ có bốn dòng.

### 6.4. Theo dõi đường tạo từng bean

1. `context.register(AppConfig.class, GreetingService.class)` đăng ký hai class trước khi gọi `refresh()`. Không cần component scan.
2. Spring đọc `@Configuration` và thấy hai `@Bean` methods.
3. Bean `phrase` được tạo bằng phương thức `static Phrase phrase()` trả một record `Phrase("Hello")`.
4. Bean `greetingFormatter` được tạo bằng phương thức **instance** `AppConfig.greetingFormatter(Phrase)`. Spring truyền `Phrase` đã đăng ký vào tham số, rồi method gọi `GreetingFormatter.create(phrase)`.
5. Bean `GreetingService` được tạo bằng **constructor injection**, vì đã đăng ký trực tiếp class và class có một constructor nhận `GreetingFormatter`.
6. `getBean(GreetingService.class)` trả service. `greet("Lan")` gọi formatter đã inject và tạo `Hello Lan`.
7. `getBean(Phrase.class)` và `getBean(GreetingFormatter.class)` đều tra những bean đã được tạo; lệnh in thứ ba minh họa factory trả về đúng kiểu sản phẩm.
8. Vì scope mặc định là `singleton` theo từng context, lần lookup thứ hai cho `GreetingService` trả đúng instance, in `SINGLETON true`.
9. `try-with-resources` đóng context; các callback destroy phù hợp của managed beans được Spring xử lý.

Đây là lý do ví dụ có thể phân biệt **cơ chế tạo** mà không dựa vào thứ tự println trong constructor. Đầu ra business được in sau khi context refresh, nên không phụ thuộc thứ tự tạo các singleton trong quá trình khởi động.

### Tại sao `GreetingService` không cần `@Component`?

`context.register(GreetingService.class)` đăng ký trực tiếp class với `AnnotationConfigApplicationContext`. Class đã là một bean candidate rõ ràng, dù không có `@Component`. Nếu bạn bỏ lời gọi đăng ký đó và không dùng một cơ chế đăng ký khác, Spring sẽ không tự tạo bean `GreetingService` chỉ vì class có trong project.

Một phương án khác là đánh dấu `@Component` rồi bật component scan cho package thích hợp, hoặc thêm một `@Bean GreetingService service(GreetingFormatter formatter)`. Không nên dùng cả ba cách đăng ký cùng một đối tượng một cách vô ý, vì có thể tạo trùng bean/nhầm tên.

## 7. Điểm dễ nhầm: `@Bean` factory method khác `FactoryBean<T>`

Hai khái niệm có tên gần giống nhưng không đồng nhất.

### `@Bean`

Đây là annotation đánh dấu một phương thức factory trong configuration. Spring gọi method và quản lý object mà method trả về:

~~~java
@Bean
GreetingFormatter greetingFormatter(Phrase phrase) {
    return GreetingFormatter.create(phrase);
}
~~~

Mã là trích đoạn từ chương trình mục 6. Bản thân `@Bean` **không yêu cầu** class sản phẩm phải implement một giao diện Spring đặc biệt.

### `FactoryBean<T>`

`org.springframework.beans.factory.FactoryBean<T>` là một **SPI chuyên biệt**. Một bean implement `FactoryBean<T>` có thể cung cấp *product bean* qua `getObject()`, đồng thời thông báo `getObjectType()` và `isSingleton()`.

Ví dụ **minh họa ý tưởng, không phải chương trình độc lập**:

~~~java
class FormatterFactoryBean
        implements org.springframework.beans.factory.FactoryBean<GreetingFormatter> {

    public GreetingFormatter getObject() {
        return GreetingFormatter.create(new Phrase("Hello"));
    }

    public Class<?> getObjectType() {
        return GreetingFormatter.class;
    }

    public boolean isSingleton() {
        return true;
    }
}
~~~

Nếu một Spring bean được đăng ký là `FactoryBean` với tên `formatterFactoryBean`, thì:

- `getBean("formatterFactoryBean")` thông thường trả **product** của factory.
- `getBean("&formatterFactoryBean")` lấy **chính factory bean**.

Tiền tố `&` là quy ước dereference của Spring `FactoryBean`. Nó **không** có liên quan tới toán tử bitwise Java trong trường hợp này.

Đặc biệt, một **instance factory method** như `factoryBean.createFormatter()` trong XML **không bắt buộc** object factory phải implement `FactoryBean<T>`. Đó là hai API/mẫu cấu hình khác nhau.

**Khi nào cần `FactoryBean`?** Khi bạn viết integration/factory logic có tính framework và muốn Spring quản lý một đối tượng trung gian tạo product theo SPI. Với ứng dụng bình thường, `@Bean` hoặc constructor injection thường đủ và dễ hiểu hơn.

## 8. Return type, bean name và phụ thuộc khi tạo

### Bean type không nhất thiết là kiểu cụ thể

~~~java
@Bean
MessageSender sender() {
    return new ConsoleSender();
}
~~~

Đây là ví dụ **minh họa**, chưa định nghĩa `MessageSender` và `ConsoleSender`. Phương thức `@Bean` trả về interface `MessageSender` nhưng instance có thể là `ConsoleSender`. Code sử dụng nên tra/inject theo **hợp đồng** khi phù hợp.

Khi lựa chọn bean theo type, Spring dựa vào metadata từ bean definition/factory method và có thể cần tạo object để xác định type cụ thể. Đừng mặc định lookup trước khởi tạo luôn biết mọi subtype implementation bằng cách phản chiếu return type cụ thể.

### Bean name

Mặc định với `@Bean`, tên bean là tên method: `phrase`, `greetingFormatter`. Với class đăng ký trực tiếp, Spring đặt tên theo quy tắc của đăng ký component; mã demo không dựa vào bean name mà lookup theo type.

### Đối số constructor/factory method

Tương tự constructor injection, Spring có thể cấp tham số cho `@Bean` factory method từ những bean khác:

~~~java
@Bean
GreetingFormatter greetingFormatter(Phrase phrase) {
    return GreetingFormatter.create(phrase);
}
~~~

Ở đây `Phrase` phải có một bean phù hợp. Nếu không có, tạo bean `GreetingFormatter` thất bại. Nếu có hai `Phrase` khác nhau và không có cơ chế phân giải hợp lệ, injection có thể mơ hồ.

Nên khai báo dependency bằng tham số thay vì tự dùng `ApplicationContext.getBean(...)` tràn lan trong body factory method. Trong `@Configuration(proxyBeanMethods = false)`, **gọi trực tiếp một `@Bean` method khác như một lời gọi Java thông thường không nhất thiết tham chiếu tới managed singleton**, nên tham số method injection là lựa chọn rõ ràng.

## 9. Scope, vòng đời và lỗi lúc khởi tạo

- **`singleton` (mặc định):** một bean instance theo bean definition trong **một container**, thường được khởi tạo khi `ApplicationContext.refresh()` nếu không lazy. Factory method thường được gọi trong lúc tạo instance đó, không phải mỗi lần lookup.
- **`prototype`:** thường tạo instance mới mỗi khi container nhận yêu cầu tạo bean; factory method hoặc constructor có thể được gọi nhiều lần theo số lần yêu cầu.
- **`@Lazy`:** có thể hoãn việc tạo bean. Nếu bean lazy trở thành dependency bắt buộc của một singleton eager khác, thời điểm khởi tạo vẫn tùy cấu hình injection.
- **Lifecycle:** container có thể chạy initialization/destruction callbacks và bean post-processors theo quy tắc. Không thể suy rằng mọi object do factory trả về đều nhận đầy đủ mọi tiện ích nếu object đó không được quản lý như bean.
- **Proxy:** khi bật AOP hoặc giao dịch, `getBean` có thể trả proxy, nên runtime type của bean có thể khác class tạo ban đầu.

### Khi constructor/factory ném exception

Ví dụ:

~~~java
@Bean
GreetingFormatter greetingFormatter(Phrase phrase) {
    if (phrase.prefix().isBlank()) {
        throw new IllegalArgumentException("Blank prefix");
    }
    return GreetingFormatter.create(phrase);
}
~~~

Đây là **minh họa**, không phải đoạn code trong ví dụ chạy mục 6. Nếu factory method ném exception, Spring không thể tạo bean `greetingFormatter` và thường báo lỗi tạo bean với nguyên nhân gốc kèm theo. Với singleton eager, lỗi có thể làm `refresh()` thất bại trước khi `getBean` được gọi.

### Hai anti-pattern thường gặp

1. **Tạo bean cùng class nhiều cách mà không có chủ đích:** vừa component-scan `GreetingService`, vừa đăng ký `@Bean GreetingService`, vừa register class. Điều này có thể tạo nhiều candidate, làm injection/lookup theo type mơ hồ.
2. **Factory method chứa business workflow:** body factory nên tập trung tạo/cấu hình object. Quy trình xử lý nghiệp vụ nên nằm ở service, không chạy khi container khởi động.

## 10. Lỗi phổ biến và cách xử lý

| Triệu chứng | Cần kiểm tra |
| --- | --- |
| `NoSuchBeanDefinitionException` khi `getBean` | Class/`@Bean` đã được đăng ký đúng context chưa? Có profile/condition cản không? |
| `NoUniqueBeanDefinitionException` | Có nhiều candidate cùng type? Chỉ rõ `@Primary`, `@Qualifier` hoặc tên bean |
| `UnsatisfiedDependencyException` | Constructor/factory method đang cần bean type nào mà thiếu? |
| `BeanCreationException` | Constructor/factory/init method ném lỗi gì? Xem nguyên nhân gốc |
| Không tìm được constructor phù hợp | Có nhiều constructor? Cấu hình autowire/đối số đã đúng? |
| Factory method không tìm thấy | Static hay instance? Method name/access/signature đúng? |
| XML `factory-bean` bị dùng như class name | Thuộc tính này là **bean name** của factory instance |
| Nhầm `@Bean` với `FactoryBean` | Cái thứ nhất là annotation cho factory method, cái thứ hai là SPI tạo product |
| Trả về class có constructor private | Có thể tạo thông qua public static factory nếu API cho phép |
| Gọi `@Bean` method thủ công trong lite mode | Lời gọi trực tiếp là Java call, có thể tạo object ngoài singleton managed |
| Gọi `new` trên class rồi chờ Spring quản lý | Instance ngoài container không tự có metadata/lifecycle Spring |
| Tưởng bean singleton là thread-safe | Scope không bảo đảm an toàn trạng thái thay đổi đồng thời |
| Tưởng Spring xóa hết `new` | Constructor và factory method vẫn tạo object; Spring tổ chức nơi tạo và vòng đời |

**Gỡ lỗi đúng thứ tự:** kiểm tra bean definition đã đăng ký → cách tạo (constructor/factory) → dependency và scope → lỗi gốc khi khởi tạo → cuối cùng mới xem lookup. Đừng sửa dependency bằng cách thêm một bean trùng lặp nếu chưa hiểu nguyên nhân.

## 11. Bài tập có đáp án

**Bài 1.** Class `GreetingService` có duy nhất constructor nhận `GreetingFormatter`. Nếu đã đăng ký class và có bean `GreetingFormatter`, có nhất thiết phải viết constructor không tham số không?

**Đáp án:** Không. Spring có thể chọn constructor duy nhất và cung cấp dependency tương ứng. Constructor không tham số không phải quy tắc bắt buộc của bean.

**Bài 2.** Vì sao `Formatter.of("Hello")` có thể tạo object dù constructor của `Formatter` private?

**Đáp án:** Static factory là method nằm trong class, nên có quyền gọi constructor private của chính class đó. Container có thể gọi static factory được cấu hình thay vì trực tiếp gọi constructor private.

**Bài 3.** XML `factory-bean="formatterFactory"` nghĩa là gọi method trên class tên `formatterFactory`?

**Đáp án:** Không. `factory-bean` là **tên một bean factory instance đã đăng ký**; Spring gọi instance method trên object đó.

**Bài 4.** Vì sao không dùng `@Bean` và `FactoryBean` như hai từ đồng nghĩa?

**Đáp án:** `@Bean` đánh dấu method cung cấp object. `FactoryBean<T>` là interface SPI để một factory bean cung cấp product qua `getObject()` và có quy tắc dereference riêng.

**Bài 5.** Trong ví dụ, `GreetingService` không có `@Component` mà vẫn có thể lookup vì sao?

**Đáp án:** `context.register(GreetingService.class)` đăng ký class làm bean definition trước `refresh()`. Component scan không phải cách đăng ký duy nhất.

**Bài 6.** Khi đổi `@Bean GreetingFormatter greetingFormatter(...)` thành `@Bean GreetingFormatter createFormatter(...)`, tác động nào đáng lưu ý?

**Đáp án:** Bean name mặc định có thể đổi từ `greetingFormatter` sang `createFormatter`. Code lookup theo type có thể vẫn hoạt động nếu duy nhất ứng viên; code dùng bean name cũ có thể lỗi.

**Bài 7.** Nếu bean `GreetingFormatter` có scope prototype, mọi lần `service.greet(...)` đều tự nhận formatter mới không?

**Đáp án:** Không. `GreetingService` singleton được inject một dependency khi tạo, nên thường giữ reference đó. Muốn cấp prototype mới theo mỗi lời gọi cần cách thiết kế/provider phù hợp.

## 12. Checklist lựa chọn và định nghĩa bean

- [ ] Xác định đúng **class sản phẩm** và khả năng gọi constructor/static/instance factory.
- [ ] Chọn constructor injection khi class thuộc quyền kiểm soát và dependency rõ ràng.
- [ ] Chọn static factory nếu API class yêu cầu hoặc lợi ích rõ.
- [ ] Chọn instance factory nếu việc tạo dựa trên một factory object đã được cấu hình.
- [ ] Nếu dùng `@Bean`, hiểu method có thể là static hoặc instance, và kết quả mới là managed bean.
- [ ] Không nhầm `factory-method`/`factory-bean` trong XML với interface `FactoryBean<T>`.
- [ ] Đăng ký class hoặc configuration vào context; annotation/source code một mình không tự tạo bean.
- [ ] Làm rõ bean name, return type, dependency arguments và khi nào type được nhận diện.
- [ ] Kiểm tra scope singleton/prototype và những ảnh hưởng tới số lần chạy constructor/factory.
- [ ] Tránh chạy logic nghiệp vụ phức tạp khi container đang tạo bean.
- [ ] Rà lỗi missing/ambiguous dependency và exception gốc.
- [ ] Dùng `getBean(Class<T>)` ở biên ứng dụng và constructor injection bên trong service.
- [ ] Viết test cho bean configuration khi nhiều đường tạo/triển khai cùng tồn tại.

**Kết luận:** **Bean class** mô tả loại object, còn **constructor hoặc factory method** quyết định đường tạo object. Spring lưu lựa chọn đó trong bean definition, nối dependency, quản lý scope/vòng đời và trả về bean cho nơi dùng. Phân biệt constructor, static factory, instance factory và `FactoryBean` giúp cấu hình Spring Core Container chính xác, dễ test và không bị phụ thuộc vào cách tạo object của một thư viện cụ thể.