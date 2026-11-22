# Đổi ObjectName và tác động tới dashboard hoặc script trong Spring Framework JMX

## 1. Vì sao đổi tên một MBean có thể gây lỗi vận hành?

Trong Java Management Extensions (JMX), mỗi MBean được đăng ký trong một `MBeanServer` dưới một `ObjectName`. Đây là định danh mà các JMX client dùng để tìm MBean, đọc attribute, gọi operation và đăng ký notification listener.

Một ObjectName có dạng:

```text
domain:key=value,key2=value2
```

Ví dụ:

```text
company.orders:type=QueueMonitor,name=primary
```

Nếu phiên bản mới đổi tên thành:

```text
company.orders:type=QueueMonitor,name=orders
```

MBean Java có thể vẫn hoạt động, Spring context có thể start thành công và JConsole vẫn hiển thị monitor, nhưng những công cụ đã cấu hình theo ObjectName cũ có thể không còn tìm thấy đối tượng. Dashboard trở nên trống, cảnh báo ngừng cập nhật, JMX exporter không thu thập metric hoặc script gặp `InstanceNotFoundException`.

**Đổi ObjectName là thay đổi hợp đồng quản trị JMX**, không chỉ là đổi tên nội bộ trong source code. Bài này hướng dẫn xác định phạm vi ảnh hưởng, thiết kế chính sách tương thích, triển khai migration và kiểm chứng bằng JMX API.

## 2. Phân biệt ObjectName, Spring bean name và Java class

Một resource có ít nhất ba tên:

| Khái niệm | Ví dụ | Phạm vi |
|---|---|---|
| Java class | `com.example.monitor.QueueMonitor` | Kiểu trong JVM |
| Spring bean name | `ordersQueueMonitor` | `ApplicationContext` / `BeanFactory` |
| JMX ObjectName | `company.orders:type=QueueMonitor,name=primary` | Một `MBeanServer` |

Ba tên không tự động đồng nhất. Tên Spring bean có thể thay đổi mà ObjectName vẫn được giữ nguyên nhờ explicit mapping; ngược lại ObjectName có thể bị thay khi không thay đổi Java class hoặc Spring bean name.

Ví dụ:

```java
exporter.setBeans(Map.of(
    "company.orders:type=QueueMonitor,name=primary",
    ordersQueueMonitor
));
```

Trong cấu hình này, key là ObjectName JMX. Đổi key sang `name=orders` là thay đổi địa chỉ MBean từ góc nhìn client.

Nếu dùng `@ManagedResource(objectName = "...")`, ObjectName có thể được khai báo trực tiếp trên bean. Nếu dùng `ObjectNamingStrategy`, tên hiệu lực có thể được sinh từ cấu hình, kiểu bean, tên bean hoặc giá trị khác. Với Spring Boot Actuator JMX, endpoint còn có domain/naming convention riêng.

**Điều cần kiểm tra là ObjectName đã đăng ký thực tế**, không chỉ tên annotation hoặc bean trong IDE.

## 3. ObjectName là một phần của API quản trị

Một JMX client thường gọi:

```java
ObjectName name = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);

Object depth = connection.getAttribute(name, "QueueDepth");
```

Nếu server đổi tên thành `name=orders` nhưng client vẫn dùng `name=primary`, lời gọi có thể thất bại vì tên cũ không còn đăng ký.

Các ràng buộc giống một API contract:

- **Tên miền (domain)**: `company.orders`.
- **Key properties**: `type`, `name`, `instance`, `service`...
- **Giá trị key**: `primary`, `orders`, `worker-1`.
- **Các attribute/operation** dưới ObjectName đó.
- **Notification subscription** đăng ký theo nguồn.
- **Quyền truy cập** có thể phụ thuộc domain/ObjectName trong môi trường có policy chi tiết.

Một thay đổi nhỏ ở bất kỳ thành phần nào có thể làm selector hoặc query không còn matching.

### 3.1. Khác biệt giữa key order và key value

Hai ObjectName:

```text
company.orders:type=QueueMonitor,name=primary
company.orders:name=primary,type=QueueMonitor
```

có cùng domain và tập key/value, nên biểu diễn cùng ObjectName xét theo quy tắc JMX. Thứ tự các key properties không phải thay đổi danh tính. Có thể dùng `ObjectName.getCanonicalName()` để tạo dạng ổn định cho so sánh.

Ngược lại:

```text
company.orders:type=QueueMonitor,name=primary
company.orders:type=QueueMonitor,name=orders
```

là hai tên khác nhau vì giá trị `name` khác.

Không dùng so sánh chuỗi thô để kết luận hai ObjectName khác nhau chỉ vì key order đã đảo; hãy parse thành `ObjectName` rồi so sánh hoặc canonicalize.

## 4. Những nơi dễ bị ảnh hưởng bởi đổi ObjectName

Tác động thường vượt xa JConsole:

| Thành phần | Cách phụ thuộc ObjectName | Triệu chứng khi đổi tên |
|---|---|---|
| JConsole script hoặc Java JMX client | `new ObjectName("...")` | `InstanceNotFoundException` |
| JMX monitoring exporter | Include rules theo domain/properties | Metric biến mất khỏi collector |
| Dashboard | Metric/label sinh từ ObjectName | Panel No data, series mới |
| Alert rule | Query metric cũ | Alert im lặng hoặc false positive |
| Automation script | `invoke` trên ObjectName cố định | Job quản trị không chạy |
| Notification listener | Đăng ký với ObjectName cụ thể | Không còn nhận notification từ MBean mới |
| Access policy | Quyền theo tên/domain | Client bị từ chối sau migration |
| Inventory hoặc audit | Tập ObjectName allowlist | Xuất hiện resource “lạ”, tên cũ mất |
| Integration test | Expected ObjectName | Test registration thất bại |

**Rủi ro lớn nhất đôi khi là lỗi im lặng:** monitoring exporter có thể không thu metric nào mà không làm Spring ứng dụng crash. Dashboard trống có thể bị hiểu nhầm là “không có lỗi”, trong khi thực tế không còn dữ liệu.

## 5. Khả năng phụ thuộc của dashboard và metric pipeline

Một luồng metrics phổ biến:

```text
MBeanServer
    |
    | ObjectName + attribute
    v
JMX collector / exporter
    |
    | metric name + labels
    v
Monitoring backend
    |
    +--> Dashboard panel
    +--> Recording rule
    +--> Alert rule
```

Có ít nhất hai kiểu phụ thuộc:

1. **Collector chọn ObjectName bằng selector.** Nếu selector không còn match, metric không được xuất.
2. **Collector tạo metric label hoặc metric name từ ObjectName.** Sau khi rename, metric vẫn có thể tồn tại nhưng dưới nhãn/tên mới; dashboard cũ vẫn mất dữ liệu.

Ví dụ một rule của JMX exporter được thiết kế cho:

```text
company.orders<type=QueueMonitor,name=primary><>QueueDepth
```

Sau khi tên đổi thành `name=orders`, một rule khớp chính xác `primary` sẽ không còn trúng. Cú pháp rule thực tế phụ thuộc exporter; dòng trên chỉ mô tả một kiểu pattern, không phải cấu hình universal.

Do đó đừng chỉ kiểm tra rằng `queryNames` thấy MBean mới. Hãy kiểm tra cả metrics được collector phát ra, labels thực tế và các query dashboard/alert.

## 6. Tác động đến cảnh báo: missing data không phải zero

Giả sử dashboard giám sát queue depth:

```text
old ObjectName -> queue_depth{queue="primary"} = 120
```

Sau rename, collector có thể không thu được series cũ:

```text
queue_depth{queue="primary"} -> absent / stale
```

Điều này **không tương đương `queue_depth=0`**. Nếu alert xử lý missing data như trạng thái bình thường, một queue quá tải có thể không được cảnh báo.

Cần thiết kế alert rule phân biệt:

- Giá trị số đo thật.
- Metric absent/stale.
- Exporter unavailable.
- JMX target chưa READY.
- Collector scrape thất bại.
- Rename đang trong giai đoạn migration.

Khi đổi ObjectName, nên có kiểm tra “metrics presence” hoặc health của collector, không chỉ cảnh báo ngưỡng như `QueueDepth > 100`.

## 7. Tác động đến script và proxy Spring

Một script có thể hard-code:

```java
ObjectName monitor = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);

connection.invoke(
    monitor,
    "resetCounters",
    new Object[0],
    new String[0]
);
```

Sau khi rename, thao tác có thể ném `InstanceNotFoundException` hoặc lỗi tương đương. Nếu script tự retry vô hạn, nó chỉ tạo log và tải không cần thiết.

Một Spring client proxy cũng có thể gắn ObjectName cố định:

```java
MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
proxy.setServer(connection);
proxy.setObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);
proxy.setProxyInterface(QueueManagementMBean.class);
```

Proxy có thể được tạo nhưng lời gọi đầu tiên tới tên cũ thất bại. **Tạo proxy thành công không chứng minh target ObjectName còn tồn tại.**

Nên cập nhật interface client/proxy config và integration test đi kèm trong kế hoạch migration, không chỉ thay annotation ở server.

## 8. Tác động đến NotificationListener

JMX listener đăng ký bằng ObjectName:

```java
connection.addNotificationListener(
    oldName,
    listener,
    filter,
    handback
);
```

Khi MBean được unregister và đăng ký lại dưới tên mới, registration cũ không tự động theo resource mới.

Trong Spring, một `NotificationListenerBean` cũng có thể sử dụng:

```java
listenerBean.setMappedObjectNames(
    "company.orders:type=QueueMonitor,name=primary"
);
```

Sau rename, mapping cần được cập nhật hoặc có chiến lược hỗ trợ cả hai tên trong giai đoạn chuyển tiếp.

JMX Notification không mặc nhiên là hàng đợi bền vững. Nếu listener chưa đăng ký với tên mới, những notification đã phát có thể không được replay. Khi migration ảnh hưởng cảnh báo quan trọng, có thể cần đọc trạng thái hiện tại qua attribute sau khi đăng ký lại để tránh mất khả năng phát hiện.

## 9. Tác động đến policy, permissions và allowlist

Một số hệ thống dùng domain/ObjectName trong chính sách truy cập hoặc allowlist monitoring. Khi đổi tên:

```text
Allowed:
  company.orders:type=QueueMonitor,name=primary

New:
  company.orders:type=QueueMonitor,name=orders
```

Chính sách cũ có thể không còn áp dụng. Có hai hướng rủi ro:

- Client mất quyền đọc/gọi dù được phép.
- Policy quá rộng hoặc fallback permission gây mở rộng truy cập ngoài mong đợi.

Cần kiểm tra authorization thực tế của JMX connector/server, chứ không chỉ xác thực rằng username/password còn đăng nhập được. Connection thành công không chứng minh quyền gọi attribute hoặc operation sau rename.

Đừng giải quyết bằng cách cấp toàn quyền cho cả domain chỉ để làm script hoạt động. Hãy cập nhật những rule có chủ đích và kiểm thử bằng identity có đúng quyền.

## 10. Chiến lược 1: giữ ObjectName ổn định

Cách có chi phí migration thấp nhất là **không đổi ObjectName** dù nội bộ ứng dụng đã refactor.

Ví dụ class và bean đổi tên:

```java
@ManagedResource(
    objectName = "company.orders:type=QueueMonitor,name=primary"
)
public class OrdersRuntimeStatus {
    // ...
}
```

JMX ObjectName vẫn giữ như cũ. Client có thể tiếp tục hoạt động nếu attribute/operation cũng giữ tương thích.

Đây là cách tốt khi:

- ObjectName cũ đã được nhiều dashboard/script sử dụng.
- Tên cũ chưa gây xung đột hoặc vấn đề bảo mật.
- Thay đổi chỉ là refactor nội bộ.
- Không cần phân biệt thêm instance mới.

Hãy coi ObjectName như một stable external identifier. Java class có thể đổi tên; ObjectName không nhất thiết phải phản ánh class hiện tại.

### Khi giữ nguyên tên không còn phù hợp

Nếu ObjectName cũ gây trùng nhiều module, chứa thông tin nhạy cảm hoặc không thể phân biệt instance, có thể cần đổi. Khi đó hãy dùng chiến lược migration rõ ràng, không đổi đột ngột trong một commit.

## 11. Chiến lược 2: hỗ trợ song song tên cũ và mới

Khi đổi ObjectName là cần thiết, một giai đoạn chuyển tiếp có thể đăng ký **hai ObjectName** để client cũ và mới có thời gian cập nhật.

```text
OLD:
company.orders:type=QueueMonitor,name=primary

NEW:
company.orders:type=QueueMonitor,name=orders
```

Cả hai tên nên trỏ tới cùng trạng thái quản trị hoặc các facade có hành vi nhất quán, để dashboard không báo số liệu mâu thuẫn.

Cần tránh giả định có thể đăng ký **cùng một MBean instance** dưới hai ObjectName trong mọi trường hợp. Một số implementation, lifecycle hoặc notification source có thể có ràng buộc registration riêng. Cách dễ kiểm soát là tạo hai facade MBean mỏng cùng đọc từ một state holder/service chung.

```text
        QueueRuntimeState
           /        \
          /          \
 LegacyMonitor    CurrentMonitor
       |               |
  ObjectName OLD    ObjectName NEW
       |               |
   old clients      new clients
```

Nếu cả hai facade có operation thay đổi trạng thái, cần xác định liệu caller có thể thực hiện operation hai lần qua hai tên. Khi chuyển tiếp, ưu tiên tên legacy chỉ đọc nếu có thể và giữ operation điều khiển tại một tên duy nhất.

### 11.1. Đừng đếm đôi metric

Nếu collector scrape cả OLD và NEW, có thể sinh hai series cho cùng một số liệu. Tổng hợp không cẩn thận sẽ đếm đôi.

Ví dụ hai ObjectName cùng báo `CompletedTotal=500`:

```text
old monitor -> 500
new monitor -> 500
```

Một dashboard `sum(...)` qua cả hai có thể hiển thị 1000 dù business thực tế chỉ hoàn tất 500 tác vụ.

Trong giai đoạn song song, cấu hình collector/recording rules chỉ chọn một nguồn làm primary cho mỗi logic metric; các series legacy có thể tồn tại để tương thích nhưng không được cộng vào cùng tổng.

## 12. Chiến lược 3: client discovery thay vì hard-code

Nếu hệ thống có nhiều instance, có thể dùng ObjectName pattern:

```java
Set<ObjectName> matches = connection.queryNames(
    new ObjectName("company.orders:type=QueueMonitor,*"),
    null
);
```

Client sau đó chọn target dựa trên key properties như `service`, `instance` hoặc `role`.

Discovery giúp giảm phụ thuộc vào một giá trị tên cứng, nhưng có điều kiện:

1. Pattern phải đủ hẹp để không bắt nhầm MBean khác.
2. Nếu có nhiều match, client phải chọn một cách có chủ đích.
3. Không tự gọi operation lên tất cả match nếu có tác dụng phụ.
4. Phải xử lý target xuất hiện/biến mất trong runtime.
5. Cần version/contract check qua `MBeanInfo`.
6. Không dùng discovery như một biện pháp thay thế authorization.

Nếu một proxy `MBeanProxyFactoryBean` cần target ObjectName cụ thể, bạn vẫn phải chọn một ObjectName sau discovery rồi cấu hình proxy phù hợp. Pattern dùng cho query không tự là một MBean duy nhất để proxy gọi.

## 13. Chiến lược 4: phiên bản hóa hợp đồng JMX

Với thay đổi không chỉ ở ObjectName mà còn ở attribute/operation, một chính sách versioning có thể hữu ích:

```text
company.orders:type=QueueMonitor,version=v1,name=primary
company.orders:type=QueueMonitor,version=v2,name=primary
```

Hoặc:

```text
company.orders.v1:type=QueueMonitor,name=primary
company.orders.v2:type=QueueMonitor,name=primary
```

Không có một chuẩn duy nhất cho việc đặt version trong ObjectName. Điều quan trọng là chọn convention thống nhất và được tài liệu hóa.

Một version mới nên có contract rõ:

- Attribute nào tồn tại và kiểu gì?
- Writable attribute nào được phép thay đổi?
- Operation nào thay đổi signature?
- Notification types/payload thay đổi không?
- ObjectName sẽ được giữ ổn định trong vòng đời version như thế nào?

Nếu chỉ refactor implementation không thay contract, tạo version mới có thể là không cần thiết. Versioning không nên làm ObjectName dài hoặc khó quản lý một cách vô ích.

## 14. Quy trình migration theo giai đoạn

Một quy trình an toàn gồm:

### Giai đoạn A — kiểm kê dependency

Tìm tất cả nơi tham chiếu ObjectName cũ:

- Java JMX clients, shell scripts và maintenance tools.
- Cấu hình JMX collector/exporter.
- Dashboard panel, alert, recording rules.
- Spring `MBeanProxyFactoryBean` configuration.
- `NotificationListenerBean.mappedObjectNames`.
- Access policy, inventory và test fixtures.
- Tài liệu runbook vận hành.

Ghi lại owner của từng consumer, tần suất sử dụng, quyền và mức độ quan trọng.

### Giai đoạn B — xác định contract mới

Quyết định tên mới, lý do thay đổi, phạm vi MBeanServer và các attribute/operation được giữ tương thích. Xác định cách chuyển tiếp: giữ tên cũ, alias song song hay cutover có downtime.

### Giai đoạn C — triển khai dual registration hoặc compatibility adapter

Nếu cần, đăng ký facade legacy và current. Kiểm tra chúng cùng phản ánh trạng thái đúng. Không để hai exporter tranh nhau cùng ObjectName hoặc tạo side effect trùng.

### Giai đoạn D — cập nhật consumer

Đổi selector ở collector, dashboard, alert, script và proxy. Chạy kiểm tra end-to-end trên môi trường staging. Đặc biệt xác nhận alert khi metric mất dữ liệu.

### Giai đoạn E — quan sát và deprecate

Trong thời gian chuyển tiếp, kiểm tra consumer nào còn đọc tên cũ. Không phải mọi JMX server cung cấp audit chi tiết tới từng getter; có thể cần log ở client, monitoring configuration hoặc access gateway để suy ra mức dùng.

### Giai đoạn F — loại bỏ tên cũ có chủ đích

Chỉ gỡ legacy MBean khi các consumer đã chuyển, quyền đã cập nhật và có rollback plan. Sau khi gỡ, xác minh không còn dashboard/script phụ thuộc tên cũ.

## 15. Ví dụ Java: đọc MBeanInfo trước và sau khi đổi tên

Đặt hai ObjectName:

```java
ObjectName oldName = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);
ObjectName newName = new ObjectName(
    "company.orders:type=QueueMonitor,name=orders"
);
```

Kiểm tra sự tồn tại:

```java
boolean oldPresent = server.isRegistered(oldName);
boolean newPresent = server.isRegistered(newName);

System.out.printf(
    "old=%s new=%s%n",
    oldPresent, newPresent
);
```

Kiểm tra hợp đồng:

```java
if (newPresent) {
    MBeanInfo info = server.getMBeanInfo(newName);

    for (MBeanAttributeInfo attr : info.getAttributes()) {
        System.out.printf(
            "%s type=%s read=%s write=%s%n",
            attr.getName(),
            attr.getType(),
            attr.isReadable(),
            attr.isWritable()
        );
    }

    for (MBeanOperationInfo op : info.getOperations()) {
        System.out.println(
            "operation=" + op.getName()
        );
    }
}
```

Các type cần import từ `javax.management`. Code này phải chạy với **đúng MBeanServer**; dùng platform server local của client JVM sẽ không kiểm tra được remote server nếu target ở JVM khác.

Đừng tự động gọi mọi operation khi migration: một operation có thể restart service, clear cache hoặc thay đổi dữ liệu. Metadata inventory là bước kiểm chứng phù hợp trước.

## 16. Ví dụ Spring: explicit ObjectName để ổn định

Thay vì phụ thuộc vào tên bean/class:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class StableJmxConfiguration {

    @Bean
    public QueueStatusMonitor queueStatusMonitor() {
        return new QueueStatusMonitor();
    }

    @Bean
    public MBeanExporter exporter(
            MBeanServer server,
            QueueStatusMonitor monitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "company.orders:type=QueueMonitor,name=primary",
            monitor
        ));
        return exporter;
    }
}
```

`QueueStatusMonitor` phải là JMX-compliant MBean hoặc được cấu hình assembler thích hợp. Khi class được refactor, mapping vẫn giữ ObjectName cũ.

Nếu sau này muốn đổi sang `name=orders`, thực hiện theo migration plan thay vì chỉ thay giá trị trong `Map.of` rồi deploy.

## 17. Ví dụ hỗ trợ legacy và current bằng facade

Một state holder:

```java
import java.util.concurrent.atomic.AtomicLong;

public class QueueRuntimeState {
    private final AtomicLong processed = new AtomicLong();

    public long getProcessed() {
        return processed.get();
    }

    public void recordProcessed() {
        processed.incrementAndGet();
    }
}
```

Management interface:

```java
public interface QueueMonitorMBean {
    long getProcessedTotal();
}
```

Hai facade khác nhau có thể dùng `StandardMBean` wrapper hoặc management interface phù hợp:

```java
public class QueueMonitorView implements QueueMonitorMBean {
    private final QueueRuntimeState state;

    public QueueMonitorView(QueueRuntimeState state) {
        this.state = state;
    }

    @Override
    public long getProcessedTotal() {
        return state.getProcessed();
    }
}
```

Vì tên class `QueueMonitorView` không tự khớp convention `QueueMonitorViewMBean`, có thể đăng ký bằng `StandardMBean` wrapper nếu dùng JMX thuần:

```java
QueueRuntimeState state = new QueueRuntimeState();

StandardMBean legacy = new StandardMBean(
    new QueueMonitorView(state),
    QueueMonitorMBean.class
);

StandardMBean current = new StandardMBean(
    new QueueMonitorView(state),
    QueueMonitorMBean.class
);

server.registerMBean(legacy, oldName);
server.registerMBean(current, newName);
```

Các import cần thiết:

```java
import javax.management.StandardMBean;
import javax.management.ObjectName;
```

Hai wrapper riêng cùng đọc state holder, tránh việc một MBean instance bị đăng ký hai lần ngoài dự kiến. Trong Spring, có thể dùng hai bean facade và `MBeanExporter` mapping riêng với assembler phù hợp.

Đây là một chiến lược compatibility cụ thể, không phải yêu cầu mọi ứng dụng phải dùng dual registration. Nếu tên cũ chỉ có ít consumer và có thể coordinated cutover, giữ một tên rồi cập nhật clients đồng thời có thể đơn giản hơn.

## 18. Đổi ObjectName bằng annotation trong Spring

Một bean annotation-based:

```java
@ManagedResource(
    objectName = "company.orders:type=QueueMonitor,name=primary"
)
public class QueueMetrics {
    @ManagedAttribute
    public long getProcessedTotal() { /* ... */ }
}
```

Nếu đổi annotation thành:

```java
@ManagedResource(
    objectName = "company.orders:type=QueueMonitor,name=orders"
)
```

thì exporter có thể đăng ký MBean ở tên mới khi context khởi tạo lại. Điều đó không tự tạo alias cho tên cũ.

Nếu ứng dụng đang dùng `@EnableMBeanExport` hoặc Spring Boot JMX auto-configuration, xác định exporter nào sở hữu resource và tránh cấu hình thêm exporter trùng lặp trong lúc migration.

ObjectName có thể bị override bằng naming strategy hoặc explicit mappings tùy cách export. Vì vậy phải quan sát `queryNames` sau startup, không chỉ tin annotation mới đã được áp dụng.

## 19. Những hiểu nhầm thường gặp

### 19.1. “Đổi ObjectName không đổi Java method nên client không bị ảnh hưởng”

Sai. Client dùng ObjectName để định vị MBean trước khi truy cập method. Tên thay đổi có thể làm client không tìm thấy resource.

### 19.2. “Thứ tự key property đổi là một ObjectName mới”

Không nhất thiết. Với cùng domain và cùng tập key/value, ObjectName canonicalization thể hiện danh tính tương đương.

### 19.3. “Dashboard trống nghĩa là QueueDepth bằng 0”

Không. Có thể metric missing/stale vì collector không còn match ObjectName. Cần phân biệt missing data.

### 19.4. “Đổi cấu hình Spring server là đủ”

Không. Client proxy, listener, collector, dashboard, alert, script và access policy có thể giữ tên cũ.

### 19.5. “Cứ đăng ký cùng một object hai lần là hỗ trợ backward compatibility”

Không nên mặc định. Lifecycle và notification behavior có thể phức tạp. Facade/wrapper riêng cùng state holder thường dễ kiểm soát hơn.

### 19.6. “Hai MBean cùng metric thì dashboard vẫn đúng”

Có nguy cơ double counting. Collector và aggregation cần xác định primary source trong giai đoạn dual registration.

### 19.7. “Query ObjectName pattern là đủ để tránh mọi breaking change”

Pattern có thể match nhiều resource khác nhau hoặc bỏ qua contract drift. Cần chọn target và kiểm tra `MBeanInfo`.

### 19.8. “Có thể bỏ alias legacy ngay khi code mới deploy”

Chưa chắc tất cả clients, cron jobs và monitoring configurations đã cập nhật. Cần xác minh dependency và deprecation window phù hợp.

## 20. Kiểm thử tương thích trong CI/CD

Một test có thể tạo Spring context và truy vấn ObjectNames dự kiến:

```java
ObjectName oldName = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);

assertTrue(server.isRegistered(oldName));
```

Khi muốn chuyển sang tên mới, mở rộng test để kiểm tra cả hai trong giai đoạn migration:

```java
assertTrue(server.isRegistered(oldName));
assertTrue(server.isRegistered(newName));
```

Sau khi deprecate, cập nhật test để kỳ vọng tên mới và xác nhận tên cũ không còn. Test phải chạy với MBeanServer cô lập hoặc quy hoạch ObjectName riêng để không phụ thuộc resource của JVM/test khác.

Ngoài registration, nên test:

- Attribute và operation signature vẫn đúng ở tên mới.
- Không có secret hoặc operation không intended bị export.
- Listener có thể đăng ký tới tên mới.
- Metrics collector thực sự phát series mong đợi.
- Dashboard query và alert rule có thể tìm series tương ứng.
- Các tài khoản quản trị được cấp đúng quyền.
- Cleanup khi context shutdown không để MBean thừa.

**Kiểm thử Spring context một mình chưa đủ cho pipeline metrics:** cần ít nhất một phép thử đầu-cuối ở staging để xác nhận exporter, label và dashboard/alert theo cấu hình thực tế.

## 21. Điều tra sự cố sau khi rename

Nếu JConsole thấy MBean mới nhưng dashboard không có dữ liệu, kiểm tra theo trình tự:

1. **Đúng JVM/MBeanServer?** JConsole/collector có đang kết nối cùng target không?
2. **MBean registered?** `queryNames` có ObjectName mới không?
3. **Metadata đúng?** `MBeanInfo` có attribute được collector đọc không?
4. **Collector rule match?** Rule có dùng domain/name cũ không?
5. **Scrape success?** Collector có lỗi query/permission không?
6. **Metric name/labels đổi?** Backend có series mới nhưng panel vẫn query series cũ không?
7. **Alert behavior?** Missing data có bị coi là OK không?
8. **Dual registration?** Có đếm đôi hay label mơ hồ không?
9. **Access control?** Quyền theo ObjectName mới đã được cấp chưa?
10. **Caching/restart?** Collector hoặc JMX client cần reload configuration/reconnect không?

Nếu automation script thất bại:

```text
InstanceNotFoundException
  -> kiểm tra ObjectName thật
  -> kiểm tra môi trường/instance
  -> cập nhật script theo migration plan

AttributeNotFoundException
  -> ObjectName có thể đúng nhưng contract đổi
  -> kiểm tra MBeanInfo attribute

ReflectionException / MBeanException
  -> kiểm tra operation signature và target runtime
```

Không tự động thay ObjectName bằng wildcard rộng để “có dữ liệu” nếu script có operation gây tác dụng phụ.

## 22. Runbook rollback khi đổi tên gây mất giám sát

Nếu sau deploy bị mất telemetry nghiêm trọng:

1. Xác nhận lỗi nằm ở ObjectName/collector rules chứ không phải MBeanServer hay network.
2. Nếu có dual registration, tạm giữ legacy tên cũ và chuyển collector về primary source phù hợp.
3. Nếu đã xóa legacy, cân nhắc rollback cấu hình/phiên bản hoặc bổ sung compatibility facade có kiểm soát.
4. Đồng bộ dashboard, recording rules và alert để tránh missing-data bị hiểu nhầm là healthy.
5. Xác nhận metrics/alert phục hồi bằng dữ liệu thực, không chỉ ứng dụng start.
6. Ghi nhận consumer bị bỏ sót để cập nhật inventory và migration checklist.

Không dùng `REPLACE_EXISTING` như cơ chế rollback mù khi không rõ ai đang sở hữu MBean. Điều đó có thể thay nhầm resource của module khác.

## 23. Bài tập thực hành

**Bài 1 — Rename và lỗi script.** Đăng ký `QueueMonitor` tại ObjectName cũ. Viết JMX client đọc `ProcessedTotal`. Đổi registration sang tên mới, giữ client cũ, quan sát `InstanceNotFoundException`, rồi cập nhật client.

**Bài 2 — Canonical ObjectName.** Tạo hai `ObjectName` có cùng key/value nhưng thứ tự khác; so sánh `equals` và `getCanonicalName()`. Sau đó đổi giá trị `name` và giải thích khác biệt.

**Bài 3 — Dashboard selector.** Viết cấu hình collector giả định chỉ match `name=primary`. Đổi tên thành `name=orders` và mô tả vì sao metric biến mất. Thiết kế sửa rule hoặc giai đoạn dual collection.

**Bài 4 — Dual facade.** Tạo hai MBean wrapper dùng cùng state holder. Đăng ký dưới old/new ObjectName, đọc cùng một counter và giải thích vì sao không được cộng hai series lại.

**Bài 5 — Notification migration.** Đăng ký listener theo ObjectName cũ, đổi nguồn sang tên mới. Kiểm tra listener không tự theo nguồn mới, rồi cập nhật mapping.

**Bài 6 — Access policy.** Trong môi trường test có JMX authorization, kiểm tra một tài khoản được quyền đọc tên cũ nhưng không đọc được tên mới. Cập nhật policy có chủ đích, không mở rộng toàn domain.

**Bài 7 — Integration test.** Tạo Spring context với exporter và một MBean. Assert ObjectName, MBeanInfo, attribute. Thay tên và điều chỉnh test theo từng giai đoạn migration.

**Bài 8 — Missing-data alert.** Thiết kế cảnh báo khi metric `queue_depth` biến mất khỏi backend, phân biệt nó với `queue_depth=0`. Mô tả cách xác nhận alert hoạt động trong staging.

## 24. Câu hỏi tự kiểm tra

1. ObjectName thuộc phạm vi nào và dùng để làm gì?
2. Đổi Spring bean name có bắt buộc đổi ObjectName không?
3. Hai ObjectName chỉ khác thứ tự key có phải hai MBean khác nhau?
4. Vì sao JConsole có MBean mới nhưng dashboard vẫn mất dữ liệu?
5. Missing metric khác giá trị zero như thế nào?
6. Những consumer nào ngoài Java JMX client phụ thuộc ObjectName?
7. Vì sao dual registration có nguy cơ double counting?
8. Khi nào nên giữ ObjectName cũ dù implementation đã refactor?
9. Vì sao `queryNames` với pattern rộng không nên được dùng để gọi hàng loạt operation?
10. Những bước nào cần trước khi xóa một legacy ObjectName?
11. Access policy có thể bị ảnh hưởng như thế nào sau khi rename?
12. Làm sao xác nhận migration đã thành công đầu-cuối?

## 25. Ghi nhớ

**ObjectName là một phần của API quản trị JMX.** Đổi domain hoặc key/value có thể làm Java client, Spring proxy, notification listener, monitoring exporter, dashboard, alert và automation script ngừng hoạt động dù MBean vẫn được đăng ký bình thường dưới tên mới.

Ưu tiên giữ ObjectName ổn định khi chỉ refactor nội bộ. Nếu bắt buộc đổi, hãy kiểm kê consumer, chọn chiến lược tương thích, cập nhật selector/quyền, kiểm tra MBeanInfo và telemetry đầu-cuối, quản lý deprecation window và chỉ gỡ tên legacy sau khi xác nhận không còn phụ thuộc.
