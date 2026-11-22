# Giới hạn proxy dựa trên lớp và phương thức có thể chặn trong Spring Framework

## 1. Bối cảnh: dependency khác scope và tại sao Spring cần proxy

Trong Spring IoC Container, bean `singleton` được tạo một lần cho mỗi bean definition trong một container, còn bean `prototype` được tạo mỗi lần Spring thực sự yêu cầu tạo instance. Các web scope như `request` và `session` giữ instance theo request hoặc HTTP session. Khi singleton phụ thuộc trực tiếp vào một bean có vòng đời ngắn hơn, cần xác định **thời điểm** Spring chọn target của dependency.

Xét thiết kế:

```java
@Service
class ReportService {
    private final UserContext userContext;

    ReportService(UserContext userContext) {
        this.userContext = userContext;
    }

    String report() {
        return userContext.currentUser();
    }
}
```

`UserContext` ở đây là bean đại diện dữ liệu từng request; đoạn mã minh họa này không chạy độc lập vì thiếu định nghĩa `UserContext` và import. Nếu inject **target thật** khi tạo `ReportService` singleton, ta gặp lệch vòng đời: lúc khởi tạo singleton có thể chưa có HTTP request, hoặc singleton có nguy cơ giữ trạng thái một request quá lâu. Với **scoped proxy**, singleton nhận một reference ổn định; proxy tìm target tương ứng với scope đang hoạt động vào thời điểm gọi phương thức.

```text
                         Spring IoC Container
                               |
                          ReportService
                          (singleton)
                               |
                               v
                    UserContext scoped proxy
                               |
            +------------------+------------------+
            |                                     |
     HTTP request A                          HTTP request B
       target A                                target B

Singleton giữ PROXY lâu dài;
proxy chọn TARGET theo request khi gọi method có thể chặn.
```

Điều này có hai hệ quả thiết kế:

1. Proxy phải đứng ở **ranh giới lời gọi**: chỉ các lời gọi đi qua proxy và vào những phương thức có thể được proxy chặn mới được chuyển hướng đúng.
2. Loại proxy quyết định bean có thể được biểu diễn dưới dạng class hay interface và các phương thức nào có thể được chặn.

Đối với request/session scope, `@RequestScope` và `@SessionScope` có `proxyMode` mặc định là `ScopedProxyMode.TARGET_CLASS`. Đối với `@Scope("prototype")` thông thường, không mặc định tạo scoped proxy; có thể yêu cầu bằng thuộc tính `proxyMode`. Một prototype có scoped proxy sẽ được tạo target mới **theo từng lần gọi phương thức được proxy chuyển tiếp**, vì mỗi lần resolve prototype là một lần tạo mới. Vì vậy một quy trình cần cùng một target xuyên suốt nhiều method call thường hợp với `ObjectProvider` hơn.

## 2. Proxy dựa trên lớp (class-based proxy / CGLIB) hoạt động như thế nào?

Khi chọn `ScopedProxyMode.TARGET_CLASS`, Spring tạo proxy có thể gán được vào kiểu class của target. Thông thường Spring dùng CGLIB, tạo ra **lớp con tại runtime** (CGLIB được repackaged trong `spring-core`). Proxy ghi đè các instance method có thể override; mã chặn được tạo bởi Spring có thể resolve scoped target trước khi chuyển lời gọi.

```text
class UserContext
      ▲
      | extends
class UserContext$$SpringCGLIB$$...     (proxy, tên class chỉ minh họa)
      |
      +-- public String currentUser()  → intercept → scoped target.currentUser()

class UserContext (scoped target thật)
      |
      +-- logic nghiệp vụ và trạng thái theo request/session
```

Ví dụ annotation tạo class proxy:

```java
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class UserContext {
    public String currentUser() {
        return "user-of-current-request";
    }
}
```

Class trên minh họa syntax, nhưng chỉ chạy đúng trong Spring web-aware context với request thực. Class proxy cho phép injection bằng `UserContext` (concrete type), vì proxy là subtype của `UserContext`.

**Không nhầm lẫn hai vai trò:**

- `Scoped proxy` chủ yếu chọn đúng target theo scope, ví dụ HTTP request.
- `Spring AOP proxy` có thể áp dụng advice như transaction, cache, security, logging vào các method call được hỗ trợ.

Cả hai dùng cơ chế proxy và cùng chịu giới hạn override/interface. Tuy nhiên hành vi nghiệp vụ khác nhau: bỏ qua proxy AOP có thể mất advice; bỏ qua scoped proxy có thể không resolve đúng target trong scope. Cũng không nên nhầm lớp CGLIB hỗ trợ `@Configuration(proxyBeanMethods=true)` (intercept lời gọi đến method `@Bean`) với scoped proxy được nói đến ở đây; chúng có mục đích cấu hình khác nhau.

## 3. Phương thức nào CGLIB có thể chặn?

Điều kiện nền tảng là một lớp con Java có thể **override** method và Spring có thể tiếp cận method qua proxy. Bảng dưới đây giả định Spring dùng class-based proxy, không dùng AspectJ weaving.

| Thành phần Java | CGLIB class proxy chặn được? | Lý do / lưu ý |
| --- | --- | --- |
| `public` instance method, không `final` | **Có**, trường hợp chuẩn | Subclass override và chuyển lời gọi qua interceptor |
| `protected` instance method, không `final` | **Có thể**, nếu method truy cập được | Việc advice cụ thể còn chịu chính sách/matching của từng Spring facility |
| package-private instance method | **Tùy khả năng truy cập** | Method không visible với subclass ở package khác là bất khả override; nên cung cấp public API khi proxy là chủ ý |
| `public final` hoặc `protected final` method | **Không** | `final` cấm override, vì thế không thể chặn qua subclass |
| `private` method | **Không** | Method private không được kế thừa để override |
| `static` method | **Không** theo proxy instance | Gọi tĩnh được bind theo class, không dispatch đến override của proxy |
| Constructor | **Không** | Constructor không phải instance method có thể override |
| Toàn bộ class `final` / Java `record` | **Không tạo được class proxy** cho class đó | Lớp con không thể `extends` class `final` |
| `abstract` instance method | Có thể bị override về mặt Java, nhưng cần target hiện thực cụ thể | Không xem là cách vượt qua yêu cầu về bean instance có thể tạo |
| Method chỉ có trên implementation, không có trong interface | CGLIB **có thể** chặn nếu overridable | JDK interface proxy chỉ cung cấp method qua interface |

Điểm cần cẩn trọng với method không public: từ Spring Framework 6.x, một số tiện ích AOP như transaction có thể hỗ trợ protected/package-private trên class-based proxy; nhưng **khả năng kỹ thuật CGLIB override** và **quy tắc annotation/advisor có áp dụng** là hai bước riêng. Trước khi dựa vào chúng, kiểm tra tài liệu của annotation cụ thể và thử trên phiên bản Spring hiện dùng. Public method qua proxy là lựa chọn rõ ràng nhất.

### 3.1. Lớp final và record

```java
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
@Component
public final class FinalRequestContext {
    public String userId() {
        return "U1";
    }
}
```

Đoạn trên cần import `Scope`, `ScopedProxyMode` và `Component`; nó cố ý minh họa cấu hình **không hợp lệ**. Spring không thể sinh subclass cho `FinalRequestContext` vì class là `final`. Khi cần khởi tạo proxy, ứng dụng có thể gặp lỗi tạo bean, thường kèm `AopConfigException`/lỗi CGLIB trong chuỗi nguyên nhân; không dựa vào text ngoại lệ chính xác vì khác phiên bản và kiểu cấu hình.

`record` trong Java cũng là class `final`, nên không dùng record như một class-based scoped proxy target. Record rất tốt làm immutable value trả về từ service; có thể cho một service thông thường trả về record mỗi request thay vì biến chính record thành scoped bean cần subclass.

Kotlin mặc định tạo class/method `final` nếu không đánh dấu `open`. Khi tích hợp Spring, cần bảo đảm các class/method dùng class proxy có thể được mở rộng; plugin Kotlin Spring/all-open có thể hỗ trợ trong các trường hợp được cấu hình.

### 3.2. final method: proxy có thể được tạo nhưng method không được chuyển tiếp như mong đợi

```java
public class RequestData {
    private final String token = "stored-in-real-target";

    public String ordinaryMethod() {
        return token;
    }

    public final String finalMethod() {
        return token;
    }

    private String helper() {
        return token;
    }

    public String ordinaryCallsPrivate() {
        return helper();
    }
}
```

Nếu một scoped class proxy kế thừa `RequestData`:

- `ordinaryMethod()` có thể được intercept và chuyển đến target tương ứng của scope.
- `finalMethod()` **không thể override**, do đó lời gọi vào proxy không được interceptor scoped target chuyển tiếp theo cách bình thường. Nó có thể chạy method kế thừa ngay trên **đối tượng proxy**, nên trạng thái đọc được có thể không phải trạng thái của target thật. Không được dựa vào việc trả về `token` của method đó.
- `helper()` private không phải điểm có thể chặn độc lập. Nhưng nếu proxy chuyển `ordinaryCallsPrivate()` vào target thật, rồi trên target gọi `helper()`, hàm private vẫn **chạy bình thường trên target**. "Không thể chặn" không có nghĩa "private method bị vô hiệu hóa".

Ví dụ `RequestData` chỉ minh họa mặt kỹ thuật, không phải chương trình chạy Spring đầy đủ; tránh gọi `finalMethod()` trên scoped proxy để suy ra target. Spring thường tạo proxy qua Objenesis để không cần gọi constructor target hai lần, làm việc quan sát field chưa được khởi tạo trên proxy càng không đáng tin. Không dựa vào tình cờ cùng giá trị giữa proxy và target như một hợp đồng.

### 3.3. static, constructor và các vấn đề bổ sung

Class-based proxy không biến Java static dispatch thành dynamic dispatch; lời gọi `ClassName.staticMethod()` vẫn không qua proxy. Constructor của target chạy khi Spring thực sự tạo target theo vòng đời bean; lời gọi constructor không đi qua method interceptor của proxy.

Một vài giới hạn thực tế khác:

- Constructor/package access hoặc các ràng buộc Java visibility có thể khiến Spring không tạo subclass như mong muốn.
- Java Platform Module System (JPMS) có quy định module access và `opens`. Proxy class qua CGLIB có thể không tạo được cho một số kiểu trong module/package đóng; ví dụ cố proxy class từ `java.lang` trên module path sẽ bị giới hạn rất mạnh.
- Bean không public, nested private class hoặc API không thể truy cập có thể làm cấu hình proxy phức tạp, khó kiểm chứng.
- Các method từ `Object` như `equals`, `hashCode`, `toString` có xử lý đặc biệt tùy cơ chế proxy; đừng dùng chúng để suy đoán target scoped hiện hành hoặc identity giữa các request.
- Proxy không tự làm các field mutable thread-safe; kể cả target là session-scoped, nhiều HTTP request cùng session có thể chạy song song.

## 4. Proxy dựa trên interface (JDK dynamic proxy) là lựa chọn thay thế

Nếu interface biểu diễn đầy đủ hành vi bên ngoài, có thể chọn `ScopedProxyMode.INTERFACES`:

```java
public interface CurrentUser {
    String id();
}
```

```java
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
public final class HttpCurrentUser implements CurrentUser {
    @Override
    public String id() {
        return "resolved-for-request";
    }
}
```

Trong ứng dụng thực, service singleton nên nhận `CurrentUser`:

```java
import org.springframework.stereotype.Service;

@Service
public class AuditService {
    private final CurrentUser currentUser;

    public AuditService(CurrentUser currentUser) {
        this.currentUser = currentUser;
    }

    public String currentActor() {
        return currentUser.id();
    }
}
```

Ba source trên cần đặt thành ba file Java tương ứng với tên public type, chung package; chạy trong web-aware Spring MVC context. `HttpCurrentUser` là `final` nhưng **JDK dynamic proxy không cần extends implementation**, vì vậy proxy interface vẫn hợp lệ. Spring tạo proxy có thể gán cho `CurrentUser`. Chọn inject `CurrentUser`, không inject `HttpCurrentUser`:

```java
// Không hợp với proxy INTERFACES:
private final HttpCurrentUser currentUser;

// Hợp với proxy INTERFACES:
private final CurrentUser currentUser;
```

JDK proxy chỉ expose các phương thức thuộc interface mà nó implement. Nếu `HttpCurrentUser` có thêm method `internalDetail()` không khai báo trên `CurrentUser`, consumer giữ proxy `CurrentUser` không gọi trực tiếp được method đó. Java cast từ JDK proxy sang `HttpCurrentUser` cũng không hợp lệ. Với JDK proxy, lời gọi qua interface sẽ chuyển qua invocation handler sang target, kể cả khi implementation method ở class là `final`; điều kiện là method đó thỏa hợp đồng interface và được xử lý qua proxy. Chính vì thế interface giúp tránh giới hạn không subclass được class `final`.

| Tiêu chí | `TARGET_CLASS` (CGLIB) | `INTERFACES` (JDK proxy) |
| --- | --- | --- |
| Proxy tạo kiểu gì? | Subclass của target class | Object implement một hay nhiều interface |
| Điểm inject phù hợp | Concrete class hoặc interface của nó | Interface |
| Target class `final` | Không phù hợp | Có thể dùng, nếu có interface |
| Target method `final` | Không chặn qua override | Lời gọi qua interface vẫn chuyển tới implementation |
| Method riêng chỉ khai báo trong class | Có thể proxy nếu overridable | Không được expose qua proxy interface |
| Khả năng mở rộng API | Phụ thuộc tính kế thừa | Phụ thuộc contract của interface |
| Ưu tiên | Cần inject concrete type và class có thể proxy | Có interface nghiệp vụ ổn định, muốn hỗ trợ implementation final |

Đối với code không thể thêm interface hoặc không muốn dùng proxy, `ObjectProvider<T>`/lookup tại điểm sử dụng là một phương án kiểm soát target rõ ràng.

## 5. Ví dụ Spring Core hoàn chỉnh: proxy subclass và prototype dependency

Ví dụ sau chạy không cần Servlet container hay web server, giúp quan sát chính xác cách một singleton giữ class-based scoped proxy. Ta dùng `prototype` vì Spring Core luôn hỗ trợ scope này. Nguyên tắc giới hạn class/method cũng giải thích vì sao request/session-scoped class proxy phải dùng những method có thể chặn.

Yêu cầu: **JDK 17+, Maven 3.9+**. Ví dụ đặt dependency Spring Framework **6.2.19**. Chương trình giữ proxy ổn định và tạo hai target prototype khác nhau cho hai lần gọi. Khi đang làm việc với Spring Framework 7.x, có thể thay version phù hợp với bộ dependency dự án.

Cấu trúc:

```text
class-proxy-demo/
├── pom.xml
└── src/main/java/edu/example/proxy/
    ├── App.java
    ├── AppConfig.java
    ├── VisitToken.java
    └── Viewer.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>class-proxy-demo</artifactId>
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
                    <mainClass>edu.example.proxy.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/proxy/VisitToken.java**

```java
package edu.example.proxy;

import java.util.concurrent.atomic.AtomicInteger;

public class VisitToken {
    private static final AtomicInteger SEQUENCE = new AtomicInteger();

    private final int number = SEQUENCE.incrementAndGet();

    // Phải có thể override nếu muốn class proxy chuyển lời gọi vào target.
    public int number() {
        return number;
    }
}
```

**src/main/java/edu/example/proxy/Viewer.java**

```java
package edu.example.proxy;

public class Viewer {
    private final VisitToken tokenProxy;

    public Viewer(VisitToken tokenProxy) {
        this.tokenProxy = tokenProxy;
    }

    public int number() {
        return tokenProxy.number();
    }
}
```

**src/main/java/edu/example/proxy/AppConfig.java**

```java
package edu.example.proxy;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    @Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
           proxyMode = ScopedProxyMode.TARGET_CLASS)
    public VisitToken visitToken() {
        return new VisitToken();
    }

    @Bean
    public Viewer viewer(VisitToken visitToken) {
        return new Viewer(visitToken);
    }
}
```

**src/main/java/edu/example/proxy/App.java**

```java
package edu.example.proxy;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            VisitToken firstProxy = context.getBean(VisitToken.class);
            VisitToken secondProxy = context.getBean(VisitToken.class);
            Viewer viewer = context.getBean(Viewer.class);

            int firstTargetNumber = viewer.number();
            int secondTargetNumber = viewer.number();

            System.out.println("same proxy: " + (firstProxy == secondProxy));
            System.out.println("distinct targets: "
                    + (firstTargetNumber != secondTargetNumber));
            System.out.println("positive ids: "
                    + (firstTargetNumber > 0 && secondTargetNumber > 0));
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**stdout của ba câu lệnh `println`:**

```text
same proxy: true
distinct targets: true
positive ids: true
```

Giải thích: Spring đăng ký scoped proxy ở tên bean `visitToken`; target prototype thật nằm sau cơ chế resolve. `getBean(VisitToken.class)` lặp lại trả về cùng proxy singleton do bean definition proxy được quản lý ở scope singleton. `Viewer` cũng singleton và giữ reference ấy; mỗi lần `tokenProxy.number()` được intercept, prototype target mới được tạo, nên số nhận được là hai số khác nhau và dương.

Kết quả chỉ nêu quan hệ giữa các giá trị vì số nguyên tuyệt đối có thể thay đổi nếu một bean khác truy cập target sớm. Đây là **prototype scoped proxy**, không phải phép đo request/session scope; điểm cần quan sát là cơ chế subclass và chuyển lời gọi.

**Thử thay đổi:** Đánh dấu `VisitToken` là `final` hoặc chuyển method `number()` thành `final`. Với class `final`, việc tạo CGLIB class proxy sẽ không thành công. Với method `final`, proxy không thể override để chuyển tiếp lời gọi; nếu phương thức đọc field thì có thể quan sát trạng thái proxy thay vì target và không được dựa vào kết quả. Hai biến thể này là anti-pattern được phân tích, **không** phải phần của mẫu runnable đang đưa ra.

## 6. Tình huống tương đương với request scope

Trong ứng dụng Spring MVC, giả sử context dùng để xử lý request có dạng:

```java
package edu.example.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestTrace {
    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

```java
package edu.example.web;

import org.springframework.stereotype.Service;

@Service
public class TraceService {
    private final RequestTrace trace;

    public TraceService(RequestTrace trace) {
        this.trace = trace;
    }

    public String currentTrace() {
        return trace.id();
    }
}
```

Hai class trên là thành phần Spring MVC, cần web-aware ApplicationContext, annotation scanning và lời gọi chạy trong request; chúng không phải chương trình `main` độc lập. `@RequestScope` mặc định dùng `TARGET_CLASS` và phương thức `id()` là public, không final. Spring inject class-based proxy vào `TraceService` singleton. Trong một request, target `RequestTrace` được tái sử dụng; sang request khác, target khác và có ID khác. Đổi `RequestTrace` thành `final class` sẽ làm proxy class-based không tạo được, còn đổi `id()` thành `final` làm proxy mất khả năng chặn method đó.

Điều này **không** đồng nghĩa mọi lời gọi đến `TraceService.currentTrace()` đều hợp lệ. Khi gọi từ background thread bên ngoài request binding, scoped proxy không tìm được request context; thường phát sinh `ScopeNotActiveException` hoặc nguyên nhân như "No thread-bound request found". Proxy giải quyết chênh lệch lifecycle, nhưng không tự tạo request context hay truyền nó sang executor.

Các annotation `@SessionScope`, `@ApplicationScope` cũng mặc định tạo class-based scoped proxy theo Spring annotation model. Cần cân nhắc khả năng cùng một session bean được nhiều request thread truy cập đồng thời, dù các method đều được proxy đúng.

## 7. Self-invocation: lời gọi nội bộ có đi qua proxy?

Với **Spring AOP proxy** như `@Transactional`, `@Cacheable` hoặc một advice custom, lời gọi `this.anotherMethod()` từ trong target thường **không** quay qua proxy. Xét mã minh họa:

```java
@Service
public class PaymentService {
    public void placeOrder() {
        charge(); // this.charge(): gọi trực tiếp bên trong target
    }

    @Transactional
    public void charge() {
        // Database operations
    }
}
```

Đoạn này cần import `Service` và `Transactional` cùng cấu hình Spring transaction tương ứng; nó không phải project chạy độc lập. Nếu code khác gọi `paymentService.placeOrder()` qua proxy nhưng `placeOrder()` không có advice transaction, lời gọi nội bộ đến `charge()` không tự kích hoạt advice `@Transactional` trên `charge`. Nếu code bên ngoài gọi `paymentService.charge()` **qua proxy**, advice có thể áp dụng theo điều kiện transaction config và method signature.

```text
External caller → proxy → target.placeOrder()
                                  |
                                  +-- this.charge() [bypass proxy AOP]

External caller → proxy → advice → target.charge()
```

**Phân biệt với scoped proxy:** Khi external caller đã gọi một public method qua scoped proxy, proxy chọn scoped target; nếu method trên target gọi helper nội bộ (private, public...), helper vẫn chạy trên **chính target đã chọn**. Self-invocation lúc đó không tự chuyển sang target của scope khác, và thường không cần chuyển scope lần nữa. Nhưng nếu helper cần một advice AOP khác, self-invocation vẫn có thể bỏ qua advice ấy. Đây là lý do không nên khái quát rằng mọi internal call đều làm hỏng scoped bean.

Giải pháp khi cần advice chặn method:

1. Đưa method cần advice sang một Spring bean cộng tác khác và gọi thông qua bean được inject, để lời gọi thực sự đi qua proxy.
2. Nếu đã có interface hợp lý, dùng interface-based proxy với method cần gọi nằm trong interface.
3. Chỉ khi có lý do rõ ràng mới dùng `AopContext.currentProxy()` và bật exposeProxy, vì nó ràng buộc code nghiệp vụ vào cơ chế Spring proxy.
4. Nếu cần chặn **self-invocation/constructor/private method** ở mức bytecode, Spring AOP proxy không đáp ứng; xem xét AspectJ weaving hoặc cấu trúc lại lời gọi phù hợp. Weaving có ràng buộc triển khai riêng.

## 8. ObjectProvider: tránh subclass proxy hoặc điều khiển target theo thao tác

Khi concrete class là final, hoặc một nghiệp vụ cần giữ **cùng một target prototype qua nhiều method call**, có thể inject `ObjectProvider<T>` và yêu cầu target **trong method**, lúc ngữ cảnh scope sẵn sàng:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class GenerateReportService {
    private final ObjectProvider<ReportBuilder> builders;

    public GenerateReportService(ObjectProvider<ReportBuilder> builders) {
        this.builders = builders;
    }

    public String createReport(String title) {
        ReportBuilder builder = builders.getObject();
        builder.title(title);
        builder.addLine("Content");
        return builder.build();
    }
}
```

Đoạn này là minh họa API; `ReportBuilder` cần là bean prototype do ứng dụng khai báo, có các method `title`, `addLine` và `build`. `getObject()` resolve target khi thực sự chạy. Nếu prototype, mỗi lần `createReport` gọi `getObject()` sẽ nhận instance mới rồi **giữ instance đó** qua ba method. Nếu dùng một prototype scoped proxy gọi `title`, `addLine` và `build` riêng lẻ, mỗi lần gọi có thể đi đến target khác, làm mất dữ liệu tích lũy.

Với request-scoped target, `ObjectProvider.getObject()` chỉ thành công khi đang có request scope hoạt động. Nếu gọi từ lúc ứng dụng startup hoặc background task thiếu request context thì vẫn lỗi. Dùng provider không tự kéo dài vòng đời scope và không tự copy request context.

Lựa chọn thực tế:

| Tình huống | Cách làm |
| --- | --- |
| Singleton cần gọi một method của request bean ở mỗi HTTP request, class không final | `@RequestScope` / `@Scope(..., TARGET_CLASS)` và public overridable method |
| Class final nhưng có interface dùng chung ổn định | `ScopedProxyMode.INTERFACES`, inject theo interface |
| Cần target prototype riêng cho **cả một thao tác nhiều bước** | `ObjectProvider<T>.getObject()` một lần trong thao tác |
| Không muốn phụ thuộc web bean | Truyền request data dưới dạng method parameters hoặc DTO immutable |
| Proxy cần chặn private/static/constructor | Thiết kế lại API; proxy Java thông thường không đáp ứng |
| AOP advice cần hiệu lực trên gọi nội bộ | Đưa qua bean collaborator/proxy hoặc dùng weaving trong trường hợp có cơ sở |

## 9. Chẩn đoán lỗi thực tế

| Dấu hiệu | Nguyên nhân khả dĩ | Cách kiểm tra và sửa |
| --- | --- | --- |
| `Cannot subclass final class` / bean creation failure | `TARGET_CLASS` với class final hoặc record | Gỡ final nếu hợp lý, chuyển sang interface proxy hoặc provider |
| Method final đọc state sai, khác target | Proxy subclass không intercept final method | Làm method cần dispatch không final; gọi qua interface proxy; không suy luận từ tình cờ kết quả đúng |
| Method private có `@Transactional` nhưng không tạo transaction | Private method không phải điểm advise qua Spring proxy | Đặt transaction boundary trên public method được gọi qua proxy hoặc tách bean |
| `No thread-bound request found` | Resolve request target ngoài web request | Gọi trong request; truyền dữ liệu cần thiết vào task bất đồng bộ |
| Inject implementation class khi dùng `INTERFACES` bị lỗi type | JDK proxy không là subtype của implementation | Inject interface đã khai báo |
| Prototype injected singleton chỉ tạo một lần | Injection trực tiếp resolve target tại khởi tạo | `ObjectProvider` hoặc prototype scoped proxy khi phù hợp |
| Prototype scoped proxy trả state thiếu giữa nhiều method | Mỗi intercepted method resolve target mới | Lấy một target qua provider và dùng trọn thao tác |
| `@Transactional` trên method gọi nội bộ không có hiệu lực | Self-invocation bỏ qua proxy AOP | Chuyển lời gọi qua bean được proxy |
| Proxy lỗi dưới Java module path | Module/package không mở cho subclass/reflective access | Kiểm tra module exports/opens, dùng interface proxy khi phù hợp |
| Kotlin bean hoạt động khi không proxy nhưng fail khi proxy | Class/method mặc định final | Đảm bảo class/method mở để Spring có thể proxy hoặc dùng interface |

### Debug có hệ thống

- Xác nhận bean definition thực sự có `scope` mong muốn và `proxyMode` phù hợp.
- Xem type tại điểm injection, không mặc định giả định proxy là class thật. Với một bean AOP, `AopUtils.isAopProxy(bean)` và `AopUtils.isCglibProxy(bean)` có thể hữu ích khi debug. Chúng là API Spring, không nên đưa logic phân nhánh dựa trên proxy type vào nghiệp vụ.
- Kiểm tra cách lời gọi được thực hiện: external caller đi qua injected proxy hay đang dùng `new`, `this.`, self-invocation, hoặc method final/private?
- Nếu cần trace thực tế, bật logging phù hợp cho bean creation/AOP tại môi trường thử nghiệm và kiểm tra exception root cause; không dựa vào tên proxy sinh động dạng `$$SpringCGLIB$$...` làm API ổn định.
- Đặt một integration test trong web-aware context và chạy **hai request** để xác nhận target theo scope, đồng thời test những method proxy được gọi.
- Nếu có yêu cầu an toàn luồng, test riêng concurrency/invariant. Proxy không thay thế kiểm thử thread safety.

## 10. Quy tắc thiết kế nên nhớ

1. **Class-based scoped proxy cần class có thể subclass và method có thể override.** Tránh `final` ở class/method cần Spring chặn; `private`, `static` và constructor không thể được intercept bằng subclass proxy.
2. **Public method rõ ràng là điểm mở rộng đáng tin nhất.** Protected/package-private chỉ nên dùng sau khi kiểm chứng visibility và facility cụ thể.
3. **Inject qua interface khi contract ổn định hoặc implementation final.** JDK proxy không expose concrete type; dependency cần khai báo bằng interface.
4. **Phân biệt proxy với target:** bean được inject có thể là proxy sống lâu; mỗi lời gọi hợp lệ mới resolve target phù hợp với `request`, `session` hoặc `prototype`.
5. **Một target prototype cho nhiều bước nên lấy một lần bằng provider.** Scoped proxy của prototype có thể resolve đối tượng khác nhau cho từng method call.
6. **Self-invocation bỏ qua advice của Spring AOP proxy.** Nó không đồng nghĩa helper trên target sẽ không chạy, nhưng có thể làm annotation advice mất tác dụng.
7. **Đừng nhầm lifecycle, interception và concurrency.** Scope/proxy quyết định truy xuất instance; transaction, đồng bộ thread và consistency dữ liệu là các thiết kế riêng.

## 11. Câu hỏi tự kiểm tra

1. Vì sao class `final` không thể được đại diện bằng class-based CGLIB scoped proxy? `record` có gặp giới hạn tương tự không?
2. Một class không final có `public final String id()`. Proxy class-based có thể tạo không? Nó có chặn `id()` để delegate vào request target không?
3. Private helper được gọi từ một public method đã được scoped proxy chuyển vào target: helper có chạy không? Nó có được intercept độc lập không?
4. Nếu một singleton inject bean prototype qua `@Scope(value="prototype", proxyMode=TARGET_CLASS)`, hai method call trên proxy có được cùng một target không?
5. Vì sao interface-based proxy dùng được implementation final nhưng không inject proxy vào field typed bằng implementation?
6. Ngoài Spring AOP proxy, tại sao `this.pay()` gọi từ `placeOrder()` có thể làm `@Transactional` trên `pay()` không được áp dụng?
7. Để giữ một `ReportBuilder` prototype cho `setTitle`, `addLine` và `build` trong cùng thao tác, nên chọn provider hay scoped proxy gọi ba lần?
8. Một request-scoped proxy được gọi trong `@Async` mà thread mới không có request context: class có non-final method thì có tự chạy đúng không?

**Đáp án gợi ý:** (1) CGLIB phải tạo subclass, final class/record cấm kế thừa. (2) Có thể tạo proxy của class nhưng không intercept final method. (3) Helper chạy trên target nếu public method đã delegate; bản thân private method không thể override/intercept. (4) Không bảo đảm cùng target, mỗi intercepted call có thể tạo prototype mới. (5) JDK proxy implement interface chứ không extends implementation. (6) Self-invocation chạy trên target, bỏ qua interception của proxy. (7) Provider, lấy target một lần mỗi thao tác. (8) Không; thiếu scope context khi resolve target sẽ lỗi.

## Tài liệu chính thức

- Spring Framework — Bean Scopes; Scoped Beans as Dependencies; Choosing the Type of Proxy to Create: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Proxying Mechanisms (CGLIB/JDK, final/private, Java modules, self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Declaring a Pointcut (phương thức được proxy chặn): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — `@Scope` và `scoped-proxy`: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework — Classpath Scanning and Managed Components (mặc định proxy của `@RequestScope`/`@SessionScope`): https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
