# Tự gọi nội bộ qua `this` và nguyên nhân bỏ qua advice trong Spring AOP

## 1. Mục tiêu của bài học

Khi sử dụng **Spring AOP dựa trên proxy**, một phương thức có thể nhận advice khi được gọi từ một bean khác nhưng **không nhận advice** khi được gọi qua `this` ngay trong lớp của nó. Đây được gọi là **self-invocation** (lời gọi nội bộ lên chính đối tượng).

Ví dụ:

```java
public void placeOrder() {
    this.saveOrder(); // Lời gọi nội bộ, không quay lại Spring AOP proxy
}

public void saveOrder() {
    // Có thể là phương thức mà một advice nhắm tới
}
```

Nếu `placeOrder()` được gọi **qua proxy** thì advice dành cho `placeOrder()` vẫn có thể chạy. Tuy nhiên, khi code đã đi vào **target object** và gọi `this.saveOrder()`, lời gọi thứ hai **không đi qua proxy**, nên advice dành riêng cho `saveOrder()` không được kích hoạt ở lần gọi đó. Nếu client bên ngoài gọi `proxy.saveOrder()` thì advice của `saveOrder()` lại có thể chạy bình thường.

Sau bài học, bạn sẽ:

1. Diễn giải được **ranh giới proxy** trong Spring AOP và lý do self-invocation bỏ qua advice.
2. Dự đoán đúng output khi gọi cùng một method từ bên ngoài và từ bên trong target.
3. Phân biệt self-invocation với các lý do khác khiến advice không chạy (pointcut, bean registration, `final` method, object tạo bằng `new`).
4. Sửa code theo hướng **tách trách nhiệm thành các Spring beans** và gọi xuyên qua proxy.
5. Hiểu những đánh đổi khi dùng **self-injection** hoặc `AopContext.currentProxy()`, và hệ quả thực tế với transaction/cache/async ở chế độ proxy.

Bài chỉ nói về **hành vi Spring Aspect/Spring AOP**; không trình bày lại các khái niệm Aspect tổng quát.

## 2. Hai đối tượng quan trọng: proxy và target

Giả sử ứng dụng có bean `OrderService` phù hợp với một advisor từ lớp `@Aspect`. Spring có thể trả về một **AOP proxy** cho client thay vì trả trực tiếp target.

```text
Lời gọi từ bean/client khác
           |
           v
   OrderService proxy
           |
           +--> Pointcut/advisor khớp phương thức ngoài?
           |         |
           |         +--> chạy advice tương ứng
           |
           v
      Target object
           |
           +--> logic trong method
                  |
                  +--> this.innerMethod()
                              |
                              v
                        Target method trực tiếp
                        (KHÔNG quay lại proxy)
```

Ở đường gọi đầu tiên, client giữ **tham chiếu proxy**. Spring có cơ hội xây chuỗi interceptor/advice cho method được gọi qua proxy. Nhưng bên trong target, `this` trỏ đến **đối tượng đang thực thi logic nghiệp vụ**, không phải một lời gọi mới tới proxy Spring AOP. Việc gọi method qua tham chiếu `this` không tự quay về proxy để xét advisor lần nữa.

Trong Spring AOP, **advice được chèn tại đường gọi đi qua proxy**, không phải tự động được chèn vào mọi lệnh gọi Java bên trong class. Spring dùng `@AspectJ` để mô tả pointcut/advice nhưng lúc chạy vẫn là **Spring AOP proxy-based** nếu không cấu hình weaving riêng.

### 2.1. Vì sao pointcut khớp vẫn không chạy?

Xem ví dụ:

```java
@Before("execution(* example.OrderService.saveOrder(..))")
public void auditSaveOrder() {
    System.out.println("advice: saveOrder");
}
```

Biểu thức pointcut có thể **khớp chính xác** với `OrderService.saveOrder()`. Điều đó mới trả lời câu hỏi “method nào nằm trong phạm vi advisor?”. Còn để advice thực thi, invocation cần đi qua **Spring AOP proxy đang mang advisor ấy**.

`this.saveOrder()` gọi trực tiếp method trên target. Do đó:

- Pointcut **không nhất thiết sai**.
- Aspect **không nhất thiết chưa được đăng ký**.
- Bean **không nhất thiết thiếu proxy**.
- Đúng hơn, **lời gọi cụ thể đã bỏ qua ranh giới proxy**.

Đây là sự khác nhau giữa **khả năng áp dụng advisor** và **lời gọi thật sự đi qua advisor**.

## 3. So sánh các đường gọi

Giả sử cả `outer()` và `inner()` đều public, target là Spring bean đã có AOP proxy và pointcut advisor nhắm tới `inner()`.

| Lời gọi | Có đi qua proxy khi bước vào `inner()`? | Advice dành riêng cho `inner()` có cơ hội chạy? |
| --- | --- | --- |
| Bean khác gọi `service.inner()` trên tham chiếu Spring cung cấp | **Có** | **Có**, nếu pointcut và điều kiện khác khớp |
| Bean khác gọi `service.outer()`, trong `outer()` dùng `this.inner()` | **Không** cho lời gọi `inner()` | **Không** ở lời gọi `inner()` nội bộ |
| Trong `outer()` gọi `inner()` không ghi `this` | **Không** | **Không**; lời gọi ngầm cũng là `this.inner()` |
| Bên ngoài gọi `new Service().inner()` | **Không** | **Không** vì instance không được Spring proxy |
| `outer()` gọi `anotherBean.inner()` bằng tham chiếu bean đã được proxy | **Có** tại bean thứ hai | **Có**, nếu advisor khớp |
| Trong target dùng `AopContext.currentProxy()` rồi gọi method của proxy | **Có**, khi proxy được expose và gọi hợp lệ | **Có**; nhưng cách này gắn chặt business code với Spring AOP |
| Trong target inject chính proxy của mình rồi gọi qua tham chiếu đó | **Có**, nếu Spring thực sự inject proxy phù hợp | **Có**; song có chi phí thiết kế/cấu hình vòng phụ thuộc |

**Phân biệt rõ:** Khi `outer()` được gọi qua proxy, advice nhắm riêng vào `outer()` **vẫn có thể chạy**. Chỉ advice tương ứng với `inner()` bị bỏ qua tại bước gọi nội bộ. Không nên nói ngắn gọn “self-invocation làm tất cả AOP của `outer()` biến mất”.

## 4. Ví dụ Java 17+ chạy được: quan sát ba con đường

Ví dụ dùng **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, **Java 17+**, Maven và `@EnableAspectJAutoProxy`. Không dùng HTTP server hoặc cơ sở dữ liệu để chỉ quan sát ranh giới Spring AOP.

### 4.1. Cấu trúc project

```text
spring-aop-self-invocation/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── OrderService.java
    ├── PersistenceService.java
    ├── WorkflowService.java
    ├── TraceAspect.java
    └── Main.java
```

### 4.2. Maven: `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-aop-self-invocation</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Trong ứng dụng thực tế, nên quản lý version `spring-*` qua **Spring Framework BOM** hoặc Spring Boot BOM để tránh lệch phiên bản. Ví dụ này khai báo bản cụ thể để có một project độc lập dễ thử nghiệm.

### 4.3. Target tự gọi nội bộ: `OrderService.java`

```java
package example;

public class OrderService {

    public void submit() {
        System.out.println("order: submit");
        this.persist();
    }

    public void persist() {
        System.out.println("order: persist");
    }
}
```

`submit()` gọi `this.persist()` bên trong **cùng target class**. Không có Spring bean lookup hay tham chiếu proxy ở giữa hai method.

### 4.4. Target khác để minh họa hướng sửa: `PersistenceService.java`

```java
package example;

public class PersistenceService {

    public void persist() {
        System.out.println("storage: persist");
    }
}
```

### 4.5. Bean điều phối gọi sang bean khác: `WorkflowService.java`

```java
package example;

public class WorkflowService {

    private final PersistenceService persistenceService;

    public WorkflowService(PersistenceService persistenceService) {
        this.persistenceService = persistenceService;
    }

    public void submit() {
        System.out.println("workflow: submit");
        persistenceService.persist();
    }
}
```

Khác với `this.persist()` trong `OrderService`, tham chiếu `persistenceService` sẽ nhận **bean do Spring cung cấp**. Nếu bean ấy được proxy, lời gọi có đường đi qua proxy.

### 4.6. Hai advice được khai báo trong Spring aspect: `TraceAspect.java`

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("execution(* example.OrderService.persist(..))")
    public void beforeOrderPersist() {
        System.out.println("advice: order persist");
    }

    @Before("execution(* example.PersistenceService.persist(..))")
    public void beforeStoragePersist() {
        System.out.println("advice: storage persist");
    }
}
```

Hai pointcut đều nhắm tới method tên `persist()`, nhưng **khác target class**. Điều này tránh phụ thuộc thứ tự giữa nhiều advice cho cùng một invocation và giúp stdout dễ dự đoán.

### 4.7. Cấu hình Spring: `AppConfig.java`

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public PersistenceService persistenceService() {
        return new PersistenceService();
    }

    @Bean
    public WorkflowService workflowService(PersistenceService persistenceService) {
        return new WorkflowService(persistenceService);
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

Lưu ý:

- `TraceAspect` có `@Aspect` nhưng không cần `@Component` vì được **đăng ký bằng `@Bean`**.
- `@EnableAspectJAutoProxy` bật Spring AOP auto-proxy cho context; `proxyTargetClass=true` ép dùng **class-based proxy** cho các target phù hợp.
- Cả `OrderService` và `PersistenceService` có method match pointcut và có thể nhận proxy.
- Đổi từ JDK sang CGLIB **không chữa self-invocation**. Chọn CGLIB ở đây chỉ giúp ví dụ dùng trực tiếp concrete type và giải thích rõ điểm này.

### 4.8. Chạy thử: `Main.java`

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService order = context.getBean(OrderService.class);
            PersistenceService storage = context.getBean(PersistenceService.class);
            WorkflowService workflow = context.getBean(WorkflowService.class);

            System.out.println("order is proxy: " + AopUtils.isAopProxy(order));
            System.out.println("storage is proxy: " + AopUtils.isAopProxy(storage));

            System.out.println("-- call 1: external direct --");
            order.persist();

            System.out.println("-- call 2: self invocation --");
            order.submit();

            System.out.println("-- call 3: another bean --");
            workflow.submit();
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

**Các dòng do các method trong ví dụ in ra, theo đúng thứ tự:**

```text
order is proxy: true
storage is proxy: true
-- call 1: external direct --
advice: order persist
order: persist
-- call 2: self invocation --
order: submit
order: persist
-- call 3: another bean --
workflow: submit
advice: storage persist
storage: persist
```

### 4.9. Phân tích kết quả

**Lời gọi 1 — `order.persist()`:** `order` là tham chiếu tới **AOP proxy** được Spring trả về. Proxy nhận invocation `persist()`, tìm advice phù hợp trong `TraceAspect`, in `advice: order persist`, rồi gọi target và in `order: persist`.

**Lời gọi 2 — `order.submit()`:** `submit()` được gọi qua proxy, nhưng không có advice nào trong ví dụ nhắm tới `submit()`. Khi target bắt đầu thực thi `submit()`, dòng `order: submit` xuất hiện. Lệnh `this.persist()` bên trong target gọi trực tiếp `persist()`; vì **không đi qua AOP proxy lần thứ hai**, dòng `advice: order persist` **không xuất hiện**. Dòng `order: persist` vẫn xuất hiện — method nghiệp vụ **không bị bỏ qua**, chỉ **advice** bị bỏ qua.

**Lời gọi 3 — `workflow.submit()`:** `WorkflowService` giữ tham chiếu Spring đã inject cho `PersistenceService`. Khi nó gọi `persistenceService.persist()`, invocation đi **qua proxy của một bean khác** nên advice `beforeStoragePersist()` chạy. Đây là cách sửa thiết kế phổ biến: đặt hành vi cần advice vào **Spring service khác** và gọi qua dependency injection.

Kết quả minh họa **chính xác một nguyên nhân bỏ qua advice** mà không sử dụng transaction/cache/database. Nếu bạn bổ sung advisor khác hoặc thay cấu hình, output có thể khác và cần kiểm chứng lại.

## 5. CGLIB vẫn gặp self-invocation: tại sao?

Một hiểu nhầm thường gặp: “JDK proxy chỉ can thiệp interface, vậy bật CGLIB là `this.inner()` sẽ được advice.” Điều này **sai đối với Spring AOP proxy-based**.

Về mặt loại proxy:

- **JDK dynamic proxy:** proxy thực thi interface; caller từ bên ngoài gọi interface method trên proxy.
- **CGLIB proxy:** proxy là subclass có thể can thiệp các method override được; caller bên ngoài gọi method trên proxy.

Nhưng ở cả hai dạng, khi interceptor đã đưa lời gọi vào **target thực hiện business logic**, lời gọi nội bộ qua `this` ở target **không vượt qua proxy boundary**. Spring documentation nêu rõ self-invocation bằng tham chiếu `this`, tường minh hoặc ngầm định, bỏ qua advice.

Ví dụ trong mục 4 đã ép `proxyTargetClass = true`, nghĩa là dùng CGLIB — nhưng `this.persist()` **vẫn không chạy** `beforeOrderPersist()`.

**Ngoài ra, một method `private` hoặc `final` không được Spring AOP CGLIB advice qua cơ chế override.** Đó là một giới hạn *khác* với self-invocation. Với self-invocation, ngay cả khi `inner()` là `public` và hoàn toàn proxy được, đường gọi nội bộ vẫn bỏ qua proxy.

## 6. Cách sửa được ưu tiên: tách bean và gọi qua DI

### 6.1. Thiết kế ban đầu

```java
@Service
public class OrderService {

    public void submit() {
        validate();
        this.persist();
    }

    public void persist() {
        // Code dự kiến được advice riêng.
    }

    private void validate() {
        // ...
    }
}
```

Đây là **snippet minh họa trong ứng dụng Spring có component scanning**, không phải chương trình Java độc lập. Nếu advisor chỉ match `persist()`, lời gọi nội bộ ở đây không kích hoạt advice.

### 6.2. Tách phương thức cần advisor sang bean khác

```java
@Service
public class OrderPersistenceService {

    public void persist() {
        // Logic cần được Spring AOP advice.
    }
}
```

```java
@Service
public class OrderService {

    private final OrderPersistenceService persistence;

    public OrderService(OrderPersistenceService persistence) {
        this.persistence = persistence;
    }

    public void submit() {
        validate();
        persistence.persist(); // Đi qua tham chiếu Spring đã inject.
    }

    private void validate() {
        // ...
    }
}
```

Các snippet trên cần import `org.springframework.stereotype.Service` và cấu hình component scanning/AOP phù hợp. Spring sẽ tạo proxy cho `OrderPersistenceService` khi có advisor match; tham số constructor nhận tham chiếu do Spring cung cấp.

**Vì sao cách này hiệu quả?** Tại điểm `persistence.persist()`, đối tượng được gọi là **dependency bean khác**, có thể là proxy. Lời gọi qua tham chiếu này đi vào Spring AOP interceptor chain rồi mới đến target.

Các lợi ích đi kèm:

- Ranh giới giữa **điều phối** và **tác vụ được advice** rõ hơn.
- Tránh phụ thuộc trực tiếp vào `AopContext`.
- Dễ kiểm thử đơn vị vì `OrderPersistenceService` có thể được mock/fake qua constructor.
- Tránh self-injection và một số vấn đề circular dependency.
- Có thể áp dụng cho những boundary mà `@Transactional`, `@Cacheable`, `@Async` hoặc custom `@Aspect` cùng yêu cầu lời gọi qua proxy.

**Điều kiện:** Dependency phải là **bean Spring thực sự được proxy**, không phải object tự `new`; pointcut vẫn phải match đúng method đó. Không phải cứ tách class là Spring tự có advice.

### 6.3. Tách đúng ranh giới chức năng, không tách máy móc

Không nên tách mọi method private chỉ để chạy AOP. Chỉ cân nhắc tạo bean riêng khi method có **hợp đồng độc lập** cần lời gọi qua proxy, ví dụ một thao tác transactional độc lập, tác vụ async hoặc nghiệp vụ cần audit riêng. Phương thức tính toán nội bộ bình thường có thể tiếp tục là method `private` trong cùng lớp.

## 7. Lựa chọn thứ hai: inject tham chiếu proxy của chính bean

Spring documentation đề cập **self injection** như một lựa chọn khi không tiện tách bean. Ý tưởng là để class giữ **tham chiếu proxy do Spring cung cấp**, sau đó gọi `self.inner()` thay vì `this.inner()`.

Ví dụ minh họa:

```java
@Service
public class OrderService {

    private final ObjectProvider<OrderService> selfProvider;

    public OrderService(ObjectProvider<OrderService> selfProvider) {
        this.selfProvider = selfProvider;
    }

    public void submit() {
        selfProvider.getObject().persist();
    }

    public void persist() {
        // Advice nhắm tới persist() khi gọi qua proxy.
    }
}
```

Đây là **snippet minh họa**, cần import `org.springframework.beans.factory.ObjectProvider` và `org.springframework.stereotype.Service`. Nó không nằm trong dự án chạy độc lập ở mục 4.

`ObjectProvider` trì hoãn việc tìm bean cho đến khi `submit()` được gọi. Nếu context đã khởi tạo xong và `OrderService` được proxy thích hợp, `selfProvider.getObject()` có thể trả **tham chiếu proxy** rồi `persist()` được can thiệp.

**Các điều kiện/rủi ro cần kiểm tra:**

1. Phải có **đúng bean** được resolve từ provider. Nếu nhiều `OrderService` bean cùng type, cần qualifier hoặc cơ chế chọn bean.
2. Không gọi provider quá sớm trong constructor/`@PostConstruct`: lúc đó vòng đời proxy có thể chưa hoàn thành.
3. Tránh circular dependency khó debug, đặc biệt trong Spring Boot hiện đại vốn mặc định hạn chế circular references.
4. Nếu bean được JDK proxy theo interface, đừng kỳ vọng proxy assignable cho concrete class. Khi dùng self proxy theo interface, chọn provider type là **interface được proxy expose**.
5. Self-injection khiến class nhận biết sự hiện diện của container/proxy và thường kém rõ ràng hơn việc tách service.

Nói cách khác, self-injection có thể được dùng trong trường hợp có chủ đích, nhưng **không nên là lời giải mặc định** cho một boundary thiết kế không rõ ràng.

## 8. Lựa chọn cuối cùng: `AopContext.currentProxy()`

Spring cung cấp API `AopContext.currentProxy()` để truy xuất proxy hiện tại theo ngữ cảnh thread khi việc **expose proxy** đã được bật. Tuy nhiên, Spring documentation cảnh báo đây là phương án **không được khuyến khích**, vì business code bị gắn chặt với Spring AOP.

Đoạn minh họa:

```java
// Trong một class OrderService phù hợp, method được gọi qua proxy:
public void submit() {
    ((OrderService) AopContext.currentProxy()).persist();
}
```

Cần import `org.springframework.aop.framework.AopContext`. Với Spring Java configuration, phải bật:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)
```

**Đây là hai snippet bổ sung, không phải chương trình độc lập.** Chúng còn yêu cầu `submit()` ban đầu được gọi **qua proxy** trong một invocation mà Spring expose proxy, và `OrderService` là kiểu có thể cast từ proxy (ví dụ CGLIB trong cấu hình trên).

Các hạn chế:

- `AopContext.currentProxy()` có thể ném `IllegalStateException` khi không có proxy hiện hành được expose (ví dụ gọi từ một target tự `new`, gọi ngoài proxy context hoặc `exposeProxy=false`).
- Bật `exposeProxy=true` tạo thêm coupling và có chi phí; **không giải quyết những lời gọi không đi vào proxy ngay từ đầu**.
- Nếu là **JDK proxy**, cast proxy thành implementation class là sai; cần cast về một interface được expose.
- Nó không biến `private`/`final` method thành join point có thể advice theo Spring proxy.
- Không khuyến nghị dùng API này chỉ để “vá” mọi self-invocation. Khi có thể, hãy **refactor để tránh self-invocation cần advice**.

## 9. Vì sao lấy bean từ ApplicationContext trong method không phải giải pháp tốt?

Có thể gặp kiểu code:

```java
public void submit() {
    applicationContext.getBean(OrderService.class).persist();
}
```

Với context/proxy đúng, lời gọi từ bean được tìm thấy có thể đi qua proxy. Nhưng cách này đưa **service locator** trực tiếp vào business method, làm code phụ thuộc vào `ApplicationContext`, khó unit test và khó nhận diện vòng phụ thuộc. Nếu dùng JDK proxy, việc tra bean theo concrete type còn có thể thất bại.

Ưu tiên constructor injection của một **bean khác có trách nhiệm riêng**. Nếu bắt buộc giữ cùng class, dùng một self-reference được quản lý và tài liệu hóa rõ, thay vì rải `getBean(...)` khắp phương thức nghiệp vụ.

## 10. Liên hệ với `@Transactional`, `@Cacheable` và `@Async`

Các tính năng Spring sau thường dựa vào infrastructure advisors/proxies ở **proxy mode**, dù không yêu cầu bạn tự viết `@Aspect`. Vì vậy chúng cùng chịu vấn đề **self-invocation**.

### 10.1. `@Transactional`: không kích hoạt interceptor mới ở lời gọi nội bộ

Ví dụ minh họa:

```java
@Service
public class PaymentService {

    public void checkout() {
        this.savePayment(); // Không đi qua transaction proxy.
    }

    @Transactional
    public void savePayment() {
        // Mong đợi transaction bắt đầu khi gọi savePayment().
    }
}
```

Nếu gọi `checkout()` từ ngoài, mà `checkout()` **không có transaction riêng** và không có transaction nào khác đang active, annotation `@Transactional` trên `savePayment()` sẽ **không khiến transaction được mở cho lời gọi nội bộ này**. Đó là vì transaction interceptor không được gọi ở bước `this.savePayment()`.

**Sắc thái quan trọng:** Nếu `checkout()` đã được gọi qua một transaction proxy và **có transaction đang active**, code trong `savePayment()` vẫn có thể chạy **bên trong transaction hiện hữu**. Nhưng metadata `@Transactional` **riêng của `savePayment()` không được đánh giá cho invocation nội bộ**, nên không tự mở một boundary transaction mới theo thuộc tính của nó.

Ví dụ:

```java
@Transactional
public void checkout() {
    this.savePayment();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void savePayment() {
    // ...
}
```

Khi `checkout()` đi qua proxy, transaction bên ngoài được mở. Nhưng `this.savePayment()` **không đi qua interceptor mới**, do đó cấu hình `REQUIRES_NEW` tại `savePayment()` **không tạo transaction mới và không suspend transaction ngoài** trong đường gọi này.

Cần import `org.springframework.transaction.annotation.Transactional` và `org.springframework.transaction.annotation.Propagation`; để hoạt động thực tế còn cần transaction management, transaction manager và resources tương ứng. Đây chỉ là đoạn minh họa, **không** thuộc project Maven độc lập ở mục 4.

**Cách xử lý phù hợp:** Di chuyển thao tác `REQUIRES_NEW` sang một Spring bean khác, inject bean đó và gọi qua transaction proxy. Kiểm thử bằng database/transaction manager thật để xác nhận propagation, commit và rollback.

### 10.2. `@Cacheable`

```java
@Service
public class ProductService {

    public Product refresh(String id) {
        return this.findById(id); // Bỏ qua caching proxy tại bước nội bộ.
    }

    @Cacheable("products")
    public Product findById(String id) {
        // Đọc dữ liệu.
    }
}
```

Nếu `refresh()` gọi `this.findById(id)`, cache interceptor dành cho `findById` không chạy qua bước gọi ấy. Chuyển thao tác truy vấn cache sang một Spring bean khác và gọi qua bean proxy khi cần giữ caching semantics. Snippet cần các class và cache configuration tương ứng, không chạy độc lập.

### 10.3. `@Async`

```java
@Service
public class NotificationService {

    public void register() {
        this.sendEmail(); // Gọi đồng bộ trong cùng target.
    }

    @Async
    public void sendEmail() {
        // Tác vụ dự định chạy qua async interceptor.
    }
}
```

Trong proxy mode, lời gọi nội bộ `this.sendEmail()` **không đi qua async proxy** nên annotation `@Async` trên method này không tự chuyển execution sang executor. Nếu `register()` không có cơ chế async riêng thì `sendEmail()` chạy đồng bộ ngay trên thread gọi. Muốn async đúng, tách sang một Spring bean được `@EnableAsync`/Boot infrastructure xử lý, gọi qua proxy và kiểm chứng thread/exception semantics.

**Ranh giới học tập:** Những ví dụ transaction/cache/async chỉ làm rõ hệ quả của **Spring AOP proxy boundary**, không thay thế các bài học chuyên sâu về transaction, caching hay concurrency.

## 11. Các lời gọi trong vòng đời khởi tạo

Self-invocation không chỉ xuất hiện trong method nghiệp vụ thông thường. Ví dụ:

```java
@PostConstruct
public void init() {
    this.loadData();
}
```

Vì `@PostConstruct` chạy trong vòng đời khởi tạo bean, không nên dựa vào AOP proxy đã hoàn chỉnh để đảm bảo advice cho `loadData()`. Tương tự, gọi method có advice từ **constructor** hoặc từ code được thực thi trước khi container hoàn tất bean lifecycle rất dễ bỏ qua cơ chế interception.

Nếu cần tác vụ khởi động có advice, cân nhắc kích hoạt **sau khi context đã sẵn sàng** thông qua một bean điều phối/phù hợp với lifecycle, rồi gọi bean đích qua Spring reference. Với Spring Boot, có thể dùng `ApplicationRunner`/`CommandLineRunner` khi phù hợp, nhưng cần kiểm tra thứ tự khởi động và transaction/resources.

Không chuyển `this.loadData()` sang `@PostConstruct` rồi kỳ vọng lời gọi sẽ “đi qua proxy” chỉ nhờ có `@Aspect`.

## 12. Self-invocation khác gì với các lỗi AOP khác?

| Triệu chứng | Nguyên nhân cần kiểm tra | Dấu hiệu để phân biệt |
| --- | --- | --- |
| `inner()` chạy advice khi gọi từ ngoài nhưng không chạy khi gọi từ `outer()` | **Self-invocation** qua `this` | Cùng Spring bean/proxy; chỉ đường gọi khác |
| Mọi lời gọi tới `inner()` đều không chạy advice | Aspect chưa thành bean, AOP chưa bật hoặc pointcut không khớp | Kiểm tra aspect bean, auto-proxy config, advisor |
| `AopUtils.isAopProxy(service) == false` | Bean chưa có proxy hoặc đang dùng instance ngoài Spring | Kiểm tra `context.getBean`, registration, advisor match |
| Method `private` hoặc `final` không nhận advice qua class-based Spring proxy | Giới hạn proxy/override method | Gọi từ ngoài cũng không cứu được method không proxy được |
| `inner()` gọi qua proxy nhưng advice vẫn không chạy | Pointcut, method signature, runtime args hoặc advisor không khớp | Kiểm tra `@Before`, class/method, proxy type, runtime match |
| Object tạo bằng `new Service()` không nhận advice | Instance ngoài container, không được Spring bọc proxy | Gọi qua object đó luôn không vào Spring AOP |
| Aspect bean tồn tại nhưng chính aspect không có proxy | Hành vi Spring AOP bình thường | Aspect bean là **nguồn advisor**, không phải target auto-proxy thông thường |
| JDK proxy không cast được sang implementation | Runtime type là interface-based proxy | Inject/call qua interface hoặc dùng class-based proxy có kiểm chứng |
| Đổi `proxyTargetClass = true` mà self-invocation vẫn bỏ qua advice | JDK/CGLIB đều là proxy-based | Cần thay **đường gọi**, không chỉ chiến lược proxy |

### Checklist chẩn đoán nhanh

1. **Lấy bean từ Spring:** `context.getBean(...)` hoặc constructor injection, không tự `new`.
2. **Kiểm tra proxy:** `AopUtils.isAopProxy(bean)`; nhớ rằng proxy tồn tại **không chứng minh** mọi method có advice.
3. **Kiểm tra đường gọi:** dùng debug/log đặt tại `outer()` và `inner()`; có đoạn `this.inner()` hoặc `inner()` ngầm định không?
4. **So sánh:** gọi `inner()` trực tiếp từ caller ngoài trên Spring proxy. Nếu advice xuất hiện ở đường này nhưng mất ở đường nội bộ thì self-invocation là ứng viên nguyên nhân rất mạnh.
5. **Kiểm tra pointcut/advisor:** class, method, visibility, runtime matching, JDK/CGLIB; đừng thay đổi biểu thức khi vấn đề thật nằm ở đường đi.
6. **Refactor và thử lại:** đưa method cần advice qua Spring bean khác, gọi bằng dependency injection, rồi xác minh stdout/transaction/cache/async thực tế.
7. **Test hồi quy:** kiểm tra hành vi nghiệp vụ ngoài việc chỉ đếm log advice; đặc biệt với transaction propagation, rollback và dữ liệu.

## 13. Có nên dùng AspectJ weaving để xử lý self-invocation?

**Spring AOP proxy-based** và **AspectJ weaving** là hai cơ chế khác nhau:

| Spring AOP proxy-based | AspectJ compile-time/load-time weaving |
| --- | --- |
| Tạo proxy để chặn lời gọi đi từ client qua proxy | Thay đổi/đan bytecode của class theo cấu hình weaving |
| Self-invocation `this.inner()` bỏ qua proxy nên advice của `inner()` không chạy | Không chịu giới hạn self-invocation theo cách đó vì advice không phụ thuộc vào việc đi qua Spring proxy |
| Phù hợp cho đa số nhu cầu advice trên Spring-managed beans | Có thể xử lý join point/phạm vi rộng hơn nhưng cần công cụ và cấu hình khác |
| `@EnableAspectJAutoProxy` **không phải** lệnh bật AspectJ weaving | Cần AspectJ compiler hoặc weaver, cấu hình weaving tương ứng |

Spring Framework documentation xác nhận compile-time hoặc load-time AspectJ weaving **không gặp self-invocation issue như Spring AOP proxies**, vì hành vi advice nằm trong bytecode chứ không phụ thuộc một wrapper proxy.

Tuy nhiên, **chỉ thêm `aspectjweaver` hoặc `@Aspect` vào classpath không có nghĩa đã bật weaving**. Trong hầu hết trường hợp nên ưu tiên sửa Spring bean boundary (tách service) thay vì thay toàn bộ cơ chế AOP chỉ vì một lời gọi nội bộ.

Đặc biệt với `@Transactional`, chế độ `AdviceMode.ASPECTJ`/weaving có yêu cầu `spring-aspects` và thiết lập AspectJ khác; nó không tương đương `@EnableAspectJAutoProxy` và không được tự động kích hoạt chỉ nhờ Spring Boot starter AOP/AspectJ. Bài này không hướng dẫn cấu hình weaving đầy đủ vì trọng tâm là Spring proxy boundary.

## 14. Tình huống kiểm tra kiến thức

**Tình huống A.** `service.outer()` được gọi qua Spring AOP proxy. Trong `outer()`, code viết `inner()` thay vì `this.inner()`. Có chạy advice nhắm vào `inner()` không?

**Đáp án:** Không, nếu đó là lời gọi method cùng target: `inner()` viết ngắn vẫn là self-invocation trên `this`, không quay lại proxy.

**Tình huống B.** Đặt `@EnableAspectJAutoProxy(proxyTargetClass=true)` để chuyển JDK proxy sang CGLIB. Điều đó có làm `this.inner()` chạy advice không?

**Đáp án:** Không. CGLIB vẫn là Spring AOP proxy; self-invocation bên trong target tiếp tục bỏ qua proxy.

**Tình huống C.** `outer()` đã được advice và chạy bên trong transaction. Nó gọi `this.inner()`, trong khi `inner()` có `@Transactional(REQUIRES_NEW)`. Có tự tạo transaction mới không?

**Đáp án:** Không đối với lời gọi nội bộ ở proxy mode. `inner()` có thể chạy trong transaction hiện hữu của `outer()`, nhưng propagation `REQUIRES_NEW` của `inner()` không được transaction interceptor đánh giá cho invocation này.

**Tình huống D.** Chuyển `inner()` sang `InnerService` và inject `InnerService` vào `OuterService`. Lúc gọi `innerService.inner()` có chắc chắn advice chạy không?

**Đáp án:** Chỉ khi `InnerService` là Spring bean có proxy/advisor phù hợp, method có thể được advice và caller thực sự gọi qua tham chiếu proxy. Tách class **chưa đủ** nếu không có đăng ký bean/AOP đúng.

**Tình huống E.** `AopUtils.isAopProxy(service)` trả `true`, `this.inner()` vẫn không có log. Điều này có mâu thuẫn không?

**Đáp án:** Không. `isAopProxy` kiểm tra **tham chiếu service** là proxy; lời gọi `this.inner()` trong target không đi qua tham chiếu proxy ấy.

## 15. Nguồn tham khảo Spring chính thức

- [Spring Framework — Proxying Mechanisms (Spring 6.2)](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): giải thích trực tiếp self-invocation qua `this`, các lựa chọn refactor/self injection/`AopContext` và khác biệt với weaving.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy`, AspectJ library trên classpath, auto-proxying Spring beans.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction proxy mode, ranh giới external method calls và self-invocation.
- [Spring Framework — Understanding Transaction Proxy Infrastructure](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): vai trò AOP proxies và transaction interceptors.
- [Spring Framework — AopContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/framework/AopContext.html): yêu cầu expose proxy và `currentProxy()`.
- [Spring Framework — AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): nhận diện Spring AOP proxy và các tiện ích liên quan.
