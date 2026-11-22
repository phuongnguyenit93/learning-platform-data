# Tiêm trường, setter và phương thức nhiều tham số với `@Autowired`

## 1. Mục tiêu và phạm vi

Spring Core Container có thể tự cung cấp dependency cho một object do container quản lý qua nhiều điểm tiêm (*injection points*). Bài này tập trung vào ba kiểu sử dụng `@Autowired` trên **instance field**, **JavaBean setter**, và **phương thức có tên tùy ý, nhận nhiều tham số**. Đây là những cơ chế liên quan nhau nhưng có khác biệt quan trọng về thời điểm tiêm, trạng thái đối tượng, cách xử lý dependency thiếu và khả năng kiểm thử.

Sau khi học, bạn có thể:

1. Viết và đọc đúng `@Autowired` trên trường `private`, trên setter `setX(...)` và trên phương thức `configure(A, B, ...)`.
2. Giải thích vì sao cả **field và method injection** xảy ra **sau khi Java constructor chạy**; Spring thực hiện nó khi tạo **Spring-managed bean**, không phải tự chạy trên một object được `new` tùy ý.
3. Phân biệt phương thức nhiều tham số `required=true` (mặc định) với `@Autowired(required=false)` và tham số `Optional<T>`.
4. Biết cách Spring chọn bean theo type, qualifier, primary và xử lý các tình huống thiếu hoặc có nhiều candidate.
5. Quan sát trực tiếp **một bean được field-inject, một bean setter-inject và một bean có hai tham số method-inject**, có ví dụ riêng cho phương thức nhiều tham số tùy chọn.
6. Dùng được Java 17+, Maven, Spring Framework 7.0.9 với lệnh chạy và expected stdout xác định.

**Phạm vi:** chỉ Spring Framework Core Container thuần; không sử dụng Spring Boot, HTTP server, database, `@SpringBootApplication` hoặc auto-configuration. Quy tắc cụ thể về Java constructor injection chỉ được so sánh khi nó giúp hiểu ba kiểu injection chính.

## 2. Ba cơ chế đặt cạnh nhau

| Kiểu injection | Ví dụ annotation | Tham số | Thời điểm | Hệ quả thiết kế |
| --- | --- | --- | --- | --- |
| **Field** | `@Autowired private Gateway gateway;` | Không có tham số method | **Sau construction**, khi Spring population field | Rất ngắn nhưng dependency bị ẩn khỏi constructor; không tự nhiên với `final` |
| **Setter** | `@Autowired void setGateway(Gateway g)` | Thường một | **Sau construction**, Spring resolve argument và gọi setter | Hợp lý cho property có giá trị mặc định/cho phép cấu hình lại; reference mutable nếu setter công khai |
| **Arbitrary method** | `@Autowired void prepare(Gateway g, Formatter f)` | **Một hoặc nhiều**, tên bất kỳ | **Sau construction**, Spring resolve **các tham số** rồi gọi method | Có thể cấu hình nhiều dependency trong một thao tác có chủ đích |
| Constructor (đối chiếu) | `@Autowired Service(Gateway g)` hoặc một constructor duy nhất không annotation | Một hoặc nhiều | **Trước/suốt construction** | Hợp đồng rõ, hỗ trợ fields `final`, unit test thuận lợi |

Điểm thường gây nhầm: **setter injection không phải một hệ thống Spring đặc biệt tách khỏi method injection**. Setter `setGateway(Gateway)` là **trường hợp riêng** của phương thức cấu hình mà Spring có thể gọi. `@Autowired` không yêu cầu method tên `set...`, và phương thức nhiều tham số có thể tên `initializeClients`, `configure`, `prepare` hoặc tên khác.

Tất cả các dạng trên đều cần một **bean đích thuộc context** và hạ tầng xử lý annotation. Mặc định `AnnotationConfigApplicationContext` đăng ký các annotation processors thiết yếu; trong đó có `AutowiredAnnotationBeanPostProcessor`. Container phải tìm bean candidates cho injection point rồi mới có reference để cấp.

**`@Autowired` không tự tạo một implementation bất kỳ từ interface.** Ví dụ `@Autowired Gateway gateway` cần có bean Gateway được đăng ký và phù hợp; nếu thiếu, Spring thường báo lỗi tạo bean, không tự `new Gateway`.

## 3. Field injection: ngắn, nhưng dependency bị ẩn

Đoạn cú pháp:

~~~java
// Snippet trong một Spring-managed bean:
@Autowired
private Gateway gateway;

public String route() {
    return gateway.id();
}
~~~

Điểm quan trọng:
- Spring có thể inject **private instance field** nhờ cơ chế phản chiếu thích hợp. Field không cần setter hay `public`; annotation nằm ngay trên field.
- Injection xảy ra **sau lúc constructor tạo instance**. Nếu constructor đọc field này trước khi Spring cấp nó, giá trị thường vẫn là `null` (trừ khi class tự khởi tạo field).
- Cần **Spring-managed bean**. `new FieldClient()` ngoài Spring không kích hoạt `@Autowired`. Nếu không có giá trị khởi tạo khác, dùng field lúc đó có thể gây `NullPointerException`.
- **Field `final` nên được gán ở constructor hoặc initializer trong Java**; không sử dụng field injection như đường thông thường để cung cấp required dependency vào một final field.
- `@Autowired` mặc định có `required=true`. Khi không có candidate phù hợp để inject một required field, bean creation có thể thất bại.
- `@Autowired(required=false)` cho field thật sự optional có thể **bỏ qua việc gán**, giữ giá trị field mặc định. Không dùng cách này để che một dependency vốn bắt buộc.

**So với constructor injection:** Một constructor `Service(Gateway gateway)` cho phép Java caller truyền fake và giữ `private final Gateway gateway`. Với field injection, mã test tự `new Service()` không nhận được dependency trừ khi dùng test seam, reflection hoặc context thật. Vì thế constructor injection thường phù hợp hơn cho **required business dependency**, còn field injection được hỗ trợ nhưng cần nhận biết rõ trade-off.

**Thread safety:** Một Spring singleton field-injected không mặc nhiên thread-safe. Việc được inject một reference không làm object cộng tác thành immutable hay đồng bộ hóa trạng thái của nó. Nếu reference không cần thay đổi sau startup, thiết kế bằng constructor + `final` thường làm invariant rõ hơn.

## 4. Setter injection: JavaBean setter là một config method

Một setter injection có dạng:

~~~java
// Snippet đặt trong class có interface Gateway.
private Gateway gateway;
private int calls;

@Autowired
public void setGateway(Gateway gateway) {
    this.gateway = gateway;
    calls++;
}
~~~

Khi Spring tạo bean:
1. Constructor của bean được chạy.
2. Spring nhận diện method có `@Autowired`.
3. Bean factory resolve một dependency `Gateway` phù hợp.
4. Spring gọi `setGateway(resolvedGateway)` **một lần trong quá trình injection thông thường**.
5. Business code có thể dùng field đã được cấu hình khi bean được khởi tạo xong.

Điều kiện không phải chỉ có tên `set...`: `@Autowired` là thứ làm method được xem như injection point. Nếu setter không annotation và cũng không được cấu hình inject bằng cơ chế khác, Spring **không mặc nhiên phải gọi nó** chỉ vì method bắt đầu bằng `set`.

Setter có thể là `public`, `protected` hoặc không-public khi khả năng truy cập của môi trường cho phép. Các ví dụ chạy độc lập ở dưới dùng method `public` cho dễ quan sát. Trong các ứng dụng JPMS dùng Java module path, cần xem yêu cầu `opens`/reflection; bài này chạy trên classpath thông thường.

### Khi nào setter hữu ích?

- Dependency **thật sự optional** có default behavior hợp lệ.
- Cấu hình khởi tạo của một class legacy đã tồn tại mà không thể sửa constructor.
- Một property có thể được điều chỉnh lại bằng API công khai theo hợp đồng rõ ràng.

Nhưng **mở setter cho dependency bắt buộc** có thể cho phép Java caller tạo bean ở trạng thái chưa đầy đủ, và các caller khác có thể thay reference sau đó. Với một singleton được dùng nhiều luồng, thay đổi mutable dependency mà không có đồng bộ đúng sẽ tạo rủi ro.

**Vì sao có thể fail lúc startup?** Nếu setter được annotate `@Autowired` mặc định required, mà không có bean Gateway phù hợp, Spring thường không khởi tạo xong bean. Việc setter chỉ có một tham số không khiến nó tự biến thành optional.

## 5. Phương thức nhiều tham số: mọi dependency được resolve trước lời gọi

Spring hỗ trợ config method có tên bất kỳ:

~~~java
// Snippet: Gateway và Formatter là các interfaces trong demo.
private Gateway gateway;
private Formatter formatter;

@Autowired
public void configure(Gateway gateway, Formatter formatter) {
    this.gateway = gateway;
    this.formatter = formatter;
}
~~~

Với method trên, Spring phải tìm **cả Gateway và Formatter** trước khi gọi `configure(...)`. Nếu injection point required và thiếu một tham số bắt buộc, bean creation có thể thất bại; method không được gọi thành công với một danh sách đối số “nửa vời”.

Có thể dùng một method để đặt **một nhóm phụ thuộc có liên quan**; ví dụ gateway và formatter phối hợp trong một đơn vị cấu hình. Nếu chúng không có liên hệ nghiệp vụ chặt chẽ, gộp 12 tham số vào một method để né constructor dài không giải quyết vấn đề nhiều trách nhiệm của class.

### Tên method và số lượng tham số

- `configure(Gateway, Formatter)` và `setParts(Gateway, Formatter)` đều có thể được Spring xử lý nếu được annotate; đây **không** phải JavaBeans setter đơn tham số theo convention, nhưng là arbitrary config method của Spring.
- Có thể dùng `@Qualifier` trên **tham số cụ thể** khi nhiều beans cùng type, chẳng hạn `configure(@Qualifier("primaryGateway") Gateway g, Formatter f)`.
- `@Autowired` trên **declaration của method** dùng cho method injection. Đặt `@Autowired` riêng lên từng parameter không phải cách thông thường để làm method đó được tự động gọi bởi Core Container.
- Các method không-public vẫn có thể được hỗ trợ theo khả năng truy cập, nhưng tránh thiết kế phụ thuộc quá nặng vào reflection khi cần chạy trên module path.
- Phương thức `static` không phải đích autowiring instance thông thường; dependency nên nằm ở bean instance thay vì global static state.

**Thứ tự:** Javadoc của `AutowiredAnnotationBeanPostProcessor` mô tả field injection được xử lý sau construction và trước các autowired config methods. Không nên dựa vào **thứ tự tuyệt đối giữa nhiều methods độc lập** của cùng một bean khi thiết kế business rule; nếu phải chạy công việc initialization **sau tất cả các injections**, dùng lifecycle callback phù hợp.

## 6. `required=false`: phương thức nhiều tham số bị bỏ qua toàn bộ

Đây là phần khác biệt đặc biệt quan trọng giữa **method injection** và cách nhiều người suy đoán về null:

~~~java
// Snippet: Gateway có bean, nhưng Telemetry có thể vắng mặt.
@Autowired(required = false)
public void attach(Gateway gateway, Telemetry telemetry) {
    // Chỉ chạy nếu resolve được toàn bộ tham số cần thiết.
}
~~~

Nếu context có Gateway nhưng **không có Telemetry**, Spring **không gọi `attach`**. Nó không tự gọi `attach(gateway, null)`. Thuộc tính `required=false` ở đây áp dụng cho **injection point của method**, nghĩa là khi một dependency cần thiết không thỏa, có thể **bỏ qua cả method**. Điều này phù hợp với tài liệu Spring Framework: non-required method không được gọi nếu một trong các dependency thiếu.

| Tình huống | `@Autowired` method required | `@Autowired(required=false)` method |
| --- | --- | --- |
| Có đủ Gateway và Telemetry | Spring resolve và gọi method | Spring resolve và gọi method |
| Có Gateway, thiếu Telemetry | Thường fail bean creation | **Bỏ qua toàn bộ method**, không gán một nửa |
| Không có cả hai | Thường fail bean creation | **Bỏ qua toàn bộ method** |
| Có nhiều Gateway candidates, không chọn được | Có thể fail vì ambiguity | Không nên coi `required=false` là cơ chế chọn tùy tiện hoặc che conflict |

Trong các phương thức nhiều tham số cần vừa **chạy khi có dependency A**, vừa **chấp nhận thiếu B**, hãy cân nhắc biểu diễn riêng tham số B thành `Optional<B>` (hoặc dùng provider/default strategy). Điều đó khác rõ ràng với việc đánh dấu **cả method** non-required.

Ví dụ:

~~~java
@Autowired
public void observe(
        Gateway gateway, Optional<Telemetry> telemetry) {
    // Method vẫn được gọi khi có Gateway, dù telemetry = Optional.empty().
}
~~~

Dù `Optional<T>` có thể biểu diễn vắng mặt, **đừng dùng Optional để biến business dependency thực sự bắt buộc thành không bắt buộc**. Khi thiếu Gateway là lỗi không thể vận hành, nên để context fail-fast thay vì âm thầm chạy ở chế độ sai.

## 7. Phân giải nhiều candidates, qualifiers, collection và nullability

### Một type có nhiều beans

Nếu có `fastGateway` và `safeGateway` cùng implement `Gateway`, một injection point chỉ khai báo `Gateway` có thể mơ hồ:

~~~java
// Snippet áp dụng cho arbitrary config method:
@Autowired
public void configure(
        @Qualifier("fastGateway") Gateway gateway,
        Formatter formatter) {
    // ...
}
~~~

Cần import `org.springframework.beans.factory.annotation.Qualifier`, đăng ký bean tên/qualifier phù hợp. `@Qualifier` giúp **lọc candidate**; nó không tạo Gateway và cũng không đổi Java type. `@Primary` có thể đặt ưu tiên bean khi resolve single-valued dependency trong điều kiện phù hợp.

**Không khẳng định Spring luôn tìm theo tên field trước rồi mới theo type**. Spring resolution chủ yếu theo type, cùng metadata qualifier/primary, generic và các quy tắc khác. Việc trùng tên field/parameter với bean name có thể có vai trò nhưng không nên dùng nó thay hợp đồng lựa chọn rõ khi có nhiều implementations.

### Nhiều beans muốn inject cùng lúc

Spring còn hỗ trợ:
- `List<Gateway>` hoặc `Gateway[]` để nhận các beans phù hợp (quy tắc ordering có thể bị ảnh hưởng bởi `@Order`/`Ordered`).
- `Map<String, Gateway>` để dùng **bean names** làm keys.
- Các điểm inject vào collection bắt buộc có quy tắc riêng theo từng trường hợp; **không** tự suy ra lúc nào thiếu beans sẽ thành empty collection, nhất là khi so sánh với constructor/factory method special cases.

### Optional của từng tham số

`Optional<T>` tại injection point là cách diễn đạt vắng bean. `ObjectProvider<T>` là một API Spring cho **lookup khi cần**, với `getIfAvailable()` khác `getObject()`; cái sau yêu cầu một bean phù hợp và có thể lỗi nếu thiếu. Với `@Autowired(required=false)` trên setter, cả setter bị bỏ qua khi dependency vắng — không cần có một lệnh `setX(null)`.

`@Nullable` được Spring hỗ trợ tại injection points qua những annotation nullability thích hợp theo version, nhưng cần chọn đúng package/semantics. Trong bài, `Optional<T>` thuần Java 17 được dùng để tránh lệ thuộc thêm vào một nullability annotation cụ thể.

## 8. Demo Maven Java 17: field, setter, method nhiều tham số và optional method

Một project Java 17 duy nhất dùng Spring Framework **7.0.9**. Nó chạy ba thí nghiệm có kiểm soát:

1. **Java `new` ngoài container:** field `@Autowired` của `FieldClient` chưa có reference.
2. **Context cơ bản:** có Gateway và Formatter, nhưng **không** có Telemetry. Spring inject field, gọi setter và multi-parameter method. Phương thức non-required `attach(Gateway, Telemetry)` **bị bỏ qua**, trong khi `observe(Gateway, Optional<Telemetry>)` vẫn được gọi với empty.
3. **Context có Telemetry:** cả hai dependency được cấp, nên `attach(...)` được gọi; `Optional<Telemetry>` nhận bean hiện diện.
4. **Thiếu required field:** tạo một bean `MissingClient` có `@Autowired Telemetry` nhưng không khai báo Telemetry, quan sát startup bị từ chối.

Mọi lớp trong demo đều khai báo **cùng một file Java**, làm ví dụ độc lập và dễ chạy. Không cần Spring Boot, web, database hoặc JUnit.

### 8.1. Cấu trúc project

~~~text
injection-forms-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── InjectionFormsDemo.java
~~~

Trước khi thực hành, xác nhận **JDK 17+**, **Maven 3.9+** và repository Maven Central/mirror truy cập được.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>injection-forms-demo</artifactId>
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
                    <mainClass>demo.InjectionFormsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven giải quyết `spring-context` và các Spring artifacts nền theo dependency graph; không cần tự tải các JAR transitive. `maven.compiler.release=17` đặt target Java 17, và Exec Maven Plugin chạy main class cùng dependency classpath.

### 8.3. `src/main/java/demo/InjectionFormsDemo.java`

~~~java
package demo;

import java.util.Optional;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class InjectionFormsDemo {
    private InjectionFormsDemo() {
    }

    @FunctionalInterface
    public interface Gateway {
        String id();
    }

    @FunctionalInterface
    public interface Formatter {
        String format(String name);
    }

    @FunctionalInterface
    public interface Telemetry {
        String id();
    }

    public static final class FieldClient {
        @Autowired
        private Gateway gateway;

        public boolean ready() {
            return gateway != null;
        }

        public String gatewayId() {
            return gateway.id();
        }
    }

    public static final class SetterClient {
        private Gateway gateway;
        private int setterCalls;

        @Autowired
        public void setGateway(Gateway gateway) {
            this.gateway = gateway;
            setterCalls++;
        }

        public int calls() {
            return setterCalls;
        }

        public String gatewayId() {
            return gateway.id();
        }
    }

    public static final class MultiClient {
        @Autowired
        private Gateway fieldGateway;
        private Gateway gateway;
        private Formatter formatter;
        private int methodCalls;
        private boolean fieldReadyDuringMethod;

        @Autowired
        public void configure(Gateway gateway, Formatter formatter) {
            this.fieldReadyDuringMethod = fieldGateway != null;
            this.gateway = gateway;
            this.formatter = formatter;
            methodCalls++;
        }

        public int calls() {
            return methodCalls;
        }

        public boolean fieldReadyDuringMethod() {
            return fieldReadyDuringMethod;
        }

        public String result(String name) {
            return gateway.id() + "|" + formatter.format(name);
        }
    }

    public static final class OptionalClient {
        private int optionalMethodCalls;
        private int observationCalls;
        private boolean telemetryPresent;
        private String state = "default";

        @Autowired(required = false)
        public void attach(Gateway gateway, Telemetry telemetry) {
            optionalMethodCalls++;
            state = gateway.id() + ":" + telemetry.id();
        }

        @Autowired
        public void observe(Gateway gateway, Optional<Telemetry> telemetry) {
            observationCalls++;
            telemetryPresent = telemetry.isPresent();
        }

        public int optionalMethodCalls() {
            return optionalMethodCalls;
        }

        public int observationCalls() {
            return observationCalls;
        }

        public boolean telemetryPresent() {
            return telemetryPresent;
        }

        public String state() {
            return state;
        }
    }

    public static final class MissingClient {
        @Autowired
        private Telemetry telemetry;
    }

    @Configuration(proxyBeanMethods = false)
    public static class BaseConfig {
        @Bean
        public Gateway gateway() {
            return () -> "GW";
        }

        @Bean
        public Formatter formatter() {
            return name -> "Hello," + name;
        }

        @Bean
        public FieldClient fieldClient() {
            return new FieldClient();
        }

        @Bean
        public SetterClient setterClient() {
            return new SetterClient();
        }

        @Bean
        public MultiClient multiClient() {
            return new MultiClient();
        }

        @Bean
        public OptionalClient optionalClient() {
            return new OptionalClient();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExtraConfig {
        @Bean
        public Telemetry telemetry() {
            return () -> "TR";
        }
    }

    public static void main(String[] args) {
        // Lệnh new thuần Java KHÔNG chạy Spring post-processors.
        FieldClient plain = new FieldClient();
        System.out.println("manual.field.ready=" + plain.ready());

        // Có Gateway và Formatter nhưng KHÔNG có Telemetry.
        try (var base =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            FieldClient field = base.getBean(FieldClient.class);
            SetterClient setter = base.getBean(SetterClient.class);
            MultiClient multi = base.getBean(MultiClient.class);
            OptionalClient optional = base.getBean(OptionalClient.class);

            System.out.println("base.field.ready=" + field.ready());
            System.out.println("base.field.gateway=" + field.gatewayId());
            System.out.println("base.setter.calls=" + setter.calls());
            System.out.println("base.setter.gateway=" + setter.gatewayId());
            System.out.println("base.multi.calls=" + multi.calls());
            System.out.println("base.multi.fieldBeforeMethod="
                    + multi.fieldReadyDuringMethod());
            System.out.println("base.multi.value=" + multi.result("Lan"));
            System.out.println("base.optional.calls="
                    + optional.optionalMethodCalls());
            System.out.println("base.optional.state=" + optional.state());
            System.out.println("base.optional.observeCalls="
                    + optional.observationCalls());
            System.out.println("base.optional.telemetryPresent="
                    + optional.telemetryPresent());
        }

        // Thêm Telemetry, các injection points đều thỏa mãn.
        try (var with = new AnnotationConfigApplicationContext(
                BaseConfig.class, ExtraConfig.class)) {
            OptionalClient optional = with.getBean(OptionalClient.class);

            System.out.println("with.optional.calls="
                    + optional.optionalMethodCalls());
            System.out.println("with.optional.state=" + optional.state());
            System.out.println("with.optional.observeCalls="
                    + optional.observationCalls());
            System.out.println("with.optional.telemetryPresent="
                    + optional.telemetryPresent());
            System.out.println("with.optional.singleton="
                    + (optional == with.getBean(OptionalClient.class)));
        }

        // Required field thiếu bean: refresh() thất bại.
        try (var missing = new AnnotationConfigApplicationContext()) {
            missing.register(BaseConfig.class);
            missing.registerBean(MissingClient.class);
            missing.refresh();
        } catch (BeansException expected) {
            System.out.println("missingRequired.failed=true");
        }
    }
}
~~~

### 8.4. Giải thích code theo ba injection styles

- **FieldClient:** field `private Gateway gateway` có `@Autowired`, Spring điền bean Gateway sau construction. Với object `new FieldClient()` bên ngoài Spring, `ready() == false`.
- **SetterClient:** method `setGateway(Gateway)` có annotation. Bộ đếm `setterCalls` giúp xác nhận method được Spring gọi **một lần** ở lần tạo bean trong ví dụ. Method cũng có thể được gọi bằng Java code thường nếu caller gọi trực tiếp; annotation không độc quyền cho Spring.
- **MultiClient:** method `configure(Gateway,Formatter)` không mang tên `set...` nhưng vẫn là injection point. Spring resolve cả hai tham số. `fieldGateway` được inject qua field trước config method trong cơ chế này, nên cờ `fieldReadyDuringMethod` là `true`.
- **OptionalClient:** `attach(Gateway,Telemetry)` được đánh dấu `required=false`. Trong context base chỉ có Gateway, Spring **bỏ qua toàn bộ method**, giữ `state="default"` và `optionalMethodCalls=0`. Nhưng `observe(Gateway,Optional<Telemetry>)` vẫn được gọi; tham số optional là empty.
- **ExtraConfig:** thêm Telemetry, lần này `attach` chạy một lần và `observe` nhận `Optional.of(...)`. Hai methods không phụ thuộc vào **thứ tự giữa chúng**, nên kết quả cuối cùng ổn định.
- **MissingClient:** một required field Telemetry, được đăng ký riêng trong context thiếu Telemetry. `refresh()` có thể ném `BeansException`; demo catch và ghi đúng một dòng xác nhận thất bại.

`BaseConfig` dùng `@Bean` factory methods trả các object Java. **Bean do `@Bean` trả về vẫn được Spring post-process**, nên các trường/methods có `@Autowired` được xử lý dù `FieldClient` không hề mang `@Component`.

`@Configuration(proxyBeanMethods=false)` phù hợp vì các factory methods không gọi trực tiếp nhau. Không sửa `BaseConfig` để tự gọi `gateway()` trong những factory methods khác rồi suy luận đó là cùng Spring singleton: với chế độ proxy tắt, lời gọi Java thông thường có thể tạo object khác.

## 9. Chạy CLI và expected stdout

Tại thư mục `injection-forms-demo` chứa `pom.xml`, chạy:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Ba lệnh kiểm tra môi trường có output phụ thuộc hệ điều hành, JDK và Maven. Lệnh cuối biên dịch với `javac` thông qua Maven Compiler Plugin, sau đó chạy `demo.InjectionFormsDemo` với classpath Spring.

**18 dòng stdout xác định do chính các lệnh `System.out.println` trong `main` tạo ra** (không tính log/diagnostic của Maven hay Spring):

~~~text
manual.field.ready=false
base.field.ready=true
base.field.gateway=GW
base.setter.calls=1
base.setter.gateway=GW
base.multi.calls=1
base.multi.fieldBeforeMethod=true
base.multi.value=GW|Hello,Lan
base.optional.calls=0
base.optional.state=default
base.optional.observeCalls=1
base.optional.telemetryPresent=false
with.optional.calls=1
with.optional.state=GW:TR
with.optional.observeCalls=1
with.optional.telemetryPresent=true
with.optional.singleton=true
missingRequired.failed=true
~~~

**Nhóm quan sát cần nắm:**

| Dòng stdout | Bằng chứng |
| --- | --- |
| `manual.field.ready=false` | Java `new` riêng không kích hoạt autowiring |
| `base.field.ready=true`, `gateway=GW` | Spring cấp bean vào private instance field |
| `base.setter.calls=1` | Spring gọi method setter `@Autowired` khi tạo bean |
| `base.multi.calls=1`, `multi.value=GW|Hello,Lan` | Method tên tùy ý nhận **hai dependencies**, xử lý kết quả |
| `base.multi.fieldBeforeMethod=true` | Field injection đã chạy trước autowired config method của bean này |
| `base.optional.calls=0`, `state=default` | Non-required multi-param method **không chạy** khi thiếu Telemetry |
| `base.optional.observeCalls=1`, `telemetryPresent=false` | Method required vẫn chạy nhờ `Optional.empty()` ở tham số optional |
| `with.optional.calls=1`, `state=GW:TR` | Khi đủ dependencies, non-required method được gọi |
| `with.optional.telemetryPresent=true` | `Optional<Telemetry>` chứa bean hiện diện |
| `with.optional.singleton=true` | OptionalClient là singleton trong context thứ hai |
| `missingRequired.failed=true` | Thiếu required field làm bean creation thất bại, không âm thầm gán null |

**Không chép log exception cố định** cho `missing` context: Spring có thể ghi cảnh báo khi startup fail, với stack trace/message phụ thuộc phiên bản/logging. Expected output chỉ là các dòng do source ứng dụng chủ động in.

## 10. Java thuần `javac`/`java`: tự tạo object và tự cấp tham số

Cả field và method injection đều có điểm tương đồng với Java thông thường: **một object được tạo, rồi caller gán field/gọi setter hoặc config method**. Spring tự động hóa việc tìm bean và gọi đúng injection points, còn Java thuần phải làm việc đó bằng code rõ ràng.

Tạo file riêng `PureInjectionTypes.java`:

~~~java
public class PureInjectionTypes {
    interface Gateway {
        String id();
    }

    interface Formatter {
        String format(String name);
    }

    static final class Client {
        Gateway field;
        Gateway setterGateway;
        Gateway multiGateway;
        Formatter formatter;
        int setterCalls;

        void setGateway(Gateway gateway) {
            setterGateway = gateway;
            setterCalls++;
        }

        void configure(Gateway gateway, Formatter formatter) {
            multiGateway = gateway;
            this.formatter = formatter;
        }

        String multiResult(String name) {
            return multiGateway.id() + "|" + formatter.format(name);
        }
    }

    public static void main(String[] args) {
        Client client = new Client();
        System.out.println("before.manual.field="
                + (client.field != null));

        Gateway gateway = () -> "G";
        Formatter formatter = name -> "Hi," + name;

        client.field = gateway;
        client.setGateway(gateway);
        client.configure(gateway, formatter);

        System.out.println("after.manual.field="
                + (client.field != null));
        System.out.println("after.manual.setter.calls="
                + client.setterCalls);
        System.out.println("after.manual.multi="
                + client.multiResult("Lan"));
    }
}
~~~

Biên dịch bằng **JDK 17+** trong thư mục chứa file, không cần Maven hay Spring:

~~~bash
javac PureInjectionTypes.java
java PureInjectionTypes
~~~

Stdout chính xác:

~~~text
before.manual.field=false
after.manual.field=true
after.manual.setter.calls=1
after.manual.multi=G|Hi,Lan
~~~

Ví dụ chứng minh setter và method nhiều tham số vốn là **lời gọi Java bình thường**. Spring thêm khả năng resolve dependency từ context. Không phải cứ tạo một object Java có setter là Spring tự động inject nó; object phải thuộc cơ chế đăng ký/quản lý bean.

## 11. Các lỗi thường gặp và cách chẩn đoán đúng tầng

| Triệu chứng | Khả năng gây lỗi | Cách xác minh |
| --- | --- | --- |
| Field `@Autowired` vẫn null sau `new` | Object **ngoài Spring container** | Dùng constructor injection trong test hoặc lấy bean từ context |
| Field dùng ngay trong constructor dẫn đến NPE | Injection được thực hiện **sau construction** | Đưa dependency required vào constructor |
| Spring báo không có bean `Gateway` | Không đăng ký bean phù hợp trong context | Kiểm `@Bean`, scan, qualifier, context scope |
| Spring báo nhiều `Gateway` candidates | Type ambiguous | Dùng `@Primary`/`@Qualifier` rõ ràng |
| Setter không được gọi | Không có annotation/cấu hình inject, hoặc non-required method bị skip | Xác minh injection metadata và available candidates |
| Setter required fail lúc startup | Thiếu một dependency bắt buộc | Đọc `UnsatisfiedDependencyException` và `Caused by` |
| Multi-method bị skip dù có tham số A | Dùng `required=false` nhưng còn thiếu tham số B | Tất cả arguments phải được resolve để method được gọi |
| Muốn method chạy dù B vắng | Required `B` đang được biểu diễn sai | Dùng `Optional<B>`/provider hoặc default theo domain |
| Cùng một method chạy hai lần ngoài ý muốn | Test/caller có thể tự gọi thêm method; bean lifecycle/registration cần kiểm tra | Phân biệt lời gọi Java trực tiếp và lời gọi khi Spring inject |
| `@Autowired` static field không hoạt động | Static injection không phải cơ chế được hỗ trợ | Đặt dependency trong bean instance, bỏ global mutable state |
| Một private field trên Java module path bị chặn reflection | Module/package chưa cho phép reflective access | Xem `opens` và module setup; classpath demo không gặp vấn đề đó |
| `@Autowired(required=false)` mà code vẫn NPE | Đã bỏ qua field/method nhưng business không có default hợp lệ | Thiết kế optional thật, kiểm tra null/Optional hoặc dùng no-op implementation |
| Bean bị tạo quá sớm trước processor | Custom factory/post-processor làm lifecycle bất thường | Xem thứ tự registration và BeanPostProcessor |
| `mvn` không resolve `spring-context` | Artifact/repository/JDK/proxy | Kiểm POM GAV, `mvn -version`, Maven Central/mirror |

**Không nhầm thiếu bean với thiếu JAR:** thiếu package lúc compile là vấn đề build classpath; `NoSuchBeanDefinitionException` hay `UnsatisfiedDependencyException` trong Spring là vấn đề graph/configuration. Nếu factory method ném exception thì phải đọc nguyên nhân gốc, không chỉ nhìn nhãn “autowire error”.

### Lưu ý khi có XML hoặc cấu hình hỗn hợp

`@Autowired` hoạt động nhờ các bean post-processors. `AnnotationConfigApplicationContext` đăng ký processors thường dùng; một XML context cấu hình thủ công có thể cần bật annotation configuration, chẳng hạn `<context:annotation-config/>`. XML property injection có thể có thứ tự/ưu tiên riêng khi kết hợp annotation và explicit property values; tránh đặt hai cách cấu hình xung đột trên một property mà không có lý do rõ.

Các class **`BeanPostProcessor` và `BeanFactoryPostProcessor`** do bạn tự tạo cũng có lifecycle đặc biệt. Không giả định `@Autowired` trong chính những processor ấy được xử lý như bean ứng dụng thông thường; tài liệu Spring khuyến nghị cấu hình dependencies cho processors bằng factory method/XML rõ ràng.

## 12. Bài tập dự đoán, sau đó kiểm chứng

Giữ một bản source gốc để đối chiếu; với mỗi thử nghiệm, chỉnh trên bản sao và khôi phục code trước khi làm thử nghiệm tiếp theo.

1. **Bỏ `@Autowired` trên FieldClient:** dự đoán `base.field.ready` và điều gì xảy ra khi gọi `gatewayId()`. Vì sao `@Bean` tạo được FieldClient nhưng không có trường đã được inject?
2. **Thêm một setter thứ hai:** viết một method `setFormatter(Formatter)` có `@Autowired` trong SetterClient, thêm field và bộ đếm; kiểm tra method được gọi lúc bean creation.
3. **Đổi tên `MultiClient.configure` thành `prepareComponents`:** output logic giữ nguyên không? Vì sao tên method không quyết định khả năng autowiring?
4. **Xóa bean `Formatter`:** dự đoán MultiClient required method bị lỗi ở bước tạo bean, không nhận `null`.
5. **Chỉ thêm Telemetry vào context:** dự đoán `optionalMethodCalls=1` và `telemetryPresent=true` trong OptionalClient.
6. **Bỏ Telemetry nhưng vẫn muốn method chạy:** chuyển `attach(Gateway, Telemetry)` thành `attach(Gateway, Optional<Telemetry>)` và bỏ `required=false`; xử lý empty trong method.
7. **Thêm hai bean Gateway:** cố tình gây ambiguity, chọn một bằng `@Primary` hoặc đặt `@Qualifier("mainGateway")` trên **tham số method**.
8. **Cho Getter vào constructor:** refactor FieldClient để nhận Gateway qua constructor và giữ field `final`, viết test bằng Java `new FieldClient(fake)`. So sánh với field injection.
9. **Tạo bean qua component scan:** gắn `@Component` cho MultiClient, quét package thích hợp thay vì `@Bean` method, bảo đảm không có hai bean definitions trùng type.
10. **Non-required method có hai tham số:** đổi `attach` thành method có ba tham số, trong đó một type không có bean; xác nhận cả method được skip.
11. **Quan sát lifecycle:** thêm `InitializingBean.afterPropertiesSet()` vào MultiClient, kiểm tra các references đã có trước init callback.
12. **Dùng provider:** thay một optional parameter bằng `ObjectProvider<Telemetry>`, gọi `getIfAvailable()` để minh họa lookup theo nhu cầu.
13. **Pure Java comparison:** sửa `PureInjectionTypes` để không gọi `configure`, dự đoán `multiResult` lỗi vì thiếu state; Spring required injection giúp phát hiện lỗi wiring sớm hơn khi tạo bean.
14. **Thử hai contexts:** tạo hai context BaseConfig độc lập, so reference `FieldClient`; Spring singleton là phạm vi theo bean definition/container, không phải một instance trên toàn JVM.

### Checklist hiểu bài

- [ ] Field injection và setter/method injection diễn ra **sau constructor** với Spring-managed bean.
- [ ] Setter là một trường hợp đặc biệt của autowired configuration method.
- [ ] Arbitrary method có thể có **tên tùy ý và nhiều tham số**.
- [ ] Multi-argument method required đòi resolve được các required args.
- [ ] Non-required method **bị skip toàn bộ** nếu không thỏa một dependency cần thiết; không nhận một nửa đối số.
- [ ] `Optional<T>` ở tham số diễn đạt vắng dependency theo cách khác với `required=false` trên method.
- [ ] Biết dùng qualifiers khi có nhiều candidates cùng type.
- [ ] Không nhầm `new` ngoài context với bean được Spring quản lý.
- [ ] Dự đoán chính xác 18 stdout lines của Maven demo và 4 dòng của Java thuần.
- [ ] Biết chọn constructor injection cho required dependencies và không lạm dụng mutable setter.

## 13. Tổng kết và tài liệu chính thức

**Tổng kết ngắn gọn:** Spring hỗ trợ tiêm dependency vào **field**, **setter** và **phương thức nhiều tham số** thông qua cùng cơ chế `@Autowired` trên bean thuộc container. Sự khác biệt không chỉ ở cú pháp:
- Field injection gán trường trực tiếp sau construction.
- Setter injection là lời gọi method cấu hình một dependency (thông thường).
- Multi-argument method injection resolve nhiều dependencies trước khi gọi một method tùy tên.
- Non-required method được phép bỏ qua **toàn bộ lời gọi** khi thiếu một dependency bắt buộc, còn `Optional<T>` cho phép method chạy với tham số optional ở trạng thái empty.
- Hãy lựa chọn cơ chế theo hợp đồng của object và khả năng kiểm thử, không chỉ theo số dòng code.

Nguồn tài liệu:
- [Spring Framework – Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework – Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework – Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring API – AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Java 17 – Optional API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)

**Ghi nhớ:** Annotation không thay thế bean registration. Hãy luôn hỏi **đối tượng có do Spring quản lý không**, **injection point yêu cầu những tham số nào**, **thiếu tham số thì fail hay skip method**, và **dependency có thực sự tùy chọn không**. Trả lời bốn câu hỏi này giúp bạn sử dụng field/setter/multi-parameter injection có chủ đích và debug đúng khi cấu hình thay đổi.