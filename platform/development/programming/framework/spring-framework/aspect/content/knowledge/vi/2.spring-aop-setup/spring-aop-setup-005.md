# Spring AOP: cấu hình `proxyTargetClass` và `exposeProxy`

## 1. Hai thuộc tính giải quyết hai vấn đề khác nhau

Trong Spring Framework, khi bật AOP bằng `@EnableAspectJAutoProxy`, có hai thuộc tính thường gặp:

```java
@Configuration
@EnableAspectJAutoProxy(
    proxyTargetClass = false,
    exposeProxy = false
)
class AopConfig {
}
```

Đây là **đoạn cấu hình minh họa**, chưa phải ứng dụng chạy độc lập. Hai thuộc tính đều mặc định `false` tại **annotation `@EnableAspectJAutoProxy` của Spring Framework**. Tuy nhiên, Spring Boot thường tự cấu hình **class-based proxy** theo mặc định; cần phân biệt mặc định của annotation với mặc định của Spring Boot.

| Thuộc tính | Câu hỏi mà nó trả lời | `false` | `true` |
| --- | --- | --- | --- |
| `proxyTargetClass` | Spring tạo loại AOP proxy nào? | Ưu tiên JDK dynamic proxy nếu target có interface; nếu không có interface thì dùng class-based proxy | Ép Spring dùng class-based (CGLIB) proxy cho target class có thể proxy |
| `exposeProxy` | Code đang chạy trong một lời gọi AOP có thể truy cập **proxy hiện tại** qua `AopContext.currentProxy()` hay không? | Không công bố current proxy; thông thường sẽ ném `IllegalStateException` nếu cố lấy | Công bố current proxy trong phạm vi lời gọi qua proxy hiện tại; có thể dùng `AopContext.currentProxy()` |

Hai cờ **độc lập về ý nghĩa**. Bật `proxyTargetClass=true` không làm `AopContext.currentProxy()` hoạt động. Bật `exposeProxy=true` không tự đổi JDK proxy thành CGLIB. Cả hai cũng **không khiến mọi bean được proxy**: Spring AOP chỉ tạo proxy khi hạ tầng advice/advisor cần áp dụng cho bean tương ứng.

## 2. Hiểu rõ `proxyTargetClass` trong Spring AOP

Spring AOP dùng proxy cho **các lời gọi phương thức trên Spring-managed bean**. Khi target triển khai ít nhất một interface, hai cách tạo proxy có khác biệt lớn:

### `proxyTargetClass=false`: ưu tiên interface-based proxy

Ví dụ target:

```java
public interface PaymentService {
    void pay();
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {
        System.out.println("pay");
    }
}
```

Nếu bean này được advisor chọn và `proxyTargetClass=false`, Spring thường tạo **JDK dynamic proxy**:

- Proxy triển khai `PaymentService`, nên inject hoặc lấy bean qua **interface** là cách tự nhiên.
- Proxy không phải subclass của `PaymentServiceImpl`. Ép kiểu sang `PaymentServiceImpl` hoặc inject trực tiếp theo implementation class có thể gây lỗi kiểu bean.
- Qua interface proxy, caller chỉ gọi trực tiếp được các phương thức được công bố bởi interface mà proxy triển khai. Một public method chỉ có trên implementation nhưng không thuộc proxy interface sẽ không được expose qua kiểu đó.
- Nếu target **không có interface phù hợp**, Spring vẫn cần dùng class-based proxy; `false` không có nghĩa là luôn JDK proxy.

### `proxyTargetClass=true`: ép class-based proxy

Spring tạo một subclass CGLIB của target (khi có thể). Ngay cả target có interface, loại AOP proxy vẫn hướng đến class:

- Điểm inject có thể khai báo theo concrete target class vì proxy là subclass của class đó.
- Một phương thức có thể được advice mà không cần nằm trên interface, miễn lời gọi **đi qua proxy**, advisor khớp và phương thức có thể bị intercept.
- Target class `final` không thể được tạo subclass proxy. Các phương thức `final` và `private` không thể bị override để advice qua CGLIB; phương thức không đủ khả năng truy cập cũng có thể bị giới hạn.
- Proxy CGLIB không biến self-invocation `this.method()` thành lời gọi qua proxy; vấn đề gọi nội bộ vẫn tồn tại.

**Lưu ý:** `proxyTargetClass=true` chỉ chọn **kiểu proxy** cho bean cần proxy. Nó không yêu cầu Spring chuyển tất cả bean thành CGLIB proxy và không liên quan đến AspectJ weaving.

### Bảng chọn nhanh

| Tình huống | `proxyTargetClass=false` | `proxyTargetClass=true` |
| --- | --- | --- |
| Target có interface và được AOP advice | Thường là JDK proxy | CGLIB proxy |
| Target không có interface | Class-based proxy | Class-based proxy |
| Consumer inject theo interface | Phù hợp | Phù hợp |
| Consumer bắt buộc inject implementation class | Có thể lỗi nếu dùng JDK proxy | Thường hợp lệ nếu class có thể subclass |
| Muốn advice public method chỉ khai báo trên implementation | JDK proxy không expose method đó qua interface | Có thể qua class proxy khi gọi từ bên ngoài |
| Target class `final` | JDK proxy vẫn có thể proxy các interface phù hợp | Không thể subclass final class |
| Target `this.work()` gọi nội bộ | Bỏ qua advice | Vẫn bỏ qua advice |

## 3. `exposeProxy` là gì?

Spring AOP mặc định không cung cấp một API cho business code tự lấy proxy hiện hành. Nếu bật:

```java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
class AopConfig {
}
```

Spring có thể tạm lưu **proxy đang thực hiện lời gọi** trong `ThreadLocal` cho thời gian lời gọi qua AOP proxy. Từ bên trong target của lời gọi đó, code có thể lấy proxy bằng:

```java
Object proxy = AopContext.currentProxy();
```

Trong ví dụ, dòng lấy proxy là **mã minh họa** và chỉ hợp lệ nếu đang thực sự ở trong lời gọi qua proxy có cấu hình expose. Nếu chạy từ main, constructor, `@PostConstruct`, một object tạo bằng `new`, hoặc một thread khác không có invocation context, `AopContext.currentProxy()` sẽ không tìm được proxy phù hợp và ném `IllegalStateException`.

### Tại sao người ta dùng `exposeProxy=true`?

Spring AOP không chặn self-invocation thông thường:

```java
public void outer() {
    this.inner(); // Gọi trực tiếp target, không qua proxy.
}
```

Nếu buộc phải đưa lời gọi `inner()` **quay lại qua proxy**, có thể làm:

```java
public void outer() {
    ((MyService) AopContext.currentProxy()).inner();
}
```

Trong đó `MyService` là interface mà proxy JDK triển khai (hoặc loại tương thích với proxy CGLIB). Caller bên ngoài phải gọi `outer()` qua Spring AOP proxy trước; method `outer()` đang chạy phải có current proxy được expose. Đây là cách xử lý **có chủ đích** cho một tình huống hẹp.

Bật `exposeProxy=true` **không tự sửa** lệnh `this.inner()`. Chỉ lời gọi qua tham chiếu proxy như `((MyService) AopContext.currentProxy()).inner()` mới có cơ hội qua advice. Nó cũng không buộc advisor áp dụng cho `inner()` nếu pointcut không khớp.

### Chi phí và giới hạn

- `AopContext.currentProxy()` dựa trên `ThreadLocal`, chỉ có ý nghĩa trong phạm vi execution của lời gọi AOP đang diễn ra; Spring phục hồi trạng thái cũ khi thoát invocation.
- Spring cần thiết lập/khôi phục thông tin proxy ở mỗi lời gọi liên quan, tạo một ít overhead. Chỉ bật khi có nhu cầu thực sự.
- Nếu thực thi chuyển sang thread khác, ví dụ gọi bất đồng bộ hoặc thread pool, không giả định proxy hiện hành tự được truyền theo.
- Business code phụ thuộc trực tiếp Spring AOP, khó unit test thuần và làm cách gọi không qua Spring dễ lỗi.
- Lấy proxy rồi ép kiểu sai có thể gây `ClassCastException`, đặc biệt với JDK proxy không triển khai concrete class.

**Hướng thiết kế ưu tiên:** tách phương thức cần advice sang một bean khác và constructor-inject bean đó; consumer gọi qua dependency do Spring cấp. Cách này giữ business logic ít phụ thuộc hạ tầng AOP hơn. Chỉ dùng `exposeProxy` khi đã hiểu các ràng buộc và cần kiểm soát self-invocation một cách có chủ đích.

## 4. Cấu hình bằng annotation, XML và Spring Boot

### Spring Framework thuần

```java
@Configuration
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
class AppConfig {
    // @Bean registrations hoặc @ComponentScan
}
```

Đây là ví dụ **cấu hình riêng lẻ**. `@EnableAspectJAutoProxy` chỉ tác động trong application context mà annotation được đăng ký. Với các application context phân cấp, cần kiểm tra từng context thực tế thay vì giả định một annotation ở context cha sẽ bật AOP trên mọi context con.

Aspect muốn Spring phát hiện cần đăng ký thành bean qua `@Component` + `@Aspect` hoặc qua `@Bean` trả về một đối tượng `@Aspect`. Với `@EnableAspectJAutoProxy` cần thư viện `aspectjweaver` để dùng cú pháp @AspectJ; không cần áp dụng bytecode weaving để chạy Spring proxy AOP.

Trong XML tương đương:

```xml
<aop:aspectj-autoproxy
    proxy-target-class="true"
    expose-proxy="true"/>
```

Cần namespace AOP và bean definitions tương ứng; fragment XML trên chưa phải một file cấu hình XML hoàn chỉnh.

### Spring Boot

Spring Boot có AOP auto-configuration khi dependency cần thiết hiện diện. Khi dùng `spring-boot-starter-aop`, cấu hình ứng dụng thông thường **không cần tự thêm** `@EnableAspectJAutoProxy`.

Trong `application.properties`:

```properties
# Spring Boot mặc định ưu tiên CGLIB.
spring.aop.proxy-target-class=true

# Đổi sang JDK dynamic proxy nếu target có interface phù hợp:
# spring.aop.proxy-target-class=false
```

Trong Spring Boot, `spring.aop.proxy-target-class` có giá trị mặc định `true`. Spring Framework thuần với `@EnableAspectJAutoProxy` không đặt đối số lại có mặc định `proxyTargetClass=false`. Đây là nguyên nhân thường gặp của sự khác biệt giữa hai ứng dụng khi inject theo concrete class.

Spring Boot cũng có thuộc tính `spring.aop.auto=true` để cho phép auto-configure AOP; `false` tắt **auto-configuration** đó, nhưng không ngăn một cơ chế kích hoạt AOP khác được khai báo tường minh. Đừng nhầm nó với `proxy-target-class`.

Muốn sử dụng `exposeProxy=true` trong cấu hình sử dụng annotation, khai báo rõ:

```java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
class ExplicitAopConfig {
}
```

Khi kết hợp với Spring Boot, hãy nhớ Spring có thể **gộp cấu hình của các auto-proxy creator**, nên loại proxy thực tế còn chịu ảnh hưởng của các cấu hình khác trong cùng context. Nếu Boot đang ép `proxyTargetClass=true`, chỉ thêm `@EnableAspectJAutoProxy(proxyTargetClass=false)` không bảo đảm được JDK proxy; hãy kiểm tra giá trị `spring.aop.proxy-target-class` và các khai báo auto-proxy còn lại.

### Các cấu hình có thể tác động lẫn nhau

Spring hợp nhất một số cơ chế tạo AOP proxy. Chẳng hạn `@EnableAspectJAutoProxy(proxyTargetClass=true)` và `@EnableTransactionManagement(proxyTargetClass=true)` có thể làm toàn bộ các bean được những hạ tầng proxy liên quan tạo bằng class-based proxy theo cùng cấu hình mạnh nhất. Vì vậy, đừng kết luận proxy chỉ từ annotation đặt ngay cạnh bean. Xác minh bằng `AopUtils` sau khi khởi tạo context.

## 5. Dự án Java 17+ chạy được: quan sát cả hai thuộc tính

Ví dụ dưới đây dùng **Spring Framework 6.2.x**, Maven và Java 17. Có một `TaskService` được auto-proxy vì `TraceAspect` áp dụng advice cho `work()`. Phương thức `run()` gọi `work()` lần đầu qua `this` và lần thứ hai qua `AopContext.currentProxy()`. Ban đầu dùng **JDK proxy** với `proxyTargetClass=false` và bật `exposeProxy=true`.

Cấu trúc file:

```text
spring-aop-flags/
├── pom.xml
└── src/main/java/demo/aop/
    ├── App.java
    ├── AppConfig.java
    ├── TaskService.java
    ├── TaskServiceImpl.java
    └── TraceAspect.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-flags</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.18</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/aop/TaskService.java`**

```java
package demo.aop;

public interface TaskService {
    void run();
    void work();
}
```

**`src/main/java/demo/aop/TaskServiceImpl.java`**

```java
package demo.aop;

import org.springframework.aop.framework.AopContext;

public class TaskServiceImpl implements TaskService {
    @Override
    public void run() {
        System.out.println("run()");
        this.work(); // Bỏ qua proxy: sẽ không chạy advice.

        // Đây là lối gọi qua proxy với exposeProxy=true:
        ((TaskService) AopContext.currentProxy()).work();
    }

    @Override
    public void work() {
        System.out.println("work()");
    }
}
```

**`src/main/java/demo/aop/TraceAspect.java`**

```java
package demo.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(* demo.aop.TaskServiceImpl.work(..))")
    public void beforeWork() {
        System.out.println("[advice] before work()");
    }
}
```

**`src/main/java/demo/aop/AppConfig.java`**

```java
package demo.aop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false, exposeProxy = true)
public class AppConfig {
    @Bean
    TaskService taskService() {
        return new TaskServiceImpl();
    }

    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

Aspect được đăng ký rõ bằng `@Bean`, vì vậy không cần `@ComponentScan`. Cấu hình `@EnableAspectJAutoProxy` phát hiện `@Aspect` trên `TraceAspect` và tạo AOP proxy cho `TaskService`.

**`src/main/java/demo/aop/App.java`**

```java
package demo.aop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));
            System.out.println("isJdkDynamicProxy=" + AopUtils.isJdkDynamicProxy(service));
            System.out.println("isCglibProxy=" + AopUtils.isCglibProxy(service));

            service.run();
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.aop.App
```

**Những dòng stdout do ví dụ in ra** (bỏ qua thông tin/log của công cụ build nếu có):

```text
isAopProxy=true
isJdkDynamicProxy=true
isCglibProxy=false
run()
work()
[advice] before work()
work()
```

Giải thích:

1. `TaskServiceImpl` có interface, và `proxyTargetClass=false` nên Spring chọn JDK dynamic proxy cho bean cần advice.
2. `service.run()` là lời gọi từ bên ngoài đi qua proxy. Vì `exposeProxy=true`, proxy hiện tại sẵn có trong `run()`.
3. `this.work()` là lời gọi trực tiếp trên target. Dòng `work()` đầu tiên không có `[advice]` đứng trước.
4. `((TaskService) AopContext.currentProxy()).work()` gửi lời gọi trở lại qua proxy; pointcut `work(..)` khớp nên advice chạy trước lần `work()` thứ hai.

### Thí nghiệm A: thay `proxyTargetClass=true`

Trong `AppConfig.java` đổi:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)
```

Biên dịch/chạy lại cùng lệnh. Với target có thể subclass như ví dụ, ba dòng kiểm tra đầu trở thành:

```text
isAopProxy=true
isJdkDynamicProxy=false
isCglibProxy=true
```

Các dòng `run()`, `work()` và advice theo cùng quy tắc. Đổi loại proxy **không** làm `this.work()` đi qua advice. Với proxy CGLIB, caller có thể dùng concrete class nếu cần; với JDK proxy, tốt nhất lấy bean qua `TaskService`.

### Thí nghiệm B: thay `exposeProxy=false`

Giữ `proxyTargetClass=false` nhưng đổi:

```java
@EnableAspectJAutoProxy(proxyTargetClass = false, exposeProxy = false)
```

Ở đoạn `service.run()`, dòng `this.work()` đầu tiên vẫn chạy; khi tới `AopContext.currentProxy()`, ứng dụng **ném `IllegalStateException`** do Spring không expose current proxy. Tắt expose không có nghĩa advice đã biến mất: nếu `App.main()` gọi trực tiếp `service.work()` qua proxy, advice vẫn hoạt động bình thường. Để chạy thành công khi expose=false, hãy bỏ đoạn gọi `AopContext.currentProxy()` hoặc thiết kế lại lời gọi giữa các bean.

### Thí nghiệm C: so sánh kiểu inject

Nếu đặt `proxyTargetClass=false`, việc lấy bean bằng:

```java
TaskService service = context.getBean(TaskService.class);
```

là lựa chọn đúng, còn lấy qua `TaskServiceImpl.class` có thể thất bại do JDK proxy không phải instance của implementation. Khi `proxyTargetClass=true` và class không final, context có thể cấp proxy tương thích với `TaskServiceImpl`. Hãy khai báo dependency theo interface khi thiết kế cho hợp đồng nghiệp vụ; dùng CGLIB khi có lý do rõ ràng cho proxy theo class.

## 6. Tình huống thực tế và lỗi thường gặp

| Triệu chứng | Cách lý giải và xử lý |
| --- | --- |
| `AopUtils.isAopProxy(bean)` là `false` | Kiểm tra bean có thực sự được advisor chọn, aspect đã được đăng ký, và auto-proxy đã bật. Hai cờ không tự tạo proxy nếu không có advice áp dụng. |
| `@EnableAspectJAutoProxy(proxyTargetClass=false)` nhưng runtime vẫn CGLIB | Spring Boot có thể mặc định đặt `spring.aop.proxy-target-class=true`, hoặc có một cấu hình auto-proxy khác dùng class proxy. Kiểm tra cấu hình hợp nhất. |
| Lỗi kiểu khi inject implementation | Có thể đang dùng JDK dynamic proxy. Inject theo interface hoặc xem lại lý do bắt buộc dùng class proxy. |
| Lỗi tạo proxy cho `final class` | CGLIB phải tạo subclass. Thay thiết kế class/method hoặc dùng interface proxy nếu phù hợp. |
| Advice không chạy khi target dùng `this.method()` | Self-invocation bỏ qua proxy dù `proxyTargetClass=true`; chuyển lời gọi qua bean khác hoặc dùng exposed proxy có cân nhắc. |
| `AopContext.currentProxy()` báo `IllegalStateException` | Expose chưa bật hoặc đang ở ngoài invocation qua proxy; đừng gọi tại constructor, `@PostConstruct`, từ `new` hoặc từ thread khác. |
| Ép `(TaskServiceImpl) AopContext.currentProxy()` bị `ClassCastException` | Proxy thực tế là JDK proxy của interface; ép về interface được proxy triển khai hoặc thay cấu hình có cơ sở. |
| Bật `exposeProxy=true` nhưng `this.method()` vẫn không có advice | Expose chỉ mở quyền **lấy** proxy; tự gọi trực tiếp vẫn bypass. Phải gọi thực sự trên reference proxy. |
| Bật `proxyTargetClass=true` để mong intercept private/final method | CGLIB không override được private/final method. Đưa điểm advice đến method có thể được proxy hoặc thay ranh giới service. |
| Trong request async, `currentProxy()` bỗng không có | Context hiện hành lưu theo thread; không tự truyền qua thread khác. Đưa thao tác AOP sang một Spring bean và gọi qua dependency thích hợp. |

### Khi nào dùng cấu hình nào?

- **Spring Framework thuần, DI theo interface và không cần truy cập proxy hiện hành:** thường bắt đầu bằng `@EnableAspectJAutoProxy` với mặc định của nó. Giữ `exposeProxy=false`.
- **Cần class-based proxy vì hợp đồng ứng dụng thực sự dựa vào class và class có thể được proxy:** cân nhắc `proxyTargetClass=true`, kiểm tra method visibility, `final`, scope và cấu hình thống nhất.
- **Cần gọi nội bộ đi qua advice:** ưu tiên đổi cấu trúc thành hai Spring bean. Nếu bất khả thi, bật `exposeProxy=true` và gọi qua `AopContext.currentProxy()` trong invocation hợp lệ, đồng thời chấp nhận phụ thuộc vào Spring AOP.
- **Dự án Spring Boot:** đọc `spring.aop.proxy-target-class` trước khi kết luận về JDK/CGLIB; Boot mặc định chọn class-based proxy. Tránh vô tình có nhiều cấu hình proxy mâu thuẫn.
- **Debug hoặc viết test tích hợp:** kiểm tra đối tượng Spring thực sự cấp bằng `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy` và kiểm tra advice với lời gọi qua DI.

## 7. Câu hỏi ôn tập

**1. `proxyTargetClass=true` có buộc tất cả Spring beans thành CGLIB proxy?** Không. Nó ép **kiểu proxy** cho các bean thực sự được AOP proxy; bean không có advisor phù hợp vẫn có thể giữ nguyên.

**2. Vì sao cùng code nhưng Spring Framework thuần là JDK proxy còn Spring Boot là CGLIB?** Vì `@EnableAspectJAutoProxy` mặc định `proxyTargetClass=false`, trong khi Spring Boot auto-configuration mặc định `spring.aop.proxy-target-class=true`.

**3. `exposeProxy=true` có chữa self-invocation không?** Không tự động. Nó cho phép lấy proxy đang thực hiện invocation; caller phải gọi method thông qua proxy ấy.

**4. Khi nào `AopContext.currentProxy()` có thể ném `IllegalStateException`?** Khi không có current proxy được expose trong thread và invocation hiện hành, chẳng hạn expose=false hoặc gọi ngoài proxy.

**5. Làm thế nào xác định loại proxy thực tế?** Dùng `AopUtils.isJdkDynamicProxy(bean)` / `AopUtils.isCglibProxy(bean)` trên bean lấy trực tiếp từ context hoặc DI, rồi đối chiếu cấu hình hợp nhất.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — `@EnableAspectJAutoProxy` API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html)
- [Spring Framework — `AopContext` API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/aop/framework/AopContext.html)
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
- [Spring Boot — Application Properties (spring.aop)](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
