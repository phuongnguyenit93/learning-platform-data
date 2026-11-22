# Tài liệu hóa mục đích của resource quản trị với Spring @ManagedResource

## Mục tiêu

Sau bài học, bạn có thể mô tả rõ **mục đích, phạm vi và hợp đồng vận hành** của một JMX-managed resource trong Spring Framework; biết sử dụng thuộc tính `description` của `@ManagedResource`, bổ sung tài liệu cho `@ManagedAttribute` và `@ManagedOperation`; tổ chức tên `ObjectName`, đơn vị đo, mức độ tác động và lưu ý bảo mật để JMX client có thể hiểu đúng resource; đồng thời kiểm tra metadata được xuất qua `MBeanInfo`.

## 1. Resource quản trị là gì và vì sao phải tài liệu hóa?

Trong Spring JMX, một object có thể được công bố làm MBean để công cụ như JConsole, Java Mission Control (JMC) hoặc monitoring agent đọc trạng thái và gọi thao tác quản trị. Annotation `@ManagedResource` đánh dấu đối tượng được quản lý, còn exporter của Spring quyết định cách đưa nó vào `MBeanServer`.

Ví dụ:

```java
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Management view for the payment processing queue"
)
public class PaymentQueueMonitor {
    // ...
}
```

`objectName` trả lời **“resource này được nhận diện ở đâu?”**; `description` trả lời **“resource này dùng để làm gì?”**. Nếu bỏ mô tả hoặc dùng câu chung chung như `"JMX resource"`, người vận hành có thể nhìn thấy một MBean mà không biết nó quản lý thành phần nào, phạm vi dữ liệu ra sao, giá trị nào là trạng thái thông thường và action nào gây thay đổi thực tế.

Tài liệu hóa giúp:

- Người vận hành tìm đúng MBean khi có nhiều bean cùng class hoặc nhiều application instance.
- Dashboard và script nhận biết ý nghĩa của attribute/operation mà không phải đọc source code.
- Người bảo trì hiểu lý do interface quản trị tồn tại và tránh đổi tên/hợp đồng tùy tiện.
- Reviewer xác định dữ liệu nào nên được công bố ra JMX và dữ liệu nào là bí mật.
- Nhóm SRE/operations biết giới hạn, đơn vị đo, khả năng reset và tác động khi gọi action.

**MBean là một giao diện vận hành, không chỉ là một class Java được gắn annotation.** Vì vậy, mô tả nên viết theo góc nhìn người dùng công cụ quản trị, không đơn thuần mô tả kỹ thuật implementation.

## 2. Vai trò của @ManagedResource trong Spring

`org.springframework.jmx.export.annotation.ManagedResource` là annotation cấp class dùng để khai báo metadata quản trị. Trong quá trình export dựa trên annotation, Spring đọc thông tin này để xây dựng MBean metadata và đặt tên JMX theo cấu hình.

Ví dụ có mô tả rõ:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Cache,name=ProductCatalog",
    description = "Observes the product catalog cache and supports controlled eviction"
)
public class ProductCatalogCacheMonitor {
    // ...
}
```

Mô tả có các thành phần quan trọng:

1. **Đối tượng được quản trị:** product catalog cache.
2. **Mục đích quan sát:** theo dõi trạng thái cache.
3. **Khả năng điều khiển:** cho phép eviction có kiểm soát.
4. **Ranh giới:** chỉ cache sản phẩm, không phải toàn bộ ứng dụng.

Khi `AnnotationMBeanExporter`, `@EnableMBeanExport` hoặc `<context:mbean-export/>` được cấu hình phù hợp, metadata này có thể xuất hiện trong `MBeanInfo.getDescription()` mà JMX client hiển thị.

Cần phân biệt: **có annotation không đồng nghĩa MBean đã đăng ký**. Bean phải nằm trong ApplicationContext và exporter phải hoạt động trên `MBeanServer` mà client đang kết nối.

## 3. Một mô tả @ManagedResource tốt cần gì?

Mục đích resource có thể được diễn đạt theo công thức:

```text
[Resource quản trị đối tượng gì]
+ [những thông tin/điều khiển chính]
+ [phạm vi hoặc giới hạn quan trọng]
```

Ví dụ chưa tốt:

```java
@ManagedResource(
    objectName = "com.example:type=Worker",
    description = "Worker MBean"
)
```

Mô tả này chỉ lặp lại tên; không giúp người vận hành biết worker nào và vai trò gì.

Ví dụ tốt hơn:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Billing",
    description = "Monitors billing worker throughput, backlog and pause state"
)
```

Mô tả này xác định service, thành phần và phạm vi quan sát. Nếu MBean còn có operations làm thay đổi trạng thái, nên thể hiện khả năng đó một cách chính xác:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Billing",
    description = "Billing worker pool: read execution statistics and control pause/resume"
)
```

Độ dài không phải tiêu chí duy nhất. Mô tả cần **đúng chức năng** và **không hứa hẹn những khả năng MBean không công bố**.

## 4. Tài liệu hóa từ resource xuống attribute và operation

Tài liệu resource nên là phần tổng quan; các chi tiết cụ thể phải được công bố ngay ở attribute và operation.

Spring cung cấp:

- `@ManagedResource`: mô tả tài nguyên.
- `@ManagedAttribute`: mô tả thuộc tính đọc/ghi, đặc biệt đơn vị, nguồn và ý nghĩa.
- `@ManagedOperation`: mô tả thao tác quản trị.
- `@ManagedOperationParameter` và `@ManagedOperationParameters`: mô tả tên/thông tin tham số của operation khi cần.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue status and limited operator controls"
)
public class PaymentQueueAdmin {
    private volatile boolean paused;
    private volatile int pendingCount = 10;

    @ManagedAttribute(
        description = "Number of payment messages waiting to be processed"
    )
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(
        description = "Whether intake from this payment queue is paused"
    )
    public boolean isPaused() {
        return paused;
    }

    @ManagedAttribute(
        description = "Whether intake from this payment queue is paused"
    )
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @ManagedOperation(
        description = "Attempts to reprocess at most maxCount failed messages"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxCount",
            description = "Maximum messages to retry; must be between 1 and 100"
        )
    })
    public int retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException(
                "maxCount must be between 1 and 100"
            );
        }
        // Ví dụ: ở ứng dụng thật, gọi service xử lý retry.
        return 0;
    }
}
```

Trong ví dụ, `@ManagedResource` giải thích mục tiêu tổng thể, `@ManagedAttribute` diễn giải thuộc tính, `@ManagedOperation` nói rõ thao tác và tham số có phạm vi hợp lệ.

**Lưu ý:** các setter và operation có tác động thật cần được triển khai và kiểm soát quyền. Annotation mô tả không tự động thực thi validation, authentication hoặc authorization.

## 5. Viết mô tả cho chỉ số: tên, đơn vị, phạm vi, thời điểm

Một resource quan sát thường công bố các chỉ số như `ActiveConnections`, `PendingCount`, `ErrorRate`, `TotalProcessed`, `OldestJobAgeMillis`.

Tài liệu cần trả lời:

| Câu hỏi | Ví dụ |
| --- | --- |
| Giá trị đo cái gì? | Số job đang chờ trong queue |
| Phạm vi đo là gì? | Chỉ queue Payment của JVM hiện tại |
| Đơn vị là gì? | Count, milliseconds, bytes, percent |
| Giá trị là tức thời hay tích lũy? | Số đang chờ tại thời điểm đọc; tổng từ khi khởi động |
| Khi nào reset? | Reset khi JVM khởi động hoặc khi gọi operation |
| Giá trị đặc biệt có ý nghĩa gì? | `-1` nếu không xác định, nếu API quy định vậy |
| Dữ liệu cập nhật với độ trễ nào? | Snapshot được làm mới mỗi 5 giây |

Ví dụ:

```java
@ManagedAttribute(
    description = "Age in milliseconds of the oldest pending payment; 0 when empty"
)
public long getOldestPendingAgeMillis() {
    return oldestPendingAgeMillis;
}
```

`OldestPendingAgeMillis` tự gợi ý đơn vị; mô tả bổ sung trường hợp rỗng. Nếu không thể tính tức thời, nên nêu rõ dữ liệu là snapshot hoặc được cập nhật theo chu kỳ.

Không nên mô tả một counter tích lũy là “số request hiện tại”. Khác biệt giữa **gauge** và **counter** ảnh hưởng mạnh đến cách người vận hành diễn giải dữ liệu và thiết lập cảnh báo.

## 6. Tài liệu hóa operation theo mức độ tác động

Một operation JMX có thể chỉ đọc thông tin, có thể thay đổi trạng thái, hoặc gây ảnh hưởng nghiêm trọng nếu gọi sai.

Ví dụ:

```java
@ManagedOperation(
    description = "Clears in-memory statistics; does not delete persisted orders"
)
public void resetStatistics() { /* ... */ }
```

Mô tả tốt trả lời:

1. **Động từ và đối tượng:** reset những thống kê nào?
2. **Tác động:** có xóa dữ liệu nghiệp vụ hay chỉ xóa counter?
3. **Phạm vi:** chỉ trong instance hiện tại hay cả cluster?
4. **Điều kiện:** có yêu cầu trạng thái/role nào không?
5. **Kết quả:** trả về giá trị nào hoặc khi nào lỗi?
6. **Khả năng lặp lại:** gọi nhiều lần có an toàn hay gây side effect?

Một bảng ví dụ:

| Operation | Mô tả chưa đủ | Mô tả có ích |
| --- | --- | --- |
| `clearCache()` | Clears cache | Evicts product cache entries from this JVM; subsequent requests reload data |
| `pause()` | Pauses | Stops accepting new tasks in this worker pool; running tasks continue |
| `retryFailed(int maxCount)` | Retry errors | Retries up to maxCount failed jobs; invalid if maxCount is outside 1–100 |
| `resetCounters()` | Reset | Resets local counters only; historical metrics already exported are unchanged |

Có thể dùng `MBeanOperationInfo` metadata `impact` để phân loại `INFO`, `ACTION`, `ACTION_INFO` hoặc `UNKNOWN`. Tuy nhiên, thông tin impact **không thay thế mô tả và không phải rào chắn bảo mật**. Một JMX client có quyền gọi operation có thể thực thi action bất kể tên/mô tả thân thiện đến đâu.

## 7. ObjectName cũng là một phần của tài liệu quản trị

`@ManagedResource` hỗ trợ `objectName`, ví dụ:

```java
@ManagedResource(
    objectName = "com.example.billing:type=Cache,name=ExchangeRates",
    description = "Monitors and refreshes the exchange-rate cache for billing"
)
```

ObjectName chứa domain và các key property, giúp client tìm đúng resource:

```text
com.example.billing:type=Cache,name=ExchangeRates
```

Hướng đặt tên:

- **Domain:** namespace module hoặc dịch vụ, ví dụ `com.example.billing`.
- **type:** loại resource, ví dụ `Cache`, `Queue`, `WorkerPool`.
- **name:** tên logic ổn định, ví dụ `ExchangeRates`.
- **instance:** chỉ thêm khi cần phân biệt resource trong cùng `MBeanServer` và giá trị có ý nghĩa ổn định.

Tên nên độc lập với PID, hash code hay UUID được tạo lại mỗi lần khởi động nếu resource logic không đổi. Việc đặt tên ổn định giúp dashboard và automation không bị đứt kết nối khi restart.

`ObjectName` chỉ duy nhất **trong một `MBeanServer`**, không phải trên mọi JVM. Khi tài liệu nói “cache hiện tại”, cần nêu rõ cache ở JVM nào hay toàn cluster.

## 8. MBeanInfo: nơi client nhìn thấy mô tả

Khi Spring xuất MBean, JMX client lấy metadata qua `MBeanServerConnection.getMBeanInfo(ObjectName)` hoặc `MBeanServer.getMBeanInfo`.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Resource: " + info.getDescription());

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute %s: %s%n",
        attribute.getName(),
        attribute.getDescription()
    );
}

for (var operation : info.getOperations()) {
    System.out.printf(
        "Operation %s: %s%n",
        operation.getName(),
        operation.getDescription()
    );
}
```

Ví dụ trên giả định bean đã được đăng ký vào platform `MBeanServer`. Nếu exporter dùng server khác, cần lấy đúng server. `isRegistered(name)` có thể dùng trước `getMBeanInfo` để tránh `InstanceNotFoundException`.

Các giao diện như JConsole/JMC có thể hiển thị tên, description, attributes và operations theo cách riêng. Không phải UI nào cũng hiển thị mọi trường metadata ở vị trí dễ thấy; việc xuất mô tả đúng vẫn cần được kiểm chứng qua JMX API.

### Mô tả không phải một tài liệu đầy đủ thay thế runbook

`MBeanInfo.getDescription()` rất tiện cho khám phá MBean, nhưng thường chỉ chứa chuỗi mô tả ngắn. Runbook hoặc tài liệu hệ thống vẫn cần mô tả sâu hơn về quyền, tác động tới production, tình huống vận hành, quy trình rollback và các tình huống lỗi.

## 9. Cấu hình Spring để xuất metadata annotation

Trong Spring Framework, có thể bật annotation-driven JMX export bằng Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Hoặc trong XML:

```xml
<context:mbean-export/>
```

với namespace Spring context được khai báo đúng.

Cơ chế này sử dụng hạ tầng exporter và metadata thích hợp, trong đó `AnnotationMBeanExporter` là thành phần quan trọng cho annotation-driven JMX. Chỉ các Spring bean được phát hiện và có metadata phù hợp mới được export; annotation không tự tạo một remote JMX endpoint.

Nếu ứng dụng dùng `MBeanExporter` tự cấu hình, cần bảo đảm `MetadataMBeanInfoAssembler`, `AnnotationJmxAttributeSource` và naming strategy thích hợp nếu mong muốn descriptions từ annotation xuất hiện trong `MBeanInfo`.

Tránh đăng ký cùng ObjectName bằng cả exporter thủ công và auto-export. Hai exporter cùng đăng ký vào một `MBeanServer` có thể gặp xung đột tên.

## 10. Mẫu tài liệu hóa một resource đầy đủ

Có thể thống nhất một mẫu tài liệu ngắn đặt trong mã nguồn hoặc tài liệu vận hành:

```text
ObjectName:
  com.example.orders:type=Queue,name=Payment

Purpose:
  Theo dõi queue Payment trong JVM hiện tại,
  cho phép xem backlog, pause/resume intake và retry có giới hạn.

Scope:
  Chỉ xử lý trong instance đang được kết nối;
  không tác động tự động đến các replica khác.

Attributes:
  PendingCount (int, read-only):
    Số message đang chờ tại thời điểm đọc.
  Paused (boolean, read-write):
    Trạng thái ngừng tiếp nhận message mới.
  OldestPendingAgeMillis (long, read-only):
    Tuổi của message chờ lâu nhất, theo milliseconds.

Operations:
  retryFailed(maxCount):
    Thử xử lý lại tối đa maxCount message lỗi.
    Tham số hợp lệ: 1..100.
    Có thể tạo side effects và tăng tải queue.

Security:
  Chỉ vai trò vận hành được ủy quyền mới được thực thi operations.

Lifecycle:
  MBean xuất hiện khi Spring context khởi tạo và mất đi khi context đóng.
```

Một phần tài liệu được đưa vào annotation description để client có thể đọc ngay; phần còn lại thuộc README/runbook để người vận hành tham khảo.

## 11. Những lỗi tài liệu hóa thường gặp

**Mô tả quá chung:** `"Managed service"` hoặc `"JMX MBean"` không nói được resource dùng làm gì. Hãy chỉ rõ domain nghiệp vụ, phạm vi và hành động cho phép.

**Lặp lại tên method:** `@ManagedOperation(description = "resetStatistics")` không giúp hiểu tác động. Nên giải thích reset những gì và không reset những gì.

**Quên đơn vị đo:** `Timeout = 5000` không cho biết là milliseconds hay seconds. Ghi đơn vị trong tên/description.

**Lẫn lộn trạng thái local và cluster:** `ActiveWorkers` trong một JVM không mặc nhiên là tổng mọi replica. Mô tả phải chỉ rõ phạm vi.

**Không nói về reset:** Counter có thể khởi động lại ở 0 khi JVM restart; người dùng có thể hiểu nhầm dashboard nếu tưởng tổng tích lũy vĩnh viễn.

**Không cảnh báo operation có side effect:** `clearCache`, `purgeQueue`, `shutdown` hoặc `rebuildIndex` không nên được mô tả như thao tác đọc thông tin.

**Đưa thông tin nhạy cảm vào description:** Tránh ghi mật khẩu, access token, địa chỉ nội bộ nhạy cảm hoặc dữ liệu cá nhân. Metadata JMX có thể được nhiều client đọc.

**Description lỗi thời:** Nếu implementation thay đổi nhưng metadata không cập nhật, người vận hành sẽ ra quyết định dựa trên thông tin sai. Coi nội dung mô tả như một phần hợp đồng quản trị cần duy trì cùng code.

## 12. Cách xác định ranh giới an toàn

Một `@ManagedResource` phục vụ quản trị không nên vô tình trở thành API truy cập toàn bộ dữ liệu nghiệp vụ.

Nên ưu tiên:

- Các chỉ số tổng hợp, trạng thái, uptime, số lượng lỗi, độ trễ.
- Tên và đơn vị đo rõ ràng.
- Operation có tham số giới hạn và tác động xác định.
- Mô tả không lộ dữ liệu bí mật.
- ObjectName logic ổn định.
- Metadata nhất quán với quyền thực tế.

Nên tránh:

- Attribute trả danh sách người dùng, session token hoặc dữ liệu cá nhân.
- Operation không có giới hạn có thể xóa dữ liệu hàng loạt.
- Getter thực hiện truy vấn cực nặng và bị JMX client poll liên tục.
- Mô tả gây hiểu nhầm như “read-only” trong khi setter vẫn được xuất.
- Sử dụng annotation như thể nó cung cấp authorization hoặc auditing mặc định.

Remote JMX cần kiểm soát access, authentication, transport security và network exposure độc lập với descriptions. Tài liệu tốt hỗ trợ vận hành an toàn nhưng không thay thế cơ chế bảo mật.

## 13. Một kiểm thử kiểm tra tài liệu đã công bố

Dưới đây là phác thảo integration test với một bean đã được Spring xuất thành MBean:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.*;
import org.junit.jupiter.api.Test;

class JmxMetadataTest {
    @Test
    void exposesMeaningfulResourceDescription() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);
        assertNotNull(info.getDescription());
        assertTrue(info.getDescription().contains("Payment"));

        boolean hasPendingCount = false;
        for (MBeanAttributeInfo attr : info.getAttributes()) {
            if ("PendingCount".equals(attr.getName())) {
                hasPendingCount = true;
                assertTrue(attr.getDescription().contains("waiting"));
            }
        }
        assertTrue(hasPendingCount);
    }
}
```

Test phải chạy sau khi Spring context đã khởi tạo, MBean đã đăng ký, và exporter dùng platform `MBeanServer`. Nếu mô tả trong code sử dụng tiếng Việt, điều chỉnh các từ khóa mà assertion tìm kiếm theo đúng ngôn ngữ đã chọn.

Mục đích test là xác minh **metadata đã được export đúng như khai báo**, không đánh giá toàn bộ chất lượng văn phong.

## 14. Thực hành cải thiện một resource

Cho class chưa được tài liệu hóa đầy đủ:

```java
@ManagedResource(objectName = "com.example:type=Pool")
public class PoolMonitor {
    @ManagedAttribute
    public int getSize() { return 12; }

    @ManagedOperation
    public void clear() { /* ... */ }
}
```

Hãy thiết kế lại:

1. Đặt ObjectName thể hiện loại và tên logic của pool.
2. Thêm `description` chỉ rõ pool thuộc service nào và scope là local hay cluster.
3. Đổi hoặc mô tả `getSize()` thành “active connections”, “idle connections” hay “configured capacity” tùy đúng semantics.
4. Mô tả `clear()` tác động tới connection nào, có gây ngắt request hay không và khi nào được phép gọi.
5. Kiểm tra metadata qua `MBeanInfo`, xem JConsole/JMC có hiển thị thông tin phù hợp không.
6. Lập runbook cho operation nguy hiểm thay vì đặt toàn bộ hướng dẫn vào một chuỗi annotation.

## 15. Câu hỏi tự kiểm tra

- `@ManagedResource.description` khác `@ManagedAttribute.description` như thế nào?
- Vì sao `"Service MBean"` không phải một mô tả đủ hữu ích?
- Một thuộc tính trả về `long` có cần ghi đơn vị và ngữ nghĩa reset không?
- Khi resource quản trị một replica, mô tả cần làm rõ phạm vi gì?
- Có thể đọc mô tả đã xuất ở đâu trong JMX API?
- Vì sao operation được mô tả rõ vẫn cần authorization độc lập?
- Khi chuyển class implementation nhưng giữ ObjectName, cần kiểm tra phần nào của hợp đồng metadata?

**Ghi nhớ:** `@ManagedResource` không chỉ đánh dấu một Spring bean để export qua JMX; thông qua `description` và ObjectName, nó còn giúp tài liệu hóa mục đích của giao diện quản trị. Hãy diễn đạt rõ resource quản lý gì, phạm vi nào, số liệu có nghĩa ra sao và operation gây tác động gì; đồng thời bổ sung mô tả chi tiết ở attribute/operation và kiểm tra `MBeanInfo` mà JMX client thực sự nhận được.