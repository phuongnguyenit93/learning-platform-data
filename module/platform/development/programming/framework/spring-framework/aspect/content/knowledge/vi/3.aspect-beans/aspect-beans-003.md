# Tiêm phụ thuộc vào aspect qua Spring

## 1. Mục tiêu và phạm vi

Một Spring aspect thường không tự thực hiện mọi công việc. Ví dụ, advice cần gửi sự kiện đến một bean ghi audit, dùng một bộ đếm dùng chung, hoặc gọi một dịch vụ hạ tầng. Spring có thể **tiêm các bean đó vào chính aspect** như với những Spring bean thông thường. Để việc này hoạt động, **aspect phải được đăng ký và quản lý trong ApplicationContext**, và hạ tầng Spring AOP phải được kích hoạt để sử dụng advice của nó.

Sau bài này, bạn có thể:

- Đăng ký một lớp `@Aspect` thành Spring bean bằng `@Component` hoặc `@Bean`.
- Dùng **constructor injection** để cung cấp dependency cho aspect.
- Giải thích thứ tự quan hệ giữa Spring container, aspect bean, collaborator bean, advisor và proxy của service.
- Quan sát cùng một bean dependency được sử dụng từ advice và từ client lấy bean trong context.
- Phân biệt **tiêm dependency vào aspect** với **tiêm service proxy vào một client**.
- Chẩn đoán lỗi thiếu bean, trùng bean, vòng phụ thuộc, khởi tạo aspect bằng `new`, và vấn đề scope hoặc dữ liệu chia sẻ.

**Giới hạn:** Bài chỉ nói về dependency injection trong **Spring AOP dựa trên proxy**. Các chủ đề AOP tổng quát và AspectJ weaving ngoài Spring không được triển khai ở đây.

## 2. Aspect là bean được Spring quản lý

Cần phân biệt ba vai trò:

| Thành phần | Spring sử dụng thế nào? |
| --- | --- |
| Lớp `@Aspect` | Khai báo pointcut/advice; riêng annotation này **không tự đăng ký bean** |
| Bean aspect | Instance do `ApplicationContext` quản lý; có thể nhận dependency qua constructor, `@Autowired`, `@Value`, v.v. |
| Service proxy | Đối tượng Spring AOP cung cấp để lời gọi service đi qua chuỗi interceptor/advice thích hợp |

Nếu lớp `AuditAspect` có `@Aspect` và `@Component`, component scan có thể đăng ký nó. Spring sẽ giải quyết constructor dependency trước khi aspect được sử dụng. Khi Spring AOP đọc advice từ aspect bean và tạo proxy cho một service phù hợp, lời gọi qua proxy có thể thực thi advice; advice sẽ sử dụng dependency đã được tiêm từ trước.

~~~text
                  ApplicationContext
                           |
          +----------------+----------------+
          |                |                |
    AuditStore bean   AuditAspect bean   OrderServiceImpl bean
          |                ^                |
          +-- inject ------+                |
                           |                |
                  @Before advice            |
                           +----- advisor --+
                                             |
                                         Spring proxy
                                             |
                                  App -> OrderService.submit()
~~~

`@Aspect` phục vụ nhận diện các khai báo AOP; `@Component` hoặc `@Bean` phục vụ **đăng ký aspect là bean**. Dependency injection được Spring container thực hiện; advice chạy khi **phương thức khớp pointcut và lời gọi đi qua Spring proxy**. Việc inject thành công không tự bảo đảm advice sẽ chạy.

## 3. Ví dụ chạy được: aspect nhận một AuditStore

Giả sử `OrderService` xử lý mã đơn. Mỗi lần client gọi `submit(...)`, Spring AOP kích hoạt advice `@Before`; advice nhận `AuditStore` qua constructor và yêu cầu bean đó ghi một sự kiện. Đây là ví dụ Spring Framework thuần với **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12**, không cần Spring Boot hoặc cơ sở dữ liệu.

Cấu trúc dự án:

~~~text
spring-aop-aspect-injection/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── AppConfig.java
    ├── AuditStore.java
    ├── AuditAspect.java
    ├── OrderService.java
    └── OrderServiceImpl.java
~~~

### 3.1. Maven dependencies

Tạo **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-aspect-injection</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp container annotation và kéo theo các module Spring cần thiết, trong đó có Spring AOP. `aspectjweaver` cung cấp những kiểu của AspectJ và hỗ trợ phân tích biểu thức pointcut dạng `@AspectJ`. Ứng dụng **không bật AspectJ weaving**; Spring vẫn chặn lời gọi qua proxy.

### 3.2. Tạo bean phụ thuộc mà aspect sẽ dùng

**src/main/java/demo/AuditStore.java**

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;

@Component
public class AuditStore {

    private final List<String> events = new CopyOnWriteArrayList<>();

    public void record(String message) {
        events.add(message);
        System.out.println("AUDIT " + message);
    }

    public int size() {
        return events.size();
    }
}
~~~

`@Component` làm `AuditStore` trở thành ứng viên của component scanning. Nó có tên bean mặc định `auditStore`. Instance này chịu trách nhiệm lưu sự kiện minh họa trong bộ nhớ. `CopyOnWriteArrayList` cho phép thao tác thêm/đọc an toàn về mặt đồng thời cho ví dụ nhỏ; trong ứng dụng sản xuất có nhiều sự kiện, nên chọn cơ chế lưu trữ và đồng bộ phù hợp thay vì giữ mọi sự kiện vô hạn trong singleton.

Hãy để ý: `AuditStore` là một **Spring bean thông thường**, không cần biết mình đang được gọi từ advice. Aspect là nơi phụ thuộc vào nó, không phải ngược lại.

### 3.3. Tạo hợp đồng và bean service

**src/main/java/demo/OrderService.java**

~~~java
package demo;

public interface OrderService {
    String submit(String orderId);
}
~~~

**src/main/java/demo/OrderServiceImpl.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {

    @Override
    public String submit(String orderId) {
        System.out.println("SERVICE submit " + orderId);
        return "created:" + orderId;
    }
}
~~~

`@Service` giúp Spring đăng ký `OrderServiceImpl` qua component scan. Phương thức nghiệp vụ không tự biết đến audit. Việc ghi audit sẽ xuất hiện từ advice áp dụng cho lời gọi service qua Spring proxy.

### 3.4. Tiêm dependency bằng constructor của aspect

**src/main/java/demo/AuditAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {

    private final AuditStore auditStore;

    public AuditAspect(AuditStore auditStore) {
        this.auditStore = auditStore;
    }

    @Before("execution(* demo.OrderServiceImpl.submit(..))")
    public void beforeSubmit(JoinPoint joinPoint) {
        Object orderId = joinPoint.getArgs()[0];
        auditStore.record("submit " + orderId);
    }
}
~~~

Đây là trọng tâm bài học:

1. **`@Aspect`** khai báo class có advice cho Spring AOP đọc.
2. **`@Component`** cho component scanner phát hiện `AuditAspect` và đăng ký bean tên mặc định `auditAspect`.
3. **`private final AuditStore auditStore`** là dependency của instance aspect. Lớp không tự tạo `AuditStore`.
4. Constructor **`AuditAspect(AuditStore auditStore)`** cho Spring biết instance cần bean loại `AuditStore`. Vì đây là constructor duy nhất, Spring có thể tự chọn nó mà không cần `@Autowired`.
5. **`@Before(...)`** chạy trước target method nếu lời gọi khớp và đi qua proxy. Advice dùng **chính trường `auditStore` đã được inject** để ghi sự kiện.

Pointcut `execution(* demo.OrderServiceImpl.submit(..))` nhắm vào phương thức triển khai `submit` của service. Việc inject một dependency không ảnh hưởng trực tiếp đến điều kiện match pointcut.

Phương thức `beforeSubmit` nhận `JoinPoint` do hạ tầng advice cung cấp khi thực thi, **không phải một constructor dependency do container tiêm**. `JoinPoint` chứa dữ liệu của lời gọi hiện tại như đối số, signature; còn `AuditStore` là Spring bean có vòng đời riêng.

### 3.5. Cấu hình Spring AOP và component scan

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

- `@Configuration`: đánh dấu nguồn cấu hình Java của Spring.
- `@ComponentScan(basePackages = "demo")`: đăng ký `AuditStore`, `AuditAspect`, `OrderServiceImpl` bằng các stereotype annotation.
- `@EnableAspectJAutoProxy`: bật hạ tầng Spring AOP tự phát hiện advice từ những aspect đã được đăng ký và tạo proxy cho bean service có advisor thích hợp.

Trong ví dụ Spring Framework thuần này, nếu thiếu `@EnableAspectJAutoProxy`, constructor injection vào `AuditAspect` vẫn có thể hoạt động vì aspect vẫn là một component; tuy nhiên advice của nó không tự áp dụng vào `OrderServiceImpl` nếu không có hạ tầng AOP tương đương. Ngược lại, chỉ bật auto-proxy mà không đăng ký aspect hoặc `AuditStore` cũng không đủ.

### 3.6. Chạy ứng dụng và kiểm chứng cả injection lẫn advice

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println(
                    "ASPECT_BEAN " + context.containsBean("auditAspect"));
            System.out.println(
                    "STORE_BEAN " + context.containsBean("auditStore"));

            OrderService service = context.getBean(OrderService.class);
            AuditStore store = context.getBean(AuditStore.class);

            System.out.println("IS_PROXY " + AopUtils.isAopProxy(service));
            System.out.println("COUNT_BEFORE " + store.size());

            String result = service.submit("ORD-42");
            System.out.println("RESULT " + result);
            System.out.println("COUNT_AFTER " + store.size());
        }
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

**Đầu ra logic kỳ vọng**, không tính các thông báo riêng của Maven hoặc hệ thống logging:

~~~text
ASPECT_BEAN true
STORE_BEAN true
IS_PROXY true
COUNT_BEFORE 0
AUDIT submit ORD-42
SERVICE submit ORD-42
RESULT created:ORD-42
COUNT_AFTER 1
~~~

Đọc từng giai đoạn:

- **`ASPECT_BEAN true`**: aspect đã là bean, nên Spring có cơ hội inject `AuditStore`.
- **`STORE_BEAN true`**: dependency `AuditStore` cũng được đăng ký.
- **`IS_PROXY true`**: đối tượng service lấy từ context được Spring bọc AOP proxy; ví dụ này có advisor khớp `submit(...)`.
- **`COUNT_BEFORE 0`**: bean store chưa ghi sự kiện.
- **`AUDIT submit ORD-42`**: proxy kích hoạt `@Before`; advice gọi phương thức trên dependency đã được inject.
- **`SERVICE submit ORD-42`**: phương thức nghiệp vụ chạy sau advice.
- **`COUNT_AFTER 1`**: cùng bean `AuditStore` mà `App` lấy từ context đã nhận thêm một sự kiện.

Với cấu hình mặc định, các `@Component` này thuộc **singleton scope**, nên Spring cung cấp một shared instance `AuditStore` cho `AuditAspect` và cho `App`. Khi thay đổi scope, không thể mặc định suy ra hai điểm sử dụng luôn thấy chính cùng một instance.

## 4. Bản chất của constructor injection trong aspect

Spring khởi tạo aspect giống như một bean có dependency:

~~~text
@Component AuditStore
        |
        v
Spring có thể tạo AuditStore bean
        |
        v
@Component @Aspect AuditAspect(AuditStore)
        |
        +-- resolve constructor argument theo bean type
        +-- truyền AuditStore vào constructor
        +-- lưu dependency ở trường final
        |
        v
Spring AOP đọc advice / advisor từ aspect bean
        |
        v
Service proxy gọi advice đã cấu hình
        |
        v
AuditAspect.beforeSubmit(...) sử dụng auditStore
~~~

Sơ đồ diễn giải **quan hệ phụ thuộc**, không bắt buộc toàn bộ bean trong mọi ứng dụng được khởi tạo theo thứ tự cứng. Container có thể tạo các singleton khác trước hoặc sau tùy graph dependency và configuration.

**Vì sao nên dùng constructor injection?**

- Aspect có dependency bắt buộc và được khởi tạo ở trạng thái đầy đủ; không có trạng thái đã tạo xong nhưng trường nghiệp vụ bắt buộc chưa được gán.
- Trường `final` thể hiện tham chiếu không bị thay đổi sau constructor.
- Khi test phần logic bên trong aspect bằng Java, có thể truyền một fake/stub `AuditStore` rõ ràng.
- Constructor mô tả chính xác dependency graph, giúp lỗi thiếu bean xuất hiện khi container khởi tạo.

`@Autowired` trên constructor duy nhất là **không bắt buộc** với cơ chế constructor injection hiện đại của Spring. Nếu có nhiều constructor, cần xác định constructor nào được chọn; có thể dùng `@Autowired` theo quy tắc resolve constructor của Spring.

### Constructor injection khác với phương thức advice

Không nên nhầm:

~~~java
public AuditAspect(AuditStore auditStore) { ... }
~~~

với:

~~~java
@Before("execution(* demo.OrderServiceImpl.submit(..))")
public void beforeSubmit(JoinPoint joinPoint) { ... }
~~~

Constructor được Spring gọi để **tạo bean aspect** và cung cấp `AuditStore`. Advice được AOP interceptor gọi **mỗi lần lời gọi phù hợp đi qua proxy**; đối tượng `JoinPoint` phản ánh invocation hiện tại.

Không thể kỳ vọng Spring tự tiêm một service bean tùy ý vào mọi tham số của phương thức `@Before`. Muốn dependency bền vững, hãy dùng constructor hoặc cơ chế injection bean. Muốn dữ liệu invocation, dùng `JoinPoint` hoặc argument binding phù hợp.

## 5. Cách khác: đăng ký aspect và dependency bằng @Bean

Nếu không dùng component scanning, Spring vẫn tiêm dependency vào aspect được đăng ký bằng Java configuration. Để thử riêng cách này, **thay hẳn nội dung** file `src/main/java/demo/AppConfig.java` ở ví dụ bằng:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public AuditStore auditStore() {
        return new AuditStore();
    }

    @Bean
    public AuditAspect auditAspect(AuditStore auditStore) {
        return new AuditAspect(auditStore);
    }

    @Bean
    public OrderService orderService() {
        return new OrderServiceImpl();
    }
}
~~~

Trong biến thể này, `@ComponentScan` đã được gỡ bỏ, nên việc còn giữ `@Component` hoặc `@Service` trên các class **không khiến chúng bị đăng ký hai lần**. Chỉ có ba phương thức `@Bean` ở trên tạo ra ba bean tương ứng. Vì tên bean `auditStore` và `auditAspect` giữ nguyên, và `App` lấy service theo **OrderService.class**, **không cần sửa App.java**. Chạy lại:

~~~bash
mvn -q clean compile exec:java
~~~

Đầu ra logic vẫn là:

~~~text
ASPECT_BEAN true
STORE_BEAN true
IS_PROXY true
COUNT_BEFORE 0
AUDIT submit ORD-42
SERVICE submit ORD-42
RESULT created:ORD-42
COUNT_AFTER 1
~~~

Ở đây:

1. Spring gọi factory `auditStore()` để có dependency bean.
2. Khi cần `AuditAspect`, Spring resolve tham số `AuditStore` của factory method `auditAspect(...)`; method truyền bean đó vào constructor.
3. Bean `AuditAspect` có `@Aspect` trong định nghĩa class nên Spring AOP vẫn nhận diện advice của nó.
4. Bean service được Spring quản lý dù factory sử dụng `new OrderServiceImpl()`; instance đó được trả **về cho container**, có thể trải qua các bước xử lý như auto-proxy trước khi client nhận.
5. `@EnableAspectJAutoProxy` vẫn cần thiết trong cấu hình Spring Framework thuần.

Điều quan trọng là **ai quản lý instance và làm sao dependency được resolve**. `new AuditAspect(...)` trong phương thức `@Bean` hợp lệ vì instance sau đó được đăng ký thành Spring bean. Nếu ứng dụng tạo `new AuditAspect(...)` ở ngoài context mà không đăng ký, Spring AOP không tự dùng instance ấy làm aspect.

Có thể bỏ `@Component` khỏi `AuditAspect` trong biến thể `@Bean` mà aspect vẫn chạy vì class vẫn có `@Aspect` và instance được Spring quản lý qua factory method.

Sau thí nghiệm, nếu muốn trở về phiên bản scanner, khôi phục `AppConfig` ban đầu. Không giữ đồng thời hai đường đăng ký cùng service/aspect khi chưa chủ đích dùng nhiều bean; điều này có thể gây ambiguity, xung đột bean name hoặc advice được áp dụng nhiều lần.

## 6. Các kiểu dependency có thể inject vào aspect

### 6.1. Một bean dịch vụ thông thường

Đây là trường hợp đã chạy: `AuditAspect` nhận `AuditStore` từ Spring. Cũng có thể inject một interface thay vì implementation, ví dụ:

~~~java
public interface AuditWriter {
    void write(String event);
}
~~~

Nếu aspect khai báo constructor `AuditAspect(AuditWriter writer)`, Spring cần tìm được một bean thực thi `AuditWriter`. Khi nhiều implementation cùng tồn tại, phải giải quyết ambiguity, chẳng hạn bằng **`@Qualifier`** hoặc **`@Primary`** tùy thiết kế. Đoạn interface này chỉ là **minh họa API**, chưa thay thế file nào trong ví dụ chạy được.

Nên ưu tiên interface khi collaborator có nhiều cách triển khai hoặc cần test double. Không nhất thiết tạo interface cho mọi class nhỏ chỉ vì dependency injection hỗ trợ việc đó.

### 6.2. Thuộc tính cấu hình với @Value

Aspect có thể nhận giá trị do Spring resolve trong constructor:

~~~java
@Aspect
@Component
public class AuditAspect {

    private final AuditStore auditStore;
    private final boolean enabled;

    public AuditAspect(
            AuditStore auditStore,
            @org.springframework.beans.factory.annotation.Value(
                    "${audit.enabled:true}") boolean enabled) {
        this.auditStore = auditStore;
        this.enabled = enabled;
    }

    @Before("execution(* demo.OrderServiceImpl.submit(..))")
    public void beforeSubmit(org.aspectj.lang.JoinPoint joinPoint) {
        if (enabled) {
            auditStore.record("submit " + joinPoint.getArgs()[0]);
        }
    }
}
~~~

Đây là **phiên bản thay thế minh họa** cho toàn bộ nội dung `AuditAspect.java`, không dùng đồng thời với class trùng tên ở mục 3. Ví dụ đọc `audit.enabled`, mặc định `true`, từ các property sources mà Spring context có sẵn. Khi dùng cấu hình riêng, cần bảo đảm property source được nạp đúng cách; trong Spring Boot có thể dùng cơ chế configuration properties phù hợp. **`@Value` chỉ lấy giá trị cấu hình**, không quyết định có proxy hay pointcut có match.

### 6.3. Dependency có vòng đời ngắn hơn aspect

Aspect được đăng ký bằng `@Component` thường là singleton, còn một collaborator có thể dùng `request` hoặc `prototype` scope. Nếu inject thẳng một bean prototype vào singleton bằng constructor, dependency thường được resolve **một lần lúc singleton được tạo**; không tự tạo instance prototype mới trên mỗi advice invocation.

Nếu cần tra cứu bean theo mỗi lời gọi, Spring có **`ObjectProvider<T>`**. Ví dụ minh họa:

~~~java
private final org.springframework.beans.factory.ObjectProvider<AuditContext>
        contextProvider;

public AuditAspect(
        org.springframework.beans.factory.ObjectProvider<AuditContext>
                contextProvider) {
    this.contextProvider = contextProvider;
}
~~~

Trong advice, dùng `contextProvider.getObject()` tại thời điểm thật sự cần. Đoạn mã chỉ minh họa cách khai báo dependency: lớp `AuditContext` và bean tương ứng phải được định nghĩa; **không phải mã chạy độc lập**. Đối với request-scoped dependency cần request scope đang hoạt động, hoặc một scoped proxy thích hợp. Gọi trong thread không có HTTP request thường dẫn tới lỗi scope; `ObjectProvider` không tự tạo ra request context.

Không lưu dữ liệu biến đổi của từng request vào trường instance của singleton aspect. Nếu advice chạy đồng thời ở nhiều thread, dữ liệu đó dễ lẫn giữa các invocation.

## 7. Cùng một ApplicationContext và điều kiện proxy

Trong ví dụ, `AppConfig` bật AOP trong context chứa cả `AuditAspect`, `AuditStore` và `OrderServiceImpl`. Đây là tình huống dễ quan sát nhất.

Ở ứng dụng có **nhiều ApplicationContext** (ví dụ parent/child), cần kiểm tra:

- Aspect bean và dependency của nó có nhìn thấy nhau qua cơ chế bean resolution của context hay không.
- Service được xử lý bởi hạ tầng auto-proxy của context nào.
- Cấu hình bật Spring AOP có được đặt ở context chứa bean cần advice hay không.

`@EnableAspectJAutoProxy` áp dụng cho **context nơi nó được khai báo**. Không thể tự suy luận việc bật AOP ở một context sẽ làm tất cả bean trong mọi context liên quan đều trở thành proxy.

Trong Spring Framework thuần, nếu service có interface, Spring AOP thường dùng **JDK dynamic proxy** khi phù hợp. Ví dụ gọi `context.getBean(OrderService.class)` để dùng interface. Không giả định proxy là đối tượng có runtime type `OrderServiceImpl`. Cấu hình `proxyTargetClass = true` có thể chọn class-based proxy; việc này không thay đổi cách constructor injection diễn ra trong aspect.

**Hai kiểm tra độc lập cần có**:

1. **Injection**: bean `AuditAspect` khởi tạo được, nhận bean `AuditStore` và có thể gọi `record(...)`.
2. **AOP**: bean `OrderService` trả về là proxy phù hợp và lời gọi đến `submit(...)` thực sự chạy advice.

Kết quả `AopUtils.isAopProxy(service)` bằng `true` một mình vẫn chưa chứng minh **AuditAspect** được áp dụng: proxy có thể được tạo bởi một advisor khác. Kiểm tra hành vi output hoặc kiểm thử trạng thái của dependency là bằng chứng cụ thể hơn.

## 8. Các lỗi thường gặp khi inject vào aspect

| Hiện tượng | Nguyên nhân trong Spring | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` khi tạo aspect | Chưa đăng ký `AuditStore`, package nằm ngoài vùng scan hoặc thiếu `@Bean` | Kiểm tra `@Component`, package scan và Java configuration |
| `NoUniqueBeanDefinitionException` cho constructor dependency | Có nhiều bean phù hợp cùng kiểu, không xác định được bean cần dùng | Dùng `@Qualifier`, `@Primary`, hoặc cấu hình một bean đúng mục đích |
| Aspect được tạo nhưng advice không chạy | Thiếu `@EnableAspectJAutoProxy`, pointcut không khớp, hoặc lời gọi không qua proxy | Kiểm tra AOP config, biểu thức pointcut và client lấy service từ Spring |
| `@Aspect` có tồn tại nhưng bean không có trong context | Chỉ gắn `@Aspect` mà không có đăng ký component hoặc factory `@Bean` | Thêm `@Component` trong vùng scan hoặc đăng ký aspect bằng `@Bean` |
| Dùng `new AuditAspect(...)` trong mã ứng dụng rồi mong advice tự chạy | Instance nằm ngoài Spring container | Đăng ký aspect như bean trong context |
| Xảy ra `BeanCurrentlyInCreationException` hoặc lỗi vòng phụ thuộc | Aspect và collaborator/service phụ thuộc vòng qua lại | Thiết kế lại hướng phụ thuộc, tách collaborator audit khỏi service đang được advise |
| Đếm audit sai khi nhiều lời gọi đồng thời | Mutable field chung trong singleton aspect/collaborator không an toàn thread | Dùng cấu trúc đồng thời thích hợp, giữ dữ liệu invocation ở biến cục bộ |
| Không lấy được request-scoped bean trong advice | Scope không active ở thread hiện tại | Xem lại nơi kích hoạt lời gọi, dùng scoped proxy/provider đúng yêu cầu |
| Inject `null` khi unit test dùng `new AuditAspect()` sai cách | Test đã bỏ qua constructor injection và container | Truyền dependency qua constructor hoặc tạo Spring test context |
| Advice log trước nhưng nghiệp vụ không chạy | Advice ném exception; với `@Before`, lỗi của advice có thể ngắt lời gọi | Kiểm soát ngoại lệ và xác định chính sách lỗi của hạ tầng audit |

Vòng phụ thuộc cần chú ý hơn trong AOP vì quá trình tạo proxy có thể cần đọc advisor và aspect bean. Ví dụ graph `AuditAspect → AuditStore → OrderService → (advisor cần AuditAspect)` là một thiết kế dễ trở nên rắc rối. Hãy giữ các collaborator mà aspect dùng **đơn giản, độc lập với service đang bị chặn** khi có thể.

## 9. Phân biệt dependency injection với self-invocation và thứ tự advice

Đặt được dependency vào aspect không làm thay đổi giới hạn **self-invocation** của Spring AOP. Nếu một phương thức của `OrderServiceImpl` tự gọi `this.submit(...)`, cuộc gọi nội bộ đó bỏ qua proxy nên advice không được thực thi riêng cho `submit(...)`. Đây là vấn đề **đường đi của lời gọi**, không phải lỗi constructor injection.

Nếu có nhiều aspect cùng dùng `AuditStore`, các aspect có thể được inject cùng một singleton store. Tuy nhiên thứ tự advice có thể ảnh hưởng thứ tự sự kiện. Trong Spring có thể dùng `@Order` để kiểm soát mức ưu tiên khi cần, và cần thử hành vi thực tế. Không lấy thứ tự khai báo class hoặc tên bean làm bằng chứng về thứ tự chạy advice.

Đối với **`@Before`**, nếu `AuditStore.record(...)` ném exception, phương thức service có thể không được gọi. Khi audit chỉ là quan sát, quyết định có bắt/ghi/lờ lỗi audit hay không phải dựa trên yêu cầu nghiệp vụ; tránh tự động nuốt mọi lỗi làm che giấu sự cố.

## 10. Cách kiểm tra bằng test ngắn

Có thể kiểm thử logic tích hợp mà không cần phụ thuộc vào kết quả in log, bằng cách tạo lại context và assert trực tiếp trên `AuditStore`:

~~~java
try (var context =
         new org.springframework.context.annotation
             .AnnotationConfigApplicationContext(demo.AppConfig.class)) {

    demo.OrderService service =
            context.getBean(demo.OrderService.class);
    demo.AuditStore store = context.getBean(demo.AuditStore.class);

    if (store.size() != 0) {
        throw new AssertionError("Store must begin empty");
    }

    String result = service.submit("T-1");

    if (!"created:T-1".equals(result)) {
        throw new AssertionError("Unexpected result: " + result);
    }
    if (store.size() != 1) {
        throw new AssertionError("Aspect did not record exactly once");
    }
}
~~~

Đoạn này là **fragment kiểm thử bổ sung**, để đặt vào một phương thức test hoặc `main` khác trong dự án ở mục 3; nó không phải file Java hoàn chỉnh đứng độc lập. Kết quả thành công: không ném `AssertionError`. Test kiểm tra cả kết quả service và hiệu ứng ở collaborator. Nếu bỏ `@EnableAspectJAutoProxy` trong ví dụ Spring Framework thuần, điều kiện `store.size() == 1` sẽ thất bại do advice không chạy.

Khi unit test riêng `AuditAspect`, có thể tạo `new AuditAspect(fakeStore)` và gọi trực tiếp phương thức `beforeSubmit` với một `JoinPoint` giả lập. Kiểu test đó xác nhận logic advice nhưng **không xác nhận Spring đã tạo proxy**; cần ít nhất một integration test qua `ApplicationContext` cho cơ chế Spring AOP.

## 11. Nguyên tắc áp dụng trong ứng dụng Spring

- Dùng **constructor injection** cho dependency bắt buộc của aspect, ưu tiên `final` và dependency rõ ràng.
- Đăng ký aspect qua **`@Component` + component scan** hoặc **`@Bean`**; không coi `@Aspect` là cách đăng ký Spring bean.
- Bảo đảm các collaborator được tiêm có bean definition hợp lệ và scope phù hợp với vòng đời aspect.
- Đặt logic nghiệp vụ ở service; aspect chỉ thực hiện trách nhiệm phụ trợ như quan sát hoặc áp dụng quy tắc cắt ngang có mục đích.
- Tránh để aspect phụ thuộc ngược vào service đang bị chính aspect chặn nếu tạo vòng phụ thuộc hoặc khiến logic audit tái nhập bất ngờ.
- Hạn chế mutable state theo request trong singleton aspect; dùng tham số advice hoặc collaborator được thiết kế thread-safe.
- Kiểm tra **cả dependency injection lẫn AOP advice thực tế**. Có bean, có proxy và có hiệu ứng advice là ba trạng thái có quan hệ nhưng không đồng nhất.

## 12. Câu hỏi tự đánh giá

**1. Vì sao `@Aspect` không đủ để Spring inject `AuditStore`?**

Vì `@Aspect` chỉ khai báo aspect. Spring phải đăng ký `AuditAspect` như một bean (ví dụ `@Component` trong vùng quét hoặc `@Bean`) trước khi container thực hiện dependency injection.

**2. Constructor của `AuditAspect` có cần `@Autowired` không?**

Không bắt buộc khi lớp chỉ có một constructor. Spring có thể tự chọn constructor đó và resolve dependency theo kiểu, rồi áp dụng quy tắc chọn bean nếu có nhiều ứng viên.

**3. Tại sao `COUNT_AFTER` là 1 dù `App` không trực tiếp gọi `store.record(...)`?**

Vì lời gọi service qua proxy kích hoạt advice. Advice gọi `record(...)` trên singleton `AuditStore` đã được inject; `App` lấy cùng bean đó từ context để kiểm tra kết quả.

**4. Cấu hình `@Bean` dùng `new AuditAspect(auditStore)` có mất khả năng inject hoặc advice không?**

Không. Instance được trả về từ factory `@Bean` là Spring-managed bean. Spring AOP có thể đọc khai báo `@Aspect` và dùng advice nếu hạ tầng AOP hoạt động.

**5. Nếu `AuditStore` không được đăng ký, liệu aspect có chạy mà bỏ qua audit không?**

Với dependency constructor bắt buộc, context sẽ thất bại khi cần tạo `AuditAspect` vì không resolve được tham số; Spring không tự truyền `null` để bỏ qua dependency.

**6. Một aspect singleton có thể lưu mã đơn hiện tại trong field `lastOrderId` không?**

Không nên dùng field đó để biểu diễn dữ liệu của từng invocation, vì nhiều thread có thể ghi đè lẫn nhau. Dùng biến cục bộ trong advice hoặc cơ chế context phù hợp.

**7. Nếu `IS_PROXY true` nhưng không thấy audit, nên kiểm tra gì?**

Kiểm tra có `AuditAspect` bean thật sự không, pointcut có khớp method không, lời gọi có qua proxy không và liệu proxy có được tạo từ advisor khác không.

## 13. Tài liệu Spring chính thức

- Spring Framework — Dependency Injection: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- Spring Framework — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework — `@Bean` methods: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework — `@AspectJ` support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Ghi nhớ:** Trong Spring, aspect nhận dependency bằng cơ chế bean injection thông thường khi đã là Spring-managed bean. Việc advice của aspect chạy lại phụ thuộc vào cấu hình Spring AOP, pointcut và lời gọi qua proxy. Hai cơ chế phối hợp để aspect có thể sử dụng các dịch vụ của `ApplicationContext` mà không tự khởi tạo dependency.
