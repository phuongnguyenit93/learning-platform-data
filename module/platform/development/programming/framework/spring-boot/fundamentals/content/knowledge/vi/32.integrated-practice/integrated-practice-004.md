# Quan sát singleton, prototype và cách lấy bean theo nhu cầu

Trong Spring, scope quyết định **container quản lý số lượng instance bean như thế nào và khi nào một instance mới được tạo**. Hai scope nền tảng cần hiểu rõ là `singleton` và `prototype`.

- `singleton`: một instance cho mỗi bean definition trong một `ApplicationContext`.
- `prototype`: mỗi lần yêu cầu bean từ container, Spring tạo một instance mới.

Sự khác biệt nghe có vẻ đơn giản, nhưng ảnh hưởng trực tiếp đến state, dependency injection, thread safety, lifecycle và cách viết test. Một lỗi thường gặp là inject prototype bean vào một singleton rồi mong Spring tự tạo prototype mới mỗi lần gọi method. Thực tế, dependency được resolve khi singleton được tạo, nên singleton giữ cùng một prototype instance nếu không có cơ chế lookup lại.

Bài học **Spring Boot Fundamentals → Thực hành tổng hợp → Quan sát singleton, prototype và cách lấy bean theo nhu cầu** hướng dẫn cách quan sát identity của bean, kiểm tra scope trong context, lấy prototype theo từng lần cần, chọn đúng bean khi có nhiều implementation và quản lý tài nguyên của prototype.

## 1. Scope bean là gì?

Scope mô tả vòng đời và phạm vi chia sẻ instance mà Spring container áp dụng cho một bean definition.

Khi container tạo bean, scope ảnh hưởng các câu hỏi:

- Một lần đăng ký bean có tạo một instance dùng chung hay nhiều instance?
- Khi code yêu cầu bean lần nữa, Spring trả lại object cũ hay tạo object mới?
- Instance có được chia sẻ giữa các consumer không?
- Ai chịu trách nhiệm giải phóng tài nguyên khi instance không còn được dùng?

Các scope thông dụng:

| Scope | Hành vi | Phạm vi |
|---|---|---|
| `singleton` | Một instance được dùng lại | Mỗi bean definition trong một container |
| `prototype` | Tạo instance mới mỗi lần container resolve bean | Mỗi lần yêu cầu |
| `request` | Một instance trong một HTTP request | Web application context |
| `session` | Một instance trong một HTTP session | Web application context |
| `application` | Một instance trong ServletContext | Web application context |
| `websocket` | Một instance trong vòng đời WebSocket | Web application context |

Trong ứng dụng Spring Boot thông thường, phần lớn service, repository, controller và component được đăng ký với scope mặc định là `singleton`.

Bài học tập trung vào `singleton`, `prototype` và những cách lấy bean theo nhu cầu. Các web scope được nhắc tới để phân biệt, không phải mục tiêu triển khai chính.

## 2. Singleton: một instance cho mỗi bean definition trong một container

Khi một bean không khai báo scope riêng, Spring mặc định dùng `singleton`.

Ví dụ:

~~~java
@Service
public class CartService {
    public int itemCount() {
        return 0;
    }
}
~~~

Spring tạo và quản lý một instance `CartService` cho bean definition đó trong `ApplicationContext`. Khi nhiều consumer inject cùng bean, họ thường nhận cùng một object:

~~~text
ApplicationContext
       |
       +-- bean definition: cartService
                 |
                 v
          CartService instance
             /        \
            /          \
           v            v
    CheckoutFacade   CartController
~~~

Một cấu hình tường minh cũng có thể viết:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
CartService cartService() {
    return new CartService();
}
~~~

Nhưng vì singleton là mặc định, annotation `@Scope` thường không cần thiết nếu không có mục đích nhấn mạnh.

### 2.1. Singleton không có nghĩa là một object cho toàn JVM

Đây là điểm rất dễ nhầm.

Singleton của Spring được giới hạn theo **container và bean definition**, không phải singleton pattern toàn cục trong JVM.

Nếu tạo hai context độc lập:

~~~java
try (var first = new AnnotationConfigApplicationContext(AppConfig.class);
     var second = new AnnotationConfigApplicationContext(AppConfig.class)) {

    Object a = first.getBean(CartService.class);
    Object b = second.getBean(CartService.class);

    System.out.println(a == b); // false
}
~~~

Hai context có hai instance riêng. Trong mỗi context, các lần resolve bean tương ứng sẽ trả về cùng instance.

Một ứng dụng bình thường thường có một root context, nhưng test, ứng dụng nhiều context, parent/child context hoặc các ứng dụng nhúng có thể tạo nhiều container.

Vì vậy, câu nói chính xác là:

> Một singleton bean có một instance được chia sẻ trong phạm vi bean definition của ApplicationContext quản lý nó.

### 2.2. Quan sát singleton bằng identity

Có thể kiểm tra trực tiếp bằng toán tử `==` hoặc JUnit `assertSame`.

~~~java
@Test
void singletonReturnsTheSameInstance() {
    try (var context =
            new AnnotationConfigApplicationContext(AppConfig.class)) {

        CartService first = context.getBean(CartService.class);
        CartService second = context.getBean(CartService.class);

        assertSame(first, second);
    }
}
~~~

`assertSame` kiểm tra hai biến tham chiếu tới cùng object. Đây là phép kiểm tra phù hợp hơn việc so sánh giá trị do `equals()` định nghĩa.

Nếu class override `equals()` để so sánh dữ liệu, hai object khác nhau vẫn có thể `equals()` trả về true. Điều đó không chứng minh chúng là cùng instance.

### 2.3. Quan sát state dùng chung

Một bean singleton có thể giữ state:

~~~java
public class RequestCounter {

    private int count;

    public void increment() {
        count++;
    }

    public int current() {
        return count;
    }
}
~~~

Nếu hai consumer cùng nhận bean này, thay đổi qua consumer thứ nhất sẽ được consumer thứ hai quan sát:

~~~java
RequestCounter first = context.getBean(RequestCounter.class);
RequestCounter second = context.getBean(RequestCounter.class);

first.increment();

assertEquals(1, second.current());
assertSame(first, second);
~~~

Ví dụ này cho thấy singleton chia sẻ cả identity và state của object. Nó cũng gợi ra một yêu cầu thiết kế quan trọng: **state mutable của singleton cần được quản lý cẩn thận khi nhiều request hoặc thread cùng truy cập**.

## 3. Thread safety của singleton

Spring singleton không tự động thread-safe. Container chỉ quản lý việc tạo và chia sẻ instance; nó không tự khóa mọi method hay bảo vệ field mutable của bean.

Ví dụ có rủi ro:

~~~java
@Service
public class ShoppingCartService {

    private final List<String> currentItems = new ArrayList<>();

    public void add(String item) {
        currentItems.add(item);
    }

    public List<String> items() {
        return currentItems;
    }
}
~~~

Nếu `ShoppingCartService` là singleton, danh sách trên được chia sẻ giữa tất cả caller. Dữ liệu của người dùng này có thể lẫn với người dùng khác và `ArrayList` không an toàn khi có truy cập đồng thời không được đồng bộ.

Với service xử lý request, thiết kế thường tốt hơn là giữ bean stateless:

~~~java
@Service
public class ShoppingCartService {

    public Cart calculate(CartInput input) {
        // Dữ liệu của một lần xử lý nằm trong biến cục bộ.
        return new Cart(input.items());
    }
}
~~~

Nếu cần state dùng chung thật sự, hãy chọn cơ chế phù hợp:

- Collection đồng bộ hoặc concurrent collection.
- Atomic type hoặc lock khi cần thao tác nguyên tử.
- Database/cache chuyên dụng cho state chia sẻ.
- State gắn với request/user được lưu ở scope phù hợp hoặc truyền qua tham số.
- Một component quản lý state có contract và concurrency policy rõ ràng.

**Không nên đổi mọi service sang prototype chỉ để tránh nghĩ về thread safety.** Prototype cũng không tự làm object thread-safe; caller vẫn có thể chia sẻ một prototype instance cho nhiều thread.

## 4. Prototype: mỗi lần yêu cầu tạo một instance mới

Khai báo prototype bằng `@Scope`:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class WorkUnit {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Hoặc dùng tên scope:

~~~java
@Component
@Scope("prototype")
public class WorkUnit {
    // ...
}
~~~

Khi container được yêu cầu resolve bean `workUnit`, Spring tạo instance mới theo bean definition.

~~~text
Lần gọi getBean("workUnit") thứ nhất
             |
             v
        WorkUnit A

Lần gọi getBean("workUnit") thứ hai
             |
             v
        WorkUnit B

Lần gọi getBean("workUnit") thứ ba
             |
             v
        WorkUnit C
~~~

Thông thường:

~~~java
WorkUnit first = context.getBean(WorkUnit.class);
WorkUnit second = context.getBean(WorkUnit.class);

assertNotSame(first, second);
assertNotEquals(first.id(), second.id());
~~~

Mỗi lần resolve prototype từ container sẽ tạo instance mới. Nếu code lấy một lần rồi lưu reference vào field, các lần dùng field đó vẫn đang sử dụng cùng instance đã lấy; scope prototype không tự thay reference trong object consumer.

### 4.1. Prototype không phải “mỗi method call tự tạo object”

Scope chỉ áp dụng khi container resolve bean. Nó không can thiệp vào mọi lần gọi method trên reference mà caller đang giữ.

Ví dụ:

~~~java
WorkUnit unit = context.getBean(WorkUnit.class);

unit.execute();
unit.execute();
unit.execute();
~~~

Ba lần gọi `execute()` diễn ra trên **cùng một WorkUnit instance**. Muốn instance mới, phải yêu cầu bean từ container thêm lần nữa hoặc dùng một cơ chế lookup theo nhu cầu.

Đây là khác biệt cốt lõi giữa vòng đời object và số lần gọi method.

## 5. Cấu hình thực hành để quan sát hai scope

Tạo hai class đơn giản.

`SingletonProbe.java`:

~~~java
package com.example.scope;

import java.util.UUID;

public class SingletonProbe {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

`PrototypeProbe.java`:

~~~java
package com.example.scope;

import java.util.UUID;

public class PrototypeProbe {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Cấu hình:

~~~java
package com.example.scope;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

@Configuration(proxyBeanMethods = false)
public class ScopeConfiguration {

    @Bean
    SingletonProbe singletonProbe() {
        return new SingletonProbe();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    PrototypeProbe prototypeProbe() {
        return new PrototypeProbe();
    }
}
~~~

`singletonProbe` dùng scope mặc định. `prototypeProbe` được yêu cầu tạo instance mới mỗi lần resolve.

Test:

~~~java
package com.example.scope;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class BeanScopeTest {

    @Test
    void observesSingletonAndPrototype() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        ScopeConfiguration.class)) {

            SingletonProbe singletonA =
                    context.getBean(SingletonProbe.class);
            SingletonProbe singletonB =
                    context.getBean(SingletonProbe.class);

            PrototypeProbe prototypeA =
                    context.getBean(PrototypeProbe.class);
            PrototypeProbe prototypeB =
                    context.getBean(PrototypeProbe.class);

            assertSame(singletonA, singletonB);
            assertNotSame(prototypeA, prototypeB);
            assertNotEquals(prototypeA.id(), prototypeB.id());
        }
    }
}
~~~

Bài test dùng context thực để xác nhận hành vi scope do Spring quản lý. Nó không chỉ gọi constructor bằng `new`.

## 6. Kiểm tra scope từ ApplicationContext

Ngoài việc so sánh identity, có thể hỏi container bean có scope nào:

~~~java
boolean singleton =
        context.isSingleton("singletonProbe");

boolean prototype =
        context.isPrototype("prototypeProbe");
~~~

Kết quả mong đợi trong cấu hình trên:

~~~java
assertTrue(context.isSingleton("singletonProbe"));
assertTrue(context.isPrototype("prototypeProbe"));
~~~

Các API này giúp quan sát metadata/hành vi scope theo bean name.

Nếu có nhiều bean cùng kiểu, cần chỉ rõ tên bean hoặc qualifier. Không nên dùng một kiểu Java duy nhất để suy ra tên bean duy nhất.

Có thể liệt kê tên bean theo type:

~~~java
String[] names =
        context.getBeanNamesForType(PrototypeProbe.class);
~~~

Nếu muốn xem metadata bean definition chi tiết hơn, với một context có bean factory hỗ trợ registry có thể truy cập `BeanDefinitionRegistry`:

~~~java
BeanDefinitionRegistry registry =
        (BeanDefinitionRegistry) context.getBeanFactory();

String scope =
        registry.getBeanDefinition("prototypeProbe").getScope();
~~~

Một bean definition không ghi scope tường minh có thể trả về chuỗi rỗng vì singleton là mặc định. Vì thế, `getScope()` rỗng không có nghĩa bean không có scope. `context.isSingleton(...)` thể hiện hành vi hiệu lực rõ hơn cho ví dụ này.

## 7. Khác biệt lifecycle giữa singleton và prototype

Spring quản lý lifecycle của singleton khá đầy đủ:

~~~text
Tạo singleton
     |
     v
Dependency injection
     |
     v
Initialization callbacks
     |
     v
Bean được sử dụng
     |
     v
ApplicationContext đóng
     |
     v
Destroy callbacks
~~~

Với prototype:

~~~text
Container được yêu cầu bean
        |
        v
Tạo instance mới
        |
        v
Dependency injection
        |
        v
Initialization callbacks
        |
        v
Trả instance cho caller
        |
        v
Caller sở hữu việc dùng và cleanup
~~~

Spring vẫn thực hiện các bước tạo và khởi tạo prototype bean, bao gồm dependency injection và init callbacks. Nhưng sau khi giao instance cho caller, container **không tiếp tục quản lý toàn bộ destruction lifecycle của prototype như singleton**.

Đặc biệt, Spring không tự động gọi `@PreDestroy` hoặc destroy method cho từng prototype instance khi ApplicationContext đóng.

Điều này rất quan trọng nếu prototype giữ:

- File handle hoặc stream.
- Socket hoặc client connection.
- Executor hoặc thread.
- Temporary file.
- Native resource.
- Một object có callback cleanup riêng.

Caller hoặc một component sở hữu prototype cần có chính sách đóng tài nguyên.

## 8. Bẫy thường gặp: inject prototype trực tiếp vào singleton

Giả sử có prototype bean:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Và singleton consumer:

~~~java
@Service
public class JobCoordinator {

    private final JobContext jobContext;

    public JobCoordinator(JobContext jobContext) {
        this.jobContext = jobContext;
    }

    public UUID currentJobId() {
        return jobContext.id();
    }
}
~~~

Nhiều người kỳ vọng mỗi lần gọi `currentJobId()` sẽ có một `JobContext` mới vì `JobContext` là prototype.

Thực tế:

1. Spring tạo singleton `JobCoordinator`.
2. Trong quá trình tạo coordinator, Spring resolve dependency `JobContext`.
3. Một prototype instance được tạo và inject vào constructor.
4. Coordinator giữ reference đó trong field.
5. Những lần gọi `currentJobId()` tiếp theo dùng cùng reference.

~~~text
ApplicationContext tạo JobCoordinator
                 |
                 v
       resolve JobContext prototype
                 |
                 v
             JobContext A
                 |
                 v
       inject vào JobCoordinator
                 |
                 v
     JobCoordinator giữ reference A
           /           \
          v             v
      call #1        call #2
          |             |
          +------ A ----+
~~~

Scope prototype chỉ yêu cầu Spring tạo instance mới khi Spring được hỏi lấy bean mới. Nó không làm dependency đã inject tự thay đổi.

Test có thể quan sát:

~~~java
@Test
void prototypeInjectedDirectlyIntoSingletonIsResolvedOnce() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    DirectInjectionConfiguration.class)) {

        JobCoordinator coordinator =
                context.getBean(JobCoordinator.class);

        UUID first = coordinator.currentJobId();
        UUID second = coordinator.currentJobId();

        assertEquals(first, second);
    }
}
~~~

Tên class `DirectInjectionConfiguration` đại diện cho cấu hình đăng ký `JobContext` prototype và `JobCoordinator` singleton như ví dụ.

**Đây là một trong những quy tắc quan trọng nhất khi kết hợp scope.**

## 9. Dùng ObjectProvider để lấy prototype theo nhu cầu

Spring cung cấp `ObjectProvider<T>` để consumer yêu cầu bean từ container vào đúng thời điểm cần.

Thay vì inject prototype instance:

~~~java
public JobCoordinator(JobContext jobContext) {
    this.jobContext = jobContext;
}
~~~

hãy inject provider:

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> jobContexts;

    public JobCoordinator(ObjectProvider<JobContext> jobContexts) {
        this.jobContexts = jobContexts;
    }

    public UUID startNewJob() {
        JobContext context = jobContexts.getObject();
        return context.id();
    }
}
~~~

Mỗi lần gọi `getObject()`, provider resolve bean theo scope đã đăng ký. Nếu `JobContext` là prototype, mỗi lần sẽ tạo một instance mới.

~~~text
Singleton JobCoordinator
          |
          v
ObjectProvider<JobContext>
          |
          +-- getObject() --> JobContext A
          |
          +-- getObject() --> JobContext B
          |
          +-- getObject() --> JobContext C
~~~

Điểm quan trọng: `ObjectProvider` không tự biến bean thành prototype. Nó áp dụng quy tắc scope của bean được resolve. Nếu bean là singleton, nhiều lần `getObject()` vẫn trả về cùng singleton.

### 9.1. Ví dụ đầy đủ

Prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

Singleton:

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public JobContext createContext() {
        return contexts.getObject();
    }
}
~~~

Test:

~~~java
@Test
void providerCreatesANewPrototypeForEachLookup() {
    try (var context =
            new AnnotationConfigApplicationContext(JobConfiguration.class)) {

        JobCoordinator coordinator =
                context.getBean(JobCoordinator.class);

        JobContext first = coordinator.createContext();
        JobContext second = coordinator.createContext();

        assertNotSame(first, second);
        assertNotEquals(first.id(), second.id());
    }
}
~~~

Test xác nhận một singleton có thể yêu cầu nhiều prototype instance trong suốt vòng đời của nó.

### 9.2. Khi nào ObjectProvider phù hợp?

- Một bean cần được tạo theo từng lần xử lý.
- Dependency có thể không tồn tại trong một số cấu hình.
- Có nhiều candidate và consumer cần resolve theo qualifier.
- Cần trì hoãn việc resolve dependency.
- Cần truy cập bean theo nhu cầu thay vì giữ một instance được inject sẵn.

`ObjectProvider` là API của Spring, tích hợp với bean factory và các cơ chế dependency resolution.

## 10. Các method hữu ích của ObjectProvider

`ObjectProvider<T>` có nhiều cách lấy bean:

| Method | Ý nghĩa |
|---|---|
| `getObject()` | Resolve bean; ném lỗi nếu không thể cung cấp |
| `getIfAvailable()` | Trả bean nếu có, hoặc `null` nếu không có |
| `getIfUnique()` | Trả bean nếu xác định được một candidate duy nhất |
| `ifAvailable(consumer)` | Thực thi consumer khi có bean |
| `ifUnique(consumer)` | Thực thi consumer khi có một bean duy nhất |
| `stream()` | Stream các candidate phù hợp |
| `orderedStream()` | Stream candidate theo thứ tự Spring áp dụng |

Ví dụ dependency tùy chọn:

~~~java
@Service
public class ReportCoordinator {

    private final ObjectProvider<ReportExporter> exporters;

    public ReportCoordinator(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void exportIfConfigured(Report report) {
        ReportExporter exporter = exporters.getIfAvailable();

        if (exporter != null) {
            exporter.export(report);
        }
    }
}
~~~

Nếu exporter là bắt buộc, dùng `getObject()` và để lỗi dependency được thể hiện rõ. Nếu exporter là tùy chọn, `getIfAvailable()` làm ý định rõ ràng hơn.

### 10.1. getIfAvailable và getIfUnique không giống nhau

Giả sử có hai bean cùng implement `ReportExporter`.

- `getIfAvailable()` có thể ném lỗi nếu có nhiều candidate không thể phân giải duy nhất.
- `getIfUnique()` trả về một candidate nếu có thể xác định duy nhất theo quy tắc resolution, nếu không có thể trả `null`.

Không nên dùng `getIfUnique()` để che một cấu hình có nhiều implementation mà nghiệp vụ cần chọn rõ ràng. Nếu lựa chọn là bắt buộc, dùng qualifier hoặc một registry có quy tắc chọn cụ thể.

## 11. Lấy bean theo nhu cầu bằng ApplicationContext

Có thể inject `ApplicationContext` rồi gọi `getBean()`:

~~~java
@Service
public class JobCoordinator {

    private final ApplicationContext context;

    public JobCoordinator(ApplicationContext context) {
        this.context = context;
    }

    public JobContext createContext() {
        return context.getBean(JobContext.class);
    }
}
~~~

Với prototype, mỗi lần gọi sẽ resolve một instance mới.

Cách này hoạt động, nhưng nó khiến class phụ thuộc trực tiếp vào Spring container API. Nó mang phong cách **Service Locator**: class tự đi tìm dependency thay vì khai báo rõ dependency cần dùng qua constructor.

So sánh:

~~~java
public JobCoordinator(ObjectProvider<JobContext> contexts) {
    this.contexts = contexts;
}
~~~

với:

~~~java
public JobCoordinator(ApplicationContext context) {
    this.context = context;
}
~~~

`ObjectProvider<JobContext>` mô tả rõ consumer cần lấy một `JobContext` theo nhu cầu. `ApplicationContext` cho phép truy cập gần như toàn bộ container, làm dependency ẩn hơn và khiến unit test phải giả lập thêm framework API.

**Ưu tiên inject `ObjectProvider<T>` khi chỉ cần resolve một loại bean cụ thể theo nhu cầu.** Dùng `ApplicationContext.getBean()` khi class thực sự có trách nhiệm điều phối container hoặc plugin registry và việc đó là một phần thiết kế có chủ đích.

Không nên inject `ApplicationContext` vào mọi service chỉ để thay constructor injection bằng lookup thủ công.

## 12. Dùng jakarta.inject.Provider khi phù hợp

Nếu dự án có dependency `jakarta.inject-api`, có thể sử dụng `jakarta.inject.Provider<T>`:

~~~java
import jakarta.inject.Provider;

@Service
public class JobCoordinator {

    private final Provider<JobContext> contexts;

    public JobCoordinator(Provider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public JobContext createContext() {
        return contexts.get();
    }
}
~~~

Provider biểu diễn một nguồn có thể resolve object khi cần. Spring hỗ trợ tích hợp kiểu Provider trong dependency injection khi API tương ứng có mặt.

Khác biệt thực hành:

- `ObjectProvider<T>` là API của Spring và có các method như `getIfAvailable`, `getIfUnique`, `stream`.
- `Provider<T>` là abstraction từ Jakarta Inject, có API đơn giản hơn với `get()`.

Nếu ứng dụng đã dùng Spring và cần các khả năng resolution đặc thù của Spring, `ObjectProvider` thường tiện hơn. Nếu code muốn phụ thuộc vào chuẩn injection độc lập hơn, `Provider` có thể phù hợp.

Không cần thêm abstraction thứ hai nếu `ObjectProvider` đã giải quyết rõ nhu cầu.

## 13. Method injection với @Lookup

Một cách khác để lấy prototype từ singleton là method injection bằng `@Lookup`.

Ví dụ:

~~~java
@Component
public abstract class JobCoordinator {

    public JobContext createContext() {
        return createJobContext();
    }

    @Lookup
    protected abstract JobContext createJobContext();
}
~~~

Spring tạo subclass cho bean `JobCoordinator` và override method lookup để resolve bean `JobContext` từ container khi method được gọi.

Mỗi lần gọi `createJobContext()`, Spring thực hiện lookup theo bean definition và scope của `JobContext`. Nếu prototype, mỗi lần gọi trả về instance mới.

~~~text
Caller
  |
  v
JobCoordinator proxy/subclass
  |
  v
@Lookup method
  |
  v
BeanFactory.getBean(JobContext)
  |
  v
Prototype instance mới
~~~

### 13.1. Điều kiện và giới hạn của @Lookup

- Bean chứa method lookup phải do Spring quản lý.
- Spring cần có khả năng tạo subclass để override method.
- Method lookup không thể là `private`, `final` hoặc `static`.
- Class không nên là `final`.
- Không tự tạo coordinator bằng `new` nếu muốn method injection hoạt động.
- Cần kiểm tra behavior khi dùng factory method hoặc các cấu hình bean đặc biệt.

Ví dụ này minh họa method injection, nhưng với nhiều dự án, `ObjectProvider<T>` thường dễ đọc và dễ test hơn vì dependency được khai báo rõ trong constructor.

### 13.2. Khi nào @Lookup có ích?

- Muốn method diễn đạt trực tiếp hành động “tạo một instance mới”.
- Class có một điểm lookup rõ ràng và ít dependency động.
- Dự án đã quen với method injection.
- Cần tránh một service locator tổng quát.

Nếu class cần nhiều loại lookup hoặc cần optional resolution, `ObjectProvider` thường linh hoạt hơn.

## 14. So sánh các cách lấy prototype theo nhu cầu

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| Inject prototype trực tiếp vào singleton | Cấu hình đơn giản | Chỉ resolve một lần khi singleton được tạo |
| `ObjectProvider<T>` | Dependency rõ, hỗ trợ optional và nhiều candidate | Consumer phụ thuộc API Spring |
| `Provider<T>` | API injection gọn, ít đặc thù framework | Ít chức năng resolution hơn |
| `ApplicationContext.getBean()` | Linh hoạt, dễ lookup theo tên/kiểu | Service Locator, dependency container bị ẩn |
| `@Lookup` | Method thể hiện ý định lấy instance theo lần gọi | Cần subclassing, có giới hạn method/class |

Với một singleton cần prototype mới mỗi lần xử lý, lựa chọn thường dễ duy trì là:

~~~java
private final ObjectProvider<JobContext> contexts;
~~~

và gọi:

~~~java
JobContext context = contexts.getObject();
~~~

## 15. Lấy bean theo type, name và qualifier

Trong một context có thể có nhiều bean cùng implement một interface.

Ví dụ:

~~~java
public interface DocumentExporter {
    void export(Document document);
}
~~~

~~~java
@Component
@Qualifier("pdf")
public class PdfExporter implements DocumentExporter {
    @Override
    public void export(Document document) {
        // Xuất PDF.
    }
}
~~~

~~~java
@Component
@Qualifier("csv")
public class CsvExporter implements DocumentExporter {
    @Override
    public void export(Document document) {
        // Xuất CSV.
    }
}
~~~

Nếu inject:

~~~java
public ExportCoordinator(DocumentExporter exporter) {
    this.exporter = exporter;
}
~~~

Spring có thể báo `NoUniqueBeanDefinitionException` vì có nhiều candidate cùng kiểu.

Có thể chọn bằng qualifier:

~~~java
public ExportCoordinator(
        @Qualifier("pdf") DocumentExporter exporter
) {
    this.exporter = exporter;
}
~~~

Nếu cần lấy theo nhu cầu:

~~~java
public ExportCoordinator(
        @Qualifier("pdf")
        ObjectProvider<DocumentExporter> exporters
) {
    this.exporters = exporters;
}
~~~

~~~java
public void export(Document document) {
    exporters.getObject().export(document);
}
~~~

Qualifier giới hạn tập candidate; provider quyết định thời điểm resolve. Nếu candidate được chọn là prototype, mỗi lần gọi provider tạo instance mới; nếu là singleton, provider trả instance singleton đã quản lý.

### 15.1. Bean name và type lookup

Có thể lookup theo tên và kiểu:

~~~java
DocumentExporter exporter =
        context.getBean("pdfExporter", DocumentExporter.class);
~~~

Cách này hữu ích khi tên bean là một phần cấu hình rõ ràng, nhưng việc hardcode tên bean trong nhiều service có thể làm coupling tăng.

Nếu lựa chọn là quyết định nghiệp vụ, có thể thiết kế một factory/registry với API rõ nghĩa:

~~~java
public interface ExporterRegistry {
    DocumentExporter exporterFor(ExportFormat format);
}
~~~

Registry có thể dùng map/qualifier/provider bên trong, trong khi consumer chỉ biết contract nghiệp vụ.

## 16. Singleton phụ thuộc prototype: ba thiết kế thường gặp

Giả sử một ứng dụng tạo nhiều `JobContext` trong vòng đời của `JobCoordinator`.

### Cách A — Inject prototype trực tiếp

~~~java
@Service
public class JobCoordinator {

    private final JobContext context;

    public JobCoordinator(JobContext context) {
        this.context = context;
    }
}
~~~

Kết quả: một prototype được resolve khi singleton được tạo và giữ lại.

Phù hợp khi singleton chỉ cần một prototype instance gắn với chính vòng đời singleton. Không phù hợp khi muốn một instance mới cho từng job.

### Cách B — Inject ObjectProvider

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void startJob() {
        JobContext context = contexts.getObject();
        // Xử lý job bằng context mới.
    }
}
~~~

Kết quả: mỗi lần `getObject()` resolve một prototype mới.

Phù hợp khi singleton cần nhiều instance theo từng thao tác.

### Cách C — Inject factory do ứng dụng định nghĩa

~~~java
public interface JobContextFactory {
    JobContext create();
}
~~~

~~~java
@Component
public class SpringJobContextFactory implements JobContextFactory {

    private final ObjectProvider<JobContext> contexts;

    public SpringJobContextFactory(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    @Override
    public JobContext create() {
        return contexts.getObject();
    }
}
~~~

Singleton phụ thuộc factory:

~~~java
@Service
public class JobCoordinator {

    private final JobContextFactory factory;

    public JobCoordinator(JobContextFactory factory) {
        this.factory = factory;
    }

    public void startJob() {
        JobContext context = factory.create();
        // ...
    }
}
~~~

Factory hữu ích khi muốn tách Spring-specific lookup khỏi domain/service logic. Unit test có thể truyền fake factory để tạo object theo kịch bản.

Không cần tạo factory chỉ để bọc một dòng `getObject()` nếu không có lợi ích về boundary, testability hoặc logic tạo object. Chọn abstraction theo nhu cầu thực tế.

## 17. Tạo bean prototype và cleanup tài nguyên

Spring gọi initialization callbacks cho prototype, nhưng không tự gọi destroy callback khi context đóng.

Ví dụ:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryWorkspace implements AutoCloseable {

    private final Path directory;

    public TemporaryWorkspace() throws IOException {
        this.directory = Files.createTempDirectory("job-");
    }

    public Path directory() {
        return directory;
    }

    @Override
    public void close() throws IOException {
        // Xóa file tạm và thư mục theo chính sách ứng dụng.
    }
}
~~~

Nếu lấy prototype qua provider:

~~~java
TemporaryWorkspace workspace = workspaces.getObject();

try {
    process(workspace);
} finally {
    workspace.close();
}
~~~

Caller biết instance được tạo ra và có trách nhiệm đóng resource.

Có thể dùng try-with-resources nếu type implement `AutoCloseable`:

~~~java
try (TemporaryWorkspace workspace = workspaces.getObject()) {
    process(workspace);
}
~~~

Cách này bảo đảm `close()` được gọi cả khi `process()` ném exception.

### 17.1. @PreDestroy trên prototype không tự chạy khi context đóng

Ví dụ:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PrototypeResource {

    @PreDestroy
    public void destroy() {
        // Đóng tài nguyên.
    }
}
~~~

Không nên kỳ vọng Spring tự gọi method `destroy()` cho mọi instance prototype khi ApplicationContext đóng. Container không giữ danh sách để quản lý toàn bộ destruction lifecycle của prototype theo cách singleton.

Nếu cần Spring thực thi destruction-aware callbacks cho một prototype cụ thể, code sở hữu instance có thể yêu cầu `AutowireCapableBeanFactory.destroyBean(instance)` khi đã hoàn tất. Tuy nhiên, với tài nguyên có hợp đồng Java rõ như `AutoCloseable`, caller gọi `close()` trực tiếp thường dễ hiểu hơn.

Tránh vừa gọi `close()` thủ công vừa gọi destroy callback mà không có thiết kế idempotent, vì có thể giải phóng cùng resource hai lần.

## 18. Lazy initialization khác prototype

`@Lazy` điều khiển thời điểm khởi tạo bean hoặc resolve dependency. Nó không đồng nghĩa với prototype.

Ví dụ singleton lazy:

~~~java
@Component
@Lazy
public class ExpensiveCatalog {
    // Khởi tạo khi được yêu cầu lần đầu.
}
~~~

Bean singleton lazy được tạo khi cần, sau đó các lần resolve tiếp theo vẫn dùng cùng instance trong context.

Prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
~~~

Mỗi lần resolve prototype tạo instance mới.

| Thuộc tính | Lazy singleton | Prototype |
|---|---|---|
| Thời điểm tạo | Trì hoãn đến khi cần | Khi mỗi lần resolve |
| Số instance trong context | Một instance cho bean definition | Nhiều instance |
| Resolve lần tiếp theo | Dùng singleton đã tạo | Tạo instance mới |
| Mục đích chính | Trì hoãn khởi tạo | Tạo object riêng theo lần yêu cầu |

`@Lazy` ở injection point có thể tạo một proxy trì hoãn việc resolve dependency. Không nên dùng nó như một cách diễn đạt “mỗi method call cần một prototype mới”. Khi yêu cầu là tạo instance mới theo từng lần thao tác, dùng `ObjectProvider<T>` hoặc factory rõ ràng.

## 19. Singleton bean có thể giữ một prototype provider lâu dài

Một provider được inject vào singleton là dependency ổn định:

~~~java
@Service
public class BatchCoordinator {

    private final ObjectProvider<BatchItemContext> contexts;

    public BatchCoordinator(
            ObjectProvider<BatchItemContext> contexts
    ) {
        this.contexts = contexts;
    }
}
~~~

Provider không phải prototype instance. Nó là một object truy cập bean factory để resolve bean theo scope hiện tại.

Do đó:

~~~java
BatchItemContext first = contexts.getObject();
BatchItemContext second = contexts.getObject();
~~~

Nếu `BatchItemContext` là prototype, hai lần lookup tạo hai object khác nhau. Nếu đổi bean thành singleton, hai lần lookup trả về cùng singleton.

Điều này giúp consumer không cần biết cách container triển khai cache/creation; nó chỉ dùng provider để yêu cầu dependency vào đúng thời điểm.

## 20. Quan sát creation count bằng constructor hoặc counter

Trong môi trường thực hành, có thể ghi số lần constructor được gọi:

~~~java
public class CreationProbe {

    private static final AtomicInteger CREATED =
            new AtomicInteger();

    private final int sequence;

    public CreationProbe() {
        this.sequence = CREATED.incrementAndGet();
    }

    public int sequence() {
        return sequence;
    }

    public static int createdCount() {
        return CREATED.get();
    }

    public static void reset() {
        CREATED.set(0);
    }
}
~~~

Đăng ký prototype:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
CreationProbe creationProbe() {
    return new CreationProbe();
}
~~~

Test:

~~~java
@Test
void createsAPrototypeForEachLookup() {
    CreationProbe.reset();

    try (var context =
            new AnnotationConfigApplicationContext(ProbeConfig.class)) {

        CreationProbe first = context.getBean(CreationProbe.class);
        CreationProbe second = context.getBean(CreationProbe.class);

        assertNotSame(first, second);
        assertEquals(2, CreationProbe.createdCount());
    }
}
~~~

Counter static chỉ phù hợp cho một minh họa test đơn giản. Trong suite chạy song song hoặc nhiều context, static mutable state có thể làm test phụ thuộc nhau. Khi cần quan sát chính xác, nên dùng recorder instance được inject vào bean hoặc reset/isolated context phù hợp.

### 20.1. Identity hash code không phải ID nghiệp vụ

Có thể in:

~~~java
System.out.println(System.identityHashCode(bean));
~~~

Giá trị này hữu ích để quan sát identity trong một lần chạy, nhưng không nên lưu làm ID ổn định hoặc dùng làm bằng chứng duy nhất về uniqueness lâu dài. Hash code có thể trùng giữa hai object.

Để demo rõ hơn, dùng UUID hoặc sequence do test recorder cấp; để kiểm tra cùng object, dùng `assertSame`/`assertNotSame`.

## 21. Kiểm tra singleton/prototype qua nhiều consumer

Tạo hai consumer cùng inject một singleton:

~~~java
@Component
public class CartReaderA {

    private final SharedCart cart;

    public CartReaderA(SharedCart cart) {
        this.cart = cart;
    }

    public SharedCart cart() {
        return cart;
    }
}
~~~

~~~java
@Component
public class CartReaderB {

    private final SharedCart cart;

    public CartReaderB(SharedCart cart) {
        this.cart = cart;
    }

    public SharedCart cart() {
        return cart;
    }
}
~~~

Test:

~~~java
assertSame(
        context.getBean(CartReaderA.class).cart(),
        context.getBean(CartReaderB.class).cart()
);
~~~

Với prototype inject trực tiếp vào hai singleton consumer khác nhau, mỗi consumer có thể nhận một prototype instance khi chính nó được tạo. Nhưng mỗi consumer vẫn giữ instance đã inject.

~~~text
Container
  |
  +-- Create Consumer A
  |       |
  |       +-- resolve Prototype X
  |
  +-- Create Consumer B
          |
          +-- resolve Prototype Y
~~~

Hai consumer khác nhau nhận hai prototype khác nhau, nhưng gọi method nhiều lần trên từng consumer vẫn dùng instance của consumer đó.

Nếu consumer A cần prototype mới mỗi thao tác, A cần provider/factory chứ không phải field prototype inject trực tiếp.

## 22. Scope của dependency lồng nhau

Scope của bean và scope của dependency không tự động đồng nhất.

Ví dụ:

- Singleton `OrderCoordinator` inject prototype `OrderContext`: một prototype được resolve khi coordinator tạo.
- Prototype `OrderWorker` inject singleton `PricingService`: mỗi worker mới vẫn dùng cùng singleton pricing service.
- Prototype `OrderWorker` inject prototype `OrderContext`: khi mỗi worker được tạo, một OrderContext mới được resolve cho worker đó.
- Singleton inject `ObjectProvider<OrderContext>`: mỗi lần provider lookup tạo prototype mới nếu target bean là prototype.

Bảng:

| Consumer | Dependency | Kết quả khi consumer được tạo |
|---|---|---|
| Singleton | Singleton | Dùng instance singleton |
| Singleton | Prototype trực tiếp | Một prototype được inject và giữ lại |
| Prototype | Singleton | Dùng singleton chung |
| Prototype | Prototype trực tiếp | Một prototype mới cho mỗi lần tạo consumer |
| Singleton | `ObjectProvider<Prototype>` | Consumer có thể yêu cầu nhiều prototype trong tương lai |

Quy tắc dễ nhớ: **scope của dependency được áp dụng tại thời điểm container resolve dependency đó**. Nếu dependency được resolve trong constructor, lần resolve đó xảy ra khi consumer được tạo.

## 23. Khi nào nên chọn singleton?

Singleton phù hợp với những object:

- Stateless service.
- Repository hoặc gateway có cấu hình ổn định.
- Validator, mapper, formatter không giữ state theo request.
- Coordinator dùng dependency an toàn khi chia sẻ.
- Cache hoặc registry được thiết kế cho truy cập đồng thời.
- Object khởi tạo tốn kém và có thể chia sẻ an toàn.

Cần cân nhắc khi bean:

- Giữ dữ liệu mutable theo từng user/request.
- Có field thay đổi trong mỗi lần xử lý.
- Giữ resource có vòng đời ngắn.
- Không có concurrency control nhưng được nhiều thread gọi.
- Có trạng thái gắn với một transaction hoặc job riêng.

Một singleton có thể chứa state nếu state đó thực sự là state chia sẻ có chủ đích, được bảo vệ và có lifecycle rõ ràng. Vấn đề không phải “singleton không được có field”, mà là **field có đúng phạm vi chia sẻ và concurrency semantics hay không**.

## 24. Khi nào nên chọn prototype?

Prototype phù hợp khi mỗi lần tạo object cần một state độc lập:

- Context xử lý một job.
- Builder có state riêng cho một thao tác.
- Command object được tạo cho mỗi lần thực thi.
- Object tạm thời chứa dữ liệu của một workflow.
- Một component có tài nguyên riêng và caller chịu trách nhiệm cleanup.
- Một thuật toán cần mutable workspace độc lập.

Prototype không phù hợp chỉ vì muốn “mỗi request có service riêng” mà không có lý do về state/lifecycle. Một service stateless singleton thường đơn giản và hiệu quả hơn.

Ngoài ra, prototype có chi phí tạo object mỗi lần lookup và caller phải quản lý cleanup. Nếu object chỉ là một data holder nhỏ, tạo bằng constructor thuần Java có thể hợp lý hơn việc đăng ký thành Spring bean.

## 25. Không phải object nào cũng cần là Spring bean

Một class có thể được tạo trực tiếp bằng `new` nếu:

- Nó là value object hoặc DTO.
- Nó không cần dependency injection.
- Nó không cần Spring lifecycle callbacks.
- Nó không cần proxy hoặc framework-managed behavior.
- Caller có thể quản lý vòng đời đơn giản.

Ví dụ:

~~~java
public record Money(BigDecimal amount, Currency currency) {
}
~~~

~~~java
public class InvoiceCalculator {

    public Invoice calculate(InvoiceInput input) {
        Money total = new Money(
                input.amount(),
                input.currency()
        );

        return new Invoice(total);
    }
}
~~~

Không cần đăng ký mọi `Money` thành prototype bean. Object có thể được tạo bằng constructor vì nó chỉ là dữ liệu.

Spring bean phù hợp khi container mang lại giá trị như DI, lifecycle, AOP, configuration hoặc scope. **Không biến container thành factory cho mọi object Java nếu không có lợi ích rõ ràng.**

## 26. Chọn scope trong @Component và @Bean

Có thể khai báo scope ở component:

~~~java
@Component
@Scope("prototype")
public class CommandContext {
}
~~~

Hoặc ở factory method:

~~~java
@Configuration(proxyBeanMethods = false)
class CommandConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    CommandContext commandContext() {
        return new CommandContext();
    }
}
~~~

Scope áp dụng cho bean definition được đăng ký từ class hoặc factory method.

Nếu cùng một class được đăng ký thành hai bean definition với scope khác nhau, mỗi definition có thể có behavior riêng:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
CommandContext sharedCommandContext() {
    return new CommandContext();
}

@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
CommandContext newCommandContext() {
    return new CommandContext();
}
~~~

Khi đó lookup theo type `CommandContext.class` có thể mơ hồ. Cần chọn bằng tên hoặc qualifier:

~~~java
context.getBean("newCommandContext", CommandContext.class);
~~~

Không nên tạo nhiều bean cùng type mà không có quy tắc phân biệt nếu consumer cần một candidate duy nhất.

## 27. Phân biệt scope với proxy

Một số scope hoặc dependency resolution có thể dùng proxy để đại diện cho target. Điều này thường thấy ở request/session scope hoặc khi cần inject một dependency có vòng đời ngắn vào singleton.

Proxy và scope là hai khái niệm khác nhau:

- Scope quyết định vòng đời/instance của target.
- Proxy là object trung gian giúp lời gọi được chuyển tới target thích hợp.
- `ObjectProvider` là API để yêu cầu container resolve object theo nhu cầu.
- `@Lookup` là cơ chế method injection để lookup bean khi method được gọi.

Ví dụ scoped proxy có thể giữ một proxy ổn định trong singleton, nhưng target được resolve theo request đang hoạt động. Đó không phải là prototype đơn thuần.

Không nên nhìn thấy một proxy rồi kết luận bean là singleton hoặc prototype chỉ dựa trên class runtime. Khi cần xác định scope, kiểm tra bean definition và hành vi resolve trong context.

## 28. Kiểm thử ObjectProvider mà không mock toàn bộ ApplicationContext

Một cách đơn giản là test qua Spring context thật:

~~~java
@Test
void coordinatorRequestsFreshContexts() {
    try (var context =
            new AnnotationConfigApplicationContext(JobConfiguration.class)) {

        JobCoordinator coordinator =
                context.getBean(JobCoordinator.class);

        JobContext first = coordinator.createContext();
        JobContext second = coordinator.createContext();

        assertNotSame(first, second);
    }
}
~~~

Test này kiểm tra cả wiring của provider và scope prototype.

Nếu muốn unit test logic coordinator độc lập, có thể mock hoặc fake provider:

~~~java
ObjectProvider<JobContext> provider =
        mock(ObjectProvider.class);

JobContext first = new JobContext();
JobContext second = new JobContext();

when(provider.getObject())
        .thenReturn(first, second);

JobCoordinator coordinator = new JobCoordinator(provider);

assertSame(first, coordinator.createContext());
assertSame(second, coordinator.createContext());
verify(provider, times(2)).getObject();
~~~

Ví dụ dùng Mockito, thường có trong `spring-boot-starter-test` theo cấu hình phổ biến. Nó kiểm tra coordinator gọi provider mỗi lần cần context, còn context integration test mới chứng minh Spring thực sự tạo prototype.

Hai cấp test trả lời hai câu hỏi khác nhau.

## 29. Test trường hợp nhiều implementation và provider

Giả sử có nhiều bean `DocumentExporter`. Consumer cần một exporter cụ thể theo cấu hình.

Có thể inject provider với qualifier:

~~~java
@Service
public class PdfJob {

    private final ObjectProvider<DocumentExporter> exporterProvider;

    public PdfJob(
            @Qualifier("pdfExporter")
            ObjectProvider<DocumentExporter> exporterProvider
    ) {
        this.exporterProvider = exporterProvider;
    }

    public void execute(Document document) {
        exporterProvider.getObject().export(document);
    }
}
~~~

Nếu exporter được đăng ký prototype, mỗi lần `execute()` sẽ resolve exporter mới. Nếu exporter singleton, cùng instance được dùng lại.

Nếu lựa chọn định dạng đến từ dữ liệu runtime, một provider cố định với qualifier `pdf` chưa đủ. Khi đó cần registry/factory nhận `ExportFormat` và chọn implementation theo key.

Ví dụ:

~~~java
public interface ExporterFactory {
    DocumentExporter forFormat(ExportFormat format);
}
~~~

Factory có thể giữ map các provider hoặc map các implementation stateless singleton. Cần chọn cách phù hợp với lifecycle của exporter.

## 30. Các lỗi thường gặp khi làm việc với scope

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Prototype được inject vào singleton nhưng không đổi | Prototype chỉ resolve lúc singleton tạo | Inject `ObjectProvider<T>` hoặc factory |
| Hai lần `getBean()` vẫn cùng object | Bean thực tế là singleton | Kiểm tra scope definition và bean name |
| Nhiều bean cùng type gây lỗi | Không có qualifier/primary rõ ràng | Chọn bằng qualifier hoặc registry |
| `@PreDestroy` prototype không chạy | Spring không quản lý destroy đầy đủ cho prototype | Caller cleanup hoặc gọi destruction callback phù hợp |
| State user bị lẫn | Mutable state đặt trong singleton | Stateless service hoặc scope/state boundary phù hợp |
| Prototype object vẫn bị chia sẻ giữa thread | Caller giữ và chia sẻ cùng reference | Quản lý ownership và concurrency |
| `@Lazy` không tạo object mới mỗi lần | Lazy là trì hoãn resolve, không phải prototype factory | Dùng provider |
| `@Lookup` không hoạt động | Bean không do Spring quản lý hoặc method/class không thể override | Kiểm tra subclassing và method visibility |
| `getBean(Type.class)` bị mơ hồ | Có nhiều candidate cùng type | Dùng qualifier hoặc tên |
| Context test không thấy đúng số instance | Test tái sử dụng context hoặc static counter | Kiểm tra scope và cô lập state test |

## 31. Thực hành: quan sát scope bằng một ứng dụng nhỏ

Tạo các class:

- `SessionMarker`: singleton, giữ UUID để nhận diện instance.
- `TaskMarker`: prototype, mỗi instance có UUID riêng.
- `TaskCoordinator`: singleton, inject `ObjectProvider<TaskMarker>`.

`SessionMarker.java`:

~~~java
public class SessionMarker {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

`TaskMarker.java`:

~~~java
public class TaskMarker {

    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
~~~

`TaskCoordinator.java`:

~~~java
public class TaskCoordinator {

    private final ObjectProvider<TaskMarker> taskMarkers;

    public TaskCoordinator(ObjectProvider<TaskMarker> taskMarkers) {
        this.taskMarkers = taskMarkers;
    }

    public TaskMarker newTask() {
        return taskMarkers.getObject();
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class ScopeLabConfiguration {

    @Bean
    SessionMarker sessionMarker() {
        return new SessionMarker();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    TaskMarker taskMarker() {
        return new TaskMarker();
    }

    @Bean
    TaskCoordinator taskCoordinator(
            ObjectProvider<TaskMarker> taskMarkers
    ) {
        return new TaskCoordinator(taskMarkers);
    }
}
~~~

Test:

~~~java
@Test
void observesScopeAndOnDemandLookup() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    ScopeLabConfiguration.class)) {

        SessionMarker firstSession =
                context.getBean(SessionMarker.class);
        SessionMarker secondSession =
                context.getBean(SessionMarker.class);

        TaskCoordinator coordinator =
                context.getBean(TaskCoordinator.class);

        TaskMarker firstTask = coordinator.newTask();
        TaskMarker secondTask = coordinator.newTask();

        assertSame(firstSession, secondSession);
        assertNotSame(firstTask, secondTask);

        assertTrue(context.isSingleton("sessionMarker"));
        assertTrue(context.isPrototype("taskMarker"));
    }
}
~~~

Sau khi chạy test, hãy giải thích:

1. Vì sao hai session marker là cùng object?
2. Vì sao hai task marker khác object?
3. Vì sao `TaskCoordinator` vẫn chỉ có một instance?
4. `ObjectProvider` có phải prototype bean không?
5. Nếu bỏ provider và inject `TaskMarker` trực tiếp, điều gì thay đổi?
6. Ai phải cleanup một `TaskMarker` nếu nó giữ file hoặc socket?

Bài tập cho thấy scope của coordinator độc lập với scope của dependency mà nó resolve theo nhu cầu.

## 32. Một lưu ý về parent và child ApplicationContext

Trong một số ứng dụng, Spring có parent context và child context. Mỗi container quản lý singleton của bean definition thuộc phạm vi của nó.

Một bean ở parent có thể được child context nhìn thấy thông qua cơ chế phân cấp. Việc child nhìn thấy bean parent không có nghĩa child tạo một singleton copy khác của bean đó.

Nếu cùng một cấu hình được đăng ký riêng trong cả parent và child, hai bean definition ở hai container có thể có hai instance riêng.

Điều này ít gặp trong một Spring Boot application đơn giản, nhưng quan trọng khi làm việc với ứng dụng web nhiều context hoặc test tạo context riêng.

## 33. Checklist lựa chọn scope và lookup

Trước khi chọn singleton, prototype hoặc provider, hãy tự hỏi:

- Bean có giữ state mutable không?
- State đó thuộc về toàn ứng dụng, một job hay một request?
- Có nhiều thread gọi cùng bean không?
- Bean cần một instance dùng chung hay một instance mới mỗi lần xử lý?
- Caller có thể tự tạo object bằng constructor thay vì đăng ký Spring bean không?
- Nếu là prototype, ai chịu trách nhiệm cleanup?
- Singleton có inject prototype trực tiếp không?
- Có cần `ObjectProvider`, `Provider`, factory hay `@Lookup`?
- Có nhiều candidate cùng type không?
- Qualifier/bean name đã thể hiện lựa chọn rõ chưa?
- `@Lazy` đang được dùng để trì hoãn tạo bean hay bị nhầm là tạo instance mới?
- Test có xác nhận identity bằng `assertSame`/`assertNotSame` không?
- Test có vô tình phụ thuộc static state hoặc context cache không?

Một quyết định scope tốt bắt đầu từ **vòng đời và quyền sở hữu state**, sau đó mới chọn annotation hoặc API lookup.

## Kết luận

Spring scope xác định cách container tạo và chia sẻ instance. **Singleton** cung cấp một instance cho mỗi bean definition trong một ApplicationContext; **prototype** tạo instance mới mỗi lần container resolve bean.

Điểm dễ nhầm nhất là prototype được inject trực tiếp vào singleton: Spring chỉ resolve prototype một lần khi singleton được tạo, nên consumer giữ cùng reference. Nếu cần một prototype mới theo từng thao tác, hãy dùng `ObjectProvider<T>`, `Provider<T>`, factory hoặc `@Lookup` phù hợp.

Khi thực hành:

- Dùng `assertSame` để quan sát singleton và `assertNotSame` để quan sát prototype.
- Dùng `context.isSingleton()` và `context.isPrototype()` để hỏi container về scope.
- Nhớ singleton được giới hạn theo ApplicationContext, không phải toàn JVM.
- Thiết kế singleton stateless hoặc bảo vệ state mutable khi có truy cập đồng thời.
- Nhớ Spring không tự gọi destroy callbacks cho mọi prototype instance; caller chịu trách nhiệm cleanup.
- Chọn provider hoặc factory khi cần resolve bean theo nhu cầu.
- Không đăng ký mọi object Java thành Spring bean nếu constructor thông thường đã đủ.

Hiểu rõ scope giúp ứng dụng quản lý state, dependency và tài nguyên đúng vòng đời, đồng thời làm cho hành vi của container có thể quan sát và kiểm thử được.
