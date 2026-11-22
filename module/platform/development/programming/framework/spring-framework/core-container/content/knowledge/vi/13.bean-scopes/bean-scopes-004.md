# Prototype scope trong Spring: mỗi lần container đáp ứng yêu cầu lấy bean

## 1. Prototype là gì?

Trong Spring Framework Core Container, mỗi **bean definition** là một công thức để container tạo đối tượng, cấu hình dependency và thực hiện các bước khởi tạo. `scope` quyết định container tái sử dụng đối tượng đã có hay tạo đối tượng mới khi một bean được yêu cầu.

Với `prototype`, **mỗi lần Spring IoC container thực sự giải quyết một yêu cầu lấy bean thuộc scope đó, container tạo và cung cấp một instance mới**. Những yêu cầu điển hình gồm:

- Gọi `applicationContext.getBean(TaskState.class)` hoặc `beanFactory.getBean("taskState")`.
- Container cần một dependency prototype để dựng một bean khác.
- Gọi `ObjectProvider<TaskState>.getObject()` để yêu cầu bean vào đúng thời điểm cần sử dụng.
- Gọi một phương thức `@Lookup` đã được container triển khai để tra cứu bean.

Định nghĩa thường dùng:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
TaskState taskState() {
    return new TaskState();
}
~~~

Trong một context đã đăng ký bean này, hai lời gọi `getBean(TaskState.class)` độc lập bình thường trả về hai đối tượng khác nhau. Dữ liệu có thể thay đổi bên trong đối tượng thứ nhất không tự động xuất hiện ở đối tượng thứ hai. Đây là **quy tắc theo lần tra cứu/giải quyết bean**, không phải một đối tượng cho mỗi thread, mỗi HTTP request, mỗi transaction hay mỗi lần gọi một phương thức bất kỳ.

So với `singleton` (mặc định), prototype có điểm khác trọng tâm:

| Tiêu chí | `singleton` | `prototype` |
| --- | --- | --- |
| Mỗi lần container lấy cùng bean definition | Trả lại cùng instance trong context | Tạo instance mới cho lần lấy đó |
| Khởi tạo thường gặp | Khi context khởi động nếu không lazy, hoặc khi được yêu cầu | Khi bean thực sự được yêu cầu, bao gồm khi cần để tiêm dependency |
| Trạng thái mutable | Có thể được nhiều nơi dùng chung; phải xử lý an toàn đồng thời | Tách biệt giữa các instance **nếu bên gọi không chia sẻ lại chúng** |
| Dọn dẹp lúc đóng context | Spring gọi destroy callback theo cơ chế lifecycle | Spring **không tự gọi destroy callback** cho prototype đã trao cho bên dùng |

Hai quy tắc quan trọng: **scope gắn với bean definition** (không tự động biến mọi `new TaskState()` thành bean Spring) và **instance mới chỉ được tạo khi có một lần lấy bean mới**.

## 2. Một lần container đáp ứng yêu cầu diễn ra như thế nào?

Xét bean `taskState` khai báo prototype. Một chuỗi yêu cầu điển hình:

~~~text
ApplicationContext
  ├── getBean("taskState") lần 1
  │     └── tạo TaskState A → inject dependencies → init → trả A
  ├── getBean("taskState") lần 2
  │     └── tạo TaskState B → inject dependencies → init → trả B
  └── getBean("taskState") lần 3
        └── tạo TaskState C → inject dependencies → init → trả C

A, B, C là ba instance riêng.
~~~

Mỗi lần tạo, Spring dùng cấu hình của bean definition: lựa chọn constructor/factory method, giải quyết dependency, áp dụng `BeanPostProcessor` và gọi các callback khởi tạo phù hợp trước khi trả bean. Khi đó `prototype` **không có nghĩa là bỏ qua dependency injection hay khởi tạo của Spring**.

Một prototype thường được tạo lúc cần dùng, nhưng “chưa gọi `getBean` thì chưa bao giờ được tạo” là kết luận sai: singleton khởi tạo sớm có constructor parameter là prototype có thể khiến prototype được tạo **ngay khi singleton được dựng**. Ngược lại, một bean prototype không có ai yêu cầu sẽ không được tự động dựng hàng loạt chỉ vì context đã `refresh`.

Tên “prototype” dễ gây nhầm với design pattern Prototype (clone một object mẫu). Spring prototype scope **không đảm bảo sử dụng `clone()`**: thông thường container chạy lại quy trình tạo bean từ bean definition hoặc factory method.

## 3. Ví dụ Java 17 chạy được: `getBean`, trạng thái riêng và singleton

Ví dụ dùng Spring Framework `6.2.0`, Java 17+ và Maven. Cấu trúc:

~~~text
prototype-demo/
├── pom.xml
└── src/main/java/example/PrototypeDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>prototype-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/PrototypeDemo.java`:

~~~java
package example;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public final class PrototypeDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            TaskState first = context.getBean(TaskState.class);
            TaskState second = context.getBean(TaskState.class);
            first.mark();

            System.out.println("Hai lần getBean tạo hai object: " + (first != second));
            System.out.println("Trạng thái độc lập: "
                    + (first.value() == 1 && second.value() == 0));

            JobRunner runner = context.getBean(JobRunner.class);
            System.out.println("Runner là singleton: "
                    + (runner == context.getBean(JobRunner.class)));
            System.out.println("Dependency tiêm trực tiếp được giữ lại: "
                    + (runner.injected() == runner.injected()));
            System.out.println("Provider cấp instance mới mỗi lần: "
                    + (runner.fresh() != runner.fresh()));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public TaskState taskState() {
            return new TaskState();
        }

        @Bean
        public JobRunner jobRunner(TaskState injected,
                                   ObjectProvider<TaskState> provider) {
            return new JobRunner(injected, provider);
        }
    }

    public static final class TaskState {
        private int value;

        public void mark() {
            value++;
        }

        public int value() {
            return value;
        }
    }

    public static final class JobRunner {
        private final TaskState injected;
        private final ObjectProvider<TaskState> provider;

        public JobRunner(TaskState injected, ObjectProvider<TaskState> provider) {
            this.injected = injected;
            this.provider = provider;
        }

        public TaskState injected() {
            return injected;
        }

        public TaskState fresh() {
            return provider.getObject();
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.PrototypeDemo
~~~

Stdout mong đợi (không tính thông báo riêng của môi trường Maven):

~~~text
Hai lần getBean tạo hai object: true
Trạng thái độc lập: true
Runner là singleton: true
Dependency tiêm trực tiếp được giữ lại: true
Provider cấp instance mới mỗi lần: true
~~~

Giải thích theo thứ tự: hai `getBean` tạo hai `TaskState`; tăng bộ đếm ở instance đầu không thay đổi instance sau. `JobRunner` mặc định là singleton nên hai lần lấy runner cho cùng reference. Khi dựng runner, Spring đã tạo **một** `TaskState` để tiêm vào tham số `injected`; trường đó giữ nguyên reference khi gọi `runner.injected()` nhiều lần. Ngược lại, mỗi `runner.fresh()` gọi `provider.getObject()`, kích hoạt một lần lấy bean prototype mới.

Ví dụ dùng `@Configuration(proxyBeanMethods = false)` vì các `@Bean` được resolve thông qua container. Không dùng các lời gọi trực tiếp `new Config().taskState()` hoặc `config.taskState()` để kiểm tra lifecycle của bean Spring: gọi Java thông thường không tương đương một lần truy xuất bean qua container.

## 4. Trường hợp quan trọng nhất: prototype được tiêm vào singleton

Giả sử `OrderService` là singleton, `OrderDraft` là prototype:

~~~java
@Component
class OrderService {
    private final OrderDraft draft;

    OrderService(OrderDraft draft) {
        this.draft = draft;
    }

    OrderDraft currentDraft() {
        return draft;
    }
}

@Component
@Scope("prototype")
class OrderDraft {
    // Trạng thái đang soạn đơn
}
~~~

Đây là **đoạn minh họa** với các import Spring tương ứng, không phải chương trình chạy độc lập. Khi Spring dựng `OrderService`, nó tạo một `OrderDraft` rồi tiêm reference vào constructor. Mọi lần gọi `currentDraft()` trên **cùng `OrderService`** đều trả lại instance đã tiêm ấy. Việc đặt scope prototype trên `OrderDraft` không làm trường `draft` tự động biến đổi theo mỗi method call.

Nếu muốn **một draft mới cho mỗi thao tác**, nên lấy bean lúc thao tác diễn ra:

~~~java
@Component
class OrderService {
    private final ObjectProvider<OrderDraft> drafts;

    OrderService(ObjectProvider<OrderDraft> drafts) {
        this.drafts = drafts;
    }

    void placeOrder() {
        OrderDraft draft = drafts.getObject(); // Mỗi lần gọi là một lookup mới
        // Dùng draft này xuyên suốt một thao tác, rồi chủ động giải phóng nếu cần.
    }
}
~~~

`ObjectProvider<T>` được Spring cấp vào injection point; `getObject()` là thời điểm yêu cầu `T` từ container. Nếu `T` mang scope prototype, mỗi lần gọi cung cấp bean mới. Provider có thêm các API như `getIfAvailable()` và `getIfUnique()`, nhưng hành vi “mới mỗi lần” chỉ đúng khi bean **được provider resolve là prototype**, không đúng cho singleton. Nếu cần một đối tượng được dùng thống nhất xuyên suốt một thao tác, **gọi provider một lần và giữ biến cục bộ**; tránh gọi lại ở từng dòng mã làm việc với cùng draft.

Các đường lấy prototype trong singleton:

| Cách truy cập | Bao giờ resolve? | Kết quả với prototype |
| --- | --- | --- |
| Constructor/field/setter inject `T` | Lúc khởi tạo bean nhận dependency | Một instance được giữ theo reference đã inject |
| `ObjectProvider<T>.getObject()` | Mỗi lần gọi `getObject()` | Một instance mới mỗi lần gọi |
| `ObjectFactory<T>.getObject()` | Mỗi lần gọi `getObject()` | Một instance mới mỗi lần gọi |
| `jakarta.inject.Provider<T>.get()` | Mỗi lần gọi `get()` | Một instance mới; cần dependency Jakarta Inject phù hợp |
| `ApplicationContext.getBean(T.class)` | Mỗi lần gọi `getBean` | Một instance mới; mã nghiệp vụ phụ thuộc trực tiếp vào container |
| Phương thức `@Lookup` | Mỗi lần method được Spring override được gọi | Một instance mới nếu bean được lookup là prototype |

Nên ưu tiên `ObjectProvider` khi một singleton cần lấy prototype nhiều lần, vì dễ thể hiện ý định “lấy mới theo nhu cầu” và dễ thay thế trong test. Constructor injection trực tiếp phù hợp khi chỉ cần một dependency tại thời điểm tạo bean nhận nó.

## 5. Các cách cấu hình scope prototype

**Qua `@Bean` trong Java configuration** (như ví dụ chạy ở trên):

~~~java
@Bean
@Scope("prototype")
public TaskState taskState() {
    return new TaskState();
}
~~~

**Qua component scanning**:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class WorkerTask {
    // ...
}
~~~

Để ví dụ component-scanning có hiệu lực, ứng dụng phải scan package chứa `WorkerTask` (chẳng hạn cấu hình `@ComponentScan`), và class phải được đăng ký như Spring bean. Nếu đồng thời khai báo nhiều bean cùng type, lookup bằng type có thể cần `@Qualifier` hoặc bean name rõ ràng.

**Qua XML bean definition** trong ứng dụng cấu hình XML:

~~~xml
<bean id="workerTask" class="example.WorkerTask" scope="prototype"/>
~~~

Lưu ý: các cách trên thể hiện ba cơ chế đăng ký bean khác nhau; không khai báo trùng một bean name một cách vô ý.

## 6. Lifecycle: container khởi tạo prototype nhưng không tự destroy

Một lần tạo prototype đi qua các bước chung của bean Spring: dựng instance, resolve/inject dependency, áp dụng các bean post-processor, gọi callback khởi tạo tương ứng (ví dụ `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()`), rồi trao đối tượng cho bên yêu cầu.

**Giới hạn đặc biệt:** sau khi đã trả prototype cho bên dùng, Spring thường không lưu danh sách instance đó để tự gọi callback hủy về sau. Khi `ApplicationContext.close()`, Spring **không tự động gọi** `@PreDestroy`, `DisposableBean.destroy()` hoặc custom destroy method trên mỗi prototype đã từng tạo. `@PreDestroy` có thể khai báo hợp lệ nhưng vẫn không được gọi tự động cho prototype như đối với singleton.

Vì vậy:

- Nếu bean giữ file handle, socket, connection hay tài nguyên phải đóng, bên nhận cần quy ước ownership và chủ động đóng.
- Một đối tượng triển khai `AutoCloseable` có thể được dùng với `try-with-resources` tại nơi lấy bean: `try (WorkUnit unit = context.getBean(WorkUnit.class)) { unit.execute(); }`. Đây là ví dụ minh họa, giả sử `WorkUnit` triển khai `AutoCloseable`.
- Có thể tổ chức một cơ chế theo dõi và dọn dẹp chuyên biệt (ví dụ custom `BeanPostProcessor`) khi nghiệp vụ thật sự cần; chỉ gắn `@PreDestroy` cho prototype là chưa đủ.
- Prototype không tự hết hạn theo thời gian. Nếu singleton lưu reference prototype vào field hoặc collection dài hạn, instance vẫn tồn tại chừng nào còn được tham chiếu; có thể làm tăng bộ nhớ và giữ tài nguyên.

Phân biệt **Spring hoàn tất giai đoạn tạo bean** với **ứng dụng hoàn tất sử dụng bean**. Với prototype, phần thứ hai là trách nhiệm của mã sử dụng hoặc cơ chế quản lý do ứng dụng thiết kế.

## 7. `@Lookup` và scoped proxy: hiểu chính xác “mỗi lần”

### Lookup method injection

`@Lookup` cho phép Spring tạo subclass động để override method lấy bean (điển hình là prototype), nhờ đó service không trực tiếp gọi container. Ví dụ minh họa:

~~~java
@Component
public abstract class JobService {
    public void handle() {
        WorkerTask task = newTask();
        // Dùng task cho lần xử lý này
    }

    @Lookup
    protected abstract WorkerTask newTask();
}
~~~

Trong cấu hình này, nếu `WorkerTask` là prototype, mỗi lời gọi `newTask()` qua instance do Spring tạo sẽ lấy một bean mới. Vì cần tạo subclass, class và method được override không được `final`. Lookup method injection không hoạt động với các đối tượng được dựng bởi `@Bean` factory method rồi trả về vì container không tạo subclass của đối tượng đó theo cách này. Cách dùng trên là minh họa độc lập với ví dụ Maven.

### Scoped proxy cho prototype

Cấu hình `@Scope(value = "prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)` có thể tiêm một **proxy ổn định** vào singleton; **mỗi method call qua proxy** tìm một target prototype mới. Điều đó dễ gây hiểu nhầm: hai method call kế tiếp lên “cùng proxy” có thể thực thi trên **hai target khác nhau**, vì thế dữ liệu sửa trong method thứ nhất không nhất thiết còn ở method thứ hai. Nếu một thao tác cần gọi nhiều method trên cùng một đối tượng có trạng thái, `ObjectProvider.getObject()` một lần và giữ reference cục bộ thường minh bạch hơn.

Đừng nhầm prototype scoped proxy với request-scoped proxy: proxy request thường chọn cùng target trong một HTTP request; proxy prototype thường tạo target mới **theo mỗi invocation**.

## 8. Lúc nào nên dùng và những lỗi thường gặp

Prototype phù hợp khi mỗi lần thực hiện công việc cần **state mutable độc lập** và đối tượng ấy phải được Spring wiring/configure, ví dụ worker mang trạng thái xử lý một job hoặc một command object đang được bổ sung dữ liệu. Singleton phù hợp hơn cho service/stateless component dùng chung, đặc biệt khi nó không giữ state riêng cho từng tác vụ.

Các lỗi và cách kiểm tra:

1. **“`@Scope("prototype")` nghĩa là mỗi lần gọi method sẽ tự tạo bean mới.”** Sai với reference prototype thông thường. Chỉ một lookup mới (hoặc proxy có hành vi đặc biệt) mới kích hoạt tạo instance mới.
2. **“Tiêm prototype một lần vào singleton thì singleton luôn nhận prototype mới.”** Sai. Constructor/field injection thông thường xảy ra lúc singleton được tạo. Cần `ObjectProvider`, `@Lookup` hoặc giải pháp truy xuất theo nhu cầu tương đương.
3. **“Prototype = một bean cho mỗi HTTP request.”** Sai. Hai lookup trong cùng request tạo hai prototype; còn `request` scope thiết kế một instance cho một request trong web-aware context.
4. **“Prototype mặc định thread-safe.”** Sai. Mỗi instance ban đầu có thể riêng, nhưng khi chia sẻ reference cho nhiều thread, state mutable vẫn cần đồng bộ hoặc giới hạn ownership. Dependencies singleton có trạng thái chia sẻ cũng cần xem xét an toàn đồng thời.
5. **“Đóng context sẽ đóng mọi prototype từng cấp phát.”** Sai. Phải dọn dẹp tài nguyên theo ownership; đừng dựa vào destroy callback tự động.
6. **“Tự `new` một object tương đương `getBean`.”** Sai. `new` bỏ qua wiring, post-processing, AOP proxy và nhiều tiện ích lifecycle mà container thực hiện.
7. **“Prototype giúp giảm cấp phát.”** Thường ngược lại: nhiều lookup có nghĩa nhiều đối tượng hơn. Với đối tượng rất nhỏ chỉ chứa dữ liệu và không cần Spring wiring, tạo object Java thông thường có thể đơn giản hơn.
8. **“Prototype ngăn rò rỉ bộ nhớ.”** Sai. Nếu giữ các instance trong cache/collection không giới hạn hoặc quên đóng resource, chúng vẫn được giữ lại.

### Checklist thực hành

- Đã khai báo `prototype` trên **bean definition** và bean được đăng ký đúng trong context chưa?
- Bên nhận cần **một instance khi khởi tạo**, hay **một instance mới cho mỗi lần xử lý**?
- Tại điểm sử dụng đã thực sự tạo lookup mới (`getBean`/`getObject`/`@Lookup`) chưa?
- Nếu nhiều method cùng làm việc với một job, đã giữ **cùng reference cục bộ** cho toàn bộ job chưa?
- Bên nào chịu trách nhiệm đóng resource, và prototype có bị giữ quá thời gian cần thiết không?
- Đã kiểm tra hành vi bằng `a != b` sau **hai lookup độc lập**, đồng thời xác nhận state không vô tình được chia sẻ qua dependency khác chưa?

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Bean `A` là singleton, bean `B` là prototype. `A` nhận `B` qua constructor rồi gọi `b.run()` 10 lần. Spring tạo bao nhiêu `B` chỉ vì 10 lần `run()` đó?

**Đáp án:** Không tạo thêm `B` nào chỉ do gọi `run()`. Một `B` đã được tạo khi dựng `A` và được tái sử dụng; có thể có các instance `B` khác vì lookup ở nơi khác.

**Câu 2.** Trong cùng một HTTP request, gọi `context.getBean(B.class)` ba lần khi `B` là prototype. Ba kết quả có buộc là cùng object không?

**Đáp án:** Không. Có ba lần lookup prototype độc lập nên thông thường ba instance riêng.

**Câu 3.** `ObjectProvider<B>` được tiêm vào singleton, nhưng `B` thực chất là singleton. Hai `provider.getObject()` có tạo hai đối tượng khác nhau không?

**Đáp án:** Không. Provider tuân theo scope thật của bean được lấy; với singleton, nó trả instance đã được container quản lý.

**Câu 4.** Một prototype có `@PreDestroy`. Khi đóng `AnnotationConfigApplicationContext`, phương thức này chắc chắn được gọi cho tất cả prototype đã lấy không?

**Đáp án:** Không. Ứng dụng cần cơ chế cleanup cho prototype đã nhận.

## Tham khảo chính thức

- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html)
- [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
