# ScopedProxyMode.INTERFACES và ScopedProxyMode.TARGET_CLASS trong Spring Framework

## Mục tiêu học tập

Khi một bean có vòng đời ngắn (ví dụ `request`, `session` hoặc `prototype`) được dùng bởi một bean có vòng đời dài hơn (thường là `singleton`), Spring có thể chèn **scoped proxy** vào nơi phụ thuộc. Hai tùy chọn `ScopedProxyMode.INTERFACES` và `ScopedProxyMode.TARGET_CLASS` quyết định **kiểu proxy được tạo, những kiểu Java nào proxy có thể được inject vào và những phương thức nào được chuyển tiếp**.

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa **proxy ổn định** và **target thay đổi theo scope**.
2. Chọn đúng `INTERFACES` hoặc `TARGET_CLASS` dựa trên hợp đồng interface, kiểu injection và giới hạn của lớp Java.
3. Phân biệt `DEFAULT`, `NO`, `INTERFACES` và `TARGET_CLASS`; hiểu mặc định của `@Scope` khác mặc định của `@RequestScope`/`@SessionScope`.
4. Tự chạy một ứng dụng Spring Boot MVC minh họa hai loại proxy, kiểm tra nhiều lời gọi trong cùng request và nhiều request khác nhau.
5. Chẩn đoán lỗi inject concrete class khi proxy chỉ có interface, lỗi scope không active và lỗi proxy với `final`/`private`.

## 1. Vấn đề: phụ thuộc có scope ngắn hơn bean đang sử dụng

Spring mặc định tạo bean ở phạm vi `singleton`: một instance cho mỗi bean definition trong một IoC container. Nhưng bean `request` tồn tại cho một HTTP request, `session` cho một HTTP session; bean `prototype` được tạo mới mỗi khi container được yêu cầu cung cấp instance.

Xét phụ thuộc sau (đoạn code giải thích ý tưởng, các lớp sẽ được viết đầy đủ ở mục 4):

~~~java
@Service
class OrderService {
    private final RequestIdentity requestIdentity;

    OrderService(RequestIdentity requestIdentity) {
        this.requestIdentity = requestIdentity;
    }

    String currentIdentity() {
        return requestIdentity.value();
    }
}
~~~

`OrderService` mặc định là singleton, trong khi `RequestIdentity` được định nghĩa là request-scoped. Nếu inject trực tiếp **target** khi singleton được tạo, thời điểm startup thường chưa có request; ngay cả khi tạo target thành công trong một request nào đó thì giữ một target cố định cũng không đáp ứng kỳ vọng “mỗi request một instance”.

**Scoped proxy** thay thế tham chiếu trực tiếp đến target bằng một đối tượng trung gian có thể inject lâu dài:

~~~text
Singleton OrderService
         |
         | giữ reference ổn định
         v
     Scoped proxy
         |
         | mỗi lời gọi cần target
         v
  Scope hiện hành (request/session/...)
         |
         +---- Request #1 ---> RequestIdentity target A
         |
         +---- Request #2 ---> RequestIdentity target B
~~~

Trong request #1, các lời gọi qua proxy cùng trỏ đến target A; trong request #2, proxy tìm target B. Cùng một **đối tượng proxy** có thể được singleton giữ lại, nhưng **đối tượng target** do scope quyết định. Proxy **không tự tạo hoặc duy trì HTTP request**; phải có web-aware context và request/session thực sự active khi truy cập target.

Đây là chức năng của **Core Container, IoC và bean scopes**. Nó dùng cơ chế proxy tương tự Spring AOP, nhưng lý do tạo proxy ở đây là **phân giải bean theo phạm vi**, không phải tự động thêm transaction, cache hay aspect nghiệp vụ.

## 2. Bốn giá trị của enum ScopedProxyMode

Import:

~~~java
import org.springframework.context.annotation.ScopedProxyMode;
~~~

| Giá trị | Ý nghĩa | Có tạo scoped proxy? | Khi nào phù hợp? |
| --- | --- | --- | --- |
| `DEFAULT` | Theo mặc định cấu hình của bước đăng ký bean, thường tương đương `NO` nếu không có cấu hình khác | Tùy cấu hình | Khi muốn kế thừa cấu hình scan; cần kiểm tra giá trị thực |
| `NO` | Không dùng scoped proxy | Không | Lấy bean trong đúng scope bằng `ObjectProvider`, lookup trực tiếp hoặc khi dependency có cùng vòng đời thích hợp |
| `INTERFACES` | Tạo JDK dynamic proxy thực thi các interface mà target công khai triển khai | Có | Người dùng phụ thuộc thông qua interface; ưu tiên hợp đồng trừu tượng |
| `TARGET_CLASS` | Tạo proxy theo lớp, dựa trên CGLIB, bằng một subclass của target type | Có | Phải inject theo concrete class hoặc cần expose phương thức không thuộc interface |

**Không nhầm mặc định:**

- `@Scope("request")` tương đương `@Scope(value = "request", proxyMode = ScopedProxyMode.DEFAULT)` nếu không chỉ định riêng; `DEFAULT` **thường** là `NO`.
- `@RequestScope`, `@SessionScope` và `@ApplicationScope` là các annotation chuyên biệt cho web scope; thuộc tính `proxyMode` mặc định là **`TARGET_CLASS`**.
- `@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)` hoặc `@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)` sẽ ghi đè mặc định đó.
- `@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)` nói rõ cả scope và cơ chế tạo proxy.

Vì vậy, không thể kết luận rằng “Spring mặc định dùng JDK proxy khi class có interface” cho **mọi scoped proxy**: ở đây lựa chọn được chỉ định trực tiếp bởi `ScopedProxyMode`. Các mặc định chọn proxy trong những cơ chế AOP khác là vấn đề riêng.

## 3. So sánh INTERFACES và TARGET_CLASS

### 3.1. INTERFACES — JDK dynamic proxy

Khai báo:

~~~java
public interface UserView {
    String displayName();
}

@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
public class RequestUserView implements UserView {
    @Override
    public String displayName() {
        return "user-from-current-request";
    }
}
~~~

Các đoạn trong mục 3 chỉ minh họa cấu trúc; mục 4 có dự án biên dịch/chạy độc lập với đầy đủ file và import.

JDK dynamic proxy là một object sinh ra ở runtime, **implements các interface** cần thiết thay vì extends `RequestUserView`. Các lời gọi qua interface được đưa đến bộ xử lý proxy; scoped proxy tìm target phù hợp với scope đang active rồi gọi phương thức của target.

Cách inject đúng:

~~~java
@Service
class UserService {
    private final UserView userView;

    UserService(UserView userView) {
        this.userView = userView;
    }

    String read() {
        return userView.displayName();
    }
}
~~~

**Điểm bắt buộc:** collaborator phải phụ thuộc vào `UserView` (hoặc một interface được proxy expose), không phải `RequestUserView`. Proxy JDK thông thường **không phải** instance của implementation class:

~~~java
// Ý nghĩa kiểu Java:
UserView view = /* proxy được Spring inject */;
// view instanceof UserView       -> true
// view instanceof RequestUserView -> false
~~~

Nếu constructor của singleton yêu cầu `RequestUserView` trong khi bean đó đã được expose dưới dạng JDK interface proxy, Spring không thể dùng proxy để thỏa mãn kiểu concrete class. Lỗi thực tế phụ thuộc điểm injection và cấu hình, thường được bọc trong `UnsatisfiedDependencyException` hoặc có nguyên nhân “bean không đúng kiểu”/“không tìm thấy bean phù hợp”.

JDK proxy cần target thực thi **ít nhất một interface thích hợp**. Nó chỉ expose những phương thức khai báo trên các interface được proxy; một phương thức public chỉ tồn tại ở implementation sẽ không được gọi qua kiểu `UserView` nếu interface không khai báo nó.

Một implementation `final` vẫn có thể được JDK proxy bao bọc **thông qua interface**, vì JDK proxy không cần kế thừa implementation. Điều này khác với class-based proxy.

### 3.2. TARGET_CLASS — CGLIB subclass proxy

Khai báo:

~~~java
@Component
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestIdentity {
    public String value() {
        return "request-data";
    }
}
~~~

Spring tạo một subclass proxy tương thích với `RequestIdentity` (thường nhận diện bằng tên runtime chứa dấu hiệu `$$SpringCGLIB$$`). Vì proxy là subclass, injection theo concrete class hoạt động:

~~~java
@Service
class IdentityService {
    private final RequestIdentity identity;

    IdentityService(RequestIdentity identity) {
        this.identity = identity;
    }

    String read() {
        return identity.value();
    }
}
~~~

Lựa chọn này thích hợp khi không có interface hoặc API người dùng cần một phương thức của class không nằm trong interface. Nó **không bắt buộc** bạn tự thêm thư viện CGLIB riêng: phiên bản Spring Framework hiện đại đã đóng gói CGLIB trong `spring-core`.

Các giới hạn từ mô hình subclass:

- **`final class` không thể được subclass**, nên không thể tạo CGLIB proxy từ class final.
- **`final method` không thể bị override/intercept**. Đừng gọi một phương thức final và kỳ vọng nó chuyển tiếp đến scoped target như phương thức public có thể override.
- **`private method` không thể override/intercept**; tương tự với một số phương thức package-private không truy cập được từ subclass.
- Với Java modules, visibility/access của các package có thể hạn chế việc sinh subclass proxy; cân nhắc thiết kế module và quyền truy cập phù hợp.
- Trong Kotlin, class và method mặc định final, cần mở rộng phù hợp hoặc chọn interface proxy.

Không nên “sửa” lỗi bằng cách đổi tất cả lớp thành public/non-final vô điều kiện. Trước hết xem xét có thể định nghĩa interface ổn định và dùng `INTERFACES` hay không.

### 3.3. Bảng quyết định

| Câu hỏi | `INTERFACES` | `TARGET_CLASS` |
| --- | --- | --- |
| Proxy Java là gì? | JDK dynamic proxy | Subclass proxy bằng CGLIB |
| Bean target cần implement interface? | Có | Không |
| Có thể inject vào thuộc tính/constructor kiểu interface? | Có, khi interface được expose | Có, nếu class implement interface đó |
| Có thể inject vào kiểu concrete implementation? | Không | Có, vì proxy kế thừa concrete class |
| Gọi phương thức chỉ có trên concrete class? | Không qua interface proxy | Có khi phương thức đủ điều kiện được intercept |
| Target là final class? | Có thể, nếu interface phù hợp | Không |
| Target có public final method cần proxy? | Có thể proxy lời gọi qua interface | Không intercept được final method |
| Proxy tự làm request/session active? | Không | Không |
| Số target theo request/session khác nhau? | Theo scope, như nhau ở cả hai mode | Theo scope, như nhau ở cả hai mode |
| Có cần dependency CGLIB độc lập? | Không | Không trong Spring hiện đại |

**Nguyên tắc chọn:** Nếu API có interface rõ ràng và tất cả nơi sử dụng đều inject theo interface, `INTERFACES` là lựa chọn tốt. Nếu phải inject implementation class, `TARGET_CLASS` phù hợp hơn, miễn class/method có thể proxy. Cả hai không thay đổi lifetime của target.

## 4. Ví dụ chạy độc lập với Java 17 và Spring Boot MVC

Ví dụ cố ý tạo **hai request-scoped beans** và inject cả hai vào một controller singleton: một bean được proxy bằng interface, một bean bằng concrete class. Có thể chạy bằng JDK 17+ và Maven 3.9+.

Cây thư mục:

~~~text
scoped-proxy-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ScopedProxyApplication.java
    ├── Greeting.java
    ├── RequestGreeting.java
    ├── RequestNumber.java
    └── ProxyController.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>scoped-proxy-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` thiết lập Spring MVC/Servlet web context cho request scope; `spring-context` và `spring-aop` đến từ Spring dependencies. Không cần tự tạo `RequestContextFilter` vì request đến endpoint này được xử lý bởi `DispatcherServlet`.

### 4.2. ScopedProxyApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopedProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedProxyApplication.class, args);
    }
}
~~~

### 4.3. Greeting.java — interface được client nhìn thấy

~~~java
package demo;

public interface Greeting {
    String identity();
}
~~~

### 4.4. RequestGreeting.java — INTERFACES

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
public class RequestGreeting implements Greeting {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    @Override
    public String identity() {
        return "interface=" + id;
    }
}
~~~

Mỗi request có một **target `RequestGreeting`** riêng. Target mới nhận id tăng dần để thấy rõ hai request dùng hai instance khác nhau. Bean được expose cho nơi sử dụng bằng JDK interface proxy; nơi inject cần khai báo kiểu `Greeting`.

### 4.5. RequestNumber.java — TARGET_CLASS

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestNumber {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    public String identity() {
        return "class=" + id;
    }
}
~~~

`RequestNumber` không implement interface. Class proxy được inject trực tiếp qua kiểu `RequestNumber`. Phương thức public `identity()` không final, nên proxy có thể intercept và truy cập target thuộc request hiện hành.

### 4.6. ProxyController.java — singleton nhận hai proxy

~~~java
package demo;

import java.lang.reflect.Proxy;
import org.springframework.aop.support.AopUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProxyController {
    private final Greeting greeting;
    private final RequestNumber number;

    public ProxyController(Greeting greeting, RequestNumber number) {
        this.greeting = greeting;
        this.number = number;
    }

    @GetMapping(value = "/types", produces = MediaType.TEXT_PLAIN_VALUE)
    public String types() {
        boolean jdk = Proxy.isProxyClass(greeting.getClass());
        boolean cglib = AopUtils.isCglibProxy(number);
        return "jdk=" + jdk + ",cglib=" + cglib + "\n";
    }

    @GetMapping(value = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        String i1 = greeting.identity();
        String c1 = number.identity();
        String i2 = greeting.identity();
        String c2 = number.identity();
        return i1 + "\n" + c1 + "\n" + i2 + "\n" + c2 + "\n";
    }
}
~~~

`ProxyController` không khai báo scope riêng nên là singleton. Constructor nhận hai proxy, không yêu cầu tạo trước hai request-scoped targets. Endpoint `/types` kiểm tra **kiểu proxy** mà chưa gọi phương thức nghiệp vụ của target. Endpoint `/probe` gọi mỗi proxy hai lần trong cùng HTTP request.

### 4.7. Lệnh chạy và kết quả

Tại thư mục `scoped-proxy-demo`:

~~~bash
mvn spring-boot:run
~~~

Mở terminal khác, chạy tuần tự:

~~~bash
curl -s http://localhost:8080/types
curl -s http://localhost:8080/probe
curl -s http://localhost:8080/probe
~~~

Kỳ vọng trong ứng dụng vừa khởi động, không có request nào khác tạo target của hai bean:

~~~text
jdk=true,cglib=true
interface=1
class=1
interface=1
class=1
interface=2
class=2
interface=2
class=2
~~~

`/types` cho thấy đối tượng phía `Greeting` là JDK dynamic proxy, còn phía `RequestNumber` là CGLIB proxy. Mỗi response `/probe` có hai dòng cho cùng target loại interface và hai dòng cho cùng target loại class. Ở request kế tiếp, hai target đổi sang instance mới.

**Phạm vi ý nghĩa của output:** Số `1` và `2` giả định không có request khác đến `/probe`; nếu có request song song, bộ đếm có thể khác. Tính chất quan trọng vẫn là **hai lần gọi cùng bean trong một request cho cùng id; request khác nhận target khác**. Các chuỗi output được ghép bằng newline, nên hiển thị trên terminal không bị dính dòng.

### 4.8. Thử thay đổi để hiểu rõ cơ chế

1. Trong `RequestGreeting`, đổi `INTERFACES` thành `TARGET_CLASS`. Endpoint vẫn hoạt động: CGLIB proxy có thể được inject qua interface `Greeting`, vì subclass của `RequestGreeting` cũng implement `Greeting`. Tuy nhiên `/types` sẽ cho `jdk=false,cglib=true`.
2. Trong `RequestNumber`, thử đổi `TARGET_CLASS` thành `INTERFACES` **mà không thêm interface**. Đây là cấu hình không phù hợp: JDK proxy không thể expose API của class không có interface thích hợp; Spring có thể báo lỗi khi tạo proxy/khởi động hoặc không thể đáp ứng điểm injection concrete class. Kết quả cụ thể phụ thuộc cấu hình/runtime, nên đọc nguyên nhân gốc.
3. Giữ `INTERFACES` cho `RequestGreeting`, sau đó đổi constructor `ProxyController(Greeting greeting, ...)` thành constructor đòi `RequestGreeting greeting`. Proxy JDK không phải `RequestGreeting`; kiểu injection không phù hợp, dù target phía sau là instance `RequestGreeting`.
4. Đặt `final` lên `RequestNumber` trong khi giữ `TARGET_CLASS`. CGLIB không thể kế thừa class final; ứng dụng sẽ gặp lỗi tạo proxy. Đổi sang interface-based proxy (sau khi thêm interface) hoặc bỏ ràng buộc class final khi có lý do thiết kế phù hợp.
5. Thay `@RequestScope(proxyMode = ...)` bằng `@Scope(value = "prototype", proxyMode = ...)` trong một thí nghiệm **riêng**: mỗi lần gọi qua scoped proxy có thể resolve **một prototype target mới**, nên không còn quy tắc “một target cho một request”. Điều này đến từ `prototype` scope, không từ proxy mode.

## 5. Vì sao hai proxy có lifetime khác target?

Spring đăng ký một proxy đứng tại tên bean mà client yêu cầu; bean đích được quản lý riêng theo scope (trong triển khai scoped proxy của Spring thường có bean target nội bộ với tiền tố `scopedTarget.`).

Có thể hình dung:

~~~text
Bean được client inject: greeting
  └── scoped proxy (ổn định)
       └── target lookup theo request (nội bộ: scopedTarget.requestGreeting)
             ├── Request A: target instance #1
             └── Request B: target instance #2
~~~

Tên nội bộ là chi tiết hiện thực, dùng để đọc log/diagnostics; code nghiệp vụ không nên gọi trực tiếp các bean `scopedTarget.*`.

**Hai lớp trách nhiệm:**

- **Proxy mode** định nghĩa hình dạng Java của proxy (`INTERFACES` hay `TARGET_CLASS`) và những lời gọi có thể đi qua nó.
- **Bean scope** định nghĩa cách tạo, tái sử dụng và hủy target (`request`/`session`/`prototype`/custom). Đổi proxy mode **không** đổi quy luật scope.

Ví dụ `@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)` hoạt động với HTTP session thay vì request. Client cần duy trì session cookie; các request thuộc cùng session tìm cùng target cho tới khi session kết thúc. Nếu bean session có mutable state, hãy lưu ý nhiều request đồng thời có thể cùng truy cập target; chọn proxy mode không tự đảm bảo thread-safety.

## 6. @Scope, @RequestScope, @SessionScope, @Bean và component scan

### 6.1. Khai báo bằng @Scope

~~~java
@Component
@Scope(value = "request", proxyMode = ScopedProxyMode.INTERFACES)
class ScopedByInterface implements BusinessApi {
    @Override
    public String execute() {
        return "ok";
    }
}
~~~

Ở đây `BusinessApi` là một interface của ứng dụng (cần khai báo riêng). Đây là cách tường minh khi bạn dùng một scope tên `request` và muốn JDK proxy. Nếu dùng `@Scope("request")` không khai báo `proxyMode`, `DEFAULT` thường không tạo scoped proxy.

### 6.2. Khai báo bằng annotation chuyên biệt

~~~java
@Component
@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)
class PerRequestService implements BusinessApi {
    @Override
    public String execute() {
        return "ok";
    }
}

@Component
@SessionScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
class PerSessionState {
    public String current() {
        return "current";
    }
}
~~~

Các snippet ở mục 6 là ví dụ khai báo trong ứng dụng có package/import thích hợp, **không phải một chương trình standalone**. `@RequestScope` và `@SessionScope` vốn đã có `TARGET_CLASS` làm giá trị mặc định cho `proxyMode`; chỉ cần ghi rõ khi chủ động đổi hoặc muốn nhấn mạnh ý đồ.

### 6.3. Bean đăng ký qua @Bean

~~~java
@Configuration
class AppConfig {
    @Bean
    @Scope(value = "request", proxyMode = ScopedProxyMode.INTERFACES)
    BusinessApi businessApi() {
        return new BusinessImpl();
    }
}
~~~

Ở đây `BusinessImpl implements BusinessApi`, không phải một bean component riêng cùng tên. `@Scope` áp dụng được cho method `@Bean`, không chỉ cho `@Component`. Khi dùng interface proxy, khai báo kiểu API return là interface rõ ràng. Nếu dùng class proxy, bảo đảm class thực tế có thể được subclass và Spring có đủ thông tin kiểu bean.

### 6.4. DEFAULT không phải một “kiểu proxy thứ ba”

`DEFAULT` thể hiện kế thừa mặc định trong metadata/configuration. Trong nhiều trường hợp nó trở thành `NO`, nhưng một component scan có thể cấu hình mặc định khác cho scoped proxy. Vì thế khi đọc code cần đối chiếu cấu hình registration, annotation tổng hợp và giá trị `proxyMode` cuối cùng; **không** kết luận chỉ dựa trên literal `DEFAULT`.

`NO` được chọn khi thực sự không muốn proxy. Nếu singleton cần lấy request-scoped target đúng lúc xử lý request, có thể dùng lookup trì hoãn như `ObjectProvider` thay vì giữ target ngay lúc constructor chạy.

## 7. Khi nào nên dùng ObjectProvider thay vì scoped proxy?

Proxy giúp mã sử dụng rất tự nhiên (`service.operation()`) nhưng vẫn là object trung gian với ràng buộc kiểu. `ObjectProvider<T>` là một giải pháp khác: trì hoãn lookup tới thời điểm cần target.

Ví dụ minh họa, `RequestData` là bean `request` được cấu hình với `proxyMode = ScopedProxyMode.NO`:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
class ReportService {
    private final ObjectProvider<RequestData> provider;

    ReportService(ObjectProvider<RequestData> provider) {
        this.provider = provider;
    }

    String render() {
        RequestData data = provider.getObject();
        return data.value();
    }
}
~~~

Không có request active, `provider.getObject()` cũng không thể lấy target của request scope. `ObjectProvider` không thay đổi vòng đời target; nó chỉ đưa việc phân giải ra **thời điểm gọi** thay vì constructor injection. Ưu điểm là có thể phụ thuộc vào concrete type ngay cả khi target không được proxy; nhược điểm là ứng dụng phải gọi `getObject()` chủ động.

Trường hợp `prototype`, `ObjectProvider.getObject()` nhiều lần tạo nhiều target mới. Nếu muốn giữ một prototype instance trong suốt một tác vụ cụ thể, **lấy một lần rồi truyền/giữ trong phạm vi tác vụ đó**; không kỳ vọng proxy tự giữ cố định instance cho cả tác vụ.

## 8. Cơ chế lời gọi và những trường hợp không đi qua proxy

### 8.1. Cần có scope đang active

Khi gọi `greeting.identity()` trong controller của ví dụ, Spring đang xử lý HTTP request, nên scope `request` biết target hiện hành. Nếu chuyển lời gọi ấy sang `@Scheduled`, constructor singleton, callback startup hoặc một thread nền không có request context, proxy **vẫn tồn tại** nhưng việc lấy target có thể ném lỗi kiểu:

~~~text
Scope 'request' is not active for the current thread
~~~

Có thể gặp thông báo lồng nhau về `No thread-bound request found`. Kiểm tra nơi gọi, request binding và thread; đổi `INTERFACES` sang `TARGET_CLASS` **không** chữa nguyên nhân “scope chưa active”.

Nếu một bean dùng scope tùy biến mà scope chưa đăng ký, thông báo lại thiên về “No Scope registered for scope name ...”. Cần phân biệt “scope chưa được đăng ký” với “đã đăng ký nhưng không active”.

### 8.2. Lời gọi trong target và self-invocation

Một lời gọi từ object bên ngoài đến proxy được intercept; còn target có thể gọi `this.otherMethod()` nội bộ mà không thực hiện thêm một lượt phân giải target qua proxy. Điều này quan trọng nhất khi lập luận về lời gọi AOP được advice; với scoped proxy, đối tượng đang thực thi đã là target của scope hiện hành.

Ví dụ khái niệm:

~~~java
public String operation() {
    return this.helper(); // Gọi trực tiếp trên target hiện hành.
}
~~~

Cách gọi này không tự tạo thêm một request-scoped instance. Đừng giải thích mọi lời gọi method trong class là một lần tra scope độc lập.

### 8.3. final/private và class proxy

Đối với CGLIB subclass proxy, lời gọi method cần có khả năng bị intercept. Method `final` không thể override; `private` không thể override từ subclass. Một rủi ro thực tế là những phương thức này có thể thực thi ở trạng thái của **proxy object**, không phải scoped target mong muốn. Đừng dựa vào hành vi đó để truy cập state theo request.

Với JDK dynamic proxy, chỉ những lời gọi qua interface được expose mới được intercept. Một target final class vẫn có thể đáp ứng interface proxy, nhưng nếu method không có trên interface, client không thể gọi method ấy qua reference interface.

### 8.4. Proxy không giải quyết hết vấn đề đồng thời

`request` tách dữ liệu giữa request độc lập; `session` có thể được truy cập đồng thời từ hai request cùng session. Dùng `TARGET_CLASS` hay `INTERFACES` không cung cấp đồng bộ hóa, locking, transaction isolation hoặc session distribution. Với mutable state, áp dụng nguyên tắc thread-safety và session persistence phù hợp hệ thống.

## 9. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Inject bean request-scoped qua implementation class báo thiếu bean/sai kiểu | Cấu hình `INTERFACES` nên Spring expose JDK proxy, không phải subclass implementation | Inject qua interface hoặc đổi sang `TARGET_CLASS` khi class có thể được subclass |
| Proxy class JDK chỉ thấy các method trong interface | Interface chưa khai báo phương thức cần gọi | Bổ sung vào hợp đồng interface hoặc cân nhắc class proxy |
| `No Scope registered for scope name 'request'` | Dùng context không đăng ký web scopes, ví dụ standalone `AnnotationConfigApplicationContext` | Dùng web-aware Spring context, hoặc scope test được đăng ký phù hợp |
| `Scope 'request' is not active for the current thread` | Resolve target ngoài HTTP request đang được Spring expose | Gọi trong request, truyền data sang background task, hoặc thay thiết kế |
| Startup lỗi vì CGLIB không thể subclass | Bean class `final` hoặc có ràng buộc access/module | Chọn `INTERFACES` nếu có interface hoặc thay đổi thiết kế class |
| Gọi public final method không có kết quả scoped-target mong muốn | `TARGET_CLASS` không intercept được final method | Dùng public overridable method hoặc giao diện với `INTERFACES` |
| Singleton khởi tạo thất bại vì bean request chưa active | Dùng `@Scope("request")` mà không tạo proxy, target bị lấy quá sớm | Dùng `@RequestScope` (mặc định TARGET_CLASS), proxy mode rõ ràng hoặc `ObjectProvider` |
| Cùng một bean session bị ghi dữ liệu chồng chéo | Hai HTTP requests đồng thời cùng truy cập session target | Thiết kế dữ liệu bất biến/đồng bộ truy cập; proxy mode không giải quyết |
| Thấy một proxy được inject nên nghĩ chỉ có một target | Nhầm lifetime proxy với lifetime bean thuộc scope | Theo dõi id target qua các request trong ví dụ |
| `@EnableTransactionManagement(proxyTargetClass = true)` nhưng bean scoped proxy vẫn khó inject | Nhầm lựa chọn proxy cho transaction AOP với metadata scoped proxy | Kiểm tra `@Scope(proxyMode = ...)`/`@RequestScope` của bean và kiểu injection thực tế |

Khi chẩn đoán bean đã được proxy, có thể dùng:

~~~java
import org.springframework.aop.support.AopUtils;

boolean jdkProxy = AopUtils.isJdkDynamicProxy(bean);
boolean classProxy = AopUtils.isCglibProxy(bean);
~~~

Đây là snippet dùng trong method đang có biến `bean`, không phải chương trình riêng. `AopUtils` có thể nhận diện nhiều proxy Spring AOP nói chung, **không chứng minh proxy đó nhất thiết là scoped proxy**. Muốn xác nhận mục đích scoped proxy, hãy xem annotation/bean definition và scope của target.

## 10. Các lưu ý thiết kế

- **Thiết kế dựa trên interface:** Cân nhắc `INTERFACES` nếu client cần hợp đồng ổn định và không phải phụ thuộc implementation class. Nó hữu ích khi implementation có method không public trong API hoặc class final.
- **Phụ thuộc kiểu cụ thể:** `TARGET_CLASS` giữ tính tương thích kiểu concrete class, thuận lợi cho code cũ nhưng phụ thuộc khả năng subclass/override.
- **Không chọn chỉ vì hiệu năng:** Chi phí JDK proxy so với CGLIB proxy thường không phải yếu tố quyết định trong nghiệp vụ web; quy tắc scope, loại injection, correctness và khả năng bảo trì quan trọng hơn.
- **Tránh giữ target ngoài scope:** Không đưa request target vào static field, cache toàn cục hoặc một singleton stateful dùng lại; chỉ giữ proxy hoặc giá trị dữ liệu đã trích xuất đúng lifetime.
- **Không truyền nguyên proxy request sang async worker** nếu worker không có request context; truyền một DTO mang thông tin cần thiết.
- **Không trộn khái niệm proxy mode của scoped bean với lựa chọn proxy toàn cục của AOP**: property cấu hình AOP của Spring Boot và annotation `@EnableAspectJAutoProxy` phục vụ các trường hợp khác; luôn đọc metadata scope trên bean đang xét.
- **Định nghĩa bean rõ ràng:** Tránh đăng ký hai bean cùng trách nhiệm vừa qua component scan vừa qua `@Bean` nếu không có chủ ý; lựa chọn proxy mode không giải quyết ambiguity khi nhiều candidates trùng kiểu.

## 11. Checklist lựa chọn và kiểm thử

1. Xác định bean đích thực sự thuộc scope nào (`request`, `session`, `prototype`, v.v.).
2. Xác định người dùng bean sẽ inject theo **interface** hay **concrete class**.
3. Nếu inject theo interface và target implement interface công khai: thử `INTERFACES`.
4. Nếu inject theo concrete class và class/method có thể subclass/override: thử `TARGET_CLASS`.
5. Không suy đoán mặc định: `@Scope` mặc định `DEFAULT` thường là `NO`, trong khi `@RequestScope`/`@SessionScope` mặc định `TARGET_CLASS`.
6. Xác nhận trong thử nghiệm có scope active khi gọi bean; thử cả request đầu tiên lẫn request kế tiếp.
7. Kiểm tra hai lời gọi trong cùng request và hai request khác nhau; kết quả phải tuân theo target scope, không theo proxy mode.
8. Kiểm tra class final, final/private methods, type mismatch và request bị mất khi thực thi trên thread nền.
9. Dùng `Proxy.isProxyClass(...)` hoặc `AopUtils` để xác nhận proxy type khi chẩn đoán; đối chiếu với metadata scope để tránh nhầm loại proxy khác.
10. Dùng `ObjectProvider<T>` nếu cần lookup chủ động hoặc muốn tránh giới hạn kiểu của scoped proxy.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Vì sao một singleton có thể nhận `@RequestScope` bean lúc startup dù chưa có HTTP request?  
**Đáp:** Singleton nhận **proxy**, chưa cần tạo target. Khi code gọi phương thức qua proxy trong request, Spring mới tìm target của request hiện tại.

**Câu 2.** Với `@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)`, một bean `CheckoutImpl implements Checkout` nên được inject bằng `Checkout` hay `CheckoutImpl`?  
**Đáp:** Dùng `Checkout`, vì JDK proxy implements interface mà không extends `CheckoutImpl`.

**Câu 3.** `@RequestScope` không khai báo `proxyMode` tương đương `@Scope("request")` không khai báo `proxyMode` chứ?  
**Đáp:** Không. `@RequestScope` mặc định `TARGET_CLASS`; `@Scope` mặc định `DEFAULT`, thường tương đương `NO` nếu không có default override.

**Câu 4.** Có thể dùng `TARGET_CLASS` cho class final không?  
**Đáp:** Không, vì CGLIB phải tạo subclass. Nếu có interface phù hợp, có thể dùng `INTERFACES`.

**Câu 5.** Chuyển `INTERFACES` sang `TARGET_CLASS` có sửa lỗi “request scope is not active” không?  
**Đáp:** Không. Lỗi phát sinh vì không có request scope active khi resolve target; kiểu proxy không tạo thêm request.

**Câu 6.** Với `@Scope(value = "prototype", proxyMode = TARGET_CLASS)`, tại sao hai lời gọi trên cùng proxy có thể đi đến hai targets?  
**Đáp:** Proxy phân giải target từ scope khi gọi; scope prototype trả instance mới theo lần lookup. Điều này khác request scope, nơi lookup trong cùng request sẽ trả cùng target.

**Câu 7.** Vì sao một phương thức final trên class-based proxy có thể gây lỗi logic dù chương trình biên dịch?  
**Đáp:** CGLIB subclass không override/intercept được final method. Không có bảo đảm lời gọi đó chuyển tiếp đúng tới scoped target; thiết kế API qua method có thể intercept hoặc qua interface.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — [Bean Scopes; Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html).
- Spring Framework Reference — [Using the @Bean Annotation: @Scope and scoped-proxy](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html).
- Spring Framework Reference — [Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- Spring Framework Reference — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html).
- Spring Framework Javadoc — [ScopedProxyMode (6.2)](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/annotation/ScopedProxyMode.html).
- Spring Framework Javadoc — [RequestScope (6.1)](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/web/context/annotation/RequestScope.html).
