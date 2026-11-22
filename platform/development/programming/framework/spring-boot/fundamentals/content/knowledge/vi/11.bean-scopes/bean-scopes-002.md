# Prototype và thời điểm một instance mới được tạo

Trong Spring, **scope** xác định cách container quản lý instance của một bean. Scope mặc định là `singleton`: trong một `ApplicationContext`, một bean definition thường được gắn với một instance dùng chung. Với scope `prototype`, Spring tạo một instance mới mỗi khi container cần phân giải bean đó.

Điều cần hiểu chính xác là: “mỗi lần tạo mới” được tính theo **lần yêu cầu bean từ container**, chẳng hạn một lời gọi `getBean()` hoặc một lần Spring phân giải dependency khi tạo bean khác. Nó không có nghĩa là mỗi lần gọi một phương thức trên object, mỗi HTTP request hay mỗi thread đều tự động nhận một instance mới.

Sự khác biệt này đặc biệt quan trọng khi inject một prototype bean vào một singleton service. Nếu inject trực tiếp, singleton thường chỉ nhận **một instance prototype tại thời điểm chính nó được tạo**. Muốn lấy instance mới ở từng thao tác, cần yêu cầu container tra cứu lại, thường thông qua `ObjectProvider<T>`.

## 1. Scope prototype là gì?

Một bean prototype là bean có scope được khai báo bằng `prototype`. Ví dụ:

~~~java
package com.example.jobs;

import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class JobContext {
    private final String id = java.util.UUID.randomUUID().toString();

    public String getId() {
        return id;
    }
}
~~~

Khi Spring phát hiện class này qua component scanning, container đăng ký bean definition có scope prototype. Mỗi lần yêu cầu `JobContext` từ container, Spring tạo và trả về một object mới:

~~~java
JobContext first = applicationContext.getBean(JobContext.class);
JobContext second = applicationContext.getBean(JobContext.class);

System.out.println(first == second); // false
System.out.println(first.getId());
System.out.println(second.getId());
~~~

Hai biến tham chiếu đến hai instance khác nhau. Mỗi object giữ trạng thái riêng, ví dụ giá trị `id` được tạo trong constructor/field initializer.

Có thể dùng hằng số scope thay vì chuỗi:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
~~~

`ConfigurableBeanFactory.SCOPE_PROTOTYPE` có giá trị `"prototype"`. Dùng hằng số giúp giảm lỗi gõ sai tên scope.

## 2. So sánh singleton và prototype

| Đặc điểm | Singleton | Prototype |
|---|---|---|
| Scope mặc định? | Có | Không |
| Instance được tạo | Thường một instance cho bean definition trong một container | Mỗi lần container phân giải bean lại tạo instance mới |
| Thời điểm thường gặp | Khi context khởi tạo (nếu không lazy), hoặc lần đầu được yêu cầu | Khi được yêu cầu |
| Container giữ instance để tái sử dụng? | Có | Không quản lý một instance dùng chung để trả lại ở lần tiếp theo |
| Trạng thái giữa các lần lấy bean | Dùng chung instance | Instance mới có trạng thái riêng |
| Phù hợp với | Service stateless, repository, cấu hình dùng chung | Object giữ trạng thái cho một tác vụ, builder hoặc context ngắn hạn |
| Hủy tài nguyên | Container quản lý destruction callbacks khi context đóng | Container không tự gọi destruction callbacks cho prototype sau khi giao object cho client |

Singleton ở đây là singleton **trong một bean factory/application context**, không phải một object toàn cục cho cả JVM. Hai application context độc lập có thể có hai singleton instance cho cùng một bean definition.

Prototype cũng không đồng nghĩa với “mỗi request HTTP một object”. Nếu muốn một instance gắn với vòng đời HTTP request, Spring có scope riêng là `request`; nếu muốn theo phiên người dùng, có scope `session` trong web application phù hợp.

## 3. Khi nào Spring tạo prototype instance mới?

Quy tắc thực tế là Spring tạo prototype khi có một **lần phân giải bean** cần một instance của bean definition đó.

### 3.1. Mỗi lần gọi getBean()

Đây là trường hợp dễ quan sát nhất:

~~~java
JobContext first = context.getBean(JobContext.class);
JobContext second = context.getBean(JobContext.class);
JobContext third = context.getBean(JobContext.class);
~~~

Kết quả là ba instance khác nhau nếu cả ba lần gọi đều được thực hiện với cùng bean definition prototype và không có lớp wrapper/cache riêng giữ lại kết quả.

Lưu ý, nếu code chỉ gọi một lần:

~~~java
JobContext contextForJob = context.getBean(JobContext.class);
contextForJob.runStepOne();
contextForJob.runStepTwo();
~~~

thì hai lời gọi phương thức dùng **cùng object**. Scope prototype không tạo instance mới cho mỗi phương thức.

### 3.2. Khi Spring inject prototype vào một bean khác

Giả sử một bean cần `JobContext`:

~~~java
@Component
public class JobRunner {
    private final JobContext jobContext;

    public JobRunner(JobContext jobContext) {
        this.jobContext = jobContext;
    }

    public void run() {
        jobContext.run();
    }
}
~~~

Nếu `JobRunner` là singleton (mặc định), Spring tạo `JobRunner` khi khởi tạo context hoặc khi bean được yêu cầu. Trong lúc tạo `JobRunner`, Spring phân giải dependency `JobContext` và tạo một prototype instance để truyền vào constructor.

Sau đó `JobRunner` giữ reference đó. Khi gọi `run()` nhiều lần, code vẫn dùng cùng `jobContext`. Spring không tự quay lại container mỗi lần phương thức `run()` chạy.

~~~text
ApplicationContext khởi tạo JobRunner (singleton)
                |
                v
     Cần dependency JobContext
                |
                v
     Spring tạo prototype instance #1
                |
                v
     Inject vào constructor JobRunner
                |
                v
       JobRunner giữ reference #1
                |
          run() nhiều lần
                |
                v
       Vẫn sử dụng instance #1
~~~

Đây là điểm thường gây hiểu nhầm nhất: **prototype scope không tự biến một dependency đã inject thành dependency mới mỗi lần sử dụng**.

### 3.3. Prototype được inject vào một prototype khác

Nếu bean cha cũng là prototype, mỗi lần Spring tạo bean cha, container lại phân giải dependency của nó:

~~~java
@Component
@Scope("prototype")
class JobContext {
}

@Component
@Scope("prototype")
class JobRunner {
    private final JobContext context;

    JobRunner(JobContext context) {
        this.context = context;
    }
}
~~~

Mỗi lần gọi `context.getBean(JobRunner.class)`, Spring tạo một `JobRunner` mới và phân giải một `JobContext` mới cho lần tạo đó. Vì vậy, các cặp runner/context của những lần yêu cầu khác nhau có instance riêng.

Nếu dependency của prototype là singleton, Spring vẫn inject singleton dùng chung. Scope của bean cha không tự thay đổi scope của các dependency mà nó tham chiếu.

## 4. Khai báo prototype bằng @Scope

Có hai cách phổ biến để đăng ký prototype bean.

### 4.1. Dùng component scanning

~~~java
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class ShoppingCart {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    public void add(String item) {
        items.add(item);
    }

    public java.util.List<String> items() {
        return java.util.List.copyOf(items);
    }
}
~~~

Spring phát hiện class nhờ `@Component` và đăng ký bean definition với scope prototype nhờ `@Scope`.

### 4.2. Dùng phương thức @Bean

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

@Configuration
public class JobConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    JobContext jobContext() {
        return new JobContext();
    }
}
~~~

Tên bean mặc định trong ví dụ là `jobContext`, theo tên phương thức factory. Scope prototype được áp dụng cho bean definition do phương thức đó khai báo.

Khi một phương thức `@Bean` khác cần `JobContext`, nên khai báo dependency qua tham số:

~~~java
@Bean
JobRunner jobRunner(JobContext jobContext) {
    return new JobRunner(jobContext);
}
~~~

Spring sẽ phân giải tham số theo bean definition và scope tương ứng. Không nên tùy tiện gọi trực tiếp phương thức factory như một phương thức Java để mong mọi kiểu cấu hình đều có cùng semantics: với `@Configuration(proxyBeanMethods = false)`, lời gọi trực tiếp là lời gọi Java thông thường. Dùng tham số method injection giúp ý định phụ thuộc rõ ràng.

## 5. Cách lấy một prototype mới trong singleton: ObjectProvider

Nếu một singleton cần một prototype instance mới cho mỗi lần thực hiện tác vụ, hãy inject `ObjectProvider<T>` thay vì inject trực tiếp `T`.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class JobCoordinator {
    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void executeJob(String jobName) {
        JobContext context = contexts.getObject();
        context.start(jobName);
        context.run();
    }
}
~~~

Mỗi lần gọi `executeJob`, code gọi `getObject()` và yêu cầu container phân giải `JobContext`. Vì bean đích có scope prototype, mỗi lần phân giải sẽ tạo một instance mới.

~~~text
JobCoordinator (singleton)
        |
        +--- executeJob("A")
        |          |
        |          +--> contexts.getObject()
        |                    |
        |                    +--> JobContext #1
        |
        +--- executeJob("B")
                   |
                   +--> contexts.getObject()
                             |
                             +--> JobContext #2
~~~

`ObjectProvider` là handle tra cứu bean do Spring cung cấp. Nó không giữ sẵn một prototype instance duy nhất; mỗi lần gọi phương thức tra cứu sẽ yêu cầu bean factory phân giải dependency theo scope hiện hành.

### 5.1. Chọn API phù hợp

| API | Khi không có bean phù hợp | Mục đích |
|---|---|---|
| `getObject()` | Ném lỗi | Bean là bắt buộc |
| `getIfAvailable()` | Trả `null` | Bean là tùy chọn |
| `getIfUnique()` | Trả `null` nếu không có ứng viên duy nhất | Chỉ dùng khi lựa chọn rõ ràng |
| `stream()` | Stream rỗng nếu không có ứng viên | Duyệt các bean phù hợp |
| `orderedStream()` | Stream rỗng nếu không có ứng viên | Duyệt theo thứ tự của Spring |

Với một prototype dependency bắt buộc, `getObject()` thường là lựa chọn dễ hiểu nhất. Nếu dùng `getIfAvailable()`, hãy định nghĩa rõ ứng dụng sẽ làm gì khi bean không tồn tại. Nếu có nhiều implementation cùng kiểu, có thể dùng qualifier hoặc duyệt stream thay vì mong `getObject()` chọn tùy ý.

## 6. Một cách khác: method injection với @Lookup

Spring hỗ trợ `@Lookup` để container override một method và thực hiện tra cứu bean khi method được gọi. Cách này có thể dùng khi singleton muốn lấy prototype mới mà không giữ trực tiếp `ObjectProvider`.

~~~java
import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.stereotype.Component;

@Component
public class LookupJobCoordinator {

    public void execute(String jobName) {
        JobContext context = newJobContext();
        context.start(jobName);
        context.run();
    }

    @Lookup
    protected JobContext newJobContext() {
        // Spring sẽ override method này khi tạo bean.
        return null;
    }
}
~~~

Spring tạo subclass runtime cho bean chứa lookup method và thay implementation của method để tra cứu bean đích. Mỗi lần gọi `newJobContext()` sẽ phân giải `JobContext`; nếu target là prototype, mỗi lần gọi nhận instance mới.

Một số điều kiện và giới hạn cần nhớ:

- Bean chứa lookup method phải được tạo và quản lý bởi Spring container.
- Spring cần khả năng override method; class/method không được là `final`, method không thể là `private` hoặc `static`.
- Cơ chế subclassing có giới hạn với các class/factory setup không thể được Spring subclass theo cách cần thiết.
- Không nên tự khởi tạo bean chứa `@Lookup` bằng `new`, vì object đó không phải instance được container tạo và method sẽ không được override.

`@Lookup` hữu ích trong một số tình huống, nhưng `ObjectProvider` thường dễ nhìn thấy dependency hơn trong constructor và thuận tiện cho kiểm thử. Khi thiết kế service, ưu tiên cách thể hiện rõ dependency mà team có thể đọc và kiểm soát.

## 7. Vòng đời của prototype bean

Prototype không có nghĩa Spring bỏ qua toàn bộ lifecycle. Mỗi lần tạo instance, container vẫn có thể thực hiện các bước quản lý bean thông thường:

~~~text
Yêu cầu prototype bean
        |
        v
Tạo instance
        |
        v
Inject dependency / populate properties
        |
        v
Aware callbacks (nếu có)
        |
        v
BeanPostProcessor trước initialization
        |
        v
Initialization callbacks
(@PostConstruct, InitializingBean, initMethod...)
        |
        v
BeanPostProcessor sau initialization
        |
        v
Trả instance cho nơi yêu cầu
        |
        v
Client sử dụng và chịu trách nhiệm vòng đời sau đó
~~~

Sơ đồ là mô tả khái quát thứ tự các giai đoạn; chi tiết phụ thuộc các callback và processor mà ứng dụng đăng ký.

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class TemporaryWorkspace {

    @PostConstruct
    void initialize() {
        System.out.println("Prepare workspace");
    }

    @PreDestroy
    void cleanup() {
        System.out.println("Release workspace");
    }
}
~~~

Mỗi lần Spring tạo `TemporaryWorkspace`, callback khởi tạo như `@PostConstruct` vẫn được thực hiện. Nhưng có một khác biệt quan trọng:

**Spring không tự gọi destruction callbacks cho prototype bean sau khi đã giao instance cho client.** Vì container không giữ danh sách các prototype instance để quản lý việc đóng tất cả chúng khi context dừng, `@PreDestroy` trong ví dụ không tự được gọi chỉ vì ứng dụng kết thúc.

Nếu prototype sở hữu tài nguyên như file handle, socket, temporary directory hoặc executor, nơi yêu cầu instance phải có kế hoạch giải phóng tài nguyên. Có thể để object triển khai `AutoCloseable` và gọi `close()` khi hoàn tất; trong trường hợp cần Spring chạy destruction processing, `AutowireCapableBeanFactory` cung cấp API `destroyBean(Object)` cho instance do ứng dụng đang quản lý.

Ví dụ với try/finally:

~~~java
TemporaryWorkspace workspace = workspaces.getObject();
try {
    workspace.performTask();
} finally {
    workspace.close();
}
~~~

Đoạn code giả định `TemporaryWorkspace` triển khai `AutoCloseable`. Nếu cần các callback hủy do Spring quản lý, hãy dùng đúng cơ chế hủy tương ứng thay vì giả định `@PreDestroy` tự chạy.

## 8. Prototype có thread-safe không?

Prototype thường hữu ích cho object có trạng thái riêng của một lần xử lý. Tuy nhiên, **scope prototype không phải cam kết thread safety**.

Khi Spring trả hai instance khác nhau:

~~~java
JobContext first = contexts.getObject();
JobContext second = contexts.getObject();
~~~

hai object không dùng chung trạng thái instance thông thường. Nhưng nếu:

- code chia sẻ cùng reference `first` cho nhiều thread,
- object chứa static mutable state,
- hai instance cùng thao tác lên một tài nguyên bên ngoài,
- hoặc dependency singleton bên trong prototype không thread-safe,

thì vẫn có thể xảy ra race condition.

Prototype chỉ xác định cách container tạo và trả object. Nó không tự:

- tạo một thread mới,
- khóa các thao tác,
- cô lập database transaction,
- tạo một instance riêng cho mỗi HTTP request,
- hoặc quản lý tài nguyên dùng chung.

Nếu cần một object riêng cho mỗi request HTTP, xem xét `@RequestScope`. Nếu cần một object riêng cho mỗi lần xử lý job, dùng provider để yêu cầu prototype ở đầu mỗi job thường thể hiện ý định rõ hơn.

## 9. Prototype và các scope khác

| Scope | Phạm vi instance | Thời điểm thường được tạo |
|---|---|---|
| `singleton` | Một instance cho bean definition trong một container | Khi context khởi tạo hoặc lần đầu được yêu cầu nếu lazy |
| `prototype` | Một instance cho mỗi lần bean được yêu cầu/phân giải | Khi có yêu cầu |
| `request` | Một instance trong vòng đời HTTP request | Khi request scope được truy cập |
| `session` | Một instance trong vòng đời HTTP session | Khi session scope được truy cập |
| `application` | Một instance trong phạm vi ServletContext | Khi application scope được truy cập |
| `websocket` | Một instance trong vòng đời WebSocket session | Khi WebSocket scope được truy cập |

Các web scope chỉ khả dụng trong môi trường web tương ứng và cần scope context đang hoạt động. Prototype là scope cơ bản, không phụ thuộc HTTP.

### Prototype không phải request scope

Một request HTTP có thể gọi `getObject()` nhiều lần và nhận nhiều prototype instance trong cùng request. Ngược lại, nếu request-scoped bean được phân giải trong cùng request, các lần truy cập hợp lệ sẽ tham chiếu tới instance gắn với request đó.

Ví dụ:

~~~java
@Component
@Scope("prototype")
class RequestWorkBuffer {
}
~~~

Controller gọi provider hai lần:

~~~java
RequestWorkBuffer a = buffers.getObject();
RequestWorkBuffer b = buffers.getObject();
~~~

`a` và `b` là hai prototype instance khác nhau dù cùng nằm trong một HTTP request. Vì vậy, đừng chọn prototype chỉ vì muốn “mỗi request một object”.

## 10. Kiểm chứng thời điểm tạo instance

Có thể kiểm chứng bằng identity trong một Spring test:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotSame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class PrototypeScopeTest {

    @Autowired
    ApplicationContext context;

    @Test
    void eachLookupReturnsANewInstance() {
        JobContext first = context.getBean(JobContext.class);
        JobContext second = context.getBean(JobContext.class);

        assertNotSame(first, second);
    }
}
~~~

Test giả định `JobContext` đã được đăng ký trong application context với scope prototype.

Để kiểm tra hành vi khi inject vào singleton, có thể tạo một facade nhận provider:

~~~java
@Component
class JobFacade {
    private final ObjectProvider<JobContext> contexts;

    JobFacade(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    JobContext newContext() {
        return contexts.getObject();
    }
}
~~~

~~~java
@SpringBootTest
class JobFacadeTest {
    @Autowired
    JobFacade facade;

    @Test
    void providerResolvesAPrototypeForEachCall() {
        JobContext first = facade.newContext();
        JobContext second = facade.newContext();

        assertNotSame(first, second);
    }
}
~~~

Có thể bổ sung test đối chứng với constructor injection trực tiếp: lấy singleton facade hai lần vẫn là cùng singleton, và field prototype đã inject trong facade vẫn là cùng reference. Đối chứng này giúp làm rõ khác biệt giữa **tạo mới khi container phân giải dependency** và **yêu cầu lại bean ở từng lần thao tác**.

## 11. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Hành vi thực tế |
|---|---|
| “Prototype nghĩa là mỗi lần gọi method sẽ có object mới.” | Instance mới chỉ xuất hiện khi container phân giải bean lại; method call trên reference cũ vẫn dùng object cũ. |
| “Inject prototype vào singleton thì mỗi lần singleton dùng sẽ nhận prototype mới.” | Dependency được phân giải khi tạo singleton; singleton giữ instance đã inject. |
| “Prototype tự hủy khi dùng xong.” | Spring không tự chạy destruction callbacks cho prototype sau khi giao instance; client chịu trách nhiệm giải phóng tài nguyên. |
| “Prototype luôn thread-safe.” | Scope không cung cấp đồng bộ hóa; code và dependency vẫn cần thiết kế an toàn luồng. |
| “Prototype tương đương request scope.” | Một request có thể yêu cầu nhiều prototype instance; request scope gắn instance với vòng đời request. |
| “Dùng ObjectProvider là Spring tạo một object mới.” | Provider chỉ yêu cầu container phân giải; scope của bean đích quyết định instance có mới hay không. |
| “Mọi dependency bên trong prototype cũng tự động prototype.” | Mỗi dependency tuân theo scope riêng; singleton dependency vẫn dùng chung. |

## 12. Khi nào nên dùng prototype?

Prototype hợp lý khi ứng dụng cần object có trạng thái riêng cho từng thao tác, ví dụ:

- `JobContext` chứa tiến trình, kết quả và metadata của một job.
- `ShoppingCartDraft` dùng để dựng một phiên tính toán độc lập trong một tác vụ.
- `ReportBuilder` tích lũy dữ liệu để tạo một báo cáo.
- `CommandContext` chứa trạng thái tạm thời của một lần thực thi command.
- `TemporaryWorkspace` quản lý tài nguyên tạm trong một thao tác và được giải phóng rõ ràng sau đó.

Không cần chuyển mọi service sang prototype. Các service nghiệp vụ stateless, repository và thành phần cấu hình thường phù hợp với singleton. Prototype có chi phí tạo object lặp lại và yêu cầu nơi sử dụng quản lý vòng đời tài nguyên nếu có.

Nếu mục tiêu là tạo một object Java đơn giản không cần Spring injection, lifecycle hoặc cấu hình, dùng constructor/factory Java thông thường có thể rõ ràng hơn. Scope prototype hữu ích khi cần **Spring container tạo instance mới nhưng vẫn áp dụng dependency injection và bean initialization** cho từng instance.

## 13. Quy trình quyết định và áp dụng

Khi thiết kế một bean có trạng thái, hãy xác định:

1. **Ai sở hữu trạng thái?** Nếu trạng thái dùng chung toàn ứng dụng và bean an toàn khi dùng đồng thời, singleton có thể phù hợp. Nếu trạng thái chỉ thuộc một lần xử lý, prototype là một lựa chọn.
2. **Khi nào cần instance?** Nếu cần ngay khi tạo bean cha, có thể inject trực tiếp. Nếu cần ở từng lần thực hiện thao tác, inject `ObjectProvider<T>` và gọi `getObject()` tại điểm bắt đầu thao tác.
3. **Ai giải phóng tài nguyên?** Prototype không được container tự động gọi destruction callback; xác định nơi gọi `close()` hoặc cơ chế hủy phù hợp.
4. **Có nhiều implementation không?** Dùng qualifier để thu hẹp ứng viên hoặc stream để chọn theo quy tắc nghiệp vụ.
5. **Scope có đúng với vòng đời thực tế?** Phân biệt prototype với request/session scope và không dựa vào scope để giải quyết thread safety.
6. **Kiểm thử thời điểm tạo mới.** Dùng `assertNotSame` cho hai lần lookup và kiểm tra trường hợp singleton inject trực tiếp so với singleton sử dụng provider.

Prototype có nghĩa là **một lần phân giải bean từ container tạo một instance mới**. Sau khi object được trả về, ứng dụng sử dụng chính instance đó cho đến khi không còn cần nó. Nếu một singleton cần instance mới cho từng công việc, nó phải yêu cầu container phân giải lại bằng `ObjectProvider` hoặc một cơ chế lookup tương đương. Hiểu đúng ranh giới này giúp lựa chọn scope phù hợp và tránh kỳ vọng sai về thời điểm tạo object, trạng thái và vòng đời bean.
