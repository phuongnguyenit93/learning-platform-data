# Ép proxy lớp bằng proxyTargetClass và tác động toàn cấu hình Spring AOP

## 1. `proxyTargetClass` giải quyết vấn đề gì?

Spring AOP can thiệp vào lời gọi method của **Spring bean qua proxy**. Đối với bean cần áp dụng advisor, Spring thường cân nhắc hai dạng proxy:

- **JDK dynamic proxy**: khi target triển khai interface phù hợp, proxy thực thi các interface; người gọi làm việc qua kiểu interface. Một proxy kiểu này không phải instance của implementation class.
- **CGLIB class-based proxy**: Spring sinh một lớp con của target class. Proxy có thể gán cho kiểu class đích và có thể intercept những method đủ điều kiện của class, kể cả method `public` không được khai báo trên interface.

Giá trị `proxyTargetClass = true` **yêu cầu Spring dùng proxy theo lớp đích** thay vì ưu tiên proxy interface. Trong Java config hỗ trợ Spring AOP kiểu `@AspectJ`:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class AopConfiguration {
}
~~~

Đây là **đoạn cấu hình minh họa**, dùng trong một cấu hình Spring thực tế có các import `org.springframework.context.annotation.*`. Nó bật auto-proxying bằng class proxy cho các bean đủ điều kiện trong context. `proxyTargetClass = false` cho phép Spring lựa chọn proxy interface khi thích hợp; **không ép JDK proxy** cho một class không có interface.

Điều quan trọng: `proxyTargetClass` là **thiết lập cơ chế tạo proxy của Spring**. Nó không biến mọi bean thành proxy, không tạo thêm advisor, không thay thế pointcut, không tự đăng ký `@Aspect` thành bean và không kích hoạt AspectJ weaving.

## 2. Mặc định so với ép dùng CGLIB

Giả sử `CheckoutService implements CheckoutPort` và có method `checkout(...)` được Spring AOP advice:

| Trường hợp | Loại proxy dự kiến | Hệ quả đối với caller |
| --- | --- | --- |
| Spring Framework thuần; `@EnableAspectJAutoProxy` không ép class proxy; bean có interface | Thường là JDK dynamic proxy | Dùng `CheckoutPort`, không cast proxy thành `CheckoutService` |
| Bean cần AOP nhưng không có business interface | CGLIB class proxy, kể cả khi không bật `proxyTargetClass` | Proxy có thể gán cho implementation class nếu class có thể subclass |
| `@EnableAspectJAutoProxy(proxyTargetClass = true)` | CGLIB class proxy cho bean được auto-proxy creator chọn | Có thể inject/lấy theo implementation type nếu method/class cho phép |
| Một context chứa cả `proxyTargetClass = false` và `proxyTargetClass = true` trên các cấu hình AOP được hợp nhất | **Cấu hình mạnh hơn (`true`) thắng** | Không thể dùng một annotation `false` khác để buộc các bean trong cùng creator trở về JDK proxy |
| Bean không có bất cứ advisor/pointcut nào áp dụng | Thường giữ nguyên target, không có AOP proxy | `AopUtils.isAopProxy(bean)` là `false`, dù cấu hình ép class proxy đang bật |

Bảng trên nói về **Spring AOP trong Spring Framework**, không coi `proxyTargetClass = false` là mệnh lệnh “mọi nơi phải dùng JDK”. Kết quả cuối cùng còn tùy phạm vi context, auto-configuration và cách tạo từng proxy.

Trong **Spring Boot**, tự cấu hình AOP thường ưu tiên **CGLIB theo mặc định**. Thuộc tính:

~~~properties
spring.aop.proxy-target-class=false
~~~

cho phép chọn JDK proxy khi interface phù hợp trong cấu hình Boot được quản lý tương ứng. Khi ứng dụng có khai báo riêng yêu cầu `proxyTargetClass = true` hoặc hạ tầng proxy khác, hãy kiểm tra cấu hình thực tế; đừng đoán chỉ từ property. Không chuyển kết luận về mặc định của Spring Framework thuần sang Spring Boot mà không xét auto-configuration.

## 3. Vì sao một khai báo có thể tác động toàn cấu hình?

Đây là phần dễ bỏ sót nhất của bài học. Trong một **ApplicationContext**, các cấu hình Spring AOP và transaction dựa trên auto-proxy thường được **hợp nhất vào hạ tầng auto-proxy creator dùng chung**, với thiết lập proxy mạnh nhất được áp dụng. Theo tài liệu Spring Framework 6.2, cả các khai báo Java tương ứng như `@EnableAspectJAutoProxy` và `@EnableTransactionManagement` đều có thuộc tính `proxyTargetClass` và được xét theo cơ chế hợp nhất đó.

Ví dụ ý tưởng:

~~~java
@Configuration
@EnableAspectJAutoProxy
class LoggingAopConfig {
    // Aspect beans được đăng ký ở nơi phù hợp.
}

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ForceClassProxyConfig {
}
~~~

Nếu hai cấu hình trên **được đăng ký trong cùng một context**, Spring không coi chúng như hai vùng độc lập, mỗi vùng chỉ áp dụng flag cho “bean thuộc config của mình”. Cờ `true` khiến auto-proxy creator hợp nhất ưu tiên **class proxy cho các bean cần được auto-proxy** trong phạm vi đó. Cấu hình thứ hai không cần tự khai báo lại toàn bộ aspect mới có ảnh hưởng.

Tương tự, trong Spring Framework 6.2:

~~~java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfiguration {
}
~~~

Nếu dùng cùng context/hạ tầng hợp nhất với AOP, cấu hình transaction này có thể làm **loại proxy của các bean được Spring AOP advice** thay đổi, dù tác giả chỉ định ép class proxy vì mục tiêu transaction. Đoạn transaction trên chỉ minh họa cờ; một ứng dụng giao dịch chạy thật vẫn phải có transaction manager và hạ tầng tương ứng.

Với XML, nhóm cấu hình liên quan có cùng ý nghĩa:

~~~xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
<aop:config proxy-target-class="true"/>
<tx:annotation-driven proxy-target-class="true"/>
~~~

Các dòng XML là **những lựa chọn khai báo được trích riêng**; không phải file XML đầy đủ để chạy độc lập. Tài liệu Spring mô tả việc hợp nhất cấu hình mạnh nhất giữa `<aop:config/>`, `<aop:aspectj-autoproxy/>` và `<tx:annotation-driven/>`.

Cần hiểu chữ **“toàn cấu hình”** chính xác:

1. **Trong cùng context và cùng hạ tầng auto-proxy được hợp nhất**, lựa chọn class proxy có thể có tác dụng vượt ra ngoài vị trí khai báo ban đầu.
2. **Không có nghĩa mọi bean bị proxy**: chỉ bean có advisor phù hợp, đủ điều kiện và do container quản lý mới có khả năng được auto-proxy.
3. **Không có nghĩa toàn JVM**: `ApplicationContext` khác (đặc biệt parent/child context) có thể có đăng ký BPP/auto-proxy riêng. Đừng suy từ cấu hình của một context sang context khác.
4. **Không có nghĩa thay đổi proxy đã tạo tại runtime**: hiệu lực được áp dụng trong quá trình cấu hình và tạo bean/proxy. Việc đổi annotation sau khi bean đã khởi tạo không tự tạo lại proxy của singleton.

Trong Spring Framework **7.0 trở lên**, các tài liệu còn mô tả cơ chế mặc định hợp nhất rộng hơn và khả năng override theo bean với `@Proxyable`. Bài này chọn mô hình Spring Framework **6.2.x** để làm rõ thuộc tính `proxyTargetClass` và tác động hạ tầng AOP/transaction; không giả định các tính năng mới có trong 6.2.

## 4. Luồng xử lý khi Spring quyết định kiểu proxy

Với `@EnableAspectJAutoProxy`, Spring đăng ký auto-proxy creator, tiêu biểu `AnnotationAwareAspectJAutoProxyCreator`. Đây là một `BeanPostProcessor`/hạ tầng kế thừa từ `AbstractAutoProxyCreator`. Nó phát hiện advisor từ Spring bean `@Aspect`, tìm bean phù hợp và trả AOP proxy thay bean gốc khi cần.

~~~text
@Configuration / @EnableAspectJAutoProxy
          |
          v
Đăng ký / hợp nhất auto-proxy creator
          |
          +--> tổng hợp proxyTargetClass từ cấu hình liên quan
          |
          v
Tạo từng Spring bean đủ điều kiện
          |
          v
Tìm advisors/pointcut khớp method của bean
          |
          +--> không khớp ------> trả target thường
          |
          +--> khớp
                  |
                  v
          Kiểm tra proxyTargetClass, interface, proxy settings
                  |
                  +--> JDK dynamic proxy (khi phù hợp và không ép class)
                  |
                  +--> CGLIB subclass proxy (khi ép class hoặc cần proxy class)
                               |
                               v
                      Caller -> proxy -> advice -> target
~~~

**Đổi loại proxy không đổi mục tiêu của advice**: biểu thức pointcut vẫn dùng để xác định method được advice; proxy chỉ là cách chuyển hướng lời gọi. Có thể có advisor từ logging, transaction, cache hoặc security cùng tham gia một chain; loại proxy ảnh hưởng các method/kiểu đối tượng có thể được expose, chứ không trực tiếp làm từng advisor đúng hay sai.

Hai biểu thức nên phân biệt:

- `proxyTargetClass = true` — chọn class-based proxy.
- `exposeProxy = true` — một tùy chọn khác của `@EnableAspectJAutoProxy`, cho phép truy xuất proxy hiện hành qua `AopContext.currentProxy()` trong những điều kiện thích hợp. Không nên bật để giải quyết việc chọn JDK/CGLIB proxy; nó phục vụ vấn đề khác và gắn chặt mã vào Spring.

Ngoài ra, `@Configuration(proxyBeanMethods = false)` quyết định xử lý các factory method `@Bean` của configuration class. Cờ này **không tương đương** `@EnableAspectJAutoProxy(proxyTargetClass = false)`.

## 5. Project Java 17+ kiểm chứng tác động trên nhiều bean

Ta dùng hai service **đều triển khai interface**, cùng có advice `@Before`. Chạy hai `ApplicationContext` độc lập trong **cùng một chương trình**:

- Context `BASE` chỉ nạp cấu hình AOP thông thường: JDK proxy được dùng cho hai bean.
- Context `FORCED` nạp **cùng cấu hình đó cộng thêm** cấu hình `proxyTargetClass = true`: cả hai bean được CGLIB proxy.

Cách đối chứng này chứng minh tác động hạ tầng lên nhiều bean. Hai context độc lập để so sánh rõ, còn trong từng context cấu hình được hợp nhất theo các annotation đăng ký.

Cấu trúc:

~~~text
spring-proxy-target-class/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── CheckoutPort.java
    ├── CheckoutService.java
    ├── ReportPort.java
    ├── ReportService.java
    └── AuditAspect.java
~~~

Yêu cầu JDK 17 trở lên, Maven 3.9+ và có thể resolve Maven artifacts. Ví dụ cố định phiên bản **Spring Framework 6.2.0** và **AspectJ Weaver 1.9.22** cho khả năng tái lập, không khẳng định đây là bản mới nhất.

### 5.1. Maven build

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-proxy-target-class</artifactId>
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

`spring-context` cung cấp `ApplicationContext`/configuration, `spring-aop` chứa proxy utilities và AOP infrastructure, `aspectjweaver` hỗ trợ Spring phân tích cú pháp `@AspectJ`. Dependency AspectJ không tự bật compiler/weaver và không yêu cầu `-javaagent` cho ví dụ proxy AOP này.

### 5.2. Hai interface cùng hai implementation

`src/main/java/example/CheckoutPort.java`:

~~~java
package example;

public interface CheckoutPort {
    void checkout(String item);
}
~~~

`src/main/java/example/CheckoutService.java`:

~~~java
package example;

public class CheckoutService implements CheckoutPort {
    @Override
    public void checkout(String item) {
        System.out.println("CHECKOUT: " + item);
    }

    public void implementationOnly() {
        System.out.println("IMPLEMENTATION: checkout");
    }
}
~~~

`src/main/java/example/ReportPort.java`:

~~~java
package example;

public interface ReportPort {
    void generate();
}
~~~

`src/main/java/example/ReportService.java`:

~~~java
package example;

public class ReportService implements ReportPort {
    @Override
    public void generate() {
        System.out.println("REPORT: generated");
    }
}
~~~

Vì cả hai implementation đều có interface, Spring Framework auto-proxy trong cấu hình `BASE` có thể chọn JDK dynamic proxy. Method `CheckoutService.implementationOnly()` không có trên `CheckoutPort`: ví dụ có thể dùng nó để giải thích tính khác nhau giữa **kiểu interface được expose** và **lớp proxy theo target**. Trong mã chạy chính, ta chỉ gọi `checkout()` và `generate()` theo interface cho cả hai trường hợp để so sánh cùng một lời gọi.

### 5.3. Aspect dùng Spring AOP để chọn cả hai service

`src/main/java/example/AuditAspect.java`:

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.CheckoutService.checkout(..))"
          + " || execution(* example.ReportService.generate(..))")
    public void before(JoinPoint point) {
        System.out.println("ADVICE: " + point.getSignature().getName());
    }
}
~~~

Điều quan trọng là cả hai bean có **advisor áp dụng được**. Vì thế chúng là những bean cần proxy. `@Aspect` không tự tạo bean; cấu hình `App` bên dưới dùng `@Bean` để đăng ký `AuditAspect` vào container.

### 5.4. Hai cấu hình cùng context và mã kiểm chứng

`src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class App {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class BaseConfig {
        @Bean
        public CheckoutService checkoutService() {
            return new CheckoutService();
        }

        @Bean
        public ReportService reportService() {
            return new ReportService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class ForceClassProxyConfig {
    }

    private static void inspect(
            String label,
            AnnotationConfigApplicationContext context,
            boolean forced) {
        Object checkout = context.getBean("checkoutService");
        Object report = context.getBean("reportService");

        boolean checkoutJdk = AopUtils.isJdkDynamicProxy(checkout);
        boolean reportJdk = AopUtils.isJdkDynamicProxy(report);
        boolean checkoutCglib = AopUtils.isCglibProxy(checkout);
        boolean reportCglib = AopUtils.isCglibProxy(report);
        boolean assignableToClass = checkout instanceof CheckoutService;

        System.out.println(label + "_CHECKOUT_JDK: " + checkoutJdk);
        System.out.println(label + "_REPORT_JDK: " + reportJdk);
        System.out.println(label + "_CHECKOUT_CGLIB: " + checkoutCglib);
        System.out.println(label + "_REPORT_CGLIB: " + reportCglib);
        System.out.println(label + "_IS_CHECKOUT_CLASS: " + assignableToClass);

        boolean correct = forced
                ? checkoutCglib && reportCglib
                        && !checkoutJdk && !reportJdk && assignableToClass
                : checkoutJdk && reportJdk
                        && !checkoutCglib && !reportCglib && !assignableToClass;

        if (!correct) {
            throw new IllegalStateException(
                    "Unexpected proxy type in context " + label);
        }

        ((CheckoutPort) checkout).checkout("book");
        ((ReportPort) report).generate();
    }

    public static void main(String[] args) {
        try (var base =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            inspect("BASE", base, false);
        }

        try (var forced = new AnnotationConfigApplicationContext(
                BaseConfig.class, ForceClassProxyConfig.class)) {
            inspect("FORCED", forced, true);
        }

        System.out.println("CHECK: PASS");
    }
}
~~~

Phân tích hai lần khởi tạo context:

1. `new AnnotationConfigApplicationContext(BaseConfig.class)` chỉ thấy `@EnableAspectJAutoProxy(proxyTargetClass = false)`. Vì cả hai service đều triển khai interface và có advice áp dụng, Spring Framework 6.2 chọn **JDK dynamic proxy** cho chúng.
2. `new AnnotationConfigApplicationContext(BaseConfig.class, ForceClassProxyConfig.class)` nạp hai cấu hình cùng một context. Dù `BaseConfig` ghi `false`, `ForceClassProxyConfig` ghi `true`; creator được hợp nhất và dùng **class-based proxy** cho **cả hai service**, không chỉ cho bean có mặt trong `ForceClassProxyConfig` (thực ra config này không khai báo service bean nào).
3. Cả JDK proxy lẫn CGLIB proxy đều implement `CheckoutPort` và `ReportPort` ở đây, nên lời gọi qua interface dùng chung mà không phải thay business code.
4. `instanceof CheckoutService` là `false` với JDK proxy, `true` với CGLIB proxy; điều này cho thấy ảnh hưởng đến các injection point dùng implementation class.
5. `AopUtils.isJdkDynamicProxy(...)` và `AopUtils.isCglibProxy(...)` kiểm tra cơ chế thực tế, có giá trị hơn việc suy đoán từ annotation.
6. Chương trình ném `IllegalStateException` nếu loại proxy không đúng, chỉ in `CHECK: PASS` khi hai context thỏa các kỳ vọng. Điểm khác biệt của bài học nằm ở **proxy class selection**; advice đều chạy ở cả hai context.

### 5.5. Lệnh chạy và stdout

Chạy tại thư mục project:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chính `App`, `AuditAspect` và các service in ra, theo đúng thứ tự:

~~~text
BASE_CHECKOUT_JDK: true
BASE_REPORT_JDK: true
BASE_CHECKOUT_CGLIB: false
BASE_REPORT_CGLIB: false
BASE_IS_CHECKOUT_CLASS: false
ADVICE: checkout
CHECKOUT: book
ADVICE: generate
REPORT: generated
FORCED_CHECKOUT_JDK: false
FORCED_REPORT_JDK: false
FORCED_CHECKOUT_CGLIB: true
FORCED_REPORT_CGLIB: true
FORCED_IS_CHECKOUT_CLASS: true
ADVICE: checkout
CHECKOUT: book
ADVICE: generate
REPORT: generated
CHECK: PASS
~~~

Maven hoặc logging của framework có thể tạo thêm dòng bên ngoài; bản trên liệt kê **chỉ stdout do mã ví dụ chủ động in ra**.

Từ kết quả, có thể kết luận:

- Cùng hai service, cùng advice, cùng business calls nhưng **khác loại proxy** khi cấu hình trong context thay đổi.
- Chỉ thêm `ForceClassProxyConfig` làm **cả hai bean đủ điều kiện** chuyển sang CGLIB dù config ép không khai báo bean cụ thể.
- `CHECK: PASS` được in sau kiểm tra loại proxy, chứ không phải phép thử xem mọi bean Spring đều có proxy.
- Bài đã xác nhận cơ chế Spring AOP. **Không có AspectJ compile-time hay load-time weaving** trong project này.

## 6. Những hệ quả thực tế của việc ép proxy lớp

### 6.1. Kiểu injection và cast

Nếu service triển khai `CheckoutPort`:

~~~java
@Autowired
private CheckoutPort checkout;
~~~

Đây là kiểu injection hoạt động với JDK proxy và CGLIB proxy (khi bean duy nhất/được chọn đúng). Nếu viết:

~~~java
@Autowired
private CheckoutService checkout;
~~~

Khi bean thực tế là JDK dynamic proxy, đối tượng proxy **không phải** instance của `CheckoutService`; việc inject theo class có thể thất bại vì không phù hợp kiểu. CGLIB proxy là lớp con của `CheckoutService` nên trong điều kiện class proxy tạo được, kiểu này có thể được inject. Hai snippet trên là **minh họa field injection trong class Spring-managed**, không phải tệp Java độc lập; trong ứng dụng thật, constructor injection thường dễ kiểm soát dependency hơn.

**Đừng ép toàn bộ hạ tầng CGLIB chỉ để tránh thiết kế interface** nếu phần lớn dependency dùng interface một cách rõ ràng và ổn định. Khi có nhu cầu thực sự gọi method chỉ nằm trên implementation, hãy cân nhắc trước khi chọn class proxy cho toàn context.

### 6.2. Method không thuộc interface

JDK proxy không expose method `implementationOnly()` của `CheckoutService` vì `CheckoutPort` không khai báo nó. Với class proxy, method đó có thể truy cập qua `CheckoutService` (nếu không có giới hạn method/class).

Tuy nhiên, **truy cập được method không đồng nghĩa method sẽ được advice**. Pointcut trong ví dụ chỉ khớp `checkout(...)` và `generate(...)`. Muốn `implementationOnly()` cũng chạy advice thì phải mở rộng pointcut hoặc tạo advisor phù hợp; `proxyTargetClass = true` tự nó không thêm advice.

### 6.3. Giới hạn class proxy

| Đặc điểm target | Điều cần nhớ khi dùng CGLIB |
| --- | --- |
| `final class` | Không thể tạo subclass proxy cho chính class đó |
| `final method` | Không thể override/intercept method đó qua CGLIB proxy |
| `private method` | Không thể override; Spring AOP proxy không advice nó theo cách thông thường |
| Method không nhìn thấy từ lớp con | Có thể không intercept được; ví dụ một method package-private ở parent class thuộc package khác |
| Object được khởi tạo bằng `new` ngoài Spring | Không tự nhận proxy chỉ vì cấu hình `proxyTargetClass` |
| Self-invocation `this.otherMethod()` trong target | Vẫn bỏ qua lời gọi qua proxy, kể cả CGLIB |
| JVM module path / hạn chế module accessibility | Một số class không cho phép subclass proxy nếu package không mở phù hợp |
| Constructor của class proxy | Spring thường dùng Objenesis để tránh gọi constructor đích hai lần; tùy giới hạn JVM có thể có ngoại lệ/diagnostic |

Những giới hạn này bắt nguồn từ kỹ thuật **lớp con** và cách Spring AOP gọi target. Dùng CGLIB không mang lại khả năng chặn mọi field access/constructor như AspectJ weaving. Đừng chuyển flag sang `true` chỉ vì muốn khắc phục self-invocation: giải pháp ở cấp thiết kế là gọi qua bean proxy (thường tách service) hoặc chọn cơ chế phù hợp khác nếu yêu cầu vượt phạm vi Spring AOP.

### 6.4. Ảnh hưởng với transaction và các advisor khác

Một project Spring có thể dùng `@Transactional`, cache, security và `@Aspect` logging cùng lúc. Các cơ chế này có thể sử dụng Spring AOP proxy/advisor. Trong Spring Framework 6.2, cấu hình Spring AOP và transaction với cờ `proxyTargetClass` có thể hợp nhất về **global auto-proxy creator settings** trong cùng context.

Điều đó **không** có nghĩa mọi annotation tự động tham gia advice hay mọi cơ chế @Async có cùng quy tắc ở mọi phiên bản. Đừng mở rộng kết luận vượt hỗ trợ framework/version đang dùng; khi nâng Spring 7.x, đọc tài liệu về cách hợp nhất proxy processors có thay đổi.

Trước khi bật ép class proxy cho application có transaction, hãy kiểm tra tất cả target cần proxy: class/method `final`, kiểu injection và hành vi khi nhiều advisor cùng áp dụng. Một thay đổi cấu hình nhỏ có thể đổi kiểu runtime của nhiều bean.

## 7. Cấu hình theo các kiểu Spring phổ biến

### Java configuration thuần Spring

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
}
~~~

Có thể dùng một configuration Java được Spring load. Aspect cần là bean, chẳng hạn có cả `@Aspect` và `@Component` dưới component scanning, hoặc được tạo bằng `@Bean` như ví dụ chính.

### Spring Boot auto-configuration

~~~properties
spring.aop.proxy-target-class=true
~~~

Spring Boot thường đã cấu hình AOP nếu dependency cần thiết có trên classpath; trong nhiều phiên bản mặc định của Boot, CGLIB cũng đã bật. Property `false` là cách yêu cầu proxy interface trong thiết lập tương ứng của Boot, nhưng không nên coi nó có quyền ghi đè bất kỳ cấu hình AOP riêng biệt nào vốn ép `true`. Kiểm tra `AopUtils` và cấu hình thực tế.

### XML AOP

~~~xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
~~~

Đây là phần tử thuộc namespace AOP cần khai báo trong XML cấu hình Spring, không phải tệp XML độc lập. Nếu cùng context có `<tx:annotation-driven/>`, hãy nhớ quy tắc kết hợp mạnh nhất thay vì giả định namespace nào chỉ ảnh hưởng namespace đó.

### Kiểm tra trực tiếp tại runtime

Trong method Java có biến `context` thuộc Spring `ApplicationContext`:

~~~java
Object bean = context.getBean("checkoutService");

System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

Đoạn trên **cắm vào ứng dụng đã tồn tại**, không phải chương trình biên dịch riêng. Nếu đối tượng thực sự có AOP proxy, hàm đầu tiên phải `true`; hai hàm sau giúp phân biệt loại. Không suy luận loại proxy từ việc class có interface hay không khi cấu hình application đã phức tạp.

## 8. Các nhầm lẫn phổ biến

**“`proxyTargetClass = true` chỉ ảnh hưởng bean khai báo trong configuration chứa annotation.”** Sai với cơ chế auto-proxy dùng chung trong cùng context: các bean khác đủ điều kiện advisor vẫn có thể chịu cấu hình mạnh nhất, như `ReportService` trong ví dụ.

**“`proxyTargetClass = false` sẽ ép mọi service thành JDK proxy.”** Sai. Nếu class không có interface để proxy, Spring vẫn có thể dùng CGLIB. Nếu trong context có cấu hình liên quan ép `true`, cờ `false` ở nơi khác không xóa được thiết lập mạnh hơn.

**“Bật `proxyTargetClass` là tất cả bean sẽ có proxy.”** Sai. Spring AOP vẫn cần advisor/pointcut khớp và bean đủ điều kiện xử lý. Cấu hình `true` chỉ chọn kiểu **khi phải tạo proxy**.

**“CGLIB xử lý được `final`, `private`, constructor hoặc `this.save()`.”** Sai. CGLIB là subclass proxy nên không override được method `final`/`private`; lời gọi nội bộ trên `this` không đi qua proxy của Spring AOP.

**“CGLIB là AspectJ weaving.”** Sai. CGLIB là kỹ thuật sinh subclass proxy ở runtime; AspectJ weaving là cơ chế biến đổi bytecode theo compiler/weaver riêng. Cùng syntax `@AspectJ` không đồng nhất hai cơ chế.

**“Thay property của Boot sang `false` chắc chắn đã tắt mọi class proxy.”** Sai khi ứng dụng còn cấu hình Spring AOP/transaction yêu cầu class proxy hoặc khi bean không có interface. Hãy xác nhận lại bằng quan sát proxy thực tế.

**“Đã dùng CGLIB thì không cần interface nữa.”** Không bắt buộc loại interface khỏi thiết kế. Interface vẫn hữu ích cho API, kiểm thử, định nghĩa contract. Lựa chọn JDK hay CGLIB là quyết định proxy kỹ thuật, nên dựa trên nhu cầu thực.

## 9. Quy trình chẩn đoán khi thay đổi `proxyTargetClass`

1. **Xác nhận đúng context và profile:** config nào thực sự được nạp, Spring Framework/Spring Boot version nào, có parent/child contexts không.
2. **Liệt kê nguồn thiết lập ép class proxy:** `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, XML AOP/transaction, Boot `spring.aop.proxy-target-class` và các hạ tầng proxy liên quan.
3. **Xác định bean cần proxy:** aspect/advisor nào áp dụng, pointcut có khớp method qua Spring bean không. Không có advisor thì việc đổi flag có thể không hiện ra.
4. **Đo loại proxy tại runtime:** `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy` trên reference nhận từ context.
5. **Kiểm tra tính tương thích của target:** `final`, `private`, visibility, interface và module accessibility trước khi ép CGLIB.
6. **Đối chiếu kiểu injection và code cast:** một bean từng là JDK proxy nay là subclass proxy có thể thay đổi giả định trong các điểm inject hoặc code reflection; tập trung vào contract cần expose.
7. **Kiểm tra hành vi advice thật:** gọi method qua proxy rồi quan sát log/counter hoặc integration test; proxy đúng loại nhưng pointcut không khớp vẫn không chạy advice.
8. **Sau khi đổi cấu hình, khởi tạo lại context để kiểm chứng:** không dựa vào proxy singleton đã được tạo từ cấu hình cũ.
9. **Đánh giá tác động đến bean khác:** nhất là khi application có AOP và transaction dùng chung hạ tầng; test thêm bean không nằm trong configuration đã chỉnh nhưng có advisor.

## 10. Câu hỏi tự kiểm tra

1. Khi `CheckoutService implements CheckoutPort`, vì sao `proxyTargetClass = false` thường cho JDK proxy nhưng `true` cho CGLIB?  
   Vì `false` cho phép cơ chế chọn interface proxy khi phù hợp, còn `true` yêu cầu subclass proxy theo target class.

2. Bật `proxyTargetClass = true` có khiến một bean không khớp advisor thành proxy không?  
   Không. Flag điều khiển **loại** proxy, không sinh ra yêu cầu advice mới.

3. Hai configuration cùng một `ApplicationContext`, một cấu hình ghi `false` và một ghi `true` thì kết quả nào?  
   Với auto-proxy creator hợp nhất, **thiết lập mạnh nhất (`true`)** được áp dụng cho các bean cần proxy trong context.

4. Vì sao mã inject implementation class có thể hỏng khi đổi từ CGLIB về JDK proxy?  
   JDK proxy chỉ thực thi interface nên không phải instance của implementation class.

5. Có thể chữa self-invocation bằng `proxyTargetClass = true` không?  
   Không. `this.method()` trên target vẫn không đi qua Spring proxy.

6. Một ứng dụng dùng Spring Boot mặc định class proxy nhưng project Maven Spring thuần dùng JDK proxy; có mâu thuẫn không?  
   Không. Spring Boot có auto-configuration và default riêng; cần xét thiết lập hiệu lực của từng application.

## Tài liệu chính thức

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): lựa chọn JDK/CGLIB, giới hạn class proxy và cơ chế cấu hình mạnh nhất.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring dùng syntax AspectJ trong AOP runtime dựa trên proxy.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): bật auto-proxy creator.
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html): lý do JDK proxy và class proxy có phạm vi method khác nhau.
- [Spring Boot — AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html): mặc định Boot và thuộc tính `spring.aop.proxy-target-class`.
