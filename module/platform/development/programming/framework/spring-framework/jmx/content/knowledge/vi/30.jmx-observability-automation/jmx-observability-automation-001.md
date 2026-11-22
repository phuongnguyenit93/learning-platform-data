# Đọc MBean bằng script hoặc Web API trung gian

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Quan sát và tự động hóa  
> **Bài học:** Đọc MBean bằng script hoặc Web API trung gian

## 1. Mục tiêu

Khi cần theo dõi Spring JMX định kỳ, không phải lúc nào người vận hành cũng mở JConsole. Một script có thể truy vấn \`MBeanServerConnection\` và một Web API trung gian có thể cung cấp các chỉ số quản trị đã chọn lọc cho dashboard hoặc automation. Tuy nhiên cần phân biệt **đọc trạng thái** với **công bố toàn bộ quyền JMX ra mạng**.

Sau bài này, bạn có thể:

- Hiểu cách lấy \`ObjectName\`, \`MBeanInfo\`, \`getAttribute\` và \`queryNames\` trong JMX.
- Viết một chương trình Java dạng script/CLI đọc các attribute chỉ định trên MBean.
- Thiết kế một Web API trung gian chỉ đọc, ánh xạ kết quả JMX thành DTO JSON.
- Phân biệt local \`MBeanServer\` và remote \`MBeanServerConnection\`.
- Xử lý kiểu dữ liệu JMX như primitive, \`CompositeData\`, \`TabularData\`, \`ObjectName\` và mảng.
- Bảo vệ API trung gian bằng allowlist ObjectName/attribute, xác thực, phân quyền, timeout và giới hạn tải.
- Biết khi nào nên dùng metrics backend/Actuator thay vì polling JMX trực tiếp.

## 2. Tại sao cần script hoặc API trung gian?

JConsole phù hợp để xem trạng thái thủ công, nhưng các hệ thống vận hành thường cần:

- Thu thập giá trị định kỳ.
- Kiểm tra một chỉ số trong runbook.
- Đưa trạng thái JVM/Spring lên dashboard.
- Kết hợp dữ liệu từ nhiều instance.
- Cảnh báo khi queue depth, error count hoặc thread pool saturation vượt ngưỡng.
- Cung cấp một interface ổn định cho công cụ không hiểu JMX.

Mô hình:

\`\`\`text
Spring application
       |
       v
MBeanExporter -> MBeanServer
                      |
              MBeanServerConnection
                      |
          +-----------+-------------+
          |                         |
       Java CLI                  Read-only API
          |                         |
    stdout/JSON             HTTP JSON response
          |                         |
      Runbook                   Dashboard
\`\`\`

**Không nên tạo API kiểu \`/jmx/invoke?operation=...\` cho mọi ObjectName.** Nó có thể trở thành đường vòng bỏ qua chính sách quản trị, cho phép client từ xa gọi những operation có tác dụng phụ.

## 3. Thành phần cần phân biệt

| Thành phần | Vai trò |
|---|---|
| Spring \`@ManagedResource\` | Đánh dấu bean phục vụ quản trị |
| \`MBeanExporter\` | Đăng ký bean vào MBeanServer |
| \`MBeanServer\` | Registry MBean trong JVM |
| \`MBeanServerConnection\` | API đọc/ghi/invoke MBean local hoặc remote |
| \`ObjectName\` | Danh tính MBean trong một server |
| \`MBeanInfo\` | Metadata attribute/operation/notification |
| \`JMXConnector\` | Kết nối remote JMX |
| CLI/script | Client gọi API JMX theo kịch bản |
| Web API trung gian | Lớp chuyển dữ liệu JMX thành HTTP response có chính sách |
| Metrics backend | Nơi lưu time series, aggregation và alerting |

Một \`ObjectName\` chỉ có ý nghĩa trong một \`MBeanServer\`. Hai JVM khác nhau có thể chứa cùng ObjectName nhưng giá trị khác nhau.

## 4. MBean ví dụ trong Spring

\`\`\`java
package example.monitoring;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=Queue,name=orders",
    description = "Orders queue diagnostics"
)
public class OrdersQueueMonitor {

    private final AtomicLong processed = new AtomicLong();

    @ManagedAttribute(description = "Pending jobs")
    public int getPendingJobs() {
        // Trong ứng dụng thật: đọc từ queue adapter.
        return 12;
    }

    @ManagedAttribute(description = "Processed job count")
    public long getProcessedJobs() {
        return processed.get();
    }

    public void recordProcessed() {
        processed.incrementAndGet();
    }
}
\`\`\`

Cấu hình export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Hai attribute quản trị dự kiến:

\`\`\`text
PendingJobs: int (read-only)
ProcessedJobs: long (read-only)
\`\`\`

Khi exporter đăng ký thành công và client hỏi đúng server, các giá trị có thể được lấy qua \`getAttribute\`. Nếu dùng Spring Boot, cần kiểm tra auto-configuration JMX và tránh tạo exporter trùng không chủ đích.

## 5. Trước tiên xác định đúng MBeanServer

Một lỗi phổ biến: ứng dụng export vào custom server nhưng script lại đọc platform MBeanServer.

Local platform server:

\`\`\`java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Nếu exporter được cấu hình:

\`\`\`java
exporter.setServer(customMBeanServer);
\`\`\`

thì script trong cùng JVM phải đọc từ \`customMBeanServer\` hoặc connector đã được liên kết với server đó.

Kiểm tra:

\`\`\`java
ObjectName name = new ObjectName(
    "app.management:type=Queue,name=orders"
);

System.out.println(connection.isRegistered(name));
\`\`\`

\`false\` chưa chứng minh exporter không chạy: ObjectName, registry hoặc thời điểm truy vấn có thể khác.

## 6. Dùng MBeanInfo để khám phá API chỉ đọc

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
\`\`\`

Đối với script đọc, nên lọc:

\`\`\`java
if (attr.isReadable()) {
    // Attribute được metadata công bố là có thể đọc.
}
\`\`\`

Nhưng **readable** không đồng nghĩa dữ liệu không nhạy cảm. \`SystemProperties\`, dữ liệu environment hoặc attribute tùy biến có thể chứa secret. Web API trung gian phải có allowlist riêng, không tự expose tất cả readable attributes.

## 7. Script Java CLI đọc một MBean

Một CLI nhỏ có thể nhận cấu hình ObjectName cố định:

\`\`\`java
package example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class LocalJmxRead {

    public static void main(String[] args) throws Exception {
        MBeanServerConnection connection =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "app.management:type=Queue,name=orders"
        );

        if (!connection.isRegistered(name)) {
            System.err.println("MBean missing: " + name);
            System.exit(2);
        }

        Object pending =
            connection.getAttribute(name, "PendingJobs");

        Object processed =
            connection.getAttribute(name, "ProcessedJobs");

        System.out.println(
            "pendingJobs=" + pending
        );
        System.out.println(
            "processedJobs=" + processed
        );
    }
}
\`\`\`

**Quan trọng:** đoạn CLI này chỉ đọc MBean của **chính JVM đang chạy chương trình CLI**. Nếu chạy nó như một Java process riêng, \`ManagementFactory.getPlatformMBeanServer()\` trỏ tới MBeanServer của process CLI, không phải JVM ứng dụng khác.

Để đọc JVM khác, sử dụng remote connector hoặc đưa phần đọc vào application process rồi xuất dữ liệu qua một API/metrics integration.

## 8. Script kết nối JMX từ xa

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxRead {

    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://" +
            "jmx.internal.example:9010/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();

        // Đặt credentials và cấu hình TLS qua cơ chế
        // quản lý secret/truststore của môi trường.
        // Không hardcode password vào source.

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, environment)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "app.management:type=Queue,name=orders"
            );

            System.out.println(
                connection.getAttribute(name, "PendingJobs")
            );
        }
    }
}
\`\`\`

Đoạn trên giả định server connector và network đã được thiết lập. Trong production, cần sử dụng authentication, authorization, TLS, timeout và network isolation phù hợp. \`@EnableMBeanExport\` không tự mở remote JMX connector.

JMX RMI có thể sử dụng registry port và một RMI endpoint port riêng. Khi firewall/NAT can thiệp, phải kiểm tra cả endpoint được quảng bá bởi RMI stub.

## 9. Ví dụ credentials client

Với connector hỗ trợ xác thực username/password theo cơ chế phù hợp:

\`\`\`java
Map<String, Object> environment = new HashMap<>();

environment.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);

JMXConnector connector =
    JMXConnectorFactory.connect(url, environment);
\`\`\`

\`username\` và \`password\` phải lấy từ secret source đã được bảo vệ, không đặt hằng số trong Java file hoặc tham số command line bị ghi log. Tùy connector/JDK, cấu hình TLS có thể cần truststore/system properties hoặc socket factory thích hợp.

Hạn chế cấp tài khoản read-write cho script chỉ đọc. Tuy nhiên khả năng phân quyền đến từng MBean/operation còn tùy JMX connector/access control implementation, không tự được đảm bảo chỉ bằng việc dùng \`getAttribute\`.

## 10. Không dùng MBeanServerConnection như API không giới hạn

Một interface \`MBeanServerConnection\` có các phương thức:

\`\`\`java
connection.getAttribute(...);
connection.getAttributes(...);
connection.queryNames(...);
connection.invoke(...);
connection.setAttribute(...);
\`\`\`

Nếu mục tiêu là quan sát, chương trình nên chỉ sử dụng:

- \`queryNames\` có pattern giới hạn.
- \`getMBeanInfo\` để kiểm tra metadata khi cần.
- \`getAttribute\`/\`getAttributes\` với allowlist.
- Có thể \`getMBeanCount\` hoặc thông tin hệ thống đã được duyệt.

Không cho user tùy ý gọi \`invoke\`, \`setAttribute\` hoặc \`unregisterMBean\` thông qua một endpoint HTTP chỉ vì API JMX hỗ trợ.

## 11. Đọc nhiều attribute trong một lần

\`getAttributes\` có thể giảm số lần gọi, đặc biệt với remote connector:

\`\`\`java
import javax.management.Attribute;
import javax.management.AttributeList;

AttributeList result = connection.getAttributes(
    name,
    new String[] {
        "PendingJobs",
        "ProcessedJobs"
    }
);

for (Object entry : result) {
    Attribute attr = (Attribute) entry;
    System.out.println(
        attr.getName() + "=" + attr.getValue()
    );
}
\`\`\`

Kết quả không nên được coi là luôn đầy đủ cho mọi tên yêu cầu. Tùy MBean và lỗi, \`getAttributes\` có thể trả danh sách chỉ gồm những attribute đọc thành công.

Trong code quan sát, hãy so sánh những tên nhận được với danh sách mong đợi và báo trạng thái \`PARTIAL\` nếu có attribute bị thiếu, thay vì điền số 0 làm kết quả mặc định.

## 12. Đọc MBean theo ObjectName pattern

\`\`\`java
ObjectName pattern = new ObjectName(
    "app.management:type=Queue,*"
);

Set<ObjectName> queues =
    connection.queryNames(pattern, null);

for (ObjectName objectName : queues) {
    System.out.println(objectName.getCanonicalName());
}
\`\`\`

Pattern chỉ phù hợp khi bạn thật sự muốn khám phá các instance tương ứng. Khi thiết kế Web API, nên giới hạn domain và key properties để tránh người gọi khám phá MBean không liên quan.

\`queryNames\` trả về các tên tại thời điểm truy vấn. MBean có thể unregister sau đó; \`getAttribute\` vẫn có thể ném \`InstanceNotFoundException\`.

## 13. Chuyển dữ liệu JMX sang JSON

HTTP JSON client thường không hiểu Java JMX types như \`CompositeData\` hoặc \`TabularData\` trực tiếp. Cần mapping có kiểm soát.

Ví dụ các kiểu cơ bản:

| Giá trị JMX | JSON thích hợp |
|---|---|
| \`Integer\`, \`Long\`, \`Double\` | JSON number khi không mất độ chính xác |
| \`Boolean\` | JSON boolean |
| \`String\` | JSON string |
| \`ObjectName\` | Canonical name string |
| \`String[]\` | JSON array |
| \`CompositeData\` | JSON object với key được allowlist |
| \`TabularData\` | JSON array hoặc object theo schema xác định |
| \`null\` | JSON null |

Lưu ý JavaScript JSON number chỉ biểu diễn số nguyên chính xác trong một khoảng giới hạn. Với counter 64-bit rất lớn, cân nhắc biểu diễn dưới dạng chuỗi hoặc format được client thống nhất để tránh mất precision.

Không tự serialize mọi JMX object bằng reflection hoặc \`toString()\`; một số kiểu có thể chứa cấu trúc phức tạp, dữ liệu nhạy cảm hoặc biểu diễn không ổn định.

## 14. Xử lý CompositeData

Một số MBean của JVM sử dụng \`javax.management.openmbean.CompositeData\`, ví dụ thông tin memory usage.

\`\`\`java
import javax.management.openmbean.CompositeData;

Object raw = connection.getAttribute(
    memoryPoolObjectName,
    "Usage"
);

if (raw instanceof CompositeData data) {
    Object used = data.get("used");
    Object max = data.get("max");

    System.out.println("used=" + used);
    System.out.println("max=" + max);
}
\`\`\`

Khi chuyển sang JSON, nên chỉ lấy key đã biết và kiểm tra kiểu:

\`\`\`json
{
  "usedBytes": 12582912,
  "maxBytes": 67108864
}
\`\`\`

Không mặc định mọi \`CompositeData\` đều có key \`used\` hoặc \`max\`; schema OpenType phụ thuộc MBean/attribute.

## 15. Xử lý TabularData

\`TabularData\` đại diện cấu trúc dạng bảng trong Open MBean. Một converter có thể lấy \`values()\`, chuyển mỗi \`CompositeData\` thành object JSON theo schema đã định.

\`\`\`java
import javax.management.openmbean.TabularData;
import javax.management.openmbean.CompositeData;

if (value instanceof TabularData table) {
    for (Object row : table.values()) {
        if (row instanceof CompositeData data) {
            // Chọn những field được phép công bố.
        }
    }
}
\`\`\`

Cần tránh:

- Chuyển một bảng rất lớn thành response không giới hạn.
- Giả định thứ tự hàng luôn ổn định.
- Trả về dữ liệu toàn phần không được phân loại.
- Bỏ qua kích thước JSON hoặc lỗi serializing.

Trong API, cân nhắc giới hạn số dòng, schema cố định hoặc chỉ trả về metric aggregate.

## 16. Thiết kế Web API trung gian

Mô hình hợp lý:

\`\`\`text
Dashboard / automation
         |
         | HTTPS + authentication + authorization
         v
    Read-only HTTP controller
         |
         | allowlist endpoint
         v
    Management snapshot service
         |
         | ObjectName cố định
         | Attribute cố định
         v
    MBeanServerConnection
         |
         v
      MBeanServer
\`\`\`

Thay vì expose generic \`GET /jmx?objectName=...&attribute=...\`, nên thiết kế endpoint theo dữ liệu vận hành:

\`\`\`text
GET /internal/monitoring/orders-queue
\`\`\`

Response:

\`\`\`json
{
  "queue": "orders",
  "pendingJobs": 12,
  "processedJobs": 1420,
  "sampledAt": "2026-11-11T11:00:00Z"
}
\`\`\`

Ví dụ này không mở một cổng phép toán tùy ý vào JVM. Client biết schema JSON rõ ràng, không cần xây \`ObjectName\`.

## 17. Ví dụ Spring Web API chỉ đọc

DTO:

\`\`\`java
package example.monitoring;

import java.time.Instant;

public record QueueSnapshot(
    String queue,
    int pendingJobs,
    long processedJobs,
    Instant sampledAt
) {}
\`\`\`

Service:

\`\`\`java
package example.monitoring;

import java.time.Instant;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

import org.springframework.stereotype.Service;

@Service
public class QueueSnapshotService {

    private final MBeanServerConnection connection;
    private final ObjectName queueName;

    public QueueSnapshotService(
            MBeanServerConnection connection
    ) throws Exception {
        this.connection = connection;
        this.queueName = new ObjectName(
            "app.management:type=Queue,name=orders"
        );
    }

    public QueueSnapshot read() throws Exception {
        int pending = (Integer) connection.getAttribute(
            queueName,
            "PendingJobs"
        );

        long processed = (Long) connection.getAttribute(
            queueName,
            "ProcessedJobs"
        );

        return new QueueSnapshot(
            "orders",
            pending,
            processed,
            Instant.now()
        );
    }
}
\`\`\`

Controller:

\`\`\`java
package example.monitoring;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/monitoring")
public class QueueMonitoringController {

    private final QueueSnapshotService service;

    public QueueMonitoringController(
            QueueSnapshotService service
    ) {
        this.service = service;
    }

    @GetMapping("/orders-queue")
    public QueueSnapshot readQueue() throws Exception {
        return service.read();
    }
}
\`\`\`

Đây là ví dụ cấu trúc. Ứng dụng cần cung cấp \`MBeanServerConnection\` bean, cấu hình HTTP security và exception handling phù hợp. Không expose endpoint này công khai chỉ vì đường dẫn bắt đầu bằng \`/internal\`.

## 18. Cấp MBeanServerConnection cho Web API

Với Spring application dùng platform server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxConnectionConfig {

    @Bean
    public MBeanServerConnection managementConnection() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Nếu exporter được cấu hình dùng một custom MBeanServer, Web API phải nhận **cùng server**, không tự dùng platform server.

Một cách rõ ràng là tạo một \`MBeanServer\` bean duy nhất và inject vào cả exporter và snapshot service. Khi có nhiều MBeanServer trong cùng JVM, dùng \`@Qualifier\` để tránh tiêm nhầm.

## 19. Không expose ObjectName tùy ý từ HTTP request

Một anti-pattern:

\`\`\`java
@GetMapping("/jmx")
public Object read(
        @RequestParam String objectName,
        @RequestParam String attribute
) throws Exception {
    return connection.getAttribute(
        new ObjectName(objectName),
        attribute
    );
}
\`\`\`

Dù chỉ gọi \`getAttribute\`, API này có thể tiết lộ:

- JVM/system properties.
- Thread dump hoặc trạng thái nội bộ.
- Cấu hình app và connection settings.
- MBean của thư viện khác.
- Định danh nội bộ của hệ thống.

Nếu bắt buộc hỗ trợ nhiều chỉ số, dùng mapping cố định:

\`\`\`java
Map<String, MetricMapping> allowed = Map.of(
    "orders.pending",
    new MetricMapping(
        "app.management:type=Queue,name=orders",
        "PendingJobs"
    ),
    "orders.processed",
    new MetricMapping(
        "app.management:type=Queue,name=orders",
        "ProcessedJobs"
    )
);
\`\`\`

\`MetricMapping\` là record/class do ứng dụng định nghĩa. Client chỉ chọn key được allowlist, không truyền raw \`ObjectName\` hoặc attribute string.

## 20. HTTP security là bắt buộc

Với API trung gian, cần thiết kế:

- Authentication bằng cơ chế đang dùng của tổ chức.
- Authorization theo role/service identity.
- HTTPS/TLS.
- Network segmentation hoặc private ingress.
- Rate limiting và protection chống polling quá dày.
- Audit các truy cập dữ liệu nhạy cảm.
- Sanitization dữ liệu trả về.
- Không ghi credentials vào log.
- Timeout và circuit breaker với remote JMX.

Một đường dẫn \`/internal/monitoring\` không tự tạo access control. Spring Security cần được cấu hình cho endpoint này theo yêu cầu thực tế.

Nếu API chỉ phục vụ monitoring agent, cân nhắc sử dụng service-to-service identity thay vì token chia sẻ rộng rãi.

## 21. Timeout, retries và tải hệ thống

Một \`getAttribute\` local thường nhanh hơn remote JMX, nhưng vẫn có thể bị chậm nếu getter truy cập database, network hoặc giữ lock.

Tránh getter:

\`\`\`java
@ManagedAttribute
public int getPendingJobs() {
    return remoteQueueClient.scanAllJobs();
}
\`\`\`

nếu mỗi lần đọc kích hoạt truy vấn tốn kém.

Tốt hơn:

\`\`\`java
@ManagedAttribute
public int getPendingJobs() {
    return cachedQueueDepth.get();
}
\`\`\`

với dữ liệu tổng hợp/cached được cập nhật phù hợp.

Dành cho Web API:

1. Đặt timeout ở tầng remote connector/HTTP request theo khả năng.
2. Hạn chế concurrency và request rate.
3. Xác định stale-data policy.
4. Không retry vô hạn khi server không có MBean.
5. Trả trạng thái unavailable hoặc partial thay vì gán số 0 giả.
6. Theo dõi latency của chính bridge service.

Một API phản hồi “pendingJobs=0” khi JMX bị timeout có thể tạo ra tín hiệu vận hành sai. Hãy phân biệt \`0\` là số đo thật với “không lấy được số liệu”.

## 22. Trạng thái lỗi nên được biểu diễn rõ

Một API trung gian có thể dùng schema:

\`\`\`json
{
  "status": "UNAVAILABLE",
  "sampledAt": "2026-11-11T11:00:00Z",
  "reasonCode": "JMX_TIMEOUT"
}
\`\`\`

Hoặc HTTP \`503 Service Unavailable\` với body có mã lỗi ổn định.

Không gửi stack trace, username, connector URL chứa secret hay exception message nội bộ cho client không đáng tin. Log server-side phải có correlation ID để tra cứu, đồng thời tránh rò rỉ thông tin nhạy cảm.

Các lỗi thường gặp:

| Lỗi JMX | Ý nghĩa khả dĩ | Hướng xử lý |
|---|---|---|
| \`InstanceNotFoundException\` | ObjectName chưa đăng ký hoặc bị unregister | Kiểm tra exporter/server/lifecycle |
| \`AttributeNotFoundException\` | Attribute không tồn tại | Kiểm tra \`MBeanInfo\` |
| \`MBeanException\` | Getter/operation server-side lỗi | Kiểm tra cause và business code |
| \`ReflectionException\` | Reflection/access mismatch | Kiểm tra adapter/metadata |
| \`IOException\` | Remote connection lỗi | Kiểm tra network/connector |
| Authentication failure | Credentials hoặc access rules sai | Kiểm tra identity/security setup |
| \`SecurityException\` | Bị từ chối quyền | Không bypass, điều tra policy |

## 23. Dùng script định kỳ để thu thập snapshot

Một lịch thu thập nên xác định:

\`\`\`text
Mỗi 30 giây
   |
   v
JMX read-only query
   |
   v
Normalize + timestamp + instance ID
   |
   v
Metrics/time-series backend
\`\`\`

Không nên để mỗi dashboard tab mở một connection riêng và polling nhanh vào cùng JVM. Dùng agent/collector chung hoặc cache snapshot để giảm tải.

Với script định kỳ:

- Có timeout và exit code rõ.
- Ghi timestamp/instance ID.
- Phân biệt missing MBean với giá trị 0.
- Xử lý credentials an toàn.
- Không ghi password vào stdout.
- Có cleanup connector.
- Không gọi operation có tác dụng phụ trong job thu thập.

## 24. Khi nào nên dùng Spring Boot Actuator/Micrometer?

Nếu mục tiêu chủ yếu là metrics và health, thường có các công cụ phù hợp hơn một Web API bridge tự viết:

\`\`\`text
Spring Boot Actuator
    |
    +--> health/info endpoints
    |
    +--> metrics endpoint
    |
    +--> Micrometer meter registry
              |
              +--> monitoring backend
\`\`\`

Actuator có thể expose endpoint qua HTTP hoặc JMX tùy cấu hình. Micrometer có nhiều exporter để tích hợp với hệ thống metrics.

Một bridge JMX tự viết phù hợp khi:

- Ứng dụng/library chỉ công bố dữ liệu dưới dạng MBean.
- Cần một số chỉ số JMX đặc thù mà chưa có metric adapter.
- Client không biết JMX nhưng cần schema HTTP ổn định.
- Có khả năng quản lý security, rate limiting và lifecycle của bridge.

Nếu chỉ cần JVM metrics chuẩn, nên đánh giá Actuator/Micrometer/JMX exporter hiện có trước khi tạo controller mới.

## 25. Kiểm thử API trung gian

Một integration test nên kiểm tra:

1. MBean được đăng ký trên server dùng trong test.
2. Endpoint chỉ đọc những attribute được allowlist.
3. Response JSON có kiểu và giá trị đúng.
4. Không expose dữ liệu ngoài danh sách cho phép.
5. Khi MBean missing, API trả lỗi rõ ràng.
6. Khi attribute missing, không tự trả 0.
7. Authentication/authorization chặn client không đủ quyền.
8. Timeout/rate limiting hoạt động trong hạ tầng phù hợp.
9. Application shutdown cleanup connector/resource.
10. Không có đường HTTP cho arbitrary \`invoke\`/\`setAttribute\`.

Ví dụ kiểm thử service:

\`\`\`java
MBeanServer testServer =
    MBeanServerFactory.newMBeanServer("monitoring.test");

ObjectName name = new ObjectName(
    "app.management:type=Queue,name=orders"
);

// Đăng ký một test MBean tương thích với schema.
// Sau đó inject testServer vào QueueSnapshotService.
// Gọi service.read() và assert PendingJobs/ProcessedJobs.
\`\`\`

Đây là phác thảo cần test fixture MBean và DI setup thực tế. Không dùng platform MBeanServer nếu test có khả năng xung đột với MBean production của JVM test runner.

## 26. Quan sát nhiều JVM

Một API trung gian muốn tổng hợp nhiều JVM cần xử lý mỗi connection riêng:

\`\`\`text
JVM A MBeanServer ----\
                       \
JVM B MBeanServer ------> Collector/API
                       /
JVM C MBeanServer ----/
\`\`\`

Mỗi JVM có thể sử dụng cùng ObjectName \`app.management:type=Queue,name=orders\`, vì vậy định danh dữ liệu phải kèm instance ID hoặc server identity.

Ví dụ JSON:

\`\`\`json
{
  "instances": [
    {
      "instance": "orders-1",
      "pendingJobs": 12,
      "status": "OK"
    },
    {
      "instance": "orders-2",
      "status": "UNAVAILABLE"
    }
  ]
}
\`\`\`

Không gán \`pendingJobs=0\` cho instance đang unreachable. Cũng không coi nhiều MBean cùng ObjectName trong các JVM khác nhau là một object duy nhất.

Với quy mô lớn, collector/metrics backend được thiết kế chuyên dụng thường hiệu quả hơn controller tự fan-out sang mọi JVM trong mỗi HTTP request.

## 27. Bài tập thực hành

### Bài A: CLI đọc hai attribute

Từ Spring MBean \`app.management:type=Queue,name=orders\`, dùng \`MBeanServerConnection\` và \`getAttributes\` lấy \`PendingJobs\` cùng \`ProcessedJobs\`.

Yêu cầu: in đúng hai giá trị, báo lỗi khi ObjectName không tồn tại, không thực hiện \`invoke\`.

### Bài B: MBeanInfo discovery

Dùng \`getMBeanInfo\` để in danh sách readable attributes và kiểu. Giải thích tại sao vẫn cần allowlist trước khi expose qua HTTP.

### Bài C: HTTP bridge

Thiết kế endpoint \`GET /internal/monitoring/orders-queue\` trả DTO \`QueueSnapshot\`. Bảo vệ bằng Spring Security hoặc security layer phù hợp. Tạo test xác minh client không đủ quyền bị từ chối.

### Bài D: CompositeData

Đọc một attribute dạng \`CompositeData\`, chọn hai field không nhạy cảm và chuyển sang JSON. Xử lý trường hợp key bị thiếu hoặc sai kiểu.

### Bài E: Remote connection bị mất

Mô phỏng \`IOException\` khi truy vấn và trả \`UNAVAILABLE\` hoặc HTTP 503. Không trả số đo giả.

## 28. Câu hỏi tự kiểm tra

1. Vì sao chương trình CLI trong một JVM riêng không thể tự đọc MBeanServer platform của JVM khác?
2. \`ObjectName\` có định danh duy nhất toàn bộ JVM trên nhiều máy không?
3. Khi nào nên dùng \`getAttributes\` thay vì nhiều lần \`getAttribute\`?
4. Vì sao API không nên nhận raw ObjectName từ HTTP request?
5. \`CompositeData\` cần mapping sang JSON như thế nào?
6. Tại sao read-only API vẫn cần authentication và authorization?
7. Một getter MBean có thể gây tải lớn dù chỉ đọc không?
8. Timeout JMX có nên được chuyển thành số đo bằng 0 không?
9. Khi nào Actuator/Micrometer tốt hơn bridge tự viết?
10. Vì sao không nên cho Web API trung gian tùy ý gọi \`invoke\`?

## 29. Ghi nhớ

\`\`\`text
JMX script:
  MBeanServerConnection
      -> queryNames/getMBeanInfo
      -> getAttribute/getAttributes
      -> stdout/JSON

Read-only Web API:
  HTTPS + authorization
      -> allowlist
      -> fixed ObjectName + attribute
      -> normalize typed DTO
      -> JSON response

Không expose arbitrary JMX invoke/setAttribute.
\`\`\`

**Nguyên tắc cốt lõi:** có thể đọc MBean bằng script hoặc Web API trung gian, nhưng cần chọn **đúng MBeanServer**, **đúng ObjectName**, **đúng attribute**, chuyển dữ liệu thành schema ổn định và áp dụng bảo mật. Không biến một bridge quan sát thành cổng truy cập JMX không giới hạn; với metrics chuẩn và nhu cầu thu thập định kỳ, ưu tiên nền tảng observability phù hợp khi có thể.