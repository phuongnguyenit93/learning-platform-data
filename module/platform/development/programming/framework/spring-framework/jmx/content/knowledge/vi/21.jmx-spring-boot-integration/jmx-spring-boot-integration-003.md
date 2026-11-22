# Phân biệt endpoint Actuator với MBean tự định nghĩa trong Spring Boot

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **Spring Boot Actuator endpoint** với **JMX MBean tự định nghĩa** về mục đích, cách lập trình và quản lý.
- Hiểu một Actuator endpoint có thể được công bố qua nhiều công nghệ, trong đó có HTTP và JMX, còn một MBean tùy chỉnh là đối tượng quản trị trực tiếp của JMX.
- Xác định thành phần nào được điều khiển bởi cấu hình \`management.endpoints.*\`, thành phần nào phụ thuộc Spring Framework \`MBeanExporter\`, \`@ManagedResource\` và \`@ManagedOperation\`.
- Biết cách chọn Actuator endpoint, custom MBean hoặc cả hai cho yêu cầu quan sát và quản trị.
- Tránh nhầm **endpoint exposure** với **JMX remote access**, và không coi bật một endpoint là mở sẵn kết nối JMX qua mạng.
- Kiểm chứng chính xác những gì đã được công bố trong \`MBeanServer\`.

## 1. Vì sao dễ nhầm Actuator và MBean?

Spring Boot có hai nhóm tính năng có thể cùng xuất hiện khi quan sát ứng dụng bằng JMX:

1. **Spring Boot Actuator** cung cấp các endpoint phục vụ vận hành, chẳng hạn health, info, metrics, beans hoặc các endpoint tự định nghĩa bằng \`@Endpoint\`.
2. **Spring Framework JMX** cho phép export một Spring bean thành MBean với \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` hoặc Standard MBean.

Cả hai có thể xuất hiện trong JConsole, nhưng chúng không cùng một khái niệm.

\`\`\`text
Spring Boot application
  |
  +-- Actuator endpoint model
  |     +-- HealthEndpoint
  |     +-- InfoEndpoint
  |     +-- MetricsEndpoint
  |     +-- @Endpoint custom
  |           |
  |           +-- HTTP exposure (nếu bật)
  |           +-- JMX exposure  (nếu bật)
  |
  +-- Spring Framework JMX model
        +-- @ManagedResource bean
        +-- Standard MBean
        +-- MBeanExporter
              |
              +-- MBeanServer
\`\`\`

Điểm then chốt:

> **Actuator endpoint là một abstraction vận hành của Spring Boot; MBean là một contract của Java JMX.** Actuator có thể có JMX adaptation, nhưng điều đó không biến mọi Spring MBean thành Actuator endpoint.

## 2. So sánh nhanh

| Tiêu chí | Actuator endpoint | MBean tự định nghĩa |
|---|---|---|
| Hệ sinh thái chính | Spring Boot Actuator | Java JMX / Spring Framework JMX |
| Cách khai báo | \`@Endpoint\`, \`@ReadOperation\`, \`@WriteOperation\`, \`@DeleteOperation\` | \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` hoặc interface \`*MBean\` |
| Mô hình quản trị | Endpoint và operations trừu tượng | MBean với attributes, operations, notifications |
| HTTP | Có thể công bố qua web exposure | Không tự sinh HTTP endpoint |
| JMX | Có thể công bố qua JMX exposure | Đăng ký trực tiếp vào MBeanServer qua exporter/registration |
| Định danh | Endpoint ID, ví dụ \`health\` | ObjectName, ví dụ \`learning.jmx:type=Queue,name=Primary\` |
| Cấu hình exposure | \`management.endpoints.web.exposure.*\`, \`management.endpoints.jmx.exposure.*\` | JMX exporter và MBeanServer configuration |
| Discovery qua JMX | Theo cơ chế JMX mapping của Actuator | Theo ObjectName mà exporter/registration tạo |
| Cách truy cập từ xa | Tùy transport HTTP hoặc JMX được cấu hình | Cần JMX connector/attach phù hợp |
| Phù hợp | Health, metrics, diagnostics, operational APIs | Java-specific management, operations, notifications, thuộc tính MBean tùy chỉnh |

Tên setting và giá trị mặc định có thể thay đổi giữa phiên bản Spring Boot. Khi triển khai, cần đối chiếu tài liệu đúng phiên bản đang sử dụng; bảng trên mô tả khái niệm và cơ chế chính.

## 3. Actuator endpoint là gì?

Actuator cung cấp một tập endpoint sẵn có và cho phép tạo endpoint tùy chỉnh. Một endpoint được xác định bằng ID và các operation.

Ví dụ tùy chỉnh:

\`\`\`java
package example.boot;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueStatus")
public class QueueStatusEndpoint {

    private final QueueService queueService;

    public QueueStatusEndpoint(QueueService queueService) {
        this.queueService = queueService;
    }

    @ReadOperation
    public QueueSnapshot status() {
        return new QueueSnapshot(
            queueService.pendingJobs(),
            queueService.isPaused()
        );
    }

    public record QueueSnapshot(int pendingJobs, boolean paused) {
    }
}
\`\`\`

Đây là **custom Actuator endpoint**, không phải một MBean được khai báo bằng \`@ManagedResource\`.

Spring Boot có thể tạo adapter để endpoint này xuất hiện qua một hoặc nhiều công nghệ exposure. Với HTTP, endpoint có thể có URL theo management web base path và endpoint ID; với JMX, có thể được ánh xạ thành MBean quản trị theo cơ chế Actuator.

Nhưng **khai báo \`@Endpoint\` không tự bảo đảm endpoint đã được expose trên mọi transport**. Cần xem dependencies, enablement, exposure policy và security.

### Các annotation Actuator cần phân biệt

- \`@Endpoint\`: endpoint có thể hỗ trợ nhiều công nghệ exposure.
- \`@ReadOperation\`: thao tác đọc trạng thái.
- \`@WriteOperation\`: thao tác thay đổi trạng thái.
- \`@DeleteOperation\`: thao tác xóa/loại bỏ theo contract endpoint.
- \`@WebEndpoint\`: endpoint dành riêng cho web technology.
- \`@JmxEndpoint\`: endpoint dành riêng cho JMX technology.

Tùy loại endpoint, các operation có thể được điều chỉnh để phù hợp công nghệ. Ví dụ một \`@WebEndpoint\` không tự động trở thành JMX endpoint, vì nó được thiết kế riêng cho web exposure.

## 4. MBean tự định nghĩa là gì?

MBean là đối tượng được đăng ký trong Java \`MBeanServer\`, có ObjectName và management interface.

Spring Framework hỗ trợ định nghĩa MBean qua annotations:

\`\`\`java
package example.boot;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary",
    description = "Queue management through JMX"
)
public class QueueManagement {

    private final QueueService queueService;

    public QueueManagement(QueueService queueService) {
        this.queueService = queueService;
    }

    @ManagedAttribute(description = "Current pending job count")
    public int getPendingJobs() {
        return queueService.pendingJobs();
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pause() {
        queueService.pause();
    }
}
\`\`\`

Khi \`MBeanExporter\` và annotation metadata export được kích hoạt phù hợp, bean có thể được đăng ký dưới ObjectName:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary
\`\`\`

JMX client có thể dùng:

\`\`\`java
Object pending = connection.getAttribute(
    new ObjectName("learning.jmx:type=QueueManagement,name=Primary"),
    "PendingJobs"
);
\`\`\`

Hoặc gọi operation:

\`\`\`java
connection.invoke(
    objectName,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

**MBean này không tự trở thành Actuator endpoint** và không tự có đường dẫn \`/actuator/queueManagement\`.

## 5. Cùng là “custom”, nhưng custom endpoint khác custom MBean

Dễ gặp hai cách gọi:

- “Tôi viết một endpoint custom bằng \`@Endpoint\`.”
- “Tôi viết một MBean custom bằng \`@ManagedResource\`.”

Chúng khác nhau ngay từ contract:

\`\`\`text
@Endpoint(id = "queueStatus")
  -> endpoint ID
  -> @ReadOperation, @WriteOperation ...
  -> Actuator exposure adapters

@ManagedResource(objectName = "learning.jmx:type=Queue,name=Primary")
  -> JMX ObjectName
  -> @ManagedAttribute, @ManagedOperation ...
  -> MBeanExporter / MBeanServer
\`\`\`

Một bean dùng \`@Endpoint\` được xử lý bởi hạ tầng Actuator; một bean dùng \`@ManagedResource\` được xử lý theo hạ tầng Spring Framework JMX. Nếu một ứng dụng có cả hai loại, người vận hành có thể thấy hai mục quản trị liên quan cùng một hệ thống.

Không nên tự ý giả định rằng hai mục có cùng trạng thái hoặc cùng quy trình bảo mật. Cần thiết kế rõ ranh giới trách nhiệm.

## 6. Cấu hình dependency và exposure

Để sử dụng các endpoint sẵn có của Actuator, Spring Boot thường cần dependency Actuator tương ứng, ví dụ Maven:

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

Một số cấu hình dạng properties cần biết:

\`\`\`properties
# Ví dụ chủ động expose một tập endpoint qua HTTP
management.endpoints.web.exposure.include=health,info,metrics

# Ví dụ chủ động expose một tập endpoint qua JMX
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

Những dòng này minh họa hai **tập exposure khác nhau**, không bảo đảm ba endpoint đều được enabled hoặc có mặt trong mọi phiên bản, môi trường và cấu hình bảo mật.

Một endpoint có thể được:

1. Cung cấp bởi dependency.
2. Enabled hoặc disabled.
3. Exposed hoặc không exposed qua web.
4. Exposed hoặc không exposed qua JMX.
5. Cho phép hoặc từ chối truy cập bởi security/runtime policy.

Các quyết định này cần được kiểm tra riêng.

### Điểm khác biệt quan trọng

\`management.endpoints.jmx.exposure.include\` điều khiển **Actuator endpoints được expose qua JMX**. Nó **không phải danh sách ObjectName cho mọi MBean tùy chỉnh** do \`MBeanExporter\` đăng ký.

Ngược lại, đăng ký một \`@ManagedResource\` không làm endpoint đó tự xuất hiện trong \`management.endpoints.web.exposure.include\`.

## 7. Spring Boot JMX và MBeanExporter

Trong Spring Boot, cấu hình JMX có thể bao gồm property điều khiển JMX export của ứng dụng, chẳng hạn:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Tác động chính xác của property và mặc định của nó cần xem theo phiên bản Boot. Khi sử dụng custom \`@ManagedResource\`, cần bảo đảm exporter phù hợp được kích hoạt.

Ví dụ một cách bật JMX export trực tiếp qua Spring Framework:

\`\`\`java
package example.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {
}
\`\`\`

Đừng cấu hình nhiều exporter cho cùng resource một cách thiếu kiểm soát. Trong Spring Boot, auto-configuration có thể đã cung cấp exporter; bổ sung một exporter thủ công có thể gây đăng ký trùng ObjectName.

### Có phải bật Actuator JMX exposure cũng tự bật mọi custom MBean?

Không. Hai cơ chế khác nhau:

- Actuator JMX exposure đưa các **Actuator endpoints** được chọn lên JMX.
- Spring Framework MBean exporter đăng ký **managed beans** theo annotation, convention hoặc mapping.

Có thể có cả hai trong một MBeanServer. Nhưng không nên suy luận rằng một cấu hình của cơ chế này kiểm soát toàn bộ cơ chế kia.

## 8. ObjectName khác endpoint ID

Một Actuator endpoint có ID:

\`\`\`text
health
metrics
queueStatus
\`\`\`

Trong JMX, Actuator sẽ ánh xạ endpoint sang MBean naming scheme do Actuator quản lý. Chi tiết ObjectName có thể phụ thuộc domain/naming strategy và cấu hình Boot.

Một custom MBean có ObjectName:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary
\`\`\`

**Endpoint ID không phải ObjectName.** Không nên lấy \`queueStatus\` làm ObjectName rồi kỳ vọng JMX client tìm thấy MBean theo cách đó.

Để khám phá chính xác những tên đã đăng ký:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(null, null)) {
    System.out.println(name);
}
\`\`\`

Kết quả có thể chứa MBeans nền tảng JVM, Actuator-exposed MBeans và MBeans tùy chỉnh. Cần xác định server thực sự mà các exporters sử dụng.

## 9. Ví dụ ứng dụng có cả Actuator endpoint và custom MBean

Giả sử một queue service:

\`\`\`java
package example.boot;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueService {

    private final AtomicInteger pending = new AtomicInteger();
    private final AtomicBoolean paused = new AtomicBoolean();

    public int pendingJobs() {
        return pending.get();
    }

    public boolean isPaused() {
        return paused.get();
    }

    public void pause() {
        paused.set(true);
    }

    public void resume() {
        paused.set(false);
    }
}
\`\`\`

Spring configuration:

\`\`\`java
package example.boot;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueConfiguration {

    @Bean
    QueueService queueService() {
        return new QueueService();
    }

    @Bean
    QueueStatusEndpoint queueStatusEndpoint(QueueService service) {
        return new QueueStatusEndpoint(service);
    }

    @Bean
    QueueManagement queueManagement(QueueService service) {
        return new QueueManagement(service);
    }
}
\`\`\`

Trong ví dụ này:

- \`QueueStatusEndpoint\` cung cấp trạng thái cho Actuator, có thể được expose qua web/JMX theo policy.
- \`QueueManagement\` cung cấp JMX-specific attribute và operation; cần Spring JMX exporter để đăng ký.
- Cả hai cùng gọi vào \`QueueService\` và có thể phản ánh cùng state.
- Chúng không cần có cùng tên hoặc cùng cơ chế exposure.

**Lưu ý:** Khi đã khai báo bean qua \`@Bean\`, không đồng thời dùng \`@Component\` để tạo thêm một instance cùng loại nếu không muốn duplicate beans/registrations.

## 10. Khi nào chọn Actuator endpoint?

Actuator thường phù hợp khi:

- Muốn cung cấp health, readiness, liveness, info hoặc metrics theo mô hình Spring Boot.
- Muốn operational API có thể được expose qua web hoặc JMX theo công nghệ phù hợp.
- Muốn một lớp abstraction độc lập hơn với JMX cho thao tác đọc trạng thái hoặc cấu hình.
- Đã có hạ tầng vận hành và security dành cho Actuator.
- Muốn xây custom endpoint với \`@ReadOperation\` hoặc \`@WriteOperation\`.

Ví dụ nếu một đội vận hành muốn đọc queue backlog qua HTTP và tích hợp với hệ thống monitoring, một custom Actuator endpoint hoặc Micrometer metric thường dễ tích hợp hơn việc yêu cầu mọi client dùng JMX.

Không phải mọi nhu cầu telemetry nên trở thành custom Actuator endpoint. Dữ liệu time-series có tần suất cao thường phù hợp hơn với metrics instrumentation, tùy thiết kế hệ thống.

## 11. Khi nào chọn custom MBean?

Custom MBean thường phù hợp khi:

- Đối tượng quản trị chủ yếu được dùng bởi công cụ Java/JMX.
- Cần mô hình attributes, operations, notifications đặc thù của JMX.
- Hệ thống đã có JMX clients và ObjectName naming convention ổn định.
- Muốn tích hợp với MBeanServer đang được container hoặc framework dùng.
- Có nhu cầu thao tác Java runtime hoặc quản trị component theo contract JMX.

Ví dụ một hệ thống sử dụng JConsole hoặc JMX client để xem pool status, reset thống kê và nhận notifications về threshold có thể dùng MBean tùy chỉnh.

Nhưng custom MBean không phải lựa chọn an toàn chỉ vì nó “không phải HTTP”. Khi có remote connector, nó vẫn là một bề mặt quản trị qua mạng.

## 12. Khi nào dùng cả hai?

Có trường hợp hợp lý để công bố cùng một dữ liệu qua hai công nghệ:

\`\`\`text
QueueService
   |
   +-- Actuator / metrics: đọc trạng thái cho vận hành phổ biến
   |
   +-- Custom MBean: quản trị chi tiết cho JMX tooling
\`\`\`

Tuy nhiên cần giải quyết:

- Có hai contract cần duy trì và versioning hay không?
- Dữ liệu có cùng ngữ nghĩa, kiểu và đơn vị không?
- Có vô tình expose operation nhạy cảm qua nhiều đường không?
- Hai cơ chế có sử dụng cùng lifecycle và cùng instance service không?
- Khi monitoring cho ra kết quả khác nhau, nguồn nào là authoritative?
- Có đủ yêu cầu để chấp nhận chi phí vận hành song song không?

Một cách thiết kế tốt là dùng **service/facade nghiệp vụ chung** làm nguồn state, còn Actuator endpoint và custom MBean chỉ là hai adapter phục vụ nhu cầu khác nhau.

## 13. Bảo mật: HTTP exposure và JMX remote là hai bề mặt khác nhau

Actuator endpoint có thể được expose qua HTTP. Đường HTTP cần được bảo vệ theo security configuration của web application hoặc management web server.

Custom JMX MBean và Actuator JMX exposure dùng JMX management path. Nếu từ xa, cần JMX connector được bảo vệ riêng.

Điều đó dẫn đến các nguyên tắc:

1. Bật HTTP authentication không tự bảo vệ một JMX remote connector.
2. Bật JMX authentication không tự bảo vệ HTTP Actuator endpoints.
3. Không coi remote JMX là read-only; MBean có thể có writable attributes và operations.
4. Đừng bật \`management.endpoints.web.exposure.include=*\` hoặc JMX exposure quá rộng nếu không có nhu cầu rõ.
5. Phân quyền tối thiểu cho công cụ quan sát và công cụ quản trị.
6. Không công bố password, token hoặc dữ liệu nhạy cảm trong Actuator endpoint lẫn custom MBean.
7. Với operation có tác dụng phụ, đánh giá thêm audit, approval và rollback.

Bảo mật cần được xét **theo từng transport và operation**, không dựa vào nhãn “Actuator” hay “JMX”.

## 14. Actuator exposure không phải mở JMX remote connector

Đây là nhầm lẫn quan trọng:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Cấu hình này nói rằng các endpoint được lựa chọn có thể được expose qua JMX theo hạ tầng Actuator. Nó **không tự đồng nghĩa**:

- JVM đã mở một remote JMX port.
- Remote client đã có quyền truy cập.
- TLS, authentication và authorization đã cấu hình.
- Một MBeanServer tùy biến khác cũng được expose.
- Mọi MBeans trong JVM đều được phép gọi từ xa.

Remote JMX connector là cơ chế Java/JMX riêng. Với JDK management agent, cấu hình remote có thể liên quan authentication, TLS, RMI ports và hostname. Không tắt bảo mật chỉ để thấy endpoint từ xa.

Ngược lại, một JConsole local có thể thấy một số MBeans mà không cần ứng dụng mở remote port, tùy attach/local management và quyền hệ điều hành.

## 15. Kiểm chứng trong MBeanServer

Để phân biệt nhóm MBeans, bắt đầu bằng việc khám phá registry:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> all = server.queryNames(null, null);

all.forEach(System.out::println);
\`\`\`

Sau đó kiểm tra tên cụ thể của custom MBean:

\`\`\`java
ObjectName custom = new ObjectName(
    "learning.jmx:type=QueueManagement,name=Primary"
);

System.out.println(server.isRegistered(custom));
\`\`\`

Để xem attributes và operations:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(custom);
\`\`\`

Có thể inspect:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Trong một ứng dụng có custom MBeanServer, platform server không nhất thiết chứa mọi registration. Lúc đó phải dùng đúng server mà exporter đã chọn, hoặc JMX connector vào server tương ứng.

## 16. Kiểm thử sự khác biệt bằng integration test

Một test hữu ích nên xác nhận:

- Custom MBean được đăng ký dưới ObjectName mong đợi.
- Attribute/operation JMX được công bố đúng.
- Actuator endpoint có tồn tại trong application context.
- Endpoint được expose qua transport mà bài test thực sự cấu hình.
- Không xuất hiện endpoint/operation ngoài dự kiến.
- Sau khi context đóng, các registrations do exporter quản lý được cleanup.

Ví dụ custom MBean test:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueManagement,name=Primary"
);

assertTrue(server.isRegistered(name));

assertNotNull(server.getAttribute(name, "PendingJobs"));

server.invoke(name, "pause", new Object[0], new String[0]);
\`\`\`

Khi test Actuator, cần dùng đúng adapter:

- Với web exposure: dùng HTTP test client vào management endpoint.
- Với JMX exposure: dùng MBeanServer hoặc MBeanServerConnection và ObjectName đã được Actuator tạo.
- Với endpoint availability: xác minh enablement/exposure theo cấu hình của phiên bản Boot.

Không dùng việc \`@Endpoint\` class tồn tại như bằng chứng duy nhất rằng web/JMX client đã có thể truy cập.

## 17. Những lỗi thường gặp

| Triệu chứng | Nhầm lẫn hoặc nguyên nhân | Hướng kiểm tra |
|---|---|---|
| \`@ManagedResource\` không xuất hiện ở \`/actuator\` | Custom MBean không phải Actuator endpoint | Dùng JMX exporter/connector; tạo Actuator endpoint riêng nếu cần HTTP |
| \`@Endpoint\` không hiện trong JConsole | JMX exposure chưa bật/endpoint chưa enabled | Kiểm tra Actuator JMX configuration và MBeanServer |
| Actuator endpoint có HTTP nhưng không có JMX | Exposure được cấu hình khác nhau | Kiểm tra từng transport |
| Custom MBean có trên JConsole nhưng không có HTTP | JMX không tự tạo HTTP route | Dùng Actuator/web API nếu thực sự cần |
| ObjectName của Actuator khác dự đoán | Actuator naming strategy/domain | Truy vấn MBeanServer thực tế |
| MBean trùng tên khi startup | Nhiều exporters hoặc context cùng register | Kiểm tra ObjectName, exporter và ownership |
| JMX remote không kết nối được | Chưa có connector, firewall, TLS hoặc credentials | Kiểm tra transport và bảo mật riêng |
| HTTP security hoạt động nhưng JMX operation vẫn được gọi | Hai bề mặt có security khác nhau | Bảo vệ JMX connector và methods |
| Metrics khác giá trị custom MBean | Định nghĩa, đơn vị hoặc timing khác nhau | Chuẩn hóa semantics và nguồn state |
| Boot property được đổi nhưng MBean vẫn còn | Property chỉ chi phối Actuator, không phải custom exporter | Phân biệt hai registration paths |

## 18. Tình huống thực tế

### Tình huống A — Monitoring muốn đọc queue depth

Nếu hệ thống giám sát chủ yếu thu thập time-series, cân nhắc Micrometer metrics/Actuator hoặc metrics endpoint tương ứng. Không nhất thiết tạo một custom MBean chỉ để công bố một counter.

### Tình huống B — JConsole cần pause/resume scheduler

Nếu môi trường đã có JMX tooling và thao tác cần quản trị Java runtime, custom MBean có \`@ManagedOperation\` có thể phù hợp. Vẫn phải phân quyền JMX và kiểm tra rủi ro của thao tác.

### Tình huống C — Một API cho cả HTTP và JMX

Nếu custom operation phù hợp với mô hình Actuator và cần nhiều transport, một \`@Endpoint\` có thể hữu ích. Nhưng phải kiểm thử adapter và representation của từng transport; không giả định mọi kiểu tham số/trả về đều có semantics giống nhau.

### Tình huống D — Hai nguồn dữ liệu

Actuator metrics và custom MBean cùng báo số active connections nhưng khác nhau. Cần kiểm tra lúc lấy mẫu, định nghĩa active, đơn vị, đồng bộ và implementation, không vội kết luận một bên sai vì cả hai hiển thị trong JConsole.

### Tình huống E — Không thấy MBean sau đổi cấu hình

Team thay \`management.endpoints.jmx.exposure.include\` rồi custom \`@ManagedResource\` vẫn còn. Điều này có thể hoàn toàn đúng: property Actuator không kiểm soát mọi custom Spring JMX registration.

## 19. Bài tập thực hành

### Bài 1 — Phân loại

Cho hai class:

\`\`\`java
@Endpoint(id = "queueStatus")
class QueueStatusEndpoint { ... }
\`\`\`

và:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
class QueueManagement { ... }
\`\`\`

Hãy xác định class nào dùng Actuator API, class nào dùng JMX metadata, và vì sao chúng không tự động có cùng endpoint.

### Bài 2 — Chọn giải pháp

Bạn cần hiển thị health readiness, thu thập request rate và cung cấp thao tác reset thống kê cho kỹ sư Java. Chọn Actuator health/metrics, Micrometer và/hoặc custom MBean cho từng yêu cầu. Giải thích ưu nhược điểm.

### Bài 3 — Thử exposure

Cấu hình một custom Actuator endpoint, expose nó qua web rồi qua JMX trong môi trường test. So sánh HTTP route với ObjectName mà Actuator tạo và ghi lại khác biệt.

### Bài 4 — Thử MBean riêng

Tạo \`@ManagedResource\` với \`@ManagedAttribute\` và \`@ManagedOperation\`. Dùng \`MBeanServer.isRegistered\` và \`getMBeanInfo\` xác nhận registration. Kiểm tra rằng chỉ tạo custom MBean không tự tạo web route.

### Bài 5 — Bảo mật

Một hệ thống bật cả Actuator HTTP và JMX remote. Hãy liệt kê những chính sách xác thực, phân quyền, TLS và network cần xem xét riêng cho từng đường kết nối.

## 20. Checklist thiết kế

Trước khi chọn cách công bố management functionality:

1. Consumer chính là HTTP client, metrics system hay JMX tool?
2. Có cần health/metrics có sẵn của Actuator không?
3. Có cần JMX-specific attributes, operations hoặc notifications không?
4. Có cần cùng chức năng xuất qua nhiều transport không?
5. Contract dữ liệu và kiểu tham số/trả về có phù hợp với từng adapter không?
6. ObjectName hoặc endpoint ID có đủ ổn định cho tooling không?
7. Bean được đăng ký bởi exporter nào và trong MBeanServer nào?
8. Có nguy cơ duplicate registration khi Boot auto-configuration cùng custom config không?
9. Exposure và enablement đã được cấu hình đúng phiên bản Boot chưa?
10. Bảo mật HTTP và JMX có được đánh giá riêng không?
11. Có operations làm thay đổi trạng thái cần giới hạn/audit không?
12. Đã có integration test cho đường kết nối thực tế chưa?

## 21. Ghi nhớ cốt lõi

- **Actuator endpoint** là mô hình endpoint quản trị của Spring Boot; nó có thể được expose qua web hoặc JMX tùy loại endpoint và cấu hình.
- **Custom MBean** là đối tượng quản trị của Java JMX, thường đăng ký bằng Standard MBean convention hoặc Spring Framework JMX exporter.
- \`@Endpoint\` khác \`@ManagedResource\`; \`@ReadOperation\` khác \`@ManagedAttribute\`.
- Actuator endpoint ID khác JMX ObjectName.
- \`management.endpoints.jmx.exposure.*\` điều khiển Actuator JMX exposure, không phải toàn bộ custom MBeans.
- Bật JMX exposure không đồng nghĩa đã mở remote connector; mỗi transport cần bảo mật và connectivity riêng.
- Khi dùng cả hai, nên có nguồn dữ liệu nghiệp vụ thống nhất và contract rõ ràng cho từng adapter.
- Kiểm chứng kết quả thực tế qua MBeanServer, HTTP test client và application context, không chỉ dựa vào annotation.

## Tài liệu tham khảo

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Boot API — Endpoint: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html
