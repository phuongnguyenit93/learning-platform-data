# SimpleThreadScope trong Spring: đăng ký, cách hoạt động và giới hạn giải phóng tài nguyên

## 1. Mục tiêu và phạm vi

`SimpleThreadScope` là một cài đặt của giao diện `org.springframework.beans.factory.config.Scope`, nằm trong `org.springframework.context.support`. Nó giữ **một instance của mỗi bean name cho mỗi Java thread** trong phạm vi một đối tượng scope được đăng ký với BeanFactory. Khi cùng thread hỏi lại bean cùng tên, Spring trả về instance đã lưu; khi thread khác hỏi, scope tạo hoặc lấy instance riêng của thread đó.

Bài học này tập trung vào: cách đăng ký vì scope **không có sẵn mặc định**, cách `ThreadLocal` chi phối vòng đời, hành vi trong thread pool và `@Async`, giới hạn nghiêm trọng về destruction callback, cách chủ động cleanup và cách chọn giải pháp thay thế.

> Cần phân biệt: **thread-bound** nghĩa là gắn với danh tính thread đang thực thi; không có nghĩa là một HTTP request, một job nghiệp vụ, một transaction hoặc một tác vụ bất đồng bộ sẽ tự động có một scope riêng.

## 2. Cơ chế lưu bean theo thread

Có thể hình dung nội bộ `SimpleThreadScope` như sau (mã giả, không phải source đầy đủ):

```java
// Mỗi SimpleThreadScope có một ThreadLocal chứa Map theo bean name.
private final ThreadLocal<Map<String, Object>> storage =
        ThreadLocal.withInitial(HashMap::new);

Object get(String beanName, ObjectFactory<?> factory) {
    Map<String, Object> beansOfCurrentThread = storage.get();
    Object bean = beansOfCurrentThread.get(beanName);
    if (bean == null) {
        bean = factory.getObject();
        beansOfCurrentThread.put(beanName, bean);
    }
    return bean;
}
```

- **Cùng thread + cùng bean name:** nhận lại cùng đối tượng cho đến khi bean bị xóa khỏi map của thread đó.
- **Hai thread khác nhau:** có hai map riêng; lần truy cập đầu tiên của mỗi thread thường tạo hai bean khác nhau.
- **Hai bean name trong cùng thread:** có hai phần tử độc lập, dù chúng cùng Java class.
- **Hai Spring context:** không mặc nhiên chia sẻ bean thread-scope vì mỗi context/đăng ký scope có vòng đời và kho lưu riêng.
- **Thread kết thúc:** dữ liệu thread-local có thể được GC khi không còn tham chiếu, nhưng đó **không phải** một sự kiện Spring chạy `destroy()` hoặc `@PreDestroy`.

Ví dụ với bean `workState`: main thread có thể giữ `workState#1`; worker thread có thể giữ `workState#2`. Khi thread pool chạy hai tác vụ liên tiếp trên **cùng worker**, cả hai có thể gặp `workState#2`, dù chúng là hai yêu cầu nghiệp vụ khác nhau.

`getConversationId()` của `SimpleThreadScope` trả về **tên thread hiện tại**, hữu ích để chẩn đoán nhưng không phải ID duy nhất toàn hệ thống: hai thread có thể trùng tên.

## 3. Đăng ký bắt buộc trước khi sử dụng

`SimpleThreadScope` **không được tự đăng ký** dưới key `"thread"` trong những Spring ApplicationContext thông dụng. Khai báo `@Scope("thread")` thôi chưa đủ. Nếu bean được tạo/truy cập khi key chưa tồn tại, Spring có thể ném `IllegalStateException` vì không có scope `thread` được đăng ký.

**Cách A – đăng ký trực tiếp** với `ConfigurableBeanFactory` trước khi refresh/tạo bean theo scope:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.getBeanFactory().registerScope("thread", new SimpleThreadScope());
context.register(AppConfig.class);
context.refresh();
```

Đây là phần minh họa; ví dụ chạy hoàn chỉnh ở mục 5. Trong tình huống khác, có thể dùng `ConfigurableBeanFactory.registerScope(String, Scope)` trên factory **đúng của context**. Key `"thread"` do ứng dụng tự chọn nhưng phải khớp chính xác với `@Scope("thread")`; không nên đặt trùng các tên built-in như `singleton`, `prototype`.

**Cách B – khai báo `CustomScopeConfigurer`** dưới dạng `BeanFactoryPostProcessor`:

```java
import org.springframework.beans.factory.config.CustomScopeConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.SimpleThreadScope;

@Configuration(proxyBeanMethods = false)
class ThreadScopeRegistration {
    @Bean
    static CustomScopeConfigurer threadScopeConfigurer() {
        CustomScopeConfigurer configurer = new CustomScopeConfigurer();
        configurer.addScope("thread", new SimpleThreadScope());
        return configurer;
    }
}
```

Class cấu hình trên là một **mảnh tích hợp**, cần được Spring quét hoặc `@Import` vào ứng dụng. Phương thức `@Bean static` giúp đăng ký processor ở giai đoạn sớm, trước khi tạo các bean thông thường. Một ứng dụng chỉ cần **một cách đăng ký có chủ đích** cho cùng key trong cùng BeanFactory; đừng vô tình ghi đè đăng ký scope hiện có.

Khai báo bean sử dụng scope:

```java
@Bean
@Scope("thread")
WorkerState workerState() {
    return new WorkerState();
}
```

Đoạn vừa rồi cũng là **mảnh minh họa** (giả định đã có lớp `WorkerState` và các import liên quan).

## 4. Scope của bean khác với scope của nơi sử dụng bean

Giả sử một singleton inject trực tiếp một bean `thread` trong lúc singleton được xây dựng:

```java
@Service
class ReportService {
    private final WorkerState workerState;

    ReportService(WorkerState workerState) {
        this.workerState = workerState;
    }
}
```

Nếu không có scoped proxy hoặc cơ chế truy xuất lười, đối tượng `workerState` có thể được lấy đúng **một lần lúc tạo singleton**, rồi chính tham chiếu đó được singleton giữ và sử dụng từ nhiều thread. Điều này phá vỡ ý định "mỗi thread một instance".

Hai cách xử lý:

**Dùng scoped proxy** để proxy singleton giải quyết target theo thread tại **mỗi lần gọi method**:

```java
@Bean
@Scope(value = "thread", proxyMode = ScopedProxyMode.TARGET_CLASS)
WorkerState workerState() {
    return new WorkerState();
}
```

`ScopedProxyMode.TARGET_CLASS` cần target thích hợp để tạo class-based proxy (chú ý class/method `final`). Với interface, có thể cân nhắc `ScopedProxyMode.INTERFACES`. Proxy không thay đổi ranh giới thread: gọi từ thread khác sẽ giải quyết target của thread đó, **không tự mang instance của thread cũ sang**.

**Dùng `ObjectProvider<WorkerState>`**, rồi gọi `getObject()` đúng thời điểm thực thi:

```java
@Service
class ReportService {
    private final ObjectProvider<WorkerState> states;

    ReportService(ObjectProvider<WorkerState> states) {
        this.states = states;
    }

    void execute() {
        WorkerState state = states.getObject();
        // Dùng state trong thread hiện tại.
    }
}
```

Các mảnh ví dụ ở mục này cần ghép với định nghĩa bean/import tương ứng; chúng minh họa vấn đề injection chứ không phải các chương trình độc lập.

## 5. Ví dụ Java 17+ chạy được

Dự án Gradle tối thiểu (JDK 17+, Gradle 8+) có hai tệp:

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
    mainClass = 'ThreadScopeDemo'
}
```

`src/main/java/ThreadScopeDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.context.support.SimpleThreadScope;

public class ThreadScopeDemo {
    static class WorkState implements DisposableBean {
        private static final AtomicInteger NEXT = new AtomicInteger();
        final int id = NEXT.incrementAndGet();

        @Override
        public void destroy() {
            System.out.println("destroy " + id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        @Scope("thread")
        WorkState workState() {
            return new WorkState();
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Đăng ký scope trước khi context.refresh().
            context.getBeanFactory()
                    .registerScope("thread", new SimpleThreadScope());
            context.register(AppConfig.class);
            context.refresh();

            WorkState main1 = context.getBean(WorkState.class);
            WorkState main2 = context.getBean(WorkState.class);

            ExecutorService pool = Executors.newSingleThreadExecutor(
                    task -> new Thread(task, "demo-worker"));
            try {
                int workerId1 = pool.submit(
                        () -> context.getBean(WorkState.class).id).get();
                int workerId2 = pool.submit(
                        () -> context.getBean(WorkState.class).id).get();

                System.out.println("mainSame=" + (main1 == main2));
                System.out.println("mainId=" + main1.id);
                System.out.println("workerIds="
                        + workerId1 + "," + workerId2);
                System.out.println("mainDiffWorker="
                        + (main1.id != workerId1));
            } finally {
                pool.shutdown();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }
    }
}
```

Chạy từ thư mục dự án:

```bash
gradle run --quiet
# Hoặc ./gradlew run --quiet nếu dự án đã có Gradle Wrapper.
```

**Các dòng do chương trình in ra qua `System.out`**:

```text
mainSame=true
mainId=1
workerIds=2,2
mainDiffWorker=true
```

Giải thích:

1. Hai lần `getBean` trên main thread trả về đúng một `WorkState#1`.
2. Executor có **một worker cố định**: hai task chạy nối tiếp lấy chung `WorkState#2`.
3. Main thread và worker thread có bean riêng.
4. Không có dòng `destroy 1` hoặc `destroy 2` dù đã `shutdown` executor và đóng Spring context. Đây là giới hạn quan trọng: các callback hủy của bean theo `SimpleThreadScope` **không được thực thi tự động**. Tùy cấu hình logging, Spring có thể thêm cảnh báo về callback không được hỗ trợ vào log; chúng không thuộc bốn dòng `System.out` nêu trên.

`WorkState implements DisposableBean` được đưa vào có chủ đích để chứng minh: có cấu hình destruction **không đồng nghĩa** scope này sẽ chủ động hủy đối tượng.

## 6. Giới hạn vòng đời và giải phóng tài nguyên

Spring giao cho `Scope.registerDestructionCallback(name, callback)` khả năng nhận callback khi scoped bean cần được hủy. Tuy nhiên, cài đặt `SimpleThreadScope` **không hỗ trợ chạy các destruction callback**: nó bỏ qua yêu cầu và ghi cảnh báo. Vì vậy không được dựa vào các hook sau để tự giải phóng bean ở scope này:

- `@PreDestroy`;
- `DisposableBean.destroy()`;
- phương thức `destroyMethod` được cấu hình trên `@Bean`;
- cleanup dự kiến diễn ra khi bean rời scope hoặc khi context đóng.

### Vì sao `remove(name)` vẫn chưa đủ?

`Scope.remove("workState")` chỉ **bỏ tham chiếu bean khỏi map của thread hiện tại** và trả về bean bị bỏ (hoặc `null`). Lời gọi này **không tự chạy** destruction callback, không tự đóng `AutoCloseable`, không quét bean thuộc các thread khác.

Đây là tình huống dễ gây hiểu nhầm:

```java
Object removed = context.getBeanFactory()
        .getRegisteredScope("thread")
        .remove("workState");
// removed không còn được cache trong map của thread hiện tại,
// nhưng DisposableBean.destroy() chưa được tự gọi.
```

Đoạn trên là **mảnh minh họa**, giả định đang ở nơi có biến `context` đã mở và `workState` không dùng scoped proxy.

### Cleanup chủ động trong phạm vi do ứng dụng kiểm soát

Nếu muốn tiếp tục dùng `SimpleThreadScope`, chỉ dùng cho bean mà ứng dụng **tự điều khiển được việc kết thúc tác vụ và dọn dẹp**. Ví dụ, thực hiện trên **chính thread đã dùng bean**:

```java
try {
    WorkState current = context.getBean(WorkState.class);
    // Sử dụng current trong công việc của thread này.
} finally {
    Object removed = context.getBeanFactory()
            .getRegisteredScope("thread")
            .remove("workState");
    if (removed instanceof DisposableBean disposable) {
        disposable.destroy(); // Do ứng dụng chủ động gọi.
    }
}
```

Đây là mảnh ghép từ chương trình mục 5, **không phải chương trình Java độc lập**. Cách gọi `destroy()` thủ công chỉ hợp lý với hợp đồng cleanup bạn thực sự sở hữu. Nó **không tương đương** toàn bộ cơ chế Spring destruction (chẳng hạn xử lý `@PreDestroy` qua post-processor). Nếu tài nguyên có `close()` rõ ràng, nên viết quản lý `AutoCloseable`/`try-with-resources` sao cho luôn close, rồi xóa cache đúng thread; cẩn thận tránh dùng lại một bean đã close.

Các trường hợp có kết nối cơ sở dữ liệu, socket, stream, lock, buffer lớn, transaction handle hoặc tài nguyên native cần cleanup chắc chắn **không nên mặc định được đưa vào `SimpleThreadScope`**. Nếu nhiệm vụ là triển khai một scope thực sự có vòng đời hoàn chỉnh, cần tự cài đặt `Scope` có quản lý callback, điểm kết thúc scope, và kiểm thử cleanup ở mọi đường thoát (bình thường, lỗi, hủy).

## 7. Thread pool: nguồn lỗi dễ gặp nhất

Thread pool giữ worker sống và **tái sử dụng thread**. Vì `SimpleThreadScope` khóa dữ liệu theo thread nên hai tác vụ độc lập có thể thấy **cùng bean**, như ví dụ chạy ở mục 5.

```text
Task A -> pool-worker-1 -> thread-local["workState"] -> bean #2
Task B -> pool-worker-1 -> thread-local["workState"] -> bean #2 (còn từ A)
Task C -> pool-worker-2 -> thread-local["workState"] -> bean #3
```

Hệ quả:

- **Rò rỉ dữ liệu giữa tác vụ:** trạng thái người dùng, correlation ID hoặc dữ liệu bảo mật của task A có thể bị task B đọc lại nếu không reset.
- **Giữ tài nguyên quá lâu:** worker sống hàng giờ/ngày, nên map thread-local vẫn có thể giữ đối tượng nặng dù nghiệp vụ đã kết thúc.
- **Khó dự đoán instance:** một request có thể đổi worker hoặc một workflow chia nhiều task; không thể suy ra "một job = một bean" chỉ từ scope `thread`.
- **Khó cleanup toàn cục:** `remove` trên main thread không xóa map của các worker khác; muốn cleanup cần cơ chế thực thi trên đúng worker và kiểm soát toàn bộ tác vụ.

`@Async`, `CompletableFuture.supplyAsync` và các executor không tự truyền `ThreadLocal` của thread gọi sang thread chạy task. Dùng scoped proxy cũng không thay đổi điều đó. Đặc biệt, một tác vụ logic đổi thread giữa các giai đoạn sẽ nhìn thấy các bean thread-scope khác nhau.

**Virtual threads (Java 21+)** có `ThreadLocal` riêng nhưng vẫn **không biến `SimpleThreadScope` thành task/request scope đúng nghĩa**. Một virtual thread riêng cho mỗi tác vụ có thể giảm việc worker tái sử dụng trạng thái, nhưng vẫn không cung cấp destruction callback; việc thread kết thúc cũng không đồng nghĩa tài nguyên đã được close. Các chương trình reactive có thể đổi thread trong một luồng xử lý, nên không nên dùng thread scope để mô hình hóa reactive context.

## 8. So sánh với scope và cơ chế thay thế

| Giải pháp | Ranh giới instance | Vòng đời/cleanup | Khi nên dùng |
| --- | --- | --- | --- |
| `singleton` | Một bean name trong một Spring container | Spring quản lý destruction khi đóng context | Service không trạng thái, dùng chung an toàn giữa các thread |
| `prototype` | Mỗi lần yêu cầu bean là lần tạo mới | Spring không tự quản lý destruction hoàn chỉnh sau khi trao bean | Đối tượng ngắn hạn, caller chủ động dọn dẹp |
| `SimpleThreadScope` | Một bean name / một thread / một scope instance | **Không có callback cleanup tự động** | Demo thread-local, tác vụ có thread ownership rất rõ và không giữ tài nguyên cần hủy |
| `request` | Một HTTP request trong web-aware context | Scope tích hợp vòng đời request và callback hủy | Trạng thái đúng vòng đời HTTP request |
| `session` | Một HTTP session trong web-aware context | Theo lifecycle session | Trạng thái gắn với một phiên người dùng, không gắn với thread |
| Tham số phương thức / object mới + `try-with-resources` | Theo tác vụ do code xác định | Caller chủ động close, kể cả khi lỗi | Trạng thái ngắn hạn hoặc tài nguyên bắt buộc giải phóng |
| `TaskDecorator` hoặc cơ chế context propagation chuyên dụng | Theo ngữ cảnh thực thi được truyền rõ ràng | Tùy cơ chế, cần reset trong `finally` | Truyền thông tin request/correlation qua executor khi thực sự cần |

**Với ứng dụng web:** nếu cần bean đúng một lần cho mỗi request, dùng `@RequestScope` thay vì `@Scope("thread")`. Một HTTP request có thể chuyển thread; đồng thời một servlet worker có thể phục vụ nhiều HTTP request khác nhau.

**Với xử lý nền:** nếu state chỉ tồn tại trong một công việc, thường rõ ràng và an toàn hơn khi tạo state ở đầu job, truyền nó qua tham số tới các hàm, rồi đóng trong `finally` hoặc `try-with-resources`. Nếu cần custom scope, phải thiết kế "job started/job completed" và cleanup rõ ràng.

## 9. Kiểm tra một custom thread scope

Nếu bắt buộc dùng thread scope trong ứng dụng hoặc bài thử nghiệm, nên có các kiểm tra hành vi sau:

1. **Chưa đăng ký:** `@Scope("thread")` được truy cập phải cho thấy lỗi thiếu scope; đăng ký đúng key và đúng thời điểm sẽ giải quyết được.
2. **Cùng thread:** hai lần `getBean` cùng tên trả cùng reference.
3. **Khác thread:** hai thread nhận đối tượng khác nhau.
4. **Thread pool tái sử dụng:** hai task trên một worker vẫn nhận cùng bean nếu không remove/reset.
5. **Tháo bean:** chạy `remove` trên chính worker khiến lần truy cập sau tạo đối tượng mới, nhưng destructor không tự chạy.
6. **Đóng context:** thử `@PreDestroy`/`DisposableBean` phải xác nhận không thể trông cậy vào callback từ `SimpleThreadScope`.
7. **Lỗi giữa chừng:** bảo đảm cleanup trong `finally`, không chỉ ở đường chạy thành công.
8. **Singleton dependency:** kiểm chứng scoped proxy hoặc `ObjectProvider` nhận target phù hợp với thread thực thi.

Một kiểm thử "đã giải phóng tài nguyên" phải quan sát việc `close/destroy` thực sự được gọi hoặc tài nguyên thực sự đã đóng; **việc map không còn tham chiếu hoặc GC có thể xảy ra không đủ làm bằng chứng**.

## 10. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân điển hình | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| `No Scope registered for scope name 'thread'` hoặc `IllegalStateException` | Chưa đăng ký trước khi bean được tạo | Đăng ký bằng `registerScope` trước `refresh`, hoặc cấu hình `CustomScopeConfigurer` từ sớm |
| Hai request khác nhau đọc chung state | Servlet/worker thread được tái sử dụng | Dùng `request` scope hoặc quản lý state theo request/job |
| Một singleton luôn thấy cùng một instance | Inject trực tiếp scoped bean lúc khởi tạo singleton | `ObjectProvider` hoặc scoped proxy, kiểm tra thời điểm resolve |
| Bean không được close sau khi xong việc | `SimpleThreadScope` bỏ qua destruction callback | Tự close trong `finally` đúng thread hoặc thay bằng scope có lifecycle |
| `remove` không có tác dụng với worker | Gọi `remove` trên thread khác | Gọi cleanup đúng thread hoặc thiết kế job-scope chủ động |
| `@Async` không thấy state của caller | Chuyển sang executor thread có thread-local riêng | Truyền dữ liệu cần thiết rõ ràng, hoặc dùng cơ chế truyền context thích hợp |
| Log xuất hiện cảnh báo destruction callback | Bean có cấu hình destroy nhưng scope không hỗ trợ | Không dựa vào callback đó; thay thiết kế quản lý lifecycle |
| Tên thread giống nhau nhưng bean khác | `getConversationId()` chỉ phản ánh tên thread | Dùng identity/reference và mô hình ownership thực tế, không dùng tên như key độc nhất |

## 11. Checklist lựa chọn trước khi đưa vào ứng dụng

- Scope `thread` đã được đăng ký chính xác trong BeanFactory quản lý bean chưa?
- Nghiệp vụ có bảo đảm **một tác vụ luôn sống đúng trên một Java thread** không?
- Có executor/thread pool, `@Async`, virtual threads hoặc reactive pipeline có thể tái phân phối công việc không?
- Một worker có tái sử dụng state từ tác vụ trước và gây rò rỉ dữ liệu không?
- Bean có chứa tài nguyên cần `close()`/`destroy()`/`@PreDestroy` không? Nếu có, đâu là **điểm cleanup thực thi được**?
- Singleton có nắm giữ trực tiếp instance thay vì proxy/provider không?
- Đã kiểm tra riêng trường hợp success, exception, timeout, cancellation và context shutdown chưa?

**Quy tắc quyết định:** `SimpleThreadScope` rất hữu ích để học cơ chế custom `Scope` và `ThreadLocal`, hoặc dùng cho trạng thái gắn với thread có kiểm soát. Nếu mục tiêu thật là "mỗi HTTP request", "mỗi tác vụ bất đồng bộ", "mỗi transaction" hoặc "tự hủy tài nguyên", hãy chọn abstraction phản ánh đúng vòng đời đó.

## 12. Nguồn đối chiếu chính thức

- Spring Framework — [Bean Scopes và Using a Custom Scope](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html).
- Spring Framework Javadoc — [SimpleThreadScope](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/support/SimpleThreadScope.html).
- Spring Framework Javadoc — [Scope interface](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/config/Scope.html).
- Spring Framework Javadoc — [CustomScopeConfigurer](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/config/CustomScopeConfigurer.html).

Các nguồn trên xác nhận `SimpleThreadScope` không được đăng ký mặc định và không hỗ trợ lifecycle cleanup đầy đủ. Những ví dụ vận hành thread pool cho thấy vì sao phạm vi theo Java thread không thay thế phạm vi theo request hoặc job.
