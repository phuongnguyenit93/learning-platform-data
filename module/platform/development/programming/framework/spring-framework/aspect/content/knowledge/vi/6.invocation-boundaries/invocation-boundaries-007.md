# Đối tượng không được Spring quản lý và giới hạn của proxy tự động trong Spring AOP

## 1. Ranh giới quan trọng nhất: Spring AOP chỉ tự bọc Spring bean

Spring AOP hoạt động chủ yếu bằng cách **tạo proxy cho những Spring bean có advisor phù hợp**. `@EnableAspectJAutoProxy` bật cơ chế tìm các aspect/advisor và tự bọc bean trong `ApplicationContext`; nó không đăng ký một bộ chặn toàn cục cho mọi lời gọi Java.

Cùng một class, cùng một method và cùng biểu thức pointcut nhưng kết quả khác nhau khi reference có nguồn gốc khác nhau:

- **Reference lấy từ Spring container:** nếu bean được container xử lý và có advisor phù hợp, người gọi nhận Spring AOP proxy; lời gọi qua reference này có thể kích hoạt advice.
- **Reference tạo bằng `new` ở ngoài container:** đối tượng không tự trải qua quy trình `BeanPostProcessor`/auto-proxy creator của context. Gọi method trên reference đó là lời gọi Java bình thường, không tự kích hoạt Spring AOP advice.
- **Một instance được tạo bằng `new` nhưng trả về từ `@Bean`:** đây vẫn là Spring bean sau khi container đăng ký và xử lý kết quả từ factory method; nó **có thể được proxy**. Chính việc Spring quản lý instance, không phải từ khóa `new` đơn lẻ, xác định ranh giới.
- **Giữ một reference trỏ thẳng tới target bên cạnh proxy Spring:** gọi qua reference target thô vẫn có thể bỏ qua advice; cần gọi qua **proxy** Spring trả về.

Ý chính cần nhớ:

> **Pointcut khớp tên class/method chỉ là điều kiện chọn advice; Spring AOP còn cần một Spring-managed bean và lời gọi đi qua proxy.**

Bài học này chỉ nói về Spring AOP và giới hạn auto-proxy. AspectJ compile-time/load-time weaving là cơ chế khác, không tự xuất hiện chỉ nhờ thêm `@Aspect` hoặc thư viện `aspectjweaver`.

## 2. Spring tạo proxy ở giai đoạn nào?

Khi dùng `@EnableAspectJAutoProxy`, Spring đăng ký auto-proxy creator, tiêu biểu là `AnnotationAwareAspectJAutoProxyCreator`. Thành phần này kế thừa hạ tầng `AbstractAutoProxyCreator`, vốn sử dụng các callback của `BeanPostProcessor` trong vòng đời tạo bean.

Luồng khái quát:

~~~text
             ApplicationContext
                     |
           tạo/nhận instance bean
                     |
          đi qua các BeanPostProcessor
                     |
          có advisor phù hợp không?
                  /       \
                Không     Có
                 |         |
              target     tạo proxy
                 |         |
                 +----+----+
                      |
            container cung cấp reference
                      |
          caller gọi method qua reference
                      |
                [nếu là proxy]
                      |
                 advice chain
                      |
                target.method()
~~~

So sánh với lời gọi nằm ngoài container:

~~~text
new Notifier("manual") --> raw Notifier object --> send()
                                                  |
                                                  v
                                               target code

ApplicationContext.getBean(Notifier.class)
          |
          v
      Spring AOP proxy --> @Before advice --> target.send()
~~~

Auto-proxy creator là thành phần **của Spring container**, không phải một hook được cài vào mọi class của JVM. Khi lập trình viên tự gọi `new Notifier(...)` trong một method thông thường, Spring không biết đối tượng đó cần xử lý như một bean mới. Việc annotation hoặc pointcut nhắc tới `Notifier` không biến đối tượng tự tạo thành Spring bean.

Cần phân biệt hai thời điểm:

1. **Tạo bean:** Spring kiểm tra advisor và có thể phát hành proxy thay cho target. Đây là công việc của hạ tầng auto-proxying.
2. **Gọi method:** caller gọi trên proxy thì interceptor/advice được chạy trước/sau/quanh target theo advisor đã khớp. Đối tượng không được proxy sẽ không tự có interceptor chain.

Không phải cứ là Spring bean là chắc chắn có proxy: còn phải có advisor áp dụng, bean đủ điều kiện xử lý và method có thể được chặn qua kiểu proxy tương ứng.

## 3. Các tình huống thường gặp

| Cách có được đối tượng | Có là Spring bean được xử lý bởi container? | Spring AOP tự áp dụng? |
| --- | --- | --- |
| `context.getBean("notifier")` hoặc inject bean bằng constructor | Có, nếu định nghĩa bean tồn tại trong context đó | Có thể; cần advisor khớp và proxy được tạo |
| `@Component` nằm trong package được component scan | Có | Có thể, khi advice/điều kiện proxy phù hợp |
| `@Bean Notifier notifier() { return new Notifier(...); }` | Có; kết quả factory method đi qua quy trình bean | Có thể; `new` bên trong `@Bean` không loại trừ AOP |
| `new Notifier(...)` trong controller/service/helper mà không đăng ký instance | Không | Không tự được Spring AOP auto-proxy |
| `new Notifier(...)` trong `main` bên ngoài `ApplicationContext` | Không | Không tự được Spring AOP auto-proxy |
| Object do thư viện bên ngoài tự tạo, không đưa vào container | Không, theo cách sử dụng đó | Không được auto-proxy chỉ bởi `@EnableAspectJAutoProxy` |
| Đối tượng do custom factory tạo và trả cho Spring qua một bean definition | Có, nếu Spring thực sự quản lý kết quả factory | Có thể; cần xem vòng đời và advisor |
| Prototype bean tạo bởi `context.getBean(...)` mỗi lần | Có; mỗi instance lấy qua container | Có thể được post-process/proxy khi Spring tạo từng instance |
| Một object chỉ gắn `@Component` nhưng được gọi bằng `new` | Reference tự tạo không qua container | Không; annotation không chuyển quyền sở hữu của object |
| Một bean được proxy nhưng code giữ và gọi reference trực tiếp vào target | Reference target thô đứng ngoài đường gọi proxy | Không chạy advice qua reference target thô |

Bảng xét trường hợp sử dụng **Spring AOP theo proxy**. Một kỹ thuật chủ động tạo proxy bằng API Spring hoặc AspectJ weaving là cấu hình riêng, không phải hành vi tự động của `@EnableAspectJAutoProxy`.

## 4. Ví dụ Java 17+: cùng class, chỉ Spring bean kích hoạt advice

Ví dụ chạy được với Spring Framework thuần; không cần Spring Boot, HTTP server, cơ sở dữ liệu hoặc Java agent.

Cấu trúc:

~~~text
spring-aop-boundary/
├── pom.xml
└── src/main/java/demo/
    ├── Demo.java
    ├── Notifier.java
    └── TraceAspect.java
~~~

Yêu cầu JDK 17+, Maven 3.9+; project dùng phiên bản cố định Spring Framework 6.2.0 và AspectJ Weaver 1.9.22 để có cùng cơ sở khi học.

### 4.1. Maven dependencies

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-boundary</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
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
                <configuration>
                    <mainClass>demo.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp `ApplicationContext` và Java config. `spring-aop` cung cấp auto-proxy utilities và proxy infrastructure. `aspectjweaver` cung cấp API/công cụ phân tích kiểu pointcut `@AspectJ` cho Spring; chỉ có dependency đó **không kích hoạt weaving**.

### 4.2. Cùng một lớp Notifier cho hai đối tượng

Tạo `src/main/java/demo/Notifier.java`:

~~~java
package demo;

public class Notifier {
    private final String label;

    public Notifier(String label) {
        this.label = label;
    }

    public void send() {
        System.out.println("TARGET: " + label);
    }
}
~~~

Class `Notifier` không `final`, method `send()` là `public` và có thể được override. Đây là kiểu dễ tạo class-based proxy. `label` chỉ giúp phân biệt đối tượng được container quản lý và object tự tạo; cả hai đều gọi đúng method `Notifier.send()`.

### 4.3. Aspect có bộ đếm chỉ tăng trong advice

Tạo `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger adviceCount = new AtomicInteger();

    @Before("execution(* demo.Notifier.send(..))")
    public void beforeSend() {
        adviceCount.incrementAndGet();
        System.out.println("ADVICE: before send");
    }

    public int getAdviceCount() {
        return adviceCount.get();
    }
}
~~~

Điểm cần quan sát:

- `@Aspect` đánh dấu class aspect bằng cú pháp mà Spring AOP hiểu, **không tự đăng ký thành Spring bean**.
- `@Before("execution(* demo.Notifier.send(..))")` khớp method execution `send()` của `Notifier`. Về mặt tên class/method, cả hai instance đều có cùng chữ ký.
- `beforeSend()` in dòng `ADVICE` và tăng counter. Nếu object tự tạo không kích hoạt advice, bộ đếm không tăng khi gọi nó.
- `AtomicInteger` giúp đọc số lần advice thực thi rõ ràng. Ví dụ chạy tuần tự nên không cần hạ tầng concurrency riêng.

### 4.4. Configuration, lời gọi và phép xác nhận

Tạo `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Demo {
    @Bean
    public Notifier notifier() {
        return new Notifier("managed");
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Demo.class)) {
            Notifier managed = context.getBean(Notifier.class);
            Notifier manual = new Notifier("manual");
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean managedProxy = AopUtils.isAopProxy(managed);
            boolean manualProxy = AopUtils.isAopProxy(manual);

            System.out.println("MANAGED_PROXY: " + managedProxy);
            System.out.println("MANUAL_PROXY: " + manualProxy);

            managed.send();
            manual.send();

            int calls = aspect.getAdviceCount();
            System.out.println("ADVICE_COUNT: " + calls);

            if (!managedProxy || manualProxy || calls != 1) {
                throw new IllegalStateException(
                        "Spring AOP proxy boundary verification failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Cơ chế trong chương trình:

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` đăng ký auto-proxy creator cho Spring context; class-based proxy phù hợp khi `Notifier` không triển khai interface. Cờ này **không** yêu cầu Spring tự nhận diện mọi object được gọi `new`.
2. `@Bean notifier()` **có `new Notifier("managed")` ở bên trong** nhưng kết quả được trả về cho Spring như một bean. Spring có thể xử lý, bọc proxy và công bố reference proxy cho caller; `AopUtils.isAopProxy(managed)` sẽ là `true`.
3. `@Bean traceAspect()` đăng ký instance `TraceAspect` trong chính context, để Spring tìm advisor từ `@Before`.
4. `new Notifier("manual")` trong `main` **không được đưa qua BeanFactory**, nên `AopUtils.isAopProxy(manual)` là `false`. Nó có cùng class, cùng method `send`, nhưng không có proxy.
5. `managed.send()` đi vào proxy rồi advice, sau đó vào target. `manual.send()` chỉ thực thi mã class; không tự đi qua proxy vì pointcut khớp về tên.
6. Điều kiện kiểm tra xác nhận trạng thái proxy trái ngược và **chỉ một lần advice thực sự chạy**. Một dòng `CHECK: PASS` chứng tỏ ứng dụng đã quan sát đúng ranh giới này.

### 4.5. Chạy và đối chiếu output

Chạy từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chính mã Java trên in ra, theo thứ tự:

~~~text
MANAGED_PROXY: true
MANUAL_PROXY: false
ADVICE: before send
TARGET: managed
TARGET: manual
ADVICE_COUNT: 1
CHECK: PASS
~~~

Nếu Maven/framework in thêm thông báo ngoài chương trình, hãy tập trung vào bảy dòng vừa nêu. Tại sao kết quả như vậy?

- **`MANAGED_PROXY: true`** chứng minh bean do Spring cấp đã được bọc khi advisor khớp.
- **`MANUAL_PROXY: false`** chứng minh object `new` độc lập không trở thành Spring proxy.
- **`ADVICE: before send`** đứng trước `TARGET: managed`, xác nhận phương thức được chặn qua proxy.
- **`TARGET: manual`** xuất hiện **không có dòng `ADVICE` thứ hai**, dù object thuộc cùng class `Notifier`.
- **`ADVICE_COUNT: 1`** là phép đo từ aspect bean; nếu advice đã chạy cho object `manual` thì số đếm phải tăng.
- **`CHECK: PASS`** chỉ được in khi cả trạng thái proxy và số lần advice đều đúng.

Ví dụ cố tình chọn cùng class/method và chạy hai reference cạnh nhau để loại bỏ giả thuyết “method không khớp pointcut”. Khác biệt được tạo bởi **nguồn gốc và cách gọi object**, không phải do code trong target.

## 5. Ba tình huống dễ nhầm khi thấy từ khóa new

### 5.1. new bên trong @Bean vẫn tạo Spring-managed bean

~~~java
@Configuration
class ServiceConfig {
    @Bean
    Notifier notifier() {
        return new Notifier("created-in-bean");
    }
}
~~~

Đây là **đoạn cấu hình trích riêng** (cần import `@Configuration`/`@Bean` và class `Notifier` như ví dụ). Spring container gọi factory method, nhận instance, thực hiện quá trình bean lifecycle và có thể trả AOP proxy. Việc câu lệnh tạo instance dùng `new` không khiến kết quả trở thành “object ngoài container”.

Vì vậy, không kết luận theo luật “có chữ `new` thì Spring AOP không chạy”. Phải hỏi **ai sở hữu instance sau khi tạo** và **reference nào được caller gọi**.

### 5.2. new bên trong một Spring bean không tự đăng ký object con

Ví dụ minh họa:

~~~java
public class DispatchService {
    public void dispatch() {
        Notifier temp = new Notifier("inner-manual");
        temp.send();
    }
}
~~~

Giả sử `DispatchService` là Spring bean và được proxy, object `temp` vẫn chỉ là đối tượng local do phương thức tự tạo. Spring không tự coi nó là một bean mới hoặc tự gắn AOP proxy vào reference `temp`. Method `send` của nó không được advice bởi Spring AOP chỉ vì object mẹ là Spring bean.

Đây là snippet dùng class `Notifier` đã khai báo; để thành chương trình chạy cần đăng ký `DispatchService` trong context và gọi `dispatch()` ở một entry point. Không được suy rằng Spring tự quản lý toàn bộ object graph mà các bean tự tạo ra.

### 5.3. Một object raw được đăng ký làm bean nhưng code giữ reference cũ

Giả sử một instance đã được tạo thủ công và sau đó **được đăng ký vào container theo cách cho phép Spring post-process nó**. Spring có thể công bố AOP proxy cho instance ấy, trong khi mã ngoài vẫn giữ một biến trỏ trực tiếp tới original:

~~~text
  Object target = new Notifier(...)
          |
          +--> biến rawTarget vẫn trỏ vào target
          |
          +--> Spring nhận instance này như một bean
                         |
                         +--> auto-proxy creator trả AOP proxy
                                            |
                                      managedReference
~~~

Gọi `managedReference.send()` có thể chạy advice; gọi `rawTarget.send()` vẫn đi thẳng vào target. Hai reference **không đồng nhất** chỉ vì chúng liên quan cùng object đích. Để bảo đảm advice, ưu tiên lấy/inject reference do container cung cấp và không giữ target thô ở đường gọi nghiệp vụ.

Không giả định rằng gọi `registerSingleton(...)` vào một BeanFactory đã chạy sẽ có cùng vòng đời/post-processing như một bean definition được đăng ký và tạo bình thường; việc đưa đối tượng sẵn có vào container phải đi theo API/lifecycle phù hợp.

## 6. Các giới hạn liên quan đến ranh giới Spring AOP

### 6.1. Có bean chưa đủ; cần lời gọi đi qua proxy

Ngay cả với Spring-managed bean đã có proxy:

~~~java
public class OrderService {
    public void place() {
        this.confirm();
    }

    public void confirm() {
        System.out.println("confirmed");
    }
}
~~~

Nếu advice chỉ chọn `confirm()` và caller gọi `place()` qua Spring proxy, lời gọi nội bộ `this.confirm()` trong target **không quay trở lại proxy**; advice trên `confirm()` có thể không chạy. Đây là **self-invocation**, một nguyên nhân khác với “đối tượng không được Spring quản lý” nhưng cùng liên quan đến ranh giới đường gọi.

Với Spring AOP, giải pháp thiết kế thông dụng là tách `confirm()` sang một bean riêng và gọi bean đó qua dependency Spring inject. Đừng nhầm rằng đổi JDK proxy sang CGLIB proxy hoặc bật `proxyTargetClass = true` sẽ làm `this.confirm()` đi qua proxy.

### 6.2. Class và method phải phù hợp với proxy

Spring AOP tự động xét bean, nhưng proxy có các giới hạn:

- Với **JDK dynamic proxy**, chỉ các phương thức được expose qua các interface của proxy có thể được gọi qua proxy theo kiểu interface; không cast proxy xuống implementation class.
- Với **CGLIB class proxy**, class `final` không thể subclass; method `final`/`private` không thể được override để intercept qua cơ chế subclass proxy.
- Lời gọi đến **static method**, constructor, field access hoặc object không do Spring quản lý không được Spring AOP proxy tự động chặn như một method execution trên Spring bean.
- Nếu bean không có advisor/pointcut phù hợp, Spring không bắt buộc tạo proxy chỉ vì `@EnableAspectJAutoProxy` đang bật.
- Nếu bean bị tạo quá sớm, ngoài đường BeanPostProcessor bình thường, nó có thể không được auto-proxy theo mong đợi. Việc này cần được chẩn đoán riêng với nguyên nhân `new` ngoài container.

Điểm chung: **cùng tồn tại trong JVM với một Spring AOP application không có nghĩa tất cả lời gọi đều đi qua proxy**.

### 6.3. @Autowired, @Transactional hoặc @Cacheable trên object tự new

Khi code viết:

~~~java
public class Processor {
    // Ví dụ minh họa, class này chưa được Spring đăng ký thành bean.
    @org.springframework.beans.factory.annotation.Autowired
    private Notifier notifier;

    public void process() {
        notifier.send();
    }
}
~~~

Nếu caller tự làm `new Processor()`, các callback inject dependency của Spring không tự chạy cho instance đó. `notifier` có thể vẫn là `null`, dẫn đến `NullPointerException` khi `process()` được gọi. Tương tự, các annotation ứng dụng dựa trên Spring AOP như `@Transactional`/`@Cacheable` (trong chế độ proxy) không tự biến object tự tạo thành proxy.

Đây là **snippet minh họa về dependency injection**, không phải một project biên dịch độc lập: nó dùng `Notifier` từ ví dụ và không có main method. Cần phân biệt rõ:

- **DI không chạy trên raw object** là vấn đề container ownership.
- **Advice không chạy trên raw object** là vấn đề Spring AOP proxy.
- **Bean có proxy nhưng tự gọi method nội bộ** là vấn đề đường gọi qua proxy.

Ba trường hợp có dấu hiệu gần nhau nhưng cần cách sửa khác nhau.

## 7. Cách thiết kế để object được Spring quản lý

### 7.1. Đăng ký bằng @Component hoặc @Bean

Nếu service thuộc application layer và cần Spring AOP, đăng ký nó trong `ApplicationContext`:

~~~java
@Component
public class NotificationService {
    public void send() {
        // application logic
    }
}
~~~

Snippet này phải đặt trong tệp `NotificationService.java` có `import org.springframework.stereotype.Component;` và cần component scanning bật cho package chứa class. Với cấu hình dùng `@Bean`, phương pháp ở ví dụ phần 4 rõ ràng hơn vì không phụ thuộc package scanning.

Đảm bảo aspect cũng được đăng ký như bean:

~~~java
@Aspect
@Component
public class MonitoringAspect {
    @Before("execution(* demo.NotificationService.send(..))")
    public void before() {
        System.out.println("advised");
    }
}
~~~

Đây là đoạn minh họa cần các import `org.aspectj.lang.annotation.*` và `org.springframework.stereotype.Component` trong project có component scanning; bản thân `@Aspect` **không đủ** để Spring tự quét class làm bean. Chỉ dùng các snippet này khi application có cấu hình AOP và scanning phù hợp.

### 7.2. Inject service, không tự tạo service bằng new

Thay vì:

~~~java
public class Sender {
    private final Notifier notifier = new Notifier("manual");

    public void doSend() {
        notifier.send();
    }
}
~~~

hãy để Spring inject đúng bean:

~~~java
public class Sender {
    private final Notifier notifier;

    public Sender(Notifier notifier) {
        this.notifier = notifier;
    }

    public void doSend() {
        notifier.send();
    }
}
~~~

Hai đoạn là **hai phiên bản lựa chọn** của một class `Sender`, không đặt đồng thời vào cùng project. Lớp `Sender` cũng cần được khai báo làm Spring bean (bằng `@Bean`/`@Component`) để container thực hiện constructor injection. Với Spring-managed `Notifier` đã được proxy, dependency thông thường của `Sender` là reference proxy; `doSend()` gọi đúng đường để Spring advice chạy.

Sử dụng constructor injection giúp lộ phụ thuộc ở API class, thuận tiện kiểm thử và tránh việc quên đăng ký bean.

### 7.3. Cần một đối tượng mới mỗi lần gọi?

Đừng mặc định phải dùng `new` chỉ vì business logic cần mỗi lần một instance khác nhau. Trong Spring có **prototype scope** và cách lấy object theo nhu cầu từ container:

~~~java
@Configuration
class NotificationConfig {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Notifier notifier() {
        return new Notifier("prototype");
    }
}
~~~

Đoạn cấu hình là minh họa: cần import `@Configuration`, `@Bean`, `@Scope`, `ConfigurableBeanFactory` cùng class `Notifier`. Mỗi lần Spring container tạo một prototype bean từ definition này, bean đi qua các cơ chế xử lý thích hợp, bao gồm khả năng auto-proxy nếu có advisor.

Một consumer có thể inject `ObjectProvider<Notifier>` và gọi `provider.getObject()` **mỗi khi cần instance mới**. Cần nhớ: một prototype được inject trực tiếp vào singleton thông thường chỉ được resolve tại thời điểm tạo singleton; không tự sinh prototype mới mỗi khi gọi method của singleton.

### 7.4. Nếu đối tượng phải do thư viện ngoài tạo

Với một callback object do SDK/framework khác tự tạo, có các lựa chọn phụ thuộc quyền kiểm soát vòng đời:

1. Nếu kiểm soát được factory, để Spring quản lý factory/result qua bean definition và truyền **proxy reference** tới nơi cần gọi, tránh giữ raw reference cũ.
2. Nếu không thay được factory bên ngoài nhưng caller do ứng dụng quản lý, đặt một **Spring-managed adapter/service** làm điểm gọi có Spring AOP và chuyển yêu cầu tới SDK object bên trong. Advice áp dụng tại **boundary của adapter**, không tự chặn mọi method bên trong SDK object.
3. Nếu thật sự phải advice trực tiếp một object không do Spring quản lý, **Spring AOP có API tạo proxy thủ công** (`AspectJProxyFactory`/`ProxyFactory`) cho target phù hợp. Đây là hành động explicit: caller phải nhận/dùng proxy tạo ra; tự động auto-proxy của `@EnableAspectJAutoProxy` không thực hiện bước này cho mọi raw object. Nếu yêu cầu vượt cả giới hạn proxy, phải đánh giá cơ chế khác với chi phí cấu hình riêng.

Một adapter Spring thường là cách đơn giản nhất để giữ các cross-cutting concern như logging, audit hoặc tracing ở ranh giới ứng dụng mà không cần điều khiển vòng đời nội bộ của thư viện thứ ba.

## 8. Tạo proxy thủ công cho object không được quản lý: giới hạn và ví dụ API

Spring Framework còn có `org.springframework.aop.aspectj.annotation.AspectJProxyFactory` để tạo AOP proxy một cách **chủ động**. Ví dụ minh họa đặt **trong một method Java đã có `Notifier` và `TraceAspect` của phần 4**:

~~~java
Notifier raw = new Notifier("external");

org.springframework.aop.aspectj.annotation.AspectJProxyFactory factory =
        new org.springframework.aop.aspectj.annotation.AspectJProxyFactory(raw);

TraceAspect manualAspect = new TraceAspect();
factory.addAspect(manualAspect);

Notifier proxy = factory.getProxy();
proxy.send();

System.out.println(manualAspect.getAdviceCount()); // 1
~~~

Đây **không phải project chạy độc lập**, mà là đoạn sử dụng thêm API vào project đã có dependency Spring AOP/AspectJ. Do `Notifier` không có interface, Spring có thể tạo class-based proxy phù hợp cho target trong ví dụ. `factory.addAspect(manualAspect)` dùng một instance aspect cụ thể; advice counter được đọc từ **instance này** chứ không phải aspect bean trong `ApplicationContext`.

Khác biệt với auto-proxy:

- Lập trình viên **chủ động chọn target**, **thêm aspect** và **lấy proxy** bằng `factory.getProxy()`.
- Chỉ những lời gọi trên `proxy` mới đi qua advice; gọi `raw.send()` vẫn bỏ qua proxy.
- Proxy thủ công không đồng nghĩa target gốc tự được đăng ký làm Spring bean hoặc có lifecycle/DI của container.
- Khi dùng Spring AOP auto-proxy cho application services thông thường, ưu tiên Spring-managed bean; không nên lặp việc tự tạo proxy thủ công khắp code.

## 9. Chẩn đoán khi advice không chạy cho một instance

Dùng checklist theo đúng thứ tự:

1. **Xác định nơi đối tượng được tạo:** `new` trong controller, factory, SDK, deserializer, callback hoặc lấy từ `context.getBean(...)`? Đặc biệt phân biệt `new` nằm **trong `@Bean` factory** với `new` nằm trong method thường.
2. **Kiểm tra Spring container có quản lý bean không:** tên bean/definition, component scanning, đúng `ApplicationContext` và đúng scope? Có thể cùng class tồn tại cả bean managed lẫn object raw.
3. **Kiểm tra reference thật đang được gọi:** dùng `AopUtils.isAopProxy(reference)` cho reference tại call site, không chỉ cho một instance khác trong context.
4. **Kiểm tra loại proxy và advisor:** `AopUtils.isJdkDynamicProxy`/`isCglibProxy`, pointcut method execution có khớp hay không. Có bean vẫn chưa chắc advice áp dụng.
5. **Xác định ranh giới method invocation:** caller gọi qua proxy, qua target raw hay `this.method()` trên cùng target?
6. **Kiểm tra giới hạn method:** JDK interface, CGLIB `final`/`private`, static method và constructor không phải method execution interceptable như method business thông thường.
7. **Nếu DI cũng thiếu:** object có được Spring inject và init không, hay được tự new? Không dùng sự có mặt của `@Autowired` như bằng chứng container đang quản lý instance.
8. **Nếu bean đã được Spring quản lý nhưng thiếu proxy:** xem auto-proxy creator có bật, aspect có đăng ký làm bean, advisor có khớp và bean có bị khởi tạo quá sớm trước khi BPP đầy đủ không.
9. **Sau khi sửa:** gọi cùng method qua reference Spring cấp, xác nhận dòng advice/counter hoặc integration test. Đừng chỉ kiểm tra việc method nghiệp vụ vẫn trả kết quả bình thường.

Đoạn kiểm tra chèn vào một ứng dụng đã có biến `context`:

~~~java
Object bean = context.getBean("notifier");

System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(
        org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(
        org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

Đoạn này không phải file Java độc lập; mục đích là đo reference Spring **đang thực sự cấp**. Nếu code còn giữ một raw reference khác và gọi vào nó, kết quả đo trên `bean` không nói được lời gọi raw có đi qua advice.

## 10. Những hiểu lầm thường gặp

**“Pointcut ghi đúng package/class/method nên bắt cả đối tượng tạo bằng `new`.”** Sai với proxy Spring AOP. Pointcut chỉ xác định advisor áp dụng cho những join point có thể đi qua proxy; nó không lắp interceptor vào mọi instance của class trong JVM.

**“`@Component` trên class bảo đảm mọi `new ThatClass()` được quản lý.”** Sai. Annotation giúp đăng ký bean definition khi component scanning phù hợp. Một instance khác tự tạo vẫn không tự đi qua Spring IoC.

**“Trong `@Bean` có `new` nên Spring không proxy được.”** Sai. Factory method trả instance cho container; quy trình bean post-processing có thể bọc nó.

**“Bean mẹ đã là proxy nên object nó tự tạo cũng được proxy.”** Sai. Object được tự new trong method là instance riêng; Spring không tự xử lý toàn bộ object graph bên trong method.

**“Spring bean có proxy thì tất cả lời gọi method của nó đều được advice.”** Sai. Self-invocation, loại method, điểm gọi, kiểu proxy và pointcut đều ảnh hưởng kết quả. Một proxy không làm mọi method trở thành join point được chặn.

**“Tôi gọi `getBean(...)` một lần để lấy proxy; reference raw cũ cũng tự thay thành proxy.”** Sai. Variable trỏ thẳng vào target không được biến đổi thành proxy chỉ vì container trả một wrapper cho người khác.

**“Thêm AspectJ Weaver dependency là auto-proxy cả object ngoài Spring.”** Sai. `aspectjweaver` thường là dependency giúp Spring giải thích kiểu `@AspectJ`; muốn AspectJ weaving thực sự cần thiết lập compiler/weaver riêng và cơ chế khác.

## 11. Tự kiểm tra

1. **Hai object `Notifier` cùng class, một được lấy từ Spring context, một được `new` ở main. Chỉ object nào tự động nhận advice?**  
   Object mà container xử lý và xuất ra qua proxy; object `new` độc lập không được Spring AOP tự bao.

2. **Tại sao `return new Notifier(...)` trong một `@Bean` vẫn có thể được AOP?**  
   Vì Spring quản lý **giá trị trả về của bean factory method**, cho nó đi qua BPP/auto-proxy trước khi công bố.

3. **Nếu một object raw được đưa vào proxy thủ công, có phải mọi biến đang trỏ tới object đó đều được advice?**  
   Không. Caller phải sử dụng biến trỏ tới **proxy**; reference raw vẫn gọi trực tiếp target.

4. **Vì sao dùng `@Autowired` trên field của object tự `new` có thể dẫn tới `null`?**  
   Vì Spring chưa hề thực hiện bước dependency injection cho instance đó.

5. **Nếu hai method cùng một Spring bean gọi nhau qua `this`, có chắc cả hai advice chạy không?**  
   Không. Lời gọi nội bộ trên target có thể bypass Spring proxy.

6. **Khi cần nhiều instance được advice, giải pháp Spring-native là gì?**  
   Đăng ký prototype/factory dưới Spring và lấy instance qua container (`ObjectProvider` khi cần), thay vì tạo raw object ngoài BeanFactory.

7. **`AspectJProxyFactory` có nghĩa `@EnableAspectJAutoProxy` tự động làm điều đó cho mọi raw object?**  
   Không. Đây là API tạo proxy **tường minh**; auto-proxy thuộc Spring bean lifecycle.

## 12. Tài liệu chính thức

- [Spring Framework — AOP @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): Spring đọc syntax @AspectJ nhưng runtime AOP vẫn dựa vào proxy.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): auto-proxying cho Spring beans.
- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): aspect phải được đăng ký làm bean; `@Aspect` riêng lẻ chưa đủ.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giới hạn JDK/CGLIB và self-invocation.
- [Spring Framework — Programmatic Creation of @AspectJ Proxies](https://docs.spring.io/spring-framework/reference/core/aop/aspectj-programmatic.html): API `AspectJProxyFactory`.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): Spring-managed singleton/prototype và cách yêu cầu instance theo scope.
