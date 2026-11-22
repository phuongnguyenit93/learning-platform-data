# Mô hình singleton, perthis và pertarget được Spring AOP hỗ trợ

## 1. Học gì trong bài này?

Trong Spring AOP, aspect được Spring quản lý như một bean, nhưng **số lượng instance của aspect** có thể được quyết định theo những mô hình khác nhau. Ba mô hình quan trọng cần hiểu là:

- **singleton**: một instance aspect dùng chung cho nhiều proxy/lời gọi trong phạm vi bean và ApplicationContext.
- **perthis**: một instance aspect được gắn với từng đối tượng **Spring AOP proxy** phù hợp.
- **pertarget**: một instance aspect được gắn với từng đối tượng **target** phía sau proxy phù hợp.

Đây là **aspect instantiation models**, tức chính sách liên kết và tạo instance aspect trong Spring AOP. Chúng khác với các khái niệm bean scope như singleton, prototype, request hoặc session. Đặc biệt, với perthis/pertarget, ta phải cấu hình bean aspect theo **prototype** để Spring có thể tạo các instance theo từng proxy hoặc target.

Mục tiêu thực hành:

1. Viết annotation **@Aspect** đúng cho từng mô hình.
2. Đăng ký aspect bean và bật **@EnableAspectJAutoProxy**.
3. Thấy khác biệt giữa một bộ đếm duy nhất và bộ đếm riêng theo từng đối tượng được advise.
4. Giải thích rõ Spring AOP phân biệt **this = proxy** và **target = đối tượng được proxy bọc**.
5. Tránh lỗi cấu hình singleton bean cho perthis/pertarget, cùng các nhầm lẫn về số bean, số lời gọi và dữ liệu đồng thời.

**Phạm vi:** Chỉ xem xét hành vi của **Spring AOP với @AspectJ annotation style** trong **ApplicationContext**. Không giảng lại lý thuyết AspectJ nói chung hoặc chuyển sang weaving bằng trình biên dịch/Java agent.

## 2. Vì sao mô hình tạo instance quan trọng?

Giả sử có hai bean service độc lập:

~~~text
ApplicationContext
  |
  +-- first  --> Spring proxy P1 --> JobImpl target T1
  |
  +-- second --> Spring proxy P2 --> JobImpl target T2
  |
  +-- aspect definition (advice cho Job.execute)
~~~

Client lần lượt gọi:

~~~text
first.execute()
second.execute()
first.execute()
second.execute()
~~~

Nếu aspect có trường **counter**, câu hỏi đặt ra là counter dùng chung hay riêng?

| Mô hình | Gắn instance aspect vào | Với P1→T1 và P2→T2 | Bộ đếm nếu mỗi lời gọi khớp chạy advice |
| --- | --- | --- | --- |
| singleton | Một instance aspect dùng chung | 1 instance aspect | 1, 2, 3, 4 |
| perthis | Từng proxy P1, P2 | 2 instance aspect | P1: 1→2; P2: 1→2 |
| pertarget | Từng target T1, T2 | 2 instance aspect | T1: 1→2; T2: 1→2 |

**Bảng trên chỉ minh họa hai proxy trỏ đến hai target khác nhau.** Vì vậy perthis và pertarget có kết quả giống nhau trong tình huống này. Điểm làm hai mô hình khác nhau là **mối quan hệ proxy–target**, đặc biệt khi nhiều proxy dùng chung một target.

Không được hiểu perthis là “một instance cho từng request”, pertarget là “một instance cho từng lời gọi”, hoặc prototype bean là “đương nhiên tạo mới mỗi lần advice chạy”. Đây là ba nhầm lẫn phổ biến.

## 3. Mô hình mặc định: singleton

Khai báo:

~~~java
@Aspect
public class SingletonCounter {
    // Các trường của instance này được dùng chung
}
~~~

Spring AOP mặc định sử dụng mô hình **singleton aspect**. Khi aspect được khai báo như Spring bean mặc định qua **@Component** hoặc **@Bean**, ta thường có một instance aspect trong context cho bean definition đó.

Nếu cùng aspect được dùng để advise nhiều service, advice sẽ chạy trên cùng instance aspect. Điều này hữu ích với aspect không giữ trạng thái theo đối tượng như logging, metrics, xác thực chính sách hoặc đánh dấu tracing. Tuy nhiên, lưu dữ liệu của từng invocation trong mutable field của singleton aspect có thể tạo race condition khi nhiều thread cùng gọi.

Phân biệt hai ý:

- **Mô hình singleton aspect**: một instance aspect cho những join point liên quan đến aspect đó.
- **Singleton Spring bean scope**: cùng bean name trong một container thường luôn trả về cùng instance.

Trong cấu hình thông dụng, hai khái niệm đi cùng nhau, nhưng không nên coi chúng là một annotation duy nhất. Spring có thể hỗ trợ aspect model singleton trong những trường hợp bean definition không khai báo singleton; lúc đó vòng đời Spring bean và vòng đời aspect cần được phân tích riêng. Cách dễ kiểm soát cho ví dụ cơ bản vẫn là một bean aspect singleton.

## 4. Mô hình perthis: một instance theo proxy

Khai báo:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
public class PerThisCounter {
    // Mỗi proxy phù hợp có state của aspect riêng
}
~~~

Trong Spring AOP, **this** tại join point chỉ tới **đối tượng proxy** mà client gọi. **perthis(...)** liên kết instance aspect với đối tượng proxy phù hợp với biểu thức bên trong mệnh đề perthis.

Với sơ đồ:

~~~text
P1 (proxy) ---> T1 (target)  ---> aspect A1
P2 (proxy) ---> T2 (target)  ---> aspect A2
~~~

A1 và A2 có thể giữ trạng thái riêng. Instance liên kết được khởi tạo khi đối tượng tương ứng lần đầu tham gia một join point khớp mệnh đề perthis; nó không cần được tạo sẵn chỉ vì ApplicationContext khởi động. Trước khi aspect instance được tạo, advice thuộc instance đó chưa thể chạy; sau khi đã tạo, advice chạy ở các join point phù hợp của đối tượng liên kết. Không được mặc định rằng mọi method trên cùng service sẽ đều khớp mệnh đề hoặc mọi lời gọi Java đều bị Spring AOP chặn.

**Điều kiện Spring quan trọng:** Bean definition của **PerThisCounter** phải là **prototype**, ví dụ:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public PerThisCounter perThisCounter() {
    return new PerThisCounter();
}
~~~

Chỉ dùng **@Aspect("perthis(...)")** trên một **@Component** singleton mặc định là cấu hình sai. Spring không thể cấp một instance aspect khác nhau cho từng proxy nếu bean aspect luôn trả về một singleton; có thể xuất hiện lỗi về aspect instantiation model không tương thích với singleton bean.

## 5. Mô hình pertarget: một instance theo target

Khai báo:

~~~java
@Aspect("pertarget(execution(* demo.Job.execute(..)))")
public class PerTargetCounter {
    // Mỗi target phù hợp có state của aspect riêng
}
~~~

Spring AOP bọc **target** bằng một proxy. **pertarget(...)** liên kết aspect instance với target tương ứng tại những join point phù hợp. Với một proxy cho mỗi target, số aspect instance có vẻ giống perthis. Khác biệt rõ ràng ở trường hợp hai proxy P1 và P2 cùng bọc một đối tượng T:

~~~text
PERTHIS                         PERTARGET

P1 ------> T                    P1 ------> T
  |                               |        ^
  +---- aspect A1                 |        |
                                 +------ aspect A
P2 ------> T                      |        ^
  |                               |        |
  +---- aspect A2                 P2 ------> T

2 instance aspect                  1 instance aspect
nếu P1/P2 đều khớp                 cho cùng target T
~~~

Đây là **mô hình khái niệm** để phân biệt identity, không phải chương trình độc lập tạo hai proxy thủ công. Khi Spring tạo proxy, các cấu hình wrapper/advisor có thể khiến cách tổ chức target trở nên phức tạp; không được suy ra chắc chắn số proxy/target chỉ từ số bean name.

Giống perthis, bean aspect pertarget phải là bean **không phải singleton**, thực tế nên khai báo **prototype**:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public PerTargetCounter perTargetCounter() {
    return new PerTargetCounter();
}
~~~

**Prototype ở đây là cơ chế cung cấp các instance aspect mới theo yêu cầu Spring AOP.** Không có nghĩa Spring tạo một aspect mới trên mỗi lần gọi `execute()`. Với cùng target đã được liên kết, các lời gọi phù hợp tiếp tục dùng instance aspect của target đó.

## 6. @Scope("prototype") và per-clause không thay thế nhau

Đây là phần đặc biệt quan trọng khi làm việc với **Spring bean** và **Spring AOP**.

| Cấu hình | Ý nghĩa | Kết luận |
| --- | --- | --- |
| **@Aspect** với bean singleton | Mô hình aspect mặc định | Một instance dùng chung |
| **@Aspect("perthis(...)")** với bean prototype | Aspect instance gắn theo proxy | Phù hợp mô hình perthis |
| **@Aspect("pertarget(...)")** với bean prototype | Aspect instance gắn theo target | Phù hợp mô hình pertarget |
| **@Aspect("perthis(...)")** nhưng aspect bean singleton | Per-clause cần nhiều instance, bean chỉ có một | Sai cấu hình; Spring có thể báo lỗi |
| **@Scope("prototype")** nhưng chỉ **@Aspect** không có per-clause | Mỗi lần lấy prototype bean có thể tạo instance mới, nhưng aspect model vẫn mặc định singleton | Không tự tạo ngữ nghĩa perthis/pertarget |

Lưu ý kỹ thuật: **@Scope** áp dụng cho Spring bean definition, còn **perthis/pertarget** nằm trong metadata mô tả **aspect instantiation model**. Spring AOP kiểm tra hai mặt cấu hình để xây dựng aspect instance factory phù hợp.

Nếu dùng **@Component** thay **@Bean**, cần đặt scope trực tiếp trên lớp:

~~~java
@Aspect("pertarget(execution(* demo.Job.execute(..)))")
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PerTargetCounter {
    // ...
}
~~~

Đoạn trên là **phương án component scan**, không dùng đồng thời với phương án đăng ký cùng aspect bằng **@Bean**. Phải có **@ComponentScan** bao phủ package chứa class và **@EnableAspectJAutoProxy** trong context liên quan.

## 7. Dự án Java 17+ để quan sát cả ba mô hình

Ví dụ dùng **Spring Framework 6.2.12**, **Java 17+** và **Maven 3.9+**. Ta tạo ba ApplicationContext **độc lập**, mỗi context đăng ký **một loại aspect** để log không bị trộn với advice của mô hình khác.

Cấu trúc:

~~~text
spring-aop-instantiation/
├── pom.xml
└── src/main/java/demo/
    ├── Job.java
    ├── JobImpl.java
    ├── SingletonCounter.java
    ├── PerThisCounter.java
    ├── PerTargetCounter.java
    └── App.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-instantiation</artifactId>
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

**spring-context** cung cấp Java-based ApplicationContext và kéo theo Spring AOP. **aspectjweaver** cung cấp các kiểu annotation/pointcut mà Spring dùng để xử lý phong cách **@AspectJ**. Ví dụ vẫn dùng **proxy-based Spring AOP**, không dùng weaving agent.

### 7.2. Service interface và target

**src/main/java/demo/Job.java**

~~~java
package demo;

public interface Job {
    void execute();
}
~~~

**src/main/java/demo/JobImpl.java**

~~~java
package demo;

public class JobImpl implements Job {

    private final String label;

    public JobImpl(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }

    @Override
    public void execute() {
        System.out.println("SERVICE " + label);
    }
}
~~~

Tạo hai instance khác nhau **JobImpl("A")** và **JobImpl("B")** bằng hai phương thức **@Bean**. Client chỉ lấy kiểu **Job**, vì với interface và cấu hình mặc định, Spring Framework thuần có thể tạo **JDK dynamic proxy**.

### 7.3. Singleton aspect

**src/main/java/demo/SingletonCounter.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class SingletonCounter {

    private int calls;

    @Before("execution(* demo.Job.execute(..))")
    public void before(JoinPoint joinPoint) {
        calls++;
        String label = ((JobImpl) joinPoint.getTarget()).label();
        System.out.println("ASPECT singleton count=" + calls
                + " target=" + label);
    }
}
~~~

Một instance được đăng ký vào context. Mọi advice invocation **ở context đó** làm tăng cùng một trường **calls**. Bộ đếm `int` cố tình đơn giản vì chương trình chạy tuần tự; nó không an toàn khi nhiều thread đồng thời cập nhật.

### 7.4. Perthis aspect

**src/main/java/demo/PerThisCounter.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect("perthis(execution(* demo.Job.execute(..)))")
public class PerThisCounter {

    private int calls;

    @Before("execution(* demo.Job.execute(..))")
    public void before(JoinPoint joinPoint) {
        calls++;
        String label = ((JobImpl) joinPoint.getTarget()).label();
        System.out.println("ASPECT perthis count=" + calls
                + " target=" + label);
    }
}
~~~

Mệnh đề **perthis(...)** quyết định **lúc nào và với proxy nào** một instance được liên kết. Advice **@Before(...)** là logic chạy tại các join point phù hợp sau khi instance đã có thể được dùng. Trong ví dụ, cả hai đều nói tới **Job.execute()** để dễ kiểm tra.

Chỉ dùng lớp này khi bean definition **PerThisCounter** được cấu hình prototype như ở mục 7.6.

### 7.5. Pertarget aspect

**src/main/java/demo/PerTargetCounter.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect("pertarget(execution(* demo.Job.execute(..)))")
public class PerTargetCounter {

    private int calls;

    @Before("execution(* demo.Job.execute(..))")
    public void before(JoinPoint joinPoint) {
        calls++;
        String label = ((JobImpl) joinPoint.getTarget()).label();
        System.out.println("ASPECT pertarget count=" + calls
                + " target=" + label);
    }
}
~~~

Dòng **joinPoint.getTarget()** dùng để lấy **target object** tại invocation. Đây không phải API quyết định pertarget; chính metadata của **@Aspect("pertarget(...)")** chỉ định mô hình. Khi một instance target tiếp tục được gọi qua proxy phù hợp, state trong aspect liên kết với nó được tái sử dụng.

### 7.6. Ba cấu hình Spring riêng biệt

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Scope;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;

public class App {

    @Configuration(proxyBeanMethods = false)
    static class ServiceBeans {

        @Bean("first")
        Job first() {
            return new JobImpl("A");
        }

        @Bean("second")
        Job second() {
            return new JobImpl("B");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    @EnableAspectJAutoProxy
    static class SingletonConfig {

        @Bean
        SingletonCounter singletonCounter() {
            return new SingletonCounter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    @EnableAspectJAutoProxy
    static class PerThisConfig {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        PerThisCounter perThisCounter() {
            return new PerThisCounter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    @EnableAspectJAutoProxy
    static class PerTargetConfig {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        PerTargetCounter perTargetCounter() {
            return new PerTargetCounter();
        }
    }

    private static void run(String mode, Class<?> config) {
        try (var context =
                     new AnnotationConfigApplicationContext(config)) {
            Job first = context.getBean("first", Job.class);
            Job second = context.getBean("second", Job.class);

            System.out.println("=== " + mode + " ===");
            first.execute();
            second.execute();
            first.execute();
            second.execute();
        }
    }

    public static void main(String[] args) {
        run("singleton", SingletonConfig.class);
        run("perthis", PerThisConfig.class);
        run("pertarget", PerTargetConfig.class);
    }
}
~~~

**Đọc kỹ cấu hình:**

1. **ServiceBeans** tạo hai bean tên **first** và **second**. Không phải một bean hai tên alias: mỗi phương thức tạo **target JobImpl khác nhau**.
2. Mỗi context đều dùng **@Import(ServiceBeans.class)** và **@EnableAspectJAutoProxy**.
3. Mỗi context chỉ có **một** aspect bean definition; không cần component scan và không vô tình đăng ký cả ba aspect.
4. **SingletonConfig** tạo bean aspect singleton theo mặc định; không có per-clause.
5. **PerThisConfig** tạo bean aspect prototype, có perthis trong class metadata.
6. **PerTargetConfig** cũng tạo bean aspect prototype, có pertarget trong class metadata.
7. Ba context được tạo và đóng tuần tự. **Không gộp số instance giữa ba context**; số instance phụ thuộc từng ApplicationContext.
8. Các phương thức **@Bean** dùng package-private trong ví dụ cùng package. Lớp cấu hình được khai báo **static nested class** để Spring có thể nạp không cần instance của outer App.

Việc **@Bean** gọi **new** không làm mất Spring AOP: object được trả cho container quản lý. Ngược lại, nếu client tự tạo **new JobImpl("A")** và gọi trực tiếp, Spring proxy không nằm trên đường gọi nên advice không chạy.

### 7.7. Chạy chương trình

Từ thư mục **spring-aop-instantiation**, chạy:

~~~bash
mvn -q clean compile exec:java
~~~

**Các dòng logic theo thứ tự gọi trong chương trình:**

Đối với **singleton**, mỗi lời gọi đều dùng cùng một aspect instance, vì vậy đầu ra phần này là:

~~~text
=== singleton ===
ASPECT singleton count=1 target=A
SERVICE A
ASPECT singleton count=2 target=B
SERVICE B
ASPECT singleton count=3 target=A
SERVICE A
ASPECT singleton count=4 target=B
SERVICE B
~~~

Trong hai phần **perthis** và **pertarget**, vì **first** và **second** có hai proxy và hai target độc lập, state advice sẽ được quản lý theo từng đối tượng tương ứng. Ta kiểm tra rằng dòng log **ASPECT perthis/perttarget** xuất hiện trước dòng **SERVICE** của những lời gọi đã được advice, và thấy bộ đếm của A và B tăng **độc lập** (các lần advice trên A: 1, 2; các lần advice trên B: 1, 2).

**Lưu ý về lần gọi đầu:** Mệnh đề per-clause dùng join point đầu tiên để kích hoạt việc tạo instance; tài liệu Spring mô tả rằng trước khi instance được tạo, advice của instance đó chưa chạy. Vì vậy không nên dựa vào một dòng log duy nhất của lần gọi đầu để đo số lần aspect được khởi tạo. Khi kiểm thử lifecycle sâu, hãy kiểm tra đủ chuỗi invocation và quan sát trạng thái sau khi instance đã gắn với proxy/target.

Để quan sát chính xác hơn khi debug, đặt breakpoint vào constructor của **PerThisCounter** và **PerTargetCounter**, ghi lại identity của aspect instance, sau đó đặt breakpoint ở **before(...)**. Bạn có thể phân biệt **thời điểm khởi tạo** với **thời điểm một advice invocation bắt đầu**.

> Các kết quả so sánh số lượng instance trong bài là **mô hình expected behavior** theo cấu hình. Những đoạn code minh họa chỉ dựa trên stdout được nêu rõ là quan sát logic; khi chương trình chạy trong IDE/Maven, các thông báo framework riêng không nằm trong phần expected output.

## 8. Phân biệt chính xác proxy (this) và target

Trong Spring AOP, đối tượng mà client giữ thường là proxy. Tại join point:

- **this**: tham chiếu tới **Spring AOP proxy**.
- **target**: tham chiếu tới **đối tượng ứng dụng** nằm phía sau proxy.

Hình dung hai đối tượng proxy cùng trỏ đến target T:

| Identity | perthis | pertarget |
| --- | --- | --- |
| P1 → T | Aspect instance A1 | Aspect instance A |
| P2 → T | Aspect instance A2 | Vẫn aspect instance A |
| Gọi lại P1 → T | Dùng A1 | Dùng A |
| Gọi lại P2 → T | Dùng A2 | Dùng A |

Nếu P1 và P2 là hai **alias bean name cùng trả về một proxy**, không có hai proxy identity khác nhau; perthis không tạo thêm instance chỉ vì đổi tên alias. Ngược lại, hai target khác nhau thường dẫn tới hai liên kết pertarget dù cùng lớp triển khai.

**Proxy tạo bằng JDK hay class-based proxy** chỉ quyết định cách Spring tạo đối tượng trung gian và phương thức nào có thể được intercept. Quy tắc phân biệt proxy identity/target identity vẫn cần được áp dụng khi phân tích perthis/pertarget.

### Phân biệt biến this trong Java và this trong pointcut

Trong class **JobImpl**, **this** của Java là object target khi phương thức đang chạy. Trong biểu thức Spring AOP **this(...)**, ngữ nghĩa chọn/ghép đối tượng lại nói tới **proxy** của Spring AOP. Không suy luận ngược chỉ từ từ khóa giống nhau.

**joinPoint.getThis()** trả proxy; **joinPoint.getTarget()** trả target. Đoạn kiểm tra minh họa bên trong advice:

~~~java
Object proxy = joinPoint.getThis();
Object target = joinPoint.getTarget();
System.out.println("SAME_OBJECT " + (proxy == target));
~~~

Đoạn này là **fragment thêm vào advice**, chưa phải file Java độc lập. Với proxy thực sự bọc target riêng biệt, giá trị thường là **false**. Kết quả này chưa tự chứng minh đang dùng perthis hay pertarget; phải kết hợp với mô hình aspect đã khai báo và identity của các đối tượng.

## 9. Mối quan hệ giữa per-clause và advice pointcut

Ví dụ:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
public class DemoAspect {

    @Before("execution(* demo.Job.execute(..))")
    public void beforeExecution() {
        // ...
    }
}
~~~

Có **hai biểu thức**:

1. **Trong perthis(...)**: mô tả các join point kích hoạt/liên kết một aspect instance với proxy.
2. **Trong @Before(...)**: mô tả những join point mà logic advice muốn xử lý.

Hai biểu thức có thể khác nhau. Tuy nhiên, nếu chọn một per-clause quá hẹp so với advice, advice có thể không có instance gắn với proxy/target cho lời gọi mong muốn. Nếu quá rộng, nhiều service có thể được gắn instance không cần thiết.

Trong Spring AOP, chỉ các **method-execution join point trên Spring bean** được proxy hỗ trợ. Việc dùng **call(...)**, truy cập field, constructor execution hoặc những designator không được Spring AOP hỗ trợ sẽ không trở thành hợp lệ chỉ nhờ perthis hoặc pertarget. Với JDK proxy, các lời gọi public method trên interface của proxy là đường đi chuẩn.

**Self-invocation** vẫn là giới hạn: nếu phương thức trên target gọi **this.execute()** ngay bên trong, lời gọi Java trực tiếp đó không quay qua Spring proxy; không có invocation advisor mới chỉ vì aspect dùng perthis hoặc pertarget.

## 10. Khi nào aspect instance được tạo và hủy?

### 10.1. Singleton

Spring container thường tạo aspect singleton khi khởi tạo các singleton cần thiết trong context (trừ khi có lazy initialization hoặc cấu hình đặc biệt). Một instance đó tồn tại cùng vòng đời Spring bean, và Spring quản lý các callback thích hợp khi đóng context.

Khi aspect là singleton, **không tạo mới per-proxy hoặc per-method-call** chỉ vì hai service khác nhau được advise.

### 10.2. Perthis và pertarget

Spring AOP sử dụng một aspect instance factory có khả năng cung cấp nhiều instance khi cần. Mỗi proxy hoặc target phù hợp được gắn một instance riêng sau khi per-clause khớp. Instance đó gắn với đối tượng tương ứng; không phải lifecycle request/session hay đơn vị thread.

Với **Spring prototype scope**, container tạo và inject bean instance nhưng theo mặc định **không đảm bảo gọi destroy callback cho tất cả các instance prototype**. Do đó, không nên đặt các tài nguyên cần cleanup phức tạp trực tiếp vào từng aspect perthis/pertarget rồi mặc nhiên tin rằng đóng context sẽ hủy từng instance như singleton. Nếu aspect cần kết nối, pool, cache hoặc tài nguyên sống dài, nên inject một Spring bean quản lý vòng đời riêng, tránh mỗi aspect instance tự sở hữu tài nguyên khó thu hồi.

Việc tạo nhiều instance cũng không có nghĩa aspect giữ state của **mỗi yêu cầu HTTP**. Nhiều request có thể gọi cùng proxy và cùng target; khi đó vẫn truy cập một aspect instance tương ứng và cần thiết kế thread-safe.

## 11. Vì sao không dùng @Scope("request") hoặc @Scope("prototype") thay perthis?

Nhiều Spring bean scope thường gây nhầm với AOP instantiation model:

| Cơ chế | Quyết định theo | Câu hỏi phù hợp |
| --- | --- | --- |
| Bean **singleton** | Bean name trong Spring container | Mỗi lần lấy cùng bean trả object nào? |
| Bean **prototype** | Mỗi lần container được yêu cầu tạo/lấy bean | Có thể tạo một bean instance mới không? |
| Bean **request** | Web request scope đang hoạt động | Mỗi request dùng object nào? |
| Aspect **perthis** | Proxy identity ở join point khớp | Một proxy liên kết với aspect instance nào? |
| Aspect **pertarget** | Target identity ở join point khớp | Một target liên kết với aspect instance nào? |

**@Scope("prototype") trên aspect perthis/pertarget là điều kiện để Spring cấp instance theo mô hình aspect**, không có nghĩa hai thuật ngữ tương đương. Nếu yêu cầu thật sự là đếm giao dịch theo HTTP request, perthis/pertarget có thể không phù hợp: cùng service proxy singleton phục vụ nhiều request sẽ vẫn dùng chung instance aspect. Khi đó cần xử lý dữ liệu theo request bằng dependency/scope thích hợp, thay vì gán ý nghĩa request cho perthis.

## 12. Lỗi cấu hình và cách chẩn đoán

### 12.1. Khai báo perthis hoặc pertarget trên aspect bean singleton

Ví dụ sai:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
@Component
public class BrokenAspect {
    // ...
}
~~~

Trong component scan mặc định, **BrokenAspect** được đăng ký singleton. Mô hình perthis cần nhiều aspect instance nên không tương thích. Cách sửa:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class FixedAspect {
    // ...
}
~~~

Hai snippet trên **chỉ minh họa khác biệt cấu hình**; chúng không phải các file trong dự án chạy ở mục 7. Khi copy, cần import đúng **Aspect**, **Component**, **Scope**, **ConfigurableBeanFactory** và có phương thức advice cần thiết. Lỗi có thể xuất hiện trong quá trình Spring xây dựng advisor hoặc proxy, với thông báo đại ý rằng bean singleton nhưng aspect instantiation model không phải singleton.

### 12.2. Có @Aspect và @Scope nhưng không có bean

**@Aspect** không tự đăng ký Spring bean. Nếu không dùng **@Component** và không có **@Bean**, aspect có thể không được tìm thấy. Trong ví dụ ở mục 7, aspect được đăng ký qua **@Bean** nên các class aspect không cần **@Component**.

### 12.3. Có bean aspect nhưng chưa bật Spring AOP

Trong Spring Framework thuần, cần **@EnableAspectJAutoProxy** hoặc cấu hình hạ tầng tương đương. Việc khởi tạo một instance aspect thông thường không có nghĩa advice sẽ tự chạy.

### 12.4. Nhầm bean alias với nhiều target/proxy

Hai bean name có thể alias tới cùng object, hoặc hai bean khác nhau có cùng implementation class. Muốn suy ra số instance perthis/pertarget cần quan sát **identity thực**, không chỉ tên hoặc lớp. Công cụ gợi ý: **AopUtils.isAopProxy(...)**, **System.identityHashCode(...)** khi debug, và so sánh **==** cho hai tham chiếu lấy từ Spring context.

### 12.5. Có mutable state nhưng nhiều thread cùng sử dụng

Ngay cả perthis/pertarget cũng **không phải thread-local**. Nếu nhiều thread dùng cùng proxy hoặc target, chúng có thể đồng thời cập nhật trường **calls** của cùng một aspect instance.

Khi cần đếm chính xác trong môi trường đồng thời, thay `int calls` bằng **AtomicInteger**:

~~~java
private final java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

int count = calls.incrementAndGet();
~~~

Đây là **fragment thay thế cho trường và phép tăng trong aspect**, không phải một chương trình độc lập. AtomicInteger chỉ giải quyết thao tác tăng đơn lẻ; logic phối hợp nhiều state khác vẫn phải được thiết kế cho concurrency.

### 12.6. Advice không chạy trong một số lời gọi

Phải kiểm tra từng điều kiện: service thật sự là Spring-managed bean, có proxy phù hợp, biểu thức advice có match, per-clause có khớp đối tượng và lời gọi có đi qua proxy không. Không nên đổ mọi trường hợp thiếu log cho sai instantiation model.

## 13. Bảng lựa chọn cho bài toán thực tế

| Mục đích | Hướng dùng ban đầu | Lý do |
| --- | --- | --- |
| Ghi log, đo thời gian, theo dõi call count toàn hệ thống | **singleton** + collaborator thread-safe | Đơn giản và ít instance |
| Giữ state liên quan đến một **proxy cụ thể** | **perthis** | Identity là Spring proxy |
| Giữ state liên quan đến một **target cụ thể** | **pertarget** | Identity là object nằm sau proxy |
| Giữ dữ liệu riêng từng HTTP request | Request-scoped bean/context thích hợp | Không đánh đồng request và proxy/target |
| Muốn dữ liệu riêng cho từng method invocation | Biến cục bộ trong advice | Tránh giữ state không cần thiết trong aspect |
| Muốn tạo bean phụ thuộc mới mỗi lần dùng | ObjectProvider, lookup hoặc factory phù hợp | Khác với aspect instantiation model |

Trong phần lớn ứng dụng Spring dùng aspect để logging, validation phụ trợ hoặc tracing, **singleton stateless aspect** là lựa chọn dễ bảo trì nhất. Chỉ chuyển sang perthis/pertarget khi thực sự có nhu cầu **lưu trạng thái gắn với identity của proxy/target**, và đã hiểu quan hệ giữa các đối tượng trong container.

## 14. Câu hỏi tự đánh giá

**1. Tại sao @Aspect("perthis(...)") thường phải đi cùng @Scope("prototype")?**

Vì Spring cần khả năng tạo nhiều aspect instance để gắn theo các proxy khác nhau. Bean singleton mặc định chỉ có một instance và không thỏa mô hình perthis.

**2. Một ApplicationContext có ba service bean thì có chắc pertarget tạo ba aspect instance ngay khi startup không?**

Không. Số instance phụ thuộc số **target phù hợp được kích hoạt qua join point khớp**, không chỉ số bean definition. Các instance có thể được tạo theo nhu cầu khi lần đầu join point tương ứng xuất hiện.

**3. Có hai proxy P1 và P2 cùng bọc target T. perthis và pertarget khác nhau thế nào?**

Nếu cả hai proxy đều kích hoạt per-clause: perthis có thể liên kết **hai** aspect instance theo P1 và P2; pertarget liên kết **một** aspect instance theo target T.

**4. Vì sao hai bean service singleton khác nhau có thể tạo hai pertarget aspect instance?**

Vì mỗi service bean có thể là một target object độc lập. Singleton scope của **mỗi service bean** không nói rằng tất cả service dùng chung một object.

**5. Perthis có nghĩa một instance aspect cho mỗi thread không?**

Không. Nó gắn với proxy identity. Nhiều thread gọi cùng proxy có thể cùng chạm vào một aspect instance.

**6. Chỉ thêm @Scope("prototype") cho một @Aspect thông thường đã tương đương pertarget chưa?**

Chưa. Prototype kiểm soát cách container cung cấp bean; pertarget là metadata cụ thể trong **@Aspect("pertarget(...)")**.

**7. Vì sao hai lời gọi từ cùng client có thể không chạy advice dù bean đã được tạo?**

Vì chỉ những method execution khớp pointcut và đi qua Spring proxy mới được advise. Self-invocation trên target hoặc method không khớp không tự chạy advice mới.

**8. Có nên dùng instance field của singleton aspect để lưu mã request hiện tại không?**

Không. Singleton aspect có thể được dùng đồng thời bởi nhiều request và thread. Dữ liệu invocation nên nằm ở biến cục bộ hoặc một cơ chế context được thiết kế rõ ràng.

## 15. Checklist cấu hình Spring AOP

- Xác định **ApplicationContext** chứa target bean và aspect bean.
- Bật **@EnableAspectJAutoProxy** trong Spring Framework thuần, hoặc xác minh cấu hình AOP tương ứng đã có.
- Đăng ký aspect bằng **@Component/@Bean**, không chỉ thêm **@Aspect**.
- Chọn **@Aspect** mặc định cho singleton, **@Aspect("perthis(...)")** hoặc **@Aspect("pertarget(...)")** khi muốn instance gắn theo đối tượng.
- Với perthis/pertarget, cấu hình aspect bean **prototype**, tránh bean singleton mặc định.
- Giữ per-clause và advice pointcut rõ ràng, test đúng các invocation cần chặn.
- Kiểm tra **proxy identity**, **target identity** và chuyện nhiều bean name có thể cùng object.
- Thiết kế mutable state an toàn khi nhiều thread có thể dùng cùng aspect instance.
- Không suy ra advice chạy chỉ vì Spring có aspect bean hoặc service bean; kiểm tra hành vi thực.

## 16. Tài liệu chính thức để đối chiếu

- **Spring Framework — Aspect Instantiation Models**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- **Spring Framework — Declaring a Pointcut** (khác nhau giữa this và target trong Spring AOP): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- **Spring Framework — @AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — Bean Scopes** (singleton/prototype của container): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html

**Điểm cần ghi nhớ:** Spring AOP hỗ trợ các aspect instantiation model singleton, perthis và pertarget. Singleton dùng chung một instance; perthis liên kết state của aspect với Spring AOP proxy; pertarget liên kết với target object. Cấu hình **@Scope("prototype")** là điều kiện quan trọng để perthis/pertarget hoạt động với Spring-managed aspect, nhưng phạm vi prototype của bean và mô hình tạo instance aspect không phải cùng một khái niệm.
