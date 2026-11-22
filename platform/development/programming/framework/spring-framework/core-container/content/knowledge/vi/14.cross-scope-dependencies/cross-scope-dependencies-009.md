# Thiết kế, đăng ký và kiểm soát vòng đời Scope tùy biến trong Spring Framework

## 1. Vì sao cần tự xây dựng Scope?

**Bean scope** trả lời câu hỏi: *Với một bean definition, Spring nên cung cấp cùng một instance trong khoảng thời gian hoặc ngữ cảnh nào?* Scope mặc định `singleton` giữ một instance trên mỗi bean definition trong một IoC container; `prototype` tạo instance cho từng lần container được yêu cầu. Trong ứng dụng web còn có `request`, `session`, `application` và `websocket` khi context tương ứng hỗ trợ.

Những vòng đời của nghiệp vụ đôi khi không trùng với scope sẵn có. Ví dụ:

- Một **lần chạy job** phải chia sẻ một đối tượng trạng thái giữa các bước, nhưng job tiếp theo cần đối tượng mới.
- Một **lượt xử lý batch** có cache ngắn hạn và phải xóa cache khi batch kết thúc.
- Một **conversation/wizard** gồm nhiều bước cần giữ trạng thái đến khi người dùng kết thúc cuộc hội thoại.
- Một **đơn vị công việc** có tài nguyên được tạo lúc truy cập đầu tiên, rồi đóng có kiểm soát khi công việc hoàn tất.

Lúc đó, Spring cho phép bạn định nghĩa một scope mới bằng giao diện `org.springframework.beans.factory.config.Scope`, đặt tên (chẳng hạn `operation`), đăng ký nó với `ConfigurableBeanFactory` và gắn tên scope lên bean definition.

Đây là cơ chế thuộc **Spring Core Container / Dependency Injection**. Scope tùy biến quản lý *lifetime và identity* của target bean, không tự xử lý transaction, cơ chế khóa, HTTP request, bảo mật, hay đồng bộ giữa các JVM.

### Kết quả học tập

Sau bài này bạn có thể:

1. Thiết kế đúng ranh giới *scope identity*, thời điểm kích hoạt, lưu trữ và kết thúc.
2. Hiểu ý nghĩa và hợp đồng của năm phương thức trong `Scope` SPI.
3. Đăng ký scope trước khi Spring tạo các bean phụ thuộc bằng `registerScope` hoặc `CustomScopeConfigurer`.
4. Dùng `@Scope`, scoped proxy và `ObjectProvider` để phối hợp bean ngắn vòng đời với singleton.
5. Chủ động chạy destruction callbacks, tránh leak với thread pool, xử lý concurrency, exception và test vòng đời.
6. Chạy ví dụ Java 17 + Spring Framework và kiểm tra mỗi operation có target riêng, cleanup chạy đúng một lần.

## 2. Phân biệt bean definition, scope storage, proxy và target

Trong Spring, bean definition chứa thông tin Spring cần để tạo bean: class/factory method, dependency, cấu hình lifecycle và tên scope. **Scope** là bộ phận giữ hoặc tra cứu các *target object* của những bean dùng cùng tên scope đó.

~~~text
ApplicationContext / BeanFactory
  ├── bean definition: scopedState; scope="operation"
  │       └── scoped proxy (nếu khai báo proxyMode)
  │                 └── Scope.get(targetName, ObjectFactory)
  │                         ├── operation A → ScopedState #1
  │                         └── operation B → ScopedState #2
  └── bean definition: worker; scope="singleton"
          └── giữ tham chiếu đến scoped proxy
~~~

Nếu một singleton giữ **target** được tạo trong operation A, nó sẽ vô tình dùng dữ liệu cũ ở operation B. Thay vào đó, singleton có thể giữ **scoped proxy**, hoặc yêu cầu target bằng `ObjectProvider` trong lúc operation đang active.

**Không đồng nhất ba thời điểm sau:**

1. **Đăng ký scope:** BeanFactory biết tên `operation` trỏ đến một đối tượng triển khai `Scope`.
2. **Đăng ký bean definition:** Bean `scopedState` tuyên bố dùng `operation`; nếu proxy được cấu hình, Spring có thể tạo proxy trước khi operation bắt đầu.
3. **Tạo target:** Khi ứng dụng thực sự gọi qua proxy/provider và scope đang active, `Scope.get(...)` mới lấy hoặc tạo target tương ứng.

Đổi từ `ScopedProxyMode.INTERFACES` sang `TARGET_CLASS` chỉ thay *kiểu proxy*, không thay quy tắc target được tạo hoặc hủy bởi scope.

## 3. Thiết kế hợp đồng vòng đời trước khi viết code

Một scope tùy biến phải quy định rõ những câu hỏi sau:

| Khía cạnh | Cần quyết định | Ví dụ scope `operation` |
| --- | --- | --- |
| Khóa ngữ cảnh | Ai xác định một phiên scope? | Mỗi lần gọi `begin(operationId)` |
| Kích hoạt | Khi nào truy cập bean là hợp lệ? | Giữa `begin` và `end` của cùng thread |
| Identity | Hai lần tra cùng bean ở cùng ngữ cảnh có cùng instance? | Có |
| Lưu trữ | Instance được giữ ở đâu? | Map gắn với `ThreadLocal` trong bản mẫu |
| Tạo mới | Ai thực sự tạo bean? | `ObjectFactory.getObject()` do Spring cung cấp |
| Loại bỏ sớm | Nếu bỏ một bean riêng lẻ thì sao? | `remove(name)` bỏ instance và callback của nó |
| Hủy tự nhiên | Ai chạy callback khi scope kết thúc? | `end()` chạy callbacks, sau đó giải phóng state |
| Truyền ngữ cảnh | Operation có tự đi qua thread khác? | Không trong bản mẫu |
| Đồng thời | Có nhiều thread chia sẻ cùng ngữ cảnh không? | Không; mỗi thread có scope state riêng |
| Lỗi | Nếu callback ném exception thì sao? | Tiếp tục callback khác, cuối cùng dọn state và báo lỗi |

**Scope identity phải khớp khái niệm nghiệp vụ.** `ThreadLocal` chỉ thích hợp cho *một operation gắn với một thread*; nó không tự trở thành scope cho một HTTP request, distributed job, Reactor subscription hoặc mọi tác vụ của thread pool. Nếu một operation chạy qua nhiều thread, cần cơ chế lưu state theo operation-id và context propagation có kiểm soát; thay cấu trúc lưu trữ mà vẫn giữ đúng vòng đời/callback.

Với scope có thể được truy cập đồng thời từ nhiều thread, phải thiết kế **atomic get-or-create theo (scope-id, bean-name)**, cơ chế kết thúc khi vẫn có người dùng và đồng bộ destruction callbacks. Chỉ dùng `ConcurrentHashMap` không tự giải quyết race giữa tạo/hủy/đóng scope.

## 4. Scope SPI: năm phương thức quan trọng

Giao diện:

~~~java
package org.springframework.beans.factory.config;

public interface Scope {
    Object get(String name, ObjectFactory<?> objectFactory);
    Object remove(String name);
    void registerDestructionCallback(String name, Runnable callback);
    Object resolveContextualObject(String key);
    String getConversationId();
}
~~~

Đây là **chữ ký giản lược minh họa**: bỏ annotation nullability và Javadoc, không phải mã nguồn để biên dịch như một tệp ứng dụng. `ObjectFactory` thuộc `org.springframework.beans.factory.ObjectFactory`.

### 4.1. get(String name, ObjectFactory<?> objectFactory)

Đây là phương thức trung tâm, Spring gọi để truy xuất target:

1. Kiểm tra scope đang **active**; nếu không, thường ném `IllegalStateException`.
2. Tìm target theo tên bean trong vùng lưu trữ của scope hiện hành.
3. Nếu target đã có, trả lại **đúng instance đó**.
4. Nếu chưa có, gọi `objectFactory.getObject()` để **Spring tạo và khởi tạo target**, lưu lại rồi trả về.

Không tạo target bằng `new TargetClass()` trong scope implementation: làm vậy bỏ qua dependency injection, `BeanPostProcessor`, initialization và lifecycle của Spring. `ObjectFactory` đã được BeanFactory cung cấp để tạo bean theo metadata tương ứng.

`get(...)` không nên trả `null`; lifecycle contract yêu cầu trả object. Không gọi `ObjectFactory.getObject()` mỗi lần trong scope mà mục tiêu là “một instance mỗi operation”: như vậy sẽ biến scope thành gần như prototype, khiến cùng công việc nhận nhiều target.

### 4.2. remove(String name)

Loại một target riêng lẻ khỏi storage và trả về instance đã bỏ, hoặc `null` nếu không có. Nếu có destruction callback cho bean đó, scope implementation **nên xóa callback khỏi registry** để tránh chạy lại khi kết thúc scope.

Một điểm dễ nhầm: theo hợp đồng `Scope`, `remove()` **không bắt buộc tự chạy destruction callback**; trong trường hợp remove được gọi qua BeanFactory, bên gọi có thể chịu trách nhiệm hủy bean phù hợp. Vì thế không nên tùy tiện vừa chạy callback trong `remove` vừa để caller hủy cùng bean lần thứ hai.

Để kết thúc **toàn bộ scope**, tạo API riêng như `end()` hoặc `closeConversation(id)`: API đó chạy callback của những target còn lại, xóa storage và giải phóng ngữ cảnh.

### 4.3. registerDestructionCallback(String name, Runnable callback)

Spring dùng phương thức này để đăng ký thao tác cleanup nếu scoped bean có cấu hình destruction thực sự (ví dụ `@PreDestroy`, `DisposableBean` hoặc method khai báo bằng `@Bean(destroyMethod = "...")`).

Trách nhiệm của scope: giữ callback cùng lifecycle của instance và **thực thi khi instance/scope được hủy tự nhiên**. Callback không tự chạy chỉ vì Java garbage collector thu hồi proxy, cũng không được bảo đảm tự chạy khi đóng `ApplicationContext` nếu custom scope không chủ động kết thúc những context state đã mở.

Nếu scope không hỗ trợ callback, tài nguyên như kết nối, buffer hoặc cache có thể bị giữ quá lâu. Một implementation production nên:

- Cho phép callbacks được thêm trong lúc target được tạo.
- Không chạy callback hai lần.
- Chạy cleanup cho những instance còn tồn tại ngay cả khi một callback khác bị lỗi.
- Dọn tham chiếu đến instance/callback khỏi storage để tránh memory leak.
- Chốt rõ thứ tự hủy; thường có thể chạy theo **thứ tự ngược** với lúc callbacks được đăng ký, nhưng dependency phức tạp cần thiết kế riêng.
- Ghi nhận lỗi dọn dẹp theo cơ chế quan sát của ứng dụng, không im lặng nuốt mọi exception.

**Phân biệt:** `prototype` có lifecycle hủy khác: Spring không tự theo dõi và dọn mọi prototype instance sau khi trả về client. Trong custom scope, chính implementation có thể chủ động thu thập và gọi callbacks nếu được BeanFactory đăng ký.

### 4.4. resolveContextualObject(String key)

Cho phép phân giải một đối tượng/phần thông tin của scope theo khóa cụ thể. Ví dụ custom operation scope có thể hỗ trợ khóa `"operationId"` để truy cập id ngữ cảnh hiện hành.

Nếu không có contextual object tương ứng, có thể trả `null`. Không nên dùng API này làm một service locator tùy tiện hoặc cho phép truy cập dữ liệu nhạy cảm ngoài ngữ cảnh hiện tại. Với scope chưa active, implementation có thể ném `IllegalStateException` nhất quán với `get`.

### 4.5. getConversationId()

Trả identifier của **ngữ cảnh scope hiện hành** nếu có ý nghĩa. Với HTTP session scope, đó thường là session id; với `operation`, đó có thể là operation id. Có thể trả `null` nếu scope không có identifier phù hợp.

Tên `conversation` ở đây mang tính khái niệm của Scope SPI: không có nghĩa bạn bắt buộc xây dựng web conversation hoặc lưu thông tin trong HTTP session.

## 5. Đăng ký scope đúng thời điểm

### 5.1. registerScope: con đường tường minh

Spring cung cấp:

~~~java
ConfigurableBeanFactory beanFactory = /* BeanFactory của context */;
beanFactory.registerScope("operation", new OperationScope());
~~~

`registerScope(String, Scope)` liên kết tên phạm vi với một implementation. Việc đăng ký cần xảy ra **trước khi bean definition dùng scope đó được resolve để tạo target**; thực tế nên thực hiện ngay trong giai đoạn cấu hình BeanFactory, trước khi context bắt đầu eager singleton creation.

Không tái sử dụng `singleton` hoặc `prototype` làm tên custom scope: đây là hai scope lõi không thể override theo cách này. Hãy dùng tên riêng thể hiện semantics: `operation`, `batch`, `conversation`... và tránh trùng các scope khác đã đăng ký.

Trong ví dụ chạy ở mục 6, thứ tự bảo đảm:

~~~java
AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext();
OperationScope operationScope = new OperationScope();
context.getBeanFactory().registerScope("operation", operationScope);
context.register(AppConfig.class);
context.refresh();
~~~

Đoạn này nằm trong method Java của chương trình bên dưới. `refresh()` là ranh giới khởi tạo context; cấu hình proxy và các singleton có thể được thiết lập trong giai đoạn đó.

### 5.2. CustomScopeConfigurer trong cấu hình Spring

Spring có `CustomScopeConfigurer`, một `BeanFactoryPostProcessor` chuyên đăng ký scopes. Đây là lựa chọn thích hợp khi để Spring bootstrap toàn bộ context từ configuration:

~~~java
@Bean
static CustomScopeConfigurer customScopeConfigurer() {
    CustomScopeConfigurer configurer = new CustomScopeConfigurer();
    configurer.addScope("operation", new OperationScope());
    return configurer;
}
~~~

Snippet giả định method nằm trong lớp `@Configuration` và có import của `CustomScopeConfigurer`. Khai báo `@Bean static` giúp Spring tạo BeanFactoryPostProcessor sớm, tránh phải khởi tạo instance configuration class quá sớm chỉ để tạo post-processor.

**Lưu ý về cùng một instance:** Nếu code nghiệp vụ phải gọi `begin()/end()` trên scope implementation, nó cần tham chiếu đến **đúng đối tượng scope đã đăng ký với BeanFactory**. Đừng vô tình tạo hai `new OperationScope()` rồi điều khiển bản không được đăng ký. Với trường hợp này, có thể quản lý đối tượng bằng bootstrap rõ ràng như mục 6, hoặc thiết kế factory/registrar phù hợp.

Một lựa chọn linh hoạt hơn là tự tạo `BeanFactoryPostProcessor` gọi `beanFactory.registerScope("operation", scope)`. Cả hai cách đăng ký phù hợp hơn việc cố đăng ký quá muộn trong constructor của một singleton khác.

### 5.3. Khai báo scope cho bean

~~~java
@Component
@Scope(value = "operation", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class OperationState {
    public String status() {
        return "active";
    }
}
~~~

Snippet minh họa này nằm trong ứng dụng đã đăng ký tên scope `operation`. Bạn cũng có thể áp dụng `@Scope` trên method `@Bean` hoặc dùng thuộc tính `scope` trong XML bean definition. Một tên scope custom **không tự xuất hiện** chỉ vì bạn ghi annotation; BeanFactory vẫn phải đăng ký scope implementation tương ứng.

Nếu `@Scope("operation")` để `proxyMode` mặc định `DEFAULT`, thường không có scoped proxy. Để inject vào singleton mà không lấy target trước giờ, hãy cấu hình proxy hoặc dùng lazy lookup.

## 6. Ví dụ hoàn chỉnh: scope “operation” với begin/end và cleanup

Ví dụ Java 17 sau **không cần Spring Boot, servlet hay HTTP server**. Nó minh họa cách mở một operation, tái sử dụng cùng target trong operation đó, tạo target mới trong operation tiếp theo và gọi callback cleanup khi operation đóng.

### 6.1. Cấu trúc dự án

~~~text
operation-scope-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ScopeLifecycleDemo.java
~~~

**pom.xml** — Spring Framework `6.2.9` và Java 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>operation-scope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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

**src/main/java/demo/ScopeLifecycleDemo.java**

~~~java
package demo;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectFactory;
import org.springframework.beans.factory.config.Scope;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ScopedProxyMode;

public class ScopeLifecycleDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // 1. Khởi tạo và đăng ký đúng instance của custom scope.
            OperationScope operationScope = new OperationScope();
            context.getBeanFactory().registerScope("operation", operationScope);

            // 2. Nạp bean definitions rồi khởi động container.
            context.register(AppConfig.class);
            context.refresh();

            // 3. Đây là singleton, giữ một scoped proxy.
            Worker worker = context.getBean(Worker.class);

            // 4. Mở / đóng lần lượt hai phạm vi nghiệp vụ.
            for (String operationId : List.of("op-A", "op-B")) {
                operationScope.begin(operationId);
                try {
                    int first = worker.currentStateId();
                    int second = worker.currentStateId();

                    System.out.println(
                            "operation=" + operationScope.getConversationId()
                                    + " first=" + first
                                    + " second=" + second);
                } finally {
                    operationScope.end();
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean(destroyMethod = "cleanup")
        @org.springframework.context.annotation.Scope(
                value = "operation",
                proxyMode = ScopedProxyMode.TARGET_CLASS)
        public ScopedState scopedState() {
            return new ScopedState();
        }

        @Bean
        public Worker worker(ScopedState scopedState) {
            return new Worker(scopedState);
        }
    }

    public static class Worker {
        private final ScopedState scopedState;

        public Worker(ScopedState scopedState) {
            this.scopedState = scopedState;
        }

        public int currentStateId() {
            return scopedState.id();
        }
    }

    public static class ScopedState {
        private static final AtomicInteger NEXT_ID = new AtomicInteger();
        private final int id = NEXT_ID.incrementAndGet();

        public int id() {
            return id;
        }

        public void cleanup() {
            System.out.println("destroy=" + id);
        }
    }

    public static class OperationScope implements Scope {
        private final ThreadLocal<Bucket> current = new ThreadLocal<>();

        // Chỉ một operation active trên mỗi thread trong ví dụ này.
        public void begin(String operationId) {
            Objects.requireNonNull(operationId, "operationId");
            if (current.get() != null) {
                throw new IllegalStateException("Operation already active");
            }
            current.set(new Bucket(operationId));
        }

        // Hủy các target còn lại rồi luôn tháo ThreadLocal.
        public void end() {
            Bucket bucket = requireActive();
            try {
                List<Runnable> callbacks =
                        new ArrayList<>(bucket.destructionCallbacks.values());
                Collections.reverse(callbacks);

                RuntimeException failure = null;
                for (Runnable callback : callbacks) {
                    try {
                        callback.run();
                    } catch (RuntimeException ex) {
                        if (failure == null) {
                            failure = ex;
                        } else {
                            failure.addSuppressed(ex);
                        }
                    }
                }
                if (failure != null) {
                    throw failure;
                }
            } finally {
                bucket.beans.clear();
                bucket.destructionCallbacks.clear();
                current.remove();
            }
        }

        @Override
        public Object get(String name, ObjectFactory<?> objectFactory) {
            Bucket bucket = requireActive();
            return bucket.beans.computeIfAbsent(
                    name, ignored -> Objects.requireNonNull(
                            objectFactory.getObject(), "Scoped bean is null"));
        }

        @Override
        public Object remove(String name) {
            Bucket bucket = requireActive();
            bucket.destructionCallbacks.remove(name);
            return bucket.beans.remove(name);
        }

        @Override
        public void registerDestructionCallback(
                String name, Runnable callback) {
            requireActive().destructionCallbacks.put(
                    name, Objects.requireNonNull(callback));
        }

        @Override
        public Object resolveContextualObject(String key) {
            Bucket bucket = requireActive();
            return "operationId".equals(key) ? bucket.operationId : null;
        }

        @Override
        public String getConversationId() {
            return requireActive().operationId;
        }

        private Bucket requireActive() {
            Bucket bucket = current.get();
            if (bucket == null) {
                throw new IllegalStateException("No active operation scope");
            }
            return bucket;
        }

        private static class Bucket {
            final String operationId;
            final Map<String, Object> beans = new LinkedHashMap<>();
            final Map<String, Runnable> destructionCallbacks =
                    new LinkedHashMap<>();

            Bucket(String operationId) {
                this.operationId = operationId;
            }
        }
    }
}
~~~

### 6.2. Biên dịch và chạy

Đảm bảo `java -version` và `mvn -version` báo JDK 17 trở lên. Tại thư mục `operation-scope-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ScopeLifecycleDemo
~~~

**Kết quả stdout của chương trình** (không tính thông báo riêng của Maven nếu môi trường in thêm):

~~~text
operation=op-A first=1 second=1
destroy=1
operation=op-B first=2 second=2
destroy=2
~~~

Giải thích từng quan sát:

1. `Worker` là singleton nên được tạo trong `context.refresh()`; constructor chỉ nhận proxy class của `ScopedState`.
2. `begin("op-A")` mở một `Bucket` mới. Lần đầu gọi `worker.currentStateId()`, proxy yêu cầu target, scope gọi `ObjectFactory.getObject()` và tạo `ScopedState` có id 1.
3. Lần gọi thứ hai trong **cùng operation** lấy lại instance có id 1.
4. `end()` gọi destruction callback mà Spring đã đăng ký cho bean có `destroyMethod="cleanup"`. Vì vậy xuất hiện `destroy=1`.
5. `begin("op-B")` tạo một `Bucket` khác. Target mới có id 2; đến `end()` thì callback in `destroy=2`.

Dù `Worker` giữ **cùng proxy**, object `ScopedState` phía sau thay đổi theo operation. Hai thao tác `begin/end` được điều khiển bởi mã ứng dụng, không có server hoặc request context ẩn nào làm thay.

### 6.3. Tại sao code trên không dùng @PostConstruct để kiểm tra bean?

Một singleton có thể được tạo khi context refresh, tức là **trước `begin()`**. Nếu trong constructor, `@PostConstruct` hoặc bean initialization method của `Worker` bạn gọi `scopedState.id()`, scoped proxy sẽ thử resolve target khi `OperationScope` chưa active và nhận lỗi. Constructor chỉ nên lưu proxy; lời gọi target diễn ra sau khi operation bắt đầu.

### 6.4. Vì sao dùng try/finally thay vì gọi end sau code nghiệp vụ?

Nếu mã xử lý phát sinh exception mà `end()` nằm sau đoạn code thường, cleanup có thể bị bỏ qua. `finally` bảo đảm cơ hội chạy callback và xóa ThreadLocal dù công việc thành công hay thất bại. Trong ứng dụng production, nên đóng gói API thành `AutoCloseable` và dùng `try-with-resources` nếu cần đảm bảo mọi caller tuân thủ:

~~~java
try (OperationHandle handle = operationManager.open("op-C")) {
    worker.process();
}
~~~

Đây là **API thiết kế minh họa**, không có sẵn trong Spring và không được định nghĩa trong chương trình ở mục 6. Với triển khai thực, `OperationHandle.close()` cần idempotent hoặc kiểm soát double close, ràng buộc thread/ownership và gọi end đúng phạm vi.

### 6.5. Giới hạn cố ý của ví dụ

Scope trong mục 6 được thiết kế cho **operation tuần tự, một thread mỗi lần**, vì:

- `ThreadLocal` chỉ lưu state trên đúng thread đã gọi `begin()`.
- `LinkedHashMap` không được đồng bộ; an toàn trong giới hạn một thread.
- `begin()` từ chối mở lồng nhau. Muốn nested operations cần stack ngữ cảnh, logic phục hồi context trước và quy tắc target visibility.
- `get()` không hỗ trợ truy cập đồng thời trong cùng một Bucket. Nếu chia sẻ qua nhiều thread, phải có lock/lifecycle coordination.
- Khi thread kết thúc đột ngột trước `finally`, cleanup không được bảo đảm. Ở môi trường có thread pool, bỏ quên `end()` sẽ làm thread tái sử dụng mang state cũ và có thể leak bộ nhớ/dữ liệu.
- Đây là minh họa trong một JVM, không có persistence/distributed coordination.

Những giới hạn trên là **thuộc tính của implementation ví dụ**, không phải ràng buộc bắt buộc của giao diện Spring `Scope`.

## 7. Đăng ký scope trong ứng dụng Spring Boot hoặc ứng dụng lớn

Nếu ứng dụng do Spring Boot tạo context tự động, bạn thường không tự viết `AnnotationConfigApplicationContext`. Có hai hướng:

**Hướng A — dùng BeanFactoryPostProcessor tạo và đăng ký scope:**

~~~java
@Configuration
class ScopeRegistrationConfig {

    @Bean
    static org.springframework.beans.factory.config.BeanFactoryPostProcessor
    registerOperationScope() {
        return beanFactory ->
                beanFactory.registerScope("operation", new OperationScope());
    }
}
~~~

Đây là **snippet tích hợp**, yêu cầu `OperationScope` có sẵn trong package ứng dụng. Nếu cần điều khiển begin/end, phải cung cấp một cách lấy lại **chính instance** đã đăng ký, chẳng hạn một coordinator/factory với lifecycle phù hợp. Tránh tạo duplicate scope state.

**Hướng B — CustomScopeConfigurer:**

~~~java
@Configuration
class ScopeRegistrationConfig {

    @Bean
    static org.springframework.beans.factory.config.CustomScopeConfigurer
    customScopes() {
        var configurer =
                new org.springframework.beans.factory.config.CustomScopeConfigurer();
        configurer.addScope("operation", new OperationScope());
        return configurer;
    }
}
~~~

`CustomScopeConfigurer` là BeanFactoryPostProcessor do Spring cung cấp, hỗ trợ đăng ký scope theo tên. Trong cấu hình XML, có thể khai báo bean `CustomScopeConfigurer` và map `scopes` tương ứng.

**Không đăng ký scope trễ ở một controller/service constructor:** Eager singleton initialization có thể xảy ra trước đó và scoped bean chưa được nhận diện đúng. Đăng ký trong giai đoạn BeanFactory preparation/BFPP là cách ổn định hơn.

Với nhiều `ApplicationContext` (ví dụ parent/child web contexts), đăng ký ở **BeanFactory chứa bean definitions liên quan**. Custom scope storage và registry thuộc từng BeanFactory; cùng một tên trên hai contexts không mặc nhiên dùng chung cùng đối tượng `Scope` hoặc cùng target.

## 8. Scope khác vòng đời và tương tác với singleton/prototype

### 8.1. Inject ngắn vòng đời vào singleton

~~~java
@Service
class JobService {
    private final OperationState state;

    JobService(OperationState state) {
        this.state = state;
    }

    void execute() {
        state.process();
    }
}
~~~

Nếu `OperationState` được khai báo `@Scope(value = "operation", proxyMode = ScopedProxyMode.TARGET_CLASS)`, singleton `JobService` có thể giữ scoped proxy. Khi `execute()` được gọi trong một operation active, proxy tìm target thích hợp.

Nếu dùng `INTERFACES`, code phải inject qua interface được proxy expose; JDK proxy không phải instance của concrete implementation class. Nếu class final, class-based proxy không thể subclass. Đây là vấn đề *proxy type* khác với trách nhiệm *lifecycle storage* của custom scope.

### 8.2. ObjectProvider khi muốn tự quyết định thời điểm lấy target

~~~java
@Service
class JobService {
    private final ObjectProvider<OperationState> states;

    JobService(ObjectProvider<OperationState> states) {
        this.states = states;
    }

    void execute() {
        OperationState current = states.getObject();
        current.process();
    }
}
~~~

Snippet minh họa cần các import `org.springframework.beans.factory.ObjectProvider`, `org.springframework.stereotype.Service`, một class `OperationState` thực tế và scope đã đăng ký. Có thể dùng `@Scope("operation")` **không proxy** cho target trong trường hợp này. `getObject()` gọi lúc operation đã active; nếu gọi ngoài operation, scope có thể ném `IllegalStateException`. Provider không tự mở scope hoặc làm bean “an toàn đa luồng”.

### 8.3. Đừng lấy target và giữ vĩnh viễn

Nếu client làm như sau:

~~~java
OperationState cached = provider.getObject();
// Lưu cached vào static/global singleton field, rồi dùng lại trong operation khác.
~~~

thì custom scope không thể tự thay target của tham chiếu `cached`. Khi lifetime của scope kết thúc, resource có thể đã bị dọn trong khi caller vẫn giữ reference. Hãy truyền dữ liệu cần thiết ra khỏi scope thay vì giữ target hoặc dùng scoped proxy khi cần hành vi tra target theo ngữ cảnh.

### 8.4. Scope khác singleton/prototype thế nào?

| Scope | Lúc gọi lấy bean | Ai xác định điểm hết đời? | Dọn target |
| --- | --- | --- | --- |
| `singleton` | Cùng bean instance theo bean definition trong container | Container / context | Spring thực hiện destruction khi container đóng đúng quy trình |
| `prototype` | Tạo instance mới khi được BeanFactory lookup | Caller quyết định sử dụng đến đâu | Caller tự chịu trách nhiệm cleanup; Spring không theo dõi để tự gọi destroy cho mọi instance |
| `operation` tự định nghĩa | Cùng target trong một operation, target khác trong operation kế | Application-defined `end()` | Scope implementation chạy callbacks và giải phóng state |
| `request` có sẵn trong web-aware context | Cùng target trong HTTP request | HTTP request lifecycle | Web scope implementation đảm nhận cleanup theo lifecycle |

Khi so sánh, cần phân biệt **target thực tế** với proxy: cùng một scoped proxy có thể được dùng qua nhiều operation, song target của nó thay đổi.

## 9. Kiểm soát hủy và loại bỏ sớm

### 9.1. Callback đến từ đâu?

Khi Spring tạo target qua `ObjectFactory` và bean có destruction metadata, BeanFactory đăng ký destruction logic với implementation `Scope` bằng `registerDestructionCallback`. Ví dụ dùng `@Bean(destroyMethod = "cleanup")` tạo callback đóng `ScopedState`.

Những cơ chế liên quan gồm:

- `@PreDestroy` (với Jakarta annotation API nếu ứng dụng dùng).
- `DisposableBean.destroy()`.
- `@Bean(destroyMethod = "...")` hoặc metadata destroy method khác.

Không phải mọi bean đều đăng ký callback: bean không có logic destruction có thể không tạo callback nào; chỉ việc rời scope storage vẫn cần được thực hiện.

### 9.2. Đóng scope là hành động chủ động của application

Một custom scope không tự động biết thời điểm “job hoàn tất” hoặc “conversation kết thúc” chỉ nhờ container. Người thiết kế phải đưa `end()` vào đúng execution boundary, ví dụ finally block của job dispatcher hoặc hook kết thúc conversation, và chắc chắn mọi nhánh đều thực hiện cleanup.

Đóng `ApplicationContext` **không thay thế** việc chốt tất cả các scope context tự quản lý trên nhiều thread. Chỉ cần gọi `context.close()` không có nghĩa một custom `ThreadLocal` scope sẽ tự thu thập state từ mọi thread: dữ liệu đó có thể không còn truy cập được từ thread đang đóng container.

### 9.3. Xóa riêng một bean

Trong ví dụ, `OperationScope.remove(name)`:

- Xóa target khỏi `beans`.
- Xóa destruction callback tương ứng khỏi `destructionCallbacks`.
- Trả target đã xóa (hoặc `null`).

Đó là hành vi đúng theo contract phổ biến của `Scope.remove`: không tự chạy callback vì bên gọi có thể thực hiện destroy. Nếu ứng dụng cung cấp API “invalidate bean”, cần quyết định rõ API đó chỉ evict hay còn hủy resource theo đúng một đường chịu trách nhiệm, tránh double destroy hoặc resource leak.

### 9.4. Thứ tự dọn và lỗi

Ở bản mẫu, callbacks chạy ngược thứ tự đăng ký. Nếu một callback ném `RuntimeException`, code vẫn chạy các callback còn lại, gắn lỗi phát sinh khác vào `suppressed`, và cuối cùng xóa maps/ThreadLocal trong `finally`.

Trong hệ thống phức tạp cần xét thêm:

- Thứ tự hủy theo quan hệ bean dependencies.
- Callback có thể thay đổi cấu trúc scope hay tạo target khác trong lúc đóng.
- Callback treo/chặn lâu, timeout/cancellation.
- Phân biệt lỗi nghiệp vụ ban đầu và lỗi cleanup để không vô tình che mất nguyên nhân gốc.
- Logging/metrics cho callback thất bại.
- Thread interrupt và các loại `Error` nghiêm trọng; hệ thống phải có chính sách xử lý rõ ràng.

Ví dụ chỉ bắt `RuntimeException` để đủ ngắn; production cleanup phức tạp có thể cần error policy mạnh hơn và trạng thái `closing` để từ chối tạo target mới khi scope đang kết thúc.

## 10. Concurrency, context propagation và phân tán

### 10.1. ThreadLocal là một chiến lược, không phải định nghĩa scope

Đối với `ThreadLocal`:

~~~text
Thread T1: begin("A") → target#1 → end() → remove ThreadLocal
Thread T2: begin("B") → target#2 → end() → remove ThreadLocal
Thread T1: begin("C") → target#3 → end() → remove ThreadLocal
~~~

Thậm chí T1 được thread pool dùng lại, lần `begin("C")` phải tạo state mới. Nếu quên `end()`, lần gọi kế tiếp trên cùng thread có thể báo “Operation already active” và vẫn giữ references. Nguy hiểm hơn, implementation lỏng lẻo có thể vô tình trộn dữ liệu của hai tác vụ.

Đừng dùng `InheritableThreadLocal` như cách tổng quát để chia sẻ scope trong `ExecutorService`: các pool worker được tái sử dụng và không có quan hệ lifetime một-một với task. Với async/reactive workflows, hãy dùng cơ chế context propagation phù hợp hoặc scope keyed theo logical operation, cùng chiến lược ownership/cleanup rõ ràng.

### 10.2. Nếu cùng một operation chạy trên nhiều thread

Bạn cần thiết kế lại thành map `operationId → bucket`, hoặc một storage của framework thích hợp:

1. Có cơ chế mang `operationId` đến mọi execution segment.
2. Cùng operationId phải tìm cùng bucket (nếu semantics nghiệp vụ yêu cầu chia sẻ).
3. `get(name, factory)` đồng bộ việc tạo bean để không tạo trùng instance.
4. Không đóng bucket khi vẫn có in-flight users.
5. Quyết định có dùng reference count, lease, timeout hay explicit ownership hay không.
6. Khi kết thúc, dừng tạo mới, chờ/quyết định xử lý yêu cầu còn hoạt động, chạy callbacks, evict storage.
7. Nếu operation nằm trên nhiều node/JVM, dữ liệu và lifecycle cần distributed coordination riêng; một map in-memory của một JVM không chia sẻ state với node khác.

**Scope isolation không tự bảo đảm thread safety của bean.** Nếu một scoped target có `ArrayList` mutable và nhiều thread cùng dùng, target vẫn có thể race.

### 10.3. Timeout và cleanup khi client mất kết nối

Với conversation dài hạn hoặc session do ứng dụng tự định nghĩa, caller có thể không gọi `end()` vì crash/network drop. Production scope thường cần TTL/idle eviction/scheduled cleanup theo chính sách, ranh giới quyền sở hữu và xử lý retry/idempotency. Cần tránh callback hủy resource khi một tác vụ hợp lệ vẫn đang truy cập.

## 11. Chiến lược kiểm thử Scope tùy biến

Nên kiểm thử cả hợp đồng SPI lẫn tích hợp container.

### 11.1. Kiểm thử thao tác đơn vị

Với một implementation tương tự ví dụ:

- Gọi `get("x", factory)` **trước begin** phải báo scope chưa active.
- `begin("A")`; hai lần `get("x", factory)` trả **cùng object**, factory chỉ được gọi một lần.
- Gọi `get("y", factory)` tạo object khác.
- `resolveContextualObject("operationId")` và `getConversationId()` trả id A; khóa lạ trả `null`.
- Đăng ký callbacks, gọi `end()`: callbacks chạy đúng một lần, state được tháo.
- `begin("B")`; `get("x", factory)` tạo object mới.
- `remove("x")` trả instance cũ và xóa callback; sau đó `get("x", factory)` tạo target mới nếu operation vẫn active.
- `begin(...)` khi đang active phải bị từ chối theo API ví dụ.
- Để callback ném lỗi, xác minh callbacks khác vẫn chạy và `ThreadLocal` không còn state.
- Với nhiều threads, kiểm chứng isolation theo hợp đồng được thiết kế.

### 11.2. Kiểm thử tích hợp BeanFactory

Chạy ví dụ mục 6 và xác minh:

- Scope đã đăng ký trước khi refresh.
- `Worker` singleton được tạo dù chưa có operation.
- Proxy không resolve target trong constructor.
- Hai lời gọi trong một operation dùng cùng instance.
- Operation tiếp theo có target mới.
- `@Bean(destroyMethod = "cleanup")` được gọi sau từng operation, không gọi hai lần.
- Sau `end()`, gọi target qua proxy sẽ thất bại rõ ràng vì scope inactive.
- `context.close()` không bị hiểu nhầm là thay thế cơ chế `end()`.

Nếu dùng JUnit 5, giữ cùng Spring context nhưng mở và đóng operation riêng trong `@BeforeEach`/`@AfterEach`, tuyệt đối không để state của test trước chảy qua test tiếp theo. Với test đa luồng, kiểm thử không chỉ unique ids mà cả callback timing và không có data race.

## 12. Các lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `No Scope registered for scope name 'operation'` | Quên đăng ký scope hoặc đăng ký vào sai BeanFactory | Đăng ký đúng tên, đúng container, trước khi resolve target |
| `Scope 'operation' is not active for the current thread` | Gọi target ngoài `begin/end`, hoặc gọi trong thread khác | Đặt call trong operation active hoặc cung cấp context propagation đúng thiết kế |
| Singleton khởi tạo lỗi khi inject custom-scoped bean | Đã inject target trực tiếp, scope chưa active | Sử dụng scoped proxy hoặc `ObjectProvider` với lazy lookup |
| Mỗi lời gọi cho id mới dù cùng operation | `get` luôn gọi object factory, không cache theo bean name | Cache kết quả theo (active scope identity, bean name) |
| Operation tiếp theo vẫn có id cũ | Lưu target vào singleton/static field, hoặc không xóa state khi đóng | Giữ proxy/provider, chốt `end` và xóa storage |
| Method cleanup không chạy | Không lưu/chạy callback, bean không có destruction metadata, hoặc thiếu `end` | Đăng ký callback đúng SPI, tạo execution boundary bao đủ finally |
| Callback chạy hai lần | Vừa gọi trong `remove` vừa để caller hủy, hoặc `end` được gọi lặp không bảo vệ | Xác định duy nhất trách nhiệm destroy và bảo đảm idempotency khi cần |
| Thread pool có dữ liệu từ job trước | Quên xóa `ThreadLocal` | Dọn trong `finally`, kiểm soát lifecycle toàn bộ job |
| Exception cleanup làm bỏ qua cleanup các bean khác | `end` dừng ở callback đầu tiên lỗi | Chạy đầy đủ callbacks, tổng hợp lỗi và dọn state trong finally |
| Hai threads tạo cùng bean hai lần | Storage/get-or-create không atomic trong multi-thread scope | Đồng bộ per scope/key và điều phối đóng scope |
| Đổi `proxyMode` nhưng lỗi scope vẫn còn | Kiểu proxy không tạo context active hoặc sửa registry | Chẩn đoán riêng proxy typing, registry và scope activation |
| CGLIB không tạo proxy được | Bean target là final class hoặc phương thức cần intercept final/private | Dùng interface-based proxy hoặc thiết kế class có thể proxy |
| Một operation “chia sẻ” qua nhiều JVM nhưng trạng thái khác nhau | Scope chỉ lưu memory cục bộ mỗi JVM | Thiết kế distributed state và cluster lifecycle |

Khi gặp một lỗi, phân loại theo thứ tự: **(1) tên scope đã đăng ký? (2) đúng BeanFactory? (3) có active context? (4) proxy/provider lấy target tại đúng thời điểm? (5) storage và cleanup có đúng semantics?** Đọc root cause của `BeanCreationException`/`ScopeNotActiveException` thay vì chỉ nhìn thông báo ngoài cùng.

## 13. Những nguyên tắc dùng trong dự án thật

1. **Ưu tiên scope sẵn có** khi semantics đã khớp; custom scope làm tăng trách nhiệm lifecycle, observability và concurrency.
2. Định nghĩa rõ identity: key nào, ai mở/đóng, khi nào cùng target, thời gian sống tối đa.
3. Giao việc tạo bean cho Spring qua `ObjectFactory`; đừng bypass dependency injection.
4. Đăng ký scope sớm và đặt tên tránh xung đột với `singleton`/`prototype` cũng như scopes web.
5. Khi inject vào singleton, dùng scoped proxy hoặc `ObjectProvider`; không giữ target qua nhiều scope lifetimes.
6. Đảm bảo mỗi target được hủy **đúng một lần** theo hợp đồng, nhất là khi có remove/eviction.
7. Bọc execution boundary trong `try/finally` hoặc `try-with-resources` và luôn giải phóng ThreadLocal.
8. Nếu có concurrency hoặc cross-thread execution, thiết kế context propagation, synchronization và shutdown sequencing trước khi dùng.
9. Đừng giả định context close tự dọn toàn bộ state thuộc custom scope mà bạn tạo bên ngoài lifecycle container.
10. Kiểm thử cả happy path lẫn cancellation, lỗi khi tạo bean, lỗi callback, nested calls, pool reuse và nhiều contexts.

## 14. Tự kiểm tra

**Câu 1.** Vì sao `Scope.get` nên gọi `objectFactory.getObject()` thay vì `new`?

**Trả lời:** Vì ObjectFactory do BeanFactory cấp sẽ tạo bean theo Spring metadata, bao gồm dependency injection và lifecycle callbacks, trong khi `new` tự viết không được Spring xử lý như một bean target.

**Câu 2.** Nếu bean operation-scoped được inject vào singleton mà không có proxy, điều gì có thể xảy ra?

**Trả lời:** Singleton có thể cố lấy target ngay khi khởi tạo mà operation chưa active, hoặc giữ cố định một target thuộc operation trước. Dùng scoped proxy/`ObjectProvider` để phân giải lúc có operation.

**Câu 3.** `Scope.remove(name)` có bắt buộc gọi destruction callback không?

**Trả lời:** Không. Contract cho phép caller đảm nhận destruction. Scope implementation nên loại callback đã đăng ký để tránh hủy trùng; việc đóng toàn scope cần cơ chế gọi callbacks riêng.

**Câu 4.** Vì sao `ThreadLocal` scope phải xóa dữ liệu trong finally?

**Trả lời:** Thread pool worker có thể được tái sử dụng. Nếu state vẫn gắn với thread sau operation, nó có thể rò dữ liệu và giữ tham chiếu đến những object lẽ ra phải được hủy.

**Câu 5.** Đăng ký `operation` trong `BeanFactory` có tự mở một operation hay không?

**Trả lời:** Không. Đăng ký chỉ tạo mapping tên → Scope implementation. Application còn phải thực hiện bước kích hoạt và kết thúc ngữ cảnh theo semantics của scope.

**Câu 6.** Khi một scope được nhiều threads cùng truy cập, dùng `ConcurrentHashMap` có đủ chưa?

**Trả lời:** Chưa. Cần điều phối get/create/destroy, vòng đời đang đóng, race với callback, ownership và các yêu cầu đang chạy. Scope chỉ đúng khi không thể cung cấp target đã bị hủy hoặc tạo trùng ngoài semantics dự kiến.

**Câu 7.** Tại sao bean operation-scoped có `@Bean(destroyMethod="cleanup")` trong ví dụ in thông báo “destroy” sau `end()`?

**Trả lời:** Spring đăng ký destruction callback của target với custom scope; API `end()` do ứng dụng tự thiết kế thực thi callback rồi bỏ storage. Đây là trách nhiệm chủ động của scope implementation.

## Tài liệu tham khảo

- Spring Framework Reference — [Bean Scopes / Custom Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html#beans-factory-scopes-custom).
- Spring Framework API — [Scope SPI](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/Scope.html).
- Spring Framework API — [ConfigurableBeanFactory.registerScope](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html#registerScope(java.lang.String,org.springframework.beans.factory.config.Scope)).
- Spring Framework API — [CustomScopeConfigurer](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/CustomScopeConfigurer.html).
- Spring Framework Reference — [Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html#beans-factory-scopes-other-injection).
