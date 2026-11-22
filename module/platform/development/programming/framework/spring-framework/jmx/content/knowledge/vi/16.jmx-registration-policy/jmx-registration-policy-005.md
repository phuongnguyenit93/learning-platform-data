# Đánh đổi khi thay thế MBean đang được sử dụng trong Spring JMX

## 1. Bối cảnh: thay thế MBean nghĩa là gì?

Trong Java Management Extensions (**JMX**), một MBean được đăng ký với **MBeanServer** bằng một **ObjectName** duy nhất. Các công cụ như JConsole, VisualVM, script quản trị và hệ thống giám sát truy cập MBean thông qua ObjectName đó.

Ví dụ ứng dụng xuất:

```text
com.example.orders:type=Queue,name=payments
```

Khi một Spring bean hoặc exporter khác cố đăng ký MBean mới với đúng ObjectName, sẽ xảy ra **xung đột tên**. Spring Framework hỗ trợ lựa chọn chính sách đăng ký qua `RegistrationPolicy`, trong đó có **`REPLACE_EXISTING`**: thay MBean đã đăng ký bằng MBean mới.

Việc thay thế có thể giải quyết nhu cầu triển khai lại hoặc chuyển quyền sở hữu một tên quản trị. Tuy nhiên, nếu MBean cũ **đang được client sử dụng**, hành động thay thế mang theo các đánh đổi về:

- Tính liên tục khi đọc attribute hoặc gọi operation.
- Khả năng tương thích của metadata và hợp đồng JMX.
- Notification listener và subscription đang hoạt động.
- Trạng thái bên trong MBean.
- Quyền sở hữu và vòng đời của các Spring ApplicationContext.
- Hành vi trong khoảng thời gian hủy đăng ký rồi đăng ký lại.
- Rủi ro client điều khiển nhầm resource sau khi ObjectName được tái sử dụng.

Điểm quan trọng: **ObjectName không phải là danh tính của đối tượng Java bất biến theo thời gian**. Nó là tên trong registry. Sau khi thay thế, cùng một ObjectName có thể trỏ tới một MBean khác với trạng thái và hành vi mới.

## 2. Ba chính sách xử lý trùng tên

Spring cung cấp `org.springframework.jmx.support.RegistrationPolicy` để định nghĩa cách exporter xử lý tình huống một ObjectName đã được dùng.

| Chính sách | Hành vi | Ý nghĩa vận hành |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Báo lỗi khi tên đã đăng ký | Phát hiện xung đột và buộc xác định chủ sở hữu |
| `IGNORE_EXISTING` | Bỏ qua đăng ký MBean mới nếu tên đã có | Giữ MBean hiện hữu, nhưng bean mới có thể không được quản trị |
| `REPLACE_EXISTING` | Gỡ đăng ký MBean cũ và đăng ký MBean mới | Chuyển nội dung gắn với ObjectName, nhưng có rủi ro gián đoạn và thay đổi hợp đồng |

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import java.util.Map;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(PaymentQueueAdmin queueAdmin) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=payments",
            queueAdmin
        ));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.REPLACE_EXISTING
        );

        return exporter;
    }
}
```

`PaymentQueueAdmin` là một bean minh họa; trong ứng dụng thật nó cần là MBean hợp lệ hoặc được xuất bằng metadata assembler phù hợp. Chính sách `REPLACE_EXISTING` không làm method của bean tự động an toàn; nó chỉ điều chỉnh **hành vi đăng ký khi trùng ObjectName**.

### Cần hiểu đúng “replace”

Replace không phải một phép cập nhật tại chỗ lên Java object của MBean cũ. Thông thường exporter phải **unregister** tên đang tồn tại rồi **register** MBean mới. Điều này có thể kích hoạt các sự kiện đăng ký/hủy đăng ký và tạo ra một khoảng thời gian mà ObjectName không có MBean tương ứng.

Không nên giả định toàn bộ quá trình replace là transaction nguyên tử hoặc các lời gọi client sẽ luôn được chuyển tiếp trơn tru sang MBean mới.

## 3. Khi MBean đang được sử dụng, ai có thể bị ảnh hưởng?

Một ObjectName có thể đang là điểm phụ thuộc của nhiều consumer:

```text
                      +-- JConsole: xem attributes
                      |
                      +-- Monitoring collector: poll mỗi 10 giây
                      |
MBeanServer/ObjectName+-- Automation script: gọi resetStatistics()
                      |
                      +-- Alerting service: theo dõi queue depth
                      |
                      +-- Notification listener: nhận cảnh báo
```

Các consumer này không nhất thiết biết rằng MBean đã bị thay đổi. Họ chỉ biết ObjectName, attribute hoặc operation.

Sau khi replace:

1. Client có thể tiếp tục truy vấn ObjectName và nhận **đối tượng mới**.
2. Một lời gọi đang diễn ra có thể thành công trên MBean cũ, bị lỗi, hoặc thực thi trên MBean mới tùy thời điểm và cơ chế dispatch.
3. Metadata của MBean mới có thể khác: attribute/operation cũ không còn.
4. Subscription notification gắn với MBean cũ có thể không còn hiệu lực như trước.
5. Trạng thái MBean mới có thể bắt đầu lại từ giá trị mặc định hoặc snapshot khác.
6. Spring context cũ có thể vẫn sở hữu lifecycle của resource, dẫn tới vấn đề khi nó đóng.

Vì vậy, thao tác replace cần được xem như **thay đổi hợp đồng quản trị đang hoạt động**, dù tên vẫn giữ nguyên.

## 4. Đánh đổi thứ nhất: tính sẵn sàng khi truy cập

Giả sử một công cụ giám sát đọc:

```java
connection.getAttribute(
    new ObjectName("com.example.orders:type=Queue,name=payments"),
    "PendingCount"
);
```

Trong lúc exporter thay thế MBean, có thể xảy ra:

```text
T0: Old MBean đang đăng ký
T1: unregister Old MBean
T2: ObjectName tạm thời không tồn tại
T3: register New MBean
T4: Client đọc thành công từ New MBean
```

Nếu client gọi đúng T2, `getAttribute` có thể thất bại với `InstanceNotFoundException`.

Nếu việc register mới thất bại ở T3, tên có thể tiếp tục không có MBean, tùy cách triển khai và xử lý lỗi. Đây là lý do không thể coi replace mặc nhiên là cập nhật không gián đoạn.

### Tác động đến monitoring

Một collector có thể ghi nhận:

- Một hoặc nhiều lần scrape lỗi.
- Khoảng trống dữ liệu.
- Một cảnh báo giả do metric tạm thời mất.
- Metric đột ngột thay đổi vì MBean mới dùng trạng thái khác.

Với metric không quá quan trọng, một khoảng gián đoạn ngắn có thể chấp nhận được. Với các operation điều khiển vận hành, việc ObjectName tạm thời biến mất hoặc chuyển sang resource mới cần được tính đến trong quy trình triển khai.

### Kết luận thiết kế

Nếu yêu cầu là **không có khoảng trống quản trị**, replace cùng ObjectName có thể không đáp ứng yêu cầu đó. Cần cân nhắc lifecycle rõ ràng hơn, thay thế tài nguyên bên dưới một MBean ổn định, hoặc cơ chế chuyển đổi có kiểm soát.

## 5. Đánh đổi thứ hai: hợp đồng metadata có thể thay đổi

Các client JMX sử dụng `MBeanInfo` để biết một MBean công bố:

- Attributes: tên, kiểu, readable/writable.
- Operations: tên, tham số, kiểu trả về.
- Notifications: các loại sự kiện hỗ trợ.
- Descriptions và descriptors.

Ví dụ MBean cũ:

```text
ObjectName: com.example.orders:type=Queue,name=payments

Attributes:
  PendingCount : long [read-only]
  Enabled      : boolean [read/write]

Operations:
  resetStatistics() : void
```

MBean mới:

```text
Attributes:
  QueueDepth : int [read-only]
  Enabled    : boolean [read-only]

Operations:
  clearQueue() : void
```

Dù ObjectName không đổi, các client cũ có thể lỗi vì:

- `PendingCount` không còn.
- `Enabled` không còn writable.
- `resetStatistics()` bị xóa.
- Kiểu số `long` chuyển thành `int`.
- `clearQueue()` có tác động rất khác so với reset metric.

**Giữ nguyên ObjectName không có nghĩa giữ nguyên API quản trị.**

### Tương thích nên được kiểm tra thế nào?

Trước khi thay:

1. Lấy `MBeanInfo` của MBean đang chạy.
2. Xác định những attributes/operations/notifications được client sử dụng.
3. So sánh với metadata của MBean mới trong một môi trường riêng.
4. Đánh giá thay đổi breaking, đặc biệt là tên và kiểu.
5. Cập nhật collector/script/dashboard trước hoặc theo quy trình chuyển đổi.
6. Xác nhận client hoạt động sau khi thay.

Một client có typed proxy có thể chịu tác động lớn hơn nếu method Java proxy không còn tương thích với hợp đồng mới.

## 6. Đánh đổi thứ ba: mất trạng thái quản trị

Nhiều MBean chứa trạng thái nội bộ:

- Bộ đếm từ lần khởi động.
- Trạng thái tác vụ quản trị.
- Thời điểm gọi operation gần nhất.
- Lỗi gần nhất.
- Cache hoặc snapshot metric.
- Trạng thái bật/tắt của subsystem.

Khi thay MBean cũ bằng đối tượng mới, những trạng thái đó có thể được khởi tạo lại.

Ví dụ:

```text
Old MBean:
  ProcessedCount = 150000
  LastResetTime = 10:00

New MBean:
  ProcessedCount = 0
  LastResetTime = null
```

Monitoring có thể hiểu sai việc counter giảm về 0 nếu không biết đây là một lần reset/replace.

### Tách MBean khỏi resource để giảm tác động

Một thiết kế là giữ **tài nguyên nghiệp vụ** độc lập và dùng MBean như một adapter:

```text
PaymentQueueService (giữ trạng thái thật)
              |
      PaymentQueueAdmin (JMX adapter)
              |
          MBeanServer
```

Nếu thay adapter nhưng vẫn tham chiếu tới cùng `PaymentQueueService`, trạng thái nghiệp vụ có thể không bị mất. Tuy nhiên, trạng thái riêng của adapter vẫn có thể mất và việc chuyển đổi vẫn cần xử lý concurrency.

Ví dụ:

```java
public interface PaymentQueueAdminMBean {
    long getPendingCount();
}
```

```java
public final class PaymentQueueAdmin
        implements PaymentQueueAdminMBean {

    private final PaymentQueueService service;

    public PaymentQueueAdmin(PaymentQueueService service) {
        this.service = service;
    }

    @Override
    public long getPendingCount() {
        return service.pendingCount();
    }
}
```

`PaymentQueueService` là dependency minh họa; cần định nghĩa và quản lý lifecycle trong ứng dụng thật.

## 7. Đánh đổi thứ tư: notification listener và subscription

JMX hỗ trợ notification qua `NotificationBroadcaster` và `NotificationListener`. Một client có thể đăng ký listener để nhận cảnh báo khi queue vượt ngưỡng hoặc MBean thay đổi trạng thái.

Khi unregister MBean cũ:

- Subscription có thể gắn với broadcaster của MBean cũ.
- MBean mới là một đối tượng khác và không nhất thiết kế thừa listener/subscription cũ.
- Notification phát trong khoảng chuyển đổi có thể không đến client.
- Client cần cơ chế phát hiện registration thay đổi và đăng ký listener lại.

Một phương pháp theo dõi thay đổi registry là lắng nghe notification từ **`JMImplementation:type=MBeanServerDelegate`**, MBean delegate công bố các sự kiện đăng ký/hủy đăng ký của MBeanServer.

Sơ đồ:

```text
Client
  |
  +-- Subscribe to MBean notifications
  |
  +-- Subscribe to MBeanServerDelegate
          |
          +-- UNREGISTRATION_NOTIFICATION
          +-- REGISTRATION_NOTIFICATION
                  |
                  v
       Refresh metadata / re-subscribe
```

Đây là gợi ý kiến trúc cho client cần thích nghi với việc thay MBean. Không phải mọi client JMX đều tự động re-subscribe sau replace; cần xác minh với công cụ đang dùng.

### Đừng nhầm notification với hàng đợi bền vững

JMX notification là cơ chế thông báo runtime. Không có bảo đảm tương đương hệ thống message queue bền vững hoặc replay sự kiện sau mất kết nối. Nếu cảnh báo không được phép mất, cần một cơ chế sự kiện đáng tin cậy hơn ở tầng ứng dụng.

## 8. Đánh đổi thứ năm: quyền sở hữu giữa nhiều Spring context

Giả sử một JVM chứa hai Spring `ApplicationContext`:

```text
Context A
  └── MBeanExporter A
       └── ObjectName = com.example:type=Cache,name=primary

Context B
  └── MBeanExporter B
       └── ObjectName = com.example:type=Cache,name=primary
```

Nếu Context B dùng `REPLACE_EXISTING`, MBean của Context A có thể bị hủy đăng ký và bị thay bởi MBean của Context B.

Các vấn đề:

1. Context A có thể vẫn nghĩ nó chịu trách nhiệm quản lý MBean đó.
2. Khi Context A đóng, logic hủy đăng ký có thể ảnh hưởng tới MBean hiện tại nếu ownership/lifecycle không được xử lý đúng.
3. Context B có thể bị đóng trước, để lại trạng thái không còn MBean dù Context A vẫn hoạt động.
4. MBean mới có thể điều khiển resource khác nhưng giữ cùng tên.
5. Đội vận hành khó xác định context nào là chủ sở hữu hợp lệ.

**Registration policy là chính sách xử lý xung đột, không phải cơ chế xác định quyền sở hữu nghiệp vụ.**

### Cách thiết kế ownership rõ ràng

- Mỗi ObjectName có một owner được định nghĩa.
- Chỉ owner đó đăng ký/hủy đăng ký.
- Các context khác dùng proxy/client để truy cập thay vì đăng ký cùng tên.
- Nếu mỗi context cần một MBean riêng, thêm key định danh context/resource ổn định.
- Khi có handover, thực hiện quy trình chuyển quyền sở hữu có kiểm soát.

## 9. Đánh đổi thứ sáu: thao tác quản trị đang chạy

Một MBean có thể có operation như:

```java
@ManagedOperation
public void rebuildIndex() {
    // Long-running maintenance task.
}
```

Nếu replace xảy ra khi `rebuildIndex()` đang chạy, việc unregister MBean không nhất thiết dừng thread đã được gọi vào method cũ. Java object cũ có thể vẫn được tham chiếu bởi thread, task hoặc resource khác.

Từ đó có thể xảy ra:

```text
T0: Client gọi rebuildIndex() trên Old MBean
T1: Old MBean bắt đầu tác vụ dài
T2: Exporter unregister Old MBean
T3: Exporter register New MBean
T4: Client khác gọi rebuildIndex() trên New MBean
T5: Hai tác vụ có thể chạy cùng lúc
```

Thay MBean không tự bảo đảm **single-flight** hoặc mutex chung giữa phiên bản cũ và mới.

### Cần tách lifecycle của resource và MBean

Nếu operation thay đổi resource dùng chung, hãy kiểm soát concurrency tại resource/service, không chỉ bằng biến `running` trong adapter MBean.

Ví dụ hai adapter cũ/mới cùng tham chiếu tới một service có state machine duy nhất:

```text
Old MBean ─┐
           ├── SharedReindexService
New MBean ─┘        |
                    +-- single-flight
                    +-- operation ID
                    +-- status
```

Như vậy, cả hai adapter dùng chung cơ chế kiểm soát. Nếu resource cũ và mới là hai đối tượng độc lập, cần thêm handover protocol để tránh tác vụ cạnh tranh trên cùng dữ liệu hoặc hệ thống ngoài.

## 10. Thay thế có luôn cần thiết không?

Có nhiều trường hợp nhu cầu thực tế không đòi hỏi unregister/register MBean.

### 10.1. Chỉ thay đổi dữ liệu hoặc trạng thái

Nếu cần cập nhật attribute, sử dụng setter hoặc operation trên cùng MBean.

```text
MBean giữ nguyên ObjectName và instance
    |
    +-- setConfiguration(...)
    +-- refreshSnapshot()
    +-- resetStatistics()
```

Cách này tránh gián đoạn tên trong registry, nhưng các operation vẫn phải được thiết kế an toàn.

### 10.2. Muốn thay implementation bên dưới

Có thể giữ một MBean adapter ổn định và đổi delegate theo một cơ chế thread-safe:

```text
Stable MBean
    |
    +-- AtomicReference<ManagedService>
              |
              +-- Service V1
              +-- Service V2
```

Ví dụ minh họa:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class StableServiceAdmin implements StableServiceAdminMBean {
    private final AtomicReference<ManagedService> delegate;

    public StableServiceAdmin(ManagedService initial) {
        this.delegate = new AtomicReference<>(
            Objects.requireNonNull(initial)
        );
    }

    @Override
    public String getStatus() {
        return delegate.get().status();
    }

    public void replaceDelegate(ManagedService next) {
        delegate.set(Objects.requireNonNull(next));
    }
}
```

`ManagedService` và `StableServiceAdminMBean` là những interface cần định nghĩa ở ứng dụng thật. Đoạn code cho thấy cách thay tham chiếu atomically; nó **không tự quản lý các lời gọi đang chạy** trên delegate cũ, tài nguyên chưa dọn dẹp hoặc khả năng tương thích của hai implementation. Nếu yêu cầu không có lời gọi nào chạy trên service cũ sau cutover, cần cơ chế drain/quiesce riêng.

### 10.3. Cần một API mới không tương thích

Nếu hợp đồng quản trị thay đổi đáng kể, cân nhắc đăng ký tên mới:

```text
com.example.orders:type=QueueAdmin,version=v1,name=payments
com.example.orders:type=QueueAdmin,version=v2,name=payments
```

Trong giai đoạn chuyển đổi, hai MBean có thể cùng tồn tại với tên khác nhau. Điều này cho phép client nâng cấp từng bước, nhưng cần tránh để hai MBean đồng thời thực hiện lệnh nguy hiểm mà không phối hợp.

## 11. Khi nào REPLACE_EXISTING là lựa chọn hợp lý?

Replace có thể phù hợp nếu:

- Một thành phần sở hữu rõ ràng ObjectName.
- MBean hiện tại chắc chắn là instance cũ cần thay.
- Không có operation dài chưa được kiểm soát.
- Hợp đồng attributes/operations không thay đổi gây breaking cho client.
- Trạng thái cần duy trì nằm ở resource chung hoặc có cơ chế chuyển giao.
- Gián đoạn ngắn khi unregister/register được chấp nhận.
- Client có thể xử lý lỗi tạm thời và làm mới metadata/subscription.
- Lifecycle của exporter và context được tổ chức rõ.
- Có giám sát xác nhận MBean mới thực sự xuất hiện và hoạt động.

Ví dụ trong một môi trường phát triển, context reload có thể tái đăng ký một MBean quản trị ít quan trọng. Replace có thể thuận tiện hơn fail nếu đã biết rõ rằng MBean cũ bị bỏ lại do cơ chế reload và owner duy nhất kiểm soát cả hai phiên bản.

Ngược lại, trong môi trường production có nhiều context dùng chung platform MBeanServer, không nên đặt `REPLACE_EXISTING` cho mọi exporter như chính sách chung.

## 12. Quy trình handover MBean có kiểm soát

Nếu vẫn cần thay MBean cùng tên, có thể dùng quy trình:

### Bước 1: Xác định owner

Ghi nhận context/exporter nào đang sở hữu tên và resource nào được quản lý.

### Bước 2: Khảo sát client

Liệt kê dashboard, script, JConsole session, listener và những operation đang sử dụng.

### Bước 3: So sánh metadata

Đọc `MBeanInfo` cũ và mới, xác nhận các attribute/operation bắt buộc vẫn tương thích.

### Bước 4: Kiểm tra trạng thái và tác vụ đang chạy

Nếu có operation dài, chuyển sang trạng thái drain/quiesce hoặc chờ hoàn tất theo hợp đồng. Không giả định unregister sẽ hủy tác vụ.

### Bước 5: Chuẩn bị MBean mới

Khởi tạo resource, validate configuration, bảo đảm MBean mới compliant và có thể được đăng ký. Có thể kiểm thử MBean mới dưới ObjectName tạm trong MBeanServer riêng, hoặc trong môi trường thử nghiệm.

### Bước 6: Chuyển đổi

Thực hiện unregister/register qua cơ chế owner có kiểm soát. Nếu dùng Spring `REPLACE_EXISTING`, cần hiểu giới hạn và xử lý lỗi thực tế của exporter.

### Bước 7: Xác minh

Kiểm tra ObjectName đã đăng ký, `MBeanInfo` đúng, attribute đọc được, notification listener được phục hồi nếu cần.

### Bước 8: Theo dõi

Giám sát lỗi scrape, lỗi invoke, thay đổi đột ngột của metric và trạng thái tác vụ sau cutover.

### Bước 9: Xác định rollback

Nếu cần rollback, phải biết trạng thái có thể chuyển lại hay không. Với side effect nghiệp vụ đã được MBean mới thực hiện, việc đăng ký lại MBean cũ không tự đảo ngược tác động.

## 13. Xác minh MBean trước và sau replace bằng API

### Kiểm tra tên được đăng ký

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=payments"
);

System.out.println("Registered: " + server.isRegistered(name));
```

`isRegistered` cho biết có một MBean dưới tên đó, **không cho biết đó là phiên bản cũ hay mới**.

### Đọc metadata

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTRIBUTE %s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "OPERATION %s return=%s%n",
        operation.getName(),
        operation.getReturnType()
    );
}
```

Metadata giúp kiểm tra hợp đồng, nhưng nếu hai implementation công bố cùng MBeanInfo thì chưa đủ xác định chắc chắn phiên bản runtime. Có thể công bố attribute quản trị an toàn như `ImplementationVersion` hoặc `Generation` để client biết mốc thay thế.

### Kiểm tra trạng thái vận hành

Đọc các attribute quan trọng như:

```text
Status
PendingCount
LastSuccessfulOperation
ImplementationVersion
```

Với operation có side effect, không dùng một lệnh thử nguy hiểm chỉ để xác nhận MBean hoạt động. Ưu tiên getter/read-only diagnostics.

## 14. Theo dõi thay đổi registry qua MBeanServerDelegate

JMX có MBean hệ thống `JMImplementation:type=MBeanServerDelegate`, có thể phát `MBeanServerNotification` khi MBean được đăng ký hoặc hủy đăng ký.

Một listener minh họa:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerNotification;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class RegistryObserver {

    public static void subscribe(MBeanServer server)
            throws Exception {

        ObjectName delegate = new ObjectName(
                "JMImplementation:type=MBeanServerDelegate"
        );

        NotificationListener listener = (notification, handback) -> {
            if (notification instanceof MBeanServerNotification event) {
                System.out.println(
                    notification.getType()
                    + " : " + event.getMBeanName()
                );
            }
        };

        server.addNotificationListener(
                delegate,
                listener,
                null,
                null
        );
    }
}
```

Ví dụ trên dùng cú pháp Java hiện đại `instanceof ... event`; với Java đời cũ hơn, cần cast theo cú pháp truyền thống.

Nếu muốn tự làm client hỗ trợ replace, có thể quan sát sự kiện registry, cập nhật metadata và đăng ký lại listener của MBean đích khi thấy tên được đăng ký trở lại. Cần quản lý vòng đời listener để tránh leak.

**Giới hạn:** notification có thể bị bỏ lỡ khi client mất kết nối. Client vẫn cần cơ chế query lại trạng thái registry sau khi reconnect.

## 15. Không dùng REPLACE_EXISTING để sửa mọi lỗi cấu hình

Khi gặp `InstanceAlreadyExistsException`, nguyên nhân có thể là:

1. Hai bean khác nhau dùng cùng ObjectName.
2. Hai `ApplicationContext` cùng export một bean.
3. Một MBean đã được đăng ký thủ công và một exporter muốn đăng ký lại.
4. ObjectName được hard-code quá chung.
5. Bean/proxy được khởi tạo nhiều lần.
6. Context cũ chưa unregister MBean.
7. Một thư viện/framework đã đăng ký tên mà ứng dụng muốn dùng.

Chọn replace ngay có thể làm mất dấu nguyên nhân thật. Giải pháp tốt hơn thường là:

- Thêm key phân biệt như `application`, `context`, `name`.
- Đảm bảo chỉ một exporter làm owner.
- Kiểm tra lifecycle đăng ký/hủy đăng ký.
- Dùng explicit naming hoặc `ObjectNamingStrategy` nhất quán.
- Dùng `FAIL_ON_EXISTING` trong môi trường cần phát hiện lỗi sớm.

**Replace chỉ phù hợp khi việc xóa MBean hiện hữu thực sự là hành vi mong muốn.**

## 16. IGNORE_EXISTING có an toàn hơn không?

`IGNORE_EXISTING` tránh unregister MBean hiện tại nên giảm rủi ro ngắt client đang dùng MBean cũ. Tuy nhiên, nó có đánh đổi khác:

- Bean mới không được export như mong muốn.
- Người vận hành có thể thấy số liệu từ bản cũ dù ứng dụng mới đã chạy.
- Một ObjectName có thể âm thầm trỏ tới owner không đúng.
- Nếu MBean cũ bị hủy sau đó, MBean mới không nhất thiết tự được đăng ký thay.

Do đó `IGNORE_EXISTING` phù hợp khi MBean hiện hữu là tài nguyên dùng chung và việc không đăng ký bean mới là chủ ý đã được xác định, không phải cách bỏ qua xung đột chưa hiểu.

### So sánh theo mục tiêu

| Mục tiêu | Chính sách hợp lý hơn |
| --- | --- |
| Phát hiện sai cấu hình tên và ownership | `FAIL_ON_EXISTING` |
| Giữ MBean đã có được xác định là owner hợp lệ | `IGNORE_EXISTING` |
| Chuyển quyền sở hữu và thay MBean có kiểm soát | `REPLACE_EXISTING` |
| Cần không gián đoạn hoặc chuyển đổi client từ từ | Cân nhắc adapter ổn định hoặc ObjectName phiên bản mới |

## 17. Trường hợp đặc biệt: remote client đang giữ proxy

Một JMX client có thể tạo typed proxy:

```java
import javax.management.JMX;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

PaymentQueueAdminMBean proxy = JMX.newMBeanProxy(
        connection,
        new ObjectName(
            "com.example.orders:type=Queue,name=payments"
        ),
        PaymentQueueAdminMBean.class
);
```

Proxy thường gửi lời gọi qua ObjectName và connection. Nếu MBean được thay dưới cùng tên, lời gọi tiếp theo có thể tới MBean mới.

Nhưng điều đó chỉ hoạt động nếu:

- MBean mới công bố đúng các attributes/operations cần thiết.
- Kiểu tham số và kết quả tương thích.
- Quyền truy cập vẫn cho phép.
- MBean đã được đăng ký khi lời gọi xảy ra.

Một typed proxy không khóa ObjectName vào đúng Java object cũ. Nếu contract mới khác, proxy có thể gặp lỗi runtime. Nếu client giữ thêm metadata cache hoặc notification subscription, việc thay MBean có thể yêu cầu refresh/re-subscribe.

## 18. Trường hợp đặc biệt: Model MBean và metadata cache

Spring có thể xuất POJO qua Model MBean dựa trên metadata. Một Model MBean có thể có descriptor điều khiển cache attribute, ví dụ `currencyTimeLimit`.

Khi thay Model MBean:

- Giá trị cache cũ của Model MBean có thể mất.
- Metadata descriptor có thể thay đổi.
- Getter của resource mới có thể phản ánh dữ liệu khác.
- Client đọc trước/sau có thể thấy biến động không do hoạt động nghiệp vụ.

Nếu dashboard dựa vào counter, cần hiểu liệu counter nằm ở business service hay chỉ nằm trong adapter/cache metadata. Việc reset/replace có thể tạo ranh giới thống kê mới.

## 19. Trường hợp đặc biệt: multi-replica và nhiều JVM

Mỗi JVM có MBeanServer riêng, nên cùng ObjectName trên hai JVM **không phải xung đột đăng ký**.

```text
JVM A:
  com.example.orders:type=Queue,name=payments

JVM B:
  com.example.orders:type=Queue,name=payments
```

`REPLACE_EXISTING` ở JVM B không thay MBean của JVM A. Tuy nhiên, hệ thống giám sát tập trung phải gắn nhãn target/instance để phân biệt dữ liệu.

Nếu nhiều Spring context trong **cùng JVM** dùng chung MBeanServer, xung đột lại có thể xảy ra. Đừng nhầm khái niệm “nhiều application” với “nhiều MBeanServer”: phạm vi duy nhất luôn là server cụ thể.

## 20. Quan sát và cảnh báo sau khi thay thế

Một quy trình replace nên có tín hiệu đo lường:

| Tín hiệu | Điều cần phát hiện |
| --- | --- |
| MBean registration count | Tên có biến mất/đăng ký lại đúng không |
| Scrape errors | Collector có đọc lỗi trong quá trình replace không |
| Attribute schema | Tên, kiểu, readable/writable có giữ nguyên không |
| Operation failures | Script có gọi thiếu operation hoặc sai signature không |
| Notification subscription health | Listener có nhận lại event sau replace không |
| Resource status | Tài nguyên mới đã sẵn sàng chưa |
| Active job count | Có tác vụ cũ và mới chạy chồng lấn không |
| State continuity | Counter, config, job status có thay đổi bất thường không |

Có thể xuất một attribute `Generation` hoặc `ImplementationVersion` chỉ đọc để việc chẩn đoán đơn giản hơn:

```java
@ManagedAttribute(
    description = "Generation of this management adapter"
)
public String getGeneration() {
    return generation;
}
```

Không nên đưa secret hoặc thông tin build nhạy cảm vào attribute. Giá trị generation cũng cần được thiết kế theo mục đích: định danh triển khai, vòng đời adapter hay phiên bản giao diện quản trị.

## 21. Ví dụ diễn biến sự cố

Một ứng dụng có MBean:

```text
ObjectName: com.example.cache:type=Cache,name=products
HitCount: 120000
Operations: clear(), resetStatistics()
```

Một Spring context mới khởi động và dùng `REPLACE_EXISTING` cho cùng tên. MBean mới chỉ công bố:

```text
HitCount: 0
Operations: clear()
```

Kết quả:

1. Dashboard thấy `HitCount` giảm đột ngột từ 120000 về 0.
2. Script gọi `resetStatistics()` gặp lỗi vì operation không còn.
3. JConsole vẫn nhìn thấy ObjectName cũ và có thể khiến người vận hành tưởng MBean không đổi.
4. Listener đăng ký cho MBean cũ không nhất thiết nhận notification của MBean mới.
5. Khi context cũ dừng, vòng đời export cần được kiểm tra để tránh xóa nhầm tên hiện tại.

Cách xử lý đúng phải bắt đầu từ **hợp đồng và ownership**. Nếu chỉ cần thay code tính metric, một adapter ổn định hoặc một bước chuyển phiên bản có kiểm soát có thể giảm gián đoạn đáng kể.

## 22. Checklist trước khi bật REPLACE_EXISTING

Trả lời các câu hỏi sau trước khi chọn chính sách thay thế:

1. ObjectName hiện tại do exporter/context nào sở hữu?
2. MBean đang phục vụ những client/script/dashboard nào?
3. Có notification listener đang đăng ký không?
4. MBean cũ có operation đang chạy không?
5. MBean mới có giữ nguyên attribute/operation contract không?
6. Có state trong adapter cần chuyển giao không?
7. Resource cũ có thể dừng an toàn trước khi resource mới hoạt động không?
8. Có thể chấp nhận khoảng ngắn ObjectName không tồn tại không?
9. Có cách xác minh MBean mới đang là implementation mong đợi không?
10. Nếu registration mới thất bại, hệ thống làm gì?
11. Nếu cần rollback, liệu operation mới đã thực hiện có thể đảo ngược không?
12. Sau replace, client có refresh metadata và re-subscribe notification không?
13. Context/exporter cũ có thể vô tình unregister MBean mới không?
14. Có thể dùng tên mới hoặc adapter ổn định để tránh replace không?

Những câu hỏi này biến lựa chọn registration policy thành quyết định thiết kế có thể kiểm chứng, thay vì một cờ cấu hình đơn lẻ.

## 23. Câu hỏi tự kiểm tra

**1. `REPLACE_EXISTING` có bảo đảm không gián đoạn không?**

Không. Việc hủy đăng ký rồi đăng ký MBean mới có thể tạo khoảng trống, lỗi tạm thời và mất subscription.

**2. Cùng ObjectName có nghĩa cùng Java object không?**

Không. ObjectName là tên registry; có thể trỏ tới MBean khác sau replace.

**3. Tại sao client typed proxy có thể lỗi sau replace?**

Vì MBean mới có thể thiếu operation/attribute hoặc có chữ ký không tương thích với interface proxy cũ.

**4. Replace có dừng operation đang chạy trên MBean cũ không?**

Không nhất thiết. Thread đang thực thi vẫn có thể tiếp tục trên resource cũ; cần cơ chế concurrency và handover riêng.

**5. `IGNORE_EXISTING` có luôn là lựa chọn an toàn nhất không?**

Không. Nó có thể giữ một MBean cũ không đúng owner và khiến bean mới không được quản trị.

**6. Vì sao nhiều ApplicationContext trong cùng JVM dễ gặp xung đột?**

Vì chúng có thể dùng chung platform MBeanServer; ObjectName phải duy nhất trong server đó.

**7. Làm sao client nhận biết MBean vừa bị thay?**

Có thể theo dõi notification đăng ký/hủy đăng ký từ MBeanServerDelegate và kiểm tra lại metadata/attribute sau reconnect.

**8. Khi nào nên dùng ObjectName mới?**

Khi cần chuyển đổi API không tương thích hoặc phải duy trì song song hai phiên bản để nâng cấp client có kiểm soát.

## 24. Tổng kết

`RegistrationPolicy.REPLACE_EXISTING` có thể hữu ích khi cần thay MBean dưới cùng ObjectName, nhưng việc thay một MBean **đang được sử dụng** có thể ảnh hưởng trực tiếp tới khả năng truy cập, hợp đồng API, trạng thái, listener, tác vụ đang chạy và lifecycle của nhiều Spring context.

Một quyết định thay thế an toàn cần:

- Xác định **owner** của ObjectName.
- Kiểm tra tương thích **MBeanInfo** và các client.
- Chủ động xử lý **notification subscription**.
- Quản lý trạng thái và tác vụ đang chạy ở **resource/service layer**.
- Chấp nhận hoặc giảm thiểu khoảng gián đoạn unregister/register.
- Có bước xác nhận MBean mới và phương án xử lý khi chuyển đổi lỗi.

Nếu mục tiêu chỉ là thay implementation hoặc thay dữ liệu trong resource, việc giữ một **MBean adapter ổn định** thường giúp giảm rủi ro. Khi API thay đổi không tương thích, đặt ObjectName mới để chuyển đổi từng bước có thể rõ ràng hơn.

**Registration policy giải quyết xung đột tên; tính liên tục và an toàn của hệ thống quản trị phải được thiết kế riêng.**

### Tài liệu tham khảo

- Spring Framework API — `RegistrationPolicy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE API — `MBeanServerNotification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
