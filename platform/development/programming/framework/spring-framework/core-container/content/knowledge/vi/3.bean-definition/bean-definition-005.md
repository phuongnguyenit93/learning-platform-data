# Thuộc tính `scope`, `lazy-init`, `primary` và `depends-on` trong Spring Bean Definition

## 1. Bốn thuộc tính điều khiển bốn quyết định khác nhau

Khi đã biết định nghĩa bean bằng `@Bean` hoặc `@Component`, ta cần hiểu **metadata** quyết định **số lượng và vòng đời instance**, **thời điểm khởi tạo**, **cách chọn dependency** và **thứ tự khởi tạo của các bean có quan hệ đặc biệt**.

| Thuộc tính | Câu hỏi nó giải quyết | Mặc định/thông dụng | Java configuration |
| --- | --- | --- | --- |
| **`scope`** | Một bean instance được cấp và tồn tại theo phạm vi nào? | `singleton` theo từng Spring container | `@Scope("singleton")`, `@Scope("prototype")` |
| **`lazy-init`** | Bean singleton có bị tạo sớm khi khởi động context không? | Non-lazy singleton thường eager | `@Lazy` |
| **`primary`** | Khi có nhiều bean cùng type, ứng viên nào được ưu tiên cho **một dependency**? | Không có bean mặc định được ưu tiên trừ khi khai báo | `@Primary` |
| **`depends-on`** | Bean nào phải được **khởi tạo trước** bean hiện tại dù không là constructor argument? | Spring dựa trên những dependency được khai báo thực sự | `@DependsOn("beanName")` |

Các metadata trên **không thay thế nhau**:

- `@Scope("prototype")` **không** tự làm bean thành lazy singleton; nó đổi scope.
- `@Lazy` **không** tạo instance mới mỗi lần `getBean`; điều đó liên quan tới scope.
- `@Primary` **không** đặt thứ tự tạo bean và không đổi scope.
- `@DependsOn` **không** chọn bean khi inject theo interface và **không tự inject** đối tượng phụ thuộc.

Một bean definition có thể kết hợp nhiều thuộc tính, nhưng cần lý do thực tế. Ví dụ bài này sẽ kết hợp `@Lazy` và `@DependsOn` trên một service để thấy thứ tự tạo khi service được yêu cầu.

## 2. `scope`: phạm vi cấp phát và vòng đời

### 2.1. `singleton` — mặc định phổ biến

Trong Spring, `singleton` nghĩa là **một bean instance cho mỗi bean definition trong mỗi IoC container** (trong phạm vi thông thường). Vì vậy hai lần lấy cùng một singleton bean bằng `getBean` trong cùng context thường trả về cùng reference:

~~~java
Object first = context.getBean("catalogService");
Object second = context.getBean("catalogService");
System.out.println(first == second); // true với singleton bean
~~~

Đây là trích đoạn minh họa, giả sử `catalogService` đã được đăng ký trong `context`. Nó không đồng nghĩa Singleton pattern cổ điển giữ **một** object duy nhất trên toàn JVM: hai context riêng có thể chứa hai instance khác nhau; hai bean definition riêng cũng có thể tạo hai singleton khác nhau của cùng class.

Vì Spring thường pre-instantiate những singleton **không lazy** khi `ApplicationContext.refresh()`, constructor và factory methods có thể được gọi từ lúc khởi động, **trước** lệnh `getBean` đầu tiên.

**Singleton không tự thread-safe.** Nếu một bean singleton giữ `HashMap`, bộ đếm hoặc trạng thái mutable mà nhiều thread truy cập, vẫn phải xem xét concurrency, đồng bộ hoặc thiết kế stateless. Việc có một instance dùng chung khiến vấn đề state càng cần chú ý.

### 2.2. `prototype` — yêu cầu bean thường cho instance mới

Một prototype bean thường được tạo **mỗi lần container nhận yêu cầu lấy instance**:

~~~java
@Bean
@Scope("prototype")
RequestToken requestToken() {
    return new RequestToken();
}
~~~

Đây là ví dụ minh họa, `RequestToken` chưa được định nghĩa ở đoạn này. Với prototype, hai lần `getBean("requestToken")` thông thường cho hai object khác nhau, nhưng **không nên dùng một random ID để chứng minh `==`**; hãy so identity trực tiếp hoặc giữ ID đếm ổn định như ví dụ chạy ở mục 6.

Khác biệt lifecycle cần nhớ:

- Spring quản lý giai đoạn khởi tạo và cấp instance của prototype.
- Spring **không tự gọi đầy đủ destroy callbacks cho mọi prototype** như đối với singleton khi đóng context. Bên yêu cầu/giữ object thường phải chịu trách nhiệm dọn tài nguyên tương ứng.
- Prototype không phải “bean cho từng HTTP request”. Nó chỉ nói về mỗi lần container được yêu cầu tạo bean.
- Một **prototype dependency inject trực tiếp vào singleton** thường được giải quyết **một lần khi singleton được tạo**. Vì thế singleton giữ nguyên reference đó trong các lời gọi về sau. Muốn có prototype mới theo nhu cầu, cân nhắc `ObjectProvider<T>` hoặc factory phù hợp.

### 2.3. Scope khác và ngữ cảnh web

Một số scope được cung cấp khi dùng môi trường web có hỗ trợ tương ứng:

| Scope | Ý nghĩa thông thường | Bối cảnh |
| --- | --- | --- |
| `singleton` | Một bean instance mỗi definition/context | Core Container |
| `prototype` | Instance mới theo yêu cầu lấy bean | Core Container |
| `request` | Bean sống theo một HTTP request | Web-aware application context |
| `session` | Bean theo một HTTP session | Web-aware application context |
| `application` | Bean gắn với ServletContext | Ứng dụng Servlet |
| `websocket` | Bean theo một WebSocket session | WebSocket integration |

Không thể lấy `@Scope("request")` hoạt động đúng chỉ bằng việc dùng `AnnotationConfigApplicationContext` console. Nó cần web scope được đăng ký và request context hợp lệ. Khi inject bean ngắn hạn vào bean sống lâu hơn, đôi khi cần **scoped proxy** hoặc provider, chứ không chỉ đổi tên scope.

Với các ứng dụng không có HTTP, thường tập trung hiểu `singleton` và `prototype` trước.

### 2.4. Cú pháp XML tương ứng

~~~xml
<bean id="accountService"
      class="demo.AccountService"
      scope="singleton"/>

<bean id="requestToken"
      class="demo.RequestToken"
      scope="prototype"/>
~~~

Đây là **đoạn XML minh họa**, các class được giả định có sẵn và có constructor phù hợp. XML và annotation là hai cách cung cấp metadata cho cùng Core Container, không phải hai loại container khác nhau.

## 3. `lazy-init`: thời điểm khởi tạo singleton

### 3.1. Tại sao có lazy initialization?

`ApplicationContext` thường tạo trước **singleton non-lazy** trong quá trình `refresh()`. Lợi ích là lỗi thiếu bean/khởi tạo thường được phát hiện ngay khi startup. Nhưng có bean rất nặng hoặc hiếm khi dùng, và bạn muốn hoãn chi phí tạo cho tới lần cần đầu tiên.

Trong XML, có thuộc tính:

~~~xml
<bean id="reportGenerator"
      class="demo.ReportGenerator"
      lazy-init="true"/>
~~~

Trong Java configuration, dùng `@Lazy`:

~~~java
@Bean
@Lazy
ReportGenerator reportGenerator() {
    return new ReportGenerator();
}
~~~

Hai đoạn **minh họa**, `ReportGenerator` chưa được khai báo ở đây. Khi không bị dependency eager khác buộc tạo sớm, `@Lazy` khiến singleton bean thường chỉ được tạo khi có yêu cầu đầu tiên, như `getBean(ReportGenerator.class)`.

**Không nhầm:** `@Lazy` trên **bean definition** nhằm trì hoãn tạo bean; `@Lazy` ở **injection point** trong một số cấu hình `@Autowired` có thể tạo proxy giải quyết dependency trì hoãn. Cùng annotation nhưng nơi đặt ảnh hưởng cách xử lý.

### 3.2. Bẫy thường gặp: lazy bean bị một eager singleton cần dùng

Giả sử:

~~~java
@Bean
@Lazy
ExpensiveClient expensiveClient() {
    return new ExpensiveClient();
}

@Bean
PaymentService paymentService(ExpensiveClient client) {
    return new PaymentService(client);
}
~~~

Đây là mã minh họa. `paymentService` là singleton eager, constructor/factory method của nó cần `ExpensiveClient`. Spring thường phải tạo `ExpensiveClient` để cấp argument, **dù bean đó đánh dấu `@Lazy`**. Vì vậy không thể chỉ nhìn `@Lazy` rồi khẳng định client chắc chắn chưa được tạo sau `refresh()`.

Muốn trì hoãn truy cập cho đến lúc sử dụng, có thể thiết kế `ObjectProvider<ExpensiveClient>`, một factory hoặc lazy-resolution proxy tùy nhu cầu. Nên cân nhắc rõ vòng đời và lỗi sẽ chuyển sang thời điểm sử dụng đầu tiên.

### 3.3. Lazy không đồng nghĩa hiệu năng luôn tốt

Đặt nhiều bean lazy có thể làm thời gian startup giảm, nhưng:

- Lỗi cấu hình có thể chỉ xuất hiện khi bean được yêu cầu, khó nhận ra sớm.
- Lần sử dụng đầu tiên chịu chi phí tạo và có thể gây latency.
- Bean được dùng thường xuyên thường không được lợi nhiều.
- Dependency graph vẫn quyết định thời điểm tạo thực tế.
- Có thể khiến hành vi init/lifecycle khó theo dõi hơn nếu bật lazy đại trà.

Nên tối ưu sau khi biết yêu cầu thật và đo đạc, không đánh dấu mọi bean `@Lazy` chỉ vì tưởng như nhanh hơn.

## 4. `primary`: chọn bean khi có nhiều ứng viên cùng kiểu

### 4.1. Bài toán autowiring theo type

Giả sử có interface:

~~~java
interface Formatter {
    String format(String value);
}
~~~

Có hai bean cùng kiểu `Formatter`:

~~~java
@Bean
Formatter basicFormatter() {
    return value -> "BASIC:" + value;
}

@Bean
Formatter decoratedFormatter() {
    return value -> "DECORATED:" + value;
}
~~~

Nếu một factory method/constructor yêu cầu **một** tham số `Formatter`, Spring cần quyết định chọn bean nào. Nếu không có quy tắc chọn rõ, có thể xảy ra `NoUniqueBeanDefinitionException`.

`@Primary` đánh dấu **ứng viên ưu tiên** cho dependency một giá trị:

~~~java
@Bean
@Primary
Formatter basicFormatter() {
    return value -> "BASIC:" + value;
}
~~~

Với đúng một primary candidate phù hợp, tham số `Formatter formatter` được inject từ `basicFormatter`, thay vì bean còn lại.

Đây là các đoạn minh họa. Chương trình chạy đầy đủ ở mục 6 sử dụng hai implementation rõ ràng và cho output chứng minh bean được chọn.

### 4.2. `@Primary` không làm được những gì?

- **Không xóa/khóa bean khác.** Bean không primary vẫn có thể truy cập theo tên hoặc `@Qualifier`.
- **Không có nghĩa chạy trước khi startup.** Thứ tự khởi tạo không do `@Primary` điều khiển.
- **Không đổi scope** hoặc tạo thêm singleton.
- **Không chọn một phần tử duy nhất cho injection dạng collection.** Inject `List<Formatter>`, `Formatter[]`, map hoặc stream thường vẫn thấy các bean phù hợp, bao gồm cả bean primary; cần kiểm tra chính xác quy tắc thứ tự khi dùng collection.
- **Không bảo đảm mọi lookup mơ hồ được giải quyết** nếu có nhiều primary cùng phù hợp hoặc các qualifier/priority khác chi phối.

Nếu muốn một triển khai cụ thể tại một injection point, thường có thể dùng `@Qualifier("decoratedFormatter")`. `@Primary` phù hợp cho **mặc định của một nhóm ứng viên**, còn `@Qualifier` biểu đạt lựa chọn rõ tại nơi tiêu thụ. Tránh gắn primary tràn lan không có chiến lược.

### 4.3. XML tương ứng

~~~xml
<bean id="basicFormatter"
      class="demo.BasicFormatter"
      primary="true"/>

<bean id="decoratedFormatter"
      class="demo.DecoratedFormatter"/>
~~~

XML chỉ minh họa cấu trúc. Hai class cần được định nghĩa trong project nếu muốn chạy.

## 5. `depends-on`: thứ tự khởi tạo trước khi sử dụng

### 5.1. Khi nào cần `depends-on`?

Dependency thường được Spring suy ra từ constructor hoặc `@Bean` method parameters:

~~~java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
~~~

Spring buộc phải cung cấp `OrderRepository` trước khi tạo `OrderService`. Không cần thêm `@DependsOn` chỉ để lặp lại quan hệ này.

Tuy nhiên, đôi lúc một bean cần **một hoạt động khởi tạo bên ngoài dependency trực tiếp** được thực hiện trước; chẳng hạn đăng ký driver/cấu hình cơ sở, nạp metadata hoặc khởi tạo một subsystem cần cho static API. Khi đó dùng `@DependsOn`:

~~~java
@Bean
@DependsOn("startupGate")
JobRunner jobRunner() {
    return new JobRunner();
}
~~~

Đây là ví dụ minh họa. Spring yêu cầu **bean có tên `startupGate` khởi tạo trước** bean `jobRunner`. Không có nghĩa Spring tự truyền instance `startupGate` làm constructor argument cho `JobRunner`.

Quan hệ này được khai báo bằng **bean name**, không phải class name. Nếu `startupGate` không tồn tại trong container, việc tạo `jobRunner` sẽ gặp lỗi cấu hình; nếu có vòng `depends-on`, container không thể hoàn tất khởi tạo.

### 5.2. Thứ tự hủy cho singleton

Với singleton beans có quan hệ `depends-on`, Spring còn có thể dùng quan hệ ngược trong thứ tự hủy: **bean phụ thuộc bị hủy trước bean mà nó depends-on**, để đối tượng nền tảng không bị đóng quá sớm. Quy tắc này áp dụng trong lifecycle được container quản lý; không suy ra tương tự cho prototype mà Spring không quản lý đầy đủ destruction.

**Không coi `@DependsOn` là scheduler.** Nó không lập lịch chạy nghiệp vụ, không thực hiện retry, không bảo đảm order cho các event bất đồng bộ và không thay `@Order` cho thứ tự trong collection hay post-processing.

### 5.3. XML tương ứng

~~~xml
<bean id="jobRunner"
      class="demo.JobRunner"
      depends-on="startupGate"/>

<bean id="startupGate"
      class="demo.StartupGate"/>
~~~

Bean `startupGate` được tạo trước `jobRunner`. Đừng nhầm thuộc tính `depends-on` với `constructor-arg ref`: cái đầu cưỡng chế thứ tự init, cái sau là **truyền dependency thật**.

## 6. Ví dụ Spring 6.2 / Java 17 runnable: kiểm tra cả bốn thuộc tính

Ví dụ console này không dùng Spring Boot, web server hay database. Nó chủ đích tạo **hai bean cùng interface `Formatter`**, một service lazy có `@DependsOn`, và một prototype có ID được cấp tăng dần.

### 6.1. Cấu trúc project

Yêu cầu JDK 17+, Maven, tải `spring-context` khi chạy lần đầu:

~~~text
bean-metadata-demo/
├── pom.xml
└── src/main/java/demo/BeanMetadataDemo.java
~~~

Tạo file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>bean-metadata-demo</artifactId>
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
                    <mainClass>demo.BeanMetadataDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Mã nguồn Java đầy đủ

Tạo `src/main/java/demo/BeanMetadataDemo.java`:

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Scope;

public final class BeanMetadataDemo {
    private BeanMetadataDemo() {}

    public interface Formatter {
        String format(String text);
    }

    public static final class MainFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "MAIN:" + text;
        }
    }

    public static final class AlternateFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "ALT:" + text;
        }
    }

    public static final class StartupGate {
        // Demo không có dependency bắt buộc phải truyền vào TaskRunner.
    }

    public record RequestToken(int id) {}

    public static final class TaskRunner {
        private final Formatter formatter;

        public TaskRunner(Formatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        public String run(String id) {
            return formatter.format(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        private static final AtomicInteger SEQUENCE = new AtomicInteger();

        @Bean
        @Primary
        public Formatter mainFormatter() {
            return new MainFormatter();
        }

        @Bean
        public Formatter alternateFormatter() {
            return new AlternateFormatter();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public RequestToken requestToken() {
            return new RequestToken(SEQUENCE.incrementAndGet());
        }

        @Bean
        @Lazy
        public StartupGate startupGate() {
            System.out.println("CREATE gate");
            return new StartupGate();
        }

        @Bean
        @Lazy
        @DependsOn("startupGate")
        public TaskRunner taskRunner(Formatter formatter) {
            System.out.println("CREATE runner");
            return new TaskRunner(formatter);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("BEFORE runner="
                    + context.getBeanFactory().containsSingleton("taskRunner"));

            TaskRunner runner = context.getBean(TaskRunner.class);
            System.out.println("RESULT " + runner.run("A01"));

            System.out.println("SAME runner="
                    + (runner == context.getBean(TaskRunner.class)));

            Formatter chosen = context.getBean(Formatter.class);
            Formatter alternate =
                    context.getBean("alternateFormatter", Formatter.class);

            System.out.println("PRIMARY " + chosen.format("B02"));
            System.out.println("ALTERNATE " + alternate.format("B02"));

            RequestToken one = context.getBean(RequestToken.class);
            RequestToken two = context.getBean(RequestToken.class);
            System.out.println("TOKENS " + one.id() + "," + two.id());
            System.out.println("TOKEN_DIFFERENT " + (one != two));

            System.out.println("AFTER runner="
                    + context.getBeanFactory().containsSingleton("taskRunner"));
        }
    }
}
~~~

### 6.3. Lệnh chạy và stdout

Từ thư mục `bean-metadata-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Các dòng stdout **do `BeanMetadataDemo` tự in** theo đúng thứ tự:

~~~text
BEFORE runner=false
CREATE gate
CREATE runner
RESULT MAIN:A01
SAME runner=true
PRIMARY MAIN:B02
ALTERNATE ALT:B02
TOKENS 1,2
TOKEN_DIFFERENT true
AFTER runner=true
~~~

`mvn -version` và Maven/plugin có thể phát sinh thêm phiên bản/log riêng. Khối trên chỉ mô tả đúng output của các `println` trong Java demo; không cam kết terminal chỉ có những dòng này.

### 6.4. Giải thích vì sao kết quả như vậy

1. `AnnotationConfigApplicationContext(AppConfig.class)` tạo và refresh context. Hai formatter singleton non-lazy có thể được tạo trong startup; chúng không tự in gì.
2. `taskRunner` là singleton `@Lazy`, không có bean eager nào yêu cầu nó. Ngay sau refresh, `containsSingleton("taskRunner")` trả `false`, in `BEFORE runner=false`.
3. Khi `getBean(TaskRunner.class)` yêu cầu tạo `taskRunner`, Spring thấy `@DependsOn("startupGate")`. Vì `startupGate` cũng đánh dấu `@Lazy` và trước đó chưa có bean nào cần nó, **Spring tạo gate trước**, in `CREATE gate`.
4. Sau gate, Spring giải quyết tham số `Formatter` của `taskRunner`. Có hai formatter, nhưng `mainFormatter` là ứng viên `@Primary` duy nhất, nên được chọn. Factory method `taskRunner` chạy và in `CREATE runner`.
5. `runner.run("A01")` dùng formatter primary, trả `MAIN:A01`. `TaskRunner` là singleton nên lần `getBean` thứ hai trả cùng object: `SAME runner=true`.
6. `getBean(Formatter.class)` trả `mainFormatter` được ưu tiên; lookup rõ tên `alternateFormatter` vẫn lấy formatter thứ hai. Vì vậy có hai dòng `PRIMARY MAIN:B02` và `ALTERNATE ALT:B02`.
7. `RequestToken` có scope prototype, nên hai lần `getBean(RequestToken.class)` chạy factory method hai lần. Bộ đếm trong demo tăng từ 0 tạo ID 1 rồi 2, và so identity cho `TOKEN_DIFFERENT true`.
8. Đến cuối block, singleton `taskRunner` đã tồn tại trong container nên `containsSingleton("taskRunner")` trả `true`.
9. `try-with-resources` đóng Spring context. Demo không có callbacks hủy cần in log nên kết quả stdout kết thúc ở dòng `AFTER runner=true`.

**Điểm mấu chốt của demo:** dòng `CREATE gate` xuất hiện **trước** `CREATE runner` vì `depends-on`. Chúng không hiện từ lúc startup vì hai bean lazy và không bị bean eager khác buộc khởi tạo.

Đừng suy từ output rằng mọi bean được tạo đúng theo thứ tự source code trong `AppConfig`: Spring chỉ bảo đảm những quan hệ dependency/cấu hình tương ứng; thứ tự không liên quan không nên được dùng làm logic nghiệp vụ.

## 7. Kết hợp bốn thuộc tính trong ứng dụng thực tế

### 7.1. Một service singleton cần prototype theo từng tác vụ

Nếu `TaskRunner` singleton cần một `RequestToken` mới trên mỗi lần gọi, **không** inject `RequestToken` trực tiếp vào constructor và kỳ vọng nó đổi tự động.

Thay vào đó, có thể inject `ObjectProvider<RequestToken>`:

~~~java
import org.springframework.beans.factory.ObjectProvider;

final class ProcessingService {
    private final ObjectProvider<RequestToken> tokens;

    ProcessingService(ObjectProvider<RequestToken> tokens) {
        this.tokens = tokens;
    }

    void process() {
        RequestToken token = tokens.getObject();
        // Dùng token mới cho lần xử lý hiện tại.
    }
}
~~~

Đây là **đoạn minh họa**, sử dụng record `RequestToken` của mục 6; không phải file runnable độc lập. `ObjectProvider.getObject()` yêu cầu bean từ container khi được gọi, nên với prototype thông thường sẽ nhận object mới.

### 7.2. Chọn primary nhưng vẫn truy cập bean khác

Một ứng dụng có thể có bean email và SMS cùng interface, đặt email làm mặc định `@Primary`. Tuy nhiên khi một use case cần SMS rõ ràng, `@Qualifier("smsNotifier")` ở injection point là cách nói rõ ý định. Không dùng `@Primary` để quyết định logic nghiệp vụ per-request, ví dụ chọn kênh từ dữ liệu người dùng; đó là yêu cầu thiết kế strategy/router khác.

### 7.3. Không nhầm `depends-on` với dependency injection

Nếu một service cần gọi phương thức của `ClientPool`, hãy khai báo `ClientPool` trong constructor hoặc factory method parameter. `@DependsOn("clientPool")` **không cung cấp tham chiếu `ClientPool`**. Nó chỉ buộc init trước. Dùng `depends-on` khi có **ràng buộc thứ tự ngoài quan hệ inject thông thường**, và ghi rõ vì sao.

### 7.4. Lazy với bean có tác dụng phụ khởi tạo

Cân nhắc:

- Bean làm việc nặng lúc startup có thực sự cần tạo ngay?
- Nếu hoãn, request đầu tiên có chịu latency/exception khó chấp nhận không?
- Có một singleton eager khác cần trực tiếp bean này không?
- Có thể thiết kế khởi tạo nền, preload sau startup hoặc factory/provider thay vì lazy chung chung không?

Đừng đặt side effect nghiệp vụ chính vào constructor chỉ để tận dụng `depends-on`; thứ tự xử lý nghiệp vụ thuộc method rõ ràng hoặc lifecycle hợp lý, không nên ẩn hoàn toàn trong việc tạo bean.

## 8. Các hiểu nhầm và lỗi thường gặp

| Hiểu nhầm / lỗi | Cách hiểu hoặc xử lý đúng |
| --- | --- |
| “`singleton` là một object cho cả JVM.” | Singleton của Spring thường theo bean definition trong **mỗi container**. |
| “`singleton` luôn thread-safe.” | Scope không tạo đồng bộ; cần tự thiết kế state/concurrency. |
| “`prototype` được destroy khi đóng context.” | Spring thường không quản lý đầy đủ destroy callbacks của prototype. |
| “Inject prototype vào singleton thì mỗi method nhận prototype mới.” | Injection thường xảy ra một lần; dùng provider/factory khi cần. |
| “`@Lazy` bảo đảm bean không khởi tạo ở startup.” | Eager dependency có thể buộc nó được tạo trước. |
| “`@Lazy` tương đương `@Scope("prototype")`.” | Một thuộc tính quyết định thời điểm, một thuộc tính quyết định scope. |
| “`@Primary` khiến bean được khởi tạo đầu tiên.” | Primary quyết định ưu tiên resolution, không phải init order. |
| “`@Primary` làm biến mất các bean cùng interface khác.” | Chúng vẫn tồn tại và có thể tra theo tên/qualifier. |
| “Hai primary cùng type chắc chắn chọn được một.” | Có thể vẫn ambiguous; cấu hình lựa chọn phải không mơ hồ. |
| “`@DependsOn` tự truyền dependency cho constructor.” | Không; nó buộc init order theo bean name. |
| “`@DependsOn` là cách phổ biến để giải quyết mọi vòng phụ thuộc.” | Không; có thể tạo hoặc bộc lộ vòng dependency, cần thiết kế lại. |
| “`@DependsOn` điều khiển mọi event/job theo thứ tự.” | Không; chỉ liên quan lifecycle bean tương ứng. |
| “Scope request/session chạy trong console context.” | Cần web-aware scope và request/session context thích hợp. |
| “Prototype và singleton luôn có cùng cơ chế hủy.” | Vòng đời destroy prototype khác singleton. |
| “Lỗi lazy luôn lộ lúc startup.” | Có thể chỉ lộ lúc lần đầu bean được yêu cầu. |
| “Có `@Bean` là đã có bean.” | Class cấu hình phải được đăng ký/scan, metadata được container xử lý. |

### Đọc lỗi liên quan

- `NoSuchBeanDefinitionException`: `@DependsOn` trỏ sai tên bean, hoặc dependency không đăng ký.
- `NoUniqueBeanDefinitionException`: nhiều ứng viên cho một dependency mà không chọn được; cân nhắc `@Primary` hoặc `@Qualifier`.
- `BeanCreationException`: lỗi constructor/factory/lifecycle, có thể xảy ra muộn với bean lazy.
- `BeanCurrentlyInCreationException` hoặc lỗi vòng phụ thuộc: graph tạo bean có vòng không giải quyết được.
- `ScopeNotActiveException`: cố truy cập scoped bean ngoài context scope hoạt động.

Khi debug, xem **nguyên nhân gốc** và bean name trong stack trace. Đừng giải quyết bằng cách đổi tất cả sang prototype hoặc thêm `@Lazy` tràn lan nếu graph thiết kế có vấn đề.

## 9. Bài tập tự kiểm tra (có đáp án)

**1.** Hai lần `getBean("catalogService")` nhận cùng reference. Có thể kết luận object duy nhất trong JVM không?

**Đáp án:** Không. Với singleton, thường là cùng instance của bean trong **context đang xét**. Context khác hoặc bean definition khác có thể tạo instance khác.

**2.** Một `@Lazy` bean được inject trực tiếp vào eager singleton. Nó có luôn đợi đến lúc được gọi mới tạo không?

**Đáp án:** Không. Để tạo eager singleton, Spring có thể phải giải quyết và tạo dependency lazy trước. Nếu muốn hoãn, sử dụng provider/lazy proxy có chủ đích.

**3.** Hai bean cùng interface `Formatter`; một bean có `@Primary`. Còn lấy được bean kia không?

**Đáp án:** Có. Có thể lấy theo tên hoặc dùng `@Qualifier` rõ ràng. Primary chủ yếu giải quyết một injection point khi nhiều ứng viên.

**4.** Một bean `jobRunner` có `@DependsOn("startupGate")`. `JobRunner` có tự nhận tham số `StartupGate` không?

**Đáp án:** Không. Đó là một ràng buộc thứ tự khởi tạo. Nếu cần object để gọi method thì khai báo dependency qua constructor/factory parameter.

**5.** Lý do `CREATE gate` xuất hiện trước `CREATE runner` trong demo?

**Đáp án:** `taskRunner` có `@DependsOn("startupGate")`. Khi runner được yêu cầu, Spring tạo gate trước rồi mới tạo runner.

**6.** Vì sao hai lần `getBean(RequestToken.class)` cho ID 1 và 2?

**Đáp án:** Bean `RequestToken` là prototype, nên factory được gọi cho mỗi yêu cầu. `AtomicInteger` dùng để cấp ID tăng dần trong một lần chạy JVM demo. Hai instance khác nhau theo `==`.

**7.** Nếu service singleton có tham số constructor `RequestToken token` là prototype, mỗi lần gọi `service.run()` có token mới không?

**Đáp án:** Không theo thiết kế injection trực tiếp thông thường. Singleton giữ instance đã inject lúc tạo; cần `ObjectProvider<RequestToken>` hoặc factory khi muốn cấp mới cho mỗi lần chạy.

**8.** Với singleton A `@DependsOn("B")`, nếu có callback destroy, B có bị hủy trước A không?

**Đáp án:** Không trong cơ chế hủy phụ thuộc singleton được Spring quản lý: bean phụ thuộc **A thường bị hủy trước B**, giúp B còn sẵn khi A dọn dẹp.

**9.** Nên dùng `@Primary` để chọn phương án thanh toán dựa trên loại đơn hàng ở runtime?

**Đáp án:** Không trực tiếp. Primary là metadata resolution một candidate mặc định khi lắp bean; lựa chọn theo dữ liệu nghiệp vụ tại runtime cần strategy/router hoặc kiến trúc phù hợp.

## 10. Checklist dùng metadata bean có chủ đích

- [ ] Bean được đăng ký qua `@Configuration`/`@Bean`, component scan hoặc bean definition đúng context.
- [ ] Xác định bean nào nên stateless singleton và bean nào cần instance ngắn hạn.
- [ ] Không để mutable state không an toàn trong singleton dùng nhiều thread.
- [ ] Với prototype, có kế hoạch sở hữu/dọn tài nguyên khi cần.
- [ ] Nếu singleton cần prototype nhiều lần, chọn provider/factory, không mong injection trực tiếp tự đổi.
- [ ] Chỉ đặt `@Lazy` khi thực sự cần trì hoãn tạo và đã xem xét eager dependencies.
- [ ] Có kế hoạch quan sát lỗi có thể xảy ra lúc sử dụng đầu tiên đối với lazy bean.
- [ ] Với nhiều bean cùng type, chỉ định primary/qualifier theo quy tắc rõ ràng.
- [ ] Không coi primary là cơ chế lập lịch init hoặc loại trừ bean khác.
- [ ] Đặt `@DependsOn` bằng **đúng bean name**, chỉ khi thứ tự khởi tạo không thể biểu đạt bằng dependency trực tiếp.
- [ ] Hiểu thứ tự hủy singleton phụ thuộc và không áp dụng máy móc cho prototype.
- [ ] Không dùng `@DependsOn` để thay truyền dependency trong constructor.
- [ ] Kiểm thử output/lifecycle bằng ứng dụng nhỏ trước khi dùng cho graph lớn.
- [ ] Khi mở rộng sang request/session scope, dùng đúng web-aware context.
- [ ] Không đồng nhất bốn thuộc tính với AOP proxy, transaction management hay HTTP routing.

## 11. Tài liệu tham khảo Spring

- [Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Lazy-initialized beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html)
- [Classpath scanning, @Scope và @Primary](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)

**Kết luận:** `scope` quyết định **phạm vi instance**, `lazy-init` quyết định **khi nào tạo** (trong điều kiện dependency graph), `primary` chọn **ứng viên được ưu tiên** cho một dependency, và `depends-on` buộc **khởi tạo bean khác trước**. Biết đúng giới hạn từng thuộc tính giúp thiết kế bean graph dự đoán được, tránh lỗi vòng đời, tránh mơ hồ autowiring và không biến metadata thành nơi giấu luồng nghiệp vụ.