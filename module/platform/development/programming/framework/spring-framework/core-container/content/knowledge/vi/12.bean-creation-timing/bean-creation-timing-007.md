# Phân biệt `@Order`, `@DependsOn` và thứ tự định nghĩa bean trong Spring Framework

## 1. Ba loại “thứ tự” khác nhau

Trong Spring IoC Container, rất nhiều câu hỏi được diễn đạt bằng cụm từ “bean nào chạy trước?”; tuy nhiên, ít nhất **ba vấn đề độc lập** thường bị gộp chung:

1. **Thứ tự sử dụng các beans trong một tập:** khi inject `List<Handler>`, handler nào đứng trước để pipeline gọi trước?
2. **Thứ tự khởi tạo và hủy beans:** khi một singleton có side effect tạo infrastructure, bean nào phải được tạo xong trước bean khác?
3. **Thứ tự đăng ký/khai báo bean definitions:** developer viết `@Bean` method hoặc XML `<bean>` nào trước trong source file, và BeanFactory ghi nhận định nghĩa theo thứ tự nào?

Ba vấn đề này có cơ chế và mức bảo đảm khác nhau:

| Câu hỏi | Cơ chế thích hợp | Điều không nên suy diễn |
| --- | --- | --- |
| Một `List<Stage>` được tiêm có thứ tự nào? | `@Order`, `Ordered`, `@Priority` trong ngữ cảnh được hỗ trợ | Không suy ra target beans được khởi tạo theo thứ tự list |
| Bean B phải **được khởi tạo sau** bean A? | Dependency injection thực sự hoặc `@DependsOn("A")` | `@Order(1)` trên A không bảo đảm A tạo trước B |
| B phải đóng trước A khi shutdown? | Quan hệ dependency/`@DependsOn` với singleton, lifecycle phù hợp | `@Order` dùng để sort list không định nghĩa destruction order |
| Không có `@Order` thì list có thứ tự gì? | Thường theo thứ tự đăng ký target bean definitions | Không phải bảo đảm lâu dài khi scan/import/refactor đổi |
| Viết `@Bean first()` trên `second()` thì sao? | Chỉ là thứ tự trong source code | Không phải hợp đồng init-before |
| Cần start/stop những services theo phase? | `SmartLifecycle.getPhase()` và dependency graph | Không dùng `@Order` để thay `SmartLifecycle` |

Trong bài này, `@Order` thuộc package `org.springframework.core.annotation`, còn `@DependsOn` thuộc `org.springframework.context.annotation`. Hai annotations không phải các cách viết khác nhau của một tính năng.

**Điểm then chốt từ Spring Framework 6.2:** `@Order` được dùng cho thứ tự ở nhiều điểm tiêu thụ (đặc biệt collection injection), **không điều khiển thứ tự startup singleton**. `@DependsOn` tạo quan hệ bảo đảm giữa các bean definitions: dependency được khởi tạo trước dependent và, với singleton, dependent bị hủy trước dependency.

Mục tiêu học tập:

- Phân biệt các pha **đăng ký bean definition**, **khởi tạo bean instance**, **sort injection collection**, **init/start** và **destroy/stop**.
- Dùng đúng `@Order` trên component classes/`@Bean` methods; hiểu số nhỏ có ưu tiên cao.
- Dùng `@DependsOn` ở đúng bean cần dependency, bằng **bean name**, không phải class name.
- Biết thứ tự fallback theo registration đối với collection không có order metadata và giới hạn của cơ chế.
- Phân biệt `@Order` trên `@Configuration` class với `@Order` trên **từng `@Bean` method**.
- Hiểu `@Primary`/`@Qualifier` và `@Priority` không hoàn toàn đồng nghĩa `@Order`.
- Viết và chạy demo Java 17+ với Spring Context 6.2, có assertions và stdout.
- Kiểm thử lỗi cấu hình, shutdown order, event pipeline và các tác động của lazy/prototype.

## 2. Mô hình thời gian của Spring Container

Một sơ đồ được đơn giản hóa:

```text
ApplicationContext được cấu hình
             |
             v
Đọc @Configuration / @Component / XML / imports
             |
             v
Đăng ký BeanDefinition và metadata liên quan
  name, scope, lazy, dependsOn, qualifiers, order...
             |
             v
Xử lý BeanFactoryPostProcessor / bean metadata
             |
             v
Pre-instantiate eligible non-lazy singleton beans
   với dependency graph được tôn trọng
             |
             v
Cấp dependency cho consumers
  + sort List<T>/T[] tại injection point thích hợp
             |
             v
Gọi business methods, SmartLifecycle.start(), ...
             |
             v
Đóng context
   lifecycle stop, singleton destruction ...
```

Sơ đồ không phải toàn bộ vòng đời Spring: bean post-processors, AOP proxies, factory methods, custom scopes và Spring 6.2 background initialization có thể làm chi tiết phức tạp hơn. Nhưng một phân biệt rất quan trọng là:

- **Registration**: container biết *có* bean definition; instance có thể chưa được tạo.
- **Instantiation/initialization**: container tạo object và hoàn tất initialization.
- **Collection resolution**: container chọn và sắp các candidate objects cho injection point.
- **Invocation**: application gọi methods theo thứ tự mà application quyết định.
- **Destruction**: container giải phóng managed singletons khi context đóng theo dependency/lifecycle rules.

Bạn có thể có một `List<Stage>` được sắp `A, B, C` nhưng thứ tự constructor hoặc static init events hoàn toàn không phải `A, B, C`. Không được đồng nhất “sorted list” với “startup order”.

## 3. `@Order`: dùng khi một tập phần tử cần thứ tự

Annotation:

```java
import org.springframework.core.annotation.Order;

@Order(-100)
class SecurityFilter implements FilterStep {
    // ...
}
```

Đây là **trích đoạn minh họa**; cần interface `FilterStep` và method bodies phù hợp để biên dịch. Ý nghĩa `@Order(-100)` là khai báo một **giá trị thứ tự** dùng khi Spring hoặc infrastructure liên quan sắp xếp các elements.

### 3.1. Số nhỏ đứng trước

Thứ tự số học:

```text
@Order(-10)  → trước
@Order(0)    → giữa
@Order(20)   → sau
@Order(100)  → sau nữa
```

Theo contract `Ordered`, **giá trị nhỏ hơn có độ ưu tiên cao hơn** trong sorting. Spring định nghĩa hai hằng:

```java
Ordered.HIGHEST_PRECEDENCE   // Integer.MIN_VALUE
Ordered.LOWEST_PRECEDENCE    // Integer.MAX_VALUE
```

Đây là ví dụ tham chiếu constants, cần import `org.springframework.core.Ordered` khi viết Java độc lập.

`@Order` có default value `Ordered.LOWEST_PRECEDENCE`. Nếu nhiều phần tử không có chỉ dẫn order hoặc có cùng order value, đừng thiết kế nghiệp vụ dựa vào một tie-breaking thứ tự không được contract bảo đảm; có thể cần thêm quy tắc rõ ở application layer.

### 3.2. Ví dụ inject `List<Step>`

Giả sử có:

```java
public interface Step {
    String code();
}
```

Và ba implementations/component beans:

```java
@Component
@Order(30)
class StepValidate implements Step {
    public String code() { return "validate"; }
}

@Component
@Order(-10)
class StepAuthenticate implements Step {
    public String code() { return "authenticate"; }
}

@Component
@Order(10)
class StepEnrich implements Step {
    public String code() { return "enrich"; }
}
```

Hai đoạn là snippets minh họa; cần imports và component scanning để beans tồn tại. Với consumer:

```java
@Component
class Pipeline {
    private final List<Step> steps;

    Pipeline(List<Step> steps) {
        this.steps = steps;
    }
}
```

Spring có thể inject `steps` theo thứ tự `authenticate, enrich, validate` vì giá trị `-10 < 10 < 30`.

**Đây là thứ tự phần tử trong collection tại injection point.** Container không bị yêu cầu khởi tạo `StepAuthenticate` trước `StepEnrich` trước `StepValidate` chỉ vì chúng có `@Order`.

### 3.3. Dùng `@Order` trên `@Bean` method

Một số types không mang `@Component` hoặc bạn muốn có nhiều bean definitions trả về cùng implementation nhưng mỗi bean có priority khác:

```java
@Bean("secondStep")
@Order(20)
Step secondStep() {
    return new NamedStep("second");
}

@Bean("firstStep")
@Order(0)
Step firstStep() {
    return new NamedStep("first");
}
```

Snippet này cần `Step`, `NamedStep` và `@Bean` import. Khi inject `List<Step>`, Spring 6.2 đọc `@Order` trên **target `@Bean` methods** và có thể sắp `first` trước `second`.

Điều này quan trọng nếu hai bean definitions dùng cùng class: `@Order` trên class không đủ để diễn đạt mức ưu tiên khác nhau cho từng bean definition, trong khi method annotations có thể làm được.

### 3.4. `Ordered` interface khi order tính theo instance

Thay vì hard-code annotation metadata, một object có thể:

```java
public final class ConfigurableStep
        implements Step, Ordered {

    private final String code;
    private final int order;

    public ConfigurableStep(String code, int order) {
        this.code = code;
        this.order = order;
    }

    @Override
    public String code() {
        return code;
    }

    @Override
    public int getOrder() {
        return order;
    }
}
```

Cần imports của `Ordered` và `Step`. Khi infrastructure dùng `AnnotationAwareOrderComparator`/order-aware sorting, giá trị từ `Ordered.getOrder()` có thể được dùng để sắp elements. Nó hữu ích khi cấu hình thứ tự ở bean instance level thay vì một annotation cố định trên class.

**Giới hạn:** implement `Ordered` không khiến Spring tự gọi business method `execute()` theo thứ tự. Một consumer/pipeline phải thực sự lặp qua tập đã được order, hoặc hạ tầng cụ thể phải áp dụng comparator ấy.

### 3.5. `@Order` trên `@Configuration` không lan xuống `@Bean` methods

Đây là một khác biệt được tài liệu Spring 6.2 nói rõ:

```java
@Configuration
@Order(-100)
class AlphaConfiguration {

    @Bean
    Step alphaStep() {
        return new NamedStep("alpha");
    }
}

@Configuration
@Order(100)
class BetaConfiguration {

    @Bean
    Step betaStep() {
        return new NamedStep("beta");
    }
}
```

Mã minh họa trên thiếu imports/types. `@Order` trên **configuration classes** có thể ảnh hưởng **evaluation order trong tập các configuration classes**, không tự gán `-100` và `100` cho các `Step` beans được factory methods tạo.

Muốn list `List<Step>` được sort theo các giá trị cụ thể, đặt `@Order` trên **mỗi `@Bean` method** (hoặc trên target classes/`Ordered` phù hợp).

**Không suy ra**: config Alpha được đánh giá trước → bean `alphaStep` nhất định được tạo trước → list được order như vậy. Đây là ba tầng khác nhau.

## 4. Collection injection khi không có `@Order`

Spring Reference nói rằng với typed array/list injection, nếu candidates không có `Ordered`, `@Order` hoặc `@Priority` để điều khiển, thứ tự thường theo **registration order của target bean definitions** trong container.

Ví dụ:

```java
@Bean("eastStep")
Step eastStep() { return new NamedStep("east"); }

@Bean("westStep")
Step westStep() { return new NamedStep("west"); }
```

Không có order metadata, Spring dùng registration order làm fallback cho List. Nhưng **đừng xem thứ tự dòng code là hợp đồng luôn bất biến**. Registration order có thể thay đổi khi:
- thêm `@Import` hoặc thay composition root;
- đổi component scan packages/filtering;
- thêm `BeanDefinitionRegistryPostProcessor`/registrar;
- dịch từ XML sang JavaConfig hoặc đổi build packaging;
- thay dependency/framework version;
- thay cách programmatic registration được gọi.

**Nhận diện hai loại order khác nhau**:

| Tên | Nghĩa | Dùng khi nào? |
| --- | --- | --- |
| Source declaration order | Method/class/`<bean>` xuất hiện vị trí nào trong source | Con người đọc và maintain |
| Bean definition registration order | Container ghi nhận target bean definitions theo thứ tự nào | Fallback cho unordered List/array candidates |
| Bean instance creation order | Constructor/factory/init chạy thực tế vào thời điểm nào | Dependency graph, eager/lazy, background/bootstrap |
| Consumer invocation order | Pipeline gọi các Step theo sequence nào | Consumer logic và sorted collection |

Không có phép suy ra chung “source declaration = registration = instantiation = invocation”.

### 4.1. XML `<bean>` từ trên xuống dưới có đảm bảo init thứ tự không?

Không nên phụ thuộc vào **vị trí thẻ** để đòi một side effect phải xảy ra trước. Trong một số cấu hình thông thường, non-lazy singleton pre-instantiation có thể quan sát thấy gần với registration order; tuy nhiên, dependency graph, lazy beans, FactoryBeans, imports, BeanPostProcessors và những cơ chế khác có thể làm thứ tự khác đi.

Nếu Bean B bắt buộc chờ Bean A hoàn tất initialization, khai báo quan hệ đúng bằng `<ref>`/constructor dependency hoặc `depends-on`, thay vì di chuyển các thẻ XML.

### 4.2. Java reflection/method declaration order không phải scheduling API

Trong JavaConfig, Spring phân tích annotations và factory methods để đăng ký bean definitions. Đừng thiết kế logic chỉ dựa trên dòng nào viết trước trong `@Configuration` class. Java source method order không phải API contract để ràng buộc thứ tự khởi tạo managed beans.

### 4.3. XML import/Java import có thể thay candidate set

Khi một configuration import thêm beans, tổng số candidates và registration order có thể thay đổi. Nếu list là một **pipeline quan trọng** (security, validation, routing), dùng `@Order` hoặc order contract rõ ràng. Nếu stage order không ảnh hưởng nghiệp vụ, đừng đặt order values chỉ vì cảm giác cần một thứ tự.

## 5. `@DependsOn`: khởi tạo prerequisite trước, hủy dependent trước

`@DependsOn("bootstrap")` đặt trên bean `worker` diễn đạt một quan hệ **lifecycle**, độc lập với thứ tự handler trong collection:

```java
@Bean("worker")
@DependsOn("bootstrap")
Worker worker() {
    return new Worker();
}
```

Tên `bootstrap` phải là bean name hoặc alias hợp lệ. Khi worker được khởi tạo, Spring phải tạo và initialize prerequisite trước; với hai managed singleton có destroy callback, worker được hủy trước bootstrap.

```text
INIT:    bootstrap -> worker
DESTROY: worker    -> bootstrap
```

XML sử dụng `<bean id="worker" depends-on="bootstrap" ... />`. `@DependsOn` **không inject object**: nếu `Worker` cần dùng chính `Bootstrap` instance, constructor hoặc factory-method parameter là cách khai báo phù hợp. Class-level `@DependsOn` được xử lý theo đường component scanning; nếu class được đăng ký trực tiếp bằng XML, dùng XML `depends-on`.

`@DependsOn({"bootstrap","metrics"})` bắt cả hai prerequisites có trước worker, nhưng không nên xem thứ tự liệt kê trong array là một quy trình nghiệp vụ bắt bootstrap phải chạy trước metrics. Cũng đừng dùng nó để trì hoãn bean: eager dependent có thể kéo lazy prerequisite vào startup.

Bài trước về `@DependsOn` dạy chi tiết declaration và diagnostics. Ở bài so sánh này, điểm cần kiểm chứng là **`@DependsOn` tạo init/destroy relation, trong khi `@Order` chỉ sort tập bean**. Hai yêu cầu có thể cùng tồn tại trên một component và cần kiểm thử tách biệt.

## 6. Vì sao `@Order` không thay thế `@DependsOn`?

Giả sử có một pipeline với hai `Handler`:

```java
@Component
@Order(-100)
class BootstrapHandler implements Handler {
    // ...
}

@Component
@Order(100)
class AuditHandler implements Handler {
    // ...
}
```

Collection `List<Handler>` có thể xếp BootstrapHandler trước AuditHandler. Nhưng Spring **không bị yêu cầu** gọi constructor/init của BootstrapHandler trước AuditHandler chỉ vì `@Order(-100)`.

Trong một ứng dụng dùng singleton beans:
- khi context pre-instantiates beans, thứ tự còn chịu ảnh hưởng graph và bootstrap operations;
- `@Order` có thể chỉ được đọc lúc BeanFactory resolve candidates cho một List;
- nếu AuditHandler có `@PostConstruct` side effect cần hạ tầng BootstrapHandler đã sẵn sàng, `@Order` không giải quyết requirement đó.

Nếu cần init-before, dùng:

```java
@Component
@DependsOn("bootstrapHandler")
class AuditHandler implements Handler {
    // ...
}
```

Giải pháp này giả định bean name `bootstrapHandler` được đăng ký đúng theo naming convention hoặc chỉ định explicit. Vẫn có thể giữ `@Order` **đồng thời** để điều khiển vị trí trong List khi nghiệp vụ cần.

### 6.1. Cùng lúc cần cả hai cơ chế

Một hệ thống có thể:
- phải khởi tạo authentication infrastructure trước handler audit;
- phải thực thi authentication handler trước audit handler trong request pipeline.

Khi đó cần **hai hợp đồng riêng**:
- `@DependsOn` hoặc DI edge cho initialization graph;
- `@Order` cho collection processing order.

Chỉ một annotation không thể thay thế annotation kia.

### 6.2. Thứ tự List không đồng nghĩa một handler được gọi trước

Nếu consumer không sử dụng `List<Handler>` mà lookup bean bằng name rồi gọi trực tiếp, `@Order` không ép caller gọi handlers theo order.

Ngược lại, một consumer đã nhận ordered list nhưng cố ý gọi `list.get(2)` trước cũng không bị Spring ngăn. Framework sắp **collection**, còn application quyết định **invocation**.

## 7. `@Order`, `@Priority`, `Ordered`, `@Primary` và `@Qualifier`

Những tên này dễ gây nhầm, nhưng giải quyết các vấn đề khác nhau:

| Cơ chế | Mục đích chính | Ví dụ |
| --- | --- | --- |
| `@Order(5)` | Khai báo sort order khi xử lý tập phần tử | Pipeline List |
| `Ordered#getOrder()` | Trả order value từ bean instance | Plugin order từ config |
| `@Priority(5)` (Jakarta) | Priority trong ordering; có semantics bổ sung ở một số single-bean selection contexts | Framework-level prioritization |
| `@Primary` | Chọn default khi có nhiều bean cùng type cho **single injection point** | Một `DataSource` mặc định |
| `@Qualifier("east")` | Thu hẹp candidate set cho dependency | Chọn bean cụ thể |
| `@DependsOn("bootstrap")` | Init-before/destruction-after relation | Resource initialization |
| Registration order | Fallback sorting cho List/array không có order metadata | Hậu quả cách đăng ký definitions |

### 7.1. `@Order` không mặc định chọn một bean duy nhất

Hai beans đều implement `PaymentGateway`:

```java
@Bean
@Order(-100)
PaymentGateway fastGateway() { return new FastGateway(); }

@Bean
@Order(100)
PaymentGateway safeGateway() { return new SafeGateway(); }
```

Nếu consumer yêu cầu **một** `PaymentGateway` không qualifier:

```java
@Bean
CheckoutService checkoutService(PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
```

Đừng suy ra Spring sẽ tự chọn `fastGateway` chỉ vì `@Order(-100)`. `@Order` chủ yếu xử lý **order trong tập candidates**. Với một dependency đơn, có thể cần `@Primary`, `@Qualifier` hoặc naming policy thích hợp. `@Priority` có thể có semantics bổ sung trong trường hợp chọn một phần tử, vì vậy cũng không nên đánh đồng nó với `@Order`.

### 7.2. `@Primary` không sort List

Nếu một trong ba handlers có `@Primary`, điều đó không tự đưa handler này lên đầu `List<Handler>`. Injection point là collection thì Spring thường thu thập nhiều candidates và áp dụng order metadata riêng.

### 7.3. Qualifier lọc candidates trước/đồng thời với ordering

Một List injection point có `@Qualifier("critical")` có thể chỉ nhận nhóm handlers gắn qualifier phù hợp, rồi sắp order trong **tập đã lọc**.

Cần kiểm tra annotations và bean definitions cụ thể: `@Qualifier` không phải thứ tự, `@Order` không phải bộ lọc.

### 7.4. `Set` và `Map`: đọc contract trước khi hứa thứ tự

Spring reference mô tả order sorting rõ cho **array** và **typed List** injection. `Map<String, Handler>` cung cấp bean names làm keys và beans làm values. Không nên viết business pipeline dựa trên giả định mọi traversal của Set/Map sẽ tuân `@Order` như List.

Nếu thứ tự chính là nghiệp vụ, inject `List<Handler>`, hoặc rõ ràng tạo một ordered sequence từ map values bằng comparator trong code, và viết tests cho contract ấy.

## 8. Ví dụ XML đối chiếu

XML beans:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="worker"
          class="example.Worker"
          depends-on="bootstrap"/>

    <bean id="bootstrap"
          class="example.Bootstrap"/>
</beans>
```

Đoạn này là **cấu hình minh họa**: `example.Worker`/`example.Bootstrap` cần tồn tại. Worker được viết trước Bootstrap trong XML nhưng dependency metadata buộc Bootstrap được khởi tạo trước Worker. Chuyển gần tương đương:

```java
@Configuration(proxyBeanMethods = false)
class ExampleConfiguration {

    @Bean("worker")
    @DependsOn("bootstrap")
    Worker worker() {
        return new Worker();
    }

    @Bean("bootstrap")
    Bootstrap bootstrap() {
        return new Bootstrap();
    }
}
```

Đây là snippet Java minh họa, cần imports/types. `@DependsOn` áp dụng trên factory method `worker()`; cấu hình không cần gọi `bootstrap()` trực tiếp từ `worker()` để tạo ordering dependency.

### 8.1. XML declaration order không tạo dependency edge

Nếu bỏ `depends-on="bootstrap"` và Worker không inject Bootstrap, chỉ còn hai bean definitions độc lập. Việc Worker nằm trước hoặc sau Bootstrap trong file có thể làm thay đổi **quan sát** trong một phiên bản/cách loading cụ thể, nhưng đó không phải một dependency contract tốt để đảm bảo side effect.

### 8.2. Bean có alias thì `depends-on` có thể dùng name đã đăng ký

Nếu `bootstrap` có alias `initSubsystem`, một `depends-on="initSubsystem"` có thể resolve tên alias hợp lệ. Tuy nhiên, dependency naming nên ổn định và được tests bảo vệ; đổi bean names/aliases trong migration có thể phá `@DependsOn`.

### 8.3. Đừng ép bằng `<import>` file order

Chia cấu hình thành `00-bootstrap.xml` và `10-worker.xml` không phải thay thế logic dependency graph. Khi import nhiều XML, file load order có thể tạo ảo giác “bootstrap lúc nào cũng trước”. Dùng `depends-on` hoặc constructor/reference injection cho yêu cầu thật.

## 9. Demo chạy được: Java 17+ và Spring Framework 6.2

Demo này tách hai khái niệm ngay trong một application context:

- **Collection order:** `@Order` đặt trên ba `@Bean` methods: bước `first` đứng trước `middle` và `last` dù method `lastStep` được viết trước.
- **Initialization/destruction order:** bean `worker` có `@DependsOn("bootstrap")`. Hai beans không inject reference của nhau; mục tiêu là chứng minh metadata thứ tự độc lập.
- **Bean definition order inspection:** có thể đọc names đã đăng ký để kiểm tra rằng registration không tự là creation contract.
- **Assertions:** không chỉ in log rồi phỏng đoán, chương trình xác minh sorted List, created-before và destroyed-after.

Không cần Spring Boot, database, HTTP hoặc external service. Demo dùng một Java file có nested types và bản Gradle đơn giản.

### 9.1. Cấu trúc dự án

```text
bean-ordering-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── BeanOrderingDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-ordering-demo'
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
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'BeanOrderingDemo'
}
```

JDK 17+ và một bản Gradle hỗ trợ JDK tương ứng là đủ cho source sử dụng records, `List.of` và `AnnotationConfigApplicationContext`.

### 9.2. Mã Java đầy đủ

Lưu `src/main/java/BeanOrderingDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.core.annotation.Order;

public class BeanOrderingDemo {

    public interface Stage {
        String label();
    }

    public record NamedStage(String label) implements Stage {
    }

    public record Pipeline(List<Stage> stages) {
        public List<String> labels() {
            return stages.stream()
                    .map(Stage::label)
                    .toList();
        }
    }

    public static final class Events {
        private final List<String> values = new ArrayList<>();

        public void add(String event) {
            values.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(values);
        }
    }

    public static final class Bootstrap implements AutoCloseable {
        private final Events events;

        public Bootstrap(Events events) {
            this.events = events;
            events.add("init:bootstrap");
        }

        @Override
        public void close() {
            events.add("destroy:bootstrap");
        }
    }

    public static final class Worker implements AutoCloseable {
        private final Events events;

        public Worker(Events events) {
            this.events = events;
            events.add("init:worker");
        }

        @Override
        public void close() {
            events.add("destroy:worker");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {

        // Method declared first, but not permitted to initialize
        // before the bean named "bootstrap".
        @Bean(name = "worker", destroyMethod = "close")
        @DependsOn("bootstrap")
        Worker worker(Events events) {
            return new Worker(events);
        }

        @Bean(name = "bootstrap", destroyMethod = "close")
        Bootstrap bootstrap(Events events) {
            return new Bootstrap(events);
        }

        @Bean
        Events events() {
            return new Events();
        }

        // The source order of these factory methods is purposely
        // different from the desired order in List<Stage>.
        @Bean("lastStage")
        @Order(30)
        Stage lastStage() {
            return new NamedStage("last");
        }

        @Bean("firstStage")
        @Order(-10)
        Stage firstStage() {
            return new NamedStage("first");
        }

        @Bean("middleStage")
        @Order(10)
        Stage middleStage() {
            return new NamedStage("middle");
        }

        @Bean
        Pipeline pipeline(List<Stage> stages) {
            return new Pipeline(stages);
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Events events;

        try (var context = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {

            events = context.getBean(Events.class);
            Pipeline pipeline = context.getBean(Pipeline.class);

            List<String> order = pipeline.labels();
            List<String> init = events.snapshot();

            String[] dependsOn = context.getBeanFactory()
                    .getBeanDefinition("worker")
                    .getDependsOn();

            require(
                    order.equals(List.of("first", "middle", "last")),
                    "Collection @Order contract failed");

            require(
                    init.equals(List.of(
                            "init:bootstrap", "init:worker")),
                    "@DependsOn initialization contract failed");

            require(
                    Arrays.equals(
                            dependsOn, new String[] {"bootstrap"}),
                    "Missing depends-on bean definition metadata");

            System.out.println("pipeline=" + order);
            System.out.println("initialization=" + init);
            System.out.println("worker.dependsOn=" +
                    Arrays.toString(dependsOn));
        }

        List<String> afterClose = events.snapshot();
        require(
                afterClose.equals(List.of(
                        "init:bootstrap", "init:worker",
                        "destroy:worker", "destroy:bootstrap")),
                "@DependsOn destruction contract failed");

        System.out.println("shutdown=" + afterClose);
    }
}
```

### 9.3. Lệnh chạy

Từ thư mục dự án:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Stdout **do chương trình chủ động in**:

```text
pipeline=[first, middle, last]
initialization=[init:bootstrap, init:worker]
worker.dependsOn=[bootstrap]
shutdown=[init:bootstrap, init:worker, destroy:worker, destroy:bootstrap]
```

Gradle hay Spring logging backend có thể xuất thêm dòng bên ngoài `System.out.println`. Các assertions sẽ khiến chương trình fail nếu behavior quan sát được sai với contract đã khai báo.

### 9.4. Phân tích từng dòng

**`pipeline=[first, middle, last]`:** Ba target bean definitions có order metadata `-10`, `10` và `30`. Khi BeanFactory resolve tham số `List<Stage> stages` cho `pipeline`, nó sắp thứ tự candidates. Pipeline chỉ lưu List ấy và in labels theo thứ tự.

**`initialization=[init:bootstrap, init:worker]`:** Bean `worker` mang `@DependsOn("bootstrap")`. Dù `worker()` được khai báo trước `bootstrap()` trong Java source, BeanFactory phải bảo đảm bootstrap đã được khởi tạo trước worker khi worker được tạo. Các stage beans không thêm events vào log, nên snapshot chỉ chứa hai init events và giá trị dự đoán ổn định.

**`worker.dependsOn=[bootstrap]`:** Metadata được lưu trong `BeanDefinition`. Đây là cách xác minh chính xác rằng annotation trên factory method đã tạo ra dependency relation mà bạn muốn.

**`shutdown=[init:bootstrap, init:worker, destroy:worker, destroy:bootstrap]`:** Khi context đóng, singleton dependent `worker` được hủy trước `bootstrap`. Hai classes implement `AutoCloseable`; `@Bean(destroyMethod="close")` được khai báo tường minh để tránh lệ thuộc vào inferred destruction callbacks.

### 9.5. Vì sao việc khai báo method theo thứ tự ngược lại quan trọng?

`worker()` được viết trước `bootstrap()` một cách có chủ đích. Điều này giúp người đọc không lầm source order với business rule. Program không **dựa vào** source order; nó dựa vào `@DependsOn`. Nếu về sau chuyển configuration sang nhiều files hoặc đổi method order, dependency relation vẫn thể hiện cùng yêu cầu.

### 9.6. Vì sao không lấy thứ tự constructor của Stage để làm bằng chứng `@Order`?

`@Order` chỉ khẳng định thứ tự khi **List được resolve**; nó không yêu cầu Stage constructors/factory methods được gọi theo thứ tự đó. Để tránh đưa ra một kết luận sai, demo kiểm tra **pipeline.labels()** mà không dùng creation events cho Stage. Ngược lại, demo dùng creation/destruction events cho `@DependsOn` vì đó mới là contract của annotation ấy.

### 9.7. Tại sao `Events` không có `@Order`?

`Events` chỉ là collector. Nó không được inject vào `List<Stage>` và không phải một stage. Order metadata trên nó không giúp thay đổi khởi tạo bootstrap/worker. Nó được tạo bởi BeanFactory để ghi events, không tự đưa ra một policy ordering.

### 9.8. Có thể thay bằng constructor injection không?

Nếu Worker thực sự cần Bootstrap object, hãy dùng:

```java
@Bean("worker")
Worker worker(Bootstrap bootstrap, Events events) {
    return new Worker(events);
}
```

Khi đó Bootstrap được resolve trước lời gọi `worker(...)` vì factory method parameter. `@DependsOn` trở nên ít cần thiết nếu chỉ yêu cầu object dependency này; tuy nhiên demo cố ý không inject Bootstrap để minh họa trường hợp ordering dependency không trực tiếp bằng object reference.

Đây là **snippet thay thế minh họa**, không phải toàn bộ bản demo và không bảo toàn destruction order metadata độc lập trong mọi setup nếu bạn loại bỏ quan hệ explicit; cần test lifecycle khi thay cách diễn đạt.

## 10. Kịch bản test âm tính: những cách dùng sai

### 10.1. Dùng `@Order` để ép init-before

Sai về mục tiêu:

```java
@Bean
@Order(-100)
Bootstrap bootstrap() { return new Bootstrap(); }

@Bean
@Order(100)
Worker worker() { return new Worker(); }
```

Các snippets giả định constructors no-arg. **Không có dependency edge** giữa hai definitions. Nếu Worker yêu cầu Bootstrap init trước, dùng `@DependsOn` hoặc DI thật thay vì dựa vào order values.

### 10.2. Dùng `@DependsOn` để sort pipeline

```java
@Bean
@DependsOn("authenticationStage")
Stage auditStage() { return new AuditStage(); }
```

Khai báo này có thể làm `authenticationStage` khởi tạo trước `auditStage`, nhưng không tự sắp `List<Stage>` theo “authentication rồi audit” khi collection được inject. Cần `@Order`/`Ordered` hoặc consumer sorting contract.

### 10.3. Dùng `@Order` trên configuration class cho bean methods

```java
@Configuration
@Order(-100)
class MyConfig {
    @Bean Stage x() { return new StageX(); }
    @Bean Stage y() { return new StageY(); }
}
```

`@Order(-100)` trên `MyConfig` là metadata configuration-level; không trở thành order -100 cho cả `x` và `y`. Nếu muốn x đứng trước y trong injected List, annotate từng `@Bean` method hoặc target classes.

### 10.4. Trông chờ thứ tự XML/Java source

`worker` viết dưới `bootstrap` hôm nay không ngụ ý Worker luôn init sau Bootstrap ở mọi composition và startup mode. Một refactor import/scan có thể đổi cách definitions được đăng ký. Dùng explicit dependencies.

### 10.5. Một dependency tên sai

```java
@Bean
@DependsOn("bootstarp")
Worker worker() {
    return new Worker();
}
```

Tên `bootstarp` bị typo. BeanFactory có thể ném `NoSuchBeanDefinitionException`/`BeanCreationException` khi tạo `worker` bởi named dependency không tồn tại. `@DependsOn` không tự tìm bean có tên gần giống. Viết integration test kiểm tra context refresh và metadata khi rename.

### 10.6. Vòng dependency

Nếu A `@DependsOn("B")` và B `@DependsOn("A")`, BeanFactory sẽ gặp vòng dependency và bean creation có thể thất bại. Đừng sử dụng `@Order` để “giải” vòng: một annotation sort list không sửa dependency graph.

### 10.7. `@Lazy` và `@DependsOn`

Một lazy bean Worker có `@DependsOn("bootstrap")`. Nó chưa bị tạo tại refresh nếu không có consumer kéo vào. Khi Worker thực sự được yêu cầu, container cần khởi tạo Bootstrap trước Worker. `@DependsOn` không tự có nghĩa “mọi named dependency phải được tạo ngay ở refresh” nếu bản thân dependent chưa được instantiate.

### 10.8. Prototype và shutdown

`@DependsOn` có thể điều khiển việc khởi tạo prototype khi BeanFactory tạo prototype, nhưng **Spring không tự gọi destroy callbacks của mọi prototype instances khi context close** như với singletons. Vì vậy không suy ra destruction-order guarantee giống singleton nếu bên phụ thuộc là prototype.

## 11. Phạm vi `@Order` trong các framework components khác

Thứ tự có mặt nhiều nơi trong Spring, nhưng phải xác định **đơn vị nào thực sự được sắp**:

- `List<Handler>` hoặc `Handler[]` được autowire: BeanFactory sắp candidates theo `Ordered`/`@Order`.
- `ObjectProvider<T>.orderedStream()`: API stream có ordering semantics dựa trên comparator phù hợp.
- BeanPostProcessors/BeanFactoryPostProcessors có ordering/registration rules đặc thù; không giả định mọi nơi chỉ cần gắn `@Order` trên class.
- MVC interceptors, security filters, AOP advisors: có thể có ordering APIs riêng; một annotation đặt sai type không thay quy tắc hạ tầng đó.
- `@Configuration` classes: `@Order` tác động evaluation order trong tập configuration classes; không điều khiển bean product startup theo cùng số.

### 11.1. `ObjectProvider.orderedStream()`

Trong Spring, `ObjectProvider<T>` có thể dùng để lấy các candidates của kiểu T theo ordered stream, ví dụ:

```java
List<Step> ordered = provider.orderedStream().toList();
```

Cần một `ObjectProvider<Step> provider` hợp lệ. `orderedStream()` hữu ích khi muốn **hoãn việc lấy một tập plugins đến thời điểm sử dụng**, đồng thời yêu cầu order metadata được áp dụng. Không đồng nhất thứ tự stream với init startup.

### 11.2. `SmartLifecycle` khi cần thứ tự start/stop

Nếu vấn đề của bạn là **dịch vụ nền start/stop theo phases** (scheduler, broker consumer, server, network listener), có thể cần:

```java
public final class WorkerLifecycle implements SmartLifecycle {
    @Override
    public int getPhase() {
        return 100;
    }

    // Các methods isRunning, start, stop,
    // isAutoStartup, stop(Runnable) phải triển khai đầy đủ.
}
```

Đây là trích đoạn **không compile độc lập**, mục đích minh họa phase. Spring `SmartLifecycle` bắt đầu các phases số thấp trước, dừng theo thứ tự ngược lại. Cần phân biệt:
- **Bean creation/init** thường xảy ra trước vòng lifecycle start;
- **SmartLifecycle.start/stop** có các phase/order rules riêng;
- `@DependsOn` cũng có thể ảnh hưởng startup/shutdown dependency relationships;
- `@Order` của pipeline không phải phase start/stop.

Nếu cần startup order của hạ tầng thực, xem cả `SmartLifecycle.getPhase()` thay vì tìm cách ép mọi thứ bằng `@Order` hoặc đảo `@Bean` source methods.

### 11.3. Annotation `@Priority` có khác `@Order` không?

Spring hỗ trợ `jakarta.annotation.Priority` cho nhiều order scenarios (cần Jakarta annotation API phù hợp trên classpath). `@Priority` còn có semantics ở một số tình huống Spring cần chọn **một** element giữa nhiều candidates; `@Order` không có cùng bảo đảm về single-bean selection. `@Priority` không dùng cho `@Bean` method nếu Java target của annotation đó không cho phép methods. Khi muốn từng `@Bean` definition có collection order, dùng `@Order` trên method.

## 12. Kiểm thử thực tế: viết assertions nào?

Một bộ test tốt tách các contract thay vì in một chuỗi events rồi suy đoán.

### 12.1. Test list order

```java
List<String> names = pipeline.labels();
if (!names.equals(List.of("first", "middle", "last"))) {
    throw new AssertionError("Wrong pipeline order");
}
```

Đây là fragment dựa trên demo ở mục 9. Nó xác nhận **thứ tự tại injection point**; không xác nhận init order.

### 12.2. Test depends-on metadata

```java
String[] requires = context.getBeanFactory()
        .getBeanDefinition("worker").getDependsOn();

if (!Arrays.equals(
        requires, new String[] {"bootstrap"})) {
    throw new AssertionError("Missing depends-on");
}
```

Đây là fragment kiểm tra container metadata. Nó chứng minh đúng bean name dependency đã được đăng ký, nhưng không tự thay integration test lifecycle nếu behavior phức tạp.

### 12.3. Test init-before

Tạo hai beans có callbacks/constructors ghi vào `Events`. Xác nhận thứ tự `bootstrap` trước `worker`. Tránh đưa nhiều unrelated constructors vào log rồi kỳ vọng toàn bộ events có một total order không cần thiết.

### 12.4. Test shutdown

Đóng context bằng try-with-resources hoặc explicit `close()`; kiểm tra dependent destroy trước dependency destroy. Nếu bean implement `SmartLifecycle` hoặc có async shutdown, cần xác minh đúng phase/callback contract riêng.

### 12.5. Test khi đổi thứ tự khai báo

Chuyển factory methods sang config class khác, hoặc đảo method source order trong test fixture. Nếu contract được thể hiện bằng `@Order` và `@DependsOn` đúng, list order và init-before relationship vẫn phải đúng. Đây là test rất tốt chống một sự phụ thuộc tình cờ vào source order.

### 12.6. Test thiếu bean

Cố ý đổi `@DependsOn("bootstrap")` thành `@DependsOn("missingBootstrap")` trong một **test configuration riêng**, kỳ vọng startup hoặc lookup của dependent bean thất bại. Đọc exception root cause; tránh bắt mọi `Exception` rồi coi bất kỳ lỗi nào cũng chứng minh dependency check.

### 12.7. Test nhiều beans cùng order value

Nếu hai stages có `@Order(10)` bằng nhau, xây test xem **nghiệp vụ có yêu cầu tie-breaking hay không**. Nếu cần tổng thứ tự deterministic qua nhiều refactors, cấp order values khác nhau hoặc sort bằng explicit application key. Không cần assert một thứ tự tie ngẫu nhiên nếu không phải requirement.

## 13. Bảng lỗi và cách giải quyết

| Triệu chứng | Giải thích | Cách xử lý |
| --- | --- | --- |
| Stage có `@Order(-100)` nhưng tạo sau Stage khác | `@Order` không điều khiển startup | Dùng dependency graph/`@DependsOn` nếu cần init-before |
| List không đúng thứ tự khi gắn `@Order` trên config class | Configuration-level order không truyền xuống `@Bean` methods | Annotate target class hoặc từng `@Bean` method |
| `@DependsOn` đã có nhưng List vẫn sai thứ tự | `@DependsOn` không sort collection | Dùng `@Order`/`Ordered` |
| Đổi XML bean order rồi thứ tự init thay | Chỉ đang dựa vào registration side effect | Khai báo dependency rõ |
| `NoSuchBeanDefinitionException` với `@DependsOn` | Sai bean name/bean không đăng ký | Kiểm tra names/aliases/profiles |
| Circular depends-on | A↔B explicit dependencies | Refactor graph, loại vòng |
| `@Primary` được gắn nhưng List vẫn chứa nhiều beans | Primary chỉ chọn single injection candidate | Dùng `@Order` cho list, hoặc qualifier lọc |
| `@Order` không tự chọn một implementation | Single-bean resolution khác collection sorting | `@Qualifier`/`@Primary` |
| Handler được tiêm đúng List nhưng business calls khác thứ tự | Consumer bỏ qua thứ tự collection | Duyệt List theo contract |
| Bean lazy với `@DependsOn` chưa được tạo lúc startup | Dependent chưa bị instantiate | Kiểm tra trigger tạo dependent |
| Bean prototype không destroy theo shutdown order | Prototype lifecycle khác singleton | Cleanup instance ở owner/application |
| Bean có `@DependsOn` trên class nhưng XML vẫn không tôn trọng | Đăng ký XML bỏ qua class-level annotation trong trường hợp Javadoc nêu | Dùng XML `depends-on` |
| `SmartLifecycle` start order sai | Nhầm phase startup với bean init | Dùng `getPhase()`/dependency và test |
| Unordered List đổi order khi thêm package scan | Registration order/candidate set đổi | Set explicit `@Order` |
| Ordered interface chưa có tác dụng | Consumer không sử dụng comparator/ordered injection | Xác định điểm ordering áp dụng |
| XML `<import>` thay đổi thứ tự nhưng không sửa lỗi | File order không phải dependency contract | Thiết kế init dependency |
| BeanPostProcessor chạy thứ tự khác | Processor infrastructure có rules riêng | Tra cứu `PriorityOrdered`/`Ordered`, registration semantics |
| Cố ép mọi bean chạy theo một số thứ tự duy nhất | Thứ tự thực tế là một partial dependency graph | Chỉ khai báo dependencies cần thiết |

### 13.1. Cách debug ưu tiên bằng chứng

1. **Đọc câu hỏi thật:** đang cần thứ tự List, init callback, start/stop, hay chỉ để hiển thị?
2. **Kiểm tra bean candidates:** bean names/types/qualifiers nào thực sự có trong context?
3. **Với List:** xem annotations trên **target beans/`@Bean` methods** và implementation `Ordered`; kiểm tra order values.
4. **Với startup:** xem constructor injection, `@DependsOn` metadata, `@Lazy` và các infrastructure beans.
5. **Với shutdown:** đóng đúng context; xem destroy callbacks và dependency direction.
6. **Với source order:** ghi lại registration order nếu cần debug, nhưng đừng biến trace đó thành một API guarantee.
7. **Với lifecycle services:** phân biệt bean initialization với `SmartLifecycle.start()`/`stop()` phases.
8. **Đọc root cause:** lỗi missing dependency/circular reference khác hoàn toàn lỗi ambiguous collection hoặc wrong sorting.
9. **Kiểm thử trên Spring version thực tế:** Spring 6.2 có background initialization và các candidate-selection rules có thể ảnh hưởng những giả định cũ.
10. **Không sửa bằng cách “đổi vị trí hai methods”** trước khi xem một dependency contract có thiếu hay không.

## 14. Bài tập có đáp án

### Bài 1 — Lựa chọn annotation

Một hệ thống có ba `Handler`, muốn handlers trong injected `List<Handler>` theo thứ tự xác thực → validate → audit. Dùng gì?

**Đáp án:** `@Order` hoặc `Ordered` trên handler beans (hoặc sort explicit) và consumer duyệt ordered List. Không dùng `@DependsOn` chỉ để sort List.

### Bài 2 — Side effect phải sẵn sàng trước

Bean `worker` cần một `schemaMigrator` chạy initialization trước khi worker init, nhưng không có reference đến migrator. Dùng gì?

**Đáp án:** `@DependsOn("schemaMigrator")` trên worker hoặc tạo một dependency thật nếu nghiệp vụ có object relation.

### Bài 3 — Hai beans được viết theo thứ tự trong Java

Method `@Bean Service a()` nằm trước `@Bean Service b()`. Có tự bảo đảm a được tạo trước b không?

**Đáp án:** Không có dependency contract như vậy. Bean creation chịu BeanFactory graph, scopes và startup processing.

### Bài 4 — Âm hay dương?

`@Order(-5)` và `@Order(15)` trên hai Step. Ai đứng trước trong ordered List?

**Đáp án:** `-5` đứng trước vì số nhỏ có ưu tiên cao.

### Bài 5 — `@Order` trên configuration

`@Configuration @Order(-100)` có hai `@Bean Step` methods không order metadata. Cả hai có tự nhận `@Order(-100)` không?

**Đáp án:** Không. Configuration-level `@Order` ảnh hưởng evaluation order của config classes, không tự áp lên product beans.

### Bài 6 — Fallback registration

Không Stage nào có `@Order`. Spring docs nói List order thường dựa vào yếu tố nào?

**Đáp án:** Registration order của target bean definitions. Nhưng không nên dựa vào source declaration order như một bảo đảm dài hạn.

### Bài 7 — Destroy sequence

`@DependsOn("bootstrap")` đặt trên bean `worker`, cả hai singleton có destroy callbacks. Ai hủy trước?

**Đáp án:** Worker bị hủy trước Bootstrap khi context shutdown theo dependency relation.

### Bài 8 — `@Order` và singleton startup

`@Order(0)` trên FastHandler, `@Order(100)` trên SlowHandler. Điều đó ép FastHandler constructor luôn chạy trước SlowHandler không?

**Đáp án:** Không. `@Order` không điều khiển singleton initialization order.

### Bài 9 — Bean name

Bean được đặt `@Bean("primaryCache")`, consumer `@DependsOn("Cache")`. Spring có tự match theo class type không?

**Đáp án:** Không. DependsOn dùng names/aliases, nên hãy dùng `"primaryCache"` hoặc tên alias hợp lệ.

### Bài 10 — Constructor injection thay ordering

Bean B có constructor `B(A a)` và A là bean Spring. Có cần `@DependsOn("a")` chỉ để đảm bảo A đã được resolve trước khi B constructed?

**Đáp án:** Thông thường không; constructor injection là dependency edge thực đã buộc Spring resolve A. `@DependsOn` hữu ích cho side effects khác không có tham số.

### Bài 11 — `@Primary`

Có ba Stage beans, một `@Primary`. Khi inject `List<Stage>`, Spring chỉ inject primary bean?

**Đáp án:** Không. Collection injection thường nhận mọi eligible beans; order/filter riêng mới quyết định tập và thứ tự.

### Bài 12 — `@Qualifier`

Consumer cần một `List<Stage>` chỉ gồm nhóm `critical` và được sort. Cần những bước nào?

**Đáp án:** Lọc bằng qualifier/selection metadata thích hợp, rồi áp dụng ordering trong candidate set bằng `@Order`/`Ordered` hoặc explicit sort.

### Bài 13 — Vòng `@DependsOn`

Bean A dependsOn B, B dependsOn A. Có thể giải bằng `@Order(0)` và `@Order(1)` không?

**Đáp án:** Không. Cycle dependency graph phải được thiết kế lại; `@Order` không xóa cạnh phụ thuộc.

### Bài 14 — Prototype và destruction

Prototype Worker dependsOn Singleton Bootstrap. Khi context close, Spring có tự tìm mọi prototype Workers đã cấp để chạy destroy đúng trước bootstrap không?

**Đáp án:** Không. Spring không quản lý tự động việc hủy mọi prototype như singleton; owner cần cleanup đúng.

### Bài 15 — SmartLifecycle

Một server cần Listener A start trước Listener B và stop sau B; hai beans implement `SmartLifecycle`. Nên xem cơ chế nào?

**Đáp án:** `getPhase()` và các dependencies tương ứng; phase nhỏ start trước, stop sau, không dùng `@Order` của List để ép lifecycle.

### Bài 16 — Order bằng nhau

Hai beans có `@Order(10)`, thứ tự tuyệt đối giữa chúng rất quan trọng. Có nên dựa vào thứ tự scan/register không?

**Đáp án:** Không; cấp thứ tự phân biệt hoặc dùng application comparator/key explicit và test.

### Bài 17 — Test scope

Trong demo, `Pipeline` in order đúng nhưng `Events` cho init order ngược. Có thể cả hai đúng theo Spring contract không?

**Đáp án:** Có. Collection sorting và singleton initialization là hai mục tiêu độc lập; phải biết dependency graph.

### Bài 18 — Annotation trên XML-declared class

Class `Worker` mang `@DependsOn("bootstrap")` nhưng được khai `<bean class="...">` trong legacy XML. Annotation trên class có chắc được áp dụng không?

**Đáp án:** Theo `@DependsOn` Javadoc, class-level annotation được xử lý theo component scanning; khi đăng ký bằng XML theo con đường nêu trong Javadoc, cần dùng XML `depends-on` để bảo đảm.

### Bài 19 — Thêm `@Order` vào một bean hạ tầng

Một BeanFactoryPostProcessor chạy quá muộn; team chỉ thêm `@Order(-999)` mà không kiểm tra cách processor được register. Đã đủ chưa?

**Đáp án:** Chưa. Infrastructure extension points có ordering policies riêng (`PriorityOrdered`/`Ordered` và registration rules); cần tra đúng extension point.

### Bài 20 — Yêu cầu nhiều dependencies

Service phải chờ Migrator và CacheWarmup, CacheWarmup phải chờ Migrator. Có nên chỉ đặt `@DependsOn({"migrator","cacheWarmup"})` trên service không?

**Đáp án:** Chưa biểu đạt trực tiếp dependency giữa CacheWarmup và Migrator. Hãy khai `cacheWarmup` dependsOn `migrator`, service dependsOn cacheWarmup (và những quan hệ khác thật sự cần).

## 15. Checklist trước khi merge cấu hình bean ordering

- Requirement là **List order** hay **bean init-before** hay **runtime start/stop**?
- Với List, `@Order` có đặt trên **target beans/`@Bean` methods** chứ không chỉ config class?
- Có đúng convention số nhỏ đứng trước? Có ties ảnh hưởng nghiệp vụ?
- Consumer có thực sự duyệt ordered List hay lại tự lookup theo name/map?
- `@Primary`/`@Qualifier` có được dùng đúng để chọn/giới hạn candidates, không nhầm order?
- Nếu không có order metadata, có đang dựa vào registration fallback như một hợp đồng mong manh?
- Với init dependency, `@DependsOn`/constructor injection có biểu diễn cạnh phụ thuộc thật không?
- Những names trong `@DependsOn` có tồn tại đúng theo XML/JavaConfig/alias registration?
- `@DependsOn` ở class có thực sự được Spring đọc theo phương thức đăng ký bean hiện tại?
- Lazy/prototype/FactoryBean/background init có thay đổi thời điểm tạo dependency?
- Với singleton destroy, đã test dependent hủy trước dependency khi context close chưa?
- Có vô tình tạo vòng dependsOn/dependency graph không?
- Với `SmartLifecycle` đã dùng phase/start/stop semantics riêng khi cần?
- Tests có kiểm tra **cả** injected List và startup/shutdown log thay vì gộp thành một assertion?
- Refactor imports, scan roots hoặc source file method order có làm thay đổi bất kỳ contract thực sự nào không?
- Metadata ordering có được ghi rõ trong tài liệu module để người bảo trì không sửa sai?

## 16. Tổng kết

**`@Order`** trả lời “nếu có nhiều ứng viên cùng loại được tiêu thụ như một danh sách, phần tử nào đứng trước?”; số nhỏ được ưu tiên. Annotation có thể đặt trên bean class hoặc từng `@Bean` method; khi đặt trên `@Configuration` class, nó không tự truyền order xuống từng product bean. `@Order` **không** bảo đảm thứ tự tạo singletons.

**`@DependsOn`** trả lời “để tạo bean này, những bean nào phải được khởi tạo trước?” và, với singleton beans, “khi shutdown, dependent phải được hủy trước dependency nào?”. Nó dùng **bean names**, không phải Java class names, và không sắp List.

**Thứ tự định nghĩa/đăng ký** là một trục khác: Spring có thể dùng registration order làm fallback cho unordered injected List, nhưng source method/XML order **không phải** cách chuẩn để ràng buộc init-before. Hãy dùng đúng abstraction cho requirement: `@Order` cho tập cần sort; DI hoặc `@DependsOn` cho dependency initialization; `SmartLifecycle` phase cho start/stop services.

### Tài liệu Spring Framework 6.2 chính thức

- [Spring Framework 6.2 — Using `@Autowired`, section Arrays and Collections](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html).
- [Spring Framework 6.2 — Using `depends-on`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html).
- [Spring Framework 6.2 — Composing Java-based Configurations, startup singletons](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — `@Order` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/annotation/Order.html).
- [Spring Framework 6.2 — `@DependsOn` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/DependsOn.html).
- [Spring Framework 6.2 — Customizing the Nature of a Bean: Lifecycle and `SmartLifecycle`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — `@Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html).
