# AopContext.currentProxy(), exposeProxy và lý do hạn chế sử dụng trong Spring AOP

## 1. Mục tiêu của bài

Trong Spring AOP, advice chỉ được áp dụng cho **lời gọi đi qua AOP proxy**. Một service có thể được container trả về dưới dạng proxy, nhưng bên trong chính target, lời gọi **this.method()** lại không quay trở lại proxy. Đây là lý do một phương thức có annotation, hoặc khớp pointcut, vẫn có thể không được advice khi được gọi nội bộ.

Spring cung cấp hai cơ chế liên quan trực tiếp đến tình huống này:

- **AopContext.currentProxy()**: lấy **proxy của lời gọi Spring AOP đang diễn ra** trên thread hiện tại.
- **exposeProxy = true**: cấu hình cho Spring đặt proxy đang hoạt động vào ngữ cảnh thread để currentProxy() có thể lấy ra.

Cơ chế này có thể chuyển một lời gọi nội bộ thành một lời gọi đi qua proxy, nhưng **không phải hướng thiết kế được khuyến nghị**. Nó tạo sự phụ thuộc giữa mã nghiệp vụ với Spring AOP, đòi hỏi cấu hình đặc biệt, phụ thuộc vào đường đi lời gọi và thread, đồng thời có chi phí bổ sung.

Sau bài học, bạn sẽ:

1. Phân biệt **this** của target với **Spring AOP proxy**.
2. Hiểu điều kiện để **AopContext.currentProxy()** trả về proxy hoặc ném **IllegalStateException**.
3. Sử dụng **@EnableAspectJAutoProxy(exposeProxy = true)** trong cấu hình Spring Framework thuần.
4. Chạy ví dụ Java 17+ cho thấy **this.inner()** bỏ qua advice còn **((ServiceApi) AopContext.currentProxy()).inner()** đi qua advice.
5. Nhận diện giới hạn của JDK dynamic proxy, CGLIB, callback, thread mới, self-invocation, final/private và recursion.
6. Ưu tiên refactor thành **hai Spring beans có dependency rõ ràng**, thay vì đưa AopContext vào service.

**Phạm vi:** Chỉ bàn về **Spring Framework proxy-based AOP** và ảnh hưởng của currentProxy/exposeProxy tới lời gọi Spring-managed bean. Không đi sâu vào lý thuyết Aspect tổng quát hoặc AspectJ weaving.

## 2. Vấn đề gốc: self-invocation vượt qua proxy

Giả sử Spring trả về proxy P cho target T:

~~~text
Client
   |
   v
Spring AOP proxy P
   |
   +-- xem xét advisor/pointcut
   +-- chạy advice phù hợp
   |
   v
Target T.outer()
   |
   +-- this.inner() ------> T.inner()
                             |
                             +-- không quay về proxy P
~~~

Khi client gọi **outer()** qua proxy, lời gọi ngoài được Spring AOP xử lý. Nhưng khi **T.outer()** gọi **this.inner()**, biến **this** tham chiếu **target T**, không phải P. Vì vậy advice gắn với **inner()** không nhận thêm một lời gọi proxy để thực thi.

Ví dụ:

~~~java
public class OrderService {
    public void place() {
        this.validate();
    }

    public void validate() {
        // Logic kiểm tra đơn hàng
    }
}
~~~

Đây là **đoạn minh họa self-invocation**, chưa có cấu hình Spring bean hoặc aspect độc lập. Nếu advice chỉ khớp **validate()**, lời gọi từ **place()** vào **this.validate()** sẽ không chạy advice ấy khi Spring sử dụng proxy-based AOP.

Hai ý quan trọng:

- **Bean được proxy** không đồng nghĩa **mọi method invocation** đều đi qua proxy.
- **CGLIB proxy** không tự chữa self-invocation. Dù proxy là subclass, Spring AOP vẫn có ranh giới lời gọi: lời gọi phát sinh ngay trong target và không quay qua proxy sẽ bỏ qua advice.

Khi cần advice trên một thao tác, thiết kế tốt thường là **gọi thao tác đó qua Spring-managed dependency ở một bean khác**.

## 3. AopContext.currentProxy() là gì?

Spring cung cấp API:

~~~java
org.springframework.aop.framework.AopContext.currentProxy()
~~~

Method static này trả về kiểu **Object**, là **AOP proxy đang được Spring expose trên thread hiện tại**. Nó không nhận bean name hoặc target class; vì vậy **không phải API tìm một bean bất kỳ từ ApplicationContext**.

Điều kiện dùng thành công phải đồng thời thỏa:

1. Hiện tại đang ở trong **một lời gọi qua Spring AOP proxy** có cơ chế expose proxy.
2. Proxy ấy được cấu hình **exposeProxy = true**.
3. Lời gọi tới **currentProxy()** xảy ra **trên cùng thread** của invocation được expose, trong lúc invocation đó còn hoạt động.
4. Object trả về là proxy hiện tại; khi cast, kiểu cần tương thích với các interface/class được proxy công bố.

Nếu không có proxy tương ứng, currentProxy() **ném IllegalStateException**, chứ không trả **null** như một tín hiệu có thể tùy ý bỏ qua.

Các ví dụ không thỏa điều kiện:

- Gọi currentProxy() trong **main()**, ngoài bất cứ Spring AOP invocation nào.
- Gọi trong constructor hoặc **@PostConstruct** rồi mặc nhiên chờ proxy hiện tại đã tồn tại.
- Gọi trên target được tạo trực tiếp bằng **new** và được sử dụng ngoài container.
- Gọi từ code chạy ở **thread khác** so với invocation (chẳng hạn công việc được chuyển sang executor) mà không có một proxy invocation mới trên thread đó.
- Proxy được tạo nhưng **exposeProxy** vẫn mặc định **false**.

**AopContext** sử dụng một holder theo **ThreadLocal**. Spring quản lý việc đặt proxy hiện tại, khôi phục proxy cũ sau lời gọi và dọn holder khi phù hợp; ứng dụng không nên tự giả định có thể giữ object đó như một context xuyên thread, xuyên request hoặc dùng sau khi invocation đã kết thúc.

## 4. exposeProxy là gì, bật ở đâu?

**exposeProxy** là thuộc tính của cấu hình proxy Spring AOP; mặc định **false**. Khi bật, Spring công bố proxy đang xử lý invocation để **AopContext.currentProxy()** truy cập được.

Với **Spring Framework thuần** và annotation-based AOP:

~~~java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
public class AppConfig {
}
~~~

Bạn vẫn cần **đăng ký aspect và service như các Spring beans** qua **@ComponentScan**, **@Bean** hoặc cơ chế tương đương. Annotation trên chỉ là ví dụ phần cấu hình; nó chưa tự tạo service, aspect hay pointcut.

So sánh:

~~~java
@EnableAspectJAutoProxy
~~~

và:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

Cả hai bật Spring AOP auto-proxying trong context tương ứng. Dòng thứ hai **bổ sung việc expose current proxy**. Nó không làm thay đổi ý nghĩa của **@Before**, **@Around**, điều kiện match pointcut, bean registration hay khả năng chặn **private/final** của một class-based proxy.

Một cấu hình khác dễ nhầm:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

Thuộc tính **proxyTargetClass** chọn class-based proxy (CGLIB) thay vì mặc định ưu tiên JDK dynamic proxy khi phù hợp. Thuộc tính **exposeProxy** quyết định có cung cấp proxy hiện tại qua AopContext hay không. Hai thuộc tính **độc lập về mục đích**:

~~~java
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
~~~

Nếu dùng **ProxyFactory** theo lối lập trình thay vì annotation-based auto-proxy:

~~~java
factory.setExposeProxy(true);
~~~

là cấu hình tương đương **trên proxy factory đó**. Đoạn này giả sử **factory** là một instance **org.springframework.aop.framework.ProxyFactory** đã được tạo và thiết lập target/advice; không phải file Java độc lập.

## 5. Ví dụ hoàn chỉnh Java 17+: this.inner() và lời gọi lại qua proxy

Ta xây dự án **Spring Framework 6.2.12, Java 17+, Maven 3.9+**. Ví dụ không cần Spring Boot, database hay web server. Một service có ba method:

- **direct()**: gọi **this.inner("direct")**, advice cho inner **không chạy**.
- **viaProxy()**: gọi **((Operations) AopContext.currentProxy()).inner("viaProxy")**, advice cho inner **chạy** khi exposeProxy được bật và lời gọi ngoài đi qua proxy.
- **inner(String)**: method được pointcut lựa chọn.

### 5.1. Cấu trúc thư mục

~~~text
spring-aop-current-proxy/
├── pom.xml
└── src/main/java/demo/
    ├── Operations.java
    ├── OperationsImpl.java
    ├── InnerAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-current-proxy</artifactId>
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

**spring-context** cung cấp Spring ApplicationContext và kéo theo Spring AOP. **aspectjweaver** cung cấp kiểu AspectJ annotation/pointcut để Spring xử lý **@AspectJ-style advice**. Đây **vẫn là Spring AOP proxy**, không phải AspectJ compile-time hoặc load-time weaving.

### 5.3. Interface của service

**src/main/java/demo/Operations.java**

~~~java
package demo;

public interface Operations {
    void direct();
    void viaProxy();
    void inner(String source);
}
~~~

Đưa cả ba method vào interface để ví dụ hoạt động với **JDK dynamic proxy** mặc định. Khi **AopContext.currentProxy()** trả về JDK proxy, cast sang **Operations** là hợp lệ; cast sang **OperationsImpl** lại không an toàn.

### 5.4. Service triển khai hai đường gọi

**src/main/java/demo/OperationsImpl.java**

~~~java
package demo;

import org.springframework.aop.framework.AopContext;
import org.springframework.stereotype.Service;

@Service
public class OperationsImpl implements Operations {

    @Override
    public void direct() {
        System.out.println("OUTER direct");
        this.inner("direct");
    }

    @Override
    public void viaProxy() {
        System.out.println("OUTER viaProxy");
        Operations proxy = (Operations) AopContext.currentProxy();
        proxy.inner("viaProxy");
    }

    @Override
    public void inner(String source) {
        System.out.println("TARGET inner " + source);
    }
}
~~~

Điểm khác biệt duy nhất giữa hai entry methods là **đối tượng nhận lời gọi inner()**:

- Trong **direct()**, receiver là **this**, tức target hiện tại. Không có lời gọi thứ hai đi vào proxy.
- Trong **viaProxy()**, receiver là **proxy** Spring đang expose. Lời gọi inner() quay qua proxy và được advisor xem xét.

Lưu ý: **AopContext.currentProxy()** chỉ có giá trị trong đường gọi có đủ điều kiện như đã mô tả ở mục 3. Vì vậy code này **không còn là POJO độc lập**: nó phụ thuộc cụ thể vào Spring AOP.

### 5.5. Aspect chỉ bắt inner()

**src/main/java/demo/InnerAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InnerAspect {

    @Before("execution(* demo.OperationsImpl.inner(..))")
    public void beforeInner(JoinPoint joinPoint) {
        Object source = joinPoint.getArgs()[0];
        System.out.println("ADVICE inner " + source);
    }
}
~~~

Đây là một **Spring-managed aspect bean**:

- **@Aspect**: khai báo advice.
- **@Component**: cho component scanning đăng ký bean aspect.
- **@Before**: chỉ match **inner(...)** của implementation; **direct()** và **viaProxy()** không có advice riêng trong ví dụ.

Điều này làm rõ một điểm tinh tế: **viaProxy()** không cần có **@Before advice** riêng để currentProxy() hoạt động, miễn **Operations bean thực sự là proxy** và outer call đang chạy trong invocation của proxy được cấu hình exposeProxy. Spring vẫn đi qua lớp proxy khi client gọi **viaProxy()**, dù danh sách interceptor riêng cho method đó rỗng.

### 5.6. Bật component scan và exposeProxy

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy(exposeProxy = true)
public class AppConfig {
}
~~~

Cấu hình thực hiện ba việc độc lập:

1. **@Configuration**: lớp cấu hình Java cho Spring.
2. **@ComponentScan**: đăng ký **OperationsImpl** và **InnerAspect** thành Spring beans.
3. **@EnableAspectJAutoProxy(exposeProxy = true)**: bật hạ tầng Spring AOP và công bố proxy hiện tại cho AopContext.

Nếu chỉ giữ **exposeProxy = true** mà không có advisor áp dụng cho service, Spring không mặc nhiên tạo một proxy cho mọi bean. Ví dụ có advisor match inner() nên **OperationsImpl** đủ điều kiện được Spring proxy.

### 5.7. Chạy App và kiểm tra lỗi ngoài AOP invocation

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.framework.AopContext;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Operations operations = context.getBean(Operations.class);
            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(operations));

            System.out.println("=== direct ===");
            operations.direct();

            System.out.println("=== via proxy ===");
            operations.viaProxy();

            System.out.println("=== outside ===");
            try {
                AopContext.currentProxy();
                System.out.println("OUTSIDE unexpected success");
            } catch (IllegalStateException expected) {
                System.out.println("OUTSIDE IllegalStateException");
            }
        }
    }
}
~~~

Chạy trong thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java
~~~

Các dòng **stdout logic** dự kiến, không tính các thông báo riêng từ Maven hoặc cấu hình logging:

~~~text
IS_PROXY true
=== direct ===
OUTER direct
TARGET inner direct
=== via proxy ===
OUTER viaProxy
ADVICE inner viaProxy
TARGET inner viaProxy
=== outside ===
OUTSIDE IllegalStateException
~~~

Giải thích thứ tự:

1. **IS_PROXY true**: Spring trả bean **Operations** dưới dạng một AOP proxy có advisor áp dụng cho **inner**.
2. Khi gọi **operations.direct()**, Spring đi qua proxy cho method direct; sau đó target gọi **this.inner()**. Không có **ADVICE inner direct**.
3. Khi gọi **operations.viaProxy()**, target truy cập proxy hiện tại và gọi **inner()** trên proxy ấy. Advice chạy trước target nên có **ADVICE inner viaProxy**.
4. Sau khi invocation **viaProxy()** kết thúc, Spring đã khôi phục trạng thái proxy trong ThreadLocal. Code của **main()** không còn ở trong AOP invocation nên **AopContext.currentProxy()** ném **IllegalStateException** dù exposeProxy đã bật trong context.

Dòng **OUTSIDE IllegalStateException** được in bởi catch có chủ đích để minh họa API contract. Trong ứng dụng thật, không nên dựa vào exception như một cách dò bean/proxy tùy tiện.

## 6. Tự kiểm tra tác dụng của exposeProxy

### 6.1. Tắt exposeProxy nhưng giữ AOP

Trong **AppConfig.java**, đổi:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

thành:

~~~java
@EnableAspectJAutoProxy
~~~

Khởi động lại cùng ứng dụng. Spring vẫn tạo AOP proxy để áp dụng advice cho **inner()**, nhưng không expose proxy trong thread.

Khi **operations.direct()** chạy, hành vi vẫn giống trước:

~~~text
=== direct ===
OUTER direct
TARGET inner direct
~~~

Khi **operations.viaProxy()** chạy:

~~~text
=== via proxy ===
OUTER viaProxy
~~~

Sau đó **AopContext.currentProxy() ném IllegalStateException** vì exposeProxy không bật. Trong file **App.java** ở mục 5, không có try/catch bao quanh lời gọi **operations.viaProxy()**, nên **main() sẽ kết thúc bằng lỗi** thay vì in tiếp phần **=== outside ===**. Đó là **kết quả mong đợi của thí nghiệm lỗi**, không phải toàn bộ stdout có thể bảo đảm của một lần chạy Maven.

Muốn tiếp tục chương trình để quan sát cả phần outside, bạn có thể thay riêng lời gọi này bằng:

~~~java
try {
    operations.viaProxy();
} catch (IllegalStateException expected) {
    System.out.println("VIA_PROXY IllegalStateException");
}
~~~

Đây là **đoạn thay thế trong App.main**, không dùng đồng thời với lời gọi cũ. Sau khi kiểm chứng, trả cấu hình về **exposeProxy = true** để chạy lại bản hoàn chỉnh.

Kết luận: **có Spring proxy** và **có proxy hiện tại để currentProxy() lấy** là hai điều kiện khác nhau.

### 6.2. Gọi đối tượng tạo bằng new

Đoạn minh họa:

~~~java
OperationsImpl direct = new OperationsImpl();
direct.direct();
~~~

In:

~~~text
OUTER direct
TARGET inner direct
~~~

Đối tượng đó không được lấy từ Spring ApplicationContext; **direct()** không cần AopContext nên vẫn chạy, nhưng không có Spring AOP advice.

Nếu dùng:

~~~java
direct.viaProxy();
~~~

và không có một AOP invocation phù hợp đang active trên thread, currentProxy() sẽ ném **IllegalStateException**. Tạo object qua **new** không kích hoạt Spring AOP.

### 6.3. Gọi từ thread khác

Ví dụ biểu diễn ý tưởng:

~~~java
Thread thread = new Thread(() -> {
    AopContext.currentProxy();
});
thread.start();
~~~

Đây là **fragment minh họa**, chưa bắt exception ở thread mới. Thread mới **không tự thừa hưởng** AOP proxy đang expose trong ThreadLocal của thread gọi. Nếu không có một AOP proxy invocation mới được tạo trên thread kia, currentProxy() ném **IllegalStateException**.

Các tình huống như **@Async**, executor, CompletableFuture, hoặc asynchronous callback đều cần được phân tích theo thread thực tế. Ngay cả khi proxy được expose ở lời gọi bên ngoài, điều đó **không biến AopContext thành request-scoped hay asynchronous context**.

## 7. Vì sao lời gọi qua AopContext lại kích hoạt advice?

Xét đối tượng đã chạy ở mục 5:

~~~text
App
 |
 v
Operations proxy P: direct()
 |
 v
OperationsImpl target T: direct()
 |
 +-- this.inner() --> T.inner()
                        |
                        +-- advice inner không chạy
~~~

Đường khác:

~~~text
App
 |
 v
Operations proxy P: viaProxy()
 |
 v
OperationsImpl target T: viaProxy()
 |
 +-- AopContext.currentProxy() --> proxy P
                                    |
                                    +-- P.inner("viaProxy")
                                             |
                                             +-- advice inner
                                             |
                                             +-- T.inner("viaProxy")
~~~

Trong trường hợp thứ hai, lời gọi phát sinh từ target **được chuyển thành một lời gọi tới proxy P**. Spring AOP lại nhận một method invocation **inner()** hợp lệ, nên advisor áp dụng được.

Điều này **không thay đổi bytecode của inner()**, không tự sửa pointcut và không kích hoạt advice cho lời gọi trực tiếp **this.inner()** trước đó. Mọi khác biệt nằm ở **đối tượng nhận lời gọi**.

Đó cũng là nguyên nhân cần rất thận trọng với cách viết **currentProxy().someMethod()**: khi gọi nhầm method đang thực thi, bạn có thể tạo một chuỗi recursion không mong muốn.

## 8. Nguy cơ đệ quy vô hạn hoặc gọi advice lặp lại

Giả sử trong **viaProxy()** bạn viết nhầm:

~~~java
@Override
public void viaProxy() {
    Operations proxy = (Operations) AopContext.currentProxy();
    proxy.viaProxy();
}
~~~

Đây là **ví dụ mã sai**, không thay thế file chạy ở mục 5 nếu không chủ đích thử lỗi.

Chuỗi gọi là:

~~~text
proxy.viaProxy()
  -> target.viaProxy()
      -> currentProxy().viaProxy()
          -> target.viaProxy()
              -> currentProxy().viaProxy()
                  -> ...
~~~

Mã tiếp tục gọi chính entry method qua proxy, có thể kết thúc bằng **StackOverflowError**. Nếu method đó cũng được advise, advice còn có thể chạy lặp lại ở mỗi vòng.

Đối với **@Around** advice, còn một nguồn gây lặp khác: tự gọi lại một method được advice qua proxy mà không kiểm soát recursion, hoặc nhầm **ProceedingJoinPoint.proceed()** với việc thực hiện một proxy invocation mới. **proceed()** tiếp tục invocation hiện tại theo chuỗi interceptor; **currentProxy().someMethod()** tạo một lời gọi proxy khác. Hai thao tác không tương đương.

Không thay lời gọi **this** bằng currentProxy một cách máy móc. Trước tiên phải xác định chính xác method nào cần được advice, điểm vào nào an toàn và graph lời gọi sau thay đổi.

## 9. currentProxy() không phải cách lấy target hoặc bean tùy ý

API này trả về **proxy của invocation hiện tại**, không phải một BeanFactory, không phải service locator và không phải target raw.

| Nhu cầu | API phù hợp |
| --- | --- |
| Lấy một Spring bean từ container | Constructor injection, **@Bean** method parameter hoặc **ApplicationContext.getBean(...)** khi có lý do phù hợp |
| Tiếp tục invocation advice hiện tại | **ProceedingJoinPoint.proceed()** trong **@Around** advice |
| Truy cập proxy đang active trong invocation hiện tại | **AopContext.currentProxy()**, chỉ khi exposeProxy được bật |
| Xác minh một object có phải AOP proxy | **AopUtils.isAopProxy(object)** |
| Xác định proxy dùng JDK hay CGLIB | **AopUtils.isJdkDynamicProxy** / **AopUtils.isCglibProxy** |
| Tách logic sang một thao tác có advice rõ ràng | Tạo Spring bean khác và inject dependency |
| Truy cập target cụ thể từ hạ tầng AOP | Chỉ dùng API dành cho hạ tầng khi thật sự cần; không coi currentProxy là target |

Giả sử **currentProxy()** trả về một **JDK dynamic proxy** của **Operations**. Không nên cast:

~~~java
OperationsImpl impl =
        (OperationsImpl) AopContext.currentProxy();
~~~

Với JDK proxy, cast này có thể gây **ClassCastException**. Vì thế ví dụ chính cast về **Operations**, interface thực sự được proxy triển khai.

Với CGLIB, proxy là subclass của target nếu cấu hình và class cho phép; cast về target class có thể hợp lệ, nhưng **điều đó không xóa giới hạn self-invocation, final/private và exposeProxy**.

## 10. Vì sao Spring khuyến nghị hạn chế sử dụng?

Tài liệu Spring Framework về **Proxying Mechanisms** xem việc dùng **AopContext.currentProxy()** là cách nên tránh nếu có lựa chọn hợp lý hơn. Có ba nhóm lý do thực tế.

### 10.1. Coupling giữa nghiệp vụ và Spring AOP

Service bình thường chỉ cần triển khai interface của mình và gọi dependency:

~~~java
public void process() {
    collaborator.run();
}
~~~

Khi chuyển thành:

~~~java
public void process() {
    ((Operations) AopContext.currentProxy()).inner("work");
}
~~~

service đã biết rằng nó phải chạy dưới **Spring AOP proxy** có exposeProxy. Điều này giảm khả năng tái sử dụng class trong môi trường không dùng Spring AOP, gây khó khăn cho unit test thuần Java, và có thể làm code fail bất ngờ khi cấu hình proxy đổi.

**Dependency ngầm** này không nằm trong constructor hoặc interface của service. Người đọc class có thể không biết muốn gọi **process()** phải đi qua một proxy được cấu hình đặc biệt.

### 10.2. Điều kiện runtime mong manh

currentProxy() phụ thuộc vào **thread và invocation hiện tại**. Một service có thể chạy đúng khi được gọi qua controller/injected proxy nhưng lỗi khi:

- được gọi trực tiếp trong unit test;
- được tạo bằng **new**;
- được gọi trong constructor/init callback;
- được gọi từ callback chạy sau khi proxy invocation đã hoàn tất;
- được chuyển sang thread khác;
- được gọi ở context hoặc proxy không bật exposeProxy;
- bị cấu hình lại advisor khiến bean không còn được Spring proxy.

Vấn đề có thể chỉ xuất hiện ở một đường gọi cụ thể, khiến kiểm thử và chẩn đoán khó hơn dependency injection bình thường.

### 10.3. Chi phí và phạm vi tác động của exposeProxy

Spring **không expose proxy theo mặc định**, một phần vì việc cập nhật và khôi phục ThreadLocal cho các proxy invocation có **chi phí bổ sung**. Không nên đưa ra con số phần trăm hiệu năng nếu chưa benchmark tải thực tế.

Bật exposeProxy không phải giải pháp “miễn phí” cho mọi bean được auto-proxy; nên tránh bật rộng chỉ vì một method đang có self-invocation. Điều này đặc biệt quan trọng khi hệ thống có nhiều advice, nesting hoặc throughput lớn.

### 10.4. Khả năng nhầm proxy hiện tại trong chuỗi gọi lồng nhau

Giả sử proxy A gọi một proxy B trên cùng thread, bên trong lời gọi B thì **currentProxy()** trỏ tới **proxy của invocation B đang hoạt động**, không nhất thiết là A. Khi B kết thúc, Spring khôi phục trạng thái proxy trước đó. Code tự ý cast hoặc lưu currentProxy() mà không hiểu ngữ cảnh lồng nhau có thể dùng sai loại proxy.

Vì vậy currentProxy() không tương đương **“lấy proxy của chính class này ở mọi thời điểm”**. Ý nghĩa chính xác của nó là **proxy đang được expose bởi invocation đang hoạt động trên thread hiện tại**.

## 11. Hướng thay thế được ưu tiên: tách thành hai Spring beans

Cách giải quyết ít coupling nhất là **không tự gọi vào method cần AOP trong cùng target**. Thay vào đó, tạo một bean thực hiện method đó, rồi inject bean này vào bean điều phối.

Ví dụ một thiết kế khác cho nghiệp vụ đơn hàng:

~~~text
OrderOrchestrator bean
         |
         | constructor injection
         v
OrderValidation bean/proxy
         |
         +-- @Before advice phù hợp
         |
         v
OrderValidationImpl.validate(...)
~~~

Code Java minh họa đầy đủ các lớp chính:

**src/main/java/demo/ValidationApi.java**

~~~java
package demo;

public interface ValidationApi {
    void validate(String id);
}
~~~

**src/main/java/demo/ValidationService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ValidationService implements ValidationApi {

    @Override
    public void validate(String id) {
        System.out.println("VALIDATE " + id);
    }
}
~~~

**src/main/java/demo/OrderOrchestrator.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderOrchestrator {

    private final ValidationApi validation;

    public OrderOrchestrator(ValidationApi validation) {
        this.validation = validation;
    }

    public void process(String id) {
        System.out.println("PROCESS " + id);
        validation.validate(id);
    }
}
~~~

**src/main/java/demo/ValidationAspect.java**

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ValidationAspect {

    @Before("execution(* demo.ValidationService.validate(..))")
    public void beforeValidation() {
        System.out.println("ADVICE validate");
    }
}
~~~

Các lớp trên là **phương án kiến trúc thay thế**, không phải các file cần chèn đồng thời vào project **spring-aop-current-proxy** để tái tạo đúng stdout ở mục 5; nếu bổ sung chúng vào cùng package demo, context sẽ phát hiện thêm beans và advisor.

Với một context có **@ComponentScan("demo")** và **@EnableAspectJAutoProxy** (không cần exposeProxy), khi lấy **OrderOrchestrator** từ Spring và gọi **process("A-1")** qua bean, các dòng logic kỳ vọng là:

~~~text
PROCESS A-1
ADVICE validate
VALIDATE A-1
~~~

Vì sao tốt hơn:

1. **OrderOrchestrator** phụ thuộc vào **ValidationApi**, một hợp đồng Java thông thường.
2. **ValidationService** là một Spring bean độc lập và có thể được proxy khi pointcut khớp.
3. Lời gọi **validation.validate(...)** từ orchestrator đi qua dependency được inject, tức Spring có cơ hội cung cấp **AOP proxy**.
4. Không dùng AopContext, không cần exposeProxy và không phụ thuộc vào ThreadLocal.
5. Unit test có thể truyền fake **ValidationApi** qua constructor mà không khởi động Spring.
6. Trách nhiệm nghiệp vụ và điểm cắt Spring AOP được phân chia rõ ràng.

Đây là lời giải nên ưu tiên ngay cả khi cần thêm một bean hoặc một interface nhỏ.

## 12. Self-injection: một lựa chọn khác nhưng cần thận trọng

Một cách khác là để service nhận tham chiếu tới chính **interface của bean đó** được Spring quản lý, rồi gọi qua tham chiếu này thay cho **this**. Ví dụ **minh họa ý tưởng**:

~~~java
@Service
public class ExampleService implements ExampleApi {

    private final ExampleApi self;

    public ExampleService(@Lazy ExampleApi self) {
        this.self = self;
    }

    @Override
    public void outer() {
        self.inner();
    }

    @Override
    public void inner() {
        // ...
    }
}
~~~

Đoạn fragment trên cần có interface **ExampleApi** và import **@Service**, **@Lazy**, cùng AOP configuration; không phải file thuộc project runnable mục 5. **@Lazy** tại injection point có thể khiến Spring tạo một lazy-resolution proxy rồi resolve bean sau; cách này cần kiểm thử kỹ.

Ưu điểm so với AopContext là không cần gọi static API và không yêu cầu exposeProxy. Tuy nhiên nó đưa **self-reference** vào dependency graph, có thể phát sinh phụ thuộc vòng hoặc các tình huống khởi tạo tinh vi; cũng cần nhận thức rằng bean có thể được proxy theo interface hoặc class. Spring documentation xem đây là một lựa chọn thay thế, nhưng cách **refactor để tránh self-invocation** vẫn sạch hơn.

**Không** tự động thêm self-injection vào mọi service. Đặc biệt, vòng phụ thuộc constructor trực tiếp không được coi là hợp lệ chỉ vì muốn advice chạy cho method nội bộ.

## 13. Một tình huống quan trọng: @Transactional và các advice khác

Spring cũng sử dụng proxy cho nhiều tính năng như declarative transactions, security, caching hoặc custom aspect. Hệ quả self-invocation có thể tương tự khi tính năng ở **proxy mode**:

~~~java
public void outer() {
    this.innerTransactional();
}
~~~

Nếu **innerTransactional()** chỉ được áp dụng transaction advice khi đi qua proxy, lời gọi **this.innerTransactional()** không được proxy advice xử lý như một invocation độc lập. Tuy nhiên, cần phân biệt:

- Nếu **outer()** đã có transaction hoặc advice, lời gọi nội bộ có thể **tiếp tục chạy trong transaction/context đang tồn tại**. “Advice không chạy thêm” không đồng nghĩa “không có transaction nào”.
- Nếu dùng **currentProxy()** để gọi innerTransactional qua proxy, advisor có thể được xét lại; kết quả còn phụ thuộc transaction propagation, annotation metadata, loại proxy và phương thức có interceptable hay không.
- Không nên khuyến nghị bật exposeProxy chỉ để sửa một transaction boundary sai kiến trúc; tách method sang bean khác, xem xét transaction service boundary và test kết quả thực tế.

Ví dụ này **chỉ giải thích hệ quả của ranh giới Spring proxy**, không thay thế tài liệu cấu hình transaction manager hoặc quy tắc của @Transactional.

## 14. Với JDK proxy và CGLIB, currentProxy() khác nhau thế nào?

**AopContext.currentProxy()** trả về **đối tượng proxy thực tế** của invocation, nên kiểu cast hợp lệ phụ thuộc cách Spring tạo proxy.

### 14.1. JDK dynamic proxy

Khi target có interface và Spring chọn JDK proxy, object trả về triển khai những interface mà proxy công bố. Trong ví dụ mục 5, dùng:

~~~java
Operations proxy = (Operations) AopContext.currentProxy();
proxy.inner("X");
~~~

là đúng. Không mặc định cast sang **OperationsImpl**.

JDK dynamic proxy chỉ expose các method thuộc những interface đã được proxy; method public chỉ có trên implementation không tự được công bố bởi interface proxy đó.

### 14.2. CGLIB class-based proxy

Khi dùng:

~~~java
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
~~~

Spring có thể tạo subclass proxy. currentProxy() lúc này có thể được cast theo target class nếu class và cơ chế proxy cho phép; nhưng protected/package-visible còn tuân theo Java visibility, final/private không thể override, và self-invocation vẫn không đi qua proxy.

Không cố khắc phục một method không thể advice chỉ bằng việc bật **exposeProxy**. Nếu method là private hoặc final trên class-based proxy, chuyển receiver thành proxy cũng không làm phép override bất khả thi trở thành hợp lệ.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| **AopContext.currentProxy()** ném IllegalStateException | exposeProxy chưa bật hoặc không có invocation phù hợp trên thread hiện tại | Kiểm tra @EnableAspectJAutoProxy(exposeProxy=true), đường gọi qua proxy và thread |
| Bean là AOP proxy nhưng currentProxy() vẫn thất bại | Có proxy không đồng nghĩa proxy đang được expose | Xác minh cấu hình exposeProxy và thời điểm gọi |
| Chạy được qua Spring, lỗi khi unit test bằng new | Test dùng target raw thay vì Spring-managed proxy | Test logic thuần không phụ thuộc AopContext, hoặc dùng integration test qua context |
| ClassCastException khi cast currentProxy() | JDK proxy không phải subclass của implementation | Cast theo interface proxy thực sự triển khai |
| currentProxy() ở async task thất bại | ThreadLocal không tự truyền sang thread khác | Đặt AOP boundary phù hợp ở thread thực thi hoặc refactor |
| Thấy proxy nhưng lời gọi inner không chạy advice | this.inner() bỏ qua proxy, hoặc pointcut không match | Kiểm tra receiver, pointcut, method visibility và finality |
| currentProxy() được trả về nhưng advice không chạy | Lời gọi mới qua proxy không có advisor phù hợp | Kiểm tra method có match và interceptable không |
| StackOverflowError sau khi dùng currentProxy | Lặp lại lời gọi proxy vào chính entry method | Phân tích call graph, tránh recursion không có điều kiện dừng |
| Advice bị chạy nhiều lần ngoài dự kiến | Gọi lại method qua proxy hoặc nested invocations tạo thêm advice | Đếm proxy entry, xem thứ tự và điều kiện advisor |
| exposeProxy bật nhưng target không được proxy | Không có advisor phù hợp hoặc bean không phải Spring-managed | Kiểm tra bean registration, @Aspect, pointcut |
| Khởi tạo bean lỗi khi self-injection | Vòng dependency hoặc bean chưa sẵn sàng | Refactor thành hai bean độc lập, không dựa vào vòng constructor |
| Dựa vào currentProxy làm trạng thái request | AopContext chỉ gắn với invocation/thread, không phải request context | Dùng request scope hoặc context chuyên dụng nếu thật sự cần |

## 16. Checklist khi bắt buộc cân nhắc currentProxy()

Trước khi chấp nhận giải pháp này, hãy tự trả lời:

1. **Tại sao không thể tách method cần advice sang bean khác?** Nếu có thể refactor, ưu tiên làm thế.
2. **Bean có luôn được lấy qua Spring ApplicationContext không?** Nếu có đường code tự tạo target raw, currentProxy không đáng tin.
3. **Có bảo đảm caller đi qua AOP proxy trước khi method gọi currentProxy() không?** Mặc định interface method nên được expose rõ.
4. **Proxy đã bật exposeProxy chưa?** Bật thuộc tính này không tự tạo advisor hoặc bean.
5. **Code có chạy cùng thread và trong thời gian invocation đang hoạt động không?** Đừng phụ thuộc vào async ThreadLocal propagation.
6. **Kiểu cast có phù hợp JDK/CGLIB không?** Dùng interface proxy công bố khi có thể.
7. **Method được gọi lại có interceptable và pointcut match không?** Private/final hoặc self-invocation khác có thể tiếp tục bỏ qua advice.
8. **Có nguy cơ gọi đệ quy cùng entry method không?** Xem call graph, đặc biệt với @Around, retry và transaction advice.
9. **Có integration test kiểm chứng cả trường hợp bật/tắt exposeProxy không?** Dùng assertion về advice thực tế, không chỉ isAopProxy.
10. **Có cần benchmark nếu lượng gọi rất lớn không?** Expose proxy có chi phí ThreadLocal; đo trong bối cảnh ứng dụng thật.

Nếu vẫn buộc phải dùng, giới hạn đường gọi dựa vào currentProxy vào một chỗ có giải thích rõ ràng, không phổ biến thành coding convention cho toàn bộ service layer.

## 17. Câu hỏi tự đánh giá

**Câu 1. Vì sao this.inner() không chạy @Before cho inner()?**

Vì **this** là target và lời gọi nội bộ không tạo một lời gọi mới đi qua Spring AOP proxy. Advice của inner không được xét riêng cho lời gọi đó.

**Câu 2. Có Spring AOP proxy rồi, tại sao AopContext.currentProxy() vẫn có thể ném lỗi?**

Vì proxy hiện tại phải **được expose** và method phải chạy trong một **AOP invocation trên cùng thread**. Có proxy trong context không đủ.

**Câu 3. @EnableAspectJAutoProxy(exposeProxy = true) có khiến mọi bean thành proxy không?**

Không. Spring vẫn cần các bean được đăng ký và advisor/pointcut phù hợp để tạo proxy tương ứng.

**Câu 4. Với JDK proxy, nên cast kết quả currentProxy() về kiểu nào?**

Về một **interface thực sự được proxy triển khai**, ví dụ **Operations**, không cast tùy tiện về **OperationsImpl**.

**Câu 5. Có nên dùng currentProxy() từ constructor hoặc @PostConstruct không?**

Không mặc định. Những callback đó không bảo đảm đang ở trong một AOP proxy invocation có exposeProxy; còn có rủi ro bean chưa khởi tạo hoàn tất.

**Câu 6. currentProxy() có dùng được trong thread mới tạo từ method đang được proxy không?**

Thread mới không tự nhận ThreadLocal proxy của thread gọi; cần có invocation riêng trên thread ấy hoặc thay thiết kế.

**Câu 7. Vì sao refactor thành hai Spring beans được ưu tiên?**

Vì lời gọi tới dependency được inject có thể đi qua proxy một cách tường minh, giảm coupling với static Spring AOP API, dễ test và không yêu cầu exposeProxy.

**Câu 8. Khi gọi currentProxy().inner(), liệu advice chắc chắn chạy không?**

Không. Method phải có advisor/pointcut khớp, interceptable theo JDK/CGLIB và được gọi qua đúng proxy; exposeProxy chỉ tạo điều kiện **lấy proxy hiện tại**.

**Câu 9. Khi proxy A gọi proxy B lồng nhau, currentProxy() trả proxy nào trong B?**

Nó trả proxy đang được expose bởi **invocation hiện tại** trên thread, tức thường là B trong lúc B hoạt động, rồi Spring khôi phục proxy trước khi B kết thúc.

**Câu 10. CGLIB có xóa vấn đề self-invocation không?**

Không. Class-based proxy không khiến lời gọi trực tiếp **this.method()** trong target tự quay lại Spring AOP proxy.

## 18. Tài liệu Spring Framework chính thức

- **Spring Framework 6.2 — Proxying Mechanisms và self-invocation:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- **Spring Framework 6.2.12 — AopContext Javadoc:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/framework/AopContext.html
- **Spring Framework — @AspectJ Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — JDK dynamic proxies và CGLIB:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — Annotation-based AOP configuration:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/autoproxy.html

**Kết luận:** **AopContext.currentProxy()** là lối truy cập proxy hiện tại để xử lý một số lời gọi nội bộ trong Spring AOP khi **exposeProxy=true**. Nó có tác dụng ở đúng invocation, thread, proxy type và pointcut, nhưng làm code lệ thuộc chặt vào Spring AOP. **Không dùng làm giải pháp mặc định cho self-invocation**; ưu tiên tách chức năng cần advice sang một Spring bean khác và gọi qua dependency injection.
