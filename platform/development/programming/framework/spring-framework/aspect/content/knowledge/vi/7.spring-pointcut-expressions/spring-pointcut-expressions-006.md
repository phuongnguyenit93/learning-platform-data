# @within và @target theo annotation của kiểu trong Spring AOP

## 1. Bài toán: chọn Spring bean theo annotation trên class

Khi nhiều Spring service triển khai những tác vụ khác nhau, ta có thể muốn áp cùng một advice (ghi audit, đo thời gian, log chẩn đoán) lên **những service có đánh dấu một annotation ở cấp kiểu**, thay vì thêm annotation vào từng method hoặc hard-code danh sách tên class.

Spring AOP hỗ trợ hai pointcut designator gần nhau:

- `@within(com.example.aop.TracedType)`: chọn các **method execution join point nằm trong những kiểu có annotation được chỉ định**. Theo cách diễn đạt của Spring Framework, với Spring AOP đây là các method execution **được khai báo trong kiểu có annotation đó**.
- `@target(com.example.aop.TracedType)`: chọn method execution join point khi **class của đối tượng target đang thực thi** mang annotation được chỉ định.

Chúng đều sử dụng annotation **trên kiểu**, nhưng **không cùng ý nghĩa khái niệm**. `@within` quan tâm phạm vi kiểu **khai báo execution**, còn `@target` quan tâm **class runtime của target object** phía sau Spring proxy.

**Phạm vi bài:** cú pháp, matching, annotation placement, proxy và những bẫy thực tế của **Spring Framework / Spring AOP @AspectJ**. Không xem `@within`/`@target` là AspectJ weaving; Spring AOP vẫn chỉ hỗ trợ join point dạng **method execution của Spring-managed bean thông qua proxy**.

### Khi hai designator có vẻ giống nhau

Nếu một class `PaymentService` được gắn `@TracedType` và tự khai báo method `pay()`, thì một lời gọi `pay()` từ bean khác qua Spring proxy thường đồng thời phù hợp `@within(TracedType)` và `@target(TracedType)`.

Vì thế, **quan sát cả hai advice cùng chạy trong một ví dụ đơn giản là bình thường**, không chứng minh hai biểu thức đồng nghĩa trong mọi trường hợp. Sự phân biệt quan trọng khi xem **nơi khai báo method, kế thừa, kiểu thực thi, interface, proxy kind** và việc annotation có thật sự hiện diện trên target class hay không.

## 2. Cú pháp Spring AOP và điều kiện tiên quyết

Một annotation đánh dấu kiểu:

```java
package com.example.typecut;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TracedType {
    String value() default "";
}
```

Hai pointcut:

```java
@Aspect
public class TypeSelectionAspect {
    @Before("@within(com.example.typecut.TracedType)")
    public void beforeWithin() {
        // Chạy khi method execution khớp @within.
    }

    @Before("@target(com.example.typecut.TracedType)")
    public void beforeTarget() {
        // Chạy khi method execution khớp @target.
    }
}
```

Đây là **đoạn Java minh họa**; muốn chạy trong Spring cần đưa `TypeSelectionAspect` thành bean, bật AOP support, cung cấp dependencies, có target Spring bean và có caller đi qua proxy. Cần import `org.aspectj.lang.annotation.Aspect` và `Before`.

Các điều kiện Spring-specific:

1. **Annotation có `@Target(ElementType.TYPE)`.** Cả hai designator ở đây đều chọn annotation cấp type, không phải `@Target(ElementType.METHOD)`.
2. **Dùng `@Retention(RetentionPolicy.RUNTIME)` cho ví dụ này.** Nó giúp Spring/AspectJ pointcut xử lý và bind annotation tại runtime; không trông cậy vào annotation chỉ có `SOURCE` hoặc suy rằng một retention policy khác sẽ được Spring AOP hỗ trợ giống nhau.
3. **`@Aspect` class là Spring bean.** Dùng `@Aspect` + `@Component` trong vùng scan hoặc trả về aspect từ phương thức `@Bean`.
4. **Bật cơ chế Spring AOP @AspectJ.** Trong Java-config Spring Framework dùng `@EnableAspectJAutoProxy`; Spring Boot thường tự cấu hình khi có AOP starter phù hợp.
5. **Target cũng phải là Spring bean.** `new PaymentService()` ngoài container sẽ không được interceptor Spring AOP nhận diện.
6. **Call path phải đi qua proxy** và method phải proxy được; `this.method()`, constructor, field access, class/method `final` trong CGLIB có giới hạn riêng.
7. **Có `aspectjweaver` trên classpath** để Spring đọc/khớp biểu thức pointcut. Không cần `-javaagent` cho Spring proxy AOP thông thường.

Điều quan trọng: `@target` trong biểu thức pointcut **không phải** annotation Java `@Target` dùng để khai báo nơi được phép đặt annotation. Một bên là **AspectJ pointcut expression**, một bên là **meta-annotation của Java**.

## 3. Phân biệt ý nghĩa của @within và @target

| Tiêu chí | `@within(TracedType)` | `@target(TracedType)` |
| --- | --- | --- |
| Ý nghĩa Spring AOP | Method execution nằm trong kiểu được đánh dấu; tài liệu Spring nhấn mạnh **kiểu khai báo method** | Class của **target object** đang thực thi mang annotation |
| Yếu tố cần kiểm tra | Kiểu chứa method execution, annotation trên kiểu ấy | Kiểu runtime của đối tượng target đứng sau Spring proxy và annotation của kiểu |
| Đặt `@TracedType` ở đâu trong ví dụ điển hình? | Trên class khai báo method | Trên class của target bean |
| Chọn các method theo annotation của chính method? | **Không**; việc ấy dành cho `@annotation` | **Không**; cũng là annotation cấp type |
| Với method khai báo trong một class mang annotation và target cũng là class đó | Thường match | Thường match |
| Khi method được kế thừa, override, khai báo qua interface | Cần kiểm tra kiểu khai báo và cách Spring resolve method | Cần kiểm tra annotation trên class target thực tế và cách Spring resolve type/proxy |
| Với class không mang annotation | Không match theo kiểu khai báo thông thường | Không match nếu target class thực tế cũng không mang annotation |
| Có thay đổi giới hạn Spring proxy? | Không | Không |

Định nghĩa trên dựa vào tài liệu **Spring Framework Pointcuts**. Không tự chuyển chúng thành câu “`@within` luôn match superclass/subclass” hay “`@target` luôn match mọi method kế thừa”. Với kế thừa và interface, **chính annotation placement, cơ chế Java annotation inheritance và khả năng resolve method của Spring** quyết định kết quả runtime.

### Khác với `@annotation`

```java
@TracedType
public class PaymentService {
    public void pay() { }

    @AuditedOperation
    public void refund() { }
}
```

Giả sử `@AuditedOperation` là annotation `METHOD` tự định nghĩa và class là một Spring bean:

- `@within(TracedType)` và `@target(TracedType)` có mục đích chọn execution theo **kiểu PaymentService**; không yêu cầu method `pay`/`refund` có riêng `@TracedType`.
- `@annotation(AuditedOperation)` chọn theo **annotation trên method**, không tự áp dụng lên `pay()` chỉ vì class có `@TracedType`.
- Nếu cần vừa annotation cấp class vừa giới hạn method cụ thể, kết hợp `execution(...) && @within(...)` hoặc `execution(...) && @target(...)`; nếu cần **hai annotation đồng thời**, dùng thêm `@annotation(...)`.

Đừng dùng `@target` để tìm annotation trên **tham số** hoặc trên **return type**; hai trường hợp ấy có cơ chế/biểu thức khác và không phải nội dung của điểm cắt này.

## 4. Giới hạn kiểu trong pointcut: vì sao không nên dùng biểu thức quá rộng?

Biểu thức ngắn:

```java
@Before("@target(com.example.typecut.TracedType)")
public void trace() {
    // ...
}
```

có thể khiến Spring phải xét **rất nhiều ứng viên bean/method** trước khi xác định annotation của target; nhất là `@target` có yếu tố target runtime. Trong ứng dụng có nhiều bean hạ tầng, pointcut quá rộng có thể làm auto-proxy creator phải làm thêm việc, hoặc gây lỗi proxy ở bean hạ tầng không mong muốn (ví dụ bean final được xét để proxy trong cấu hình class-based).

Nên giới hạn type/package/method rõ ràng:

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && @target(com.example.typecut.TracedType)"
)
public void beforeSpecificServiceMethod() {
    // ...
}
```

- `execution(public * ... )` yêu cầu public method execution.
- `com.example.typecut..*Service` giới hạn vùng package và tên class.
- `perform(..)` giới hạn method có tên cụ thể, bất kỳ số tham số.
- `&& @target(TracedType)` còn yêu cầu class target có annotation.

Nếu muốn cùng logic theo kiểu khai báo method, thay `@target` bằng `@within`. Hai đoạn trên là **mã minh họa**, không phải project chạy độc lập.

Trong project thật, chọn scope **theo package/bean và contract** thay vì chọn tất cả class trong ứng dụng. Khi loại bỏ một method khỏi interception, viết test để xác minh nó thực sự bị loại bỏ.

## 5. Demo Java 17+ chạy được: cùng annotation cấp class, hai counters

Ví dụ Spring Framework thuần dưới đây xác nhận **một class được gắn annotation** kích hoạt cả `@within` và `@target`; một class không gắn annotation không kích hoạt advice theo type annotation trong ví dụ. Hai advice tăng counter nhưng **không in log**, tránh phụ thuộc vào thứ tự chạy giữa các advisors.

Môi trường: **Java 17+**, **Spring Framework 6.2.18**, **AspectJ Weaver 1.9.24**, Gradle có plugin `application`. Các phiên bản dependency này có trên Maven Central. Không dùng Spring Boot trong demo để quan sát rõ `@EnableAspectJAutoProxy`.

### 5.1. Cây thư mục

```text
spring-type-annotation-pointcuts/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/typecut/
    ├── AppConfig.java
    ├── TracedType.java
    ├── MarkedService.java
    ├── PlainService.java
    ├── TypeSelectionAspect.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-type-annotation-pointcuts'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'org.springframework:spring-aop:6.2.18'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
}

application {
    mainClass = 'com.example.typecut.Main'
}
```

Spring Framework 6.x yêu cầu Java 17+. Ở project Spring Boot thực tế, nên dựa vào dependency management/BOM của Boot, không ghép phiên bản Spring Framework độc lập khi chưa kiểm tra tương thích.

### 5.2. Annotation cấp type

**`TracedType.java`**

```java
package com.example.typecut;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TracedType {
    String value() default "";
}
```

Annotation giữ thông tin `value` để có thể mở rộng sang binding, nhưng hai advice trong demo đầu tiên chỉ kiểm tra **đúng type annotation** mà chưa dùng giá trị.

### 5.3. Một service có annotation, một service không có

**`MarkedService.java`**

```java
package com.example.typecut;

@TracedType("checkout")
public class MarkedService {
    public String perform(String id) {
        return "marked:" + id;
    }
}
```

**`PlainService.java`**

```java
package com.example.typecut;

public class PlainService {
    public String perform(String id) {
        return "plain:" + id;
    }
}
```

Cả hai class đều không final, cả hai method đều public/non-final; không có self-call. Như vậy khác biệt quan trọng giữa hai loại service là **annotation cấp type**, không phải method visibility hoặc proxy eligibility.

### 5.4. Một aspect có hai advice độc lập

**`TypeSelectionAspect.java`**

```java
package com.example.typecut;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TypeSelectionAspect {
    private final AtomicInteger withinCalls = new AtomicInteger();
    private final AtomicInteger targetCalls = new AtomicInteger();

    @Before(
        "execution(public * com.example.typecut..*Service.perform(..))"
        + " && @within(com.example.typecut.TracedType)"
    )
    public void beforeWithin() {
        withinCalls.incrementAndGet();
    }

    @Before(
        "execution(public * com.example.typecut..*Service.perform(..))"
        + " && @target(com.example.typecut.TracedType)"
    )
    public void beforeTarget() {
        targetCalls.incrementAndGet();
    }

    public int withinCount() {
        return withinCalls.get();
    }

    public int targetCount() {
        return targetCalls.get();
    }
}
```

**Vì sao không in thứ tự advice?** Hai advices đều là `@Before` trên cùng join point; không khóa một thứ tự thực thi nếu không có cấu hình order rõ ràng. Dùng counter rồi in sau khi method hoàn thành cho output kiểm chứng **tất định**, không tự khẳng định `@within` luôn trước `@target` hoặc ngược lại.

`AtomicInteger` bảo đảm increment/get an toàn khi có concurrent calls. Tuy nhiên, counter trong singleton aspect chỉ là demo quan sát interception, không phải hệ thống metrics production hay counter toàn cluster.

### 5.5. Đăng ký beans, bật @AspectJ support

**`AppConfig.java`**

```java
package com.example.typecut;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TypeSelectionAspect typeSelectionAspect() {
        return new TypeSelectionAspect();
    }

    @Bean
    MarkedService markedService() {
        return new MarkedService();
    }

    @Bean
    PlainService plainService() {
        return new PlainService();
    }
}
```

`TypeSelectionAspect` là **Spring bean nhờ `@Bean`**, không cần `@Component`. Hai service cũng là Spring beans nhờ `@Bean`, không cần `@Service` hoặc `@ComponentScan`.

`@EnableAspectJAutoProxy` cho phép Spring lấy các advice từ `@Aspect` bean để xét target beans. `proxyTargetClass=true` khiến proxy có thể truy cập qua kiểu class trong ví dụ; điều này **không thay đổi ý nghĩa** annotation đặt trên **target class**.

### 5.6. Main kiểm tra hành vi, không dựa vào thứ tự advices

**`Main.java`**

```java
package com.example.typecut;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            MarkedService marked = context.getBean(MarkedService.class);
            PlainService plain = context.getBean(PlainService.class);
            TypeSelectionAspect aspect =
                    context.getBean(TypeSelectionAspect.class);

            System.out.println("markedProxy=" + AopUtils.isAopProxy(marked));
            System.out.println("marked=" + marked.perform("A"));
            System.out.println("plain=" + plain.perform("B"));
            System.out.println("withinCalls=" + aspect.withinCount());
            System.out.println("targetCalls=" + aspect.targetCount());
        }
    }
}
```

Chạy từ root project với Gradle đã cài:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper: `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Stdout ứng dụng mong đợi theo thứ tự** (không tính log môi trường/Gradle):

```text
markedProxy=true
marked=marked:A
plain=plain:B
withinCalls=1
targetCalls=1
```

### 5.7. Đọc kết quả cho đúng

1. `markedProxy=true`: `MarkedService` được Spring trả về dưới dạng Spring AOP proxy vì có advisors có thể áp dụng.
2. `marked=marked:A`: method `MarkedService.perform("A")` thực thi, còn hai advices tăng counter ở proxy.
3. `plain=plain:B`: method cùng tên của `PlainService` chạy nhưng **không có annotation `@TracedType` ở type**, nên không tăng hai counters trong demo.
4. `withinCalls=1`: method thuộc kiểu được đánh dấu, `@within` chọn execution.
5. `targetCalls=1`: target runtime class `MarkedService` có annotation, `@target` chọn execution.

**Không in/khẳng định `plainProxy=false` trong ví dụ.** Tùy việc Spring phân tích pointcut động, các advisor khác và phiên bản cấu hình, một bean không được annotation đánh dấu có thể vẫn được xem xét khi tạo proxy. Điều cần assert là **advice không ghi event cho `PlainService.perform`**, không phải ép toàn bộ ứng dụng phải có cùng một kết quả `AopUtils.isAopProxy(plain)`.

Và lưu ý: demo này **không phân biệt về mặt output** hai designator trên class/method đơn giản. Nó xác nhận cách bật, kiểu annotation và việc pointcut hoạt động trong Spring. Để phân biệt trong codebase thực tế, phải xây ma trận có kế thừa/annotation placement, không thay thế bằng suy đoán.

## 6. Kế thừa class, override method: vì sao cần phân biệt declared type và runtime target?

Xét ba loại tình huống. Chúng là **mô hình phân tích**, không phải những kết quả stdout tất định của demo chính.

### 6.1. Class khai báo method đồng thời có annotation

```java
@TracedType
public class TracedBillingService {
    public void bill() { }
}
```

- `bill()` được khai báo trong `TracedBillingService`.
- Target bean runtime class cũng là `TracedBillingService`.
- Khi gọi qua Spring proxy, cả `@within(TracedType)` và `@target(TracedType)` có điều kiện rõ ràng để match.

Đây là tình huống phù hợp nhất để bắt đầu học và test cả hai.

### 6.2. Method được khai báo trong superclass không có annotation

```java
public class BaseBillingService {
    public void bill() { }
}

@TracedType
public class SpecialBillingService extends BaseBillingService {
    // bill() được kế thừa, không khai báo lại ở đây
}
```

Phân tích về mặt ý nghĩa:

- **Kiểu khai báo method** là `BaseBillingService`, không có `@TracedType`.
- **Target object thực tế** có thể là `SpecialBillingService`, có `@TracedType`.
- Theo sự phân biệt của pointcut designator, đây là ca cần kiểm tra `@within` theo declaring type và `@target` theo runtime target type, thay vì coi chúng có chung nghĩa.

**Giới hạn của khẳng định:** Spring AOP ủy quyền một phần matching cho AspectJ pointcut parser và có logic tìm method tương ứng từ target class/interface/bridge methods. Với inheritance và các proxy types cụ thể, cách Spring resolve method có thể làm kết quả khó suy chỉ từ một đoạn source. Hãy **thử trên đúng Spring version và runtime proxy đang dùng**; không áp đặt bảng output duy nhất chưa được thực nghiệm.

Một biến thể khác: `SpecialBillingService` **override `bill()` và khai báo method ngay trong annotated class**. Khi đó declaring type đã thay đổi, vì vậy kết quả có thể khác inherited method. Khi test, ghi lại rõ method được **inherited** hay **overridden**.

### 6.3. Annotation trên superclass, target là subclass

```java
@TracedType
public class ParentBillingService {
    public void bill() { }
}

public class ChildBillingService extends ParentBillingService {
    // Không tự gắn @TracedType
}
```

Annotation Java `@Inherited` quyết định một phần khả năng class con **kế thừa annotation cấp class** khi tra cứu bằng reflection. Nếu `TracedType` **không** được meta-annotate bằng `@Inherited`, `ChildBillingService.class.isAnnotationPresent(TracedType.class)` không mặc nhiên thành true chỉ vì parent có annotation. Nếu muốn annotation có hành vi kế thừa ở Java class hierarchy, cân nhắc:

```java
import java.lang.annotation.Inherited;

@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TracedType {
    String value() default "";
}
```

Đây là đoạn **minh họa annotation variant**; muốn biên dịch thành file độc lập cần thêm các imports Java và package; không thay trực tiếp `TracedType.java` của demo nếu chưa kiểm tra test.

`@Inherited` **không làm annotation trên interface được triển khai trở thành annotation kế thừa trên implementation class**. Các utility annotation lookup của Spring có thể có cơ chế merge/meta-annotation khác reflection Java thông thường, nên không lẫn các lookup semantics ấy với điều kiện pointcut runtime cụ thể.

**Bài học:** khi policy bắt buộc áp cho cả class con, kiểm thử reflection/annotation lookup lẫn **actual advice invocation** trên subclass thực. Đừng đặt policy bảo mật vào một annotation và suy rằng annotation ấy tự lan sang mọi target class.

## 7. Annotation đặt trên interface: bẫy thường gặp trong Spring AOP

Trong thiết kế Spring, một service hay có interface:

```java
@TracedType
public interface PaymentPort {
    String pay(String id);
}

public class PaymentService implements PaymentPort {
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

Các đoạn minh họa, không thuộc demo `MarkedService` chạy được phía trên.

Cần phân biệt:

- **`PaymentPort` có annotation**; **`PaymentService` chưa chắc có annotation đó** trong kết quả Java reflection. `@Inherited` không truyền annotation từ interface sang implementing class.
- Với `@target(TracedType)`, tài liệu Spring mô tả annotation **trên class của target object**. Không suy rằng annotation chỉ đặt trên interface luôn đủ để pointcut này match implementation.
- Với `@within(TracedType)`, method declaring type, kiểu interface được proxy và cách Spring resolve implementation method có thể ảnh hưởng kết quả. Cần test trên **JDK proxy** và **CGLIB proxy**, đặc biệt khi method annotation / type annotation xuất hiện ở interface nhưng không xuất hiện trên implementation.
- Kết quả của một Spring feature có hỗ trợ **merged annotations** không phải bằng chứng `@within`/`@target` sẽ áp dụng cùng semantics; chúng là AspectJ expression pointcuts do Spring AOP diễn giải.

**Hướng thực tế dễ kiểm soát:** nếu policy phải dựa vào **annotation cấp class của runtime target**, đặt annotation trực tiếp trên class implementation mục tiêu (hoặc dùng inheritance được kiểm chứng và tài liệu hóa). Nếu policy thuộc **contract của interface**, cân nhắc pointcut theo `execution(* PaymentPort.*(..))` / `this(PaymentPort)` hoặc một marker method annotation phù hợp, rồi **test** với loại proxy thực tế. Không dùng lời giải dựa trên phép thừa kế annotation interface mà Java không bảo đảm.

## 8. Khi nào dùng @within, khi nào dùng @target?

Câu trả lời không phải “một cái luôn tốt hơn cái kia”. Chọn theo **nơi lưu ý nghĩa của annotation** và những ràng buộc cần bảo đảm:

**Dùng `@within` khi:**

- Bạn chủ ý chọn **code thuộc kiểu được đánh dấu** và muốn diễn tả phạm vi type khai báo method.
- Method được khai báo trực tiếp trong những service class có annotation là trường hợp chính.
- Bạn đã kiểm thử behavior với inherited/overridden/interface methods có liên quan, thay vì mở rộng nghĩa quá mức.
- Bạn muốn biểu thức rõ “method executions bên trong annotated type”, không chỉ dựa vào class runtime.

**Dùng `@target` khi:**

- Bạn muốn ràng buộc “object target mà Spring proxy chuyển tới có class mang annotation này”.
- Runtime implementation class là nơi **đặt marker type annotation**.
- Bạn cần binding/đọc metadata của annotation trên target trong advice và có test xác nhận.
- Bạn kết hợp với một `execution` cụ thể để Spring không phải xét quá nhiều loại bean và method.

**Dùng `@annotation` thay thế khi:**

- Chỉ một số method trên một class cần interception.
- Annotation policy là thuộc tính của **operation**, không phải cả target service.
- Cần phân biệt method này được audit, method khác trong cùng class không audit.

Nếu mục tiêu chỉ là **một Spring bean có tên** (ví dụ `paymentService`) thì pointcut extension `bean(paymentService)` có thể chính xác hơn type annotation. `bean` là extension **riêng của Spring AOP**; nó không phải pointcut designator chung của AspectJ weaving.

## 9. Kết hợp @within/@target với execution, bean và các biểu thức khác

### 9.1. Chặn public operation trong package nghiệp vụ

```java
@Pointcut("execution(public * com.example.billing..*Service.*(..))")
public void billingOperations() { }

@Pointcut("@target(com.example.typecut.TracedType)")
public void tracedTarget() { }

@Before("billingOperations() && tracedTarget()")
public void beforeBillingOperation() {
    // ...
}
```

Đây là **đoạn minh họa bên trong cùng một class `@Aspect`**, cần import `Pointcut`, `Before`. Chia pointcut thành tên nhỏ giúp đọc và tái sử dụng; Spring vẫn cần aspect bean và target Spring-managed.

### 9.2. Chặn theo kiểu khai báo và tên method

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && @within(com.example.typecut.TracedType)"
)
public void beforePerform() {
    // ...
}
```

Điều này chọn phạm vi kiểu và operation. Nếu class có nhiều method, chỉ `perform` thuộc biểu thức `execution` mới được xét.

### 9.3. Dùng OR khi thật sự chấp nhận một trong hai điều kiện

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && ("
    + "@within(com.example.typecut.TracedType)"
    + " || @target(com.example.typecut.TracedType)"
    + ")"
)
public void beforeAnyMarkedCase() {
    // ...
}
```

`||` không làm Spring “chạy advice hai lần nếu cả hai cùng match”; **một advice method** gắn trên biểu thức OR sẽ chạy **một lần cho mỗi join point invocation** mà expression match, trừ khi ứng dụng còn có các advisors/advice khác hoặc invocation lặp lại. Nhưng biểu thức OR làm phạm vi match rộng hơn; với policy quan trọng cần test trường hợp inheritance/interface để biết chính xác vì sao target được chọn.

**Lưu ý phân biệt:** nếu viết **hai advice methods** riêng `@within` và `@target` như demo, một method invocation có thể gọi **cả hai advice methods**, nên counter mỗi bên tăng một. Đây không phải biểu thức OR “tự chạy hai lần”.

### 9.4. Loại trừ package hoặc bean không mong muốn

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && @target(com.example.typecut.TracedType)"
    + " && !bean(internal*Service)"
)
public void beforePublicFacingTarget() {
    // ...
}
```

`bean(...)` là **Spring-specific** bean-name PCD. Pattern `internal*Service` chỉ là ví dụ; nếu bean name thực tế khác, rule exclusion không hoạt động. Không dùng biểu thức exclude theo tên để thay thế architecture/security boundary chắc chắn.

## 10. Binding annotation instance vào advice

Spring AOP `@AspectJ` hỗ trợ bind annotation của `@target`/`@within` theo tham số advice. Dùng khi cần đọc metadata như `value` của `@TracedType` thay vì chỉ hỏi annotation tồn tại hay không.

Ví dụ **minh họa riêng**, không thêm vào demo chính vì sẽ thay đổi bộ đếm và stdout:

```java
@Aspect
public class MetadataAspect {
    @Before(
        value = "execution(public * com.example.typecut..*Service.perform(..))"
              + " && @target(marker)",
        argNames = "marker"
    )
    public void beforeTarget(TracedType marker) {
        System.out.println("typeTag=" + marker.value());
    }
}
```

Nếu target class có `@TracedType("checkout")` và method join point phù hợp, Spring có thể bind annotation instance vào `marker` để in:

```text
typeTag=checkout
```

Điều kiện để code chạy thật: class aspect phải là Spring bean, `TracedType` phải có `RUNTIME` retention, các pointcut bindings phải tương thích, method target phải qua proxy. `argNames = "marker"` làm tham số binding tường minh, tránh dựa vào thông tin tên tham số Java có thể thiếu khi build không dùng `-parameters`.

Tương tự có thể viết `@within(marker)` khi muốn bind annotation của kiểu liên quan đến `@within`, nhưng hãy xem annotation đó có thực sự ở declaring type mà pointcut chọn không. Binding không biến annotation method thành annotation cấp class.

**Không nhầm `@target(marker)` với `target(targetObject)`:**

- `@target(marker)` bind **annotation object**.
- `target(targetObject)` bind **Spring target instance** tương ứng type parameter, nếu biểu thức và kiểu hợp lệ.

Nếu chỉ cần annotation tồn tại chứ không dùng metadata, viết `@target(com.example.typecut.TracedType)` sẽ dễ kiểm tra và không cần binding.

## 11. Một ma trận test nhỏ nhưng đủ bao phủ

Khi áp dụng pointcut annotation kiểu trong Spring, nên chuẩn bị integration tests theo **các đường match** thay vì suy đoán từ tên designator.

| Case | Nơi gắn type annotation | Method entry | Cần kiểm chứng |
| --- | --- | --- | --- |
| A | Trực tiếp trên class target | Public method khai báo tại chính class | Cả `@within` và `@target` có đúng số events dự kiến? |
| B | Không có annotation trên class | Public method cùng tên | Không có advice ngoài ý muốn? |
| C | Annotation ở subclass, method kế thừa từ base | Method không override | Type declaring và runtime target có tạo khác biệt? |
| D | Annotation ở subclass, method được override tại subclass | Override public method | Kết quả có khác case C không? |
| E | Annotation trên superclass có/không `@Inherited` | Method target thuộc subclass | Runtime annotation semantics có đúng ý định? |
| F | Annotation chỉ trên interface | Public method implementation | JDK/CGLIB và method resolution có khác nhau không? |
| G | Annotation trực tiếp trên implementation | Interface method gọi qua JDK proxy | `@target` có bắt được target class đúng không? |
| H | Annotation đúng, nhưng target được tạo bằng `new` | Gọi ngoài container | Không có Spring AOP advice? |
| I | Annotation đúng, self-invocation trên target | `this.perform()` | Advice trên `perform` có bị bypass? |
| J | Annotation đúng, CGLIB method `final` hoặc class `final` | Method không override được | Proxy có bị giới hạn/fail startup như dự kiến? |

Không cần biến mỗi case thành một README mới. Hãy tạo **test context tối giản** đúng proxy mode và chỉ assert **số advice invocations**/side effect. Với cấu hình có nhiều advisors, đếm theo từng advice thay vì kết luận proxy tồn tại nghĩa là tất cả advices match.

### Ví dụ kiểm thử trên context demo

```java
// Đoạn minh họa bên trong một Spring integration test hoặc main
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    MarkedService marked = context.getBean(MarkedService.class);
    PlainService plain = context.getBean(PlainService.class);
    TypeSelectionAspect aspect = context.getBean(TypeSelectionAspect.class);

    marked.perform("T1");
    marked.perform("T2");
    plain.perform("T3");

    if (aspect.withinCount() != 2 || aspect.targetCount() != 2) {
        throw new AssertionError("Unexpected type-annotation pointcut count");
    }
}
```

Đây là một biến thể **đứng riêng** chạy được trong package demo với import `AnnotationConfigApplicationContext`. Không chạy nó chung trong cùng `Main` nếu vẫn muốn stdout tại mục 5.7, vì nó là một context khác. Logic khẳng định hai method calls tới annotated class được tính, một call tới plain class không được tính.

Với `@Before`, counter đo **điểm advice trước khi target chạy**, không phải số business transaction đã commit. Nếu method target ném exception sau `@Before`, counter vẫn đã tăng; nếu muốn đo “thành công”, chọn thời điểm advice và điều kiện nghiệp vụ tương ứng.

## 12. Những bẫy phổ biến và cách xử lý

### 12.1. Gắn annotation lên method nhưng viết @within hoặc @target

```java
public class ExampleService {
    @TracedOperation
    public void execute() { }
}
```

Nếu `@TracedOperation` chỉ có `@Target(ElementType.METHOD)`, `@within(TracedOperation)`/`@target(TracedOperation)` không phải biểu thức tương ứng với annotation ấy. Nếu annotation là **method policy**, chọn `@annotation(com.example.TracedOperation)` và bảo đảm target method được proxy.

### 12.2. Class mang annotation nhưng không phải Spring bean

```java
@TracedType
class TracedService {
    public void perform() { }
}
```

Một class được đánh dấu `@TracedType` không tự đăng ký bean trong Spring. Đăng ký bằng `@Component`/`@Service` và component scan, hoặc `@Bean` trên `@Configuration`. Phía aspect cũng cần Spring-managed bean.

### 12.3. Coi @within và @target luôn giống nhau trong mọi phép kế thừa

Hai biểu thức có thể cùng match trên ví dụ cơ bản, nhưng ý nghĩa **declaring type** và **runtime target type** khác nhau. Khi có inherited/overridden/interface methods, hãy test Spring version/proxy của project. Không tự tạo một bảng output tuyệt đối rồi xem đó là contract.

### 12.4. Nhầm Java @Inherited với interface inheritance

`@Inherited` hoạt động theo **class inheritance**, không theo interface implements. Interface mang annotation không tự biến implementation thành runtime annotated target class; những cơ chế annotation search riêng của framework còn cần phân biệt rõ.

### 12.5. Điểm cắt quá rộng

`@target(TracedType)` trần có thể làm AOP infrastructure xét quá nhiều ứng viên. Ưu tiên `execution(...) && @target(...)` hoặc một pointcut kết hợp vùng package. Kiểm tra các bean internal/security/framework có vô tình bị áp advisor hay không.

### 12.6. Đổi proxy mode để “sửa” một vấn đề annotation mà chưa test

JDK interface proxy và CGLIB class proxy khác nhau về method exposure và điều kiện class/method. Nếu annotation nằm trên interface, việc đổi loại proxy có thể làm matching thay đổi, nhưng không phải cam kết Spring tự sao chép annotation lên implementation. Dùng test xác nhận.

### 12.7. Test đối tượng tạo bằng new

`new MarkedService().perform("A")` không đi qua Spring AOP proxy; annotation class vẫn tồn tại nhưng advice không chạy. Test AOP phải lấy bean từ `ApplicationContext`.

### 12.8. Self-invocation

`markedService.outer()` gọi `this.perform()` trên target thì `perform` không tự đi lại qua proxy; dù class có annotation, advice riêng trên `perform` vẫn có thể bị bypass. Đổi `@within` sang `@target` không sửa được self-invocation.

### 12.9. Annotation policy bị đặt trên class final hoặc method final

Với CGLIB proxy, Spring không subclass được class `final` và không override được method `final`. Annotation đúng vẫn không thể biến bytecode không override được thành Spring proxy interception. Nếu có business interface và không ép CGLIB, JDK proxy có thể là lựa chọn phù hợp; method phải expose qua interface proxy.

### 12.10. Suy từ isAopProxy rằng annotation pointcut đã chạy

`AopUtils.isAopProxy(bean)` chỉ chứng minh có một Spring AOP proxy. Một bean có thể có proxy vì advisor khác, một method có thể không match pointcut đang test, và một self-call có thể bypass. Luôn assert advice event/counter của chính `@within` hoặc `@target`.

## 13. Quy trình debug khi @within/@target không chạy như dự kiến

1. **Xác nhận annotation placement.** `TracedType` có `@Target(TYPE)` và `@Retention(RUNTIME)` không? Annotation nằm trên implementation class, superclass hay interface?
2. **Xác nhận Spring context.** Aspect có thực sự là bean? Target là bean? Có đúng ApplicationContext và AOP auto-configuration không?
3. **Nhìn đúng pointcut.** `@within` xét kiểu khai báo method, `@target` xét runtime class target; thêm `execution` để tránh match ngoài phạm vi.
4. **Kiểm tra proxy.** `AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy`, `isCglibProxy`; method entry có thuộc interface hay override được không?
5. **Gọi method qua proxy.** Lấy Spring bean từ context, inject vào một bean khác; không dùng `new` và không dựa vào `this.method()`.
6. **Đo riêng từng advice.** Tạo counters/test recorder cho `@within` và `@target`; không chỉ quan sát return value của method.
7. **Xét inheritance/bridge methods nếu cần.** Ghi rõ method có được override, annotation có `@Inherited`, class runtime nào đang làm target. Đừng dùng `proxy.getClass().isAnnotationPresent(...)` để thay cho việc kiểm tra annotation trên target class.
8. **Tạo integration test theo proxy mode thực tế.** Kiểm thử cùng Spring/Boot version và JDK, đặc biệt với interface annotations, generic bridge methods hoặc Kotlin final classes.
9. **Rà soát tác động.** Advice dùng cho audit/security/transaction cần test hành vi nghiệp vụ thực sự, không suy từ một dòng log rằng policy đã được bảo vệ toàn diện.

### Xem target class thay vì generated proxy class

```java
Object bean = context.getBean("markedService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Đây là **đoạn minh họa**, cần import `org.springframework.aop.support.AopUtils`, và context có bean tên `markedService`. Ở demo, `getTargetClass` xác định class nghiệp vụ `MarkedService`, tránh nhầm generated proxy subclass hoặc JDK proxy runtime class với nơi đặt type annotation.

Khi muốn biết annotation có thật trên target type theo Java reflection:

```java
Class<?> targetType = AopUtils.getTargetClass(bean);
boolean directlyOrInherited =
        targetType.isAnnotationPresent(TracedType.class);
```

Đoạn code là công cụ chẩn đoán annotation `RUNTIME` theo Java reflection (và `@Inherited` nếu có); nó **không thay thế** Spring/AspectJ pointcut matching engine hoặc phép đo advice thực tế.

## 14. Checklist thực hành

- [ ] Annotation đánh dấu **kiểu**, có `@Target(TYPE)` và `@Retention(RUNTIME)`?
- [ ] Phân biệt rõ **kiểu khai báo method** của `@within` và **class target runtime** của `@target`?
- [ ] Không nhầm `@within`/`@target` với `@annotation` trên method hoặc meta-annotation Java `@Target`?
- [ ] Aspect đã là Spring bean; target cũng là Spring bean; @AspectJ support được bật?
- [ ] Pointcut được giới hạn bằng `execution(...)` phù hợp, không vô tình áp lên quá nhiều bean?
- [ ] Gọi từ bean khác/context qua **Spring proxy**, không từ `new` hoặc `this.method()`?
- [ ] Đã xác nhận loại JDK/CGLIB proxy và khả năng intercept public/interface/non-final method?
- [ ] Nếu annotation nằm trên superclass/interface, đã test inheritance/override/Java `@Inherited` thật thay vì giả định?
- [ ] Nếu cần giá trị của annotation, đã dùng binding `@target(marker)` hoặc `@within(marker)` với tên tham số đúng?
- [ ] Integration tests kiểm tra riêng số lần `@within` và `@target` advice chạy cho class có/không marker?
- [ ] Không suy `isAopProxy=true` tương đương “mọi method đều được advice”?
- [ ] Policy liên quan bảo mật/giao dịch có test hiệu ứng thực tế, kể cả đường gọi bypass?

**Ghi nhớ:** Trong Spring AOP, `@within` nhấn mạnh **method execution nằm trong kiểu được annotate**; `@target` nhấn mạnh **annotation trên class target object**. Với class đơn giản cả hai thường cùng match, nhưng sự tương đồng đó không loại bỏ khác biệt về kiểu khai báo/runtime khi có kế thừa, proxy và annotation placement. Luôn giới hạn pointcut và kiểm chứng bằng Spring context cùng lời gọi thực sự qua proxy.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Declaring a Pointcut: @within, @target, @annotation, supported PCDs](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Declaring Advice: binding annotation vào tham số advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Maven Central — spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18)
- [Maven Central — aspectjweaver 1.9.24](https://central.sonatype.com/artifact/org.aspectj/aspectjweaver/1.9.24)
