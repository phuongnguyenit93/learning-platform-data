# Scoped proxy trong Spring Core Container: cơ chế chọn target theo scope

## 1. Vấn đề: bean sống dài cần dùng dependency sống ngắn

Trong Spring IoC container, bean có **scope khác nhau** có thời điểm tạo, thời gian tồn tại và quy tắc tái sử dụng khác nhau. Ví dụ, một `CheckoutService` mặc định là `singleton`, còn `CurrentCart` cần tồn tại theo một HTTP session; hoặc `RequestInfo` chỉ tồn tại trong từng HTTP request.

Khi một bean sống dài (ví dụ singleton) nhận **trực tiếp instance** của bean sống ngắn qua constructor, Spring giải quyết dependency tại lúc dựng singleton. Reference đã inject được giữ nguyên. Đây không phải lúc nào cũng là điều mong muốn: singleton phải xử lý nhiều request/session, trong khi dữ liệu phải đúng với **request/session đang thực thi**.

**Scoped proxy** là một đối tượng trung gian do Spring tạo và inject thay cho target thật. Dependency giữ **cùng proxy** qua nhiều lần dùng; mỗi lần gọi phương thức trên proxy, Spring xác định target đang phù hợp với scope, rồi chuyển lời gọi đến target đó.

~~~text
Singleton service
    │ tham chiếu ổn định
    ▼
Scoped proxy (P)
    │ mỗi lần gọi method: tra cứu target theo scope hiện hành
    ▼
Target thực tế
    ├── request A → target R-A
    ├── request B → target R-B
    ├── session S1 → target S1
    └── prototype → target mới ở mỗi lần method invocation
~~~

Cần phân biệt rõ:

- **Proxy**: đối tượng facade do container cấp cho nơi inject; thường tồn tại như một bean singleton trong context.
- **Target**: đối tượng nghiệp vụ thật mà proxy lấy từ container và gọi phương thức.
- **Scope**: quy tắc Spring dùng để quyết định lần tra cứu này phải lấy lại target đã có hay tạo target mới.
- **Scope context**: ngữ cảnh xác định “đang thuộc request nào, session nào, v.v.”. Với web scopes, context phải đang hoạt động trong luồng thực thi tương ứng.

Scoped proxy **không tự chọn target ngẫu nhiên** và không clone target. Nó giải quyết lại bean qua container, để chính scope cung cấp đúng instance.

## 2. Cơ chế hoạt động khi gọi method

Khai báo một bean có scope phù hợp cùng `proxyMode` khiến Spring đăng ký proxy đại diện cho bean đó. Ở mức triển khai, scoped proxy thường dựa vào `ScopedProxyFactoryBean` và một target source; tên nội bộ của bean target có dạng `scopedTarget.<tên-bean>`. Đây là chi tiết hữu ích để đọc log/BeanFactory, không phải API nghiệp vụ cần tự truy cập.

Quy trình logic:

1. Spring khởi tạo singleton cần dependency và **inject proxy P**, chưa cần buộc target request/session phải tồn tại ngay lúc này.
2. Mã gọi `P.process()` khi đang có một scope context phù hợp.
3. Proxy yêu cầu container lấy target thực qua target source, tương đương tra cứu bean target bằng tên.
4. BeanFactory áp dụng quy tắc scope: tạo instance mới hoặc trả instance đã lưu trong scope.
5. Proxy chuyển lời gọi `process()` đến target được tìm thấy; method chạy trên trạng thái của target ấy.
6. Trong lời gọi kế tiếp, proxy **tra cứu lại**. Đối tượng được chọn có thể giống hoặc khác, tùy scope context và loại scope.

~~~text
service.run()
   │
   ▼
proxy.process()
   │
   ▼
BeanFactory → Scope.get(beanName, objectFactory)
                       │
             ┌─────────┴──────────┐
             │ đã có target hợp lệ?│
             └─────────┬──────────┘
                  có   │   chưa
             ┌─────────┴──────────┐
             ▼                    ▼
        trả target cũ       tạo target mới
             └─────────┬──────────┘
                       ▼
                 target.process()
~~~

Sơ đồ minh họa ý nghĩa của scope, **không phải pseudocode tái hiện nguyên xi mọi nhánh nội bộ** của Spring. Với `prototype`, quy tắc là tạo mới mỗi lần container cần target. Với `request` hoặc `session`, scope thường lưu một target cho cùng request/session và trả lại nó ở những lần gọi sau trong phạm vi đó.

Một lần gọi qua proxy có thể chọn một target; **những lời gọi method tiếp theo trên cùng proxy không mặc nhiên dùng lại target trước**. Để có nhiều method thao tác trên đúng một prototype instance, phải lấy và giữ reference target theo nhu cầu, xem mục 7.

## 3. Spring chọn target theo từng loại scope ra sao?

| Scope của bean target | Khóa/ngữ cảnh tái sử dụng | Hai method call trên cùng scoped proxy | Hệ quả |
| --- | --- | --- | --- |
| `singleton` | Cùng một Spring container | Thường cùng target singleton | Scoped proxy thường không có ích |
| `prototype` | Không cache target theo scope | **Target mới cho từng invocation qua proxy** | State sửa ở call trước có thể không còn ở call sau |
| `request` | HTTP request hiện hành | Cùng target trong cùng request; request khác có target khác | Phù hợp thông tin gắn với một request |
| `session` | HTTP session hiện hành | Cùng target trong một session; session khác có target khác | Phù hợp giỏ hàng/trạng thái phiên theo người dùng |
| `application` | `ServletContext` trong web app | Cùng target trong phạm vi web application | Khác `singleton` nếu có nhiều Spring contexts dùng chung `ServletContext` |
| Custom scope | Khóa/lifetime do implementation của `Scope` quy định | Phụ thuộc logic custom scope | Phải đăng ký scope và quản lý context/lifecycle đúng |

Điểm then chốt là **proxy tự nó không mang ý nghĩa “một target mỗi request” hoặc “một target mỗi method”**: chính **scope của target** quyết định kết quả.

### Đối chiếu qua các lượt gọi

~~~text
1) Target scope = prototype
   Proxy P → call #1 → T1
   Proxy P → call #2 → T2
   Proxy P → call #3 → T3       (T1, T2, T3 khác nhau)

2) Target scope = request
   Request A: P → call #1 → RA
              P → call #2 → RA
   Request B: P → call #1 → RB  (RB khác RA)

3) Target scope = session
   Session S1, request A: P → call #1 → TS1
   Session S1, request B: P → call #2 → TS1
   Session S2, request C: P → call #1 → TS2
~~~

Ví dụ session giả định session S1 vẫn hợp lệ và cùng ứng dụng quản lý scope. Khi session hết hạn hoặc bị invalidate, target thuộc session đó kết thúc vòng đời theo cơ chế quản lý của scope.

### Khi không có scope context phù hợp

Inject một request-scoped proxy vào singleton có thể thành công lúc khởi động ứng dụng. Nhưng khi gọi method qua proxy **ngoài một HTTP request đang được ràng buộc** (ví dụ từ `main`, background scheduler, thread tự tạo), Spring không thể tìm target request hợp lệ; thường phát sinh `ScopeNotActiveException` hoặc một ngoại lệ scope nền tương ứng. Scoped proxy chỉ **trì hoãn tra cứu target**, không tự tạo HTTP request giả.

Trong Spring MVC, `DispatcherServlet` giúp thiết lập request context khi xử lý request. Trong môi trường servlet khác, `RequestContextFilter` hoặc `RequestContextListener` có thể hỗ trợ bind request. Không mặc định coi request context sẽ tự truyền sang `@Async`, executor thread hay CompletableFuture chạy ở thread khác.

## 4. Khai báo scoped proxy bằng annotation

Annotation `@Scope` có thuộc tính `proxyMode` với ba lựa chọn cần nhớ:

- `ScopedProxyMode.NO`: không tạo scoped proxy; inject bình thường theo thời điểm dependency được resolve.
- `ScopedProxyMode.TARGET_CLASS`: tạo proxy dựa trên lớp target (CGLIB/subclass). Nơi inject có thể phụ thuộc concrete type nếu lớp/method cho phép proxy.
- `ScopedProxyMode.INTERFACES`: tạo JDK dynamic proxy dựa trên interface. Nơi inject phải dùng kiểu interface mà proxy triển khai.

Đặt scope và proxy mode trên bean definition, chẳng hạn:

~~~java
@Component
@Scope(value = "prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class ReportPart {
    public void render() {
        // ...
    }
}
~~~

Hoặc trên Java configuration:

~~~java
@Bean
@Scope(value = "prototype", proxyMode = ScopedProxyMode.INTERFACES)
public ReportPartApi reportPart() {
    return new ReportPartImpl();
}
~~~

Hai đoạn trên là **mẫu cấu hình độc lập**, giả định lớp/interface có thật, import annotation Spring thích hợp và component scan hoặc config được đăng ký trong context.

Với web scopes, Spring có annotation tiện dụng:

~~~java
@Component
@RequestScope
public class CurrentRequestData {
    public String requestId() {
        return "...";
    }
}

@Component
@SessionScope
public class ShoppingCart {
    // State trong một HTTP session
}
~~~

`@RequestScope` và `@SessionScope` mặc định sử dụng `ScopedProxyMode.TARGET_CLASS`. Có thể viết `@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)` nếu bean implements interface và nơi inject dùng interface đó.

Các đoạn dùng `request`/`session` chỉ có ý nghĩa trong **web-aware ApplicationContext** đang quản lý những scope này. Với plain `AnnotationConfigApplicationContext` không đăng ký request/session scope, cấu hình sẽ không tự biến thành web application.

### Interface proxy và class proxy

| Kiểu | Cơ chế | Cần chú ý |
| --- | --- | --- |
| `INTERFACES` | JDK proxy implements interface | Injection type phải là interface; không thể ép proxy thành concrete implementation |
| `TARGET_CLASS` | CGLIB subclass của class target | Không proxy được class `final`; method `final` hoặc `private` không thể được override/intercept |

Nếu chọn `INTERFACES` nhưng service khai báo constructor `CheckoutService(ShoppingCartImpl cart)`, injection theo implementation có thể thất bại vì proxy chỉ implements `ShoppingCart` interface. Đổi constructor thành `CheckoutService(ShoppingCart cart)` hoặc cân nhắc target-class proxy khi thật sự cần concrete type.

Nếu class target là `final` (đặc biệt gặp ở record), target-class scoped proxy không thể kế thừa class đó. Ưu tiên interface hoặc đổi thiết kế, thay vì cố gắn proxy vào class không proxy được.

Cần bảo đảm các **phương thức nghiệp vụ đi qua proxy** là những method có thể được proxy intercept. Không dựa vào `private` hoặc `final` methods để kích hoạt tra cứu target mới theo scope.

## 5. Ví dụ Java 17 chạy được: prototype proxy được giữ trong singleton

Ví dụ sau cho thấy **reference đến proxy không đổi**, nhưng target của từng lời gọi method trên proxy prototype là object mới. Dùng Spring Framework 6.2.19 và Java 17+. Không cần Spring Boot, web server hay HTTP request.

Cây tệp:

~~~text
scoped-proxy-demo/
├── pom.xml
└── src/main/java/example/ScopedProxyDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>scoped-proxy-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/example/ScopedProxyDemo.java`:

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;

public final class ScopedProxyDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JobService service = context.getBean(JobService.class);
            WorkState proxy = service.state();

            System.out.println("Singleton giữ cùng proxy: "
                    + (proxy == service.state()));
            System.out.println("getBean trả cùng proxy: "
                    + (proxy == context.getBean(WorkState.class)));

            int firstId = proxy.instanceId();
            int secondId = proxy.instanceId();
            System.out.println("Hai lời gọi chọn target khác nhau: "
                    + (firstId != secondId));

            proxy.increment();
            System.out.println("Đọc ở lời gọi kế tiếp thấy: " + proxy.value());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        @Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
               proxyMode = ScopedProxyMode.TARGET_CLASS)
        public WorkState workState() {
            return new WorkState();
        }

        @Bean
        public JobService jobService(WorkState workState) {
            return new JobService(workState);
        }
    }

    // Không đặt final: Spring cần tạo subclass làm scoped proxy.
    public static class WorkState {
        private static final AtomicInteger NEXT = new AtomicInteger();
        private final int instanceId = NEXT.incrementAndGet();
        private int value;

        public int instanceId() {
            return instanceId;
        }

        public void increment() {
            value++;
        }

        public int value() {
            return value;
        }
    }

    public static final class JobService {
        private final WorkState state;

        public JobService(WorkState state) {
            this.state = state;
        }

        public WorkState state() {
            return state;
        }
    }
}
~~~

Chạy ở thư mục `scoped-proxy-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ScopedProxyDemo
~~~

Stdout dự kiến của chương trình (không tính log/chẩn đoán của Maven nếu môi trường in thêm):

~~~text
Singleton giữ cùng proxy: true
getBean trả cùng proxy: true
Hai lời gọi chọn target khác nhau: true
Đọc ở lời gọi kế tiếp thấy: 0
~~~

Vì sao dòng cuối là `0`, không phải `1`? `proxy.increment()` tăng biến `value` trên target prototype của **lời gọi thứ nhất**. `proxy.value()` là một **lời gọi qua proxy khác**, Spring chọn một target prototype mới có `value=0`. Đây là hành vi đúng theo cấu hình, nhưng thường không phù hợp khi muốn duy trì state của một job qua nhiều method call.

`context.getBean(WorkState.class)` trong cấu hình này trả về **proxy của bean `workState`**, không bắt buộc là một target mới cho bên gọi. Nếu lấy bean từ container rồi giữ proxy trong biến cục bộ, mỗi lần gọi method trên biến ấy vẫn tra cứu lại target theo scope.

**Lưu ý về dependency**: `spring-context` trong Maven kéo theo các module Spring cần thiết, bao gồm cơ chế proxy trong Spring AOP. Mã demo là chương trình Java đầy đủ; những ví dụ ngắn khác trong README chỉ minh họa API/cấu hình và có thể cần các import hoặc dependency của ứng dụng thực.

## 6. Scoped proxy với request và session trong ứng dụng web

Một ví dụ thiết kế:

~~~java
public interface CartView {
    int itemCount();
}

// Các class dưới đây là minh họa trong ứng dụng web có component scanning.
@Component
@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)
public class SessionCart implements CartView {
    private int count;

    @Override
    public int itemCount() {
        return count;
    }

    public void addOne() {
        count++;
    }
}

@Service
public class CartSummaryService {
    private final CartView cart;

    public CartSummaryService(CartView cart) {
        this.cart = cart;  // Proxy stable, target được chọn theo session.
    }

    public int currentCount() {
        return cart.itemCount();
    }
}
~~~

Đây là mã minh họa chia thành các type/file phù hợp, không phải một file Java độc lập vì có nhiều `public` type và thiếu các import Spring. Khi người dùng thuộc cùng một HTTP session truy cập hai request liên tiếp, `currentCount()` được proxy chuyển tới target `SessionCart` của session đó. Với hai session khác nhau, hai target khác nhau. `CartSummaryService` vẫn có thể là singleton.

Lưu ý ở ví dụ interface proxy: `CartView` chỉ khai báo `itemCount()`, nên nơi nhận proxy dưới type `CartView` không thể gọi `addOne()` trực tiếp. Nếu cần thao tác thêm hàng, hãy thiết kế cả hành vi đó vào interface hoặc điều chỉnh interface/class proxy phù hợp.

Với request scope:

~~~java
@Component
@RequestScope
public class RequestAudit {
    private final String marker = java.util.UUID.randomUUID().toString();

    public String marker() {
        return marker;
    }
}

@Service
public class AuditService {
    private final RequestAudit audit;

    public AuditService(RequestAudit audit) {
        this.audit = audit;
    }

    public String auditMarker() {
        return audit.marker();
    }
}
~~~

`AuditService` giữ request-scoped proxy. Trong cùng request, hai lần gọi `auditMarker()` nhận cùng `marker` vì scope dùng cùng target. Sang request khác, một target `RequestAudit` khác được tạo với marker khác. Không dùng UUID để lập luận danh tính chắc chắn ở mức toán học; tiêu chí chính xác của scope là **reference identity** của target.

Cả hai ví dụ yêu cầu ứng dụng Spring Web MVC hoặc web-aware container thích hợp; chúng minh họa dependency/scoped proxy, không bao gồm `@Controller` hay cấu hình khởi động web server.

## 7. Chọn scoped proxy hay `ObjectProvider`?

**Scoped proxy** phù hợp khi collaborator muốn gọi một dependency như object bình thường, và một lần gọi method cần tìm target đúng của request/session đang hoạt động. Mã client giữ reference proxy ổn định, không phải tự viết lệnh lookup. Điều này đặc biệt tiện với `request`, `session` hoặc custom scope có caching theo context.

**`ObjectProvider<T>`** phù hợp khi mã nghiệp vụ cần **chủ động quyết định thời điểm lấy bean**, nhất là lúc muốn dùng **cùng một prototype target cho cả một quy trình nhiều bước**.

Ví dụ prototype có state không dùng proxy:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class Draft {
    private int lines;

    public void addLine() {
        lines++;
    }

    public int lineCount() {
        return lines;
    }
}

@Service
public class DraftService {
    private final ObjectProvider<Draft> drafts;

    public DraftService(ObjectProvider<Draft> drafts) {
        this.drafts = drafts;
    }

    public int createTwoLineDraft() {
        Draft draft = drafts.getObject(); // Một target prototype thực.
        draft.addLine();
        draft.addLine();
        return draft.lineCount();         // Kết quả: 2.
    }
}
~~~

Đây là các lớp minh họa cho ứng dụng có component scanning, không phải chương trình standalone. Với prototype **không cấu hình scoped proxy** như ví dụ này, mỗi `drafts.getObject()` lấy một target độc lập và bạn giữ nguyên reference `draft` qua các lời gọi.

**Bẫy kết hợp:** nếu `Draft` được cấu hình **scoped proxy**, thì `ObjectProvider<Draft>.getObject()` thường cũng giải quyết **bean proxy** theo tên/type được đăng ký. Bản thân việc gọi provider một lần không đảm bảo “giữ nguyên target prototype” khi sau đó gọi nhiều method trên proxy! Để giữ một target prototype cho cả thao tác, tổ chức một bean prototype **không proxy** để provider lấy trực tiếp; hoặc sử dụng factory API thiết kế riêng cho việc tạo draft.

Bảng lựa chọn:

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Singleton đọc thông tin của **request hiện hành** | `@RequestScope` + scoped proxy | Tự chọn target cho request hiện hành ở từng method call |
| Singleton dùng trạng thái **session hiện hành** | `@SessionScope` + scoped proxy | Cùng target được tái sử dụng qua các request cùng session |
| Mỗi job cần một object mutable; nhiều lời gọi dùng chung object ấy | Unproxied prototype + `ObjectProvider.getObject()` một lần/job | Giữ reference target nhất quán suốt job |
| Đúng một dependency lúc dựng collaborator; không cần đổi theo ngữ cảnh | Inject trực tiếp | Đơn giản, đủ khi lifetime tương thích |
| Mã phải kiểm soát lookup, optional dependency | `ObjectProvider` hoặc `ObjectFactory` | Tường minh thời điểm container tạo/trả bean |

Các phương án khác gồm `jakarta.inject.Provider<T>` hoặc `@Lookup` (lookup-method injection); chúng vẫn dựa vào scope khi thực sự resolve bean. Không phải mọi vấn đề trạng thái đều cần scoped proxy: nếu đối tượng chỉ là dữ liệu Java thuần và không cần DI/lifecycle, tạo object thường có thể đơn giản hơn.

## 8. Những tình huống tinh tế dễ hiểu sai

### 8.1. Self-invocation bên trong target

Giả sử target có `outer()` và `inner()`:

~~~java
public void outer() {
    inner(); // this.inner(): cùng target đang chạy outer().
}
~~~

Sau khi gọi `proxy.outer()`, container đã chọn target cho lần invocation này. Lời gọi `this.inner()` xảy ra **bên trong target**, không quay lại proxy để chọn target khác. Ngược lại, gọi `proxy.outer()` rồi `proxy.inner()` từ bên ngoài là **hai lần đi qua proxy**; với prototype scope, thường nhận hai target khác nhau.

Điều này cùng nguyên lý “self-invocation bỏ qua proxy” của Spring AOP, nhưng ở đây đang xét hậu quả đối với **việc lựa chọn target theo scope**.

### 8.2. Inject proxy và lưu target là hai việc khác nhau

Nếu singleton lưu proxy trong field, mỗi method call thông qua field có thể chọn target phù hợp với context hiện tại. Nếu singleton bằng cách khác tự lấy **target thật** rồi lưu lâu dài vào field, target ấy có thể bị sử dụng ngoài lifetime mong muốn; request/session state có nguy cơ bị giữ hoặc dùng nhầm giữa người dùng.

Đừng suy luận target identity từ `proxy == proxy`, `System.identityHashCode(proxy)` hay `proxy.getClass()`. Những biểu thức đó quan sát **proxy**, không chứng minh target bên dưới giống nhau.

### 8.3. Constructor, init và destroy của target

Tạo proxy lúc dựng context không đồng nghĩa đã tạo target request/session. Target thường được tạo khi scope được truy vấn và chưa có instance phù hợp. Khi target được tạo, Spring vẫn thực hiện wiring, bean post-processing và callback khởi tạo như các bean Spring khác.

- `request`/`session`: vòng đời target và destroy callback gắn với lúc scope kết thúc theo cơ chế container/web framework, trong điều kiện scope đã đăng ký hủy phù hợp.
- `prototype`: Spring khởi tạo và giao instance nhưng **không tự động gọi destroy callback cho từng prototype target** sau khi dùng xong. Nếu giữ tài nguyên cần đóng, thiết kế ownership/cleanup tường minh.
- Proxy không thể tự biến mọi target thành singleton hoặc tự kéo dài lifetime của request/session.

### 8.4. Thread, async và request context

Không giả định “cùng user” có nghĩa request context hiện hành ở mọi thread. Với `@Async`, `ExecutorService`, scheduled task hoặc message listener, thường không có HTTP request được bind vào thread; scoped proxy request có thể không resolve được target. Nếu nghiệp vụ cần request data trong tác vụ async, nên **trích xuất dữ liệu cần thiết** thành giá trị độc lập và truyền vào task, hoặc dùng cơ chế propagate context được cấu hình và kiểm chứng rõ ràng. Không lưu đại trà toàn bộ request/session proxy vào tác vụ kéo dài ngoài web request.

### 8.5. Hệ quả hiệu năng và tính đúng

Mỗi method call đi qua scoped proxy phát sinh bước chọn target; với prototype có thể phát sinh tạo instance thường xuyên. Mô hình “increment ở method A, read ở method B” sai khi hai method chạy trên hai prototype target. Với request/session scope, các lời gọi trong cùng context thường dùng lại target nên mô hình stateful có thể phù hợp hơn.

Lựa chọn scope theo **đơn vị trạng thái cần nhất quán**: request, session, job, hay toàn context; không chọn chỉ vì mong muốn code constructor injection ngắn hơn.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Singleton luôn thấy state của request đầu tiên | Inject target sống ngắn trực tiếp, hoặc tự cache target | Inject request-scoped proxy, tránh lưu target ngoài scope |
| Gọi method ngoài HTTP request báo scope không active | Không có request-bound context | Gọi trong lifecycle request hoặc truyền dữ liệu cần thiết sang xử lý nền |
| Prototype proxy “mất state” giữa hai method | Mỗi invocation chọn target prototype mới | Dùng unproxied prototype + provider một lần mỗi job |
| Bean theo interface báo thiếu implementation khi inject concrete type | Chọn `INTERFACES` (JDK proxy) nhưng injection đòi class | Inject theo interface hoặc chọn `TARGET_CLASS` nếu khả thi |
| Class `final`/method `final` không proxy đúng | CGLIB cần subclass/override | Dùng interface proxy, bỏ `final` khi phù hợp, hoặc đổi thiết kế |
| Gọi `new MyBean()` không thấy scope/proxy/AOP | Object được tạo ngoài Spring container | Lấy bean từ Spring hoặc DI theo đúng bean definition |
| Test call request proxy trên plain context thất bại | Chưa đăng ký web scope/context | Dùng web test context/MockMvc hoặc thiết lập mock scope hợp lệ |
| Log cho thấy proxy giống nhau nhưng user data khác | So sánh proxy thay vì target | Kiểm tra identity/state bên trong method target theo từng context |
| Prototype giữ resource không được dọn | Prototype không được Spring tự destroy theo mặc định | Đóng resource theo ownership, không trông chờ context close |

## 10. Checklist thiết kế và tự kiểm tra

Trước khi cấu hình scoped proxy, xác định: **bean nào cần state theo scope**, **bean nào giữ reference lâu hơn**, **mỗi lời gọi method có cần cùng target với lần trước không**, **web/custom scope context đang active ở đâu**, và **bạn đang inject proxy qua interface hay class**.

Một checklist thực hành ngắn:

1. Bean target được khai báo scope đúng (`prototype`/`request`/`session`/custom scope) và thực sự được Spring đăng ký.
2. Đã bật proxy qua `@Scope(proxyMode = ...)` hoặc annotation web phù hợp.
3. Kiểu injection khớp với JDK interface proxy hay CGLIB target-class proxy.
4. Method sử dụng đi qua proxy, không dựa vào `private`/`final` method hoặc self-invocation để chọn target mới.
5. Đã kiểm chứng **cùng request/session dùng cùng target**, và **scope khác nhau dùng target khác nhau**.
6. Nếu dùng prototype stateful, đã chọn cơ chế giữ một target cho **trọn thao tác** khi cần.
7. Đã có chiến lược xử lý thiếu active scope, request context qua async và cleanup tài nguyên.

### Câu hỏi tự kiểm tra

**Câu 1.** Singleton giữ một request-scoped proxy `P`. Trong request A, nó gọi `P.read()` hai lần, sau đó request B gọi một lần. Có bao nhiêu target request tối thiểu cần tạo?

**Đáp án:** Hai target (một cho A, một cho B), giả sử cả hai request đều lần đầu truy cập bean đó và context hoạt động hợp lệ. Hai method call trong request A dùng lại target A.

**Câu 2.** Singleton giữ prototype-scoped proxy `P`. Gọi `P.addItem()` rồi `P.total()`. `total()` nhất thiết thấy item vừa thêm không?

**Đáp án:** Không. Hai lời gọi qua proxy thường chọn hai prototype target khác nhau. Cần một target giữ xuyên suốt thao tác nếu nghiệp vụ yêu cầu state liên tục.

**Câu 3.** Cùng một session có hai HTTP request khác nhau. Session-scoped proxy chọn hai target khác nhau hay giống nhau?

**Đáp án:** Cùng target trong session còn hoạt động, nếu cùng web application/scope và không bị invalidate hay thay đổi scope state.

**Câu 4.** Có thể inject request-scoped proxy vào singleton khi khởi động web app trước request đầu tiên không?

**Đáp án:** Có. Proxy có thể được dựng và inject trước; target request thực chỉ cần được resolve khi có request context. Gọi method ngoài request thì không có target phù hợp và có thể báo lỗi scope.

**Câu 5.** Nếu `@Scope(proxyMode = INTERFACES)` tạo JDK proxy, có thể inject nó như lớp triển khai cụ thể không?

**Đáp án:** Không nên. Proxy JDK triển khai interface, không phải instance của class implementation. Constructor/field cần dùng interface mà proxy hỗ trợ.

## 11. Tài liệu tham khảo

- [Spring Framework Reference — Bean Scopes và Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework Javadoc — Scope](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Scope.html)
- [Spring Framework Javadoc — ScopedProxyMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ScopedProxyMode.html)
