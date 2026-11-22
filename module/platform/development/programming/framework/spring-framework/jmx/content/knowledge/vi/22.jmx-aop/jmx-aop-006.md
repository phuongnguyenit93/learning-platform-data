# Spring Framework JMX — Security proxy và quyền gọi operation

## 1. Bài toán: một operation JMX có thật sự được bảo vệ bởi Spring Security?

Spring Framework JMX cho phép công cụ vận hành đọc trạng thái hoặc gọi operation trên một bean thông qua \`MBeanServer\`. Khi ứng dụng dùng Spring AOP và Spring Security method authorization, một câu hỏi rất quan trọng xuất hiện:

**Nếu một method được bảo vệ bởi \`@PreAuthorize\`, liệu lời gọi JMX vào \`@ManagedOperation\` có tự động phải vượt qua cùng kiểm tra quyền?**

Không nên mặc định câu trả lời là có.

Spring Security method authorization trong mô hình proxy-based hoạt động khi lời gọi **đi qua Spring AOP proxy** có advice bảo mật. Trong khi đó, JMX exporter có thể lấy metadata từ target class và đăng ký MBean theo cách mà đường thực thi thực tế không hoàn toàn giống lời gọi nghiệp vụ thông thường. Nếu một operation được gọi trực tiếp trên target hoặc qua một adapter bỏ qua proxy, method-security interceptor có thể không chạy.

Đồng thời, một lời gọi JMX remote thường bắt đầu từ thread/connector context khác HTTP request. Một user đã xác thực với JMX connector chưa chắc được biến thành \`Authentication\` trong \`SecurityContextHolder\` của Spring Security.

Vì vậy, cần phân biệt **hai lớp bảo vệ độc lập**:

1. **JMX transport/server security:** ai được phép kết nối JMX và thao tác trên MBean.
2. **Spring method security:** lời gọi method Java có đi qua security proxy và có Authentication phù hợp hay không.

Mục tiêu của bài học là thiết kế management API không bị bypass kiểm tra quyền, bảo vệ operation nguy hiểm và kiểm chứng hành vi theo đường gọi JMX thật.

\`\`\`text
JConsole / JMX client
       |
       v
JMX Connector (authentication / authorization / TLS)
       |
       v
MBeanServer.invoke(ObjectName, operation, parameters, signature)
       |
       v
Spring MBeanExporter / ModelMBean adapter
       |
       +-- path A: call target directly --> possible AOP bypass
       |
       +-- path B: call Spring AOP proxy --> method security advice
                                                |
                                                v
                                           business method
\`\`\`

**Ý cốt lõi:** xuất hiện annotation bảo mật trong source code không đủ chứng minh JMX invocation đã được authorize. Cần biết object thật được MBean invoker gọi, đường proxy và identity ở thread thực hiện operation.

## 2. Thành phần liên quan

| Thành phần | Vai trò |
|---|---|
| \`@ManagedResource\` | Đánh dấu Spring bean là JMX-managed resource |
| \`@ManagedOperation\` | Công bố method thành JMX operation |
| \`MBeanExporter\` | Đăng ký MBean vào \`MBeanServer\` |
| \`MBeanServer.invoke\` | Điểm vào của client để gọi operation |
| Spring AOP proxy | Đối tượng trung gian áp dụng interceptor/advice |
| \`@EnableMethodSecurity\` | Bật cơ chế method security trong Spring Security hiện đại |
| \`@PreAuthorize\` | Khai báo điều kiện authorization trước khi gọi method |
| \`Authentication\` | Thông tin principal và authorities trong Spring Security |
| \`SecurityContextHolder\` | Nơi lưu security context theo chiến lược cấu hình, mặc định gắn với thread |
| JMX remote connector | Đường kết nối từ client đến MBeanServer |
| Management facade | Bean chuyên expose JMX và chuyển lời gọi tới service nghiệp vụ qua proxy |

Ba khái niệm dễ nhầm:

- **MBean registration:** server có ObjectName và operation được expose.
- **JMX authorization:** quyền ở connector/MBeanServer hoặc lớp kiểm soát riêng cho client.
- **Spring method authorization:** security interceptor kiểm tra \`Authentication\` khi lời gọi method đi qua proxy.

Chúng có liên quan nhưng **không tự động thay thế nhau**.

## 3. Java method, AOP proxy và JMX operation

Giả sử có service:

\`\`\`java
package com.example.orders;

import org.springframework.security.access.prepost.PreAuthorize;

public class OrderAdministrationService {
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // Retry các đơn hàng bị lỗi.
    }
}
\`\`\`

Nếu Spring Security method authorization đã bật và caller lấy Spring bean thông qua AOP proxy, interceptor có thể kiểm tra quyền trước khi method chạy.

\`\`\`text
Spring caller --> proxy --> authorization advice --> target method
\`\`\`

Nhưng JMX client chỉ biết MBean và operation:

\`\`\`java
server.invoke(
    objectName,
    "retryFailedOrders",
    new Object[0],
    new String[0]
);
\`\`\`

JMX contract không quy định rằng server phải tìm Spring AOP proxy, lấy security context từ HTTP request hay kiểm tra biểu thức \`@PreAuthorize\`.

Thực tế phụ thuộc vào cơ chế MBean được export:
- Bean reference được exporter giữ là proxy hay target?
- MBean metadata được dựng từ interface hay target class?
- Operation có tồn tại trên proxy?
- Adapter có dùng đường gọi giữ nguyên các AOP interceptors không?
- Có \`Authentication\` hợp lệ trong thread chạy lời gọi JMX không?

Vì vậy, một thiết kế an toàn phải chủ động quyết định security boundary thay vì trông chờ annotation trên implementation tự được áp dụng.

## 4. Trường hợp nguy hiểm: JMX export target bỏ qua proxy

Ví dụ đơn giản:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=OrderAdmin,name=primary"
)
public class OrderAdminTarget {

    @ManagedOperation(description = "Retry failed orders")
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // ...
    }
}
\`\`\`

Nếu operation cuối cùng được gọi qua proxy có method-security advisor, lời gọi có thể được kiểm soát bởi \`@PreAuthorize\`. Nhưng nếu một adapter hoặc cấu hình xuất **target object trực tiếp**, interceptor Spring Security không có cơ hội chạy.

Ví dụ rủi ro về mặt ý tưởng:

\`\`\`java
Object target = ...; // raw object không phải Spring AOP proxy
exporter.setBeans(Map.of(
    "com.example:type=OrderAdmin,name=primary",
    target
));
\`\`\`

Việc class có \`@PreAuthorize\` **không biến raw object thành đối tượng tự thực thi kiểm tra quyền**. Annotation cần hạ tầng method-security cùng invocation path thích hợp.

Vấn đề này không chỉ xảy ra với security:
- \`@Transactional\` cũng có thể bị bypass.
- Retry/caching/logging advice có thể không được gọi.
- Metrics/audit dựa vào AOP proxy có thể không ghi nhận.
- Các rule về self-invocation vẫn áp dụng.

**Không dùng JMX làm con đường vòng qua business-service proxy** chỉ vì muốn gọi method quản trị nhanh hơn.

## 5. JDK dynamic proxy và CGLIB proxy

### 5.1. JDK dynamic proxy

JDK proxy dựa trên interface.

\`\`\`java
public interface OrderMaintenance {
    void retryFailedOrders();
}
\`\`\`

\`\`\`java
public class OrderMaintenanceImpl implements OrderMaintenance {
    @Override
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // ...
    }
}
\`\`\`

Với JDK proxy, client Java thường tương tác qua \`OrderMaintenance\` interface. Method JMX cần gọi qua proxy phải có mặt trong interface mà proxy expose; nếu chỉ có trên implementation class, JMX adapter có thể không gọi đúng qua proxy.

Điều này khác với việc có metadata:
- Annotation JMX có thể được đọc trên target class.
- Nhưng đường invocation phải có method khả dụng trên proxy.
- Nếu metadata công bố một method không gọi được qua proxy, client có thể nhận lỗi invocation.

### 5.2. CGLIB class-based proxy

Class-based proxy là subclass của implementation trong các trường hợp được hỗ trợ. Nó thường giúp expose methods của class rộng hơn JDK proxy, nhưng vẫn có giới hạn:

- \`final\` class không thể được subclass bằng CGLIB thông thường.
- \`final\` method không thể được override để áp dụng proxy advice.
- Private methods không phải điểm interception của Spring proxy-based AOP.
- Self-invocation trong cùng target có thể bypass advice.

Không nên đổi toàn bộ ứng dụng sang CGLIB chỉ để “bảo vệ JMX”. Tốt hơn là tạo management facade và xác định đường gọi business service rõ ràng.

## 6. Thread của JMX và SecurityContext

Trong web application, \`SecurityContextHolder\` thường được đặt bởi security filters theo request.

\`\`\`text
HTTP request -> Security filter chain -> SecurityContext -> Controller -> Service
\`\`\`

Một remote JMX invocation không nhất thiết đi qua HTTP security filter chain:

\`\`\`text
JMX connector thread -> MBeanServer.invoke -> MBean method
\`\`\`

Vì vậy, ngay cả khi JMX connector đã xác thực tài khoản vận hành, \`SecurityContextHolder.getContext().getAuthentication()\` có thể là \`null\` hoặc không phản ánh đúng principal của JMX client.

Hệ quả:
- Nếu method-security proxy có chạy, \`@PreAuthorize\` có thể từ chối vì thiếu Authentication.
- Nếu proxy bị bypass, có thể không có kiểm tra nào từ method security.
- Không được mặc định JMX username và Spring Security principal là cùng một identity.
- Không nên tự tạo Authentication có quyền cao nhất cho **mọi** JMX call chỉ để vượt qua \`@PreAuthorize\`.

Nếu cần tích hợp JMX identity với Spring Security, phải thiết kế một **trusted bridge** xác thực mapping, ràng buộc quyền và quản lý context theo lời gọi một cách rõ ràng. Không xem username truyền trong tham số operation là nguồn danh tính đáng tin cậy.

## 7. Một management facade là ranh giới dễ kiểm soát

Thiết kế khuyến nghị cho ứng dụng có operation quản trị:

\`\`\`text
JMX client
    |
    v
MBeanServer -> OrderJmxManagementFacade (Spring bean)
                    |
             explicit validation + audit
                    |
                    v
          OrderMaintenance interface
                    |
                    v
          Spring Security AOP proxy
                    |
            @PreAuthorize check
                    |
                    v
             business target
\`\`\`

Facade export API nhỏ và rõ ý nghĩa, còn business service được inject qua Spring DI. Điều này giúp tránh việc trực tiếp export implementation class có nhiều method nội bộ.

### 7.1. Service interface

\`\`\`java
package com.example.orders;

public interface OrderMaintenance {
    long getFailedOrderCount();
    void retryFailedOrders();
}
\`\`\`

### 7.2. Service implementation

\`\`\`java
package com.example.orders;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderMaintenanceImpl implements OrderMaintenance {

    @Override
    public long getFailedOrderCount() {
        return 0L; // Thay bằng dữ liệu thực tế.
    }

    @Override
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // Business operation.
    }
}
\`\`\`

Để \`@PreAuthorize\` có hiệu lực, application cần bật Spring Security method authorization và đảm bảo bean được gọi qua proxy, ví dụ:

\`\`\`java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
\`\`\`

Đây là annotation của \`org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity\` trong các phiên bản Spring Security hỗ trợ API đó.

### 7.3. JMX facade

\`\`\`java
package com.example.orders;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary",
    description = "Operational controls for order maintenance"
)
public class OrderJmxManagementFacade {

    private final OrderMaintenance service;

    public OrderJmxManagementFacade(OrderMaintenance service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of failed orders")
    public long getFailedOrderCount() {
        return service.getFailedOrderCount();
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        service.retryFailedOrders();
    }
}
\`\`\`

Spring configuration:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {

    @Bean
    public OrderJmxManagementFacade orderJmxManagementFacade(
            OrderMaintenance service) {
        return new OrderJmxManagementFacade(service);
    }
}
\`\`\`

Khi Spring inject \`OrderMaintenance\` proxy vào facade, lời gọi \`service.retryFailedOrders()\` đi qua proxy, nên method-security advice được thực thi **nếu đúng infrastructure được bật và phương thức nằm trong giao diện được proxy expose**.

Tuy nhiên vẫn phải trả lời câu hỏi **ai tạo Authentication trong JMX thread**. Facade này giúp giữ invocation path; nó không tự chuyển JMX credentials thành Spring Security identity.

## 8. Kiểm soát quyền trực tiếp tại management boundary

Khi JMX được dùng làm control plane riêng, có thể thiết kế lớp authorization dành cho JMX thay vì cố dùng lại security context HTTP.

Ví dụ một chính sách quản trị trừu tượng:

\`\`\`java
public interface ManagementAuthorizer {
    void requirePermission(String permission);
}
\`\`\`

Facade:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary"
)
public class SecuredOrderJmxFacade {

    private final ManagementAuthorizer authorizer;
    private final OrderMaintenance service;

    public SecuredOrderJmxFacade(
            ManagementAuthorizer authorizer,
            OrderMaintenance service) {
        this.authorizer = authorizer;
        this.service = service;
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        authorizer.requirePermission("orders:retry");
        service.retryFailedOrders();
    }
}
\`\`\`

\`ManagementAuthorizer\` trong ví dụ là interface **do ứng dụng định nghĩa**, không phải API có sẵn của Spring. Implementation phải dựa vào identity được xác thực một cách đáng tin cậy ở JMX boundary hoặc trong môi trường thực thi được quản lý.

Nếu không có cách đáng tin cậy để xác định caller, chính sách an toàn thường là **deny by default**, hoặc không expose operation thay đổi trạng thái qua remote JMX.

Không tạo security check dựa trên tham số do caller tự gửi:

\`\`\`java
@ManagedOperation
public void retryFailedOrders(String claimedRole) {
    if ("ADMIN".equals(claimedRole)) {
        // Không an toàn: caller tự khai báo vai trò.
    }
}
\`\`\`

Một client có thể tự truyền \`"ADMIN"\`; đây không phải authorization.

## 9. Quyền của JMX connector khác Spring Security roles

Với remote JMX, server có thể cấu hình:
- Authentication để xác định ai kết nối.
- Authorization ở JMX layer hoặc policy cụ thể.
- Transport protection để bảo vệ credentials và dữ liệu.
- Network restrictions để hạn chế endpoint có thể truy cập.

Các thiết lập này không tương đương một-một với Spring Security authority \`orders:retry\`.

Ví dụ một account JMX có quyền remote management rộng có thể được server cho phép invoke operation, nhưng Spring Security proxy không biết account đó là ai. Ngược lại, một người có quyền admin trong HTTP web UI không tự động có quyền JMX connector.

Nên thiết lập các vai trò vận hành cụ thể:
- **Read-only monitoring:** truy vấn trạng thái/metrics.
- **Runtime configuration:** thay đổi một số attributes có giới hạn.
- **High-impact administration:** thao tác reset, xóa hoặc reload có kiểm soát.
- **Infrastructure administration:** thao tác với connector/server rộng hơn.

Đừng cấp tất cả quyền JMX cho một tài khoản monitoring chỉ để đọc CPU và heap memory.

## 10. ObjectName và operation name không phải quyền

ObjectName chỉ định MBean:

\`\`\`text
com.example.app:type=OrderMaintenance,name=primary
\`\`\`

Operation name chỉ định hành động:

\`\`\`text
retryFailedOrders()
\`\`\`

Hai giá trị này không phải dữ liệu xác thực. Việc một client đoán được ObjectName và tên operation không nên cấp quyền gọi.

Phân quyền cần kiểm soát từ connector/MBeanServer hoặc management facade đáng tin cậy. Tương tự, \`@ManagedOperation(description="Admin only")\` chỉ thêm metadata mô tả; nó không tự chặn caller không có quyền.

Một thiết kế tốt giữ contract JMX nhỏ và dễ audit:
- Tên operation phản ánh hành động cụ thể.
- Chỉ expose operation thật sự cần cho vận hành.
- Không expose methods như \`deleteAllData\` nếu không có chính sách và kiểm soát quyền thích hợp.
- Không cho phép caller gửi Java class name hoặc expression để thực thi code tùy ý.

## 11. Trường hợp self-invocation

Giả sử:

\`\`\`java
public class JobService {

    public void runFromJmx() {
        executePrivilegedTask(); // this.executePrivilegedTask()
    }

    @PreAuthorize("hasAuthority('jobs:execute')")
    public void executePrivilegedTask() {
        // ...
    }
}
\`\`\`

Trong Spring proxy-based AOP, lời gọi từ \`runFromJmx\` tới \`executePrivilegedTask\` trên cùng object thường **không đi qua proxy**. Vì thế method-security advice đặt ở \`executePrivilegedTask\` có thể không chạy.

Nếu \`runFromJmx\` được gọi qua proxy, điều đó không tự biến internal call \`this.executePrivilegedTask()\` thành cuộc gọi qua proxy.

Hướng xử lý:
1. Tách privileged method sang một bean/service khác.
2. Inject service đó vào facade theo interface.
3. Đảm bảo cross-bean call đi qua proxy.
4. Test thực tế rằng caller không đủ quyền bị từ chối.

Không dùng self-injection/AopContext một cách tùy tiện vì làm business code phụ thuộc vào proxy internals và có thể tạo vòng phụ thuộc.

## 12. Security context trong asynchronous operations

Một JMX operation có thể submit công việc sang executor:

\`\`\`java
@ManagedOperation
public void startReindex() {
    executor.execute(() -> indexService.reindex());
}
\`\`\`

Nếu thread JMX có security context, không nên mặc định context được truyền sang worker thread. \`SecurityContextHolder\` mặc định dùng thread-local semantics. Muốn propagate, cần thiết kế có chủ đích bằng các cơ chế Spring Security concurrency phù hợp hoặc một identity nội bộ được kiểm soát.

Điều này càng quan trọng khi:
- Operation JMX chạy bất đồng bộ.
- \`CompletableFuture\` đổi thread.
- Một scheduler thực hiện phần còn lại sau khi lời gọi JMX trả về.
- Audit cần ghi lại caller nguyên thủy và approval context.

Không sao chép \`Authentication\` từ một request ngẫu nhiên vào background job. Phải biết caller identity đến từ đâu, thời hạn và phạm vi ủy quyền.

## 13. Authorization cho operation có tác dụng phụ

Với operation như \`retryFailedOrders\`, \`clearQueue\`, \`resetCounters\`, \`shutdownWorker\`, cần xác định:

| Câu hỏi | Yêu cầu thiết kế |
|---|---|
| Ai được gọi? | Principal/role/permission được xác thực |
| Qua kênh nào? | Local JMX, authenticated remote JMX, hoặc internal management service |
| Hành động ảnh hưởng gì? | Dữ liệu, tính sẵn sàng, tài nguyên, trạng thái runtime |
| Đầu vào hợp lệ là gì? | Validation và giới hạn miền giá trị |
| Có thể lặp lại không? | Idempotency và retry policy |
| Ghi log ra sao? | Audit actor, operation, thời điểm, kết quả; không lộ secrets |
| Làm sao kiểm tra hậu trạng thái? | Read-only attribute/metric hoặc operation status |
| Có giới hạn tần suất không? | Rate limit hoặc operational policy tại boundary |

Ví dụ việc đặt \`@PreAuthorize\` ở service không giải quyết tất cả các câu hỏi trên. JMX endpoint cần được hạn chế bằng network và authentication, operation cần validation, và đường gọi qua security proxy cần được kiểm chứng.

## 14. Kiểm tra proxy thực tế với Spring AOP

Spring cung cấp utility \`AopUtils\`:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderMaintenance");

System.out.println(
    "isAopProxy=" + AopUtils.isAopProxy(bean)
);
System.out.println(
    "isJdkDynamicProxy=" + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "isCglibProxy=" + AopUtils.isCglibProxy(bean)
);
System.out.println(
    "targetClass=" + AopUtils.getTargetClass(bean).getName()
);
\`\`\`

Nếu là JDK proxy, cần xác nhận interface chứa method cần gọi. Nếu là class-based proxy, xác nhận method có thể được proxy intercept. Tuy nhiên, kết quả \`isAopProxy=true\` **không tự chứng minh JMX exporter đang gọi đúng proxy ấy**.

Cần thêm phép thử invocation thật từ \`MBeanServer.invoke\` hoặc client JMX với account/identity đại diện cho người dùng không đủ quyền.

## 15. Xem MBeanInfo trước khi gọi operation

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    for (var op : info.getOperations()) {
        System.out.print(op.getName() + "(");
        for (var param : op.getSignature()) {
            System.out.print(param.getType() + " ");
        }
        System.out.println(")");
    }
}
\`\`\`

Metadata này xác định những operation thực sự được công bố, nhưng **không chứng minh authorization đang hoạt động**. Một operation có thể được hiển thị trong JConsole và vẫn có kiểm tra quyền khi gọi; hoặc ngược lại, bị expose ngoài ý muốn mà không có security interception.

Nếu exporter dùng MBeanServer khác platform server, phải kiểm tra đúng server đã đăng ký bean. Tránh chẩn đoán nhầm vấn đề security khi thực tế client đang kết nối sai registry.

## 16. Cách kiểm thử quyền JMX end-to-end

Một phép thử đáng tin cần tạo ra tình huống người gọi không đủ quyền và xác nhận operation không có tác dụng phụ.

Ví dụ test plan:

1. Khởi tạo Spring context với method security bật.
2. Đăng ký management facade vào MBeanServer kiểm soát bởi test.
3. Dùng một fake \`OrderMaintenance\` ghi lại số lần operation chạy.
4. Chuẩn bị identity theo cơ chế authorization thực tế của JMX boundary.
5. Gọi \`MBeanServer.invoke\` với permission không đủ.
6. Xác nhận operation bị từ chối.
7. Xác nhận fake service **không được gọi** và state không thay đổi.
8. Gọi với identity đủ quyền.
9. Xác nhận chỉ một lần thực thi và audit được ghi.
10. Dọn MBean registration khi test kết thúc.

Khung gọi:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);

server.invoke(
    name,
    "retryFailedOrders",
    new Object[0],
    new String[0]
);
\`\`\`

Không được coi một \`SecurityException\` bất kỳ là bằng chứng đủ. Cần biết exception phát sinh ở JMX connector authorization, ở management authorizer hay ở Spring Security method interceptor. Hai lớp khác nhau có thể cần test độc lập.

Đối với integration test trong cùng JVM, \`MBeanServer.invoke\` có thể không tái hiện chính xác caller identity của remote connector. Muốn xác nhận remote security, cần test qua chính connector/transport và account cấu hình.

## 17. Những lỗi và ngộ nhận thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Operation chạy dù có \`@PreAuthorize\` | Lời gọi bypass AOP proxy hoặc method security chưa bật | Kiểm tra invocation path, \`@EnableMethodSecurity\`, test deny |
| Operation luôn bị từ chối từ JMX | Thread JMX thiếu Spring \`Authentication\` | Thiết kế trusted identity bridge hoặc JMX-specific authorization |
| HTTP admin gọi được nhưng JMX không gọi được | Hai hệ thống xác thực/authorization khác nhau | Phân biệt HTTP roles và JMX permissions |
| JDK proxy thiếu operation | Method không nằm trong interface proxy expose | Dùng management interface hoặc facade |
| CGLIB proxy không chặn method | \`final\`/private/self-invocation | Tách component và kiểm tra method interception |
| Operation hiển thị trong JConsole nhưng invoke thất bại | Signature, authorization hoặc business exception | Kiểm tra metadata và cause chain |
| Audit không ghi nhận JMX call | Advice bị bypass hoặc thiếu caller context | Log tại management boundary và kiểm tra proxy |
| Operation ở thread khác bỏ qua security | Async context propagation chưa được thiết kế | Dùng cơ chế propagation được kiểm soát |
| Remote JMX quá rộng quyền | Connector credentials/policy quá thoáng | Least privilege, network isolation, TLS |
| Operation nhạy cảm bị expose ngoài ý muốn | Assembler phản chiếu quá nhiều public methods | Whitelist \`@ManagedOperation\`/interface quản trị |

Không nên sửa vấn đề authorization bằng cách âm thầm cấp \`ROLE_ADMIN\` cho mọi JMX thread. Điều đó che đi việc thiếu identity đáng tin cậy và tạo lỗ hổng leo thang quyền.

## 18. Bài thực hành

### Bài 1: Annotation trên target có đủ không?

\`\`\`java
@PreAuthorize("hasAuthority('system:shutdown')")
public void shutdown() { /* ... */ }
\`\`\`

Nếu exporter expose raw target mà không gọi qua Spring security proxy, annotation có tự chặn JMX client không?

**Đáp án:** Không. Method security dựa vào AOP interception; nếu đường gọi bypass proxy, annotation không tự thực thi kiểm tra quyền.

### Bài 2: Identity trong JMX thread

Một tài khoản có quyền JMX connector kết nối thành công. Có thể giả định \`SecurityContextHolder\` đã có \`Authentication\` tương ứng không?

**Đáp án:** Không. Cần cơ chế bridge được thiết kế rõ nếu muốn dùng JMX identity trong Spring Security.

### Bài 3: JDK proxy

\`\`\`java
interface Worker {
    void run();
}

class WorkerImpl implements Worker {
    public void run() {}

    @ManagedOperation
    public void resetQueue() {}
}
\`\`\`

Vì sao \`resetQueue\` có thể không gọi được qua JDK proxy?

**Đáp án:** Method không có trong interface mà proxy expose. Cần interface quản trị phù hợp hoặc facade.

### Bài 4: Self-invocation

Method JMX \`trigger()\` gọi \`this.securedOperation()\`, trong khi \`securedOperation\` có \`@PreAuthorize\`. Vì sao security advice có thể không chạy?

**Đáp án:** Self-invocation trong proxy-based Spring AOP thường không đi qua proxy.

### Bài 5: Facade an toàn

Thiết kế một \`IndexJmxFacade\` chỉ expose \`rebuildIndex()\`, inject \`IndexMaintenanceService\` thông qua Spring proxy, validate authorization ở management boundary và xác minh bằng integration test rằng caller thiếu quyền không làm index thay đổi.

### Bài 6: Đánh giá nguy cơ

\`@ManagedOperation(description = "Admin only")\` có đủ bảo vệ \`deleteAllData()\` không?

**Đáp án:** Không. Description chỉ là metadata; cần authorization thực sự.

## 19. Checklist trước khi đưa operation ra production

1. Có thực sự cần gọi operation này qua JMX không?
2. JMX connector có authentication và authorization phù hợp không?
3. Remote endpoint có TLS/transport protection và network isolation không?
4. Operation có được export từ bean/facade đúng chủ sở hữu không?
5. Lời gọi JMX thực tế có đi qua Spring Security proxy nếu dựa vào \`@PreAuthorize\` không?
6. Thread JMX có identity/Authentication đáng tin cậy không?
7. Có xử lý trường hợp thiếu authentication theo hướng deny by default không?
8. Với JDK proxy, method có trong management interface không?
9. Với CGLIB, method có bị \`final\` hoặc giới hạn interception không?
10. Có tránh self-invocation bypass không?
11. Có test caller thiếu quyền và xác nhận state không đổi không?
12. Có audit, validation và retry policy an toàn cho operation có side effects không?

## 20. Kết luận

Spring JMX và Spring Security AOP có thể cùng tồn tại, nhưng authorization **không tự động được bảo toàn chỉ vì một bean có \`@PreAuthorize\`**. Method security chỉ có hiệu lực khi lời gọi thực tế đi qua proxy/advice phù hợp và có identity trong security context. JMX connector có hệ thống authentication/authorization riêng, không mặc định chuyển thành Spring Security principal.

Giải pháp bền vững là coi JMX như một management boundary độc lập: dùng connector security và least privilege, expose một facade nhỏ, gọi business service qua Spring proxy, kiểm soát identity có nguồn đáng tin cậy, và kiểm thử end-to-end bằng một lời gọi JMX với quyền không đủ.