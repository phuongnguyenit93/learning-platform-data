# Lookup method injection bằng @Lookup trong Spring Framework

## 1. Bài toán: singleton cần lấy bean có vòng đời ngắn hơn

Một Spring bean thường có scope `singleton`: trong cùng container, Spring cung cấp cùng một instance cho các lần tra cứu bean đó. Ngược lại, scope `prototype` tạo một instance mới mỗi lần container nhận yêu cầu tạo/lấy bean.

Vấn đề xuất hiện khi một singleton cần **một prototype mới cho mỗi lần chạy nghiệp vụ**. Cách inject trực tiếp sau đây không đáp ứng yêu cầu:

```java
@Component
class BatchProcessor {
    private final WorkUnit workUnit;

    BatchProcessor(WorkUnit workUnit) {
        this.workUnit = workUnit;
    }

    void process() {
        workUnit.run();
    }
}
```

Giả sử `WorkUnit` đã được đăng ký dưới scope `prototype`. Spring resolve constructor dependency **một lần khi tạo `BatchProcessor` singleton**, nên mọi lần `process()` dùng lại đúng instance `workUnit` đã được inject.

`@Lookup` giải quyết trường hợp cần **tra cứu một bean khác vào thời điểm gọi method**. Container sinh một subclass tại runtime để thay thế nội dung một method được đánh dấu `@Lookup` bằng lời gọi tới `BeanFactory`. Vì vậy, singleton có thể gọi method lookup nhiều lần và nhận prototype mới từng lần.

> `@Lookup` không tự làm bean đích trở thành prototype. Scope của bean **được tra cứu** vẫn quyết định số instance: tra cứu một singleton nhiều lần vẫn nhận cùng singleton; tra cứu prototype nhiều lần sẽ nhận các instance mới.

## 2. @Lookup là gì, đặt ở đâu?

Annotation đầy đủ: `org.springframework.beans.factory.annotation.Lookup`, có `@Target(METHOD)` và `@Retention(RUNTIME)`.

Hai cách chỉ ra bean cần tra cứu:

```java
// Spring suy ra bean đích từ kiểu trả về WorkUnit.
@Lookup
protected WorkUnit createWorkUnit() {
    throw new UnsupportedOperationException("Spring must override this method");
}

// Spring dùng bean name cụ thể.
@Lookup("specialWorkUnit")
protected WorkUnit createSpecialWorkUnit() {
    throw new UnsupportedOperationException("Spring must override this method");
}
```

Đây là **hai phương án minh họa độc lập**; một lớp thực tế có thể chỉ dùng phương án phù hợp.

- `@Lookup`, không truyền `value`: resolve bean dựa trên **kiểu trả về** của method, tương đương ý tưởng `getBean(WorkUnit.class, ...)`.
- `@Lookup("specialWorkUnit")`: resolve theo **bean name**, tương đương ý tưởng `getBean("specialWorkUnit", ...)`. Cách này hữu ích khi có nhiều bean cùng kiểu.
- Method có thể `abstract` hoặc có thân mặc định (stub). Spring ghi đè method được phép override khi nó tự tạo bean chứa method đó.
- Method được annotate phải là **instance method có thể bị override**; không dùng `private`, `static` hoặc `final`.
- Lớp chứa lookup method phải có thể subclass; lớp `final` không phù hợp.
- Trị trả về nên là kiểu bean đích hoặc kiểu cha/interface phù hợp; bean đích phải tồn tại và có thể resolve đúng scope lúc lookup.

Nếu bạn khai báo method body ném exception như trên, exception **không xuất hiện** khi gọi bean đã được Spring tạo và enhancement thành công, vì subclass gọi `BeanFactory` thay cho stub. Exception giúp phát hiện việc ai đó khởi tạo class trực tiếp bằng `new` hoặc test không qua Spring.

## 3. Spring làm gì khi ứng dụng chạy?

Luồng làm việc lý tưởng:

```text
ApplicationContext tạo BatchProcessor singleton
  -> phát hiện metadata @Lookup trên createWorkUnit()
  -> Spring tạo subclass động dựa trên CGLIB
  -> singleton thực tế là một instance của subclass
  -> BatchProcessor.process()
      -> gọi createWorkUnit() qua virtual dispatch
      -> implementation do Spring sinh gọi BeanFactory
      -> BeanFactory lấy/tạo bean WorkUnit theo scope được cấu hình
      -> trả WorkUnit cho process()
```

Điều này khác với `@Autowired` trên field/constructor, vốn resolve dependency lúc bean nhận injection. `@Lookup` là **phụ thuộc được lấy khi method chạy**.

Một điểm dễ nhầm: khi method `process()` của singleton gọi `this.createWorkUnit()`, lời gọi vẫn đi vào implementation đã **override trong subclass**, nên có lookup mới. Trong trường hợp này, không nên áp dụng máy móc quy tắc self-invocation của Spring AOP proxy; cơ chế `@Lookup` dựa vào method overriding trên chính đối tượng được container tạo.

Nhưng hành vi đó chỉ đúng khi:

1. Đối tượng gọi là **bean do Spring container trực tiếp tạo**, đã được method injection.
2. Method lookup có thể override.
3. Bean đích đã đăng ký và scope của nó đang hoạt động.
4. Không gọi lookup trên instance do `new` tạo thủ công.

## 4. Ví dụ hoàn chỉnh Java 17+: singleton lấy prototype mới

Ví dụ sử dụng Spring Framework 6.2.x và Java 17, không cần Spring Boot. Tạo cấu trúc:

```text
lookup-demo/
  settings.gradle
  build.gradle
  src/main/java/LookupDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'lookup-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'LookupDemo'
}
```

`src/main/java/LookupDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

public class LookupDemo {

    @Component
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public static class WorkUnit {
        private static final AtomicInteger NEXT = new AtomicInteger();
        private final int id = NEXT.incrementAndGet();

        public int id() {
            return id;
        }
    }

    @Component("namedTask")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public static class NamedTask {
        private final String label;

        public NamedTask(String label) {
            this.label = label;
        }

        public String label() {
            return label;
        }
    }

    @Component
    public static class WorkManager {
        private final WorkUnit constructorInjected;

        // Chỉ inject đúng một lần khi tạo singleton WorkManager.
        public WorkManager(WorkUnit constructorInjected) {
            this.constructorInjected = constructorInjected;
        }

        public WorkUnit fixedUnit() {
            return constructorInjected;
        }

        // Spring tìm bean theo return type WorkUnit.
        @Lookup
        protected WorkUnit createUnit() {
            throw new UnsupportedOperationException(
                    "Only Spring-managed instances support this lookup");
        }

        // Spring tìm bean theo name và truyền label tới constructor.
        @Lookup("namedTask")
        protected NamedTask createNamedTask(String label) {
            throw new UnsupportedOperationException(
                    "Only Spring-managed instances support this lookup");
        }

        public WorkUnit newUnit() {
            return createUnit();
        }

        public NamedTask newNamedTask(String label) {
            return createNamedTask(label);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Spring phải tự tạo các bean definition được đăng ký.
            context.register(WorkUnit.class, NamedTask.class, WorkManager.class);
            context.refresh();

            WorkManager manager = context.getBean(WorkManager.class);

            WorkUnit fixed1 = manager.fixedUnit();
            WorkUnit fixed2 = manager.fixedUnit();
            WorkUnit fresh1 = manager.newUnit();
            WorkUnit fresh2 = manager.newUnit();

            NamedTask task1 = manager.newNamedTask("alpha");
            NamedTask task2 = manager.newNamedTask("beta");

            System.out.println("sameSingleton="
                    + (manager == context.getBean(WorkManager.class)));
            System.out.println("fixedSame=" + (fixed1 == fixed2));
            System.out.println("lookupFresh=" + (fresh1 != fresh2));
            System.out.println("lookupDiffFromFixed="
                    + (fresh1 != fixed1 && fresh2 != fixed1));
            System.out.println("taskNames="
                    + task1.label() + "," + task2.label());
            System.out.println("namedTaskFresh=" + (task1 != task2));
        }
    }
}
```

Chạy bằng Gradle 8+ đã cài:

```bash
gradle run --quiet
# Nếu đã có Gradle Wrapper:
# ./gradlew run --quiet
```

Các dòng mà `System.out.println` của chương trình in ra:

```text
sameSingleton=true
fixedSame=true
lookupFresh=true
lookupDiffFromFixed=true
taskNames=alpha,beta
namedTaskFresh=true
```

Không phụ thuộc giá trị `id` để diễn giải output, vì thứ tự khởi tạo bean có thể thay đổi khi mở rộng ví dụ. Điều cần kiểm tra là **identity của các đối tượng**.

**Giải thích kết quả:**

1. `WorkManager` là singleton; tra cứu cùng bean vẫn trả cùng manager.
2. `fixed1 == fixed2` vì dependency đã được inject một lần khi tạo manager.
3. `createUnit()` được Spring override, gọi BeanFactory theo kiểu `WorkUnit` mỗi lần; `WorkUnit` có scope prototype nên mỗi lần được instance mới.
4. `@Lookup("namedTask")` chỉ định đúng bean name; hai tham số chuỗi được dùng làm **constructor arguments** khi bean prototype `NamedTask` được tạo, nên tên lần lượt là `alpha` và `beta`.
5. Hai `NamedTask` cũng khác identity vì bean có scope prototype.

Spring có thể hiển thị log ở ngoài các dòng `System.out`; chúng không phải stdout do logic ví dụ tự in.

## 5. Truyền tham số vào lookup method

Theo Javadoc của `@Lookup`, khi lookup method có parameters, Spring chuyển chúng thành đối số của lời gọi `BeanFactory.getBean(...)` để dùng làm **tham số constructor hoặc factory method** của bean đích.

Ví dụ cô đọng:

```java
@Lookup("namedTask")
protected NamedTask createNamedTask(String label) {
    return null; // Thân được Spring ghi đè ở runtime.
}

// Khi được gọi từ bean Spring đã enhance:
NamedTask task = createNamedTask("invoice-42");
```

Đây là đoạn trích minh họa, không phải chương trình độc lập. Phải tồn tại bean tên `namedTask` có constructor/factory method nhận được `String` tương ứng. Method lookup không nhận mọi argument như business method theo kiểu "tự bind": từng tham số phải khớp cách Spring tạo bean.

Phân biệt rõ:

- `@Lookup` không thay thế `@Value`, `@Autowired` hoặc cấu hình dependencies cố định.
- Những tham số runtime truyền qua lookup chủ yếu thích hợp với bean được tạo mới (điển hình `prototype`).
- Đừng giả định có thể đổi constructor arguments của một singleton đã tồn tại: scope singleton vẫn giữ instance cũ.
- Nếu bean đích có nhiều constructors/factory methods quá tải, nên thiết kế signature rõ ràng hoặc đăng ký bean bằng phương án ít mơ hồ.

## 6. Lookup theo tên hay theo kiểu trả về?

### Theo kiểu: @Lookup

```java
@Lookup
protected WorkUnit createUnit() {
    return null;
}
```

Ưu điểm là không phụ thuộc bean name dạng chuỗi, phù hợp khi chỉ có một ứng viên được resolve cho kiểu `WorkUnit`. Nếu có nhiều bean cùng kiểu, cấu hình `@Primary`/`@Qualifier` tại definition hoặc chọn lookup theo tên theo yêu cầu nghiệp vụ. Không giả định phương thức không ghi tên sẽ tùy ý chọn một bean khi việc resolve mơ hồ.

### Theo tên: @Lookup("beanName")

```java
@Lookup("specialWorkUnit")
protected WorkUnit createSpecialUnit() {
    return null;
}
```

Cách này giúp yêu cầu chính xác bean `specialWorkUnit`, với điều kiện bean tồn tại và có kiểu phù hợp với return type. Sai tên bean sẽ làm lookup thất bại tại runtime khi gọi method. Trường hợp bean name thay đổi trong quá trình refactor phải cập nhật chuỗi tương ứng.

Cả hai cách **không thêm caching ở lookup method**; chỉ scope của bean đích quyết định có tái sử dụng instance hay không.

## 7. Những giới hạn quan trọng của @Lookup

### 7.1. Class và method cần được phép override

Spring tạo subclass runtime. Các khai báo sau không dùng được cho mục đích override:

```java
// Không dùng làm bean cần được subclass để implement @Lookup.
public final class FinalManager {
    // ...
}

// Method final không thể bị override.
@Lookup
public final WorkUnit createUnit() {
    return null;
}

// Method private không phải virtual override point.
@Lookup
private WorkUnit createPrivateUnit() {
    return null;
}
```

Đây là các **anti-example minh họa**; không ghép chúng vào ví dụ chạy ở mục 4. `static` method cũng không thể được override theo cơ chế instance subclass này. Với các dự án Kotlin, class/method mặc định final nên cần bảo đảm mở rộng được (chẳng hạn dùng `open` hoặc compiler plugin phù hợp).

### 7.2. @Lookup không hoạt động với bean được trả về từ @Bean factory method

Spring cần **quyền tạo instance bằng cơ chế subclassing của container**. Đoạn sau không phải cách đáng tin để kích hoạt `@Lookup`:

```java
@Configuration
class AppConfig {
    @Bean
    WorkManager workManager(WorkUnit workUnit) {
        return new WorkManager(workUnit);
    }
}
```

Đây là anti-example minh họa trên cùng kiểu `WorkManager` của mục 4. Mặc dù Spring quản lý bean sau khi factory method trả về, instance đã được `new WorkManager(...)` bên trong phương thức `@Bean`. Container không thể thay thế đối tượng đang được trả về bằng subclass sinh động cho lookup method. Khi gọi `newUnit()` trên instance đó, stub `createUnit()` có thể ném `UnsupportedOperationException`.

**Cách đúng** là để Spring tự instantiate lớp chứa `@Lookup`, chẳng hạn:

```java
context.register(WorkManager.class);
```

hoặc khai báo `@Component` và bật component scanning phù hợp để Spring xử lý bean definition từ class; bảo đảm không đồng thời tạo thêm một bean `WorkManager` khác bằng `@Bean` gây mơ hồ.

Nếu thực sự cần factory method `@Bean` để tạo manager (ví dụ constructor có logic đặc biệt), dùng `ObjectProvider<WorkUnit>` như mục 9 thay cho `@Lookup`.

### 7.3. Tự new một đối tượng không kích hoạt container

```java
WorkManager manager = new WorkManager(new WorkUnit());
manager.newUnit(); // Stub throws, vì không có Spring-generated subclass.
```

`@Lookup` không phải cơ chế Java reflection biến mọi instance của class thành Spring bean. Chỉ đối tượng container đã tạo với lookup override mới có hành vi mong đợi.

### 7.4. @Lookup không tạo scope và không tự chuyển ngữ cảnh

- Bean đích scope singleton -> lookup nhiều lần vẫn là một singleton.
- Bean đích scope prototype -> mỗi lookup thường là một instance mới.
- Bean đích scope request/session -> phải có request/session scope đang hoạt động. Gọi ngoài context thích hợp có thể gặp lỗi scope không active.
- Lookup chạy trên worker của `@Async` sẽ resolve bean theo **ngữ cảnh hiện có ở thread gọi lookup**, không tự sao chép HTTP request hoặc thread-local context từ thread ban đầu.

### 7.5. Lifecycle của prototype vẫn thuộc trách nhiệm caller

`@Lookup` chỉ yêu cầu **lấy bean**, không bổ sung destruction semantics. Với scope prototype, Spring chạy các bước khởi tạo thường lệ nhưng không tự gọi các destruction callback của từng prototype sau khi caller dùng xong.

Vì vậy, `@PreDestroy` hoặc `DisposableBean.destroy()` của prototype thường **không tự được gọi** chỉ nhờ method lookup hay khi đóng context. Nếu bean cần đóng tài nguyên, thiết kế caller đóng rõ ràng. Ví dụ với một prototype thực thi `AutoCloseable`:

```java
try (ExpensiveUnit unit = manager.newExpensiveUnit()) {
    unit.execute();
}
```

Đây là **mảnh thiết kế minh họa**: giả định `ExpensiveUnit implements AutoCloseable` và manager có lookup method tương ứng. Phải tự bảo đảm `close()` có nghĩa đúng và bean không bị dùng lại sau khi đóng.

## 8. Phân biệt lookup method với @Bean, scoped proxy và ObjectProvider

| Cơ chế | Thời điểm chọn dependency | Điều kiện | Khi dùng |
| --- | --- | --- | --- |
| Inject prototype trực tiếp vào constructor singleton | Một lần khi tạo singleton | Bean prototype đã có definition | Singleton giữ cố định một collaborator; **không** phù hợp nếu muốn instance mới mỗi lần |
| `@Lookup` | Mỗi lần gọi method lookup | Bean chứa method phải được Spring tự instantiate qua class và method override được | Muốn che giấu `BeanFactory` trong code nghiệp vụ, cần prototype mới theo từng lần sử dụng |
| `ObjectProvider<T>.getObject()` | Mỗi lần caller gọi provider | Injection provider hoạt động với cả bean trả về từ `@Bean` factory method | Muốn dependency lookup tường minh, dễ kiểm thử và ít phụ thuộc subclassing |
| Scoped proxy | Mỗi lần gọi method trên proxy (resolve target theo scope) | Scope cấu hình proxy và đang active | Bean dài hạn giữ proxy tới target thuộc scope ngắn hơn, ví dụ request scope |
| `ApplicationContext.getBean(...)` | Mỗi lần gọi container | Caller phải có context/BeanFactory | Công cụ, hạ tầng; business code chấp nhận phụ thuộc trực tiếp Spring container |

Một khác biệt tinh tế: **scoped proxy** thường duy trì một reference proxy trong singleton, còn `@Lookup` làm cho method trả về **bean target được tra cứu ngay lần gọi đó**. Với prototype, bạn có thể lấy instance và sử dụng liên tiếp qua nhiều method trước khi tạo instance tiếp theo; với proxy prototype, mỗi lần invoke method trên proxy có thể resolve target mới (theo cách proxy/scope triển khai). Hãy chọn theo cách collaborator được dùng thực tế.

## 9. Giải pháp thay thế bằng ObjectProvider

`ObjectProvider<T>` thường dễ làm rõ ý định hơn `@Lookup`, nhất là khi class được tạo từ `@Bean` factory method hoặc phải unit test không có Spring.

Ví dụ minh họa hoàn chỉnh logic class:

```java
import org.springframework.beans.factory.ObjectProvider;

public final class WorkManagerWithProvider {
    private final ObjectProvider<WorkUnit> units;

    public WorkManagerWithProvider(ObjectProvider<WorkUnit> units) {
        this.units = units;
    }

    public int runOnce() {
        WorkUnit unit = units.getObject();
        return unit.id();
    }
}
```

Đoạn này là **một class minh họa**, giả định `WorkUnit` được định nghĩa như mục 4 và provider được Spring inject. Không có điều kiện phải subclass `WorkManagerWithProvider`; lớp có thể `final`.

Khai báo trong configuration class:

```java
@Configuration(proxyBeanMethods = false)
class ProviderConfig {
    @Bean
    WorkManagerWithProvider providerManager(
            ObjectProvider<LookupDemo.WorkUnit> units) {
        return new WorkManagerWithProvider(units);
    }
}
```

Ở đây cần dùng `ObjectProvider<LookupDemo.WorkUnit>` và import `ObjectProvider`, `Bean`, `Configuration` tương ứng. Đây là **mảnh cấu hình minh họa**, không phải phần cần thêm vào `LookupDemo.java` để chương trình mục 4 chạy. Với `WorkUnit` prototype, mỗi `getObject()` giải quyết một prototype mới.

Nếu cần truyền runtime constructor args, `ObjectProvider.getObject(Object... args)` có overload thích hợp (bảo đảm bean đích hỗ trợ constructor/factory arguments). Với bean thông thường không cần arguments, dùng `getObject()` là cách đơn giản nhất.

**Vì sao provider dễ test hơn?** Trong unit test, có thể cấp một provider giả trả về các `WorkUnit` mong muốn, rồi kiểm tra số lần gọi và kết quả; không cần khởi tạo Spring ApplicationContext hoặc dựa vào CGLIB.

## 10. Kiểm thử @Lookup đúng cách

### Integration test qua Spring container

Các assertion quan trọng:

```java
WorkManager manager = context.getBean(WorkManager.class);
WorkUnit a = manager.newUnit();
WorkUnit b = manager.newUnit();

assert a != b;                      // Khi WorkUnit là prototype.
assert manager.fixedUnit()
        == manager.fixedUnit();      // Constructor injection cố định.
assert a != manager.fixedUnit();
```

Đây là trích đoạn từ mẫu mục 4; giả định biến `context` đã được khởi tạo đúng và chạy JVM với `-ea` nếu dùng Java `assert`. Trong dự án thực tế, ưu tiên JUnit 5 `assertNotSame` và kiểm thử bằng container.

### Pure unit test, không bật Spring

Với lookup method **cụ thể** (không abstract), bạn có thể tạo subclass thử nghiệm ghi đè phương thức:

```java
class TestWorkManager extends LookupDemo.WorkManager {
    TestWorkManager(LookupDemo.WorkUnit unit) {
        super(unit);
    }

    @Override
    protected LookupDemo.WorkUnit createUnit() {
        return new LookupDemo.WorkUnit();
    }
}
```

Đây là class hỗ trợ test, không thuộc ví dụ chính. Spring có thể subclass ở runtime, nhưng trong unit test bạn chủ động cung cấp implementation. Nếu method lookup khai báo `abstract` thì cả unit test cũng phải cài đặt method trước khi khởi tạo class.

Nếu test chỉ gọi `new WorkManager(...)` rồi kỳ vọng `@Lookup` tự hoạt động, test đó đang bỏ qua cơ chế mà Spring cung cấp. Một integration test với `AnnotationConfigApplicationContext` là cách xác minh chính xác wiring và enhancement.

### Tình huống cần đưa vào test

1. Hai lần lookup cùng prototype trả **reference khác nhau**.
2. Hai lần lookup cùng singleton trả **reference giống nhau**.
3. Khi không chỉ định tên và có nhiều bean cùng kiểu, cấu hình resolve phải xác định rõ ứng viên.
4. `@Lookup("x")` phải trỏ tới bean name thực sự đăng ký.
5. Method có runtime args phải chuyển đúng tham số tới constructor/factory method.
6. Factory-method-created owner bean không được kỳ vọng có lookup override.
7. Các bean scoped như request/session phải được gọi trong context hợp lệ.
8. Nếu prototype giữ tài nguyên, test phải quan sát cleanup ở caller.

## 11. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Mỗi lần gọi vẫn cùng đối tượng | Bean đích thực tế là `singleton` | Kiểm tra `@Scope("prototype")`/bean definition, không chỉ annotation trên method |
| Stub của lookup method bị chạy | Tạo owner bằng `new` hoặc factory method `@Bean` trả instance đã xây dựng | Để Spring instantiate owner từ class definition; hoặc chuyển sang `ObjectProvider` |
| Không thể sinh subclass/override | Class `final`, method `final`/`private`/`static` | Dùng class và instance method có thể override |
| `NoUniqueBeanDefinitionException` | Lookup theo type có nhiều ứng viên không phân giải được | Chỉ định `@Lookup("beanName")` hoặc làm rõ bean selection |
| `NoSuchBeanDefinitionException` | Chưa đăng ký bean đích, sai tên, sai type | Xem bean name, component scan, điều kiện cấu hình, kiểu trả về |
| Scope không hoạt động | Tra cứu request/session bean ngoài ngữ cảnh hợp lệ | Đưa lookup vào scope hợp lệ, hoặc thiết kế lại ranh giới dữ liệu |
| Runtime args không khớp constructor | Parameters của method không phù hợp cách tạo bean | Thiết kế constructor/factory method nhận đúng đối số |
| Prototype giữ tài nguyên mãi | Lầm tưởng `@Lookup` sẽ kích hoạt destruction callback | Caller đóng tài nguyên rõ ràng; dùng `try-with-resources`/`finally` |
| Unit test ném `UnsupportedOperationException` | Test dùng object Java thuần, chưa được Spring enhance | Subclass stub, inject provider hoặc integration test |
| Lỗi trong native-image/AOT hoặc môi trường giới hạn dynamic subclass | Thiết kế phụ thuộc runtime-generated subclass | Kiểm chứng công cụ build/runtime mục tiêu; cân nhắc `ObjectProvider` để giảm phụ thuộc dynamic method replacement |

Lưu ý: loại exception cụ thể có thể được Spring wrap trong ngoại lệ cấp cao hơn khi lỗi xảy ra trong quá trình tạo bean. Hãy xem **root cause** (không chỉ exception ngoài cùng).

## 12. Khi nào nên chọn @Lookup?

Chọn `@Lookup` khi tất cả điều sau đúng:

- Có bean do container tạo cần giữ lâu (điển hình singleton).
- Nó phải lấy một bean khác vào **đúng thời điểm sử dụng**.
- Scope của bean đích đã được xác định, thường là prototype.
- Lớp chứa method được Spring trực tiếp instantiate, có thể subclass và method có thể override.
- Bạn chấp nhận cơ chế container-generated subclass và cần API lookup ngắn gọn.

Nên ưu tiên `ObjectProvider` hoặc factory abstraction khi class có thể được tạo bởi `@Bean`, yêu cầu dễ mock/unit test, hoặc muốn cấu trúc ít phụ thuộc vào bytecode method injection. Dùng scoped proxy khi muốn injection một reference mà mỗi lần gọi đều resolve target theo scope đang hoạt động.

Không dùng `@Lookup` để mặc định giải quyết **thread safety** hoặc quản lý lifetime của tài nguyên: mỗi prototype chỉ là một object mới, còn việc dùng đồng thời và đóng tài nguyên vẫn phải được thiết kế.

## 13. Nguồn chính thức

- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): cơ chế lookup, CGLIB, abstract/concrete methods và giới hạn factory methods.
- [Spring Framework API — @Lookup (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/annotation/Lookup.html): khai báo annotation, chọn target theo type/name, chuyển runtime arguments tới BeanFactory.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton/prototype lifecycle và lý do constructor injection một prototype vào singleton không tạo instance mới mỗi invocation.
- [Maven Central — spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18): artifact version cho ví dụ Gradle.

Các nguyên tắc chính: `@Lookup` là **tra cứu dependency bằng method do Spring ghi đè**, không phải annotation biến scope; scope của target, cách tạo owner và lifecycle của target đều phải được xác định riêng.
