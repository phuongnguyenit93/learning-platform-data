# Scope của bean đích không tự thay đổi scope của aspect trong Spring AOP

## 1. Tình huống hay bị hiểu nhầm

Một Spring `@Aspect` ghi nhận lời gọi của `JobService`. Người phát triển đổi `JobService` từ singleton thành `@Scope("prototype")` và mong rằng mỗi `JobService` cũng có một bản sao aspect riêng. Trong Spring AOP, suy luận đó **không đúng**.

**Scope của target bean, vòng đời của Spring proxy và vòng đời của bean `@Aspect` là những quyết định khác nhau.** Một singleton aspect vẫn có thể tư vấn nhiều target instances, kể cả các target có scope prototype/request/session.

Bài này chỉ nói về **Aspect trong Spring**, Spring bean factory, Spring AOP proxy và phạm vi thực thi advice. Các kiến thức AOP tổng quát không được lặp lại.

## 2. Ba đối tượng phải phân biệt

| Thành phần | Vai trò | Ai quyết định lifecycle? |
| --- | --- | --- |
| **Aspect bean** | Chứa các method `@Before`, `@Around`, ... và dependency của advice | Spring IoC container, bean definition của aspect; mặc định singleton với `@Component` hoặc `@Bean` |
| **Target bean** | Chứa logic nghiệp vụ được advice áp dụng | Bean definition của target: singleton, prototype, request, session hoặc custom scope |
| **AOP proxy** | Đối tượng mà caller thực sự gọi để interceptor/advisor chạy | Cấu hình proxy/advisor và bean lifecycle; có thể thêm scoped proxy khi cần |

Chỉ nhìn vào `this`, `getClass()` hoặc danh tính proxy không đủ để kết luận target đang có scope nào. Với một **scoped proxy** request/session, một reference proxy có thể tồn tại lâu và delegate đến các target khác nhau theo scope; với **prototype bean** lấy trực tiếp từ `getBean()`, mỗi lần lấy có thể tạo một instance/proxy mới.

Trong một `@Aspect` singleton, fields là shared state của các lời gọi advice. Hai target khác nhau **không** biến các fields đó thành state riêng.

## 3. Ví dụ sai: lưu state của target trong field aspect

~~~java
@Aspect
class WrongTrackingAspect {
    private String lastJobId;

    @Before("execution(* demo.JobService.execute(..))")
    public void before(JoinPoint jp) {
        lastJobId = ((JobService) jp.getTarget()).toString();
    }

    @After("execution(* demo.JobService.execute(..))")
    public void after() {
        // lastJobId có thể do một target/proxy/lời gọi khác ghi vào.
        System.out.println("completed " + lastJobId);
    }
}
~~~

Dù mọi `JobService` là prototype, `WrongTrackingAspect` singleton vẫn có một field `lastJobId`. Khi hai lời gọi xen nhau, người dùng A có thể ghi nhầm ID của B. Sai lầm tương tự xảy ra nếu lưu `JoinPoint`, request context, exception, `StopWatch`, `startNanos` hoặc danh sách arguments vào field aspect.

Cách đúng nhất cho một phép đo bao quanh invocation thường là **local variable**:

~~~java
@Around("execution(* demo.JobService.execute(..))")
public Object time(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        // Ghi metric bằng dependency thread-safe; không lưu started trên field.
        System.out.println("elapsedNanos=" + elapsed);
    }
}
~~~

Đây là snippet về scope, không phải ví dụ cho stdout cố định: thời gian là không xác định và Spring `@Around` phải được đăng ký vào container để chạy.

## 4. Demo Java 17 + Spring Framework: target prototype, aspect singleton

Demo sau minh họa **hai target khác nhau**, **hai proxy**, nhưng **một aspect bean** với tổng số lượt advice bằng hai. Tất cả code cần thiết được liệt kê.

~~~text
spring-aop-target-vs-aspect-scope/
  pom.xml
  src/main/java/demo/JobService.java
  src/main/java/demo/JobServiceImpl.java
  src/main/java/demo/AuditAspect.java
  src/main/java/demo/App.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aop-target-vs-aspect-scope</artifactId>
  <version>1.0.0</version>
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
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.25</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**JobService.java**

~~~java
package demo;

public interface JobService {
    String execute();
}
~~~

**JobServiceImpl.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class JobServiceImpl implements JobService {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    @Override
    public String execute() {
        return "job-" + id;
    }
}
~~~

Mỗi target instance giữ `id` riêng. `NEXT_ID` chỉ phục vụ việc nhìn thấy rằng constructor đã tạo hai target khác nhau; không phải state của aspect.

**AuditAspect.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(* demo.JobService.execute(..))")
    public void beforeExecution() {
        System.out.println("aspectCall=" + calls.incrementAndGet());
    }

    public int callCount() {
        return calls.get();
    }
}
~~~

Bộ đếm aspect là shared state **có chủ đích** và dùng `AtomicInteger` để an toàn cho tăng đếm đồng thời. Nếu cần tách metric theo target, nên dùng key ổn định trong một concurrent registry và xem xét cleanup/lifecycle, thay vì đặt một field `lastTarget` trên singleton aspect.

**App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class App {
    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect(); // singleton theo mặc định của @Bean
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public JobService jobService() {
        return new JobServiceImpl();
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(App.class)) {
            JobService one = ctx.getBean(JobService.class);
            JobService two = ctx.getBean(JobService.class);

            AuditAspect aspectOne = ctx.getBean(AuditAspect.class);
            AuditAspect aspectTwo = ctx.getBean(AuditAspect.class);

            System.out.println("first=" + one.execute());
            System.out.println("second=" + two.execute());
            System.out.println("differentProxies=" + (one != two));
            System.out.println("aopProxy=" + AopUtils.isAopProxy(one));
            System.out.println("sameAspect=" + (aspectOne == aspectTwo));
            System.out.println("adviceCalls=" + aspectOne.callCount());
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.App
~~~

Kết quả mong đợi của phần `System.out` do ứng dụng sinh ra:

~~~text
aspectCall=1
first=job-1
aspectCall=2
second=job-2
differentProxies=true
aopProxy=true
sameAspect=true
adviceCalls=2
~~~

Lý do: bean method `jobService()` có scope prototype nên hai lần `getBean(JobService.class)` tạo hai target riêng. Spring AOP nhận diện `AuditAspect`, tạo advisor cho `JobService.execute()` và tạo proxy cho từng bean cần advice. Bean `AuditAspect` vẫn singleton, được gọi hai lần và cộng cùng một `AtomicInteger`.

Đây là **expected output được rà soát tĩnh** theo Spring AOP/Java API; không khẳng định đã thực thi Maven trong môi trường hiện tại.

## 5. Đổi scope target sẽ thay đổi điều gì?

### Singleton target

Một bean singleton thường được lấy lặp lại dưới cùng một reference proxy/target trong một context. Nếu được advice matching thì nhiều caller chạy qua cùng proxy; aspect cũng có thể singleton. Target và aspect là **hai singleton khác nhau**, không dùng chung fields của nhau.

### Prototype target

Mỗi lần container tạo bean prototype mới có thể có một target mới và proxy mới. Nếu singleton bean chỉ được inject một lần với prototype bean bình thường, reference prototype ấy **không tự đổi target sau mỗi lần gọi method**. Muốn lấy instance mới trên từng nhu cầu, dùng `ObjectProvider<JobService>` hoặc lookup method phù hợp:

~~~java
@Component
class WorkCoordinator {
    private final ObjectProvider<JobService> jobServices;

    WorkCoordinator(ObjectProvider<JobService> jobServices) {
        this.jobServices = jobServices;
    }

    void runTwice() {
        jobServices.getObject().execute();
        jobServices.getObject().execute();
    }
}
~~~

Snippet cần import `org.springframework.beans.factory.ObjectProvider` và `org.springframework.stereotype.Component`, cùng một bean definition prototype của `JobService`. Dù hai lần có hai target, singleton aspect vẫn được dùng chung.

### Request hoặc session scoped target

Trong web application, scoped proxy có thể là một object được tiêm lâu dài nhưng delegate đến request/session target khác theo context hiện hành. Do đó **proxy reference giống nhau không chứng minh target reference giống nhau**.

Ví dụ annotation thường dùng trong ứng dụng web:

~~~java
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
@Component
class RequestJobService { /* ... */ }
~~~

Đây là đoạn cấu hình minh họa cho môi trường web, cần import `org.springframework.context.annotation.Scope`, `ScopedProxyMode`, `Component`; ứng dụng demo Maven ở phần 4 không cần request scope và không tạo web request context.

## 6. Scope của aspect và mô hình instantiation

Trong Spring proxy-based `@AspectJ` support, mô hình phổ biến và được Spring AOP hỗ trợ là **singleton aspects**. Instantiation models như `perthis`, `pertarget`, `percflow` của AspectJ không phải cơ chế tự có của Spring AOP proxy để làm một aspect mới cho mỗi target hoặc invocation.

Nếu cần state riêng cho mỗi target, cân nhắc đặt nó ở target (khi phù hợp domain), ở một dependency được tra cứu theo scope, hoặc dùng registry keyed theo target lifecycle với dọn dẹp rõ ràng. Nếu bài toán thật sự đòi hỏi AspectJ instantiation hoặc field/method join points ngoài Spring proxy execution, đó là yêu cầu thiết kế tích hợp AspectJ weaving riêng, không phải hệ quả của `@Scope` trên một target Spring.

Tránh đặt `@Scope("prototype")` lên aspect và **mặc định giả định** mọi proxy target sẽ nhận aspect instance riêng. Hãy kiểm thử lifecycle thực tế của configuration nếu làm một thiết kế ngoài mô hình singleton thông thường.

## 7. Một số hậu quả khi dùng nhiều ApplicationContext

Singleton nghĩa là **một instance trên từng Spring bean definition trong mỗi container phù hợp**, không nhất thiết là đúng một instance cho toàn JVM.

- Hai ApplicationContext độc lập có thể tạo hai bean aspect singleton khác nhau, mỗi cái có counter riêng.
- Parent/child context và bean visibility có thể khiến một aspect được đăng ký ở nhiều nơi hoặc advisors xuất hiện theo cách không dự kiến.
- Các target prototype trong cùng context vẫn có thể được một aspect singleton tư vấn.
- Nếu test khởi tạo context mới, static fields trong demo `JobServiceImpl.NEXT_ID` có lifecycle khác Spring bean scope; không đồng nhất static Java state với Spring singleton scope.

Để phân biệt, kiểm tra `ctx.getBean(AuditAspect.class)`, `ctx.isSingleton("auditAspect")`, `ctx.isPrototype("jobService")` và inspection qua `AopUtils.isAopProxy`.

## 8. Điều kiện advice thực sự chạy

Thay đổi scope không sửa các giới hạn nền của Spring AOP:

1. Caller phải đi qua Spring AOP proxy. Đối tượng do `new JobServiceImpl()` bên ngoài Spring tạo ra không tự được advice.
2. Self-invocation (`this.execute()` nội bộ target) không đi lại qua proxy tương ứng.
3. Spring AOP tập trung vào **method execution**, không bắt trực tiếp constructor hoặc field access.
4. JDK dynamic proxy thể hiện interface methods; class-based proxy có giới hạn với `final`, `private`, method không override được.
5. Pointcut phải thực sự match target method, và aspect/advisor cần được đăng ký trong đúng context.

Vì vậy, nếu advice có vẻ chạy một lần rồi mất, trước khi kết luận scope “chuyển” sang aspect, cần kiểm tra xem lần gọi thứ hai lấy proxy từ Spring hay dùng raw instance.

## 9. Concurrent calls vẫn dùng chung aspect

Prototype target có thể giảm khả năng chia sẻ fields **bên trong target**, nhưng không loại bỏ khả năng hai lời gọi chạy đồng thời trong cùng aspect singleton. Tương tự, scoped proxy request có thể gọi các target request-specific khác nhau nhưng dùng cùng một aspect recorder.

Không làm như sau:

~~~java
@Aspect
class RiskyAspect {
    private long startedAt;
    private String currentUser;

    @Around("execution(* demo.JobService.execute(..))")
    Object around(ProceedingJoinPoint pjp) throws Throwable {
        startedAt = System.nanoTime();
        currentUser = findUser(); // giả sử helper riêng
        return pjp.proceed();
    }
}
~~~

Hãy đặt `startedAt` và user context vào local variables hoặc một scoped dependency có contract rõ. `ThreadLocal` không phải “per request” tự động trong `@Async`/reactive flows; dùng nó thì phải cleanup/restore và hiểu thread boundary.

`AtomicInteger` phù hợp cho counter, nhưng với invariant liên quan nhiều fields hoặc nhiều map operations cần synchronization/atomic operation tổng thể. Đồng thời, **đừng giữ reference tới target prototype trong map mãi mãi** nếu không có eviction, vì như vậy tạo memory leak.

## 10. Kiểm thử lifecycle và nội dung advice

Một bộ integration test thực tế nên khẳng định:

| Kiểm tra | Kỳ vọng trong cấu hình demo |
| --- | --- |
| `ctx.isPrototype("jobService")` | `true` |
| `ctx.isSingleton("auditAspect")` | `true` |
| `ctx.getBean(JobService.class)` hai lần | Hai reference khác |
| `ctx.getBean(AuditAspect.class)` hai lần | Cùng reference |
| `AopUtils.isAopProxy(jobService)` | `true` |
| Gọi `execute()` trên cả hai proxy | Aspect counter tăng hai |
| Tạo `new JobServiceImpl()` và gọi trực tiếp | Không tự bị Spring advice |
| Hai luồng gọi hai target cùng lúc | Shared aspect fields phải thread-safe |

Khi kiểm thử race, dùng `CountDownLatch`/barrier và assertions thay vì dựa vào thứ tự log giữa threads; scheduler không đảm bảo thứ tự output. Với Java 17, không suy ra tính an toàn luồng chỉ từ việc một lần chạy test cho kết quả đúng.

## 11. Lỗi phổ biến và cách gỡ

**“Target prototype rồi, sao aspect chỉ có một constructor call?”** — Đây là hai bean definitions riêng. Kiểm tra `ctx.isSingleton("auditAspect")` và bean scope riêng của target.

**“Một proxy được inject vào singleton, sao target không đổi?”** — Prototype injection thông thường xảy ra lúc inject. Dùng `ObjectProvider` nếu thực sự cần lấy prototype mới mỗi lần; với request scoped proxy, thiết kế delegate lại theo scope phù hợp.

**“Hai target khác nhau nhưng log lại cùng một user/startTime?”** — Aspect lưu dữ liệu invocation vào field dùng chung. Sửa bằng local variables và dependency thread-safe.

**“Có `@Aspect` rồi nhưng không log?”** — Kiểm tra `@EnableAspectJAutoProxy`, advisor/pointcut, bean managed, JDK/CGLIB proxy, method visibility và self-invocation.

**“Test đơn luồng đúng, production lẫn request?”** — Các lỗi race cần kiểm thử với concurrency và assertions về dữ liệu, không chỉ đếm log.

## 12. Tài liệu đối chiếu

- Spring Framework Reference — `@AspectJ` support và instantiation models: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — `@Bean`, `@Scope` và Java-based configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html

**Kết luận thực hành:** Hãy kiểm tra scope target, scope aspect và dạng proxy **độc lập**. Dù target là prototype hay request-scoped, đừng đặt dữ liệu mỗi invocation vào fields của singleton `@Aspect`; hãy dùng local state và chứng minh thread safety cho dữ liệu thực sự dùng chung.