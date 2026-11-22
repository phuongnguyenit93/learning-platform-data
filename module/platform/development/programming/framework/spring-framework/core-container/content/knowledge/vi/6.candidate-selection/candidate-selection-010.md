# Phân biệt ưu tiên lựa chọn với thứ tự khởi tạo — Spring Framework Core Container

## 1. Ba câu hỏi khác nhau thường bị trộn lẫn

Trong Spring IoC Container, khi có nhiều bean thực thi cùng một interface, developer có thể cần **chọn một bean**, **sắp xếp nhiều beans**, hoặc **bảo đảm một bean khởi tạo trước bean khác**. Ba yêu cầu này xảy ra ở những bước khác nhau và không được giải quyết bằng một annotation duy nhất.

Giả sử ứng dụng có hai bean cùng kiểu `Sender`: `emailSender` và `smsSender`. Hãy phân biệt:

1. **Ưu tiên chọn ứng viên:** Nếu constructor cần **một** `Sender`, bean nào được inject? Đây là vấn đề candidate resolution. Công cụ thường dùng là `@Primary`, `@Qualifier`, `@Fallback` hoặc các quy tắc chọn bean khác.
2. **Thứ tự của các ứng viên được tập hợp:** Nếu constructor cần `List<Sender>`, phần tử nào đứng trước trong danh sách? Đây là collection ordering. Công cụ thường dùng là `@Order`, `Ordered` hoặc khi thích hợp `jakarta.annotation.Priority`.
3. **Thứ tự khởi tạo/lifecycle:** Bean nào được Spring **tạo và hoàn tất khởi tạo** trước một bean khác? Đây là vấn đề dependency graph, `@DependsOn`, constructor dependencies, `@Lazy`, scope và lịch bootstrap. `@Primary` hoặc `@Order` không phải câu lệnh điều khiển thứ tự khởi tạo singleton.

Một câu ghi nhớ quan trọng:

> **Được ưu tiên chọn không đồng nghĩa được tạo trước. Đứng đầu collection cũng không đồng nghĩa được tạo đầu tiên.**

Bài học đặt ba ý niệm này cạnh nhau trong **Spring Framework Core Container**, không dùng Spring Boot để tránh thêm lifecycle/scheduler không liên quan.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Giải thích injection một bean khác injection `List<Bean>` và khác trình tự tạo bean.
- Biết `@Primary` chọn một ứng viên mặc định, `@Qualifier` chọn theo ý định consumer và `@Fallback` hạ độ ưu tiên trong Spring 6.2.
- Biết `@Order` tác động tới **thứ tự các phần tử trong collection** và một số điểm ưu tiên khác của framework, nhưng **không điều khiển singleton startup order**.
- Dùng `@DependsOn` khi thực sự cần thứ tự initialization do side effect, và phân biệt nó với **truyền dependency qua constructor**.
- Hiểu singleton eager initialization, `@Lazy`, prototype, circular dependency và giới hạn của việc dựa vào thứ tự khai báo.
- Chạy ví dụ Java 17+ với Spring Framework 6.2.19: một bean **`@Primary` và `@Order(1)` được khởi tạo sau** bean còn lại do `@DependsOn`.
- Viết smoke tests xác nhận **đúng bean**, **đúng collection order** và **đúng quan hệ khởi tạo**, tránh suy luận từ log ngẫu nhiên.
- Phân biệt initialization order, destruction order và thứ tự gọi method nghiệp vụ.

**Phạm vi:** lựa chọn ứng viên so với thứ tự khởi tạo của beans trong IoC container. Bài không yêu cầu Spring Boot, MVC, transaction manager, thread scheduler hay dependency ngoài module Spring Context.

## 2. Bảng phân biệt trước khi viết annotation

| Câu hỏi | Điểm cần quan sát | Công cụ Spring phù hợp | Không nên suy ra |
| --- | --- | --- | --- |
| Chọn **một** Sender | Constructor parameter `Sender` | `@Primary`, `@Qualifier`, `@Fallback`, candidate rules | Chọn trước tức là tạo trước |
| Chọn Sender theo một nghiệp vụ cụ thể | `@Qualifier("emailSender") Sender` | Qualifier metadata và type resolution | Qualifier quyết định init order |
| Lấy và sắp **nhiều** Sender | `List<Sender>` / array | `@Order`, `Ordered`, ordering comparator | `@Order(1)` tự thành primary |
| Buộc bean B chỉ tạo sau bean A | Bean definitions và dependency graph | Constructor/factory parameter, `@DependsOn("beanA")` | `@Primary` hoặc `@Order` giải quyết quan hệ này |
| Trì hoãn tạo một singleton | Bean definition | `@Lazy` | Lazy đồng nghĩa phụ thuộc luôn optional |
| Tạo lại object theo mỗi lần yêu cầu | Bean scope | `@Scope("prototype")` | Prototype được eagerly pre-instantiate như singleton |
| Điều khiển thứ tự **shutdown** với quan hệ depends-on | Lifecycle singleton | `@DependsOn` + destruction callbacks | Mọi bean đều có cùng thứ tự hủy |
| Điều khiển thứ tự gọi nghiệp vụ | Logic application | Orchestrator/explicit method calls | Spring tự chạy method theo `@Order` của bean |

Nếu một team dùng chữ “priority” mà không nói **priority cho hành động gì**, hãy hỏi lại: “Ưu tiên lựa chọn dependency đơn trị, ưu tiên trong danh sách hay ưu tiên khởi động?” Nhiều bug xuất phát từ việc gọi cả ba là “thứ tự bean”.

## 3. Chọn một ứng viên với @Primary, @Qualifier, @Fallback

Giả sử context có hai bean cùng interface `Sender`. Một điểm tiêm `Sender` đơn trị cần chọn một trong các ứng viên hợp lệ: `@Primary` có thể xác định lựa chọn mặc định; `@Qualifier("emailSender")` yêu cầu vai trò cụ thể; `@Fallback` từ Spring 6.2 hạ ưu tiên một bean dự phòng. Các cơ chế này can thiệp vào **lựa chọn dependency**, không ra lệnh cho Spring gọi factory method nào trước.

Nếu một ứng viên bị loại bằng `autowireCandidate=false`, các annotation ưu tiên không tự đưa nó trở lại tập được autowire. Nếu consumer yêu cầu `List<Sender>`, những bean đủ điều kiện có thể cùng xuất hiện dù bean nào là primary/fallback. Bài này dùng SMS được chọn làm default để đối chiếu với thứ tự collection và khởi tạo khác hẳn trong demo mục 8.

## 4. @Order: thứ tự trả về cho collection injection

Nếu consumer cần **tất cả** senders, nó có thể inject collection:

~~~java
public NotificationPipeline(List<Sender> senders) {
    this.senders = List.copyOf(senders);
}
~~~

Spring sắp collection theo metadata phù hợp như `@Order`, `Ordered`, hoặc `@Priority` khi annotation chuẩn có mặt và được hỗ trợ đúng vị trí.

~~~java
@Bean("emailSender")
@Order(20)
Sender emailSender() {
    return new NamedSender("EMAIL");
}

@Bean("smsSender")
@Order(1)
Sender smsSender() {
    return new NamedSender("SMS");
}
~~~

Nếu inject `List<Sender>` từ hai beans này, kết quả dự kiến là:

~~~text
[SMS, EMAIL]
~~~

**Giá trị nhỏ hơn có ưu tiên đứng trước trong collection** (ví dụ 1 đứng trước 20). Điều đó là **sorting policy**, không phải quy tắc gọi hai factory methods theo thứ tự 1 rồi 20.

### Không dùng @Order để thay thế @Primary

Một consumer cần đơn trị:

~~~java
public NotificationJob(Sender sender) {
    this.sender = sender;
}
~~~

Giả sử hai bean cùng type có `@Order(1)` và `@Order(20)`, **không nên xem @Order là cách giải quyết đáng tin cậy để chọn một sender duy nhất**. Hãy khai báo `@Primary` cho default thực sự hoặc `@Qualifier` ở injection point.

JavaDoc Spring ghi rõ order values có thể ảnh hưởng tới mức ưu tiên ở **một số injection points**, nhưng **chúng không ảnh hưởng singleton startup order**. Cách áp dụng an toàn là xem `@Order` chủ yếu như **collection ordering**, không viết logic nghiệp vụ giả định nó sẽ thay thế mọi rule candidate resolution.

### @Order trên @Configuration class có ý nghĩa khác

Có thể gắn `@Order` cho `@Configuration` class, điều này ảnh hưởng **thứ tự đánh giá** các configuration classes trong tập đang xử lý. Nó **không tự áp dụng mức order đó cho các `@Bean` methods** bên trong.

Nếu muốn List<Sender> có thứ tự, gắn order trên từng target component hoặc `@Bean` method phù hợp. Đừng dựa vào thứ tự các configuration files hoặc classpath scanning để làm thứ tự collection có ý nghĩa nghiệp vụ.

### @Order không mặc định quyết định Map iteration

Spring có thể inject `Map<String, Sender>`, trong đó key là bean name. Nếu muốn hiển thị danh sách tên bean theo thứ tự xác định, hãy sort keys hoặc dùng một chính sách rõ. Đừng suy rằng `@Order(1)` luôn quyết định mọi kiểu Map traversal hoặc container iteration.

## 5. Thứ tự khởi tạo phụ thuộc bean graph, không phải ưu tiên chọn

Khi Spring tạo một bean, trước tiên những **dependency cần thiết của nó** phải được resolve và khởi tạo phù hợp. Một constructor:

~~~java
public EmailJob(Sender sender) {
    this.sender = Objects.requireNonNull(sender);
}
~~~

thể hiện quan hệ **EmailJob phụ thuộc Sender**. Trong cơ chế bean initialization bình thường không có vòng phụ thuộc, Spring cần có Sender phù hợp rồi mới có thể hoàn thành EmailJob.

Sơ đồ dependency theo chiều consumer → dependency:

~~~mermaid
flowchart LR
    Job["emailJob"] --> Sender["emailSender"]
    Sms["smsSender"] -.->|"phụ thuộc initialization"| Email["emailSender"]
    Note["Chú ý: quan hệ phụ thuộc"] --> Meaning["không phải @Primary/@Order"]
~~~

Mũi tên từ `smsSender` tới `emailSender` trong ví dụ phản ánh trường hợp ta **khai báo dependency khởi tạo**, chẳng hạn `@DependsOn("emailSender")`. Nó không phát sinh từ việc smsSender là primary hay có order number nhỏ.

### Khi không có quan hệ phụ thuộc

Hai singleton độc lập có thể được Spring tạo trong giai đoạn context startup, nhưng **không nên coi thứ tự source code của `@Bean` methods hay tên class là hợp đồng**. Một số cấu hình bình thường tạo non-lazy singletons theo thứ tự đăng ký definitions, nhưng điều đó không thay cho quan hệ phụ thuộc tường minh và có thể bị ảnh hưởng bởi graph, lazy beans, conditions, post-processors và những lựa chọn bootstrap khác.

**Nguyên tắc:** nếu đúng chức năng hệ thống cần bean A khởi tạo trước bean B, hãy biểu đạt lý do đó qua dependency thật hoặc `@DependsOn`, không dùng một đặc tính quan sát được trong lần chạy hiện tại.

## 6. @DependsOn: yêu cầu bean khác được khởi tạo trước

Khi bean B cần một **side effect khởi tạo** của bean A, nhưng không trực tiếp cần reference A trong constructor/property, bạn có thể khai báo:

~~~java
@Bean("emailSender")
Sender emailSender() {
    return new NamedSender("EMAIL");
}

@Bean("smsSender")
@DependsOn("emailSender")
Sender smsSender() {
    return new NamedSender("SMS");
}
~~~

Đây là **snippet** thuộc configuration class. Khi Spring tạo `smsSender`, nó bảo đảm bean `emailSender` được khởi tạo **trước đó**, dù `smsSender` không cần giữ field reference tới `emailSender`.

**Điều @DependsOn làm:**

- Ghi metadata initialization dependency theo **bean name**.
- Buộc Spring tạo/cấu hình bean được chỉ định trước bean hiện tại, trong điều kiện lifecycle liên quan.
- Với singleton destruction, `depends-on` còn tạo quan hệ hủy ngược: bean phụ thuộc bị hủy trước bean mà nó phụ thuộc.
- Hữu ích cho yêu cầu side-effect initialization không được thể hiện qua constructor/property injection; ví dụ một registration prerequisite được cung cấp bởi infrastructure bean.

**Điều @DependsOn không làm:**

- Không tự inject object A vào field của B.
- Không biến A thành primary hay cho A đứng đầu `List<T>`.
- Không thay `@Qualifier` khi cần chọn giữa nhiều beans cùng type.
- Không bảo đảm B không bao giờ bị gọi trước A trong mọi luồng nghiệp vụ; nó chỉ ràng buộc **bean lifecycle**.
- Không sửa được vòng phụ thuộc. Nếu A depends on B và B depends on A thì graph không thể được khởi tạo bình thường.
- Không có nghĩa A đã hoàn tất **mọi tác vụ asynchronous** hay external system side effects; cần contract readiness riêng nếu có công việc nền.

### Ưu tiên một dependency thực sự khi có thể

Nếu B thực sự **dùng API của A**, nên dùng constructor injection:

~~~java
public StartupCoordinator(ReadyState readyState) {
    this.readyState = Objects.requireNonNull(readyState);
}
~~~

Đây là API Java rõ ràng, cho phép test thuần Java. Dùng `@DependsOn` khi cần **khởi tạo trước nhưng không có dependency reference thích hợp**, không thay constructor injection bằng một string-based ordering khó bảo trì.

**Cẩn thận khi rename:** `@DependsOn("emailSender")` chứa tên bean dưới dạng String. Đổi bean name mà không cập nhật annotation có thể khiến context startup lỗi. Nên kiểm tra wiring/registration ở integration tests.

## 7. @Lazy, singleton và prototype: khi nào việc tạo thực sự xảy ra?

Theo mặc định, nhiều `ApplicationContext` implementations **eagerly pre-instantiate singleton beans** khi refresh context. Nhưng có các ngoại lệ quan trọng.

| Bean/cấu hình | Thời điểm tạo thường thấy | Điều không thể kết luận |
| --- | --- | --- |
| Singleton không lazy | Trong khởi động/`refresh()` của context | Sẽ tạo theo @Primary/@Order |
| `@Lazy` singleton không bị eager bean khác cần ngay | Khi được yêu cầu lần đầu | Không bao giờ tạo hoặc không thể lỗi |
| `@Lazy` singleton bị non-lazy singleton khác yêu cầu trực tiếp | Có thể vẫn tạo trong startup để đáp ứng dependency | @Lazy luôn trì hoãn tuyệt đối |
| Prototype | Khi Spring xử lý yêu cầu tạo bean tương ứng | Được eagerly instantiate như mọi singleton |
| Prototype injected trực tiếp vào singleton | Thường được resolve một lần lúc singleton tạo | Mỗi lần gọi method trên singleton sẽ có prototype mới |
| `ObjectProvider<T>` | Bean có thể được tra cứu on-demand bằng provider | Tự bảo đảm thứ tự nghiệp vụ |
| `@DependsOn` | Buộc prerequisite khởi tạo trước bean dependent | Chọn bean theo primary/order |
| Background initialization của Spring 6.2 (khi bật) | Có thể song song/lệch thứ tự so với synchronous startup | Nên đoán thứ tự từ log constructor |

Khi code không đăng ký bean lazy làm dependency bắt buộc của eager singleton, bạn có thể kiểm tra nó **chưa** được tạo sau `refresh()` và **đã** được tạo sau `getBean(...)`.

### @Lazy đặt ở đâu?

`@Lazy` trên bean definition thông báo chính sách lazy initialization; nó khác với `@Lazy` ở injection point, có thể yêu cầu lazy-resolution proxy tùy cấu hình. Nếu eager consumer cần một bean lazy **trực tiếp** khi xây dựng constructor, bean đích có thể vẫn được tạo sớm.

Không dùng `@Lazy` để che một vòng phụ thuộc hoặc một dependency thiếu bắt buộc. Nó có thể **chỉ dời thời điểm lỗi**, khiến runtime failure đến muộn và khó phân tích hơn.

### Scope không phải priority

Một bean `@Primary` có thể singleton, prototype hoặc scope khác. `@Primary` quyết định candidate khi cần single injection; **scope quyết định cách cấp instance**. Chọn đúng implementation chưa bảo đảm cùng object identity qua mỗi lời gọi nếu scope không phải singleton.

## 8. Demo Java 17+ hoàn chỉnh: chọn SMS trước nhưng tạo EMAIL trước

Chương trình cho thấy **cùng lúc**:

- `smsSender` có **`@Primary`** → dependency đơn trị trần nhận SMS.
- `smsSender` có **`@Order(1)`**, `emailSender` có `@Order(20)` → `List<Sender>` theo thứ tự **[SMS, EMAIL]**.
- `smsSender` có **`@DependsOn("emailSender")`** → dù SMS đứng đầu collection và là primary, bean EMAIL phải khởi tạo trước SMS.
- `@Qualifier("emailSender")` ở một factory method → consumer chuyên biệt vẫn nhận EMAIL.
- Bean `lazyReporter` gắn `@Lazy` và không được eager bean nào yêu cầu → sau startup chưa là instantiated singleton; sau lookup thì được khởi tạo.

Đây là **ba chiều độc lập**: *bean selection*, *list ordering*, và *creation timing*.

Yêu cầu: **JDK 17+**, Maven và Spring Framework **6.2.19**. Phiên bản được ghim để ví dụ tái lập; không có nghĩa đó là bản mới nhất. Không cần Spring Boot, HTTP server hay database.

### 8.1. Cấu trúc

~~~text
bean-order-vs-initialization/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanOrderVsInitDemo.java
~~~

### 8.2. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-order-vs-initialization</artifactId>
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
                    <mainClass>demo.BeanOrderVsInitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven giải quyết các module/transitive JARs của Spring Context. Với `javac`/`java` trực tiếp, cần thêm cả compile/runtime dependencies chứ không chỉ đặt một JAR `spring-context` lên classpath.

### 8.3. File src/main/java/demo/BeanOrderVsInitDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public final class BeanOrderVsInitDemo {
    private BeanOrderVsInitDemo() {}

    public interface Sender {
        String id();
    }

    public record NamedSender(String id) implements Sender {
        public NamedSender {
            Objects.requireNonNull(id);
        }
    }

    public static final class Events {
        private final List<String> events = new ArrayList<>();

        public void record(String name) {
            events.add(name);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }

        public boolean before(String earlier, String later) {
            int a = events.indexOf(earlier);
            int b = events.indexOf(later);
            return a >= 0 && b > a;
        }
    }

    public static final class Dashboard {
        private final Sender selected;
        private final Sender specificEmail;
        private final List<Sender> ordered;

        public Dashboard(Sender selected, Sender specificEmail,
                         List<Sender> ordered) {
            this.selected = Objects.requireNonNull(selected);
            this.specificEmail = Objects.requireNonNull(specificEmail);
            this.ordered = List.copyOf(ordered);
        }

        public Sender selectedBean() {
            return selected;
        }

        public String selected() {
            return selected.id();
        }

        public String qualified() {
            return specificEmail.id();
        }

        public String collectionOrder() {
            return ordered.stream().map(Sender::id)
                    .toList().toString();
        }
    }

    public record LazyReporter(String status) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Events events() {
            return new Events();
        }

        // Khai báo SMS trước trong mã để tránh dựa vào source order.
        // @DependsOn mới là ràng buộc yêu cầu EMAIL được tạo trước.
        @Bean("smsSender")
        @Primary
        @Order(1)
        @DependsOn("emailSender")
        public Sender smsSender(Events events) {
            events.record("sms");
            return new NamedSender("SMS");
        }

        @Bean("emailSender")
        @Order(20)
        public Sender emailSender(Events events) {
            events.record("email");
            return new NamedSender("EMAIL");
        }

        @Bean
        public Dashboard dashboard(
                Sender selected,
                @Qualifier("emailSender") Sender specificEmail,
                List<Sender> senders) {
            return new Dashboard(selected, specificEmail, senders);
        }

        @Bean("lazyReporter")
        @Lazy
        public LazyReporter lazyReporter(Events events) {
            events.record("lazy");
            return new LazyReporter("READY");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Dashboard dashboard = context.getBean(Dashboard.class);
            Events events = context.getBean(Events.class);
            Sender primary = context.getBean(Sender.class);

            System.out.println("selected=" + dashboard.selected());
            System.out.println("qualified=" + dashboard.qualified());
            System.out.println("collection=" +
                    dashboard.collectionOrder());
            System.out.println("created=" + events.snapshot());
            System.out.println("selectedIsPrimary=" +
                    (dashboard.selectedBean() == primary));
            System.out.println("emailBeforeSms=" +
                    events.before("email", "sms"));
            System.out.println("orderVsCreationDifferent=" +
                    !dashboard.collectionOrder().equals(
                            events.snapshot().stream()
                                    .map(String::toUpperCase)
                                    .toList().toString()));

            System.out.println("lazyBefore=" +
                    context.getBeanFactory()
                            .containsSingleton("lazyReporter"));
            System.out.println("lazyValue=" +
                    context.getBean(LazyReporter.class).status());
            System.out.println("lazyAfter=" +
                    context.getBeanFactory()
                            .containsSingleton("lazyReporter"));
            System.out.println("createdAfterLazy=" + events.snapshot());
        }
    }
}
~~~

### 8.4. Phân tích từng đặc điểm của code

**Bean selection:** `dashboard(Sender selected, ...)` có một tham số single-valued `Sender` không qualifier, trong context có EMAIL và SMS. `smsSender` có `@Primary` nên selected là SMS. `context.getBean(Sender.class)` cũng nhận SMS. Identity check cho thấy cùng singleton trong context này.

**Qualifier-specific dependency:** `@Qualifier("emailSender") Sender specificEmail` được chọn là EMAIL, dù SMS là primary. Qualifier chọn bean theo ngữ nghĩa injection point, không buộc EMAIL khởi tạo trước SMS; ràng buộc creation được khai báo ở chỗ khác.

**Collection ordering:** `@Order(1)` ở SMS, `@Order(20)` ở EMAIL; `List<Sender>` được sắp [SMS, EMAIL]. Không sử dụng source order hoặc random để sắp danh sách.

**Creation ordering:** `@DependsOn("emailSender")` trên SMS yêu cầu EMAIL initialization xong trước khi SMS factory được chạy. Hai factory methods ghi một event vào `Events`, nên trace là [email, sms]. Cả hai phụ thuộc cùng singleton `Events` nhưng Events không ghi sự kiện của chính nó.

**Cố ý ngược nhau:** SMS là **primary và first in List**, nhưng EMAIL được tạo **trước**. Do đó demo phản ví dụ trực tiếp cho ý tưởng “ưu tiên được chọn là khởi tạo sớm”.

**Lazy:** `LazyReporter` có `@Lazy` trên factory method và không có bean eager khác yêu cầu nó. `containsSingleton("lazyReporter")` ban đầu false, sau `getBean(LazyReporter.class)` thì true. Event thứ ba `lazy` chứng tỏ thời điểm tạo khác hai Sender eager.

**Ổn định:** demo dùng các labels String cố định, không dùng thời gian, random hoặc output từ các thread. List/Event trace cùng nằm trong một context, được ghi đồng bộ và chỉ để minh họa; `ArrayList` không được quảng cáo là thread-safe trong ứng dụng đa luồng.

**Cấu trúc Java:** chỉ có một public top-level class `BeanOrderVsInitDemo`, các interface/records/config là nested types; package `demo` và file path tương ứng. Java 17 hỗ trợ record, `List.copyOf` và `Stream.toList()`.

**`@Configuration(proxyBeanMethods=false)`:** các factory methods **không gọi trực tiếp lẫn nhau**. Spring resolve dependency qua tham số `@Bean`/`@DependsOn`, nên không phụ thuộc interception của lời gọi method JavaConfig.

**Lifecycle:** context đóng khi ra khỏi `try-with-resources`. Demo không đăng ký destroy callbacks in stdout; các dòng dự kiến chỉ đến từ `System.out.println` ở `main`. Với một singleton `@DependsOn` có destroy callback, Spring cũng có quan hệ hủy theo chiều ngược, nhưng demo này không dùng log hủy để tránh nhầm với thứ tự khởi tạo.

### 8.5. Chạy bằng Maven

Từ thư mục `bean-order-vs-initialization`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng 11 dòng stdout do chương trình in khi chạy thành công:**

~~~text
selected=SMS
qualified=EMAIL
collection=[SMS, EMAIL]
created=[email, sms]
selectedIsPrimary=true
emailBeforeSms=true
orderVsCreationDifferent=true
lazyBefore=false
lazyValue=READY
lazyAfter=true
createdAfterLazy=[email, sms, lazy]
~~~

Các dòng `java -version`, `mvn -version`, Maven downloading/logs hoặc framework logging (nếu có) không tính vào **11 dòng `System.out.println` do `main` in**.

**Đọc kết quả mà không suy quá mức:**

| Dòng | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `selected=SMS` | @Primary chọn SMS cho bare type dependency | SMS được tạo sớm nhất |
| `qualified=EMAIL` | Qualifier chọn EMAIL ngay cả khi SMS primary | Qualifier điều khiển startup |
| `collection=[SMS, EMAIL]` | @Order sắp List<Sender> | Factory SMS chạy trước factory EMAIL |
| `created=[email, sms]` | Thứ tự tạo 2 Sender objects quan sát được | Mọi bean khác cũng theo thứ tự này |
| `selectedIsPrimary=true` | Dashboard giữ đúng bean singleton được chọn | Singleton toàn JVM hay mọi scope |
| `emailBeforeSms=true` | Ràng buộc @DependsOn hoạt động | Một business method EMAIL luôn chạy trước SMS |
| `orderVsCreationDifferent=true` | Collection order và creation order khác nhau | Có một lịch bootstrap chung cho mọi ứng dụng |
| `lazyBefore=false` | lazyReporter chưa instantiated sau startup | Lazy luôn trì hoãn khi có eager consumer cần nó |
| `lazyValue=READY` | Lookup tạo được LazyReporter | Lazy bean không có lifecycle |
| `lazyAfter=true` | Singleton này đã được tạo sau lookup | Mọi prototype có chứa trong singleton registry |
| `createdAfterLazy=[email, sms, lazy]` | Trace có event khởi tạo lazy sau | Mọi background job đều đã xong |

### 8.6. Chạy bằng javac/java trên hai hệ điều hành

Nếu chạy trực tiếp, phải tạo compile/runtime classpath có **đầy đủ** các transitive dependencies từ Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash/zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanOrderVsInitDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanOrderVsInitDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanOrderVsInitDemo.java
java -cp "out;$deps" demo.BeanOrderVsInitDemo
~~~

Trên Unix, classpath separator là `:`, Windows là `;`. Hai cách chạy đều gọi cùng `main`. Nếu `javac` không thấy package `org.springframework...`, kiểm tra Maven POM/classpath trước khi chẩn đoán candidate resolution hoặc lifecycle.

## 9. Tại sao không nên dựa vào thứ tự @Bean trong source?

Một vài lần chạy có thể cho thấy bean khai báo trước trong `@Configuration` được tạo trước. Đó là một **quan sát cụ thể**, không phải contract đủ vững để điều phối nghiệp vụ.

Ví dụ:

~~~java
@Bean
public Warmup warmup() { ... }

@Bean
public Worker worker() { ... }
~~~

Đây là snippet minh họa, thiếu classes/implementation. Nếu `Worker` phụ thuộc vào side effect của `Warmup` nhưng không khai báo quan hệ, việc chỉ đặt method `warmup()` lên phía trên là **mong manh**. Hãy khai báo:

~~~java
@Bean
@DependsOn("warmup")
public Worker worker() { ... }
~~~

Hoặc tốt hơn, nếu `Worker` dùng chính object `Warmup`, đưa nó vào constructor/factory parameter để Spring thấy dependency thật.

Thứ tự đăng ký có thể bị ảnh hưởng bởi các configuration classes, conditional beans, component scanning, bean factory post-processors hoặc những extension points khác. Vì vậy **không ràng buộc nghiệp vụ với thứ tự reflection trả về methods**.

### @Order trên @Configuration khác order trên @Bean

`@Order` ở configuration-class level tác động tới thứ tự đánh giá các configuration classes, không tự “truyền” order xuống các bean methods. Để làm List injection có thứ tự, đặt order trên **bean definition target** hoặc implementation type. Để bắt initialization A trước B, khai báo **dependency B → A**.

## 10. Initialization và execution là hai thứ tự khác nhau

Ngay cả khi `@DependsOn("cacheLoader")` bảo đảm CacheLoader bean được **khởi tạo** trước Job bean, Spring không tự chạy `Job.execute()` sau `cacheLoader.load()` trừ khi có logic/lifecycle contract thực sự gọi chúng.

Phân biệt:

- **Construction order:** lúc constructor/factory method tạo object.
- **Dependency resolution order:** lúc Spring tạo/lấy những collaborator cần cho object.
- **Initialization callbacks:** `@PostConstruct`, `InitializingBean.afterPropertiesSet`, custom init methods, sau khi injection và trước bean sẵn sàng theo lifecycle thông thường.
- **Runtime method execution order:** controller, scheduler, event handler hoặc application orchestrator gọi method theo logic riêng.
- **Destruction order:** lúc context close/shutdown, có thể chịu ràng buộc đảo chiều của depends-on với singleton.

**Ví dụ nghiệp vụ:** nếu phải kiểm tra tồn kho trước khi charge, hãy viết một use case gọi stock rồi charge với xử lý lỗi/transaction phù hợp; đừng gắn `@Order(1)` cho `StockGateway` rồi mong runtime tự gọi nó trước `PaymentGateway`.

Tương tự, `@Primary` chỉ nói khi chọn một gateway thì lấy gateway nào; nó không nói **khi nào charge được phép thực hiện**. Chọn bean và lập lịch thực thi là hai trách nhiệm khác nhau.

## 11. Thứ tự hủy: @DependsOn có hiệu lực ngược với singletons

Với hai singleton beans:

~~~java
@Bean("connectionManager")
ConnectionManager manager() { ... }

@Bean("consumer")
@DependsOn("connectionManager")
Consumer consumer() { ... }
~~~

**Snippet minh họa** thiếu types. Khi khởi tạo, manager phải hoàn thành trước consumer. Khi container hủy singleton beans theo dependency relationship, Spring đảm bảo **consumer được hủy trước connectionManager**, để consumer có thể cleanup khi prerequisite còn tồn tại.

Điều này hữu ích với resource ownership, nhưng không thay cho proper `close()`/destroy callback khi bean thực sự có tài nguyên cần giải phóng.

Không suy rằng @Order hoặc @Primary áp dụng cho destruction order. Cũng không khẳng định prototype instances có full automatic destroy callbacks chỉ vì được chọn và tạo qua Spring; Spring không quản lý destruction của prototypes giống singletons mặc định.

## 12. Những nhầm lẫn cần sửa ngay

| Hiểu nhầm | Vì sao sai | Cách tiếp cận đúng |
| --- | --- | --- |
| “`@Primary` nghĩa là bean được khởi tạo đầu tiên” | Primary dùng chọn candidate đơn trị | Dùng dependency graph/`@DependsOn` nếu cần thứ tự khởi tạo |
| “`@Order(1)` nghĩa là factory method gọi trước” | Order sắp collection/priority ở các injection points liên quan | Đừng dùng @Order điều khiển singleton startup |
| “`@DependsOn` nghĩa là phụ thuộc sẽ được inject vào field” | Depends-on chỉ nói điều kiện khởi tạo | Inject object qua constructor/factory argument |
| “Bean đầu tiên trong List luôn là primary” | List ordering khác single-bean selection | Kiểm tra @Order và @Primary riêng |
| “Bean được chọn theo @Qualifier sẽ tạo trước bean khác” | Qualifier chỉ chọn ứng viên | Khởi tạo theo graph/scope/lazy |
| “@Fallback hoãn tạo bean cho tới lúc cần” | Fallback là chính sách ưu tiên lựa chọn | Dùng @Lazy khi muốn lazy singleton |
| “Dán @Lazy là không thể khởi tạo lúc startup” | Eager consumer có thể yêu cầu lazy bean | Xác định trực tiếp dependency và proxy/injection semantics |
| “Prototype giống eagerly created singleton” | Prototype được tạo khi cần | Xác định scope và request điểm lấy bean |
| “Đổi thứ tự các @Bean methods để fix bug” | Source order không phải lifecycle contract | Biểu đạt dependency tường minh |
| “@DependsOn tự chờ external service thật sự healthy” | Bean init không đồng nghĩa remote readiness | Có health/readiness contract riêng |
| “@Order trên @Configuration sắp mọi bean trong class” | Config processing order khác bean-level collection order | Đánh dấu @Order trên bean target |
| “Ứng dụng khởi động rồi thì mọi bean đã được tạo” | Có lazy/prototype/background modes | Test time-of-creation theo scope |
| “@Order quyết định thứ tự gọi các strategies” | Nó sắp List khi inject, method calls vẫn do code quyết định | Viết orchestrator loop theo collection khi cần |
| “@DependsOn giải quyết constructor cycle” | Graph tuần hoàn không có thứ tự init hợp lệ | Refactor cycle, bỏ hidden mutual dependencies |

### Vấn đề thiếu/thừa bean là vấn đề khác

Nếu injection một `Sender` thất bại vì có hai beans và không có selection policy, thêm `@DependsOn` **không giải quyết ambiguity**. Nếu `@DependsOn("emailSender")` báo không tìm thấy bean, thêm `@Primary` cũng không tạo được bean bị thiếu. Mỗi annotation sửa một loại quan hệ khác nhau; chẩn đoán đúng vấn đề trước khi chỉnh.

## 13. Debug có hệ thống khi thứ tự không như kỳ vọng

**Bước 1 — Làm rõ thứ tự cần kiểm tra.** Bạn đang nhìn order của `List<T>`, order của những factory events, lifecycle callbacks, destruction, hay business logs?

**Bước 2 — Chọn đúng bằng chứng.** Với candidate selection, kiểm tra bean identity của một injection point. Với List, kiểm tra thứ tự `Sender::id` trong List. Với initialization, thu events từ constructors/initializers vào một collector test đơn luồng hoặc kiểm tra dependency graph tường minh.

**Bước 3 — Xem bean definitions.** Tên bean nào được đăng ký, declared types nào, primary/fallback/qualifier/order metadata ra sao? Có `@Lazy`, scope hoặc `@DependsOn` không?

**Bước 4 — Kiểm tra graph trước timestamps.** Nếu B có constructor A, hoặc `@DependsOn("A")`, Spring phải xử lý A trước B theo contract thông thường. Không có edge thì một log tình cờ chưa tạo bảo đảm cho lần chạy sau.

**Bước 5 — Phân biệt eager và lazy.** Một singleton non-lazy thường tạo lúc refresh; một bean lazy có thể chưa tạo tới khi getBean. Nếu bean lazy là dependency của eager bean, kiểm tra liệu nó có bị buộc tạo sớm không.

**Bước 6 — Xem exception chain.** `NoUniqueBeanDefinitionException` chỉ việc chọn candidate; `NoSuchBeanDefinitionException` có thể chỉ thiếu prerequisite/bean; `BeanCurrentlyInCreationException` liên quan vòng dependency; `BeanCreationException` có thể chứa lỗi initializer.

**Bước 7 — Sửa đúng chiều quan hệ.** Chọn một bean → `@Primary`/`@Qualifier`; sắp nhiều beans → `@Order`; cần prerequisite init → dependency/`@DependsOn`; muốn trì hoãn → `@Lazy`; muốn thứ tự nghiệp vụ → code orchestration.

**Bước 8 — Viết regression test.** Đừng chỉ nhìn console log khi mọi thứ “có vẻ đúng”; kiểm tra một invariant cụ thể trong automated test.

### Ma trận chọn công cụ

| Nhu cầu | Ưu tiên dùng | Kiểm thử |
| --- | --- | --- |
| Luôn inject SMS mặc định | `@Primary` trên smsSender | `getBean(Sender.class)` hoặc service.selected.id == SMS |
| Chỉ client EMAIL dùng emailSender | `@Qualifier("emailSender")` | Consumer giữ đúng instance theo tên |
| Nhiều senders có thứ tự | `List<Sender>` và `@Order` trên beans | IDs == [SMS, EMAIL] |
| Email initialization phải xong trước SMS | `@DependsOn("emailSender")` hoặc dependency thật | Event email xuất hiện trước sms |
| Trì hoãn reporter cho tới lần dùng | `@Lazy` trên bean không bị eager consumer yêu cầu | Chưa singleton trước lookup, có sau |
| Consumer cần A trước khi thực hiện logic B | Explicit orchestration/method calls | Assert call order và failure paths |
| Shutdown consumer trước prerequisite | Singleton depends-on relationship | Destroy callback event order trong test riêng |

## 14. Test những khẳng định độc lập

### Unit test Java thuần cho logic chọn strategy

Có thể tạo fake/implementation với constructor injection thường:

~~~java
Sender fake = () -> "FAKE";
Dashboard dashboard = new Dashboard(
        fake, fake, List.of(fake));
System.out.println(dashboard.selected()); // FAKE
~~~

**Snippet** cần nằm trong phạm vi có thể truy cập các nested types của demo; không phải file Java độc lập. Unit test này chỉ chứng minh Java logic của Dashboard, không kiểm tra Spring chọn bean.

### Spring wiring test

Tạo context với `AppConfig.class`, rồi kiểm tra:

- `getBean(Sender.class)` nhận đúng SMS có `@Primary`.
- Bean EMAIL vẫn lấy được theo name và được inject vào `specificEmail`.
- `Dashboard.collectionOrder()` trả `[SMS, EMAIL]` theo `@Order`.
- Events sau refresh chứa `email` trước `sms` vì `@DependsOn`.
- LazyReporter chưa được tạo khi context mới refresh và chưa có eager consumer nào yêu cầu.
- Sau `getBean(LazyReporter.class)`, Events thêm `lazy`, bean được tạo.

Có thể dùng test framework assertions; không dựa vào Java `assert` khi không bật `-ea`. Trong test nghiêm túc, hãy tạo collector trong một context mới để không lẫn events các lần chạy.

### Negative tests hữu ích

**Test 1 — bỏ @Primary:** với hai Sender beans và single bare `Sender` injection, có thể phát sinh ambiguity (trừ khi có lựa chọn khác như qualifier/name matching); thiết kế test để không có name-based shortcut làm sai kết luận.

**Test 2 — bỏ @DependsOn:** vẫn có thể quan sát EMAIL trước SMS trong một lần chạy. Nhưng **không còn ràng buộc bắt buộc**; test không được kết luận từ một trace tình cờ rằng Spring cam kết ordering.

**Test 3 — thay @Order:** đổi `@Order(1)` thành giá trị lớn hơn EMAIL sẽ đổi list ordering, **không thay contract @DependsOn**.

**Test 4 — lazy bị eager consumer yêu cầu:** thêm singleton non-lazy cần LazyReporter trong constructor; có thể khiến LazyReporter tạo trong context refresh mặc dù @Lazy trên bean definition.

**Test 5 — constructor cycle:** bean A bắt buộc B, B bắt buộc A; Spring không giải quyết vòng constructor dependency đơn giản. Cần sửa graph.

**Test 6 — context shutdown:** thêm destroy callbacks ở cả hai singleton có quan hệ @DependsOn để test thứ tự hủy ngược. Đừng lẫn output đó vào expected stdout của demo chính.

## 15. Bài tập có đáp án

**Bài 1.** SMS có `@Primary`, EMAIL không có. Bare `Sender` injection nhận gì?

**Đáp án:** SMS nếu không có ràng buộc khác loại nó khỏi candidate set; primary quyết định lựa chọn đơn trị, không quyết định lúc tạo.

**Bài 2.** SMS `@Order(1)`, EMAIL `@Order(20)`. `List<Sender>` nhận thứ tự nào trong demo?

**Đáp án:** [SMS, EMAIL]; order nhỏ đứng trước khi Spring sắp collection injection.

**Bài 3.** SMS có `@Order(1)` và `@Primary`. Có bảo đảm SMS được tạo trước EMAIL không?

**Đáp án:** Không. Demo còn có @DependsOn(emailSender), nên SMS bắt buộc tạo sau EMAIL.

**Bài 4.** `@DependsOn("emailSender")` trên SMS có làm SMS không còn primary không?

**Đáp án:** Không. @DependsOn chi phối initialization dependency; @Primary vẫn là selection metadata.

**Bài 5.** EMAIL có `@Order(20)`. Sao trong trace vẫn được tạo trước SMS?

**Đáp án:** Vì @DependsOn ràng buộc EMAIL phải được khởi tạo trước SMS; @Order không quy định thứ tự factory invocations.

**Bài 6.** Consumer có `@Qualifier("emailSender")` dù SMS primary. Consumer lấy gì?

**Đáp án:** EMAIL trong demo; qualifier thu hẹp ứng viên mà injection point muốn.

**Bài 7.** Bean lazy không được tham chiếu bởi eager beans. Nó được tạo lúc nào?

**Đáp án:** Thường khi được truy cập lần đầu, không phải trong initial pre-instantiation của context.

**Bài 8.** Nếu singleton non-lazy trực tiếp cần một lazy bean trong constructor thì sao?

**Đáp án:** Spring có thể phải tạo lazy bean trong startup để đáp ứng eager consumer; lazy definition không phải cam kết “không bao giờ khởi tạo trước getBean trực tiếp”.

**Bài 9.** @DependsOn có tự gọi method send() của Sender theo thứ tự không?

**Đáp án:** Không. Nó ràng buộc bean initialization; method execution do code ứng dụng quyết định.

**Bài 10.** Khi context đóng, thứ tự hủy singletons có depends-on thế nào?

**Đáp án:** Dependent bean bị hủy trước prerequisite bean; ngược chiều ràng buộc initialization.

**Bài 11.** Nếu hai singleton không có quan hệ phụ thuộc, có nên đưa thứ tự init quan sát được vào hợp đồng domain không?

**Đáp án:** Không. Hãy thiết kế dependency/ready-state tường minh nếu thứ tự thật sự quan trọng, tránh phụ thuộc registration order tình cờ.

**Bài 12.** Với task cần các bước chuẩn bị → xử lý → thông báo, dùng @Order trên ba service để Spring tự chạy đủ thứ tự có ổn không?

**Đáp án:** Không. Dùng một orchestrator/service method kiểm soát trình tự nghiệp vụ, lỗi và retry; @Order chỉ có thể hỗ trợ sắp collection nếu chính code thực thi tuần tự trên collection.

## 16. Checklist áp dụng

- [ ] Phân biệt rõ **lựa chọn một bean**, **thứ tự List**, **thứ tự khởi tạo** và **thứ tự chạy nghiệp vụ**.
- [ ] Dùng `@Primary` cho một default hợp lý, không phải startup priority.
- [ ] Dùng `@Qualifier` cho lựa chọn riêng của consumer.
- [ ] Dùng `@Fallback` như chính sách lựa chọn ưu tiên thấp, không phải lazy initialization.
- [ ] Dùng `@Order` cho List/array ordering, không dùng nó làm lifecycle contract.
- [ ] Đọc đúng vị trí @Order trên @Bean methods hoặc target components; không nhầm @Configuration order.
- [ ] Dùng dependency graph/constructor injection cho những collaborator thực sự được dùng.
- [ ] Dùng `@DependsOn` khi cần prerequisite initialization không có direct reference.
- [ ] Không dựa vào thứ tự khai báo @Bean trong source để buộc một side effect khởi tạo.
- [ ] Không nhầm bean initialized với service bên ngoài đã ready hay nghiệp vụ đã chạy.
- [ ] Với @Lazy, kiểm tra có eager consumer buộc bean khởi tạo sớm không.
- [ ] Với prototype, hiểu bean không được eagerly pre-instantiate như singleton.
- [ ] Biết quan hệ hủy singleton ngược chiều depends-on.
- [ ] Không dùng @DependsOn để che circular dependencies.
- [ ] Viết unit tests cho Java logic và integration tests cho chọn bean, List ordering và creation events.
- [ ] Chạy Java 17+ với Maven hoặc javac/java; so **11 dòng stdout ứng dụng**.
- [ ] Khi đọc logs, hỏi “đây là init event, log nghiệp vụ hay destroy callback?”
- [ ] Khi lỗi, sửa đúng annotation/cơ chế phục vụ đúng mục tiêu.

**Kết luận:** `@Primary`, `@Qualifier` và `@Fallback` giúp Spring **chọn đúng bean cho dependency**. `@Order` giúp sắp **nhiều bean** trong những collection/injection points tương ứng. `@DependsOn`, constructor dependencies, `@Lazy` và scope chi phối **khi nào bean được tạo**. Ba lớp quyết định này độc lập về ý nghĩa; nắm ranh giới của chúng giúp bạn tránh wiring lệch, startup assumptions mong manh và sai trình tự nghiệp vụ.

### Tài liệu Spring chính thức

- [Spring 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring 6.2 — Fine-tuning @Primary / @Fallback](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html)
- [Spring 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html)
- [Spring 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html)
- [Spring 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
