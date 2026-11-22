# Spring Boot Actuator và quan hệ với JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Spring Boot integration  
> **Bài học:** Spring Boot Actuator và quan hệ với JMX

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích **Spring Boot Actuator** là gì và vì sao nó có thể expose thông tin quản trị qua **JMX**.
- Phân biệt **Actuator endpoint**, **Spring JMX MBean**, **MBeanServer** và **remote JMX connector**.
- Hiểu quan hệ giữa \`management.endpoints.jmx.exposure.*\` và \`spring.jmx.enabled\`.
- Cấu hình endpoint Actuator xuất hiện trong JMX phù hợp với phiên bản Spring Boot.
- Phân biệt quản trị qua HTTP \`/actuator/*\` và quản trị qua JMX.
- Xác minh endpoint và MBean được đăng ký thực sự bằng JConsole hoặc \`MBeanServerConnection\`.
- Tránh expose nhầm endpoint nhạy cảm, dùng sai server/port, hoặc trộn lẫn cơ chế export của Spring Framework với Spring Boot auto-configuration.

## 2. Bức tranh tổng thể

**Spring Boot Actuator** bổ sung các endpoint phục vụ quan sát và quản trị ứng dụng như health, info, metrics, loggers, beans, env và những endpoint khác tùy phiên bản, dependency và cấu hình.

Một endpoint Actuator là một khái niệm ở tầng ứng dụng. Nó có thể được expose qua nhiều công nghệ nếu môi trường hỗ trợ:

\`\`\`text
                    Spring Boot Application
                              |
                              v
                   Actuator endpoint model
                              |
                   +----------+----------+
                   |                     |
                   v                     v
              HTTP exposure        JMX exposure
                   |                     |
                   v                     v
             /actuator/...         MBean adapter
                                         |
                                         v
                                    MBeanServer
                                         |
                                         v
                                 JConsole/JMX client
\`\`\`

Hai đường **HTTP** và **JMX** có cấu hình exposure và bảo mật khác nhau. Việc endpoint có thể truy cập qua HTTP không tự động có nghĩa nó được expose qua JMX, và ngược lại.

Spring Boot còn có thể export những **MBean ứng dụng** được khai báo bằng \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`. Những MBean này khác với Actuator endpoint MBeans, dù cùng nằm trong JMX registry.

## 3. Phân biệt bốn tầng

| Tầng | Mục đích | Ví dụ |
|---|---|---|
| Application management | Định nghĩa thông tin/trạng thái quản trị | Actuator \`health\`, \`metrics\` |
| Exposure technology | Công bố endpoint qua HTTP hoặc JMX | \`/actuator/health\`, Actuator JMX MBean |
| JMX registry | Đăng ký và quản lý MBean | \`MBeanServer\`, \`ObjectName\` |
| Transport connector | Cho client local/remote truy cập JMX | Local attach, RMI/JMXConnector |

\`management.endpoints.jmx.exposure.include\` quyết định nhóm endpoint Actuator nào được expose qua JMX theo cơ chế Boot. Nó **không tự tạo remote RMI listener**. Ngược lại, mở remote JMX connector không có nghĩa Actuator đã được thêm vào ứng dụng hoặc mọi endpoint được công bố.

## 4. Dependency để sử dụng Actuator

Với dự án Spring Boot dùng Maven:

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

Gradle Groovy DSL:

\`\`\`groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
\`\`\`

Sau khi thêm starter, Boot auto-configures các thành phần Actuator phù hợp với môi trường, dependency và cấu hình.

Không tự suy luận rằng tất cả endpoint đều tồn tại hoặc đều được expose. Một số endpoint có điều kiện phụ thuộc vào classpath, bean/hệ thống tương ứng, cấu hình enablement và phiên bản Spring Boot.

## 5. Hai trục cấu hình riêng: enablement và exposure

**Enablement** liên quan endpoint có được tạo/kích hoạt trong application context hay không; **exposure** liên quan endpoint đó có được công bố qua một transport cụ thể hay không.

Một cấu hình có thể thể hiện:

\`\`\`properties
management.endpoints.enabled-by-default=true
management.endpoint.health.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Cần kiểm tra tên thuộc tính và mặc định đúng phiên bản Boot. Trong các phiên bản Boot hiện đại, nhóm \`management.endpoints.jmx.exposure.include\` và \`exclude\` kiểm soát danh sách exposure qua JMX.

\`\`\`text
Endpoint được enable?
          |
       Không ---> không có endpoint để expose
          |
         Có
          |
          v
Có nằm trong JMX exposure include
và không bị exclude?
          |
       Không ---> không expose qua JMX
          |
         Có
          |
          v
Actuator JMX adapter -> MBeanServer
\`\`\`

Không nên dùng wildcard cho mọi endpoint chỉ để tiện debug ở production, bởi một số endpoint chứa cấu hình, thuộc tính môi trường, logger state, thread dump hoặc dữ liệu quản trị không nên công bố rộng rãi.

## 6. Cấu hình JMX exposure trong application.properties

Ví dụ giới hạn hai endpoint:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
management.endpoints.jmx.exposure.exclude=
\`\`\`

Hoặc YAML:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info
\`\`\`

Đây là cấu hình **Actuator JMX exposure**, không phải Spring Framework \`@EnableMBeanExport\` thuần.

Trong một số môi trường, có thể muốn expose thêm metrics:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

Nhưng chỉ nên bật khi đã hiểu dữ liệu/operations mà endpoint cung cấp và ai có quyền sử dụng MBeanServer.

### Include và exclude

Ví dụ:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
management.endpoints.jmx.exposure.exclude=env,beans
\`\`\`

Cấu hình kiểu wildcard phụ thuộc cơ chế property binding và phiên bản; đây là minh họa về ý nghĩa include/exclude, **không phải khuyến nghị production**. Nếu dùng YAML, cần quote \`'*'\` khi giá trị wildcard vì ký tự \`*\` có ý nghĩa đặc biệt trong YAML.

Một cấu hình allowlist cụ thể thường an toàn và dễ kiểm kê hơn wildcard + exclude.

## 7. spring.jmx.enabled có liên quan gì?

Spring Boot hỗ trợ property \`spring.jmx.enabled\` để điều khiển tính năng JMX của ứng dụng theo cơ chế auto-configuration trong các phiên bản tương ứng.

Ví dụ:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Ý nghĩa khái quát: cho phép Spring Boot cấu hình hạ tầng JMX export thích hợp. Tuy nhiên phải đọc tài liệu đúng phiên bản, bởi mặc định, điều kiện auto-configuration và cách Actuator quản lý JMX có thể thay đổi giữa các dòng Boot.

Không nhầm:

- \`spring.jmx.enabled\`: chính sách Boot đối với JMX auto-configuration.
- \`management.endpoints.jmx.exposure.include\`: endpoint Actuator nào được công bố qua JMX.
- \`management.endpoints.web.exposure.include\`: endpoint Actuator nào được công bố qua HTTP.
- Remote connector agent flags: có thể truy cập MBeanServer qua mạng hay không.

Bật \`spring.jmx.enabled=true\` không có nghĩa JVM tự mở cổng remote JMX.

## 8. Actuator endpoint và @ManagedResource là hai con đường khác nhau

Một bean tự viết:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=WorkerPool,name=primary"
)
public class WorkerPoolMonitor {

    @ManagedAttribute
    public int getActiveWorkers() {
        return 3;
    }

    @ManagedOperation
    public void resetCounters() {
        // ...
    }
}
\`\`\`

Đây là **Spring JMX annotated bean**, không phải một Actuator endpoint chỉ vì nó sử dụng annotation quản trị.

Một endpoint Actuator tự viết có thể dùng \`@Endpoint\`:

\`\`\`java
import java.util.Map;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueStatus")
public class QueueStatusEndpoint {

    @ReadOperation
    public Map<String, Object> status() {
        return Map.of(
            "active", true,
            "pending", 12
        );
    }
}
\`\`\`

Đây là endpoint ở mức Actuator. Nếu có exposure và technology adapter thích hợp, endpoint này có thể được công bố qua HTTP hoặc JMX theo chính sách.

Hai loại thành phần:

\`\`\`text
@ManagedResource
    -> Spring JMX exporter -> MBean

@Endpoint / @ReadOperation
    -> Actuator endpoint model
    -> JMX exposure adapter -> MBean
\`\`\`

Vì vậy một codebase có thể có đồng thời MBean ứng dụng và MBean Actuator, nhưng phải tránh trùng \`ObjectName\`, domain và các exporter được tạo chồng nhau.

## 9. Quy ước tên MBean Actuator

Các endpoint Actuator được expose qua JMX dưới một ObjectName theo naming strategy và JMX domain của Boot. Trong nhiều cấu hình Boot, domain mặc định liên quan đến \`org.springframework.boot\`, và key properties mô tả endpoint.

Có thể tùy biến domain bằng cấu hình Boot như:

\`\`\`properties
management.endpoints.jmx.domain=com.example.management
\`\`\`

Tùy phiên bản Spring Boot, naming strategy và cách tạo ObjectName có thể thay đổi. **Không hardcode ObjectName Actuator từ trí nhớ**; hãy dùng \`MBeanServer.queryNames\` hoặc JConsole để xem tên thực tế đã đăng ký.

Ví dụ truy vấn một domain:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.management:*"
);

for (ObjectName name :
        connection.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Nếu trong cùng JVM có nhiều Spring application context, cấu hình domain khác nhau có thể giúp tránh xung đột tên và làm rõ ownership.

## 10. Truy cập Actuator qua HTTP khác gì JMX?

HTTP ví dụ:

\`\`\`text
GET /actuator/health
GET /actuator/info
GET /actuator/metrics
\`\`\`

JMX có thể mô tả các endpoint dưới dạng MBean operations mà client invoke, và kiểu dữ liệu được chuyển phù hợp với JMX technology adapter.

| Đặc điểm | HTTP Actuator | JMX Actuator |
|---|---|---|
| Đường vào | HTTP server / management HTTP port | MBeanServer / connector |
| Định danh | URL endpoint | ObjectName |
| Client | curl, browser, HTTP monitoring | JConsole, Java JMX client |
| Phương thức | HTTP GET/POST/DELETE theo operation | JMX MBean operations/attributes tùy adapter |
| Bảo mật | HTTP security chain, network, auth | JMX connector security/host access |
| Exposure | \`management.endpoints.web.exposure.*\` | \`management.endpoints.jmx.exposure.*\` |
| Mở port | Web server / management port | Remote JMX connector nếu có |

Không nên suy luận rằng một endpoint được cho phép trên HTTP sẽ mặc nhiên có cùng authorization khi truy cập qua JMX. Bảo mật hai kênh phải được thiết kế độc lập.

## 11. Ví dụ kiểm tra bằng JConsole

Sau khi thêm Actuator starter và bật JMX exposure:

1. Chạy ứng dụng Spring Boot, ghi PID của JVM.
2. Mở \`jconsole\` từ JDK thích hợp.
3. Chọn đúng local Java process.
4. Mở tab **MBeans**.
5. Tìm domain Actuator thực tế, ví dụ \`org.springframework.boot\` hoặc domain tùy biến.
6. Chọn MBean tương ứng với \`health\`, \`info\` hoặc \`metrics\`.
7. Đọc metadata/operations; chỉ thực thi những thao tác an toàn trong môi trường đang chạy.
8. Nếu không thấy endpoint, kiểm tra starter, enablement, exposure, auto-configuration và MBeanServer.

Một số JDK/JConsole có thể không hiển thị kết quả cấu trúc Actuator theo cách đẹp như JSON HTTP. Điều đó là khác biệt của giao diện/adapter, không nhất thiết là dữ liệu thiếu.

## 12. Kiểm tra bằng MBeanServerConnection

Để không phụ thuộc vào UI, có thể query MBean qua API:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names =
    server.queryNames(
        new ObjectName("org.springframework.boot:*"),
        null
    );

for (ObjectName name : names) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(name.getCanonicalName());
    System.out.println(info.getDescription());
}
\`\`\`

Đoạn code giả định Actuator export MBean trên **platform MBeanServer** và sử dụng domain tương ứng. Với domain tùy biến, hãy thay pattern; với server tùy biến, hãy lấy connection đúng server mà exporter dùng.

\`queryNames\` cho biết registry hiện tại. Không thấy một ObjectName trên platform MBeanServer **không chứng minh** ứng dụng không có Actuator; có thể endpoint chưa expose, domain khác hoặc exporter sử dụng server khác.

## 13. Xem danh sách operation và signature

Các MBean Actuator có thể expose operations với tên và kiểu dữ liệu do adapter tạo. Đọc metadata:

\`\`\`java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] ps = op.getSignature();

    for (int i = 0; i < ps.length; i++) {
        if (i > 0) {
            System.out.print(", ");
        }
        System.out.print(ps[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

Khi cần gọi một operation, dùng chính signature từ metadata:

\`\`\`java
Object result = server.invoke(
    name,
    operationName,
    params,
    signature
);
\`\`\`

Không đoán operation \`health\` có tên \`health()\` trên JMX. Endpoint ID và tên operation MBean có thể không giống biểu diễn HTTP. Metadata thực tế của version đang chạy mới là nguồn để client xây lời gọi.

## 14. Custom Actuator endpoint có thể có operation thay đổi trạng thái

Actuator hỗ trợ các annotation như \`@ReadOperation\`, \`@WriteOperation\` và \`@DeleteOperation\` cho endpoint.

Ví dụ:

\`\`\`java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "cacheMaintenance")
public class CacheMaintenanceEndpoint {

    private final CacheMaintenanceService service;

    public CacheMaintenanceEndpoint(
            CacheMaintenanceService service
    ) {
        this.service = service;
    }

    @WriteOperation
    public void refresh(String cacheName) {
        service.refresh(cacheName);
    }
}
\`\`\`

\`CacheMaintenanceService\` là dependency ứng dụng minh họa. Operation dạng write có thể ảnh hưởng trạng thái thật. Nếu endpoint được expose qua nhiều technology, cần xem xét tác dụng phụ và bảo mật ở từng đường truy cập.

Đừng đặt operation xóa dữ liệu hoặc thay đổi cấu hình nhạy cảm lên một endpoint rồi expose rộng rãi chỉ để tiện quan sát.

## 15. Mối liên hệ với Spring Boot auto-configuration

Spring Boot có thể tạo các bean JMX infrastructure dựa trên classpath và property. Điều này giảm cấu hình thủ công, nhưng dễ gây nhầm khi ứng dụng đã khai báo exporter:

\`\`\`text
Boot auto-configuration
      |
      +-- JMX/Actuator infrastructure
      |
      v
MBeanServer

Developer configuration
      |
      +-- @EnableMBeanExport
      +-- MBeanExporter bean thủ công
\`\`\`

Nếu hai exporter cùng đăng ký một Spring bean dưới cùng ObjectName trên một MBeanServer, có thể xảy ra registration conflict. Đừng dùng \`RegistrationPolicy.REPLACE_EXISTING\` như cách mặc định để che lỗi exporter trùng.

Nên kiểm kê các exporter thực tế, xác định thành phần sở hữu mỗi MBean và tránh đăng ký duplicate. Với Boot, trước hết kiểm tra cách auto-configuration của phiên bản đang dùng vận hành, rồi mới bổ sung cấu hình thủ công khi thật sự cần.

## 16. Remote JMX không phải management HTTP port

Hai loại port có thể tồn tại:

\`\`\`text
HTTP Management Port
  -> Spring Boot embedded web server
  -> /actuator/*

Remote JMX Port(s)
  -> JMXConnector/RMI
  -> MBeanServer
\`\`\`

\`management.server.port\` thường cấu hình HTTP management server port trong các phiên bản Boot phù hợp; nó **không phải** thuộc tính chỉ định JMX RMI registry port.

Remote JMX thường có cấu hình agent/connector riêng, ví dụ các system properties của JDK:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.example.internal
\`\`\`

Khi bật remote, phải thiết lập authentication, authorization, TLS và firewall phù hợp. Đừng công bố cổng JMX ra Internet công khai chỉ để theo dõi Actuator.

Một công cụ client có thể kết nối được đến JMX remote nhưng không thấy Actuator MBean nếu connector expose server khác với exporter; kiểm tra registry thực tế thay vì chỉ xét URL.

## 17. Bảo mật HTTP và JMX là hai bài toán

Ví dụ HTTP:

\`\`\`text
GET /actuator/env
\`\`\`

có thể được kiểm soát bởi Spring Security HTTP filter chain hoặc mạng reverse proxy. Nhưng quyền truy cập JMX đi qua connector và permission của JMX, không nhất thiết đi qua HTTP filter.

Do vậy:

- Không mặc định HTTP security policy bảo vệ JMX operations.
- Không dùng exposure wildcard trên cả hai kênh khi chưa đánh giá dữ liệu.
- Chỉ expose Actuator endpoints cần thiết cho vận hành.
- Giới hạn remote JMX theo identity, network và permissions.
- Tránh để custom endpoint trả secret hoặc dữ liệu cá nhân.
- Kiểm tra sanitization và dữ liệu thực tế được trả về theo phiên bản Boot.
- Ghi nhận quyền sở hữu và mục đích của từng management endpoint.

Trong nhiều hệ thống, thông tin giám sát chỉ đọc như health/metrics đủ đáp ứng nhu cầu; không cần expose tất cả endpoint có khả năng thay đổi trạng thái.

## 18. Health, Info và Metrics

### Health

Health endpoint thể hiện tình trạng ứng dụng và có thể có nhiều contributor. Nếu JMX adapter công bố health, một client có thể gọi operation tương ứng để lấy kết quả.

Không mặc định chi tiết health luôn được hiển thị đầy đủ; visibility có thể phụ thuộc cấu hình, vai trò client và technology adapter.

### Info

Info endpoint chứa các thông tin được cấu hình hoặc đóng góp bởi \`InfoContributor\`. Không đưa secret, mã định danh nhạy cảm hoặc toàn bộ environment vào info chỉ để tiện debug.

### Metrics

Metrics endpoint cung cấp cách truy vấn các meter/measurements do Micrometer và Boot quản lý theo cấu hình. Nó không đồng nghĩa mọi số liệu tự động có một JMX attribute tách biệt.

Với hệ thống quan sát quy mô lớn, Micrometer metrics có thể xuất qua hệ thống metrics riêng. JMX là một cách truy cập quản trị, không phải lựa chọn duy nhất hay luôn tối ưu cho time-series collection.

## 19. Một ví dụ kiểm chứng không phụ thuộc giả định tên MBean

Giả sử ứng dụng có JMX domain Actuator:

\`\`\`properties
management.endpoints.jmx.domain=com.example.actuator
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Client:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.actuator:*"
);

Set<ObjectName> objects =
    connection.queryNames(pattern, null);

for (ObjectName objectName : objects) {
    MBeanInfo info = connection.getMBeanInfo(objectName);

    System.out.println(objectName);
    System.out.println("Attributes: " + info.getAttributes().length);
    System.out.println("Operations: " + info.getOperations().length);
}
\`\`\`

Tiếp theo, mở JConsole và đối chiếu ObjectName được tìm thấy. Cách này phù hợp hơn việc hardcode \`org.springframework.boot:type=Endpoint,name=Health\` cho mọi phiên bản/configuration.

## 20. Xử lý khi không thấy Actuator MBean

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| Không có domain Actuator | Chưa có starter, JMX exposure tắt, exporter chưa hoạt động | Dependencies, application properties |
| Có endpoint HTTP nhưng không có JMX | Hai exposure độc lập | \`management.endpoints.jmx.exposure.*\` |
| Có MBean ứng dụng nhưng không có Actuator | Annotation exporter hoạt động nhưng Actuator JMX adapter chưa expose | Actuator auto-configuration |
| Có Actuator MBean nhưng không có custom \`@ManagedResource\` | MBean Actuator và annotated bean là hai cơ chế khác nhau | Spring JMX exporter |
| JConsole local không thấy | Sai JVM hoặc server khác platform server | PID, MBeanServer |
| JMX remote connect OK nhưng endpoint thiếu | Connector expose registry khác hoặc domain khác | \`queryNames\`, exporter/server |
| Startup báo trùng ObjectName | Nhiều exporter/endpoint trùng naming | Exporter ownership, naming |
| HTTP 404 nhưng JMX có MBean | HTTP endpoint không expose hoặc base path khác | Web exposure |
| HTTP bị 401/403 nhưng JMX gọi được | Security policy không giống nhau | Kiểm tra quyền JMX riêng |
| Metrics trống/khó đọc | Meter không tồn tại hoặc adapter hiển thị khác | Kiểm tra meter registry, metadata |

## 21. Phân biệt Actuator với JMX metrics exporter

Spring Boot Actuator có **metrics endpoint**, nhưng Micrometer cũng có thể dùng **JMX meter registry** để xuất meter trực tiếp dưới dạng MBean trong một domain metric riêng.

\`\`\`text
Micrometer MeterRegistry
         |
         +--> Actuator metrics endpoint
         |          |
         |          +--> HTTP/JMX exposure
         |
         +--> JMX meter registry
                    |
                    +--> Metrics MBeans
\`\`\`

Đây là những đường công bố khác nhau. Nếu thấy nhiều MBean metrics trong JConsole, hãy kiểm tra component nào đăng ký chúng, domain nào được dùng và liệu có duplication hay không.

Không coi \`management.endpoints.jmx.exposure.include=metrics\` là đồng nghĩa đã cấu hình Micrometer JMX registry xuất mọi meter thành các MBean độc lập.

## 22. Môi trường nhiều ApplicationContext

Trong ứng dụng có parent/child context hoặc nhiều Spring Boot application trong cùng JVM, có thể gặp:

- Nhiều exporter.
- Nhiều endpoint cùng ID.
- ObjectName collision.
- MBeanServer khác nhau.
- Domain JMX trùng nhau.
- Connector chỉ truy cập một server.

Khi đó cần xác định:

1. Endpoint thuộc context nào?
2. Exporter nào công bố endpoint?
3. ObjectName cụ thể là gì?
4. Exporter dùng MBeanServer nào?
5. Client đang kết nối tới server nào?

Việc cùng JVM không tự đảm bảo mọi MBean nằm trong một registry duy nhất.

## 23. Khi nào chọn HTTP Actuator, khi nào chọn JMX?

**HTTP Actuator** thường hợp khi hạ tầng đã có HTTP monitoring, reverse proxy, health probe hoặc service discovery. Dễ tích hợp với một số hệ thống observability, nhưng cần cấu hình web exposure và HTTP security.

**JMX Actuator** phù hợp khi công cụ vận hành dựa trên JConsole, JMX client/agent, hoặc khi cần quan sát registry JVM cùng các MBean khác. Với local attachment, có thể không cần HTTP endpoint.

Cả hai có thể cùng tồn tại. Lựa chọn không chỉ dựa vào “cái nào bật dễ hơn”, mà còn dựa vào quyền truy cập, network policy, kiểu dữ liệu, tần suất truy vấn và công cụ khách hàng đang dùng.

## 24. Bài tập thực hành

### Bài 1: Chỉ expose health và info qua JMX

Thêm starter Actuator và cấu hình:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Chạy ứng dụng, mở JConsole local, tìm domain Actuator thật và đọc metadata của các MBean đã xuất hiện. Nếu không thấy, kiểm tra đúng phiên bản Boot, enablement và MBeanServer.

### Bài 2: So sánh HTTP và JMX

Bật thêm HTTP exposure có chủ đích:

\`\`\`properties
management.endpoints.web.exposure.include=health,info
\`\`\`

Đối chiếu dữ liệu \`/actuator/health\` và operation JMX tương ứng. Chú ý representation, security và details visibility có thể khác nhau; không kết luận chỉ từ chuỗi kết quả hiển thị.

### Bài 3: Custom endpoint

Tạo một \`@Endpoint(id = "queueStatus")\` với \`@ReadOperation\` trả dữ liệu tổng hợp không nhạy cảm. Cấu hình exposure qua JMX; dùng \`queryNames\` và \`getMBeanInfo\` để xác nhận endpoint thực tế.

### Bài 4: Điều tra sai MBeanServer

Tạo một custom MBeanServer và kiểm tra một exporter được gán vào server này, trong khi JConsole local quan sát platform MBeanServer. Giải thích vì sao không thấy MBean và đề xuất cấu hình thống nhất server hoặc connector phù hợp.

## 25. Câu hỏi tự kiểm tra

1. Actuator endpoint có đồng nghĩa trực tiếp với \`@ManagedResource\` không?
2. Vì sao \`@EnableMBeanExport\` không tự mở remote JMX port?
3. Khác biệt giữa \`management.endpoints.web.exposure.include\` và \`management.endpoints.jmx.exposure.include\` là gì?
4. Vì sao không nên đoán ObjectName Actuator chỉ từ endpoint ID?
5. JMX adapter công bố endpoint trong registry nào?
6. Tại sao HTTP authorization không tự bảo vệ một JMX operation?
7. \`spring.jmx.enabled\` và endpoint exposure mang hai ý nghĩa khác nhau ra sao?
8. JMX meter registry khác Actuator metrics endpoint như thế nào?
9. Nếu JConsole local không thấy Actuator, cần kiểm tra những lớp nào?
10. Khi có nhiều exporter trong cùng JVM, rủi ro registration conflict là gì?

## 26. Ghi nhớ

\`\`\`text
Spring Boot Actuator
    |
    +--> Endpoint enablement
    |
    +--> HTTP exposure
    |       -> /actuator/*
    |
    +--> JMX exposure
            -> Actuator MBean adapter
            -> MBeanServer
            -> JConsole / JMX connector

Spring @ManagedResource
    -> Spring JMX exporter
    -> MBeanServer

Remote JMX connector
    -> đường mạng tới MBeanServer
    -> không tự được bật chỉ vì có Actuator
\`\`\`

**Nguyên tắc cốt lõi:** Actuator là mô hình endpoint quản trị của Spring Boot; JMX là một công nghệ expose endpoint đó. Spring JMX annotation exporter là một đường khác để công bố MBean ứng dụng. Hãy kiểm soát riêng enablement, JMX/HTTP exposure, MBeanServer, remote connector và security để biết chính xác **cái gì** được công bố và **ai** có thể sử dụng.