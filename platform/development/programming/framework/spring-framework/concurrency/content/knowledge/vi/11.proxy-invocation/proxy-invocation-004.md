# Proxy theo interface và proxy theo lớp

## 1. Vì sao Spring cần proxy?

Trong Spring Framework, nhiều tính năng không chỉ chạy mã của phương thức gốc mà còn phải làm việc **trước, sau hoặc xung quanh lời gọi**. Ví dụ:

- `@Async`: gửi phương thức tới `TaskExecutor` để thực thi bất đồng bộ.
- `@Transactional`: mở/tham gia transaction, commit hoặc rollback theo kết quả.
- Spring AOP: logging, đo thời gian, kiểm soát quyền hoặc các *advice* tùy chỉnh.
- Một số cơ chế cache, retry hoặc bảo mật được cài đặt bằng interceptor/proxy.

Spring thường cung cấp cho đối tượng gọi **một proxy** thay vì tham chiếu trực tiếp tới đối tượng nghiệp vụ (*target*). Proxy quyết định chạy interceptor nào, rồi mới chuyển lời gọi tới target.

```text
Bean A (caller)
      |
      | gọi service.process()
      v
  [ SPRING PROXY ]
      |
      +-- advice/interceptor: @Async / @Transactional / AOP ...
      |
      v
  [ TARGET OBJECT ]
      |
      v
  business method
```

**Hai cơ chế proxy chủ yếu** là **JDK dynamic proxy theo interface** và **CGLIB proxy theo lớp**. Chọn cơ chế nào ảnh hưởng đến kiểu đối tượng Spring có thể inject, phương thức nào có thể được proxy, những hạn chế liên quan đến `final` và việc annotation có được áp dụng ở ranh giới lời gọi hay không.

**Điểm quan trọng nhất cho concurrency:** dù là JDK proxy hay CGLIB proxy, trong chế độ Spring AOP *proxy-based* mặc định, **lời gọi nội bộ `this.someMethod()` trên target không đi qua proxy**. Vì thế `@Async` có thể không tạo task mới và `@Transactional` có thể không mở transaction theo mong đợi.

## 2. Proxy theo interface: JDK dynamic proxy

### 2.1. Cấu trúc

Một đối tượng nghiệp vụ triển khai interface:

```java
public interface ReportService {
    String generate(String id);
}

public class ReportServiceImpl implements ReportService {
    @Override
    public String generate(String id) {
        return "report:" + id;
    }

    public String internalStatus() {
        return "ready";
    }
}
```

Hai khai báo này là **snippet mô tả API**, không phải một chương trình độc lập (mỗi `public` type thường cần tệp riêng). Spring có thể tạo JDK dynamic proxy triển khai `ReportService` và những interface được chọn của target. Một caller có tham chiếu kiểu `ReportService` sẽ gọi vào proxy.

```text
ReportService interface
          ^
          | implements
          |
   JDK dynamic proxy ---- advice ----> ReportServiceImpl (target)
          ^
          |
      caller injects ReportService
```

**Đặc điểm:**

- Proxy là một đối tượng **triển khai interface**, không phải subclass của `ReportServiceImpl`.
- Các phương thức nghiệp vụ đi qua proxy phải nằm trong **interface được proxy**. Phương thức `internalStatus()` chỉ có trên lớp implementation, không phải API có thể gọi qua biến `ReportService`.
- Với cấu hình JDK proxy, `proxy instanceof ReportService` thường là `true`, nhưng `proxy instanceof ReportServiceImpl` là `false`.
- Vì thế, inject theo **kiểu interface** tương thích, còn ép JDK proxy về `ReportServiceImpl` sẽ không hợp lệ và thường dẫn tới `ClassCastException`. Inject bean bị proxy theo kiểu concrete class có thể gây lỗi dependency resolution ở startup nếu kiểu proxy không gán được.
- JDK proxy không đòi target class có thể được subclass. Tuy nhiên, phương thức cần được expose qua interface và cơ chế annotation/advisor phải nhận diện đúng phương thức nghiệp vụ.

Không hiểu “proxy theo interface” là Spring tạo **một interface mới** chứa code. Interface chỉ mô tả hợp đồng; JDK tạo lớp proxy ở runtime để chuyển cuộc gọi tới interceptor/target.

### 2.2. Hệ quả với @Async

Nếu service có phương thức `@Async` chỉ hiện diện trên implementation nhưng không khai báo trong interface, caller chỉ nhìn thấy biến kiểu interface **không thể trực tiếp gọi phương thức đó**. Với API công khai được gọi từ bean khác, hãy đưa chữ ký phương thức cần sử dụng vào interface hoặc cân nhắc class-based proxy có lý do rõ ràng.

Với Spring, nên đặt annotation nghiệp vụ trên **phương thức implementation** để rõ nguồn hiệu lực, đặc biệt khi code có thể chuyển qua nhiều chế độ proxy/weaving. Không suy luận rằng đổi từ JDK sang CGLIB tự kích hoạt mọi phương thức mang `@Async`: phương thức vẫn cần lời gọi đi qua proxy và đủ điều kiện được intercept.

## 3. Proxy theo lớp: CGLIB subclass proxy

Khi target không có interface phù hợp, hoặc cấu hình buộc dùng proxy theo lớp, Spring có thể dùng **CGLIB** (được repackaged trong `spring-core`) để tạo một **subclass runtime** của lớp target.

```text
ReportServiceImpl
       ^
       | extends
       |
 CGLIB-generated subclass(proxy)
       |
       +-- interceptor/advice
       +-- delegates method invocation to target
       |
     caller
```

**Khác biệt cốt lõi:**

- Proxy CGLIB là một subtype của target class, vì vậy có thể được inject theo **concrete class** hoặc interface mà nó triển khai.
- Phương thức public của target dù **không khai báo trong interface** vẫn có thể là điểm được advice nếu phương thức đủ điều kiện override/intercept và advisor áp dụng cho nó.
- Không cần viết interface chỉ để Spring tạo proxy.
- CGLIB sử dụng cơ chế subclass, vì vậy có những ràng buộc thật của Java inheritance.

### Những giới hạn không thể bỏ qua

| Tình huống | CGLIB class-based proxy |
| --- | --- |
| Lớp `final` | Không thể tạo subclass để proxy lớp đó |
| Phương thức `final` | Không thể override để advice phương thức đó |
| Phương thức `private` | Không override/intercept được bằng subclass |
| Phương thức không đủ khả năng truy cập | Có thể không advice được, chẳng hạn package-private ở parent package khác |
| `this.process()` gọi nội bộ | Vẫn bypass proxy trong Spring AOP proxy mode |
| Lớp thuộc module/JDK bị đóng truy cập | Có thể gặp ràng buộc Java Module System |

**Không nhầm “CGLIB là subclass” với “mọi lần gọi `this.method()` đều đi qua subclass proxy”.** Trong Spring AOP, proxy chuyển lời gọi tới target; bên trong target, `this` là tham chiếu target, nên lời gọi nội bộ không tự đi lại qua proxy. Đây là lý do tự gọi `@Async` hoặc `@Transactional` không được advice trong cả hai chế độ.

Spring thường dùng Objenesis khi tạo proxy theo lớp để tránh gọi constructor hai lần; tuy nhiên không nên xây dựng logic nghiệp vụ dựa trên chi tiết khởi tạo proxy, và vẫn cần tuân thủ khả năng subclass, visibility và Java module constraints.

### Trường hợp có cả interface và class-based proxy

Một implementation có interface **vẫn có thể** được CGLIB proxy nếu cấu hình bật `proxyTargetClass=true`. JDK proxy không phải là quy tắc bất biến cho mọi bean có interface; đó là **lựa chọn mặc định của Spring AOP trong cấu hình không ép lớp**, còn Spring Boot và các cấu hình tự động có thể thay đổi quyết định cuối cùng.

## 4. So sánh nhanh hai loại proxy

| Khía cạnh | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| Nền tảng | `java.lang.reflect.Proxy` | Subclass tạo ở runtime |
| Điều kiện chính | Có ít nhất một interface được proxy | Target class có thể subclass |
| Kiểu proxy | Triển khai interface | Kế thừa target class |
| Có thể inject theo interface | Có | Có, nếu target triển khai interface |
| Có thể inject theo concrete implementation | Không, với JDK proxy thông thường | Có |
| Phương thức chỉ tồn tại trên implementation | Không được expose qua interface proxy | Có thể được advice nếu override/visibility hợp lệ |
| Lớp `final` | JDK proxy vẫn có thể wrap interface của một target final | Không subclass được |
| Phương thức `final` | Có thể intercept lời gọi **qua interface** trước khi đi vào target | Không advice được bằng override |
| Phương thức `private` | Không nằm trong hợp đồng interface proxy | Không advice trực tiếp được |
| Lời gọi nội bộ `this.method()` | Bypass proxy | Bypass proxy |
| Hạn chế JPMS | Theo giới hạn proxy/interface/JVM | Có thể vướng quyền mở package cho subclass generation |

Trong thực tế, **thiết kế ranh giới lời gọi** và **tính đúng đắn của nghiệp vụ** quan trọng hơn chênh lệch hiệu năng giữa hai cơ chế. Đừng đổi sang CGLIB chỉ với giả định “nó luôn nhanh hơn” hoặc “nó sửa được self-invocation”.

## 5. Spring chọn kiểu proxy như thế nào?

### 5.1. Trong Spring Framework thông thường

Với Spring AOP theo proxy, khi target có interface và không có cấu hình buộc proxy theo lớp, Spring thường chọn **JDK dynamic proxy**. Khi không có interface phù hợp, Spring sử dụng **CGLIB class proxy**. Có thể ép dùng proxy theo lớp bằng:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

hoặc với quản lý transaction:

```java
@EnableTransactionManagement(proxyTargetClass = true)
```

và với xử lý asynchronous:

```java
@EnableAsync(proxyTargetClass = true)
```

Đây là **snippet cấu hình annotation**, không phải file Java độc lập. Các annotation này cần import, đặt ở class cấu hình thích hợp và bổ sung dependency tương ứng. `proxyTargetClass=true` chỉ có ý nghĩa trong chế độ proxy; nó **không chuyển** sang AspectJ weaving.

### 5.2. Trong Spring Boot

Spring Boot có auto-configuration AOP và **thường mặc định dùng CGLIB class-based proxy** cho Spring AOP. Khi muốn bật JDK interface-based proxy cho phần auto-configuration đó, có thể cấu hình:

```properties
spring.aop.proxy-target-class=false
```

Hoặc chọn class-based:

```properties
spring.aop.proxy-target-class=true
```

**Không kết luận** chỉ dựa trên thuộc tính này rằng mọi `@Async`/`@Transactional` bean trong mọi phiên bản Spring Boot chắc chắn dùng cùng kiểu. Kiểu proxy thực tế chịu ảnh hưởng phiên bản Framework/Boot, cấu hình annotation, loại bean, post-processor và các cấu hình proxy kết hợp. Khi nhiều bộ auto-proxy cùng hoạt động, cấu hình buộc subclass có thể có ảnh hưởng rộng hơn một bean.

Ví dụ trong **Spring Framework 6.2**, `@EnableAsync(proxyTargetClass = true)` có thể ảnh hưởng tới các bean Spring-managed khác cần proxy, không chỉ những bean có `@Async`. Không dùng nó như một “switch cục bộ tuyệt đối” rồi bỏ qua transaction/AOP đang chạy.

### 5.3. Kiểm tra thay vì đoán

Dùng API Spring:

```java
import org.springframework.aop.support.AopUtils;

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đây là snippet chạy trong môi trường có bean Spring `bean` thực tế và module `spring-aop`. Kiểm tra sau khi lấy bean từ `ApplicationContext`, không phải đối tượng tự tạo bằng `new`. `bean.getClass().getName()` có thể hữu ích cho debug, nhưng tên lớp proxy tạo động không nên được hard-code trong test.

## 6. Ví dụ thực hành Maven + Java 17: JDK proxy và CGLIB trên cùng một target type

Ví dụ này tạo proxy **bằng Spring `ProxyFactory`**, không phụ thuộc vào cơ chế tự động scan bean. Cách đó làm lựa chọn JDK/CGLIB hoàn toàn rõ ràng. Một `MethodBeforeAdvice` in log khi phương thức `hello(...)` được gọi **qua proxy**; đồng thời phương thức `localCall()` cho thấy self-invocation không được advice.

**Điều kiện:** JDK 17 trở lên, Maven 3.x, Spring Framework **6.2.10** (phiên bản được khóa cho ví dụ).

Cấu trúc:

```text
spring-proxy-modes/
├── pom.xml
└── src/main/java/demo/ProxyModeDemo.java
```

### 6.1. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-proxy-modes</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.10</version>
        </dependency>
        <dependency>
            <groupId>aopalliance</groupId>
            <artifactId>aopalliance</artifactId>
            <version>1.0</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ProxyModeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Tệp src/main/java/demo/ProxyModeDemo.java

```java
package demo;

import org.springframework.aop.MethodBeforeAdvice;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

public final class ProxyModeDemo {
    // Hợp đồng mà JDK dynamic proxy có thể triển khai.
    public interface Greeter {
        String hello(String name);
    }

    // Phải không-final để CGLIB có thể tạo subclass.
    public static class GreeterImpl implements Greeter {
        @Override
        public String hello(String name) {
            return "hello:" + name;
        }

        // Phương thức này KHÔNG được khai báo trong interface.
        public String localCall() {
            return "local:" + this.hello("inside");
        }
    }

    private static ProxyFactory createFactory(boolean classProxy) {
        ProxyFactory factory = new ProxyFactory(new GreeterImpl());
        factory.setInterfaces(Greeter.class);
        factory.setProxyTargetClass(classProxy);

        factory.addAdvice((MethodBeforeAdvice) (method, args, target) -> {
            if ("hello".equals(method.getName())) {
                System.out.println("advice:" + args[0]);
            }
        });
        return factory;
    }

    public static void main(String[] args) {
        Greeter jdk = (Greeter) createFactory(false).getProxy();
        System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(jdk));
        System.out.println("jdkConcrete=" + (jdk instanceof GreeterImpl));
        System.out.println(jdk.hello("outside"));

        GreeterImpl cglib =
                (GreeterImpl) createFactory(true).getProxy();
        System.out.println("cglibProxy=" + AopUtils.isCglibProxy(cglib));
        System.out.println("cglibConcrete=" + (cglib instanceof GreeterImpl));
        System.out.println(cglib.hello("outside"));
        System.out.println(cglib.localCall());
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Standard output từ chương trình (không tính log của Maven):**

```text
jdkProxy=true
jdkConcrete=false
advice:outside
hello:outside
cglibProxy=true
cglibConcrete=true
advice:outside
hello:outside
local:hello:inside
```

### 6.3. Phân tích từng quan sát

- `jdkProxy=true`: factory được chỉ định dùng JDK dynamic proxy. Biến `jdk` là một `Greeter`; proxy không kế thừa `GreeterImpl` nên `jdkConcrete=false`.
- Gọi `jdk.hello("outside")` từ main đi qua proxy, vì vậy dòng `advice:outside` xuất hiện trước dòng kết quả `hello:outside`.
- Với `classProxy=true`, Spring tạo CGLIB proxy kế thừa `GreeterImpl`. `cglibConcrete=true` là hệ quả của quan hệ subclass; gọi `cglib.hello(...)` từ main cũng đi qua advice.
- `cglib.localCall()` gọi tới target; bên trong target, `this.hello("inside")` **không đi lại qua proxy**, nên kết quả chỉ là `local:hello:inside`, **không có** dòng `advice:inside`.
- Ví dụ thể hiện nguyên tắc cho **Spring AOP proxy**. Nó không dùng annotation `@Async` hay mở transaction DB; advice ở đây là `MethodBeforeAdvice` đơn giản để nhìn rõ ranh giới interception.

Nếu có thêm advisor cho `localCall()`, lời gọi bên ngoài có thể được advise ở chính phương thức `localCall()`, nhưng điều đó **không làm phát sinh lời gọi proxy thứ hai cho `this.hello()`**.

**Vì sao dùng Maven thay vì `javac ProxyModeDemo.java`?** Vì `ProxyFactory`, `MethodBeforeAdvice` và CGLIB integration thuộc thư viện Spring; biên dịch trực tiếp chỉ với JDK mà không có classpath của Spring sẽ thất bại. Maven tải dependency và dựng classpath thích hợp; mã nguồn vẫn là Java 17.

## 7. Tác động lên @Async: lời gọi bên ngoài và tự gọi nội bộ

Xét một service do Spring quản lý:

```java
public interface NotificationService {
    java.util.concurrent.CompletableFuture<String> send(String id);
    void trigger(String id);
}
```

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationServiceImpl implements NotificationService {
    @Override
    @Async("notificationExecutor")
    public CompletableFuture<String> send(String id) {
        String result = "sent:" + id;
        return CompletableFuture.completedFuture(result);
    }

    @Override
    public void trigger(String id) {
        // SAI nếu mong @Async được áp dụng ở lời gọi này:
        this.send(id);
    }
}
```

Đây là các **snippet tích hợp**: interface và implementation cần tệp riêng; ứng dụng phải bật `@EnableAsync` và có bean executor tên `notificationExecutor`.

Có hai đường đi khác nhau:

```text
Bean A inject NotificationService
     |
     +-- notificationService.send("x")
     |        |
     |        +--> Spring proxy --> @Async interceptor --> executor
     |                                           |
     |                                           +--> target.send("x")
     |
     +-- notificationService.trigger("x")
              |
              +--> Spring proxy --> target.trigger("x")
                                      |
                                      +--> this.send("x")
                                              |
                                              +--> target.send("x") trực tiếp
                                                   (KHÔNG qua @Async proxy)
```

Vì `trigger()` gọi `this.send()` trên cùng target, mã `send()` ở đường này có thể chạy **trong thread hiện tại** thay vì được dispatch qua executor. Điều này đúng với **cả JDK và CGLIB** ở chế độ proxy thông thường.

### Cách sửa nên ưu tiên: gọi qua bean khác

Tách phương thức bất đồng bộ sang bean riêng và để orchestration ở bean khác:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class NotificationCoordinator {
    private final NotificationService notificationService;

    public NotificationCoordinator(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    public CompletableFuture<String> trigger(String id) {
        // Gọi qua reference được Spring inject -> đi qua proxy.
        return notificationService.send(id);
    }
}
```

Đây cũng là snippet tích hợp với `NotificationService` ở trên. Ưu điểm: ranh giới async rõ ràng, dễ test bằng bean khác và ít phụ thuộc chi tiết AOP. Cần bảo đảm đối tượng được inject thực sự là Spring bean đã proxied; tự tạo `new NotificationServiceImpl()` rồi gọi sẽ không được Spring intercept.

### Chọn kiểu proxy có giải quyết tự gọi nội bộ không?

**Không.** Chuyển `@EnableAsync(proxyTargetClass=true)` chỉ đổi công nghệ tạo proxy, không khiến `this.send()` trên target quay lại proxy. Nếu cần intercept self-invocation, Spring hỗ trợ chế độ `AdviceMode.ASPECTJ` với compile-time/load-time weaving nhưng đây là cơ chế khác, có dependency và vận hành phức tạp hơn. Với phần lớn ứng dụng, thiết kế service gọi service rõ ràng đơn giản và ít rủi ro hơn.

## 8. Tác động lên @Transactional và phạm vi transaction

Với Spring transaction ở proxy mode:

```java
@Service
public class BillingService {
    @Transactional
    public void charge(String id) {
        // Thao tác DB cần nằm trong transaction.
    }

    public void chargeFromSameBean(String id) {
        this.charge(id); // Không đi qua proxy transaction.
    }
}
```

Đây là snippet minh họa; cần import `@Service`, `@Transactional`, datasource/transaction manager và môi trường Spring. Nếu bean khác gọi `billingService.charge(id)` qua proxy, Spring transaction advice có cơ hội mở/tham gia transaction theo annotation. Nếu gọi `this.charge(id)` từ target, advice của phương thức `charge` **không được kích hoạt bởi lời gọi đó**.

**Phân biệt tinh tế:** “self-invocation bỏ qua transaction advice” không đồng nghĩa “chắc chắn không có transaction nào cả”. Nếu phương thức ngoài đã được gọi qua proxy và **đang có transaction**, lời gọi nội bộ vẫn có thể thực thi trong transaction sẵn có, nhưng không kích hoạt thêm cấu hình transaction riêng của phương thức trong (ví dụ `REQUIRES_NEW`). Ngược lại, nếu phương thức ngoài không có transaction, self-invocation thường sẽ không tạo transaction mới chỉ vì phương thức trong được annotate.

Với xử lý bất đồng bộ, transaction imperative do Spring quản lý thường gắn với **thread hiện tại**. Khi `@Async` thực sự chuyển việc sang thread khác, transaction của caller không tự đi theo như một context có thể dùng lại. Nếu task async phải thao tác DB trong transaction, đặt ranh giới transaction tại service/method chạy trong worker qua cơ chế Spring quản lý đúng.

**Lưu ý về visibility trên Spring Framework 6.x:** `@Transactional` trên JDK interface proxy thường đòi method `public` và được khai báo trong interface; với class-based proxy, Spring Framework 6.0+ có thể nhận `protected` hoặc package-visible transactional methods theo cấu hình mặc định, miễn đủ điều kiện intercept. Không suy rộng quy tắc này sang mọi loại annotation/interceptor; để dễ tương thích và dễ test, ưu tiên **public method, non-final, lời gọi từ bean khác**.

Spring khuyến nghị thường đặt `@Transactional` trên **concrete class/method**. Đặt annotation trên interface có thể hoạt động với proxy mode ở các phiên bản mới, nhưng AspectJ weaving không thừa kế annotation từ interface theo quy tắc Java; chuyển cơ chế có thể khiến annotation bị bỏ qua.

## 9. Những lỗi cấu hình và dependency injection điển hình

### Lỗi A: inject implementation nhưng thực tế bean là JDK proxy

```java
@Autowired
private ReportServiceImpl reportService; // Có thể không gán được JDK proxy.
```

**Cách sửa:** inject `ReportService` interface hoặc, nếu có nhu cầu hợp lý về kiểu concrete, cấu hình/kiểm tra class-based proxy. Đổi mỗi kiểu khai báo mà không xem bean được tạo ra thế nào dễ dẫn đến lỗi khởi động.

### Lỗi B: ép kiểu JDK proxy về implementation

```java
ReportService service = applicationContext.getBean(ReportService.class);
ReportServiceImpl impl = (ReportServiceImpl) service; // Sai với JDK proxy.
```

Đây là snippet minh họa với `applicationContext` đã có. JDK proxy không extend implementation. **Không** coi `applicationContext.getBean(...)` trả về target nguyên bản; Spring có thể trả proxy đang chứa advice.

### Lỗi C: đổi qua CGLIB nhưng class final

```java
public final class FinalService {
    public void execute() { }
}
```

Lớp `final` không thể được CGLIB subclass. Với Kotlin, classes/methods thường final mặc định; ứng dụng có thể cần plugin `kotlin-spring`/all-open hoặc thiết kế không-final phù hợp. Đừng bỏ `final` bừa bãi khỏi đối tượng chứa invariant quan trọng; xác định cơ chế proxy và ranh giới API trước.

### Lỗi D: phương thức final/private có annotation nhưng tưởng được advice

Một `@Async` hoặc `@Transactional` trên `private`/`final` method không có nghĩa class-based proxy có thể intercept nó. Khi CGLIB không override được, advice không hoạt động như kỳ vọng. **Sửa:** chuyển logic sang public non-final method của Spring bean khác và gọi qua proxy; tránh sửa visibility chỉ để “vượt qua” kiểm tra mà vẫn còn self-invocation.

### Lỗi E: lấy proxy bằng new, hoặc dùng trong @PostConstruct

Tạo `new BillingService()` không chạy qua Spring post-processors và không có transaction interceptor. Tương tự, `@PostConstruct` là giai đoạn khởi tạo bean; không nên dựa vào proxy để tự gọi các phương thức có `@Async`/`@Transactional` trong đó. Hãy tạo một bean khởi động riêng gọi bean cần xử lý sau khi context đã được thiết lập.

### Lỗi F: tưởng hai loại proxy sửa được mọi lời gọi nội bộ

Cả JDK và CGLIB đều bị giới hạn bởi **đường đi của lời gọi** khi dùng Spring AOP proxy. `this.method()` không qua advice. Nếu cố dùng `AopContext.currentProxy()`, phải cấu hình `exposeProxy=true` và chấp nhận coupling vào Spring AOP; đây không phải lựa chọn mặc định được khuyến nghị. Tách bean hoặc gọi qua một component orchestration riêng thường rõ hơn.

### Lỗi G: ép mọi nơi sang CGLIB mà không xét ảnh hưởng toàn ứng dụng

Một setting proxy-target-class ở mức cấu hình có thể ảnh hưởng nhiều bean AOP/transaction/async cùng lúc. Class proxy còn có hạn chế với final, module path, visibility. **Sửa:** cấu hình có mục đích, kiểm thử kiểu proxy và chức năng giao dịch/async sau thay đổi.

### Lỗi H: suy ra hành vi chỉ từ tên lớp proxy

Tên sinh bởi runtime có thể đổi theo Framework, JVM, build hoặc cấu hình. Dùng `AopUtils.isAopProxy`, `AopUtils.isJdkDynamicProxy` và `AopUtils.isCglibProxy` để kiểm tra thay vì viết logic phụ thuộc chuỗi tên class.

## 10. Checklist kiểm tra proxy trong ứng dụng Spring

Khi `@Async` không chạy bất đồng bộ, transaction không rollback như mong đợi hoặc bean injection lỗi:

1. **Bean có do Spring quản lý không?** Kiểm tra đối tượng được lấy từ `ApplicationContext`, không phải object mới tạo bằng `new`.
2. **Annotation infrastructure đã bật chưa?** Ví dụ `@EnableAsync` cho xử lý async, `@EnableTransactionManagement` hoặc auto-configuration phù hợp cho transaction.
3. **Kiểu proxy thực tế là gì?** Dùng ba phương thức `AopUtils.isAopProxy/isJdkDynamicProxy/isCglibProxy`.
4. **Caller đang giữ kiểu nào?** Với JDK proxy, biến nên có kiểu interface được proxy; với class proxy, kiểm tra lớp có thể subclass không.
5. **Phương thức có khả năng được intercept không?** Có nằm trên interface JDK được proxy? Có final/private/unavailable visibility ở class proxy không? Annotation được đặt nơi Spring nhận diện không?
6. **Lời gọi có đi qua proxy?** `beanFromContainer.method()` khác với `this.method()` bên trong target.
7. **Advice của tính năng đã được đăng ký chưa?** Proxy tồn tại không tự chứng minh interceptor cụ thể cho `@Async`/`@Transactional` được áp dụng.
8. **Async executor có đúng không?** Kiểm tra tên executor trong `@Async("...")`, khả năng reject và thread thực thi.
9. **Transaction đang tồn tại ở đâu?** Xác minh method entry/commit/rollback, propagation và thread boundary; không chỉ nhìn annotation.
10. **Có proxy lồng nhau hoặc nhiều advisor không?** Kiểm tra loại bean thực tế và chuỗi interceptor; không giả định thứ tự advice nếu chưa cấu hình/đo.

### Test phân biệt external và self invocation

Tạo hai test cases:

```text
Case 1:
  otherBean -> proxiedService.process()
  mong đợi: advice của process được áp dụng

Case 2:
  otherBean -> proxiedService.wrapper()
  target.wrapper() -> this.process()
  mong đợi: lời gọi nội bộ KHÔNG kích hoạt advice riêng của process
```

Đối với `@Async`, ghi thread name hoặc dùng latch/future để xác nhận worker khác; đừng chỉ dựa vào `Thread.sleep`. Với `@Transactional`, tạo integration test có transaction manager/database thật, cố ý ném exception rồi kiểm tra rollback, vì stdout một mình không chứng minh transaction hoạt động.

## 11. Chọn kiểu nào cho thiết kế service và concurrency?

**Ưu tiên thiết kế API trước, rồi chọn proxy phù hợp:**

- Nếu ứng dụng có **interface nghiệp vụ ổn định**, inject theo interface giúp caller ít phụ thuộc implementation; JDK proxy hoạt động tự nhiên.
- Nếu không có interface và muốn advice public method của class, CGLIB class proxy là lựa chọn phổ biến, miễn class/method có thể subclass/override.
- Nếu ứng dụng dùng Spring Boot, **đừng mặc định rằng Spring Framework thuần và Spring Boot có cùng lựa chọn proxy**; kiểm tra cấu hình Boot, cấu hình annotation và phiên bản.
- Nếu phải dùng `final` ở class hoặc method, cân nhắc interface proxy nếu method được expose qua interface, hoặc refactor kiến trúc. Không mặc định subclass sẽ hoạt động.
- Nếu cần `@Async` để chạy song song, tách orchestration và async worker thành **hai Spring beans khác nhau** giúp lời gọi chắc chắn đi qua proxy và làm rõ lifecycle/thread boundary.
- Nếu cần transaction đúng trong xử lý async, để async service gọi một **transactional service riêng** trên worker thay vì trông cậy transaction của caller tự được chuyển qua executor.
- Nếu bị giới hạn bởi executor pool/DB connections, thay kiểu proxy **không giải quyết được quá tải**. Cần cấu hình thread pool, queue, connection pool, timeout và backpressure ở tầng phù hợp.

### Sơ đồ kiến trúc tham khảo

```text
RestController
      |
      v
JobCoordinator
      |
      | gọi qua Spring-injected interface
      v
AsyncWorker proxy
      |
      | @Async advice: submit vào executor
      v
worker thread
      |
      v
AsyncWorker target
      |
      | gọi qua Spring-injected transactional service
      v
TransactionalService proxy
      |
      | @Transactional advice trên worker thread
      v
TransactionalService target -> DB
```

Mô hình này tách rõ **proxy boundary**, **thread boundary** và **transaction boundary**; ba điều đó không nhất thiết trùng nhau. Các thành phần trên là vai trò kiến trúc, không phải những tên lớp bắt buộc phải có trong mọi dự án.

## 12. Bài tập và tiêu chí tự kiểm tra

1. Chạy ví dụ Maven ở mục 6. Xác minh JDK proxy triển khai interface nhưng không phải subtype của implementation; CGLIB proxy thì là subtype.
2. Thêm một phương thức public `extra()` chỉ có trong `GreeterImpl`. Quan sát: caller typed `Greeter` không thể gọi `extra()`, còn biến `GreeterImpl` nhận từ CGLIB proxy có thể gọi; nếu thêm advice phù hợp, lời gọi ngoài có thể được intercept.
3. Thử thay `GreeterImpl` thành `final class` và dự đoán hành vi class-based proxy. Không coi bài test thành công nếu nó chỉ tạo JDK proxy do bạn đã vô tình tắt `proxyTargetClass`.
4. Thêm `final` cho phương thức `hello()` và tìm hiểu vì sao class-based advice không còn bảo đảm intercept; so sánh với JDK proxy trên interface method.
5. Đo sự khác biệt giữa `cglib.hello("outside")` và `cglib.localCall()`: vì sao chỉ trường hợp đầu có dòng `advice:outside`?
6. Trong một Spring app, tạo method `@Async` và một method gọi `this.asyncMethod()`. Kiểm tra thread đang chạy và refactor sang bean khác để chứng minh external call được advice.
7. Với `@Transactional(propagation = REQUIRES_NEW)`, thử self-invocation và external invocation trong integration test có database; đối chiếu ranh giới transaction thực tế thay vì chỉ nhìn source code.
8. Cấu hình `spring.aop.proxy-target-class=false` trong ứng dụng Spring Boot có AOP auto-configuration và interface service. Đọc `AopUtils.isJdkDynamicProxy(...)` để xác nhận trong topology/cấu hình thực tế; không suy luận từ property nếu còn cấu hình proxy khác.

**Tiêu chí đạt:** phân biệt được proxy/target, mô tả đúng kiểu và phương thức có thể advice, dự đoán được lỗi inject/cast, chỉ ra rõ self-invocation bypass và tự kiểm tra được bằng code/test thay vì dựa trên tên annotation.

## 13. Tóm tắt và tài liệu chính thức

| Câu hỏi | Câu trả lời ngắn |
| --- | --- |
| JDK dynamic proxy được tạo dựa trên gì? | Interface của target |
| CGLIB được tạo dựa trên gì? | Subclass của target class |
| Interface proxy có thể inject theo implementation class? | Không, với JDK proxy thông thường |
| CGLIB có thể proxy final class/final method? | Không |
| CGLIB có thể intercept phương thức ngoài interface? | Có, nếu class/method đủ điều kiện và advisor áp dụng |
| Đổi JDK sang CGLIB có sửa self-invocation? | **Không** |
| Tại sao `@Async` trên self-call không chuyển thread? | Lời gọi không đi qua async proxy interceptor |
| Chọn JDK/CGLIB chỉ bằng `@EnableAsync` hoặc property? | Cần xét phiên bản và cấu hình AOP tổng thể; đo proxy thực tế |
| Cách khắc phục phổ biến cho self-invocation? | Tách service và gọi qua bean được Spring inject |

**Tài liệu tham khảo:**

1. [Spring Framework 6.2 – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, self-invocation, final/private/module constraints.
2. [Spring Framework 6.2 – Creating AOP Proxies with ProxyFactory](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/prog.html): tạo proxy có advice bằng Java code.
3. [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@Async`, executor và proxy mode.
4. [Spring Framework 6.2 – Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): proxy semantics, method visibility, AspectJ và self-invocation.
5. [Spring Framework 6.2 – @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): `proxyTargetClass` và `AdviceMode.PROXY`.
6. [Spring Boot – Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): mặc định CGLIB trong AOP auto-configuration và thuộc tính `spring.aop.proxy-target-class`.

**Ghi nhớ:** JDK proxy dựa trên interface; CGLIB proxy dựa trên subclass. Cả hai cùng giúp Spring đặt interceptor **ở biên lời gọi đi vào proxy**, chứ không tự thay đổi các lời gọi giữa những phương thức của cùng target. Với concurrency, hiểu rõ biên này là điều kiện để `@Async` thực sự chuyển công việc sang executor và `@Transactional` có hiệu lực đúng nơi mong muốn.
