# Giới hạn @Lookup với lớp final và đối tượng do @Bean tạo

## 1. Vấn đề và kết luận cần nắm

Trong Spring Core Container, **lookup method injection** là kỹ thuật để một bean, thường là **singleton**, yêu cầu một bean khác ở thời điểm chạy method, thường là bean **prototype** cần có instance mới cho mỗi công việc. Annotation `@Lookup` cho phép khai báo một method mà Spring sẽ thay thế bằng logic truy xuất bean từ container.

Tuy nhiên, `@Lookup` **không hoạt động với mọi loại class và mọi cách đăng ký bean**. Hai giới hạn cốt lõi:

1. **Class có lookup method không được là `final`, và lookup method không được là `final`.** Spring cần tạo **subclass động** và override method; Java cấm subclass `final class` và cấm override `final method`.
2. **Lookup method injection không hoạt động trên đối tượng được tạo bởi factory method, đặc biệt là sản phẩm trả về từ phương thức `@Bean` trong `@Configuration`.** Spring nhận instance đã được factory method tạo nên không có cơ hội dùng một subclass động để thay thế việc khởi tạo instance đó.

Các giới hạn này được mô tả trực tiếp trong tài liệu *Method Injection* của Spring Framework; đây là giới hạn cơ chế, không phải một quy tắc đặt tên annotation.

**Cách chọn thực tế:** dùng `@Lookup` cho class/method có thể override, được Spring **trực tiếp khởi tạo bằng constructor và quản lý như một bean definition**. Với class `final`, method `final`, hoặc sản phẩm của `@Bean`, hãy cân nhắc **tiêm `ObjectProvider<T>` hoặc `ObjectFactory<T>`**, rồi gọi `getObject()` tại thời điểm cần sử dụng.

## 2. Nhắc lại vì sao cần @Lookup trong phụ thuộc khác phạm vi

Giả sử một `CheckoutService` là singleton nhưng cần `CheckoutAttempt` scope prototype cho mỗi lần xử lý. Nếu viết constructor injection trực tiếp:

```java
@Service
public class CheckoutService {
    private final CheckoutAttempt attempt;

    public CheckoutService(CheckoutAttempt attempt) {
        this.attempt = attempt;
    }

    public void process() {
        attempt.execute();
    }
}
```

Đoạn trên là **mã minh họa**, cần class `CheckoutAttempt` cùng bean definition prototype, và import `@Service`. Singleton `CheckoutService` được tạo một lần; dependency prototype được resolve khi singleton đó được tạo. Vì thế nhiều lần gọi `process()` vẫn thường dùng **cùng object đã inject**, không phải instance mới theo mỗi lời gọi.

Nếu `CheckoutService` đủ điều kiện cho lookup method injection, có thể viết:

```java
@Component
public class CheckoutService {
    public void process() {
        CheckoutAttempt attempt = newAttempt();
        attempt.execute();
    }

    @Lookup("checkoutAttempt")
    protected CheckoutAttempt newAttempt() {
        throw new IllegalStateException("Spring phải override method này");
    }
}
```

Đây cũng là **mã minh họa tích hợp**; cần các import `@Component`, `@Lookup`, bean tên `checkoutAttempt` và method `execute()`. Khi Spring tự tạo một bean `CheckoutService` theo constructor thông thường và xử lý `@Lookup`, container tạo một **subclass động** với phiên bản `newAttempt()` được override. Khi `process()` gọi method đó trên bean do Spring cung cấp, lời gọi được chuyển thành lookup bean đích.

Phần thân method gốc ở trên cố ý ném lỗi để việc **không được Spring override** lộ rõ. Nếu đang sử dụng object do `new CheckoutService()` bên ngoài Spring tạo, method gốc vẫn chạy và ném `IllegalStateException`. Annotation không khiến bytecode của mọi object cùng class tự biến đổi.

Nếu không khai báo tên trong `@Lookup`, Spring có thể resolve bean đích theo **kiểu trả về** của method. Khai báo `@Lookup("checkoutAttempt")` rõ tên hữu ích khi container có nhiều bean cùng kiểu; tên đó phải khớp bean definition.

## 3. Cơ chế kỹ thuật: vì sao Java final chặn được @Lookup

Spring áp dụng **method injection bằng subclass động dựa trên CGLIB**. Về ý tưởng, khi Spring đang tạo bean một class như sau:

```java
public class CommandManager {
    @Lookup("command")
    protected Command obtainCommand() {
        throw new UnsupportedOperationException();
    }
}
```

Spring cần tạo một lớp con có hành vi **tương đương** mã giải thích sau:

```java
// PSEUDOCODE để hình dung cơ chế, không phải Java source Spring tạo ra.
class CommandManagerGeneratedSubclass extends CommandManager {
    @Override
    protected Command obtainCommand() {
        return beanFactory.getBean("command", Command.class);
    }
}
```

Mã thứ hai chỉ là **pseudocode theo ngữ cảnh có `Command`, `beanFactory`**, không biên dịch độc lập; subclass thực do Spring sinh bằng bytecode. Ý nghĩa quan trọng nằm ở từ khóa `extends` và `@Override`:

- Để dùng `extends CommandManager`, `CommandManager` phải cho phép subclassing.
- Để `@Override obtainCommand()`, method phải là instance method có thể override.
- Khi client gọi method trên **instance subclass do container cấp**, Java virtual dispatch sẽ đi vào implementation mà Spring sinh.
- Khi client tự tạo instance gốc bằng `new CommandManager()`, không có subclass này và không có lookup injection.
- Dù Spring override thành công, **scope bean đích vẫn quyết định** mỗi lookup là object mới hay object cũ. `@Lookup` không tự chuyển singleton thành prototype.

### 3.1. Lớp final: không thể sinh subclass

```java
@Component
public final class FinalCommandManager {
    @Lookup("command")
    protected Command obtainCommand() {
        throw new UnsupportedOperationException();
    }
}
```

**Mẫu cấu hình sai; không dùng để chạy:** cần type `Command` tương ứng, nhưng dù bean đích có tồn tại thì Spring vẫn không thể sinh subclass từ `FinalCommandManager`. Không có cơ chế override theo `@Lookup` trên class `final`. Tùy đường tạo bean và phiên bản Spring, vấn đề có thể xuất hiện lúc tạo bean hoặc khi gọi method; **không giả định một exception cố định** trong mọi cấu hình.

Không nên chỉ bỏ `final` cho có nếu tính bất biến của class hoặc giới hạn kiến trúc yêu cầu `final`: có thể giữ class `final` và dùng provider qua constructor.

### 3.2. Method final: subclass cũng không override được

```java
@Component
public class FinalMethodManager {
    @Lookup("command")
    protected final Command obtainCommand() {
        throw new UnsupportedOperationException();
    }
}
```

**Mẫu cấu hình sai.** Class `FinalMethodManager` có thể được subclass, nhưng Java **cấm override** method `protected final obtainCommand()`. Việc có `@Lookup` trên method không loại bỏ cấm đoán này. Một số trường hợp Spring vẫn tạo được bean, nhưng lời gọi method `final` sẽ không được chuyển thành lookup như mong đợi; hành vi lỗi chính xác phụ thuộc cách xử lý cấu hình. Không được dựa vào việc annotation tồn tại làm bằng chứng method injection đang hoạt động.

### 3.3. Các kiểu method khác cũng không phù hợp

`static` method không có virtual dispatch như instance method nên không thể override. `private` method không được subclass override. Constructor không phải method để override. Vì vậy nên thiết kế lookup method thành **instance method `protected` hoặc `public` không `final`**, có kiểu trả về chỉ rõ bean cần lấy. Có thể khai báo `abstract` nếu cơ chế đăng ký bean chấp nhận class trừu tượng đó và Spring tự tạo subclass, hoặc cung cấp một method concrete làm stub (thường thuận tiện hơn với component scanning và unit test).

Ví dụ Java 17 về khả năng override, không cần Spring:

```java
public class FinalRulesDemo {
    static class Parent {
        protected String changeable() { return "parent"; }
        protected final String fixed() { return "fixed"; }
    }

    static class Child extends Parent {
        @Override
        protected String changeable() { return "child"; }
        // Không thể override fixed() ở đây.
    }

    public static void main(String[] args) {
        Parent obj = new Child();
        System.out.println(obj.changeable());
        System.out.println(obj.fixed());
    }
}
```

Lưu thành `FinalRulesDemo.java`, chạy:

```bash
javac FinalRulesDemo.java
java FinalRulesDemo
```

Stdout chính xác:

```text
child
fixed
```

Nếu thêm một method `fixed()` cùng chữ ký vào `Child`, `javac` báo lỗi do không thể override method `final`. Tương tự, nếu đổi `Parent` thành `final class Parent`, câu lệnh `extends Parent` không thể biên dịch. Đây là các quy tắc của Java mà Spring không thể bỏ qua.

## 4. Giới hạn riêng của sản phẩm do @Bean tạo

Đặt cạnh hai cách tạo cùng một loại service:

```java
@Component
public class ContainerCreatedManager {
    @Lookup("taskContext")
    protected TaskContext currentContext() {
        throw new UnsupportedOperationException();
    }
}
```

Ở trường hợp này, Spring có thể trực tiếp chọn class để khởi tạo và thay bằng subclass động khi nó đủ điều kiện. `@Component` và component scanning (hoặc đăng ký class trực tiếp trong `AnnotationConfigApplicationContext`) đưa bean definition để container sở hữu quá trình khởi tạo.

Ngược lại:

```java
@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    FactoryCreatedManager factoryCreatedManager() {
        return new FactoryCreatedManager();
    }
}

public class FactoryCreatedManager {
    @Lookup("taskContext")
    protected TaskContext currentContext() {
        throw new UnsupportedOperationException();
    }
}
```

Đây là **mã minh họa**, cần các import Spring và class `TaskContext`. Ở đây Spring gọi **factory method** `factoryCreatedManager()` và nhận object do `new FactoryCreatedManager()` trả về. Container không trực tiếp chọn một subclass để thay câu lệnh `new` đã nằm trong factory method. **`@Lookup` trên `FactoryCreatedManager.currentContext()` không được thay thế** theo cơ chế lookup method injection thông thường.

Phân biệt kỹ ba tình huống:

| Bean và vị trí annotation | Có thể dùng lookup method injection? | Vì sao? |
|---|---|---|
| `@Component` class non-final, method `@Lookup` non-final, do Spring tự khởi tạo | **Có**, nếu bean definition và lookup target hợp lệ | Spring trực tiếp khởi tạo subclass động |
| Đối tượng **được trả về** bởi `@Bean FactoryCreatedManager factoryCreatedManager()`, class sản phẩm có `@Lookup` | **Không** theo cơ chế chuẩn | Factory tạo sẵn instance sản phẩm; Spring không thay instance gốc thành subclass |
| Method `@Bean` nằm trên `@Configuration` class và trả về một bean khác | **Không phải bản thân `@Lookup`** | `@Bean` là cách khai báo/factory tạo bean; không đồng nghĩa lookup method injection |

**`@Configuration(proxyBeanMethods = true)` không sửa được giới hạn này.** Chế độ đó liên quan đến việc Spring intercept các lời gọi `@Bean` method trong lớp cấu hình để giữ semantics bean reference; nó **khác** việc thay `@Lookup` trong **class sản phẩm** do factory method trả về. Không dùng `proxyBeanMethods=true` như mẹo kích hoạt lookup method injection trên sản phẩm `@Bean`.

Cũng đừng nhầm rằng mọi class được gắn `@Configuration` mặc nhiên không bao giờ dùng `@Lookup`. Điểm cần xét là **bean chứa lookup method được khởi tạo như thế nào**; câu hỏi ở đây nói đến **object được factory method `@Bean` tạo ra**. Tránh khái quát thành “hễ dự án dùng `@Bean` thì mọi `@Lookup` đều vô hiệu”.

## 5. Thí nghiệm Spring Java 17+: @Lookup được ghi đè, @Bean không được ghi đè

Bài thực hành này đặt hai đường khởi tạo cạnh nhau. `ComponentManager` do Spring trực tiếp tạo, có `@Lookup` làm việc; `FactoryManager` được một `@Bean` method trả về, nên method `@Lookup` của nó không được override. Cuối cùng `ProviderManager` cho thấy cách giải quyết trường hợp `@Bean` một cách đáng tin bằng `ObjectProvider`.

**Yêu cầu:** JDK 17+ và Maven 3.9+. Dùng Spring Framework 6.2.0 (Core Container thuần, không yêu cầu Spring Boot hay server).

Cấu trúc:

```text
lookup-limits/
├── pom.xml
└── src/main/java/example/LookupLimitsDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>lookup-limits</artifactId>
    <version>1.0.0</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/LookupLimitsDemo.java`:

```java
package example;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

public class LookupLimitsDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                Config.class, ComponentManager.class)) {

            ComponentManager component = ctx.getBean(ComponentManager.class);
            WorkUnit first = component.createWorkUnit();
            WorkUnit second = component.createWorkUnit();

            System.out.println("Component lookup A: " + first.id());
            System.out.println("Component lookup B: " + second.id());
            System.out.println("Different prototypes: " + (first != second));

            FactoryManager factory = ctx.getBean(FactoryManager.class);
            try {
                factory.createWorkUnit();
                System.out.println("Unexpected factory lookup success");
            } catch (IllegalStateException ex) {
                System.out.println("Factory lookup: original stub invoked");
            }

            ProviderManager provider = ctx.getBean(ProviderManager.class);
            WorkUnit third = provider.createWorkUnit();
            WorkUnit fourth = provider.createWorkUnit();

            System.out.println("Provider lookup A: " + third.id());
            System.out.println("Provider lookup B: " + fourth.id());
            System.out.println("Provider objects differ: " + (third != fourth));
        }
    }

    // Bean prototype được dùng làm target của cả ba cách lookup.
    public static final class WorkUnit {
        private static final AtomicInteger SEQUENCE = new AtomicInteger();
        private final int id = SEQUENCE.incrementAndGet();

        public int id() {
            return id;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public WorkUnit workUnit() {
            return new WorkUnit();
        }

        // Spring nhận FactoryManager đã được factory method tạo.
        @Bean
        public FactoryManager factoryManager() {
            return new FactoryManager();
        }

        // Factory method vẫn dùng provider injection thành công.
        @Bean
        public ProviderManager providerManager(ObjectProvider<WorkUnit> units) {
            return new ProviderManager(units);
        }
    }

    // Class này được đăng ký TRỰC TIẾP với container (qua ctx).
    @Component
    public static class ComponentManager {
        @Lookup("workUnit")
        public WorkUnit createWorkUnit() {
            throw new IllegalStateException("Spring did not override @Lookup");
        }
    }

    // Instance này lại được trả về bởi @Bean factoryManager().
    public static class FactoryManager {
        @Lookup("workUnit")
        public WorkUnit createWorkUnit() {
            throw new IllegalStateException("Factory stub was not overridden");
        }
    }

    // Không cần subclass động: provider giữ logic tra bean khi cần.
    public static final class ProviderManager {
        private final ObjectProvider<WorkUnit> units;

        public ProviderManager(ObjectProvider<WorkUnit> units) {
            this.units = units;
        }

        public WorkUnit createWorkUnit() {
            return units.getObject();
        }
    }
}
```

Điểm cố ý trong thiết kế ví dụ:

- `ComponentManager` là **public static nested class**, non-final và có lookup method public non-final, nên Spring có thể sinh subclass. Class này được đăng ký trực tiếp vào `AnnotationConfigApplicationContext`, không phải sản phẩm của method `@Bean`.
- `FactoryManager` cũng non-final và method cũng non-final; ví dụ loại trừ yếu tố `final` để chỉ ra **riêng giới hạn khởi tạo qua factory method**.
- `ProviderManager` cố ý là `final`, vẫn hoạt động với `ObjectProvider<WorkUnit>` vì provider không cần subclass `ProviderManager`.
- `WorkUnit` có thể là `final` vì nó là **bean đích được tra cứu**, không phải **class cần tạo subclass để override `@Lookup`**. Giới hạn `final` ở đây áp dụng đối với **class chứa lookup method**, không mặc nhiên áp dụng cho mọi bean được lookup. Đừng gán nhầm hạn chế cho target.
- Hai method bị annotation `@Lookup` có stub ném exception để rõ ràng xác định khi nào Spring đã override.

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.LookupLimitsDemo
```

Stdout dự kiến của chương trình (không kể log riêng của Maven):

```text
Component lookup A: 1
Component lookup B: 2
Different prototypes: true
Factory lookup: original stub invoked
Provider lookup A: 3
Provider lookup B: 4
Provider objects differ: true
```

**Đối chiếu từng dòng:**

1. `ctx.getBean(ComponentManager.class)` nhận instance do Spring tạo với subclass động. Hai lần gọi `component.createWorkUnit()` resolve `workUnit` scope prototype và nhận đối tượng có ID 1 và 2.
2. `Different prototypes: true` xác nhận hai tham chiếu khác nhau. `@Lookup` tự nó **không** tạo prototype; annotation `@Scope(PROTOTYPE)` trên target mới là yếu tố tạo mới mỗi lần lookup.
3. `factory.createWorkUnit()` chạy **stub trong class gốc**; lỗi `IllegalStateException` được bắt để chương trình tiếp tục. Đây là hậu quả đối tượng `FactoryManager` được `@Bean` factory method tạo sẵn.
4. `provider.createWorkUnit()` gọi `ObjectProvider.getObject()`; lần gọi thứ ba và thứ tư tạo `WorkUnit` ID 3 và 4.
5. `Provider objects differ: true` minh họa việc dùng provider vẫn làm việc trong một class `final` được tạo từ `@Bean`.

Nếu thay class `ComponentManager` thành `final` hoặc method `createWorkUnit()` thành `final`, **đừng coi mẫu này vẫn hợp lệ**. Nó vi phạm yêu cầu subclass/override của method injection. Không cần đưa những cấu hình sai này vào ví dụ chạy chính, vì kết quả startup/thời điểm lỗi có thể phụ thuộc cách container tạo bean và cấu hình annotation.

## 6. Vấn đề với Kotlin: class và method mặc định final

Kotlin mặc định tạo class và member function **final**, trái với Java nơi class/method thường có thể kế thừa nếu không đánh dấu `final`. Vì vậy mã Kotlin kiểu:

```kotlin
@Component
class TaskManager {
    @Lookup("task")
    fun newTask(): Task {
        error("Not overridden")
    }
}
```

có thể gặp đúng giới hạn subclass/override. Đây là mã minh họa, cần `Task` và Spring Kotlin setup; không phải chương trình độc lập.

Có thể dùng `open class TaskManager` và `open fun newTask()` trong ngữ cảnh phù hợp. Trong dự án có plugin Kotlin `kotlin-spring`/`all-open`, một số annotation Spring có thể khiến class/member được biên dịch thành `open` theo cấu hình; **phải xác nhận bytecode và plugin setup thực tế**, không coi mọi `final` đã biến mất. Nếu không muốn phụ thuộc việc class có mở được hay không, `ObjectProvider<T>` thường biểu đạt nhu cầu rõ ràng hơn.

## 7. Vì sao @Bean/proxyBeanMethods có thể gây nhầm lẫn?

Có nhiều cơ chế dùng kỹ thuật tạo proxy/subclass trong Spring nhưng chúng giải quyết các vấn đề khác nhau:

| Cơ chế | Mục tiêu | Đối tượng được can thiệp |
|---|---|---|
| `@Lookup` method injection | Resolve bean khi method được gọi, ví dụ lấy prototype mới | **Class chứa lookup method** do container trực tiếp tạo |
| `@Configuration(proxyBeanMethods = true)` | Intercept lời gọi giữa các method `@Bean` nhằm áp dụng semantics bean trong full configuration class | **Lớp cấu hình** và lời gọi `@Bean` method của nó |
| Spring AOP proxy | Áp dụng advice ở các join point hỗ trợ như lời gọi method qua proxy | Tham chiếu bean được proxy (JDK interface proxy/CGLIB proxy tùy cấu hình) |
| `ObjectProvider<T>` | Tra cứu dependency khi code gọi `getObject()` | Provider tương tác với `BeanFactory`; không cần subclass client |

Việc thấy một `@Configuration` được enhance bằng CGLIB **không có nghĩa** object do `@Bean` method trả về cũng được Spring tạo thành subclass hỗ trợ `@Lookup`. Việc bật `proxyBeanMethods` là quyết định cho semantics configuration class, không phải cách sửa lookup method trên sản phẩm `@Bean`.

Các loại proxy/AOP có thể có hạn chế riêng với `final`; tuy nhiên, tránh lấy một quy tắc AOP rồi áp dụng máy móc vào mọi trường hợp `@Lookup`. Khi debug, luôn xác định **bean nào** được subclass, **method nào** được override và **ai** tạo instance.

## 8. Thay @Lookup bằng ObjectProvider khi có giới hạn

Một thiết kế có thể hoạt động ngay cả khi class được `final` và do `@Bean` tạo:

```java
public final class InvoiceProcessor {
    private final ObjectProvider<InvoiceWork> works;

    public InvoiceProcessor(ObjectProvider<InvoiceWork> works) {
        this.works = works;
    }

    public void process(String invoiceId) {
        InvoiceWork work = works.getObject();
        work.execute(invoiceId);
    }
}

@Configuration(proxyBeanMethods = false)
class InvoiceConfig {
    @Bean
    InvoiceProcessor invoiceProcessor(ObjectProvider<InvoiceWork> works) {
        return new InvoiceProcessor(works);
    }
}
```

Đây là **mã tích hợp minh họa**, không phải chương trình độc lập. Cần import `ObjectProvider`, `@Configuration`, `@Bean`, đăng ký `InvoiceWork` bean và cung cấp `execute(String)`. Cách này có hai ưu điểm trực tiếp:

1. `InvoiceProcessor` có thể giữ `final` để bảo vệ thiết kế class.
2. `@Bean` factory nhận provider do Spring inject và chủ động truyền vào constructor; không cần Spring thay thế object đã tạo.

**Cách `ObjectProvider` hoạt động:** tại `works.getObject()`, Spring tra bean đích theo định nghĩa và scope hiện hành. Nếu `InvoiceWork` là prototype, mỗi lần tra thường tạo instance mới; nếu singleton, provider trả cùng singleton. Việc dùng provider không tự động đổi scope và không bảo đảm thread safety.

Khi phụ thuộc có thể tùy chọn, `getIfAvailable()`/ `ifAvailable(...)` có thể phù hợp. Khi có nhiều implementation, hãy khai báo qualifier/ưu tiên phù hợp hoặc duyệt `stream()`/`orderedStream()`; đừng dùng `getObject()` mà bỏ qua lỗi chọn nhiều bean. Việc sử dụng provider để tra bean qua tên/kiểu chỉ khác cách gọi, còn quy tắc scope và bean resolution vẫn thuộc Spring container.

### 8.1. Chọn giữa @Lookup và provider

| Tiêu chí | `@Lookup` | `ObjectProvider<T>` |
|---|---|---|
| Resolve ở thời điểm method chạy | Có, khi Spring override thành công | Có, khi gọi API provider |
| Class client được phép final | Không | Có |
| Method client được phép final | Lookup method: không | Method dùng provider có thể final |
| Bean client được `@Bean` method tạo | Không hỗ trợ lookup injection trên sản phẩm | Hỗ trợ tiêm provider vào `@Bean` method hoặc constructor |
| Cần Spring sinh subclass client | Có | Không |
| Mức độ thể hiện phụ thuộc trong constructor | Lookup dependency xuất hiện gián tiếp trong annotation method | Provider được khai báo trực tiếp ở constructor |
| Test thuần Java khi không khởi tạo Spring | Cần stub/override lookup method nếu gọi nó | Có thể truyền fake provider; test kiểm soát lookup rõ hơn |
| Bean đích prototype | Mỗi lookup được container tạo mới theo scope | Mỗi `getObject()` được container tạo mới theo scope |
| Bean đích singleton | Trả về singleton hiện có | Trả về singleton hiện có |
| Cleanup prototype | Client tự chịu trách nhiệm | Client tự chịu trách nhiệm |

Một phương án bổ sung là **factory do ứng dụng định nghĩa** như `WorkUnitFactory` với method `newWorkUnit()`; factory đó có thể tự nhận `ObjectProvider` hoặc được cài bằng implementation phù hợp. Khi logic tạo có nhiều tham số nghiệp vụ, factory với interface rõ ràng có thể dễ test hơn việc gọi trực tiếp container.

### 8.2. Dọn dẹp prototype do provider hoặc lookup trả về

Bất kể dùng `@Lookup` hay `ObjectProvider`, Spring **không tự gọi destroy callback cho prototype bean** sau khi giao instance cho caller. Nếu prototype giữ stream, socket, connection hay tài nguyên cần release, caller/resource owner phải đóng đúng lúc. Ví dụ một `WorkSession implements AutoCloseable` có thể được dùng:

```java
try (WorkSession session = sessions.getObject()) {
    session.execute();
}
```

Đoạn này là minh họa trong ngữ cảnh có `ObjectProvider<WorkSession> sessions`. Với kết quả `@Lookup`, dùng `try (WorkSession session = createSession()) { ... }` theo nguyên tắc tương tự. **Không tự đóng bean singleton dùng chung** sau mỗi lần lookup; cleanup phải phù hợp đúng ownership và scope.

## 9. Một số lỗi thường gặp trong ứng dụng

### 9.1. “Tôi đã thêm @Lookup nhưng method vẫn chạy code gốc”

Kiểm tra **đối tượng được tạo như thế nào**:

- Nếu code gọi `new Service()`, đó là object Java thuần, Spring không tạo subclass cho object đã tạo bên ngoài container.
- Nếu service là kết quả một `@Bean` factory method, lookup method injection không thay method trên sản phẩm đó.
- Nếu service thuộc `final class`, hoặc method được đánh dấu `final`, CGLIB không thể override như yêu cầu.
- Nếu method là `private`/`static`, cũng không nên kỳ vọng cơ chế override.
- Nếu bean được quản lý trực tiếp đúng cách, xác minh bean definition, tên bean đích và scope.

Nếu method gốc trả về `null` thay vì ném lỗi, vấn đề có thể xuất hiện như `NullPointerException` rất xa nơi đăng ký bean. Với ví dụ học tập, một stub ném `IllegalStateException` giúp lỗi lộ rõ; với production, thường ưu tiên một thiết kế provider/factory dễ kiểm soát.

### 9.2. “Bean đích là final, nên @Lookup không được phép?”

Không nhất thiết. Hạn chế subclassing của `@Lookup` nằm ở **class chứa method cần ghi đè**. Bean đích, chẳng hạn `WorkUnit`, có thể là class `final` được Spring tạo bằng `@Bean`; container vẫn có thể resolve nó nếu bean definition hợp lệ. Trong ví dụ chạy ở phần 5, `WorkUnit` là `final` nhưng component `@Lookup` vẫn lấy được nó.

### 9.3. “@Lookup có bảo đảm object mới ở mọi lời gọi?”

Không. `@Lookup` resolve bean theo **scope**. Nếu bean đích là singleton thì hai lookup có thể trả cùng object. Khi cần một instance cho mỗi lần chạy, phải thật sự khai báo scope prototype hoặc một scope phù hợp ngữ nghĩa công việc.

### 9.4. “Bật proxyBeanMethods = true có giải quyết @Lookup trên @Bean product?”

Không. Nó thay đổi cách intercept method `@Bean` ở class `@Configuration`, không biến sản phẩm do factory trả về thành subclass lookup của sản phẩm đó. Hãy dùng `ObjectProvider`, `ObjectFactory` hoặc factory abstraction nếu cần resolve muộn.

### 9.5. “Vì sao test dùng new không hoạt động, nhưng chạy trong Spring thì có?”

Vì `@Lookup` dựa vào **subclass do Spring tạo**. Unit test gọi trực tiếp `new ComponentManager()` sẽ chạy method gốc. Có thể test qua integration context, tạo test subclass override lookup method để trả fake, hoặc refactor dùng provider được truyền qua constructor. Các bài test nên khẳng định số instance trong phạm vi cần thiết, không chỉ kiểm tra annotation có tồn tại.

### 9.6. “Với nhiều bean cùng return type, @Lookup không ghi tên vẫn chạy?”

Phụ thuộc quy tắc chọn bean của Spring, qualifier và `@Primary`. Nếu không xác định duy nhất một target, lookup theo return type có thể thất bại do nhập nhằng. `@Lookup("beanName")` chỉ định rõ bean target, miễn là tên và type tương thích.

### 9.7. “Có nên dùng @Lookup để giải quyết vòng phụ thuộc hoặc scope web?”

`@Lookup` chủ yếu giải quyết **lúc nào cần tra bean**; nó không phải công cụ chung để chữa mọi vòng phụ thuộc. Với request/session scope, phương án `ObjectProvider` hoặc scoped proxy thường trực quan hơn, nhưng thao tác vẫn phải diễn ra khi scope cần thiết đang hoạt động. Nếu không có active request, không được giả định lookup sẽ tự tạo ra request context.

## 10. Checklist triển khai và kiểm chứng

Trước khi chấp nhận một `@Lookup` trong dự án Spring, trả lời lần lượt:

1. **Bean chứa lookup method:** Spring có trực tiếp tạo instance của class này từ constructor bean definition, hay object lại được `@Bean`/factory method bên ngoài trả về?
2. **Khả năng override:** Class có `final` không? Method có `final`, `private`, `static` không? Với Kotlin, plugin `all-open` có thật sự mở class/member?
3. **Bean đích:** Tên trong `@Lookup("...")` có tồn tại? Nếu tra theo type, có một ứng viên xác định được không?
4. **Scope đích:** Có thật sự là `prototype` khi muốn nhận object mới? Nếu là singleton, kết quả có thể cùng tham chiếu qua nhiều lookup.
5. **Đường gọi:** Đang gọi method trên bean **do Spring trả về**, hay trên một object tự `new`/bản sao khác?
6. **Tài nguyên và đồng thời:** Object được lấy có nắm tài nguyên cần đóng, mutable state hoặc scoped context phụ thuộc thread không?
7. **Test:** Có test thực tế rằng hai lần lấy prototype là hai instance khác nhau, và với class do `@Bean` tạo thì provider thay thế hoạt động?

Phép thử nhỏ có thể dùng trong integration test:

```java
ComponentManager manager = ctx.getBean(ComponentManager.class);
WorkUnit a = manager.createWorkUnit();
WorkUnit b = manager.createWorkUnit();
boolean fresh = a != b;
```

Đây là **mã minh họa trong ngữ cảnh có `ctx` Spring context** từ ví dụ phần 5. `fresh` là `true` khi `workUnit` prototype và lookup injection được áp dụng thành công. Không suy ra chỉ từ tên method `createWorkUnit` hoặc annotation mà bỏ qua việc chạy thực.

## 11. Câu hỏi tự kiểm tra

**1. Vì sao `final class` ngăn `@Lookup` hoạt động?**  
Vì Spring cần sinh subclass động để override method; Java không cho phép một class khác `extends` lớp `final`.

**2. Vì sao `final method` trong một class không final vẫn không hợp lệ?**  
Vì dù Spring có thể subclass class đó, method `final` vẫn không thể override.

**3. Một `@Bean` method trả về object có method `@Lookup`; Spring tự ghi đè method đó không?**  
Không theo cơ chế chuẩn. Factory đã tạo sẵn object; container không thể thay việc tạo object thành một subclass động.

**4. `@Configuration(proxyBeanMethods=true)` có chữa được vấn đề trên không?**  
Không. Nó can thiệp lời gọi các phương thức `@Bean` trong configuration class; không tự tạo subclass cho sản phẩm `@Bean`.

**5. Bean target là `final class` có luôn ngăn một bean khác dùng `@Lookup` để tìm nó không?**  
Không. Class cần có khả năng subclass là class **chứa lookup method**; target class chỉ phải đáp ứng quy tắc tạo và scope của bean target.

**6. Nếu client phải là `final` hoặc được tạo từ `@Bean`, nên dùng gì?**  
Dùng `ObjectProvider<T>`/ `ObjectFactory<T>` hoặc một factory rõ ràng, gọi lookup ở đúng điểm cần bean.

**7. `@Lookup` của một bean target singleton có tạo instance mới mỗi lần gọi không?**  
Không. Lookup chỉ lấy bean theo scope; singleton vẫn thường trả cùng instance.

## Tài liệu chính thức

- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): nêu trực tiếp giới hạn `final class`, `final method` và sản phẩm của `@Bean` factory method.
- [Spring Framework API — @Lookup](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/factory/annotation/Lookup.html): semantics annotation, lookup theo bean name/return type và yêu cầu bean do container khởi tạo qua constructor.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype và lý do cần lookup đúng thời điểm.
- [Spring Framework API — ObjectProvider](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): giải pháp provider thay thế cho lookup method injection.
