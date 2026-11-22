# Quyền truy cập khi listener xử lý trong Spring Application Events

## 1. Câu hỏi cốt lõi: nhận được event có đồng nghĩa được phép xử lý?

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(...)` là cơ chế phát sự kiện **bên trong ứng dụng**. Một `@EventListener` sẽ được Spring chọn theo kiểu event và có thể thực thi logic nghiệp vụ. Tuy nhiên, **khả năng nhận một event không phải là quyền truy cập vào dữ liệu, tài nguyên hoặc thao tác mà listener sắp thực hiện**.

Ví dụ: sau khi đặt đơn, hệ thống phát `OrderPlaced`. Các listener có thể ghi audit, truy vấn hồ sơ người mua, gửi email, cập nhật hạn mức tín dụng hoặc khởi động quy trình hoàn tiền. Những side effect này có **quyền hạn khác nhau**. Việc Spring gửi event tới listener không tự kiểm tra rằng người dùng hiện tại có quyền gọi API gửi email hay truy cập đơn hàng của một tenant khác.

Cần phân biệt bốn tầng:

1. **Nguồn phát**: ai được phép tạo nghiệp vụ khiến sự kiện xuất hiện?
2. **Sự kiện**: dữ liệu có đúng schema, đáng tin và đủ thông tin để xác thực nguồn gốc không?
3. **Listener**: việc xử lý đang chạy dưới danh tính/security context nào?
4. **Service thực hiện side effect**: có được phép đọc/ghi tài nguyên cụ thể đó tại **thời điểm thực thi** hay không?

Một quy tắc quan trọng:

> **Event cho biết điều gì đã xảy ra; nó không tự cấp quyền cho người nhận thực hiện mọi hành động liên quan.**

Với listener đồng bộ chạy ngay trong request thread, `SecurityContextHolder` có thể còn lưu `Authentication` của người dùng. Nhưng khi chuyển sang `@Async`, executor, job retry hoặc xử lý sau commit, quyền và danh tính có thể vắng mặt hoặc đã thay đổi. Vì thế thiết kế đúng cần kết hợp **Spring Security method authorization**, quản lý **SecurityContext** an toàn, và **ủy quyền nghiệp vụ** phù hợp.

## 2. Phân biệt authentication, authorization và event filtering

| Khái niệm | Trả lời câu hỏi | Cơ chế ví dụ |
| --- | --- | --- |
| **Authentication** | Caller/worker là ai? | `Authentication` trong `SecurityContextHolder`, JWT đã được xác minh, service principal. |
| **Authorization** | Actor có được thực hiện thao tác cụ thể không? | `@PreAuthorize`, `AuthorizationManager`, policy ở domain/service layer. |
| **Event type matching** | Listener có đăng ký nhận loại event này không? | `@EventListener`, `ApplicationListener<E>` và multicaster. |
| **Event condition** | Payload có thỏa quy tắc lọc nghiệp vụ không? | `@EventListener(condition = "...")`. |
| **Data/tenant isolation** | Actor có được xem/sửa đúng bản ghi thuộc phạm vi mình không? | Kiểm tra owner/tenant/object permission, truy vấn có tenant constraint. |
| **Message authenticity** | Event từ nguồn nào và có bị sửa hay giả mạo không? | Identity của publisher, mTLS/ACL, xác minh signature khi qua broker. |

**`@EventListener(condition)` không phải cơ chế phân quyền.** Nó có thể lọc theo event data, ví dụ `status == 'PAID'`, nhưng nếu dữ liệu đến từ nguồn không đáng tin, điều kiện chỉ cho biết dữ liệu khớp expression. Nó không chứng minh người phát sở hữu đơn hàng hoặc có `ROLE_ADMIN`.

Ví dụ dễ mắc lỗi:

~~~java
// KHÔNG dùng giá trị claimedRole trong payload làm bằng chứng được ủy quyền.
@EventListener(condition = "#p0.claimedRole() == 'ADMIN'")
public void grantRefund(OrderEvent event) {
    // side effect nhạy cảm
}
~~~

*Đây là anti-pattern minh họa; `OrderEvent` là kiểu giả định. Không dùng đoạn mã trên để bảo vệ thao tác hoàn tiền.*

Đối tượng event có thể chứa `claimedRole="ADMIN"` do caller tự gửi, không khác một chuỗi dữ liệu bình thường. Quyền chỉ có ý nghĩa khi xuất phát từ **security context được xác thực** hoặc một policy/claim đã được kiểm tra tại trust boundary thích hợp.

## 3. Hành vi mặc định của Spring: listener thường chạy cùng thread

Theo cách hoạt động mặc định của `SimpleApplicationEventMulticaster`, listener được gọi đồng bộ trên thread phát event:

~~~text
HTTP request thread
  |
  | SecurityContextHolder -> Authentication("alice", ORDER_NOTIFY)
  v
OrderController -> OrderService.placeOrder()
  |
  | publishEvent(OrderPlaced)
  v
SimpleApplicationEventMulticaster
  |
  v
@EventListener OrderListener.onOrderPlaced()
  |
  | cùng thread, cùng SecurityContextHolder của request nếu còn hiệu lực
  v
@PreAuthorize trên protected service
  |
  +-- granted -> thực thi side effect
  +-- denied  -> ném lỗi, không vào method body
~~~

Đặc điểm:

- Khi listener chạy **cùng thread** và scope xác thực của request vẫn đang mở, `SecurityContextHolder.getContext().getAuthentication()` thường trả về cùng principal/authorities mà request đã được xác thực.
- Điều đó **không có nghĩa mọi event đều có người dùng đăng nhập**. Startup events, scheduler, batch, CLI và message consumer có thể không chạy trong HTTP security filter chain.
- Một sự kiện chỉ được gọi từ một component nội bộ cũng **không tự bảo đảm** mọi dữ liệu và quyền nghiệp vụ đã được xác thực.
- Khi listener đồng bộ ném một exception không được bắt, exception có thể đi ngược về lời gọi `publishEvent(...)`, ảnh hưởng đến service/transaction đang gọi.
- Nếu nhiều listener cùng nhận event, một listener có thể đã thực hiện side effect trước khi listener khác bị từ chối. **Lỗi quyền ở một listener không biến toàn bộ fan-out thành giao dịch phân tán nguyên tử.**

Spring không thêm một “quyền LISTEN_EVENT” chung cho mọi `@EventListener`. Để bảo vệ hành động, cần đặt kiểm tra quyền tại điểm gọi service, repository hoặc API nhạy cảm phù hợp.

## 4. Spring Security quản lý quyền ở đâu?

### 4.1. SecurityContextHolder và Authentication

Trong ứng dụng servlet/imperative phổ biến, Spring Security quản lý `SecurityContext` chứa `Authentication`, thường gắn với thread hiện tại:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

*Đây là đoạn Java tích hợp. Cần import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`.*

Một `Authentication` có thể bao gồm principal, authorities, trạng thái xác thực và các thông tin tùy provider. Không nên tự suy ra quyền chỉ từ `getName()`, email hoặc một chuỗi `actorId` trong event.

Nếu không có authentication hoặc actor được xác thực không có quyền cần thiết, policy bảo mật phải **từ chối hoặc chuyển sang mô hình service principal có kiểm soát**, không tự gán một người dùng đặc quyền vào thread cho tiện.

### 4.2. Bật method security

Với Spring Security hiện đại, dùng:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

*Đoạn cấu hình minh họa: cần import `org.springframework.context.annotation.Configuration` và `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`.*

`@EnableMethodSecurity` kích hoạt hạ tầng phương thức như `@PreAuthorize`. **Chỉ thêm `spring-boot-starter-security` chưa đồng nghĩa tất cả method sẽ tự có `@PreAuthorize`.** Các phương thức không được bảo vệ bằng annotation/policy phù hợp có thể vẫn được gọi.

Ví dụ bảo vệ thao tác gửi thông báo:

~~~java
@Service
class NotificationService {
    @PreAuthorize("hasAuthority('ORDER_NOTIFY')")
    public void notifyOrder(OrderPlaced event) {
        // side effect chỉ được thực hiện sau khi kiểm tra authority
    }
}
~~~

*Đoạn code minh họa: cần `@Service`, `@PreAuthorize` và kiểu `OrderPlaced`.*

`hasAuthority('ORDER_NOTIFY')` yêu cầu authority **đúng chuỗi `ORDER_NOTIFY`**. Nếu dùng `hasRole('OPS')`, Spring Security mặc định diễn giải thành authority có tiền tố `ROLE_OPS`; không nhầm hai biểu thức.

### 4.3. Kiểm tra qua AOP proxy, không chỉ ghi annotation

Spring method security mặc định dùng AOP. Khi một bean bên ngoài gọi protected method qua **Spring proxy**, interceptor sẽ kiểm tra quyền trước khi method body chạy.

Ngược lại, nếu cùng class gọi `this.securedMethod()`, lời gọi self-invocation có thể **bỏ qua proxy**. Vì vậy nên tách:

~~~text
OrderEventListener (bean)
    |
    | gọi qua dependency được Spring inject
    v
SecuredNotificationService (proxy)
    |
    | @PreAuthorize/AuthorizationManager
    v
Side effect
~~~

Thực hành tốt: để listener điều phối nhẹ và gọi **protected application service** riêng. Điều này còn bảo vệ service nếu ngày mai nó được gọi từ REST controller, CLI, scheduler hay một listener khác.

`@PreAuthorize` gắn trực tiếp trên listener method cũng có thể hoạt động khi việc gọi phương thức thật sự đi qua proxy được Spring quản lý, nhưng cần kiểm thử proxy mode, method visibility và registration của `@EventListener`. Đặt quyền ở service thực hiện side effect giúp quy tắc ít phụ thuộc hơn vào chi tiết dispatch.

## 5. Bảo vệ đúng đối tượng dữ liệu, không chỉ theo quyền toàn cục

Có authority `ORDER_NOTIFY` không có nghĩa nhân viên được gửi thông báo cho **mọi đơn hàng của mọi tenant**.

Một chính sách đầy đủ có thể yêu cầu cả:

- Actor được xác thực và có authority tối thiểu cho thao tác.
- Đơn hàng tồn tại và thuộc tenant/organization actor được phép phục vụ.
- Actor được phép thao tác trên **trạng thái hiện tại** của đơn hàng.
- Đích gửi (email/SMS/payment endpoint) đúng quy định, không lấy từ payload không đáng tin.
- Mọi thao tác truy cập DB đều áp dụng tenant isolation, không chỉ kiểm tra ở controller.

Ví dụ minh họa kiểm tra object-level authorization trong service:

~~~java
@PreAuthorize("hasAuthority('ORDER_NOTIFY')")
public void notifyOrder(OrderPlaced event) {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

    // orderAccessPolicy tra cứu quyền đối với orderId thật từ dữ liệu đáng tin.
    if (!orderAccessPolicy.canNotify(auth, event.orderId())) {
        throw new AccessDeniedException("Not allowed to notify this order");
    }

    // Thực thi tác dụng phụ sau khi cả authority lẫn object policy đều đạt.
    notificationGateway.sendForOrder(event.orderId());
}
~~~

*Đây là đoạn tích hợp minh họa; `orderAccessPolicy` và `notificationGateway` là dependency nghiệp vụ phải tự định nghĩa. Cần import `Authentication` và `AccessDeniedException`.*

Đừng thực hiện “check tenant” bằng cách so sánh hai chuỗi **cùng lấy từ event chưa được xác minh**; đó không phải kiểm tra quyền. Policy cần đối chiếu với danh tính được xác thực và dữ liệu được lưu/tra cứu từ nguồn đáng tin cậy.

Với hệ thống nhiều tenant, nên kết hợp kiểm tra domain với điều kiện truy vấn giới hạn tenant, tránh chỉ có một lớp logic trong listener. Nếu dùng row-level security của database, hãy xác định rõ cách đặt database identity/tenant session và vòng đời connection.

## 6. Ví dụ Java 17+ chạy được: event bị giả mạo role vẫn không qua @PreAuthorize

Ví dụ dùng **Spring Boot 3.5.16**, Java 17+ và Maven. Ứng dụng không mở web server, để mô phỏng hai actor trong phương thức `main` mà không cần HTTP login:

- `alice` được gán authority đáng tin cậy `ORDER_NOTIFY` → được phép gọi protected service.
- `bob` chỉ có authority `ORDER_VIEW` → bị từ chối.
- **Cả hai event đều khai `claimedRole="ADMIN"`**. Trường này chỉ là dữ liệu event, không tham gia quyết định phân quyền.

Điều quan trọng là `@EventListener` không tự trao quyền; nó gọi một bean service đã được Spring Security bảo vệ bằng `@PreAuthorize`.

### 6.1. Cấu trúc

~~~text
event-access-demo/
├── pom.xml
└── src/main/java/example/EventAuthorizationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>event-access-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

`src/main/java/example/EventAuthorizationDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class EventAuthorizationDemo {

    // claimedRole la du lieu nhan duoc, KHONG phai authority da xac minh.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String actorId,
            String claimedRole) {
    }

    // La Spring bean: method security tao proxy cho protected method.
    @Bean
    public SecuredNotificationService securedNotificationService() {
        return new SecuredNotificationService();
    }

    // Bean listener goi service qua dependency duoc Spring inject.
    @Bean
    public OrderListener orderListener(
            SecuredNotificationService securedNotificationService) {
        return new OrderListener(securedNotificationService);
    }

    public static class SecuredNotificationService {

        @PreAuthorize("hasAuthority('ORDER_NOTIFY')")
        public void sendNotification(OrderPlaced event) {
            System.out.println("SENT " + event.orderId());
        }
    }

    public static class OrderListener {

        private final SecuredNotificationService service;

        public OrderListener(SecuredNotificationService service) {
            this.service = service;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            // Khong tin vao event.claimedRole() de cap quyen.
            service.sendNotification(event);
        }
    }

    private static void publishAs(
            ApplicationEventPublisher publisher,
            String username,
            String authority,
            OrderPlaced event) {

        // Gia lap mot SecurityContext da xac thuc.
        // Production: authentication den tu bo loc/token duoc xac minh.
        Authentication auth =
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        "not-used",
                        AuthorityUtils.createAuthorityList(authority));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);

        try {
            publisher.publishEvent(event);
            System.out.println("ALLOWED " + username
                    + " " + event.orderId());
        } catch (AccessDeniedException denied) {
            System.out.println("DENIED " + username
                    + " " + event.orderId());
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(EventAuthorizationDemo.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.<String, Object>of(
                "logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            publishAs(
                    context,
                    "alice",
                    "ORDER_NOTIFY",
                    new OrderPlaced(
                            "evt-1", "ORD-7", "alice", "ADMIN"));

            publishAs(
                    context,
                    "bob",
                    "ORDER_VIEW",
                    new OrderPlaced(
                            "evt-2", "ORD-8", "bob", "ADMIN"));
        }
    }
}
~~~

Để chạy từ thư mục có `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

**Các dòng do chương trình in trên stdout khi khởi động thành công**, không kể log riêng của Maven:

~~~text
SENT ORD-7
ALLOWED alice ORD-7
DENIED bob ORD-8
~~~

### 6.2. Giải thích chi tiết

1. `@SpringBootApplication` tạo Spring context; `@EnableMethodSecurity` kích hoạt method authorization.
2. `SecuredNotificationService` được tạo làm Spring bean; Spring Security có thể tạo AOP proxy để chặn lời gọi `sendNotification(...)`.
3. `OrderListener` được tạo làm bean, nên `@EventListener` được đăng ký. Nó **không tự kiểm tra** trường `claimedRole` trong payload.
4. `publishAs(...)` mô phỏng security context của hai actor bằng `UsernamePasswordAuthenticationToken.authenticated(...)`. Trong ứng dụng thật, **không dùng cách này để biến dữ liệu từ client thành người dùng đã đăng nhập**; authentication phải được xác minh ở trust boundary.
5. Khi `alice` gọi `publishEvent(...)`, listener chạy đồng bộ trong cùng thread, thấy authentication có authority `ORDER_NOTIFY`. Lời gọi tới service được phép, nên `SENT ORD-7` xuất hiện rồi publisher in `ALLOWED alice ORD-7`.
6. Khi `bob` gọi tương tự, authority chỉ có `ORDER_VIEW`. Interceptor của `@PreAuthorize` từ chối **trước khi method body chạy**, nên **không có** dòng `SENT ORD-8`. `AccessDeniedException` được bắt trên publisher thread trong cấu hình đồng bộ, rồi in `DENIED bob ORD-8`.
7. Cả hai event đều mang `claimedRole="ADMIN"`, nhưng trường ấy không thay đổi `Authentication` hoặc authorities mà security policy nhìn thấy.
8. `finally` xóa `SecurityContextHolder` sau mỗi lượt để không rò context sang lần publish tiếp theo khi thread được dùng lại.

Đây là một ví dụ **minh họa cơ chế**, không phải quy trình đăng nhập. Việc tự tạo token authenticated bằng code như trên chỉ phù hợp trong demo hoặc test kiểm soát. Production cần xác thực request/message bằng bộ lọc, identity provider, service account hoặc cơ chế được hệ thống phê duyệt.

**Lưu ý về phạm vi:** mã minh họa kiểm tra authority toàn cục. Trong hệ thống thật phải bổ sung object-level authorization với `orderId`, tenant, trạng thái và quy tắc dữ liệu như phần 5. Nó cũng không đưa ra bảo đảm bền vững hay transactional delivery.

## 7. Vì sao không chỉ đặt @PreAuthorize trực tiếp lên @EventListener?

Có thể gặp cách viết:

~~~java
@EventListener
@PreAuthorize("hasAuthority('ORDER_NOTIFY')")
public void onOrderPlaced(OrderPlaced event) {
    // Nhận event và làm side effect ngay tại method.
}
~~~

*Đây là đoạn mã minh họa, không phải chương trình độc lập.*

Cách này **có thể** được chặn bởi method-security interceptor khi listener bean/proxy được đăng ký và phương thức được gọi qua proxy đúng cách. Tuy nhiên, có những rủi ro cần kiểm tra:

- Hạ tầng event listener và method security đều sử dụng cơ chế proxy/adapter; class, interface, method visibility, final/private method và thứ tự bean post-processing có thể làm cấu hình không hoạt động như mong muốn.
- Nếu mã nghiệp vụ khác gọi một helper nội bộ bằng `this.someSecuredMethod()`, self-invocation có thể bỏ qua security proxy.
- Quyền bị đặt riêng trên listener nhưng cùng side effect có thể được thực hiện từ REST endpoint/job khác không đi qua listener.
- Test chỉ trực tiếp gọi `listener.onOrderPlaced(...)` không tái hiện chính xác event dispatch/proxy behavior.

**Khuyến nghị thực tế:** listener nên chuyển thông tin sự kiện vào **application service được bảo vệ**, nơi quyền gắn với chính thao tác nhạy cảm. Test qua `ApplicationContext` và quan sát trạng thái dữ liệu thực để chắc rằng denial chặn side effect.

Không coi cách viết trực tiếp trên listener là “luôn không hoạt động”; điểm cần đánh giá là **lời gọi thật có đi qua proxy đang áp dụng advisor hay không**.

## 8. @Async và executor: SecurityContext có tự được chuyển không?

Với chiến lược mặc định, `SecurityContextHolder` dùng ngữ cảnh gắn với thread. Nếu chuyển listener sang thread pool, giá trị đang có trên publisher thread **không tự đi theo worker**:

~~~text
Publisher request thread                    Executor worker
------------------------                    ---------------------------
Authentication=alice
    |
    | publishEvent(OrderPlaced)
    |       |
    |       +-- submit task ----------------> @EventListener(...)
    |                                        SecurityContextHolder:
    |                                        - co the khong co Authentication
    |                                        - hoac nhan context cu neu cleanup sai
    |
    +-- request ket thuc
~~~

Hai cách thường dùng để chuyển sang async:

1. Cấu hình `SimpleApplicationEventMulticaster` dùng `TaskExecutor`.
2. Đánh dấu một method listener bằng `@Async` và bật `@EnableAsync`.

**Hai executor có thể khác nhau.** Nếu listener dùng `@Async("emailExecutor")` nhưng propagation lại được cài trên executor của multicaster tên `eventExecutor`, context có thể mất ở chặng `emailExecutor`.

Spring Security có những wrapper như:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextExecutor`.
- `DelegatingSecurityContextAsyncTaskExecutor`.
- `DelegatingSecurityContextExecutorService` và các biến thể liên quan.

Các wrapper này giúp thiết lập `SecurityContext` khi task chạy và dọn hoặc khôi phục trạng thái phù hợp sau khi task kết thúc. Cần chọn **capture context lúc submit** hay dùng **service identity cố định** theo đúng yêu cầu nghiệp vụ.

### 8.1. Minh họa cấu hình executor có SecurityContext propagation

~~~java
@Bean(name = "securedEventExecutor")
AsyncTaskExecutor securedEventExecutor() {
    ThreadPoolTaskExecutor delegate =
            new ThreadPoolTaskExecutor();
    delegate.setCorePoolSize(2);
    delegate.setMaxPoolSize(4);
    delegate.setQueueCapacity(100);
    delegate.setThreadNamePrefix("secure-events-");
    delegate.initialize();

    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}

@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("securedEventExecutor") AsyncTaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

*Đây là **cấu hình tích hợp minh họa**, không phải mã độc lập: cần các import `@Bean`, `@Qualifier`, `AsyncTaskExecutor`, `ThreadPoolTaskExecutor`, `DelegatingSecurityContextAsyncTaskExecutor`, `SimpleApplicationEventMulticaster` và một bean configuration thích hợp. Trong production, quản lý lifecycle/shutdown của executor một cách rõ ràng; khi dùng Spring Boot nên cân nhắc bean executor được container quản lý thay vì tự khởi tạo mà không có cơ chế đóng.*

Với constructor không truyền `SecurityContext` cố định, wrapper sử dụng security context tương ứng lúc task được submit. Với constructor truyền một context cố định, task có thể chạy dưới cùng identity cho mọi lần submit — thích hợp trong một số background-service use cases nhưng **rất nguy hiểm nếu service account có quyền quá rộng**.

**Propagation là truyền một snapshot/tham chiếu ngữ cảnh để thực thi; không phải xác thực lại người dùng.** Nếu tài khoản bị khóa hoặc quyền thay đổi sau khi task được submit, context đã capture có thể trở nên cũ. Các thao tác nhạy cảm có độ trễ dài nên có chính sách kiểm tra quyền tại thời điểm xử lý, không chỉ ở lúc publish.

### 8.2. Vì sao không dùng InheritableThreadLocal cho pool?

`SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` không phải giải pháp tổng quát cho thread pool: nó có thể kế thừa khi tạo thread mới nhưng executor thường tái sử dụng worker đã tồn tại từ request trước. Điều này làm rủi ro rò danh tính, nhầm quyền và khó kiểm soát cleanup. Ưu tiên wrapper được Spring Security hỗ trợ hoặc thiết kế ủy quyền service-to-service rõ ràng.

### 8.3. Không phải lỗi nào cũng đi ngược tới publisher

Listener đồng bộ bị từ chối có thể ném exception qua `publishEvent(...)` như demo. Với listener `@Async` hoặc multicaster executor, lỗi quyền có thể chỉ xuất hiện trên worker; caller đã kết thúc và không nhận exception trực tiếp.

Dùng `AsyncUncaughtExceptionHandler` khi thích hợp cho `@Async void`, và `ErrorHandler` của multicaster cho các callback được dispatch qua multicaster. Nếu yêu cầu retry/durable processing thì cần hạ tầng lưu trữ, queue/outbox/inbox và idempotency; **không nuốt AccessDeniedException rồi đánh dấu event là đã xử lý thành công**.

## 9. Event được xử lý sau commit: quyền được đánh giá lúc nào?

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho phép listener chỉ phản ứng sau transaction commit phù hợp:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void whenOrderCommitted(OrderPlaced event) {
    securedNotificationService.sendNotification(event);
}
~~~

*Đây là đoạn tích hợp minh họa với Spring transaction infrastructure; cần import `@TransactionalEventListener` và `TransactionPhase`. Không phải ví dụ runnable độc lập.*

Có ba trục thời gian khác nhau:

1. **Authorization lúc nhận request**: người dùng có quyền đặt đơn không?
2. **Commit dữ liệu nghiệp vụ**: thay đổi đơn có thật sự được ghi thành công không?
3. **Authorization lúc thực thi side effect**: actor hoặc service đang xử lý event có được phép gửi thông báo/truy cập dữ liệu không?

Với callback đồng bộ cùng thread, security context có thể còn hiện diện lúc after-commit. Nhưng nếu việc thực thi được chuyển sang executor, kéo dài hoặc replay sau khi process restart, không thể giả định `Authentication` của request cũ vẫn tồn tại hay còn hiệu lực.

Cần chọn chính sách rõ ràng:

- **User-delegated action**: xác thực actor và kiểm tra quyền trên tài nguyên; đối với tác vụ chạy trễ có thể cần xác thực lại/truy vấn current permissions.
- **System-owned business reaction**: thao tác do chính hệ thống phải làm khi fact đã xảy ra, ví dụ gửi receipt theo yêu cầu bắt buộc của nghiệp vụ; chạy dưới **service principal giới hạn quyền**, không giả vờ đó là session của khách hàng.
- **Audit attribution**: lưu `actorId` đã xác minh lúc tạo nghiệp vụ để ghi ai khởi phát, nhưng không dùng nó như token ủy quyền cho tác vụ sau này.

Đừng suy diễn rằng dùng `AFTER_COMMIT` làm event được giao chắc chắn sau crash. Nếu nghiệp vụ không được phép mất event sau commit, cân nhắc **transactional outbox** và policy quyền rõ ràng ở consumer.

## 10. ActorId trong payload và dữ liệu đáng tin cậy

Đưa `actorId`, `tenantId`, `correlationId` vào event có lợi cho audit/routing. Nhưng ý nghĩa bảo mật khác nhau:

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        String actorId,
        String tenantId,
        String correlationId) {
}
~~~

*Đoạn record minh họa; bản thân record không xác thực bất cứ trường nào.*

| Trường | Công dụng đúng | Không được suy diễn |
| --- | --- | --- |
| `eventId` | Định danh occurrence, hỗ trợ dedup và audit. | Có event ID là có quyền thực hiện side effect. |
| `actorId` | Quy trách nhiệm ai khởi tạo fact **nếu đã được xác minh ở producer**. | Chuỗi actorId chứng minh caller hiện tại là actor đó. |
| `tenantId` | Phân vùng dữ liệu/routing sau khi đã kiểm tra nguồn. | TenantId trong payload đủ để cho phép truy cập mọi dữ liệu tenant. |
| `correlationId` | Kết nối log/event cùng workflow. | Correlation ID là authentication/authorization token. |
| `claimedRole` | Chỉ là một claim nếu có; cần kiểm chứng provenance. | Chuỗi `ADMIN` trong payload tương đương authority đáng tin. |

Nếu event đến từ **broker bên ngoài, đối tác hoặc boundary khác**, cần xác thực source (mTLS/ACL/authenticated producer), xác minh integrity khi thiết kế yêu cầu, validate schema và áp dụng quyền cho thao tác trên dữ liệu nội bộ. Không dùng `@EventListener(condition)` như công cụ chứng minh nguồn đáng tin.

Nếu event trong cùng JVM xuất phát từ một service chưa có kiểm tra quyền đầu vào, “nội bộ” cũng không làm nó tự an toàn. **Bảo vệ ứng dụng ở nơi tất cả đường gọi hội tụ**, thường là application service thực hiện thay đổi tài nguyên.

## 11. Quyền của người dùng khác quyền của background service

Một quy trình dài có thể bắt đầu từ request của khách hàng nhưng kết thúc bằng consumer chạy lúc nửa đêm. Có ba lựa chọn kiến trúc thường gặp:

### 11.1. Tiếp tục xử lý dưới danh tính người dùng

Dùng khi policy thực sự yêu cầu acting-on-behalf-of, có token/ủy quyền hợp lệ và hành vi hủy quyền rõ ràng. Không đơn giản lưu cả `Authentication` object vào database/JSON rồi tái sử dụng vô thời hạn.

Nếu cần ủy quyền cho một tác vụ dài, dùng cơ chế delegation/credential có phạm vi và thời hạn thích hợp, lưu an toàn, kiểm tra lại tại thời điểm thực hiện. Danh tính người dùng có thể bị khóa hoặc quyền có thể đã bị thu hồi giữa lúc publish và consume.

### 11.2. Chạy với service identity

Dùng khi event phản ánh một fact đã commit và hệ thống phải thực hiện tác vụ nội bộ. Ví dụ gửi email xác nhận, cập nhật projection hoặc truyền message sang service khác. Service identity cần **least privilege**: chỉ có quyền đúng loại thao tác, không mặc định `ROLE_ADMIN`.

Đừng chia sẻ một service principal có toàn quyền cho mọi event listener; nếu một listener bị lỗi/chiếm quyền, phạm vi ảnh hưởng sẽ lớn. Có thể tách các service identities theo loại tác vụ hoặc trust boundary.

### 11.3. Không có quyền thì từ chối rõ ràng

Đây là lựa chọn mặc định cho hành động không có policy thích hợp. Với event có thể retry, cần phân biệt:

- **Không có authentication hợp lệ**: fail closed, ghi nhận lỗi theo policy.
- **Authenticated nhưng thiếu authority**: access denied, không thực hiện side effect.
- **Quyền tạm chưa xác định do service policy lỗi**: xử lý theo chính sách an toàn, không biến lỗi truy vấn policy thành allow.
- **Actor bị thu hồi quyền**: quyết định nghiệp vụ có nên dừng, chuyển duyệt, hoặc để một system-owned workflow tiếp tục dưới principal khác, nhưng không âm thầm vượt quyền.

## 12. Tính bất biến, data minimization và không rò thông tin

Payload nên chứa đúng dữ liệu phục vụ listener. Đừng gửi toàn bộ `UserEntity`, `Authentication`, JWT hay thông tin nhạy cảm vào event chỉ để downstream “có đủ context”. Những rủi ro:

- Đối tượng mutable hoặc JPA lazy proxy có thể thay đổi giữa lúc publish và xử lý async.
- Một event fan-out đến nhiều listener làm tăng số nơi dữ liệu cá nhân xuất hiện.
- Log/trace có thể ghi payload và vô tình lộ email, số điện thoại, access token, địa chỉ, thông tin thanh toán.
- Dữ liệu lưu lâu ở outbox/broker có thể vi phạm retention hoặc mục đích xử lý ban đầu.
- Dữ liệu nhạy cảm có thể bị consumer không đúng privilege truy cập nếu authorization chỉ nằm ở producer.

Khuyến nghị:

1. Dùng **ID, tenant key đã xác minh và snapshot tối thiểu** thay vì entity graph.
2. Lấy thêm dữ liệu từ repository/service qua API được bảo vệ khi thực sự cần.
3. Mã hóa/che trường nhạy cảm, thiết kế retention và quyền đọc event store/broker.
4. Không ghi token, password, private key vào event, MDC hoặc tracing baggage.
5. Tránh coi “có access tới message topic” là quyền đọc mọi dữ liệu nội dung; topic ACL và data-level authorization là hai lớp khác nhau.

Khi cần gửi email theo event, chỉ một service được cấp quyền truy cập địa chỉ người nhận và template; các listener về metric có thể chỉ cần event type, event ID và trạng thái tổng hợp.

## 13. Xử lý lỗi phân quyền, transaction và side effect

Trong listener đồng bộ, `@PreAuthorize` từ chối lời gọi service trước khi side effect được thực hiện **trong method được bảo vệ**. Nhưng có một lưu ý quan trọng: nếu một listener khác đã chạy trước và thay đổi dữ liệu, lỗi quyền của listener sau không tự undo tất cả tác vụ trước.

Ví dụ:

~~~text
OrderPlaced
  |
  +--> AuditListener writes audit row     [có thể đã xảy ra]
  |
  +--> SecuredNotificationService
           |
           +--> @PreAuthorize fails       [không gửi email]
  |
  +--> OtherListener                     [có thể chưa được chạy]
~~~

Nếu phát event trong `@Transactional` hiện hành và listener đồng bộ tham gia transaction, exception chưa được xử lý có thể khiến transaction rollback theo quy tắc transaction manager. Tuy nhiên gửi HTTP, email, message ra ngoài DB **không tự rollback được** chỉ vì transaction bị rollback.

Nếu muốn “đơn đã commit thì gửi thông báo, không mất sự kiện”, hãy cân nhắc:

- Ghi **transactional outbox** cùng transaction với thay đổi đơn.
- Worker gửi thông báo từ outbox theo queue/retry policy.
- Consumer kiểm tra quyền dưới service identity phù hợp và bảo vệ object/tenant.
- Dùng `eventId`/idempotency key để tránh side effect trùng khi retry.
- Phân loại lỗi **authorization denied** là lỗi policy/tenant hoặc lỗi cấu hình đáng điều tra, không retry vô hạn như lỗi mạng tạm thời.

**Không dùng một listener `@TransactionalEventListener(AFTER_COMMIT)` như lời hứa bền vững tuyệt đối**: callback trong memory không tự có durable delivery nếu tiến trình chết sau commit.

## 14. @EventListener(condition), @PreAuthorize và @TransactionalEventListener

Ba annotation này giải quyết ba câu hỏi khác nhau:

| Cơ chế | Mục tiêu | Khi nào đánh giá? | Không thay thế được |
| --- | --- | --- | --- |
| `@EventListener(condition=...)` | Lọc loại/value event phù hợp | Khi hạ tầng event chuẩn bị gọi handler | Authentication, object authorization. |
| `@PreAuthorize(...)` | Chặn method khi actor không được phép | Trước method body qua method-security proxy | Validation đầu vào hoặc đảm bảo event đã commit. |
| `@TransactionalEventListener(phase=...)` | Gắn listener vào pha transaction | Theo trạng thái transaction synchronization | Quyền truy cập, durable delivery, security context async. |

Ví dụ:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#p0.status() == 'CONFIRMED'")
public void onConfirmed(OrderConfirmed event) {
    securedService.handleConfirmed(event);
}
~~~

*Đoạn tích hợp minh họa; `OrderConfirmed`/`securedService` do ứng dụng định nghĩa. Phải có transaction synchronization thích hợp; Spring không tự tạo quyền dựa vào status `CONFIRMED`.*

Ở đây condition chọn event thích hợp, phase chọn thời điểm, còn `securedService` phải tự bảo vệ thao tác. Nếu event không có transaction và `fallbackExecution=false` (mặc định), listener có thể không chạy **dù điều kiện SpEL đúng và actor có quyền**.

## 15. Kiểm thử quyền thật: đừng chỉ assert rằng listener được gọi

Một bộ kiểm thử security cho event listener phải bao gồm **actor, event, method interceptor, dữ liệu và đường thực thi**.

### 15.1. Test cơ bản

- Actor có `ORDER_NOTIFY` → protected service được thực thi.
- Actor chỉ có `ORDER_VIEW` → side effect không được thực hiện.
- Event mang `claimedRole="ADMIN"` nhưng actor thiếu quyền → vẫn bị từ chối.
- Không có `SecurityContext` → xử lý theo fail-closed policy của hệ thống.
- Actor đủ authority toàn cục nhưng sai tenant/order owner → bị chặn tại object policy.
- Có quyền với đơn này nhưng không có quyền với đơn khác → không được “đi ké” ID trong event.
- Service được gọi từ REST/scheduler/CLI → kiểm tra quyền vẫn có hiệu lực.

### 15.2. Test proxy và cấu hình

- Có `@EnableMethodSecurity` và bean được Spring quản lý.
- Protected service là dependency **được inject từ context**, không phải instance tự tạo bằng `new` bên ngoài Spring.
- Lời gọi thật đi qua proxy: không self-invocation.
- Với event dispatch, test bằng `context.publishEvent(...)` để đảm bảo listener được đăng ký.
- Test cả assertion về **không có side effect**, không chỉ kiểm tra có exception.
- Nếu dùng `@PreAuthorize` với method parameter names, bảo đảm metadata compiler đúng hoặc dùng cách binding rõ ràng được hỗ trợ.

### 15.3. Test async, retry và cleanup

- Không cấu hình propagation: worker không được tự mang user identity từ publisher.
- Có propagation hợp lệ: worker nhận đúng context cần thiết, không nhận của request trước.
- Cleanup trong `finally` để thread pool không rò principal/tenant.
- Quyền bị thu hồi trước khi job xử lý: policy recheck cho kết quả đúng.
- Listener ném `AccessDeniedException` trên worker: lỗi được quan sát và không đánh dấu success giả.
- Nếu event được giao lại, idempotency ngăn phát thông báo nhiều lần.
- Nếu quyền tenant thay đổi, consumer không gửi dữ liệu sang tenant cũ từ event không được xác thực.

Dùng `CountDownLatch`, await có timeout hoặc các test utilities thích hợp khi kiểm thử async; không dựa vào `Thread.sleep(100)` rồi kỳ vọng task đã kết thúc. Với Spring Security test, `@WithMockUser` hữu ích để tạo Authentication cho một số integration tests, nhưng cần chắc rằng context được thiết lập ở **thread chạy code thực sự**.

### 15.4. Nhận biết lỗi “auth không có” khác “không đủ quyền”

Một hệ thống có thể ném `AuthenticationCredentialsNotFoundException` khi thiếu authentication, hoặc `AccessDeniedException` khi actor có Authentication nhưng không đủ quyền. Các đường exception phụ thuộc cấu hình bảo mật/method interceptor; không giả định mọi lỗi đều cùng một lớp.

Với listener async, những lỗi đó có thể chỉ thấy ở executor. Test phải kiểm chứng error handling và side effect state, không chỉ gọi `publisher.publishEvent(...)` rồi assert không có exception.

## 16. Vận hành: log, audit, metric và quyền truy cập dữ liệu

Khi xử lý event có dữ liệu nhạy cảm, quan sát lỗi bảo mật cần có các trường hữu ích nhưng không lộ bí mật:

| Trường | Cách dùng |
| --- | --- |
| `eventType`, `eventId` | Truy vết event và xử lý trùng. |
| `correlationId` | Liên hệ các bước cùng workflow. |
| `principalId` hoặc subject đã rút gọn | Ai đang được xác thực ở thời điểm xử lý, khi policy cho phép ghi. |
| `actorId` của event | Ai khởi phát fact, **chỉ khi provenance đã được kiểm tra**. |
| `resourceType` | Loại tài nguyên (ORDER, PAYMENT, PROFILE). |
| `tenantId` | Có thể hữu ích cho audit nhưng phải cân nhắc privacy. |
| `authorizationOutcome` | `GRANTED` / `DENIED` / `ERROR`. |
| `policyName` / `action` | Quy tắc nào được áp dụng. |

Không ghi access token, password, raw JWT hoặc toàn bộ danh sách authorities vào log nếu không có lý do và kiểm soát truy cập. Với metric, các giá trị duy nhất như `eventId`, `userId`, `correlationId` không nên làm low-cardinality tags; dùng action, event type, listener và outcome.

Một deny cần được ghi nhận đủ để điều tra, nhưng **không tiết lộ chi tiết sự tồn tại của tài nguyên hoặc thông tin nhạy cảm** cho caller không đủ quyền. Thông báo lỗi công khai có thể chung hơn log nội bộ đã được bảo vệ.

Đối với broker/outbox, quản trị truy cập topic/queue, consumer identity, bí mật của credential và thời gian lưu là một phần của bảo mật event-driven, không phải nhiệm vụ riêng của listener.

## 17. Những sai lầm thường gặp

1. **Xem `@EventListener` là security boundary.** Được Spring gọi không đồng nghĩa được phép đọc dữ liệu/ghi DB/gửi email.
2. **Dùng `claimedRole` hoặc `actorId` từ payload để cấp quyền.** Những trường này có thể bị giả mạo và chỉ có giá trị khi provenance được xác minh.
3. **Tưởng `@EventListener(condition)` là authorization.** Nó chỉ là bộ lọc event, không phải kiểm tra principal và object permissions.
4. **Chỉ bảo vệ REST controller.** Listener/scheduler/message consumer có thể gọi service khác đường HTTP; cần bảo vệ tại service boundary.
5. **Có `@PreAuthorize` nhưng quên `@EnableMethodSecurity`.** Annotation có thể không tạo ra interceptor.
6. **Self-invocation hoặc tạo bean bằng `new`.** Có thể bỏ qua proxy và bỏ qua bảo vệ method.
7. **Bật `@Async` rồi giả định authentication tự đi theo thread.** `SecurityContextHolder` thường thread-bound; cần propagation hoặc service identity.
8. **Dùng `MODE_INHERITABLETHREADLOCAL` cho thread pool.** Không phải cơ chế propagation tin cậy trong môi trường tái sử dụng worker.
9. **Quên cleanup SecurityContext trên worker.** Nguy cơ rò identity/tenant giữa các request và task.
10. **Capture context người dùng rồi dùng mãi cho job dài ngày.** Quyền có thể thay đổi, cần expiry/revalidation hoặc principal khác.
11. **Dùng service account toàn quyền để chữa lỗi denied.** Vi phạm least privilege và làm tăng ảnh hưởng khi handler bị lỗi.
12. **Chỉ check authority toàn cục, bỏ qua object/tenant access.** Actor có quyền gửi email chưa chắc được truy cập đơn của tenant khác.
13. **Cho rằng `AFTER_COMMIT` tự bảo đảm retry sau crash.** Callback trong memory không phải durable messaging.
14. **Bắt AccessDeniedException rồi coi event xử lý thành công.** Side effect không xảy ra nhưng hệ thống có thể đánh dấu success sai.
15. **Giả định exception trong listener async sẽ quay lại publisher.** Cần error handler/monitoring riêng.
16. **Truyền nguyên JWT hoặc Authentication object qua event.** Dễ lộ bí mật, tăng coupling và tạo quyền stale khi replay.
17. **Dùng correlation ID hay event ID như khóa phân quyền.** Chúng giúp truy vết/dedup, không chứng minh danh tính.
18. **Để kiểm tra quyền sau khi đã thực hiện side effect.** Authorization phải xảy ra trước thao tác nhạy cảm.
19. **Quên kiểm tra đường gọi thay thế của cùng service.** Policy nên nằm ở nơi mọi caller hội tụ.
20. **Bỏ qua tác dụng phụ đã hoàn thành ở listener khác khi một listener bị denied.** Event fan-out không tự rollback email/HTTP đã gửi.

## 18. Checklist thiết kế cho production

Trước khi đưa một listener có side effect vào môi trường thật, hãy tự xác nhận:

1. **Event contract**: event mô tả fact nào, field nào đáng tin, ai là producer?
2. **Trust boundary**: nguồn event thuộc cùng JVM hay qua broker/HTTP/đối tác? Đã xác thực source chưa?
3. **Authorization boundary**: service nào thực hiện side effect; tất cả đường gọi có đi qua policy không?
4. **Method security**: đã bật `@EnableMethodSecurity`, test proxy và method accessibility chưa?
5. **Object scope**: tenant, owner, data sensitivity và trạng thái hiện tại có được kiểm tra không?
6. **Execution identity**: xử lý dưới user hay service principal? Lúc nào xác thực/ủy quyền lại?
7. **Thread hop**: multicaster hoặc `@Async` dùng executor nào, có propagation/cleanup phù hợp không?
8. **Transaction**: publish trước commit, sau commit hay từ outbox? Exception có thể rollback đến đâu?
9. **Error semantics**: denied được log/metric/retry hay báo thất bại thế nào?
10. **Idempotency**: một event retry có thể làm side effect hai lần không?
11. **Data minimization**: payload/log có chứa token, PII hoặc entity mutable không?
12. **Test matrix**: allow, deny, no-auth, wrong tenant, async, replay và startup/shutdown đã được phủ chưa?

Nếu chưa có câu trả lời cho một mục quan trọng, listener đó có thể hoạt động trong demo nhưng vẫn gây rủi ro bảo mật khi chạy production.

## 19. Bài tập tự kiểm tra

**Câu 1.** Một listener nhận được `OrderPlaced` có `claimedRole="ADMIN"`. Có thể dùng trường đó để bỏ qua kiểm tra quyền không?

**Đáp án:** Không. Đây là dữ liệu event, không phải `Authentication` được xác thực. Quyền phải đến từ cơ chế trusted security/policy được kiểm tra.

**Câu 2.** Trong ví dụ phần 6, vì sao `bob` không tạo dòng `SENT ORD-8`?

**Đáp án:** Dù event của Bob mang `claimedRole="ADMIN"`, authentication hiện hành chỉ có `ORDER_VIEW`. Service proxy áp dụng `@PreAuthorize("hasAuthority('ORDER_NOTIFY')")` và chặn trước method body.

**Câu 3.** Vì sao chỉ bảo vệ controller bằng HTTP authorization chưa đủ cho event listener?

**Đáp án:** Cùng protected service có thể được gọi từ event, scheduler, CLI hoặc message consumer, không đi qua cùng đường HTTP. Bảo vệ tại method/domain service boundary giúp các đường gọi đều phải tuân policy.

**Câu 4.** Một listener `@Async` không đọc được `SecurityContextHolder` của request. Đây có chứng minh user chưa đăng nhập không?

**Đáp án:** Không. Context thường gắn với thread; worker có thể không được truyền authentication. Cần propagation hợp lệ hoặc thiết kế chạy dưới service identity.

**Câu 5.** Có nên copy một `Authentication` của user vào event rồi lưu trong broker để xử lý sau 3 ngày không?

**Đáp án:** Không phải lựa chọn mặc định an toàn. Credentials/authorities có thể hết hạn, thay đổi hoặc bị lộ. Lưu audit attribution tối thiểu, chọn chính sách delegation/revalidation hoặc service principal phù hợp.

**Câu 6.** `@TransactionalEventListener(AFTER_COMMIT)` có tự cấp quyền cho method xử lý không?

**Đáp án:** Không. Nó xác định mốc transaction, còn authorization phải được kiểm tra độc lập.

**Câu 7.** Một actor có authority gửi notification, nhưng đơn thuộc tenant khác. Có nên cho qua chỉ vì `hasAuthority('ORDER_NOTIFY')` đúng?

**Đáp án:** Không. Cần object/tenant-level access control đối chiếu với dữ liệu đáng tin.

**Câu 8.** Listener đồng bộ ném `AccessDeniedException` sau khi một listener khác đã gọi API thanh toán. Exception có tự thu hồi tác dụng phụ qua HTTP không?

**Đáp án:** Không. Side effect ngoài DB thường không tự rollback. Cần thiết kế transaction boundary và compensation/idempotency phù hợp.

**Câu 9.** Vì sao `SecurityContextHolder.clearContext()` trong `finally` quan trọng?

**Đáp án:** Thread có thể được dùng lại; nếu không cleanup, principal/authorities của request trước có thể rò sang xử lý tiếp theo.

**Câu 10.** Tại sao method security cần test qua Spring context/proxy thay vì chỉ gọi thẳng Java method?

**Đáp án:** Interceptor `@PreAuthorize` hoạt động qua AOP proxy. Lời gọi trực tiếp lên object được tạo bằng `new` hoặc self-invocation có thể bỏ qua lớp kiểm tra này.

## Tài liệu tham khảo

- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `AuthorizationManager`, proxy và kiểm soát quyền theo tham số.
- [Spring Security Reference — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): `SecurityContextHolder` gắn với thread, `DelegatingSecurityContextRunnable`, executor wrappers và cleanup.
- [Spring Security Reference — SecurityContextHolder](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): cách lưu và lấy authentication.
- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener` và giới hạn xử lý async.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, `AFTER_COMMIT` và `fallbackExecution`.
- [Spring Boot 3.5 Reference — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): vòng đời ứng dụng dùng trong ví dụ; ứng dụng minh họa chạy `WebApplicationType.NONE`.
