# Giữ management interface tương thích khi nâng phiên bản Spring Framework JMX

## 1. Mục tiêu bài học

Một management API qua JMX không chỉ phục vụ người đang mở JConsole hoặc Java Mission Control. Nó có thể được sử dụng bởi monitoring agents, shell scripts, dashboard, cảnh báo, kiểm thử tự động và công cụ vận hành khác. Vì vậy, khi nâng phiên bản ứng dụng hoặc Spring Framework, thay đổi nhỏ trong `ObjectName`, attribute, operation hay kiểu dữ liệu cũng có thể làm các client hiện có ngừng hoạt động.

Bài học thuộc **Spring Framework JMX → Thiết kế management API**. Sau bài này, bạn có thể:

- Xem management interface như một hợp đồng phiên bản hóa.
- Phân biệt thay đổi **tương thích**, **có điều kiện** và **breaking change**.
- Bảo vệ `ObjectName`, tên attribute, kiểu dữ liệu, khả năng read/write, tên operation và chữ ký tham số.
- Giữ ổn định API khi refactor Java class, thay annotation, thay assembler hoặc bật Spring AOP.
- Xây dựng quy trình deprecation, alias, versioned ObjectName và rollout nhiều phiên bản.
- Viết contract test so sánh `MBeanInfo` của phiên bản hiện tại với baseline đã công bố.
- Nhận biết những giới hạn của JMX remote, serialization, Open Types và management automation.

## 2. Management API là một public contract

Giả sử hệ thống xuất MBean:

```text
com.example.orders:type=Queue,name=Payment
```

với hợp đồng:

```text
Attributes:
  PendingCount : int      readable=true, writable=false
  Paused       : boolean  readable=true, writable=true

Operations:
  retryFailed(int maxCount) : void
  resetStatistics()         : void

Notifications:
  com.example.orders.queue.overloaded
```

Một script vận hành có thể gọi:

```java
Object pending = connection.getAttribute(
    name, "PendingCount"
);

connection.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);
```

Nếu bản nâng cấp đổi `PendingCount` thành `QueueDepth`, script cũ thất bại dù logic nghiệp vụ vẫn chạy. Nếu đổi tham số từ `int` sang `long`, client đang gửi signature `"int"` có thể nhận lỗi invoke. Nếu đổi `ObjectName`, client có thể không tìm thấy MBean.

Đó là lý do quản trị phải được xem là một API được sử dụng từ bên ngoài tiến trình, không chỉ là tập tên method nội bộ.

## 3. Những thành phần tạo thành hợp đồng JMX

Hợp đồng JMX có ít nhất các lớp sau:

| Thành phần | Ví dụ | Rủi ro khi thay đổi |
| --- | --- | --- |
| `ObjectName` | `com.example.orders:type=Queue,name=Payment` | Client không tìm thấy MBean |
| Domain/key properties | `type=Queue,name=Payment` | Query pattern và dashboard không match |
| Attribute name | `PendingCount` | `getAttribute` thất bại |
| Attribute type | `int` | Cast/deserialization sai |
| Readability/writability | `readable=true,writable=false` | Client đọc/ghi không còn hợp lệ |
| Operation name | `retryFailed` | `invoke` không tìm thấy |
| Operation signature | `int` | Invocation sai overload |
| Operation return type | `void` | Client xử lý response sai |
| Notification type | `queue.overloaded` | Listener/filter không còn nhận event |
| Open MBean data schema | `CompositeType`, `TabularType` | Client không parse được kết quả |
| Behavior | Giới hạn, side effect, lỗi | Automation có thể xử lý sai dù signature giữ nguyên |

Không nên chỉ so sánh Java interface source code. JMX client thấy **metadata đã đăng ký trong `MBeanServer`**, có thể bị tác động bởi exporter, assembler, proxy, annotation hoặc JVM.

## 4. Tính tương thích khác với khả năng compile

Trong Java, đổi:

```java
int getPendingCount();
```

thành:

```java
long getPendingCount();
```

có thể là một thay đổi hợp lý trong code nghiệp vụ. Nhưng trong JMX, attribute `PendingCount` đổi từ `int` sang `long`, khiến client cũ:

```java
Integer count = (Integer)
    connection.getAttribute(name, "PendingCount");
```

thất bại tại runtime.

Tương tự, Java method overload mới có thể compile bình thường, nhưng JMX client gọi bằng operation name và **mảng tên kiểu tham số**, ví dụ:

```java
new String[] { "int" }
```

Nếu signature thay đổi, client không tự biết điều đó.

Do vậy, compatibility test phải chạy ở tầng JMX, không chỉ ở tầng compile hoặc unit test class.

## 5. Các loại thay đổi và mức độ tương thích

Bảng phân loại thực tế:

| Thay đổi | Đánh giá thường gặp | Giải thích |
| --- | --- | --- |
| Thêm attribute chỉ đọc mới | Thường tương thích | Client cũ vẫn đọc attribute cũ |
| Thêm operation tên mới | Thường tương thích | Không làm mất operation cũ; cần xét bảo mật |
| Thêm notification type mới | Thường tương thích, nhưng cần xét listener | Listener lọc rộng có thể nhận thêm event |
| Đổi description | Thường tương thích kỹ thuật | Có thể ảnh hưởng công cụ dựa vào description |
| Đổi thứ tự key properties trong ObjectName text | Không đổi danh tính | `ObjectName.equals()` vẫn true |
| Đổi domain hoặc key properties | Breaking | Tên MBean khác |
| Đổi tên attribute | Breaking | Client cũ không tìm được |
| Đổi kiểu attribute | Breaking | Cast/schema client có thể sai |
| Biến attribute readable thành không readable | Breaking | Client cũ không đọc được |
| Bỏ writability của attribute | Breaking với writer | Script setAttribute sẽ lỗi |
| Đổi tên operation | Breaking | `invoke` không tìm thấy |
| Đổi kiểu/thứ tự tham số operation | Breaking | Signature không khớp |
| Đổi kiểu trả về operation | Có thể breaking | Client parse/cast khác |
| Xóa overload cũ | Breaking | Client dùng overload đó lỗi |
| Đổi ý nghĩa operation mà giữ tên | Semantic breaking | Có thể gây hậu quả vận hành |
| Đổi tên notification type | Breaking với listener/filter | Filter cũ không match |

“Thường tương thích” không có nghĩa an toàn tuyệt đối. Một collector tự động liệt kê mọi operation có thể bị ảnh hưởng khi API mở rộng, và một notification type mới có thể kích hoạt listener viết quá rộng. Compatibility luôn xét **client thực tế**.

## 6. ObjectName cần ổn định

Ví dụ ObjectName:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

Nên chọn domain/key property thể hiện tài nguyên logic thay vì thông tin runtime như PID, object identity, random UUID hoặc proxy class name.

Ví dụ không ổn định:

```text
com.example.orders:type=Queue,name=Payment,pid=48122
com.example.orders:type=Queue,name=Payment,pid=53280
```

Nếu dashboard dùng exact ObjectName, mỗi lần restart sẽ đổi tên.

Tên ổn định hơn:

```text
com.example.orders:type=Queue,name=Payment
```

Trong hệ thống nhiều JVM, cùng ObjectName có thể tồn tại trên các server khác nhau. Collector cần định danh thêm endpoint/instance, chứ không bắt ObjectName nội bộ chứa thông tin động nếu không cần.

### Thứ tự key không phải breaking change

```java
ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Payment,type=Queue"
);

System.out.println(first.equals(second)); // true
```

Khi so sánh, dùng `ObjectName.equals()` hoặc canonical name, không chỉ `String.equals()`.

## 7. Standard MBean interface rõ ràng

Một cách định nghĩa hợp đồng quản trị là Java interface chuyên dụng:

```java
package com.example.orders.jmx;

public interface QueueAdminMBean {

    int getPendingCount();

    boolean isPaused();

    void setPaused(boolean paused);

    void retryFailed(int maxCount);
}
```

Implementation:

```java
package com.example.orders.jmx;

public class QueueAdmin implements QueueAdminMBean {

    private final QueueService service;

    public QueueAdmin(QueueService service) {
        this.service = service;
    }

    @Override
    public int getPendingCount() {
        return service.pendingCount();
    }

    @Override
    public boolean isPaused() {
        return service.isPaused();
    }

    @Override
    public void setPaused(boolean paused) {
        service.setPaused(paused);
    }

    @Override
    public void retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException(
                "maxCount must be between 1 and 100"
            );
        }
        service.retryFailed(maxCount);
    }
}
```

`QueueService` là interface nghiệp vụ do ứng dụng định nghĩa. Adapter `QueueAdmin` tách đường quản trị khỏi business implementation, giúp refactor service mà vẫn giữ các tên method trong management API.

Để giữ compatibility, các method cũ trong `QueueAdminMBean` nên được duy trì đến khi có kế hoạch deprecation/migration rõ ràng.

## 8. Với @ManagedResource, phải kiểm tra metadata runtime

Spring JMX có thể xuất MBean từ annotation:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue management"
)
public class AnnotatedQueueAdmin {

    @ManagedAttribute
    public int getPendingCount() {
        return 10;
    }

    @ManagedOperation
    public void retryFailed(int maxCount) {
        // ...
    }
}
```

Bật annotation-driven exporter:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
```

Tuy nhiên, chỉ có annotation trên source code không chứng minh hợp đồng JMX thực tế giữ nguyên:

- Exporter có thể không được bật ở một profile.
- Bean có thể không được quét vào context.
- Spring AOP proxy thay đổi method surface.
- Metadata assembler/naming strategy khác có thể được cấu hình.
- Một exporter khác có thể đăng ký cùng ObjectName.

Do vậy, contract test phải đọc `MBeanInfo` từ `MBeanServer` sau khi Spring context khởi tạo.

## 9. Contract test bằng MBeanInfo

`MBeanServer.getMBeanInfo(ObjectName)` trả về metadata đã được đăng ký.

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Expected MBean missing: " + name.getCanonicalName()
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "attribute %s %s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(
        "operation " + operation.getName()
    );
    for (var param : operation.getSignature()) {
        System.out.println(
            "  param type=" + param.getType()
        );
    }
}
```

Các thông tin quan trọng:

- `MBeanAttributeInfo`: name, type, readable/writable, isIs.
- `MBeanOperationInfo`: name, return type, signature, impact.
- `MBeanParameterInfo`: type và metadata tham số.
- `MBeanNotificationInfo`: notification types.
- Với OpenMBean, có thể kiểm tra `OpenType` và schema tương ứng.

Không nên dùng duy nhất `MBeanInfo.getClassName()` để kiểm tra hợp đồng: Spring ModelMBean hoặc proxy có thể thể hiện class metadata khác với class nghiệp vụ.

## 10. Viết baseline contract có chủ đích

Một bản baseline cho phiên bản v1 có thể mô tả:

```yaml
objectName: "com.example.orders:type=Queue,name=Payment"
attributes:
  PendingCount:
    type: int
    readable: true
    writable: false
  Paused:
    type: boolean
    readable: true
    writable: true
operations:
  - name: retryFailed
    returnType: void
    parameters:
      - int
notifications:
  - "com.example.orders.queue.overloaded"
```

Baseline phải phản ánh **API đã công bố và các client đang sử dụng**, không chỉ metadata của bản build mới. Nếu đơn giản xuất metadata hiện tại rồi so với chính nó, test luôn xanh nhưng không phát hiện regression.

Có thể lưu baseline như fixture versioned trong test resources và so sánh với metadata runtime. Phương pháp tốt là tạo một snapshot normalized đã xác định những field nào là hợp đồng, tránh phụ thuộc vào thứ tự array hoặc description không quan trọng.

## 11. Ví dụ kiểm thử backward compatibility bằng JUnit

Một test chỉ kiểm tra phần hợp đồng quan trọng:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class QueueJmxContractTest {

    private final MBeanServer server = /* test server */;
    
    @Test
    void keepsV1ManagementContract() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        MBeanAttributeInfo count = Arrays.stream(
                info.getAttributes())
            .filter(a -> a.getName().equals("PendingCount"))
            .findFirst()
            .orElseThrow();

        assertEquals("int", count.getType());
        assertTrue(count.isReadable());
        assertFalse(count.isWritable());

        boolean retryAvailable = Arrays.stream(
                info.getOperations())
            .filter(op -> op.getName().equals("retryFailed"))
            .anyMatch(op ->
                op.getReturnType().equals("void")
                && op.getSignature().length == 1
                && op.getSignature()[0].getType().equals("int")
            );

        assertTrue(retryAvailable);
    }
}
```

Trong project thật, `server` phải được khởi tạo qua Spring test configuration hoặc một JMX test fixture đã đăng ký MBean. Placeholder trong ví dụ biểu thị dependency cần được cung cấp, không phải Java source có thể compile nguyên xi.

Một test backward-compatible thường kiểm tra **các thành phần cũ vẫn còn** thay vì đòi toàn bộ MBeanInfo bằng tuyệt đối, bởi bản mới có thể bổ sung attributes hoặc operations hợp lệ.

## 12. Phân biệt compatibility kiểm thử và semantic compatibility

Một operation vẫn có cùng signature:

```java
void retryFailed(int maxCount);
```

nhưng nếu trước đây `maxCount` là giới hạn số item retry, sau nâng cấp lại được hiểu là số batch, client cũ có thể gây tải lớn dù metadata không đổi.

Tương tự:

- `getPendingCount()` trước đây tính mọi job trong queue, bản mới chỉ đếm job đã sẵn sàng.
- `setPaused(true)` trước đây chỉ dừng intake local, bản mới dừng toàn cluster.
- `resetStatistics()` trước đây chỉ reset counter, bản mới xóa dữ liệu lịch sử.
- `getTimeoutMillis()` trước đây trả millisecond, bản mới trả second nhưng vẫn là `long`.

Vì vậy, với operations quan trọng cần thêm **behavioral tests** và tài liệu semantics, units, phạm vi tác động, side effects và error handling.

Contract test chỉ kiểm tra tên/kiểu là cần thiết nhưng chưa đủ.

## 13. Đừng sửa API cũ chỉ để đổi tên cho đẹp

Giả sử v1 có:

```java
@ManagedAttribute
public int getPendingCount() { ... }
```

Đến v2 muốn dùng tên rõ nghĩa hơn:

```java
@ManagedAttribute
public int getQueuedOrderCount() { ... }
```

Nếu thay thế trực tiếp, attribute `PendingCount` biến mất. Client cũ có thể lỗi.

Có thể giữ alias trong giai đoạn chuyển tiếp:

```java
@ManagedAttribute(
    description = "Deprecated: use QueuedOrderCount"
)
public int getPendingCount() {
    return getQueuedOrderCount();
}

@ManagedAttribute(
    description = "Queued orders waiting for processing"
)
public int getQueuedOrderCount() {
    return service.queuedOrderCount();
}
```

Điều này cho phép client cũ tiếp tục gọi `PendingCount` trong khi client mới chuyển sang `QueuedOrderCount`.

**Lưu ý:** hai getter dùng cùng service method để tránh trả hai cách tính khác nhau. Nên ghi rõ thời hạn deprecation và chỉ xóa alias trong một phiên bản breaking được thông báo.

## 14. Giữ operation signature cũ

Giả sử v1:

```java
void retryFailed(int maxCount);
```

v2 muốn thêm `boolean dryRun`:

```java
void retryFailed(int maxCount, boolean dryRun);
```

Nếu chỉ giữ phiên bản mới, client cũ gọi:

```java
connection.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);
```

sẽ không tìm thấy chữ ký cũ.

Một hướng chuyển tiếp là giữ overload cũ:

```java
@ManagedOperation(
    description = "Deprecated: retries without dry-run"
)
public void retryFailed(int maxCount) {
    retryFailed(maxCount, false);
}

@ManagedOperation(
    description = "Retries with optional dry-run"
)
public void retryFailed(int maxCount, boolean dryRun) {
    service.retryFailed(maxCount, dryRun);
}
```

Cách này có thể hỗ trợ cả client cũ và mới nếu assembler/exporter công bố cả hai overload đúng cách. Với JMX, client phải gửi operation signature chính xác; hãy test cả `"int"` lẫn `"int","boolean"`.

Nếu một framework/assembler không xử lý overload như bạn muốn, cân nhắc method tên khác như `retryFailedPreview` hoặc một management adapter rõ ràng hơn. Không dựa vào giả định tên method đủ để phân biệt overload.

## 15. Khi nào nên version hóa ObjectName?

Có những thay đổi không thể giữ cả hai hợp đồng ở một MBean:

- Kiểu attribute bắt buộc thay đổi không tương thích.
- Schema Open Data thay đổi sâu.
- Semantics operation thay đổi căn bản.
- Client/agent có hai thế hệ không thể dùng chung API.

Có thể công bố hai endpoint quản trị trong cùng server:

```text
com.example.orders:type=Queue,name=Payment,api=v1
com.example.orders:type=Queue,name=Payment,api=v2
```

Hoặc dùng versioned domain:

```text
com.example.orders.management.v1:type=Queue,name=Payment
com.example.orders.management.v2:type=Queue,name=Payment
```

Chỉ nên dùng khi có nhu cầu tương thích mạnh. Bản chất JMX vẫn yêu cầu mỗi ObjectName trong cùng MBeanServer là duy nhất.

Thiết kế phù hợp có thể có hai adapter:

```text
Business Service
     |
     +-- QueueAdminV1 (old contract)
     |        -> ObjectName api=v1
     |
     +-- QueueAdminV2 (new contract)
              -> ObjectName api=v2
```

Hai adapter có thể delegate tới cùng service nhưng giữ hai hợp đồng client. Cần quản lý rõ lifecycle và eventual removal của v1.

## 16. Rolling upgrade nhiều instance

Trong một cluster hoặc hệ thống nhiều JVM, có thể xuất hiện đồng thời:

```text
Instance A: application version 1.9
Instance B: application version 2.0
Instance C: application version 2.0
```

Cùng ObjectName trong mỗi JVM không có nghĩa các MBean đều cùng contract. Collector/agent có thể phải nói chuyện với cả phiên bản cũ và mới trong giai đoạn rolling upgrade.

Các nguyên tắc:

1. Giữ API cũ hoạt động ở bản mới đến khi phần lớn client đã hỗ trợ.
2. Không bắt buộc tất cả monitoring agents phải nâng đồng thời với server.
3. Cung cấp capability/management API version attribute nếu hệ thống cần phân biệt.
4. Client có thể kiểm tra `MBeanInfo` rồi chọn operation khả dụng.
5. Không gọi operation mới trên instance cũ nếu metadata chưa có.
6. Đọc trạng thái/units nhất quán trước khi tổng hợp metrics giữa versions.

Một attribute tham khảo:

```java
@ManagedAttribute(
    description = "Version of the public JMX management contract"
)
public String getManagementApiVersion() {
    return "2.0";
}
```

Version này mô tả **management contract**, không nhất thiết giống version của ứng dụng hay Spring Framework.

## 17. Spring AOP và compatibility

Khi bật `@Transactional`, method security hoặc advisor khác, Spring có thể tạo JDK dynamic proxy hay class-based proxy.

Nếu exporter nhận proxy thay target, danh sách methods và cách tìm annotation JMX có thể thay đổi:

- JDK proxy chỉ expose methods trên interface mà nó triển khai.
- Class-based proxy có nhiều method từ target nhưng có giới hạn với final/private methods.
- Naming strategy dựa runtime class name có thể trở nên không ổn định.
- Export trực tiếp target để tránh proxy có thể làm JMX invocation bỏ qua transaction/security advice.

Để bảo vệ contract, sử dụng management adapter chuyên biệt:

```text
JMX / ObjectName ổn định
     |
     v
ManagementAdapter
     |
     v
BusinessService interface / Spring proxy
     |
     v
Business implementation
```

Adapter cho phép Java business service đổi class/proxy mà không làm thay tên attribute/operation công khai. Nhưng vẫn phải integration test lời gọi qua proxy để đảm bảo advice được thực thi.

## 18. Nâng phiên bản Spring Framework và metadata assembler

Cùng một class Java có thể được export qua nhiều cơ chế:

- Standard MBean/MXBean.
- `MBeanExporter` với explicit `beans` mapping.
- `MetadataMBeanInfoAssembler` và annotation source.
- `InterfaceBasedMBeanInfoAssembler`.
- `MethodNameBasedMBeanInfoAssembler`.
- Auto-detection qua `@EnableMBeanExport`.

Khi đổi cách export hoặc nâng Spring, hành vi metadata discovery, naming strategy hoặc proxy processing có thể khác. Vì vậy, trước khi đổi dependency, cần biết implementation đang dùng và giữ contract test trên **thành phẩm runtime**.

Không kết luận “Spring version mới không tương thích” chỉ vì một unit test source annotation pass nhưng JConsole thiếu MBean. Kiểm tra exporter configuration, target server, ObjectName, proxy type và `MBeanInfo`.

## 19. Remote client và serialization compatibility

Remote JMX thêm yêu cầu kiểu dữ liệu phải phù hợp với client JVM/classpath và cách serialization của connector.

Một operation:

```java
InternalJobDetails getJobDetails(String id);
```

có thể hoạt động local nhưng fail remote nếu client không có class `InternalJobDetails`, schema thay đổi hoặc class serialVersionUID khác.

Để tương thích dễ hơn:

- Ưu tiên primitives, wrappers, `String`, `ObjectName`, các kiểu Open MBean phù hợp.
- Với cấu trúc, cân nhắc MXBean/Open Data (`CompositeData`, `TabularData`).
- Tránh trả domain entities hoặc object graph nội bộ trực tiếp qua quản trị.
- Quản lý schema/field names/units như hợp đồng.
- Nếu thay data schema, cân nhắc field optional có default hợp lý hoặc API version mới.
- Test client tương thích từ JVM/agent version đang được hỗ trợ, không chỉ gọi server trong cùng process.

Một `MBeanInfo` chỉ có type `java.lang.Object` hoặc DTO không đảm bảo client remote deserialize được object thực tế.

## 20. Thay đổi notification cũng là thay đổi contract

Giả sử MBean phát:

```text
com.example.orders.queue.overloaded
```

Một listener dùng `NotificationFilterSupport`:

```java
filter.enableType(
    "com.example.orders.queue.overloaded"
);
```

Nếu bản mới đổi type thành:

```text
com.example.orders.queue.backlog.high
```

listener cũ không còn match.

Trong giai đoạn chuyển tiếp có thể phát cả hai type hoặc cung cấp đường migration phù hợp, nhưng phải cân nhắc **duplicate notifications** làm client xử lý hai lần.

Ngoài type, cần giữ semantics của `source`, `sequenceNumber`, `message`, `userData` và metadata `getNotificationInfo()` phù hợp. Nếu client dùng userData schema, thay đổi field cũng có thể breaking.

JMX notifications không phải durable message delivery; không dùng chúng như một cơ chế migration đảm bảo nhận đầy đủ mọi event.

## 21. Deprecation lifecycle

Một quy trình nâng cấp ít phá vỡ:

```text
Version N:
  Công bố contract v1

Version N+1:
  Thêm API v2 / alias
  Giữ v1
  Đánh dấu deprecated trong description và docs

Migration window:
  Cập nhật dashboards, automation, runbooks
  Đo lượng client còn gọi v1 (nếu có telemetry phù hợp)

Version N+K:
  Chỉ loại v1 trong đợt breaking có thông báo
```

Trong JMX không có cơ chế chung đảm bảo mọi client tự đọc hoặc tôn trọng deprecation description. Vì vậy:

- Có tài liệu API và migration guide.
- Giữ thời gian hỗ trợ phù hợp.
- Liệt kê client/agents chịu ảnh hưởng.
- Có tests xác nhận v1 còn hoạt động trong migration window.
- Chỉ loại API cũ khi có quyết định chính thức.

Không nên thay đổi semantics một operation cũ mà không đổi version chỉ vì source signature giống nhau.

## 22. Kiểm thử tương thích theo ba lớp

### Lớp A: metadata contract test

Khởi tạo Spring context và đọc `MBeanInfo` từ server. So sánh những attributes/operations/notifications bắt buộc vẫn tồn tại với tên, kiểu và flags.

### Lớp B: invocation contract test

Gọi các operation cũ theo **đúng JMX signature** và xác minh kết quả/side effect:

```java
connection.invoke(
    name,
    "retryFailed",
    new Object[] { 5 },
    new String[] { "int" }
);
```

Kiểm tra cả `getAttribute`, `setAttribute` (nếu supported), lỗi đầu vào và return type.

### Lớp C: remote client compatibility test

Từ một JMX client phiên bản cũ còn được hỗ trợ, kết nối vào server phiên bản mới rồi thực hiện các thao tác quan trọng. Điều này bắt lỗi classloading/serialization/connector mà test local không thấy.

Một nhóm test cân bằng có cả ba lớp sẽ bảo vệ tốt hơn so với chỉ kiểm tra annotation tồn tại trên class.

## 23. So sánh metadata theo tập thay vì thứ tự

Khi viết contract test, không nên dựa vào thứ tự mảng `getAttributes()` hoặc `getOperations()`, vì thứ tự không phải thứ client JMX dựa vào khi gọi theo tên.

Ví dụ helper:

```java
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

static boolean hasOperation(
        MBeanInfo info,
        String name,
        String returnType,
        String... paramTypes) {

    return Arrays.stream(info.getOperations()).anyMatch(op ->
        op.getName().equals(name)
        && op.getReturnType().equals(returnType)
        && Arrays.equals(
            Arrays.stream(op.getSignature())
                .map(p -> p.getType())
                .toArray(String[]::new),
            paramTypes
        )
    );
}
```

Với helper đó:

```java
assertTrue(
    hasOperation(info, "retryFailed", "void", "int")
);
```

Điều quan trọng là giữ **signature của operation** đúng, không phải vị trí của nó trong danh sách.

## 24. Checklist trước khi phát hành bản nâng cấp

| Câu hỏi | Cần xác nhận |
| --- | --- |
| ObjectName có đổi không? | So sánh canonical names |
| Attributes cũ còn không? | Tên, kiểu, readable/writable |
| Operations cũ còn không? | Tên, signature, return type |
| Semantics có đổi không? | Units, side effects, phạm vi tác động |
| Notifications có đổi không? | Types, userData schema, filters |
| Proxy/AOP có đổi không? | Metadata và invocation vẫn đúng |
| Exporter/assembler có đổi không? | Integration test runtime |
| Client cũ có kết nối được không? | Remote compatibility test |
| Có alias/deprecation window không? | Migration plan |
| Rolling upgrade có hỗ trợ hai version không? | Client capability checks |
| Security có thay đổi không? | Permissions và endpoint access |
| Lỗi startup có thể do trùng ObjectName không? | Registration policy/ownership |

## 25. Bài tập thực hành

1. Tạo `QueueAdminMBean` v1 với `PendingCount` và `retryFailed(int)`. Xuất qua Spring `MBeanExporter` và lưu baseline `MBeanInfo`.
2. Thêm `ActiveWorkers` ở v2, chạy contract test v1 và giải thích vì sao thay đổi này thường tương thích.
3. Đổi `PendingCount` thành `QueueDepth` mà không có alias; quan sát test v1 thất bại.
4. Khôi phục getter cũ làm alias, tạo description deprecation và kiểm thử cả hai attribute.
5. Đổi `retryFailed(int)` thành `retryFailed(long)`, gọi bằng signature `"int"` và phân tích lỗi.
6. Giữ overload `retryFailed(int)`, thêm operation mới, kiểm tra `MBeanInfo` có hai chữ ký.
7. Tạo hai adapter v1/v2 với hai ObjectName có key `api=v1` và `api=v2`.
8. Bật Spring AOP proxy ở bản mới, kiểm tra ObjectName và metadata không thay đổi.
9. Tạo một remote client test và xác minh kiểu trả về có thể deserialize được.
10. Viết migration checklist cho một dashboard đang dùng `PendingCount` trước khi deprecate attribute cũ.

## 26. Câu hỏi tự kiểm tra

- Vì sao management API vẫn cần backward compatibility dù không phải REST endpoint?
- Khi đổi tên attribute nhưng giữ Java method khác, client JMX có thể hỏng không?
- Tại sao thứ tự key property trong ObjectName không phải breaking change?
- Thay kiểu tham số `int` thành `long` ảnh hưởng `MBeanServer.invoke` thế nào?
- Thêm một operation mới có luôn không ảnh hưởng client cũ không?
- Vì sao contract test phải lấy `MBeanInfo` ở runtime?
- Khi nào nên dùng alias thay vì đổi tên trực tiếp?
- Khi nào nên tạo `ObjectName` versioned?
- Vì sao nâng Spring AOP proxy mode có thể ảnh hưởng JMX contract?
- Local test có kiểm tra đầy đủ remote serialization compatibility không?

**Ghi nhớ:** Management interface là một **API vận hành có client thực**. Khi nâng phiên bản Spring hoặc ứng dụng, hãy giữ `ObjectName`, attribute/operation/signature, notification và semantics ổn định. Với thay đổi không tương thích, sử dụng alias, deprecation window hoặc versioned MBean, rồi bảo vệ bằng metadata contract test, invocation test và remote client compatibility test.