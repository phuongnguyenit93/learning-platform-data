# Khai báo `@Scope` và các annotation phạm vi web trong Spring Framework

## 1. Mục tiêu và bối cảnh

Trong Spring Core Container, **scope (phạm vi bean)** quyết định một bean definition sẽ tương ứng với bao nhiêu đối tượng thực tế, đối tượng được lấy từ đâu và tồn tại trong ngữ cảnh nào. Cùng một class có thể được khai báo với các scope khác nhau để đáp ứng các yêu cầu quản lý trạng thái khác nhau.

Sau bài này, bạn có thể:

- Khai báo scope bằng `@Scope` trên class `@Component` hoặc trên phương thức `@Bean`.
- Phân biệt chính xác `singleton`, `prototype`, `request`, `session`, `application` và `websocket`.
- Sử dụng các annotation chuyên biệt `@RequestScope`, `@SessionScope`, `@ApplicationScope`.
- Giải thích vì sao singleton cần **scoped proxy** hoặc `ObjectProvider` khi dùng một bean có vòng đời ngắn.
- Nhận biết lỗi truy cập scope ngoài ngữ cảnh HTTP, vấn đề chia sẻ trạng thái và giới hạn của proxy.

Phạm vi trình bày tập trung vào cơ chế Spring Framework IoC và các web scope trong ứng dụng **Servlet/Spring MVC**. Ví dụ chạy bằng Java 17 và Spring Boot 3.3.x (Spring Framework 6.1.x).

## 2. Scope thực sự kiểm soát điều gì?

Spring lưu một **bean definition** mô tả cách tạo bean. Scope quy định cách container cung cấp instance cho từng lần truy xuất definition đó. Scope **không** sửa access modifier của Java, không làm một đối tượng trở thành thread-safe và không tự đồng bộ dữ liệu giữa các JVM.

| Scope | Số lượng/vùng dùng chung | Kết thúc vòng đời | Có sẵn ở đâu? |
| --- | --- | --- | --- |
| `singleton` | Một instance trên **một bean definition trong một Spring IoC container** | Khi container đóng | Mọi Spring context |
| `prototype` | Instance mới khi container được yêu cầu tạo/lấy bean | Spring không tự gọi destruction callback của prototype sau khi giao bean cho phía dùng | Mọi Spring context |
| `request` | Một instance cho mỗi HTTP request, mỗi bean definition | Cuối request | Web-aware `ApplicationContext` |
| `session` | Một instance cho mỗi HTTP `HttpSession`, mỗi bean definition | Khi session bị hủy/timeout | Web-aware `ApplicationContext` |
| `application` | Một instance theo `ServletContext` của web application | Khi web application kết thúc | Web-aware `ApplicationContext` |
| `websocket` | Một instance cho mỗi WebSocket session trong ứng dụng STOMP messaging | Khi WebSocket session kết thúc | Ngữ cảnh web có hỗ trợ STOMP/WebSocket scope |

**Hai điểm dễ nhầm:**

1. `singleton` của Spring là một instance **trong phạm vi container**, không nhất thiết là singleton toàn JVM và cũng không đồng nghĩa với mẫu thiết kế singleton Java.
2. `application` gắn với **`ServletContext`**. Nó có thể được chia sẻ giữa nhiều Spring `ApplicationContext` sử dụng cùng `ServletContext`, khác với `singleton` theo từng context. Nó không chia sẻ dữ liệu giữa các instance của ứng dụng đang chạy trên nhiều máy.

Web scope chỉ hoạt động khi scope tương ứng đã được đăng ký và ngữ cảnh hiện tại đang hoạt động. Ví dụ, tải `@RequestScope` trong một `AnnotationConfigApplicationContext` thuần Java có thể gây lỗi không tìm thấy scope; truy cập bean request ngoài HTTP request thường dẫn đến `ScopeNotActiveException`.

## 3. Cú pháp `@Scope`

`@Scope` nằm trong package `org.springframework.context.annotation`. Annotation áp dụng cho **kiểu bean được Spring quản lý** hoặc **factory method `@Bean`**.

### 3.1. Đặt trên `@Component`

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ImportJobState {
    // Mỗi lần container yêu cầu bean prototype sẽ tạo một instance mới.
}
~~~

`ConfigurableBeanFactory.SCOPE_PROTOTYPE` tương đương chuỗi `"prototype"`. Với singleton có thể dùng `ConfigurableBeanFactory.SCOPE_SINGLETON` hoặc bỏ `@Scope` vì đó là mặc định.

### 3.2. Đặt trên phương thức `@Bean`

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

@Configuration(proxyBeanMethods = false)
public class JobConfiguration {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public JobToken jobToken() {
        return new JobToken();
    }

    public static class JobToken {
    }
}
~~~

Đoạn trên minh họa cách khai báo một bean prototype; class `JobConfiguration` có thể được Spring phát hiện hoặc đăng ký như một cấu hình. `@Scope` phải nằm trên **definition** thực sự được Spring đăng ký. Gắn `@Scope` lên một đối tượng tạo bằng `new` mà không đăng ký bean không có tác dụng quản lý vòng đời.

### 3.3. Chọn proxy khi khai báo scope

~~~java
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestAuditContext {
    public String description() {
        return "Thông tin gắn với request hiện tại";
    }
}
~~~

Hai cách `@Scope("request")` và `@Scope(scopeName = "request")` đều hợp lệ: `value` và `scopeName` là hai tên bí danh. Thuộc tính `proxyMode` quy định có tạo đối tượng đại diện hay không và loại proxy:

| `ScopedProxyMode` | Ý nghĩa |
| --- | --- |
| `DEFAULT` | Theo mặc định cấu hình component scan; thông thường dẫn đến không tạo scoped proxy |
| `NO` | Không tạo proxy; nhận trực tiếp target khi scope đang hoạt động |
| `INTERFACES` | Proxy dựa trên interface (JDK dynamic proxy); điểm inject nên dùng interface |
| `TARGET_CLASS` | Proxy theo class, phù hợp khi inject bằng concrete type; có giới hạn với `final` class/method |

`@Scope` thông thường không tự bật scoped proxy. Việc gắn `@Scope("request")` đơn thuần chưa giải quyết bài toán singleton phụ thuộc request-scoped bean.

## 4. Ba annotation chuyên biệt cho phạm vi web

Spring Framework cung cấp **composed annotations** trong `org.springframework.web.context.annotation`. Chúng là cách viết rõ ngữ nghĩa hơn cho `@Scope` và đều dùng được trên class component lẫn phương thức `@Bean`.

| Annotation | Tương đương theo scope | Mặc định `proxyMode` | Dùng khi |
| --- | --- | --- | --- |
| `@RequestScope` | `@Scope("request")` | `TARGET_CLASS` | Lưu thông tin tạm trong một HTTP request |
| `@SessionScope` | `@Scope("session")` | `TARGET_CLASS` | Lưu trạng thái riêng cho một HTTP session |
| `@ApplicationScope` | `@Scope("application")` | `TARGET_CLASS` | Trạng thái chung trong một `ServletContext` |

**Điểm rất quan trọng:** `@RequestScope` không hoàn toàn tương đương `@Scope("request")` nếu không xét `proxyMode`. Annotation chuyên biệt **mặc định tạo class-based scoped proxy**; `@Scope("request")` thông thường không làm vậy. Tương tự cho session và application.

### 4.1. `@RequestScope`: một target trong mỗi HTTP request

~~~java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestCorrelation {
    private final String requestId = UUID.randomUUID().toString();

    public String getRequestId() {
        return requestId;
    }
}
~~~

Một request gọi `getRequestId()` nhiều lần trên scoped proxy sẽ nhận cùng `requestId` từ cùng target. HTTP request kế tiếp sử dụng target mới. Đừng nhầm với `@RequestParam`: `@RequestParam` lấy giá trị tham số của HTTP request cho controller; `@RequestScope` thay đổi **vòng đời của một Spring bean**.

Một bean request scope hữu ích để giữ dữ liệu request-specific đã được kiểm tra, trạng thái tính toán tạm, mã truy vết trong call chain. Dữ liệu cần dùng xuyên nhiều HTTP request không nên để ở đây.

### 4.2. `@SessionScope`: một target trong mỗi HTTP session

~~~java
import java.io.Serial;
import java.io.Serializable;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class SessionVisitCounter implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final AtomicInteger visits = new AtomicInteger();

    public int nextVisit() {
        return visits.incrementAndGet();
    }
}
~~~

Những HTTP request mang cùng session ID sẽ truy cập cùng target session-scoped. Người dùng khác có session khác sẽ có bean riêng. Việc hiện thực `Serializable` là lựa chọn phù hợp nếu ứng dụng cần cơ chế serialize/passivate/replicate HTTP session, nhưng còn phụ thuộc vào các field bên trong và hạ tầng session.

Một session có thể nhận **nhiều request đồng thời** (nhiều tab hoặc AJAX), vì vậy session-scoped bean không mặc nhiên thread-safe. Ví dụ dùng `AtomicInteger` để cập nhật bộ đếm an toàn hơn `int++`.

Session scope **không tự xác thực người dùng**: nó dựa vào HTTP session. Không lấy bean scope làm cơ chế thay thế cho Spring Security, và tránh lưu dữ liệu nhạy cảm quá mức cần thiết trong session.

### 4.3. `@ApplicationScope`: một target trong một `ServletContext`

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
public class LocalApplicationMetrics {
    private final AtomicLong requests = new AtomicLong();

    public long nextRequest() {
        return requests.incrementAndGet();
    }
}
~~~

Tất cả session cùng một web application/`ServletContext` nhìn thấy cùng bộ đếm. Nếu khởi chạy hai instance ứng dụng trên hai JVM khác nhau, mỗi instance có bộ đếm riêng. Những trạng thái phải đúng trên cả cụm máy nên dùng cơ sở dữ liệu, Redis hoặc hệ thống phối hợp tương ứng.

`@ApplicationScope` dành cho trạng thái thực sự theo web application. Với phần lớn service không giữ trạng thái, `singleton` thông thường là đủ và đơn giản hơn.

### 4.4. Tùy chỉnh proxy của annotation chuyên biệt

Các annotation chuyên biệt có thuộc tính `proxyMode`:

~~~java
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.stereotype.Component;

@Component
@RequestScope(proxyMode = ScopedProxyMode.NO)
public class TemporaryBuffer {
    public String read() {
        return "temporary";
    }
}
~~~

Khi đặt `NO`, cần bảo đảm việc lấy target xảy ra **trong request hợp lệ**, chẳng hạn thông qua `ObjectProvider<TemporaryBuffer>` ngay bên trong phương thức đang xử lý request. Nếu muốn dùng proxy JDK, khai báo bean implement interface và `@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)` rồi inject bằng interface đó.

## 5. Scoped proxy: vì sao bean singleton vẫn gọi đúng bean theo request?

Controller và service trong Spring MVC thường là `singleton`. Nếu chỉ inject trực tiếp **target request-scoped** vào constructor singleton, Spring phải giải quyết dependency lúc tạo singleton, khi đó thường chưa có request; hoặc một target có vòng đời ngắn bị giữ quá lâu. Scoped proxy giải quyết bất tương thích vòng đời này.

~~~text
Singleton Controller (được tạo lúc khởi động)
    |
    | field requestCorrelation
    v
Scoped Proxy (tham chiếu ổn định trong singleton)
    |
    | mỗi lần gọi phương thức
    v
Tìm target theo HTTP request hiện tại
    |-- Request A --> Target A
    |-- Request B --> Target B
    '-- Request C --> Target C
~~~

Một proxy được inject vào singleton; mỗi lời gọi phương thức hợp lệ được chuyển tiếp tới target của **ngữ cảnh scope hiện tại**. Vì thế:

- Việc tạo singleton không buộc target request phải được tạo ngay.
- Trong cùng request, các lần truy cập cùng bean definition thường nhận cùng target.
- Sang request hoặc session khác, cùng một trường dependency proxy có thể chuyển tới target khác.
- Proxy **không tự tạo HTTP request**. Gọi proxy từ thread không có request được bind vẫn có thể thất bại.

Cách dùng điển hình:

~~~java
import org.springframework.stereotype.Service;

@Service
public class AuditService {
    private final RequestCorrelation requestCorrelation;

    public AuditService(RequestCorrelation requestCorrelation) {
        this.requestCorrelation = requestCorrelation;
    }

    public String describe() {
        // Trường chứa proxy; target được chọn ở thời điểm gọi.
        return "request=" + requestCorrelation.getRequestId();
    }
}
~~~

Đoạn `AuditService` phụ thuộc class `RequestCorrelation` đã khai báo ở mục 4.1; đây là mã ghép vào ứng dụng Spring MVC, không phải một chương trình Java chạy độc lập.

**Chọn `TARGET_CLASS` hay `INTERFACES`?** Với inject theo concrete class, `TARGET_CLASS` thường thuận tiện. Không nên dựa vào class `final` hoặc method `final` cần proxy intercept; cơ chế subclass-based proxy không thể override phương thức final. Với interface rõ ràng, `INTERFACES` cho phép thiết kế phụ thuộc abstraction. Tránh xem scoped proxy là một đối tượng target để lưu cache bằng identity hoặc truy cập trạng thái ở thời điểm không có scope.

## 6. Khi không muốn sử dụng scoped proxy: `ObjectProvider`

`ObjectProvider<T>` (package `org.springframework.beans.factory`) cho phép **lấy bean tại thời điểm cần dùng**. Cách này hữu ích với prototype hoặc request bean có `proxyMode = NO`.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class BufferService {
    private final ObjectProvider<TemporaryBuffer> provider;

    public BufferService(ObjectProvider<TemporaryBuffer> provider) {
        this.provider = provider;
    }

    public String inspectCurrentRequest() {
        TemporaryBuffer buffer = provider.getObject();
        return buffer.read();
    }
}
~~~

Đoạn này dùng class `TemporaryBuffer` ở mục 4.4 và phải được gọi trong HTTP request đang hoạt động. `ObjectProvider` không tự tạo scope và không tự mang request context sang thread khác.

Với prototype:

~~~java
@Component
@Scope("prototype")
public class WorkUnit {
}

@Service
public class WorkFactory {
    private final ObjectProvider<WorkUnit> provider;

    public WorkFactory(ObjectProvider<WorkUnit> provider) {
        this.provider = provider;
    }

    public boolean getTwoDifferentInstances() {
        return provider.getObject() != provider.getObject();
    }
}
~~~

Khi `WorkUnit` đúng là prototype bean, phương thức trên trả về `true`. Nếu inject một `WorkUnit` trực tiếp vào singleton qua constructor và giữ field đó, singleton chỉ nhận một prototype instance tại thời điểm injection. Đây là khác biệt cơ bản giữa **scope định nghĩa việc tạo bean** và **thời điểm dependency được giải quyết**.

## 7. Ví dụ Spring Boot hoàn chỉnh: request, session, application và prototype

Ứng dụng sau đặt tất cả class trong **một file Java** để có thể chạy và kiểm chứng ngay. Spring Boot 3.3.x dùng Spring Framework 6.1.x. Các component bên trong là `public static` nested classes nên được component scan nhận diện; các class target không khai báo `final`.

Cấu trúc dự án:

~~~text
scope-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── scopes/
                        └── ScopeDemoApplication.java
~~~

### 7.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>scope-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

### 7.2. `src/main/java/com/example/scopes/ScopeDemoApplication.java`

~~~java
package com.example.scopes;

import java.io.Serial;
import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.ApplicationScope;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class ScopeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopeDemoApplication.class, args);
    }

    @Component
    @RequestScope
    public static class RequestIdentity {
        private final String id = UUID.randomUUID().toString();

        public String id() {
            return id;
        }
    }

    @Component
    @SessionScope
    public static class SessionCounter implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final AtomicInteger counter = new AtomicInteger();

        public int next() {
            return counter.incrementAndGet();
        }
    }

    @Component
    @ApplicationScope
    public static class ApplicationCounter {
        private final AtomicInteger counter = new AtomicInteger();

        public int next() {
            return counter.incrementAndGet();
        }
    }

    @Component
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public static class PrototypeTicket {
    }

    @RestController
    public static class ScopeController {
        private final RequestIdentity requestIdentity;
        private final SessionCounter sessionCounter;
        private final ApplicationCounter applicationCounter;
        private final ObjectProvider<PrototypeTicket> tickets;

        public ScopeController(
                RequestIdentity requestIdentity,
                SessionCounter sessionCounter,
                ApplicationCounter applicationCounter,
                ObjectProvider<PrototypeTicket> tickets) {
            this.requestIdentity = requestIdentity;
            this.sessionCounter = sessionCounter;
            this.applicationCounter = applicationCounter;
            this.tickets = tickets;
        }

        @GetMapping("/scopes")
        public Map<String, Object> scopes() {
            String first = requestIdentity.id();
            String second = requestIdentity.id();

            PrototypeTicket ticketA = tickets.getObject();
            PrototypeTicket ticketB = tickets.getObject();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("requestId", first);
            result.put("sameRequestBean", first.equals(second));
            result.put("sessionCalls", sessionCounter.next());
            result.put("applicationCalls", applicationCounter.next());
            result.put("distinctPrototypeTickets", ticketA != ticketB);
            return result;
        }
    }
}
~~~

**Giải thích các dependency:** `ScopeController` là singleton mặc định. `RequestIdentity`, `SessionCounter` và `ApplicationCounter` được inject dưới dạng scoped proxy nhờ annotation chuyên biệt. `PrototypeTicket` dùng `ObjectProvider` để mỗi lần gọi `getObject()` tạo một target mới.

### 7.3. Chạy và quan sát

Yêu cầu: JDK 17 trở lên và Maven 3.9.x. Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác, gọi endpoint lần lượt:

~~~bash
# Request đầu tiên: lưu cookie phiên.
curl -s -c cookies.txt http://localhost:8080/scopes

# Request thứ hai: dùng lại cùng HTTP session.
curl -s -b cookies.txt -c cookies.txt http://localhost:8080/scopes

# Request thứ ba: không gửi cookie session cũ.
curl -s http://localhost:8080/scopes
~~~

Mỗi response là JSON chứa năm trường:

~~~json
{
  "requestId": "UUID-duoc-tao-tu-request",
  "sameRequestBean": true,
  "sessionCalls": 1,
  "applicationCalls": 1,
  "distinctPrototypeTickets": true
}
~~~

**JSON ở trên là biểu diễn minh họa**, không phải stdout cố định: `requestId` là UUID sinh động và các bộ đếm thay đổi theo thứ tự truy cập, lượt gọi trước đó và thời điểm restart. Các quan sát cần kiểm chứng là:

1. `sameRequestBean` luôn là `true` trong từng HTTP request, bởi cùng target request được truy cập hai lần.
2. `requestId` thường khác giữa các request do mỗi target mới tạo UUID mới (UUID có xác suất trùng cực nhỏ; kiểm thử quyết định hơn nên so sánh object identity trong cùng scope).
3. `sessionCalls` tăng từ 1 lên 2 khi gọi lại với cùng cookie `JSESSIONID`; client không mang cookie cũ bắt đầu một session riêng với bộ đếm 1.
4. `applicationCalls` tiếp tục tăng qua các request, kể cả hai session khác nhau, khi chạy trong cùng một instance ứng dụng.
5. `distinctPrototypeTickets` luôn là `true` vì hai lần lấy prototype nhận hai Java object khác nhau.

Có thể mở thêm một trình duyệt private/incognito để quan sát sự độc lập của session. Nếu ứng dụng chạy dưới load balancer nhiều JVM mà không có session affinity hoặc session store chung, hành vi session và bộ đếm application sẽ còn phụ thuộc hạ tầng triển khai.

## 8. Scope `websocket`: trường hợp đặc biệt

Trong ứng dụng **Spring Messaging với STOMP over WebSocket**, target scope `websocket` sống theo một WebSocket session. Ở Spring Framework 6.x, có thể khai báo:

~~~java
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SocketConversationState {
    private int messages;

    public int nextMessage() {
        return ++messages;
    }
}
~~~

Đoạn trên là **thành phần minh họa**, chỉ có hiệu lực khi ứng dụng đã cấu hình STOMP WebSocket message broker và scope `websocket` tương ứng; không thể tự chạy như một `main()` Java đơn lẻ. Bean nên được truy xuất trong luồng xử lý message đang có WebSocket session. Nếu nhiều message của cùng session có thể xử lý đồng thời, phải bảo vệ mutable state tương ứng.

**Lưu ý phiên bản:** Spring Framework **7.0** bổ sung annotation `@WebSocketScope` với `proxyMode` mặc định `TARGET_CLASS`. Trong dự án Spring Framework **6.1.x / Boot 3.3.x** của ví dụ ở trên, sử dụng `@Scope("websocket", proxyMode = ...)`; không import `@WebSocketScope` từ API 7.x vào dự án 6.x.

WebSocket scope không đồng nghĩa với HTTP `session`: WebSocket session có vòng đời kết nối riêng, còn HTTP session được quản lý bởi Servlet container. Một HTTP session có thể gắn với nhiều WebSocket connection.

## 9. Điều kiện để web scope hoạt động

Trong luồng request do **Spring MVC `DispatcherServlet`** xử lý, Spring thông thường đã đưa request attributes vào ngữ cảnh phù hợp; không phải tự đăng ký listener cho trường hợp phổ biến.

Trong Servlet application có request được xử lý **ngoài `DispatcherServlet`**, có thể cần `RequestContextListener` hoặc `RequestContextFilter` để bind request vào thread xử lý theo hướng dẫn Spring. Điều này cần cấu hình đúng Servlet environment. Web scope không mặc định tồn tại trong một IoC context Java thuần.

Không được suy diễn rằng thread mới hoặc tác vụ `@Async` tự mang theo request/session context. Ví dụ:

~~~java
// Mã minh họa vấn đề: khi chạy ở thread không có request context,
// lời gọi scoped proxy có thể phát sinh ScopeNotActiveException.
executor.execute(() -> requestCorrelation.getRequestId());
~~~

Nếu cần xử lý bất đồng bộ, nên **trích xuất dữ liệu bất biến cần thiết trong request hiện tại**, rồi truyền rõ ràng vào tác vụ. Không dùng scoped proxy để che giấu việc thiếu context. Với WebFlux/reactive processing, cần xét mô hình lưu trữ ngữ cảnh riêng; không mặc định áp dụng các giả định `ThreadLocal` của Servlet MVC.

## 10. Vòng đời, hủy bean và quản lý trạng thái

- Spring thường tạo singleton khi khởi tạo context (trừ lazy). Singleton có thể có init/destroy callback gắn vòng đời container.
- Prototype được Spring khởi tạo và inject dependency khi lấy bean; container không tự chạy destruction callback cho từng prototype được giao ra. Phía sử dụng cần chủ động dọn dẹp tài nguyên.
- Request/session/application/WebSocket scope quản lý target theo ngữ cảnh tương ứng. Callback như `@PreDestroy` có thể chạy khi scope tiêu hủy target theo lifecycle được hỗ trợ, phụ thuộc việc request/session/context được đóng/hủy bình thường.
- Scoped proxy là đối tượng trung gian có thể sống lâu; **target thực** mới mang trạng thái thuộc request hoặc session.
- Scope không cung cấp khóa đồng bộ. Session/app bean có mutable state phải xử lý truy cập đồng thời nếu có nhiều request hoặc nhiều thread.

Không dùng bean scope như nơi lưu mọi dữ liệu nghiệp vụ lâu dài. Trạng thái cần truy vấn, khôi phục sau restart, hoặc chia sẻ giữa nhiều instance nên thuộc hệ thống lưu trữ phù hợp. Luôn cân nhắc rò rỉ thông tin giữa người dùng nếu vô tình đặt request/session state vào singleton/application bean.

## 11. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `No Scope registered for scope name 'request'` | Context không hỗ trợ/đăng ký web scope | Dùng `WebApplicationContext` phù hợp; kiểm tra môi trường Servlet và cấu hình |
| `ScopeNotActiveException` hoặc `No thread-bound request found` | Lấy target request scope ngoài HTTP request đang bind | Chỉ truy cập trong request hợp lệ hoặc truyền dữ liệu cần thiết sang thread khác |
| Injection request bean vào singleton thất bại lúc startup | `@Scope("request")` không có proxy, target bị resolve khi chưa có request | Dùng `@RequestScope`, chọn `proxyMode` hoặc `ObjectProvider` |
| Cùng một prototype trong mọi lời gọi service | Prototype được inject một lần qua constructor vào singleton | Dùng `ObjectProvider.getObject()` khi cần instance mới |
| Field của `@SessionScope` thay đổi bất thường | Nhiều request trong một session cùng sửa mutable state | Thiết kế immutable hoặc đồng bộ/thread-safe theo nhu cầu |
| `@ApplicationScope` không chia sẻ giữa các pod | Một `ServletContext` trên mỗi instance triển khai | Chuyển trạng thái chia sẻ sang persistence/distributed store |
| Proxy class lỗi hoặc method final không được intercept | Dùng `TARGET_CLASS` với kiểu/phương thức khó proxy | Bỏ `final` ở điểm cần intercept hoặc dùng interface proxy phù hợp |
| Bị mất dữ liệu giữa hai request | Dùng `@RequestScope` cho dữ liệu cần tồn tại lâu hơn | Chọn session hoặc nơi lưu trữ bền vững tùy nhu cầu |
| Áp dụng `@Scope` nhưng không thấy hiệu lực | Object do `new` tạo hoặc class không được Spring đăng ký bean | Đăng ký `@Component`/`@Bean` đúng package và lấy object từ container |
| Import `@WebSocketScope` không tồn tại | Dùng Spring Framework 6.x trong khi annotation thuộc 7.0+ | Trên 6.x dùng `@Scope("websocket", proxyMode = ...)` |

Một cách gỡ lỗi thực dụng là xác nhận **(1)** bean có được đăng ký không, **(2)** scope name là gì, **(3)** proxy có được tạo không, **(4)** thread/request/session hiện tại có hoạt động không, và **(5)** có đang vô tình giữ target trực tiếp trong một singleton không.

## 12. Tiêu chí lựa chọn scope

- **Service thuần, stateless:** giữ `singleton` mặc định; ít chi phí và rõ vòng đời.
- **Mỗi lần yêu cầu bean là một công việc/trạng thái mới:** cân nhắc `prototype` cùng `ObjectProvider`, đồng thời tự quản lý cleanup.
- **Dữ liệu sống đúng một HTTP request:** `@RequestScope`, đặc biệt khi nhiều tầng xử lý cùng cần request-specific context.
- **Dữ liệu cần giữ trong một HTTP session:** `@SessionScope` sau khi cân nhắc bộ nhớ, timeout, phân tán, serialization và concurrency.
- **Dữ liệu gắn với một web application/`ServletContext`:** `@ApplicationScope` khi cần đúng ngữ nghĩa ServletContext; trạng thái toàn cục giữa các JVM phải chuyển sang storage chia sẻ.
- **Dữ liệu gắn với STOMP WebSocket session:** `websocket` scope trong môi trường đã cấu hình phù hợp.

Tự kiểm tra kiến thức: Vì sao một singleton controller có thể sử dụng `@RequestScope` bean cho các request khác nhau mà không cần tạo lại controller? Tại sao inject trực tiếp prototype vào singleton không mang lại prototype mới mỗi lần gọi method? Vì sao `@SessionScope` không bảo đảm thread safety? Nếu giải thích được cả ba bằng **thời điểm dependency được resolve, proxy delegation và ranh giới scope**, bạn đã nắm cơ chế cốt lõi.

## 13. Tài liệu chính thức

- [Spring Framework 6.1 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-scopes.html)
- [`@RequestScope` Javadoc (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/web/context/annotation/RequestScope.html)
- [Spring Framework 6.2 — WebSocket Scope](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/scope.html)
- [`@WebSocketScope` Javadoc (Spring Framework 7.0+)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketScope.html)
