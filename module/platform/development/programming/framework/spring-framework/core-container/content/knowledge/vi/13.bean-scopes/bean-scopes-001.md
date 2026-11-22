# Scope quyết định quan hệ giữa định nghĩa và thể hiện trong Spring Core Container

## 1. Tại sao bean definition chưa cho biết có bao nhiêu object?

Trong Spring Framework, **bean definition** là công thức (recipe) để container biết **cách tạo, cấu hình và quản lý một bean**. Cùng một bean definition, container có thể trả về **một object được dùng chung** hoặc **nhiều object riêng biệt** tùy **scope**. Vì vậy hai câu hỏi phải được tách rời:

1. **Definition:** Spring đã đăng ký thông tin về bean nào, cách tạo ra sao, dependencies là gì?
2. **Instance:** Khi ứng dụng yêu cầu bean, Spring trả object nào, tạo mới hay dùng lại, và object đó tồn tại trong ranh giới nào?

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    CatalogService catalogService() {
        return new CatalogService();
    }
}
```

Đây là ví dụ ngắn, chưa phải chương trình chạy độc lập. `catalogService` mặc định thuộc **singleton scope**, vì thế mỗi bean definition `catalogService` trong một Spring IoC container thông thường chỉ gắn với **một managed singleton object**.

Nhưng nếu đổi sang:

```java
@Bean
@Scope("prototype")
CatalogService catalogService() {
    return new CatalogService();
}
```

cùng cách khai báo factory method có thể tạo **nhiều CatalogService objects**, mỗi lần container nhận một yêu cầu lấy prototype bean.

**Điểm cốt lõi của chủ đề:** Scope không phải tên loại Java class; nó là **chính sách ánh xạ giữa bean definition và thể hiện (instance)** cùng ranh giới sử dụng/lifecycle của object.

### Mục tiêu học tập

Sau bài, bạn sẽ:

- Hiểu `BeanDefinition` là metadata/factory recipe, không đồng nhất với object.
- Nắm các scope chuẩn: `singleton`, `prototype`, `request`, `session`, `application`, `websocket`.
- Phân biệt Spring singleton **per bean, per container** với GoF Singleton dùng static global instance.
- Hiểu thời điểm bean creation, eager/lazy và scope là **những chiều khác nhau**.
- Biết tại sao một singleton inject prototype qua constructor vẫn giữ **chính một prototype instance đã nhận**.
- Sử dụng `ObjectProvider<T>`/`ObjectFactory<T>` hoặc scoped proxy cho dependency có vòng đời ngắn.
- Đánh giá request/session scope cần **web-aware ApplicationContext**, không tự hoạt động trong plain context.
- Hiểu destruction callback của prototype **không được Spring tự gọi khi context close**.
- Viết @Scope, @RequestScope, @SessionScope, XML scope và thiết lập custom scope.
- Thử nghiệm Java 17/Spring Framework 6.2 với output chính xác, chứng minh singleton identity và prototype multiplicity.
- Tránh các lỗi scope mismatch, stale request state, memory leaks và phụ thuộc sai lifecycle.

## 2. Mô hình từ định nghĩa đến thể hiện

Một bean definition bao gồm những thuộc tính như:

- Bean name/aliases.
- Java class, constructor hoặc factory method.
- Constructor/property dependencies.
- Scope.
- Lazy initialization.
- Initialization/destruction callbacks.
- Qualifiers, primary, role và các metadata khác.

BeanFactory đọc/gặp định nghĩa và thực hiện theo scope:

```text
                         BeanDefinition
            name = "jobUnit", class = JobUnit
            scope = singleton hoặc prototype
                              |
              +---------------+----------------+
              |                                |
              v                                v
         singleton scope                 prototype scope
        +----------------+               +----------------+
request #1 ---> object A                 request #1 ---> object A
request #2 ---> object A                 request #2 ---> object B
request #3 ---> object A                 request #3 ---> object C
        +----------------+               +----------------+
              |                                |
              v                                v
       Một object dùng chung              Nhiều objects tạo từ
       theo bean/container                cùng một recipe
```

Cụm từ “request #1/#2” trong sơ đồ là **yêu cầu BeanFactory lấy bean**, không nhất thiết là HTTP request. HTTP `request` scope sẽ được giải thích riêng.

### 2.1. Một definition có thể tồn tại mà chưa có instance

```java
boolean registered =
        context.getBeanFactory().containsBeanDefinition("jobUnit");
boolean singletonPresent =
        context.getBeanFactory().containsSingleton("jobUnit");
```

Ví dụ chỉ hoạt động khi `context` là `ConfigurableApplicationContext` phù hợp và `jobUnit` đã được khai báo. `containsBeanDefinition` kiểm tra definition trong local registry; `containsSingleton` kiểm tra singleton instance đã được đăng ký trong singleton registry. Hai kết quả không phải lúc nào cũng giống nhau.

Một prototype definition có thể có trong registry nhưng không có singleton instance, bởi **prototype không được cache như singleton**.

### 2.2. Một class có thể có nhiều bean definitions

```java
@Bean("primaryClient")
Client clientA() {
    return new Client("primary");
}

@Bean("backupClient")
Client clientB() {
    return new Client("backup");
}
```

Cả hai definitions cùng trả class `Client`, nhưng nếu đều singleton, Spring vẫn quản lý **hai singleton bean objects khác nhau** — mỗi tên bean có definition và cache entry của riêng nó.

Đừng diễn giải “singleton” là “một instance cho mỗi Java class”. Spring docs gọi đặc tính này là **per-container and per-bean**.

### 2.3. Một object Java chưa chắc là managed bean

```java
Client manual = new Client("manual");
```

Nếu bạn tự dùng `new`, object này **không tự động** có BeanDefinition, scope, injection, initialization callbacks hay destruction callback Spring. Một object có class trùng class của bean được quản lý vẫn có thể nằm **ngoài container**.

## 3. Bảng các scope chuẩn

Spring Framework 6.2 hỗ trợ các scopes sau:

| Scope | Ranh giới instance | Khi nào áp dụng? |
| --- | --- | --- |
| `singleton` | Một object được quản lý cho mỗi bean definition trong mỗi Spring IoC container | Scope mặc định, thường cho service/stateless collaborator |
| `prototype` | Mỗi yêu cầu BeanFactory lấy bean có thể tạo instance mới | Object có trạng thái ngắn hạn, mỗi lần sử dụng riêng |
| `request` | Một object cho mỗi HTTP request | Trạng thái gắn với request đang xử lý |
| `session` | Một object cho mỗi HTTP session | Trạng thái gắn với người dùng/phiên HTTP |
| `application` | Một object cho mỗi `ServletContext` | Trạng thái dùng chung trong một web application/servlet context |
| `websocket` | Một object cho mỗi WebSocket session phù hợp | Thành phần gắn với phiên WebSocket/STOMP |
| Custom scope | Do implementation `Scope` quyết định | Tenant, conversation hoặc mô hình vòng đời riêng |

Bốn web scopes **request, session, application, websocket** yêu cầu **web-aware `ApplicationContext`** tương ứng. `AnnotationConfigApplicationContext` thuần trong chương trình console không tự kích hoạt những scopes này.

Spring còn có `SimpleThreadScope` trong thư viện nhưng **không đăng ký mặc định**. Không coi `thread` là một trong sáu scope chuẩn tự động có sẵn ở mọi context.

### Cảnh báo thuật ngữ

“Request” trong `request scope` là một **HTTP request**; “yêu cầu lấy prototype bean” là **một lần BeanFactory resolve/getBean**, không phải một HTTP request. Một HTTP request có thể gọi `getBean` nhiều lần; các requests đến prototype sẽ nhận nhiều instances trừ khi có cơ chế giữ reference khác.

## 4. Singleton: một thể hiện dùng chung theo định nghĩa/container

### 4.1. Cú pháp Java

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    SharedCatalog sharedCatalog() {
        return new SharedCatalog();
    }
}
```

`singleton` là default scope, không cần `@Scope("singleton")`. Nếu muốn explicit:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
SharedCatalog sharedCatalog() {
    return new SharedCatalog();
}
```

Hai snippets minh họa riêng, không đặt cả hai definitions cùng tên vào một class thật. `ConfigurableBeanFactory` thuộc `org.springframework.beans.factory.config`.

### 4.2. Cú pháp XML

```xml
<bean id="sharedCatalog" class="example.SharedCatalog"/>
```

tương đương khai báo scope mặc định, và:

```xml
<bean id="sharedCatalog"
      class="example.SharedCatalog"
      scope="singleton"/>
```

là cách explicit. Trong file XML thật cần root `<beans>` và các namespace/schema hợp lệ.

### 4.3. Identity của singleton

```java
Object first = context.getBean("sharedCatalog");
Object second = context.getBean("sharedCatalog");
boolean same = first == second;
```

Với regular singleton, `same` là `true`. Hai tên alias trỏ cùng singleton definition cũng có thể trả đúng một object. Tuy nhiên nếu lấy `FactoryBean` hoặc AOP proxy, cần phân biệt object đang lấy là **factory, product hay proxy** khi đọc identity.

### 4.4. Khác GoF Singleton

GoF Singleton pattern thường đặt static global holder/constructor hạn chế trong Java class. Spring singleton:

- Ánh xạ theo **bean name/definition + BeanFactory**.
- Có thể có nhiều singleton definitions cùng class.
- Có thể có một instance riêng trong mỗi `ApplicationContext`.
- Không buộc class Java dùng static holder/private constructor.
- Có thể được Spring wrap bằng proxy.
- Được Spring quản lý injection/lifecycle.

Nói “singleton service” trong Spring thường không có nghĩa “Java class đó được phép instantiate đúng một lần trên toàn JVM”.

### 4.5. Singleton không đồng nghĩa thread-safe

Nhiều requests/threads có thể dùng cùng bean singleton. Scope chỉ nói về **chia sẻ object identity**, không tự đồng bộ mutable fields:

```java
// Phản ví dụ về mutable state không thread-safe.
class UnsafeCounter {
    private int count;
    int next() {
        return ++count;
    }
}
```

Nếu bean singleton bị gọi đồng thời, `++count` có thể mất updates. Dùng immutable state hoặc concurrency primitives như `AtomicInteger` khi thực sự cần shared mutation. Với request-specific data, không nên lưu trực tiếp vào field của singleton service.

## 5. Prototype: một bean definition tạo nhiều thể hiện

`prototype` thường dùng cho object stateful hoặc job/request objects có chủ sở hữu rõ.

### 5.1. Java configuration

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
JobUnit jobUnit() {
    return new JobUnit();
}
```

Hoặc:

```java
@Component
@Scope("prototype")
class JobUnit {
}
```

Hai snippets là **hai cách đăng ký thay thế**, không cùng dùng một class trong một context nếu không chủ động muốn hai definitions.

### 5.2. XML

```xml
<bean id="jobUnit"
      class="example.JobUnit"
      scope="prototype"/>
```

### 5.3. Mỗi lookup của prototype có thể tạo object mới

```java
JobUnit first = context.getBean(JobUnit.class);
JobUnit second = context.getBean(JobUnit.class);

System.out.println(first == second); // false trong trường hợp thường
```

Nhưng đó chỉ đúng nếu `JobUnit` được Spring đăng ký như prototype và không có wrapper/provider layer làm thay đổi ý nghĩa object bạn đang so sánh.

### 5.4. Prototype không phải “một object cho mỗi HTTP request”

Nếu service gọi `getBean(prototypeName)` ba lần trong cùng HTTP request, thông thường có ba prototype instances. Nếu cần **một instance dùng lại xuyên các lookups trong cùng HTTP request**, dùng `request` scope thay vì prototype.

### 5.5. Prototype được tạo khi có nhu cầu

BeanFactory thường không tạo toàn bộ prototype instances lúc `ApplicationContext.refresh()`. Nhưng một eager singleton yêu cầu prototype làm constructor dependency sẽ làm container tạo **một prototype object** ngay khi xây singleton. Xem mục 7.

## 6. Bean definition, scope và lazy/eager là ba trục khác nhau

Ba thuộc tính có liên hệ nhưng không đồng nghĩa:

- **Definition:** Có recipe/metadata được đăng ký hay chưa?
- **Scope:** Bao nhiêu instance và sharing boundary?
- **Laziness:** Khi nào container chủ động tạo một bean singleton?

Ví dụ:

```java
@Bean
@Lazy
SharedCatalog sharedCatalog() {
    return new SharedCatalog();
}
```

Đây vẫn là **singleton scope**. `@Lazy` chỉ làm container có thể trì hoãn việc tạo cho đến first use, trừ khi một eager dependency yêu cầu nó sớm.

`prototype` lại khác: object mới thường xuất hiện cho mỗi lần lookup, không phải có một singleton chờ được tạo muộn.

| Definition | Scope | Lazy? | Nghĩa gần đúng |
| --- | --- | --- | --- |
| `sharedCatalog` | singleton | false | Một bean được pre-instantiate trong ApplicationContext thông thường |
| `rareClient` | singleton | true | Một singleton được tạo khi thật sự được yêu cầu |
| `jobUnit` | prototype | tùy metadata | Một instance mới mỗi lần được yêu cầu |
| `requestState` | request | không thể diễn giải như eager singleton | Một instance theo HTTP request đang active |
| `userPrefs` | session | phụ thuộc active session | Một instance theo HTTP session |

**Không** nghĩ rằng đổi `@Lazy` thành `@Scope("prototype")` là tối ưu “cùng một việc”. Một cái thay thời điểm, cái kia thay identity/multiplicity và lifecycle.

## 7. Bẫy thường gặp: singleton inject prototype chỉ một lần

Xem cấu hình:

```java
@Bean
@Scope("prototype")
TaskUnit taskUnit() {
    return new TaskUnit();
}

@Bean
TaskProcessor taskProcessor(TaskUnit taskUnit) {
    return new TaskProcessor(taskUnit);
}
```

`taskProcessor` là singleton mặc định; Spring chỉ gọi factory method `taskProcessor(TaskUnit)` khi tạo singleton. Tại thời điểm ấy, BeanFactory cung cấp **một** TaskUnit prototype. Processor giữ đúng reference đó:

```text
BeanDefinition taskUnit, scope=prototype
           |
           | một dependency request khi tạo taskProcessor
           v
      TaskUnit instance #1 -----------+
                                       |
                                       v
                           TaskProcessor singleton
                                       |
                  method run() lần 1 / lần 2 / lần 3
                                       |
                                       v
                            vẫn dùng TaskUnit #1
```

Vì vậy nếu `TaskProcessor.run()` kỳ vọng một task state object **mới cho mỗi lần chạy**, constructor-inject prototype trực tiếp là sai semantics.

### 7.1. Điều này không làm prototype đổi thành singleton

Bean definition `taskUnit` **vẫn thuộc prototype scope**. Những lần `context.getBean(TaskUnit.class)` khác có thể tạo TaskUnit #2, #3. Nhưng object mà singleton processor **đã giữ** không tự bị thay mới khi chạy method.

### 7.2. Sửa bằng ObjectProvider

```java
import org.springframework.beans.factory.ObjectProvider;

final class TaskProcessor {
    private final ObjectProvider<TaskUnit> taskUnits;

    TaskProcessor(ObjectProvider<TaskUnit> taskUnits) {
        this.taskUnits = taskUnits;
    }

    void run() {
        TaskUnit fresh = taskUnits.getObject();
        fresh.process();
    }
}
```

Đoạn minh họa cần class `TaskUnit` có method `process()`. Giờ processor giữ provider; từng lần `getObject()` thực hiện **một bean lookup mới**, phù hợp với prototype.

### 7.3. ObjectFactory và jakarta.inject.Provider

Spring có `ObjectFactory<T>` với `getObject()`. `ObjectProvider<T>` mở rộng khả năng lookup thêm `getIfAvailable()`, `getIfUnique()`, streams và những phương thức khác. `jakarta.inject.Provider<T>` có `get()` nếu tích hợp dependency tương ứng.

Dùng loại nào dựa trên semantics thực. Đừng inject `ApplicationContext` vào tất cả business services chỉ để gọi `getBean` bằng chuỗi: đó là service-locator coupling và khó test.

### 7.4. @Lookup method injection

Spring còn hỗ trợ `@Lookup` cho lookup-method injection:

```java
abstract class BatchRunner {
    public void run() {
        TaskUnit fresh = newTaskUnit();
        fresh.process();
    }

    @Lookup
    protected abstract TaskUnit newTaskUnit();
}
```

Đây là đoạn minh họa cần Spring tạo/enhance `BatchRunner` theo cơ chế method injection. **Không áp dụng tùy tiện cho object tạo bởi `@Bean` factory method hoặc object `new` ngoài container**: Spring cần kiểm soát instantiation/enhancement; method/class final hoặc constraints khác có thể làm injection không hoạt động. Trong nhiều thiết kế, `ObjectProvider<T>` đơn giản và minh bạch hơn.

### 7.5. Prototype qua scoped proxy

Nếu Spring inject một **scoped proxy** cho prototype vào singleton, *mỗi lời gọi method qua proxy* có thể tạo một target prototype mới. Đây là semantics khác với “một prototype mới cho mỗi business operation gồm nhiều lời gọi method”.

Nếu một operation cần gọi `prepare()` và `execute()` **trên cùng TaskUnit**, gọi hai method độc lập qua prototype scoped proxy có thể tác động **hai targets khác nhau**. Hãy dùng provider để lấy object một lần ở đầu operation rồi gọi cả hai methods trên cùng reference.

## 8. Ví dụ runnable Java 17: singleton, prototype và provider

Ví dụ hoàn chỉnh này dùng **Spring Framework 6.2.19**, Java 17 và Maven, không cần Spring Boot, server, database hay network ở runtime.

Nó chứng minh:

1. `SharedCatalog` singleton trả cùng reference.
2. Một eager singleton `FixedConsumer` đã được inject một prototype `TaskUnit` lúc context refresh.
3. Hai lần `getBean(TaskUnit.class)` tạo các prototype instances mới.
4. `DynamicConsumer` singleton giữ `ObjectProvider<TaskUnit>` để lấy prototype mới mỗi lần gọi.
5. `RareTool` là lazy **singleton**: chưa tạo sau refresh, được tạo tại first use, rồi trả cùng reference.
6. Cả singleton, prototype và provider đều xuất phát từ **những bean definitions duy nhất cho từng bean name**.

### 8.1. Cấu trúc

```text
scope-recipe-demo/
├── pom.xml
└── src/main/java/demo/
    └── ScopeRecipeDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>scope-recipe-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

### 8.3. Java source đầy đủ

Tạo `src/main/java/demo/ScopeRecipeDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public class ScopeRecipeDemo {

    public static final class Sequence {
        private final AtomicInteger next = new AtomicInteger();

        public int nextId() {
            return next.incrementAndGet();
        }
    }

    public static final class SharedCatalog {
        public String name() {
            return "catalog-ready";
        }
    }

    public static final class TaskUnit {
        private final int id;

        public TaskUnit(int id) {
            this.id = id;
        }

        public int id() {
            return id;
        }
    }

    public static final class FixedConsumer {
        private final TaskUnit taskUnit;

        public FixedConsumer(TaskUnit taskUnit) {
            this.taskUnit = taskUnit;
        }

        public int assignedId() {
            return taskUnit.id();
        }

        public TaskUnit taskUnit() {
            return taskUnit;
        }
    }

    public static final class DynamicConsumer {
        private final ObjectProvider<TaskUnit> tasks;

        public DynamicConsumer(ObjectProvider<TaskUnit> tasks) {
            this.tasks = tasks;
        }

        public int newTaskId() {
            return tasks.getObject().id();
        }
    }

    public static final class LazyMarker {
        private boolean created;

        public void mark() {
            created = true;
        }

        public boolean created() {
            return created;
        }
    }

    public static final class RareTool {
        public RareTool(LazyMarker marker) {
            marker.mark();
        }

        public String label() {
            return "rare-ready";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Sequence sequence() {
            return new Sequence();
        }

        @Bean
        public SharedCatalog sharedCatalog() {
            return new SharedCatalog();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public TaskUnit taskUnit(Sequence sequence) {
            return new TaskUnit(sequence.nextId());
        }

        @Bean
        public FixedConsumer fixedConsumer(TaskUnit taskUnit) {
            return new FixedConsumer(taskUnit);
        }

        @Bean
        public DynamicConsumer dynamicConsumer(
                ObjectProvider<TaskUnit> tasks) {
            return new DynamicConsumer(tasks);
        }

        @Bean
        public LazyMarker lazyMarker() {
            return new LazyMarker();
        }

        @Bean
        @Lazy
        public RareTool rareTool(LazyMarker marker) {
            return new RareTool(marker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            SharedCatalog catalog1 =
                    context.getBean(SharedCatalog.class);
            SharedCatalog catalog2 =
                    context.getBean(SharedCatalog.class);
            FixedConsumer fixed =
                    context.getBean(FixedConsumer.class);
            DynamicConsumer dynamic =
                    context.getBean(DynamicConsumer.class);
            LazyMarker marker =
                    context.getBean(LazyMarker.class);

            System.out.println("catalog=" + catalog1.name());
            System.out.println("singletonSame=" + (catalog1 == catalog2));
            System.out.println("fixedTaskId=" + fixed.assignedId());

            TaskUnit task2 = context.getBean(TaskUnit.class);
            TaskUnit task3 = context.getBean(TaskUnit.class);
            System.out.println("directPrototypeIds=" +
                    task2.id() + "," + task3.id());
            System.out.println("directPrototypeDifferent=" +
                    (task2 != task3));
            System.out.println("fixedStillFirst=" +
                    (fixed.assignedId() == 1));

            System.out.println("providerPrototypeIds=" +
                    dynamic.newTaskId() + "," + dynamic.newTaskId());

            System.out.println("lazyBeforeLookup=" +
                    marker.created());
            RareTool rare1 = context.getBean(RareTool.class);
            RareTool rare2 = context.getBean(RareTool.class);
            System.out.println("rare=" + rare1.label());
            System.out.println("lazyAfterLookup=" +
                    marker.created());
            System.out.println("lazySingletonSame=" +
                    (rare1 == rare2));
        }
    }
}
```

### 8.4. Chạy

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.ScopeRecipeDemo
```

Dự án có thể cần Maven tải dependencies lần đầu; chương trình không phụ thuộc network khi đã có các JAR cần thiết.

### 8.5. Output dự kiến

Các dòng **do chương trình `System.out.println` in**, không tính logs tùy môi trường:

```text
catalog=catalog-ready
singletonSame=true
fixedTaskId=1
directPrototypeIds=2,3
directPrototypeDifferent=true
fixedStillFirst=true
providerPrototypeIds=4,5
lazyBeforeLookup=false
rare=rare-ready
lazyAfterLookup=true
lazySingletonSame=true
```

### 8.6. Vì sao các ID chính xác?

`Sequence` là singleton chứa `AtomicInteger` riêng của **context**. Tạo bean `FixedConsumer` eager yêu cầu `TaskUnit` prototype, nên Spring gọi factory `taskUnit(sequence)` lần đầu và cấp **id=1**.

Không có bean eager nào khác cần TaskUnit ngay ở startup. `DynamicConsumer` chỉ giữ `ObjectProvider<TaskUnit>`, không lấy prototype khi constructor/factory method của dynamic consumer chạy.

Sau refresh, hai lời gọi `context.getBean(TaskUnit.class)` tạo instances mới **id=2** và **id=3**. Hai lần `dynamic.newTaskId()` gọi provider và tạo tiếp **id=4** và **id=5**.

`fixed.assignedId()` vẫn là 1 vì singleton FixedConsumer giữ reference TaskUnit đầu tiên. Đây là hiện tượng **singleton lifetime dài hơn prototype lifetime được inject** chứ không phải Spring vô tình làm prototype trở thành singleton.

### 8.7. Vì sao RareTool không được tạo trước?

`RareTool` là singleton lazy được khai báo bằng `@Lazy` trên `@Bean`. Không bean eager nào trong demo cần RareTool. `LazyMarker` eager có thể được tạo trước, nhưng việc có marker **không** tự kích hoạt RareTool. Vì vậy `marker.created()` là false trước `getBean(RareTool.class)` và true sau đó; hai lookups trả cùng singleton.

### 8.8. Tại sao output không dựa vào thứ tự bean không có dependency?

Sequence IDs chỉ cấp trong `TaskUnit` factory. Để FixedConsumer ra đời cần tạo một TaskUnit; các TaskUnit khác chỉ được yêu cầu bằng những lời gọi `getBean` và `provider.getObject` rõ ràng trong `main`. Các bean khác không tạo TaskUnit, nên không phụ thuộc thứ tự creation của chúng. Không có static global IDs hoặc background threads.

### 8.9. Điểm quan trọng của @Configuration(proxyBeanMethods=false)

Factory methods nhận dependencies qua **tham số**, không direct-call factory khác. Đây là cách đảm bảo BeanFactory quyết định bean identity/scope. Nếu viết `return new FixedConsumer(taskUnit(sequence()))` trong lite configuration, các factory method calls Java trực tiếp có thể tạo objects ngoài container, phá semantics mà demo đang dạy.

## 9. Scope và dependency injection: chú ý vòng đời dài/ngắn

Một vấn đề kiến trúc phổ biến là **long-lived bean** giữ reference tới **short-lived bean**:

```text
Singleton Service
      |
      | inject trực tiếp lúc singleton được tạo
      v
Prototype / Request / Session Bean
      |
      +--> Object cụ thể được giữ qua nhiều lượt gọi
```

Điều này gây hai loại bug:

1. **Prototype được dùng lại ngoài ý định:** singleton chỉ nhận một prototype object lúc khởi tạo.
2. **Request/session scope không hợp lệ hoặc stale:** singleton không thể trực tiếp giữ một request-specific object rồi dùng cho mọi HTTP requests/users.

### 9.1. Nếu dependency thực sự thuộc cùng vòng đời

Có thể inject trực tiếp. Ví dụ singleton service giữ singleton repository là hợp lý; hai object cùng ranh giới container.

### 9.2. Nếu dependency ngắn hơn consumer

Bạn có thể:

- Dùng `ObjectProvider<T>` rồi resolve target tại từng operation.
- Inject **scoped proxy** thay vì target object trực tiếp.
- Truyền request-specific data thành **method parameters** từ controller/use-case layer.
- Tái thiết kế interface để tách mutable state ra khỏi singleton service.
- Dùng method injection nếu phù hợp nhưng chú ý constraints.

### 9.3. Cách tốt cho request-specific business data

Thay vì lưu `currentUserId` trong singleton service field:

```java
// Phản ví dụ:
class UnsafeOrderService {
    private String currentUserId;

    public void setCurrentUserId(String userId) {
        currentUserId = userId;
    }
}
```

nên truyền dữ liệu đến service method:

```java
class OrderService {
    public String createOrder(String userId, String sku) {
        return userId + ":" + sku;
    }
}
```

Đây là hai thiết kế minh họa riêng. Stateless service không chứa per-request mutable state nên dễ chia sẻ giữa threads và tests hơn.

## 10. Request scope: một bean trong một HTTP request

Trong một web-aware `ApplicationContext` có HTTP request active, bean `request` có **một target trên mỗi request**. Hai lần dùng cùng bean trong một request nhận cùng target; request tiếp theo có target mới. `@RequestScope` mặc định dùng class-based scoped proxy, nên singleton controller có thể giữ proxy và gọi đến target hiện tại khi xử lý HTTP.

~~~java
@Component
@RequestScope
class RequestTrace {
    private final String traceId =
            java.util.UUID.randomUUID().toString();

    String id() {
        return traceId;
    }
}
~~~

Đoạn code chỉ minh họa một bean trong môi trường Spring Servlet; cần các import `Component`, `RequestScope` và component scanning phù hợp. Giá trị `traceId` được khởi tạo một lần cho mỗi target, nên các lần gọi `id()` trong cùng HTTP request trả cùng kết quả. Bài chuyên về web scope có ví dụ HTTP hoàn chỉnh để kiểm chứng.

## 11. Session scope: theo HTTP session, không theo mỗi user account vĩnh viễn

`@SessionScope` gắn một target với **một HTTP session**: nhiều requests giữ cùng session ID thường dùng chung target, session khác có target riêng. Một user có thể mở nhiều sessions; nhiều tab cùng cookie có thể dùng chung một session. Với state mutable, cần xem xét đồng thời giữa các HTTP requests cùng session, memory pressure, timeout và serialization/persistence khi hạ tầng yêu cầu.

## 12. Application scope khác singleton scope

`@ApplicationScope` lưu target trong **`ServletContext`**; `singleton` thuộc **bean definition/container**. Một ServletContext có thể liên quan nhiều Spring contexts, còn các JVM/pods khác nhau không tự chia sẻ bộ nhớ. Cả hai scope đều có thể bị nhiều threads truy cập, nên giữ state immutable/stateless hoặc bảo vệ mutation phù hợp.

## 13. WebSocket scope

`websocket` quản lý target theo **WebSocket/STOMP session** trong messaging infrastructure phù hợp, khác HTTP request/session. Mỗi kết nối có state riêng; nhiều messages của cùng kết nối có thể truy cập cùng target và vẫn cần thiết kế concurrency. Spring 6.x có thể khai báo `@Scope("websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)` khi đã cấu hình STOMP broker; annotation `@WebSocketScope` thuộc Spring 7.x.

## 14. Scoped proxy: cùng reference ở consumer, target thay theo scope

Singleton consumer có vòng đời dài hơn request/session bean. **Scoped proxy** cho phép giữ một proxy reference ổn định nhưng mỗi lần gọi method sẽ resolve target theo request/session đang active. Với `ScopedProxyMode.INTERFACES`, injection point dùng interface; `TARGET_CLASS` tạo subclass proxy và chịu giới hạn của `final` class/method. Không truy cập target request ngoài active request.

~~~java
// Snippet trong web-aware Spring configuration; RequestIdentityImpl implements RequestIdentity.
@Bean
@Scope(value = "request", proxyMode = ScopedProxyMode.INTERFACES)
RequestIdentity requestIdentity() {
    return new RequestIdentityImpl();
}
~~~

Proxy được inject vào singleton; giữa hai HTTP requests, reference proxy có thể giống nhưng target khác. Tránh cache target thực trong một singleton field.

## 15. ObjectProvider và scoped proxy: chọn theo ý nghĩa

- **Scoped proxy**: consumer gọi collaborator như một interface/class thông thường; proxy chọn target ở thời điểm method call, phù hợp request/session bean.
- **`ObjectProvider<T>`**: consumer chủ động gọi `getObject()` khi cần, rồi có thể giữ target trong một biến cục bộ xuyên suốt một business operation.
- Với **prototype scoped proxy**, hai method calls có thể tạo hai prototype targets khác nhau. Nếu `prepare()` và `commit()` phải cùng một instance, lấy prototype qua provider **một lần** rồi gọi cả hai methods trên nó.

## 16. Lifecycle: Spring không hủy prototype như singleton

Spring khởi tạo singleton/prototype theo bean lifecycle, nhưng với prototype **không tự thực thi destruction callbacks** khi `ApplicationContext.close()`; caller hoặc một owner riêng phải `close()` các resource cần thiết. Singleton được Spring quản lý destruction theo context khi có callback hợp lệ. Request/session targets theo lifecycle của web scope được hỗ trợ, không phải cứ hết HTTP request là toàn bộ bean Spring biến mất.

Ví dụ: một prototype `AutoCloseable` lấy bằng provider có thể dùng `try (var session = provider.getObject()) { session.run(); }` khi phù hợp. Đây là đoạn định hướng cho bài về prototype cleanup, nơi giải thích callback và xử lý exception chi tiết.

## 17. Khi tạo object: eager/lazy áp dụng tới scopes khác nhau thế nào?

`ApplicationContext.refresh()` thường pre-instantiate **regular non-lazy singleton beans**. Prototype không bị bulk instantiate khi đọc definition, request/session targets cần active web scope.

Nhưng dependency có thể kéo object khác được tạo khi cần:

```text
Eager singleton Processor
   |
   +---- constructor requires prototype Worker
   |                    |
   |                    +--> Tạo Worker khi Processor được tạo
   |
   +---- provider<Worker>
                        |
                        +--> Chưa tạo Worker cho tới getObject()
```

Đừng kết luận “mình đánh `@Lazy` lên bean nên nó sẽ không được tạo ở startup”. Một eager bean constructor-inject bean ấy vẫn có thể kéo nó lên, kể cả khi target là singleton lazy.

### Bean scope không phải creation order

Hai singleton độc lập có thể được tạo theo thứ tự tùy cơ chế bootstrap. Nếu A cần B, Spring resolve B theo dependency graph. `@Order` không phải singleton startup ordering; nó thường dùng để sắp xếp collection injections.

### @DependsOn và scope

`@DependsOn("x")` cho biết dependent bean cần bean `x` được initialized trước, không làm x đổi scope, cũng không biến prototype thành singleton. Một eager bean có `dependsOn` có thể làm bean lazy được tạo sớm.

## 18. FactoryBean và bean scope: hai tầng semantics

`FactoryBean<T>` là Spring contract để bean factory object cung cấp một product object. Đừng nhầm với một `@Bean` factory method.

Khi một bean definition định nghĩa FactoryBean:

- BeanFactory quản lý **factory object** theo scope của definition.
- `getBean("name")` thường trả **product** được factory tạo.
- `getBean("&name")` trả **FactoryBean object**.
- `FactoryBean.isSingleton()` mô tả product singleton semantics từ factory.
- Product/cache/lifecycle còn phụ thuộc loại factory, bean definition, implementation và BeanFactory.

Bởi vậy không thể chỉ nhìn `scope="singleton"` trên FactoryBean definition rồi kết luận mọi lượt `getBean("name")` chắc chắn có product identity như singleton bean thông thường. Hãy xem **cả factory bean scope và product semantics**.

Đây là chủ đề nâng cao; với một class service bình thường khai báo bằng `@Bean`, singleton/prototype vẫn hoạt động theo các quy tắc ở mục 4–8.

## 19. Custom scope: tự định nghĩa ranh giới instance

Khi sáu scopes chuẩn chưa khớp domain, Spring cho phép triển khai `org.springframework.beans.factory.config.Scope`, rồi đăng ký với BeanFactory.

Interface `Scope` có các hợp đồng chính:

- `Object get(String name, ObjectFactory<?> objectFactory)`: tìm hoặc tạo object theo ranh giới scope.
- `Object remove(String name)`: loại object khỏi scope.
- `void registerDestructionCallback(String name, Runnable callback)`.
- `Object resolveContextualObject(String key)`.
- `String getConversationId()`.

Một scope custom cần quyết định **storage**, **isolation boundary**, **cleanup** và **concurrency semantics**. Ví dụ tenant scope phải bảo đảm không để dữ liệu tenant A lẫn sang tenant B.

### 19.1. Đăng ký scope theo API

```java
ConfigurableBeanFactory factory = ...;
factory.registerScope("tenant", tenantScope);
```

Đây là đoạn minh họa, yêu cầu `tenantScope` implementation của `Scope` và đúng giai đoạn BeanFactory configuration. Với ApplicationContext, custom scope thường được đăng ký thông qua `CustomScopeConfigurer` hoặc cấu hình bootstrap phù hợp, **trước khi** những bean thuộc scope đó cần resolve.

### 19.2. XML định nghĩa scope

```xml
<bean id="tenantWorkspace"
      class="example.TenantWorkspace"
      scope="tenant"/>
```

Sẽ không hoạt động nếu container chưa đăng ký scope tên `tenant`. Không phải cứ viết một chuỗi scope mới trong XML thì Spring tự biết quản lý nó.

### 19.3. Custom scope không đồng nghĩa ThreadLocal an toàn

Tenant context trên `ThreadLocal` có thể bị stale/leak khi thread pools tái sử dụng threads. Với reactive processing hoặc virtual threads, correlation và context propagation còn phải được thiết kế đúng. Không tự viết scope storage đơn giản dựa vào global map keyed bằng user string mà chưa giải quyết lifecycle, logout/eviction, concurrent access và memory cleanup.

## 20. Bean aliases, multiple names và scopes

Một bean có thể có nhiều tên thông qua aliases:

```xml
<bean id="catalogClient" class="example.CatalogClient"/>
<alias name="catalogClient" alias="legacyCatalogClient"/>
```

Hai tên ánh xạ tới **cùng bean definition**, không tự tạo hai instances. Nếu definition là singleton, thông thường:

```java
context.getBean("catalogClient")
        == context.getBean("legacyCatalogClient")
```

là true.

Còn nếu bạn đăng ký **hai bean definitions riêng** cùng class nhưng tên khác, chúng có scope/lifecycle riêng:

```java
@Bean("eastClient")
Client eastClient() {
    return new Client("east");
}

@Bean("westClient")
Client westClient() {
    return new Client("west");
}
```

Dù cả hai là singleton, không vì cùng class mà Spring gộp chúng thành một object.

### Injection theo type có thể nhập nhằng

Hai `Client` bean definitions khác nhau khiến `getBean(Client.class)` hoặc constructor injection theo type có thể bị ambiguity. Dùng `@Qualifier`, `@Primary` hoặc tên bean rõ. Scope **không phải tiêu chí chọn một candidate chính xác** nếu có nhiều beans cùng type.

## 21. Định nghĩa inner bean và scope

Trong Spring XML:

```xml
<bean id="processor" class="example.Processor">
    <constructor-arg>
        <bean class="example.Policy"/>
    </constructor-arg>
</bean>
```

Bean `example.Policy` ở trong thẻ `<constructor-arg>` là một **inner bean definition**. Nó không có top-level bean name công khai để `getBean("policy")`. Inner beans thường được tạo như object thuộc ownership của outer bean, và không dùng làm shared singleton độc lập.

Nếu nhiều consumer cùng cần một policy singleton, đăng ký named bean riêng rồi dùng `ref`:

```xml
<bean id="policy" class="example.Policy"/>

<bean id="processor" class="example.Processor">
    <constructor-arg ref="policy"/>
</bean>
```

Đừng lạm dụng inner bean để xây một “singleton toàn cục” vì tên XML thẻ giống nhau. Definition nesting và bean scope phải được hiểu riêng.

## 22. Web scope examples: ví dụ minh họa đúng ngữ cảnh

Một singleton `RequestLoggingService` có thể inject interface `RequestInfo` được đăng ký bằng `@Scope(value="request", proxyMode=ScopedProxyMode.INTERFACES)`. Trong HTTP request đang active, hai lần gọi `requestInfo.correlationId()` tìm cùng request target; HTTP request khác tìm target khác. Plain `AnnotationConfigApplicationContext` trong CLI không tự có HTTP scope. Để chạy thật và so sánh cookie/request/application state, xem các bài web scopes, web-aware context và annotation ở các mục chuyên biệt trong chương.

## 23. Debug các lỗi do scope

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Hai `getBean()` cho cùng bean name trả cùng object | Bean scope singleton | Expected; kiểm tra `scope` definition |
| Hai `getBean()` cho prototype trả hai object | Prototype semantics | Expected |
| Prototype inject vào singleton bị dùng lại liên tục | Dependency chỉ resolve một lần khi singleton được tạo | `ObjectProvider`/factory per operation |
| Request bean dùng trong CLI báo thiếu scope | Không có web-aware context | Dùng web scope chỉ trong web app hoặc custom mock/register scope cho test |
| `Scope 'request' is not active` | Không có request bound vào thread/dispatch tại lúc target được gọi | Đặt lookup trong request hợp lệ |
| Một session bean bị truy cập nhầm giữa hai users | Shared mutable target/proxy/session binding sai | Sửa scope ownership, không cache target trong singleton |
| Cùng một scoped proxy reference nhưng ID target đổi | Proxy giữ identity, còn target thay theo request | Đây là expected behavior |
| Prototype scoped proxy state “mất” giữa hai methods | Mỗi method invocation có thể tới target mới | Dùng provider lấy target một lần |
| Scope proxy lỗi với final class/method | Proxying limitations | Dùng interface-based proxy hoặc provider |
| Prototype resource không được đóng khi context close | Spring không quản lý destroy callbacks của prototype như singleton | Caller tự cleanup |
| Memory tăng theo số sessions | Session state quá lớn/chưa timeout/invalidation | Thiết kế cleanup, tránh giữ object lớn |
| Singleton field chứa request ID của request trước | Per-request state bị lưu trong long-lived bean | Truyền method parameter hoặc dùng request scope đúng |
| Một class nhưng hai singleton instances | Hai bean definitions hoặc hai contexts | Kiểm tra names/aliases/context boundaries |
| `@Lazy` singleton tạo sau nhưng vẫn same identity | Lazy chỉ thay thời điểm, không đổi scope | Expected |
| Bean prototype xuất hiện ở startup | Eager singleton yêu cầu prototype dependency | Xem constructor/factory method parameters |
| Custom scope không tìm thấy | Chưa đăng ký scope name | `CustomScopeConfigurer`/`registerScope` trước lookup |
| `NoUniqueBeanDefinitionException` | Nhiều candidates cùng type | Qualifier/Primary/tên bean |
| Method `@Bean` bị gọi trực tiếp tạo object ngoài BeanFactory | `proxyBeanMethods=false`/manual config instance | Dùng BeanFactory lookup/injection parameters |
| FactoryBean product identity khó hiểu | Factory vs product scope semantics khác | Kiểm tra `FactoryBean.isSingleton()` |
| Production-only bug với WebSocket session | Messaging infrastructure/scope lifecycle khác tests | Test đúng WebSocket/STOMP setup |

### Quy trình debug

1. Xác minh bean **name/alias** và definition thực tế đã được đăng ký.
2. Tìm `@Scope`/`@RequestScope`/`@SessionScope` hoặc XML `scope="..."`.
3. Xác định **container** nào đang tạo bean (parent, child, test context, app context).
4. Xác định lookup là `getBean`, constructor injection, provider hay scoped proxy.
5. Nếu singleton giữ prototype: kiểm tra injection xảy ra **một lần** hay per-use lookup.
6. Nếu bean web-scoped: xác minh request/session/WebSocket scope đang active.
7. Tách identity của proxy khỏi target instance.
8. Kiểm tra scope-specific cleanup và object ownership.
9. Không gọi `getBean` khi chỉ muốn kiểm tra bean đã được tạo — lookup có thể instantiate.
10. Test với đúng profile/web environment và concurrency/lifecycle nếu có.

## 24. Kiểm thử semantics của scope

### 24.1. Test singleton identity

```java
SharedCatalog a = context.getBean(SharedCatalog.class);
SharedCatalog b = context.getBean(SharedCatalog.class);
if (a != b) {
    throw new AssertionError("SharedCatalog is not singleton");
}
```

Đây là đoạn bổ sung đặt bên trong `main` của project mục 8, khi `context` đang mở.

### 24.2. Test prototype multiplicity

```java
TaskUnit first = context.getBean(TaskUnit.class);
TaskUnit second = context.getBean(TaskUnit.class);
if (first == second) {
    throw new AssertionError("Expected distinct prototype objects");
}
```

Đừng assert literal IDs nếu test khác cũng đã lấy prototype trước; kiểm tra identity và scope contract quan trọng hơn số thứ tự được gắn tùy ngữ cảnh.

### 24.3. Test singleton giữ prototype một lần

```java
FixedConsumer fixed = context.getBean(FixedConsumer.class);
TaskUnit stored = fixed.taskUnit();

if (fixed.taskUnit() != stored) {
    throw new AssertionError("FixedConsumer changed its dependency");
}
```

Nội dung quan trọng là FixedConsumer đã giữ cùng reference. Việc nó cần object mới mỗi lần hay không là **yêu cầu thiết kế**, không phải lỗi Spring.

### 24.4. Test provider tạo prototype mỗi lần

```java
ObjectProvider<TaskUnit> units =
        context.getBeanProvider(TaskUnit.class);
TaskUnit a = units.getObject();
TaskUnit b = units.getObject();
if (a == b) {
    throw new AssertionError("Prototype provider returned same object");
}
```

### 24.5. Test request scope phải mô phỏng HTTP lifecycle

Với Spring web test infrastructure, mock request/session phải được bind đúng vào `RequestContextHolder` hoặc mock web context tương ứng khi kiểm tra target resolution. Tạo plain `AnnotationConfigApplicationContext` rồi trực tiếp `getBean` một request-scoped target không phải integration test web đúng nghĩa.

### 24.6. Test cleanup

Với singleton có `destroyMethod`, đóng context và assert callback phù hợp. Với prototype, viết test chứng minh application caller chịu trách nhiệm close, không đợi context cleanup giúp.

### 24.7. Test scope bằng API BeanFactory mà không tạo target

```java
String scope =
        context.getBeanFactory()
               .getBeanDefinition("taskUnit")
               .getScope();
```

Với `@Scope("prototype")`, scope string là `prototype`. Với scope mặc định, BeanDefinition scope field có thể chưa được ghi explicit (chuỗi rỗng biểu thị default singleton), vì vậy cần hiểu API contract; đừng assert `getScope().equals("singleton")` cho mọi bean mặc định.

## 25. Câu hỏi thường gặp

### Singleton bean có phải được tạo đúng một lần trên toàn JVM?

Không. Nó là singleton **theo bean definition trong mỗi container**. Hai contexts độc lập có thể có hai instances. Hai definitions cùng Java class trong một context cũng có thể có hai singleton instances.

### Prototype có nghĩa một bean mới mỗi HTTP request?

Không. Nó thường là bean mới **mỗi yêu cầu lấy instance** từ BeanFactory. Muốn một bean tồn tại xuyên lookups trong một HTTP request, chọn request scope.

### @Lazy có phải một scope?

Không. `@Lazy` điều chỉnh **thời điểm pre-instantiation**, không đổi instance multiplicity. Lazy singleton vẫn chỉ có một managed singleton instance khi được tạo.

### Bean scope có thay đổi dependencies không?

Scope quyết định khi/how nhiều object được tạo theo bean definition. Dependency injection vẫn cần resolve object phù hợp; nhưng thời điểm/identity được truyền cho consumer chịu ảnh hưởng scope.

### Tại sao prototype bị tạo lúc startup dù không bulk pre-instantiate?

Vì eager singleton có thể **cần prototype làm dependency**, dẫn tới tạo một instance ngay lúc singleton được dựng.

### Một singleton inject prototype có tự thay instance mỗi lần method chạy?

Không. Constructor/property injection diễn ra tại thời điểm tạo singleton, nên reference đã inject thường giữ nguyên. Dùng provider/factory/scoped proxy với semantics được thiết kế nếu cần dynamic instance.

### @RequestScope sử dụng được trong chương trình console không?

Không tự động. Cần web-aware context và active request. Plain ApplicationContext thường không có scope đó, trừ khi bạn tự register/mock scope cho test với ý thức rõ.

### Scoped proxy có cùng reference qua nhiều requests không?

Có thể. Consumer singleton giữ **cùng proxy instance**, nhưng target mà proxy giải quyết theo request/session có thể khác nhau.

### Scoped proxy prototype và ObjectProvider có giống nhau không?

Không. Prototype scoped proxy có thể tạo target mới **mỗi method call**, còn provider cho phép bạn **chủ động lấy một target** bằng `getObject()` rồi dùng cùng target trong một operation.

### Prototype bean có được Spring tự close khi context close không?

Theo semantics Spring thông thường, **không**. Spring gọi init callbacks nhưng không theo dõi và thực hiện mọi prototype destruction callbacks; caller phải quản lý cleanup.

### Application scope có luôn giống singleton?

Không. Application scope ràng theo ServletContext; singleton ràng theo một Spring IoC container. Khi có nhiều contexts chia sẻ một ServletContext, khác biệt có thể quan trọng.

### Spring có tự đăng ký thread scope?

Không. `SimpleThreadScope` tồn tại nhưng **không đăng ký mặc định**, và có lifecycle caveats quan trọng.

### Scope có phải dùng để đảm bảo thread safety?

Không. Scope chỉ nói về **sharing/lifespan**. Nhiều threads có thể dùng cùng singleton hoặc session-scoped object, nên mutable state vẫn cần concurrency design.

### Mọi đối tượng tạo bằng new trong @Bean đều không được Spring quản lý?

Object được **return từ `@Bean` factory method do container gọi** sẽ trở thành managed bean theo definition đó. Nhưng objects phụ được tạo bằng `new` rồi giữ bên trong mà không trả về/đăng ký riêng **không tự thành Spring beans**. Phân biệt rõ “factory method trả object” và “manual new không qua BeanFactory”.

## 26. Bài tập có đáp án

### Bài 1 — Một definition, nhiều objects

`TaskUnit` được khai báo bằng `@Bean @Scope("prototype")`. Hai lần `context.getBean(TaskUnit.class)` có mấy instances thông thường?

**Đáp án:** Hai instances khác nhau từ một bean definition. Scope quy định cơ chế tạo/lookup, không nhân bản definition.

### Bài 2 — Singleton per-container

Hai `AnnotationConfigApplicationContext` độc lập cùng đăng ký `@Bean Cache cache()`. `Cache` singleton ở mỗi context. Hai references có chắc giống nhau không?

**Đáp án:** Không. Mỗi container quản lý singleton riêng.

### Bài 3 — Hai bean names cùng class

Một config có `@Bean("a") Client clientA()` và `@Bean("b") Client clientB()`, cả hai singleton. Có đúng một Client instance trong container không?

**Đáp án:** Không. Hai definitions riêng có thể có hai singleton objects riêng.

### Bài 4 — Lazy singleton

`@Bean @Lazy ExpensiveClient client()` có phải prototype không?

**Đáp án:** Không. Mặc định vẫn singleton; `@Lazy` chỉ thay thời điểm container chủ động tạo.

### Bài 5 — Prototype inject vào singleton

Eager singleton `BatchService` constructor nhận `TaskUnit` prototype. Gọi `batchService.process()` 10 lần có tự nhận 10 TaskUnits không?

**Đáp án:** Không. Constructor được gọi khi singleton tạo và nhận một prototype tại thời điểm đó, rồi giữ reference.

### Bài 6 — ObjectProvider

`BatchService` phải tạo một TaskUnit mới cho mỗi job. Nêu cách giải quyết.

**Đáp án:** Inject `ObjectProvider<TaskUnit>` rồi trong `processOneJob` gọi `getObject()` đúng một lần, sử dụng returned TaskUnit cho cả job.

### Bài 7 — Prototype scoped proxy

Một workflow gọi `proxy.prepare()` rồi `proxy.commit()`. Proxy trỏ prototype scope. Có bảo đảm cùng target object không?

**Đáp án:** Không. Mỗi method call qua prototype scoped proxy có thể nhận target mới. Nếu cần chung state, dùng provider lấy một instance trước.

### Bài 8 — Request scope

Hai lookup cùng bean trong một HTTP request, rồi hai lookup trong HTTP request khác. Có bao nhiêu target request-scoped objects thông thường?

**Đáp án:** Một target cho mỗi request, tổng hai targets giữa hai requests, nếu target được yêu cầu trong cả hai.

### Bài 9 — Session scope

Hai HTTP requests thuộc cùng session sử dụng `CartState` session-scoped. Có thường lấy cùng target không?

**Đáp án:** Có trong một HTTP session còn active, theo scope contract; khác session có target riêng.

### Bài 10 — Scope ở CLI

`@RequestScope` bean được tra cứu trong plain `AnnotationConfigApplicationContext` không có web request. Tại sao có thể lỗi?

**Đáp án:** Request scope chưa được đăng ký/active; web scopes yêu cầu web-aware context và active request lifecycle.

### Bài 11 — Application scope

Spring có hai child WebApplicationContexts cùng liên kết tới một ServletContext. Có thể có khác biệt identity của `application` và `singleton` beans không?

**Đáp án:** Có. Application scope theo ServletContext; singleton theo container/definition. Xem hierarchy, bean names và web infrastructure thực tế.

### Bài 12 — Lifecycle prototype

`@Bean(destroyMethod="close") @Scope("prototype")` tạo TempBuffer. Context đóng có chắc gọi close cho mọi buffer không?

**Đáp án:** Không theo lifecycle prototype mặc định; client/owner chịu trách nhiệm cleanup.

### Bài 13 — Proxy và target

Một singleton service giữ request-scoped proxy; hai requests gọi service. Có thể reference proxy giống nhau nhưng target khác nhau không?

**Đáp án:** Có. Proxy reference ổn định; target được resolve theo active scope của từng request.

### Bài 14 — Custom scope

Developer viết `@Scope("tenant")` nhưng chưa đăng ký Scope implementation. Có hoạt động không?

**Đáp án:** Không khi tenant bean được yêu cầu; cần đăng ký scope `tenant` trước lookup.

### Bài 15 — Thread safety

Một singleton có `int count` và `count++` khi 100 requests đồng thời. Scope singleton tự đảm bảo kết quả đúng không?

**Đáp án:** Không. Cần thread-safe mutable state hoặc thiết kế stateless.

### Bài 16 — Alias

`<bean id="reportClient".../>` có `<alias name="reportClient" alias="oldReportClient"/>`. Hai tên có tạo hai singleton objects không?

**Đáp án:** Không. Alias trỏ cùng bean identity.

### Bài 17 — Prototype vs request

Bạn muốn một `RequestContext` duy nhất trong mỗi HTTP request bất kể code lookup bao nhiêu lần. Chọn `prototype` hay `request`?

**Đáp án:** Chọn request scope. Prototype tạo mới mỗi bean lookup, không giữ một target cho toàn HTTP request.

### Bài 18 — Scope và order

`@Order(1)` trên singleton A, `@Order(2)` trên singleton B. Có nói object A được tạo trước B không?

**Đáp án:** Không. `@Order` thường ảnh hưởng sắp thứ tự collection/candidates, không điều khiển thứ tự tạo singleton.

### Bài 19 — Kết quả chương trình

Trong demo mục 8, vì sao `fixedTaskId=1` nhưng `directPrototypeIds=2,3`?

**Đáp án:** FixedConsumer eager được inject prototype đầu tiên trong startup; các lần `getBean` trong main tạo hai instances tiếp theo.

### Bài 20 — Dynamic ids

Vì sao hai lần `dynamic.newTaskId()` tạo IDs 4 và 5?

**Đáp án:** Consumer giữ provider, không giữ một TaskUnit cụ thể; mỗi `getObject()` tạo prototype mới dùng cùng singleton Sequence counter.

### Bài 21 — Lazy marker

`RareTool` được đánh `@Lazy` và không bean eager nào cần nó. `marker.created()` là gì ngay sau refresh?

**Đáp án:** False. Sau lần đầu `getBean(RareTool.class)`, constructor đánh dấu true; lookup thứ hai trả lại singleton.

### Bài 22 — Scope leak

Singleton giữ trực tiếp `UserPreferences` session target từ request của Alice, rồi xử lý request của Bob. Rủi ro gì?

**Đáp án:** Dùng nhầm/stale state giữa sessions, thậm chí lộ dữ liệu. Inject scoped proxy/provider hoặc truyền dữ liệu request/session đúng boundary; không cache target.

## 27. Checklist thực hành

- [ ] Đã phân biệt bean definition với object instance.
- [ ] Biết mỗi bean definition có scope riêng.
- [ ] Hiểu singleton là **per bean/per container**.
- [ ] Không nhầm singleton với static/global GoF Singleton.
- [ ] Không coi singleton là mặc định thread-safe.
- [ ] Prototype tạo object mới trên mỗi bean lookup.
- [ ] Không nhầm prototype với per HTTP request.
- [ ] Biết singleton inject prototype **chỉ một lần** ở creation/injection.
- [ ] Dùng ObjectProvider/factory khi cần prototype theo mỗi operation.
- [ ] Nếu dùng prototype scoped proxy, đã xác minh semantics theo từng method call.
- [ ] Phân biệt `@Lazy` timing với `@Scope` multiplicity.
- [ ] Hiểu eager bean có thể tạo lazy dependency sớm.
- [ ] Dùng đúng web-aware context cho request/session/application/websocket scopes.
- [ ] Không lookup request-scoped target ngoài request active.
- [ ] Không giữ concrete short-lived target trong long-lived singleton.
- [ ] Scope proxy mode phù hợp interface/class, tránh final proxy limitations.
- [ ] Không lưu mutable request/session data vào singleton fields.
- [ ] Session state có lifecycle, timeout, size và concurrency controls.
- [ ] Application-scoped object không bị nhầm với per-context singleton.
- [ ] Custom scope có storage, conversation key, destruction và cleanup rõ.
- [ ] Không xem thread scope là tự động có sẵn.
- [ ] Prototype resources được caller/owner cleanup.
- [ ] Không dùng direct `new` để kỳ vọng Spring scope/lifecycle.
- [ ] Không direct-call `@Bean` methods trong lite configuration để nhận managed object.
- [ ] Bean aliases và multiple bean definitions được phân biệt rõ.
- [ ] Test identity, scope cardinality, first use, web scope và cleanup.
- [ ] Nếu dùng FactoryBean, đã phân biệt factory vs product scope.
- [ ] Không dùng scope làm “sửa tạm” cho dependency cycle hoặc sai business ownership.

## Tổng kết

**Scope quyết định quan hệ giữa bean definition và thể hiện**: cùng một metadata recipe có thể gắn với **một managed singleton object**, tạo **nhiều prototype instances**, hoặc trả target được quản lý theo **HTTP request, session, ServletContext, WebSocket session hay custom boundary**.

Bốn điều nên ghi nhớ:

1. **Spring singleton = một managed object theo bean definition trong một IoC container**, không phải một object duy nhất cho mọi class/global JVM.
2. **Prototype = tạo instance mới theo mỗi bean lookup**, nhưng singleton inject prototype trực tiếp **chỉ nhận một instance lúc dependency được resolve**.
3. **Scope web = target thay theo active web lifecycle**; dùng scoped proxy, provider hoặc method parameters cho dependencies ngắn hạn trong long-lived consumers.
4. **Lifecycle gắn với scope**: Spring quản lý destruction của singleton theo context, nhưng với prototype thông thường caller phải tự cleanup; `@Lazy` không đổi những semantics này.

Khi thiết kế, hãy chọn scope theo **ownership, lifespan, sharing và concurrency** của object; chọn injection mechanism theo **thời điểm cần collaborator**; rồi kiểm chứng bằng context tests thay vì suy từ Java class name hoặc annotation riêng lẻ.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): sáu scopes chuẩn, singleton/prototype, scoped proxy, web scopes, custom scope và lifecycle.
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): bean scope khác eager/lazy behavior.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property wiring, dependency graph.
- [Spring Framework 6.2 — Method Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-method-injection.html): @Lookup, prototype trong singleton, hạn chế lookup injection.
- [Spring Framework 6.2 — @Scope API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Scope.html): scope names và ScopedProxyMode.
- [Spring Framework 6.2 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): deferred/dynamic bean lookup.
- [Spring Framework 6.2 — Scope SPI](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/Scope.html): custom scope contract.
