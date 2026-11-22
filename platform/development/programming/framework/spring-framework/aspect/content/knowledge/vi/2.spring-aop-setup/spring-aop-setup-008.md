# Ứng dụng Spring AOP tối thiểu để xác nhận một advice được thực thi

## 1. Mục tiêu thực hành

Xây dựng một chương trình Java 17+ chỉ dùng Spring Framework, không cần web server hay cơ sở dữ liệu, để xác nhận **Spring AOP đã gọi một `@Before` advice** trước phương thức của một Spring bean.

Đầu ra cần chứng minh đủ bốn việc:

1. `ApplicationContext` chứa service và aspect đã đăng ký.
2. Đối tượng service lấy từ Spring là AOP proxy, kiểm tra bằng `AopUtils.isAopProxy(...)`.
3. Khi gọi method qua proxy, dòng `ADVICE` xuất hiện **trước** dòng `SERVICE`.
4. Bộ đếm được tăng **ngay trong advice** có giá trị `1`; chương trình chỉ in `CHECK: PASS` sau khi kiểm tra cả proxy lẫn bộ đếm.

Các annotation `@Aspect` và `@Before` có cú pháp của AspectJ nhưng được **Spring AOP** phân tích và triển khai dưới dạng proxy. Bài này chỉ kiểm tra Spring Aspect; không kích hoạt AspectJ compiler hay load-time weaving. Thư viện AspectJ hiện diện trong classpath không đồng nghĩa lớp Java đã được weave.

## 2. Chuẩn bị Maven project

Cấu trúc đầy đủ:

~~~text
spring-aop-check/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── NotificationService.java
    └── TraceAspect.java
~~~

Yêu cầu JDK 17 trở lên và Maven 3.9+. Các phiên bản thư viện dưới đây được cố định để ví dụ có thể tái lập; không phải lời khẳng định về bản mới nhất.

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-check</artifactId>
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
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp container và các annotation cấu hình bean; `spring-aop` cung cấp hạ tầng proxy cùng `AopUtils`. `aspectjweaver` cung cấp thư viện để Spring xử lý kiểu khai báo `@AspectJ` và pointcut. **Không cần tham số `-javaagent`** để chạy Spring AOP trong ví dụ này.

## 3. Service có method để advice can thiệp

Tạo `src/main/java/example/NotificationService.java`:

~~~java
package example;

public class NotificationService {
    public void deliver(String recipient) {
        System.out.println("SERVICE: Delivered to " + recipient);
    }
}
~~~

Class và method này đều là `public`, không `final`. Điều này thuận lợi cho class-based proxy được bật ở phần cấu hình. Không gắn `@Component` bởi `App` sẽ đăng ký service bằng `@Bean`, giúp nhìn rõ đối tượng nào thuộc Spring container.

## 4. Aspect dùng `@Before` và bộ đếm

Tạo `src/main/java/example/TraceAspect.java`:

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger adviceInvocations = new AtomicInteger();

    @Before("execution(* example.NotificationService.deliver(..))")
    public void beforeDeliver() {
        adviceInvocations.incrementAndGet();
        System.out.println("ADVICE: before deliver");
    }

    public int getAdviceInvocations() {
        return adviceInvocations.get();
    }
}
~~~

Giải thích dưới góc độ **Spring AOP**:

- `@Aspect` thông báo lớp chứa pointcut/advice theo cách Spring hiểu; **không tự biến lớp thành Spring bean**.
- `execution(* example.NotificationService.deliver(..))` chọn method execution của `deliver` trong class cụ thể. Dấu `*` chấp nhận mọi kiểu trả về; `(..)` chấp nhận danh sách đối số.
- `@Before` làm Spring gọi `beforeDeliver()` khi lời gọi method khớp **đi qua proxy**. Dòng `ADVICE` chỉ được in tại đây, không nằm trong service.
- `adviceInvocations` chỉ được tăng trong method advice. Sau một lời gọi hợp lệ, giá trị `1` chứng tỏ Spring đã kích hoạt advice thật. `AtomicInteger` là cách đếm đơn giản, an toàn nếu sau này có nhiều thread, dù ví dụ hiện tại chạy tuần tự.
- Method `getAdviceInvocations()` cho phép mã chính lấy bằng chứng từ **chính bean aspect** đã đăng ký trong container.

## 5. Bật Spring AOP và gọi bean qua context

Tạo `src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public NotificationService notificationService() {
        return new NotificationService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            NotificationService service =
                    context.getBean(NotificationService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean proxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxy);

            service.deliver("Spring");

            int count = aspect.getAdviceInvocations();
            System.out.println("ADVICE_COUNT: " + count);

            if (!proxy || count != 1) {
                throw new IllegalStateException(
                        "Spring AOP advice was not executed exactly once");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

**Tại sao từng phần lại cần thiết?**

1. `@Configuration` khai báo lớp cấu hình Java; `proxyBeanMethods = false` chỉ điều khiển việc proxy hóa các phương thức `@Bean` của configuration class, **không vô hiệu hóa AOP trên service**.
2. `@EnableAspectJAutoProxy(proxyTargetClass = true)` đăng ký cơ chế Spring AOP, cho phép dùng class-based (CGLIB) proxy. Chọn class proxy để có thể lấy bean bằng `NotificationService.class` mà không cần thêm interface. Dùng `proxyTargetClass = true` **không** có nghĩa AspectJ weaving đã bật.
3. `@Bean notificationService()` và `@Bean traceAspect()` đăng ký cả đối tượng đích lẫn aspect. `@Aspect` riêng lẻ là chưa đủ.
4. `AnnotationConfigApplicationContext(App.class)` khởi tạo Spring container. `getBean(NotificationService.class)` trả bean mà Spring cung cấp, có thể là proxy nếu advisor khớp.
5. `AopUtils.isAopProxy(service)` cho biết Spring đã tạo proxy, nhưng chưa đủ một mình để khẳng định advice này đã chạy; vì vậy chương trình còn đo số lần advice.
6. `service.deliver("Spring")` là lời gọi **từ mã bên ngoài đối tượng đích vào Spring bean**. Lời gọi qua proxy được so khớp pointcut trước khi vào method service.
7. Kiểm tra `!proxy || count != 1` khiến chương trình thất bại nếu thiếu một bằng chứng. Chỉ khi đủ điều kiện mới in `CHECK: PASS`.

Tất cả ba lớp đều có `package example;` và nằm đúng đường dẫn tương ứng, nên có thể biên dịch chung bằng Maven.

### Chạy chương trình

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do mã ví dụ tạo ra, theo đúng thứ tự:

~~~text
PROXY: true
ADVICE: before deliver
SERVICE: Delivered to Spring
ADVICE_COUNT: 1
CHECK: PASS
~~~

Maven hoặc môi trường có thể phát thêm thông báo riêng; năm dòng trên là đầu ra của chương trình cần kiểm tra.

- `PROXY: true` chứng minh service bean đã được proxy.
- `ADVICE: before deliver` **đứng trước** `SERVICE: Delivered to Spring` chứng minh advice `@Before` thực thi trước target method.
- `ADVICE_COUNT: 1` chứng minh instance `TraceAspect` trong Spring ghi nhận đúng một lần advice chạy.
- `CHECK: PASS` cho biết chương trình đã tự kiểm tra cả `proxy` lẫn `count`. Nếu một trong hai sai, `IllegalStateException` xuất hiện thay cho dòng thành công.

Dòng chảy tại runtime:

~~~text
main()
  |
  +--> AnnotationConfigApplicationContext(App.class)
  |       +--> NotificationService bean được Spring proxy
  |       +--> TraceAspect bean có @Before advisor
  |
  +--> service.deliver("Spring")
           |
           v
       Spring proxy -- pointcut khớp execution(...deliver(..))
           |
           v
       TraceAspect.beforeDeliver()    -> count tăng, in ADVICE
           |
           v
       NotificationService.deliver()   -> in SERVICE
           |
           v
       main() -> đọc count, kiểm tra, in CHECK: PASS
~~~

Trong luồng trên, Spring AOP intercept method execution trên bean bằng **proxy**; không biên dịch lại hoặc weave bytecode của `NotificationService`.

## 6. Phép đối chứng để xác nhận nguyên nhân

Thay đổi **một điều tại một thời điểm** và khôi phục trước phép thử tiếp theo:

| Thay đổi | Kết quả dự kiến | Kết luận |
| --- | --- | --- |
| Giữ nguyên mã mẫu | `PROXY: true`, `ADVICE_COUNT: 1`, `CHECK: PASS` | Đã tạo proxy, advice chạy đúng một lần |
| Bỏ `@EnableAspectJAutoProxy` trong ứng dụng Maven này | Không có proxy AOP do ví dụ tự tạo; count = 0, chương trình ném exception | Có bean và `@Aspect` vẫn cần hạ tầng auto-proxy |
| Bỏ `@Bean traceAspect()` | `context.getBean(TraceAspect.class)` thất bại | `@Aspect` không đồng nghĩa bean tự động xuất hiện trong context |
| Đổi pointcut thành `execution(* example.NotificationService.notThere(..))` | Advice không khớp `deliver`; count = 0, không đạt CHECK | Pointcut phải khớp method thực được gọi |
| Tự gọi `new NotificationService().deliver("Direct")` ngoài context | In SERVICE nhưng không in ADVICE, không tăng count Spring aspect | Đối tượng được tạo ngoài container không đi qua proxy |

Các dự đoán về việc bỏ auto-proxy áp dụng cho **project tối thiểu chỉ có cấu hình này**. Ứng dụng Spring Boot có starter AOP hoặc cấu hình khác có thể đã tự bật auto-proxy, nên cần xác minh bối cảnh trước khi kết luận.

Nếu muốn kiểm chứng bằng debugger, đặt breakpoint ở `TraceAspect.beforeDeliver()` và chạy qua `service.deliver("Spring")`. Breakpoint dừng trong advice là bằng chứng trực tiếp, nhưng dấu hiệu stdout kết hợp bộ đếm đã đủ cho mục tiêu bài này.

## 7. Tích hợp quy trình vào project Spring thực tế

Khi chuyển từ ví dụ sang project Spring có sẵn:

1. Chọn method `public` của một service **do Spring quản lý**, được caller khác gọi qua container. Giới hạn biểu thức pointcut vào package/service muốn kiểm tra để tránh log ngoài ý muốn.
2. Đảm bảo có cơ chế bật AOP: `@EnableAspectJAutoProxy` cho Spring Framework dùng cấu hình Java, hoặc Spring Boot AOP auto-configuration trong ứng dụng Boot.
3. Đăng ký aspect như Spring bean (`@Bean` hoặc `@Component` được scan), rồi đặt `@Before` với biểu thức `execution(...)` khớp đúng method.
4. Thêm một dấu hiệu có thể kiểm chứng bên trong advice: log marker duy nhất hoặc bộ đếm dùng trong môi trường thử nghiệm.
5. Gọi từ một bean/caller thực tế, xác nhận proxy, advice và hành vi của method. Trong integration test có thể dùng assertion tương đương `count == 1` thay cho dựa vào đọc log thủ công.

Trong Spring Boot, dependency `spring-boot-starter-aop` thường cung cấp thư viện và auto-configuration cần thiết; bạn vẫn phải đăng ký aspect. Ví dụ dùng Spring Framework thuần ở đây để người học thấy rõ điểm bật AOP, không phụ thuộc cấu hình tự động của Boot.

Đối với ứng dụng có nhiều advisor như transaction, security hoặc caching, hãy phân biệt hai câu hỏi: “bean có được proxy không?” và “**advice cụ thể của mình** có khớp lời gọi này không?”. `AopUtils.isAopProxy` trả lời câu đầu, bộ đếm/log trong `beforeDeliver()` trả lời câu sau.

## 8. Các lỗi phổ biến và cách xử lý

**Không thấy dòng ADVICE:**

- Kiểm tra `TraceAspect` đã đăng ký vào cùng `ApplicationContext` với service chưa. Chỉ có `@Aspect` mà không có `@Bean` hay component scanning là chưa đủ.
- Xem `@EnableAspectJAutoProxy` có nằm trong configuration thực sự được nạp không; với Boot kiểm tra starter và auto-configuration hiện tại.
- Soát biểu thức `execution(...)`: đúng package `example`, class `NotificationService` và method `deliver`. Spring AOP chủ yếu áp dụng advice cho method execution qua proxy.
- Xác nhận bạn gọi `service` lấy bằng `context.getBean(...)`; đối tượng tạo bởi `new` không tự được Spring proxy.
- Nếu method của service gọi `this.otherMethod()` trên chính target, đó là self-invocation và có thể bỏ qua advice trên method nội bộ. Ví dụ này cố ý gọi từ `main` để tránh nhầm lẫn.
- Với class proxy, `final` method, `private` method hoặc class `final` không thể được can thiệp theo cách subclass proxy; phương thức mẫu là `public` và không `final`.

**Có `PROXY: true` nhưng counter không tăng:**

Proxy tồn tại không đảm bảo `@Before` này được kích hoạt. Pointcut có thể không khớp; method bạn gọi có thể khác method mong muốn; bean có thể được proxy vì advisor khác. Kiểm tra đúng aspect bean đang đọc số đếm và đúng luồng lời gọi đi qua proxy.

**Lỗi khi biên dịch hoặc khởi động:**

- `ClassNotFoundException` / `NoClassDefFoundError` liên quan AspectJ: xem Maven đã tải dependency `aspectjweaver`, phiên bản và classpath. Bài này không cần bật `-javaagent` để chữa lỗi.
- `NoSuchBeanDefinitionException`: kiểm tra `@Bean`/`@Configuration` và class cấu hình được nạp vào context.
- `Cannot subclass final class` hoặc lỗi proxy method: kiểm tra các giới hạn CGLIB nói trên. Tránh suy ra rằng chuyển sang weaving là bước bắt buộc cho ví dụ tối thiểu.
- Nếu thay bằng JDK dynamic proxy trên interface, bean thường được lấy qua interface; không mặc định cast proxy về implementation. Project gốc dùng `proxyTargetClass = true` để giảm biến số này.

**Counter lớn hơn 1:** xác minh `deliver` chỉ được gọi một lần, không vô tình chạy nhiều luồng/test. Nếu có nhiều aspect, cần tách marker của từng advice; nhiều dòng log không mặc nhiên có nghĩa một advice chạy nhiều lần. Trong mã mẫu, bộ đếm được tăng tại duy nhất một method advice.

## 9. Checklist hoàn thành

- [ ] Maven biên dịch ba tệp Java trong đúng package `example`.
- [ ] `App` có `@Configuration`, `@EnableAspectJAutoProxy` và hai phương thức `@Bean`.
- [ ] `TraceAspect` có `@Aspect` và `@Before` pointcut khớp `deliver`.
- [ ] Service được lấy qua `ApplicationContext`; không gọi đối tượng tự tạo `new`.
- [ ] Đầu ra có `PROXY: true`.
- [ ] `ADVICE` xuất hiện trước `SERVICE`.
- [ ] `ADVICE_COUNT: 1` và `CHECK: PASS` được in.
- [ ] Hiểu rằng kết quả chứng minh **Spring AOP proxy đã chạy advice**, không chứng minh AspectJ weaving.

## Tài liệu đối chiếu chính thức

- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html).
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html).
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html).
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).
